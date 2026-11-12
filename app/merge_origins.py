"""병합 — 원본 자리 지도(spec_작업 ② §12 「누른 자리 따라 보기」, 2026-11-12 사용자 "작성된 부분은 클릭하면 상대 페이지 바로 보여주기"):
목적 문서(연차보고서)의 자리 id → 원본 문서(사업계획서)의 자리 id. 화면이 목적 문서에서 누른 문단·칸의 원본 자리를 둘째 면에 바로 띄우는 데 쓴다. 문서는 읽기만 한다(스크립트만 — LLM 없음).

- `build(to, frm, view, applied=None, forced=None)` → {"map": {목적 id: 원본 id}, "counts": {groups, tables, labels, blocks, cells}}.
  to·frm = merge_api._read 의 꼴({"doc", "graph", "tables", "values"}), view = `merge_pairs.pair` 결과(연결 목록), applied = 믿을 넣은 기록(merge_api._alive), forced = 사람·LLM 이 정한 표 짝.
- **넣을 때 적어 둔 대응을 읽는 것이 아니라 지금 두 문서의 짝을 다시 셈한다** — 넣기 계획(merge_fill·merge_tables·merge_fixed)과 같은 규칙이라, 이 기능이 생기기 전에 넣은 문서에서도 되고
  실행 취소·사람이 고친 뒤에도 지금 문서에 맞는다. 넣은 뒤에 남는 기록은 본문 항목의 넣은 블록(merge.json `applied[].ids`)뿐이어서 그것만 기록에서 읽는다.
- 든 것(거친 것 → 촘촘한 것 — 같은 id 면 뒤가 이긴다): ① 이어진 묶음(자리 묶음 key) ② 묶음 항목(구분 값마다의 라벨·칸) ③ 표 짝(묶음의 표 · 같은 이름 자리의 표) ④ 같은 이름 라벨·본문 항목 라벨
  ⑤ 넣은 블록 ↔ 원본 블록(차례대로 — 그 안의 표 칸·문단도 꼴이 같으면 하나씩, 다르면 모두 그 원본 블록으로) ⑥ 칸 짝(merge_tables `pairs`·`cells` · merge_fixed.pairs)
  ⑦ 짝이 있는 표·그림의 캡션 문단(원본 개체의 캡션으로).
  화면은 누른 문단에서 바깥으로(문단 → 칸 → 표 → 바깥 칸 …) 올라가며 처음 맞는 id 를 쓴다 — 칸 짝이 없으면 표 짝으로 간다.
- 짝이 **분명한 것만** 든다(계획이 모호하다고 건너뛴 칸은 없다 — 틀린 자리로 가는 것보다 안 가는 것이 낫다). 두 문서에 지금 없는 id 는 뺀다.
- 못 내는 것: 반영으로 늘린 행인데 그 뒤 글을 고쳐 원본 행과 달라진 행(같은 행인지 글로 본다) · `ids` 없이 남은 옛 넣은 기록의 본문 블록(그 항목의 라벨로만 간다)."""
from app import merge_fill as MF
from app import merge_fixed as MX
from app import merge_tables as MT
from app.division_profiles import _structure as structure


def _walk(b):
    """블록과 그 안(표 칸 · 칸 안 블록 — 중첩 표 포함)을 문서 차례로 → (종류, id)."""
    yield (b.get("type") or "cell"), b.get("id")
    for c in b.get("cells") or ():
        yield "cell", c.get("id")
        for x in c.get("blocks") or ():
            yield from _walk(x)


def _spread(out, new, old, t_idx, f_idx):
    """넣은 블록 new(목적) ↔ 원본 블록 old — 그 안의 칸·문단도 함께: 두 블록의 꼴(종류의 차례)이 같으면 하나씩, 다르면(넣은 뒤 행을 늘렸거나 원본이 바뀜) 모두 old 로. → 이었나."""
    a, b = t_idx.get(new), f_idx.get(old)
    if a is None or b is None:
        return False
    ta, tb = list(_walk(a)), list(_walk(b))
    same = [k for k, _ in ta] == [k for k, _ in tb]
    for i, (_, x) in enumerate(ta):
        if x:
            out[x] = (tb[i][1] if same else None) or old
    return True


