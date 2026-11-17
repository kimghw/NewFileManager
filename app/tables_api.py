"""표 모듈 API(spec_헤딩_추출 ② §10 「모듈」) — 표만 다루는 끝점을 한곳에(사용자 2026-11-10 "본문 따로, 테이블 따로"): 표 지침(표 에이전트 입력) ·
엑셀식 보기의 사용자 수식 저장 · 에이전트 입력 묶음 미리보기 · **표 행·열 편집**(`POST …/table` — 2026-11-10 astra 협의로 server.py 에서 옮김, URL·본문·응답 그대로;
트랜잭션 `server._edit` — 잠금·스냅샷·OWPML 검사·실행 취소 스택·기록 — 은 본문 편집과 공유한다. 실행 취소가 문서마다 한 줄이어야 하므로 — spec_owpml_편집 ② §2·§3).
본문(문단·헤딩) 끝점은 server.py 에 그대로.

여기 두지 않은 표 끝점: 3단계 표 구조 결과(`GET …/headings/tables`·`…/xlsx`)는 헤딩 추출 실행(1·2·3단계)의 일부라 server.py 「헤딩 추출」 절에.
저장소·묶음 글은 `app/table_agent.py`, 작성요령·표 구조는 `app/heading_tables.py`, 행·열 편집의 형식 중립부(`TABLE_OPS`·`table_range`)는 `app/table_ops.py`.

**표 만들기 · 서식 변환**(spec_헤딩_추출 ② §11 — 파일 끝 절): 구역 수 `GET …/tables/{tid}/roles` · 정리(LLM | 그대로) `POST …/tables/compose` · 문서에 넣기 `POST …/tables/make` ·
서식만 입히기 `POST …/tables/restyle`. 형식 중립부 `app/table_make.py`, LLM 계약 `app/table_llm.py`, hwpx 어댑터 `app/hwpx_table_make.py`.

**빈 필드 제거**(spec_헤딩_추출 ② §16 — 파일 끝): `POST …/tables/{tid}/prune` — 미리보기(`dry`) · 필드가 모두 빈 행·열 지우기. 판정·지우기는 `app/table_prune.py`.

**표 채우기**(spec_헤딩_추출 ② §18 — 파일 끝): `POST …/tables/{tid}/fill` — 채울 칸 미리보기(`dry`) · LLM 제안(문서 안 바뀜) · `POST …/tables/{tid}/fill/apply` — 고른 제안을 문서에(한 트랜잭션).
판정·계약·답 검사는 `app/table_fill.py`."""
import time

from fastapi import APIRouter, Body, HTTPException

from app import heading_forms, heading_rules, heading_runs, job_prompts, llm, table_agent, table_llm, table_make, works

router = APIRouter()


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    return server._sess(doc_id)


def is_table(s, tid):
    """문서의 표 블록인가 — 블록 id 로 요소를 찾아 tbl 인지 본다(hwpx hp:tbl · docx w:tbl)."""
    el = s.doc._ids.get(tid)
    return el is not None and str(el.tag).endswith("}tbl")


def table_notes(s, tid, tb=None):
    """그 표의 작성요령(문서에서) — 3단계 결과의 것(표 안 안내 칸 · 표 앞뒤 안내 문단) + 지금 문서에서 읽은 뒤따르는 「작성 요령」 표(`table_fill.guide_tables` — spec ② §18).
    세션 잠금 안에서 부른다. hwpx 만 「작성 요령」 표를 잇는다."""
    from app import table_fill
    notes = list((tb or {}).get("notes") or [])
    if hasattr(s.doc, "_sections"):
        notes += table_fill.guide_tables(s.doc, tid)
    return notes


def agent_view(s, tid):
    """{table, stage3, ident, notes, common, own, form, rulesDefault, forms, prompt} — tid `_common` 은 공통 지침(ident null · notes [] · own null · forms null).
    form = 이 문서 양식 정보의 「표」 절 글("" = 없음) — 양식마다 관리하는 표 요청(spec ② §12), 묶음 글에 [양식 지침] 으로 든다.
    작성요령의 세 묶음(spec ② §18): notes = 문서의 작성요령(+ 뒤따르는 「작성 요령」 표 — where "guide") · form·common·own 의 instructions = 지침 ·
    rulesDefault(앱 기본)·common.rules·own.rules = 칸 입력 규칙. forms = 표에서 읽은 칸 꼴 {counts{꼴: 수}, fields, open, text} | null(hwpx 아님 · 못 읽음)."""
    from app import table_fill
    t3 = heading_runs.tables(s)
    tb = next((x for x in (t3 or {}).get("tables", []) if x["id"] == tid), None) if tid != table_agent.COMMON else None
    common = table_agent.get(s.id, table_agent.COMMON)
    own = table_agent.get(s.id, tid) if tid != table_agent.COMMON else None
    form = heading_forms.table_guide(s)
    notes, forms = [], None
    if tid != table_agent.COMMON:
        with s.lock:
            notes = table_notes(s, tid, tb)
            if hasattr(s.doc, "_sections") and is_table(s, tid):
                try:
                    an = table_fill.analyze(s.doc, tid, doc_key=getattr(s, "doc_key", None), roles=_heads(s, tid))
                except ValueError:
                    an = None   # 너무 큰 표 — 칸 꼴 없이
                if an is not None:
                    forms = {"counts": an["forms"], "fields": an["counts"]["fields"], "open": an["counts"]["open"], "text": table_fill.forms_text(an["forms"])}
    return {"table": tid, "stage3": tb is not None, "ident": table_agent.ident(tb), "notes": notes, "common": common, "own": own,
            "form": form, "rulesDefault": table_agent.DEFAULT_RULES, "forms": forms,
            "prompt": table_agent.prompt(tb, common, own, tid=tid, notes=notes, form=form, forms=(forms or {}).get("text"))}


def _check(s, tid):
    if tid != table_agent.COMMON and not is_table(s, tid):
        raise HTTPException(404, "그 표가 문서에 없습니다")


@router.get("/api/docs/{doc_id}/headings/tables/agents")
def table_agents(doc_id: str):
    """저장된 표 지침·사용자 수식 전부 — {common, tables: {표 id: {instructions, formulas, version, updated}}}."""
    return table_agent.all_tables(_sess(doc_id).id)


@router.get("/api/docs/{doc_id}/headings/tables/{tid}/agent")
def table_agent_get(doc_id: str, tid: str):
    s = _sess(doc_id)
    _check(s, tid)
    return agent_view(s, tid)


@router.put("/api/docs/{doc_id}/headings/tables/{tid}/agent")
def table_agent_put(doc_id: str, tid: str, body: dict = Body(...)):
    """{instructions?, rules?, formulas?, version?} — `_common` 은 instructions·rules 만. rules = 칸 입력 규칙(spec ② §18). version 이 다르면 409 · 값이 틀리면 400 · 파일 쓰기 실패 503."""
    s = _sess(doc_id)
    _check(s, tid)
    try:
        table_agent.save(s.id, tid, instructions=body.get("instructions"), formulas=body.get("formulas"), rules=body.get("rules"), expect=body.get("version"))
    except heading_rules.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, f"그런 표가 없습니다: {tid}") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"표 지침을 저장하지 못했습니다: {e}") from e
    return agent_view(s, tid)


