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


def _stage1(edit=None, cells=None):
    """합성 1단계 레코드(표 하나 + 앞 문단). edit = {칸 id: [문단 글…]} 로 칸의 문단을 바꾼다. 문단 종류는 실제 분류기로.
    cells = [(칸 id, 행, 열, 행 병합, 열 병합, 음영, [문단 글…])…] 을 주면 그 칸들로(줄을 지우거나 늘린 표 — 칸 id 는 그대로 따라간다)."""
    rules, run = R.active(R.load(), ()), R._Run()
    cells = cells if cells is not None else [(f"c{101 + i}", *x) for i, x in enumerate(CELLS)]
    tbl = {"t": "tbl", "id": TID, "rows": max(x[1] + x[3] for x in cells), "cols": max(x[2] + x[4] for x in cells), "cells": len(cells), "key": 1, "host": "x1"}
    recs = [{"id": "p90", "n": 0, "path": [], "text": "<연구개발비 사용계획> (단위: 천원)", "kind": "plain", "blank": False, "char": {"text": {"bold": False}}}]
    n = 0
    for i, (cid, r, c, rs, cs, fill, paras) in enumerate(cells):
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
    moved = TM.judge(_stage1({LABOR_CASH: ["999"]}), TID, stored=llm)            # 이 표의 칸 글이 바뀜 → 버리지 않고 칸마다 이어 쓴다(2026-11-23 「LLM 판정이 되면 그게 유지되어야지」)
    assert moved["source"] == "stage3" and moved["reuse"] == {"ok": True, "why": "판정을 이어 씀 — 판정 때 있던 칸 27"}
    assert (_by(moved)[FOOT]["role"], _by(moved)[FOOT]["reason"], _by(moved)[LABOR_CASH]["textFull"]) == ("field", "값으로 읽힘", "999")
    assert llm == keep
    old = {k: v for k, v in llm.items() if k != "inputKey"}                      # 열쇠가 없는 옛 결과 — 문서가 그대로면 그대로 · 아니면 이어 쓴다
    assert TM.judge(_stage1(), TID, stored=old)["reuse"]["why"].startswith("판정을 이어 씀") and TM.judge(_stage1(), TID, stored=old, same_doc=True)["reuse"]["why"] == "문서가 그대로"
    fewer = {**llm, "cells": llm["cells"][:-1]}                                  # 판정 뒤에 칸이 하나 생긴 꼴 — 있던 칸은 그대로 · 새 칸은 띠의 자리로
    got = TM.judge(_stage1(), TID, stored=fewer, same_doc=True)
    assert got["reuse"] == {"ok": True, "why": "판정을 이어 씀 — 판정 때 있던 칸 26 · 그 뒤 생긴 칸 1"} and _by(got)[FOOT]["role"] == "field"


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
    assert old["reuse"] == {"ok": True, "why": "판정을 이어 씀 — 판정 때 있던 칸 26 · 그 뒤 생긴 칸 1"} and _by(old)[LABOR]["role"] == "rowhead"   # 가를 수 없는 그 칸만 띠의 자리로(헤더 열) — 나머지는 이어 쓴다


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


def _cells(drop=(), add=(), edit=None):
    """CELLS 에서 줄(drop — 판정 때의 행 번호)을 지우고 아래 줄을 당긴 표 + 더한 칸(add — 지금 자리의 (칸 id, 행, 열, 행 병합, 열 병합, 음영, 문단)) · edit = {칸 id: [문단 글…]}."""
    out = []
    for i, (r, c, rs, cs, fill, paras) in enumerate(CELLS):
        if r in drop:
            continue
        cid = f"c{101 + i}"
        out.append((cid, r - sum(1 for d in drop if d < r), c, rs, cs, fill, (edit or {}).get(cid, paras)))
    return out + list(add)


