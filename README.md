# AI Agent Patterns

A reference library of production-ready patterns for building AI agents, multi-agent workflows, and business system integrations — built on Anthropic Claude.

This repo serves two purposes: a reusable pattern library for common agent architectures, and a showcase of a production deployment built on those patterns — a fully operational multi-agent lead generation system for a social media agency.

---

## Production Case Study — Resolve Studios Lead Gen System

The patterns in this repo aren't hypothetical. They're the foundation of a live multi-agent system deployed for **Resolve Studios**, a social media marketing agency.

The system runs two persistent AI agents — Brian and Sarah — that collaborate in Discord to identify, research, qualify, and convert leads, with all data written automatically to an Obsidian knowledge base.

### What it does

```
You (in Discord)
    │
    ▼
@Brian find me a lead in the dental space in Melbourne
    │
    ├── Brian: Intent classifier (claude-haiku) detects find_lead
    ├── Brian: Picks best-fit target company
    │
    ▼
Lead Gen Pipeline (3 specialist agents)
    │
    ├── Research Agent    → company profile, social presence, pain points
    ├── Qualification Agent → lead score (0-100), tier, retainer estimate
    └── Sarah (Outreach)  → personalised first-touch message, channel recommendation
    │
    ├── Discord: live status updates as each agent completes
    ├── Brian: posts final lead report embed
    └── Brain vault: structured Obsidian note written automatically
    │
    ▼
@Sarah have you added them to the brain?
    Sarah: searches vault, replies with [[wiki links]] to relevant notes

@Sarah Dental On Clarendon just signed — move them to client at $10k/month
    Sarah: finds note (typo-tolerant), moves Leads/ → Clients/, updates frontmatter
```

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Discord Channel                          │
│                                                                 │
│  Brian (Pipeline Manager)        Sarah (Account Manager)        │
│  ─────────────────────────       ────────────────────────────   │
│  • Intent classification         • Full Brain vault access      │
│  • Lead target selection         • Fuzzy note search            │
│  • Pipeline orchestration        • Lead → Client conversion     │
│  • Read-only: Leads folder       • Obsidian [[wiki links]]      │
│  • Reads Sarah's messages        • Conversation memory          │
└──────────────┬──────────────────────────┬───────────────────────┘
               │                          │
    ┌──────────▼──────────┐    ┌──────────▼──────────┐
    │   Lead Gen Pipeline  │    │   Brain Vault         │
    │                      │    │   ~/Documents/Brain   │
    │  Research Agent      │    │                       │
    │       ↓              │    │   Leads/              │
    │  Qualification Agent │───▶│   Clients/            │
    │       ↓              │    │   [other vault areas] │
    │  Outreach Agent      │    │                       │
    └──────────────────────┘    └───────────────────────┘
```

### Agent responsibilities

| Agent | Owns | Access |
|-------|------|--------|
| Brian | Pipeline orchestration, intent routing, lead selection | Leads folder (read-only), Sarah's Discord messages |
| Sarah | Outreach drafting, Brain vault, client conversion | Full Brain vault (read + write) |
| Research | Company profiling, social presence, pain points | Claude knowledge |
| Qualification | Lead scoring, tier classification, retainer estimation | Research output |
| Outreach | Personalised first-touch copy | Research + qualification output |

### Key engineering decisions

**Claude-haiku for intent classification** — cheap and fast (~$0.0003/call) for routing decisions. Claude-opus handles the reasoning-heavy steps. Right tool for each job.

**Fuzzy matching with SequenceMatcher** — agents find notes despite typos ("clareden" resolves to "Dental On Clarendon"). Production systems get real input; they need to handle it.

**Conversation memory via channel history** — Sarah reads recent messages before classifying intent, so follow-up replies ("Dental On Clarendon") are understood in context without requiring the user to repeat themselves.

**Separate access levels** — Brian has read-only Leads access and reads Sarah's messages for context. Sarah owns the full vault. Role separation isn't just good architecture — it makes the agent-to-agent dependency visible and auditable.

**Structured outputs everywhere** — every agent returns typed JSON validated before passing to the next step. Unstructured responses are stripped of code fences and parsed with fallbacks.

---

## Pattern Library

The patterns below are the building blocks this system is assembled from. Each is reusable, standalone, and documented for production use.

### Directory structure

```
ai-agent-patterns/
├── agents/
│   ├── lead_gen_pipeline.py      ← production multi-agent pipeline (Resolve Studios)
│   ├── bot_listener.py           ← persistent Discord bot (Brian + Sarah)
│   ├── multi_agent_pipeline.py   ← orchestrator + specialist pattern (generic)
│   ├── structured_output.py      ← JSON schema enforcement with retry
│   ├── mcp_integration.py        ← Claude tool use loop
│   └── eval_harness.py           ← prompt accuracy evaluation
├── prompt-templates/
│   ├── triage-agent.md           ← classify + route inbound messages
│   ├── extraction-agent.md       ← structured data from unstructured text
│   ├── summarisation-agent.md    ← audience-aware document summaries
│   └── orchestrator-agent.md     ← plan + delegate to specialist agents
├── workflows/
│   ├── inbound-triage-pipeline.json      ← n8n: webhook → Claude → CRM
│   ├── document-extraction-pipeline.json ← n8n: scheduled batch extraction
│   └── agent-monitor-alert.json          ← n8n: error rate + latency monitor
├── docs/
│   ├── integration-runbook.md    ← deployment, monitoring, troubleshooting
│   └── prompt-engineering-guide.md ← versioning, evals, failure modes
└── evals/
    └── triage/                   ← labelled eval cases
