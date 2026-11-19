"""표의 키-값 추출 · 다른 표에 매핑(spec_테이블매니저 ② §7 「키-값 추출과 매핑」 · app/table_kv.py · app/table_kv_api.py) — 추출 · 계획(규칙 없이 · 매핑 규칙으로) · 표 타입 · 끝점."""
import hashlib
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import server, table_heads, table_maps, works
from app import table_kv as KV
from app import table_manager as TM
from app.hwpx_doc import TBL

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
DOCX = ROOT / "samples" / "기술수요조사서.docx"
SRC, DST = "t6599", "t6932"     # 「연구책임자」 인적사항 표 둘 — 머리글이 같은 표(키 11개 · 「주소」 칸에만 서식의 글 「(우:      )」)
OTHER = "t7685"                 # 「책임자 · 실무 담당자」 표 — 머리글이 다르다(「직장 › 기관명」 ↔ 「책임자 › 기관명」): 매핑 규칙이 있어야 이어진다
# 원본 표(SRC)에 심는 값 {칸 id: 글} — 키 「개인›국문|」 … 「직장›직위›전자우편|」
VALS = {"c6604": "홍길동", "c6608": "대한민국", "c6612": "Hong Gildong", "c6616": "12345678", "c6622": "한국선급", "c6626": "051-000-0000",
        "c6630": "연구본부", "c6634": "010-0000-0000", "c6638": "책임연구원", "c6642": "hong@example.org"}
NAME_TO, NATION_TO, ADDR_TO = "c6937", "c6941", "c6979"   # DST 의 「개인 › 국문」 · 「개인 › 국문 › 국적」 · 「직장 › 주소」 칸
SHADE = "#D6D6D6"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))   # 매핑 규칙(table_maps.json)도 이 폴더에 — 사용자 저장소를 안 건드린다
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    table_maps._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()
    table_maps._MEMORY.clear()


# ---- 합성 표 ----------------------------------------------------------------------------------------------------------

def _stage1(tid, cells, base):
    """합성 1단계 레코드(표 하나) — cells = [(행, 열, 행 병합, 열 병합, 음영, [문단 글…])]. 칸 id 는 c{base + 차례}. 문단 종류는 실제 분류기로."""
    rules, run = R.active(R.load(), ()), R._Run()
    tbl = {"t": "tbl", "id": tid, "rows": max(r + rs for r, _c, rs, *_ in cells), "cols": max(c + cs for _r, c, _rs, cs, *_ in cells), "cells": len(cells), "key": 1, "host": "x1"}
    recs, n = [], 0
    for i, (r, c, rs, cs, fill, paras) in enumerate(cells):
        cell = {"t": "cell", "id": f"c{base + i}", "row": r, "col": c, "rs": rs, "cs": cs, "fill": fill, "key": 10 + i}
        for t in paras:
            n += 1
            h = R.classify(t, rules, run)
            recs.append({"id": f"p{base * 10 + n}", "n": n, "path": [tbl, cell], "text": t, "kind": h["kind"], "blank": h["blank"], "char": {"text": {"bold": False}}})
    return {"paras": recs}


def _budget(y1="1차년도", y2="2차년도", mat="재료비", vals=None):
    """「연구개발비 사용계획」 꼴 — 머리 2행 · 머리 1열 · 합계 열/행 · 안내 줄. vals = {A1 주소: 글 | [문단 글…]} 로 값 칸을 바꾼다."""
    v = vals or {}

    def g(ref, default):
        got = v.get(ref, default)
        return got if isinstance(got, list) else [got]
    return [
        (0, 0, 2, 1, SHADE, ["구분"]), (0, 1, 1, 2, SHADE, [y1]), (0, 3, 1, 2, SHADE, [y2]), (0, 5, 2, 1, SHADE, ["합계"]),
        (1, 1, 1, 1, SHADE, ["현금"]), (1, 2, 1, 1, SHADE, ["현물"]), (1, 3, 1, 1, SHADE, ["현금"]), (1, 4, 1, 1, SHADE, ["현물"]),
        (2, 0, 1, 1, None, ["인건비"]), (2, 1, 1, 1, None, g("B3", "100")), (2, 2, 1, 1, None, g("C3", "20")), (2, 3, 1, 1, None, g("D3", "120")), (2, 4, 1, 1, None, g("E3", "30")), (2, 5, 1, 1, None, g("F3", "270")),
        (3, 0, 1, 1, None, [mat]), (3, 1, 1, 1, None, g("B4", "50")), (3, 2, 1, 1, None, g("C4", "10")), (3, 3, 1, 1, None, g("D4", "60")), (3, 4, 1, 1, None, g("E4", "10")), (3, 5, 1, 1, None, g("F4", "130")),
        (4, 0, 1, 1, None, ["합계"]), (4, 1, 1, 1, None, g("B5", "150")), (4, 2, 1, 1, None, g("C5", "30")), (4, 3, 1, 1, None, g("D5", "180")), (4, 4, 1, 1, None, g("E5", "40")), (4, 5, 1, 1, None, g("F5", "400")),
        (5, 0, 1, 6, None, ["※ 현물은 기관이 부담하는 금액을 적는다."]),
    ]


BLANK = {k: "" for k in "B3 C3 D3 E3 F3 B4 C4 D4 E4 F4 B5 C5 D5 E5 F5".split()}


def _tbx(tid, cells, base, user=None):
    """합성 표 → (판정된 표, 추출) — 초안 + 사람 지정(끝점과 같은 길)."""
    s1 = _stage1(tid, cells, base)
    j = TM.judge(s1, tid, stored=None, user=user)
    return j["table"], KV.extract(j["table"], lines=KV.cell_lines(s1, j["table"]))


def _ex(tid, cells, base, user=None):
    """합성 표 → 추출."""
    return _tbx(tid, cells, base, user)[1]


def _by_ref(ex):
    return {i["ref"]: i for i in ex["items"]}


def _pairs(p):
    return {x["label"]: x for x in p["pairs"]}


# ---- 추출 ------------------------------------------------------------------------------------------------------------

def test_extract_keys_labels_numbers_and_calc_cells():
    ex = _ex("t100", _budget(vals={"E4": ""}), 101)
    by = _by_ref(ex)
    assert ex["table"] == "t100" and ex["counts"] == {"items": 15, "keyed": 15, "empty": 1, "dups": 0} and ex["dups"] == []
    assert sorted(by) == sorted(f"{c}{r}" for r in (3, 4, 5) for c in "BCDEF")          # 필드 칸만 — 머리 칸 · 안내 줄은 없다
    b3 = by["B3"]
    assert (b3["key"], b3["label"], b3["row"], b3["col"]) == ("인건비|1차년도›현금", "인건비 | 1차년도 › 현금", ["인건비"], ["1차년도", "현금"])
    assert (b3["text"], b3["num"], b3["empty"], b3["calc"], b3["sub"], b3["cell"]) == ("100", 100, False, False, "A", "c110")
    assert by["F3"]["key"] == "인건비|합계" and by["F3"]["calc"] and by["B5"]["calc"] and by["F5"]["calc"] and not by["E3"]["calc"]   # 수식으로 셈하는 칸 = 합계 열 · 합계 행
    assert by["E4"]["empty"] and by["E4"]["text"] == "" and by["E4"]["num"] is None


def _cell(cid, row, col, role, text="", **kw):
    kinds = kw.pop("kinds", {"plain": 1} if text else {"empty": 1})
    return {"id": cid, "row": row, "col": col, "rs": 1, "cs": 1, "role": role, "textFull": text, "text": text[:80], "kinds": kinds, "nested": [], **kw}


def test_extract_edge_cells():
    tb = {"id": "t1", "rows": 9, "cols": 3, "cells": [
        _cell("h0", 0, 0, "rowhead", ""),                                    # 글 없는 머리 칸 — 투명
        _cell("h1", 0, 1, "rowhead", "총 인건비15) (A)"),                      # 각주 번호 · 코드를 뗀 핵심 글
        _cell("h2", 1, 0, "colhead", "금액 (천원)"),                           # 단위 괄호를 뗀다
        _cell("h3", 2, 0, "rowhead", "(단위: 천원)"),                          # 핵심 글이 빈 머리 — 키에서 투명
        _cell("f1", 0, 2, "field", "1,200", rowPath=["h0", "h1"], colPath=["h2"], num=1200.0, formulas=["f9"]),
        _cell("f2", 1, 2, "field", "", rowPath=[], colPath=[]),               # 경로 없는 칸 — 키 없음
        _cell("f3", 2, 2, "field", "글", rowPath=["h3"], colPath=[]),          # 머리는 있지만 핵심 글이 빔 — 키 없음
        _cell("f4", 3, 2, "field", "0,000", rowPath=["h1"], colPath=[]),      # 수 자리표시
        _cell("f5", 4, 2, "field", "○○대학교", rowPath=["h1"], colPath=[], kinds={"placeholder": 1}),   # 1단계의 자리표시 문단
        _cell("f6", 5, 2, "field", "-", rowPath=["h2"], colPath=[], num=0.0),  # 「-」 는 값(0)
        _cell("f7", 6, 2, "field", "", rowPath=["h2"], colPath=["h1"], kinds={"object": 1}),   # 그림만 든 칸
        _cell("f8", 7, 2, "field", "첫 줄 둘째 줄", rowPath=["h2"], colPath=["h2"]),
        _cell("n1", 8, 0, "note", "※ 안내"),
    ]}
    ex = KV.extract(tb, lines={"f8": ["첫 줄", "둘째 줄"]}, objs={"f8"})
    by = {i["cell"]: i for i in ex["items"]}
    assert list(by) == ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"]
    assert (by["f1"]["key"], by["f1"]["label"], by["f1"]["ref"], by["f1"]["num"], by["f1"]["calc"]) == ("총인건비|금액", "총 인건비15) (A) | 금액 (천원)", "C1", 1200, True)
    assert by["f2"]["key"] is None and by["f2"]["label"] == "" and by["f2"]["row"] == [] and by["f2"]["empty"]
    assert by["f3"]["key"] is None and by["f3"]["row"] == ["(단위: 천원)"] and not by["f3"]["empty"]
    assert by["f4"]["empty"] and by["f4"]["text"] == "0,000" and by["f5"]["empty"]      # 자리표시뿐 = 빈 칸
    assert not by["f6"]["empty"] and by["f6"]["num"] == 0
    assert by["f7"]["obj"] and not by["f7"]["empty"] and "obj" not in by["f1"]           # 칸 안 그림 — 빈 칸이 아니고 글을 쓰지 않는 칸
    assert by["f8"]["text"] == "첫 줄\n둘째 줄" and by["f8"]["obj"]                        # 문단마다 줄 · 부르는 쪽이 준 「표 · 그림이 든 칸」
    assert KV.extract(tb)["items"][-1]["text"] == "첫 줄 둘째 줄"                          # 줄을 안 주면 이어 붙인 글
    assert ex["dups"] == ["총인건비|"] and ex["counts"] == {"items": 8, "keyed": 6, "empty": 3, "dups": 1}   # f4 · f5 가 같은 키


def test_cell_lines_keep_paragraphs_and_forced_breaks():
    cells = _budget(vals={"B3": ["o 첫째", "", f"o 둘째{R.BR}이어진 줄"]})
    s1 = _stage1("t100", cells, 101)
    tb = TM.judge(s1, "t100")["table"]
    lines = KV.cell_lines(s1, tb)
    assert lines["c110"] == ["o 첫째", "o 둘째", "이어진 줄"] and lines["c111"] == ["20"]
    assert _by_ref(KV.extract(tb, lines=lines))["B3"]["text"] == "o 첫째\no 둘째\n이어진 줄"


# ---- 계획(규칙 없이) ---------------------------------------------------------------------------------------------------

def test_plan_five_statuses_and_never_overwrites():
    src = _ex("t100", _budget(vals={"E4": ""}), 101)
    dst = _ex("t200", _budget(vals={**BLANK, "C3": "20", "D3": "999", "E3": "0,000"}), 201)
    p = KV.plan(src, dst)
    by = _pairs(p)
    assert p["counts"] == {"fill": 5, "same": 1, "clash": 1, "calc": 7, "emptySrc": 1, "nonnum": 0, "check": 0, "unmatched": 0, "unmatchedSrc": 0, "unmatchedDst": 0, "byRule": 0}
    assert [x["to"] for x in p["pairs"]] == [i["cell"] for i in dst["items"]]            # 받을 표의 칸 차례로
    a = by["인건비 | 1차년도 › 현금"]
    assert (a["status"], a["from"], a["to"], a["text"], a["was"], a["key"], a["by"]) == ("fill", "c110", "c210", "100", "", "인건비|1차년도›현금", "key") and "why" not in a
    assert by["인건비 | 1차년도 › 현물"]["status"] == "same"
    clash = by["인건비 | 2차년도 › 현금"]
    assert (clash["status"], clash["text"], clash["was"]) == ("clash", "120", "999") and "덮지 않습니다" in clash["why"]   # 겹치면 안 덮는다
    ph = by["인건비 | 2차년도 › 현물"]
    assert (ph["status"], ph["was"]) == ("fill", "0,000")                                # 자리표시뿐인 칸은 빈 칸
    assert by["인건비 | 합계"]["status"] == "calc" and "수식" in by["인건비 | 합계"]["why"] and by["합계 | 합계"]["status"] == "calc"
    assert by["재료비 | 2차년도 › 현물"]["status"] == "emptySrc" and by["재료비 | 2차년도 › 현물"]["why"]
    assert all("fromKey" not in x for x in p["pairs"])


def _item(cell, key, text="", **kw):
    return {"cell": cell, "ref": cell.upper(), "sub": "A", "row": [], "col": [], "key": key, "label": key or "", "text": text, "empty": kw.pop("empty", not text), "num": None,
            "calc": kw.pop("calc", False), **kw}


def _exd(*items):
    keys = [i["key"] for i in items if i["key"] is not None]
    return {"table": "t", "items": list(items), "dups": [k for k in dict.fromkeys(keys) if keys.count(k) > 1], "counts": {}}


def test_plan_exact_keys_only_and_duplicate_keys_never_pair():
    src = _exd(_item("s1", "a|x", "1"), _item("s2", "dup|", "2"), _item("s3", "dup|", "3"), _item("s4", None, "4"), _item("s5", "only|src", "5"), _item("s6", "d2|", "6"),
               _item("s7", "sp|", "한국 선급\n본부"), _item("s8", "obj|", "8"), _item("s9", "pic|", "", empty=False, obj=True), _item("s10", "ph|", "0,000", empty=True))
    dst = _exd(_item("d1", "a|x"), _item("d2", "dup|"), _item("d3", "d2|"), _item("d4", "d2|"), _item("d5", None), _item("d6", "a|xx"),
               _item("d7", "sp|", "한국선급 본부"), _item("d8", "obj|", "", empty=False, obj=True), _item("d9", "pic|"), _item("d10", "ph|"))
    p = KV.plan(src, dst)
    got = {x["to"]: x for x in p["pairs"]}
    assert set(got) == {"d1", "d7", "d8", "d9", "d10"}
    assert got["d1"]["status"] == "fill" and got["d7"]["status"] == "same"               # 빈칸 · 줄 나눔만 다른 글은 같은 글
    assert got["d8"]["status"] == "clash" and "표 · 그림" in got["d8"]["why"]             # 칸 안에 표 · 그림 — 안 쓴다
    assert got["d9"]["status"] == "emptySrc" and "표 · 그림만" in got["d9"]["why"] and got["d10"]["status"] == "emptySrc"   # 자리표시뿐인 원본도 빈 것
    why_s = {u["cell"]: u["why"] for u in p["unmatched"]["src"]}
    why_d = {u["cell"]: u["why"] for u in p["unmatched"]["dst"]}
    assert set(why_s) == {"s2", "s3", "s4", "s5", "s6"} and set(why_d) == {"d2", "d3", "d4", "d5", "d6"}
    assert "이 표에 같은 키가 둘" in why_s["s2"] and "키가 없습니다" in why_s["s4"] and "같은 키가 없습니다" in why_s["s5"] and "상대 표에 같은 키가 둘" in why_s["s6"]
    assert "상대 표에 같은 키가 둘" in why_d["d2"] and "이 표에 같은 키가 둘" in why_d["d3"] and "키가 없습니다" in why_d["d5"] and "같은 키가 없습니다" in why_d["d6"]   # 「a|xx」 는 「a|x」 와 어림으로 잇지 않는다
    assert p["counts"]["unmatched"] == 10 and p["counts"]["unmatchedSrc"] == 5 and p["counts"]["unmatchedDst"] == 5


def test_sig_follows_cell_text_and_now():
    pair = {"to": "c1", "text": "값", "was": ""}
    s = KV.sig(pair)
    assert s == KV.sig(dict(pair)) and len(s) == 12
    assert len({s, KV.sig({**pair, "text": "값2"}), KV.sig({**pair, "was": "x"}), KV.sig({**pair, "to": "c2"})}) == 4


# ---- 표 타입 · 매핑 규칙 ------------------------------------------------------------------------------------------------

def _sha(sig):
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]


def test_type_key_is_the_shaded_headers_without_values_or_digits():
    tb, ex = _tbx("t100", _budget(), 101)
    k = KV.type_key(tb, ex)
    assert k == _sha("구분|차년도|차년도|합계|현금|현물|현금|현물") and k == KV.type_key(tb)   # 음영 칸의 글을 (행, 열) 차례로 — 빈칸 · 숫자 · 문장 부호를 빼고(ex 를 안 줘도 같다)
    blank = _tbx("t200", _budget(vals=BLANK), 201)
    names = _tbx("t210", _budget(vals={r: "홍길동" for r in BLANK}), 211)                 # 값 칸을 짧은 글로 채움 — 초안이 그 칸을 머리로 읽어 키 묶음은 바뀐다
    assert KV.type_key(*blank) == k and KV.type_key(*names) == k                         # 값을 채운 표와 빈 표는 같은 타입
    assert KV.form_key(names[1]) != KV.form_key(ex)                                      # (키 묶음의 해시로는 다른 표였다 — 타입으로 바꾼 까닭)
    later = _tbx("t300", _budget(y1="3차년도", y2="4차년도", vals=BLANK), 301)
    assert KV.type_key(*later) == k and KV.form_key(later[1]) != KV.form_key(ex)         # 숫자만 다른 머리글은 같은 타입 — 키는 다르다
    assert KV.type_key(*_tbx("t400", _budget(y1="1년차", y2="2년차", vals=BLANK), 401)) != k   # 머리글의 글이 다르면 다른 타입
    long = "가" * 30
    wide = {"id": "t9", "rows": 1, "cols": 3, "cells": [_cell("b", 0, 1, "colhead", f"{long} (단위: 천원)", shaded=True), _cell("a", 0, 0, "colhead", " ", shaded=True),
                                                        _cell("c", 0, 2, "colhead", "2024", shaded=True), _cell("d", 0, 3, "field", "값")]}
    assert KV.type_key(wide) == _sha("가" * 24)                                           # 칸마다 24자까지 · 뺀 뒤 빈 글인 칸(빈칸 · 숫자뿐)은 건너뛴다


def test_type_key_falls_back_to_the_first_row_then_to_the_key_set():
    plain = [(0, 0, 1, 1, None, ["항목 1"]), (0, 1, 1, 1, None, ["내용(2024)"]), (1, 0, 1, 1, None, ["가"]), (1, 1, 1, 1, None, [""])]
    tb, ex = _tbx("t500", plain, 501)
    assert not any(x["shaded"] for x in tb["cells"]) and KV.type_key(tb, ex) == _sha("항목|내용")   # 음영 칸이 없으면 첫 행의 글
    assert KV.type_key(*_tbx("t510", [*plain[:3], (1, 1, 1, 1, None, ["값을 채웠다"])], 511)) == _sha("항목|내용")   # 첫 행 밖의 값은 타입에 안 든다
    bare = {"id": "t9", "rows": 2, "cols": 2, "cells": [_cell("a", 0, 0, "rowhead", ""), _cell("b", 0, 1, "field", "12", rowPath=[], colPath=[]),
                                                        _cell("h", 1, 0, "rowhead", "이름"), _cell("f", 1, 1, "field", "", rowPath=["h"], colPath=[])]}
    assert KV.type_key(bare) == KV.form_key(KV.extract(bare)) == KV.type_key(bare, KV.extract(bare))   # 음영도 첫 행의 글도 없으면 키 묶음의 해시(마지막 대체)


