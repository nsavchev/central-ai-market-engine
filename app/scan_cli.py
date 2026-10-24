import argparse
import json
from pathlib import Path
from app.scanner import scan

def main():
    parser = argparse.ArgumentParser(description='Offline market relative-strength scanner')
    parser.add_argument('input', help='JSON with dated closes')
    parser.add_argument('--output', default='scan_report.json')
    args = parser.parse_args()
    result = scan(json.loads(Path(args.input).read_text()))
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print('Saved', args.output)

if __name__ == '__main__': main()
