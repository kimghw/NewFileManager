"""tools/llm_stats.py — 실행 기록에서 「스크립트 판정을 LLM 이 얼마나 고치나」 를 뽑는다(spec_작업 ② §22 「보정 통계」)."""
import gzip
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location("llm_stats", Path(__file__).resolve().parents[1] / "tools" / "llm_stats.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


def _run(root, wid, n, rec, tables=None, name="문서.hwpx"):
    d = root / wid / "headings" / str(n)
    d.mkdir(parents=True, exist_ok=True)
    (root / wid / "work.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    (d / "run.json").write_text(json.dumps({**rec, "n": n}), encoding="utf-8")
    if tables is not None:
        with gzip.open(d / "tables.json.gz", "wt", encoding="utf-8") as f:
            json.dump({"tables": tables}, f)


def _cell(draft, role, shaded=False):
    return {"draft": draft, "role": role, "shaded": shaded}


def test_collect_and_trend(tmp_path):
    _run(tmp_path, "a", 1, {"stage": 1, "llm": False, "at": 10, "summary": {"paragraphs": 100, "unmatched": 9}})
    _run(tmp_path, "a", 2, {"stage": 2, "llm": True, "at": 20, "costUsd": 1.5, "summary": {"nodes": 200, "changed": 20}})
    _run(tmp_path, "a", 3, {"stage": 3, "llm": True, "at": 30, "summary": {"cells": 4, "changed": 2, "tables": 2}},
         tables=[{"llm": {"sent": True}, "cells": [_cell("rowhead", "field"), _cell("rowhead", "field"), _cell("field", "field")]},
                 {"llm": {"sent": True}, "cells": [_cell("colhead", "colhead", True)]}])
    _run(tmp_path, "b", 1, {"stage": 1, "llm": False, "at": 40, "summary": {"paragraphs": 100, "unmatched": 0}})
    _run(tmp_path, "b", 2, {"stage": 2, "llm": True, "at": 50, "summary": {"nodes": 201, "changed": 5}})
    _run(tmp_path, "b", 3, {"stage": 2, "llm": True, "at": 60, "derivedFrom": 2, "summary": {"nodes": 201, "changed": 5}})  # 이름만 다시 붙인 실행 — 안 센다
    _run(tmp_path, "c", 1, {"stage": 2, "llm": True, "at": 70, "summary": {"nodes": 50, "changed": 1}}, name="다른.hwpx")

    data = S.collect(tmp_path)
    doc = data["문서.hwpx"]
    assert [r["unmatched"] for r in doc["rules"]] == [9, 0]
    assert [(x["size"], x["changed"]) for x in doc["heads"]] == [(200, 20), (201, 5)]
    t = doc["tables"][0]
    assert (t["sent"], t["touched"]) == (2, 1) and t["kinds"][("rowhead", "field", False)] == 2
    assert list(S.collect(tmp_path, "다른")) == ["다른.hwpx"]

    text = S.report(data)
    assert "처음 10.0%" in text and "마지막 2.5%" in text and "줄었음" in text  # 크기가 같은(2% 안) 실행끼리 견준다
    assert "rowhead → field (음영 없음): 2 (100%)" in text


def test_trend_keeps_sizes_apart():
    rows = [{"at": 1, "size": 100, "changed": 10}, {"at": 2, "size": 300, "changed": 3}, {"at": 3, "size": 100, "changed": 10}]
    out = S.trends(rows, "칸")
    assert len(out) == 1 and "칸 100 짜리" in out[0] and "그대로" in out[0]