# ---- 표 엑셀화(spec_헤딩_추출 ② §14) — 지금 문서의 표(또는 끌어 고른 범위)만 수식 판정 · 엑셀식 보기 격자를 .xlsx 로 ----------------------------------------------
def _range(body):
    rng = body.get("range") if isinstance(body, dict) else None
    if rng is None:
        return None
    try:
        out = {k: int(rng[k]) for k in ("r0", "c0", "r1", "c1")}
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(400, "range 는 {r0, c0, r1, c1} 정수") from e
    if out["r0"] < 0 or out["c0"] < 0 or out["r1"] < out["r0"] or out["c1"] < out["c0"]:
        raise HTTPException(400, "range 가 거꾸로이거나 음수입니다")
    return out


@router.post("/api/docs/{doc_id}/tables/{tid}/excel")
def table_excel_judge(doc_id: str, tid: str, body: dict = Body(default={})):
    """{range?: {r0, c0, r1, c1}} → 수식 판정(`table_excel.judge`) — 칸 역할·서브 테이블·엑셀 수식·숫자 칸. 문서를 바꾸지 않는다. hwpx 만."""
    from app import table_excel
    s = _sess(doc_id)
    rng = _range(body)
    with s.lock:
        if not hasattr(s.doc, "_sections"):
            raise HTTPException(400, "수식 판정은 지금 hwpx 문서만 됩니다")
        _live_table(s, tid)
        try:
            out = table_excel.judge(s.doc, tid, rng, doc_key=getattr(s, "doc_key", None), roles=_heads(s, tid))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    if out is None:
        raise HTTPException(404, "그 표가 지금 문서에 없습니다")
    out["rev"] = s.rev
    return out


@router.post("/api/docs/{doc_id}/tables/{tid}/excel/xlsx")
def table_excel_xlsx(doc_id: str, tid: str, body: dict = Body(...)):
    """엑셀식 보기 격자(화면 그대로 — 사용자 수식·정렬·고친 값 포함) → .xlsx. 본문 {range?, rows, cols, unit?, cells:[…]} — `table_excel.grid_workbook`."""
    from urllib.parse import quote

    from fastapi.responses import Response

    from app import table_excel
    s = _sess(doc_id)
    cells = body.get("cells")
    if not isinstance(cells, list) or len(cells) > table_excel.MAX_CELLS:
        raise HTTPException(400, "cells 가 없거나 너무 많습니다")
    rng = _range(body)
    try:
        data = table_excel.grid_workbook({**body, "table": tid, "range": rng}, s.name)
    except ImportError as e:
        raise HTTPException(503, "openpyxl 이 없어 엑셀을 만들 수 없습니다(pip install openpyxl)") from e
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(400, f"격자 값이 틀렸습니다: {e}") from e
    stem = s.name.rsplit(".", 1)[0] if "." in s.name else s.name
    from app.heading_calc import col_letter
    part = f"_{col_letter(rng['c0'])}{rng['r0'] + 1}-{col_letter(rng['c1'])}{rng['r1'] + 1}" if rng else ""
    name = f"{stem}_{tid}{part}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}", "Cache-Control": "no-store"})


@router.post("/api/docs/{doc_id}/tables/{tid}/excel/llm")
def table_excel_llm(doc_id: str, tid: str, body: dict = Body(default={})):
    """LLM 수식 판정(spec_헤딩_추출 ② §14 「LLM 수식 판정」) — {range?, effort?} → {table, rev, range, formulas[{ref, formula, reason, script, kind}], rejected[], note, counts, call}.
    엑셀식 보기의 단추를 누를 때만 부른다. 문서를 바꾸지 않는다(제안 — 화면에서 사람이 적용). 자료는 세션 잠금 안에서 모으고 호출은 잠금 밖(동기 — 수 초~수십 초). hwpx 만."""
    from app import table_excel
    from app import table_excel_llm as TL
    s = _sess(doc_id)
    rng = _range(body)
    effort = body.get("effort") if isinstance(body, dict) else None
    if effort is not None and effort not in llm.EFFORTS:
        raise HTTPException(400, f"effort 는 {'·'.join(llm.EFFORTS)} 중 하나")
    form_guide = heading_forms.table_guide(s)   # 양식 정보의 「표」 절(spec ② §12) — 양식 폴더·작업 파일을 읽으므로 세션 잠금 밖에서
    with s.lock:
        if not hasattr(s.doc, "_sections"):
            raise HTTPException(400, "수식 판정은 지금 hwpx 문서만 됩니다")
        block = _live_table(s, tid)
        try:
            judged = table_excel.judge(s.doc, tid, None, doc_key=getattr(s, "doc_key", None), roles=_heads(s, tid))  # 늘 표 전체 — 범위 보기여도 헤더 맥락과 스크립트 수식이 있어야 한다
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if judged is None:
            raise HTTPException(404, "그 표가 지금 문서에 없습니다")
        if not judged.get("cells"):
            raise HTTPException(400, judged.get("note") or "1칸 표(글상자)는 엑셀식으로 판정하지 않습니다")
        sh = TL.sheet(block, judged)
        if len(sh["cells"]) > TL.MAX_CELLS:
            raise HTTPException(400, f"표가 너무 큽니다(칸 {len(sh['cells'])} > {TL.MAX_CELLS})")
        if rng:  # 표 안으로 — 화면의 범위는 구조 편집 뒤 낡았을 수 있다
            rng = {"r0": min(rng["r0"], sh["rows"] - 1), "c0": min(rng["c0"], sh["cols"] - 1), "r1": min(rng["r1"], sh["rows"] - 1), "c1": min(rng["c1"], sh["cols"] - 1)}
        data = TL.payload(tid, sh, table_excel.context(s.doc, tid), judged.get("unit"), rng)
        guide = TL.guide_text(table_agent.get(s.id, table_agent.COMMON)["instructions"], table_agent.get(s.id, tid)["instructions"], form=form_guide)
        rev = s.rev
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐)")
    res = TL.ask(data, guide, effort=effort)
    call, got = res["call"], res["data"]
    out = TL.apply(got, sh, rng) if got is not None else None
    detail = works.add_detail(s.id, "tables", f"formula_{int(time.time() * 1000)}",
                              {"rev": rev, "table": tid, "range": rng, "prompt": res["prompt"], "response": got, "call": call, "result": out})
    works.log(s.id, "tableFormulaLlm", rev=rev, table=tid, range=data.get("range"), counts=(out or {}).get("counts"),
              backend=call.get("backend"), ms=call.get("ms"), costUsd=call.get("costUsd"), error=call.get("error"), detail=detail)
    if out is None:
        raise HTTPException(502, f"LLM 이 수식을 판정하지 못했습니다: {call.get('error') or '응답 없음'}")
    return {"table": tid, "rev": rev, "range": rng, **out, "note": str(got.get("note") or "")[:600], "call": call}


