# 데이터

- 이 폴더에는 **스키마만** 올린다. 사진·원본·gold 파일은 공유 드라이브에 둔다.
- 모든 gold 파일은 `schema/`의 JSON 스키마를 통과해야 한다.
- 검증: `python -m jsonschema -i <파일> schema/label_record.schema.json` 또는 아래 스크립트 사용.

## 구성
| 파일 | 설명 |
|---|---|
| `schema/label_record.schema.json` | 라벨 사진 한 장당 전사·정답 기록 |
| `schema/example_record.json` | 작성 예시 (가상 제품) |

## 라벨 규칙
- 판정 3단계: `confirmed`(확정) / `inferable`(추론가능) / `undecidable`(판정불가)
- 모든 정답에는 **근거 조항**(법령·지침)과 **근거 원재료**를 적는다.
- 예외 조항이 적용되면 `exception_note`에 적는다.
