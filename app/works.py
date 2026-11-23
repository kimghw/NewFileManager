"""작업 저장소(spec_작업 ② §2·§4·§5) — 올린 파일마다 폴더 하나: 원본·지금 편집 상태·기록(log.jsonl)·검증 기록·출력 파일.

폴더 %LOCALAPPDATA%\\NewFileManager\\works\\<작업 id>, env NFM_WORKS(off·0 이면 저장 끔). 서버(server.py)가 세션 상태를 묶어 넘기고
이 모듈은 파일만 다룬다(문서 객체를 모름)."""
import gzip
import hashlib
import json
import os
import pickle
import re
import shutil
import threading
import time
import zlib
from pathlib import Path

ID = re.compile(r"^[0-9a-f]{12}$")
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def root() -> Path | None:
    env = os.environ.get("NFM_WORKS")
    if env is not None and env.strip().lower() in ("off", "0", ""):
        return None
    if env:
        return Path(env)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "works"


def enabled() -> bool:
    return root() is not None


def folder(wid: str) -> Path | None:
    """작업 폴더 — id 꼴(12자 16진)이 아니거나 저장이 꺼져 있으면 None(경로를 받지 않는다)."""
    base = root()
    if base is None or not isinstance(wid, str) or not ID.match(wid):
        return None
    return base / wid


def _lock(wid) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(wid, threading.Lock())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}-{threading.get_ident()}")
    try:
        tmp.write_bytes(data)
    except OSError:  # 디스크가 찼을 때(Errno 28) 반쯤 쓴 사본이 남아 자리를 더 잡지 않게 — 대상 파일은 그대로(2026-11-23 C: 0 바이트)
        tmp.unlink(missing_ok=True)
        raise
    for k in range(6):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: 대상 파일을 다른 손잡이(같은 때 읽는 스레드·백신·색인기)가 잠깐 잡고 있으면 바꿔 넣기가 거절된다 — 몇 번 다시(2026-11-10)
            if k == 5:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.02 * (k + 1))


