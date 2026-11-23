"""개요 줄의 헤딩 고치기(spec_hwpx_웹편집 ② §8-12 — 2026-11-24 전의 이름 「레터 고치기」) — 고른 개요 줄의 **레터 · 레터 앞 빈칸 · 레터 뒤 빈칸 · 앞 여백 · 2번째 줄**을 고치고,
그 고침을 어디까지 걸지(범위)를 고른다.

2026-11-23 사용자 "문장을 선택하고 레더를 클릭할 수 있고 레터를 변경할 수 있도록 레터 옵션을 줘, 문자 숫자, 둥근숫자 포함해서, 그리고 앞 여백, 레터 뒤여백을 조절할 수 있게 해줘,
그리고 수정을 했잖아. 그럼 이제 그 서식 전체를 변경할 수 있는 옵션을 제공해줘, . 되돌릴 수 있는 옵션도 주고, , 전체서식변경으로 할 수 있는 옵션 해당 문단/헤딩만 수정할 수 있는 옵션을 주고
선택할 수 있게 해줘, ,, T1L5 이였는데 여기서 변경된 템플릿을 추가할 수 있도록해줘"(astra 협의 — artifacts/letter_tune_astra_2026-11-23).
2026-11-24 사용자 "레터 앞 빈칸 뒤 빈칸도 칸이랑 mm 둘다 할 수 있게 해줘, 그리고 새 탬플릿으로 추가 할떄 t1L6 부터 어디까지 알수 있고 선택할 수 있어야 함, … 대표도 새 탬플릿을 할 수 있지..
T1L1 하고 T1L2 를 T3L1 로 할 수 있지 종속관계로 만들 수 있잖아? … 2번째 줄을 레터 앞에 맞출건지 레터 뒤의 첫번째 문자/글자에 맞출건지. 또는 여백으로 맞출건지를 선택할 수 있게 해줘 …
근데 새 템플릿으로 나누기 기능이 있네" — 「새 템플릿으로」 는 라벨의 「나누기」(② §8-13 `outline_match.cut` — 자리로: 대표 줄도)와 같은 길이고 시작 · 끝 레벨을 고른다 · 2번째 줄 규칙 셋.

- 범위(`SCOPES`): `line` 「이 문단만 수정」 · `level` 「서식 전체 변경」(그 (템플릿, 레벨)의 줄 모두 — 이 줄을 대표로 삼고 맞춤) ·
  `split` 「새 템플릿으로 나누기」(이 줄 — 또는 고른 시작 레벨의 윗줄 — 부터 새 템플릿 「T1L5a」 로: 시작 레벨 `start` · 끝 레벨 `upto`(더 깊은 아래 줄은 원래 템플릿에 남음) ·
  `cut` 「here」 그 줄과 아래 | 「all」 그 레벨 줄 모두 — 값을 바꿨으면 새 템플릿의 이 줄 레벨을 이 줄의 서식으로: 「서식 전체 변경」 을 새 템플릿 안에서).
- **2번째 줄**(`line2` — 「text」 글 시작 · 「letter」 레터 · 「front」 앞 여백: outline_pos 의 자리 규칙): 이 문단만 = 그 줄에만 건 규칙(오버레이 줄의 `pos`) · 서식 전체 변경 · 새 템플릿 = 그 레벨의 규칙.
- **레터가 달라지면 다른 템플릿이다**(사용자 11-16 「헤딩레터가 다르면 종속 템플릿이야」): 레터 계열(`outline_match.kin`)이 바뀌는 고침은 「이 문단만」 으로 못 한다 — 그 줄만 다른 레터인 채 그 레벨에 남으면
  Enter · 번호 매김이 옛 레터로 돈다(astra P1). 「서식 전체 변경」 이나 「새 템플릿으로 나누기」 로만. 닮은 글자(「o」·「○」)와 같은 꼴의 다른 번호는 같은 레터라 「이 문단만」 으로 된다.
- 새 길을 만들지 않는다 — 줄을 대표 서식으로 바꾸는 것은 `outline_conform.conform`(= `outline_match.match_one` + 확정 서식 ② §8-8), 대표 = `outline_match.set_rep`, 나누기 = `outline_match.cut`(② §8-13).
  이 모듈의 새 일은 **줄 하나의 접두를 조각마다 제자리에서 바꾸는 것**(`retoken` — 런 · 글자 모양 · 표지는 그대로: hwpx_struct `_swap_piece`)과 그 차례를 엮는 것(`plan` → `apply`)뿐이다.
  레터 글자는 늘 `retoken` 이 먼저 바꾼다 — `match_one` 의 번호 셈에 맡기지 않는다(기호 「o」 를 영문 15번째로 읽어 「⑮」 를 만든다: astra).
- 문서 · 오버레이를 바꾸는 것은 `apply` 하나(부른 쪽이 트랜잭션 안에서 — app/outline_tune_api.py). `suggest` · `plan` · `preview` 는 읽기만 한다.
"""
import copy

from app import heading_rules as HR
from app import outline_conform as OC
from app import outline_edit as OE
from app import outline_grow as OG
from app import outline_match as OM
from app import outline_pos as OP
from app import para_letter as PL
from app.hwpx_struct import MARK_BEGIN, MARK_KIND, MARKERS, RUN, T, MarkBlock

SCOPES = ("line", "level", "split")
LEAD_MAX = OG.LEAD_MAX   # 레터 앞 빈칸 칸 수 상한(레벨 더하기와 같다)
GAP_MAX = 8              # 레터 뒤 빈칸 칸 수 상한
FRONT_MAX = 150.0        # 앞 여백(mm) 상한
EPS = 0.05               # mm — 같은 앞 여백으로 보는 차(화면은 0.1mm 로 보인다)
SHOW = 6                 # 미리보기에 싣는 줄 수(레터가 바뀌는 줄의 본보기)


# ---------------------------------------------------------------- 읽기
def line_of(doc, ov, pid):
    """고칠 수 있는 개요 줄 → 그 줄. 아니면 ValueError(까닭)."""
    x = (ov.get("lines") or {}).get(pid)
    if x is None:
        if pid in (ov.get("autos") or {}):
            raise ValueError("자동 글머리표·문단 번호 줄은 레터가 글에 없습니다 — 「대표에 맞추기」 로 친 레터로 바꾼 뒤 고치세요")
        raise ValueError("개요 줄이 아닙니다 — 헤딩 추출 2단계가 템플릿을 매긴 줄에서만 됩니다(다른 문단은 도구 줄 「레터 넣기」 에서 개요 레벨을 고르세요)")
    if x.get("role") in OE.ROOTED:
        raise ValueError(f"{'구분 라벨' if x['role'] == 'label' else '괄호 소제목'} 줄은 글 전체가 레터라 여기서 고치지 않습니다")
    if x.get("role") == OE.TABLE:
        raise ValueError("표 제목 줄은 레터가 없습니다")
    if not OM._alive(doc, pid):
        raise ValueError("그 문단이 지금 문서에 없습니다 — 다시 읽어 주세요")
    if OM.lone_value(doc, ov, pid):
        raise ValueError("값 칸(표 칸에 혼자 있는 레터)은 개요 줄로 고치지 않습니다")
    if not OM.parts(doc, ov, pid)[1]:
        raise ValueError("그 줄의 첫머리에 레터가 없습니다")
    if str(x["tpl"]) not in ov["templates"] or OE._slot(ov, x["tpl"], x["level"]) is None:
        raise ValueError("그 줄의 템플릿 레벨이 없습니다 — 문서를 다시 읽어 주세요")
    return x


