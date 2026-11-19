"""테이블 매니저 — 표 하나의 지금 판정(spec_테이블매니저 ② §2 「지금 판정」 · app/table_manager.py) + 3단계가 남기는 `auto` · `inputKey`(app/heading_tables.py)."""
import copy

import pytest

from app import heading_guides as G
from app import heading_rules as R
from app import heading_tables as HT
from app import table_manager as TM

SHADE = "#D6D6D6"
TID = "t100"
# (행, 열, 행 병합, 열 병합, 음영, [문단 글…]) — 「연구개발비 사용계획」 꼴: 머리 2행 · 머리 1열 · 합계 열/행 · 안내 줄
CELLS = [
    (0, 0, 2, 1, SHADE, ["구분"]), (0, 1, 1, 2, SHADE, ["1차년도"]), (0, 3, 1, 2, SHADE, ["2차년도"]), (0, 5, 2, 1, SHADE, ["합계"]),
    (1, 1, 1, 1, SHADE, ["현금"]), (1, 2, 1, 1, SHADE, ["현물"]), (1, 3, 1, 1, SHADE, ["현금"]), (1, 4, 1, 1, SHADE, ["현물"]),
    (2, 0, 1, 1, None, ["인건비"]), (2, 1, 1, 1, None, ["100"]), (2, 2, 1, 1, None, ["20"]), (2, 3, 1, 1, None, ["120"]), (2, 4, 1, 1, None, ["30"]), (2, 5, 1, 1, None, ["270"]),
    (3, 0, 1, 1, None, ["재료비"]), (3, 1, 1, 1, None, ["50"]), (3, 2, 1, 1, None, ["10"]), (3, 3, 1, 1, None, ["60"]), (3, 4, 1, 1, None, ["10"]), (3, 5, 1, 1, None, ["130"]),
    (4, 0, 1, 1, None, ["합계"]), (4, 1, 1, 1, None, ["150"]), (4, 2, 1, 1, None, ["30"]), (4, 3, 1, 1, None, ["180"]), (4, 4, 1, 1, None, ["40"]), (4, 5, 1, 1, None, ["400"]),
    (5, 0, 1, 6, None, ["※ 현물은 기관이 부담하는 금액을 적는다."]),
]
LABOR, LABOR_CASH, LABOR_SUM, FOOT = "c109", "c110", "c114", "c121"   # 「인건비」 · 그 줄의 「100」 · 그 줄의 합계 「270」 · 왼쪽 아래 「합계」


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _stage1(edit=None):
    """합성 1단계 레코드(표 하나 + 앞 문단). edit = {칸 id: [문단 글…]} 로 칸의 문단을 바꾼다. 문단 종류는 실제 분류기로."""
    rules, run = R.active(R.load(), ()), R._Run()
    tbl = {"t": "tbl", "id": TID, "rows": 6, "cols": 6, "cells": len(CELLS), "key": 1, "host": "x1"}
    recs = [{"id": "p90", "n": 0, "path": [], "text": "<연구개발비 사용계획> (단위: 천원)", "kind": "plain", "blank": False, "char": {"text": {"bold": False}}}]
    n = 0
    for i, (r, c, rs, cs, fill, paras) in enumerate(CELLS):
        cid = f"c{101 + i}"
        cell = {"t": "cell", "id": cid, "row": r, "col": c, "rs": rs, "cs": cs, "fill": fill, "key": 10 + i}
        for t in (edit or {}).get(cid, paras):
            n += 1
            h = R.classify(t, rules, run)
            recs.append({"id": f"p{200 + n}", "n": n, "path": [tbl, cell], "text": t, "kind": h["kind"], "blank": h["blank"], "char": {"text": {"bold": False}}})
    return {"paras": recs}


def _stored(roles=None, s1=None):
    """3단계(스크립트만)가 남긴 그 표."""
    return HT.build(s1 or _stage1(), use_llm=False, roles={TID: roles} if roles else None)["tables"][0]


def _by(j):
    return {x["id"]: x for x in j["table"]["cells"]}


def test_build_leaves_input_key_and_auto_only_under_a_designation():
    plain, mine = _stored(), _stored({LABOR: "field"})
    assert plain["inputKey"] and plain["inputKey"] == mine["inputKey"]          # 사람 지정은 자료 열쇠에 안 든다(초안일 때의 자료)
    assert not any("auto" in c for c in plain["cells"])
    c = next(c for c in mine["cells"] if c["id"] == LABOR)
    assert (c["auto"], c["role"], c["reason"]) == ("rowhead", "field", "사용자 지정")
    assert [c["id"] for c in mine["cells"] if "auto" in c] == [LABOR]
    assert TM.judge(_stage1(), TID)["inputKey"] == plain["inputKey"]            # 매니저의 열쇠 = 3단계의 열쇠(같은 자료)


