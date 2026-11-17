"""개요 레벨 더하기(spec_hwpx_웹편집 ② §8-6) — 템플릿의 **마지막 레벨**에서 Alt+↓ 를 누르면 레터 · 앞 공백 · 둘째 줄 후보를 보이고, 고른 것으로 템플릿에 새 개요 레벨을 더한다.

2026-11-16 사용자 "alt + 아랫방향을 누르면 없는 경우 10개 정도 레터와 앞공백 2번째줄 공백을 제안해서 템플릿에 새로운 서식을 /개요레벨을 추가할 수 있는 기능을 넣어주세요".

- 후보(`suggest`) = 레터 약 10개(이 템플릿 사슬에 없는 계열만 — 마지막 레벨보다 깊은 기호가 먼저, 그다음 번호형) + 앞 공백(칸 수 — 마지막 두 레벨의 차만큼 더) +
  둘째 줄(`text` 글 시작에 맞춤 · `letter` 레터 자리에 맞춤 · `keep` 윗 레벨과 같게).
- 새 레벨(`prepare` → `apply`) = 오버레이 템플릿의 슬롯 L(max+1): 문단·글자 모양은 **마지막 레벨 슬롯의 것**(동결 참조 그대로 — 새 서식 정의를 만들지 않는다), 접두 = 앞 공백 + 레터 + 레터 뒤 공백,
  자리 규칙 `pos`(② §8-1 — `set` 이라 새 줄·내린 줄에 통째로 걸린다)로 둘째 줄을 정한다. 사슬(chain)·max 도 한 칸 늘린다.
  종속 템플릿(「T1T3」)·서식 종속 템플릿(「T1L3a」)과 그 바탕 템플릿은 **같은 레벨이 비어 있으면 함께** 늘린다(떼거나 합칠 때 줄이 갈 레벨이 있어야 한다 — `_related`).
- 문서는 여기서 안 바꾼다 — 줄을 새 레벨로 내리는 것은 `outline_edit.plan_level`(같은 트랜잭션: app/outline_grow_api.py). 실행 취소는 오버레이 묶음째(`server._snap`).
- 2단계를 다시 돌려 오버레이를 새로 만들 때(`carry`): 그래프가 새 레벨을 템플릿에 넣었으면(앵커 뒤에 「›레터 키」 가 붙음) 자리 규칙만 옮기고, 못 넣었으면(그 레벨 줄이 없음) 슬롯을 다시 더한다.
"""
import copy

from app import heading_graph as HG
from app import heading_rules as HR
from app import outline_edit as OE

MAX_SHOW = 10    # 보이는 후보 수(사용자 「10개 정도」)
LEAD_MAX = 40    # 앞 공백 칸 수 상한
LINE2 = ("text", "letter", "keep")
LINE2_NAMES = {"text": "글 시작에 맞춤", "letter": "레터 자리에 맞춤", "keep": "윗 레벨과 같게"}
BLANKS = "  　"  # 앞 공백으로 치는 글자(outline_pos.BLANKS 와 같다) — 반각 빈칸 · 줄 안 바꾸는 빈칸 · 전각 빈칸
# 제안 레터 (레터, 서열) — 서열 = 한국어 개요의 흔한 깊이(얕음 → 깊음 · heading_graph._RANK 와 같은 뜻). 차례 = 같은 서열 안에서 보이는 차례.
# 안내(※)·각주(*)·화살표(→)는 헤딩 추출이 개요 레터로 보지 않아 뺀다(2단계를 다시 돌리면 그 줄이 템플릿에서 빠진다). 둘레 글자(㉮)는 번호 열을 몰라 뺀다(직접 입력은 됨 — 번호를 안 매긴다).
POOL = (("·", 13), ("•", 13), ("▪", 14), ("▶", 14), ("◇", 14), ("-", 12), ("○", 11), ("o", 11), ("□", 10),
        ("①", 9), ("(1)", 7), ("1)", 7), ("가)", 8), ("(가)", 8), ("가.", 6), ("a.", 9), ("1.", 5))
RANK = {"N.": 5, "가.": 6, "(N)": 7, "N)": 7, "가)": 8, "(가)": 8, "①": 9, "a.": 9, "a)": 9, "□": 10, "o": 11, "-": 12, "·": 13, "▫": 14, "▶": 14, "◇": 14, "△": 14}