def mode_of(at, prefer=None):
    """줄의 2번째 줄이 어느 자리에 있나(자리 cur = outline_pos.Measure.place) → 「text」 글 시작 | 「letter」 레터 | 「front」 앞 여백 | None(그 밖 — 직접 mm …).
    둘 이상이 같은 자리면(레터 앞 빈칸 0칸 = 레터 = 앞 여백) prefer(그 레벨의 규칙)를 먼저, 없으면 글 시작 · 레터 · 앞 여백 차례."""
    if not at:
        return None
    spots = {"text": at["textMm"], "letter": at["letterMm"], "front": at["x0"]}
    hits = [k for k in OP.LINE2_REL if abs(at["line2Mm"] - spots[k]) <= EPS]
    return (prefer if prefer in hits else hits[0]) if hits else None


def now(doc, ov, pid, m=None):
    """줄의 지금 값 {letter, lead(칸), gap(칸), frontMm(앞 여백 — 첫 줄이 시작하는 자리 = 왼쪽 여백 + 첫 줄 들여쓰기), letterMm, textMm, line2Mm, leadMm · gapMm(빈칸 폭),
    line2(2번째 줄이 어느 자리에 있나 — mode_of)} — 못 재는 자리는 None."""
    lead, tok, gap, _plen, _text = OM.parts(doc, ov, pid)
    m = m or OP.Measure(doc)
    at = m.place(pid, tok) or {}
    x = ov["lines"].get(pid) or {}
    r = lambda v: None if v is None else round(v, 1)  # noqa: E731
    w = widths(doc, ov, pid, m)
    rule = (OC.rule(OE._slot(ov, x.get("tpl"), x.get("level")) if x else None) or {}).get("line2")
    return {"letter": tok, "lead": len(lead), "gap": len(gap), "frontMm": r(at.get("x0")), "letterMm": r(at.get("letterMm")), "textMm": r(at.get("textMm")), "line2Mm": r(at.get("line2Mm")),
            "leadMm": _sum(w["lead"]), "gapMm": _sum(w["gap"]), "line2": mode_of(at or None, (x.get("pos") or {}).get("line2") or rule)}


def _sum(ws):
    return None if ws is None or any(v is None for v in ws) else round(sum(ws), 2)


def widths(doc, ov, pid, m=None):
    """빈칸 폭(mm) — {lead: [레터 앞 빈칸 글자마다], gap: [레터 뒤 빈칸 글자마다], leadAdd · gapAdd(칸을 늘리면 더할 빈칸 글자 하나의 폭)} · 못 재면 그 자리 None.
    화면이 칸 ↔ mm 를 바꿔 보이는 데 쓴다(줄이면 앞에서부터 남고 늘리면 끝에 그 조각의 마지막 빈칸 글자를 — `_resize`)."""
    from app.heading_extract import _cid_at, run_ranges
    m = m or OP.Measure(doc)
    lead, tok, gap, _plen, _text = OM.parts(doc, ov, pid)
    p = doc._ids[pid]
    rr, fb = run_ranges(doc, p), doc._char_id(p)
    cid = lambda i: _cid_at(rr, max(i, 0), fb)  # noqa: E731
    sl = OE._slot(ov, (ov["lines"].get(pid) or {}).get("tpl"), (ov["lines"].get(pid) or {}).get("level")) or {}
    a, b = len(lead), len(lead) + len(tok)
    r2 = lambda v: None if v is None else round(v, 2)  # noqa: E731
    return {"lead": [r2(m.advance(ch, cid(i))) for i, ch in enumerate(lead)], "gap": [r2(m.advance(ch, cid(b + i))) for i, ch in enumerate(gap)],
            "leadAdd": r2(m.advance(_blank(lead), cid(a - 1 if lead else a))), "gapAdd": r2(m.advance(_blank(gap, nb=OP.NB in (sl.get("prefix") or "")), cid(b + len(gap) - 1 if gap else b - 1)))}


def _split_name(ov, tid, level):
    """새 서식 종속 템플릿의 표기(「T1L5a」)와 글자 — 글자가 다 찼으면 (None, None)."""
    sfx = OM._free_sfx(ov, tid, level)
    return (f"T{ov['templates'][str(tid)]['no']}L{level}{sfx}", sfx) if sfx else (None, None)


def others(doc, ov, pid, tid, level, rep=None):
    """그 레벨의 다른 줄을 「서식 전체 변경」 의 눈으로 가른다(오버레이는 안 바꾼다) → {"diff": 이 줄과 서식이 다른 줄(맞출 줄), "same": 이미 같은 줄,
    "own": 표의 서식이라 맞추지 않는 줄(② §8-11 — **지금 대표** rep 기준: 대표를 바꾼 뒤에 다시 세면 방금까지 대표 서식이던 표까지 든다), "skip": 자동 글머리 줄 · 값 칸 · 못 읽는 줄}. 문서 순."""
    order = OM._order(doc)
    mine = OM.look(doc, ov, pid)
    rows, skip, auto = [], [], []
    for p in sorted(OM.slot_ids(ov, tid, level), key=lambda q: order.get(q, 1 << 30)):
        if p == pid:
            continue
        if p not in ov["lines"]:   # 자동 글머리 줄(ov["autos"]) — 레터가 글에 없다
            auto.append(p)
            skip.append(p)
            continue
        if not OM._alive(doc, p) or OM.lone_value(doc, ov, p):
            skip.append(p)
            continue
        try:
            rows.append((p, OM.look(doc, ov, p)))
        except (KeyError, ValueError):
            skip.append(p)
    own = set()
    if rep and rep in ov["lines"] and OM._alive(doc, rep):
        try:
            base = mine if rep == pid else OM.look(doc, ov, rep)
            forms = OM.rep_forms([base, mine] + [lk for _, lk in rows], base)
            own = {p for p, lk in rows if p != rep and not OM.same(lk, base) and OM.is_own(lk, base, forms)}
        except (KeyError, ValueError):
            own = set()
    return {"diff": [p for p, lk in rows if p not in own and not OM.same(lk, mine)], "same": [p for p, lk in rows if p not in own and OM.same(lk, mine)],
            "own": [p for p, _ in rows if p in own], "skip": skip, "auto": auto}


