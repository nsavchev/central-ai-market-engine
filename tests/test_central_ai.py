import os
from fastapi.testclient import TestClient
from central_ai.app import app

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
