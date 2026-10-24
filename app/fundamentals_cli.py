"""Offline calculator; does not download any market data."""
import argparse, json
from pathlib import Path
from .fundamentals import Financials, calculate
from .sources import validate_source

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('--output',default='fundamentals_report.json')
    args=parser.parse_args()
    financials=Financials.model_validate_json(Path(args.input).read_text())
    validate_source(financials.source)
    Path(args.output).write_text(json.dumps(calculate(financials),indent=2,ensure_ascii=False))
    print(f'Wrote {args.output}')

if __name__=='__main__': main()
