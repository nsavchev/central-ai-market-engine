import os
import asyncio
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from central_ai.app import app
from central_ai import app as provider_app

def test_health():
    assert TestClient(app).get('/health').json()['status'] == 'ok'

def test_auth():
    os.environ['CENTRAL_API_TOKEN']='test-secret-token-at-least-24-chars'
    c=TestClient(app)
    assert c.post('/ask',json={'prompt':'hi'}).status_code == 401
    assert c.post('/ask',headers={'X-API-Token':os.environ['CENTRAL_API_TOKEN']},json={'prompt':'hi','providers':['openai','gemini']}).status_code == 422

def test_missing_key():
    os.environ['CENTRAL_API_TOKEN']='test-secret-token-at-least-24-chars'
    os.environ.pop('OPENAI_API_KEY',None)
    c=TestClient(app)
    r=c.post('/ask',headers={'X-API-Token':os.environ['CENTRAL_API_TOKEN']},json={'prompt':'hi'})
    assert r.status_code==200
    assert r.json()['results'][0]['status']=='not_configured'


class ProviderStream(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks = chunks
        self.delay = delay
        self.read = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.read += 1
            yield chunk

    async def aclose(self):
        self.closed = True


def invoke_provider(monkeypatch, stream, *, provider='openai', headers=None, status=200):
    keys = {'openai':'OPENAI_API_KEY', 'deepseek':'DEEPSEEK_API_KEY',
            'anthropic':'ANTHROPIC_API_KEY', 'gemini':'GEMINI_API_KEY'}
    monkeypatch.setenv(keys[provider], 'synthetic-provider-secret')
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, headers=headers or {}, stream=stream)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as client:
            return await asyncio.wait_for(
                provider_app.call_provider(client, provider, 'synthetic prompt', 20), timeout=0.3
            )

    return asyncio.run(exercise()), requests


def test_provider_total_deadline_stops_slow_body_and_closes_stream(monkeypatch):
    monkeypatch.setattr(provider_app, 'PROVIDER_DEADLINE_SECONDS', 0.02, raising=False)
    stream = ProviderStream([b' '] * 50, delay=0.01)
    result, requests = invoke_provider(monkeypatch, stream)
    assert result == {'provider':'openai', 'status':'error', 'error_type':'TimeoutError'}
    assert stream.closed and stream.read < 50 and len(requests) == 1


def test_provider_size_limit_stops_before_consuming_entire_response(monkeypatch):
    monkeypatch.setattr(provider_app, 'MAX_PROVIDER_RESPONSE_BYTES', 4096, raising=False)
    stream = ProviderStream([b' ' * 1024] * 100)
    result, requests = invoke_provider(monkeypatch, stream)
    assert result == {'provider':'openai', 'status':'error', 'error_type':'ValueError'}
    assert stream.closed and stream.read < 100 and len(requests) == 1


@pytest.mark.parametrize('provider,payload', [
    ('openai', {'choices':[{'message':{'content':'fixture answer'}}]}),
    ('deepseek', {'choices':[{'message':{'content':'fixture answer'}}]}),
    ('anthropic', {'content':[{'type':'text','text':'fixture answer'}]}),
    ('gemini', {'candidates':[{'content':{'parts':[{'text':'fixture answer'}]}}]}),
])
def test_bounded_provider_preserves_each_existing_response_protocol(monkeypatch, provider, payload):
    stream = ProviderStream([json.dumps(payload).encode()])
    result, requests = invoke_provider(monkeypatch, stream, provider=provider)
    assert result == {'provider':provider, 'status':'ok', 'answer':'fixture answer'}
    assert stream.closed and len(requests) == 1
    assert requests[0].headers['Accept-Encoding'] == 'identity'
    sent = json.loads(requests[0].content)
    assert (sent['generationConfig']['maxOutputTokens'] if provider == 'gemini' else sent['max_tokens']) == 20


@pytest.mark.parametrize('headers', [
    {'Content-Length':'999999999'}, {'Content-Length':'-1'}, {'Content-Encoding':'gzip'}
])
def test_provider_rejects_unreviewed_body_encoding_or_length_before_read(monkeypatch, headers):
    stream = ProviderStream([b'synthetic-provider-secret'])
    result, requests = invoke_provider(monkeypatch, stream, headers=headers)
    assert result['status'] == 'error' and 'answer' not in result
    assert 'synthetic-provider-secret' not in json.dumps(result)
    assert stream.closed and stream.read == 0 and len(requests) == 1


def test_provider_answer_is_rejected_instead_of_truncated(monkeypatch):
    monkeypatch.setattr(provider_app, 'MAX_PROVIDER_ANSWER_CHARS', 8, raising=False)
    stream = ProviderStream([json.dumps({'choices':[{'message':{'content':'too long answer'}}]}).encode()])
    result, requests = invoke_provider(monkeypatch, stream)
    assert result['status'] == 'error' and 'answer' not in result
    assert len(requests) == 1


def test_provider_redirect_is_not_followed_even_with_redirecting_client(monkeypatch):
    stream = ProviderStream([b'private redirect body'])
    result, requests = invoke_provider(monkeypatch, stream, status=302,
                                       headers={'Location':'https://unreviewed.invalid/collect'})
    assert result == {'provider':'openai','status':'upstream_error','http_status':302}
    assert len(requests) == 1 and stream.closed


@pytest.mark.parametrize('payload', [[], {'choices':[{'message':{'content':['invalid']}}]},
                                     {'choices':[{'message':{'content':'   '}}]}])
def test_invalid_or_empty_provider_answer_is_not_success(monkeypatch, payload):
    stream = ProviderStream([json.dumps(payload).encode()])
    result, requests = invoke_provider(monkeypatch, stream)
    assert result['status'] == 'error' and 'answer' not in result
    assert len(requests) == 1 and stream.closed


def test_provider_deadline_also_covers_waiting_for_headers(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-provider-secret')
    monkeypatch.setattr(provider_app, 'PROVIDER_DEADLINE_SECONDS', 0.02)
    calls = []

    async def handle(request):
        calls.append(request)
        await asyncio.sleep(1)
        pytest.fail('header wait must have been cancelled')

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await asyncio.wait_for(
                provider_app.call_provider(client, 'openai', 'synthetic prompt', 20), 0.3
            )

    result = asyncio.run(exercise())
    assert result == {'provider':'openai', 'status':'error', 'error_type':'TimeoutError'}
    assert len(calls) == 1


def test_caller_cancellation_is_not_converted_into_provider_success_or_retry(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-provider-secret')
    stream = ProviderStream([b' '] * 50, delay=0.01)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, stream=stream)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            task = asyncio.create_task(provider_app.call_provider(client, 'openai', 'synthetic', 20))
            await asyncio.sleep(0.02)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(exercise())
    assert stream.closed and len(calls) == 1


@pytest.mark.parametrize('provider,prompt,tokens', [
    ('unknown','fixture',20), ('openai','',20), ('openai','x'*12001,20),
    ('openai','fixture',0), ('openai','fixture',1501), ('openai','fixture',True),
])
def test_direct_transport_call_cannot_bypass_request_limits(monkeypatch, provider, prompt, tokens):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-provider-secret')

    def unexpected_request(request):
        pytest.fail('Invalid request must not reach provider transport')

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as client:
            with pytest.raises(ValueError, match='INVALID_PROVIDER_REQUEST'):
                await provider_app.call_provider(client, provider, prompt, tokens)

    asyncio.run(exercise())
