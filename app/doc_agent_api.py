"""에이전트 열 API(spec_일반편집 ② §8·§9·§10) — 한 턴(`POST …/agent/turn`: 문서는 안 바뀐다) · 제안 반영(`POST …/agent/apply`: 서버에 저장한 제안을 실행 — `server._edit` 한 번) ·
보기(`GET …/agent` · `GET …/agent/turns/{turn}`) · 비우기(`DELETE …/agent`) · 자료(`POST …/agent/material` · `DELETE …/agent/material/{mid}`).

형식 중립부(계약 · 제안 검사 · 엑셀 검증 · 정책 · 자료 · 저장소)는 `app/doc_agent.py`, 문서에 쓰는 함수는 `app/style_apply.py`(서식 보관함 모듈 — 없으면 서식 없는 길만: 글은 넣을 자리 문단 모양으로,
새 표·표 서식은 「이 문서의 표」 `doc:<표 id>` 만), 표 채우기는 기존 길 그대로(`table_fill.analyze → payload → ask → apply` — `tables_api.table_fill_propose` 와 같은 입력, 자료만 이 턴의 자료 글).
트랜잭션(`server._edit` — 잠금·스냅샷·OWPML 검사·실행 취소 1개·기록)은 본문·표 편집과 공유한다.

2026-11-13 astra 검토(artifacts/general_edit_astra_2026-11-13/review_answer.md 2·3·4·5·6·15)로 조인 것:
- 턴: 실행할 수 있는 대상을 **보낸 id**(`doc_agent.allowed_ids`)와 사람이 고른 것(표·칸 범위·서식)에 묶는다 · 표 밖 범위는 표 전체로 바꿔 읽지 않고 버린다 ·
  기준 차례는 호출 **전**의 것(`rev0`) — 도는 동안 문서가 바뀌었으면 그 턴의 제안은 모두 `stale` · 턴 id 는 무작위 꼬리 · 도는 동안 「비우기」 를 했으면 저장하지 않는다.
- 반영: 같은 requestId 는 **영수증 + 지금 문서 상태**만(옛 구조 패치 없음 — `replayed`) · 보관함 서식의 revision 이 달라졌으면 409 · 성공하면 제안 상태를 쓰고(한 번 더 해 본다)
  **같은 요청 안에서** 문서 상태를 작업 폴더에 쓴다 · 제안 상태를 못 썼어도 이 프로세스는 그 제안을 다시 반영하지 않는다(`_APPLIED`).

2026-11-14 서식 복사(spec_서식복사 ② §6 — 행동 `styleCopy`): 턴의 프롬프트 자료에 개요 템플릿(`doc_agent.templates_of` — 2단계 그래프)을 싣고, 그 제안의 반영은 문서를 바꾸지 않는 길(`_copy_apply` —
`style_api.save_doc_style` 을 pick 마다: `server._edit` 없음 · 쓰기 정책 없음 · 일부 실패는 `failed` 로)."""
import logging
import time

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import doc_agent, heading_forms, heading_runs, job_prompts, llm, material_index, merge_guides, table_agent, table_make, work_guide, works
from app.hwpx_doc import TBL, P

router = APIRouter()
log = logging.getLogger(__name__)
TURNS_SHOWN = 20      # GET …/agent 가 싣는 최근 턴 수
REQUEST_ID_MAX = 80
NO_LLM = "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐)"
NOT_SAVED = "반영했지만 제안 상태를 저장하지 못했습니다 — 같은 제안을 다시 반영하지 마세요"   # 반영 응답 applied.note(문서는 바뀌었고 제안 기록 쓰기가 두 번 다 실패)
APPLIED_KEEP = 500    # 작업마다 붙들어 두는 「이 프로세스에서 반영한 (턴, 제안)」 수
_APPLIED = {}         # 작업 id → {(턴 id, 제안 id): True}(넣은 차례) — 제안 상태를 디스크에 못 썼어도 같은 제안을 다시 반영하지 않게(저장소 잠금 안에서만 만진다 · 서버를 다시 켜면 사라진다)


def _applied_here(wid, turn, proposal, mark=False):
    """이 프로세스에서 그 제안을 반영했는가 — mark 면 반영했다고 적는다(작업마다 최근 APPLIED_KEEP 개)."""
    seen = _APPLIED.setdefault(wid, {})
    if mark:
        seen[(turn, proposal)] = True
        for k in list(seen)[:-APPLIED_KEEP]:
            del seen[k]
    return (turn, proposal) in seen


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    return server._sess(doc_id)


def _style_apply():
    """`app.style_apply`(서식 보관함의 적용 모듈) | None(아직 없음 · 가져오기 실패) — 없으면 서식 없는 길만 쓴다."""
    try:
        from app import style_apply
        return style_apply
    except Exception:  # noqa: BLE001 — 모듈 없음·가져오다 오류: 에이전트 열은 서식 보관함 없이도 돈다
        return None


def _listing():
    """서식 보관함의 템플릿 meta 들 — 모듈이 없거나 보관함이 꺼져 있거나 못 읽으면 []."""
    try:
        from app import style_lib
        return [m for m in (style_lib.listing() or {}).get("styles") or [] if isinstance(m, dict)] if style_lib.enabled() else []
    except Exception:  # noqa: BLE001
        return []


def _styles_view(metas):
    """화면의 서식 고르기용 요약 {table: [{id, name, revision, bands, rows, cols, blueprint, fidelity}], text: [{id, name, revision, items[{key, name, level, sample}], fidelity}]}."""
    out = {"table": [], "text": []}
    for m in metas:
        if m.get("kind") == "table":
            out["table"].append({"id": m.get("id"), "name": m.get("name"), "revision": m.get("revision"), "bands": m.get("bands"), "rows": m.get("rows"), "cols": m.get("cols"),
                                 "blueprint": bool(m.get("blueprint")), "fidelity": m.get("fidelity")})
        elif m.get("kind") == "text":
            out["text"].append({"id": m.get("id"), "name": m.get("name"), "revision": m.get("revision"), "fidelity": m.get("fidelity"),
                                "items": [{k: it.get(k) for k in ("key", "name", "level", "sample")} for it in m.get("items") or [] if isinstance(it, dict)]})
    return out


def _policy(s):
    return doc_agent.policy((works.work(s.id) or {}).get("task"), s.name)


def _view(rec, full=False):
    """턴 기록 → 화면 꼴 — 진행 턴(`kind: "guide"` — 작업 진행 에이전트)은 `work_guide.view`, 편집 턴은 `doc_agent.turn_view`."""
    return work_guide.view(rec, full) if rec.get("kind") == "guide" else doc_agent.turn_view(rec, full)


def _limits():
    return {"text": doc_agent.TEXT_MAX, "materials": doc_agent.MATERIALS_MAX, "materialMb": doc_agent.MATERIAL_BYTES // 2 ** 20, "materialChars": doc_agent.MATERIAL_CHARS,
            "sent": doc_agent.MATERIALS_SENT, "ext": list(doc_agent.MATERIAL_EXT), "actions": doc_agent.ACTIONS_MAX, "candidates": doc_agent.CANDIDATES_MAX}


@router.get("/api/docs/{doc_id}/agent")
def agent_state(doc_id: str):
    """에이전트 보기의 상태 — {enabled(LLM 쓸 수 있는가), hwpx(이 문서에 쓸 수 있는가 — docx 는 false), policy{apply, why}(반영 금지 문서면 apply false), rev,
    turns[턴 보기 — 최근 20개 · 옛 것부터: `doc_agent.turn_view`], materials[{id, name, kind, chars, sha256, cut, lossy, note, head, at}], styles{table[], text[]}(보관함 요약 — 없으면 빈 목록), limits}."""
    s = _sess(doc_id)
    store = doc_agent.Store(s.id)
    turns = [_view(t) for t in (store.turn(row["id"]) for row in store.turns()[-TURNS_SHOWN:]) if t]   # 진행 턴(kind guide — spec_작업에이전트)이 차례대로 섞여 있다
    return {"enabled": bool(llm.status()["available"]), "hwpx": s.fmt == "hwpx", "policy": _policy(s), "rev": s.rev, "turns": turns,
            "materials": [doc_agent.material_view(m) for m in store.materials()], "styles": _styles_view(_listing()), "limits": _limits()}


@router.get("/api/docs/{doc_id}/agent/turns/{turn}")
def agent_turn_get(doc_id: str, turn: str):
    """턴 하나 — 턴 보기 + 「지침」 보기용 parts[{key, title, text}](보낸 글 — contract · job? · guide? · request · data · 표 채우기 호출마다 fill:<표 id>) · response(LLM 의 답 그대로) ·
    calls[{what, backend, model, effort, ms, costUsd, error}](호출마다 — 이 보기에서는 수가 아니라 목록) · prompt{contract(코드 고정 계약), job(할 일 프롬프트 절 | ""), guide(판단 지침 절 | ""), data(자료 JSON)} ·
    answers{turn(조정 호출의 답 그대로), fills[{table, range, prompt, response, call, counts}](표 채우기 호출)}. 404: 그런 턴 없음."""
    rec = doc_agent.Store(_sess(doc_id).id).turn(turn)
    if rec is None:
        raise HTTPException(404, "그런 턴이 없습니다")
    return _view(rec, full=True)


@router.delete("/api/docs/{doc_id}/agent")
def agent_clear(doc_id: str):
    """대화·제안·자료를 모두 지운다(「비우기」) — 문서는 안 바뀐다. 작업 기록과 턴마다의 호출 상세는 남는다."""
    s = _sess(doc_id)
    doc_agent.Store(s.id).clear()
    works.log(s.id, "agentClear", rev=s.rev)
    return {"ok": True}


# ---- 자료(spec ② §10) ------------------------------------------------------------------------------------------------

