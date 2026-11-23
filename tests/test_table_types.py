"""양식의 표 판정(spec_테이블매니저 ② §10 「양식의 표 판정」) — 확정본의 꼴 · 구조 견주기 · 저장(app/table_types.py) + 끝점(app/table_types_api.py) + 표 서식 점검에 잇기(tables_api._style_tb).

astra 3차 검토(artifacts/table_manager_astra_2026-11-19/answer3.md)의 반례를 그대로 옮겼다 — 타입 · 열 수 · 음영 자리 · 칸 수가 같아도 **안 맞아야** 하는 표(병합만 다름 · 중간에 안내 행 · 행이 늘어남 ·
같은 머리글 아래 고정 이름 ↔ 사람 이름), 띠만으로는 못 되살리는 역할(음영 값 칸), 저절로 배우지 않는 것, 양식의 확정이 그 작업의 헤더 지정이 되지 않는 것."""
import json
import os
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_forms as F
from app import heading_guides as G
from app import heading_rules as R
from app import server, table_heads, table_kv, table_types_api, tables_api
from app import table_manager as TM
from app import table_types as TT
from app.hwpx_doc import P

S = "#D6D6D6"
TID = "t100"
PLAN = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
FORM = "시험계획서"
FORM_MD = '# 양식 정보 — 시험\n\n```json\n{"name": "시험 계획서", "match": {"names": ["*연구개발계획서*"]}}\n```\n'
CAREER = "t6685"   # 3×4 「기간 | 기관명 | 직위 | 비고」 경력 표 — 빈 값 칸 6개(B2 · C2 · D2 · B3 · C3 · D3): 짧은 글로 채우면 초안이 B · C 열을 헤더 열로 읽는다
CAREER_TWIN = "t7018"   # 같은 문서의 구조가 꼭 같은 표(다른 사람의 경력)
HELD_MSG = "헤더 지정 1칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))   # 확정본(table_types.json)도 이 폴더에 — 사용자 저장소를 안 건드린다
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    for m in (R._MEMORY, G._MEMORY, F._CHOICE, TT._MEMORY, TT._CACHE):
        m.clear()
    yield
    for m in (R._MEMORY, G._MEMORY, F._CHOICE, TT._MEMORY, TT._CACHE):
        m.clear()


def _stage1(cells, tid=TID):
    """합성 1단계 레코드(표 하나) — cells = [(행, 열, 행 병합, 열 병합, 음영, [문단 글…])…]. 칸 id 는 c101 부터 차례로. 문단 종류는 실제 분류기로."""
    rules, run = R.active(R.load(), ()), R._Run()
    rows, cols = max(r + rs for r, _c, rs, _cs, _f, _p in cells), max(c + cs for _r, c, _rs, cs, _f, _p in cells)
    tbl = {"t": "tbl", "id": tid, "rows": rows, "cols": cols, "cells": len(cells), "key": 1, "host": "x1"}
    recs, n = [], 0
    for i, (r, c, rs, cs, fill, paras) in enumerate(cells):
        cell = {"t": "cell", "id": f"c{101 + i}", "row": r, "col": c, "rs": rs, "cs": cs, "fill": fill, "key": 10 + i}
        for t in paras:
            n += 1
            h = R.classify(t, rules, run)
            recs.append({"id": f"p{200 + n}", "n": n, "path": [tbl, cell], "text": t, "kind": h["kind"], "blank": h["blank"], "char": {"text": {"bold": False}}})
    return {"paras": recs}


def _judge(cells, **kw):
    return TM.judge(_stage1(cells), TID, **kw)


def _roles(j):
    return {TT.ref(x["row"], x["col"]): x["role"] for x in j["table"]["cells"]}


def _row(r, *texts, shade=None):
    """한 행의 칸들 — 병합 없이 왼쪽부터."""
    return [(r, c, 1, 1, shade, [t]) for c, t in enumerate(texts)]


def _confirm(cells, form=FORM, variable=None, **kw):
    """표를 판정해 그대로 확정 → (저장한 확정본, 그 판정)."""
    j = _judge(cells, **kw)
    return TT.put(TT.entry_of(j, form, variable, origin={"work": "w1", "table": TID, "rev": 0})), j


# ---- 확정본의 꼴 -------------------------------------------------------------------------------------------------------

BUDGET = (_row(0, "구분", "1차년도", "2차년도", "합계", shade=S) + _row(1, "인건비", "987654", "876543", "1864197") + _row(2, "재료비", "765432", "654321", "1419753")
          + [(3, 0, 1, 4, None, ["※ 현물은 기관이 부담하는 금액을 적는다."])])


def test_entry_keeps_places_roles_and_head_text_but_no_values(tmp_path):
    j = _judge(BUDGET, user={"c105": "rowhead"})                                   # 「인건비」 는 이 작업에서 사람이 지정한 칸이기도 하다 — 최종 역할이 그대로 확정본에 든다
    e = TT.entry_of(j, FORM, origin={"work": "w1", "table": TID, "rev": 7})
    assert e["form"] == FORM and e["type"] == table_kv.type_key(j["table"]) and (e["rows"], e["cols"]) == (4, 4)
    assert e["geometry"][:5] == [[0, 0, 1, 1, 1], [0, 1, 1, 1, 1], [0, 2, 1, 1, 1], [0, 3, 1, 1, 1], [1, 0, 1, 1, 0]] and e["geometry"][-1] == [3, 0, 1, 4, 0]
    assert len(e["roles"]) == len(e["geometry"]) == len(j["table"]["cells"]) == 13   # 모든 칸의 자리 · 역할
    assert {(r, c): role for r, c, role in e["roles"]} == {(x["row"], x["col"]): x["role"] for x in j["table"]["cells"]}
    assert e["bands"] == [{k: s[k] for k in TT.BAND_KEYS} for s in j["subs"]]
    assert e["labels"] == [[0, 0, "구분", 0], [0, 1, "", 1], [0, 2, "", 1], [0, 3, "합계", 0], [1, 0, "인건비", 0], [2, 0, "재료비", 0], [3, 0, "※현물은기관이부담하는금액을적는다.", 0]]
    assert e["name"] == "구분 · 합계" and e["from"] == {"work": "w1", "table": TID, "rev": 7, "source": "draft"}
    saved = TT.put(e)
    raw = (tmp_path / "heads" / TT.FILE).read_text(encoding="utf-8")
    for value in ("987654", "876543", "1864197", "765432", "654321", "1419753"):    # 값 칸의 글은 어디에도 없다
        assert value not in raw and value not in json.dumps(saved, ensure_ascii=False)
    assert "차년도" not in raw                                                      # 가변 머리글(구분 기준의 값 머리)의 글도 저장하지 않는다 — 견주지 않는 글이다
    assert "인건비" in raw and "구분" in raw and saved["id"] in raw


def test_default_variable_heads_are_the_division_value_heads_only():
    j = _judge(_row(0, "구분", "2024", "2025", "한국선급", shade=S) + _row(1, "매출", "", "", ""))
    assert {TT.ref(x["row"], x["col"]) for x in j["table"]["cells"] if x["id"] in TT.default_variable(j["table"])} == {"B1", "C1"}   # 연도 — 기관 이름은 사람이 고른다
    e = TT.entry_of(j, FORM, variable=["c104", "c106", "nope"])                    # 사람이 고른 것: 「한국선급」 만(값 칸 c106 · 없는 칸은 무시)
    assert [x[:2] for x in e["labels"] if x[3]] == [[0, 3]] and [0, 1, "2024", 0] in e["labels"]
    assert [x[3] for x in TT.entry_of(j, FORM, variable=[])["labels"]] == [0, 0, 0, 0, 0]   # 빈 목록 = 가변 없음


# ---- 맞는 확정본 — 구조가 꼭 같은 표만 ---------------------------------------------------------------------------------

def test_the_same_table_fits_whatever_is_typed_into_the_value_cells():
    e, blank = _confirm(BUDGET)
    filled = _row(0, "구분", "1차년도", "2차년도", "합계", shade=S) + _row(1, "인건비", "홍길동", "김철수", "이영희") + _row(2, "재료비", "현금", "현물", "기타") + [BUDGET[-1]]
    tb = _judge(filled)["table"]
    assert _roles(_judge(filled)) != _roles(blank)                                 # 내용으로 어림하면 흔들린다(짧은 글 = 헤더 열)
    assert TT.match(TT.list(FORM), tb)["id"] == e["id"] and TT.state_of(TT.list(FORM), tb, e["type"]) == "confirmed"
    j = _judge(filled, template=TT.template_of(TT.match(TT.list(FORM), tb)))
    assert j["source"] == "template" and j["template"] == {"id": e["id"], "rev": 1} and _roles(j) == _roles(blank)
    assert TT.list("다른양식") == [] and TT.match(TT.list("다른양식"), tb) is None   # 다른 양식의 문서에는 쓰지 않는다


