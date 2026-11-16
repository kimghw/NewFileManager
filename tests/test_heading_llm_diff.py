"""LLM 이 바꾼 것(app/heading_llm_diff.py — spec_헤딩_추출 ② §7 「LLM 이 바꾼 것」): 저장된 결과 안의 스크립트 초안과 LLM 답의 차이를 모은다(읽기만)."""
import types

from app import heading_llm_diff as D


def _sess(**st):
    base = {"job": None, "stage1": None, "stage2": None, "stage3": None, "runs": [], "loaded": True}
    base.update(st)
    return types.SimpleNamespace(id="none", rev=5, heads=base)


S1 = {"meta": {"run": 4, "at": 40.0}, "review": {"unmatched": [{"key": "u:x"}], "conflicts": []},
      "paras": [{"id": "p1", "text": "100 : 보고서", "rule": "l1"}, {"id": "p2", "text": "100 : 기술문서", "rule": "l1"}, {"id": "p3", "text": "□ 개요", "rule": "□"}],
      "llm": {"seconds": 12.0, "items": [
          {"group": "u:N:", "decision": "rule", "reason": "값 글", "verdict": "saved", "id": "l1", "why": "고침 2",
           "rule": {"name": "숫자 : 설명", "kind": "plain", "pattern": r"\d+\s*:", "scope": "prefix"}, "test": {"fixed": 2, "taken": 0}},
          {"group": "u::", "decision": "rule", "reason": "넓음", "verdict": "rejected", "why": "너무 넓음",
           "rule": {"name": "콜론", "kind": "plain", "pattern": ":", "scope": "prefix"}, "test": {"fixed": 1, "taken": 10}}]}}
RUNS = [{"n": 1, "stage": 1, "llm": False, "at": 10.0}, {"n": 2, "stage": 2, "llm": False, "at": 11.0, "summary": {"heuristic": 7, "adjust": 0}},
        {"n": 3, "stage": 3, "llm": False, "at": 12.0, "summary": {"subtables": 2, "roles": {"field": 3, "rowhead": 1}}},
        {"n": 4, "stage": 1, "llm": True, "at": 40.0, "costUsd": 0.2, "rules": {"groups": 2, "asked": True, "saved": 1, "rejected": 1}},
        {"n": 5, "stage": 2, "llm": True, "at": 50.0}, {"n": 6, "stage": 3, "llm": True, "at": 60.0}]


def _graph():
    nodes = [{"id": "n1", "para": "p3", "letter": "□", "text": " 개요", "type": "T1", "role": "heading"},
             {"id": "n2", "para": "p9", "letter": "[기관]", "text": "", "type": "T2", "role": "label", "undecided": True},
             {"id": "n3", "para": "p10", "letter": "o", "text": " 내용", "type": "T3", "role": "heading"}]
    return {"meta": {"run": 5, "at": 50.0}, "nodes": nodes, "counts": {"heuristic": 0, "disagreed": 0},
            "types": [{"type": "T1", "shape": "□", "kind": "marker", "role": "heading", "reason": "주 사슬 L1"},
                      {"type": "T2", "shape": "[…]", "kind": "label", "role": "label", "basis": "기관", "reason": "구분 기준 값"},
                      {"type": "T3", "shape": "o", "kind": "marker", "role": "not_heading", "variantOf": "", "reason": "본문 글머리"},
                      {"type": "T4", "shape": "□", "kind": "marker", "role": "heading", "variantOf": "T1", "reason": "크기만 다름"}],
            "hints": {"bases": [], "labels": {}},
            "templates": [{"name": "body:□", "slots": [{"level": 1, "letter": "□"}]}],
            "changes": [{"id": "n3", "before": {"parent": "n1", "role": "heading", "slot": None}, "after": {"parent": "n1", "role": "not_heading", "slot": None}, "reason": "글머리"}],
            "rejected": [{"id": "n1", "why": "순환"}],
            "adjustments": [{"id": "n1", "para": "p3", "template": "body:□", "tplNo": 1, "level": 1, "from": "S2", "to": "S1", "decision": "adjust", "reason": "같은 구실",
                             "review": {"verdict": "agree", "same": True, "reason": "동의"}},
                            {"id": "n9", "para": "p11", "template": "body:□", "tplNo": 1, "level": 1, "from": "S2", "to": "S1", "decision": "adjust", "reason": "같은 구실",
                             "review": {"verdict": "agree", "same": True, "reason": "동의"}},
                            {"id": "n8", "para": "p12", "template": "body:□", "tplNo": 1, "level": 1, "from": "S3", "to": "S1", "decision": "keep", "reason": "다른 구실"}],
            "llm": {"requested": True, "fallback": False, "calls": 3, "costUsd": 1.1, "seconds": 50, "summary": "주 사슬 하나",
                    "mainChainProposal": ["□", "o"], "mainChain": ["□"], "mainChainFixed": True, "formatPairs": 2, "reviewPairs": 2}}


