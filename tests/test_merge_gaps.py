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
    """답 검증 — 보낸 자리·후보에 없는 id · 라벨 줄에 content · 차년도가 어긋나는 줄 · 긴 내용 · 제목뿐인 줄은 안 받는다. 빈 표에 원본 표를 고르면 그 표의 칸 답은 버린다(한 자리를 두 길이 쓰지 않게)."""
    d, tgt, src, goal, line = pair
    T, F, fixed = _sides(d, tgt, src)
    found = G.targets(T, F, fixed)
    cell, define = _slot(found, "cell", "추진목표"), _slot(found, "line", "정의")
    cand = lambda year=1: {"id": goal, "year": year}  # noqa: E731
    base = {"F": F, "T": T, "tables": {"tA": {"ctx": {"org": None, "year": 1}, "cands": {"fOK": {"org": None, "year": 1}, "fBAD": {"org": None, "year": 2}}}},
            "slots": {cell["id"]: {**cell, "cands": {goal: cand()}}, define["id"]: {**define, "cands": {line: {"id": line, "year": None}, goal: cand(None)}}}}
    got, rej = G.check(base, {"tables": [{"to": "tA", "from": "fBAD", "reason": ""}, {"to": "없는표", "from": "fOK", "reason": ""}],
                              "slots": [{"to": cell["id"], "from": "p-없는줄", "take": "content", "reason": ""}, {"to": define["id"], "from": line, "take": "content", "reason": ""}]})
    assert not got["tables"] and not got["slots"] and len(rej) == 4   # 차년도가 다른 표 · 보낸 표가 아님 · 후보에 없는 줄 · 라벨 줄에 content
    year = {**base, "slots": {cell["id"]: {**cell, "cands": {goal: cand(2)}}}}
    assert G.check(year, {"tables": [], "slots": [{"to": cell["id"], "from": goal, "take": "content", "reason": ""}]}) == ({"tables": {}, "slots": {}}, [{"to": cell["id"], "why": G.NOTE["year"]}])
    monkeypatch.setattr(G, "LINES_MAX", 1)   # 두 줄짜리 내용이 「긴 내용」 이 되게
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
