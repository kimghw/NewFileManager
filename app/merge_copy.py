"""병합 — 표 통째로 복사(spec_병합 ② §5-8 —2026-11-22 사용자(계획서와 연차보고서의 「[연구개발성과의 기술기여도]」 표를 나란히 보이며) "이 테이블은 그냥 복사 타입으로 넣어줘").
목적 양식이 「통째로 복사」 로 정해 둔 표는 칸을 맞추지 않는다 — 목적 표 자리에 원본(사업계획서)의 **같은 제목 표의 사본**을 넣고 목적 표를 지운다. 스크립트만(LLM 없음).
까닭: 그 표는 구조 반영이 기관 수만큼 행을 늘리는데(7개 기관) 계획서에는 값이 있는 기관만 적혀 있어(1개 기관), 칸 맞추기로는 빈 기관 행 6개가 남는다 — 계획서의 표가 그대로 답이다.

- 어느 표인가 = 목적 양식의 양식 정보 json 블록 `copy`(제목 목록 — `heading_forms.copy_tables`: 양식마다 정한 것이라 양식 정보에 둔다 · jobs/plan_to_report.md 「연결 코멘트」 와 같은 자리).
  제목 = 그 표의 소속 제목(3단계 owner — 「[연구개발성과의 기술기여도]」). 견줄 때 빈칸 · 괄호 기호를 뗀다(`key`).
- `plan(T, F, titles, copied=None)` = 넣기 계획(문서를 안 고침). T · F = merge_fixed._side 꼴. copied = merge.json `copied`(앞서 복사한 기록 {제목 열쇠: {to, from, hash}}).
  → {"items": [{key, title, to, from, rows, cols, skip, detail}], "tables": [이 계획이 맡는 목적 표 id — 다른 길(표 대응 · 묶음 · 같은 이름 자리)은 그 표를 건너뛴다], "counts", "todo"}.
  잇는 조건: 그 제목의 표가 두 문서에 **하나씩**(여럿이면 ambiguous — 짐작하지 않는다) · 기관 · 차년도 맥락이 어긋나지 않음 · 목적 표의 값 칸에 **원본 표에 없는 글이 없음**
  (사람이 쓴 글을 지우지 않는다 — 빈 칸 · 원본 표에 있는 글(앞선 넣기가 옮긴 값)뿐일 때만 바꾼다. 행 머리 · 열 머리는 안 따진다: 구조 반영이 넣은 기관 이름이다).
  앞서 복사한 표가 지금 문서에 있으면 applied(원본 표가 그 뒤 바뀌었으면 changed — 다시 넣지 않는다: 복사한 뒤 기관이 고친 글을 덮지 않게).
- `apply(to_doc, from_doc, plan)` = 계획을 목적 문서에 → {"copied", "records"{제목 열쇠: {to(새 표 id), from, hash}}, "inserted"{옛 표 id: [새 블록 id]}, "skipped"}.
  차례 = 원본 표의 사본을 목적 표의 문단 뒤에 넣고(`HwpxDoc.insert_after(kind=copy)` — 서식 · 칸 병합 · 글이 함께 온다) → 목적 표를 지운다(`delete_blocks`). 실행 취소는 반영 전체와 함께 1번.
맞추지 않는 것: 표 너비 · 열 너비(원본 표의 것 그대로 — spec_병합 ② §5-2 「안 맞추는 것」)."""
import hashlib
import json
import re
from collections import Counter

from app import merge_fixed as X
from app import merge_pairs as P

WHY = ("ambiguous", "noSource", "occupied", "org", "year", "changed")   # 못 넣는 까닭(applied 는 까닭이 아니라 끝난 것)
_STRIP = re.compile(r"[\s\[\]<>〈〉《》「」『』【】()（）:：·.\-]")


def key(title):
    """표 제목 → 견줄 열쇠(빈칸 · 괄호 기호 · 구두점을 뗀 글). 숫자는 둔다 — 「4-3. 연구개발성과의 기술기여도」(본문 절의 표)와 「[연구개발성과의 기술기여도]」(요약문의 표)는 다른 표다."""
    return _STRIP.sub("", title or "")


def _titled(S, k):
    """그 열쇠의 제목(소속 제목)을 가진 표 — 지금 문서에 있는 것."""
    return [t for t in S["tables"] if t["id"] in S["idx"] and key((t.get("owner") or {}).get("text")) == k]


