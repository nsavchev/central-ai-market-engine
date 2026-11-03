# P0 frozen verifier inputs — 2026-11-03

Parent 3b9fdbb7508a838ceca3eca919af6e287a3fb503, PR #128. Existing functional verifier only; no new verifier, queue, scheduling or deployment path.

## Execution-byte boundary

Read each absolute .py input through a single no-follow/nonblocking descriptor. fstat must identify a regular file with at most 32768 bytes, no group/other write bits and one hardlink. Reads are bounded to 32769 bytes to reject growth/oversize. The expected candidate and separate test SHA256 are checked against the captured bytes. Caller-owned file paths are not mounted thereafter.

Copy the captured bytes into a unique private 0700 directory, use 0444 files, and bind those exact copies read-only into the existing restricted container. The caller originals can be replaced after validation without changing execution bytes. The Docker daemon must be local to the dedicated runner filesystem; remote daemon/other host file access is not supported by this arrangement.

The trusted runner account/host/root can still modify its own snapshots. This is protection against mutable caller input paths, not a tamper-proof or host-root security boundary. Docker is still not a hostile-code high-assurance sandbox.

## Cleanup and quarantine

Remove snapshots after normal completion or confirmed forced timeout removal. On timeout cleanup failure, timeout/OSError during removal, or Docker launch OSError, retain snapshots and return cleanup_unconfirmed, snapshot_directory and container_name. Never automatically retry this result. Operator must inspect/remove the named container before deleting quarantined inputs. Local resource bounds still apply; quarantine directories need operator retention monitoring.

## Evidence

80 local tests pass, including replacement of both original files immediately before Docker, unsafe file types, bounded input checks and quarantine retention. The real functional Docker CI fixture mutates originals immediately before subprocess.run while the container must still pass with the captured candidate/tests; normal failing-functional and timeout-removal fixtures remain.

New-commit CI must be reviewed separately. Signed/trusted reviewer authorization for the exact task/candidate/test/image tuple remains OPEN. Expected hashes alone are not author authentication. No production/VPS operation, merge, activation or live trading; issue #90 remains NO-GO without current deployment/restore evidence.
