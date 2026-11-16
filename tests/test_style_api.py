"""서식 보관함 끝점(spec_일반편집 ② §7): 보관함(목록·읽기·고치기·지우기) · 문서에서 저장(표·구조·글) · 적용(새 표·빈 표·입히기·글 서식 — 실행 취소·OWPML) · 추출·검증 모듈 붙이기 · 상태 코드."""
import io
import types
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import doc_agent, works
from app import heading_rules as R
from app import server, style_api, style_apply, style_carrier, style_lib, table_make
from app.hwpx_doc import HwpxDoc

if not any(getattr(r, "path", "") == "/api/styles" for r in server.app.routes):  # 서버가 아직 이 라우터를 안 물었으면 여기서
    server.app.include_router(style_api.router)

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, RND, DOCX = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "연구개발계획서_양식.hwpx", SAMPLES / "기술수요조사서.docx"
GRID = {"rows": [["구분", "2024", "2025"], ["매출", "1,200", "1,450"], ["합계", "2,000", "2,350"]], "headerRows": 1, "footRows": 1}
REAL_MOD = style_api._mod


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    monkeypatch.setattr(style_api, "_mod", lambda name: None)  # 추출·검증 모듈 없이(검증 스레드가 시험 사이로 새지 않게) — 붙이는 시험은 가짜 모듈을 준다
    R._MEMORY.clear()
    yield
    R._MEMORY.clear()


