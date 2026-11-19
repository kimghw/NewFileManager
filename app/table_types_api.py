"""양식의 표 판정 끝점(spec_테이블매니저 ② §10 「양식의 표 판정」) — `GET/PUT …/tables/{tid}/type` · `GET …/tables/types` · `GET /api/table-types` · `DELETE /api/table-types/{entry}` · `POST /api/table-types/restore`.
저장 · 견주기는 `app/table_types.py`(순수), 화면은 `app/static/table_types.js`(표 메뉴 「양식의 표 판정…」 → 2열 kind tblType). 문서를 바꾸지 않고 LLM 도 부르지 않는다. hwpx 만.

`template_for(s, tb)` 는 다른 끝점 모듈(표 서식 점검 · 키-값)이 부른다 — 그 표에 맞는 확정본(`table_manager.judge` 의 `template` 꼴) | None.

- **양식** = 「양식 정보」 의 양식(`heading_forms.for_session` — 사람이 고름 → 올린 원본의 sha256 → 파일 이름 꼴). 양식이 정해지지 않은 문서에는 이 기능이 없다(응답 `form: null` · 확정은 400).
- **확정**(`PUT …/type`)이 저장하는 것 = 지금 그 표의 판정 **전체**: 표 서식 점검과 같은 재료(`tables_api._table_now` · `_heads_now` · 끝난 3단계 결과 · 지금 맞는 확정본)로 낸 `table_manager.judge` 의 최종 역할 · 띠.
  보류된 헤더 지정이 있으면 409(같은 사양서 ② §3 「사람의 헤더 지정」) · 문서 차례(`rev`)가 다르면 409 · 맞는 확정본이 둘 이상이면 409(지운 뒤에) · 화면이 본 확정본(`match`)과 지금 것이 다르면 409.
  확정본은 사람이 「이 판정으로 확정」 을 누를 때만 생긴다 — 읽는 끝점은 아무것도 저장하지 않는다.
- **확정본의 역할은 그 작업의 헤더 지정과 따로 선 층**이다: 판정의 칸에 `user` 는 그 작업에서 사람이 지정한 칸에만 붙는다(응답의 칸마다 `by`: user | template | stage3 | draft).
- 지운 확정본은 알림의 「되돌리기」 가 `POST /api/table-types/restore {id}` 로 그대로 되살린다 — 서버가 지닌 지운 확정본에서만(요청의 확정본은 저장하지 않는다).
- **더 좁은 확정본이 먼저**(`table_types.pick`) · **같이 쓰이는 표**(`also` — 이 문서에서 그 확정본이 맞는 다른 표와 다른 칸 수) · **고치기와 따로 확정**(`PUT … {mode}`) — 한 표의 확정이 구조가 같은 다른 표의 판정을 모르게 바꾸지 않게(astra 4차 7번)."""
from fastapi import APIRouter, Body, HTTPException, Query

from app import heading_forms, table_types

router = APIRouter()
TEXT_MAX = 30     # 판정 격자에 보이는 칸 글
NO_FORM = "양식이 정해지지 않은 문서입니다 — 양식 정보에서 양식을 고르세요"


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    return server._sess(doc_id)


def _form(s):
    """이 문서의 양식 {key, name} | None(양식이 정해지지 않음 · 못 읽음). 파일 읽기뿐(세션 잠금을 잡지 않는다)."""
    try:
        f = heading_forms.for_session(s)
    except (OSError, ValueError):
        return None
    return {"key": f["key"], "name": f.get("name") or f["key"]} if f else None


def template_for(s, tb):
    """세션 s 의 문서에서 표 tb(heading_tables.collect 꼴 — 칸마다 row · col · rs · cs · shaded · textFull)에 **맞는** 양식의 확정본 → {id, rev, roles, bands} | None
    (양식이 정해지지 않은 문서 · 확정본 없음 · 구조나 머리글이 달라 안 맞음 · 둘 이상 맞음). 세션 잠금 안에서 불러도 된다(파일 읽기뿐 — 잠금을 잡지 않는다)."""
    if not isinstance(tb, dict) or not tb.get("cells") or getattr(s, "fmt", None) != "hwpx":
        return None
    form = _form(s)
    if form is None:
        return None
    hit = table_types.match(table_types.list(form["key"]), tb)
    return table_types.template_of(hit) if hit else None


