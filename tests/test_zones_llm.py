"""편집 구역 — LLM 검토(app/zones_llm.py · app/zones_api.py 의 LLM 끝점 — spec_구역 ② §8 「LLM 검토 — 스크립트가 못 정한 것」).
후보 고르기(근거가 다름 · 기관 모름 · 낌새 있는 표 · 혼자 빠진 표 — 지정된 블록과 깨끗이 읽힌 블록은 빠진다 · 후보마다 기준별로 바꿀 수 있는지 editable) ·
답 검증(모르는 id·열쇠 · 범위 밖 · 바꿀 수 없는 기준(editable false)에 적은 답 → 버림 — astra 결과 검토 P1-3 의 반례를 read → build → candidates → check 로) ·
반영(by llm · 사람 지정은 안 건드림 · keep 은 지정을 안 만듦) · 호출 앞뒤의 차례 검사(409) · LLM 지정 모두 해제 · 끝점 응답 꼴 · 「지침」 · 로그 · 에이전트 등록.
**실제 LLM 은 부르지 않는다** — `llm.call` 을 흉내로 바꾼다(끝점 시험) · `call=` 로 준다(순수 시험). 끝점 시험의 자료는 test_zones_api 와 같다(gather_data)."""
import json

import pytest
from fastapi.testclient import TestClient

import gather_data as D
from app import agent_settings as AS
from app import agents as AG
from app import merge_api as MA
from app import merge_gather_api as GA
from app import merge_guides as MG
from app import server, works
from app import task_options as TO
from app import work_logs as WL
from app import zones as Z
from app import zones_api as ZA
from app import zones_llm as ZL
from app.division_profiles.rnd import core
from test_merge_gather_api import _master, _upload, _why
from test_zones_api import KEYS, _ok, _post, _zones

J1, J2, LEAD = D.J1, D.J2, D.LEAD
ORGS = [{"key": LEAD, "name": "㈜인텍", "role": "lead"}, {"key": J1, "name": J1, "role": "joint"}, {"key": J2, "name": J2, "role": "joint"}]
CALL = {"backend": "fake", "model": "m-fake", "effort": "medium", "ms": 7, "costUsd": 0.02, "error": None}


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")   # 흉내를 안 건 시험이 실제 LLM 을 부르지 않게


@pytest.fixture
def client():
    server.DOCS.clear()
    for box in (GA._MEM, GA._BLOB, GA._FRAMES, GA._LINKS, GA._JUDGE, GA._PLANS, GA._DROPS, GA._ZONES, ZA._AUTO, ZA._LLM_RUN, ZA._LLM_LAST, TO._MEMORY):
        box.clear()
    return TestClient(server.app)


# ---- 손으로 만든 자료 -------------------------------------------------------------------------------------------------

def _p(i, text=""):
    return {"id": i, "type": "paragraph", "text": text}


def _tbl(tid, rows):
    """표 블록 — rows[r][c] = 글 | (글, 행 병합, 열 병합) | None(다른 칸이 덮은 자리). 칸 id = <표 id>.<행>.<열>."""
    cells = []
    for r, row in enumerate(rows):
        for c, x in enumerate(row):
            if x is None:
                continue
            text, rs, cs = x if isinstance(x, tuple) else (x, 1, 1)
            cells.append({"id": f"{tid}.{r}.{c}", "row": r, "col": c, "rowSpan": rs, "colSpan": cs, "text": text})
    return {"id": tid, "type": "table", "nRows": len(rows), "nCols": max(len(r) for r in rows), "cells": cells}


def _lab(org=None, stage=None, year=None, kind="org", ev="group", why=None):
    """자동 라벨 하나(`zones.read` 가 내는 꼴)."""
    kind = kind if org is not None or kind in ("unknown", "conflict") else None
    vals = {"org": kind, "stage": stage, "year": year}
    lab = {"org": org, "orgKind": kind, "stage": stage, "year": year, "src": {d: "auto" for d in Z.DIMS if vals[d] is not None}, "ev": {d: ev for d in Z.DIMS if vals[d] is not None}}
    return {**lab, "why": why} if why else lab


def _info(blocks, auto=None, stages=(2,), path=None):
    """손으로 만든 info(`zones.read` 의 꼴) — 블록 차례 그대로."""
    text = {b["id"]: (" | ".join(c["text"] for c in b["cells"][:8] if c["text"]) if b["type"] == "table" else b["text"])[:Z.TEXT_MAX] for b in blocks}
    return {"order": [b["id"] for b in blocks], "kinds": {b["id"]: "tbl" if b["type"] == "table" else "p" for b in blocks},
            "cellsOf": {b["id"]: [c["id"] for c in b["cells"]] for b in blocks if b["type"] == "table"}, "auto": dict(auto or {}), "path": dict(path or {}), "text": text, "orgs": ORGS, "stages": list(stages)}


def _s3(blocks, roles, guides=()):
    """3단계 표 구조(칸의 역할만) — roles{표 id: rows 와 같은 꼴의 역할 글(h = rowhead · c = colhead · k = corner · f = field · t = title)}."""
    name = {"h": "rowhead", "c": "colhead", "k": "corner", "f": "field", "t": "title"}
    out = []
    for b in blocks:
        if b["id"] in roles:
            out.append({"id": b["id"], "cells": [{"id": c["id"], "role": name[roles[b["id"]][c["row"]][c["col"]]]} for c in b["cells"]]})
    return {"tables": out, "tempTables": [{"id": g, "why": "guide"} for g in guides]}


def _mark(ids, label, by="user", mid="m1"):
    return {"id": mid, "ids": list(ids), "label": dict(label), "note": "", "by": by, "at": "2026-11-17T10:00:00"}


def _cands(blocks, auto=None, marks=(), tables=None, stages=(2,), path=None):
    info = _info(blocks, auto, stages, path)
    return ZL.candidates(info, Z.build(info, list(marks), [], ["org"]), blocks, tables), info


# ---- 후보 고르기 ------------------------------------------------------------------------------------------------------

def test_candidates_are_conflicts_unknowns_and_never_marked_or_cleanly_read_blocks():
    why = {"byNo": J2, "byName": [J1]}
    blocks = [_p("p1", "1. 개요"), _p("p2", f"[공동연구개발기관1({J1})]"), _p("p3", " o 개발 목표 " + "가" * 200), _p("p4", "[공동연구개발기관N(기관명 기입)]"), _p("p5", ""),
              _p("p6", f"[주관연구개발기관({LEAD})]"), _p("p7", " o 주관의 글"), _p("p8", "[기관 모름인데 사람이 정한 줄]"), _p("p9", "[기관 모름인데 LLM 이 정한 줄]"), _p("p10", "끝 글")]
    auto = {"p2": _lab(kind="conflict", why=why), "p3": _lab(kind="conflict", year=1, stage=1, why=why), "p4": _lab(kind="unknown"), "p5": _lab(kind="unknown"),
            "p6": _lab(LEAD), "p7": _lab(LEAD, stage=1, year=2), "p8": _lab(kind="unknown"), "p9": _lab(kind="conflict", why=why)}
    marks = [_mark(["p8"], {"org": J1}), _mark(["p9"], {"org": J2}, by="llm", mid="m2")]
    got, info = _cands(blocks, auto, marks, path={"p3": ["1. 개요", "x" * 60, "a", "b", "c", "d"]})
    assert [(c["id"], c["type"], c["kind"]) for c in got] == [("p2", "paragraph", "conflict"), ("p3", "paragraph", "conflict"), ("p4", "paragraph", "unknown"), ("p5", "paragraph", "unknown")]
    assert ZL.kinds(got) == {"conflict": 2, "unknown": 2, "hint": 0, "alone": 0}
    c2, c3, c4, c5 = got
    assert c2["read"] == {"orgKind": "conflict", "ev": {"org": "group"}, "why": why} and c2["text"] == f"[공동연구개발기관1({J1})]" and "signs" not in c2   # 두 근거를 같이
    assert c3["read"] == {"orgKind": "conflict", "stage": 1, "year": 1, "ev": {"org": "group", "stage": "group", "year": "group"}, "why": why}
    assert len(c3["text"]) == ZL.PARA_LEN and c3["text"].endswith("…") and c3["path"] == ["a", "b", "c", "d"] and "path" not in c2   # 글은 줄여서 · 윗 제목은 안쪽 넷
    assert c2["prev"] == {"text": "1. 개요"} and c2["next"] == {"text": blocks[2]["text"].strip()[:ZL.NEAR_LEN - 1] + "…", "org": "conflict", "stage": 1, "year": 1}   # 앞뒤 블록의 구역
    assert c4["read"] == {"orgKind": "unknown", "ev": {"org": "group"}} and c4["next"] == {"text": f"[주관연구개발기관({LEAD})]", "org": LEAD}   # 빈 문단은 건너뛴다
    assert c5["text"] == "" and c5["prev"]["text"].startswith("[공동연구개발기관N") and c5["next"]["org"] == LEAD   # 빈 문단도 후보(띠가 끊기지 않게) — 앞뒤는 글 있는 블록
    # 기준별로 바꿀 수 있는지 — 기관은 정해지지 않았으니(확인 필요 · 모름) 정할 수 있고, 단계·차년도는 비어 있을 때만
    assert c2["editable"] == c4["editable"] == {"org": True, "stage": True, "year": True} and c3["editable"] == {"org": True, "stage": False, "year": False}
    # 사람이 지정한 블록(p8) · 앞선 검토가 지정한 블록(p9) · 깨끗이 읽힌 블록(p6·p7) · 값이 없는 문단(p1·p10)은 후보가 아니다
    assert not {"p1", "p6", "p7", "p8", "p9", "p10"} & {c["id"] for c in got}
    # 프로젝트 구성 값이 없으면 고를 것이 없다
    assert ZL.candidates({**info, "orgs": []}, Z.build(info, [], [], ["org"]), blocks) == [] and ZL.candidates({**info, "stages": []}, {}, blocks) == [] and ZL.candidates(None, None, None) == []


