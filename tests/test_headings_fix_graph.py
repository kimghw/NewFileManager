"""헤딩 추출 2단계 고침 시험(heading_graph·heading_llm) — 칸 안 1칸 상자 흐름 · 루트 라벨 닫힘 · B 변경 검증(템플릿·레벨·부모 역할·구분) ·
C 슬롯별 답 · 미판정 대표 서식 · 작은 최상위 구간 합치기 · 그릇 key 흐름 · plain 규칙 넓이 · 실행 시작 때 고정한 지침(pinned).

LLM 은 늘 끈다 — 가짜 ask(jobs). 규칙·지침 저장소는 시험마다 임시 폴더(NFM_HEADINGS). 큰 표본(연구개발계획서 양식)은 모듈에서 한 번만 뽑는다."""
import copy
import json
from pathlib import Path

import pytest

from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_llm as HL
from app import heading_rules as R
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
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


@pytest.fixture(scope="module")
def rnd():
    tol = G.parse_tolerance(G.default_text("tolerance"))
    return E.extract(HwpxDoc(RND.read_bytes()), store=copy.deepcopy(EMPTY), doc_key="rnd", tol=tol)


def _find(res, prefix, *, area="body", kind=None, start=0):
    for r in res["paras"][start:]:
        if r["area"] == area and r["text"].strip().startswith(prefix) and (kind is None or r["kind"] == kind):
            return r
    raise AssertionError(f"문단을 못 찾음: {prefix!r}")


def _texty(res, rec, k):
    return [r for r in res["paras"][rec["n"] + 1:] if r["kind"] not in ("empty", "object")][:k]


@pytest.fixture(scope="module")
def P(rnd):
    """그림 2·3 문단(글로 찾음) → 레코드(tests/test_headings.py 의 P 와 같다)."""
    out = {}
    out["h1"] = _find(rnd, "1. 연구개발과제의 필요성", kind="marker")
    out["h11"] = _find(rnd, "1-1. 개발 대상 기술", kind="marker", start=out["h1"]["n"])
    out["sq"] = _find(rnd, "□ 연구개발기술(제품)의 정의 및 범위", start=out["h11"]["n"])
    out["o1"], out["dash"], out["dot"], out["o2"] = _texty(rnd, out["sq"], 4)
    out["stage"] = _find(rnd, "[1단계]")
    out["sec22"] = [r for r in rnd["paras"][:out["stage"]["n"]] if r["area"] == "body" and r["kind"] == "marker" and r["letter"].strip() == "2-2."][-1]
    out["year"] = _find(rnd, "(1) 1차년도", start=out["stage"]["n"])
    out["goal"] = _find(rnd, "① 개발 목표", start=out["year"]["n"])
    out["lead"] = _find(rnd, "[주관연구개발기관(기관명 기입)]", start=out["goal"]["n"])
    out["joint"] = _find(rnd, "[공동연구개발기관1(기관명 기입)]", start=out["goal"]["n"])
    out["joint_o"] = _texty(rnd, out["joint"], 1)[0]
    out["foreign"] = _find(rnd, "[국외기관(기관명 기입)]", start=out["goal"]["n"])
    out["content"] = _find(rnd, "② 개발 내용 및 범위", start=out["goal"]["n"])
    return out


def _no_llm(jobs):
    pytest.fail("LLM 을 부르면 안 됨")


def _res(data=None, error=None, cost=0.0):
    return {"data": data, "backend": "fake", "model": "fake", "ms": 0, "costUsd": cost, "error": error}


def _data(job):
    return json.loads(job["content"].rsplit("## 자료(JSON)\n", 1)[1])


def _review_agree(job, data):
    """가짜 D(재검토) 기본 답 — 1차 판정에 모두 동의."""
    return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "verdict": "agree", "same": p["first"]["same"], "reason": "가짜 재검토 동의"}
                          for p in data["pairs"]], "summary": ""})


def fake_ask(**handlers):
    """job["what"] 의 「#」 앞 이름마다 handler(job, 자료) → 결과. heading_review 를 안 주면 1차 판정에 모두 동의하는 기본 답."""
    seen = []
    handlers.setdefault("heading_review", _review_agree)

    def ask(jobs):
        out = []
        for job in jobs:
            seen.append(job["what"])
            out.append(handlers[job["what"].split("#", 1)[0]](job, _data(job)))
        return out
    ask.seen = seen
    return ask


