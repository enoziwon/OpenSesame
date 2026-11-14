"""frontend에서 python -m evaluation --gold gold.json --predictions predictions.json"""
import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .metrics import evaluate


def main():
    parser = argparse.ArgumentParser(description="재현율/과잉 경고율 평가 (presence_v1)")
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="생략하면 stdout에만 JSON 출력")
    args = parser.parse_args()
    try:
        gold = json.loads(args.gold.read_text(encoding="utf-8-sig"))
        predictions = json.loads(args.predictions.read_text(encoding="utf-8-sig"))
        schema_path = Path(__file__).resolve().parents[2] / "data/schema/label_record.schema.json"
        validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
        if not isinstance(gold, list):
            raise ValueError("gold는 JSON 배열이어야 합니다.")
        for i, record in enumerate(gold):
            errors = list(validator.iter_errors(record))
            if errors:
                raise ValueError(f"gold[{i}] 스키마 오류: {errors[0].message}")
        result = evaluate(gold, predictions)
        output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            if args.output.resolve() in {args.gold.resolve(), args.predictions.resolve()}:
                raise ValueError("출력 경로는 입력 파일과 달라야 합니다.")
            args.output.write_text(output + "\n", encoding="utf-8")
        print(output)
    except (OSError, ValueError) as error:
        parser.exit(2, f"평가 실패: {error}\n")


if __name__ == "__main__":
    main()
