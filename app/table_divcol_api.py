"""구분 기준 열 넣기 끝점(spec_테이블매니저 ② §13 「구분 기준 열 넣기」) — `GET /api/docs/{id}/tables/{tid}/divcol` · `POST …/divcol/apply`.
계산은 `app/table_divcol.py`(순수), 화면은 `app/static/table_divcol.js`(표 메뉴 → 2열 kind tblDivCol). LLM 을 부르지 않는다. 연구개발과제 문서(hwpx)만.

- 칸 역할은 쓰는 도구의 기본 역할(같은 사양서 ② §4 — 초안 + 유효한 사람 지정 · 양식의 확정본): `table_kv_api._judge` 를 그대로 쓴다. 보류된 지정은 계획의 `held` · 넣기는 409.
- 고를 값 = 프로젝트 구성의 값(`server._project_settings_sync` 뒤 `s.division["settings"]["values"]`): 기관 = `merge_gather_frame.orgs_of`(이름이 있는 것만) · 단계 = 「N단계」 ·
  차년도 = 편집 구역의 이름표 꼴(`zones.label_text` — 단계 둘 이상 「N단계 M차년도」 · 하나 「M차년도」). 값이 없으면 `ready: false`(화면이 「프로젝트 구성을 먼저 정하세요」).
- 권하는 값은 편집 구역의 귀속(`table_kinds_api._zone_of` — **세션 잠금 밖에서** 받아 둔다: `zones_api.read` 가 그 잠금을 제가 잡는다).
- 넣기 = 한 트랜잭션(`server._edit` — 실행 취소 1 · OWPML 지역 검사 · 기록 `tableDivCol`): 지금의 「열 넣기」(`doc.table_edit` col_right | col_left — 열 폭 규칙 그대로) → 기준이 여럿이면
  새 열을 본떠 더 넣음 → 새 열의 폭(`doc.set_col_widths` — 값 글 길이로 어림 · 표 폭 그대로) → 머리 칸 글 · 값 칸 글(`doc.set_text`).
"""
from fastapi import APIRouter, Body, HTTPException

from app import table_divcol as TD

router = APIRouter()
COLS_MAX = len(TD.BASES)
ITEMS_MAX = 2000


def _gate(s):
    from app import division_scan_api
    return getattr(s, "fmt", None) == "hwpx" and division_scan_api.enabled(s)


def _choices(s):
    """세션 잠금 안에서 — 고를 값 {org: [{key, label}], year: […], stage: […]} | None(프로젝트 구성 값이 없음)."""
    from app import server, zones
    from app.merge_gather_frame import orgs_of
    try:
        server._project_settings_sync(s)
    except Exception:   # noqa: BLE001 — 프로젝트 설정을 못 읽어도 세션의 값으로
        pass
    st = (getattr(s, "division", None) or {}).get("settings")
    values = st.get("values") if isinstance(st, dict) else None
    if not isinstance(values, dict) or not values.get("stages"):
        return None
    stages = [int(x) for x in values["stages"]]
    info = {"stages": stages}
    return {"org": [{"key": o["key"], "label": o["name"]} for o in orgs_of(values) if o.get("key") and o.get("name")],
            "year": [{"key": n, "label": zones.label_text({"year": n}, info, dims=("year",))} for n in range(1, sum(stages) + 1)],
            "stage": [{"key": n, "label": f"{n}단계"} for n in range(1, len(stages) + 1)]}


def _public_items(its):
    return [{k: it[k] for k in ("id", "label", "rows", "sub", "cells", "suggest", "by")} for it in its]


