"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속 API(spec_hwpx_웹편집 ② §8-2) — server.py 가 include 한다(`outline_format_api` 와 같은 꼴).
계산은 `app/outline_match.py`, 오버레이는 `server._outline_ov`, 트랜잭션은 `server._transact`·`server._edit`(실행 취소 1 · 기록)."""
import contextlib
import copy

from fastapi import APIRouter, Body, HTTPException

from app import outline_edit, outline_match, outline_pos

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
    맞출 줄이 없으면 편집을 열지 않고 {changed: [], nothing: true, …편집 상태}. 400 대표가 문서에 없음 · 404 그런 레벨 없음 · 409 2단계 없음."""
    server = _server()
    paras, like = body.get("paras"), body.get("like")
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
        if not pre:
            return {"changed": [], "nothing": True, **_state(s0)}
    extra, changed = {}, []

    def make(s):
        ov2 = _ov(server, s)
        try:
            ids = outline_match.match_targets(s.doc, ov2, tpl, level, paras, like)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not ids:
            raise HTTPException(409, "그 사이에 문서가 바뀌어 맞출 줄이 없습니다 — 다시 읽어 주세요")
        sl = outline_edit._slot(ov2, tpl, level)

        def run():
            sh = outline_match.rep_shape(s.doc, ov2, sl["rep"])
            sl.update(prefix=sh["prefix"], letter=sh["tok"], attrs=sh["attrs"], bodyChar=sh["body"])  # 새 줄도 대표의 지금 모양으로
            meas = outline_pos.Measure(s.doc) if (sl.get("pos") or {}).get("set") else None
            for pid in ids:
                outline_match.match_one(s.doc, ov2, pid, sh)
                if meas is not None:  # 사람이 정한 자리 규칙(② §8-1)도 다시
                    try:
                        outline_pos.align(s.doc, ov2, pid, full=True, measure=meas)
                    except ValueError:
                        pass
                changed.append(pid)
            extra.update({"lines": {pid: outline_edit.line_view(ov2["lines"][pid]) for pid in ids}, "removed": []})
            return {"hosts": [s.doc._ids[i] for i in ids], "formatted": set(ids), "struct": set(), "origin": {}, "anchor": ids[0],
                    "log": {"tpl": ov2["templates"][str(tpl)]["no"], "level": level, "rep": sl["rep"], "changed": len(ids)}}
        return [s.doc._ids[i] for i in ids], run
    out = server._edit(doc_id, make, "outlineMatch", {"tpl": tpl, "level": level, "paras": paras, "like": like})
    if isinstance(out, dict):
        out["outline"] = extra
        out["changed"] = changed
    return out


