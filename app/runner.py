import os
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import DeadLetter, StepEvent, Workflow, WorkflowRun
from app.schemas import StepDefinition


def execute_step(step: StepDefinition, run_input: dict, previous: dict) -> dict:
    parameters = dict(step.input)
    if step.type == "echo":
        return {"result": parameters.get("text", ""), "input_keys": sorted(run_input.keys())}
    if step.type == "delay":
        seconds = float(parameters.get("seconds", 0))
        if not 0 <= seconds <= 2:
            raise ValueError("delay seconds must be between 0 and 2")
        time.sleep(seconds)
        return {"slept_seconds": seconds}
    if step.type == "llm_summary":
        text = parameters.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("llm_summary requires non-empty text")
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return {"summary": text.strip()[:500], "provider": "fallback"}
        from openai import OpenAI
        response = OpenAI(api_key=key).chat.completions.create(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), messages=[{"role": "system", "content": "Summarize in one concise sentence; return plain text only."}, {"role": "user", "content": text[:10000]}], max_tokens=120)
        summary = response.choices[0].message.content
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 1000:
            raise ValueError("LLM output failed validation")
        return {"summary": summary.strip(), "provider": "llm"}
    raise ValueError("Unsupported action type")


def execute_run(db: Session, workflow: Workflow, run: WorkflowRun) -> WorkflowRun:
    run.status = "running"
    db.commit()
    outputs: dict[str, dict] = {}
    for raw in workflow.definition["steps"]:
        step = StepDefinition.model_validate(raw)
        succeeded = False
        last_error = ""
        for attempt in range(step.retries + 1):
            event = StepEvent(run_id=run.id, step_id=step.id, attempt=attempt, status="running", input=step.input)
            db.add(event)
            db.commit()
            try:
                output = execute_step(step, run.input, outputs)
                event.status, event.output, event.finished_at = "succeeded", output, datetime.now(UTC)
                db.commit()
                outputs[step.id] = output
                succeeded = True
                break
            except (ValueError, RuntimeError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"[:1000]
                event.status, event.error, event.finished_at = "failed", last_error, datetime.now(UTC)
                db.commit()
                if attempt < step.retries:
                    time.sleep(min(0.05 * (2**attempt), 1.0))
        if not succeeded:
            db.add(DeadLetter(run_id=run.id, step_id=step.id, payload={"input": step.input, "attempts": step.retries + 1}, error=last_error))
            run.status, run.output, run.finished_at = "dead_lettered", outputs, datetime.now(UTC)
            db.commit()
            return run
    run.status, run.output, run.finished_at = "succeeded", outputs, datetime.now(UTC)
    db.commit()
    return run
