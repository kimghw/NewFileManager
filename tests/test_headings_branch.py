"""헤딩 추출 2단계 — 템플릿 가지 규칙(spec_헤딩_추출 ② §0 「템플릿 가지 규칙」·§6 「템플릿 가지」, 2026-11-09 사용자 확정 + astra 협의).
astra 가 요구한 회귀 목록: 라벨 안/밖 같은 o · 다음 라벨·(N)·□ 복귀 · (N)→가.·□→① (지식이 앞 공백·서열을 이김) · L2→L4 생략(B 슬롯 예외) · B 수정 보존 ·
라벨 L1 조정 · 중첩 인스턴스 · 양식 기대값(사용자가 본 두 화면). LLM 은 가짜 ask."""
import copy
import json
from pathlib import Path

import pytest

from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app.hwpx_doc import HwpxDoc

RND = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _res(data=None, error=None, cost=0.0):
    return {"data": data, "backend": "fake", "model": "fake", "ms": 0, "costUsd": cost, "error": error}


def _data(job):
    return json.loads(job["content"].rsplit("## 자료(JSON)\n", 1)[1])


def fake_ask(**handlers):
    handlers.setdefault("heading_section", lambda job, d: _res({"changes": [], "summary": ""}))
    handlers.setdefault("heading_formats", lambda job, d: _res({"pairs": [], "summary": ""}))
    handlers.setdefault("heading_review", lambda job, d: _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "verdict": "agree", "same": p["first"]["same"],
                                                                          "reason": "동의"} for p in d["pairs"]], "summary": ""}))
    seen = []

    def ask(jobs):
        out = []
        for job in jobs:
            seen.append(job["what"])
            out.append(handlers[job["what"].split("#", 1)[0]](job, _data(job)))
        return out
    ask.seen = seen
    return ask


def _rec(i, letter, shape, family, text="", lead=0, fmt="S1", kind="marker"):
    """1단계 레코드(필요한 칸만). kind label 이면 letter = 「[…]」 글 전체, 제목(rest)은 빈 글."""
    full = " " * lead + (letter + (" " + text if text else ""))
    return {"id": f"p{i}", "n": i, "area": "body", "path": [], "table": None, "cell": None, "kind": kind, "family": family, "shape": shape,
            "letter": " " * lead + letter, "rest": text, "text": full, "leadSpaces": lead, "fmt": fmt,
            "char": {"text": {"sizePt": 10.0, "bold": False}}, "blank": not text,
            "spans": [{"i": 0, "line": 0, "kind": kind, "family": family, "letter": letter}]}


def _stage1(rows):
    """rows = (letter, shape, family, text, lead[, fmt]) — label 은 shape "[…]" · family "bracket"."""
    paras = []
    for r in rows:
        letter, shape, family, text, lead = r[:5]
        fmt = r[5] if len(r) > 5 else "S1"
        paras.append(_rec(len(paras), letter, shape, family, text, lead, fmt, kind="label" if family == "bracket" else "marker"))
    return {"paras": paras, "labels": {"S1": {"name": "보통"}, "S2": {"name": "굵게"}}}


def _a(stage1, parents, main, basis=None):
    """가짜 A — shape 별 parents, 라벨 basis(shape → basis), 주 사슬."""
    types = HG.type_table(HG.candidates(stage1))
    out = []
    for tid, t in types.items():
        if t["kind"] == "label":
            out.append({"type": tid, "role": "label", "parents": [], "variantOf": "", "basis": (basis or {}).get(t["shape"], "기관"), "reason": ""})
        else:
            out.append({"type": tid, "role": "heading", "parents": parents.get(t["shape"], []), "variantOf": "", "basis": "", "reason": ""})
    return {"types": out, "mainChain": list(main), "summary": "가짜"}


def _nodes(g):
    return {n["id"]: n for n in g["nodes"]}