def test_draft_when_nothing_is_stored():
    j = TM.judge(_stage1(), TID)
    assert j["source"] == "draft" and not j["reuse"]["ok"] and j["reuse"]["why"]
    by = _by(j)
    assert by[LABOR]["role"] == by[LABOR]["auto"] == by[LABOR]["draft"] == "rowhead" and not by[LABOR].get("user")
    assert [by[i]["text"] for i in by[LABOR_CASH]["rowPath"]] == ["인건비"] and [by[i]["text"] for i in by[LABOR_CASH]["colPath"]] == ["1차년도", "현금"]
    assert {s["id"]: (s["kind"], s["headerRows"], s["headerCols"]) for s in j["subs"]} == {"A": ("matrix", 2, 1), "B": ("note", 0, 0)}
    assert j["sem"]["calc"]["formulas"] == 8 and j["sem"]["calc"]["mismatch"] == 0
    assert j["sem"]["unit"] is None                                              # 표 앞 문단은 부르는 쪽이 준다(표 레코드에는 없다)
    assert TM.judge(_stage1(), TID, before="<연구개발비 사용계획> (단위: 천원)")["sem"]["unit"] == "천원"
    assert TM.judge(_stage1(), TID, stored=_stored(), same_doc=True)["sem"]["unit"] == "천원"   # 안 주면 저장된 앞 문단
    assert TM.judge(_stage1(), "t999") is None


def test_stored_roles_and_bands_are_reused_only_when_the_input_is_the_same():
    stored = _stored()
    llm = copy.deepcopy(stored)
    foot = next(c for c in llm["cells"] if c["id"] == FOOT)
    foot.update(role="field", changed=True, reason="값으로 읽힘")                 # LLM 이 왼쪽 아래 「합계」 를 필드로 고쳤다고 치자
    keep = copy.deepcopy(llm)
    same = TM.judge(_stage1(), TID, stored=llm, same_doc=True)
    assert same["source"] == "stage3" and same["reuse"] == {"ok": True, "why": "문서가 그대로"}
    assert (_by(same)[FOOT]["role"], _by(same)[FOOT]["auto"], _by(same)[FOOT]["draft"], _by(same)[FOOT]["changed"]) == ("field", "field", "rowhead", True)
    assert _by(same)[FOOT]["reason"] == "값으로 읽힘"
    assert llm == keep                                                           # 저장된 결과는 안 고친다
    key = TM.judge(_stage1(), TID, stored=llm)                                   # 문서의 다른 곳이 바뀜 — 이 표의 자료는 그대로
    assert key["source"] == "stage3" and key["reuse"]["why"] == "이 표의 자료가 그대로"
    moved = TM.judge(_stage1({LABOR_CASH: ["999"]}), TID, stored=llm)            # 이 표의 칸 글이 바뀜 → 그 표 전체를 초안으로
    assert moved["source"] == "draft" and moved["reuse"]["why"] == "판정 뒤 이 표가 바뀜" and _by(moved)[FOOT]["role"] == "rowhead"
    old = {k: v for k, v in llm.items() if k != "inputKey"}                      # 열쇠가 없는 옛 결과 — 문서가 그대로일 때만
    assert TM.judge(_stage1(), TID, stored=old)["source"] == "draft" and TM.judge(_stage1(), TID, stored=old, same_doc=True)["source"] == "stage3"
    fewer = {**llm, "cells": llm["cells"][:-1]}                                  # 칸이 달라짐
    assert TM.judge(_stage1(), TID, stored=fewer, same_doc=True)["reuse"] == {"ok": False, "why": "표의 칸이 바뀜"}


def test_text_paragraphs_and_numbers_always_come_from_the_current_records():
    stored = _stored()
    now = _stage1({LABOR_SUM: ["280"], "c127": ["※ 현물은 기관이 부담하는 금액을 적는다.", "IMPORTANT CONTENT"]})
    j = TM.judge(now, TID, stored=stored, same_doc=True)                         # 다시 쓰는 것은 역할 · 띠뿐
    by = _by(j)
    assert j["source"] == "stage3"
    assert len(by["c127"]["paras"]) == 2 and "IMPORTANT CONTENT" in by["c127"]["textFull"]      # 저장된 표에는 문단이 하나뿐이었다
    assert len(next(c for c in stored["cells"] if c["id"] == "c127")["paras"]) == 1
    assert by[LABOR_SUM]["num"] == 280
    f = next(f for f in j["sem"]["formulas"] if f["cell"] == LABOR_SUM)
    assert (f["expected"], f["actual"], f["status"]) == (270, 280, "mismatch")                   # 검산도 지금 값으로