@pytest.fixture()
def client():
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _save(c, d, **body):
    r = c.post(f"/api/docs/{d}/styles", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _cell_paras(c, d, table="t8"):
    tb = next(b for b in c.get(f"/api/docs/{d}").json()["blocks"] if b["id"] == table)
    return [x["id"] for cell in tb["cells"] for x in cell["blocks"] if x["type"] == "paragraph" and x["text"].strip()]


def _kinds(c, d):
    return [e["kind"] for e in c.get(f"/api/works/{d}/log").json()["events"]]


# ---- 보관함 --------------------------------------------------------------------------------------------------------

def test_save_list_get_put_delete(client):
    assert client.get("/api/styles").json() == {"enabled": True, "pdf": False, "pdfDocx": False, "broken": [], "styles": []}  # pdfDocx = Word 출력이 되나(spec_서식복사 ② §8)
    d = _upload(client, SMALL)
    m = _save(client, d, kind="table", table="t8", name="수요조사  표")
    sid = m["id"]
    assert m["revision"] == "r1" and m["name"] == "수요조사 표" and m["kind"] == "table" and (m["rows"], m["cols"]) == (18, 11) and m["fidelity"] == "native" and m["verify"] is None
    assert m["bands"] == {"headerRows": 0, "headerCols": 1, "footRows": 0} and m["blueprint"] is None and m["losses"] and m["requirements"]["fonts"]
    assert m["source"]["name"] == SMALL.name and m["source"]["format"] == "hwpx" and m["source"]["work"] == d and m["source"]["block"] == "t8" and len(m["source"]["sha256"]) == 64
    assert client.get(f"/api/docs/{d}").json()["pristine"] is True and "styleSave" in _kinds(client, d)  # 저장은 문서를 안 바꾼다
    got = client.get("/api/styles").json()["styles"]
    assert len(got) == 1 and got[0]["id"] == sid and got[0]["losses"] == len(m["losses"]) and got[0]["blueprint"] is False and got[0]["verify"] is None and got[0]["preview"]["looks"]["stub"]
    full = client.get(f"/api/styles/{sid}").json()
    assert full["losses"] == m["losses"] and full["view"]["table"] == "t2" and len(full["view"]["grid"]["rows"]) == 18 and full["view"]["spec"]["cols"] == 11 and "viewError" not in full
    assert full["view"]["grid"]["rows"][0]["cells"][0]["text"] == "제안기술 분류" and full["view"]["grid"]["rows"][0]["cells"][1]["text"] == "가나다"  # 자료값은 견본으로
    car = client.get(f"/api/styles/{sid}/carrier")
    assert car.status_code == 200 and car.headers["content-type"] == "application/hwp+zip" and ".hwpx" in car.headers["content-disposition"]
    assert HwpxDoc(car.content).table_block("t2") is None and style_carrier.doc(car.content).table_block("t2")["nRows"] == 18 and car.content == style_lib.carrier(sid)
    assert client.get(f"/api/styles/{sid}/proof.png").status_code == 404
    # 고치기 — 새 revision · 낡은 revision 409
    p = client.put(f"/api/styles/{sid}", json={"expectedRevision": "r1", "name": "새 이름", "note": "메모", "bands": {"headerRows": 1}})
    assert p.status_code == 200 and p.json()["revision"] == "r2" and p.json()["name"] == "새 이름" and p.json()["note"] == "메모" and p.json()["bands"] == {"headerRows": 1, "headerCols": 1, "footRows": 0}
    assert client.put(f"/api/styles/{sid}", json={"expectedRevision": "r1", "name": "늦은 쪽"}).status_code == 409
    assert client.put(f"/api/styles/{sid}", json={"expectedRevision": "r2", "name": " "}).status_code == 400
    assert client.put(f"/api/styles/{sid}", json={"expectedRevision": "r2", "items": [{"key": "i1", "name": "x"}]}).status_code == 400  # 표 서식에 items
    bp = {"cells": [{"row": 0, "col": 0, "rowSpan": 3, "colSpan": 1, "role": "label", "label": "클라이언트가 보낸 글"}, {"row": 0, "col": 1, "role": "input", "label": "자료값"},
                    {"row": 0, "col": 2, "role": "note", "label": "원본의 자료값"}], "formulas": [{"ref": "B1", "formula": "=A1"}]}
    b = client.put(f"/api/styles/{sid}", json={"expectedRevision": "r2", "blueprint": bp})
    assert b.status_code == 200 and b.json()["revision"] == "r3" and b.json()["blueprint"]["cells"][1] == {"row": 0, "col": 1, "rowSpan": 1, "colSpan": 1, "role": "input", "label": None}  # 채울 칸의 글은 안 싣는다
    assert [c["label"] for c in b.json()["blueprint"]["cells"]] == ["제안기술 분류", None, "가나다"]  # 라벨 글은 운반 문서에 남긴 글에서만(보낸 글은 안 쓴다 — 자료값이 그 길로 들어오지 않게)
    assert client.get("/api/styles").json()["styles"][0]["blueprint"] is True
    for bad in ({"cells": [{"row": 0, "col": 0, "role": "total"}]}, {"cells": [{"row": 99, "col": 0, "role": "label"}]}, {"cells": "x"}, "x"):
        assert client.put(f"/api/styles/{sid}", json={"expectedRevision": "r3", "blueprint": bad}).status_code == 400
    assert client.put(f"/api/styles/{sid}", json={"expectedRevision": "r3", "blueprint": None}).json()["blueprint"] is None
    assert style_lib.get(sid)["revision"] == "r4" and style_lib.carrier(sid) == car.content  # 운반 문서는 그대로
    # 없는 id · 지우기
    for path in ("/api/styles/ffffffffffff", "/api/styles/nope", "/api/styles/ffffffffffff/carrier", "/api/styles/ffffffffffff/proof.png"):
        assert client.get(path).status_code == 404
    assert client.put("/api/styles/ffffffffffff", json={"name": "x"}).status_code == 404 and client.delete("/api/styles/ffffffffffff").status_code == 404
    assert client.delete(f"/api/styles/{sid}?expectedRevision=r1").status_code == 409 and style_lib.get(sid) is not None
    gone = client.delete(f"/api/styles/{sid}?expectedRevision=r4")
    assert gone.status_code == 200 and gone.json() == {"deleted": sid} and client.get(f"/api/styles/{sid}").status_code == 404 and client.delete(f"/api/styles/{sid}?expectedRevision=").status_code == 404


def test_put_and_delete_require_expected_revision(client, tmp_path):
    """astra 14: expectedRevision 을 빼면 revision 검사를 건너뛰어, 오래된 화면이 남의 고침을 덮어쓰거나 지웠다 — 성한 템플릿의 PUT·DELETE 는 꼭 받는다(없으면 400 · 다르면 409).
    깨진 템플릿(읽을 revision 이 없다)을 지울 때만 없이 된다 — 운반 문서가 없어졌거나 바뀐(해시가 다른) 것도 깨진 것이다."""
    d = _upload(client, SMALL)
    sid = _save(client, d, kind="table", table="t8", name="표")["id"]
    for body in ({"name": "몰래"}, {"expectedRevision": "", "name": "몰래"}, {"expectedRevision": None, "name": "몰래"}, {"expectedRevision": "1", "name": "몰래"}, {"expectedRevision": 1, "name": "몰래"}):
        r = client.put(f"/api/styles/{sid}", json=body)
        assert r.status_code == 400 and "expectedRevision" in r.json()["detail"], (body, r.text)
    for q in ("", "?expectedRevision=", "?expectedRevision=latest"):
        r = client.delete(f"/api/styles/{sid}{q}")
        assert r.status_code == 400 and "expectedRevision" in r.json()["detail"], (q, r.text)
    assert style_lib.get(sid)["name"] == "표" and style_lib.get(sid)["revision"] == "r1"  # 아무것도 안 바뀌었다
    assert client.put(f"/api/styles/{sid}", json={"expectedRevision": "r9", "name": "x"}).status_code == 409 and client.delete(f"/api/styles/{sid}?expectedRevision=r9").status_code == 409
    other = _save(client, d, kind="table", table="t1", name="둘")["id"]
    (tmp_path / "styles" / other / "revisions" / "r1" / "carrier.hwpx").write_bytes(b"altered carrier")  # 운반 문서가 바뀜(해시가 meta 와 다르다)
    got = client.get("/api/styles").json()
    assert got["broken"] == [other] and [s["id"] for s in got["styles"]] == [sid]  # 정상 목록에 섞지 않는다
    assert client.get(f"/api/styles/{other}").status_code == 404 and client.get(f"/api/styles/{other}/carrier").status_code == 404
    assert client.put(f"/api/styles/{other}", json={"expectedRevision": "r1", "name": "성한 것으로"}).status_code == 404
    assert client.post(f"/api/docs/{d}/styles/{other}/apply", json={"mode": "tableBlank", "after": "t8"}).status_code == 404  # 적용의 원본이 되지 못한다
    assert client.delete(f"/api/styles/{other}").status_code == 200 and client.get("/api/styles").json()["broken"] == []  # 깨진 것은 expectedRevision 없이 지운다
    assert client.delete(f"/api/styles/{sid}?expectedRevision=r1").status_code == 200 and client.get("/api/styles").json()["styles"] == []


def test_library_off_is_503_but_builtin_still_applies(client, monkeypatch):
    d = _upload(client, SMALL)
    monkeypatch.setenv("NFM_STYLES", "off")
    assert client.get("/api/styles").json() == {"enabled": False, "pdf": False, "pdfDocx": False, "broken": [], "styles": []}
    sid = "a" * 12
    for r in (client.get(f"/api/styles/{sid}"), client.put(f"/api/styles/{sid}", json={"name": "x"}), client.delete(f"/api/styles/{sid}"), client.post(f"/api/styles/{sid}/verify"),
              client.get(f"/api/styles/{sid}/carrier"), client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": "t8"}),
              client.post(f"/api/docs/{d}/styles/{sid}/apply", json={"mode": "tableBlank", "after": "t8"}),
              client.post("/api/styles/from-file", json={"token": "t", "picks": [{"kind": "table", "key": "k"}]})):
        assert r.status_code == 503 and "꺼져" in r.json()["detail"], r.text
    ok = client.post(f"/api/docs/{d}/styles/builtin/apply", json={"mode": "tableMake", "after": "t8", "grid": GRID})  # 기본 표는 보관함 없이도
    assert ok.status_code == 200 and ok.json()["made"]["rows"] == 3


def test_broken_style_is_listed_and_can_be_deleted(client, tmp_path):
    d = _upload(client, SMALL)
    a, b = _save(client, d, kind="table", table="t8", name="하나")["id"], _save(client, d, kind="table", table="t1", name="둘")["id"]
    (tmp_path / "styles" / a / "revisions" / "r1" / "meta.json").write_text("{", "utf-8")
    got = client.get("/api/styles").json()
    assert got["broken"] == [a] and [s["id"] for s in got["styles"]] == [b]
    assert client.get(f"/api/styles/{a}").status_code == 404 and client.put(f"/api/styles/{a}", json={"name": "x"}).status_code == 404
    assert client.post(f"/api/docs/{d}/styles/{a}/apply", json={"mode": "tableBlank", "after": "t8"}).status_code == 404
    assert client.delete(f"/api/styles/{a}").status_code == 200 and client.get("/api/styles").json()["broken"] == []


# ---- 문서에서 저장 ---------------------------------------------------------------------------------------------------

def test_save_table_keep_text_and_blueprint(client):
    d = _upload(client, SMALL)
    kept = _save(client, d, kind="table", table="t8", keepText=True, bands={"headerRows": 0, "headerCols": 0, "footRows": 0})
    grid = client.get(f"/api/styles/{kept['id']}").json()["view"]["grid"]
    assert kept["name"] == "표 18×11" and kept["labels"] == [] and "전력변환시스템" in grid["rows"][0]["cells"][1]["text"] and grid["headerCols"] == 0  # keepText = 글 그대로 · 이름 기본값은 라벨 칸의 글에서만(띠가 없으면 크기)
    named = _save(client, d, kind="table", table="t8")
    assert named["name"] == "제안기술 분류 표" and named["labels"][0] == [0, 0] and all(c == 0 for _, c in named["labels"])  # 이름 기본값 = 첫 라벨 칸의 글 · labels = 글을 남긴 칸(머리열)
    m = _save(client, d, kind="table", table="t8", blueprint=True, name="구조까지")
    cells = m["blueprint"]["cells"]
    assert len(cells) == len(next(b for b in client.get(f"/api/docs/{d}").json()["blocks"] if b["id"] == "t8")["cells"]) and m["blueprint"]["formulas"] == []
    assert cells[0] == {"row": 0, "col": 0, "rowSpan": 3, "colSpan": 1, "role": "label", "label": "제안기술 분류"}
    assert {c["role"] for c in cells} == {"label", "input"} and all((c["role"] == "label") == (c["col"] == 0) for c in cells)
    assert all(c["label"] is None for c in cells if c["role"] != "label")  # 채울 칸의 글(자료값)은 저장하지 않는다
    # 빈 표 넣기 — blueprint 의 input 칸은 비고 label 은 남는다
    r = client.post(f"/api/docs/{d}/styles/{m['id']}/apply", json={"mode": "tableBlank", "after": "t8"})
    assert r.status_code == 200, r.text
    made = next(b for b in r.json()["tops"]["blocks"] if b["id"] == r.json()["made"]["table"])
    assert r.json()["made"]["rows"] == 18 and {c["text"] for c in made["cells"] if c["col"] > 0} == {""} and [c["text"] for c in made["cells"] if c["col"] == 0][0] == "제안기술 분류"
    for bad, code in (({"kind": "table", "table": "t9999"}, 404), ({"kind": "table", "table": "p10"}, 404), ({"kind": "chart"}, 400), ({"kind": "table", "table": "t8", "name": "가" * 61}, 400)):
        assert client.post(f"/api/docs/{d}/styles", json=bad).status_code == code, bad
    assert client.post("/api/docs/nope/styles", json={"kind": "table", "table": "t8"}).status_code == 404


def test_save_text_from_paras_and_template(client, monkeypatch):
    d = _upload(client, SMALL)
    paras = _cell_paras(client, d)
    doc = server.DOCS[d].doc
    tokens = list(dict.fromkeys(doc.get_format(i)["token"] for i in paras))
    assert 1 < len(tokens) < len(paras)
    m = _save(client, d, kind="text", paras=paras)
    assert m["kind"] == "text" and m["name"] == "문단 서식" and len(m["items"]) == len(tokens) and [i["key"] for i in m["items"]] == [f"i{n}" for n in range(1, len(tokens) + 1)]
    assert all(i["level"] is None and i["origin"]["template"] is None for i in m["items"]) and m["items"][0]["origin"]["para"] == paras[0]  # 서식이 같은 문단은 하나로 · 레벨은 지어내지 않는다
    v = client.get(f"/api/styles/{m['id']}").json()["view"]
    assert len(v["paras"]) == len(tokens) and v["items"] == m["items"] and m["source"]["block"] == paras[0]
    p = client.put(f"/api/styles/{m['id']}", json={"expectedRevision": "r1", "items": [{"key": "i2", "name": "둘째 수준", "level": 2}]})
    assert p.status_code == 200 and [(i["name"], i["level"]) for i in p.json()["items"]][1] == ("둘째 수준", 2) and p.json()["items"][0] == m["items"][0]
    for bad in ([{"key": "i99", "name": "x"}], [{"key": "i1", "name": ""}], [{"key": "i1", "level": 0}], "x"):
        r = client.put(f"/api/styles/{m['id']}", json={"expectedRevision": "r2", "items": bad})
        assert r.status_code == 400 and "expectedRevision" not in r.json()["detail"], r.text
    r = client.put(f"/api/styles/{m['id']}", json={"expectedRevision": "r2", "bands": {"headerRows": 1}})
    assert r.status_code == 400 and "글 서식은 items" in r.json()["detail"]  # 글 서식에 띠 수
    for bad, code in (({"kind": "text", "paras": []}, 400), ({"kind": "text"}, 400), ({"kind": "text", "paras": ["p99999"]}, 404), ({"kind": "text", "paras": ["t8"]}, 404),
                      ({"kind": "text", "template": 1}, 400)):  # 2단계 그래프가 없으면 템플릿으로는 못 저장
        assert client.post(f"/api/docs/{d}/styles", json=bad).status_code == code, bad
    graph = {"templates": [{"id": 3, "no": 3, "name": "N.", "chain": ["N.", "□"], "slots": [
        {"level": 1, "letter": "N.", "format": "p1|c1", "rep": paras[0]}, {"level": 2, "letter": "□", "format": "p2|c2", "rep": paras[2]},
        {"level": 3, "letter": "o", "format": None, "rep": paras[1]}, {"level": 4, "letter": "-", "format": "p3|c3", "rep": "p99999"}]}]}
    monkeypatch.setattr(style_api.heading_runs, "graph", lambda s: graph)
    t = _save(client, d, kind="text", template=3, name="개요템플릿 글")
    assert [(i["level"], i["origin"], i["name"]) for i in t["items"]] == [(1, {"template": 3, "slot": 1, "para": paras[0]}, "1수준 N."), (2, {"template": 3, "slot": 2, "para": paras[2]}, "2수준 □")]
    assert client.post(f"/api/docs/{d}/styles", json={"kind": "text", "template": 9}).status_code == 404
    assert _save(client, d, kind="text", template="3")["name"] == "템플릿 3 글 서식"


def test_para_style_role_is_saved_listed_and_edited(client):
    """문단 서식의 역할(spec_서식복사 ② §12): 저장 `{kind: "text", paras, role?}` · meta `role`(정해진 코드나 null — 틀린 값 400) · `PUT {role}`(레벨 없는 글 서식만) · 목록 요약의 `role`·`leveled`."""
    d = _upload(client, SMALL)
    paras = _cell_paras(client, d)
    m = _save(client, d, kind="text", paras=paras[:1], role="caption", name="캡션 글")
    sid, url = m["id"], f"/api/styles/{m['id']}"
    assert m["role"] == "caption" and style_lib.get(sid)["role"] == "caption" and _save(client, d, kind="text", paras=paras, name="역할 없이")["role"] is None
    row = next(s for s in client.get("/api/styles").json()["styles"] if s["id"] == sid)
    assert (row["role"], row["leveled"]) == ("caption", False)                                          # 문단 서식 = 레벨 없는 글 서식
    for bad in ("제목", "title", "", 3):
        r = client.post(f"/api/docs/{d}/styles", json={"kind": "text", "paras": paras[:1], "role": bad})
        assert r.status_code == 400 and "role" in r.json()["detail"], bad
    p = client.put(url, json={"expectedRevision": "r1", "role": "note"})
    assert p.status_code == 200 and (p.json()["role"], p.json()["revision"]) == ("note", "r2") and style_lib.carrier(sid) == style_lib.carrier(sid, "r1")   # 운반 문서는 그대로
    assert client.put(url, json={"expectedRevision": "r2", "role": None}).json()["role"] is None       # r3 — 모름으로
    r = client.put(url, json={"expectedRevision": "r3", "role": "heading"})
    assert r.status_code == 400 and "role" in r.json()["detail"] and style_lib.get(sid)["revision"] == "r3"
    r = client.put(url, json={"expectedRevision": "r3", "role": "body", "items": [{"key": "i1", "level": 1}]})   # 같은 요청으로 레벨을 붙이면서 역할을 줄 수는 없다
    assert r.status_code == 400 and "문단 서식" in r.json()["detail"]
    lv = client.put(url, json={"expectedRevision": "r3", "items": [{"key": "i1", "level": 1}]})          # 레벨이 붙으면 내용 서식 — 역할은 없다
    assert lv.status_code == 200 and lv.json()["role"] is None and lv.json()["revision"] == "r4"
    assert client.put(url, json={"expectedRevision": "r4", "role": "body"}).status_code == 400
    row = next(s for s in client.get("/api/styles").json()["styles"] if s["id"] == sid)
    assert (row["role"], row["leveled"]) == (None, True)
    t = _save(client, d, kind="table", table="t8")
    assert client.put(f"/api/styles/{t['id']}", json={"expectedRevision": "r1", "role": "body"}).status_code == 400   # 표 서식에 역할
    trow = next(s for s in client.get("/api/styles").json()["styles"] if s["id"] == t["id"])
    assert "role" not in trow and "leveled" not in trow


def test_template_save_takes_rep_only_from_the_same_slot(client, monkeypatch):
    """템플릿 저장의 `rep`(spec_서식복사 ② §15·§16 — LLM 이 고른 대표 문단 {레벨: 문단 id}): 그래프의 `nodes` 에서 **그 템플릿 그 레벨의 문단**일 때만 받는다 — 아니면 400(다른 문단의 서식이 그 레벨로 저장되지 않게)."""
    d = _upload(client, SMALL)
    paras = _cell_paras(client, d)
    doc = server.DOCS[d].doc
    a, c = paras[0], paras[1]
    b = next((p for p in paras[2:] if doc.get_format(p)["token"] != doc.get_format(a)["token"]), paras[2])   # 1수준의 다른 문단(되도록 서식이 다른 것)
    other = next(p for p in paras if p not in (a, b, c))
    node = lambda pid, no, level: {"id": f"n{pid}", "para": pid, "template": "N." if no == 3 else "다른", "tplNo": no, "level": level}  # noqa: E731
    graph = {"templates": [{"id": 3, "no": 3, "anchor": "N.", "name": "N.", "chain": ["N.", "□"], "slots": [{"level": 1, "letter": "N.", "format": "p1|c1", "rep": a},
                                                                                                         {"level": 2, "letter": "□", "format": "p2|c2", "rep": c}]}],
             "nodes": [node(a, 3, 1), node(b, 3, 1), node(c, 3, 2), node(other, 4, 1), node("p99999", 3, 1)]}
    monkeypatch.setattr(style_api.heading_runs, "graph", lambda s: graph)
    url = f"/api/docs/{d}/styles"
    base = _save(client, d, kind="text", template=3, name="스크립트 대표")
    assert [i["origin"]["para"] for i in base["items"]] == [a, c] and base["role"] is None
    picked = _save(client, d, kind="text", template=3, rep={"1": b}, name="고른 대표")
    assert [(i["level"], i["origin"]["para"], i["origin"]["slot"]) for i in picked["items"]] == [(1, b, 1), (2, c, 2)]   # 그 레벨만 바뀐다
    assert picked["items"][0]["format"] != base["items"][0]["format"] or doc.get_format(a)["summary"] == doc.get_format(b)["summary"]
    for bad in ({"1": other}, {"2": b}, {"9": a}, {"x": a}, {"1": 3}, "p1", [b]):
        r = client.post(url, json={"kind": "text", "template": 3, "rep": bad})
        assert r.status_code == 400 and "rep" in r.json()["detail"], bad
    assert client.post(url, json={"kind": "text", "template": 3, "rep": {"1": "p99999"}}).status_code == 404   # 그래프에는 있는데 문서에서 지워진 문단
    r = client.post(url, json={"kind": "text", "paras": [a], "rep": {"1": b}})
    assert r.status_code == 400 and "rep" in r.json()["detail"]                                         # rep 는 템플릿 저장에만
    r = client.post(url, json={"kind": "text", "template": 3, "role": "body"})
    assert r.status_code == 400 and "role" in r.json()["detail"]                                        # 개요템플릿의 글 서식에는 역할이 없다
    assert _save(client, d, kind="text", template=3, rep={}, name="빈 rep")["items"][0]["origin"]["para"] == a


def test_saved_table_template_carries_no_source_values(client):
    """astra 10: 머리글 없는 표를 저장하면 첫 행(관례로 머리행)의 이름·주민번호가 기본 이름·미리보기·구조(blueprint)·보기·운반 문서에 남았고, 빈 표를 넣으면 다시 나왔다."""
    d = _upload(client, SMALL)
    people = {"rows": [["홍길동", "910101-1234567"], ["김철수", "920202-2345678"]]}
    made = client.post(f"/api/docs/{d}/styles/builtin/apply", json={"mode": "tableMake", "after": "t8", "grid": people})  # 음영·굵게 없는 표
    assert made.status_code == 200, made.text
    m = _save(client, d, kind="table", table=made.json()["made"]["table"], blueprint=True)
    assert m["name"] == "표 2×2" and m["bands"]["headerRows"] == 1 and m["labels"] == []  # 띠 수는 관례대로 첫 행(서식의 구역) — 글을 남길 라벨은 없다
    assert [(c["role"], c["label"]) for c in m["blueprint"]["cells"]] == [("input", None)] * 4
    full = client.get(f"/api/styles/{m['id']}").json()
    shown = [c["text"] for g in (m["preview"]["grid"], full["view"]["grid"]) for r in g["rows"] for c in r["cells"]] + [c["text"] for c in full["view"]["spec"]["cells"]]
    assert set(shown) == {"가나다", "0"}
    z = zipfile.ZipFile(io.BytesIO(style_lib.carrier(m["id"])))
    raw = "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist()) + str(m) + str(full)
    assert not [s for s in ("홍길동", "김철수", "910101", "1234567", "920202") if s in raw]
    for sid in (m["id"], _save(client, d, kind="table", table=made.json()["made"]["table"], name="구조 없이")["id"]):  # 구조(blueprint)가 있든 없든
        r = client.post(f"/api/docs/{d}/styles/{sid}/apply", json={"mode": "tableBlank", "after": "t8"})
        assert r.status_code == 200, r.text
        blank = next(b for b in r.json()["tops"]["blocks"] if b["id"] == r.json()["made"]["table"])
        assert [c["text"] for c in blank["cells"]] == [""] * 4  # 견본 글(「가나다」)이 머리 띠라는 까닭으로 남지 않는다


def test_docx_documents_take_only_blank_table_and_format(client):
    """spec_서식복사 ② §6·§9: docx 문서도 서식을 저장하지만(표 = 명세로 다시 지음 — summary), 적용은 빈 표 넣기 · 문단에 입히기만 — 그 밖의 모드와 개요템플릿 저장은 400."""
    d = _upload(client, DOCX)
    tid = max((b for b in client.get(f"/api/docs/{d}").json()["blocks"] if b["type"] == "table"), key=lambda b: len(b["cells"]))["id"]  # 20×6 자료 표(파일 추출의 후보와 같은 표)
    for mode in ("tableMake", "tableRestyle", "page", "cover"):  # cover = 표지 넣기(spec_서식복사 ② §14 — hwpx 문서만)
        r = client.post(f"/api/docs/{d}/styles/builtin/apply", json={"mode": mode, "after": tid, "table": tid, "grid": GRID})
        assert r.status_code == 400 and "빈 표 넣기 · 문단에 입히기만" in r.json()["detail"], r.text
    r = client.post(f"/api/docs/{d}/styles/builtin/apply", json={"mode": "tableBlank", "after": tid})
    assert r.status_code == 400 and "서식 보관함의 서식만" in r.json()["detail"]  # 기본 표 · 이 문서의 표는 hwpx 문서의 것
    r = client.post(f"/api/docs/{d}/styles", json={"kind": "text", "template": 1})
    assert r.status_code == 400 and "hwpx 문서만" in r.json()["detail"]
    assert client.post(f"/api/docs/{d}/styles/candidates", json={}).status_code == 501  # 추출 모듈 없이(이 파일의 _env) — 그 기능만 빠진다
    m = _save(client, d, kind="table", table=tid)
    assert (m["kind"], m["fidelity"], m["source"]["format"], m["source"]["block"], m["source"]["work"]) == ("table", "summary", "docx", tid, d) and m["docx"] is None  # style_docx 없이(_env) — docx: null
    assert client.get(f"/api/docs/{d}").json()["pristine"] is True and "styleSave" in _kinds(client, d)
    assert client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": "t99999"}).status_code == 404


# ---- 적용 ----------------------------------------------------------------------------------------------------------

def test_apply_from_another_document_then_undo_restores_bytes(client):
    src = _upload(client, RND)
    blocks = client.get(f"/api/docs/{src}").json()["blocks"]
    tpl = next(b for b in blocks if b["type"] == "table" and b["nRows"] >= 4 and b["nCols"] >= 3 and not table_make.block_nested(b)
               and table_make.roles_of(b["cells"], b["nRows"], b["nCols"]) == {"headerRows": 1, "headerCols": 0, "footRows": 1})
    para = lambda start: next(b["id"] for b in blocks if b["type"] == "paragraph" and b["text"].startswith(start))  # noqa: E731
    tm = _save(client, src, kind="table", table=tpl["id"], name="성과지표 표")
    xm = _save(client, src, kind="text", paras=[para("1. "), para("□ ")], name="본문 글")
    assert tm["bands"] == {"headerRows": 1, "headerCols": 0, "footRows": 1} and [i["marker"]["literal"] for i in xm["items"]] == ["1.", "□"]
    calc = _save(client, src, kind="table", table=blocks[[b["type"] for b in blocks].index("table")]["id"], blueprint=True, name="수식 표")  # 연구개발비 표(합계 수식)
    roles = [c["role"] for c in calc["blueprint"]["cells"]]
    assert "computed" in roles and calc["blueprint"]["formulas"] and set(calc["blueprint"]["formulas"][0]) == {"ref", "formula"} and calc["blueprint"]["formulas"][0]["formula"].startswith("=")
    assert all(c["label"] is None for c in calc["blueprint"]["cells"] if c["role"] != "label")

    d = _upload(client, SMALL)
    url, t0 = f"/api/docs/{d}/styles", [b["id"] for b in client.get(f"/api/docs/{d}").json()["blocks"]]
    r = client.post(f"{url}/{tm['id']}/apply", json={"mode": "tableMake", "after": "t8", "grid": GRID})
    assert r.status_code == 200, r.text
    v = r.json()
    new = v["made"]["table"]
    assert v["made"] == {"table": new, "rows": 3, "cols": 3} and v["undo"] == 1 and v["pristine"] is False and v["owpml"]["status"] != "fail"
    made = next(b for b in v["tops"]["blocks"] if b["id"] == new)
    assert [c["text"] for c in made["cells"]][:3] == ["구분", "2024", "2025"] and made["cells"][0]["fill"] == tm["preview"]["looks"]["head"]["fill"] and "t8" in v["tops"]["drop"]
    assert [b["id"] for b in client.get(f"/api/docs/{d}").json()["blocks"]] == [*t0, new]  # 넣을 자리 뒤 · 임시 블록 없음
    blank = client.post(f"{url}/{tm['id']}/apply", json={"mode": "tableBlank", "after": new})
    assert blank.status_code == 200 and (blank.json()["made"]["rows"], blank.json()["made"]["cols"]) == (tpl["nRows"], tpl["nCols"]) and blank.json()["undo"] == 2
    re_ = client.post(f"{url}/builtin/apply", json={"mode": "tableRestyle", "table": new, "bands": {"headerRows": 1}})
    assert re_.status_code == 200 and re_.json()["made"]["table"] == new and re_.json()["made"]["formatted"] > 0
    styled = next(b for b in re_.json()["tops"]["blocks"] if b["id"] == new)
    assert [c["text"] for c in styled["cells"]] == [c["text"] for c in made["cells"]] and {c["fill"] for c in styled["cells"]} == {None}  # 글 그대로 · 기본 표의 서식
    paras = _cell_paras(client, d)[:2]
    fm = client.post(f"{url}/{xm['id']}/apply", json={"mode": "format", "item": "i2", "paras": paras})
    assert fm.status_code == 200 and fm.json()["formatted"] == {"paras": 2} and fm.json()["undo"] == 4
    doc = server.DOCS[d].doc
    assert {k: doc.get_format(paras[0])["summary"][k] for k in ("font", "sizePt", "bold", "align")} == {k: xm["items"][1]["format"][k] for k in ("font", "sizePt", "bold", "align")}
    rp = client.post(f"{url}/doc:t1/apply", json={"mode": "tableMake", "after": new, "grid": GRID, "replace": {"table": new}})  # 이 문서의 표를 양식으로 · 바꿀 표를 지움
    assert rp.status_code == 200 and new not in [b["id"] for b in client.get(f"/api/docs/{d}").json()["blocks"]] and rp.json()["made"]["table"] != new
    later = client.post(f"/api/docs/{d}/format/chars", json={"id": paras[1], "start": 0, "end": 1, "changes": {"italic": True}})
    assert later.status_code == 200, later.text  # 가져온 정의가 지닌 위반 종류가 기준선에 들어가 있어 — 뒤의 서식 편집(header 에 정의 추가)이 422 로 떨어지지 않는다
    assert _kinds(client, d).count("styleApply") == 5
    for _ in range(6):
        assert client.post(f"/api/docs/{d}/undo").status_code == 200
    back = client.get(f"/api/docs/{d}").json()
    assert back["pristine"] is True and back["undo"] == 0 and [b["id"] for b in back["blocks"]] == t0 and server.DOCS[d].doc.save() == SMALL.read_bytes()  # 실행 취소 — 바이트까지 원본


def test_apply_errors_do_not_touch_the_document(client):
    d = _upload(client, SMALL)
    tm = _save(client, d, kind="table", table="t8", name="표")
    xm = _save(client, d, kind="text", paras=_cell_paras(client, d)[:1], name="글")
    url, cellp = f"/api/docs/{d}/styles", _cell_paras(client, d)[0]
    cases = [
        (tm["id"], {"mode": "tableMake", "after": "p99999", "grid": GRID}, 404), (tm["id"], {"mode": "tableMake", "after": cellp, "grid": GRID}, 400),
        (tm["id"], {"mode": "tableBlank", "after": None}, 404), (tm["id"], {"mode": "tableMake", "after": "t8", "grid": {"rows": []}}, 400),
        (tm["id"], {"mode": "tableMake", "after": "t8", "grid": GRID, "replace": {"table": "t9999"}}, 404), (tm["id"], {"mode": "tableMake", "after": "t8", "grid": GRID, "replace": "x"}, 400),
        (tm["id"], {"mode": "tableRestyle", "table": "t9999"}, 404), (tm["id"], {"mode": "paint", "after": "t8"}, 400), (tm["id"], {"after": "t8"}, 400),
        ("f" * 12, {"mode": "tableBlank", "after": "t8"}, 404), ("doc:t9999", {"mode": "tableBlank", "after": "t8"}, 404), ("doc:t8", {"mode": "tableRestyle", "table": "t8"}, 400),
        (xm["id"], {"mode": "tableBlank", "after": "t8"}, 400), (tm["id"], {"mode": "format", "item": "i1", "paras": [cellp]}, 400),
        (xm["id"], {"mode": "format", "item": "i9", "paras": [cellp]}, 400), (xm["id"], {"mode": "format", "item": "i1", "paras": ["p99999"]}, 404),
        (xm["id"], {"mode": "format", "item": "i1", "paras": []}, 400), ("builtin", {"mode": "format", "item": "i1", "paras": [cellp]}, 404)]
    for sid, body, code in cases:
        r = client.post(f"{url}/{sid}/apply", json=body)
        assert r.status_code == code, (sid, body, r.text)
    assert "본문 최상위 블록만" in client.post(f"{url}/{tm['id']}/apply", json={"mode": "tableBlank", "after": cellp}).json()["detail"]
    assert client.post(f"/api/docs/nope/styles/{tm['id']}/apply", json={"mode": "tableBlank", "after": "t8"}).status_code == 404
    back = client.get(f"/api/docs/{d}").json()
    assert back["pristine"] is True and back["undo"] == 0 and "styleApply" not in _kinds(client, d)


def test_apply_refuses_source_documents_of_a_task(client, monkeypatch):
    """astra 7: 에이전트 반영은 이관·취합의 **원본 문서**(이관의 사업계획서 · 취합의 기관 문서)에 403 을 내는데, 보관함의 적용 끝점은 정책 검사 없이 그 문서를 고쳤다.
    같은 정책(`doc_agent.policy`)을 **세션 잠금 안**에서 본다 — TASK 를 바꾸는 요청과 엇갈리지 않게."""
    d = _upload(client, SMALL)
    tm = _save(client, d, kind="table", table="t8", name="표")
    xm = _save(client, d, kind="text", paras=_cell_paras(client, d)[:1], name="글")
    url, cellp = f"/api/docs/{d}/styles", _cell_paras(client, d)[0]
    assert works.update(d, task={"kind": "rnd", "job": "plan_to_report", "file": "plan"}) is not None  # 이관의 사업계획서 = 원본 문서
    seen, real = [], doc_agent.policy
    monkeypatch.setattr(doc_agent, "policy", lambda task, name=None: seen.append(((task or {}).get("file"), server.DOCS[d].lock.locked())) or real(task, name))
    bodies = [("builtin", {"mode": "tableMake", "after": "t8", "grid": GRID}), (tm["id"], {"mode": "tableBlank", "after": "t8"}), ("doc:t1", {"mode": "tableRestyle", "table": "t8"}),
              (xm["id"], {"mode": "format", "item": "i1", "paras": [cellp]}), ("f" * 12, {"mode": "tableBlank", "after": "t8"})]  # 없는 서식(404)보다 정책이 먼저
    for sid, body in bodies:
        r = client.post(f"{url}/{sid}/apply", json=body)
        assert r.status_code == 403 and "원본 문서는 바꾸지 않습니다" in r.json()["detail"], (sid, r.text)
    assert seen == [("plan", True)] * len(bodies)  # 그 작업의 TASK 로 · 세션 잠금을 쥔 채 판정했다
    state = client.get(f"/api/docs/{d}").json()
    assert state["pristine"] is True and state["undo"] == 0 and "styleApply" not in _kinds(client, d) and server.DOCS[d].doc.save() == SMALL.read_bytes()
    works.update(d, task={"kind": "rnd", "job": "plan_merge", "file": "org"})  # 취합의 기관 문서도 원본 문서
    assert client.post(f"{url}/builtin/apply", json=bodies[0][1]).status_code == 403
    works.update(d, task={"kind": "rnd", "job": "plan_to_report", "file": "report"})  # 목적 문서(연차보고서)에는 된다
    assert client.post(f"{url}/builtin/apply", json=bodies[0][1]).status_code == 200
    works.update(d, task={"kind": "general", "job": "doc_edit", "file": ""})  # 일반 편집도
    assert client.post(f"{url}/{tm['id']}/apply", json=bodies[1][1]).status_code == 200 and client.get(f"/api/docs/{d}").json()["undo"] == 2
    assert client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": "t8"}).status_code == 201  # 원본 문서에서 서식을 **저장**하는 것은 문서를 안 바꾼다 — 막지 않는다


def test_apply_refuses_a_template_whose_references_dangle(client):
    """astra 8: 운반 문서의 borderFill 1 을 지워 두면(참조 46곳이 끊어짐) 적용이 성공하고 대상에는 참조 오류가 0 — 대상 문서의 borderFill 1 에 잘못 붙은 것이다."""
    d = _upload(client, SMALL)
    m = _save(client, d, kind="table", table="t8", name="표")
    bad = style_carrier.doc(style_lib.carrier(m["id"]))
    el = bad._defs["borderFill"].pop("1")
    lst = el.getparent()
    lst.remove(el)
    lst.set("itemCnt", str(len(lst)))
    bad._touch(lst)
    assert "1" in server.DOCS[d].doc._defs["borderFill"]  # 대상에 같은 번호의 정의가 있다
    broken = style_lib.create({k: m[k] for k in ("kind", "name", "rows", "cols", "bands")}, bad.save())  # 보관함에 이미 든 깨진 운반 문서(전에 저장된 것 · 손으로 고친 것)
    url = f"/api/docs/{d}/styles/{broken['id']}/apply"
    for body in ({"mode": "tableMake", "after": "t8", "grid": GRID}, {"mode": "tableBlank", "after": "t8"}, {"mode": "tableRestyle", "table": "t1"}):
        r = client.post(url, json=body)
        assert r.status_code == 400 and "서식 템플릿의 정의 참조가 깨져 있어 적용하지 않았습니다" in r.json()["detail"] and "borderFillIDRef=1" in r.json()["detail"], r.text
    state = client.get(f"/api/docs/{d}").json()
    assert state["pristine"] is True and state["undo"] == 0 and server.DOCS[d].doc.save() == SMALL.read_bytes() and not server.DOCS[d].owpml_ok
    assert client.post(f"/api/docs/{d}/styles/{m['id']}/apply", json={"mode": "tableBlank", "after": "t8"}).status_code == 200  # 성한 것은 된다
    # 깨진 원본에서는 저장도 안 된다(깨진 템플릿이 보관함에 들어가지 않게) — 고른 표가 닿는 정의가 없는 문서
    doc = server.DOCS[d].doc
    bf = next(tc.get("borderFillIDRef") for tc in doc._ids["t1"].iter("{*}tc"))
    gone = doc._defs["borderFill"].pop(bf)
    try:
        r = client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": "t1"})
        assert r.status_code == 400 and "정의 참조가 깨져 있어 서식으로 저장하지 않았습니다" in r.json()["detail"] and f"borderFillIDRef={bf}" in r.json()["detail"], r.text
    finally:
        doc._defs["borderFill"][bf] = gone
    assert len(client.get("/api/styles").json()["styles"]) == 2


def test_apply_hands_the_session_over_so_an_evicted_session_still_gets_the_allowance(client, monkeypatch):
    """astra(표 「_carry 의 DOCS 역탐색」): 편집이 도는 사이 LRU 가 그 세션을 `DOCS` 에서 밀어내면 `_carry` 가 세션을 못 찾아 판정 기준선에 못 더했다 — 끝점이 세션을 넘긴다."""
    d = _upload(client, SMALL)
    tm = _save(client, d, kind="table", table="t8", name="표")
    xm = _save(client, d, kind="text", paras=_cell_paras(client, d)[:1], name="글")
    s, allowed, real_allow, real_new = server.DOCS[d], [], server.owpml_allow, style_apply.table_new
    monkeypatch.setattr(server, "owpml_allow", lambda sess, kinds: allowed.append(sess) or real_allow(sess, kinds))

    def evicted(doc, style, norm, after, **kw):
        server.DOCS.pop(d, None)  # 편집이 도는 사이 다른 문서가 열려 이 세션이 밀려났다(server._admit)
        try:
            return real_new(doc, style, norm, after, **kw)
        finally:
            server.DOCS[d] = s
    monkeypatch.setattr(style_apply, "table_new", evicted)
    url = f"/api/docs/{d}/styles"
    r = client.post(f"{url}/{tm['id']}/apply", json={"mode": "tableMake", "after": "t8", "grid": GRID})
    assert r.status_code == 200 and allowed == [s], r.text
    for sid, body in ((tm["id"], {"mode": "tableBlank", "after": "t8"}), (tm["id"], {"mode": "tableRestyle", "table": "t1"}), (xm["id"], {"mode": "format", "item": "i1", "paras": _cell_paras(client, d)[1:2]})):
        assert client.post(f"{url}/{sid}/apply", json=body).status_code == 200
    assert allowed == [s] * 4  # 네 가지 적용 모두 세션을 넘겨받았다


def test_apply_rolls_back_dangling_import_and_unexpected_errors(client, monkeypatch):
    d = _upload(client, SMALL)
    cellp = _cell_paras(client, d)[0]
    carrier, items = style_carrier.from_paras(server.DOCS[d].doc, [{"para": cellp}])
    bad = style_carrier.doc(carrier)
    h = bad._heading(bad._ids[style_carrier.para_ids(bad)[0]])
    h.attrib.update({"type": "NUMBER", "idRef": "777", "level": "0"})  # 운반 문서에 없는 번호 정의를 가리킨다
    bad._touch(h)
    broken = style_lib.create({"kind": "text", "name": "끊어진 참조", "items": items}, bad.save())
    url = f"/api/docs/{d}/styles"
    r = client.post(f"{url}/{broken['id']}/apply", json={"mode": "format", "item": "i1", "paras": [cellp], "keepNumbering": False})
    assert r.status_code == 400 and "정의 참조가 깨져 있어 적용하지 않았습니다" in r.json()["detail"] and "idRef=777" in r.json()["detail"]  # 가져오기 전에 운반 문서에서 잡는다
    state = client.get(f"/api/docs/{d}").json()
    assert state["pristine"] is True and state["undo"] == 0 and server.DOCS[d].doc.save() == SMALL.read_bytes()
    assert "777" not in "".join(server.DOCS[d].doc._defs["numbering"])
    real_check, real_new, seen = style_apply.source_check, style_apply.table_new, {}  # 고친 것은 하나씩 되돌린다 — monkeypatch.undo() 는 conftest 의 임시 폴더 설정까지 푼다
    monkeypatch.setattr(style_apply, "source_check", lambda src: None)  # 그 검사를 지나쳐도 — 가져온 정의의 끊어진 참조는 뒤에서 잡아 되돌린다(imported_check)
    r = client.post(f"{url}/{broken['id']}/apply", json={"mode": "format", "item": "i1", "paras": [cellp], "keepNumbering": False})
    assert r.status_code == 400 and "끊어진 참조" in r.json()["detail"]
    assert client.get(f"/api/docs/{d}").json()["undo"] == 0 and server.DOCS[d].doc.save() == SMALL.read_bytes()  # 가져온 정의까지 되돌림
    monkeypatch.setattr(style_apply, "source_check", real_check)

    def half_done(doc, style, norm, after, session=None):
        seen["session"] = session
        doc.insert_line(cellp, "쓰다 만 줄")
        raise RuntimeError("예상 밖")
    monkeypatch.setattr(style_apply, "table_new", half_done)
    r = client.post(f"{url}/builtin/apply", json={"mode": "tableMake", "after": "t8", "grid": GRID})
    assert r.status_code == 400 and "서식을 적용하지 못했습니다" in r.json()["detail"] and "RuntimeError" in r.json()["detail"]
    assert seen["session"] is server.DOCS[d]  # 끝점은 세션을 넘긴다(판정 기준선에 더할 곳 — DOCS 를 뒤지지 않게)
    assert server.DOCS[d].doc.save() == SMALL.read_bytes() and client.get(f"/api/docs/{d}").json()["undo"] == 0  # 예상 밖 예외도 되돌린다(고치다 만 문서가 안 남는다)
    monkeypatch.setattr(style_apply, "table_new", real_new)
    ok = client.post(f"{url}/builtin/apply", json={"mode": "tableBlank", "after": "t8"})
    assert ok.status_code == 200 and ok.json()["made"] == {"table": ok.json()["made"]["table"], "rows": 2, "cols": 2} and ok.json()["undo"] == 1


# ---- 추출·검증 모듈 붙이기 ---------------------------------------------------------------------------------------------

def test_candidates_and_file_routes_use_the_extract_module(client, monkeypatch):
    d = _upload(client, SMALL)
    for r in (client.post(f"/api/docs/{d}/styles/candidates", json={}), client.post("/api/styles/extract-file", files={"file": ("a.hwpx", b"x")}),
              client.post("/api/styles/from-file", json={"token": "t", "picks": [{"kind": "table", "key": "k"}]})):
        assert r.status_code == 501, r.text  # 모듈이 없으면 그 기능만 빠진다
    seen, held = {}, {}

    def candidates(doc, graph=None):
        seen["graph"] = graph
        return {"tables": [{"key": "t:1", "table": "t8", "rows": 18, "cols": 11, "bands": {"headerRows": 0, "headerCols": 1, "footRows": 0}}, {"key": "t:2", "table": "t1"}], "texts": [{"key": "x:1"}]}

    def name(cands, job=None):  # job = 「문서 서식 복사」 의 할 일 프롬프트(끝점이 붙인다 — spec_서식복사 ② §6)
        return {"tables": {"t:1": {"name": "수요조사 양식", "keep": True, "bands": {"headerRows": 1, "headerCols": 1, "footRows": 0}, "bandsChanged": True}}, "texts": {}, "note": "하나만",
                "call": {"backend": "api", "model": "m", "ms": 5, "costUsd": 0.01, "error": None}, "prompt": "긴 프롬프트", "response": {"tables": []}}

    def from_file(fname, data):
        if not data.startswith(b"PK"):
            raise ValueError("못 읽는 파일입니다")
        return {"name": fname, "format": "hwpx", "tables": [{"key": "f:1", "rows": 18, "cols": 11}], "texts": [], "losses": ["뺀 것"], "_doc": style_carrier.doc(data)}

    def build_pick(entry, pick):
        if pick.get("key") != "f:1":
            raise ValueError("없는 서식 후보입니다")
        data, info = style_carrier.from_table(entry["_doc"], "t8", pick.get("bands"))
        return data, {"kind": "table", "name": pick.get("name") or "파일 표", "source": {"name": entry["name"], "format": "hwpx"}, "fidelity": "native", "losses": info["losses"],
                      "requirements": {"fonts": info["fonts"]}, "bands": info["bands"], "rows": info["rows"], "cols": info["cols"], "preview": info["preview"]}
    fake = types.SimpleNamespace(candidates=candidates, name=name, from_file=from_file, build_pick=build_pick,
                                 hold=lambda entry: held.setdefault("tok", entry) and "tok", held=lambda token: held.get(token))
    monkeypatch.setattr(style_api, "_mod", lambda n: fake if n == "style_extract" else None)
    r = client.post(f"/api/docs/{d}/styles/candidates", json={"llm": False})
    assert r.status_code == 200 and r.json() == {"rev": 0, "stage2": False, "texts": [{"key": "x:1"}], "tables": candidates(None)["tables"], "pages": [], "paras": [], "covers": [], "format": "hwpx",
                                                 "fidelity": "native"} and seen["graph"] is None  # pages·format·fidelity = spec_서식복사 ② §8(이 가짜 모듈은 script_graph 가 없어 stage2 false) · paras·covers = ② §16(옛 모듈이 안 내면 빈 목록)
    assert client.post(f"/api/docs/{d}/styles/candidates", json={"llm": True}).status_code == 503  # LLM 꺼짐
    monkeypatch.setattr("app.llm.status", lambda: {"available": True})
    n = client.post(f"/api/docs/{d}/styles/candidates", json={"llm": True}).json()
    assert n["tables"][0] == {**candidates(None)["tables"][0], "name": "수요조사 양식", "keep": True, "bands": {"headerRows": 1, "headerCols": 1, "footRows": 0}, "bandsChanged": True}
    assert n["tables"][1] == {"key": "t:2", "table": "t1"} and n["call"]["backend"] == "api" and n["note"] == "하나만" and "prompt" not in n
    assert n["calls"] == [n["call"]] and n["paras"] == [] and n["covers"] == []  # calls = 호출마다의 기록(② §16 — 옛 `name` 은 한 번)
    ev = [e for e in client.get(f"/api/works/{d}/log").json()["events"] if e["kind"] == "styleName"]
    assert len(ev) == 1 and ev[0]["named"] == 1 and ev[0]["costUsd"] == 0.01 and str(ev[0]["detail"]).startswith("styles/name_")
    # 파일에서 — 토큰과 후보 key 만 오간다
    assert client.post("/api/styles/extract-file", files={"file": ("a.hwpx", b"not a zip")}).status_code == 400
    up = client.post("/api/styles/extract-file", files={"file": (SMALL.name, SMALL.read_bytes())})
    assert up.status_code == 200 and up.json() == {"token": "tok", "name": SMALL.name, "format": "hwpx", "tables": [{"key": "f:1", "rows": 18, "cols": 11}], "texts": [], "pages": [],
                                                   "paras": [], "covers": [], "losses": ["뺀 것"]}
    pv = client.post("/api/styles/preview-file", json={"token": "tok", "pick": {"kind": "table", "key": "f:1", "bands": {"headerCols": 1}}})  # 견본(② §13) — 저장과 같은 생성 함수(build_pick), 보관함에는 안 쓴다
    assert pv.status_code == 200 and set(pv.json()) == {"rev", "kind", "view", "losses", "fidelity"} and (pv.json()["rev"], pv.json()["kind"], pv.json()["fidelity"]) == (None, "table", "native")
    assert pv.json()["view"]["grid"]["headerCols"] == 1 and len(pv.json()["view"]["grid"]["rows"]) == 18 and client.get("/api/styles").json()["styles"] == []
    gone = client.post("/api/styles/preview-file", json={"token": "expired", "pick": {"kind": "table", "key": "f:1"}})
    assert gone.status_code == 410 and gone.json()["detail"] == "올린 파일을 서버가 놓았습니다 — 다시 올려야 저장할 수 있습니다"   # 「30분이 지남」 으로 단정하지 않는다(넷까지만 잡아 둔다)
    assert client.post("/api/styles/preview-file", json={"token": "tok", "pick": {"kind": "table", "key": "nope"}}).status_code == 400
    assert client.post("/api/styles/preview-file", json={"token": "tok"}).status_code == 400
    made = client.post("/api/styles/from-file", json={"token": "tok", "picks": [{"kind": "table", "key": "f:1", "name": "파일에서 온 표", "bands": {"headerCols": 1}}]})
    assert made.status_code == 200 and [m["name"] for m in made.json()["styles"]] == ["파일에서 온 표"] and made.json()["styles"][0]["revision"] == "r1"
    assert [s["name"] for s in client.get("/api/styles").json()["styles"]] == ["파일에서 온 표"] and made.json()["styles"][0]["source"]["work"] is None
    assert client.post("/api/styles/from-file", json={"token": "tok", "picks": [{"kind": "table", "key": "nope"}]}).status_code == 400
    late = client.post("/api/styles/from-file", json={"token": "expired", "picks": [{"kind": "table", "key": "f:1"}]})
    assert late.status_code == 410 and late.json()["detail"] == style_api.GONE and "30분" not in late.json()["detail"]
    assert client.post("/api/styles/from-file", json={"token": "tok", "picks": [{"kind": "cover", "key": "cover"}]}).status_code == 400   # 이 파일에는 표지 후보가 없다
    for bad in ({"token": "tok"}, {"token": "tok", "picks": []}, {"token": "tok", "picks": ["x"]}):
        assert client.post("/api/styles/from-file", json=bad).status_code == 400


def test_verify_overlay_start_and_stale(client, monkeypatch):
    d = _upload(client, SMALL)
    sid = _save(client, d, kind="table", table="t8", name="표")["id"]
    assert client.post(f"/api/styles/{sid}/verify").status_code == 501  # 검증 모듈 없음 — verify 는 null 인 채
    state = {"running": set(), "started": []}

    def start(s, force=False):
        state["running"].add(s)
        state["started"].append((s, force))
        return {"status": "running", "revision": style_lib.get(s)["revision"]}
    fake = types.SimpleNamespace(start=start, running=lambda s: s in state["running"], subject_hash=lambda meta: f"h{meta['bands']['headerRows']}")
    monkeypatch.setattr(style_api, "_mod", lambda n: fake if n == "style_verify" else None)
    second = _save(client, d, kind="table", table="t1", name="둘째")  # 저장하면 바로 검증을 건다
    assert state["started"] == [(second["id"], False)] and second["verify"] == {"stale": False, "status": "running"}
    r = client.post(f"/api/styles/{sid}/verify")
    assert r.status_code == 202 and r.json() == {"status": "running", "revision": "r1"} and state["started"][-1] == (sid, True)  # 다시 검증 = PDF 캐시를 지우고
    assert client.post(f"/api/styles/{sid}/verify", json={"force": False}).status_code == 202 and state["started"][-1] == (sid, False)
    assert [s["verify"] for s in client.get("/api/styles").json()["styles"]] == [{"status": "running", "coverage": None, "stale": False}] * 2
    state["running"].clear()
    rec = {"status": "ok", "at": 1.0, "revision": "r1", "subjectHash": "h0", "profile": "table-v1", "checks": [{"what": "render", "status": "pass"}], "coverage": {"pass": 1, "fail": 0, "unknown": 0, "unsupported": 0}}
    assert style_lib.put_verify(sid, "r1", rec, {"proof.png": b"\x89PNG"}) is True
    full = client.get(f"/api/styles/{sid}").json()
    assert full["verify"] == {**rec, "stale": False} and client.get(f"/api/styles/{sid}/proof.png").content == b"\x89PNG"
    assert next(s for s in client.get("/api/styles").json()["styles"] if s["id"] == sid)["verify"] == {"status": "ok", "coverage": rec["coverage"], "stale": False}
    p = client.put(f"/api/styles/{sid}", json={"expectedRevision": "r1", "bands": {"headerRows": 2}}).json()
    assert p["revision"] == "r2" and p["verify"]["status"] == "ok" and p["verify"]["stale"] is True  # 운반 문서는 같아 검증을 물려받지만, 띠 수가 바뀌어 「검증 뒤 바뀜」
    assert client.get(f"/api/styles/{sid}/proof.png").status_code == 200  # 검증 그림도 물려받음
    assert client.post("/api/styles/ffffffffffff/verify").status_code == 404


def test_real_extract_and_verify_modules_plug_in(client, monkeypatch):
    """옆 모듈(app.style_extract · app.style_verify)이 있으면 실제로 물려 본다 — 없으면 건너뜀."""
    pytest.importorskip("app.style_extract")
    pytest.importorskip("app.style_verify")
    monkeypatch.setattr(style_api, "_mod", REAL_MOD)
    d = _upload(client, SMALL)
    r = client.post(f"/api/docs/{d}/styles/candidates", json={})
    assert r.status_code == 200 and r.json()["rev"] == 0 and isinstance(r.json()["tables"], list) and isinstance(r.json()["texts"], list) and r.json()["stage2"] in ("script", False)  # 2단계가 없으면 스크립트 그래프로(spec_서식복사 ② §6)
    assert isinstance(r.json()["pages"], list) and (r.json()["format"], r.json()["fidelity"]) == ("hwpx", "native")
    m = _save(client, d, kind="table", table="t8", name="실제 모듈")
    assert m["verify"] is None or m["verify"]["status"] in ("running", "none")  # 한글이 꺼져 있어(NFM_PDF=off) 「출력 없음」 으로 끝난다
    up = client.post("/api/styles/extract-file", files={"file": (SMALL.name, SMALL.read_bytes())})
    assert up.status_code == 200 and up.json()["format"] == "hwpx" and up.json()["token"] and not [k for k in up.json() if k.startswith("_")]
    if up.json()["tables"]:
        made = client.post("/api/styles/from-file", json={"token": up.json()["token"], "picks": [{"kind": "table", "key": up.json()["tables"][0]["key"], "name": "파일 표"}]})
        assert made.status_code == 200 and made.json()["styles"][0]["name"] == "파일 표" and made.json()["styles"][0]["fidelity"] == "native"
    import time
    from app import style_verify
    for _ in range(100):  # 검증 스레드가 시험 밖으로 새지 않게 기다린다
        if not any(style_verify.running(s["id"]) for s in style_lib.listing()["styles"]):
            break
        time.sleep(0.05)


# ---- 값 고치기 · 복사본 만들기(spec_서식복사 ② §19-6·§19-7) -----------------------------------------------------------

def _lettered(c, d):
    """글머리 레터(□·o·-)로 시작하는 본문 문단 id — 그런 문단이 없는 표본이면 건너뛴다."""
    import re
    for b in c.get(f"/api/docs/{d}").json()["blocks"]:
        if b["type"] == "paragraph" and re.match(r"\s*[□○ㅇo-]\s+\S", b["text"]):
            return b["id"]
    pytest.skip("레터로 시작하는 본문 문단이 없는 표본")


def test_item_format_edit_retunes_the_sample_paragraph(client):
    d = _upload(client, RND)
    m = _save(client, d, kind="text", paras=[_lettered(client, d)])
    sid, it = m["id"], m["items"][0]
    key, url = it["key"], f"/api/styles/{m['id']}/items/{it['key']}/format"
    assert it["marker"]["mode"] == "literal"
    g = client.get(f"/api/styles/{sid}").json()
    pos, f = g["view"]["pos"][key], it["format"]
    assert g["view"]["items"] == m["items"]  # 자리 값은 items 밖(view.pos) — items 는 meta 그대로
    # 자리: 앞 여백 = 왼쪽 여백 + max(첫 줄, 0) · 2번째 줄 = 왼쪽 여백 + max(−첫 줄, 0) · 글 시작 = 앞 여백 + 레터 자리 폭(잰 값)
    assert abs(pos["line1Mm"] - (f["indentLeftMm"] + max(f["firstLineMm"], 0))) < .02 and abs(pos["line2Mm"] - (f["indentLeftMm"] + max(-f["firstLineMm"], 0))) < .02
    assert pos["prefixMm"] > 0 and abs(pos["textMm"] - (pos["line1Mm"] + pos["prefixMm"])) < .02 and abs(pos["letterMm"] - (pos["line1Mm"] + pos["leadMm"])) < .02
    # 글 시작 30mm · 2번째 줄 30mm · 본문 글자(폰트·크기) · 줄간격 — 새 revision, 레터·견본 글은 그대로
    r = client.put(url, json={"expectedRevision": "r1", "changes": {"textMm": 30, "line2Mm": 30, "sizePt": 13, "font": "함초롬돋움", "lineSpacingPct": 180}})
    assert r.status_code == 200, r.text
    n = r.json()
    nf = n["items"][0]["format"]
    assert n["revision"] == "r2" and nf["sizePt"] == 13 and nf["font"] == "함초롬돋움" and nf["lineSpacingPct"] == 180
    assert n["items"][0]["marker"] == it["marker"] and n["items"][0]["sample"] == it["sample"] and n["items"][0]["name"] == it["name"]
    p2 = client.get(f"/api/styles/{sid}").json()["view"]["pos"][key]
    assert abs(p2["textMm"] - 30) < .06 and abs(p2["line2Mm"] - 30) < .06 and abs(p2["prefixMm"] - pos["prefixMm"]) < .02  # 글자 값은 본문 런만 — 레터 자리 폭은 그대로
    assert pos["letter"]["sizePt"] and p2["letter"] == pos["letter"]  # 레터 글자의 모양도 그대로(크기 13 · 함초롬돋움은 본문에만)
    assert abs(p2["line1Mm"] - (30 - pos["prefixMm"])) < .06  # 글이 30mm 에 오게 첫 줄이 움직였다
    # 앞 여백만 — 2번째 줄은 그대로, 글 시작이 따라온다
    r = client.put(url, json={"expectedRevision": "r2", "changes": {"line1Mm": 5}})
    assert r.status_code == 200 and r.json()["revision"] == "r3", r.text
    p3 = client.get(f"/api/styles/{sid}").json()["view"]["pos"][key]
    assert abs(p3["line1Mm"] - 5) < .06 and abs(p3["line2Mm"] - 30) < .06 and abs(p3["textMm"] - (5 + pos["prefixMm"])) < .06
    # 거절 — 낡은 revision 409 · 앞 여백과 글 시작을 함께 · 레터 자리 폭보다 작은 글 시작 · 모르는 키 · 범위 밖 · 빈 값 400 · 없는 항목 404 (서식은 그대로 r3)
    assert client.put(url, json={"expectedRevision": "r1", "changes": {"line1Mm": 6}}).status_code == 409
    for bad in ({"line1Mm": 5, "textMm": 20}, {"textMm": 0}, {"bold": True}, {"sizePt": 0}, {"line2Mm": 301}, {"font": " "}, {}, None, {"lineSpacingPct": "180"}):
        r = client.put(url, json={"expectedRevision": "r3", "changes": bad})
        assert r.status_code == 400, (bad, r.text)
    assert client.put(url, json={"changes": {"line1Mm": 6}}).status_code == 400  # expectedRevision 없음
    assert client.put(f"/api/styles/{sid}/items/i99/format", json={"expectedRevision": "r3", "changes": {"line1Mm": 6}}).status_code == 404
    assert client.get(f"/api/styles/{sid}").json()["revision"] == "r3"
    t = _save(client, _upload(client, SMALL), kind="table", table="t8")
    assert client.put(f"/api/styles/{t['id']}/items/i1/format", json={"expectedRevision": "r1", "changes": {"line1Mm": 6}}).status_code == 400  # 표 서식에는 없다


def test_style_copy_makes_a_separate_style_with_the_same_values(client):
    d = _upload(client, RND)
    m = _save(client, d, kind="text", paras=[_lettered(client, d)], name="사업계획서: body1")
    r = client.post(f"/api/styles/{m['id']}/copy", json={})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["id"] != m["id"] and c["name"] == "사업계획서: body1 복사" and c["copyOf"] == m["id"] and c["revision"] == "r1" and c["kind"] == "text"
    assert c["items"] == m["items"] and c["source"] == m["source"]
    assert client.get(f"/api/styles/{c['id']}/carrier").content == client.get(f"/api/styles/{m['id']}/carrier").content  # 같은 운반 문서
    assert {s["id"] for s in client.get("/api/styles").json()["styles"]} == {m["id"], c["id"]}  # 「같은 서식은 한 번만」 을 지나지 않는다 — 둘 다 남는다
    # 복사본을 고쳐도 원래 서식은 그대로
    assert client.put(f"/api/styles/{c['id']}/items/i1/format", json={"expectedRevision": "r1", "changes": {"line2Mm": 40}}).status_code == 200
    assert client.get(f"/api/styles/{m['id']}").json()["items"] == m["items"]
    n = client.post(f"/api/styles/{m['id']}/copy", json={"name": "  둘째   복사본 "})
    assert n.status_code == 201 and n.json()["name"] == "둘째 복사본"
    assert client.put(f"/api/styles/{m['id']}", json={"expectedRevision": "r1", "name": "가" * 60}).status_code == 200
    long = client.post(f"/api/styles/{m['id']}/copy", json={})
    assert long.status_code == 201 and len(long.json()["name"]) <= 60 and long.json()["name"].endswith(" 복사")
    for bad in ("", " ", "가" * 61, 3):
        assert client.post(f"/api/styles/{m['id']}/copy", json={"name": bad}).status_code == 400, bad
    assert client.post("/api/styles/nope/copy", json={}).status_code == 404
