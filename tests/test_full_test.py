"""전체 시험의 때 판단(tools/full_test.py decide — spec_워크플로우 ② §12): 밤 0시~7시에만 · 하룻밤에 한 번 · 낮에는 며칠이 지났어도 안 돌림."""
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

DAY = dt.datetime(2026, 11, 17, 15, 0)
NIGHT = dt.datetime(2026, 11, 17, 2, 0)


def test_daytime_never_runs_even_without_record_or_after_days():
    """2026-11-27 사용자 「전체 테스트는 밤 12시에서 7시 사이에만」 — 낮에는 기록이 없어도 · 며칠이 지났어도 돌릴 때가 아니다."""
    for last in (None, DAY - dt.timedelta(days=3), DAY - dt.timedelta(hours=25)):
        kind, why = FT.decide(last, DAY, None)
        assert kind == "no" and "0시~7시" in why
    for hour in (7, 8, 12, 23):  # 7시 정각부터는 밤 시간이 아니다
        assert FT.decide(None, DAY.replace(hour=hour, minute=0), None)[0] == "no"


def test_night_runs_once_per_night():
    assert FT.decide(None, NIGHT, None)[0] == "night"
    assert FT.decide(dt.datetime(2026, 11, 16, 23, 30), NIGHT, None)[0] == "night"   # 어젯밤 자정 전에 끝난 것은 오늘 밤 몫이 아니다
    assert FT.decide(dt.datetime(2026, 11, 16, 3, 0), NIGHT, None)[0] == "night"
    assert FT.decide(dt.datetime(2026, 11, 17, 0, 40), NIGHT, None)[0] == "no"       # 오늘 0시 뒤에 끝난 것이 있다
    for hour, minute in ((0, 0), (6, 59)):
        assert FT.decide(None, NIGHT.replace(hour=hour, minute=minute), None)[0] == "night"


def test_running_elsewhere_blocks():
    assert FT.decide(None, NIGHT, {"pid": 1})[0] == "running"


def test_run_refuses_outside_night_unless_anytime(monkeypatch, capsys):
    """낮에 `full_test.py` 를 그냥 부르면 돌지 않는다(종료 코드 3 — 잠금 · 기록을 만들지 않는다)."""
    class Noon(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 17, 12, 0)
    monkeypatch.setattr(FT.dt, "datetime", Noon)
    monkeypatch.setattr(FT, "running", lambda: (_ for _ in ()).throw(AssertionError("밤 시간 밖이면 잠금도 보지 않는다")))
    assert FT.run() == 3 and "--anytime" in capsys.readouterr().out


def test_status_reads_last_record(tmp_path, monkeypatch):
    for k in ("DIR", "LAST", "HISTORY", "LOCK"):
        monkeypatch.setattr(FT, k, tmp_path / getattr(FT, k).name if k != "DIR" else tmp_path)
    FT._write(FT.LAST, {"end": "2026-11-17T00:40:00", "ok": True})
    assert FT.status(NIGHT)["kind"] == "no"
    FT._write(FT.LAST, {"end": "2026-11-15T03:00:00", "ok": True})
    assert FT.status(NIGHT)["kind"] == "night" and FT.status(DAY)["kind"] == "no"


def test_hook_command_output_is_valid_json_or_empty():
    r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "tools" / "full_test.py"), "--due", "--hook"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0
    out = r.stdout.strip()
    if out:  # 돌릴 때면 훅 JSON 한 줄(맥락 글 + 사용자에게 보일 한 줄)
        d = json.loads(out)
        assert d["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit" and "full_test.py" in d["hookSpecificOutput"]["additionalContext"] and d["systemMessage"]