_RULES = []


def _rules():
    """내장 레터 규칙만(배운 규칙·끈 규칙과 무관 — 새 레벨의 레터는 어느 문서에서나 같은 뜻이어야 한다)."""
    if not _RULES:
        _RULES.extend(HR.active({"rules": [], "builtin": {}}))
    return _RULES


def letter_key(letter):
    """레터 → 정규 레터 키(2단계 그래프의 키와 같은 꼴 — 「(3)」 → 「(N)」, 「•」 → 「·」, 「○」 → 「o」). 개요 레터로 읽히지 않으면 ValueError."""
    s = (letter or "").strip() if isinstance(letter, str) else ""
    if not s or len(s) > 8 or any(ch.isspace() for ch in s):
        raise ValueError("레터는 빈칸 없는 1~8글자입니다")
    c = HR.classify(s + " 가", _rules())
    if c["kind"] != "marker" or c["letter"] != s:
        raise ValueError(f"「{s}」 는 개요 레터로 읽히지 않습니다 — 기호(· - o □ ▪ ▶ ◇)나 번호 꼴(① (1) 1) 가. 가) a.)로 고르세요")
    return HG.VARIANTS.get(c.get("family") or "") or c["shape"] or s


def _at(ov, pids):
    """줄들 → (템플릿 id, 템플릿, 마지막 레벨, 그 슬롯). 새 레벨을 더할 수 없는 자리면 ValueError."""
    pids = list(dict.fromkeys(pids or []))
    if not pids:
        raise ValueError("id 가 필요합니다")
    xs = []
    for pid in pids:
        x = ov["lines"].get(pid)
        if x is None:
            raise ValueError("개요 줄이 아닙니다 — 헤딩 추출 2단계가 템플릿을 매긴 문단에서만 됩니다")
        if x.get("role") in OE.ROOTED:
            raise ValueError(f"{'구분 라벨' if x['role'] == 'label' else '괄호 소제목'} 줄 아래로는 Enter 로 줄을 만드세요(레벨 바꾸기는 안 됩니다)")
        xs.append(x)
    tid, level = xs[0]["tpl"], int(xs[0]["level"])
    t = ov["templates"].get(tid)
    if t is None:
        raise ValueError("그 줄의 템플릿이 없습니다 — 문서를 다시 읽어 주세요")
    if any(x["tpl"] != tid or int(x["level"]) != level for x in xs):
        raise ValueError("새 레벨은 같은 템플릿의 같은 레벨 줄들에서만 더할 수 있습니다")
    if OE._slot(ov, tid, level + 1) is not None:
        raise ValueError(f"T{t['no']} 에는 이미 L{level + 1} 이 있습니다 — Alt+↓ 로 내리면 됩니다")
    last = OE._slot(ov, tid, level)
    if last is None or not last.get("prefix") or not last.get("attrs"):
        raise ValueError(f"T{t['no']} L{level} 의 본보기 문단이 문서에 없어 그 아래 레벨의 모양을 정할 수 없습니다")
    return tid, t, level, last


def _used(t):
    """템플릿이 이미 쓰는 레터 키들 — 사슬(종속 템플릿은 부모 템플릿의 레벨까지) + 슬롯."""
    return {k for k in t.get("chain") or [] if k} | {sl.get("key") for sl in (t.get("slots") or {}).values() if sl.get("key")}


def _lead_default(ov, tid, level, last):
    """새 레벨의 앞 공백 (칸 수, 빈칸 글자) — 마지막 레벨의 앞 공백 + 마지막 두 레벨의 차(차가 없으면 2칸)."""
    lead = OE.prefix_of(last["prefix"], last["letter"])[0]
    step = 2
    prev = OE._slot(ov, tid, level - 1)
    if prev and prev.get("prefix"):
        d = len(lead) - len(OE.prefix_of(prev["prefix"], prev.get("letter") or None)[0])
        if 0 < d <= 8:
            step = d
    blank = lead[-1] if lead and lead[-1] in BLANKS else " "
    return min(LEAD_MAX, len(lead) + step), blank


