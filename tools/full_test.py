"""전체 시험 — 밤(0시~7시)에만 · 하룻밤에 한 번(2026-11-27 사용자 "테스트는 수정한 부분만 하고,, 전체 테스트는 밤 12시에서 7시 사이에만 하도록 해줘" · "전체 테스트를 하고 있어 다른거 못쓰게"
— 낮에 도는 전체 시험이 PC 를 잡아 다른 일을 못 했다. 전: 2026-11-17 「24시간이 지나면 알리고 돌림 · CPU 가 한가하면 돌림」. 원본 spec/spec_워크플로우.md ② §12).

    python -X utf8 tools/full_test.py               전체 시험을 돌린다 — pytest 전체(run_pytest.py) → 화면 검사 기본 묶음(run_ui_gates.py), 차례로(같이 돌리지 않는다) · 기록을 남긴다.
                                                    밤 시간(0시~7시) 밖이면 돌리지 않고 종료 코드 3 — 사용자가 지금 돌리라고 직접 말했을 때만 --anytime
    python -X utf8 tools/full_test.py --due         돌릴 때인가 — 마지막 전체 시험 · 도는 중인가 · 판단(사람이 읽는 글)
    python -X utf8 tools/full_test.py --due --hook  훅(UserPromptSubmit — .claude/settings.json)용: 돌릴 때일 때만 JSON 한 줄(맥락 글 + 사용자에게 보일 한 줄), 아니면 아무것도 안 찍는다

돌릴 때(decide):
  지금이 밤 시간(이 PC 의 시계로 0시 이상 7시 미만)이고 · 오늘 0시 뒤에 끝난 전체 시험이 없다 → "night": 돌리고 한 줄로 알린다
  그 밖 → 안 돌린다(낮에는 며칠이 지났어도). 다른 세션이 전체 시험을 돌리고 있으면(잠금 — 살아 있는 프로세스) 안 돌린다.
기록(artifacts/full_test/ — 세션들이 같이 본다): last.json(마지막 전체 시험) · history.jsonl · lock.json(도는 동안) ·
  <때>/(pytest.out · gates.out · 화면 검사 그림). 끝까지 돈 실행만 기록한다(실패도 기록). 중간에 끊긴 실행은 기록하지 않는다.
하나라도 떨어지면 종료 코드 1 · 이미 도는 중이면 2 · 밤 시간 밖이면 3."""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "artifacts" / "full_test"
LAST, HISTORY, LOCK = DIR / "last.json", DIR / "history.jsonl", DIR / "lock.json"
NIGHT = (0, 7)         # 전체 시험을 돌리는 밤 시간 — 이 PC 의 시계로 0시 이상 7시 미만(2026-11-27 사용자 「밤 12시에서 7시 사이에만」)
GATE_PORT = 18500      # 화면 검사의 첫 포트 — 세션들이 고친 곳 검사에 쓰는 기본 18300~ 와 겹치지 않게(2026-11-17 첫 실행: 다른 세션의 검사가 18301 을 같이 써서 결과가 어긋남)


