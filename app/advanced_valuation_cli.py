import argparse, json
from pathlib import Path
from app.advanced_valuation import AdvancedRequest, analyze

def main():
    p=argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--output",default="advanced_valuation_report.json")
    a=p.parse_args()
    req=AdvancedRequest.model_validate_json(Path(a.input).read_text(encoding="utf-8"))
    result=analyze(req)
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Report saved to {a.output}")
if __name__=="__main__":main()