def _hwpx(s):
    if getattr(s, "fmt", None) != "hwpx":
        raise HTTPException(400, "양식의 표 판정은 지금 hwpx 문서만 됩니다")


def _live(s, tid):
    el = s.doc._ids.get(tid) if isinstance(tid, str) else None
    if el is None or not str(el.tag).endswith("}tbl") or not s.doc._attached(el):
        raise HTTPException(404, "그 표가 지금 문서에 없습니다 — 다시 고르세요")


def _why(e, tb):
    """확정본이 이 표에 안 맞는 까닭의 화면 글 | ""(맞음) — 견준 두 값에는 이름을 붙인다(확정본 · 지금)."""
    w = table_types.why_not(e, tb)
    if w is None:
        return ""
    if w["what"] == "size":
        return f"행 · 열 · 칸 수가 다릅니다 — 확정본 {e['rows']}×{e['cols']} · 칸 {len(e['geometry'])} / 지금 {tb['rows']}×{tb['cols']} · 칸 {len(tb['cells'])}"
    if w["what"] == "geometry":
        return "칸의 자리 · 병합 · 음영이 다릅니다"
    bad = w["labels"]

    def cut(t):
        return (t[:20] + "…") if len(t) > 20 else (t or "(빈 칸)")
    return "머리글이 다릅니다 — " + " · ".join(f"{b['ref']} 확정본 「{cut(b['template'])}」 / 지금 「{cut(b['now'])}」" for b in bad[:3]) + (f" 밖에 {len(bad) - 3}칸" if len(bad) > 3 else "")


def _read(s, tid, form, entries):
    """세션 잠금 안에서 — 표 tid 의 지금 판정과 그 표에 맞는 확정본 → dict(j · tb · held · hits · hit · stage1 · stored · same · user).
    판정의 재료는 표 서식 점검(`tables_api._style_tb`)과 같다. 400 1칸 표 · 너무 큰 표."""
    from app import heading_runs, table_manager, tables_api
    stage1, tb = tables_api._table_now(s, tid)
    if tb is None:
        raise HTTPException(400, "칸 역할을 읽지 못한 표입니다(1칸 표 · 상자)")
    user, held = tables_api._heads_now(s, tid, tb)
    t3 = heading_runs.tables(s) or {}
    stored = next((t for t in t3.get("tables") or [] if isinstance(t, dict) and t.get("id") == tid), None)
    same = (t3.get("meta") or {}).get("rev") == s.rev
    hits = table_types.matches(entries, tb) if form else []
    hit = table_types.pick(hits)   # 하나면 그것 · 둘 이상이면 더 좁은 것(고정 머리글 칸이 다른 것들을 다 품고 더 많은 것) · 없으면 어느 쪽도 안 쓴다
    j = table_manager.judge(stage1, tid, stored=stored, user=user, same_doc=same, template=table_types.template_of(hit) if hit else None)
    if hit is not None and j["source"] != "template":   # 저장된 확정본은 늘 그 표를 다 덮는다(`table_types.clean`) — 그래도 못 얹었으면 안 맞는 것으로 본다
        hits, hit = [], None
    return {"j": j, "tb": tb, "held": held, "hits": hits, "hit": hit, "stage1": stage1, "stored": stored, "same": same, "user": user, "t3": t3}


def _variable(ctx):
    """가변 머리글의 지금 기본 — 확정본이 맞으면 그 확정본이 가변으로 둔 자리, 아니면 구분 기준의 값 머리. 지금 판정에서 헤더 · 제목 · 안내 역할인 칸만."""
    table = ctx["j"]["table"]
    ids = table_types.variable_cells(ctx["hit"], table) if ctx["hit"] else table_types.default_variable(table)
    labels = {x["id"] for x in table["cells"] if x["role"] in table_types.LABEL_ROLES}
    return [i for i in ids if i in labels]


