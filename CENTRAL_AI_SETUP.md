# Central AI v1.0 — initial deploy (Bulgarian project)

This is an **initial functional API prototype**, not a finished autonomous multi-agent platform. It preserves Market Engine v0.9 unchanged and adds a separate service.

## VPS (Ubuntu 24.04)

1. Install Docker Engine and Compose plugin from Docker official Ubuntu instructions; enable firewall and SSH-key access. Do not expose port 8010 publicly.
2. Extract archive; `cd market_engine_v0_9`.
3. `cp .env.central.example .env.central` and edit secrets. Generate a token with `openssl rand -hex 32`.
4. Set only the provider API keys you intend to use. Model names are configurable; update if providers retire them.
5. `chmod 600 .env.central`.
6. `docker compose -f docker-compose.central.yml up -d --build`.
7. `curl http://127.0.0.1:8010/health`.
8. Example (do not paste the real token in chat):

```bash
curl -sS http://127.0.0.1:8010/ask \
  -H "X-API-Token: $CENTRAL_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Explain relative strength in one paragraph","providers":["openai"],"mode":"single"}'
```

To load token in shell: `set -a; . ./.env.central; set +a` (only for trusted files). Or use a local reverse proxy with authenticated access. Keep port 8010 loopback-only.

## Limitations and next phase

- No keys included; no real model calls performed in this build environment.
- `/ask` compares model outputs but does not yet synthesize, validate claims, route automatically, maintain long-term memory or invoke Market Engine tools.
- Hard caps on request length, max tokens and four providers limit *individual* request size, not overall monthly spend; set provider-side budgets, quotas and alerts before public use.
- Add rate limiting, user authentication, audit logs, proxy TLS, secret management, data redaction and usage accounting before external access.
- Market Engine remains paper/simulation-only; no live orders are triggered by Central AI.
- Provider API responses may contain sensitive information; do not send confidential data without reviewing provider policies.