def test_tables_with_a_hint_are_candidates_and_tables_that_cannot_be_one_orgs_are_not():
    tag = _tbl("ta", [["연구개발기관명", "GND 대학교"], ["용역명", "가공"], ["용역 필요성", "가" * 90]])                  # 이름표 칸 옆의 값이 과제 기관 이름이 아니다
    name = _tbl("tn", [["구분", "내용"], ["소속", f"㈜ {J1}"], ["비고", f"{J1} 실험동"]])                                # 이름표 칸 없이 짧은 칸에 과제 기관 이름 하나
    year = _tbl("ty", [["(단계)구입연차", "1차년도(2026년)", "품명", "레이저"]])                                         # 단계가 둘인데 「1차년도」 만 — 스크립트가 못 읽는다
    col = _tbl("tc", [["기관명", "역할"], [("GND", 2, 1), "설계"], [None, "제작"]])                                      # 열 머리 아래 세로로 합친 이름 하나
    blank = _tbl("tb", [["연구개발기관명", ""], ["용역명", ""]])                                                          # 빈 양식
    rows = _tbl("tr", [["기관명", "역할"], ["GND", "설계"], ["HJK", "제작"]])                                             # 행마다 값이 다르다
    two = _tbl("t2", [["구분", J1, J2], ["예산", "1", "2"]])                                                              # 과제 기관 이름이 둘 — 기관을 견주는 표
    read = _tbl("tq", [["연구개발기관명", J1], ["용역명", "가공"]])                                                       # 스크립트가 읽은 표
    cells = _tbl("tk", [["기관명", "역할"], [J1, "설계"], [J2, "제작"]])                                                  # 스크립트가 행마다 읽은 표(칸에 기관)
    guide = _tbl("tg", [["작성 요령", f"{J1} 처럼 적는다"], ["소속", J1]])                                                # 작성요령 표
    head = _tbl("th", [["연차", "1", "2"], ["예산", "10", "20"]])                                                          # 차년도마다 열이 있는 머리 행
    none_ = _tbl("tx", [["연구개발기관명", "해당 없음"], ["수행기관", "(기관명 기입)"], ["기관명", "○○○"]])                # 값이 아닌 글
    blocks = [_p("p1", "<표 1> 외주 용역"), tag, name, year, col, blank, rows, two, read, cells, guide, head, none_]
    auto = {"tq": _lab(J1, ev="cell"), "tk.1.0": _lab(J1, ev="cell"), "tk.1.1": _lab(J1, ev="cell"), "tk.2.0": _lab(J2, ev="cell")}
    s3 = _s3(blocks, {"ta": ["hf", "hf", "hf"], "tn": ["cc", "hf", "hf"], "ty": ["hfhf"], "tc": ["kc", "hf", "hf"], "tb": ["hf", "hf"], "tr": ["kc", "hf", "hf"], "t2": ["kcc", "hff"],
                      "tq": ["hf", "hf"], "tk": ["kc", "hf", "hf"], "tg": ["hf", "hf"], "th": ["hff", "hff"], "tx": ["hf", "hf", "hf"]}, guides=["tg"])
    got, info = _cands(blocks, auto, tables=s3, stages=(2, 2))
    by = {c["id"]: c for c in got}
    assert [(c["id"], c["kind"], c["signs"]) for c in got] == [("ta", "hint", ["orgTag"]), ("tn", "hint", ["orgName"]), ("ty", "hint", ["yearTag"]), ("tc", "hint", ["orgTag"])]
    assert ZL.kinds(got) == {"conflict": 0, "unknown": 0, "hint": 4, "alone": 0} and all(c["type"] == "table" and "read" not in c for c in got)
    assert all(c["editable"] == {"org": True, "stage": True, "year": True} for c in got)   # 값이 하나도 안 붙은 낌새 후보 — 셋 다 정할 수 있다
    a = by["ta"]
    assert a["size"] == "3x2" and a["tags"] == [{"tag": "연구개발기관명", "right": "GND 대학교", "below": ["용역명", "용역 필요성"]}] and a["head"] == ["연구개발기관명", "GND 대학교"] and a["side"] == ["용역명", "용역 필요성"]
    assert a["prev"] == {"text": "<표 1> 외주 용역"} and "names" not in a
    assert by["tn"]["names"] == [{"org": J1, "n": 2}] and "tags" not in by["tn"]
    assert by["ty"]["tags"] == [{"tag": "(단계)구입연차", "right": "1차년도(2026년)"}]
    assert by["tc"]["tags"] == [{"tag": "기관명", "right": "역할", "below": ["GND"]}]
    long = _tbl("tl", [["연구개발기관명", "GND"]] + [[f"항목 {r} " + "나" * 60, "다" * 60, "라", "마"] for r in range(30)])
    (c,), _ = _cands([long], tables=_s3([long], {"tl": ["hf"] + ["hfff"] * 30}))
    shown = [c["tags"][0]["tag"], c["tags"][0]["right"], *c["tags"][0]["below"], *c["head"], *c["side"]]
    assert len(shown) <= ZL.CELLS_MAX and all(len(x) <= ZL.CELL_LEN for x in shown) and len(c["side"]) == ZL.SIDE_MAX and len(c["tags"][0]["below"]) == ZL.BELOW_MAX   # 표마다 40칸 · 칸마다 40자까지
    # 단계가 하나면 「1차년도(2026년)」 은 스크립트가 읽는 값이라 낌새가 아니다 · 표 구조(칸의 역할)가 없으면 이름표 칸의 값은 낌새로 치지 않는다(이름은 그대로 본다)
    assert [c["id"] for c in _cands(blocks, auto, tables=s3, stages=(2,))[0]] == ["ta", "tn", "tc"]
    assert [(c["id"], c["signs"]) for c in _cands(blocks, auto, stages=(2, 2))[0]] == [("tn", ["orgName"]), ("tg", ["orgName"])]
    # 사람이 지정한 표는 낌새가 있어도 후보가 아니다
    assert "ta" not in {c["id"] for c in _cands(blocks, auto, [_mark(["ta"], {"org": None})], tables=s3, stages=(2, 2))[0]}