def test_merge_only_difference_does_not_fit():
    """astra 3차 반례 ① — 둘 다 2×4 · 물리 칸 7 · 타입 · 음영 자리가 같고 병합만 다르다: 원본의 헤더 1열을 쓰면 대상의 「10000」 이 필드 → 행헤더가 된다."""
    head = _row(0, "Org", "Cash", "InKind", "Notes", shade=S)
    src = head + [(1, 0, 1, 2, None, ["Total"]), (1, 2, 1, 1, None, [""]), (1, 3, 1, 1, None, [""])]
    dst = head + [(1, 0, 1, 1, None, ["10000"]), (1, 1, 1, 2, None, ["Remark"]), (1, 3, 1, 1, None, [""])]
    e, js = _confirm(src)
    jd = _judge(dst)
    assert len(js["table"]["cells"]) == len(jd["table"]["cells"]) == 7 and table_kv.type_key(js["table"]) == table_kv.type_key(jd["table"])
    assert (js["table"]["rows"], js["table"]["cols"]) == (jd["table"]["rows"], jd["table"]["cols"]) == (2, 4)
    assert not TT.fits(e, jd["table"]) and TT.why_not(e, jd["table"]) == {"what": "geometry"}
    assert TT.match(TT.list(FORM), jd["table"]) is None and TT.state_of(TT.list(FORM), jd["table"], e["type"]) == "changed"
    assert _judge(dst, template=TT.template_of(e))["source"] == "draft"            # 억지로 줘도 매니저가 안 쓴다(그 표의 칸을 다 덮지 못한다) — 「10000」 은 필드 그대로
    assert _roles(_judge(dst, template=TT.template_of(e)))["A2"] == "field"


def test_a_note_row_put_in_the_middle_does_not_fit():
    """astra 3차 반례 ② — 중간에 음영 없는 전체 너비 「NOTE」 행이 끼었다: 타입 · 열 수 · 음영 자리가 같아도 행 수가 다르다(띠를 늘려 쓰면 NOTE 가 행헤더가 된다)."""
    base = _row(0, "Item", "Amount", shade=S) + _row(1, "Labor", "") + _row(2, "Total", "")
    noted = _row(0, "Item", "Amount", shade=S) + _row(1, "Labor", "") + [(2, 0, 1, 2, None, ["NOTE"])] + _row(3, "Total", "")
    e, _ = _confirm(base)
    tb = _judge(noted)["table"]
    assert table_kv.type_key(tb) == e["type"] and TT.why_not(e, tb) == {"what": "size"} and TT.match(TT.list(FORM), tb) is None
    assert TT.state_of(TT.list(FORM), tb, e["type"]) == "changed" and _roles(_judge(noted))["A3"] == "title"   # 그때는 지금처럼(초안)


def test_a_table_with_one_more_row_does_not_fit():
    """astra 3차 반례 ③ — 사람이 「A」 를 필드로 지정해 확정한 표에 같은 꼴의 행 「B | 20000」 이 늘었다: 「마지막 띠를 늘려」 쓰면 저장된 예외는 A 에만 붙고 새 B 는 행헤더가 된다 — 안 쓴다."""
    base = _row(0, "Item", "Amount", shade=S) + _row(1, "A", "") + _row(2, "Total", "")
    grown = _row(0, "Item", "Amount", shade=S) + _row(1, "A", "") + _row(2, "B", "20000") + _row(3, "Total", "")
    e, j = _confirm(base, user={"c103": "field"})
    assert _roles(j)["A2"] == "field" and [0, 0, "Item", 0] in e["labels"] and not any(x[:2] == [1, 0] for x in e["labels"])   # 필드가 된 「A」 는 머리글이 아니다(글을 저장하지 않는다)
    tb = _judge(grown)["table"]
    assert table_kv.type_key(tb) == e["type"] and not TT.fits(e, tb) and TT.match(TT.list(FORM), tb) is None
    used = _judge(grown, template=TT.template_of(e))
    assert used["source"] == "draft" and used["template"] is None                   # 띠를 늘려 맞추지 않는다


def test_fixed_name_and_person_name_under_the_same_heads_do_not_fit():
    """astra 3차 반례 ④ — 격자 · 병합 · 음영 · 음영 머리글이 모두 같다: 구판의 첫 열은 고정 이름 「Director」, 신판은 사람 이름 「Alice」. 구판의 역할을 쓰면 Alice 가 헤더가 되어 값에서 빠진다."""
    head = _row(0, "Class", "Content", "Remark", shade=S)
    old, new = head + _row(1, "Director", "", ""), head + _row(1, "Alice", "Engineer", "")
    e, j = _confirm(old)
    assert _roles(j)["A2"] == "rowhead" and [1, 0, "Director", 0] in e["labels"]    # 음영 없는 고정 머리 칸도 자리와 글을 견준다
    tb = _judge(new)["table"]
    assert table_kv.type_key(tb) == e["type"] and TT.geometry_of(tb) == e["geometry"]   # 타입 · 격자는 꼭 같다
    assert TT.why_not(e, tb) == {"what": "labels", "labels": [{"cell": "c104", "ref": "A2", "now": "Alice", "template": "Director"}]}
    assert TT.match(TT.list(FORM), tb) is None and TT.state_of(TT.list(FORM), tb, e["type"]) == "changed"
    assert TT.fits(e, _judge(head + _row(1, "Director", "기획", "2024-01"))["table"])   # 같은 고정 이름의 표는 값을 채워도 맞는다


def test_variable_heads_may_differ_but_fixed_heads_may_not():
    table = lambda y1, y2, org, first="구분": _row(0, first, y1, y2, org, shade=S) + _row(1, "매출", "", "", "")   # noqa: E731
    j = _judge(table("2024", "2025", "한국선급"))
    e = TT.put(TT.entry_of(j, FORM, variable=TT.default_variable(j["table"]) + ["c104"]))   # 연도(기본) + 기관 이름(사람이 고름)
    other = _judge(table("2027", "2028", "한국해양대학교"))["table"]
    assert table_kv.type_key(other) != e["type"]                                    # 타입은 기관 이름에서 달라진다 — 그래서 타입으로 거르지 않는다
    assert TT.match(TT.list(FORM), other)["id"] == e["id"] and TT.variable_cells(e, other) == ["c102", "c103", "c104"]
    assert not TT.fits(e, _judge(table("2024", "2025", "한국선급", first="항목"))["table"])   # 고정 머리글이 다르면 안 맞는다
    assert not TT.fits(e, _judge(_row(0, "구분", "2024", "2025", "한국선급") + _row(1, "매출", "", "", ""))["table"])   # 음영이 다르면 안 맞는다
    fixed = TT.put(TT.entry_of(j, "양식B", variable=[]))                           # 가변 없이 확정하면 연도가 달라도 안 맞는다
    assert not TT.fits(fixed, other) and TT.fits(fixed, _judge(table("2024", "2025", "한국선급"))["table"])


def test_long_fixed_text_is_compared_whole():
    note = "※ " + "가" * 300
    base = lambda tail: _row(0, "항목", "금액", shade=S) + _row(1, "인건비", "") + [(2, 0, 1, 2, None, [note + tail])]   # noqa: E731
    e, _ = _confirm(base(""))
    assert len(e["labels"][-1][2]) == TT.LABEL_MAX + 11                             # 저장은 짧게(앞 글 + 전체 글의 해시)
    assert TT.fits(e, _judge(base(""))["table"]) and not TT.fits(e, _judge(base(" 끝이 다름"))["table"])


def test_of_two_fitting_entries_the_narrower_one_is_used():
    """더 좁은 확정본이 먼저 — 맞는 것이 둘일 때 한쪽의 고정 머리글 칸이 다른 쪽을 다 품고 더 많으면 그것."""
    table = lambda y: _row(0, "구분", y, shade=S) + _row(1, "매출", "")   # noqa: E731
    j = _judge(table("2024"))
    loose = TT.put(TT.entry_of(j, FORM))                                           # 연도 가변
    tight = TT.put(TT.entry_of(j, FORM, variable=[]))                              # 연도 고정 「2024」 — 고정 머리글 칸이 하나 더 있다(더 좁다)
    assert loose["id"] != tight["id"] and len(TT.list(FORM)) == 2 and TT.fixed_cells(loose) < TT.fixed_cells(tight)
    same, later = _judge(table("2024"))["table"], _judge(table("2025"))["table"]
    assert len(TT.matches(TT.list(FORM), same)) == 2 and TT.match(TT.list(FORM), same)["id"] == tight["id"]   # 둘 다 맞으면 더 좁은 것
    assert TT.state_of(TT.list(FORM), same, loose["type"]) == "confirmed"
    assert TT.match(TT.list(FORM), later)["id"] == loose["id"] and TT.state_of(TT.list(FORM), later) == "confirmed"   # 「2025」 표에는 넓은 것만 맞는다
    assert TT.overlaps(loose, TT.list(FORM)) == [] and TT.overlaps(tight, TT.list(FORM)) == []   # 품는 사이는 알릴 것이 없다(늘 하나로 정해진다)
    TT.delete(tight["id"])
    assert TT.match(TT.list(FORM), same)["id"] == loose["id"]
    assert TT.pick([]) is None and TT.pick([loose]) is loose


