"""넣은 뒤 템플릿 · 서식 정리(spec_병합 ② §5-9) — 이관 · 취합으로 넣은 개요 줄을 목적 문서(연차보고서 · 취합본)의 템플릿 · 서식에 맞추는 계획. 스크립트만(LLM 없음) · 문서는 안 바꾼다(반영은 merge_retidy_api).

2026-11-22 사용자(넣은 줄의 서식이 들쭉날쭉한 연차보고서를 보며) "옮기고 나서 서식은 목적문서의 템플릿/서식을 따르되, 복사하고자 하는게 개요가 더 길면 긴쪽을 받아서 템플릿/서식이 재조정 했으면 좋겠어" ·
"정리된 서식이 와서 내용이랑 서식이 복사되던지 기존 넘어오는 곳에 변경하던지 해야 하는데".
넣을 때의 템플릿 변환(merge_convert)은 목적 템플릿에 받을 레벨이 있는 줄만 목적 문서의 줄(본보기) 모양으로 바꾼다 — 넣을 자리가 그 템플릿의 마지막 레벨이면(연차보고서 「[1차년도 개발내용]」 칸 ·
「- (추진 내용)」) 넣는 줄은 모두 넘친 레벨(넣을 자리보다 깊은 레벨 — 「긴 쪽」)이고 원본 모양 그대로 들어온다(그 원본 모양도 정리 전이다 — 이관은 원본을 바꾸지 않는다).
이 계획은 **넣은 뒤** 목적 문서를 다시 분석한 개요 오버레이 위에서 (템플릿, 레벨)마다 넣은 줄의 대표를 정한다:

- **목적 레벨을 받은 줄이 있는 레벨**(넣은 줄 가운데 그 레벨의 목적 문서 줄과 서식이 같은 줄이 있다 — 넣을 때 그 레벨로 바뀐 줄) → 대표 = 그 목적 문서의 줄, 다른 넣은 줄이 그 서식을 받는다
  ("목적문서의 템플릿/서식을 따르되") · 목적 문서의 줄 가운데 대표와 오차 안(「≈」)인 줄도 같이(kind "form").
- **그 밖의 레벨**(넣는 쪽 개요가 더 길다 — 넘친 레벨 · 받을 레벨 없이 들어온 줄): 넣은 줄끼리 가장 많은 서식으로("긴쪽을 받아서 … 재조정").
  목적 문서의 줄이 없는 레벨이면 그 줄이 레벨의 대표가 된다(kind "grown") · 목적 문서의 줄이 있으면 **그 줄과 레벨의 대표는 그대로** 두고 넣은 줄끼리만(kind "deep").
  다시 분석한 그래프는 레터가 같으면 넣을 자리 아래의 더 깊은 내용을 목적 문서의 같은 레터 줄과 같은 레벨로 읽는다(연차보고서 「- (추진 내용)」 아래 넣은 「□ · o · -」 = 양식의 굵은 소제목 「□ · ㅇ · -」 과 같은 레벨) —
  그 소제목의 모양(굵게)을 내용에 입히지 않는다(실제 작성본에서 그랬다: 2026-11-22).
  **반영 전에 그 레벨을 서식 종속 템플릿(「T10L2a」 — spec_hwpx_웹편집 ② §8-5)으로 가른다**(`cut_all` — 넣은 줄과 그 아래 넣은 줄을 새 템플릿으로 · 그 아래 매달린 목적 문서의 줄은 남김):
  같은 레벨에 남겨 두면 넣은 줄이 그 레벨의 「다른 서식」 이 되어 뒤의 「대표에 맞추기」 · 「템플릿 맞추기」 · 서식 정리 계획 · 「조정」 이 내용을 양식 소제목 모양으로(또는 소제목을 내용 모양으로) 바꾼다.
  가른 뒤의 그 템플릿 레벨은 kind "cut"(대표 고르기는 grown 과 같다). 못 가르는 레벨(번호형 레벨에서 형제의 일부 …)만 전처럼 deep.
  뗀 쪽은 템플릿에 남긴다(variant.side — 「ins」 넣은 줄 · 「form」 목적 문서의 줄): 넣은 줄을 뗀 템플릿만 그 줄 모두를 넣은 쪽으로 센다.
  deep 으로 맞춘 레벨은 그 슬롯에 표를 적는다(`mark` — outline_match.RETIDY_DEEP: 그때의 넣은 줄 · 그 대표) — 다음 누름에서 그 줄은 목적 레벨을 받은 줄로 다시 보지 않는다
  (지킨 강조로 양식 소제목과 서식이 같아진 줄 때문에 form 으로 바뀌어 내용이 소제목 모양이 되지 않게 — 두 번째 누름은 할 것 없음).
- **넣는 쪽의 서식을 받는 레벨(KEEP — grown · deep · cut)은 줄마다 본문 강조(굵게 · 기울임 · 밑줄)를 지킨다**(`outline_match.EMPH` · `own_emph`): 원본에서 굵은 소제목이던 넣은 줄이
  넣은 줄끼리의 대표(본문 보통)에 맞춰지며 굵기를 잃었다(한글 출력 실측 2026-11-22). 그 레벨의 서식 갈래 · 가장 많은 서식 · 맞출 줄도 강조만 다른 줄을 같은 서식으로 본다(`_alike` — 두 번째 누름은 할 것 없음).
  목적 문서의 서식을 따르는 레벨(form · user)은 전처럼 강조까지 대표 것.
- 사람이 정한 대표(repSet)는 그대로 둔다(kind "user").
- 맞출 줄 = 그 묶음의 넣은 줄 가운데 대표와 서식이 다른 줄 — **표의 서식**(그 표 양식에 대표 서식의 줄이 없음 — spec_hwpx_웹편집 ② §8-11)은 맞추지 않고 남긴다(own).

- **사람이 처리를 고른 넘친 사례의 줄은 맞추지 않는다**(held — 목적 작업 merge_over.json 의 cases 에 있는 사례의 넘친 줄: jobs/plan_merge.md · plan_to_report.md 「그 깊은 레벨을 … 사람이 고른다」).
- 취합(2026-11-22 — spec_병합 ② §5-9 9): 넣은 기록은 gather.json(`gather_ids`) · 「≈」 줄을 두지 않는다(near=False — 취합본에 있던 줄은 건드리지 않는다: 반영 쪽 merge_retidy_api 가 그 레벨을 확정 서식으로 다시 짓지 않는다).

- `record_ids(rec)` = 이관의 넣은 기록(merge.json — applied[].ids · 넘친 줄 기록 · filled.ids · 통째로 복사한 표)의 블록 id · `gather_ids(G)` = 취합의 넣은 기록(gather.json — 기관 문서마다 · 뺀 기관 문서의 본문 기록)의 블록 id ·
  `within(blocks, want)` = 그 가운데 지금 문서에 있는 것(넣은 표 안의 문단까지) · `inserted(blocks, rec)` = within(blocks, record_ids(rec)).
- `overs(rec, gather)` = 넣은 넘친 줄의 기록 · `held_ids(recs, cases)` = 사람이 처리를 고른 사례의 줄.
- `plan(doc, ov, ins, keep=(), near=True)` → {"rows": [{tpl, no, level, letter, kind, rep, slot(대표를 레벨의 대표로 삼나), lines(넣은 줄 수), fix[맞출 넣은 줄], near[같이 맞출 목적 문서의 「≈」 줄], own[표의 서식으로 남긴 줄],
  same[이미 대표 서식인 넣은 줄 — KEEP 레벨은 강조만 다른 줄도], form(그 레벨의 목적 문서 줄 수), held[그 레벨의 사람이 고른 넘친 줄 — 계획 밖]}], "tpls": [넣은 줄이 든 템플릿 id], "held": [모든 레벨의 사람이 고른 넘친 줄]}.
- `cut_all(doc, ov, ins, keep=())` = deep 레벨을 서식 종속 템플릿으로 가름(오버레이만 — `cut_of` 계획 · `cut` 반영) → (cuts, left).
- `mark(ov, rows)` = 반영한 계획의 deep 레벨에 표를 적음(오버레이만 — 반영과 같은 트랜잭션)."""
from collections import Counter

