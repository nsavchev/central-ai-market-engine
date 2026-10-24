"""Usage: python -m app.quality_cli data/demo_quality.json --output quality_report.json"""
import argparse, json
from pathlib import Path
from .data_quality import check_snapshot

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('--output',default='quality_report.json')
    args=parser.parse_args()
    raw=json.loads(Path(args.input).read_text(encoding='utf-8'))
    rows=raw if isinstance(raw,list) else [raw]
    results=[check_snapshot(row) for row in rows]
    Path(args.output).write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'Checked {len(results)} snapshots; blocked {sum(r["status"]=="blocked" for r in results)}')
if __name__=='__main__': main()
