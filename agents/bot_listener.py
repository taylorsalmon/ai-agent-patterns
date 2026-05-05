"""
Bot Listener — Sarah & Brian respond to Discord mentions
=========================================================
Sarah  — outreach specialist, searches the full Brain vault and links
         to relevant notes using Obsidian [[wiki links]]

Brian  — pipeline manager, can trigger a full lead gen run from Discord
         when asked to find a lead in a given industry or company

Usage:
  python agents/bot_listener.py

Keep running in a terminal. Ctrl+C to stop.
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
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
BRIAN_TOKEN   = os.environ["BRIAN_TOKEN"]
SARAH_TOKEN   = os.environ["SARAH_TOKEN"]
CHANNEL_ID    = int(os.environ["DISCORD_CHANNEL_ID"])
BRAIN_PATH    = Path.home() / "Documents" / "Brain"
LEADS_PATH    = BRAIN_PATH / "Leads"

claude    = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
executor  = ThreadPoolExecutor(max_workers=4)

# ── Intent detection keywords ──────────────────────────────────────────────────

PIPELINE_TRIGGERS = [
    "find me a lead", "find a lead", "research a lead", "run the pipeline",
    "run pipeline", "look into", "prospect", "find someone in", "who should we target",
    "give me a lead", "get me a lead", "find leads in",
]

LIST_TRIGGERS = ["list", "recent leads", "what leads", "who have we", "show me leads"]


# ── Brain vault search ─────────────────────────────────────────────────────────

def search_brain(query: str, max_results: int = 4) -> tuple[list[dict], list[str]]:
    """
    Search the full Brain vault for query.
    Returns (results, wiki_links) where wiki_links are Obsidian [[Note]] references.
    """
    BRAIN_PATH.mkdir(parents=True, exist_ok=True)
    query_lower = query.lower()
    results = []

    for note in BRAIN_PATH.rglob("*.md"):
        try:
            content = note.read_text(encoding="utf-8")
        except Exception:
            continue

        name_match    = query_lower in note.stem.lower()
        content_match = query_lower in content.lower()

        if name_match or content_match:
            # Score: name match ranks higher than content match
            score = (2 if name_match else 0) + (1 if content_match else 0)
            # Relative path from Brain root for the wiki link
            rel = note.relative_to(BRAIN_PATH)
            folder = rel.parent.name if rel.parent.name != "." else "Brain"
            results.append({
                "stem":    note.stem,
                "folder":  folder,
                "score":   score,
                "snippet": content[:400].strip(),
                "path":    str(rel),
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:max_results]

    wiki_links = [f"[[{r['stem']}]]" for r in results]
    return results, wiki_links


def list_recent_leads(n: int = 6) -> str:
    LEADS_PATH.mkdir(parents=True, exist_ok=True)
    notes = sorted(LEADS_PATH.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not notes:
        return "No leads in the Brain yet — run the pipeline on a company to add one."
    lines = [
        f"• **{note.stem}** — {datetime.fromtimestamp(note.stat().st_mtime).strftime('%d %b %Y')}"
        for note in notes[:n]
    ]
    return "\n".join(lines)


# ── Company picker (Brian uses this to choose who to prospect) ─────────────────

def pick_target_company(industry_or_brief: str) -> dict:
    """Ask Claude to suggest the single best target company for a given brief."""
    r = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        system=(
            "You are a B2B sales strategist. Given an industry or brief, suggest the single "
            "best Australian company to prospect for AI engineering services. "
            "Return valid JSON only: "
            "{\"company\": \"Company Name\", \"website\": \"https://...\", "
            "\"reason\": \"one sentence why this is the best target\"}"
        ),
        messages=[{"role": "user", "content": industry_or_brief}],
    )
    text = r.content[0].text.strip()
    if "```" in text:
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return json.loads(text.strip())


# ── Claude persona replies ─────────────────────────────────────────────────────

def sarah_reply(question: str, results: list[dict], wiki_links: list[str]) -> str:
    if results:
        brain_context = "\n\n".join(
            f"[{r['folder']}/{r['stem']}]\n{r['snippet']}" for r in results
        )
        links_str = ", ".join(wiki_links) if wiki_links else "none"
    else:
        brain_context = "No matching notes found in the Brain vault."
        links_str = "none"

    system = f"""You are Sarah, an outreach specialist agent. You have access to the team's Brain vault.

