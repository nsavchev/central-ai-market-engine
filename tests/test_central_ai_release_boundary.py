"""Release boundaries for the separately deployed Central AI API."""
from pathlib import Path


def test_central_ai_compose_is_api_only_and_fail_closed():
    source = Path("docker-compose.central.yml").read_text()
    assert 'central-ai:' in source
    assert '127.0.0.1:8010:8010' in source
    assert 'CENTRAL_TASK_API_ENABLED: "NO"' in source
    assert 'env_file: .env.central' in source
    assert 'read_only: true' in source
    assert 'no-new-privileges:true' in source
    assert 'central_ai_tasks:/var/lib/central-ai' in source
    assert 'dockerfile: central_ai/Dockerfile' in source
    assert '\n  api:' not in source
    assert '\n  db:' not in source


def test_release_document_preserves_production_boundaries():
    doc = Path("docs/audits/CENTRAL_AI_ONLY_RELEASE_GATE_2026-11-01.md").read_text()
    for phrase in (
        'docker-compose.central.yml',
        'market_engine_v0_9',
        '--no-deps',
        'CENTRAL_TASK_API_ENABLED=NO',
        '127.0.0.1:8010:8010',
        'rollback',
        'Postgres',
    ):
        assert phrase in doc
