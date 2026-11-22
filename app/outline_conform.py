"""확정 서식으로 바꾸기 — 줄을 그 (템플릿, 레벨)의 확정 서식으로 바꾸는 스크립트(spec_hwpx_웹편집 ② §8-8 「확정 서식으로 바꾸기」).

추출(문서 → 템플릿 · 서식)의 짝이다. 템플릿과 서식이 정해지면 문서의 줄을 그 서식으로 **바꾸는** 길은 이 모듈 하나다 —
「대표에 맞추기」·「템플릿 맞추기」(서식 맞추기) · 조정의 「모두 반영」 · 이관·취합의 템플릿 변환(넣은 줄)이 같이 쓴다
(2026-11-16 사용자 "모든 템플릿 및 서식은 역으로 변환하는 스크립트가 있어야 해 … 서식 맞추기, 조정, 템플릿 변환에도 적용" ·
"템플릿의 서식을 사용하도록 하는 건 LLM 이 하지만 그걸 맞추는 건 스크립트로"). 무엇을 대표로 삼고 어느 갈래를 맞출지는 사람·LLM 이 고르고, **맞추는 것은 이 스크립트**다.

- **확정 서식** = 그 레벨 대표 줄의 모양(접두 = 앞 공백 · 레터 · 레터 뒤 빈칸 / 문단 모양 / 레터 글자 / 본문 바탕 글자 — `outline_match.rep_shape`)에 둘을 건 것:
  ① **레터 뒤 빈칸 = 묶음 빈칸**(hp:nbSpace — 블록 글의 U+2002): 한글은 양쪽 정렬 줄에서 레터 뒤의 보통 빈칸을 그 줄의 다른 빈칸과 같이 늘려, 글이 넘어간 문단은 첫 줄의 글 시작이
     줄마다 0.1~1.7mm 오른쪽으로 밀린다. 묶음 빈칸은 폭이 같고(0.5em × 장평) 늘어나지 않는다(한글 PDF 실측 — references/한글_문단모양_줄나눔.md 「묶음 빈칸」).
  ② **자리 규칙**(② §8-1): 사람이 그 레벨에 정한 규칙이 있으면 그것, 없으면 기본 「둘째 줄 = 글 시작」 — 문단이 이미 가진 첫 줄 값도 덮는다(`outline_pos.align(force=True)`).
     대표와 접두 폭이 다른 줄(번호형 「10.」 · 줄 맞춤으로 자간을 줄인 레터)은 제 접두 폭으로 — 값이 아니라 규칙이 같다.
     가운데 · 오른쪽 정렬 줄은 기본 규칙을 안 건다(`outline_pos.free`: 줄 시작이 글 길이로 정해진다) — 확정 꼴은 「내어쓰기 없음」(첫 줄 0 · 왼쪽 여백 그대로 — `outline_pos.unhang`:
     이 변경 전에 넣은 내어쓰기도 없앤다 · 대표와 접두 폭이 다른 줄도 한 상태로 모인다) · 사람이 정한 규칙은 건다.
- `place(doc, ov, pid, m)` = 줄 하나에 ①② · `needs(…)` = 그 줄이 ①② 에 안 맞는가(문서는 안 바꿈).
- `conform(doc, ov, pid, sh, m, left, keep, rules)` = **줄 하나를 확정 서식으로**: 접두·문단·글자(`outline_match.match_one`) + ①② · keep = 본문 강조는 그 줄의 것(넣은 뒤 정리 — `outline_match.own_emph`) · rules 거짓 = ①② 없이 대표의 모양만(가운데 · 오른쪽 정렬 줄은 대표의 「글 시작」 꼴을 제 접두 폭으로 — `_follow`).
- `freeze(ov, tid, level, sh)` = 슬롯의 동결 접두 · 모양을 sh 로(Enter 로 만드는 새 줄 — settle 이 대표에 ①② 를 건 뒤 부른다).
- `settle(doc, ov, tid, level, ids, m, left)` = 레벨 하나: 대표 줄에 ①② 를 걸어 확정 서식을 정하고(슬롯의 동결 접두·모양도 그것으로 — Enter 로 만드는 새 줄이 같은 서식),
  대표와 서식이 같던 줄(대표 갈래)과 ids(맞추기로 고른 줄)를 그 서식으로. → 바뀐 줄 id.
- `pending(doc, ov, tids)` = 대표 갈래의 줄 가운데 ①② 가 아직 안 걸린 줄(서식이 대표와 다른 줄은 서식 갈래가 센다) — 조정 줄의 「자리 맞춤 n줄」.
- `after_insert(doc, pid, letter, like, like_letter, m)` = 템플릿 변환(이관·취합이 넣은 줄 — 개요 오버레이 없이 본보기 문단으로): 넣은 줄에 ①② 를 본보기의 꼴대로.
괄호 줄(구분 라벨·괄호 소제목 — 글 전체가 레터) · 표 제목 줄 · 값 칸(표 칸에 혼자 있는 레터) · 접두에 탭이 든 줄 · 접두 폭 50mm 초과 줄에는 걸지 않는다(② §8-1 과 같은 제외).
짝 표지가 든 줄(형광펜 · 필드 · 변경 추적 — ② §8-8 「짝 표지가 든 줄」): 글을 못 바꾸면 모양만 맞추고 `left` 에 남긴다(`outline_match.match_one`) · 레터 뒤 빈칸이 필드·변경 추적 범위에 걸리면 묶음 빈칸으로 안 바꾼다(`_gap`) —
대표나 대표 갈래의 줄이 그렇다면 그 레벨의 다른 줄도 보통 빈칸 그대로(`_held` — 한 레벨 = 한 서식: 갈라 놓거나 맞추기가 안 끝나지 않게).
"""
from app import outline_edit as OE
from app import outline_match as OM
from app import outline_pos as OP

