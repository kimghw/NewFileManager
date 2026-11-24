"""문서 라이브러리 서버(doclib/ — 따로 선 서버 · 포트 8121)를 HTTP 로 읽는 얇은 손님(spec_양식작성 ② §4). 그 서버의 파일 · 함수를 가져오지 않는다 — 주소만 안다.

- 주소 = env NFM_DOCLIB_URL | `http://127.0.0.1:<NFM_DOCLIB_PORT | 8121>`. 그 서버가 꺼져 있으면 `Down`(화면이 「문서 라이브러리 서버가 꺼져 있습니다」 로 알린다 — 8114 는 그대로 돈다).
- `health()` · `docs()` · `extract(eid)` · `md(eid)` — 읽기만(추출을 시작 · 지우는 것은 그 서버의 화면에서)."""
import json
import os
import re
import urllib.error
import urllib.request

TIMEOUT = 6.0
MD_MAX = 4 * 2 ** 20
_EID = re.compile(r"^x[0-9a-f]{10}$")


class Down(RuntimeError):
    """문서 라이브러리 서버에 닿지 못함(꺼짐 · 시간 초과)."""


def url():
    env = (os.environ.get("NFM_DOCLIB_URL") or "").strip().rstrip("/")
    if env:
        return env
    return f"http://127.0.0.1:{int(os.environ.get('NFM_DOCLIB_PORT') or 8121)}"


def _get(path, timeout=TIMEOUT, limit=MD_MAX):
    try:
        with urllib.request.urlopen(url() + path, timeout=timeout) as r:
            return r.read(limit + 1)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail")
        except Exception:   # noqa: BLE001
            detail = None
        raise LookupError(detail or f"문서 라이브러리 서버의 응답 {e.code}") from e
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise Down(f"문서 라이브러리 서버({url()})에 닿지 못했습니다") from e


def _json(path):
    try:
        return json.loads(_get(path).decode("utf-8"))
    except ValueError as e:
        raise Down("문서 라이브러리 서버의 응답을 읽지 못했습니다") from e


def health():
    return _json("/api/health")


def docs():
    return _json("/api/docs").get("docs") or []


def ok_id(eid):
    return isinstance(eid, str) and bool(_EID.fullmatch(eid))


def extract(eid):
    """추출 하나의 기록 → dict. 없으면 LookupError · 서버가 꺼졌으면 Down."""
    if not ok_id(eid):
        raise LookupError("추출 id 의 꼴이 아닙니다")
    return _json(f"/api/extracts/{eid}").get("extract") or {}


def md(eid):
    """추출한 MD 글. 없으면 LookupError · 서버가 꺼졌으면 Down."""
    if not ok_id(eid):
        raise LookupError("추출 id 의 꼴이 아닙니다")
    data = _get(f"/api/extracts/{eid}/md", timeout=20.0)
    if len(data) > MD_MAX:
        raise LookupError("MD 가 너무 큽니다")
    return data.decode("utf-8", errors="replace")
