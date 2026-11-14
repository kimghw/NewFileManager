"""서식 보관함 끝점(spec_일반편집 ② §7) — 보관함(목록·읽기·고치기·지우기·검증) · 문서에서 저장 · 파일에서 추출 · 문서에 적용.

- 저장소 `app/style_lib.py` · 운반 문서 `app/style_carrier.py` · 적용 `app/style_apply.py`. 추출 후보(`app/style_extract.py`)와 PDF 검증(`app/style_verify.py`)은
  **부를 때 가져온다** — 그 모듈이 없으면 그 기능만 빠진다(후보·파일 추출 501 · 검증은 null).
- 적용은 구조 편집 트랜잭션 `server._edit` 하나(잠금·스냅샷·OWPML 검사·실행 취소 1개·기록 `styleApply`): `make(s)` 에서는 **검사만**, 가져오기·삽입은 모두 `run()` 안
  (스냅샷이 `make` 뒤에 찍힌다). `run()` 의 예상 밖 예외는 ValueError 로 바꿔 던진다(트랜잭션이 되돌리고 400). 대상 문서는 hwpx 만.
  **쓰기 정책**(`doc_agent.policy` — 에이전트 반영과 같은 것)을 `make(s)` 에서 = 세션 잠금 안에서 본다: 그 TASK 의 원본 문서(이관의 사업계획서 · 취합의 기관 문서)는 403.
- 고치기·지우기는 `expectedRevision` 을 **꼭 받는다**(없거나 revision 꼴이 아니면 400 · 지금 것과 다르면 409) — 깨진 템플릿을 지울 때만 없이.
- 저장하는 글(기본 이름 · 구조 blueprint 의 라벨)은 **운반 문서에 남긴 글**에서만 읽는다(원본 문서의 칸 글이 아니라 — `style_carrier.label_cells`).
- 상태 코드: 없는 id·깨진 템플릿 404 · revision 다름 409 · 보관함 끔 503 · hwpx 아님·틀린 입력·expectedRevision 없음·끊어진 참조 400 · 원본 문서 403 · 토큰 만료 410 · 모듈 없음 501."""
import importlib
import logging
import re
import time
from urllib.parse import quote

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from app import heading_runs, pdf_render, style_apply, style_carrier, style_lib, table_make, works
from app.hwpx_doc import P

router = APIRouter()
log = logging.getLogger(__name__)
MODES = ("tableMake", "tableBlank", "tableRestyle", "format")
PARAS_MAX, PICKS_MAX, UPLOAD_MB = 2000, 60, 100
BP_ROLES = ("label", "input", "computed", "note")


# ---- 공통 ---------------------------------------------------------------------------------------------------------

def _mod(name):
    """뒤에 붙는 모듈(app.style_extract · app.style_verify) | None(아직 없음 · 가져오기 실패)."""
    try:
        return importlib.import_module(f"app.{name}")
    except ImportError:
        return None


def _on():
    if not style_lib.enabled():
        raise HTTPException(503, "서식 보관함이 꺼져 있습니다")


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    return server._sess(doc_id)


def _hwpx(s):
    if not hasattr(s.doc, "table_make"):
        raise HTTPException(400, "서식 보관함의 추출·적용은 지금 hwpx 문서만 됩니다")


def _meta(sid):
    _on()
    m = style_lib.get(sid)
    if m is None:
        raise HTTPException(404, "그 서식이 서식 보관함에 없습니다")
    return m


def _expected(value) -> str:
    """요청의 expectedRevision(읽었을 때의 revision) — 없거나 revision 꼴(「r3」)이 아니면 400. 성한 템플릿의 고치기·지우기는 이것 없이 안 된다(오래된 화면의 덮어쓰기·삭제 막이)."""
    if not isinstance(value, str) or not style_lib.RID.fullmatch(value):
        raise HTTPException(400, style_lib.NEED_EXPECTED)
    return value


def _verify(meta, full=True):
    """meta.verify 의 보기 — 도는 중이면 status "running"(메모리), stale = 검증 뒤 meta(띠 수·blueprint·items)가 바뀜. full 이 아니면 {status, coverage, stale} 만."""
    v, sv = meta.get("verify") if isinstance(meta.get("verify"), dict) else None, _mod("style_verify")
    stale = running = False
    try:
        running = bool(sv is not None and sv.running(meta["id"]))
        stale = bool(v and sv is not None and v.get("subjectHash") and v["subjectHash"] != sv.subject_hash(meta))
    except Exception as e:  # noqa: BLE001 — 검증 모듈의 오류가 목록을 막지 않는다
        log.warning("서식 검증 상태를 읽지 못함: %r", e)
    if v is None and not running:
        return None
    out = {**(v or {}), "stale": stale} if full else {"status": (v or {}).get("status"), "coverage": (v or {}).get("coverage"), "stale": stale}
    return {**out, "status": "running"} if running else out