def _a_answer(rnd, P):
    """가짜 A(2026-11-09 꼴) — 유형마다 role·parents·basis, 주 사슬 1. › 1-1. › (1) › o › - › ⋅. 1-1. 아래 □ 는 가지, 구분 라벨(단계·기관)은 제 템플릿의 뿌리."""
    nodes = HG.candidates(rnd)
    types = HG.type_table(nodes)
    K = HG.type_keys(types, HG.fallback_roles(types))
    T = {nd["id"]: nd["type"] for nd in nodes}
    t = lambda k: T[P[k]["id"]]  # noqa: E731
    key = lambda k: K[t(k)]  # noqa: E731
    par = {"h1": ["root"], "h11": [key("h1")], "sq": [key("h11"), key("year")], "year": [key("h11"), "[단계]"], "goal": [key("year")],
           "o1": [key("sq"), key("year"), "[기관]"], "dash": [key("o1")], "dot": [key("dash")]}
    types_ = [{"type": t(k), "role": "heading", "parents": p, "variantOf": "", "basis": "차년도" if k == "year" else "", "reason": ""} for k, p in par.items()]
    types_ += [{"type": t("stage"), "role": "label", "parents": [], "variantOf": "", "basis": "단계", "reason": ""}]
    types_ += [{"type": t(k), "role": "label", "parents": [], "variantOf": "", "basis": "기관", "reason": ""} for k in ("lead", "joint", "foreign")]
    return {"types": types_, "mainChain": [key(k) for k in ("h1", "h11", "year", "o1", "dash", "dot")], "summary": "가짜 A"}, T


def _ask_ab(A, b=None):
    """가짜 A(고정 답) · B(handler 또는 변경 없음) · C(쌍 없음)."""
    return fake_ask(heading_types=lambda job, d: _res(A), heading_section=b or (lambda job, d: _res({"changes": [], "summary": ""})),
                    heading_formats=lambda job, d: _res({"pairs": [], "summary": ""}))


def _rec(i, text, letter, shape, family, fmt, lead=0, *, area="body", path=None, cell=None):
    """1단계 레코드(필요한 칸만) — marker 문단."""
    return {"id": f"p{i}", "n": i, "area": area, "path": path or [], "table": None, "cell": cell, "kind": "marker", "family": family, "shape": shape,
            "letter": " " * lead + letter, "rest": text[len(letter):].strip(), "text": " " * lead + text, "leadSpaces": lead, "fmt": fmt,
            "char": {"text": {"sizePt": 10.0, "bold": False}}, "blank": False,
            "spans": [{"i": 0, "line": 0, "kind": "marker", "family": family, "letter": letter}]}


# ---- S2-boxflow: 여러 칸 표 칸 안 1칸 상자 = 그 칸의 흐름 -------------------------------------------------------------

def test_box_inside_table_cell_takes_cell_flow(rnd):
    """여러 칸 표 칸 안 1칸 상자는 투명 — 그 칸의 흐름. 본문 스택에 올라가 본문 헤딩(「6-2.」)의 부모를 빼앗지 않고, 유형·템플릿도 칸(scope cell)."""
    box1 = _find(rnd, "1. 위험성 추정", area="box")
    box2 = _find(rnd, "2. 위험성 결정", area="box", start=box1["n"])
    assert any(c["t"] == "tbl" and c["cells"] > 1 for c in box1["path"])  # 3칸 표 칸 안의 1칸 상자
    h6 = [r for r in rnd["paras"][:box1["n"]] if r["area"] == "body" and r["kind"] == "marker" and r["letter"].strip() == "6."][-1]
    h62 = _find(rnd, "6-2.", kind="marker", start=box2["n"])
    g = HG.build(rnd, use_llm=False, ask=_no_llm)
    N = {n["id"]: n for n in g["nodes"]}
    cells = {c["id"] for c in g["containers"] if c["kind"] == "cell"}
    for r in (box1, box2):
        n = N[r["id"]]
        assert n["flow"].startswith("cell:") and n["template"].startswith("cell:"), n
        assert n["parent"] in cells or N[n["parent"]]["flow"] == n["flow"], n  # 부모는 칸 그릇이거나 같은 칸의 노드 — 본문이 아님
    assert N[h62["id"]]["parent"] == h6["id"]  # 6-2. 보안조치 이행계획 은 6. 아래
    ty = {t["type"]: t for t in g["types"]}
    assert ty[N[box1["id"]]["type"]]["area"] == "cell"
    # 본문 상자는 그대로 본문, 상자 안 상자도 바깥 칸
    box = [{"t": "tbl", "id": "t1", "cells": 1}, {"t": "cell", "id": "c1"}]
    multi = [{"t": "tbl", "id": "t0", "cells": 3}, {"t": "cell", "id": "c0"}]
    assert HG._flow({"area": "box", "path": box, "cell": "c1"}) == "body"
    assert HG._flow({"area": "box", "path": multi + box + [{"t": "tbl", "id": "t2", "cells": 1}, {"t": "cell", "id": "c2"}], "cell": "c2"}) == "cell:c0"


def test_box_inside_table_cell_not_sent_to_b(rnd, P):
    """spec ② §6 「칸 안 노드는 B 에 안 보낸다」 — 칸 안 1칸 상자 노드도 B 구간·A 스케치에 없다."""
    box_ids = {r["id"] for r in rnd["paras"] if r["area"] == "box" and any(c["t"] == "tbl" and c.get("cells", 0) > 1 for c in r["path"])}
    A, _ = _a_answer(rnd, P)
    sent = []

    def b(job, d):
        sent.extend(r[0] for r in d["nodes"])
        return _res({"changes": [], "summary": ""})
    g = HG.build(rnd, use_llm=True, ask=_ask_ab(A, b))
    nodes = {n["id"]: n for n in g["nodes"]}
    assert len(box_ids & set(nodes)) >= 10  # 표본에 칸 안 상자 후보가 있다
    assert sent and not (box_ids & set(sent))
    assert all(nodes[i]["flow"].startswith("cell:") for i in box_ids & set(nodes))  # 스케치(본문 흐름)에도 없다