from app import outline_edit as OE
from app import outline_match as OM

KINDS = ("form", "grown", "deep", "user", "cut")
KEEP = ("grown", "deep", "cut")   # 넣는 쪽의 서식을 받는 레벨(「긴 쪽을 받아서」) — 줄마다 본문 강조를 지킨다(모듈 설명)
BY = "retidy"   # 이 정리가 뗀 서식 종속 템플릿의 표(variant.by · 떼기 기록 splits[].by — outline_match.split)


GATHER_BODY = ("added", "filled")   # 취합의 본문 넣은 기록(= merge_gather.BODY — 표 칸 · 행 기록 cells · rows 의 ids 는 칸 id 라 넣은 줄이 아니다)


def record_ids(rec):
    """이관의 넣은 기록(merge.json)이 적은 넣은 블록 id — 항목마다의 넣은 블록(applied[].ids) · 넘친 줄 기록(applied[].over.lines) · 마지막 반영의 넣은 블록(filled.ids) · 통째로 복사한 표(copied[].to)."""
    rec = rec or {}
    want = set()
    for v in (rec.get("applied") or {}).values():
        want.update(v.get("ids") or ())
        want.update(x.get("id") for x in ((v.get("over") or {}).get("lines") or ()) if x.get("id"))
    want.update((rec.get("filled") or {}).get("ids") or ())
    want.update(c.get("to") for c in (rec.get("copied") or {}).values() if isinstance(c, dict) and c.get("to"))
    return want


