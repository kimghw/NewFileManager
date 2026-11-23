"""줄 정리 끝점(spec/spec_줄정리.md ② §5 · §6) — 계산은 `app/line_tidy.py`, 한글 조판은 `pdf_render.layout_hwpx`. hwpx 문서만 · 어느 워크플로우의 문서에서나.

- 규칙(이 PC 의 모든 문서 · 워크플로우가 같이 씀): `GET /api/line-tidy/rules` → {rules, defs, defaults, updated} · `PUT …` {rules} → 저장 · `DELETE …` → 기본값으로.
  저장 `%LOCALAPPDATA%\\NewFileManager\\line_tidy.json`(env `NFM_LINE_TIDY` = 파일 경로 · `off`·`0` 이면 메모리만 — 시험 · 화면 검사는 임시 파일).
- `GET /api/docs/{id}/line-tidy` → 저장한 것(마지막 계획 · 마지막 반영)과 상태의 재료. 문서 안 바뀜 · 한글 안 부름.
- `POST …/line-tidy/plan` → 지금 문서를 떠서(세션 잠금 안 — 바이트 · rev) **잠금 밖에서** 한글로 조판해 줄을 읽고, 규칙에 걸린 자리마다 자간을 어림해 고친 사본을 다시 조판해 맞았는지 본다
  (맞지 않으면 1%씩 더 — 규칙 「한글로 다시 재기」 번까지). 문단은 서로의 줄 나눔에 닿지 않아 모든 문단을 한 번에 고쳐 한 번에 잰다 → {planId, rev, items, left, counts, seconds}. 문서 안 바뀜.
  이어서 **쪽에 걸친 줄**(② §8 — 규칙 `pageTail` 이 0 이 아니면): 자간을 입힌 사본에서 다음 쪽으로 넘어간 줄이 규칙 이하인 문단마다 그 쪽의 빈 줄 높이를 낮춰 다시 잰다(`_page_pass`) → pages · pageLeft · blanks.
- `POST …/line-tidy/apply {planId}` → 그 계획의 자간과 빈 줄 높이를 한 번에(구조 편집 트랜잭션 하나 — 실행 취소 1 · 기록 `lineTidy`). 계획을 잰 뒤 문서가 바뀌었으면 409(다시 잰다).
  고칠 것이 없어도 반영 기록은 남긴다(확인은 끝남).
- 저장 = 작업 폴더 `linetidy.json` {version, plan{planId, at, rev, rules, items[{id, text, ops[{kind, rs, re, pct}], before[], after[]}], left[…], counts, seconds,
  pages[{id, text, tail, blanks[{id, pct}]}], pageLeft[{id, text, tail, why}], blanks[{id, pct}], pageRounds} | None,
  applied{at, planId, rev, fill(그때의 「내용 넣기」 반영 표식 | None), paras, ops, pages, blanks, counts} | None,
  ratio[{id, text, ops[{rs, re, pct}], before[], after[]}](전에 **장평으로** 고친 줄의 기록 — 한 번 적고 지우지 않는다: ② §9) | 없음}.
- **장평 → 자간**(② §9 — 2026-11-23 사용자 「자간으로 당기기」): 계획의 `by: "space"` = 배율을 자간으로 입히는 계획. 그 표시가 없는 계획(전의 장평 계획)은 반영하지 않는다(409 — 다시 잰다).
  전에 장평으로 반영한 기록이 있으면(`_legacy`) 다시 잴 때 **그 장평이 지금 문서에 있다는 근거가 있는 줄만**(`line_tidy.ratio_proof` — 기록은 실행 취소해도 남는다) 장평을 되돌린 사본에서 재고(`plan_bytes(undo=)`),
  반영이 같은 편집에서 장평을 되돌리고 자간을 입힌다(계획의 `undo`). 「옛 줄이 남았나」 는 기록이 아니라 **문서에서** 센다(`facts.ratio` — 자간으로 바꾼 것을 실행 취소하면 다시 선다)."""
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


def _legacy(rec):
    """전에 **장평으로** 고친 줄의 기록 [{id, text, ops[{rs, re, pct}], before[], after[]}](② §9) — 그 장평이 지금 문서에 있는지는 따로 본다(`_proven` · `line_tidy.ratio_proof`).
    기록의 `ratio` 가 원본이고(한 번 적고 지우지 않는다), 그 키가 없는 옛 기록은 마지막 반영이 장평 계획(`by` 없음)이고 그 계획이 아직 남아 있을 때(planId 가 같음) 그 계획의 항목이다."""
    if isinstance(rec.get("ratio"), list):
        return rec["ratio"]
    p, a = rec.get("plan"), rec.get("applied")
    if not p or not a or p.get("by") or p.get("planId") != a.get("planId"):
        return []
    return [{"id": it["id"], "text": it["text"], "ops": [{k: o[k] for k in ("rs", "re", "pct")} for o in it["ops"]], "before": it.get("before") or [], "after": it.get("after") or []}
            for it in p.get("items") or ()]