def _doc_letters(ov):
    """이 문서의 템플릿들이 쓰는 (레터 키 → 가장 많이 쓰는 실제 레터) — 같은 계열이면 문서가 쓰는 글자를 권한다(「·」 계열을 「⋅」 로 쓰는 문서)."""
    seen = {}
    for t in ov["templates"].values():
        for sl in (t.get("slots") or {}).values():
            k, lt = sl.get("key"), sl.get("letter")
            if k and lt and not k.startswith("["):
                seen.setdefault(k, {})
                seen[k][lt] = seen[k].get(lt, 0) + max(1, int(sl.get("count") or 0))
    return {k: max(v.items(), key=lambda kv: kv[1])[0] for k, v in seen.items()}


def candidates(ov, tid, level):
    """새 레벨의 레터 후보 [{letter, key, numbered, inDoc}] — 이 템플릿이 안 쓰는 계열만, MAX_SHOW 개까지. 마지막 레벨보다 깊은 서열이 먼저(서열 순), 그 밖은 POOL 차례."""
    t = ov["templates"][str(tid)]
    used = _used(t)
    last = OE._slot(ov, tid, level) or {}
    base = RANK.get(last.get("key") or "", 0)
    doc = _doc_letters(ov)
    keys = [letter_key(lt) for lt, _ in POOL]
    out, seen = [], set()
    for i, (letter, rank) in enumerate(POOL):
        key = keys[i]
        if key in used:
            continue
        numbered = OE.is_numbered(key)
        if not numbered and key in doc and i == keys.index(key):
            letter = doc[key]  # 그 계열의 첫 후보는 문서가 쓰는 글자로
        if letter in seen:
            continue
        seen.add(letter)
        out.append({"letter": letter, "key": key, "numbered": numbered, "inDoc": key in doc, "_o": (0, rank, i) if rank > base else (1, 0, i)})
    out.sort(key=lambda c: c.pop("_o"))
    return out[:MAX_SHOW]


def suggest(doc, ov, pids):
    """Alt+↓ 를 마지막 레벨에서 눌렀을 때 화면이 보일 것 → {tpl, no, level(새 레벨), chain, last{level, letter, lead, gap, prefix}, lead(권하는 칸 수), leadMax, gap,
    line2, line2s[[값, 이름]…], lines(내릴 줄 수), candidates}. 더할 수 없는 자리면 ValueError."""
    tid, t, level, last = _at(ov, pids)
    lead, tok, gap = OE.prefix_of(last["prefix"], last["letter"])
    n, _ = _lead_default(ov, tid, level, last)
    return {"tpl": tid, "no": t["no"], "level": level + 1, "chain": list(t.get("chain") or []),
            "last": {"level": level, "letter": last["letter"], "lead": len(lead), "gap": gap, "prefix": last["prefix"]},
            "lead": n, "leadMax": LEAD_MAX, "gap": gap or " ", "line2": "text", "line2s": [[k, LINE2_NAMES[k]] for k in LINE2],
            "lines": len(set(pids)), "candidates": candidates(ov, tid, level)}


def _related(ov, tid, level):
    """(tid, level) 에 슬롯을 더할 때 **같이** 더할 (템플릿, 레벨)들 — 서식 종속 템플릿과 그 원래 템플릿(레벨 번호가 같다), 종속 템플릿과 넣은 템플릿(레벨이 at 만큼 밀린다).
    그 레벨이 비어 있고 바로 다음 레벨(max + 1)인 것만 — 이미 그 레벨이 있는 템플릿은 건드리지 않고 그 너머로도 안 간다."""
    out, todo, seen = [], [(str(tid), int(level))], {str(tid)}
    while todo:
        cur, lv = todo.pop(0)
        t = ov["templates"].get(cur) or {}
        near = []
        v, c = t.get("variant"), t.get("composite")
        if v:
            near.append((str(v["of"]), lv))
        if c:
            near.append((str(c["child"]), lv - int(c["at"]) + int((ov["templates"].get(str(c["child"])) or {}).get("base") or 0)))
        for oid, o in ov["templates"].items():
            if (o.get("variant") or {}).get("of") == cur:
                near.append((oid, lv))
            oc = o.get("composite") or {}
            if oc.get("child") == cur:
                near.append((oid, int(oc["at"]) + lv - int(t.get("base") or 0)))
        for oid, olv in near:
            o = ov["templates"].get(oid)
            if oid in seen or o is None:
                continue
            seen.add(oid)
            if OE._slot(ov, oid, olv) is None and int(o.get("max") or 0) == olv - 1:
                out.append((oid, olv))
                todo.append((oid, olv))
    return out