# ---- S2-labelclose: 본문 루트 라벨이 꼴만 같은 다른 유형 라벨을 만나도 열린 개요를 지우지 않는다 ---------------------------

def _with_top_label(rnd, text="[별지 제1호서식]"):
    """본문 맨 앞(어떤 헤딩보다 앞)에 앞 공백 0 「[…]」 라벨 문단 하나를 끼운 1단계 결과(복사본 — 모듈 표본은 그대로)."""
    res = copy.deepcopy(rnd)
    paras = res["paras"]
    src = next(r for r in paras if r["area"] == "body" and r["text"].strip().startswith("[1단계]"))
    at = next(i for i, r in enumerate(paras) if r["area"] == "body")
    rec = copy.deepcopy(src)
    rec.update(id="pTopLabel", n=paras[at]["n"], text=text, letter=text, rest="")
    rec["spans"] = [dict(s, letter=text) for s in rec["spans"] if s["i"] == 0]
    paras.insert(at, rec)
    return res


def test_root_label_does_not_wipe_outline(rnd, P):
    """본문 맨 앞 라벨(닻 = 루트, 앞 공백 0)은 꼴만 같은 다른 라벨(「[1단계]」)과 같은 묶음이 아니다 — 열린 개요(2-2.)를 루트까지 지우지 않는다.
    라벨은 제 템플릿의 뿌리: 「[1단계]」 아래 「(1) 1차년도」 의 부모는 라벨."""
    g = HG.build(_with_top_label(rnd), use_llm=False, ask=_no_llm)
    N = {n["id"]: n for n in g["nodes"]}
    par = lambda k: N[P[k]["id"]]["parent"]  # noqa: E731
    assert N["pTopLabel"]["role"] == "subtitle" and N["pTopLabel"]["key"] == "[…]" and N["pTopLabel"]["parent"] == "root"  # 구분 기준 값이 아닌 괄호 글 = 괄호 소제목(§13)
    assert par("stage") == P["sec22"]["id"]
    assert par("year") == P["stage"]["id"] and N[P["year"]["id"]]["division"] == P["stage"]["id"]
    assert par("goal") == P["year"]["id"] and par("joint") == P["goal"]["id"]
    # 칸 안 라벨 묶음(꼴 같은 다른 유형 「[최종목표]」「[N차년도 목표]」)은 그대로 칸 뿌리까지 닫힌다
    labs = [n for n in g["nodes"] if n["kind"] == "label" and n["flow"] == "cell:c682"]
    assert len(labs) == 4 and all(n["parent"] == "cell:c682" for n in labs)


# ---- S2-tplcheck: B 의 template ""·level 0 = 초안 값, 모르는 템플릿·범위 밖 레벨은 버림 ----------------------------------

def _g3():
    graph = {i: {"id": i, "parent": p, "role": "heading", "key": k, "division": None} for i, p, k in (("a0", "root", "N."), ("n1", "a0", "□"), ("n2", "n1", "o"))}
    return graph, {"body:N.›□›o"}


