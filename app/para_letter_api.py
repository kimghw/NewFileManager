"""레터 넣기 API(spec_hwpx_웹편집 ② §8-9) — 도구 줄 「문단 수정」 묶음의 「레터 넣기」 단추: 메뉴 받기(POST …/letter/suggest) · 넣기·빼기·개요 레벨로(POST …/letter).
server.py 가 include 한다(개요 레벨 더하기 `outline_grow_api` 와 같은 꼴). 계획은 `app/para_letter.py`(순수 함수), 실행은 편집 트랜잭션 하나(`server._edit` — OWPML·OOXML 검사 · 실행 취소 1 · 기록 kind `outline` `op: letter`):
- 레터만 · 레터 빼기(hwpx · docx): 접두만 바꾼다 — hwpx `replace_prefix`(런·글자 모양 그대로) · docx `set_text`. 개요 오버레이의 줄이면 같은 꼴 레터로 바뀐 줄만 오버레이에 남기고(레터만 고침),
  다른 꼴이 됐거나 레터가 빠진 줄은 `_outline_sync` 가 오버레이에서 뺀다(그 줄은 헤딩 추출을 다시 돌리면 새 자리를 받는다).
- 개요 레벨로(hwpx + 2단계 오버레이): `para_letter.plan_adopt` 의 계획을 개요 편집과 같은 실행(`server._outline_run`)으로 — 응답에 outline{lines, removed, new, focuses}."""
from fastapi import APIRouter, Body, HTTPException

from app import outline_edit, para_letter

router = APIRouter()


def _ids(body):
    ids = list(dict.fromkeys(body.get("ids") or ([body["id"]] if body.get("id") else [])))
    if not ids or not all(isinstance(i, str) for i in ids):
        raise HTTPException(400, "id 가 필요합니다")
    return ids


def _seq(s, ids):
    """문단들이 든 그릇의 문단 열 → (그릇, seq, 자리들). 그릇이 섞이면 400. hwpx 는 개요 편집과 같은 열(`server._outline_seq` — 표 제목 줄은 그 표를 품은 문단 자리에), docx 는 같은 꼴로 만든다."""
    from app import server
    els = [server._para_el(s, i) for i in ids]
    if s.fmt == "hwpx":
        par, seq = server._outline_seq(s, els[0])
    else:
        par, doc, seq = els[0].getparent(), s.doc, []
        for c in par.iterchildren(s.kit["para"]):
            text, obj = doc._text(c), doc._has_object(c)
            seq.append({"id": doc._id(c), "text": text, "blank": not text.strip() and not obj, "object": obj})
    if any(e.getparent() is not par for e in els):
        raise HTTPException(400, "같은 구역·칸 안의 문단들만 함께 바꿀 수 있습니다")
    pos = {it["id"]: k for k, it in enumerate(seq)}
    if any(i not in pos for i in ids):
        raise HTTPException(400, "레터를 넣을 수 있는 문단이 아닙니다(표를 품은 문단)")
    return par, seq, [pos[i] for i in ids]


def _ov(s):
    from app import server
    return server._outline_ov(s) if s.fmt == "hwpx" else None


def _known(ov):
    """오버레이가 아는 줄의 레터 {문단 id: 레터} — 괄호 줄(글 전체가 레터)·표 제목 줄은 뺀다(그 글을 레터로 보고 바꾸면 제목이 통째로 사라진다)."""
    if not ov:
        return {}
    return {p: x["letter"] for p, x in ov["lines"].items() if x.get("letter") and x.get("role") not in outline_edit.ROOTED and x.get("role") != outline_edit.TABLE}


@router.post("/api/docs/{doc_id}/letter/suggest")
def letter_suggest(doc_id: str, body: dict = Body(...)):
    """{ids: 커서가 든 문단(고른 범위면 걸친 문단들 — 같은 그릇)} → 메뉴에 보일 것(para_letter.suggest 꼴 — 지금 레터 · 개요 레벨 · 번호·기호 후보마다 넣을 레터) + rev · format.
    문서·오버레이는 안 바뀐다. 400 넣을 수 없는 자리(표·그림만 든 문단 · 그릇이 섞임)."""
    from app import server
    s = server._sess(doc_id)
    ids = _ids(body)
    with s.lock:
        _, seq, idxs = _seq(s, ids)
        ov = _ov(s)
        try:
            flat = [{**it, "text": ""} if it.get("host") else it for it in seq]  # 표 제목 줄은 이 그릇의 글이 아니다(letter 와 같은 눈으로 — 「넣을 레터」 가 실제와 같게)
            return {**para_letter.suggest(flat, idxs, ov, _known(ov)), "rev": s.rev, "format": s.fmt}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.post("/api/docs/{doc_id}/letter")
