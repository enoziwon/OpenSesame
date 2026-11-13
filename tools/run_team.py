"""정답 파일의 원재료명을 팀 1차 파이프라인(팀 파서 + 팀 분류기 + 팀 합치기)에 넣어 응답 파일을 만든다.

    python tools/run_team.py --gold data/raw/gold/dev.jsonl --out data/raw/eval/team_mock_dev.jsonl --classifier mock
    python tools/run_team.py --gold data/raw/gold/dev.jsonl --out data/raw/eval/team_llm_box_dev.jsonl --classifier llm --with-box

- src/pipeline.py의 analyze를 고치지 않고 쓴다. 사진 대신 받은 글자를 그대로 돌려주는 OCR 대역(name="text")을 넘긴다.
- 팀 파이프라인은 표시란을 따로 다루지 않는다. --with-box면 원재료명 뒤에 ", 밀, 대두 함유"처럼 표시란을 붙이고,
  없으면 원재료명만 넣는다. 표시란 항목이 없는 제품은 둘 다 원재료명만 들어간다.
- --classifier llm은 팀원이 자기 키로 돌린다(.env 또는 환경 변수의 LLM_API_KEY). 키는 어디에도 찍지 않는다.
- 팀 파이프라인은 분류에 실패하면 경고만 남기고 알레르기를 비운다. 그런 제품은 모든 알레르기가 absent로 채점되므로
  건수와 id를 알리고 1로 끝난다(파일은 만든다).
- 화면에는 건수와 시간만 찍는다. 원재료 글자는 찍지 않는다(시험 세트 보호).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # python tools/run_team.py 로 실행해도 src를 찾게 한다

from src.common.schema import OcrResult  # noqa: E402
from src.final.eval import EvalInputError, load_gold  # noqa: E402

FAIL_PREFIX = "분류 실패"              # 팀 파이프라인이 분류기 예외를 경고로 바꿀 때 쓰는 말 (src/pipeline.py)


class TextOcr:
    """OCR 대역: 받은 바이트(UTF-8 글자)를 그대로 돌려준다."""

    name = "text"

    def read_text(self, image, content_type):
        return OcrResult(text=image.decode("utf-8"), engine=self.name, confidence=None)


def team_text(product, with_box):
    """팀 파이프라인에 넣을 글자. with_box면 표시란을 '…, 밀, 대두 함유'로 붙인다."""
    if with_box and product.declared:
        return product.ingredients_text + ", " + ", ".join(product.declared) + " 함유"
    return product.ingredients_text


def load_dotenv(path):
    """팀 서버(src/app/main.py)와 같은 방식으로 .env를 읽는다. 이미 있는 환경 변수는 덮어쓰지 않고, 값은 찍지 않는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_classifier(name):
    """팀 분류기를 만든다. llm이면 .env를 먼저 읽는다."""
    from src.model import get_classifier

    if name == "llm":
        load_dotenv(ROOT / ".env")
    try:
        return get_classifier(name)
    except (ImportError, RuntimeError, ValueError) as e:
        raise SystemExit(f"분류기 {name}을(를) 준비하지 못함: {type(e).__name__}: {e}") from e


def run(products, classifier, with_box, out):
    """제품마다 팀 analyze를 불러 한 줄씩 쓴다. (처리 시간 목록, 분류 실패 id 목록)을 돌려준다."""
    from src.pipeline import analyze

    ocr = TextOcr()
    part = out.with_name(out.name + ".part")
    times, failed = [], []
    with open(part, "w", encoding="utf-8") as f:
        for i, p in enumerate(products, 1):
            image = team_text(p, with_box).encode("utf-8")
            try:
                start = time.perf_counter()
                res = analyze(image, "text/plain", ocr=ocr, classifier=classifier)
                ms = (time.perf_counter() - start) * 1000
            except Exception as e:     # 원재료 글자가 섞일 수 있어 오류 내용은 찍지 않는다
                raise SystemExit(f"{p.id}에서 실패: {type(e).__name__}. 쓰다 만 파일: {part}") from e
            if any(w.startswith(FAIL_PREFIX) for w in res.warnings):
                failed.append(p.id)
            f.write(json.dumps({"id": p.id, "response": res.model_dump(mode="json"), "ms": round(ms, 3)},
                               ensure_ascii=False) + "\n")
            f.flush()
            times.append(ms)
            if i % 10 == 0:
                print(f"  {i}/{len(products)}", file=sys.stderr, flush=True)
    part.replace(out)
    return times, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description="정답 파일의 입력을 팀 1차 파이프라인에 넣어 응답 JSONL을 만든다.")
    ap.add_argument("--gold", required=True, help="정답 JSONL (빈 정답 *_blank.jsonl도 된다)")
    ap.add_argument("--out", required=True, help="응답 JSONL 경로 (예: data/raw/eval/team_mock_dev.jsonl)")
    ap.add_argument("--classifier", choices=("mock", "llm"), default="mock", help="팀 분류기 (기본 mock)")
    ap.add_argument("--with-box", action="store_true", help="원재료명 뒤에 표시란을 '…, 밀, 대두 함유'로 붙인다")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.resolve() == Path(args.gold).resolve():
        print("오류: --out이 --gold와 같은 파일이다", file=sys.stderr)
        return 2
    try:
        gold = load_gold(args.gold)
    except (OSError, EvalInputError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    classifier = load_classifier(args.classifier)
    out.parent.mkdir(parents=True, exist_ok=True)
    times, failed = run(gold.products, classifier, args.with_box, out)
    box = "표시란 붙임" if args.with_box else "원재료명만"
    print(f"{len(times)}개 제품 -> {out} (분류기 {args.classifier}, {box}, 제품당 평균 {sum(times) / len(times):.2f} ms)")
    if failed:
        print(f"분류 실패 {len(failed)}개: {', '.join(failed[:10])}{' …' if len(failed) > 10 else ''}. "
              "이 제품들은 모든 알레르기가 absent로 채점된다. 다시 돌릴 것을 권한다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
