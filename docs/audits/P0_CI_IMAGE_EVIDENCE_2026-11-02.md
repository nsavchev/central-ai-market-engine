# Verified CI build inventory — 2026-11-02

Source workflow: DUP-01 workflow ownership contracts, run 41427830102, commit `5bb8e1521ad79c47873c809d615a81177f209ad9`. GitHub Actions 32/32 SUCCESS. Artifact `p0-central-ai-build-evidence`, artifact ID `13132294658`, downloaded and inspected.

Image ID (local Docker image, **not** repository digest):

`sha256:be984d7f745c322c4c38371c77687a8a261aa82e53dd6b91b33ab95c5074189f`

Actual `python -m pip freeze --all`:

```text
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.16.0
certifi==2026.10.23
click==8.5.0
fastapi==0.162.0
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.20
opentelemetry-api==1.45.2
pip==25.0.1
pydantic==2.14.2
pydantic_core==2.50.2
starlette==1.10.0
typing-inspection==0.4.4
typing_extensions==4.16.0
uvicorn==0.54.0
```

## Interpretation and mandatory follow-up

- Evidence establishes package versions **for one CI image only**, not that the image can be built reproducibly.
- The floating `FROM python:3.12-slim` must be replaced by a vetted immutable base digest; the exact image digest above must **not** be inserted as the base digest.
- A verified hashes-based resolver process needs to generate a complete transitive `requirements.lock`; do not invent or infer wheel hashes from `pip freeze`.
- Lock regeneration must be performed in a pinned environment for target platform/architecture and installation must use the checked lock.
- Independent builds from the same exact commit+base+lock should be compared before calling the result reproducible.
- Static `release_build_policy.py` is only an early guard, not an independent cryptographic validator. Keep Task API NO and do not deploy.
