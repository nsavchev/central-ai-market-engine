"""Root-controlled install/publish boundary for the existing report timer.

The API CLI owns acquisition/validation; systemd owns credentials and scheduling.
Installation requires a reviewed immutable source checkout.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time

ROOT_UID = 0
POLICY = ['MARKET_TWELVE_DATA_ENABLED=1', 'MARKET_TWELVE_DATA_PRIVATE_USE_CONFIRMED=1']


def run(command, *, cwd=None, timeout=90):
    return subprocess.check_output(command, cwd=cwd, timeout=timeout,
        text=True, stderr=subprocess.STDOUT).strip()


def trusted(path):
    resolved = path.resolve(strict=True)
    for item in (path, *path.parents, resolved, *resolved.parents):
        info = item.stat()
        if info.st_uid != ROOT_UID or info.st_mode & 0o022:
            raise ValueError('ROOT_OWNED_IMMUTABLE_CODE_REQUIRED')


def read_regular(path, limit=5_000_000, owner=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_size > limit
                or (owner is not None and info.st_uid != owner)):
            raise ValueError('BOUNDED_REGULAR_FILE_REQUIRED')
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('FILE_TOO_LARGE')
        return raw, info


def atomic(path, data, uid, gid, mode):
    fd, name = tempfile.mkstemp(prefix='.market-update-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fchown(stream.fileno(), uid, gid)
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def publish(source, python, account, state, config, runner=run):
    """Validate a root-held immutable copy before replacing the complete input."""
    identity = pwd.getpwnam(account)
    trusted(source)
    trusted(python)
    trusted(config)
    target = config / 'input.json'
    old, metadata = read_regular(target, owner=ROOT_UID)
    if metadata.st_gid != identity.pw_gid or stat.S_IMODE(metadata.st_mode) != 0o640:
        raise ValueError('INSTALLED_INPUT_METADATA_MISMATCH')
    previous = json.loads(old)
    if any(previous.get(key) is not None for key in ('macro', 'valuation')):
        raise ValueError('EXISTING_CONTEXT_REQUIRES_EXPLICIT_PRESERVATION')
    raw, _ = read_regular(state / 'pending.json', owner=identity.pw_uid)
    payload = json.loads(raw)
    if (payload.get('schema') != 'market-combined-input-v1'
            or payload.get('market_input', {}).get('schema') != 'market-provider-input-v1'
            or payload['market_input'].get('provenance', {}).get('source') != 'twelve_data'
            or any(payload.get(key) is not None for key in ('macro', 'valuation'))):
        raise ValueError('PROVIDER_PAIR_ONLY_REQUIRED')
    market = payload['market_input'].get('market', {})
    if (set(market) != {'benchmark', 'assets'} or market['benchmark'].get('symbol') != 'SPY'
            or len(market['assets']) != 1 or market['assets'][0].get('symbol') != 'NVDA'):
        raise ValueError('PROVIDER_PAIR_ONLY_REQUIRED')
    fd, name = tempfile.mkstemp(prefix='.provider-check-', dir=config)
    candidate = Path(name)
    preview = state / 'preview.json'
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fchown(stream.fileno(), ROOT_UID, identity.pw_gid)
            os.fchmod(stream.fileno(), 0o640)
            os.fsync(stream.fileno())
        runner(['/usr/sbin/runuser', '-u', account, '--', '/usr/bin/env', '-i',
            'HOME=' + str(state), 'PATH=/usr/bin:/bin', *POLICY, str(python), '-B',
            '-m', 'app.scan_cli', str(candidate), '--combined-report', '--report-asof-now',
            '--max-age-calendar-days', '3', '--output', str(preview)], cwd=source, timeout=30)
        result = json.loads(read_regular(preview, owner=identity.pw_uid)[0])
        expected = hashlib.sha256(json.dumps(payload['market_input']['market'],
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if (result.get('market_sha256') != expected
                or result.get('provenance') != payload['market_input']['provenance']
                or result.get('data_mode') != 'PROVIDER_API'
                or result.get('deployment_allowed') is not False
                or result.get('paper_trades_executed') is not False):
            raise ValueError('PREVIEW_BINDING_FAILED')
        current, current_info = read_regular(target, owner=ROOT_UID)
        if current != old or current_info.st_ino != metadata.st_ino:
            raise ValueError('ACTIVE_INPUT_CHANGED_DURING_PREVIEW')
        # Backup is durable before replacement, and retains the original metadata.
        atomic(config / 'input.previous.json', old, ROOT_UID, metadata.st_gid, 0o640)
        atomic(target, raw, ROOT_UID, metadata.st_gid, 0o640)
        print('PROVIDER_INPUT_PUBLISHED', flush=True)
    finally:
        candidate.unlink(missing_ok=True)


def units(source, python, account):
    """One dependency, no second timer; credential is only in the fetch unit."""
    if re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', account) is None:
        raise ValueError('INVALID_SERVICE_ACCOUNT')
    policy = ' '.join(POLICY)
    helper = source / 'deploy/market-report/twelve_data_rollout.py'
    refresh = f'''[Unit]
Description=Refresh the private paired daily market input
ConditionPathExists=/etc/market-report/execution.authorized

[Service]
Type=oneshot
User={account}
Group={account}
WorkingDirectory={source}
StateDirectory=market-report-refresh
StateDirectoryMode=0700
LoadCredential=twelve-data.key:/etc/market-report/twelve-data.key
ExecStartPre=/usr/bin/rm -f /var/lib/market-report-refresh/pending.json
ExecStart=/usr/bin/env -i HOME=/var/lib/market-report-refresh PATH=/usr/bin:/bin {policy} {python} -B -m app.scan_cli - --prepare-twelve-data-input --api-key-file %d/twelve-data.key --max-age-calendar-days 3 --output /var/lib/market-report-refresh/pending.json
ExecStartPost=+/usr/bin/python3 -I -B {helper} publish --source {source} --python {python} --account {account}
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/market-report-refresh
TimeoutStartSec=90
TimeoutStopSec=15
KillMode=control-group
Restart=no
'''
    dropin = f'''[Unit]
Description=Market Engine private daily report
Requires=market-report-refresh.service
After=market-report-refresh.service

[Service]
WorkingDirectory={source}
ExecStart=
ExecStart=/usr/bin/env -i HOME=/var/lib/market-report PATH=/usr/bin:/bin {policy} {python} -B -m app.scan_cli /etc/market-report/input.json --combined-report --report-asof-now --max-age-calendar-days 3 --output /var/lib/market-report/latest-report.json
'''
    return refresh.encode(), dropin.encode()


def install(checkout, expected_sha, account, expected_service_hash):
    """Reversible fixed-path rollout; original timer configuration is never edited."""
    trusted(checkout)
    if (re.fullmatch('[0-9a-f]{40}', expected_sha) is None
            or run(['git', '-C', str(checkout), 'rev-parse', 'HEAD']) != expected_sha
            or run(['git', '-C', str(checkout), 'status', '--porcelain'])):
        raise ValueError('CLEAN_PINNED_ROOT_CHECKOUT_REQUIRED')
    identity = pwd.getpwnam(account)
    if identity.pw_uid == 0:
        raise ValueError('NONROOT_REPORT_ACCOUNT_REQUIRED')
    service = Path('/etc/systemd/system/market-report.service')
    timer = Path('/etc/systemd/system/market-report.timer')
    dropdir = Path('/etc/systemd/system/market-report.service.d')
    refresh = Path('/etc/systemd/system/market-report-refresh.service')
    config = Path('/etc/market-report')
    python = Path('/opt/market-report/venv/bin/python')
    trusted(python)
    trusted(config)
    old_service = read_regular(service, owner=ROOT_UID)[0]
    if hashlib.sha256(old_service).hexdigest() != expected_service_hash:
        raise ValueError('REVIEWED_SERVICE_CHANGED')
    if dropdir.exists() or dropdir.is_symlink() or refresh.exists() or refresh.is_symlink():
        raise ValueError('EXISTING_OVERRIDE_DO_NOT_OVERWRITE')
    state = Path('/var/lib/market-report-refresh')
    if state.exists() or state.is_symlink():
        raise ValueError('EXISTING_REFRESH_STATE_DO_NOT_OVERWRITE')
    if run(['systemctl', 'is-enabled', 'market-report.timer']) != 'enabled':
        raise ValueError('EXPECTED_EXISTING_TIMER_ENABLED')
    if run(['systemctl', 'is-active', 'market-report.timer']) != 'active':
        raise ValueError('EXPECTED_EXISTING_TIMER_ACTIVE')
    old_timer = read_regular(timer, owner=ROOT_UID)[0]
    if b'08:00:00 Europe/Sofia' not in old_timer or b'23:15:00 Europe/Sofia' not in old_timer:
        raise ValueError('EXPECTED_TWO_SOFIA_SLOTS')
    old_input, input_info = read_regular(config / 'input.json', owner=ROOT_UID)
    old_report, report_info = read_regular(Path('/var/lib/market-report/latest-report.json'), owner=identity.pw_uid)
    audit = Path(tempfile.mkdtemp(prefix='market-api-rollout-', dir='/root'))
    print('ROLLOUT_BACKUP=' + str(audit), flush=True)
    for name, data in [('service.before', old_service), ('timer.before', old_timer),
            ('input.before.json', old_input), ('report.before.json', old_report)]:
        atomic(audit / name, data, ROOT_UID, 0, 0o600)
    release = Path('/opt/market-report/releases') / expected_sha
    if release.exists() or release.is_symlink():
        raise ValueError('RELEASE_ALREADY_EXISTS_DO_NOT_REPLAY')
    release.parent.mkdir(mode=0o755, exist_ok=True)
    trusted(release.parent)
    release.parent.chmod(0o755)
    release.mkdir(mode=0o755)
    archive = audit / 'source.tar'
    with archive.open('wb') as stream:
        subprocess.run(['git', '-C', str(checkout), 'archive', expected_sha], stdout=stream, check=True)
    with tarfile.open(archive) as stream:
        stream.extractall(release, filter='data')
    for path in [release, *release.rglob('*')]:
        if path.is_symlink():
            raise ValueError('SYMLINK_IN_RELEASE')
        path.chmod(0o755 if path.is_dir() else 0o644)
    refresh_data, dropin_data = units(release, python, account)
    manifest = {'account': account, 'source_sha': expected_sha,
        'input_metadata': [input_info.st_uid, input_info.st_gid, stat.S_IMODE(input_info.st_mode)],
        'report_metadata': [report_info.st_uid, report_info.st_gid, stat.S_IMODE(report_info.st_mode)],
        'refresh_sha256': hashlib.sha256(refresh_data).hexdigest(),
        'dropin_sha256': hashlib.sha256(dropin_data).hexdigest()}
    atomic(audit / 'manifest.json', json.dumps(manifest).encode(), ROOT_UID, 0, 0o600)
    paused = False
    changed = False
    try:
        run(['systemctl', 'stop', 'market-report.timer'])
        paused = True
        deadline = time.monotonic() + 70
        while run(['systemctl', 'show', 'market-report.service', '-p', 'ActiveState', '--value']) in ('activating', 'active', 'deactivating'):
            if time.monotonic() > deadline:
                raise ValueError('EXISTING_REPORT_STILL_RUNNING')
            time.sleep(1)
        # Snapshot again after any already-running scheduled job completed.
        old_report, report_info = read_regular(Path('/var/lib/market-report/latest-report.json'), owner=identity.pw_uid)
        atomic(audit / 'report.before.json', old_report, ROOT_UID, 0, 0o600)
        manifest['report_metadata'] = [report_info.st_uid, report_info.st_gid, stat.S_IMODE(report_info.st_mode)]
        atomic(audit / 'manifest.json', json.dumps(manifest).encode(), ROOT_UID, 0, 0o600)
        if read_regular(config / 'input.json', owner=ROOT_UID)[0] != old_input:
            raise ValueError('ACTIVE_INPUT_CHANGED_BEFORE_INSTALL')
        dropdir.mkdir(mode=0o755)
        dropdir.chmod(0o755)
        changed = True
        atomic(refresh, refresh_data, ROOT_UID, 0, 0o644)
        atomic(dropdir / '20-twelve-data.conf', dropin_data, ROOT_UID, 0, 0o644)
        run(['systemd-analyze', 'verify', str(refresh), str(service)])
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'start', 'market-report.service'], timeout=130)
        current = json.loads(read_regular(config / 'input.json', owner=ROOT_UID)[0])
        result = json.loads(read_regular(Path('/var/lib/market-report/latest-report.json'), owner=identity.pw_uid)[0])
        expected_market = hashlib.sha256(json.dumps(current['market_input']['market'],
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if (result.get('market_sha256') != expected_market or result.get('data_mode') != 'PROVIDER_API'
                or result.get('provenance') != current['market_input']['provenance']
                or not result.get('automated_acquisition') or result.get('deployment_allowed') is not False
                or read_regular(timer, owner=ROOT_UID)[0] != old_timer):
            raise ValueError('INSTALLED_REPORT_BINDING_FAILED')
        receipt = {'installed': True, 'source_sha': expected_sha,
            'data_mode': result['data_mode'], 'market_asof': result['relative_strength']['as_of'],
            'schedule_sofia': ['08:00', '23:15'], 'automatic_data_download': True,
            'report_sha256': hashlib.sha256(read_regular(Path('/var/lib/market-report/latest-report.json'))[0]).hexdigest()}
    except Exception:
        if changed:
            run(['systemctl', 'stop', 'market-report.service', 'market-report-refresh.service'], timeout=40)
            refresh.unlink(missing_ok=True)
            (dropdir / '20-twelve-data.conf').unlink(missing_ok=True)
            dropdir.rmdir()
            atomic(config / 'input.json', old_input, input_info.st_uid, input_info.st_gid, stat.S_IMODE(input_info.st_mode))
            atomic(Path('/var/lib/market-report/latest-report.json'), old_report,
                report_info.st_uid, report_info.st_gid, stat.S_IMODE(report_info.st_mode))
            run(['systemctl', 'daemon-reload'])
            print('PREVIOUS_RUNTIME_INPUT_AND_REPORT_RESTORED', flush=True)
        raise
    finally:
        if paused:
            run(['systemctl', 'start', 'market-report.timer'])
    if (run(['systemctl', 'is-active', 'market-report.timer']) != 'active'
            or run(['systemctl', 'is-enabled', 'market-report.timer']) != 'enabled'):
        raise ValueError('TIMER_RESUMPTION_REQUIRES_OPERATOR_ATTENTION')
    atomic(audit / 'receipt.json', json.dumps(receipt, indent=2).encode(), ROOT_UID, 0, 0o600)
    print(json.dumps(receipt, indent=2), flush=True)
    print('MARKET_REPORT_AUTOMATIC_REFRESH_INSTALLED', flush=True)


def rollback(audit):
    """Restore the recorded manual runtime without discarding newer evidence."""
    trusted(audit)
    if (audit / 'rollback.json').exists():
        raise ValueError('ROLLBACK_ALREADY_COMPLETED')
    manifest = json.loads(read_regular(audit / 'manifest.json', owner=ROOT_UID)[0])
    refresh = Path('/etc/systemd/system/market-report-refresh.service')
    dropin = Path('/etc/systemd/system/market-report.service.d/20-twelve-data.conf')
    if sorted(path.name for path in dropin.parent.iterdir()) != [dropin.name]:
        raise ValueError('ADDITIONAL_OVERRIDE_REQUIRES_REVIEW')
    for installed, backup in [('market-report.service', 'service.before'), ('market-report.timer', 'timer.before')]:
        if read_regular(Path('/etc/systemd/system') / installed, owner=ROOT_UID)[0] != read_regular(audit / backup, owner=ROOT_UID)[0]:
            raise ValueError('BASE_UNIT_CHANGED_REQUIRES_REVIEW')
    for path, key in [(refresh, 'refresh_sha256'), (dropin, 'dropin_sha256')]:
        if hashlib.sha256(read_regular(path, owner=ROOT_UID)[0]).hexdigest() != manifest[key]:
            raise ValueError('INSTALLED_OVERRIDE_CHANGED_REVIEW_BEFORE_ROLLBACK')
    old_input = read_regular(audit / 'input.before.json', owner=ROOT_UID)[0]
    old_report = read_regular(audit / 'report.before.json', owner=ROOT_UID)[0]
    was_active = run(['systemctl', 'show', 'market-report.timer', '-p', 'ActiveState', '--value']) == 'active'
    run(['systemctl', 'stop', 'market-report.timer'])
    try:
        run(['systemctl', 'stop', 'market-report.service', 'market-report-refresh.service'], timeout=40)
        target = Path('/etc/market-report/input.json')
        report = Path('/var/lib/market-report/latest-report.json')
        for name, path in [('rollback-current-input.json', target), ('rollback-current-report.json', report)]:
            atomic(audit / name, read_regular(path)[0], ROOT_UID, 0, 0o600)
        refresh.unlink()
        dropin.unlink()
        dropin.parent.rmdir()
        atomic(target, old_input, *manifest['input_metadata'])
        atomic(report, old_report, *manifest['report_metadata'])
        run(['systemctl', 'daemon-reload'])
        atomic(audit / 'rollback.json', json.dumps({'restored': True,
            'newer_evidence_retained': True, 'timer_was_active': was_active}).encode(), ROOT_UID, 0, 0o600)
    finally:
        if was_active:
            run(['systemctl', 'start', 'market-report.timer'])
    print('PREVIOUS_MANUAL_REPORT_RUNTIME_RESTORED', flush=True)


def main():
    os.umask(0o077)
    if os.geteuid() != ROOT_UID:
        raise PermissionError('ROOT_CONTROLLED_OPERATION_REQUIRED')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['publish', 'install', 'rollback'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--python', type=Path, default=Path('/opt/market-report/venv/bin/python'))
    parser.add_argument('--account')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--sha')
    parser.add_argument('--expected-service-sha256')
    args = parser.parse_args()
    if args.mode in ('install', 'publish') and (args.source is None or args.account is None):
        parser.error('Install/publish requires source and account')
    lockfile = Path('/etc/market-report') / ('.api-refresh.lock' if args.mode == 'publish' else '.api-install.lock')
    fd = os.open(lockfile, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != ROOT_UID
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError('REGULAR_LOCK_REQUIRED')
        # Separate locks allow install to start its own serialized publisher.
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.mode == 'publish':
            publish(args.source, args.python, args.account,
                Path('/var/lib/market-report-refresh'), Path('/etc/market-report'))
        else:
            if args.mode == 'rollback':
                if args.backup is None:
                    parser.error('Rollback requires the private rollout backup directory')
                rollback(args.backup)
                return
            if args.sha is None or args.expected_service_sha256 is None:
                parser.error('Installation requires exact source and reviewed service hashes')
            install(args.source, args.sha, args.account, args.expected_service_sha256)


if __name__ == '__main__':
    main()