def test_judgment_is_carried_when_the_table_changes_after_it():
    """판정 이어 쓰기(2026-11-23 사용자 「LLM 판정이 되면 그게 유지되어야지」 — 이관 목적 문서의 연구개발비 표: 빈 양식일 때 판정 → 내용 반영으로 값이 들어옴 → 빈 필드 제거로 줄이 지워짐):
    판정 때 있던 칸은 그 역할 그대로다 — 음영 칸에 값이 들어와도, 줄이 지워져 자리가 당겨져도. 판정 뒤에 생긴 줄은 그 띠의 헤더 행 · 열 수로."""
    blank = {f"c{101 + i}": [""] for i, x in enumerate(CELLS) if x[0] in (2, 3, 4) and x[1] >= 1}          # 빈 양식 — 값 칸이 다 비었다
    shade = [(f"c{101 + i}", r, c, rs, cs, SHADE if (r in (2, 3, 4) and c >= 3) else fill, blank.get(f"c{101 + i}", paras)) for i, (r, c, rs, cs, fill, paras) in enumerate(CELLS)]
    stored = HT.build(_stage1(cells=shade), use_llm=False)["tables"][0]                                     # 3 · 4열과 합계 열을 칠해 둔 빈 양식의 판정
    assert {c["role"] for c in stored["cells"] if c["row"] in (2, 3, 4) and c["col"] >= 1} == {"field"}
    keep = copy.deepcopy(stored)
    filled = [(cid, r, c, rs, cs, fill, ["1,234"] if cid in blank else paras) for cid, r, c, rs, cs, fill, paras in shade]   # 내용 반영 — 값이 들어옴
    j = TM.judge(_stage1(cells=filled), TID, stored=stored)
    assert j["source"] == "stage3" and j["reuse"] == {"ok": True, "why": "판정을 이어 씀 — 판정 때 있던 칸 27"}
    assert {x["role"] for x in j["table"]["cells"] if x["row"] in (2, 3, 4) and x["col"] >= 1} == {"field"}  # 음영 칸에 값이 들어와도 필드
    assert [(tuple(b["rows"]), b["headerRows"], b["headerCols"]) for b in j["subs"]] == [(tuple(s["rows"]), s["headerRows"], s["headerCols"]) for s in stored["subtables"]]
    assert _by(j)[LABOR_CASH]["num"] == 1234 and stored == keep                                              # 글 · 숫자는 지금 것 · 저장된 결과는 안 고친다
    pruned = [(cid, r - (1 if r > 3 else 0), c, rs, cs, fill, paras) for cid, r, c, rs, cs, fill, paras in filled if r != 3]   # 빈 필드 제거 — 「재료비」 줄이 지워지고 아래가 당겨짐
    j = TM.judge(_stage1(cells=pruned), TID, stored=stored)
    assert j["reuse"] == {"ok": True, "why": "판정을 이어 씀 — 판정 때 있던 칸 21 · 없어진 칸 6"} and j["table"]["rows"] == 5
    assert (_by(j)[FOOT]["row"], _by(j)[FOOT]["role"]) == (3, _by(TM.judge(_stage1(cells=filled), TID, stored=stored))[FOOT]["role"])   # 당겨진 줄도 제 역할
    assert {x["role"] for x in j["table"]["cells"] if x["row"] in (2, 3) and x["col"] >= 1} == {"field"}
    assert [b["kind"] for b in j["subs"]] == [s["kind"] for s in stored["subtables"]] and j["subs"][0]["headerRows"] == 2 and j["subs"][0]["headerCols"] == 1
    grown = [(cid, r + (1 if r > 2 else 0), c, rs, cs, fill, paras) for cid, r, c, rs, cs, fill, paras in filled]               # 줄 늘리기 — 「인건비」 아래에 새 줄
    grown += [("n1", 3, 0, 1, 1, None, ["연구활동비"])] + [(f"n{2 + k}", 3, 1 + k, 1, 1, SHADE if k >= 2 else None, ["500"]) for k in range(5)]
    j = TM.judge(_stage1(cells=grown), TID, stored=stored)
    assert j["reuse"] == {"ok": True, "why": "판정을 이어 씀 — 판정 때 있던 칸 27 · 그 뒤 생긴 칸 6"}
    by = _by(j)
    assert by["n1"]["role"] == "rowhead" and {by[f"n{2 + k}"]["role"] for k in range(5)} == {"field"}       # 새 줄 — 헤더 열은 행헤더 · 값 열은 필드(음영이어도)
    assert by[LABOR_CASH]["role"] == "field" and by["n2"]["rowPath"] == ["n1"]
    assert TM.judge(_stage1(), TID, stored={"cells": [], "subtables": []})["source"] == "draft"             # 이을 칸이 없으면 초안


