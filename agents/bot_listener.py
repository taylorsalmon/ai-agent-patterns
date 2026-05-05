"""
Bot Listener — Sarah & Brian respond to Discord mentions
=========================================================
Sarah  — owns the Brain vault. Searches notes, responds with [[wiki links]].
Brian  — owns the pipeline. No Brain access. Reads Sarah's recent messages
         from the channel when he needs lead context.

Usage:
  python agents/bot_listener.py
"""

import asyncio
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import anthropic
import discord
from difflib import SequenceMatcher
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
BRIAN_TOKEN   = os.environ["BRIAN_TOKEN"]
SARAH_TOKEN   = os.environ["SARAH_TOKEN"]
CHANNEL_ID    = int(os.environ["DISCORD_CHANNEL_ID"])
BRAIN_PATH    = Path.home() / "Documents" / "Brain"
LEADS_PATH    = BRAIN_PATH / "Leads"

claude   = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
executor = ThreadPoolExecutor(max_workers=4)

# Shared reference so Brian can look up Sarah's user ID at runtime
sarah_user_id: int | None = None

LIST_TRIGGERS = ["list", "recent leads", "what leads", "who have we", "show me leads"]


# ── Brain vault (Sarah only) ───────────────────────────────────────────────────

CLIENTS_PATH = BRAIN_PATH / "Clients"


def fuzzy_match(query: str, target: str) -> int:
    """Score query words against target, tolerating typos via SequenceMatcher."""
    words = [w for w in re.sub(r"[^\w\s]", "", query.lower()).split() if len(w) > 2]
    target_words = re.sub(r"[^\w\s]", "", target.lower()).split()
    if not words:
        return 0
    hits = 0
    for qw in words:
        if qw in target.lower():
            hits += 2  # exact substring
            continue
        for tw in target_words:
            if SequenceMatcher(None, qw, tw).ratio() > 0.75:
                hits += 1  # close enough (handles typos like clareden/clarendon)
                break
    return hits


def find_note(query: str) -> Path | None:
    """Find a single best-matching note anywhere in the Brain vault."""
    best_score, best_path = 0, None
    for note in BRAIN_PATH.rglob("*.md"):
        score = fuzzy_match(query, note.stem)
        if score > best_score:
            best_score, best_path = score, note
    return best_path if best_score > 0 else None


def search_brain(query: str, max_results: int = 4) -> tuple[list[dict], list[str]]:
    BRAIN_PATH.mkdir(parents=True, exist_ok=True)
    scored = []

    for note in BRAIN_PATH.rglob("*.md"):
        try:
            content = note.read_text(encoding="utf-8")
        except Exception:
            continue
        name_score    = fuzzy_match(query, note.stem) * 2
        content_score = 1 if query.lower() in content.lower() else 0
        total = name_score + content_score
        if total > 0:
            rel    = note.relative_to(BRAIN_PATH)
            folder = rel.parent.name if rel.parent.name != "." else "Brain"
            scored.append({
                "stem":    note.stem,
                "folder":  folder,
                "score":   total,
                "snippet": content[:400].strip(),
                "path":    note,
            })

    scored.sort(key=lambda r: r["score"], reverse=True)
    scored = scored[:max_results]
    wiki_links = [f"[[{r['stem']}]]" for r in scored]
    return scored, wiki_links


