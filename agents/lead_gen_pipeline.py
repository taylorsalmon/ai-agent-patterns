"""
Lead Generation Pipeline — Multi-Agent Demo
============================================
Demonstrates:
  - Orchestrator → specialist agent delegation
  - Live Discord status updates as agents work
  - Structured outputs passed between agents
  - Rich Discord embed as final report

Usage:
  python agents/lead_gen_pipeline.py "Company Name" "https://company.com"

  or interactive:
  python agents/lead_gen_pipeline.py
"""

import json
import os
import sys
import time
from datetime import datetime
import anthropic
import requests
from dotenv import load_dotenv

from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_CHANNEL = os.environ["DISCORD_CHANNEL_ID"]
DISCORD_API = "https://discord.com/api/v10"


# ── Discord helpers ────────────────────────────────────────────────────────────

def parse_json(text: str) -> dict:
    """Extract and parse JSON from a response that may contain prose or code fences."""
    text = text.strip()
    # Extract content inside ``` fences if present anywhere in the response
    if "```" in text:
        start = text.find("```")
        block = text[start:].split("\n", 1)[-1]  # strip opening fence line
        block = block.rsplit("```", 1)[0]         # strip closing fence
        text = block.strip()
    # Fallback: find the first { and last } if still not clean JSON
    if not text.startswith("{") and not text.startswith("["):
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]
    return json.loads(text.strip())


def discord_headers():
    return {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json",
    }


def post_message(content: str) -> str:
    """Post a plain message, return message ID for later editing."""
    resp = requests.post(
        f"{DISCORD_API}/channels/{DISCORD_CHANNEL}/messages",
        headers=discord_headers(),
        json={"content": content},
    )
    resp.raise_for_status()
    return resp.json()["id"]


def edit_message(message_id: str, content: str):
    """Edit an existing message (used to update status lines)."""
    requests.patch(
        f"{DISCORD_API}/channels/{DISCORD_CHANNEL}/messages/{message_id}",
        headers=discord_headers(),
        json={"content": content},
    )


def post_embed(embed: dict):
    """Post a rich embed card."""
    resp = requests.post(
        f"{DISCORD_API}/channels/{DISCORD_CHANNEL}/messages",
        headers=discord_headers(),
        json={"embeds": [embed]},
    )
    resp.raise_for_status()


def score_colour(score: int) -> int:
    """Discord embed colour based on lead score (0–100)."""
    if score >= 75:
        return 0x57F287   # green
    if score >= 50:
        return 0xFEE75C   # yellow
    return 0xED4245       # red


# ── Agent definitions ──────────────────────────────────────────────────────────

RESEARCH_PROMPT = """You are a lead research agent. Given a company name and optional website,
research the company and return a structured profile.

Return valid JSON only:
{
  "company_name": "string",
  "industry": "string",
  "estimated_size": "startup | smb | mid-market | enterprise",
  "location": "string or null",
  "what_they_do": "2-3 sentence description",
  "recent_signals": ["list of growth signals, news, or relevant observations"],
  "decision_maker_titles": ["likely titles of people who'd buy AI services"],
  "tech_stack_signals": ["any technology signals you can infer"],
  "potential_pain_points": ["business problems AI could solve for them"]
}"""

QUALIFICATION_PROMPT = """You are a lead qualification agent. Given a company research profile,
score and qualify the lead for an AI engineering services pitch.

The buyer is an AI engineer offering: custom Claude agents, n8n automation pipelines,
API integrations, and workflow automation for business operations.

Return valid JSON only:
{
  "score": <integer 0-100>,
  "tier": "hot | warm | cold",
  "fit_reasons": ["why this is a good fit"],
  "risks": ["reasons they might not buy"],
  "recommended_approach": "one paragraph on how to approach this lead",
  "urgency": "low | normal | high",
  "estimated_deal_size": "small (<$10k) | medium ($10k-$50k) | large (>$50k)"
}"""

OUTREACH_PROMPT = """You are an outreach copywriting agent. Given a company profile and qualification,
write a short, personalised first-touch LinkedIn message or cold email.

Rules:
- Max 120 words
- Reference something specific about their business
- Lead with value, not credentials
- One clear call to action (a 20-minute call)
- Sound human, not like a template
- Do not mention AI buzzwords like "leverage", "synergy", "cutting-edge"

Return valid JSON only:
{
  "subject": "email subject line (if email) or null (if LinkedIn)",
  "message": "the full message text",
  "channel": "linkedin | email",
  "personalisation_hook": "what specific detail you used to personalise"
}"""


# ── Individual agent calls ─────────────────────────────────────────────────────

def run_research_agent(company: str, website: str) -> dict:
    user_content = f"Company: {company}"
    if website:
        user_content += f"\nWebsite: {website}"

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=RESEARCH_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return parse_json(response.content[0].text)


def run_qualification_agent(research: dict) -> dict:
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system=QUALIFICATION_PROMPT,
        messages=[{"role": "user", "content": f"Company profile:\n{json.dumps(research, indent=2)}"}],
    )
    return parse_json(response.content[0].text)