def _gather_applied(G):
    """취합의 넣은 기록(gather.json)의 값들 — 기관 문서마다(parts[].applied) + 뺀 기관 문서(gone[].applied — 넣은 내용은 취합본에 남는다)."""
    for grp in ((G or {}).get("parts"), (G or {}).get("gone")):
        for r in (grp.values() if isinstance(grp, dict) else ()):
            for v in ((r.get("applied") or {}).values() if isinstance(r, dict) and isinstance(r.get("applied"), dict) else ()):
                if isinstance(v, dict):
                    yield v


def gather_ids(G):
    """취합의 넣은 기록이 적은 넣은 블록 id — 본문 기록(kind added · filled)의 ids(새 최상위 블록) + 그 기록의 넘친 줄(convert.over.lines).
    표 칸 · 행에 쓴 기록(cells · rows — 칸 id)은 들지 않는다(이관도 칸 채움은 넣은 줄로 보지 않는다) · 끌어 넣기는 넣은 기록이 없어 들지 않는다."""
    want = set()
    for v in _gather_applied(G):
        if v.get("kind") in GATHER_BODY:
            want.update(i for i in v.get("ids") or () if i)
            want.update(x.get("id") for x in (((v.get("convert") or {}).get("over") or {}).get("lines") or ()) if isinstance(x, dict) and x.get("id"))
    return want


def overs(rec, gather=False):
    """넣은 넘친 줄의 기록 [{key, to, lines}] — 이관 = merge.json applied[].over · 취합(gather) = gather.json applied[].convert.over(뺀 기관 문서의 것도)."""
    if gather:
        return [o for o in (((v.get("convert") or {}).get("over")) for v in _gather_applied(rec)) if isinstance(o, dict)]
    return [v["over"] for v in ((rec or {}).get("applied") or {}).values() if isinstance(v, dict) and isinstance(v.get("over"), dict)]


def held_ids(recs, cases):
    """사람이 처리를 고른 넘친 사례의 줄 — 사례 열쇠가 목적 작업 merge_over.json 의 cases 에 있는 넘친 줄 기록의 lines[].id(모드가 무엇이든 — 「덮은 템플릿 그대로」 를 고른 것도).
    jobs/plan_merge.md · plan_to_report.md 「그 깊은 레벨을 … 사람이 고른다」 — 이 정리가 그 줄을 맞추지 않는다(plan 의 keep)."""
    cases = cases or {}
    return {x.get("id") for r in recs or () if isinstance(r, dict) and r.get("key") in cases for x in r.get("lines") or () if isinstance(x, dict) and x.get("id")}


def within(blocks, want):
    """want 가운데 지금 문서에 있는 블록 id — 넣은 표 안의 칸 · 문단까지(넣은 표의 안은 모두 넣은 것)."""
    want, out = set(want or ()), set()

    def visit(b, inside):
        here = inside or b.get("id") in want
        if here and b.get("id"):
            out.add(b["id"])
        for c in b.get("cells") or ():
            for x in c.get("blocks") or ():
                visit(x, here)
    for b in blocks or ():
        visit(b, False)
    return out


def inserted(blocks, rec):
    """넣은 블록 id(지금 문서에 있는 것 — 넣은 표 안의 칸 · 문단까지) — 이관의 넣은 기록(record_ids)에서."""
    return within(blocks, record_ids(rec))


