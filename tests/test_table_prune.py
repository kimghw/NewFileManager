"""빈 필드 제거(spec_헤딩_추출 ② §16 · spec_테이블매니저 ② §12): 빈 칸 판정 · 빈 줄(합계·수식 칸 제외) · 행 묶음째 비면 딸린 줄도 · 묶음 제목을 남기는 열 띠 ·
열쇠 칸(구분 기준 · 번호 머리 아래) · 쓴 값 보호(수가 적힌 머리 칸 · 셈 칸의 값 · 목표/실적 쌍) · 빈 서브 테이블째 · 머리만 남은 서브 테이블(저장된 판정과 칸 id 대조) · 표째 · 소속 헤딩 ·
작성 글 보호 · 빈 것으로 본 까닭(spec_테이블매니저 ② §4 「지우거나 쓰는 도구」 ⓐ ⓑ — 합성 레코드) ·
hwpx 지우기(OWPML 검사·다시 열기) · API(미리보기·지우기·실행 취소·409/400·hwpx 만 — 지우기는 미리보기의 rev 를 늘 보낸다)."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_tables as HT
from app import owpml_check as C
from app import server
from app import table_grid as grid
from app import table_prune as P
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL = SAMPLES / "기술수요조사서.hwpx"
DOCX = SAMPLES / "기술수요조사서.docx"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _c(cid, row, col, role="field", text="", rs=1, cs=1, **kw):
    return {"id": cid, "row": row, "col": col, "rs": rs, "cs": cs, "role": role, "textFull": text, "kinds": {}, "nested": [], **kw}


def _tables(blocks, out=None):
    out = [] if out is None else out
    for b in blocks:
        if b["type"] == "table":
            out.append(b)
            for c in b["cells"]:
                _tables(c.get("blocks") or [], out)
    return out


def _find(doc, word, size=None):
    """word 가 든 칸이 있는 첫 표 id — size (행, 열) 을 주면 그 크기의 표만."""
    for b in _tables(doc.blocks()):
        if size and (b["nRows"], b["nCols"]) != size:
            continue
        if any(word in (p.get("text") or "") for c in b["cells"] for p in c.get("blocks") or []):
            return b["id"]
    raise AssertionError(f"「{word}」 표 없음")


# ---- 판정(형식 중립) -------------------------------------------------------------------------------------------------

def test_cell_empty():
    assert P.cell_empty(_c("a", 0, 0)) and P.cell_empty(_c("a", 0, 0, text="  "))
    assert P.cell_empty(_c("a", 0, 0, text="0,000")) and P.cell_empty(_c("a", 0, 0, text="○○"))  # 숫자·이름 자리표시
    assert P.cell_empty(_c("a", 0, 0, text="○○대학교", kinds={"placeholder": 1, "empty": 2}))  # 1단계가 자리표시로 본 글(빈 문단은 세지 않음)
    assert not P.cell_empty(_c("a", 0, 0, text="○○대학교 홍길동 교수", kinds={"placeholder": 1, "plain": 1}))  # 자리표시 줄 아래에 글을 써 넣은 칸은 채워진 칸
    assert P.cell_empty(_c("a", 0, 0, text="0,000", kinds={"data": 1}))  # 수 문단이어도 꼴이 자리표시면 빈 칸
    assert not P.cell_empty(_c("a", 0, 0, text="-")) and not P.cell_empty(_c("a", 0, 0, text="0"))  # 「-」·0 은 값
    assert not P.cell_empty(_c("a", 0, 0, text="o")) and not P.cell_empty(_c("a", 0, 0, text="○"))  # 글머리·체크 한 글자는 값일 수 있다
    assert not P.cell_empty(_c("a", 0, 0, nested=["t9"])) and not P.cell_empty(_c("a", 0, 0, kinds={"object": 1}))  # 칸 안 표·그림


def test_empty_lines_skip_totals_and_headers():
    cells = [_c("h0", 0, 0, "corner", "구분"), _c("h1", 0, 1, "colhead", "1차"), _c("h2", 0, 2, "colhead", "비고"), _c("h3", 0, 3, "colhead", "계", basis=["total"]),
             _c("r1", 1, 0, "rowhead", "인건비"), _c("a1", 1, 1, text="10"), _c("a2", 1, 2), _c("a3", 1, 3, text="10"),
             _c("r2", 2, 0, "rowhead", "재료비"), _c("b1", 2, 1), _c("b2", 2, 2), _c("b3", 2, 3),
             _c("r3", 3, 0, "rowhead", "합계", basisKind="total"), _c("c1", 3, 1), _c("c2", 3, 2), _c("c3", 3, 3)]
    inputs = {"a1", "a2", "b1", "b2", "c1", "c2"}  # 계 열(a3·b3·c3)은 수식 칸 — 채우는 필드가 아니다
    empty = {"a2", "b1", "b2", "c1", "c2"}
    assert P._empty_lines(cells, inputs, empty, 4, "r") == [2]  # 헤더 행·합계 행은 아님
    assert P._empty_lines(cells, inputs, empty, 4, "c") == [2]  # 「비고」 열 — 계 열은 채우는 필드가 없어 대상이 아님
    assert P._names(cells, [2], "r") == {"2": "재료비"} and P._names(cells, [2], "c") == {"2": "비고"}


def test_grow_groups_takes_note_rows_of_an_empty_item():
    # 항목 = 제목(2행에 걸침) + 값 줄 + 안내 줄 — 값이 비면 안내 줄까지 한 묶음으로. 채워진 항목·값 줄이 둘인 묶음은 그대로
    cells = [_c("k1", 0, 0, "rowhead", "과제명", rs=2), _c("v1", 0, 1), _c("n1", 1, 1, "note", "[작성가이드라인]"),
             _c("k2", 2, 0, "rowhead", "필요성", rs=2), _c("v2", 2, 1, text="필요함"), _c("n2", 3, 1, "note", "[작성가이드라인]"),
             _c("k3", 4, 0, "rowhead", "내용", rs=3), _c("v3", 4, 1), _c("n3", 5, 1, "note", "안내"), _c("v4", 6, 1, text="세부 계획")]
    assert P._grow_groups(cells, [0, 4], 7) == [0, 1, 4]  # 「내용」 묶음은 채워진 값 줄(6행)이 있어 4행만


def test_runs_and_band():
    assert P._runs([7, 3, 4, 9, 8]) == [(7, 9), (3, 4)]  # 뒤에서부터
    cells = [grid.Cell(None, 0, 0, 3, 1), grid.Cell(None, 0, 1), grid.Cell(None, 0, 2), grid.Cell(None, 1, 1), grid.Cell(None, 1, 2),
             grid.Cell(None, 2, 1), grid.Cell(None, 2, 2)]
    assert P.band(cells, 3, 1, 2) is None  # 위에서 내려온 칸은 줄어들 뿐
    assert P.band(cells, 3, 0, 1) == (1, 2)  # 0행에서 시작해 2행까지 가는 묶음 제목을 피한 열 띠
    grid.drop_band(cells, 3, 3, 0, 1, 1, 2)
    assert [(x.r, x.c, x.rs) for x in sorted(cells, key=lambda x: (x.r, x.c))] == [(0, 0, 1), (0, 1, 1), (0, 2, 1)]  # 제목은 글째 남고 남은 행으로


# ---- 작성 글 보호 · 빈 것으로 본 까닭(spec_테이블매니저 ② §4 「지우거나 쓰는 도구」 ⓐ ⓑ) — 합성 1단계 레코드(문서 없음 · 실제 문단 분류기 · 실제 초안) --------

BODY = "이 과제는 연안 운항 선박의 항해 안전을 높이기 위한 통합 감시 체계를 설계하고 현장에서 시험한다"  # 54자 — 성격 필드(긴 글)
LABEL = "참여\n연구자\n(기존)"  # 짧은 글 3문단 — 양식의 묶음 제목 꼴(성격은 필드: 문단 3개 이상)


def _table(rows, spans=None, heads=(0,)):
    """글 격자 → `heading_tables.collect` 꼴의 표(역할을 매기기 전). heads 의 행은 음영(머리 행 — 기본 첫 행), 칸 id = 「r<행>c<열>」, 칸 글의 "\\n" 은 문단을 나눈다.
    자리가 None 이면 칸 없음(합친 칸에 덮인 자리) — spans = {(행, 열): (행 병합, 열 병합)}. 재현 스크립트 artifacts/table_manager_astra_2026-11-19/repro_prune_draft.py 와 같은 꼴."""
    rules, run = R.active(copy.deepcopy(EMPTY), (), doc_key=None), R._Run()
    nr, nc = len(rows), len(rows[0])
    tbl = {"t": "tbl", "id": "t1", "rows": nr, "cols": nc, "cells": nr * nc, "key": 1, "host": "x"}
    recs = []
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            if text is None:
                continue
            rs, cs = (spans or {}).get((r, c), (1, 1))
            cell = {"t": "cell", "id": f"r{r}c{c}", "row": r, "col": c, "rs": rs, "cs": cs, "fill": "#D6D6D6" if r in heads else None, "key": 100 + r * nc + c}
            for k, line in enumerate(text.split("\n")):
                head = R.classify(line, rules, run)
                recs.append({"id": f"p{r}_{c}_{k}", "n": len(recs), "path": [tbl, cell], "text": line, "kind": head["kind"], "blank": head["blank"],
                             "char": {"text": {"bold": False}}})
    return next(t for t in HT.collect({"paras": recs}) if t["id"] == "t1")


def _judge(rows, spans=None, roles=None, heads=(0,), history=None, values=None):
    tb = _table(rows, spans, heads)
    return P.analyze_table(tb, "t1", roles, history, values), {x["id"]: x for x in tb["cells"]}


def test_written_text_under_a_header_word_column_is_kept():
    # ㉢ 머리글 「내용」 아래 긴 작성 글 — 헤더 열 낱말 규칙으로 행헤더가 되지만 성격은 필드: 옆 칸이 비어도 그 행은 지울 줄이 아니다
    rows = [["내용", "금액"], ["짧은 제목", "10"], [BODY, ""]]
    a, at = _judge(rows)
    assert (at["r2c0"]["role"], at["r2c0"]["nature"]) == ("rowhead", "field") and at["r2c1"]["role"] == "field"  # 전제 — 초안이 이렇게 본다
    assert (a["fields"], a["emptyFields"]) == (2, 1) and a["emptyRows"] == [] and a["emptyCols"] == [] and a["why"] == {"rows": {}, "cols": {}}
    # 사람이 그 칸을 행헤더로 지정했으면 지정이 먼저 — 전처럼 헤더(그 행은 다시 지울 줄)
    b, _ = _judge(rows, roles={"r2c0": "rowhead"})
    assert b["emptyRows"] == [2] and b["rowNames"] == {"2": BODY[:24]} and b["why"]["rows"] == {"2": []}
    # 짧은 행헤더(성격이 필드가 아닌 글) + 빈 값 행은 전처럼 지울 줄 — 긴 글 행은 값이 있어 그대로
    c, at = _judge([["내용", "금액"], ["짧은 제목", ""], [BODY, "10"]])
    assert (at["r1c0"]["role"], at["r1c0"]["nature"]) == ("rowhead", "text") and c["emptyRows"] == [1] and c["rowNames"] == {"1": "짧은 제목"}


def test_written_text_guards_columns_and_row_groups():
    # 열 쪽 — 「내용」 열의 한 칸을 사람이 필드로 지정(빈 칸)해 그 열이 빈 열 후보가 되어도, 같은 열의 작성 글 칸이 통째로 없어지므로 지울 줄이 아니다
    rows = [["내용", "금액"], ["짧은 제목", "10"], ["", "20"], [BODY, ""]]
    a, at = _judge(rows, roles={"r2c0": "field"})
    assert (at["r3c0"]["role"], at["r3c0"]["nature"]) == ("rowhead", "field") and a["emptyRows"] == [] and a["emptyCols"] == []
    b, _ = _judge(rows, roles={"r2c0": "field", "r3c0": "rowhead"})  # 작성 글 칸을 헤더로 지정하면 보호 없음
    assert b["emptyRows"] == [3] and b["emptyCols"] == []  # 열은 지우지 않는다(2026-11-22 — 값이 든 줄의 빈 칸은 그대로)
    # 행 묶음 — 작성 글 칸(2행에 걸침) + 빈 값 줄 + 딸린 안내 줄: 묶음째 지우면 글이 없어지므로 값 줄도 안내 줄도 지울 줄이 아니다
    rows, spans = [["항목", "내용"], [BODY, ""], [None, "※ 작성 요령: 자세히 적는다"], ["짧은 제목", "적음"]], {(1, 0): (2, 1)}
    a, at = _judge(rows, spans)
    assert (at["r1c0"]["role"], at["r1c0"]["nature"], at["r1c0"]["rs"]) == ("rowhead", "field", 2) and at["r2c1"]["role"] == "note"
    assert a["emptyRows"] == [] and a["emptyCols"] == []
    assert _judge(rows, spans, roles={"r1c0": "rowhead"})[0]["emptyRows"] == [1, 2]  # 지정하면 전처럼 묶음째
    # 묶음 키우기 단위 — 남기는 행(keep)이 낀 묶음은 키우지 않는다
    cells = [_c("k1", 0, 0, "rowhead", "과제명", rs=2), _c("v1", 0, 1), _c("n1", 1, 1, "note", "[작성가이드라인]")]
    assert P._grow_groups(cells, [0], 2) == [0, 1] and P._grow_groups(cells, [0], 2, {1}) == [0]


def test_written_guard_exceptions_ordinals_and_surviving_merged_cells():
    # 순번 칸(「1」·「2」 — 성격은 필드(값)지만 초안이 순번이라서 헤더 열로 본 칸)은 작성 글이 아니다 — 번호 붙은 표의 빈 줄은 전처럼 지울 줄
    a, at = _judge([["번호", "내용", "금액"], ["1", "설계", "10"], ["2", "", ""], ["3", "시험", "5"]])
    assert (at["r2c0"]["role"], at["r2c0"]["nature"]) == ("rowhead", "field") and a["emptyRows"] == [2] and a["rowNames"] == {"2": "2"}
    assert P._written(list(at.values())) == set()
    # 여러 행에 걸친 묶음 제목(짧은 글 3문단 = 성격 필드): 남는 행이 있으면 칸이 줄어들 뿐 글은 남는다 — 빈 사람 줄은 전처럼 지울 줄
    rows, spans = [["구분", "성명", "금액"], [LABEL, "홍길동", "10"], [None, "", ""], ["기타", "이순신", "20"]], {(1, 0): (2, 1)}
    a, at = _judge(rows, spans)
    assert (at["r1c0"]["role"], at["r1c0"]["nature"], at["r1c0"]["rs"]) == ("rowhead", "field", 2) and P._written(list(at.values())) == {"r1c0"}
    assert a["emptyRows"] == [2]
    # 그 칸이 걸친 행이 모두 빈 행이면(칸이 통째로 없어진다) 그 행들은 지울 줄이 아니다 — 헤더로 지정하면 전처럼 묶음째
    rows = [["구분", "성명", "금액"], [LABEL, "", ""], [None, "", ""], ["기타", "이순신", "20"]]
    assert _judge(rows, spans)[0]["emptyRows"] == [] and _judge(rows, spans, roles={"r1c0": "rowhead"})[0]["emptyRows"] == [1, 2]
    # _guard 단위(행·열 같은 규칙) — 걸친 줄이 모두 지울 줄일 때만 그 줄들
    cells = [_c("a", 1, 0, "rowhead", BODY, rs=2, nature="field"), _c("b", 3, 0, "rowhead", BODY, nature="field"), _c("h", 0, 1, "colhead", BODY, cs=2, nature="field")]
    kept = P._written(cells)
    assert kept == {"a", "b", "h"} and P._written(cells, {"a": "rowhead", "h": "colhead", "x": "field"}) == {"b"}
    assert P._guard(cells, kept, [1, 3], 4, "r") == {3} and P._guard(cells, kept, [1, 2], 4, "r") == {1, 2} and P._guard(cells, kept, [], 4, "r") == set()
    assert P._guard(cells, kept, [1], 3, "c") == set() and P._guard(cells, kept, [1, 2], 3, "c") == {1, 2}
    assert P._written([_c("p", 0, 0, "rowhead", "○○", nature="field"), _c("q", 1, 0, "rowhead", "", nature="field"), _c("r", 2, 0, "field", BODY, nature="field"),
                       _c("s", 3, 0, "rowhead", "짧은 제목", nature="text"), _c("t", 4, 0, "note", BODY, nature="field")]) == set()  # 자리표시뿐 · 빈 칸 · 필드 · 성격이 필드가 아닌 글 · 안내


def test_why_names_the_placeholder_text_of_each_empty_line():
    # ㉣ 「00%」 는 자리표시 꼴이라 빈 필드로 보지만 사람이 쓴 값일 수도 있다 — 줄마다 그 글을 싣는다(글이 없는 칸뿐인 줄은 빈 목록)
    a, _ = _judge([["항목", "값"], ["A", "00%"], ["B", "3%"]])
    assert a["emptyRows"] == [1] and a["rowNames"] == {"1": "A"} and a["why"] == {"rows": {"1": ["00%"]}, "cols": {}}
    a, _ = _judge([["항목", "값", "비고"], ["A", "00%", "0,000"], ["B", "3%", "적음"], ["C", "", ""]])
    assert a["emptyRows"] == [1, 3] and a["why"]["rows"] == {"1": ["00%", "0,000"], "3": []}
    a, _ = _judge([["항목", "1차", "2차"], ["A", "10", "000"], ["B", "3", "000"], ["C", "7", ""]])  # 「2차」 열이 자리표시와 빈 칸뿐 — 열은 지우지 않는다(줄마다 값이 있다)
    assert a["emptyRows"] == [] and a["emptyCols"] == [] and a["why"] == {"rows": {}, "cols": {}}
    # 단위 — 칸 차례로 · 중복 없이 · 3개까지 · 빈 필드만(채워진 칸·헤더의 글은 까닭이 아니다) · 합친 칸은 걸친 줄마다
    cells = [_c("h", 0, 0, "rowhead", "재료비"), _c("a", 0, 1, text="00%"), _c("b", 0, 2, text="00%"), _c("c", 0, 3, text="0,000"), _c("d", 0, 4, text="○○"),
             _c("e", 0, 5, text="000"), _c("f", 0, 6, text="12"), _c("g", 1, 1, text="○○", rs=2), _c("i", 2, 2)]
    empty = {"a", "b", "c", "d", "e", "g", "i"}
    assert P._why(cells, empty, [0, 1, 2], "r") == {"0": ["00%", "0,000", "○○"], "1": ["○○"], "2": ["○○"]}
    assert P._why(cells, empty, [2, 6], "c") == {"2": ["00%"], "6": []} and P._why(cells, empty, [], "r") == {}
    assert P.WHY_MAX == 3


# ---- hwpx 문서 -------------------------------------------------------------------------------------------------------

def test_plan_and_apply_small_form():
    d = HwpxDoc(SMALL.read_bytes())
    d.blocks()
    tid = _find(d, "기술수요 과제명")
    p = P.plan(d, tid, store=copy.deepcopy(EMPTY))
    assert (p["rows"], p["cols"]) == (18, 11) and not p["allEmpty"] and p["fields"] > p["emptyFields"] > 0
    assert p["emptyRows"] == [3, 4, 5, 6, 7, 8] and p["skipRows"] == [] and p["emptyCols"] == []  # 빈 항목 셋 — 값 줄 + 딸린 작성가이드라인 줄
    assert p["rowNames"]["3"] == "기술수요 과제명" and p["rowNames"]["5"] == "기술개발의 필요성"
    base = C.counts(C.check_doc(d))
    bad = {**p, "goneCells": p["goneCells"][1:]}   # 미리 본 칸과 지금 칸이 다르면 지우지 않는다(계획 그대로만 — astra 2차)
    with pytest.raises(ValueError):
        P.apply(d, tid, bad)
    out = P.apply(d, tid, p)
    assert out == {"rows": [3, 4, 5, 6, 7, 8], "cols": [], "skipRows": [], "skipCols": [], "bands": [], "skipBands": []}
    b = d.table_block(tid)
    assert b["nRows"] == 12 and not any("기술수요 과제명" in (q.get("text") or "") for c in b["cells"] for q in c.get("blocks") or [])
    assert any("기술내용" in (q.get("text") or "") for c in b["cells"] for q in c.get("blocks") or [])  # 채워진 항목은 그대로
    assert C.verdict(d, base, C.check_doc(d))["status"] != "fail"
    again = HwpxDoc(d.save())  # 저장본이 다시 열린다
    assert again.table_block(_find(again, "기술내용"))["nRows"] == 12
    assert P.plan(d, tid, store=copy.deepcopy(EMPTY))["emptyRows"] == []


def test_plan_blank_form_and_one_cell_box():
    d = HwpxDoc(RND.read_bytes())
    plans = [P.plan(d, b["id"], store=copy.deepcopy(EMPTY)) for b in _tables(d.blocks())]
    assert any(p["allEmpty"] and not p["emptyRows"] and not p["emptyCols"] for p in plans)  # 하나도 안 채운 표는 지울 줄을 정하지 않는다
    assert any(p.get("note", "").startswith("1칸 표") for p in plans)
    assert all(not (set(p["emptyRows"]) & set(p["skipRows"])) for p in plans)
    assert P.plan(d, "p1", store=copy.deepcopy(EMPTY)) is None


def test_apply_keeps_group_header():
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    tid = _find(d, "회수율", (9, 5))  # 성능지표 평가 표(9×5) — 「1 | 회수율」 묶음(1~4행) · 「2 | 정밀도」 묶음(5~8행), 양식은 1~3행만 예시 글
    b = d.table_block(tid)
    assert (b["nRows"], b["nCols"]) == (9, 5)
    at = {(c["row"], c["col"]): c for c in b["cells"]}
    for r in (7, 8):  # 둘째 묶음의 뒤 두 행만 채운다 → 4행(첫 묶음 끝)·5·6행(둘째 묶음 앞)이 빈 행, 둘째 묶음 제목은 5행에서 시작해 8행까지
        d.set_text(at[r, 3]["blocks"][0]["id"], "평가함")
    p = P.plan(d, tid, store=copy.deepcopy(EMPTY))
    assert p["emptyRows"] == [4, 5, 6] and p["skipRows"] == [] and p["emptyCols"] == []
    base = C.counts(C.check_doc(d))
    out = P.apply(d, tid, p)
    assert out == {"rows": [4, 5, 6], "cols": [], "skipRows": [], "skipCols": [], "bands": [], "skipBands": []}
    nb = d.table_block(tid)
    assert nb["nRows"] == 6 and sum(c["rowSpan"] * c["colSpan"] for c in nb["cells"]) == 6 * 5  # 구멍·겹침 없음
    by_text = {" ".join(q.get("text") or "" for q in c.get("blocks") or []).split(" ")[0]: c for c in nb["cells"]}
    assert by_text["회수율"]["rowSpan"] == 3 and (by_text["정밀도"]["row"], by_text["정밀도"]["rowSpan"]) == (4, 2)  # 묶음 제목은 글째 남고 남은 행으로
    assert C.verdict(d, base, C.check_doc(d))["status"] != "fail"
    HwpxDoc(d.save())


def test_plan_keeps_pruning_rows_under_a_multi_paragraph_group_title():
    # 참여 연구자 표(12×11) — 묶음 제목 「참여 / 연구자 / (기존)」 은 짧은 글 3문단이라 성격이 필드인 행헤더(작성 글 보호의 대상)지만 여러 행에 걸친 칸:
    # 빈 사람 줄을 지워도 제목은 남은 행으로 줄어들 뿐이라 그 줄은 전처럼 지울 줄이다(걸친 행을 다 막으면 [] 가 된다 — 2026-11-19 이 양식에서 잼)
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    p = P.plan(d, _find(d, "참여", (12, 11)), store=copy.deepcopy(EMPTY))
    assert p["emptyRows"] == [4, 7] and p["skipRows"] == [] and p["rowNames"] == {"4": "참여 연구자 (기존)", "7": "참여 연구자 (신규)"}
    assert p["emptyCols"] == [] and p["why"] == {"rows": {"4": [], "7": []}, "cols": {}}  # 빈 열(급여총액 · 참여기간 · 계상률)은 지우지 않는다


def test_empty_columns_are_not_pruned():
    # 2026-11-22 사용자 "빈 필드란느건.... 빈 칸만 이야기 하는게 아니고 … 입력해야할 행을 이야기 하는거야" — 빈 열(속성)은 지우지 않는다(전에는 「예 · 아니오」 두 열을 지웠다)
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    tid = _find(d, "보안등급 분류", (7, 4))  # 번호 | 분류 | 점검 결과(예 · 아니오 — 빈 열 둘)
    b = d.table_block(tid)
    p = P.plan(d, tid, store=copy.deepcopy(EMPTY))
    assert p["emptyCols"] == [] and p["colNames"] == {} and p["skipCols"] == []
    assert P.apply(d, tid, p)["cols"] == [] and d.table_block(tid)["nCols"] == b["nCols"]


# ---- 열쇠 칸 · 쓴 값 보호 · 서브 테이블 · 표째(spec_테이블매니저 ② §12) --------------------------------------------------

KEYED = [["연구개발기관", "연도", "용역명", "금액"], ["한국선급", "2027", "자료 정리", "100"], ["한국선급", "2028", "", ""], ["서울대학교", "2027", "", ""]]
VALUES = {"stages": [2], "orgs": {"lead": "한국선급", "joint": ["서울대학교"]}, "period": {"start": "2027-01-01", "end": "2028-12-31"}}


def test_division_key_cells_are_not_inputs():
    # 사용자 "구분기준, 구역이 되는 필드는 열 또는 행 헤더로봐야지 .. 입력하는 값이 아니니깐" — 「연도」 아래 칸(초안은 필드)의 글이 프로젝트 구성의 해(사업기간)면 줄의 열쇠: 그 칸만 든 줄은 빈 줄
    a, at = _judge(KEYED, values=VALUES)
    assert at["r2c1"]["role"] == "field" and a["keys"] == 3 and a["emptyRows"] == [2, 3] and not a["tableGone"]
    assert _judge(KEYED)[0]["keys"] == 0 and _judge(KEYED)[0]["emptyRows"] == []   # 프로젝트 구성이 없으면(일반 문서) 기관 · 연도 열쇠는 없다
    late = [list(r) for r in KEYED]
    late[2][1] = "2031"   # 사업기간 밖의 해 — 그 칸은 쓴 값
    assert _judge(late, values=VALUES)[0]["emptyRows"] == [3]
    for head in ("구축연도", "해당연도"):  # 속성 머리(낱말 그대로가 아님) — 그 아래 칸은 입력값이라 줄이 채워져 있다
        rows = [list(r) for r in KEYED]
        rows[0][1] = head
        assert _judge(rows, values=VALUES)[0]["emptyRows"] == [] and _judge(rows, values=VALUES)[0]["keys"] == 0
    assert _judge(KEYED, roles={"r2c1": "field", "r3c1": "field"}, values=VALUES)[0]["emptyRows"] == []  # 사람이 필드로 지정한 칸은 입력값
    # 열쇠뿐인 표(열쇠 열 말고 입력 칸이 없음)의 열쇠는 그 자체가 쓴 값이다
    assert _judge([["연구개발기관", "연도"], ["한국선급", "2027"], ["서울대학교", ""]], values=VALUES)[0]["keys"] == 0
    # 속성 열의 기관 이름(구성에 없는 이름 — astra 2차 반례 「신청자 | 직책 | 기관」)은 쓴 값
    a, _ = _judge([["신청자", "직책", "기관", "비고"], ["갑", "", "", "작성 완료"], ["을", "", "새봄병원", ""]], values=VALUES)
    assert a["emptyRows"] == []
    # 모든 입력 칸이 비면(열쇠만 채움) 표째 — 줄은 정하지 않고 tableGone 만(사람이 확인해 고른다)
    a, _ = _judge([KEYED[0], ["한국선급", "2027", "", ""], ["서울대학교", "2027", "", ""]], values=VALUES)
    assert a["allEmpty"] and a["tableGone"] and a["drop"] == [0, 1, 2]
    assert P._time_value("1단계-2차년도", VALUES) and not P._time_value("3차년도", VALUES) and P._time_value("2028년", VALUES) and not P._time_value("2029", VALUES)
    assert P._time_value("2차 (1단계)", VALUES) and not P._time_value("2차 (2단계)", VALUES)   # 차년도가 앞인 꼴(연구개발계획서 「연차 (단계)」 열)
    assert P._org_value("㈜ 한국선급", P._key_names(VALUES)) and not P._org_value("한국선급엔지니어링", P._key_names(VALUES))
    assert P._key_head("연구개발 기관명15)") == "org" and P._key_head("차년도") == "time" and P._key_head("발행기관") is None and P._key_head("소속기관명") is None
    assert P._in_order([_c("a", 1, 0, text="1"), _c("b", 2, 0, text="2."), _c("c", 3, 0)]) and not P._in_order([_c("a", 1, 0, text="2"), _c("b", 2, 0, text="1")])


def test_written_numbers_totals_and_pairs_are_kept():
    # 음영 때문에 머리로 읽힌 금액(astra 가 t9199 에서 재현 — 그 줄을 지우면 수 세 칸이 없어짐)은 쓴 값 · 구분 기준 값(basis)과 순번은 아님
    cells = [_c("x", 0, 0, "rowhead", "24,000", nature="header"), _c("y", 1, 0, "rowhead", "2026", nature="header", basis=["period"]),
             _c("z", 2, 0, "rowhead", "1", nature="header"), _c("w", 3, 0, "rowhead", "-", nature="header")]
    assert P._written(cells) == {"x"}
    # 순번은 같은 열에서 1, 2, 3 … 차례일 때만 — 「수량 | 금액」 의 「10」(꼴은 순번)은 쓴 값 · 체크 표시도 쓴 값(astra 2차)
    assert P._written([_c("q", 1, 0, "rowhead", "10", nature="field"), _c("v", 1, 1)]) == {"q"}
    assert P._written([_c("o1", 1, 0, "rowhead", "1", nature="field"), _c("o2", 2, 0, "rowhead", "2", nature="field")]) == set()
    assert P._written([_c("k", 0, 0, "rowhead", "☑", nature="header")]) == {"k"}
    # 셈 칸(합계)에 값이 적히면 그 줄은 채워진 줄 — 피연산자가 비어도(수기 합계) · 「0」 · 「-」 도(양식의 기본값이라는 근거가 없다 — astra 2차)
    assert P._hand(_c("t", 0, 0, text="70")) and P._hand(_c("t", 0, 0, text="0")) and P._hand(_c("t", 0, 0, text="-")) and not P._hand(_c("t", 0, 0)) and not P._hand(_c("t", 0, 0, text="0,000"))
    row = [_c("h", 0, 0, "rowhead", "A"), _c("a", 0, 1), _c("b", 0, 2), _c("t", 0, 3, text="70")]
    assert P._empty_lines(row, {"a", "b"}, {"a", "b"}, 1, "r") == [0] and P._empty_lines(row, {"a", "b"}, {"a", "b"}, 1, "r", {"t"}) == []
    # 목표 · 실적 쌍 — 한 행이라도 남으면 쌍째 남긴다 · 다른 낱말 묶음은 행마다
    cells = [_c("p", 0, 0, "rowhead", "2027", rs=2), _c("k1", 0, 1, "rowhead", "목표"), _c("k2", 1, 1, "rowhead", "실적")]
    assert P._pairs(cells, [0]) == [] and P._pairs(cells, [0, 1]) == [0, 1] and P._pairs(cells, [1, 5]) == [5]
    cells[1]["textFull"] = "인건비"
    assert P._pairs(cells, [0]) == [0]


def test_empty_sub_table_goes_with_its_header_rows():
    # 사용자 "이게 서브 테이블이면 그 섭테이블에 필드가 없으면 삭제" — 입력 줄이 모두 빈 띠는 머리 행까지 띠째(지우기 전 표의 띠로 본다)
    rows = [["구분", "내용", "비고"], ["과제명", "자율운항", "있음"], ["등록 건수", "논문", "특허"], [None, "", ""]]
    a, at = _judge(rows, spans={(2, 0): (2, 1)}, heads=(0, 2))
    assert at["r2c0"]["sub"] != at["r1c0"]["sub"]  # 전제 — 머리 행이 다시 와서 새 띠
    assert a["emptyRows"] == [3] and a["drop"] == [2, 3] and [(b["rows"], b["name"], b["how"]) for b in a["bands"]] == [([2, 3], "등록 건수", "empty")] and not a["tableGone"]
    # 그 띠에 값이 하나라도 있으면 띠는 남고 빈 줄도 없다
    rows[3][1] = "2"
    assert _judge(rows, spans={(2, 0): (2, 1)}, heads=(0, 2))[0]["drop"] == []


def test_orphan_sub_table_is_matched_with_the_saved_judgement():
    # 이미 머리만 남은 서브 테이블(사용자 그림 — 값 행만 지워 머리 행만 남음): 저장된 3단계 판정(지우기 전)의 띠와 칸 id 로 대조해서만 찾는다
    tb = {"id": "t1", "rows": 2, "cols": 2, "cells": [_c("k", 0, 0, "rowhead", "과제명"), _c("v", 0, 1, text="자율운항"),
                                                       _c("h1", 1, 0, "corner", "등록 건수"), _c("h2", 1, 1, "colhead", "논문")]}
    saved = {"id": "t1", "subtables": [{"id": "A", "rows": [0, 1], "cols": [0, 2], "kind": "form"}, {"id": "B", "rows": [1, 3], "cols": [0, 2], "kind": "matrix"}],
             "cells": [{"id": "k", "row": 0, "col": 0, "role": "rowhead", "text": "과제명"}, {"id": "v", "row": 0, "col": 1, "role": "field", "text": ""},
                       {"id": "h1", "row": 1, "col": 0, "role": "corner", "text": "등록 건수21)"}, {"id": "h2", "row": 1, "col": 1, "role": "colhead", "text": "논문"},
                       {"id": "f1", "row": 2, "col": 1, "role": "field", "draft": "field", "text": ""}]}
    got = P.orphans(tb, saved)
    assert [(o["rows"], o["how"], o["heads"]) for o in got] == [([1, 1], "orphan", ["h1", "h2"])]   # 각주 번호(「21)」)만 다른 글은 같은 글
    assert P.orphans(tb, {**saved, "id": "t2"}) == [] and P.orphans(tb, None) == []
    changed = copy.deepcopy(tb)
    changed["cells"][3]["textFull"] = "논문 (건)"   # 사람이 고친 머리 — 짐작하지 않는다
    assert P.orphans(changed, saved) == []
    more = copy.deepcopy(tb)
    more["cells"].append(_c("n", 1, 1, "field", "새 글"))   # 그 행에 다른 칸 — 아님
    more["cells"][3]["col"], more["cols"] = 2, 3
    assert P.orphans(more, saved) == []
    alive = copy.deepcopy(saved)
    alive["cells"][4]["id"] = "v"   # 그 띠의 입력 칸이 지금도 있다 — 아님
    assert P.orphans(tb, alive) == []
    long = copy.deepcopy(saved)   # 저장 글이 잘렸으면(TEXT_MAX) 뒤에 덧붙인 글을 알 수 없다 — 짐작하지 않는다(astra 2차)
    long["cells"][3]["text"] = "가" * 80
    cut = copy.deepcopy(tb)
    cut["cells"][3]["textFull"] = "가" * 80 + " 새로 입력한 검토 결과"
    assert P.orphans(cut, long) == []
    other = copy.deepcopy(saved)   # 각주 번호가 다른 글(「차수1)」 ↔ 「차수2)」)은 다른 글
    other["cells"][3]["text"], same = "차수1)", copy.deepcopy(tb)
    same["cells"][3]["textFull"] = "차수2)"
    assert P.orphans(same, other) == []
    # 겹치는 띠(지금 판정의 빈 띠 + 저장된 판정의 머리만 남은 띠)는 하나로 — 따로 두면 같은 자리를 두 번 지운다(astra 2차)
    merged = P._merge([{"sub": "B", "rows": [2, 3], "name": "가", "how": "empty", "recs": [3]}, {"sub": "E", "rows": [2, 2], "name": "가", "how": "orphan", "heads": ["h"], "recs": []},
                       {"sub": "F", "rows": [5, 5], "name": "나", "how": "orphan", "heads": ["k"], "recs": []}])
    assert [(m["rows"], m["how"]) for m in merged] == [([2, 3], "empty"), ([5, 5], "orphan")]


def _graph(tid, head_para, next_para, child=False, text=None, next_text=None):
    """2단계 그래프 꼴(헤딩 두 개 + 표 그릇) — head_para 헤딩 바로 아래 표 tid, 그 뒤 next_para 헤딩(child = 그 헤딩이 첫 헤딩의 하위)."""
    return {"nodes": [{"id": "H1", "para": head_para, "role": "heading", "letter": "", "text": text, "parent": "root"},
                      {"id": "H2", "para": next_para, "role": "heading", "letter": "", "text": next_text, "parent": "H1" if child else "root"}],
            "containers": [{"id": f"tbl:{tid}", "kind": "table", "parent": "H1"}]}


def test_table_scope_takes_the_heading_only_when_it_holds_just_this_table():
    # 사용자 "이 테이블의 소속 헤딩이 있고 .. 그 헤딩의 테이블 이였다면 그 헤딩까지 삭제" — 그래프가 바로 그 헤딩 아래에 둔 표 · 헤딩 ~ 표 사이 빈 줄뿐 · 뒤가 하위 헤딩이 아님
    d = HwpxDoc(RND.read_bytes())
    top = d.blocks()
    tid = _find(d, "취득연월", (4, 5))   # 「나. 학력」 바로 아래의 빈 표
    i = next(k for k, b in enumerate(top) if b["id"] == tid)
    head = top[i - 1]
    nxt = next(b for b in top[i + 1:] if b["type"] != "paragraph" or (b.get("text") or "").strip())
    assert head["type"] == "paragraph" and "학력" in head["text"] and nxt["type"] == "paragraph"
    p = P.plan(d, tid, store=copy.deepcopy(EMPTY))
    assert p["tableGone"] and p["emptyRows"] == []   # 빈 양식의 표 — 표째(줄은 정하지 않음)
    sc = P.table_scope(d, tid, _graph(tid, head["id"], nxt["id"], text=head["text"], next_text=nxt["text"]))
    assert sc["first"] == head["id"] and sc["last"] == tid and sc["heading"]["text"] == " ".join(head["text"].split()) and not sc["block"]
    assert P.table_scope(d, tid, _graph(tid, head["id"], nxt["id"], child=True, text=head["text"], next_text=nxt["text"]))["heading"] is None   # 뒤 헤딩이 하위 — 헤딩은 남김
    assert P.table_scope(d, tid, _graph(tid, head["id"], nxt["id"], text="다른 제목", next_text=nxt["text"]))["heading"] is None              # 헤딩 글이 판정 때와 다름
    assert P.table_scope(d, tid, _graph(tid, head["id"], nxt["id"], text=head["text"], next_text="옛 제목"))["heading"] is None   # 뒤 헤딩이 지금은 다른 글(본문이 됨) — 확인 못 함(astra 2차)
    assert "판정" in P.table_scope(d, tid, None)["why"] and P.table_scope(d, tid, None)["first"] == tid
    base = C.counts(C.check_doc(d))
    P.drop_table(d, sc)
    assert tid not in d._ids or not d._attached(d._ids[tid])
    assert not d._attached(d._ids[head["id"]]) and d._attached(d._ids[nxt["id"]])   # 헤딩까지 · 다음 헤딩은 남음
    assert C.verdict(d, base, C.check_doc(d))["status"] != "fail"
    HwpxDoc(d.save())


# ---- API -------------------------------------------------------------------------------------------------------------

def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


@pytest.fixture()
def client():
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def test_api_prune_dry_apply_undo(client):
    d = _upload(client, SMALL)
    tbs = _tables(client.get(f"/api/docs/{d}").json()["blocks"])
    big = max(tbs, key=lambda b: b["nRows"])
    url = f"/api/docs/{d}/tables/{big['id']}/prune"
    dry = client.post(url, json={"dry": True})
    assert dry.status_code == 200, dry.text
    p = dry.json()
    assert p["emptyRows"] == [3, 4, 5, 6, 7, 8] and p["rev"] == client.get(f"/api/docs/{d}").json()["rev"] and p["action"] == "rows" and p["planId"]
    assert client.get(f"/api/docs/{d}").json()["pristine"] is True  # 미리보기는 문서를 안 바꾼다
    assert p["why"] == {"rows": {str(i): [] for i in p["emptyRows"]}, "cols": {}}  # 빈 것으로 본 까닭 — 이 표의 빈 필드는 글이 없는 칸뿐(자리표시 글 없음)
    go = {"action": "rows", "planId": p["planId"], "rev": p["rev"]}
    assert client.post(url, json={**go, "rev": p["rev"] + 5}).status_code == 409  # 미리 본 뒤 문서가 바뀜
    assert client.post(url, json={**go, "planId": "0" * 16}).status_code == 409   # 미리 본 계획과 다름(헤더 지정이 바뀌면 rev 는 그대로라 이것으로 견준다)
    assert client.post(url, json={**go, "action": "table"}).status_code == 409    # 계획의 동작과 다름
    assert client.post(url, json={"rows": True, "rev": p["rev"]}).status_code == 400  # 옛 요청(planId 없음) — 다른 지우기를 성공으로 받지 않게
    assert client.post(url, json={**go, "cols": True}).status_code == 400            # 빈 열 지우기는 없앴다
    assert client.post(url, json={**go, "action": "cols"}).status_code == 400
    assert client.get(f"/api/docs/{d}").json()["pristine"] is True
    r = client.post(url, json=go)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["pruned"] == {"table": big["id"], "tableDeleted": False, "heading": None, "rows": [3, 4, 5, 6, 7, 8], "cols": [], "skipRows": [], "skipCols": [],
                           "bands": [], "skipBands": []} and v["undo"] == 1
    now = next(b for b in v["tops"]["blocks"] if b["id"] == big["id"])
    assert now["nRows"] == big["nRows"] - 6
    after = client.post(url, json={"dry": True}).json()
    assert after["emptyRows"] == [] and after["action"] is None
    assert client.post(url, json={"action": "rows", "planId": after["planId"], "rev": after["rev"]}).status_code == 400  # 더 지울 줄이 없다(계획의 동작이 없음)
    assert client.post(f"/api/docs/{d}/undo").status_code == 200
    back = client.get(f"/api/docs/{d}").json()
    assert back["pristine"] is True and max(_tables(back["blocks"]), key=lambda b: b["nRows"])["nRows"] == big["nRows"]
    assert client.post(f"/api/docs/{d}/tables/t9999/prune", json={"dry": True}).status_code == 404
    assert [e["kind"] for e in client.get(f"/api/works/{d}/log").json()["events"]].count("tablePrune") == 1


def test_api_prune_whole_table(client):
    # 지우면 입력 줄이 하나도 안 남는 표 — 미리보기가 표째(action table)를 내고, 확인한 지우기는 문서 전체 검사 한 트랜잭션 · 실행 취소 1개
    d = _upload(client, RND)
    tbs = _tables(client.get(f"/api/docs/{d}").json()["blocks"])
    tid = next(b["id"] for b in tbs if (b["nRows"], b["nCols"]) == (4, 5) and any("취득연월" in (q.get("text") or "") for c in b["cells"] for q in c.get("blocks") or []))
    url = f"/api/docs/{d}/tables/{tid}/prune"
    p = client.post(url, json={"dry": True}).json()
    assert p["action"] == "table" and p["tableGone"] and p["emptyRows"] == [] and p["scope"]["first"] == tid and p["scope"]["heading"] is None  # 헤딩 판정 없음 — 표까지만
    assert client.post(url, json={"action": "rows", "planId": p["planId"], "rev": p["rev"]}).status_code == 409
    r = client.post(url, json={"action": "table", "planId": p["planId"], "rev": p["rev"]})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["pruned"]["tableDeleted"] is True and v["undo"] == 1
    assert tid not in {b["id"] for b in _tables(client.get(f"/api/docs/{d}").json()["blocks"])}
    assert client.post(f"/api/docs/{d}/undo").status_code == 200
    assert tid in {b["id"] for b in _tables(client.get(f"/api/docs/{d}").json()["blocks"])}
    assert [e["kind"] for e in client.get(f"/api/works/{d}/log").json()["events"]].count("tablePrune") == 1


def test_api_prune_docx_is_hwpx_only(client):
    d = _upload(client, DOCX)
    doc = client.get(f"/api/docs/{d}").json()
    tb = _tables(doc["blocks"])[0]
    for body in ({"dry": True}, {"action": "rows", "planId": "x", "rev": doc["rev"]}):
        r = client.post(f"/api/docs/{d}/tables/{tb['id']}/prune", json=body)
        assert r.status_code == 400 and "hwpx" in r.json()["detail"]
