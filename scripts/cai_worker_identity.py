"""Reviewed, same-filesystem identity transfer of an existing ledger and key.

Never copies/resets a ledger, creates a reviewer key, starts a worker or calls a model.
The CLI requires root. Interrupted operations retain an exclusive intent and
must be reconciled by the operator; there is no automatic crash replay.
"""
import argparse
import ctypes
import fcntl
import gc
import hashlib
import json
import os
from pathlib import Path
import pwd
import sqlite3
import stat
import subprocess

from central_ai.task_storage import TaskStorage
from central_ai.verifier_gate import read_private_host_file


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def _exchange(source,target):
    # Linux RENAME_EXCHANGE swaps the file with a precreated empty directory.
    # The old pathname is never vacant, even between syscalls or after SIGKILL.
    library=ctypes.CDLL(None,use_errno=True)
    try:rename=library.renameat2
    except AttributeError:raise ValueError('IDENTITY_ATOMIC_EXCHANGE_UNAVAILABLE') from None
    rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    rename.restype=ctypes.c_int
    if rename(-100,os.fsencode(source),-100,os.fsencode(target),2)!=0:
        error=ctypes.get_errno()
        raise OSError(error,os.strerror(error))


def _write(path, value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:
        out.write(raw);out.flush();os.fsync(out.fileno())
    _sync(path.parent)
    return hashlib.sha256(raw).hexdigest()


def _directory(path, *, private=False):
    if not path.is_absolute() or path.resolve()!=path or path.is_symlink() or not path.is_dir():
        raise ValueError('IDENTITY_DIRECTORY_INVALID')
    meta=path.stat()
    if meta.st_uid!=os.geteuid() or stat.S_IMODE(meta.st_mode) & (0o077 if private else 0o022):
        raise ValueError('IDENTITY_DIRECTORY_NOT_OPERATOR_CONTROLLED')
    return meta


def _file(path):
    _directory(path.parent,private=True)
    if not path.is_absolute() or path.resolve()!=path or path.is_symlink():
        raise ValueError('IDENTITY_SOURCE_INVALID')
    m=path.stat()
    if not stat.S_ISREG(m.st_mode) or m.st_nlink!=1 or m.st_uid!=os.geteuid():
        raise ValueError('IDENTITY_SOURCE_INVALID')
    return dict(device=m.st_dev,inode=m.st_ino,uid=m.st_uid,gid=m.st_gid,
        mode=stat.S_IMODE(m.st_mode),size=m.st_size,sha256=_digest(path))


def _process_directories():
    return Path('/proc').iterdir()


def _quiescent(database, key):
    # No SQLite sidecar is silently deleted, checkpointed or reconstructed.
    for suffix in ('-wal','-shm','-journal'):
        p=Path(str(database)+suffix)
        if p.exists() or p.is_symlink():raise ValueError('IDENTITY_SQLITE_SIDECAR_PRESENT')
    gc.collect()
    identities={(p.stat().st_dev,p.stat().st_ino) for p in (database,key)}
    for process in _process_directories():
        if not process.name.isdecimal():continue
        try:
            for fd in (process/'fd').iterdir():
                try:m=fd.stat()
                except (FileNotFoundError,ProcessLookupError):continue
                if (m.st_dev,m.st_ino) in identities:
                    raise ValueError('IDENTITY_SOURCE_OPEN_BY_PROCESS')
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError:
            # Root-owned source parents are private. A root process we cannot
            # inspect is uncertainty, never proof that the files are idle.
            try:owner=process.stat().st_uid
            except FileNotFoundError:continue
            if owner==os.geteuid():raise ValueError('IDENTITY_PROCESS_SCAN_UNCERTAIN') from None


def plan(database, reviewer_key, target_state, target_authority, account, *, expected_history_sha256, expected_policy_sha256):
    database,key,state,authority=map(Path,(database,reviewer_key,target_state,target_authority))
    person=pwd.getpwnam(account)
    if person.pw_uid<=0 or person.pw_gid<=0:raise ValueError('NONROOT_IDENTITY_REQUIRED')
    if database.parent==key.parent:raise ValueError('AUTHORITY_INSIDE_LEDGER')
    source=_file(database);secret=_file(key)
    with database.open('rb') as stream:header=stream.read(24)
    if header[:16]!=b'SQLite format 3\x00' or header[18:20]!=b'\x01\x01':
        raise ValueError('IDENTITY_ROLLBACK_JOURNAL_DATABASE_REQUIRED')
    if secret['mode'] & 0o077 or not 32<=secret['size']<=128:
        raise ValueError('PRIVATE_REVIEWER_KEY_REQUIRED')
    for target in (state,authority):
        _directory(target.parent)
        if target.exists() or target.is_symlink() or target.resolve()!=target:
            raise ValueError('IDENTITY_DESTINATION_OCCUPIED')
        if target.parent.stat().st_dev!=source['device'] or secret['device']!=source['device']:
            raise ValueError('IDENTITY_SAME_FILESYSTEM_REQUIRED')
        if any(target.is_relative_to(p) or p.is_relative_to(target) for p in (database.parent,key.parent)):
            raise ValueError('IDENTITY_PATH_OVERLAP')
    if state==authority or state.is_relative_to(authority) or authority.is_relative_to(state):
        raise ValueError('IDENTITY_PATH_OVERLAP')
    _quiescent(database,key)
    snapshot=TaskStorage.generation_budget_snapshot(database)
    if (snapshot['admission_history_sha256']!=expected_history_sha256
            or snapshot['active_policy_sha256']!=expected_policy_sha256
            or snapshot['admitted_calls']!=1 or snapshot['effective_call_limit']!=3
            or not snapshot['model_profiles_installed']):
        raise ValueError('IDENTITY_LEDGER_BASELINE_CHANGED')
    con=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=5)
    try:
        con.execute('PRAGMA query_only=ON');con.execute('BEGIN')
        if con.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('IDENTITY_DATABASE_CHECK_FAILED')
        tasks=[json.loads(row[0]) for row in con.execute('SELECT payload FROM tasks')]
        TaskStorage.check_verification_barrier(tasks)
        if any('dispatch' in t.get('generation',{}) and t['generation'].get('phase')!='completed' for t in tasks):
            raise ValueError('IDENTITY_DISPATCH_UNRESOLVED')
    finally:con.close()
    _quiescent(database,key)
    if _file(database)!=source or _file(key)!=secret:raise ValueError('IDENTITY_SOURCE_CHANGED')
    return dict(schema='cai-worker-identity-review-v1',database=str(database),reviewer_key=str(key),
        target_state=str(state),target_authority=str(authority),account=account,uid=person.pw_uid,gid=person.pw_gid,
        database_identity=source,key_identity=secret,history_sha256=expected_history_sha256,
        policy_sha256=expected_policy_sha256,execution_authorized=False,jobs={},worker_activated=False,
        old_paths_retired_with_directory_guards=True)


