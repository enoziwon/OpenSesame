"""gold 파일이 스키마를 통과하는지 검사한다.

사용: python data/validate.py data/schema/example_record.json [파일 ...]
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = Path(__file__).parent / "schema" / "label_record.schema.json"


def main(paths):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    failed = 0
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else [data]
        for rec in records:
            errors = sorted(validator.iter_errors(rec), key=lambda e: list(e.path))
            for e in errors:
                failed += 1
                loc = "/".join(map(str, e.path)) or "(root)"
                print(f"[FAIL] {p} id={rec.get('id')} {loc}: {e.message}")
    if failed:
        sys.exit(1)
    print("OK: 모든 레코드가 스키마를 통과했다.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