def _ops(x):
    return [(o["rs"], o["re"], o["pct"]) for o in x["ops"]]


def _proven(s, old):
    """(세션 잠금 안) 옛 장평 기록 가운데 그 장평이 **지금 문서에 있다는 구조 근거**가 있는 항목 — 문단이 있고 글이 그대로이고 `ratio_proof`(옆 런까지)가 선다. 문서 안 바뀜 · 한글 안 부름."""
    out = []
    for x in old:
        p = s.doc._ids.get(x["id"])
        if p is not None and s.doc._attached(p) and s.doc._text(p) == x["text"] and LT.ratio_proof(s.doc, p, _ops(x)):
            out.append(x)
    return out


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
    """워크플로우 상태의 재료 → {why, plan{at, rev, paras, ops, left} | None, applied{at, rev, fill, paras, ops, counts} | None, fill, rules, rulesText, ratio(전에 장평으로 고친 문단 수)}. 문서 안 바뀜 · 한글 안 부름."""
    from app import server
    s = server._sess(doc_id)
    rec = load(doc_id)
    old = _legacy(rec) if s.fmt == "hwpx" else []
    with s.lock:
        why, rev = _why(s), s.rev
        ratio = len(_proven(s, old)) if old else 0   # 전에 장평으로 고친 줄이 지금 문서에 남아 있나(② §9) — 기록이 아니라 문서에서 센다
    p, a = rec.get("plan"), rec.get("applied")
    R = rules()
    return {"why": why, "rev": rev, "fill": _fill_at(doc_id), "rules": R, "rulesText": LT.rules_text(R),
            "plan": {"at": p.get("at"), "rev": p.get("rev"), "planId": p.get("planId"), "paras": len(p.get("items") or ()), "counts": p.get("counts") or {}} if p else None,
            "applied": {k: a.get(k) for k in ("at", "rev", "fill", "paras", "ops", "counts")} if a else None,
            "ratio": ratio}   # 전에 장평으로 고친 문단 가운데 지금 문서에 그 장평이 남아 있는 수(② §9 — 다시 돌리면 자간으로 바꾼다)


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
    """쪽에 걸친 줄(② §8) — 자간 걸음이 끝난 사본에서: 걸린 문단마다 그 쪽의 빈 줄 높이를 낮춰 보고(LT.Pages) 한글로 다시 잰다. segs = 지금 사본의 줄 자리 · lay() → 사본을 다시 잰 줄 자리.
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


def plan_bytes(data, R, pick, layout, progress=None, undo=None):
    """문서 바이트 → 줄 정리 계획(문서 차례 idx 로). pick(idx, p, text) → 그 문단을 볼지 · layout(bytes) → 한글이 끝 쪽까지 조판한 바이트(pdf_render.layout_hwpx — 시험은 가짜).
    undo = {idx: {text, ops[{rs, re, pct}], before[], after[]}} — 전에 장평으로 고친 줄의 기록(② §9): 글이 그대로이고 **그 장평이 지금 문서에 있다는 근거**가 있는 문단만
    장평을 되돌린 사본에서 잰다 → 결과의 `undone`(idx 차례) · `undoneBy` {idx: "runs" | "lines"}. 근거 = 구조(`LT.ratio_proof` — 옆 런까지) · 옆 런이 없는 문단(본문 전체가 범위)은
    지금 문서를 한 번 조판한 줄이 옛 계획의 after 와 같을 때(before 와는 다름 — 실행 취소한 문서는 before 로 돌아가 있다).
    → {items[{idx, text, ops[{kind, rs, re, pct}], before[], after[]}], left[{idx, text, kind, line, a, b, why, at}], counts, rounds,
       pages[{idx, text, tail, blanks[{idx, pct}]}], pageLeft[{idx, text, tail, why}], blanks[{idx, pct}]}(쪽에 걸친 줄 — ② §8: 장평 걸음 뒤 · 규칙 pageTail 이 0 이면 빈 목록)."""
    from app import outline_pos
    from app.heading_extract import _cid_at, run_ranges
    from app.hwpx_doc import HwpxDoc
    clone = HwpxDoc(data)
    ps = _paras(clone)
    texts = [clone._text(p) for p in ps]
    undone, by, proofs, maybe = [], {}, {}, {}
    for i, x in sorted((undo or {}).items()):   # 전에 장평으로 고친 줄 — 되돌린 꼴이 이 계획의 「처음」 이다. 근거는 모두 먼저 세고(문서를 안 바꾼다) 그 뒤에 되돌린다
        if not (0 <= i < len(ps) and texts[i] == x["text"]):
            continue
        ops = [(o["rs"], o["re"], o["pct"]) for o in x["ops"]]
        got = LT.ratio_proof(clone, ps[i], ops)
        if got:
            proofs[i], by[i] = got, "runs"
        elif x.get("after") and x.get("after") != x.get("before"):
            got = LT.ratio_proof(clone, ps[i], ops, neighbor=False)
            if got:
                maybe[i] = (got, x["after"])
    if maybe:   # 옆 런이 없는 문단 — 지금 문서의 한글 줄이 옛 계획의 after 와 같을 때만(조판 한 번 더)
        now = _laid(layout(data), texts)[0]
        for i, (got, after) in maybe.items():
            if now[i] is not None and LT.lines_text(texts[i], LT.spans_of(texts[i], now[i])) == after:
                proofs[i], by[i] = got, "lines"
    for i in sorted(proofs):
        LT.restore(clone, ps[i], proofs[i])
        undone.append(i)
    if undone:
        data = clone.save()
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

        def spaces(a, b, cids=cids):   # 그 범위의 지금 자간(%) — (가장 좁은, 가장 넓은). **언어 일곱 모두**에서 센다 — 자간은 일곱 언어에 다 적히니(scale_spacing)
            vals = []                    # 그 글자의 언어 것만 보면 안 쓰인 언어의 값이 한도를 넘는다(한글 0% · 영문 −14% 인 런을 90% 로 → 영문 −23%: astra 2026-11-23)
            for cid in set(cids[a:max(b, a + 1)]) or {cids[-1]}:
                e = clone._defs["charPr"].get(str(cid))
                e = e.find(LT._hh("spacing")) if e is not None else None
                vals += [int(e.get(x) or 0) if e is not None else 0 for x in LT.LANGS]
            return (min(vals), max(vals))
        jobs.append(LT.Para(i, t, spans, R, width, spaces, cell))
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
                LT.scale_spacing(clone, p, rs, re_, pct)
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
    if R.get("pageTail"):   # 쪽에 걸친 줄(② §8) — 남길 자간만 입힌 사본에서(거둔 시도 · 되돌린 문단을 처음 꼴로 — 그랬으면 다시 잰다)
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
                LT.scale_spacing(clone, p, rs, re_, pct)
            clone._touch(p)
            applied[j.idx], stale = want, True

        def lay():
            return _laid(layout(clone.save()), texts)[1]
        got = _page_pass(clone, ps, texts, pick, R, lay() if stale else segs, lay, progress)
        pages = [{**d, "text": texts[d["idx"]]} for d in got[0]]
        page_left = [{**x, "text": texts[x["idx"]][:80]} for x in got[1]]
        blanks, page_seen, page_rounds = got[2], got[3], got[4]
    kinds = Counter(o["kind"].split("+")[0] for it in items for o in it["ops"])
    return {"items": items, "left": left, "rounds": rounds, "pages": pages, "pageLeft": page_left, "blanks": blanks, "pageRounds": page_rounds, "undone": undone, "undoneBy": by,
            "counts": {"seen": seen, "paras": len(jobs), "fixed": len(items), "ops": sum(kinds.values()), "pull": kinds["pull"], "push": kinds["push"], "last": kinds["last"],
                       "chain": sum(1 for it in items for o in it["ops"] if o["kind"] == "pull+last"),
                       "left": len([x for x in left if x["why"] != "short"]), "short": len([x for x in left if x["why"] == "short"]),
                       "why": dict(Counter(LT.WHY.get(x["why"], x["why"]) for x in left if x["why"] != "short")),
                       "undone": len(undone), "ratioLeft": sum(1 for i, x in (undo or {}).items() if 0 <= i < len(ps) and texts[i] == x["text"]) - len(undone),
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
    """한글로 줄을 재고 규칙에 걸린 자리를 고친 사본으로 다시 재어 맞는 자간을 찾는다(수십 초) → {planId, rev, items, left, counts, rounds, seconds} | {nothing, why}.
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
    old = _legacy(load(doc_id))   # 전에 장평으로 고친 줄의 기록(② §9) — 근거가 있는 것만 되돌린 사본에서 재고, 반영이 같은 편집에서 되돌린다
    at = {b: i for i, b in pid.items()}
    undo = {at[x["id"]]: x for x in old if x["id"] in at and at[x["id"]] in ok}
    try:
        res = plan_bytes(data, R, lambda i, p, t: i in ok, _layout, undo=undo)
    except LayoutMismatch as e:
        raise HTTPException(409, str(e)) from e
    except (TimeoutError, RuntimeError) as e:
        raise HTTPException(503, f"한글로 줄을 재지 못했습니다 — {e}") from e
    items = [{"id": pid[it.pop("idx")], **it} for it in res["items"]]
    left = [{"id": pid[x.pop("idx")], **x} for x in res["left"] if x["idx"] in pid]
    blanks = [{"id": pid[b["idx"]], "pct": b["pct"]} for b in res.get("blanks") or ()]   # 쪽에 걸친 줄(② §8) — 높이를 낮출 빈 줄(볼 문단만 고르니 모두 블록 문단이다)
    pages = [{"id": pid[d["idx"]], "text": d["text"], "tail": d["tail"], "blanks": [{"id": pid[b["idx"]], "pct": b["pct"]} for b in d["blanks"]]} for d in res.get("pages") or ()]
    page_left = [{"id": pid[x["idx"]], "text": x["text"], "tail": x["tail"], "why": x["why"]} for x in res.get("pageLeft") or ()]
    how = {pid[i]: w for i, w in (res.get("undoneBy") or {}).items()}
    plan = {"planId": uuid.uuid4().hex[:12], "at": time.time(), "rev": rev, "by": "space", "rules": R, "items": items, "left": left, "counts": res["counts"],
            "undo": [{"id": x["id"], "text": x["text"], "ops": x["ops"], "by": how[x["id"]]} for x in old if x["id"] in how],
            "pages": pages, "pageLeft": page_left, "blanks": blanks, "rounds": res["rounds"], "pageRounds": res.get("pageRounds", 0), "seconds": round(time.time() - t0, 1)}
    # ratio — 이 계획이 옛 계획을 덮어도 전에 장평으로 고친 줄의 기록을 잃지 않게. 한 번 적고 지우지 않는다(근거를 못 찾은 줄도 — 재기만으로 근거를 지우지 않는다:
    # 그 장평이 문서에 있는지는 늘 문서에서 다시 본다 — `_proven`)
    _save(doc_id, {**load(doc_id), "plan": plan, "ratio": old})
    log.info("[줄 정리] %s 계획 — 문단 %d · 고칠 문단 %d · 다시 재기 %d번 · 쪽에 걸친 문단 %d 가운데 %d(빈 줄 %d · 다시 재기 %d번) · %.1fs", doc_id, res["counts"]["paras"], len(items), res["rounds"],
             res["counts"].get("pageSeen", 0), len(pages), len(blanks), plan["pageRounds"], plan["seconds"])
    return {k: plan[k] for k in ("planId", "rev", "items", "left", "counts", "pages", "pageLeft", "blanks", "undo", "rounds", "pageRounds", "seconds")} | (
        {"nothing": True} if not items and not blanks and not plan["undo"] else {})