def test_fitting_entries_that_do_not_contain_each_other_are_ambiguous():
    table = lambda y, org: _row(0, "구분", y, org, shade=S) + _row(1, "매출", "", "")   # noqa: E731
    j = _judge(table("2024", "한국선급"))
    by_year = TT.put(TT.entry_of(j, FORM, variable=["c103"]))                      # 연도 고정 · 기관 이름 가변
    by_org = TT.put(TT.entry_of(j, FORM, variable=["c102"]))                       # 기관 이름 고정 · 연도 가변 — 고정 머리글 칸이 서로를 품지 않는다
    both = _judge(table("2024", "한국선급"))["table"]
    assert len(TT.matches(TT.list(FORM), both)) == 2 and TT.match(TT.list(FORM), both) is None   # 둘 다 맞고 더 좁은 것이 없으면 어느 쪽도 쓰지 않는다
    assert TT.state_of(TT.list(FORM), both, by_year["type"]) == "ambiguous"
    assert TT.match(TT.list(FORM), _judge(table("2025", "한국선급"))["table"])["id"] == by_org["id"]
    assert TT.match(TT.list(FORM), _judge(table("2024", "한국해양대학교"))["table"])["id"] == by_year["id"]
    assert [e["id"] for e in TT.overlaps(by_year, TT.list(FORM))] == [by_org["id"]] and [e["id"] for e in TT.overlaps(by_org, TT.list(FORM))] == [by_year["id"]]   # 확정한 뒤 화면이 알리는 짝
    full = TT.put(TT.entry_of(j, FORM, variable=[]))                               # 둘 다 고정한 셋째 — 두 확정본을 다 품는다
    assert TT.match(TT.list(FORM), both)["id"] == full["id"] and TT.state_of(TT.list(FORM), both) == "confirmed"


def test_split_pieces_keep_their_own_entries_and_each_is_read_by_its_own():
    """astra 3차(나뉜 두 표) — 헤더 열을 복제해 나눈 두 조각은 둘 다 3×3 · 타입 · 병합 · 음영 자리가 같지만 앞 조각의 헤더 열은 1개, 뒤 조각은 2개다(둘째 열이 음영 없는 고정 이름).
    타입마다 하나로 덮지 않는다(둘 다 남는다) · 뒤 조각은 두 확정본에 다 맞지만 제 고정 이름까지 맞은 더 좁은 확정본으로 읽는다(앞 조각의 판정을 쓰면 고정 이름이 값 칸이 된다)."""
    piece = lambda names: [cell for r, (head, name) in enumerate(zip(("인건비", "재료비", "경비"), names)) for cell in ((r, 0, 1, 1, S, [head]), (r, 1, 1, 1, None, [name]), (r, 2, 1, 1, None, [""]))]   # noqa: E731
    front, back = piece(("", "", "")), piece(("현금", "현물", "기타"))
    a, ja = _confirm(front)
    b, jb = _confirm(back, user={"c102": "rowhead", "c105": "rowhead", "c108": "rowhead"})   # 사람이 둘째 열을 행헤더로 지정하고 확정
    assert (_roles(ja)["B1"], _roles(jb)["B1"]) == ("field", "rowhead") and a["type"] == b["type"] and a["geometry"] == b["geometry"]
    assert a["id"] != b["id"] and len(TT.list(FORM)) == 2                          # 같은 타입 · 같은 격자여도 따로 선 확정본
    assert TT.match(TT.list(FORM), ja["table"])["id"] == a["id"]                   # 앞 조각 — 뒤 조각의 고정 이름이 없어 하나만 맞는다
    assert sorted(e["id"] for e in TT.matches(TT.list(FORM), jb["table"])) == sorted([a["id"], b["id"]])
    assert TT.match(TT.list(FORM), jb["table"])["id"] == b["id"] and TT.state_of(TT.list(FORM), jb["table"], b["type"]) == "confirmed"   # 뒤 조각 — 더 좁은 확정본
    assert TT.match(TT.list(FORM), _judge(piece(("홍길동", "", "")))["table"])["id"] == a["id"]   # 앞 조각의 값 칸에 다른 글 — 앞 조각의 확정본


def test_a_table_confirmed_apart_is_read_by_its_own_narrower_entry():
    """astra 4차 7번 — 같은 양식의 2×3 표 둘: 격자 · 음영 · 1행 머리 · A2 가 같고, 첫 표는 B2 · C2 가 값 칸 / 둘째 표는 B2 가 고정 행머리 · C2 만 값 칸.
    첫 표만 확정하면 둘째 표도 그 확정본으로 맞아 B2 가 행헤더 → 필드로 읽힌다(끝점이 `also` 로 보인다). 둘째 표를 따로 확정한 뒤에는 표마다 제 확정본으로 읽는다."""
    head = _row(0, "구분", "세목", "금액", shade=S)
    first = lambda b2="", c2="": head + _row(1, "인건비", b2, c2)   # noqa: E731
    second = lambda c2="": head + _row(1, "인건비", "현금", c2)   # noqa: E731
    a, ja = _confirm(first())
    assert (_roles(ja)["B2"], _roles(ja)["C2"]) == ("field", "field") and _roles(_judge(second()))["B2"] == "rowhead"   # 내용으로 읽으면 둘째 표의 B2 는 행헤더
    only = TT.match(TT.list(FORM), _judge(second())["table"])
    assert only["id"] == a["id"]                                                   # 첫 확정본만 있을 때 — 둘째 표에도 그것이 맞는다(격자 · 고정 머리글이 같다)
    lost = _judge(second(), template=TT.template_of(only))
    assert _roles(lost)["B2"] == "field" and [d["ref"] for d in TT.differs(a, _judge(second())["table"])] == ["B1", "B2"]   # 고정 행머리가 값 칸으로 — 「다른 칸 2」(그 열의 머리 칸까지)로 드러난다
    mine = _judge(second(), template=TT.template_of(only), user={"c105": "rowhead"})   # 둘째 표에서 헤더 지정으로 B2 를 행헤더로 고치고
    entry = TT.entry_of(mine, FORM)
    assert not TT.same_judgment(a, TT.clean(entry)) and TT.separable(a, TT.clean(entry)) == (True, "")
    b = TT.put(entry)                                                              # 「이 표만 따로 확정」 — 새 확정본(첫 확정본은 그대로)
    assert b["id"] != a["id"] and TT.get(a["id"])["rev"] == 1 and [0, 0] not in [x[:2] for x in b["labels"] if x[3]] and [1, 1, "현금", 0] in b["labels"]
    entries = TT.list(FORM)
    for cells, want, b2 in ((second(), b, "rowhead"), (second("9"), b, "rowhead"),          # B2 에 그 고정 글이 있는 표 → 둘째 확정본
                            (first("7", "9"), a, "field"), (first("홍길동"), a, "field"),   # B2 에 다른 값이 든 첫 표 → 첫 확정본
                            (first(), a, "field")):                                         # B2 가 빈 첫 표 → 첫 확정본
        hit = TT.match(entries, _judge(cells)["table"])
        assert hit["id"] == want["id"] and _roles(_judge(cells, template=TT.template_of(hit)))["B2"] == b2
    blank = TT.entry_of(_judge(first(), template=TT.template_of(a), user={"c105": "rowhead"}), FORM)   # 첫 표에서 빈 B2 를 행헤더로 — 더 있는 고정 머리글이 빈 칸뿐이다
    ok, why = TT.separable(a, TT.clean(blank))
    assert not ok and "빈 칸뿐" in why
    fewer = TT.entry_of(_judge(first(), template=TT.template_of(a), user={"c104": "field"}), FORM)     # 고정 머리글이 줄어든 판정 — 따로 확정해도 이 표에는 지금 확정본이 쓰인다
    ok, why = TT.separable(a, TT.clean(fewer))
    assert not ok and "이 표에만 있는 고정 머리글이 없습니다" in why and TT.separable(a, TT.clean(TT.entry_of(ja, FORM)))[0] is False


# ---- 띠만으로는 못 되살리는 역할 · 따로 선 층 · 저절로 배우지 않음 ------------------------------------------------------------

