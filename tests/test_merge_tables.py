"""표 안 연결 + 표 칸 넣기(spec_병합 ② §0 자리 두 갈래 · §5 · §6) — app/merge_tables.py. 저장소 자료(small)로: 원본(빈 계획서 양식)에 시험이 칸 글을 넣고 계획 → 반영 → 다시 계획."""
import pytest

import merge_data as M
from app import hwpx_struct
from app import merge_pairs as P
from app import owpml_check
from app import merge_tables as MT
from app.hwpx_doc import HwpxDoc


@pytest.fixture(scope="module")
def small():
    d = M.small()
    s = {side: P.summarize(d[side]["doc"].blocks(), d[side]["graph"], d[side]["tables"], d["values"]) for side in ("to", "from")}
    return d, P.pair(s["to"], s["from"])


def _fresh(side):
    """독립 사본 — 블록 id 는 읽을 때 붙으므로 한 번 읽어 둔다(table_block 이 id 로 찾게)."""
    doc = M.fresh(side)
    doc.blocks()
    return doc


def _run(d, pairs, src, tgt):
    return MT.plan({**d["to"], "doc": tgt}, {**d["from"], "doc": src}, d["values"], d["values"], pairs)


def _cells(doc, tid):
    return doc.table_block(tid)["cells"]


def _at(doc, tid, row, col):
    return next(c for c in _cells(doc, tid) if c["row"] == row and c["col"] == col)


def _col(doc, tid, prefix):
    return next(c["col"] for c in _cells(doc, tid) if (c["text"] or "").replace(" ", "").startswith(prefix))


def _mine(p, g):
    return [c for c in p["cells"] if c["group"] == g["id"]], [r for r in p["rows"] if r["group"] == g["id"]], [s for s in p["skipped"] if s["group"] == g["id"]]


def test_fixed_year_rows_by_header_with_calc_occupied_and_idempotent(small):
    """표지 연구개발비 연차 행(정해진 자리): 같은 차년도 행끼리 열 머리 꼴로 칸 글을 옮긴다 — 열 수가 다른 두 표(32 · 30열)에서도. 합계 열은 같은 행의 합이라 calc 로 옮기고,
    사람이 쓴 칸은 덮지 않으며(occupied), 반영 뒤 다시 계획하면 할 일이 없다."""
    d, pairs = small
    g = next(g for g in pairs["groups"] if g["status"] == "paired" and g["kind"] == "rows" and g["dim"] == "year" and g["to"]["label"] == "차년도" and not g["to"]["path"])
    src, tgt = _fresh(d["from"]), _fresh(d["to"])
    ft, tt = g["from"]["table"], g["to"]["table"]
    lab = next(c for c in _cells(src, ft) if c["id"] == g["items"][0]["from"]["id"])   # 원본 1차년도 행
    filled = {}
    for k, c in enumerate(sorted((c for c in _cells(src, ft) if c["row"] == lab["row"] and c["col"] > lab["col"]), key=lambda c: c["col"]), 1):
        src.set_text(c["id"], f"{k},000")
        filled[c["id"]] = f"{k},000"
    trow = next(c for c in _cells(tgt, tt) if c["id"] == g["items"][0]["to"]["id"])["row"]
    gov_t, gov_f = _col(tgt, tt, "정부지원"), _col(src, ft, "정부지원")
    mine = next(c for c in _cells(tgt, tt) if c["row"] == trow and c["col"] > gov_t)   # 사람이 쓴 칸
    tgt.set_text(mine["id"], "999")
    p = _run(d, pairs, src, tgt)
    cells, rows, skipped = _mine(p, g)
    assert cells and not rows and all(c["text"] == filled[c["from"]] for c in cells)
    assert {_at(tgt, tt, trow, gov_t)["id"]: filled[_at(src, ft, lab["row"], gov_f)["id"]]}.items() <= {c["to"]: c["text"] for c in cells}.items()   # 정부지원 열 ↔ 정부지원 열
    assert any(c["calc"] for c in cells)   # 「총 연구개발비 › 현금」 = 같은 행 현금 칸의 합 — 피연산자가 모두 이어져 옮김
    assert [(s["why"], s["to"]) for s in skipped if s["why"] == "occupied"] == [("occupied", mine["id"])]
    r = MT.apply(tgt, src, {**p, "cells": cells, "rows": rows})   # 이 묶음 몫만(양식 예시가 든 다른 표도 계획에 있다)
    assert r["filled"] == len(cells) and _at(tgt, tt, trow, gov_t)["text"] == filled[_at(src, ft, lab["row"], gov_f)["id"]]
    assert _at(tgt, tt, trow, mine["col"])["text"] == "999"
    again = _run(d, pairs, src, tgt)
    assert not _mine(again, g)[0] and not _mine(again, g)[1]


