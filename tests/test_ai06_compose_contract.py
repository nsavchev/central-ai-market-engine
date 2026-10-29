"""AI-06: test-only Docker worker must remain isolated and default-disabled."""
from pathlib import Path

def test_ai06_compose_security_contract():
    source = Path("docker-compose.ai06.yml").read_text()
    for required in (
        'profiles: ["ai06"]',
        'restart: "on-failure:3"',
        'network_mode: "none"',
        'read_only: true',
        'cap_drop: ["ALL"]',
        'pids_limit: 64',
        'cpus: 0.50',
        'mem_limit: 256m',
        'AI06_TEST_ENABLE:-NO',
        'ai06_isolated_tasks:/var/lib/central-ai',
        'central_ai.worker_supervised',
    ):
        assert required in source, required
    assert "/opt/central-ai/" not in source
    assert "privileged: true" not in source