def test_roles_survive_a_number_typed_into_a_shaded_value_cell():
    """astra 3차 P1(띠만 저장) — 음영 값 칸에 수를 채우면 같은 띠(헤더 1행 · 1열)로도 엔진은 그 칸을 필드 → 열헤더로 읽는다: 모든 칸의 역할을 자리로 지닌다.
    2026-11-23 부터 금액 꼴 수(「10000」 · 「10,000」)는 초안도 필드 그대로다(spec_헤딩_추출 ② §8 「음영 값 칸」 — 숫자 값만 든 음영 칸) — 아직 뒤집히는 것은 순번 꼴(1~3자리 수 홀로)이다."""
    table = lambda v: _row(0, "항목", "금액", shade=S) + [(1, 0, 1, 1, None, ["인건비"]), (1, 1, 1, 1, S, [v])] + _row(2, "재료비", "")   # noqa: E731
    e, blank = _confirm(table(""))
    filled = _judge(table("100"))
    assert _roles(blank)["B2"] == "field" and _roles(filled)["B2"] == "colhead"
    assert _roles(_judge(table("10000")))["B2"] == _roles(_judge(table("10,000")))["B2"] == "field"   # 금액 꼴은 초안이 값 칸으로 읽는다
    assert [(s["headerRows"], s["headerCols"]) for s in blank["subs"]] == [(s["headerRows"], s["headerCols"]) for s in filled["subs"]] == [(1, 1)]   # 띠는 그대로인데 역할이 달라졌다
    hit = TT.match(TT.list(FORM), filled["table"])
    assert hit["id"] == e["id"] and _roles(_judge(table("100"), template=TT.template_of(hit))) == _roles(blank)


def test_confirmation_is_a_separate_layer_from_a_works_designation():
    """astra 3차 P1(상속) — 한 작업에서 사람이 지정해 확정한 역할이 다른 문서에서 「그 작업의 사람 지정」(user)이 되지 않는다(빈 필드 제거의 작성 글 보호가 양식의 확정으로 풀리지 않게)."""
    cells = _row(0, "항목", "지급방법", "금액", shade=S) + _row(1, "인건비", "현금", "") + _row(2, "재료비", "현물", "")
    draft = _judge(cells)
    assert _roles(draft)["B2"] == _roles(draft)["B3"] == "rowhead"                  # 짧은 작성 글이 헤더 열로 읽힌다
    e, mine = _confirm(cells, user={"c105": "field", "c108": "field"})              # 작업 1 — 사람이 지급방법 두 칸을 필드로 지정하고 확정
    assert [x["id"] for x in mine["table"]["cells"] if x.get("user")] == ["c105", "c108"]
    other = _judge(cells, template=TT.template_of(TT.match(TT.list(FORM), draft["table"])))   # 작업 2 — 지정이 없는 다른 문서
    assert (_roles(other)["B2"], _roles(other)["B3"], other["source"]) == ("field", "field", "template")
    assert not any(x.get("user") for x in other["table"]["cells"])
    assert all(x["auto"] == x["role"] for x in other["table"]["cells"])
    top = _judge(cells, template=TT.template_of(e), user={"c104": "field"})        # 작업 2 의 지정은 그 위에 — user 는 그 칸에만
    assert [x["id"] for x in top["table"]["cells"] if x.get("user")] == ["c104"] and _roles(top)["A2"] == "field"


def test_nothing_is_learned_by_reading():
    """astra 3차 P1(자동 학습) — 「필드가 모두 빔」 은 빈 양식의 증명이 아니다(「현금」·「현물」 이 행헤더로 읽힌 채워진 표): 판정 · 견주기는 아무것도 저장하지 않는다."""
    cells = _row(0, "항목", "지급방법", "금액", shade=S) + _row(1, "인건비", "현금", "") + _row(2, "재료비", "현물", "")
    j = _judge(cells)
    assert all(not x["textFull"] for x in j["table"]["cells"] if x["role"] == "field")   # 모든 필드가 빈 「빈 양식」 처럼 보인다
    for _ in range(3):
        assert TT.match(TT.list(FORM), j["table"]) is None and TT.state_of(TT.list(FORM), j["table"], table_kv.type_key(j["table"])) == "none"
        TT.entry_of(j, FORM)
        _judge(cells, template=None)
    assert TT.list() == [] and not (Path(os.environ["NFM_HEADINGS"]) / TT.FILE).exists()


# ---- 저장 ------------------------------------------------------------------------------------------------------------

def test_put_edits_the_same_structure_and_checks_the_expected_rev(tmp_path):
    j = _judge(BUDGET)
    first = TT.put(TT.entry_of(j, FORM))
    assert first["rev"] == 1 and TT._ID.match(first["id"]) and first["at"]
    again = TT.put(TT.entry_of(_judge(BUDGET, user={"c105": "field"}), FORM))      # 같은 표 — 역할 하나를 고쳐 다시 확정: 격자와 고정 머리글… 이 달라졌다(「인건비」 가 머리글에서 빠짐)
    assert again["id"] != first["id"]                                              # 고정 머리글이 다르면 따로 선 확정본(덮지 않는다)
    assert TT.put(TT.entry_of(j, FORM))["rev"] == 2 and TT.get(first["id"])["rev"] == 2   # 구조 열쇠가 같으면 그것을 고친다
    swapped = TT.put(TT.entry_of(_judge(BUDGET, user={"c105": "field"}), FORM), replace=again["id"], expect=1)
    assert (swapped["id"], swapped["rev"]) == (again["id"], 2)
    with pytest.raises(TT.StaleVersion):
        TT.put(TT.entry_of(j, FORM), expect=1)                                     # 판 다름(지금 2)
    with pytest.raises(TT.StaleVersion):
        TT.put(TT.entry_of(j, FORM), replace="e0123456789")                        # 그 사이 지워진 확정본
    with pytest.raises(ValueError):
        TT.put(TT.entry_of(j, FORM), replace=again["id"])                          # 열쇠가 같은 확정본이 따로 있다 — 둘로 만들지 않는다
    moved = TT.put(TT.entry_of(_judge(_row(0, "항목", "금액", shade=S) + _row(1, "인건비", "")), FORM), replace=first["id"])   # 지금 쓰이는 확정본을 가리켜 고침(화면의 「다시 확정」)
    assert (moved["id"], moved["rev"], moved["rows"]) == (first["id"], 3, 2)
    assert [e["id"] for e in TT.list(FORM)] == [first["id"], again["id"]] and len(TT.list()) == 2 and TT.list("없는양식") == []
    assert TT.put(TT.entry_of(j, "양식B"))["rev"] == 1 and len(TT.list()) == 3 and len(TT.list(FORM)) == 2   # 양식마다 따로
    gone = TT.delete(again["id"])
    assert gone["id"] == again["id"] and TT.get(again["id"]) is None and [e["id"] for e in TT.removed()] == [again["id"]]   # 지운 것은 저장소가 지닌다
    assert [e["id"] for e in json.loads((tmp_path / "heads" / TT.FILE).read_text(encoding="utf-8"))["removed"]] == [again["id"]]
    with pytest.raises(KeyError):
        TT.delete(again["id"])
    assert TT.restore(again["id"]) == gone and TT.get(again["id"])["rev"] == 2 and TT.removed() == []   # 되살리면 id · 판 그대로
    for missing in (again["id"], "e0123456789"):                                   # 이미 되살린 것 · 지운 적 없는 id
        with pytest.raises(KeyError):
            TT.restore(missing)
    for bad in (gone, {"id": again["id"]}, None, "nope"):                          # 확정본 자체 · id 꼴이 아닌 것은 받지 않는다
        with pytest.raises(ValueError):
            TT.restore(bad)
    raw = json.loads((tmp_path / "heads" / TT.FILE).read_text(encoding="utf-8"))
    assert raw["version"] == 1 and set(raw["forms"]) == {FORM, "양식B"} and set(raw["forms"][FORM]) == {first["id"], again["id"]} and raw["removed"] == []


def test_removed_entries_are_kept_for_restore_only_the_last_twenty():
    table = lambda i: _row(0, "항목", f"머리글{i}", shade=S) + _row(1, "인건비", "")   # noqa: E731
    ids = [TT.put(TT.entry_of(_judge(table(i)), FORM, variable=[]))["id"] for i in range(TT.REMOVED_MAX + 2)]
    assert len(set(ids)) == len(ids) == 22
    for i in ids:
        TT.delete(i)
    assert [e["id"] for e in TT.removed()] == ids[2:] and TT.list() == []          # 마지막 20개만 지닌다
    with pytest.raises(KeyError):
        TT.restore(ids[0])                                                         # 밀려난 것은 되살리지 못한다
    again = TT.put(TT.entry_of(_judge(table(21)), FORM, variable=[]))              # 같은 구조의 확정본이 그 사이 새로 생겼다
    with pytest.raises(ValueError):
        TT.restore(ids[21])
    assert [e["id"] for e in TT.list(FORM)] == [again["id"]] and len(TT.removed()) == 20   # 실패한 되살리기는 아무것도 안 바꾼다
    assert TT.restore(ids[20])["id"] == ids[20] and len(TT.removed()) == 19 and {e["id"] for e in TT.list(FORM)} == {again["id"], ids[20]}
    with pytest.raises(KeyError):
        TT.restore(ids[20])                                                        # 이미 되살린 것 — 지운 것 목록에 더는 없다


