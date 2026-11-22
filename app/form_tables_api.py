"""양식의 표 등록부 끝점(spec_테이블매니저 ② §11 「표 · 띠 정체」) — 짓기 · 보기 · 지우기 · 이 문서의 표를 등록부에 잇기. 계산과 저장은 `app/form_tables.py`(순수 + 파일).
문서를 바꾸지 않고 LLM 도 부르지 않는다(판정은 3단계 결과의 것 — 빈 양식에서 LLM 표 판정을 돌렸으면 그 판정이 등록부에 든다).

- `POST /api/docs/{id}/form-tables/build {force?}` — 이 문서(hwpx · 양식이 정해진 문서)의 **마지막 3단계 결과**로 그 양식의 등록부를 짓는다(있으면 바꿔 쓴다).
  막는 것(409): 양식이 정해지지 않음 · 3단계 결과 없음 · 3단계 뒤 문서가 바뀜(그 결과가 지금 문서의 것이 아님) · **등록된 빈 양식이 아님**(올린 원본의 sha256 이 양식 정보
  `match.sha256` 에 없고, 내용 지문이 `match.blank` 에도 없음 — `force` 면 짓는다: 사람이 그 문서를 빈 양식으로 쓰겠다고 고른 것) · 등록부 파일이 깨짐.
  병합 방식 = `table_kinds.kinds`(편집 구역 없이 — 빈 양식에는 프로젝트 구성 값이 없다: 머리글의 꼴) · 구분 기준 엔진의 자리 = 구분 기준 판독(`division_scan_api.ensure` — 연구개발과제 문서만 ·
  값이 없으면 기본 구성 값으로 찾은 엔진 묶음).
- `GET /api/forms/{key}/tables` — 등록부(없으면 404 · 깨졌으면 409). `DELETE /api/forms/{key}/tables` — 옮겨 둔다(`form_tables.remove`).
- `GET /api/docs/{id}/form-tables` — 이 문서의 양식 · 등록부 요약 · 이 문서의 표마다 이은 항목(`form_tables.link` — 스크립트 몫) · 안 이어진 항목.
  양식이 없거나 등록부가 없거나 3단계 결과가 없으면 그 까닭(`missing`)만 싣는다(404 가 아니다 — 「테이블」 탭이 열릴 때마다 묻는다). 낡은 3단계 결과는 `stale: true` 를 싣고 그대로 잇는다."""
import logging

from fastapi import APIRouter, Body, HTTPException

from app import form_tables as FT
from app import heading_forms as HF

router = APIRouter()
log = logging.getLogger("uvicorn.error")


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    return server._sess(doc_id)


def _form(s):
    try:
        f = HF.for_session(s)
    except (OSError, ValueError):
        return None
    return {"key": f["key"], "name": f.get("name") or f["key"], "text": f.get("text") or ""} if f else None


def _key(key):
    try:
        HF.check_key(key)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return key


def _load(key):
    try:
        return FT.load(key)
    except FT.Broken as e:
        raise HTTPException(409, str(e)) from e


def blank_of(s, form, blocks):
    """이 문서가 그 양식의 **등록된 빈 양식**인가 → "sha256" | "blank"(내용 지문) | None."""
    from app import merge_table_map
    try:
        sha = HF.doc_sha(s)
    except Exception:  # noqa: BLE001 — 원본 바이트를 못 읽으면 지문으로만 본다
        sha = None
    text = form.get("text") or ""
    head = HF.parse(text) if text else {"sha256": []}
    if sha and sha.lower() in {x.lower() for x in head.get("sha256") or ()}:
        return "sha256"
    fps = HF.blank_fps(text)
    if fps and merge_table_map.blank_fp(blocks) in fps:
        return "blank"
    return None


def _engine_groups(s):
    from app import division_scan_api
    try:
        e = division_scan_api.ensure(s)
    except Exception:  # noqa: BLE001 — 엔진 자리를 못 읽어도 등록부의 다른 값은 짓는다
        log.exception("[양식의 표 등록부] 구분 기준 판독을 읽지 못했습니다 — 엔진 자리 없이 짓습니다")
        return []
    return list(((e or {}).get("result") or {}).get("_groups") or ())


