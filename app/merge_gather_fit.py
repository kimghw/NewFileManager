"""취합 — 자동 넣기의 틀 맞춤(spec_취합 ② §4-4 「틀 맞춤」 · jobs/plan_merge.md 「서식의 기준은 취합본」).
2026-11-12 사용자 "취합의 자동 넣기는 A(취합문서), B(취합대상문서) 인 경우 A에 맞추고, 다만 depth 나 레터 형식이 다른 경우 A에 맞추고 향후 다른 서식으로 변경할 수 있게 한다" —
기관 문서에서 복사해 넣은 개요 줄 가운데 **개요 깊이(레벨)나 레터 꼴이 취합본 틀과 다른 줄**을 취합본 틀의 그 자리 (템플릿, 레벨)·레터·문단 모양으로 바꾼다. 스크립트만(LLM 없음).
바꾸는 일 자체는 merge_convert(이관·끌어 넣기와 같은 변환) — 여기는 「어느 자리에 맞출지」 와 「무엇을 그대로 둘지」 만 정한다.

- `plan(to, part, op)` = 본문 넣기 하나(merge_gather.plan 의 added·filled op — {after, src, drop})의 틀 맞춤 계획(문서는 안 바뀜) →
  `{"mode", "anchor", "rows", "same", "kept"}` | None(두 문서 가운데 2단계 헤딩 그래프가 없는 것이 있음 — 쓴 대로 넣는다).
  - **맞출 자리**: ① `slot` — 그 내용이 대신하는 취합본 자리표시 줄(op.drop) 가운데 가장 얕은 개요 줄. 내용의 맨 위 줄이 그 줄과 **같은** (템플릿, 레벨)을 받는다
    (`merge_convert.plan(..., sibling=True)`). 가지 템플릿의 뿌리 자리(「(1) 최종목표」 아래 「□」)도 그 자리표시 줄이 가리키므로 맞는다(양식 실측: 자리표시 줄 77곳 가운데 8곳이 그런 자리).
    ② `owner` — 자리표시 줄이 없는 끼어든 내용(added): 넣을 자리를 품은 제목 줄의 **자식**으로(끌어 넣기와 같은 규칙 — `merge_gather_drop._owner`·`_convert`, 서브 템플릿이 붙는 자리는 `branch` 로 그대로).
  - **그대로 두는 줄**: 이미 그 자리의 (템플릿, 레벨)인 줄 · 템플릿 이름만 다르고 레벨·레터 꼴이 같은 줄(`same` — 건드리지 않는다. 기관이 틀 안에서 쓴 보통의 경우) · merge_convert 가 못 바꾸는 줄(`kept{까닭: n}` — label·hetero·otherChain·multi·tooDeep·noLike·numEnd·branch …) ·
    첫머리에 레터가 없는 줄(noLetter) · 번호형 자리에 이미 번호 줄이 있는데 다른 꼴의 줄이 들어오는 내용(`numbered` — 번호를 이어 매기지 못한다, spec_취합 ④ ⓔ). 개요 줄이 아닌 줄(본문·표·그림)은 세지 않는다.
  - 같은 번호 꼴의 줄(「(N)」 자리의 「(3)」)은 번호를 새로 매기지 않고 **기관이 쓴 번호**를 둔다(모양만 맞춤).
  - rows = merge_convert.plan 의 줄 그대로(바꿀 줄만) — `apply` 가 쓴다.
- `view(cv)` = 넣기 계획 화면에 보일 요약 `{"converted", "same", "kept", "labels", "rows"[{src, was, letter, from, to}]}`.
- `apply(to_doc, op, new)` = 넣은 사본(new — op.src 와 같은 차례)에 계획을 입힌다 → **반영 기록** `{"mode", "anchor", "rows": [{id, src, from: [원본 템플릿, 레벨], was: 원래 레터, to: [맞춘 템플릿, 레벨], letter}], "same", "kept"}` | None.
  자리표시 줄을 지우기 **전에** 부른다(본보기가 그 줄일 수 있다). 이 기록이 「향후 다른 서식으로 변경」 의 근거다 — 넣은 줄마다 원래 꼴과 맞춘 자리가 남아 있어, 나중에 다른 틀로 다시 맞추거나 원래 모양으로 되돌릴 수 있다(화면·끝점은 아직 없음 — ④ ⓗ).
- **넘친 개요 레벨**(2026-11-13 — spec_병합 ② §5-5 가 원본): 틀보다 깊은 줄(tooDeep)은 사례로 묶여 계획의 `over`(merge_convert.plan 의 summary.over)에 나오고, `to["over"]`(merge_over.resolve 가 푼 사람의 선택)가 있으면
  그 지정대로 입힌다(없으면 전처럼 쓴 대로 = 「덮은 템플릿 그대로」). 반영 기록에 `over{key, to, lines}` — 쓴 대로 둔 넘친 줄까지 줄마다 원본 접두·모양(merge_over.refit 「넣은 뒤 다시 맞추기」 의 근거)."""
