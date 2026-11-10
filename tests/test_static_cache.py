"""정적 파일 캐시 — 고친 CSS·JS 가 보통 새로 고침만으로 쓰이게(spec_hwpx_웹편집 ② §6 · 2026-11-09).

브라우저는 Cache-Control 이 없으면 Last-Modified 기준 추정으로 옛 파일을 그대로 써서, 2열 컬럼을 넣은 뒤 사용자 화면이 옛 style.css 로 깨져 보였다."""
import re

from fastapi.testclient import TestClient

from app import server


def client():
    return TestClient(server.app)


def test_index_links_static_with_mtime_version_and_no_cache():
    r = client().get("/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    assert "text/html" in r.headers["content-type"]
    css = re.search(r'href="/static/style\.css\?v=(\d+)"', r.text)
    js = re.search(r'src="/static/app\.js\?v=(\d+)"', r.text)
    assert css and js, "style.css·app.js 주소에 ?v= 가 붙어야 한다"
    assert int(css.group(1)) == int((server.STATIC / "style.css").stat().st_mtime)
    assert int(js.group(1)) == int((server.STATIC / "app.js").stat().st_mtime)
    assert "/static/style.css\"" not in r.text  # 버전 없는 주소는 남지 않음


def test_static_files_are_revalidated():
    c = client()
    r = c.get("/static/style.css?v=1")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers.get("etag")
    # 같은 ETag 면 304 — 다시 묻는 비용은 작다
    r2 = c.get("/static/style.css", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304
