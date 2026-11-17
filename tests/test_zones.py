"""편집 구역의 순수 계산(`app/zones.py` — spec_구역 ② §2~§5): 자동 판독(묶음 · 윗 제목 · 표 안의 값 읽기) · 지정 · 출처 · 보기.
자료 = gather_data(양식에 값(1단계 2차년도 · 기관 인텍·가나대·다라연)을 반영한 문서 + 그래프·표) · 같은 양식에 2단계(1차년도 + 2차년도) · 기관 인텍·가나·가나대 를 반영한 문서(이름이 이름을 품는 경우 · 단계 안 차년도).
취합의 느슨한 판독(`merge_gather_frame.make` 의 scope)에 반례가 없는 시험 자료에서는 두 판독이 같아야 한다 — 반례(astra 협의 P1 — 2.)는 문서를 메모리에서 고쳐 만든다."""
import copy

import pytest

import gather_data as D
import merge_data as M
from app import merge_gather_frame as F
from app import zones as Z
from app.division_profiles import rnd
from app.division_profiles.rnd import core

LEAD, J1, J2 = D.LEAD, D.J1, D.J2
_MEMO = {}


def _snap(blocks, values, graph=None, tables=None, **kw):
    return {"blocks": blocks, "values": values, "graph": graph, "tables": tables, "hints": [], "prior": None, **kw}


def _base():
    """시험 자료의 기준본을 읽은 것 — {side, frame, info}(프로세스에 한 번)."""
    if "base" not in _MEMO:
        b = D.base()
        s = b["side"]
        _MEMO["base"] = {**b, "info": Z.read(_snap(s["blocks"], s["values"], s["graph"], s["tables"]))}
    return _MEMO["base"]


def _edited(edit):
    """기준본의 사본(블록 id 가 같다)을 edit(doc) 로 고친 뒤 **분석은 그대로 둔 채**(낡은 그래프) 다시 읽는다 → (doc, info)."""
    m = D.master()
    edit(m["doc"])
    return m["doc"], Z.read(_snap(m["doc"].blocks(), m["values"], m["graph"], m["tables"]))


TWO = {"stages": [1, 2], "orgs": {"lead": "인텍", "joint": ["가나", "가나대"]}}   # 1단계 1년 + 2단계 2년 — 2단계의 「2차년도」(전체 차례 3)는 번호만으로는 2단계의 것처럼 보인다


def _two():
    """2단계(1차년도 + 2차년도) · 기관 인텍·가나·가나대 를 반영한 양식 — {values, bytes}(프로세스에 한 번 · 분석 없음)."""
    if "two" not in _MEMO:
        from app.hwpx_doc import HwpxDoc
        values = core.norm_values(TWO)
        doc = HwpxDoc(M.PLAN_FORM.read_bytes())
        assert not core.apply(doc, values, levels_of=rnd.levels_of)["errors"]
        _MEMO["two"] = {"values": values, "bytes": D.save(doc)}
    return _MEMO["two"]


def _two_doc():
    from app.hwpx_doc import HwpxDoc
    return HwpxDoc(_two()["bytes"])


def _lab(org=None, stage=None, year=None, kind="org", ev="group"):
    """자동 라벨 하나(시험용 — `read` 가 내는 꼴)."""
    kind = kind if org is not None or kind in ("unknown", "conflict") else None
    vals = {"org": kind, "stage": stage, "year": year}
    return {"org": org, "orgKind": kind, "stage": stage, "year": year, "src": {d: "auto" for d in Z.DIMS if vals[d] is not None}, "ev": {d: ev for d in Z.DIMS if vals[d] is not None}}


ORGS = [{"key": "인텍", "name": "㈜인텍", "role": "lead"}, {"key": "가나대", "name": "가나대", "role": "joint"}, {"key": "다라연", "name": "다라연", "role": "joint"}]


def _info(auto=None, order=None, cells=None, stages=(2, 2), orgs=ORGS, **kw):
    """손으로 만든 info — 본문 블록 a·b·c·d·e·f(문단) 와 표 t(칸 c1·c2·c3)."""
    order = list(order or ["a", "b", "c", "t", "d", "e", "f"])
    cells = {"t": ["c1", "c2", "c3"]} if cells is None else cells
    return {"order": order, "kinds": {i: "tbl" if i in cells else "p" for i in order}, "cellsOf": cells, "auto": dict(auto or {}), "path": {"a": ["1. 개요", "[주관]"]},
            "text": {i: f"글 {i}" for i in order}, "orgs": list(orgs), "stages": list(stages), **kw}


def _mark(ids, label, mid="m1", **kw):
    return {"id": mid, "ids": list(ids), "label": dict(label), "note": "", "by": "user", "at": "2026-11-17T10:00:00", **kw}


def _tbl(rows, tid="t"):
    """손으로 만든 표 블록 — rows[r][c] = 글 | (글, 행 병합, 열 병합) | None(다른 칸이 덮은 자리)."""
    cells = []
    for r, row in enumerate(rows):
        for c, x in enumerate(row):
            if x is None:
                continue
            text, rs, cs = x if isinstance(x, tuple) else (x, 1, 1)
            cells.append({"id": f"{tid}{r}_{c}", "row": r, "col": c, "rowSpan": rs, "colSpan": cs, "text": text})
    return {"id": tid, "type": "table", "nRows": len(rows), "nCols": max(len(r) for r in rows), "cells": cells}


def _doc(*items):
    """손으로 만든 문서의 블록 목록 — 글 = 문단(id p<n>) · 행 목록(_tbl 과 같은 꼴) = 표(id t<n> · 칸 id c<n>_<행>_<열>). n = 차례(1부터). `read` 가 엔진(core.find)까지 그대로 돈다."""
    blocks = []
    for n, x in enumerate(items, 1):
        if isinstance(x, str):
            blocks.append({"id": f"p{n}", "type": "paragraph", "text": x})
            continue
        t = _tbl(x, f"t{n}")
        for c in t["cells"]:
            c["id"] = f"c{n}_{c['row']}_{c['col']}"
            c["blocks"] = [{"id": c["id"] + "p", "type": "paragraph", "text": c["text"]}]
        blocks.append(t)
    return blocks


KEYS = ["가나대", "다라연", "인텍"]


# ---- 자동 판독: 시험 자료(반례 없음) — 취합의 판독과 같다 ----------------------------------------------------------

def test_read_gives_the_block_order_kinds_cells_and_texts():
    b = _base()
    info, frame = b["info"], b["frame"]
    assert set(info) >= {"order", "kinds", "cellsOf", "auto", "path", "text", "orgs", "stages"}
    assert info["order"] == [x["id"] for x in frame["blocks"]] and len(info["order"]) == len(set(info["order"]))   # 본문 최상위 블록 차례(캡션 블록 뺌)
    assert [info["kinds"][x["id"]] for x in frame["blocks"]] == [x["kind"] for x in frame["blocks"]]
    tables = {x["id"]: x["table"] for x in frame["blocks"] if x.get("table")}
    assert set(info["cellsOf"]) == set(tables) and all(info["cellsOf"][t] == [c["id"] for c in g["cells"]] for t, g in tables.items())
    assert [(o["key"], o["role"]) for o in info["orgs"]] == [(LEAD, "lead"), (J1, "joint"), (J2, "joint")] and info["stages"] == [2]
    assert set(info["text"]) == set(info["order"]) and all(isinstance(t, str) and len(t) <= Z.TEXT_MAX for t in info["text"].values())
    assert all(info["path"].get(x["id"], []) == x["path"] for x in frame["blocks"])   # 윗 제목 사슬은 취합의 자리 정보와 같다
    for i, lab in info["auto"].items():   # 값이 하나라도 있는 것만 · 라벨 꼴
        assert set(lab) - {"why"} == {"org", "orgKind", "stage", "year", "src", "ev"}
        assert lab["orgKind"] is not None or lab["stage"] is not None or lab["year"] is not None or lab.get("why")   # 값이 있거나 엇갈린 근거가 남은 것
        assert (lab["org"] is not None) == (lab["orgKind"] == "org") and set(lab["src"].values()) <= {"auto"}
        assert set(lab["ev"]) == set(lab["src"]) and set(lab["ev"].values()) <= {"group", "cell", "path"}
        assert lab["year"] is None or (1 <= lab["year"] <= 2 and lab["stage"] == 1)   # 차년도가 있으면 단계도(차년도에서 채운다)


def test_group_and_title_reading_agree_with_the_gather_scope_where_it_has_no_counterexample():
    """묶음·윗 제목 근거만 읽은 것(표 안의 값 읽기 뺌)은 취합의 scope 와 같다 — 값이 있는 블록·칸마다 같은 기관·차년도. 다른 곳은 범위 밖 차년도(양식의 「3차년도」 칸)뿐: 엄격한 판독은 비운다."""
    b = _base()
    s, frame = b["side"], b["frame"]
    auto = Z._scan(_snap(s["blocks"], s["values"], s["graph"], s["tables"]), cells=False)["auto"]
    best = F._memberships(s["blocks"], s["values"])[0]
    total, seen, beyond = sum(s["values"]["stages"]), {"org": set(), "year": set(), "unknown": 0}, 0

    def same(sc, lab):
        nonlocal beyond
        lab = lab or {"org": None, "orgKind": None, "year": None, "stage": None}
        assert (sc["kind"], sc["org"]) == ("common" if lab["orgKind"] is None else lab["orgKind"], lab["org"])
        if sc["year"] is not None and sc["year"] > total:
            beyond += 1
            assert lab["year"] is None and lab["stage"] is None   # 범위 밖 — 마지막 단계로 접지 않는다
        else:
            assert (sc["year"], sc["stage"]) == (lab["year"], lab["stage"])
        seen["org"].add(lab["org"])
        seen["year"].add(lab["year"])
        seen["unknown"] += lab["orgKind"] == "unknown"
    for row in frame["blocks"]:
        same(row["scope"], auto.get(row["id"]))
        for c in (row.get("table") or {}).get("cells") or ():
            if c["id"] in best:
                same(F._scope(best[c["id"]], s["values"]), auto.get(c["id"]))
            else:
                assert c["id"] not in auto
    assert seen["org"] >= {LEAD, J1, J2, None} and seen["year"] >= {1, 2, None} and seen["unknown"] and beyond   # 기관 셋·차년도를 가른다 · 기관 모름 · 범위 밖 차년도가 실제로 있다
    full = b["info"]["auto"]   # read 는 여기에 표의 칸 근거를 얹는다 — 칸 근거가 없는 곳은 그대로
    assert set(auto) <= set(full)
    assert all(full[i] == lab for i, lab in auto.items() if "cell" not in full[i]["ev"].values() and "why" not in full[i])
    assert {i for i in full if full[i].get("ev", {}).get("org") == "path"} and not [i for i in full if full[i]["orgKind"] == "conflict"]   # 윗 제목으로 읽은 블록이 있다 · 시험 자료에는 충돌이 없다


def test_read_without_values_or_with_odd_input_only_lists_the_blocks():
    b = _base()
    s = b["side"]
    for values in (None, {}, {"stages": "x"}):
        info = Z.read(_snap(s["blocks"], values, s["graph"], s["tables"]))
        assert info["auto"] == {} and info["orgs"] == [] and info["stages"] == []
        assert (info["order"], info["kinds"], info["cellsOf"], info["text"]) == tuple(b["info"][k] for k in ("order", "kinds", "cellsOf", "text"))
        assert info["path"] == b["info"]["path"]
    odd = [{"id": "p1", "type": "paragraph", "text": "제목"}, {"id": "x1", "type": "paragraph", "text": "캡션", "captionOf": "t1"}, {"id": "t1", "type": "table", "cells": [{"id": "c1"}]},
           {"id": "g1", "type": "image"}, {"type": "paragraph"}]
    info = Z.read({"blocks": odd})   # 키가 빠진 snap · 낯선 블록 꼴
    assert info["order"] == ["p1", "t1", "g1"] and info["kinds"] == {"p1": "p", "t1": "tbl", "g1": "pic"} and info["cellsOf"] == {"t1": ["c1"]} and info["text"]["g1"] == ""
    assert Z.build(info, [], [], ["org"])["counts"]["zones"] == 0
    hinted = Z.read(_snap(s["blocks"], s["values"], s["graph"], s["tables"], hints=[{"id": "h1", "para": s["blocks"][0]["id"]}, {"id": "h2"}, "x"], prior=[s["values"]]))
    assert hinted["order"] == b["info"]["order"] and {o["key"] for o in hinted["orgs"]} == {LEAD, J1, J2}   # 추가한 자리·앞서 반영한 값을 엔진에 그대로 넘긴다(꼴이 틀린 줄은 버림)


# ---- 자동 판독: 값 읽기 — 엄격하게(반례) ----------------------------------------------------------------------------