def _drafted(s1):
    """오늘의 초안이 얹힌 표(collect 꼴) · 격자 · 초안 띠 · 자료 열쇠 — carry_over 가 받는 것."""
    tb = next(t for t in HT.collect(s1) if t["id"] == TID)
    bs, occ = HT.draft(tb)
    return tb, occ, bs, HT.input_key(tb, occ, bs)


def test_carry_over_is_the_judge_reuse_step_and_leaves_the_draft_alone_when_nothing_carries():
    """carry_over(spec_작업 ② §22 「구현 계약」 22-4) = judge 의 「그대로 다시 쓰기 · 아니면 칸마다 이어 쓰기」 를 밖에서 부르는 것 — 3단계 실행이 같은 셈으로 앞 LLM 판정을 이어 쓴다.
    이을 것이 없으면 None 이고 표의 칸 역할은 초안 그대로다(건드린 채 돌려주지 않는다). 저장된 결과는 고치지 않는다."""
    llm = copy.deepcopy(_stored())
    next(c for c in llm["cells"] if c["id"] == FOOT).update(role="field", changed=True, reason="값으로 읽힘")   # LLM 이 왼쪽 아래 「합계」 를 필드로 고쳤다
    keep = copy.deepcopy(llm)
    role = lambda tb, cid: next(x["role"] for x in tb["cells"] if x["id"] == cid)  # noqa: E731
    tb, occ, bs, key = _drafted(_stage1())
    bands, how = TM.carry_over(tb, occ, bs, llm, key)                               # 표의 자료가 그대로 — 그대로 다시 쓴다
    assert how == {"mode": "same"} and role(tb, FOOT) == "field" and [b["id"] for b in bands] == [s["id"] for s in llm["subtables"]]
    tb, occ, bs, key = _drafted(_stage1({LABOR_CASH: ["999"]}))                     # 칸 글이 바뀜 — 칸마다 이어 쓴다
    bands, how = TM.carry_over(tb, occ, bs, llm, key)
    assert how == {"mode": "carried", "kept": 27, "new": 0, "gone": 0, "bands": "stored"} and role(tb, FOOT) == "field"
    tb, occ, bs, key = _drafted(_stage1({LABOR_CASH: ["999"]}))
    old = {k: v for k, v in llm.items() if k != "inputKey"}                         # 열쇠가 없는 옛 결과 — 문서가 그대로라고 알려 주면 그대로
    assert TM.carry_over(tb, occ, bs, old, key, same_doc=True)[1] == {"mode": "same"} and role(tb, FOOT) == "field"
    for nothing in (None, {}, {"cells": [], "subtables": []}, {"cells": [{"id": "zz", "role": "field"}], "subtables": []}):   # 이을 것이 없다
        tb, occ, bs, key = _drafted(_stage1())
        draft = [(x["id"], x["role"]) for x in tb["cells"]]
        assert TM.carry_over(tb, occ, bs, nothing, key) is None and [(x["id"], x["role"]) for x in tb["cells"]] == draft and role(tb, FOOT) == "rowhead"
    assert llm == keep
    for edit in (None, {LABOR_CASH: ["999"]}):                                      # judge 의 자동 역할 = carry_over 가 얹은 역할
        tb, occ, bs, key = _drafted(_stage1(edit))
        TM.carry_over(tb, occ, bs, llm, key)
        assert {x["id"]: x["role"] for x in tb["cells"]} == {i: x["auto"] for i, x in _by(TM.judge(_stage1(edit), TID, stored=llm)).items()}
