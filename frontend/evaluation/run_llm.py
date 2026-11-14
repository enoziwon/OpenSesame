"""루트에서 python -m frontend.evaluation.run_llm (OCR 제외 전사 평가)."""
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from src.parser import parse, flatten
from src.pipeline import validate, aggregate
from .metrics import evaluate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()
    os.environ.setdefault("LLM_PROVIDER", "openai")
    os.environ.setdefault("LLM_BASE_URL", "https://api.baze.co/v1/gateway")
    if not os.getenv("LLM_API_KEY") or not os.getenv("LLM_MODEL"):
        raise SystemExit("LLM_API_KEY / LLM_MODEL missing (no calls made)")
    spec = importlib.util.spec_from_file_location("gateway_pr7", HERE / "gateway_pr7.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PROMPT_PATH = ROOT / "src/model/prompts/classify_v1.txt"
    classifier = module.LLMClassifier.from_env()
    gold = json.loads((HERE / "local/jaewon/pilot-10.draft.json").read_text(encoding="utf-8"))
    # gold 판정·한국 표시란·검수 메모는 전송하지 않는다.
    inputs = [{"id": r["id"], "ingredients": flatten(parse(r["ingredients_text"]))} for r in gold]
    output = HERE / "local" / datetime.now(timezone.utc).strftime("llm-run-%Y%m%dT%H%M%S%fZ")
    output.mkdir()

    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save("inputs.json", inputs)
    save("metadata.json", {"model": classifier.model, "prompt_version": classifier.prompt_version,
        "gateway_commit": "630ec8d9d52c00b6f902a3870e6a0357eb0e8d38", "input": "manual_transcription",
        "gold_status": "user_reviewed_AI_assisted_not_cross_reviewed"})
    predictions = []
    for record in inputs:
        try:
            checked, warnings = validate(record["ingredients"], classifier.classify(record["ingredients"]))
            allergens, unknown = aggregate(checked)
        except Exception as error:
            save("failure.json", {"id": record["id"], "error_type": type(error).__name__})
            raise SystemExit(f"{record['id']}: {type(error).__name__}; stopped without scoring failed requests")
        predictions.append({"id": record["id"], "allergens": [a.model_dump(mode="json") for a in allergens],
            "warnings": warnings, "undecidable_ingredients": unknown})
        save("predictions.json", predictions)
        print(f"{record['id']}: completed", flush=True)
    save("report.json", evaluate(gold, predictions))
    print(f"Saved: {output.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