def test_names_drop_the_note_and_names_inside_longer_names():
    keys = ["AB", "A", "C"]
    assert Z._names("공동연구개발기관: A ※ AB collaborates", keys) == ["A"]   # 「※」 뒤 안내 글은 안 본다
    assert Z._names("[공동연구개발기관1(AB)]", keys) == ["AB"]               # A 는 AB 안에 든 것뿐
    assert Z._names("AB 와 A 가 함께", keys) == ["AB", "A"]                  # A 가 AB 밖에 따로 또 적혀 있다
    assert Z._names("[공동연구개발기관2]", keys) == [] and Z._names("", keys) == [] and Z._names(None, keys) == []
    assert Z._names("㈜ 가나 대학", ["가나대학"]) == ["가나대학"]             # ㈜·빈칸은 떼고 견준다(merge_pairs.org_key)


def test_org_item_number_and_name_disagree_is_a_conflict():
    v = core.norm_values({"stages": [1], "orgs": {"lead": "L사", "joint": ["AB", "C"]}})
    keys, g = ["L사", "AB", "C"], {}
    item = lambda value, text: Z._org_item(g, {"value": value, "labelText": text}, v, keys)  # noqa: E731
    assert item(("joint", 1), "[공동연구개발기관1(C)]") == ("conflict", None, {"byNo": "AB", "byName": ["C"]})    # 값의 공동1 = AB 인데 라벨에는 C
    assert item(("joint", 2), "[공동연구개발기관2(AB)]") == ("conflict", None, {"byNo": "C", "byName": ["AB"]})
    assert item(("joint", 1), "[공동연구개발기관1(AB)]") == ("org", "AB", None) and item(("joint", 2), "2번째 행") == ("org", "C", None)   # 이름이 없으면 번호대로
    assert item(("lead", 0), "[주관연구개발기관 : L사] ※ AB 와 C 가 참여") == ("org", "L사", None)
    assert item(("joint", None), "[공동연구개발기관 : C]") == ("org", "C", None)            # 번호가 없으면 이름이 정확히 하나일 때만
    assert item(("joint", None), "[공동연구개발기관 : AB, C]") == ("unknown", None, None)
    assert item(("joint", "N"), "[공동연구개발기관N(기관명 기입)]") == ("unknown", None, None)
    assert item(("joint", 5), "[공동연구개발기관5]") == ("unknown", None, None)             # 값에 없는 번호
    assert item(("col", 2), "C") == ("org", "C", None) and item(("col", 3), "○○○") == ("unknown", None, None)
    assert item(("outside", 1), "가. 기관명: (역할: )") == ("unknown", None, None)
    assert Z._org_item({"named": True}, {"value": ("joint", 1), "labelText": "[공동연구개발기관1(다른회사)]"}, v, keys) == ("unknown", None, None)   # 과제에 없는 이름이 적힌 묶음 — 자리 차례를 믿지 않는다
    empty = core.norm_values({"stages": [1], "orgs": {"lead": "", "joint": [""]}})   # 이름이 아직 안 적힌 값 — 자리표시 글이 열쇠다(빈 열쇠는 안 쓴다)
    assert Z._org_item(g, {"value": ("joint", 1), "labelText": "[공동연구개발기관1(참여기관1)]"}, empty, ["주관기관(미입력)", "참여기관1"]) == ("org", "참여기관1", None)
    assert Z._names("[공동연구개발기관1]", ["", "참여기관1"]) == [] and Z._names("가나대", [""]) == []   # 빈 열쇠는 「든 것」 으로 치지 않는다


def test_swapped_values_make_every_numbered_label_a_conflict_in_read():
    """값은 공동1=다라연·공동2=가나대 인데 문서의 라벨은 「…1(가나대)」·「…2(다라연)」 — 번호를 먼저 믿으면 반대로 붙는다. 엄격한 판독은 둘 다 conflict."""
    s = _base()["side"]
    swapped = core.norm_values({**D.VALUES, "orgs": {"lead": LEAD, "joint": [J2, J1], "nonprofit": [False, False, True]}})
    info = Z.read(_snap(s["blocks"], swapped, s["graph"], s["tables"]))
    top = {b["id"]: b for b in s["blocks"]}
    l1 = [i for i, b in top.items() if b["type"] == "paragraph" and b["text"].strip() == f"[공동연구개발기관1({J1})]"]
    l2 = [i for i, b in top.items() if b["type"] == "paragraph" and b["text"].strip() == f"[공동연구개발기관2({J2})]"]
    assert l1 and l2
    for i in l1:
        assert info["auto"][i]["orgKind"] == "conflict" and info["auto"][i]["org"] is None and info["auto"][i]["why"] == {"byNo": J2, "byName": [J1]}
    for i in l2:
        assert info["auto"][i]["why"] == {"byNo": J1, "byName": [J2]} and info["auto"][i]["src"]["org"] == "auto" and info["auto"][i]["ev"]["org"] == "group"
    lead = next(i for i, b in top.items() if b["type"] == "paragraph" and b["text"].strip() == f"[주관연구개발기관({LEAD})]")
    assert info["auto"][lead]["orgKind"] == "org" and info["auto"][lead]["org"] == LEAD
    view = Z.build(info, [], [], ["org"])
    assert view["counts"]["conflicts"] >= len(l1) + len(l2) and any(z["label"]["orgKind"] == "conflict" and z["text"] == "기관 확인 필요" for z in view["zones"])


def test_two_stage_document_reads_inner_years_in_overall_order_and_names_inside_names():
    t = _two()
    doc = _two_doc()
    blocks, values = doc.blocks(), t["values"]
    top = [b for b in blocks if not b.get("captionOf")]
    plain = next(b["id"] for b in top if b["type"] == "paragraph" and b["text"].strip() == "[공동연구개발기관 : 가나]")
    doc.set_text(plain, "   [공동연구개발기관 : 가나] ※ 가나대 collaborates")   # 안내 글의 「가나대」 는 이 자리의 기관이 아니다
    blocks = doc.blocks()
    info = Z.read(_snap(blocks, values))
    assert info["stages"] == [1, 2] and [o["key"] for o in info["orgs"]] == ["인텍", "가나", "가나대"]
    auto = info["auto"]
    assert auto[plain]["orgKind"] == "org" and auto[plain]["org"] == "가나"
    by_text = lambda text: [b["id"] for b in top if b["type"] == "paragraph" and b["text"].strip() == text]  # noqa: E731
    assert by_text("[공동연구개발기관1(가나)]") and all(auto[i]["org"] == "가나" for i in by_text("[공동연구개발기관1(가나)]"))
    assert by_text("[공동연구개발기관2(가나대)]") and all(auto[i]["org"] == "가나대" for i in by_text("[공동연구개발기관2(가나대)]"))   # 「가나」 가 「가나대」 안에 들어 있어도 가나대
    assert not [i for i, lab in auto.items() if lab["orgKind"] == "conflict"]
    groups = core.find(blocks, rnd.levels_of(blocks), values)
    inner = [g for g in groups if g["dim"] == core.YEAR and g.get("ctx") == 2]
    assert inner   # 2단계 항목 안의 「1차년도·2차년도」 묶음이 있다
    for g in inner:
        for it in g["items"]:
            lab = auto[it["label"]]
            assert (lab["stage"], lab["year"]) == (2, 1 + it["value"])   # 2단계 아래 「1차년도」·「2차년도」 = 전체 차례 2·3(단계 안 차년도 — 묶음의 맥락 ctx 로 읽는다)
    assert {v for g in inner for it in g["items"] for v in [it["value"]]} == {1, 2}
    assert all(lab["stage"] == Z._stage_of([1, 2], lab["year"]) for lab in auto.values() if lab["year"] is not None)
    assert {None, 2, 3} <= {lab["year"] for lab in auto.values()} <= {None, 1, 2, 3}
    assert Z.label_text(auto[inner[0]["items"][0]["label"]], info, ["stage", "year"]) == "2단계 1차년도"


def test_memberships_stage_context_free_years_and_out_of_range_values():
    v = core.norm_values({"stages": [2, 2], "orgs": {"lead": "인텍", "joint": []}})
    it = lambda value, label, *ids: {"value": value, "label": label, "scope": {label, *ids}}  # noqa: E731
    groups = [{"dim": "stage", "items": [it(1, "s1", "a", "y11", "p"), it(2, "s2", "b", "y21", "q", "f1", "r", "n1", "z")]},
              {"dim": "year", "ctx": 1, "items": [it(1, "y11", "p")]},
              {"dim": "year", "ctx": 2, "items": [it(1, "y21", "q"), it(3, "y23")]},                 # 2단계 안 3차년도 = 그 단계의 차년도 수를 넘는다
              {"dim": "year", "ctx": None, "items": [it(1, "f1", "r"), it(5, "f5", "w")]},          # 단계 항목 밖에서 찾은 차년도 묶음이 2단계 블록을 덮는다 · 5차년도 = 범위 밖
              {"dim": "year", "ctx": "?", "items": [it(1, "q1", "u")]},                              # 자리표시 단계 안
              {"dim": "stageYear", "items": [it((2, 2), "sy", "x"), it((2, 3), "sy3", "x3"), it(("N", "N"), "syn", "xn")]},
              {"dim": "year", "ctx": None, "items": [it("N", "n1", "z")]},                           # 자리표시 차년도 — 바깥 단계는 남고 차년도는 비운다
              {"dim": "stage", "items": [it(3, "s3", "k")]},                                         # 값에 없는 단계
              {"dim": "year", "yearBase": 2, "ctx": None, "items": [it(1, "nb", "v"), it(3, "nb3", "v3")]},
              {"dim": "sub", "items": [it(1, "sub1", "a")]}]
    best, inside = Z._memberships(groups, v, ["인텍"])
    lab = lambda i: Z._auto_label(best.get(i), None, None, None, [2, 2])  # noqa: E731
    sy = lambda i: ((lab(i)[0] or {}).get("stage"), (lab(i)[0] or {}).get("year"))  # noqa: E731
    assert sy("p") == (1, 1) and sy("q") == (2, 3) and sy("y21") == (2, 3)       # 단계 안 차년도 → 전체 차례
    assert sy("y23") == (None, None) and lab("y23")[0] is None                  # 범위 밖 — 비운다(라벨도 없다)
    assert sy("r") == (2, 3)                                                    # 단계는 정해졌는데 차년도(1)가 그 단계의 것이 아니다 → 단계 안 차년도로
    assert sy("w") == (None, None) and sy("u") == (None, None)
    assert sy("x") == (2, 4) and sy("x3") == (None, None) and sy("xn") == (None, None)
    assert sy("z") == (2, None) and sy("k") == (None, None) and sy("a") == (1, None)
    assert sy("v") == (2, 3) and sy("v3") == (None, None)                       # 「다음 연도」 표(yearBase) — 전체 차례 그대로 · 범위 밖은 비움
    assert lab("x")[1] is True and lab("q")[1] is False and lab("a")[1] is False   # 단계를 차년도에서 채웠나(단계 항목이 말한 것이 아니다)
    assert inside == {}
    assert Z._memberships([{"dim": "org", "table": "t9", "items": []}, {"dim": "stageYear", "table": "t9", "items": []}, {"dim": "stage", "table": "t8", "items": []}], v, [])[1] == {"t9": {"org", "year"}}
    v13 = core.norm_values({"stages": [1, 3], "orgs": {"lead": "인텍", "joint": []}})
    g13 = [{"dim": "stage", "items": [it(1, "s1", "a"), it(2, "s2", "y1", "y2", "y3", "p1", "p2", "p3")]},
           {"dim": "year", "ctx": 2, "items": [it(1, "y1", "p1"), it(2, "y2", "p2"), it(3, "y3", "p3")]}]
    best = Z._memberships(g13, v13, [])[0]
    assert [Z._auto_label(best[i], None, None, None, [1, 3])[0]["year"] for i in ("p1", "p2", "p3")] == [2, 3, 4]   # 2단계 안 「2차년도」 는 번호만 보면 2단계의 것(전체 차례 2)처럼 보인다 — 묶음의 맥락으로 3