def test_a_table_left_alone_among_same_shaped_tables_and_a_table_whose_cells_disagree():
    shape = lambda tid, org, item: _tbl(tid, [["연구개발기관명", org, "구입연차", "1차년도"], ["품명", "규격", "수량", "금액"], [item, "A4", "1", "100"]])  # noqa: E731
    a, b, c, d = shape("t1", J1, "프린터"), shape("t2", "", "복합기"), shape("t3", J1, "스캐너"), shape("t4", "", "모니터")
    other = _tbl("t9", [["구분", "내용"], ["가", "나"]])
    blocks = [a, _p("p1", "사이 글"), b, c, other, d]
    auto = {"t1": _lab(J1, stage=1, year=1, ev="cell"), "t3": _lab(J1, stage=1, year=1, ev="cell")}
    got, info = _cands(blocks, auto)
    text = lambda i: ZL._short(info["text"][i], ZL.NEAR_LEN)  # noqa: E731
    assert [(x["id"], x["kind"]) for x in got] == [("t2", "alone"), ("t4", "alone")] and "signs" not in got[0]   # 같은 꼴의 이웃(있는 쪽 모두)이 기관이 붙었는데 저만 빠졌다 — 끝의 표(t4)는 이웃이 하나
    assert got[0]["like"] == {"prev": {"org": J1, "text": text("t1")}, "next": {"org": J1, "text": text("t3")}, "n": 4} and got[1]["like"] == {"prev": {"org": J1, "text": text("t3")}, "n": 4}
    assert got[0]["prev"] == {"text": "사이 글"} and got[0]["next"] == {"text": text("t3"), "org": J1, "stage": 1, "year": 1} and got[0]["size"] == "3x4" and "read" not in got[0]
    assert [x["id"] for x in _cands(blocks, {**auto, "t2": _lab(J1, ev="cell")})[0]] == ["t4"]
    # 이웃 가운데 안 붙은 표가 있으면 아니다 · 같은 꼴에서 기관이 붙은 표가 둘은 돼야 한다 · 차년도만 붙은 표도 기관은 빠진 것이다(이웃의 기관이 서로 달라도 후보 — 고르는 것은 LLM)
    alone = lambda bs, au: [x["id"] for x in _cands(bs, au)[0] if x["kind"] == "alone"]  # noqa: E731
    assert alone(blocks, {"t1": auto["t1"]}) == [] and alone([a, b], {"t1": auto["t1"]}) == [] and alone([a, b, c], auto) == ["t2"]
    assert _cands(blocks, {"t1": auto["t1"], "t3": _lab(J2, ev="cell"), "t2": _lab(kind=None, year=1, stage=1)})[0][0]["like"]["next"]["org"] == J2
    far = [a, *[_p(f"q{n}", "글") for n in range(ZL.NEAR_SPAN)], b, c]   # 이웃이 너무 멀면(앞 표가 80블록 밖) 아니다
    assert _cands(far, auto)[0] == []
    # 표의 기관은 묶음이 읽었는데(인텍) 칸은 다른 이름을 말한다 — 근거가 서로 다른 칸이 있는 표
    t = _tbl("tk", [["직장", "기관명", "부서"], ["현재", J1, "연구소"], ["이전", J1, "개발팀"]])
    why = {"byGroup": LEAD, "byCell": [J1]}
    auto = {"tk": _lab(LEAD), **{f"tk.{r}.{k}": _lab(kind="conflict", why=why) for r in (1, 2) for k in range(3)}}
    (x,), _ = _cands([t], auto)
    assert (x["kind"], x["signs"], x["read"]) == ("conflict", ["cells"], {"orgKind": "org", "org": LEAD, "ev": {"org": "group"}})
    assert x["cells"] == [{"r": 1, "text": "현재", "why": why}, {"r": 2, "text": "이전", "why": why}] and x["cellsN"] == 6 and x["names"] == [{"org": J1, "n": 2}]   # 행마다 한 줄
    assert x["editable"] == {"org": True, "stage": True, "year": True}   # 칸에서 **기관** 근거가 엇갈린다 — 표의 기관(인텍)도 다시 고를 수 있다
    assert got[0]["editable"] == {"org": True, "stage": True, "year": True}   # 혼자 빠진 표(기관 없음)


def test_only_the_dims_whose_evidence_disagrees_or_is_empty_can_be_changed():
    """astra 결과 검토 P1-3: 표의 기관은 깨끗이 읽혔고 칸에 **차년도** 근거만 엇갈린 표 — 「칸의 근거가 다른 표」 라고 기관을 바꿀 권한을 주면 안 된다. 기준마다 따로 본다(editable)."""
    t = _tbl("tk", [["직장", "기관명", "부서"], ["현재", J1, "연구소"], ["이전", J1, "개발팀"]])
    info = _info([t])
    y_why = {"year": {"byGroup": 1, "byCell": 2}}
    cell = {**_lab(LEAD, stage=1), "why": y_why}   # 칸: 차년도만 엇갈려 비워 둠(기관·단계는 그대로)
    view = lambda table, c=cell: {"blocks": {"tk": table} if table else {}, "cells": {"tk": {"tk.1.0": c}}, "marks": []}  # noqa: E731
    (x,) = ZL.candidates(info, view(_lab(LEAD, stage=1)), [t])
    assert (x["kind"], x["signs"], x["editable"]) == ("conflict", ["cells"], {"org": False, "stage": False, "year": True})   # 기관·단계는 읽힌 값 — 빈 차년도만
    assert x["cells"] == [{"r": 1, "text": "현재", "why": y_why}] and x["read"] == {"orgKind": "org", "org": LEAD, "stage": 1, "ev": {"org": "group", "stage": "group"}}
    assert ZL.candidates(info, view(_lab(LEAD, stage=1, year=1)), [t]) == []   # 표의 값이 모두 읽혔다 — 바꿀 수 있는 기준이 없어 후보가 아니다(보내도 LLM 이 못 바꾼다)
    # 칸의 엇갈림이 기관의 것이면(확인 필요 · why 에 기관 근거) 표의 기관도 고를 수 있다 — 차년도·단계의 것만이면 못 고른다
    org_why = {"byGroup": LEAD, "byCell": [J1]}
    for c, can in (({**_lab(kind="conflict", stage=1, year=1), "why": org_why}, True), ({**_lab(LEAD, stage=1, year=1), "why": {"byPath": LEAD, "byCell": [J1]}}, True),
                   ({**_lab(LEAD), "why": {"stage": {"byGroup": 1, "byCell": 2}, "year": {"byGroup": 1, "byCell": 3}}}, False)):
        got = ZL.candidates(info, view(_lab(LEAD, stage=1, year=1), c), [t])
        assert [g["editable"] for g in got] == ([{"org": True, "stage": False, "year": False}] if can else []), c
    # 기관이 안 붙은 표에 차년도만 엇갈린 칸 — 기관의 낌새(짧은 칸의 이름 하나)가 있으면 기관도 정할 수 있고, 없으면 못 정한다
    (x,) = ZL.candidates(info, view(None, {**_lab(kind=None, stage=1), "why": y_why}), [t])
    assert (x["kind"], x["signs"], x["editable"]) == ("conflict", ["cells", "orgName"], {"org": True, "stage": True, "year": True}) and "read" not in x
    plain = _tbl("tk", [["구분", "연차", "내용"], ["가", "2", "나"]])
    (x,) = ZL.candidates(_info([plain]), view(None, {**_lab(kind=None, stage=1), "why": y_why}), [plain])
    assert (x["kind"], x["signs"], x["editable"]) == ("conflict", ["cells"], {"org": False, "stage": True, "year": True})
    # 값이 하나도 없고 why 만 있는 라벨(차년도·단계가 엇갈려 비워 둔 것)도 후보다 — 기관은 못 정한다 · 키가 빠진 라벨에도 안 깨진다
    bare = {"org": None, "orgKind": None, "stage": None, "year": None, "src": {}, "ev": {}, "why": {"stage": {"byGroup": 1, "byCell": 2}, "year": {"byGroup": 1, "byCell": 3}}}
    p = _p("p1", "문단")
    (x,) = ZL.candidates(_info([p], stages=(2, 2)), {"blocks": {"p1": bare}, "cells": {}, "marks": []}, [p])
    assert (x["kind"], x["editable"], x["read"]) == ("conflict", {"org": False, "stage": True, "year": True}, {"why": bare["why"]})
    (x,) = ZL.candidates(info, {"blocks": {"tk": {"why": y_why}}, "cells": {"tk": {"tk.1.0": {"why": y_why}, "tk.9.9": {}}}}, [t])
    assert (x["kind"], x["read"], x["cellsN"]) == ("conflict", {"why": y_why}, 1)