@router.post("/api/docs/{doc_id}/agent/material")
async def agent_material(doc_id: str, request: Request):
    """자료 올리기 — 붙여 넣은 글(JSON `{name?, text}`) 또는 파일(multipart `file` — txt·md·csv·tsv·xlsx·docx·hwpx·pdf, 20 MB 까지) → {id, name, kind, chars, sha256, cut, lossy, note, head(앞 300자), at}.
    글로 바꿔 작업 폴더에 둔다(자료 하나 200,000자까지 — 넘으면 cut). lossy = 글로 바꾸며 그대로 옮기지 못한 것이 있음(xlsx: 그대로 그릴 수 없는 표시 형식 · 계산값 없는 수식 칸 — note 에 까닭).
    같은 바이트의 자료가 이미 있으면 그것을 돌려준다(reused true).
    400: 빈 글 · 모르는 형식 · 못 읽는 파일 · 자료 30개 초과 · 413: 20 MB 초과."""
    s = await run_in_threadpool(_sess, doc_id)   # 메모리에 없는 작업은 작업 폴더에서 다시 연다(수백 ms~) — 이벤트 루프 밖에서
    ctype = (request.headers.get("content-type") or "").lower()
    size = request.headers.get("content-length") or ""
    if size.isdigit() and int(size) > doc_agent.MATERIAL_BYTES + 2 ** 20:
        raise HTTPException(413, f"자료는 {doc_agent.MATERIAL_BYTES // 2 ** 20} MB 까지입니다")
    if ctype.startswith("multipart/"):
        form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "read"):
            raise HTTPException(400, "file 이 필요합니다")
        name, data = f.filename or "자료", await f.read()
        make = lambda: doc_agent.material_from_file(name, data)  # noqa: E731
    else:
        try:
            body = await request.json()
        except Exception as e:  # noqa: BLE001 — 깨진 JSON
            raise HTTPException(400, "자료는 JSON {name?, text} 또는 multipart file 로 보냅니다") from e
        if not isinstance(body, dict) or not isinstance(body.get("text"), str) or (body.get("name") is not None and not isinstance(body["name"], str)):
            raise HTTPException(400, "자료는 JSON {name?, text} 또는 multipart file 로 보냅니다")
        make = lambda: doc_agent.material_from_text(body.get("name"), body["text"])  # noqa: E731
    try:
        rec = await run_in_threadpool(make)   # 문서·PDF 를 글로 바꾸는 데 수 초 걸릴 수 있다 — 이벤트 루프 밖에서
    except doc_agent.TooBig as e:
        raise HTTPException(413, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    store = doc_agent.Store(s.id)
    with store.lock:
        have = store.materials()
        same = next((m for m in have if m.get("sha256") == rec["sha256"] and m.get("name") == rec["name"]), None)
        if same is not None:
            return {**doc_agent.material_view(same), "reused": True}
        if len(have) >= doc_agent.MATERIALS_MAX:
            raise HTTPException(400, f"자료는 {doc_agent.MATERIALS_MAX}개까지 둘 수 있습니다 — 안 쓰는 자료를 지우세요")
        store.add_material(rec)
    works.log(s.id, "agentMaterial", material=rec["id"], name=rec["name"], format=rec["kind"], chars=rec["chars"], cut=rec["cut"])
    return doc_agent.material_view(rec)


@router.delete("/api/docs/{doc_id}/agent/material/{mid}")
def agent_material_delete(doc_id: str, mid: str):
    """자료 지우기 → {ok, materials[남은 자료]}. 404: 그런 자료 없음."""
    s = _sess(doc_id)
    store = doc_agent.Store(s.id)
    if not store.drop_material(mid):
        raise HTTPException(404, "그런 자료가 없습니다")
    works.log(s.id, "agentMaterial", material=mid, removed=True)
    return {"ok": True, "materials": [doc_agent.material_view(m) for m in store.materials()]}


# ---- 한 턴(spec ② §8) -------------------------------------------------------------------------------------------------

def _turn_input(s, body, store, metas):
    """요청 본문 검사 → (글, 자료 기록들, selection, 고른 서식 {table, text}, effort). 틀리면 400."""
    text = body.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > doc_agent.TEXT_MAX:
        raise HTTPException(400, f"요청 글(text)은 1~{doc_agent.TEXT_MAX:,}자")
    ids = body.get("materials") or []
    if not isinstance(ids, list) or len(ids) > doc_agent.MATERIALS_MAX or not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        raise HTTPException(400, "materials 는 자료 id 목록(겹침 없이)")
    mats = [store.material(i) for i in ids]
    if any(m is None for m in mats):
        raise HTTPException(400, "없는 자료가 들어 있습니다 — 자료 목록을 다시 읽어 주세요")
    sel = body.get("selection") or {}
    if not isinstance(sel, dict) or not isinstance(sel.get("paras") or [], list) or len(sel.get("paras") or []) > 5 * doc_agent.SELECTION_MAX:
        raise HTTPException(400, "selection 은 {paras: [문단 id…], table, range, cursor}")
    rng = sel.get("range")
    if rng is not None:
        try:
            rng = {k: int(rng[k]) for k in ("r0", "c0", "r1", "c1")}
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(400, "selection.range 는 {r0, c0, r1, c1} 정수") from e
        if rng["r0"] < 0 or rng["c0"] < 0 or rng["r1"] < rng["r0"] or rng["c1"] < rng["c0"]:
            raise HTTPException(400, "selection.range 가 거꾸로이거나 음수입니다")
    sel = {"paras": [p for p in sel.get("paras") or [] if isinstance(p, str)], "table": sel.get("table") if isinstance(sel.get("table"), str) else None, "range": rng,
           "cursor": sel.get("cursor") if isinstance(sel.get("cursor"), str) else None}
    st = body.get("styles") or {}
    if not isinstance(st, dict) or any(st.get(k) is not None and not isinstance(st.get(k), str) for k in ("table", "text")):
        raise HTTPException(400, "styles 는 {table: 서식 id | \"builtin\" | \"doc:<표 id>\" | null, text: 서식 id | null}")
    idx = doc_agent.styles_index(metas)
    picked = {"table": st.get("table") or None, "text": st.get("text") or None}
    if picked["table"] and picked["table"] != "builtin" and not picked["table"].startswith("doc:") and picked["table"] not in idx["table"]:
        raise HTTPException(400, "고른 표 서식이 보관함에 없습니다 — 서식을 다시 고르세요")
    if picked["text"] and picked["text"] not in idx["text"]:
        raise HTTPException(400, "고른 글 서식이 보관함에 없습니다 — 서식을 다시 고르세요")
    effort = body.get("effort")
    if effort is not None and effort not in llm.EFFORTS:
        raise HTTPException(400, f"effort 는 {'·'.join(llm.EFFORTS)} 중 하나")
    return text.strip(), mats, sel, picked, effort


def _fill_gather(s, tid, rng, tb, allowed=None):
    """표 채우기의 잠금 안 부분 — `tables_api.table_fill_propose` 와 같은 것을 모은다(이 문서의 글은 안 싣는다). → {table, an, notes, ctx, common, own, heads, place, rev, hash} | {table, error}.
    allowed = 이 턴의 프롬프트에 보낸 id(`doc_agent.allowed_ids`) — 그 밖의 표는 문서에 있어도 채우지 않는다(표 채우기 호출도 안 한다).
    rng = 행동이 적은 범위({r0, c0, r1, c1} | None = 표 전체): **표 밖으로 나가면 틀린 범위**다 — `table_fill.analyze` 가 그런 범위를 표 전체로 바꿔 읽으므로(검토 2) 여기서 먼저 거른다."""
    from app import table_excel, table_fill, tables_api
    el = s.doc._ids.get(tid) if isinstance(tid, str) else None
    if el is None or el.tag != TBL or not s.doc._attached(el):
        return {"table": tid, "error": f"채울 표가 문서에 없습니다: {tid}"}
    if allowed is not None and tid not in allowed:
        return {"table": tid, "error": f"{doc_agent.NOT_SENT}입니다(table: {tid}) — outline·tables·selection 으로 보낸 id 만 대상이 됩니다"}
    block = s.doc.table_block(tid)
    if not doc_agent.range_in(rng, block["nRows"], block["nCols"]):
        return {"table": tid, "error": f"채울 범위(range)가 표 밖입니다: 「{doc_agent.range_a1(rng)}」 — 표 {tid} 는 {block['nRows']}×{block['nCols']}"
                                       f"(A1:{doc_agent.F.a1(block['nRows'] - 1, block['nCols'] - 1)}). 표 전체로 바꿔 채우지 않습니다"}
    heads = tables_api._heads(s, tid)
    try:
        an = table_fill.analyze(s.doc, tid, rng, overwrite=False, doc_key=getattr(s, "doc_key", None), roles=heads, block=block)
    except ValueError as e:
        return {"table": tid, "error": str(e)}
    if an is None:
        return {"table": tid, "error": f"채울 표가 문서에 없습니다: {tid}"}
    if not an["targets"]:
        return {"table": tid, "error": an.get("note") or "그 표에 채울 칸이 없습니다 — 빈 필드가 없거나 고른 범위에 없습니다"}
    if len(an["cells"]) > table_fill.MAX_CELLS:
        return {"table": tid, "error": f"표가 너무 커서 채우기 제안을 받을 수 없습니다(칸 {len(an['cells']):,}개 — 한도 {table_fill.MAX_CELLS:,}개)"}
    if len(an["targets"]) > table_fill.TARGETS_MAX:
        return {"table": tid, "error": f"한 번에 채울 칸이 너무 많습니다({len(an['targets']):,}개 — 한도 {table_fill.TARGETS_MAX}개) — 표 칸을 끌어 범위를 고른 뒤 다시 요청하세요"}
    return {"table": tid, "an": an, "notes": tables_api.table_notes(s, tid, tb), "ctx": table_excel.context(s.doc, tid), "common": table_agent.get(s.id, table_agent.COMMON),
            "own": table_agent.get(s.id, tid), "heads": heads, "place": table_fill.place_of(tb), "rev": s.rev, "hash": doc_agent.target_hash(s.doc, tid)}


def _fill_ask(g, material, form_guide, job, effort, how=""):
    """표 채우기의 잠금 밖 부분 — 기존 호출 그대로(`table_fill.payload → ask → apply`). g 에 out(답 검사 결과 | None)·answer·기록할 것(prompt·response·call)을 더한다.
    how = 양식 작성의 자리 턴이 보낸 요청 글(작성 지침 · 작성 계획 · 예시) — 자료(material)가 아니라 「지침」 절로 싣는다: 값의 근거 검사에 안 든다(고정 글의 근거 where "rule" 로만 찾는다)."""
    from app import table_fill
    data = table_fill.payload(g["an"], g["ctx"], material, "", g["place"])
    notes_txt, guide_txt, rules_txt = (table_fill.notes_text(g["notes"]), table_fill.guide_text(g["common"]["instructions"], g["own"]["instructions"], form=form_guide, request=how or None),
                                       table_agent.rules_text(g["common"], g["own"]))
    res = table_fill.ask(data, notes_txt, guide_txt, rules_txt, job_prompts.part(job, table_fill.JOB_NOTE), effort=effort)
    got = res["data"]
    out = table_fill.apply(got, g["an"], table_fill.haystack(data), table_fill.rules_haystack(notes_txt, guide_txt, rules_txt)) if got is not None else None
    g.update(out=out, answer=str((got or {}).get("note") or "")[:600], prompt=res["prompt"], response=got, call=res["call"])
    if out is None:
        g["error"] = f"LLM 이 그 표에 채울 값을 제안하지 못했습니다: {res['call'].get('error') or '응답 없음'}"
    return g


@router.post("/api/docs/{doc_id}/agent/turn")
def agent_turn(doc_id: str, body: dict = Body(...)):
    """에이전트 한 턴 — {text(1~4,000자), materials?: [자료 id…], selection?: {paras: [ids], table: id|null, range: {r0,c0,r1,c1}|null, cursor: 블록 id|null},
    styles?: {table: 서식 id|"builtin"|"doc:<표 id>"|null, text: 서식 id|null}, effort?} → {turn: 턴 보기}(`doc_agent.turn_view`: {id, at, rev, text, reply, notes[], proposals[], dropped[], call, calls, …}).
    (몸통은 `_turn` — 이 끝점은 범위 없이 부른다.)
    문서를 바꾸지 않는다. 조정 호출 1번 + 표 채우기 행동마다 기능 호출 1번(한 턴에 2개까지) — 자료는 세션 잠금 안에서 모으고 호출은 잠금 밖(동기 — 수 초~수십 초).
    제안은 서버에 저장한다(반영은 `…/agent/apply` 가 저장한 것을 실행). 400: 입력 틀림 · docx · 503: LLM 없음 · 502: 조정 호출이 답하지 못함(본문에 turn — 오류가 적힌 턴 보기: 화면이 그대로 보인다).
    기준은 **호출 전** 문서(rev · 보낸 id · 사람이 고른 것): 행동의 대상은 보낸 id 뿐이고(그 밖은 dropped 「보낸 목록에 없는 대상」), 사람이 고른 표·칸 범위·서식과 다르면 경고(처음부터 안 고름),
    도는 동안 문서가 바뀌었으면 제안이 모두 `state: "stale"` + notes 「요청을 처리하는 동안 문서가 바뀌었습니다 — 다시 요청하세요」, 도는 동안 「비우기」 를 했으면 저장하지 않고
    notes 「대화를 비운 뒤에 온 답입니다」(제안은 stale — 반영할 수 없다). 턴 id = 「t<밀리초><16진 6자>」."""
    return _turn(doc_id, body)


OFF_TYPE = "이 자리에서는 하지 않는 행동입니다"
OFF_TABLE = "이 자리에서는 채우지 않는 표입니다"
OFF_AFTER = "이 자리에서는 그 자리 뒤에 쓰지 않습니다"
MOVED = "그 자리의 윗 제목 · 머리가 바뀜"


def _levels(s):
    """헤딩 그래프가 매긴 줄의 레벨 {문단 id: 레벨}(상자 안 줄도) — 상자의 쓸 자리가 「어느 제목 아래」 인지. 작업 파일을 읽으므로 세션 잠금 밖에서."""
    return {n["para"]: n["level"] for n in (heading_runs.graph(s) or {}).get("nodes") or () if isinstance(n, dict) and n.get("para") and n.get("level")}


def _uploaded(s):
    """그 작업에 올린 원본의 문단 원문 {문단 id: 글} | None(`guide_write_api.uploaded_texts` — 그 모듈이 이 모듈을 가져오므로 함수 안에서). 세션 잠금 밖에서."""
    from app import guide_write_api
    return guide_write_api.uploaded_texts(s)


def _turn(doc_id, body, scope=None):
    """한 턴의 몸통(끝점 `agent_turn` 과 같은 답) + **서버만 주는 범위**(scope — 요청 본문으로는 못 준다: 「지침 작성」 이 자리마다의 턴을 이 함수로 돌린다 — spec_양식작성 ② §5-3).
    scope = {"types": 이 턴에 받는 행동 종류 모음(그 밖의 행동은 버림 「이 자리에서는 하지 않는 행동입니다」), "paras": 자리 채우기(fill)를 받는 문단 id 모음 | None(= 셈한 대상 모두 — 같은 이름의 자리가 여럿인 덩이는 빼고),
    "tables": 표 채우기를 받는 표 id 모음 | None(= 안 좁힘), "after": 글 쓰기 · 새 표를 받는 자리(after) id 모음 | None(= 안 좁힘 — 그 밖의 자리는 `OFF_AFTER`), "decided": [사람이 정한 답 글…](fill · 표 채우기의 값 근거 — 범위가 있는 턴의 표 채우기는 요청 글을 근거로 세지 않는다: `doc_agent.fill_basis`),
    "uploaded": {문단 id: 올린 원본의 원문} | None(글이 있는 쓸 자리가 올린 그대로인지 · 이미 채운 줄)}. 범위가 없는 턴은 올린 원본을 작업 폴더에서 읽는다(`_uploaded`).
    막는 것은 모두 **하위 호출 전**이다 — 범위 밖의 표는 표 채우기 호출(유료)을 하지 않는다. 범위가 없어도 상자를 고른 턴은 그 상자 안의 표를 채우지 않는다(그림 · 샘플 자리 — astra 2차 G9)."""
    body = body if isinstance(body, dict) else {}
    scope = scope if isinstance(scope, dict) else None
    types = set(scope["types"]) if scope and scope.get("types") is not None else None
    only_paras = set(scope["paras"]) if scope and scope.get("paras") is not None else None
    only_tables = set(scope["tables"]) if scope and scope.get("tables") is not None else None
    only_after = set(scope["after"]) if scope and scope.get("after") is not None else None   # 글 쓰기 · 새 표를 받는 자리(after) — 그 밖의 자리 뒤에는 쓰지 않는다(헤딩 턴이 다른 헤딩 아래에 쓰지 않게: astra 3차)
    s = _sess(doc_id)
    # 올린 원본 — 범위가 줬으면 그것, 범위가 없는 턴(에이전트 보기에서 바로)도 작업 폴더에서 읽는다: 이미 채운 줄이 다시 쓸 자리가 되거나 같은 이름의 자리가 하나를 채운 뒤 풀리지 않게(astra 3차)
    uploaded = (scope.get("uploaded") if isinstance(scope.get("uploaded"), dict) else None) if scope else _uploaded(s)
    if s.fmt != "hwpx":
        raise HTTPException(400, "에이전트 쓰기는 지금 hwpx 문서만 됩니다")
    store, metas = doc_agent.Store(s.id), _listing()
    text, mats, sel, picked, effort = _turn_input(s, body, store, metas)
    # 읽는 문서 = 목적 문서(지금 문서)와 그 프로젝트의 참조 문서뿐(2026-11-26 사용자 「에이전트는 목적문서랑 참조하는 문서들만 읽어야지」 — spec_양식작성 ② §5-3 「읽는 문서」):
    # 양식 작성의 문서 · 지침 작성의 자리 턴은 참조 문서 밖의 자료를 받지 않고, 다른 문서에서 뽑은 서식(보관함)을 싣지 않는다
    from app import guide_write_api
    narrow = scope is not None or guide_write_api.refs_of(s.id)["only"]
    bad = guide_write_api.outside(s.id, [m["id"] for m in mats])
    if bad:
        raise HTTPException(409, f"이 프로젝트의 참조 문서가 아닌 문서의 자료입니다({' · '.join(bad[:3])}) — 빼고 고르거나 그 문서를 「이 프로젝트에 넣기」 합니다")
    if not llm.status()["available"]:
        raise HTTPException(503, NO_LLM)
    gen0 = store.gen()   # 대화의 차례 — 이 턴이 도는 동안 「비우기」 를 하면 저장하지 않는다(검토 15)
    job, guide = job_prompts.for_work(s.id), doc_agent.guide()     # 할 일 프롬프트(그 작업의 TASK 에 있으면) · 판단 지침 — 파일을 읽으므로 잠금 밖에서
    here = {"name": s.name, "sha256": getattr(s, "doc_key", None), "project": (((works.work(s.id) or {}).get("task") or {}).get("project") or "").strip() or None}   # 지금 문서 — 서식의 원본 문서와 견준다(spec_서식복사 ② §17)
    form_guide = heading_forms.table_guide(s)
    t3 = heading_runs.tables(s)
    graph = heading_runs.graph(s)
    templates = doc_agent.templates_of(graph)   # 2단계 그래프의 개요 템플릿(서식 복사의 대상 — spec_서식복사 ② §6) — 작업 파일을 읽으므로 세션 잠금 밖에서(t3 와 같다). 그래프가 없으면 빈 목록
    levels = {n["para"]: n["level"] for n in (graph or {}).get("nodes") or () if isinstance(n, dict) and n.get("para") and n.get("level")}   # 헤딩 그래프가 매긴 줄의 레벨(상자 안 줄도) — 상자의 쓸 자리가 「어느 제목 아래」 인지
    with s.lock:
        if picked["table"] and picked["table"].startswith("doc:"):
            el = s.doc._ids.get(picked["table"][4:])
            if el is None or el.tag != TBL or not s.doc._attached(el):
                raise HTTPException(400, "서식으로 고른 표가 지금 문서에 없습니다 — 다시 고르세요")
        blocks = s.doc.blocks()
        got_sel = doc_agent.selection_of(s.doc, sel, levels, uploaded, only=set(scope["paras"]) if scope and scope.get("paras") is not None else None)
        outline, tables, rev0 = doc_agent.outline_of(blocks, got_sel["focus"]), doc_agent.tables_of(blocks, focus_ids=got_sel["focus"]), s.rev   # rev0 = 이 턴의 기준 차례(호출 전 — 잠금 안에서)
    # 실행 권한의 테두리(검토 2): 프롬프트에 실제로 보낸 id · 사람이 고른 것(지금 문서에 있는 것만 — 표를 골랐을 때만 그 칸 범위)
    allowed = doc_agent.allowed_ids(outline, tables, got_sel["data"], templates)
    chosen = {"paras": [p["id"] for p in got_sel["data"]["paras"]], "table": (got_sel["data"]["table"] or {}).get("id"), "range": sel["range"] if got_sel["data"]["table"] else None}
    sent = doc_agent.materials_data(mats)
    # 자리 턴이 근거 절을 받았으면(작성 계획이 고른 것 — scope.evidence) 자료 전체가 아니라 **그 절 + 앞뒤 절 + 목차**만 싣는다(spec_양식작성 ② §5-12 4). 아는 절이 하나도 없으면 전처럼 자료 전체
    evidence = [e for e in (scope or {}).get("evidence") or () if isinstance(e, dict)]
    narrowed = material_index.narrow(mats, evidence, doc_agent.MATERIALS_SENT) if evidence else None
    if narrowed:
        sent = [{"id": m["id"], "name": m["name"], "text": m["text"], "cut": m["cut"]} for m in narrowed]
    basis_mats = narrowed or mats   # 표 채우기 호출에 줄 자료(같은 절만)
    fill_targets = {k: v for k, v in got_sel["fill"].items() if only_paras is None or k in only_paras}   # 자리 채우기의 대상 — 서버가 이 선택에서 셈한 것(범위를 줬으면 그 안으로)
    inner = set(got_sel["inner"])                                                                        # 고른 상자 안의 표 — 이 턴에 채우지 않는다
    # 자리 턴(scope)은 앞선 대화를 싣지 않는다 — 한 실행의 다른 자리 턴(다른 상자의 요청 · 답)이 이 자리의 답에 섞이지 않게(2026-11-26 사용자 「보고있는 문서와 에이전트가 하고 있는 문서가 관련이 없음」)
    history = [] if scope is not None else doc_agent.history_of([t for t in (store.turn(row["id"]) for row in store.turns()[-2 * doc_agent.HISTORY:]) if t])
    data = doc_agent.payload(text, got_sel["data"], outline, tables, doc_agent.styles_data(metas, picked, here, only_here=narrow), sent, history, templates=templates)
    job_part, guide_part = job_prompts.part(job, doc_agent.JOB_NOTE), doc_agent.guide_part(guide)
    # 표 자리의 턴(범위의 행동이 표 채우기 하나 · 표 하나)은 조정 호출 없이 그 표의 표 채우기를 바로 부른다 — 조정 호출은 자료 전체를 읽고 「그 표를 채운다」 한 줄만 답한다(2026-11-27 Carbon · spec_양식작성 ② §5-12 10)
    direct = next(iter(only_tables)) if scope is not None and types == {"tableFill"} and only_tables is not None and len(only_tables) == 1 else None
    if direct is not None:
        res = {"call": {"backend": None, "model": None, "effort": None, "ms": 0, "costUsd": None, "error": None, "skipped": True}, "prompt": "", "contract": "", "response": None,
               "data": {"reply": "", "actions": [{"type": "tableFill", "table": direct, "range": ""}]}}
    else:
        res = doc_agent.ask(data, guide_part, job_part, effort=effort)
    call, got = res["call"], res["data"]
    tid = store.new_turn_id()   # 무작위 꼬리 — 같은 밀리초에 끝난 두 턴도 다른 id
    rec = {"id": tid, "at": round(time.time(), 3), "rev": rev0, "request": {"text": text, "materials": [m["id"] for m in mats], "selection": sel, "styles": picked},
           "narrowed": [material_index.ref(m["id"], sec) for m in narrowed for sec in m["secs"]] if narrowed else [],   # 이 턴에 **실제로 실은** 절(근거 절 + 앞뒤 — 분량을 넘어 못 실은 절은 빠진다 · 비면 자료 전체를 실었다)
           # 지침 작성의 자리 턴 — 어느 자리의 턴인가 · 어느 계획(작성 계획 + 그 자리에 닿는 답)으로 받았나(서버가 준 범위에서만: 덮임이 이것으로 세고, 계획 · 답이 바뀐 뒤의 옛 초안을 가린다 — guide_write_api.coverage)
           **({"place": scope["place"], "planSig": scope.get("planSig")} if scope and isinstance(scope.get("place"), str) else {}),
           "reply": "", "notes": [], "error": None, "proposals": [], "dropped": [], "prompt": {"contract": res.get("contract", doc_agent.CONTRACT), "job": job_part, "guide": guide_part, "data": data},
           "response": res["response"], "call": call, "fills": [], "job": job_prompts.brief(job) if job_part else None, "guide": merge_guides.brief(guide) if guide_part else None}
    fills, fill_recs = {}, []
    if got is not None:
        actions = got["actions"]
        rec["reply"] = got["reply"]
        off = {i: OFF_TYPE for i, a in enumerate(actions) if types is not None and a.get("type") not in types}   # 범위 밖의 행동 — 제안 검사 전에(표 채우기 호출도 안 한다)
        if only_after is not None:
            off.update({i: OFF_AFTER for i, a in enumerate(actions) if i not in off and a.get("type") in ("write", "tableNew") and str(a.get("after") or "").strip() not in only_after})
        want = [i for i, a in enumerate(actions[:doc_agent.ACTIONS_MAX]) if a.get("type") == "tableFill" and i not in off][:doc_agent.FILLS_PER_TURN]
        # 표 채우기의 값 근거: 에이전트 보기에서 바로 온 턴은 자료 + 요청 글(사람이 값을 요청에 바로 적는다 — 전과 같다). **양식 작성의 자리 턴(scope)** 의 요청 글은 작성 지침 · 작성 계획 · 예시를 모은 글이라
        # 근거가 아니다 — 자료 + 사람이 정한 답만 근거로 주고(`fill_basis`), 요청 글은 「지침」 절로만 보낸다(2026-11-27 astra P1-5: 지침에 섞인 샘플 기관명이 자료 없이 근거 검사를 지나갔다)
        material, how = ("", "") if not want else (doc_agent.fill_basis(basis_mats, (scope or {}).get("decided")), text) if scope is not None else (doc_agent.fill_material(text, mats), "")
        for i in want:   # 표마다: 잠금 안에서 모으고 → 잠금 밖에서 기능 호출(기존 표 채우기 길 그대로)
            a = actions[i]
            tid_ = str(a.get("table") or "").strip()
            if tid_ not in only_tables if only_tables is not None else tid_ in inner:
                fills[i] = {"table": a.get("table"), "error": OFF_TABLE}   # 하위 호출 전에 막는다
                continue
            try:
                rng = doc_agent.range_of(a.get("range"))
            except ValueError as e:
                fills[i] = {"table": a.get("table"), "error": str(e)}
                continue
            tb = next((x for x in (t3 or {}).get("tables", []) if x["id"] == a.get("table")), None)
            with s.lock:
                g = _fill_gather(s, str(a.get("table") or "").strip(), rng, tb, allowed)
            if not g.get("error"):
                g = _fill_ask(g, material, form_guide, job, effort, how)
                fill_recs.append({"table": g["table"], "range": g["an"]["range"], "prompt": g["prompt"], "response": g["response"], "call": g["call"], "counts": (g.get("out") or {}).get("counts")})
            fills[i] = g
        if direct is not None and not rec["reply"]:   # 조정 호출이 없는 턴 — 답 글은 표 채우기의 것(없으면 못 한 까닭)
            g0 = fills.get(0) or {}
            rec["reply"] = str(g0.get("answer") or g0.get("error") or "")[:doc_agent.TEXT_MAX]
        with s.lock:   # 제안 검사는 지금 문서와 견주되(없는 id 는 여기서 버려진다) **기준 차례는 호출 전의 rev0** — 호출 뒤 문서로 기준을 다시 찍지 않는다(검토 3)
            changed = s.rev != rev0   # 도는 동안 문서가 바뀌었다 — 낡은 문서를 보고 한 답이다: 이 턴의 제안은 모두 낡은 것으로
            built = doc_agent.proposals(s.doc, actions, {"rev": rev0, "turn": tid, "sources": doc_agent.sources(text, got_sel["text"], sent), "styles": doc_agent.styles_index(metas),
                                                         "picked": picked, "fills": fills, "docKey": getattr(s, "doc_key", None), "allowed": allowed, "selection": chosen, "changed": changed,
                                                         "templates": templates, "off": off, "fill": fill_targets, "box": got_sel["box"], "scope": scope,
                                                         "decided": [d for d in (scope or {}).get("decided") or [] if isinstance(d, str)], "uploaded": uploaded,
                                                         # 자리 채우기의 근거는 자료만(요청 글 · 고른 글 = 양식의 글은 근거가 아니다) — each = 자료마다의 글(근거 구절 · 수는 자료 하나 안에서 견준다)
                                                         "sources_mat": {**doc_agent.sources("", "", sent), "each": [str(m.get("text") or "") for m in sent]},
                                                         # 근거 구절의 자료 자리(줄마다의 at · evid — ② §5-12 3 · 5): 자료 **전체 글**에서 찾는다(보낸 글이 근거 절만일 때도 자리는 자료 글의 글자 자리) ·
                                                         # evidence = 작성 계획이 고른 절(같은 구절이 여러 곳이면 그 절의 것이 먼저) · ctx = 그 자리의 머리 글(차년도 · 단계가 근거의 제목과 다른지 견준다)
                                                         "mats": [{"id": m["id"], "name": m.get("name") or "", "text": str(m.get("text") or "")} for m in mats],
                                                         "evidence": evidence, "ctx": str((scope or {}).get("ctx") or ""),
                                                         # 근거 절만 실은 턴 — 실제로 보낸 구간(그 밖의 절 · 절 머리 줄 · 목차의 구절은 근거가 아니다: doc_agent._evid)
                                                         "spans": {m["id"]: m["spans"] for m in narrowed} if narrowed else None})
        rec.update(proposals=built["proposals"], dropped=built["dropped"], fills=fill_recs,
                   notes=[f"{d['why']}" for d in built["dropped"] if d.get("type") == "tableFill"]   # 채울 칸이 없거나 막힌 표는 그 까닭을 답에(spec ② §8)
                   + ([doc_agent.BUSY_STALE] if changed and built["proposals"] else []))
    else:
        rec["error"] = f"LLM 이 답하지 못했습니다: {call.get('error') or '응답 없음'}"
    kept = store.save_turn(rec, gen=gen0) is not None
    if not kept:   # 도는 동안 「비우기」 — 비운 대화에 뒤늦은 턴을 되살리지 않는다: 저장하지 않고 그 말과 함께 돌려준다(저장한 제안이 없으니 반영도 안 된다 — 404)
        rec["notes"] = [*rec["notes"], doc_agent.CLEARED]
        for p in rec["proposals"]:
            p.update(state="stale", preselect=False)
            if p["type"] in ("tableFill", "fill"):
                p["view"]["picked"] = []
    calls = [call] + [f["call"] for f in fill_recs]
    cost = [c.get("costUsd") for c in calls if isinstance(c.get("costUsd"), (int, float))]
    detail = works.add_detail(s.id, "agent", f"turn_{tid[1:]}", {"turn": tid, "rev": rev0, "request": rec["request"], "prompt": res["prompt"], "response": res["response"], "call": call,
                                                                "fills": fill_recs, "proposals": [doc_agent.card(p) for p in rec["proposals"]], "dropped": rec["dropped"],
                                                                "job": rec["job"], "guide": rec["guide"]})
    lead = next((c for c in calls if not c.get("skipped")), call)   # 조정 호출을 건너뛴 턴(표 자리)은 첫 실제 호출(표 채우기)의 길 · 모델을 적는다
    works.log(s.id, "agentTurn", rev=rev0, turn=tid, proposals=len(rec["proposals"]), dropped=len(rec["dropped"]), materials=len(mats), fills=len(fill_recs),
              backend=lead.get("backend"), model=lead.get("model"), ms=sum(int(c.get("ms") or 0) for c in calls), costUsd=round(sum(cost), 6) if cost else None,
              **({"narrowed": len(rec["narrowed"])} if rec.get("narrowed") else {}), **({"place": rec["place"]} if rec.get("place") else {}),
              error=call.get("error"), detail=detail, **({} if kept else {"cleared": True}))
    if got is None:
        return JSONResponse({"detail": rec["error"], "turn": doc_agent.turn_view(rec)}, status_code=502)
    return {"turn": doc_agent.turn_view(rec)}


# ---- 반영(spec ② §9) --------------------------------------------------------------------------------------------------

def _guard(fn):
    """run() 안에서 문서를 바꾸는 호출 — KeyError·ValueError 말고의 예외는 ValueError 로 바꿔 던진다(`server._transact` 가 그 둘만 되돌리고 400 으로 답한다 —
    다른 예외가 새면 고치다 만 문서가 남는다)."""
    try:
        return fn()
    except (KeyError, ValueError):
        raise
    except HTTPException as e:
        raise ValueError(str(e.detail)) from e
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"반영하지 못했습니다: {type(e).__name__}: {e}"[:300]) from e