def _write_json(path: Path, obj):
    _write(path, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _read_json(path: Path):
    for k in range(5):
        try:
            return json.loads(path.read_text("utf-8"))
        except PermissionError:  # Windows: 다른 스레드가 막 바꿔 넣는 중인 파일은 열기가 거절된다(references/Windows_파일_바꿔넣기.md) — 잠깐 뒤 다시
            time.sleep(0.01 * (k + 1))
        except (OSError, ValueError):
            return None
    return None


# ---- 작업 만들기·목록·지우기 -----------------------------------------------------------------------------

def create(wid, name, fmt, data, source="upload") -> dict | None:
    d = folder(wid)
    if d is None:
        return None
    now = time.time()
    work = {"id": wid, "name": name, "format": fmt, "size": len(data), "sha256": sha256(data), "source": source,
            "created": now, "updated": now, "rev": 0, "edited": 0, "verify": {}}
    with _lock(wid):
        _write(d / f"original.{fmt}", data)
        _write_json(d / "work.json", work)
    log(wid, "create", rev=0, name=name, size=len(data), sha256=work["sha256"], source=source)
    return work


def work(wid) -> dict | None:
    d = folder(wid)
    w = _read_json(d / "work.json") if d else None
    return w if isinstance(w, dict) and w.get("id") == wid else None


def update(wid, **fields) -> dict | None:
    """work.json 필드를 고친다(verify 는 종류별로 합침)."""
    d = folder(wid)
    if d is None:
        return None
    with _lock(wid):
        w = work(wid)
        if w is None:
            return None
        if "verify" in fields:
            w["verify"] = {**w.get("verify", {}), **fields.pop("verify")}
        w.update(fields, updated=time.time())
        _write_json(d / "work.json", w)
        return w


def list_works() -> list[dict]:
    """최근 바뀐 차례. 못 읽는 폴더는 빼기만 한다(지우지 않음)."""
    base = root()
    if base is None or not base.is_dir():
        return []
    out = []
    for p in base.iterdir():
        if p.is_dir() and ID.match(p.name):
            w = work(p.name)
            if w is not None:
                out.append(w)
    return sorted(out, key=lambda w: w.get("updated", 0), reverse=True)


def same_works(name, fmt, sha, job=None) -> list[dict]:
    """같은 파일(이름·형식·올린 원본 sha256 이 모두 같음)로 만든 작업들 — 이어 열 차례(spec_작업 ② §1 「같은 파일은 묻고 연다」: 「같은 파일 고르기」 의 줄 차례).
    sha256 은 올린 원본 것이라 확정해도 그대로다(② §8). 최근 바뀐 차례이고, job(고른 TASK — ② §15)이 있으면 그 TASK 의 작업 → TASK 가 빈 작업 → 그 밖 차례(저마다 최근 차례)."""
    rows = [w for w in list_works() if w.get("sha256") == sha and w.get("name") == name and w.get("format") == fmt]   # 최근 바뀐 차례
    if job:
        rows.sort(key=lambda w: 0 if ((w.get("task") or {}).get("job") or "") == job else 1 if not (w.get("task") or {}).get("job") else 2)   # 안정 정렬 — 같은 칸 안은 최근 차례 그대로
    return rows


def find_same(name, fmt, sha, job=None) -> dict | None:
    """같은 파일로 만든 작업 가운데 이어 열 것(same_works 의 맨 앞) — 묻지 않고 이어 여는 길(예제 열기 · ?ask 없는 옛 화면 — spec_작업 ② §1)."""
    rows = same_works(name, fmt, sha, job)
    return rows[0] if rows else None


class _Targets(dict):
    """할 일 → 목적 문서의 첨부 파일 종류. 붙박이 TASK 는 사전의 값이고, **조립한 TASK**(app/custom_tasks.py — spec_워크플로우 ② §14)는 그 저장소에서 읽는다 —
    `TARGET_FILE.get(job)` · `job in TARGET_FILE` · `TARGET_FILE[job]` 을 쓰는 곳이 조립한 TASK 를 따로 알 필요가 없다. 사전의 내용(견줌 · 돌기)은 붙박이 것 그대로다.
    **문서 하나로 조립한 것**(custom_tasks.is_single — 원본 없음)도 그 문서의 종류를 준다(그 문서가 곧 목적 문서다 — 보이는 이름 · 고정 양식의 칸 · 전환할 때의 문서 종류가 이것을 읽는다).
    붙박이 문서 하나(양식 표준화 · 양식 맞추기)는 여기 없다(None) — 「목적 종류가 있으면 원본 문서도 있다」 고 읽는 곳(문서 쌍 unit_steps.pair)은 is_single 로 가른다."""

    def get(self, job, default=None):
        if dict.__contains__(self, job):
            return dict.__getitem__(self, job)
        from app import custom_tasks   # 가벼운 모듈(다른 app 모듈을 안 가져온다)
        return custom_tasks.target_file(job) or default

    def __contains__(self, job):
        return self.get(job) is not None

    def __getitem__(self, job):
        got = self.get(job)
        if got is None:
            raise KeyError(job)
        return got


TARGET_FILE = _Targets({"plan_to_report": "report", "plan_merge": "plan"})  # 할 일 → 목적 문서(내용을 받는 문서)의 첨부 파일 종류: 이관의 연차보고서 · 취합의 취합본(spec_작업 ② §10 「목적 문서의 보이는 이름」)
_NOT_IN_FILE_NAME = re.compile(r'[\\/:*?"<>|]+')
# 임시 프로젝트 이름(spec_작업 ② §17 「임시 프로젝트」 — 이름 없이 TASK 를 시작하면 서버가 붙이는 「임시 프로젝트 N」). 원본은 여기 — projects.TEMP_RE 가 이것이다(projects 가 works 를 가져다 쓰므로 여기 둔다).
# 보이는 이름 · 프레임 이름에는 붙이지 않는다 — 임시 이름이 문서 이름 · 내려받는 파일 이름에 남지 않게(이름을 정하면 그때 붙는다)
TEMP_PROJECT_RE = re.compile(r"임시 프로젝트 [1-9][0-9]{0,8}")


def _named_project(task) -> str:
    """보이는 이름에 붙일 프로젝트 이름 — 파일 이름에 못 쓰는 글자는 「_」, 임시 이름이면 ""."""
    project = " ".join(str((task or {}).get("project") or "").split())
    return "" if TEMP_PROJECT_RE.fullmatch(project) else _NOT_IN_FILE_NAME.sub("_", project).strip()


# 프레임 이름(spec_작업 ② §10 「프레임 이름」 — 2026-11-14 사용자 "프로젝트 구성 반영이 완료 하면 사업계획서_{프로젝트이름}_프레임 .. 이라고 파일명을 저장하도록"):
# 양식 표준화 · 양식 맞추기 TASK → 맞추는 문서의 첨부 파일 종류. 그 문서에 프로젝트 구성을 반영하면 그것이 그 프로젝트의 프레임이다. 이관·취합의 문서는 뒤에 내용이 들어가므로 여기 없다.
FRAME_FILE = {"plan_fit": "plan", "report_fit": "report"}
FILE_LABEL = {"plan": "사업계획서", "report": "연차보고서"}   # 첨부 파일 종류의 이름(화면 app.js WORK_TASK.file 과 같게)
FRAME_TAIL = "프레임"


ALIAS_MAX = 40


def normalize_alias(alias) -> str:
    """별칭(spec_작업 ② §10 「별칭」) — 앞뒤를 떼고 빈칸을 하나로. 글이 아니면 ValueError, 길이는 부르는 쪽이 본다."""
    if not isinstance(alias, str):
        raise ValueError("별칭은 글이어야 합니다")
    return " ".join(alias.split())


def frame_stem(task, framed) -> str | None:
    """프레임 이름의 몸통 「<첨부 파일 종류>_<프로젝트 이름>_프레임」(spec_작업 ② §10 「프레임 이름」) | None(프레임 이름을 안 쓰는 문서).
    framed = 그 문서에 프로젝트 구성을 반영한 기록이 있음. 양식 표준화 · 양식 맞추기 TASK 의 맞추는 문서이고 프로젝트 이름이 있을 때만."""
    t = task if isinstance(task, dict) else {}
    kind = FRAME_FILE.get(t.get("job") or "")
    project = _named_project(t)   # 임시 이름이면 "" — 프레임 이름을 안 쓴다(이름을 정하면 그때)
    if not framed or not kind or t.get("file") != kind or not project:
        return None
    return f"{FILE_LABEL[kind]}_{project}_{FRAME_TAIL}"


def shown_name(name, task, alias=None, framed=False) -> str:
    """보이는 이름(spec_작업 ② §10) — 과제에 묶인 목적 문서는 「<올린 이름>_<과제 이름>.<확장자>」, 별칭이 있으면 확장자 앞에 「(<별칭>)」, 그 밖에는 올린 이름 그대로.
    프로젝트 구성을 반영한(framed) 양식 표준화 · 양식 맞추기 문서는 올린 이름 대신 「<첨부 파일 종류>_<프로젝트 이름>_프레임.<확장자>」(frame_stem — 별칭은 그 뒤에).
    저장된 이름(work.json `name`)은 안 바꾼다 — 같은 파일 이어 열기(find_same)·양식 판정(파일 이름 꼴)이 올린 이름을 본다. 이미 그 꼬리로 끝나면 두 번 안 붙인다."""
    t = task if isinstance(task, dict) else {}
    kind = TARGET_FILE.get(t.get("job") or "")
    project = _named_project(t)   # 임시 이름이면 "" — 올린 이름 뒤에 붙이지 않는다
    tag = _NOT_IN_FILE_NAME.sub("_", alias).strip() if isinstance(alias, str) else ""
    frame = frame_stem(t, framed) if name else None
    if not name or ((not kind or t.get("file") != kind or not project) and not tag and not frame):
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    if frame:   # 올린 이름을 안 쓴다 — 같은 빈 서식을 프로젝트마다 올려도 프레임은 프로젝트 이름으로 갈린다
        return frame + (f"({tag})" if tag else "") + (f".{ext}" if ext else "")
    if tag and stem.endswith(f"({tag})"):   # 올린 이름이 이미 그 꼬리로 끝남 — 프로젝트 꼬리도 그 앞에 있다고 본다
        return name
    if kind and t.get("file") == kind and project and not stem.endswith("_" + project):
        stem = f"{stem}_{project}"
    return stem + (f"({tag})" if tag else "") + (f".{ext}" if ext else "")


def shown(w) -> str:
    """작업(work.json) 하나의 보이는 이름 — framed(프로젝트 구성을 반영한 문서 — 서버가 편집 상태와 함께 적는다)면 프레임 이름."""
    w = w if isinstance(w, dict) else {}
    return shown_name(w.get("name"), w.get("task"), w.get("alias"), bool(w.get("framed")))


def mark(wid, **fields) -> dict | None:
    """work.json 필드를 고치되 바뀐 때(updated)는 그대로 — 내용이 아니라 표시만 맞출 때(옛 작업을 다시 열 때의 framed)."""
    d = folder(wid)
    if d is None:
        return None
    with _lock(wid):
        w = work(wid)
        if w is None:
            return None
        w.update(fields)
        _write_json(d / "work.json", w)
        return w


def workflow_update(wid, job, **fields) -> dict | None:
    """문서의 워크플로우 한 항목만 합친다. 다른 항목·문서 요약을 덮지 않고 같은 진행 상태는 다시 쓰지 않는다."""
    d = folder(wid)
    if d is None:
        return None
    with _lock(wid):
        w = work(wid)
        if w is None:
            return None
        rows = list(w.get("workflows") or [])
        index = next((i for i, row in enumerate(rows) if row.get("job") == job), None)
        old = rows[index] if index is not None else None
        row = {**(old or {"job": job, "status": "ready", "done": 0, "total": 0}), **fields}
        if old == row:
            return w
        row["updated"] = time.time()
        if index is None:
            rows.append(row)
        else:
            rows[index] = row
        w["workflows"] = rows
        _write_json(d / "work.json", w)
        return w


def workflow_remove(wid, job) -> dict | None:
    """문서의 워크플로우 목록에서 그 워크플로우의 줄(job 이 같은 줄 — 모두)을 뺀다 → 고친 작업 | None(작업 없음). 문서 · 분석 · 다른 줄은 그대로(진행 요약 줄만 — 대시보드
    「이 문서의 워크플로우」). 그런 줄이 없으면 쓰지 않고 그대로 돌려준다 — 있는지 · 지금 워크플로우인지는 부르는 쪽이 먼저 본다(app/workflow_runs.py). workflow_update 와 같은 잠금 · 같은 저장."""
    d = folder(wid)
    if d is None:
        return None
    with _lock(wid):
        w = work(wid)
        if w is None:
            return None
        rows = list(w.get("workflows") or [])
        keep = [row for row in rows if not (isinstance(row, dict) and row.get("job") == job)]
        if len(keep) == len(rows):
            return w
        w["workflows"] = keep
        _write_json(d / "work.json", w)
        return w


RESET_KEEP = ("work.json", "log.jsonl", "commits", "outputs", "reset")   # 작업 내용 초기화가 제자리에 두는 것(spec_작업 ② §3-1) — 올린 원본(original.<ext>)과 함께


def reset_files(wid, rev, carry=(), tries=6) -> dict | None:
    """작업 내용 초기화(spec_작업 ② §3-1)의 파일 쪽 — 남기는 것(RESET_KEEP · original.*) 밖의 항목을 `reset/<n>/` 으로 옮기고(지우지 않음)
    carry(옮긴 것 가운데 제자리에 사본을 되돌려 둘 상대 경로 — 양식 선택 등, 있을 때만) 를 되돌린 뒤 work.json 의 요약을 올린 직후로(rev 는 이어 센다 · 고친 문단 0 · 검증 요약 비움 · 프레임 표시 끔).
    → {n, archive, moved[이름]} | None(지운 작업 · 저장 끔). 다른 손잡이가 잡아 못 옮기면 몇 번 다시 뒤 OSError — 그때까지 옮긴 것은 그대로 둔다."""
    d = folder(wid)
    if d is None:
        return None
    with _lock(wid):
        w = work(wid)
        if w is None:
            return None
        box = d / "reset"
        box.mkdir(exist_ok=True)
        n = max([int(p.name) for p in box.iterdir() if p.name.isdigit()] + [0]) + 1
        dst = box / str(n)
        dst.mkdir()
        moved = []
        for p in sorted(d.iterdir(), key=lambda x: x.name):
            if p.name in RESET_KEEP or p.name.startswith("original."):
                continue
            for k in range(tries):
                try:
                    os.replace(p, dst / p.name)
                    break
                except OSError:   # Windows: 백신·색인기·읽는 스레드가 잠깐 잡음 — 몇 번 다시
                    if k == tries - 1:
                        raise
                    time.sleep(0.05 * (k + 1))
            moved.append(p.name)
        for rel in carry:
            src = dst / rel
            if src.is_file():
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, d / rel)
        w.update(rev=rev, edited=0, verify={}, framed=False, updated=time.time())
        _write_json(d / "work.json", w)
    return {"n": n, "archive": f"reset/{n}", "moved": moved}


