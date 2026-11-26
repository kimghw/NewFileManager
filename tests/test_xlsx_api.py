"""엑셀 시트 편집 끝점(spec_엑셀편집 ② §1 · §6) — 올리기(문서 올리기 길로도) · 칸 · 행 · 실행 취소 · 내려받기 · 다시 열기."""
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app import server, xlsx_api


@pytest.fixture
def client():
    xlsx_api.BOOKS.clear()
    return TestClient(server.app)


def _xlsx():
    wb = Workbook()
    ws = wb.active
    ws.title = "참고문헌"
    ws.append(["번호", "저자", "제목"])
    ws.append([1, "홍길동", "연구 A"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _up(client, path="/api/sheets", name="refs.xlsx", data=None, q=""):
    return client.post(path + q, files={"file": (name, data or _xlsx(), "application/octet-stream")})


def test_upload_edit_rows_undo_download(client):
    r = _up(client)
    assert r.status_code == 200, r.text
    d = r.json()
    wid = d["docId"]
    assert d["open"] == f"/sheet#w={wid}" and d["reused"] is False
    v = client.get(f"/api/sheets/{wid}").json()
    assert v["sheets"][0]["name"] == "참고문헌" and v["rev"] == 0
    r = client.put(f"/api/sheets/{wid}/cells", json={"sheet": 0, "rev": 0, "cells": [{"r": 3, "c": 1, "text": "2"}, {"r": 3, "c": 2, "text": "김철수"}]})
    assert r.status_code == 200, r.text
    assert r.json()["rev"] == 1 and r.json()["cells"][0][5] == "n"
    assert client.put(f"/api/sheets/{wid}/cells", json={"sheet": 0, "rev": 0, "cells": [{"r": 1, "c": 1, "text": "x"}]}).status_code == 409
    r = client.post(f"/api/sheets/{wid}/rows", json={"sheet": 0, "rev": 1, "op": "insert", "at": 2, "n": 1})
    assert r.status_code == 200 and r.json()["rev"] == 2
    ws = load_workbook(io.BytesIO(client.get(f"/api/sheets/{wid}/download").content)).active
    assert ws["B3"].value == "홍길동" and ws["B4"].value == "김철수" and ws["B2"].value is None
    r = client.post(f"/api/sheets/{wid}/undo", json={"sheet": 0})
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(client.get(f"/api/sheets/{wid}/download").content)).active
    assert ws["B2"].value == "홍길동" and ws["B3"].value == "김철수"
    # 메모리를 비워도 작업 폴더의 지금 상태로 다시 연다
    xlsx_api.BOOKS.clear()
    v = client.get(f"/api/sheets/{wid}").json()
    assert v["rev"] == 3 and any(c[:3] == [3, 2, "김철수"] for c in v["sheet"]["cells"])


def test_docs_upload_routes_xlsx_and_get_doc_points_to_sheet(client):
    r = _up(client, path="/api/docs", q="?ask=1")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["format"] == "xlsx" and d["open"].startswith("/sheet#w=")
    g = client.get(f"/api/docs/{d['docId']}").json()
    assert g["format"] == "xlsx" and g["open"] == d["open"]
    again = _up(client, path="/api/docs").json()   # 같은 파일 = 이어 엶
    assert again["docId"] == d["docId"] and again["reused"] is True
    assert _up(client, path="/api/docs", q="?new=1").json()["docId"] != d["docId"]


def test_refuses_other_excel_and_broken(client):
    assert _up(client, name="old.xls").status_code == 400
    assert _up(client, path="/api/docs", name="m.xlsm").status_code == 400
    assert _up(client, name="bad.xlsx", data=b"not a zip").status_code == 400


def test_merged_cell_error_keeps_doc(client):
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "병합"
    ws.merge_cells("A1:B1")
    buf = io.BytesIO()
    wb.save(buf)
    wid = _up(client, data=buf.getvalue()).json()["docId"]
    r = client.put(f"/api/sheets/{wid}/cells", json={"sheet": 0, "cells": [{"r": 2, "c": 1, "text": "ok"}, {"r": 1, "c": 2, "text": "x"}]})
    assert r.status_code == 400 and "병합" in r.json()["detail"]
    v = client.get(f"/api/sheets/{wid}").json()
    assert v["rev"] == 0 and not any(c[:2] == [2, 1] for c in v["sheet"]["cells"])


def test_page_served(client):
    r = client.get("/sheet")
    assert r.status_code == 200 and "/static/sheet/sheet.js?v=" in r.text
