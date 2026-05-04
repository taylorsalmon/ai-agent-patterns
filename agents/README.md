# Agent Patterns

Python examples for production agent patterns using the Anthropic SDK. Each example is self-contained and runnable.

## Setup

```bash
pip install anthropic python-dotenv
export ANTHROPIC_API_KEY=your_key_here
```

## Examples

| File | Pattern |
|------|---------|
| [`mcp_integration.py`](./mcp_integration.py) | Connect Claude to external tools via MCP |
| [`multi_agent_pipeline.py`](./multi_agent_pipeline.py) | Orchestrator + specialist agent pattern |
| [`structured_output.py`](./structured_output.py) | Enforce JSON schema on every response |
| [`eval_harness.py`](./eval_harness.py) | Run a prompt against a labelled eval set |