def test_form_key_is_the_set_of_keys():
    src = _ex("t100", _budget(), 101)
    blank = _ex("t200", _budget(vals=BLANK), 201)
    other = _ex("t300", _budget(y1="1년차", y2="2년차", vals=BLANK), 301)
    assert KV.form_key(src) == KV.form_key(blank) and len(KV.form_key(src)) == 12        # 수로 채운 표는 키 묶음이 그대로
    assert KV.form_key(other) != KV.form_key(src)                                        # 머리글이 다르면 키 묶음도 다르다
    assert KV.form_key(_exd(_item("a", "k1|"), _item("b", "k2|"), _item("c", "k2|"), _item("d", None))) == KV.form_key(_exd(_item("x", "k2|"), _item("y", "k1|")))   # 중복 없이 · 정렬
    assert KV.key_parts("행1›행2|열1") == (["행1", "행2"], ["열1"]) and KV.key_parts("|열1›열2") == ([], ["열1", "열2"]) and KV.key_parts("행1|") == (["행1"], [])


def test_plan_rules_between_two_tables_of_the_same_type():
    src, dst = _tbx("t100", _budget(), 101), _tbx("t300", _budget(y1="3차년도", y2="4차년도", vals=BLANK), 301)
    assert KV.type_key(*src) == KV.type_key(*dst)                                        # 같은 타입 — 그래도 키는 다르다(「1차년도 › 현금」 ↔ 「3차년도 › 현금」)
    bare = KV.plan(src[1], dst[1])
    assert {x["label"] for x in bare["pairs"]} == {"인건비 | 합계", "재료비 | 합계", "합계 | 합계"} and bare["counts"]["unmatched"] == 24
    p = KV.plan(src[1], dst[1], {"alias": [{"from": "1차년도", "to": "3차년도"}, {"from": "2차년도", "to": "4차년도"}]})
    by = _pairs(p)
    assert p["counts"]["byRule"] == 12 and p["counts"]["unmatched"] == 0 and p["counts"]["fill"] == 8
    assert by["인건비 | 3차년도 › 현금"]["text"] == "100" and by["재료비 | 4차년도 › 현물"]["text"] == "10" and by["합계 | 3차년도 › 현금"]["status"] == "calc"
    shift = _ex("t400", _budget(y1="2차년도", y2="3차년도", vals=BLANK), 401)
    q = _pairs(KV.plan(src[1], shift, {"alias": [{"from": "1차년도", "to": "2차년도"}, {"from": "2차년도", "to": "3차년도"}]}))   # 바꿔 읽기는 조각마다 한 번(이어 읽지 않는다)
    assert q["인건비 | 2차년도 › 현금"]["text"] == "100" and q["인건비 | 3차년도 › 현금"]["text"] == "120" and all(x["by"] == "alias" for k, x in q.items() if "차년도" in k)


def test_plan_alias_reads_a_header_for_every_cell_under_it():
    src = _ex("t100", _budget(), 101)
    dst = _ex("t300", _budget(y1="1년차", y2="2년차", mat="연구재료비", vals={**BLANK, "C3": "777"}), 301)
    bare = KV.plan(src, dst)
    assert {x["label"] for x in bare["pairs"]} == {"인건비 | 합계", "합계 | 합계"} and bare["counts"]["byRule"] == 0   # 규칙이 없으면 꼭 같은 키뿐
    p = KV.plan(src, dst, {"alias": [{"from": "1차년도", "to": "1년차"}]})
    by = _pairs(p)
    assert p["counts"]["byRule"] == 4 and {k for k, x in by.items() if x["by"] == "alias"} == {"인건비 | 1년차 › 현금", "인건비 | 1년차 › 현물", "합계 | 1년차 › 현금", "합계 | 1년차 › 현물"}
    a = by["인건비 | 1년차 › 현금"]
    assert (a["status"], a["text"], a["from"], a["key"], a["fromKey"], a["fromLabel"]) == ("fill", "100", "c110", "인건비|1년차›현금", "인건비|1차년도›현금", "인건비 | 1차년도 › 현금")
    assert by["인건비 | 1년차 › 현물"]["status"] == "clash" and by["인건비 | 1년차 › 현물"]["was"] == "777"   # 규칙으로 맺은 짝도 겹치면 안 덮는다
    assert by["합계 | 1년차 › 현금"]["status"] == "calc" and by["인건비 | 합계"]["by"] == "key"                # 수식 칸도 그대로 · 그대로 같은 키는 by key
    left = {u["ref"]: u for u in p["unmatched"]["src"]}
    assert left["B4"]["as"] == "재료비|1년차›현금" and "as" not in left["D3"]            # 바꿔 읽었지만 대상에 없는 키 — 무엇으로 읽었는지 남긴다
    raw = KV.plan(src, dst, {"alias": [{"from": "1 차년도", "to": "1 년차"}]})            # 머리글을 그대로 적은 규칙도 핵심 글로 견준다
    assert raw["counts"]["byRule"] == 4


def test_plan_cell_pair_comes_first_and_read_duplicates_never_pair():
    src = _ex("t100", _budget(), 101)
    dst = _ex("t300", _budget(y1="1년차", y2="2년차", mat="연구재료비", vals=BLANK), 301)
    rules = {"alias": [{"from": "1차년도", "to": "1년차"}], "pairs": [{"from": "재료비|1차년도›현금", "to": "연구재료비|1년차›현금"}]}
    p = KV.plan(src, dst, rules)
    by = _pairs(p)
    mat = by["연구재료비 | 1년차 › 현금"]
    assert (mat["by"], mat["status"], mat["text"], mat["fromKey"]) == ("pair", "fill", "50", "재료비|1차년도›현금") and p["counts"]["byRule"] == 5   # 바꿔 읽기(→ 「재료비|1년차›현금」 — 대상에 없음)보다 칸 짝이 먼저
    twice = {"alias": rules["alias"], "pairs": [{"from": "인건비|1차년도›현금", "to": "인건비|1년차›현물"}]}   # 칸 짝이 보낸 키 = 바꿔 읽기가 다른 칸을 보낸 키
    q = KV.plan(src, dst, twice)
    assert "인건비 | 1년차 › 현물" not in _pairs(q) and "인건비 | 1년차 › 현금" not in _pairs(q)
    left = {u["ref"]: u for u in q["unmatched"]["src"]}
    assert "바꿔 읽은 뒤 같은 키가 둘" in left["B3"]["why"] and "바꿔 읽은 뒤 같은 키가 둘" in left["C3"]["why"] and left["B3"]["as"] == left["C3"]["as"] == "인건비|1년차›현물"
    assert "상대 표에 같은 키가 둘" in {u["ref"]: u["why"] for u in q["unmatched"]["dst"]}["C3"]
    assert KV.plan(src, dst, {"alias": [{"from": "", "to": "x"}, "bad"], "pairs": [{"from": 1}, None]})["counts"] == KV.plan(src, dst)["counts"]   # 꼴이 틀린 규칙은 없는 것


# ---- 구분 기준으로 묶어 넣기(다대일) -----------------------------------------------------------------------------------------

def _year_table(vals=None, labor="인건비", mat="재료비"):
    """한 차년도의 표(차년도 머리가 없다) — 「구분 | 현금 | 현물」 × 인건비 · 재료비 · 합계. vals = {A1 주소: 글}."""
    v = {"B2": "100", "C2": "20", "B3": "50", "C3": "10", "B4": "150", "C4": "30", **(vals or {})}
    return [(0, 0, 1, 1, SHADE, ["구분"]), (0, 1, 1, 1, SHADE, ["현금"]), (0, 2, 1, 1, SHADE, ["현물"]),
            (1, 0, 1, 1, None, [labor]), (1, 1, 1, 1, None, [v["B2"]]), (1, 2, 1, 1, None, [v["C2"]]),
            (2, 0, 1, 1, None, [mat]), (2, 1, 1, 1, None, [v["B3"]]), (2, 2, 1, 1, None, [v["C3"]]),
            (3, 0, 1, 1, None, ["합계"]), (3, 1, 1, 1, None, [v["B4"]]), (3, 2, 1, 1, None, [v["C4"]])]


Y2 = {"B2": "120", "C2": "30", "B3": "60", "C3": "10", "B4": "180", "C4": "40"}


def _two_years(dst_vals=None):
    """(받을 표 = 차년도 × 현금/현물 — 값 칸은 빔, 그 기준, 1차년도의 표, 2차년도의 표)."""
    tb, dst = _tbx("t100", _budget(vals={**BLANK, **(dst_vals or {})}), 101)
    return dst, KV.bases(tb)[0], _ex("t200", _year_table(), 201), _ex("t300", _year_table(Y2), 301)


def test_bases_are_value_headers_that_come_in_twos():
    tb, _ = _tbx("t100", _budget(vals=BLANK), 101)
    assert KV.bases(tb) == [{"basis": "year", "on": "col", "level": 0, "values": [{"part": "1차년도", "label": "1차년도", "cells": 6}, {"part": "2차년도", "label": "2차년도", "cells": 6}]}]
    assert KV.bases(_tbx("t200", _budget(y2="비고", vals=BLANK), 201)[0]) == []                      # 값 머리가 하나뿐이면 묶을 기준이 아니다
    assert KV.bases(_tbx("t300", _year_table(), 301)[0]) == []                                        # 한 차년도의 표 — 차년도 머리가 없다
    by_row = [(0, 0, 1, 1, SHADE, ["구분"]), (0, 1, 1, 1, SHADE, ["현금"]), (0, 2, 1, 1, SHADE, ["현물"]),
              (1, 0, 1, 1, SHADE, ["1차년도"]), (1, 1, 1, 1, None, [""]), (1, 2, 1, 1, None, [""]),
              (2, 0, 1, 1, SHADE, ["2차년도 (2026)"]), (2, 1, 1, 1, None, [""]), (2, 2, 1, 1, None, [""]),
              (3, 0, 1, 1, SHADE, ["합계"]), (3, 1, 1, 1, None, [""]), (3, 2, 1, 1, None, [""])]
    got = [b for b in KV.bases(_tbx("t400", by_row, 401)[0]) if b["basis"] == "year"]
    assert [(b["on"], b["level"], [(v["part"], v["label"], v["cells"]) for v in b["values"]]) for b in got] == [("row", 0, [("1차년도", "1차년도", 2), ("2차년도(2026)", "2차년도 (2026)", 2)])]   # 행 쪽


def test_value_of_and_suggest_never_guess():
    year = {"basis": "year", "on": "col", "level": 0, "values": [{"part": "1차년도", "label": "1차년도", "cells": 6}, {"part": "2차년도", "label": "2차 년도", "cells": 6}]}
    assert KV.value_of(year, "[2차년도 개발내용]") == "2차년도" and KV.value_of(year, "2026년 1 차 년도 연구개발비") == "1차년도" and KV.value_of(year, "2년차") == "2차년도"
    assert KV.value_of(year, "1차년도 ~ 2차년도") is None and KV.value_of(year, "3차년도") is None and KV.value_of(year, "1차 시험 결과") is None and KV.value_of(year, "") is None   # 둘이 맞거나 하나도 안 맞으면 값 없음
    org = {"basis": "org", "on": "row", "level": 0, "values": [{"part": "한국선급", "label": "한국선급", "cells": 3}, {"part": "주관연구개발기관", "label": "주관 연구개발기관", "cells": 3}]}
    assert KV.value_of(org, "o 한국 선급 (공동)") == "한국선급" and KV.value_of(org, "(1) 주관연구개발기관책임자") == "주관연구개발기관" and KV.value_of(org, "씨드로닉스") is None
    hints = {"zone": {"year": 2, "stage": 1, "orgName": "한국선급"}, "owner": "[1차년도 개발내용]", "before": ["1차년도 연구개발비", "(단위: 천원)"]}
    assert KV.suggest(year, hints) == {"value": "2차년도", "valueLabel": "2차 년도", "by": "zone"}       # 편집 구역이 먼저
    assert KV.suggest(year, {**hints, "zone": None})["by"] == "owner" and KV.suggest(year, {**hints, "zone": {"year": 7}, "owner": None}) == {"value": "1차년도", "valueLabel": "1차년도", "by": "text"}
    assert KV.suggest(org, hints) == {"value": "한국선급", "valueLabel": "한국선급", "by": "zone"}
    assert KV.suggest(year, {"zone": None, "owner": None, "before": ["2차년도 대비", "1차년도 연구개발비"]})["value"] == "1차년도"   # 표 앞 문단은 가까운 것부터
    assert KV.suggest(year, {"zone": {"year": True}, "owner": "연구개발비", "before": []}) == {"value": None, "valueLabel": None, "by": None}   # 못 읽으면 값 없음 — 사람이 고른다


def test_plan_grouped_puts_each_source_under_its_value_header():
    dst, base, y1, y2 = _two_years({"D3": "999"})
    p = KV.plan_grouped([{"ex": y1, "value": "1차년도", "table": "t200"}, {"ex": y2, "value": "2차년도", "table": "t300"}], dst, base)
    by = _pairs(p)
    assert p["counts"] == {"fill": 7, "same": 0, "clash": 1, "calc": 4, "emptySrc": 0, "nonnum": 0, "check": 0, "unmatched": 3, "unmatchedSrc": 0, "unmatchedDst": 3, "byRule": 0}
    a = by["인건비 | 1차년도 › 현금"]
    assert (a["status"], a["text"], a["from"], a["group"], a["value"], a["key"], a["src"], a["by"]) == ("fill", "100", {"table": "t200", "cell": "c205"}, "1차년도", "1차년도", "인건비|1차년도›현금", 0, "key")
    assert by["재료비 | 2차년도 › 현물"]["text"] == "10" and by["재료비 | 2차년도 › 현물"]["from"]["table"] == "t300" and by["합계 | 2차년도 › 현금"]["status"] == "calc"   # 수식 칸은 그대로 안 넣는다
    clash = by["인건비 | 2차년도 › 현금"]
    assert (clash["status"], clash["text"], clash["was"]) == ("clash", "120", "999") and "덮지 않습니다" in clash["why"]   # 묶어 넣어도 겹치면 안 덮는다
    assert [x["to"] for x in p["pairs"]] == [i["cell"] for i in dst["items"] if i["cell"] in {x["to"] for x in p["pairs"]}]   # 받을 표의 칸 차례로
    assert [(g["value"], g["label"], g["tables"], g["counts"]["fill"], g["counts"]["clash"], g["counts"]["calc"]) for g in p["groups"]] == [("1차년도", "1차년도", ["t200"], 4, 0, 2), ("2차년도", "2차년도", ["t300"], 3, 1, 2)]
    assert {i["ref"] for i in p["unmatched"]["dst"]} == {"F3", "F4", "F5"} and all("이 기준의 머리글 아래 칸이 아닙니다" == i["why"] for i in p["unmatched"]["dst"])   # 「합계」 열은 어느 차년도의 것도 아니다
    assert [(s["table"], s["value"], s["valueLabel"], s["counts"]["fill"]) for s in p["sources"]] == [("t200", "1차년도", "1차년도", 4), ("t300", "2차년도", "2차년도", 3)]
    assert KV.sig(a) != KV.sig({**a, "from": {"table": "t300", "cell": "c305"}}) and KV.sig(a) == KV.sig(dict(a))   # 도장에 원본 표 · 원본 칸이 든다


def test_plan_grouped_leaves_out_sources_without_a_value_and_cells_two_sources_claim():
    dst, base, y1, y2 = _two_years()
    p = KV.plan_grouped([{"ex": y1, "value": "1차년도", "table": "t200"}, {"ex": y2, "value": None, "table": "t300"}, {"ex": y2, "value": "3차년도", "table": "t310"}], dst, base)
    assert {x["from"]["table"] for x in p["pairs"]} == {"t200"} and p["counts"]["fill"] == 4                # 값이 없는 원본 · 그 값의 머리글이 없는 원본은 짝짓지 않는다
    assert ["why" in s for s in p["sources"]] == [False, True, True] and "정해지지 않았습니다" in p["sources"][1]["why"] and "머리글이 없습니다" in p["sources"][2]["why"]
    assert {i["ref"]: i["why"] for i in p["unmatched"]["dst"]}["D3"] == "이 값의 원본 표가 없습니다" and [g["value"] for g in p["groups"]] == ["1차년도"]
    twice = KV.plan_grouped([{"ex": y1, "value": "1차년도", "table": "t200"}, {"ex": y2, "value": "1차년도", "table": "t300"}], dst, base)   # 두 원본이 같은 값 — 같은 칸에 걸린다
    assert len(twice["pairs"]) == 12 and all(x["status"] == "clash" and "원본 둘이 같은 칸" in x["why"] for x in twice["pairs"]) and twice["counts"]["fill"] == 0
    flat = KV.plan_grouped([{"ex": y1, "value": None, "table": "t200"}, {"ex": y2, "value": None, "table": "t300"}], _ex("t400", _year_table({r: "" for r in Y2}), 401))   # 기준 없이 — 원본마다 키 그대로
    assert len(flat["pairs"]) == 12 and all(x["status"] == "clash" and x["group"] is None for x in flat["pairs"]) and [g["table"] for g in flat["groups"]] == ["t200", "t300"]
    one = KV.plan_grouped([{"ex": y1, "value": None, "table": "t200"}], _ex("t400", _year_table({r: "" for r in Y2}), 401))
    assert one["counts"]["fill"] == 4 and one["counts"]["calc"] == 2 and one["pairs"][0]["from"] == {"table": "t200", "cell": "c205"}


def test_plan_grouped_uses_mapping_rules_per_source():
    dst, base, _y1, y2 = _two_years()
    wage = _ex("t200", _year_table(labor="노무비", mat="원재료"), 201)
    bare = KV.plan_grouped([{"ex": wage, "value": "1차년도", "table": "t200"}, {"ex": y2, "value": "2차년도", "table": "t300"}], dst, base)
    assert bare["sources"][0]["counts"]["fill"] == 0 and bare["sources"][1]["counts"]["fill"] == 4 and bare["counts"]["unmatchedSrc"] == 4
    rules = [{"alias": [{"from": "노무비", "to": "인건비"}], "pairs": [{"from": "원재료|현금", "to": "재료비|1차년도›현금"}]}, None]   # 원본마다 다른 묶음 — 칸 짝의 대상 키는 1대1 때의 온전한 키
    p = KV.plan_grouped([{"ex": wage, "value": "1차년도", "table": "t200"}, {"ex": y2, "value": "2차년도", "table": "t300"}], dst, base, rules)
    by = _pairs(p)
    assert (by["인건비 | 1차년도 › 현금"]["by"], by["인건비 | 1차년도 › 현금"]["text"], by["인건비 | 1차년도 › 현물"]["by"]) == ("alias", "100", "alias")
    assert (by["재료비 | 1차년도 › 현금"]["by"], by["재료비 | 1차년도 › 현금"]["text"]) == ("pair", "50") and "재료비 | 1차년도 › 현물" not in by   # 칸 짝은 그 칸 하나만
    assert p["sources"][0]["counts"]["byRule"] == 3 and p["sources"][1]["counts"]["byRule"] == 0 and by["인건비 | 2차년도 › 현금"]["by"] == "key"
    other = KV.plan_grouped([{"ex": wage, "value": "2차년도", "table": "t200"}], dst, base, rules[0])      # 그 칸 짝은 1차년도의 칸을 가리킨다 — 2차년도로 넣을 때는 안 듣는다
    assert "재료비 | 2차년도 › 현금" not in _pairs(other) and _pairs(other)["인건비 | 2차년도 › 현금"]["by"] == "alias"


# ---- 더해서 넣기(다대일 — 셀 값 합산) · 나눠 넣기(일대다) ------------------------------------------------------------------------

def _sum3(a, b, dst=None, **kw):
    """(원본 둘의 추출, 받을 표의 추출) — 셋 다 한 차년도의 표(「구분 | 현금 | 현물」 × 인건비 · 재료비 · 합계)."""
    blank = {r: "" for r in Y2}
    return _ex("t200", _year_table({**blank, **a}, **kw), 201), _ex("t300", _year_table({**blank, **b}), 301), _ex("t100", _year_table({**blank, **(dst or {})}), 101)


