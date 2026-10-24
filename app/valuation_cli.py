import argparse,json
from pathlib import Path
from .valuation import ValuationRequest,evaluate

def main():
    p=argparse.ArgumentParser(description='Offline scenario DCF valuation (explicit inputs only)')
    p.add_argument('input')
    p.add_argument('--output')
    args=p.parse_args()
    result=evaluate(ValuationRequest.model_validate_json(Path(args.input).read_text(encoding='utf-8')))
    output=json.dumps(result,indent=2,ensure_ascii=False)
    if args.output: Path(args.output).write_text(output+'\n',encoding='utf-8')
    else: print(output)
if __name__=='__main__': main()
