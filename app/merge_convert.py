"""병합 — 템플릿 변환(spec_병합 ② §0-1 「옮길 때의 규칙」 · §5 문단 묶음 넣기): 원본 문서에서 복사해 목적 문서 넣을 자리(anchor) 아래 넣은 개요 줄을
목적 문서 개요템플릿의 그 개요레벨 (레터 · 문단 모양 · 기본 글자 모양)으로 바꾼다. 문서 사이 복사(`hwpx_doc._copy`)는 원본 정의를 가져올 뿐이라 그대로면 원본 모양이 남는다.

- `plan(to_graph, from_graph, anchor_id, src_ids)` = 넣기 계획(두 문서의 2단계 헤딩 그래프만 — 문서는 안 봄) → {"rows": [...], "summary": {...}}.
  **기준 사슬** = 복사한 줄 가운데 문서 순 첫 맨 위 줄(부모가 복사 범위 밖인 개요 줄 — 라벨 아님)의 템플릿. 사슬 줄 = 그 템플릿이고 부모가 범위 밖이거나 사슬 줄인 것 —
  서브 템플릿 줄 아래 다시 나온 같은 템플릿은 사슬 줄이 아니다(레벨을 템플릿 경계 너머로 빼지 않는다). 기준 레벨 = 사슬 줄의 가장 얕은 레벨, rel = 레벨 − 기준 레벨.
  **목적 자리** = (넣을 자리의 템플릿, 넣을 자리 레벨 + 1 + rel) — 맨 위 줄이 넣을 자리의 자식이 된다. 넣을 자리가 그 템플릿의 마지막 레벨이면(연차보고서 「- (추진 내용)」 = […]›□›o›- 의 L4)
  자식 자리가 없어 개요 줄은 모두 tooDeep 이다 — 목적 문서에 근거 없는 레벨을 만들지 않고 원본 모양으로 두고 알린다(summary.anchorLeaf).
  본보기(like) = 그 자리의 줄 가운데 넣을 자리와 같은 인스턴스의 첫 줄, 없으면 템플릿 슬롯의 대표 문단. 레터 = 본보기의 실제 레터(「o」 자리의 「ㅇ」),
  번호형 자리는 목적 부모마다 처음부터(first → succ, 합성 번호는 부모 번호를 앞에) — 넣을 자리에 이미 있던 자식의 번호는 잇지 않는다.
  rows[{src, level: [템플릿, 레벨] | None, rel, slot: [목적 템플릿, 레벨] | None, like, letter, was: 원본 레터, likeLetter, cells, why}] — why 가 있으면 그대로 둔다:
  body(개요 레벨 없는 본문·간격 줄) · table(표 블록 — 칸 안 글머리는 v1 밖, 수는 cells) · label(구분 라벨·괄호 소제목 — 괄호 글 전체가 레터라 바꾸면 글이 갈린다) ·
  multi(문단에 개요 노드 둘 이상 — 강제 줄 바꿈 뒤 레터) · otherChain(다른 사슬 — 서브 템플릿) · hetero(이종 형제 — 사슬 줄과 같은 부모의 다른 템플릿 줄, 또는 사슬 레벨과 다른 레터를 쓴 줄) ·
  tooDeep(목적 사슬보다 깊음) · noAnchor(넣을 자리가 개요 줄이 아님) · noLike(그 자리 본보기 문단 없음) · numEnd(번호 열 끝).
- `apply(to_doc, pairs, plan)` = pairs[(원본 id, 넣은 사본 id)] 의 사본에 계획대로 `replace_prefix` — 접두 = 본보기 문단의 앞 공백 + 새 레터 + 뒤 공백, 문단 속성·접두와 기본 글자 모양 = 본보기 것
  (따로 강조한 런은 그대로) → {"converted", "kept": {why: n}, "ids": 바꾼 사본 id}. 문서에서 보고 못 하는 것도 kept 에: noLetter(사본 첫머리에 원본 레터가 없음 — 한글 자동 번호 등) ·
  noLike(본보기 첫머리에 레터 없음) · marker(형광펜·변경 추적 표지가 든 문단) · missing(pairs 에 사본 없음).
- `converter(to_doc, to_graph, from_graph, over=None)` → `convert(anchor_id, pairs)` — 본문 넣기가 복사한 바로 뒤 부르는 고리(apply 결과 + plan 요약 + 넘친 줄 기록 `over`).
- **넘친 개요 레벨**(spec_병합 ② §5-5 — 2026-11-13 사용자 「덮은 템플릿으로 사용할지 템플릿을 수정할지, 다른 템플릿을 선택할 수 있게」): 목적 레벨이 자리 템플릿의 길이 K 를 넘는 줄(tooDeep)은
  **사례**(열쇠 = `<자리 템플릿 앵커><<원본 기준 사슬에서 K+1 에 오는 레벨부터 끝까지의 레터 키를 「›」 로 이은 글>`)로 묶여 `summary.over` 에 나온다 —
  {key, to[자리 템플릿, K], from[원본 템플릿, K+1 에 오는 원본 레벨], tail[키…], levels[{n(K+j), src(원본 레벨), key, was(그 레벨 첫 줄의 레터), rep(그 줄), lines}], lines, under[그 자리 아래에 이미 붙은 다른 템플릿 앵커…]}, 줄마다 `over`(j).
  `plan(…, over={사례 열쇠: [레벨 지정 | None …]})`(merge_over.resolve 가 사람의 선택을 푼 것 — j 번째 넘친 레벨의 지정): 지정이 없으면 전처럼 tooDeep(원본 모양 그대로 = 「덮은 템플릿 그대로」).
  지정 {like(목적 문서의 본보기 문단 | None), letter, lead(앞 공백 칸 수 | None), numbered} 가 있으면 바꿀 줄이 된다 — like 가 있으면 맞는 레벨과 같은 길(접두·문단 속성·기본 글자 모양 = 본보기 것),
  없으면 `own`(제 모양을 둔 채 접두의 레터·앞 공백만). numbered 면 목적 부모마다 처음부터 번호를 매긴다(덮은 그대로인 줄은 쓴 번호 그대로). 본보기 문단이 그래프에 없으면 noLike.
  `over=None`·빈 것이면 줄의 결과는 이 기능 전과 같다(덧붙는 것은 줄의 `over`·`parent`·`pl` 과 `summary.over` 뿐).
  `apply` 는 넘친 줄마다 **기록** `lines[{id(넣은 줄), src, over(j), was(원본 레터), letter(지금 레터), parent(넘친 부모 줄의 넣은 id | None), pl(그 밖의 부모 레터), orig{prefix, attrs}}]` 를 함께 낸다 —
  원본 접두와 문단·글자 모양 참조가 남아 있어 나중에 다른 선택으로 다시 입히거나 원본 모양으로 되돌릴 수 있다(merge_over.refit — 원본 문서 없이). `record(summary, res)` = 저장할 꼴 {key, to, lines} | None."""
