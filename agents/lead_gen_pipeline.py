"""
Lead Generation Pipeline — Multi-Agent Demo
============================================
Two Discord bots collaborate visibly:

  Brian (Pipeline Manager)
    — orchestrates the run, posts status updates, owns the final report

  Sarah (Outreach Agent)
    — owns the outreach drafting step, posts in her own voice

Usage:
  python agents/lead_gen_pipeline.py "Company Name" "https://company.com"
  python agents/lead_gen_pipeline.py   (interactive)
"""

import json
import os
import sys
from datetime import datetime
import anthropic
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
CHANNEL   = os.environ["DISCORD_CHANNEL_ID"]
BRIAN_TOK = os.environ["BRIAN_TOKEN"]
SARAH_TOK = os.environ["SARAH_TOKEN"]
DISCORD   = "https://discord.com/api/v10"


# ── Discord helpers ────────────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def post(token: str, content: str = "", embeds: list = None) -> str:
    payload = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds
    r = requests.post(f"{DISCORD}/channels/{CHANNEL}/messages",
                      headers=_headers(token), json=payload)
    r.raise_for_status()
    return r.json()["id"]


def edit(token: str, msg_id: str, content: str):
    requests.patch(f"{DISCORD}/channels/{CHANNEL}/messages/{msg_id}",
                   headers=_headers(token), json={"content": content})


def score_colour(score: int) -> int:
    if score >= 75: return 0x57F287
    if score >= 50: return 0xFEE75C
    return 0xED4245


# ── JSON parser ────────────────────────────────────────────────────────────────

def parse_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        start = text.find("```")
        block = text[start:].split("\n", 1)[-1]
        block = block.rsplit("```", 1)[0]
        text = block.strip()
    if not text.startswith(("{", "[")):
        s, e = text.find("{"), text.rfind("}") + 1
        if s != -1 and e > s:
            text = text[s:e]
    return json.loads(text.strip())


# ── System prompts ─────────────────────────────────────────────────────────────

RESEARCH_PROMPT = """You are a lead research agent. Given a company name and optional website,
return a structured company profile as valid JSON only.

{
  "company_name": "string",
  "industry": "string",
  "estimated_size": "startup | smb | mid-market | enterprise",
  "location": "string or null",
  "what_they_do": "2-3 sentence description",
  "recent_signals": ["growth signals, news, or observations"],
  "decision_maker_titles": ["titles of people who would buy AI services"],
  "tech_stack_signals": ["technology signals you can infer"],
  "potential_pain_points": ["business problems AI could solve"]
}"""

QUALIFICATION_PROMPT = """You are a lead qualification agent. Score and qualify this company
for an AI engineering services pitch (custom Claude agents, n8n pipelines, API integrations).

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

OUTREACH_PROMPT = """You are Sarah, an outreach specialist. Write a short personalised
first-touch LinkedIn message for this lead.

Rules:
- Max 120 words
- Reference something specific about their business
- Lead with value, not credentials
- One clear CTA: a 20-minute call
- Sound human — no buzzwords like leverage, synergy, cutting-edge

