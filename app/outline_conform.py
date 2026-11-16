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
- `place(doc, ov, pid, m)` = 줄 하나에 ①② · `needs(…)` = 그 줄이 ①② 에 안 맞는가(문서는 안 바꿈).
- `conform(doc, ov, pid, sh, m)` = **줄 하나를 확정 서식으로**: 접두·문단·글자(`outline_match.match_one`) + ①②.
- `settle(doc, ov, tid, level, ids, m)` = 레벨 하나: 대표 줄에 ①② 를 걸어 확정 서식을 정하고(슬롯의 동결 접두·모양도 그것으로 — Enter 로 만드는 새 줄이 같은 서식),
  대표와 서식이 같던 줄(대표 갈래)과 ids(맞추기로 고른 줄)를 그 서식으로. → 바뀐 줄 id.
- `pending(doc, ov, tids)` = 대표 갈래의 줄 가운데 ①② 가 아직 안 걸린 줄(서식이 대표와 다른 줄은 서식 갈래가 센다) — 조정 줄의 「자리 맞춤 n줄」.
- `after_insert(doc, pid, letter, like, like_letter, m)` = 템플릿 변환(이관·취합이 넣은 줄 — 개요 오버레이 없이 본보기 문단으로): 넣은 줄에 ①② 를 본보기의 꼴대로.
괄호 줄(구분 라벨·괄호 소제목 — 글 전체가 레터) · 표 제목 줄 · 값 칸(표 칸에 혼자 있는 레터) · 접두에 탭이 든 줄 · 접두 폭 50mm 초과 줄에는 걸지 않는다(② §8-1 과 같은 제외).
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


def _gap(doc, pid, letter):
    """(레터 뒤 빈칸의 시작 자리, 그 글) — 묶음 빈칸으로 바꿀 것이 있을 때만(접두가 잴 수 있는 빈칸뿐이고 보통 빈칸이 있음), 아니면 None."""
    lead, tok, gap = OE.prefix_of(doc._text(doc._ids[pid]), letter or None)
    if not tok or " " not in gap or any(ch not in OP.BLANKS for ch in lead + gap):
        return None
    return len(lead) + len(tok), gap


def _target(doc, ov, pid, m):
    """자리 규칙을 걸면 바뀔 (왼쪽 여백, 첫 줄) | None(그대로 · 못 잼)."""
    line = ov["lines"][pid]
    cur = m.place(pid, line.get("letter"))
    if cur is None:
        return None
    try:
        return OP.target(cur, rule(OE._slot(ov, line["tpl"], line["level"])), full=True)
    except ValueError:  # 사람이 정한 레터 위치가 이 줄의 앞 공백 폭보다 작다 — 그 줄은 그대로
        return None


def needs(doc, ov, pid, m):
    """그 줄이 확정 서식의 ①(묶음 빈칸) ②(자리 규칙)에 안 맞는가 — 문서는 안 바꾼다."""
    if _skip(doc, ov, pid):
        return False
    return _gap(doc, pid, ov["lines"][pid].get("letter")) is not None or _target(doc, ov, pid, m) is not None


def place(doc, ov, pid, m):
    """줄 하나에 ①② 를 건다 → 바뀌었는가. 접두의 글자 모양·런은 그대로(빈칸 글자만 제 자리에서 바꾼다)."""
    if _skip(doc, ov, pid):
        return False
    changed = False
    g = _gap(doc, pid, ov["lines"][pid].get("letter"))
    if g is not None:
        changed = doc.set_chars(pid, g[0], nb_gap(g[1]))
    try:
        if OP.align(doc, ov, pid, measure=m, force=True) is not None:
            changed = True
    except ValueError:
        pass
    return changed


def conform(doc, ov, pid, sh, m):
    """줄 pid 를 확정 서식 sh(①② 를 건 대표의 `outline_match.rep_shape`)로 — 접두·문단·레터 글자·본문 바탕 글자 + ①②. 줄 하나를 템플릿 레벨 서식으로 바꾸는 단 하나의 길."""
    OM.match_one(doc, ov, pid, sh)
    place(doc, ov, pid, m)


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


def settle(doc, ov, tid, level, ids=(), m=None):
    """레벨 하나를 확정 서식으로 → 바뀐 줄 id. ① 대표 줄에 묶음 빈칸·자리 규칙 → 그 모양이 확정 서식(슬롯의 동결 접두·모양도 그것으로)
    ② 대표와 서식이 같던 줄(대표 갈래) + ids(맞추기로 고른 그 레벨 줄 — 대표와 다른 갈래)를 그 서식으로. 대표가 없는 레벨은 건드리지 않는다(ids 가 있으면 ValueError)."""
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
    OE._slot(ov, tid, level).update(prefix=sh["prefix"], letter=sh["tok"], attrs=sh["attrs"], bodyChar=sh["body"])  # 새 줄(Enter)도 확정 서식으로
    for p in ids:
        conform(doc, ov, p, sh, m)
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