def test_apply_changes_template_level_keep_or_reject():
    # 부모만 바꾸는 변경에 B 가 채운 ""·0 — 슬롯 예외 없음(템플릿·레벨은 스크립트가 부모 관계에서 셈)
    graph, anchors = _g3()
    applied, rejected = HG.apply_changes([{"id": "n2", "parent": "a0", "template": "", "level": 0, "role": "heading", "reason": "부모만"}],
                                         ["n1", "n2"], ["a0"], graph, anchors)
    assert rejected == [] and [a["id"] for a in applied] == ["n2"]
    assert graph["n2"]["parent"] == "a0" and graph["n2"].get("slot") is None and applied[0]["after"]["slot"] is None
    # 모르는 템플릿 · 레벨 0 이하 · 템플릿 없는 레벨 — 버리고 기록, 그래프는 그대로
    for ch, why in (({"template": "nope", "level": 2}, "모르는 템플릿"), ({"template": "body:N.›□›o", "level": -1}, "범위 밖"),
                    ({"template": "body:N.›□›o", "level": 0}, "범위 밖"), ({"template": "", "level": 7}, "모르는 템플릿")):
        graph, anchors = _g3()
        applied, rejected = HG.apply_changes([{"id": "n2", "parent": "n1", "role": "heading", "reason": "", **ch}],
                                             ["n1", "n2"], ["a0"], graph, anchors)
        assert applied == [] and len(rejected) == 1 and why in rejected[0]["why"], (ch, rejected)
        assert graph["n2"]["parent"] == "n1" and graph["n2"].get("slot") is None
    # 슬롯 예외(아는 앵커 + 레벨 ≥ 1)는 그대로 적힌다 — 배정이 범위를 본다. 구분 라벨로 내리면(basis = 구분 기준) 슬롯 없음·레터 키는 「[기준]」
    graph, anchors = _g3()
    applied, rejected = HG.apply_changes([{"id": "n2", "parent": "a0", "template": "body:N.›□›o", "level": 3, "role": "heading"},
                                          {"id": "n1", "parent": "", "template": "", "level": 0, "role": "label", "basis": "기관"}], ["n1", "n2"], ["a0"], graph, anchors)
    assert rejected == [] and len(applied) == 2
    assert graph["n2"]["slot"] == {"template": "body:N.›□›o", "level": 3}
    assert (graph["n1"]["role"], graph["n1"].get("slot"), graph["n1"]["key"]) == ("label", None, "[기관]")
    assert applied[1]["asked"] == {"role": "label", "basis": "기관", "template": "", "level": 0}  # B 가 적은 그대로 — 다시 셈(replay)의 입력
    # basis 가 없거나 구분 기준 목록 밖(지어낸 이름)이면 구분 라벨이 되지 않는다 — 역할·키 그대로(§13: 구분 라벨 = 구분 기준 값만), 괄호 줄이 아닌 줄은 소제목도 못 된다
    for ch in ({"role": "label"}, {"role": "label", "basis": "측면"}, {"role": "subtitle"}):
        graph, anchors = _g3()
        HG.apply_changes([{"id": "n1", "parent": "", "template": "", "level": 0, **ch}], ["n1", "n2"], ["a0"], graph, anchors)
        assert (graph["n1"]["role"], graph["n1"]["key"]) == ("heading", "□"), ch
    # 템플릿 없는 잎 제목을 heading 으로 — 이제 된다(레터 키 「제목」, 템플릿은 스크립트가 셈)
    graph, anchors = _g3()
    graph["t1"] = {"id": "t1", "parent": "n1", "role": "title", "key": None, "division": None}
    applied, rejected = HG.apply_changes([{"id": "t1", "parent": "", "template": "", "level": 0, "role": "heading"}], ["n1", "n2", "t1"], ["a0"], graph, anchors)
    assert rejected == [] and (graph["t1"]["role"], graph["t1"]["key"]) == ("heading", "제목")


def test_build_parent_only_change_keeps_template(rnd, P):
    """B 가 부모만 바꾸며 template ""·level 0 을 채우면 스크립트가 새 부모 아래에서 템플릿·레벨을 다시 셈한다(o 아래 o = 「o」 가지 L1). 계약도 「초안 값을 그대로」 를 말한다."""
    A, _ = _a_answer(rnd, P)
    o1, o2 = P["o1"]["id"], P["o2"]["id"]

    def b(job, d):
        if o2 in [r[0] for r in d["nodes"]]:
            return _res({"changes": [{"id": o2, "parent": o1, "template": "", "level": 0, "role": "heading", "reason": "부모만"}],
                         "summary": ""})
        return _res({"changes": [], "summary": ""})
    g = HG.build(rnd, use_llm=True, ask=_ask_ab(A, b))
    n = next(x for x in g["nodes"] if x["id"] == o2)
    assert n["changed"] and n["parent"] == o1
    assert n["template"].startswith("body:o") and n["level"] == 1 and n["tplNo"] not in (1, next(x for x in g["nodes"] if x["id"] == o1)["tplNo"]), n
    assert "초안 값을 그대로" in HL.SECTION_CONTRACT


# ---- S2-parentrole: 헤딩 아님은 투명 · 라벨 부모는 라벨의 부모 + 구분 ------------------------------------------------------

def _sub_graph():
    """① › □ › o,o 인스턴스 4개 — 확정 트리(B 뒤). 뿌리 ① 이 본문 뿌리 아래 가장 많으니 주 사슬 「① › □ › o」."""
    fam = {"T1": ("circled", "①"), "T2": ("square", "□"), "T3": ("latin-o", "o")}
    keys = {"T1": "①", "T2": "□", "T3": "o"}
    rows = []
    for k in range(4):
        rows += [(f"r{k}", "T1", "root"), (f"s{k}", "T2", f"r{k}"), (f"o{k}a", "T3", f"s{k}"), (f"o{k}b", "T3", f"s{k}")]
    nodes = [{"id": i, "para": i, "n": n, "type": t, "fmt": "S1", "text": i, "kind": "marker", "family": fam[t][0], "shape": fam[t][1],
              "letter": fam[t][1], "outline": None, "flow": "body", "lead": 0} for n, (i, t, _) in enumerate(rows)]
    graph = {i: {"id": i, "para": i, "type": t, "parent": p, "role": "heading", "key": keys[t], "division": None} for i, t, p in rows}
    types = {t: {"shape": fam[t][1]} for t in fam}
    return nodes, graph, keys, types


def _fin(nodes, graph, keys, types):
    asg = HG.assign_templates(nodes, graph, keys)
    return HG.finish(nodes, graph, asg, types, {}, {})


