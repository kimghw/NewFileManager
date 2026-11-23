"""줄 정리 끝점(spec/spec_줄정리.md ② §5 · §6) — 계산은 `app/line_tidy.py`, 한글 조판은 `pdf_render.layout_hwpx`. hwpx 문서만 · 어느 워크플로우의 문서에서나.

- 규칙(이 PC 의 모든 문서 · 워크플로우가 같이 씀): `GET /api/line-tidy/rules` → {rules, defs, defaults, updated} · `PUT …` {rules} → 저장 · `DELETE …` → 기본값으로.
  저장 `%LOCALAPPDATA%\\NewFileManager\\line_tidy.json`(env `NFM_LINE_TIDY` = 파일 경로 · `off`·`0` 이면 메모리만 — 시험 · 화면 검사는 임시 파일).
- `GET /api/docs/{id}/line-tidy` → 저장한 것(마지막 계획 · 마지막 반영)과 상태의 재료. 문서 안 바뀜 · 한글 안 부름.
- `POST …/line-tidy/plan` → 지금 문서를 떠서(세션 잠금 안 — 바이트 · rev) **잠금 밖에서** 한글로 조판해 줄을 읽고, 규칙에 걸린 자리마다 장평을 어림해 고친 사본을 다시 조판해 맞았는지 본다
  (맞지 않으면 1%씩 더 — 규칙 「한글로 다시 재기」 번까지). 문단은 서로의 줄 나눔에 닿지 않아 모든 문단을 한 번에 고쳐 한 번에 잰다 → {planId, rev, items, left, counts, seconds}. 문서 안 바뀜.
  이어서 **쪽에 걸친 줄**(② §8 — 규칙 `pageTail` 이 0 이 아니면): 장평을 입힌 사본에서 다음 쪽으로 넘어간 줄이 규칙 이하인 문단마다 그 쪽의 빈 줄 높이를 낮춰 다시 잰다(`_page_pass`) → pages · pageLeft · blanks.
- `POST …/line-tidy/apply {planId}` → 그 계획의 장평과 빈 줄 높이를 한 번에(구조 편집 트랜잭션 하나 — 실행 취소 1 · 기록 `lineTidy`). 계획을 잰 뒤 문서가 바뀌었으면 409(다시 잰다).
  고칠 것이 없어도 반영 기록은 남긴다(확인은 끝남).
- 저장 = 작업 폴더 `linetidy.json` {version, plan{planId, at, rev, rules, items[{id, text, ops[{kind, rs, re, pct}], before[], after[]}], left[…], counts, seconds,
  pages[{id, text, tail, blanks[{id, pct}]}], pageLeft[{id, text, tail, why}], blanks[{id, pct}], pageRounds} | None,
  applied{at, planId, rev, fill(그때의 「내용 넣기」 반영 표식 | None), paras, ops, pages, blanks, counts} | None}."""
import copy
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from app import line_tidy as LT
from app import works

router = APIRouter()
log = logging.getLogger("uvicorn.error")
FILE = "linetidy.json"
VERSION = 1
NO_HWP = "한글(한컴오피스)이 없어 한글의 줄 나눔을 잴 수 없습니다"

# ---------------------------------------------------------------- 규칙 저장(tool_names.py 와 같은 꼴 — 가벼움)
_LOCK = threading.RLock()
_MEMORY = {"rules": {}, "updated": None}


