# English reason integration

The existing Figma layout is unchanged. Only Likely and Cannot Determine rows expose reason accordions; Confirmed and Not Detected have no reason or chevron. Existing warnings, incomplete-analysis handling, notes, evidence and safety text remain.

## Data flow

Photo upload -> POST /analyze -> CLOVA -> final parser/classifier -> pipeline.reason() -> FinalAllergenResult.reason_en -> analyze.ts -> normalizeAnalysis() -> ResultsPage.

Text input uses POST /analyze-text with {"text":"..."} and runs the same final parser/classifier without OCR. The API also accepts {"ingredients":"...","declaration":"..."}.

The frontend default and .env.example target http://localhost:8001. Run the product server from the repository root:

    .venv/Scripts/python.exe -m uvicorn src.final.app:app --host 127.0.0.1 --port 8001

src.app.main is the comparison server and is not used by the product integration.

## Changes in this task

- frontend/src/types/analysis.ts: optional basis, species, reason_ko fields; existing evidence_en and reason_en retained.
- frontend/src/utils/analysis.ts: normalize optional metadata without changing valid reason_en strings.
- frontend/src/pages/ResultsPage.tsx: display server reason verbatim; missing, empty or whitespace-only reasons use the requested neutral fallback. Remove duplicated reason prose from the original-label section, including confirmed reasons.
- src/final/pipeline.py: use known evidence_en followed by the original ingredient in parentheses for LIKELY, POSSIBLE, OPAQUE, COMPOUND and ingredient-based R1-1 explanations. When no English name exists, retain only the original name. Confirmed/statement wording and all judgement rules remain unchanged.
- tests/test_final_pipeline.py: update wording expectations and check missing-English behavior.
- frontend/tests/results-design.spec.ts: remove the shared-equipment example from the fixture.
- frontend/tests/reasons.spec.ts: check verbatim normalization, fallback, long text, 9 rows, simultaneous expansion, and absence of confirmed accordions/reasons.
- frontend/tests/integration/server.spec.ts: compare real final-server JSON with rendered explanations for different labels.
- frontend/REASON_INTEGRATION.md: this report.

Existing response.py, verdict.py, common schema, endpoints, API request code and classifier logic were reused.

## Actual final API examples

POST /analyze-text {"ingredients":"간장, 설탕"} returns a wheat result:

    {
      "allergen": "wheat",
      "verdict": "inferable",
      "evidence_ingredient": "간장",
      "basis": ["LIKELY"],
      "species": [],
      "evidence_en": "soy sauce",
      "reason_en": "Wheat may be present because soy sauce (간장) is commonly made with wheat."
    }

The Wheat / Likely accordion displays that reason_en unchanged under WHY IT MAY BE PRESENT. This input also returns a confirmed soy finding and the existing missing-allergen-statement warning.

POST /analyze-text {"ingredients":"육수, 설탕, 밀 함유"} returns fish / undecidable with:

    Cannot tell: broth (stock) (육수) sometimes contains fish.

The Fish / Cannot Determine accordion displays that sentence under WHY IT'S UNCLEAR. The English name "broth (stock)" comes directly from the existing dictionary.

Absent, empty and whitespace-only reason_en use:

    The reason could not be provided. Please check the original label.

Facility statements continue to be notes only. No frontend inference or translation was added.

## Verification

- Final pipeline, app and verdict tests: 92 passed.
- Frontend reason, accordion and existing photo-response tests: 5 passed.
- Real final-server browser integration over /analyze-text: 2 passed.
- Production typecheck/Vite build: passed.
- Long explanations checked for internal horizontal/vertical clipping; existing 375px/320px accordion and keyboard checks passed.
- /analyze route and photo-to-final-parser wiring are covered with an OCR test double in the backend tests. This is not a live CLOVA verification.

CLOVA credentials are configured, but no product-label photo was available in the workspace and no photo-test path was supplied, so live external OCR was not called. The existing optional live-photo integration can be run when a label image is provided. No API contract or verdict-rule change, or backend agreement, is required for this work.
