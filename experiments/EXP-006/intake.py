"""EXP-006: 찍어 온 사진을 정리한다 (맥 전용). 원본 사진은 건드리지 않는다.

  python experiments/EXP-006/intake.py stage <원본 폴더>    찍은 순서로 001.jpg …를 만들고 sort.tsv 초안을 쓴다
  python experiments/EXP-006/intake.py apply               sort.tsv대로 실험 폴더에 나눠 넣는다

- stage: photo_tool.swift가 사진을 찍은 시각 순서로 data/raw/photos/exp006_stage/NNN.jpg로 옮겨 적는다.
  방향은 픽셀에 반영하고 위치·기기·시각 같은 메타데이터는 지운다(CLOVA로 위치 정보가 나가지 않게).
  앱 서버 한도(10MB)를 넘으면 긴 변 4032px로 줄인다. 12장씩 모아 보기(sheet_NN.jpg)도 만든다.
  이 폴더는 저장소에 올라가지 않는다(data/raw).
- 맥 내장 OCR(Vision)로 품목보고번호를 찾아 sort.tsv 초안을 쓴다. 정리에만 쓰고, 실험 입력 글자는 CLOVA(run_raw.py)다.
  초안은 사람이 모아 보기를 보며 고친다. sort.tsv가 이미 있으면 sort.draft.tsv에 쓴다.
- sort.tsv 한 줄 (탭으로 나눔): 번호, 원본 파일, id, 역할, 메모
  - id: 시험 세트 제품은 B_test_085, 목록 밖 제품은 N_<품목보고번호>
  - back: 라벨 사진(실험 입력). data/raw/photos/exp006/<id>/1.jpg, 2.jpg … (sort.tsv 순서)
  - front: 앞면(제품 확인용). data/raw/photos/exp006_front/<id>.jpg
  - skip: 쓰지 않는다. 메모에 이유(흐림, 반사, 중복, 개발 세트 등)를 적는다.
- apply는 모든 줄을 먼저 검사하고, 틀린 곳이 하나라도 있으면 아무것도 옮기지 않는다.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from lookup import GOLD, ITEMS, digits, gold_index  # noqa: E402

STAGE = ROOT / "data" / "raw" / "photos" / "exp006_stage"
PHOTOS = ROOT / "data" / "raw" / "photos" / "exp006"
FRONTS = ROOT / "data" / "raw" / "photos" / "exp006_front"
SORT = HERE / "sort.tsv"
ROLES = ("front", "back", "skip")
HEADER = "# 번호\t원본\tid\t역할(front|back|skip)\t메모"
LABELED = re.compile(r"품\s*목\s*(?:제\s*조\s*)?보\s*고\s*번\s*호[^0-9]{0,10}([0-9][0-9 \-]{6,24}[0-9])")
BARE = re.compile(r"(?<![0-9])((?:19|20)[0-9]{8,12})(?![0-9])")
ID_RE = re.compile(r"B_test_\d{3}|N_\d{8,16}")


# ---------- stage: sort.tsv 초안 ----------
def load_haccp(path: Path = ITEMS) -> dict:
    """품목보고번호(숫자만) -> 제품명."""
    names = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                names[digits(item.get("prdlstReportNo"))] = item.get("prdlstNm") or ""
    return names


def report_numbers(lines, known) -> list:
    """'품목보고번호' 옆 숫자를 먼저, 그 밖의 숫자는 HACCP 자료에 있는 번호만(바코드·전화번호를 거른다).
    번호 뒤에 다른 숫자가 붙어 읽히면(예: '200105495411 120g') HACCP 자료에 있는 가장 긴 앞부분을 쓴다."""
    found = []
    for m in LABELED.findall(" | ".join(lines)):  # 줄 경계(|)는 넘어서 숫자를 잇지 않는다
        n = digits(m)
        hit = next((n[:k] for k in range(len(n), 7, -1) if n[:k] in known), None)
        if hit or 8 <= len(n) <= 16:
            found.append(hit or n)
    for line in lines:
        found += [n for n in BARE.findall(re.sub(r"[ \-]", "", line)) if n in known]
    return list(dict.fromkeys(found))


def is_back(lines, nums) -> bool:
    return bool(nums) or "원재료" in "".join(lines).replace(" ", "") or len(lines) >= 15


def product_of(num: str, gold: dict, haccp: dict) -> tuple:
    """품목보고번호 -> (id, 라벨 사진 역할, 메모)."""
    where, name = gold.get(num), haccp.get(num, "")
    if where and where[0] == "test":
        return where[1], "back", f"시험 세트 {name}".strip()
    if where:
        return f"N_{num}", "skip", f"개발 세트 {where[1]}라 뺌 {name}".strip()
    if num in haccp:
        return f"N_{num}", "back", f"목록 밖 {name}"
    return f"N_{num}", "back", "목록 밖, HACCP에 없음(사진 글자로 정답)"


def group_photos(records, known) -> list:
    """앞면이 나오면 새 제품, 뒤따르는 라벨 사진은 그 제품. 라벨 사진의 번호가 앞 제품과 다르면 새 제품.
    읽지 못한 사진은 따로."""
    groups = []
    for rec in records:
        if rec.get("error"):
            groups.append({"photos": [(rec, "error")], "nums": []})
            continue
        nums = report_numbers(rec.get("lines", []), known)
        role = "back" if is_back(rec.get("lines", []), nums) else "front"
        last = groups[-1] if groups else None
        if (role == "front" or last is None or last["photos"][0][1] == "error"
                or (nums and last["nums"] and nums[0] not in last["nums"])):
            groups.append({"photos": [], "nums": []})
        groups[-1]["photos"].append((rec, role))
        groups[-1]["nums"] += nums
    return groups


def draft(records, gold: dict, haccp: dict) -> list:
    """stage.json 기록 -> sort.tsv 줄 [(번호, 원본, id, 역할, 메모)]."""
    rows = []
    for g in group_photos(records, haccp):
        has_back = any(role == "back" for _, role in g["photos"])
        if g["nums"]:
            pid, back_role, memo = product_of(g["nums"][0], gold, haccp)
        else:
            pid, back_role, memo = "?", "back", "번호를 못 찾음, 사진을 보고 채울 것"
        for rec, role in g["photos"]:
            no, src = rec.get("no", ""), rec.get("source", "")
            if role == "error":
                rows.append((no, src, "?", "skip", f"읽기 실패: {rec['error']}"))
            elif not has_back:
                rows.append((no, src, pid, "skip", "앞면만 있음, 확인할 것: " + " ".join(rec.get("lines", [])[:3])))
            elif role == "front":
                front_role = "skip" if back_role == "skip" else "front"
                rows.append((no, src, pid, front_role, "앞면: " + " ".join(rec.get("lines", [])[:3])))
            else:
                rows.append((no, src, pid, back_role, memo))
    return rows


def write_rows(rows, path: Path) -> None:
    lines = [HEADER] + ["\t".join(r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def stage(src: Path, stage_dir: Path, sort_path: Path, gold_dir: Path, items: Path, force: bool) -> int:
    if not src.is_dir():
        print(f"원본 폴더가 없다: {src}", file=sys.stderr)
        return 2
    if stage_dir.exists() and any(stage_dir.iterdir()):
        if not force:
            print(f"이미 정리한 사진이 있다: {stage_dir}\n사진을 더 넣고 다시 정리하려면 --force"
                  " (번호는 찍은 시각 순서다. apply가 번호와 원본 파일이 맞는지 다시 본다)", file=sys.stderr)
            return 2
        shutil.rmtree(stage_dir)
    swift = shutil.which("swift")
    if not swift:
        print("swift가 없다. 맥에서 xcode-select --install 뒤에 다시 돌린다", file=sys.stderr)
        return 2
    done = subprocess.run([swift, str(HERE / "photo_tool.swift"), str(src), str(stage_dir)])
    if not (stage_dir / "stage.json").exists():
        print(f"사진 정리 실패(코드 {done.returncode}). 위 메시지를 볼 것", file=sys.stderr)
        return 1
    records = json.loads((stage_dir / "stage.json").read_text(encoding="utf-8"))
    rows = draft(records, gold_index(gold_dir), load_haccp(items))
    out = sort_path if not sort_path.exists() else sort_path.with_name("sort.draft.tsv")
    write_rows(rows, out)
    count = lambda role: sum(r[3] == role for r in rows)  # noqa: E731
    print(f"사진 {len(rows)}장: 라벨 {count('back')}, 앞면 {count('front')}, 뺌 {count('skip')}, "
          f"id 모름 {sum(r[2] == '?' for r in rows)} -> {out}")
    print(f"모아 보기: {stage_dir}/sheet_*.jpg")
    return 1 if done.returncode else 0


# ---------- apply: 실험 폴더에 나눠 넣기 ----------
def read_sort(path: Path) -> list:
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 4:
            raise SystemExit(f"{path.name} {i}번째 줄: 칸이 모자란다(번호, 원본, id, 역할, 메모)")
        rows.append(tuple(parts[:4]) + (parts[4] if len(parts) > 4 else "",))
    return rows


def gold_test_ids(gold_dir: Path) -> set:
    path = gold_dir / "test.jsonl"
    return {json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def check_row(row, sources: dict, gold: dict, tests: set) -> list:
    no, src, pid, role, memo = row
    errors = []
    if sources.get(no) != src:
        errors.append(f"{no}: 정리 폴더의 원본은 '{sources.get(no)}'인데 sort.tsv에는 '{src}' (다시 정리했다면 초안부터)")
    if role not in ROLES:
        return errors + [f"{no}: 역할 '{role}'은 front·back·skip 중 하나"]
    if role == "skip":
        return errors + ([] if memo else [f"{no}: skip은 메모에 이유를 적는다"])
    if not ID_RE.fullmatch(pid):
        return errors + [f"{no}: id '{pid}'는 B_test_085 또는 N_<품목보고번호> 꼴"]
    if pid.startswith("B_test_") and pid not in tests:
        errors.append(f"{no}: {pid}는 시험 세트에 없다")
    where = gold.get(digits(pid)) if pid.startswith("N_") else None
    if where:
        hint = "개발 세트 제품이라 뺀다(skip)" if where[0] == "dev" else "시험 세트 제품이니 그 id를 쓴다"
        errors.append(f"{no}: {pid}는 {where[1]}. {hint}")
    return errors


def check_rows(rows, stage_dir: Path, gold_dir: Path) -> tuple:
    """(틀린 곳, 제품별 라벨 사진 번호, 제품별 앞면 번호)."""
    records = json.loads((stage_dir / "stage.json").read_text(encoding="utf-8"))
    sources = {r.get("no"): r.get("source") for r in records if not r.get("error")}
    gold, tests = gold_index(gold_dir), gold_test_ids(gold_dir)
    errors, backs, fronts, seen = [], {}, {}, set()
    for row in rows:
        no, _, pid, role, _ = row
        if no in seen:
            errors.append(f"{no}: 두 번 나온다")
        seen.add(no)
        row_errors = check_row(row, sources, gold, tests)
        errors += row_errors
        if not row_errors and role in ("back", "front"):
            (backs if role == "back" else fronts).setdefault(pid, []).append(no)
    errors += [f"{no}: sort.tsv에 없다" for no in sorted(set(sources) - seen)]
    for pid, nos in fronts.items():
        if len(nos) > 1:
            errors.append(f"{pid}: 앞면이 {len(nos)}장({', '.join(nos)}). 하나만 front로 두고 나머지는 skip")
        if pid not in backs:
            errors.append(f"{pid}: 앞면만 있고 라벨 사진(back)이 없다")
    return errors, backs, fronts


def copy_plan(backs: dict, fronts: dict, stage_dir: Path, photos: Path, front_dir: Path) -> tuple:
    """([(정리 사진, 옮길 곳)], 틀린 곳). 이미 다른 사진이 있으면 덮어쓰지 않는다(CLOVA raw와 어긋나지 않게)."""
    pairs = [(stage_dir / f"{no}.jpg", photos / pid / f"{k}.jpg")
             for pid, nos in backs.items() for k, no in enumerate(nos, 1)]
    pairs += [(stage_dir / f"{nos[0]}.jpg", front_dir / f"{pid}.jpg") for pid, nos in fronts.items()]
    errors = [f"{dst}: 이미 다른 사진이 있다" for src, dst in pairs
              if dst.exists() and dst.read_bytes() != src.read_bytes()]
    if photos.exists():
        wanted = {dst for _, dst in pairs}
        extra = sorted(str(p) for d in photos.iterdir() if d.is_dir() for p in d.iterdir()
                       if p.is_file() and not p.name.startswith(".") and p not in wanted)
        errors += [f"{p}: sort.tsv에 없는 사진이 실험 폴더에 있다" for p in extra]
    return pairs, errors


def apply(sort_path: Path, stage_dir: Path, photos: Path, front_dir: Path, gold_dir: Path) -> int:
    if not sort_path.exists() or not (stage_dir / "stage.json").exists():
        print(f"sort.tsv나 정리 폴더가 없다. stage부터: {sort_path}, {stage_dir}", file=sys.stderr)
        return 2
    errors, backs, fronts = check_rows(read_sort(sort_path), stage_dir, gold_dir)
    pairs, copy_errors = copy_plan(backs, fronts, stage_dir, photos, front_dir) if not errors else ([], [])
    if errors or copy_errors:
        print("\n".join(errors + copy_errors), file=sys.stderr)
        print(f"틀린 곳 {len(errors) + len(copy_errors)}개. 아무것도 옮기지 않았다", file=sys.stderr)
        return 2
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copyfile(src, dst)
    n_test = sum(pid.startswith("B_test_") for pid in backs)
    n_backs = sum(len(nos) for nos in backs.values())
    print(f"제품 {len(backs)}개(시험 세트 {n_test}, 목록 밖 {len(backs) - n_test}), "
          f"라벨 사진 {n_backs}장(CLOVA {n_backs}번), 앞면 {len(fronts)}장 -> {photos}")
    return 0


def main(argv=None, stage_dir: Path = STAGE, photos: Path = PHOTOS, front_dir: Path = FRONTS,
         sort_path: Path = SORT, gold_dir: Path = GOLD, items: Path = ITEMS) -> int:
    ap = argparse.ArgumentParser(description="EXP-006 사진 정리 (맥 전용)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("stage", help="찍은 순서로 번호를 붙이고 sort.tsv 초안을 쓴다")
    st.add_argument("src", type=Path, help="원본 사진 폴더")
    st.add_argument("--force", action="store_true", help="이미 정리한 폴더를 지우고 다시 정리한다")
    sub.add_parser("apply", help="sort.tsv대로 실험 폴더에 나눠 넣는다")
    args = ap.parse_args(argv)
    if args.cmd == "stage":
        return stage(args.src, stage_dir, sort_path, gold_dir, items, args.force)
    return apply(sort_path, stage_dir, photos, front_dir, gold_dir)


if __name__ == "__main__":
    sys.exit(main())