def prepare(doc, ov, pids, letter, lead=None, line2="text"):
    """검사하고 새 레벨의 슬롯을 만든다(오버레이·문서는 안 바꾼다) → 기록 {"tid", "no", "level", "key", "slot", "also": [[템플릿 id, 레벨]…], "anchor"}. 잘못된 값은 ValueError."""
    tid, t, level, last = _at(ov, pids)
    key = letter_key(letter)
    letter = letter.strip()
    if key in _used(t):
        at = next((i for i, k in enumerate(t.get("chain") or [], 1) if k == key), None)
        raise ValueError(f"「{letter}」 계열은 T{t['no']} 가 이미 씁니다{f'(L{at})' if at else ''} — 다른 레터를 고르세요")
    if OE.is_numbered(key):
        letter = OE.first(letter) or letter  # 번호형은 그 꼴의 첫 번호로 — 줄의 번호는 형제 차례로 다시 매긴다
    if line2 not in LINE2:
        raise ValueError(f"line2 는 {', '.join(LINE2)} 중 하나")
    n, blank = _lead_default(ov, tid, level, last)
    if lead is not None:
        if isinstance(lead, bool) or not isinstance(lead, int) or not 0 <= lead <= LEAD_MAX:
            raise ValueError(f"레터 앞 빈칸은 0~{LEAD_MAX}칸의 정수")
        n = lead
    gap = OE.prefix_of(last["prefix"], last["letter"])[2] or " "
    slot = {"letter": letter, "key": key, "rep": None, "count": 0, "prefix": blank * n + letter + gap, "attrs": dict(last["attrs"]), "spacer": None, "grown": True}
    if last.get("bodyChar"):
        slot["bodyChar"] = last["bodyChar"]
    pos = {"line2": "text" if line2 == "letter" else line2, "set": True}
    if line2 == "letter":  # 둘째 줄 = 레터 자리(본문 왼끝에서 mm) — 못 재면(탭이 든 접두 · 단위가 다른 문단 모양) 글 시작에 맞춤으로 둔다
        from app import outline_pos
        try:
            at = outline_pos.Measure(doc).slot_place(slot)
        except Exception:  # noqa: BLE001 — 재기 실패가 레벨 더하기를 막지 않게
            at = None
        if at:
            pos = {"line2": "mm", "mm": round(at["letterMm"], 2), "set": True}
    slot["pos"] = pos
    new = level + 1
    return {"tid": tid, "no": t["no"], "level": new, "key": key, "slot": slot, "also": [[a, b] for a, b in _related(ov, tid, new)], "anchor": t.get("anchor"),
            "line2": line2, "lead": n}


def _put(t, level, key, slot):
    """템플릿 t 에 슬롯 하나(사본) — 사슬·max 도 한 칸. -> 되돌릴 때 쓸 옛 (chain, max)."""
    old = (list(t.get("chain") or []), t.get("max"))
    chain = list(old[0])
    chain += [""] * (level - 1 - len(chain))
    t["chain"] = chain[:level - 1] + [key]
    t["slots"][str(level)] = copy.deepcopy(slot)
    t["max"] = max(int(t.get("max") or 0), level)
    return old


def apply(ov, g):
    """기록 g(prepare)대로 오버레이에 새 레벨을 더한다 — 같이 늘릴 템플릿(also)도. 기록을 `grows` 에 남긴다(carry)."""
    g["_undo"] = {}
    for tid, level in [[g["tid"], g["level"]]] + g["also"]:
        t = ov["templates"][str(tid)]
        g["_undo"][str(tid)] = (int(level), *_put(t, int(level), g["key"], g["slot"]))
    ov["seq"] = int(ov.get("seq") or 0) + 1
    ov.setdefault("grows", []).append({"anchor": g.get("anchor"), "tid": g["tid"], "level": g["level"], "key": g["key"], "slot": copy.deepcopy(g["slot"]), "n": ov["seq"]})


