"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속 API(spec_hwpx_웹편집 ② §8-2) — server.py 가 include 한다(`outline_format_api` 와 같은 꼴).
계산은 `app/outline_match.py`, 오버레이는 `server._outline_ov`, 트랜잭션은 `server._transact`·`server._edit`(실행 취소 1 · 기록)."""
import contextlib
import copy

from fastapi import APIRouter, Body, HTTPException

from app import outline_conform, outline_edit, outline_match, outline_pos

router = APIRouter()


@contextlib.contextmanager
def _ov_guard(ov, on=True):
    """오버레이를 여러 걸음 바꾸는 동안(대표 바꿈 → 떼기 → … — ② §8-5) 도중의 ValueError·KeyError 에 오버레이를 처음 것으로 **제자리에서** 되돌린다
    (문서를 안 건드린 실패는 트랜잭션이 되돌리지 않는다). on 이 거짓이면 아무것도 안 한다(떼기가 없는 맞추기 — 사본 비용을 안 쓴다)."""
    back = copy.deepcopy(ov) if on else None
    try:
        yield
    except (KeyError, ValueError):
        if back is not None:
            ov.clear()
            ov.update(back)
        raise


def _server():
    from app import server  # 세션·트랜잭션은 server 것 — 부를 때 가져온다(순환 import 피함)
    return server


def _hwpx(s):
    if s.fmt != "hwpx":
        raise HTTPException(400, "개요 편집은 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")


def _ov(server, s):
    ov = server._outline_ov(s)
    if ov is None:
        raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
    return ov


def _state(s):
    edited = s.edited()
    return {"edited": sorted(edited), "original": {i: s.orig_texts.get(i, "") for i in edited}, **s.state()}


def _model_only(server, s, op, req, change):
    """문서를 안 바꾸는 오버레이 변경(대표 정하기 · 넣기 · 떼기)을 트랜잭션 하나로 — 실행 취소 묶음에 오버레이가 들어 되돌릴 수 있고 기록에 한 줄.
    change() -> 기록에 더할 것(dict). 그 안의 ValueError·KeyError 는 400(오버레이는 바꾸기 전에 다 검사한다)."""
    got = {}

    def run():
        got.update(change() or {})
        return {"hosts": [], "formatted": set(), "struct": set(), "origin": {}, "anchor": None, "log": dict(got)}
    out, after = server._transact(s, run, op, req=req, local=[])
    return (out, None) if after is None else (got, True)


@router.get("/api/docs/{doc_id}/outline/formats")
def formats(doc_id: str, tpl: str | None = None, level: int | None = None):
    """모든 템플릿 레벨의 서식 갈래 → {rev, keys[[키, 이름]…](비교 값 차례), slots: {tpl: {레벨: {total, rep, repMissing, others, groups[{key, count, paras, more, rep, look, raw, diff}]}}}}.
    2단계 결과가 없거나 docx 면 {off: true}.
    `?tpl=&level=` 을 주면 그 슬롯 하나만, 갈래마다 **줄 전부**(paras 를 30줄에서 자르지 않는다 · more 0 · 응답에 full: true) —
    문서의 「템플릿만 또렷이」 가 줄마다 대표와 다른 값을 표시할 때 쓴다(spec_헤딩_추출 ② §7 — 갈래 둘 이상이 30줄을 넘는 레벨에서만 부른다)."""
    server = _server()
    s = server._sess(doc_id)
    with s.lock:
        ov = server._outline_ov(s) if s.fmt == "hwpx" else None
        if ov is None:
            return {"off": True, "rev": s.rev, "slots": {}}
        keys = [[k, outline_match.LABELS.get(k, k)] for k in outline_match.KEYS]
        if tpl is not None and level is not None:
            if str(tpl) not in ov["templates"]:
                raise HTTPException(404, "그 템플릿이 없습니다")
            v = outline_match.variants(s.doc, ov, str(tpl), level, full=True)
            return {"rev": s.rev, "full": True, "slots": {str(tpl): {str(level): v}} if v["total"] else {}, "keys": keys}
        return {"rev": s.rev, "slots": outline_match.all_variants(s.doc, ov),
                "keys": [[k, outline_match.LABELS.get(k, k)] for k in outline_match.KEYS]}  # 비교 값의 차례·이름(화면 「서식 비교」 표의 열)


@router.put("/api/docs/{doc_id}/outline/slots/{tpl}/{level}/rep")
def set_rep(doc_id: str, tpl: str, level: int, body: dict = Body(...)):
    """{para} — 그 레벨의 대표를 그 줄로(오버레이 슬롯의 rep · 동결 접두·모양). 문서는 안 바뀐다 · 실행 취소 1(기록 `outlineRep`).
    → {slot: 그 레벨의 서식 갈래, outline(GET /outline 꼴), …편집 상태}. 400 그 레벨 줄이 아님 · 404 그런 레벨 없음 · 409 2단계 없음."""
    server = _server()
    pid = body.get("para")
    if not isinstance(pid, str) or not pid:
        raise HTTPException(400, "para(문단 id)가 필요합니다")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)
        if outline_edit._slot(ov, tpl, level) is None:
            raise HTTPException(404, "그런 템플릿 레벨이 없습니다")

        def change():
            was = (outline_edit._slot(ov, tpl, level) or {}).get("rep")
            outline_match.set_rep(s.doc, ov, tpl, level, pid)
            return {"tpl": ov["templates"][str(tpl)]["no"], "level": level, "rep": pid, "was": was}
        out, ok = _model_only(server, s, "outlineRep", {"tpl": tpl, "level": level, "para": pid}, change)
        if not ok:
            return out
        return {"slot": outline_match.variants(s.doc, s.outline, tpl, level), "outline": outline_pos.view(s.doc, s.outline), **_state(s)}


@router.post("/api/docs/{doc_id}/outline/slots/{tpl}/{level}/match")
def match(doc_id: str, tpl: str, level: int, body: dict = Body(default={})):
    """{paras?, like?} — 그 레벨에서 대표와 비교 값이 다른 줄(paras 를 주면 그 가운데 그 레벨 줄만 · like(그 레벨 줄 id)를 주면 그 줄과 서식이 같은 갈래만 — 30줄 넘는 갈래도)을
    대표의 지금 모양으로(접두 · 문단 모양 · 레터·본문 바탕 글자 모양).
    구조 편집 트랜잭션 하나(기록 `outlineMatch` · 실행 취소 1 · 닿은 문단 검사). 응답 = 다른 구조 편집과 같은 꼴 + changed · outline{lines}.
    맞출 줄이 없으면 편집을 열지 않고 {changed: [], nothing: true, …편집 상태}. 400 대표가 문서에 없음 · 404 그런 레벨 없음 · 409 2단계 없음.
    **확정 서식으로**(② §8-8 — 기본): 대표 줄에 레터 뒤 묶음 빈칸 · 자리 규칙(둘째 줄 = 글 시작)을 걸고, 맞춘 줄과 대표 갈래의 줄을 그 서식으로(`outline_conform.settle`) —
    답의 `placed` = 대표에 맞춘 줄이 아니라 그것만 걸린 줄. `place: false` 면 걸지 않는다(대표의 지금 모양 그대로 복사 — 전의 동작)."""
    server = _server()
    paras, like, place = body.get("paras"), body.get("like"), _place_on(body)
    if paras is not None and (not isinstance(paras, list) or not all(isinstance(p, str) for p in paras)):
        raise HTTPException(400, "paras 는 문단 id 목록")
    if like is not None and (not isinstance(like, str) or not like):
        raise HTTPException(400, "like 는 문단 id")
    s0 = server._sess(doc_id)
    _hwpx(s0)
    with s0.lock:
        ov = _ov(server, s0)
        if outline_edit._slot(ov, tpl, level) is None:
            raise HTTPException(404, "그런 템플릿 레벨이 없습니다")
        try:
            pre = outline_match.match_targets(s0.doc, ov, tpl, level, paras, like)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not pre and not (place and _pend_level(s0.doc, ov, tpl, level)):
            return {"changed": [], "nothing": True, **_state(s0)}
    extra, changed, placed = {}, [], []

    def make(s):
        ov2 = _ov(server, s)
        try:
            ids = outline_match.match_targets(s.doc, ov2, tpl, level, paras, like)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        pend = _pend_level(s.doc, ov2, tpl, level) if place else []  # 대표 갈래의 줄 가운데 확정 서식(묶음 빈칸 · 자리 규칙)이 아직 안 걸린 줄 — 같이 맞춘다(② §8-8)
        hit = list(dict.fromkeys(ids + pend))
        if not hit:
            raise HTTPException(409, "그 사이에 문서가 바뀌어 맞출 줄이 없습니다 — 다시 읽어 주세요")
        sl = outline_edit._slot(ov2, tpl, level)

        def run():
            # 줄을 확정 서식으로 바꾸는 길은 하나다(outline_conform.settle — ② §8-8): 대표에 묶음 빈칸·자리 규칙을 걸어 확정 서식을 정하고, 고른 줄(ids)과 대표 갈래의 줄을 그 서식으로
            if place:
                done = outline_conform.settle(s.doc, ov2, tpl, level, ids, outline_pos.Measure(s.doc))
            else:  # 확정 서식을 걸지 않는다 — 대표의 지금 모양 그대로(사람이 정한 자리 규칙만 다시)
                sh = outline_match.rep_shape(s.doc, ov2, sl["rep"])
                sl.update(prefix=sh["prefix"], letter=sh["tok"], attrs=sh["attrs"], bodyChar=sh["body"])
                meas = outline_pos.Measure(s.doc) if (sl.get("pos") or {}).get("set") else None
                for pid in ids:
                    outline_match.match_one(s.doc, ov2, pid, sh)
                    if meas is not None:
                        try:
                            outline_pos.align(s.doc, ov2, pid, full=True, measure=meas)
                        except ValueError:
                            pass
                done = ids
            changed.extend(i for i in hit if i in set(done))
            placed.extend(i for i in changed if i not in set(ids))  # 대표에 맞춘 줄(ids)이 아니라 확정 서식만 건 줄(대표 · 대표 갈래)
            extra.update({"lines": {pid: outline_edit.line_view(ov2["lines"][pid]) for pid in hit}, "removed": [], "fmts": outline_match.labels_now(s.doc, ov2, hit)})  # fmts = 그 레벨 줄들의 지금 서식 라벨(맞춘 줄은 대표의 라벨이 됐다)
            return {"hosts": [s.doc._ids[i] for i in hit], "formatted": set(changed), "struct": set(), "origin": {}, "anchor": hit[0],
                    "log": {"tpl": ov2["templates"][str(tpl)]["no"], "level": level, "rep": sl["rep"], "changed": len(ids), "placed": len(changed) - len(ids)}}
        return [s.doc._ids[i] for i in hit], run
    out = server._edit(doc_id, make, "outlineMatch", {"tpl": tpl, "level": level, "paras": paras, "like": like})
    if isinstance(out, dict):
        out["outline"] = extra
        out["changed"] = changed
        out["placed"] = placed
    return out


def _place_on(body):
    """요청 몸의 `place`(확정 서식을 거는가 — ② §8-8) — 없으면 참(기본). 불리언이 아니면 400."""
    v = body.get("place")
    if v is not None and not isinstance(v, bool):
        raise HTTPException(400, "place 는 true · false")
    return v is not False


def _pend_level(doc, ov, tpl, level):
    """그 레벨에서 확정 서식(② §8-8 — 레터 뒤 묶음 빈칸 · 자리 규칙)이 아직 안 걸린 대표 갈래의 줄."""
    return [p for p in outline_conform.pending(doc, ov, {str(tpl)}) if int(ov["lines"][p]["level"]) == int(level)]


def _settle_ids(ov, settle):
    """확정 서식을 걸 템플릿 id — "all" = 모든 템플릿 · 목록 = 그 템플릿과 거기서 뗀 서식 종속 템플릿(「T1L3a」) · None = 없음."""
    if settle is None:
        return []
    if settle == "all":
        return list(ov["templates"])
    want = {str(t) for t in settle}
    return [tid for tid, t in ov["templates"].items() if tid in want or str((t.get("variant") or {}).get("of")) in want]


def _want(levels):
    """몸의 levels([{level, rep?, likes?, splits?}] | None) → [(level, rep, likes, cuts[(likes, rep, sfx, match)])] | None(없음 = 줄이 있는 모든 레벨) — 꼴이 틀리면 400."""
    if levels is None:
        return None
    if not isinstance(levels, list) or not all(isinstance(x, dict) for x in levels):
        raise HTTPException(400, "levels 는 [{level, rep?, likes?, splits?}] 목록")
    want = []
    for x in levels:
        lv, rep, likes, splits = x.get("level"), x.get("rep"), x.get("likes"), x.get("splits")
        if isinstance(lv, bool) or not isinstance(lv, int) or lv < 1:
            raise HTTPException(400, "level(1 이상의 정수)이 필요합니다")
        if rep is not None and (not isinstance(rep, str) or not rep):
            raise HTTPException(400, "rep 는 문단 id")
        if likes is not None and (not isinstance(likes, list) or not all(isinstance(p, str) and p for p in likes)):
            raise HTTPException(400, "likes 는 문단 id 목록")
        if splits is not None and (not isinstance(splits, list) or not all(isinstance(sp, dict) for sp in splits)):
            raise HTTPException(400, "splits 는 [{likes, rep?, sfx?, match?}] 목록")
        cuts = []
        for sp in splits or []:
            sl_, sr, sx = sp.get("likes"), sp.get("rep"), sp.get("sfx")
            if not isinstance(sl_, list) or not sl_ or not all(isinstance(p, str) and p for p in sl_):
                raise HTTPException(400, "splits[].likes 는 비어 있지 않은 문단 id 목록")
            if sr is not None and (not isinstance(sr, str) or not sr):
                raise HTTPException(400, "splits[].rep 는 문단 id")
            if sx is not None and not (isinstance(sx, str) and len(sx) == 1 and sx in outline_match.SFX):
                raise HTTPException(400, "splits[].sfx 는 a~z 한 글자")
            cuts.append((sl_, sr or sl_[0], sx, sp.get("match", True) is not False))
        if len({sx for _, _, sx, _ in cuts if sx}) != len([1 for _, _, sx, _ in cuts if sx]):
            raise HTTPException(400, "같은 글자(sfx)가 두 번 있습니다")
        want.append((lv, rep, likes, cuts))
    if len({lv for lv, _, _, _ in want}) != len(want):
        raise HTTPException(400, "같은 레벨이 두 번 있습니다")
    return want


def _plan_tpl(s, ov, tpl, want):
    """템플릿 하나에서 바꿀 것 → [(level, 대표, 대표 바뀜, [바꿀 줄], [뗄 것 {paras, rep, sfx, ids(뗀 뒤 새 대표에 맞출 줄)}])] — 바꿀 것이 있는 레벨만.
    want = _want 의 답(None 이면 줄이 있는 모든 레벨의 대표와 다른 줄 모두 — 대표가 없는 레벨은 건너뛴다)."""
    todo = want if want is not None else [(int(lv), None, None, []) for lv in sorted(ov["templates"][str(tpl)].get("slots", {}), key=int)
                                          if outline_match.slot_ids(ov, tpl, lv)]
    out = []
    for lv, rep, likes, cuts in todo:
        sl = outline_edit._slot(ov, tpl, lv)
        if sl is None:
            raise HTTPException(404, f"L{lv} 이 없습니다")
        try:
            if want is None and (not sl.get("rep") or sl["rep"] not in ov["lines"] or outline_match.lone_value(s.doc, ov, sl["rep"])):
                continue  # 「모든 레벨」 — 대표가 없는 레벨 · 대표가 값 칸인 옛 레벨(그 모양으로 글 줄을 맞추지 않는다)은 건너뛴다(고른 레벨이면 400)
            r, ids = outline_match.match_set(s.doc, ov, tpl, lv, rep, likes)
            cut, gone = [], set()
            for c_likes, c_rep, c_sfx, c_match in cuts:  # 서식 종속 템플릿으로 뗄 갈래(② §8-5) — 바꾸기 전에 다 검사한다
                paras = outline_match.split_targets(s.doc, ov, tpl, lv, c_likes)
                if c_rep not in paras:
                    raise ValueError("splits[].rep 는 그 갈래의 줄이어야 합니다")
                if gone & set(paras):
                    raise ValueError(f"L{lv} 의 같은 갈래를 두 템플릿으로 뗄 수는 없습니다")
                why = outline_match.split_block(ov, tpl, lv, paras, rep=r)
                if why:
                    raise ValueError(why)
                if c_sfx and outline_match.var_id(tpl, lv, c_sfx) in ov["templates"]:
                    raise ValueError(f"T{ov['templates'][str(tpl)]['no']}L{lv}{c_sfx} 는 이미 있습니다 — 계획을 다시 받으세요")
                base = outline_match.look(s.doc, ov, c_rep)
                cut.append({"paras": paras, "rep": c_rep, "sfx": c_sfx,
                            "ids": [p for p in paras if p != c_rep and not outline_match.same(outline_match.look(s.doc, ov, p), base)] if c_match else []})
                gone |= set(paras)
            if likes is not None and gone & set(ids):
                raise ValueError(f"L{lv} 의 같은 갈래를 맞추면서 뗄 수는 없습니다")
            ids = [i for i in ids if i not in gone]
            used = outline_match.used_sfx(ov, tpl, lv) | {c["sfx"] for c in cut if c["sfx"]}
            for c in cut:  # 글자를 안 준 것은 여기서 정해 둔다(빈 글자 가운데 첫 것 — 뒤의 것이 준 글자와 안 겹치게)
                if not c["sfx"]:
                    c["sfx"] = next((ch for ch in outline_match.SFX if ch not in used), None)
                    if not c["sfx"]:
                        raise ValueError(f"L{lv} 에서 뗄 수 있는 템플릿 수({len(outline_match.SFX)}개)를 다 썼습니다")
                    used.add(c["sfx"])
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if ids or cut or r != sl.get("rep"):
            out.append((lv, r, r != sl.get("rep"), ids, cut))
    return out


def _plan(s, ov, jobs, rev):
    """jobs = [(tpl, want | None)] → [(tpl, _plan_tpl 의 답)] — 바꿀 것이 있는 템플릿만. 404 없는 템플릿 · 409 문서가 바뀜(rev). 템플릿이 여럿이면 400·404 의 글 앞에 「T3 — 」."""
    for tpl, _ in jobs:
        if str(tpl) not in ov["templates"]:
            raise HTTPException(404, "그런 템플릿이 없습니다")
    if rev is not None and rev != s.rev:
        raise HTTPException(409, "그 사이에 문서가 바뀌었습니다 — 서식 갈래를 다시 읽은 뒤 맞추세요")
    out = []
    for tpl, want in jobs:
        try:
            rows = _plan_tpl(s, ov, tpl, want)
        except HTTPException as e:
            if len(jobs) > 1:
                raise HTTPException(e.status_code, f"T{ov['templates'][str(tpl)]['no']} — {e.detail}") from e
            raise
        if rows:
            out.append((tpl, rows))
    return out


def _cut_now(s, ov, tpl, lv, c, done_cuts):
    """뗄 것 하나를 지금 뗀다(오버레이) → (새 템플릿 대표의 모양 — 뗀 줄을 맞출 때 쓴다, split 의 답)."""
    shape = outline_match.rep_shape(s.doc, ov, c["rep"])
    got = outline_match.split(ov, tpl, lv, c["paras"], rep=c["rep"], shape=shape, sfx=c["sfx"])
    done_cuts.append({"level": lv, "id": got["id"], "no": got["no"], "moved": len(got["moved"]), "changed": len(c["ids"])})
    return shape, got


def _in_slot(ov, pid, tpl, lv):
    x = ov["lines"].get(pid) or {}
    return x.get("tpl") == str(tpl) and int(x.get("level", -1)) == int(lv)


def _settle_rep(s, ov, tpl, lv, sl, r, sh, want):
    """레벨 하나를 맞춘 뒤 슬롯의 대표·동결 모양을 정한다(② §8-2 「계획의 대표로」). 계획의 대표 줄 r 이 그 레벨에 그대로면 그 줄이 대표이고 동결 모양 = 그 모양(sh).
    r 이 윗레벨 떼기로 떠났으면 — 남은 줄 가운데 **지금 비교 값이 계획의 대표와 같은**(want) 첫 줄이 새 대표(사람이 정한 대표 표시는 지운다).
    그런 줄이 하나도 없으면(맞춘 줄까지 다 떠남) 슬롯을 건드리지 않는다 — 떼기가 정해 둔 대표·동결 모양 그대로(다른 모양의 줄을 대표로 둔 채 동결 모양만 바꾸면 다음 맞추기가 그 줄 기준이 된다)."""
    if sl.get("rep") != r or not _in_slot(ov, r, tpl, lv):
        order = outline_match._order(s.doc)
        left = []
        for p in sorted(outline_match.slot_ids(ov, tpl, lv), key=lambda q: order.get(q, 1 << 30)):
            try:
                if outline_match._alive(s.doc, p) and outline_match.same(outline_match.look(s.doc, ov, p), want):
                    left.append(p)
            except (KeyError, ValueError):
                continue
        if not left:
            return
        sl["rep"] = left[0]
        sl.pop("repSet", None)
    sl.update(prefix=sh["prefix"], letter=sh["tok"], attrs=sh["attrs"], bodyChar=sh["body"])  # 새 줄도 대표의 지금 모양으로


def _marks(ov, marks):
    """반영한 서식 정리 계획의 표를 개요 오버레이에(ov["agent"][템플릿] = 그 계획의 at) — 「반영함」 은 이 표가 그 계획의 것일 때만이다(analysis.plan_applied · spec_hwpx_웹편집 ② §8-4).
    **반영과 같은 트랜잭션 · 같은 잠금 안에서** 적는다: 반영 직전의 실행 취소 묶음에는 없고 그 뒤의 묶음에는 있어, 반영을 되돌리면 표도 사라진다."""
    if marks and isinstance(ov, dict):
        ov.setdefault("agent", {}).update({str(k): v for k, v in marks.items()})


def _plan_shapes(s, ov, rows):
    """계획의 대표 모양(rep_shape) · 비교 값(look)을 레벨마다 → {레벨: (모양, 비교 값)} — 맞출 줄이 있거나 대표를 바꾸는 레벨만. **그 템플릿을 바꾸기 전에** 잡는다:
    윗레벨 떼기가 아랫레벨의 대표 줄을 새 템플릿으로 데려가면 슬롯의 대표가 남은 줄로 바뀌는데(outline_match.split), 그때 그 바뀐 대표로 맞추면 계획과 다른 모양이 된다
    (2026-11-16 astra — spec_hwpx_웹편집 ② §8-2 「계획의 대표로」). 문서 편집 길 · 오버레이만 바꾸는 길 · 그 사본(_pend_after)이 같이 쓴다."""
    return {lv: (outline_match.rep_shape(s.doc, ov, r), outline_match.look(s.doc, ov, r)) for lv, r, rep_changed, ids, _ in rows if ids or rep_changed}


def _take_rep(s, ov, tpl, lv, r, rep_changed, by=None):
    """대표를 바꾸는 레벨에서 계획의 대표 줄 r 을 그 레벨의 대표로 — 윗레벨 떼기가 그 줄을 데려갔으면 삼지 않는다(그 레벨의 줄이 아니다 — 전에는 400 으로 계획 전체가 막혔다:
    그때는 _settle_rep 이 남은 줄에서 뽑는다). by = "agent" 면 서식 정리 계획이 정한 대표(사람이 정한 대표처럼 잠그지 않는다 — outline_match.set_rep)."""
    if rep_changed and _in_slot(ov, r, tpl, lv):
        outline_match.set_rep(s.doc, ov, tpl, lv, r, by=by)


def _model_run(s, ov, pre, per, by=None):
    """문서를 안 바꾸는 반영(대표 바꿈 · 떼기)을 오버레이 ov 에 건다 — per 에 템플릿마다 한 것을 싣는다(pre = _plan 의 답).
    apply_templates 의 「오버레이만」 길과, 그 길로 가도 되는지 사본에 걸어 보는 _pend_after 가 같이 쓴다(같은 걸음이어야 미리 본 것과 실제가 같다).
    대표 결정과 동결 모양은 문서 편집 길과 **같은 함수**로 한다(_plan_shapes → _take_rep → _settle_rep): 윗레벨 떼기가 계획의 대표를 데려가면 남은 줄 가운데 그 대표와 서식이 같은 줄이 대표가 되고
    동결 모양은 계획의 대표 모양이다 — 전에는 이 길만 그것을 건너뛰어, 같은 계획이 다른 레벨에 안 걸린 줄이 있느냐에 따라 다른 대표를 냈다(2026-11-17 astra)."""
    for tpl, rows in pre:
        one = {"tpl": str(tpl), "no": ov["templates"][str(tpl)]["no"], "levels": [], "splits": [], "changed": []}
        shapes = _plan_shapes(s, ov, rows)  # 이 템플릿을 바꾸기 전에
        for lv, r, rep_changed, _, cut in rows:
            sl = outline_edit._slot(ov, tpl, lv)
            _take_rep(s, ov, tpl, lv, r, rep_changed, by)
            if rep_changed:
                _settle_rep(s, ov, tpl, lv, sl, r, *shapes[lv])
            one["levels"].append({"level": lv, "rep": sl["rep"], "repChanged": rep_changed, "changed": 0})  # rep = 실제로 대표가 된 줄(문서 편집 길의 답과 같게 — 떠난 줄이 아니다)
            for c in cut:
                _cut_now(s, ov, tpl, lv, c, one["splits"])
        per.append(one)


def _pend_after(s, ov, pre, rel, settle):
    """대표 바꿈 · 떼기(rel 이면 확실한 종속도)를 **건 뒤의** 대표·템플릿으로 볼 때 확정 서식(② §8-8)이 아직 안 걸린 줄 → [줄 id]. 오버레이 **사본**에 걸어 보고 센다 — 문서 · 오버레이는 그대로.
    문서를 맞출 줄이 없는 반영(떼기만 · 대표만 · 종속만)이어도 새 대표 · 새 템플릿의 대표와 그 갈래는 같은 반영에서 확정 서식이 돼야 한다: 바꾸기 **전의** 대표로만 세면(outline_conform.pending)
    그 줄들이 빠져 오버레이만 바꾸는 길로 가고, 새 서식 종속 템플릿의 대표(대표가 아니던 갈래의 줄)가 한 번도 안 걸린 채 남았다(2026-11-16 astra).
    사본에서 실패하면 빈 목록 — 실제 반영이 같은 까닭으로 400 을 낸다."""
    sim = copy.deepcopy(ov)
    try:
        _model_run(s, sim, pre, [])
        if rel:
            outline_match.auto_merge(sim)
    except (KeyError, ValueError):
        return []
    return outline_conform.pending(s.doc, sim, set(_settle_ids(sim, settle)))


def apply_templates(server, doc_id, jobs, *, rev=None, op="outlineTplMatch", req=None, log=None, marks=None, relations=None, settle=None, by=None):
    """템플릿 하나 또는 여럿의 맞추기 · 떼기를 **트랜잭션 하나**(실행 취소 1)로 — 템플릿 단위 맞추기(아래 match_template)와 받아 둔 서식 정리 계획을 한 번에 반영하는 끝점
    (tpl_agent_api.apply_plans)이 같이 쓴다. jobs = [(tpl, _want 의 답 | None)] · rev = 계획을 세운 문서 차례(지금과 다르면 409) · log(per, doc) → 기록에 적을 것(doc = 문서가 바뀌었나).
    → (kind, per, 답): kind "nothing"(바꿀 것 없음 — 답 = {changed: [], nothing, …편집 상태}) · "model"(대표만 · 떼기만 — 문서는 그대로, 오버레이만) · "edit"(문서가 바뀜 — 답이 dict 가 아니면 422 응답).
    per = [{tpl, no, levels[{level, rep, repChanged, changed(수)}], splits[{level, id, no, moved, changed}], changed[줄 id]}] — 바꾼 것이 있는 템플릿만, jobs 차례.
    레벨마다 대표 바꿈 → 맞추기(뗄 줄은 빼고) → 떼기 → 뗀 줄 맞추기. 도중의 오류는 오버레이를 처음 것으로 되돌린다(_ov_guard).
    marks = {템플릿 id: 계획의 at} — 서식 정리 계획을 반영하는 것이면 그 표를 같은 트랜잭션 안에서 오버레이에 적는다(_marks). 바꿀 것이 없을 때도 같은 잠금 안에서.
    settle = 확정 서식을 걸 템플릿("all" | [템플릿 id] | None — ② §8-8): 맞추기·떼기 **뒤에** 그 템플릿들의 모든 레벨에서 대표와 그 갈래의 줄에 레터 뒤 묶음 빈칸·자리 규칙을 건다
    (`outline_conform.settle_templates` — 같은 트랜잭션). 맞출 갈래가 없어도 그것만으로 문서가 바뀔 수 있다. 답의 `placed` = 그것으로만 바뀐 줄 id(맞춘 줄은 changed 에).
    방금 맞춘 줄은 대표 갈래에 다시 들었는지와 무관하게 묶음 빈칸·자리 규칙을 직접 건다(접두 폭이 대표와 다른 줄). 대표만 · 떼기만 · 종속만인 반영도 **바꾼 뒤의** 대표·템플릿으로 안 걸린 줄을 세어(_pend_after),
    있으면 문서 편집 트랜잭션으로 건다(kind "edit" — 답의 `reps` = 대표를 바꾼 레벨 수는 두 길 모두에).
    by = 대표를 바꾸는 쪽("agent" = 서식 정리 계획 — 그 대표는 사람이 정한 대표처럼 잠기지 않는다 · None = 사람: 잠긴다 — outline_match.set_rep · rep_origin)."""
    s0 = server._sess(doc_id)
    _hwpx(s0)
    with s0.lock:
        ov0 = _ov(server, s0)
        pre = _plan(s0, ov0, jobs, rev)
        pend0 = outline_conform.pending(s0.doc, ov0, set(_settle_ids(ov0, settle))) if settle is not None else []
        # 문서를 맞출 줄이 없는 반영(대표만 · 떼기만 · 종속만)도 새 대표 · 새 템플릿의 대표와 그 갈래는 **같은 반영에서** 확정 서식으로 — 바꾼 뒤의 대표로 다시 센다(_pend_after: ② §8-8).
        # 그런 줄이 있으면 아래 문서 편집 트랜잭션으로 간다(실행 취소는 그대로 1) — 없으면 전처럼 오버레이만
        if settle is not None and not pend0 and (pre or relations is not None) and not any(ids or any(c["ids"] for c in cut) for _, rows in pre for _, _, _, ids, cut in rows):
            pend0 = _pend_after(s0, ov0, pre, relations is not None, settle)
        if pend0:
            pass  # 확정 서식이 안 걸린 줄이 있다 — 아래 문서 편집 트랜잭션으로(맞출 갈래가 없어도)
        elif not pre:
            if marks:  # 바꿀 것이 없는 계획 — 트랜잭션은 없지만 표는 남긴다(문서 차례가 그대로라 다음 저장에 들어가게 표시)
                _marks(s0.outline, marks)
                s0.saved_rev = -1
            return "nothing", [], {"changed": [], "nothing": True, **_state(s0)}
        elif not any(ids or any(c["ids"] for c in cut) for _, rows in pre for _, _, _, ids, cut in rows):  # 대표만 바뀜 · 떼기만 — 문서는 그대로(오버레이만: 실행 취소 1)
            ov = s0.outline
            per0 = []

            def change():
                with _ov_guard(ov, relations is not None or any(cut for _, rows in pre for *_, cut in rows)):
                    _model_run(s0, ov, pre, per0, by)
                    _marks(ov, marks)
                    if relations is not None:  # 문서가 안 바뀌는 반영(대표만 · 떼기만)에서도 확실한 종속을 같은 트랜잭션에
                        relations.extend(outline_match.auto_merge(ov))
                return log(per0, False)
            got, ok = _model_only(server, s0, op, req, change)
            if not ok:
                return "edit", per0, got
            return "model", per0, {"changed": [], "reps": sum(1 for _, rows in pre for x in rows if x[2]), "outline": outline_pos.view(s0.doc, s0.outline), **_state(s0)}
    extra, per, changed, placed = {}, [], [], []

    def make(s):
        ov2 = _ov(server, s)
        todo = _plan(s, ov2, jobs, rev)
        ids_all = [i for _, rows in todo for _, _, _, ids, cut in rows for i in ids + [p for c in cut for p in c["ids"]]]
        # 확정 서식(② §8-8)이 닿을 줄: 맞추기·대표 바꿈·떼기가 있으면 어느 줄이 대표 갈래가 될지 미리 알 수 없다 — 그 템플릿들의 줄을 모두 「닿는 문단」 으로 잡는다(안 바뀐 줄은 고친 문단에 안 든다 — formatted 는 바뀐 줄만)
        # (맞출 것도 종속도 없으면 대표 갈래가 그대로라 안 걸린 줄을 정확히 안다 — 그 줄만)
        tids = _settle_ids(ov2, settle)
        wide = [] if settle is None else outline_conform.lines_of(s.doc, ov2, tids) if todo or relations is not None else outline_conform.pending(s.doc, ov2, set(tids))
        hit = list(dict.fromkeys(ids_all + wide))
        if not hit:
            raise HTTPException(409, "그 사이에 문서가 바뀌어 맞출 줄이 없습니다 — 다시 읽어 주세요")

        def run():
            moved = []
            with _ov_guard(ov2, relations is not None or any(cut for _, rows in todo for *_, cut in rows)):
                for tpl, rows in todo:
                    one = {"tpl": str(tpl), "no": ov2["templates"][str(tpl)]["no"], "levels": [], "splits": [], "changed": []}
                    # 계획의 대표 모양은 **이 템플릿을 바꾸기 전에** 잡는다(_plan_shapes) — 대표 결정(_take_rep → 맞추기 → _settle_rep)은 오버레이만 바꾸는 길(_model_run)과 같은 함수다
                    shapes = _plan_shapes(s, ov2, rows)
                    for lv, r, rep_changed, ids, cut in rows:
                        sl = outline_edit._slot(ov2, tpl, lv)
                        _take_rep(s, ov2, tpl, lv, r, rep_changed, by)
                        if ids or rep_changed:
                            sh, want = shapes[lv]
                            meas = outline_pos.Measure(s.doc) if (sl.get("pos") or {}).get("set") else None
                            for pid in ids:
                                outline_match.match_one(s.doc, ov2, pid, sh)
                                if meas is not None:  # 사람이 정한 자리 규칙(② §8-1)도 다시
                                    try:
                                        outline_pos.align(s.doc, ov2, pid, full=True, measure=meas)
                                    except ValueError:
                                        pass
                                one["changed"].append(pid)
                            _settle_rep(s, ov2, tpl, lv, sl, r, sh, want)
                        one["levels"].append({"level": lv, "rep": sl["rep"], "repChanged": rep_changed, "changed": len(ids)})
                        for c in cut:  # 서식 종속 템플릿으로 떼고(② §8-5), 뗀 줄 가운데 새 대표와 다른 줄은 그 대표 모양으로
                            shape, got = _cut_now(s, ov2, tpl, lv, c, one["splits"])
                            moved.extend(got["moved"])
                            for pid in c["ids"]:
                                outline_match.match_one(s.doc, ov2, pid, shape)
                                one["changed"].append(pid)
                    per.append(one)
                _marks(ov2, marks)
                if relations is not None:  # 확실한 종속(한 자리에만 매달린 가지 템플릿 → 그 자리의 템플릿 아래 — ② §8-2 「종속 제안」)을 같은 트랜잭션에: 줄을 제 대표에 맞춘 **뒤에** 옮긴다
                    relations.extend(outline_match.auto_merge(ov2))
                    moved.extend(i for m in relations for i in m["ids"])
                if settle is not None:  # 확정 서식으로(② §8-8) — 맞추고 · 떼고 · 종속을 건 **뒤의** 템플릿·대표로: 레벨마다 대표와 그 갈래의 줄(방금 맞춘 줄 포함)에 레터 뒤 묶음 빈칸 · 자리 규칙
                    pm = outline_pos.Measure(s.doc)
                    got = set(outline_conform.settle_templates(s.doc, ov2, _settle_ids(ov2, settle), pm))
                    done = {i for one in per for i in one["changed"]}
                    # 방금 맞춘 줄(뗀 뒤 새 대표에 맞춘 줄 포함)은 대표 갈래를 다시 찾는 것(settle 의 _mates)에 맡기지 않고 **직접** 건다 — 대표가 이미 확정 서식이면 맞춘 줄은 대표의 내어쓰기 값을
                    # 그대로 받는데, 접두 폭이 대표와 다른 줄(제 번호 「10.」 · 제 자간을 지킨 줄)은 둘째 줄이 제 글 시작이 아니라서 대표 갈래에서 빠져 안 걸렸다(2026-11-16 astra).
                    # 다시 맞추지는 않는다(계획의 대표 모양으로 이미 맞췄다 — 「계획의 대표로」) — 묶음 빈칸 · 자리 규칙만, 그 줄이 **지금 든** 템플릿·레벨의 규칙으로(떼기 · 종속 뒤의 소속)
                    for pid in dict.fromkeys(i for one in per for i in one["changed"]):
                        try:
                            outline_conform.place(s.doc, ov2, pid, pm)
                        except (KeyError, ValueError):
                            continue
                    placed.extend(i for i in hit if i in got and i not in done)
                    placed.extend(i for i in got if i not in done and i not in set(hit))  # 닿는 문단으로 미리 못 잡은 줄(없어야 한다 — 있으면 그 줄도 고친 문단으로)
            changed.extend(dict.fromkeys([i for one in per for i in one["changed"]] + placed))
            seen = list(dict.fromkeys(hit + placed))
            extra.update({"lines": {pid: outline_edit.line_view(ov2["lines"][pid]) for pid in dict.fromkeys(seen + moved) if pid in ov2["lines"]}, "removed": [], "fmts": outline_match.labels_now(s.doc, ov2, seen)})
            return {"hosts": [s.doc._ids[i] for i in seen], "formatted": set(changed), "struct": set(), "origin": {}, "anchor": seen[0],
                    "log": {**log(per, True), **({"placed": len(placed)} if placed else {})}}
        return [s.doc._ids[i] for i in hit], run
    out = server._edit(doc_id, make, op, req)
    if isinstance(out, dict):
        out["outline"] = extra
        out["changed"] = changed
        out["placed"] = placed
        out["reps"] = sum(1 for one in per for x in one["levels"] if x["repChanged"])  # 대표를 바꾼 레벨 수 — 문서를 안 바꾸는 길("model")의 답과 같은 이름
    return "edit", per, out


@router.post("/api/docs/{doc_id}/outline/templates/{tpl}/match")
def match_template(doc_id: str, tpl: str, body: dict = Body(default={})):
    """템플릿 단위 맞추기 — 한 템플릿의 여러 레벨을 **트랜잭션 하나**(실행 취소 1 · 기록 `outlineTplMatch`)로 대표 모양에 맞춘다(spec_hwpx_웹편집 ② §8-2 「템플릿 맞추기」 ·
    §8-4 정리 에이전트의 적용). {levels?: [{level, rep?(그 레벨 줄 id — 대표를 이 줄로 바꾼 뒤 맞춤), likes?([그 레벨 줄 id] — 그 줄들과 서식이 같은 갈래만 · 없으면 대표와 다른 줄 모두)}],
    rev?(계획을 세운 문서 차례 — 지금과 다르면 409), by?("agent" — 정리 에이전트의 계획을 적용: 기록 + 그 계획을 「반영함」 으로 · 그 계획이 바꾼 대표는 사람이 정한 대표처럼 잠기지 않는다 — by 가 없으면 사람이 정한 대표),plan?(by agent 일 때 화면이 가진 계획의 at — 남아 있는 계획이 그것일 때만 「반영함」 으로 적는다)}. levels 가 없으면 줄이 있는 모든 레벨의 대표와 다른 줄 모두.
    → 다른 구조 편집과 같은 꼴 + changed[줄 id] · levels[{level, rep, repChanged, changed(수)}] · outline{lines}. 바꿀 것이 없으면 {changed: [], nothing: true, …편집 상태}.
    대표만 바뀌면(맞출 줄 없음) 문서는 안 바뀌고 {changed: [], reps, outline(GET /outline 꼴), …편집 상태}. 400 대표·갈래 줄이 그 레벨 줄이 아님 · 404 템플릿·레벨 없음 · 409 2단계 없음·문서가 바뀜.
    **떼기도 같이**(② §8-5): levels[].splits = [{likes([그 레벨 줄 id] — 그 줄들과 서식이 같은 갈래를 서식 종속 템플릿 「T1L3a」 로), rep?(새 템플릿의 대표 줄 — 없으면 likes 의 첫 줄),
    sfx?(글자), match?(기본 true — 뗀 줄 가운데 새 대표와 다른 줄을 그 대표 모양으로)}] — 그 레벨에서 대표 바꿈 → 맞추기(뗄 줄은 빼고) → 떼기 → 뗀 줄 맞추기를 같은 트랜잭션으로.
    응답에 splits[{level, id, no, moved, changed}]. 문서가 안 바뀌는 조합(떼기만 · 대표만)이면 오버레이만 — 다만 확정 서식을 거는 요청(정리 에이전트의 계획 적용 by "agent" 등 — 아래 fit)이면
    새 대표 · 새 템플릿의 대표와 그 갈래에 묶음 빈칸·자리 규칙을 같은 트랜잭션에서 건다(그런 줄이 있으면 문서가 바뀐다 — 답의 placed). 같은 갈래가 likes 와 splits 에 함께 · 대표 갈래를 뗌 · 번호형 레벨의 형제 일부는 400."""
    server = _server()
    levels, rev, by = body.get("levels"), body.get("rev"), body.get("by")
    want = _want(levels)

    def log(per, doc):
        if not per:  # 맞출 갈래 없이 확정 서식(묶음 빈칸 · 자리 규칙 — ② §8-8)만 건 것
            return {"tpl": tpl, "levels": [], "by": by}
        one = per[0]
        return {"tpl": one["no"], "levels": list(one["levels"]), **({"changed": len(one["changed"])} if doc else {}), "by": by, **({"splits": list(one["splits"])} if one["splits"] else {})}
    at = None
    if by == "agent" and rev is not None:  # 정리 에이전트의 계획을 적용함 — 어느 계획인지(그 계획의 at)를 반영 전에 잡아 둔다: 표는 반영과 같은 트랜잭션에서 적는다(② §8-4 「반영함은 문서에 남아 있을 때만」)
        from app import tpl_agent_api
        at = tpl_agent_api.plan_at(server, server._sess(doc_id), tpl, rev, body.get("plan"))
    # 맞춘 뒤 그 템플릿의 줄을 확정 서식으로(② §8-8) — 맞추기를 청한 것일 때만: 모든 레벨(levels 없음) · 정리 에이전트의 계획 적용 · 맞출 갈래를 고른 레벨이 있음.
    # 떼기만 · 대표만 청한 것(likes 가 빈 목록뿐)은 전처럼 오버레이만 바꾼다(문서는 그대로)
    fit = _place_on(body) and (want is None or by == "agent" or any(likes is None or likes for _, _, likes, _ in want))
    kind, per, out = apply_templates(server, doc_id, [(tpl, want)], rev=rev, op="outlineTplMatch", req={"tpl": tpl, "levels": levels, "by": by}, log=log,
                                     marks={str(tpl): at} if at is not None else None, settle=[tpl] if fit else None,
                                     by="agent" if by == "agent" else None)  # 정리 에이전트의 계획이 바꾼 대표는 잠그지 않는다 — 그 밖(대표 미리보기의 묶음 맞추기 …)은 사람이 정한 대표
    if kind == "nothing" or not isinstance(out, dict):
        return out
    one = per[0] if per else {"levels": [], "splits": [], "changed": []}
    out["levels"] = one["levels"]
    if one["splits"]:
        out["splits"] = one["splits"]
    if at is not None:  # 분석 상태의 서식 LLM 칸(spec_작업 ② §20). 문서가 안 바뀐 반영(떼기만 · 대표만)도 적는다
        s1 = server._sess(doc_id)
        tpl_agent_api.applied(s1, tpl, rev, len(one["changed"]), at)
        graph = (s1.outline or {}).get("run")
        rec = tpl_agent_api.plans(s1, graph).get(str(tpl)) or {}
        if rec.get("at") == at:  # 실제로 반영한 것(사람이 고르기를 바꿨으면 바꾼 대로)을 실행 기록에 — 결과 화면(spec_헤딩_추출 ② §7 「결과 화면」)
            tpl_agent_api.note_apply(s1, graph, "tpl", [{"tpl": str(tpl), "no": rec.get("no"), "plan": at, "summary": (rec.get("plan") or {}).get("summary", ""), "changed": len(one["changed"]),
                                                         "levels": tpl_agent_api.A.apply_view(rec.get("plan"), levels if isinstance(levels, list) else [])}])
    return out


def _tid(v, what):
    if isinstance(v, bool) or not isinstance(v, (str, int)) or str(v) == "":
        raise HTTPException(400, f"{what}(템플릿 id)가 필요합니다")
    return str(v)


@router.post("/api/docs/{doc_id}/outline/merge")
def merge(doc_id: str, body: dict = Body(...)):
    """{child, parent, at} — 템플릿 child 를 parent 의 L at 아래로: 종속 템플릿 「T{parent}T{child}」(id 「parent+child」)를 만들어 그 자리에 매달린 child 줄을
    (종속 템플릿, at + 레벨)로. parent 는 안 바뀐다. 문서는 안 바뀐다 · 실행 취소 1(기록 `outlineMerge`). → {merged{id, no, moved, levels}, outline, …편집 상태}.
    400 매달린 곳 없음·이미 넣음·제 자신·잘못된 값 · 409 2단계 없음."""
    server = _server()
    child, parent, at = _tid(body.get("child"), "child"), _tid(body.get("parent"), "parent"), body.get("at")
    if isinstance(at, bool) or not isinstance(at, int) or at < 1:
        raise HTTPException(400, "at(넣을 자리의 레벨 — 1 이상의 정수)이 필요합니다")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)

        def change():
            rec = outline_match.merge(ov, child, parent, at, outline_match.context(s.doc, ov))
            C = ov["templates"][rec["id"]]
            return {"id": rec["id"], "no": C["no"], "child": ov["templates"][child]["no"], "parent": ov["templates"][parent]["no"], "at": at,
                    "moved": len(rec["moved"]), "levels": [at + 1, C["max"]]}
        got, ok = _model_only(server, s, "outlineMerge", {"child": child, "parent": parent, "at": at}, change)
        if not ok:
            return got
        return {"merged": got, "outline": outline_pos.view(s.doc, s.outline), **_state(s)}


@router.post("/api/docs/{doc_id}/outline/unmerge")
def unmerge(doc_id: str, body: dict = Body(...)):
    """{child, parent} — 종속 템플릿을 지우고 그 줄을 child 로 되돌린다(넣은 뒤 Enter 로 만든 줄 포함). 실행 취소 1(기록 `outlineUnmerge`). → {back, outline, …편집 상태}.
    400 기록 없음 · 그 종속 템플릿으로 또 만든 종속 템플릿이 있음(그것부터)."""
    server = _server()
    child, parent = _tid(body.get("child"), "child"), _tid(body.get("parent"), "parent")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)

        def change():
            return {"child": ov["templates"].get(child, {}).get("no"), "parent": ov["templates"].get(parent, {}).get("no"),
                    "back": outline_match.unmerge(ov, child, parent)}
        got, ok = _model_only(server, s, "outlineUnmerge", {"child": child, "parent": parent}, change)
        if not ok:
            return got
        return {"back": got.get("back", 0), "outline": outline_pos.view(s.doc, s.outline), **_state(s)}


@router.post("/api/docs/{doc_id}/outline/slots/{tpl}/{level}/split")
def split(doc_id: str, tpl: str, level: int, body: dict = Body(...)):
    """{likes[그 레벨 줄 id], rep?, into?, sfx?} — 그 줄들과 서식이 같은 갈래를 **서식 종속 템플릿**(표기 「T{tpl}L{level}a」 · id 「tpl~level글자」 — spec_hwpx_웹편집 ② §8-5)으로 뗀다:
    그 갈래의 줄과 그 아래 줄(자손)이 새 템플릿으로 가고(레벨은 그대로 — 새 템플릿의 줄은 L level 부터), 새 템플릿의 L level 대표·모양은 rep(없으면 likes 의 첫 줄)의 지금 것.
    into(이미 있는 서식 종속 템플릿 id)를 주면 거기에 더 넣는다. 원래 템플릿은 안 바뀐다 · 문서는 안 바뀐다 · 실행 취소 1(기록 `outlineSplit`).
    → {split{id, no, of, level, moved, lines, added}, outline, …편집 상태}. 400 그 레벨 줄이 아님 · 대표 갈래 · 번호형 레벨의 형제 일부 · 글자 다 씀 · 404 템플릿·레벨 없음 · 409 2단계 없음."""
    server = _server()
    likes, rep, into, sfx = body.get("likes"), body.get("rep"), body.get("into"), body.get("sfx")
    if not isinstance(likes, list) or not likes or not all(isinstance(p, str) and p for p in likes):
        raise HTTPException(400, "likes(뗄 갈래의 줄 id 목록)가 필요합니다")
    if rep is not None and (not isinstance(rep, str) or not rep):
        raise HTTPException(400, "rep 는 문단 id")
    if into is not None:
        into = _tid(into, "into")
    if sfx is not None and not (isinstance(sfx, str) and len(sfx) == 1 and sfx in outline_match.SFX):
        raise HTTPException(400, "sfx 는 a~z 한 글자")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)
        if outline_edit._slot(ov, tpl, level) is None:
            raise HTTPException(404, "그런 템플릿 레벨이 없습니다")

        def change():
            paras = outline_match.split_targets(s.doc, ov, tpl, level, likes)
            r = rep or likes[0]
            shape = outline_match.rep_shape(s.doc, ov, r) if into is None else None  # 더 넣을 때는 그 템플릿의 대표·모양 그대로
            got = outline_match.split(ov, tpl, level, paras, rep=r, shape=shape, into=into, sfx=sfx)
            return {"id": got["id"], "no": got["no"], "of": ov["templates"][str(tpl)]["no"], "level": level, "moved": len(got["moved"]), "lines": len(paras), "added": not got["new"]}
        got, ok = _model_only(server, s, "outlineSplit", {"tpl": tpl, "level": level, "likes": likes, "rep": rep, "into": into, "sfx": sfx}, change)
        if not ok:
            return got
        return {"split": got, "outline": outline_pos.view(s.doc, s.outline), **_state(s)}


@router.post("/api/docs/{doc_id}/outline/unsplit")
def unsplit(doc_id: str, body: dict = Body(...)):
    """{id} — 서식 종속 템플릿을 지우고 그 줄(뗀 뒤 Enter 로 만든 줄 포함)을 원래 템플릿의 같은 레벨로 되돌린다(② §8-5 「합치기」). 실행 취소 1(기록 `outlineUnsplit`).
    → {back, outline, …편집 상태}. 400 서식 종속 템플릿이 아님 · 그 템플릿으로 만든 종속·서식 종속 템플릿이 있음(그것부터)."""
    server = _server()
    cid = _tid(body.get("id"), "id")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)

        def change():
            C = ov["templates"].get(cid) or {}
            return {"id": cid, "no": C.get("no"), "of": ov["templates"].get((C.get("variant") or {}).get("of"), {}).get("no"), "back": outline_match.unsplit(ov, cid)}
        got, ok = _model_only(server, s, "outlineUnsplit", {"id": cid}, change)
        if not ok:
            return got
        return {"back": got.get("back", 0), "outline": outline_pos.view(s.doc, s.outline), **_state(s)}