def rules_path():
    env = os.environ.get("NFM_LINE_TIDY", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "line_tidy.json"


def _read():
    p = rules_path()
    if p is None:
        return dict(_MEMORY)
    try:
        got = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rules": {}, "updated": None}
    return got if isinstance(got, dict) else {"rules": {}, "updated": None}


def rules():
    """지금 규칙(모든 키) — 저장한 것 위에 기본값."""
    with _LOCK:
        return LT.rules_of(_read().get("rules"))


def _write(data):
    p = rules_path()
    if p is None:
        _MEMORY.clear()
        _MEMORY.update(data)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".line_tidy.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _rules_out():
    with _LOCK:
        d = _read()
    return {"rules": LT.rules_of(d.get("rules")), "defaults": dict(LT.DEFAULTS), "defs": [dict(x) for x in LT.RULE_DEFS], "updated": d.get("updated"),
            "text": LT.rules_text(LT.rules_of(d.get("rules")))}


@router.get("/api/line-tidy/rules")
def rules_get():
    """줄 정리 규칙 {rules, defaults, defs[{key, default, lo, hi, unit, name, text}], updated, text(한 줄 요약)}."""
    return _rules_out()


@router.put("/api/line-tidy/rules")
def rules_put(body: dict = Body(...)):
    """{rules: {키: 정수}} — 준 키만 바꾸고 나머지는 지금 값. 범위 밖 · 모르는 키는 400(그 규칙의 이름으로)."""
    want = body.get("rules") if isinstance(body, dict) else None
    if not isinstance(want, dict):
        raise HTTPException(400, "rules 가 필요합니다")
    with _LOCK:
        try:
            got = LT.clean_rules({**rules(), **want})
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        _write({"rules": {k: v for k, v in got.items() if v != LT.DEFAULTS[k]}, "updated": time.time()})
    return _rules_out()


@router.delete("/api/line-tidy/rules")
def rules_reset():
    """규칙을 모두 기본값으로."""
    with _LOCK:
        _write({"rules": {}, "updated": time.time()})
    return _rules_out()


# ---------------------------------------------------------------- 작업 폴더의 기록
def _path(wid):
    f = works.folder(wid)
    return f / FILE if f is not None and (f / "work.json").is_file() else None


def load(wid):
    p = _path(wid)
    got = works._read_json(p) if p is not None and p.is_file() else None
    return got if isinstance(got, dict) and got.get("version") == VERSION else {"version": VERSION, "plan": None, "applied": None}


def _save(wid, data):
    p = _path(wid)
    if p is not None:
        works._write_json(p, data)


def _fill_at(wid):
    from app import guide_fix_api
    return guide_fix_api._fill_at(wid)


def _hwp_ok():
    """이 PC 에 한글(COM)이 있나 — 줄 정리만의 문(시험은 이것만 바꾼다: pdf_render.available 을 바꾸면 서버의 다른 길(검증 PDF)이 진짜 한글을 띄운다)."""
    from app import pdf_render
    return pdf_render.available("hwpx")


def _layout(data):
    """한글이 끝 쪽까지 조판한 바이트(pdf_render.layout_hwpx) — 줄 정리만의 문(시험은 가짜 조판으로 바꾼다)."""
    from app import pdf_render
    return pdf_render.layout_hwpx(data)


def _why(s):
    if s.fmt != "hwpx":
        return "HWPX 문서가 아닙니다"
    if not _hwp_ok():
        return NO_HWP
    return ""


def facts(doc_id):
    """워크플로우 상태의 재료 → {why, plan{at, rev, paras, ops, left} | None, applied{at, rev, fill, paras, ops, counts} | None, fill, rules, rulesText}. 문서 안 바뀜 · 한글 안 부름."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        why, rev = _why(s), s.rev
    rec = load(doc_id)
    p, a = rec.get("plan"), rec.get("applied")
    R = rules()
    return {"why": why, "rev": rev, "fill": _fill_at(doc_id), "rules": R, "rulesText": LT.rules_text(R),
            "plan": {"at": p.get("at"), "rev": p.get("rev"), "planId": p.get("planId"), "paras": len(p.get("items") or ()), "counts": p.get("counts") or {}} if p else None,
            "applied": {k: a.get(k) for k in ("at", "rev", "fill", "paras", "ops", "counts")} if a else None}


# ---------------------------------------------------------------- 재기 · 고치기(잠금 밖 — 뜬 바이트만 쓴다)
P_TAG = "{http://www.hancom.co.kr/hwpml/2011/paragraph}p"
TC_TAG = "{http://www.hancom.co.kr/hwpml/2011/paragraph}tc"


def _in_cell(p):
    """표 칸 안의 문단인가(② §2 `cellWord` — 표 칸의 짧은 낱말)."""
    return any(a.tag == TC_TAG for a in p.iterancestors())


def _paras(doc):
    """문서의 모든 문단(구역 차례 · 문서 차례 — 표 칸 · 캡션 안 문단까지). 한글이 다시 저장해도 같은 차례다(2026-11-23 실측 6549 = 6549)."""
    return [p for sec in doc._sections for p in sec.iter(P_TAG)]


class LayoutMismatch(Exception):
    """한글이 조판한 사본의 문단이 문서와 맞지 않음."""


def _hu(v):
    """lineseg 의 값(HWPUNIT) — 한글은 음수를 부호 없는 32비트로 쓰기도 한다."""
    try:
        n = int(v or 0)
    except ValueError:
        return 0
    return n - (1 << 32) if n >= 1 << 31 else n


def _laid(laid_bytes, texts):
    """한글이 조판한 바이트 → (문단 차례마다 줄 시작 자리(둘째 줄부터) | None(글이 다름 · 캐시 없음), 문단 차례마다 줄 자리 [(vertpos, vertsize, spacing)…] — 쪽 나눔을 읽는 재료: ② §8)."""
    from app import hwpx_layout
    from app.hwpx_doc import HwpxDoc
    L = HwpxDoc(laid_bytes)
    lps = _paras(L)
    if len(lps) != len(texts):
        raise LayoutMismatch(f"한글이 조판한 사본의 문단 수가 다릅니다({len(lps)} ≠ {len(texts)})")
    seg = f"{hwpx_layout.HP}linesegarray/{hwpx_layout.HP}lineseg"
    breaks, segs = [], []
    for lp, t in zip(lps, texts):
        segs.append([(_hu(x.get("vertpos")), _hu(x.get("vertsize")), _hu(x.get("spacing"))) for x in lp.findall(seg)])
        breaks.append(None if t is None or L._text(lp) != t else hwpx_layout.lines(L, lp, t))
    return breaks, segs


def _laid_breaks(laid_bytes, texts):
    """한글이 조판한 바이트 → 문단 차례마다 줄 시작 자리(둘째 줄부터) | None(글이 다름 · 캐시 없음)."""
    return _laid(laid_bytes, texts)[0]


def _page_pass(clone, ps, texts, pick, R, segs, lay, progress=None):
    """쪽에 걸친 줄(② §8) — 장평 걸음이 끝난 사본에서: 걸린 문단마다 그 쪽의 빈 줄 높이를 낮춰 보고(LT.Pages) 한글로 다시 잰다. segs = 지금 사본의 줄 자리 · lay() → 사본을 다시 잰 줄 자리.
    → (고친 문단 [{idx, tail, blanks}], 그대로 둔 문단 [{idx, tail, why}], 바꾼 빈 줄 [{idx, pct}], 처음에 걸려 있던 수, 다시 잰 횟수). 사본은 마지막으로 잰 꼴로 남는다."""
    from app.hwpx_doc import RUN
    by = {}
    for i, p in enumerate(ps):   # 흐름 = 같은 부모(구역 본문 · 표 칸 · 글상자)의 문단들 — 문서 차례
        by.setdefault(p.getparent(), []).append(i)
    obj = [clone._has_object(p) for p in ps]
    ok = [bool(pick(i, p, t)) for i, (p, t) in enumerate(zip(ps, texts))]
    blank = [not o and not (t or "").strip() for o, t in zip(obj, texts)]

    def view(sg):
        return [[{"idx": i, "segs": sg[i], "blank": blank[i], "obj": obj[i], "ok": ok[i]} for i in flow] for flow in by.values()]
    PG, keep, put, n, more = LT.Pages(R), {}, {}, 0, R["rounds"]
    while PG.step(view(segs), more=more > 0):
        for b in set(put) | set(PG.scale):
            pct = PG.scale.get(b, 100)
            if put.get(b, 100) == pct:
                continue
            runs = list(ps[b].iterchildren(RUN))
            if b not in keep:
                keep[b] = [r.get("charPrIDRef", "0") for r in runs]
            for r, old in zip(runs, keep[b]):   # 처음 글자 모양으로 되돌린 뒤 그 배율을(배율이 겹쳐 쌓이지 않게)
                r.set("charPrIDRef", old)
            LT.scale_height(clone, ps[b], pct)
            put[b] = pct
        n += 1
        more -= 1
        if progress:
            progress(n, len(PG.tries))
        segs = lay()
    done, left, blanks = PG.result(view(segs))
    return done, left, blanks, PG.first or 0, n


def plan_bytes(data, R, pick, layout, progress=None):
    """문서 바이트 → 줄 정리 계획(문서 차례 idx 로). pick(idx, p, text) → 그 문단을 볼지 · layout(bytes) → 한글이 끝 쪽까지 조판한 바이트(pdf_render.layout_hwpx — 시험은 가짜).
    → {items[{idx, text, ops[{kind, rs, re, pct}], before[], after[]}], left[{idx, text, kind, line, a, b, why, at}], counts, rounds,
       pages[{idx, text, tail, blanks[{idx, pct}]}], pageLeft[{idx, text, tail, why}], blanks[{idx, pct}]}(쪽에 걸친 줄 — ② §8: 장평 걸음 뒤 · 규칙 pageTail 이 0 이면 빈 목록)."""
    from app import outline_pos
    from app.heading_extract import _cid_at, run_ranges
    from app.hwpx_doc import HwpxDoc
    clone = HwpxDoc(data)
    ps = _paras(clone)
    texts = [clone._text(p) for p in ps]
    M = outline_pos.Measure(clone)
    first, segs = _laid(layout(data), texts)
    jobs, seen = [], 0
    for i, (p, t) in enumerate(zip(ps, texts)):
        br = first[i]
        if not br or not pick(i, p, t):
            continue
        seen += 1
        spans = LT.spans_of(t, br)
        cell = _in_cell(p)
        if not LT.issues(t, spans, R, cell=cell):
            continue
        rr, fb = run_ranges(clone, p), clone._char_id(p)
        cids = [_cid_at(rr, j, fb) for j in range(len(t))]

        def width(a, b, t=t, cids=cids):
            tot = 0.0
            for j in range(a, b):
                w = M.advance(t[j], cids[j])
                if w is None:
                    return None
                tot += w
            return tot

        def ratios(a, b, t=t, cids=cids):
            from app import fonts
            vals = []
            for j in range(a, max(b, a + 1)):
                c = M._char(cids[min(j, len(cids) - 1)])
                vals.append(round(100 * (c["ratio"][fonts.lang_of(t[min(j, len(t) - 1)])] if c else 1)))
            return (min(vals), max(vals))
        jobs.append(LT.Para(i, t, spans, R, width, ratios, cell))
    orig, applied, rounds = {}, {}, 0
    for _ in range(R["rounds"]):
        live = [j for j in jobs if j.trial]
        if not live:
            break
        rounds += 1
        if progress:
            progress(rounds, len(live))
        for j in live:
            want = tuple((o["rs"], o["re"], o["pct"]) for o in j.all_ops())
            if applied.get(j.idx) == want:
                continue
            p = ps[j.idx]
            if j.idx in orig:   # 처음 문단으로 되돌린 뒤 ops 를 모두 다시(배율이 겹쳐 쌓이지 않게)
                for c in list(p):
                    p.remove(c)
                for c in orig[j.idx]:
                    p.append(copy.deepcopy(c))
            else:
                orig[j.idx] = [copy.deepcopy(c) for c in p]
            for rs, re_, pct in want:
                LT.scale_ratio(clone, p, rs, re_, pct)
            applied[j.idx] = want
        now, segs = _laid(layout(clone.save()), texts)
        for j in live:
            br = now[j.idx]
            if br is None:
                j._fail(j.trial, "measure")
            else:
                j.observe(LT.spans_of(j.text, br))
    items, left = [], []
    for j in jobs:
        ops = j.finish()
        left += [{"idx": j.idx, **x} for x in j.left]
        if ops:
            items.append({"idx": j.idx, "text": j.text, "ops": [{"kind": o["kind"], "rs": o["rs"], "re": o["re"], "pct": o["pct"]} for o in ops],
                          "before": LT.lines_text(j.text, j.spans0), "after": LT.lines_text(j.text, j.spans)})
    pages, page_left, blanks, page_seen, page_rounds = [], [], [], 0, 0
    if R.get("pageTail"):   # 쪽에 걸친 줄(② §8) — 남길 장평만 입힌 사본에서(거둔 시도 · 되돌린 문단을 처음 꼴로 — 그랬으면 다시 잰다)
        stale = False
        for j in jobs:
            want = tuple((o["rs"], o["re"], o["pct"]) for o in j.ops)
            if applied.get(j.idx, ()) == want:
                continue
            p = ps[j.idx]
            for c in list(p):
                p.remove(c)
            for c in orig[j.idx]:
                p.append(copy.deepcopy(c))
            for rs, re_, pct in want:
                LT.scale_ratio(clone, p, rs, re_, pct)
            clone._touch(p)
            applied[j.idx], stale = want, True

        def lay():
            return _laid(layout(clone.save()), texts)[1]
        got = _page_pass(clone, ps, texts, pick, R, lay() if stale else segs, lay, progress)
        pages = [{**d, "text": texts[d["idx"]]} for d in got[0]]
        page_left = [{**x, "text": texts[x["idx"]][:80]} for x in got[1]]
        blanks, page_seen, page_rounds = got[2], got[3], got[4]
    kinds = Counter(o["kind"].split("+")[0] for it in items for o in it["ops"])
    return {"items": items, "left": left, "rounds": rounds, "pages": pages, "pageLeft": page_left, "blanks": blanks, "pageRounds": page_rounds,
            "counts": {"seen": seen, "paras": len(jobs), "fixed": len(items), "ops": sum(kinds.values()), "pull": kinds["pull"], "push": kinds["push"], "last": kinds["last"],
                       "chain": sum(1 for it in items for o in it["ops"] if o["kind"] == "pull+last"),
                       "left": len([x for x in left if x["why"] != "short"]), "short": len([x for x in left if x["why"] == "short"]),
                       "why": dict(Counter(LT.WHY.get(x["why"], x["why"]) for x in left if x["why"] != "short")),
                       "pageSeen": page_seen, "pageFixed": len(pages), "pageLeft": len(page_left), "pageBlanks": len(blanks),
                       "pageWhy": dict(Counter(LT.PAGE_WHY.get(x["why"], x["why"]) for x in page_left))}}


def _snapshot(s):
    """(세션 잠금 안) → (바이트, rev, 문단 차례 → 블록 id, 볼 차례). 볼 문단 = 블록 문단(본문 · 표 칸 · 캡션) · 개체 없음 · 한 쪽 평면 밖 글자(UTF-16 둘) 없음."""
    from app.division_profiles import _structure as structure
    ids = {b["id"] for b in structure.iter_blocks(s.doc.blocks()) if b.get("type") == "paragraph"}
    ps = _paras(s.doc)
    pid, ok = {}, set()
    for i, p in enumerate(ps):
        b = s.doc._rev.get(p)
        if b in ids:
            pid[i] = b
            t = s.doc._text(p)
            if not s.doc._has_object(p) and all(ord(c) <= 0xFFFF for c in t):
                ok.add(i)
    return s.doc.save(), s.rev, pid, ok


@router.post("/api/docs/{doc_id}/line-tidy/plan")
def line_tidy_plan(doc_id: str):
    """한글로 줄을 재고 규칙에 걸린 자리를 고친 사본으로 다시 재어 맞는 장평을 찾는다(수십 초) → {planId, rev, items, left, counts, rounds, seconds} | {nothing, why}.
    문서는 안 바뀐다 — 반영은 POST …/line-tidy/apply. 한글이 없으면 409."""
    from app import server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 됩니다")
    if not _hwp_ok():
        raise HTTPException(409, NO_HWP)
    R = rules()
    t0 = time.time()
    with s.lock:
        data, rev, pid, ok = _snapshot(s)
    try:
        res = plan_bytes(data, R, lambda i, p, t: i in ok, _layout)
    except LayoutMismatch as e:
        raise HTTPException(409, str(e)) from e
    except (TimeoutError, RuntimeError) as e:
        raise HTTPException(503, f"한글로 줄을 재지 못했습니다 — {e}") from e
    items = [{"id": pid[it.pop("idx")], **it} for it in res["items"]]
    left = [{"id": pid[x.pop("idx")], **x} for x in res["left"] if x["idx"] in pid]
    blanks = [{"id": pid[b["idx"]], "pct": b["pct"]} for b in res.get("blanks") or ()]   # 쪽에 걸친 줄(② §8) — 높이를 낮출 빈 줄(볼 문단만 고르니 모두 블록 문단이다)
    pages = [{"id": pid[d["idx"]], "text": d["text"], "tail": d["tail"], "blanks": [{"id": pid[b["idx"]], "pct": b["pct"]} for b in d["blanks"]]} for d in res.get("pages") or ()]
    page_left = [{"id": pid[x["idx"]], "text": x["text"], "tail": x["tail"], "why": x["why"]} for x in res.get("pageLeft") or ()]
    plan = {"planId": uuid.uuid4().hex[:12], "at": time.time(), "rev": rev, "rules": R, "items": items, "left": left, "counts": res["counts"],
            "pages": pages, "pageLeft": page_left, "blanks": blanks, "rounds": res["rounds"], "pageRounds": res.get("pageRounds", 0), "seconds": round(time.time() - t0, 1)}
    _save(doc_id, {**load(doc_id), "plan": plan})
    log.info("[줄 정리] %s 계획 — 문단 %d · 고칠 문단 %d · 다시 재기 %d번 · 쪽에 걸친 문단 %d 가운데 %d(빈 줄 %d · 다시 재기 %d번) · %.1fs", doc_id, res["counts"]["paras"], len(items), res["rounds"],
             res["counts"].get("pageSeen", 0), len(pages), len(blanks), plan["pageRounds"], plan["seconds"])
    return {k: plan[k] for k in ("planId", "rev", "items", "left", "counts", "pages", "pageLeft", "blanks", "rounds", "pageRounds", "seconds")} | ({"nothing": True} if not items and not blanks else {})


@router.get("/api/docs/{doc_id}/line-tidy")
def line_tidy_get(doc_id: str):
    """저장한 것 {plan, applied} + 상태의 재료(facts) + 규칙. 문서 안 바뀜."""
    return {**load(doc_id), "facts": facts(doc_id), **_rules_out()}


@router.post("/api/docs/{doc_id}/line-tidy/apply")
def line_tidy_apply(doc_id: str, body: dict = Body(default={})):
    """{planId} → 그 계획의 장평을 한 번에(실행 취소 1 · 기록 `lineTidy`) → {done[문단 id], items, …편집 상태} | {nothing: true}(고칠 것이 없음 — 반영 기록은 남김).
    409 = 지금 계획이 아님 · 계획을 잰 뒤 문서가 바뀜."""
    from app import server
    s0 = server._sess(doc_id)
    if s0.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 됩니다")
    rec = load(doc_id)
    plan = rec.get("plan")
    if not plan or plan.get("planId") != body.get("planId"):
        raise HTTPException(409, "그 줄 정리 계획은 지금 계획이 아닙니다 — 다시 재세요")
    items = plan.get("items") or []
    blanks = plan.get("blanks") or []   # 쪽에 걸친 줄(② §8) — 높이를 낮출 빈 줄 [{id, pct}]
    applied = {"at": time.time(), "planId": plan["planId"], "rev": None, "fill": _fill_at(doc_id), "paras": len(items),
               "ops": sum(len(it["ops"]) for it in items), "pages": len(plan.get("pages") or ()), "blanks": len(blanks), "counts": plan.get("counts") or {}}
    with s0.lock:
        if s0.rev != plan.get("rev"):
            raise HTTPException(409, "줄을 잰 뒤 문서가 바뀌었습니다 — 다시 재세요")
        if not items and not blanks:
            applied["rev"] = s0.rev
            _save(doc_id, {**rec, "applied": applied})
            return {"nothing": True, "done": [], "items": [], **s0.state()}

    def make(s):
        if s.rev != plan.get("rev"):
            raise HTTPException(409, "줄을 잰 뒤 문서가 바뀌었습니다 — 다시 재세요")
        els, bls = [], []
        for it in items:
            p = s.doc._ids.get(it["id"])
            if p is None or not s.doc._attached(p) or s.doc._text(p) != it["text"]:
                raise HTTPException(409, "줄을 잰 뒤 그 문단이 바뀌었습니다 — 다시 재세요")
            els.append(p)
        for b in blanks:
            p = s.doc._ids.get(b["id"])
            if p is None or not s.doc._attached(p) or s.doc._text(p).strip() or s.doc._has_object(p):
                raise HTTPException(409, "줄을 잰 뒤 그 빈 줄이 바뀌었습니다 — 다시 재세요")
            bls.append(p)

        def run():
            for p, it in zip(els, items):
                for o in it["ops"]:
                    LT.scale_ratio(s.doc, p, o["rs"], o["re"], o["pct"])
            for p, b in zip(bls, blanks):
                LT.scale_height(s.doc, p, b["pct"])
            return {"hosts": els + bls, "formatted": {it["id"] for it in items} | {b["id"] for b in blanks}, "struct": set(), "origin": {},
                    "anchor": (items[0] if items else blanks[0])["id"], "log": {"paras": len(items), "ops": applied["ops"], "pages": applied["pages"], "blanks": len(blanks)}}
        return els + bls, run
    out = server._edit(doc_id, make, "lineTidy", {"planId": plan["planId"], "paras": len(items), "blanks": len(blanks)})
    if isinstance(out, dict):
        applied["rev"] = out.get("rev", server._sess(doc_id).rev)
        _save(doc_id, {**load(doc_id), "applied": applied})
        out["done"] = [it["id"] for it in items]
        out["tidy"] = {"pages": plan.get("pages") or [], "blanks": blanks}   # 쪽에 걸친 줄(② §8) — 한 쪽으로 모은 문단 · 높이를 낮춘 빈 줄
        out["items"] = [{k: it[k] for k in ("id", "before", "after", "ops")} for it in items]
    return out