NB = OP.NB  # 묶음 빈칸(블록 글의 U+2002 ↔ hp:nbSpace)


def rule(slot):
    """그 레벨에 걸 자리 규칙 — 사람이 정한 것(② §8-1 `pos.set`)이 있으면 그것, 없으면 기본(둘째 줄 = 글 시작)."""
    return dict((slot or {}).get("pos") or {"line2": "text"}, set=True)


def _skip(doc, ov, pid):
    line = ov["lines"].get(pid)
    if line is None or line.get("role") in OE.ROOTED or line.get("role") == OE.TABLE or not OM._alive(doc, pid):
        return True
    try:
        return bool(OM.lone_value(doc, ov, pid))
    except (KeyError, ValueError):
        return True


def nb_gap(gap):
    """레터 뒤 빈칸의 확정 꼴 — 보통 빈칸(U+0020)을 묶음 빈칸으로(전각 빈칸·줄 안 바꾸는 빈칸은 그대로)."""
    return gap.replace(" ", NB)


def _gap_at(doc, pid, letter):
    """(레터 뒤 빈칸의 시작 자리, 그 글) — 묶음 빈칸으로 바꿀 보통 빈칸이 있을 때만(접두가 잴 수 있는 빈칸뿐이고 보통 빈칸이 있음), 아니면 None. 표지는 안 본다."""
    lead, tok, gap = OE.prefix_of(doc._text(doc._ids[pid]), letter or None)
    if not tok or " " not in gap or any(ch not in OP.BLANKS for ch in lead + gap):
        return None
    return len(lead) + len(tok), gap


