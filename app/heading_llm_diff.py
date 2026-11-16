"""LLM 이 바꾼 것(spec_헤딩_추출 ② §7 「LLM 이 바꾼 것」, 2026-11-16 사용자 "LLM 작업하고 뭐가 수정되었는지를 모르겠다").

헤딩 추출의 LLM 실행(규칙 보강 · 헤딩 판정 · 표 판정)과 템플릿 서식 정리 계획(★)이 **스크립트가 낸 것과 다르게 정한 것**을 한 보고로 모은다 — 읽기만.
LLM 판정은 분석 결과만 바꾸고 문서는 바꾸지 않는다(문서를 바꾸는 것은 서식 계획의 반영 — 「템플릿 맞추기」·★ 열).
견줌의 기준(실행을 따로 다시 돌리지 않는다 — 저장된 결과 안에 이미 있는 것):
  ① 규칙 보강 = 그 1단계 실행의 LLM 답(stage1.llm.items — 저장 · 거절 · 그대로 · 모름) + 저장한 규칙이 지금 1단계에서 판정한 문단
  ② 헤딩 판정 = 그 2단계 결과 안의 스크립트 초안과 LLM 답의 차이: 유형 역할(스크립트 대체 판정 fallback_roles 와 다른 것) · 변형(variantOf) · 주 사슬 ·
     구간 판정 B 의 변경(changes — before/after) · 버린 변경 · 미판정 · 서식 쌍 판정(조정 — 스크립트는 모두 미판정)
  ③ 표 판정 = 칸마다 초안 역할(draft) → LLM 역할(role) · 표마다 LLM 요약 · 서브 테이블 수(초안 수는 그 값을 남긴 실행만 — heading_tables `llm.draftSubs`)
  ④ 서식 계획 = 받아 둔 템플릿 서식 정리 계획(tpl_agent_api.plans) — 레벨마다 맞출 줄 · 남긴 줄 · 뗄 줄
  더해 단계마다 앞서 돈 **스크립트 실행**의 요약 수(실행 목록 run.json 의 summary)가 있으면 견줄 수로 붙인다(base).
server 를 import 하지 않는다 — heading_llm_diff_api 가 세션·계획을 넘긴다."""
from collections import Counter, defaultdict

from app import heading_graph as HG
from app import heading_runs as HR

PARAS_MAX = 40   # 규칙 하나 · 조정 묶음 하나에 싣는 문단 id 수(나머지는 수만)
NODES_MAX = 300  # 구간 판정 변경 · 버린 변경 · 미판정 노드 목록의 끝
CELLS_MAX = 200  # 표 하나의 바뀐 칸 목록의 끝


def _short(t, n=60):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def _base(st, stage, before_at):
    """그 LLM 실행보다 앞서 돈 같은 단계의 스크립트 실행(가장 늦은 것) → {run, at, summary} | None."""
    got = None
    for r in st.get("runs") or []:
        if r.get("stage") == stage and not r.get("llm") and (before_at is None or (r.get("at") or 0) <= before_at):
            got = r
    return {"run": got.get("n"), "at": got.get("at"), "summary": got.get("summary") or {}} if got else None


# ---- ① 규칙 보강 ---------------------------------------------------------------------------------------------------

def _rules_llm(sess, st):
    """규칙 보강을 마지막으로 돌린 1단계 실행 → (그 실행 메타, stage1.llm | None, 지금 1단계가 그 실행인가)."""
    rv = HR.rules_view(st)
    if rv is None:
        return None, None, False
    s1 = st.get("stage1") or {}
    if (s1.get("meta") or {}).get("run") == rv.get("run") and s1.get("llm"):
        return rv, s1["llm"], True
    d = HR._dir(sess)
    res = HR._read(d / str(rv["run"]) / "stage1.json") if d is not None and isinstance(rv.get("run"), int) else None
    return rv, (res or {}).get("llm") if isinstance(res, dict) else None, False