Your personality: warm, direct, sharp. Talk like a smart sales professional, not a robot.
Keep replies under 150 words. Use first person.

When referencing Brain notes, use their Obsidian wiki link format exactly as provided.
Relevant wiki links for this query: {links_str}

Brain vault content found:
{brain_context}

If vault has relevant info, reference it naturally using the [[wiki link]] format.
If the note is in a subfolder (e.g. Leads), still just use [[Company Name]] — Obsidian resolves it.
If nothing found, say so and suggest running the pipeline."""

    r = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return r.content[0].text.strip()


def brian_reply(question: str, results: list[dict], wiki_links: list[str]) -> str:
    brain_context = (
        "\n\n".join(f"[{r['stem']}]\n{r['snippet']}" for r in results)
        if results else "No matching notes found."
    )

    system = f"""You are Brian, a pipeline manager agent. Efficient, operational, brief.
Keep replies under 100 words.

Brain vault context:
{brain_context}

If asked about pipeline status or leads, reference what's in the vault.
Do NOT handle requests to find new leads — just answer the question asked."""

    r = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=200,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return r.content[0].text.strip()


# ── Run pipeline from within the bot (blocking → thread) ──────────────────────

def _run_pipeline_sync(company: str, website: str):
    """Import and call the pipeline run() function in a thread."""
    sys.path.insert(0, str(Path(__file__).parent))
    from lead_gen_pipeline import run
    run(company, website)


async def trigger_pipeline(company: str, website: str):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, _run_pipeline_sync, company, website)


# ── Shared intent parser ───────────────────────────────────────────────────────

def clean(text: str) -> str:
    return re.sub(r"<@!?\d+>", "", text).strip()


def is_pipeline_request(text: str) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in PIPELINE_TRIGGERS)


def is_list_request(text: str) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in LIST_TRIGGERS)


# ── Discord clients ────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True


class SarahBot(discord.Client):
    async def on_ready(self):
        print(f"  ✅ Sarah online ({self.user})")

    async def on_message(self, message: discord.Message):
        if message.author.bot or message.channel.id != CHANNEL_ID:
            return
        if self.user not in message.mentions:
            return

        question = clean(message.content)
        if not question:
            await message.channel.send(
                "Hey! Ask me about a lead, a company, or anything in the Brain."
            )
            return

        async with message.channel.typing():
            results, wiki_links = await asyncio.get_event_loop().run_in_executor(
                executor, search_brain, question
            )
            reply = await asyncio.get_event_loop().run_in_executor(
                executor, sarah_reply, question, results, wiki_links
            )

        await message.channel.send(reply)


class BrianBot(discord.Client):
    async def on_ready(self):
        print(f"  ✅ Brian online ({self.user})")

    async def on_message(self, message: discord.Message):
        if message.author.bot or message.channel.id != CHANNEL_ID:
            return
        if self.user not in message.mentions:
            return

        question = clean(message.content)
        if not question:
            await message.channel.send(
                "Brian here. Ask me to find a lead, run the pipeline, or check recent leads."
            )
            return

        # ── List recent leads ──────────────────────────────────────────────────
        if is_list_request(question):
            recent = await asyncio.get_event_loop().run_in_executor(
                executor, list_recent_leads
            )
            await message.channel.send(f"**Recent leads in the Brain:**\n{recent}")
            return

        # ── Trigger pipeline ───────────────────────────────────────────────────
        if is_pipeline_request(question):
            async with message.channel.typing():
                try:
                    target = await asyncio.get_event_loop().run_in_executor(
                        executor, pick_target_company, question
                    )
                except Exception as e:
                    await message.channel.send(f"❌ Couldn't pick a target: {e}")
                    return

            await message.channel.send(
                f"🎯 Best target for **\"{question}\"**:\n"
                f"> **{target['company']}** — {target.get('website', 'no website')}\n"
                f"> {target['reason']}\n\n"
                f"Kicking off the pipeline now..."
            )

            try:
                await trigger_pipeline(target["company"], target.get("website", ""))
            except Exception as e:
                await message.channel.send(f"❌ Pipeline failed: {e}")
            return

        # ── General question ───────────────────────────────────────────────────
        async with message.channel.typing():
            results, _ = await asyncio.get_event_loop().run_in_executor(
                executor, search_brain, question
            )
            reply = await asyncio.get_event_loop().run_in_executor(
                executor, brian_reply, question, results, []
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