def _also(s, tid, entries, hit, t3):
    """세션 잠금 안에서 — 이 문서에서 확정본 hit 가 맞아 쓰이는 **다른 표** [{table, differs: 그 표의 확정본 없이 낸 판정(3단계 결과 · 초안)이 확정본과 다른 칸 수}](문서 순).
    칸 수가 그 확정본과 같은 표만 읽는다(`…/tables/types` 와 같은 거르기 — 맞을 수 없는 표의 글을 다시 읽지 않는다)."""
    from app import heading_rules, table_excel, table_manager
    n, store, out = len(hit["geometry"]), None, []
    stored = {t.get("id"): t for t in t3.get("tables") or [] if isinstance(t, dict)}
    same = (t3.get("meta") or {}).get("rev") == s.rev
    for i, el in [*s.doc._ids.items()]:
        if i == tid or not str(el.tag).endswith("}tbl") or not s.doc._attached(el) or len(s.doc._tgrid(el)[1]) != n:
            continue
        store = heading_rules.load() if store is None else store   # 문단 종류 규칙 — 표마다 다시 읽지 않게 한 번만
        j0 = table_manager.judge(table_excel.records(s.doc, i, store, getattr(s, "doc_key", None)) or {"paras": []}, i, stored=stored.get(i), same_doc=same)
        if j0 is not None and (table_types.match(entries, j0["table"]) or {}).get("id") == hit["id"]:
            out.append({"table": i, "differs": len(table_types.differs(hit, j0["table"]))})
    return out


def _choose(hit, entry):
    """그 표에 맞아 쓰이는 확정본(hit)과 지금 확정하려는 것(entry — `entry_of` 의 결과) 사이 → {needed: 고치기 · 따로 확정 가운데 골라야 하나(판정이 확정본과 다름), canNew: 「이 표만 따로 확정」 을 할 수 있나, why: 못 하는 까닭}."""
    body = table_types.clean(entry)
    if table_types.same_judgment(hit, body):
        return {"needed": False, "canNew": False, "why": "지금 판정이 확정본과 같습니다 — 따로 확정할 것이 없습니다"}
    ok, why = table_types.separable(hit, body)
    return {"needed": True, "canNew": ok, "why": why}


