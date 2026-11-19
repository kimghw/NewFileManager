"""서식 보관함 끝점(spec_일반편집 ② §7) — 보관함(목록·읽기·고치기·지우기·검증) · 문서에서 저장 · 파일에서 추출 · 문서에 적용.

- 저장소 `app/style_lib.py` · 운반 문서 `app/style_carrier.py` · 적용 `app/style_apply.py`. 추출 후보(`app/style_extract.py`)와 PDF 검증(`app/style_verify.py`)은
  **부를 때 가져온다** — 그 모듈이 없으면 그 기능만 빠진다(후보·파일 추출 501 · 검증은 null).
- 적용은 구조 편집 트랜잭션 `server._edit` 하나(잠금·스냅샷·OWPML 검사·실행 취소 1개·기록 `styleApply`): `make(s)` 에서는 **검사만**, 가져오기·삽입은 모두 `run()` 안
  (스냅샷이 `make` 뒤에 찍힌다). `run()` 의 예상 밖 예외는 ValueError 로 바꿔 던진다(트랜잭션이 되돌리고 400). 대상 문서는 hwpx 만.
  **쓰기 정책**(`doc_agent.policy` — 에이전트 반영과 같은 것)을 `make(s)` 에서 = 세션 잠금 안에서 본다: 그 TASK 의 원본 문서(이관의 사업계획서 · 취합의 기관 문서)는 403.
- 고치기·지우기는 `expectedRevision` 을 **꼭 받는다**(없거나 revision 꼴이 아니면 400 · 지금 것과 다르면 409) — 깨진 템플릿을 지울 때만 없이.
- 저장하는 글(기본 이름 · 구조 blueprint 의 라벨)은 **운반 문서에 남긴 글**에서만 읽는다(원본 문서의 칸 글이 아니라 — `style_carrier.label_cells`).
- 상태 코드: 없는 id·깨진 템플릿 404 · revision 다름 409 · 보관함 끔 503 · hwpx 아님·틀린 입력·expectedRevision 없음·끊어진 참조 400 · 원본 문서 403 · 토큰 만료 410 · 모듈 없음 501.
- **문서 서식 복사**(spec_서식복사 ② §4~§9): 종류 `page`(문서 서식 — 쪽 설정 + 바탕 글) · **두 형식**(저장할 때 docx 운반 문서를 함께 지어 넣는다 — `_create`: `app.style_docx` 가 없거나
  못 지으면 저장은 그대로 `docx: null` · 옛 템플릿은 내려받기·검증·docx 적용 때 그 자리에서 지어 붙인다 — `_docx_bytes`) · 검증 기록 둘(`verify` · `verifyDocx` — `_verify(meta, fmt=)`) ·
  **docx 문서**(후보 · 저장: 표 = 명세로 다시 지음 · 글 = 문단의 서식 요약 · 문서 서식 — `fidelity: "summary"` / 적용: 빈 표 넣기 · 문단에 입히기만) · hwpx 문서의 `{mode: "page"}` ·
  파일 후보에 이름 붙이기 `POST /api/styles/name-file`. `app.style_docx`·`app.style_page` 도 부를 때 가져온다(없으면 그 기능만 빠진다).
- **2차**(spec_서식복사 ② §12~§16):
  - 저장의 몸통을 **짓기**(`build_doc_style(s, body) -> (meta, data)` — 보관함에 쓰지 않고 검증도 걸지 않는다)와 **저장**(`save_doc_style` = 짓기 + `_create` + 기록 + 검증)으로 갈랐다.
    **견본 끝점**(`POST /api/docs/{id}/styles/preview` · `POST /api/styles/preview-file`)이 앞의 것(파일은 `style_extract.build_pick`)으로 지은 운반 문서의 보기(`style_carrier.view`)만 돌려준다 —
    그림은 「저장될 견본」 이다(저장과 같은 생성 함수). 같은 문서 차례(rev)·같은 몸의 견본은 세션마다 작게 기억한다(`_memo` — 문서가 바뀌면 버림).
  - 종류 **`cover`**(표지 서식 — `app.style_cover`: 부를 때 가져온다): 저장 `{kind: "cover", end?, roles?, name?, keepText?}`(범위 = 그때의 표지 후보 `style_cover.find` · `end` 로 줄임) · 적용 `{mode: "cover"}`(hwpx — `covered: {blocks: n}`).
  - 문단 서식의 **`role`**(저장 · `PUT` · 목록 요약의 `role`·`leveled`) · 템플릿 저장의 `rep`(레벨 → 대표 문단: 그래프의 그 템플릿 그 레벨 노드일 때만) · 쪽 설정 저장의 `bodyKey`(후보의 `bodies` 가운데 하나 | "none").
  - 후보 응답에 `paras`·`covers`(추출 모듈이 안 내면 빈 목록) · `llm: true` 면 `style_extract.review`(없으면 옛 `name`)의 결과를 다섯 종류의 후보에 합친다(`_named` — X 가 돌려준 칸 그대로) · 응답에 `calls`.
  - 쪽 설정·표지의 검증 그림은 첫 쪽 전체 — `GET …/proof.png?full=1` 은 저장된 `proof.pdf` 에서 그 자리에서 다시 그린다(옛 그림은 내용 둘레로 잘린 것)."""
import importlib
import json
import logging
import re
import threading
import time
import weakref
from collections import OrderedDict
from urllib.parse import quote

from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from app import format_names, heading_runs, pdf_render, style_apply, style_carrier, style_lib, table_make, works
from app.hwpx_doc import P