def _live_excel(s, tid, roles):
    """반영한 **뒤** 그 표의 엑셀 검증(지금 문서의 표를 그대로 판정 — run() 안에서). 판정 못 하면 unknown."""
    from app import table_excel
    try:
        return doc_agent.excel_summary(table_excel.judge(s.doc, tid, None, None, getattr(s, "doc_key", None), roles))
    except Exception as e:  # noqa: BLE001 — 검증이 편집을 되돌리게 두지 않는다
        return {**doc_agent.excel_summary(None), "note": f"엑셀 검증을 하지 못했습니다: {e}"[:200]}


def _plain_lines(doc, after, lines):
    """서식 보관함 모듈 없이 줄 쓰기 — 넣을 자리 문단 모양(자리가 표·그림이면 문서의 기본 글 문단)으로 새 문단들. 번호·쪽 나눔은 물려받지 않는다."""
    tpl = after if doc._ids[after].tag == P else None
    ids = doc.insert_after(after, [{"kind": "paragraph", "text": ln["text"], "keepNumbering": False, **({"templateId": tpl} if tpl else {})} for ln in lines])
    for i in ids:
        for a in ("pageBreak", "columnBreak"):
            if doc._ids[i].get(a) not in (None, "0"):
                doc._ids[i].set(a, "0")
    return ids