def _looks(doc, ov, tid, lv):
    """(tid, lv) 줄의 비교 값 {줄 id: look} — 값 칸(표의 빈 값 「-」)은 서식 갈래에 안 넣는다."""
    out = {}
    for p in OM.slot_ids(ov, tid, lv):
        try:
            if OM._alive(doc, p) and not OM.lone_value(doc, ov, p):
                out[p] = OM.look(doc, ov, p)
        except (KeyError, ValueError):
            continue
    return out


def _rank(ov, tid):
    """템플릿의 차례 열쇠 — 번호 차례 · 서식 종속 템플릿(「1L2a」)은 원래 템플릿 바로 뒤((1, 2, "a")) · 종속 템플릿(「1T3」)처럼 번호가 정수가 아닌 것은 맨 뒤
    (전에는 int(no) 라 「1L2a」 에서 떨어졌다)."""
    t = ov["templates"].get(str(tid)) or {}
    v = t.get("variant") or {}
    if v.get("of") is not None and str(v["of"]) != str(tid):
        return (_rank(ov, v["of"])[0], int(v.get("level") or 0), str(v.get("sfx") or ""))
    try:
        return (int(t.get("no")), 0, "")
    except (TypeError, ValueError):
        return (1 << 30, 0, str(t.get("no")))


def _bare(lk):
    return {k: v for k, v in lk.items() if k not in OM.EMPH}


def _alike(a, b):
    """강조(본문 바탕 글자의 굵게 · 기울임 · 밑줄)만 다른 줄은 같은 서식 — KEEP 레벨의 견줌(그 강조는 줄마다 지킨다: 모듈 설명). 레터 글자의 강조(「L.bold」 …)는 견준다."""
    return OM.same(_bare(a), _bare(b))


def _groups(ids, looks, order, eq=None):
    """같은 서식(eq — 없으면 OM.same)끼리 → [[줄 id …] …] — 줄은 문서 차례 · 묶음은 줄 수가 많은 차례(같으면 먼저 나온 묶음)."""
    eq = eq or OM.same
    gs = []
    for p in sorted(ids, key=lambda q: order.get(q, 1 << 30)):
        for g in gs:
            if eq(looks[g[0]], looks[p]):
                g.append(p)
                break
        else:
            gs.append([p])
    return sorted(gs, key=lambda g: (-len(g), order.get(g[0], 1 << 30)))


def _ok(doc, ov, pid):
    """대표가 될 수 있는 줄인가(자동 글머리 줄 · 첫머리에 레터가 없는 줄은 못 된다 — outline_match.set_rep 과 같은 조건)."""
    if OM._is_auto(ov, pid):
        return False
    try:
        OM.rep_shape(doc, ov, pid)
    except (KeyError, ValueError):
        return False
    return True


def _pick(doc, ov, cands, looks, order, cur, eq=None):
    """가장 많은 서식의 줄 — 지금 대표가 그 서식이면 그 줄, 아니면 그 서식의 첫 줄(대표가 못 되는 줄은 건너뛰고 다음 서식으로). 없으면 None. eq = 같은 서식의 견줌(_groups).
    eq 를 주면(강조만 다른 줄을 같이 센 묶음 — _alike) 새로 고를 때 그 묶음에서 가장 많은 강조의 줄을 먼저(굵은 소제목이 앞에 있어도 내용의 모양이 대표 — Enter 로 만든 새 줄이 그 모양을 받는다).
    지금 대표가 그 묶음이면 그대로다(두 번째 누름이 대표를 옮기지 않게)."""
    for g in _groups(cands, looks, order, eq):
        if cur in g and _ok(doc, ov, cur):
            return cur
        if eq is not None:
            emph = Counter(tuple(looks[p].get(k) for k in OM.EMPH) for p in g)
            g = sorted(g, key=lambda p: -emph[tuple(looks[p].get(k) for k in OM.EMPH)])   # 안정 정렬 — 같은 강조끼리는 문서 차례
        for p in g:
            if _ok(doc, ov, p):
                return p
    return None