# ---- 라벨 안/밖 같은 o · 다음 라벨·(N)·□ 복귀 · 중첩 인스턴스 ----------------------------------------------------------------

def _label_doc():
    rows = [("1.", "N.", "decimal", "장", 0),
            ("(1)", "(N)", "paren-num", "1차년도", 1),
            ("[주관기관]", "[주관기관]", "bracket", "", 2), ("o", "o", "latin-o", "가", 2), ("o", "o", "latin-o", "나", 2),
            ("[공동기관]", "[공동기관]", "bracket", "", 2), ("o", "o", "latin-o", "다", 2),
            ("(2)", "(N)", "paren-num", "2차년도", 1),
            ("o", "o", "latin-o", "라", 2),  # 라벨 밖 o — 주 사슬 L3
            ("□", "□", "square", "네모", 1)]  # (2) 아래 가지
    st1 = _stage1(rows)
    A = _a(st1, {"N.": ["root"], "(N)": ["N."], "o": ["[기관]", "(N)"], "□": ["(N)"]}, ["N.", "(N)", "o"])
    return st1, A


def test_o_inside_label_is_label_template_and_outside_is_main():
    st1, A = _label_doc()
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A)))
    N = _nodes(g)
    lab1, oa, ob, lab2, oc, y2, od, sq = (N[f"p{i}"] for i in (2, 3, 4, 5, 6, 7, 8, 9))
    assert lab1["role"] == "label" and (lab1["template"], lab1["level"]) == ("body:[기관]›o", 1) and lab1["parent"] == "p1"
    assert oa["parent"] == "p2" and (oa["tplNo"], oa["level"], oa["division"]) == (lab1["tplNo"], 2, "p2")
    assert ob["parent"] == "p2" and ob["level"] == 2  # 라벨 안 둘째 o 는 첫 o 의 형제
    assert lab2["parent"] == "p1" and lab2["tplNo"] == lab1["tplNo"] and oc["parent"] == "p5"  # 다음 라벨 = 앞 라벨의 형제, 그 아래 o
    assert y2["parent"] == "p0" and (y2["tplNo"], y2["level"]) == (1, 2)  # (N) 이 오면 라벨 범위 끝 — 주 사슬 복귀
    assert od["parent"] == "p7" and (od["tplNo"], od["level"], od["division"]) == (1, 3, None)  # 라벨 밖 o = 주 사슬 L3
    assert sq["parent"] == "p7" and sq["level"] == 1 and sq["template"] == "body:□" and sq["tplNo"] not in (1, lab1["tplNo"])
    # 인스턴스 — 라벨마다 하나(같은 템플릿 #), 주 사슬 인스턴스(1.)의 childInstances 에 라벨 인스턴스·□ 가지
    ins = {i["root"]: i for i in g["instances"]}
    assert ins["p2"]["template"] == ins["p5"]["template"] == lab1["tplNo"] and [ins["p2"]["no"], ins["p5"]["no"]] == [1, 2]
    assert ins["p2"]["members"] == ["p3", "p4"] and ins["p5"]["members"] == ["p6"] and ins["p2"]["basis"] == "[주관기관]"
    assert ins["p2"]["parent"] == "p1" and ins["p2"]["i"] in ins["p0"]["childInstances"] and ins["p9"]["i"] in ins["p0"]["childInstances"]
    assert {"p1", "p7", "p8"} <= set(ins["p0"]["members"])
    tp = {t["anchor"]: t for t in g["templates"]}
    assert [t["kind"] for t in g["templates"]] == ["main", "branch", "label"] and tp["body:[기관]›o"]["instances"] == 2
    assert tp["body:[기관]›o"]["where"] == [{"parent": "(N)", "count": 2}]
    assert {h["parent"]: sorted(x["key"] for x in h["letters"]) for h in g["heterogeneous"]} == {"p7": ["o", "□"]}