def _full(meta) -> dict:
    return {**meta, "verify": _verify(meta)}


def _kick(sid, force=False):
    """그 템플릿의 PDF 검증을 건다(작업 — 동기 응답이 아니다) -> 도는 기록 | None(검증 모듈 없음 · 못 걺)."""
    sv = _mod("style_verify")
    if sv is None:
        return None
    try:
        return sv.start(sid, force=True) if force else sv.start(sid)
    except Exception as e:  # noqa: BLE001 — 검증을 못 걸어도 저장은 된 것이다
        log.warning("서식 검증을 걸지 못함 %s: %r", sid, e)
        return None


def _store(fn):
    """저장소 호출 하나 — Stale 409 · 없는 id 404 · 틀린 값 400 · 쓰기 실패 503."""
    try:
        return fn()
    except style_lib.Stale as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, "그 서식이 서식 보관함에 없습니다") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"서식 보관함에 쓰지 못했습니다: {e}") from e


# ---- 보관함 --------------------------------------------------------------------------------------------------------

@router.get("/api/styles")
def styles_list():
    """{enabled, pdf: 한글 PDF 출력이 되는가, styles: [meta 요약 — losses 는 수 · blueprint 는 있나 · verify 는 {status, coverage, stale}], broken: [깨진 id]}.
    broken = current·meta 를 못 읽는 것 + 운반 문서가 없거나 바뀐(해시가 meta 와 다른) 것 — 읽기·고치기·적용은 404, 지우기만 된다(expectedRevision 없이)."""
    got = style_lib.listing()
    return {"enabled": style_lib.enabled(), "pdf": pdf_render.available("hwpx"), "broken": got["broken"],
            "styles": [{**m, "losses": len(m.get("losses") or []), "blueprint": bool(m.get("blueprint")), "verify": _verify(m, full=False)} for m in got["styles"]]}


@router.get("/api/styles/{sid}")
def style_get(sid: str):
    """{...meta(verify 는 기록 전체 + stale), view} — view = 표: {table, grid(글 전체), spec} · 글: {paras, items}(`style_carrier.view`), 운반 문서를 못 읽으면 null + viewError."""
    meta = _meta(sid)
    try:
        view, err = style_carrier.view(style_lib.carrier(sid) or b"", meta), None
    except ValueError as e:
        view, err = None, str(e)
    return {**_full(meta), "view": view, **({"viewError": err} if err else {})}


