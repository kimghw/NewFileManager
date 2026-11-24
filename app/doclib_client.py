"""문서 라이브러리 서버(doclib/ — 따로 선 서버 · 포트 8121)를 HTTP 로 읽는 얇은 손님(spec_양식작성 ② §4). 그 서버의 파일 · 함수를 가져오지 않는다 — 주소만 안다.

- 주소 = env NFM_DOCLIB_URL | `http://127.0.0.1:<NFM_DOCLIB_PORT | 8121>`. 그 서버가 꺼져 있으면 `Down`(화면이 「문서 라이브러리 서버가 꺼져 있습니다」 로 알린다 — 8114 는 그대로 돈다).
- `health()` · `docs()` · `extract(eid)` · `md(eid)` · `file(did, limit)`(등록한 원본 파일 — 이름 · 바이트) — 읽기만(추출을 시작 · 지우는 것은 그 서버의 화면에서)."""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 6.0
MD_MAX = 4 * 2 ** 20
_EID = re.compile(r"^x[0-9a-f]{10}$")
_DID = re.compile(r"^d[0-9a-f]{12}$")   # 문서 id = 「d」 + sha256 앞 12자(doclib/store.py 의 꼴)


class Down(RuntimeError):
    """문서 라이브러리 서버에 닿지 못함(꺼짐 · 시간 초과)."""


class TooBig(LookupError):
    """받을 수 있는 크기를 넘는 파일(끝점이 413 으로)."""


def url():
    env = (os.environ.get("NFM_DOCLIB_URL") or "").strip().rstrip("/")
    if env:
        return env
    return f"http://127.0.0.1:{int(os.environ.get('NFM_DOCLIB_PORT') or 8121)}"


def _get(path, timeout=TIMEOUT, limit=MD_MAX, head=None):
    """그 길의 바이트(limit + 1 까지). head 에 dict 를 주면 응답 머리말을 거기 담는다(소문자 이름)."""
    try:
        with urllib.request.urlopen(url() + path, timeout=timeout) as r:
            if head is not None:
                head.update({k.lower(): v for k, v in r.headers.items()})
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


def ok_doc(did):
    return isinstance(did, str) and bool(_DID.fullmatch(did))


def file(did, limit):
    """등록한 문서의 원본 파일 → (파일 이름 | None, 바이트). limit 바이트를 넘으면 TooBig · 없으면 LookupError · 서버가 꺼졌으면 Down.
    이름은 응답의 Content-Disposition(filename*=UTF-8''…)에서 읽는다 — 없으면 None(부르는 쪽이 문서 목록의 이름을 쓴다)."""
    if not ok_doc(did):
        raise LookupError("문서 id 의 꼴이 아닙니다")
    head = {}
    data = _get(f"/api/docs/{did}/file", timeout=60.0, limit=limit, head=head)
    if len(data) > limit:
        raise TooBig(f"원본 파일이 너무 큽니다({limit // 2 ** 20} MB 까지)")
    m = re.search(r"filename\*=UTF-8''([^;]+)", head.get("content-disposition") or "", re.I)
    return (urllib.parse.unquote(m.group(1).strip()) if m else None), data
