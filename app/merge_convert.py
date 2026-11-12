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
- `converter(to_doc, to_graph, from_graph)` → `convert(anchor_id, pairs)` — 본문 넣기가 복사한 바로 뒤 부르는 고리(apply 결과 + plan 요약)."""
from collections import Counter

from app.outline_edit import ROOTED, first, is_numbered, prefix_of, succ

_CLEAR = ("not_heading", "note")  # 의미 부모를 찾을 때 투명한 노드(heading_graph._eff_parent 와 같음)


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


def plan(to_graph, from_graph, anchor_id, src_ids, sibling=False):
    """복사한 원본 블록(src_ids — 문서 순)을 목적 문서 anchor_id 아래 넣을 때 줄마다 목적 자리·레터·본보기 → {"rows", "summary"}(모듈 설명).
    sibling=True 면 anchor_id 는 넣을 자리의 **부모가 아니라 그 자리의 줄**이다(취합 — 자리표시 줄을 대신하는 내용, merge_gather_fit): 맨 위 줄이 그 줄과 같은 (템플릿, 레벨)을 받는다."""
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
        if tl > len(a_chain):
            row["why"] = "tooDeep"
            continue
        row["slot"] = [an["template"], tl]
        like = members.get(tl) or reps.get(tl)
        ln = tp.get(like) if like else None
        if ln is None or tper[like] != 1:
            row["why"] = "noLike"
            continue
        row["like"], row["likeLetter"] = like, ln.get("letter") or ""
        p = par[s]
        pkey = p if p in copied else anchor_id
        pl = new_letter.get(p) if p in copied else top_letter
        letter = row["likeLetter"]
        if is_numbered(a_chain[tl - 1]):
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
    return {"rows": rows, "summary": summary}


def apply(to_doc, pairs, plan):
    """계획대로 넣은 사본의 접두를 목적 자리 모양으로 → {"converted", "kept": {why: n}, "ids"}. 바꾸지 못한 줄은 원본 모양 그대로."""
    new_of = dict(pairs)
    kept, ids = Counter(), []
    for r in plan["rows"]:
        if r["why"]:
            kept[r["why"]] += 1
            if r["cells"]:
                kept["cell"] += r["cells"]
            continue
        nid = new_of.get(r["src"])
        if nid is None or nid not in to_doc._ids:
            kept["missing"] += 1
            continue
        lead, tok, gap = prefix_of(to_doc._text(to_doc._ids[nid]), r["was"] or None)
        if not tok:
            kept["noLetter"] += 1
            continue
        like = to_doc._ids.get(r["like"])  # 블록 id 는 blocks() 를 읽을 때 붙는다 — 부르는 쪽이 이미 읽은 문서
        llead, ltok, lgap = prefix_of(to_doc._text(like), r["likeLetter"] or None) if like is not None else ("", "", "")
        if not ltok:
            kept["noLike"] += 1
            continue
        try:
            to_doc.replace_prefix(nid, len(lead) + len(tok) + len(gap), llead + r["letter"] + lgap, like_id=r["like"])
        except ValueError:
            kept["marker"] += 1
            continue
        ids.append(nid)
    return {"converted": len(ids), "kept": dict(kept), "ids": ids}


def converter(to_doc, to_graph, from_graph):
    """본문 넣기 고리 — convert(anchor_id, pairs[(원본 id, 사본 id)]) 가 계획하고 바로 바꾼다 → apply 결과 + {"plan": 요약}."""
    def convert(anchor_id, pairs):
        p = plan(to_graph, from_graph, anchor_id, [s for s, _ in pairs])
        return {**apply(to_doc, pairs, p), "plan": p["summary"]}
    return convert