def list_recent_leads(n: int = 6) -> str:
    LEADS_PATH.mkdir(parents=True, exist_ok=True)
    notes = sorted(LEADS_PATH.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not notes:
        return "No leads in the Brain yet."
    return "\n".join(
        f"• **{note.stem}** — {datetime.fromtimestamp(note.stat().st_mtime).strftime('%d %b %Y')}"
        for note in notes[:n]
    )


def convert_to_client(query: str, monthly_retainer: int | None) -> tuple[bool, str]:
    """
    Move a lead note from Leads/ to Clients/, update its frontmatter.
    Returns (success, message).
    """
    note_path = find_note(query)
    if not note_path:
        return False, f"Couldn't find a note matching '{query}' in the vault."

    # Only move from Leads — don't touch notes already in Clients or elsewhere
    if LEADS_PATH not in note_path.parents and note_path.parent != LEADS_PATH:
        return False, f"[[{note_path.stem}]] isn't in the Leads folder — it may already be a client."

    CLIENTS_PATH.mkdir(parents=True, exist_ok=True)
    dest = CLIENTS_PATH / note_path.name

    content = note_path.read_text(encoding="utf-8")
    today   = datetime.now().strftime("%Y-%m-%d")

    # Update frontmatter fields
    content = re.sub(r"^verified:.*$",        "verified: true",           content, flags=re.MULTILINE)
    content = re.sub(r"^tags:.*$",
                     f"tags: [client, active]",                           content, flags=re.MULTILINE)

    # Inject or update status + client fields after the closing ---
    client_block = (
        f"\nstatus: client\n"
        f"date_converted: {today}\n"
        f"monthly_retainer: {monthly_retainer or 'TBC'}\n"
    )
    if "status:" in content:
        content = re.sub(r"^status:.*$", f"status: client", content, flags=re.MULTILINE)
    else:
        content = content.replace("---\n", f"---{client_block}", 1)

    # Append a conversion log entry
    content += f"\n\n## Conversion Log\n- **{today}** — Converted to client. Retainer: ${monthly_retainer:,}/mo\n"

    dest.write_text(content, encoding="utf-8")
    note_path.unlink()  # remove from Leads

    return True, f"✅ **[[{note_path.stem}]]** moved to Clients and updated — ${monthly_retainer:,}/mo retainer logged."


# ── Company picker (Brian) ─────────────────────────────────────────────────────

def classify_sarah_intent(message: str, recent_context: str = "") -> dict:
    """Classify what Sarah should do, with optional recent channel context."""
    context_block = (
        f"\nRecent conversation context (last few messages):\n{recent_context}\n"
        if recent_context else ""
    )
    r = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        system=(
            "Classify the intent of a message sent to Sarah, an account manager at a social media agency. "
            f"{context_block}"
            "Intents: "
            "convert_to_client — user wants to move a lead to client status. "
            "This includes follow-up messages where Sarah previously asked for the company name and the user is now providing it. "
            "If the context shows Sarah asked 'which company?' and the user replied with a name, that is convert_to_client. "
            "convert_to_client triggers on: convert, move to client, they signed, onboard, paying, confirmed, just got off the call. "
            "list_leads — user wants to see what's in the Leads folder. "
            "search — user is asking about a specific company or lead. "
            "general — anything else. "
            "Return valid JSON only: "
            "{\"intent\": \"convert_to_client|list_leads|search|general\", "
            "\"company\": \"company name if mentioned, else null\", "
            "\"monthly_retainer\": <integer dollars per month if mentioned, else null>}"
        ),
        messages=[{"role": "user", "content": message}],
    )
    text = r.content[0].text.strip()
    if "```" in text:
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return json.loads(text.strip())


def classify_intent(message: str) -> dict:
    """Use Claude to classify what Brian should do with this message."""
    r = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        system=(
            "Classify the intent of a message sent to Brian, a pipeline manager at a social media agency. "
            "Use find_lead when the user wants to find, source, prospect, or research a NEW lead — "
            "any phrasing that implies finding someone we haven't approached yet. "
            "Use list_leads when asking what leads already exist in the system. "
            "Use general for status, pipeline, or other questions. "
            "When in doubt between find_lead and list_leads, prefer find_lead. "
            "Return valid JSON only: "
            "{\"intent\": \"find_lead | list_leads | general\", "
            "\"brief\": \"extracted industry/location/type brief for find_lead, else null\"}"
        ),
        messages=[{"role": "user", "content": message}],
    )
    text = r.content[0].text.strip()
    if "```" in text:
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return json.loads(text.strip())


def pick_target_company(brief: str) -> dict:
    r = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        system=(
            "You are a business development strategist for Resolve Studios, a social media marketing agency. "
            "Given an industry or brief, suggest the single best Australian company to prospect "
            "for social media management services — one with weak or inconsistent social presence "
            "but clear budget and growth signals. "
            "Return valid JSON only: "
            "{\"company\": \"string\", \"website\": \"https://...\", "
            "\"reason\": \"one sentence why they're a strong prospect\"}"
        ),
        messages=[{"role": "user", "content": brief}],
    )
    text = r.content[0].text.strip()
    if "```" in text:
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return json.loads(text.strip())


# ── Claude persona replies ─────────────────────────────────────────────────────