def test_path_org_reads_the_paragraph_as_it_is_now():
    node = lambda nid, text, role="label", parent=None, letter="": {"id": nid, "para": nid, "role": role, "letter": letter, "text": text, "parent": parent}  # noqa: E731
    para = lambda text: {"type": "paragraph", "text": text}  # noqa: E731
    lab = node("p1", f"[공동연구개발기관1 : {J1}]")
    sub = node("p2", "세부 내용", "heading")
    assert Z._path_org([sub, lab], {"p1": para(f"   [공동연구개발기관1 : {J1}] ※ {J2} 와 협력"), "p2": para("o 세부 내용")}, KEYS) == ("org", J1)
    assert Z._path_org([sub, lab], {"p1": para(f"[공동연구개발기관1 : {J2}]"), "p2": para("o 세부 내용")}, KEYS) == ("org", J2)       # 그래프의 옛 글(가나대)이 아니라 지금 글
    assert Z._path_org([sub, lab], {"p1": para("□ 공통 제목"), "p2": para("o 세부 내용")}, KEYS) is None                              # 지금 글은 기관 라벨이 아니다
    assert Z._path_org([sub, lab], {"p2": para("o 세부 내용")}, KEYS) is None                                                        # 그 문단이 지금 문서에 없다
    assert Z._path_org([sub, lab], {"p1": {"type": "table"}, "p2": para("o 세부 내용")}, KEYS) is None
    assert Z._path_org([lab], {"p1": para("[공동연구개발기관N(기관명 기입)]")}, KEYS) == ("unknown", None)                            # 이름을 못 읽음
    assert Z._path_org([lab], {"p1": para(f"[공동연구개발기관 : {J1}, {J2}]")}, KEYS) == ("unknown", None)                            # 이름이 둘
    assert Z._path_org([lab], {"p1": para(f"[공동연구개발기관2 : {J1}]")}, KEYS) == ("org", J1)                                      # 번호는 안 본다(이름이 정체다)
    sec = node("p3", "연구개발비 세부 사용계획", "heading", letter="8-3.")
    assert Z._path_org([sub, sec, lab], {"p1": para(f"[공동연구개발기관1 : {J1}]"), "p2": para("o 세부"), "p3": para(" 8-3. 연구개발비 세부 사용계획")}, KEYS) is None   # 절 제목이 먼저 — 그 바깥은 안 본다
    assert Z._path_org([sub, sec, lab], {"p1": para(f"[공동연구개발기관1 : {J1}]"), "p2": para("o 세부")}, KEYS) is None               # 절 제목 문단이 없어져도 옛 글이 절 제목이면 멈춘다
    plain = node("p4", "주관연구개발기관 현황", "heading")
    assert Z._path_org([plain], {"p4": para("주관연구개발기관 현황")}, KEYS) is None                                                 # 구분 라벨이 아닌 제목


def test_stale_graph_label_does_not_fill_the_blocks_under_it():
    """그래프에는 기관 라벨로 남아 있지만 지금 글이 바뀐(또는 없어진) 문단 — 그 아래 블록에 기관을 채우지 않는다. 지금 글이 다른 기관의 라벨이면 그 기관으로 읽는다."""
    b = _base()
    info, s = b["info"], b["side"]
    tid = next(i for i in info["order"] if info["kinds"][i] == "tbl" and info["auto"].get(i, {}).get("ev", {}).get("org") == "path")
    assert info["auto"][tid]["org"] == J2
    top = [x for x in s["blocks"] if not x.get("captionOf")]
    k = next(n for n, x in enumerate(top) if x["id"] == tid)
    label = next(x["id"] for x in reversed(top[:k]) if x["type"] == "paragraph" and "공동연구개발기관2" in x["text"])
    _, changed = _edited(lambda d: d.set_text(label, "    [참고 자료]"))
    assert tid not in changed["auto"]
    _, renamed = _edited(lambda d: d.set_text(label, f"    [공동연구개발기관2({J1})]"))
    assert renamed["auto"][tid]["org"] == J1 and renamed["auto"][tid]["ev"] == {"org": "path"}
    gone = Z.read(_snap([x for x in s["blocks"] if x["id"] != label], s["values"], s["graph"], s["tables"]))   # 그 라벨 문단이 없어진 문서 — 그 아래 블록은 더는 다라연의 자리가 아니다
    assert gone["auto"].get(tid, {}).get("org") != J2 and label not in gone["order"]


# ---- 자동 판독: 표 안의 값 읽기 ------------------------------------------------------------------------------------

def test_year_value_reads_only_what_is_written():
    assert [Z._year_value(t, [2]) for t in ("2차년도", "2차년도(2027년)", " 2 ", "1년차", "1단계 2차년도", "1차년도 ※ 안내")] == [2, 2, 2, 1, 2, 1]
    assert [Z._year_value(t, [2]) for t in ("3차년도", "0", "2026", "", None, "2차년도 목표", "2단계 1차년도", "약 2")] == [None] * 8
    assert [Z._year_value(t, [2, 2]) for t in ("2단계 1차년도", "2단계-2차년도", "(1단계)2차년도", "1단계 1차년도(2026년)")] == [3, 4, 2, 1]
    assert [Z._year_value(t, [2, 2]) for t in ("1차년도", "3", "3단계 1차년도", "2단계 3차년도")] == [None] * 4   # 단계가 둘 이상인데 단계가 안 적힘 — 짐작하지 않는다 · 범위 밖


def test_tag_cells_are_the_bare_word_and_have_no_value_of_their_own():
    """이름표 칸 = 괄호 안과 빈칸을 뗀 글이 낱말 그대로일 때만 — 역할이 든 이름표와 낱말이 섞인 칸은 읽지 않는다."""
    kinds = lambda t: Z._tag_kinds(t, KEYS)  # noqa: E731
    for t in ("연구개발기관명", "연구개발기관", "기 관 명", "연구개발\n기관", "수행기관", "수행기관명", "참여기관", "참여기관명", "소유권자", "연구개발기관명5)", "연구개발기관명 (소유권자)", "기관명\n(주관/공동)",
              "소속\n기관\n(역할)", "소속기관명", "보유기관", "보유기관명"):   # 참여연구원 표 · 연구시설·장비 보유현황 표(2026-11-17 사용자 그림)
        assert kinds(t) == ("org",), t
    for t in ("주관연구개발기관", "공동연구개발기관", "주관연구개발기관명", "해당과제의 주관연구개발기관", "공동연구개발기관(책임자)", "주관기관명", "기술실시기관명", "전문기관명", "중앙행정기관명2)", "기관명/구분",
              "위탁연구개발기관", f"연구개발기관명 : {J1}", f"기관명({J1})", J1, "", None, "과제명", "연구개발기관의 연구개발과제 지원 담당자 현황과 연락처를 적는 칸"):
        assert kinds(t) == (), t   # 역할이 든 이름표 · 다른 낱말이 붙은 칸 · 값이 든 칸 · 긴 칸
    for t in ("연차", "차년도", "년차", "연차\n(단계)", "(단계)구입연차", "사용연차", "해당 연차", "수행연차", "집행연차", "개발\n연차", "해당차년도", "차년도1)"):
        assert kinds(t) == ("year",), t
    for t in ("연차휴가 일수", "연차별 예산", "연차보고서", "2차년도", "1차년도 목표", "3년차", "(x단계)x차년도(2021년)", "기관명/차년도", "매출발생 연도", "구축연도"):
        assert kinds(t) == (), t


def test_value_cells_name_an_org_only_when_the_whole_cell_is_the_name():
    """값 칸의 기관은 「※」 뒤와 괄호 안을 떼고 정리한 글이 과제 기관 열쇠와 통째로 같을 때만 — 품은 이름(「한국선급엔지니어링」)은 그 기관이 아니다."""
    keys = ["한국선급", "씨드로닉스", "주관기관(미입력)", "가나(KR)"]
    org = lambda t: Z._cell_org(t, keys)  # noqa: E731
    for t in ("한국선급", " 한국 선급 ", "㈜한국선급", "(주)한국선급", "주식회사 한국선급", "한국선급\n(주관)", "한국선급(김○○ 외 2)", "한국선급 ※ 주관연구개발기관", "한국선급（본부）"):
        assert org(t) == "한국선급", t
    assert org("씨드로닉스 주식회사") == "씨드로닉스" and org("씨드로닉스(김동훈 외 2)") == "씨드로닉스" and org("씨드로닉스(주)(부설연구소(본사))") == "씨드로닉스"
    assert org("주관기관(미입력)") == "주관기관(미입력)" and org("가나(KR)") == "가나(KR)"   # 이름에 괄호가 든 기관은 괄호째로 견준다
    for t in ("한국선급엔지니어링", "한국선급 / 주관", "한국선급, 씨드로닉스", "한국선급 외 2", "(한국선급)", "가나", "", None, "※ 한국선급", "한국선급1)"):
        assert org(t) is None, t
    assert Z._names("한국선급엔지니어링", keys) == ["한국선급"]   # 라벨 줄·윗 제목의 「문장 속 이름 찾기」 는 그대로 — 값 칸 판독과 함수가 갈린다


def test_table_read_whole_table_rows_merged_cells_and_conflicts():
    read = lambda rows, stages=(2,), skip=(): Z._table_read(_tbl(rows), KEYS, list(stages), skip)  # noqa: E731
    # ① 표 전체 — 이름표 칸의 오른쪽 이웃에 값, 아래에는 값 없음
    whole, per = read([["연구개발기관명", J1, "과제책임자", "홍길동"], ["차년도", "2차년도(2027년)", "비고", ""]])
    assert whole == {"org": ("org", J1, None), "year": 2} and per == {}
    assert read([["연구개발기관명", ""], ["대표자", "홍길동"]]) == (None, {})                      # ⑥ 빈 값 칸 — 아무것도 안 읽는다
    assert read([["연구개발기관명", "다른회사㈜"], ["대표자", J1]]) == (None, {})                  # ⑦ 과제 기관이 아닌 이름 · 이름표 없는 칸의 이름
    assert read([["연구개발기관명", f"{J1}, {J2}"]]) == (None, {}) and read([["연구개발기관명", f"{J1}엔지니어링"]]) == (None, {})   # 통째로 일치할 때만
    assert read([["연구개발기관명", f"㈜ {J1}(홍길동 외 2)"]])[0] == {"org": ("org", J1, None)}
    assert read([["주관연구개발기관", LEAD], ["공동연구개발기관", J1]]) == (None, {})              # 역할이 든 이름표는 소유의 근거가 아니다 — 읽지 않는다
    assert read([["주관연구개발기관", LEAD], ["연구개발기관명", J1]])[0] == {"org": ("org", J1, None)}   # 공동기관의 표에 주관기관이 함께 적혀 있어도 그 표는 그 공동기관의 것
    assert read([["주관연구개발기관", "기관명", LEAD], ["대표자", "성명", "홍길동"]]) == (None, {})    # 역할 줄의 「기관명 | 이름」 — 왼쪽 칸이 역할 줄의 머리
    assert read([["연구개발기관명", LEAD], ["수행기관", J1]])[0] == {"org": ("conflict", None, {"byCell": [LEAD, J1]})}   # 한 표에서 표 전체 기관이 서로 다르다
    assert read([["수행기관명", LEAD, "연구개발기관명", LEAD]])[0] == {"org": ("org", LEAD, None)}
    assert read([["기관명", LEAD, J1, J2], ["구분", "", "", ""]]) == (None, {})                    # 값이 옆으로 이어짐 — 값마다 열이 있는 머리 행
    assert read([["연구개발기관명", J1]], skip=("org",)) == (None, {})                             # 그 표 안에 기관 묶음(행·열)이 있다
    assert read([[J1, "연구개발기관명"]]) == (None, {})                                            # 왼쪽에 값이 있는 꼴은 읽지 않는다
    assert read([["차년도", "1차년도"], ["연차", "2"]])[0] is None                                 # 표 전체 차년도가 서로 다르면 비운다
    assert read([["차년도", "1차년도"]], stages=(2, 2))[0] is None and read([["차년도", "2단계 1차년도"]], stages=(2, 2))[0] == {"year": 3}
    assert read([["연차휴가 일수", "2"]]) == (None, {}) and read([["(단계)구입연차", "2"]])[0] == {"year": 2}
    # ② 행 — 이름표 칸 아래의 값: 그 값 칸이 걸친 행의 모든 칸 · ③ 세로로 합친 이름 칸
    whole, per = read([["기관명", "연차", "내용"], [(J1, 2, 1), "1", "가"], [None, "2", "나"], [J2, "3", "다"], ["합계", "", "라"], ["", "", ""]])
    assert whole is None
    assert {i: e.get("org") for i, e in per.items()} == {"t1_0": ("org", J1, None), "t1_1": ("org", J1, None), "t1_2": ("org", J1, None), "t2_1": ("org", J1, None), "t2_2": ("org", J1, None),
                                                         "t3_0": ("org", J2, None), "t3_1": ("org", J2, None), "t3_2": ("org", J2, None)}
    assert {i: e.get("year") for i, e in per.items() if "year" in e} == {"t1_1": 1, "t1_2": 1, "t2_1": 2, "t2_2": 2}   # ④ 「연차」 열 — 3 은 범위 밖 · 합친 기관 칸은 두 해에 걸쳐 차년도가 없다
    _, per = read([["구분", "기관명", "값"], [("1단계", 2, 1), J1, "가"], [None, J2, "나"]])
    assert "t1_0" not in per and per["t1_1"]["org"][1] == J1 and per["t2_2"]["org"][1] == J2                          # 두 기관의 행에 걸친 칸은 어느 기관의 것도 아니다
    _, per = read([["연구개발기관명", "기술실시기관명", "값"], [J1, J2, "가"], [J2, J2, "나"]])
    assert per["t1_2"]["org"] == ("org", J1, None) and per["t2_2"]["org"] == ("org", J2, None)                          # 「기술실시기관명」 은 이름표가 아니다 — 그 열의 이름은 안 본다
    _, per = read([["연구개발기관명(소유권자)", "수행기관", "값"], [J1, J2, "가"], [J2, J2, "나"]])
    assert per["t1_2"]["org"] == ("conflict", None, {"byCell": [J1, J2]}) and per["t1_0"]["org"][0] == "conflict" and per["t2_2"]["org"] == ("org", J2, None)   # 한 행의 기관 열 둘이 다르면 conflict
    whole, per = read([["연구개발기관명", LEAD, ""], ["기관명", "내용", ""], [J1, "가", ""], [J2, "나", ""]])
    assert whole is None and per["t2_1"]["org"][1] == J1                                                                # 행마다 기관이 갈리는 표는 한 기관의 표가 아니다
    assert read([["과제명", "내용"], [J1, "가"]]) == (None, {}) and Z._table_read({"id": "e", "type": "table", "cells": []}, KEYS, [2]) == (None, {})
    # 이름표의 아래쪽 범위 — 다음 머리 행 앞까지 · 같은 열 · 같은 너비
    whole, per = read([["연구개발기관명", "내용"], [LEAD, "연구"], ["수탁회사", "연구개발기관명"], [J1, J2]])       # 표 중간에서 열의 뜻이 바뀐다
    assert whole is None and {i: e["org"][1] for i, e in per.items()} == {"t1_0": LEAD, "t1_1": LEAD, "t3_0": J2, "t3_1": J2}   # 앞 이름표는 새 머리 행 앞까지만 — 마지막 행이 conflict 가 되지 않는다
    assert read([[("연차", 1, 2), None], ["금액(억원)", "비고"], ["2", "운영비"]]) == (None, {})                    # 여러 열을 덮은 머리 아래의 세부 열(금액)은 그 머리의 값이 아니다
    assert read([[("연차별 예산", 1, 2), None], ["금액(억원)", "비고"], ["2", "운영비"]]) == (None, {})
    _, per = read([[("연구개발기관명", 2, 1), ("연구개발비", 1, 2), None], [None, "연차", "금액"], [J1, "1", "100"], [J2, "2", "2"]])   # 여러 줄 머리 — 이어진 머리 행은 건너뛴다
    assert {i: (e.get("org", (0, None))[1], e.get("year")) for i, e in per.items()} == {"t2_0": (J1, 1), "t2_1": (J1, 1), "t2_2": (J1, 1), "t3_0": (J2, 2), "t3_1": (J2, 2), "t3_2": (J2, 2)}
    _, per = read([["기관명", "값"], [(J1, 3, 1), "가"], [None, "나"], [None, "값"], [J2, "다"]])                      # 세로로 합친 값 칸(1~3행)이 걸친 행 — 그 안에 온전히 든 칸
    assert {i: e["org"][1] for i, e in per.items()} == {"t1_0": J1, "t1_1": J1, "t2_1": J1, "t3_1": J1, "t4_0": J2, "t4_1": J2}