def test_listed_entries_are_not_changed_by_using_them():
    e, j = _confirm(BUDGET)
    tpl = TT.template_of(TT.list(FORM)[0])
    tpl["roles"][0][2] = "field"
    tpl["bands"][0]["rows"][0] = 9
    TT.summary(TT.list(FORM)[0])["from"]["work"] = "x"
    assert TT.list(FORM)[0] == e == TT.get(e["id"]) and TT.load()["forms"][FORM][e["id"]] == e


def test_bad_entries_are_refused():
    e = TT.entry_of(_judge(BUDGET), FORM)
    for bad in ({**e, "roles": e["roles"][:-1]},                                    # 역할이 없는 칸
                {**e, "bands": [b for b in e["bands"] if b["id"] != e["bands"][-1]["id"]]},   # 어느 띠에도 안 드는 칸
                {**e, "labels": e["labels"][:-1]},                                  # 머리글 목록이 역할과 안 맞음
                {**e, "roles": [[r, c, "nonsense"] for r, c, _ in e["roles"]]},
                {**e, "geometry": e["geometry"][::-1]}, {**e, "type": "x"}, {**e, "form": ""}, {**e, "rows": 0}, "nope"):
        with pytest.raises(ValueError):
            TT.put(bad)
    assert TT.list() == []


def test_out_of_table_bands_and_non_finite_numbers_are_refused_without_saving(tmp_path):
    """astra 4차 9번 — 표 밖의 띠 · 띠보다 큰 머리 수 · 겹치는 띠 · 무한대 · 소수 · 터무니없이 큰 수는 저장 전에 걸린다(저장 파일은 생기지도 않는다)."""
    e = TT.entry_of(_judge(_row(0, "항목", "금액", shade=S) + _row(1, "인건비", "")), FORM)   # 2×2 표 — 띠 하나
    assert (e["rows"], e["cols"], len(e["bands"])) == (2, 2, 1)
    band, inf = e["bands"][0], float("inf")
    for bad in ({**e, "bands": [{**band, "rows": [0, 99]}]}, {**e, "bands": [{**band, "cols": [0, 99]}]},        # 표 밖의 띠
                {**e, "bands": [{**band, "headerRows": 100}]}, {**e, "bands": [{**band, "headerCols": 100}]},    # 띠보다 큰 머리 수
                {**e, "bands": [band, {**band, "id": "B"}]}, {**e, "bands": [{**band, "rows": [0, 1]}, {**band, "id": "B", "rows": [0, 2]}]},   # 겹치는 띠
                {**e, "bands": [{**band, "rows": [0, inf]}]}, {**e, "bands": [{**band, "headerRows": 1.0}]}, {**e, "bands": [{**band, "kind": ["matrix"]}]},
                {**e, "rows": inf}, {**e, "rows": 2.0}, {**e, "cols": True}, {**e, "rows": 10 ** 9},
                {**e, "geometry": [[0, 0, 1, 1, 1.0], *e["geometry"][1:]]}, {**e, "geometry": [[0, 0, 1, inf, 1], *e["geometry"][1:]]},
                {**e, "geometry": [[0, 0, 1, 3, 1], *e["geometry"][1:]]},                                           # 표 밖으로 나가는 병합
                {**e, "roles": [[0.0, 0, "corner"], *e["roles"][1:]]}, {**e, "labels": [[0, 0, "항목", 0.0], *e["labels"][1:]]}):
        with pytest.raises(ValueError):
            TT.put(bad)
    assert TT.list() == [] and not (tmp_path / "heads" / TT.FILE).exists()
    ok = TT.put(e)
    for at in (inf, float("nan"), -1, "어제", True):                                # 판 · 때도 — 무한대가 든 때는 그 뒤 목록을 JSON 으로 못 내게 만든다
        with pytest.raises(ValueError):
            TT._stamped(ok["id"], TT.clean(ok), ok["rev"], at)
    with pytest.raises(ValueError):
        TT._stamped(ok["id"], TT.clean(ok), float("inf"), ok["at"])
    json.dumps(TT.list(FORM), allow_nan=False)


