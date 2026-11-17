"""OpenSesame 최종본 서버 (LLM 없이 파서 + 원재료 사전 + 표시란 규칙).

실행 (저장소 루트에서):
    uvicorn src.final.app:app --port 8001

- GET  /health        : 상태
- POST /analyze       : 라벨 사진 하나 -> 팀 OCR(src.ocr.get_ocr)로 글자를 읽어 판정
- POST /analyze-text  : {"text": "..."} 또는 {"ingredients": "...", "declaration": "..."} -> 판정
응답은 팀 형식(src/common/schema.py)을 넓힌 src/final/response.py의 형식이다.
사용자 알레르기 프로필은 받지 않는다. 사진·글자는 메모리에서만 처리하고 저장하거나 로그에 남기지 않는다.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StrictStr, model_validator


def _load_dotenv(path: Path) -> None:
    """의존성 없이 .env를 읽는다. 이미 설정된 환경 변수는 덮어쓰지 않는다 (팀 src/app/main.py와 같은 방식)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.final.lexicon import kr_box  # noqa: E402
from src.final.parser import MAX_CHARS  # noqa: E402
from src.final.pipeline import CLASSIFIER_NAME, analyze_fields, analyze_text  # noqa: E402
from src.final.response import FinalAnalyzeResponse  # noqa: E402
from src.ocr import get_ocr  # noqa: E402

MAX_BYTES = 10 * 1024 * 1024

app = FastAPI(title="OpenSesame 최종본", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_ocr = get_ocr()
kr_box()          # 사전 표를 미리 읽어 첫 요청도 빠르게 한다


class TextRequest(BaseModel):
    """글자 입력. text(라벨 글자 전체) 하나, 또는 ingredients(원재료명)와 declaration(표시란)."""

    text: Optional[StrictStr] = Field(None, max_length=MAX_CHARS)
    ingredients: Optional[StrictStr] = Field(None, max_length=MAX_CHARS)
    declaration: Optional[StrictStr] = Field(None, max_length=MAX_CHARS)

    @model_validator(mode="after")
    def _one_input(self) -> TextRequest:
        has_text = bool(self.text and self.text.strip())
        has_fields = bool(self.ingredients and self.ingredients.strip())
        if has_text == has_fields:
            raise ValueError("text와 ingredients 중 하나만 넣어 주세요")
        if has_text and self.declaration is not None:
            raise ValueError("declaration은 ingredients와 함께만 씁니다")
        return self


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "ocr": _ocr.name, "classifier": CLASSIFIER_NAME}


@app.post("/analyze", response_model=FinalAnalyzeResponse)
def analyze_label(file: UploadFile = File(...)) -> FinalAnalyzeResponse:
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 받습니다.")
    image = file.file.read(MAX_BYTES + 1)
    if len(image) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="사진이 10MB를 넘습니다.")
    if not image:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    try:
        ocr_result = _ocr.read_text(image, content_type)
    except Exception as e:  # OCR 장애: 무엇을 읽었는지 단정하지 않는다
        raise HTTPException(status_code=502, detail="글자를 읽지 못했습니다. 잠시 뒤 다시 시도해 주세요.") from e
    try:
        return analyze_text(ocr_result.text, ocr_engine=_ocr.name)
    except (TypeError, ValueError) as e:     # 읽은 글자가 너무 길거나 글자가 아님
        raise HTTPException(status_code=422, detail=str(e)) from e


@app.post("/analyze-text", response_model=FinalAnalyzeResponse)
def analyze_label_text(req: TextRequest) -> FinalAnalyzeResponse:
    if req.text is not None and req.text.strip():
        return analyze_text(req.text)
    return analyze_fields(req.ingredients, req.declaration)
