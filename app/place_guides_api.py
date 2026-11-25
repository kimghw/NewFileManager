"""자리마다의 작성 지침 끝점(spec_병합 ② §5-11) — 고르기는 `app/place_guides.py`(순수), 화면은 `app/static/place_guides.js`.
문서를 바꾸지 않고 LLM 도 부르지 않는다. 어느 hwpx 문서에서나(공통 모듈) — 이관 3단계의 LLM 셋이 `index_of(s)` 로 같은 색인을 읽는다.

- `GET /api/docs/{id}/place-guides` → 지침이 있는 헤딩 · 표의 목록(화면의 「지침」 단추 — 수만).
- `GET /api/docs/{id}/place-guides/heads/{pid}` → 그 헤딩의 지침(문서의 것 · 사람의 것 · 그 자리에 걸린 양식의 매칭 지침).
- `PUT …/heads/{pid}` {text, version?} → 사람이 그 헤딩에 적는 지침(작업 폴더 `guides_user.json` — 빈 글 = 지움 · 판이 다르면 409). 표의 사람 지침은 이미 있는 표 지침(「이 표」 — table_agent)이다.
- 저장본 = form_guides_api.load(작업 폴더 guides.json) — 없으면 지금 문서에서 모은 것(쓰지 않음 — form_guides_api.current)."""
import time

from fastapi import APIRouter, Body, HTTPException

from app import place_guides as PG
from app import works

router = APIRouter()
FILE = "guides_user.json"
_MEM = {}   # 작업 저장이 꺼졌을 때


def _path(wid):
    f = works.folder(wid)
    return f / FILE if f is not None and (f / "work.json").is_file() else None


def user_load(wid):
    """사람이 헤딩에 적은 지침 {version, heads{헤딩 id: {text, label, at}}}(없으면 빈 것)."""
    p = _path(wid)
    got = works._read_json(p) if p is not None and p.is_file() else _MEM.get(wid)
    return got if isinstance(got, dict) and isinstance(got.get("heads"), dict) else {"version": 0, "heads": {}}


def _user_save(wid, data):
    p = _path(wid)
    if p is not None:
        works._write_json(p, data)
    else:
        _MEM[wid] = data


def _table_user(wid):
    """표마다 사람이 적은 「이 표」 지침(table_agent — 표 채우기의 표 지침과 같은 글) {표 id: 글}."""
    from app import table_agent
    try:
        got = table_agent.all_tables(wid).get("tables") or {}
    except Exception:   # 지침은 덤이다 — 못 읽어도 검토는 나간다
        return {}
    return {t: (r or {}).get("instructions") or "" for t, r in got.items()}


def index_of(s):
    """문서 s 의 자리 지침 색인(place_guides.index 꼴) | None(hwpx 아님). **세션 잠금 안에서** 부른다(문서 블록 · 분석 결과를 읽는다)."""
    from app import form_guides_api, heading_runs
    if s.fmt != "hwpx":
        return None
    saved = form_guides_api.load(s.id)
    if saved is None:
        saved, _ = form_guides_api.current(s)
    t3 = heading_runs.tables(s) or {}
    return PG.index(saved, s.doc.blocks(), [t.get("id") for t in t3.get("tables") or () if isinstance(t, dict)], user_load(s.id), _table_user(s.id), t3.get("tables"))


def _head_text(s, pid):
    el = s.doc._ids.get(pid) if hasattr(s.doc, "_ids") else None
    return " ".join((s.doc._text(el) if el is not None else "").split())[:200]


def _matches(s, text, kind):
    """그 자리 글에 걸린 양식의 매칭 지침(link_guides — 「어떻게 잇나」 · 양식 전체가 같이 씀)."""
    from app import link_guides
    from app.merge_api import _link_guides
    try:
        return [{"n": e["n"], "kind": e["kind"], "title": e["title"], "text": e["text"]} for e in link_guides.match(_link_guides(s.id), [text], kind)] if text else []
    except Exception:
        return []