def test_org_columns_known_by_their_values_name_the_org_of_their_rows():
    """「기관 열」(② §2 — 2026-11-17 사용자 그림: 일정표 「개발 내용 | 서브모듈 기초설계\\n(인텍전기전자)」 · 보유현황 표 첫 열의 합친 기관 이름 칸): 기관 이름표 칸이 없는 표에서
    칸의 값(기관 이름 그대로 · 「… (기관 이름)」 으로 끝남)이 기관을 말하는 칸이 되풀이되는 열 → 그 칸이 걸친 행의 기관."""
    tail = lambda t: Z._tail_org(t, KEYS)  # noqa: E731
    for t in (f"기초설계\n({J1})", f"기초설계 ({J1}) ", f"기초설계（{J1}）", f"기술 기준(안)\n({J1})", f"설계\n(㈜{J1})", f"설계\n({J1}) ※ 주관"):
        assert tail(t) == J1, t
    for t in (f"({J1})", f"({J1}) 기초설계", f"설계\n({J1}, {J2})", f"설계\n({J1}엔지니어링)", "기술 기준(안)", "설계\n(외부기관)", "", None):
        assert tail(t) is None, t   # 괄호 앞 글 없음 · 끝이 아님 · 여러 기관 · 품은 이름 · 과제 기관 아님
    read = lambda rows: Z._table_read(_tbl(rows), KEYS, [4])  # noqa: E731
    head = [("일련\n번호", 2, 1), ("개발 내용", 2, 1), ("추진 일정", 1, 2), None]
    gantt = [head, [None, None, "1차년도", "2차년도"],
             [("1", 2, 1), (f"기초설계\n({J1})", 2, 1), "", ""], [None, None, "", ""],
             [("2", 2, 1), (f"시작품 제작\n({J2})", 2, 1), "", ""], [None, None, "", ""],
             ["3", f"검증\n({J1})", "", ""]]
    whole, per = read(gantt)
    assert whole is None                                                                                       # 행마다 기관이 갈리는 표는 한 기관의 표가 아니다
    assert {i for i, e in per.items() if e["org"] == ("org", J1, None)} == {"t2_0", "t2_1", "t2_2", "t2_3", "t3_2", "t3_3", "t6_0", "t6_1", "t6_2", "t6_3"}
    assert {i for i, e in per.items() if e["org"] == ("org", J2, None)} == {"t4_0", "t4_1", "t4_2", "t4_3", "t5_2", "t5_3"}
    assert not [i for i in per if i.startswith(("t0_", "t1_"))]                                               # 머리 행
    assert read([["개발 내용", "비고"], [f"기초설계\n({J1})", ""], ["시작품 제작", ""]]) == (None, {})          # 한 칸뿐 — TAIL_MIN 미만
    assert read([["사용용도(업체)", "금액"], ["사무용품 구입", "1"], ["회의", "2"], ["출장", "3"], [f"형식승인\n({LEAD})", "4"], [f"적합성 평가\n({LEAD})", "5"]]) == (None, {})   # 열의 절반 미만 — 상대 업체
    _, per = read([["연구개발기관", "사용용도(업체)"], [(J1, 2, 1), f"형식승인\n({LEAD})"], [None, f"적합성 평가\n({LEAD})"]])
    assert {e["org"] for e in per.values()} == {("org", J1, None)}                                           # 기관 이름표 칸이 있으면 그것이 먼저 — 끝 괄호는 안 본다
    _, per = read([["연차", "개발 내용"], ["1", f"기초설계\n({J1})"], ["2", f"시작품\n({J2})"]])
    assert per["t1_0"] == {"org": ("org", J1, None), "year": 1} and per["t2_1"] == {"org": ("org", J2, None), "year": 2}   # 차년도 이름표는 막지 않는다
    # 기관 이름 그대로인 칸의 열 — 첫 열의 세로로 합친 이름 칸(머리 낱말이 이름표 목록에 없어도) · 못 읽은 이름의 행은 비움
    whole, per = read([["구분", "장비명", "금액"], [(f"㈜\n{LEAD}", 2, 1), "오실로스코프", "1"], [None, "항온항습조", "2"], [(f"{J1}\n(연구실 자체 운영 장비)", 1, 1), "발전기", "3"],
                       [("다른대학교 산학협력단", 1, 1), "계측기", "4"]])
    assert whole is None and {i: e["org"][1] for i, e in per.items()} == {"t1_0": LEAD, "t1_1": LEAD, "t1_2": LEAD, "t2_1": LEAD, "t2_2": LEAD, "t3_0": J1, "t3_1": J1, "t3_2": J1}
    assert read([["주관연구개발기관", LEAD], ["공동연구개발기관", J1], ["공동연구개발기관", J2]]) == (None, {})   # 역할 줄의 이름 — 참여 기관을 적는 공통 표는 기관 열이 아니다
    assert read([["과제명", "내용"], [J1, "가"]]) == (None, {})                                                   # 이름 한 칸
    assert read([["번호", "인증기준", "발행기관"], ["1", "규칙 6편", LEAD], ["2", "지침", J1]]) == (None, {})       # 첫 열이 아닌 열의 이름 그대로인 칸 — 발행기관일 수 있다
    assert read([["과제명", "주관연구개발기관"], ["가", f"과제\n({LEAD})"], ["나", f"과제\n({J1})"]]) == (None, {})   # 맨 위 칸이 역할 낱말인 열
    assert read([["구분", "장비명"], [(LEAD, 2, 1), "가"], [None, "나"], [("", 1, 1), "다"]]) == (None, {})          # 기관이 하나뿐 — 표 전체의 일(LLM 검토의 후보)
    assert read([["개발 내용", "비고"], [f"설계\n({LEAD})", ""], [f"제작\n({LEAD})", ""]]) == (None, {})


def test_join_of_group_and_cell_evidence():
    stages = [2, 2]
    lab = lambda m=None, org=None, ev="group", cell=None: Z._auto_label(m, org, ev, cell, stages)[0]  # noqa: E731
    g = ("org", J1, None)
    assert lab(org=g, cell={"org": ("org", J1, None)}) == _lab(J1)                                             # 같은 기관 — 묶음 근거 그대로
    x = lab(org=g, cell={"org": ("org", J2, None)})
    assert (x["orgKind"], x["org"], x["why"], x["ev"]) == ("conflict", None, {"byGroup": J1, "byCell": [J2]}, {"org": "group"})   # 다르면 conflict — 둘 다 근거로
    x = lab(org=g, ev="path", cell={"org": ("conflict", None, {"byCell": [J1, J2]})})
    assert x["orgKind"] == "conflict" and x["why"] == {"byPath": J1, "byCell": [J1, J2]}
    assert lab(cell={"org": ("org", J2, None)}) == _lab(J2, ev="cell")                                         # 한쪽만 있으면 그것
    assert lab(org=("unknown", None, None), cell={"org": ("org", J2, None)}) == _lab(J2, ev="cell")            # 기관 모름 자리 — 칸의 이름이 말해 준다
    x = lab(org=("conflict", None, {"byNo": J1, "byName": [J2]}), cell={"org": ("org", J2, None)})
    assert x["orgKind"] == "conflict" and x["why"] == {"byNo": J1, "byName": [J2], "byCell": [J2]}
    year = lambda y, mode="abs": {"year": (1, (y, mode))}  # noqa: E731
    assert lab(year(3), cell={"year": 3}) == _lab(stage=2, year=3)
    assert lab(cell={"year": 3}) == _lab(stage=2, year=3, ev="cell")
    x = lab(year(3), cell={"year": 4})                                                                          # 차년도가 다르다 — 비우고 근거를 남긴다(단계는 둘 다 2)
    assert (x["stage"], x["year"], x["why"], x["ev"]) == (2, None, {"year": {"byGroup": 3, "byCell": 4}}, {"stage": "group"})
    x = lab(year(1), cell={"year": 3})                                                                          # 단계도 다르다 — 값은 안 남아도 엇갈린 근거는 남는다(「값 없음」 과 다르다)
    assert x == {"org": None, "orgKind": None, "stage": None, "year": None, "src": {}, "ev": {}, "why": {"stage": {"byGroup": 1, "byCell": 2}, "year": {"byGroup": 1, "byCell": 3}}}
    assert lab() is None and lab({"year": (1, (None, "abs"))}) is None                                           # 값도 근거도 없으면 라벨이 없다
    x = lab({"stage": (1, 1)}, org=g, cell={"year": 3})
    assert (x["org"], x["stage"], x["year"]) == (J1, None, None) and x["why"] == {"stage": {"byGroup": 1, "byCell": 2}, "year": {"byGroup": None, "byCell": 3}}
    x = lab({"stage": (1, 2)}, cell={"year": 3})
    assert (x["stage"], x["year"], x["ev"]) == (2, 3, {"stage": "group", "year": "cell"})


