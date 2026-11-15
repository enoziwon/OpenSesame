# EXP-003 측정 자료

결과와 해석은 [`../EXP-003-ocr-compare.md`](../EXP-003-ocr-compare.md). 이 폴더는 그 수치를 다시 계산하거나 다시 측정하는 데 쓰는 자료다.

## 들어 있는 것
| 경로 | 내용 |
|---|---|
| `gold/pXX.txt` | 정답: 사진의 원재료명 칸을 사람이 옮겨 적은 것 (항목명부터 '○○ 함유'까지) |
| `crops.json` | 원재료명 칸 좌표 `[x0, y0, x1, y1]` |
| `crops_mask_p08.json` | p08(기울어진 사진)에서 흰색으로 지운 영역 |
| `results/<엔진>/pXX.txt` | 비교 1: 엔진별로 원재료명 칸을 읽은 결과, `meta.json`은 장당 시간 |
| `raw/pXX.json` | 비교 2: 사진 전체를 CLOVA로 읽은 원본 응답 |
| `results/clova_full/pXX.txt` | 비교 2: `raw/`에서 `src/ocr/clova.py`로 원재료명 칸을 자동 추출한 결과 |

**들어 있지 않은 것**: 사진(`imgs/`, `crops/`, `crops2x/`)은 공유 드라이브 `데이터 사진`에만 둔다. 키는 저장소 루트 `.env`에.

## 다시 계산하기 (API 호출 없음)
```
cd experiments/EXP-003
python score.py                 # EXP-003 표의 수치 (비교 1, 사진별 CER, 비교 2)
python run_raw.py --from-raw    # src/ocr/clova.py 를 고친 뒤 results/clova_full 다시 만들기
```
`ocr_eval.py`도 표를 출력하지만 CER을 사진별 단순 평균으로, 항목명까지 세서 계산한다. EXP-003의 수치는 `score.py` 기준이다.

## 다시 측정하기
1. 공유 드라이브에서 사진 10장을 `imgs/p01.jpg` ~ `imgs/p10.jpg`로 넣는다.
2. `python make_crops.py` → `crops/`
3. 엔진 실행 (결과는 `results/<엔진>/`에 덮어씀)
   - CLOVA·Google: `python run_cloud.py clova` / `python run_cloud.py google`. 일부만: `--only p08`
     CLOVA 무료는 월 100건이라 10장 전체 실행은 10건을 쓴다.
   - 사진 전체(비교 2): `python run_raw.py` (CLOVA 10건)
   - 오픈소스: `run_tess.py`, `run_easy.py`, `run_paddle.py` (각 도구 설치 필요)
4. `python score.py`

## 알아 둘 점
- `crops2x/`(2배 확대 + 흑백 + 대비 보정)를 만든 스크립트는 남아 있지 않다. `run_tess2.py`, `run_easy2.py`는 그 이미지가 있어야 돌아간다.
- Tesseract·EasyOCR의 p08 결과는 예전 잘라 낸 칸(면 원료만)으로 읽은 것이다. 그래서 `score.py`의 오픈소스 행은 EXP-003 표(†)보다 높게 나온다.
- 비교 1의 CLOVA 호출(`run_cloud.py`)에는 `lang` 값을 넣지 않았다. 비교 2(`run_raw.py`, `src/ocr/clova.py`)는 `lang: ko`.