def _hit(doc, p, at, n):
    """글 [at, at+n) 이 필드 · 변경 추적 범위와 겹치면 그 종류("field" | "track"), 아니면 None(형광펜은 안 막는다 — set_chars 가 표지를 지킨다).
    짝이 이 문단 밖에 있는 표지(문단을 넘는 범위 — mark_spans 의 ok 가 거짓)는 시작 표지면 그 자리부터 문단 끝까지 · 끝 표지면 문단 처음부터 그 자리까지로 본다
    (prefix_keep_marks 가 같은 줄을 unpaired 로 막는 것과 어긋나지 않게 — 2026-11-17 검토)."""
    if not hasattr(doc, "own_marks"):  # DocxDoc — 짝 표지를 안 다룬다
        return None
    marks = doc.own_marks(p)
    if not marks:
        return None
    spans, ok = doc.mark_spans(p)
    rng = [(sp["kind"], sp["start"], sp["end"]) for sp in spans if sp["kind"] != "markpen"]
    if not ok:
        paired = {el for sp in spans for el in (sp["begin"], sp["close"])}
        rng += [(mk["kind"], -1, mk["pos"]) if mk["end"] else (mk["kind"], mk["pos"], float("inf"))
                for mk in marks if mk["kind"] != "markpen" and mk["el"] not in paired]
    return next((k for k, x, y in rng if x < at + n and y > at), None)


def _blocked(doc, pid, letter):
    """그 줄의 레터 뒤 보통 빈칸이 필드 · 변경 추적 범위 안이라 묶음 빈칸으로 못 바꾸면 그 종류("field" | "track"), 아니면 None(바꿀 것이 없거나 바꿀 수 있음)."""
    g = _gap_at(doc, pid, letter)
    return _hit(doc, doc._ids[pid], g[0], len(g[1])) if g is not None else None


def _gap(doc, pid, letter):
    """(레터 뒤 빈칸의 시작 자리, 그 글) — 묶음 빈칸으로 바꿀 것이 있을 때만(접두가 잴 수 있는 빈칸뿐이고 보통 빈칸이 있음), 아니면 None.
    레터 뒤 빈칸이 필드(하이퍼링크 …)·변경 추적 범위와 겹치면 None — 그 범위의 글은 바꾸지 않는다(형광펜은 set_chars 가 표지를 지키므로 바꾼다: ② §8-8 「짝 표지가 든 줄」 ·
    문단을 넘는 범위는 _hit). 레벨 전체의 규칙은 _held — needs · place 가 같이 따른다."""
    g = _gap_at(doc, pid, letter)
    if g is None or _hit(doc, doc._ids[pid], g[0], len(g[1])):
        return None
    return g


def _held(doc, ov, tid, level, m=None):
    """그 레벨은 레터 뒤 빈칸을 묶음 빈칸으로 바꾸지 않는가(한 레벨 = 한 서식) — 대표 줄이나 대표와 서식이 같은 줄(대표 갈래)의 레터 뒤 보통 빈칸이 필드 · 변경 추적 범위 안이면
    그 줄은 못 바꾸므로 그 레벨의 다른 줄도 보통 빈칸 그대로 둔다. 전에는 막힌 줄만 보통 빈칸으로 남고 나머지가 묶음 빈칸이 되어 같은 서식이던 줄이 「다른 서식」 으로 갈라졌고,
    대표가 막혔으면 맞추기를 거듭해도 끝나지 않았다(2026-11-17 검토). m(요청 하나 동안의 재개)에 레벨마다 기억한다 — 판정은 그 레벨을 처음 볼 때(바꾸기 전) 한 번."""
    memo = m.__dict__.setdefault("_conform_held", {}) if m is not None else {}
    key = (str(tid), int(level))
    if key not in memo:
        memo[key] = _held_now(doc, ov, tid, level)
    return memo[key]


def _held_now(doc, ov, tid, level):
    if not hasattr(doc, "own_marks"):
        return False
    rep = _rep(doc, ov, tid, level)
    if rep is None:
        return False
    stuck = [p for p in OM.slot_ids(ov, tid, level) if OM._alive(doc, p) and doc.own_marks(doc._ids[p])
             and not _skip(doc, ov, p) and _blocked(doc, p, ov["lines"][p].get("letter"))]
    if not stuck:
        return False
    if rep in stuck:
        return True
    base = OM.look(doc, ov, rep)
    for p in stuck:
        try:
            if OM.same(OM.look(doc, ov, p), base):
                return True
        except (KeyError, ValueError):
            continue
    return False