def rules_part(sess, st):
    rv, lm, current = _rules_llm(sess, st)
    if rv is None:
        return None
    s1 = st.get("stage1") or {}
    sm = (s1.get("review") or {})
    by_rule = defaultdict(list)
    for p in s1.get("paras") or []:
        if p.get("rule"):
            by_rule[p["rule"]].append(p)
    items = []
    for it in (lm or {}).get("items") or []:
        rule = it.get("rule") or {}
        hit = by_rule.get(it.get("id")) if it.get("verdict") == "saved" and it.get("id") else []
        test = it.get("test") or {}
        items.append({"verdict": it.get("verdict"), "group": it.get("group"), "rule": it.get("id"), "name": rule.get("name"), "kind": rule.get("kind"),
                      "pattern": rule.get("pattern"), "scope": rule.get("scope"), "first": bool(rule.get("first")), "reason": it.get("reason") or "",
                      "why": it.get("why") or "", "fixed": test.get("fixed"), "taken": test.get("taken"),
                      "paras": [{"id": p["id"], "text": _short(p.get("text"), 80)} for p in (hit or [])[:PARAS_MAX]],  # 레코드 text 는 레터까지 든 문단 글
                      "parasTotal": len(hit or [])})
    verdicts = Counter(x["verdict"] for x in items)
    return {"run": rv.get("run"), "at": rv.get("at"), "costUsd": rv.get("costUsd"), "seconds": (lm or {}).get("seconds"), "groups": rv.get("groups"),
            "asked": rv.get("asked"), "error": rv.get("error") or (lm or {}).get("error"), "current": current, "items": items,
            "counts": {k: verdicts.get(k, 0) for k in ("saved", "rejected", "kept", "unsure", "duplicate")},
            "left": len(sm.get("unmatched") or []) + len(sm.get("conflicts") or []),
            "base": _base(st, 1, rv.get("at"))}


# ---- ② 헤딩 판정 ---------------------------------------------------------------------------------------------------

def _node_text(n):
    return _short(f"{(n.get('letter') or '').strip()} {n.get('text') or ''}".strip(), 60) if n else ""


def _slot_text(s):
    return f"{s.get('template')} L{s.get('level')}" if isinstance(s, dict) and s.get("template") else ""


