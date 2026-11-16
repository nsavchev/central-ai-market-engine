"""Prepare a private review; applying requires a separate explicit operator action.

No provider/key, worker, service, task grant or ledger copy is created here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from central_ai.task_storage import TaskStorage
from central_ai.verifier_gate import read_private_host_file


def prepare(database, proposal, *, expected_history_sha256, new_call_limit, amendment_id):
    database, proposal = Path(database), Path(proposal)
    parent = proposal.parent
    if (not proposal.is_absolute() or parent.resolve() != parent or not parent.is_dir()
            or parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077
            or proposal.is_relative_to(database.parent)):
        raise ValueError('PRIVATE_REVIEW_OUTSIDE_LEDGER_REQUIRED')
    amendment = TaskStorage.prepare_generation_budget_amendment(database,
        expected_history_sha256=expected_history_sha256,
        new_call_limit=new_call_limit, amendment_id=amendment_id)
    review = dict(schema='operator-generation-budget-review-v1', database=str(database),
        purpose='bounded-project-relative-performance-trial', execution_authorized=False,
        amendment=amendment, provider_request_sent=False, worker_activated=False)
    raw = (json.dumps(review, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    fd = os.open(proposal, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        proposal.unlink(missing_ok=True)
        raise
    return dict(prepared=True, ledger_changed=False, provider_request_sent=False, worker_activated=False,
        proposal_file=str(proposal), proposal_sha256=hashlib.sha256(raw).hexdigest(),
        budget_period=amendment['budget_period'], used_calls=amendment['expected_used_calls'],
        previous_call_limit=amendment['previous_call_limit'], proposed_call_limit=amendment['new_call_limit'],
        budget_limit_microusd=amendment['budget_limit_microusd'], model=amendment['model'],
        max_output_tokens=amendment['max_output_tokens'])


def apply(database, proposal, *, approved, expected_review_sha256):
    if approved is not True:
        raise ValueError('EXPLICIT_OPERATOR_BUDGET_APPROVAL_REQUIRED')
    database, proposal = Path(database), Path(proposal)
    if proposal.is_relative_to(database.parent):
        raise ValueError('PRIVATE_REVIEW_OUTSIDE_LEDGER_REQUIRED')
    raw = read_private_host_file(proposal, max_bytes=65536)
    if hashlib.sha256(raw).hexdigest() != expected_review_sha256:
        raise ValueError('REVIEW_FILE_CHANGED')
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_REVIEW_FIELD')
            result[key] = value
        return result
    review = json.loads(raw, object_pairs_hook=unique)
    if (not isinstance(review, dict) or set(review) != {'schema', 'database', 'purpose',
            'execution_authorized', 'amendment', 'provider_request_sent', 'worker_activated'}
            or review['schema'] != 'operator-generation-budget-review-v1'
            or review['database'] != str(database)
            or review['purpose'] != 'bounded-project-relative-performance-trial'
            or review['execution_authorized'] is not False
            or review['provider_request_sent'] is not False or review['worker_activated'] is not False):
        raise ValueError('INVALID_OPERATOR_REVIEW')
    amendment = review['amendment']
    TaskStorage._validated_budget_amendment(amendment, authorized=False)
    # This explicit host operation grants only the recorded monthly ceiling.
    # It does not change task execution/deployment flags or call any provider.
    amendment = dict(amendment, operator_authorized=True)
    return TaskStorage.record_generation_budget_amendment(database, enabled='YES', amendment=amendment)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--apply-approved', action='store_true')
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--proposal-file', type=Path, required=True)
    parser.add_argument('--expected-history-sha256')
    parser.add_argument('--expected-review-sha256')
    parser.add_argument('--new-call-limit', type=int)
    parser.add_argument('--amendment-id')
    args = parser.parse_args()
    if args.prepare:
        if args.expected_history_sha256 is None or args.new_call_limit is None or args.amendment_id is None:
            parser.error('Preparation requires exact history, new-call-limit and amendment-id')
        result = prepare(args.database, args.proposal_file, expected_history_sha256=args.expected_history_sha256,
            new_call_limit=args.new_call_limit, amendment_id=args.amendment_id)
    else:
        if args.expected_review_sha256 is None:
            parser.error('Apply requires the exact previously reviewed file hash')
        result = apply(args.database, args.proposal_file, approved=True,
            expected_review_sha256=args.expected_review_sha256)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