# ---- 표 행·열 편집(spec_owpml_편집 ② §2 「표 행·열」·② §4 「표 칸 고르기」) ------------------------------------------------------------------------------
@router.post("/api/docs/{doc_id}/table")
def table_edit(doc_id: str, body: dict = Body(...)):
    """표 행·열 {id: 칸 안 문단(또는 칸), op: row_above|row_below|row_delete|col_left|col_right|col_delete,
    range?: {r0, c0, r1, c1}} — range(격자 좌표, 끌어 고른 칸 묶음)가 있으면 그 칸 대신 그 범위의 행·열 기준. 어댑터 `doc.table_edit`(hwpx_struct·docx_struct).
    응답·검사 대상은 늘 표를 품은 본문 문단(= 표 전체): 기준 칸이 지워져도 남은 표의 OWPML 지역 검사와 `tops` 가 같은 잠금 안에서 나온다(astra P1, 2026-11-10 — 전에는
    hosts 가 비어 검사가 빠지고 잠금을 풀었다 다시 잡아 블록을 찾았다).
    고른 칸만(spec_owpml_편집 ② §5-2): op cells_below|cells_above|cells_copy|cells_delete|merge|unmerge|split + `opts {rows, cols, keep: table|cell}`(split).
    열 넣기·지우기의 폭은 헤더 열을 지키고 필드 열끼리 비율대로(② §5-1 — 칸 역할은 `table_heads`: 스크립트 초안 + 사용자 헤더 지정)."""
    from app import server  # 트랜잭션(_edit)·세션은 server 것 — 부를 때 가져온다(순환 import 피함)
    from app import table_heads
    bid, op, rng = body.get("id"), body.get("op"), body.get("range")
    given = body.get("opts") if isinstance(body.get("opts"), dict) else {}

    def make(s):
        el = server._para_el(s, bid, cell_ok=True)
        host = s.kit["struct"].top_host(s.doc, el)  # 표를 품은 본문 문단 — 편집 전에 잡아 둔다(행·열을 지워 기준 칸이 사라져도 남는다)
        opts = {k: given[k] for k in ("rows", "cols", "keep") if k in given}
        opts["fields"] = lambda tid: table_heads.fields_of(s.doc, tid, table_heads.get(s.id, tid), doc_key=getattr(s, "doc_key", None))

        def run():
            s.doc.table_edit(bid, op, rng, opts)
            keep = s.doc._attached(el)
            hosts = [host] if host is not None and s.doc._attached(host) else ([el] if keep else [])
            return {"hosts": hosts, "anchor": bid, "focus": {"id": bid, "offset": 0} if keep and el.tag == s.kit["para"] else None}
        return [el], run
    return server._edit(doc_id, make, "table", body)


# ---- 표 만들기 · 서식 변환(spec_헤딩_추출 ② §11) -------------------------------------------------------------------------------------------------------
# 흐름: 표 양식(문서의 표 하나) → 원본(고른 글 · 붙여 넣기 · 문서의 표) → 정리(LLM | 그대로 — compose, 문서 안 바뀜) → 미리보기 격자 → 문서에 넣기(make) | 서식만 입히기(restyle).
PARAS_MAX = 2000  # 원본으로 고를 수 있는 문단 수


def _hwpx_only(s):
    if not hasattr(s.doc, "table_make"):
        raise HTTPException(400, "표 만들기·서식 변환은 지금 hwpx 문서만 됩니다")


def _live_table(s, tid, what="표"):
    """문서에 붙어 있는 표의 웹 블록 — 없으면 404."""
    el = s.doc._ids.get(tid) if isinstance(tid, str) else None
    if el is None or not str(el.tag).endswith("}tbl") or not s.doc._attached(el):
        raise HTTPException(404, f"{what}가 지금 문서에 없습니다 — 다시 고르세요")
    return s.doc.table_block(tid)


def _roles(block, given=None):
    """구역 수 — 준 값(화면에서 고친 것)이 없으면 자동 판정."""
    return table_make.clean_roles(given, block["nRows"], block["nCols"], default=table_make.roles_of(block["cells"], block["nRows"], block["nCols"]))


@router.get("/api/docs/{doc_id}/tables/{tid}/roles")
def table_roles(doc_id: str, tid: str):
    """표의 구역 수 자동 판정 {table, rows, cols, roles: {headerRows, headerCols, footRows}, nested}."""
    s = _sess(doc_id)
    with s.lock:
        _hwpx_only(s)
        b = _live_table(s, tid)
        return {"table": tid, "rows": b["nRows"], "cols": b["nCols"], "roles": _roles(b), "nested": table_make.block_nested(b)}


def _source(s, src):
    """원본 → (글 | None, 격자 입력 | None) — 표 꼴이면 격자도. 세션 잠금 안에서."""
    kind = src.get("kind") if isinstance(src, dict) else None
    if kind == "paras":
        ids = src.get("ids")
        if not isinstance(ids, list) or not ids or len(ids) > PARAS_MAX or not all(isinstance(i, str) for i in ids):
            raise HTTPException(400, f"원본 문단(ids)은 1~{PARAS_MAX}개")
        texts = []
        for i in ids:
            el = s.doc._ids.get(i)
            if el is None or el.tag != s.kit["para"] or not s.doc._attached(el):
                raise HTTPException(404, "고른 문단이 지금 문서에 없습니다 — 문서에서 다시 고르세요")
            texts.append(s.doc._text(el).replace(" ", "\n"))
        text = "\n".join(texts)
        return text, table_make.parse_text(text)
    if kind == "text":
        text = src.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(400, "원본 글이 비어 있습니다 — 표나 글을 붙여 넣으세요")
        return text, table_make.parse_text(text)
    if kind == "grid":
        if not isinstance(src.get("grid"), dict):
            raise HTTPException(400, "원본 격자(grid)가 필요합니다")
        return None, src["grid"]
    if kind == "table":
        return None, table_make.block_grid(_live_table(s, src.get("id"), "원본으로 고른 표"))
    raise HTTPException(400, "source.kind 는 paras·text·grid·table 중 하나")