def heads_part(st):
    g = st.get("stage2")
    if not g:
        return None
    lm, meta = g.get("llm") or {}, g.get("meta") or {}
    out = {"run": meta.get("run"), "at": meta.get("at"), "llm": bool(lm.get("requested") and not lm.get("fallback")), "requested": bool(lm.get("requested")),
           "fallback": bool(lm.get("fallback")), "error": lm.get("error"), "costUsd": lm.get("costUsd"), "seconds": lm.get("seconds"), "calls": lm.get("calls"),
           "summary": lm.get("summary") or "", "base": _base(st, 2, meta.get("at")), "counts": g.get("counts") or {}}
    if not out["llm"]:
        return out
    nodes = {n["id"]: n for n in g.get("nodes") or []}
    per_type = Counter(n.get("type") for n in nodes.values())
    types = {t.get("type"): t for t in g.get("types") or [] if t.get("type")}
    script = HG.fallback_roles(types, g.get("hints"))
    trows = []
    for tid, t in types.items():
        sr = (script.get(tid) or {}).get("role")
        trows.append({"type": tid, "shape": t.get("shape"), "area": t.get("area"), "kind": t.get("kind"), "bold": t.get("bold"), "size": t.get("size"),
                      "nodes": per_type.get(tid, 0), "role": t.get("role"), "script": sr, "changed": bool(sr and t.get("role") != sr),
                      "variantOf": t.get("variantOf") or "", "basis": t.get("basis") or "", "parents": list(t.get("parents") or []), "reason": t.get("reason") or ""})
    ch = []
    for c in (g.get("changes") or [])[:NODES_MAX]:
        n, b, a = nodes.get(c.get("id")), c.get("before") or {}, c.get("after") or {}
        side = lambda x: {"role": x.get("role"), "parent": x.get("parent"), "parentText": _node_text(nodes.get(x.get("parent"))), "slot": _slot_text(x.get("slot"))}
        ch.append({"id": c.get("id"), "para": (n or {}).get("para"), "text": _node_text(n), "before": side(b), "after": side(a), "reason": c.get("reason") or ""})
    rej = [{"id": r.get("id"), "para": (nodes.get(r.get("id")) or {}).get("para"), "text": _node_text(nodes.get(r.get("id"))), "why": r.get("why") or ""}
           for r in (g.get("rejected") or [])[:NODES_MAX]]
    und = [n for n in nodes.values() if n.get("undecided")]
    letters = {}
    for t in g.get("templates") or []:
        for s in t.get("slots") or []:
            letters[(t.get("name"), s.get("level"))] = s.get("letter")
    groups = {}
    for a in g.get("adjustments") or []:
        rv = (a.get("review") or {}).get("verdict") or ""
        k = (a.get("tplNo"), a.get("template"), a.get("level"), a.get("from"), a.get("to"), a.get("decision"), rv)
        x = groups.get(k)
        if x is None:
            x = groups[k] = {"tplNo": a.get("tplNo"), "template": a.get("template"), "level": a.get("level"), "letter": letters.get((a.get("template"), a.get("level"))) or "",
                             "from": a.get("from"), "fromName": a.get("fromName") or "", "to": a.get("to"), "toName": a.get("toName") or "",
                             "decision": a.get("decision"), "verdict": rv, "first": a.get("first") or "", "reason": a.get("reason") or "",
                             "review": (a.get("review") or {}).get("reason") or "", "n": 0, "paras": []}
        x["n"] += 1
        if len(x["paras"]) < PARAS_MAX and a.get("para"):
            x["paras"].append(a["para"])
    dec = Counter(a.get("decision") for a in g.get("adjustments") or [])
    order = {"adjust": 0, "keep": 1, "undecided": 2}
    out.update(
        mainChain={"proposal": list(lm.get("mainChainProposal") or []), "fixed": list(lm.get("mainChain") or []), "accepted": bool(lm.get("mainChainFixed")),
                   "rejected": lm.get("mainChainRejected") or ""},
        types=sorted(trows, key=lambda r: (not r["changed"], not r["variantOf"], r["type"])),
        typesChanged=sum(1 for r in trows if r["changed"]), variants=sum(1 for r in trows if r["variantOf"]),
        nodes=ch, nodesTotal=len(g.get("changes") or []), rejected=rej, rejectedTotal=len(g.get("rejected") or []),
        undecided=len(und), undecidedNodes=[{"id": n["id"], "para": n.get("para"), "text": _node_text(n)} for n in und[:NODES_MAX]],
        adjust={"adjust": dec.get("adjust", 0), "keep": dec.get("keep", 0), "undecided": dec.get("undecided", 0),
                "disagreed": (g.get("counts") or {}).get("disagreed", 0), "pairs": lm.get("formatPairs"), "reviewPairs": lm.get("reviewPairs"),
                "groups": sorted(groups.values(), key=lambda x: (order.get(x["decision"], 3), x["tplNo"] or 0, x["level"] or 0, -x["n"]))})
    return out


# ---- ③ 표 판정 -----------------------------------------------------------------------------------------------------

