# Prompt Templates

Reusable, production-tested system prompts. Each template is parameterised with `{{PLACEHOLDER}}` variables — fill these at runtime from your business context.

All templates follow the same structure:
1. **Role** — who the agent is and what it's optimising for
2. **Context** — what it knows about the environment
3. **Constraints** — what it must not do
4. **Output format** — explicit JSON schema with examples

---

## Templates

| File | Use Case |
|------|----------|
| [`triage-agent.md`](./triage-agent.md) | Classify and route inbound enquiries |
| [`extraction-agent.md`](./extraction-agent.md) | Extract structured data from unstructured text |
| [`summarisation-agent.md`](./summarisation-agent.md) | Summarise long documents with audience awareness |
| [`orchestrator-agent.md`](./orchestrator-agent.md) | Plan and delegate tasks to specialist agents |
