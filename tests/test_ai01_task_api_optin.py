"""Task HTTP API is opt-in, authenticated and planning-only."""
from fastapi.testclient import TestClient
from central_ai.app import app


def test_tasks_disabled_by_default(monkeypatch):
    monkeypatch.setenv("CENTRAL_API_TOKEN", "x" * 32)
    monkeypatch.delenv("CENTRAL_TASK_API_ENABLED", raising=False)
    client = TestClient(app)
    response = client.post("/tasks", headers={"x-api-token": "x" * 32},
                           json={"description": "Analyze a safe source file"})
    assert response.status_code == 503


def test_tasks_auth_and_durable_status(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRAL_API_TOKEN", "x" * 32)
    monkeypatch.setenv("CENTRAL_TASK_API_ENABLED", "YES")
    monkeypatch.setenv("CENTRAL_TASK_DB", str(tmp_path / "tasks.sqlite"))
    client = TestClient(app)
    assert client.post("/tasks", json={"description": "Analyze sample.py"}).status_code == 401
    headers = {"x-api-token": "x" * 32}
    created = client.post("/tasks", headers=headers, json={"description": "Analyze sample.py"})
    assert created.status_code == 202, created.text
    task = created.json()
    assert task["approved"] is False and task["deployment_allowed"] is False
    reopened = TestClient(app).get("/tasks/" + task["task_id"], headers=headers)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "planned"
    assert reopened.json()["deployment_allowed"] is False
