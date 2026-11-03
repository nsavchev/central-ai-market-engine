# P0 two-build evidence — 2026-11-03

Verified GitHub Actions run **41531864191** for commit `b8a2d70d2e9a8bc18c2da2495e554b69ce3e5d50`, artifact **13182487569**. All 33 associated workflow runs succeeded.

The ZIP `manifest.sha256` was independently checked against **every named artifact entry**. The package inventories and import smoke outputs match between two CI builds, including a second `--no-cache` build.

**Results (distinct Docker local image IDs):**
- initial `sha256:f5c1b3ea099df627ddb3fffbb7649c5815b172d74f8aecacbba61ae874f329c9`
- rebuilt `sha256:2dbfc0d423dfd050f3f97395bd232cce43103624657b5c25216621ccb8d28717`
- pinned source base `python@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30`

**Interpretation:** hash-locked dependencies and smoke checks are repeatable in this runner. Docker image IDs **differ**, so byte-for-byte reproducibility is **not** established. Different image IDs may arise from build metadata/timestamps; investigate deterministically rather than treating matching package lists as proof of identical images.

**Correction:** the subsequent CI recipe commit `0115a94dc2ff15c0ef739a8e74dba31e6e9a97f0` explicitly pulls the previously inspected immutable base digest instead of resolving mutable `python:3.12-slim` anew. CI for this correction must pass before accepting it.

**Still blocked:** source-controlled hash-locked release file and approved Docker recipe, independent API/task-storage integration and isolated VPS acceptance. No production deployment or secrets on untrusted runner.