def _anchor(s, block_id):
    ref = doc_agent.top_el(s.doc, block_id)
    if ref is None:
        raise HTTPException(409, doc_agent.STALE)
    return ref


def _same_style(op, style, side):
    """보관함 서식이 제안을 낸 때의 revision(op.styleRev) 그대로인가 — 다르면 409 「서식이 바뀌었습니다 — 다시 요청하세요」, 제안은 낡은 것으로(side.stale).
    style = `style_apply.text_style`·`style_of` 의 결과(meta 가 든다). 기본 표 · 「이 문서의 표」 · revision 을 안 적은 옛 제안(styleRev 없음)은 안 본다 —
    「이 문서의 표」 는 대상 지문(`doc_agent.style_hash`)이 본다. 반영은 미리 본 서식으로만(검토 4)."""
    want = op.get("styleRev")
    if want is not None and ((style or {}).get("meta") or {}).get("revision") != want:
        side["stale"] = True
        raise HTTPException(409, doc_agent.STYLE_STALE)


def _make_write(op, done, side):
    def make(s):
        ref, sa, tstyle = _anchor(s, op["after"]), _style_apply(), None
        if op.get("style"):
            if sa is None:
                raise HTTPException(503, "서식 보관함 모듈이 없어 글 서식을 입힐 수 없습니다")
            try:
                tstyle = sa.text_style(op["style"])
            except (KeyError, ValueError) as e:
                raise HTTPException(409, f"글 서식을 읽지 못했습니다 — 서식을 다시 고르고 요청하세요: {e}") from e
            _same_style(op, tstyle, side)
        lines = [{"text": ln["text"], "item": ln.get("item")} for ln in op["lines"]]

        def run():
            ids = list(_guard(lambda: sa.write_lines(s.doc, op["after"], lines, tstyle, session=s) if sa is not None else _plain_lines(s.doc, op["after"], lines)))
            done.update(written={"paras": ids})
            return {"hosts": [s.doc._ids[i] for i in ids] + [ref], "anchor": op["after"], "focus": None, "log": {"type": "write", "paras": len(ids), "style": op.get("style")}}
        return [ref], run
    return make


