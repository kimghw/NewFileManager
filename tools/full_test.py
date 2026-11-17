"""전체 시험 — 하루 한 번(2026-11-17 사용자 "고친 부분만 테스트 하고, 이후에 하루에 한번 사용자가 요청하거나 24시간 이내에 테스트 하지 않으면
사용자에게 알리고 테스트 하도록, 또는 cpu를 사용량이 낮은 경우 테스트 진행하도록" — 원본 spec/spec_워크플로우.md ② §12).

    python -X utf8 tools/full_test.py               전체 시험을 돌린다 — pytest 전체(run_pytest.py) → 화면 검사 기본 묶음(run_ui_gates.py), 차례로(같이 돌리지 않는다) · 기록을 남긴다
    python -X utf8 tools/full_test.py --due         돌릴 때인가 — 마지막 전체 시험 · 지난 시간 · 도는 중인가 · CPU · 판단(사람이 읽는 글)
    python -X utf8 tools/full_test.py --due --hook  훅(UserPromptSubmit — .claude/settings.json)용: 돌릴 때일 때만 JSON 한 줄(맥락 글 + 사용자에게 보일 한 줄), 아니면 아무것도 안 찍는다

돌릴 때(decide):
  ① 마지막 전체 시험이 끝난 지 24시간이 지났다(기록이 없어도) → "24h": 사용자에게 알리고 돌린다(CPU 와 상관없이)
  ② 오늘(이 PC 의 날짜) 아직 안 돌렸고 · 마지막에서 12시간이 지났고 · CPU 사용량이 낮다(2초 평균 25% 미만) → "idle": 돌리고 한 줄로 알린다
  그 밖 → 안 돌린다. 다른 세션이 전체 시험을 돌리고 있으면(잠금 — 살아 있는 프로세스) 안 돌린다. 사용자가 청하면 언제든 돌린다(판단과 상관없이).
기록(artifacts/full_test/ — 세션들이 같이 본다): last.json(마지막 전체 시험) · history.jsonl · lock.json(도는 동안) · cpu.json(CPU 를 잰 때 — 10분에 한 번만 재서 훅이 매번 2초를 기다리지 않게) ·
  <때>/(pytest.out · gates.out · 화면 검사 그림). 끝까지 돈 실행만 기록한다(실패도 기록 — 24시간은 다시 센다). 중간에 끊긴 실행은 기록하지 않는다.
하나라도 떨어지면 종료 코드 1 · 이미 도는 중이면 2."""
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
LAST, HISTORY, LOCK, CPU = DIR / "last.json", DIR / "history.jsonl", DIR / "lock.json", DIR / "cpu.json"
FULL_HOURS = 24        # ① 이만큼 지나면 알리고 돌린다
IDLE_MIN_HOURS = 12    # ② 한가할 때 돌리는 것도 마지막에서 이만큼은 지나야(자정 넘어 곧바로 또 돌지 않게)
CPU_LOW = 25.0         # ② 「CPU 사용량이 낮다」 = 2초 평균 이 % 미만(에이전트 판단 — 8114 서버 · 다른 세션이 늘 조금 쓴다)
CPU_SAMPLE_S, CPU_CACHE_S = 2.0, 600
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


def cpu_now():
    """CPU 사용량 %(2초 평균) — 10분 안에 잰 값이 있으면 그것(훅이 말마다 2초를 기다리지 않게). 못 재면 None."""
    c = _read(CPU)
    if c and time.time() - float(c.get("at", 0)) < CPU_CACHE_S:
        return float(c["pct"])
    try:
        import psutil
        pct = float(psutil.cpu_percent(interval=CPU_SAMPLE_S))
    except Exception:  # noqa: BLE001
        return None
    try:
        _write(CPU, {"at": time.time(), "pct": pct})
    except OSError:
        pass
    return pct


def decide(last_end, now, busy, cpu_fn):
    """돌릴 때인가 → (판단, 까닭). 판단 = "running"(다른 실행이 도는 중) · "24h"(알리고 돌린다) · "idle"(돌리고 알린다) · "wait"(오늘 아직이지만 CPU 가 바쁘다) · "no".
    cpu_fn 은 그것이 필요할 때만 부른다(오늘 이미 돌렸으면 CPU 를 재지 않는다)."""
    if busy:
        return "running", "다른 세션이 전체 시험을 돌리고 있습니다"
    if last_end is None:
        return "24h", "전체 시험 기록이 없습니다"
    age = now - last_end
    if age >= dt.timedelta(hours=FULL_HOURS):
        return "24h", f"마지막 전체 시험이 {_ago(age)}입니다(24시간 지남)"
    if last_end.date() == now.date() or age < dt.timedelta(hours=IDLE_MIN_HOURS):
        return "no", f"마지막 전체 시험 {_ago(age)} — 오늘 몫은 했습니다" if last_end.date() == now.date() else f"마지막 전체 시험 {_ago(age)} — {IDLE_MIN_HOURS}시간 안"
    pct = cpu_fn()
    if pct is not None and pct < CPU_LOW:
        return "idle", f"오늘 아직 전체 시험을 안 돌렸고 CPU 가 한가합니다({pct:.0f}% < {CPU_LOW:.0f}%)"
    return "wait", f"오늘 아직 전체 시험을 안 돌렸지만 CPU 가 바쁩니다({'못 잼' if pct is None else f'{pct:.0f}%'}) — 한가해지면 돌립니다(늦어도 24시간이 되면)"


def status(now=None):
    now = now or dt.datetime.now()
    last, busy = _read(LAST), running()
    kind, why = decide(_when((last or {}).get("end")), now, busy, cpu_now)
    return {"kind": kind, "why": why, "last": last, "busy": busy}


def due(hook):
    s = status()
    if hook:
        if s["kind"] not in ("24h", "idle"):
            return 0
        act = ("사용자에게 먼저 한 줄로 알리고 " if s["kind"] == "24h" else "") + "`python -X utf8 tools/full_test.py` 를 백그라운드(run_in_background)로 돌린다"
        ctx = (f"[전체 시험 — CLAUDE.md 「시험 — 고친 곳만, 전체는 하루 한 번」] {s['why']}. 이번 턴에 {act}"
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


def run():
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
    a = ap.parse_args()
    if a.due:
        try:
            sys.exit(due(a.hook))
        except Exception as e:  # noqa: BLE001 — 훅은 사용자의 말을 막지 않는다
            if not a.hook:
                raise
            print(f"full_test --due 실패: {e}", file=sys.stderr)
            sys.exit(0)
    sys.exit(run())
