"""빈 자리 검토(spec_병합 ② §5-4 · app/merge_gaps.py) — 다른 길이 못 채운 목적 자리(글머리만 있는 칸 · 라벨만 있는 줄)에 LLM 이 고른 원본 줄의 글을 스크립트가 그대로 옮긴다.
저장소 안 자료만(merge_data.small): 계획서 양식의 요약문 「[1차년도 목표]」 아래와 「□ … 정의 및 범위」 아래 「o」 줄에 시험이 글을 쓴 것(원본) ↔ 같은 값으로 반영한 연차보고서 서식(목적).
LLM 은 가짜(보낸 자료에서 시험이 고른다) — 후보 고르기 · 답 검증 · 넣기 계획 · 반영 · 다시 계획을 본다."""
import json

import pytest

import merge_data as M
from app import merge_fixed as X
from app import merge_gaps as G
from app.division_profiles import _structure as structure

GOALS = ["ㅇ 시험 목표 하나를 세운다", "ㅇ 시험 목표 둘을 세운다"]
DEFINE = "운항 데이터를 한곳에 모으는 시험용 정의 문단입니다"


def _para(doc, pred):
    return next(b for b in structure.iter_blocks(doc.blocks()) if b.get("type") == "paragraph" and pred(b.get("text") or ""))


def _sides(d, tgt, src):
    to, frm = {**d["to"], "doc": tgt, "values": d["values"]}, {**d["from"], "doc": src, "values": d["values"]}
    T, F = X._side(to), X._side(frm)
    return T, F, X.plan(to, frm, sides=(T, F))


@pytest.fixture()
def pair():
    """(d, 목적 문서, 원본 문서, 원본의 「[1차년도 목표]」 줄 id, 원본의 「o (정의) …」 줄 id) — 문서는 시험마다 새 사본."""
    d = M.small()
    tgt, src = M.fresh(d["to"]), M.fresh(d["from"])
    F0 = X._side({**d["from"], "doc": src, "values": d["values"]})
    goal = next(n["id"] for n in F0["nodes"] if (F0["idx"].get(n["id"]) or {}).get("text", "").strip() == "[1차년도 목표]")
    first = G.content(F0, goal)[0]["id"]   # 라벨 아래의 빈 글머리 줄
    src.set_text(first, GOALS[0])
    src.insert_after(first, [{"kind": "paragraph", "text": GOALS[1]}])
    scope = next(n["id"] for n in F0["nodes"] if "정의 및 범위" in ((F0["idx"].get(n["id"]) or {}).get("text") or "") and n.get("flow") == "body")
    line = next(b["id"] for b in G.content(F0, scope) if (b.get("text") or "").strip() == "o")
    src.set_text(line, f"  o (정의) {DEFINE}")
    return d, tgt, src, goal, line


def _slot(found, kind, label):
    return next(s for s in found["slots"] if s["kind"] == kind and s["label"] == label)


def _fake(monkeypatch, choose):
    """가짜 LLM — 단위마다 보낸 자료(JSON)를 choose(payload) 에 넘겨 답을 받는다. → 보낸 자료 목록."""
    sent = []

    def ask_all(jobs):
        out = []
        for j in jobs:
            payload = json.loads(j["content"].split("## 자료(JSON)\n", 1)[1])
            sent.append(payload)
            out.append({"data": choose(payload), "backend": "fake", "ms": 1})
        return out
    monkeypatch.setattr(G.llm, "ask_all", ask_all)
    return sent


def test_targets_are_bullet_cells_and_label_only_lines(pair):
    """빈 자리 = 서식이 글머리 자리표시(「ㅇ」 줄)를 둔 칸(「추진목표」 — 3단계가 머리 칸을 못 읽은 표라 첫 행의 같은 열 칸이 머리) + 글이 괄호 라벨뿐인 본문 줄(「- (정의)」).
    결과를 적는 칸(「달성내용」·「달성도」)과 결과를 적는 라벨은 빈 자리가 아니다(계획서에 없는 내용)."""
    d, tgt, src, goal, line = pair
    T, F, fixed = _sides(d, tgt, src)
    found = G.targets(T, F, fixed)
    cell = _slot(found, "cell", "추진목표")
    assert cell["ctx"]["year"] == 1 and cell["was"].replace(" ", "") == "ㅇㅇ"   # 「해당연도」 표 = 당해 차년도
    assert {"정의", "범위", "배경", "필요성"} <= {s["label"] for s in found["slots"] if s["kind"] == "line"}
    assert not [s for s in found["slots"] if "달성" in s["label"].replace(" ", "") or "실적" in s["label"]]
    assert G.open_count(found, None) == len(found["tables"]) + len(found["slots"]) and G.open_count(found, {"slots": {cell["id"]: {"from": None}}}) == G.open_count(found, None) - 1


