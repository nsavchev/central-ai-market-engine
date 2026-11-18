"""Offline CLI for testing v0.6 without PostgreSQL (SQLite file or in-memory)."""
import argparse, json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from .db import Base
from .fundamentals import Financials
from .fundamentals_history import store_snapshot, history_report, validate_history_snapshot

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input', help='JSON list of financial snapshots')
    parser.add_argument('--database',default='sqlite:///financial_history_demo.db')
    parser.add_argument('--output',default='history_report.json')
    args=parser.parse_args()
    data=json.load(open(args.input,encoding='utf-8'))
    items=[Financials.model_validate(x) for x in data]
    if not items: raise ValueError('No records')
    # Reject bad metadata/permissions before creating the demo database/schema.
    for item in items: validate_history_snapshot(item)
    engine=create_engine(args.database)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with db.begin():
            for item in items: store_snapshot(db,item)
            report=history_report(db,items[0].symbol,items[0].currency,items[0].source)
    with open(args.output,'w',encoding='utf-8') as f: json.dump(report,f,indent=2,ensure_ascii=False)
    print(f'Wrote {args.output} ({report["records"]} FY records)')

if __name__=='__main__': main()