def prepare(proposal, **kwargs):
    proposal=Path(proposal)
    _directory(proposal.parent,private=True)
    body=plan(**kwargs)
    for p in (Path(body['database']).parent,Path(body['reviewer_key']).parent,
              Path(body['target_state']),Path(body['target_authority'])):
        if proposal.is_relative_to(p):raise ValueError('IDENTITY_REVIEW_LOCATION_INVALID')
    digest=_write(proposal,body)
    return dict(prepared=True,proposal_file=str(proposal),proposal_sha256=digest,
        target_state=body['target_state'],target_authority=body['target_authority'],uid=body['uid'],gid=body['gid'],
        used_calls=1,total_call_limit=3,ledger_changed=False,reviewer_key_regenerated=False,
        generation_request_sent=False,worker_activated=False)


def _verify_access(body):
    # Standard library only; no imports from the privileged source checkout.
    program="""import hashlib,json,os,sqlite3,sys
from pathlib import Path
p=json.loads(sys.stdin.read())
assert os.getuid()==p['uid'] and os.geteuid()==p['uid']
db=Path(p['target_state'])/Path(p['database']).name
key=Path(p['target_authority'])/Path(p['reviewer_key']).name
assert hashlib.sha256(db.read_bytes()).hexdigest()==p['database_identity']['sha256']
assert hashlib.sha256(key.read_bytes()).hexdigest()==p['key_identity']['sha256']
c=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)
try:
 c.execute('PRAGMA query_only=ON')
 assert c.execute('PRAGMA quick_check').fetchall()==[('ok',)]
finally:c.close()
print('NONROOT_RETAINED_LEDGER_ACCESS_CONFIRMED')
"""
    if os.geteuid()==0:
        cmd=['runuser','-u',body['account'],'--','env','-i','PATH=/usr/bin:/bin',
             '/usr/bin/python3','-B','-c',program]
    else:
        import sys
        cmd=[sys.executable,'-I','-B','-c',program]
    result=subprocess.run(cmd,input=json.dumps(body),text=True,capture_output=True,timeout=15)
    if result.returncode or result.stdout.strip()!='NONROOT_RETAINED_LEDGER_ACCESS_CONFIRMED':
        raise ValueError('IDENTITY_NONROOT_ACCESS_FAILED')


