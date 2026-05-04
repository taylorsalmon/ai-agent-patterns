# AI Agent Patterns

A reference library of production-ready patterns for building AI agents, MCP integrations, and multi-agent workflows. Built from real deployment experience across Anthropic Claude, n8n, and REST API pipelines.

---

## What's In Here

| Directory | Contents |
|-----------|----------|
| [`prompt-templates/`](./prompt-templates/) | Reusable system prompts for common agent roles |
| [`workflows/`](./workflows/) | n8n workflow JSON exports — importable, production-structured |
| [`agents/`](./agents/) | Multi-agent orchestration patterns and MCP integration examples |
| [`docs/`](./docs/) | Architecture notes, integration guides, runbooks |

---

## Philosophy

Three rules I apply to every build:

1. **Reliability over cleverness.** An agent that works predictably in production beats one that's impressive in a demo. I scope carefully, handle edge cases explicitly, and monitor everything that ships.

2. **Prompt engineering is engineering.** System prompts have versions, changelogs, and tests. A prompt that isn't evaluated against real inputs isn't ready to ship.

3. **Document as you build.** Every integration gets a README. Every workflow gets a runbook. If another engineer can't pick it up cold, it's not done.

---

## Architecture Overview

### Agent-to-Agent Patterns

```
┌─────────────────────────────────────────────────────┐
│                  Orchestrator Agent                  │
│  - Decomposes task into subtasks                    │
│  - Routes to specialist agents                      │
│  - Aggregates and validates outputs                 │
└──────────┬────────────────────────┬─────────────────┘
           │                        │
    ┌──────▼──────┐          ┌──────▼──────┐
    │  Specialist  │          │  Specialist  │
    │   Agent A    │          │   Agent B    │
    │  (research)  │          │   (write)    │
    └──────┬──────┘          └──────┬──────┘
           │                        │
    ┌──────▼──────────────────────▼──────┐
    │            Tool Layer               │
    │  web_search │ read_file │ send_email │
    └────────────────────────────────────┘
```

The orchestrator maintains a shared context object passed between agents. Each specialist receives only the context it needs (minimal context principle — keeps token costs down and reduces hallucination risk).

### MCP Integration Pattern

```
Claude Agent
    │
    ├── MCP Server: CRM (read/write customer records)
    ├── MCP Server: Calendar (schedule follow-ups)
    ├── MCP Server: Slack (post summaries to channels)
    └── MCP Server: n8n (trigger downstream automations)
```

MCP servers are the clean interface layer between Claude and business systems. I prefer MCP over raw API calls inside prompts because:
- Tools are declared, versioned, and testable independently
- Agents can discover capabilities at runtime
- Errors surface at the tool layer, not mid-generation

### Webhook → Agent → Action Pipeline

```
Trigger (webhook/schedule/form)
    │
    ▼
n8n Workflow
    │  normalise payload
    │  enrich from CRM
    │
    ▼
Claude API call
    │  system prompt: role + constraints
    │  user message: enriched context
    │  tools: actions the agent can take
    │
    ▼
Structured JSON output
    │
    ▼
n8n: route by intent
    ├── intent: "follow_up" → create CRM task
    ├── intent: "urgent"    → Slack alert + email
    └── intent: "info_only" → log and close
```

---

## Key Design Decisions

### Why structured outputs over free text

Every agent I build returns structured JSON. It makes downstream routing deterministic, errors obvious, and evaluation automatable. I validate against a schema before passing output to the next step.

```json
{
  "intent": "follow_up",
  "confidence": 0.92,
  "summary": "Customer asked about delivery timeline for order #4821",
  "recommended_action": "create_crm_task",
  "urgency": "normal",
  "entities": {
    "order_id": "4821",
    "customer_id": "cust_9923"
  }
}
```

### Multi-step chain vs single prompt

I reach for multi-step chains when:
- The task has distinct reasoning phases (gather → analyse → decide → act)
- Context would exceed ~20k tokens in a single call
- I need to validate intermediate outputs before proceeding

Single prompt is almost always better for simple classification, extraction, and transformation tasks.

### Prompt versioning

Every system prompt lives in version control. Changes go through the same review process as code. I run eval sets against new versions before promoting them to production.

---

## Integrations I've Built Against

- **Anthropic Claude** — primary LLM, including tool use, multi-turn, and streaming
- **n8n** — workflow automation backbone for most pipelines
- **Zapier / Make** — for integrations where n8n isn't available in the client's stack
- **REST APIs** — CRM systems, ERPs, Shopify, email platforms
- **Webhooks** — inbound triggers from Shopify, Stripe, Typeform, and custom sources
- **Slack & email** — standard output channels for agent notifications

---

## Evaluating Agent Quality

Before anything goes to production I check:

| Check | How |
|-------|-----|
| **Accuracy** | Run against 20+ real examples, measure correct intent classification |
| **Reliability** | Inject malformed inputs — does it fail gracefully? |
| **Latency** | P95 response time acceptable for the use case? |
| **Cost** | Token usage per call × expected volume = monthly cost estimate |
| **Edge cases** | Empty inputs, ambiguous inputs, adversarial inputs |

---

## Running the Examples

Each subdirectory has its own README with setup instructions. Most examples require:

```bash
# Python examples
pip install anthropic python-dotenv

# Set your API key
export ANTHROPIC_API_KEY=your_key_here
```

n8n workflows are importable JSON — open n8n, go to **Workflows → Import from file**.

---

## Contact

Built by Taylor Salmon — AI engineer focused on practical, production-grade agent systems.

- [LinkedIn](https://linkedin.com/in/taylorsalmon)
- [GitHub](https://github.com/taylorsalmon)
