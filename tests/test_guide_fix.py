"""지침 보정(spec_워크플로우 ② §18-23 「지침 보정」 · app/guide_fix.py · API …/guide-fix) — 저장한 작성 지침의 헤딩 · 표마다 지금 글을 LLM 에 보내고,
있는 글만 고친 답(지은 수 · 너무 늘어난 글 · 자리 밖의 문단은 버림)을 한 번에 반영한다. LLM 은 가짜로 바꿔 끼운다."""
import json

import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import guide_fix as GF
from app import llm, server
from app import workflow_units as U
from app.division_profiles import _structure as structure

needs_report = pytest.mark.skipif(not M.REPORT_FORM.exists(), reason="KEIT 연차보고서 서식 hwpx 없음")


def test_check_keeps_trims_and_drops_made_up_numbers():
    ctx = {"u1": {"ids": {"p1": "2026년 매출 1,200억원 달성 및 그 뒤의 긴 설명 문장", "p2": "수요기업"}, "nums": {"2026", "1200"}, "where": "개요", "kind": "heading"}}
    fixes, left, rejected = GF.check(ctx, {"fixes": [
        {"unit": "u1", "id": "p1", "new": "2026년 매출 1,200억원 달성", "rule": "2page 이내", "why": "뒷부분 덜기"},   # 덜기 — 받음
        {"unit": "u1", "id": "p2", "new": "수요 3곳", "rule": "", "why": ""},                                             # 지은 수 3 — 버림
        {"unit": "u1", "id": "p2", "new": "수요기업" + "가" * 40, "rule": "", "why": ""},                                  # 너무 늘어남 — 버림
        {"unit": "u1", "id": "p9", "new": "x", "rule": "", "why": ""},                                                    # 그 자리에 없는 문단
        {"unit": "u2", "id": "p1", "new": "x", "rule": "", "why": ""},                                                    # 모르는 자리
        {"unit": "u1", "id": "p1", "new": "다시", "rule": "", "why": ""},                                                  # 이미 고친 문단
        {"unit": "u1", "id": "p2", "new": "수요기업", "rule": "", "why": ""},                                              # 같은 글 — 고침이 아니다(버림도 아님)
    ], "left": [{"unit": "u1", "id": "p2", "why": "정보 없음"}, {"unit": "zz", "id": "", "why": "모름"}]})
    assert [(f["id"], f["new"]) for f in fixes] == [("p1", "2026년 매출 1,200억원 달성")] and fixes[0]["old"].startswith("2026년") and fixes[0]["where"] == "개요"
    assert [r["why"].split(" ")[0] for r in rejected] == ["지은", "글이", "그", "모르는", "이미"]
    assert left == [{"unit": "u1", "id": "p2", "where": "개요", "why": "정보 없음"}]


def test_units_follow_heading_depth_and_skip_guide_blocks():
    para = lambda i, t: {"id": i, "type": "paragraph", "text": t}  # noqa: E731
    blocks = [para("h1", "1. 개요"), para("p1", "내용 하나"), para("n1", "※ 2page 이내 요약 작성"), para("h2", "1-1. 세부"), para("p2", "내용 둘"),
              {"id": "t1", "type": "table", "cells": [{"id": "c1", "row": 0, "col": 0, "text": "구분", "blocks": [para("cp1", "구분")]}]},
              para("h3", "2. 다음"), para("p3", "다른 절")]
    graph = {"nodes": [{"role": "heading", "area": "body", "para": p, "depth": d} for p, d in (("h1", 1), ("h2", 2), ("h3", 1))]}
    saved = {"items": [{"id": "n1", "kind": "notes", "name": "※ 안내", "text": "※ 2page 이내 요약 작성", "heading": {"id": "h1", "text": "1. 개요"}, "table": None, "top": 2},
                       {"id": "x", "kind": "notes", "name": "※ 안내", "text": "※ 표 지침", "heading": {"id": "h2", "text": "1-1. 세부"}, "table": {"id": "t1", "label": "구분"}, "top": 5}], "marks": []}
    us, ctx = GF.units(blocks, graph, saved, {"notes": [{"id": "n1", "whole": True}], "tables": [], "refs": []})
    assert [u["kind"] for u in us] == ["heading", "heading"]   # 헤딩 자리 안에 든 표는 그 헤딩의 자리로 — 표 자리를 따로 묻지 않는다
    assert set(ctx["u1"]["ids"]) == {"p1", "p2", "cp1"} and {"h": "1-1. 세부"} in us[0]["content"]   # 깊은 헤딩까지 · 안내 줄 · 헤딩 줄은 고칠 대상이 아니다 · 다음 같은 깊이의 헤딩 전까지
    assert set(ctx["u2"]["ids"]) == {"p2", "cp1"} and us[0]["guides"] == [{"kind": "※ 안내", "text": "※ 2page 이내 요약 작성"}]
    assert GF.units(blocks, graph, {"items": [], "marks": []}, {})[0] == []   # 지침이 없으면 자리도 없다