def delete(wid, tries=6) -> bool:
    """작업 폴더를 지운다. work.json 을 먼저 지워 목록·다시 열기에서 곧바로 빠지게 하고, 나머지는 몇 번 다시 시도한다 —
    Windows 에서 백신·색인기가 막 쓴 파일을 잠깐 잡으면 rmtree 가 일부를 못 지운다(시험이 다른 PC 상태에서 빈 폴더가 남은 일, 2026-11-09)."""
    d = folder(wid)
    if d is None or not d.is_dir():
        return False
    with _lock(wid):
        for k in range(tries):
            try:
                (d / "work.json").unlink(missing_ok=True)
                shutil.rmtree(d)
            except FileNotFoundError:
                pass
            except OSError:
                time.sleep(0.05 * (k + 1))
                continue
            if not d.exists():
                return True
            time.sleep(0.05 * (k + 1))
    return not d.exists()


# ---- 편집 상태 ---------------------------------------------------------------------------------------

def save_state(wid, fmt, snap: dict, state: dict, **summary):
    """snap = struct.snapshot(doc)({"bytes", "dirty", "new"|"blobs", "ids"}), state = 세션 집합·매핑(JSON)."""
    d = folder(wid)
    if d is None:
        return
    # 직렬화를 먼저 끝낸다 — 못 쓰는 값이 있으면 파일을 하나도 안 바꾼다(셋이 어긋난 채 남지 않게)
    pkl = pickle.dumps({k: v for k, v in snap.items() if k != "bytes"}, protocol=pickle.HIGHEST_PROTOCOL)
    js = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with _lock(wid):
        if not (d / "work.json").exists():  # 지운 작업 — 되살리지 않는다
            return
        _write(d / f"current.{fmt}", snap["bytes"])
        _write(d / "doc.pkl", pkl)
        _write(d / "state.json", js)
    if summary:
        update(wid, **summary)


