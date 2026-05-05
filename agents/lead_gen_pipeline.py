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
import re
import sys
from datetime import datetime
import anthropic
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
CHANNEL          = os.environ["DISCORD_CHANNEL_ID"]
BRIAN_TOK        = os.environ["BRIAN_TOKEN"]
SARAH_TOK        = os.environ["SARAH_TOKEN"]
DISCORD          = "https://discord.com/api/v10"
FIREBASE_URL     = os.environ.get("FIREBASE_URL", "")
FIREBASE_SECRET  = os.environ.get("FIREBASE_SECRET", "")
RESOLVE_CRM_URL  = os.environ.get("RESOLVE_CRM_URL", "")
RESOLVE_CRM_SECRET = os.environ.get("RESOLVE_CRM_SECRET", "")


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

AGENCY_NAME = "Resolve Studios"
AGENCY_SERVICES = "social media management, content creation, paid social advertising, and brand growth on Instagram, TikTok, Facebook, and LinkedIn"

RESEARCH_PROMPT = f"""You are a lead research agent working for {AGENCY_NAME}, a social media marketing agency.
Given a company name and optional website, research the company and return a structured profile
focused on their social media presence and marketing opportunity.

Return valid JSON only:
{{
  "company_name": "string",
  "industry": "string",
  "estimated_size": "startup | smb | mid-market | enterprise",
  "location": "string or null",
  "what_they_do": "2-3 sentence description",
  "social_media_presence": "strong | moderate | weak | none — based on what you can infer",
  "active_platforms": ["platforms they likely use e.g. Instagram, LinkedIn, TikTok"],
  "content_gaps": ["types of content they are likely missing or underutilising"],
  "recent_signals": ["growth signals, campaigns, launches, or news worth referencing"],
  "decision_maker_titles": ["titles of people who buy marketing services e.g. Marketing Manager, CMO, Founder"],
  "potential_pain_points": ["social media and marketing problems {AGENCY_NAME} could solve for them"]
}}"""

QUALIFICATION_PROMPT = f"""You are a lead qualification agent for {AGENCY_NAME}, a social media marketing agency
offering {AGENCY_SERVICES}.

Score this company as a potential social media management client.

Score high if: they have weak or inconsistent social presence, they're in a visual or consumer-facing industry,
they're growing and would benefit from brand awareness, or they have budget signals.

Return valid JSON only:
{{
  "score": <integer 0-100>,
  "tier": "hot | warm | cold",
  "fit_reasons": ["why they're a good fit for social media services"],
  "risks": ["reasons they might not convert"],
  "recommended_approach": "one paragraph — what angle to lead with and why",
  "urgency": "low | normal | high",
  "estimated_monthly_retainer": "small (<$2k/mo) | medium ($2k-$5k/mo) | large (>$5k/mo)"
}}"""

OUTREACH_PROMPT = f"""You are Sarah, an account manager at {AGENCY_NAME}, a social media marketing agency.
Write a short, personalised first-touch outreach message for this prospect.

{AGENCY_NAME} offers: {AGENCY_SERVICES}.

Rules:
- Max 120 words
- Reference something specific and real about their business or social presence
- Lead with what we can do for them, not who we are
- One clear CTA: a free 15-minute social media audit call
- Sound like a real person — warm, confident, not salesy
- No buzzwords: no "leverage", "synergy", "elevate your brand", "take it to the next level"

Return valid JSON only:
{{
  "message": "the full message text",
  "channel": "linkedin | email",
  "subject": "subject line if email, else null",
  "personalisation_hook": "the specific detail you used to personalise this"
}}"""


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


# ── Obsidian Brain ────────────────────────────────────────────────────────────

BRAIN_PATH = Path.home() / "Documents" / "Brain" / "Leads"

