# 08. 서버 API와 코드 구조

형식을 바꿀 때는 제안 이슈 → 회의 합의 → [결정 0003](decisions/0003-api-contract.md) 갱신 순서를 지킨다.
형식의 원본은 `src/common/schema.py`다.

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env          # 처음 한 번
uvicorn src.app.main:app --reload --host 0.0.0.0
# http://localhost:8000/docs 에서 직접 호출해 볼 수 있다
python -m pytest -q           # 테스트
```

`.env`의 `OPENSESAME_OCR`, `OPENSESAME_CLASSIFIER`

| 값 | 의미 |
|---|---|
| `mock` | 가짜. 사진과 무관하게 고정 결과. 프론트 개발용 |
| `llm` (분류기만) | LLM 분류기. `LLM_API_KEY` 필요 |

## POST /analyze

- 요청: `multipart/form-data`, 필드 `file` 하나 (이미지, 10MB 이하)
- **알레르기 프로필은 보내지 않는다.** 서버는 9개 전부를 판정하고, 대조는 브라우저가 한다.
- 사진은 메모리에서만 처리한다. 저장·로그 없음.

응답 예시 전체: [`src/app/sample_response.json`](../src/app/sample_response.json)

```json
{
  "ingredients_text": "OCR이 읽은 원재료명 전문",
  "ingredients": [{"name": "혼합조미분말", "children": [{"name": "멸치분말", "children": []}]}],
  "allergens": [
    {"allergen": "fish", "verdict": "confirmed", "evidence_ingredient": "멸치분말", "other_evidence": []}
  ],
  "undecidable_ingredients": ["향료"],
  "warnings": [],
  "meta": {"ocr_engine": "mock", "classifier": "mock", "prompt_version": null}
}
```

| 필드 | 뜻 | 화면 처리 |
|---|---|---|
| `allergens` | 9개 중 근거가 있는 항목. 알레르겐마다 가장 강한 판정 하나 | 사용자가 고른 항목만 ⚠ 표시, 근거 원재료 함께 |
| `allergens`에 없는 항목 | 검출 안 됨 | **"Not detected"**. "Safe"라고 쓰지 않는다 |
| `undecidable_ingredients` | 무엇에서 왔는지 알 수 없는 원재료 (예: 향료) | "확인할 수 없는 원재료가 있음" 안내 |
| `warnings` | 분류 실패, 원재료를 못 읽음 등 | 비어 있지 않으면 결과를 단정하지 말 것 |

`allergen`, `verdict` 값은 gold 스키마(`data/schema/label_record.schema.json`)와 같다.

## 코드 구조

| 경로 | 단계 | 담당 | 상태 |
|---|---|---|---|
| `src/common/schema.py` | 단계 사이 형식 | 이진영 | 초안 |
| `src/ocr/` | 2. 사진 → 텍스트 | 김민재 | mock만 있음 |
| `src/parser/` | 3·4. 텍스트 → 원재료 트리 | 김민재 | 최소 버전 (원산지 분리, 오타 처리 없음) |
| `src/model/` | 5. 원재료 이름 → 알레르겐 | 이진영 → 2주차 자체 모델 | mock, LLM |
| `src/pipeline.py` | 검증·제품 단위 합치기 | 이진영 | 완료 |
| `src/app/` | 서버 | 이진영 | 완료 |
| `src/eval/` | 평가 | 최재원 | 비어 있음 |

새 OCR 엔진이나 분류기는 각 폴더 `__init__.py`의 인터페이스(`read_text`, `classify`)를 지키는 클래스로 만들고
`get_ocr()` / `get_classifier()`에 등록한다.

## LLM 분류기 원칙

- 5단계만 맡는다. 입력은 원재료 이름 목록뿐이다 (사진·프로필을 보내지 않는다).
- 프롬프트는 `src/model/prompts/classify_v1.txt`로 고정한다. 고치면 파일을 새 버전으로 만들고 `PROMPT_VERSION`을 올린다.
- 판정 정의는 정답지 판정 기준표와 같아야 한다. 기준표가 바뀌면 프롬프트도 새 버전으로 맞춘다.
- 출력은 코드가 검사한다: 입력에 없는 원재료는 버리고, 빠진 원재료는 판정 불가로, 잘못된 값은 source_unknown으로.