def letter(doc_id: str, body: dict = Body(...)):
    """{ids, letter(레터만 넣기) | level{tpl, level}(개요 레벨로 — hwpx + 2단계) | remove: true(레터 빼기), restart?(번호를 앞 줄에 잇지 않고 고른 레터부터)} —
    응답 = 편집 응답(_edit: tops · focus · rev …) + letter{mode(plain|level|remove), put[넣은(뺀) 레터…], from(이은 앞 줄의 레터), follow(번호를 민 뒤 줄 수), ids(바뀐 문단)},
    개요 레벨로면 outline{lines, removed, new, focuses} 도. 400 잘못된 값·넣을 수 없는 자리·바뀔 것이 없음 · 409 개요 레벨로인데 2단계 결과 없음 · 422 표준 검사에 걸려 되돌림."""
    from app import server
    s0 = server._sess(doc_id)
    ids = _ids(body)
    level = body.get("level")
    mode = "remove" if body.get("remove") else "level" if level else "plain"
    if mode == "level":
        if s0.fmt != "hwpx":
            raise HTTPException(400, "개요 레벨로 바꾸기는 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
        if not isinstance(level, dict) or level.get("tpl") is None or not isinstance(level.get("level"), int) or isinstance(level.get("level"), bool):
            raise HTTPException(400, "level 은 {tpl, level(정수)}")
    elif mode == "plain" and not isinstance(body.get("letter"), str):
        raise HTTPException(400, "letter(넣을 레터)가 필요합니다")
    extra, made = {}, {}

    def make(s):
        par, seq, idxs = _seq(s, ids)
        ov = _ov(s)
        text_of = lambda pid: s.doc._text(s.doc._ids[pid])  # noqa: E731
        if mode == "level":
            if ov is None:
                raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
            try:
                plan = para_letter.plan_adopt(seq, idxs, level["tpl"], level["level"], ov, text_of)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
            plan["alias"] = {it["id"]: it["host"] for it in seq if it.get("host")}  # 표 제목 줄(② §8-7) → 호스트 문단(server._outline_run 의 rid)
            touched = {a["id"] for a in plan["actions"]}
            before = [s.doc._ids[i] for i in touched if i in s.doc._ids]

            def run():
                out = server._outline_run(s, ov, par, plan, extra, "letter", ids)
                t = ov["templates"][str(level["tpl"])]
                done = [a for a in plan["actions"] if a["act"] == "restyle"]
                made.update({"mode": "level", "tpl": str(level["tpl"]), "no": t["no"], "level": level["level"], "put": [ov["lines"][a["id"]]["letter"] for a in done if a["id"] in ov["lines"]],
                             "from": None, "follow": len({a["id"] for a in plan["actions"] if a["act"] == "retext"} - {a["id"] for a in done}),  # 번호가 밀린 **다른** 줄 수(바꾼 줄 자신의 번호 매김은 빼고)
                             "ids": [a["id"] for a in done]})
                out["log"] = {**(out.get("log") or {}), "letter": {k: made[k] for k in ("mode", "no", "level", "put")}}
                return out
            return before, run
        # 표 제목 줄(② §8-7 — 그 표를 품은 문단 자리에 칸 안 제목 글로 놓인 것)은 이 그릇의 글이 아니다: 번호를 잇거나 미는 데서 뺀다(표·그림만 든 문단으로 본다)
        flat = [{**it, "text": ""} if it.get("host") else it for it in seq]
        try:
            plan = para_letter.plan_remove(flat, idxs, _known(ov)) if mode == "remove" else para_letter.plan_plain(flat, idxs, body["letter"], bool(body.get("restart")), _known(ov))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not plan["actions"]:
            raise HTTPException(400, f"바뀔 것이 없습니다 — 이미 「{' '.join(plan['put'])}」 입니다")
        # 닿는 범위 = 그릇 안 **이어진 구간 전체**(첫 바뀐 문단 ~ 마지막 바뀐 문단 — 사이의 안 바뀐 문단·표 포함): 화면 applyTops 는 응답이 옛 구간을 다 덮어야 그 토막만 바꾼다(아니면 문서를 통째로 다시 읽는다 — ② §8)
        kids = list(par.iterchildren(s.kit["para"]))
        ix = {c: k for k, c in enumerate(kids)}
        hit = [ix[s.doc._ids[a["id"]]] for a in plan["actions"]]
        els = kids[min(hit):max(hit) + 1]

        def run():
            changed = []
            for a in plan["actions"]:
                pid = a["id"]
                if s.fmt == "hwpx":
                    s.doc.replace_prefix(pid, a["old_len"], a["prefix"])
                else:
                    s.doc.set_text(pid, a["prefix"] + text_of(pid)[a["old_len"]:])
                changed.append(pid)
                line = ov["lines"].get(pid) if ov else None
                if line is not None and a["letter"] and _same_key(line, a["letter"]):  # 같은 꼴의 다른 번호 — 개요 줄로 남긴다(레터만 고침). 다른 꼴·뺀 줄은 _outline_sync 가 뺀다
                    line["letter"] = a["letter"]
                    extra.setdefault("lines", {})[pid] = outline_edit.line_view(line)
                    server.outline_pos.align_quiet(s.doc, ov, pid)
            if ov:
                extra["removed"] = [p for p in changed if p in ov["lines"] and p not in extra.get("lines", {})]
            head = [a for a in plan["actions"] if not a.get("follow")]
            made.update({"mode": mode, "put": plan["put"], "from": plan["from"], "follow": plan["follow"], "ids": [a["id"] for a in head]})
            return {"hosts": els, "focus": plan["focus"], "anchor": ids[0],
                    "log": {"op": "letter", "ids": ids, "letter": {"mode": mode, "put": plan["put"], "follow": plan["follow"]}}}
        return els, run
    # 기록 kind = outline(「개요 편집」) · op = letter — 기록 보기(app.js OUTLINE_OP)가 「레터 넣기」 로 보인다
    out = server._edit(doc_id, make, "outline", {"op": "letter", **{k: body.get(k) for k in ("ids", "letter", "level", "restart", "remove") if body.get(k) is not None}})
    if isinstance(out, dict):
        if extra:
            out["outline"] = extra
        out["letter"] = made
    return out


def _same_key(line, letter):
    """새 레터가 그 개요 줄의 레터와 같은 꼴인가(번호만 다름 — 「②」 → 「③」)."""
    try:
        return para_letter.same(para_letter.check(line.get("letter")), para_letter.check(letter))
    except ValueError:  # 내장 규칙이 못 읽는 레터(배운 규칙의 줄) — 같은 꼴인지 모른다: 오버레이에서 빼 둔다
        return False
