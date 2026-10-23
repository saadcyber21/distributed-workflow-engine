from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker import publish_run_event
from app.database import Base, engine, get_db
from app.models import DeadLetter, StepEvent, Workflow, WorkflowRun
from app.runner import execute_run
from app.schemas import RunCreate, RunOut, WorkflowDefinition, WorkflowOut

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Distributed Workflow Engine", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    details = [{"type": e.get("type"), "loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Request validation failed", "details": jsonable_encoder(details)}})


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "request_error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": {**detail, "details": detail.get("details", [])}})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/workflows", response_model=WorkflowOut, status_code=201)
def create_workflow(payload: WorkflowDefinition, db: Session = Depends(get_db)):
    workflow = Workflow(id=str(uuid4()), name=payload.name.strip(), definition=payload.model_dump(mode="json"))
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return {"id": workflow.id, "name": workflow.name, "steps": workflow.definition["steps"], "created_at": workflow.created_at}


@app.post("/v1/workflows/{workflow_id}/runs", response_model=RunOut, status_code=201)
def start_run(workflow_id: str, payload: RunCreate, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail={"code": "workflow_not_found", "message": "Workflow not found"})
    run = WorkflowRun(id=str(uuid4()), workflow_id=workflow.id, status="queued", input=payload.input, output=None, trace_id=str(uuid4()))
    db.add(run)
    db.commit()
    publish_run_event({"run_id": run.id, "workflow_id": workflow.id, "trace_id": run.trace_id})
    return execute_run(db, workflow, run)


@app.get("/v1/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "run_not_found", "message": "Run not found"})
    return run


@app.get("/v1/runs/{run_id}/trace")
def get_trace(run_id: str, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "run_not_found", "message": "Run not found"})
    steps = list(db.scalars(select(StepEvent).where(StepEvent.run_id == run_id).order_by(StepEvent.id)))
    return {"run_id": run.id, "trace_id": run.trace_id, "status": run.status, "steps": [{"step_id": e.step_id, "attempt": e.attempt, "status": e.status, "error": e.error, "started_at": e.started_at, "finished_at": e.finished_at} for e in steps]}


@app.get("/v1/dead-letters")
def list_dead_letters(limit: int = 100, db: Session = Depends(get_db)):
    letters = list(db.scalars(select(DeadLetter).order_by(DeadLetter.created_at.desc()).limit(max(1, min(limit, 500)))))
    return [{"id": row.id, "run_id": row.run_id, "step_id": row.step_id, "payload": row.payload, "error": row.error, "created_at": row.created_at} for row in letters]
