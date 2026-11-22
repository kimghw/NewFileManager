"""자리 연결 LLM 보정 — 장별 병렬 검토(spec_병합 ② §4 「LLM 보정」) — app/merge_chunks.py · app/merge_llm.review. LLM 은 부르지 않는다(가짜 ask)."""
import json

import pytest

import merge_data as M
from app import merge_chunks as C
from app import merge_llm as L
from app import merge_pairs as P


def _doc(n_pages, heads):
    """쪽마다 문단 하나인 문서(블록 i = i+1 쪽) + 본문 헤딩 그래프. heads = [(블록 차례, 노드 id, 부모 id, 레터, 레벨)] — 주 사슬 레벨 1 = 장."""
    blocks = [{"id": f"p{i}", "type": "paragraph", "text": f"줄 {i}", "lines": [], **({"page": None} if i == 0 else {"pageStart": True})} for i in range(n_pages)]
    nodes = [{"id": nid, "para": f"p{i}", "n": i, "flow": "body", "area": "body", "role": "heading", "letter": letter, "text": f"제목 {nid}",
              "template": "body:main" if lv == 1 else "body:sub", "level": lv, "parent": parent} for i, nid, parent, letter, lv in heads]
    return blocks, {"nodes": nodes, "templates": [{"key": "body:main", "kind": "main"}, {"key": "body:sub", "kind": "branch"}]}


def test_units_split_long_chapter_by_sections_within_page_limit():
    heads = [(2, "A", "root", "1.", 1),                                   # 1장 3~5쪽
             (5, "B", "root", "2.", 1), (6, "B1", "B", "2-1.", 1), (14, "B2", "B", "2-2.", 1), (22, "B3", "B", "2-3.", 1),   # 2장 6~31쪽 — 절 9·8·9쪽
             (30, "X", "B3", "1.", 1),                                    # 장 안의 「1.」 목록(번호가 앞 장보다 작음)은 장이 아니다
             (31, "D", "root", "3.", 1), (32, "D1", "D", "3-1.", 1)]       # 3장 32~60쪽 — 더 자를 수 없는 절 하나(29쪽)
    blocks, graph = _doc(60, heads)
    us = C.units(blocks, graph, pages=20)
    assert [(u["start"], u["end"]) for u in us] == [(0, 2), (2, 5), (5, 22), (22, 31), (31, 60)]   # 빈틈·겹침 없이 문서 전체
    assert us[0]["title"] == C.FRONT and us[2]["title"].endswith("2-1. 제목 B1 ~ 2-2. 제목 B2") and us[3]["title"].endswith("2-3. 제목 B3")
    assert [u["pages"] for u in us] == [[1, 2], [3, 5], [6, 22], [23, 31], [32, 60]]
    assert [u["over"] for u in us] == [False, False, False, False, True]   # 혼자 넘는 절은 넘는 채로 한 단위(over)
    assert C.assign(us, C.index(blocks), ["p0", "p7", "p21", "p22", "p59", "없음"]) == [0, 2, 2, 3, 4, 0]


def test_page_numbers_count_tall_tables_and_uncached_paragraphs():
    page = {"widthMm": 210, "heightMm": 297, "marginsMm": {"l": 20, "r": 20, "t": 20, "b": 20}}   # 본문 257mm
    tall = {"id": "t", "type": "table", "cells": [{"row": r, "col": 0, "heightMm": 100} for r in range(6)]}   # 600mm — 쪽 둘을 넘김
    blocks = [{"id": "p0", "type": "paragraph", "text": "", "lines": [], "page": page}, tall,
              {"id": "p1", "type": "paragraph", "text": ""}, *({"id": f"q{i}", "type": "paragraph", "text": "가" * 400} for i in range(4))]   # 캐시 없는 11줄 문단 넷
    assert C.page_numbers(blocks) == [1, 1, 3, 3, 3, 3, 4]   # 블록의 쪽 = 시작하는 쪽(넷째 문단이 3쪽에서 시작해 4쪽으로 넘침)


