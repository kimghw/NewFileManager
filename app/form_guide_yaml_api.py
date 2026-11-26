"""양식 지침 YAML 의 끝점(spec_양식작성 ② §5-8) — 꼴 · 자리 잇기 · 후보 · 올리기는 `app/form_guide_yaml.py`. server.py 가 include 한다.
문서를 바꾸지 않고 LLM 도 부르지 않는다. 쓰기(올리기 · 예시 · YAML 고치기)는 사람이 누를 때만 — 04 · 3단계가 저절로 쓰지 않는다(astra · Fable 합의).

- `GET /api/docs/{id}/form-guide` → {form{key, name, how} | null, writable, why?, sha1, exists, counts, unmatched[…], keywords[…], candidates[…], bands{표 id: [{id, head, rows}]}}.
- `POST /api/docs/{id}/form-guide/promote` {keys[], sha1} → 고른 후보를 양식 지침에 올린다(같은 글은 건너뜀) · 409 = 그 사이 파일이 바뀜 · 400 = 쓸 수 없는 문서.
- `POST /api/docs/{id}/form-guide/skeleton` {sha1} → 지금 문서의 구조(본문 절 → 표 → 서브 테이블)를 깐다(없는 항목만 · 지침 없이).
- `POST /api/docs/{id}/form-guide/example` {place, band?, text, note?, sha1} → 그 자리(헤딩 · 표 · 띠)에 작성 예시 하나.
- `GET /api/form-guides/{key}/yaml` → {key, text, sha1, exists} · `PUT …` {text, sha1} → 검사 뒤 저장(400 = 틀린 꼴 · 409 = 그 사이 바뀜).
- 쓰기는 **양식이 사람이 고른 것이거나 올린 원본의 sha256 이 양식의 조건(`match.sha256`)과 맞을 때만**(파일 이름만 맞은 문서는 다른 기관의 같은 이름 양식일 수 있다 — Fable P1-2) — 아니면 「헤딩 추출의 양식 고르기」 로 고른 뒤.
- `overlay(s, t3)` = place_guides_api.index_of 가 부른다(세션 잠금 안) → form_guide_yaml.locate 결과 | None."""
import time

from fastapi import APIRouter, Body, HTTPException

from app import form_guide_yaml as FG
from app import heading_forms as HF
from app import works

router = APIRouter()
_CACHE = {}   # {문서 id: (열쇠, (places, located))} — 자리 지침을 읽을 때마다 부르므로 같은 문서 · 같은 파일이면 다시 셈하지 않는다
_FILE = {}    # {양식 키: ((mtime, size), 읽은 것)}


def _form(s):
    try:
        return HF.for_session(s)
    except Exception:
        return None


def _yaml(key):
    p = FG.path_of(key)
    try:
        st = p.stat() if p is not None and p.is_file() else None
    except OSError:
        st = None
    mark = (st.st_mtime_ns, st.st_size) if st else None
    hit = _FILE.get(key)
    if hit and hit[0] == mark:
        return hit[1]
    d = FG.load(key) if mark else None
    _FILE[key] = (mark, d)
    return d


def _places(s, t3):
    from app import heading_runs
    graph = heading_runs.graph(s)
    return FG.doc_places(s.doc.blocks(), graph, (t3 or {}).get("tables")), graph


_PL = {}      # {문서 id: (열쇠, 자리)} — 규정 · 문서 목적의 자리 잇기가 같은 문서 차례에서 자리를 다시 셈하지 않게(place_guides_api.index_of 가 읽을 때마다 부른다)


def places_cached(s, t3):
    """세션 잠금 안 — 지금 문서의 자리(form_guide_yaml.doc_places): 같은 문서 차례 · 같은 그래프 · 같은 3단계 결과면 앞에 셈한 것."""
    from app import heading_runs
    graph = heading_runs.graph(s)
    key = (s.rev, id(graph), id(t3))
    hit = _PL.get(s.id)
    if hit and hit[0] == key:
        return hit[1]
    got = FG.doc_places(s.doc.blocks(), graph, (t3 or {}).get("tables"))
    _PL[s.id] = (key, got)
    return got


