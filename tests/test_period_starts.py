"""사업기간 날짜 칸의 글 시작 맞추기(spec_구분_기준 ② §27 「날짜 칸의 글 시작」 —2026-11-23 사용자 「여기 년도는 앞 여백이 동일해야 하는데 왜 자꾸 가운데 정렬로 되는 거야?」):
같은 표 · 같은 열에 선 날짜 범위 칸(연구개발기간 「전체 · 1~N년차 · 해당연도」)은 왼쪽 정렬 + 같은 앞 여백 — 앞 여백 = 가장 왼쪽에서 시작하던 날짜의 시작 자리."""
from pathlib import Path

import pytest

from app.division_profiles import _structure as structure
from app.division_profiles import rnd
from app.division_profiles.rnd import core
from app.hwpx_doc import HwpxDoc

REPORT = Path(__file__).parents[1] / "samples" / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"
PLAN = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
VALUES = {"stages": [4], "orgs": {"lead": "한국선급", "joint": []}, "period": {"start": "2026-04-01", "end": "2029-12-31"}, "current": 1}


def _period_paras(doc):
    """연구개발기간 표(「…년차」 칸이 있는 표)의 날짜 문단 [(블록, 칸)]."""
    out = []
    for t in structure.iter_blocks(doc.blocks()):
        if t.get("type") != "table" or not any("년차" in (c.get("text") or "") for c in t["cells"]):
            continue
        for c in t["cells"]:
            for p in c.get("blocks") or ():
                if p.get("type") == "paragraph" and core.SPAN_RE.search(p.get("text") or "") and "YYYY" not in p["text"]:
                    out.append((p, c))
    return out


def _cell(pid, col=13, span=19, width=90.0):
    return {"id": f"c{pid}", "row": 0, "col": col, "colSpan": span, "widthMm": width, "marginsMm": {"l": 0.5, "r": 0.5}, "blocks": []}


def _blocks(rows):
    """rows = [(문단 id, 글, align, 앞 여백, 열)] → 표 하나의 블록."""
    cells = []
    for pid, text, align, left, col in rows:
        c = _cell(pid, col=col)
        c["blocks"] = [{"id": pid, "type": "paragraph", "text": text, "format": {"align": align, "indentLeftMm": left, "firstLineMm": 0.0, "indentRightMm": 0.0, "sizePt": 10}}]
        cells.append(c)
    return [{"id": "t1", "type": "table", "cells": cells}]


def _fill(blocks):
    return [{"id": p["id"], "old": p["text"], "new": p["text"], "kind": "year", "where": {"table": "t1", "cell": c["id"]}}
            for c in blocks[0]["cells"] for p in c["blocks"]]


SPAN_A, SPAN_B = "2026. 04. 01 - 2029. 12. 31(3년 9개월)", "2027. 01. 01 - 2027. 12. 31(1년)"


def test_starts_groups():
    centered = _blocks([("p1", SPAN_A, "center", 0.0, 13), ("p2", SPAN_B, "center", 0.0, 13)])
    assert [g["ids"] for g in core.period_starts(centered, _fill(centered))] == [["p1", "p2"]]
    same = _blocks([("p1", SPAN_A, "left", 10.6, 13), ("p2", SPAN_B, "left", 10.6, 13)])
    assert core.period_starts(same, _fill(same)) == []   # 이미 같은 시작 — 할 일 없음(계획서 양식의 그 칸)
    apart = _blocks([("p1", SPAN_A, "left", 10.6, 13), ("p2", SPAN_B, "left", 4.0, 13)])
    assert [g["ids"] for g in core.period_starts(apart, _fill(apart))] == [["p1", "p2"]]
    alone = _blocks([("p1", SPAN_A, "center", 0.0, 13), ("p2", SPAN_B, "center", 0.0, 4)])
    assert core.period_starts(alone, _fill(alone)) == []   # 열이 다르면 묶지 않는다 — 한 칸뿐인 열은 맞출 것이 없다
    label = _blocks([("p1", SPAN_A, "center", 0.0, 13), ("p2", "1단계 1차년도", "center", 0.0, 13)])
    assert core.period_starts(label, _fill(label)) == []   # 날짜 범위가 아닌 문단(당해 라벨)은 묶음에 넣지 않는다