def _tables():
    cells = [{"id": "c1", "row": 0, "col": 0, "text": "팀장", "draft": "field", "role": "colhead", "changed": True, "reason": "직위"},
             {"id": "c2", "row": 1, "col": 0, "text": "", "draft": "field", "role": "field", "changed": False}]
    return {"meta": {"run": 6, "at": 60.0}, "counts": {"subtables": 3, "roles": {"field": 2, "colhead": 1}},
            "tables": [{"id": "t1", "before": "결재란", "rows": 2, "cols": 1, "cells": cells, "subtables": [{}, {}],
                        "llm": {"sent": True, "changed": 1, "rejected": [], "undecided": False, "summary": "결재란", "draftSubs": 1}},
                       {"id": "t2", "before": "", "rows": 1, "cols": 1, "cells": [], "subtables": [{}], "llm": {"sent": False, "changed": 0, "rejected": []}}],
            "llm": {"requested": True, "fallback": False, "calls": 1, "sent": 1, "skipped": 1, "applied": 1, "rejected": 0, "undecided": 0, "summary": "표 하나"}}


def test_rules_part_items_paras_and_base():
    r = D.report(_sess(stage1=S1, runs=RUNS))
    p = r["rules"]
    assert p["run"] == 4 and p["current"] is True and p["counts"]["saved"] == 1 and p["counts"]["rejected"] == 1
    saved = next(x for x in p["items"] if x["verdict"] == "saved")
    assert saved["parasTotal"] == 2 and [x["id"] for x in saved["paras"]] == ["p1", "p2"] and saved["paras"][0]["text"] == "100 : 보고서"
    rej = next(x for x in p["items"] if x["verdict"] == "rejected")
    assert rej["paras"] == [] and rej["why"] == "너무 넓음"
    assert p["left"] == 1 and p["base"]["run"] == 1


def test_rules_none_without_llm_run():
    assert D.report(_sess(stage1=S1, runs=RUNS[:3]))["rules"] is None