@router.post("/api/docs/{doc_id}/tables/compose")
def table_compose(doc_id: str, body: dict = Body(...)):
    """원본을 표 격자로 정리(문서는 안 바뀜) — {template, templateRoles?, source, instructions?, llm: bool, effort?} → {grid, note, check, mode, call, rev}.
    llm false = 그대로(원본이 표 꼴일 때만). 자료는 잠금 안에서, LLM 호출은 잠금 밖(동기 — 수 초~수십 초)."""
    s = _sess(doc_id)
    use_llm = body.get("llm", True) is not False
    tpl_id, extra = body.get("template"), body.get("instructions")
    if extra is not None and (not isinstance(extra, str) or len(extra) > table_agent.TEXT_MAX):
        raise HTTPException(400, f"지침은 {table_agent.TEXT_MAX:,}자 이하의 글")
    with s.lock:
        _hwpx_only(s)
        tb = _live_table(s, tpl_id, "표 양식으로 고른 표")
        tpl_roles = _roles(tb, body.get("templateRoles"))
        text, grid_in = _source(s, body.get("source"))
        rev = s.rev
    if text is not None and len(text) > table_make.SOURCE_MAX:
        raise HTTPException(400, f"원본 글이 너무 깁니다 — {len(text):,}자(한도 {table_make.SOURCE_MAX:,}자)")
    try:
        src_norm = table_make.normalize(grid_in) if grid_in is not None else None
    except ValueError as e:
        if text is None:
            raise HTTPException(400, str(e)) from e
        src_norm = None  # 표 꼴로 읽다 실패한 글은 글로 다룬다
    if src_norm is not None and "headerRows" not in grid_in:  # 구역 수 없이 온 격자(붙여 넣은 HTML 표) — 자동 판정
        src_norm.update(table_make.roles_of(src_norm["cells"], src_norm["nRows"], src_norm["nCols"]))
    if not use_llm:
        if src_norm is None:
            raise HTTPException(400, "원본이 표 꼴이 아니라 그대로는 표로 못 옮깁니다 — 「LLM 으로 표 정리」 를 쓰세요")
        return {"grid": table_make.to_rows(src_norm), "note": "", "check": table_make.check_texts(src_norm, src_norm), "mode": "asis", "call": None, "rev": rev}
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐) — 표 꼴 원본은 「그대로 표로」 를 쓰세요")
    mode = "convert" if src_norm is not None else "compose"
    t3 = heading_runs.tables(s)
    notes = next((x.get("notes") for x in (t3 or {}).get("tables", []) if x.get("id") == tpl_id), None)
    guide = table_llm.guide_text(table_agent.get(s.id, table_agent.COMMON)["instructions"], table_agent.get(s.id, tpl_id)["instructions"], extra,
                                 form=heading_forms.table_guide(s))   # 양식 정보의 「표」 절(spec ② §12)
    source = {"kind": "table", "grid": table_make.to_rows(src_norm)} if mode == "convert" else {"kind": "text", "text": text}
    res = table_llm.ask(mode, table_llm.template_data(tb, tpl_roles, notes), source, guide, effort=body.get("effort"))
    call, norm = res["call"], res["norm"]
    detail = works.add_detail(s.id, "tables", f"make_{int(time.time() * 1000)}",
                              {"rev": rev, "mode": mode, "template": tpl_id, "prompt": res["prompt"], "response": res["response"], "call": call})
    works.log(s.id, "tableCompose", rev=rev, mode=mode, template=tpl_id, rows=norm["nRows"] if norm else None, cols=norm["nCols"] if norm else None,
              backend=call.get("backend"), ms=call.get("ms"), costUsd=call.get("costUsd"), error=call.get("error"), detail=detail)
    if norm is None:
        raise HTTPException(502, f"LLM 이 표를 만들지 못했습니다: {call.get('error') or '응답 없음'}")
    check = table_make.check_texts(src_norm, norm) if mode == "convert" else table_make.check_numbers(text, norm)
    return {"grid": table_make.to_rows(norm), "note": res["note"], "check": check, "mode": mode, "call": call, "rev": rev}


def _slim(body, norm=None):
    """기록에 남길 요청 요약 — 격자 본문은 빼고 크기만."""
    out = {k: body.get(k) for k in ("template", "templateRoles", "after", "replace", "table", "roles") if body.get(k) is not None}
    if norm is not None:
        out["grid"] = {"rows": norm["nRows"], "cols": norm["nCols"], "headerRows": norm["headerRows"], "headerCols": norm["headerCols"], "footRows": norm["footRows"]}
    return out