def test_year_columns_all_years_by_row_header(small):
    """기관별 사용계획 총괄표(차년도 열 묶음 — 전 차년도 열): 열마다 같은 차년도 열로, 행은 행 머리 꼴(「직접비 › 인건비 › 내부인건비 › 현금」)로."""
    d, pairs = small
    g = next(g for g in pairs["groups"] if g["status"] == "paired" and g["kind"] == "cols" and (g["ctx"] or {}).get("org") == "인텍")
    src, tgt = _fresh(d["from"]), _fresh(d["to"])
    ft, tt = g["from"]["table"], g["to"]["table"]
    ycols = {(next(c for c in _cells(src, ft) if c["id"] == it["from"]["id"])["col"], next(c for c in _cells(tgt, tt) if c["id"] == it["to"]["id"])["col"])
             for it in g["items"]}
    for fc, _ in ycols:
        for c in _cells(src, ft):
            if c["col"] == fc and c["row"] >= 2:
                src.set_text(c["id"], f"{c['row']}{fc}0")
    p = _run(d, pairs, src, tgt)
    cells, _, skipped = _mine(p, g)
    assert len(cells) >= 20 * len(ycols) and not [s for s in skipped if s["why"] in ("shape", "ambiguous")]
    tby, sby = {c["id"]: c for c in _cells(tgt, tt)}, {c["id"]: c for c in _cells(src, ft)}
    assert all((sby[c["from"]]["col"], tby[c["to"]]["col"]) in ycols and sby[c["from"]]["row"] == tby[c["to"]]["row"] for c in cells)   # 같은 차년도 열 · 같은 비목 행(두 표 꼴이 같음)


def test_list_rows_pair_by_org_name_not_position(small):
    """표지 공동연구개발기관 목록 행: 원본 행의 차례가 달라도(다라연 → 가나대) 기관 이름으로 잇는다 — 이름 칸 자신은 옮기지 않는다."""
    d, pairs = small
    g = next(g for g in pairs["groups"] if g["status"] == "paired" and g["kind"] == "list" and not g["to"]["path"])
    src, tgt = _fresh(d["from"]), _fresh(d["to"])
    ft, tt = g["from"]["table"], g["to"]["table"]
    name_f, name_t = (_col(doc, t, "기관명") for doc, t in ((src, ft), (tgt, tt)))
    boss_f, boss_t = (_col(doc, t, "책임자") for doc, t in ((src, ft), (tgt, tt)))
    rows = sorted({c["row"] for c in _cells(src, ft) if c["col"] == name_f and c["text"] in ("가나대", "다라연")})
    for r, (name, boss) in zip(rows, (("다라연", "박다라"), ("가나대", "김가나"))):   # 원본 차례를 뒤집음
        src.set_text(_at(src, ft, r, name_f)["id"], name)
        src.set_text(_at(src, ft, r, boss_f)["id"], boss)
    p = _run(d, pairs, src, tgt)
    cells, _, _ = _mine(p, g)
    got = {c["to"]: c["text"] for c in cells}
    for name, boss in (("가나대", "김가나"), ("다라연", "박다라")):
        r = next(c["row"] for c in _cells(tgt, tt) if c["col"] == name_t and c["text"] == name)
        assert got.get(_at(tgt, tt, r, boss_t)["id"]) == boss
    assert not any(c["text"] in ("가나대", "다라연") for c in cells)