@router.get("/api/docs/{doc_id}/tables/{tid}/divcol")
def table_divcol_get(doc_id: str, tid: str):
    """구분 기준 열 넣기의 계획(문서 안 바뀜) → {gate: "rnd", ready, values, positions[{at, label, src, op, default}], items: {본뜰 열: [{id, label, rows, sub, cells, suggest, by}]},
    heads: {본뜰 열: [칸 id…]}, cols, rows, held, rev, planId} | {gate: "none"}(연구개발과제 문서가 아님 · docx). 404 표 없음 · 400 1칸 표."""
    from app import server, table_kv_api
    from app.table_kinds_api import _zone_of
    s = server._sess(doc_id)
    with s.lock:
        if not _gate(s):
            return {"gate": "none"}
        ready = _choices(s) is not None
    zone_of = _zone_of(s) if ready else None   # 편집 구역 — 잠금 밖에서(제가 잡는다)
    with s.lock:
        choices = _choices(s)
        j, held, _objs, _stage1 = table_kv_api._judge(s, tid)
        tb = j["table"]
        p = TD.plan(tb, s.rev, tid, zone_of, choices)
        return {"gate": "rnd", "ready": choices is not None, "values": choices or {"org": [], "year": [], "stage": []},
                "positions": p["positions"], "items": {str(k): _public_items(v["items"]) for k, v in p["bySrc"].items()},
                "heads": {str(k): v["heads"] for k, v in p["bySrc"].items()}, "cols": tb["cols"], "rows": tb["rows"],
                "zones": zone_of is not None, "held": held, "rev": s.rev, "planId": p["planId"], "source": j.get("source")}


def _body(body):
    """요청 → (rev, planId, at, [(기준, 머리 글)…](구분 순서), {항목 id: {기준: 글}}). 꼴이 틀리면 400."""
    rev, pid, at, cols, values = body.get("rev"), body.get("planId"), body.get("at"), body.get("cols"), body.get("values") or {}
    if not isinstance(rev, int) or isinstance(rev, bool):
        raise HTTPException(400, "rev(계획을 본 문서 차례)가 필요합니다")
    if not isinstance(pid, str) or not pid:
        raise HTTPException(400, "planId(계획의 도장)가 필요합니다")
    if not isinstance(at, int) or isinstance(at, bool):
        raise HTTPException(400, "at(넣을 자리 — 열 사이의 경계 번호)이 필요합니다")
    if not isinstance(cols, list) or not 1 <= len(cols) <= COLS_MAX:
        raise HTTPException(400, f"cols 는 [{{basis: {' | '.join(TD.BASES)}, head?}}] 1~{COLS_MAX}개")
    out, seen = [], set()
    for c in cols:
        b = c.get("basis") if isinstance(c, dict) else None
        head = c.get("head") if isinstance(c, dict) else None
        if b not in TD.BASES or b in seen or (head is not None and (not isinstance(head, str) or len(head) > TD.HEAD_MAX or "\n" in head)):
            raise HTTPException(400, f"cols 의 basis 는 {' · '.join(TD.BASES)} 가운데 하나씩 · head 는 {TD.HEAD_MAX}자 이하 한 줄")
        seen.add(b)
        out.append((b, (head if head is not None else TD.HEAD_TEXT[b]).strip()))
    out.sort(key=lambda x: TD.BASES.index(x[0]))
    if not isinstance(values, dict) or len(values) > ITEMS_MAX:
        raise HTTPException(400, f"values 는 {{항목 id: {{기준: 글}}}} — {ITEMS_MAX}개까지")
    vals = {}
    for k, v in values.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            raise HTTPException(400, "values 는 {항목 id: {기준: 글}}")
        row = {}
        for b, t in v.items():
            if b not in seen or not isinstance(t, str) or len(t) > TD.TEXT_MAX or "\n" in t:
                raise HTTPException(400, f"values 의 기준은 cols 에 있는 것 · 글은 {TD.TEXT_MAX}자 이하 한 줄")
            if t.strip():
                row[b] = t.strip()
        if row:
            vals[k] = row
    return rev, pid, at, out, vals