@router.post("/api/docs/{doc_id}/tables/make")
def table_make_insert(doc_id: str, body: dict = Body(...)):
    """격자를 표 양식의 서식으로 문서에 넣기 — {template, templateRoles?, grid, after: 블록 id(그 문단 바로 뒤), replace?: {first, last}(문단 범위) | {table}}.
    replace 는 같은 트랜잭션에서 그 범위를 지운다(문단 범위에 표·그림이 끼어 있으면 400 — 원본 글에 없던 것을 지우지 않게). 응답 = 구조 편집 응답 + made {table, rows, cols}."""
    from app import server  # 트랜잭션(_edit)은 server 것 — 부를 때 가져온다(순환 import 피함)
    tpl_id, after, replace = body.get("template"), body.get("after"), body.get("replace")
    try:
        norm = table_make.normalize(body.get("grid"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    made = {}

    def make(s):
        _hwpx_only(s)
        roles = _roles(_live_table(s, tpl_id, "표 양식으로 고른 표"), body.get("templateRoles"))
        ref = s.doc._ids.get(after) if isinstance(after, str) else None
        if ref is None or not s.doc._attached(ref):
            raise HTTPException(404, "넣을 자리의 블록이 지금 문서에 없습니다 — 자리를 다시 고르세요")
        before, rng = [ref], None
        if replace:
            if not isinstance(replace, dict):
                raise HTTPException(400, "replace 는 {first, last} 또는 {table}")
            if replace.get("table") is not None:
                _live_table(s, replace["table"], "바꿀 표")
                rng = (replace["table"], replace["table"])
                before.append(s.doc._ids[replace["table"]])
            else:
                first, last = replace.get("first"), replace.get("last")
                for i in (first, last):
                    server._para_el(s, i)
                try:
                    hosts = s.doc._host_range(first, last)
                except ValueError as e:
                    raise HTTPException(400, str(e)) from e
                if any(s.doc._has_object(h) for h in hosts):
                    raise HTTPException(400, "고른 범위에 표·그림이 들어 있어 표로 바꿀 수 없습니다 — 「뒤에 넣기」 를 쓰세요")
                rng = (first, last)
                before += hosts

        def run():
            r = s.doc.table_make(after, tpl_id, norm, roles)
            if rng:
                s.doc.delete_blocks(*rng)
            made.update(table=r["table"], rows=r["rows"], cols=r["cols"])
            hosts = [s.doc._ids[r["host"]]] + [e for e in before if s.doc._attached(e)]
            return {"hosts": hosts, "anchor": after, "focus": None,
                    "log": {"table": r["table"], "template": tpl_id, "rows": r["rows"], "cols": r["cols"], "replaced": bool(rng)}}
        return before, run
    out = server._edit(doc_id, make, "tableMake", _slim(body, norm))
    if isinstance(out, dict):
        out["made"] = made
    return out


@router.post("/api/docs/{doc_id}/tables/restyle")
def table_restyle(doc_id: str, body: dict = Body(...)):
    """문서의 표에 표 양식의 서식만 입히기 — {table, template, roles?(그 표의 구역 수), templateRoles?}. 구조·글·칸 크기는 그대로. 응답 = 구조 편집 응답 + made."""
    from app import server
    tid, tpl_id = body.get("table"), body.get("template")
    made = {}

    def make(s):
        _hwpx_only(s)
        tpl_roles = _roles(_live_table(s, tpl_id, "표 양식으로 고른 표"), body.get("templateRoles"))
        sb = _live_table(s, tid, "서식을 입힐 표")
        roles = _roles(sb, body.get("roles"))
        el = s.doc._ids[tid]

        def run():
            r = s.doc.table_restyle(tid, tpl_id, roles, tpl_roles)
            made.update(table=tid, rows=sb["nRows"], cols=sb["nCols"], formatted=len(r["formatted"]))
            return {"hosts": [el], "anchor": tid, "focus": None, "formatted": set(r["formatted"]),
                    "log": {"table": tid, "template": tpl_id, "cells": r["cells"], "formatted": len(r["formatted"])}}
        return [el], run
    out = server._edit(doc_id, make, "tableRestyle", _slim(body))
    if isinstance(out, dict):
        out["made"] = made
    return out


# ---- 빈 필드 제거(spec_헤딩_추출 ② §16 — 표 메뉴) ---------------------------------------------------------------------------------------------------
def _prune_hwpx(s):
    if not hasattr(s.doc, "_sections"):
        raise HTTPException(400, "빈 필드 제거는 지금 hwpx 문서만 됩니다")


@router.post("/api/docs/{doc_id}/tables/{tid}/prune")
def table_prune_lines(doc_id: str, tid: str, body: dict = Body(default={})):
    """필드가 모두 빈 행·열 지우기(`app/table_prune.py`). hwpx 만.
    `{dry: true}` → 미리보기(문서 안 바뀜) `{table, rows, cols, fields, emptyFields, allEmpty, emptyRows[], emptyCols[], skipRows[], skipCols[], rowNames, colNames, note?, rev}`.
    `{rows?: bool(기본 true), cols?: bool(기본 false), rev?}` → 지우기 — 한 트랜잭션(`server._edit`: 실행 취소 1개 · OWPML 지역 검사 · 기록 `tablePrune`),
    응답 = 구조 편집 응답 + `pruned {table, rows[], cols[], skipRows[], skipCols[]}`. rev 가 지금 문서와 다르면 409(미리보기 뒤 문서가 바뀜), 지울 줄이 없으면 400."""
    from app import server, table_prune
    body = body if isinstance(body, dict) else {}
    if body.get("dry") is True:
        s = _sess(doc_id)
        with s.lock:
            _prune_hwpx(s)
            _live_table(s, tid)
            try:
                out = table_prune.plan(s.doc, tid, doc_key=getattr(s, "doc_key", None), roles=_heads(s, tid))
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
            if out is None:
                raise HTTPException(404, "그 표가 지금 문서에 없습니다")
            out["rev"] = s.rev
        return out
    rows, cols, rev = body.get("rows", True), body.get("cols", False), body.get("rev")
    if not isinstance(rows, bool) or not isinstance(cols, bool) or not (rows or cols):
        raise HTTPException(400, "rows·cols 는 true/false 이고 하나는 true 여야 합니다")
    pruned = {}

    def make(s):
        _prune_hwpx(s)
        _live_table(s, tid)
        if rev is not None and rev != s.rev:
            raise HTTPException(409, "미리 본 뒤 문서가 바뀌었습니다 — 표 메뉴에서 「빈 필드 제거하기」 를 다시 누르세요")
        el = s.doc._ids[tid]

        def run():
            r = table_prune.apply(s.doc, tid, rows=rows, cols=cols, doc_key=getattr(s, "doc_key", None), roles=_heads(s, tid))
            if not r["rows"] and not r["cols"]:
                raise ValueError("지울 빈 행·열이 없습니다" + ("(합친 칸에 걸려 못 지움)" if r["skipRows"] or r["skipCols"] else ""))
            pruned.update(table=tid, **r)
            return {"hosts": [el], "anchor": tid, "focus": None, "log": {"table": tid, "rows": r["rows"], "cols": r["cols"]}}
        return [el], run
    out = server._edit(doc_id, make, "tablePrune", {"table": tid, "rows": rows, "cols": cols})
    if isinstance(out, dict):
        out["pruned"] = pruned
    return out


# ---- 헤더 지정 · 표 판정 · 표 나누기(spec_owpml_편집 ② §5-3·§5-4) -----------------------------------------------------------------------------------
def _heads(s, tid):
    """그 표의 사용자 헤더 지정 {칸 id: 역할} — 없으면 None."""
    from app import table_heads
    return table_heads.get(s.id, tid) or None


def _heads_hwpx(s):
    if not hasattr(s.doc, "split_table"):
        raise HTTPException(400, "헤더 지정·표 나누기는 지금 hwpx 문서만 됩니다")


@router.get("/api/docs/{doc_id}/tables/heads")
def table_heads_all(doc_id: str):
    """저장된 헤더 지정 전부 {version, updated, tables: {표 id: {칸 id: rowhead|colhead|field}}} — 문서 표시(지정한 칸의 꼬리표)가 읽는다."""
    from app import table_heads
    return table_heads.load(_sess(doc_id).id)


@router.put("/api/docs/{doc_id}/tables/{tid}/heads")
def table_heads_put(doc_id: str, tid: str, body: dict = Body(...)):
    """{cells: [칸 id…], role: rowhead|colhead|field|null(지정 풀기)} → {table, roles: 그 표의 지정, layout}. 문서는 안 바뀐다. 그 표의 칸이 아니면 400."""
    from app import table_heads
    s = _sess(doc_id)
    with s.lock:
        _heads_hwpx(s)
        _live_table(s, tid)
        alive = {s.doc._id(x.el) for x in s.doc._tgrid(s.doc._ids[tid])[1]}
        cells = body.get("cells")
        if isinstance(cells, list) and any(c not in alive for c in cells):
            raise HTTPException(400, "그 표의 칸이 아닌 것이 있습니다 — 칸을 다시 고르세요")
        try:
            roles = table_heads.put(s.id, tid, cells, body.get("role"), alive)
            lay = table_heads.layout(s.doc, tid, roles, doc_key=getattr(s, "doc_key", None))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except OSError as e:
            raise HTTPException(503, f"헤더 지정을 저장하지 못했습니다: {e}") from e
        return {"table": tid, "roles": roles, "layout": {**lay, "rev": s.rev}}


@router.get("/api/docs/{doc_id}/tables/{tid}/layout")
def table_layout(doc_id: str, tid: str):
    """한 표의 판정(`table_heads.layout`) — 필드 열 표시·헤더 열 수·필드 열 단위·이어진 표·지정 + rev. 메뉴 미리보기·표 나누기 목록이 읽는다. 문서는 안 바뀐다."""
    from app import table_heads
    s = _sess(doc_id)
    with s.lock:
        _heads_hwpx(s)
        _live_table(s, tid)
        try:
            out = table_heads.layout(s.doc, tid, table_heads.get(s.id, tid), doc_key=getattr(s, "doc_key", None))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        out["rev"] = s.rev
        return out


def _between(a, b):
    """문단 a 에서 b 까지(같은 부모의 이어진 형제) — 짝 사이의 빈 문단도 편집 응답에 함께 실리게(화면이 그 구간을 통째로 바꿔 끼운다)."""
    out, el = [], a
    while el is not None:
        out.append(el)
        if el is b:
            return out
        el = el.getnext()
    return [a, b]


@router.post("/api/docs/{doc_id}/tables/{tid}/split")
def table_split(doc_id: str, tid: str, body: dict = Body(default={})):
    """표 나누기(② §5-3) — {op: "split" | "join" | "resplit", first: 앞 표에 둘 필드 열 단위 수}. split = 이 표를 둘로 · join = 이어진 표와 한 표로 · resplit = 합친 뒤 first 에서 다시.
    tid 는 짝의 어느 쪽이어도 된다(join·resplit — 뒤 표가 있으면 이 표가 앞, 아니면 앞 표의 뒤). 한 트랜잭션(실행 취소 1개 · OWPML 지역 검사 · 기록 `tableSplit`).
    응답 = 구조 편집 응답 + `split {op, tables: [앞, 뒤 | null], units: [앞 단위 수, 뒤 단위 수]}`. 400: 헤더 열이 없거나 필드 열 단위가 2개 미만 · 자리 밖 · 짝 없음 · 행 구조 다름."""
    from app import server, table_grid, table_heads
    body = body if isinstance(body, dict) else {}
    op, first = body.get("op", "split"), body.get("first")
    if op not in ("split", "join", "resplit"):
        raise HTTPException(400, "op 는 split·join·resplit 중 하나")
    if op != "join" and (not isinstance(first, int) or isinstance(first, bool) or first < 1):
        raise HTTPException(400, "first(앞 표에 둘 필드 열 단위 수 — 1 이상의 정수)가 필요합니다")
    done = {}

    def make(s):
        _heads_hwpx(s)
        _live_table(s, tid)
        lay = table_heads.layout(s.doc, tid, table_heads.get(s.id, tid), doc_key=getattr(s, "doc_key", None))
        hc = lay["headCols"]
        if not lay["units"]:
            raise HTTPException(400, "왼쪽 헤더 열과 그 뒤 필드 열이 있는 표만 나눌 수 있습니다 — 헤더가 안 잡혔으면 칸을 골라 「헤더 지정」 으로 행헤더를 지정하세요")
        a, b = tid, None
        if op != "split":
            nxt, prv = lay["partner"]["next"], lay["partner"]["prev"]
            if nxt:
                b = nxt["table"]
            elif prv:
                a, b = prv["table"], tid
            else:
                raise HTTPException(400, "이어진 표(바로 앞·뒤 문단에 헤더 열이 같은 표)가 없습니다")
        elif not 1 <= first < len(lay["units"]):
            raise HTTPException(400, f"나눌 자리가 틀렸습니다 — 필드 열 단위 {len(lay['units'])}개 중 앞 표에 1~{len(lay['units']) - 1}개")
        ta = s.doc._ids[a]
        before = _between(s.doc._host(ta), s.doc._host(s.doc._ids[b])) if b else [ta]

        def run():
            if b:
                s.doc.join_tables(a, b, hc)
            _t, cells, _nr, nc = s.doc._tgrid(ta)
            units = table_grid.col_units(cells, nc, hc)
            new = None
            if op != "join":
                if not 1 <= first < len(units):
                    raise ValueError(f"나눌 자리가 틀렸습니다 — 필드 열 단위 {len(units)}개 중 앞 표에 1~{len(units) - 1}개")
                new = s.doc.split_table(a, hc, units[first][0])["new"]
            k = first if new else len(units)
            done.update(op=op, tables=[a, new], units=[k, len(units) - k])
            hosts = [e for e in before if s.doc._attached(e)] + ([s.doc._ids[new]] if new else [])
            return {"hosts": hosts, "anchor": a, "focus": None, "log": {"table": a, "second": new, "joined": b, "units": done["units"]}}
        return before, run
    out = server._edit(doc_id, make, "tableSplit", {"table": tid, "op": op, "first": first})
    if isinstance(out, dict):
        out["split"] = done
    return out


# ---- 표 채우기(spec_헤딩_추출 ② §18 — 표 메뉴 「에이전트로 표 채우기」) -------------------------------------------------------------------------------
# 흐름: 채울 칸 미리보기(dry — 문서 안 바뀜·LLM 없음) → LLM 제안(작성요령 · 지침 · 칸 입력 규칙 + 자료 — 문서 안 바뀜) → 화면에서 사람이 고름 → fill/apply(한 트랜잭션).
FILLS_MAX = 400


def _fill_hwpx(s):
    if not hasattr(s.doc, "_sections"):
        raise HTTPException(400, "표 채우기는 지금 hwpx 문서만 됩니다")


@router.post("/api/docs/{doc_id}/tables/{tid}/fill")
def table_fill_propose(doc_id: str, tid: str, body: dict = Body(default={})):
    """표 채우기 제안 — {range?: {r0, c0, r1, c1}, overwrite?: bool(채워진 필드도 대상 — 기본 false), material?: 자료 글, useDoc?: bool(이 문서의 글도 자료로 — 기본 true),
    effort?, dry?: bool}. 문서를 바꾸지 않는다. hwpx 만.
    `dry: true` → 채울 칸 미리보기(LLM 없음) `{table, rev, range, rows, cols, unit, counts{cells, fields, open, targets, skipped}, forms, targets[{ref, cell, name, form, open, now}],
    skipped[{ref, why}], notes(작성요령 건수), guides(「작성 요령」 표 수), doc{chars, sent, cut}, job, llm(쓸 수 있는가), blocked(제안을 받을 수 없는 까닭 | null), note?}`.
    아니면 위 + `fills[{ref, cell, row, col, name, form, now, text, source, where, reason, quoted, warn[]}], rejected[], counts{…, fills, clean, warn, rejected, left}, answer(LLM 요약), call`.
    자료는 세션 잠금 안에서 모으고 호출은 잠금 밖(동기 — 수 초~수십 초). 400: 채울 칸 없음 · 채울 칸 300 초과(범위를 고르면 됨) · 칸 1,500 초과 표(범위로도 안 됨) · 칸 4,000 초과(판정 안 함) ·
    자료 6만 자 초과 · effort·range 값 틀림 · docx · 404: 표 없음 · 503: LLM 없음 · 502: 답 없음."""
    from app import table_excel, table_fill
    body = body if isinstance(body, dict) else {}
    s = _sess(doc_id)
    rng = _range(body)
    overwrite, use_doc, dry = body.get("overwrite") is True, body.get("useDoc", True) is not False, body.get("dry") is True
    material, effort = body.get("material") or "", body.get("effort")
    if not isinstance(material, str) or len(material) > table_fill.MATERIAL_MAX:
        raise HTTPException(400, f"자료는 {table_fill.MATERIAL_MAX:,}자 이하의 글")
    if effort is not None and effort not in llm.EFFORTS:
        raise HTTPException(400, f"effort 는 {'·'.join(llm.EFFORTS)} 중 하나")
    form_guide = heading_forms.table_guide(s)   # 양식 정보의 「표」 절(spec ② §12) — 파일을 읽으므로 세션 잠금 밖에서
    job = job_prompts.for_work(s.id)            # 이 작업의 할 일 프롬프트(spec_작업 ② §13) — 있으면 계약 바로 뒤에 한 절
    t3 = heading_runs.tables(s)
    tb = next((x for x in (t3 or {}).get("tables", []) if x["id"] == tid), None)
    with s.lock:
        _fill_hwpx(s)
        block = _live_table(s, tid)
        try:
            an = table_fill.analyze(s.doc, tid, rng, overwrite=overwrite, doc_key=getattr(s, "doc_key", None), roles=_heads(s, tid), block=block)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if an is None:
            raise HTTPException(404, "그 표가 지금 문서에 없습니다")
        notes = table_notes(s, tid, tb)
        ctx = table_excel.context(s.doc, tid)
        common, own = table_agent.get(s.id, table_agent.COMMON), table_agent.get(s.id, tid)
        doc_text, cut, chars = table_fill.doc_text(s.doc.blocks(), skip={tid}) if use_doc else ("", False, 0)
        rev = s.rev
    available = llm.status()["available"]
    # 제안을 받을 수 없는 까닭(미리보기에도 실어 화면이 단추를 끈다): 격자는 범위를 골라도 늘 표 전체라 칸 수 한도는 범위로 못 푼다 · 채울 칸 수 한도는 범위를 고르면 풀린다
    blocked = None
    if len(an["cells"]) > table_fill.MAX_CELLS:
        blocked = f"표가 너무 커서 채우기 제안을 받을 수 없습니다(칸 {len(an['cells']):,}개 — 한도 {table_fill.MAX_CELLS:,}개 · 범위를 골라도 표 전체를 보내야 합니다)"
    elif len(an["targets"]) > table_fill.TARGETS_MAX:
        blocked = f"한 번에 채울 칸이 너무 많습니다({len(an['targets']):,}개 — 한도 {table_fill.TARGETS_MAX}개) — 표 칸을 끌어 범위를 고른 뒤 다시 여세요"
    view = {"table": tid, "rev": rev, "range": an["range"], "rows": an["rows"], "cols": an["cols"], "unit": an["unit"], "counts": an["counts"], "forms": an["forms"],
            "targets": [{k: t[k] for k in ("ref", "cell", "name", "form", "open", "now")} for t in an["targets"]], "skipped": an["skipped"],
            "notes": len(notes), "guides": sum(1 for n in notes if n.get("where") == "guide"),
            "doc": {"chars": chars, "sent": len(doc_text), "cut": cut}, "job": job_prompts.brief(job), "llm": available, "blocked": blocked,
            **({"note": an["note"]} if an.get("note") else {})}
    if dry:
        return view
    if not an["targets"]:
        raise HTTPException(400, an.get("note") or ("채울 칸이 없습니다 — 빈 필드가 없거나 고른 범위에 없습니다" + ("" if overwrite else "(채워진 칸도 보려면 「채워진 칸도 다시 제안」)")))
    if blocked:
        raise HTTPException(400, blocked)
    if not available:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐)")
    data = table_fill.payload(an, ctx, material, doc_text, table_fill.place_of(tb))
    notes_txt, guide_txt, rules_txt = (table_fill.notes_text(notes), table_fill.guide_text(common["instructions"], own["instructions"], form=form_guide),
                                       table_agent.rules_text(common, own))
    res = table_fill.ask(data, notes_txt, guide_txt, rules_txt, job_prompts.part(job, table_fill.JOB_NOTE), effort=effort)
    call, got = res["call"], res["data"]
    out = table_fill.apply(got, an, table_fill.haystack(data), table_fill.rules_haystack(notes_txt, guide_txt, rules_txt)) if got is not None else None
    detail = works.add_detail(s.id, "tables", f"fill_{int(time.time() * 1000)}",
                              {"rev": rev, "table": tid, "range": an["range"], "overwrite": overwrite, "prompt": res["prompt"], "response": got, "call": call, "result": out,
                               "job": job_prompts.brief(job)})
    works.log(s.id, "tableFillLlm", rev=rev, table=tid, range=an["range"], targets=len(an["targets"]), counts=(out or {}).get("counts"), material=len(material), doc=len(doc_text),
              backend=call.get("backend"), ms=call.get("ms"), costUsd=call.get("costUsd"), error=call.get("error"), detail=detail)
    if out is None:
        raise HTTPException(502, f"LLM 이 채울 값을 제안하지 못했습니다: {call.get('error') or '응답 없음'}")
    return {**view, **out, "counts": {**an["counts"], **out["counts"]}, "answer": str(got.get("note") or "")[:600], "call": call}


@router.post("/api/docs/{doc_id}/tables/{tid}/fill/apply")
def table_fill_apply(doc_id: str, tid: str, body: dict = Body(...)):
    """고른 제안을 문서에 — {fills: [{cell: 칸 id, text, was?: 제안을 받을 때의 칸 글}]}. 칸의 글 문단을 text 의 줄로 바꾼다(`doc.set_text` — 문단 모양은 그 칸 것 그대로).
    was 가 지금 칸 글과 다르면 그 칸은 건너뛴다(제안 뒤 사람이 고친 칸을 덮지 않는다). 한 트랜잭션(`server._edit`: 실행 취소 1개 · OWPML 지역 검사 · 기록 `tableFill`).
    칸 안에 표·그림이 있는 칸도 건너뛴다(`skipped` — 쓰기가 칸의 문단을 통째로 바꾼다). 칸 역할은 다시 보지 않는다(그 표의 칸 id 면 쓴다 — 무엇을 채울지는 제안 단계가 정한 것).
    응답 = 구조 편집 응답 + `filled {table, cells[칸 id…], skipped[{cell, why}]}`. 400: 그 표의 칸이 아님 · 빈 글 · 2,000자 초과 · was 가 글이 아님 · 같은 칸 두 번 · 목록이 1~400개가 아님 ·
    409: 넣을 칸이 하나도 안 남음 · 404: 표 없음. hwpx 만."""
    from app import server, table_fill
    fills = body.get("fills") if isinstance(body, dict) else None
    if not isinstance(fills, list) or not fills or len(fills) > FILLS_MAX:
        raise HTTPException(400, f"fills 는 1~{FILLS_MAX}개의 목록")
    for f in fills:
        if not isinstance(f, dict) or not isinstance(f.get("cell"), str) or not isinstance(f.get("text"), str) or not f["text"].strip() or len(f["text"]) > table_fill.CELL_MAX \
                or ("was" in f and not isinstance(f["was"], str)):
            raise HTTPException(400, f"fills 의 항목은 {{cell: 칸 id, text: 1~{table_fill.CELL_MAX:,}자, was?: 글}}")
    if len({f["cell"] for f in fills}) != len(fills):
        raise HTTPException(400, "같은 칸이 두 번 들어 있습니다")
    done = {}

    def make(s):
        _fill_hwpx(s)
        block = _live_table(s, tid)
        tbl = s.doc._ids[tid]
        alive = {s.doc._id(x.el) for x in s.doc._tgrid(tbl)[1]}
        now = {c["id"]: str(c.get("text") or "") for c in block["cells"]}
        nested = {c["id"] for c in block["cells"] if any(b.get("type") != "paragraph" for b in c.get("blocks") or [])}
        todo, skipped = [], []
        for f in fills:
            if f["cell"] not in alive:
                raise HTTPException(400, "그 표의 칸이 아닌 것이 있습니다 — 제안을 다시 받으세요")
            if f["cell"] in nested:
                skipped.append({"cell": f["cell"], "why": "칸 안에 표·그림이 있음"})
                continue
            if "was" in f and f["was"] != now.get(f["cell"], ""):
                skipped.append({"cell": f["cell"], "why": "제안을 받은 뒤 칸 글이 바뀜"})
                continue
            todo.append((f["cell"], f["text"].replace("\r", "").replace(heading_rules.BR, "\n").strip()))
        if not todo:
            raise HTTPException(409, "넣을 칸이 없습니다 — 제안을 받은 뒤 칸 글이 바뀌었습니다. 제안을 다시 받으세요")

        def run():
            for cid, text in todo:
                s.doc.set_text(cid, text)   # 칸 안 표가 있으면 ValueError → 400(트랜잭션이 되돌림)
            done.update(table=tid, cells=[c for c, _ in todo], skipped=skipped)
            return {"hosts": [tbl], "anchor": tid, "focus": None, "log": {"table": tid, "cells": len(todo), "skipped": len(skipped)}}
        return [tbl], run
    out = server._edit(doc_id, make, "tableFill", {"table": tid, "cells": len(fills)})
    if isinstance(out, dict):
        out["filled"] = done
    return out


# ---- 표 서식 — 점검 · 맞추기(spec_헤딩_추출 ② §19) -------------------------------------------------------------------------------------------
STYLE_KEYS_MAX = 2000


def _style_hwpx(s):
    if not hasattr(s.doc, "split_table"):
        raise HTTPException(400, "표 서식 점검은 지금 hwpx 문서만 됩니다")


def _style_tb(s, tid):
    """표 서식의 칸 역할 → (표, 출처). 3단계 결과에 그 표가 있고 칸이 지금 문서와 같으면 그것(표 판정 LLM 이 고친 역할 포함 — 출처 stage3),
    아니면 그 표만의 스크립트 초안(`table_heads.table` — draft). 어느 쪽이든 지금의 사람 헤더 지정을 덮는다(3단계 결과는 복사해서 — 캐시를 바꾸지 않게)."""
    from app import table_heads
    user = table_heads.get(s.id, tid) or None
    alive = {s.doc._id(x.el) for x in s.doc._tgrid(s.doc._ids[tid])[1]}
    t3 = heading_runs.tables(s)
    tb = next((t for t in (t3 or {}).get("tables") or [] if t.get("id") == tid), None)
    if tb is not None and {c["id"] for c in tb.get("cells") or []} == alive:
        tb = {**tb, "cells": [dict(c) for c in tb["cells"]]}
        table_heads.apply(tb, user)
        return tb, "stage3"
    try:
        tb = table_heads.table(s.doc, tid, user, doc_key=getattr(s, "doc_key", None))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if tb is None:
        raise HTTPException(400, "칸 역할을 읽지 못한 표입니다(1칸 표 · 상자)")
    return tb, "draft"


def _style_report(s, tid):
    """그 표의 점검(문서 안 바뀜) — 개요 줄(템플릿이 다룸)은 견주지 않는다."""
    from app import server, table_style
    tb, source = _style_tb(s, tid)
    ov = server._outline_ov(s) or {}
    skip = {k for part in ("lines", "autos") for k in (ov.get(part) or ()) if isinstance(k, str)}  # 개요 줄 · 자동 글머리 줄(템플릿 대표에 맞추는 줄 — spec_hwpx_웹편집 ② §8-8)
    return table_style.check(s.doc, tb, skip=frozenset(skip), source=source)


@router.get("/api/docs/{doc_id}/tables/{tid}/style")
def table_style_get(doc_id: str, tid: str):
    """표 하나의 서식 점검 — 자리(머리행 · 머리열 · 합계행 · 열 · 빈 값)마다 대표 서식과 다른 서식, 그 표의 빈 값 표시. 문서는 안 바뀐다. hwpx 만 · 표 없음 404."""
    s = _sess(doc_id)
    with s.lock:
        _style_hwpx(s)
        _live_table(s, tid, "서식을 볼 표")
        return {**_style_report(s, tid), "rev": s.rev}


@router.post("/api/docs/{doc_id}/tables/{tid}/style/apply")
def table_style_apply(doc_id: str, tid: str, body: dict = Body(...)):
    """고른 다른 서식을 그 자리의 대표로 — {keys: [항목 키 「무엇:칸 id:문단 id」…]}(1~2,000개). 맞출 때 다시 점검해 지금도 다른 것만 바꾼다(그 밖은 skipped).
    한 트랜잭션(`server._edit`: 실행 취소 1개 · OWPML 지역 검사 · 기록 `tableStyle`). 응답 = 구조 편집 응답 + `styled {table, done[키], skipped[{key, why}], formatted}`.
    400 키 꼴 · docx · 409 맞출 것이 하나도 안 남음 · 404 표 없음."""
    from app import server, table_style
    keys = body.get("keys") if isinstance(body, dict) else None
    if not isinstance(keys, list) or not keys or len(keys) > STYLE_KEYS_MAX or not all(isinstance(k, str) and table_style.KEY_RE.match(k) for k in keys):
        raise HTTPException(400, f"keys 는 1~{STYLE_KEYS_MAX}개의 항목 키(「무엇:칸 id:문단 id」)")
    done = {}

    def make(s):
        _style_hwpx(s)
        _live_table(s, tid, "서식을 맞출 표")
        tbl = s.doc._ids[tid]
        report = _style_report(s, tid)
        live = {o["key"] for p in report["places"] for o in p["odd"]}
        if not any(k in live for k in keys):
            raise HTTPException(409, "맞출 것이 없습니다 — 점검한 뒤 문서가 바뀌었습니다. 다시 점검하세요")

        def run():
            r = table_style.conform(s.doc, report, keys)
            done.update(table=tid, done=r["done"], skipped=r["skipped"], formatted=len(r["formatted"]))
            return {"hosts": [tbl], "anchor": tid, "focus": None, "formatted": set(r["formatted"]),
                    "log": {"table": tid, "done": len(r["done"]), "skipped": len(r["skipped"]), "formatted": len(r["formatted"])}}
        return [tbl], run
    out = server._edit(doc_id, make, "tableStyle", {"table": tid, "keys": len(keys)})
    if isinstance(out, dict):
        out["styled"] = done
    return out
