"""표 모듈 API(spec_헤딩_추출 ② §10 「모듈」) — 표만 다루는 끝점을 한곳에(사용자 2026-11-10 "본문 따로, 테이블 따로"): 표 지침(표 에이전트 입력) ·
엑셀식 보기의 사용자 수식 저장 · 에이전트 입력 묶음 미리보기 · **표 행·열 편집**(`POST …/table` — 2026-11-10 astra 협의로 server.py 에서 옮김, URL·본문·응답 그대로;
트랜잭션 `server._edit` — 잠금·스냅샷·OWPML 검사·실행 취소 스택·기록 — 은 본문 편집과 공유한다. 실행 취소가 문서마다 한 줄이어야 하므로 — spec_owpml_편집 ② §2·§3).
본문(문단·헤딩) 끝점은 server.py 에 그대로.

여기 두지 않은 표 끝점: 3단계 표 구조 결과(`GET …/headings/tables`·`…/xlsx`)는 헤딩 추출 실행(1·2·3단계)의 일부라 server.py 「헤딩 추출」 절에.
저장소·묶음 글은 `app/table_agent.py`, 작성요령·표 구조는 `app/heading_tables.py`, 행·열 편집의 형식 중립부(`TABLE_OPS`·`table_range`)는 `app/table_ops.py`."""
from fastapi import APIRouter, Body, HTTPException

from app import heading_rules, heading_runs, table_agent

router = APIRouter()


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    return server._sess(doc_id)


def is_table(s, tid):
    """문서의 표 블록인가 — 블록 id 로 요소를 찾아 tbl 인지 본다(hwpx hp:tbl · docx w:tbl)."""
    el = s.doc._ids.get(tid)
    return el is not None and str(el.tag).endswith("}tbl")


def agent_view(s, tid):
    """{table, stage3, ident, notes, common, own, prompt} — tid `_common` 은 공통 지침(ident null · notes [] · own null)."""
    t3 = heading_runs.tables(s)
    tb = next((x for x in (t3 or {}).get("tables", []) if x["id"] == tid), None) if tid != table_agent.COMMON else None
    common = table_agent.get(s.id, table_agent.COMMON)
    own = table_agent.get(s.id, tid) if tid != table_agent.COMMON else None
    return {"table": tid, "stage3": tb is not None, "ident": table_agent.ident(tb), "notes": (tb or {}).get("notes") or [], "common": common, "own": own,
            "prompt": table_agent.prompt(tb, common, own, tid=tid)}


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
    """{instructions?, formulas?, version?} — `_common` 은 instructions 만. version 이 다르면 409 · 값이 틀리면 400 · 파일 쓰기 실패 503."""
    s = _sess(doc_id)
    _check(s, tid)
    try:
        table_agent.save(s.id, tid, instructions=body.get("instructions"), formulas=body.get("formulas"), expect=body.get("version"))
    except heading_rules.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, f"그런 표가 없습니다: {tid}") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"표 지침을 저장하지 못했습니다: {e}") from e
    return agent_view(s, tid)


# ---- 표 행·열 편집(spec_owpml_편집 ② §2 「표 행·열」·② §4 「표 칸 고르기」) ------------------------------------------------------------------------------
@router.post("/api/docs/{doc_id}/table")
def table_edit(doc_id: str, body: dict = Body(...)):
    """표 행·열 {id: 칸 안 문단(또는 칸), op: row_above|row_below|row_delete|col_left|col_right|col_delete,
    range?: {r0, c0, r1, c1}} — range(격자 좌표, 끌어 고른 칸 묶음)가 있으면 그 칸 대신 그 범위의 행·열 기준. 어댑터 `doc.table_edit`(hwpx_struct·docx_struct).
    응답·검사 대상은 늘 표를 품은 본문 문단(= 표 전체): 기준 칸이 지워져도 남은 표의 OWPML 지역 검사와 `tops` 가 같은 잠금 안에서 나온다(astra P1, 2026-11-10 — 전에는
    hosts 가 비어 검사가 빠지고 잠금을 풀었다 다시 잡아 블록을 찾았다)."""
    from app import server  # 트랜잭션(_edit)·세션은 server 것 — 부를 때 가져온다(순환 import 피함)
    bid, op, rng = body.get("id"), body.get("op"), body.get("range")

    def make(s):
        el = server._para_el(s, bid, cell_ok=True)
        host = s.kit["struct"].top_host(s.doc, el)  # 표를 품은 본문 문단 — 편집 전에 잡아 둔다(행·열을 지워 기준 칸이 사라져도 남는다)

        def run():
            s.doc.table_edit(bid, op, rng)
            keep = s.doc._attached(el)
            hosts = [host] if host is not None and s.doc._attached(host) else ([el] if keep else [])
            return {"hosts": hosts, "anchor": bid, "focus": {"id": bid, "offset": 0} if keep and el.tag == s.kit["para"] else None}
        return [el], run
    return server._edit(doc_id, make, "table", body)
