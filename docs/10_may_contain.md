# 10. may contain 연결 안내 (같은 시설 문구, LLM 추측, 화면, LLM 설명)

- 작성: 정형식(최종본), 2026-11-19
- 관련: 11/18 회의 결정, `experiments/EXP-007-may-contain.md`, PR #13·#14·#15, 정형식 브랜치 커밋 d8ead23
- 이 문서만 보고 각자 어디를 고치면 되는지 알 수 있게 썼다. 판정 규칙은 `docs/09_gold_guide.md`, 응답 칸 목록은 `src/final/README.md`에 있다.

## 한눈에

11/18 회의에서 정한 것

- 화면은 알레르기마다 Contains / May contain / Not detected 셋으로 보여 준다(최재원).
- 같은 시설 문구도 may contain에 넣는다.
- may contain 항목에는 규칙으로 만든 영어 이유(`reason_en`) 뒤에 LLM 설명을 덧붙인다(이진영).
- OCR 글자를 LLM으로 고치는 일은 김민재(#13, #15).

이번에 최종본(정형식)이 한 일

- 같은 시설 문구에만 있는 알레르기를 `shared_facility` 칸에 고정 문장과 함께 담는다. 판정은 바꾸지 않는다.
- LLM이 정한 근거에 표시를 단다. basis `LLM-FIX`는 OCR이 잘못 읽은 이름을 LLM이 고쳐 사전에서 찾은 것, `LLM`은 사전에 없는 이름을 LLM이 판단한 것이다. 둘 다 추정까지만 되고 Contains는 되지 않는다.
- 고친 이름은 `read_as`에 담는다. 예: 근거 '회류', read_as '어류'.
- LLM 설명이 들어갈 빈 칸 `explanation_en`을 만들어 두었다. 최종본은 채우지 않는다.
- 기존 칸의 뜻과 팀 공통 형식(`src/common/schema.py`)은 바꾸지 않았고 칸만 더했다.

누가 무엇을

| 사람 | 할 일 | 고칠 곳 |
|---|---|---|
| 최재원 | `shared_facility`를 May contain의 가장 낮은 단계로 보여 주기, `explanation_en`이 있으면 이유 아래에 보여 주기 | `frontend/src/types/analysis.ts`, `frontend/src/pages/ResultsPage.tsx` (3절) |
| 이진영 | May contain 항목의 `explanation_en` 채우기 | 새 파일 `src/final/explain.py`(가칭), `src/final/app.py` 두 곳 (4절) |
| 김민재 | 없음. #15는 그대로 두면 된다 | (5절) |

## 1. 알레르기 하나가 받는 단계

알레르기 하나는 아래 중 한 단계만 받는다. 위에 있는 것이 이긴다.

| 순서 | 화면 | 응답에서 | 예 |
|---|---|---|---|
| 1 | Contains | `allergens[].verdict` = confirmed | 밀가루 → wheat |
| 2 | May contain · Likely | verdict = inferable | 표시란의 대두가 정제유 때문일 수 있음(R1-1), LLM이 고친 이름(LLM-FIX) |
| 3 | May contain · Cannot determine | verdict = undecidable | 속 모를 양념(OPAQUE), LLM이 '가능'이라고 한 이름(LLM) |
| 4 | May contain · Shared facility | `allergens`에 없고 `shared_facility`에 있음 | 같은 시설 문구의 땅콩 |
| 5 | Not detected | 둘 다 없음 | |

- 고추참치는 같은 시설 문구에 고등어가 있지만 원재료 가다랑어 때문에 생선이 이미 confirmed다. 최종본이 이런 알레르기를 `shared_facility`에서 빼고 보내므로, 화면은 `allergens`에 없을 때만 `shared_facility`를 보면 된다.
- LLM은 2·3단계까지만 만든다. Contains를 만들거나 판정을 지우지 못한다.
- 표시란 규칙은 LLM 근거에도 그대로 적용된다. 표시란을 읽었는데 '우유'가 없으면, LLM이 '유우'를 '우유'로 고쳐도 다른 추정 근거처럼 지운다. 표시란에 '우유'가 있으면 표시란 때문에 Contains다.
- `warnings`가 있으면(원재료나 표시란을 못 읽음) 지금처럼 결과를 단정하지 않는다.

## 2. 응답 예

합친 코드(main + #13·#14·#15 + 정형식)에 가짜 LLM을 넣어 실제로 뽑은 응답에서 칸 몇 개만 남겼다.
입력 글자: `원재료명: 밀가루, 회류, 헤즐너트페이스트, 해물양념분말, 설탕 / 알레르기 유발물질: 밀 함유 / 이 제품은 땅콩, 새우, 게를 사용한 제품과 같은 제조시설에서 제조하고 있습니다.`

```json
{
  "allergens": [
    {
      "allergen": "fish", "verdict": "inferable", "evidence_ingredient": "회류",
      "other_evidence": ["해물양념분말"], "basis": ["LLM-FIX"], "read_as": "어류",
      "reason_en": "Likely contains fish: the label text “회류” looks like a misread of 어류 (fish).",
      "explanation_en": null
    },
    {
      "allergen": "tree_nut", "verdict": "inferable", "evidence_ingredient": "헤즐너트페이스트",
      "basis": ["LLM"], "read_as": null,
      "reason_en": "Likely contains tree nuts: “헤즐너트페이스트” is not in our ingredient dictionary, and an AI model judged that it likely contains tree nuts.",
      "explanation_en": null
    },
    {
      "allergen": "sesame", "verdict": "undecidable", "evidence_ingredient": "해물양념분말",
      "basis": ["OPAQUE"], "read_as": null,
      "reason_en": "Cannot tell: “해물양념분말” is a seasoning blend whose contents are not listed, and Korean labels do not have to declare sesame.",
      "explanation_en": null
    }
  ],
  "shared_facility": [
    {
      "allergen": "crustacean", "words": ["새우", "게"],
      "reason_en": "Crustacean shellfish are not listed as an ingredient, but this product is made in a facility that also handles shrimp and crab, so traces are possible. Avoid it if your allergy is severe.",
      "reason_ko": "원재료에 갑각류는 없지만, 새우, 게를 쓰는 제품과 같은 시설에서 만들어 미량이 섞일 수 있다. 알레르기가 심하면 피하는 것이 좋다."
    },
    {
      "allergen": "peanut", "words": ["땅콩"],
      "reason_en": "Peanuts are not listed as an ingredient, but this product is made in a facility that also handles peanuts, so traces are possible. Avoid it if your allergy is severe.",
      "reason_ko": "원재료에 땅콩은 없지만, 땅콩을 쓰는 제품과 같은 시설에서 만들어 미량이 섞일 수 있다. 알레르기가 심하면 피하는 것이 좋다."
    }
  ]
}
```

- 밀은 confirmed라 위에서 뺐다. 원래 응답에는 있다.
- LLM-FIX·LLM은 `OPENSESAME_FINAL_FALLBACK=llm`이고 LLM 키가 있을 때만 나온다. `shared_facility`는 LLM 없이 늘 나온다.

## 3. 최재원: 화면

#14 위에서 바로 할 수 있다. 새 칸이 없는 응답(옛 서버)에도 깨지지 않게 `?.`과 `?? []`로 읽으면 된다.

(1) `frontend/src/types/analysis.ts`

```ts
export interface AllergenResult {
  // 지금 칸들 그대로 두고 두 칸을 더한다
  read_as?: string | null;          // LLM이 고친 이름 (basis가 LLM-FIX일 때)
  explanation_en?: string | null;   // LLM 추가 설명 (진영 님 담당, 없으면 null)
}
export interface FacilityResult {
  allergen: Allergen;
  words: string[];                  // 문구에 적힌 한국어 낱말
  reason_en: string;                // 고정 문장. 그대로 보여 준다
  reason_ko?: string;
}
export interface Analysis {
  // 지금 칸들 그대로 두고 한 칸을 더한다
  shared_facility?: FacilityResult[];
}
```

(2) `frontend/src/pages/ResultsPage.tsx`

- 줄마다 `found`가 없으면 `result.shared_facility?.find((f) => f.allergen === id)`를 본다. 있으면 그 줄을 May contain의 가장 낮은 단계(Shared facility)로 그리고, 펼치면 그 `reason_en`을 그대로 보여 준다. 펼친 제목은 예를 들어 "SHARED FACILITY".
- `incomplete`(warnings 있음)일 때는 지금처럼 'Cannot determine'이 먼저다. 즉 `found`도 없고 `incomplete`도 아닐 때만 Shared facility를 본다.
- `rank`: confirmed 0, inferable 1, undecidable 2, shared facility 3, 없음 4.
- 위 배너의 'n results need review'에는 Shared facility를 세지 않기를 권한다. 사진 14개 중 12개에 이 문구가 있어서, 세면 거의 모든 제품이 '검토 필요'가 된다. 줄에서 보이는 것으로 충분하다.
- inferable·undecidable 줄을 펼쳤을 때 `reason_en` 아래에 `found.explanation_en`이 있으면 한 문단 더 보여 준다. null이면 아무것도 보여 주지 않는다. LLM 설명이라는 작은 표시(예: "AI explanation")가 있으면 좋다.
- 선택: `found.basis?.[0]`이 "LLM-FIX"나 "LLM"이면 배지 옆에 "AI estimate" 같은 작은 표시. `reason_en`에 이미 적혀 있어서 없어도 된다.
- 'Not detected ≠ allergen-free' 안내는 그대로 둔다.

May contain 안의 세 단계를 어떻게 보여 줄지(작은 글씨, 색)는 재원 님이 정하면 된다. 지금 #14의 'Likely'와 'Cannot determine' 배지를 May contain 하나로 묶고, 그 아래 작은 글씨로 Likely / Cannot determine / Shared facility를 붙이는 방식을 제안한다.

## 4. 이진영: LLM 설명 (`explanation_en`)

할 일: `allergens[]` 중 verdict가 inferable·undecidable인 항목마다 `explanation_en`에 영어 1~2문장을 채운다. 화면이 `reason_en` 아래에 덧붙여 보여 준다.

LLM에 넘길 입력(항목마다): `allergen`, `verdict`, `basis`, `evidence_ingredient`, `other_evidence`, `evidence_en`, `read_as`, `reason_en`. 필요하면 제품의 `ingredients_text`, `declaration_text`.

basis별로 설명할 것

- `LLM-FIX`: 라벨 글자가 잘 안 읽혀 `read_as`로 고쳐 읽었다는 것, `read_as`가 무엇이고 왜 그 알레르기인지. 예: "Part of the label was hard to read. “회류” is most likely 어류, the Korean word for fish."
- `LLM`: 사전에 없는 이름이 무엇으로 보이는지, 왜 그 알레르기일 수 있는지. 예: "“헤즐너트페이스트” appears to be a spelling variant of hazelnut paste."
- `OPAQUE`, `COMPOUND`: 그런 원료가 보통 무엇으로 만드는지 일반적인 설명. 이 제품에 들었다고 단정하지 않는다.
- `LIKELY`, `POSSIBLE`: 그 원료가 보통 무엇으로 만드는지.
- `R1-1`: 한국은 정제 대두유만 써도 표시란에 대두를 적는다는 것. `reason_en`이 이미 말하므로 짧게 하거나 비워도 된다.

지킬 것

1. 판정은 그대로 둔다. `verdict`, `basis`, `reason_en`, `allergens` 목록, `shared_facility`는 바꾸지 않고 `explanation_en`만 채운다.
2. 이미 나온 판단을 설명한다. LLM-FIX는 `read_as`를 그대로 설명하고 다른 이름으로 다시 추측하지 않는다. 다시 추측하면 배지와 설명이 엇갈린다.
3. "safe", "allergen-free", "you can eat it"처럼 안심시키는 말은 쓰지 않는다.
4. LLM 호출이 실패하거나 크레딧이 없으면 `explanation_en`을 null로 둔다. `reason_en`만으로도 화면은 완성된다.
5. confirmed와 `shared_facility`는 설명하지 않는다. `shared_facility`를 고정 문장으로 둔 이유는 6절.

어디에 붙이나

- 새 파일 `src/final/explain.py`(가칭)에 `explain(res: FinalAnalyzeResponse) -> FinalAnalyzeResponse` 같은 함수 하나를 두고, `src/final/app.py`의 `analyze_label`(/analyze)과 `analyze_label_text`(/analyze-text)가 응답을 돌려주기 직전에 부르는 방식을 제안한다.
- 환경 변수로 켜고 끄게 하고 기본은 끈다(예: `OPENSESAME_FINAL_EXPLAIN=llm`). 테스트와 평가는 LLM 없이 늘 같은 결과가 나와야 한다.
- LLM 호출은 팀 클라이언트 `src/model/llm.py`(게이트웨이 설정)를 쓰면 된다.
- `app.py`는 #13·#14·#15가 모두 고치는 파일이다. 세 PR이 main에 들어간 뒤에 붙이면 충돌이 없다. `explain.py`와 그 테스트는 지금 만들어도 된다.

사전에 없는 이름을 사전에 맞추는 일(11/18 회의에서 진영 님 몫으로 이야기한 것)은 최종본의 보조 분류기가 이미 한다. `OPENSESAME_FINAL_FALLBACK=llm`이면 끝까지 모르는 이름을 LLM에 한 번 묻고(#15 프롬프트 `src/model/prompts/ocr_fix_v1.txt`: 글자 고치기와 알레르기), 그 결과가 basis `LLM-FIX`·`LLM`으로 온다. 그래서 설명 LLM은 같은 이름을 다시 판정하지 않고 그 결과를 풀어 주면 된다. 맞추는 질을 올리고 싶으면 그 프롬프트를 민재 님과 함께 고치면 된다.

크레딧 없이 시험하려면 2절 예시를 입력으로 쓰거나, `tests/test_final_llm_marks.py`의 `FakeFixLLM`처럼 가짜 LLM을 넣으면 된다.

실제로 얼마나 붙나(EXP-007): 표시란을 읽은 제품 100개당 생선 약 20개, 대두 12개, 참깨 10개 항목이 may contain이다. 이유는 속 모를 양념·국물 원료가 가장 많고 다음이 정제유 대두(R1-1)다. LLM-FIX·LLM은 보조 분류기를 켰을 때만 나온다.

## 5. 김민재: #15

고칠 것은 없다. 최종본이 via 'ocrfix'를 받아 추정으로 낮추고 basis `LLM-FIX`와 `read_as`를 단다. #15 설명의 '바로잡은 이름이 사전에서 찾아지면 사전 판정을 쓴다'는, 합친 뒤에는 '사전에서 찾은 알레르기를 추정으로 쓴다'가 된다.
`read_as`는 지금 Resolver의 `_fixed`를 읽는다. #15가 main에 들어가면 공개 속성으로 바꾼다(정형식).

## 6. 같은 시설 문구를 LLM이 아니라 고정 문장으로 둔 이유

- 알레르기 이름만 바뀌고 매번 같은 말이라 LLM이 추론할 것이 없다.
- LLM에 맡기면 표현이 매번 달라지고 "괜찮다"처럼 지나치게 안심시키는 말이 나올 수 있다. 크레딧이 떨어지면 안내가 통째로 사라진다.
- 한국은 같은 제조 과정에서 알레르기 원료를 다루면 이 문구를 적게 해서 거의 모든 라벨에 있다(EXP-006 사진 14개 중 12개, 땅콩 11개). 그대로 may contain에 섞으면 14개 제품의 may contain 항목이 13개에서 57개로 늘어, 정말 애매한 생선·대두·참깨가 묻힌다. 그래서 가장 낮은 단계로 따로 둔다.
- 문장이 '원재료에는 없다'와 '미량이 섞일 수 있다'를 함께 말하는 이유: 2010년 미국 연구(마트 제품 400여 개)에서 이런 경고 문구가 붙은 제품 중 실제로 성분이 나온 것은 약 5%였고, 문구가 없는 제품은 약 2%였다([FoodNavigator-USA](https://www.foodnavigator-usa.com/Article/2010/08/13/Products-carrying-may-contain-allergen-labels-often-contaminated-finds-study/)). 대부분은 들어 있지 않지만, 심한 알레르기에는 무시할 수 없는 수치다.

## 7. 합치는 순서와 확인한 것

- main + #13 + #14 + #15 + 정형식(d8ead23)을 차례로 합치면 충돌이 없다. 합친 코드에서 Python 3.12·3.9 모두 테스트 688개가 통과했다(#15와 이어지는 테스트 포함, 2026-11-19).
- 권하는 순서: #13·#14·#15 → 정형식 PR → 재원·진영 작업. 재원 님 화면 작업은 새 칸이 선택 칸이라 지금 #14에서 바로 해도 된다.

AI 사용: 이 문서와 관련 코드는 Claude Code(Opus 5.5)로 작성했다.