def _target(doc, ov, pid, m):
    """자리 규칙을 걸면 바뀔 (왼쪽 여백, 첫 줄) | None(그대로 · 못 잼). 기본 규칙을 안 거는 가운데 · 오른쪽 정렬 줄(outline_pos.free)은 내어쓰기가 남았을 때만
    (outline_pos.unhang — 이 변경 전의 확정 서식이 넣은 내어쓰기도 「자리 맞춤」 · 조정이 없앤다: place 와 같은 셈)."""
    line = ov["lines"][pid]
    cur = m.place(pid, line.get("letter"))
    if cur is None:
        return None
    if OP.free(doc, ov, pid):
        return OP.unhang(cur)
    try:
        return OP.target(cur, rule(OE._slot(ov, line["tpl"], line["level"])), full=True)
    except ValueError:  # 사람이 정한 레터 위치가 이 줄의 앞 공백 폭보다 작다 — 그 줄은 그대로
        return None


def needs(doc, ov, pid, m):
    """그 줄이 확정 서식의 ①(묶음 빈칸) ②(자리 규칙)에 안 맞는가 — 문서는 안 바꾼다."""
    if _skip(doc, ov, pid):
        return False
    line = ov["lines"][pid]
    return (not _held(doc, ov, line["tpl"], line["level"], m) and _gap(doc, pid, line.get("letter")) is not None) or _target(doc, ov, pid, m) is not None


def place(doc, ov, pid, m):
    """줄 하나에 ①② 를 건다 → 바뀌었는가. 접두의 글자 모양·런은 그대로(빈칸 글자만 제 자리에서 바꾼다)."""
    if _skip(doc, ov, pid):
        return False
    changed = False
    line = ov["lines"][pid]
    g = None if _held(doc, ov, line["tpl"], line["level"], m) else _gap(doc, pid, line.get("letter"))  # 레벨 규칙이 먼저(_held — 한 레벨 = 한 서식)
    if g is not None:
        changed = doc.set_chars(pid, g[0], nb_gap(g[1]))
    try:   # 가운데 · 오른쪽 정렬 줄은 기본 규칙을 안 건다 — 내어쓰기만 없앤다(outline_pos.free · unhang — align 이 본다)
        if OP.align(doc, ov, pid, measure=m, force=True) is not None:
            changed = True
    except ValueError:
        pass
    return changed


def conform(doc, ov, pid, sh, m, left=None, keep=None, rules=True):
    """줄 pid 를 확정 서식 sh(①② 를 건 대표의 `outline_match.rep_shape`)로 — 접두·문단·레터 글자·본문 바탕 글자 + ①②. 줄 하나를 템플릿 레벨 서식으로 바꾸는 단 하나의 길.
    left = 짝 표지 때문에 모양만 맞춘 줄을 적을 목록(`outline_match.match_one` — 그런 줄에도 ①② 는 건다).
    keep = 본문 바탕 글자에서 그 줄의 것을 지킬 강조(`outline_match.EMPH` — 넣은 뒤 정리가 넣는 쪽의 서식을 받는 레벨에서: spec_병합 ② §5-9) · None 이면 전처럼 모두 대표 것.
    rules = ①② 도 거나 — 거짓이면 대표의 모양 그대로만(대표가 ①② 를 갖추지 않은 레벨에서 그 레벨의 다른 줄은 두고 넣은 줄만 맞출 때: 취합의 넣은 뒤 정리 — spec_병합 ② §5-9 9 ⓐ)
    · 가운데 · 오른쪽 정렬 줄은 대표의 「둘째 줄 = 글 시작」 꼴을 제 접두 폭으로 따른다(`_follow`)."""
    OM.match_one(doc, ov, pid, OM.own_emph(doc, ov, pid, sh, keep) if keep else sh, left)
    if rules:
        place(doc, ov, pid, m)
    elif pid in (ov.get("lines") or {}) and OP.free(doc, ov, pid):   # 가운데 · 오른쪽 정렬 줄 — 대표의 꼴을 따른다(_follow)
        _follow(doc, ov, pid, sh, m)


