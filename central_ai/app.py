"""Central AI v1: controlled multi-provider orchestration; no autonomous trading."""
import os
import asyncio
import json
import secrets
import re
from datetime import datetime, timezone
from typing import Literal
import httpx
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Central AI v1.0", docs_url=None, redoc_url=None)
PROVIDERS = ("openai", "anthropic", "gemini", "deepseek")
PROVIDER_DEADLINE_SECONDS = 65.0
MAX_PROVIDER_RESPONSE_BYTES = 128 * 1024
MAX_PROVIDER_ANSWER_CHARS = 12000

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

async def _provider_json(client, url, *, headers, json_body):
    """One bounded request, including headers/body; no redirects or retries."""
    headers = dict(headers, **{"Accept-Encoding": "identity"})
    async with asyncio.timeout(PROVIDER_DEADLINE_SECONDS):
        async with client.stream("POST", url, headers=headers, json=json_body,
                                 follow_redirects=False) as response:
            response.raise_for_status()
            if response.headers.get("content-encoding", "identity").lower() not in ("", "identity"):
                raise ValueError("PROVIDER_ENCODING_NOT_ALLOWED")
            length = response.headers.get("content-length")
            if length is not None and not 0 <= int(length) <= MAX_PROVIDER_RESPONSE_BYTES:
                raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
            body = bytearray()
            async for chunk in response.aiter_raw(chunk_size=4096):
                if len(body) + len(chunk) > MAX_PROVIDER_RESPONSE_BYTES:
                    raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
                body.extend(chunk)
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("INVALID_PROVIDER_RESPONSE")
            return data


async def call_provider(client: httpx.AsyncClient, provider: str, prompt: str, max_tokens: int, *, model_override=None):
    if (provider not in PROVIDERS or not isinstance(prompt, str) or not 1 <= len(prompt) <= 12000
            or type(max_tokens) is not int or not 1 <= max_tokens <= 1500):
        raise ValueError("INVALID_PROVIDER_REQUEST")
    if model_override is not None and (provider != 'openai' or not isinstance(model_override, str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}', model_override)):
        raise ValueError('INVALID_PROVIDER_MODEL')
    keys = {"openai":"OPENAI_API_KEY", "anthropic":"ANTHROPIC_API_KEY", "gemini":"GEMINI_API_KEY", "deepseek":"DEEPSEEK_API_KEY"}
    key = os.getenv(keys[provider], "")
    if not key:
        return {"provider":provider,"status":"not_configured"}
    try:
        if provider in ("openai", "deepseek"):
            base = "https://api.openai.com/v1/chat/completions" if provider == "openai" else "https://api.deepseek.com/chat/completions"
            model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini") if provider == "openai" else os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            if model_override is not None:
                model = model_override
            data = await _provider_json(client, base, headers={"Authorization":f"Bearer {key}"},
                json_body={"model":model,"messages":[{"role":"user","content":prompt}],"max_tokens":max_tokens})
            result = data["choices"][0]["message"]["content"]
        elif provider == "anthropic":
            data = await _provider_json(client, "https://api.anthropic.com/v1/messages",headers={"x-api-key":key,"anthropic-version":"2023-06-01"},
                json_body={"model":os.getenv("ANTHROPIC_MODEL","claude-sonnet-4-5"),"max_tokens":max_tokens,"messages":[{"role":"user","content":prompt}]})
            result = "\n".join(x.get("text","") for x in data.get("content",[]) if x.get("type")=="text")
        else:
            model = os.getenv("GEMINI_MODEL","gemini-2.5-flash")
            data = await _provider_json(client, f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",headers={"x-goog-api-key":key},
                json_body={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"maxOutputTokens":max_tokens}})
            result = "\n".join(part.get("text", "") for candidate in data.get("candidates",[]) for part in candidate.get("content",{}).get("parts",[]))
        if not isinstance(result, str) or not result.strip() or len(result) > MAX_PROVIDER_ANSWER_CHARS:
            raise ValueError("INVALID_PROVIDER_ANSWER")
        return {"provider":provider,"status":"ok","answer":result}
    except httpx.HTTPStatusError as e:
        return {"provider":provider,"status":"upstream_error","http_status":e.response.status_code}
    except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError, TimeoutError, RecursionError) as e:
        return {"provider":provider,"status":"error","error_type":type(e).__name__}


def make_openai_generator(*, enabled, database, transport=None):
    """Opt-in host callback for admitted generation; never enables a worker."""
    from pathlib import Path
    from central_ai.task_storage import TaskStorage, OPENAI_GENERATOR_ID
    path = Path(database)
    if enabled != 'YES' or not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('OPENAI_GENERATOR_NOT_CONFIGURED')
    storage = TaskStorage(path)

    async def dispatch(profile):
        async with httpx.AsyncClient(timeout=PROVIDER_DEADLINE_SECONDS, trust_env=False,
                                     follow_redirects=False, transport=transport) as client:
            if datetime.now(timezone.utc) >= datetime.fromisoformat(profile['expires_at']):
                raise ValueError('GENERATION_ADMISSION_EXPIRED')
            result = await call_provider(client, 'openai', profile['prompt'], profile['max_tokens'],
                                         model_override=profile['model'])
            if result.get('status') != 'ok':
                raise RuntimeError('OPENAI_GENERATION_FAILED')
            return result['answer']

    def generate(request):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise ValueError('OPENAI_GENERATOR_REQUIRES_SYNC_CONTEXT')
        if not os.getenv('OPENAI_API_KEY'):
            raise ValueError('OPENAI_GENERATOR_NOT_CONFIGURED')
        profile = storage.begin_openai_dispatch(request)
        return asyncio.run(dispatch(profile))

    generate.generator_id = OPENAI_GENERATOR_ID
    return generate

@app.post("/ask", dependencies=[Depends(auth)])
async def ask(req: Query):
    chosen = list(dict.fromkeys(req.providers))
    if req.mode == "single" and len(chosen) != 1:
        raise HTTPException(422, "single mode requires exactly one provider")
    if req.mode == "compare" and len(chosen) < 2:
        raise HTTPException(422, "compare mode requires at least two providers")
    async with httpx.AsyncClient(timeout=httpx.Timeout(65.0), follow_redirects=False, trust_env=False) as client:
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

