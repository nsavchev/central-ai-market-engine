# Supplied-input report schedule: disabled proposal

These `.example` files are not installed or enabled. They do not download data,
start an AI worker, use Docker, read trading credentials or execute orders.
Use the existing systemd timer mechanism; no second application scheduler exists.
The draft times are 08:00 and 23:15 Europe/Sofia, every calendar day. This is not
an exchange holiday schedule. A report can legitimately reuse the previous daily
close; its hash, source retrieval time and actual report time must be inspected.

## Required layout and acceptance

Review an exact source SHA and compatible existing Python environment under the
intended nonroot service account. The paths below are example account-relative
locations, not observations of an installed host:

- `~/market-report-runtime/source`: reviewed source, not generated code.
- `~/market-report-runtime/venv`: reviewed dependencies; no installation at startup.
- `~/market-report-runtime/input.json`: operator-managed `market-combined-input-v1`.
- `~/market-report-state`: private writable output directory.
- `~/market-report-runtime/execution.authorized`: explicit enable sentinel, absent by default.

Inputs require declared manual provenance/usage rights and aware retrieval times;
publish each complete input atomically. Never backdate retrieval metadata to make
old data pass. `--report-asof-now` records actual UTC report time and preserves
the input's declared time, then applies freshness to the actual day. The draft
three-calendar-day age limit is an explicit proposal; it does not prove that the
latest exchange session is included. Review weekends/long closures separately.
No inputs, sentinel, virtualenv, units or directories are created by these files.

Before any installation, validate user-manager sandbox support and read/write
paths under the intended identity, run one approved foreground report, measure
runtime/termination and inspect its output/hash. Proposed 60/15-second service
bounds are not operational acceptance. `RestrictAddressFamilies=AF_UNIX` blocks
new Internet sockets; do not use this unit as a downloader. No network or
provider credential belongs in its environment.

## Failure and consumption

One oneshot service serializes timer starts. There is no automatic restart and
`Persistent=false` does not replay missed schedules. Validation failures exit
nonzero before replacing output. Complete JSON is written to a private temporary
file in the destination directory, flushed and atomically replaced. A forced
kill may leave a temporary file; retain it for inspection. Atomic replacement
does not establish a full power-loss durability contract.

After any failed run, the old latest-report file can still exist. Consumers must
check service result, `report_asof`, `execution_clock_mode`, market date/age and
source provenance. File existence alone does not mean a successful current run.
The report remains partial while unsupported/missing context is unavailable.

## Operator run and stop contract (after separate installation approval)

First inspect the exact installed unit/config diff and retain the previous
versions. Do not replace the existing Central AI service or staging timer.
After the approved sentinel and units are deliberately installed, a manual run
is `systemctl --user start market-report.service`; inspect its result and output
before separately enabling any timer. No timer is enabled by manual service start.

For rollback, stop future triggers with
`systemctl --user disable --now market-report.timer`, then stop any active report
with `systemctl --user stop market-report.service`. Verify both states, retain
inputs/outputs/journals and remove the enable sentinel if withdrawing authority.
Do not reset AI ledgers, revert databases, replay paid work or alter unrelated
services. Restore only the reviewed unit/config/source version after compatibility
review; a previous file's presence is not proof of a new successful run.
