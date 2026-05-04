# Integration Runbook — Claude + n8n

Operational guide for the inbound triage pipeline. Written to be followed cold by someone who didn't build it.

---

## Architecture Summary

```
Inbound form (web) → n8n webhook → Claude API → CRM task + Slack alert
```

Three moving parts:
1. **n8n** — receives webhooks, orchestrates the flow, handles errors
2. **Claude API** — classifies each enquiry and returns structured JSON
3. **CRM** — receives the created task; Slack receives alerts for edge cases

---

## Credential Locations

| Credential | Where to find it | Used by |
|-----------|-----------------|---------|
| `ANTHROPIC_API_KEY` | 1Password → AI Integrations → Anthropic | n8n HTTP Request node (Claude call) |
| `CRM_API_KEY` | 1Password → AI Integrations → CRM | n8n HTTP Request nodes (CRM read/write) |
| `SLACK_WEBHOOK_URL` | Slack App settings → Incoming Webhooks | n8n HTTP Request nodes (Slack alerts) |
| `WEBHOOK_HMAC_SECRET` | 1Password → AI Integrations → Webhooks | n8n webhook validation code node |

**Rotate credentials** by updating the relevant n8n credential entry — the workflow references the credential name, not the value directly.

---

## Deployment Steps

1. Import the workflow JSON from `workflows/inbound-triage-pipeline.json`
2. Update each credential reference to match your n8n credential store
3. Set the webhook URL in your form platform to the n8n webhook endpoint
4. Run a test submission and verify:
   - CRM task created ✓
   - Slack alert fires for `requires_human_review: true` cases ✓
   - Audit log entry written ✓
5. Activate the workflow

---

## Monitoring

**What to watch:**

| Signal | Where | Threshold |
|--------|-------|-----------|
| Error rate | n8n execution history | < 2% |
| Claude API latency | n8n execution time | < 5s P95 |
| Low-confidence rate | Audit log | < 15% |
| CRM write failures | n8n error log | 0 |

**Agent monitor workflow** (`workflows/agent-monitor-alert.json`) checks these every 15 minutes and alerts Slack automatically.

---

## Common Issues

### Claude returns non-JSON

**Symptom:** `parse-claude-response` node fails with a JSON parse error.

**Cause:** Claude occasionally wraps JSON in markdown code fences, or prefaces it with explanation text.

**Fix:** The parse node includes a fallback that catches this and routes to human review. If it's happening frequently (>2% of calls), check whether the system prompt has drifted — compare against the versioned template in `prompt-templates/triage-agent.md`.

---

### CRM write fails with 409 Conflict

**Symptom:** `create-crm-task` node returns HTTP 409.

**Cause:** Duplicate submission — the same enquiry was processed twice (e.g., user clicked submit twice, or the webhook fired twice due to a retry).

**Fix:** The workflow doesn't currently deduplicate on submission ID. Add an idempotency check: before creating the CRM task, query for an existing task with the same `source_document_id`. If found, skip creation.

---

### Slack alerts not firing

**Symptom:** Pipeline runs but no Slack message received.

**Cause:** Usually an expired or revoked webhook URL.

**Fix:**
1. Test the webhook URL directly with a `curl -X POST` call
2. If it returns 404, regenerate the webhook in the Slack App settings and update the n8n credential

---

### High low-confidence rate

**Symptom:** >20% of classifications have `confidence < 0.8` — more than expected going to human review.

**Cause:** Either the distribution of inbound enquiries has shifted (new enquiry types the prompt wasn't designed for), or the system prompt needs updating.

**Action:**
1. Pull the last 50 low-confidence cases from the audit log
2. Identify the most common category they're falling into
3. Add examples of that category to the system prompt
4. Run the eval harness against the full eval set (`agents/eval_harness.py`) before promoting

---

## Prompt Version History

Treat this table as a changelog for the triage agent system prompt.

| Version | Date | Change | Eval Accuracy |
|---------|------|--------|--------------|
| 1.0 | 2025-07-01 | Initial prompt | 91.2% |
| 1.1 | 2025-07-28 | Added `spam` category; tightened urgency definitions | 94.8% |
| 1.2 | 2025-08-10 | Added explicit examples for billing vs. refund distinction | 96.3% |

---

## Rollback

1. In n8n, open the workflow
2. Click **Versions** (top right)
3. Select the previous version and activate it
4. Verify the prompt version in the system prompt matches the rollback target above