from collections import Counter

from app.outline_edit import ROOTED, first, is_numbered, prefix_of, succ

_CLEAR = ("not_heading", "note")  # 의미 부모를 찾을 때 투명한 노드(heading_graph._eff_parent 와 같음)
SEP = "›"   # 사슬의 레터 키를 잇는 글자(템플릿 앵커와 같은 꼴 — heading_graph)


def _index(g):
    """그래프 → (문단 → 개요 노드(템플릿·레벨 있는 첫 것), 문단마다 개요 노드 수, 노드 id → 노드)."""
    nodes = g.get("nodes") or []
    outline = [n for n in nodes if n.get("template") and n.get("level")]
    by_para = {}
    for n in outline:
        by_para.setdefault(n["para"], n)
    return by_para, Counter(n["para"] for n in outline), {n["id"]: n for n in nodes}


def _parent_para(n, by_id):
    """의미 부모의 문단 id(안내·헤딩 아님 노드는 건너뜀) | None(뿌리·칸)."""
    p, seen = n.get("parent"), set()
    while p in by_id and by_id[p].get("role") in _CLEAR and p not in seen:
        seen.add(p)
        p = by_id[p].get("parent")
    return by_id[p]["para"] if p in by_id else None


def _cell_lines(g, tables):
    """복사한 표(안의 표 포함)의 칸 안 개요 줄 수 — 표 블록 id → 수."""
    cont = {c["id"]: c for c in g.get("containers") or []}
    out = Counter()
    for n in g.get("nodes") or []:
        if not (n.get("template") and n.get("level")) or not str(n.get("flow") or "").startswith("cell:"):
            continue
        c, hit = cont.get(n["flow"]), None
        while c is not None:
            if c["kind"] == "table" and c["id"][4:] in tables:
                hit = c["id"][4:]  # 바깥으로 올라가며 마지막(가장 바깥) 것
            c = cont.get(c.get("parent"))
        if hit:
            out[hit] += 1
    return out