def apply(proposal, *, expected_review_sha256, approved):
    if approved is not True:raise ValueError('EXPLICIT_IDENTITY_TRANSFER_APPROVAL_REQUIRED')
    proposal=Path(proposal);raw=read_private_host_file(proposal,max_bytes=65536)
    if hashlib.sha256(raw).hexdigest()!=expected_review_sha256:raise ValueError('IDENTITY_REVIEW_CHANGED')
    body=json.loads(raw)
    if not isinstance(body,dict):raise ValueError('IDENTITY_REVIEW_CHANGED')
    original=Path(body['database']);key=Path(body['reviewer_key'])
    fd=os.open(original.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        current=plan(original,key,body['target_state'],body['target_authority'],body['account'],
            expected_history_sha256=body['history_sha256'],expected_policy_sha256=body['policy_sha256'])
        if current!=body:raise ValueError('IDENTITY_REVIEW_CHANGED')
        intent=proposal.parent/'identity-intent.json'
        _write(intent,dict(review_sha256=expected_review_sha256,operation='move_existing_inode_only',automatic_replay=False))
        state,authority=Path(body['target_state']),Path(body['target_authority'])
        moves=[(original,state/original.name,body['database_identity']),
               (key,authority/key.name,body['key_identity'])]
        created=[];moved=[];prepared_guards=[]
        try:
            for directory in (state,authority):directory.mkdir(mode=0o700);created.append(directory);_sync(directory.parent)
            for source,target,identity in moves:
                if source.stat().st_ino!=identity['inode'] or _digest(source)!=identity['sha256']:
                    raise ValueError('IDENTITY_SOURCE_CHANGED')
                target.mkdir(mode=0o700);prepared_guards.append(target);_sync(target.parent)
                _exchange(source,target);moved.append((source,target,identity));prepared_guards.remove(target)
                source.chmod(0o000)
                _sync(source.parent);_sync(target.parent)
                os.chmod(target,0o600);os.chown(target,body['uid'],body['gid'])
            descriptor=authority/'identity.json'
            _write(descriptor,dict(schema='cai-worker-location-v1',database=str(state/original.name),
                reviewer_key_file=str(authority/key.name),review_sha256=expected_review_sha256,
                execution_authorized=False,jobs={},worker_activated=False))
            os.chown(descriptor,body['uid'],body['gid'])
            for directory in created:os.chown(directory,body['uid'],body['gid'])
            _verify_access(body)
            snapshot=TaskStorage.generation_budget_snapshot(state/original.name)
            if snapshot['admission_history_sha256']!=body['history_sha256'] or snapshot['active_policy_sha256']!=body['policy_sha256']:
                raise ValueError('IDENTITY_TRANSFER_HISTORY_CHANGED')
            for source,target,identity in moved:
                m=target.stat()
                if (m.st_ino!=identity['inode'] or m.st_dev!=identity['device'] or _digest(target)!=identity['sha256']
                        or m.st_uid!=body['uid'] or m.st_gid!=body['gid'] or stat.S_IMODE(m.st_mode)!=0o600):
                    raise ValueError('IDENTITY_TRANSFER_FILE_CHANGED')
            result=dict(identity_transferred=True,database=str(state/original.name),
                reviewer_key_file=str(authority/key.name),history_preserved=True,same_database_inode=True,
                reviewer_key_regenerated=False,nonroot_access_confirmed=True,old_paths_retired=True,
                used_calls=snapshot['admitted_calls'],total_call_limit=snapshot['effective_call_limit'],
                generation_request_sent=False,worker_activated=False)
            _write(proposal.parent/'identity-receipt.json',result)
            return result
        except BaseException:
            # Refuse restoration if another process changed the moved ledger;
            # retained intent and artifacts then require manual reconciliation.
            try:
                for source,target,identity in moved:
                    if target.is_symlink() or target.stat().st_ino!=identity['inode'] or _digest(target)!=identity['sha256']:
                        raise ValueError('IDENTITY_ROLLBACK_UNCERTAIN')
                for source,target,identity in reversed(moved):
                    source.chmod(0o700)
                    _exchange(target,source);target.rmdir()
                    os.chown(source,identity['uid'],identity['gid']);os.chmod(source,identity['mode'])
                    _sync(source.parent);_sync(target.parent)
                for guard in prepared_guards:guard.rmdir();_sync(guard.parent)
                descriptor=authority/'identity.json'
                if descriptor.exists():descriptor.unlink()
                for directory in reversed(created):directory.rmdir();_sync(directory.parent)
                _write(proposal.parent/'identity-rollback.json',dict(restored=True,automatic_replay=False))
            except BaseException:
                raise RuntimeError('IDENTITY_TRANSFER_UNCERTAIN_RETAIN_INTENT') from None
            raise
    finally:os.close(fd)


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare',action='store_true');modes.add_argument('--apply-approved',action='store_true')
    parser.add_argument('--proposal-file',type=Path,required=True)
    for name in ('database','reviewer-key','target-state','target-authority','account','expected-history-sha256',
                 'expected-policy-sha256','expected-review-sha256'):parser.add_argument('--'+name)
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error('Identity transfer CLI requires the root operator')
    if args.prepare:
        names=['database','reviewer_key','target_state','target_authority','account','expected_history_sha256','expected_policy_sha256']
        if any(getattr(args,n) is None for n in names):parser.error('Preparation requires all source/destination/identity/baseline fields')
        result=prepare(args.proposal_file,**{n:getattr(args,n) for n in names})
    else:
        if args.expected_review_sha256 is None:parser.error('Apply requires the exact reviewed hash')
        result=apply(args.proposal_file,expected_review_sha256=args.expected_review_sha256,approved=True)
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':main()