def tables_part(st):
    t3 = st.get("stage3")
    if not t3:
        return None
    lm, meta = t3.get("llm") or {}, t3.get("meta") or {}
    out = {"run": meta.get("run"), "at": meta.get("at"), "llm": bool(lm.get("requested") and not lm.get("fallback")), "requested": bool(lm.get("requested")),
           "fallback": bool(lm.get("fallback")), "error": lm.get("error"), "costUsd": lm.get("costUsd"), "seconds": lm.get("seconds"), "calls": lm.get("calls"),
           "summary": lm.get("summary") or "", "base": _base(st, 3, meta.get("at")), "counts": t3.get("counts") or {}}
    if not out["llm"]:
        return out
    rows = []
    for t in t3.get("tables") or []:
        tl = t.get("llm") or {}
        cells = [x for x in t.get("cells") or [] if x.get("changed")]
        rows.append({"id": t.get("id"), "before": t.get("before") or "", "rows": t.get("rows"), "cols": t.get("cols"), "sent": bool(tl.get("sent")),
                     "undecided": bool(tl.get("undecided")), "error": tl.get("error"), "summary": tl.get("summary") or "",
                     "subs": len(t.get("subtables") or []), "draftSubs": tl.get("draftSubs"),
                     "changed": [{"id": x.get("id"), "row": x.get("row"), "col": x.get("col"), "text": _short(x.get("text"), 40), "draft": x.get("draft"),
                                  "role": x.get("role"), "reason": x.get("reason") or ""} for x in cells[:CELLS_MAX]],
                     "changedTotal": len(cells), "rejected": [str(r)[:120] for r in (tl.get("rejected") or [])[:20]]})
    out.update(sent=lm.get("sent"), skipped=lm.get("skipped"), applied=lm.get("applied"), rejected=lm.get("rejected"), undecided=lm.get("undecided"),
               tables=sorted(rows, key=lambda r: (not r["changedTotal"], not (r["draftSubs"] is not None and r["draftSubs"] != r["subs"]), not r["sent"])))
    return out


# ---- ④ 서식 계획 ---------------------------------------------------------------------------------------------------

def _lines(gs):
    return sum(int(g.get("count") or 0) for g in gs or [])


def formats_part(plans):
    """plans = {tpl: 기록(+ state — analysis.plan_state)} → 템플릿 번호 차례의 목록."""
    rows = []
    for tpl, rec in (plans or {}).items():
        p = rec.get("plan") or {}
        lv = []
        for L in p.get("levels") or []:
            sp = [{"sfx": s.get("sfx"), "lines": int((s.get("rep") or {}).get("count") or 0) + _lines(s.get("match"))} for s in L.get("split") or []]
            lv.append({"level": L.get("level"), "letter": L.get("letter") or "", "lines": L.get("lines"), "single": bool(L.get("single")),
                       "repChanged": bool((L.get("rep") or {}).get("changed")), "match": _lines(L.get("match")), "matchGroups": len(L.get("match") or []),
                       "keep": _lines(L.get("keep")), "keepGroups": len(L.get("keep") or []), "split": sp, "change": L.get("change") or 0,
                       "moved": L.get("moved") or 0, "why": L.get("why") or ""})
        rows.append({"tpl": str(tpl), "no": rec.get("no"), "state": rec.get("state"), "at": rec.get("at"), "rev": rec.get("rev"), "model": rec.get("model"),
                     "costUsd": rec.get("costUsd"), "skill": (rec.get("skill") or {}).get("name"), "summary": p.get("summary") or "",
                     "applied": rec.get("applied"), "levels": lv,
                     "change": sum(x["change"] for x in lv), "moved": sum(x["moved"] for x in lv), "keep": sum(x["keep"] for x in lv)})
    rows.sort(key=lambda r: (int(r["no"]) if str(r["no"] or "").isdigit() else 10 ** 6, r["tpl"]))
    return rows


def report(sess, plans=None):
    """→ {rev, rules, heads, tables, formats} — 각 부분은 그 단계 결과가 없으면 None(서식은 빈 목록). 문서·결과는 바꾸지 않는다."""
    st = HR.state(sess)
    return {"rev": getattr(sess, "rev", None), "rules": rules_part(sess, st), "heads": heads_part(st), "tables": tables_part(st), "formats": formats_part(plans)}
