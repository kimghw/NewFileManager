"""다른 문서의 서식을 입힌 작업을 **다시 연 뒤**에도 편집이 된다(spec_일반편집 ② §4 — `server.owpml_allow`).

운반 문서는 원본 문서의 정의와 함께 한글이 써 둔 스키마 위반 **종류**(tabPr/tabItem 등)를 물고 온다. 대상 문서의 원본에 없던 종류라 그대로면 `_edit` 의 판정이 422 로 되돌린다 —
`style_apply` 가 그 종류를 작업의 기준선에 더하고(`owpml_allow`), 편집 상태와 함께 저장한다. 저장하지 않으면 서버를 다시 켠 뒤(기준선을 원본에서 다시 셈) 그 문서의 서식 편집이
「원본에 없던 종류」 로 422 가 난다(2026-11-13 하위 에이전트가 재현)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_rules as R
from app import server, style_api, table_make

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, RND = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "연구개발계획서_양식.hwpx"
GRID = {"rows": [["구분", "값"], ["가", "1"]], "headerRows": 1}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    monkeypatch.setattr(style_api, "_mod", lambda name: None)  # 검증 스레드를 띄우지 않는다
    R._MEMORY.clear()
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()
    R._MEMORY.clear()


def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _bring(client):
    """(대상 문서 id, 받아들인 종류) — 대상 원본에 없던 위반 종류를 물고 오는 표 서식을 찾아 적용한 상태(양식의 표 대부분은 안 물고 온다)."""
    src, d = _upload(client, RND), _upload(client, SMALL)
    tables = [b for b in client.get(f"/api/docs/{src}").json()["blocks"] if b["type"] == "table" and len(b["cells"]) > 1 and not table_make.block_nested(b)]
    for tb in tables[:40]:
        sid = client.post(f"/api/docs/{src}/styles", json={"kind": "table", "table": tb["id"]}).json()["id"]
        r = client.post(f"/api/docs/{d}/styles/{sid}/apply", json={"mode": "tableMake", "after": "t8", "grid": GRID})
        assert r.status_code == 200, r.text   # 물고 온 종류 때문에 422 로 되돌리지 않는다
        if server.DOCS[d].owpml_ok:
            return d, set(server.DOCS[d].owpml_ok)
    pytest.skip("이 표본에서는 새 위반 종류를 물고 오는 표를 못 찾았습니다")


def test_allowed_kinds_are_undone_with_the_edit(client):
    d, brought = _bring(client)
    s = server.DOCS[d]
    orig = s.owpml_base   # 원본 기준선(캐시)은 그대로 — 받아들인 종류는 판정 때마다 합친다
    assert all(k[0] == "header" for k in brought) and not any(k in orig["schema"] for k in brought)
    assert all(k in server.owpml_base(s)["schema"] for k in brought) and server.owpml_base(s) is not orig
    assert client.post(f"/api/docs/{d}/undo").status_code == 200   # 그 종류를 들여온 적용을 되돌림
    s = server.DOCS[d]
    assert s.owpml_ok == set() and server.owpml_base(s) is s.owpml_base   # 가져온 정의가 사라졌으니 허용도 사라진다


def test_allowed_kinds_survive_reopen(client):
    d, brought = _bring(client)
    assert all(k in server.owpml_base(server.DOCS[d])["schema"] for k in brought)
    para = next(x["id"] for b in client.get(f"/api/docs/{d}").json()["blocks"] if b["id"] == "t8" for c in b["cells"] for x in c["blocks"] if x["type"] == "paragraph" and x["text"].strip())

    server._persist_all()
    server.DOCS.clear()   # 서버를 다시 켠 것처럼 — 다음 요청이 작업 폴더에서 다시 연다
    later = client.post(f"/api/docs/{d}/format/chars", json={"id": para, "start": 0, "end": 1, "changes": {"italic": True}})
    assert later.status_code == 200, later.text   # header 에 정의를 더하는 편집 — 기준선을 원본에서 다시 세도 받아들인 종류는 남아 있다
    s = server.DOCS[d]
    assert set(s.owpml_ok) == brought and all(k in server.owpml_base(s)["schema"] for k in brought)


def test_edit_response_carries_web_fonts_when_new_faces_arrive(client):
    """다른 문서의 글 서식을 입혀 header 에 새 글꼴이 들어오면 편집 응답에 webFonts 가 실린다 — 화면이 그 글꼴의 @font-face 를 받게(없으면 기본 글꼴로 그려진다).
    글꼴이 안 늘어난 편집의 응답에는 없다(전과 같은 꼴)."""
    src, d = _upload(client, RND), _upload(client, SMALL)
    have = {face for faces in server.DOCS[d].doc.font_table().values() for face in faces}
    blocks = client.get(f"/api/docs/{src}").json()["blocks"]
    para = next((b for b in blocks if b["type"] == "paragraph" and b["text"].strip() and b["format"]["font"] and b["format"]["font"] not in have), None)
    if para is None:
        pytest.skip("대상 문서에 없는 글꼴을 쓰는 문단을 못 찾았습니다")
    sid = client.post(f"/api/docs/{src}/styles", json={"kind": "text", "paras": [para["id"]]}).json()
    target = next(x["id"] for b in client.get(f"/api/docs/{d}").json()["blocks"] if b["id"] == "t8" for c in b["cells"] for x in c["blocks"] if x["type"] == "paragraph" and x["text"].strip())
    r = client.post(f"/api/docs/{d}/styles/{sid['id']}/apply", json={"mode": "format", "item": sid["items"][0]["key"], "paras": [target]})
    assert r.status_code == 200, r.text
    assert "webFonts" in r.json() and para["format"]["font"] in {face for faces in server.DOCS[d].doc.font_table().values() for face in faces}
    plain = client.post(f"/api/docs/{d}/format/chars", json={"id": target, "start": 0, "end": 1, "changes": {"italic": True}})
    assert plain.status_code == 200 and "webFonts" not in plain.json()


def test_allow_ignores_rule_kinds(client):
    d = _upload(client, SMALL)
    s = server.DOCS[d]
    added = server.owpml_allow(s, [("rule", "ref", "charPrIDRef"), ("header", "x", "y", "", "SCHEMAV_TEST"), ("section", "p", "", "pageBreak", "SCHEMAV_CVC_ENUMERATION_VALID"), "bad"])
    # 끊어진 참조 같은 규칙 위반도, 본문(section)의 스키마 위반(가져온 문단·표 자체의 손상 — 틀린 속성 값)도 받지 않는다: header 정의의 종류만
    assert added == [("header", "x", "y", "", "SCHEMAV_TEST")] and s.owpml_ok == {("header", "x", "y", "", "SCHEMAV_TEST")}
    assert server.owpml_allow(s, [("header", "x", "y", "", "SCHEMAV_TEST")]) == []   # 이미 있는 종류
    assert ("header", "x", "y", "", "SCHEMAV_TEST") not in s.owpml_base["schema"]   # 원본 기준선은 건드리지 않는다