@router.get("/api/styles/{sid}/proof.png")
def style_proof(sid: str):
    _meta(sid)
    p = style_lib.file(sid, "proof.png")
    if p is None:
        raise HTTPException(404, "검증 그림이 아직 없습니다")
    return Response(p.read_bytes(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/api/styles/{sid}/carrier")
def style_carrier_file(sid: str):
    """운반 문서(hwpx) 내려받기 — 한글에서 열어 서식을 눈으로 볼 수 있다."""
    meta, data = _meta(sid), style_lib.carrier(sid)
    if data is None:
        raise HTTPException(404, "운반 문서가 없습니다")
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", meta["name"]).strip("_") or sid
    return Response(data, media_type="application/hwp+zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}.hwpx", "Cache-Control": "no-store"})


def _blueprint_in(bp, meta):
    """PUT 으로 받은 blueprint → 고른 꼴 | None(없앰). 칸은 표 안의 자리·아는 역할만. 라벨 글은 label·note 칸에만, 그것도 **운반 문서의 그 칸 글**로 적는다 —
    요청이 보낸 label 글은 쓰지 않는다(자료값이 그 길로 저장되지 않게)."""
    if bp is None:
        return None
    if not isinstance(bp, dict) or not isinstance(bp.get("cells"), list):
        raise HTTPException(400, "blueprint 는 {cells: [...], formulas?: [...]} 또는 null")
    try:
        texts = style_carrier.cell_texts(style_lib.carrier(meta["id"]) or b"")
    except ValueError:
        texts = {}
    cells = []
    for c in bp["cells"]:
        try:
            row, col, rs, cs = (int(c.get(k) or d) for k, d in (("row", 0), ("col", 0), ("rowSpan", 1), ("colSpan", 1)))
        except (AttributeError, TypeError, ValueError) as e:
            raise HTTPException(400, "blueprint.cells 의 row·col 은 정수") from e
        if not (0 <= row < meta["rows"] and 0 <= col < meta["cols"]) or c.get("role") not in BP_ROLES:
            raise HTTPException(400, f"blueprint.cells: 표 밖의 칸이거나 role 이 {'·'.join(BP_ROLES)} 이 아닙니다")
        cells.append({"row": row, "col": col, "rowSpan": max(1, rs), "colSpan": max(1, cs), "role": c["role"],
                      "label": (texts.get((row, col)) or None) if c["role"] in ("label", "note") else None})
    formulas = [{"ref": str(f.get("ref") or "")[:12], "formula": str(f.get("formula") or "")[:400]} for f in bp.get("formulas") or [] if isinstance(f, dict)]
    return {"cells": cells, "formulas": formulas}


def _items_in(given, meta):
    """PUT 으로 받은 items [{key, name?, level?}] → meta.items 에 이름·레벨만 고친 것(서식·레터 정책은 운반 문서와 짝이라 못 고친다)."""
    if not isinstance(given, list) or not all(isinstance(x, dict) for x in given):
        raise HTTPException(400, "items 는 [{key, name?, level?}]")
    by = {x.get("key"): x for x in given}
    if set(by) - {it["key"] for it in meta["items"]}:
        raise HTTPException(400, "items: 이 서식에 없는 항목 key 가 있습니다")
    out = []
    for it in meta["items"]:
        x, new = by.get(it["key"]) or {}, dict(it)
        if "name" in x:
            name = re.sub(r"\s+", " ", x["name"]).strip() if isinstance(x["name"], str) else ""
            if not 1 <= len(name) <= style_lib.NAME_MAX:
                raise HTTPException(400, f"항목 이름은 1~{style_lib.NAME_MAX}자")
            new["name"] = name
        if "level" in x:
            if x["level"] is not None and (not isinstance(x["level"], int) or isinstance(x["level"], bool) or not 1 <= x["level"] <= 20):
                raise HTTPException(400, "항목 레벨은 1~20 의 정수 또는 null")
            new["level"] = x["level"]
        out.append(new)
    return out


@router.put("/api/styles/{sid}")
def style_put(sid: str, body: dict = Body(...)):
    """{expectedRevision, name?, note?, bands?, blueprint?, items?: [{key, name?, level?}]} → meta(새 revision). 운반 문서는 그대로(검증 기록도 물려받는다 —
    띠 수·blueprint·items 가 바뀌면 `verify.stale`). expectedRevision 은 **꼭** — 없거나 revision 꼴이 아니면 400, 지금과 다르면 409."""
    meta, ch = _meta(sid), {}
    expected = _expected(body.get("expectedRevision"))
    for k in ("name", "note"):
        if k in body:
            ch[k] = body[k]
    table = meta["kind"] == "table"
    if any(body.get(k) is not None for k in (("items",) if table else ("bands", "blueprint"))):
        raise HTTPException(400, "표 서식은 bands·blueprint, 글 서식은 items 만 고칩니다")
    if table and body.get("bands") is not None:
        ch["bands"] = table_make.clean_roles(body["bands"], meta["rows"], meta["cols"], default=meta.get("bands"))
    if table and "blueprint" in body:
        ch["blueprint"] = _blueprint_in(body["blueprint"], meta)
    if not table and body.get("items") is not None:
        ch["items"] = _items_in(body["items"], meta)
    return _full(_store(lambda: style_lib.revise(sid, expected, ch)))


@router.delete("/api/styles/{sid}")
def style_delete(sid: str, expectedRevision: str | None = None):  # noqa: N803 — 쿼리 이름 그대로
    """?expectedRevision= — 성한 템플릿은 **꼭**(없거나 revision 꼴이 아니면 400 · 지금 revision 과 다르면 409). **깨진 템플릿**(목록의 `broken` — current·meta 를 못 읽음,
    운반 문서가 없거나 바뀜: 읽을 revision 이 없다)만 없이 지운다. → {deleted}."""
    _on()
    expected = _expected(expectedRevision) if style_lib.get(sid) is not None else None  # 없는 것은 아래에서 404
    if not _store(lambda: style_lib.delete(sid, expected)):
        raise HTTPException(404, "그 서식이 서식 보관함에 없습니다")
    return {"deleted": sid}


@router.post("/api/styles/{sid}/verify")
def style_verify(sid: str, body: dict = Body(default={})):
    """PDF 검증을 다시 건다(작업 — 화면은 `GET /api/styles/{sid}` 를 다시 읽는다) → 202 {status: "running", revision}. {force?: false} 가 아니면 PDF 캐시를 지우고 다시 출력."""
    _meta(sid)
    if _mod("style_verify") is None:
        raise HTTPException(501, "PDF 검증 모듈(app.style_verify)이 없습니다")
    rec = _kick(sid, force=(body or {}).get("force") is not False)
    if rec is None:
        raise HTTPException(503, "검증을 시작하지 못했습니다")
    return JSONResponse({**rec, "status": "running"}, status_code=202)


# ---- 문서에서: 후보 · 저장 --------------------------------------------------------------------------------------------

def _named(cands, res) -> dict:
    """이름 붙이기(LLM — `style_extract.name`)의 답 {"tables": {후보 key: {name, keep, bands, bandsChanged}}, "texts": {key: {name, keep}}, "note", "call"} 을 후보 목록에 합친다
    -> {"tables", "texts", "note", "call"}. 답에 없는 후보는 그대로(이름 없음)."""
    res = res if isinstance(res, dict) else {}
    out = {}
    for k in ("tables", "texts"):
        names = res.get(k) if isinstance(res.get(k), dict) else {}
        out[k] = [{**c, **names[c["key"]]} if isinstance(names.get(c.get("key")), dict) else c for c in cands.get(k) or []]
    return {**out, "note": str(res.get("note") or ""), "call": res.get("call")}


@router.post("/api/docs/{doc_id}/styles/candidates")
def style_candidates(doc_id: str, body: dict = Body(default={})):
    """{llm?: false} → {rev, tables, texts, stage2: 2단계 그래프가 있나, call?} — 이 문서의 표 서식·글 서식 후보(스크립트 — 문서 안 바뀜). llm true = 후보에 이름·저장할 만한가·띠 수 보정을
    받아 합친다(누를 때만 — 잠금 밖, 동기). hwpx 만."""
    s = _sess(doc_id)
    _hwpx(s)
    se = _mod("style_extract")
    if se is None:
        raise HTTPException(501, "서식 추출 모듈(app.style_extract)이 없습니다")
    graph = heading_runs.graph(s)  # 작업 파일을 읽으므로 세션 잠금 밖에서
    with s.lock:
        try:
            cands = se.candidates(s.doc, graph)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        rev = s.rev
    out = {"rev": rev, "tables": cands.get("tables") or [], "texts": cands.get("texts") or [], "stage2": graph is not None}
    if (body or {}).get("llm") is True:
        from app import llm
        if not llm.status()["available"]:
            raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐) — 이름은 직접 붙일 수 있습니다")
        res = se.name(cands)
        out.update(_named(out, res))
        call = out["call"] if isinstance(out["call"], dict) else {}
        detail = works.add_detail(s.id, "styles", f"name_{int(time.time() * 1000)}", {"rev": rev, "prompt": res.get("prompt"), "response": res.get("response"), "call": call})
        works.log(s.id, "styleName", rev=rev, named=sum(1 for c in out["tables"] + out["texts"] if c.get("name")), backend=call.get("backend"), ms=call.get("ms"),
                  costUsd=call.get("costUsd"), error=call.get("error"), detail=detail)
        if call.get("error") and not any(c.get("name") for c in out["tables"] + out["texts"]):
            raise HTTPException(502, f"LLM 이 이름을 붙이지 못했습니다: {call['error']}")
    return out


