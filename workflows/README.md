# n8n Workflow Examples

Importable n8n workflow JSON files. These are sanitised — no credentials, no proprietary business logic. They demonstrate structure, patterns, and integration approaches.

## How to Import

1. Open your n8n instance
2. Go to **Workflows → Import from file**
3. Select the `.json` file
4. Update credential references to match your environment
5. Activate

## Workflows

| File | Pattern | Description |
|------|---------|-------------|
| [`inbound-triage-pipeline.json`](./inbound-triage-pipeline.json) | Webhook → Claude → Route | Classify inbound form submissions and route by intent |
| [`document-extraction-pipeline.json`](./document-extraction-pipeline.json) | Schedule → Fetch → Claude → CRM | Poll a source, extract structured data, write to CRM |
| [`agent-monitor-alert.json`](./agent-monitor-alert.json) | Schedule → Check → Alert | Monitor agent error rates and alert via Slack |

## Credential Placeholders

All workflows use placeholder credential names:

- `YOUR_CLAUDE_API_KEY` → Anthropic API key
- `YOUR_SLACK_WEBHOOK` → Slack incoming webhook URL  
- `YOUR_CRM_API_KEY` → Your CRM's API key
- `YOUR_WEBHOOK_SECRET` → HMAC secret for inbound webhook validation

## Design Principles Applied

**Error handling on every node.** Each HTTP Request node has error output wired to a Slack alert. Silent failures in automation pipelines are the hardest bugs to catch in production.

**Idempotency.** Where workflows process records, they check for existing records before creating new ones. Running the same workflow twice produces the same state.

**Structured logging.** Each workflow writes a log entry (timestamp, workflow ID, input hash, output, status) to a logging endpoint before completing.