def test_plan_sum_adds_the_numbers_of_the_same_key():
    a, b, dst = _sum3({"B2": "500", "C2": "1,000", "B3": "12.5", "C3": "값을 확인한다.", "B4": "150"}, {"B2": "700", "B3": "0.25", "C3": "10", "B4": "180"})
    p = KV.plan_sum([{"ex": a, "table": "t200"}, {"ex": b, "table": "t300"}], dst)
    by = _pairs(p)
    one = by["인건비 | 현금"]
    assert (one["status"], one["text"], one["sum"], one["was"], one["to"], one["by"]) == ("fill", "1,200", 1200, "", "c105", "key") and "check" not in one and "missing" not in one
    assert one["parts"] == [{"table": "t200", "cell": "c205", "text": "500", "num": 500}, {"table": "t300", "cell": "c305", "text": "700", "num": 700}] and one["from"] == [{"table": "t200", "cell": "c205"}, {"table": "t300", "cell": "c305"}]
    part = by["인건비 | 현물"]
    assert (part["status"], part["text"], part["sum"], part["missing"], part["check"]) == ("fill", "1,000", 1000, 1, True)   # 일부만 값 — 있는 것만 더하고 확인을 붙인다
    assert (by["재료비 | 현금"]["text"], by["재료비 | 현금"]["sum"]) == ("12.75", 12.75)                # 소수 자리 = 원본들의 최대
    bad = by["재료비 | 현물"]
    assert (bad["status"], bad["text"], bad["sum"]) == ("nonnum", "", None) and "수가 아닌 글" in bad["why"] and "check" not in bad   # 수가 아닌 글 — 안 넣는다
    assert by["합계 | 현금"]["status"] == "calc" and by["합계 | 현금"]["sum"] == 330 and by["합계 | 현물"]["status"] == "emptySrc"   # 합계 줄은 표의 수식이 셈한다 · 원본이 모두 빔
    assert p["counts"] == {"fill": 3, "same": 0, "clash": 0, "calc": 1, "emptySrc": 1, "nonnum": 1, "check": 1, "unmatched": 0, "unmatchedSrc": 0, "unmatchedDst": 0, "byRule": 0}
    assert [(x["table"], x["counts"]["pairs"], x["counts"]["nums"]) for x in p["sources"]] == [("t200", 6, 4), ("t300", 6, 4)]
    assert KV.sig(one) != KV.sig({**one, "text": "1,300"}) and KV.sig(one) != KV.sig({**one, "from": one["from"][:1]})   # 합이나 원본 칸이 바뀌면 도장이 달라진다


def test_plan_sum_same_clash_and_the_shape_of_the_number():
    a, b, dst = _sum3({"B2": "500", "C2": "1200", "B3": "-", "C3": "10%"}, {"B2": "700", "C2": "300", "B3": "-", "C3": "15%"}, {"B2": "1,200", "C2": "99", "C3": "00%"})
    by = _pairs(KV.plan_sum([{"ex": a, "table": "t200"}, {"ex": b, "table": "t300"}], dst))
    assert by["인건비 | 현금"]["status"] == "same"                                                      # 받을 칸의 수 = 합(쉼표만 다름)
    clash = by["인건비 | 현물"]
    assert (clash["status"], clash["text"], clash["was"]) == ("clash", "1500", "99") and "덮지 않습니다" in clash["why"]   # 다른 값 — 안 덮는다 · 쉼표 없이 네 자리를 적은 원본이 있으면 쉼표를 안 쓴다
    assert (by["재료비 | 현금"]["status"], by["재료비 | 현금"]["text"], by["재료비 | 현금"]["sum"]) == ("fill", "-", 0)   # 원본이 모두 「-」 — 그 「-」
    assert (by["재료비 | 현물"]["status"], by["재료비 | 현물"]["text"], by["재료비 | 현물"]["was"]) == ("fill", "25%", "00%")   # 자리표시뿐인 칸은 빈 칸 · 뒤 글은 원본이 모두 같은 것을 붙였을 때
    a, b, dst = _sum3({"B2": "3명", "C2": "1,000", "B3": "(100)", "C3": "5"}, {"B2": "4명", "C2": "2,500.5", "B3": "30", "C3": "-"}, {"C3": "0,000"})
    by = _pairs(KV.plan_sum([{"ex": a, "table": "t200"}, {"ex": b, "table": "t300"}], dst))
    assert [by[k]["text"] for k in ("인건비 | 현금", "인건비 | 현물", "재료비 | 현금", "재료비 | 현물")] == ["7명", "3,500.5", "-70", "5"]   # 단위 · 쉼표 · 괄호 음수 · 「-」 = 0


def test_plan_sum_sources_without_the_key_and_mapping_rules():
    a, b, dst = _sum3({"B2": "500", "B3": "5"}, {"B2": "700", "B3": "6"}, labor="노무비")
    srcs = [{"ex": a, "table": "t200"}, {"ex": b, "table": "t300"}]
    p = KV.plan_sum(srcs, dst)
    lone = _pairs(p)["인건비 | 현금"]
    assert (lone["status"], lone["text"], lone["missing"], lone["check"], len(lone["parts"])) == ("fill", "700", 1, True, 1)   # 그 키의 칸이 없는 원본도 「값이 없는 원본」
    assert _pairs(p)["재료비 | 현금"]["text"] == "11" and {i["ref"] for i in p["unmatched"]["src"] if i["table"] == "t200"} == {"B2", "C2"} and p["counts"]["check"] == 1
    q = KV.plan_sum(srcs, dst, [{"alias": [{"from": "노무비", "to": "인건비"}]}, None])                   # 원본마다 다른 묶음 — 바꿔 읽으면 같이 더한다
    both = _pairs(q)["인건비 | 현금"]
    assert (both["text"], both["by"], "check" in both) == ("1,200", "alias", False) and q["counts"]["byRule"] == 2 and q["sources"][0]["counts"]["byRule"] == 2
    assert KV.plan_sum(srcs[:1], dst)["counts"]["fill"] == 1 and KV.plan_sum([], dst)["pairs"] == []


def _split3(tgt1=None, tgt2=None):
    """(원본 = 차년도 × 현금/현물 표(값이 든), 그 기준, 받을 표 둘 = 한 차년도의 표(값 칸은 빔))."""
    tb, src = _tbx("t100", _budget(), 101)
    blank = {r: "" for r in Y2}
    return src, KV.bases(tb)[0], _ex("t200", _year_table({**blank, **(tgt1 or {})}), 201), _ex("t300", _year_table({**blank, **(tgt2 or {})}), 301)


def test_plan_split_sends_each_value_to_its_own_table():
    src, base, t1, t2 = _split3(tgt2={"B2": "999"})
    p = KV.plan_split(src, [{"ex": t1, "value": "1차년도", "table": "t200"}, {"ex": t2, "value": "2차년도", "table": "t300"}], base)
    got = {(x["to"]["table"], x["label"]): x for x in p["pairs"]}
    a = got[("t200", "인건비 | 현금")]
    assert (a["status"], a["text"], a["from"], a["fromRef"], a["to"], a["ref"], a["group"], a["value"], a["tgt"], a["key"]) == ("fill", "100", "c110", "B3", {"table": "t200", "cell": "c205"}, "B2", "1차년도", "1차년도", 0, "인건비|현금")
    assert got[("t300", "재료비 | 현물")]["text"] == "10" and got[("t300", "재료비 | 현물")]["from"] == "c119" and got[("t200", "합계 | 현금")]["status"] == "calc"   # 받을 표의 수식 칸에는 안 넣는다
    clash = got[("t300", "인건비 | 현금")]
    assert (clash["status"], clash["text"], clash["was"]) == ("clash", "120", "999") and "덮지 않습니다" in clash["why"]   # 겹치면 안 덮는다
    assert p["counts"] == {"fill": 7, "same": 0, "clash": 1, "calc": 4, "emptySrc": 0, "nonnum": 0, "check": 0, "unmatched": 3, "unmatchedSrc": 3, "unmatchedDst": 0, "byRule": 0}
    assert {i["ref"]: i["why"] for i in p["unmatched"]["src"]} == {r: "이 기준의 머리글 아래 칸이 아닙니다" for r in ("F3", "F4", "F5")}   # 원본의 「합계」 열은 어느 차년도의 것도 아니다
    assert [(g["table"], g["value"], g["label"], g["counts"]["fill"], g["counts"]["clash"]) for g in p["groups"]] == [("t200", "1차년도", "1차년도", 4, 0), ("t300", "2차년도", "2차년도", 3, 1)]
    assert [x["to"]["table"] for x in p["pairs"]] == ["t200"] * 6 + ["t300"] * 6 and len({KV.sig(x) for x in p["pairs"]}) == 12   # 받을 표 차례 · 그 표의 칸 차례


def test_plan_split_leaves_out_targets_without_a_value_and_uses_rules():
    src, base, t1, t2 = _split3()
    p = KV.plan_split(src, [{"ex": t1, "value": "1차년도", "table": "t200"}, {"ex": t2, "value": None, "table": "t300"}, {"ex": t2, "value": "3차년도", "table": "t310"}], base)
    assert {x["to"]["table"] for x in p["pairs"]} == {"t200"} and ["why" in t for t in p["targets"]] == [False, True, True]   # 값이 없는 받을 표 · 그 값의 머리글이 없는 받을 표에는 안 넣는다
    assert "정해지지 않았습니다" in p["targets"][1]["why"] and "머리글이 없습니다" in p["targets"][2]["why"] and [g["table"] for g in p["groups"]] == ["t200"]
    assert {i["ref"]: i["why"] for i in p["unmatched"]["src"]}["D3"] == "이 값의 받을 표가 없습니다"
    wage = _ex("t200", _year_table({r: "" for r in Y2}, labor="노무비", mat="원재료"), 201)
    bare = KV.plan_split(src, [{"ex": wage, "value": "1차년도", "table": "t200"}], base)
    assert bare["counts"]["fill"] == 0 and bare["counts"]["unmatchedDst"] == 4                              # 키가 다른 받을 표 — 합계 줄만 닿는다(수식 칸)
    rules = {"alias": [{"from": "인건비", "to": "노무비"}], "pairs": [{"from": "재료비|1차년도›현금", "to": "원재료|현금"}]}   # 칸 짝의 원본 키는 1대1 때의 온전한 키
    q = {x["label"]: x for x in KV.plan_split(src, [{"ex": wage, "value": "1차년도", "table": "t200"}], base, rules)["pairs"]}
    assert (q["노무비 | 현금"]["by"], q["노무비 | 현금"]["text"], q["원재료 | 현금"]["by"], q["원재료 | 현금"]["text"]) == ("alias", "100", "pair", "50") and "원재료 | 현물" not in q
    two = KV.plan_split(src, [{"ex": t1, "value": "1차년도", "table": "t200"}, {"ex": t2, "value": "1차년도", "table": "t300"}], base)   # 받을 표 둘이 같은 값 — 둘 다 받는다(겹치는 칸이 아니다)
    assert two["counts"]["fill"] == 8 and {x["from"] for x in two["pairs"] if x["to"]["table"] == "t300"} == {x["from"] for x in two["pairs"] if x["to"]["table"] == "t200"}


# ---- 구분 기준의 값 고르기 ------------------------------------------------------------------------------------------------

def test_div_of_comes_from_the_key_of_the_receiving_cell():
    tb, dst = _tbx("t100", _budget(vals=BLANK), 101)
    bs = KV.bases(tb)
    by = _by_ref(dst)
    assert KV.div_of(bs, by["B3"]["key"]) == {"year": "1차년도"} and KV.div_of(bs, by["E4"]["key"]) == {"year": "2차년도"}
    assert KV.div_of(bs, by["F3"]["key"]) == {} and KV.div_of(bs, None) == {} and KV.div_of([], by["B3"]["key"]) == {}   # 「합계」 열은 그 기준의 머리 아래가 아니다
    two = [{"basis": "year", "on": "col", "level": 0, "values": [{"part": "1차년도", "label": "1차년도", "cells": 1}]}, {"basis": "org", "on": "row", "level": 0, "values": [{"part": "인건비", "label": "인건비", "cells": 1}]},
           {"basis": "year", "on": "row", "level": 0, "values": [{"part": "인건비", "label": "인건비", "cells": 1}]}]
    assert KV.div_of(two, "인건비|1차년도›현금") == {"year": ["1차년도", "인건비"], "org": "인건비"} and KV.div_of(two, "인건비|2차년도›현금") == {"org": "인건비", "year": "인건비"}   # 기준이 여럿이면 기준마다 · 같은 기준이 두 곳이면 그 칸이 놓인 값 모두(하나면 글 · 둘이면 목록)


def test_with_div_tags_pairs_and_counts_each_value():
    src, a, b = _ex("t200", _budget(vals={"E4": ""}), 201), None, None
    tb, dst = _tbx("t100", _budget(vals={**BLANK, "D3": "999"}), 101)
    p = KV.plan(src, dst)
    bs = KV.with_div(KV.bases(tb), p["pairs"])
    by = _pairs(p)
    assert by["인건비 | 1차년도 › 현금"]["div"] == {"year": "1차년도"} and by["재료비 | 2차년도 › 현물"]["div"] == {"year": "2차년도"} and by["인건비 | 합계"]["div"] == {}
    assert [(v["part"], v["cells"], v["pairs"], v["fill"]) for v in bs[0]["values"]] == [("1차년도", 6, 6, 4), ("2차년도", 6, 6, 2)]   # 1차년도: 인건비 · 재료비 넷 · 2차년도: 겹침 1 · 원본 빈 칸 1 · 넣을 수 있음 2(합계 줄 둘은 수식 칸)
    assert KV.bases(tb)[0]["values"][0] == {"part": "1차년도", "label": "1차년도", "cells": 6}             # 준 것은 안 고친다
    y1, y2 = _ex("t300", _year_table(), 301), _ex("t310", _year_table(Y2), 311)
    full = _tbx("t400", _budget(), 401)
    sp = KV.plan_split(full[1], [{"ex": _ex("t500", _year_table({r: "" for r in Y2}), 501), "value": "2차년도", "table": "t500"}], KV.bases(full[0])[0])
    keys = {i["cell"]: i["key"] for i in full[1]["items"]}
    got = KV.with_div(KV.bases(full[0]), sp["pairs"], lambda x: keys[x["from"]])                          # 나눠 넣기 — 원본 칸의 키로
    assert all(x["div"] == {"year": "2차년도"} for x in sp["pairs"]) and [(v["part"], v["pairs"], v["fill"]) for v in got[0]["values"]] == [("1차년도", 0, 0), ("2차년도", 6, 4)] and (y1, y2, a, b) is not None


# ---- 끝점 ------------------------------------------------------------------------------------------------------------

@cache
def _raw():
    return PLAN.read_bytes()