def suggest(doc, ov, pid):
    """창을 열 때 보일 것 → {id, tpl, no, level, name(「T1 L5」), run(그래프 실행), cur(now), rep{id, …now} | None, isRep, differs[[이름, 이 줄, 대표]…], text(글 앞머리 — 견본),
    numbered(번호형 레벨), symbols[…], numbers[…], limits{lead, gap, front, letter}}. 범위마다의 수 · 가능 여부는 `preview`. 고칠 수 없는 줄이면 ValueError."""
    x = line_of(doc, ov, pid)
    tid, level = str(x["tpl"]), int(x["level"])
    t, sl = ov["templates"][tid], OE._slot(ov, tid, level)
    m = OP.Measure(doc)
    rep = OC._rep(doc, ov, tid, level)
    differs = []
    if rep and rep != pid:
        differs = [[name, mine, reps] for _k, name, reps, mine in OM.diff(OM.look(doc, ov, rep), OM.look(doc, ov, pid))]  # [이름, 이 줄, 대표]
    lead, tok, gap, plen, text = OM.parts(doc, ov, pid)
    pos = OC.rule(sl)
    return {"id": pid, "tpl": tid, "no": t["no"], "level": level, "name": f"T{t['no']} L{level}", "run": ov.get("run"), "cur": now(doc, ov, pid, m),
            "rep": ({"id": rep, **now(doc, ov, rep, m)} if rep else None), "isRep": rep == pid, "differs": differs, "text": text[plen:plen + 40],
            "leadCh": _blank(lead), "gapCh": _blank(gap, nb=OP.NB in (sl.get("prefix") or "")), "numbered": OE.is_numbered(sl.get("key") or x.get("key") or ""),
            "widths": widths(doc, ov, pid, m),
            "rule": {"line2": pos.get("line2"), **({"mm": pos["mm"]} if pos.get("mm") is not None else {}), "set": bool((sl.get("pos") or {}).get("set"))},   # 그 레벨의 2번째 줄 규칙
            "own": (x.get("pos") or {}).get("line2"),   # 이 줄에만 건 2번째 줄 규칙(「이 문단만」 으로 건 것)
            "tplLevels": tpl_levels(ov, tid), "ancestors": ancestors(ov, pid),   # 새 템플릿으로 나누기 — 시작 · 끝 레벨을 고르는 자료
            "symbols": list(PL.SYMBOLS), "numbers": [n for n in PL.NUMBERS if _ordered(n)], "limits": {"lead": LEAD_MAX, "gap": GAP_MAX, "front": FRONT_MAX, "letter": PL.LETTER_MAX}}


def tpl_levels(ov, tid):
    """템플릿의 레벨 → [{level, letter, lines(그 레벨 줄 수)}](L base+1 부터 · 레벨 차례) — 나누기의 시작 · 끝 레벨 고르기에 보인다."""
    t = ov["templates"][str(tid)]
    count = {}
    for y in ov["lines"].values():
        if y["tpl"] == str(tid):
            count[int(y["level"])] = count.get(int(y["level"]), 0) + 1
    return [{"level": int(k), "letter": sl.get("letter") or sl.get("key") or "", "lines": count.get(int(k), 0), **({"table": True} if sl.get("table") else {})}
            for k, sl in sorted(t.get("slots", {}).items(), key=lambda kv: int(kv[0])) if int(k) > OM._base(t)]


def ancestors(ov, pid):
    """줄 pid 와 그 윗줄 가운데 **같은 템플릿**의 줄 → {레벨: 줄 id}(가장 가까운 것) — 나누기의 시작 레벨 후보(그 레벨의 윗줄부터 새 템플릿)."""
    x = ov["lines"][pid]
    tid, out, cur, seen = x["tpl"], {}, pid, set()
    while cur and cur not in seen:
        seen.add(cur)
        y = ov["lines"].get(cur)
        if y is None or y["tpl"] != tid:
            break
        out.setdefault(str(int(y["level"])), cur)
        cur = y.get("parent")
    return out


# ---------------------------------------------------------------- 레터 · 번호
def _key(letter):
    """레터 → 정규 레터 키. 개요 레터로 안 읽히면 ValueError(레터 넣기 · 레벨 더하기와 같은 내장 규칙)."""
    PL.check(letter)
    return OG.letter_key(letter)


def _ordered(letter):
    """개요 편집(Enter · 번호 다시 매김 · 대표에 맞추기)이 번호를 이어 매길 줄 아는 번호 꼴인가 — 「①」 · 「1.」 · 「가.」 · 「a)」 … (「⑴」 · 「❶」 · 「㉠」 · 「㉮」 는 아니다: 같은 글자를 되풀이한다)."""
    try:
        return OE.is_numbered(_key(letter)) and bool(OE.numbers_of(letter)) and OE.succ(letter) not in (None, letter)
    except ValueError:
        return False


def _parent_letter(ov, x):
    par = ov["lines"].get(x.get("parent")) if x.get("parent") else None
    if par is None or not OE.is_numbered(par.get("key") or ""):
        return None
    return par.get("letter") or None


def _numbered_token(letter, parent_letter, k):
    """번호형 레터 letter 의 꼴에 번호 k(합성 번호 「1-1.」 은 앞 번호를 부모 것으로) → 레터. 번호 열을 넘으면 ValueError."""
    base = OE.first(letter, parent_letter) or letter
    nums = OE.numbers_of(base)
    if not nums:
        return letter
    nums[-1] = int(k)
    tok = OE.with_numbers(base, nums)
    if tok is None or OE.numbers_of(tok) != nums:
        raise ValueError(f"「{letter}」 꼴로는 {k}번째를 적을 수 없습니다(번호 열의 끝) — 다른 번호 꼴을 고르세요")
    return tok


def tokens(doc, ov, pid, letter, ids, exact=False):
    """ids(같은 (템플릿, 레벨)의 줄 — pid 포함)의 새 레터 {줄: 레터}. letter = 고른 레터(번호형은 꼴).
    기호 → 모두 그 글자. 번호형 → 지금 번호형인 줄은 제 번호를 그 꼴로, 번호가 없던 줄이 하나라도 있으면 **같은 그릇 · 같은 윗줄 아래 형제 차례로 1부터**.
    exact = 직접 입력(적은 그대로 — pid 줄에만). 번호형인지는 글자가 아니라 **키**로 본다(기호 「o」 는 번호가 아니다)."""
    key = _key(letter)
    if not OE.is_numbered(key):
        return {p: letter for p in ids}
    order = OM._order(doc)
    was = {p: OE.is_numbered(ov["lines"][p].get("key") or "") and bool(OE.numbers_of(ov["lines"][p]["letter"])) for p in ids}
    plain = not all(was.values())
    groups = {}
    for p in sorted(ids, key=lambda q: order.get(q, 1 << 30)):
        groups.setdefault((doc._ids[p].getparent(), ov["lines"][p].get("parent")), []).append(p)   # 열쇠 = 그릇 요소 자체(셈이 끝날 때까지 쥐고 있다 — 주소가 다시 쓰이지 않게)
    out = {}
    for sib in groups.values():
        for i, p in enumerate(sib, 1):
            y = ov["lines"][p]
            if exact and p == pid:
                out[p] = letter
                continue
            k = i if plain else OE.numbers_of(y["letter"])[-1]
            out[p] = _numbered_token(letter, _parent_letter(ov, y), k)
    return out


# ---------------------------------------------------------------- 줄 하나의 접두를 제자리에서
class Guard:
    """**앞 문단에서 열려 뒤 문단에서 닫히는** 필드 · 변경 추적 범위 안의 문단인가 — 그런 문단은 제 표지가 없어(`own_marks` 가 빔) 표지 검사에 안 걸린다(astra 2차 P1).
    그릇(구역 · 표 칸)마다 한 번 훑어 기억한다(요청 한 번 동안 — 미리보기와 반영이 같은 눈으로 본다). 형광펜은 글을 바꿔도 되는 표지라 세지 않는다."""

    def __init__(self, doc):
        self.doc, self._seen = doc, {}

    def enclosed(self, p):
        par = p.getparent()
        if par is None:
            return None
        got = self._seen.get(par)
        if got is None:
            got = self._seen[par] = self._scan(par, p.tag)
        return got.get(p)

    def _scan(self, par, tag):
        if next((el for el in par.iter(*MARKERS) if MARK_KIND.get(el.tag) != "markpen"), None) is None:
            return {}
        out, opened = {}, {}
        for q in par.iterchildren(tag):
            if opened:
                out[q] = next(iter(opened.values()))
            for mk in self.doc.own_marks(q):
                if mk["kind"] == "markpen":
                    continue
                el = mk["el"]
                key = ("field", el.get("beginIDRef") if mk["end"] else el.get("id")) if mk["kind"] == "field" else ("track", mk["type"], el.get("Id"))
                if mk["end"]:
                    opened.pop(key, None)
                elif el.tag in MARK_BEGIN:
                    opened[key] = mk["kind"]
        return out