def test_b_demote_with_children_keeps_subtree_in_instance():
    """B 가 자식 있는 「□」 를 not_heading 으로 내리면 헤딩 아님은 투명 — 그 아래 o,o 는 「①」 에 붙는다. 2026-11-17 부터 그 o 는 가지 「o」 가 아니라 주 사슬 「① › □ › o」 의 L3
    (레벨 건너뜀 = 잇닿은 사슬 — spec_헤딩_추출 ② §6, 사용자 답 「T1 에 넣기」)이고 ① 인스턴스의 멤버, ① 인스턴스는 편차(L2 빠짐). 내려간 뿌리 「①」 는 인스턴스가 아니다."""
    nodes, graph, keys, types = _sub_graph()
    applied, rejected = HG.apply_changes([{"id": "s0", "role": "not_heading", "reason": "제목 아님"}], ["r0", "s0", "o0a", "o0b"], [], graph, set())
    assert [a["id"] for a in applied] == ["s0"] and not rejected and graph["s0"]["key"] is None
    fin = _fin(nodes, graph, keys, types)
    ins = {x["root"]: x for x in fin["instances"]}
    assert ins["r0"]["members"] == ["o0a", "o0b"] and ins["r0"]["deviates"] and ins["r0"]["missing"] == [2]
    assert ins["r0"]["childInstances"] == [] and "o0a" not in ins and [t["anchor"] for t in fin["templates"]] == ["body:①›□›o"]
    assert ins["r1"]["members"] == ["s1", "o1a", "o1b"] and not ins["r1"]["deviates"]
    assert graph["o0a"]["parent"] == "s0"  # 그래프 부모는 그대로(화면은 흐린 「□」 아래)
    # 내려간 뿌리 「①」 는 인스턴스를 만들지 않는다 — 그 아래 □ 는 본문 뿌리에 매달린 **주 사슬의 레터**라 가지 「□ › o」 가 아니라 주 사슬 L2 다
    # (윗 레벨이 빠진 인스턴스 — spec ② §6 「잇닿은 사슬」, 2026-11-17 사용자 "레터가 다르거나 하지 않고 늘어나면 같은 템플릿으로": 전에는 「□ › o」 가지 템플릿)
    nodes, graph, keys, types = _sub_graph()
    applied, rejected = HG.apply_changes([{"id": "r2", "role": "not_heading", "reason": "뿌리 아님"}], ["r2", "s2", "o2a", "o2b"], [], graph, set())
    assert [a["id"] for a in applied] == ["r2"] and not rejected
    fin = _fin(nodes, graph, keys, types)
    main = next(t for t in fin["templates"] if t["kind"] == "main")
    assert main["chain"] == ["①", "□", "o"] and [x["root"] for x in fin["instances"] if x["template"] == main["id"]] == ["r0", "r1", "s2", "r3"]
    s2 = next(x for x in fin["instances"] if x["root"] == "s2")
    assert s2["anchor"] == "body:①›□›o" and s2["missing"] == [1] and s2["members"] == ["o2a", "o2b"] and [t["anchor"] for t in fin["templates"]] == ["body:①›□›o"]


def test_b_label_parent_kept_and_non_heading_parent_rejected():
    """B 가 부모로 구분 라벨을 주면 라벨이 그대로 부모(라벨은 제 템플릿의 뿌리 — spec ② §0 가지 규칙 ②). 헤딩 아님·안내 부모는 버림."""
    nodes, graph, keys, types = _sub_graph()
    graph["lab"] = {"id": "lab", "para": "lab", "type": "T9", "parent": "s0", "role": "label", "key": "[기관]", "division": None}
    applied, rejected = HG.apply_changes([{"id": "o0b", "parent": "lab"}], ["r0", "s0", "lab", "o0a", "o0b"], [], graph, set())
    assert not rejected and graph["o0b"]["parent"] == "lab" and HG._division_of("o0b", graph) == "lab"
    graph["s1"]["role"] = "not_heading"
    graph["o1a"]["role"] = "note"
    applied, rejected = HG.apply_changes([{"id": "o1b", "parent": "s1"}, {"id": "o1b", "parent": "o1a"}], ["r1", "s1", "o1a", "o1b"], [], graph, set())
    assert applied == [] and [r["id"] for r in rejected] == ["o1b", "o1b"] and all("헤딩 아님" in r["why"] for r in rejected)
    assert graph["o1b"]["parent"] == "s1"


# ---- S2-cslot: C 의 답은 슬롯마다 --------------------------------------------------------------------------------------