def test_append_org_year_rows_reuse_blank_then_add_and_idempotent(small):
    """세부 사용계획 기관-연도 행 표(이어 넣는 자리): 목적 「다음 연도」 자리(2차년도 = 2027)에 원본 같은 기관 · 같은 해의 행만, 원본 차례대로 — 빈 행을 먼저 쓰고 모자란 행은 늘린다.
    1차년도 행은 안 가져오고, 원본 행이 없는 기관은 noSource, 반영 뒤 다시 계획하면 할 일이 없다. 늘린 문서는 저장해 다시 열 수 있다."""
    d, pairs = small
    src, tgt = _fresh(d["from"]), _fresh(d["to"])
    g = next(g for g in pairs["groups"] if g["status"] == "paired" and g["kind"] == "rows" and any(c["row"] == 0 and c["text"] == "연구재료" for c in _cells(src, g["from"]["table"]))
             and any(c["text"] == "변동여부*" for c in _cells(tgt, g["to"]["table"])))
    ft, tt = g["from"]["table"], g["to"]["table"]
    org_rows = [c for c in _cells(src, ft) if c["col"] == 0 and c["text"] == "가나대"][0]
    y26, y27 = org_rows["row"], org_rows["row"] + 1
    assert _at(src, ft, y27, 1)["text"] == "2027"
    ncol = max(c["col"] for c in _cells(src, ft))
    for col in range(2, ncol + 1):
        src.set_text(_at(src, ft, y26, col)["id"], f"옛것{col}")
        src.set_text(_at(src, ft, y27, col)["id"], f"가{col}")
    m = src.clone_rows(ft, y27, y27, [2, ncol], keep_text=False)["map"]   # 원본 2027 덩이를 두 행으로
    for col in range(2, ncol + 1):
        src.set_text(m[_at(src, ft, y27, col)["id"]], f"나{col}")
    p = _run(d, pairs, src, tgt)
    cells, rows, skipped = _mine(p, g)
    trow = next(c for c in _cells(tgt, tt) if c["col"] == 0 and c["text"] == "가나대")["row"]
    assert sorted(c["text"] for c in cells) == sorted(f"가{c}" for c in range(2, ncol + 1)) and {_at(tgt, tt, trow, 2)["id"]} <= {c["to"] for c in cells}
    assert len(rows) == 1 and sorted(x["text"] for x in rows[0]["cells"]) == sorted(f"나{c}" for c in range(2, ncol + 1))
    assert not any("옛것" in c["text"] for c in cells + [x for r in rows for x in r["cells"]])
    assert {s["item"] for s in skipped if s["why"] == "noSource"} == {"주관 · 2차년도", "공동2 · 2차년도"}
    r = MT.apply(tgt, src, {**p, "cells": cells, "rows": rows})
    assert r["rowsAdded"] == 1 and r["new"] and r["filled"] == len(cells) + len(rows[0]["cells"])
    band = next(c for c in _cells(tgt, tt) if c["col"] == 0 and c["text"] == "가나대")
    assert band["rowSpan"] == 2 and [_at(tgt, tt, trow + k, 2)["text"] for k in (0, 1)] == ["가2", "나2"]
    again = _run(d, pairs, src, tgt)
    assert not _mine(again, g)[0] and not _mine(again, g)[1]
    back = HwpxDoc(hwpx_struct.snapshot(tgt)["bytes"])
    assert any(c.get("text") == "나2" for b in back.blocks() if b.get("type") == "table" for c in b["cells"])