@router.get("/api/docs/{doc_id}/line-tidy")
def line_tidy_get(doc_id: str):
    """저장한 것 {plan, applied} + 상태의 재료(facts) + 규칙. 문서 안 바뀜."""
    return {**load(doc_id), "facts": facts(doc_id), **_rules_out()}


@router.post("/api/docs/{doc_id}/line-tidy/apply")
def line_tidy_apply(doc_id: str, body: dict = Body(default={})):
    """{planId} → 그 계획의 자간을 한 번에(전에 장평으로 고친 줄은 그 장평을 되돌리고 — ② §9 · 실행 취소 1 · 기록 `lineTidy`) → {done[문단 id], items, …편집 상태} | {nothing: true}(고칠 것이 없음 — 반영 기록은 남김).
    409 = 지금 계획이 아님 · 계획을 잰 뒤 문서가 바뀜."""
    from app import server
    s0 = server._sess(doc_id)
    if s0.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 됩니다")
    rec = load(doc_id)
    plan = rec.get("plan")
    if not plan or plan.get("planId") != body.get("planId"):
        raise HTTPException(409, "그 줄 정리 계획은 지금 계획이 아닙니다 — 다시 재세요")
    if plan.get("by") != "space":   # 장평으로 잰 옛 계획 — 그 배율을 자간으로 입히면 한글로 확인한 것이 아니다
        raise HTTPException(409, "그 줄 정리 계획은 장평으로 잰 옛 계획입니다 — 다시 재세요")
    items = plan.get("items") or []
    undo = plan.get("undo") or []   # 전에 장평으로 고친 줄(② §9) — 같은 편집에서 그 장평을 되돌린다
    blanks = plan.get("blanks") or []   # 쪽에 걸친 줄(② §8) — 높이를 낮출 빈 줄 [{id, pct}]
    applied = {"at": time.time(), "planId": plan["planId"], "rev": None, "fill": _fill_at(doc_id), "paras": len(items),
               "ops": sum(len(it["ops"]) for it in items), "pages": len(plan.get("pages") or ()), "blanks": len(blanks), "counts": plan.get("counts") or {}}
    with s0.lock:
        if s0.rev != plan.get("rev"):
            raise HTTPException(409, "줄을 잰 뒤 문서가 바뀌었습니다 — 다시 재세요")
        if not items and not blanks and not undo:
            applied["rev"] = s0.rev
            _save(doc_id, {**rec, "applied": applied, "ratio": _legacy(rec)})   # ratio — 옛 기록을 그 키로 옮겨 둔다(지우지 않는다)
            return {"nothing": True, "done": [], "items": [], **s0.state()}

    def make(s):
        if s.rev != plan.get("rev"):
            raise HTTPException(409, "줄을 잰 뒤 문서가 바뀌었습니다 — 다시 재세요")
        els, bls, uls, proofs = [], [], [], []
        for it in undo:   # 근거는 **쓰기 전에** 모두 다시 센다 — 쓰다가 409 를 내면 앞 문단은 바뀐 채 남는다(_transact 는 KeyError · ValueError 만 되돌린다: astra 2026-11-23)
            p = s.doc._ids.get(it["id"])
            if p is None or not s.doc._attached(p) or s.doc._text(p) != it["text"]:
                raise HTTPException(409, "줄을 잰 뒤 그 문단이 바뀌었습니다 — 다시 재세요")
            got = LT.ratio_proof(s.doc, p, _ops(it), neighbor=it.get("by") != "lines")
            if not got:
                raise HTTPException(409, "줄을 잰 뒤 그 문단의 서식이 바뀌었습니다 — 다시 재세요")
            uls.append(p)
            proofs.append(got)
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

        hosts = list(dict.fromkeys(uls + els + bls))

        def run():
            for p, got in zip(uls, proofs):   # 먼저 전의 장평을 되돌리고(계획은 그 꼴에서 쟀다) 그 위에 자간을
                LT.restore(s.doc, p, got)
            for p, it in zip(els, items):
                for o in it["ops"]:
                    LT.scale_spacing(s.doc, p, o["rs"], o["re"], o["pct"])
            for p, b in zip(bls, blanks):
                LT.scale_height(s.doc, p, b["pct"])
            return {"hosts": hosts, "formatted": {it["id"] for it in undo} | {it["id"] for it in items} | {b["id"] for b in blanks}, "struct": set(), "origin": {},
                    "anchor": (items[0] if items else blanks[0] if blanks else undo[0])["id"],
                    "log": {"paras": len(items), "ops": applied["ops"], "pages": applied["pages"], "blanks": len(blanks), "ratioUndone": len(undo)}}
        return hosts, run
    out = server._edit(doc_id, make, "lineTidy", {"planId": plan["planId"], "paras": len(items), "blanks": len(blanks)})
    if isinstance(out, dict):
        applied["rev"] = out.get("rev", server._sess(doc_id).rev)
        now = load(doc_id)
        _save(doc_id, {**now, "applied": applied, "ratio": _legacy(now)})   # ratio — 옛 기록은 남긴다(되돌린 줄은 이제 근거가 안 서 「옛 줄」 로 안 세고, 이 반영을 실행 취소하면 다시 선다)
        out["done"] = [it["id"] for it in items]
        out["undone"] = [it["id"] for it in undo]   # 장평을 되돌린 문단(② §9)
        out["tidy"] = {"pages": plan.get("pages") or [], "blanks": blanks}   # 쪽에 걸친 줄(② §8) — 한 쪽으로 모은 문단 · 높이를 낮춘 빈 줄
        out["items"] = [{k: it[k] for k in ("id", "before", "after", "ops")} for it in items]
    return out