def test_the_reviews_counterexample_from_read_to_check():
    """astra 결과 검토 P1-3 의 반례를 `read → build → candidates → check` 로 잇는다: 차년도만 엇갈린 표에서 기관을 바꾸는 답은 버려지고 · 같은 표의 차년도를 정하는 답은 받고 ·
    기관이 엇갈린(확인 필요) 표의 기관은 받는다."""
    values = core.norm_values({"stages": [2], "orgs": {"lead": "한국선급", "joint": ["가나대"]}})
    kr, gn = "한국선급", "가나대"

    def deep(tid, rows):   # 칸마다 문단 블록이 든 표(묶음 찾기가 칸 안의 문단을 읽는다)
        b = _tbl(tid, rows)
        for c in b["cells"]:
            c["blocks"] = [_p(c["id"] + ".p", c["text"])]
        return b
    blocks = [deep("t1", [["기관명", (kr, 1, 2), None], ["구분", "연차", "내용"], ["1차년도", "2", "가"], ["2차년도", "1", "나"]]),   # 표의 기관 = 한국선급(깨끗) · 행의 차년도는 묶음(1·2)과 「연차」 칸(2·1)이 엇갈린다
              _p("p1", "사이 글"),
              deep("t2", [["소유권자", "수행기관", "내용"], [kr, gn, "가"]])]                                                          # 한 행의 기관 열 둘이 서로 다른 기관 — 칸의 기관이 확인 필요
    info = Z.read({"blocks": blocks, "values": values, "graph": None, "tables": None, "hints": [], "prior": None})
    view = Z.build(info, [], [], ["org", "year"])
    assert (view["blocks"]["t1"]["orgKind"], view["blocks"]["t1"]["org"], view["blocks"]["t1"]["year"]) == ("org", kr, None) and "why" not in view["blocks"]["t1"]
    odd = [c for c in view["cells"]["t1"].values() if c.get("why")]
    assert odd and all(set(c["why"]) == {"year"} and c["year"] is None for c in odd)   # 칸에는 차년도 근거만 엇갈린다
    assert all(c["orgKind"] == "conflict" for c in view["cells"]["t2"].values())
    cands = ZL.candidates(info, view, blocks)
    by = {c["id"]: c for c in cands}
    assert set(by) == {"t1", "t2"} and all(c["kind"] == "conflict" and c["signs"] == ["cells"] for c in cands)
    assert by["t1"]["editable"] == {"org": False, "stage": True, "year": True} and by["t2"]["editable"] == {"org": True, "stage": True, "year": True}
    pl = ZL.payload(info, cands)
    assert json.loads(ZL.prompt(pl).split("\n\n## 자료(JSON)\n", 1)[1])["candidates"][0]["editable"] == by["t1"]["editable"] and "editable 이 false 인 기준은 keep 만" in ZL.CONTRACT   # LLM 도 안다
    row = lambda i, org="keep", year="keep": {"id": i, "org": org, "stage": "keep", "year": year, "reason": "까닭"}  # noqa: E731
    # ① 차년도만 엇갈린 표의 기관을 바꾸는 답 → 버려진다(지정이 안 생긴다)
    items, dropped = ZL.check({"items": [row("t1", gn)]}, pl)
    assert [(i["id"], i["label"], i["keep"]) for i in items] == [("t1", {}, True)] and dropped == [{"id": "t1", "dim": "org", "value": gn, "why": ZL.FIXED}]
    assert ZL.check({"items": [row("t1", "none")]}, pl) == ([{"id": "t1", "label": {}, "reason": "까닭", "keep": True}], [{"id": "t1", "dim": "org", "value": "none", "why": ZL.FIXED}])
    assert ZL.check({"items": [row("t1", kr)]}, pl) == ([{"id": "t1", "label": {}, "reason": "까닭", "keep": True}], [])   # 스크립트 값과 같은 답은 그대로(버린 것으로 세지 않는다)
    # ② 같은 표의 차년도를 정하는 답 → 받는다 · 기관을 함께 바꾸려 하면 그 기준만 버리고 차년도는 받는다
    assert ZL.check({"items": [row("t1", year="1")]}, pl) == ([{"id": "t1", "label": {"year": 1}, "reason": "까닭", "keep": False}], [])
    items, dropped = ZL.check({"items": [row("t1", gn, "2")]}, pl)
    assert [(i["label"], i["keep"]) for i in items] == [({"year": 2}, False)] and [(d["dim"], d["why"]) for d in dropped] == [("org", ZL.FIXED)]
    done = Z.build(info, [Z.mark_make(["t1"], items[0]["label"], "까닭", "llm")], [], ["org", "year"])["blocks"]["t1"]
    assert (done["org"], done["year"], done["src"]["org"], done["src"]["year"]) == (kr, 2, "auto", "mark")   # 지정으로 적어도 표의 기관은 스크립트 값 그대로
    # ③ 기관이 엇갈린 표 → 기관을 받는다(값 · 기관 없음)
    assert ZL.check({"items": [row("t2", gn)]}, pl) == ([{"id": "t2", "label": {"org": gn}, "reason": "까닭", "keep": False}], [])
    assert ZL.check({"items": [row("t2", "none")]}, pl)[1] == []   # 기관이 안 붙은 표의 none — 값이 안 바뀌어 그대로
    whole = [deep("t3", [["연구개발기관명", kr], ["기관명", gn], ["용역명", "가공"]])]   # 표 전체로 읽은 기관이 서로 다르다 — 표의 기관이 확인 필요
    info = Z.read({"blocks": whole, "values": values, "graph": None, "tables": None, "hints": [], "prior": None})
    (c,) = ZL.candidates(info, Z.build(info, [], [], ["org"]), whole)
    assert (c["kind"], c["read"]["orgKind"], c["editable"]["org"]) == ("conflict", "conflict", True)
    pl = ZL.payload(info, [c])
    assert ZL.check({"items": [row("t3", gn)]}, pl) == ([{"id": "t3", "label": {"org": gn}, "reason": "까닭", "keep": False}], [])
    assert ZL.check({"items": [row("t3", "none")]}, pl) == ([{"id": "t3", "label": {"org": None}, "reason": "까닭", "keep": False}], [])   # 확인 필요 → 기관 없음(공통)도 값이 바뀌는 답
    # editable 이 안 실린 후보(손으로 만든 자료)는 아무 기준도 못 바꾼다
    bare = {**pl, "candidates": [{k: v for k, v in c.items() if k != "editable"}]}
    assert ZL.check({"items": [row("t3", gn, "1")]}, bare) == ([{"id": "t3", "label": {}, "reason": "까닭", "keep": True}], [{"id": "t3", "dim": "org", "value": gn, "why": ZL.FIXED}, {"id": "t3", "dim": "year", "value": "1", "why": ZL.FIXED}])


def test_cut_keeps_conflicts_then_unknowns_then_the_rest_in_document_order():
    cands = [{"id": f"c{n}", "kind": ("hint", "alone", "unknown", "conflict")[n % 4]} for n in range(400)]
    kept, more = ZL.cut(cands)
    assert more is True and len(kept) == ZL.MAX == 150 and ZL.kinds(kept) == {"conflict": 100, "unknown": 50, "hint": 0, "alone": 0}
    assert [c["id"] for c in kept] == sorted((c["id"] for c in kept), key=lambda i: int(i[1:])) and kept[0]["id"] == "c2"   # 남긴 것은 문서 차례 그대로
    kept, more = ZL.cut(cands[:240])
    assert more and ZL.kinds(kept) == {"conflict": 60, "unknown": 60, "hint": 15, "alone": 15} and kept[:2] == cands[:2]   # 나머지는 문서 차례로 찰 때까지
    assert ZL.cut(cands[:150]) == (cands[:150], False) and ZL.cut([]) == ([], False) and ZL.cut(None) == ([], False)


# ---- 프롬프트 · 스키마 · 호출 ------------------------------------------------------------------------------------------

def _payload(stages=(2, 2)):
    why = {"byNo": J2, "byName": [J1]}
    can = lambda org, stage, year: {"org": org, "stage": stage, "year": year}  # noqa: E731 — 후보마다 바꿀 수 있는 기준(candidates 가 싣는 꼴)
    cands = [{"id": "p2", "type": "paragraph", "kind": "conflict", "editable": can(True, True, True), "read": {"orgKind": "conflict", "why": why}, "text": "[공동연구개발기관1]"},
             {"id": "p4", "type": "paragraph", "kind": "unknown", "editable": can(True, False, True), "read": {"orgKind": "unknown", "stage": 1}, "text": "[공동연구개발기관N]"},
             {"id": "t1", "type": "table", "kind": "hint", "editable": can(True, True, True), "signs": ["orgName"], "size": "2x2", "head": ["구분", "내용"], "side": []},
             {"id": "t2", "type": "table", "kind": "hint", "editable": can(False, True, True), "signs": ["yearTag"], "read": {"orgKind": "org", "org": J1}, "size": "1x2", "head": [], "side": []},
             {"id": "t3", "type": "table", "kind": "conflict", "editable": can(True, False, False), "signs": ["cells"], "read": {"orgKind": "org", "org": LEAD, "stage": 1, "year": 2}, "size": "1x2", "head": [], "side": []},
             {"id": "t4", "type": "table", "kind": "alone", "editable": can(True, True, True), "size": "1x2", "head": [], "side": []}]
    return ZL.payload({"orgs": ORGS, "stages": list(stages)}, cands)