from collections import Counter

from app import merge_chunks as C
from app import merge_convert as MC
from app import merge_gather_drop as DROP
from app.outline_edit import is_numbered, prefix_of

ROWS_MAX = 50
WHY = {**DROP.WHY, "branch": "넣을 자리 아래는 다른 사슬(서브 템플릿)이 붙는 자리", "noAnchor": "넣을 자리를 품은 제목 줄이 없거나 개요 줄이 아님",
       "numbered": "번호형 자리 — 이미 있는 번호 줄에 이어 매기지 못함"}   # 쓴 대로 둔 까닭 — 화면에 보일 글


def _key(node):
    return (node or {}).get("key") or ""


def _siblings(graph, by_para, by_id, an, level):
    """취합본에서 an 바로 아래 그 레벨에 이미 있는 글 든 개요 줄이 있는가(번호를 이어 매겨야 하는 자리)."""
    return any(n.get("role") == "heading" and not n.get("blank") and n.get("template") == an["template"] and int(n.get("level") or 0) == level
               and MC._parent_para(n, by_id) == an["para"] for n in graph.get("nodes") or () if by_para.get(n["para"]) is n)


def plan(to, part, op):
    """본문 넣기 하나의 틀 맞춤 계획(모듈 설명) — 문서는 안 바뀐다."""
    tg, pg = (to or {}).get("graph") or {}, (part or {}).get("graph") or {}
    if not tg.get("nodes") or not pg.get("nodes"):
        return None
    to_doc, part_doc, src = to["doc"], part["doc"], list(op["src"])
    tp, _, tid = MC._index(tg)
    fp, _, _ = MC._index(pg)
    kept = Counter()
    over = to.get("over")   # 넘친 레벨의 지정(merge_over.resolve — 사람의 선택. 없으면 넘친 줄은 쓴 대로)
    slot = min((tp[i] for i in op.get("drop") or () if i in tp), key=lambda n: int(n["level"]), default=None)   # 가장 얕은 자리표시 줄(같으면 문서 순 첫 줄)
    if slot is not None:
        mode, an = "slot", slot
        p = MC.plan(tg, pg, an["para"], src, sibling=True, over=over)
    else:
        blocks = to.get("blocks")
        at = C.index(blocks if blocks is not None else to_doc.blocks())
        owner = DROP._owner(tg, at, at[op["after"]][0]) if op.get("after") in at else None
        mode, an = "owner", tp.get(owner["para"]) if owner else None
        p = DROP._convert(tg, pg, an["para"], src, over=over) if an else MC.plan(tg, pg, None, src)   # 품은 제목 줄이 없으면 줄마다 noAnchor
    rows, same, held = [], 0, []   # held = 쓴 대로 두는 넘친 줄(반영 때 적어 둔다 — 다시 맞추기의 근거)
    for r in p["rows"]:
        if not r["level"]:
            continue   # 개요 줄이 아닌 줄(본문·표·그림) — 틀 맞춤이 볼 것이 아니다
        if r["why"]:
            kept[r["why"]] += 1
            if r.get("over") and r["why"] == "tooDeep":
                held.append(r)
        elif not r.get("over") and (r["level"] == r["slot"] or (r["level"][1] == r["slot"][1] and _key(fp.get(r["src"])) == _key(tp.get(r["like"])))):
            same += 1   # 이미 그 자리의 (템플릿, 레벨) — 건드리지 않는다. 사슬 이름만 다른 것(기관 문서에 레벨이 하나 더 생겨 「[기관]›o›-›·」)도 레벨·레터 꼴이 같으면 같은 줄. 사람이 꼴을 정한 넘친 줄은 늘 입힌다
        elif not prefix_of(part_doc._text(part_doc._ids[r["src"]]), r["was"] or None)[1]:
            kept["noLetter"] += 1
        elif not r.get("own") and (to_doc._ids.get(r["like"]) is None or not prefix_of(to_doc._text(to_doc._ids[r["like"]]), r["likeLetter"] or None)[1]):
            kept["noLike"] += 1
        else:
            like = _key(tp.get(r["like"]))
            rows.append({**r, "letter": r["was"]} if is_numbered(like) and _key(fp.get(r["src"])) == like else r)   # 같은 번호 꼴 — 기관이 쓴 번호를 둔다
    if mode == "owner" and an is not None:
        top = int(an["level"]) + 1
        if any(r["slot"][1] == top and r["letter"] != r["was"] and is_numbered(_key(tp.get(r["like"]))) for r in rows) and _siblings(tg, tp, tid, an, top):
            kept["numbered"] += len(rows)
            held += [r for r in rows if r.get("over")]
            rows = []
    return {"mode": mode, "anchor": an["para"] if an else None, "rows": rows, "same": same, "kept": dict(kept), "over": p["summary"].get("over"), "held": held}