def test_bad_entries_in_the_file_are_skipped_and_the_old_file_is_kept_aside(tmp_path):
    """astra 4차 9번 — 옛 판이 저장한 틀린 확정본(`at` 이 무한대 · 표 밖의 띠)이 파일에 있어도 그것만 건너뛴다: 목록 조회가 죽지 않고, 고쳐 쓸 때는 쓰기 전의 파일을 옆에 남긴다."""
    good, _ = _confirm(BUDGET)
    other = TT.put(TT.entry_of(_judge(_row(0, "항목", "금액", shade=S) + _row(1, "인건비", "")), FORM))
    path = tmp_path / "heads" / TT.FILE
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["forms"][FORM][other["id"]]["at"] = float("inf")
    raw["forms"][FORM]["e00000000aa"] = {**raw["forms"][FORM][good["id"]], "id": "e00000000aa", "bands": [{"id": "A", "rows": [0, 99], "cols": [0, 4], "kind": "matrix", "headerRows": 100, "headerCols": 100}]}
    raw["removed"] = [{**raw["forms"][FORM][good["id"]], "id": "e00000000bb", "rev": float("inf")}]
    text = json.dumps(raw, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    assert "Infinity" in text
    assert [e["id"] for e in TT.list(FORM)] == [good["id"]] and TT.load()["skipped"] == 3 and TT.removed() == []   # 틀린 셋만 건너뛴다
    json.dumps(TT.list(), allow_nan=False)
    assert TT.match(TT.list(FORM), _judge(BUDGET)["table"])["id"] == good["id"]
    assert path.read_text(encoding="utf-8") == text                                # 읽기만으로는 파일을 안 고친다
    assert TT.put(TT.entry_of(_judge(BUDGET), FORM))["rev"] == 2                    # 고치는 길도 막히지 않는다
    now = path.read_text(encoding="utf-8")
    assert "Infinity" not in now and "e00000000aa" not in now and "skipped" not in json.loads(now)
    kept = [p for p in path.parent.iterdir() if p.name.startswith(TT.FILE + ".skipped-")]
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == text          # 쓰기 전의 파일은 옆에 남는다(건너뛴 것을 조용히 잃지 않는다)
    assert TT.put(TT.entry_of(_judge(BUDGET), FORM))["rev"] == 3 and len([p for p in path.parent.iterdir() if ".skipped-" in p.name]) == 1   # 다음부터는 남길 것이 없다


def test_memory_store_and_a_broken_file(tmp_path, monkeypatch):
    path = tmp_path / "heads" / TT.FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ 깨진 파일", encoding="utf-8")
    assert TT.list(FORM) == []                                                     # 조회는 빈 목록
    for change in (lambda: TT.put(TT.entry_of(_judge(BUDGET), FORM)), lambda: TT.delete("e0123456789")):
        with pytest.raises(TT.Broken):
            change()
    assert path.read_text(encoding="utf-8") == "{ 깨진 파일"                        # 손상 파일은 덮지 않는다
    path.write_text(json.dumps({"version": 1, "forms": {FORM: ["확정본 묶음이 아님"]}}), encoding="utf-8")   # JSON 은 맞지만 파일의 꼴이 틀림 — 손상
    assert TT.list(FORM) == []
    with pytest.raises(TT.Broken):
        TT.put(TT.entry_of(_judge(BUDGET), FORM))
    for wrong in ({"version": 2, "forms": {}}, {"version": 1}, ["목록"]):
        path.write_text(json.dumps(wrong), encoding="utf-8")
        with pytest.raises(TT.Broken):
            TT.restore("e0123456789")
    monkeypatch.setenv("NFM_HEADINGS", "off")                                      # 저장 끔 — 메모리
    e = TT.put(TT.entry_of(_judge(BUDGET), FORM))
    assert [x["id"] for x in TT.list(FORM)] == [e["id"]] and TT.put(TT.entry_of(_judge(BUDGET), FORM))["rev"] == 2
    assert TT.delete(e["id"])["id"] == e["id"] and TT.list() == []


# ---- 끝점 ------------------------------------------------------------------------------------------------------------

@cache
def _raw():
    return PLAN.read_bytes()


@pytest.fixture()
def client():
    server.DOCS.clear()
    forms = Path(os.environ["NFM_FORMS"])
    forms.mkdir(parents=True, exist_ok=True)
    (forms / f"{FORM}.md").write_text(FORM_MD, encoding="utf-8")                   # 파일 이름 꼴 「*연구개발계획서*」 → 이 양식
    yield TestClient(server.app)
    server.DOCS.clear()


def _open(c, new=False):
    """PLAN 을 올린다 → (문서 id, 세션, 그 표의 판정 URL). new = 같은 파일의 작업이 있어도 새 작업으로(같은 양식의 다른 문서)."""
    r = c.post("/api/docs" + ("?new=1" if new else ""), files={"file": (PLAN.name, _raw())})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    return d, server.DOCS[d], f"/api/docs/{d}/tables/{CAREER}/type"


def _fill(c, d, cells, text="홍길동", tid=CAREER):
    r = c.post(f"/api/docs/{d}/tables/{tid}/fill/apply", json={"fills": [{"cell": k, "text": text} for k in cells]})
    assert r.status_code == 200, r.text


def _by(v):
    return {x["ref"]: x for x in v["judgment"]["cells"]}


BLANK = {"A1": "corner", "B1": "colhead", "C1": "colhead", "D1": "colhead", "A2": "rowhead", "B2": "field", "C2": "field", "D2": "field", "A3": "rowhead", "B3": "field", "C3": "field", "D3": "field"}
VALUES = ("B2", "C2", "D2", "B3", "C3", "D3")


def test_api_confirm_then_another_document_of_the_form_reads_the_same_roles(client, tmp_path):
    c = client
    a, sa, url = _open(c)
    v = c.get(url).json()
    assert v["form"] == {"key": FORM, "name": "시험 계획서"} and v["state"] == "none" and v["match"] is None and v["variants"] == [] and v["rev"] == sa.rev
    assert {r: x["role"] for r, x in _by(v).items()} == BLANK and v["judgment"]["source"] == "draft" and {x["by"] for x in v["judgment"]["cells"]} == {"draft"}
    assert v["name"] == "기간 · 기관명 · 직위" and v["type"] == "775a5a52ea23"
    assert [x["ref"] for x in v["judgment"]["cells"] if x["label"]] == ["A1", "B1", "C1", "D1", "A2", "A3"] and not any(x["variable"] or x["empty"] for x in v["judgment"]["cells"])
    assert _by(v)["A2"]["text"] == "yy.mm~yy.mm" and _by(v)["B2"]["text"] == ""   # 「기간」 열의 머리 칸은 사람이 채우는 칸이다(초안은 행헤더로 읽는다)
    assert c.get("/api/table-types", params={"form": FORM}).json() == {"form": FORM, "entries": []}           # 읽기만으로는 아무것도 안 생긴다
    assert c.get(f"/api/docs/{a}/tables/{CAREER}/style").json()["source"] == "draft"
    assert c.get("/api/table-types").json()["entries"] == []
    put = c.put(url, json={"rev": v["rev"], "match": None, "variable": [_by(v)["A2"]["id"], _by(v)["A3"]["id"]]})   # 기간 칸(사람이 채우는 머리 칸)은 가변으로 두고 확정
    assert put.status_code == 200, put.text
    w = put.json()
    assert w["state"] == "confirmed" and w["saved"] == {"id": w["match"]["id"], "rev": 1, "created": True, "overlaps": []} and w["judgment"]["source"] == "template"
    assert [x["ref"] for x in w["judgment"]["cells"] if x["variable"]] == ["A2", "A3"] and w["differs"] == [] and w["differsFrom"] == "draft"
    assert [x["ref"] for x in w["judgment"]["cells"] if x["fixed"]] == ["A1", "B1", "C1", "D1"] and v["also"] == [] and v["choose"] is None
    assert w["also"] == [{"table": CAREER_TWIN, "differs": 0}]                     # 같이 쓰이는 표 — 이 문서의 구조가 꼭 같은 다른 표(그 표의 초안과 다른 칸 없음)
    assert w["choose"] == {"needed": False, "canNew": False, "why": "지금 판정이 확정본과 같습니다 — 따로 확정할 것이 없습니다"}
    assert c.get(f"/api/docs/{a}").json()["pristine"] is True and sa.rev == v["rev"]                           # 확정은 문서를 안 바꾼다
    eid = w["match"]["id"]
    listed = c.get("/api/table-types", params={"form": FORM}).json()["entries"]
    assert [(e["id"], e["rev"], e["cells"], e["fixed"], e["variable"], e["from"]["work"], e["from"]["table"]) for e in listed] == [(eid, 1, 12, 4, 2, sa.id, CAREER)]
    assert [(x["id"], x["fits"], x["used"], x["why"]) for x in w["variants"]] == [(eid, True, True, "")]

    b, sb, url_b = _open(c, new=True)                                              # 같은 양식의 다른 문서(다른 작업) — 값을 짧은 글로 채운다
    assert b != a and sb.id != sa.id and c.get(url_b).json()["rev"] == 0
    cells = {x["ref"]: x["id"] for x in c.get(url_b).json()["judgment"]["cells"]}
    _fill(c, b, [cells[r] for r in VALUES])
    assert c.patch(f"/api/docs/{b}/blocks/{next(sb.doc._id(p) for p in sb.doc._ids[cells['A2']].iter(P))}", json={"text": "21.03~23.02"}).status_code == 200   # 가변 머리 칸도 채운다
    with sb.lock:
        drift = TM.judge(*[tables_api._table_now(sb, CAREER)[0]], CAREER)
    moved = {r: role for r, role in _roles(drift).items() if role != BLANK[r]}
    assert moved == {"A1": "colhead", "A2": "field", "A3": "field"}                # 내용으로 어림하면 흔들린다(기간 칸에 날짜를 쓰자 헤더 열이 없어졌다)
    vb = c.get(url_b).json()
    assert vb["state"] == "confirmed" and vb["match"]["id"] == eid and vb["judgment"]["source"] == "template"
    assert {r: x["role"] for r, x in _by(vb).items()} == BLANK and {x["by"] for x in vb["judgment"]["cells"]} == {"template"}
    assert _by(vb)["B2"]["text"] == "홍길동" and _by(vb)["A2"]["text"] == "21.03~23.02"                       # 글은 지금 문서의 것
    assert vb["differsFrom"] == "draft" and vb["differs"] == [{"cell": cells[r], "ref": r, "now": moved[r], "template": BLANK[r]} for r in ("A1", "A2", "A3")]   # 확정본이 바로잡은 칸
    assert vb["also"] == [{"table": CAREER_TWIN, "differs": 0}]
    twin = c.get(f"/api/docs/{b}/tables/{CAREER_TWIN}/type").json()
    assert twin["match"]["id"] == eid and twin["also"] == [{"table": CAREER, "differs": 3}]   # 쌍둥이 표에서 보면 — 값을 채운 표는 그 표의 초안과 3칸 다르다(확인할 표)
    style = c.get(f"/api/docs/{b}/tables/{CAREER}/style").json()
    assert style["source"] == "template" and style["template"] == {"id": eid, "rev": 1}                        # 표 서식 점검도 확정본으로
    with sb.lock:
        j, held, marks = tables_api._style_tb(sb, CAREER)
    assert j["source"] == "template" and marks is None and held == [] and not any(x.get("user") for x in j["table"]["cells"])
    raw = (tmp_path / "heads" / TT.FILE).read_text(encoding="utf-8")
    assert "홍길동" not in raw and "21.03" not in raw and "yy.mm" not in raw and "기관명" in raw                # 값 · 가변 머리글의 글은 저장 파일에 없다
    types = c.get(f"/api/docs/{b}/tables/types").json()
    assert types["form"]["key"] == FORM and types["entries"] == 1
    assert {t["table"]: t["state"] for t in types["tables"] if t["state"] != "none"} == {CAREER: "confirmed", CAREER_TWIN: "confirmed"}   # 문서 안의 구조가 꼭 같은 표도
    assert next(t for t in types["tables"] if t["table"] == CAREER)["type"] == vb["type"]
    assert len(c.get(f"/api/docs/{b}/tables/types", params={"full": 1}).json()["tables"]) == len(types["tables"])


def test_api_designation_on_top_stays_the_only_user_cell_and_held_blocks_confirm(client):
    c = client
    a, sa, url = _open(c)
    v = c.get(url).json()
    assert c.put(url, json={"rev": v["rev"], "match": None}).status_code == 200
    eid = c.get(url).json()["match"]["id"]
    heads, cid = f"/api/docs/{a}/tables/{CAREER}/heads", _by(v)["D2"]["id"]
    assert c.put(heads, json={"cells": [cid], "role": "rowhead"}).status_code == 200   # 이 작업의 헤더 지정 — 확정본 위에
    v2 = c.get(url).json()
    assert v2["state"] == "confirmed" and [(x["ref"], x["by"], x["role"], x["auto"]) for x in v2["judgment"]["cells"] if x["by"] == "user"] == [("D2", "user", "rowhead", "field")]
    assert {x["by"] for x in v2["judgment"]["cells"] if x["ref"] != "D2"} == {"template"}
    with sa.lock:
        j, _held, _marks = tables_api._style_tb(sa, CAREER)
    assert [x["id"] for x in j["table"]["cells"] if x.get("user")] == [cid] and j["source"] == "template"   # user 는 그 작업에서 지정한 칸에만
    stale = c.put(url, json={"rev": v2["rev"], "match": {"id": eid, "rev": 9}})
    assert stale.status_code == 409 and "그 사이 바뀌었습니다" in stale.json()["detail"]                       # 화면이 본 확정본과 다름
    assert v2["choose"]["needed"] is True and v2["choose"]["canNew"] is False and "빈 칸뿐" in v2["choose"]["why"]   # 지금 판정이 확정본과 다르다 — 골라야 한다(더 있는 고정 머리글이 빈 칸뿐이라 따로 확정은 안 됨)
    plain = c.put(url, json={"rev": v2["rev"], "match": v2["match"]})               # 고르지 않고 확정 → 멈춘다
    assert plain.status_code == 409 and "「이 확정본 고치기」" in plain.json()["detail"] and "「이 표만 따로 확정」" in plain.json()["detail"]
    apart = c.put(url, json={"rev": v2["rev"], "match": v2["match"], "mode": "new"})
    assert apart.status_code == 409 and "이 표만 따로 확정할 수 없습니다" in apart.json()["detail"] and "빈 칸뿐" in apart.json()["detail"]
    assert c.put(url, json={"rev": v2["rev"], "match": v2["match"], "mode": "both"}).status_code == 400
    assert c.get("/api/table-types", params={"form": FORM}).json()["entries"][0]["rev"] == 1                  # 거절된 요청은 확정본을 안 바꾼다
    again = c.put(url, json={"rev": v2["rev"], "match": v2["match"], "mode": "update"})   # 「이 확정본 고치기」 — 지정을 얹은 판정으로 그 확정본을 고친다
    assert again.status_code == 200 and again.json()["saved"] == {"id": eid, "rev": 2, "created": False, "overlaps": []}
    assert again.json()["choose"]["needed"] is False and len(c.get("/api/table-types", params={"form": FORM}).json()["entries"]) == 1
    pid = next(sa.doc._id(p) for p in sa.doc._ids[cid].iter(P))
    assert c.patch(f"/api/docs/{a}/blocks/{pid}", json={"text": "다른 글"}).status_code == 200   # 지정한 칸의 글이 바뀜 → 그 지정은 보류
    v3 = c.get(url).json()
    assert v3["held"] == [{"cell": cid, "role": "rowhead", "why": "글이 바뀜"}] and v3["state"] == "changed"   # 머리글(D2 「」)이 바뀌어 확정본도 안 맞는다
    assert [x["why"] for x in v3["variants"]] == ["머리글이 다릅니다 — D2 확정본 「(빈 칸)」 / 지금 「다른글」"] and v3["variants"][0]["fits"] is False
    held = c.put(url, json={"rev": v3["rev"], "match": None})
    assert held.status_code == 409 and held.json()["detail"] == HELD_MSG            # 보류가 있으면 확정하지 못한다
    assert c.get("/api/table-types", params={"form": FORM}).json()["entries"][0]["rev"] == 2 and table_heads.get(sa.id, CAREER) == {cid: "rowhead"}


def test_api_requires_a_form_a_rev_and_a_live_table(client):
    c = client
    a, sa, url = _open(c)
    v = c.get(url).json()
    assert c.put(url, json={"match": None}).status_code == 400 and c.put(url, json={"rev": "0"}).status_code == 400            # rev 가 있어야 한다
    assert c.put(url, json={"rev": v["rev"], "variable": "c1"}).status_code == 400 and c.put(url, json={"rev": v["rev"], "match": {"id": 3}}).status_code == 400
    wrong = c.put(url, json={"rev": v["rev"], "variable": [_by(v)["B2"]["id"]]})   # 값 칸은 가변 머리글이 아니다
    assert wrong.status_code == 400 and "헤더 · 제목 · 안내 칸" in wrong.json()["detail"]
    old = c.put(url, json={"rev": v["rev"] + 5})
    assert old.status_code == 409 and "문서가 바뀌었습니다" in old.json()["detail"]
    assert c.get(f"/api/docs/{a}/tables/t99999/type").status_code == 404 and c.put(f"/api/docs/{a}/tables/t99999/type", json={"rev": v["rev"]}).status_code == 404
    assert c.get("/api/table-types").json()["entries"] == []                       # 거절된 요청은 아무것도 안 남긴다
    F.set_choice(sa.id, "")                                                        # 「양식 없음」 으로 고정한 문서
    none = c.get(url).json()
    assert none["form"] is None and none["state"] == "none" and none["variants"] == [] and {r: x["role"] for r, x in _by(none).items()} == BLANK
    no = c.put(url, json={"rev": v["rev"]})
    assert no.status_code == 400 and no.json()["detail"] == "양식이 정해지지 않은 문서입니다 — 양식 정보에서 양식을 고르세요"
    assert c.get(f"/api/docs/{a}/tables/types").json() == {"form": None, "entries": 0, "tables": [], "rev": sa.rev}
    with sa.lock:
        tb = tables_api._table_now(sa, CAREER)[1]
    assert table_types_api.template_for(sa, tb) is None and table_types_api.template_for(sa, None) is None
    assert c.get(f"/api/docs/{a}/tables/{CAREER}/style").json()["template"] is None


def test_api_two_fitting_entries_are_not_used_and_delete_can_be_undone(client):
    c = client
    a, sa, url = _open(c)
    v = c.get(url).json()
    first = c.put(url, json={"rev": v["rev"], "match": None, "variable": [_by(v)["A3"]["id"]]}).json()["saved"]["id"]   # 고정 머리글 A1~D1 · A2(A3 는 가변)
    with sa.lock:
        stage1, tb = tables_api._table_now(sa, CAREER)
    second = TT.put(TT.entry_of(TM.judge(stage1, CAREER), FORM, variable=[_by(v)["A2"]["id"]]))   # 고정 머리글 A1~D1 · A3 인 둘째 확정본(다른 작업에서 생겼다고 치자) — 서로 품지 않는다 · 이 표에는 둘 다 맞는다
    assert second["id"] != first
    v2 = c.get(url).json()
    assert v2["state"] == "ambiguous" and v2["match"] is None and v2["judgment"]["source"] == "draft" and sorted(x["id"] for x in v2["variants"] if x["fits"]) == sorted([first, second["id"]])
    assert v2["also"] == [] and v2["choose"] is None
    assert c.get(f"/api/docs/{a}/tables/{CAREER}/style").json()["source"] == "draft"                         # 어느 쪽도 쓰지 않는다
    assert next(t for t in c.get(f"/api/docs/{a}/tables/types").json()["tables"] if t["table"] == CAREER)["state"] == "ambiguous"
    twice = c.put(url, json={"rev": v2["rev"], "match": None})
    assert twice.status_code == 409 and "맞는 확정본이 2개" in twice.json()["detail"]
    gone = c.delete(f"/api/table-types/{second['id']}")
    assert gone.status_code == 200 and gone.json()["removed"]["id"] == second["id"] and c.delete(f"/api/table-types/{second['id']}").status_code == 404
    assert c.get(url).json()["state"] == "confirmed" and c.get(url).json()["match"]["id"] == first
    back = c.post("/api/table-types/restore", json={"id": second["id"]})                                     # 알림의 「되돌리기」 — id 만 보낸다
    assert back.status_code == 200 and back.json()["entry"]["id"] == second["id"] and c.get(url).json()["state"] == "ambiguous"
    assert TT.get(second["id"]) == second                                                                    # id · 판 · 때 그대로
    assert c.post("/api/table-types/restore", json={"id": second["id"]}).status_code == 404                  # 지운 것 목록에 더는 없다


def test_api_restore_takes_an_id_only_and_never_stores_what_the_request_sends(client, tmp_path):
    """astra 4차 9번 — 되살리기 요청의 확정본을 믿으면 `at` 에 무한대가 든 것 · 표 밖의 띠 · 지운 적 없는 새 id 가 저장되고 그 뒤 목록 조회까지 죽는다: id 만 받고 서버가 지닌 지운 확정본에서만 되살린다."""
    c = client
    a, sa, url = _open(c)
    v = c.get(url).json()
    eid = c.put(url, json={"rev": v["rev"], "match": None}).json()["saved"]["id"]
    good = TT.get(eid)
    path = tmp_path / "heads" / TT.FILE
    before = path.read_text(encoding="utf-8")

    def post(text):
        return c.post("/api/table-types/restore", content=text.encode("utf-8"), headers={"Content-Type": "application/json"})
    forged = json.dumps({**good, "id": "e00000000aa"}, ensure_ascii=False)
    inf = forged.replace(f'"at": {json.dumps(good["at"])}', '"at": 1e309')         # 정상 확정본의 `at` 만 JSON 수 1e309(= 무한대)로
    assert '"at": 1e309' in inf
    out_of_table = json.dumps({**good, "id": "e00000000bb", "bands": [{"id": "A", "rows": [0, 99], "cols": [0, 4], "kind": "matrix", "headerRows": 100, "headerCols": 100}]}, ensure_ascii=False)
    for body in ('{"entry": %s}' % inf, '{"entry": %s}' % forged, '{"entry": %s}' % out_of_table, "{}", '{"id": 3}', '{"id": "x"}', '{"id": 1e309}'):
        assert post(body).status_code == 400, body[:60]                            # 확정본 자체는 받지 않는다 · id 가 있어야 한다
    for body in ('{"id": "e00000000aa", "entry": %s}' % inf, '{"id": "e00000000aa"}', '{"id": "%s"}' % eid):
        assert post(body).status_code == 404, body[:60]                            # 지운 적 없는 id(지금 있는 확정본의 id 도)
    assert path.read_text(encoding="utf-8") == before                              # 아무것도 저장되지 않았다
    listed = c.get("/api/table-types", params={"form": FORM})
    assert listed.status_code == 200 and [e["id"] for e in listed.json()["entries"]] == [eid] and c.get(url).json()["state"] == "confirmed"
    assert c.delete(f"/api/table-types/{eid}").status_code == 200
    back = post('{"id": "%s", "entry": %s}' % (eid, inf.replace("e00000000aa", eid)))   # 지운 뒤 — 요청이 같이 보낸 확정본(무한대)은 안 읽고 서버가 지닌 것을 되살린다
    assert back.status_code == 200 and TT.get(eid) == good and c.get("/api/table-types").status_code == 200
    assert "Infinity" not in path.read_text(encoding="utf-8") and "1e309" not in path.read_text(encoding="utf-8")


def test_api_update_or_confirm_this_table_apart(client):
    """astra 4차 7번(끝점) — 한 확정본이 두 표에 쓰이는데 둘째 표의 판정이 따로여야 할 때: 고르지 않으면 409 · 「이 표만 따로 확정」 은 새 확정본(첫 표는 그대로) · 그 뒤 표마다 제 확정본."""
    c = client
    a, sa, url = _open(c)
    v = c.get(url).json()
    first = c.put(url, json={"rev": v["rev"], "match": None}).json()["saved"]["id"]
    twin_url = f"/api/docs/{a}/tables/{CAREER_TWIN}/type"
    t0 = c.get(twin_url).json()
    assert t0["state"] == "confirmed" and t0["match"]["id"] == first and t0["also"] == [{"table": CAREER, "differs": 0}] and t0["choose"]["needed"] is False
    b2 = _by(t0)["B2"]["id"]
    _fill(c, a, [b2], text="고정이름", tid=CAREER_TWIN)                              # 둘째 표의 B2 는 값 칸이 아니라 고정 이름이다
    assert c.put(f"/api/docs/{a}/tables/{CAREER_TWIN}/heads", json={"cells": [b2], "role": "rowhead"}).status_code == 200   # 헤더 지정으로 행헤더로 고친다(지정이 확정본보다 먼저)
    t1 = c.get(twin_url).json()
    assert t1["state"] == "confirmed" and t1["match"]["id"] == first and (_by(t1)["B2"]["role"], _by(t1)["B2"]["auto"], _by(t1)["B2"]["by"]) == ("rowhead", "field", "user")
    assert t1["choose"] == {"needed": True, "canNew": True, "why": ""} and t1["also"] == [{"table": CAREER, "differs": 0}]
    plain = c.put(twin_url, json={"rev": t1["rev"], "match": t1["match"]})
    assert plain.status_code == 409 and "고르세요" in plain.json()["detail"] and TT.get(first)["rev"] == 1    # 고르지 않으면 첫 확정본을 고치지 않는다
    apart = c.put(twin_url, json={"rev": t1["rev"], "match": t1["match"], "mode": "new"})
    assert apart.status_code == 200, apart.text
    w = apart.json()
    second = w["saved"]["id"]
    assert w["saved"] == {"id": second, "rev": 1, "created": True, "overlaps": []} and second != first and TT.get(first)["rev"] == 1   # 새 확정본 — 첫 확정본은 그대로
    assert w["state"] == "confirmed" and w["match"]["id"] == second and w["also"] == [] and w["choose"]["needed"] is False
    assert sorted((x["id"], x["fits"], x["used"]) for x in w["variants"]) == sorted([(first, True, False), (second, True, True)])   # 둘 다 맞지만 더 좁은 둘째가 쓰인다
    v1 = c.get(url).json()
    assert v1["state"] == "confirmed" and v1["match"]["id"] == first and _by(v1)["B2"]["role"] == "field" and v1["also"] == []   # 첫 표는 첫 확정본 그대로(B2 는 값 칸)
    types = {t["table"]: t["state"] for t in c.get(f"/api/docs/{a}/tables/types").json()["tables"] if t["state"] != "none"}
    assert types == {CAREER: "confirmed", CAREER_TWIN: "confirmed"}
    assert c.get(f"/api/docs/{a}/tables/{CAREER_TWIN}/style").json()["template"] == {"id": second, "rev": 1}
    assert c.put(f"/api/docs/{a}/tables/{CAREER_TWIN}/heads", json={"cells": [b2], "role": None}).status_code == 200          # 지정을 풀어도 둘째 표는 제 확정본으로 행헤더
    t2 = c.get(twin_url).json()
    assert (_by(t2)["B2"]["role"], _by(t2)["B2"]["by"], t2["match"]["id"]) == ("rowhead", "template", second)


def test_api_a_looser_entry_next_to_a_narrower_one_keeps_both_in_use(client):
    """머리글이 달라 안 맞는 표에서 새로 확정하면 확정본이 둘이 된다(덮지 않는다) — 옛 머리글 그대로인 표는 둘 다 맞지만 더 좁은 옛 확정본으로 읽는다(어느 쪽도 안 쓰이는 표가 생기지 않는다)."""
    c = client
    a, sa, url = _open(c)
    v = c.get(url).json()
    first = c.put(url, json={"rev": v["rev"], "match": None}).json()["saved"]["id"]   # 「기간」 칸(yy.mm~yy.mm)을 고정 머리글로 둔 채 확정
    cid = _by(v)["A2"]["id"]
    assert c.patch(f"/api/docs/{a}/blocks/{next(sa.doc._id(p) for p in sa.doc._ids[cid].iter(P))}", json={"text": "21.03~23.02"}).status_code == 200
    v2 = c.get(url).json()
    assert v2["state"] == "changed" and v2["variants"][0]["why"] == "머리글이 다릅니다 — A2 확정본 「yy.mm~yy.mm」 / 지금 「21.03~23.02」"
    put = c.put(url, json={"rev": v2["rev"], "match": None})                         # 맞는 확정본이 없다 — mode 없이 새 확정본
    assert put.status_code == 200, put.text
    w = put.json()
    assert w["state"] == "confirmed" and w["saved"]["created"] is True and w["saved"]["id"] != first and w["saved"]["overlaps"] == []
    assert len(c.get("/api/table-types", params={"form": FORM}).json()["entries"]) == 2                      # 옛 확정본을 덮지 않는다
    twin = c.get(f"/api/docs/{a}/tables/{CAREER_TWIN}/type").json()
    assert twin["state"] == "confirmed" and twin["match"]["id"] == first and len([x for x in twin["variants"] if x["fits"]]) == 2   # 옛 머리글 그대로인 표 — 더 좁은 옛 확정본
    assert c.delete(f"/api/table-types/{first}").status_code == 200                                           # 옛 것을 지우면 넓은 새 확정본으로
    assert c.get(f"/api/docs/{a}/tables/{CAREER_TWIN}/type").json()["match"]["id"] == w["saved"]["id"] and c.get(url).json()["state"] == "confirmed"


def test_api_row_added_table_falls_back_to_the_draft(client):
    c = client
    a, sa, url = _open(c)
    v = c.get(url).json()
    assert c.put(url, json={"rev": v["rev"], "match": None}).status_code == 200
    pid = next(sa.doc._id(p) for p in sa.doc._ids[_by(v)["B3"]["id"]].iter(P))
    assert c.post(f"/api/docs/{a}/table", json={"id": pid, "op": "row_below"}).status_code == 200   # 행이 하나 늘었다
    v2 = c.get(url).json()
    assert v2["state"] == "changed" and v2["match"] is None and v2["judgment"]["source"] == "draft" and v2["judgment"]["rows"] == 4
    assert v2["variants"][0]["why"] == "행 · 열 · 칸 수가 다릅니다 — 확정본 3×4 · 칸 12 / 지금 4×4 · 칸 16"
    assert c.get(f"/api/docs/{a}/tables/{CAREER}/style").json()["source"] == "draft"
    twin = c.get(f"/api/docs/{a}/tables/{CAREER_TWIN}/type").json()
    assert twin["state"] == "confirmed"                                            # 구조가 그대로인 표는 여전히 확정본으로