def _open(c, new=False):
    r = c.post("/api/docs" + ("?new=1" if new else ""), files={"file": (PLAN.name, _raw())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _seed(c, d):
    """원본 표(SRC)의 값 칸을 채운다 — 표 채우기 반영 끝점으로(편집 차례가 오른다)."""
    r = c.post(f"/api/docs/{d}/tables/{SRC}/fill/apply", json={"fills": [{"cell": k, "text": v} for k, v in VALS.items()]})
    assert r.status_code == 200, r.text


def _text(d, tid, cid):
    return next(x for x in server.DOCS[d].doc.table_block(tid)["cells"] if x["id"] == cid)["text"]


def _free(sess):
    """세션 잠금이 새지 않았는가 — 잡을 수 있으면 된다(배경의 작업 저장이 잠깐 잡고 있을 수 있어 「지금 안 잡혀 있음」 으로 보지 않는다)."""
    got = sess.lock.acquire(timeout=10)
    if got:
        sess.lock.release()
    return got


def _url(d, tid, tail=""):
    return f"/api/docs/{d}/tables/{tid}/kv{tail}"


@pytest.fixture
def client():
    server.DOCS.clear()
    try:
        yield TestClient(server.app)
    finally:
        server.DOCS.clear()


def test_api_kv_get(client):
    d = _open(client)
    s = server.DOCS[d]
    r = client.get(_url(d, SRC))
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["table"] == SRC and v["rev"] == s.rev and v["held"] == [] and v["counts"] == {"items": 11, "keyed": 11, "empty": 10, "dups": 0} and len(v["type"]) == 12 and "form" not in v
    by = {i["cell"]: i for i in v["items"]}
    assert by["c6604"]["key"] == "개인›국문|" and by["c6604"]["label"] == "개인 › 국문" and by["c6604"]["empty"] and by["c6646"]["text"].startswith("(우:")
    assert client.get(_url(d, DST)).json()["type"] == v["type"] and client.get(_url(d, OTHER)).json()["type"] != v["type"]   # 머리글이 같은 표끼리 같은 타입
    _seed(client, d)
    full = client.get(_url(d, SRC)).json()
    assert full["counts"]["empty"] == 0 and full["type"] == v["type"]                                    # 값을 채운 표와 빈 표가 같은 타입
    assert client.get(_url(d, "t99999")).status_code == 404
    box = next(i for i, e in s.doc._ids.items() if e.tag == TBL and s.doc._attached(e) and table_heads.table(s.doc, i) is None)   # 1칸 표(상자)
    assert client.get(_url(d, box)).status_code == 400


def test_api_plan_then_apply_only_picked_fill_cells(client):
    d = _open(client)
    s = server.DOCS[d]
    before = client.post(_url(d, DST, "/plan"), json={"from": {"table": SRC}}).json()
    assert before["counts"]["emptySrc"] == 10 and before["counts"]["same"] == 1 and before["counts"]["fill"] == 0   # 빈 양식끼리 — 넣을 것이 없다
    _seed(client, d)
    r = client.post(_url(d, DST, "/plan"), json={"from": {"table": SRC}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["counts"]["fill"] == 10 and p["counts"]["same"] == 1 and p["counts"]["unmatched"] == 0 and p["rev"] == s.rev and p["held"] == []
    assert p["types"]["same"] and "forms" not in p and p["rules"] is None and p["table"] == DST and p["from"]["table"] == SRC and p["from"]["counts"]["items"] == 11
    by = {x["to"]: x for x in p["pairs"]}
    assert (by[NAME_TO]["status"], by[NAME_TO]["text"], by[NAME_TO]["was"], by[NAME_TO]["from"], by[NAME_TO]["by"]) == ("fill", "홍길동", "", "c6604", "key")
    assert by[ADDR_TO]["status"] == "same" and all(len(x["sig"]) == 12 for x in p["pairs"])
    rev, undo = s.rev, len(s.undo)
    body = {"from": {"table": SRC}, "cells": [NAME_TO, NATION_TO, ADDR_TO, "c1"], "rev": rev, "sigs": {NAME_TO: by[NAME_TO]["sig"], NATION_TO: "0" * 12, ADDR_TO: by[ADDR_TO]["sig"]}}
    assert client.post(_url(d, DST, "/apply"), json={**body, "rev": rev - 1}).status_code == 409        # 계획을 본 뒤 문서가 바뀜
    a = client.post(_url(d, DST, "/apply"), json=body)
    assert a.status_code == 200, a.text
    m = a.json()["mapped"]
    assert m["table"] == DST and m["from"] == {"table": SRC} and m["done"] == [NAME_TO] and m["rules"] is None
    why = {x["cell"]: x["why"] for x in m["skipped"]}
    assert set(why) == {NATION_TO, ADDR_TO, "c1"} and "달라짐" in why[NATION_TO] and "같은 글" in why[ADDR_TO] and "짝이 없습니다" in why["c1"]   # sig 가 다른 칸 · 넣을 것이 없는 칸은 건너뜀
    assert _text(d, DST, NAME_TO) == "홍길동" and _text(d, DST, NATION_TO) == "" and (s.rev, len(s.undo)) == (rev + 1, undo + 1)   # 한 번의 편집
    assert a.json()["rev"] == s.rev and a.json()["tops"]["blocks"]
    ev = [e for e in works.events(d) if e["kind"] == "tableKv"]                                           # 작업 기록에 한 줄(기록 종류 tableKv)
    assert len(ev) == 1 and (ev[0]["table"], ev[0]["src"], ev[0]["cells"], ev[0]["skipped"], ev[0]["rev"]) == (DST, SRC, 1, 3, s.rev)
    again =client.post(_url(d, DST, "/plan"), json={"from": {"table": SRC}}).json()
    assert again["counts"]["fill"] == 9 and again["counts"]["same"] == 2                                  # 넣은 칸은 「같음」
    assert client.post(_url(d, DST, "/apply"), json={**body, "rev": s.rev, "cells": [NAME_TO]}).status_code == 409   # 넣을 칸이 하나도 안 남음
    assert client.post(f"/api/docs/{d}/undo").status_code == 200 and _text(d, DST, NAME_TO) == ""          # 실행 취소 1번에 돌아온다


def test_api_bad_requests(client):
    d = _open(client)
    s = server.DOCS[d]
    ok = {"from": {"table": SRC}, "cells": [NAME_TO], "rev": s.rev, "sigs": {NAME_TO: "x"}}
    for bad in ({}, {"from": "t1"}, {"from": {"table": ""}}, {"from": {"table": SRC, "doc": 3}}, {"from": {"table": DST}}):   # 같은 문서의 같은 표는 원본이 아니다
        assert client.post(_url(d, DST, "/plan"), json=bad).status_code == 400, bad
    for patch in ({"cells": []}, {"cells": [NAME_TO, NAME_TO]}, {"cells": "c1"}, {"rev": None}, {"rev": "3"}, {"sigs": None}, {"sigs": {NAME_TO: 1}}, {"from": {"table": DST}}):
        assert client.post(_url(d, DST, "/apply"), json={**ok, **patch}).status_code == 400, patch
    assert client.post(_url(d, DST, "/plan"), json={"from": {"table": "t99999"}}).status_code == 404
    assert client.post(_url(d, "t99999", "/plan"), json={"from": {"table": SRC}}).status_code == 404
    assert client.post(_url(d, "t99999", "/apply"), json=ok).status_code == 404
    assert s.rev == 0 and not s.undo


def test_api_source_table_in_another_open_document(client):
    a, b = _open(client), _open(client, new=True)
    assert a != b
    _seed(client, b)
    sa, sb = server.DOCS[a], server.DOCS[b]
    for tail, body in (("/plan", {"from": {"table": SRC, "doc": "nope"}}), ("/apply", {"from": {"table": SRC, "doc": "nope"}, "cells": [NAME_TO], "rev": 0, "sigs": {}})):
        r = client.post(_url(a, DST, tail), json=body)
        assert r.status_code == 400 and "열려 있지 않습니다" in r.json()["detail"]                         # 다른 문서가 서버에 안 열려 있음
    p = client.post(_url(a, DST, "/plan"), json={"from": {"table": SRC, "doc": b}})
    assert p.status_code == 200, p.text
    p = p.json()
    assert p["counts"]["fill"] == 10 and p["from"] == {**p["from"], "table": SRC, "doc": b} and p["rev"] == sa.rev == 0
    by = {x["to"]: x for x in p["pairs"]}
    rb = sb.rev
    r = client.post(_url(a, DST, "/apply"), json={"from": {"table": SRC, "doc": b}, "cells": [NAME_TO, NATION_TO], "rev": p["rev"], "sigs": {k: by[k]["sig"] for k in (NAME_TO, NATION_TO)}})
    assert r.status_code == 200, r.text
    assert r.json()["mapped"]["done"] == [NAME_TO, NATION_TO] and r.json()["mapped"]["from"] == {"table": SRC, "doc": b}
    assert _text(a, DST, NAME_TO) == "홍길동" and _text(a, DST, NATION_TO) == "대한민국" and sa.rev == 1 and sb.rev == rb   # 원본 문서는 안 바뀐다
    same = client.post(_url(a, SRC, "/plan"), json={"from": {"table": SRC, "doc": b}})                   # 다른 문서의 같은 id 표는 원본이 될 수 있다
    assert same.status_code == 200 and same.json()["counts"]["fill"] == 10
    assert _free(sa) and _free(sb)


def test_api_held_header_designation_blocks_apply(client):
    d = _open(client)
    _seed(client, d)
    s = server.DOCS[d]
    table_heads.put(s.id, DST, [NAME_TO], "field", stamps={NAME_TO: {"at": [9, 9, 1, 1], "text": ""}})   # 도장의 자리가 지금 칸과 다름 → 보류
    v = client.get(_url(d, DST)).json()
    assert [(h["cell"], h["why"]) for h in v["held"]] == [(NAME_TO, "자리가 바뀜")]
    p = client.post(_url(d, DST, "/plan"), json={"from": {"table": SRC}}).json()
    assert len(p["held"]) == 1 and p["counts"]["fill"] == 10                                              # 읽는 끝점은 유효한 지정만 쓰고 held 를 싣는다
    by = {x["to"]: x for x in p["pairs"]}
    r = client.post(_url(d, DST, "/apply"), json={"from": {"table": SRC}, "cells": [NAME_TO], "rev": p["rev"], "sigs": {NAME_TO: by[NAME_TO]["sig"]}})
    assert r.status_code == 409 and "헤더 지정 1칸" in r.json()["detail"] and _text(d, DST, NAME_TO) == ""
    table_heads.put(s.id, DST, [NAME_TO], None)                                                           # 지정을 풀면 된다
    r = client.post(_url(d, DST, "/apply"), json={"from": {"table": SRC}, "cells": [NAME_TO], "rev": p["rev"], "sigs": {NAME_TO: by[NAME_TO]["sig"]}})
    assert r.status_code == 200 and _text(d, DST, NAME_TO) == "홍길동"


def test_api_docx_is_refused(client):
    r = client.post("/api/docs", files={"file": (DOCX.name, DOCX.read_bytes())})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    assert client.get(_url(d, "t1")).status_code == 400
    assert client.post(_url(d, "t1", "/plan"), json={"from": {"table": "t2"}}).status_code == 400
    assert client.post(_url(d, "t1", "/apply"), json={"from": {"table": "t2"}, "cells": ["c1"], "rev": 0, "sigs": {}}).status_code == 400


def test_api_mapping_rules_are_saved_and_used_by_plan_and_apply(client):
    d = _open(client)
    _seed(client, d)
    s = server.DOCS[d]
    fa, fb = client.get(_url(d, SRC)).json()["type"], client.get(_url(d, OTHER)).json()["type"]
    bare = client.post(_url(d, OTHER, "/plan"), json={"from": {"table": SRC}}).json()
    assert bare["pairs"] == [] and bare["rules"] is None and bare["types"] == {"from": fa, "to": fb, "same": False} and bare["counts"]["unmatchedSrc"] == 11   # 타입이 다르고 그 짝의 규칙도 없다
    assert client.get("/api/table-maps").json() == {"maps": []} and client.get("/api/table-maps/find", params={"from": fa, "to": fb}).json() is None
    body = {"from": {"type": fa, "label": "연구책임자 표"}, "to": {"type": fb, "label": "책임자 · 실무 담당자 표"},
            "alias": [{"from": "직장", "to": "책임자"}], "pairs": [{"from": "개인›국문|", "to": "책임자›성명›국문|", "fromLabel": "개인 › 국문", "toLabel": "책임자 › 성명 › 국문"}]}
    r = client.put("/api/table-maps", json=body)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["version"] == 1 and m["name"] == "연구책임자 표 → 책임자 · 실무 담당자 표" and m["alias"] == body["alias"] and m["pairs"] == body["pairs"]
    assert client.get("/api/table-maps/find", params={"from": fa, "to": fb}).json()["id"] == m["id"]
    assert client.get("/api/table-maps/find", params={"from": fb, "to": fa}).json() is None                # 방향이 있다
    assert [x["id"] for x in client.get("/api/table-maps").json()["maps"]] == [m["id"]]
    p = client.post(_url(d, OTHER, "/plan"), json={"from": {"table": SRC}}).json()
    assert p["rules"] == {"id": m["id"], "name": m["name"], "alias": 1, "pairs": 1, "ops": 0, "used": 7} and p["counts"]["fill"] == 7 and p["counts"]["byRule"] == 7
    by = {x["label"]: x for x in p["pairs"]}
    assert (by["책임자 › 기관명"]["by"], by["책임자 › 기관명"]["text"], by["책임자 › 기관명"]["fromLabel"]) == ("alias", "한국선급", "직장 › 기관명")
    assert (by["책임자 › 성명 › 국문"]["by"], by["책임자 › 성명 › 국문"]["text"]) == ("pair", "홍길동") and by["책임자 › 직위 › 전자우편"]["text"] == "hong@example.org"
    off = client.post(_url(d, OTHER, "/plan"), json={"from": {"table": SRC}, "rules": False}).json()
    assert off["pairs"] == [] and off["rules"] is None                                                    # rules: false 면 규칙 없이
    to = [by["책임자 › 기관명"]["to"], by["책임자 › 성명 › 국문"]["to"]]
    req = {"from": {"table": SRC}, "cells": to, "rev": p["rev"], "sigs": {x["to"]: x["sig"] for x in p["pairs"]}}
    assert client.post(_url(d, OTHER, "/apply"), json={**req, "rules": False}).status_code == 409         # 규칙 없이는 짝이 없다 — 넣을 칸 없음
    a = client.post(_url(d, OTHER, "/apply"), json=req)
    assert a.status_code == 200, a.text
    assert a.json()["mapped"]["done"] == to and a.json()["mapped"]["rules"] == m["id"] and _text(d, OTHER, to[0]) == "한국선급" and _text(d, OTHER, to[1]) == "홍길동"
    # 고치기 — 기대 version 이 맞을 때만
    assert client.put("/api/table-maps", json=body).status_code == 409                                    # 그 짝의 묶음이 이미 있다(version 을 안 줌)
    assert client.put("/api/table-maps", json={**body, "id": m["id"], "version": 7}).status_code == 409
    r2 = client.put("/api/table-maps", json={**body, "id": m["id"], "version": 1, "name": "인적사항", "pairs": []})
    assert r2.status_code == 200 and r2.json()["version"] == 2 and r2.json()["name"] == "인적사항" and r2.json()["pairs"] == []
    assert client.put("/api/table-maps", json={**body, "to": {"form": fb, "label": "x"}}).status_code == 400    # 옛 이름(form)은 꼴이 틀린 것
    assert client.put("/api/table-maps", json={**body, "id": "m0000000000", "version": 1}).status_code == 404
    assert client.put("/api/table-maps", json={"alias": []}).status_code == 400
    after = client.post(_url(d, OTHER, "/plan"), json={"from": {"table": SRC}}).json()
    assert after["rules"]["used"] == 6 and after["rules"]["pairs"] == 0 and after["counts"]["same"] == 1 and after["counts"]["fill"] == 5   # 넣은 「기관명」 은 같음 · 칸 짝은 지움
    assert client.delete(f"/api/table-maps/{m['id']}").json() == {"deleted": m["id"]} and client.delete(f"/api/table-maps/{m['id']}").status_code == 404
    assert client.post(_url(d, OTHER, "/plan"), json={"from": {"table": SRC}}).json()["pairs"] == [] and s.rev == 2


def test_api_rules_between_tables_of_the_same_type(client):
    d = _open(client)
    _seed(client, d)
    t = client.get(_url(d, SRC)).json()["type"]
    bare = client.post(_url(d, DST, "/plan"), json={"from": {"table": SRC}}).json()
    assert bare["types"] == {"from": t, "to": t, "same": True} and bare["rules"] is None and bare["counts"]["fill"] == 10
    # 같은 타입 → 같은 타입도 한 짝이다: 두 칸을 바꿔 읽는 칸 짝(「국적」 ↔ 「국가연구자번호」)
    swap = [{"from": "개인›국문›국적|", "to": "개인›영문›국가연구자번호|"}, {"from": "개인›영문›국가연구자번호|", "to": "개인›국문›국적|"}]
    r = client.put("/api/table-maps", json={"name": "인적사항 — 두 칸 바꿔", "from": {"type": t, "label": "연구책임자 표"}, "to": {"type": t, "label": "연구책임자 표"}, "alias": [], "pairs": swap})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["from"]["type"] == m["to"]["type"] == t and client.get("/api/table-maps/find", params={"from": t, "to": t}).json()["id"] == m["id"]
    p = client.post(_url(d, DST, "/plan"), json={"from": {"table": SRC}}).json()                          # 같은 타입이어도 그 짝의 묶음이 있으면 쓴다
    assert p["types"]["same"] and p["rules"] == {"id": m["id"], "name": "인적사항 — 두 칸 바꿔", "alias": 0, "pairs": 2, "ops": 0, "used": 2} and p["counts"]["fill"] == 10
    by = {x["label"]: x for x in p["pairs"]}
    assert (by["개인 › 국문 › 국적"]["by"], by["개인 › 국문 › 국적"]["text"]) == ("pair", "12345678") and by["개인 › 영문 › 국가연구자번호"]["text"] == "대한민국" and by["개인 › 국문"]["by"] == "key"
    off = client.post(_url(d, DST, "/plan"), json={"from": {"table": SRC}, "rules": False}).json()
    assert off["rules"] is None and {x["label"]: x["text"] for x in off["pairs"]}["개인 › 국문 › 국적"] == "대한민국"   # rules: false 면 규칙 없이 — 꼭 같은 키끼리
    a = client.post(_url(d, DST, "/apply"), json={"from": {"table": SRC}, "cells": [NATION_TO], "rev": p["rev"], "sigs": {NATION_TO: by["개인 › 국문 › 국적"]["sig"]}})
    assert a.status_code == 200 and a.json()["mapped"]["rules"] == m["id"] and _text(d, DST, NATION_TO) == "12345678"
    assert client.delete(f"/api/table-maps/{m['id']}").status_code == 200
    again = client.post(_url(d, DST, "/plan"), json={"from": {"table": SRC}}).json()
    assert again["rules"] is None and {x["to"]: x["status"] for x in again["pairs"]}[NATION_TO] == "clash"   # 규칙을 지우면 꼭 같은 키끼리 — 이미 쓴 글은 겹침(안 덮는다)


# ---- 끝점 — 구분 기준으로 묶어 넣기 ---------------------------------------------------------------------------------------
LEAD, PART = "주관연구개발기관", "공동연구개발기관"   # 받을 표(OTHER)의 기관 값 머리 — 키 조각도 같은 글
VALS_B = {"c6937": "김공동", "c6945": "Kim Gongdong", "c6955": "한국해양대학교", "c6959": "051-111-1111", "c6963": "기계공학부", "c6967": "010-1111-1111", "c6971": "교수", "c6975": "kim@example.org"}


def _grouped_doc(c):
    """견본 문서를 묶어 넣을 꼴로 — 받을 표(OTHER 「책임자 · 실무 담당자」)의 묶음 머리를 기관 값 머리(「주관연구개발기관」 · 「공동연구개발기관」)로 고치고,
    원본 표 둘(SRC = 주관 책임자의 표 · DST = 공동 책임자의 표 — 표 앞 문단에 그 기관 말이 있다)의 묶음 머리(「개인」 · 「직장」)를 비워 키가 「기관명|」 · 「부서|」 … 가 되게 한 뒤 값을 채운다."""
    d = _open(c)
    s = server.DOCS[d]
    for tid in (SRC, DST):
        by = {x["text"]: x for x in s.doc.table_block(tid)["cells"]}
        for head in ("개인", "직장"):
            pid = next(b["id"] for b in by[head]["blocks"] if b["type"] == "paragraph")
            assert c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": ""}).status_code == 200
    by = {x["text"]: x["id"] for x in s.doc.table_block(OTHER)["cells"]}
    r = c.post(f"/api/docs/{d}/tables/{OTHER}/fill/apply", json={"fills": [{"cell": by["책임자"], "text": LEAD}, {"cell": by["실무\n담당자"], "text": PART}]})
    assert r.status_code == 200, r.text
    _seed(c, d)
    r = c.post(f"/api/docs/{d}/tables/{DST}/fill/apply", json={"fills": [{"cell": k, "text": v} for k, v in VALS_B.items()]})
    assert r.status_code == 200, r.text
    return d


def test_api_grouped_plan_reads_each_source_value_and_apply_fills_under_it(client):
    d = _grouped_doc(client)
    s = server.DOCS[d]
    v = client.get(_url(d, OTHER)).json()
    assert [(b["basis"], b["on"], b["level"], [(x["part"], x["cells"]) for x in b["values"]]) for b in v["bases"]] == [("org", "row", 0, [(LEAD, 9), (PART, 8)])]
    assert client.get(_url(d, SRC)).json()["bases"] == []                                                # 원본 표에는 그 머리글이 없다
    r = client.post(_url(d, OTHER, "/plan"), json={"from": [{"table": SRC}, {"table": DST}], "group": {"basis": "org"}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["group"]["basis"], p["group"]["on"], p["group"]["level"]) == ("org", "row", 0) and p["rev"] == s.rev and "types" not in p
    assert [{k: x[k] for k in ("part", "label", "cells")} for x in p["bases"][0]["values"]] == v["bases"][0]["values"]
    assert [(x["part"], x["pairs"], x["fill"]) for x in p["bases"][0]["values"]] == [(LEAD, 6, 6), (PART, 8, 8)]   # 값마다 짝 수 · 넣을 수 있는 수(구분 기준의 값 고르기)
    assert {x["div"].get("org") for x in p["pairs"] if x["from"]["table"] == SRC} == {LEAD} and all(x["div"] == {"org": x["value"]} for x in p["pairs"])   # 짝마다 그 받을 칸이 놓인 값
    assert [(x["table"], x["value"], x["valueLabel"], x["by"], x["counts"]["fill"]) for x in p["sources"]] == [(SRC, LEAD, LEAD, "text", 6), (DST, PART, PART, "text", 8)]   # 표 앞 문단의 글로 읽었다
    assert p["counts"]["fill"] == 14 and [(g["value"], g["tables"], g["counts"]["fill"]) for g in p["groups"]] == [(LEAD, [SRC], 6), (PART, [DST], 8)]
    by = {x["label"]: x for x in p["pairs"]}
    a, b = by[f"{LEAD} › 기관명"], by[f"{PART} › 기관명"]
    assert (a["text"], a["from"], a["group"], a["value"], a["status"]) == ("한국선급", {"table": SRC, "cell": "c6622"}, LEAD, LEAD, "fill")
    assert (b["text"], b["from"], b["group"]) == ("한국해양대학교", {"table": DST, "cell": "c6955"}, PART) and by[f"{PART} › 국문"]["text"] == "김공동" and all(len(x["sig"]) == 12 for x in p["pairs"])
    assert f"{LEAD} › 성명 › 국문" not in by                                                             # 원본의 키 「국문|」 은 그 값 아래 「성명›국문|」 과 꼭 같지 않다 — 안 잇는다
    rev, undo = s.rev, len(s.undo)
    req = {"from": [{"table": SRC, "value": LEAD}, {"table": DST, "value": PART}], "group": {"basis": "org"}, "cells": [a["to"], b["to"]], "rev": rev, "sigs": {x["to"]: x["sig"] for x in p["pairs"]}}
    swapped = {**req, "from": [{"table": SRC, "value": PART}, {"table": DST, "value": LEAD}]}
    sw = client.post(_url(d, OTHER, "/plan"), json={k: swapped[k] for k in ("from", "group")}).json()   # 사람이 준 값이 권한 값보다 먼저
    assert [(x["value"], x["by"]) for x in sw["sources"]] == [(PART, "user"), (LEAD, "user")] and {x["label"]: x["text"] for x in sw["pairs"]}[f"{LEAD} › 기관명"] == "한국해양대학교"
    assert client.post(_url(d, OTHER, "/apply"), json=swapped).status_code == 409                        # 원본이 바뀌면 sig 가 달라진다 — 넣을 칸 없음
    r = client.post(_url(d, OTHER, "/apply"), json=req)
    assert r.status_code == 200, r.text
    m = r.json()["mapped"]
    assert m["done"] == [a["to"], b["to"]] and m["from"] == [{"table": SRC, "value": LEAD}, {"table": DST, "value": PART}] and m["group"] == {"basis": "org", "on": "row", "level": 0} and m["rules"] == []
    assert _text(d, OTHER, a["to"]) == "한국선급" and _text(d, OTHER, b["to"]) == "한국해양대학교" and (s.rev, len(s.undo)) == (rev + 1, undo + 1)   # 한 번의 편집
    ev = [e for e in works.events(d) if e["kind"] == "tableKv"]
    assert len(ev) == 1 and ev[0]["src"] == [SRC, DST] and ev[0]["group"] == "org" and ev[0]["cells"] == 2
    again = client.post(_url(d, OTHER, "/plan"), json={k: req[k] for k in ("from", "group")}).json()
    assert again["counts"]["fill"] == 12 and again["counts"]["same"] == 2
    assert client.post(f"/api/docs/{d}/undo").status_code == 200 and _text(d, OTHER, a["to"]) == "" and _text(d, OTHER, b["to"]) == ""   # 실행 취소 1번에 돌아온다


def test_api_grouped_requests_and_plain_lists(client):
    d = _grouped_doc(client)
    s = server.DOCS[d]
    rev = s.rev
    url = _url(d, OTHER, "/plan")
    for bad in ({"from": [{"table": SRC}], "group": {"basis": "year"}},                                  # 받을 표에 차년도 머리글이 없다
                {"from": [{"table": SRC}], "group": {"basis": "x"}}, {"from": [{"table": SRC}], "group": "org"}, {"from": [{"table": SRC}], "group": {"basis": "org", "level": "0"}},
                {"from": [{"table": SRC, "value": "없는 기관"}], "group": {"basis": "org"}},               # 고른 값의 머리글이 없다
                {"from": [{"table": SRC, "value": 3}], "group": {"basis": "org"}}, {"from": []}, {"from": [{"table": SRC}, {"table": SRC}]}, {"from": [{"table": OTHER}]},
                {"from": [{"table": f"t{i}"} for i in range(13)]}):
        assert client.post(url, json=bad).status_code == 400, bad
    assert client.post(url, json={"from": [{"table": "t99999"}], "group": {"basis": "org"}}).status_code == 404
    one = client.post(url, json={"from": {"table": SRC}, "group": {"basis": "org", "on": "row", "level": 0}}).json()   # 원본 하나도 묶어 넣을 수 있다
    assert [(x["table"], x["value"], x["by"]) for x in one["sources"]] == [(SRC, LEAD, "text")] and one["counts"]["fill"] == 6 and one["pairs"][0]["from"]["table"] == SRC
    flat = client.post(url, json={"from": [{"table": SRC, "value": LEAD}, {"table": DST}]}).json()          # 목록이지만 기준 없이 — 원본마다 키 그대로(값은 안 쓴다)
    assert flat["group"] is None and [(x["value"], x["by"]) for x in flat["sources"]] == [(None, None), (None, None)] and flat["counts"]["unmatchedSrc"] == 20
    assert [(x["label"], x["from"]["table"], x["status"]) for x in flat["pairs"]] == [("주소", SRC, "clash"), ("주소", DST, "clash")] and all("원본 둘이 같은 칸" in x["why"] for x in flat["pairs"])   # 두 원본의 「주소」 가 같은 칸에
    both = client.post(_url(d, SRC, "/plan"), json={"from": [{"table": DST}, {"table": OTHER}]}).json()     # 기준 없이 두 원본 — 원본마다 키 그대로: 한 원본만 닿는 칸은 그대로, 둘이 닿는 칸(「주소」)만 겹침
    assert both["group"] is None and len(both["pairs"]) == 12 and [g["table"] for g in both["groups"]] == [DST, OTHER]
    assert [(x["from"]["table"], x["status"]) for x in both["pairs"] if x["label"] == "주소"] == [(DST, "clash"), (OTHER, "clash")]
    assert {x["from"]["table"] for x in both["pairs"] if x["label"] != "주소"} == {DST} and all(x["status"] in ("same", "clash", "emptySrc") for x in both["pairs"])   # SRC 는 이미 채운 표 — 넣을 칸 없음
    legacy = client.post(url, json={"from": {"table": SRC}}).json()                                        # group 이 없고 from 이 표 하나면 전과 같은 1대1 꼴
    assert [(x["label"], x["from"], x["status"]) for x in legacy["pairs"]] == [("주소", "c6646", "same")] and legacy["from"]["table"] == SRC and "sources" not in legacy and "group" not in legacy and legacy["types"]["same"] is False and legacy["bases"][0]["basis"] == "org"
    assert s.rev == rev and _free(s)


def test_api_grouped_value_hints_zone_then_owner_then_text(client, monkeypatch):
    from app import heading_runs, table_kinds_api
    d = _grouped_doc(client)
    s = server.DOCS[d]
    body = {"from": [{"table": SRC}, {"table": DST}], "group": {"basis": "org"}}
    seen = []

    def zone_reader(sess):   # 편집 구역 읽기 함수는 세션 잠금 밖에서 받는다(zones_api.read 가 그 잠금을 제가 잡는다)
        free = sess.lock.acquire(timeout=10)   # 이 요청이 그 잠금을 쥔 채 부르면(다시 못 들어가는 잠금) 끝내 못 잡는다 — 뒤에서 저장하는 일이 잠깐 쥔 것은 기다리면 풀린다
        if free:
            sess.lock.release()
        seen.append(not free)
        return lambda i: {"org": "k1", "orgKind": "org", "orgName": PART, "year": None, "stage": None} if i == SRC else None
    monkeypatch.setattr(table_kinds_api, "_zone_of", zone_reader)
    monkeypatch.setattr(heading_runs, "tables", lambda sess: {"meta": {"rev": sess.rev}, "tables": [{"id": DST, "owner": {"division": {"text": f"[{LEAD}]"}}}]})
    p = client.post(_url(d, OTHER, "/plan"), json=body).json()
    assert [(x["table"], x["value"], x["by"]) for x in p["sources"]] == [(SRC, PART, "zone"), (DST, LEAD, "owner")] and seen == [False]   # 편집 구역 → 표의 소속 → 표 앞 글
    monkeypatch.setattr(heading_runs, "tables", lambda sess: {"meta": {"rev": sess.rev - 1}, "tables": [{"id": DST, "owner": {"division": {"text": f"[{LEAD}]"}}}]})
    p = client.post(_url(d, OTHER, "/plan"), json=body).json()
    assert [(x["value"], x["by"]) for x in p["sources"]] == [(PART, "zone"), (PART, "text")]              # 낡은 3단계 결과의 소속은 건너뛴다
    assert all(x["status"] == "clash" and "원본 둘이 같은 칸" in x["why"] for x in p["pairs"]) and len(p["pairs"]) == 16   # 두 원본이 같은 기관 — 어느 것도 넣지 않는다
    seen.clear()
    given = {"from": [{"table": SRC, "value": LEAD}, {"table": DST, "value": PART}], "group": {"basis": "org"}}
    assert [x["by"] for x in client.post(_url(d, OTHER, "/plan"), json=given).json()["sources"]] == ["user", "user"] and seen == []   # 사람이 값을 다 줬으면 편집 구역을 읽지 않는다
    monkeypatch.setattr(table_kinds_api, "_zone_of", lambda sess: None)                                    # 프로젝트 구성이 없는 문서 — 구역 없이
    monkeypatch.setattr(heading_runs, "tables", lambda sess: None)
    assert [(x["value"], x["by"]) for x in client.post(_url(d, OTHER, "/plan"), json=body).json()["sources"]] == [(LEAD, "text"), (PART, "text")]


# ---- 끝점 — 더해서 넣기 · 나눠 넣기 ---------------------------------------------------------------------------------------
CTE_A, CTE_B, CTE_C = "t11904", "t12105", "t12304"   # 「CTE1 · CTE2 · CTE3」 표 — 머리글이 같은 표 셋(같은 타입 · 같은 키)


def _sum_doc(c):
    """견본 문서의 같은 타입 표 셋 가운데 둘(원본)에 「개발 연차」 칸의 값을 넣는다 → (문서 id, 그 칸의 키 넷, 표마다 {키: 칸 id})."""
    d = _open(c)
    kv = {t: c.get(_url(d, t)).json() for t in (CTE_A, CTE_B, CTE_C)}
    keys = [i["key"] for i in kv[CTE_A]["items"] if i["key"].endswith("|개발연차") and i["empty"] and i["key"] not in kv[CTE_A]["dups"]][:4]
    cell = {t: {i["key"]: i["cell"] for i in v["items"]} for t, v in kv.items()}
    fills = {CTE_A: [("500", keys[0]), ("1,000", keys[1]), ("시험 평가를 수행한다.", keys[2]), ("3", keys[3])], CTE_B: [("700", keys[0]), ("7", keys[2]), ("4", keys[3])], CTE_C: [("7", keys[3])]}
    for t, rows in fills.items():
        r = c.post(f"/api/docs/{d}/tables/{t}/fill/apply", json={"fills": [{"cell": cell[t][k], "text": v} for v, k in rows]})
        assert r.status_code == 200, r.text
    return d, keys, cell


def test_api_sum_plan_and_apply(client):
    d, keys, cell = _sum_doc(client)
    s = server.DOCS[d]
    body = {"from": [{"table": CTE_A}, {"table": CTE_B}], "mode": "sum"}
    r = client.post(_url(d, CTE_C, "/plan"), json=body)
    assert r.status_code == 200, r.text
    p = r.json()
    by = {x["key"]: x for x in p["pairs"]}
    assert p["mode"] == "sum" and p["group"] is None and p["rev"] == s.rev and [x["table"] for x in p["sources"]] == [CTE_A, CTE_B] and all(x["same"] for x in p["sources"])
    assert (by[keys[0]]["status"], by[keys[0]]["text"], by[keys[0]]["sum"], [q["text"] for q in by[keys[0]]["parts"]]) == ("fill", "1,200", 1200, ["500", "700"])
    assert (by[keys[1]]["status"], by[keys[1]]["text"], by[keys[1]]["missing"], by[keys[1]]["check"]) == ("fill", "1,000", 1, True)
    assert by[keys[2]]["status"] == "nonnum" and by[keys[3]]["status"] == "same" and p["counts"]["fill"] == 2 and p["counts"]["check"] == 1 and p["counts"]["nonnum"] == 1
    to = [by[k]["to"] for k in keys]
    assert to == [cell[CTE_C][k] for k in keys] and all(len(x["sig"]) == 12 for x in p["pairs"])
    for bad in ({**body, "group": {"basis": "stage"}}, {**body, "mode": "avg"}, {"from": {"table": CTE_A}, "mode": "sum", "group": {"basis": "stage"}}):   # mode 와 group 을 같이 · 모르는 mode
        assert client.post(_url(d, CTE_C, "/plan"), json=bad).status_code == 400, bad
    rev, undo = s.rev, len(s.undo)
    req = {**body, "cells": to, "rev": rev, "sigs": {x["to"]: x["sig"] for x in p["pairs"]}}
    assert client.post(_url(d, CTE_C, "/apply"), json={**req, "group": {"basis": "stage"}}).status_code == 400
    assert client.post(_url(d, CTE_C, "/apply"), json={**req, "from": [{"table": CTE_A}]}).status_code == 409    # 원본이 바뀌면 합 · 도장이 달라진다 — 넣을 칸 없음(fill 둘 다 달라짐)
    a = client.post(_url(d, CTE_C, "/apply"), json=req)
    assert a.status_code == 200, a.text
    m = a.json()["mapped"]
    assert m["done"] == to[:2] and m["mode"] == "sum" and m["from"] == [{"table": CTE_A}, {"table": CTE_B}] and {x["cell"] for x in m["skipped"]} == set(to[2:])
    assert _text(d, CTE_C, to[0]) == "1,200" and _text(d, CTE_C, to[1]) == "1,000" and _text(d, CTE_C, to[2]) == "" and (s.rev, len(s.undo)) == (rev + 1, undo + 1)
    ev = [e for e in works.events(d) if e["kind"] == "tableKv"]
    assert len(ev) == 1 and ev[0]["mode"] == "sum" and ev[0]["src"] == [CTE_A, CTE_B] and ev[0]["cells"] == 2
    again = {x["key"]: x["status"] for x in client.post(_url(d, CTE_C, "/plan"), json=body).json()["pairs"]}
    assert again[keys[0]] == "same" and again[keys[1]] == "same"                                           # 넣은 칸은 「같음」
    assert client.post(f"/api/docs/{d}/undo").status_code == 200 and _text(d, CTE_C, to[0]) == "" and _text(d, CTE_C, to[1]) == ""   # 실행 취소 1번에 돌아온다
    plain = client.post(_url(d, CTE_C, "/plan"), json={"from": [{"table": CTE_A}, {"table": CTE_B}]}).json()   # mode 가 없으면 더하지 않는다(기준 없이 — 두 원본이 같은 칸이면 겹침)
    assert "mode" not in plain and {x["status"] for x in plain["pairs"] if x["key"] == keys[0]} == {"clash"}


VALS_O = {"c7704": "한국선급", "c7708": "051-000-0000", "c7712": "연구본부", "c7716": "010-0000-0000", "c7720": "책임연구원", "c7724": "hong@example.org",   # 받는 쪽이 될 표들의 키와 맞는 칸(주관 6 · 공동 8)
          "c7731": "김공동", "c7735": "Kim Gongdong", "c7739": "한국해양대학교", "c7743": "051-111-1111", "c7747": "기계공학부", "c7751": "010-1111-1111", "c7755": "교수", "c7759": "kim@example.org"}


def _split_doc(c):
    """견본 문서를 나눠 넣을 꼴로 — 원본 표(OTHER)의 묶음 머리를 기관 값 머리로 고치고 값을 채운다 · 받을 표 둘(SRC = 주관 책임자의 표 · DST = 공동 책임자의 표)의 묶음 머리를 비운다(값 칸은 빈 채)."""
    d = _open(c)
    s = server.DOCS[d]
    for tid in (SRC, DST):
        by = {x["text"]: x for x in s.doc.table_block(tid)["cells"]}
        for head in ("개인", "직장"):
            pid = next(b["id"] for b in by[head]["blocks"] if b["type"] == "paragraph")
            assert c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": ""}).status_code == 200
    by = {x["text"]: x["id"] for x in s.doc.table_block(OTHER)["cells"]}
    fills = [{"cell": by["책임자"], "text": LEAD}, {"cell": by["실무\n담당자"], "text": PART}, *({"cell": k, "text": v} for k, v in VALS_O.items())]
    assert c.post(f"/api/docs/{d}/tables/{OTHER}/fill/apply", json={"fills": fills}).status_code == 200
    return d


def test_api_split_plan_and_apply_two_tables_in_one_edit(client):
    d = _split_doc(client)
    s = server.DOCS[d]
    url = _url(d, OTHER, "/split/plan")
    body = {"to": [{"table": SRC}, {"table": DST}], "group": {"basis": "org"}}
    r = client.post(url, json=body)
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["table"], p["group"]["basis"], p["group"]["on"], p["rev"], p["held"]) == (OTHER, "org", "row", s.rev, [])
    assert [(t["table"], t["value"], t["by"], t["counts"]["fill"]) for t in p["targets"]] == [(SRC, LEAD, "text", 6), (DST, PART, "text", 8)]   # 받을 표가 어느 기관의 것인지 — 표 앞 문단의 글로
    assert p["counts"]["fill"] == 14 and [(g["table"], g["label"], g["counts"]["fill"]) for g in p["groups"]] == [(SRC, LEAD, 6), (DST, PART, 8)]
    by = {(x["to"]["table"], x["label"]): x for x in p["pairs"]}
    a, b = by[(SRC, "기관명")], by[(DST, "국문")]
    assert (a["text"], a["from"], a["to"], a["group"], a["status"], a["ref"]) == ("한국선급", "c7704", {"table": SRC, "cell": "c6622"}, LEAD, "fill", "C3")
    assert (b["text"], b["from"], b["to"]) == ("김공동", "c7731", {"table": DST, "cell": "c6937"}) and (SRC, "국문") not in by   # 원본의 「성명›국문|」 은 받을 표의 「국문|」 과 꼭 같지 않다
    for bad in ({"to": [{"table": SRC}]}, {"to": [], "group": {"basis": "org"}}, {"to": [{"table": OTHER}], "group": {"basis": "org"}}, {"to": [{"table": SRC}, {"table": SRC}], "group": {"basis": "org"}},
                {"to": [{"table": SRC}], "group": {"basis": "year"}}, {"to": [{"table": SRC, "value": "없는 기관"}], "group": {"basis": "org"}}, {"to": {"table": SRC}, "group": {"basis": "org"}}):
        assert client.post(url, json=bad).status_code == 400, bad
    assert client.post(url, json={"to": [{"table": "t99999"}], "group": {"basis": "org"}}).status_code == 404
    swapped = client.post(url, json={"to": [{"table": SRC, "value": PART}, {"table": DST, "value": LEAD}], "group": {"basis": "org"}}).json()   # 사람이 준 값이 먼저
    assert [(t["value"], t["by"]) for t in swapped["targets"]] == [(PART, "user"), (LEAD, "user")] and {(x["to"]["table"], x["label"]): x["text"] for x in swapped["pairs"]}[(SRC, "기관명")] == "한국해양대학교"
    rev, undo = s.rev, len(s.undo)
    req = {"to": [{"table": SRC, "value": LEAD}, {"table": DST, "value": PART}], "group": {"basis": "org"}, "cells": [a["to"], b["to"], {"table": DST, "cell": "c1"}], "rev": rev,
           "sigs": {x["to"]["cell"]: x["sig"] for x in p["pairs"]}}
    ap = _url(d, OTHER, "/split/apply")
    for patch in ({"cells": []}, {"cells": ["c6622"]}, {"cells": [a["to"], a["to"]]}, {"rev": None}, {"sigs": None}, {"group": None}):
        assert client.post(ap, json={**req, **patch}).status_code == 400, patch
    assert client.post(ap, json={**req, "rev": rev - 1}).status_code == 409
    table_heads.put(s.id, DST, ["c6937"], "field", stamps={"c6937": {"at": [9, 9, 1, 1], "text": ""}})    # 받을 표 하나에 보류된 헤더 지정 — 어느 표에도 안 넣는다
    held = client.post(ap, json=req)
    assert held.status_code == 409 and DST in held.json()["detail"] and "헤더 지정 1칸" in held.json()["detail"] and _text(d, SRC, "c6622") == ""
    assert [(h["table"], h["cell"]) for h in client.post(url, json=body).json()["held"]] == [(DST, "c6937")]
    table_heads.put(s.id, DST, ["c6937"], None)
    r = client.post(ap, json=req)
    assert r.status_code == 200, r.text
    m = r.json()["mapped"]
    assert m["split"] is True and m["table"] == OTHER and m["done"] == [a["to"], b["to"]] and m["to"] == [{"table": SRC, "value": LEAD}, {"table": DST, "value": PART}] and m["group"] == {"basis": "org", "on": "row", "level": 0}
    assert [(x["table"], x["cell"]) for x in m["skipped"]] == [(DST, "c1")] and "짝이 없습니다" in m["skipped"][0]["why"]
    assert _text(d, SRC, "c6622") == "한국선급" and _text(d, DST, "c6937") == "김공동" and (s.rev, len(s.undo)) == (rev + 1, undo + 1)   # 두 표에 한 번의 편집
    tops = {b["id"] for b in r.json()["tops"]["blocks"]}
    assert {SRC, DST} <= tops                                                                             # 응답에 바뀐 두 표가 함께 실린다
    ev = [e for e in works.events(d) if e["kind"] == "tableKv"]
    assert len(ev) == 1 and ev[0]["split"] == [SRC, DST] and ev[0]["cells"] == 2 and ev[0]["table"] == OTHER
    again = client.post(url, json={k: req[k] for k in ("to", "group")}).json()
    assert again["counts"]["fill"] == 12 and again["counts"]["same"] == 2
    assert client.post(f"/api/docs/{d}/undo").status_code == 200 and _text(d, SRC, "c6622") == "" and _text(d, DST, "c6937") == ""   # 실행 취소 1번에 둘 다 돌아온다
    assert _free(s)


# ---- 끝점 — 구분 기준의 값 고르기 · 양식의 확정본 ------------------------------------------------------------------------------

def test_api_plans_carry_div_for_every_way_of_putting(client):
    d = _split_doc(client)                                                                                # OTHER = 기관 값 머리가 있는 표(값이 든) · SRC · DST = 그 머리가 없는 빈 표
    one = client.post(_url(d, OTHER, "/plan"), json={"from": {"table": SRC}}).json()                      # 1대1 — 받을 표에 기준이 있다
    assert [x["div"] for x in one["pairs"]] == [{}] and one["pairs"][0]["label"] == "주소" and [(v["part"], v["pairs"]) for v in one["bases"][0]["values"]] == [(LEAD, 0), (PART, 0)]
    sp = client.post(_url(d, OTHER, "/split/plan"), json={"to": [{"table": SRC}, {"table": DST}], "group": {"basis": "org"}}).json()   # 나눠 넣기 — 원본 표의 기준 · 원본 칸의 키
    assert {x["to"]["table"]: x["div"] for x in sp["pairs"]} == {SRC: {"org": LEAD}, DST: {"org": PART}} and [(v["part"], v["pairs"], v["fill"]) for v in sp["bases"][0]["values"]] == [(LEAD, 6, 6), (PART, 8, 8)]
    part_cells = [x["to"] for x in sp["pairs"] if x["div"]["org"] == PART]                                # 「공동연구개발기관 만」 — 화면은 그 값의 칸만 보낸다(끝점의 넣기는 그대로)
    s = server.DOCS[d]
    r = client.post(_url(d, OTHER, "/split/apply"), json={"to": [{"table": SRC}, {"table": DST}], "group": {"basis": "org"}, "cells": part_cells, "rev": sp["rev"], "sigs": {x["to"]["cell"]: x["sig"] for x in sp["pairs"]}})
    assert r.status_code == 200 and len(r.json()["mapped"]["done"]) == 8 and _text(d, DST, "c6955") == "한국해양대학교" and _text(d, SRC, "c6622") == ""   # 다른 값의 칸은 그대로
    d2 = _sum_doc(client)[0]
    sm = client.post(_url(d2, CTE_C, "/plan"), json={"from": [{"table": CTE_A}, {"table": CTE_B}], "mode": "sum"}).json()   # 더해서 넣기 — 받을 표의 기준(단계)
    assert sm["bases"][0]["basis"] == "stage" and all(set(x["div"]) <= {"stage"} for x in sm["pairs"]) and sum(v["pairs"] for v in sm["bases"][0]["values"]) == sum(1 for x in sm["pairs"] if x["div"])
    assert sum(v["fill"] for v in sm["bases"][0]["values"]) == sm["counts"]["fill"] == 2 and s.rev == server.DOCS[d].rev


TPL_T, TPL_TWIN = "t6861", "t7194"   # 「그 밖의 수상경력 등 대표적 실적」 표 둘(3×4 · 값 칸 6) — 한 열을 짧은 글로 채우면 초안이 그 칸을 머리로 읽는다


def test_api_confirmed_template_keeps_the_keys_and_marks_the_sig(client, monkeypatch):
    from app import table_excel, table_types_api
    d = _open(client)
    s = server.DOCS[d]
    blank = client.get(_url(d, TPL_T)).json()
    keys = [i["key"] for i in blank["items"]]
    assert blank["source"] == "draft" and blank["template"] is None and len(keys) == 6
    j = TM.judge(table_excel.records(s.doc, TPL_T), TPL_T)                                                 # 빈 양식일 때의 판정을 「확정본」 으로(모든 칸의 역할 · 띠 — 값은 없다)
    tpl = {"id": "e1", "rev": 1, "roles": [[x["row"], x["col"], x["role"]] for x in j["table"]["cells"]], "bands": [{k: b[k] for k in ("id", "rows", "cols", "kind", "headerRows", "headerCols")} for b in j["subs"]]}
    col = [i["cell"] for i in blank["items"] if i["ref"].startswith("B")]
    assert len(col) == 2 and client.post(f"/api/docs/{d}/tables/{TPL_T}/fill/apply", json={"fills": [{"cell": c, "text": "홍길동"} for c in col]}).status_code == 200
    drift = client.get(_url(d, TPL_T)).json()
    assert drift["source"] == "draft" and [i["key"] for i in drift["items"]] != keys and len(drift["items"]) < 6   # 확정본이 없으면 — 채운 칸이 머리로 읽혀 키가 달라진다
    seen, fixed_tables = [], {TPL_T}

    def template_for(sess, tb):
        seen.append((sess.id, tb["id"], sess.lock.locked()))
        return tpl if tb["id"] in fixed_tables else None
    monkeypatch.setattr(table_types_api, "template_for", template_for)
    fixed = client.get(_url(d, TPL_T)).json()
    assert fixed["source"] == "template" and fixed["template"] == {"id": "e1", "rev": 1} and [i["key"] for i in fixed["items"]] == keys   # 확정본이 있으면 빈 양식 때와 같은 키
    assert {i["cell"]: i["text"] for i in fixed["items"]}[col[0]] == "홍길동" and seen == [(d, TPL_T, True)]    # 채운 칸은 값 칸 그대로 · 세션 잠금 안에서 부른다
    body = {"from": {"table": TPL_T}}
    p = client.post(_url(d, TPL_TWIN, "/plan"), json=body).json()                                         # 같은 타입의 빈 표에 — 확정본으로 읽은 키로 이어진다
    assert p["from"]["source"] == "template" and p["from"]["template"] == {"id": "e1", "rev": 1} and p["source"] == "draft" and p["template"] is None
    assert p["counts"]["fill"] == 2 and {x["text"] for x in p["pairs"] if x["status"] == "fill"} == {"홍길동"} and p["types"]["same"]
    sigs = {x["to"]: x["sig"] for x in p["pairs"]}
    tpl = {**tpl, "rev": 2}                                                                               # 확정본을 고쳤다(판 +1) — 도장이 달라진다
    p2 = client.post(_url(d, TPL_TWIN, "/plan"), json=body).json()
    sigs2 = {x["to"]: x["sig"] for x in p2["pairs"]}
    assert p2["from"]["template"] == {"id": "e1", "rev": 2} and set(sigs2) == set(sigs) and all(sigs2[k] != sigs[k] for k in sigs)
    to = [x["to"] for x in p["pairs"] if x["status"] == "fill"]
    old = client.post(_url(d, TPL_TWIN, "/apply"), json={**body, "cells": to, "rev": p["rev"], "sigs": sigs})
    assert old.status_code == 409 and _text(d, TPL_TWIN, to[0]) == ""                                      # 옛 판을 본 계획으로는 넣지 않는다
    new = client.post(_url(d, TPL_TWIN, "/apply"), json={**body, "cells": to, "rev": p2["rev"], "sigs": sigs2})
    assert new.status_code == 200 and new.json()["mapped"]["done"] == to and _text(d, TPL_TWIN, to[0]) == "홍길동"
    back = client.post(_url(d, TPL_T, "/plan"), json={"from": {"table": TPL_TWIN}}).json()                 # 받을 표가 확정본으로 판정된 쪽 — 값을 넣은 원본(확정본 없음)은 초안이 다시 흔들려 안 이어진다
    assert back["source"] == "template" and back["template"] == {"id": "e1", "rev": 2} and back["from"]["source"] == "draft" and back["counts"]["same"] == 0
    fixed_tables.add(TPL_TWIN)                                                                            # 구조가 같은 표라 같은 확정본이 맞는다 — 두 표 모두 확정본으로
    both = client.post(_url(d, TPL_T, "/plan"), json={"from": {"table": TPL_TWIN}}).json()
    assert both["from"]["source"] == "template" and both["counts"]["same"] == p["counts"]["same"] + 2 and both["counts"]["unmatched"] == 0   # 넣은 두 칸이 「같음」 으로 이어진다


def test_api_offs_remember_the_values_turned_off_per_table_type(client):
    """꺼 둔 값을 기억한다(같은 사양서 ② §7) — 표 타입마다 저장 · 통째로 바꿈 · 빈 것이면 지움. 규칙 묶음 · 계획은 그대로."""
    d = _open(client)
    t = client.get(_url(d, OTHER)).json()["type"]
    u = "/api/table-maps/offs"
    assert client.get(u, params={"type": t}).json() == {"type": t, "offs": {}}
    r = client.put(u, json={"type": t, "offs": {"org": ["주관연구개발기관", "주관연구개발기관"], "year": []}})
    assert r.status_code == 200 and r.json() == {"type": t, "offs": {"org": ["주관연구개발기관"]}}
    assert client.get(u, params={"type": t}).json()["offs"] == {"org": ["주관연구개발기관"]}
    assert client.get(u, params={"type": client.get(_url(d, SRC)).json()["type"]}).json()["offs"] == {}        # 다른 타입의 것은 따로
    assert client.get("/api/table-maps").json() == {"maps": []}                                               # 규칙 묶음과 따로
    p = client.post(_url(d, OTHER, "/plan"), json={"from": {"table": SRC}}).json()
    assert "offs" not in p and all("div" in x for x in p["pairs"])                                            # 계획은 저장된 것을 보지 않는다(끄는 것은 화면의 고름)
    for bad in ({"type": "zz", "offs": {}}, {"offs": {"org": ["a"]}}, {"type": t, "offs": {"month": ["1월"]}}, {"type": t, "offs": {"org": "a"}}, {"type": t, "offs": ["a"]}):
        assert client.put(u, json=bad).status_code == 400, bad
    assert client.get(u, params={"type": "zz"}).status_code == 400 and client.get(u).status_code == 400
    assert client.get(u, params={"type": t}).json()["offs"] == {"org": ["주관연구개발기관"]}                    # 틀린 요청은 저장된 것을 안 바꾼다
    assert client.put(u, json={"type": t, "offs": {"org": []}}).json() == {"type": t, "offs": {}}             # 「모두」 = 그 기준의 저장을 지움
    assert client.get(u, params={"type": t}).json() == {"type": t, "offs": {}}


# ---- 칸마다 넣는 방식(같은 사양서 ② §7 「칸마다 넣는 방식」) — 순수 ------------------------------------------------------------------------------------

def _one(src_vals, dst_vals):
    """(원본의 추출, 받을 표의 추출) — 둘 다 한 차년도의 표(「구분 | 현금 | 현물」 × 인건비 · 재료비 · 합계), 안 준 값 칸은 빈 칸."""
    blank = {r: "" for r in Y2}
    return _ex("t200", _year_table({**blank, **src_vals}), 201), _ex("t100", _year_table({**blank, **dst_vals}), 101)


def test_ops_add_sub_on_cells_with_and_without_values():
    src, dst = _one({"B2": "700", "C2": "200", "B3": "5", "C3": "값을 확인한다.", "B4": "705"}, {"B2": "500", "C2": "1,000", "C3": "10", "B4": "1"})
    rules = {"ops": [{"part": "현금", "op": "add"}, {"key": "인건비|현물", "op": "sub"}, {"key": "재료비|현물", "op": "add"}]}
    p = KV.plan(src, dst, rules)
    by = _pairs(p)
    a = by["인건비 | 현금"]
    assert (a["op"], a["status"], a["text"], a["was"], a["expr"], a["check"], a["src"]) == ("add", "fill", "1,200", "500", "= 500 + 700", True, "700")   # 받을 칸의 수 + 원본의 수 · 이미 값이 있으면 확인
    b = by["인건비 | 현물"]
    assert (b["op"], b["status"], b["text"], b["expr"], b["check"]) == ("sub", "fill", "800", "= 1,000 − 200", True)
    c = by["재료비 | 현금"]
    assert (c["op"], c["status"], c["text"], c["expr"]) == ("add", "fill", "5", "= 0 + 5") and "check" not in c       # 빈 칸은 0 으로 본다 — 확인 없음
    d = by["재료비 | 현물"]
    assert (d["op"], d["status"], d["text"]) == ("add", "nonnum", "") and "원본이 수가 아닌 글" in d["why"]            # 수가 아닌 글 — 안 넣는다
    assert (by["합계 | 현금"]["op"], by["합계 | 현금"]["status"]) == ("add", "calc")                                   # 수식으로 셈하는 칸에는 어느 방식도 안 넣는다
    assert (by["합계 | 현물"]["op"], by["합계 | 현물"]["status"]) == ("fill", "emptySrc")                             # 방식을 안 정한 칸 = 빈 칸에만(전과 같다)
    assert p["counts"] == {"fill": 3, "same": 0, "clash": 0, "calc": 1, "emptySrc": 1, "nonnum": 1, "check": 2, "unmatched": 0, "unmatchedSrc": 0, "unmatchedDst": 0, "byRule": 0}
    assert KV.sig(a) != KV.sig({**a, "op": "fill"}) and KV.sig(a) != KV.sig({**a, "was": "1,200", "text": "1,900"})    # 도장에 방식이 든다 · 한 번 더한 뒤에는 달라진다
    assert all(x["op"] == "fill" and "expr" not in x and "src" not in x for x in KV.plan(src, dst)["pairs"])          # 규칙이 없으면 모두 빈 칸에만
    src, dst = _one({"B2": "0", "C2": "30", "B3": "1,500"}, {"B2": "500", "C2": "값을 확인한다.", "B3": "0,000"})
    by = _pairs(KV.plan(src, dst, {"ops": [{"part": "인건비", "op": "add"}, {"part": "재료비", "op": "sub"}]}))
    assert (by["인건비 | 현금"]["status"], by["인건비 | 현금"]["text"]) == ("same", "500")                             # 0 을 더하면 그대로 — 같음
    assert by["인건비 | 현물"]["status"] == "nonnum" and "받을 칸의 글이 수가 아니" in by["인건비 | 현물"]["why"]
    low = by["재료비 | 현금"]
    assert (low["status"], low["text"], low["expr"], low["was"]) == ("fill", "-1,500", "= 0 − 1,500", "0,000") and "check" not in low   # 자리표시뿐인 칸은 빈 칸(0)


def test_ops_replace_and_which_rule_wins():
    src, dst = _one({"B2": "700", "C2": "20", "B3": "5", "C3": ""}, {"B2": "500", "C2": "20", "C3": "10"})
    by = _pairs(KV.plan(src, dst, {"ops": [{"part": "인건비", "op": "replace"}, {"part": "재료비", "op": "replace"}]}))
    r = by["인건비 | 현금"]
    assert (r["op"], r["status"], r["text"], r["was"], r["check"]) == ("replace", "fill", "700", "500", True) and "expr" not in r   # 덮어쓰기 — 다른 글이 있어도 넣을 수 있음(확인)
    assert by["인건비 | 현물"]["status"] == "same" and (by["재료비 | 현금"]["status"], by["재료비 | 현금"].get("check")) == ("fill", None)   # 같으면 같음 · 빈 칸이면 확인 없음
    assert by["재료비 | 현물"]["status"] == "emptySrc"                                                               # 원본이 비었으면 덮어 지우지 않는다
    plain = _pairs(KV.plan(src, dst))["인건비 | 현금"]
    assert (plain["status"], plain["op"]) == ("clash", "fill")                                                       # 기본은 여전히 빈 칸에만(겹치면 안 덮는다)
    both = [{"part": "현금", "op": "add"}, {"part": "인건비", "op": "sub"}]
    assert _pairs(KV.plan(src, dst, {"ops": both}))["인건비 | 현금"]["op"] == "sub"                                   # 머리글 둘에 걸리면 나중에 적은 것
    assert _pairs(KV.plan(src, dst, {"ops": both[::-1]}))["인건비 | 현금"]["op"] == "add"
    keyed = _pairs(KV.plan(src, dst, {"ops": [{"key": "인건비|현금", "op": "replace"}, *both]}))
    assert keyed["인건비 | 현금"]["op"] == "replace" and keyed["재료비 | 현금"]["op"] == "add" and keyed["인건비 | 현물"]["op"] == "sub"   # 칸(key) 쪽이 머리글(part)보다 먼저
    assert _pairs(KV.plan(src, dst, {"ops": [{"part": "현금", "op": "add"}, {"key": "인건비|현금", "op": "fill"}]}))["인건비 | 현금"]["status"] == "clash"   # 그 칸만 빈 칸에만으로 되돌릴 수 있다


def test_ops_in_grouped_sum_and_split_plans():
    dst, base, y1, y2 = _two_years({"B3": "500", "D3": "999"})
    rules = [{"ops": [{"key": "인건비|1차년도›현금", "op": "add"}]}, {"ops": [{"part": "2차년도", "op": "replace"}]}]   # 방식은 받을 표의 제 키 · 머리글로 찾는다(값 머리 조각을 빼기 전)
    p = KV.plan_grouped([{"ex": y1, "value": "1차년도", "table": "t200"}, {"ex": y2, "value": "2차년도", "table": "t300"}], dst, base, rules)
    by = _pairs(p)
    a, r = by["인건비 | 1차년도 › 현금"], by["인건비 | 2차년도 › 현금"]
    assert (a["op"], a["status"], a["text"], a["expr"], a["check"]) == ("add", "fill", "600", "= 500 + 100", True)
    assert (r["op"], r["status"], r["text"], r["was"], r["check"]) == ("replace", "fill", "120", "999", True) and p["counts"]["check"] == 2 and p["counts"]["clash"] == 0
    assert by["재료비 | 1차년도 › 현금"]["op"] == "fill" and by["재료비 | 2차년도 › 현물"]["op"] == "replace"
    a, b, dst = _sum3({"B2": "500", "C2": "10", "B3": "1", "B4": "150"}, {"B2": "700", "C2": "20", "B3": "2", "B4": "180"}, {"B2": "100", "C2": "5", "B3": "9"})
    rules = {"ops": [{"key": "인건비|현금", "op": "add"}, {"key": "인건비|현물", "op": "sub"}, {"key": "재료비|현금", "op": "replace"}]}
    p = KV.plan_sum([{"ex": a, "table": "t200"}, {"ex": b, "table": "t300"}], dst, rules)
    by = _pairs(p)
    one = by["인건비 | 현금"]
    assert (one["op"], one["status"], one["text"], one["sum"], one["expr"], one["check"]) == ("add", "fill", "1,300", 1200, "= 100 + 500 + 700", True)   # 방식은 원본들의 합에 걸린다
    two = by["인건비 | 현물"]
    assert (two["op"], two["status"], two["text"], two["sum"], two["expr"]) == ("sub", "fill", "-25", 30, "= 5 − (10 + 20)")
    assert (by["재료비 | 현금"]["op"], by["재료비 | 현금"]["status"], by["재료비 | 현금"]["text"], by["재료비 | 현금"]["check"]) == ("replace", "fill", "3", True)
    assert by["합계 | 현금"]["status"] == "calc" and by["합계 | 현금"]["why"] == "수식으로 셈하는 칸 — 넣은 뒤 다시 계산합니다" and p["counts"]["check"] == 3
    src, base, t1, t2 = _split3()
    full = next(i for i in src["items"] if i["label"] == "인건비 | 1차년도 › 현금")
    t1 = {**t1, "items": [{**i, "text": "5", "empty": False} if i["label"] == "인건비 | 현금" else i for i in t1["items"]]}   # 받을 표의 그 칸에 이미 5
    p = KV.plan_split(src, [{"ex": t1, "value": "1차년도", "table": "t200"}, {"ex": t2, "value": "2차년도", "table": "t300"}], base, [{"ops": [{"key": "인건비|현금", "op": "add"}]}, None])
    hit = next(x for x in p["pairs"] if x["tgt"] == 0 and x["label"] == "인건비 | 현금")
    assert (hit["op"], hit["status"], hit["text"], hit["check"], hit["from"]) == ("add", "fill", str(5 + int(full["text"])), True, full["cell"]) and p["counts"]["check"] == 1
    assert all(x["op"] == "fill" for x in p["pairs"] if x["tgt"] == 1)                                             # 방식은 받을 표(그 타입 짝의 묶음)마다


# ---- 계산 칸 다시 계산(같은 사양서 ② §7 「계산 칸 다시 계산」) — 순수 ------------------------------------------------------------------------------------

def _recalc(vals=None, **kw):
    s1 = _stage1("t100", _budget(vals=vals), 101)
    j = TM.judge(s1, "t100", stored=None, user=None)
    r = KV.recalc(j["table"], j["sem"], kw.pop("subs", j["subs"]), **kw)
    return r, {i["ref"]: i for i in r["items"]}


def test_recalc_fills_totals_and_then_the_total_of_totals():
    r, by = _recalc()
    assert sorted(by) == ["B5", "C5", "D5", "E5", "F3", "F4", "F5"] and r["counts"] == {"missing": 0, "mismatch": 0, "ok": 7, "incomplete": 0, "conflict": 0} and r["passes"] == 0   # 맞게 적힌 표 — 모두 같음
    assert by["F3"]["formula"] == "=SUM(B3:E3)" and by["F3"]["value"] == 270 and by["F3"]["now"] == "270" and not r["more"]
    r, by = _recalc({"F3": "", "F4": "", "B5": "", "C5": "", "D5": "", "E5": "", "F5": ""})
    assert r["counts"]["missing"] == 7 and r["passes"] == 1 and not r["more"]                                    # 줄 합 · 열 합을 채운 값으로 한 번 더 — 합계의 합계까지
    assert [(by[k]["status"], by[k]["text"]) for k in ("F3", "F4", "B5", "E5")] == [("missing", "270"), ("missing", "130"), ("missing", "150"), ("missing", "40")]
    assert "needs" not in by["F3"] and "check" not in by["F3"] and by["F3"]["note"]
    grand = by["F5"]
    assert (grand["status"], grand["text"], grand["value"], grand["now"]) == ("missing", "400", 400, "") and grand["needs"] and set(grand["needs"]) <= {by[k]["cell"] for k in ("F3", "F4", "B5", "C5", "D5", "E5")}
    assert KV.recalc_sig(grand) != KV.recalc_sig({**grand, "text": "401"}) and KV.recalc_sig(grand) != KV.recalc_sig({**grand, "needs": []}) and len(KV.recalc_sig(grand)) == 12
    one, by1 = _recalc({"F3": "", "F4": "", "B5": "", "C5": "", "D5": "", "E5": "", "F5": ""}, subs=None)       # 띠를 안 주면 한 겹만 — 합계의 합계는 아직 못 센다
    assert by1["F3"]["status"] == "missing" and by1["F5"]["status"] == "incomplete" and one["passes"] == 0
    wide, byw = _recalc({"B3": "1000", "C3": "200", "D3": "1200", "E3": "300", "F3": "0,000", "F5": "0,000"})    # 넣을 글의 꼴 — 그 칸의 자리표시(쉼표)
    assert (byw["F3"]["status"], byw["F3"]["text"], byw["F3"]["now"]) == ("missing", "2,700", "0,000")


def test_recalc_mismatch_incomplete_conflict_and_cells_that_cannot_be_written():
    r, by = _recalc({"F3": "999"})
    bad = by["F3"]
    assert (bad["status"], bad["check"], bad["text"], bad["now"], bad["value"]) == ("mismatch", True, "270", "999", 270) and "다릅니다" in bad["why"]   # 지금 값과 다름 — 확인(처음에는 안 고른다)
    clash = by["F5"]                                                                                              # 가로 합(400) ≠ 세로 합(999 + 130) — 넣지 않고 둘 다 보인다
    assert (clash["status"], clash["text"], clash["value"]) == ("conflict", "", None) and sorted(x["text"] for x in clash["both"]) == ["1,129", "400"] and "서로 다른 값" in clash["why"]
    assert {x["axis"] for x in clash["both"]} == {"row", "col"} and all(x["formula"].startswith("=") for x in clash["both"]) and r["counts"]["conflict"] == 1
    r, by = _recalc({"C3": "", "F3": ""})
    part = by["F3"]
    assert (part["status"], part["text"], part["value"]) == ("incomplete", "", None) and "C3" in part["why"] and "빈 칸" in part["why"]   # 더할 칸 가운데 빈 것 — 안 넣는다(어느 칸인지)
    assert by["C5"]["status"] == "incomplete" and by["B5"]["status"] == "ok" and r["counts"]["incomplete"] >= 2
    r, by = _recalc({"B3": "", "C3": "", "D3": "", "E3": "", "F3": ""})
    assert by["F3"]["status"] == "incomplete" and "모두 비어" in by["F3"]["why"]
    cid = _recalc({"F3": ""})[1]["F3"]["cell"]
    r, by = _recalc({"F3": ""}, objs={cid})
    assert (by["F3"]["status"], by["F3"]["why"]) == ("incomplete", "칸 안에 표 · 그림이 있어 넣지 않습니다") and "check" not in by["F3"]
    assert KV.recalc({"cells": []}, {"formulas": []}) == {"items": [], "counts": {"missing": 0, "mismatch": 0, "ok": 0, "incomplete": 0, "conflict": 0}, "passes": 0, "more": False}


# ---- 칸마다 넣는 방식 · 계산 칸 다시 계산 — 끝점 ----------------------------------------------------------------------------------------------------

def test_api_ops_are_saved_planned_applied_and_a_second_apply_is_skipped(client):
    d, keys, cell = _sum_doc(client)                                   # 원본 CTE_A: 500 · 1,000 · (글) · 3 / 받을 표 CTE_C: 넷째 칸에 7
    s = server.DOCS[d]
    t = client.get(_url(d, CTE_C)).json()["type"]
    body = {"from": {"table": CTE_A}}
    m = client.put("/api/table-maps", json={"from": {"type": t, "label": "CTE1"}, "to": {"type": t, "label": "CTE3"}, "ops": [{"key": keys[3], "op": "add", "label": "넷째 칸"}]})
    assert m.status_code == 200, m.text
    m = m.json()
    assert m["ops"] == [{"key": keys[3], "op": "add", "label": "넷째 칸"}] and m["alias"] == [] and m["pairs"] == []      # 넣는 방식만 있는 묶음(같은 타입끼리)
    p = client.post(_url(d, CTE_C, "/plan"), json=body).json()
    by = {x["key"]: x for x in p["pairs"]}
    a = by[keys[3]]
    assert (a["op"], a["status"], a["text"], a["was"], a["expr"], a["check"]) == ("add", "fill", "10", "7", "= 7 + 3", True)
    assert p["rules"] == {"id": m["id"], "name": m["name"], "alias": 0, "pairs": 0, "ops": 1, "used": 0} and p["counts"]["check"] == 1
    assert (by[keys[0]]["op"], by[keys[0]]["status"], by[keys[0]]["text"]) == ("fill", "fill", "500") and "check" not in by[keys[0]]
    to3, to0, to1 = (cell[CTE_C][k] for k in (keys[3], keys[0], keys[1]))
    rev, undo = s.rev, len(s.undo)
    req = {**body, "cells": [to3], "rev": rev, "sigs": {x["to"]: x["sig"] for x in p["pairs"]}}
    r = client.post(_url(d, CTE_C, "/apply"), json=req)
    assert r.status_code == 200, r.text
    assert r.json()["mapped"]["done"] == [to3] and _text(d, CTE_C, to3) == "10" and (s.rev, len(s.undo)) == (rev + 1, undo + 1)   # 값이 있던 칸에 더해 넣음 · 실행 취소 1개
    again = client.post(_url(d, CTE_C, "/apply"), json={**req, "rev": s.rev})          # 같은 반영을 다시 — 지금 글(10)이 달라져 도장이 다르다: 두 번 더해지지 않는다
    assert again.status_code == 409 and _text(d, CTE_C, to3) == "10"
    both = client.post(_url(d, CTE_C, "/apply"), json={**req, "rev": s.rev, "cells": [to3, to0]})
    assert both.status_code == 200, both.text
    mm = both.json()["mapped"]
    assert mm["done"] == [to0] and [(x["cell"], "달라짐" in x["why"]) for x in mm["skipped"]] == [(to3, True)] and (_text(d, CTE_C, to3), _text(d, CTE_C, to0)) == ("10", "500")
    nxt = {x["key"]: x for x in client.post(_url(d, CTE_C, "/plan"), json=body).json()["pairs"]}[keys[3]]
    assert (nxt["text"], nxt["was"], nxt["expr"]) == ("13", "10", "= 10 + 3") and nxt["sig"] != a["sig"]                # 다시 받은 계획은 지금 값에서 또 더한 것(사람이 보고 고른다)
    m2 = client.put("/api/table-maps", json={"id": m["id"], "version": m["version"], "from": m["from"], "to": m["to"], "ops": [{"key": keys[3], "op": "sub"}, {"part": "개발연차", "op": "replace"}]})
    assert m2.status_code == 200 and m2.json()["version"] == m["version"] + 1 and len(m2.json()["ops"]) == 2
    by = {x["key"]: x for x in client.post(_url(d, CTE_C, "/plan"), json=body).json()["pairs"]}
    assert (by[keys[3]]["op"], by[keys[3]]["status"], by[keys[3]]["text"], by[keys[3]]["expr"]) == ("sub", "fill", "7", "= 10 − 3")   # 칸(key)에 정한 것이 머리글(part)보다 먼저
    assert (by[keys[0]]["op"], by[keys[0]]["status"]) == ("replace", "same") and (by[keys[1]]["op"], by[keys[1]]["status"], by[keys[1]]["text"], by[keys[1]].get("check")) == ("replace", "fill", "1,000", None)
    assert client.post(_url(d, CTE_C, "/plan"), json={**body, "rules": False}).json()["pairs"][0]["op"] == "fill"       # 규칙 없이 = 모두 빈 칸에만
    bad = client.put("/api/table-maps", json={"id": m["id"], "version": m["version"] + 1, "from": m["from"], "to": m["to"], "ops": [{"part": "개발연차", "op": "mul"}]})
    assert bad.status_code == 400 and len(client.get("/api/table-maps").json()["maps"][0]["ops"]) == 2
    assert to1 != to0


RECALC_T = "t1339"   # 「계」 줄 · 「계」 열이 있는 표(6×7 — 값 칸 12 · 수식 칸 8: 줄 합 넷 · 열 합 셋 · 합의 합 하나)


def test_api_recalc_plan_and_apply(client):
    d = _open(client)
    s = server.DOCS[d]
    u = lambda tail: _url(d, RECALC_T, f"/recalc{tail}")   # noqa: E731
    p0 = client.post(u("/plan"))
    assert p0.status_code == 200, p0.text
    p0 = p0.json()
    assert p0["counts"] == {"missing": 0, "mismatch": 0, "ok": 0, "incomplete": 8, "conflict": 0} and p0["rev"] == s.rev and p0["source"] == "draft" and p0["held"] == []   # 빈 양식 — 셈할 칸이 비어 있다
    assert all(len(i["sig"]) == 12 and i["text"] == "" and "모두 비어" in i["why"] for i in p0["items"])
    blank = [i for i in client.get(_url(d, RECALC_T)).json()["items"] if not i["calc"] and i["empty"]]
    assert len(blank) == 12
    assert client.post(f"/api/docs/{d}/tables/{RECALC_T}/fill/apply", json={"fills": [{"cell": i["cell"], "text": str(10 * (n + 1))} for n, i in enumerate(blank)]}).status_code == 200
    p = client.post(u("/plan")).json()
    by = {i["ref"]: i for i in p["items"]}
    assert p["counts"]["missing"] == 8 and p["passes"] == 1 and not p["more"] and p["rev"] == s.rev
    assert (by["F2"]["status"], by["F2"]["text"], by["F2"]["formula"], by["F2"]["now"]) == ("missing", "30", "=SUM(D2:E2)", "") and by["F2"]["label"] and "needs" not in by["F2"]
    assert (by["D6"]["text"], by["E6"]["text"], by["G6"]["text"]) == ("220", "260", "300")
    grand = by["F6"]
    assert (grand["status"], grand["text"]) == ("missing", "480") and grand["needs"] == [by[k]["cell"] for k in ("F2", "F3", "F4", "F5")]   # 줄 합에 기대는 합의 합 — 한 번의 계획에서 끝까지
    sigs = {i["cell"]: i["sig"] for i in p["items"]}
    rev, undo = s.rev, len(s.undo)
    for bad in ({"cells": [], "rev": rev, "sigs": sigs}, {"cells": [grand["cell"]], "sigs": sigs}, {"cells": [grand["cell"]], "rev": rev, "sigs": []}, {"cells": [grand["cell"]] * 2, "rev": rev, "sigs": sigs}):
        assert client.post(u("/apply"), json=bad).status_code == 400, bad
    assert client.post(u("/apply"), json={"cells": [grand["cell"]], "rev": rev - 1, "sigs": sigs}).status_code == 409
    assert client.post(u("/apply"), json={"cells": [grand["cell"]], "rev": rev, "sigs": sigs}).status_code == 409         # 기대는 칸 없이 합의 합만 — 넣지 않는다
    r = client.post(u("/apply"), json={"cells": [grand["cell"], by["F2"]["cell"]], "rev": rev, "sigs": sigs})
    assert r.status_code == 200, r.text
    m = r.json()["mapped"]
    assert m["recalc"] is True and m["done"] == [by["F2"]["cell"]] and [x["cell"] for x in m["skipped"]] == [grand["cell"]] and "같이 넣어야" in m["skipped"][0]["why"]
    assert _text(d, RECALC_T, by["F2"]["cell"]) == "30" and _text(d, RECALC_T, grand["cell"]) == "" and (s.rev, len(s.undo)) == (rev + 1, undo + 1)
    p = client.post(u("/plan")).json()
    by = {i["ref"]: i for i in p["items"]}
    assert by["F2"]["status"] == "ok" and by["F6"]["needs"] == [by[k]["cell"] for k in ("F3", "F4", "F5")] and p["counts"]["missing"] == 7
    rev, undo = s.rev, len(s.undo)
    todo = [i["cell"] for i in p["items"] if i["status"] == "missing"]
    r = client.post(u("/apply"), json={"cells": todo, "rev": rev, "sigs": {i["cell"]: i["sig"] for i in p["items"]}})
    assert r.status_code == 200 and r.json()["mapped"]["done"] == todo and r.json()["mapped"]["skipped"] == [] and (s.rev, len(s.undo)) == (rev + 1, undo + 1)   # 한 번의 편집
    assert _text(d, RECALC_T, by["F6"]["cell"]) == "480" and _text(d, RECALC_T, by["D6"]["cell"]) == "220"
    ev = [e for e in works.events(d) if e["kind"] == "tableKv"]
    assert len(ev) == 2 and ev[-1]["recalc"] is True and ev[-1]["cells"] == 7 and ev[-1]["table"] == RECALC_T
    done = client.post(u("/plan")).json()
    assert done["counts"] == {"missing": 0, "mismatch": 0, "ok": 8, "incomplete": 0, "conflict": 0}
    d2 = next(i for i in client.get(_url(d, RECALC_T)).json()["items"] if i["ref"] == "D2")                              # 값 칸 하나를 고친다(10 → 15) — 그 줄 합 · 열 합이 「다름」
    pid = next(b["id"] for x in s.doc.table_block(RECALC_T)["cells"] if x["id"] == d2["cell"] for b in x["blocks"] if b["type"] == "paragraph")
    assert client.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": "15"}).status_code == 200
    p = client.post(u("/plan")).json()
    by = {i["ref"]: i for i in p["items"]}
    assert (by["F2"]["status"], by["F2"]["check"], by["F2"]["now"], by["F2"]["text"]) == ("mismatch", True, "30", "35") and (by["D6"]["status"], by["D6"]["text"]) == ("mismatch", "225")
    assert by["F6"]["status"] == "ok" and "needs" not in by["F6"]                                                        # 다른 값이 든 칸은 지금 값 그대로 윗겹에 든다
    r = client.post(u("/apply"), json={"cells": [by["F2"]["cell"]], "rev": s.rev, "sigs": {i["cell"]: i["sig"] for i in p["items"]}})
    assert r.status_code == 200 and _text(d, RECALC_T, by["F2"]["cell"]) == "35"
    plan = client.post(u("/plan")).json()
    after = {i["ref"]: i for i in plan["items"]}
    assert after["F2"]["status"] == "ok" and after["F6"]["status"] == "conflict" and sorted(x["text"] for x in after["F6"]["both"]) == ["480", "485"]   # 줄 합들의 합(485) ≠ 열 합들의 합(220 + 260) — 넣지 않는다
    assert client.post(u("/apply"), json={"cells": [after["F6"]["cell"]], "rev": s.rev, "sigs": {i["cell"]: i["sig"] for i in plan["items"]}}).status_code == 409
    assert client.post(u("/apply"), json={"cells": [after["D6"]["cell"]], "rev": s.rev, "sigs": {i["cell"]: i["sig"] for i in plan["items"]}}).status_code == 200   # 열 합도 맞추면
    after = {i["ref"]: i for i in client.post(u("/plan")).json()["items"]}
    assert (after["F6"]["status"], after["F6"]["check"], after["F6"]["text"], after["F6"]["now"]) == ("mismatch", True, "485", "480")   # 두 수식이 같은 값 — 윗겹이 「다름」 으로
    assert client.post(f"/api/docs/{d}/undo").status_code == 200
    assert client.post(f"/api/docs/{d}/undo").status_code == 200 and _text(d, RECALC_T, by["F2"]["cell"]) == "30"
    assert client.post(_url(d, "t99999", "/recalc/plan")).status_code == 404
    _free(s)


# ---- astra 4차(같은 사양서 ② §7 — 셈하는 수의 단위 · 「같음」 은 수가 꼭 같을 때만 · 같은 기준이 행 · 열 양쪽 · 기대는 칸을 모두 따진다 · 넣을 글은 계산한 수와 같은 수) --------

def test_units_that_differ_are_not_added_and_mixed_ones_ask_first():
    src, dst = _one({"B2": "1,200천원", "C2": "3명", "B3": "700천원", "C3": "50"}, {"B2": "2백만원", "C2": "2건", "B3": "500천원", "C3": "100천원"})
    p = KV.plan(src, dst, {"ops": [{"part": "현금", "op": "add"}, {"part": "현물", "op": "add"}]})
    by = _pairs(p)
    a = by["인건비 | 현금"]
    assert (a["status"], a["text"], a["why"]) == ("nonnum", "", "단위가 다릅니다(백만원 · 천원)") and "check" not in a           # 「2백만원」 + 「1,200천원」 — 환산하지 않는다: 안 넣는다(전에는 「1,202」)
    assert (by["인건비 | 현물"]["status"], by["인건비 | 현물"]["why"]) == ("nonnum", "단위가 다릅니다(건 · 명)")                    # 「2건」 + 「3명」(전에는 「5」)
    same = by["재료비 | 현금"]
    assert (same["status"], same["text"], same["expr"], same["check"], same["had"]) == ("fill", "1,200천원", "= 500천원 + 700천원", True, True) and "why" not in same   # 같은 단위 — 넣을 글에 뒤 글을 지킨다
    mix = by["재료비 | 현물"]
    assert (mix["status"], mix["text"], mix["check"], mix["why"]) == ("fill", "150천원", True, "단위를 적지 않은 수가 섞여 있습니다")     # 적은 수와 안 적은 수 — 셈하되 확인
    assert p["counts"]["nonnum"] == 2 and p["counts"]["fill"] == 2 and p["counts"]["check"] == 2
    src, dst = _one({"B2": "50", "C2": "-", "B3": "3%"}, {"C2": "5명", "B3": "00%"})
    by = _pairs(KV.plan(src, dst, {"ops": [{"part": "인건비", "op": "add"}, {"part": "재료비", "op": "sub"}]}))
    assert (by["인건비 | 현금"]["text"], by["인건비 | 현금"].get("check")) == ("50", None)                                        # 빈 칸 + 단위 없는 수 — 그대로
    assert (by["인건비 | 현물"]["status"], by["인건비 | 현물"]["text"]) == ("same", "5명")                                        # 「-」(0)는 단위를 따지지 않는다
    assert (by["재료비 | 현금"]["status"], by["재료비 | 현금"]["text"], by["재료비 | 현금"].get("check")) == ("fill", "-3%", None)   # 자리표시 「00%」 의 꼴과 같은 뒤 글


def test_sum_units_and_same_only_when_the_number_is_exactly_the_same():
    a, b, dst = _sum3({"B2": "1,200천원", "C2": "10%", "B3": "40", "C3": "40"}, {"B2": "2백만원", "C2": "15", "B3": "60", "C3": "60"}, {"B3": "100.4", "C3": "100"})
    srcs = [{"ex": a, "table": "t200"}, {"ex": b, "table": "t300"}]
    p = KV.plan_sum(srcs, dst)
    by = _pairs(p)
    bad = by["인건비 | 현금"]
    assert (bad["status"], bad["text"], bad["sum"], bad["why"]) == ("nonnum", "", None, "단위가 다릅니다(천원 · 백만원)") and "check" not in bad   # 빈 칸에 더해서 넣기 — 기본으로 고르던 「1,202」 가 아니다
    mix = by["인건비 | 현물"]
    assert (mix["status"], mix["text"], mix["sum"], mix["check"], mix["why"]) == ("fill", "25%", 25, True, "단위를 적지 않은 수가 섞여 있습니다") and "missing" not in mix   # 「10%」 + 「15」
    near = by["재료비 | 현금"]
    assert (near["status"], near["text"], near["was"]) == ("clash", "100", "100.4") and "덮지 않습니다" in near["why"]              # 「40 + 60」 과 「100.4」 — 같음이 아니라 겹침(전에는 허용 오차 0.5 로 같음)
    assert by["재료비 | 현물"]["status"] == "same" and p["counts"]["same"] == 1 and p["counts"]["nonnum"] == 1 and p["counts"]["check"] == 1
    over = _pairs(KV.plan_sum(srcs, dst, {"ops": [{"part": "재료비", "op": "replace"}]}))
    assert (over["재료비 | 현금"]["status"], over["재료비 | 현금"]["text"], over["재료비 | 현금"]["check"], over["재료비 | 현금"]["had"]) == ("fill", "100", True, True)   # 덮어쓰기면 확인이 붙은 넣을 수 있음
    assert over["재료비 | 현물"]["status"] == "same"
    a, b, dst = _sum3({"B2": "1,200"}, {"B2": "0.0"}, {"B2": "1200.0"})
    assert _pairs(KV.plan_sum([{"ex": a, "table": "t200"}, {"ex": b, "table": "t300"}], dst))["인건비 | 현금"]["status"] == "same"   # 꼴(쉼표 · 소수 자리)만 다른 같은 수는 같음


def _years_both_ways(vals):
    return [(0, 0, 1, 1, SHADE, ["구분"]), (0, 1, 1, 1, SHADE, ["2026년"]), (0, 2, 1, 1, SHADE, ["2027년"]),
            (1, 0, 1, 1, SHADE, ["2026년"]), (1, 1, 1, 1, None, [vals[0]]), (1, 2, 1, 1, None, [vals[1]]),
            (2, 0, 1, 1, SHADE, ["2027년"]), (2, 1, 1, 1, None, [vals[2]]), (2, 2, 1, 1, None, [vals[3]])]


def test_div_keeps_every_value_when_rows_and_columns_share_a_basis():
    tb, dst = _tbx("t100", _years_both_ways(["", "", "", ""]), 101)
    src = _ex("t200", _years_both_ways(["1", "2", "3", "4"]), 201)
    bases = KV.bases(tb)
    assert [(b["basis"], b["on"]) for b in bases] == [("period", "col"), ("period", "row")]
    p = KV.plan(src, dst)
    got = KV.with_div(bases, p["pairs"])
    div = {x["key"]: x["div"] for x in p["pairs"]}
    assert div == {"2026년|2026년": {"period": "2026년"}, "2026년|2027년": {"period": ["2027년", "2026년"]}, "2027년|2026년": {"period": ["2026년", "2027년"]}, "2027년|2027년": {"period": "2027년"}}
    off = {"2026년"}                                                  # 화면이 2026 을 끄면 — 그 값이 하나라도 든 짝은 빠진다(전에는 「2026년 행 × 2027년 열」 이 남았다)
    left = [x["key"] for x in p["pairs"] if not off & set(x["div"]["period"] if isinstance(x["div"]["period"], list) else [x["div"]["period"]])]
    assert left == ["2027년|2027년"]
    assert [[(v["part"], v["pairs"], v["fill"]) for v in b["values"]] for b in got] == [[("2026년", 2, 2), ("2027년", 2, 2)]] * 2   # 양쪽에 걸린 짝은 두 값에 다 센다


def _subtotals(vals):
    """한 열에 소계 둘과 합계 — 「인건비 · 재료비 · 소계 · 경비 · 소계 · 합계」(B2~B7)."""
    names = ["인건비", "재료비", "소계", "경비", "소계", "합계"]
    return [(0, 0, 1, 1, SHADE, ["구분"]), (0, 1, 1, 1, SHADE, ["금액"]), *(x for i, n in enumerate(names) for x in ((i + 1, 0, 1, 1, None, [n]), (i + 1, 1, 1, 1, None, [vals[i]])))]


def _rc(cells, **kw):
    s1 = _stage1("t100", cells, 101)
    j = TM.judge(s1, "t100", stored=None, user=None)
    r = KV.recalc(j["table"], j["sem"], j["subs"], **kw)
    return r, {i["ref"]: i for i in r["items"]}


def test_recalc_follows_every_cell_a_value_leans_on():
    r, by = _rc(_subtotals(["10", "20", "999", "40", "40", ""]))          # 소계 B4 = 999(계산은 30) · 소계 B6 = 40(같음) · 합계 B7 = 빈 칸(= B4 + B6)
    sub, total = by["B4"], by["B7"]
    assert (sub["status"], sub["text"], sub["check"]) == ("mismatch", "30", True) and by["B6"]["status"] == "ok"
    assert (total["status"], total["text"], total["formula"], total["check"], total["stale"]) == ("missing", "1,039", "=B4+B6", True, [sub["cell"]]) and "needs" not in total
    assert total["why"] == "기대는 칸 B4 의 지금 값(999)으로 셈했습니다 — B4 는 계산과 다릅니다"   # 지금 값으로 셈한 것 — 확인(처음에는 안 고른다) · 그 칸을 같이 고치면 넣지 않는다
    assert KV.recalc_sig(total) != KV.recalc_sig({**total, "stale": []})
    r, by = _rc(_subtotals(["10", "20", "", "40", "", ""]))               # 소계 둘이 비었으면 — 합계는 그 소계들을 같이 넣을 때의 값
    assert (by["B7"]["status"], by["B7"]["text"], by["B7"]["needs"]) == ("missing", "70", [by["B4"]["cell"], by["B6"]["cell"]]) and "stale" not in by["B7"] and "check" not in by["B7"]
    r, by = _rc(_subtotals(["10", "", "55", "40", "40", ""]))             # 셈하지 못한 소계(더할 칸이 빔)에 값이 있어도 — 그 값으로 합계를 내지 않는다
    assert by["B4"]["status"] == "incomplete" and (by["B7"]["status"], by["B7"]["text"], by["B7"]["value"]) == ("incomplete", "", None) and by["B7"]["why"] == "기대는 칸 B4 를 셈하지 못했습니다"
    # 겹겹이: 지금 값이 다른 칸 P ← 이번에 채울 Q ← 이번에 채울 R / 두 수식이 다른 칸 O(지금 500) ← 그것을 나누는 X
    cells = [_cell("p", 1, 1, "field", "999", num=999.0, dec=0), _cell("q", 2, 1, "field", ""), _cell("r", 3, 1, "field", ""), _cell("o", 1, 2, "field", "500", num=500.0, dec=0), _cell("x", 2, 2, "field", ""),
             _cell("a", 0, 1, "field", "10", num=10.0, dec=0), _cell("b", 0, 2, "field", "20", num=20.0, dec=0)]
    rec = lambda cell, ops, expected, formula, kind="sum", **kw: {"cell": cell, "kind": kind, "formula": formula, "operands": ops, "expected": expected, "status": "missing", "axis": "row", "excel": True, "note": "", **kw}   # noqa: E731
    forms = [rec("p", ["a", "b"], 30, "=B1+C1"), rec("q", ["p", "a"], 1009, "=B2+B1"), rec("r", ["q"], 1009, "=B3"),
             rec("o", ["a"], 100, "=B1*10", kind="expr"), rec("o", ["b"], 110, "=C1*5.5", kind="expr", axis="col", excel=False), rec("x", ["o"], 100, "=C2/5", kind="expr")]
    by = {i["cell"]: i for i in KV.recalc({"cells": cells}, {"formulas": forms})["items"]}
    assert by["p"]["status"] == "mismatch" and (by["q"]["status"], by["q"]["stale"], by["q"]["check"]) == ("missing", ["p"], True) and "needs" not in by["q"]
    assert (by["r"]["status"], by["r"]["needs"], by["r"]["stale"], by["r"]["check"]) == ("missing", ["q"], ["p"], True)       # 거쳐서 기대는 칸까지(소계 → 합계 → 총계)
    assert by["o"]["status"] == "conflict" and (by["x"]["status"], by["x"]["text"], by["x"]["why"]) == ("incomplete", "", "기대는 칸 C2 를 셈하지 못했습니다")   # 두 수식이 다른 칸의 지금 값(500)으로 셈하지 않는다(전에는 100 을 넣을 수 있었다)


def test_recalc_text_is_the_same_number_and_keeps_the_unit():
    code = lambda rows: [(0, 0, 1, 1, SHADE, ["구분"]), (0, 1, 1, 1, SHADE, ["계획(A)"]), (0, 2, 1, 1, SHADE, ["집행(B)"]), (0, 3, 1, 1, SHADE, ["잔액(C=A-B)"]),   # noqa: E731
                         *(x for i, (n, a, b) in enumerate(rows) for x in ((i + 1, 0, 1, 1, None, [n]), (i + 1, 1, 1, 1, None, [a]), (i + 1, 2, 1, 1, None, [b]), (i + 1, 3, 1, 1, None, [""])))]
    r, by = _rc(code([("인건비", "0.0005", "0.0002"), ("재료비", "100천원", "20천원"), ("경비", "100천원", "2백만원"), ("수당", "1,500.5", "500")]))
    assert (by["D2"]["status"], by["D2"]["text"], by["D2"]["value"], by["D2"]["formula"]) == ("missing", "0.0003", 0.0003, "=B2-C2")   # 가장 긴 소수 자리(전에는 「0」)
    assert (by["D3"]["status"], by["D3"]["text"]) == ("missing", "80천원")                                                        # 뒤 글을 지킨다(전에는 「80」)
    assert (by["D4"]["status"], by["D4"]["text"], by["D4"]["why"]) == ("incomplete", "", "단위가 다릅니다(천원 · 백만원)")           # 단위가 다르면 안 넣는다
    assert by["D5"]["text"] == "1,000.5"
    pct = lambda a, b, t: [(0, 0, 1, 1, SHADE, ["구분"]), (0, 1, 1, 1, SHADE, ["비율(%)"]), (1, 0, 1, 1, None, ["인건비"]), (1, 1, 1, 1, None, [a]), (2, 0, 1, 1, None, ["재료비"]), (2, 1, 1, 1, None, [b]),   # noqa: E731
                           (3, 0, 1, 1, None, ["합계"]), (3, 1, 1, 1, None, [t])]
    mix = _rc(pct("10%", "15", ""))[1]["B4"]
    assert (mix["status"], mix["text"], mix["formula"], mix["check"], mix["why"]) == ("missing", "25%", "=SUM(B2:B3)", True, "단위를 적지 않은 수가 섞여 있습니다")   # % 머리글의 합 — 둘 다 더하고, 섞인 것은 확인
    for a, b, t in (("10%", "15%", ""), ("10%", "15%", "00%"), ("10", "15", "00%")):
        one = _rc(pct(a, b, t))[1]["B4"]
        assert (one["status"], one["text"]) == ("missing", "25%") and "check" not in one, (a, b, t)                              # 빈 칸 · 자리표시 「00%」 모두
    # 이 칸의 꼴로 적을 수 없는 값 · 반올림해 0 이 되는 비율
    cells = [_cell("a", 0, 0, "field", "0.0000001", num=1e-07, dec=7), _cell("b", 0, 1, "field", "0.0000002", num=2e-07, dec=7), _cell("s", 0, 2, "field", ""),
             _cell("n", 1, 0, "field", "4", num=4.0, dec=0), _cell("t", 1, 1, "field", "100,000", num=100000.0, dec=0), _cell("q", 1, 2, "field", ""), _cell("h", 2, 2, "field", "00%")]
    rec = lambda cell, ops, expected, formula, kind: {"cell": cell, "kind": kind, "formula": formula, "operands": ops, "expected": expected, "status": "missing", "axis": "row", "excel": True, "note": ""}   # noqa: E731
    by = {i["cell"]: i for i in KV.recalc({"cells": cells}, {"formulas": [rec("s", ["a", "b"], 3e-07, "=SUM(A1:B1)", "sum"), rec("q", ["n", "t"], 0.004, "=A2/B2*100", "ratio"), rec("h", ["n", "t"], 0.004, "=A2/B2*100", "ratio")]})["items"]}
    assert (by["s"]["status"], by["s"]["text"], by["s"]["why"]) == ("incomplete", "", "계산한 값을 이 칸의 꼴로 적을 수 없습니다")   # 7자리 — 6자리까지 늘려도 같은 수가 안 된다
    assert (by["q"]["status"], by["q"]["text"]) == ("missing", "0.004")                                                           # 비율은 2자리까지 — 0 이 되어 버리면 자리를 늘린다
    assert (by["h"]["status"], by["h"]["text"]) == ("missing", "0.004%")                                                          # 자리표시 「00%」 — 뒤 글은 「%」 만


def _set_cell(c, d, tid, cid, text):
    """칸의 글을 고친다(그 칸의 첫 문단 — 보통 글 고침과 같은 길)."""
    pid = next(b["id"] for x in server.DOCS[d].doc.table_block(tid)["cells"] if x["id"] == cid for b in x["blocks"] if b["type"] == "paragraph")
    assert c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": text}).status_code == 200


def test_api_units_and_exact_same_decide_what_is_written(client):
    d = _open(client)
    s = server.DOCS[d]
    kv = {t: client.get(_url(d, t)).json() for t in (CTE_A, CTE_B, CTE_C)}
    k0, k1, k2 = [i["key"] for i in kv[CTE_A]["items"] if i["key"].endswith("|개발연차") and i["empty"] and i["key"] not in kv[CTE_A]["dups"]][:3]
    cell = {t: {i["key"]: i["cell"] for i in v["items"]} for t, v in kv.items()}
    fills = {CTE_A: [("1,200천원", k0), ("700천원", k1), ("60", k2)], CTE_B: [("2백만원", k0), ("40", k2)], CTE_C: [("2백만원", k0), ("500천원", k1), ("100.4", k2)]}
    for t, rows in fills.items():
        assert client.post(f"/api/docs/{d}/tables/{t}/fill/apply", json={"fills": [{"cell": cell[t][k], "text": v} for v, k in rows]}).status_code == 200
    c0, c1, c2 = (cell[CTE_C][k] for k in (k0, k1, k2))
    sums = {"from": [{"table": CTE_A}, {"table": CTE_B}], "mode": "sum"}
    p = client.post(_url(d, CTE_C, "/plan"), json=sums).json()
    by = {x["key"]: x for x in p["pairs"]}
    assert (by[k0]["status"], by[k0]["why"], by[k0]["text"]) == ("nonnum", "단위가 다릅니다(천원 · 백만원)", "")              # 원본 둘의 단위가 다르다 — 더하지 않는다
    assert (by[k2]["status"], by[k2]["text"], by[k2]["was"]) == ("clash", "100", "100.4")                                    # 「40 + 60」 과 「100.4」 — 같음이 아니라 겹침
    r = client.post(_url(d, CTE_C, "/apply"), json={**sums, "cells": [c0, c2], "rev": s.rev, "sigs": {x["to"]: x["sig"] for x in p["pairs"]}})
    assert r.status_code == 409 and (_text(d, CTE_C, c0), _text(d, CTE_C, c2)) == ("2백만원", "100.4")                         # 넣을 칸이 없다 — 문서는 그대로
    t = kv[CTE_C]["type"]
    m = client.put("/api/table-maps", json={"from": {"type": t, "label": "CTE1"}, "to": {"type": t, "label": "CTE3"}, "ops": [{"part": "개발연차", "op": "add"}]}).json()
    one = {"from": {"table": CTE_A}}
    p = client.post(_url(d, CTE_C, "/plan"), json=one).json()
    by = {x["key"]: x for x in p["pairs"]}
    assert (by[k0]["status"], by[k0]["why"]) == ("nonnum", "단위가 다릅니다(백만원 · 천원)")                                   # 「2백만원」 + 「1,200천원」(전에는 「1,202」 를 썼다)
    assert (by[k1]["status"], by[k1]["text"], by[k1]["check"]) == ("fill", "1,200천원", True) and (by[k2]["text"], by[k2]["expr"]) == ("160.4", "= 100.4 + 60")
    rev, undo = s.rev, len(s.undo)
    r = client.post(_url(d, CTE_C, "/apply"), json={**one, "cells": [c0, c1], "rev": rev, "sigs": {x["to"]: x["sig"] for x in p["pairs"]}})
    assert r.status_code == 200, r.text
    mm = r.json()["mapped"]
    assert mm["done"] == [c1] and [(x["cell"], x["why"]) for x in mm["skipped"]] == [(c0, "단위가 다릅니다(백만원 · 천원)")]
    assert (_text(d, CTE_C, c0), _text(d, CTE_C, c1)) == ("2백만원", "1,200천원") and (s.rev, len(s.undo)) == (rev + 1, undo + 1)   # 쓴 글 — 단위가 다른 칸은 그대로 · 같은 단위는 뒤 글을 지켜
    m2 = client.put("/api/table-maps", json={"id": m["id"], "version": m["version"], "from": m["from"], "to": m["to"], "ops": [{"key": k2, "op": "replace"}]})
    assert m2.status_code == 200
    p = client.post(_url(d, CTE_C, "/plan"), json=sums).json()
    over = {x["key"]: x for x in p["pairs"]}[k2]
    assert (over["op"], over["status"], over["text"], over["check"], over["had"]) == ("replace", "fill", "100", True, True)   # 덮어쓰기면 확인이 붙은 넣을 수 있음
    r = client.post(_url(d, CTE_C, "/apply"), json={**sums, "cells": [c2], "rev": s.rev, "sigs": {x["to"]: x["sig"] for x in p["pairs"]}})
    assert r.status_code == 200 and _text(d, CTE_C, c2) == "100"
    _free(s)


def test_api_recalc_does_not_write_a_total_computed_from_a_subtotal_fixed_in_the_same_apply(client):
    d = _open(client)
    s = server.DOCS[d]
    u = lambda tail: _url(d, RECALC_T, f"/recalc{tail}")   # noqa: E731
    blank = [i for i in client.get(_url(d, RECALC_T)).json()["items"] if not i["calc"] and i["empty"]]
    assert client.post(f"/api/docs/{d}/tables/{RECALC_T}/fill/apply", json={"fills": [{"cell": i["cell"], "text": str(10 * (n + 1))} for n, i in enumerate(blank)]}).status_code == 200
    ref = {i["ref"]: i["cell"] for i in client.get(_url(d, RECALC_T)).json()["items"]}
    _set_cell(client, d, RECALC_T, ref["F2"], "999")                    # 줄 합 F2(계산은 30)와 열 합 D6(계산은 220)을 틀리게 — 합의 합 F6(빈 칸)의 두 수식은 둘 다 1,449
    _set_cell(client, d, RECALC_T, ref["D6"], "1189")
    p = client.post(u("/plan")).json()
    by = {i["ref"]: i for i in p["items"]}
    assert (by["F2"]["status"], by["F2"]["text"]) == ("mismatch", "30") and (by["D6"]["status"], by["D6"]["text"]) == ("mismatch", "220")
    f6 = by["F6"]
    assert (f6["status"], f6["text"], f6["formula"], f6["check"], f6["stale"], f6["needs"]) == ("missing", "1,449", "=SUM(F2:F5)", True, [ref["F2"]], [ref["F3"], ref["F4"], ref["F5"]])
    assert "지금 값(999)으로 셈했습니다" in f6["why"]
    sigs = {i["cell"]: i["sig"] for i in p["items"]}
    rev, undo = s.rev, len(s.undo)
    rows = [ref["F3"], ref["F4"], ref["F5"], ref["F6"]]
    r = client.post(u("/apply"), json={"cells": rows, "rev": rev, "sigs": sigs})    # 소계를 안 고치고 사람이 확인해 고른 것 — 지금 값으로 셈한 것을 그대로 쓴다
    assert r.status_code == 200 and r.json()["mapped"]["done"] == rows and _text(d, RECALC_T, ref["F6"]) == "1,449"
    assert client.post(f"/api/docs/{d}/undo").status_code == 200 and _text(d, RECALC_T, ref["F6"]) == ""
    p = client.post(u("/plan")).json()
    sigs = {i["cell"]: i["sig"] for i in p["items"]}
    r = client.post(u("/apply"), json={"cells": [ref["F2"], *rows], "rev": s.rev, "sigs": sigs})   # 소계 F2 를 같이 고치면 — 그 옛 값으로 셈한 F6 은 넣지 않는다
    assert r.status_code == 200, r.text
    m = r.json()["mapped"]
    assert m["done"] == [ref["F2"], ref["F3"], ref["F4"], ref["F5"]] and [x["cell"] for x in m["skipped"]] == [ref["F6"]] and "F2 를 고친 뒤 다시 계산합니다" in m["skipped"][0]["why"]
    assert (_text(d, RECALC_T, ref["F2"]), _text(d, RECALC_T, ref["F5"]), _text(d, RECALC_T, ref["F6"])) == ("30", "210", "")   # 쓴 글 — F6 은 빈 채(전에는 「1,449」 가 들어갔다)
    after = {i["ref"]: i for i in client.post(u("/plan")).json()["items"]}
    assert after["F2"]["status"] == "ok" and after["F6"]["status"] == "conflict" and sorted(x["text"] for x in after["F6"]["both"]) == ["1449", "480"]   # 다시 읽으면 새 값(480)으로 — 열 합 D6 이 아직 틀려(「1189」 — 쉼표 없이 적은 수라 그 꼴대로) 두 수식이 다르다
    _free(s)
