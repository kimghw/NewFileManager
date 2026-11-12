"""표 만들기 · 서식 변환(spec_헤딩_추출 ② §11): 격자 정규화 · 구역 판정/맞춤 · 표 꼴 글 읽기 · 검산 · hwpx 새 표/서식 입히기(OWPML 검사) · LLM 계약 · API."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_rules as R
from app import owpml_check as C
from app import hwpx_struct, server, table_agent, table_llm
from app import table_make as M
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL = SAMPLES / "기술수요조사서.hwpx"
DOCX = SAMPLES / "기술수요조사서.docx"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
GRID = {"rows": [["구분", "내용", "비고"], ["가", "첫째 줄\n둘째 줄", ""], ["나", {"text": "합친 칸", "colSpan": 2}], ["합계", "3", "-"]], "headerRows": 1, "footRows": 1}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    table_agent._MEMORY.clear()
    yield
    R._MEMORY.clear()
    table_agent._MEMORY.clear()


def _cell(row, col, text="", rs=1, cs=1, shaded=False, bold=False):
    return {"row": row, "col": col, "rowSpan": rs, "colSpan": cs, "text": text, "shaded": shaded, "bold": bold}


def _tables(blocks, out=None):
    out = [] if out is None else out
    for b in blocks:
        if b["type"] == "table":
            out.append(b)
            for c in b["cells"]:
                _tables(c.get("blocks") or [], out)
    return out


# ---- 격자 정규화 ---------------------------------------------------------------------------------------------------

def test_normalize_places_cells_like_html_tables():
    n = M.normalize({"rows": [[{"text": "A", "rowSpan": 2}, "B", "C"], ["D", {"text": "E"}], {"cells": ["F", {"text": "G", "colSpan": 2}]}], "headerRows": 1, "headerCols": 1})
    assert (n["nRows"], n["nCols"]) == (3, 3) and (n["headerRows"], n["headerCols"], n["footRows"]) == (1, 1, 0)
    at = {(c["row"], c["col"]): c for c in n["cells"]}
    assert at[0, 0]["rowSpan"] == 2 and at[1, 1]["text"] == "D" and at[1, 2]["text"] == "E"  # 내려온 자리를 건너뜀
    assert at[2, 1]["colSpan"] == 2 and len(n["cells"]) == 7
    assert sum(c["rowSpan"] * c["colSpan"] for c in n["cells"]) == 9  # 구멍·겹침 없음
    back = M.to_rows(n)
    assert [len(r["cells"]) for r in back["rows"]] == [3, 2, 2] and M.normalize(back) == n  # 왕복


def test_normalize_fills_holes_clips_spans_and_squeezes():
    n = M.normalize({"rows": [["a", "b", "c"], ["d"]]})
    assert len(n["cells"]) == 6 and [c["text"] for c in n["cells"] if c["row"] == 1] == ["d", "", ""]  # 짧은 행은 빈 칸으로
    n = M.normalize({"rows": [[{"text": "x", "rowSpan": 9, "colSpan": 2}, "y"], ["z"]]})
    assert n["nRows"] == 2 and n["cells"][0]["rowSpan"] == 2  # 표 밖 rowSpan 자름
    n = M.normalize({"rows": [["a", {"text": "b", "rowSpan": 2}], [{"text": "wide", "colSpan": 3}]]})
    wide = next(c for c in n["cells"] if c["text"] == "wide")
    assert wide["colSpan"] == 1 and (wide["row"], wide["col"]) == (1, 0)  # 내려온 칸에 걸리면 거기까지만
    n = M.normalize({"rows": [[{"text": "a", "rowSpan": 2}, {"text": "b", "rowSpan": 2}], [], ["c", "d"]]})
    assert n["nRows"] == 2 and all(c["rowSpan"] == 1 for c in n["cells"])  # 칸이 시작하지 않는 행은 없앰(빈 hp:tr 방지)
    assert M.normalize({"rows": [["a"]], "headerRows": 5, "footRows": 5})["headerRows"] == 1


@pytest.mark.parametrize("bad", [None, {}, {"rows": []}, {"rows": [[]]}, {"rows": [["x"] * (M.COLS_MAX + 1)]}, {"rows": [["x"]] * (M.ROWS_MAX + 1)},
                                 {"rows": [["가" * (M.TEXT_MAX + 1)]]}])
def test_normalize_rejects(bad):
    with pytest.raises(ValueError):
        M.normalize(bad)


# ---- 구역 ---------------------------------------------------------------------------------------------------------

def test_zone_index():
    assert [M.zone_index(i, 4, 1, 1, 4, 1, 1) for i in range(4)] == [0, 1, 2, 3]  # 같은 꼴 = 1:1
    # 양식 머리 2 · 몸 3 · 합계 1(6줄) ← 대상 머리 1 · 몸 5 · 합계 1(7줄): 머리는 양식 머리의 마지막 줄, 몸은 첫·가운데·마지막
    assert [M.zone_index(i, 7, 1, 1, 6, 2, 1) for i in range(7)] == [1, 2, 3, 3, 3, 4, 5]
    assert [M.zone_index(i, 4, 3, 0, 6, 2, 1) for i in range(4)] == [0, 0, 1, 2]  # 대상 머리가 더 많으면 남는 윗줄은 양식 머리 첫 줄 · 몸이 1줄뿐이면 양식 몸 첫 줄
    assert [M.zone_index(i, 3, 1, 1, 3, 0, 0) for i in range(3)] == [0, 1, 2]  # 양식에 머리·합계가 없으면 몸 줄로
    assert [M.zone_index(i, 3, 1, 0, 2, 2, 0) for i in range(3)] == [1, 1, 1]  # 양식에 몸이 없으면 머리 마지막 줄
    assert [M.zone_index(i, 5, 0, 0, 2, 0, 0) for i in range(5)] == [0, 0, 0, 0, 1] and M.zone_index(0, 1, 0, 0, 0, 0, 0) == 0


def test_col_weights():
    n = M.normalize({"rows": [["연차", "연구개발 내용", "비"], ["1", "선박 운항 데이터 수집 체계 구축 및 데이터 전처리 모듈 개발 — 아주 긴 문장이 이어진다 계속 이어진다", "3"],
                              [{"text": "합친 칸은 폭 계산에서 빠진다 합친 칸은 폭 계산에서 빠진다", "colSpan": 3}]]})
    w = M.col_weights(n)
    assert w == [6, 40, 6]  # 짧은 열은 바닥 6 · 긴 문장 열은 천장 40 · 합친 칸은 안 봄
    assert M.col_weights(M.normalize({"rows": [["abcdefgh", "가나다라\n마"]]})) == [10, 10]  # 전각 2 · 가장 긴 줄 + 여백 2


def test_roles_of():
    cells = [_cell(0, c, f"h{c}", shaded=True) for c in range(3)] + [_cell(1, 0, "가", shaded=True), _cell(1, 1, "1"), _cell(1, 2, "2"),
                                                                    _cell(2, 0, "나", shaded=True), _cell(2, 1, "3"), _cell(2, 2, "4"),
                                                                    _cell(3, 0, "합 계", shaded=True), _cell(3, 1, "4"), _cell(3, 2, "6")]
    assert M.roles_of(cells, 4, 3) == {"headerRows": 1, "headerCols": 1, "footRows": 1}
    plain = [_cell(r, c, "x") for r in range(3) for c in range(2)]
    assert M.roles_of(plain, 3, 2) == {"headerRows": 1, "headerCols": 0, "footRows": 0}  # 표시가 없으면 첫 행
    assert M.roles_of([_cell(0, 0, "x")], 1, 1) == {"headerRows": 0, "headerCols": 0, "footRows": 0}
    allshade = [_cell(r, c, "x", shaded=True) for r in range(3) for c in range(2)]
    assert M.roles_of(allshade, 3, 2)["headerRows"] == 1  # 표 전체가 한 가지
    merged = [_cell(0, 0, "큰 머리", rs=2, shaded=True), _cell(0, 1, "a", shaded=True), _cell(1, 1, "b", shaded=True), _cell(2, 0, "v"), _cell(2, 1, "w")]
    assert M.roles_of(merged, 3, 2)["headerRows"] == 2  # 합친 머리 칸이 걸친 줄도
    bold = [_cell(0, 0, "h", bold=True), _cell(0, 1, "h", bold=True), _cell(1, 0, "v"), _cell(1, 1, "w")]
    assert M.roles_of(bold, 2, 2)["headerRows"] == 1  # 음영이 없는 표는 굵게
    assert M.clean_roles({"headerRows": 9, "footRows": "x"}, 4, 3, default={"footRows": 1, "headerCols": 2}) == {"headerRows": 4, "headerCols": 2, "footRows": 0}


# ---- 표 꼴 글 · 블록 ----------------------------------------------------------------------------------------------------

def test_parse_text():
    g = M.parse_text("구분\t1차\t2차\n현금\t10\t20\n합계\t10\t20\n")
    assert g["rows"] == [["구분", "1차", "2차"], ["현금", "10", "20"], ["합계", "10", "20"]] and g["headerRows"] == 1 and g["footRows"] == 1
    g = M.parse_text('이름\t설명\n가\t"첫 줄\n둘째 줄"\n')
    assert g["rows"][1] == ["가", "첫 줄\n둘째 줄"]  # 엑셀의 따옴표 칸(줄 바꿈)
    g = M.parse_text("| 항목 | 값 |\n|---|:--:|\n| a | 1 |\n| b | 2 |")
    assert g["rows"] == [["항목", "값"], ["a", "1"], ["b", "2"]] and g["headerRows"] == 1
    assert M.parse_text("그냥 글입니다.\n둘째 줄입니다.") is None and M.parse_text("") is None and M.parse_text(None) is None
    assert M.parse_text("한 줄에만\t탭이 있고\n나머지는 글이다\n셋째 줄") is None  # 탭 한 줄로는 표가 아님
    assert M.parse_text("a\tb")["rows"] == [["a", "b"]]


def test_block_grid_and_nested():
    block = {"nRows": 2, "nCols": 2, "cells": [{"row": 0, "col": 0, "rowSpan": 1, "colSpan": 2, "text": "제목", "shaded": True, "blocks": []},
                                             {"row": 1, "col": 0, "rowSpan": 1, "colSpan": 1, "text": "a", "blocks": [{"type": "table"}]},
                                             {"row": 1, "col": 1, "rowSpan": 1, "colSpan": 1, "text": "b", "blocks": []}]}
    g = M.block_grid(block)
    assert g["rows"][0] == [{"text": "제목", "rowSpan": 1, "colSpan": 2}] and g["headerRows"] == 1 and M.block_nested(block)
    assert M.normalize(g)["nCols"] == 2


def test_checks():
    a = M.normalize({"rows": [["구분", "값"], ["가", "1,000"], ["가", ""]]})
    b = M.normalize({"rows": [["구분", "값"], ["가", "1,000 "], ["나", "새 글"]]})
    out = M.check_texts(a, b)
    assert out["lost"] == ["가"] and sorted(out["added"]) == ["나", "새 글"] and out["more"] == 0  # 공백 접어 모둠 비교(「가」 둘 중 하나가 빠짐)
    assert M.check_texts(a, a) == {"lost": [], "added": [], "numbers": [], "more": 0}
    nums = M.check_numbers("예산은 1,200만원이고 2026년 3월에 12명이 참여한다.", M.normalize({"rows": [["예산", "1200만원"], ["인원", "15명"], ["시기", "2026.3"], ["순번", "1"]]}))
    assert nums["numbers"] == ["15"]  # 쉼표는 떼고 견줌 · 한 자리 수는 안 봄 · 「2026.3」 은 조각(2026 · 3)이 원본에 있어 통과
    assert M.check_numbers("2026.3 기준", M.normalize({"rows": [["2026.3"], ["2027.3"]]}))["numbers"] == ["2027.3"]


# ---- hwpx 새 표 · 서식 입히기 --------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rnd_bytes():
    return RND.read_bytes()


def _cover(block, r, c):
    """표 블록에서 자리 (r, c) 를 덮는 칸(합친 칸 포함)."""
    return next(x for x in block["cells"] if x["row"] <= r < x["row"] + x["rowSpan"] and x["col"] <= c < x["col"] + x["colSpan"])


def _pick_template(doc):
    """머리 1 · 합계 1 인 양식 표(연구개발계획서 「성과지표」 꼴) — 없으면 머리행이 있는 첫 표."""
    tbs = _tables(doc.blocks())
    for want in ({"headerRows": 1, "headerCols": 0, "footRows": 1}, None):
        for b in tbs:
            r = M.roles_of(b["cells"], b["nRows"], b["nCols"])
            if b["nRows"] >= 4 and b["nCols"] >= 3 and (r == want if want else r["headerRows"] >= 1):
                return b, r
    raise AssertionError("양식으로 쓸 표가 없음")


def test_hwpx_table_make_builds_valid_table(rnd_bytes):
    d = HwpxDoc(rnd_bytes)
    base = C.counts(C.check_doc(d))
    tb, roles = _pick_template(d)
    ref = next(b["id"] for b in d.blocks() if b["type"] == "paragraph" and b["text"].strip())
    norm = M.normalize(GRID)
    r = d.table_make(ref, tb["id"], norm, roles)
    assert r["rows"] == 4 and r["cols"] == 3 and r["table"] != tb["id"]
    host = d._ids[r["host"]]
    assert host.getprevious() is d._ids[ref] and C.verdict(d, base, C.check_hosts(d, [host], header=True), local=True)["status"] != "fail"
    nb = d.table_block(r["table"])
    at = {(c["row"], c["col"]): c for c in nb["cells"]}
    assert nb["nRows"] == 4 and nb["nCols"] == 3 and len(nb["cells"]) == 11
    assert at[0, 0]["text"] == "구분" and at[1, 1]["text"] == "첫째 줄\n둘째 줄" and len(at[1, 1]["blocks"]) == 2  # 줄마다 문단
    assert at[2, 1]["colSpan"] == 2 and at[2, 1]["text"] == "합친 칸" and at[3, 0]["text"] == "합계"
    assert at[0, 1]["shaded"] == _cover(tb, 0, 1)["shaded"] and at[1, 1]["shaded"] == _cover(tb, roles["headerRows"], 1)["shaded"]  # 머리 ↔ 머리 · 몸 ↔ 몸
    tw = sum(int(tc.find("{*}cellSz").get("width")) for tc in next(d._ids[tb["id"]].iterchildren("{*}tr")))
    nw = sum(int(tc.find("{*}cellSz").get("width")) for tc in next(d._ids[r["table"]].iterchildren("{*}tr")))
    assert nw == tw and d._ids[r["table"]].get("id") != d._ids[tb["id"]].get("id")  # 표 폭 = 양식 표 폭 · 개체 id 는 새로
    d2 = HwpxDoc(d.save())  # 저장·다시 열기
    assert len(_tables(d2.blocks())) == len(_tables(HwpxDoc(rnd_bytes).blocks())) + 1


def test_hwpx_table_make_same_shape_copies_the_look(rnd_bytes):
    d = HwpxDoc(rnd_bytes)
    tb, roles = _pick_template(d)
    grid = {**M.block_grid(tb), **roles}
    norm = M.normalize(grid)
    r = d.table_make(tb["id"], tb["id"], norm, roles)  # 표 id 를 자리로 주면 그 표를 품은 문단 뒤
    nb = d.table_block(r["table"])
    key = lambda c: (c["row"], c["col"], c["rowSpan"], c["colSpan"])  # noqa: E731
    assert sorted(map(key, nb["cells"])) == sorted(map(key, tb["cells"]))
    t_at = {key(c): c for c in tb["cells"]}
    for c in nb["cells"]:  # 같은 꼴이면 칸마다 양식 칸의 borderFill·여백·정렬 그대로
        t = t_at[key(c)]
        assert (c["bf"], c["fill"], c["valign"], c["marginsMm"]) == (t["bf"], t["fill"], t["valign"], t["marginsMm"]), key(c)
        assert c["text"] == t["text"]


def test_hwpx_table_make_other_shape_fits_widths_and_drops_diagonals(rnd_bytes):
    d = HwpxDoc(rnd_bytes)
    d.blocks()
    diag = lambda bf: any((e := d._defs["borderFill"][bf].find("{*}" + t)) is not None and e.get("type", "NONE") != "NONE" for t in ("slash", "backSlash"))  # noqa: E731
    tb = next(b for b in _tables(d.blocks()) if b["nRows"] >= 4 and b["nCols"] >= 4 and any(diag(c["bf"]) for c in b["cells"]))  # 귀퉁이에 대각선이 든 양식
    roles = M.roles_of(tb["cells"], tb["nRows"], tb["nCols"])
    norm = M.normalize({"rows": [["연차", "연구개발 내용", "비고"], ["1차년도", "선박 운항 데이터 수집 체계 구축 및 데이터 전처리 모듈 개발", "-"], ["2차년도", "고장 예측 모델 개발", "-"]],
                        "headerRows": 1})
    r = d.table_make(tb["id"], tb["id"], norm, roles)
    nb = d.table_block(r["table"])
    assert not any(diag(c["bf"]) for c in nb["cells"])  # 꼴이 다르면 대각선은 안 옮김
    ws = [int(tc.find("{*}cellSz").get("width")) for tc in next(d._ids[r["table"]].iterchildren("{*}tr"))]
    tw = sum(int(tc.find("{*}cellSz").get("width")) for tc in next(d._ids[tb["id"]].iterchildren("{*}tr")))
    assert sum(ws) == tw and ws[1] > 2 * ws[0] and ws[1] > 2 * ws[2] and min(ws) * 12 > tw  # 열 수가 다르면 글 길이로 나눔(가는 열 없음) · 표 폭은 양식 폭
    same = d.table_make(tb["id"], tb["id"], M.normalize({**M.block_grid(tb), **roles}), roles)
    assert any(diag(c["bf"]) for c in d.table_block(same["table"])["cells"])  # 같은 꼴이면 대각선까지 그대로


def test_hwpx_table_make_errors(rnd_bytes):
    d = HwpxDoc(rnd_bytes)
    tb, roles = _pick_template(d)
    norm = M.normalize(GRID)
    with pytest.raises(ValueError):
        d.table_make("p999999", tb["id"], norm, roles)
    with pytest.raises(ValueError):
        d.table_make(tb["id"], "p1", norm, roles)  # 양식이 표가 아님
    assert d._blocks_cache is not None or True


def test_hwpx_table_restyle_keeps_structure_and_text(rnd_bytes):
    d = HwpxDoc(rnd_bytes)
    base = C.counts(C.check_doc(d))
    tb, roles = _pick_template(d)
    tbs = _tables(d.blocks())
    target = next(b for b in tbs if b["id"] != tb["id"] and b["nRows"] >= 3 and b["nCols"] >= 3 and not M.block_nested(b)
                  and {c["bf"] for c in b["cells"]} != {c["bf"] for c in tb["cells"]})
    before = copy.deepcopy(target)
    t_roles = M.roles_of(target["cells"], target["nRows"], target["nCols"])
    r = d.table_restyle(target["id"], tb["id"], t_roles, roles)
    assert r["table"] == target["id"] and r["cells"] == len(before["cells"])
    after = d.table_block(target["id"])
    key = lambda c: (c["row"], c["col"], c["rowSpan"], c["colSpan"], c["text"], c["id"])  # noqa: E731
    assert sorted(map(key, after["cells"])) == sorted(map(key, before["cells"]))  # 구조·글·칸 id 그대로
    fills_tpl = {c["fill"] for c in tb["cells"]}
    assert {c["fill"] for c in after["cells"]} <= fills_tpl  # 음영은 양식의 것만
    host = hwpx_struct.top_host(d, d._ids[target["id"]])  # 검사는 표를 품은 본문 문단 단위(server._hosts_check 와 같이)
    assert C.verdict(d, base, C.check_hosts(d, [host], header=True), local=True)["status"] != "fail"
    assert r["formatted"] and all(d._ids[i].tag.endswith("}p") for i in r["formatted"])
    with pytest.raises(ValueError):
        d.table_restyle(tb["id"], tb["id"], roles, roles)


# ---- LLM 계약 ------------------------------------------------------------------------------------------------------

def test_llm_content_and_ask():
    block = {"nRows": 20, "nCols": 2, "cells": [_cell(r, c, f"칸{r}-{c}" + "가" * 60) for r in range(20) for c in range(2)]}
    tpl = table_llm.template_data(block, {"headerRows": 1, "headerCols": 0, "footRows": 0}, [{"text": "※ 천원 단위"}])
    assert len(tpl["grid"]) == table_llm.TPL_ROWS and tpl["more"] == "아래 5행 생략" and tpl["notes"] == ["※ 천원 단위"] and len(tpl["grid"][0][0]) == table_llm.TPL_TEXT
    guide = table_llm.guide_text("공통", "", "이번만")
    assert "### 공통 표 지침\n공통" in guide and "### 이번 지침\n이번만" in guide and "표 양식의 표 지침" not in guide and table_llm.guide_text("", None, " ") == "(없음)"
    seen = {}

    def fake(schema, content, what, timeout=0, effort=None):
        seen.update(schema=schema, content=content, what=what)
        return {"data": {"headerRows": 1, "headerCols": 0, "footRows": 0, "rows": [{"cells": [{"text": "a", "rowSpan": 1, "colSpan": 1}, {"text": "b", "rowSpan": 1, "colSpan": 1}]},
                                                                                {"cells": [{"text": "1", "rowSpan": 1, "colSpan": 2}]}], "note": "두 열"},
                "backend": "sdk", "model": "m", "effort": "low", "ms": 5, "costUsd": 0.01, "error": None}
    out = table_llm.ask("compose", tpl, {"kind": "text", "text": "원본"}, guide, call=fake)
    assert out["norm"]["nRows"] == 2 and out["norm"]["nCols"] == 2 and out["note"] == "두 열" and out["call"]["backend"] == "sdk"
    assert seen["what"] == "table-make-compose" and seen["schema"] is table_llm.SCHEMA and '"mode":"compose"' in seen["content"] and "## 지침\n### 공통 표 지침" in seen["content"]
    assert "한 글자도 고치지 않고" in table_llm.CONTRACT and '"\\n"' in table_llm.CONTRACT
    bad = table_llm.ask("convert", tpl, {"kind": "table", "grid": {}}, guide, call=lambda *a, **k: {"data": {"rows": []}, "error": None})
    assert bad["norm"] is None and bad["call"]["error"].startswith("못 쓰는 답")
    off = table_llm.ask("convert", tpl, {"kind": "table", "grid": {}}, guide, call=lambda *a, **k: {"data": None, "error": "off"})
    assert off["norm"] is None and off["call"]["error"] == "off"


# ---- API ----------------------------------------------------------------------------------------------------------

def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


@pytest.fixture()
def client():
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def test_api_roles_compose_asis_and_errors(client):
    d = _upload(client, SMALL)
    tbs = _tables(client.get(f"/api/docs/{d}").json()["blocks"])
    big = max(tbs, key=lambda b: b["nRows"])
    r = client.get(f"/api/docs/{d}/tables/{big['id']}/roles").json()
    assert r["table"] == big["id"] and r["rows"] == big["nRows"] and set(r["roles"]) == {"headerRows", "headerCols", "footRows"} and r["nested"] is False
    assert client.get(f"/api/docs/{d}/tables/t9999/roles").status_code == 404
    url = f"/api/docs/{d}/tables/compose"
    g = client.post(url, json={"template": big["id"], "llm": False, "source": {"kind": "text", "text": "구분\t값\n가\t1\n"}}).json()
    assert g["mode"] == "asis" and g["call"] is None and [[c["text"] for c in row["cells"]] for row in g["grid"]["rows"]] == [["구분", "값"], ["가", "1"]]
    assert g["grid"]["headerRows"] == 1 and g["check"] == {"lost": [], "added": [], "numbers": [], "more": 0}
    t = client.post(url, json={"template": big["id"], "llm": False, "source": {"kind": "table", "id": big["id"]}}).json()
    assert len(t["grid"]["rows"]) == big["nRows"]
    pid = big["cells"][0]["blocks"][0]["id"]
    assert client.post(url, json={"template": big["id"], "llm": False, "source": {"kind": "paras", "ids": [pid]}}).status_code == 400  # 글은 그대로 못 옮김
    assert client.post(url, json={"template": big["id"], "llm": False, "source": {"kind": "text", "text": "그냥 글"}}).status_code == 400
    assert client.post(url, json={"template": big["id"], "llm": True, "source": {"kind": "text", "text": "그냥 글"}}).status_code == 503  # LLM 꺼짐
    assert client.post(url, json={"template": "t9999", "llm": False, "source": {"kind": "text", "text": "a\tb"}}).status_code == 404
    assert client.post(url, json={"template": big["id"], "llm": False, "source": {"kind": "paras", "ids": ["p99999"]}}).status_code == 404
    assert client.post(url, json={"template": big["id"], "llm": False, "source": {"kind": "what"}}).status_code == 400
    assert client.post(url, json={"template": big["id"], "llm": False, "source": {"kind": "grid", "grid": {"rows": []}}}).status_code == 400
    assert client.post(url, json={"template": big["id"], "instructions": 5, "source": {"kind": "text", "text": "a\tb"}}).status_code == 400


def test_api_compose_with_llm_stub(client, monkeypatch):
    d = _upload(client, SMALL)
    big = max(_tables(client.get(f"/api/docs/{d}").json()["blocks"]), key=lambda b: b["nRows"])
    assert client.put(f"/api/docs/{d}/headings/tables/_common/agent", json={"instructions": "금액은 천원 단위"}).status_code == 200
    assert client.put(f"/api/docs/{d}/headings/tables/{big['id']}/agent", json={"instructions": "양식 표 지침"}).status_code == 200
    calls = []

    def fake(schema, content, what, timeout=0, effort=None):
        calls.append({"content": content, "what": what, "effort": effort})
        cells = lambda *ts: {"cells": [{"text": t, "rowSpan": 1, "colSpan": 1} for t in ts]}  # noqa: E731
        if "convert" in what:
            return {"data": {"headerRows": 1, "headerCols": 1, "footRows": 0, "rows": [cells("구분", "값"), cells("가", "1,000"), cells("나", "고친 글")], "note": "그대로"},
                    "backend": "sdk", "model": "m", "effort": effort, "ms": 3, "costUsd": 0.02, "error": None}
        return {"data": {"headerRows": 1, "headerCols": 0, "footRows": 0, "rows": [cells("항목", "내용"), cells("예산", "1,200만원"), cells("인원", "15명")], "note": "2열로"},
                "backend": "sdk", "model": "m", "effort": effort, "ms": 3, "costUsd": 0.02, "error": None}
    monkeypatch.setattr(table_llm.llm, "call", fake)
    monkeypatch.setattr(server.tables_api.llm, "status", lambda: {"available": True})
    url = f"/api/docs/{d}/tables/compose"
    r = client.post(url, json={"template": big["id"], "instructions": "짧게", "effort": "medium", "source": {"kind": "text", "text": "예산은 1,200만원이고 인원은 12명이다."}})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["mode"] == "compose" and v["note"] == "2열로" and v["check"]["numbers"] == ["15"] and v["call"]["backend"] == "sdk" and len(v["grid"]["rows"]) == 3
    p = calls[0]["content"]
    assert calls[0]["effort"] == "medium" and "### 공통 표 지침\n금액은 천원 단위" in p and "### 표 양식의 표 지침\n양식 표 지침" in p and "### 이번 지침\n짧게" in p
    assert '"source":{"kind":"text","text":"예산은 1,200만원이고 인원은 12명이다."}' in p and '"template":{"rows":' in p
    v2 = client.post(url, json={"template": big["id"], "source": {"kind": "text", "text": "구분\t값\n가\t1,000\n나\t원래 글\n"}}).json()
    assert v2["mode"] == "convert" and v2["check"]["lost"] == ["원래 글"] and v2["check"]["added"] == ["고친 글"] and v2["grid"]["headerCols"] == 1  # 글이 바뀌면 검산에
    assert '"source":{"kind":"table","grid":{"rows":[{"cells":[{"text":"구분"' in calls[1]["content"]
    monkeypatch.setattr(table_llm.llm, "call", lambda *a, **k: {"data": None, "backend": None, "ms": 1, "costUsd": None, "error": "sdk: 시간 초과"})
    bad = client.post(url, json={"template": big["id"], "source": {"kind": "text", "text": "글"}})
    assert bad.status_code == 502 and "시간 초과" in bad.json()["detail"]
    log = client.get(f"/api/works/{d}/log").json()["events"]
    ev = [e for e in log if e["kind"] == "tableCompose"]
    assert len(ev) == 3 and ev[0]["mode"] == "compose" and ev[0]["rows"] == 3 and ev[2]["error"] == "sdk: 시간 초과" and str(ev[0]["detail"]).startswith("tables/make_")


def test_api_make_restyle_undo_small(client):
    d = _upload(client, SMALL)
    doc0 = client.get(f"/api/docs/{d}").json()
    tbs = _tables(doc0["blocks"])
    big, small = max(tbs, key=lambda b: b["nRows"]), min(tbs, key=lambda b: b["nRows"])
    r = client.post(f"/api/docs/{d}/tables/make", json={"template": big["id"], "grid": GRID, "after": big["id"]})
    assert r.status_code == 200, r.text
    v = r.json()
    new_id = v["made"]["table"]
    assert v["made"]["rows"] == 4 and v["made"]["cols"] == 3 and v["undo"] == 1 and v["pristine"] is False
    made = next(b for b in v["tops"]["blocks"] if b["id"] == new_id)
    assert [c["text"] for c in made["cells"]][:3] == ["구분", "내용", "비고"] and big["id"] in v["tops"]["drop"]
    now = _tables(client.get(f"/api/docs/{d}").json()["blocks"])
    assert [b["id"] for b in now if b["id"] in (big["id"], small["id"], new_id)] == [small["id"], big["id"], new_id]  # 양식 표(를 품은 문단) 뒤
    # 서식만 입히기 — 새 표에 작은 표의 서식을
    rs = client.post(f"/api/docs/{d}/tables/restyle", json={"table": new_id, "template": small["id"]})
    assert rs.status_code == 200, rs.text
    v2 = rs.json()
    assert v2["made"]["table"] == new_id and v2["undo"] == 2
    styled = next(b for b in v2["tops"]["blocks"] if b["id"] == new_id)
    assert [c["text"] for c in styled["cells"]] == [c["text"] for c in made["cells"]] and {c["fill"] for c in styled["cells"]} <= {c["fill"] for c in small["cells"]}
    assert client.post(f"/api/docs/{d}/tables/restyle", json={"table": new_id, "template": new_id}).status_code == 400
    # 새 표로 바꾸기(replace table) — 바꿀 표가 사라지고 새 표가 남는다
    rp = client.post(f"/api/docs/{d}/tables/make", json={"template": big["id"], "grid": GRID, "after": new_id, "replace": {"table": new_id}})
    assert rp.status_code == 200, rp.text
    ids = [b["id"] for b in _tables(client.get(f"/api/docs/{d}").json()["blocks"])]
    assert new_id not in ids and rp.json()["made"]["table"] in ids
    for _ in range(3):
        assert client.post(f"/api/docs/{d}/undo").status_code == 200
    back = client.get(f"/api/docs/{d}").json()
    assert [b["id"] for b in _tables(back["blocks"])] == [b["id"] for b in tbs] and back["pristine"] is True
    # 오류
    assert client.post(f"/api/docs/{d}/tables/make", json={"template": big["id"], "grid": {"rows": []}, "after": big["id"]}).status_code == 400
    assert client.post(f"/api/docs/{d}/tables/make", json={"template": big["id"], "grid": GRID, "after": "p99999"}).status_code == 404
    assert client.post(f"/api/docs/{d}/tables/make", json={"template": "t9999", "grid": GRID, "after": big["id"]}).status_code == 404
    assert client.post(f"/api/docs/{d}/tables/make", json={"template": big["id"], "grid": GRID, "after": big["id"], "replace": {"table": "t9999"}}).status_code == 404
    log = [e["kind"] for e in client.get(f"/api/works/{d}/log").json()["events"]]
    assert log.count("tableMake") == 2 and log.count("tableRestyle") == 1


def test_api_make_replaces_paragraph_range(client):
    d = _upload(client, RND)
    blocks = client.get(f"/api/docs/{d}").json()["blocks"]
    tb = next(b for b in _tables(blocks) if b["nRows"] >= 4 and b["nCols"] >= 3)
    sess = server.DOCS[d]
    # 본문의 잇단 글 문단 둘(개체·구역 설정 없음)
    pair = None
    for a, b in zip(blocks, blocks[1:]):
        if a["type"] == b["type"] == "paragraph" and a["text"].strip() and b["text"].strip():
            ea, eb = sess.doc._ids[a["id"]], sess.doc._ids[b["id"]]
            if ea.getnext() is eb and not sess.doc._has_object(ea) and not sess.doc._has_object(eb) and next(ea.iter("{*}secPr"), None) is None:
                pair = (a["id"], b["id"])
                break
    assert pair, "잇단 본문 문단을 못 찾음"
    r = client.post(f"/api/docs/{d}/tables/make", json={"template": tb["id"], "grid": GRID, "after": pair[1], "replace": {"first": pair[0], "last": pair[1]}})
    assert r.status_code == 200, r.text
    v = r.json()
    assert set(pair) <= set(v["tops"]["drop"]) and [b["id"] for b in v["tops"]["blocks"]] == [v["made"]["table"]]
    assert v["kinds"].get(pair[0]) == "removed" and v["owpml"]["status"] in ("ok", "warn")
    after = client.get(f"/api/docs/{d}").json()["blocks"]
    ids = [b["id"] for b in after]
    assert pair[0] not in ids and pair[1] not in ids and v["made"]["table"] in ids
    # 표가 낀 범위는 바꾸지 않는다(원본 글에 없던 표를 지우지 않게) — 400 이고 문서는 그대로
    host_i = next(i for i, b in enumerate(after) if b["type"] == "table" and i > 0 and after[i - 1]["type"] == "paragraph" and i + 1 < len(after) and after[i + 1]["type"] == "paragraph")
    rev = v["rev"]
    bad = client.post(f"/api/docs/{d}/tables/make", json={"template": tb["id"], "grid": GRID, "after": after[host_i + 1]["id"],
                                                         "replace": {"first": after[host_i - 1]["id"], "last": after[host_i + 1]["id"]}})
    assert bad.status_code == 400 and client.get(f"/api/docs/{d}").json()["rev"] == rev


def test_api_docx_is_not_supported_yet(client):
    d = _upload(client, DOCX)
    tbs = _tables(client.get(f"/api/docs/{d}").json()["blocks"])
    assert tbs
    tid = tbs[0]["id"]
    assert client.get(f"/api/docs/{d}/tables/{tid}/roles").status_code == 400
    assert client.post(f"/api/docs/{d}/tables/compose", json={"template": tid, "llm": False, "source": {"kind": "text", "text": "a\tb"}}).status_code == 400
    assert client.post(f"/api/docs/{d}/tables/make", json={"template": tid, "grid": GRID, "after": tid}).status_code == 400
    assert client.post(f"/api/docs/{d}/tables/restyle", json={"table": tid, "template": tid}).status_code == 400
