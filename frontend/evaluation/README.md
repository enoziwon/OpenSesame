# 평가 스크립트

예측과 gold를 제품 ID로 연결해 미국 9개 알레르겐의 존재 여부를 평가합니다.

## 실행

기존 루트 requirements를 설치한 Python으로 frontend 폴더에서 실행합니다.

```powershell
cd frontend
python -m evaluation --gold gold.json --predictions predictions.json
python -m evaluation --gold gold.json --predictions predictions.json --output report.json
```

gold는 `data/schema/label_record.schema.json`을 따르는 레코드의 JSON 배열입니다. 예측도 배열이며 각 항목은 다음 형태입니다. `/analyze` 응답에 해당 사진의 gold ID를 붙여 저장하면 됩니다. `id`는 파일 순서가 아닌 제품 식별자로 일치시켜야 합니다.

```json
[
  {
    "id": "pilot_01",
    "allergens": [
      {"allergen": "wheat", "verdict": "confirmed", "evidence_ingredient": "소맥분"}
    ]
  }
]
```

미검출 응답도 `{"id": "pilot_01", "allergens": []}`처럼 포함합니다. ID 누락·추가·중복, 동일 제품 내 중복 알레르겐, 알 수 없는 판정은 오류로 종료합니다. gold의 동일 알레르겐 근거가 여러 개면 제품 단위 판정 한 개로 정리한 뒤 입력합니다. UTF-8 및 BOM이 있는 UTF-8 파일을 지원합니다.

## 실제 LLM 전사 테스트

저장소 루트에서 `python -m frontend.evaluation.run_llm`을 실행합니다. 추가 의존성은 `openai>=1.40`입니다. 루트 `.env`의 `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL=https://api.baze.co/v1/gateway`를 사용합니다. 이 실행기는 `.env` 값을 기존 프로세스 환경보다 우선합니다. 인증은 OpenAI 호환 SDK의 `Authorization: Bearer`입니다. 백엔드 서버를 실행할 필요는 없습니다.

로컬 입력은 `evaluation/local/jaewon/pilot-10.draft.json`이며, 원재료 전사만 파서·분류기에 전달합니다. 판정과 검수 메모는 LLM에 보내지 않습니다. PR #7의 커밋 `630ec8d9d52c00b6f902a3870e6a0357eb0e8d38`에 있는 `src/model/llm.py`를 `local/gateway_pr7.py`로 저장해 사용하며 프롬프트와 파서·집계는 현재 저장소 코드를 읽습니다. 결과와 실행 메타데이터는 Git에서 제외된 `local/llm-run-*/`에 저장됩니다. 사진 OCR 및 프론트 HTTP 연결 테스트가 아닌 전사 기반 분류 테스트입니다. 교차 검수 전 라벨과의 비교 결과는 예비 점수입니다.

## 초기 계산 정책: presence_v1

프론트 연동 개발 서버는 루트에서 `python -m frontend.evaluation.serve_llm`으로 실행합니다. PR #7 로컬 사본을 프로세스 안에서 로드하므로 공용 백엔드 파일 변경 없이 BAZE를 사용합니다. 루트 `.env`에 `OPENSESAME_CLASSIFIER=llm`, `OPENSESAME_OCR=mock`, `LLM_PROVIDER=openai`와 키·모델·Base URL을 설정합니다. 프론트는 별도 터미널에서 `cd frontend` 후 `npm run dev`를 실행합니다. 일반 `uvicorn src.app.main:app`은 현재 브랜치의 기존 Anthropic 구현을 쓰므로 이 개발 실행기와 구분해야 합니다.

- 제품 × 알레르겐 9개를 평가 단위로 사용하고 전체 지표는 micro 집계합니다. 항목별 지표도 출력합니다.
- gold와 예측의 `confirmed`·`inferable`은 양성입니다. 두 판정 간 정확한 구분은 이 지표로 평가하지 않습니다.
- gold 목록에 없는 알레르겐은 음성입니다(기존 gold 스키마 규칙). 미판독·누락이 있는 초안을 그대로 입력하면 안 됩니다.
- gold의 `undecidable`은 양성/음성 정답이 아니므로 분모에서 제외하고 `excluded_gold`에 셉니다.
- 예측의 `undecidable`은 검출 성공이 아닙니다. 평가 가능한 gold에 대해 별도 `predicted_undecidable`로 세며 gold 양성이면 FN, 음성이면 TN으로 집계합니다. 따라서 이는 존재 여부 평가이며 화면의 모든 주의 안내를 평가한 지표는 아닙니다.
- 재현율: `TP / (TP + FN)`. 과잉 경고율(오경보율/FPR): `FP / (FP + TN)`. 후자는 `FP / (TP + FP)`와 다릅니다. 결과는 0~1 비율이며 분모가 0이면 JSON `null`입니다.
- warnings 및 undecidable_ingredients는 전체 주의 안내용이며 특정 알레르겐 양성으로 변환하지 않습니다.
- 출력의 TP/FN/FP/TN 합계는 평가 단위 수이며 제품 수가 아닙니다.

과제의 기본 지표를 실행할 수 있는 뼈대입니다. 누락 가중치, Seen/Unseen 분할, 가상 프로필별 평가, 근거 일치 및 판정 불가 적절성은 아직 구현하지 않았습니다. 최종 평가 정책은 팀 합의로 확정해야 합니다. 실제 사진·gold·예측은 공유 드라이브 또는 Git에서 제외된 `data/annotations/`에 보관하세요. 스크립트는 LLM을 호출하지 않습니다.
