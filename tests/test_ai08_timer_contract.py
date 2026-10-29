from pathlib import Path

def test_ai08_timer_optin_and_non_overlap():
    timer=Path("deploy/ai08/central-ai-staging.timer").read_text()
    service=Path("deploy/ai08/central-ai-staging.service").read_text()
    assert "OnUnitInactiveSec=5min" in timer
    assert "Persistent=false" in timer
    assert "Type=oneshot" in service
    assert "TimeoutStartSec=120" in service
    assert "CENTRAL_SUPERVISED_SERVICE_ENABLED=YES" in service
    assert "--project-name ca-ai08-staging" in service
    assert "--rm --no-deps" in service
    assert "docker-compose.ai06.yml" in service
    assert "enable --now" not in service
    assert "market_engine" not in service