def _blank(s, nb=False):
    """빈칸 조각 s 를 늘릴 때 쓸 글자 — 그 조각의 마지막 글자(잴 수 있는 빈칸일 때), 없으면 반각(nb 면 묶음 빈칸)."""
    return s[-1] if s and s[-1] in OP.BLANKS else (OP.NB if nb else " ")


def _resize(old, n, nb=False):
    """빈칸 조각 old 를 n칸으로 — **늘리고 줄이는 만큼만** 바꾼다(있던 빈칸의 종류 · 차례는 그대로: 반각 · 전각 · 묶음 빈칸이 섞인 조각). 탭 · 줄 바꿈이 든 조각은 ValueError."""
    if any(ch not in OP.BLANKS for ch in old):
        raise ValueError("이 줄의 빈칸에 탭 · 줄 바꿈이 들어 있어 칸 수로 고칠 수 없습니다")
    return old[:n] if n <= len(old) else old + _blank(old, nb) * (n - len(old))


def _narrow(s, old, new):
    """조각 [s, s+len(old)) 의 old → new 에서 **실제로 달라지는 가운데만** (시작, 끝, 새 글) — 앞뒤의 같은 글자는 건드리지 않는다(그 글자의 런 · 글자 모양이 그대로:
    「1.」→「2.」 는 숫자만 · 빈칸을 늘리면 조각 끝에 더할 칸만 — astra 2차)."""
    i = 0
    while i < min(len(old), len(new)) and old[i] == new[i]:
        i += 1
    j = 0
    while j < min(len(old), len(new)) - i and old[len(old) - 1 - j] == new[len(new) - 1 - j]:
        j += 1
    return s + i, s + len(old) - j, new[i:len(new) - j]


def pieces_of(doc, pid, old, new, guard=None):
    """줄의 접두 (lead, tok, gap) = old 를 new 로 바꿀 때 제자리에서 바꿀 조각 [(시작, 끝, 새 글)…](뒤에서부터) — **문서는 안 바꾼다**. 못 바꾸는 줄은 MarkBlock / ValueError
    (짝 표지가 바꿀 조각에 걸림 · 문단을 넘는 필드 · 변경 추적 범위 안 · 자동 번호가 든 접두 — `prefix_keep_marks` 와 같은 검사). 미리보기(`plan`)와 반영(`retoken`)이 같이 쓴다."""
    p = doc._ids[pid]
    lead, tok, gap = old
    a, b = len(lead), len(lead) + len(tok)
    plen = b + len(gap)
    if doc._text(p)[:plen] != lead + tok + gap:
        raise ValueError("접두(레터 앞 빈칸 · 레터 · 레터 뒤 빈칸)가 지금 문단 글과 다릅니다 — 다시 읽어 주세요")
    pieces = [_narrow(s, o, n) for s, o, n in ((b, gap, new[2]), (a, tok, new[1]), (0, lead, new[0])) if o != n]
    if not pieces:
        return []
    kind = (guard or Guard(doc)).enclosed(p)
    if kind:
        raise MarkBlock(kind, ["필드" if kind == "field" else "변경 추적"])
    marks = doc.own_marks(p)
    if marks:
        spans, ok = doc.mark_spans(p)
        kinds = doc.mark_names(p)
        if not ok:
            raise MarkBlock("unpaired", kinds)
        for s, e, _ in pieces:
            if e > s and any(s < mk["pos"] < e for mk in marks):
                raise MarkBlock("inside", kinds)
            for sp in spans:
                u, v = sp["start"], sp["end"]
                if sp["kind"] != "markpen" and ((u < e and v > s) if e > s else u < s < v):
                    raise MarkBlock(sp["kind"], kinds)
    items, _ = doc._flat(p)
    for s, e, _ in pieces:
        if any(it[3] is None and it[1] and ((it[0] < e and it[0] + it[1] > s) if e > s else it[0] < s < it[0] + it[1]) for it in items):
            raise ValueError("자동 번호(그림·표 번호)가 든 접두는 바꿀 수 없습니다")
    return pieces


def retoken(doc, pid, old, new, guard=None):
    """줄의 접두 (lead, tok, gap) = old 를 new 로 **제자리에서** — 달라지는 글자만(뒤에서부터) 바꾸고 런 · 글자 모양 · 표지는 그대로(hwpx_struct `_swap_piece`). → 바뀌었는가.
    못 바꾸는 줄은 MarkBlock / ValueError — 문서는 그대로(먼저 다 보고 그다음 바꾼다: `pieces_of`)."""
    pieces = pieces_of(doc, pid, old, new, guard)
    if not pieces:
        return False
    p = doc._ids[pid]
    for s, e, n in pieces:
        doc._swap_piece(p, s, e, n)
    doc._drop_cache(p)
    runs = list(p.iterchildren(RUN))
    # 문단 끝의 빈 글 런(마지막 줄 높이를 정하는 런)은 정리(_tidy)가 지우지 않게 잠깐 떼어 둔다 — 접두와 무관한 런이다(astra 2차)
    tail = runs[-1] if len(runs) > 1 and all(c.tag == T for c in runs[-1]) and not any(len(c) or c.text for c in runs[-1]) else None
    if tail is not None:
        p.remove(tail)
    doc._tidy(p)
    if tail is not None:
        p.append(tail)
    doc._touch(p)
    return True


def _reads(text, tok):
    """고친 뒤의 글 text 가 그 레터 tok 의 줄로 **다시 읽히는가**(내장 레터 규칙 — 「-(정의)」 처럼 레터 뒤 빈칸이 없으면 레터로 안 읽히는 글자가 있다)."""
    c = HR.classify(text, OG._rules())
    return c["kind"] == "marker" and c["letter"] == tok


# ---------------------------------------------------------------- 계획 · 미리보기 · 반영
def _int(v, lo, hi, what):
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ValueError(f"{what}은 {lo}~{hi}칸의 정수")
    return v


def _shadow(ov):
    """나누기를 미리 해 볼 오버레이 사본 — 나누기(`outline_match.cut`)가 바꾸는 것만 깊이 복사한다(나머지는 읽기만)."""
    out = dict(ov)
    for k in ("templates", "lines", "branches", "splits"):
        if k in ov:
            out[k] = copy.deepcopy(ov[k])
    return out