def test_append_form_example_rows_do_not_stay_under_a_real_org(small):
    """올린 원본이 등록된 빈 양식이면(orig) 이어 넣는 덩이의 **예시 행**(값 칸이 모두 양식의 글 그대로 — 「Fe계 금속파우더 …」)을 사람 글로 보지 않는다: 그 기관 · 그 해의 실제 행이 있으면
    예시 행에 실제 행을 쓰고, 없으면 예시 값을 비운다(실제 기관 이름 아래에 서식의 보기 값이 남지 않게). 반영 뒤 다시 계획하면 할 일이 없다. orig 가 없으면 전처럼 그대로 둔다."""
    d, pairs = small
    src, tgt = _fresh(d["from"]), _fresh(d["to"])
    g = next(g for g in pairs["groups"] if g["status"] == "paired" and g["kind"] == "rows" and any(c["row"] == 0 and c["text"] == "연구재료" for c in _cells(src, g["from"]["table"]))
             and any(c["text"] == "변동여부*" for c in _cells(tgt, g["to"]["table"])))
    ft, tt = g["from"]["table"], g["to"]["table"]
    orig = {c["id"]: {"text": c.get("text") or ""} for c in _cells(tgt, tt)}   # 지금 글 = 양식의 글(막 구성만 반영한 양식)
    lead = next(c for c in _cells(tgt, tt) if c["col"] == 0 and c["text"] == "인텍")["row"]
    example = [c for c in _cells(tgt, tt) if c["row"] == lead and c["col"] >= 2 and (c["text"] or "").strip()]
    assert any("금속파우더" in c["text"] for c in example)   # 서식의 예시 행이 주관 기관 덩이에 있다
    run = lambda: MT.plan({**d["to"], "doc": tgt}, {**d["from"], "doc": src}, d["values"], d["values"], pairs, orig=orig)  # noqa: E731
    assert not [c for c in _mine(_run(d, pairs, src, tgt), g)[0] if c.get("clear")]   # orig 없음 — 예시인지 모른다: 안 건드린다
    cells = _mine(run(), g)[0]
    assert {c["to"] for c in cells if c.get("clear")} >= {c["id"] for c in example if c["text"].strip() not in ("2027",)} - {c["id"] for c in example if MT._empty(c["text"])}
    # 그 기관 · 그 해의 실제 행이 생기면 — 예시 행이 그 행의 자리가 된다
    row27 = next(c for c in _cells(src, ft) if c["col"] == 0 and c["text"] == "인텍")["row"] + 1
    assert _at(src, ft, row27, 1)["text"] == "2027"
    ncol = max(c["col"] for c in _cells(src, ft))
    for col in range(2, ncol + 1):
        src.set_text(_at(src, ft, row27, col)["id"], f"인{col}")
    p = run()
    cells, rows, _ = _mine(p, g)
    put = {c["to"]: c for c in cells if not c.get("clear")}
    assert not rows and all(put[c["id"]]["was"] == c["text"] for c in example if c["id"] in put) and any(c["id"] in put for c in example)
    MT.apply(tgt, src, {**p, "cells": cells, "rows": rows})
    after = {c["col"]: c["text"] for c in _cells(tgt, tt) if c["row"] == lead and c["col"] >= 2}
    assert not any("금속파우더" in (t or "") or "KEIT" in (t or "") for t in after.values()) and after[2] == "인2"
    again = _mine(run(), g)
    assert not again[0] and not again[1]


def test_append_reports_source_columns_missing_in_target(small):
    """이어 넣는 자리에서 원본에만 있는 열(목적 표에 그 열 머리가 없음)의 글은 못 넣고 까닭(shape)에 열 머리 이름을 적는다 —
    열 머리 꼴은 글의 튜플이라 그대로 이어 붙이면 TypeError(2026-11-11 실제 쌍의 「넣기 계획」 이 500 으로 죽은 자리)."""
    d, pairs = small
    src, tgt = _fresh(d["from"]), _fresh(d["to"])
    g = next(g for g in pairs["groups"] if g["status"] == "paired" and g["kind"] == "rows" and any(c["row"] == 0 and c["text"] == "연구재료" for c in _cells(src, g["from"]["table"]))
             and any(c["text"] == "변동여부*" for c in _cells(tgt, g["to"]["table"])))
    ft = g["from"]["table"]
    y27 = next(c for c in _cells(src, ft) if c["col"] == 0 and c["text"] == "가나대")["row"] + 1
    ncol = max(c["col"] for c in _cells(src, ft))
    for col in range(2, ncol + 1):
        src.set_text(_at(src, ft, y27, col)["id"], f"가{col}")
    src.set_text(_at(src, ft, 0, ncol)["id"], "없는 열")   # 원본의 끝 열 머리를 목적 표에 없는 이름으로
    p = _run(d, pairs, src, tgt)
    cells, _, skipped = _mine(p, g)
    assert [s["detail"] for s in skipped if s["why"] == "shape"] == ["목적 표에 없는 원본 열: 없는열"]
    assert cells and f"가{ncol}" not in {c["text"] for c in cells}   # 나머지 열은 그대로 넣고 그 열만 뺀다