def write_brain_note(profile: dict, qual: dict, draft: dict) -> Path:
    """Write a structured lead note into ~/Documents/Brain/Leads/."""
    BRAIN_PATH.mkdir(parents=True, exist_ok=True)

    company     = profile.get("company_name", "Unknown")
    score       = qual.get("score", 0)
    tier        = qual.get("tier", "warm")
    tier_emoji  = {"hot": "🔥", "warm": "🟡", "cold": "🔵"}.get(tier, "⚪")
    today       = datetime.now().strftime("%Y-%m-%d")
    safe_name   = re.sub(r'[\\/*?:"<>|]', "", company).strip()
    note_path   = BRAIN_PATH / f"{safe_name}.md"

    pain_points  = "\n".join(f"- {p}" for p in profile.get("potential_pain_points", []))
    signals      = "\n".join(f"- {s}" for s in profile.get("recent_signals", []))
    fit_reasons  = "\n".join(f"- {r}" for r in qual.get("fit_reasons", []))
    risks        = "\n".join(f"- {r}" for r in qual.get("risks", []))
    dm_titles    = ", ".join(profile.get("decision_maker_titles", []))

    retainer = qual.get("estimated_monthly_retainer", qual.get("estimated_deal_size", ""))
    note = f"""---
company: {company}
industry: {profile.get("industry", "")}
size: {profile.get("estimated_size", "")}
location: {profile.get("location", "")}
social_presence: {profile.get("social_media_presence", "")}
active_platforms: {", ".join(profile.get("active_platforms", []))}
score: {score}
tier: {tier}
estimated_retainer: {retainer}
outreach_channel: {draft.get("channel", "linkedin")}
date_added: {today}
verified: false
tags: [lead, {tier}, unverified, {profile.get("industry", "").lower().replace(" ", "-")}]
---

# {company}  {tier_emoji} {score}/100

## Overview
{profile.get("what_they_do", "")}

**Industry:** {profile.get("industry", "")}
**Size:** {profile.get("estimated_size", "")}
**Location:** {profile.get("location", "")}
**Social presence:** {profile.get("social_media_presence", "unknown")}
**Active platforms:** {", ".join(profile.get("active_platforms", [])) or "—"}
**Decision makers:** {dm_titles}

## Signals
{signals or "— none captured"}

## Pain Points
{pain_points or "— none captured"}

## Qualification

**Score:** {score}/100  |  **Tier:** {tier.upper()}  |  **Deal size:** {qual.get("estimated_deal_size", "")}
**Urgency:** {qual.get("urgency", "")}

### Why they fit
{fit_reasons or "— none captured"}

### Risks
{risks or "— none captured"}

### Recommended approach
{qual.get("recommended_approach", "")}

## Draft Outreach ({draft.get("channel", "linkedin").capitalize()})

**Personalisation hook:** {draft.get("personalisation_hook", "")}

{f"**Subject:** {draft.get('subject')}" if draft.get("subject") else ""}

```
{draft.get("message", "")}
```

---
*Generated by lead gen pipeline — {datetime.now().strftime("%Y-%m-%d %H:%M")}*
"""

    note_path.write_text(note, encoding="utf-8")
    return note_path


# ── Firebase CRM ──────────────────────────────────────────────────────────────

def write_crm_lead(profile: dict, qual: dict) -> bool:
    """POST a new lead to the Resolve Studios CRM API endpoint. Returns True on success."""
    if not RESOLVE_CRM_URL or not RESOLVE_CRM_SECRET:
        return False

    pain_points = profile.get("potential_pain_points", [])
    platforms   = ", ".join(profile.get("active_platforms", []))
    presence    = profile.get("social_media_presence", "unknown")

    payload = {
        "biz":       profile.get("company_name", ""),
        "type":      profile.get("industry", ""),
        "location":  profile.get("location", "") or "",
        "owner":     "",
        "createdBy": "brian",
        "online":    f"{presence.capitalize()} social presence · Platforms: {platforms or '—'}",
        "pain":      " · ".join(pain_points[:3]),
        "notes":     (
            f"Score: {qual.get('score', 0)}/100 · Tier: {qual.get('tier', '').upper()} · "
            f"Est. retainer: {qual.get('estimated_monthly_retainer', '—')}\n"
            f"{qual.get('recommended_approach', '')}"
        ),
    }

    r = requests.post(
        f"{RESOLVE_CRM_URL}/api/add-lead",
        headers={"Authorization": f"Bearer {RESOLVE_CRM_SECRET}"},
        json=payload,
    )
    return r.ok




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
                                    "value": f"**{score}/100** — {qual.get('estimated_monthly_retainer', qual.get('estimated_deal_size','—'))}", "inline": True},
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

    # ── Write to Obsidian Brain + Firebase CRM ────────────────────────────────
    note_path   = write_brain_note(profile, qual, draft)
    crm_success = write_crm_lead(profile, qual)

    post(BRIAN_TOK,
         f"🧠 **Brain + CRM updated**\n"
         f"> Obsidian: `Leads/{note_path.name}`\n"
         f"> CRM: {'✅ Added to leads board' if crm_success else '⚠️ CRM write failed'}\n"
         f"> Ask Sarah about it anytime.")
    print(f"\n✅ Done — Score: {score}/100  |  Tier: {tier}")
    print(f"   Brain note: {note_path}")


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
