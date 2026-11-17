"""라벨 사진 세트(EXP-003)의 글자를 최종본이나 팀 1차 파이프라인에 넣어 응답 파일을 만든다.

    python tools/run_photo.py --system final --cond clean --out data/raw/eval/photo/final_clean.jsonl
    python tools/run_photo.py --system final --cond clova --out data/raw/eval/photo/final_clova.jsonl
    python tools/run_photo.py --system team --classifier llm --cond clean --out data/raw/eval/photo/team_llm_clean.jsonl
    python tools/run_photo.py --system team --classifier llm --cond clova --out data/raw/eval/photo/team_llm_clova.jsonl

- 입력은 민재 님 EXP-003 폴더(`experiments/EXP-003`)의 사진별 글자다.
  clean = 사람이 사진을 보고 옮겨 적은 정답 전사(`gold/pNN.txt`),
  clova = CLOVA OCR에 사진 전체를 넣어 원재료명 칸을 자동으로 뽑은 결과(`results/clova_full/pNN.txt`). 서버의 OPENSESAME_OCR=clova가 넘기는 글자와 같다.
  저장된 결과를 쓰므로 CLOVA를 다시 부르지 않는다.
- 두 시스템 모두 글자 전체를 한 덩어리로 받는다. 원재료명과 '○○ 함유' 줄을 나누는 일은 각 시스템의 파서가 한다.
- 팀 1차는 src/pipeline.py의 analyze를 고치지 않고 부른다. --classifier llm이면 저장소 .env의 LLM 설정을 읽는다. 키는 찍지 않는다.
- 출력 한 줄: {"id": "photo_pNN", "response": 응답 JSON, "ms": 처리 시간}. 화면에는 건수와 시간만 찍는다.
- 다른 사진 세트: --exp-dir experiments/EXP-006 --pattern 'B_test_*.txt'. 파일 이름에 '_'가 있으면 그대로 id로 쓴다(B_test_085).
- --resume, --limit은 tools/run_team.py와 같다(이어서 돌리기, 이번에 새로 돌릴 개수). 끝날 때 값도 같다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_team  # noqa: E402

FILES = {"clean": "gold", "clova": "results/clova_full"}
FAIL_PREFIX = run_team.FAIL_PREFIX


def photo_id(stem: str) -> str:
    """EXP-003의 p01은 photo_p01, 시험 세트 제품을 찍은 B_test_085는 그대로."""
    return stem if "_" in stem else f"photo_{stem}"


def load_texts(exp_dir: Path, cond: str, pattern: str = "p*.txt") -> list:
    """(id, 글자) 목록. 파일 이름 순서."""
    folder = exp_dir / FILES[cond]
    paths = sorted(folder.glob(pattern))
    if not paths:
        raise SystemExit(f"입력 글자가 없다: {folder}/{pattern}")
    return [(photo_id(p.stem), p.read_text(encoding="utf-8")) for p in paths]


def load_dotenv(path: Path) -> None:
    """이미 있는 환경 변수는 덮어쓰지 않고, 값은 찍지 않는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


class TextOcr:
    """OCR 대역: 받은 바이트(UTF-8 글자)를 그대로 돌려준다."""

    def __init__(self, name: str):
        self.name = name

    def read_text(self, image, content_type):
        from src.common.schema import OcrResult

        return OcrResult(text=image.decode("utf-8"), engine=self.name, confidence=None)


def make_runner(system: str, classifier_name: str, engine: str):
    """(글자 하나를 받아 응답 dict를 돌려주는 함수, 분류기 또는 None)."""
    if system == "final":
        from src.final.pipeline import analyze_text

        return (lambda text: analyze_text(text, ocr_engine=engine).model_dump(mode="json")), None
    from src.model import get_classifier
    from src.pipeline import analyze

    if classifier_name == "llm":
        load_dotenv(ROOT / ".env")
    try:
        classifier = get_classifier(classifier_name)
    except (ImportError, RuntimeError, ValueError) as e:
        raise SystemExit(f"분류기 {classifier_name}을(를) 준비하지 못함: {type(e).__name__}: {e}") from e
    if classifier_name == "llm":   # 게이트웨이 거절에 대비한 다시 보내기 (run_team.py와 같음)
        classifier = run_team.RetryingClassifier(classifier)
    ocr = TextOcr(engine)
    return (lambda text: analyze(text.encode("utf-8"), "text/plain", ocr=ocr, classifier=classifier).model_dump(mode="json")), classifier


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="라벨 사진 세트의 글자를 시스템에 넣어 응답 JSONL을 만든다.")
    ap.add_argument("--system", choices=("final", "team"), required=True)
    ap.add_argument("--classifier", choices=("mock", "llm"), default="mock", help="팀 1차의 분류기 (final이면 쓰지 않음)")
    ap.add_argument("--cond", choices=tuple(FILES), required=True, help="clean = 정답 전사, clova = CLOVA OCR 결과")
    ap.add_argument("--out", required=True)
    ap.add_argument("--exp-dir", default=str(ROOT / "experiments" / "EXP-003"))
    ap.add_argument("--pattern", default="p*.txt", help="글자 파일 이름 (EXP-006는 'B_test_*.txt')")
    ap.add_argument("--resume", action="store_true", help="이미 쓴 사진은 건너뛰고 이어서 돈다 (분류 실패 줄은 다시)")
    ap.add_argument("--limit", type=int, help="이번에 새로 돌릴 최대 사진 수 (LLM 호출 수를 정할 때)")
    args = ap.parse_args(argv)
    texts = load_texts(Path(args.exp_dir), args.cond, args.pattern)
    run, classifier = make_runner(args.system, args.classifier, "transcript" if args.cond == "clean" else "clova")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    times, failed, remaining = run_team.run_items(texts, run, out, resume=args.resume, limit=args.limit,
                                                  classifier=classifier)
    label = args.system if args.system == "final" else f"team/{args.classifier}"
    speed = f"장당 평균 {sum(times) / len(times):.1f} ms" if times else "새로 돈 사진 없음"
    where = out if remaining == 0 else out.with_name(out.name + ".part")
    print(f"{len(times)}장 새로 돌림 -> {where} ({label}, {args.cond}, {speed})")
    if failed:
        print(f"분류 실패 {len(failed)}장: {', '.join(failed)}. --resume으로 다시 돌릴 것을 권한다.", file=sys.stderr)
        return 1
    if remaining:
        print(f"남은 사진 {remaining}장. 같은 명령에 --resume을 붙여 이어서 돌린다.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
