from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app

client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_workflow_run_and_trace():
    created = client.post("/v1/workflows", json={"name": "demo", "steps": [{"id": "one", "type": "echo", "input": {"text": "hello"}}]})
    assert created.status_code == 201
    run = client.post(f"/v1/workflows/{created.json()['id']}/runs", json={"input": {"request_id": "r1"}})
    assert run.status_code == 201 and run.json()["status"] == "succeeded"
    trace = client.get(f"/v1/runs/{run.json()['id']}/trace").json()
    assert trace["trace_id"] == run.json()["trace_id"] and trace["steps"][0]["status"] == "succeeded"


def test_failed_action_retries_and_dead_letters():
    created = client.post("/v1/workflows", json={"name": "bad-input", "steps": [{"id": "summary", "type": "llm_summary", "input": {}, "retries": 2}]})
    run = client.post(f"/v1/workflows/{created.json()['id']}/runs", json={})
    assert run.json()["status"] == "dead_lettered"
    assert len(client.get(f"/v1/runs/{run.json()['id']}/trace").json()["steps"]) == 3
    assert len(client.get("/v1/dead-letters").json()) == 1


def test_duplicate_step_ids_are_rejected():
    response = client.post("/v1/workflows", json={"name": "bad", "steps": [{"id": "same", "type": "echo"}, {"id": "same", "type": "echo"}]})
    assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"


def test_missing_workflow_error():
    response = client.post("/v1/workflows/missing/runs", json={})
    assert response.status_code == 404 and response.json()["error"]["code"] == "workflow_not_found"