def test_review_plan_apply_and_replan(pair, monkeypatch):
    """검토 → 계획 → 반영 → 다시 계획. 후보는 스크립트가 고른다 — 「추진목표」(1차년도)의 후보에 「[1차년도 목표]」 는 있고 「[2차년도 목표]」 는 없다(차년도가 어긋남).
    칸에는 라벨 아래 줄들이 줄마다 한 문단으로(content), 라벨 줄에는 원본 한 문단이 같은 문단에 이어진다(line — 앞 글머리와 같은 라벨은 뗀다). 글은 원본 그대로다."""
    d, tgt, src, goal, line = pair
    T, F, fixed = _sides(d, tgt, src)
    found = G.targets(T, F, fixed)
    cell, define = _slot(found, "cell", "추진목표"), _slot(found, "line", "정의")
    pick = {cell["id"]: (goal, "content"), define["id"]: (line, "line")}
    sent = _fake(monkeypatch, lambda p: {"tables": [{"to": t["key"], "from": "", "reason": "없음"} for t in p["tables"]],
                                         "slots": [{"to": s["id"], "from": pick.get(s["id"], ("", ""))[0], "take": pick.get(s["id"], ("", "line"))[1], "reason": "시험"} for s in p["slots"]]})
    res = G.review(T, F, fixed)
    slots = {s["id"]: s for p in sent for s in p["slots"]}
    cands = {c["id"]: c for c in slots[cell["id"]]["candidates"]}
    assert goal in cands and cands[goal]["year"] == 1 and cands[goal]["lines"] == 2 and "시험 목표 하나" in cands[goal]["preview"]
    assert not [c for c in cands.values() if c["year"] == 2]   # 2차년도 줄은 후보가 아니다
    assert slots[define["id"]]["candidates"][0]["id"] == line   # 그 라벨로 시작하는 줄이 먼저
    assert res["asked"] == len(sent) >= 1 and not res["rejected"]
    assert (res["slots"][cell["id"]]["from"], res["slots"][cell["id"]]["take"]) == (goal, "content") and res["slots"][define["id"]]["from"] == line
    assert all(v["from"] is None for k, v in res["slots"].items() if k not in pick)   # 나머지는 「원본 없음」 으로 적힌다(다시 안 묻게)
    gaps = {"tables": res["tables"], "slots": res["slots"]}
    assert G.open_count(found, gaps) == 0 and not G.prepare(T, F, fixed, gaps)["units"] and G.prepare(T, F, fixed, gaps, again=True)["units"]
    p = G.plan(T, F, gaps)
    assert (p["counts"]["cells"], p["counts"]["lines"], p["todo"]) == (1, 1, 2)
    assert p["cells"][0]["text"] == "\n".join(GOALS) and p["lines"][0]["text"] == f"{define['was']} {DEFINE}"
    done = G.apply(tgt, p)
    assert (done["cells"], done["lines"], done["skipped"]) == (1, 1, [])
    idx = structure.index_blocks(tgt.blocks())
    assert idx[cell["id"]]["text"] == "\n".join(GOALS) and idx[define["id"]]["text"].strip() == f"- (정의) {DEFINE}"
    T2, F2, fixed2 = _sides(d, tgt, src)   # 다시 계획 — 넣은 자리는 글이 같아 일 없음 · 더는 빈 자리도 아니다
    again = G.plan(T2, F2, gaps)
    assert again["todo"] == 0 and {it["skip"] for it in again["items"]} == {"done"}
    left = G.targets(T2, F2, fixed2)
    assert cell["id"] not in {s["id"] for s in left["slots"]} and define["id"] not in {s["id"] for s in left["slots"]}


