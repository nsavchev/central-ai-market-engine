import argparse
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]

BASELINE = Path(
    "/opt/central-ai/trust-baseline/v2.sha256"
)

VERIFIER = BASE / (
    "developer_agent/v3/"
    "trusted_verifier_v2/verifier.py"
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=["workflow"],
        required=True,
    )
    args = parser.parse_args()

    if not BASELINE.is_file():
        print("BASELINE_MISSING")
        return 1

    check = subprocess.run(
        ["sha256sum", "-c", str(BASELINE)],
        cwd=BASE,
        capture_output=True,
        text=True,
        check=False,
    )

    if check.returncode != 0:
        print("INTEGRITY_CHECK_FAILED")
        print(check.stdout)
        print(check.stderr)
        return 1

    print("INTEGRITY_CHECK_PASSED", flush=True)

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(VERIFIER),
            "--suite",
            args.suite,
        ],
        cwd=BASE,
        check=False,
    )

    return result.returncode

if __name__ == "__main__":
    sys.exit(main())