def _label_texts(data, info) -> dict:
    """막 만든 표 운반 문서의 라벨 칸 글 {(행, 열): 글} — info.labels(글을 남긴 칸)의 글을 **운반 문서에서** 읽는다(기본 이름·구조의 라벨은 여기서만)."""
    texts = style_carrier.cell_texts(data)
    return {tuple(rc): texts[tuple(rc)] for rc in info.get("labels") or [] if tuple(rc) in texts}


def _blueprint(s, tid, block, labels) -> dict:
    """지금 표에서 구조(blueprint)를 읽는다 — 라벨 칸(labels = `_label_texts`: 운반 문서에 글을 남긴 칸) = label(그 글), 엑셀 판정(`table_excel.judge`)의 수식 대상 칸 = computed
    (수식 글은 formulas 에 참고로), 나머지 = input. 머리 띠 안이라도 라벨이 아닌 칸(머리 표시가 없는 줄 · 자료처럼 보이는 글)은 input 이다 — 그 글(자료값)은 싣지 않는다. 세션 잠금 안에서."""
    from app import table_excel, tables_api
    try:
        judged = table_excel.judge(s.doc, tid, doc_key=getattr(s, "doc_key", None), roles=tables_api._heads(s, tid)) or {}
    except ValueError:  # 너무 큰 표 — 수식 없이
        judged = {}
    formulas = [f for f in judged.get("formulas") or [] if f.get("cell") and f.get("formula")]
    targets, cells = {f["cell"] for f in formulas}, []
    for c in sorted(block["cells"], key=lambda c: (c["row"], c["col"])):
        label = (c["row"], c["col"]) in labels
        cells.append({"row": c["row"], "col": c["col"], "rowSpan": c["rowSpan"], "colSpan": c["colSpan"],
                      "role": "label" if label else "computed" if c["id"] in targets else "input", "label": labels[c["row"], c["col"]] if label else None})
    return {"cells": cells, "formulas": [{"ref": f.get("ref"), "formula": f["formula"]} for f in formulas]}


