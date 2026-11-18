"""Legacy report CLI: untrusted report files cannot authorize progress."""
import argparse

def verify_report(name):
    # Fail closed until report provenance is verified.
    raise ValueError("UNVERIFIED_REPORT_BLOCKED")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    verify_report(args.report)

if __name__ == "__main__":
    main()
