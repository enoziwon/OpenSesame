"""OpenSesame 서버.

실행 (저장소 루트에서):
    uvicorn src.app.main:app --reload

- POST /analyze : 라벨 사진 하나를 받아 9개 알레르겐 판정을 돌려준다.
  사용자 알레르기 프로필은 받지 않는다. 대조는 브라우저에서 한다.
- 사진은 메모리에서만 처리하고 저장하거나 로그에 남기지 않는다.
- OPENSESAME_OCR / OPENSESAME_CLASSIFIER 가 mock 이면 가짜 응답(프론트 개발용).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware


def _load_dotenv(path: Path) -> None:
    """의존성 없이 .env를 읽는다. 이미 설정된 환경 변수는 덮어쓰지 않는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.common.schema import AnalyzeResponse  # noqa: E402
from src.model import get_classifier  # noqa: E402
from src.ocr import get_ocr  # noqa: E402
from src.pipeline import analyze  # noqa: E402

MAX_BYTES = 10 * 1024 * 1024

app = FastAPI(title="OpenSesame", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_ocr = get_ocr()
_classifier = get_classifier()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "ocr": _ocr.name, "classifier": _classifier.name}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_label(file: UploadFile = File(...)) -> AnalyzeResponse:
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 받습니다.")
    image = await file.read(MAX_BYTES + 1)
    if len(image) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="사진이 10MB를 넘습니다.")
    if not image:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    return analyze(image, content_type, ocr=_ocr, classifier=_classifier)