@router.post("/api/docs/{doc_id}/outline/templates/{tpl}/match")
def match_template(doc_id: str, tpl: str, body: dict = Body(default={})):
    """템플릿 단위 맞추기 — 한 템플릿의 여러 레벨을 **트랜잭션 하나**(실행 취소 1 · 기록 `outlineTplMatch`)로 대표 모양에 맞춘다(spec_hwpx_웹편집 ② §8-2 「템플릿 맞추기」 ·
    §8-4 정리 에이전트의 적용). {levels?: [{level, rep?(그 레벨 줄 id — 대표를 이 줄로 바꾼 뒤 맞춤), likes?([그 레벨 줄 id] — 그 줄들과 서식이 같은 갈래만 · 없으면 대표와 다른 줄 모두)}],
    rev?(계획을 세운 문서 차례 — 지금과 다르면 409), by?("agent" — 기록에만)}. levels 가 없으면 줄이 있는 모든 레벨의 대표와 다른 줄 모두.
    → 다른 구조 편집과 같은 꼴 + changed[줄 id] · levels[{level, rep, repChanged, changed(수)}] · outline{lines}. 바꿀 것이 없으면 {changed: [], nothing: true, …편집 상태}.
    대표만 바뀌면(맞출 줄 없음) 문서는 안 바뀌고 {changed: [], reps, outline(GET /outline 꼴), …편집 상태}. 400 대표·갈래 줄이 그 레벨 줄이 아님 · 404 템플릿·레벨 없음 · 409 2단계 없음·문서가 바뀜.
    **떼기도 같이**(② §8-5): levels[].splits = [{likes([그 레벨 줄 id] — 그 줄들과 서식이 같은 갈래를 서식 종속 템플릿 「T1L3a」 로), rep?(새 템플릿의 대표 줄 — 없으면 likes 의 첫 줄),
    sfx?(글자), match?(기본 true — 뗀 줄 가운데 새 대표와 다른 줄을 그 대표 모양으로)}] — 그 레벨에서 대표 바꿈 → 맞추기(뗄 줄은 빼고) → 떼기 → 뗀 줄 맞추기를 같은 트랜잭션으로.
    응답에 splits[{level, id, no, moved, changed}]. 문서가 안 바뀌는 조합(떼기만 · 대표만)이면 오버레이만. 같은 갈래가 likes 와 splits 에 함께 · 대표 갈래를 뗌 · 번호형 레벨의 형제 일부는 400."""
    server = _server()
    levels, rev, by = body.get("levels"), body.get("rev"), body.get("by")
    if levels is not None and (not isinstance(levels, list) or not all(isinstance(x, dict) for x in levels)):
        raise HTTPException(400, "levels 는 [{level, rep?, likes?, splits?}] 목록")
    want = []
    for x in levels or []:
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

    def plan(s, ov):
        """-> [(level, 대표, 대표 바뀜, [바꿀 줄], [뗄 것 {paras, rep, sfx, ids(뗀 뒤 새 대표에 맞출 줄)}])] — 바꿀 것이 있는 레벨만."""
        if str(tpl) not in ov["templates"]:
            raise HTTPException(404, "그런 템플릿이 없습니다")
        if rev is not None and rev != s.rev:
            raise HTTPException(409, "그 사이에 문서가 바뀌었습니다 — 서식 갈래를 다시 읽은 뒤 맞추세요")
        todo = want if levels is not None else [(int(lv), None, None, []) for lv in sorted(ov["templates"][str(tpl)].get("slots", {}), key=int)
                                               if outline_match.slot_ids(ov, tpl, lv)]
        out = []
        for lv, rep, likes, cuts in todo:
            sl = outline_edit._slot(ov, tpl, lv)
            if sl is None:
                raise HTTPException(404, f"L{lv} 이 없습니다")
            try:
                if levels is None and (not sl.get("rep") or sl["rep"] not in ov["lines"]):
                    continue  # 「모든 레벨」 — 대표가 없는 레벨은 건너뛴다(고른 레벨이면 400)
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
                                "ids": [p for p in paras if p != c_rep and outline_match.look(s.doc, ov, p) != base] if c_match else []})
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

    def cut_now(s, ov, lv, c, done_cuts):
        """뗄 것 하나를 지금 뗀다(오버레이) → 새 템플릿 대표의 모양(뗀 줄을 맞출 때 쓴다)."""
        shape = outline_match.rep_shape(s.doc, ov, c["rep"])
        got = outline_match.split(ov, tpl, lv, c["paras"], rep=c["rep"], shape=shape, sfx=c["sfx"])
        done_cuts.append({"level": lv, "id": got["id"], "no": got["no"], "moved": len(got["moved"]), "changed": len(c["ids"])})
        return shape, got

    s0 = server._sess(doc_id)
    _hwpx(s0)
    with s0.lock:
        pre = plan(s0, _ov(server, s0))
        if not pre:
            return {"changed": [], "nothing": True, **_state(s0)}
        if not any(ids or any(c["ids"] for c in cut) for _, _, _, ids, cut in pre):  # 대표만 바뀜 · 떼기만 — 문서는 그대로(오버레이만: 실행 취소 1)
            ov = s0.outline
            cuts0 = []

            def change():
                with _ov_guard(ov, any(cut for *_, cut in pre)):
                    for lv, r, rep_changed, _, cut in pre:
                        if rep_changed:
                            outline_match.set_rep(s0.doc, ov, tpl, lv, r)
                        for c in cut:
                            cut_now(s0, ov, lv, c, cuts0)
                return {"tpl": ov["templates"][str(tpl)]["no"], "levels": [{"level": lv, "rep": r, "repChanged": rc, "changed": 0} for lv, r, rc, _, _ in pre],
                        "by": by, **({"splits": list(cuts0)} if cuts0 else {})}
            got, ok = _model_only(server, s0, "outlineTplMatch", {"tpl": tpl, "levels": levels, "by": by}, change)
            if not ok:
                return got
            return {"changed": [], "reps": sum(1 for x in pre if x[2]), "levels": got["levels"], **({"splits": got["splits"]} if got.get("splits") else {}),
                    "outline": outline_pos.view(s0.doc, s0.outline), **_state(s0)}
    extra, changed, done, cuts = {}, [], [], []

    def make(s):
        ov2 = _ov(server, s)
        todo = plan(s, ov2)
        ids_all = [i for _, _, _, ids, cut in todo for i in ids + [p for c in cut for p in c["ids"]]]
        if not ids_all:
            raise HTTPException(409, "그 사이에 문서가 바뀌어 맞출 줄이 없습니다 — 다시 읽어 주세요")

        def run():
            moved = []
            with _ov_guard(ov2, any(cut for *_, cut in todo)):
                for lv, r, rep_changed, ids, cut in todo:
                    sl = outline_edit._slot(ov2, tpl, lv)
                    if rep_changed:
                        outline_match.set_rep(s.doc, ov2, tpl, lv, r)
                    if ids or rep_changed:
                        sh = outline_match.rep_shape(s.doc, ov2, sl["rep"])
                        sl.update(prefix=sh["prefix"], letter=sh["tok"], attrs=sh["attrs"], bodyChar=sh["body"])  # 새 줄도 대표의 지금 모양으로
                        meas = outline_pos.Measure(s.doc) if (sl.get("pos") or {}).get("set") else None
                        for pid in ids:
                            outline_match.match_one(s.doc, ov2, pid, sh)
                            if meas is not None:  # 사람이 정한 자리 규칙(② §8-1)도 다시
                                try:
                                    outline_pos.align(s.doc, ov2, pid, full=True, measure=meas)
                                except ValueError:
                                    pass
                            changed.append(pid)
                    done.append({"level": lv, "rep": sl["rep"], "repChanged": rep_changed, "changed": len(ids)})
                    for c in cut:  # 서식 종속 템플릿으로 떼고(② §8-5), 뗀 줄 가운데 새 대표와 다른 줄은 그 대표 모양으로
                        shape, got = cut_now(s, ov2, lv, c, cuts)
                        moved.extend(got["moved"])
                        for pid in c["ids"]:
                            outline_match.match_one(s.doc, ov2, pid, shape)
                            changed.append(pid)
            extra.update({"lines": {pid: outline_edit.line_view(ov2["lines"][pid]) for pid in dict.fromkeys(ids_all + moved)}, "removed": []})
            return {"hosts": [s.doc._ids[i] for i in ids_all], "formatted": set(ids_all), "struct": set(), "origin": {}, "anchor": ids_all[0],
                    "log": {"tpl": ov2["templates"][str(tpl)]["no"], "levels": list(done), "changed": len(ids_all), "by": by, **({"splits": list(cuts)} if cuts else {})}}
        return [s.doc._ids[i] for i in ids_all], run
    out = server._edit(doc_id, make, "outlineTplMatch", {"tpl": tpl, "levels": levels, "by": by})
    if isinstance(out, dict):
        out["outline"] = extra
        out["changed"] = changed
        out["levels"] = done
        if cuts:
            out["splits"] = cuts
        if by == "agent" and rev is not None:  # 정리 에이전트의 계획을 적용함 — 분석 상태의 서식 LLM 칸(spec_작업 ② §20)
            from app import tpl_agent_api
            tpl_agent_api.applied(server._sess(doc_id), tpl, rev, len(changed))
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