def test_written_places_are_not_overwritten(pair, monkeypatch):
    """계획 뒤 사람이 그 자리에 글을 쓰면 넣지 않는다 — 반영은 `occupied` 로 건너뛰고, 다시 계획해도 `occupied`."""
    d, tgt, src, goal, line = pair
    T, F, fixed = _sides(d, tgt, src)
    found = G.targets(T, F, fixed)
    cell, define = _slot(found, "cell", "추진목표"), _slot(found, "line", "정의")
    gaps = {"slots": {cell["id"]: {"from": goal, "take": "content", "kind": "cell", "was": cell["was"], "label": cell["label"]},
                      define["id"]: {"from": line, "take": "line", "kind": "line", "was": define["was"], "label": define["label"]}}}
    p = G.plan(T, F, gaps)
    tgt.set_text(cell["id"], "ㅇ 사람이 쓴 목표")
    tgt.set_text(define["id"], " - (정의) 사람이 쓴 정의")
    done = G.apply(tgt, p)
    assert (done["cells"], done["lines"]) == (0, 0) and {s["why"] for s in done["skipped"]} == {"occupied"}
    T2, F2, _ = _sides(d, tgt, src)
    again = G.plan(T2, F2, gaps)
    assert again["todo"] == 0 and again["counts"]["skipped"]["occupied"] == 2


def test_check_rejects_what_the_data_does_not_allow(pair, monkeypatch):
    """답 검증 — 보낸 자리·후보에 없는 id · 모르는 take · 차년도가 어긋나는 줄 · 긴 내용 · 제목뿐인 줄은 안 받는다. 빈 표에 원본 표를 고르면 그 표의 칸 답은 버린다(한 자리를 두 길이 쓰지 않게)."""
    d, tgt, src, goal, line = pair
    T, F, fixed = _sides(d, tgt, src)
    found = G.targets(T, F, fixed)
    cell, define = _slot(found, "cell", "추진목표"), _slot(found, "line", "정의")
    cand = lambda year=1: {"id": goal, "year": year}  # noqa: E731
    base = {"F": F, "T": T, "tables": {"tA": {"ctx": {"org": None, "year": 1}, "cands": {"fOK": {"org": None, "year": 1}, "fBAD": {"org": None, "year": 2}}}},
            "slots": {cell["id"]: {**cell, "cands": {goal: cand()}}, define["id"]: {**define, "cands": {line: {"id": line, "year": None}, goal: cand(None)}}}}
    got, rej = G.check(base, {"tables": [{"to": "tA", "from": "fBAD", "reason": ""}, {"to": "없는표", "from": "fOK", "reason": ""}],
                              "slots": [{"to": cell["id"], "from": "p-없는줄", "take": "content", "reason": ""}, {"to": define["id"], "from": line, "take": "아래", "reason": ""}]})
    assert not got["tables"] and not got["slots"] and len(rej) == 4   # 차년도가 다른 표 · 보낸 표가 아님 · 후보에 없는 줄 · 모르는 take(라벨 줄의 content 는 이제 받는다 — 아래 「라벨 줄 아래의 내용」 시험)
    year = {**base, "slots": {cell["id"]: {**cell, "cands": {goal: cand(2)}}}}
    assert G.check(year, {"tables": [], "slots": [{"to": cell["id"], "from": goal, "take": "content", "reason": ""}]}) == ({"tables": {}, "slots": {}}, [{"to": cell["id"], "why": G.NOTE["year"]}])
    monkeypatch.setattr(G, "CELL_LINES_MAX", 1)   # 두 줄짜리 내용이 「긴 내용」 이 되게(칸의 한도)
    got, rej = G.check(base, {"tables": [], "slots": [{"to": cell["id"], "from": goal, "take": "content", "reason": "r"}]})
    assert got["slots"][cell["id"]]["from"] is None and rej == [{"to": cell["id"], "why": G.NOTE["long"]}]   # 「원본 없음」 으로 적힌다(다시 안 묻게)
    got, rej = G.check(base, {"tables": [], "slots": [{"to": define["id"], "from": goal, "take": "line", "reason": ""}]})   # 「[1차년도 목표]」 = 제목뿐인 줄 — 줄 자체의 글로는 못 옮긴다
    assert got["slots"][define["id"]]["from"] is None and rej[0]["why"] == G.NOTE["noSource"]
    whole = {**base, "slots": {cell["id"]: {**cell, "table": "tA", "cands": {goal: cand()}}}}
    got, rej = G.check(whole, {"tables": [{"to": "tA", "from": "fOK", "reason": "같은 표"}], "slots": [{"to": cell["id"], "from": goal, "take": "content", "reason": ""}]})
    assert got["tables"] == {"tA": {"from": "fOK", "reason": "같은 표"}} and got["slots"][cell["id"]]["from"] is None and not rej


