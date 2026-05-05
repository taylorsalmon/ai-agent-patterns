"""
Bot Listener — Sarah & Brian respond to Discord mentions
=========================================================
Keeps a WebSocket connection to Discord and responds when mentioned.

Sarah  — outreach specialist, checks the Brain vault for lead notes
Brian  — pipeline manager, can trigger new pipeline runs when asked

Usage:
  python agents/bot_listener.py

Keep this running in a terminal. Both bots listen on the same process.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import discord
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

ANTHROPIC_KEY  = os.environ["ANTHROPIC_API_KEY"]
BRIAN_TOKEN    = os.environ["BRIAN_TOKEN"]
SARAH_TOKEN    = os.environ["SARAH_TOKEN"]
CHANNEL_ID     = int(os.environ["DISCORD_CHANNEL_ID"])
BRAIN_PATH     = Path.home() / "Documents" / "Brain"
LEADS_PATH     = BRAIN_PATH / "Leads"

claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)


# ── Brain vault helpers ────────────────────────────────────────────────────────

def search_brain(query: str) -> str:
    """Search lead notes in the Brain vault for a company name or keyword."""
    LEADS_PATH.mkdir(parents=True, exist_ok=True)
    results = []
    query_lower = query.lower()

    for note in LEADS_PATH.glob("*.md"):
        content = note.read_text(encoding="utf-8")
        if query_lower in content.lower() or query_lower in note.stem.lower():
            # Return first 600 chars of the note as context
            results.append(f"### {note.stem}\n{content[:600]}{'...' if len(content) > 600 else ''}")

    if results:
        return "\n\n---\n\n".join(results)
    return f"No notes found matching '{query}' in the Brain vault."


def list_recent_leads(n: int = 5) -> str:
    """Return the n most recently modified lead notes."""
    LEADS_PATH.mkdir(parents=True, exist_ok=True)
    notes = sorted(LEADS_PATH.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not notes:
        return "No leads in the Brain vault yet."
    lines = [f"• **{n.stem}** — updated {datetime.fromtimestamp(n.stat().st_mtime).strftime('%d %b %Y')}"
             for n in notes[:n]]
    return "\n".join(lines)


# ── Claude response helpers ────────────────────────────────────────────────────

def sarah_reply(question: str, brain_context: str) -> str:
    system = f"""You are Sarah, an outreach specialist agent working with Brian on a lead generation pipeline.
You have access to the team's Brain vault — a set of lead research notes.

Your personality: warm, direct, practical. You talk like a sharp sales professional, not a robot.
Keep replies under 120 words. Use first person. No bullet points unless listing multiple items.

Current Brain vault context relevant to this question:
{brain_context}

If the vault has relevant info, reference it naturally.
If not, say you don't have that lead on file yet and suggest running the pipeline on them."""

    r = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return r.content[0].text.strip()


def brian_reply(question: str, brain_context: str) -> str:
    system = f"""You are Brian, a pipeline manager agent. You oversee the lead generation pipeline
and coordinate with Sarah on outreach.

Your personality: efficient, operational, no-nonsense. Brief and precise.
Keep replies under 100 words. Reference pipeline status, scores, or next steps where relevant.

Current Brain vault context relevant to this question:
{brain_context}

If asked to run the pipeline on a company, tell them to use:
  python agents/lead_gen_pipeline.py "Company Name"
Or confirm you'll kick it off."""

    r = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=250,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return r.content[0].text.strip()


# ── Extract company name from a question ──────────────────────────────────────

def extract_company(text: str) -> str:
    """Best-effort extract of a company name from a question."""
    # Strip mention patterns like <@123456>
    clean = re.sub(r"<@!?\d+>", "", text).strip()
    # Look for quoted company names first
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', clean)
    if quoted:
        return quoted[0][0] or quoted[0][1]
    # Otherwise return the cleaned text for broad search
    return clean


# ── Discord bot clients ────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True


class SarahBot(discord.Client):
    async def on_ready(self):
        print(f"  Sarah online — {self.user}")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != CHANNEL_ID:
            return
        if self.user not in message.mentions:
            return

        question = re.sub(r"<@!?\d+>", "", message.content).strip()
        if not question:
            await message.channel.send("Hey! Ask me anything about a lead or the Brain vault.")
            return

        async with message.channel.typing():
            company = extract_company(question)
            brain_context = search_brain(company)
            reply = sarah_reply(question, brain_context)

        await message.channel.send(f"{reply}")


class BrianBot(discord.Client):
    async def on_ready(self):
        print(f"  Brian online — {self.user}")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != CHANNEL_ID:
            return
        if self.user not in message.mentions:
            return

        question = re.sub(r"<@!?\d+>", "", message.content).strip()
        if not question:
            await message.channel.send("Brian here. Need me to run the pipeline on someone?")
            return

        # Special case: list recent leads
        if any(w in question.lower() for w in ["list", "recent", "what leads", "who have"]):
            recent = list_recent_leads()
            await message.channel.send(f"Recent leads in the Brain:\n{recent}")
            return

        async with message.channel.typing():
            company = extract_company(question)
            brain_context = search_brain(company)
            reply = brian_reply(question, brain_context)

        await message.channel.send(f"{reply}")


# ── Run both bots concurrently ─────────────────────────────────────────────────

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