@pytest.fixture(scope="module")
def small():
    d = M.small()
    side = {k: {"blocks": d[k]["doc"].blocks(), "graph": d[k]["graph"]} for k in ("to", "from")}
    s = {k: P.summarize(side[k]["blocks"], d[k]["graph"], d[k]["tables"], d["values"]) for k in ("to", "from")}
    return side, s, P.pair(s["to"], s["from"])


def _payload(job):
    return json.loads(job["content"].split("## 자료(JSON)\n", 1)[1])


def test_review_units_targets_model_and_validation(small):
    side, s, pairs = small
    und = {g["to"]["key"] for g in pairs["groups"] if g["status"] in L.UNDECIDED}
    assert len(und) >= 3
    jobs = []

    def fits(t, x):   # check() 가 받는 원본(구분 갈래·종류 갈래·맥락 차년도)
        ys = ((t.get("ctx") or {}).get("year"), (x.get("ctx") or {}).get("year"))
        return L._dim(x["dim"]) == L._dim(t["dim"]) and L.family(x["kind"]) == L.family(t["kind"]) and (None in ys or ys[0] == ys[1])

    def ask(js):   # 단위마다: 모든 못 정한 묶음에 답한다(제 단위 것은 맞는 원본 — 없으면 "", 남의 것은 아무 원본) — 다른 단위의 key 는 거절돼야 한다. 첫 단위는 실패.
        jobs.extend(js)
        out = []
        for k, j in enumerate(js):
            p = _payload(j)
            pick = {t["key"]: next((x["key"] for x in p["sources"] if fits(t, x)), "") for t in p["targets"]}
            dec = [{"to": key, "from": pick.get(key, p["sources"][0]["key"]), "anchor": "", "reason": "시험"} for key in sorted(und)]
            out.append({"data": None, "error": "시험 실패", "model": j["model"]} if k == 0 else {"data": {"decisions": dec, "summary": ""}, "backend": "fake", "model": j["model"], "error": None})
        return out

    r = L.review(side["to"], side["from"], pairs, s["to"], s["from"], pages=3, ask=ask)
    sent = [[t["key"] for t in _payload(j)["targets"]] for j in jobs]
    assert len(jobs) >= 2 and sorted(k for ks in sent for k in ks) == sorted(und)      # 못 정한 목적 묶음마다 꼭 한 단위
    assert all(j["model"] == L.MODEL == "claude-opus-5-5" and j["effort"] == "medium" for j in jobs)
    assert all(u["pages"][1] - u["pages"][0] + 1 <= 3 for u in r["units"] if not u["over"])
    called = [u for u in r["units"] if u["call"]]
    assert [u["targets"] for u in called] == [len(ks) for ks in sent] and called[0]["call"]["error"] == "시험 실패"
    assert set(r["fixed"]) | {n["to"] for n in r["none"]} == {k for ks in sent[1:] for k in ks} and r["fixed"]   # 실패한 단위의 몫만 빠지고 나머지는 남는다
    assert all(x["why"].startswith("보정 대상이 아닌") for x in r["rejected"]) and len(r["rejected"]) == sum(len(und) - len(ks) for ks in sent[1:])
    p = _payload(jobs[1])
    assert p["chapter"]["title"] and all("excerpt" in t for t in p["targets"]) and all("excerpt" in x for x in p["sources"])
    assert {g["id"] for g in P.pair(s["to"], s["from"], fixed=r["fixed"])["groups"] if g["source"] == "llm"} == set(r["fixed"])