def _template_picks(s, g, tid):
    """2단계 그래프 g 의 템플릿 tid → (템플릿, picks — 슬롯마다 대표 문단). 대표 서식이 없는 슬롯·대표 문단이 문서에 없는 슬롯은 뺀다. 그래프가 없으면 400. 세션 잠금 안에서."""
    if not g:
        raise HTTPException(400, "2단계(개요템플릿) 결과가 없습니다 — 헤딩 추출을 먼저 돌리거나, 문단을 골라 문단 서식으로 저장하세요")
    t = next((t for t in g.get("templates") or [] if str(t.get("id", t.get("no"))) == str(tid)), None)
    if t is None:
        raise HTTPException(404, "그 템플릿이 2단계 결과에 없습니다")
    picks = []
    for slot in t.get("slots") or []:
        el = s.doc._ids.get(slot.get("rep"))
        if slot.get("format") and el is not None and el.tag == P and s.doc._attached(el):
            picks.append({"para": slot["rep"], "level": int(slot["level"]), "origin": {"template": t.get("id", t.get("no")), "slot": int(slot["level"])},
                          "name": f"{int(slot['level'])}수준 {slot.get('letter') or ''}".strip()})
    if not picks:
        raise HTTPException(400, "그 템플릿에 저장할 대표 문단이 없습니다(추출 뒤 문서가 바뀌었으면 헤딩 추출을 다시 돌리세요)")
    return t, picks


def _para_picks(s, ids):
    """고른 문단들 → picks(레벨 없음) — 서식(문단 모양 + 첫 글 런의 글자 모양)이 같은 문단은 하나로."""
    if not isinstance(ids, list) or not ids or len(ids) > PARAS_MAX or not all(isinstance(i, str) for i in ids):
        raise HTTPException(400, f"paras 는 문단 id 1~{PARAS_MAX}개")
    seen, picks = set(), []
    for i in ids:
        el = s.doc._ids.get(i)
        if el is None or el.tag != P or not s.doc._attached(el):
            raise HTTPException(404, "고른 문단이 지금 문서에 없습니다 — 문서에서 다시 고르세요")
        token = s.doc.get_format(i)["token"]
        if token not in seen:
            seen.add(token)
            picks.append({"para": i, "level": None, "origin": None})
    return picks