def _follow(doc, ov, pid, sh, m):
    """rules 거짓으로 대표의 모양만 받은 가운데 · 오른쪽 정렬 줄(outline_pos.free): 대표가 「둘째 줄 = 글 시작」 꼴(이 변경 전의 확정 서식이 넣은 내어쓰기)이면
    그 줄도 **제** 접두 폭으로(`after_insert` 와 같은 꼴 따르기) → 바뀌었는가. 대표의 문단 모양을 그대로 받으면 내어쓰기가 대표의 접두 폭이라, 접두 폭이 다른 줄
    (「1.」 대표 옆의 「10.」 · 줄 맞춤으로 자간을 지킨 레터)은 둘째 줄이 제 글 시작이 아니어서 대표와 끝내 「다른 서식」 으로 남았다(2026-11-22 검토 — 취합의 넣은 뒤 정리:
    대표가 옛 내어쓰기를 가지면 `needs` 가 참이라 `merge_retidy_api._full` 이 거짓). 대표의 내어쓰기는 「자리 맞춤」 · 조정이 없앤다(unhang) — 그 뒤에는 모두 내어쓰기 없는 꼴.
    sh 가 그 레벨 대표의 문단 모양이 아니면(대표를 못 읽음) 대표의 모양 그대로."""
    if _skip(doc, ov, pid):
        return False
    line = ov["lines"][pid]
    rep = _rep(doc, ov, line["tpl"], line["level"])
    if rep is None or rep == pid or doc._ids[rep].get("paraPrIDRef", "0") != (sh.get("attrs") or {}).get("paraPrIDRef"):
        return False
    return after_insert(doc, pid, line.get("letter"), rep, ov["lines"][rep].get("letter"), m)


def freeze(ov, tid, level, sh):
    """슬롯의 동결 접두 · 모양을 확정 서식 sh(`outline_match.rep_shape`)로 — Enter 로 만드는 새 줄이 같은 서식(settle · 대표에 ①② 를 건 뒤의 넣은 뒤 정리)."""
    OE._slot(ov, tid, level).update(prefix=sh["prefix"], letter=sh["tok"], attrs=sh["attrs"], bodyChar=sh["body"])


def _rep(doc, ov, tid, level):
    """그 레벨의 대표 줄 | None(대표 없음 · 문서에 없음 · 그 레벨 줄이 아님 · 값 칸)."""
    sl = OE._slot(ov, tid, level)
    rep = (sl or {}).get("rep")
    if not rep or rep not in ov["lines"] or not OM._alive(doc, rep):
        return None
    x = ov["lines"][rep]
    if x.get("tpl") != str(tid) or int(x.get("level", -1)) != int(level) or OM.lone_value(doc, ov, rep):
        return None
    return rep


def _mates(doc, ov, tid, level, rep, skip=()):
    """대표 갈래 — 그 레벨에서 대표와 비교 값이 같은 줄(대표 빼고 · skip 빼고)."""
    base, out = OM.look(doc, ov, rep), []
    for p in OM.slot_ids(ov, tid, level):
        if p == rep or p in skip or not OM._alive(doc, p):
            continue
        try:
            if not OM.lone_value(doc, ov, p) and OM.same(OM.look(doc, ov, p), base):
                out.append(p)
        except (KeyError, ValueError):
            continue
    return out


