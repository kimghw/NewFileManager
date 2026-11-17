"""고친 문단이 어떻게 바뀌었나(spec_작업 ② §8 「화면」 — 깃 diff 처럼) — app/edit_detail.py 순수 함수 + GET /api/docs/{id}/edits/detail."""
import pytest
from fastapi.testclient import TestClient

from app import edit_detail as ED
from app import server
from tests.test_server import SMALL, _paras


def _p(**kw):
    fmt = {"font": "바탕", "sizePt": 11.0, "bold": False, "color": "#000000", "align": "justify", "indentLeftMm": 0.0, "lineSpacingPct": 160}
    fmt.update(kw.pop("format", {}))
    return {"id": "p1", "type": "paragraph", "text": "가나다", "style": "바탕글", "outlineLevel": None, "list": None, "format": fmt, "runs": None, **kw}


def test_changes_names_each_side_in_screen_form():
    a, b = _p(), _p(format={"sizePt": 13.0, "indentLeftMm": 10.44, "align": "center"}, style="개요 1")
    got = {c["key"]: c for c in ED.changes(a, b)}
    assert set(got) == {"style", "align", "line1Mm", "line2Mm", "sizePt"}  # 왼쪽 여백이 늘면 첫 줄도 둘째 줄부터도 옮겨진다
    assert (got["sizePt"]["label"], got["sizePt"]["before"], got["sizePt"]["after"]) == ("크기", "11pt", "13pt")
    assert (got["line1Mm"]["label"], got["line1Mm"]["before"], got["line1Mm"]["after"]) == ("앞 여백", "0mm", "10.4mm")
    assert (got["line2Mm"]["label"], got["line2Mm"]["before"], got["line2Mm"]["after"]) == ("2번째 줄", "0mm", "10.4mm")
    assert (got["align"]["before"], got["align"]["after"]) == ("양쪽", "가운데")
    assert "part" not in got["sizePt"] and "hint" not in got["sizePt"] and "문단 모양" in got["line2Mm"]["hint"]


def test_line_places_not_raw_indent_values():
    """줄의 자리(앞 여백 · 2번째 줄)로 견준다 — 2026-11-17 사용자 「이게 원본이 원래 0은 아닌데」: 한글의 내어쓰기는 첫 줄을 그대로 두고 둘째 줄부터를 들인다(「첫 줄 0mm → -7.8mm」 가 아니라 「2번째 줄 0mm → 7.8mm」)."""
    hang = ED.changes(_p(format={"firstLineMm": 0.0}), _p(format={"firstLineMm": -7.78}))
    assert [(c["key"], c["before"], c["after"]) for c in hang] == [("line2Mm", "0mm", "7.8mm")]  # 첫 줄은 안 움직였다 — 적지 않는다
    dent = ED.changes(_p(format={"firstLineMm": 0.0}), _p(format={"firstLineMm": 5.0}))
    assert [(c["key"], c["before"], c["after"]) for c in dent] == [("line1Mm", "0mm", "5mm")]  # 들여쓰기 — 첫 줄만
    assert ED.lines({"indentLeftMm": 10.0, "firstLineMm": -4.0}) == {"line1Mm": 10.0, "line2Mm": 14.0}
    # Word: 왼쪽 값이 둘째 줄부터의 자리 · 내어쓰기는 첫 줄을 왼쪽으로(left 14 · hanging 4 = 첫 줄 10 · 둘째 줄부터 14)
    assert ED.lines({"indentLeftMm": 14.0, "firstLineMm": -4.0}, word=True) == {"line1Mm": 10.0, "line2Mm": 14.0}
    word = ED.changes(_p(format={"indentLeftMm": 14.0, "firstLineMm": 0.0}), _p(format={"indentLeftMm": 14.0, "firstLineMm": -4.0}), word=True)
    assert [(c["key"], c["before"], c["after"]) for c in word] == [("line1Mm", "14mm", "10mm")]
    assert ED.lines({}) == {"line1Mm": None, "line2Mm": None}  # 서식 값이 없는 블록 — 「없음」 끼리라 다름이 아니다
    assert ED.changes(_p(format={"indentLeftMm": None}), _p(format={"indentLeftMm": None})) == []


