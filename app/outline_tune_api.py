"""개요 줄의 헤딩 고치기 API(spec_hwpx_웹편집 ② §8-12 — 2026-11-24 전의 이름 「레터 고치기」) — 고른 개요 줄의 레터 · 레터 앞뒤 빈칸 · 앞 여백 · 2번째 줄을 고치고
범위(이 문단만 · 서식 전체 변경 · 새 템플릿으로 나누기 — 시작 · 끝 레벨)를 고른다:
창의 자료(POST …/outline/tune/suggest) · 반영(POST …/outline/tune). server.py 가 include 한다(개요 레벨 더하기 `outline_grow_api` 와 같은 꼴).
계획 · 반영은 `app/outline_tune.py`, 실행은 편집 트랜잭션 하나(`server._edit` — 표준 검사 · 실행 취소 1(오버레이도 함께) · 기록 kind `outline` `op: tune`)."""
import secrets

from fastapi import APIRouter, Body, HTTPException

from app import outline_edit, outline_match, outline_tune

router = APIRouter()
UNDO_MARK = "tune"   # 실행 취소 묶음에 남기는 표(이 창의 반영이 만든 묶음인가 — 창의 「되돌리기」 가 본다)
SCOPE_NAMES = {"line": "이 문단만", "level": "서식 전체 변경", "split": "새 템플릿으로 나누기"}


def _sess(doc_id):
    from app import server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "개요 편집은 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
    return server, s


def _ov(server, s):
    ov = server._outline_ov(s)
    if ov is None:
        raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
    return ov


def _pid(body):
    pid = body.get("id")
    if not isinstance(pid, str) or not pid:
        raise HTTPException(400, "id(문단)가 필요합니다")
    return pid


@router.post("/api/docs/{doc_id}/outline/tune/suggest")
def tune_suggest(doc_id: str, body: dict = Body(...)):
    """{id: 개요 줄} → 창의 자료(outline_tune.suggest 꼴 — 지금 값 · 대표의 값 · 대표와 다른 것 · 줄 수 · 새 템플릿 이름 · 레터 후보) + rev. 문서 · 오버레이는 안 바뀐다.
    400 고칠 수 없는 줄(개요 줄 아님 · 괄호 줄 · 표 제목 줄 · 자동 글머리 줄 · 값 칸) · 409 2단계 결과 없음."""
    server, s = _sess(doc_id)
    pid = _pid(body)
    with s.lock:
        ov = _ov(server, s)
        try:
            return {**outline_tune.suggest(s.doc, ov, pid), "rev": s.rev}
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e)) from e


def _args(body):
    return {"letter": body.get("letter"), "lead": body.get("lead"), "gap": body.get("gap"), "front": body.get("frontMm"), "exact": bool(body.get("exact")),
            "line2": body.get("line2"), "start": body.get("start"), "upto": body.get("upto"), "cut": body.get("cut")}


@router.post("/api/docs/{doc_id}/outline/tune/preview")
def tune_preview(doc_id: str, body: dict = Body(...)):
    """{id, letter?, exact?, lead?, gap?, frontMm?, line2?(text | letter | front), start?, upto?, cut?(here | all — 새 템플릿으로 나누기의 시작 · 끝 레벨 · 범위)} — 그 값으로 범위 셋
    (이 문단만 · 서식 전체 변경 · 새 템플릿으로 나누기)을 반영하면 어떻게 되나(outline_tune.preview 꼴 — 범위마다 ok · 못 하는 까닭 ·
    바뀔 줄 수 · 이미 같은 줄 · 표의 서식이라 남는 줄 · 새 템플릿 이름 · 옮겨 갈 줄 · 끝 레벨 아래라 남는 줄) + rev. 문서 · 오버레이는 안 바뀐다. 400 고칠 수 없는 줄 · 409 2단계 결과 없음."""
    server, s = _sess(doc_id)
    pid = _pid(body)
    with s.lock:
        ov = _ov(server, s)
        try:
            outline_tune.line_of(s.doc, ov, pid)
            return {**outline_tune.preview(s.doc, ov, pid, **_args(body)), "rev": s.rev}
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e)) from e


@router.post("/api/docs/{doc_id}/outline/tune/undo")
def tune_undo(doc_id: str, body: dict = Body(...)):
    """{rev: 이 창의 반영이 남긴 문서 차례, token: 그 반영의 표(응답 tune.undo)} — 그 반영을 되돌린다(도구 줄 「↶ 실행 취소」 와 같은 것 — 문서 · 개요 오버레이가 그 편집 앞으로).
    **실행 취소 묶음의 맨 위가 그 반영이고 문서 차례가 그대로일 때만**: 그 뒤에 다른 편집 · 글 고침이 있었거나 다른 문서의 것이면 409(그것까지 되돌리지 않는다 — 도구 줄의 실행 취소로:
    차례 번호만으로는 어느 문서의 어떤 편집인지 모른다 — astra 2차). 응답 = GET /api/docs/{id}(블록 전체)."""
    server, s = _sess(doc_id)
    rev, token = body.get("rev"), body.get("token")
    with s.lock:
        server._fenced(s)
        if (not isinstance(rev, int) or isinstance(rev, bool) or rev != s.rev or not s.undo or not isinstance(token, str) or not token
                or s.undo[-1].get(UNDO_MARK) != token):
            raise HTTPException(409, "그 뒤에 문서가 바뀌어 이 창에서는 되돌릴 수 없습니다 — 도구 줄 「↶ 실행 취소」 를 쓰세요")
        server._rollback(s, s.undo.pop())
        s.owpml_last = None
        server._bump(s, "undo")
    return server.get_doc(doc_id)


