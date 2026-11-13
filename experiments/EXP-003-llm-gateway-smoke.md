# EXP-003 학교 게이트웨이 LLM 동작 확인 (평가 아님)

- 날짜: 2026-11-12 ~ 11-13
- 모델: claude-sonnet-5-5 (숭실대 BAZE 게이트웨이, OpenAI 호환)
- 프롬프트: classify_v1 / temperature 0 / tool_choice auto

## 1. 분류기 단독 (tools/try_llm.py, 원재료 17개 × 3회)
- 누락 0, 지어냄 0 (3회 모두)
- 회차별 불일치 2개
  - 카제인나트륨: milk inferable → confirmed → inferable
  - 새우맛분말: crustacean undecidable → inferable → undecidable
- 둘 다 판정 기준이 애매한 경우 → 판정 기준표 확정 후 프롬프트 v2

## 2. POST /analyze 경유 (OCR mock + LLM)
- 정상 응답, warnings 없음
- 발견: 괄호가 있는 부모 원재료를 따로 판정함
  - 식물성유지(팜유) → soy 근거로 잡힘 (과잉 경고)
  - 혼합조미분말[멸치분말, 정제소금, 효모추출물] → 판정 불가 원재료로 분류
  - 원인: flatten이 부모 이름도 넘기고, 프롬프트는 이름만 보고 판단하게 함
  - 11/15 회의에서 방식 결정 (하위만 분류 / 부모+하위 함께 전달)

## 한계
- 원재료 17개, 대부분 쉬운 경우. 정확도·일관성 수치로 쓰지 않는다.