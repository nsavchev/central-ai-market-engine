# Supplied-input report schedule: disabled proposal

These `.example` files are not installed or enabled. They do not download data,
start an AI worker, use Docker, read trading credentials or execute orders.
Use the existing systemd timer mechanism; no second application scheduler exists.
The draft times are 08:00 and 23:15 Europe/Sofia, every calendar day. This is not
an exchange holiday schedule. A report can legitimately reuse the previous daily
close; its hash, source retrieval time and actual report time must be inspected.

## Required layout and acceptance

Review an exact source SHA and compatible existing Python environment under the
intended nonroot service account. This is a system-manager unit with explicit
`User=market-report` and `Group=market-report`, not a `systemctl` unit.
The generic account is a proposal, not an existing-account assertion; deliberately
select a reviewed nonroot identity before installation. No account is created.
Systemd prepares the sandbox before dropping to that identity; the report process
must still prove nonroot UID and zero effective/permitted/ambient capabilities.
The paths below are generic proposed locations, not installed-host observations:

- `/opt/market-report/source`: reviewed source, not generated code.
- `/opt/market-report/venv`: reviewed dependencies; no installation at startup.
- `/etc/market-report/input.json`: operator-managed `market-combined-input-v1`.
- `/var/lib/market-report`: private writable output directory.
- `/etc/market-report/execution.authorized`: explicit enable sentinel, absent by default.

Inputs require declared manual provenance/usage rights and aware retrieval times;
publish each complete input atomically. Never backdate retrieval metadata to make
old data pass. `--report-asof-now` records actual UTC report time and preserves
the input's declared time, then applies freshness to the actual day. The draft
three-calendar-day age limit is an explicit proposal; it does not prove that the
latest exchange session is included. Review weekends/long closures separately.
No inputs, sentinel, virtualenv, units or directories are created by these files.
Keep source, environment and enable sentinel administrator-controlled; grant the
selected service identity read access to required inputs and write access only
to its private output directory. Do not grant sudo or change Docker groups.
Do not use `%h` for this system-unit layout: system-manager home specifiers are
not a reliable substitution for the selected service account's private paths.

Before any installation, validate system-manager sandbox support and read/write
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
is `systemctl start market-report.service`; inspect its result and output
before separately enabling any timer. No timer is enabled by manual service start.

For rollback, stop future triggers with
`systemctl disable --now market-report.timer`, then stop any active report
with `systemctl stop market-report.service`. Verify both states, retain
inputs/outputs/journals and remove the enable sentinel if withdrawing authority.
Do not reset AI ledgers, revert databases, replay paid work or alter unrelated
services. Restore only the reviewed unit/config/source version after compatibility
review; a previous file's presence is not proof of a new successful run.

## Prepare a refreshed manual CSV input

The reviewed candidate CLI has a preparation-only path; it does not replace the
installed input, change its ownership/permissions, restart a service or alter a
timer. Run from that reviewed checkout using a compatible Python environment:

```bash
python -B -m app.scan_cli /private/SPY.csv \
  --prepare-nasdaq-input --asset-csv /private/NVDA.csv \
  --benchmark-symbol SPY --asset-symbol NVDA \
  --confirm-manual-use --max-age-calendar-days 3 \
  --output /private/new-input.json
```

Symbol mapping is an explicit operator assertion: these exports do not contain a
symbol column. Confirm rights for manual use; this flag is not an independent
vendor licence check. Original files remain unchanged. Header/date/OHLCV,
positive finite prices, duplicate/future dates, matching session sets and existing
source/freshness permissions are validated before a new staged file is written.
`N/A`/blank volume is recorded in provenance, never filled with zero; price-only
scanner calculations do not use volume. Missing prices are rejected. The two
original byte hashes are retained in provenance. Receipt time is local conversion
time, not a claimed vendor download/publication time or evidence of fresh prices.

The staged file uses the existing `market-combined-input-v1` contract. Preserve
missing macro/valuation/catalyst states; do not silently carry old company context
into a different symbol or overwrite it with invented values. Preparation refuses
an existing output path. Do not copy the private staged file directly over the
installed input: installation must retain an audited prior version, preserve root
ownership/service-group read access and atomically replace the complete file.
This operator installation step is separate from preparation. Do not run the
converter as a downloader or add vendor credentials to the service environment.

## Read an existing report

The reviewed candidate CLI can display compatible reports without writing files:

```bash
python -B -m app.scan_cli /var/lib/market-report/latest-report.json --show-report
```

Run this from a checkout containing the new mode; an older installed runtime may
not contain it. Reading an old report does not require upgrading the active
service. The view shows report time, price date, current calendar-day age,
benchmark/relative performance and unavailable sections. It recalculates the age
at viewing time; it never refreshes prices or treats file existence as service
health. Query the actual service/timer separately. No raw CSVs, generated reports,
private deployment metadata or provider credentials belong in the repository.


## Stage official API daily prices (explicitly disabled by default)

The candidate CLI can prepare a complete SPY/NVDA snapshot from Twelve Data's
fixed official HTTPS endpoint. It makes at most two requests per invocation,
without redirects or retries. It does not install input or manage services.
The positional `-` is unused in this preparation mode:

```bash
MARKET_TWELVE_DATA_ENABLED=1 MARKET_TWELVE_DATA_PRIVATE_USE_CONFIRMED=1 \
python -B -m app.scan_cli - --prepare-twelve-data-input \
  --api-key-file /private/provider.key --max-age-calendar-days 3 \
  --output /private/new-provider-input.json
```

The key must be a regular non-symlink file owned by the invoking UID, mode0400
or0600. Never pass credentials in command-line arguments, logs, reports or git.
Both environment declarations are required by `validate_source` before reading
the key or connecting; an account's private-use entitlement is an operator
assertion, not inferred from registration or successful authentication. Other
sources retain their existing permissions. Do not enable redistribution.

The pair uses200 daily bars per symbol, USD, regular sessions and explicit
`adjust=splits`, not dividend-inclusive total returns. No cross-provider splicing
or implicit session dropping occurs. Validate exact symbols/timezone/interval,
OHLC, positive finite closes, duplicate/future dates, history length, matching
sessions and the declared calendar-day freshness limit. Before16:10 New York,
exclude that date; afterwards allow that date, with no promise the provider has
published it. This buffer does not implement an exchange holiday/early-close
calendar or independently prove the latest completed-session close is available.
The freshest returned date remains visible; freshness failures preserve old files.

Output uses `market-provider-input-v1` inside the existing combined envelope.
Combined reports label `PROVIDER_API`, `automated_acquisition=true`, source and
retrieval completion time; original response hashes are retained. This is not a
manual import or independent quote verification. Macro, valuation and catalysts
remain unavailable unless separately supplied and validated.

The installed runtime must contain this provider-envelope support and receive
both source policy declarations before it can consume such input. An older
manual-only runtime must retain its old input. Keep the report process network
restricted and credential-free; acquisition and root-controlled audited atomic
installation are a separate operational step. Candidate preparation is not a
standing automatic updater, deployment or change to an existing timer.

References: [official API documentation](https://twelvedata.com/docs),
[historical request parameters](https://support.twelvedata.com/en/articles/5656039-how-to-get-historical-prices),
[personal plans](https://twelvedata.com/pricing).


## Install the reviewed automatic refresh dependency

`deploy/market-report/twelve_data_rollout.py` owns only root-controlled deployment
and atomic input publication. It reuses the existing scanner/API CLI and the
existing report timer; it is not a second scheduler or an AI worker controller.
Run installation only from a clean, exact-SHA, root-owned checkout after source
CI and isolated operator acceptance. Supply the already-reviewed base service
hash; unexpected units, overrides, state, source changes or replay stop the install.

```bash
python3 -I -B deploy/market-report/twelve_data_rollout.py install \
  --source /root/private-reviewed-checkout --sha REVIEWED_COMMIT_SHA \
  --account EXISTING_NONROOT_REPORT_ACCOUNT \
  --expected-service-sha256 REVIEWED_INSTALLED_SERVICE_SHA256
```

The original manual source, venv, input, output and base unit are retained.
A root-owned versioned release is extracted from the pinned git archive. A report
service drop-in adds Requires/After on one new oneshot refresh service, without
RemainAfterExit or a second timer. The existing timer is briefly paused while
an in-flight report finishes and the change is tested, then resumed unchanged.
The first new report validates provider provenance/hash binding before success.
A startup failure attempts to restore the original input/output and unit
configuration and resume the previous timer; retain the private audit directory
and inspect any error instead of replaying the installer.

Acquisition runs as the existing nonroot report account, with systemd
LoadCredential supplying the root-held key privately for that service's lifetime.
No secret is placed in argv, inherited environment, repository or report service.
The fetch service permits Internet address families; the report service retains
its existing AF_UNIX-only profile and has no credential. Requests remain fixed
to the provider's official HTTPS host and bounded by the accepted CLI contract.

The fetch unit's sole privileged ExecStartPost uses the systemd `+` prefix to run
the fixed reviewed publisher with root filesystem access, intentionally outside
the fetch user's capability/filesystem restrictions. It accepts only the fixed
SPY/NVDA provider pair, refuses to discard supplied macro/valuation context,
snapshots the pending file into a root-held immutable temporary input, and calls
the reviewed report CLI as nonroot before atomic publication. Previous input is
fsynced before replacement; ownership/group/read permissions are preserved.
The old report remains on acquisition/publication failure because the dependent
report job does not start. This is a narrow trusted deployment boundary, not
permission to execute arbitrary generated code as root.

A private root audit directory contains the original files, metadata, installed
unit identities and receipt. To explicitly restore the prior manual pipeline:

```bash
python3 -I -B /opt/market-report/releases/REVIEWED_COMMIT_SHA/deploy/market-report/twelve_data_rollout.py rollback \
  --backup /root/PRIVATE_ROLLOUT_BACKUP
```

Rollback refuses changed base units or extra/modified overrides, retains the newer
input/report as evidence, restores the recorded manual input/output/permissions
and removes only the refresh unit and its own drop-in. It preserves whether the
timer was active at rollback entry. Old price freshness still applies; rollback
is not a download of current quotes. No credentials, raw responses or private
operational receipts belong in public git.
