"""앱으로 설치(PWA) — spec_hwpx_웹편집 ② §9 「상단 바 오른쪽 끝 아이콘」 의 「앱으로 설치」.

Chromium(Chrome·Edge)이 「설치할 수 있다」(beforeinstallprompt)고 알려 주는 조건을 지킨다: 시작 화면이 설명 파일을 걸고,
설명 파일에 이름 · start_url · display · 192·512 아이콘이 있고, 그 파일들이 실제로 나간다. 이 조건이 깨지면 상단 바 단추가 조용히 안 보인다.
"""
import json
import struct
from pathlib import Path

from fastapi.testclient import TestClient

from app import server

STATIC = Path(server.__file__).resolve().parent / "static"


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_index_links_manifest_and_script():
    c = TestClient(server.app)
    html = c.get("/").text
    assert '<link rel="manifest" href="/static/app.webmanifest">' in html
    assert "/static/app_install.css" in html
    assert "/static/app_install.js" in html
    # 단추를 끼우는 자리(app_install.js 가 #panelBtn 앞에 넣는다)
    assert 'id="panelBtn"' in html and 'id="agentBtn"' in html   # 에이전트 아이콘(전의 「에이전트 설정」 링크 자리 — 2026-11-18) 다음 · 패널 여닫기 앞


def test_manifest_meets_install_criteria():
    c = TestClient(server.app)
    r = c.get("/static/app.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    m = json.loads(r.content.decode("utf-8"))
    assert m["name"] and m["short_name"]
    assert m["start_url"] == "/" and m["scope"] == "/" and m["id"] == "/"
    assert m["display"] in ("standalone", "minimal-ui", "fullscreen")
    sizes = {}
    for ic in m["icons"]:
        assert ic["type"] == "image/png"
        ir = c.get(ic["src"])
        assert ir.status_code == 200, ic["src"]
        w, h = _png_size(ir.content)
        assert ic["sizes"] == f"{w}x{h}", ic["src"]
        sizes[w] = ic
    assert 192 in sizes and 512 in sizes  # Chromium 설치 조건


def test_install_button_script_served():
    c = TestClient(server.app)
    js = c.get("/static/app_install.js").text
    assert "beforeinstallprompt" in js and "appinstalled" in js
    assert 'b.id = "installBtn"' in js
