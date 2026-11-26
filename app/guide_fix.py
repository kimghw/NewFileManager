"""지침 보정(spec_워크플로우 ② §18-23 「지침 보정」) — 내용을 넣은 뒤 양식의 **작성 지침**(작성 요령 표 · ※ 안내 · <참고 N> · 각주 번호가 가리키는 항목 — 저장해 둔 것)에 따라
그 헤딩 · 그 표에 **이미 들어간 글을 LLM 이 고친다**. 2026-11-22 사용자 "3단계 본문 및 테이블 매칭 이후에 문서의 테이블이나 본문의 지침에 따라 LLM 보정해 주는 단계를 4단계 도구에 추가해줘".
**문서를 고치지 않는다** — 자료 · 프롬프트 · 답 검증만(묻기 · 반영 · 저장은 `app/guide_fix_api.py`).

- `units(blocks, graph, saved, found)` → (자리 목록, 검증 재료) — 자리 하나 = 지침 묶음 하나(`form_guides.groups`): 헤딩 묶음 = 그 헤딩 줄 다음부터 같거나 얕은 깊이(그래프 `depth`)의 다음 본문 헤딩 전까지 ·
  표 묶음 = 그 표(헤딩 자리 안에 든 표는 그 헤딩의 자리로 — 같은 표를 두 번 묻지 않는다). 양식 안내 블록(`form_cleanup.find`)과 헤딩 줄은 글로만 보이고 고칠 대상이 아니다.
- LLM 은 있는 글을 지침에 맞게 고치기만 한다(새 사실 · 수를 짓지 않는다) — `check` 가 지킨다: 그 자리의 고칠 수 있는 문단 id 만 · 새 글의 수는 그 자리의 글에 있는 수만 · `GROW` 넘게 늘리지 않음.
- `ask(prep, job)` → {"fixes"[{unit, id, old, new, rule, why}], "left"[{unit, id, why}], "rejected"[{unit, id, why}], "units"[…], "asked", "guide", "job"}."""
import json
import re

from app import prompt_texts
from app import job_prompts, llm, merge_guides
from app.division_profiles import _structure as structure

S_ = {"type": "string"}


