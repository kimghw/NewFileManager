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
import bisect
from collections import Counter

from app import outline_edit as OE
from app import outline_match as OM

KINDS = ("form", "grown", "deep", "user", "cut")
KEEP = ("grown", "deep", "cut")   # 넣는 쪽의 서식을 받는 레벨(「긴 쪽을 받아서」) — 줄마다 본문 강조를 지킨다(모듈 설명)
BY = "retidy"   # 이 정리가 뗀 서식 종속 템플릿의 표(variant.by · 떼기 기록 splits[].by — outline_match.split)


GATHER_BODY = ("added", "filled")   # 취합의 본문 넣은 기록(= merge_gather.BODY — 표 칸 · 행 기록 cells · rows 의 ids 는 칸 id 라 넣은 줄이 아니다)


def record_ids(rec):
    """이관의 넣은 기록(merge.json)이 적은 넣은 블록 id — 항목마다의 넣은 블록(applied[].ids) · 넘친 줄 기록(applied[].over.lines) · 마지막 반영의 넣은 블록(filled.ids) · 통째로 복사한 표(copied[].to)
    · 마지막 반영이 글을 쓴 표 칸(filled.cells — 표 묶음 · 표 대응: 칸 안의 개요 줄 「1. 선내 데이터 …」 도 원본 모양 그대로 들어온다 · 2026-11-23)."""
    rec = rec or {}
    want = set()
    for v in (rec.get("applied") or {}).values():
        want.update(v.get("ids") or ())
        want.update(x.get("id") for x in ((v.get("over") or {}).get("lines") or ()) if x.get("id"))
    want.update((rec.get("filled") or {}).get("ids") or ())
    want.update((rec.get("filled") or {}).get("cells") or ())
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
    표 칸 · 행에 쓴 기록(cells · rows — 칸 id)은 아직 들지 않는다(이관은 2026-11-23 부터 글을 쓴 칸의 문단도 넣은 줄 — record_ids · 취합은 spec_병합 ④) · 끌어 넣기는 넣은 기록이 없어 들지 않는다."""
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
    """want 가운데 지금 문서에 있는 블록 id — 넣은 표 안의 칸 · 문단까지(넣은 표의 안은 모두 넣은 것) · 글을 쓴 칸(want 의 칸 id)의 문단까지(칸 id 자체는 안 든다 — 블록이 아니다)."""
    want, out = set(want or ()), set()

    def visit(b, inside):
        here = inside or b.get("id") in want
        if here and b.get("id"):
            out.add(b["id"])
        for c in b.get("cells") or ():
            for x in c.get("blocks") or ():
                visit(x, here or c.get("id") in want)
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


# ---- 넣은 줄의 레터 — 위 레벨과 같은 레터를 쓰지 않는다(spec_병합 ② §5-9 11 — 2026-11-22 사용자 「개요레벨이 크면 갖어오는데 동일한 헤딩레벨을 쓰지 않도록 주의해줘 ..
# 동일한 경우 다른 레터를 쓰도록 해줘. 문서에서 사용하는 레터지 □ · o · -, 점... 가장 긴 템플릿 개요를 참조해서」 → 레터가 모자라면 답 「기호를 더 씀」)
# 2026-11-23 사용자(「▪ 굵은 줄」 아래 「▪ 줄」 이 선 작성본을 보며) 「개요레터가 다른 레벨에서 같은걸 사용했네」 — 덧붙이는 기호는 **헤딩 판정의 내장 규칙이 읽고 계열이 서로 다른 글자**여야 한다:
# 전의 「◦」 는 판정이 「o」 계열로 읽어(닮은 레터 글자 — 「ㅇ」 아래 「◦」 = 같은 레터) 다음 누름이 또 바꿨고, 「▸」 는 내장 규칙이 못 읽는다(배운 규칙이 있는 PC 에서만 개요 줄).
# 「◆」 · 「▶」 = 2026-11-23 더함(「▪」 를 점과 같은 레터로 세면(look) 사슬에 점 레벨이 있는 문서에서 하나가 줄어, 깊이 넣은 내용(「[기관] › • › ◇ › ▷ › [소제목] › ∘ › ▸ › △ › …」)에서
# 바꿀 레터가 모자라 위 · 아래 레벨에 「△」 가 함께 섰다 — 속이 찬 기호는 헤딩 판정이 빈 기호와 다른 레터로 읽는다: outline_match.FILLED).
EXTRA = ("▪", "◇", "▷", "△", "◆", "▶")   # 가장 긴 템플릿 사슬의 기호 레터가 모자랄 때 이어 쓰는 기호(사용자 답 「기호를 더 씀」 — 고른 기호와 차례는 에이전트 판단: 사용자 확인 전)


def _sym(key):
    """기호 레터의 키인가(「□」 · 「o」 · 「-」 · 「·」 …) — 번호형(「N.」 · 「(A)」 · 「①」) · 괄호 라벨(「[기관]」) · 사용자 정의 글자(PUA) · 1칸 제목 상자 레벨(「▦」 — 레터가 아니다)은 아니다."""
    return isinstance(key, str) and len(key) == 1 and key != OE.BOX_KEY and not OE.is_numbered(key) and not ("" <= key <= "") and (not key.isalnum() or key == "o")


PASSES = 8   # reletter_of 가 레벨들의 레터를 다시 보는 횟수의 한도(보통 2번에 멎는다 — 서로 위 · 아래로 읽힌 레벨이 있으면 여기서 그친다)

# 눈으로 같은 레터(2026-11-23 사용자 — 넣은 「• (굵은 줄)」 아래 「▪」 줄을 보며 「이거 왜 아직 다른 레벨인데 동일한 레터를 쓰고 있냐」): 헤딩 판정의 계열(outline_match.kin)로는 다른 레터여도
# 본문 글자 크기에서 같은 「점」 으로 보이는 글자는 위 · 아래 레벨에 함께 세우지 않는다 — 속이 찬 작은 네모 「▪」(계열 「▫/찬」)는 점 「•」 · 「·」 · 「⋅」(계열 「·」)과 같은 레터로 센다.
# 이 셈은 **넣은 줄의 레터 바꾸기에서만**이다 — 헤딩 판정 · 닮은 레터 글자 · 서식 정리의 떼는 기준은 그대로(그 둘을 한 레벨의 같은 레터로 묶지 않는다). 묶은 글자는 에이전트 판단(사용자 확인 전).
DOTS = frozenset("·⋅•∙‧․")   # 키 없이 글자로 센 계열(outline_match.kin 의 키 없는 줄)도 점으로
LOOK = {"▫/찬": "·", "▪/찬": "·"}


def look(f):
    """레터 계열(outline_match.kin) → 눈으로 본 계열(LOOK · DOTS — 같은 점으로 보이는 계열을 「·」 하나로) · None 은 None."""
    if f is None:
        return None
    return "·" if f in DOTS else LOOK.get(f, f)


def _kin(x):
    return look(OM.kin(x.get("letter") or "", x.get("key"))) if x else None


def canon(glyph):
    """글자 → 헤딩 판정의 정규 레터 키(「▪」 → 「▫」 · 「•」 → 「·」 · 「◦」 → 「o」 — outline_grow.letter_key: 다시 분석한 그래프가 그 글자의 줄에 주는 키) · 내장 규칙이 못 읽는 글자는 그 글자."""
    from app import outline_grow as OG
    try:
        return OG.letter_key(glyph)
    except ValueError:
        return glyph


def pool(ov, ins=None):
    """바꿀 레터의 차례 — 문서에서 **가장 긴 템플릿 사슬**(기호 레터가 가장 많은 사슬 · 같으면 사슬이 길고 줄이 많은 것)의 기호 레터를 그 차례로 + EXTRA(계열이 겹치는 것은 한 번)
    → [(키, 글자, 계열)] — 글자 = 그 키로 문서에 가장 많이 친 글자(「o」 키 → 「ㅇ」 …) · 없으면 키 그대로 · EXTRA 의 키 = 그 글자의 정규 키(canon).
    계열 = **쓸 글자**의 계열(outline_match.kin(글자, 키) — 줄의 계열과 같은 셈: 키만으로 세면 「▫」 키의 글자 「▪」(속이 찬 기호 「▫/찬」)가 위 줄의 「▪」 와 다른 레터로 읽혀
    두 레벨에 같은 「▪」 가 섰다 — 2026-11-23 실제 작성본)을 눈으로 본 계열로(look — 사슬에 점 「·」 레벨이 있으면 EXTRA 의 「▪」 는 같은 점이라 차례에 다시 안 든다: 「• › ▪」 가 서지 않게).
    ins(넣은 줄 id)를 주면 **목적 문서의 것만** 센다 — 사슬은 넣은 줄 밖의 줄이 있는 템플릿, 글자는 넣은 줄 밖의 줄(없으면 전처럼 모두): 넣은 줄의 템플릿(지난 누름이 레터를 바꾼 서식 종속 템플릿 ·
    늘어난 레벨)이 가장 긴 사슬로 잡히면 두 번째 누름의 차례가 달라져(「o」 · 「-」 가 빠짐) 바꿀 레터를 못 찾았다(2026-11-23 실제 작성본 사본)."""
    ins = set(ins or ())
    own = {str(x.get("tpl")) for p, x in ov["lines"].items() if p not in ins} if ins else None
    best, score = (), None
    for tid, t in ov["templates"].items():
        if own and str(tid) not in own:
            continue
        chain = t.get("chain") or ()
        syms = [k for k in chain if _sym(k)]
        sc = (len(syms), len(chain), sum(1 for x in ov["lines"].values() if str(x.get("tpl")) == str(tid)))
        if score is None or sc > score:
            best, score = syms, sc
    glyphs, every = {}, {}
    for p, x in ov["lines"].items():
        if _sym(x.get("key")) and x.get("letter"):
            every.setdefault(x["key"], Counter())[x["letter"]] += 1
            if p not in ins:
                glyphs.setdefault(x["key"], Counter())[x["letter"]] += 1
    glyphs = {k: glyphs.get(k) or c for k, c in every.items()}
    cands = [(k, glyphs[k].most_common(1)[0][0] if glyphs.get(k) else k) for k in best] + [(canon(g), g) for g in EXTRA]
    out, seen = [], set()
    for k, g in cands:
        f = look(OM.kin(g, k))
        if f in seen:
            continue
        seen.add(f)
        out.append((k, g, f))
    return out


def _up(ov, pid):
    """줄 pid 의 위 줄들(부모 → 그 위 …) — 오버레이의 parent 사슬(템플릿을 건너도)."""
    out, seen, p = [], {pid}, (ov["lines"].get(pid) or {}).get("parent")
    while p and p in ov["lines"] and p not in seen:
        out.append(p)
        seen.add(p)
        p = ov["lines"][p].get("parent")
    return out


def reletter_of(doc, ov, ins, keep=()):
    """넣은 줄이 위 레벨과 같은 레터를 쓰는 레벨을 찾아 바꿀 레터를 정한다(오버레이 · 문서 안 바꿈) → [{tpl, no, level, was, key, now, lines[줄 id], why}].
    대상 = 넣는 쪽의 서식을 받는 레벨 가운데 그 레벨 줄이 **모두 넣은 줄**인 것(cut — 서식 종속 템플릿으로 뗀 레벨 · grown — 목적 문서에 없던 레벨)의 기호 레터.
    얕은 레벨부터: 그 레벨 줄들의 위 줄(넣을 자리와 그 위의 목적 문서 줄 · 이미 정한 위의 넣은 줄)의 레터 계열(kin)과 겹치면 pool 의 차례에서 처음 안 겹치는 레터로(now) —
    안 겹치면 그대로(목록에 안 든다) · pool 이 다 겹치면 그대로 두고 why. 사람이 처리를 고른 넘친 줄(keep)이 든 레벨은 건드리지 않는다(why).
    계열은 줄 · pool 모두 **글자와 정규 키**로 세고 눈으로 같은 점은 하나로 센다(look(outline_match.kin) — pool 의 셋째 값: 「•」 아래 「▪」 도 겹침) · 정한 뒤 위 레벨이 바뀌어 다시 겹친 레벨은 더 바뀌지 않을 때까지 다시 본다(PASSES) ·
    같은 레벨의 줄이 위 줄인 것은 견주지 않는다(두 번째 누름은 할 것 없음)."""
    ins, keep = set(ins), set(keep or ())
    rows = [r for r in plan(doc, ov, ins, keep)["rows"] if r["kind"] in ("cut", "grown") and not r["form"]]
    P, now = pool(ov, ins), {}   # now = 정한 줄 → 새 레터의 계열(아래 레벨이 위 줄로 읽는다) · 차례는 목적 문서의 사슬 · 글자로(pool 설명)
    # 위 줄 = 그래프의 부모 사슬 + **넣은 자리**(문서 차례로 그 줄 바로 앞의 목적 문서 줄)와 그 위 사슬 — 다시 분석한 그래프는 넣은 「o」 를 같은 레터인 양식의 「ㅇ (2차년도)」 와
    # 같은 레벨(형제 — 부모 「□」)로 읽어, 부모 사슬만으로는 실제로 넣은 자리 「- (추진 내용)」 · 「ㅇ」 가 위 줄로 안 잡혔다(2026-11-22 실제 작성본)
    order = OM._order(doc)
    form = sorted((order[p], p) for p in ov["lines"] if p not in ins and p in order)
    marks = [o for o, _ in form]

    def ups(p):
        i = bisect.bisect_left(marks, order.get(p, -1)) - 1
        at = form[i][1] if i >= 0 and p in order else None
        return list(dict.fromkeys(_up(ov, p) + ([at] + _up(ov, at) if at else [])))
    slots = []
    for r in rows:
        sl = OE._slot(ov, r["tpl"], r["level"]) or {}
        ids = [p for p in OM.slot_ids(ov, r["tpl"], r["level"]) if p in ov["lines"]]
        if not ids or not _sym(sl.get("key") or ov["lines"][ids[0]].get("key")):
            continue
        slots.append((min(len(ups(p)) for p in ids), r, sl, ids))
    slots.sort(key=lambda s: (s[0], _rank(ov, s[1]["tpl"]), s[1]["level"]))
    made = {}   # (템플릿, 레벨) → 그 레벨의 계획(처음 겹친 차례대로)
    # 더 바뀌지 않을 때까지 되풀이(PASSES 번까지) — 위 줄의 수로 잡은 차례는 위 · 아래를 꼭 맞히지 못해(위 줄 = 부모 사슬 + 넣은 자리의 사슬), 아래 레벨을 먼저 정한 뒤 위 레벨이 같은 레터로 바뀌면
    # 그 둘이 다시 겹쳤다(다음 누름이 또 바꿨다 — 2026-11-23 실제 작성본: 1L5a L5 「•」 를 정한 뒤 그 위의 T10 L5 가 「•」 로)
    for _ in range(PASSES):
        moved = False
        for _, r, sl, ids in slots:
            at = (r["tpl"], r["level"])
            row = made.get(at)
            if row is not None and row["why"]:   # 못 바꾼 레벨 — 다시 보지 않는다
                continue
            key = sl.get("key") or ov["lines"][ids[0]].get("key")
            mine = set(ids)
            cur = now[ids[0]] if row is not None else look(OM.kin(sl.get("letter") or key, key))
            # 같은 레벨의 줄이 위 줄로 잡힌 것(그래프가 같은 레벨 줄을 부모 · 자식으로 읽은 곳)은 견주지 않는다 — 레벨의 레터를 무엇으로 바꿔도 겹쳐 누를 때마다 다음 레터로 넘어갔다
            used = {now.get(a) or _kin(ov["lines"][a]) for p in ids for a in ups(p) if a not in mine} - {None}
            if cur not in used:
                continue
            if row is None:
                row = made[at] = {"tpl": r["tpl"], "no": r["no"], "level": r["level"], "was": sl.get("letter") or key, "key": None, "now": None, "lines": ids, "why": None}
                if any(p in keep for p in ids):
                    row["why"] = "사람이 넘친 레벨의 처리를 고른 줄이 있어 그대로 둠"
                    continue
            moved = True
            # 차례에서 위 줄이 쓴 **가장 깊은 레터 다음부터**(「- (정의)」 아래면 「⋅」 — 처음부터 고르면 위 줄에 안 쓰인 「□」 가 잡혀 「-」 아래에 「□」 가 섰다: 사슬의 차례가 거꾸로)
            start = max((i + 1 for i, (_, _, f) in enumerate(P) if f in used), default=0)
            # 그 뒤에 빈 레터가 없으면 차례 앞쪽의 빈 레터라도(위 레벨과 같은 레터로 두는 것보다 낫다 — 위 레벨을 바꾼 탓에 아래 레벨이 같은 레터로 남던 것: 2026-11-23 실제 작성본 사본 「△ › △」)
            pick = next((x for x in P[start:] if x[2] not in used), None) or next((x for x in P[:start] if x[2] not in used), None)
            if pick is None:
                row.update(key=None, now=None, why="위 레벨과 겹치지 않는 레터가 없어 그대로 둠")
                for p in ids:
                    now.pop(p, None)
                continue
            row["key"], row["now"] = pick[0], pick[1]
            now.update({p: pick[2] for p in ids})
        if not moved:
            break
    return list(made.values())


def reletter(doc, ov, rows, left=None):
    """reletter_of 의 계획을 건다(문서 · 오버레이 — 부른 쪽이 트랜잭션 안에서) → 바꾼 줄 id. 줄마다 제 모양 그대로 레터 글자만(outline_match.match_one — 레터 앞 · 뒤 빈칸 · 문단 · 글자 모양은 그 줄 것) ·
    오버레이의 줄 · 레벨 슬롯의 레터와 키 · 템플릿 사슬의 그 자리도 새 레터로. left = 짝 표지 때문에 모양만 맞춘 줄(match_one)."""
    changed = []
    for r in rows:
        if not r["now"]:
            continue
        for p in r["lines"]:
            if not OM._alive(doc, p) or OM._is_auto(ov, p):
                continue
            try:
                sh = OM.rep_shape(doc, ov, p)
            except (KeyError, ValueError):
                continue
            OM.match_one(doc, ov, p, {**sh, "tok": r["now"], "prefix": sh["lead"] + r["now"] + sh["gap"]}, left)
            ov["lines"][p]["key"] = r["key"]
            changed.append(p)
        sl = OE._slot(ov, r["tpl"], r["level"])
        if sl is not None:
            sl.update(key=r["key"], letter=r["now"], prefix=(sl.get("prefix") or "").replace(r["was"], r["now"], 1) if sl.get("prefix") else sl.get("prefix"))
        chain = (ov["templates"].get(str(r["tpl"])) or {}).get("chain")
        if isinstance(chain, list) and 0 < int(r["level"]) <= len(chain):
            chain[int(r["level"]) - 1] = r["key"]
    return changed


def letters_view(relet):
    """reletter_of 의 계획 → 화면 · 기록의 꼴 [{tpl, no, level, was, now, lines(줄 수), why}]."""
    return [{"tpl": r["tpl"], "no": r["no"], "level": r["level"], "was": r["was"], "now": r["now"], "lines": len(r["lines"]), "why": r["why"]} for r in relet or ()]


def summary(rows, cuts=(), left=(), held=(), relet=()):
    """계획의 수 {levels(넣은 줄이 든 레벨), grown(넣은 줄만 있는 레벨 — 템플릿이 늘어난 레벨), deep(떼지 못해 목적 문서의 줄은 그대로 두고 넣은 줄끼리 맞춘 레벨), lines(넣은 개요 줄),
    fix(맞출 넣은 줄), near(같이 맞출 목적 문서의 「≈」 줄), own(표의 서식으로 남긴 넣은 줄), cutLevels(이 정리가 뗀 서식 종속 템플릿의 레벨),
    cut(이번에 뗀 것 — cut_all 의 cuts 수), cutLines(이번에 옮긴 줄 — 자손 포함), held(사람이 처리를 고른 넘친 줄 — plan 의 held: 그대로 둔 줄)}. left(못 가른 레벨)는 deep 에 든다.
    held 를 안 주면 줄마다의 것을 센다(그 레벨의 넣은 줄이 모두 사람이 고른 줄이면 줄이 없어 안 든다 — plan()["held"] 를 주면 모두)."""
    held = set(held or ()) | {p for r in rows for p in r.get("held") or ()}
    return {"levels": len(rows), "grown": sum(1 for r in rows if r["kind"] == "grown"), "deep": sum(1 for r in rows if r["kind"] == "deep"), "lines": sum(r["lines"] for r in rows),
            "fix": sum(len(r["fix"]) for r in rows), "near": sum(len(r["near"]) for r in rows), "own": sum(len(r["own"]) for r in rows),
            "cutLevels": sum(1 for r in rows if r["kind"] == "cut"), "cut": len(cuts), "cutLines": sum(c["moved"] for c in cuts), "held": len(held),
            "letters": sum(1 for r in relet or () if r["now"]), "letterSwaps": [f"{r['was']} → {r['now']}" for r in relet or () if r["now"]],   # 위 레벨과 같은 레터를 바꾼 레벨 · 그 바꿈
            "lettersLeft": sum(1 for r in relet or () if not r["now"])}