def _make_table_new(op, done, side):
    def make(s):
        from app import tables_api
        ref, sa = _anchor(s, op["after"]), _style_apply()
        try:
            norm = table_make.normalize(op["grid"])
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        style = tpl = roles = None
        if sa is not None:
            try:
                style = sa.style_of(s.doc, op["style"])
            except (KeyError, ValueError) as e:
                raise HTTPException(409, f"표 서식을 읽지 못했습니다 — 서식을 다시 고르고 요청하세요: {e}") from e
            _same_style(op, style, side)
        elif str(op["style"]).startswith("doc:"):
            tpl = op["style"][4:]
            roles = tables_api._roles(tables_api._live_table(s, tpl, "표 서식으로 고른 표"))
        else:
            raise HTTPException(503, "서식 보관함 모듈이 없어 그 표 서식을 쓸 수 없습니다 — 「이 문서의 표」 를 서식으로 고르세요")

        def run():
            r = _guard(lambda: sa.table_new(s.doc, style, norm, op["after"], session=s) if sa is not None else s.doc.table_make(op["after"], tpl, norm, roles))
            ex = _live_excel(s, r["table"], doc_agent.band_roles(s.doc.table_block(r["table"])["cells"], norm))
            done.update(made={"table": r["table"], "rows": r["rows"], "cols": r["cols"]}, excel=ex)
            return {"hosts": [s.doc._ids[r["host"]], ref], "anchor": op["after"], "focus": None,
                    "log": {"type": "tableNew", "table": r["table"], "style": op["style"], "rows": r["rows"], "cols": r["cols"]}}
        return [ref], run
    return make


def _make_fill(op, picks, view, done):
    from app import heading_rules, table_fill

    def make(s):
        from app import tables_api
        tid = op["table"]
        block = tables_api._live_table(s, tid)
        tbl = s.doc._ids[tid]
        by = {f["cell"]: f for f in op["fills"]}
        want = picks if picks is not None else list(view.get("picked") or [])
        if not want:
            raise HTTPException(400, "고른 칸이 없습니다 — 넣을 칸을 고르세요")
        if any(c not in by for c in want):
            raise HTTPException(400, "이 제안에 없는 칸이 들어 있습니다")
        alive = {s.doc._id(x.el) for x in s.doc._tgrid(tbl)[1]}
        now = {c["id"]: str(c.get("text") or "") for c in block["cells"]}
        nested = {c["id"] for c in block["cells"] if any(b.get("type") != "paragraph" for b in c.get("blocks") or [])}
        todo, skipped = [], []
        for cid in want:   # 기존 `tables_api.table_fill_apply` 와 같은 규칙: was 가 지금 칸 글과 다르면 건너뜀 · 칸 안 표·그림도 건너뜀
            f = by[cid]
            if cid not in alive:
                raise HTTPException(409, doc_agent.STALE)
            if cid in nested:
                skipped.append({"cell": cid, "why": "칸 안에 표·그림이 있음"})
            elif f.get("was", "") != now.get(cid, ""):
                skipped.append({"cell": cid, "why": "제안을 받은 뒤 칸 글이 바뀜"})
            else:
                text = f["text"].replace("\r", "").replace(heading_rules.BR, "\n").strip()
                if not text or len(text) > table_fill.CELL_MAX:
                    skipped.append({"cell": cid, "why": "넣을 글이 비었거나 너무 김"})
                else:
                    todo.append((cid, text))
        if not todo:
            raise HTTPException(409, "넣을 칸이 없습니다 — 제안을 받은 뒤 칸 글이 바뀌었습니다. 다시 요청하세요")

        def run():
            for cid, text in todo:
                _guard(lambda cid=cid, text=text: s.doc.set_text(cid, text))
            ex = _live_excel(s, tid, tables_api._heads(s, tid))   # 고른 칸만 넣은 상태로 다시 판정(일부만 골라 합계가 안 맞게 되는 것을 그 자리에서 보인다 — 막지는 않는다)
            done.update(filled={"table": tid, "cells": [c for c, _ in todo], "skipped": skipped}, excel=ex)
            return {"hosts": [tbl], "anchor": tid, "focus": None, "log": {"type": "tableFill", "table": tid, "cells": len(todo), "skipped": len(skipped), "excel": ex["status"]}}
        return [tbl], run
    return make