def _view(s, tid, form, entries, ctx):
    """세션 잠금 안에서 — `GET …/type` 의 응답."""
    from app import table_kv, table_manager, table_prune
    j, tb, hit, hits = ctx["j"], ctx["tb"], ctx["hit"], ctx["hits"]
    table = j["table"]
    kind = table_kv.type_key(table)
    state = "confirmed" if hit else "ambiguous" if len(hits) > 1 else "changed" if any(e["type"] == kind for e in entries) else "none"
    differs, base, also, choose = [], None, [], None
    var = set(_variable(ctx))
    if hit:   # 확정본 **없이** 낸 판정(3단계 결과 · 초안)의 자동 역할과 견준다 — 확정본이 무엇을 바로잡고 있는지
        j0 = table_manager.judge(ctx["stage1"], tid, stored=ctx["stored"], user=ctx["user"], same_doc=ctx["same"])
        differs, base = table_types.differs(hit, j0["table"]), j0["source"]
        also = _also(s, tid, entries, hit, ctx["t3"])
        try:   # 지금 판정(가변 머리글은 지금 기본)으로 확정한다면 — 화면은 가변 체크를 바꿀 때 같은 규칙으로 다시 센다(칸의 role · auto · variable · fixed)
            choose = _choose(hit, table_types.entry_of(j, form["key"], [*var]))
        except ValueError as e:
            choose = {"needed": True, "canNew": False, "why": str(e)}
    fixed = table_types.fixed_cells(hit) if hit else set()
    cells = [{"id": x["id"], "row": x["row"], "col": x["col"], "rs": x["rs"], "cs": x["cs"], "ref": table_types.ref(x["row"], x["col"]), "role": x["role"], "auto": x.get("auto"),
              "by": "user" if x.get("user") else j["source"], "text": (x.get("textFull") or "")[:TEXT_MAX], "shaded": bool(x.get("shaded")),
              "label": x["role"] in table_types.LABEL_ROLES, "variable": x["id"] in var, "basis": x.get("basisKind") == "value",
              "fixed": (x["row"], x["col"]) in fixed,   # 지금 쓰이는 확정본이 고정 머리글로 둔 자리
              "empty": x["role"] in table_types.LABEL_ROLES and table_prune.cell_empty(x)} for x in table["cells"]]   # empty = 글이 없거나 자리표시뿐인 머리 칸(사람이 채우는 칸일 수 있다 — 화면이 가변으로 둘지 묻는다)
    variants = []
    for e in entries:   # 같은 타입의 확정본 + 이 표에 맞는 것 + 격자가 꼭 같고 머리글 몇 칸만 다른 것(가변으로 두지 않은 기관 이름 · 연도처럼 — 타입은 음영 칸의 글이라 그런 표는 타입부터 다르다)
        miss = table_types.why_not(e, tb)
        close = miss is not None and miss["what"] == "labels" and len(miss["labels"]) <= max(1, sum(1 for x in e["labels"] if not x[3]) // 4)
        if e["type"] == kind or miss is None or close:
            why = _why(e, tb)
            variants.append({**table_types.summary(e), "fits": not why, "why": why, "used": bool(hit and hit["id"] == e["id"])})
    return {"table": tid, "form": form, "type": kind, "name": table_types.name_of(table, var),
            "match": {"id": hit["id"], "rev": hit["rev"], "at": hit.get("at")} if hit else None, "state": state, "differs": differs, "differsFrom": base,
            "also": also, "choose": choose,
            "judgment": {"table": tid, "rows": table["rows"], "cols": table["cols"], "source": j["source"], "reuse": j["reuse"], "cells": cells,
                         "subs": [{k: b[k] for k in table_types.BAND_KEYS} for b in j["subs"]]},
            "held": ctx["held"], "variants": variants, "rev": s.rev}


@router.get("/api/docs/{doc_id}/tables/{tid}/type")
def table_type_get(doc_id: str, tid: str):
    """표 하나의 양식 판정 상태 → {table, form: {key, name} | null, type, name, match: {id, rev, at} | null, state: confirmed | none | ambiguous | changed,
    differs: [{cell, ref, now, template}](확정본이 맞을 때 — 확정본 없이 낸 판정(`differsFrom`: stage3 | draft)의 역할이 확정본과 다른 칸),
    judgment: {table, rows, cols, source, reuse, cells: [{id, row, col, rs, cs, ref, role, auto, by: user | template | stage3 | draft, text(30자), shaded, label, variable, basis, empty}], subs},
    also: [{table, differs: n}](확정본이 맞을 때 — 이 문서에서 그 확정본이 맞아 쓰이는 **다른 표**와, 그 표의 확정본 없이 낸 판정이 확정본과 다른 칸 수),
    choose: {needed, canNew, why} | null(확정본이 맞을 때 — 지금 판정이 그것과 달라 「이 확정본 고치기」 · 「이 표만 따로 확정」 가운데 골라야 하나 · 따로 확정할 수 있나),
    held, variants: [같은 타입의 확정본 · 이 표에 맞는 것 · 격자가 꼭 같고 머리글 몇 칸만 다른 것의 요약 + fits · why(안 맞는 까닭) · used], rev}. 칸의 `fixed` = 지금 쓰이는 확정본이 고정 머리글로 둔 자리.
    문서는 안 바뀌고 아무것도 저장하지 않는다. hwpx 만 · 표 없음 404 · 1칸 표 400."""
    s = _sess(doc_id)
    _hwpx(s)
    form = _form(s)
    entries = table_types.list(form["key"]) if form else []
    with s.lock:
        _live(s, tid)
        return _view(s, tid, form, entries, _read(s, tid, form, entries))


@router.put("/api/docs/{doc_id}/tables/{tid}/type")
def table_type_put(doc_id: str, tid: str, body: dict = Body(...)):
    """이 판정으로 확정 — {rev, variable?: [칸 id…](가변 머리글 — 안 주면 지금 기본), match?: {id, rev} | null(화면이 본 확정본 — 주면 지금 것과 견준다), mode?: "update" | "new"}
    → `GET …/type` 의 응답(`also` 포함) + `saved {id, rev, created(새 확정본인가), overlaps: [함께 맞아 어느 쪽도 안 쓰일 수 있는 다른 확정본 id…]}`.
    지금 그 표의 판정 전체(헤더 지정 · 확정본 · 3단계 결과 · 초안을 합친 최종 역할 · 띠)를 양식의 확정본으로 저장한다(문서는 안 바뀜).
    **고치기와 따로 확정**(spec_테이블매니저 ② §10 「양식의 표 판정」): 그 표에 맞아 쓰이는 확정본이 있고 지금 판정이 그것과 다르면 사람이 고른 `mode` 가 있어야 한다 —
    `update` = 그 확정본을 고친다(`rev` +1 — 그 확정본이 맞는 모든 표의 판정이 바뀐다) · `new` = 이 표만 따로 확정(새 확정본 — 지금 확정본의 고정 머리글 칸을 다 품고 글이 있는 고정 머리글 칸이 더 있을 때만: 그래야 이 표에 새 것이 쓰인다).
    맞는 확정본이 없으면 `mode` 는 안 본다(새 확정본), 판정이 확정본과 같으면 그 확정본을 다시 확정한다(`rev` +1 — `new` 는 409).
    400 양식이 정해지지 않은 문서 · rev 없음 · variable · mode 꼴 / 409 문서 차례 다름 · 보류된 헤더 지정 · 맞는 확정본이 둘 이상이고 더 좁은 것이 없음 · 확정본이 그 사이 바뀜 · mode 를 골라야 함 · 따로 확정할 수 없음 / 503 저장 파일 손상 · 못 씀."""
    from app import tables_api, works
    body = body if isinstance(body, dict) else {}
    rev, variable, seen, mode = body.get("rev"), body.get("variable"), body.get("match"), body.get("mode")
    if not tables_api._is_rev(rev):
        raise HTTPException(400, "rev 가 필요합니다 — 판정을 읽을 때 받은 rev 를 같이 보내세요")
    if mode not in (None, "update", "new"):
        raise HTTPException(400, "mode 는 update(이 확정본 고치기) 또는 new(이 표만 따로 확정)")
    if variable is not None and not (isinstance(variable, list) and len(variable) <= table_types.CELLS_MAX and all(isinstance(v, str) for v in variable)):
        raise HTTPException(400, "variable 은 가변 머리글로 둘 칸 id 의 목록")
    if "match" in body and seen is not None and not (isinstance(seen, dict) and isinstance(seen.get("id"), str) and tables_api._is_rev(seen.get("rev"))):
        raise HTTPException(400, "match 는 {id, rev}(화면이 본 확정본) 또는 null")
    s = _sess(doc_id)
    _hwpx(s)
    form = _form(s)
    if form is None:
        raise HTTPException(400, NO_FORM)
    entries = table_types.list(form["key"])
    with s.lock:
        _live(s, tid)
        if rev != s.rev:
            raise HTTPException(409, "판정을 본 뒤 문서가 바뀌었습니다 — 다시 읽으세요")
        ctx = _read(s, tid, form, entries)
        tables_api._held_stop(ctx["held"])
        hit, j = ctx["hit"], ctx["j"]
        if hit is None and len(ctx["hits"]) > 1:
            raise HTTPException(409, f"이 표에 맞는 확정본이 {len(ctx['hits'])}개입니다 — 안 쓰는 확정본을 지운 뒤 확정하세요")
        if "match" in body and (None if hit is None else (hit["id"], hit["rev"])) != (None if seen is None else (seen["id"], seen["rev"])):
            raise HTTPException(409, "확정본이 그 사이 바뀌었습니다 — 다시 읽으세요")
        labels = {x["id"] for x in j["table"]["cells"] if x["role"] in table_types.LABEL_ROLES}
        if variable is not None and any(v not in labels for v in variable):
            raise HTTPException(400, "가변 머리글은 헤더 · 제목 · 안내 칸에서만 고릅니다 — 판정을 다시 읽으세요")
        entry = table_types.entry_of(j, form["key"], _variable(ctx) if variable is None else variable,
                                     origin={"work": s.id, "table": tid, "rev": s.rev, "source": j["source"]})
        fresh = hit is None   # 새 확정본으로 저장하나(맞는 확정본이 없음 · 「이 표만 따로 확정」)
        try:
            if hit is not None:
                ch = _choose(hit, entry)
                if ch["needed"] and mode is None:
                    raise HTTPException(409, "지금 판정이 이 표에 쓰이는 확정본과 다릅니다 — 「이 확정본 고치기」(그 확정본이 맞는 모든 표의 판정이 바뀝니다)나 「이 표만 따로 확정」 을 고르세요")
                if mode == "new":
                    if not ch["canNew"]:
                        raise HTTPException(409, f"이 표만 따로 확정할 수 없습니다 — {ch['why']}")
                    fresh = True
            saved = table_types.put(entry) if fresh else table_types.put(entry, replace=hit["id"], expect=hit["rev"])
        except table_types.StaleVersion as e:
            raise HTTPException(409, str(e)) from e
        except table_types.Broken as e:
            raise HTTPException(503, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except OSError as e:
            raise HTTPException(503, f"양식의 표 판정을 저장하지 못했습니다: {e}") from e
        made = "new" if saved["rev"] == 1 else "update"   # 실제로 한 일 — 새 확정본 | 있던 것을 고침
        works.log(s.id, "tableType", rev=s.rev, table=tid, form=form["key"], entry=saved["id"], entryRev=saved["rev"], created=made == "new", source=j["source"],
                  cells=len(saved["geometry"]), variable=sum(1 for x in saved["labels"] if x[3]))
        entries = table_types.list(form["key"])
        out = _view(s, tid, form, entries, _read(s, tid, form, entries))
    # overlaps = 이 확정본과 함께 맞아 어느 쪽도 안 쓰이는 표가 있을 수 있는 다른 확정본(격자가 같고 고정 머리글이 어긋나지 않는데 서로를 품지 않음) — 화면이 알린다(저절로 지우지 않는다)
    out["saved"] = {"id": saved["id"], "rev": saved["rev"], "created": made == "new", "overlaps": [e["id"] for e in table_types.overlaps(saved, entries)]}
    return out


@router.get("/api/docs/{doc_id}/tables/types")
def tables_types(doc_id: str, full: bool = Query(default=False)):
    """문서의 표마다 {table, type, state} — 「테이블」 탭의 상태 표지 · 「확정하고 다음 표」 가 읽는다 → {form: {key, name} | null, entries: 그 양식의 확정본 수, tables: […], rev}.
    양식이 정해지지 않은 문서 · hwpx 아님 = `{form: null, tables: []}`. 1칸 표 · 너무 큰 표는 목록에 없다.
    **칸 수가 같은 확정본이 하나도 없는 표는 읽지 않는다**(`state: none` · `type: null` — 맞을 수 없는 표다: 표가 백 개가 넘는 문서에서 표마다 글을 다시 읽지 않게). 그런 표는 「같은 타입이나 구조가 달라 안 맞음」(changed)이어도
    none 으로 나온다 — 모든 표를 읽으려면 `?full=1`. 표마다 세션 잠금을 따로 잡는다(타자를 오래 막지 않게) — 읽는 사이 문서가 바뀌었으면 `rev` 는 끝났을 때의 것이다."""
    from app import heading_rules, table_excel, table_kv, table_manager
    s = _sess(doc_id)
    form = _form(s) if getattr(s, "fmt", None) == "hwpx" else None
    if form is None:
        return {"form": None, "entries": 0, "tables": [], "rev": s.rev}
    entries = table_types.list(form["key"])
    sizes = {len(e["geometry"]) for e in entries}
    store = heading_rules.load() if entries or full else None   # 문단 종류 규칙 — 표마다 다시 읽지 않게 한 번만(`table_excel.records` 의 store)
    with s.lock:
        ids = [i for i, el in s.doc._ids.items() if str(el.tag).endswith("}tbl") and s.doc._attached(el)]
    out = []
    for tid in ids:
        with s.lock:
            el = s.doc._ids.get(tid)
            if el is None or not s.doc._attached(el):
                continue
            n = len(s.doc._tgrid(el)[1])
            if n < 2 or n > table_excel.MAX_CELLS:
                continue
            if not full and n not in sizes:
                out.append({"table": tid, "type": None, "state": "none"})
                continue
            j = table_manager.judge(table_excel.records(s.doc, tid, store, getattr(s, "doc_key", None)) or {"paras": []}, tid)   # 초안 — 타입(머리글 지문)과 격자 · 머리글 글만 쓴다(역할은 안 본다)
            if j is None:
                continue
            kind = table_kv.type_key(j["table"])
            out.append({"table": tid, "type": kind, "state": table_types.state_of(entries, j["table"], kind)})
    return {"form": form, "entries": len(entries), "tables": out, "rev": s.rev}


@router.get("/api/table-types")
def table_types_list(form: str | None = Query(default=None)):
    """그 양식의 확정본 목록(요약 — 최근에 확정한 것부터) → {form, entries: [{id, rev, at, form, type, name, rows, cols, cells, fixed, variable, from}]}. form 을 안 주면 모든 양식의 것."""
    return {"form": form, "entries": [table_types.summary(e) for e in table_types.list(form)]}


@router.delete("/api/table-types/{entry}")
def table_types_delete(entry: str):
    """확정본 지우기 → {removed: 지운 확정본}. 지운 것은 서버가 지닌다(마지막 20개) — `POST /api/table-types/restore {id}` 로 되살린다. 404 없는 id · 503 저장 파일 손상 · 못 씀."""
    try:
        return {"removed": table_types.delete(entry)}
    except KeyError as e:
        raise HTTPException(404, "그 확정본이 없습니다(이미 지워졌습니다)") from e
    except table_types.Broken as e:
        raise HTTPException(503, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"확정본을 지우지 못했습니다: {e}") from e


@router.post("/api/table-types/restore")
def table_types_restore(body: dict = Body(...)):
    """지운 확정본 되살리기 — {id: 지운 확정본의 id} → {entry: 요약}. 알림의 「되돌리기」 가 부른다(새 확정이 아니다 — id · 판 그대로).
    **서버가 지닌 지운 확정본(저장 파일의 `removed` — 마지막 20개)에서만** 되살린다 — 요청이 보낸 확정본은 읽지도 저장하지도 않는다(astra 4차: 요청의 확정본을 믿어 `at` 에 무한대가 든 것 · 표 밖의 띠 · 지운 적 없는 새 id 가 저장됐다).
    400 id 가 없거나 꼴이 아님 / 404 그 id 의 지운 확정본이 없음 / 409 그 id 가 이미 있음 · 같은 구조의 확정본이 그 사이 생김 / 503 저장 파일 손상 · 못 씀."""
    eid = body.get("id") if isinstance(body, dict) else None
    if not isinstance(eid, str) or not table_types._ID.match(eid):
        raise HTTPException(400, "id(지운 확정본의 id)가 필요합니다 — 확정본 자체는 받지 않습니다")
    try:
        return {"entry": table_types.summary(table_types.restore(eid))}
    except KeyError as e:
        raise HTTPException(404, "되살릴 확정본이 없습니다 — 지운 적이 없거나, 지운 지 오래되어 남아 있지 않습니다") from e
    except table_types.Broken as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"확정본을 되살리지 못했습니다: {e}") from e