def test_c_answers_kept_per_slot():
    """(S2 대표, S9) 쌍이 L2 · L3 두 슬롯에 — C 가 L2 같음 · L3 다름이면 조정도 슬롯마다 따로."""
    paras = []
    for i in range(1, 3):
        paras.append(_rec(len(paras), f"{i}. 큰 제목", f"{i}.", "N.", "n.dot", "S1", 0))
        for j, g in enumerate("가나다"):
            paras.append(_rec(len(paras), f"{g}. 중간 제목", f"{g}.", "가.", "k.dot", "S2" if j else "S9", 1))
            for k in range(1, 4):
                paras.append(_rec(len(paras), f"({k}) 작은 제목", f"({k})", "(N)", "n.paren", "S2" if k < 3 else "S9", 2))
    stage1 = {"paras": paras, "labels": {"S1": {"name": "큰"}, "S2": {"name": "보통"}, "S9": {"name": "빨강 안내"}}}
    types = HG.type_table(HG.candidates(stage1))
    by_shape = {t["shape"]: tid for tid, t in types.items()}
    par = {"N.": ["root"], "가.": ["N."], "(N)": ["가."]}
    A = {"types": [{"type": by_shape[s], "role": "heading", "parents": p, "variantOf": "", "basis": "", "reason": ""} for s, p in par.items()],
         "mainChain": ["N.", "가.", "(N)"], "summary": ""}
    M = "body:N.›가.›(N)"
    asked = []

    def c(job, d):
        asked.extend((p["slot"], p["a"], p["b"]) for p in d["pairs"])
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": p["slot"] == f"{M}|L2", "reason": "C " + p["slot"]}
                               for p in d["pairs"]], "summary": ""})
    ask = fake_ask(heading_types=lambda job, d: _res(A), heading_section=lambda job, d: _res({"changes": [], "summary": ""}), heading_formats=c)
    g = HG.build(stage1, use_llm=True, ask=ask)
    assert not g["llm"]["fallback"]
    assert sorted(asked) == [(f"{M}|L2", "S2", "S9"), (f"{M}|L3", "S2", "S9")]
    dec = {(a["level"], a["decision"], a["reason"]) for a in g["adjustments"] if a["from"] == "S9"}
    assert dec == {(2, "adjust", f"C {M}|L2"), (3, "keep", f"C {M}|L3")}, dec
    assert g["counts"]["adjust"] == 2


# ---- S2-undecided: 미판정 노드는 슬롯 대표 서식의 근거가 아니다 ------------------------------------------------------------

def test_undecided_not_basis_for_slot_format(monkeypatch):
    """미판정(B 실패 구간) 노드는 슬롯 대표 서식·조정·C 쌍의 근거로 안 씀(spec ② §6 검증·조립). 두 최상위 구간이 합쳐지지 않게 SECTION_MAX 를 줄인다."""
    monkeypatch.setattr(HG, "SECTION_MAX", 4)
    rows = [("1.", "첫 장", "S0", "decimal", "N."),
            ("□", "가1", "S1", "square", "□"), ("□", "가2", "S1", "square", "□"), ("□", "가3", "S3", "square", "□"),
            ("2.", "둘째 장", "S0", "decimal", "N."),  # 이 구간 B 실패
            ("□", "나1", "S2", "square", "□"), ("□", "나2", "S2", "square", "□"), ("□", "나3", "S2", "square", "□")]
    st1 = {"paras": [_rec(i, f"{lt} {rest}", lt, shape, fam, fmt) for i, (lt, rest, fmt, fam, shape) in enumerate(rows)], "labels": {}}
    asked = []

    def a(job, d):
        tid = {t["shape"]: t["type"] for t in d["types"]}
        return _res({"types": [{"type": tid["N."], "role": "heading", "parents": ["root"], "variantOf": "", "basis": "", "reason": ""},
                               {"type": tid["□"], "role": "heading", "parents": ["N."], "variantOf": "", "basis": "", "reason": ""}],
                     "mainChain": ["N.", "□"], "summary": ""})

    def b(job, d):
        return _res(None, "가짜 B 실패") if "p4" in [r[0] for r in d["nodes"]] else _res({"changes": [], "summary": ""})

    def c(job, d):
        asked.extend((p["a"], p["b"]) for p in d["pairs"])
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": True, "reason": "C"} for p in d["pairs"]], "summary": ""})
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=a, heading_section=b, heading_formats=c))
    N = {n["id"]: n for n in g["nodes"]}
    assert g["llm"]["failedSections"] == 1 and {i for i, n in N.items() if n["undecided"]} == {"p4", "p5", "p6", "p7"}
    slot = next(s for s in g["templates"][0]["slots"] if s["level"] == 2)
    assert slot["format"] == "S1" and slot["formats"]["S2"] == 3 and slot["letter"] == "□" and slot["rep"] == "p1"
    assert asked and all(x == "S1" for x, _ in asked)
    adj = {a["id"]: a for a in g["adjustments"]}
    assert "p1" not in adj and "p2" not in adj
    assert adj["p3"]["to"] == "S1" and adj["p3"]["decision"] == "adjust"


# ---- S2-sections: 작은 최상위 구간은 이어서 SECTION_MAX 안에서 합친다 ----------------------------------------------------

def _sec_graph(depths):
    nodes = [{"id": f"n{i}", "flow": "body"} for i in range(len(depths))]
    graph = {f"n{i}": {"role": "heading", "depth": d} for i, d in enumerate(depths)}
    return nodes, graph