def test_unit_state_needs_fill_guides_and_counts_the_last_apply():
    fill = {"fills": True, "filled": {"at": 5.0, "nothing": False}, "links": {}, "plan": None, "heads": {}, "stages": {}}
    ctx = lambda G, F=fill, llm=True: {"ready": True, "llm": llm, "docs": [{"role": "target"}], "pair": {"target": {"title": "연차보고서", "id": "T", "facts": {"fill": F, "guideFix": G}}}}  # noqa: E731
    G = {"guides": {"headings": 3, "tables": 1, "total": 4}, "saved": True, "applied": None, "fill": 5.0}
    got = U.state("guideFix", ctx(G))
    assert got["st"] == "todo" and got["paid"] == ["T"] and "4곳" in got["text"]
    assert U.state("guideFix", ctx(G, {**fill, "filled": None}))["st"] == "todo"   # 「내용 넣기」 가 끝나기 전
    done = U.state("guideFix", ctx({**G, "applied": {"fill": 5.0, "done": 2, "skipped": 0, "left": 1}}))
    assert done["st"] == "done" and "고친 문단 2" in done["text"] and "고치지 못한 것 1" in done["text"]
    assert U.state("guideFix", ctx({**G, "applied": {"fill": 1.0, "done": 2}}))["st"] == "todo"   # 그 뒤에 다시 넣었다 — 다시 고친다
    assert U.state("guideFix", ctx(G, llm=False))["skipped"]
    assert U.state("guideFix", ctx({**G, "guides": {"total": 0}, "saved": False}))["skipped"]


@needs_report
def test_api_asks_checks_and_applies_once(monkeypatch):
    def fake(jobs, **kw):
        out = []
        for j in jobs:
            data = json.loads(j["content"].split("## 자료(JSON)\n", 1)[1])
            fixes = []
            for u in data["units"]:
                for line in [x for x in u["content"] if x.get("id")] + [c for x in u["content"] for c in x.get("cells") or ()]:   # 본문 줄 · 표 칸의 문단
                    if len(line["text"].strip()) > 8 and not any(ch.isdigit() for ch in line["text"]) and not fixes:
                        fixes.append({"unit": u["key"], "id": line["id"], "new": line["text"].strip()[:4], "rule": "분량", "why": "덜기"})
                        fixes.append({"unit": u["key"], "id": line["id"], "new": "2099년 지은 수", "rule": "", "why": ""})   # 같은 문단을 또 — 버림
            out.append({"data": {"fixes": fixes, "left": []}, "backend": "fake", "ms": 1})
        return out
    monkeypatch.setattr(llm, "ask_all", fake)
    c = TestClient(server.app)
    d = c.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    assert c.post(f"/api/docs/{d}/form-guides").status_code == 200
    r = c.post(f"/api/docs/{d}/guide-fix/ask").json()
    assert r["asked"] >= 1 and r["fixes"] and r["rejected"]
    assert c.post(f"/api/docs/{d}/guide-fix/apply", json={"planId": "nope"}).status_code == 409
    a = c.post(f"/api/docs/{d}/guide-fix/apply", json={"planId": r["planId"]}).json()
    texts = {b["id"]: b.get("text") for b in structure.iter_blocks(server._sess(d).doc.blocks())}
    assert a["done"] and all(texts[f["id"]] == f["new"] for f in a["done"]) and not a["skipped"]
    g = c.get(f"/api/docs/{d}/guide-fix").json()
    assert g["applied"]["planId"] == r["planId"] and len(g["applied"]["done"]) == len(a["done"]) and g["parts"][0]["key"] == "contract"
    again = c.post(f"/api/docs/{d}/guide-fix/apply", json={"planId": r["planId"]}).json()   # 같은 계획을 또 — 글이 이미 바뀌어 모두 건너뜀(두 번 고치지 않는다)
    assert again.get("nothing") and len(again["skipped"]) == len(a["done"])