def sarah_reply(question: str, results: list[dict], wiki_links: list[str]) -> str:
    brain_context = (
        "\n\n".join(f"[{r['folder']}/{r['stem']}]\n{r['snippet']}" for r in results)
        if results else "No matching notes found in the Brain vault."
    )
    links_str = ", ".join(wiki_links) if wiki_links else "none"

    system = f"""You are Sarah, an account manager at Resolve Studios, a social media marketing agency.
You work alongside Brian who manages the lead pipeline. You are the keeper of the Brain vault.

Personality: warm, switched-on, commercially sharp. Talk like someone who knows their clients well.
Keep replies under 150 words. Use first person.

Use Obsidian [[wiki link]] format when referencing notes. Relevant links: {links_str}

Brain vault content:
{brain_context}

Reference vault info naturally, highlighting social media specifics (platforms, content gaps, presence).
If nothing found, say so and suggest asking Brian to run the pipeline on them."""

    r = claude.messages.create(
        model="claude-opus-4-5", max_tokens=300, system=system,
        messages=[{"role": "user", "content": question}],
    )
    return r.content[0].text.strip()


def get_leads_context(query: str) -> str:
    """Brian's only vault access — read-only search of the Leads folder."""
    LEADS_PATH.mkdir(parents=True, exist_ok=True)
    query_lower = query.lower()
    matches = []

    for note in LEADS_PATH.glob("*.md"):
        try:
            content = note.read_text(encoding="utf-8")
        except Exception:
            continue
        if query_lower in note.stem.lower() or query_lower in content.lower():
            matches.append(f"### {note.stem}\n{content[:500].strip()}")

    if not matches:
        # No query match — return all lead summaries (name + score line only)
        summaries = []
        for note in sorted(LEADS_PATH.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:8]:
            try:
                first_lines = note.read_text(encoding="utf-8")[:200]
            except Exception:
                continue
            summaries.append(f"• {note.stem}: {first_lines.splitlines()[0] if first_lines else ''}")
        return "\n".join(summaries) if summaries else "No leads on file yet."

    return "\n\n---\n\n".join(matches[:3])


def brian_reply(question: str, leads_context: str, sarah_context: str) -> str:
    system = f"""You are Brian, pipeline manager at Resolve Studios, a social media marketing agency.
You work with Sarah — she owns the full Brain vault, you manage the pipeline and have read access to the Leads folder.

Personality: efficient, direct, operational. Under 100 words.

Leads folder (your data):
{leads_context}

Sarah's recent channel messages (for additional context):
{sarah_context if sarah_context else "Nothing recent from Sarah."}

Answer confidently using the leads data above. If a specific detail isn't in your leads folder,
say Sarah would have the full notes."""

    r = claude.messages.create(
        model="claude-opus-4-5", max_tokens=200, system=system,
        messages=[{"role": "user", "content": question}],
    )
    return r.content[0].text.strip()


# ── Fetch Sarah's recent messages from the channel ────────────────────────────

async def get_sarah_messages(channel: discord.TextChannel, limit: int = 20) -> str:
    """Read the last `limit` messages and return those sent by Sarah."""
    if sarah_user_id is None:
        return ""
    messages = []
    async for msg in channel.history(limit=limit):
        if msg.author.id == sarah_user_id and msg.content:
            messages.append(f"[{msg.created_at.strftime('%H:%M')}] Sarah: {msg.content[:300]}")
    messages.reverse()
    return "\n".join(messages)


# ── Pipeline runner ────────────────────────────────────────────────────────────

def _run_pipeline_sync(company: str, website: str):
    sys.path.insert(0, str(Path(__file__).parent))
    from lead_gen_pipeline import run
    run(company, website)


async def trigger_pipeline(company: str, website: str):
    await asyncio.get_event_loop().run_in_executor(executor, _run_pipeline_sync, company, website)


# ── Helpers ────────────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    return re.sub(r"<@!?\d+>", "", text).strip()

def is_list_request(text: str) -> bool:
    return any(t in text.lower() for t in LIST_TRIGGERS)


# ── Discord clients ────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True


