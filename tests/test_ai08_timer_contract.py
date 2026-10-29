from pathlib import Path

def test_ai08_staging_isolation_and_opt_in():
    compose=Path("docker-compose.ai08.yml").read_text()
    service=Path("deploy/staging/central-ai08.service").read_text()
    timer=Path("deploy/staging/central-ai08.timer").read_text()
    for token in ('profiles: ["ai08"]','restart: "no"','network_mode: "none"','read_only: true','cap_drop: ["ALL"]','AI08_STAGING_ENABLED:-NO','ai08_staging_tasks:/var/lib/central-ai'):
        assert token in compose
    assert "worker_periodic" in compose
    assert "Type=oneshot" in service
    assert "--rm --no-deps ai08-worker" in service
    assert "OnUnitInactiveSec=5min" in timer
    assert "WantedBy=timers.target" in timer
    assert "systemctl enable" not in service+timer