def plan(doc, ov, pid, letter=None, lead=None, gap=None, front=None, scope="line", exact=False, line2=None, start=None, upto=None, cut=None):
    """검사하고 할 일을 정한다(문서 · 오버레이는 안 바꾼다) → {id, tid, no, level, scope, old(lead, tok, gap), new(lead, tok, gap), letter, exact, key(바뀌는 새 키 | None), kin(레터 계열이 바뀌나),
    front(새 앞 여백 mm | None), line2(새 2번째 줄 규칙 | None), changes(값이 바뀌나), rep(지금 대표), isRep, others{diff, same, own, skip}(level), toks{줄: 새 레터}(level — 레터를 바꿀 때),
    split{name, sfx, start, upto, cut, root, roots, moved, stay, kids, levels, conform, touch}(split — 새 템플릿으로 나누기)}.
    line2 = 2번째 줄을 「text」 글 시작 · 「letter」 레터 · 「front」 앞 여백에(None = 그대로 — 이 문단만은 그 줄의 규칙 · 넓히면 그 레벨의 규칙).
    start · upto · cut = 나누기의 시작 레벨(이 줄의 레벨이나 같은 템플릿 윗줄의 레벨 — 없으면 이 줄의 레벨) · 끝 레벨(없으면 끝까지) · 「here」 그 줄과 아래 | 「all」 그 레벨 줄 모두.
    잘못된 값 · 할 수 없는 자리는 ValueError."""
    if scope not in SCOPES:
        raise ValueError(f"scope 는 {', '.join(SCOPES)} 중 하나")
    if line2 is not None and line2 not in OP.LINE2_REL:
        raise ValueError(f"line2 는 {', '.join(OP.LINE2_REL)} 중 하나")
    args = {"letter": letter, "lead": lead, "gap": gap, "front": front, "exact": exact, "line2": line2}   # 나누기 뒤 새 템플릿 안에서 「서식 전체 변경」 을 다시 셈할 때 그대로 준다
    x = line_of(doc, ov, pid)
    tid, level = str(x["tpl"]), int(x["level"])
    t, sl = ov["templates"][tid], OE._slot(ov, tid, level)
    name = f"T{t['no']} L{level}"
    lead0, tok0, gap0, plen, text = OM.parts(doc, ov, pid)
    old = (lead0, tok0, gap0)
    n_lead = lead0 if lead is None else _resize(lead0, _int(lead, 0, LEAD_MAX, "레터 앞 빈칸"))
    n_gap = gap0 if gap is None else _resize(gap0, _int(gap, 0, GAP_MAX, "레터 뒤 빈칸"), nb=OP.NB in (sl.get("prefix") or ""))
    cur_key = x.get("key") or sl.get("key") or ""
    key, kin, n_tok = None, False, tok0
    rep = OC._rep(doc, ov, tid, level)
    o = others(doc, ov, pid, tid, level, rep) if scope == "level" else None
    toks = {}
    if letter is not None:
        if not isinstance(letter, str) or not letter.strip():
            raise ValueError("레터가 비었습니다")
        letter = letter.strip()
        new_key = _key(letter)
        toks = tokens(doc, ov, pid, letter, [pid] + (o["diff"] + o["same"] + o["own"] if o else []), exact)   # 레벨 전체면 이 줄의 번호도 형제 차례로
        n_tok = toks[pid]
        kin = OM.kin(n_tok, new_key) != OM.kin(tok0, cur_key)
        if new_key != cur_key:
            key = new_key
        if n_tok == tok0:
            letter = None   # 같은 레터를 고름 — 레터는 안 바꾼다
    if kin:
        for oid in ([tid] + (heirs(ov, tid, level) if scope == "level" else [])) if scope != "split" else []:   # 그 레벨을 물려 쓰는 템플릿의 사슬까지 — 어느 사슬에도 같은 레터 둘이 생기면 안 된다
            o2 = ov["templates"][oid]   # (새 템플릿으로 나누기는 나눈 뒤의 새 템플릿 사슬로 본다 — 끝 레벨까지만이라 원래 사슬과 다르다: 아래 split)
            at = next((i for i, k in enumerate(o2.get("chain") or [], 1) if k == key and i != level), None) if key else None
            if at:
                raise ValueError(f"「{letter}」 는 T{o2['no']} 가 이미 L{at} 에서 쓰는 레터입니다 — 한 템플릿의 두 레벨에 같은 레터를 둘 수 없습니다. 다른 레터를 고르세요")
        if scope == "line":
            raise ValueError(f"레터가 「{tok0}」 에서 「{n_tok}」 로 달라지면 다른 템플릿입니다 — 「{name} 서식 전체 변경」 이나 「새 템플릿으로 나누기」 를 고르세요")
    new = (n_lead, n_tok, n_gap)
    guard = Guard(doc)
    if new != old:
        try:
            pieces_of(doc, pid, old, new, guard)   # 표지 · 문단을 넘는 필드 · 변경 추적 · 자동 번호 — 미리보기에서 같은 까닭으로 알린다
        except MarkBlock as e:
            raise ValueError(f"이 줄은 {e}") from e
    if new != old and not _reads("".join(new) + (text[plen:] if text[plen:].strip() else "가"), n_tok):   # 레터만 있는 줄도 글이 이어질 때의 꼴로 본다
        raise ValueError(f"그렇게 고치면 「{n_tok}」 가 레터로 읽히지 않습니다 — 레터 뒤 빈칸을 한 칸 이상 두세요")
    n_front = None
    at0 = OP.Measure(doc).place(pid, tok0) if front is not None or line2 is not None else None
    if front is not None:
        if isinstance(front, bool) or not isinstance(front, (int, float)) or not 0 <= front <= FRONT_MAX:
            raise ValueError(f"앞 여백은 0~{FRONT_MAX:g}mm")
        if at0 is None:
            raise ValueError("이 줄의 앞 여백을 잴 수 없습니다(접두에 탭 · 줄 바꿈 · 다른 단위의 문단 모양)")
        if abs(float(front) - at0["x0"]) >= EPS:
            n_front = round(float(front), 2)
    rule = OC.rule(sl).get("line2")   # 그 레벨의 2번째 줄 규칙
    l2_line = l2_slot = False
    if line2 is not None:
        if at0 is None:
            raise ValueError("이 줄의 2번째 줄 자리를 잴 수 없습니다(접두에 탭 · 줄 바꿈 · 다른 단위의 문단 모양)")
        l2_line = line2 != mode_of(at0, (x.get("pos") or {}).get("line2") or rule)   # 이 줄의 2번째 줄이 바뀌나
        l2_slot = line2 != rule   # 그 레벨의 규칙이 바뀌나(서식 전체 변경 · 새 템플릿)
    changes = new != old or n_front is not None or l2_line
    if o is not None and changes:   # 값을 바꾸면 이 줄만의 서식이 된다 — 지금 같은 줄도 맞출 줄이다(표의 서식 · 건너뛸 줄은 그대로)
        order = OM._order(doc)
        o = {**o, "diff": sorted(o["diff"] + o["same"], key=lambda q: order.get(q, 1 << 30)), "same": []}
    out = {"id": pid, "tid": tid, "no": t["no"], "level": level, "name": name, "scope": scope, "old": old, "new": new, "letter": letter, "exact": bool(exact),
           "key": key, "kin": kin, "front": n_front, "line2": line2, "slotLine2": l2_slot, "changes": changes, "rep": rep, "isRep": rep == pid, "args": args}
    if scope == "line":
        if not changes:
            raise ValueError("바뀔 것이 없습니다 — 레터 · 빈칸 · 앞 여백 · 2번째 줄 가운데 하나를 바꾸세요")
    elif scope == "level":
        # 다른 줄의 새 레터 — 레터 계열이 바뀌거나 번호 꼴이 바뀔 때만(닮은 글자는 맞추기가 대표 글자로 바꾼다)
        out["toks"] = {p: tk for p, tk in toks.items() if p != pid and tk != ov["lines"][p]["letter"]} if letter is not None and (kin or OE.is_numbered(key or cur_key)) else {}
        if out["toks"]:   # 한 레벨 = 한 레터 — 못 바꾸는 줄이 하나라도 있으면 레벨 전체를 바꾸지 않는다(옛 레터가 섞인 번호 묶음을 남기지 않는다: astra 2차 P1)
            if o["auto"]:
                raise ValueError(f"{name} 에 자동 글머리표·문단 번호 줄이 {len(o['auto'])}개 있습니다 — 「템플릿 관계」 의 「대표에 맞추기」 로 친 레터로 바꾼 뒤에 레터를 바꾸세요")
            bad = []
            for q, tk in out["toks"].items():
                ql, qt, qg, qn, qtext = OM.parts(doc, ov, q)
                try:
                    pieces_of(doc, q, (ql, qt, qg), (ql, tk, qg), guard)
                    kept = q in o["own"]   # 표의 서식 — 빈칸은 그 줄 것 그대로 · 그 밖은 대표의 빈칸을 받는다
                    if not qt or not _reads((ql if kept else n_lead) + tk + (qg if kept else n_gap) + (qtext[qn:] if qtext[qn:].strip() else "가"), tk):
                        bad.append(q)
                except (MarkBlock, ValueError):
                    bad.append(q)
            if bad:
                eg = doc._text(doc._ids[bad[0]]).strip()[:18]
                raise ValueError(f"레터를 바꿀 수 없는 줄이 {len(bad)}개 있습니다(형광펜 · 필드 · 변경 추적 표지가 걸렸거나, 바꾸면 헤딩으로 읽히지 않는 줄 — 예: 「{eg}」). "
                                 f"그 줄을 먼저 고치거나 「새 템플릿으로 나누기」 를 고르세요")
        if not changes and not o["diff"] and not l2_slot and not (rep == pid and _unfrozen(doc, ov, tid, level, pid)):   # 대표를 손으로 고친 레벨은 다른 줄이 같아도 할 일이 있다(새 줄의 서식 — 동결 모양)
            raise ValueError(f"바뀔 것이 없습니다 — {name} 의 줄이 모두 이미 이 서식입니다")
        out["others"] = o
    else:
        out["split"] = _split_plan(doc, ov, pid, x, tid, level, start, upto, cut, args if changes or l2_slot else None)
        if out["split"]["new"]:   # 새 템플릿 안에서 셈한 이 줄의 새 레터(번호형은 그 묶음의 차례)
            out["new"] = out["split"]["new"]
    return out