def _make_fill_lines(op, picks, view, done, levels=None, orig=None):
    """자리 채우기(type fill)의 반영 — 고른 줄(picks = 문단 id 목록 | None = 처음부터 고른 줄)만 `set_text` 로 제자리에. 엇갈림은 **덩이마다**(같은 머리 아래의 줄 묶음 — astra 2차 G8):
    그 덩이의 머리 글이 낼 때와 다르거나(다른 사람 · 다른 항목의 자리가 됐을 수 있다) 고른 줄 하나라도 글이 달라졌거나 없어졌으면 그 덩이의 고른 줄을 **모두** 건너뛴다. 넣을 줄이 하나도 안 남으면
    편집 없이 409(실행 취소 기록도 없다). 통과한 덩이는 한 편집으로(실행 취소 1).
    상자의 줄은 **지금 문서의 덩이를 다시 셈해**(levels = 헤딩 그래프의 레벨 · orig = 올린 원본의 원문 — 부르는 쪽이 세션 잠금 밖에서 읽어 준다) 소속도 견준다(astra 3차): 그 줄이 아직 쓸 자리이고,
    머리 문단 · 머리 글 · 윗 제목 글이 낼 때와 같아야 한다 — 윗 제목만 고쳤거나(「연구개발 목표」 → 「연구개발 결과」) 줄을 다른 머리 아래로 옮겼으면 글이 그대로여도 그 덩이를 건너뛴다(`MOVED`)."""
    def make(s):
        lines = {ln["para"]: ln for ln in op["lines"]}
        want = picks if picks is not None else list(view.get("picked") or [])
        if not want:
            raise HTTPException(400, "고른 줄이 없습니다 — 넣을 줄을 고르세요")
        if any(p not in lines for p in want):
            raise HTTPException(400, "이 제안에 없는 줄이 들어 있습니다")
        box = op.get("box")
        tbl = s.doc._ids.get(box) if box else None
        if box and (tbl is None or tbl.tag != TBL or not s.doc._attached(tbl)):
            raise HTTPException(409, doc_agent.STALE)

        def live(pid):
            el = s.doc._ids.get(pid)
            if el is None or el.tag != P or not s.doc._attached(el):
                return None
            return el if (doc_agent.top_of(s.doc, el) == box if box else doc_agent.top_el(s.doc, pid) is not None) else None   # 같은 상자 안(줄 자리면 본문 최상위)에 그대로 있나

        slots = doc_agent.box_slots(s.doc, box, levels, orig) if box else None
        now = slots[1] if slots else {}   # 지금 문서의 쓸 자리 {문단 id: 자리 정보}

        def moved(pid):
            ln, t = lines[pid], now.get(pid)
            return t is None or t.get("headId") != ln.get("head") or t.get("headRaw") != ln.get("headWas") or ("under" in ln and (t.get("under") or "") != (ln["under"] or ""))

        groups = {}
        for pid in want:
            groups.setdefault(lines[pid].get("head") or f"\x00{pid}", []).append(pid)
        todo, skipped = [], []
        for ids in groups.values():
            ln0, why = lines[ids[0]], None
            if ln0.get("head"):
                hel = live(ln0["head"])
                if hel is None or s.doc._text(hel) != ln0.get("headWas"):
                    why = "그 자리의 머리 글이 바뀜"
            for pid in ids if why is None else ():
                el = live(pid)
                if el is None:
                    why = "그 줄이 없어졌거나 다른 자리로 옮겨짐"
                elif s.doc._text(el) != lines[pid]["was"]:
                    why = "제안을 받은 뒤 줄이 바뀜"
                elif box and moved(pid):
                    why = MOVED
                if why:
                    break
            if why:
                skipped += [{"para": pid, "why": why} for pid in ids]
            else:
                todo += [(pid, lines[pid]["text"]) for pid in ids]
        if not todo:
            raise HTTPException(409, f"넣을 줄이 없습니다 — {skipped[0]['why']}. 다시 요청하세요")
        hosts = [tbl] if tbl is not None else [s.doc._ids[pid] for pid, _ in todo]

        def run():
            for pid, text in todo:
                _guard(lambda pid=pid, text=text: s.doc.set_text(pid, text))
            done.update(filledLines={"box": box, "paras": [pid for pid, _ in todo], "skipped": skipped})
            return {"hosts": hosts, "anchor": box or todo[0][0], "focus": None, "log": {"type": "fill", "box": box, "paras": len(todo), "skipped": len(skipped)}}
        return hosts, run
    return make


def _make_restyle(op, done, side):
    def make(s):
        from app import tables_api
        sa = _style_apply()
        if op.get("table"):
            tid = op["table"]
            block = tables_api._live_table(s, tid, "서식을 입힐 표")
            el = s.doc._ids[tid]
            style = tpl = None
            if sa is not None:
                try:
                    style = sa.style_of(s.doc, op["style"])
                except (KeyError, ValueError) as e:
                    raise HTTPException(409, f"표 서식을 읽지 못했습니다 — 서식을 다시 고르고 요청하세요: {e}") from e
                _same_style(op, style, side)
            elif str(op["style"]).startswith("doc:"):
                tpl = op["style"][4:]
                tpl_roles, roles = tables_api._roles(tables_api._live_table(s, tpl, "표 서식으로 고른 표")), tables_api._roles(block)
            else:
                raise HTTPException(503, "서식 보관함 모듈이 없어 그 표 서식을 쓸 수 없습니다 — 「이 문서의 표」 를 서식으로 고르세요")

            def run():
                r = _guard(lambda: sa.table_restyle(s.doc, style, tid, op.get("bands"), session=s) if sa is not None else s.doc.table_restyle(tid, tpl, roles, tpl_roles)) or {}
                changed = set(r.get("formatted") or [])
                done.update(formatted={"table": tid, "paras": len(changed)})
                return {"hosts": [el], "anchor": tid, "focus": None, "formatted": changed, "log": {"type": "restyle", "table": tid, "style": op["style"], "formatted": len(changed)}}
            return [el], run
        if sa is None:
            raise HTTPException(503, "서식 보관함 모듈이 없어 글 서식을 입힐 수 없습니다")
        els = [s.doc._ids.get(i) for i in op["paras"]]
        if any(e is None or e.tag != P or not s.doc._attached(e) for e in els):
            raise HTTPException(409, doc_agent.STALE)
        try:
            tstyle = sa.text_style(op["style"])
        except (KeyError, ValueError) as e:
            raise HTTPException(409, f"글 서식을 읽지 못했습니다 — 서식을 다시 고르고 요청하세요: {e}") from e
        _same_style(op, tstyle, side)

        def run():
            changed = set(_guard(lambda: sa.format_paras(s.doc, tstyle, op["item"], list(op["paras"]), keep_numbering=True, session=s)) or [])
            done.update(formatted={"paras": len(changed)})
            return {"hosts": els, "anchor": op["paras"][0], "focus": None, "formatted": changed, "log": {"type": "restyle", "paras": len(op["paras"]), "style": op["style"], "item": op["item"]}}
        return els, run
    return make


