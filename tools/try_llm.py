"""LLM 분류기를 실제로 호출해 보는 점검 스크립트 (평가가 아니다).

사용 (저장소 루트에서):
    python tools/try_llm.py                 # 기본 원재료 목록, 3회 반복
    python tools/try_llm.py 간장 유청분말 향료 --repeat 2

확인하는 것
1. 입력한 원재료가 전부 돌아오는가 (누락)
2. 입력에 없는 원재료를 지어내는가
3. 같은 입력을 반복했을 때 답이 같은가
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT = ["정제수", "소맥분", "탈지분유", "유청분말", "카제인나트륨", "멸치분말", "어육", "새우맛분말",
           "참기름", "간장", "대두레시틴", "레시틴", "향료", "땅콩버터", "아몬드분말", "난백분", "정제소금"]


def load_dotenv(path):
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def summarize(results):
    return {r.ingredient: (sorted((m.allergen.value, m.verdict.value) for m in r.matches), r.source_unknown)
            for r in results}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ingredients", nargs="*")
    p.add_argument("--repeat", type=int, default=3)
    args = p.parse_args()
    load_dotenv(ROOT / ".env")

    from src.model.llm import LLMClassifier

    clf = LLMClassifier.from_env()
    names = args.ingredients or DEFAULT
    print(f"모델: {clf.model} / 프롬프트: {clf.prompt_version} / 원재료 {len(names)}개 / {args.repeat}회\n")

    runs = []
    for i in range(args.repeat):
        res = summarize(clf.classify(names))
        runs.append(res)
        missing = [n for n in names if n not in res]
        invented = [n for n in res if n not in names]
        print(f"[{i + 1}회] 누락 {len(missing)}개 {missing}  /  지어냄 {len(invented)}개 {invented}")

    print("\n원재료별 결과 (회차마다 다르면 ⚠)")
    for n in names:
        answers = [json.dumps(r.get(n), ensure_ascii=False) for r in runs]
        mark = "  " if len(set(answers)) == 1 else "⚠ "
        print(f"{mark}{n}: {answers[0]}" + ("" if mark == "  " else f"  ← 회차별: {answers}"))


if __name__ == "__main__":
    main()