def _numpl(letter):
    """합성 번호의 앞 번호로 쓸 부모 레터 — 로마자 한 글자(기호 「o」)는 번호가 아니다(outline_edit.numbers_of 는 그것도 번호로 읽는다)."""
    t = (letter or "").strip()
    return None if len(t) == 1 and t.isascii() and t.isalpha() else letter


def plan(to_graph, from_graph, anchor_id, src_ids, sibling=False, over=None):
    """복사한 원본 블록(src_ids — 문서 순)을 목적 문서 anchor_id 아래 넣을 때 줄마다 목적 자리·레터·본보기 → {"rows", "summary"}(모듈 설명).
    sibling=True 면 anchor_id 는 넣을 자리의 **부모가 아니라 그 자리의 줄**이다(취합 — 자리표시 줄을 대신하는 내용, merge_gather_fit): 맨 위 줄이 그 줄과 같은 (템플릿, 레벨)을 받는다.
    over = 넘친 레벨의 지정 {사례 열쇠: [레벨 지정 | None …]}(모듈 설명 「넘친 개요 레벨」) — None 이면 넘친 줄은 원본 모양 그대로(tooDeep)."""
    src_ids = list(src_ids)
    fp, fper, fid = _index(from_graph)
    tp, tper, tid = _index(to_graph)
    tpls = {t.get("anchor") or t.get("name"): t for t in to_graph.get("templates") or []}
    ftpls = {t.get("anchor") or t.get("name"): t for t in from_graph.get("templates") or []}
    copied = set(src_ids)
    tbl_ids = {c["id"] for c in from_graph.get("containers") or [] if c.get("kind") == "table"}
    tables = {s for s in src_ids if f"tbl:{s}" in tbl_ids}
    cells = _cell_lines(from_graph, tables) if tables else Counter()
    lines = [fp[s] for s in src_ids if s in fp]
    par = {n["para"]: _parent_para(n, fid) for n in lines}
    # 기준 사슬 = 문서 순 첫 맨 위 줄의 템플릿 — 내용의 맨 위 레벨은 첫 개요 줄이 정한다(「가장 많은 것」 은 실제 쌍에서 그래프가 잘못 맨 위로 올린 ① 줄 두 개를 골랐다)
    base = next((n["template"] for n in lines if par[n["para"]] not in copied and n.get("role") not in ROOTED), None)
    chain = {}  # 문단 → 사슬 줄인가(문서 순이라 부모가 먼저 정해진다)
    for n in lines:
        p = par[n["para"]]
        chain[n["para"]] = n["template"] == base and (p not in copied or chain.get(p, False))
    base_level = min((int(n["level"]) for n in lines if chain[n["para"]]), default=None)
    kids_of = {par[n["para"]] for n in lines if chain[n["para"]]}  # 사슬 줄의 부모들(이종 형제 판정)

    an = tp.get(anchor_id)
    at = tpls.get(an["template"]) if an else None
    up = 0 if sibling else 1   # 맨 위 줄의 자리 = 넣을 자리 레벨 + up
    top_letter = None   # 맨 위 줄의 부모 레터(합성 번호의 앞 번호) — sibling 이면 넣을 자리 줄의 부모 것
    if an:
        top_letter = ((tp.get(_parent_para(an, tid)) or {}).get("letter") if sibling else an.get("letter")) or None
    a_chain = list((at or {}).get("chain") or [])
    reps = {int(s["level"]): s.get("rep") for s in (at or {}).get("slots") or []}
    members = {}  # 목적 레벨 → 넣을 자리와 같은 인스턴스의 첫 줄
    if an:
        for n in to_graph.get("nodes") or []:
            if n.get("template") == an["template"] and n.get("instance") == an.get("instance") and tper[n["para"]] == 1 and n.get("role") == "heading":
                members.setdefault(int(n["level"]), n["para"])
    # 넘친 레벨(spec_병합 ② §5-5): 자리 템플릿의 길이 K 를 넘는 목적 레벨 K+j — 사례 열쇠 = 자리 템플릿 앵커 + 원본 사슬의 넘친 꼬리(K+1 에 오는 원본 레벨 s0 부터 끝까지)
    K = len(a_chain)
    s0 = base_level + K - (int(an["level"]) + up) + 1 if an and at and base_level is not None else None
    tail = list((ftpls.get(base) or {}).get("chain") or [])[s0 - 1:] if s0 else []
    case = (f"{an['template']}<{SEP.join(tail)}" if tail else f"{an['template']}<{base}@{s0}") if s0 else None
    specs = list((over or {}).get(case) or ()) if case else []
    seen = {}   # j → 그 넘친 레벨의 요약(summary.over.levels)

    rows, new_letter, last = [], {}, {}
    for s in src_ids:
        n = fp.get(s)
        row = {"src": s, "level": None, "rel": None, "slot": None, "like": None, "letter": None, "was": None, "likeLetter": None, "cells": 0, "why": None}
        rows.append(row)
        if n is None:
            row["why"] = "table" if s in tables else "body"
            row["cells"] = cells.get(s, 0)
            continue
        row["level"], row["was"] = [n["template"], int(n["level"])], n.get("letter") or ""
        new_letter[s] = row["was"] or None  # 바꾸지 않는 줄(hetero…) 아래 자식의 번호는 이 줄의 원본 레터를 부모로 — 바꾸면 아래에서 덮음
        ch = list((ftpls.get(n["template"]) or {}).get("chain") or [])
        lv = int(n["level"])
        if n.get("role") in ROOTED:
            row["why"] = "label"
        elif fper[s] > 1:
            row["why"] = "multi"
        elif not chain[s]:
            row["why"] = "hetero" if par[s] in kids_of else "otherChain"
        elif lv - 1 < len(ch) and ch[lv - 1] != n.get("key"):
            row["why"] = "hetero"  # 사슬 레벨과 다른 레터(오버라이드) — 목적 기본 레터로 덮지 않는다
        if row["why"]:
            continue
        row["rel"] = lv - base_level
        if an is None or at is None:
            row["why"] = "noAnchor"
            continue
        tl = int(an["level"]) + up + row["rel"]
        p = par[s]
        pkey = p if p in copied else anchor_id
        pl = new_letter.get(p) if p in copied else top_letter
        if tl > K:   # 넘친 레벨 — 지정이 없으면 원본 모양 그대로(덮은 템플릿 그대로)
            j = tl - K
            row["over"], row["parent"], row["pl"] = j, (p if p in copied else None), pl
            seen.setdefault(j, {"n": tl, "src": lv, "key": n.get("key") or "", "was": row["was"], "rep": s, "lines": 0})["lines"] += 1
            spec = specs[j - 1] if j - 1 < len(specs) else None
            if not spec:
                row["why"] = "tooDeep"
                continue
            row["slot"] = [an["template"], tl]
            like = spec.get("like")
            if like is None:   # 제 모양을 둔 채 레터·앞 공백만
                row["own"], letter = True, spec.get("letter") or row["was"]
                numbered = bool(spec.get("numbered")) and bool(spec.get("letter"))
            else:
                ln = tp.get(like)
                if ln is None or tper[like] != 1:
                    row["why"] = "noLike"
                    continue
                row["like"], row["likeLetter"] = like, ln.get("letter") or ""
                letter = spec.get("letter") or row["likeLetter"]
                numbered = bool(spec["numbered"]) if spec.get("numbered") is not None else is_numbered(ln.get("key"))
            if spec.get("lead") is not None:
                row["lead"] = int(spec["lead"])
            pl = _numpl(pl)
        else:
            row["slot"] = [an["template"], tl]
            like = members.get(tl) or reps.get(tl)
            ln = tp.get(like) if like else None
            if ln is None or tper[like] != 1:
                row["why"] = "noLike"
                continue
            row["like"], row["likeLetter"] = like, ln.get("letter") or ""
            letter, numbered = row["likeLetter"], is_numbered(a_chain[tl - 1])
        if numbered:
            prev = last.get((pkey, tl))
            letter = first(letter, pl) if prev is None else succ(prev, pl)
            if letter is None:
                row["why"] = "numEnd"
                continue
            last[(pkey, tl)] = letter
        row["letter"] = new_letter[s] = letter

    kept = Counter(r["why"] for r in rows if r["why"])
    summary = {"anchor": [an["template"], int(an["level"])] if an else None, "anchorLeaf": bool(an) and int(an["level"]) + up > len(a_chain),
               "base": [base, base_level] if base else None,
               "levels": dict(Counter(f"{r['level'][0]}|{r['level'][1]}" for r in rows if r["level"])),
               "slots": dict(Counter(f"{r['slot'][0]}|{r['slot'][1]}" for r in rows if r["slot"] and not r["why"])),
               "convertible": sum(1 for r in rows if not r["why"]), "kept": dict(kept), "cells": sum(r["cells"] for r in rows)}
    if seen:   # 넘친 레벨이 있는 넣기 — 사례 하나(모듈 설명 「넘친 개요 레벨」)
        under = []   # 그 자리 아래에 이미 붙어 있는 다른 템플릿(「다른 템플릿」 후보의 맨 앞) — 자리표시 줄을 대신하는 넣기(sibling)는 해당 없음
        for n in () if sibling else to_graph.get("nodes") or ():
            if n.get("template") and n.get("level") and n["template"] != an["template"] and n["template"] not in under and tp.get(n["para"]) is n and _parent_para(n, tid) == anchor_id:
                under.append(n["template"])
        summary["over"] = {"key": case, "to": [an["template"], K], "from": [base, s0], "tail": tail, "lines": sum(v["lines"] for v in seen.values()), "under": under,
                           "levels": [seen.get(j) or {"n": K + j, "src": s0 + j - 1, "key": tail[j - 1] if j - 1 < len(tail) else "", "was": "", "rep": None, "lines": 0}
                                      for j in range(1, max(len(tail), max(seen)) + 1)]}
    return {"rows": rows, "summary": summary}