def overlay(s, t3):
    """세션 잠금 안 — 이 문서의 양식 지침을 지금 자리에 이은 것(locate 결과) | None(양식이 없음 · 지침 파일이 없음)."""
    f = _form(s)
    if not f:
        return None
    d = _yaml(f["key"])
    if not d or not (d.get("sections") or d.get("guides")):
        return None
    from app import heading_runs
    graph = heading_runs.graph(s)
    key = (s.rev, id(graph), id(t3), id(d))
    hit = _CACHE.get(s.id)
    if hit and hit[0] == key:
        return hit[1]
    places = FG.doc_places(s.doc.blocks(), graph, (t3 or {}).get("tables"))
    got = FG.locate(d, places, s.doc.blocks())
    _CACHE[s.id] = (key, got)
    return got


def _writable(s, f):
    """(쓸 수 있나, 까닭)."""
    if f is None:
        return False, "이 문서에 맞는 양식이 없습니다 — 헤딩 추출의 「양식」 에서 고르세요"
    if f.get("how") in ("manual", "sha256"):
        return True, ""
    return False, f"양식 「{f['name']}」 은 파일 이름으로만 맞았습니다 — 다른 기관의 같은 이름 양식일 수 있어 양식 지침에 쓰지 않습니다(헤딩 추출의 「양식」 에서 이 양식을 고르면 씁니다)"


def _values(s):
    div = getattr(s, "division", None) or {}
    return (div.get("applied") or {}).get("values") or (div.get("settings") or {}).get("values") or {}


def _sources(s):
    """작업 폴더의 후보 원천 — (사람의 헤딩 지침, 표의 「이 표」 지침, 04 작성 지침 보완의 rules)."""
    from app import place_guides_api, writing_guidance_api
    heads = (place_guides_api.user_load(s.id).get("heads") or {})
    tabs = place_guides_api._table_user(s.id)
    try:
        rules = (writing_guidance_api._load(s.id) or {}).get("rules") or {}
    except Exception:
        rules = {}
    return heads, tabs, rules if isinstance(rules, dict) else {}


def _sess_doc(doc_id):
    from app import server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "양식 지침은 hwpx 문서에서만 다룹니다")
    return s


def _view(s):
    from app import heading_runs
    f = _form(s)
    t3 = heading_runs.tables(s) or {}
    places, _ = _places(s, t3)
    if f is None:
        return {"form": None, "writable": False, "why": _writable(s, None)[1], "sha1": "", "exists": False, "counts": {}, "unmatched": [], "keywords": [], "candidates": [], "bands": {}}
    try:
        d, text, sha = FG.read(f["key"])
        broken = ""
    except (ValueError, OSError) as e:
        d, text, sha, broken = {"sections": [], "keywords": [], "form": f["key"]}, None, None, str(e)
    ok, why = _writable(s, f)
    got = FG.locate(d, places, s.doc.blocks())
    heads, tabs, rules = _sources(s)
    cands = FG.candidates(d, places, user_heads=heads, table_user=tabs, rules=rules, words=FG._value_words(_values(s)))
    secs = d.get("sections") or []
    counts = {"sections": len(secs), "tables": sum(len(x.get("tables") or ()) for x in secs),
              "subtables": sum(len(t.get("subtables") or ()) for x in secs for t in x.get("tables") or ()),
              "guides": sum(len(x.get("guides") or ()) + sum(len(t.get("guides") or ()) + sum(len(b.get("guides") or ()) for b in t.get("subtables") or ()) for t in x.get("tables") or ()) for x in secs),
              "examples": sum(len(x.get("examples") or ()) + sum(len(t.get("examples") or ()) + sum(len(b.get("examples") or ()) for b in t.get("subtables") or ()) for t in x.get("tables") or ()) for x in secs),
              "linked": len(got["links"]), "headsHere": len(got["heads"]), "tablesHere": len(got["tables"]), "docGuides": len(d.get("guides") or ())}   # docGuides = 문서 전체에 닿는 일반 가이드라인(루트 guides — ② §5-9)
    bands = {t: [{"id": b["id"], "head": FG.head_text(b["head"]), "rows": b["rows"]} for b in v] for t, v in places["bands"].items()}
    out = {"form": {"key": f["key"], "name": f["name"], "how": f.get("how")}, "writable": ok and not broken, "why": broken or why, "sha1": sha or "", "exists": text is not None,
           "counts": counts, "unmatched": got["unmatched"][:200], "keywords": FG.keywords_found(d, s.doc.blocks()), "candidates": cands, "bands": bands, "rev": s.rev,
           "theme": d.get("theme") or ""}
    return out