def _split_plan(doc, ov, pid, x, tid, level, start, upto, cut, args):
    """「새 템플릿으로 나누기」 의 계획(② §8-12 · 나누기는 § 8-13 `outline_match.cut` — 자리로: 대표 줄도) → {name, sfx, start, upto, cut, root, roots, moved, stay, kids, levels[[레벨, 줄 수]…],
    conform(값을 바꿨으면 새 템플릿 안의 「서식 전체 변경」 수 | None), touch(바뀔 수 있는 줄), new(새 레터 조각 | None)}. args = 값(바꿨을 때만 — 오버레이 사본에서 나눈 뒤 셈한다)."""
    t = ov["templates"][tid]
    tops = {int(k) for k in t.get("slots", {})}
    tmax = max(tops) if tops else level
    start = level if start is None else start
    if isinstance(start, bool) or not isinstance(start, int) or not OM._base(t) < start <= level:
        raise ValueError(f"시작 레벨은 L{OM._base(t) + 1}~L{level}")
    root = ancestors(ov, pid).get(str(start))
    if root is None:
        raise ValueError(f"이 줄 위에 T{t['no']} L{start} 줄이 없습니다 — 다른 시작 레벨을 고르세요")
    if upto is not None and (isinstance(upto, bool) or not isinstance(upto, int) or not level <= upto <= tmax):
        raise ValueError(f"끝 레벨은 L{level}~L{tmax}")
    upto = None if upto is None or upto >= tmax else upto   # 마지막 레벨까지 = 끝까지
    cut = cut or "here"
    if cut not in OM.CUT_SCOPES:
        raise ValueError("cut 은 here | all")
    sname, sfx = _split_name(ov, tid, start)
    if sname is None:
        raise ValueError(f"T{t['no']} L{start} 에서 나눈 템플릿이 이미 26개입니다 — 안 쓰는 것을 합친 뒤 나누세요")
    got = OM.cut_paras(doc, ov, tid, start, [root], cut)
    why = OM.cut_block(ov, tid, start, got, doc=doc)
    if why:
        raise ValueError(why)
    moved = OM._members(ov, tid, got, upto=upto)
    whole = OM._members(ov, tid, got)
    by = {}
    for p in moved:
        k = int(ov["lines"][p]["level"])
        by[k] = by.get(k, 0) + 1
    out = {"name": sname, "sfx": sfx, "start": start, "upto": upto, "cut": cut, "root": root, "roots": got, "moved": len(moved), "stay": len(whole - moved),
           "kids": len(moved) - len(got), "levels": sorted(by.items()), "sig": OM.cut_sig(ov, tid, start, got, upto), "conform": None, "touch": [pid], "new": None}
    if args is None:
        return out
    ov2 = _shadow(ov)   # 나눈 뒤의 새 템플릿 안에서 「서식 전체 변경」 — 이 줄이 그 레벨의 대표 · 그 레벨의 다른 줄(옮겨 간 것)은 이 서식으로
    cid = OM.cut(doc, ov2, tid, start, [root], cut, upto=upto)["id"]
    try:
        pl2 = plan(doc, ov2, pid, scope="level", **args)
    except ValueError as e:
        raise ValueError(str(e).replace(f"T{ov2['templates'][cid]['no']} L{level}", f"새 템플릿 {sname} 의 L{level}")) from e
    o2, toks = pl2["others"], pl2["toks"]
    out["conform"] = {"total": 1 + sum(len(o2[k]) for k in ("diff", "same", "own", "skip")), "change": len(o2["diff"]) + len([p for p in o2["own"] if p in toks]),
                      "own": len(o2["own"]), "skip": len(o2["skip"]), "letters": [list(v) for v in dict.fromkeys((ov2["lines"][p]["letter"], tk) for p, tk in toks.items())][:SHOW]}
    out["touch"] = [pid] + o2["diff"] + o2["same"] + [p for p in o2["own"] if p in toks]
    out["new"] = pl2["new"]
    return out


def _unfrozen(doc, ov, tid, level, pid):
    """대표 줄 pid 가 슬롯의 동결 모양(Enter 로 만드는 새 줄의 서식)과 다른가 — 사람이 대표를 손으로 고친 레벨(다른 줄은 그대로여도 새 줄이 옛 서식으로 생긴다)."""
    sl = OE._slot(ov, tid, level) or {}
    try:
        sh = OM.rep_shape(doc, ov, pid)
    except (KeyError, ValueError):
        return False
    return sh["prefix"] != sl.get("prefix") or sh["attrs"] != sl.get("attrs") or sh["body"] != sl.get("bodyChar")


