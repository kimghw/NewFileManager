"""구분 기준 자리 표시의 「표 구조」 보탬 — 서비스(spec_구분_기준 ② §25). 계산은 `division_struct`(순수).

members 끝점(`server.divisions_members`)이 판독 보탬(`division_scan_api.reads`) 뒤에 붙인다. 판독(scan)과 그 고정본은 건드리지 않는다(§23 한 방향).
- 표마다 테이블 매니저의 「지금 판정」(`table_manager.judge` — 지금 레코드 + 끝난 3단계 결과의 그 표 + 유효한 사람 헤더 지정)을 쓴다: 3단계 결과를 통째로 다시 쓰지 않는다(astra P1).
- 대상 = 끝난 3단계 결과에서 구분 값 머리(basisKind value · basis stage/year/org)가 있던 본문 표만(다른 표는 판정하지 않는다 — 비용).
- 캐시 = 문서마다 하나 · 열쇠(문서 객체 · rev · 3단계 실행 · 헤더 지정 · 귀속 값) — 같은 rev 에서 3단계가 끝나거나 지정이 바뀌면 다시 센다."""
import hashlib
import json
import threading

from app import division_struct as DT

_CACHE, _LOCK = {}, threading.Lock()
CACHE_MAX = 16
BASES = {"stage", "year", "org"}


def _key(s, t3, heads, values):
    meta = (t3 or {}).get("meta") or {}
    raw = [id(s.doc), s.rev, meta.get("run"), meta.get("at"), heads, values]
    return hashlib.sha1(json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _cands(t3):
    out = []
    for t in (t3 or {}).get("tables") or ():
        if not isinstance(t, dict) or not t.get("id") or (t.get("depth") or 1) != 1:
            continue
        if any(c.get("basisKind") == "value" and set(c.get("basis") or ()) & BASES for c in t.get("cells") or () if isinstance(c, dict)):
            out.append(t)
    return out


def reads(s, groups, values=None, levels=None):
    """(세션 잠금을 잡지 않고 부른다 — 이 함수가 잡는다) → 보탬 목록(`division_scan_api.reads` 와 같은 꼴 — src "struct" · "series"). 3단계 결과가 없으면 []."""
    from app import heading_rules as R
    from app import heading_runs, heading_tables as HT, merge_gather_frame as F, table_excel, table_heads, table_manager
    with s.lock:
        t3 = heading_runs.tables(s)
        if not t3:
            return []
        try:
            heads_rec = table_heads.load(s.id)
        except Exception:   # noqa: BLE001 — 지정 파일을 못 읽으면 지정 없이(표시만 하는 길)
            heads_rec = {}
        key = _key(s, t3, heads_rec.get("tables") if isinstance(heads_rec, dict) else None, values)
        with _LOCK:
            e = _CACHE.get(s.id)
        if e is not None and e["key"] == key:
            return e["reads"]
        orgs = F.orgs_of(values) if values else []
        keys = sorted({o["key"] for o in orgs if o.get("key")}, key=len, reverse=True)
        names = {o["key"]: o.get("name") or o["key"] for o in orgs if o.get("key")}
        blocks = s.doc.blocks()
        order = {b["id"]: i for i, b in enumerate(blocks) if b.get("id") is not None}
        caps = {b["captionOf"]: b.get("text") or "" for b in blocks if b.get("captionOf")}
        store = R.load()
        same = ((t3.get("meta") or {}).get("rev") == s.rev)
        judged = []
        for t in sorted(_cands(t3), key=lambda t: order.get(t["id"], 1 << 30)):
            tid = t["id"]
            if tid not in order:
                continue   # 본문 최상위 표가 아니다(지금 문서에 없음 · 칸 안 표)
            st1 = table_excel.records(s.doc, tid, store, getattr(s, "doc_key", None))
            tb0 = next((x for x in HT.collect(st1) if x["id"] == tid), None) if st1 is not None else None
            if tb0 is None:
                continue
            user, _held = table_heads.check(s.id, tid, tb0)
            stored, same_t = heading_runs.stored_table(s, tid)   # 지금 결과의 그 표 — LLM 판정이 없으면 그 표의 마지막 유효한 LLM 판정(spec_작업 ② §22 「구현 계약」 22-4 ⓕ)
            j = table_manager.judge(st1, tid, stored=stored if stored is not None else t, user=user or None, same_doc=same_t if stored is not None else same)
            if j is None:
                continue
            judged.append({"tid": tid, "tb": j["table"], "owner": t.get("owner"), "caption": caps.get(tid, "")})
    labs = {}
    for g in groups or ():
        for it in g.get("items") or ():
            labs.setdefault(g.get("dim"), set()).update(it.get("labelParas") or ([it["label"]] if it.get("label") else []))
    out = []
    for x in judged:
        x["hs"] = DT.fit(DT.heads(x["tb"], keys, names), (values or {}).get("stages"))
        out.extend(DT.table_reads(x["tid"], x["tb"], x["hs"], labs))
    runs = DT.series(judged, levels, order)
    cell_paras = {x["tid"]: [p for c in x["tb"].get("cells") or () for p in c.get("paras") or ()] for x in judged}
    out.extend(DT.series_reads(runs, cell_paras))
    with _LOCK:
        _CACHE.pop(s.id, None)
        _CACHE[s.id] = {"key": key, "reads": out}
        while len(_CACHE) > CACHE_MAX:
            del _CACHE[next(iter(_CACHE))]
    return out