def test_failed_unit_stays_open_and_candidate_less_places_are_closed(pair, monkeypatch):
    """한 단위의 호출이 실패하면 그 자리는 안 물은 것으로 남는다(다음에 다시). 후보가 하나도 없는 빈 자리는 묻지 않고 「원본 없음」 으로 닫는다."""
    d, tgt, src, goal, line = pair
    T, F, fixed = _sides(d, tgt, src)
    found = G.targets(T, F, fixed)
    monkeypatch.setattr(G.llm, "ask_all", lambda jobs: [{"data": None, "error": "시간 초과"} for _ in jobs])
    res = G.review(T, F, fixed)
    prep = G.prepare(T, F, fixed)
    asked = {s["id"] for u in prep["units"] for s in u["payload"]["slots"]}
    assert res["asked"] >= 1 and all(u["error"] for u in res["units"]) and asked and not asked & set(res["slots"])
    bare = [s["id"] for s in found["slots"] if s["id"] not in asked]
    assert all(res["slots"][i]["from"] is None and res["slots"][i]["reason"] for i in bare)
    assert G.open_count(found, res) == len(asked) + sum(1 for t in found["tables"] if t["key"] not in res["tables"])


# ---- 라벨 줄 아래의 내용 · 쪽 한도(spec_병합 ② §5-6 — 2026-11-22 사용자 「서식은 다르지만 매칭이 되잖아 … 2페이지 내에서 개요를 매핑하도록」) ----

BELOW = ["- 시험용 정의의 첫 문단입니다 — 제목 줄 아래에 적혀 있습니다", "- 시험용 정의의 둘째 문단입니다", "- 시험용 정의의 셋째 문단입니다"]


@pytest.fixture()
def below(pair):
    """pair + 원본의 「□ … 정의 및 범위」 제목 **아래에** 문단 셋(라벨과 내용이 한 줄이 아닌 계획서 — 「□ 개발 기술(제품)의 정의」 아래 문단들의 꼴) → (…, 그 제목 줄 id)."""
    d, tgt, src, goal, line = pair
    F0 = X._side({**d["from"], "doc": src, "values": d["values"]})
    scope = next(n["id"] for n in F0["nodes"] if "정의 및 범위" in ((F0["idx"].get(n["id"]) or {}).get("text") or "") and n.get("flow") == "body")
    src.set_text(line, BELOW[0])
    src.insert_after(line, [{"kind": "paragraph", "text": t} for t in BELOW[1:]])
    return d, tgt, src, scope


def test_label_lines_under_a_page_limit_get_a_line_budget(below):
    """「1. 연구개발과제의 개요 ※ 2page 이내 요약 작성」 아래의 라벨 줄(「- (정의)」 …)은 줄 한도를 갖는다 — 2쪽의 줄 수에서 그 제목 아래 서식 줄을 빼고 라벨 줄 수로 나눈 것(자리마다 같은 몫).
    양식의 매칭 지침에 쪽 한도가 적혀 있으면 서식의 「※ 2page 이내」 글이 없어도(문서 정리 뒤) 같은 한도다."""
    d, tgt, src, scope = below
    T, F, fixed = _sides(d, tgt, src)
    lines = [s for s in G.targets(T, F, fixed)["slots"] if s["kind"] == "line" and s["label"] in ("정의", "범위", "배경", "필요성")]
    assert len(lines) == 4 and len({s["budget"] for s in lines}) == 1
    assert G.BUDGET_MIN <= lines[0]["budget"] <= 2 * G.PAGE_LINES // 4
    head = next(n for n in T["nodes"] if "2page" in (T["idx"].get(n["id"]) or {}).get("text", ""))
    tgt.set_text(head["id"], "1. 연구개발과제의 개요")   # 문서 정리가 「※ 2page 이내 요약 작성」 을 지운 뒤
    T2, F2, fixed2 = _sides(d, tgt, src)
    bare = _slot(G.targets(T2, F2, fixed2), "line", "정의")
    assert bare["budget"] is None
    guides = [{"n": 0, "kind": "body", "title": "1. 연구개발과제의 개요 ※ 2page 이내 요약 작성", "text": "2쪽 안에서", "pages": 2}]
    assert _slot(G.targets(T2, F2, fixed2, guides=guides), "line", "정의")["budget"] == lines[0]["budget"]


