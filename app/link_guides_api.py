"""매칭 지침 — 표 · 본문별: 보기 · 더하기 · 고치기 · 지우기(spec_병합 ② §5-6, 2026-11-22 사용자 「테이블, 본문별로 어떻게 매칭해야하는지 지침을 관리하고 LLM 이 검토할때 이 부분을 검토할 수 있도록」).
원본 = 목적 문서 양식의 양식 정보 「자리 연결」 절(`forms/<양식>.md` — 연결 코멘트와 같은 절 · 같은 저장 길: heading_forms.save). 여기는 그 절을 지침 하나하나로 읽고(app/link_guides.py) 고쳐 저장하는 끝점뿐이다.

- `GET    /api/docs/{to}/link-guides` → {formInfo{key, name} | null, canSave, guides[{n, kind("table" | "body"), title, text, pages, places[{id, kind, text}]}], comments[{date, text}]}
  — places = 이 문서에서 그 지침이 걸리는 자리(표 · 헤딩 줄: 화면이 그 자리로 간다 · 없으면 빈 목록 = 이 문서에는 그 자리가 없다).
- `PUT    /api/docs/{to}/link-guides` {kind, title, text, n?} → 더하기(n 없음) · 고치기(n) → 위와 같은 몸통.
- `DELETE /api/docs/{to}/link-guides/{n}` → 지우기 → 위와 같은 몸통.
문서 · 세션 상태는 안 바꾼다(양식 정보 파일만). 이 글은 LLM 검토(자리 연결 · 표 대응 · 빈 자리)가 읽는 판단 기준이다 — 스크립트의 동작을 바꾸는 설정이 아니다(쪽 한도 하나만 빈 자리 검토가 읽는다)."""
from fastapi import APIRouter, Body, HTTPException

from app import heading_forms as HF
from app import heading_runs as HR
from app import link_guides as LG
from app import merge_api
from app import merge_pairs as P

router = APIRouter()
HEADS = ("heading", "subtitle", "label")
PLACES_MAX, TEXT = 6, 80


def _places(doc_id):
    """이 문서의 자리 목록 → [{id, kind("table" | "body"), text, more[견줄 다른 글]}] — 헤딩 줄(2단계 그래프)과 표(3단계 — 소속 제목 · 첫 칸의 글). 분석이 없으면 빈 목록."""
    from app import server
    from app.division_profiles import _structure as structure
    s = server._sess(doc_id)
    with s.lock:
        if s.fmt != "hwpx":
            return []
        g, t = HR.graph(s), HR.tables(s)
        idx = structure.index_blocks(s.doc.blocks())
    out = []
    for n in (g or {}).get("nodes") or ():
        b = idx.get(n["id"])
        if n.get("role") in HEADS and b is not None and (b.get("text") or "").strip():
            out.append({"id": n["id"], "kind": "body", "text": P._ws(b["text"]), "more": []})
    for tb in (t or {}).get("tables") or ():
        if tb["id"] not in idx:
            continue
        own = tb.get("owner") or {}
        first = next((c for c in tb.get("cells") or () if c.get("row") == 0 and c.get("col") == 0), None)
        texts = [x for x in (P._ws(own.get("text") or ""), P._ws((idx.get((first or {}).get("id")) or {}).get("text") or "")) if x]
        if texts:
            out.append({"id": tb["id"], "kind": "table", "text": texts[0], "more": texts[1:]})
    return out


def _view(doc_id):
    form = merge_api._link_form(doc_id)
    ents = LG.entries(form["text"]) if form else []
    try:
        places = _places(doc_id)
    except HTTPException:
        raise
    except Exception:   # 자리 찾기는 덤이다 — 못 읽어도 지침 목록은 나가야 한다
        places = []
    for e in ents:
        e["places"] = [{"id": p["id"], "kind": p["kind"], "text": p["text"][:TEXT]} for p in places if p["kind"] == e["kind"] and LG.match([e], [p["text"], *p["more"]], e["kind"])][:PLACES_MAX]
    return {"formInfo": {"key": form["key"], "name": form["name"]} if form else None, "canSave": HF.forms_dir() is not None, "guides": ents, "comments": merge_api._link_comments(doc_id)}


def _save(doc_id, edit, reason):
    """양식 정보에 고친 글을 저장(연결 코멘트 merge_api.merge_link_comment 와 같은 길 — 맞는 양식이 없으면 그 문서의 양식 정보를 만든다 · 그 사이 다른 곳에서 고쳤으면 한 번 다시 읽어 얹는다)."""
    from app import heading_rules, server
    s = server._sess(doc_id)
    if HF.forms_dir() is None:
        raise HTTPException(503, "양식 정보 저장이 꺼져 있어 지침을 남길 수 없습니다(NFM_FORMS)")
    with s.lock:
        name = server.PROFILE.form_of(s.doc.blocks())
    try:
        for again in (True, False):
            form = HF.pin(s)
            if form is None:
                new = HF.bare(name or s.name, HF.doc_sha(s))
                try:
                    form = HF.get(new["key"])
                except KeyError:
                    form = {**new, "sha1": ""}
            try:
                saved = HF.save(form["key"], edit(form["text"]), expect=form["sha1"], reason=reason)
                break
            except heading_rules.StaleVersion:
                if not again:
                    raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except (heading_rules.StaleVersion, OSError) as e:
        raise HTTPException(503, f"지침을 양식 정보에 남기지 못했습니다: {e}") from e
    if form.get("how") is None:
        try:
            HF.set_choice(s.id, saved["key"])
        except (KeyError, ValueError, OSError):
            pass
    return _view(doc_id)


@router.get("/api/docs/{doc_id}/link-guides")
def guides_get(doc_id: str):
    """매칭 지침 목록(모듈 설명)."""
    return _view(doc_id)


@router.put("/api/docs/{doc_id}/link-guides")
def guides_put(doc_id: str, body: dict = Body(...)):
    """지침 하나 더하기 · 고치기 {kind, title, text, n?} → 목록. 400 = 모르는 종류 · 빈 글 · 없는 n."""
    kind, title, text, n = body.get("kind"), body.get("title"), body.get("text"), body.get("n")
    if n is not None and (not isinstance(n, int) or isinstance(n, bool)):
        raise HTTPException(400, "n 은 지침 번호(정수)입니다")
    return _save(doc_id, lambda raw: LG.put(raw, kind, title, text, n), "매칭 지침")


@router.delete("/api/docs/{doc_id}/link-guides/{n}")
def guides_delete(doc_id: str, n: int):
    """지침 하나 지우기 → 목록. 400 = 없는 n."""
    return _save(doc_id, lambda raw: LG.drop(raw, n), "매칭 지침 지움")