class SarahBot(discord.Client):
    async def on_ready(self):
        global sarah_user_id
        sarah_user_id = self.user.id
        print(f"  ✅ Sarah online ({self.user}) — Brain vault access: YES")

    async def on_message(self, message: discord.Message):
        if message.author.bot or message.channel.id != CHANNEL_ID:
            return
        if self.user not in message.mentions:
            return

        question = clean(message.content)
        if not question:
            await message.channel.send("Hey! Ask me about a lead, or tell me to convert one to a client.")
            return

        # Fetch recent messages so Sarah understands follow-up context
        recent_msgs = []
        async for msg in message.channel.history(limit=6):
            if msg.id == message.id:
                continue
            author = "Sarah" if (sarah_user_id and msg.author.id == sarah_user_id) else msg.author.display_name
            recent_msgs.append(f"{author}: {msg.content[:150]}")
        recent_context = "\n".join(reversed(recent_msgs))

        async with message.channel.typing():
            intent_data = await asyncio.get_event_loop().run_in_executor(
                executor, classify_sarah_intent, question, recent_context
            )
        intent   = intent_data.get("intent", "general")
        company  = intent_data.get("company")
        retainer = intent_data.get("monthly_retainer")

        # ── List leads ─────────────────────────────────────────────────────────
        if intent == "list_leads":
            recent = await asyncio.get_event_loop().run_in_executor(executor, list_recent_leads)
            await message.channel.send(f"**Leads in the Brain:**\n{recent}")
            return

        # ── Convert lead → client ──────────────────────────────────────────────
        if intent == "convert_to_client":
            if not company:
                await message.channel.send(
                    "Which company are we converting? Give me the name and I'll move them to Clients."
                )
                return
            async with message.channel.typing():
                success, msg = await asyncio.get_event_loop().run_in_executor(
                    executor, convert_to_client, company, retainer
                )
            await message.channel.send(msg)
            return

        # ── Search / general ───────────────────────────────────────────────────
        async with message.channel.typing():
            results, wiki_links = await asyncio.get_event_loop().run_in_executor(
                executor, search_brain, company or question
            )
            reply = await asyncio.get_event_loop().run_in_executor(
                executor, sarah_reply, question, results, wiki_links
            )
        await message.channel.send(reply)


class BrianBot(discord.Client):
    async def on_ready(self):
        print(f"  ✅ Brian online ({self.user}) — Brain vault access: NO (reads Sarah's messages)")

    async def on_message(self, message: discord.Message):
        if message.author.bot or message.channel.id != CHANNEL_ID:
            return
        if self.user not in message.mentions:
            return

        question = clean(message.content)
        if not question:
            await message.channel.send(
                "Brian here. Ask me to find a lead, run the pipeline, or check pipeline status."
            )
            return

        # ── Classify intent with Claude ────────────────────────────────────────
        async with message.channel.typing():
            intent_result = await asyncio.get_event_loop().run_in_executor(
                executor, classify_intent, question
            )
        intent = intent_result.get("intent", "general")
        brief  = intent_result.get("brief") or question

        # ── List leads ─────────────────────────────────────────────────────────
        if intent == "list_leads" or is_list_request(question):
            leads_context = await asyncio.get_event_loop().run_in_executor(
                executor, get_leads_context, question
            )
            sarah_context = await get_sarah_messages(message.channel)
            reply = await asyncio.get_event_loop().run_in_executor(
                executor, brian_reply, question, leads_context, sarah_context
            )
            await message.channel.send(reply)
            return

        # ── Find / research a lead ─────────────────────────────────────────────
        if intent == "find_lead":
            async with message.channel.typing():
                try:
                    target = await asyncio.get_event_loop().run_in_executor(
                        executor, pick_target_company, brief
                    )
                except Exception as e:
                    await message.channel.send(f"❌ Couldn't pick a target: {e}")
                    return

            await message.channel.send(
                f"🎯 On it — best target I can see:\n"
                f"> **{target['company']}** — {target.get('website', 'no website')}\n"
                f"> {target['reason']}\n\n"
                f"⚠️ AI-suggested — verify they exist before outreach. Running the pipeline now..."
            )
            try:
                await trigger_pipeline(target["company"], target.get("website", ""))
            except Exception as e:
                await message.channel.send(f"❌ Pipeline failed: {e}")
            return

        # ── General question ───────────────────────────────────────────────────
        async with message.channel.typing():
            leads_context = await asyncio.get_event_loop().run_in_executor(
                executor, get_leads_context, question
            )
            sarah_context = await get_sarah_messages(message.channel)
            reply = await asyncio.get_event_loop().run_in_executor(
                executor, brian_reply, question, leads_context, sarah_context
            )
        await message.channel.send(reply)


# ── Entry point ────────────────────────────────────────────────────────────────

async def main():
    print("\n🤖 Starting Sarah & Brian...\n")
    sarah = SarahBot(intents=intents)
    brian = BrianBot(intents=intents)
    await asyncio.gather(
        sarah.start(SARAH_TOKEN),
        brian.start(BRIAN_TOKEN),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down.")