def test_label_line_takes_the_content_below_a_heading(below, monkeypatch):
    """라벨 줄 ← 제목 줄 **아래의 내용**(take content): 서식이 달라도 같은 내용이면 잇는다 — 내용 블록이 라벨 줄 뒤에 원본 차례 그대로 복사된다(라벨 줄의 글은 그대로). 자료에는 그 자리의 줄 한도와
    그 자리에 걸린 매칭 지침이 실린다. 다시 계획하면 일 없음 · 더는 빈 자리도 아니다."""
    d, tgt, src, scope = below
    T, F, fixed = _sides(d, tgt, src)
    guides = [{"n": 0, "kind": "body", "title": "1. 연구개발과제의 개요 ※ 2page 이내 요약 작성", "text": "계획서의 정의 절에서 2쪽 안에서 옮긴다", "pages": 2}]
    found = G.targets(T, F, fixed, guides=guides)
    define = _slot(found, "line", "정의")
    sent = _fake(monkeypatch, lambda p: {"tables": [{"to": t["key"], "from": "", "reason": ""} for t in p["tables"]],
                                         "slots": [{"to": s["id"], "from": scope if s["id"] == define["id"] else "", "take": "content", "reason": "제목 아래"} for s in p["slots"]]})
    res = G.review(T, F, fixed, guides=guides)
    slot = next(s for p in sent for s in p["slots"] if s["id"] == define["id"])
    assert slot["budget"] == define["budget"] and slot["guide"] and "2쪽 안에서" in slot["guide"][0] and scope in {c["id"] for c in slot["candidates"]}
    got = res["slots"][define["id"]]
    assert (got["from"], got["take"], got["budget"]) == (scope, "content", define["budget"]) and not res["rejected"]
    gaps = {"tables": res["tables"], "slots": res["slots"]}
    p = G.plan(T, F, gaps)
    assert p["counts"]["blocks"] == 1 and p["todo"] == 1 and len(p["blocks"][0]["src"]) == 3 and p["blocks"][0]["left"] == 0
    done = G.apply(tgt, p, src)
    assert done["blocks"] == 1 and not done["skipped"] and len(done["inserted"][define["id"]]) == 3
    seq = [b for b in structure.iter_blocks(tgt.blocks()) if b.get("type") == "paragraph"]
    k = next(i for i, b in enumerate(seq) if b["id"] == define["id"])
    assert seq[k]["text"].strip() == "- (정의)" and [b["text"].strip() for b in seq[k + 1:k + 4]] == BELOW
    T2, F2, fixed2 = _sides(d, tgt, src)
    again = G.plan(T2, F2, gaps)
    assert again["todo"] == 0 and [it["skip"] for it in again["items"]] == ["done"]
    assert define["id"] not in {s["id"] for s in G.targets(T2, F2, fixed2, guides=guides)["slots"]}
    assert G.apply(tgt, p) == {"cells": 0, "lines": 0, "blocks": 0, "inserted": {}, "dropped": [], "fitted": 0,
                               "skipped": [{"to": define["id"], "why": "occupied", "detail": "원본 문서를 못 읽음"}]}   # 원본 문서 없이는 내용을 못 넣는다(덮지 않는다)