def _form_rep(doc, ov, mine, form, looks, order, cur):
    """넣은 줄 가운데 목적 문서의 줄과 서식이 같은 줄이 있으면(넣을 때 그 레벨을 받은 줄) 그 서식의 목적 문서 줄 — 지금 대표가 그 서식이면 그 줄. 여럿이면 넣은 줄이 많이 쓴 서식. 없으면 None."""
    for g in _groups(mine, looks, order):
        hit = [p for p in sorted(form, key=lambda q: order.get(q, 1 << 30)) if OM.same(looks[p], looks[g[0]])]
        if cur in hit and _ok(doc, ov, cur):
            return cur
        for p in hit:
            if _ok(doc, ov, p):
                return p
    return None


def plan(doc, ov, ins, keep=(), near=True):
    """넣은 줄 ins 가 든 (템플릿, 레벨)마다 대표 · 맞출 줄(모듈 설명). 오버레이 · 문서는 안 바꾼다.
    keep = 사람이 처리를 고른 넘친 사례의 줄(held_ids) — 맞추지 않고 대표 후보도 아니다(그 레벨의 줄 수 · 목적 문서의 줄 수에도 안 든다: row["held"]) ·
    near = 목적 문서의 「≈」 줄을 같이 맞추나(취합은 거짓 — 취합본에 있던 줄은 건드리지 않는다: 뒤에 올 기관 문서가 그 줄의 글로 자리를 찾는다)."""
    ins, keep = set(ins), set(keep or ())
    order = OM._order(doc)
    by = {}
    for pid in ins:
        x = ov["lines"].get(pid)
        if not x or not x.get("tpl") or x.get("role") in OE.ROOTED or x.get("role") == OE.TABLE:
            continue
        by.setdefault((str(x["tpl"]), int(x["level"])), []).append(pid)
    rows, tpls, tol, held = [], [], None, []
    for (tid, lv), _mine in sorted(by.items(), key=lambda kv: (_rank(ov, kv[0][0]), kv[0][1])):
        sl = OE._slot(ov, tid, lv)
        if sl is None:
            continue
        var = ov["templates"].get(tid, {}).get("variant") or {}
        vby = var.get("by")
        looks = _looks(doc, ov, tid, lv)
        here = sorted((p for p in looks if p in keep and p in ins), key=lambda q: order.get(q, 1 << 30))
        held += here
        looks = {p: v for p, v in looks.items() if p not in keep or p not in ins}   # 사람이 고른 넘친 줄은 이 계획 밖(넣은 줄인 것만 — 목적 문서의 줄은 기록에 없다)
        # 이 정리가 넣은 줄을 뗀 서식 종속 템플릿(넣은 내용의 템플릿)은 그 줄 모두가 넣은 쪽이다 — 뗀 뒤 Enter 로 만든 줄도(두 번째 누름이 대표를 옮기지 않게).
        # 목적 문서의 줄을 뗀 것(side form)은 아니다 — 거기 든 넣은 줄만(양식 줄을 넣은 줄의 서식으로 바꾸지 않게)
        mine = [p for p in looks if p in ins or (vby == BY and var.get("side") != "form")]
        if not mine:
            continue
        if tid not in tpls:
            tpls.append(tid)
        form = [p for p in looks if p not in mine]
        cur = sl.get("rep") if sl.get("rep") in looks else None
        if cur is not None and OM.rep_origin(sl) == "user":
            rep, kind = cur, "user"
        else:
            # 지난 정리가 넣은 줄끼리 맞추기로 정한 줄(mark)은 목적 레벨을 받은 줄로 다시 보지 않는다 — 그 줄에 지킨 강조(굵게 …)로 양식 소제목과 서식이 같아져도
            # 두 번째 누름이 그 레벨을 form 으로 바꿔 내용을 소제목 모양으로 바꾸지 않게. 그 뒤에 넣은 줄(다른 반영)은 전처럼 본다
            dz = sl.get(OM.RETIDY_DEEP) or {}
            seen = set(dz.get("lines") or ()) if form else set()
            rep, kind = _form_rep(doc, ov, [p for p in mine if p not in seen], form, looks, order, cur), "form"
            if rep is None:   # 목적 레벨을 받은 넣은 줄이 없다 — 넣은 줄끼리(긴 쪽 · 강조만 다른 줄은 같은 서식) · 지난 정리의 넣은 줄 대표가 그 서식이면 그 줄
                own = dz.get("rep") if form and dz.get("rep") in mine else cur
                rep, kind = _pick(doc, ov, mine, looks, order, own, _alike), ("deep" if form else "grown")
            if kind == "grown" and vby == BY:   # 이 정리가 뗀 서식 종속 템플릿의 레벨(넣을 자리보다 깊은 내용 — cut_all) — 대표 고르기는 grown 과 같다
                kind = "cut"
        t = ov["templates"].get(tid) or {}
        row = {"tpl": tid, "no": t.get("no"), "level": lv, "letter": sl.get("letter") or "", "kind": kind, "rep": rep, "slot": kind != "deep",
               "lines": len(mine), "form": len(form), "fix": [], "near": [], "own": [], "same": [], "held": here}
        rows.append(row)
        if rep is None:
            continue
        base = looks[rep]
        eq = _alike if kind in KEEP else OM.same
        # 표 양식(② §8-11): 대표 서식의 줄이 있는 표 양식 — 「deep」 은 넣은 줄끼리 맞추므로 넣은 줄만으로 센다(목적 문서의 소제목이 있는 표라고 내용을 그 서식으로 보지 않게)
        forms = {lk["form"] for lk in (looks[p] for p in (mine if kind == "deep" else looks)) if lk.get("form") and eq(lk, base)}   # = OM.rep_forms(eq 로)
        for p in sorted(mine, key=lambda q: order.get(q, 1 << 30)):
            if p == rep or eq(looks[p], base):
                row["same"].append(p)
            elif OM.is_own(looks[p], base, forms):
                row["own"].append(p)
            else:
                row["fix"].append(p)
        if near and kind in ("form", "user") and rep not in ins:
            # 목적 문서의 줄이 대표 — 그 레벨의 목적 문서 줄 가운데 대표와 오차 안(「≈」 — outline_match.near)인 줄도 같이: 대표에 확정 서식(묶음 빈칸 · 자리 규칙)을 걸면 그 줄만 「≠」 로 벌어진다
            # (실제 연차보고서 T1 L3 에서 그랬다). 오차 밖인 목적 문서의 줄(사람이 「그대로」 둔 다른 서식일 수 있다)은 건드리지 않는다
            tol = tol or OM._tolerance()
            row["near"] = [p for p in sorted(form, key=lambda q: order.get(q, 1 << 30))
                           if p != rep and not OM.same(looks[p], base) and not OM.is_own(looks[p], base, forms) and OM.near(base, looks[p], tol)]
    return {"rows": rows, "tpls": tpls, "held": held}