@pytest.mark.parametrize("calc", [False, True])
def test_append_column_key_ignores_head_cells_in_data_rows_and_is_idempotent(small, calc):
    """이어 넣는 표에서 3단계가 자료 행의 칸(「명칭(구분)」·「방식」 열의 글)을 행 머리로 봐도 열 머리 꼴은 행마다 같다 — 윗 행의 글이 꼴에 끼면 늘린 행에서 그 열의 글이 빠지고
    (6칸 가운데 4칸), 다시 계획할 때 「없는 행」 으로 보여 한 줄이 또 들어간다(2026-11-12 화면 「한 번에 진행」 을 다시 눌러 드러남 — 반영할 때마다 행이 늘었다).
    calc = 목적 표의 끝 열이 계산 칸: 그 칸은 비워 두고 넣는데, 다시 계획할 때 그 빈 칸 때문에 「없는 행」 으로 보면 안 된다."""
    import copy
    d, pairs = small
    src, tgt = _fresh(d["from"]), _fresh(d["to"])
    head = lambda doc, tid: {c["col"]: (c["text"] or "").replace("\n", "") for c in _cells(doc, tid) if c["row"] == 0}  # noqa: E731
    g = next(g for g in pairs["groups"] if g["status"] == "paired" and g["kind"] == "rows" and g["to"].get("table") and g["from"].get("table")
             and "명칭(구분)" in head(src, g["from"]["table"]).values() and "명칭(구분)" in head(tgt, g["to"]["table"]).values())
    ft, tt = g["from"]["table"], g["to"]["table"]
    tabs = {side: copy.deepcopy(d[side]["tables"]) for side in ("to", "from")}
    for side, doc, tid in (("to", tgt, tt), ("from", src, ft)):   # 실제 서버 분석이 낸 꼴 — 「명칭(구분)」·「방식」 열의 자료 칸이 행 머리
        cols = {col for col, text in head(doc, tid).items() if text.startswith(("명칭", "방식"))}
        ids = {c["id"] for c in _cells(doc, tid) if c["row"] and c["col"] in cols}
        assert len(cols) == 2 and ids
        for t in tabs[side]["tables"]:
            for c in t["cells"]:
                if c["id"] in ids:
                    c["role"] = "rowhead"
    last = max(c["col"] for c in _cells(src, ft))
    for c in _cells(src, ft):   # 원본의 자료 칸마다 다른 글(기관·연도 칸 빼고)
        if c["row"] and c["col"] >= 2:
            src.set_text(c["id"], f"r{c['row']}c{c['col']}")
    if calc:   # 목적 표에서 원본의 끝 열과 같은 열의 자료 칸 = 계산 칸(수식이 걸림)
        col = next(k for k, text in head(tgt, tt).items() if text == head(src, ft)[last])
        mine = [c["id"] for c in _cells(tgt, tt) if c["row"] and c["col"] == col]
        next(t for t in tabs["to"]["tables"] if any(c["id"] in mine for c in t["cells"])).setdefault("formulas", []).extend({"cell": i, "operands": ["없는칸"]} for i in mine)
        last -= 1
    run = lambda: MT.plan({**d["to"], "doc": tgt, "tables": tabs["to"]}, {**d["from"], "doc": src, "tables": tabs["from"]}, d["values"], d["values"], pairs)  # noqa: E731
    p = run()
    cells, rows, _ = _mine(p, g)
    assert rows and not cells
    for r in rows:   # 늘리는 행마다 원본 한 행의 모든 열(2열 ~ 끝 열)
        assert len({x["text"].split("c")[0] for x in r["cells"]}) == 1 and sorted(int(x["text"].split("c")[1]) for x in r["cells"]) == list(range(2, last + 1)), r["cells"]
    out = MT.apply(tgt, src, {**p, "cells": cells, "rows": rows})
    assert out["rowsAdded"] == len(rows) and not out["skipped"]
    again = _mine(run(), g)
    assert not again[0] and not again[1], again[1]


SHAPE = {"ratioPct": 70, "spacingPct": -5, "sizePt": 9.0}   # 시험이 원본 칸에 주는 장평·자간·글자 크기
REST = ("font", "fontLatin", "bold", "italic", "underline", "color", "align", "lineSpacingPct")   # 그 밖의 글자 모양·문단 모양 — 이것도 원본 칸 것이 온다(칸 서식 통째)


def _fmt(doc, tid, cid):
    """칸 첫 문단의 (서식 요약 — 글 있는 첫 런의 글자 모양 + 문단 모양, 문단 id)."""
    b = next(c for c in _cells(doc, tid) if c["id"] == cid)["blocks"][0]
    return b["format"], b["id"]