def _hash(S, t):
    """원본 표의 지문(칸 배치 · 글) — 복사한 뒤 원본 표가 바뀌었는지."""
    b = S["idx"][t["id"]]
    cells = [[c["row"], c["col"], c.get("rowSpan") or 1, c.get("colSpan") or 1, c.get("text") or ""] for c in b.get("cells") or ()]
    return hashlib.sha256(json.dumps(cells, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def plan(T, F, titles, copied=None, skip=()):
    """넣기 계획(모듈 설명). titles = 통째로 복사할 표의 제목 목록(양식 정보 `copy`) · copied = 앞서 복사한 기록 · skip = 다른 스크립트가 먼저 맡은 목적 표 id(일정 표 — 그 표는 여기서 안 본다)."""
    copied = copied if isinstance(copied, dict) else {}
    items, own, seen = [], [], set()
    for title in titles or ():
        k = key(title)
        if not k or k in seen:
            continue
        seen.add(k)
        row = {"key": k, "title": P._ws(title)[:P.TEXT_MAX], "to": None, "from": None, "rows": 0, "cols": 0, "skip": None, "detail": ""}
        items.append(row)
        was = copied.get(k) if isinstance(copied.get(k), dict) else None
        fs = _titled(F, k)
        if was and was.get("to") in T["idx"]:   # 앞서 복사한 표가 지금 문서에 있다(실행 취소로 사라졌으면 처음부터 다시)
            same = len(fs) == 1 and fs[0]["id"] == was.get("from") and _hash(F, fs[0]) == was.get("hash")
            row.update(to=was["to"], **{"from": was.get("from")}, skip="applied" if same else "changed", detail="" if same else "복사한 뒤 원본 표가 바뀜 — 다시 넣지 않음")
            own.append(was["to"])
            continue
        ts = [t for t in _titled(T, k) if t["id"] not in skip]
        if not ts:   # 이 문서에 그 제목의 표가 없다(다른 판의 양식 · 표를 지움 · 다른 스크립트가 맡음) — 할 일 없음
            row.update(skip="noSource", detail="목적 문서에 그 제목의 표가 없음")
            continue
        if len(ts) > 1 or len(fs) > 1:
            row.update(skip="ambiguous", detail=f"그 제목의 표가 여럿(목적 {len(ts)} · 원본 {len(fs)}) — 어느 표인지 짐작하지 않음")
            own += [t["id"] for t in ts]   # 정해 둔 표 — 다른 길이 칸을 맞춰 넣지도 않는다(복사할 표에 반쯤 채운 값이 남는다)
            continue
        t = ts[0]
        own.append(t["id"])
        row["to"] = t["id"]
        if not fs:
            row.update(skip="noSource", detail="원본 문서에 그 제목의 표가 없음")
            continue
        f = fs[0]
        b = F["idx"][f["id"]]
        row.update(**{"from": f["id"]}, rows=b.get("nRows") or 0, cols=b.get("nCols") or 0, hash=_hash(F, f))
        if clash := X._ctx_clash(X._ctx(T, t), X._ctx(F, f)):
            row.update(skip=clash, detail="기관이 다른 표" if clash == "org" else "차년도가 다른 표")
            continue
        have = {P._ws(c.get("text") or "") for c in b.get("cells") or ()}
        mine = next((x for c in t["cells"] if c.get("role") == "field" and (x := P._ws(X._text(T, c["id"]))) and x not in have), None)
        if mine is not None:
            row.update(skip="occupied", detail=f"목적 표에 원본 표에 없는 글 「{mine[:30]}」 — 통째로 바꾸지 않음")
    todo = [r for r in items if r["skip"] is None]
    why = Counter(r["skip"] for r in items if r["skip"] in WHY)
    return {"items": items, "tables": own, "todo": len(todo),
            "counts": {"tables": len(todo), "applied": sum(r["skip"] == "applied" for r in items), "skipped": {k: why.get(k, 0) for k in WHY}}}


def apply(to_doc, from_doc, plan):
    """계획을 목적 문서에(모듈 설명) → {"copied", "records", "inserted", "skipped"}. 목적 표는 **지금** 문서에 있을 때만 바꾼다."""
    done, records, inserted, skipped = 0, {}, {}, []
    to_doc.blocks()   # 블록 id 는 읽을 때 붙는다(merge_tables.apply 와 같은 까닭)
    for it in (plan or {}).get("items") or ():
        if it.get("skip") is not None:
            continue
        if to_doc.table_block(it["to"]) is None:
            skipped.append({"to": it["to"], "why": "shape", "detail": "목적 표가 지금 문서에 없음"})
            continue
        try:
            new = to_doc.insert_after(it["to"], [{"kind": "copy", "srcId": it["from"]}], src=from_doc)
            to_doc.delete_blocks(it["to"], it["to"])
        except (KeyError, ValueError) as x:
            skipped.append({"to": it["to"], "why": "shape", "detail": str(x)})
            continue
        done += 1
        inserted[it["to"]] = list(new)
        records[it["key"]] = {"to": new[0], "from": it["from"], "hash": it.get("hash")}
    return {"copied": done, "records": records, "inserted": inserted, "skipped": skipped}