def _host_form(ov, tid, lv, ins):
    """(tid, lv) 가 목적 문서의 템플릿 자리인가 — 그 템플릿의 첫 레벨이거나, 더 얕은 레벨에 목적 문서의 줄이 있으면 참(넣은 줄을 뗀다).
    더 얕은 레벨의 줄이 모두 넣은 줄이면(다시 분석한 그래프가 넣은 줄로 만든 템플릿에 목적 문서의 줄이 매달림) 거짓 — 목적 문서의 줄을 뗀다."""
    base = OM._base(ov["templates"][str(tid)])
    up = [p for p, x in ov["lines"].items() if x["tpl"] == str(tid) and base < int(x["level"]) < int(lv)]
    return not up or any(p not in ins for p in up)


def cut_of(doc, ov, ins, tid, lv, order=None, keep=()):
    """deep 레벨 (tid, lv) 를 서식 종속 템플릿으로 가를 계획(오버레이 · 문서 안 바꿈) → {tpl, level, side, paras, rep, stay, stop, moved, into, why}.
    side = "ins"(넣은 줄을 뗀다 — 보통) | "form"(목적 문서의 줄을 뗀다 — _host_form 이 거짓) · paras = 뗄 그 레벨 줄(자동 글머리 줄 빼고) · rep = 새 템플릿의 대표(뗄 줄의 가장 많은 서식 — 강조만 다른 줄은 같은 서식) ·
    stay = 남는 쪽에서 새로 대표가 될 줄(지금 대표가 떠날 때) · stop = 뗄 줄 아래에 매달린 남는 쪽 줄(데려가지 않음 — 그 아래도) · moved = 옮길 줄 수(자손 포함) ·
    into = 같은 (tid, lv) 에서 이 정리가 전에 뗀 템플릿(거기에 더 넣는다) · why = 못 가르는 까닭(번호형 레벨의 형제 일부 · 대표가 될 줄 없음 …) | None.
    keep = 사람이 처리를 고른 넘친 줄(plan 의 keep) — 같이 옮기되(오버레이만 — 문서는 안 바뀜) 새 템플릿의 대표로는 고르지 않는다(그 줄뿐이면 그 줄)."""
    tid, lv, ins = str(tid), int(lv), set(ins)
    order = order or OM._order(doc)
    looks = _looks(doc, ov, tid, lv)
    host = _host_form(ov, tid, lv, ins)

    def on(p):   # 떼는 쪽의 줄인가
        return (p in ins) == host
    paras = [p for p in sorted(looks, key=lambda q: order.get(q, 1 << 30)) if on(p) and not OM._is_auto(ov, p)]
    rest = [p for p in looks if not on(p)]
    out = {"tpl": tid, "level": lv, "side": "ins" if host else "form", "paras": paras, "rep": None, "stay": None, "stop": [], "moved": 0, "into": None, "why": None}
    if not paras:
        out["why"] = "뗄 줄이 없습니다"
        return out
    cur = (OE._slot(ov, tid, lv) or {}).get("rep")
    if cur not in rest:   # 남는 쪽의 대표 — 목적 문서의 줄이면 그 서식 그대로(OM.same) · 넣은 줄이면(side form) 넣은 줄끼리의 견줌(_alike)
        out["stay"] = _pick(doc, ov, rest, looks, order, None, OM.same if host else _alike)
        if out["stay"] is None:
            out["why"] = "남는 줄 가운데 레벨의 대표가 될 줄이 없습니다"
            return out
    free = [p for p in paras if p not in set(keep or ())]   # 사람이 고른 넘친 줄은 대표 후보가 아니다 — 그 줄뿐이면 그 줄 가운데서
    out["rep"] = (_pick(doc, ov, free, looks, order, None, _alike) if free else None) or _pick(doc, ov, paras, looks, order, None, _alike)
    if out["rep"] is None:
        out["why"] = "뗄 줄 가운데 대표가 될 줄이 없습니다"
        return out
    out["why"] = OM.split_block(ov, tid, lv, paras, rep=out["stay"] or cur, doc=doc)
    if out["why"]:
        return out
    got, stop, changed = set(paras), set(), True
    while changed:   # 떼는 쪽의 줄로만 내려간다(outline_match._members 와 같은 걸음 — 남는 쪽 줄에서 멈춘다)
        changed = False
        for p, x in ov["lines"].items():
            if p in got or p in stop or x["tpl"] != tid or x.get("parent") not in got:
                continue
            (got if on(p) else stop).add(p)
            changed = True
    out["stop"], out["moved"] = sorted(stop), len(got)
    out["into"] = next((c for c, t in ov["templates"].items() if (t.get("variant") or {}).get("by") == BY and str(t["variant"].get("of")) == tid
                        and int(t["variant"].get("level") or 0) == lv and (t["variant"].get("side") or "ins") == out["side"]), None)   # 같은 쪽을 뗀 것에만(넣은 줄 · 양식 줄을 한 템플릿에 섞지 않게)
    return out


