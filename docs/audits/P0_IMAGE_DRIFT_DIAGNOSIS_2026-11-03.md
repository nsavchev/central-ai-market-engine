# P0 image drift diagnosis — 2026-11-03

Evidence: PR #128 diagnostic commit 3a2706b1a753b9be343d6a5a3ad6197aa8d21596, Actions run 41585739193, artifact 13207194242. All 33 workflows succeeded. Downloaded artifact manifest checks all matched.

Two images have equal runtime Config, different Created timestamps and RootFS layers. The scoped filesystem inventory found 1509 differing records, all with differing mtime_ns, all under Python site-packages. Of these, 421 also have differing content SHA256; every such file is .pyc. No other content differences were observed within the scanned directories (site-packages, /srv, /var/lib/central-ai). This is not a full root filesystem comparison or proof that timestamps are the only cause of image ID drift.

Remediation: disable pip bytecode compilation with --no-compile and runtime bytecode writes with PYTHONDONTWRITEBYTECODE=1 in the isolated release recipe. Preserve exact pins, --require-hashes, immutable base and USER 10001. The existing validator accepts only the optional --no-compile token in the required pip command. Regression test covers the actual release recipe and rejection of a missing hash flag or unhashed entry.

Architecture: no new runtime module or alternate worker, queue, verifier or deployment path. Diagnostic Python runs in disposable read-only containers without network or host mounts. The temporary root override is for reading the filesystem only; the image Config must still declare USER 10001.

Remaining gates: inspect the new CI artifact to verify removal of .pyc content drift; timestamp/layer reproducibility remains open. Builds are on the same runner, not independent-builder proof. Registry provenance, full security review, isolated acceptance and issue #90 VPS evidence remain required. No merge, production changes, live trading or deployment authorized.