def settle(doc, ov, tid, level, ids=(), m=None, left=None, keep=None):
    """레벨 하나를 확정 서식으로 → 바뀐 줄 id. ① 대표 줄에 묶음 빈칸·자리 규칙 → 그 모양이 확정 서식(슬롯의 동결 접두·모양도 그것으로)
    ② 대표와 서식이 같던 줄(대표 갈래) + ids(맞추기로 고른 그 레벨 줄 — 대표와 다른 갈래)를 그 서식으로. 대표가 없는 레벨은 건드리지 않는다(ids 가 있으면 ValueError).
    left = ids 가운데 짝 표지 때문에 모양만 맞춘 줄을 적을 목록(`conform`) — 그 줄도 바뀐 줄에 든다. keep = ids 의 본문 강조를 지킴(`conform`)."""
    rep = _rep(doc, ov, tid, level)
    if rep is None:
        if ids:
            raise ValueError(f"L{level} 의 대표 문단이 문서에 없습니다 — 줄 하나를 대표로 정한 뒤 맞추세요")
        return []
    m = m or OP.Measure(doc)
    ids = [p for p in ids if p != rep]
    mates = _mates(doc, ov, tid, level, rep, set(ids))
    out = [rep] if place(doc, ov, rep, m) else []
    sh = OM.rep_shape(doc, ov, rep)
    freeze(ov, tid, level, sh)  # 새 줄(Enter)도 확정 서식으로
    for p in ids:
        conform(doc, ov, p, sh, m, left, keep)
        out.append(p)
    for p in mates:
        if place(doc, ov, p, m):
            out.append(p)
    return out


def settle_templates(doc, ov, tids, m=None):
    """템플릿들의 모든 레벨을 확정 서식으로(대표 갈래의 줄만 — 서식이 대표와 다른 갈래는 맞추기가 고른 것만 바뀐다) → 바뀐 줄 id."""
    m, out = m or OP.Measure(doc), []
    for tid in tids:
        t = ov["templates"].get(str(tid))
        for lv in sorted((t or {}).get("slots", {}), key=int):
            try:
                out += settle(doc, ov, str(tid), int(lv), (), m)
            except (KeyError, ValueError):
                continue
    return out


def pending(doc, ov, tids=None):
    """①② 가 아직 안 걸린 줄(레벨마다 대표와 그 갈래의 줄) → [줄 id]. tids = 볼 템플릿(없으면 모두). 문서는 안 바꾼다."""
    m, out = OP.Measure(doc), []
    for tid, t in ov["templates"].items():
        if tids is not None and str(tid) not in tids:
            continue
        for lv in sorted(t.get("slots", {}), key=int):
            try:
                rep = _rep(doc, ov, tid, lv)
                if rep is None:
                    continue
                out += [p for p in [rep, *_mates(doc, ov, tid, lv, rep)] if needs(doc, ov, p, m)]
            except (KeyError, ValueError):
                continue
    return out


def lines_of(doc, ov, tids):
    """그 템플릿들의 줄 가운데 확정 서식이 닿을 수 있는 줄(문서에 있는 것 — 괄호 줄·표 제목 줄 빼고) — 편집 트랜잭션이 「닿는 문단」 으로 미리 잡아 둔다."""
    tids = {str(t) for t in tids}
    return [p for p, x in ov["lines"].items() if x.get("tpl") in tids and x.get("role") not in OE.ROOTED and x.get("role") != OE.TABLE and OM._alive(doc, p)]


def after_insert(doc, pid, letter, like, like_letter, m=None):
    """템플릿 변환(이관·취합이 넣은 줄 — 개요 오버레이 없이 본보기 문단 like 의 모양을 입힌 뒤): 넣은 줄 pid 에 ①② 를 **본보기의 꼴대로** 건다 → 바뀌었는가.
    ① 본보기의 레터 뒤 빈칸이 묶음 빈칸이면 넣은 줄도(접두는 본보기 것을 복사하므로 보통 이미 같다) ② 본보기가 「둘째 줄 = 글 시작」 꼴(내어쓰기 = 접두 폭)이면
    넣은 줄도 제 접두 폭으로(번호형 「10.」 처럼 접두 폭이 본보기와 다른 줄). 본보기가 그 꼴이 아니면(조정 전 문서) 건드리지 않는다 — 본보기 모양 그대로."""
    m = m or OP.Measure(doc)
    at = m.place(like, like_letter) if like else None
    cur = m.place(pid, letter)
    if at is None or cur is None or abs(at["line2Mm"] - at["textMm"]) > OP.EPS * 2:
        return False
    try:
        t = OP.target(cur, {"line2": "text", "set": True}, full=True)
    except ValueError:
        return False
    if t is None:
        return False
    doc.format_para([pid], {"indentLeftMm": t[0], "firstLineMm": t[1]})
    return True