Return valid JSON only:
{
  "message": "the full message text",
  "channel": "linkedin | email",
  "subject": "subject line if email, else null",
  "personalisation_hook": "the specific detail you used"
}"""


# ── Agent calls ────────────────────────────────────────────────────────────────

def research(company: str, website: str) -> dict:
    content = f"Company: {company}" + (f"\nWebsite: {website}" if website else "")
    r = client.messages.create(model="claude-opus-4-5", max_tokens=2048,
                                system=RESEARCH_PROMPT,
                                messages=[{"role": "user", "content": content}])
    return parse_json(r.content[0].text)


def qualify(profile: dict) -> dict:
    r = client.messages.create(model="claude-opus-4-5", max_tokens=1024,
                                system=QUALIFICATION_PROMPT,
                                messages=[{"role": "user", "content": json.dumps(profile, indent=2)}])
    return parse_json(r.content[0].text)


def outreach(profile: dict, qual: dict) -> dict:
    r = client.messages.create(model="claude-opus-4-5", max_tokens=1024,
                                system=OUTREACH_PROMPT,
                                messages=[{"role": "user", "content":
                                    f"Company profile:\n{json.dumps(profile, indent=2)}\n\n"
                                    f"Qualification:\n{json.dumps(qual, indent=2)}"}])
    return parse_json(r.content[0].text)


# ── Pipeline ───────────────────────────────────────────────────────────────────

def run(company: str, website: str = ""):
    started = datetime.now().strftime("%H:%M:%S")
    print(f"\n🚀 {company}\n")

    # Brian opens the run
    post(BRIAN_TOK,
         f"📋 **Pipeline initiated** — `{company}`{(' — ' + website) if website else ''}\n"
         f"Started at {started}. Spinning up the research agent...")

    # ── Step 1: Research ───────────────────────────────────────────────────────
    s1 = post(BRIAN_TOK, "🔍 **[Research Agent]** Pulling company intel...")
    print("→ Research...")
    try:
        profile = research(company, website)
        edit(BRIAN_TOK, s1, "✅ **[Research Agent]** Profile built.")
        print("  Done")
    except Exception as e:
        edit(BRIAN_TOK, s1, f"❌ **[Research Agent]** Failed: {e}")
        raise

    # Brian summarises what research found and hands off to qualification
    pain_points = profile.get("potential_pain_points", [])[:2]
    signals = profile.get("recent_signals", [])[:1]
    post(BRIAN_TOK,
         f"📤 **Research → Qualification handoff**\n"
         f"> **Industry:** {profile.get('industry', '—')}  |  "
         f"**Size:** {profile.get('estimated_size', '—')}  |  "
         f"**Location:** {profile.get('location', '—')}\n"
         f"> **Signal:** {signals[0] if signals else '—'}\n"
         f"> **Top pain point:** {pain_points[0] if pain_points else '—'}\n"
         f"Passing to qualification agent...")

    # ── Step 2: Qualification ──────────────────────────────────────────────────
    s2 = post(BRIAN_TOK, "⚖️ **[Qualification Agent]** Scoring the lead...")
    print("→ Qualifying...")
    try:
        qual = qualify(profile)
        edit(BRIAN_TOK, s2, "✅ **[Qualification Agent]** Scored.")
        print("  Done")
    except Exception as e:
        edit(BRIAN_TOK, s2, f"❌ **[Qualification Agent]** Failed: {e}")
        raise

    # Brian posts the score and hands off to Sarah
    score = qual.get("score", 0)
    tier = qual.get("tier", "warm").upper()
    tier_emoji = {"HOT": "🔥", "WARM": "🟡", "COLD": "🔵"}.get(tier, "⚪")
    fit = qual.get("fit_reasons", [])[:1]
    post(BRIAN_TOK,
         f"📤 **Qualification → Outreach handoff**\n"
         f"> **Score:** {score}/100  |  **Tier:** {tier_emoji} {tier}  |  "
         f"**Deal size:** {qual.get('estimated_deal_size', '—')}\n"
         f"> **Best fit reason:** {fit[0] if fit else '—'}\n"
         f"Handing to Sarah to draft outreach...")

    # ── Step 3: Sarah drafts outreach ──────────────────────────────────────────
    s3 = post(SARAH_TOK,
              f"👋 Hey, just picked this up from Brian — scoring a **{score}/100** "
              f"on {profile.get('company_name', company)}. Let me draft something...")
    print("→ Sarah drafting outreach...")
    try:
        draft = outreach(profile, qual)
        edit(SARAH_TOK, s3,
             f"✅ Draft ready for **{profile.get('company_name', company)}** "
             f"({draft.get('channel', 'linkedin').capitalize()})")
        print("  Done")
    except Exception as e:
        edit(SARAH_TOK, s3, f"❌ Outreach draft failed: {e}")
        raise

    # Sarah posts her draft in her own voice
    post(SARAH_TOK,
         f"✍️ **Here's what I'd send ({draft.get('channel', 'linkedin').capitalize()}):**\n"
         f"*Hook: {draft.get('personalisation_hook', '—')}*\n\n"
         f"```{draft.get('message', '—')}```")

    # ── Brian posts the final report embed ─────────────────────────────────────
    risks = qual.get("risks", [])
    fit_reasons = qual.get("fit_reasons", [])
    pain_points_all = profile.get("potential_pain_points", [])

    embed = {
        "title": f"📋 Lead Report — {profile.get('company_name', company)}",
        "color": score_colour(score),
        "timestamp": datetime.utcnow().isoformat(),
        "fields": [
            {"name": "Industry",    "value": profile.get("industry", "—"),                        "inline": True},
            {"name": "Size",        "value": profile.get("estimated_size", "—"),                  "inline": True},
            {"name": "Location",    "value": profile.get("location") or "—",                      "inline": True},
            {"name": f"Score  {tier_emoji} {tier}",
                                    "value": f"**{score}/100** — {qual.get('estimated_deal_size','—')}", "inline": True},
            {"name": "Urgency",     "value": qual.get("urgency", "normal").capitalize(),           "inline": True},
            {"name": "Channel",     "value": draft.get("channel", "linkedin").capitalize(),        "inline": True},
            {"name": "What They Do","value": profile.get("what_they_do", "—"),                    "inline": False},
            {"name": "Pain Points", "value": "\n".join(f"• {p}" for p in pain_points_all[:3]) or "—", "inline": False},
            {"name": "Why They Fit","value": "\n".join(f"• {r}" for r in fit_reasons[:3]) or "—", "inline": False},
            {"name": "Risks",       "value": "\n".join(f"• {r}" for r in risks[:2]) or "—",      "inline": False},
            {"name": "Recommended Approach", "value": qual.get("recommended_approach", "—"),      "inline": False},
        ],
        "footer": {"text": f"Pipeline completed {datetime.now().strftime('%H:%M:%S')}  •  Research → Qualification → Sarah (Outreach)"}
    }

    post(BRIAN_TOK, embeds=[embed])
    print(f"\n✅ Done — Score: {score}/100  |  Tier: {tier}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        company  = sys.argv[1]
        website  = sys.argv[2] if len(sys.argv) >= 3 else ""
    else:
        company = input("Company name: ").strip()
        website = input("Website (optional): ").strip()

    if not company:
        print("Company name required.")
        sys.exit(1)

    run(company, website)
