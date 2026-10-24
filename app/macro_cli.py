import argparse, json
from datetime import datetime
from pathlib import Path
from app.macro import Event, evaluate

def main():
    p=argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--output",default="macro_report.json")
    p.add_argument("--asof",default=None)
    a=p.parse_args()
    raw=json.loads(Path(a.input).read_text(encoding="utf-8"))
    result=evaluate([Event.model_validate(e) for e in raw["events"]],datetime.fromisoformat(a.asof) if a.asof else None)
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(a.output)
if __name__=="__main__": main()