@router.post("/api/docs/{doc_id}/form-tables/build")
def build(doc_id: str, body: dict = Body(default={})):
    """→ {form, summary, blank: sha256|blank|forced} — 등록부를 짓고 저장."""
    from app import heading_runs, table_kinds
    s = _sess(doc_id)
    if getattr(s, "fmt", None) != "hwpx":
        raise HTTPException(400, "양식의 표 등록부는 지금 hwpx 문서로만 짓습니다")
    force = bool((body or {}).get("force"))
    form = _form(s)
    if form is None:
        raise HTTPException(409, "양식이 정해지지 않은 문서입니다 — 양식 정보에서 양식을 고르세요")
    with s.lock:
        t3 = heading_runs.tables(s)
        rev, blocks = s.rev, s.doc.blocks()
    if not isinstance(t3, dict) or not isinstance(t3.get("tables"), list):
        raise HTTPException(409, "표 구조(헤딩 추출 3단계) 결과가 없습니다 — 「테이블」 탭에서 표 구조를 먼저 만드세요")
    if (t3.get("meta") or {}).get("rev") != rev:
        raise HTTPException(409, "표 구조를 만든 뒤 문서가 바뀌었습니다 — 표 구조를 다시 만든 뒤 지으세요(등록부는 빈 양식 그대로의 표로 짓습니다)")
    how = blank_of(s, form, blocks)
    if how is None and not force:
        raise HTTPException(409, f"이 문서는 「{form['name']}」 의 등록된 빈 양식이 아닙니다 — 빈 양식으로 지으세요(이 문서로 지으려면 force)")
    kinds = [table_kinds.kinds(t, None, t3.get("repeats")) for t in t3["tables"] if isinstance(t, dict)]
    meta = t3.get("meta") or {}
    llm = t3.get("llm") if isinstance(t3.get("llm"), dict) else {}   # 3단계의 LLM 표 판정(T 호출) 기록 — 호출이 있고 거꾸로 돌아가지(fallback) 않았으면 LLM 판정을 거친 결과
    source = {"doc": getattr(s, "name", ""), "sha256": HF.doc_sha(s), "run": meta.get("run"), "blank": how or "forced",
              "llm": bool(llm.get("calls")) and not llm.get("fallback")}
    reg = FT.build(form["key"], t3, kinds=kinds, groups=_engine_groups(s), source=source)
    try:
        saved = FT.save(form["key"], reg)
    except FT.Broken as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return {"form": {"key": form["key"], "name": form["name"]}, "summary": FT.summary(saved), "blank": how or "forced"}


@router.get("/api/forms/{key}/tables")
def get_registry(key: str):
    reg = _load(_key(key))
    if reg is None:
        raise HTTPException(404, f"양식 「{key}」 의 표 등록부가 없습니다")
    return reg


@router.delete("/api/forms/{key}/tables")
def delete_registry(key: str):
    _key(key)
    moved = FT.remove(key)
    if moved is None:
        raise HTTPException(404, f"양식 「{key}」 의 표 등록부가 없습니다")
    return {"ok": True, "moved": moved}


@router.get("/api/docs/{doc_id}/form-tables")
def doc_links(doc_id: str):
    """→ {form, registry(요약) | None, blank, links{표 id: …}, missing[], counts, stale?} | {form: None, missing: "form"} 꼴(까닭만)."""
    from app import heading_runs
    s = _sess(doc_id)
    if getattr(s, "fmt", None) != "hwpx":
        return {"form": None, "registry": None, "missing": "format"}
    form = _form(s)
    if form is None:
        return {"form": None, "registry": None, "missing": "form"}
    out = {"form": {"key": form["key"], "name": form["name"]}}
    try:
        reg = FT.load(form["key"])
    except FT.Broken as e:
        return {**out, "registry": None, "missing": "broken", "error": str(e)}
    with s.lock:
        t3 = heading_runs.tables(s)
        rev, blocks = s.rev, s.doc.blocks()
    out["blank"] = blank_of(s, form, blocks)
    if reg is None:
        return {**out, "registry": None, "missing": "registry"}
    out["registry"] = FT.summary(reg)
    if not isinstance(t3, dict) or not isinstance(t3.get("tables"), list):
        return {**out, "missing": "stage3", "links": {}, "missing_entries": [], "counts": {}}
    got = FT.link(reg, t3)
    out.update(links=got["links"], missing_entries=got["missing"], counts=got["counts"], entries={e["id"]: _brief(e) for e in reg.get("tables") or ()})
    if (t3.get("meta") or {}).get("rev") != rev:
        out["stale"] = True
    return out


def _brief(e):
    """항목의 화면 꼴(칸 글 · 머리글 몇 개 · 사슬)."""
    return {k: e.get(k) for k in ("id", "name", "title", "path", "order", "host", "rows", "cols", "type", "kind", "repeat", "division")} | {
        "subs": [{k: b.get(k) for k in ("id", "at", "kind", "merge", "basis", "heads")} for b in e.get("subs") or ()]}