def test_sections_pack_small_top_level():
    """최상위 노드가 많고 작으면 합친다 — 「□」 150개 × 2노드 = 300 노드 → 3 구간. 최상위 경계에서만 자르고 SECTION_MAX 는 안 넘는다."""
    nodes, graph = _sec_graph([1.0, 2.0] * 150)
    secs = HG.sections(nodes, graph, {})
    assert [n for s in secs for n in s] == [n["id"] for n in nodes]
    assert all(len(s) <= HG.SECTION_MAX for s in secs)
    assert all(graph[s[0]]["depth"] == 1.0 for s in secs)
    assert len(secs) == -(-len(nodes) // HG.SECTION_MAX)
    # 큰 최상위 구간(깊이 2 에서 자름)과 작은 구간이 섞여도 — 큰 것은 따로, 앞뒤 작은 것끼리만 합침
    depths = [1.0, 2.0] * 3 + [1.0] + [2.0 if i % 50 == 0 else 3.0 for i in range(1, 200)] + [1.0, 2.0] * 3
    nodes, graph = _sec_graph(depths)
    secs = HG.sections(nodes, graph, {})
    assert [n for s in secs for n in s] == [n["id"] for n in nodes]
    assert all(len(s) <= HG.SECTION_MAX for s in secs)
    assert len(secs[0]) == 6 and len(secs[-1]) == 6 and graph[secs[1][0]]["depth"] == 1.0


# ---- S2-division: B 의 division 도 B 가 본 라벨, 문서 순 앞 ------------------------------------------------------------


def test_b_parent_to_later_label_is_rejected(rnd, P):
    """B 가 「(1) 1차년도」 의 부모를 같은 구간 뒤쪽 「[공동연구개발기관1]」 로 바꾸면 「부모가 문서 순으로 뒤」 로 버린다 — 초안 부모(「[1단계]」 라벨)·① 인스턴스 그대로."""
    A, _ = _a_answer(rnd, P)
    ids = {k: P[k]["id"] for k in P}
    fired = []

    def b(job, d):
        rows = {r[0]: r for r in d["nodes"]}
        if ids["year"] in rows and ids["joint"] in rows:
            fired.append(1)
            return _res({"changes": [{"id": ids["year"], "parent": ids["joint"], "template": "", "level": 0, "role": "heading", "reason": "가짜 — 뒤 라벨"}],
                         "summary": ""})
        return _res({"changes": [], "summary": ""})
    g = HG.build(rnd, use_llm=True, ask=_ask_ab(A, b))
    assert fired and [r["why"] for r in g["rejected"]] == ["부모가 문서 순으로 뒤"]
    N = {n["id"]: n for n in g["nodes"]}
    assert N[ids["year"]]["parent"] == ids["stage"] and N[ids["year"]]["division"] == ids["stage"] and not N[ids["year"]]["changed"]
    si = next(i for i in g["instances"] if i["root"] == ids["stage"])  # 「[1단계]」 라벨 템플릿 인스턴스 — (1)·①·② 가 멤버
    assert {ids["year"], ids["goal"], ids["content"]} <= set(si["members"])


# ---- S2-flowkey(2단계 쪽): 그릇마다 흐름 — 1단계 사슬의 key, 없으면 옛 꼴 ---------------------------------------------------

def test_flow_uses_container_key():
    """id 없는 칸·글상자는 1단계 사슬 key 로 그릇마다 흐름 — 다른 그릇 노드가 서로의 부모가 되지 않는다. key 없는 옛 결과는 옛 흐름 이름."""
    shape = lambda k: {"t": "shape", "kind": "rect", "key": k}  # noqa: E731
    tbl = {"t": "tbl", "id": None, "rows": 1, "cols": 2, "cells": 2, "key": 4}
    paras = [_rec(0, "1. 본문 제목", "1.", "N.", "decimal", "S1"),
             _rec(1, "1. 상자A 제목", "1.", "N.", "decimal", "S1", area="shape", path=[shape(1)]),
             _rec(2, "가. 상자A 하위", "가.", "가.", "hangul-dot", "S1", area="shape", path=[shape(1)]),
             _rec(3, "□ 상자B 항목", "□", "□", "square", "S1", area="shape", path=[shape(2)]),
             _rec(4, "□ 칸1 항목", "□", "□", "square", "S1", area="cell", path=[shape(3), tbl, {"t": "cell", "id": None, "row": 0, "col": 0, "key": 5}]),
             _rec(5, "o 칸2 항목", "o", "o", "latin-o", "S1", area="cell", path=[shape(3), tbl, {"t": "cell", "id": None, "row": 0, "col": 1, "key": 6}])]
    g = HG.build({"paras": paras, "labels": {}}, use_llm=False, ask=_no_llm)
    N = {n["id"]: n for n in g["nodes"]}
    assert [N[f"p{i}"]["flow"] for i in range(6)] == ["body", "shape:1", "shape:1", "shape:2", "cell:k5", "cell:k6"]
    assert N["p2"]["parent"] == "p1"  # 같은 상자 안은 그대로 이어짐
    assert N["p3"]["parent"] not in N and N["p5"]["parent"] not in N  # 다른 그릇 노드 아래로 안 감
    assert N["p5"]["parent"] == "cell:k6"
    # key 없는 옛 1단계 결과 — 옛 흐름 이름
    assert HG._flow({"area": "shape", "path": [{"t": "shape", "kind": "rect"}], "cell": None}) == 'shape:{"kind": "rect", "t": "shape"}'
    assert HG._flow({"area": "cell", "path": [{"t": "tbl", "id": None, "cells": 2}, {"t": "cell", "id": None}], "cell": None}) == "cell:None"
    assert HG._flow({"area": "cell", "path": [{"t": "tbl", "id": "t1", "cells": 2}, {"t": "cell", "id": "c9", "key": 3}], "cell": "c9"}) == "cell:c9"


# ---- S1-plainbroad: plain 규칙도 「너무 넓음」 검사 ----------------------------------------------------------------------

def _item(group, decision, pattern="", kind="", **kw):
    return {"group": group, "decision": decision, "name": kw.get("name", kind), "kind": kind, "family": kw.get("family", ""),
            "pattern": pattern, "scope": kw.get("scope", "prefix" if pattern else ""), "first": kw.get("first", False),
            "positives": kw.get("positives", []), "negatives": kw.get("negatives", []), "globalHint": kw.get("globalHint", False),
            "reason": kw.get("reason", "가짜")}


def test_check_proposal_broad_plain_rule_rejected(rnd):
    """kind plain 규칙도 묶음 밖 보통 글을 max(3, 보통 글 1%) 넘게 가져가면 「너무 넓음」(spec ② §3 빼앗음 검사). 좁은 plain 규칙은 통과."""
    g = next(g for g in rnd["review"]["unmatched"] if g["key"] == "u:(글)")
    item = _item(g["key"], "rule", r"\S.*", "plain", family="any", positives=g["ids"][:2])
    rule, verdict = HL.check_proposal(item, {**g, "type": "unmatched"}, rnd, copy.deepcopy(EMPTY), "rnd")
    assert rule is None and verdict["verdict"] == "rejected" and "너무 넓음" in verdict["why"], verdict
    ok = _item(g["key"], "rule", r"\([가-힣]+\)", "plain", family="paren-word", positives=g["ids"][:2])
    rule, verdict = HL.check_proposal(ok, {**g, "type": "unmatched"}, rnd, copy.deepcopy(EMPTY), "rnd")
    assert rule is not None and verdict["verdict"] == "saved", verdict


# ---- S3-provenance(LLM 쪽): 실행 시작 때 고정한 지침(pinned)으로 프롬프트 ---------------------------------------------------

def test_build_uses_pinned_guides(rnd, P):
    """A 호출 중 사용자가 지침을 저장해도 B·C 프롬프트와 graph["guides"] 는 시작 때 고정한 지침(pinned)."""
    pinned = G.snapshot()
    A, _ = _a_answer(rnd, P)
    A["same"] = []
    prompts = []

    def a(job, d):
        prompts.append(job["content"])
        G.save("graph", "# 실행 중 고친 그래프 지침\n", reason="mid-run")
        return _res(A)

    def b(job, d):
        prompts.append(job["content"])
        return _res({"changes": [], "summary": ""})

    def c(job, d):
        prompts.append(job["content"])
        return _res({"pairs": [], "summary": ""})
    g = HG.build(rnd, use_llm=True, ask=fake_ask(heading_types=a, heading_section=b, heading_formats=c), pinned=pinned)
    assert G.get("graph")["sha1"] != pinned["graph"]["sha1"]
    assert g["guides"] == {n: pinned[n]["sha1"] for n in ("graph", "templates", "tolerance")}
    assert len(prompts) >= 3 and not any("실행 중 고친" in p for p in prompts)
    assert all(f"## 지침 — {G.TITLES['templates']} (templates)" in p for p in prompts)


def test_propose_rules_uses_pinned_guides(rnd):
    """propose_rules(pinned=…) — 시작 뒤 저장된 규칙 지침이 아니라 고정한 글로 묻고, 보고서 guides 도 그 sha1."""
    pinned = G.snapshot()
    G.save("rules", "# 시작 뒤 고친 규칙 지침\n", reason="mid-run")
    prompts = []

    def handle(job, d):
        prompts.append(job["content"])
        return _res({"items": []})
    rep = HL.propose_rules(rnd, doc_key="rnd", ask=fake_ask(heading_rules=handle), save=False, pinned=pinned)
    assert rep["guides"] == {"rules": pinned["rules"]["sha1"]} and pinned["rules"]["sha1"] != G.get("rules")["sha1"]
    assert prompts and all(pinned["rules"]["text"].strip() in p and "시작 뒤 고친" not in p for p in prompts)
    # pinned 없이는 지금 저장소의 글(예전 그대로)
    rep = HL.propose_rules(rnd, doc_key="rnd", ask=fake_ask(heading_rules=handle), save=False)
    assert rep["guides"] == {"rules": G.get("rules")["sha1"]} and "시작 뒤 고친" in prompts[-1]