def test_payload_prompt_schema_and_one_call(monkeypatch):
    pl = _payload()
    assert set(pl) == {"orgs", "stages", "years", "candidates"} and pl["orgs"] == ORGS and (pl["stages"], pl["years"]) == ([2, 2], 4) and len(pl["candidates"]) == 6
    period = {"start": "2026-03-01", "end": "2027-12-31"}   # 사업기간은 값에 있을 때만 싣는다
    assert ZL.payload({"orgs": ORGS, "stages": [2]}, [], {**period, "x": 1})["period"] == period and all("period" not in ZL.payload({"orgs": ORGS, "stages": [2]}, [], x) for x in (None, {}, {"start": "2026-03-01"}, "x"))
    text = ZL.prompt(pl)
    guide = MG.get("zones")
    assert text.startswith(ZL.CONTRACT + "\n\n## 판단 지침 — 편집 구역 검토\n" + ZL.GUIDE_NOTE) and MG.body(guide) in text and "<!--" not in text   # 계약 + 지침(주석·제목 줄 뺌) + 자료
    assert json.loads(text.split("\n\n## 자료(JSON)\n", 1)[1]) == pl
    sc = ZL.schema(pl)
    item = sc["properties"]["items"]["items"]
    assert sc["required"] == ["items", "summary"] and item["required"] == ["id", "org", "stage", "year", "reason"] and item["additionalProperties"] is False
    assert item["properties"]["id"]["enum"] == ["p2", "p4", "t1", "t2", "t3", "t4"] and item["properties"]["org"]["enum"] == [LEAD, J1, J2, "none", "keep"]   # 보낸 id · 보낸 열쇠만
    assert item["properties"]["stage"]["enum"] == ["1", "2", "none", "keep"] and item["properties"]["year"]["enum"] == ["1", "2", "3", "4", "none", "keep"]     # 범위 안의 번호(글)
    assert ZL.SCHEMA["properties"]["items"]["items"]["properties"]["id"] == {"type": "string"}   # 좁힌 스키마는 사본 — 기본 꼴은 그대로
    seen = {}

    def call(schema, content, what, *, timeout, effort):
        seen.update(schema=schema, content=content, what=what, timeout=timeout, effort=effort)
        return {**CALL, "data": {"items": [], "summary": "없음"}}
    res = ZL.ask(pl, call=call, effort="high", timeout=99.0)
    assert seen == {"schema": sc, "content": text, "what": "zones-llm", "timeout": 99.0, "effort": "high"}
    assert res == {"data": {"items": [], "summary": "없음"}, "prompt": text, "call": CALL, "guide": {"name": "zones", "title": guide["title"], "sha1": guide["sha1"]}}
    assert [(p["key"], p["source"]) for p in ZL.parts()] == [("contract", "app/zones_llm.py"), ("guide", guide["path"])] and ZL.parts()[0]["text"] == ZL.CONTRACT and ZL.parts()[1]["text"] == MG.body(guide)
    # 지침 파일이 없으면(끔) 최소 기준만 붙는다
    monkeypatch.setenv("NFM_MERGE_GUIDES", "off")
    assert ZL.prompt(pl).startswith(ZL.CONTRACT + ZL.FALLBACK_GUIDE + "\n\n## 자료(JSON)\n") and ZL.ask(pl, call=call)["guide"] is None and seen["content"] == ZL.prompt(pl)
    assert [p["source"] for p in ZL.parts()] == ["app/zones_llm.py", "app/zones_llm.py"]
    # 실제 호출 길(llm.call) — LLM 이 꺼져 있으면 답 없음(예외 없음)
    off = ZL.ask(pl)
    assert off["data"] is None and off["call"]["error"] == "off" and AS.runs("zone_review", 1)[0]["what"] == "zones-llm"   # 실행 기록에는 에이전트 zone_review 로 남는다


def test_check_takes_only_sent_ids_known_keys_numbers_in_range_and_never_changes_what_the_script_read():
    pl = _payload()
    ans = {"summary": "s", "items": [
        {"id": "p2", "org": J1, "stage": "keep", "year": "keep", "reason": "  글에 적힌   이름 " + "가" * 300},      # 확인 필요 → 기관
        {"id": "p2", "org": J2, "stage": "keep", "year": "keep", "reason": "둘째 답"},                                # 같은 후보를 두 번
        {"id": "p9", "org": J1, "stage": "keep", "year": "keep", "reason": "없는 id"},
        {"id": "p4", "org": "none", "stage": "2", "year": 3, "reason": "기관 모름 → 공통 · 단계는 스크립트가 읽었다"},   # 기관 없음은 받고 · 읽힌 단계(1)를 바꾸는 답과 그 단계의 것이 아닌 차년도는 버린다
        {"id": "t1", "org": "없는기관", "stage": "9", "year": "0", "reason": "모르는 열쇠 · 범위 밖"},
        {"id": "t2", "org": "none", "stage": "none", "year": "3", "reason": "읽힌 기관을 없앨 수 없다 · 차년도는 채운다"},
        {"id": "t3", "org": J1, "stage": "1", "year": "2", "reason": "칸에서 기관 근거가 엇갈린 표(editable.org)의 기관은 고를 수 있다 · 같은 값은 그대로"},
        {"id": "t4", "org": "㈜인텍", "stage": "1", "year": "3", "reason": "이름으로 적어도 열쇠로 · 단계와 차년도가 안 맞는다"},
        "x", {"org": J1}]}
    items, dropped = ZL.check(ans, pl)
    assert [(i["id"], i["label"], i["keep"]) for i in items] == [("p2", {"org": J1}, False), ("p4", {"org": None}, False), ("t1", {}, True), ("t2", {"year": 3}, False), ("t3", {"org": J1}, False), ("t4", {"org": LEAD}, False)]
    assert len(items[0]["reason"]) == ZL.REASON_MAX and items[0]["reason"].startswith("글에 적힌 이름 가")   # 까닭은 빈칸을 정리해 200자까지
    assert dropped == [{"id": "p2", "why": "같은 후보를 두 번"}, {"id": "p9", "why": "보낸 후보에 없는 id"},
                       {"id": "p4", "dim": "stage", "value": "2", "why": ZL.FIXED}, {"id": "p4", "dim": "year", "value": "3", "why": "스크립트가 읽은 단계(1단계)의 차년도가 아니다"},
                       {"id": "t1", "dim": "org", "value": "없는기관", "why": "과제 기관에 없는 열쇠"}, {"id": "t1", "dim": "stage", "value": "9", "why": "범위 밖의 번호(1~2)"},
                       {"id": "t1", "dim": "year", "value": "0", "why": "범위 밖의 번호(1~4)"}, {"id": "t2", "dim": "org", "value": "none", "why": ZL.FIXED},
                       {"id": "t4", "dim": "stage", "value": "1", "why": "단계와 차년도가 서로 안 맞음"}, {"id": "t4", "dim": "year", "value": "3", "why": "단계와 차년도가 서로 안 맞음"},
                       {"id": "", "why": "보낸 후보에 없는 id"}]
    # 값이 안 바뀌는 답은 그대로로 친다(지정을 만들지 않는다) — 기관이 안 붙은 곳의 none · 같은 기관 · 같은 번호 · keep · 빈 값
    same = {"items": [{"id": "t1", "org": "none", "stage": "none", "year": "none", "reason": ""}, {"id": "t2", "org": J1, "stage": "keep", "year": "", "reason": None},
                      {"id": "t3", "org": LEAD, "stage": 1, "year": 2}, {"id": "t4", "org": "keep"}, {"id": "p4", "org": "keep", "stage": "1", "year": "none"}]}
    items, dropped = ZL.check(same, pl)
    assert [(i["id"], i["label"], i["keep"], i["reason"]) for i in items] == [("p4", {}, True, ""), ("t1", {}, True, ""), ("t2", {}, True, ""), ("t3", {}, True, ""), ("t4", {}, True, "")] and dropped == []   # 보낸 차례
    # 채우는 답 — 단계만 · 차년도만(단계는 그 차년도의 것) · 둘 다(서로 맞음) · 꼴이 틀린 값
    fill = {"items": [{"id": "t1", "org": J2, "stage": "2", "year": "keep"}, {"id": "t4", "org": "keep", "stage": "2", "year": "4"}, {"id": "p2", "org": ["x"], "stage": True, "year": 2.5},
                      {"id": "p4", "org": "keep", "stage": "keep", "year": "2"}]}
    items, dropped = ZL.check(fill, pl)
    assert [(i["id"], i["label"]) for i in items] == [("p2", {}), ("p4", {"year": 2}), ("t1", {"org": J2, "stage": 2}), ("t4", {"stage": 2, "year": 4})]
    assert [(d["id"], d["dim"]) for d in dropped] == [("p2", "org"), ("p2", "stage"), ("p2", "year")]
    for it in items:   # 받은 값은 지정으로 적을 수 있는 꼴이다(zones.norm_label)
        if it["label"]:
            assert Z.norm_label(it["label"], {"orgs": ORGS, "stages": [2, 2]}) == it["label"]
    assert ZL.check(None, pl) == ([], []) and ZL.check({"items": "x"}, pl)[0] == [] and ZL.check({}, pl) == ([], [])


