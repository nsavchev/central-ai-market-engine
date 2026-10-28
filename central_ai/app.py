"""Central AI v1: controlled multi-provider orchestration; no autonomous trading."""
import os
import asyncio
import secrets
from typing import Literal
import httpx
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Central AI v1.0", docs_url=None, redoc_url=None)
PROVIDERS = ("openai", "anthropic", "gemini", "deepseek")

class Query(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    providers: list[Literal["openai", "anthropic", "gemini", "deepseek"]] = Field(default_factory=lambda: ["openai"] ,min_length=1,max_length=4)
    mode: Literal["single", "compare"] = "single"
    max_tokens: int = Field(default=600, ge=1, le=1500)


def auth(x_api_token: str | None = Header(default=None)):
    token = os.getenv("CENTRAL_API_TOKEN", "")
    if len(token) < 24 or not x_api_token or not secrets.compare_digest(token, x_api_token):
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/health")
def health():
    return {"status": "ok", "service": "central-ai", "version": "1.0"}

@app.get("/providers", dependencies=[Depends(auth)])
def providers():
    return {p: {"configured": bool(os.getenv(k))} for p,k in {
        "openai":"OPENAI_API_KEY", "anthropic":"ANTHROPIC_API_KEY",
        "gemini":"GEMINI_API_KEY", "deepseek":"DEEPSEEK_API_KEY"}.items()}

async def call_provider(client: httpx.AsyncClient, provider: str, prompt: str, max_tokens: int):
    keys = {"openai":"OPENAI_API_KEY", "anthropic":"ANTHROPIC_API_KEY", "gemini":"GEMINI_API_KEY", "deepseek":"DEEPSEEK_API_KEY"}
    key = os.getenv(keys[provider], "")
    if not key:
        return {"provider":provider,"status":"not_configured"}
    try:
        if provider in ("openai", "deepseek"):
            base = "https://api.openai.com/v1/chat/completions" if provider == "openai" else "https://api.deepseek.com/chat/completions"
            model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini") if provider == "openai" else os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            r = await client.post(base, headers={"Authorization":f"Bearer {key}"},json={"model":model,"messages":[{"role":"user","content":prompt}],"max_tokens":max_tokens})
            r.raise_for_status()
            result = r.json()["choices"][0]["message"]["content"]
        elif provider == "anthropic":
            r = await client.post("https://api.anthropic.com/v1/messages",headers={"x-api-key":key,"anthropic-version":"2023-06-01"},json={"model":os.getenv("ANTHROPIC_MODEL","claude-sonnet-4-5"),"max_tokens":max_tokens,"messages":[{"role":"user","content":prompt}]})
            r.raise_for_status()
            result = "\n".join(x.get("text","") for x in r.json().get("content",[]) if x.get("type")=="text")
        else:
            model = os.getenv("GEMINI_MODEL","gemini-2.5-flash")
            r = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",headers={"x-goog-api-key":key},json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"maxOutputTokens":max_tokens}})
            r.raise_for_status()
            result = "\n".join(part.get("text", "") for candidate in r.json().get("candidates",[]) for part in candidate.get("content",{}).get("parts",[]))
        return {"provider":provider,"status":"ok","answer":result}
    except httpx.HTTPStatusError as e:
        return {"provider":provider,"status":"upstream_error","http_status":e.response.status_code}
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
        return {"provider":provider,"status":"error","error_type":type(e).__name__}

@app.post("/ask", dependencies=[Depends(auth)])
async def ask(req: Query):
    chosen = list(dict.fromkeys(req.providers))
    if req.mode == "single" and len(chosen) != 1:
        raise HTTPException(422, "single mode requires exactly one provider")
    if req.mode == "compare" and len(chosen) < 2:
        raise HTTPException(422, "compare mode requires at least two providers")
    async with httpx.AsyncClient(timeout=httpx.Timeout(65.0), follow_redirects=False) as client:
        results = await asyncio.gather(*(call_provider(client,p,req.prompt,req.max_tokens) for p in chosen))
    return {"mode":req.mode,"results":results,"note":"Independent model responses; not independently fact-checked. No trades executed."}

# Task API is opt-in. This facade cannot execute work, approve or deploy.
def _task_bridge():
    from pathlib import Path
    if os.environ.get("CENTRAL_TASK_API_ENABLED") != "YES":
        raise HTTPException(status_code=503, detail="TASK_API_DISABLED")
    location = os.environ.get("CENTRAL_TASK_DB", "")
    if not location or not Path(location).is_absolute() or not Path(location).parent.is_dir():
        raise HTTPException(status_code=503, detail="TASK_DB_NOT_CONFIGURED")
    from central_ai.persistent_bridge import PersistentTaskBridge
    return PersistentTaskBridge(location)


class TaskSubmission(BaseModel):
    description: str = Field(min_length=1, max_length=4000)


@app.post("/tasks", dependencies=[Depends(auth)], status_code=202)
def submit_task(req: TaskSubmission):
    bridge = _task_bridge()
    task = bridge.submit(req.description)
    return {"task_id": task["task_id"], "status": task["status"],
            "approved": False, "deployment_allowed": False}


@app.get("/tasks/{task_id}", dependencies=[Depends(auth)])
def task_status(task_id: str):
    from uuid import UUID
    try:
        canonical = str(UUID(task_id))
        if canonical != task_id:
            raise ValueError("NON_CANONICAL")
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail="INVALID_TASK_ID")
    bridge = _task_bridge()
    result = bridge.status(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
    return {"task_id": task_id, "status": result["status"],
            "approved": False, "deployment_allowed": False}