def cut(doc, ov, c):
    """cut_of 의 계획 c 를 오버레이에 건다(문서는 안 바꿈 — 부른 쪽이 트랜잭션 안에서) → outline_match.split 의 답.
    남는 쪽의 대표(stay) · 떼기가 데려간 더 깊은 레벨의 대표는 남은 줄의 가장 많은 서식으로 다시 정한다(by="agent" — 동결 모양도: split 은 동결 모양을 그대로 둔다)."""
    tid, lv = c["tpl"], c["level"]
    before = {int(k): s.get("rep") for k, s in ov["templates"][tid]["slots"].items()}
    if c["stay"]:
        OM.set_rep(doc, ov, tid, lv, c["stay"], by="agent")
    shape = OM.rep_shape(doc, ov, c["rep"]) if c["into"] is None else None
    got = OM.split(ov, tid, lv, c["paras"], rep=c["rep"], shape=shape, into=c["into"], stop=c["stop"], by=BY, side=c["side"], doc=doc)
    gone, order = set(got["moved"]), OM._order(doc)
    for k, r in before.items():
        if k == lv or r not in gone:
            continue
        looks = _looks(doc, ov, tid, k)
        p = _pick(doc, ov, list(looks), looks, order, None)
        if p is not None:
            OM.set_rep(doc, ov, tid, k, p, by="agent")
    return got