def run_outreach_agent(research: dict, qualification: dict) -> dict:
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system=OUTREACH_PROMPT,
        messages=[{"role": "user", "content": (
            f"Company profile:\n{json.dumps(research, indent=2)}\n\n"
            f"Qualification:\n{json.dumps(qualification, indent=2)}"
        )}],
    )
    return parse_json(response.content[0].text)


# ── Orchestrator ───────────────────────────────────────────────────────────────

def run_pipeline(company: str, website: str = ""):
    started_at = datetime.now().strftime("%H:%M:%S")
    print(f"\n🚀 Starting pipeline for: {company}\n")

    # Opening Discord message
    header_id = post_message(
        f"🤖 **Lead Gen Pipeline started**\n"
        f"**Target:** {company}{(' — ' + website) if website else ''}\n"
        f"**Started:** {started_at}"
    )

    # ── Step 1: Research ───────────────────────────────────────────────────────
    status_id = post_message("🔍 **Agent 1 / Research** — gathering company intel...")
    print("→ Research agent running...")

    try:
        research = run_research_agent(company, website)
        edit_message(status_id, "✅ **Agent 1 / Research** — complete")
        print("  Done")
    except Exception as e:
        edit_message(status_id, f"❌ **Agent 1 / Research** — failed: {e}")
        raise

    # ── Step 2: Qualification ──────────────────────────────────────────────────
    status_id = post_message("⚖️ **Agent 2 / Qualification** — scoring the lead...")
    print("→ Qualification agent running...")

    try:
        qualification = run_qualification_agent(research)
        edit_message(status_id, "✅ **Agent 2 / Qualification** — complete")
        print("  Done")
    except Exception as e:
        edit_message(status_id, f"❌ **Agent 2 / Qualification** — failed: {e}")
        raise

    # ── Step 3: Outreach ───────────────────────────────────────────────────────
    status_id = post_message("✍️ **Agent 3 / Outreach** — drafting personalised message...")
    print("→ Outreach agent running...")

    try:
        outreach = run_outreach_agent(research, qualification)
        edit_message(status_id, "✅ **Agent 3 / Outreach** — complete")
        print("  Done")
    except Exception as e:
        edit_message(status_id, f"❌ **Agent 3 / Outreach** — failed: {e}")
        raise

    # ── Final Report Embed ─────────────────────────────────────────────────────
    score = qualification.get("score", 0)
    tier = qualification.get("tier", "unknown").upper()
    tier_emoji = {"HOT": "🔥", "WARM": "🟡", "COLD": "🔵"}.get(tier, "⚪")

    pain_points = research.get("potential_pain_points", [])
    fit_reasons = qualification.get("fit_reasons", [])
    risks = qualification.get("risks", [])

    embed = {
        "title": f"📋 Lead Report — {research.get('company_name', company)}",
        "color": score_colour(score),
        "timestamp": datetime.utcnow().isoformat(),
        "fields": [
            {
                "name": "Industry",
                "value": research.get("industry", "Unknown"),
                "inline": True,
            },
            {
                "name": "Size",
                "value": research.get("estimated_size", "Unknown").replace("-", "‑"),
                "inline": True,
            },
            {
                "name": "Location",
                "value": research.get("location") or "Unknown",
                "inline": True,
            },
            {
                "name": f"Lead Score — {tier_emoji} {tier}",
                "value": f"**{score}/100**\n{qualification.get('estimated_deal_size', '')}",
                "inline": True,
            },
            {
                "name": "Urgency",
                "value": qualification.get("urgency", "normal").capitalize(),
                "inline": True,
            },
            {
                "name": "Best Channel",
                "value": outreach.get("channel", "linkedin").capitalize(),
                "inline": True,
            },
            {
                "name": "What They Do",
                "value": research.get("what_they_do", "—"),
                "inline": False,
            },
            {
                "name": "Pain Points",
                "value": "\n".join(f"• {p}" for p in pain_points[:3]) or "—",
                "inline": False,
            },
            {
                "name": "Why They Fit",
                "value": "\n".join(f"• {r}" for r in fit_reasons[:3]) or "—",
                "inline": False,
            },
            {
                "name": "Risks",
                "value": "\n".join(f"• {r}" for r in risks[:2]) or "—",
                "inline": False,
            },
            {
                "name": "Recommended Approach",
                "value": qualification.get("recommended_approach", "—"),
                "inline": False,
            },
            {
                "name": f"📨 Draft Outreach ({outreach.get('channel', 'linkedin').capitalize()})",
                "value": f"```{outreach.get('message', '—')}```",
                "inline": False,
            },
        ],
        "footer": {
            "text": f"Personalisation hook: {outreach.get('personalisation_hook', '—')}  •  Pipeline completed {datetime.now().strftime('%H:%M:%S')}"
        },
    }

    post_embed(embed)
    print(f"\n✅ Pipeline complete — report posted to Discord")
    print(f"   Score: {score}/100  |  Tier: {tier}  |  Deal size: {qualification.get('estimated_deal_size', '—')}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        company_name = sys.argv[1]
        company_website = sys.argv[2] if len(sys.argv) >= 3 else ""
    else:
        company_name = input("Company name: ").strip()
        company_website = input("Website (optional, press Enter to skip): ").strip()

    if not company_name:
        print("Error: company name is required")
        sys.exit(1)

    run_pipeline(company_name, company_website)