def test_label_template_l1_is_a_slot_for_adjustment():
    """라벨 L1 도 슬롯 — 라벨 서식이 갈리면 조정 쌍이 라벨 템플릿 슬롯으로 C 에 간다."""
    rows = [("1.", "N.", "decimal", "장", 0), ("(1)", "(N)", "paren-num", "1차년도", 1),
            ("[A기관]", "[A기관]", "bracket", "", 2, "S1"), ("o", "o", "latin-o", "가", 2),
            ("[B기관]", "[B기관]", "bracket", "", 2, "S1"), ("o", "o", "latin-o", "나", 2),
            ("[C기관]", "[C기관]", "bracket", "", 2, "S2"), ("o", "o", "latin-o", "다", 2)]
    st1 = _stage1(rows)
    A = _a(st1, {"N.": ["root"], "(N)": ["N."], "o": ["[기관]"]}, ["N.", "(N)"])
    asked = []

    def c(job, d):
        asked.extend(p["slot"] for p in d["pairs"])
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": True, "reason": "C"} for p in d["pairs"]], "summary": ""})
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A), heading_formats=c))
    assert asked == ["body:[기관]›o|L1"]
    adj = g["adjustments"]
    assert [(a["id"], a["template"], a["level"], a["from"], a["to"], a["decision"]) for a in adj] == [("p6", "body:[기관]›o", 1, "S2", "S1", "adjust")]
    assert adj[0]["review"]["verdict"] == "agree" and g["counts"]["adjust"] == 1


# ---- 지식이 앞 공백·서열을 이긴다: (N) → 가. · □ → ① -------------------------------------------------------------------------

def test_knowledge_beats_indent_and_rank():
    rows = [("1.", "N.", "decimal", "장", 0),
            ("(1)", "(N)", "paren-num", "괄호", 2),
            ("가.", "가.", "hangul-dot", "가나다", 1),  # 서열은 (N) 보다 얕고 앞 공백도 적지만 A: 가. 의 부모 = (N)
            ("□", "□", "square", "네모", 0),
            ("①", "①", "circled", "동그라미", 0)]  # A: ① 의 부모 = □
    st1 = _stage1(rows)
    A = _a(st1, {"N.": ["root"], "(N)": ["N."], "가.": ["(N)"], "□": ["N."], "①": ["□"]}, ["N.", "(N)"])
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A)))
    N = _nodes(g)
    assert N["p2"]["parent"] == "p1" and (N["p2"]["tplNo"], N["p2"]["level"]) == (1, 3)  # 주 사슬이 (N) 뒤로 이어 배움
    assert N["p3"]["parent"] == "p0" and N["p3"]["template"] == "body:□›①" and N["p4"]["parent"] == "p3" and N["p4"]["level"] == 2
    assert not any(n["heuristic"] for n in g["nodes"])
    # 지식 없는 어림(fallback)은 서열·앞 공백을 따라 다르게 본다 — heuristic 표지
    g2 = HG.build(st1, use_llm=False)
    N2 = _nodes(g2)
    assert N2["p2"]["parent"] == "p0" and N2["p2"]["heuristic"] and g2["counts"]["heuristic"] >= 1


# ---- L2 → L4 생략은 B 의 슬롯 예외 · B 의 부모 변경은 재배정 뒤에도 보존 -----------------------------------------------------------

