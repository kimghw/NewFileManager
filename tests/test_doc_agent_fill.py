"""자리 채우기(type fill — spec_양식작성 ② §5-3): 상자(본문 최상위 1칸 표) 안의 쓸 자리 · 같은 줄 뒤의 값을 **있는 문단에 제자리에서** 채우는 문서 에이전트 행동.
astra 1차 · 2차(artifacts/form_fill_slots_astra_2026-11-24/)의 v1: 붙이기 · 표시만(바꾸기는 버림) · 대상은 서버가 이 턴의 선택에서 셈한 문단 · 근거는 자료만(+ 사람이 정한 답) ·
같은 이름의 자리는 범위가 정해 줄 때만 · 반영의 엇갈림은 덩이마다. LLM 은 부르지 않는다(조정 호출을 가짜로)."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import doc_agent as A
from app import doc_agent_api as API
from app import heading_guides as G
from app import heading_rules as R
from app import server, table_agent
from app import table_fill as TF
from app.hwpx_doc import HwpxDoc

if not any("/agent/turn" in getattr(r, "path", "") for r in server.app.routes):
    server.app.include_router(API.router)

RND = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
BOX = "t956"   # 견본의 본문 최상위 1칸 표 — 그 칸의 글을 아래 줄들로 바꿔 상자를 만든다
BOX_LINES = ["연구개발 목표", "000", "    - ", "", "", "공동(기업명 작성) : ", "", "", "공동(기업명 작성) : ", "", "※ 안내 글", "구분 ( □ 연차 □ 최종 □ 단계 )", "과제명 : "]
MATERIAL = "한국선급은 MVDC 계통 시뮬레이션 모델을 개발한다. 적합성 평가 절차(안) 3건. 과제명은 고전압 직류 차단기 개발이다."


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    for m in (R._MEMORY, G._MEMORY, table_agent._MEMORY, A._MEMORY):
        m.clear()
    server.DOCS.clear()
    yield
    server.DOCS.clear()
    for m in (R._MEMORY, G._MEMORY, table_agent._MEMORY, A._MEMORY):
        m.clear()


@pytest.fixture(scope="module")
def boxed():
    """견본에 상자를 만든 문서의 바이트 — 상자 안: 제목 · 자리표시 글 「000」 + 글머리 줄 · 빈 줄 둘 / 같은 이름의 자리 둘(「공동(기업명 작성) : 」 + 빈 줄) / ※ 안내 / 표시 줄 / 같은 줄 뒤에 값."""
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    d.set_text(d.table_block(BOX)["cells"][0]["id"], "\n".join(BOX_LINES))
    return d.save()


@pytest.fixture
def doc(boxed):
    d = HwpxDoc(boxed)
    d.blocks()
    return d


def _paras(d):
    """상자 안 문단 id — 이름으로: title · ph(「000」) · stub · b1 · b2 · j1(공동 1) · j1a · j1b · j2(공동 2) · j2a · note · check · name."""
    ids = [b["id"] for b in d.table_block(BOX)["cells"][0]["blocks"]]
    assert len(ids) == len(BOX_LINES)
    return dict(zip(("title", "ph", "stub", "b1", "b2", "j1", "j1a", "j1b", "j2", "j2a", "note", "check", "name"), ids))


def _line(d):
    """본문 최상위의 「같은 줄 뒤에 값을 쓰는 줄」 하나(견본의 「  o 추진전략(비전) : 」)의 id."""
    return next(b["id"] for b in d.blocks() if b["type"] == "paragraph" and b["text"] == "  o 추진전략(비전) : ")


def _act(*fills, mode="extract"):
    return {"type": "fill", "after": "", "mode": mode, "style": "", "table": "", "range": "", "paras": [], "item": "", "lines": [], "candidates": [], "picks": [],
            "fills": [{"para": p, "text": t, "source": s} for p, t, s in fills]}


def _ctx(d, sel=None, material=MATERIAL, **more):
    got = A.selection_of(d, sel or {"paras": [], "table": BOX, "range": None, "cursor": BOX}, more.pop("levels", None), more.get("uploaded"))
    fill = got["fill"]
    if (more.get("scope") or {}).get("paras") is not None:
        fill = {k: v for k, v in fill.items() if k in more["scope"]["paras"]}
    return {"rev": 3, "turn": "t1", "sources": A.sources("요청 글 — 비밀 값 9999", got["text"], [{"text": material}]), "sources_mat": A.sources("", "", [{"text": material}]),
            "fill": fill, "box": got["box"], **more}


# ---- 대상 — 서버가 선택에서 셈한다 ----------------------------------------------------------------------------------------------

def test_selection_box_lines_and_targets(doc):
    p = _paras(doc)
    got = A.selection_of(doc, {"paras": [], "table": BOX, "range": None, "cursor": _line(doc)})
    t = got["data"]["table"]
    assert t["box"] is True and t["size"] == "1×1" and "grid" not in t and got["box"] == BOX and got["inner"] == []                      # 상자 — 격자 대신 줄 목록
    assert f"[{p['stub']}] 「    - 」 (쓸 자리 — 글머리 줄)" in t["lines"] and f"[{p['b1']} {p['b2']}] (쓸 자리 — 빈 줄 2)" in t["lines"] and "안내 — 채우지 않음" in t["lines"]
    assert set(got["fill"]) == {p[k] for k in ("stub", "b1", "b2", "j1", "j1a", "j1b", "j2", "j2a", "check", "name")}                    # 제목 · 자리표시 글 · ※ 안내는 대상이 아니다
    assert "slot" not in got["data"]["cursor"]                                                                                           # 상자가 먼저 — 한 턴의 대상은 하나
    assert got["fill"][p["stub"]]["headId"] == p["ph"] and got["fill"][p["stub"]]["headRaw"] == "000" and got["fill"][p["j2a"]]["dup"] == [2, 2] and got["fill"][p["j1"]]["headId"] == p["j1"]
    line = _line(doc)
    one = A.selection_of(doc, {"paras": [], "table": None, "range": None, "cursor": line})
    assert one["data"]["cursor"]["slot"] == "label" and one["data"]["cursor"]["raw"] == "  o 추진전략(비전) : " and list(one["fill"]) == [line] and one["box"] is None
    inside = A.selection_of(doc, {"paras": [], "table": None, "range": None, "cursor": p["name"]})                                       # 상자 안 문단에 커서만 — 본문 최상위 줄이 아니다
    assert inside["fill"] == {} and "slot" not in inside["data"]["cursor"]
    other = A.selection_of(doc, {"paras": [], "table": "t1", "range": None, "cursor": None})                                             # 여러 칸 표 — 전처럼 격자
    assert "grid" in other["data"]["table"] and other["fill"] == {} and other["box"] is None


def test_selection_filled_lines_are_not_targets(doc):
    p, line = _paras(doc), _line(doc)
    orig = {p["name"]: "과제명 : ", p["b1"]: "", line: "  o 추진전략(비전) : "}
    doc.set_text(p["name"], "과제명 : 채운 값")
    doc.set_text(p["b1"], "이미 쓴 줄")
    doc.set_text(line, "  o 추진전략(비전) : 채움")
    got = A.selection_of(doc, {"paras": [], "table": BOX, "range": None, "cursor": None}, None, orig)
    assert p["name"] not in got["fill"] and p["b1"] not in got["fill"] and p["b2"] in got["fill"] and "이미 채움 — 다시 쓰지 않음" in got["data"]["table"]["lines"]
    cur = A.selection_of(doc, {"paras": [], "table": None, "range": None, "cursor": line}, None, orig)
    assert cur["fill"] == {} and "slot" not in cur["data"]["cursor"]                                                                     # 이미 채운 줄 — 다시 쓰는 대상이 아니다


# ---- 줄마다의 검사 ------------------------------------------------------------------------------------------------------------------

def test_fill_append_lines_pass_and_keep_prefix(doc, boxed):
    p = _paras(doc)
    up = {p["name"]: "과제명 : ", p["stub"]: "    - "}   # 글이 있는 쓸 자리(「이름 : 」 · 글머리 줄)는 올린 원본의 그 줄 그대로일 때만
    got = A.proposals(doc, [_act((p["stub"], "    - MVDC 계통 시뮬레이션 모델", "한국선급은 MVDC 계통 시뮬레이션 모델을 개발한다."),
                                 (p["b1"], "적합성 평가 절차(안) 3건", "적합성 평가 절차(안) 3건."),
                                 (p["name"], "과제명 : 고전압 직류 차단기 개발", "과제명은 고전압 직류 차단기 개발이다."))], _ctx(doc, uploaded=up))
    (pr,), v = got["proposals"], got["proposals"][0]["view"]
    assert got["dropped"] == [] and pr["type"] == "fill" and pr["title"] == "자리 채우기 — 3줄" and pr["preselect"] is True and pr["baseRev"] == 3 and pr["warn"] == []
    assert v["box"] == BOX and v["picked"] == [p["stub"], p["b1"]] and v["rejected"] == [] and [ln["mode"] for ln in v["lines"]] == ["append"] * 3   # 같은 줄 뒤의 값은 처음부터 안 고른다(v1)
    assert [(ln["was"], ln["value"], ln["kind"], ln["from"], ln["warn"]) for ln in v["lines"]] == [
        ("    - ", "MVDC 계통 시뮬레이션 모델", "stub", "material", []), ("", "적합성 평가 절차(안) 3건", "blank", "material", []), ("과제명 : ", "고전압 직류 차단기 개발", "label", "material", [A.LABEL_ASK])]
    assert v["lines"][0]["head"] == "000" and v["lines"][0]["nth"] == 1 and "headId" not in v["lines"][0]                                  # 화면에는 머리 글 — 머리의 id · 원문은 op 에만
    assert pr["op"] == {"box": BOX, "lines": [{"para": p["stub"], "text": "    - MVDC 계통 시뮬레이션 모델", "was": "    - ", "head": p["ph"], "headWas": "000", "under": ""},
                                               {"para": p["b1"], "text": "적합성 평가 절차(안) 3건", "was": "", "head": p["ph"], "headWas": "000", "under": ""},
                                               {"para": p["name"], "text": "과제명 : 고전압 직류 차단기 개발", "was": "과제명 : ", "head": p["name"], "headWas": "과제명 : ", "under": ""}]}
    ids = [p["stub"], p["b1"], p["name"]]
    assert pr["target"]["block"] == BOX and pr["target"]["blocks"] == ids and set(pr["target"]["fillLines"]) == set(ids) and pr["target"]["hash"]
    assert [c["status"] for c in pr["checks"]] == ["warn", "pass"] and "op" not in A.card(pr)
    # 낡음 = 줄이 **모두** 달라졌을 때만(덩이마다의 엇갈림은 반영이 가린다)
    assert A.stale(doc, pr) is False
    doc.set_text(p["b1"], "사람이 쓴 줄")
    assert A.stale(doc, pr) is False
    for k in ("stub", "name"):
        doc.set_text(p[k], "바뀜")
    assert A.stale(doc, pr) is True
    # set_text 는 글머리 줄의 첫머리(빈칸 · 글머리)를 그대로 둔다 — 저장하고 다시 열어 견준다
    d2 = HwpxDoc(boxed)
    d2.blocks()
    q = _paras(d2)
    d2.set_text(q["stub"], "    - MVDC 계통 시뮬레이션 모델")
    d3 = HwpxDoc(d2.save())
    d3.blocks()
    texts = [b["text"] for b in d3.table_block(BOX)["cells"][0]["blocks"]]
    assert texts[2] == "    - MVDC 계통 시뮬레이션 모델" and texts[:2] == ["연구개발 목표", "000"] and texts[3:] == BOX_LINES[3:]


def test_fill_rejects_before_the_card(doc):
    p = _paras(doc)
    src = "한국선급은 MVDC 계통 시뮬레이션 모델을 개발한다."
    got = A.proposals(doc, [_act((p["name"], "주제 : 고전압 직류 차단기 개발", src),             # 바꾸기 — 같은 줄 뒤가 아니라 앞 글을 바꿈
                                 (p["ph"], "MVDC 계통 시뮬레이션 모델", src),                     # 자리표시 글(text) — 이번 턴에 보낸 자리가 아니다
                                 (p["title"], "연구개발 목표 MVDC", src),                         # 제목
                                 (p["note"], "※ 안내 글 더함", src),                              # 안내
                                 ("p1", "MVDC 계통 시뮬레이션 모델", src),                        # 상자 밖 문단
                                 (p["j1a"], "MVDC 계통 시뮬레이션 모델", src),                    # 같은 이름의 자리(범위 없음)
                                 (p["stub"], "- MVDC 계통 시뮬레이션 모델", src),                 # 글머리 줄의 첫머리를 버림
                                 (p["b1"], "MVDC 계통\n시뮬레이션 모델", src),                    # 줄 바꿈
                                 (p["b2"], "MVDC 계통 시뮬레이션 모델", src),
                                 (p["b2"], "MVDC 계통 시뮬레이션 모델", src))], _ctx(doc, uploaded={p["name"]: "과제명 : "}))   # 같은 줄 두 번
    (pr,) = got["proposals"]
    why = {x["para"]: x["why"] for x in pr["view"]["rejected"][:-1]}
    assert [ln["para"] for ln in pr["view"]["lines"]] == [p["b2"]] and pr["view"]["rejected"][-1] == {"para": p["b2"], "why": "같은 줄을 두 번 적었습니다", "text": "MVDC 계통 시뮬레이션 모델"}
    assert why[p["name"]] == A.NO_REPLACE and why[p["ph"]] == why[p["title"]] == why[p["note"]] == why["p1"] == "이번 턴에 보낸 자리가 아닙니다"
    assert why[p["j1a"]].startswith("같은 이름의 자리가 2곳") and why[p["stub"]] == "글머리 줄은 그 첫머리(빈칸 · 글머리) 뒤에 씁니다" and why[p["b1"]] == "한 줄(문단 하나)에는 줄 바꿈을 넣지 않습니다"
    none = A.proposals(doc, [_act((p["ph"], "목표", src), (p["j1"], "공동(한국선급) : 목표", src))], _ctx(doc))                              # 남는 줄이 없으면 행동째 버린다
    assert none["proposals"] == [] and none["dropped"][0]["type"] == "fill" and "이번 턴에 보낸 자리가 아닙니다" in none["dropped"][0]["why"]
    free = A.proposals(doc, [_act((p["b1"], "MVDC 계통 시뮬레이션 모델", src))], {"rev": 1, "turn": "t", "sources": A.sources(MATERIAL)})   # 상자 · 줄 자리를 고르지 않은 턴
    assert free["proposals"] == [] and "자리 채우기는 상자" in free["dropped"][0]["why"]
    doc.set_text(p["b1"], "그 사이 사람이 씀")                                                                                             # 제안을 받는 사이 줄이 바뀜
    ctx = _ctx(doc)
    ctx["fill"][p["b1"]] = {**ctx["fill"][p["b2"]], "raw": ""}
    late = A.proposals(doc, [_act((p["b1"], "MVDC 계통 시뮬레이션 모델", src))], ctx)
    assert late["proposals"] == [] and "그 줄이 바뀌었습니다" in late["dropped"][0]["why"]


def test_fill_same_name_chunks_need_scope(doc):
    p = _paras(doc)
    src = "한국선급은 MVDC 계통 시뮬레이션 모델을 개발한다."
    act = _act((p["j2a"], "MVDC 계통 시뮬레이션 모델", src), (p["j1a"], "MVDC 계통 시뮬레이션 모델", src))
    off = A.proposals(doc, [act], _ctx(doc, scope={"types": {"fill"}, "paras": None}))                                                    # 범위가 있어도 자리를 정해 주지 않았으면 안 된다
    assert off["proposals"] == [] and "같은 이름의 자리가 2곳" in off["dropped"][0]["why"]
    on = A.proposals(doc, [act], _ctx(doc, scope={"types": {"fill"}, "paras": {p["j2"], p["j2a"]}}))                                       # 사람이 둘째 자리를 골랐다 — 첫째 자리의 줄은 대상이 아니다
    (pr,) = on["proposals"]
    assert [ln["para"] for ln in pr["view"]["lines"]] == [p["j2a"]] and pr["view"]["lines"][0]["dup"] == [2, 2] and pr["view"]["rejected"] == [{"para": p["j1a"], "why": "이번 턴에 보낸 자리가 아닙니다", "text": "MVDC 계통 시뮬레이션 모델"}]
    assert pr["op"]["lines"][0]["head"] == p["j2"] and pr["op"]["lines"][0]["headWas"] == "공동(기업명 작성) : "


def test_fill_label_needs_uploaded_original(doc):
    p = _paras(doc)
    act = _act((p["name"], "과제명 : 고전압 직류 차단기 개발", "과제명은 고전압 직류 차단기 개발이다."))
    ctx = _ctx(doc)
    ctx["uploaded"] = {p["name"]: "과제명 :"}
    human = A.proposals(doc, [act], ctx)                                                                                                   # 올린 원본의 그 줄과 다르다 — 올린 뒤에 사람이 쓴 줄
    assert human["proposals"] == [] and "올린 뒤에 사람이 쓴 줄입니다" in human["dropped"][0]["why"]
    was = A.proposals(doc, [act], _ctx(doc, uploaded={p["name"]: "과제명 :"}))                                                             # 같은 원본을 선택에도 주면 「이미 채운 줄」 이라 대상에서 먼저 빠진다(form_slots)
    assert was["proposals"] == [] and "이번 턴에 보낸 자리가 아닙니다" in was["dropped"][0]["why"]
    gone = A.proposals(doc, [act], _ctx(doc, uploaded={}))                                                                                 # 올린 원본에 없는 문단
    assert gone["proposals"] == [] and "올린 뒤에 사람이 쓴 줄입니다" in gone["dropped"][0]["why"]
    (unk,) = A.proposals(doc, [act], _ctx(doc))["proposals"]                                                                               # 원본을 못 견줌 — 줄은 남기되 처음부터 안 고른다
    assert unk["view"]["lines"][0]["warn"] == [A.NO_ORIGINAL, A.LABEL_ASK] and unk["view"]["picked"] == [] and unk["preselect"] is False and unk["warn"] == ["경고 없는 줄이 없습니다 — 줄마다 읽고 고르세요"]


def test_fill_evidence_is_materials_only(doc):
    p = _paras(doc)
    (a,) = A.proposals(doc, [_act((p["b1"], "자료에 없는 문장", "자료에 없는 문장"))], _ctx(doc))["proposals"]                             # 근거 구절이 자료에 없다
    assert a["view"]["lines"][0]["warn"] == ["근거 구절을 자료에서 못 찾음"] and a["view"]["lines"][0]["quoted"] is False and a["view"]["picked"] == [] and a["preselect"] is False
    (b,) = A.proposals(doc, [_act((p["b1"], "비밀 값 9999", "요청 글 — 비밀 값 9999"))], _ctx(doc))["proposals"]                           # 요청 글은 근거가 아니다(견줄 글 = 자료만)
    assert b["view"]["lines"][0]["warn"] == ["근거 구절을 자료에서 못 찾음", "자료에 없는 수가 있습니다"] and b["view"]["picked"] == []
    (c,) = A.proposals(doc, [_act((p["b1"], "000", "000"))], _ctx(doc))["proposals"]                                                       # 고른 글(= 양식의 「000」)도 근거가 아니다
    assert c["view"]["lines"][0]["quoted"] is False and c["view"]["picked"] == []
    (r,) = A.proposals(doc, [_act((p["b1"], "MVDC 모델 개발", "한국선급은 MVDC 계통 시뮬레이션 모델을 개발한다."))], _ctx(doc))["proposals"]   # 근거는 있는데 바꿔 옮김
    assert r["view"]["lines"][0]["warn"] == [A.REWORDED] and r["view"]["lines"][0]["quoted"] is True
    (n,) = A.proposals(doc, [_act((p["b1"], "적합성 평가 절차(안) 5건", "적합성 평가 절차(안) 3건."))], _ctx(doc))["proposals"]              # 수를 바꿈
    assert A.REWORDED in n["view"]["lines"][0]["warn"] and "자료에 없는 수가 있습니다" in n["view"]["lines"][0]["warn"]
    (d,) = A.proposals(doc, [_act((p["b1"], "지은 문장", ""), mode="draft")], _ctx(doc))["proposals"]                                       # 지은 글
    assert d["title"] == "자리 채우기 — 1줄 (지은 글)" and d["view"]["lines"][0]["warn"] == ["에이전트가 쓴 글 — 읽고 반영하세요"] and d["preselect"] is False
    (h,) = A.proposals(doc, [_act((p["name"], "과제명 : 인텍전기전자", ""))], _ctx(doc, uploaded={p["name"]: "과제명 : "}, decided=["주관기관 칸에는 인텍전기전자를 씀"]))["proposals"]
    assert h["view"]["lines"][0]["from"] == "decided" and h["view"]["lines"][0]["warn"] == [A.FROM_DECIDED, A.LABEL_ASK] and h["view"]["picked"] == []    # 사람이 정한 답의 값 — 보이되 처음부터 안 고른다


def test_fill_check_line(doc):
    p = _paras(doc)
    raw = "구분 ( □ 연차 □ 최종 □ 단계 )"
    one = _act((p["check"], "구분 ( ■ 연차 □ 최종 □ 단계 )", ""))
    (a,) = A.proposals(doc, [one], _ctx(doc))["proposals"]                                                                                 # 어느 항목인지 사람이 정한 답에 없다
    assert a["view"]["lines"][0]["mode"] == "check" and a["view"]["lines"][0]["value"] == "연차" and a["view"]["lines"][0]["warn"] == [A.CHECK_ASK] and a["view"]["picked"] == []
    (b,) = A.proposals(doc, [one], _ctx(doc, decided=["연차보고서로 냅니다"]))["proposals"]                                                 # 그 항목이 정한 답에 있어도 표시 줄은 늘 사람이 확인한다(v1 — 표시만 「정한 답」)
    assert b["view"]["lines"][0]["warn"] == [A.CHECK_ASK] and b["view"]["lines"][0]["from"] == "decided" and b["view"]["picked"] == [] and b["preselect"] is False
    (x,) = A.proposals(doc, [_act((p["check"], "구분 ( □ 연차 ■ 최종 □ 단계 )", ""))], _ctx(doc, decided=["최종보고서 제외"]))["proposals"]    # astra 3차 — 「최종보고서 제외」 라는 답으로 「최종」 에 표시: 처음부터 고르면 안 된다
    assert x["view"]["lines"][0]["value"] == "최종" and x["view"]["picked"] == [] and x["preselect"] is False
    (c,) = A.proposals(doc, [one], _ctx(doc, decided=["연차보고서 · 최종보고서 가운데 정함"]))["proposals"]                                  # 다른 항목도 답에 있다 — 확인
    assert c["view"]["lines"][0]["warn"] == [A.CHECK_ASK]
    two = A.proposals(doc, [_act((p["check"], "구분 ( ■ 연차 ■ 최종 □ 단계 )", ""))], _ctx(doc, decided=["연차"]))                           # 둘을 바꿈
    assert two["proposals"] == [] and "「□」 하나만 「■」 로" in two["dropped"][0]["why"]
    more = A.proposals(doc, [_act((p["check"], raw + " 그리고", ""))], _ctx(doc))                                                           # 글을 더함
    assert more["proposals"] == [] and "글을 더하거나 빼지 않습니다" in more["dropped"][0]["why"]
    doc.set_text(p["check"], "구분 ( ■ 연차 □ 최종 □ 단계 )")                                                                                # 이미 표시한 줄
    done = A.proposals(doc, [_act((p["check"], "구분 ( ■ 연차 ■ 최종 □ 단계 )", ""))], _ctx(doc, decided=["최종"]))
    assert done["proposals"] == [] and "이미 표시한 항목이 있습니다" in done["dropped"][0]["why"]


# ---- 끝점 — 범위 · 반영 ---------------------------------------------------------------------------------------------------------------

@pytest.fixture
def c():
    return TestClient(server.app)


@pytest.fixture
def plain(monkeypatch):
    monkeypatch.setattr(API, "_style_apply", lambda: None)
    monkeypatch.setattr(API, "_listing", lambda: [])


def _llm(monkeypatch, answer, seen=None):
    def fake(data, guide="", job="", **kw):
        got = answer(data) if callable(answer) else answer
        if seen is not None:
            seen.append(data)
        return {"data": A.clean(got), "prompt": A.content(data, guide, job), "response": got, "call": {"backend": "api", "model": "m", "effort": kw.get("effort"), "ms": 7, "costUsd": 0.01, "error": None}}
    monkeypatch.setattr(A, "ask", fake)
    monkeypatch.setattr(API.llm, "status", lambda: {"available": True})


def _open(c, boxed):
    r = c.post("/api/docs", files={"file": ("상자.hwpx", boxed)})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    mid = c.post(f"/api/docs/{d}/agent/material", json={"name": "자료", "text": MATERIAL}).json()["id"]
    return d, server.DOCS[d], mid


SEL = {"paras": [], "table": BOX, "range": None, "cursor": BOX}
SRC = "한국선급은 MVDC 계통 시뮬레이션 모델을 개발한다."


def test_turn_box_prompt_scope_and_refusals(c, monkeypatch, plain, boxed):
    d, s, mid = _open(c, boxed)
    p = _paras(s.doc)
    seen = []
    write = {"type": "write", "after": BOX, "mode": "extract", "style": "", "table": "", "range": "", "paras": [], "item": "", "candidates": [], "picks": [], "fills": [], "lines": [{"item": "", "text": SRC, "source": SRC}]}
    tfill = {"type": "tableFill", "after": "", "mode": "", "style": "", "table": "t1", "range": "", "paras": [], "item": "", "lines": [], "candidates": [], "picks": [], "fills": []}
    fill = _act((p["b1"], "MVDC 계통 시뮬레이션 모델", SRC), (p["j1a"], "MVDC 계통 시뮬레이션 모델", SRC))
    _llm(monkeypatch, {"reply": "채웁니다", "actions": [fill, write]}, seen)
    monkeypatch.setattr(TF, "ask", lambda *a, **k: pytest.fail("범위 밖의 표는 표 채우기 호출을 하지 않는다"))
    # 끝점(범위 없음): 상자의 줄이 프롬프트에 · 자리 채우기 제안 · 같은 이름의 자리는 빠진다 · 글 쓰기는 전처럼
    r = c.post(f"/api/docs/{d}/agent/turn", json={"text": "상자를 채워 줘", "materials": [mid], "selection": SEL})
    assert r.status_code == 200, r.text
    t = seen[0]["selection"]["table"]
    assert t["box"] is True and f"[{p['b1']} {p['b2']}] (쓸 자리 — 빈 줄 2)" in t["lines"] and "grid" not in t
    v = r.json()["turn"]
    assert [x["type"] for x in v["proposals"]] == ["fill", "write"] and v["proposals"][0]["view"]["picked"] == [p["b1"]] and "op" not in v["proposals"][0]
    assert [x["para"] for x in v["proposals"][0]["view"]["rejected"]] == [p["j1a"]] and s.rev == 0
    # 서버만 주는 범위: 이 자리에서 받는 행동 · 고른 자리 · 표 — 막는 것은 하위 호출 전
    _llm(monkeypatch, {"reply": "채웁니다", "actions": [fill, write, tfill]})
    got = API._turn(d, {"text": "상자를 채워 줘", "materials": [mid], "selection": SEL}, scope={"types": {"fill", "tableFill"}, "paras": {p["j1"], p["j1a"]}, "tables": set(), "decided": [], "uploaded": None})
    v2 = got["turn"]
    assert [x["type"] for x in v2["proposals"]] == ["fill"] and [ln["para"] for ln in v2["proposals"][0]["view"]["lines"]] == [p["j1a"]]      # 고른 자리만(b1 은 이번 범위 밖)
    assert [(x["type"], x["why"]) for x in v2["dropped"]] == [("write", API.OFF_TYPE), ("tableFill", API.OFF_TABLE)] and API.OFF_TABLE in v2["notes"]
    # 범위가 없어도 상자를 고른 턴은 그 상자 안의 표를 채우지 않는다(그림 · 샘플 자리) — 견본의 상자에는 안쪽 표가 없어, 선택이 돌려주는 「상자 안의 표」 만 바꿔 본다
    real = A.selection_of
    monkeypatch.setattr(A, "selection_of", lambda *a, **k: {**real(*a, **k), "inner": ["t1"]})
    v3 = API._turn(d, {"text": "상자를 채워 줘", "materials": [mid], "selection": SEL})["turn"]
    assert [(x["type"], x["why"]) for x in v3["dropped"]] == [("tableFill", API.OFF_TABLE)] and [x["type"] for x in v3["proposals"]] == ["fill", "write"]
    monkeypatch.setattr(A, "selection_of", real)
    with pytest.raises(HTTPException) as e:                                                                                               # 본문 검사는 그대로
        API._turn(d, {"text": "", "selection": SEL}, scope={"types": {"fill"}})
    assert e.value.status_code == 400


def test_apply_skips_a_changed_chunk_and_applies_the_rest_in_one_edit(c, monkeypatch, plain, boxed):
    d, s, mid = _open(c, boxed)
    p = _paras(s.doc)
    acts = [_act((p["stub"], "    - MVDC 계통 시뮬레이션 모델", SRC), (p["b1"], "적합성 평가 절차(안) 3건", "적합성 평가 절차(안) 3건."), (p["j2a"], "MVDC 계통 시뮬레이션 모델", SRC))]
    _llm(monkeypatch, {"reply": "", "actions": acts})
    scope = {"types": {"fill"}, "paras": {p["stub"], p["b1"], p["j2"], p["j2a"]}, "tables": set(), "decided": [], "uploaded": {p["stub"]: "    - "}}
    v = API._turn(d, {"text": "상자를 채워 줘", "materials": [mid], "selection": SEL}, scope=scope)["turn"]
    (pr,) = v["proposals"]
    assert pr["view"]["picked"] == [p["stub"], p["b1"], p["j2a"]]
    url = f"/api/docs/{d}/agent/apply"
    bad = c.post(url, json={"turn": v["id"], "proposal": "p1", "requestId": "r-0", "expectedRev": 0, "picks": {"fills": [p["b1"], p["name"]]}})   # 제안에 없는 줄
    assert bad.status_code == 400 and "이 제안에 없는 줄" in bad.json()["detail"] and s.rev == 0 and len(s.undo) == 0
    with s.lock:
        s.doc.set_text(p["ph"], "001")                                                                                                    # 첫 덩이의 머리 글이 바뀜(다른 항목의 자리가 됐을 수 있다)
    a = c.post(url, json={"turn": v["id"], "proposal": "p1", "requestId": "r-1", "expectedRev": 0})
    assert a.status_code == 200, a.text
    ap = a.json()["applied"]
    assert ap["type"] == "fill" and ap["filledLines"] == {"box": BOX, "paras": [p["j2a"]], "skipped": [{"para": p["stub"], "why": "그 자리의 머리 글이 바뀜"}, {"para": p["b1"], "why": "그 자리의 머리 글이 바뀜"}]}
    texts = [b["text"] for b in s.doc.table_block(BOX)["cells"][0]["blocks"]]
    assert texts[9] == "MVDC 계통 시뮬레이션 모델" and texts[2:5] == ["    - ", "", ""] and len(s.undo) == 1 and a.json()["undo"] == 1          # 한 편집 · 건너뛴 덩이는 그대로
    saved = c.get(f"/api/docs/{d}/agent/turns/{v['id']}").json()["proposals"][0]
    assert saved["state"] == "applied" and saved["applied"]["paras"] == [p["j2a"]] and saved["applied"]["note"] == "1줄 채움 · 건너뜀 2(그 자리의 머리 글이 바뀜)"
    assert c.post(url, json={"turn": v["id"], "proposal": "p1", "requestId": "r-2", "expectedRev": s.rev}).status_code == 409             # 이미 반영한 제안
    assert c.post(f"/api/docs/{d}/undo").status_code == 200 and s.doc.table_block(BOX)["cells"][0]["blocks"][9]["text"] == ""              # 실행 취소 한 번


def test_apply_all_chunks_conflict_is_409_without_an_edit(c, monkeypatch, plain, boxed):
    d, s, mid = _open(c, boxed)
    p = _paras(s.doc)
    _llm(monkeypatch, {"reply": "", "actions": [_act((p["stub"], "    - MVDC 계통 시뮬레이션 모델", SRC), (p["b1"], "적합성 평가 절차(안) 3건", "적합성 평가 절차(안) 3건."))]})
    v = c.post(f"/api/docs/{d}/agent/turn", json={"text": "상자를 채워 줘", "materials": [mid], "selection": SEL}).json()["turn"]
    assert v["proposals"][0]["view"]["picked"] == [p["stub"], p["b1"]]
    with s.lock:
        s.doc.set_text(p["b1"], "사람이 먼저 씀")                                                                                         # 고른 줄 하나가 바뀜 — 그 덩이를 통째로 건너뛴다(남는 덩이 없음)
    r = c.post(f"/api/docs/{d}/agent/apply", json={"turn": v["id"], "proposal": "p1", "requestId": "r-1", "expectedRev": 0})
    assert r.status_code == 409 and "넣을 줄이 없습니다" in r.json()["detail"] and "제안을 받은 뒤 줄이 바뀜" in r.json()["detail"]
    assert len(s.undo) == 0 and s.rev == 0 and s.doc.table_block(BOX)["cells"][0]["blocks"][2]["text"] == "    - "                         # 편집 없음 — 실행 취소 기록도 없다
    none = c.post(f"/api/docs/{d}/agent/apply", json={"turn": v["id"], "proposal": "p1", "requestId": "r-2", "expectedRev": 0, "picks": {"fills": []}})
    assert none.status_code == 400 and "고른 줄이 없습니다" in none.json()["detail"]


def test_line_slot_turn_and_apply(c, monkeypatch, plain, boxed):
    d, s, mid = _open(c, boxed)
    line = _line(s.doc)
    _llm(monkeypatch, {"reply": "", "actions": [_act((line, "  o 추진전략(비전) : MVDC 계통 시뮬레이션 모델", SRC))]})
    sel = {"paras": [], "table": None, "range": None, "cursor": line}
    v = API._turn(d, {"text": "이 줄을 채워 줘", "materials": [mid], "selection": sel}, scope={"types": {"fill"}, "paras": None, "tables": set(), "decided": [], "uploaded": {line: "  o 추진전략(비전) : "}})["turn"]
    (pr,) = v["proposals"]
    assert pr["view"]["box"] is None and pr["view"]["picked"] == [] and pr["view"]["lines"][0]["warn"] == [A.LABEL_ASK] and pr["target"]["block"] == line   # 같은 줄 뒤의 값 — 사람이 고른다
    assert c.post(f"/api/docs/{d}/agent/apply", json={"turn": v["id"], "proposal": "p1", "requestId": "r-0", "expectedRev": 0}).status_code == 400
    a = c.post(f"/api/docs/{d}/agent/apply", json={"turn": v["id"], "proposal": "p1", "requestId": "r-1", "expectedRev": 0, "picks": {"fills": [line]}})
    assert a.status_code == 200, a.text
    assert a.json()["applied"]["filledLines"] == {"box": None, "paras": [line], "skipped": []} and s.doc._text(s.doc._ids[line]) == "  o 추진전략(비전) : MVDC 계통 시뮬레이션 모델" and len(s.undo) == 1


# ---- astra 3차(결과 검토)의 반례 ---------------------------------------------------------------------------------------------------------

def test_fill_text_is_composed_by_the_server(doc, boxed):
    """넣을 글 = 지금 원문 그대로 + 값(서버가 짓는다) — 모델이 첫머리의 빈칸 · 탭을 다르게 적어도 카드의 글 = 문서에 쓰는 글 = 다시 연 글."""
    p = _paras(doc)
    doc.set_text(p["name"], "기관:\t")
    raw = doc._text(doc._ids[p["name"]])
    assert raw.startswith("기관:") and raw != "기관:"                                                                                        # 탭이 원문에 남는다
    up = {p["name"]: raw, p["stub"]: "    - "}
    got = A.proposals(doc, [_act((p["name"], "기관:한국선급", SRC), (p["stub"], "    -MVDC 계통 시뮬레이션 모델", SRC))], _ctx(doc, uploaded=up))
    (pr,) = got["proposals"]
    assert [ln["text"] for ln in pr["view"]["lines"]] == [raw + "한국선급", "    - MVDC 계통 시뮬레이션 모델"] and [ln["text"] for ln in pr["op"]["lines"]] == [raw + "한국선급", "    - MVDC 계통 시뮬레이션 모델"]
    for ln in pr["op"]["lines"]:
        doc.set_text(ln["para"], ln["text"])
    d2 = HwpxDoc(doc.save())
    d2.blocks()
    q = _paras(d2)
    assert d2._text(d2._ids[q["name"]]) == raw + "한국선급" and d2._text(d2._ids[q["stub"]]) == "    - MVDC 계통 시뮬레이션 모델"
    tight = A.proposals(doc_ := HwpxDoc(boxed), [], {})                                                                                     # (문서를 새로 — 아래는 빈칸으로 안 끝나는 이름 줄)
    doc_.blocks()
    q = _paras(doc_)
    doc_.set_text(q["name"], "기관:")
    (one,) = A.proposals(doc_, [_act((q["name"], "기관:한국선급", SRC))], _ctx(doc_, uploaded={q["name"]: "기관:"}))["proposals"]
    assert one["op"]["lines"][0]["text"] == "기관: 한국선급" and tight["proposals"] == []                                                    # 빈칸으로 안 끝나면 한 칸을 넣는다


def test_fill_stub_needs_uploaded_original(doc):
    p = _paras(doc)
    act = _act((p["stub"], "    - MVDC 계통 시뮬레이션 모델", SRC))
    ctx = _ctx(doc)
    ctx["uploaded"] = {p["stub"]: "    -"}
    human = A.proposals(doc, [act], ctx)                                                                                                    # 올린 원본의 그 줄과 다르다 — 사람이 친 글머리 줄(「O」 · 「------」 …)에 덧붙이지 않는다
    assert human["proposals"] == [] and A.HUMAN_LINE in human["dropped"][0]["why"]
    (unk,) = A.proposals(doc, [act], _ctx(doc))["proposals"]                                                                                # 원본을 못 견줌 — 처음부터 안 고른다
    assert unk["view"]["lines"][0]["warn"] == [A.NO_ORIGINAL] and unk["view"]["picked"] == []
    (ok,) = A.proposals(doc, [act], _ctx(doc, uploaded={p["stub"]: "    - "}))["proposals"]
    assert ok["view"]["picked"] == [p["stub"]]


def test_box_slots_skip_paragraphs_holding_an_object(doc):
    """글은 비었어도 개체(수식 · 그림)를 품은 문단은 빈 줄이 아니다 — 견본에 그런 문단을 만들 길이 없어 `_has_object` 를 바꿔 끼워 가름만 본다."""
    p = _paras(doc)
    assert p["b1"] in A.box_slots(doc, BOX)[1]
    held = doc._ids[p["b1"]]
    doc._has_object = lambda el: el is held
    slots = A.box_slots(doc, BOX)[1]
    assert p["b1"] not in slots and p["b2"] in slots
    got = A.proposals(doc, [_act((p["b1"], "MVDC 계통 시뮬레이션 모델", SRC))], _ctx(doc))
    assert got["proposals"] == [] and "이번 턴에 보낸 자리가 아닙니다" in got["dropped"][0]["why"]


def test_fill_quote_and_numbers_stay_inside_one_material(doc):
    p = _paras(doc)

    def ctx(*mats):
        c = _ctx(doc)
        c["sources_mat"] = {**A.sources("", "", [{"text": m} for m in mats]), "each": list(mats)}
        return c
    (a,) = A.proposals(doc, [_act((p["b1"], "한국선급", "한국선급"))], ctx("주관기관은 한국", "선급 규정을 따른다"))["proposals"]              # 자료 1의 끝 + 자료 2의 처음 = 근거가 아니다
    assert a["view"]["lines"][0]["quoted"] is False and a["view"]["picked"] == []
    (b,) = A.proposals(doc, [_act((p["b1"], "120 kW", "1120 kW"))], ctx("정격 출력은 1120 kW 이다", "시험 기간 120일"))["proposals"]          # 인용은 자료 1 — 수도 자료 1에서(다른 자료의 「120일」 로 지나가지 않는다)
    assert b["view"]["lines"][0]["quoted"] is True and "자료에 없는 수가 있습니다" in b["view"]["lines"][0]["warn"] and b["view"]["picked"] == [] and b["checks"][1]["status"] == "warn"
    (ok,) = A.proposals(doc, [_act((p["b1"], "1120 kW", "정격 출력은 1120 kW 이다"))], ctx("정격 출력은 1120 kW 이다", "시험 기간 120일"))["proposals"]
    assert ok["view"]["picked"] == [p["b1"]]


def _stub_card(doc, levels):
    p = _paras(doc)
    (pr,) = A.proposals(doc, [_act((p["stub"], "    - MVDC 계통 시뮬레이션 모델", SRC), (p["j2a"], "MVDC 계통 시뮬레이션 모델", SRC))],
                        _ctx(doc, levels=levels, uploaded={p["stub"]: "    - "}, scope={"types": {"fill"}, "paras": {p["stub"], p["j2a"]}}))["proposals"]
    return p, pr


def test_apply_checks_where_the_line_belongs_now(doc):
    """반영 직전에 지금 문서의 덩이를 다시 셈해 소속을 견준다 — 글(줄 · 머리)이 그대로여도 윗 제목이 바뀌었거나 다른 머리 아래로 갔으면 그 덩이를 건너뛴다(astra 3차의 두 재현)."""
    from types import SimpleNamespace
    q = _paras(doc)
    levels = {q["title"]: 3, q["ph"]: 4, q["stub"]: 5}
    p, pr = _stub_card(doc, levels)
    assert pr["op"]["lines"][0]["under"] == "연구개발 목표" and pr["view"]["lines"][0]["under"] == "연구개발 목표"
    s, done = SimpleNamespace(doc=doc), {}
    hosts, run = API._make_fill_lines(pr["op"], None, pr["view"], done, levels, None)(s)                                                   # 그대로면 둘 다 넣는다
    assert callable(run) and hosts
    doc.set_text(p["title"], "연구개발 결과")                                                                                               # (가) 윗 제목만 고침 — 「000」 · 글머리 줄은 그대로
    _, run = API._make_fill_lines(pr["op"], None, pr["view"], done, levels, None)(s)
    run()
    assert done["filledLines"]["paras"] == [p["j2a"]] and done["filledLines"]["skipped"] == [{"para": p["stub"], "why": API.MOVED}]
    assert doc._text(doc._ids[p["stub"]]) == "    - " and doc._text(doc._ids[p["j2a"]]) == "MVDC 계통 시뮬레이션 모델"
    with pytest.raises(HTTPException) as e:                                                                                               # 남는 덩이가 없으면 편집 없이 409
        API._make_fill_lines(pr["op"], [p["stub"]], pr["view"], {}, levels, None)(s)
    assert e.value.status_code == 409 and API.MOVED in e.value.detail


def test_apply_skips_a_line_now_under_another_head(doc):
    from types import SimpleNamespace
    p, pr = _stub_card(doc, None)
    doc.insert_after(p["ph"], [{"kind": "paragraph", "text": "새 머리 글", "templateId": p["ph"], "keepNumbering": False}])                  # (나) 글머리 줄 앞에 다른 머리가 들어섰다 — 그 줄은 이제 다른 머리의 자리
    assert doc._text(doc._ids[p["stub"]]) == "    - " and doc._text(doc._ids[p["ph"]]) == "000"
    done = {}
    _, run = API._make_fill_lines(pr["op"], None, pr["view"], done, None, None)(SimpleNamespace(doc=doc))
    run()
    assert done["filledLines"]["skipped"] == [{"para": p["stub"], "why": API.MOVED}] and done["filledLines"]["paras"] == [p["j2a"]]


def test_turn_scope_after_and_uploaded_without_scope(c, monkeypatch, plain, boxed):
    d, s, mid = _open(c, boxed)
    p = _paras(s.doc)
    write = {"type": "write", "after": BOX, "mode": "extract", "style": "", "table": "", "range": "", "paras": [], "item": "", "candidates": [], "picks": [], "fills": [], "lines": [{"item": "", "text": SRC, "source": SRC}]}
    _llm(monkeypatch, {"reply": "", "actions": [write]})
    body = {"text": "아래에 써 줘", "materials": [mid], "selection": SEL}
    off = API._turn(d, body, scope={"types": {"write"}, "after": {"p1"}, "paras": set(), "tables": set()})["turn"]                          # 이 자리의 턴은 그 자리 뒤에만 쓴다(다른 헤딩 · 상자 뒤는 버림)
    assert off["proposals"] == [] and [(x["type"], x["why"]) for x in off["dropped"]] == [("write", API.OFF_AFTER)]
    on = API._turn(d, body, scope={"types": {"write"}, "after": {BOX}, "paras": set(), "tables": set()})["turn"]
    assert [x["type"] for x in on["proposals"]] == ["write"]
    # 범위가 없는 턴(에이전트 보기에서 바로)도 올린 원본을 읽는다 — 이미 채운 줄은 다시 쓸 자리가 아니고, 같은 이름 자리의 하나를 채워도 나머지가 풀리지 않는다
    with s.lock:
        s.doc.set_text(p["name"], "과제명 : 채운 값")
        s.doc.set_text(p["j1"], "공동(기업명 작성) : 한국선급")
    seen = []
    _llm(monkeypatch, {"reply": "", "actions": [_act((p["name"], "과제명 : 채운 값 더", SRC), (p["j2a"], "MVDC 계통 시뮬레이션 모델", SRC))]}, seen)
    v = c.post(f"/api/docs/{d}/agent/turn", json={"text": "상자를 채워 줘", "materials": [mid], "selection": SEL}).json()["turn"]
    assert "이미 채움 — 다시 쓰지 않음" in seen[0]["selection"]["table"]["lines"] and v["proposals"] == []
    assert "이번 턴에 보낸 자리가 아닙니다" in v["dropped"][0]["why"] or "같은 이름의 자리" in v["dropped"][0]["why"]