def test_check_refuses_a_body_pair_from_another_institution():
    """본문 묶음도 표처럼 — 둘 다 알고 다른 기관 · 차년도의 짝은 거절(spec_병합 ② §5-11 G4 · astra 2차: 전에는 차년도만 봐 같은 차년도 다른 기관의 같은 이름 절이 짝으로 들어왔다)."""
    t = {"key": "t", "dim": "org", "kind": "para", "ctx": {"org": "A기관", "year": 2}}
    p = {"targets": [t, {**t, "key": "u", "ctx": {"year": 2}}], "sources": [{"key": "s", "dim": "org", "kind": "para", "ctx": {"org": "B기관", "year": 2}},
                                                                          {"key": "z", "dim": "org", "kind": "para", "ctx": {"org": "A기관", "year": 3}}]}
    r = L.check(p, {"decisions": [{"to": "t", "from": "s", "reason": "같은 이름 절"}, {"to": "u", "from": "s", "reason": "목적 기관 모름"}]})
    assert [x["why"] for x in r["rejected"]] == ["맥락 기관이 다름"] and set(r["fixed"]) == {"u"}   # 한쪽만 아는 기관은 막지 않는다
    assert [x["why"] for x in L.check(p, {"decisions": [{"to": "t", "from": "z", "reason": "다른 차년도"}]})["rejected"]] == ["맥락 차년도가 다름"]


def test_review_sends_each_place_its_guides_and_the_contract_line(small):
    """자리마다의 작성 지침(② §5-11) — places 를 주면 묶음 · 표마다 guides 를 싣고 계약에 그 한 줄. 없으면 전과 같다."""
    from app import place_guides as PG
    side, s, pairs = small
    jobs = []

    def ask(js):
        jobs.extend(js)
        return [{"data": None, "error": "시험", "model": j["model"]} for j in js]
    places = lambda kind, x: [{"src": "doc", "kind": "※ 안내", "text": f"{kind} 지침 {x['key'] if kind == 'group' else x}"}]  # noqa: E731
    r = L.review(side["to"], side["from"], pairs, s["to"], s["from"], pages=3, ask=ask, places=places)
    assert jobs and all(PG.CONTRACT_LINE in j["content"] for j in jobs)
    for j in jobs:
        p = _payload(j)
        assert all(t["guides"] == [{"src": "doc", "kind": "※ 안내", "text": f"group 지침 {t['key']}"}] for t in p["targets"])
        assert all(t["guides"][0]["text"] == f"table 지침 {t['key']}" for t in p.get("tableTargets") or ())
    assert sum(u.get("guides", 0) for u in r["units"]) == sum(len(_payload(j)["targets"]) + len(_payload(j).get("tableTargets") or ()) for j in jobs)
    jobs.clear()
    L.review(side["to"], side["from"], pairs, s["to"], s["from"], pages=3, ask=ask)
    assert jobs and not any(PG.CONTRACT_LINE in j["content"] or "guides" in j["content"].split("## 자료(JSON)\n", 1)[1] for j in jobs)


def test_review_asks_again_about_an_llm_pair_whose_place_changed(small):
    """지침이 바뀐 자리의 LLM 짝(again)은 지우지 않고 다시 묻는다 — 「확인 필요」 로 보내고 그 짝의 원본이 후보 맨 앞(astra 3차)."""
    side, s, pairs = small
    paired = next(g for g in pairs["groups"] if g["status"] == "paired" and g.get("from"))
    pg = {**pairs, "groups": [{**g, "source": "llm"} if g is paired else g for g in pairs["groups"]]}
    jobs = []

    def ask(js):
        jobs.extend(js)
        return [{"data": None, "error": "시험", "model": j["model"]} for j in js]
    r = L.review(side["to"], side["from"], pg, s["to"], s["from"], pages=3, ask=ask, again={paired["to"]["key"]}, places=lambda kind, x: [])
    sent = {t["key"]: t for j in jobs for t in _payload(j)["targets"]}
    assert paired["to"]["key"] in sent and sent[paired["to"]["key"]]["status"] == "ambiguous"
    assert sent[paired["to"]["key"]]["candidates"][0]["key"] == paired["from"]["key"]
    assert r["sigs"]["groups"][paired["to"]["key"]] == ""