def test_skipped_level_needs_slot_exception_and_parent_change_survives_reassignment():
    rows = [("1.", "N.", "decimal", "장", 0), ("1-1.", "N-N.", "hyphen", "절", 0),
            ("o", "o", "latin-o", "건너뜀", 2),  # (N) 없이 1-1. 바로 아래
            ("(1)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "보통", 2), ("o", "o", "latin-o", "둘째", 2)]
    st1 = _stage1(rows)
    M = "body:N.›N-N.›(N)›o"
    A = _a(st1, {"N.": ["root"], "N-N.": ["N."], "(N)": ["N-N."], "o": ["(N)", "N-N."]}, ["N.", "N-N.", "(N)", "o"])
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A)))
    N = _nodes(g)
    assert N["p2"]["parent"] == "p1" and N["p2"]["template"] == "body:o" and N["p2"]["level"] == 1  # 부모만으로는 새 가지
    assert (N["p4"]["template"], N["p4"]["level"]) == (M, 4)

    def b(job, d):
        rows_ = {r[0]: r for r in d["nodes"]}
        assert rows_["p2"][4] == "body:o" and rows_["p2"][5] == 1 and any(t["anchor"] == M for t in d["templates"])  # B 는 초안 배정·템플릿 목록을 본다
        return _res({"changes": [{"id": "p2", "parent": "", "role": "heading", "template": M, "level": 4, "reason": "(N) 을 건너뛴 주 사슬 L4"},
                                 {"id": "p5", "parent": "p2", "role": "heading", "template": "", "level": 0, "reason": "둘째 o 는 건너뜀 o 의 자식"},
                                 {"id": "p4", "parent": "", "role": "heading", "template": "body:없음", "level": 2, "reason": "모르는 앵커"}], "summary": ""})
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A), heading_section=b))
    N = _nodes(g)
    assert (N["p2"]["template"], N["p2"]["level"], N["p2"]["parent"]) == (M, 4, "p1") and N["p2"]["changed"]  # 슬롯 예외 그대로
    assert N["p5"]["parent"] == "p2" and N["p5"]["changed"] and N["p5"]["template"] == "body:o" and N["p5"]["level"] == 1  # 부모 변경 보존 → 재배정(o 아래 o = 가지)
    assert [r["why"] for r in g["rejected"]] == ["모르는 템플릿 body:없음"] and g["llm"]["applied"] == 2
    assert g["llm"]["slotUnresolved"] == []


# ---- 양식 기대값 — 사용자가 본 두 화면 ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rnd():
    tol = G.parse_tolerance(G.default_text("tolerance"))
    return E.extract(HwpxDoc(RND.read_bytes()), store=copy.deepcopy(EMPTY), doc_key="rnd", tol=tol)


def _find(res, prefix, *, start=0, kind="marker"):
    for r in res["paras"][start:]:
        if r["area"] == "body" and r["kind"] == kind and r["text"].strip().startswith(prefix):
            return r
    raise AssertionError(f"문단을 못 찾음: {prefix!r}")


def _after(res, rec, k):
    return [r for r in res["paras"][rec["n"] + 1:] if r["kind"] not in ("empty", "object")][:k]


def _a_sample(rnd):
    """양식용 가짜 A — 레터(shape)별 보통 부모, 라벨 basis 는 글로(기관·단계·측면·구분), 주 사슬 1. › 1-1. › (1) › o › - › ·."""
    types = HG.type_table(HG.candidates(rnd))
    par = {"N.": ["root"], "N-N.": ["N."], "(N)": ["N-N.", "[단계]", "[구분]"], "□": ["N-N.", "(N)", "제목"], "o": ["□", "(N)", "[기관]", "N-N.", "[구분]", "[측면]"],
           "-": ["o"], "·": ["-"], "①": ["(N)", "□"], "가.": ["(N)"], "N)": ["N-N."]}
    out = []
    for tid, t in types.items():
        if t["kind"] == "label":
            s = t["shape"]
            basis = "기관" if "기관" in s else "단계" if "단계" in s else "측면" if "측면" in s else "구분"
            out.append({"type": tid, "role": "label", "parents": [], "variantOf": "", "basis": basis, "reason": ""})
        else:
            key = HG.VARIANTS.get(t.get("family") or "") or t["shape"]
            out.append({"type": tid, "role": "heading" if t["kind"] != "title" else "title", "parents": par.get(key, []), "variantOf": "", "basis": "", "reason": ""})
    return {"types": out, "mainChain": ["N.", "N-N.", "(N)", "o", "-", "·"], "summary": "가짜 A(양식)"}