def test_read_takes_names_and_years_written_in_table_cells():
    """문서의 표 칸에 글을 넣어 — ① 「연구개발기관명 | 이름」 = 표 전체 ② 기관 열 아래 이름 = 그 행 ④ 「연차」 열 ⑤ 묶음의 기관과 다르면 conflict ⑥ 빈 값 칸 ⑦ 과제 기관이 아닌 이름."""
    found = {}

    def edit(d):
        t = found["overview"] = D.table_after(d, "□ 과제개요")                       # 공통 자리의 표
        d.set_text(D.cell(d, t, 1, 0)["id"], "연구개발기관명")
        d.set_text(D.cell(d, t, 1, 1)["id"], J1)
        t = found["transfer"] = D.table_after(d, "o 국가연구개발사업 수행과제에 대한 기술이전 실적")   # 머리 「연구개발기관명 | … | 기술실시기관명 | …」
        d.set_text(D.cell(d, t, 2, 0)["id"], J2)
        d.set_text(D.cell(d, t, 2, 3)["id"], LEAD)
        d.set_text(D.cell(d, t, 3, 0)["id"], "다른회사㈜")
        t = found["sales"] = D.table_after(d, "o 국가연구개발사업 수행과제에 대한 사업화 실적")
        d.set_text(D.cell(d, t, 1, 9)["id"], "연차")
        d.set_text(D.cell(d, t, 3, 9)["id"], "2차년도")
        d.set_text(D.cell(d, t, 4, 9)["id"], "7")
        t = found["lead"] = D.table_after(d, "(1) 주관연구개발기관책임자")           # 인텍 묶음 안의 표 「직장 | 기관명 | …」
        d.set_text(D.cell(d, t, 2, 2)["id"], J1)
        t = found["joint"] = D.table_after(d, f"(2) 공동연구개발기관책임자({J1})")   # 가나대 묶음 안의 표
        d.set_text(D.cell(d, t, 2, 2)["id"], f"㈜ {J1}")
        found["ip"] = D.table_after(d, "o 동 과제와 관련된 기보유 지재권 출원 및 등록 현황")   # 손대지 않은 빈 표
    doc, info = _edited(edit)
    auto, was = info["auto"], _base()["info"]["auto"]
    cells = lambda t: next(b for b in D.top(doc) if b["id"] == t)["cells"]  # noqa: E731
    assert found["overview"] not in was and auto[found["overview"]] == _lab(J1, ev="cell")                              # ①
    row = lambda t, r: [c["id"] for c in cells(t) if c["row"] == r]  # noqa: E731
    t = found["transfer"]
    assert t not in auto and len(row(t, 2)) == 7 and all(auto[c] == _lab(J2, ev="cell") for c in row(t, 2))             # ② 그 행의 모든 칸 — 기관 열이 둘이어도 「연구개발기관명」 열을 믿는다
    assert not [c for c in row(t, 3) + row(t, 1) + row(t, 0) if c in auto]                                              # ⑦ · 머리 행
    t = found["sales"]
    assert t not in auto and all(auto[c] == _lab(stage=1, year=2, ev="cell") for c in row(t, 3)) and not [c for c in row(t, 4) if c in auto]   # ④ · 범위 밖
    x = auto[found["lead"]]
    assert was[found["lead"]]["org"] == LEAD and (x["orgKind"], x["org"], x["why"]) == ("conflict", None, {"byGroup": LEAD, "byCell": [J1]})   # ⑤
    assert auto[found["joint"]] == was[found["joint"]] == _lab(J1)                                                      # 같은 기관이면 그대로
    assert found["ip"] not in auto and not [c["id"] for c in cells(found["ip"]) if c["id"] in auto]                     # ⑥
    view = Z.build(info, [], [], ["org", "year"])
    assert Z.label_of(view, D.cell(doc, found["overview"], 0, 3)["id"]) == auto[found["overview"]]                      # 표 전체 — 칸은 표의 라벨을 물려받는다
    assert Z.label_of(view, row(found["transfer"], 2)[4])["org"] == J2 and Z.label_of(view, row(found["transfer"], 3)[0]) is None
    assert view["counts"]["conflicts"] == 1 and next(z for z in view["zones"] if found["lead"] in z["ids"])["text"] == "기관 확인 필요"
    assert found["lead"] not in view["cells"] and Z.label_of(view, D.cell(doc, found["lead"], 0, 0)["id"])["orgKind"] == "conflict"   # 표가 확인 필요면 그 칸들도(묶음의 기관으로 남지 않는다)
    z = next(z for z in view["zones"] if found["overview"] in z["ids"])
    assert z["ids"] == [found["overview"]] and z["text"] == J1 and z["mark"] is None


def test_table_read_on_the_fixture_tables_with_merged_name_cells():
    b = _base()
    doc, info = b["side"]["doc"], b["info"]
    tid = D.table_after(doc, "(1) 연구시설·장비 구축(임차)계획")   # 기관-연도 표 — 「연구개발 기관」 열의 이름 칸이 두 해의 행에 걸쳐 합쳐져 있다
    t = next(x for x in b["side"]["blocks"] if x["id"] == tid)
    whole, per = Z._table_read(t, KEYS, [2])
    name = next(c for c in t["cells"] if c["col"] == 0 and c["text"].strip() == LEAD)
    assert whole is None and name["rowSpan"] == 2
    rows = [c["id"] for c in t["cells"] if name["row"] <= c["row"] < name["row"] + 2]
    assert len(rows) > 9 and all(per[c]["org"] == ("org", LEAD, None) for c in rows)   # ③ 걸친 행 모두
    assert all(info["auto"][c]["org"] == LEAD and info["auto"][c]["ev"]["org"] == "group" for c in rows)   # 묶음이 읽은 기관과 같다 — 근거는 묶음
    cost = next(x for x in b["side"]["blocks"] if x["id"] == D.table_after(doc, "8-1. 연구개발비 지원·부담계획", 1))   # 「연차 | 연구개발기관」 열 — 묶음은 연차만 읽는다
    got = [info["auto"][c["id"]] for c in cost["cells"] if c["text"].strip() == J1]
    assert got and all(x["org"] == J1 and x["ev"]["org"] == "cell" and x["year"] in (1, 2) and x["ev"]["year"] == "group" for x in got)


def test_review_counterexamples_from_read_to_build_to_label_of():
    """astra 결과 검토의 반례(P1-1 · P2-6 · P1-2 · P1-5)를 손으로 만든 문서로 `read → build → label_of` 까지 잇는다 — 잘못 확정하지 않고, 엇갈린 근거를 지우지 않는다."""
    KR, GN, IT = "한국선급", "가나대", "인텍"
    V = core.norm_values({"stages": [2], "orgs": {"lead": KR, "joint": [GN, IT]}})
    val = lambda lab: None if lab is None else (lab["orgKind"], lab["org"], lab["stage"], lab["year"])  # noqa: E731

    def run(*items, values=V, origins=(), marks=()):
        blocks = _doc(*items)
        info = Z.read(_snap(blocks, values))
        return info, Z.build(info, list(marks), list(origins), ["org", "stage", "year"])

    def cell(view, table, r, c):
        return Z.label_of(view, f"c{table[1:]}_{r}_{c}")
    # P1-1 — 과제 기관 이름을 품은 다른 회사는 그 기관이 아니다(값 칸은 통째로 일치할 때만)
    info, view = run("개요", [["연구개발기관명", f"{KR}엔지니어링"]], [["연구개발기관명", f"{KR}(김○○ 외 2)"]], [["연구개발기관명", f"{GN} 주식회사"]], [["연구개발기관명", f"{KR} / 주관"]],
                     [["기관명", "내용"], [f"{KR}엔지니어링", "가"], [f"㈜{KR}", "나"]])
    assert "t2" not in info["auto"] and Z.label_of(view, "t2") is None and cell(view, "t2", 0, 1) is None
    assert val(Z.label_of(view, "t3")) == ("org", KR, None, None) and view["blocks"]["t3"]["ev"] == {"org": "cell"} and val(cell(view, "t3", 0, 0)) == ("org", KR, None, None)   # 괄호 꼬리
    assert val(Z.label_of(view, "t4")) == ("org", GN, None, None) and Z.label_of(view, "t5") is None                                                                             # 「주식회사」 · 「이름 / 주관」
    assert cell(view, "t6", 1, 0) is None and cell(view, "t6", 1, 1) is None and val(cell(view, "t6", 2, 1)) == ("org", KR, None, None)
    assert view["counts"]["conflicts"] == 0 and view["counts"]["unknown"] == 0 and [z["ids"] for z in view["zones"]] == [["t3"], ["t4"]]
    # P2-6 ① 「연차휴가 일수 | 2」 · ② 여러 줄 머리의 금액 — 차년도가 아니다
    info, view = run("개요", [["연차휴가 일수", "2"]], [[("연차별 예산", 1, 2), None], ["금액(억원)", "비고"], ["2", "운영비"]], [[("연차", 1, 2), None], ["금액(억원)", "비고"], ["2", "운영비"]])
    assert info["auto"] == {} and view["blocks"] == {} and view["cells"] == {} and cell(view, "t3", 2, 0) is None
    # P2-6 ③ 표 중간에서 열의 뜻이 바뀐다 — 앞 이름표는 새 머리 행 앞까지만
    info, view = run("개요", [["연구개발기관명", "내용"], [KR, "연구"], ["수탁회사", "연구개발기관명"], [GN, IT]])
    assert [val(cell(view, "t2", r, 0)) for r in range(4)] == [None, ("org", KR, None, None), None, ("org", IT, None, None)] and val(cell(view, "t2", 3, 1)) == ("org", IT, None, None)
    assert Z.label_of(view, "t2") is None and not [c for c in info["auto"].values() if c["orgKind"] == "conflict"]   # 마지막 행이 conflict 가 되지 않는다
    # P2-6 ④ 역할이 든 이름표 — 공동기관의 표에 주관기관이 같이 적혀 있어도 conflict 가 아니고, 공통 표가 주관기관의 표로 확정되지 않는다
    info, view = run(f"[주관연구개발기관 : {KR}]", "o 내용", f"[공동연구개발기관1 : {GN}]", [["주관연구개발기관", KR], ["연구개발기관명", GN]], f"[공동연구개발기관2 : {IT}]", "o 내용", "3. 다음 장",
                     [["주관연구개발기관", KR], ["과제명", "가"]], [["주관연구개발기관", "기관명", KR], ["대표자", "성명", "홍길동"]])
    assert val(Z.label_of(view, "p3")) == ("org", GN, None, None) and val(Z.label_of(view, "t4")) == ("org", GN, None, None) and view["blocks"]["t4"]["ev"] == {"org": "group"} and "why" not in view["blocks"]["t4"]
    assert val(cell(view, "t4", 0, 1)) == ("org", GN, None, None) and Z.label_of(view, "t8") is None and Z.label_of(view, "t9") is None and cell(view, "t9", 0, 2) is None
    assert view["counts"]["conflicts"] == 0
    # P1-2 ① 묶음은 1차년도인데 표의 행은 2 — 엇갈려 비운 차년도를 build 가 표의 값(1)으로 되살리지 않고, 근거가 남은 칸을 싣는다
    info, view = run("(1) 1차년도", [["기관명", KR], ["연차", "내용"], ["2", "값"]], "(2) 2차년도", "o 내용")
    assert val(Z.label_of(view, "t2")) == ("org", KR, 1, 1) and val(cell(view, "t2", 0, 0)) == ("org", KR, 1, 1) and set(view["cells"]["t2"]) == {"c2_2_0", "c2_2_1"}
    for c in ("c2_2_0", "c2_2_1"):
        lab = Z.label_of(view, c)
        assert val(lab) == ("org", KR, 1, None) and lab["why"] == {"year": {"byGroup": 1, "byCell": 2}} and "year" not in lab["src"] and info["auto"][c]["year"] is None
    year2 = Z.build(info, [_mark(["t2"], {"year": 2})], [], ["year"])   # 표의 차년도를 지정이 정하면 그 칸도 그 차년도 — 엇갈린 근거를 내린다
    lab = Z.label_of(year2, "c2_2_0")
    assert (lab["year"], lab["src"]["year"]) == (2, "mark") and "why" not in lab and "c2_2_0" not in year2["cells"].get("t2", {})
    # P1-2 ② 단계가 둘(각 1차년도) — 1단계 묶음 안의 표가 「2단계 1차년도」 를 말한다: 값은 다 비지만 충돌은 버리지 않는다
    v11 = core.norm_values({"stages": [1, 1], "orgs": {"lead": KR, "joint": [GN]}})
    info, view = run("[1단계]", [["차년도", "2단계 1차년도"], ["내용", "가"]], "[2단계]", "o 내용", values=v11)
    why = {"stage": {"byGroup": 1, "byCell": 2}, "year": {"byGroup": None, "byCell": 2}}
    assert info["auto"]["t2"] == {"org": None, "orgKind": None, "stage": None, "year": None, "src": {}, "ev": {}, "why": why}
    assert view["blocks"]["t2"]["why"] == why and Z.label_of(view, "c2_1_1")["why"] == why and "t2" not in view["cells"]   # 칸은 표와 같다(값도 근거도) — 싣지 않아도 label_of 가 표의 것을 준다
    assert val(Z.label_of(view, "p1")) == (None, None, 1, None) and [z["ids"] for z in view["zones"]] == [["p1"], ["p3"]]  # 값이 없는 블록은 띠가 아니다
    assert (view["counts"]["blocks"], view["counts"]["conflicts"]) == (3, 0)                                               # conflicts = 기관 conflict 인 블록 수 그대로
    # P1-5 — 옛 기록(legacy)의 id 가 지금 문서의 다른 문단에 다시 쓰였어도 그 문단의 기관이 되지 않는다
    old = {"id": "L1", "part": "w1", "name": "기관A.hwpx", "orgs": [GN], "kind": "added", "ids": ["p1"], "at": None, "legacy": True}
    info, view = run("공통 문단", "다음 문단", origins=[old])
    assert Z.label_of(view, "p1") is None and view["blocks"] == {} and view["origins"][0]["ids"] == ["p1"] and view["origins"][0]["legacy"] is True
    _, view = run("공통 문단", "다음 문단", origins=[{**old, "legacy": False}])
    assert val(Z.label_of(view, "p1")) == ("org", GN, None, None) and view["blocks"]["p1"]["src"] == {"org": "origin"}