# ---- 등록 ------------------------------------------------------------------------------------------------------------

def test_the_review_is_a_registered_agent_with_its_guide_and_log(monkeypatch):
    monkeypatch.delenv("NFM_JOBS", raising=False)
    a = AG.BY_ID["zone_review"]
    assert (a["no"], a["group"], a["name"], a["run"], a["contract"], a["parts"]) == ("21", "프로젝트 구성", "편집 구역 검토", "manual", ("app.zones_llm", "CONTRACT"), (("merge", "zones"),))
    assert AS.agent_of("zones-llm") == "zone_review" and AS.agent_of(ZL.WHAT) == "zone_review" and a in AG.AGENTS   # 등록부의 끝이 아니어도 된다(e039879 가 22 「지침 보정」 을 뒤에 더함)
    d = AG.detail("zone_review")
    assert [p["kind"] for p in d["prompt"]] == ["contract", "merge", "data", "note"] and d["prompt"][0]["text"] == ZL.CONTRACT   # 끝의 note = 덧붙이는 글 칸(spec_에이전트 ② §6 — 모든 에이전트에 붙는다: tests/test_agents.py 와 같은 기대) and d["prompt"][1]["source"] == "app/merge_guides_default/zones.md" and d["prompt"][1]["text"]
    assert d["whats"] == ["zones-llm"] and d["model"]["source"] == "default" and d["effort"] == {"id": "medium", "source": "code"}
    assert MA.GUIDE_STEPS["zones"] == "편집 구역 LLM 검토" and ("zones", "편집 구역 LLM 검토 기록") in [(n, t) for n, t, _ in WL.SOURCES]
    for word in ("갈래", "공백", "차원", "반복 축"):   # 화면에 보이는 글(역할 · 쓰는 곳 · 자료 · 오류 글)에 안 쓰는 말
        assert word not in a["role"] + a["where"] + a["data"] + " ".join(ZA.LLM_MSG.values())


# ---- 끝점 ------------------------------------------------------------------------------------------------------------

def _set(c, to, cell, text):
    """표 칸의 글을 바꾼다(칸의 첫 문단)."""
    assert c.patch(f"/api/docs/{to}/blocks/{cell['blocks'][0]['id']}", json={"text": text}).status_code == 200


def _doc(c):
    """취합본(값 = 인텍·가나대·다라연 · 1단계 2차년도)에 스크립트가 못 정하는 표 둘을 만든다 → (id, 근거가 다른 표, 낌새 있는 표).
    인텍 묶음 안의 표 「직장 | 기관명 | …」 에 가나대 = 묶음과 칸이 다르게 말함(conflict) · 공통 자리의 표의 한 칸에 다라연(이름표 칸 옆이 아님 — 낌새 orgName)."""
    to, _ = _master(c, frame=False)
    doc = server._sess(to).doc
    lead, over = D.table_after(doc, "(1) 주관연구개발기관책임자"), D.table_after(doc, "□ 과제개요")
    _set(c, to, D.cell(doc, lead, 2, 2), J1)
    _set(c, to, D.cell(doc, over, 0, 1), J2)   # 「연구개발과제명」 옆 칸 — 기관 이름표 칸(「주관연구개발기관」)의 옆은 비어 있다
    return to, lead, over


def _fake(monkeypatch, answer, seen=None, during=None):
    """LLM 을 흉내로 — answer(자료) → items. 보낸 것은 seen 에 남기고, during 이 있으면 호출 도중에 부른다."""
    seen = seen if seen is not None else {}

    def call(schema, content, what, *, timeout=180.0, effort=None, **kw):
        pl = json.loads(content.split("\n\n## 자료(JSON)\n", 1)[1])
        seen.update(schema=schema, content=content, what=what, timeout=timeout, effort=effort, payload=pl, n=seen.get("n", 0) + 1)
        if during:
            during()
        data = answer(pl)
        return {**CALL, "data": None if data is None else {"items": data, "summary": " 표 둘을   정했습니다 "}, "error": "시간 초과 240s" if data is None else None}
    monkeypatch.setattr(ZL.llm, "call", call)
    monkeypatch.setattr(ZL.llm, "status", lambda: {"available": True})
    return seen


def _run(c, to, z=None, **more):
    z = z or _zones(c, to)
    return c.post(f"/api/docs/{to}/zones/llm", json={"docRev": z["rev"], "zonesRev": z["zonesRev"], **more})