def _obj(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def _arr(item):
    return {"type": "array", "items": item}


SCHEMA = _obj({"fixes": _arr(_obj({"unit": S_, "id": S_, "new": S_, "rule": S_, "src": S_, "why": S_})), "left": _arr(_obj({"unit": S_, "id": S_, "why": S_})),
               "ok": _arr(_obj({"unit": S_, "why": S_}))})   # src = 따른 지침의 출처 · ok = 지침에 맞는 자리(「맞음」 — 사람이 검토 결과를 본다: spec_양식작성 ② §5-9 「지침 검토 · 수정」)
SRCS = ("doc", "user", "form", "rule", "purpose", "struct")   # 조립된 지침의 출처(place_guides — 문서 · 사람 · 양식 지침 · 규정 · 문서 목적 · 표 구조)
GUIDE, MODEL = "guide_fix", "claude-opus-5-5"
SCOPE_MAX, GUIDE_MAX, CALL_MAX, UNIT_MAX, TEXT_MAX = 12000, 6000, 24000, 4, 1500   # 자리 하나의 글 · 지침 글 · 한 호출의 자료 · 한 호출의 자리 수 · 문단 하나의 글(보내는 꼴)
GROW, GROW_MIN = 0.2, 20   # 새 글이 늘 수 있는 몫(옛 글의 20% 와 20자 가운데 큰 것)
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")

CONTRACT = """당신은 국가R&D 문서(연차보고서 등 — **목적 문서**)에 내용을 옮겨 넣은 뒤, 양식이 글쓴이에게 준 **작성 지침**(작성 요령 · ※ 안내 · <참고 N> 자료 · 각주 번호가 가리키는 작성 요령 항목)에 맞게
**이미 들어간 글을 고치는** 검토자입니다. 새 내용을 쓰지 않습니다 — 있는 글을 지침이 정한 꼴로 고치거나 덜어 냅니다.

### 자료
units = 자리 [{key, kind("heading" = 그 헤딩 아래 본문 · "table" = 그 표), where(헤딩 글 · 표 이름), guides[{kind, text, src?}](그 자리에 붙은 작성 지침 — src = 출처: doc 양식의 작성요령 · user 사람 · form 양식 지침 · rule 규정(kind 에 「필수 · 권고」 와 출처) · purpose 문서 목적 · struct 표 구조. 그 자리의 것 다음에 윗 절의 것이 이어집니다), content[…], cut(참이면 자리의 글이 길어 앞부분만 보냄)}].
docGuides(있을 때) = 문서 전체에 닿는 지침(규정 · 문서 목적 · 일반 가이드라인 — 모든 자리에 함께 봅니다).
content 의 줄 = {id, text}(고칠 수 있는 문단) · {h}(헤딩 줄 — 고칠 수 없음) · {table, cells[{rc(행 r · 열 c), id, text}]}(표 — 칸 안 문단마다 id) · {pic: true}(그림 · 개체 — 고칠 수 없음).

### 답
- fixes = [{unit, id, new, rule, why}] — id 는 그 자리(unit)의 content 에 있는 문단 id 만. new = 그 문단의 **고친 글 전체**(빈 글 "" 이면 그 문단의 글을 지움 — 지침이 지우라고 한 예시 · 남은 자리표시).
  - 고치는 것: 지침이 정한 표기 · 단위 · 날짜 꼴 · 정해진 말(예: 「수요」 · 「공동」) · 분량 한도(「N page 이내」 · 「N줄 이내」)를 넘는 글 덜기 · 지침이 지우라고 한 예시 · 자리표시.
  - **새 사실 · 수를 짓지 않습니다** — 새 글의 수는 그 자리의 글에 이미 있는 수만 씁니다(스크립트가 검사해 어긴 고침은 버립니다). 글을 늘리지 않습니다.
  - 지침에 맞는 글은 그대로 둡니다(fixes 에 넣지 않습니다). 확신이 없으면 고치지 않습니다 — 틀리게 고치는 것보다 그대로 두는 것이 낫습니다.
- left = [{unit, id, why}] — 지침에 맞지 않지만 **문서에 없는 정보가 있어야** 고칠 수 있는 것(id 는 그 문단 · 자리 전체면 "").
- ok = [{unit, why}] — 그 자리의 글이 지침에 맞아 고칠 것이 없는 자리(why = 무엇을 보고 맞다고 했는지 한 문장). 고침 · left 가 있는 자리는 넣지 않습니다.
- rule = 따른 지침의 말(짧게 인용) · src = 그 지침의 출처(guides 의 src 그대로 — docGuides 의 것이면 그 줄 머리의 「규정」 은 rule · 「문서 목적」 은 purpose · 그 밖은 form) · why = 무엇을 왜 고쳤는지(또는 왜 못 고치는지) 한 문장."""

FALLBACK_GUIDE = """- 지침이 꼴(표기 · 단위 · 날짜 · 정해진 말)을 정한 곳은 그 꼴로 고친다. 지침이 분량을 정한 곳은 넘는 뒷부분을 덜어 낸다(앞부분의 뜻을 바꾸지 않는다).
- 지침이 「삭제」 · 「지우고 작성」 이라 한 예시 글 · 자리표시가 남아 있으면 지운다. 지침이 말하지 않는 문장은 고치지 않는다."""


def _short(text, n):
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def _nums(text):
    return {m.group(0).replace(",", "").rstrip(".") for m in _NUM.finditer(text or "")}


def _heads(graph, pos):
    """본문 헤딩 줄 → [(본문 차례, 문단 id, 깊이 | None)] — 문서 차례대로(form_guides._headings 와 같은 줄)."""
    out = []
    for nd in (graph or {}).get("nodes") or ():
        if isinstance(nd, dict) and nd.get("role") == "heading" and nd.get("area") == "body" and nd.get("para") in pos:
            out.append((pos[nd["para"]], nd["para"], nd.get("depth")))
    return sorted(set(out), key=lambda x: x[0])


def _guide_ids(found, blocks):
    """양식 안내 블록 id(작성 요령 표 · <참고 N> 자료 · 안내뿐인 ※ 줄) — 고칠 대상이 아니다."""
    idx = structure.index_blocks(blocks)
    out = set()
    for t in found.get("tables") or ():
        out |= {x["id"] for x in structure.iter_blocks([idx[t["id"]]])} if t["id"] in idx else set()
    pos = {b["id"]: k for k, b in enumerate(blocks)}
    for r in found.get("refs") or ():
        a, e = pos.get(r["id"]), pos.get(r.get("last"))
        for k in range(a, (e if e is not None and e >= a else a) + 1) if a is not None else ():
            out |= {x["id"] for x in structure.iter_blocks([blocks[k]])}
        out.add(r["id"])
    out |= {n["id"] for n in found.get("notes") or () if n.get("whole")}
    out |= {h["id"] for h in found.get("hints") or ()}   # 설명 줄(표 아래 「* …」 — 모으기만 하는 지침: form_cleanup hints)도 양식의 글이다
    return out


def _cells(b):
    """표 → [(행, 열, 칸 안 문단 [(id, 글)])] — 칸 안의 표는 그 칸의 문단으로 펴서."""
    out = []
    for c in sorted(b.get("cells") or (), key=lambda c: (c.get("row") or 0, c.get("col") or 0)):
        paras = [(x["id"], x.get("text") or "") for x in structure.iter_blocks(c.get("blocks") or ()) if x.get("type") == "paragraph"]
        out.append((c.get("row") or 0, c.get("col") or 0, paras))
    return out


def _guides_of(g):
    """지침 묶음 → [{kind, text}] — 글이 있는 지침 · 각주 번호가 가리키는 항목(GUIDE_MAX 자까지)."""
    out, used = [], 0
    for x in g.get("items") or ():
        if (x.get("text") or "").strip():
            out.append({"kind": x.get("name") or x.get("kind") or "", "text": x["text"].strip()})
    for m in g.get("marks") or ():
        if (m.get("text") or "").strip():
            out.append({"kind": f"각주 {m.get('no')}) — {_short(m.get('label'), 40)}", "text": m["text"].strip()})
    keep = []
    for x in out:
        if used >= GUIDE_MAX:
            break
        x = {**x, "text": x["text"][:GUIDE_MAX - used]}
        used += len(x["text"])
        keep.append(x)
    return keep


def _content(seq, guide_ids, heads_at):
    """자리의 블록들 → (content 줄, {고칠 문단 id: 옛 글}, 자리의 글, 잘림)."""
    lines, ids, texts, size, cut = [], {}, [], 0, False

    def take(text):
        nonlocal size, cut
        if size >= SCOPE_MAX:
            cut = True
            return False
        size += len(text)
        texts.append(text)
        return True
    for b in seq:
        if b["id"] in guide_ids:
            continue
        t = b.get("type")
        if t == "paragraph":
            text = b.get("text") or ""
            if not text.strip():
                continue
            if not take(text):
                break
            if b["id"] in heads_at:
                lines.append({"h": _short(text, 200)})
            else:
                lines.append({"id": b["id"], "text": text[:TEXT_MAX]})
                ids[b["id"]] = text
        elif t == "table":
            cells = []
            for r, c, paras in _cells(b):
                for pid, text in paras:
                    if pid in guide_ids or not text.strip():
                        continue
                    if not take(text):
                        break
                    cells.append({"rc": f"r{r}c{c}", "id": pid, "text": text[:TEXT_MAX]})
                    ids[pid] = text
            if cells:
                lines.append({"table": b["id"], "cells": cells})
            if cut:
                break
        elif t is not None:
            lines.append({"pic": True})
    return lines, ids, "\n".join(texts), cut


def _assembled(ix, at, kind, pid, seq):
    """조립된 지침(place_guides.index 꼴 ix + resolver at) → 그 자리의 [{kind, text, src}] — 그 자리의 것 → 표 구조 → 윗 절의 것(이관 3단계 · 양식 작성 초안과 같은 조립) + 헤딩 자리면 그 구간에 든 표의 것.
    GUIDE_MAX 자까지 — 넘치면 출처 순위가 낮은 것부터 뺀다(place_guides.pack)."""
    from app import place_guides as PG
    gs = list(at("table" if kind == "table" else "block", pid))
    if kind == "heading":
        for b in seq:
            for x in structure.iter_blocks([b]):
                if x.get("type") == "table":
                    gs += (ix.get("tables") or {}).get(x["id"]) or []
    rows, _ = PG.pack(gs, limit=GUIDE_MAX)
    return [{"kind": PG.tag(g) if g.get("src") in ("rule", "purpose") else (g.get("kind") or "") + (f" — {_short(g['label'], 40)}" if g.get("label") else ""),
             "text": g["text"].strip(), "src": g.get("src") or "doc"} for g in rows if (g.get("text") or "").strip()]


def units(blocks, graph, saved, found, ix=None):
    """자리 목록 → ([{key, kind, where, guides, content, cut}], {자리 key: {ids{문단 id: 옛 글}, nums, where, kind}}). saved = 저장한 작성 지침(form_guides_api.load 꼴).
    ix = 조립된 자리 지침 색인(place_guides_api.index_of — 문서 · 사람 · 양식 지침 · 규정 · 문서 목적: spec_양식작성 ② §5-9 「지침 검토 · 수정」)을 주면 지침을 그 조립 결과로 받고(출처 `src` 와 함께 · 윗 절의 것까지),
    자리도 그 색인에 제 지침이 있는 헤딩 · 표로 넓힌다(문서에 작성요령이 없어도 양식 지침 · 규정이 붙은 자리를 본다). ix 가 없으면 전처럼 저장한 작성 지침의 묶음만."""
    from app import form_guides
    pos = {b["id"]: k for k, b in enumerate(blocks)}
    heads = _heads(graph, pos)
    heads_at = {pid for _, pid, _ in heads}
    guide_ids = _guide_ids(found or {}, blocks)
    G = form_guides.groups(saved or {})
    out, ctx, covered = [], {}, set()
    at = None
    if ix:
        from app import place_guides as PG
        at = PG.resolver(ix, blocks, graph)
        by = {b["id"]: b for b in blocks}
        have = {g["id"] for g in G["headings"]}
        G = {"headings": sorted([*G["headings"], *({"id": h, "text": (ix.get("heads_text") or {}).get(h) or (by.get(h) or {}).get("text") or "", "items": [], "marks": []}
                                                    for h, v in (ix.get("heads") or {}).items() if v and h in pos and h not in have)], key=lambda g: pos.get(g["id"], 10 ** 9)),
             "tables": [*G["tables"], *({"id": t, "label": PG.table_head(by.get(t) or {}) or t, "items": [], "marks": []}
                                         for t, v in (ix.get("tables") or {}).items() if v and t in pos and t not in {g["id"] for g in G["tables"]})]}

    def add(kind, where, seq, g):
        guides = _guides_of(g)   # 저장한 작성 지침의 묶음 — 전과 같은 것이 먼저다(헤딩 그래프 · 3단계 결과가 없는 문서에서는 조립이 헤딩을 못 찾는다 — 그래도 이관형의 전 동작 그대로 자리가 선다)
        if at is not None:
            guides = [{**x, "src": "doc"} for x in guides]
            seen = {" ".join(x["text"].split()) for x in guides}
            guides += [x for x in _assembled(ix, at, kind, g["id"], seq) if " ".join(x["text"].split()) not in seen]   # 조립이 더한 것(사람 · 양식 지침 · 규정 · 문서 목적 · 표 구조 · 윗 절) — 같은 글은 하나
        if not guides:
            return
        lines, ids, text, cut = _content(seq, guide_ids, heads_at)
        if not ids:
            return
        key = f"u{len(out) + 1}"
        out.append({"key": key, "kind": kind, "where": _short(where, 120), "guides": guides, "content": lines, "cut": cut})
        ctx[key] = {"ids": ids, "nums": _nums(text), "where": _short(where, 120), "kind": kind}
    for g in G["headings"]:
        i = pos.get(g["id"])
        if i is None:
            continue
        me = next((h for h in heads if h[1] == g["id"]), None)
        depth = me[2] if me else None
        end = next((k for k, pid, d in heads if k > i and (depth is None or d is None or d <= depth)), len(blocks))
        seq = blocks[i + 1:end]
        covered |= {b["id"] for b in seq if b.get("type") == "table"}
        add("heading", g.get("text") or "", seq, g)
    for g in G["tables"]:
        i = pos.get(g["id"])
        if i is None or g["id"] in covered:
            continue
        add("table", g.get("label") or g["id"], [blocks[i]], g)
    return out, ctx


def batches(us):
    """자리들을 호출로 — 한 호출에 UNIT_MAX 자리 · CALL_MAX 자까지(문서 차례)."""
    out, cur, size = [], [], 0
    for u in us:
        n = len(json.dumps(u, ensure_ascii=False))
        if cur and (len(cur) >= UNIT_MAX or size + n > CALL_MAX):
            out.append(cur)
            cur, size = [], 0
        cur.append(u)
        size += n
    return out + ([cur] if cur else [])


def guide_part(g=None):
    g = merge_guides.get(GUIDE) if g is None else g
    return merge_guides.part(g) or f"\n\n## 판단 지침 — 기본\n\n{FALLBACK_GUIDE}"


def prompt(payload, job=None, guide=None):
    """프롬프트 글 = 계약 + 판단 지침 + 할 일 프롬프트 + 자료(JSON)."""
    return prompt_texts.contract(__name__) + guide_part(guide) + job_prompts.part(job) + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parts(job=None, guide=None):
    """화면 「지침」 보기 · 에이전트 설정에 싣는 글들(자료 빼고) — merge_gaps.parts 와 같은 꼴."""
    g = merge_guides.get(GUIDE) if guide is None else guide
    out = [{"key": "contract", "title": "계약 — 역할 · 자료 설명 · 답의 꼴", "text": prompt_texts.contract(__name__), "source": "app/guide_fix.py",
            "note": "코드에 든 글입니다(답을 검증하는 코드와 한 몸) — 판단 기준은 아래 지침에 있습니다"}]
    if g and merge_guides.body(g):
        out.append({"key": "guide", "title": f"판단 지침 — {g['title']}", "text": merge_guides.body(g), "source": g["path"], "note": "이 파일을 고치면 다음 실행부터 적용됩니다"})
    else:
        out.append({"key": "guide", "title": "판단 지침 — (지침 파일 없음: 기본 기준)", "text": FALLBACK_GUIDE.strip(), "source": "app/guide_fix.py", "note": "app/merge_guides_default/guide_fix.md 가 없어 기본 기준만 보냅니다"})
    if job and job_prompts.part(job):
        out.append({"key": "job", "title": f"할 일 프롬프트 — {job['name']}", "text": job_prompts.body(job.get("text")), "source": job.get("path") or "", "note": "이 작업의 전제 — 먼저 따릅니다"})
    return out


def check(ctx, answer):
    """답 검증 → (fixes[{unit, id, old, new, rule, why}], left[{unit, id, why}], rejected[{unit, id, why}]). 한 문단은 처음 고침만."""
    fixes, left, rejected, seen = [], [], [], set()
    for f in (answer or {}).get("fixes") or ():
        if not isinstance(f, dict):
            continue
        u, pid, new = f.get("unit"), f.get("id"), f.get("new")
        c = ctx.get(u)
        bad = ("모르는 자리" if c is None else "그 자리에 없는 문단(고칠 수 없는 줄 포함)" if pid not in c["ids"] else "새 글이 글이 아님" if not isinstance(new, str)
               else "이미 고친 문단" if pid in seen else "")
        if not bad:
            old = c["ids"][pid]
            new = new.replace("\n", " ").strip() if new.strip() else ""
            if new == old.strip():
                continue   # 그대로 — 고침이 아니다
            extra = _nums(new) - c["nums"] - _nums(old)
            bad = (f"지은 수 {', '.join(sorted(extra))}" if extra else
                   f"글이 너무 늘어남({len(old)} → {len(new)}자)" if len(new) > len(old) + max(GROW_MIN, int(len(old) * GROW)) else "")
        if bad:
            rejected.append({"unit": u or "", "id": pid or "", "why": bad})
            continue
        seen.add(pid)
        fixes.append({"unit": u, "id": pid, "where": c["where"], "old": c["ids"][pid], "new": new, "rule": _short(f.get("rule"), 200), "why": _short(f.get("why"), 300),
                      **({"src": f["src"]} if f.get("src") in SRCS else {})})   # src = 따른 지침의 출처(조립된 지침으로 물었을 때 — 화면이 「어느 지침 · 출처」 를 보인다)
    for x in (answer or {}).get("left") or ():
        if isinstance(x, dict) and x.get("unit") in ctx:
            left.append({"unit": x["unit"], "id": x.get("id") if x.get("id") in ctx[x["unit"]]["ids"] else "", "where": ctx[x["unit"]]["where"], "why": _short(x.get("why"), 300)})
    return fixes, left, rejected


def oks(ctx, answer, fixes=(), left=()):
    """답의 「맞음」 → [{unit, where, why}] — 아는 자리만 · 고침 · 못 고침이 있는 자리는 뺀다(맞음이 아니다) · 자리마다 하나."""
    busy = {x["unit"] for x in [*fixes, *left]}
    out, seen = [], set()
    for x in (answer or {}).get("ok") or ():
        u = x.get("unit") if isinstance(x, dict) else None
        if u in ctx and u not in busy and u not in seen:
            seen.add(u)
            out.append({"unit": u, "where": ctx[u]["where"], "why": _short(x.get("why"), 300)})
    return out


def places(ctx, fixes=(), left=(), ok=(), failed=()):
    """자리마다의 검토 결과 [{unit, where, kind, state("fix" 고침 제안 | "left" 못 고침 | "ok" 맞음 | "none" 답 없음), fixes(수), left(수), why}] — 사람이 검토 결과를 자리마다 본다. failed = 답을 못 받은 자리 key 들."""
    out = []
    why = {x["unit"]: x.get("why") or "" for x in ok}
    for u, c in ctx.items():
        nf, nl = sum(1 for f in fixes if f["unit"] == u), sum(1 for x in left if x["unit"] == u)
        state = "fix" if nf else "left" if nl else "ok" if u in why else "none"
        out.append({"unit": u, "where": c["where"], "kind": c["kind"], "state": state, "fixes": nf, "left": nl,
                    "why": why.get(u, "") if state == "ok" else "LLM 이 답을 내지 못했습니다" if state == "none" and u in set(failed) else ""})
    return out


def ask(prep, job=None, model=MODEL, effort="medium", timeout=300.0):
    """prepare 가 만든 자리들을 묻고(병렬 — 호출마다 UNIT_MAX 자리) 답을 검증 → {"fixes", "left", "rejected", "units"[{n, keys, error, prompt, answer, call}], "asked", "guide", "job"}. 잠금 밖에서 부른다."""
    us, ctx = prep["units"], prep["ctx"]
    g = merge_guides.get(GUIDE)
    groups = batches(us)
    doc = {"docGuides": prep["doc"]} if prep.get("doc") else {}   # 문서 전체에 닿는 지침(규정 · 문서 목적 · 일반 가이드라인) — 호출마다 한 번(자리마다 되풀이하지 않는다)
    jobs = [{"schema": SCHEMA, "content": prompt({"units": b, **doc}, job, g), "what": f"guide-fix-{i + 1}", "timeout": timeout, "effort": effort, "model": model} for i, b in enumerate(groups)]
    res = llm.ask_all(jobs) if jobs else []
    out = {"fixes": [], "left": [], "rejected": [], "ok": [], "failed": [], "units": [], "asked": len(jobs), "guide": merge_guides.brief(g),
           "job": {k: job[k] for k in ("job", "name", "sha1") if k in job} if job and job_prompts.part(job) else None}
    for i, (b, j, r) in enumerate(zip(groups, jobs, res)):
        call = {k: r.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error", "retried")}
        out["units"].append({"n": i, "keys": [u["key"] for u in b], "where": [u["where"] for u in b], "error": call.get("error"), "prompt": j["content"], "answer": r.get("data"), "call": call})
        if r.get("data") is None:
            out["failed"] += [u["key"] for u in b]
            continue
        mine = {u["key"]: ctx[u["key"]] for u in b}
        fixes, left, rejected = check(mine, r["data"])
        out["fixes"] += fixes
        out["left"] += left
        out["rejected"] += rejected
        out["ok"] += oks(mine, r["data"], fixes, left)
    out["places"] = places(ctx, out["fixes"], out["left"], out["ok"], out["failed"])
    return out