def preview(doc, ov, pid, letter=None, lead=None, gap=None, front=None, exact=False, line2=None, start=None, upto=None, cut=None):
    """창이 값을 바꿀 때마다 — 범위 셋의 가능 여부와 수(문서 · 오버레이는 안 바꾼다) →
    {line{ok, why}, level{ok, why, total, change, same, own, skip, letters[[옛, 새]…], more},
    split{ok, why, name, start, upto, cut, roots, kids, moved, stay(끝 레벨 아래라 원래 템플릿에 남는 줄), levels[[레벨, 줄 수]…], conform(새 템플릿 안에서 이 서식으로 맞출 수 | None), sig},
    new{letter, lead, gap}, changes, kin}."""
    out = {}
    for scope in SCOPES:
        try:
            pl = plan(doc, ov, pid, letter, lead, gap, front, scope, exact, line2, *((start, upto, cut) if scope == "split" else ()))
        except (KeyError, ValueError) as e:
            out[scope] = {"ok": False, "why": str(e)}
            continue
        new = {"letter": pl["new"][1], "lead": len(pl["new"][0]), "gap": len(pl["new"][2])}   # 범위마다 — 번호형은 범위에 따라 이 줄의 번호가 다르다(레벨 전체 = 형제 차례 · 새 템플릿 = 1부터)
        out.setdefault("new", new)
        out.setdefault("changes", pl["changes"])
        out.setdefault("kin", pl["kin"])
        if scope == "line":
            out[scope] = {"ok": True, "new": new}
        elif scope == "level":
            o, toks = pl["others"], pl["toks"]
            relet = [p for p in o["own"] if p in toks]
            pairs = list(dict.fromkeys((ov["lines"][p]["letter"], tk) for p, tk in toks.items()))
            out[scope] = {"ok": True, "new": new, "total": 1 + sum(len(o[k]) for k in ("diff", "same", "own", "skip")), "change": len(o["diff"]) + len([p for p in o["same"] if p in toks]) + len(relet),
                          "same": len([p for p in o["same"] if p not in toks]), "own": len(o["own"]), "ownLetter": len(relet), "skip": len(o["skip"]),
                          "letters": [list(x) for x in pairs[:SHOW]], "more": max(0, len(pairs) - SHOW)}
        else:
            sp = pl["split"]
            out[scope] = {"ok": True, "new": new, "name": sp["name"], "start": sp["start"], "upto": sp["upto"], "cut": sp["cut"], "roots": len(sp["roots"]), "kids": sp["kids"],
                          "moved": sp["moved"], "stay": sp["stay"], "levels": sp["levels"], "conform": sp["conform"], "sig": sp["sig"]}
    return out


def heirs(ov, tid, level):
    """템플릿 tid 의 레벨 level 을 **물려 쓰는** 템플릿 id 들(끝까지 — 물려 쓰는 템플릿을 또 물려 쓰는 것까지): 그 레벨보다 깊은 데서 뗀 서식 종속 템플릿(variant.level > level) ·
    그 레벨이나 더 아래로 넣은 종속 템플릿(composite.at >= level — 사슬의 앞 at 칸이 부모 것). 제 슬롯 · 제 줄을 가진 템플릿의 같은 번호 레벨은 아니다."""
    out, todo = [], [str(tid)]
    while todo:
        cur = todo.pop(0)
        for oid, o in ov["templates"].items():
            v, c = o.get("variant") or {}, o.get("composite") or {}
            if oid not in out and oid != str(tid) and ((str(v.get("of")) == cur and int(v.get("level") or 0) > level) or (str(c.get("parent")) == cur and int(c.get("at") or 0) >= level)):
                out.append(oid)
                todo.append(oid)
    return out


def _put_key(ov, tid, level, key, letter, wide=True):
    """레벨의 레터 계열을 바꾼 뒤 — 슬롯의 키 · 템플릿 사슬의 그 자리를 새 키로. wide 면 그 레벨을 물려 쓰는 템플릿(`heirs`)의 사슬도 같이."""
    OE._slot(ov, tid, level).update(key=key, letter=letter)
    for oid in [str(tid)] + (heirs(ov, tid, level) if wide else []):
        c = ov["templates"][oid].get("chain")
        if isinstance(c, list) and 0 < level <= len(c):
            c[level - 1] = key


def _place_line(doc, ov, pid, m, front=None, line2=None):
    """고친 줄의 자리 — 앞 여백(front mm: 첫 줄이 시작하는 자리 · None = 그대로)과 2번째 줄을 **한 번에** 정한다. → 바뀌었는가.
    2번째 줄은 그 레벨의 규칙대로(기본 「글 시작」 · 사람이 정한 「직접 mm」 · 「그대로」 = 앞 여백을 옮긴 만큼 같이): 왼쪽 여백 = min(앞 여백, 2번째 줄) · 첫 줄 = 앞 여백 − 2번째 줄
    (왼쪽 여백부터 옮기고 뒤에 맞추면 양수 첫 줄 들여쓰기가 남아 고른 자리와 달라진다 — astra 2차).
    그 레벨에 사람이 정한 **레터 위치**(pos.letterMm)는 여기서 걸지 않는다 — 방금 사람이 이 줄의 앞 여백 · 레터 앞 빈칸을 정했다(레벨 전체로 넓히면 `apply` 가 그 규칙을 새 자리로 고친다).
    가운데 · 오른쪽 정렬 줄(outline_pos.free)은 내어쓰기를 두지 않는다(확정 서식과 같은 꼴) — 앞 여백을 고르면 첫 줄 들여쓰기 없이 그 자리로.
    line2 = 2번째 줄 규칙(「text」 · 「letter」 · 「front」 — 고른 것: 정렬과 무관하게 건다) · 없으면 그 줄에만 건 규칙(x["pos"]), 그것도 없으면 그 레벨의 규칙."""
    x = ov["lines"][pid]
    cur = m.place(pid, x.get("letter"))
    if cur is None:
        if front is not None or line2 is not None:
            raise ValueError("이 줄의 앞 여백 · 2번째 줄을 잴 수 없습니다(접두에 탭 · 줄 바꿈)")
        return False
    if front is not None:
        d = front - cur["x0"]
        cur = {**cur, "x0": front, "letterMm": cur["letterMm"] + d, "textMm": cur["textMm"] + d, "line2Mm": cur["line2Mm"] + d}
    own = line2 or (x.get("pos") or {}).get("line2")
    if OP.free(doc, ov, pid) and own is None:
        t = (round(cur["x0"], 2), 0.0) if front is not None else OP.unhang(cur)
    else:
        pos = {"line2": own, "set": True} if own else dict((OE._slot(ov, x["tpl"], x["level"]) or {}).get("pos") or {"line2": "text"}, set=True)
        pos.pop("letterMm", None)
        try:
            t = OP.target(cur, pos, full=True)
        except ValueError:
            t = None
        if t is None and front is not None:   # 규칙이 줄 것이 없다(접두가 너무 넓음 …) — 고른 앞 여백만: 2번째 줄은 같이 옮긴 자리
            t = (round(min(cur["x0"], cur["line2Mm"]), 2), round(cur["x0"] - cur["line2Mm"], 2))
    if t is None:
        return False
    left, first = t
    p = doc._ids[pid]
    was = doc._summary(p.get("paraPrIDRef"), doc._char_id(p))
    if abs((was.get("indentLeftMm") or 0.0) - left) <= OP.EPS and abs((was.get("firstLineMm") or 0.0) - first) <= OP.EPS:
        return False
    doc.format_para([pid], {"indentLeftMm": left, "firstLineMm": first})
    x["first"] = first
    return True