def test_peek_counts_the_candidates_and_run_writes_llm_marks(client, monkeypatch):
    c = client
    to, lead, over = _doc(c)
    z0 = _zones(c, to)
    assert z0["blocks"][lead]["orgKind"] == "conflict" and z0["blocks"][lead]["why"] == {"byGroup": LEAD, "byCell": [J1]} and over not in z0["blocks"] and z0["counts"]["conflicts"] == 1
    peek = _ok(c.get(f"/api/docs/{to}/zones/llm"))
    assert set(peek) == {"available", "why", "running", "candidates", "kinds", "truncated", "last"} and set(peek["kinds"]) == {"conflict", "unknown", "hint", "alone"}
    assert (peek["available"], peek["running"], peek["truncated"], peek["last"]) == (False, False, False, None) and "LLM" in peek["why"]   # LLM 이 꺼져 있다 — 미리 보기는 된다
    n = peek["candidates"]
    assert peek["kinds"]["conflict"] == 1 and peek["kinds"]["hint"] >= 1 and sum(peek["kinds"].values()) == n and _zones(c, to) == z0   # 미리 보기는 아무것도 안 바꾼다
    _why(_run(c, to, z0), 409, "noLlm")   # 후보가 있는데 LLM 을 쓸 수 없다
    need = D.para(server._sess(to).doc, "□ 필요성")
    z1 = _ok(_post(c, to, [need], {"org": J2}, z0))   # 사람이 지정한 블록 — 검토가 건드리지 않는다

    def answer(pl):
        ids = [x["id"] for x in pl["candidates"]]
        rest = [i for i in ids if i not in (lead, over)]
        return [{"id": lead, "org": J1, "stage": "keep", "year": "keep", "reason": "「기관명」 칸에 가나대가 적혀 있다"},
                {"id": over, "org": J2, "stage": "keep", "year": "2", "reason": "표 안에 다라연만 적혀 있다"},
                {"id": lead, "org": LEAD, "stage": "keep", "year": "keep", "reason": "둘째 답"},
                {"id": need, "org": J1, "stage": "keep", "year": "keep", "reason": "사람이 지정한 블록"},
                {"id": "t999999", "org": J1, "stage": "keep", "year": "keep", "reason": "없는 id"},
                *[{"id": i, "org": "없는기관" if k == 0 else "keep", "stage": "keep", "year": "9" if k == 0 else "keep", "reason": "근거가 모자라다"} for k, i in enumerate(rest)]]
    seen = _fake(monkeypatch, answer)
    assert _ok(c.get(f"/api/docs/{to}/zones/llm"))["available"] is True and _ok(c.get(f"/api/docs/{to}/zones/llm"))["why"] is None
    out = _ok(_run(c, to, z1))
    assert set(out) == KEYS | {"llm"} and seen["n"] == 1 and seen["what"] == "zones-llm" and seen["effort"] == "medium" and seen["timeout"] >= 240.0
    pl = seen["payload"]
    sent = {x["id"]: x for x in pl["candidates"]}
    assert len(sent) == n and need not in sent and [o["key"] for o in pl["orgs"]] == [LEAD, J1, J2] and (pl["stages"], pl["years"], pl["period"]) == ([2], 2, D.VALUES["period"])   # 사람이 지정한 블록은 보내지 않는다
    assert (sent[lead]["kind"], sent[lead]["read"]["why"]) == ("conflict", {"byGroup": LEAD, "byCell": [J1]}) and (sent[over]["kind"], sent[over]["signs"], sent[over]["names"]) == ("hint", ["orgName"], [{"org": J2, "n": 1}])
    assert sent[lead]["editable"]["org"] is True and sent[over]["editable"] == {"org": True, "stage": True, "year": True} and all(any(x["editable"].values()) for x in sent.values())   # 후보마다 정할 수 있는 기준이 실린다
    assert seen["schema"]["properties"]["items"]["items"]["properties"]["id"]["enum"] == list(sent) and seen["content"].startswith(ZL.CONTRACT)
    extra = 2 if n > 2 else 0   # 그 밖의 후보 하나에 모르는 열쇠 · 범위 밖 번호
    assert out["llm"] == {"candidates": n, "marked": 2, "kept": n - 2, "dropped": 3 + extra, "summary": "표 둘을 정했습니다", "truncated": False, "call": {"model": "m-fake", "ms": 7, "costUsd": 0.02, "error": None}}
    marks = {m["ids"][0]: m for m in out["marks"]}
    assert set(marks) == {need, lead, over} and (out["zonesRev"], out["rev"]) == (z1["zonesRev"] + 1, z1["rev"])   # 구역 판은 한 번 · 문서 차례는 그대로
    assert (marks[lead]["by"], marks[lead]["ids"], marks[lead]["label"], marks[lead]["note"], marks[lead]["invalid"]) == ("llm", [lead], {"org": J1}, "「기관명」 칸에 가나대가 적혀 있다", [])
    assert (marks[over]["by"], marks[over]["label"], marks[over]["note"]) == ("llm", {"org": J2, "year": 2}, "표 안에 다라연만 적혀 있다") and set(marks[over]) == {"id", "ids", "gone", "label", "note", "by", "at", "invalid"}
    assert (marks[need]["by"], marks[need]["label"]) == ("user", {"org": J2}) and marks[need] == z1["marks"][0]   # 사람 지정은 그대로
    assert (out["blocks"][lead]["org"], out["blocks"][lead]["orgKind"], out["blocks"][lead]["src"]["org"]) == (J1, "org", "mark") and out["counts"]["conflicts"] == 0
    assert (out["blocks"][over]["org"], out["blocks"][over]["year"], out["blocks"][over]["stage"], out["blocks"][over]["src"]) == (J2, 2, 1, {"org": "mark", "stage": "mark", "year": "mark"})
    assert any(x["mark"] == marks[lead]["id"] and x["ids"] == [lead] for x in out["zones"]) and _zones(c, to) == {k: v for k, v in out.items() if k != "llm"}
    st = json.loads((works.folder(to) / "state.json").read_text("utf-8"))   # 지정은 바로 저장된다 · 실행 취소 대상이 아니다
    assert sorted(m["by"] for m in st["zones"]["marks"]) == ["llm", "llm", "user"] and st["zones"]["rev"] == out["zonesRev"] and server._sess(to).undo == [] and st["rev"] == out["rev"]
    ev = [e for e in works.events(to) if e["kind"] == "zoneLlm"]
    assert len(ev) == 1 and (ev[0]["op"], ev[0]["candidates"], ev[0]["marked"], ev[0]["kept"], ev[0]["dropped"], ev[0]["model"], ev[0]["costUsd"]) == ("review", n, 2, n - 2, 3 + extra, "m-fake", 0.02)
    # 미리 보기 — 지정된 블록은 다시 보내지 않는다 · 마지막 결과
    peek = _ok(c.get(f"/api/docs/{to}/zones/llm"))
    assert (peek["candidates"], peek["kinds"]["conflict"], peek["running"]) == (n - 2, 0, False)
    assert set(peek["last"]) == {"at", "candidates", "marked", "kept", "dropped", "summary", "error"} and (peek["last"]["candidates"], peek["last"]["marked"], peek["last"]["kept"], peek["last"]["error"]) == (n, 2, n - 2, None)
    # 「지침」 — 계약 · 판단 지침 · 마지막으로 보낸 프롬프트와 답
    g = _ok(c.get(f"/api/docs/{to}/llm-guide/zones"))
    assert (g["step"], g["name"], g["model"]) == ("zones", "편집 구역 LLM 검토", None) and [p["key"] for p in g["parts"]] == ["contract", "guide"] and g["parts"][0]["text"] == ZL.CONTRACT
    assert g["last"]["at"] == peek["last"]["at"] and [(u["n"], u["title"], u["targets"], u["has"], u["error"]) for u in g["last"]["units"]] == [(0, "편집 구역 LLM 검토", n, True, None)]
    p = _ok(c.get(f"/api/docs/{to}/llm-guide/zones/prompt"))
    assert p["prompt"] == seen["content"] and p["answer"]["summary"].strip() == "표 둘을   정했습니다" and len(p["answer"]["items"]) == n + 3
    # 로그 — 에이전트가 읽는 「편집 구역 LLM 검토 기록」
    lines = WL.read(to, "zones", 80)["lines"]
    assert len(lines) == 1 + n + 3 + extra and f"후보={n} 지정=2 그대로={n - 2} 버림={3 + extra}" in lines[0] and "모델=m-fake" in lines[0] and "표 둘을 정했습니다" in lines[0]
    assert any(f"{lead}(table · conflict) org={J1} — 「기관명」 칸에" in x for x in lines) and any("그대로 — 근거가 모자라다" in x for x in lines) and any("버림 t999999 — 보낸 후보에 없는 id" in x for x in lines)
    assert {x["log"]: x["lines"] for x in WL.index(to)}["zones"] == len(lines)


def test_llm_marks_can_all_be_cleared_and_user_marks_stay(client, monkeypatch):
    c = client
    to, lead, over = _doc(c)
    need = D.para(server._sess(to).doc, "□ 필요성")
    z = _ok(_post(c, to, [need, over], {"org": LEAD}))   # 낌새 있는 표를 사람이 먼저 지정했다
    seen = _fake(monkeypatch, lambda pl: [{"id": lead, "org": "none", "stage": "keep", "year": "keep", "reason": "어느 기관의 것도 아니다"},
                                         {"id": over, "org": J2, "stage": "keep", "year": "keep", "reason": "사람이 지정한 표"}])
    out = _ok(_run(c, to, z))
    assert over not in {x["id"] for x in seen["payload"]["candidates"]} and (out["llm"]["marked"], out["llm"]["dropped"]) == (1, 1)
    assert [(m["by"], m["ids"], m["label"]) for m in out["marks"]] == [("user", [need, over], {"org": LEAD}), ("llm", [lead], {"org": None})]
    assert lead not in out["blocks"] and out["counts"]["conflicts"] == 0 and out["blocks"][over]["org"] == LEAD   # 「기관 없음」 으로 지정 — 확인 필요가 풀린다
    url = f"/api/docs/{to}/zones/marks"
    _why(c.delete(f"{url}?by=user&zonesRev={out['zonesRev']}"), 400, "badMark")
    _why(c.delete(f"{url}?zonesRev={out['zonesRev']}"), 400, "badMark")
    _why(c.delete(f"{url}?by=llm"), 400, "badMark")                             # 구역 판을 안 보냄
    _why(c.delete(f"{url}?by=llm&zonesRev={out['zonesRev'] - 1}"), 409, "staleZones")
    assert _zones(c, to)["marks"] == out["marks"]
    z2 = _ok(c.delete(f"{url}?by=llm&zonesRev={out['zonesRev']}"))
    assert set(z2) == KEYS and [(m["by"], m["ids"]) for m in z2["marks"]] == [("user", [need, over])] and z2["zonesRev"] == out["zonesRev"] + 1 and z2["blocks"][lead]["orgKind"] == "conflict"   # 자동 값으로 돌아간다
    z3 = _ok(c.delete(f"{url}?by=llm&zonesRev={z2['zonesRev']}"))   # 하나도 없으면 그대로
    assert z3 == z2 and [(e["op"], e.get("marks")) for e in works.events(to) if e["kind"] == "zoneLlm"] == [("review", None), ("clear", 1)]
    assert json.loads((works.folder(to) / "state.json").read_text("utf-8"))["zones"]["marks"] == server._sess(to).zones["marks"] and len(server._sess(to).zones["marks"]) == 1
    # 다시 검토 — 해제한 블록은 다시 후보다 · 그대로(keep)면 지정을 만들지 않는다
    seen.clear()
    _fake(monkeypatch, lambda pl: [{"id": x["id"], "org": "keep", "stage": "keep", "year": "keep", "reason": "가릴 수 없다"} for x in pl["candidates"]], seen)
    out = _ok(_run(c, to, z3))
    n = len(seen["payload"]["candidates"])
    assert lead in {x["id"] for x in seen["payload"]["candidates"]} and out["llm"] == {**out["llm"], "candidates": n, "marked": 0, "kept": n, "dropped": 0}
    assert out["marks"] == z3["marks"] and out["zonesRev"] == z3["zonesRev"] and _ok(c.get(f"/api/docs/{to}/zones/llm"))["last"]["marked"] == 0   # 구역 판도 그대로