def cut_all(doc, ov, ins, keep=()):
    """deep 레벨마다 cut(오버레이를 바꾼다 — 미리보기는 사본에) → (cuts[{tpl, no, level, side, id, name, new, lines, moved, stop}], left[{tpl, no, level, why}]).
    템플릿 · 레벨 차례(얕은 레벨부터) 하나씩 — 뗀 줄의 자손(넣은 줄)이 같이 가므로 매번 다시 계획한다. 못 가른 레벨(left)은 전처럼 넣은 줄끼리 맞춘다(deep). keep = plan 의 keep."""
    cuts, left, tried, order = [], [], set(), OM._order(doc)
    while True:
        r = next((x for x in plan(doc, ov, ins, keep)["rows"] if x["kind"] == "deep" and (x["tpl"], x["level"]) not in tried), None)
        if r is None:
            return cuts, left
        tried.add((r["tpl"], r["level"]))
        c = cut_of(doc, ov, ins, r["tpl"], r["level"], order, keep)
        if c["why"]:
            left.append({"tpl": r["tpl"], "no": r["no"], "level": r["level"], "why": c["why"]})
            continue
        got = cut(doc, ov, c)
        cuts.append({"tpl": c["tpl"], "no": r["no"], "level": c["level"], "side": c["side"], "id": got["id"], "name": got["no"], "new": got["new"],
                     "lines": len(c["paras"]), "moved": len(got["moved"]), "stop": len(c["stop"])})


def mark(ov, rows):
    """deep 묶음(못 가른 레벨 — 넣은 줄끼리 맞춤)마다 그 레벨 슬롯에 표를 적는다(오버레이만 — 반영과 같은 트랜잭션) → 적은 레벨 수.
    표 = {rep(넣은 줄의 대표), lines[그 레벨의 넣은 줄 — 전에 적은 것과 합침]}(outline_match.RETIDY_DEEP): 다음 누름의 plan 이 그 줄을 목적 레벨을 받은 줄로 다시 보지 않고 그 대표를 그대로 둔다."""
    n = 0
    for r in rows:
        sl = OE._slot(ov, r["tpl"], r["level"]) if r["kind"] == "deep" and r["rep"] is not None else None
        if sl is None:
            continue
        was = set((sl.get(OM.RETIDY_DEEP) or {}).get("lines") or ())
        sl[OM.RETIDY_DEEP] = {"rep": r["rep"], "lines": sorted(was | set(r["same"]) | set(r["fix"]) | set(r["own"]))}
        n += 1
    return n


def summary(rows, cuts=(), left=(), held=()):
    """계획의 수 {levels(넣은 줄이 든 레벨), grown(넣은 줄만 있는 레벨 — 템플릿이 늘어난 레벨), deep(떼지 못해 목적 문서의 줄은 그대로 두고 넣은 줄끼리 맞춘 레벨), lines(넣은 개요 줄),
    fix(맞출 넣은 줄), near(같이 맞출 목적 문서의 「≈」 줄), own(표의 서식으로 남긴 넣은 줄), cutLevels(이 정리가 뗀 서식 종속 템플릿의 레벨),
    cut(이번에 뗀 것 — cut_all 의 cuts 수), cutLines(이번에 옮긴 줄 — 자손 포함), held(사람이 처리를 고른 넘친 줄 — plan 의 held: 그대로 둔 줄)}. left(못 가른 레벨)는 deep 에 든다.
    held 를 안 주면 줄마다의 것을 센다(그 레벨의 넣은 줄이 모두 사람이 고른 줄이면 줄이 없어 안 든다 — plan()["held"] 를 주면 모두)."""
    held = set(held or ()) | {p for r in rows for p in r.get("held") or ()}
    return {"levels": len(rows), "grown": sum(1 for r in rows if r["kind"] == "grown"), "deep": sum(1 for r in rows if r["kind"] == "deep"), "lines": sum(r["lines"] for r in rows),
            "fix": sum(len(r["fix"]) for r in rows), "near": sum(len(r["near"]) for r in rows), "own": sum(len(r["own"]) for r in rows),
            "cutLevels": sum(1 for r in rows if r["kind"] == "cut"), "cut": len(cuts), "cutLines": sum(c["moved"] for c in cuts), "held": len(held)}
