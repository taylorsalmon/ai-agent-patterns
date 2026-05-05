# n8n Workflow Patterns

Importable n8n workflow JSON files — sanitised, no credentials, production-structured.

These workflows represent the automation layer that sits alongside the Python agent system. Where the Python agents handle reasoning and generation, n8n handles scheduling, routing, retries, and integration with business systems.

## How to Import

1. Open your n8n instance
2. Go to **Workflows → Import from file**
3. Select the `.json` file
4. Update credential references to match your environment
5. Activate

## Workflows

| File | Pattern | Description |
|------|---------|-------------|
| [`inbound-triage-pipeline.json`](./inbound-triage-pipeline.json) | Webhook → Claude → Route | Classify inbound form submissions, create CRM tasks, alert on edge cases |
| [`document-extraction-pipeline.json`](./document-extraction-pipeline.json) | Schedule → Fetch → Claude → CRM | Hourly batch extraction — pull unprocessed docs, extract fields, write to CRM |
| [`agent-monitor-alert.json`](./agent-monitor-alert.json) | Schedule → Check → Alert | Every 15 min — check error rate, P95 latency, confidence drift across all agents |

## Credential Placeholders

| Placeholder | Replace with |
|------------|-------------|
| `YOUR_CLAUDE_API_KEY` | Anthropic API key |
| `YOUR_SLACK_WEBHOOK` | Slack incoming webhook URL |
| `YOUR_CRM_API_KEY` | Your CRM's API key |
| `YOUR_WEBHOOK_SECRET` | HMAC secret for inbound webhook validation |

## Design Principles

**Error handling on every node.** Error outputs are wired to a Slack alert on every HTTP Request node. Silent failures are the hardest production bugs to catch — treat them as first-class concerns.

**Idempotency.** Workflows check for existing records before creating new ones. Running the same workflow twice produces the same state.

**Structured logging.** Every workflow writes a log entry before completing — timestamp, workflow ID, input hash, output summary, status. Queryable audit trail from day one.

**Separation of concerns.** n8n handles scheduling, routing, and integration. Claude handles reasoning. Keeping these layers separate means each can be updated, tested, and monitored independently.