@router.get("/api/docs/{doc_id}/form-guide")
def form_guide_get(doc_id: str):
    s = _sess_doc(doc_id)
    with s.lock:
        return _view(s)


def _sha_arg(body):
    sha = body.get("sha1")
    if sha is not None and not isinstance(sha, str):
        raise HTTPException(400, "sha1 은 문자열(읽었을 때의 판)이어야 합니다")
    return sha


def _open_for_write(s):
    f = _form(s)
    ok, why = _writable(s, f)
    if not ok:
        raise HTTPException(400, why)
    try:
        d, _, sha = FG.read(f["key"])
    except (ValueError, OSError) as e:
        raise HTTPException(400, f"양식 지침 파일을 읽을 수 없습니다 — 「YAML 고치기」 로 먼저 고치세요: {e}") from e
    return f, d, sha


def _save(f, d, sha, reason):
    try:
        FG.save(f["key"], d, expect=sha, reason=reason)
    except FG.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"양식 지침을 저장하지 못했습니다: {e}") from e


@router.post("/api/docs/{doc_id}/form-guide/promote")
def form_guide_promote(doc_id: str, body: dict = Body(...)):
    keys = body.get("keys")
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys):
        raise HTTPException(400, "keys(올릴 후보의 key 목록)가 필요합니다")
    sha = _sha_arg(body)
    s = _sess_doc(doc_id)
    from app import heading_runs
    with s.lock:
        f, d, cur = _open_for_write(s)
        if sha is not None and sha != cur:
            raise HTTPException(409, f"양식 지침 {f['key']} 이(가) 그 사이 바뀌었습니다 — 다시 읽어 주세요")
        places, _ = _places(s, heading_runs.tables(s) or {})
        heads, tabs, rules = _sources(s)
        cands = {c["key"]: c for c in FG.candidates(d, places, user_heads=heads, table_user=tabs, rules=rules)}
        want = list(dict.fromkeys(keys))
        gone = [k for k in want if k not in cands]
        if gone:   # 후보의 key = 글 · 대상 · 출처의 지문 — 하나라도 바뀌었으면(04 를 다시 돌림 · 지침을 고침) 사람이 본 것과 다른 글이 올라가지 않게 통째로 돌려보낸다(검토 P1)
            raise HTTPException(409, f"고른 후보 {len(gone)}건이 그 사이 바뀌었습니다(글 · 자리 · 출처) — 다시 읽어 확인한 뒤 올리세요")
        picks = [cands[k] for k in want]
        bad = next((c for c in picks if c.get("blocked")), None)
        if bad:
            raise HTTPException(400, bad["blocked"])
        n = FG.promote(d, places, picks, work=s.id, date=time.strftime("%Y-%m-%d"))
        if n:
            _save(f, d, cur, f"promote {n} from {s.id}")
        works.log(s.id, "formGuidePromote", form=f["key"], picked=len(picks), added=n)
        return {"added": n, "skipped": len(picks) - n, **_view(s)}