@router.post("/api/docs/{doc_id}/styles")
def style_save(doc_id: str, body: dict = Body(...)):
    """문서의 표·문단 서식을 보관함에 저장(문서는 안 바뀜) → 201 meta(+ PDF 검증을 건다). hwpx 만.
    {kind: "table", table, name?, bands?, keepText?, blueprint?: bool} | {kind: "text", template: 템플릿 id, name?, keepText?} | {kind: "text", paras: [ids], name?, keepText?}.
    표 meta 의 `labels` = 운반 문서에 글을 남긴 라벨 칸 [[행, 열]…](`style_carrier.label_cells`) — 기본 이름(첫 라벨 글 + 「 표」, 없으면 「표 R×C」)과 blueprint 의 label 은 그 칸의 글뿐이다.
    고른 표·문단이 닿는 정의 참조가 끊어져 있으면 400(깨진 템플릿을 보관함에 넣지 않는다)."""
    _on()
    s = _sess(doc_id)
    _hwpx(s)
    kind, keep = body.get("kind"), body.get("keepText") is True
    if kind not in style_lib.KINDS:
        raise HTTPException(400, "kind 는 table 또는 text")
    by_template = kind == "text" and body.get("template") is not None
    graph = heading_runs.graph(s) if by_template else None  # 그래프(작업 파일)는 잠금 밖에서 읽는다
    try:
        with s.lock:
            src = {"name": s.name, "format": "hwpx", "work": s.id, "page": None, "sha256": getattr(s, "doc_key", None)}
            if kind == "table":
                from app import tables_api
                tid = body.get("table")
                block = tables_api._live_table(s, tid, "서식으로 저장할 표")
                bands = table_make.clean_roles(body.get("bands"), block["nRows"], block["nCols"], default=table_make.roles_of(block["cells"], block["nRows"], block["nCols"]))
                data, info = style_carrier.from_table(s.doc, tid, bands, keep_text=keep)
                labels = _label_texts(data, info)
                first = next((t.strip().split("\n")[0] for _, t in sorted(labels.items()) if t.strip()), "")  # 기본 이름은 라벨 칸의 글에서만 — 없으면 표 크기
                meta = {"kind": "table", "name": body.get("name") or (f"{first[:24]} 표" if first else f"표 {info['rows']}×{info['cols']}"), "source": {**src, "block": tid},
                        "losses": info["losses"], "requirements": {"fonts": info["fonts"]}, "bands": info["bands"], "rows": info["rows"], "cols": info["cols"], "labels": info["labels"],
                        "blueprint": _blueprint(s, tid, block, labels) if body.get("blueprint") is True else None, "preview": info["preview"]}
            else:
                t, picks = _template_picks(s, graph, body["template"]) if by_template else (None, _para_picks(s, body.get("paras")))
                data, items = style_carrier.from_paras(s.doc, picks, keep_text=keep)
                meta = {"kind": "text", "name": body.get("name") or (f"템플릿 {t.get('no', t.get('id'))} 글 서식" if t else "문단 서식"), "source": {**src, "block": picks[0]["para"]},
                        "losses": [style_carrier.STYLE_NOTE], "requirements": {"fonts": style_carrier.fonts_of(style_carrier.doc(data))}, "items": items}
            rev = s.rev
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    out = _store(lambda: style_lib.create({**meta, "note": body.get("note") or "", "fidelity": "native"}, data))
    works.log(s.id, "styleSave", rev=rev, style=out["id"], styleKind=kind, name=out["name"], block=out["source"]["block"], keepText=keep, blueprint=bool(out.get("blueprint")), losses=len(out["losses"]))
    _kick(out["id"])
    return JSONResponse(_full(out), status_code=201)


# ---- 파일에서 -------------------------------------------------------------------------------------------------------

def _extract():
    se = _mod("style_extract")
    if se is None:
        raise HTTPException(501, "서식 추출 모듈(app.style_extract)이 없습니다")
    return se


