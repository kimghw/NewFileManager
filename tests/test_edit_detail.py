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
    assert set(got) == {"style", "align", "indentLeftMm", "sizePt"}
    assert (got["sizePt"]["label"], got["sizePt"]["before"], got["sizePt"]["after"]) == ("크기", "11pt", "13pt")
    assert (got["indentLeftMm"]["before"], got["indentLeftMm"]["after"]) == ("0mm", "10.4mm")
    assert (got["align"]["before"], got["align"]["after"]) == ("양쪽", "가운데")
    assert "part" not in got["sizePt"]


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
