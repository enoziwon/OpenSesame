# OpenSesame — 외국인 관광객을 위한 한국 식품 알레르기 경고

> 한국 포장식품 라벨의 **원재료명**을 읽어서, 미국에서 온 관광객의 개인 알레르기 반응 물질이 검출되는지, 검출된다면 경고해주는 시스템

자연어처리 수업 팀 프로젝트 (중간고사 영상 제출 2026-10-31, 발표 11/3 또는 11/5)

## 한눈에 보기

| 항목 | 내용 |
|---|---|
| 문제 | 한국 표시란에는 19개 항목만 나오고, 참깨·생선 전반·갑각류 전반·견과류 전반 등은 표시란에 없을 수 있음 |
| 대상 | 편의점·마트 포장식품 (식당 제외) |
| 본국 기준 | 미국(9개 식품군), EU(14개). 최대 1개국 추가 |
| 입력 | 라벨 사진 → OCR → 한국어 원재료명 |
| 출력 | 본국 기준 알레르겐 + 근거 원재료 + 3단계 판정 (확정 / 추론가능 / 판정불가) |
| 핵심 | 데이터셋·평가 체계·모델. 앱은 데모용 |

## 원칙

- **"미검출"은 "안전"이 아니다.** 화면과 발표 모두 이 표현을 지킨다.
- 놓치는 것(누락)이 과잉 경고보다 나쁘다. 평균 정확도는 주 지표로 쓰지 않는다.
- 방향·범위를 바꿀 때는 **팀 합의 → `docs/decisions/` 기록 → 숙제 공지** 순서를 지킨다.

## 현재 상태

- [x] 주제 확정 (2026-10-09)
- [ ] 통과 조건 ① 한국 19개 밖 알레르겐 포함 제품 비율
- [ ] 통과 조건 ② LLM 베이스라인 (어려운 원재료 10줄)
- [ ] MCS·아키텍처·마일스톤 문서 완성
- [ ] 중간고사 영상 제출 (10/31)

## 문서 지도

| 문서 | 내용 |
|---|---|
| [docs/01_MCS.md](docs/01_MCS.md) | 동기·주장·기여 (중간고사 ① 개요) |
| [docs/02_architecture.md](docs/02_architecture.md) | 파이프라인·기술 스택 (중간고사 ② 개발) |
| [docs/03_milestones.md](docs/03_milestones.md) | 일정 |
| [docs/04_team.md](docs/04_team.md) | 역할·협업·의사결정 (중간고사 ③ 팀 운영) |
| [docs/05_allergen_lists.md](docs/05_allergen_lists.md) | 한국·미국·EU 목록 비교 |
| [docs/06_photo_guide.md](docs/06_photo_guide.md) | 라벨 촬영 규칙 |
| [docs/decisions/](docs/decisions/) | 결정 기록 (ADR) |
| [docs/meeting-notes/](docs/meeting-notes/) | 회의록 |
| [experiments/](experiments/) | 실험 기록 |
| [data/schema/](data/schema/) | 데이터 스키마 |

## 폴더 구조

```
.github/        이슈·PR 템플릿
docs/           기획·설계·결정·회의록
data/schema/    JSON 스키마 (데이터 자체는 공유 드라이브)
experiments/    실험 기록
src/            ocr / parser / model / eval / demo
```

## 시작하기

```bash
git clone https://github.com/enoziwon/OpenSesame.git
cd OpenSesame
cp .env.example .env   # 키는 각자 발급해서 입력
```

사진·원본 데이터는 **저장소에 올리지 않는다.** 공유 드라이브를 쓰고 파일명 규칙은 [촬영 가이드](docs/06_photo_guide.md)를 따른다.

## 주의

이 프로젝트는 연구·수업용이다. 알레르기 판단에 단독으로 사용하면 안 된다.