@router.post("/api/styles/extract-file")
def style_extract_file(file: UploadFile = File(...)):
    """multipart `file`(hwp·hwpx·docx·pdf) → {token, name, format, tables, texts, losses} — 작업을 만들지 않는다. 연 것은 서버 메모리에 토큰으로 잡아 둔다(30분)."""
    _on()
    se, name, data = _extract(), file.filename or "", file.file.read()
    if len(data) > UPLOAD_MB * 2 ** 20:
        raise HTTPException(413, f"{UPLOAD_MB} MB 보다 큰 파일은 받지 않습니다")
    if name.lower().endswith(".hwp"):  # hwp(바이너리)는 한글로 hwpx 로 바꿔 넘긴다(문서 올리기와 같은 길 — 한글이 없으면 400)
        from app import server
        name, data = server._from_hwp(name, data)
    try:
        entry = se.from_file(name, data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    pub = {k: v for k, v in entry.items() if not k.startswith("_")}  # 안쪽 값(문서 객체·명세)은 서버에만
    return {**pub, "token": se.hold(entry), "name": pub.get("name") or name, "format": pub.get("format"), "tables": pub.get("tables") or [],
            "texts": pub.get("texts") or [], "losses": pub.get("losses") or []}


@router.post("/api/styles/from-file")
def style_from_file(body: dict = Body(...)):
    """{token, picks: [{kind, key, name?, bands?}]} → {styles: [meta…]} — 잡아 둔 파일의 후보를 보관함에 저장(+ 검증). 토큰이 만료됐으면 410.
    클라이언트는 토큰과 후보 key 만 보낸다(파일 경로·명세를 받지 않는다)."""
    _on()
    se, picks = _extract(), body.get("picks")
    if not isinstance(picks, list) or not picks or len(picks) > PICKS_MAX or not all(isinstance(p, dict) for p in picks):
        raise HTTPException(400, f"picks 는 [{{kind, key, name?, bands?}}] 1~{PICKS_MAX}개")
    entry = se.held(body.get("token"))
    if entry is None:
        raise HTTPException(410, "올린 파일을 서버가 잊었습니다(30분이 지남) — 다시 올리세요")
    made = []
    for pick in picks:
        try:
            data, meta = se.build_pick(entry, pick)
        except (KeyError, ValueError) as e:
            raise HTTPException(400, f"후보 {pick.get('key')!r} 를 저장하지 못했습니다: {e.args[0] if e.args else e}") from e
        if isinstance(pick.get("name"), str) and pick["name"].strip():
            meta = {**meta, "name": pick["name"]}
        made.append(_store(lambda: style_lib.create(meta, data)))
        _kick(made[-1]["id"])
    return {"styles": [_full(m) for m in made]}


# ---- 문서에 적용 ----------------------------------------------------------------------------------------------------

def _guard(fn):
    """run() 안의 적용 한 걸음 — ValueError 는 그대로, 그 밖의 예외는 ValueError 로 바꿔 던진다(`_transact` 는 KeyError·ValueError 만 되돌린다 —
    다른 예외가 새면 고치다 만 문서가 남는다)."""
    try:
        return fn()
    except ValueError:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("서식 적용 실패")
        raise ValueError(e.args[0] if isinstance(e, KeyError) and e.args and isinstance(e.args[0], str) else f"서식을 적용하지 못했습니다({type(e).__name__}: {e})") from e


def _pick(fn):
    """make() 안의 서식 고르기 — 없는 서식 404 · 종류가 다름·손상 400."""
    try:
        return fn()
    except KeyError as e:
        raise HTTPException(404, e.args[0] if e.args and isinstance(e.args[0], str) else "그 서식이 없습니다") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _slim(sid, body, norm):
    """기록에 남길 요청 요약 — 격자 본문은 빼고 크기만."""
    out = {"style": sid, **{k: body.get(k) for k in ("mode", "after", "replace", "table", "bands", "item", "keepNumbering") if body.get(k) is not None}}
    if isinstance(body.get("paras"), list):
        out["paras"] = len(body["paras"])
    if norm is not None:
        out["grid"] = {"rows": norm["nRows"], "cols": norm["nCols"], "headerRows": norm["headerRows"], "headerCols": norm["headerCols"], "footRows": norm["footRows"]}
    return out


def _replace_range(server, s, replace, before):
    """tableMake 의 replace → 지울 블록 범위 (first, last) | None. 지워질 기존 블록을 before 에 더한다. `tables_api.table_make_insert` 와 같은 규칙."""
    from app import tables_api
    if not replace:
        return None
    if not isinstance(replace, dict):
        raise HTTPException(400, "replace 는 {first, last} 또는 {table}")
    if replace.get("table") is not None:
        tables_api._live_table(s, replace["table"], "바꿀 표")
        before.append(s.doc._ids[replace["table"]])
        return replace["table"], replace["table"]
    first, last = replace.get("first"), replace.get("last")
    for i in (first, last):
        server._para_el(s, i)
    try:
        hosts = s.doc._host_range(first, last)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if any(s.doc._has_object(h) for h in hosts):
        raise HTTPException(400, "고른 범위에 표·그림이 들어 있어 표로 바꿀 수 없습니다 — 「뒤에 넣기」 를 쓰세요")
    before += hosts
    return first, last


@router.post("/api/docs/{doc_id}/styles/{sid}/apply")
def style_apply_doc(doc_id: str, sid: str, body: dict = Body(...)):
    """서식을 문서에 적용 — 구조 편집 한 번(실행 취소 1개 · 기록 `styleApply`). sid = 보관함 템플릿 id | `builtin`(기본 표) | `doc:<표 id>`(이 문서의 표). hwpx 만.
    그 TASK 의 **원본 문서**(이관의 사업계획서 · 취합의 기관 문서 — `doc_agent.policy`)는 403 「원본 문서는 바꾸지 않습니다」. 운반 문서의 정의 참조가 끊어져 있으면 400(아무것도 안 가져온다).
    {mode: "tableMake", grid, after, replace?: {first, last} | {table}} | {mode: "tableBlank", after} | {mode: "tableRestyle", table, bands?} |
    {mode: "format", item: 항목 key, paras: [ids], keepNumbering?} → 구조 편집 응답 + made {table, rows, cols} | formatted {paras: n}. after 는 본문 최상위 블록만."""
    from app import server, tables_api  # 트랜잭션(_edit)·세션은 server 것 — 부를 때 가져온다(순환 import 피함)
    mode, norm, extra = body.get("mode"), None, {}
    if mode not in MODES:
        raise HTTPException(400, f"mode 는 {'·'.join(MODES)} 중 하나")
    if mode == "tableMake":
        try:
            norm = table_make.normalize(body.get("grid"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    def make(s):
        _hwpx(s)
        from app import doc_agent  # 쓰기 정책은 에이전트 반영과 같은 것 하나 — 부를 때 가져온다
        pol = doc_agent.policy((works.work(s.id) or {}).get("task"), s.name)  # 세션 잠금 안(_edit 가 make 를 잠금 안에서 부른다) — TASK 를 바꾸는 요청과 엇갈리지 않게
        if not pol["apply"]:
            raise HTTPException(403, pol["why"])
        if sid != "builtin" and not sid.startswith("doc:"):
            _on()
        if mode == "format":
            ts, key, ids = _pick(lambda: style_apply.text_style(sid)), body.get("item"), body.get("paras")
            if not any(it.get("key") == key for it in ts["items"]):
                raise HTTPException(400, "그 글 서식 항목이 없습니다")
            if not isinstance(ids, list) or not ids or len(ids) > PARAS_MAX or not all(isinstance(i, str) for i in ids):
                raise HTTPException(400, f"paras 는 문단 id 1~{PARAS_MAX}개")
            ps, keep = [server._para_el(s, i) for i in ids], body.get("keepNumbering", True) is not False

            def run():
                changed = _guard(lambda: style_apply.format_paras(s.doc, ts, key, ids, keep_numbering=keep, session=s))
                extra["formatted"] = {"paras": len(changed)}
                return {"hosts": ps, "anchor": ids[0], "focus": None, "formatted": set(changed), "log": {"style": sid, "mode": mode, "item": key, "formatted": len(changed)}}
            return ps, run
        style = _pick(lambda: style_apply.style_of(s.doc, sid))
        if mode == "tableRestyle":
            tid = body.get("table")
            block = tables_api._live_table(s, tid, "서식을 입힐 표")
            el = s.doc._ids[tid]

            def run():
                r = _guard(lambda: style_apply.table_restyle(s.doc, style, tid, body.get("bands"), session=s))
                extra["made"] = {"table": tid, "rows": block["nRows"], "cols": block["nCols"], "formatted": len(r["formatted"])}
                return {"hosts": [el], "anchor": tid, "focus": None, "formatted": set(r["formatted"]),
                        "log": {"style": sid, "mode": mode, "table": tid, "cells": r["cells"], "formatted": len(r["formatted"])}}
            return [el], run
        after = body.get("after")
        ref = s.doc._ids.get(after) if isinstance(after, str) else None
        if ref is None or not s.doc._attached(ref):
            raise HTTPException(404, "넣을 자리의 블록이 지금 문서에 없습니다 — 자리를 다시 고르세요")
        _pick(lambda: style_apply.top_level(s.doc, after))
        before = [ref]
        rng = _replace_range(server, s, body.get("replace"), before) if mode == "tableMake" else None

        def run():
            r = _guard(lambda: style_apply.table_new(s.doc, style, norm, after, session=s) if mode == "tableMake" else style_apply.table_blank(s.doc, style, after, session=s))
            if rng:
                _guard(lambda: s.doc.delete_blocks(*rng))
            extra["made"] = {"table": r["table"], "rows": r["rows"], "cols": r["cols"]}
            return {"hosts": [s.doc._ids[r["host"]]] + [e for e in before if s.doc._attached(e)], "anchor": after, "focus": None,
                    "log": {"style": sid, "mode": mode, "table": r["table"], "rows": r["rows"], "cols": r["cols"], "replaced": bool(rng)}}
        return before, run
    out = server._edit(doc_id, make, "styleApply", _slim(sid, body, norm))
    if isinstance(out, dict):
        out.update(extra)
    return out