def _edit_line(doc, ov, pl, m, guard=None):
    """계획의 줄 하나를 고친다(접두 → 오버레이의 레터 · 키 → 앞 여백 · 2번째 줄) → 바뀌었는가."""
    pid, x = pl["id"], ov["lines"][pl["id"]]
    changed = retoken(doc, pid, pl["old"], pl["new"], guard)
    x["letter"] = pl["new"][1]
    if pl["key"]:
        x["key"] = pl["key"]
    l2 = pl.get("line2")
    if l2 and pl["scope"] == "line":   # 이 문단만 — 그 줄에만 건 2번째 줄 규칙(그 레벨의 규칙과 같으면 지운다: 글 고침 뒤 저절로 맞출 때 이 규칙을 지킨다 — outline_pos.align)
        if l2 == OC.rule(OE._slot(ov, x["tpl"], x["level"])).get("line2"):
            x.pop("pos", None)
        else:
            x["pos"] = {"line2": l2}
    return _place_line(doc, ov, pid, m, pl["front"], l2) or changed


def _reletter(doc, ov, p, tok, key, guard=None):
    """다른 줄 p 의 레터만 제자리에서 tok 으로(빈칸 · 모양은 그 줄 것 그대로) + 오버레이의 레터 · 키. → 바뀌었는가. 못 바꾸면 MarkBlock / ValueError(문서 · 오버레이 그대로)."""
    lead, old, gap, _n, _t = OM.parts(doc, ov, p)
    if not old:
        raise ValueError("첫머리에 레터가 없습니다")
    done = retoken(doc, p, (lead, old, gap), (lead, tok, gap), guard)
    ov["lines"][p]["letter"] = tok
    if key:
        ov["lines"][p]["key"] = key
    return done


def apply(doc, ov, pl, m=None, left=None):
    """계획 pl(`plan`)을 건다 — 부른 쪽이 트랜잭션 안에서(도중의 KeyError · ValueError 는 트랜잭션이 문서 · 오버레이를 되돌린다). left = 못 바꾸거나 모양만 맞춘 줄을 적을 목록 [{id, why, kinds}].
    → {changed[바뀐 줄 id — 이 줄 포함], matched(대표 서식으로 맞춘 다른 줄 수), kept[표의 서식이라 레터만 바꾼 줄], split{id, no, name, moved, lines, start, upto, stay} | None, letter, key}."""
    m = m or OP.Measure(doc)
    left = left if left is not None else []
    pid, tid, level = pl["id"], pl["tid"], pl["level"]
    if pl["scope"] == "split":   # 새 템플릿으로 나누기 — 먼저 나누고(오버레이만 · ② §8-13 cut), 값을 바꿨으면 새 템플릿 안에서 「서식 전체 변경」(이 줄이 그 레벨의 대표)
        sp = pl["split"]
        got = OM.cut(doc, ov, tid, sp["start"], [sp["root"]], sp["cut"], upto=sp["upto"])
        if sp["conform"] is not None:
            out = apply(doc, ov, plan(doc, ov, pid, scope="level", **pl["args"]), m, left)
        else:
            out = {"changed": [], "matched": 0, "kept": [], "letter": pl["new"][1], "key": None, "slot": False}
        out["split"] = {"id": got["id"], "no": got["no"], "name": sp["name"], "moved": len(got["moved"]), "lines": len(got["paras"]), "start": sp["start"], "upto": sp["upto"], "stay": sp["stay"]}
        return out
    guard = Guard(doc)
    changed = [pid] if _edit_line(doc, ov, pl, m, guard) else []
    out = {"changed": changed, "matched": 0, "kept": [], "split": None, "letter": pl["new"][1], "key": pl["key"], "slot": False}

    def add(p):
        if p not in changed:
            changed.append(p)

    if pl["scope"] == "line":
        return out
    # level — 이 줄이 대표, 그 레벨의 다른 줄을 이 서식으로
    o, toks, key = pl["others"], pl["toks"], pl["key"]
    sl = OE._slot(ov, tid, level)
    was = (sl.get("rep"), sl.get("prefix"), dict(sl.get("attrs") or {}), sl.get("bodyChar"), sl.get("key"), dict(sl.get("pos") or {}))
    OM.set_rep(doc, ov, tid, level, pid)
    if pl.get("slotLine2"):   # 2번째 줄 규칙을 그 레벨에(사람이 정한 레터 위치는 그대로 — 아래에서 이 줄의 새 자리로)
        sl["pos"] = {**{k: v for k, v in (sl.get("pos") or {}).items() if k != "mm"}, "line2": pl["line2"], "set": True}
    if (sl.get("pos") or {}).get("letterMm") is not None:   # 사람이 정한 레터 위치 — 이 줄의 새 자리로(그 규칙이 다른 줄을 옛 자리로 되돌리지 않게)
        at = m.place(pid, ov["lines"][pid]["letter"])
        if at is not None:
            sl["pos"] = {**sl["pos"], "letterMm": round(at["letterMm"], 2)}
    if OC.place(doc, ov, pid, m):   # 대표를 확정 서식으로(레터 뒤 묶음 빈칸 · 자리 규칙)
        add(pid)
    sh = OM.rep_shape(doc, ov, pid)
    OC.freeze(ov, tid, level, sh)
    if key:
        _put_key(ov, tid, level, key, sh["tok"])
    out["slot"] = was != (sl.get("rep"), sl.get("prefix"), dict(sl.get("attrs") or {}), sl.get("bodyChar"), sl.get("key"), dict(sl.get("pos") or {}))   # 대표 · 동결 모양 · 키 · 자리 규칙이 바뀌었나(문단이 안 바뀌어도 반영할 것이 있다)
    for p in o["diff"] + o["same"] + o["own"]:
        tok = toks.get(p)
        if tok is not None:   # 레터는 늘 여기서 먼저(제자리에서) — match_one 의 번호 셈에 맡기지 않는다. 못 바꾸면 반영 전체를 되돌린다(MarkBlock = ValueError — 옛 레터가 섞인 레벨을 남기지 않는다: `plan` 이 미리 본다)
            if _reletter(doc, ov, p, tok, key, guard):
                add(p)
        elif key and p not in o["own"]:
            ov["lines"][p]["key"] = key   # 닮은 글자로 키만 달라진 레벨(같은 계열) — 맞추면 대표 글자가 된다
        if p in o["own"]:   # 표의 서식(② §8-11) — 모양 · 빈칸은 그 표의 것 그대로
            if tok is not None:
                out["kept"].append(p)
            continue
        if p in o["same"] and tok is None:
            if OC.place(doc, ov, p, m):
                add(p)
            continue
        own = ov["lines"][p]["letter"]
        n = len(left)
        # 레터를 방금 바꾼 줄은 그 레터 그대로(모양 · 빈칸만 대표 것) · 안 바꾼 줄은 전처럼(기호 = 대표 글자 · 번호형 = 대표 꼴에 제 번호)
        OC.conform(doc, ov, p, {**sh, "tok": own, "prefix": sh["lead"] + own + sh["gap"]} if tok is not None else sh, m, left)
        add(p)
        if len(left) == n:
            out["matched"] += 1
    return out