def _line(to_doc, r, nid, new_of, prefix, tok):
    """넘친 줄 하나의 기록(모듈 설명 「기록」) — 고치기 **전에** 부른다(orig = 넣은 그대로의 접두와 문단·글자 모양 참조). parent = 함께 넣은 부모 줄(넘친 줄이든 맞는 레벨 줄이든)의 넣은 id."""
    return {"id": nid, "src": r["src"], "over": r["over"], "was": tok, "letter": tok, "parent": new_of.get(r.get("parent")), "pl": r.get("pl"),
            "orig": {"prefix": prefix, "attrs": to_doc.para_attrs(nid)}}


def apply(to_doc, pairs, plan):
    """계획대로 넣은 사본의 접두를 목적 자리 모양으로 → {"converted", "kept": {why: n}, "ids", "lines": 넘친 줄의 기록}. 바꾸지 못한 줄은 원본 모양 그대로."""
    new_of = dict(pairs)
    kept, ids, lines, measure = Counter(), [], [], None
    for r in plan["rows"]:
        nid = new_of.get(r["src"])
        alive = nid is not None and nid in to_doc._ids
        lead, tok, gap = prefix_of(to_doc._text(to_doc._ids[nid]), r["was"] or None) if alive and r["level"] else ("", "", "")
        rec = _line(to_doc, r, nid, new_of, lead + tok + gap, tok) if r.get("over") and tok else None   # 넘친 줄은 그대로 둔 것도 적어 둔다(다시 맞추기의 근거)
        if rec:
            lines.append(rec)
        if r["why"]:
            kept[r["why"]] += 1
            if r["cells"]:
                kept["cell"] += r["cells"]
            continue
        if not alive:
            kept["missing"] += 1
            continue
        if not tok:
            kept["noLetter"] += 1
            continue
        if r.get("own"):   # 넘친 레벨 — 제 모양을 둔 채 레터·앞 공백만(본보기 없음)
            prefix, like_id = (" " * r["lead"] if r.get("lead") is not None else lead) + r["letter"] + gap, None
        else:
            like = to_doc._ids.get(r["like"])  # 블록 id 는 blocks() 를 읽을 때 붙는다 — 부르는 쪽이 이미 읽은 문서
            llead, ltok, lgap = prefix_of(to_doc._text(like), r["likeLetter"] or None) if like is not None else ("", "", "")
            if not ltok:
                kept["noLike"] += 1
                continue
            prefix, like_id = (" " * r["lead"] if r.get("lead") is not None else llead) + r["letter"] + lgap, r["like"]
        try:
            to_doc.replace_prefix(nid, len(lead) + len(tok) + len(gap), prefix, like_id=like_id)
        except ValueError:
            kept["marker"] += 1
            continue
        if like_id:  # 확정 서식으로(spec_hwpx_웹편집 ② §8-8): 본보기가 「둘째 줄 = 글 시작」 꼴이면 넣은 줄도 제 접두 폭으로(번호형 「10.」 처럼 접두 폭이 본보기와 다른 줄) — 레터 뒤 묶음 빈칸은 본보기 접두를 복사해 이미 같다
            from app import outline_conform  # 이 모듈은 문서를 안 보는 계획(plan)이 본체라 부를 때 가져온다
            measure = measure or outline_conform.OP.Measure(to_doc)
            try:
                outline_conform.after_insert(to_doc, nid, r["letter"], like_id, r["likeLetter"] or None, measure)
            except Exception:  # noqa: BLE001 — 자리를 못 맞춰도 넣기는 그대로(본보기 모양)
                pass
        ids.append(nid)
        if rec:
            rec["letter"] = r["letter"]
    return {"converted": len(ids), "kept": dict(kept), "ids": ids, "lines": lines}


def record(summary, res):
    """넘친 줄의 반영 기록(spec_병합 ② §5-5 7) {key, to[자리 템플릿, K], lines} — 넘친 줄이 없으면 None."""
    ov, lines = (summary or {}).get("over"), (res or {}).get("lines")
    return {"key": ov["key"], "to": ov["to"], "lines": lines} if ov and lines else None


def converter(to_doc, to_graph, from_graph, over=None):
    """본문 넣기 고리 — convert(anchor_id, pairs[(원본 id, 사본 id)]) 가 계획하고 바로 바꾼다 → apply 결과 + {"plan": 요약, "over": 넘친 줄 기록 | None}. over = plan 의 그것."""
    def convert(anchor_id, pairs):
        p = plan(to_graph, from_graph, anchor_id, [s for s, _ in pairs], over=over)
        res = apply(to_doc, pairs, p)
        return {**res, "plan": p["summary"], "over": record(p["summary"], res)}
    return convert