@router.get("/api/docs/{doc_id}/place-guides")
def place_guides_list(doc_id: str):
    """{rev, version(사람 지침의 판), heads[{id, n, user, text}], tables[{id, n, user}], loose, lines[{id, n}]} — 지침이 있는 헤딩 · 표만(문서 차례가 아님 — 화면이 그 자리를 찾는다) ·
    lines = 상자 · 칸 안의 헤딩 줄(늘 보이는 「지침」 단추 — 누르면 그 줄에 닿는 층들: GET …/at/{id} · n = 그 줄을 가리키는 작성 지침 보완 수)."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        ix = index_of(s)
        if ix is None:
            return {"rev": s.rev, "version": 0, "heads": [], "tables": [], "loose": 0}
        heads = [{"id": h, "n": len(v), "user": any(g["src"] == "user" for g in v), "text": ix["heads_text"].get(h) or _head_text(s, h)} for h, v in ix["heads"].items() if v]
        tables = [{"id": t, "n": len(v), "user": any(g["src"] == "user" for g in v)} for t, v in ix["tables"].items() if v]
        from app import heading_runs
        lines = [{"id": k, "n": v} for k, v in PG.chain_lines(heading_runs.graph(s), s.doc.blocks(), _extra(s.id)[0]).items()]
        return {"rev": s.rev, "version": user_load(s.id).get("version", 0), "heads": heads, "tables": tables, "loose": ix["loose"], "lines": lines}


def _extra(wid):
    """(작성 지침 보완 26 의 rules {자리 id: [규칙…]}, 양식 검토 25 의 작성 방향 {자리 id: how}) — 양식 작성에서만 있다(없으면 빈 것)."""
    from app import form_review_api, writing_guidance_api
    try:
        wg = writing_guidance_api._load(wid) or {}
    except Exception:
        wg = {}
    rv = (form_review_api.load(wid) or {}).get("review") or {}
    pl = rv.get("places") or {}
    rows = pl.items() if isinstance(pl, dict) else ((x.get("id"), x) for x in pl if isinstance(x, dict))
    hows = {k: v["how"] for k, v in rows if k and isinstance(v, dict) and (v.get("how") or "").strip()}
    return (wg.get("rules") if isinstance(wg.get("rules"), dict) else {}), hows


@router.get("/api/docs/{doc_id}/place-guides/at/{bid}")
def place_guides_at(doc_id: str, bid: str):
    """{id, text, layers[{key, title, at, items[{src, kind, text, label?}]}], rev} — 블록 bid(본문 · 상자 · 표 칸 안의 줄 · 칸)에 닿는 작성 지침을 가까운 층부터:
    이 줄 → 윗 줄(상자 · 칸 안의 부모 줄) → 이 칸 → 상자 · 표 → 절 → 윗 절(place_guides.chain — 읽기만 · 문서는 안 바뀐다). 2026-11-25 사용자 「헤딩마다 작성 지침 … 아이콘」 · 「테이블 필드도 마찬가지로」."""
    from app import heading_runs, server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "작성 지침은 hwpx 문서에서만 봅니다")
    rules, hows = _extra(s.id)
    owner = {}
    if rules or hows:   # 양식 작성의 자리가 품은 표(헤딩 자리 「p5」 → 표 「t6」) — 그 자리의 지침이 표 칸에도 닿게. **잠금 밖에서**(_base_places 가 세션 잠금을 잡는다 — 잠금은 다시 들어갈 수 없다)
        from app import guide_write_api
        try:
            for pl in guide_write_api._base_places(s)[0]:
                for t in pl.get("tables") or ():
                    owner.setdefault(t, pl["id"])
        except Exception:
            owner = {}
    with s.lock:
        ix = index_of(s)
        if ix is None:
            raise HTTPException(400, "작성 지침은 hwpx 문서에서만 봅니다")
        blocks = s.doc.blocks()
        if bid not in PG.owners(blocks):
            raise HTTPException(404, "그 자리가 지금 문서에 없습니다")
        return {"id": bid, "text": _head_text(s, bid), "layers": PG.chain(ix, blocks, heading_runs.graph(s), bid, rules, hows, owner), "rev": s.rev}


def _head_view(s, pid):
    ix = index_of(s) or {"heads": {}}
    doc = [g for g in ix["heads"].get(pid) or () if g["src"] == "doc"]
    u = (user_load(s.id).get("heads") or {}).get(pid)
    text = _head_text(s, pid) or (u or {}).get("label") or ""
    return {"id": pid, "text": text, "alive": bool(_head_text(s, pid)), "doc": doc, "user": u, "match": _matches(s, text, "body"),
            "version": user_load(s.id).get("version", 0), "rev": s.rev}


@router.get("/api/docs/{doc_id}/place-guides/heads/{pid}")
def place_guides_head(doc_id: str, pid: str):
    """{id, text(지금 헤딩 글), alive, doc[{src, kind, text, label?}](문서의 작성 지침 — 읽기만), user{text, label, at} | null(사람이 적은 것), match[{n, kind, title, text}](양식의 매칭 지침), version, rev}."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        return _head_view(s, pid)


@router.put("/api/docs/{doc_id}/place-guides/heads/{pid}")
def place_guides_head_put(doc_id: str, pid: str, body: dict = Body(...)):
    """{text, version?} — 그 헤딩에 사람이 적는 지침(빈 글 = 지움). version 이 지금 판과 다르면 409 · 너무 길면 400. 문서는 안 바뀐다 → GET 과 같은 몸통."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        if s.fmt != "hwpx":
            raise HTTPException(400, "자리 지침은 hwpx 문서에서만 적습니다")
        cur = user_load(s.id)
        ver = body.get("version")
        if ver is not None and (isinstance(ver, bool) or not isinstance(ver, int)):
            raise HTTPException(400, "version 은 정수(받은 지침의 판)여야 합니다")
        if ver is not None and ver != int(cur.get("version") or 0):
            raise HTTPException(409, "그 사이 다른 화면에서 지침이 바뀌었습니다 — 다시 읽어 주세요")
        text = body.get("text")
        if not isinstance(text, str):
            raise HTTPException(400, "text(글)가 필요합니다")
        if text.strip():   # 적기는 지금 문서의 본문 헤딩 줄에만(그 지침을 3단계 LLM 이 읽는 자리 — place_guides.heading_finder 와 같은 헤딩) · 지우기는 사라진 헤딩의 것도 된다
            if not _head_text(s, pid):
                raise HTTPException(404, "그 헤딩이 지금 문서에 없습니다")
            from app import heading_runs
            heads = {n.get("para") for n in (heading_runs.graph(s) or {}).get("nodes") or () if PG._head(n)}
            if pid not in heads:
                raise HTTPException(400, "본문 헤딩 줄에만 지침을 적습니다 — 헤딩 추출(2단계) 결과의 헤딩 줄을 고르세요")
        try:
            new = PG.user_put(cur, pid, text, _head_text(s, pid), time.time())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        _user_save(s.id, new)
        works.log(s.id, "placeGuide", head=pid, chars=len(text.strip()), version=new["version"])
        return _head_view(s, pid)