def test_sample_user_cases(rnd):
    """2026-11-09 사용자 화면 둘: ① 「(1) 최종목표」 는 주 사슬 L3, 그 아래 「□」 는 (1) 의 자식이자 「□ › o › -」 가지 L1(1-1. 아래 □ 와 같은 id);
    ② 「[주관연구개발기관(기관명 기입)]」 은 라벨 템플릿 「[기관] › o」 L1, 그 아래 o 는 라벨을 부모로 L2."""
    A = _a_sample(rnd)
    g = HG.build(rnd, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A)))
    N = _nodes(g)
    assert not g["llm"]["fallback"] and g["llm"]["mainChain"] == A["mainChain"]
    # A 가 확인한 주 사슬은 제약 — (N) 아래 「가.」(연구개발비 절) 가 「o」 보다 많아도 L4 는 o 그대로, 다르게 셈한 자리는 기록만
    assert any(c["level"] == 4 and c["fixed"] == "o" and "가." in c["counted"] for c in g["llm"]["mainChainConflicts"])
    sec = _find(rnd, "2-1. 최종목표")
    goal = _find(rnd, "(1) 최종목표", start=sec["n"])
    f = N[goal["id"]]
    assert (f["parent"], f["tplNo"], f["level"], f["template"]) == (sec["id"], 1, 3, "body:N.›N-N.›(N)›o›-›·")
    sq, o, dash = (N[r["id"]] for r in _after(rnd, goal, 3))
    assert (sq["letter"].strip(), o["letter"].strip(), dash["letter"].strip()) == ("□", "o", "-")
    assert sq["parent"] == goal["id"] and sq["level"] == 1 and sq["template"] == "body:□›o›-›·" and sq["tplNo"] != 1
    assert (o["parent"], o["tplNo"], o["level"]) == (sq["id"], sq["tplNo"], 2) and (dash["parent"], dash["tplNo"], dash["level"]) == (o["id"], sq["tplNo"], 3)
    sq1 = N[_find(rnd, "□ 연구개발기술(제품)의 정의 및 범위")["id"]]
    assert sq1["tplNo"] == sq["tplNo"] and sq1["level"] == 1 and N[sq1["parent"]]["letter"].strip() == "1-1."  # 같은 사슬 = 같은 id, 다른 인스턴스
    ins = {i["root"]: i for i in g["instances"]}
    assert ins[sq1["id"]]["template"] == ins[sq["id"]]["template"] and ins[sq1["id"]]["no"] < ins[sq["id"]]["no"]
    # ② 라벨
    g1 = _find(rnd, "① 개발 목표")
    lab = _find(rnd, "[주관연구개발기관(기관명 기입)]", start=g1["n"], kind="label")
    lo = N[_after(rnd, lab, 1)[0]["id"]]
    L = N[lab["id"]]
    assert L["role"] == "label" and (L["parent"], L["level"]) == (g1["id"], 1) and L["template"].startswith("body:[기관]›o")
    assert lo["letter"].strip() == "o" and (lo["parent"], lo["tplNo"], lo["level"], lo["division"]) == (lab["id"], L["tplNo"], 2, lab["id"])
    lab2 = _find(rnd, "[공동연구개발기관1(기관명 기입)]", start=g1["n"], kind="label")
    assert N[lab2["id"]]["tplNo"] == L["tplNo"] and N[lab2["id"]]["parent"] == g1["id"]  # 기관마다 같은 라벨 템플릿의 인스턴스
    # 템플릿 목록 — 앵커 유일, id 는 1부터 차례, 주 사슬 #1
    tp = g["templates"]
    assert [t["id"] for t in tp] == list(range(1, len(tp) + 1)) and len({t["anchor"] for t in tp}) == len(tp) and tp[0]["kind"] == "main"
    json.dumps(g)