def view(cv):
    """넣기 계획 화면에 보일 요약(모듈 설명) — 넘친 줄이 있으면 `over`(merge_convert.plan 의 summary.over — 사례)도."""
    return {"converted": len(cv["rows"]), "same": cv["same"], "kept": cv["kept"], "labels": {k: WHY.get(k, k) for k in cv["kept"]},
            "rows": [{"src": r["src"], "was": r["was"], "letter": r["letter"], "from": r["level"], "to": r["slot"], **({"over": r["over"]} if r.get("over") else {})} for r in cv["rows"][:ROWS_MAX]],
            **({"over": cv["over"]} if cv.get("over") else {})}


def apply(to_doc, op, new):
    """넣은 사본에 틀 맞춤을 입히고 반영 기록을 낸다(모듈 설명) — 계획이 없으면 None(쓴 대로). 넘친 줄이 있으면 기록에 `over{key, to, lines}`(spec_병합 ② §5-5 7 — 쓴 대로 둔 넘친 줄도 적는다)."""
    cv = op.get("convert")
    if not cv:
        return None
    new_of = dict(zip(op["src"], new))
    lines = []
    for r in cv.get("held") or ():   # 쓴 대로 두는 넘친 줄 — 넣은 그대로의 접두·모양을 적어 둔다
        nid = new_of.get(r["src"])
        lead, tok, gap = prefix_of(to_doc._text(to_doc._ids[nid]), r["was"] or None) if nid in to_doc._ids else ("", "", "")
        if tok:
            lines.append(MC._line(to_doc, r, nid, new_of, lead + tok + gap, tok))
    res = MC.apply(to_doc, list(new_of.items()), {"rows": cv["rows"]}) if cv["rows"] else {"ids": [], "kept": {}}
    done, kept = set(res["ids"]), Counter(cv["kept"])
    kept.update(res["kept"])
    order = {s: i for i, s in enumerate(op["src"])}
    lines = sorted(lines + list(res.get("lines") or ()), key=lambda x: order.get(x["src"], 0))   # 문서 순(부모가 먼저)
    ov = cv.get("over")
    return {"mode": cv["mode"], "anchor": cv["anchor"], "same": cv["same"], "kept": {k: v for k, v in kept.items() if v},
            "rows": [{"id": new_of[r["src"]], "src": r["src"], "from": r["level"], "was": r["was"], "to": r["slot"], "letter": r["letter"]}
                     for r in cv["rows"] if new_of.get(r["src"]) in done],
            **({"over": {"key": ov["key"], "to": ov["to"], "lines": lines, "keepNumbers": True}} if ov and lines else {})}   # keepNumbers = 다시 맞출 때도 같은 번호 꼴이면 기관이 쓴 번호를 둔다
