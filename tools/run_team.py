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
- --classifier llm이면 게이트웨이가 요청을 거절할 때(호출 한도, 일시 장애) 기다렸다가 같은 입력을 다시 보낸다.
  LLM의 답이 깨져서 난 오류는 다시 보내지 않는다. 서비스에서도 실패로 처리되기 때문이다.
- 크레딧을 아껴 쓰기: --limit N이면 이번에 새로 N개만 돌리고, --resume이면 이미 쓴 제품은 건너뛰고 이어서 돈다.
  402(크레딧 부족)로 멈췄을 때 다른 키로 같은 명령에 --resume을 붙이면 그 제품부터 다시 돈다. 분류 실패 줄은 다시 돈다.
  --ids 파일을 주면 거기 적힌 제품만 돈다.
- 끝날 때 값: 0 다 끝남, 1 분류 실패가 있음, 2 입력 오류, 3 --limit 때문에 남은 제품이 있음(쓰다 만 파일은 .part).
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


RETRY_MODULES = ("openai", "anthropic", "httpx")   # 게이트웨이·네트워크 쪽 오류만 다시 보낸다
NO_RETRY_CODES = {400, 401, 402, 403, 404, 422}     # 기다려도 풀리지 않는 거절 (402는 크레딧 부족)


class RetryingClassifier:
    """게이트웨이가 요청을 거절하면(호출 한도, 일시 장애) 기다렸다가 같은 입력을 다시 보낸다.

    LLM의 답이 깨져서 난 오류(파싱 실패 등)는 다시 보내지 않고 그대로 올린다. 답 자체는 바꾸지 않는다.
    """

    def __init__(self, inner, retries=6, wait=15.0, max_wait=240.0, sleep=time.sleep, log=None):
        self.inner = inner
        self.name = inner.name
        self.prompt_version = getattr(inner, "prompt_version", None)
        self.retries, self.wait, self.max_wait = retries, wait, max_wait
        self.sleep = sleep
        self.log = log or (lambda msg: print(msg, file=sys.stderr, flush=True))
        self.retried = 0
        self.out_of_credit = False    # 게이트웨이가 크레딧 부족(402)으로 거절하면 참. 실행기가 보고 멈춘다

    @staticmethod
    def transient(error):
        code = getattr(error, "status_code", None)
        return type(error).__module__.split(".")[0] in RETRY_MODULES and code not in NO_RETRY_CODES

    def classify(self, ingredients):
        delay = self.wait
        for attempt in range(self.retries + 1):
            try:
                return self.inner.classify(ingredients)
            except Exception as e:
                if getattr(e, "status_code", None) == 402:
                    self.out_of_credit = True
                if attempt == self.retries or not self.transient(e):
                    raise
                code = getattr(e, "status_code", None)
                self.retried += 1
                self.log(f"  게이트웨이 거절({type(e).__name__}{' ' + str(code) if code else ''}): "
                         f"{delay:.0f}초 뒤 다시 보냄 ({attempt + 1}/{self.retries})")
                self.sleep(delay)
                delay = min(delay * 2, self.max_wait)
        raise RuntimeError("unreachable")


def load_classifier(name, retries=6):
    """팀 분류기를 만든다. llm이면 .env를 먼저 읽고, 게이트웨이 거절에 대비해 다시 보내기를 씌운다."""
    from src.model import get_classifier

    if name == "llm":
        load_dotenv(ROOT / ".env")
    try:
        clf = get_classifier(name)
    except (ImportError, RuntimeError, ValueError) as e:
        raise SystemExit(f"분류기 {name}을(를) 준비하지 못함: {type(e).__name__}: {e}") from e
    return RetryingClassifier(clf, retries=retries) if name == "llm" and retries > 0 else clf


def failed_row(row):
    return any(str(w).startswith(FAIL_PREFIX) for w in row.get("response", {}).get("warnings", []))