@router.post("/api/docs/{doc_id}/form-guide/skeleton")
def form_guide_skeleton(doc_id: str, body: dict = Body(default={})):
    """{sha1} → 지금 문서의 구조(본문 절 → 표 → 서브 테이블)를 양식 지침에 깐다(없는 항목만 · 지침 없이) → {added, …보기}."""
    sha = _sha_arg(body or {})
    s = _sess_doc(doc_id)
    from app import heading_runs
    with s.lock:
        f, d, cur = _open_for_write(s)
        if sha is not None and sha != cur:
            raise HTTPException(409, f"양식 지침 {f['key']} 이(가) 그 사이 바뀌었습니다 — 다시 읽어 주세요")
        if heading_runs.graph(s) is None:
            raise HTTPException(409, "헤딩 추출(2단계) 결과가 없습니다 — 문서 검토를 먼저 돌리세요")
        places, _ = _places(s, heading_runs.tables(s) or {})
        n = FG.skeleton(d, places)
        if n:
            _save(f, d, cur, f"skeleton {n} from {s.id}")
        works.log(s.id, "formGuideSkeleton", form=f["key"], added=n)
        return {"added": n, **_view(s)}


@router.post("/api/docs/{doc_id}/form-guide/example")
def form_guide_example(doc_id: str, body: dict = Body(...)):
    place, text = body.get("place"), body.get("text")
    if not isinstance(place, str) or not place or not isinstance(text, str):
        raise HTTPException(400, "place(헤딩 · 표 id)와 text(예시 글)가 필요합니다")
    band = body.get("band") if isinstance(body.get("band"), str) else None
    note = body.get("note") if isinstance(body.get("note"), str) else ""
    sha = _sha_arg(body)
    s = _sess_doc(doc_id)
    from app import heading_runs
    with s.lock:
        f, d, cur = _open_for_write(s)
        if sha is not None and sha != cur:
            raise HTTPException(409, f"양식 지침 {f['key']} 이(가) 그 사이 바뀌었습니다 — 다시 읽어 주세요")
        places, _ = _places(s, heading_runs.tables(s) or {})
        try:
            nid = FG.add_example(d, places, place, text, note=note, band_id=band, work=s.id, date=time.strftime("%Y-%m-%d"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        _save(f, d, cur, f"example {nid} from {s.id}")
        works.log(s.id, "formGuideExample", form=f["key"], node=nid, chars=len(text.strip()))
        return {"node": nid, "warn": FG.warnings(text, FG._value_words(_values(s))), **_view(s)}


def _key(key):
    try:
        HF.check_key(key)
    except ValueError as e:
        raise HTTPException(404, "그런 양식이 없습니다") from e
    return key


@router.get("/api/form-guides/{key}/yaml")
def form_guide_yaml_get(key: str):
    p = FG.path_of(_key(key))
    if p is None:
        raise HTTPException(503, "양식 정보 저장이 꺼져 있습니다(NFM_FORMS)")
    if HF.get(key) is None:
        raise HTTPException(404, "그런 양식이 없습니다")
    text = p.read_bytes().decode("utf-8") if p.is_file() else None
    if text is None:
        text = FG.dump({"schema": FG.SCHEMA, "form": key, "theme": "", "keywords": [], "sections": []})
    return {"key": key, "text": text, "sha1": FG._sha1(text) if p.is_file() else "", "exists": p.is_file()}


@router.put("/api/form-guides/{key}/yaml")
def form_guide_yaml_put(key: str, body: dict = Body(...)):
    if HF.get(_key(key)) is None:
        raise HTTPException(404, "그런 양식이 없습니다")
    text = body.get("text")
    if not isinstance(text, str):
        raise HTTPException(400, "text(YAML 글)가 필요합니다")
    try:
        d, sha = FG.save_text(key, text, expect=_sha_arg(body), reason="edit")
    except FG.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"양식 지침을 저장하지 못했습니다: {e}") from e
    return {"key": key, "sha1": sha, "sections": len(d["sections"]), "keywords": len(d["keywords"])}