def _reshape(doc, tid, cid, changes):
    """칸 첫 문단의 글자 모양을 바꾼다(원본 칸에 장평·자간·크기를 주려고) → 그 글자 모양 정의(hh:charPr)."""
    pid = _fmt(doc, tid, cid)[1]
    doc.apply_format([pid], doc.derive_format(doc.get_format(pid), changes))
    return doc._defs["charPr"][doc._char_id(doc._ids[pid])]


def _three(fmt):
    return {k: fmt[k] for k in SHAPE}


def test_apply_brings_the_whole_cell_format_with_the_text(small):
    """표 칸에 글을 옮길 때 원본 칸의 **서식이 통째로** 온다(2026-11-12 사용자 「동일 테이블 매핑할 때는 서식정보도 같이 갖어오도록」 → 답 「원본 칸 서식 통째」 — 처음의 「장평·자간·글자 크기만」 을 넓힘):
    글꼴·크기·장평·자간·색·굵기(글자 모양)와 정렬·줄 간격(문단 모양)이 원본 칸 것이 되고 장평·자간의 언어별 값(영문만 다른 자간)도 그대로 온다. 칸의 테두리·배경은 목적 표 것 그대로.
    이미 같은 칸은 그대로 두고(다시 입혀도 정의가 늘지 않는다), 반영 뒤 다시 계획하면 할 일이 없으며(모양만 다른 칸은 할 일이 아니다), 표준 검사에 걸리지 않고 저장해 다시 열어도 그 모양이다."""
    d, pairs = small
    g = next(g for g in pairs["groups"] if g["status"] == "paired" and g["kind"] == "rows" and g["dim"] == "year" and g["to"]["label"] == "차년도" and not g["to"]["path"])
    src, tgt = _fresh(d["from"]), _fresh(d["to"])
    ft, tt = g["from"]["table"], g["to"]["table"]
    lab = next(c for c in _cells(src, ft) if c["id"] == g["items"][0]["from"]["id"])   # 원본 1차년도 행
    for k, c in enumerate(sorted((c for c in _cells(src, ft) if c["row"] == lab["row"] and c["col"] > lab["col"]), key=lambda c: c["col"]), 1):
        src.set_text(c["id"], f"{k},777")
    p = _run(d, pairs, src, tgt)
    cells, rows, _ = _mine(p, g)
    a, rest = cells[0], cells[1:]
    sc = _reshape(src, ft, a["from"], {**SHAPE, "bold": True, "color": "#FF0000", "font": "궁서", "align": "right"})   # 원본 한 칸만 — 굵게·빨강·글꼴·오른쪽 맞춤도 함께 온다
    sc.find("{*}spacing").set("latin", "-12")   # 영문 자간만 다른 글자 모양
    look = lambda doc, tid, cid: {k: _fmt(doc, tid, cid)[0][k] for k in (*SHAPE, *REST)}  # noqa: E731
    before = {c["to"]: look(tgt, tt, c["to"]) for c in cells}
    want = {c["to"]: look(src, ft, c["from"]) for c in cells}
    assert rest and _three(before[a["to"]]) != SHAPE and not before[a["to"]]["bold"] and before[a["to"]]["font"] != "궁서" and before[a["to"]]["align"] != "right"
    bf = {c["to"]: next(x for x in _cells(tgt, tt) if x["id"] == c["to"]).get("bf") for c in cells}   # 칸의 테두리·배경 정의
    r = MT.apply(tgt, src, {**p, "cells": cells, "rows": rows})
    assert r["filled"] == len(cells) and r["shaped"] >= 1
    assert all(look(tgt, tt, c["to"]) == want[c["to"]] for c in cells)   # 쓴 칸마다 원본 칸의 글자 모양·문단 모양
    got, pid = _fmt(tgt, tt, a["to"])
    assert _three(got) == SHAPE and (got["bold"], got["color"].upper(), got["font"], got["align"]) == (True, "#FF0000", "궁서", "right")
    tc = tgt._defs["charPr"][tgt._char_id(tgt._ids[pid])]
    assert all(dict(tc.find(f"{{*}}{tag}").attrib) == dict(sc.find(f"{{*}}{tag}").attrib) for tag in ("ratio", "spacing")) and tc.find("{*}spacing").get("latin") == "-12"
    assert bf == {c["to"]: next(x for x in _cells(tgt, tt) if x["id"] == c["to"]).get("bf") for c in cells}   # 칸 속성(테두리·배경)은 목적 표 것 그대로
    n = (len(tgt._defs["charPr"]), len(tgt._defs["paraPr"]))
    assert not any(tgt.fit_format(c["to"], src, c["from"]) for c in cells) and (len(tgt._defs["charPr"]), len(tgt._defs["paraPr"])) == n   # 이미 같으면 아무것도 안 한다
    again = _run(d, pairs, src, tgt)
    assert not _mine(again, g)[0] and not _mine(again, g)[1]
    base = owpml_check.counts(owpml_check.check_doc(HwpxDoc(d["to"]["bytes"])))
    assert owpml_check.verdict(tgt, base, owpml_check.check_doc(tgt))["status"] != "fail"   # 원본에 없던 종류의 위반이 없다(header 에 더한 글자 모양 포함)
    back = HwpxDoc(hwpx_struct.snapshot(tgt)["bytes"])
    assert back.adopt_ids(tgt.id_state())   # 저장본을 다시 열어 같은 id 로(표지 표는 칸 안의 표라 blocks() 최상위에 없다)
    assert next(c for c in _cells(back, tt) if c["id"] == a["to"])["text"] == a["text"] and _three(_fmt(back, tt, a["to"])[0]) == SHAPE and _fmt(back, tt, a["to"])[0]["bold"]