def read_done(out):
    """이어서 돌릴 때 남길 줄. 쓰다 만 파일(.part)이 있으면 그것을, 없으면 끝난 파일을 읽는다.
    분류 실패로 끝난 줄은 버려서 다시 돌게 한다."""
    part = out.with_name(out.name + ".part")
    src = part if part.exists() else out
    if not src.exists():
        return []
    lines = [line for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [line for line in lines if not failed_row(json.loads(line))]


def run_items(items, call, out, resume=False, limit=None, classifier=None):
    """items: [(id, 입력 글자)], call(입력) -> 응답 dict. 한 줄씩 .part에 쓰고 다 끝나면 out으로 바꾼다.

    resume이면 이미 쓴 제품을 건너뛰고, limit이면 이번에 새로 그만큼만 돈다.
    (새로 돈 처리 시간 목록, 분류 실패 id 목록, 남은 제품 수)를 돌려준다.
    """
    part = out.with_name(out.name + ".part")
    kept = read_done(out) if resume else []
    done = {json.loads(line)["id"] for line in kept}
    todo = [(pid, x) for pid, x in items if pid not in done]
    batch = todo if limit is None else todo[:max(limit, 0)]
    times, failed = [], []
    with open(part, "w", encoding="utf-8") as f:
        for line in kept:
            f.write(line + "\n")
        for i, (pid, x) in enumerate(batch, 1):
            start = time.perf_counter()
            try:
                res = call(x)
            except Exception as e:     # 원재료 글자가 섞일 수 있어 오류 내용은 찍지 않는다
                raise SystemExit(f"{pid}에서 실패: {type(e).__name__}. 쓰다 만 파일: {part} (--resume으로 이어서)") from e
            ms = (time.perf_counter() - start) * 1000
            if failed_row({"response": res}):
                failed.append(pid)
            f.write(json.dumps({"id": pid, "response": res, "ms": round(ms, 3)}, ensure_ascii=False) + "\n")
            f.flush()
            times.append(ms)
            if getattr(classifier, "out_of_credit", False):
                raise SystemExit(f"게이트웨이 크레딧이 부족해 {pid}에서 멈춤(402). 다른 키로 같은 명령에 --resume을 붙이면 "
                                 f"이 제품부터 다시 돈다. 쓰다 만 파일: {part}")
            if i % 10 == 0:
                print(f"  {i}/{len(batch)}", file=sys.stderr, flush=True)
    remaining = len(todo) - len(batch)
    if remaining == 0:
        part.replace(out)
    return times, failed, remaining


def run(products, classifier, with_box, out, resume=False, limit=None):
    """제품마다 팀 analyze를 불러 한 줄씩 쓴다. (처리 시간 목록, 분류 실패 id 목록, 남은 제품 수)를 돌려준다."""
    from src.pipeline import analyze

    ocr = TextOcr()
    items = [(p.id, team_text(p, with_box)) for p in products]

    def call(text):
        return analyze(text.encode("utf-8"), "text/plain", ocr=ocr, classifier=classifier).model_dump(mode="json")

    return run_items(items, call, out, resume=resume, limit=limit, classifier=classifier)


def read_ids(path, products):
    """--ids 파일(한 줄에 id 하나)에 적힌 제품만 정답 순서대로. 모르는 id가 있으면 EvalInputError."""
    want = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    known = {p.id for p in products}
    unknown = [i for i in want if i not in known]
    if unknown:
        raise EvalInputError(f"{path}: 정답 파일에 없는 id {len(unknown)}개 ({', '.join(unknown[:5])})")
    keep = set(want)
    return [p for p in products if p.id in keep]


def main(argv=None):
    ap = argparse.ArgumentParser(description="정답 파일의 입력을 팀 1차 파이프라인에 넣어 응답 JSONL을 만든다.")
    ap.add_argument("--gold", required=True, help="정답 JSONL (빈 정답 *_blank.jsonl도 된다)")
    ap.add_argument("--out", required=True, help="응답 JSONL 경로 (예: data/raw/eval/team_mock_dev.jsonl)")
    ap.add_argument("--classifier", choices=("mock", "llm"), default="mock", help="팀 분류기 (기본 mock)")
    ap.add_argument("--with-box", action="store_true", help="원재료명 뒤에 표시란을 '…, 밀, 대두 함유'로 붙인다")
    ap.add_argument("--retries", type=int, default=6, help="게이트웨이가 거절할 때 다시 보내는 횟수 (llm만, 0이면 끔)")
    ap.add_argument("--ids", help="이 파일에 적힌 id만 돌린다 (한 줄에 하나)")
    ap.add_argument("--resume", action="store_true", help="이미 쓴 제품은 건너뛰고 이어서 돈다 (분류 실패 줄은 다시)")
    ap.add_argument("--limit", type=int, help="이번에 새로 돌릴 최대 제품 수 (LLM 호출 수를 정할 때)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.resolve() == Path(args.gold).resolve():
        print("오류: --out이 --gold와 같은 파일이다", file=sys.stderr)
        return 2
    try:
        gold = load_gold(args.gold)
        products = read_ids(args.ids, gold.products) if args.ids else list(gold.products)
    except (OSError, EvalInputError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    classifier = load_classifier(args.classifier, args.retries)
    out.parent.mkdir(parents=True, exist_ok=True)
    times, failed, remaining = run(products, classifier, args.with_box, out, resume=args.resume, limit=args.limit)
    box = "표시란 붙임" if args.with_box else "원재료명만"
    speed = f"제품당 평균 {sum(times) / len(times):.2f} ms" if times else "새로 돈 제품 없음"
    where = out if remaining == 0 else out.with_name(out.name + ".part")
    print(f"{len(times)}개 제품 새로 돌림 -> {where} (분류기 {args.classifier}, {box}, {speed})")
    if failed:
        print(f"분류 실패 {len(failed)}개: {', '.join(failed[:10])}{' …' if len(failed) > 10 else ''}. "
              "이 제품들은 모든 알레르기가 absent로 채점된다. --resume으로 다시 돌릴 것을 권한다.", file=sys.stderr)
        return 1
    if remaining:
        print(f"남은 제품 {remaining}개. 같은 명령에 --resume을 붙여 이어서 돌린다.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