def test_user_designation_is_merged_on_top_and_released_when_removed():
    stored = _stored({LABOR: "field"})                                           # 지정이 있는 채 돈 3단계 — 최종 역할에 지정이 녹아 있다
    freed = TM.judge(_stage1(), TID, stored=stored, same_doc=True)               # 그 뒤 지정을 풀었다
    assert freed["source"] == "stage3" and _by(freed)[LABOR]["role"] == "rowhead" and not _by(freed)[LABOR].get("user")
    assert [x["text"] for x in freed["table"]["cells"] if x["id"] in _by(freed)[LABOR_CASH]["rowPath"]] == ["인건비"]
    held = TM.judge(_stage1(), TID, stored=stored, user={LABOR: "field", "c999": "rowhead", FOOT: "bogus"}, same_doc=True)
    by = _by(held)
    assert (by[LABOR]["role"], by[LABOR]["auto"], by[LABOR]["user"], by[LABOR]["reason"]) == ("field", "rowhead", True, "사용자 지정")
    assert by[FOOT]["role"] == "rowhead" and not by[FOOT].get("user")            # 모르는 역할 · 없는 칸은 안 쓴다
    assert by[LABOR_CASH]["rowPath"] == []                                       # 경로는 역할을 합친 뒤에 다시 — 「인건비」 가 더는 행헤더가 아니다
    legacy = copy.deepcopy(stored)
    next(c for c in legacy["cells"] if c["id"] == LABOR).pop("auto")             # `auto` 가 없는 옛 결과 — 지정을 가를 수 없다
    old = TM.judge(_stage1(), TID, stored=legacy, same_doc=True)
    assert old["reuse"] == {"ok": False, "why": "사람 지정이 섞인 옛 결과"} and _by(old)[LABOR]["role"] == "rowhead"


def _template(j, **over):
    """판정 → 양식의 확정본 꼴(자리별 역할 · 띠) — spec_테이블매니저 ② §10."""
    return {"id": "e1", "rev": 3, "roles": [[x["row"], x["col"], x["role"]] for x in j["table"]["cells"]],
            "bands": [{k: s[k] for k in ("id", "rows", "cols", "kind", "headerRows", "headerCols")} for s in j["subs"]], **over}


def test_template_keeps_the_roles_when_values_are_filled_in():
    blank = TM.judge(_stage1(), TID)
    tpl = _template(blank)
    filled = {"c110": ["홍길동"], "c116": ["김철수"], "c122": ["이영희"]}   # 둘째 열의 값 칸을 모두 짧은 글로 — 초안은 그 열을 헤더 열로 읽는다
    draft = TM.judge(_stage1(filled), TID)
    assert _by(draft)[LABOR_CASH]["role"] == "rowhead" and draft["source"] == "draft"                      # 내용으로 어림하면 흔들린다
    j = TM.judge(_stage1(filled), TID, template=tpl)
    by = _by(j)
    assert j["source"] == "template" and j["template"] == {"id": "e1", "rev": 3} and j["reuse"]["why"] == "양식의 확정본을 씀"
    assert {i: by[i]["role"] for i in by} == {i: x["role"] for i, x in _by(blank).items()}                 # 빈 양식 때의 역할 그대로
    assert by[LABOR_CASH]["role"] == by[LABOR_CASH]["auto"] == "field" and by[LABOR_CASH]["text"] == "홍길동" and not by[LABOR_CASH].get("user")
    assert [by[i]["text"] for i in by[LABOR_CASH]["rowPath"]] == ["인건비"] and [by[i]["text"] for i in by[LABOR_CASH]["colPath"]] == ["1차년도", "현금"]
    assert {s["id"]: (s["kind"], s["headerRows"], s["headerCols"]) for s in j["subs"]} == {"A": ("matrix", 2, 1), "B": ("note", 0, 0)}
    stored = _stored(s1=_stage1(filled))                                                                 # 그 문서의 3단계 결과가 있어도 확정본이 먼저
    assert TM.judge(_stage1(filled), TID, stored=stored, same_doc=True, template=tpl)["source"] == "template"
    mine = TM.judge(_stage1(filled), TID, template=tpl, user={LABOR: "field"})                           # 그 작업의 헤더 지정은 확정본 위에 — user 는 그 칸에만
    assert (_by(mine)[LABOR]["role"], _by(mine)[LABOR]["auto"], _by(mine)[LABOR]["user"]) == ("field", "rowhead", True)
    assert [x["id"] for x in mine["table"]["cells"] if x.get("user")] == [LABOR]


def test_template_that_does_not_cover_the_table_is_not_used():
    blank = TM.judge(_stage1(), TID)
    short = _template(blank)
    short["roles"] = short["roles"][:-1]                                         # 칸 하나의 역할이 없다
    j = TM.judge(_stage1(), TID, template=short)
    assert j["source"] == "draft" and j["template"] is None
    no_band = _template(blank, bands=[b for b in _template(blank)["bands"] if b["id"] != "B"])   # 안내 줄이 어느 띠에도 안 든다
    assert TM.judge(_stage1(), TID, template=no_band)["source"] == "draft"
    assert TM.judge(_stage1(), TID, template={"id": "x", "roles": "bad", "bands": None})["source"] == "draft"
    bogus = _template(blank)
    bogus["roles"][0][2] = "nonsense"                                            # 모르는 역할
    assert TM.judge(_stage1(), TID, template=bogus)["source"] == "draft"