def test_heads_part_types_nodes_adjust_chain():
    h = D.report(_sess(stage1=S1, stage2=_graph(), runs=RUNS))["heads"]
    assert h["llm"] is True and h["base"]["run"] == 2 and h["base"]["summary"]["heuristic"] == 7
    by = {t["type"]: t for t in h["types"]}
    assert by["T3"]["changed"] is True and by["T3"]["script"] == "heading"  # 스크립트 대체 판정은 heading — LLM 은 헤딩 아님
    assert by["T1"]["changed"] is False and by["T1"]["script"] == "heading"
    assert by["T2"]["script"] and by["T2"]["changed"] == (by["T2"]["script"] != "label")  # 괄호 꼴의 스크립트 역할은 bracket_role(구분 기준 목록·지정에 따라)
    assert by["T4"]["variantOf"] == "T1" and h["variants"] == 1 and h["typesChanged"] == sum(1 for t in h["types"] if t["changed"])
    assert h["types"][0]["changed"] and not h["types"][-1]["changed"]  # 역할이 바뀐 유형이 먼저
    n = h["nodes"][0]
    assert n["id"] == "n3" and n["before"]["role"] == "heading" and n["after"]["role"] == "not_heading" and n["after"]["parentText"] == "□ 개요"
    assert h["rejectedTotal"] == 1 and h["rejected"][0]["why"] == "순환"
    assert h["undecided"] == 1 and h["undecidedNodes"][0]["para"] == "p9"
    a = h["adjust"]
    assert (a["adjust"], a["keep"], a["undecided"]) == (2, 1, 0)
    g0 = a["groups"][0]
    assert g0["decision"] == "adjust" and g0["n"] == 2 and g0["paras"] == ["p3", "p11"] and g0["letter"] == "□" and g0["verdict"] == "agree"
    assert h["mainChain"]["proposal"] == ["□", "o"] and h["mainChain"]["fixed"] == ["□"]


def test_heads_script_result_is_not_llm():
    g = _graph()
    g["llm"] = {"requested": False, "fallback": False}
    h = D.report(_sess(stage2=g, runs=RUNS))["heads"]
    assert h["llm"] is False and "types" not in h


def test_tables_part_cells_and_draft_subs():
    t = D.report(_sess(stage3=_tables(), runs=RUNS))["tables"]
    assert t["llm"] is True and t["applied"] == 1 and t["base"]["summary"]["subtables"] == 2
    t1 = t["tables"][0]
    assert t1["id"] == "t1" and t1["changedTotal"] == 1 and t1["changed"][0]["draft"] == "field" and t1["changed"][0]["role"] == "colhead"
    assert t1["draftSubs"] == 1 and t1["subs"] == 2
    assert t["tables"][1]["sent"] is False and t["tables"][1]["draftSubs"] is None


def test_formats_part_lines():
    plans = {"1": {"no": "1", "state": "planned", "at": 70.0, "rev": 5, "model": "claude-opus-5-5", "costUsd": 0.1, "applied": None,
                   "plan": {"summary": "맞춤", "levels": [
                       {"level": 1, "letter": "□", "lines": 10, "rep": {"count": 4}, "match": [{"count": 3}], "keep": [{"count": 2}], "split": [], "change": 3, "moved": 0},
                       {"level": 2, "letter": "o", "lines": 8, "rep": {"count": 5}, "match": [], "keep": [],
                        "split": [{"sfx": "a", "rep": {"count": 2}, "match": [{"count": 1}]}], "change": 1, "moved": 3}]}}}
    f = D.report(_sess(), plans)["formats"]
    assert len(f) == 1 and f[0]["state"] == "planned" and f[0]["change"] == 4 and f[0]["moved"] == 3 and f[0]["keep"] == 2
    lv1, lv2 = f[0]["levels"]
    assert (lv1["match"], lv1["keep"]) == (3, 2) and lv2["split"] == [{"sfx": "a", "lines": 3}]


def test_empty_report():
    r = D.report(_sess())
    assert r == {"rev": 5, "rules": None, "heads": None, "tables": None, "formats": []}


# ---- 끝점(GET …/headings/llm-changes)
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import server  # noqa: E402

SAMPLES = Path(__file__).parents[1] / "samples"


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def test_api_hwpx_without_llm_and_docx_400(client):
    d = _upload(client, SAMPLES / "기술수요조사서.hwpx")
    v = client.get(f"/api/docs/{d}/headings/llm-changes")
    assert v.status_code == 200, v.text
    assert v.json()["rules"] is None and v.json()["heads"] is None and v.json()["formats"] == []
    x = _upload(client, SAMPLES / "기술수요조사서.docx")
    assert client.get(f"/api/docs/{x}/headings/llm-changes").status_code == 400