def revert(ov, g):
    """apply 를 거꾸로(실행이 문서를 건드리기 전에 실패했을 때 — 건드린 뒤의 실패는 트랜잭션이 오버레이째 되돌린다)."""
    for tid, (level, chain, mx) in (g.pop("_undo", None) or {}).items():
        t = ov["templates"].get(tid)
        if t is None:
            continue
        t["slots"].pop(str(level), None)
        t["chain"], t["max"] = chain, mx
    ov["grows"] = [r for r in ov.get("grows") or [] if not (r.get("tid") == g["tid"] and r.get("level") == g["level"])]


def preview_ov(ov, g):
    """새 레벨이 든 것처럼 보이는 오버레이 사본(템플릿만 사본 — 줄은 같은 것) — 계획(plan_level)이 읽는다. 오버레이는 안 바뀐다."""
    tpls = dict(ov["templates"])
    for tid, level in [[g["tid"], g["level"]]] + g["also"]:
        t = copy.deepcopy(tpls[str(tid)])
        _put(t, int(level), g["key"], g["slot"])
        tpls[str(tid)] = t
    return {**ov, "templates": tpls}


def settle(ov, g, pids):
    """줄을 내린 뒤 — 새 레벨의 대표를 내린 첫 줄로(대표가 없으면 「대표에 맞추기」·서식 갈래가 대표 없음으로 보인다). 동결 접두·모양은 그대로."""
    sl = OE._slot(ov, g["tid"], g["level"])
    first = next((p for p in pids if p in ov["lines"] and ov["lines"][p]["tpl"] == g["tid"] and int(ov["lines"][p]["level"]) == g["level"]), None)
    if sl is not None and first and not sl.get("rep"):
        sl["rep"] = first


def carry(old, new):
    """2단계를 다시 돌려 오버레이를 새로 만들 때 — 옛 오버레이에서 더한 레벨을 잇는다. 템플릿(같은 앵커)의 더한 레벨을 얕은 것부터 보며,
    새 그래프가 그 레벨까지 템플릿에 넣었으면(앵커 = 옛 앵커 + 「›키」…) 그 슬롯에 자리 규칙만 옮기고(사람이 정한 것이 없을 때), 안 넣었으면 슬롯을 다시 더한다. -> 다시 더한 수."""
    if not old or not new:
        return 0
    by_tpl = {}
    for r in sorted(old.get("grows") or [], key=lambda r: (r.get("n") or 0)):
        by_tpl.setdefault(r.get("anchor"), {})[int(r["level"])] = r  # 같은 레벨을 다시 더했으면(되돌린 뒤) 뒤의 것
    by_anchor = {t.get("anchor"): tid for tid, t in new.get("templates", {}).items()}
    added = 0
    for anchor, recs in by_tpl.items():
        if not anchor:
            continue
        levels = sorted(recs)
        hit, tid = 0, by_anchor.get(anchor)
        for k in range(len(levels), 0, -1):  # 새 그래프가 더한 레벨을 몇 개까지 알아봤나(가장 긴 앵커부터)
            cand = by_anchor.get(anchor + "".join("›" + recs[lv]["key"] for lv in levels[:k]))
            if cand is not None:
                hit, tid = k, cand
                break
        if tid is None:
            continue
        t = new["templates"][tid]
        for i, lv in enumerate(levels):
            r, sl = recs[lv], OE._slot(new, tid, lv)
            if i < hit:  # 그래프가 넣은 레벨 — 자리 규칙만
                if sl is not None and sl.get("key") == r["key"] and not (sl.get("pos") or {}).get("set") and (r["slot"].get("pos") or {}).get("set"):
                    sl["pos"] = dict(r["slot"]["pos"])
            elif sl is None and int(t.get("max") or 0) == lv - 1:  # 못 넣은 레벨(그 레벨 줄이 없다) — 슬롯을 다시(같이 늘리던 종속·바탕 템플릿도)
                slot = {**r["slot"], "rep": None}
                for oid, olv in _related(new, tid, lv):
                    _put(new["templates"][oid], olv, r["key"], slot)
                _put(t, lv, r["key"], slot)
                new["seq"] = int(new.get("seq") or 0) + 1
                new.setdefault("grows", []).append({**copy.deepcopy(r), "anchor": t.get("anchor"), "tid": tid, "n": new["seq"]})
                added += 1
            else:
                break
    return added