def test_same_shown_value_is_not_a_change_and_missing_block_is_none():
    assert ED.changes(_p(format={"indentLeftMm": 10.41}), _p(format={"indentLeftMm": 10.44})) == []
    assert ED.changes(None, _p()) is None and ED.changes(_p(), None) is None


def test_runs_report_part_of_the_paragraph():
    runs = [{"text": "가", "format": {"sizePt": 11.0, "bold": True}}, {"text": "나다", "format": {"sizePt": 11.0, "bold": False}}]
    got = {c["key"]: c for c in ED.changes(_p(), _p(runs=runs))}
    assert got["bold"]["before"] == "끔" and got["bold"]["after"] == "켬 · 끔" and got["bold"]["part"]
    assert "sizePt" not in got  # 모든 런이 11pt — 기준과 같다
    blank = [{"text": "가나다", "format": {"sizePt": 11.0}}, {"text": " ", "format": {"sizePt": 20.0}}]
    assert "sizePt" not in {c["key"] for c in ED.changes(_p(), _p(runs=blank))}  # 공백만 든 런은 견주지 않는다


def test_list_compares_kind_and_level_not_running_number():
    a = _p(list={"kind": "number", "level": 1, "label": "1."})
    assert ED.changes(a, _p(list={"kind": "number", "level": 1, "label": "2."})) == []
    got = ED.changes(a, _p(list={"kind": "bullet", "level": 2, "label": "●"}))
    assert got == [{"key": "list", "label": "목록", "before": "번호 수준 1", "after": "글머리표 ● 수준 2"}]


def test_index_reaches_cell_paragraphs():
    cell = {"type": "table", "id": "t1", "cells": [{"blocks": [_p(id="p9")]}]}
    assert set(ED.index([_p(), cell])) == {"p1", "p9"}


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def test_endpoint_reports_format_edit_and_skips_text_only(client):
    d = client.post(f"/api/samples/{SMALL.name}").json()["docId"]
    paras = [p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if len((p["text"] or "").strip()) > 4]
    a, b = paras[1], paras[2]
    before = a["format"]
    r = client.post(f"/api/docs/{d}/format/para", json={"ids": [a["id"]], "changes": {"align": "center" if before.get("align") != "center" else "left"}})
    assert r.status_code == 200, r.text
    assert client.patch(f"/api/docs/{d}/blocks/{b['id']}", json={"text": b["text"] + "★"}).json()["edited"]
    got = client.get(f"/api/docs/{d}/edits/detail").json()
    assert set(got["items"]) == {a["id"]} and got["more"] == 0  # 글만 고친 문단(b)은 화면이 원래 글로 그린다
    ch = {c["key"]: c for c in got["items"][a["id"]]}
    assert ch["align"]["before"] == ED.shown("align", before.get("align")) and ch["align"]["after"] in ("가운데", "왼쪽")
    assert client.get(f"/api/docs/{d}/edits/detail").json() == got  # 같은 차례 — 한 번 센 것
    rev = client.get(f"/api/docs/{d}").json()["rev"]
    assert got["rev"] == rev
    # ids — 그 문단들만(문서의 「고친 곳 보기」 가 보이는 문단만 묻는다): 모양이 바뀐 문단이 아닌 id · 없는 id 는 답에 없다
    one = client.get(f"/api/docs/{d}/edits/detail", params={"ids": f"{b['id']}, {a['id']},nope,{a['id']}"}).json()
    assert one["items"] == got["items"] and one["more"] == 0 and one["rev"] == rev
    assert client.get(f"/api/docs/{d}/edits/detail", params={"ids": b["id"]}).json()["items"] == {}
    assert client.get(f"/api/docs/{d}/edits/detail").json() == got  # ids 로 물은 뒤에도 목록 쪽 답은 그대로
    # 편집 차례가 오르면 다시 센다(색인을 옛 차례 것으로 쓰지 않는다)
    r = client.post(f"/api/docs/{d}/format/para", json={"ids": [b["id"]], "changes": {"indentLeftMm": 7}})
    assert r.status_code == 200, r.text
    two = client.get(f"/api/docs/{d}/edits/detail", params={"ids": b["id"]}).json()
    assert set(two["items"]) == {b["id"]} and any(c["key"] in ED.LINE_KEYS and c["after"] == "7mm" for c in two["items"][b["id"]])  # 왼쪽 여백 7 → 앞 여백·2번째 줄 가운데 들이지 않은 쪽이 7mm