@router.post("/api/docs/{doc_id}/tables/{tid}/divcol/apply")
def table_divcol_apply(doc_id: str, tid: str, body: dict = Body(...)):
    """구분 기준 열을 넣고 값을 적는다 — {rev, planId, at, cols: [{basis, head?}], values: {항목 id: {기준: 글}}}.
    한 트랜잭션(실행 취소 1 · OWPML 지역 검사 · 기록 `tableDivCol`). 응답 = 구조 편집 응답 + `divcol {table, at, cols: [새 열 번호…], filled: n, heads: n}`.
    400 꼴 · 관문 밖 · 자리가 아님 · 모르는 항목 / 404 표 없음 / 409 rev 가 다름 · 표가 바뀜(planId) · 보류된 헤더 지정."""
    from app import server, table_heads, table_kv_api
    rev, pid, at, cols, vals = _body(body if isinstance(body, dict) else {})
    done = {}

    def make(s):
        if not _gate(s):
            raise HTTPException(400, "구분 기준 열 넣기는 연구개발과제 문서(hwpx)에서만 씁니다")
        tbl = table_kv_api._live(s, tid)
        if rev != s.rev:
            raise HTTPException(409, "계획을 본 뒤 문서가 바뀌었습니다 — 다시 읽은 뒤 넣으세요")
        j, held, _objs, _stage1 = table_kv_api._judge(s, tid)
        tb = j["table"]
        p = TD.plan(tb, s.rev, tid)
        if p["planId"] != pid:
            raise HTTPException(409, "표가 바뀌었습니다 — 다시 여세요")
        if held:
            raise HTTPException(409, f"헤더 지정 {len(held)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요")
        pos = next((x for x in p["positions"] if x["at"] == at), None)
        if pos is None:
            raise HTTPException(400, "그 자리에는 구분 기준 열을 넣을 수 없습니다 — 자리를 다시 고르세요")
        meta = p["bySrc"][pos["src"]]
        known = {it["id"] for it in meta["items"]}
        if set(vals) - known:
            raise HTTPException(400, "값을 적을 줄 가운데 이 표에 없는 것이 있습니다 — 다시 여세요")
        nc0 = int(tb["cols"])

        def run():
            opts = {"fields": lambda t: table_heads.fields_of(s.doc, t, table_heads.get(s.id, t), doc_key=getattr(s, "doc_key", None))}
            first, rest = cols[0][0], [b for b, _ in cols[1:]]
            res = s.doc.table_edit(pos["cell"], pos["op"], None, opts)
            new = {src: (cp if pos["op"] == "col_right" else src) for src, cp in (res.get("map") or {}).items()}   # 본뜬 열의 칸 id → 새 열의 칸 id
            if not new:
                raise ValueError("새 열을 만들지 못했습니다")
            made = {first: new}
            seed = next(iter(new.values()))
            for b in reversed(rest):   # 새 열을 본떠 그 바로 오른쪽에 — 거꾸로 넣어 구분 순서(왼쪽 → 오른쪽)가 되게
                r2 = s.doc.table_edit(seed, "col_right", None, opts)
                m2 = r2.get("map") or {}
                made[b] = {src: m2[cid] for src, cid in new.items() if cid in m2}
            order = [b for b, _ in cols]
            heads = dict(cols)
            fixed, total = {}, _total_width(s, tid)
            for k, b in enumerate(order):
                texts = [heads[b]] + [v[b] for v in vals.values() if b in v]
                fixed[at + k] = TD.width_of(texts, total)
            try:
                s.doc.set_col_widths(tid, fixed)
            except ValueError:
                pass   # 좁은 표 — 폭은 열 넣기의 규칙 그대로 둔다
            filled = nh = 0
            for b in order:
                cc = made[b]
                for h in meta["heads"]:
                    if h in cc and heads[b]:
                        s.doc.set_text(cc[h], heads[b])
                        nh += 1
                for item_id, v in vals.items():
                    if b in v and item_id in cc:
                        s.doc.set_text(cc[item_id], v[b])
                        filled += 1
            done.update(table=tid, at=at, cols=list(range(at, at + len(order))), bases=order, filled=filled, heads=nh, before=nc0)
            return {"hosts": [tbl], "anchor": tid, "focus": None,
                    "log": {"table": tid, "at": at, "bases": order, "filled": filled, "heads": nh}}
        return [tbl], run
    out = server._edit(doc_id, make, "tableDivCol", {"table": tid, "at": at, "bases": [b for b, _ in cols], "items": len(vals)})
    if isinstance(out, dict):
        out["divcol"] = done
    return out


def _total_width(s, tid):
    """표의 폭(HWPUNIT) — 칸 폭의 합(첫 행에서). 못 읽으면 0(폭 어림이 상한만 안 건다)."""
    try:
        tbl, cells, nr, nc = s.doc._tgrid(s.doc._ids.get(tid))
        return sum(s.doc._tsizes(cells, nr, nc)[1])
    except Exception:   # noqa: BLE001
        return 0
