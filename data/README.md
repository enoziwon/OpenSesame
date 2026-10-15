# 데이터

- 이 폴더에는 **스키마만** 올린다. 사진·원본·gold 파일은 공유 드라이브에 둔다.
- 모든 gold 파일은 `schema/`의 JSON 스키마를 통과해야 한다.
- 검증: `python data/validate.py <파일>` (jsonschema 필요: `pip install -r requirements.txt`)
- 개인정보: 사람의 알레르기 정보는 수집하지 않는다. 평가용 프로필은 가상으로 만든다.

## 구성
| 파일 | 설명 |
|---|---|
| `schema/label_record.schema.json` | 라벨 사진 한 장당 전사·정답 기록 |
| `schema/example_record.json` | 작성 예시 (가상 제품) |

## 라벨 규칙
- 판정 기준은 **미국 의무 표시 알레르겐 9개**다: milk, egg, fish, crustacean, tree_nut, peanut, wheat, soy, sesame.
- 판정 3단계: `confirmed`(확인됨) / `inferable`(추정) / `undecidable`(판정 불가)
- 모든 정답에는 **근거 조항**(법령·지침)과 **근거 원재료**를 적는다.
- 복합 원재료·추출물·유래 표현 속에 든 경우 `hidden_or_derived`를 true로 한다 (통과 조건 ① 집계).
- 한국 표시란에 이미 표시되었는지는 `declared_in_kr`에 적는다 (참고 정보).
- 예외 조항이 적용되면 `exception_note`에 적는다.
- 사용자 프로필별 정답은 gold에서 선택 항목만 걸러 만든다.
