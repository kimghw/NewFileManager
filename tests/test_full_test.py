"""전체 시험의 때 판단(tools/full_test.py decide — spec_워크플로우 ② §12): 24시간이 지나면 알리고 돌림 · 오늘 아직이고 CPU 가 한가하면 돌림 · 하루 한 번."""
import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("full_test", ROOT / "tools" / "full_test.py")
FT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FT)

NOW = dt.datetime(2026, 11, 17, 15, 0)


def _cpu(pct):
    called = []

    def fn():
        called.append(1)
        return pct
    return fn, called


def test_no_record_or_over_24h_is_due_regardless_of_cpu():
    fn, called = _cpu(90.0)
    assert FT.decide(None, NOW, None, fn)[0] == "24h"
    assert FT.decide(NOW - dt.timedelta(hours=24, minutes=1), NOW, None, fn)[0] == "24h"
    assert not called  # 24시간이 지났으면 CPU 를 재지 않고 알리고 돌린다


def test_already_ran_today_does_not_measure_cpu():
    fn, called = _cpu(1.0)
    assert FT.decide(dt.datetime(2026, 11, 17, 0, 30), NOW, None, fn)[0] == "no"
    assert not called


def test_not_today_and_idle_cpu_runs_but_busy_cpu_waits():
    yday = dt.datetime(2026, 11, 16, 22, 0)  # 어제 · 17시간 전(12시간은 지났고 24시간은 안 됨)
    assert FT.decide(yday, NOW, None, _cpu(10.0)[0])[0] == "idle"
    assert FT.decide(yday, NOW, None, _cpu(60.0)[0])[0] == "wait"
    assert FT.decide(yday, NOW, None, _cpu(None)[0])[0] == "wait"  # 못 재면 기다린다(늦어도 24시간이 되면 돈다)


def test_idle_needs_min_gap_after_midnight():
    fn, called = _cpu(1.0)
    late = dt.datetime(2026, 11, 16, 23, 30)
    assert FT.decide(late, dt.datetime(2026, 11, 17, 2, 0), None, fn)[0] == "no"  # 날짜는 바뀌었지만 2시간 반 전
    assert not called


def test_running_elsewhere_blocks():
    assert FT.decide(None, NOW, {"pid": 1}, _cpu(1.0)[0])[0] == "running"


def test_hook_prints_json_only_when_due(tmp_path, monkeypatch):
    for k in ("DIR", "LAST", "HISTORY", "LOCK", "CPU"):
        monkeypatch.setattr(FT, k, tmp_path / getattr(FT, k).name if k != "DIR" else tmp_path)
    FT._write(FT.LAST, {"end": dt.datetime.now().isoformat(timespec="seconds"), "ok": True})
    assert FT.status()["kind"] == "no"
    FT._write(FT.LAST, {"end": (dt.datetime.now() - dt.timedelta(days=2)).isoformat(timespec="seconds"), "ok": True})
    s = FT.status()
    assert s["kind"] == "24h" and "24시간" in s["why"]


def test_hook_command_output_is_valid_json_or_empty():
    r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "tools" / "full_test.py"), "--due", "--hook"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0
    out = r.stdout.strip()
    if out:  # 돌릴 때면 훅 JSON 한 줄(맥락 글 + 사용자에게 보일 한 줄)
        d = json.loads(out)
        assert d["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit" and "full_test.py" in d["hookSpecificOutput"]["additionalContext"] and d["systemMessage"]