# ---- 옵션 · 지정 · 출처의 작은 함수 --------------------------------------------------------------------------------

def test_norm_dims():
    assert Z.DIMS == ("org", "stage", "year") and Z.DIM_NAME == {"org": "기관", "stage": "단계", "year": "차년도"} and Z.TEXT_MAX == 60
    assert Z.norm_dims(["year", "org", "year"]) == ["org", "year"] and Z.norm_dims([]) == [] and Z.norm_dims(("stage",)) == ["stage"]
    for bad in ("org", None, {"org": 1}, ["org", "기관"], [1]):
        with pytest.raises(ValueError) as e:
            Z.norm_dims(bad)
        assert "기준" in str(e.value)


def test_norm_label_checks_the_values_against_the_project():
    info = _info()
    assert Z.norm_label({"org": "가나대"}, info) == {"org": "가나대"} and Z.norm_label({"org": "㈜인텍"}, info) == {"org": "인텍"} and Z.norm_label({"org": "(주) 인텍"}, info) == {"org": "인텍"}
    assert Z.norm_label({"org": None, "year": 3, "orgKind": "org", "src": {}}, info) == {"org": None, "year": 3}   # 차년도만 — 단계는 넣지 않는다 · 라벨의 다른 키는 안 본다
    assert Z.norm_label({"stage": 2, "year": 4}, info) == {"stage": 2, "year": 4} and Z.norm_label({"stage": None}, info) == {"stage": None}
    assert Z.norm_label({"stage": "2", "year": None}, info) == {"stage": 2, "year": None}
    for body, word in (({}, "적어도 하나"), ({"note": "x"}, "적어도 하나"), (None, "필요"), ([], "필요"), ({"org": "없는기관"}, "없는 기관"), ({"org": 3}, "기관"), ({"org": " "}, "기관"),
                       ({"stage": 3}, "단계는 1~2"), ({"stage": 0}, "단계"), ({"stage": True}, "단계"), ({"year": 5}, "차년도는 1~4"), ({"year": "x"}, "차년도"), ({"stage": 1, "year": 3}, "2단계의 차년도")):
        with pytest.raises(ValueError) as e:
            Z.norm_label(body, info)
        assert word in str(e.value), (body, str(e.value))
    none = _info(stages=(), orgs=())   # 프로젝트 구성 값이 없는 문서 — 「없음」 만 지정할 수 있다
    assert Z.norm_label({"org": None}, none) == {"org": None}
    for body in ({"org": "인텍"}, {"stage": 1}, {"year": 1}):
        with pytest.raises(ValueError):
            Z.norm_label(body, none)


def test_mark_make_put_prune_and_origin_event():
    m1 = Z.mark_make(["a", "b", "a", 3, ""], {"org": "인텍"}, "메모", at="2026-11-17T09:00:00")
    assert len(m1["id"]) == 8 and m1 == {"id": m1["id"], "ids": ["a", "b"], "label": {"org": "인텍"}, "note": "메모", "by": "user", "at": "2026-11-17T09:00:00"}
    m2 = Z.mark_make(["c"], {"year": None})
    assert m2["id"] != m1["id"] and m2["note"] == "" and m2["at"]
    marks = Z.marks_put(Z.marks_put([], m1), m2)
    assert [m["id"] for m in marks] == [m1["id"], m2["id"]]
    m3 = Z.mark_make(["b", "c", "d"], {"org": "가나대"})
    out = Z.marks_put(marks, m3)   # 한 블록은 한 지정에만 — 새 지정이 가져간 블록은 옛 지정에서 빠지고 빈 지정은 지워진다
    assert [(m["id"], m["ids"]) for m in out] == [(m1["id"], ["a"]), (m3["id"], ["b", "c", "d"])] and marks[0]["ids"] == ["a", "b"] and len(marks) == 2   # 새 목록(받은 목록은 그대로)
    again = Z.marks_put(out, {**m1, "ids": ["a", "d"], "label": {"stage": 1}})   # 같은 id — 그 자리에서 바꾼다
    assert [(m["id"], m["ids"], m["label"]) for m in again] == [(m1["id"], ["a", "d"], {"stage": 1}), (m3["id"], ["b", "c"], {"org": "가나대"})]
    assert Z.marks_put(again, {**m1, "ids": []}) == [again[1]]                    # 블록이 안 남은 지정은 지운다
    pruned, n = Z.marks_prune(again, {"a", "b"})
    assert n == 2 and [(m["id"], m["ids"]) for m in pruned] == [(m1["id"], ["a"]), (m3["id"], ["b"])] and again[0]["ids"] == ["a", "d"]
    assert Z.marks_prune(again, set()) == ([], 4) and Z.marks_prune(again, {"a", "b", "c", "d"}) == (again, 0) and Z.marks_prune([], {"a"}) == ([], 0)
    ev = Z.origin_event("w1", "기관A.hwpx", ["가나대"], "filled", ["p1", "p2", "p1"], key="k1", at="2026-11-17T09:00:00")
    assert len(ev["id"]) == 8 and ev == {"id": ev["id"], "part": "w1", "name": "기관A.hwpx", "orgs": ["가나대"], "kind": "filled", "ids": ["p1", "p2"], "key": "k1", "at": "2026-11-17T09:00:00"}
    assert Z.origin_event("w1", "x", [], "drop", [])["key"] is None


def test_inherit_puts_new_blocks_right_after_the_block_they_came_from():
    marks = [_mark(["a", "b", "c"], {"org": "인텍"}, "m1"), _mark(["x"], {"year": 1}, "m2")]
    assert Z.inherit(marks, {"n1": "b"}) == 1 and marks[0]["ids"] == ["a", "b", "n1", "c"]
    assert Z.inherit(marks, {"n2": "b", "n3": "b", "n4": "x"}) == 3 and marks[0]["ids"] == ["a", "b", "n2", "n3", "n1", "c"] and marks[1]["ids"] == ["x", "n4"]
    assert Z.inherit(marks, {"q1": "zz", "q2": None, "a": "c", "b": "b"}) == 0 and marks[0]["ids"] == ["a", "b", "n2", "n3", "n1", "c"]   # 지정에 없는 블록에서 나옴 · 이미 지정에 든 블록
    assert Z.inherit(marks, {"r2": "r1", "r1": "c"}) == 2 and marks[0]["ids"][-3:] == ["c", "r1", "r2"]   # 새 블록에서 또 나온 블록
    assert Z.inherit([], {"n": "a"}) == 0 and Z.inherit(marks, {}) == 0 and Z.inherit(marks, None) == 0


# ---- 보기(build) --------------------------------------------------------------------------------------------------

def test_build_without_marks_keeps_the_auto_labels():
    auto = {"a": _lab("인텍"), "b": _lab("인텍", 1, 1), "c": _lab(stage=1, year=1), "t": _lab("가나대"), "c2": _lab("가나대", 2, 3), "e": _lab(kind="unknown")}
    info = _info(auto)
    view = Z.build(info, [], [], ["org", "stage", "year"])
    assert set(view) == {"blocks", "cells", "zones", "marks", "origins", "counts", "_tableOf", "_info"} and view["_info"] is info and view["_tableOf"] == {"c1": "t", "c2": "t", "c3": "t"}
    assert view["blocks"] == {k: auto[k] for k in ("a", "b", "c", "t", "e")}                    # 값이 있는 최상위 블록만(d·f 는 순수 공통)
    assert view["cells"] == {"t": {"c2": auto["c2"]}} and view["marks"] == [] and view["origins"] == []
    assert view["counts"] == {"zones": 5, "blocks": 5, "cells": 1, "marks": 0, "origins": 0, "conflicts": 0, "unknown": 1}
    assert [(z["ids"], z["text"], z["mark"]) for z in view["zones"]] == [(["a"], "㈜인텍", None), (["b"], "㈜인텍 · 1단계 1차년도", None), (["c"], "1단계 1차년도", None), (["t"], "가나대", None), (["e"], "기관 모름", None)]
    assert view["zones"][0] == {"ids": ["a"], "label": {"org": "인텍", "orgKind": "org", "stage": None, "year": None, "src": {"org": "auto"}, "ev": {"org": "group"}}, "text": "㈜인텍",
                                "path": ["1. 개요", "[주관]"], "first": "글 a", "mark": None}
    assert Z.build(info, None, None, None)["zones"] == [] and Z.build(info, [], [], ["없는 기준"])["zones"] == []
    assert Z.build({}, [], [], ["org"])["counts"] == {"zones": 0, "blocks": 0, "cells": 0, "marks": 0, "origins": 0, "conflicts": 0, "unknown": 0}


def test_bands_follow_the_dims_and_never_join_unknown_with_common():
    auto = {"a": _lab("인텍", 1, 1), "b": _lab("인텍", 1, 2), "c": _lab(stage=1, year=2), "t": _lab(kind="unknown"), "d": _lab(kind="conflict"), "f": _lab("인텍")}
    info = _info(auto)
    bands = lambda dims: [(z["ids"], z["text"]) for z in Z.build(info, [], [], dims)["zones"]]  # noqa: E731
    assert bands(["org"]) == [(["a", "b"], "㈜인텍"), (["t"], "기관 모름"), (["d"], "기관 확인 필요"), (["f"], "㈜인텍")]   # 기관만 — 차년도가 달라도 한 띠 · 공통(c·e)이 띠를 끊는다
    assert bands(["org", "year"]) == [(["a"], "㈜인텍 · 1단계 1차년도"), (["b"], "㈜인텍 · 1단계 2차년도"), (["c"], "1단계 2차년도"), (["t"], "기관 모름"), (["d"], "기관 확인 필요"), (["f"], "㈜인텍")]
    assert bands(["year"]) == [(["a"], "1단계 1차년도"), (["b", "c"], "1단계 2차년도")]                                 # 차년도만 — 기관이 달라도 한 띠
    assert bands(["stage"]) == [(["a", "b", "c"], "1단계")] and bands([]) == []
    z = Z.build(info, [], [], ["year"])["zones"][1]
    assert z["label"] == {"org": None, "orgKind": None, "stage": None, "year": 2, "src": {"year": "auto"}, "ev": {"year": "group"}} and z["first"] == "글 b"   # 띠의 라벨은 켠 기준의 값만
    blank = _info({"a": _lab("인텍"), "b": _lab("인텍")}, text={"a": "", "b": "둘째 글"})
    assert Z.build(blank, [], [], ["org"])["zones"][0]["first"] == "둘째 글"                                            # 첫 글 = 띠에서 처음 글이 있는 블록의 것
    assert Z.build(info, [], [], ["org"])["counts"] == {"zones": 4, "blocks": 6, "cells": 0, "marks": 0, "origins": 0, "conflicts": 1, "unknown": 1}