def _plan(s, ov, pid, body):
    try:
        return outline_tune.plan(s.doc, ov, pid, scope=body.get("scope") or "line", **_args(body))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/docs/{doc_id}/outline/tune")
def tune(doc_id: str, body: dict = Body(...)):
    """{id, letter?(고른 레터 — 번호형은 꼴: 줄마다 제 번호), exact?(직접 입력 — 적은 그대로), lead?(레터 앞 빈칸 칸 수), gap?(레터 뒤 빈칸 칸 수), frontMm?(앞 여백 mm),
    line2?(2번째 줄 — text 글 시작 | letter 레터 | front 앞 여백),
    scope: "line"(이 문단만 — 기본) | "level"(서식 전체 변경: 이 줄을 대표로 삼고 그 레벨 줄을 모두 맞춤) | "split"(새 템플릿으로 나누기: 이 줄 — 또는 start 레벨의 윗줄 — 부터 새 템플릿으로 ·
    start?(시작 레벨) · upto?(끝 레벨 — 없으면 끝까지) · cut?(here 그 줄과 아래 | all 그 레벨 줄 모두)), rev?(창을 연 문서 차례)} —
    트랜잭션 하나. 응답 = 편집 응답(tops · rev …) + tune{scope, name(「T1 L5」), letter, changed(바뀐 줄 수), matched(맞춘 다른 줄 수), kept(표의 서식이라 레터만 바꾼 줄 수),
    left[{id, why, kinds}](짝 표지 때문에 남긴 줄), split{id, no, name, moved, lines} | null} + outline{lines, removed, fmts}. 화면은 이어서 GET …/outline 로 템플릿 요약을 다시 읽는다.
    400 잘못된 값 · 고칠 수 없는 줄 · 바뀔 것이 없음 · 못 떼는 자리 · 409 2단계 없음 · 문서가 바뀜(rev) · 422 표준 검사에 걸려 되돌림."""
    server, s0 = _sess(doc_id)
    pid = _pid(body)
    rev = body.get("rev")
    extra, made = {}, {}

    def make(s):
        ov = _ov(server, s)
        if (rev is not None and rev != s.rev) or (body.get("run") is not None and body.get("run") != ov.get("run")):   # 창이 본 문서 차례 · 헤딩 그래프 실행이 지금 것인가(미리 본 줄과 다른 줄을 고치지 않게)
            raise HTTPException(409, "그 사이에 문서가 바뀌었습니다 — 지금 문서로 다시 확인했습니다. 「적용」 을 한 번 더 눌러 주세요")
        pl = _plan(s, ov, pid, body)
        o = pl.get("others") or {}
        hit = [pid] + o.get("diff", []) + o.get("same", []) + [p for p in o.get("own", []) if p in (pl.get("toks") or {})] + list((pl.get("split") or {}).get("touch") or [])
        hit = [p for p in dict.fromkeys(hit) if p in s.doc._ids]

        def run():
            left = []
            # 여기서 나는 KeyError · ValueError(MarkBlock 포함)는 그대로 올린다 — 트랜잭션(_transact)이 문서 · 오버레이를 직전 상태로 되돌리고 400 으로 답한다(HTTPException 으로 바꾸면 안 되돌린다)
            got = outline_tune.apply(s.doc, ov, pl, left=left)
            changed = list(dict.fromkeys(got["changed"]))
            if not changed and got["split"] is None and not got.get("slot"):   # 대표 · 동결 모양만 바뀐 반영(문단은 그대로)도 실행 취소 1개로 남긴다
                raise ValueError("바뀔 것이 없습니다 — 이미 그 서식입니다")
            seen = list(dict.fromkeys(hit + changed))
            moved = [p for p, x in ov["lines"].items() if got["split"] and x["tpl"] == got["split"]["id"]]
            extra.update({"lines": {p: outline_edit.line_view(ov["lines"][p]) for p in dict.fromkeys(seen + moved) if p in ov["lines"]}, "removed": [],
                          "fmts": outline_match.labels_now(s.doc, ov, seen)})
            made.update({"scope": pl["scope"], "name": f"T{pl['no']} L{pl['level']}", "letter": got["letter"], "was": pl["old"][1], "changed": len(changed), "matched": got["matched"],
                         "kept": len(got["kept"]), "left": left, "split": got["split"], "id": pid})
            return {"hosts": [s.doc._ids[i] for i in seen if i in s.doc._ids], "formatted": set(changed), "struct": set(), "origin": {}, "anchor": pid,
                    "log": {"op": "tune", "ids": [pid], "tune": {"scope": pl["scope"], "tpl": pl["no"], "level": pl["level"], "letter": got["letter"], "changed": len(changed), **({"line2": pl["line2"]} if pl.get("line2") else {}),
                                                                **({"split": got["split"]["name"]} if got["split"] else {}), **({"left": len(left)} if left else {})}}}
        return [s.doc._ids[i] for i in hit], run
    out = server._edit(doc_id, make, "outline", {"op": "tune", **{k: body.get(k) for k in ("id", "letter", "exact", "lead", "gap", "frontMm", "line2", "scope", "start", "upto", "cut") if body.get(k) is not None}})
    if isinstance(out, dict):
        token = secrets.token_hex(8)
        with s0.lock:   # 방금 만든 실행 취소 묶음에 표를 — 창의 「되돌리기」 는 이 표가 맨 위에 있을 때만 되돌린다
            if s0.undo and s0.rev == out.get("rev"):
                s0.undo[-1][UNDO_MARK] = token
                made["undo"] = token
        out["outline"] = extra
        out["tune"] = made
    return out