def build(to, frm, view, applied=None, forced=None):
    """원본 자리 지도(모듈 설명) — 문서를 안 고친다. 부르는 쪽이 목적 문서의 세션 잠금을 잡는다(merge_api.merge_plan 과 같은 조건)."""
    applied = applied or {}
    t_idx, f_idx = structure.index_blocks(to["doc"].blocks()), structure.index_blocks(frm["doc"].blocks())
    fill = MF.plan(to, frm, to["values"], frm["values"], view, applied=applied)
    tabs = MT.plan(to, frm, to["values"], frm["values"], view)
    fixed = MX.plan(to, frm, applied=applied, tables_plan=tabs, forced=forced)
    tpairs, cpairs = MX.pairs(to, frm, forced=forced)   # 넣은 뒤에도 같은 짝이 나오는 셈(빈 칸이 없는 표 · 이미 옮긴 체크 칸도)
    out, n = {}, {"groups": 0, "tables": 0, "labels": 0, "blocks": 0, "cells": 0}

    def put(kind, a, b):
        if a and b and a in t_idx and b in f_idx:
            n[kind] += out.get(a) != b
            out[a] = b

    for g in view.get("groups") or ():   # ①② 이어진 묶음과 그 항목
        if g.get("status") != "paired" or not g.get("to") or not g.get("from"):
            continue
        put("groups", g["to"].get("key"), g["from"].get("key"))
        for it in g.get("items") or ():
            if it.get("status") == "paired" and it.get("to") and it.get("from"):
                put("groups", it["to"].get("id"), it["from"].get("id"))
    for t in tabs["tables"]:   # ③ 표 짝 — 묶음의 표
        put("tables", t.get("to"), t.get("from"))
    for a, b in tpairs:   # ③ 표 짝 — 같은 이름 자리의 표
        put("tables", a, b)
    for row in (*fill["items"], *fixed["labels"]):   # ④ 라벨 ↔ 라벨 · ⑤ 넣은 블록 ↔ 원본 블록
        put("labels", row.get("to"), row.get("from"))
        ids, src = (applied.get(row.get("to")) or {}).get("ids") or (), row.get("src") or ()
        if not src:
            continue
        for i, new in enumerate(ids):   # 차례대로(insert_after 가 원본 블록마다 새 id 하나) — 수가 다르면(원본이 그 뒤 바뀜) 남는 것은 끝 블록으로
            n["blocks"] += _spread(out, new, src[min(i, len(src) - 1)], t_idx, f_idx)
    for a, b in tabs.get("pairs") or ():   # ⑥ 칸 짝 — 묶음의 표(정해진 자리 · 이미 있는 이어 넣은 행)
        put("cells", a, b)
    for c in (*tabs["cells"], *fixed["cells"]):   # 아직 안 넣은 칸(넣기 계획의 할 일)도 짝이다
        put("cells", c.get("to"), c.get("from"))
    for a, b in cpairs:   # ⑥ 칸 짝 — 같은 이름 자리의 표
        put("cells", a, b)
    f_caps, seen = {}, {}   # ⑦ 캡션 — 표·그림에 딸려 온 캡션 문단(따로 복사하는 블록이 아니다)은 그 표·그림의 짝을 따라: 원본 개체의 캡션(차례대로), 없으면 그 개체
    for b in f_idx.values():
        if b.get("captionOf"):
            f_caps.setdefault(b["captionOf"], []).append(b["id"])
    for b in t_idx.values():
        host = b.get("captionOf")
        if host and host in out and b["id"] not in out:
            k = seen[host] = seen.get(host, -1) + 1
            caps = f_caps.get(out[host]) or ()
            out[b["id"]] = caps[min(k, len(caps) - 1)] if caps else out[host]
            n["blocks"] += 1
    return {"map": out, "counts": n}