def test_append_rows_bring_shape_only_to_the_cells_they_fill(small):
    """이어 넣는 자리도 같다 — 빈 행에 넣은 칸도 늘린 행의 칸도 원본 칸의 서식(글자 모양·문단 모양 통째)을 받는다. 늘린 행에서 글을 안 넣은 칸은 목적 표의 모양 그대로다:
    늘리는 행은 앞 행을 본뜨므로 모양을 먼저 얹으면 앞 행 칸의 것이 글 없는 새 칸에도 따라간다(모양은 행을 다 늘린 뒤에 얹는다). 글 없는 원본 칸에서는 아무것도 안 가져온다."""
    d, pairs = small
    src, tgt = _fresh(d["from"]), _fresh(d["to"])
    g = next(g for g in pairs["groups"] if g["status"] == "paired" and g["kind"] == "rows" and any(c["row"] == 0 and c["text"] == "연구재료" for c in _cells(src, g["from"]["table"]))
             and any(c["text"] == "변동여부*" for c in _cells(tgt, g["to"]["table"])))
    ft, tt = g["from"]["table"], g["to"]["table"]
    y27 = next(c for c in _cells(src, ft) if c["col"] == 0 and c["text"] == "가나대")["row"] + 1
    ncol = max(c["col"] for c in _cells(src, ft))
    for col in range(2, ncol + 1):
        src.set_text(_at(src, ft, y27, col)["id"], f"가{col}")
    m = src.clone_rows(ft, y27, y27, [2, ncol], keep_text=False)["map"]   # 원본 2027 덩이를 두 행으로 — 둘째 행의 2열은 비워 둔다
    for col in range(3, ncol + 1):
        src.set_text(m[_at(src, ft, y27, col)["id"]], f"나{col}")
    _reshape(src, ft, _at(src, ft, y27, 2)["id"], SHAPE)        # 「가2」 — 목적의 빈 행에 들어갈 칸
    _reshape(src, ft, m[_at(src, ft, y27, 3)["id"]], SHAPE)    # 「나3」 — 늘린 행에 들어갈 칸
    p = _run(d, pairs, src, tgt)
    cells, rows, _ = _mine(p, g)
    trow = next(c for c in _cells(tgt, tt) if c["col"] == 0 and c["text"] == "가나대")["row"]
    look = lambda row, col: _fmt(tgt, tt, _at(tgt, tt, row, col)["id"])[0]  # noqa: E731
    own, theirs = look(trow, 2), _three(_fmt(src, ft, _at(src, ft, y27, 4)["id"])[0])   # 목적 표의 원래 모양 · 원본 표의 여느 칸(자간이 다르다)
    assert len(rows) == 1 and theirs not in (_three(own), SHAPE)
    r = MT.apply(tgt, src, {**p, "cells": cells, "rows": rows})
    assert r["rowsAdded"] == 1 and r["shaped"] == r["filled"] == len(cells) + len(rows[0]["cells"])   # 원본 표는 자간이 달라 쓴 칸마다 얹힌다
    assert [_at(tgt, tt, trow + k, 3)["text"] for k in (0, 1)] == ["가3", "나3"]
    assert _three(look(trow, 2)) == SHAPE and _three(look(trow + 1, 3)) == SHAPE   # 가2 · 나3
    assert _three(look(trow, 4)) == theirs and _three(look(trow + 1, 4)) == theirs   # 나머지 칸은 원본 표의 값
    assert _at(tgt, tt, trow + 1, 2)["text"] == "" and _three(look(trow + 1, 2)) == _three(own)   # 글을 안 넣은 새 칸 — 윗 행 「가2」 의 모양이 따라오지 않는다
    theirs_at = lambda cid: _fmt(src, ft, cid)[0]  # noqa: E731
    assert all(look(trow, col)[k] == theirs_at(_at(src, ft, y27, col)["id"])[k] for col in (2, 4) for k in REST)   # 나머지 글자 모양·문단 모양도 원본 칸 것(칸 서식 통째)
    assert all(look(trow + 1, col)[k] == theirs_at(m[_at(src, ft, y27, col)["id"]])[k] for col in (3, 4) for k in REST)
    assert all(look(trow + 1, 2)[k] == own[k] for k in REST)   # 글을 안 넣은 새 칸은 목적 표 것
    assert not tgt.fit_format(_at(tgt, tt, trow, 2)["id"], src, _at(src, ft, y27 - 1, 2)["id"]) and _three(look(trow, 2)) == SHAPE   # 글 없는 원본 칸(2026 행)
    again = _run(d, pairs, src, tgt)
    assert not _mine(again, g)[0] and not _mine(again, g)[1]
    back = HwpxDoc(hwpx_struct.snapshot(tgt)["bytes"])
    cell = next(c for b in back.blocks() if b.get("type") == "table" for c in b["cells"] if c.get("text") == "나3")
    assert _three(cell["blocks"][0]["format"]) == SHAPE