@router.post("/api/docs/{doc_id}/agent/apply")
def agent_apply(doc_id: str, body: dict = Body(...)):
    """제안 하나를 문서에 — {turn, proposal, picks?: {fills: [칸 id…]}(표 채우기 — 없으면 처음부터 고른 칸), expectedRev, requestId}. **서버에 저장한 제안**을 실행한다(본문의 내용은 실행하지 않는다).
    제안 하나 = `server._edit` 한 번(실행 취소 1개 · OWPML 지역 검사 · 기록 `agentApply`). 응답 = 구조 편집 응답 + `replayed: false` + `applied {turn, proposal, type, state, made? {table, rows, cols},
    filled? {table, cells[], skipped[{cell, why}]}, written? {paras[새 문단 id]}, formatted? {table?, paras: n}, excel?(반영한 뒤의 엑셀 검증 — 새 표 · 표 채우기), note?(제안 상태를 저장하지 못했을 때만)}`.
    저장한 제안에는 `state: "applied"` 와 `applied {at, rev, table, paras[], cells[], excel, note, made?, filled?, written?, formatted?}` 를 적는다(다시 읽은 화면이 「반영됨 — 자리로」 를 그리는 꼴),
    같은 묶음의 다른 후보는 `state: "closed"`(closedBy). 넣는 제안(글 쓰기 · 새 표)을 반영하면 **같은 턴 · 같은 자리**의 열린 넣는 제안은 대상 지문의 경계(`target.next`)를 방금 넣은 것으로
    옮겨 적는다 — 사람이 그 턴의 「표와 글」 을 차례로 반영하는 길을 막지 않으려는 것이고, 다른 길(본문 편집 · 다른 턴의 제안)로 그 자리 뒤에 들어온 것은 낡은 것으로 본다.
    **같은 requestId 가 다시 오면** `{replayed: true, applied(그때의 영수증), …지금 문서 상태(`Session.state()` — rev · undo …)}` 만 돌려준다 — `tops`·`texts`·`focus`·`edited`·`original` 은 없다:
    옛 구조 패치를 다시 주면 화면이 그 뒤의 문서(실행 취소 · 다른 편집)를 옛 것으로 덮는다(검토 5). 화면은 rev 가 제 것과 다르면 문서를 다시 읽는다.
    막이(이 차례): 403 정책(원본 문서) → 같은 requestId 는 영수증(문서 안 바뀜) → 409 이미 반영한 제안 · 낡은 제안 → 409 같은 후보 묶음의 다른 후보가 반영됨 →
    409 대상이 바뀜(expectedRev 가 지금과 다르거나 문서가 baseRev 뒤 바뀌었으면 대상 지문을 다시 견준다 — 대상 블록의 글 · 넣는 자리의 경계 · 서식으로 쓰는 이 문서의 표: 다르면 제안 상태 stale
    「문서가 바뀌었습니다 — 다시 요청하세요」) → 409 보관함 서식의 revision 이 제안을 낸 때와 다름(「서식이 바뀌었습니다 — 다시 요청하세요」 — 제안 상태 stale).
    400: 본문 틀림 · docx · 고른 칸 없음 · 404: 그런 턴·제안 없음 · 422: OWPML 에 어긋나 되돌림(제안은 그대로 열려 있다).
    문서 변경과 「반영됨」 기록(검토 6): 편집이 성공하면 제안 상태를 쓰고(실패하면 한 번 더) 바로 문서 상태를 작업 폴더에 쓴다(`server._persist_safe(s, force=True)` — 배경 저장을 기다리지 않는다).
    제안 상태를 두 번 다 못 썼으면 성공 응답의 `applied.note` 에 「반영했지만 제안 상태를 저장하지 못했습니다 — 같은 제안을 다시 반영하지 마세요」 를 싣고, 이 프로세스는 그 제안을 다시 반영하지 않는다.
    자리 채우기(type `fill` — spec_양식작성 ② §5-3): picks.fills = 고른 **문단 id**(없으면 처음부터 고른 줄) · 엇갈림은 덩이마다 가려 통과한 덩이만 한 편집으로(`_make_fill_lines`) —
    응답 `applied.filledLines {box, paras[채운 문단 id], skipped[{para, why}]}` · 넣을 줄이 하나도 안 남으면 409(편집 없음) · 제안에 없는 문단 id 는 400.
    **서식 복사(type `styleCopy` — spec_서식복사 ② §6)는 다른 길이다**(`_copy_apply`): 문서를 바꾸지 않으므로 `server._edit` 를 쓰지 않고(실행 취소 없음 · rev 그대로) 쓰기 정책 403 에 걸리지 않는다(원본 문서에서도 된다).
    같은 requestId · 404 · 409 이미 반영 · 409 낡음(고른 표·문단의 글·서식 지문)은 같다. 응답 `{replayed: false, applied {turn, proposal, type, state, styles[{id, name, kind, revision, pick}], failed[{name, why, kind, pick}]}, rev}` —
    문서 조각 없음. 하나라도 저장되면 「반영됨」, 모두 실패면 200 + failed 로 열어 둔다(state "open")."""
    from app import server
    body = body if isinstance(body, dict) else {}
    tid, pid, rid, picks = body.get("turn"), body.get("proposal"), body.get("requestId"), body.get("picks")
    if not isinstance(tid, str) or not isinstance(pid, str):
        raise HTTPException(400, "turn · proposal(글)이 필요합니다")
    if not isinstance(rid, str) or not 1 <= len(rid) <= REQUEST_ID_MAX:
        raise HTTPException(400, f"requestId(1~{REQUEST_ID_MAX}자)가 필요합니다")
    if picks is not None and (not isinstance(picks, dict) or not isinstance(picks.get("fills", []), list) or not all(isinstance(c, str) for c in picks.get("fills", []))
                              or len(set(picks.get("fills", []))) != len(picks.get("fills", []))):
        raise HTTPException(400, "picks 는 {fills: [칸 id…(표 채우기) | 문단 id…(자리 채우기)]}(겹침 없이)")
    expected = body.get("expectedRev")
    s = _sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "에이전트 쓰기는 지금 hwpx 문서만 됩니다")
    pol = _policy(s)
    store = doc_agent.Store(s.id)
    if not pol["apply"] and not _copies_style(store, tid, pid):   # 「서식 복사」 는 문서를 바꾸지 않는다 — 쓰기 정책에 걸리지 않는다(원본 문서에서도 된다: spec_서식복사 ② §6). 그 밖의 제안 · 없는 제안은 전처럼 403 이 먼저
        raise HTTPException(403, pol["why"])
    with store.lock:   # 읽기 → 검사 → 편집 → 상태 쓰기를 한 잠금 안에서(같은 제안을 두 요청이 함께 반영하지 못하게). 잠금 차례: 저장소 → 세션
        seen = store.request(rid)
        if seen is not None:
            if seen.get("turn") != tid or seen.get("proposal") != pid:
                raise HTTPException(400, "그 requestId 는 다른 제안에 쓰였습니다")
            with s.lock:   # 영수증 + **지금** 문서 상태 — 옛 구조 패치(tops·texts …)는 다시 보내지 않는다(검토 5). 옛 기록(response 통째)에서는 그 안의 applied 만 쓴다
                state = s.state()
            receipt = seen["applied"] if "applied" in seen else (seen.get("response") or {}).get("applied")
            return jsonable_encoder({"replayed": True, "applied": receipt, **state})
        rec = store.turn(tid)
        p = next((x for x in (rec or {}).get("proposals") or [] if x.get("id") == pid), None)
        if p is None:
            raise HTTPException(404, "그런 제안이 없습니다 — 대화를 비웠거나 다른 문서의 제안입니다")
        if p.get("state") == "applied" or _applied_here(s.id, tid, pid):   # 뒤의 것 = 문서는 바뀌었는데 제안 상태를 디스크에 못 쓴 경우(아래)
            raise HTTPException(409, "이미 반영한 제안입니다")
        if p.get("state") == "stale":
            raise HTTPException(409, doc_agent.STALE)
        group = p.get("choiceGroup")
        if group and any(x.get("choiceGroup") == group and x.get("state") == "applied" for x in rec["proposals"]):
            raise HTTPException(409, "같은 묶음의 다른 후보를 이미 반영했습니다 — 후보는 하나만 반영합니다")
        if p.get("state") != "open":
            raise HTTPException(409, "반영할 수 없는 제안입니다")
        if p.get("type") == "styleCopy":   # 서식 복사 — 문서를 바꾸지 않는다: `server._edit` 없이 보관함에 저장만(실행 취소 없음 · 문서 차례 그대로)
            return _copy_apply(s, store, rec, p, tid, pid, rid, expected)
        op, done, side, went_stale = p["op"], {}, {}, []   # done = 응답·영수증에 싣는 것 · side = 안에서만 쓰는 것(stale — 서식이 바뀜 · targets — 옮겨 적을 지문)
        inner = {"write": lambda: _make_write(op, done, side), "tableNew": lambda: _make_table_new(op, done, side), "restyle": lambda: _make_restyle(op, done, side),
                 "tableFill": lambda: _make_fill(op, (picks or {}).get("fills") if picks and "fills" in picks else None, p.get("view") or {}, done),
                 # 자리 채우기 — picks.fills = 문단 id · 레벨 · 올린 원본은 여기서(세션 잠금 밖) 읽어 넘긴다: 반영이 지금 문서의 덩이를 다시 셈해 소속을 견준다
                 "fill": lambda: _make_fill_lines(op, (picks or {}).get("fills") if picks and "fills" in picks else None, p.get("view") or {}, done,
                                                  _levels(s) if op.get("box") else None, _uploaded(s) if op.get("box") else None)}.get(p.get("type"))
        if inner is None:
            raise HTTPException(400, "모르는 종류의 제안입니다")
        inner = inner()

        def make(sess):
            now = _policy(sess)   # 정책을 **세션 잠금 안에서** 한 번 더(위의 검사는 잠금 밖 — 그 사이 TASK·문서 역할을 바꾸는 요청과 엇갈릴 수 있다: 검토 7 의 에이전트 쪽)
            if not now["apply"]:
                raise HTTPException(403, now["why"])
            if (expected != sess.rev or sess.rev != p.get("baseRev")) and doc_agent.stale(sess.doc, p):
                went_stale.append(True)
                raise HTTPException(409, doc_agent.STALE)
            before, run = inner(sess)
            t = p.get("target") or {}
            if "next" not in t:
                return before, run
            # 넣는 제안: 같은 턴 · 같은 자리(같은 넣을 자리 · 같은 경계)의 **지금 낡지 않은** 열린 넣는 제안 — 이 반영이 그 자리 뒤에 넣는 것 때문에 낡지 않게, 넣은 직후(같은 세션 잠금 안)의 지문을 받아 둔다
            sibs = [x for x in rec["proposals"] if x is not p and x.get("state") == "open" and "next" in (x.get("target") or {}) and x["target"].get("block") == t.get("block")
                    and x["target"].get("next") == t.get("next") and not doc_agent.stale(sess.doc, x)]

            def run_then_mark():
                out_ = run()
                side["targets"] = {x["id"]: doc_agent.target_of(sess.doc, x["target"].get("blocks") or [x["target"].get("block")], insert=True, style=x["target"].get("style")) for x in sibs}
                return out_
            return before, run_then_mark
        try:
            out = server._edit(doc_id, make, "agentApply", {"turn": tid, "proposal": pid, "type": p.get("type"), "requestId": rid})
        except HTTPException:
            if went_stale or side.get("stale"):   # 대상이 바뀜 · 보관함 서식이 바뀜 — 이 제안은 다시 반영할 수 없다
                p["state"] = "stale"
                store.save_turn(rec)
            raise
        if not isinstance(out, dict):   # 422 — OWPML 에 어긋나 되돌림: 제안은 그대로 열려 있다
            return out
        # 여기부터 문서는 바뀌었다. 먼저 메모리에 적는다 — 아래 저장이 실패해도 이 프로세스는 이 제안을 다시 반영하지 않는다(넣는 제안은 앵커 글을 안 바꿔 대상 지문으로는 두 번 넣기를 못 막는다)
        _applied_here(s.id, tid, pid, mark=True)
        made, filled, written = done.get("made") or {}, done.get("filled") or {}, done.get("written") or {}
        skipped = filled.get("skipped") or []
        note = (f"{len(filled.get('cells') or [])}칸 채움" + (f" · 건너뜀 {len(skipped)}({skipped[0]['why']})" if skipped else "")) if p["type"] == "tableFill" else ""
        lined = done.get("filledLines") or {}
        if p["type"] == "fill":   # 자리 채우기 — 채운 줄 · 덩이째 건너뛴 줄(까닭)
            note = f"{len(lined.get('paras') or [])}줄 채움" + (f" · 건너뜀 {len(lined['skipped'])}({lined['skipped'][0]['why']})" if lined.get("skipped") else "")
        # 화면이 다시 읽었을 때 그리는 꼴: table(새 표 · 채운 표 · 서식을 입힌 표) · paras(쓴 문단 · 서식을 입힌 문단) · cells(채운 칸) · excel(반영한 뒤의 검증) · note — 그리고 반영 응답의 조각 그대로
        p.update(state="applied", applied={"at": round(time.time(), 3), "rev": s.rev, "table": made.get("table") or op.get("table") or None,
                                           "paras": written.get("paras") or lined.get("paras") or list(op.get("paras") or []),
                                           "cells": filled.get("cells") or [], "excel": done.get("excel"), "note": note,
                                           "sources": doc_agent.applied_sources(p, written.get("paras") or [], lined.get("paras") or [], filled.get("cells") or []),   # 들어간 문단 · 칸 → 근거의 자료 자리(② §5-12 3)
                                           **{k: done[k] for k in ("made", "filled", "written", "formatted", "filledLines") if k in done}})
        for x in rec["proposals"]:
            if group and x is not p and x.get("choiceGroup") == group and x.get("state") == "open":   # 같은 묶음의 다른 후보는 닫는다(하나만 반영)
                x.update(state="closed", closedBy=pid)
            elif x.get("id") in (side.get("targets") or {}) and x.get("state") == "open":             # 같은 턴 · 같은 자리의 넣는 제안: 경계를 방금 넣은 것으로 옮겨 적는다
                x["target"] = side["targets"][x["id"]]
        saved = _save_twice(store, rec, s.id, tid, pid)
        # 문서 상태를 같은 요청 안에서 작업 폴더에(배경 저장 1.5초를 기다리지 않는다) — 「제안은 반영됨인데 다시 연 문서에는 없다」 의 틈을 줄인다. 남는 틈(적용 저널이 없다 — 검토 6):
        # ⓐ 위의 제안 상태 쓰기와 이 문서 쓰기 **사이**에 서버가 죽으면 제안은 반영됨인데 다시 연 문서는 반영 전이다(두 번 넣지는 않는다 — 다시 요청해야 한다)
        # ⓑ 제안 상태를 못 쓴 채(아래 note) 서버가 죽으면 다시 연 뒤 그 제안이 열린 채라 한 번 더 반영할 수 있다(문서는 이미 바뀜 — `_APPLIED` 는 메모리뿐이다)
        # ⓒ 이 문서 쓰기가 실패하면(`persistError`) 배경 저장이 다음 차례에 다시 쓴다 — 그 전에 죽으면 ⓐ 와 같다.
        server._persist_safe(s, force=True)
        receipt = jsonable_encoder({"turn": tid, "proposal": pid, "type": p["type"], "state": "applied", **done, **({} if saved else {"note": NOT_SAVED})})
        try:
            store.remember(rid, receipt, tid, pid)
        except Exception as e:  # noqa: BLE001 — 영수증을 못 붙들어도 반영은 끝났다(같은 requestId 가 다시 오면 「이미 반영한 제안」 409 가 막는다)
            log.warning("[에이전트 반영] %s 영수증을 저장하지 못했습니다(%s · %s): %r", s.id, tid, pid, e)
        return jsonable_encoder({**out, "replayed": False, "applied": receipt})