def test_content_below_is_cut_to_the_budget_and_whole_without_one(below):
    """줄 한도가 있는 자리는 한도 안의 **앞부분만** 넣고 남긴 수를 알린다. 한도가 없는 자리의 내용은 통째로만 — 길면 안 넣는다(기관이 작성). 라벨 아래에 사람이 쓴 글이 있으면 안 넣는다."""
    d, tgt, src, scope = below
    T, F, fixed = _sides(d, tgt, src)
    define = _slot(G.targets(T, F, fixed), "line", "정의")
    rec = lambda **kw: {"slots": {define["id"]: {"from": scope, "take": "content", "kind": "line", "was": define["was"], "label": "정의", **kw}}}  # noqa: E731
    cut = G.plan(T, F, rec(budget=2))   # 한 줄짜리 문단 셋 가운데 둘
    assert cut["todo"] == 1 and len(cut["blocks"][0]["src"]) == 2 and cut["blocks"][0]["left"] == 1 and "뒤 1개" in cut["items"][0]["detail"]
    other = M.fresh(d["from"])
    table = next(b["id"] for b in other.blocks() if b.get("type") == "table" and len(b.get("cells") or ()) > 1)
    src.insert_after(scope, [{"kind": "copy", "srcId": table}], src=other)   # 제목 바로 아래에 표 — 요약 자리(한도가 있는 자리)는 표 · 그림을 건너뛰고 글만 잇는다
    Tt, Ft, _ = _sides(d, tgt, src)
    skip = G.plan(Tt, Ft, rec(budget=20))
    assert len(skip["blocks"][0]["src"]) == 3 and skip["blocks"][0]["left"] == 1 and G.plan(Tt, Ft, rec())["items"][0]["skip"] == "object"   # 한도가 없는 자리는 표가 들면 통째로 안 넣는다
    whole = G.plan(T, F, rec())
    assert len(whole["blocks"][0]["src"]) == 3
    old = G.LINES_MAX
    G.LINES_MAX = 2
    try:
        long = G.plan(T, F, rec())
    finally:
        G.LINES_MAX = old
    assert long["todo"] == 0 and long["items"][0]["skip"] == "long"
    tgt.insert_after(define["id"], [{"kind": "paragraph", "text": "사람이 쓴 정의"}])
    T2, F2, _ = _sides(d, tgt, src)
    kept = G.plan(T2, F2, rec(budget=20))
    assert kept["todo"] == 0 and kept["items"][0]["skip"] == "occupied"


def test_places_put_each_slot_its_guides_and_a_changed_guide_reopens_only_that_slot(pair):
    """자리마다의 작성 지침(spec_병합 ② §5-11): 빈 자리마다 `guides`(작성 지침 — 매칭 지침 `guide` 와 따로) · 판(guideSig)을 ctx 에.
    저장된 답의 판이 지금과 다르면 그 자리만 다시 묻는다(판이 없는 옛 답 = 판 "") · 판이 같은 답은 그대로 · places 가 없으면(지침을 못 읽음) 판을 안 본다."""
    from app import place_guides as PG
    d, tgt, src, goal, line = pair
    T, F, fixed = _sides(d, tgt, src)
    text = {"now": "지금 지침"}
    places = lambda kind, x: [{"src": "user", "kind": "사용자 지침", "text": f"{text['now']} {x}"}]  # noqa: E731
    prep = G.prepare(T, F, fixed, places=places)
    slots = [s for u in prep["units"] for s in u["payload"]["slots"]]
    assert slots and all(s["guides"][0]["text"] == f"지금 지침 {s['id']}" for s in slots)
    assert all(PG.CONTRACT_LINE in G.prompt(u["payload"]) for u in prep["units"])
    sid = slots[0]["id"]
    sig = prep["ctx"]["slots"][sid]["guideSig"]
    assert sig == PG.sig(places("block", sid))
    asked = lambda saved, pl=places: {s["id"] for u in G.prepare(T, F, fixed, saved, places=pl)["units"] for s in u["payload"]["slots"]}  # noqa: E731
    assert sid not in asked({"slots": {sid: {"from": None, "reason": "옛 답", "guideSig": sig}}})   # 판이 같은 답 — 다시 안 묻는다
    assert sid in asked({"slots": {sid: {"from": None, "reason": "판이 없는 옛 답"}}})   # 판이 없는 옛 답 = 지침 없이 받은 답 — 지금 그 자리에 지침이 있으니 다시 묻는다(astra 3차)
    assert sid not in asked({"slots": {sid: {"from": None, "reason": "판이 없는 옛 답"}}}, lambda kind, x: [])   # 지금도 지침이 없는 자리는 그대로
    text["now"] = "고친 지침"
    assert sid in asked({"slots": {sid: {"from": None, "reason": "옛 답", "guideSig": sig}}})   # 그 자리의 지침이 바뀜 — 다시 묻는다
    assert sid not in asked({"slots": {sid: {"from": None, "reason": "옛 답", "guideSig": sig}}}, None)   # 지침을 못 읽으면 판을 안 본다(다시 묻지 않는다)
