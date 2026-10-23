# Distributed Workflow Engine

Learning-oriented workflow API with validated multi-step definitions, retries with exponential backoff, dead-letter records, and per-run traces. Optional Kafka publishing and LLM summary action.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

OpenAPI docs: http://127.0.0.1:8000/docs

## API

POST a workflow definition containing `name` and `steps` to `/v1/workflows`. Then POST an input object to `/v1/workflows/{workflow_id}/runs`. Supported actions: `echo`, `delay`, and `llm_summary`. View run status at `/v1/runs/{run_id}`, attempt traces at `/v1/runs/{run_id}/trace`, and dead letters at `/v1/dead-letters`.

## Optional integrations

Set `KAFKA_BOOTSTRAP_SERVERS` and install the `kafka` extra to publish run events. Set `OPENAI_API_KEY` to enable the optional summary action. Its output is length-checked plain text; generated content cannot execute tools or code.

## Limitations

Runs currently execute synchronously and SQLite is the default. This is a learning starter, not production distributed processing. Production needs durable consumers/outbox, migrations, authentication, tenant isolation, and operational tracing.
