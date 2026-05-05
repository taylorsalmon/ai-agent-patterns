# Agents

Python agent implementations — from a live production deployment to reusable reference patterns.

## Production System

| File | Description |
|------|-------------|
| [`lead_gen_pipeline.py`](./lead_gen_pipeline.py) | Full lead gen pipeline — Research → Qualification → Sarah (Outreach) → Discord report → Obsidian note |
| [`bot_listener.py`](./bot_listener.py) | Persistent Discord listener — Brian (pipeline) and Sarah (Brain vault) respond to mentions in natural language |

### Running the production system

```bash
# One-shot pipeline run
python3 agents/lead_gen_pipeline.py "Grill'd" "https://grilld.com.au"

# Persistent bot listener (keep terminal open)
python3 agents/bot_listener.py
```

Requires `.env` with `ANTHROPIC_API_KEY`, `BRIAN_TOKEN`, `SARAH_TOKEN`, `DISCORD_CHANNEL_ID`.

---

## Reference Patterns

| File | Pattern | What it demonstrates |
|------|---------|----------------------|
| [`multi_agent_pipeline.py`](./multi_agent_pipeline.py) | Orchestrator + specialists | Task decomposition, context passing, sequential execution |
| [`structured_output.py`](./structured_output.py) | JSON schema enforcement | Validation, retry with error feedback, type checking |
| [`mcp_integration.py`](./mcp_integration.py) | Claude tool use loop | Tool declaration, execution loop, result injection |
| [`eval_harness.py`](./eval_harness.py) | Prompt evaluation | Field-level accuracy, calibration, regression testing |

### Setup

```bash
pip install anthropic requests python-dotenv discord.py
export ANTHROPIC_API_KEY=your_key_here

python3 agents/multi_agent_pipeline.py
python3 agents/structured_output.py
python3 agents/mcp_integration.py
python3 agents/eval_harness.py --cases ../evals/triage/ --verbose
```
