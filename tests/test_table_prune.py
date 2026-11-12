"""빈 필드 제거(spec_헤딩_추출 ② §16): 빈 칸 판정 · 빈 줄(합계·수식 칸 제외) · 행 묶음째 비면 딸린 줄도 · 묶음 제목을 남기는 열 띠 ·
hwpx 지우기(OWPML 검사·다시 열기) · API(미리보기·지우기·실행 취소·409/400·hwpx 만)."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
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
    out = P.apply(d, tid, rows=True, cols=True, store=copy.deepcopy(EMPTY))
    assert out == {"rows": [3, 4, 5, 6, 7, 8], "cols": [], "skipRows": [], "skipCols": []}
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
    out = P.apply(d, tid, rows=True, cols=True, store=copy.deepcopy(EMPTY))
    assert out == {"rows": [4, 5, 6], "cols": [], "skipRows": [], "skipCols": []}
    nb = d.table_block(tid)
    assert nb["nRows"] == 6 and sum(c["rowSpan"] * c["colSpan"] for c in nb["cells"]) == 6 * 5  # 구멍·겹침 없음
    by_text = {" ".join(q.get("text") or "" for q in c.get("blocks") or []).split(" ")[0]: c for c in nb["cells"]}
    assert by_text["회수율"]["rowSpan"] == 3 and (by_text["정밀도"]["row"], by_text["정밀도"]["rowSpan"]) == (4, 2)  # 묶음 제목은 글째 남고 남은 행으로
    assert C.verdict(d, base, C.check_doc(d))["status"] != "fail"
    HwpxDoc(d.save())


def test_apply_drops_empty_columns_and_keeps_table_width():
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    tid = _find(d, "보안등급 분류", (7, 4))  # 번호 | 분류 | 점검 결과(예 · 아니오 — 빈 열 둘, 위 「점검 결과」 는 두 열에 걸친 제목)
    b = d.table_block(tid)
    p = P.plan(d, tid, store=copy.deepcopy(EMPTY))
    assert p["emptyCols"] == [2, 3] and p["emptyRows"] == [] and p["colNames"] == {"2": "예", "3": "아니오"}
    width = int(d._ids[tid].find("{*}sz").get("width"))
    base = C.counts(C.check_doc(d))
    assert P.apply(d, tid, rows=True, cols=False, store=copy.deepcopy(EMPTY)) == {"rows": [], "cols": [], "skipRows": [], "skipCols": []}
    out = P.apply(d, tid, rows=False, cols=True, store=copy.deepcopy(EMPTY))
    assert out["cols"] == [2, 3] and out["skipCols"] == []
    nb = d.table_block(tid)
    assert nb["nCols"] == b["nCols"] - 2 and nb["nRows"] == b["nRows"] - 1  # 「예·아니오」 줄에서 시작하는 칸이 없어져 머리 두 줄이 한 줄로 접힌다(빈 hp:tr 방지)
    assert sum(c["rowSpan"] * c["colSpan"] for c in nb["cells"]) == nb["nRows"] * nb["nCols"]
    assert int(d._ids[tid].find("{*}sz").get("width")) == width  # 지운 폭은 남은 열이 나눠 가짐
    assert not any("점검 결과" in (q.get("text") or "") for c in nb["cells"] for q in c.get("blocks") or [])
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
    assert p["emptyRows"] == [3, 4, 5, 6, 7, 8] and p["rev"] == client.get(f"/api/docs/{d}").json()["rev"]
    assert client.get(f"/api/docs/{d}").json()["pristine"] is True  # 미리보기는 문서를 안 바꾼다
    assert client.post(url, json={"rows": True, "rev": p["rev"] + 5}).status_code == 409  # 미리 본 뒤 문서가 바뀜
    assert client.post(url, json={"rows": False, "cols": False}).status_code == 400
    assert client.post(url, json={"rows": False, "cols": True}).status_code == 400  # 빈 열이 없다 — 아무것도 안 바뀜
    assert client.get(f"/api/docs/{d}").json()["pristine"] is True
    r = client.post(url, json={"rows": True, "cols": False, "rev": p["rev"]})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["pruned"] == {"table": big["id"], "rows": [3, 4, 5, 6, 7, 8], "cols": [], "skipRows": [], "skipCols": []} and v["undo"] == 1
    now = next(b for b in v["tops"]["blocks"] if b["id"] == big["id"])
    assert now["nRows"] == big["nRows"] - 6
    assert client.post(url, json={"dry": True}).json()["emptyRows"] == []
    assert client.post(url, json={}).status_code == 400  # 더 지울 줄이 없다
    assert client.post(f"/api/docs/{d}/undo").status_code == 200
    back = client.get(f"/api/docs/{d}").json()
    assert back["pristine"] is True and max(_tables(back["blocks"]), key=lambda b: b["nRows"])["nRows"] == big["nRows"]
    assert client.post(f"/api/docs/{d}/tables/t9999/prune", json={"dry": True}).status_code == 404
    assert [e["kind"] for e in client.get(f"/api/works/{d}/log").json()["events"]].count("tablePrune") == 1


def test_api_prune_docx_is_hwpx_only(client):
    d = _upload(client, DOCX)
    tb = _tables(client.get(f"/api/docs/{d}").json()["blocks"])[0]
    for body in ({"dry": True}, {"rows": True}):
        r = client.post(f"/api/docs/{d}/tables/{tb['id']}/prune", json=body)
        assert r.status_code == 400 and "hwpx" in r.json()["detail"]