def set_aside_state(wid):
    """못 붙인 편집 상태(current·doc.pkl·state.json)를 <이름>.broken-<시각> 으로 옮긴다 — 지우지 않음."""
    d = folder(wid)
    if d is None:
        return
    tag = time.strftime("%Y%m%d-%H%M%S")
    with _lock(wid):
        for p in [*d.glob("current.*"), d / "doc.pkl", d / "state.json"]:
            if p.is_file() and ".broken-" not in p.name:
                try:
                    os.replace(p, p.with_name(f"{p.name}.broken-{tag}"))
                except OSError:
                    pass


def load(wid) -> dict | None:
    """{work, original, snap | None, state | None} — 편집 상태가 없거나 못 읽으면 snap None(원본으로 연다)."""
    d, w = folder(wid), work(wid)
    if d is None or w is None:
        return None
    fmt = w["format"]
    try:
        original = (d / f"original.{fmt}").read_bytes()
    except OSError:
        return None
    snap = state = None
    try:
        cur = d / f"current.{fmt}"
        if cur.exists() and (d / "doc.pkl").exists():
            snap = {**pickle.loads((d / "doc.pkl").read_bytes()), "bytes": cur.read_bytes()}
            state = _read_json(d / "state.json")
    except Exception:  # noqa: BLE001 — 깨진 묶음: 원본으로 열고 서버가 기록에 남긴다
        snap = state = None
    return {"work": w, "original": original, "snap": snap, "state": state}


