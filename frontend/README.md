# OpenSesame 프론트엔드

React + TypeScript + Vite + Tailwind CSS로 구현한 모바일 웹 앱입니다. Figma 파일 `UPnaTDKkcWdB8aktu4Oz8w`의 프레임 `3:22`~`3:25`를 기반으로 합니다.

## 실행 방법 (PowerShell)

```powershell
# 저장소 루트에서 기존 백엔드를 데모 모드로 실행
$env:OPENSESAME_OCR='mock'
$env:OPENSESAME_CLASSIFIER='mock'
.\.venv\Scripts\python.exe -m uvicorn src.app.main:app --host 127.0.0.1 --port 8000

# 별도 터미널에서 프론트엔드 실행
cd frontend
npm.cmd ci
Copy-Item .env.example .env
npm.cmd run dev
```

브라우저에서 http://localhost:5173 에 접속합니다. 검증에는 Node 22를 사용했습니다. 백엔드 의존성이 없다면 저장소 루트에서 `python -m venv .venv`와 `.\.venv\Scripts\python.exe -X utf8 -m pip install -r requirements.txt`를 먼저 실행합니다. `-X utf8`은 Windows 한국어 코드 페이지로 인한 pip 인코딩 문제를 방지합니다.

`VITE_API_BASE_URL`의 기본값은 `http://localhost:8000`입니다. 값을 변경하면 Vite를 다시 실행해야 합니다. 휴대전화에서는 localhost 대신 기기에서 접근할 수 있는 백엔드 주소, 허용된 CORS 출처, 적절한 HTTPS 배포 환경이 필요합니다. 카메라 동작은 기기와 브라우저에 따라 다르며, 데스크톱 파일 선택창 테스트만으로 실제 촬영 동작을 검증할 수는 없습니다. 운영 환경의 호스팅 서버는 클라이언트 라우팅 경로에도 `index.html`을 제공해야 합니다.

## 데이터와 개인정보

기존 `POST /analyze`에는 multipart 필드 `file` 하나만 전송합니다. 알레르기 선택 정보는 브라우저에서 대조하며 서버로 보내거나 로그에 기록하지 않습니다. `utils/profileStorage.ts`는 localStorage의 `opensesame.allergies` 키를 사용해 새로고침과 브라우저 재시작 후에도 선택을 유지합니다. 잘못된 JSON이나 배열이 아닌 데이터는 빈 프로필로 처리하고, 허용되지 않은 ID와 중복 값은 무시합니다. 저장소 접근이 차단되어도 현재 React 상태는 사용할 수 있지만 영구 저장은 불가능합니다. 사진과 분석 결과는 메모리에만 보관하고, 미리보기용 객체 URL은 해제합니다. Results 화면을 새로고침하면 다시 분석해야 합니다.

`types/analysis.ts`는 백엔드의 알레르겐 ID와 판정 enum을 그대로 사용합니다. `utils/analysis.ts`에는 응답 검증과 정규화 로직을 분리했습니다. `undecidable_ingredients`, `other_evidence`, `meta`는 팀 확인 전까지 선택 필드로 방어적으로 처리합니다. 응답 메타데이터에 Mock 모드가 명시되어 있으면 데모 안내를 표시합니다. API 오류 시 프론트엔드 Mock으로 자동 대체하지 않습니다. 메타데이터가 없으면 어떤 서버 엔진이 실행되었는지 확정할 수 없습니다.

## 디자인과 화면 동작

Figma 원본 SVG는 `src/assets`에 있습니다. 랜딩 화면의 일러스트는 Figma의 편집 가능한 사각형 레이어를 바탕으로 CSS로 재현했습니다. Inter 글꼴은 로컬에서 제공합니다. 알레르기 선택 카드는 3열 그리드, 높이 116px, 아이콘 35px, 중앙 체크박스 배치를 유지합니다. 카메라·갤러리 버튼에는 제공된 SVG를 사용합니다.

현재 앱 UI는 영어만 지원하며, 구현되지 않은 KO 전환 버튼은 제외되어 있습니다. 미리보기에는 디자인의 예시 이미지 대신 사용자가 선택한 사진을 표시합니다. Results에는 미국 9대 알레르겐 전체, 실제 서버의 근거 성분과 판정, 출처 불명 원재료, 경고, 데모 상태를 표시합니다. 동적 내용에 따라 화면 높이는 정적 디자인의 812px보다 길어질 수 있습니다. 임의의 근거를 생성하거나 안전을 보장하는 표현은 표시하지 않습니다. Crustacean Shellfish는 Figma의 짧은 화면 표기인 Shellfish를 사용하되, 체크박스의 접근성 이름에는 전체 명칭을 제공합니다.

Results의 9개 행은 항상 유지합니다. 사용자가 선택한 알레르겐에 서버 판정이 있을 때만 개인 경고로 강조합니다. Confirmed에 해당하는 개인 결과가 있으면 검출 제목을 표시하고, 선택한 항목이 Likely 또는 Cannot determine이면 주의 안내를 표시합니다. 결과가 없는 항목은 Not detected로 표시하며 안전 보장으로 해석하지 않도록 안내합니다. 경고가 있거나 OCR 텍스트·원재료가 누락되어 분석이 불완전하면, 결과가 없는 항목도 Cannot determine으로 표시합니다. 출처 불명 원재료는 별도로 안내하며 미검출을 안전 보장으로 해석하지 않습니다.

## 검증 방법

```powershell
npm.cmd run typecheck
npm.cmd run build
npx.cmd playwright install chromium
# 통합 테스트를 위해 백엔드 Mock 서버가 8000번 포트에서 실행 중이어야 함
npm.cmd test
```

Playwright는 9개 항목 선택, localStorage 유지와 Chromium 재실행, 비정상 프로필, 세 가지 화면 크기, 카메라·갤러리 버튼 연결, 업로드·교체·삭제, 오류 처리, 요청 잠금, 선택 필드 누락, 개인별 경고, 판정 문구, OCR 실패, multipart 개인정보 제외, 실제 FastAPI Mock 연동을 검사합니다. 생성된 스크린샷·보고서와 의존성 폴더는 Git 추적에서 제외됩니다. 실제 iOS Safari·Android Chrome 카메라 촬영은 기기 테스트가 필요합니다. 실행 결과와 제한 사항은 [검증 보고서](VERIFICATION.md)를 참고하세요.