def _read(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _when(s):
    try:
        return dt.datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def _ago(td):
    h = int(td.total_seconds() // 3600)
    return f"{h // 24}일 {h % 24}시간 전" if h >= 24 else f"{h}시간 {int(td.total_seconds() % 3600 // 60)}분 전"


def running():
    """잠금이 살아 있나 — {pid, created, start} | None. 프로세스가 없거나 pid 가 다른 프로세스로 다시 쓰였으면(만든 때가 다름) 죽은 잠금."""
    lk = _read(LOCK)
    if not lk:
        return None
    try:
        import psutil
        p = psutil.Process(int(lk["pid"]))
        return lk if abs(p.create_time() - float(lk.get("created", 0))) < 2 else None
    except Exception:  # noqa: BLE001 — psutil 이 없거나 프로세스가 없다
        return None


def at_night(now):
    return NIGHT[0] <= now.hour < NIGHT[1]


def decide(last_end, now, busy):
    """돌릴 때인가 → (판단, 까닭). 판단 = "running"(다른 실행이 도는 중) · "night"(밤 시간이고 오늘 밤 아직 — 돌리고 알린다) · "no"."""
    if busy:
        return "running", "다른 세션이 전체 시험을 돌리고 있습니다"
    span = f"밤 {NIGHT[0]}시~{NIGHT[1]}시"
    if not at_night(now):
        return "no", f"전체 시험은 {span}에만 돌립니다(지금 {now:%H:%M})" + (f" — 마지막 {_ago(now - last_end)}" if last_end else " — 기록 없음")
    if last_end is not None and last_end >= now.replace(hour=0, minute=0, second=0, microsecond=0):
        return "no", f"마지막 전체 시험 {_ago(now - last_end)} — 오늘 밤 몫은 했습니다"
    return "night", f"{span}이고 오늘 밤 전체 시험을 아직 안 돌렸습니다(" + (f"마지막 {_ago(now - last_end)}" if last_end else "기록 없음") + ")"


def status(now=None):
    now = now or dt.datetime.now()
    last, busy = _read(LAST), running()
    kind, why = decide(_when((last or {}).get("end")), now, busy)
    return {"kind": kind, "why": why, "last": last, "busy": busy}


def due(hook):
    s = status()
    if hook:
        if s["kind"] != "night":
            return 0
        ctx = (f"[전체 시험 — CLAUDE.md 「시험 — 고친 곳만, 전체는 밤에만」] {s['why']}. 이번 턴에 `python -X utf8 tools/full_test.py` 를 백그라운드(run_in_background)로 돌리고 한 줄로 알린다"
               " — 이 세션이 지금 pytest·화면 검사를 돌리고 있으면 그것이 끝난 뒤에. 기다리지 말고 하던 일을 하고, 끝나면 결과(떨어진 것)를 사용자에게 알린다."
               " 사용자가 지금은 안 된다고 하면 돌리지 않는다.")
        print(json.dumps({"systemMessage": f"전체 시험: {s['why']} — 이번 턴에 돌립니다",
                          "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}, ensure_ascii=False))
        return 0
    last = s["last"]
    if last:
        print(f"마지막 전체 시험: {last.get('end', '?')[:16]} 끝남 · {'통과' if last.get('ok') else '실패'} · {last.get('head', '')}"
              f" · pytest {last.get('pytest', {}).get('code')} · 화면 검사 {last.get('gates', {}).get('code')} · 기록 {last.get('dir', '')}")
    else:
        print("마지막 전체 시험: 기록 없음")
    if s["busy"]:
        print(f"지금 도는 중: {s['busy'].get('start', '?')[:16]} 시작 · pid {s['busy'].get('pid')}")
    print(f"판단: {s['kind']} — {s['why']}")
    return 0


def _tail(path, n):
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [x.rstrip() for x in lines if x.strip()][-n:]


def _picked(path, n=80):
    """pytest 기록에서 남길 줄 — 묶음마다의 합계 줄 + 떨어진 시험(FAILED · ERROR) 전부(끝 몇 줄만 남기면 떨어진 시험이 잘린다 — 2026-11-17 첫 실행)."""
    keep = [x for x in _tail(path, 100000) if x.lstrip().startswith(("FAILED", "ERROR")) or re.search(r"\b\d+ (passed|failed)\b|^(병렬|차례)", x.strip())]
    return keep[:n]


def _git(*a):
    try:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def run(anytime=False):
    if not anytime and not at_night(dt.datetime.now()):  # 낮에 도는 전체 시험은 PC 를 잡는다 — 사용자가 직접 청했을 때만 --anytime
        print(f"전체 시험은 밤 {NIGHT[0]}시~{NIGHT[1]}시에만 돌립니다(지금 {dt.datetime.now():%H:%M}) — 고친 곳에 닿는 시험만 돌리세요. 사용자가 지금 돌리라고 직접 말했을 때만 --anytime")
        return 3
    DIR.mkdir(parents=True, exist_ok=True)
    if running():
        print(f"이미 도는 중입니다: {running()}")
        return 2
    import psutil
    me = psutil.Process()
    start = dt.datetime.now()
    try:  # 잠금 — 동시에 둘이 시작하면 하나만 연다(O_EXCL). 죽은 잠금(running() 이 None)은 지우고 다시
        LOCK.unlink(missing_ok=True)
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": me.pid, "created": me.create_time(), "start": start.isoformat(timespec="seconds")}, f)
    except FileExistsError:
        print("다른 실행이 막 시작했습니다")
        return 2
    out = DIR / start.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    head = _git("rev-parse", "--short", "HEAD")
    dirty = len([x for x in _git("status", "--porcelain").splitlines() if x.strip()])
    env = {**os.environ, "PYTHONUTF8": "1"}
    res = {}
    try:
        for name, cmd in (("pytest", [sys.executable, "-X", "utf8", "tools/run_pytest.py", "--tmp", str(out / "pytest_tmp")]),
                          ("gates", [sys.executable, "-X", "utf8", "tools/run_ui_gates.py", str(out / "gates"), "--port", str(GATE_PORT)])):
            t0 = time.time()
            print(f"▶ {name} …", flush=True)
            with (out / f"{name}.out").open("w", encoding="utf-8") as log:
                code = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
            res[name] = {"code": code, "secs": round(time.time() - t0), "tail": _tail(out / f"{name}.out", 30) if name == "gates" else _picked(out / f"{name}.out")}
            print(f"■ {name} — {'통과' if code == 0 else '실패'}(종료 코드 {code}) · {res[name]['secs']}초", flush=True)
        shutil.rmtree(out / "pytest_tmp", ignore_errors=True)  # 이 실행만의 임시 폴더(크다) — 기록은 pytest.out 에
        end = dt.datetime.now()
        rec = {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"), "secs": round((end - start).total_seconds()),
               "head": head + (f" + 안 올린 변경 {dirty}개" if dirty else ""), "dir": str(out), "ok": all(r["code"] == 0 for r in res.values()), **res}
        _write(LAST, rec)
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in rec.items() if k not in ("pytest", "gates")} | {k: res[k]["code"] for k in res}, ensure_ascii=False) + "\n")
    finally:
        LOCK.unlink(missing_ok=True)
    print(f"\n전체 시험 끝 — {'통과' if rec['ok'] else '실패'} · {rec['secs'] // 60}분 · 기록 {out}")
    for name, r in res.items():
        if r["code"] != 0:
            print(f"[{name}]")
            for x in r["tail"]:
                print("  " + x)
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--due", action="store_true")
    ap.add_argument("--hook", action="store_true")
    ap.add_argument("--anytime", action="store_true", help="밤 시간(0시~7시) 밖에도 돌린다 — 사용자가 지금 돌리라고 직접 말했을 때만")
    a = ap.parse_args()
    if a.due:
        try:
            sys.exit(due(a.hook))
        except Exception as e:  # noqa: BLE001 — 훅은 사용자의 말을 막지 않는다
            if not a.hook:
                raise
            print(f"full_test --due 실패: {e}", file=sys.stderr)
            sys.exit(0)
    sys.exit(run(a.anytime))
