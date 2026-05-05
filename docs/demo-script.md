# Live Demo Script — AI Engineer Interview

A step-by-step walkthrough for the live demo portion. Each section includes the exact Discord message to send, what to say while the agents respond, and what to point out when they reply.

Pre-flight: start `python3 agents/bot_listener.py` before the call. Confirm both Brian and Sarah appear online in the Discord server sidebar.

---

## Section 1 — Architecture walkthrough (talk track, no typing)

**Say:** "The repo has two layers. The pattern library — generic, reusable, drop these into any project. And a production case study — a fully deployed system built for a social media agency called Resolve Studios."

**Show:** the README architecture diagram.

**Say:** "Two persistent AI agents running as Discord bots. Brian is the pipeline manager — he classifies intent, selects lead targets, and orchestrates three specialist agents. Sarah is the account manager — she owns the knowledge base, handles client conversions, and responds to natural language questions about the vault. They have different access levels and different voices, and they can see each other's messages."

---

## Section 2 — Trigger the full pipeline

**Type in Discord:**
```
@Brian find me a lead in the dental space in Melbourne
```

**While Brian responds and the pipeline runs, say:**
"Brian uses claude-haiku for intent classification — cheap, about $0.0003 a call, fast enough to feel instant. The actual haiku call is about three lines of code. Then it picks a target company and hands off to three specialist agents in sequence."

**Point out as it happens:**
- Brian's "searching" message confirms intent was classified correctly
- Each "→" handoff message shows data flowing between agents
- The live status updates prove this is async — real work happening in real time

**When the final report lands, say:**
"Research agent profiled the company — social presence, pain points, platform gaps. Qualification agent scored the lead from 0 to 100 and estimated a monthly retainer. Sarah drafted the first-touch outreach message. All three agents receive only the context they need — research output goes to qualification, both go to outreach."

**Show the Obsidian note** (open Brain/Leads/ in Obsidian):
"And it's written a structured note automatically — YAML frontmatter, lead score, retainer estimate, outreach copy. Everything queryable."

---

## Section 3 — Ask Sarah about the vault

**Type in Discord:**
```
@Sarah have you added them to the brain?
```

**When Sarah replies with wiki links, say:**
"Sarah searches the vault and replies with Obsidian wiki links. Click any of these in Obsidian and it navigates directly to the note."

---

## Section 4 — Demonstrate fuzzy search and conversation memory

**Type in Discord:**
```
@Sarah update the dental lead — they've agreed to a discovery call
```

**Say:** "Notice I didn't give the full company name. Sarah reads the last six messages in the channel before classifying intent, so she has context — she knows which dental lead we were just talking about. And the fuzzy matcher handles typos, partial names, anything that's close enough."

---

## Section 5 — Convert a lead to client

**Type in Discord:**
```
@Sarah [Company Name] just signed — move them to client at $8,500/month
```
*(Use the company name from the pipeline run in Section 2)*

**When Sarah confirms, say:**
"Sarah moves the note from Leads/ to Clients/ in the vault, updates the frontmatter — status, date converted, monthly retainer — and appends a conversion log. Brian can't do this. Brian has read-only access to the Leads folder. Sarah owns the vault. Role separation isn't just good architecture — it makes the dependency between agents visible and auditable."

---

## Section 6 — Code walkthrough (if they ask for it)

**Open `agents/bot_listener.py` and show:**

1. **The intent classifier** (~line 90) — three lines calling claude-haiku, returns JSON
2. **Conversation memory** (~line 110) — `get_sarah_messages()` fetches recent history, passed as context before classification
3. **Fuzzy match** (~line 50) — word-level SequenceMatcher, 0.75 ratio threshold
4. **`convert_to_client()`** (~line 140) — file move + frontmatter update, whole function is ~40 lines
5. **`asyncio.gather()`** at the bottom — two bot clients running concurrently in one process

**Open `agents/lead_gen_pipeline.py` and show:**

1. **Three specialist agents** — each is a `claude.messages.create()` call with a focused system prompt
2. **`parse_json()`** — strips code fences, falls back to brace extraction, validates before passing downstream
3. **`write_brain_note()`** — writes YAML frontmatter + markdown, creates folder structure if missing

---

## Section 7 — Pattern library (if time allows)

**Show in the README:**
"The patterns the production system is built from are all standalone and generic. Structured output with fallback parsing — every agent returns typed JSON. Prompt versioning — system prompts live in git, new versions are evaluated before promotion. The eval harness runs against labelled cases and targets ≥95% field accuracy."

```bash
python3 agents/eval_harness.py --cases evals/triage/ --verbose
```

---

## Talking points if they go off-script

**"Why haiku for intent classification?"**
Cheap (~$0.0003/call) and fast enough to be invisible. Opus handles the reasoning-heavy steps — research, qualification, outreach. Matching model capability to task keeps costs predictable.

**"How does this scale to production?"**
The bot listener is a persistent process — Docker container on Railway or AWS ECS Fargate, auto-restarts on crash, credentials in environment variables. Logging goes to CloudWatch or Datadog. The architecture diagram in the README shows the full deployment path.

**"What would you add next?"**
CRM sync — write leads to HubSpot or Attio automatically. Scheduled pipeline runs — Brian triggers a prospecting run every Monday morning via n8n. Email integration — Sarah sends the outreach message directly from Gmail on confirmation.

**"Is the data real?"**
The company profiles are Claude's knowledge, flagged as unverified in the notes and the Discord messages. In production you'd add a web search tool call in the research agent to ground the output in live data.

---

## Pre-demo checklist

- [ ] `python3 agents/bot_listener.py` running, both bots show online
- [ ] Obsidian open to Brain/Leads/ — ready to show the note after pipeline runs
- [ ] README open in browser — architecture diagram visible
- [ ] `.env` has valid ANTHROPIC_API_KEY, BRIAN_TOKEN, SARAH_TOKEN, DISCORD_CHANNEL_ID
- [ ] Discord server open in browser or desktop app — both bots visible
- [ ] Backup screenshots of a completed pipeline run saved (in case of API issues on the day)
