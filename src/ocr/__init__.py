"""2단계: 사진 → 원재료명 텍스트.

담당: 김민재. 실제 엔진은 이 인터페이스(read_text)를 지키는 클래스로 추가하고 get_ocr()에 등록한다.
"""
from __future__ import annotations

import os
from typing import Optional, Protocol

from src.common.schema import OcrResult


class OcrEngine(Protocol):
    name: str

    def read_text(self, image: bytes, content_type: str) -> OcrResult: ...


class MockOcr:
    """개발용. 사진과 무관하게 고정 텍스트를 돌려준다."""

    name = "mock"
    SAMPLE = (
        "원재료명: 소맥분(밀:미국산), 설탕, 식물성유지(팜유), "
        "혼합조미분말[멸치분말, 정제소금, 효모추출물], 탈지분유, 참기름 3%, "
        "간장, 대두레시틴, 향료(바닐라향)"
    )

    def read_text(self, image: bytes, content_type: str) -> OcrResult:
        return OcrResult(text=self.SAMPLE, engine=self.name, confidence=None)


def get_ocr(name: Optional[str] = None) -> OcrEngine:
    name = name or os.getenv("OPENSESAME_OCR", "mock")
    if name == "mock":
        return MockOcr()
    if name == "clova":  # 사진 10장 비교로 선정 (experiments/EXP-003-ocr-compare.md)
        from src.ocr.clova import ClovaOcr

        return ClovaOcr.from_env()
    raise ValueError(f"알 수 없는 OCR 엔진: {name}")