router = APIRouter()
log = logging.getLogger(__name__)
MODES = ("tableMake", "tableBlank", "tableRestyle", "format", "page", "cover")  # cover = 표지 넣기(spec_서식복사 ② §14 — hwpx)
DOCX_MODES = ("tableBlank", "format")  # docx 문서에 되는 적용(spec_서식복사 ② §9)
GROUPS = ("tables", "texts", "paras", "pages", "covers")  # 후보의 다섯 종류(spec_서식복사 ② §16 — `style_extract.candidates`·`review` 의 키)
PICK_GROUP = {"table": "tables", "text": "texts", "page": "pages", "cover": "covers"}  # pick 의 kind → entry 의 후보 목록(글은 texts → paras 차례로 찾는다)
NAME_GROUP = {"tables": "table", "texts": "text", "paras": "para", "pages": "page", "covers": "cover"}  # 후보 종류 → 서식 이름의 갈래(`format_names.keys_for` — spec_서식복사 ② §19-2)
# 서식 값 고치기(spec_서식복사 ② §19-6·§19-7) — 받는 키와 범위(서식 지도의 대기 값과 같은 범위). line1Mm·line2Mm = 첫 줄·둘째 줄 시작(왼쪽 여백 + 첫 줄 들여쓰기 — 화면 「앞 여백」·「2번째 줄」) ·
# textMm = 첫 내용 글자의 자리(화면 「글 시작」 = 앞 여백 + 레터 자리 폭 — line1Mm 과 함께는 못 준다: `style_carrier.retune`)
EDIT_NUMS = {"line1Mm": (0, 300), "textMm": (0, 300), "line2Mm": (0, 300), "sizePt": (1, 200), "lineSpacingPct": (50, 500)}
EDIT_KEYS, FONT_MAX = (*EDIT_NUMS, "font"), 40
GONE = "올린 파일을 서버가 놓았습니다 — 다시 올려야 저장할 수 있습니다"  # 토큰이 없음(410) — 30분이 지났거나, 넷까지만 잡아 두어 먼저 밀려났다(어느 쪽인지 단정하지 않는다: ② §13)
NO_COVER = "이 문서에서 표지를 찾지 못했습니다"
MEMO_DOCS, MEMO_PREVIEWS = 6, 80  # 세션마다의 기억(`_memo`) — 문서 수 · 문서마다의 견본 수
DOCX_ONLY = "docx 문서에는 빈 표 넣기 · 문단에 입히기만 됩니다"
FORMATS = style_lib.FORMATS
MIME = {"hwpx": "application/hwp+zip", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
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


def _verify(meta, full=True, fmt="hwpx"):
    """meta.verify(fmt="docx" 면 meta.verifyDocx — spec_서식복사 ② §7)의 보기 — 도는 중이면 status "running"(메모리), stale = 검증 뒤 meta(띠 수·blueprint·items)가 바뀜.
    full 이 아니면 {status, coverage, stale} 만. 도는 중 = 그 형식이 아직 안 끝남(`style_verify.pending` — 그 함수가 없는 검증 모듈이면 hwpx 만 도는 것으로 본다)."""
    key = style_lib.VERIFY_KEY[fmt]
    v, sv = meta.get(key) if isinstance(meta.get(key), dict) else None, _mod("style_verify")
    stale = running = False
    try:
        running = bool(sv is not None and sv.running(meta["id"]))
        left = getattr(sv, "pending", None) if running else None
        if left is not None or fmt != "hwpx":
            running = left is not None and fmt in left(meta["id"])
        stale = bool(v and sv is not None and v.get("subjectHash") and v["subjectHash"] != (sv.subject_hash(meta) if fmt == "hwpx" else sv.subject_hash(meta, fmt)))
    except Exception as e:  # noqa: BLE001 — 검증 모듈의 오류가 목록을 막지 않는다
        log.warning("서식 검증 상태를 읽지 못함: %r", e)
    if v is None and not running:
        return None
    out = {**(v or {}), "stale": stale} if full else {"status": (v or {}).get("status"), "coverage": (v or {}).get("coverage"), "stale": stale}
    return {**out, "status": "running"} if running else out


def _full(meta) -> dict:
    """meta + 형식마다의 검증 보기(`verify` · `verifyDocx`). `docx` = {sha256, losses} | null(docx 서식 없음)."""
    return {**meta, "verify": _verify(meta), "docx": meta.get("docx") if isinstance(meta.get("docx"), dict) else None, "verifyDocx": _verify(meta, fmt="docx")}


def _kick(sid, force=False, formats=None):
    """그 템플릿의 PDF 검증을 건다(작업 — 동기 응답이 아니다) -> 도는 기록 | None(검증 모듈 없음 · 못 걺). formats = 검증할 형식(없으면 둘 다 — 한글 → Word)."""
    sv = _mod("style_verify")
    if sv is None:
        return None
    try:
        if formats:
            return sv.start(sid, force=bool(force), formats=list(formats))
        return sv.start(sid, force=True) if force else sv.start(sid)
    except Exception as e:  # noqa: BLE001 — 검증을 못 걸어도 저장은 된 것이다
        log.warning("서식 검증을 걸지 못함 %s: %r", sid, e)
        return None


def _is_docx(s) -> bool:
    """docx 문서의 세션인가 — hwpx 어댑터만 `table_make` 가 있다(`_hwpx` 와 같은 판정)."""
    return not hasattr(s.doc, "table_make")


def _build_docx(meta, carrier):
    """docx 운반 문서를 짓는다(spec_서식복사 ② §4 — `style_docx.build(meta, carrier)`) -> (docx 바이트, losses) | None(`app.style_docx` 가 없음 · ValueError · 그 밖의 오류).
    못 지어도 예외를 내지 않는다 — 저장은 그대로 되고 `docx: null`."""
    sd = _mod("style_docx")
    if sd is None or not carrier:
        return None
    try:
        data, losses = sd.build(meta, carrier)
    except Exception as e:  # noqa: BLE001 — docx 서식을 못 지은 것이 저장·읽기를 막지 않는다
        log.info("docx 운반 문서를 짓지 못함(%s): %r", meta.get("name"), e)
        return None
    return (bytes(data), [str(x) for x in losses or [] if x]) if data else None


def _src(s, fmt) -> dict:
    """세션 문서의 원본 기록(spec_서식복사 ② §17 — `style_lib.SOURCE_KEYS`): 문서 이름 · 형식 · 작업 id · 올린 원본의 해시 + 그 작업의 **프로젝트 · TASK · 라운드** + 뽑은 때. block·where 는 부르는 쪽이 채운다.
    작업 기록(work.json)을 못 읽으면 프로젝트·TASK·라운드는 None."""
    try:
        task = (works.work(s.id) or {}).get("task")
    except Exception:  # noqa: BLE001 — 작업 기록을 못 읽는 것이 저장을 막지 않는다
        task = None
    task = task if isinstance(task, dict) else {}
    project = (task.get("project") or "").strip() or None
    rnd = task.get("round", 1 if project else None)  # 프로젝트에 묶인 작업의 라운드 — 안 적힌 옛 작업은 1(spec_작업 ② §17), 프로젝트가 없으면 라운드도 없다
    return {"name": s.name, "format": fmt, "work": s.id, "page": None, "sha256": getattr(s, "doc_key", None), "project": project,
            "job": task.get("job") or None, "round": rnd if isinstance(rnd, int) and not isinstance(rnd, bool) and rnd > 0 else None, "where": None, "at": round(time.time(), 3)}


def _table_where(s, tid):
    """그 표가 문서의 몇 번째 표인가(본문 최상위 표 차례) → 「표 3번째」 | 「칸 안의 표」(최상위가 아님). 문서의 글은 쓰지 않는다(② §17). 세션 잠금 안에서."""
    tops = [b["id"] for b in s.doc.blocks() if b.get("type") == "table"]
    return f"표 {tops.index(tid) + 1}번째" if tid in tops else "칸 안의 표"


def _create(meta, data):
    """보관함에 새 템플릿 — hwpx 운반 문서 data 와 함께 **docx 운반 문서를 지어** 넣는다(`files={"carrier.docx": …}` + `meta.docx = {sha256, losses}`). 못 지으면 `docx: null` 로 그대로 저장.
    같은 서식이 이미 있으면 다시 저장하지 않고, **이 문서에서도 나왔다**는 것만 그 서식에 적는다(`style_lib.add_seen` — ② §17: 원본이 다른 문서일 때만)."""
    built = _build_docx(meta, data)
    files = {style_lib.CARRIER_DOCX: built[0]} if built else None
    same = _same_look(meta, built[0]) if built else None
    if same is not None:  # 같은 서식이 이미 있다 — 다시 저장하지 않고 있던 것을 돌려준다(`existing: true`): 같은 문서를 다시 「한 번에 진행」 해도 보관함에 겹쳐 쌓이지 않게
        try:
            same = style_lib.add_seen(same["id"], meta.get("source")) or same
        except OSError as e:  # 적지 못해도 있던 서식은 그대로 쓴다
            log.warning("서식의 원본 문서를 더 적지 못함 %s: %r", same.get("id"), e)
        return {**same, "existing": True}
    return _store(lambda: style_lib.create({**meta, "docx": {"losses": built[1]} if built else None}, data, files))


def _copy_job():
    """「문서 서식 복사」 의 할 일 프롬프트(`jobs/style_copy.md` — spec_서식복사 ② §6) | None. 후보에 이름을 붙이는 LLM 호출(에이전트 추출 ①)은 그 작업의 TASK 가 무엇이든 이 일을 하는 것이라 늘 이 글을 붙인다."""
    from app import job_prompts
    return job_prompts.get("style_copy")


def _look_key(meta, docx_sha):
    """「같은 서식」 의 열쇠 — 종류 + docx 운반 문서의 해시(형식 중립 명세에서 지은 것이라 **겉모습·라벨·견본이 같으면 같은 바이트**: `style_docx` 가 zip 시각을 고정한다) +
    운반 문서에 안 든 뜻(띠 수 · 구조가 있나). 이름·원본 문서는 넣지 않는다(다른 문서의 같은 서식도 하나로)."""
    return (meta.get("kind"), docx_sha, json.dumps(meta.get("bands"), sort_keys=True), bool(meta.get("blueprint")), meta.get("role"))  # role = 문단 서식의 역할(② §12 — 같은 모양이라도 역할이 다르면 다른 서식)


def _same_look(meta, docx: bytes):
    """보관함에 이미 있는 같은 서식의 meta | None(spec_서식복사 ② §4 「같은 서식은 한 번만」). docx 운반 문서를 못 지은 서식은 견주지 않는다(늘 새로 저장)."""
    import hashlib
    key = _look_key(meta, hashlib.sha256(docx).hexdigest())
    for m in style_lib.listing()["styles"]:
        if isinstance(m.get("docx"), dict) and _look_key(m, m["docx"].get("sha256")) == key:
            return m
    return None


def _docx_bytes(sid, meta):
    """그 템플릿의 docx 운반 문서 바이트 | None(못 지음). 옛 템플릿(carrier.docx 없음 · 손상)은 **그 자리에서 지어 그 revision 에 붙인다**(`style_lib.put_docx` — revision 번호는 그대로)."""
    data = style_lib.carrier(sid, meta["revision"], fmt="docx")
    if data is not None:
        return data
    built = _build_docx(meta, style_lib.carrier(sid, meta["revision"]))
    if built is None:
        return None
    try:
        style_lib.put_docx(sid, meta["revision"], built[0], built[1])
    except OSError as e:  # 붙이지 못해도 지은 것은 돌려준다
        log.warning("docx 운반 문서를 보관함에 붙이지 못함 %s: %r", sid, e)
    return built[0]


def _page_name(doc_name) -> str:
    """쪽 설정(문서 서식)의 기본 이름 — 「<문서 이름>: page」(spec_서식복사 ② §19-2 — 문서 이름 = 파일 이름의 문서 종류 낱말 `format_names.doc_prefix` · 60자까지).
    문서에서 저장할 때는 `_auto_name` 이 그 작업의 문서 이름(사람이 고친 것)·고친 이름으로 다시 짓는다."""
    return format_names.name(format_names.doc_prefix(doc_name), "page")


def _cover_name(doc_name) -> str:
    """표지 서식의 기본 이름 — 「<문서 이름>: cover」(spec_서식복사 ② §19-2 — 전에는 「<문서 이름> 표지」)."""
    return format_names.name(format_names.doc_prefix(doc_name), "cover")


# ---- 서식 이름(spec_서식복사 ② §19-2 — 「<문서 이름>: <갈래><번호>」: `app/format_names.py`) ------------------------------------------

def _given(name) -> bool:
    """요청이 이름을 실었나(빈 글 · 공백만은 안 실은 것 — 기본 이름을 붙인다)."""
    return isinstance(name, str) and bool(name.strip())


def _naming(s) -> tuple:
    """세션 문서의 (문서 이름, {이름 키: 사람이 고친 이름}) — 서식 지도의 문서별 저장(`format_names.prefix_of`·`load` — 작업 폴더의 formats.json)에서. 파일을 읽으므로 **잠금 밖에서**.
    못 읽으면 (파일 이름의 문서 종류 낱말, {})."""
    try:
        return format_names.prefix_of(s.id, s.name)[0], dict(format_names.load(s.id).get("names") or {})
    except Exception as e:  # noqa: BLE001 — 이름 저장을 못 읽는 것이 후보·저장을 막지 않는다
        log.info("서식 이름 저장을 읽지 못함 %s: %r", getattr(s, "id", None), e)
        return format_names.doc_prefix(getattr(s, "name", "")), {}


def _name_cands(cands) -> dict:
    """이름 짓기에 쓰는 후보 — 다섯 종류마다 사전이고 key 가 있는 것만(쪽 설정·표지는 key 가 없어도 — `format_names.keys_for` 가 「page」·「cover」 로 본다)."""
    cands = cands if isinstance(cands, dict) else {}
    return {g: [c for c in cands.get(g) or [] if isinstance(c, dict) and (c.get("key") or g in ("pages", "covers"))] for g in GROUPS}


def _with_names(cands, prefix, names=None) -> dict:
    """후보 사전 → 후보마다 `defaultName`(spec_서식복사 ② §19-2 ⓑ — `format_names.default_names`: 서식 지도에서 사람이 고친 이름이 있으면 그것) 을 더한 **새** 사전.
    원본 후보(세션 기억 `_memo` 의 것 · 잡아 둔 파일의 entry)는 안 바꾼다. 템플릿 번호가 없는 옛 그래프의 내용 서식 후보는 「T<차례>」."""
    clean = _name_cands(cands)
    try:
        got = format_names.default_names(clean, prefix, names)
    except Exception as e:  # noqa: BLE001 — 꼴이 틀린 후보 하나가 후보 응답을 막지 않는다
        log.warning("서식 후보의 기본 이름을 짓지 못함: %r", e)
        got = {}
    out = dict(cands) if isinstance(cands, dict) else {}
    for g in GROUPS:
        rows = []
        for n, c in enumerate((cands or {}).get(g) or [], 1):
            if not isinstance(c, dict):
                rows.append(c)
                continue
            grp = NAME_GROUP[g]
            nm = got.get((grp, c.get("key") or (grp if grp in ("page", "cover") else None)))
            if nm is None and grp == "text":
                nm = format_names.name(prefix, format_names.tpl_tail(n))
            rows.append({**c, "defaultName": nm} if nm else dict(c))
        out[g] = rows
    return out


def _tpl_anchor(t) -> str:
    """그래프 템플릿 t 의 이름 키 앵커 — 후보의 `template.anchor`(없으면 이름 · key)와 같은 값(`format_names.keys_for` 와 같은 차례)."""
    return t.get("anchor") or t.get("displayName") or t.get("name") or f"tpl{t.get('id')}"


def _para_group_of(s, groups, ids):
    """고른 문단들 가운데 문단 묶음 후보와 **서식이 같은** 첫 문단의 그 후보 | None — 묶음은 웹 블록의 서식 요약이 같은 문단끼리(`style_extract.para_groups`)라 같은 꼴로 견준다. 세션 잠금 안에서."""
    want = set(ids)
    sig = {b["id"]: json.dumps(b.get("format") or {}, ensure_ascii=False, sort_keys=True) for b in _all_blocks(s.doc.blocks()) if b.get("type") == "paragraph" and b.get("id") in want}
    by = {json.dumps(((c.get("items") or [{}])[0] or {}).get("format") or {}, ensure_ascii=False, sort_keys=True): c for c in reversed(groups)}
    return next((by[sig[i]] for i in ids if sig.get(i) in by), None)


def _auto_name(s, body, graph, prefix, names, t=None) -> str:
    """화면·에이전트가 이름을 안 보낸 저장의 기본 이름(spec_서식복사 ② §19-2 ⓒ·ⓓ) — 서식 복사 열 후보의 `defaultName` 과 같은 이름(사람이 서식 지도에서 고친 이름이 있으면 그것):
    쪽 설정 「page」 · 표지 「cover」 · 템플릿 「T<no>」(t = 그래프의 그 템플릿) · 표 · 문단 묶음은 그 문서 차례의 후보(`_doc_cands` — 화면이 본 것과 같은 차례)에서 그 대상이 든 후보의 번호.
    후보에 안 든 표·문단(1칸 표 · 12묶음 밖 서식 · 추출 모듈 없음)은 그 갈래의 다음 번호. **세션 잠금 안에서**(prefix·names 는 `_naming` 이 잠금 밖에서 읽어 둔다)."""
    kind, names = body.get("kind"), names or {}
    if kind in ("page", "cover"):
        return names.get(format_names.PAGE_KEY if kind == "page" else format_names.COVER_KEY) or format_names.name(prefix, kind)
    if t is not None:
        return names.get(format_names.tpl_key(_tpl_anchor(t))) or format_names.name(prefix, format_names.tpl_tail(t.get("no", t.get("id"))))
    se, cands = _mod("style_extract"), {}
    if se is not None:
        try:
            hit = _memo(s).get("cands")
            if kind == "table" and hit is None:  # 표의 번호는 표 후보만 본다(그래프와 무관 — 그래프를 짓지 않는다)
                cands = {"tables": se.table_candidates(s.doc.blocks())}
            else:
                cands = hit[1] if hit is not None and kind == "table" else _doc_cands(s, se, graph)[0]
        except Exception as e:  # noqa: BLE001 — 후보를 못 찾아도 저장은 된다(다음 번호의 기본 이름)
            log.info("기본 이름의 후보를 찾지 못함 %s: %r", s.id, e)
            cands = {}
    clean = _name_cands(cands)
    try:
        got = format_names.default_names(clean, prefix, names)
    except Exception:  # noqa: BLE001
        got = {}
    if kind == "table":
        tid = body.get("table")
        c = next((c for c in clean["tables"] if c.get("key") == tid or tid in (c.get("same") or [])), None)
        return (got.get(("table", c["key"])) if c is not None else None) or format_names.name(prefix, f"table{len(clean['tables']) + 1}")
    ids = [i for i in body.get("paras") or [] if isinstance(i, str)]
    keys = {c["key"]: c for c in clean["paras"]}
    c = next((keys[i] for i in ids if i in keys), None) or (_para_group_of(s, clean["paras"], ids) if clean["paras"] and ids else None)
    if c is not None and got.get(("para", c["key"])):
        return got[("para", c["key"])]
    tail = format_names.para_tail(body.get("role"))
    return format_names.name(prefix, f"{tail}{sum(1 for x in clean['paras'] if format_names.para_tail(x.get('role')) == tail) + 1}")


# ---- 세션마다의 작은 기억(견본은 잦게 불린다 — spec_서식복사 ② §13) -------------------------------------------------------------

_MEMO, _MEMO_LOCK = OrderedDict(), threading.Lock()  # 문서 id → {"s": 세션(약한 참조), "rev", "graph"?, "cands"?, "previews": {몸: 답}} — MEMO_DOCS 개까지


def _memo(s) -> dict:
    """세션 s 의 기억 — **그 세션 객체 · 그 문서 차례(rev)** 의 것만(문서가 바뀌었거나 세션을 다시 열었으면 새로 시작한다). 넣는 것: `graph`(스크립트 그래프 — 2단계가 없는 문서) ·
    `cands`(그 차례의 후보 — 쪽 설정 저장·견본이 화면이 본 후보와 같은 것을 쓰게) · `previews`(견본 답). 서버 메모리에만(MEMO_DOCS 문서)."""
    with _MEMO_LOCK:
        e = _MEMO.get(s.id)
        if e is None or e["s"]() is not s or e["rev"] != s.rev:
            try:
                ref = weakref.ref(s)
            except TypeError:  # 약한 참조를 못 거는 세션 객체(시험의 가짜) — 그 객체를 그대로 쥔다
                ref = (lambda s=s: s)
            e = _MEMO[s.id] = {"s": ref, "rev": s.rev, "previews": OrderedDict()}
        _MEMO.move_to_end(s.id)
        while len(_MEMO) > MEMO_DOCS:
            _MEMO.popitem(last=False)
        return e


def _doc_graph(s, graph, fresh=False):
    """hwpx 세션의 헤딩 그래프 → (그래프 | None, stage2 = True(2단계 결과) | "script"(그 자리에서 스크립트로 지음 — 저장 안 함) | False(못 지음)). **세션 잠금 안에서.**
    graph = 잠금 밖에서 읽은 2단계 그래프(`heading_runs.graph(s)`) | None. 스크립트 그래프는 그 문서 차례에 한 번만 짓는다(`_memo`) — fresh 면 다시(후보 찾기: 헤딩 규칙이 그 사이 바뀌었을 수 있다)."""
    if graph is not None:  # 사람이 「템플릿 관계」 에서 정한 레벨 대표(개요 오버레이 — spec_hwpx_웹편집 ② §8-2)가 있으면 내용 서식 후보도 그 줄에서
        from app import outline_match
        return outline_match.apply_reps(graph, getattr(s, "outline", None)), True
    memo = _memo(s)
    if not fresh and "graph" in memo:
        return memo["graph"]
    script, out = getattr(_mod("style_extract"), "script_graph", None), (None, False)
    if script is not None:  # 2단계가 아직 없다 — 스크립트만으로 그래프를 짓는다(LLM 없음 · 저장 안 함)
        try:
            out = (script(s.doc, s.name, getattr(s, "doc_key", None)), "script")
        except Exception as e:  # noqa: BLE001 — 헤딩 추출이 못 읽는 문서: 표·문서 서식 후보만
            log.info("스크립트 그래프를 짓지 못함 %s: %r", s.id, e)
    memo["graph"] = out
    return out


def _doc_cands(s, se, graph, fresh=False):
    """세션 문서의 서식 후보(`style_extract.candidates`·`docx_candidates`) → (후보 사전, stage2). **세션 잠금 안에서.** 그 문서 차례·같은 그래프 출처(stage2)의 것은 기억해 둔 것을 쓴다 —
    쪽 설정의 저장·견본이 화면이 본 후보(바탕 글 후보 `bodies` 의 차례)와 같은 것을 쓰게. fresh(후보 찾기 끝점)면 늘 다시 찾는다. 틀린 문서는 ValueError."""
    if _is_docx(s):
        graph, stage2 = None, False
    else:
        graph, stage2 = _doc_graph(s, graph, fresh)
    memo = _memo(s)
    hit = memo.get("cands")
    if not fresh and hit is not None and hit[0] == stage2:
        return hit[1], stage2
    cands = se.docx_candidates(s.doc) if _is_docx(s) else se.candidates(s.doc, graph)
    cands = cands if isinstance(cands, dict) else {}
    memo["cands"] = (stage2, cands)
    return cands, stage2


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
    return {"enabled": style_lib.enabled(), "pdf": pdf_render.available("hwpx"), "pdfDocx": pdf_render.available("docx"), "broken": got["broken"],  # pdfDocx = Word 출력이 되나(spec_서식복사 ② §8)
            "styles": [{**m, "losses": len(m.get("losses") or []), "blueprint": bool(m.get("blueprint")), "verify": _verify(m, full=False),
                        "docx": isinstance(m.get("docx"), dict), "verifyDocx": _verify(m, full=False, fmt="docx"),
                        **({"role": m.get("role"), "leveled": style_lib.leveled(m)} if m.get("kind") == "text" else {})}  # 글 서식의 갈래(② §12): leveled = 내용 서식 · 아니면 문단 서식(role = 역할 | null)
                       for m in got["styles"]]}


def _fmt(value) -> str:
    """요청의 format(hwpx | docx — 없으면 hwpx). 그 밖은 400."""
    if value in (None, ""):
        return "hwpx"
    if value not in FORMATS:
        raise HTTPException(400, f"format 은 {' 또는 '.join(FORMATS)}")
    return value


@router.get("/api/styles/{sid}")
def style_get(sid: str):
    """{...meta(verify·verifyDocx 는 기록 전체 + stale · docx = {sha256, losses} | null), view} — view = 표: {table, grid(글 전체), spec} · 글: {paras, items} ·
    문서 서식: {page, body, summary}(`style_carrier.view`), 운반 문서를 못 읽으면 null + viewError."""
    meta = _meta(sid)
    try:
        view, err = style_carrier.view(style_lib.carrier(sid) or b"", meta), None
    except ValueError as e:
        view, err = None, str(e)
    return {**_full(meta), "view": view, **({"viewError": err} if err else {})}


@router.get("/api/styles/{sid}/proof.png")
def style_proof(sid: str, fmt: str | None = Query(None, alias="format"), full: str | None = None):
    """검증 견본 그림 — ?format=hwpx(기본 · 한글) | docx(Word: `proof_docx.png`).
    ?full=1(spec_서식복사 ② §13 — 쪽 설정·표지): 내용 둘레를 자르지 않은 **첫 쪽 전체**를 그 revision 의 `proof.pdf`(`proof_docx.pdf`)에서 **그 자리에서 다시 그려** 돌려준다(저장된 그림은 덮어쓰지 않는다 —
    전에 저장한 쪽 설정의 그림은 내용 둘레로 잘려 있다). PDF 가 없거나 다시 그리지 못하면 저장된 그림 그대로."""
    _meta(sid)
    fmt = _fmt(fmt)
    if full not in (None, "", "0", "false"):
        sv, pdf = _mod("style_verify"), style_lib.file(sid, "proof_docx.pdf" if fmt == "docx" else "proof.pdf")
        if pdf is not None and hasattr(sv, "proof_png"):
            try:
                png = sv.proof_png(pdf.read_bytes(), full=True)
            except Exception as e:  # noqa: BLE001 — 깨진 PDF · 옛 검증 모듈(full 을 모름): 저장된 그림으로
                log.info("첫 쪽 전체 그림을 다시 그리지 못함 %s: %r", sid, e)
                png = None
            if png:
                return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
    p = style_lib.file(sid, "proof_docx.png" if fmt == "docx" else "proof.png")
    if p is None:
        raise HTTPException(404, "검증 그림이 아직 없습니다")
    return Response(p.read_bytes(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/api/styles/{sid}/carrier")
def style_carrier_file(sid: str, fmt: str | None = Query(None, alias="format")):
    """운반 문서 내려받기 — ?format=hwpx(기본 — 한글에서 열어 서식을 눈으로 볼 수 있다) | docx(Word 서식: 없으면 그 자리에서 지어 붙인 뒤 돌려준다 — 못 지으면 422)."""
    meta, fmt = _meta(sid), _fmt(fmt)
    data = _docx_bytes(sid, meta) if fmt == "docx" else style_lib.carrier(sid)
    if data is None:
        if fmt == "docx":
            raise HTTPException(422, "이 서식은 docx 서식으로 짓지 못했습니다")
        raise HTTPException(404, "운반 문서가 없습니다")
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", meta["name"]).strip("_") or sid
    return Response(data, media_type=MIME[fmt], headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}.{fmt}", "Cache-Control": "no-store"})


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
    """{expectedRevision, name?, note?, bands?, blueprint?, items?: [{key, name?, level?}], role?} → meta(새 revision). 운반 문서는 그대로(검증 기록도 물려받는다 —
    띠 수·blueprint·items 가 바뀌면 `verify.stale`). expectedRevision 은 **꼭** — 없거나 revision 꼴이 아니면 400, 지금과 다르면 409.
    role = 문단 서식의 역할(spec_서식복사 ② §12 — body·caption·note·box·toc·other | null: 레벨 없는 글 서식만, 그 밖의 서식·틀린 값은 400). 문서 서식·표지 서식은 이름·메모만."""
    meta, ch = _meta(sid), {}
    expected = _expected(body.get("expectedRevision"))
    for k in ("name", "note"):
        if k in body:
            ch[k] = body[k]
    table, text = meta["kind"] == "table", meta["kind"] == "text"
    if not table and not text and any(body.get(k) is not None for k in ("bands", "blueprint", "items")):  # 문서 서식(spec_서식복사 ② §8)·표지 서식(§14) — 쪽 설정·바탕 글·부분은 운반 문서와 짝이라 못 고친다
        raise HTTPException(400, f"{'표지' if meta['kind'] == 'cover' else '문서'} 서식은 이름·메모만 고칩니다")
    if any(body.get(k) is not None for k in (("items",) if table else ("bands", "blueprint"))):
        raise HTTPException(400, "표 서식은 bands·blueprint, 글 서식은 items 만 고칩니다")
    if table and body.get("bands") is not None:
        ch["bands"] = table_make.clean_roles(body["bands"], meta["rows"], meta["cols"], default=meta.get("bands"))
    if table and "blueprint" in body:
        ch["blueprint"] = _blueprint_in(body["blueprint"], meta)
    if text and body.get("items") is not None:
        ch["items"] = _items_in(body["items"], meta)
    if "role" in body:  # 문단 서식의 역할(spec_서식복사 ② §12) — 레벨 없는 글 서식만(이 요청으로 레벨을 붙이는 것도 안 된다). 그 밖은 400
        if not text or style_lib.leveled({"kind": "text", "items": ch.get("items", meta.get("items"))}):
            raise HTTPException(400, "role 은 문단 서식(레벨 없는 글 서식)만 고칩니다")
        ch["role"] = _role(body["role"])
    return _full(_store(lambda: style_lib.revise(sid, expected, ch)))


def _role(value):
    """요청의 role(문단 서식의 역할 — spec_서식복사 ② §12) → 정해진 코드(`style_lib.ROLES`) | None(모름). 그 밖은 400."""
    if value is None:
        return None
    if not isinstance(value, str) or value not in style_lib.ROLES:
        raise HTTPException(400, f"role 은 {'·'.join(style_lib.ROLES)} 중 하나 또는 null")
    return value


def _edit_changes(given) -> dict:
    """「값 고치기」 요청의 changes → 검사한 값 {키: 값}(준 것만 — spec_서식복사 ② §19-7). 모르는 키 · 범위 밖 · 빈 것 · 앞 여백과 글 시작을 함께 준 것은 400."""
    if not isinstance(given, dict) or not given:
        raise HTTPException(400, f"changes 는 {{{', '.join(EDIT_KEYS)}}} 가운데 1개 이상")
    if bad := set(given) - set(EDIT_KEYS):
        raise HTTPException(400, f"changes 에 모르는 값이 있습니다: {', '.join(sorted(bad))}")
    out = {}
    for k, v in given.items():
        if k == "font":
            name = re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else ""
            if not 1 <= len(name) <= FONT_MAX:
                raise HTTPException(400, f"font 는 1~{FONT_MAX}자의 글꼴 이름")
            out[k] = name
            continue
        lo, hi = EDIT_NUMS[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not lo <= v <= hi:
            raise HTTPException(400, f"{k} 는 {lo}~{hi} 의 수")
        out[k] = int(round(v)) if k == "lineSpacingPct" else round(float(v), 2)
    if "line1Mm" in out and "textMm" in out:
        raise HTTPException(400, "line1Mm(앞 여백)과 textMm(글 시작)은 하나만 보냅니다 — 글 시작 = 앞 여백 + 레터 자리 폭")
    return out


@router.put("/api/styles/{sid}/items/{key}/format")
def style_item_format(sid: str, key: str, body: dict = Body(...)):
    """「값 고치기」(spec_서식복사 ② §19-6) — {expectedRevision, changes: {line1Mm? | textMm?, line2Mm?, font?, sizePt?, lineSpacingPct?}} → 새 revision 의 meta.
    운반 문서(hwpx)의 그 항목 견본 문단을 고치고(`style_carrier.retune` — 글자 값은 본문 런만) `items[].format` 을 다시 읽는다 · docx 운반 문서를 다시 짓는다 · PDF 검증을 다시 건다.
    글 서식만(400) · 없는 항목 404 · revision 이 다르면 409 · 틀린 값·못 넣는 값 400. 문서는 안 바뀐다(보관함의 서식만)."""
    meta = _meta(sid)
    expected = _expected(body.get("expectedRevision"))
    if meta.get("kind") != "text":
        raise HTTPException(400, "값 고치기는 글 서식(내용 서식 · 문단 서식)만 됩니다")
    if not any(isinstance(it, dict) and it.get("key") == key for it in meta.get("items") or []):
        raise HTTPException(404, "그 항목이 이 서식에 없습니다")
    changes = _edit_changes(body.get("changes"))
    if expected != meta["revision"]:  # 운반 문서를 고치기 전에 — 저장소도 같은 것을 다시 본다
        raise HTTPException(409, f"서식이 그 사이 바뀌었습니다(지금 {meta['revision']} · 요청 {expected}) — 다시 읽어 주세요")
    try:
        data, items = style_carrier.retune(style_lib.carrier(sid) or b"", meta, key, changes)
    except KeyError as e:
        raise HTTPException(404, "그 항목이 이 서식에 없습니다") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    built = _build_docx({**meta, "items": items}, data)  # docx 운반 문서도 같은 값으로 다시(못 지으면 docx: null — 저장은 된다)
    files = {style_lib.CARRIER_DOCX: built[0]} if built else None
    new = _store(lambda: style_lib.revise(sid, expected, {"items": items, "docx": {"losses": built[1]} if built else None}, carrier=data, files=files))
    _kick(sid)  # 운반 문서가 바뀌었다 — 두 형식 다시 검증(전 검증 기록은 앞 revision 에 남는다)
    return _full(style_lib.get(sid) or new)


@router.post("/api/styles/{sid}/copy")
def style_copy(sid: str, body: dict = Body(default={})):
    """「복사본 만들기」(spec_서식복사 ② §19-6) — {name?} → 새 서식의 meta(201). 같은 운반 문서·같은 값 · 이름 「<이름> 복사」(60자 안) · `copyOf` = 원래 서식 id ·
    원본 문서 기록(`source`·`seenIn`)은 물려받고 검증은 새로 건다. 「같은 서식은 한 번만」(② §4)을 지나지 않는다(사람이 일부러 만든 것)."""
    meta = _meta(sid)
    name = (body or {}).get("name")
    if name is None:
        name = f"{meta['name'][:style_lib.NAME_MAX - 3]} 복사"
    elif not isinstance(name, str) or not 1 <= len(re.sub(r"\s+", " ", name).strip()) <= style_lib.NAME_MAX:
        raise HTTPException(400, f"이름은 1~{style_lib.NAME_MAX}자")
    data = style_lib.carrier(sid)
    if not data:
        raise HTTPException(404, "운반 문서가 없습니다")
    docx = _docx_bytes(sid, meta)
    new = {k: v for k, v in meta.items() if k not in style_lib.OWN or k == "kind"}  # 저장소가 정하는 키(id·revision·때·검증 기록)는 새로 — 종류는 그대로
    new.update(name=name, copyOf=sid, docx={"losses": list((meta.get("docx") or {}).get("losses") or [])} if docx else None)
    out = _store(lambda: style_lib.create(new, data, {style_lib.CARRIER_DOCX: docx} if docx else None))
    _kick(out["id"])
    return JSONResponse(_full(style_lib.get(out["id"]) or out), status_code=201)


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
    """PDF 검증을 다시 건다(작업 — 화면은 `GET /api/styles/{sid}` 를 다시 읽는다) → 202 {status: "running", revision}. {force?: false} 가 아니면 PDF 캐시를 지우고 다시 출력.
    두 형식 모두(한글 → Word — spec_서식복사 ② §7·§8). {formats?: ["hwpx", "docx"]} 로 형식을 고를 수 있다(모르는 형식·빈 목록은 400)."""
    _meta(sid)
    if _mod("style_verify") is None:
        raise HTTPException(501, "PDF 검증 모듈(app.style_verify)이 없습니다")
    formats = (body or {}).get("formats")
    if formats is not None and (not isinstance(formats, list) or not formats or any(f not in FORMATS for f in formats)):
        raise HTTPException(400, f"formats 는 {'·'.join(FORMATS)} 가운데 1개 이상")
    rec = _kick(sid, force=(body or {}).get("force") is not False, formats=formats)
    if rec is None:
        raise HTTPException(503, "검증을 시작하지 못했습니다")
    return JSONResponse({**rec, "status": "running"}, status_code=202)


# ---- 문서에서: 후보 · 저장 --------------------------------------------------------------------------------------------

def _named(cands, res, doc_name=None) -> dict:
    """이름 붙이기(LLM — `style_extract.name`)의 답 {"tables": {후보 key: {name, keep, bands, bandsChanged}}, "texts": {key: {name, keep}}, "note", "call"} 을 후보 목록에 합친다
    -> {"tables", "texts", "paras", "pages", "covers", "note", "call", "calls"}. 답에 없는 후보는 그대로. 문서 서식 후보(pages)는 옛 `name` 이 묻지 않는다 — 문서에 하나라 추천(keep).
    2차(spec_서식복사 ② §15·§16): LLM 검토 `style_extract.review` 의 답은 **다섯 종류**(tables · texts · paras · pages · covers)마다 {후보 key: R} 이고, R 의 칸(`name`·`keep`·`role`·`bands`·
    `bandsChanged`·`bandsWider`·`rep`·`sameAs`·`bodyKey`·`isCover`·`end`·`roles`·`review` …)을 **그대로** 후보에 얹는다(재검사는 추출 모듈이 이미 했다). 쪽 설정 후보는 검토 답이 없어도
    추천(keep). 돌려주는 것에 `calls`(호출마다의 기록 — `call` 은 첫 호출: 옛 꼴)를 더한다.
    2026-11-14(spec_서식복사 ② §19-2): R 의 `name` 은 **설명**이다(화면이 후보 줄의 설명 · 저장하면 meta.note) — 서식의 이름은 후보의 `defaultName`(「<문서 이름>: <갈래><번호>」).
    그래서 쪽 설정·표지에 기본 이름을 `name` 으로 채우지 않는다(전에는 「<문서 이름> 문서 서식」·「<문서 이름> 표지」). `defaultName` 이 없는 후보에는 doc_name 의 문서 종류 낱말로 붙인다."""
    res = res if isinstance(res, dict) else {}
    if any(isinstance(c, dict) and "defaultName" not in c for k in GROUPS for c in cands.get(k) or []):  # 이미 붙은 기본 이름(작업의 문서 이름·고친 이름)은 그대로 — 없는 후보에만
        filled = _with_names(cands, format_names.doc_prefix(doc_name))
        cands = {**cands, **{k: [c if not isinstance(c, dict) or "defaultName" in c else f for c, f in zip(cands.get(k) or [], filled.get(k) or [])] for k in GROUPS}}
    out = {}
    for k in GROUPS:
        got = res.get(k) if isinstance(res.get(k), dict) else {}
        out[k] = [{**c, **got[c["key"]]} if isinstance(c, dict) and isinstance(got.get(c.get("key")), dict) else c for c in cands.get(k) or []]
    out["pages"] = [{**c, "keep": c.get("keep") is not False} for c in out["pages"] if isinstance(c, dict)]
    out["covers"] = [c for c in out["covers"] if isinstance(c, dict)]
    call = res.get("call")
    calls = [c for c in res.get("calls") or [] if isinstance(c, dict)] if isinstance(res.get("calls"), list) else ([call] if isinstance(call, dict) else [])
    return {**out, "note": str(res.get("note") or ""), "call": call, "calls": calls}


def _review(se, cands) -> dict:
    """후보의 LLM 검토 한 번(spec_서식복사 ② §15 — `style_extract.review(cands, job=)`: 추출 모듈이 아직 옛 것이면 같은 일의 옛 이름 `name`) → 그 답(사전). 할 일 프롬프트 `jobs/style_copy.md` 를 늘 붙인다."""
    res = (getattr(se, "review", None) or se.name)(cands, job=_copy_job())
    return res if isinstance(res, dict) else {}


def _hits(res) -> int:
    """검토 답이 닿은 후보 수(다섯 종류의 {key: R} 를 센다) — 0 이고 호출이 오류면 502."""
    return sum(len(res[k]) for k in GROUPS if isinstance(res.get(k), dict))


def _review_error(res, out):
    """검토 호출이 **모두** 실패했고 답이 닿은 후보가 하나도 없으면 그 오류 글 | None(일부라도 됐다 — 응답의 `calls` 에 오류가 그대로 보인다)."""
    errs = [c.get("error") for c in out["calls"]]
    return next((e for e in errs if e), None) if errs and all(errs) and not _hits(res) else None


@router.post("/api/docs/{doc_id}/styles/candidates")
def style_candidates(doc_id: str, body: dict = Body(default={})):
    """{llm?: false} → {rev, tables, texts, paras, pages, covers, format, fidelity, stage2, note?, call?, calls?} — 이 문서의 서식 후보 다섯 종류(스크립트 — 문서 안 바뀜: 테이블 · 내용(레벨 있는 글) ·
    문단 묶음 · 쪽 설정 · 표지 — spec_서식복사 ② §12·§16). llm true = **LLM 검토**(② §15 — `style_extract.review`: 이름 · 저장할 만한가 · 역할 · 의심 · 띠 수 · 대표 문단 · 바탕 글 · 표지 범위)의 결과를
    후보마다 합친다(누를 때만 — 잠금 밖, 동기 · `call` = 첫 호출(옛 꼴) · `calls` = 호출마다). hwpx · docx 문서(spec_서식복사 ② §6·§8).
    - hwpx: `fidelity: "native"` · stage2 = true(2단계 그래프가 있음) | "script"(없어서 그 자리에서 스크립트 그래프로 글 후보를 냄 — 저장 안 함) | false(그것도 못 냄 — 글 후보 없음).
    - docx: 파일 추출과 같은 규칙(표 = 명세로 다시 지음 · 글 = 서식이 같은 문단 묶음(레벨 없음)) · `fidelity: "summary"` · stage2 false.
    spec_서식복사 ② §19-2·§19-7: 후보마다 **`defaultName`**(「<문서 이름>: <갈래><번호>」 — 서식 지도에서 사람이 고친 이름·문서 이름이 있으면 그것: `format_names`) ·
    내용 서식 후보의 `template.anchor`(이름 키). LLM 검토 답의 `name` 은 **설명**이다(화면이 note 로)."""
    s = _sess(doc_id)
    se = _mod("style_extract")
    if se is None:
        raise HTTPException(501, "서식 추출 모듈(app.style_extract)이 없습니다")
    docx = _is_docx(s)
    graph = None if docx else heading_runs.graph(s)  # 작업 파일을 읽으므로 세션 잠금 밖에서
    prefix, names = _naming(s)  # 서식 지도의 문서 이름·고친 이름(작업 폴더 — 잠금 밖에서)
    with s.lock:
        try:
            cands, stage2 = _doc_cands(s, se, graph, fresh=True)  # 2단계가 아직 없는 hwpx 문서는 그 자리에서 스크립트 그래프로(`_doc_graph`) — 찾은 것은 그 문서 차례 동안 기억해 저장·견본이 같은 후보를 쓴다
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        rev = s.rev
    named = _with_names({k: cands.get(k) or [] for k in GROUPS}, prefix, names)  # 새 사전 — 기억해 둔 후보(`_memo`)는 안 바뀐다
    out = {"rev": rev, **{k: named[k] for k in GROUPS},  # paras = 문단 묶음 · covers = 표지(② §12·§14 — 옛 추출 모듈이 그 키를 안 내면 빈 목록) · 후보마다의 doubts 는 온 그대로
           "format": "docx" if docx else "hwpx", "fidelity": "summary" if docx else "native", "stage2": stage2}
    if (body or {}).get("llm") is True:
        from app import llm
        if not llm.status()["available"]:
            raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐) — 이름은 직접 붙일 수 있습니다")
        res = _review(se, cands)
        out.update(_named(out, res, s.name))
        call, calls = out["call"] if isinstance(out["call"], dict) else {}, out["calls"]
        detail = works.add_detail(s.id, "styles", f"name_{int(time.time() * 1000)}",  # 상세 기록 = 프롬프트·답 전부(호출이 여럿이면 prompts·responses·calls 까지)
                                  {"rev": rev, "call": call, **{k: res.get(k) for k in ("prompt", "response", "prompts", "responses", "calls", "job", "note") if res.get(k) is not None}})
        cost = [c.get("costUsd") for c in calls if isinstance(c.get("costUsd"), (int, float))]
        err = _review_error(res, out)
        works.log(s.id, "styleName", rev=rev, named=sum(1 for k in ("tables", "texts", "paras") for c in out[k] if c.get("name")), reviewed=_hits(res), calls=len(calls),
                  backend=call.get("backend"), ms=max([c.get("ms") for c in calls if isinstance(c.get("ms"), (int, float))], default=call.get("ms")),
                  costUsd=round(sum(cost), 6) if cost else call.get("costUsd"), error=err or call.get("error"), detail=detail)
        if err:
            raise HTTPException(502, f"LLM 이 이름을 붙이지 못했습니다: {err}")
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


def _rep_in(rep, t, g) -> dict:
    """템플릿 저장의 `rep`(spec_서식복사 ② §15·§16 — LLM 이 고른 대표 문단 {레벨: 문단 id}) → {레벨(정수): 문단 id}. 받는 것은 **그 템플릿 그 레벨의 문단**뿐이다 —
    그래프의 `nodes`(노드마다 para · template(앵커)·tplNo(템플릿 id) · level)로 확인한다. 꼴이 틀리거나 그 슬롯의 문단이 아니면 400(다른 문단의 서식이 그 레벨로 저장되지 않게)."""
    if rep is None:
        return {}
    if not isinstance(rep, dict) or not all(isinstance(v, str) and v for v in rep.values()):
        raise HTTPException(400, "rep 는 {레벨: 문단 id}")
    tid, anchor, levels, out = t.get("id", t.get("no")), t.get("anchor"), {int(sl["level"]) for sl in t.get("slots") or [] if isinstance(sl.get("level"), int)}, {}
    mine = {(n.get("level"), n.get("para")) for n in g.get("nodes") or [] if isinstance(n, dict)
            and ((n.get("tplNo") is not None and str(n.get("tplNo")) == str(tid)) or (anchor is not None and n.get("template") == anchor))}
    for k, pid in rep.items():
        try:
            level = int(k)
        except (TypeError, ValueError) as e:
            raise HTTPException(400, "rep 의 레벨은 정수") from e
        if level not in levels or (level, pid) not in mine:
            raise HTTPException(400, f"rep: {level}수준의 대표 문단은 그 템플릿 그 레벨의 문단 가운데서만 고릅니다")
        out[level] = pid
    return out


def _template_picks(s, g, tid, rep=None):
    """2단계 그래프 g 의 템플릿 tid → (템플릿, picks — 슬롯마다 대표 문단). 대표 서식이 없는 슬롯·대표 문단이 문서에 없는 슬롯은 뺀다. 그래프가 없으면 400. 세션 잠금 안에서.
    rep = {레벨: 문단 id}(요청의 `rep` — `_rep_in` 이 그 템플릿 그 레벨의 문단인지 본다): 준 레벨은 슬롯의 대표 문단 대신 그 문단을 쓴다."""
    if not g:
        raise HTTPException(400, "2단계(개요템플릿) 결과가 없습니다 — 헤딩 추출을 먼저 돌리거나, 문단을 골라 문단 서식으로 저장하세요")
    t = next((t for t in g.get("templates") or [] if str(t.get("id", t.get("no"))) == str(tid)), None)
    if t is None:
        raise HTTPException(404, "그 템플릿이 2단계 결과에 없습니다")
    picks, rep = [], _rep_in(rep, t, g)
    for slot in t.get("slots") or []:
        pid = rep.get(int(slot["level"]), slot.get("rep"))
        el = s.doc._ids.get(pid)
        if slot.get("format") and el is not None and el.tag == P and s.doc._attached(el):
            picks.append({"para": pid, "level": int(slot["level"]), "origin": {"template": t.get("id", t.get("no")), "slot": int(slot["level"])},
                          "name": f"{int(slot['level'])}수준 {slot.get('letter') or ''}".strip()})
    if any(pid not in {p["para"] for p in picks} for pid in rep.values()):  # 고른 대표 문단이 그 사이 지워졌다 — 말없이 그 레벨을 빼지 않는다
        raise HTTPException(404, "rep 로 고른 대표 문단이 지금 문서에 없습니다 — 후보를 다시 찾으세요")
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
    """문서의 표·문단 서식을 보관함에 저장(문서는 안 바뀜) → 201 meta(+ PDF 검증을 건다). 몸통 = `save_doc_style`."""
    _on()  # 보관함 끔(503)이 없는 문서(404)보다 먼저 — 전과 같은 차례
    return JSONResponse(_full(save_doc_style(_sess(doc_id), body)), status_code=201)


def save_doc_style(s, body: dict) -> dict:
    """세션 s 의 문서에서 서식 하나를 보관함에 저장(문서는 안 바뀜) → meta(PDF 검증을 건 뒤). 끝점 `POST /api/docs/{id}/styles` 와 에이전트의 「서식 복사」 반영(doc_agent_api —
    spec_서식복사 ② §6)이 같이 쓴다. 틀린 입력·없는 블록·보관함 끔은 HTTPException(400·404·503). 아래 세 꼴은 hwpx 문서의 것(docx 문서는 맨 끝 문단).
    {kind: "table", table, name?, bands?, keepText?, blueprint?: bool} | {kind: "text", template: 템플릿 id, name?, keepText?} | {kind: "text", paras: [ids], name?, keepText?}.
    표 meta 의 `labels` = 운반 문서에 글을 남긴 라벨 칸 [[행, 열]…](`style_carrier.label_cells`) — blueprint 의 label 은 그 칸의 글뿐이다.
    **기본 이름**(name 이 없거나 빈 글 — spec_서식복사 ② §19-2 ⓒ·ⓓ) = 「<문서 이름>: <갈래><번호>」(`_auto_name` — 서식 복사 열 후보의 `defaultName` 과 같은 이름 · 전의 「<첫 라벨> 표」·「템플릿 N 글 서식」·「문단 서식」 을 바꿈).
    note(설명 — 0~400자: LLM 검토의 설명이 여기로 온다)는 모든 종류가 받는다.
    고른 표·문단이 닿는 정의 참조가 끊어져 있으면 400(깨진 템플릿을 보관함에 넣지 않는다).
    spec_서식복사 ② §5·§6: + {kind: "page", name?}(문서 서식 — 쪽 설정 + 바탕 글 · 기본 이름 「<문서 이름>: page」) · **docx 문서**도 받는다(`_build_docx` — 표 = 명세로 다시 지음 ·
    글 = {kind: "text", paras} 문단의 서식 요약 · 문서 서식 · `fidelity: "summary"` · `template` 은 hwpx 만 400). 어느 쪽이든 docx 운반 문서를 함께 지어 넣는다(`_create`).
    2차(spec_서식복사 ② §16): 몸통 = **짓기** `build_doc_style`(운반 문서 + meta — 견본 끝점이 같이 쓴다) + 저장(`_create`) + 기록(`styleSave`) + 검증. 더 받는 몸은 `build_doc_style` 설명에."""
    _on()
    meta, data, rev = _build(s, body)
    out = _create(meta, data)
    works.log(s.id, "styleSave", rev=rev, style=out["id"], styleKind=meta["kind"], name=out["name"], block=out["source"]["block"], keepText=body.get("keepText") is True,
              blueprint=bool(out.get("blueprint")), losses=len(out["losses"]), docx=bool(out.get("docx")), **({"format": "docx"} if _is_docx(s) else {}))
    if not out.get("existing"):  # 이미 있던 같은 서식 — 검증 기록이 있다(다시 걸지 않는다)
        _kick(out["id"])
    return out


def build_doc_style(s, body: dict) -> tuple[dict, bytes]:
    """세션 s 의 문서에서 서식 하나를 **짓기만** 한다(spec_서식복사 ② §13·§16) → (meta — `_create` 가 받는 꼴: note·fidelity 까지, hwpx 운반 문서 바이트). 보관함에 쓰지 않고 검증도 걸지 않으며
    docx 운반 문서도 짓지 않는다(문서도 안 바뀐다) — 저장(`save_doc_style`)과 견본(`POST …/styles/preview`)이 **같은 생성 함수**를 쓰게 뗀 것이다. hwpx·docx 세션 모두. 틀린 입력·없는 블록은 HTTPException.
    몸(저장과 같은 꼴): {kind: "table", table, name?, bands?, keepText?, blueprint?} | {kind: "text", template, name?, keepText?, rep?: {레벨: 문단 id}} | {kind: "text", paras, name?, keepText?, role?} |
    {kind: "page", name?, bodyKey?} | {kind: "cover", end?, roles?: {블록 id: 역할}, name?, keepText?}.
    - `role`(② §12): 문단 서식의 역할 코드(`style_lib.ROLES`) | null — 틀린 값·템플릿 저장에 준 것은 400.
    - `rep`(② §15): 템플릿의 그 레벨 대표 문단을 다른 문단으로 — 그래프의 그 템플릿 그 레벨 노드일 때만(`_rep_in`).
    - `bodyKey`(② §12): 쪽 설정의 바탕 글을 후보의 `bodies` 가운데 그 key 의 서식으로 · "none" = 바탕 글 없음 · 모르는 key 400.
    - 표지(② §14): 범위 = 그때의 표지 후보(`style_cover.find(문서, 그래프)`) — `end` 가 오면 그 블록까지 줄이고(`shrink`: 범위 밖이면 400), 후보가 없으면 400 「이 문서에서 표지를 찾지 못했습니다」.
      기본 이름 「<문서 이름>: cover」. 표지 모듈이 없으면 501.
    - name 이 없으면 기본 이름(`_auto_name` — spec_서식복사 ② §19-2)."""
    meta, data, _ = _build(s, body)
    return meta, data


def _build(s, body: dict, named=True):
    """`build_doc_style` 의 몸 → (meta, 운반 문서 바이트, 지은 때의 문서 차례 rev). named = 이름이 없을 때 기본 이름을 짓나(spec_서식복사 ② §19-2 — `_auto_name`):
    견본(`POST …/styles/preview`)은 이름을 안 쓰므로 False(후보를 찾지 않는다 — 파일 이름의 문서 종류 낱말로 지은 대강의 이름)."""
    if not isinstance(body, dict):
        raise HTTPException(400, "요청 몸은 {kind, …}")
    kind, keep = body.get("kind"), body.get("keepText") is True
    if kind not in style_lib.KINDS:
        raise HTTPException(400, f"kind 는 {' · '.join(style_lib.KINDS)} 중 하나")
    by_template = kind == "text" and body.get("template") is not None
    role = _role(body.get("role")) if kind == "text" else None
    if by_template and role is not None:
        raise HTTPException(400, "role 은 문단 서식(paras)에만 붙입니다 — 개요템플릿의 글 서식에는 역할이 없습니다")
    if body.get("rep") is not None and not by_template:
        raise HTTPException(400, "rep 는 개요템플릿 저장({kind: \"text\", template})에만 씁니다")
    auto = not _given(body.get("name"))  # 이름이 없다 — 기본 이름(② §19-2)
    naming = _naming(s) if auto and named else None  # 서식 지도의 문서 이름·고친 이름(작업 폴더 — 잠금 밖에서)
    if _is_docx(s):
        return _build_from_docx(s, body, kind, keep, role, naming)
    # 그래프(작업 파일)는 잠금 밖에서 읽는다 — 기본 이름을 지을 때도(문단 묶음의 번호 = 화면이 본 후보의 차례: 같은 그래프 출처의 후보를 써야 한다)
    graph = heading_runs.graph(s) if by_template or kind in ("page", "cover") or naming else None
    src0 = _src(s, "hwpx")  # 원본 기록(② §17) — 작업 기록(파일)을 읽으므로 잠금 밖에서
    t = None
    try:
        with s.lock:
            src = dict(src0)
            if kind == "table":
                from app import tables_api
                tid = body.get("table")
                block = tables_api._live_table(s, tid, "서식으로 저장할 표")
                bands = table_make.clean_roles(body.get("bands"), block["nRows"], block["nCols"], default=table_make.roles_of(block["cells"], block["nRows"], block["nCols"]))
                data, info = style_carrier.from_table(s.doc, tid, bands, keep_text=keep)
                labels = _label_texts(data, info)
                meta = {"kind": "table", "name": body.get("name"), "source": {**src, "block": tid, "where": _table_where(s, tid)},
                        "losses": info["losses"], "requirements": {"fonts": info["fonts"]}, "bands": info["bands"], "rows": info["rows"], "cols": info["cols"], "labels": info["labels"],
                        "blueprint": _blueprint(s, tid, block, labels) if body.get("blueprint") is True else None, "preview": info["preview"]}
            elif kind == "page":
                data, meta = _page_meta(s, "hwpx", body, src, graph)
            elif kind == "cover":
                data, meta = _cover_meta(s, body, src, _doc_graph(s, graph)[0], keep)
            else:
                if by_template:  # 2단계 결과가 아직 없는 문서 — 후보 끝점이 스크립트 그래프로 낸 템플릿(stage2 "script")은 저장도 같은 그래프로(실측 2026-11-14: 후보는 나오는데 저장이 400)
                    graph = _doc_graph(s, graph)[0]  # 못 지으면 None — 아래 _template_picks 가 400 으로 알린다
                t, picks = _template_picks(s, graph, body["template"], body.get("rep")) if by_template else (None, _para_picks(s, body.get("paras")))
                data, items = style_carrier.from_paras(s.doc, picks, keep_text=keep)
                meta = {"kind": "text", "name": body.get("name"), "source": {**src, "block": picks[0]["para"], "where": f"개요템플릿 {t.get('no', t.get('id'))}" if t else f"문단 {len(picks)}개"},
                        "losses": [style_carrier.STYLE_NOTE], "requirements": {"fonts": style_carrier.fonts_of(style_carrier.doc(data))}, "items": items, "role": role}
            if auto:  # 기본 이름(② §19-2 ⓒ·ⓓ) — 서식 복사 열 후보의 defaultName 과 같은 이름 · 견본은 대강(파일 이름의 문서 종류 낱말)
                meta["name"] = _auto_name(s, body, graph, *naming, t=t) if naming else _rough_name(s.name, kind, t)
            rev = s.rev
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {**meta, "note": body.get("note") or "", "fidelity": "native"}, data, rev


def _rough_name(doc_name, kind, t=None) -> str:
    """기본 이름의 대강(번호를 후보에서 찾지 않는다 — 견본처럼 이름을 안 쓰는 곳): 「<파일 이름의 문서 종류 낱말>: page·cover·T<no>·table1·body1」."""
    tail = {"page": "page", "cover": "cover", "table": "table1"}.get(kind) or (format_names.tpl_tail(t.get("no", t.get("id"))) if t is not None else "body1")
    return format_names.name(format_names.doc_prefix(doc_name), tail)


def _page_meta(s, fmt, body, src, graph=None):
    """세션 문서의 문서 서식(쪽 설정 + 본문 바탕 글 모양 — spec_서식복사 ② §5) → (hwpx 운반 문서 바이트, meta 의 일부). 쪽 설정을 못 읽으면 400, 추출 모듈이 없으면 501.
    세션 잠금 안에서. 기본 이름 「<문서 이름(확장자 뺌)> 문서 서식」.
    쪽 설정 후보는 **후보 끝점이 낸 그것**을 쓴다(`_doc_cands` — 그 문서 차례에 찾아 둔 것, 없으면 같은 함수로 다시: 바탕 글 후보 `bodies` 의 차례·헤딩을 뺀 셈이 화면이 본 것과 같게).
    `bodyKey`(② §12): 그 후보의 `bodies` 가운데 그 key 의 서식을 바탕 글로 · "none" = 바탕 글 없음 · 모르는 key 는 400."""
    se = _extract()
    hit, heads = _memo(s).get("cands"), getattr(se, "head_paras", None)
    if hit is not None:  # 후보 끝점이 이 문서 차례에 찾아 둔 것 — 화면이 본 그 후보
        pages = hit[1].get("pages")
    elif heads is not None and hasattr(se, "page_candidates"):  # 찾아 둔 것이 없다(에이전트 반영 등) — `candidates` 가 하는 셈 그대로 쪽 설정만(헤딩 노드의 문단을 바탕 글에서 뺀다: 표 후보까지 다 찾지 않는다)
        pages = se.page_candidates(fmt, s.doc) if fmt == "docx" else se.page_candidates(fmt, s.doc, heads(_doc_graph(s, graph)[0]))
    else:
        pages = _doc_cands(s, se, graph)[0].get("pages")
    cands = [c for c in pages or [] if isinstance(c, dict)]
    if not cands:
        raise HTTPException(400, "이 문서에서 쪽 설정을 읽지 못했습니다(문서 서식 모듈이 없거나 구역 설정이 없는 문서)")
    cand, key = cands[0], body.get("bodyKey")
    if key == "none":
        cand = {**cand, "body": None}
    elif key is not None:
        bodies = cand.get("bodies")
        if not isinstance(bodies, list):  # 옛 추출 모듈(후보에 bodies 가 없다) — 문서 서식 모듈에서 바로 읽는다(`style_page.of_hwpx`·`of_docx` 의 bodies)
            fn = getattr(_mod("style_page"), "of_docx" if fmt == "docx" else "of_hwpx", None)
            got = fn(s.doc) if fn is not None else None
            bodies = got.get("bodies") if isinstance(got, dict) else None
        pick = next((b for b in bodies or [] if isinstance(b, dict) and b.get("key") == key and isinstance(b.get("format"), dict)), None)
        if pick is None:
            raise HTTPException(400, "bodyKey: 이 문서의 바탕 글 후보에 없는 key 입니다(후보의 bodies 가운데 하나 또는 \"none\")")
        cand = {**cand, "body": {"format": pick["format"], "count": pick.get("count")}}
    data, part = se.build_page(cand)  # 틀린 값은 ValueError → 부르는 쪽이 400
    return data, {**part, "name": body.get("name") or _page_name(s.name), "source": {**src, "block": None}}


def _cover_meta(s, body, src, graph, keep):
    """세션 문서의 표지 서식(spec_서식복사 ② §14) → (hwpx 운반 문서 바이트, meta 의 일부 {kind: "cover", name, source, losses, requirements, page, parts}). 세션 잠금 안에서.
    범위 = **그때의** 표지 후보(`style_cover.find(문서, 그래프)` — hwpx·docx 문서) · `end`(블록 id)가 오면 그 블록까지 줄인다(`shrink` — 범위 밖이면 400: 줄이는 쪽만) ·
    `roles`({블록 id: 역할 코드} — `style_cover.ROLES` 의 코드만, 범위 밖 블록의 것은 버린다) · 글은 역할 견본으로(`keepText` 면 원문). 후보가 없으면 400, 표지 모듈이 없으면 501.
    기본 이름 「<문서 이름(확장자 뺌)> 표지」."""
    sc = _mod("style_cover")
    if sc is None:
        raise HTTPException(501, "표지 서식 모듈(app.style_cover)이 없습니다")
    cand = sc.find(s.doc, graph)
    if not isinstance(cand, dict) or not cand.get("blocks"):
        raise HTTPException(400, NO_COVER)
    cand = _cover_range(sc, cand, body.get("end"))
    data, info = sc.carrier(s.doc, list(cand["blocks"]), roles=_cover_roles(sc, cand, body.get("roles")), keep_text=keep)
    return data, _cover_part(info, body.get("name") or _cover_name(s.name), {**src, "block": cand["blocks"][0], "where": "첫 쪽"})


def _cover_range(sc, cand, end):
    """표지 후보 cand 를 `end`(블록 id — 없으면 그대로)까지 줄인 것. 범위 밖 블록·틀린 꼴은 400(범위를 넓히는 길은 없다 — ② §15)."""
    if end is None:
        return cand
    got = sc.shrink(cand, end) if isinstance(end, str) else None
    if not isinstance(got, dict) or not got.get("blocks"):
        raise HTTPException(400, "end: 표지 범위 안의 블록 id 가 아닙니다(범위는 줄이기만 합니다)")
    return got


def _cover_roles(sc, cand, roles):
    """요청의 roles({블록 id: 역할}) → 표지 범위 안 블록의 것만 | None(안 줌). 역할은 `style_cover.ROLES` 의 코드만 — 꼴이 틀리거나 모르는 코드는 400."""
    if roles is None:
        return None
    codes = {r[0] for r in getattr(sc, "ROLES", ()) or ()}
    if not isinstance(roles, dict) or any(not isinstance(v, str) or v not in codes for v in roles.values()):
        raise HTTPException(400, f"roles 는 {{블록 id: 역할}} — 역할은 {'·'.join(sorted(codes)) or '정해진 코드'} 중 하나")
    inside = set(cand["blocks"])
    return {k: v for k, v in roles.items() if k in inside} or None


def _cover_part(info, name, source) -> dict:
    """`style_cover.carrier` 의 info → meta 의 일부(표지 서식 — ② §14: page = 그 구역의 쪽 설정 · parts = 부분들)."""
    info = info if isinstance(info, dict) else {}
    return {"kind": "cover", "name": name, "source": source, "losses": [str(x) for x in info.get("losses") or [] if x], "requirements": {"fonts": list(info.get("fonts") or [])},
            "page": info.get("page") if isinstance(info.get("page"), dict) else None, "parts": [p for p in info.get("parts") or [] if isinstance(p, dict)]}


def _all_blocks(blocks):
    """웹 블록을 칸 안까지 훑는다(문서 순)."""
    for b in blocks or []:
        yield b
        for c in b.get("cells") or []:
            yield from _all_blocks(c.get("blocks"))


def _build_from_docx(s, body, kind, keep, role=None, naming=None):  # 이름 주의 — 위 `_build_docx(meta, carrier)`(docx 운반 문서 짓기)와 다른 함수: docx **문서**에서 서식을 짓는다
    """docx 문서에서 서식 하나를 **짓는다**(spec_서식복사 ② §6 — 파일 추출과 같은 규칙 · `_build` 의 docx 쪽) → (meta, hwpx 운반 문서 바이트, rev). 문서는 안 바뀐다 — 저장·기록·검증은 `save_doc_style` 이.
    2차(② §12·§14): 문단 서식의 `role` · 쪽 설정의 `bodyKey` · 표지 `{kind: "cover"}`(`style_cover` 가 docx 원본을 명세로 다시 짓는다).
    표 = 그 표 블록의 명세(`style_carrier.spec_of_block`)로 hwpx 운반 문서를 다시 짓는다(`from_table_spec`) · 글 = 고른 문단의 서식 요약(서식이 같은 문단은 하나로 · 레벨 없음 —
    `from_text_spec`) · 문서 서식 = 쪽 설정 + 바탕 글. `fidelity: "summary"` · `source.format: "docx"`. `template`(개요템플릿)은 hwpx 문서만(400).
    구조(blueprint: true)는 라벨 칸 = label · 나머지 = input(수식 판정은 hwpx 문서만 — computed 없음).
    naming = (문서 이름, 고친 이름) — 이름이 없을 때 기본 이름을 짓는다(`_auto_name` — spec_서식복사 ② §19-2) | None(견본 — 대강의 이름)."""
    if kind == "text" and body.get("template") is not None:
        raise HTTPException(400, "개요템플릿으로 저장하기는 hwpx 문서만 됩니다 — docx 문서는 문단을 골라 문단 서식으로 저장하세요")
    src0 = _src(s, "docx")  # 원본 기록(② §17) — 잠금 밖에서
    try:
        with s.lock:
            src = dict(src0)
            if kind == "page":
                data, meta = _page_meta(s, "docx", body, src)
            elif kind == "cover":
                data, meta = _cover_meta(s, body, src, None, keep)
            else:
                by = {b["id"]: b for b in _all_blocks(s.doc.blocks()) if b.get("type") in ("table", "paragraph")}
            if kind == "table":
                tid = body.get("table")
                block = by.get(tid) if isinstance(tid, str) else None
                if block is None or block["type"] != "table":
                    raise HTTPException(404, "서식으로 저장할 표가 지금 문서에 없습니다 — 다시 고르세요")
                spec = style_carrier.spec_of_block(block)
                bands = table_make.clean_roles(body.get("bands"), spec["rows"], spec["cols"], default=spec["bands"])
                data, info = style_carrier.from_table_spec({**spec, "bands": bands}, keep_text=keep)
                labels = _label_texts(data, info)
                bp = None
                if body.get("blueprint") is True:  # 운반 문서의 격자에서 — 라벨 칸만 label(그 글), 나머지는 input
                    cb = style_carrier.doc(data)
                    bp = {"cells": [{"row": c["row"], "col": c["col"], "rowSpan": c["rowSpan"], "colSpan": c["colSpan"], "role": "label" if (c["row"], c["col"]) in labels else "input",
                                     "label": labels.get((c["row"], c["col"]))} for c in sorted(cb.table_block(style_carrier.table_id(cb))["cells"], key=lambda c: (c["row"], c["col"]))],
                          "formulas": []}
                meta = {"kind": "table", "name": body.get("name"), "source": {**src, "block": tid, "where": _table_where(s, tid)},
                        "losses": info["losses"], "requirements": {"fonts": info["fonts"]}, "bands": info["bands"], "rows": info["rows"], "cols": info["cols"], "labels": info["labels"],
                        "blueprint": bp, "preview": info["preview"]}
            elif kind == "text":
                ids = body.get("paras")
                if not isinstance(ids, list) or not ids or len(ids) > PARAS_MAX or not all(isinstance(i, str) for i in ids):
                    raise HTTPException(400, f"paras 는 문단 id 1~{PARAS_MAX}개")
                se, seen, specs, origin = _mod("style_extract"), set(), [], []
                for i in ids:
                    b = by.get(i)
                    if b is None or b["type"] != "paragraph":
                        raise HTTPException(404, "고른 문단이 지금 문서에 없습니다 — 문서에서 다시 고르세요")
                    sig = json.dumps(b.get("format") or {}, ensure_ascii=False, sort_keys=True)
                    if sig in seen:  # 서식이 같은 문단은 하나로
                        continue
                    seen.add(sig)
                    marker = se._marker(b.get("text"), bool(b.get("list"))) if se is not None and hasattr(se, "_marker") else None  # Word 의 개요 수준은 번호를 안 그린다 — 번호는 numPr(list)만
                    specs.append({"level": None, "marker": marker, "sample": b.get("text") or "", "format": dict(b.get("format") or {})})
                    origin.append(i)
                data, items = style_carrier.from_text_spec(specs, keep_text=keep)
                items = [{**it, "origin": {**(it.get("origin") or {}), "para": pid}} for it, pid in zip(items, origin)]
                meta = {"kind": "text", "name": body.get("name"), "source": {**src, "block": origin[0], "where": f"문단 {len(ids)}개"},
                        "losses": ["서식 요약(글꼴·크기·굵게·정렬·줄 간격·여백)만 옮겼습니다 — 번호 매기기·스타일은 되살리지 않음"],
                        "requirements": {"fonts": sorted({(it.get("format") or {}).get("font") for it in items} - {None, ""})}, "items": items, "role": role}
            if not _given(body.get("name")):  # 기본 이름(② §19-2) — hwpx 문서와 같은 길(후보 = `docx_candidates`)
                meta["name"] = _auto_name(s, body, None, *naming) if naming else _rough_name(s.name, kind)
            rev = s.rev
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {**meta, "note": body.get("note") or "", "fidelity": "summary"}, data, rev


# ---- 견본(spec_서식복사 ② §13 — 「저장될 견본」: 저장과 같은 생성 함수로 지은 운반 문서의 보기) -----------------------------------------------

def _preview(meta, data, rev=None) -> dict:
    """지은 운반 문서 data 와 meta → 견본 답 {rev, kind, view, losses, fidelity}. view = `style_carrier.view(data, meta)`(표 = {table, grid, spec} · 글 = {paras, items} ·
    쪽 = {page, body, summary, paras} · 표지 = `style_cover.view`) — 같은 몸으로 저장한 서식의 `GET /api/styles/{sid}` 의 view 와 같다. 보기를 못 지으면 400."""
    try:
        view = style_carrier.view(data, _clean_for_view(meta))
    except ValueError as e:
        raise HTTPException(400, f"견본을 짓지 못했습니다: {e}") from e
    return {"rev": rev, "kind": meta.get("kind"), "view": view, "losses": [str(x) for x in meta.get("losses") or [] if x], "fidelity": meta.get("fidelity") or "native"}


def _clean_for_view(meta) -> dict:
    """보기에 쓰는 meta — 저장소가 저장할 때 고르는 꼴(`style_lib._clean`: 띠 수 · role · 부분)을 그대로 지나게 해, 견본의 보기가 저장한 뒤의 보기와 같게 한다. 틀린 meta 는 ValueError(→ 400)."""
    return style_lib._clean({**meta, "name": "견본"})  # 이름은 보기에 안 쓰인다 — 긴 이름·빈 이름이 견본을 막지 않게(저장은 그 이름을 그대로 검사한다)


@router.post("/api/docs/{doc_id}/styles/preview")
def style_preview(doc_id: str, body: dict = Body(...)):
    """문서의 후보 하나의 **견본**(spec_서식복사 ② §13·§16) — 몸은 저장(`POST …/styles`)과 **같은 꼴** → {rev, kind, view, losses, fidelity}. `build_doc_style` 로 지은 운반 문서의 보기만 돌려준다:
    **보관함에 아무것도 쓰지 않고 검증을 걸지 않으며 docx 운반 문서도 짓지 않는다**(기록도 남기지 않는다 — 잦게 불린다). 띠 수·「글도 그대로」·대표 문단·바탕 글을 바꾸면 그 몸으로 다시 부른다.
    같은 문서 차례(rev)·같은 몸의 답은 세션마다 기억해 둔 것을 준다(문서가 바뀌면 버림). 오류는 저장과 같다(400·404·501)."""
    _on()
    s = _sess(doc_id)
    try:
        key = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        key = None
    hit = _memo(s)["previews"].get(key) if key is not None else None
    if hit is not None:
        return hit
    meta, data, rev = _build(s, {**body, "blueprint": False} if isinstance(body, dict) else body, named=False)  # 구조(blueprint — 수식 판정)는 보기에 안 든다: 견본에서는 읽지 않는다 · 이름도 안 쓴다(기본 이름의 후보를 찾지 않는다)
    out = _preview(meta, data, rev)
    memo = _memo(s)
    if key is not None and memo["rev"] == rev:  # 짓는 사이 문서가 바뀌었으면 기억하지 않는다
        memo["previews"][key] = out
        while len(memo["previews"]) > MEMO_PREVIEWS:
            memo["previews"].popitem(last=False)
    return out


# ---- 파일에서 -------------------------------------------------------------------------------------------------------

def _extract():
    se = _mod("style_extract")
    if se is None:
        raise HTTPException(501, "서식 추출 모듈(app.style_extract)이 없습니다")
    return se


@router.post("/api/styles/extract-file")
def style_extract_file(file: UploadFile = File(...)):
    """multipart `file`(hwp·hwpx·docx·pdf) → {token, name, format, tables, texts, paras, pages, covers, losses} — 작업을 만들지 않는다. 연 것은 서버 메모리에 토큰으로 잡아 둔다(30분 · 넷까지 —
    넘으면 먼저 올린 것부터 놓는다: 그 토큰의 저장·견본·검토는 410). paras·covers(② §12·§14)는 추출 모듈이 낸 대로(옛 모듈·PDF 는 빈 목록).
    후보마다 `defaultName`(spec_서식복사 ② §19-2 — 「<파일 이름의 문서 종류 낱말>: <갈래><번호>」 · 작업이 없어 고친 이름은 없다)."""
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
    named = _with_names({k: pub.get(k) or [] for k in GROUPS}, format_names.doc_prefix(pub.get("name") or name))  # 새 사전 — 잡아 둔 entry 는 안 바뀐다
    return {**pub, "token": se.hold(entry), "name": pub.get("name") or name, "format": pub.get("format"), **{k: named[k] for k in GROUPS},  # pages = 문서 서식 후보(0~1 — spec_서식복사 ② §5·§8)
            "losses": pub.get("losses") or []}


def _held(se, token) -> dict:
    """잡아 둔 파일(토큰)의 entry — 없으면 410(30분이 지났거나, 넷까지만 잡아 두어 먼저 밀려났다 — 어느 쪽인지 단정하지 않는 글: spec_서식복사 ② §13)."""
    entry = se.held(token)
    if entry is None:
        raise HTTPException(410, GONE)
    return entry


@router.post("/api/styles/name-file")
def style_name_file(body: dict = Body(...)):
    """{token} → {tables, texts, paras, pages, covers, note, call, calls} — 잡아 둔 파일의 후보에 **LLM 검토**의 결과(이름 · 저장할 만한가 · 역할 · 의심 · 띠 수 … — `style_extract.review`: 옛 모듈은 `name`)를
    합친다(문서의 `candidates {llm: true}` 와 같은 꼴 · spec_서식복사 ② §6·§8·§15·§16). 쪽 설정 후보는 검토 답이 없어도 추천. 후보마다 `defaultName`(② §19-2 — 파일 이름의 문서 종류 낱말) ·
    검토 답의 `name` 은 설명이다(화면이 note 로).
    토큰 없음 410 · LLM 없음 503 · 호출이 모두 실패하고 답이 닿은 후보가 없으면 502. 작업이 없으므로 기록은 남기지 않는다."""
    _on()
    se = _extract()
    entry = _held(se, (body or {}).get("token"))
    from app import llm
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐) — 이름은 직접 붙일 수 있습니다")
    cands = {k: entry.get(k) or [] for k in GROUPS}
    res = _review(se, cands)
    out = _named(_with_names(cands, format_names.doc_prefix(entry.get("name"))), res, entry.get("name"))
    err = _review_error(res, out)
    if err:
        raise HTTPException(502, f"LLM 이 이름을 붙이지 못했습니다: {err}")
    return out


def _file_cover(entry, pick):
    """잡아 둔 파일(hwpx·docx)의 표지 후보 → (hwpx 운반 문서 바이트, meta 의 일부) — 문서의 표지 저장(`_cover_meta`)과 같은 길: 범위 = entry 의 `covers` 후보(추출 모듈이 실은 것 — 없으면 400) ·
    `end` 로 줄임 · `roles`. 원본 문서 객체는 entry 의 안쪽 값 `_doc`."""
    cand = next((c for c in entry.get("covers") or [] if isinstance(c, dict) and c.get("key") == pick.get("key") and c.get("blocks")), None)
    src = entry.get("_doc")
    if cand is None or src is None:
        raise HTTPException(400, NO_COVER)
    sc = _mod("style_cover")
    if sc is None:
        raise HTTPException(501, "표지 서식 모듈(app.style_cover)이 없습니다")
    cand = _cover_range(sc, cand, pick.get("end"))
    fmt = entry.get("format")
    data, info = sc.carrier(src, list(cand["blocks"]), roles=_cover_roles(sc, cand, pick.get("roles")), keep_text=False)  # 파일에서는 글째 저장하지 않는다(다른 파일 후보와 같다)
    part = _cover_part(info, _cover_name(entry.get("name")), {"name": entry.get("name"), "format": fmt, "work": None, "block": cand["blocks"][0], "page": None, "sha256": entry.get("_sha256"), "where": "첫 쪽"})
    return data, {**part, "fidelity": entry.get("fidelity") or {"hwpx": "native", "docx": "summary"}.get(fmt, "summary")}


def _file_name(entry, pick) -> str:
    """잡아 둔 파일의 후보 pick 의 기본 이름(spec_서식복사 ② §19-2 — `POST /api/styles/extract-file` 응답의 `defaultName` 과 같은 것) — 그 후보를 못 찾으면 대강의 이름(`_rough_name`)."""
    kind, key = pick.get("kind"), pick.get("key")
    named = _with_names({k: entry.get(k) or [] for k in GROUPS}, format_names.doc_prefix(entry.get("name")))
    groups = {"table": ("tables",), "text": ("texts", "paras"), "page": ("pages",), "cover": ("covers",)}.get(kind) or ()
    hit = next((c.get("defaultName") for g in groups for c in named[g] if isinstance(c, dict) and (c.get("key") or NAME_GROUP[g]) == key), None)
    return hit or _rough_name(entry.get("name"), kind)


def _file_build(se, entry, pick):
    """잡아 둔 파일의 후보 하나(pick = {kind, key, name?, note?, bands?, role?, end?, roles?}) → (hwpx 운반 문서 바이트, meta — `_create` 가 받는 꼴). 저장(`from-file`)과 견본(`preview-file`)이 같이 쓴다.
    name 이 없으면 그 후보의 기본 이름(`_file_name` — ② §19-2) · note = 설명(LLM 검토의 설명 — 0~400자).
    표·글·쪽 설정은 `style_extract.build_pick` 그대로(문단 묶음 `paras` 의 key · `rep` · `bodyKey` 도 그 함수가 받는다 — ② §12) · 표지는 `_file_cover`(문서의 표지 저장과 같은 검사·기본 이름).
    문단 묶음의 key 를 모르는 옛 추출 모듈이면 그 묶음을 글 후보(texts)에 얹어 한 번 더 부른다.
    문단 서식의 `role` = pick 의 것(틀리면 400) → 없으면 그 후보에 스크립트가 붙인 것. 없는 후보·틀린 값은 400."""
    kind, key = pick.get("kind"), pick.get("key")
    try:
        if kind == "cover":
            data, meta = _file_cover(entry, pick)
        else:
            para = next((c for c in entry.get("paras") or [] if isinstance(c, dict) and c.get("key") == key), None) if kind == "text" else None
            try:
                data, meta = se.build_pick(entry, pick)
            except ValueError:
                if para is None:
                    raise
                data, meta = se.build_pick({**entry, "texts": [*(entry.get("texts") or []), para]}, pick)  # 옛 추출 모듈(문단 묶음을 글 후보에서만 찾는다) — 그 묶음을 texts 에 얹어 한 번 더(entry 는 안 바꾼다)
            if kind == "text" and not style_lib.leveled({"kind": "text", "items": meta.get("items")}):
                role = _role(pick["role"]) if "role" in pick else meta.get("role") or (para or {}).get("role")
                meta = {**meta, "role": role if role in style_lib.ROLES else None}
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"후보 {key!r} 를 저장하지 못했습니다: {e.args[0] if e.args else e}") from e
    # 이름 — 준 것 · 없으면 그 후보의 기본 이름(spec_서식복사 ② §19-2 — 파일 추출 응답의 defaultName 과 같은 것: 전의 「<파일 이름> 표 R×C」·「<파일 이름> 글 서식 …」 을 바꿈)
    meta = {**meta, "name": pick["name"] if _given(pick.get("name")) else _file_name(entry, pick)}
    if pick.get("note") is not None:  # 설명(② §19-2 — LLM 검토의 설명이 여기로 온다 · 0~400자: 넘거나 글이 아니면 저장이 400)
        meta["note"] = pick["note"]
    src = meta.get("source") if isinstance(meta.get("source"), dict) else {}  # 원본 기록(② §17) — 파일에서 뽑은 것: 작업·프로젝트는 없고(파일을 바로 올렸다) 뽑은 때와 자리(쪽)만 더한다
    where = src.get("where") or (f"{src['page']}쪽" if isinstance(src.get("page"), int) and not isinstance(src.get("page"), bool) else None)
    return data, {**meta, "source": {**src, "where": where, "at": round(time.time(), 3)}}


@router.post("/api/styles/preview-file")
def style_preview_file(body: dict = Body(...)):
    """{token, pick: {kind, key, bands?, role?, end?, roles?}} → {rev: null, kind, view, losses, fidelity} — 잡아 둔 파일의 후보 하나의 **견본**(spec_서식복사 ② §13·§16: 문서의 견본 끝점과 같은 꼴).
    저장과 같은 생성 함수(`_file_build` — `style_extract.build_pick`)로 지은 운반 문서의 보기만 — 보관함에 쓰지 않고 검증을 걸지 않는다. 토큰이 없으면 410 「올린 파일을 서버가 놓았습니다 — …」."""
    _on()
    se, pick = _extract(), (body or {}).get("pick")
    if not isinstance(pick, dict):
        raise HTTPException(400, "pick 은 {kind, key, bands?}")
    data, meta = _file_build(se, _held(se, body.get("token")), pick)
    return _preview(meta, data)


@router.post("/api/styles/from-file")
def style_from_file(body: dict = Body(...)):
    """{token, picks: [{kind, key, name?, bands?}]} → {styles: [meta…]} — 잡아 둔 파일의 후보를 보관함에 저장(+ 검증). 토큰이 만료됐으면 410.
    클라이언트는 토큰과 후보 key 만 보낸다(파일 경로·명세를 받지 않는다). kind = table | text | page(문서 서식 — key "page": spec_서식복사 ② §8) | cover(표지 — key "cover" · `end?`·`roles?`: ② §14,
    파일에 표지 후보가 없으면 400). 글 pick 의 `role?` = 문단 서식의 역할(② §12). docx 운반 문서를 함께 지어 넣는다(`_create`).
    pick 의 `name?`(없으면 기본 이름 「<파일 이름의 문서 종류 낱말>: <갈래><번호>」) · `note?`(설명 — ② §19-2)."""
    _on()
    se, picks = _extract(), body.get("picks")
    if not isinstance(picks, list) or not picks or len(picks) > PICKS_MAX or not all(isinstance(p, dict) for p in picks):
        raise HTTPException(400, f"picks 는 [{{kind, key, name?, bands?}}] 1~{PICKS_MAX}개")
    entry = _held(se, body.get("token"))
    made = []
    for pick in picks:
        data, meta = _file_build(se, entry, pick)  # 표지(kind "cover" — ② §14)·문단 묶음·role 까지: 견본(`preview-file`)과 같은 생성 함수
        made.append(_create(meta, data))
        if not made[-1].get("existing"):
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


def _make_docx(server, s, sid, mode, body, extra):
    """docx 문서의 적용(spec_서식복사 ② §9) — `make(s)` 의 docx 쪽 → (편집 전 닿는 요소들, run). **빈 표 넣기**(docx 운반 문서의 표를 after 뒤에 — 채울 칸은 비움) ·
    **문단에 입히기**(템플릿 항목의 서식 요약 — 글·레터는 그대로)만. 서식은 보관함 템플릿만(기본 표 · 이 문서의 표는 hwpx 문서의 것). docx 서식이 없고 못 지으면 422."""
    if sid == "builtin" or sid.startswith("doc:"):
        raise HTTPException(400, "docx 문서에는 서식 보관함의 서식만 씁니다(기본 표 · 이 문서의 표는 hwpx 문서만)")
    if mode == "format":
        ts, key, ids = _pick(lambda: style_apply.docx_style(sid, "text")), body.get("item"), body.get("paras")
        if not any(it.get("key") == key for it in ts["items"]):
            raise HTTPException(400, "그 글 서식 항목이 없습니다")
        if not isinstance(ids, list) or not ids or len(ids) > PARAS_MAX or not all(isinstance(i, str) for i in ids):
            raise HTTPException(400, f"paras 는 문단 id 1~{PARAS_MAX}개")
        ps, keep = [server._para_el(s, i) for i in ids], body.get("keepNumbering", True) is not False

        def run():
            changed = _guard(lambda: style_apply.docx_format_paras(s.doc, ts, key, ids, keep_numbering=keep))
            extra["formatted"] = {"paras": len(changed)}
            return {"hosts": ps, "anchor": ids[0], "focus": None, "formatted": set(changed), "log": {"style": sid, "mode": mode, "item": key, "formatted": len(changed)}}
        return ps, run
    st, after = _pick(lambda: style_apply.docx_style(sid, "table")), body.get("after")
    el = s.doc._ids.get(after) if isinstance(after, str) else None
    if el is None or not s.doc._attached(el):
        raise HTTPException(404, "넣을 자리의 블록이 지금 문서에 없습니다 — 자리를 다시 고르세요")
    ref = _pick(lambda: style_apply.docx_top_level(s.doc, after))
    data = _docx_bytes(sid, st["meta"])
    if data is None:
        raise HTTPException(422, "이 서식은 docx 서식으로 짓지 못해 docx 문서에 넣을 수 없습니다")
    src = _pick(lambda: style_apply.docx_open(data))

    def run():
        r = _guard(lambda: style_apply.docx_table_blank(s.doc, src, st["meta"], after))
        extra["made"] = {"table": r["table"], "rows": r["rows"], "cols": r["cols"]}
        return {"hosts": [s.doc._ids[r["table"]], ref], "anchor": after, "focus": None,
                "log": {"style": sid, "mode": mode, "table": r["table"], "rows": r["rows"], "cols": r["cols"], "replaced": False}}
    return [ref], run


@router.post("/api/docs/{doc_id}/styles/{sid}/apply")
def style_apply_doc(doc_id: str, sid: str, body: dict = Body(...)):
    """서식을 문서에 적용 — 구조 편집 한 번(실행 취소 1개 · 기록 `styleApply`). sid = 보관함 템플릿 id | `builtin`(기본 표) | `doc:<표 id>`(이 문서의 표).
    spec_서식복사 ② §14: + {mode: "cover"}(hwpx — 표지 서식의 블록들을 문서의 **맨 앞**에 → 응답에 covered {blocks: n}: 화면은 문서를 다시 읽는다 · docx 문서는 아래 400) ·
    spec_서식복사 ② §9: + {mode: "page"}(hwpx — 문서 서식의 쪽 설정을 모든 구역에 → 응답에 paged {sections: n}: 화면은 문서를 통째로 다시 읽는다) ·
    **docx 문서**는 `tableBlank`·`format` 만(그 밖은 400 「docx 문서에는 빈 표 넣기 · 문단에 입히기만 됩니다」 — 쓰기 정책 403 은 같다). 아래는 hwpx 문서의 네 모드.
    그 워크플로우의 **원본 문서**(이관의 사업계획서 · 취합의 기관 문서 — `doc_agent.policy`)는 403 「원본 문서는 바꾸지 않습니다」. 운반 문서의 정의 참조가 끊어져 있으면 400(아무것도 안 가져온다).
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
        docx = _is_docx(s)
        if docx and mode not in DOCX_MODES:  # docx 문서: 빈 표 넣기 · 문단에 입히기만(spec_서식복사 ② §9)
            raise HTTPException(400, DOCX_ONLY)
        from app import doc_agent  # 쓰기 정책은 에이전트 반영과 같은 것 하나 — 부를 때 가져온다
        pol = doc_agent.policy((works.work(s.id) or {}).get("task"), s.name)  # 세션 잠금 안(_edit 가 make 를 잠금 안에서 부른다) — TASK 를 바꾸는 요청과 엇갈리지 않게
        if not pol["apply"]:
            raise HTTPException(403, pol["why"])
        if sid != "builtin" and not sid.startswith("doc:"):
            _on()
        if docx:
            return _make_docx(server, s, sid, mode, body, extra)
        if mode == "page":  # 문서 서식 입히기 — 모든 구역의 쪽 설정을 그 값으로(구조 편집 한 번 · 화면은 문서를 통째로 다시 읽는다: 응답의 paged)
            ps = _pick(lambda: style_apply.page_style(sid))
            firsts = style_apply.page_hosts(s.doc)  # 구역마다 쪽 설정을 품은 첫 문단 — 바뀌는 블록이 따로 없어 이것이 닿는 문단이다
            if not firsts:
                raise HTTPException(400, "이 문서에 쪽 설정을 품은 구역이 없습니다")

            def run():
                n = _guard(lambda: style_apply.set_page(s.doc, ps))
                extra["paged"] = {"sections": n}
                return {"hosts": firsts, "anchor": s.doc._id(firsts[0]), "focus": None, "log": {"style": sid, "mode": mode, "sections": n}}
            return firsts, run
        if mode == "cover":  # 표지 넣기(spec_서식복사 ② §14) — 문서의 맨 앞에 표지 서식의 블록들을(구조 편집 한 번 · 화면은 문서를 다시 읽는다: 응답의 covered)
            cs = _pick(lambda: style_apply.cover_style(sid))
            heads = [p for p in list(s.doc._sections[0].iterchildren(P))[:2]] if s.doc._sections else []  # 첫 구역의 맨 앞 문단들(구역 설정을 품은 첫 문단 + 원래 첫 블록) — 표지가 그 앞·사이에 든다
            if not heads:
                raise HTTPException(400, "이 문서에 본문 문단이 없어 표지를 넣을 수 없습니다")
            anchor = s.doc._id(heads[0])

            def run():
                r = _guard(lambda: style_apply.cover_insert(s.doc, cs, session=s))
                extra["covered"] = {"blocks": len(r["blocks"])}
                new = [s.doc._ids[i] for i in r["blocks"]] + ([s.doc._ids[r["after"]]] if r.get("after") else [])
                return {"hosts": new + [e for e in heads if s.doc._attached(e)], "anchor": anchor, "focus": None,
                        "log": {"style": sid, "mode": mode, "blocks": len(r["blocks"]), "after": r.get("after")}}
            return heads, run
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