def test_marks_override_per_dimension_and_none_means_nothing():
    auto = {"a": _lab("인텍", 1, 1), "b": _lab("인텍", 1, 1), "c": _lab("인텍", 1, 1), "d": _lab("인텍"), "e": _lab("인텍")}
    info = _info(auto)
    marks = [_mark(["a"], {"org": "가나대"}, "m1"), _mark(["b"], {"org": None}, "m2"), _mark(["c", "zz"], {"year": 3}, "m3"), _mark(["d"], {"org": None}, "m4"), _mark(["f"], {"stage": 2}, "m5")]
    view = Z.build(info, marks, [], ["org", "stage", "year"])
    B = view["blocks"]
    assert B["a"] == {"org": "가나대", "orgKind": "org", "stage": 1, "year": 1, "src": {"org": "mark", "stage": "auto", "year": "auto"}, "ev": {"stage": "group", "year": "group"}}   # 키 없는 기준은 자동 그대로
    assert B["b"] == {"org": None, "orgKind": None, "stage": 1, "year": 1, "src": {"org": "mark", "stage": "auto", "year": "auto"}, "ev": {"stage": "group", "year": "group"}}     # None = 그 기준 없음
    assert B["c"] == {"org": "인텍", "orgKind": "org", "stage": 2, "year": 3, "src": {"org": "auto", "stage": "mark", "year": "mark"}, "ev": {"org": "group"}}                      # 차년도만 지정 — 단계는 그 차년도에서
    assert "d" not in B and B["e"] is auto["e"]                                                                         # 기관 없음뿐인 블록은 값이 없다 · 지정 없는 블록은 자동 그대로
    assert B["f"] == {"org": None, "orgKind": None, "stage": 2, "year": None, "src": {"stage": "mark"}, "ev": {}}       # 자동 값이 없던 블록
    assert [(m["id"], m["ids"], m["gone"], m["invalid"]) for m in view["marks"]] == [("m1", ["a"], 0, []), ("m2", ["b"], 0, []), ("m3", ["c"], 1, []), ("m4", ["d"], 0, []), ("m5", ["f"], 0, [])]
    assert view["marks"][0] == {"id": "m1", "ids": ["a"], "gone": 0, "label": {"org": "가나대"}, "note": "", "by": "user", "at": "2026-11-17T10:00:00", "invalid": []}
    assert view["counts"]["marks"] == 5 and marks[2]["ids"] == ["c", "zz"]                                              # 없어진 블록은 그대로 두고 센다(받은 지정은 안 고친다)
    assert [(z["ids"], z["text"], z["mark"]) for z in view["zones"]] == [(["a"], "가나대 · 1단계 1차년도", "m1"), (["b"], "1단계 1차년도", "m2"), (["c"], "㈜인텍 · 2단계 1차년도", "m3"),
                                                                         (["e"], "㈜인텍", None), (["f"], "2단계", "m5")]
    by_org = Z.build(info, marks, [], ["org"])["zones"]   # 기관만 켬 — 차년도만 지정한 c 는 자동 블록과 같은 띠다(켠 기준의 값이 지정에서 온 것이 아니다)
    assert [(z["ids"], z["mark"]) for z in by_org] == [(["a"], "m1"), (["c"], None), (["e"], None)]
    same = Z.build(_info({"a": _lab("인텍"), "b": _lab("인텍"), "c": _lab("인텍")}), [_mark(["b"], {"org": "인텍"})], [], ["org"])["zones"]
    assert [(z["ids"], z["mark"]) for z in same] == [(["a"], None), (["b"], "m1"), (["c"], None)]                       # 값이 같아도 지정에서 온 블록과 자동 블록은 한 띠가 아니다
    assert Z.label_text(B["c"], view) == "㈜인텍 · 2단계 1차년도" and Z.label_text(B["b"], view, ["org"]) == ""


def test_marks_on_stage_and_year_keep_the_label_consistent():
    stages = [2, 2]
    derived, flag = Z._auto_label({"year": (1, (3, "abs"))}, None, None, None, stages)       # 단계를 차년도에서 채운 블록
    itemed, flag2 = Z._auto_label({"stage": (1, 2), "year": (1, (3, "free"))}, None, None, None, stages)   # 단계 항목이 단계를 말한 블록
    assert (derived["stage"], derived["year"], flag) == (2, 3, True) and (itemed["stage"], itemed["year"], flag2) == (2, 3, False)
    info = _info({"a": derived, "b": itemed, "c": _lab(stage=1, year=2), "d": _lab("인텍", 1, 2)}, _derived={"a": True})
    view = Z.build(info, [_mark(["a", "b"], {"year": None}, "m1"), _mark(["c", "d"], {"stage": 2}, "m2")], [], ["stage", "year"])
    B = view["blocks"]
    assert "a" not in B                                                                       # 차년도 없음 — 그 차년도에서 채웠던 단계도 없다
    assert B["b"] == {"org": None, "orgKind": None, "stage": 2, "year": None, "src": {"stage": "auto", "year": "mark"}, "ev": {"stage": "group"}}   # 단계 항목이 말한 단계는 남는다
    assert (B["c"]["stage"], B["c"]["year"], B["c"]["src"]) == (2, None, {"stage": "mark"})   # 자동 차년도(1단계의 것)가 지정한 단계와 안 맞는다 — 지정이 이긴다
    assert (B["d"]["org"], B["d"]["stage"], B["d"]["year"], B["d"]["src"]) == ("인텍", 2, None, {"org": "auto", "stage": "mark"})


def test_invalid_marks_fall_back_to_auto_and_are_listed():
    auto = {"a": _lab("인텍", 1, 1), "b": _lab("인텍", 1, 1), "c": _lab("인텍", 1, 1), "d": _lab("인텍", 1, 1)}
    info = _info(auto)
    marks = [_mark(["a"], {"org": "없어진기관", "year": 2}, "m1"), _mark(["b"], {"stage": 3, "year": 9}, "m2"), _mark(["c"], {"stage": 1, "year": 3}, "m3"), _mark(["d"], {"org": 7, "stage": "x"}, "m4")]
    view = Z.build(info, marks, [], ["org", "stage", "year"])
    assert [m["invalid"] for m in view["marks"]] == [["org"], ["stage", "year"], ["stage", "year"], ["org", "stage"]]
    assert view["marks"][0]["label"] == {"org": "없어진기관", "year": 2}                       # 지정한 값은 그대로 보인다 — 다른 값으로 옮기지 않는다
    B = view["blocks"]
    assert (B["a"]["org"], B["a"]["year"], B["a"]["src"]) == ("인텍", 2, {"org": "auto", "stage": "mark", "year": "mark"})   # 기관은 자동 값으로 · 유효한 기준은 쓴다
    assert B["b"] is auto["b"] and B["c"] is auto["c"] and B["d"] is auto["d"]
    assert [(z["ids"], z["mark"]) for z in view["zones"]] == [(["a"], "m1"), (["b", "c"], None), (["d"], None)]   # 쓰이지 않은 지정은 띠를 가르지 않는다(b·c 는 지정이 달라도 한 띠 — 표 t 가 d 를 끊는다)
    none = _info({}, stages=(), orgs=())   # 프로젝트 구성 값이 없는 문서 — 판단할 수 없어 invalid 로 치지 않고 지정 값을 그대로 쓴다
    view = Z.build(none, [_mark(["a"], {"org": "없어진기관", "year": 2}, "m1"), _mark(["b"], {"org": 7}, "m2")], [], ["org", "year"])
    assert [m["invalid"] for m in view["marks"]] == [[], ["org"]]
    assert view["blocks"] == {"a": {"org": "없어진기관", "orgKind": "org", "stage": None, "year": 2, "src": {"org": "mark", "year": "mark"}, "ev": {}}}
    assert view["zones"][0]["text"] == "없어진기관 · 2차년도" and view["zones"][0]["mark"] == "m1"   # 기관 이름은 열쇠 글 그대로


def test_origins_fill_only_common_places_with_one_single_org_event():
    auto = {"a": _lab("인텍"), "c": _lab(stage=1, year=1)}
    info = _info(auto, _caps=["cap1"])
    ev = lambda eid, orgs, ids, **kw: {"id": eid, "part": "w1", "name": "기관A.hwpx", "orgs": orgs, "kind": "filled", "ids": ids, "key": "k", "at": "2026-11-17T10:00:00", **kw}  # noqa: E731
    origins = [ev("e1", ["가나대"], ["a", "b", "c", "c1", "cap1", "zz"]), ev("e2", ["가나대", "다라연"], ["d"]), ev("e3", ["다라연"], ["e"]), ev("e4", ["인텍"], ["e"]), ev("e5", ["가나대"], ["gone1", "gone2"])]
    view = Z.build(info, [], origins, ["org", "year"])
    B = view["blocks"]
    assert B["a"] is auto["a"]                                                                # 기관이 있는 자리에 다른 기관의 내용 — 자리는 그대로(출처만 보인다)
    assert B["b"] == {"org": "가나대", "orgKind": "org", "stage": None, "year": None, "src": {"org": "origin"}, "ev": {}}   # 공통 자리 + 이벤트 하나 + 기관 하나
    assert B["c"] == {"org": "가나대", "orgKind": "org", "stage": 1, "year": 1, "src": {"org": "origin", "stage": "auto", "year": "auto"}, "ev": {"stage": "group", "year": "group"}}
    assert "d" not in B and "e" not in B and "t" not in B                                     # 기관이 둘인 문서 · 이벤트가 둘 · 칸에 넣은 것은 표를 채우지 않는다
    assert [(o["id"], o["ids"], o["gone"]) for o in view["origins"]] == [("e1", ["a", "b", "c", "c1", "cap1"], 1), ("e2", ["d"], 0), ("e3", ["e"], 0), ("e4", ["e"], 0), ("e5", [], 2)]
    assert view["origins"][0] == {"id": "e1", "part": "w1", "name": "기관A.hwpx", "orgs": ["가나대"], "kind": "filled", "at": "2026-11-17T10:00:00", "ids": ["a", "b", "c", "c1", "cap1"], "gone": 1}
    assert view["counts"]["origins"] == 4 and view["counts"]["blocks"] == 3                   # 남은 id 가 있는 이벤트 수
    assert [(z["ids"], z["text"]) for z in view["zones"]] == [(["a"], "㈜인텍"), (["b"], "가나대"), (["c"], "가나대 · 1단계 1차년도")]
    marked = Z.build(info, [_mark(["b"], {"org": None}, "m1"), _mark(["c"], {"org": "없어진기관"}, "m2")], origins, ["org"])
    assert "b" not in marked["blocks"] and marked["blocks"]["c"]["src"]["org"] == "origin"    # 「기관 없음」 으로 지정한 블록은 채우지 않는다 · 유효하지 않은 지정은 없는 것과 같다
    stale = Z.build(info, [], [ev("e9", ["없어진기관"], ["b"])], ["org"])
    assert "b" not in stale["blocks"] and stale["origins"][0]["orgs"] == ["없어진기관"]       # 지금 프로젝트 구성에 없는 기관으로는 채우지 않는다(출처는 그대로 보인다)


def test_legacy_origins_are_listed_but_never_fill_the_org():
    """옛 기록(legacy — 출처 이벤트가 생기기 전의 `applied`)은 「넣은 내용」 목록에만 실린다 — 그 id 가 실행 취소 뒤 다른 문단에 다시 쓰였을 수 있어 기관을 채우는 근거로 쓰지 않는다."""
    info = _info({})
    ev = lambda eid, orgs, ids, **kw: {"id": eid, "part": "w1", "name": "x", "orgs": orgs, "kind": "added", "ids": ids, "at": None, **kw}  # noqa: E731
    origins = [ev("old1", ["가나대"], ["a", "b", "c"], legacy=True), ev("new1", ["다라연"], ["b"]), ev("new2", ["인텍", "다라연"], ["c"]), ev("old2", ["인텍"], ["d"], legacy=True)]
    view = Z.build(info, [], origins, ["org"])
    assert "a" not in view["blocks"] and "d" not in view["blocks"]                                       # 옛 기록만 덮은 블록 — 기관 하나짜리 기록 하나여도 채우지 않는다
    assert view["blocks"]["b"]["org"] == "다라연" and view["blocks"]["b"]["src"] == {"org": "origin"}     # 새 이벤트만 본다(옛 기록이 같이 덮어도)
    assert "c" not in view["blocks"]                                                                     # 새 이벤트의 기관이 둘
    assert [(o["id"], "legacy" in o, o.get("legacy"), o["ids"]) for o in view["origins"]] == [("old1", True, True, ["a", "b", "c"]), ("new1", False, None, ["b"]), ("new2", False, None, ["c"]), ("old2", True, True, ["d"])]
    assert view["counts"]["origins"] == 4 and [z["ids"] for z in view["zones"]] == [["b"]]               # 목록에는 그대로 실린다