```

---

## Quickstart — Run the Lead Gen Pipeline

```bash
# 1. Clone and set up environment
git clone https://github.com/taylorsalmon/ai-agent-patterns.git
cd ai-agent-patterns
python3 -m venv venv && source venv/bin/activate
pip install anthropic requests python-dotenv discord.py

# 2. Configure credentials
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY, BRIAN_TOKEN, SARAH_TOKEN, DISCORD_CHANNEL_ID

# 3. Run a pipeline (one-shot)
python3 agents/lead_gen_pipeline.py "Company Name" "https://website.com"

# 4. Start the persistent bot listener (Brian + Sarah)
python3 agents/bot_listener.py
```

Once the listener is running, in Discord:
```
@Brian find me a lead in the fitness space in Richmond
@Sarah have you added [Company] to the brain?
@Sarah [Company] just signed — move them to client at $3,500/month
```

---

## Core Patterns

### 1. Orchestrator → Specialist delegation

Break complex tasks into subtasks, route to purpose-built agents, collect structured outputs, pass context forward. Each agent receives only the context it needs.

```python
# Orchestrator produces a plan
plan = orchestrator.plan(task)

# Execute steps in order, passing outputs forward
for step in plan.steps:
    context[step.id] = specialists[step.agent].run(
        step.description,
        inputs=resolve(step.inputs, context)
    )
```

See [`agents/multi_agent_pipeline.py`](./agents/multi_agent_pipeline.py)

### 2. Claude-powered intent classification

Replace brittle keyword matching with a fast haiku call that understands natural language. Cheap enough to run on every message (~$0.0003), fast enough to feel instant.

```python
def classify_intent(message: str) -> dict:
    r = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        system="Classify intent. Return JSON: {intent, brief}",
        messages=[{"role": "user", "content": message}]
    )
    return parse_json(r.content[0].text)
```

### 3. Structured output with fallback parsing

Every agent returns typed JSON. Strip code fences, fall back to brace extraction, validate before passing downstream.

```python
def parse_json(text: str) -> dict:
    if "```" in text:
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    if not text.strip().startswith("{"):
        s, e = text.find("{"), text.rfind("}") + 1
        text = text[s:e]
    return json.loads(text.strip())
```

See [`agents/structured_output.py`](./agents/structured_output.py)

### 4. Prompt versioning and evaluation

System prompts are versioned in git. New versions are evaluated against a labelled dataset before promotion. Target: ≥95% field-level accuracy.

```bash
python3 agents/eval_harness.py --cases evals/triage/ --verbose
```

See [`docs/prompt-engineering-guide.md`](./docs/prompt-engineering-guide.md)

### 5. n8n pipeline patterns

Three importable workflow templates covering the most common automation patterns: inbound triage, scheduled batch processing, and agent health monitoring.

See [`workflows/`](./workflows/) — import directly into n8n.

---

## Philosophy

**Reliability over cleverness.** An agent that works predictably in production beats one that's impressive in a demo. Scope carefully, handle edge cases explicitly, monitor everything.

**Prompt engineering is engineering.** System prompts have versions, changelogs, and eval sets. A prompt that hasn't been tested against real inputs isn't ready to ship.

**Right model for the job.** Intent classification uses claude-haiku. Complex reasoning uses claude-opus. Matching model capability to task keeps costs predictable and latency low.

**Document as you build.** Every integration gets a README. Every workflow gets a runbook. If another engineer can't pick it up cold, it's not done.

---

## Integrations

| System | Usage |
|--------|-------|
| Anthropic Claude (Opus + Haiku) | LLM backbone — reasoning, classification, generation |
| Discord (Bot API) | Agent communication layer — status updates, reports, interaction |
| Obsidian | Knowledge base — structured lead and client notes with frontmatter |
| n8n | Workflow automation — webhook pipelines, batch processing, monitoring |
| REST APIs | CRM, email platforms, webhooks |

---

## Production Deployment

The bot listener (`bot_listener.py`) is a persistent process. For production:

```
Local dev    → python3 agents/bot_listener.py (terminal stays open)
Production   → AWS ECS (Fargate) or Railway — containerised, auto-restarts on crash
Credentials  → AWS Secrets Manager or Railway environment variables
Logging      → CloudWatch or Datadog — monitor error rate, latency, intent classification accuracy
```

---

## Contact

Built by Taylor Salmon — AI engineer.

- [LinkedIn](https://linkedin.com/in/taylorsalmon)
- [GitHub](https://github.com/taylorsalmon/taylorsalmon)
