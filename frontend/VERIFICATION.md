# Verification — 2026-11-11

- `npm.cmd run build`: PASS (TypeScript noEmit check and Vite production build).
- `npm.cmd test`: PASS, 6 Chromium browser tests, 40.1 seconds.
- Existing backend `.venv\Scripts\python.exe -X utf8 -m pytest -q`: PASS, 14 tests.
- Dependency installation: successful; npm audit reported 0 vulnerabilities at installation.
- 375×812, 360×800 and 393×852: all flows pass, no horizontal document overflow on all four routes.
- All nine checkbox selections/toggle-off; route changes and page reload preserve the temporary session profile.
- Upload, preview, remove/reselect, drag-and-drop, empty/non-image/over-10MB rejection verified.
- Camera input has `accept="image/*"` and `capture="environment"`; physical camera behavior is not verified.
- HTTP error, malformed response, absent optional fields, cannot-determine verdict, incomplete analysis warning and duplicate-request locking verified.
- Multipart browser request has only `file` and its filename; no allergy profile field.
- Live existing FastAPI mock server on port 8000: browser POST `/analyze` returned 200, actual JSON populated Results, Korean evidence displayed, mock banner visible.
- Figma MCP read all four requested frames including screenshots. Original SVG assets downloaded locally; selection icons are loaded and rendered at 35×35. Result-specific icons retain their original 29×29 size; additional result rows reuse 35×35 selection icons. Captures compared with Figma for landing, allergies, scan and results. No remote Figma URLs are used at runtime.
- Captures are local ignored artifacts in `frontend/test-results/` (landing, allergies, scan, results for each width). Test input is a generated in-memory SVG, not user label data.

Intentional differences: KO switch omitted pending scope approval; photo preview uses actual selection; all nine result rows are visible and backend enum labels replace Figma placeholder wording; warnings and demo indicators extend the results page. The static example's preselected allergies are not assumed for real users.

Initial checks found a cold Vite startup timeout and broken arrow/ellipsis glyphs caused by Windows shell encoding. Source encoding and the timeout were corrected; the full final run passed. Python pip initially failed to decode the UTF-8 requirements file under cp949; `-X utf8` resolved it. No backend source changes were needed.

Remaining manual checks: iOS Safari and Android Chrome on real devices, physical camera permissions/capture, actual OCR/classifier quality outside backend mock mode, and team confirmation of profile persistence and the three provisional response fields. Production TLS/CORS/deployment is outside this frontend change.