def test_cells_inherit_from_the_table_and_only_differing_cells_are_listed():
    auto = {"t": _lab("인텍", 1, 1), "c1": _lab("인텍", 1, 1), "c2": _lab(stage=1, year=2), "c3": _lab("가나대", ev="cell")}
    info = _info(auto)
    view = Z.build(info, [], [], ["org"])
    assert set(view["cells"]) == {"t"} and set(view["cells"]["t"]) == {"c2", "c3"}                      # 표의 라벨과 같은 칸(c1)은 싣지 않는다
    assert view["cells"]["t"]["c2"] == {"org": "인텍", "orgKind": "org", "stage": 1, "year": 2, "src": {"org": "auto", "stage": "auto", "year": "auto"}, "ev": {"org": "group", "stage": "group", "year": "group"}}
    assert view["cells"]["t"]["c3"] == {"org": "가나대", "orgKind": "org", "stage": 1, "year": 1, "src": {"org": "auto", "stage": "auto", "year": "auto"}, "ev": {"org": "cell", "stage": "group", "year": "group"}}
    assert auto["c2"]["org"] is None and auto["c3"]["year"] is None                                     # 자동 라벨은 안 고친다
    assert Z.label_of(view, "t") is view["blocks"]["t"] and Z.label_of(view, "c1") is view["blocks"]["t"] and Z.label_of(view, "c2")["year"] == 2 and Z.label_of(view, "없는 id") is None
    public = {k: v for k, v in view.items() if not k.startswith("_")}                                   # 끝점의 응답(밑줄 키 뺌)에서도 실린 칸은 찾는다
    assert Z.label_of(public, "c3")["org"] == "가나대" and Z.label_of(public, "t")["org"] == "인텍" and Z.label_of(public, "c1") is None and Z.label_of(None, "t") is None
    marked = Z.build(info, [_mark(["t"], {"org": "다라연", "year": None})], [], ["org"])                   # 표를 지정 — 칸은 표의 **최종** 라벨에서 물려받는다
    assert marked["blocks"]["t"]["org"] == "다라연" and marked["blocks"]["t"]["year"] is None
    C = marked["cells"]["t"]
    assert set(C) == {"c1", "c2", "c3"} and C["c1"]["org"] == "인텍"                                    # 칸의 자동 값이 있는 기준은 칸의 것(안쪽이 이긴다)
    assert (C["c2"]["org"], C["c2"]["src"]["org"], C["c2"]["year"]) == ("다라연", "mark", 2) and (C["c3"]["org"], C["c3"]["stage"], C["c3"]["year"]) == ("가나대", 1, None)
    bare = Z.build(_info({"c2": _lab(stage=1, year=2), "c1": _lab(stage=2)}, stages=(2, 2)), [_mark(["t"], {"org": "인텍", "year": 1})], [], ["org"])
    assert bare["cells"]["t"]["c2"]["org"] == "인텍" and bare["cells"]["t"]["c2"]["year"] == 2
    assert (bare["cells"]["t"]["c1"]["stage"], bare["cells"]["t"]["c1"]["year"]) == (2, None)           # 칸이 제 단계(2)를 말하면 다른 단계의 차년도(1)는 물려받지 않는다
    lone = Z.build(_info({"c2": _lab("가나대")}), [], [], ["org"])
    assert lone["blocks"] == {} and lone["cells"] == {"t": {"c2": _lab("가나대")}} and lone["counts"]["cells"] == 1 and lone["zones"] == []   # 표에 라벨이 없어도 칸의 라벨은 싣는다
    why = {"byGroup": "인텍", "byCell": ["가나대"]}
    conflict = Z.build(_info({"t": {**_lab(kind="conflict"), "why": why}, "c2": _lab(stage=1, year=2)}), [], [], ["org"])
    assert conflict["cells"]["t"]["c2"]["orgKind"] == "conflict" and conflict["cells"]["t"]["c2"]["why"] == why and conflict["counts"]["conflicts"] == 1


def test_marking_a_table_settles_the_cells_the_script_could_not_decide():
    """표를 지정(사람 · LLM)하면 스크립트가 기관을 못 정한 칸(확인 필요 · 모름)도 그 기관이다 — 표의 「확인 필요」 는 풀렸는데 칸에는 남는 일이 없게. 칸이 제 기관을 깨끗이 읽었으면 그 칸은 그대로(안쪽이 이긴다)."""
    why = {"byGroup": "인텍", "byCell": ["가나대"]}
    auto = {"t": {**_lab(kind="conflict"), "why": why}, "c1": {**_lab(kind="conflict"), "why": why}, "c2": _lab(kind="unknown"), "c3": _lab("다라연", ev="cell")}
    info = _info(auto)
    before = Z.build(info, [], [], ["org"])
    assert Z.label_of(before, "c1")["orgKind"] == "conflict" and before["cells"]["t"]["c2"]["orgKind"] == "unknown" and before["counts"]["conflicts"] == 1
    for by in ("user", "llm"):
        view = Z.build(info, [{**_mark(["t"], {"org": "가나대"}), "by": by}], [], ["org"])
        assert view["blocks"]["t"]["org"] == "가나대" and view["blocks"]["t"]["src"]["org"] == "mark" and view["counts"]["conflicts"] == 0
        c1, c2, c3 = (Z.label_of(view, c) for c in ("c1", "c2", "c3"))
        assert (c1["org"], c1["orgKind"], c1["src"]["org"]) == ("가나대", "org", "mark") and "why" not in c1 and "org" not in c1["ev"]   # 엇갈린 근거는 더 싣지 않는다
        assert (c2["org"], c2["orgKind"], c2["src"]["org"]) == ("가나대", "org", "mark")
        assert (c3["org"], c3["src"]["org"], c3["ev"]["org"]) == ("다라연", "auto", "cell")                                               # 제 기관을 읽은 칸은 그대로
        assert set(view["cells"]["t"]) == {"c3"}                                                                                          # 표와 같아진 칸은 싣지 않는다
    assert auto["c1"]["orgKind"] == "conflict" and auto["c1"]["why"] == why                                                                # 자동 라벨은 안 고친다
    none = Z.build(info, [_mark(["t"], {"org": None})], [], ["org"])   # 「기관 없음」 으로 지정한 표 — 칸의 확인 필요를 지정이 대신 정해 주지 않는다(정한 기관이 없다)
    assert Z.label_of(none, "c1")["orgKind"] == "conflict"


def test_label_text():
    info = _info()
    text = lambda lab, dims=None, x=info: Z.label_text(lab, x, dims)  # noqa: E731
    assert text(_lab("인텍", 1, 2)) == "㈜인텍 · 1단계 2차년도" and text(_lab("가나대", 2, 3)) == "가나대 · 2단계 1차년도"   # 차년도 = 단계 안 차년도
    assert text(_lab("인텍", 1, 2), ["org"]) == "㈜인텍" and text(_lab("인텍", 1, 2), ["year"]) == "1단계 2차년도" and text(_lab("인텍", 1, 2), ["stage"]) == "1단계" and text(_lab("인텍", 1, 2), []) == ""
    assert text(_lab(stage=2)) == "2단계" and text(_lab(stage=2), ["year"]) == "" and text(_lab(kind="unknown", stage=1, year=1)) == "기관 모름 · 1단계 1차년도" and text(_lab(kind="conflict")) == "기관 확인 필요"
    assert text({"org": None, "orgKind": None, "stage": None, "year": None, "src": {}}) == "" and text(None) == "" and text({}) == ""
    one = _info(stages=(3,))
    assert text(_lab("다라연", 1, 2), None, one) == "다라연 · 2차년도" and text(_lab(stage=1), None, one) == "1단계"   # 단계가 하나면 「2차년도」
    assert text(_lab("없는열쇠", 1, 1)) == "없는열쇠 · 1단계 1차년도" and text(_lab(year=9, stage=None)) == "9차년도"   # 이름이 없으면 열쇠 글 · 범위 밖은 적힌 번호 그대로
    view = Z.build(info, [], [], [])
    assert Z.label_text(_lab("인텍", 2, 4), view) == "㈜인텍 · 2단계 2차년도"                                          # 보기를 줘도 된다
    assert Z.label_text(_lab("인텍", 2, 4), {"orgs": ORGS, "stages": [2, 2], "blocks": {}}) == "㈜인텍 · 2단계 2차년도"   # 끝점의 응답(밑줄 키 없음)도


def test_build_is_cheap_on_a_large_document():
    import time
    b = _base()
    info = copy.deepcopy(b["info"])
    marks = [Z.mark_make(info["order"][i:i + 5], {"org": J1}) for i in range(0, 200, 10)]
    origins = [Z.origin_event("w", "x", [J2], "filled", info["order"][i:i + 3]) for i in range(300, 500, 7)]
    t = time.perf_counter()
    view = Z.build(info, marks, origins, ["org", "stage", "year"])
    took = time.perf_counter() - t
    assert took < 0.5 and view["counts"]["marks"] == 20 and view["counts"]["zones"] > 20   # 옵션·지정이 바뀔 때마다 불린다 — 수 ms(여유를 크게 둔 상한)
    assert info["auto"] == b["info"]["auto"] and len(marks[0]["ids"]) == 5                  # 받은 것은 안 고친다


# ---- 2026-11-18 astra 반례(구분 기준 판독을 헤딩 앞에 — spec_구분_기준 ① 같은 날): 틀린 자리에 기관·차년도가 붙던 것 ------------------------------------

def test_table_read_keeps_a_year_clash_instead_of_the_whole_table_year():
    """한 행의 차년도 열들이 1 · 2 로 엇갈리는데 「구입연차 | 1」 이 표 전체의 차년도 1 로 서서 그 행에 물려 주던 것 — 엇갈림을 남기고 표 전체 차년도를 세우지 않는다."""
    t = _tbl([["차년도", "차년도", "구입연차", "1"], ["1", "2", "", ""]])
    whole, per = Z._table_read(t, KEYS, [4])
    assert not (whole or {}).get("year")                                                    # 전에는 {'year': 1}
    assert {c: e.get("yearClash") for c, e in per.items()} == {f"t1_{k}": [1, 2] for k in range(4)}
    blocks = _doc("머리 글", [["차년도", "차년도", "구입연차", "1"], ["1", "2", "", ""]])
    info = Z.read(_snap(blocks, core.norm_values({"stages": [4], "orgs": {"lead": "인텍", "joint": ["가나대"]}})))
    view = Z.build(info, [], [], ["org", "stage", "year"])
    for c in ("c2_1_0", "c2_1_1", "c2_1_2", "c2_1_3"):
        lab = Z.label_of(view, c) or {}
        assert lab.get("year") is None and (lab.get("why") or {}).get("year", {}).get("byCell") == [1, 2], (c, lab)   # 표의 값을 물려받지 않고 엇갈림이 보인다
    no_clash = _tbl([["차년도", "구입연차", "1"], ["1", "", ""]])
    assert Z._table_read(no_clash, KEYS, [4])[0] == {"year": 1}                              # 엇갈림이 없으면 그대로


def test_org_column_under_a_head_naming_another_party_is_not_the_rows_org():
    """첫 열 머리가 「발행기관」(인증서를 발행한 곳) · 「거래처」 열의 「자문(가나대)」 — 행을 쓴 기관이 아니다."""
    issued = _tbl([["발행기관", "인증명"], ["가나대", "ISO 9001"], ["다라연", "KS"]])
    assert Z._table_read(issued, KEYS, [2]) == (None, {})
    trade = _tbl([["활동", "거래처"], ["구매", "자문(가나대)"], ["구매", "서비스(다라연)"]])
    assert Z._table_read(trade, KEYS, [2]) == (None, {})
    own = _tbl([["기관", "인증명"], ["가나대", "ISO 9001"], ["다라연", "KS"]])                 # 머리가 상대 낱말이 아니면 전처럼 기관 열
    assert {e["org"][1] for e in Z._table_read(own, KEYS, [2])[1].values() if "org" in e} == {"가나대", "다라연"}


def test_old_org_names_from_prior_values_are_not_mapped_to_the_current_org_by_number():
    """옛 구성(주관 가나 · 공동 다라)으로 반영한 문서를 새 구성(주관 마바 · 공동 사아)으로 읽을 때 — 옛 이름이 적힌 자리를 번호로 새 기관에 붙이지 않는다(「기관 모름」)."""
    values = core.norm_values({"stages": [2], "orgs": {"lead": "마바", "joint": ["사아"]}})
    keys = ["마바", "사아"]
    old = Z.old_keys([core.norm_values({"stages": [2], "orgs": {"lead": "가나", "joint": ["다라"]}})], keys)
    assert old == ["가나", "다라"] or sorted(old) == ["가나", "다라"]
    lead = {"value": ("lead", 0), "labelText": "[주관연구개발기관(가나)]"}
    joint = {"value": ("joint", 1), "labelText": "[공동연구개발기관1(다라)]"}
    assert Z._org_item({}, lead, values, keys)[:2] == ("org", "마바")                       # prior 를 안 주면 전처럼 번호(옛 길)
    assert Z._org_item({}, lead, values, keys, old)[:2] == ("unknown", None)
    assert Z._org_item({}, joint, values, keys, old)[:2] == ("unknown", None)
    now = {"value": ("lead", 0), "labelText": "[주관연구개발기관(마바)]"}                     # 다시 반영해 새 이름이 적힌 자리는 그 기관
    assert Z._org_item({}, now, values, keys, old)[:2] == ("org", "마바")
    plain = {"value": ("lead", 0), "labelText": "[주관연구개발기관]"}                          # 이름이 없는 자리는 번호대로
    assert Z._org_item({}, plain, values, keys, old)[:2] == ("org", "마바")
    assert Z.old_keys(None, keys) == [] and Z.old_keys([values], keys) == []
