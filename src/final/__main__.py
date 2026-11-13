"""라벨 한 장을 판정해 사람이 읽는 표와 JSON을 찍는다.

    python -m src.final "원재료명: 간장, 설탕, 대두 함유"
    python -m src.final "간장, 설탕" --declaration "대두 함유"     # 원재료명과 표시란을 따로 줄 때
    echo "원재료명: 간장, 설탕" | python -m src.final -           # 표준 입력에서 읽기
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from src.final.pipeline import analyze_fields, analyze_text
from src.final.response import FinalAnalyzeResponse

VERDICT_KO = {"confirmed": "확인됨", "inferable": "추정", "undecidable": "판정 불가"}


def table(res: FinalAnalyzeResponse) -> str:
    """알레르기마다 한 줄: 이름 | 판정 | 근거 | 이유."""
    lines = [f"원재료: {res.ingredients_text}", f"표시란: {res.declaration_text or '(찾지 못함)'}", ""]
    lines.append("알레르기 | 판정 | 근거 | 이유")
    for a in res.allergens:
        lines.append(f"{a.allergen.value} | {VERDICT_KO[a.verdict.value]} | {a.evidence_ingredient} | {a.reason_ko}")
    if not res.allergens:
        lines.append("(검출 안 됨. 안전하다는 뜻은 아니다)")
    for title, items in (("판정 불가 원재료", res.undecidable_ingredients), ("참고", res.notes),
                         ("경고", res.warnings)):
        if items:
            lines.append(f"{title}: " + " / ".join(items))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.final", description="라벨 글자 하나를 판정한다 (LLM 없음)")
    p.add_argument("text", help="라벨 글자. '-'면 표준 입력에서 읽는다. --declaration을 주면 원재료명만 넣는다")
    p.add_argument("--declaration", help="알레르기 표시란 글자 (HACCP API의 allergy처럼 따로 줄 때)")
    args = p.parse_args(argv)
    text = sys.stdin.read() if args.text == "-" else args.text
    try:
        if args.declaration is not None:
            res = analyze_fields(text, args.declaration)
        else:
            res = analyze_text(text)
    except (TypeError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    print(table(res))
    print()
    print(json.dumps(res.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