def _style_api():
    """`app.style_api`(서식 보관함 끝점 모듈 — 저장 몸통 `save_doc_style`) | None(아직 없음 · 가져오기 실패)."""
    try:
        from app import style_api
        return style_api
    except Exception:  # noqa: BLE001 — 모듈 없음·가져오다 오류: 에이전트 열의 다른 길은 서식 보관함 없이도 돈다
        return None


def _copies_style(store, tid, pid):
    """저장한 그 제안이 「서식 복사」(styleCopy)인가 — 없는 턴·제안은 False(쓰기 정책 403 이 404 보다 먼저인 전의 차례 그대로)."""
    rec = store.turn(tid)
    return any(x.get("id") == pid and x.get("type") == "styleCopy" for x in (rec or {}).get("proposals") or [])


def _copy_apply(s, store, rec, p, tid, pid, rid, expected):
    """「서식 복사」 제안의 반영(spec_서식복사 ② §6) — 저장소 잠금 안에서 부른다(`agent_apply` 의 막이 404·409 를 지난 뒤). **문서를 바꾸지 않는다**: `server._edit` 를 쓰지 않고(실행 취소 없음 ·
    문서 차례 그대로 · OWPML 검사 없음) 쓰기 정책도 보지 않는다(원본 문서에서도 된다). 대상 지문(고른 표·문단의 글·서식 — `doc_agent.looks_target`)은 전과 같은 조건으로 견준다:
    expectedRev 가 지금과 다르거나 문서가 baseRev 뒤 바뀌었고 지문이 다르면 409 + 제안 상태 stale. 그 뒤 pick 마다 `style_api.save_doc_style(s, body)`(= `POST …/styles` 의 몸통 — 저장하고 PDF 검증을 건다):
    그 함수가 안에서 세션 잠금을 잡으므로 **세션 잠금 밖에서** 부른다(`threading.Lock` — 겹쳐 잡으면 멈춘다). HTTPException(없는 블록 · 보관함 끔 · 끊어진 참조 …)은 그 pick 의 실패로 모은다.
    → {replayed: false, applied: {turn, proposal, type "styleCopy", state "applied" | "open", styles[{id, name, kind, revision, pick}], failed[{name, why, kind, pick}], note?}, rev} —
    구조 편집 응답의 문서 조각(tops·texts …)은 없다. `pick` = 제안 view.picks 안의 차례. 하나라도 저장되면 제안은 「반영됨」(`applied.styles`·`applied.failed`), 모두 실패면 열어 둔다(200 + failed — 화면이 까닭을 보인다).
    영수증은 두 경우 모두 requestId 로 붙든다(같은 requestId 는 그 영수증). 기록 `agentApply`(type styleCopy · styles 수 · failed 수)."""
    sa = _style_api()
    if sa is None:
        raise HTTPException(503, "서식 보관함 모듈이 없어 서식을 저장할 수 없습니다")
    with s.lock:   # 대상 지문만 세션 잠금 안에서 — 저장은 아래(잠금 밖)
        gone = (expected != s.rev or s.rev != p.get("baseRev")) and doc_agent.stale(s.doc, p)
    if gone:       # 고른 표·문단이 제안을 낸 뒤 바뀜 — 본 것과 다른 서식을 저장하지 않는다
        p["state"] = "stale"
        store.save_turn(rec)
        raise HTTPException(409, doc_agent.STALE)
    views = (p.get("view") or {}).get("picks") or []
    styles, failed = [], []
    for k, body in enumerate((p.get("op") or {}).get("picks") or []):
        label = body.get("name") or (views[k].get("summary") if k < len(views) else None) or doc_agent.STYLE_KINDS.get(body.get("kind")) or "서식"
        try:
            meta = sa.save_doc_style(s, dict(body))
            styles.append({"id": meta.get("id"), "name": meta.get("name"), "kind": meta.get("kind"), "revision": meta.get("revision"), "pick": k})
        except HTTPException as e:
            failed.append({"name": label, "why": str(e.detail), "kind": body.get("kind"), "pick": k})
        except Exception as e:  # noqa: BLE001 — 한 서식의 예상 밖 오류가 나머지 저장을 막지 않는다
            log.warning("[에이전트 반영] %s 서식 복사 %s · %s 의 pick %d 를 저장하지 못했습니다: %r", s.id, tid, pid, k, e)
            failed.append({"name": label, "why": f"저장하지 못했습니다: {type(e).__name__}: {e}"[:300], "kind": body.get("kind"), "pick": k})
    saved = True
    if styles:     # 하나라도 저장됨 — 제안은 「반영됨」(같은 제안을 다시 반영하면 같은 서식이 또 생긴다). 모두 실패면 열어 둔다
        _applied_here(s.id, tid, pid, mark=True)
        p.update(state="applied", applied={"at": round(time.time(), 3), "rev": s.rev, "table": None, "paras": [], "cells": [], "excel": None,
                                           "note": f"서식 {len(styles)}개 저장" + (f" · 실패 {len(failed)}" if failed else ""), "styles": styles, "failed": failed})
        saved = _save_twice(store, rec, s.id, tid, pid)
    works.log(s.id, "agentApply", rev=s.rev, turn=tid, proposal=pid, type="styleCopy", requestId=rid, styles=len(styles), failed=len(failed))
    receipt = jsonable_encoder({"turn": tid, "proposal": pid, "type": "styleCopy", "state": "applied" if styles else "open", "styles": styles, "failed": failed,
                                **({} if saved else {"note": NOT_SAVED})})
    try:
        store.remember(rid, receipt, tid, pid)
    except Exception as e:  # noqa: BLE001 — 영수증을 못 붙들어도 저장은 끝났다(같은 requestId 가 다시 오면 「이미 반영한 제안」 409 가 막는다)
        log.warning("[에이전트 반영] %s 영수증을 저장하지 못했습니다(%s · %s): %r", s.id, tid, pid, e)
    return {"replayed": False, "applied": receipt, "rev": s.rev}


def _save_twice(store, rec, wid, tid, pid):
    """반영한 뒤의 턴 기록(제안 상태 「반영됨」)을 쓴다 — 실패하면 한 번 더 → 썼는가. 둘 다 실패하면 기록에 경고를 남긴다(문서는 이미 바뀌었다 — 부르는 쪽이 응답에 그 말을 싣는다)."""
    err = None
    for _ in range(2):
        try:
            store.save_turn(rec)
            return True
        except Exception as e:  # noqa: BLE001 — 디스크 가득 · 잠긴 파일 …: 반영 자체는 성공이다
            err = e
    log.warning("[에이전트 반영] %s 문서는 바뀌었는데 제안 상태를 저장하지 못했습니다(%s · %s): %r", wid, tid, pid, err)
    return False