@pytest.mark.skipif(not REPORT.exists(), reason="KEIT 연차보고서 서식 hwpx 없음")
def test_report_dates_share_start():
    """보고서 양식은 그 칸이 가운데 정렬 — 반영하면 모두 왼쪽 정렬 · 같은 앞 여백(가장 긴 「전체」 날짜가 양식이 놓은 자리), 다시 반영하면 할 일 없음."""
    doc = HwpxDoc(REPORT.read_bytes())
    before = {p["id"]: p["format"]["align"] for p, _ in _period_paras(doc)}
    rep = core.apply(doc, core.norm_values(VALUES), levels_of=rnd.levels_of)
    got = _period_paras(doc)
    assert len(got) >= 6 and set(before.values()) <= {"center"}
    assert {p["format"]["align"] for p, _ in got} == {"left"} and len({p["format"]["indentLeftMm"] for p, _ in got}) == 1
    left = got[0][0]["format"]["indentLeftMm"]
    assert 5 < left < 20   # 90mm 칸에 약 70mm 의 「전체」 날짜 — 가운데였던 자리
    moved = [c for c in rep["changes"] if c.get("format")]
    assert moved and all(c["key"] == core.PERIOD and "왼쪽 정렬" in c["format"] for c in moved)
    blocks = doc.blocks()
    fill = core.period_fill(blocks, core.norm_values(VALUES), True)
    assert core._period_spot(fill, core.period_starts(blocks, fill))["done"]
    again = core.apply(doc, core.norm_values(VALUES), levels_of=rnd.levels_of, only=core.PERIOD)
    assert not [c for c in again["changes"] if c.get("format")]


@pytest.mark.skipif(not REPORT.exists(), reason="KEIT 연차보고서 서식 hwpx 없음")
def test_report_only_period_fixes_centered_dates():
    """날짜 글은 이미 맞고 정렬만 가운데인 문서(이 변경 전에 반영한 문서) — 자리 「사업기간」 이 「이미 맞음」 이 아니고, 그 자리만 반영해도 글 시작이 맞는다."""
    doc = HwpxDoc(REPORT.read_bytes())
    vals = core.norm_values(VALUES)
    core.apply(doc, vals, levels_of=rnd.levels_of)
    ids = [p["id"] for p, _ in _period_paras(doc)]
    doc.format_para(ids, {"align": "center", "indentLeftMm": 0})   # 옛 반영의 결과처럼
    blocks = doc.blocks()
    fill = core.period_fill(blocks, vals, True)
    spot = core._period_spot(fill, core.period_starts(blocks, fill))
    assert not spot["done"] and set(ids) <= set(spot["ids"])
    rep = core.apply(doc, vals, levels_of=rnd.levels_of, only=core.PERIOD)
    assert {c["id"] for c in rep["changes"]} == set(ids) and all(c["old"] == c["new"] for c in rep["changes"])
    assert {p["format"]["align"] for p, _ in _period_paras(doc)} == {"left"}


@pytest.mark.skipif(not PLAN.exists(), reason="연구개발계획서 양식 hwpx 없음")
def test_plan_form_dates_share_start():
    """계획서 빈 양식도 그 칸이 가운데 정렬(사람이 쓴 계획서는 왼쪽 정렬 · 앞 여백 10.6mm 로 고쳐 둔 것이 있다) — 같은 규칙으로 맞춘다.
    이미 왼쪽 정렬 · 같은 앞 여백인 칸은 test_starts_groups 의 same."""
    doc = HwpxDoc(PLAN.read_bytes())
    core.apply(doc, core.norm_values(VALUES), levels_of=rnd.levels_of)
    got = _period_paras(doc)
    assert len(got) >= 6 and {p["format"]["align"] for p, _ in got} == {"left"} and len({p["format"]["indentLeftMm"] for p, _ in got}) == 1
