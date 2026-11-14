"""개발 전용: 루트에서 python -m frontend.evaluation.serve_llm."""
import importlib.util
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parents[2]
    for line in (root / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()
    path = Path(__file__).parent / "gateway_pr7.py"
    spec = importlib.util.spec_from_file_location("src.model.llm", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PROMPT_PATH = root / "src/model/prompts/classify_v1.txt"
    sys.modules["src.model.llm"] = module
    import uvicorn
    uvicorn.run("src.app.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