def test_an_llm_mark_edited_by_a_person_becomes_the_persons_and_survives_clearing(client, monkeypatch):
    """LLM 이 지정한 것을 사람이 고치면 사람의 지정이다(by user) — 「LLM 지정 모두 해제」 가 사람이 손본 것까지 지우지 않는다(spec_구역 ② §8)."""
    c = client
    to, lead, over = _doc(c)
    _fake(monkeypatch, lambda pl: [{"id": lead, "org": J1, "stage": "keep", "year": "keep", "reason": "「기관명」 칸에 가나대"},
                                   {"id": over, "org": J2, "stage": "keep", "year": "keep", "reason": "표 안에 다라연만"}])
    out = _ok(_run(c, to))
    by = {m["ids"][0]: m for m in out["marks"]}
    assert (by[lead]["by"], by[over]["by"]) == ("llm", "llm")
    z = _ok(c.put(f"/api/docs/{to}/zones/marks/{by[lead]['id']}", json={"label": {"org": LEAD}, "docRev": out["rev"], "zonesRev": out["zonesRev"]}))
    mine = next(m for m in z["marks"] if m["id"] == by[lead]["id"])
    assert (mine["by"], mine["label"], mine["ids"]) == ("user", {"org": LEAD}, [lead]) and z["blocks"][lead]["org"] == LEAD
    z2 = _ok(c.delete(f"/api/docs/{to}/zones/marks?by=llm&zonesRev={z['zonesRev']}"))
    assert [(m["by"], m["ids"]) for m in z2["marks"]] == [("user", [lead])] and z2["blocks"][lead]["org"] == LEAD   # 사람이 고친 것은 남고 LLM 의 것만 해제


def test_stale_screen_busy_failed_call_and_changes_during_the_call_leave_the_marks_alone(client, monkeypatch):
    c = client
    to, lead, over = _doc(c)
    z = _zones(c, to)
    seen = _fake(monkeypatch, lambda pl: [{"id": lead, "org": J1, "stage": "keep", "year": "keep", "reason": "칸의 이름"}])
    # 낡은 화면 — 호출하지 않는다
    _why(_run(c, to, {**z, "rev": z["rev"] + 1}), 409, "staleDoc")
    _why(_run(c, to, {**z, "zonesRev": z["zonesRev"] + 1}), 409, "staleZones")
    _why(c.post(f"/api/docs/{to}/zones/llm", json={}), 400, "badMark")
    # 이미 도는 중
    ZA._LLM_RUN.add(to)
    assert _ok(c.get(f"/api/docs/{to}/zones/llm"))["running"] is True
    assert "이미 돌고" in _why(_run(c, to, z), 409, "busy")["message"]
    ZA._LLM_RUN.clear()
    assert "n" not in seen and server._sess(to).zones["marks"] == []
    # 호출 실패 — 지정은 안 바뀌고 기록은 남는다
    _fake(monkeypatch, lambda pl: None, seen)
    assert "시간 초과" in _why(_run(c, to, z), 502, "llmFailed")["message"]
    peek = _ok(c.get(f"/api/docs/{to}/zones/llm"))
    assert seen["n"] == 1 and server._sess(to).zones["marks"] == [] and (peek["last"]["marked"], peek["last"]["error"], peek["running"]) == (0, "시간 초과 240s", False)
    assert _ok(c.get(f"/api/docs/{to}/llm-guide/zones"))["last"]["units"][0]["error"] == "시간 초과 240s" and _zones(c, to) == z
    # 호출하는 동안 문서가 바뀜 — 반영하지 않는다
    first = next(b["id"] for b in server._sess(to).doc.blocks() if b["type"] == "paragraph" and b["text"].strip())
    edit = lambda: c.patch(f"/api/docs/{to}/blocks/{first}", json={"text": "검토하는 동안 고친 글"})  # noqa: E731
    _fake(monkeypatch, lambda pl: [{"id": lead, "org": J1, "stage": "keep", "year": "keep", "reason": "칸의 이름"}], seen, during=edit)
    assert "검토하는 동안" in _why(_run(c, to, z), 409, "staleDoc")["message"]
    z = _zones(c, to)
    assert z["rev"] == 3 and z["marks"] == [] and "검토하는 동안" in _ok(c.get(f"/api/docs/{to}/zones/llm"))["last"]["error"] and ZA._LLM_RUN == set()
    # 호출하는 동안 사람이 지정함 — 반영하지 않는다(사람 지정은 남는다)
    mark = lambda: _ok(_post(c, to, [over], {"org": LEAD}))  # noqa: E731
    _fake(monkeypatch, lambda pl: [{"id": lead, "org": J1, "stage": "keep", "year": "keep", "reason": "칸의 이름"}], seen, during=mark)
    _why(_run(c, to, z), 409, "staleZones")
    assert [(m["by"], m["ids"]) for m in _zones(c, to)["marks"]] == [("user", [over])]
    kinds = [(e["op"], e.get("error")) for e in works.events(to) if e["kind"] == "zoneLlm"]
    assert len(kinds) == 3 and kinds[0] == ("review", "시간 초과 240s") and all("검토하는 동안" in k[1] for k in kinds[1:])
    # 호출이 예외를 내도 「답 없음」 으로 — 도는 중 표시가 남지 않는다
    monkeypatch.setattr(ZL.llm, "call", lambda *a, **k: 1 / 0)
    assert "ZeroDivisionError" in _why(_run(c, to), 502, "llmFailed")["message"] and ZA._LLM_RUN == set()


def test_nothing_to_send_makes_no_call(client, monkeypatch):
    c = client
    seen = _fake(monkeypatch, lambda pl: [])
    plain = _upload(c, "프레임.hwpx", D.base()["side"]["bytes"])   # 프로젝트 구성 값이 없는 문서 — 고를 것이 없다
    peek = _ok(c.get(f"/api/docs/{plain}/zones/llm"))
    assert (peek["candidates"], peek["kinds"], peek["available"], peek["last"]) == (0, {"conflict": 0, "unknown": 0, "hint": 0, "alone": 0}, True, None)
    out = _ok(_run(c, plain))
    assert set(out) == KEYS | {"llm"} and out["llm"] == {"nothing": True, "candidates": 0} and out["reasons"] == ["noValues"] and "n" not in seen
    to, lead, over = _doc(c)   # 후보를 모두 사람이 지정하면 보낼 것이 없다
    ids = []
    _fake(monkeypatch, lambda pl: ids.extend(x["id"] for x in pl["candidates"]) or [], seen)
    assert _ok(_run(c, to))["llm"]["marked"] == 0 and {lead, over} <= set(ids)
    z = _ok(_post(c, to, ids, {"org": LEAD}))
    seen.clear()
    out = _ok(_run(c, to, z))
    assert out["llm"] == {"nothing": True, "candidates": 0} and "n" not in seen and out["marks"] == z["marks"] and _ok(c.get(f"/api/docs/{to}/zones/llm"))["candidates"] == 0
    assert _ok(c.get(f"/api/docs/{to}/llm-guide/zones"))["last"]["units"][0]["targets"] == len(ids)   # 앞선 실행의 기록은 그대로
    assert c.get(f"/api/docs/{plain}/llm-guide/zones").json()["last"] is None and c.get(f"/api/docs/{plain}/llm-guide/zones/prompt").status_code == 404
