# VPS read-only evidence bridge (proposal)

This is a diagnostic collector, not a deployment agent. It does **not** SSH into the VPS from ChatGPT, execute project modules, start/restart containers, modify PostgreSQL, or migrate SQLite. It collects an allowlisted JSON snapshot: Git commit and clean flag, six Python file SHA-256 hashes compared between the export and release directories, three Docker container states, and the `workflow_states` table's column names / row count.

## Before running
- Review `tools/vps_readonly_audit.py` on its draft PR and verify paths and allowed data against local policy.
- Do not merge the entire stacked feature PR chain merely to obtain this tool; copy the reviewed standalone script to a temporary location only after review.
- Use a dedicated unprivileged system user with file-read permissions for the allowlisted files and Docker access provided through a narrowly scoped, operator-controlled collection service. **Do not add the audit user to the docker group:** Docker access is effectively root-equivalent. Until that limited access path is built, service states will be `unknown`; this is expected and safer.
- Run manually (no token, no outbound submission): `python3 tools/vps_readonly_audit.py`. Review the JSON before sharing.
- Optional posting to GitHub Issue #90: only after review, provide a **fine-grained, issues-write-only token scoped to this repository**, stored outside the repo in `/root/.config/central-ai-audit/github-token` (mode 0600) and run `python3 tools/vps_readonly_audit.py --post`. This optional workflow currently assumes the operator can access that file; do not give root SSH or secrets to ChatGPT.
- Tokens should be short-lived and revoked after validation. Never output the token, `.env`, logs, database URLs or raw task content.

## Limits / release gate
This is only partial evidence. PostgreSQL exact schema and constraints, image/source attestation, all task graph callers, backup/restore, security testing and PR stack comparisons must be reviewed separately. A successful post is **not** proof of production readiness. Always preserve human deployment approval and the paper-only trading boundary.

## Next steps
1. Unit test offline collection with mock paths and mocked commands.
2. Review output redaction, file-size limits and least-privilege execution.
3. Reconcile actual VPS findings with GitHub Issue #90.
4. Require all release gates before any proposed merge or deployment.