# ---- 기록 ------------------------------------------------------------------------------------------

def log(wid, kind, **fields):
    d = folder(wid)
    if d is None:
        return
    line = json.dumps({"t": round(time.time(), 3), "kind": kind, **fields}, ensure_ascii=False, separators=(",", ":"))
    with _lock(wid):
        if not d.is_dir():
            return
        with open(d / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")


def events(wid) -> list[dict]:
    d = folder(wid)
    out = []
    try:
        with open(d / "log.jsonl", encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue  # 쓰다 끊긴 줄
    except (OSError, TypeError):
        pass
    return out


# ---- 검증 기록·출력 파일 ----------------------------------------------------------------------------------

def add_run(wid, kind, record: dict) -> int | None:
    """verify/<n>-<kind>.json 으로 남기고 n 을 돌려준다(작업 안에서 1부터)."""
    d = folder(wid)
    if d is None:
        return None
    with _lock(wid):
        if not (d / "work.json").exists():
            return None
        vd = d / "verify"
        n = 1 + max((int(p.name.split("-", 1)[0]) for p in vd.glob("*-*.json") if p.name.split("-", 1)[0].isdigit()), default=0) \
            if vd.is_dir() else 1
        _write_json(vd / f"{n}-{kind}.json", {"n": n, "kind": kind, **record})
    return n


def runs(wid) -> list[dict]:
    """검증 기록 요약 — 번호 차례."""
    d = folder(wid)
    vd = d / "verify" if d else None
    if vd is None or not vd.is_dir():
        return []
    out = []
    for p in vd.glob("*-*.json"):
        r = _read_json(p)
        if isinstance(r, dict) and isinstance(r.get("n"), int):
            out.append({k: r.get(k) for k in ("n", "kind", "status", "at", "seconds", "revision", "rev", "outputSha", "base")})  # base = 그때의 기준 확정(② §8)
    return sorted(out, key=lambda r: r["n"])


def run(wid, n) -> dict | None:
    d = folder(wid)
    vd = d / "verify" if d else None
    if vd is None or not vd.is_dir():
        return None
    for p in vd.glob(f"{int(n)}-*.json"):
        r = _read_json(p)
        if isinstance(r, dict) and r.get("n") == int(n):
            return r
    return None


def last_runs(wid) -> dict:
    """종류마다 마지막 검증 기록 전체 — 다시 열 때 결과로 보인다."""
    last = {}
    for r in runs(wid):
        last[r["kind"]] = r["n"]
    return {k: run(wid, n) for k, n in last.items()}


def add_output(wid, fmt, data: bytes) -> str:
    """outputs/<sha256 앞 16자>.<ext> — 같은 바이트는 한 번만. sha256 전체를 돌려준다."""
    h = sha256(data)
    d = folder(wid)
    if d is not None:
        p = d / "outputs" / f"{h[:16]}.{fmt}"
        with _lock(wid):
            if (d / "work.json").exists() and not p.exists():
                _write(p, data)
    return h


def file_path(wid, which) -> Path | None:
    w, d = work(wid), folder(wid)
    if w is None or which not in ("original", "current"):
        return None
    p = d / f"{which}.{w['format']}"
    if which == "current" and not p.exists():
        p = d / f"original.{w['format']}"
    return p if p.exists() else None


# ---- 확정(spec_작업 ② §8) — commits/<n>.json(요약) · commits/<n>.data.json.gz(블록 id 자리표·구분/개요 상태·변경 목록), 파일 바이트는 outputs/ ----

def _commit_dir(wid) -> Path | None:
    d = folder(wid)
    return d / "commits" if d else None


def commits(wid) -> list[dict]:
    """확정 요약 — 번호 차례(1부터). 올린 원본(확정 0)은 여기 없다(work.json 이 그 요약)."""
    cd = _commit_dir(wid)
    if cd is None or not cd.is_dir():
        return []
    out = []
    for p in cd.glob("*.json"):
        c = _read_json(p) if p.stem.isdigit() else None
        if isinstance(c, dict) and c.get("n") == int(p.stem):
            out.append(c)
    return sorted(out, key=lambda c: c["n"])


def head(wid) -> int:
    """마지막 확정 번호 — 없으면 0(올린 원본)."""
    cs = commits(wid)
    return cs[-1]["n"] if cs else 0


def commit(wid, n) -> dict | None:
    cd = _commit_dir(wid)
    c = _read_json(cd / f"{int(n)}.json") if cd else None
    return c if isinstance(c, dict) and c.get("n") == int(n) else None


def add_commit(wid, fmt, data: bytes, meta: dict, extra: dict) -> dict | None:
    """확정 하나를 남긴다 — 바이트는 outputs/(같은 바이트는 한 번), 요약·상세는 commits/. 번호는 작업 안에서 1부터.
    -> 요약 {n, at, sha256, size, **meta} | None(저장 꺼짐·지운 작업)."""
    d = folder(wid)
    if d is None:
        return None
    # 직렬화를 먼저 끝낸다 — 못 쓰는 값이 있으면 아무것도 안 남긴다
    blob = gzip.compress(json.dumps(extra, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
    sha = add_output(wid, fmt, data)
    with _lock(wid):
        if not (d / "work.json").exists():
            return None
        cd = d / "commits"
        n = 1 + max((int(p.stem) for p in cd.glob("*.json") if p.stem.isdigit()), default=0) if cd.is_dir() else 1
        rec = {"n": n, "at": round(time.time(), 3), "sha256": sha, "size": len(data), **meta}
        _write(cd / f"{n}.data.json.gz", blob)  # 상세 먼저 — 요약(목록에 보이는 것)이 있으면 상세도 있다
        _write_json(cd / f"{n}.json", rec)
    try:
        update(wid, commits=n)  # 목록용 요약일 뿐(마지막 확정 번호는 head() 가 commits/ 에서 읽는다) — 못 써도 확정은 남았다
    except OSError:
        pass
    return rec


def commit_data(wid, n) -> dict | None:
    """확정의 상세 {ids, division, outline, changes} — 없거나 깨졌으면 None."""
    cd = _commit_dir(wid)
    if cd is None:
        return None
    try:
        got = json.loads(gzip.decompress((cd / f"{int(n)}.data.json.gz").read_bytes()).decode("utf-8"))
    except (OSError, ValueError, EOFError, zlib.error):
        return None
    return got if isinstance(got, dict) else None


def commit_path(wid, n) -> Path | None:
    """그 확정의 파일 — 0 = 올린 원본."""
    w, d = work(wid), folder(wid)
    if w is None:
        return None
    if int(n) == 0:
        p = d / f"original.{w['format']}"
    else:
        c = commit(wid, n)
        if c is None or not isinstance(c.get("sha256"), str):
            return None
        p = d / "outputs" / f"{c['sha256'][:16]}.{w['format']}"
    return p if p.exists() else None


def commit_bytes(wid, n) -> bytes | None:
    """그 확정의 바이트 — 파일이 없거나 적어 둔 sha256 과 다르면 None(깨진 파일로 기준을 삼지 않는다)."""
    p = commit_path(wid, n)
    try:
        data = p.read_bytes() if p else None
    except OSError:
        return None
    if data is not None and int(n) and sha256(data) != commit(wid, n)["sha256"]:
        return None
    return data


# ---- 부가 기록(spec_구분_기준 ② §4 — 로그 한 줄 + 상세는 결과 파일) ------------------------------------------------

def add_detail(wid, kind, name, record: dict) -> str | None:
    """`<kind>/<name>.json` 에 상세 기록(JSON) — 기록 한 줄에 다 못 싣는 변경 목록 등. 작업 저장이 꺼져 있으면 None."""
    d = folder(wid)
    if d is None:
        return None
    safe = "".join(ch for ch in str(name) if ch.isalnum() or ch in "-_")[:40] or "x"
    with _lock(wid):
        if not (d / "work.json").exists():
            return None
        sub = d / kind
        sub.mkdir(exist_ok=True)
        _write_json(sub / f"{safe}.json", record)
    return f"{kind}/{safe}.json"


def detail_records(wid, kind) -> list:
    """`<kind>/*.json` 상세 기록들(고친 시각 차례 — 옛 것부터). 못 읽는 파일은 건너뛴다. 작업 저장이 꺼져 있거나 그 폴더가 없으면 []."""
    d = folder(wid)
    sub = d / kind if d is not None else None
    if sub is None or not sub.is_dir():
        return []
    try:
        paths = sorted(sub.glob("*.json"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return []
    return [rec for rec in (_read_json(p) for p in paths) if isinstance(rec, dict)]