def test_real_pair_tables():
    """실제 작성본 ↔ 그 값으로 반영한 연차보고서(없으면 건너뜀): 자동 연결된 표 묶음 17 — 정해진 자리 10 · 이어 넣는 자리 7. 반영 → 다시 계획하면 할 일 없음 · 저장해 다시 열림."""
    d = M.real()
    if d is None:
        pytest.skip("실제 작성본 없음")
    s = {side: P.summarize(d[side]["doc"].blocks(), d[side]["graph"], d[side]["tables"], d["values"]) for side in ("to", "from")}
    pairs = P.pair(s["to"], s["from"])
    tgt = M.fresh(d["to"])
    p = MT.plan({**d["to"], "doc": tgt}, d["from"], d["values"], d["values"], pairs)
    modes = [t["mode"] for t in p["tables"]]
    assert (modes.count("fixed"), modes.count("append")) == (10, 7)
    assert p["counts"]["cells"] >= 600 and p["counts"]["rows"] >= 100 and p["counts"]["skipped"]["shape"] == 0
    assert "2,200,000" in {c["text"] for c in p["cells"] if c["group"] == p["tables"][1]["group"]}   # 표지 1차년도 정부지원 현금
    # 약칭 기관 — 짐작하지 않되 문서가 스스로 밝힌 것(본문의 「한국전기연구원(KERI)」)은 그 기관으로 읽는다(2026-11-22: 전에는 「KERI」 로 적힌 세부 사용계획 행이 통째로 빠졌다)
    assert MT._side(d["from"], d["values"])["alias"].get("KERI") == "한국전기연구원"
    assert not any(s["why"] == "ambiguous" and "KERI" in s["detail"] for s in p["skipped"])
    r = MT.apply(tgt, d["from"]["doc"], p)
    assert r["filled"] == p["counts"]["cells"] + p["counts"]["rowCells"] and r["rowsAdded"] == p["counts"]["rows"] and not r["skipped"]
    again = MT.plan({**d["to"], "doc": tgt}, d["from"], d["values"], d["values"], pairs)
    assert again["counts"]["cells"] == again["counts"]["rows"] == 0
    assert HwpxDoc(hwpx_struct.snapshot(tgt)["bytes"]).blocks()
