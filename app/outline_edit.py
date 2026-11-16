"""개요(템플릿) 편집 계획(spec_hwpx_웹편집 ② §8) — 2단계 헤딩 그래프 위의 **오버레이**와, 키·끌기 한 번을 「행동 목록」으로 바꾸는 순수 함수.

- 오버레이(JSON 꼴 — 작업 저장·실행 취소 묶음에 그대로 든다) = {"run", "baseRev", "rev", "lines", "templates", "branches"}.
  lines = {문단 id: {tpl(템플릿 id 글), no(#N), level, parent(문단 id | None), letter, key, role, flow}} — role heading|title|label 이고 (템플릿, 레벨)이 있는
  노드의 문단. **문단에 노드가 둘 이상(강제 줄 바꿈 뒤 레터)이면 개요 편집 대상에서 뺀다**(astra P1-2). 만들 때 지금 글을 보고 레터가 첫머리에 그대로 있는
  줄만 남긴다(살아 있는 id 만으로 믿지 않음 — astra S20).
  templates = {tpl: {no, kind, chain, max, slots: {level 글: {letter, key, rep, prefix(앞 공백·레터·뒤 공백 — 대표 문단에서 **동결**), attrs(문단·글자 모양 참조 동결),
  spacer(앞 간격 줄의 모양 참조 | None), count}}}}. branches = {"tpl|level": [아래에 매달리는 템플릿 id…]}(참고 — 자동 선택엔 안 씀, astra S12).
- 그래프(graph.json)는 실행 때의 문서에 매여 있어 편집해도 안 바뀐다 — 개요 편집은 오버레이만 고치고, 2단계를 다시 돌리면 오버레이를 새로 만든다(run 키).
  글 고침(PATCH)·나누기·합치기 뒤엔 sync() 로 떨어져 나간 문단·레터가 바뀐 줄을 오버레이에서 뺀다(astra P1-1).
- 그릇(구역·표 칸 subList) 하나의 문단 열 `seq` = [{id, text, blank(순수 간격 문단), object}] 문서 순 — 개요 줄이 아닌 본문·간격 문단·표 호스트 문단 포함.
  부분 트리 범위 = 줄 X 부터 「X 의 자손이 아닌 다음 개요 줄」 직전까지. **간격 줄은 뒤 줄의 것**(「앞 간격 줄」 소유 — 이 양식 □ → 빈 → o → 빈 → - → ⋅ → 빈 → o):
  옮기는 단위 = [X 의 앞 간격 줄(있으면) … X 범위의 마지막 내용(글·개체) 문단], 삽입점 「X 의 부분 트리 끝 뒤」 = 그 마지막 내용 문단 뒤.
- 행동(act): erase(id, start, end) · split_restyle(id, at, prefix, attrs, line) · insert(after, text, attrs, line, origin) · insert_blank(after, attrs) ·
  restyle(id, old_len, prefix, attrs, line) · retext(id, old_len, prefix, letter) · move(first, last, ref, after) · remove(id) · reparent(id, parent).
  `after` 가 "$last" 면 직전 행동이 만든 문단 뒤. line.parent 가 "$prev" 면 직전에 만든 줄. 서버(server.py /outline)가 hwpx_struct 원시 연산으로 차례대로
  실행하고 line 을 오버레이에 반영한다.
"""
import re
from collections import Counter

NUM_CLASSES = {  # 번호형 레터의 글자 열(차례) — 아라비아 숫자는 정수
    "①": "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳",
    "가": "가나다라마바사아자차카타파하",
    "A": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "a": "abcdefghijklmnopqrstuvwxyz",
    "Ⅰ": "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ",
    "ⅰ": "ⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹⅺⅻ",
}
_NUM_RE = re.compile(r"\d+|[①-⑳]|[가-하]|[A-Za-z]|[Ⅰ-Ⅻ]|[ⅰ-ⅻ]")
_KEY_RE = re.compile(r"N|①|가|A|a|Ⅰ|ⅰ")
ROOTED = ("label", "subtitle")  # 괄호 줄 — 구분 라벨·괄호 소제목(spec_헤딩_추출 ② §13): 둘 다 제 템플릿의 뿌리, 편집 제한이 같다
ROLES = ("heading", "title") + ROOTED
TABLE = "table"  # 표 제목 줄(spec_hwpx_웹편집 ② §8-7 — app/outline_lift.py): 제목 표(1칸 상자 · 번호 칸 + 제목 칸 띠 · 3행 표)를 템플릿의 표 레벨로 넣은 줄. 열쇠 = 칸 안 제목 문단 id, 레터 없음(letter ""), Enter 만 된다


def lift_depth(t):
    """템플릿 t 의 표 제목 레벨 수(② §8-7 「넓힘」 — 표 레벨은 L1 부터 그만큼, 글 레벨은 그 아래: 그래프의 레벨 = 오버레이 레벨 − 이 값). 표를 안 넣었으면 0 · 옛 기록(층 목록 없음)은 1."""
    lf = (t or {}).get("lift")
    return (len(lf["tiers"]) if "tiers" in lf else 1) if lf else 0


def is_numbered(key):
    """정규 레터 키(「N.」「N-N.」「(N)」「①」「가.」「(a)」…)가 번호형인지 — 기호(□·o·-··)·라벨은 아님."""
    return bool(key) and bool(_KEY_RE.search(key)) and key not in ("o", "a", "A") and not key.startswith("[")


def _runs(letter):
    return [(m.start(), m.end(), m.group()) for m in _NUM_RE.finditer(letter or "")]


def _ordinal(tok):
    if tok.isascii() and tok.isdigit():
        return int(tok)
    for seq in NUM_CLASSES.values():
        if tok in seq:
            return seq.index(tok) + 1
    return None


def _token(like, n):
    """like 와 같은 종류의 n 번째 글자(1부터). 열을 넘으면 None."""
    if like.isascii() and like.isdigit():
        return str(n) if n >= 1 else None
    for seq in NUM_CLASSES.values():
        if like in seq:
            return seq[n - 1] if 1 <= n <= len(seq) else None
    return None


def numbers_of(letter):
    """레터의 번호 값들(앞에서부터) — 「1-2.」 → [1, 2], 「③」 → [3], 「가.」 → [1]. 번호 아님 → []."""
    return [v for _, _, t in _runs(letter) if (v := _ordinal(t)) is not None]


def with_numbers(letter, values):
    """레터의 번호 글자들을 values 로(꼴은 그대로) — 자리 수가 다르면 뒤에서부터 맞춘다. 열을 넘으면 None."""
    runs = [r for r in _runs(letter) if _ordinal(r[2]) is not None]
    if not runs or not values:
        return letter
    out = letter
    for (s, e, tok), v in zip(reversed(runs), reversed(values)):
        t = _token(tok, v)
        if t is None:
            return None
        out = out[:s] + t + out[e:]
    return out


def _with_parent(nums, parent_letter):
    pn = numbers_of(parent_letter) if parent_letter else []
    if pn and len(nums) == len(pn) + 1:
        return pn + [nums[-1]]
    return list(nums)


def succ(letter, parent_letter=None):
    """다음 형제 레터 — 마지막 번호 +1(「1-1.」 → 「1-2.」, 「③」 → 「④」). 합성 번호(부모보다 번호 하나 더)는 앞 번호를 부모 것으로. 번호형 아니면 그대로."""
    nums = numbers_of(letter)
    if not nums:
        return letter
    nums = _with_parent(nums, parent_letter)
    nums[-1] += 1
    return with_numbers(letter, nums)


def first(letter, parent_letter=None):
    """그 꼴의 첫 레터 — 「(3)」 → 「(1)」, 「다.」 → 「가.」, 「2-3.」(부모 「2.」) → 「2-1.」."""
    nums = numbers_of(letter)
    if not nums:
        return letter
    nums = _with_parent(nums, parent_letter)
    nums[-1] = 1
    return with_numbers(letter, nums)


def prefix_of(text, letter=None):
    """글 첫머리의 접두 (lead, letter, gap) — lead = 앞 공백, letter = 레터(오버레이 레터가 첫머리에 그대로 있으면 그것, 없으면 빈 글), gap = 레터 뒤 공백."""
    text = text or ""
    lead = text[:len(text) - len(text.lstrip())]
    rest = text[len(lead):]
    tok = letter if letter and rest.startswith(letter) else ""
    after = rest[len(tok):]
    gap = after[:len(after) - len(after.lstrip())] if tok else ""
    return lead, tok, gap


def prefix_len(text, letter=None):
    lead, tok, gap = prefix_of(text, letter)
    return len(lead) + len(tok) + len(gap)


def body_of(text, letter=None):
    return (text or "")[prefix_len(text, letter):].strip()


# ---------------------------------------------------------------- 오버레이
def build_overlay(g, probe, rev=0):
    """2단계 그래프 → 오버레이. probe(pid) -> {"text", "attrs", "spacer"(앞 순수 간격 문단의 attrs | None)} | None(문단이 없음).
    줄 = role heading|title|label + (template, level) + 문단에 노드 하나뿐 + 지금 글 첫머리에 레터 그대로."""
    meta = g.get("meta") or {}
    per_para = Counter(n["para"] for n in g.get("nodes") or [] if n.get("role") in ROLES and n.get("template") and n.get("level"))
    tpls, by_anchor = {}, {}
    for t in g.get("templates") or []:
        tid = str(t.get("id", t.get("no")))
        slots = {}
        for s in t.get("slots") or []:
            slots[str(int(s["level"]))] = {"letter": s.get("letter") or "", "key": s.get("letter") or "", "rep": s.get("rep"), "count": s.get("count", 0),
                                          "prefix": None, "attrs": None, "spacer": None, "members": []}
        for i, k in enumerate(t.get("chain") or [], 1):  # 사슬에 있으나 관측 0 인 레벨 — 대표 없음(못 만든다)
            slots.setdefault(str(i), {"letter": k, "key": k, "rep": None, "count": 0, "prefix": None, "attrs": None, "spacer": None, "members": []})
        tpls[tid] = {"no": t.get("no", t.get("id")), "kind": t.get("kind"), "anchor": t.get("anchor") or t.get("name"), "chain": list(t.get("chain") or []),
                     "slots": slots, "max": max((int(k) for k in slots), default=0)}
        by_anchor[tpls[tid]["anchor"]] = tid
    lines, by_node, probes = {}, {}, {}

    def info(pid):
        if pid not in probes:
            probes[pid] = probe(pid)
        return probes[pid]

    for n in g.get("nodes") or []:
        if n.get("role") not in ROLES or not n.get("template") or not n.get("level") or per_para[n["para"]] != 1:
            continue
        tid = by_anchor.get(n["template"], str(n.get("tplNo")))
        if tid not in tpls:
            continue
        pi = info(n["para"])
        letter = n.get("letter") or ""
        if pi is None or not letter or not prefix_of(pi["text"], letter)[1]:
            continue
        lines[n["para"]] = {"tpl": tid, "no": tpls[tid]["no"], "level": int(n["level"]), "parent": None, "letter": letter, "key": n.get("key") or "",
                            "role": n["role"], "flow": n.get("flow", "body"), "_pnode": n.get("parent"),
                            "fmt": n.get("fmt") or ""}  # 서식 라벨(여백의 「S41」) — 추출한 때의 것. 대표에 맞춘 줄은 대표의 라벨이 된다(outline_match.match_one · label_sync)
        by_node[n["id"]] = n["para"]
        tpls[tid]["slots"].get(str(int(n["level"])), {}).setdefault("members", []).append(n["para"])
    for line in lines.values():
        pn = line.pop("_pnode")
        line["parent"] = by_node.get(pn) if pn and pn in by_node else None
    for t in tpls.values():  # 슬롯 접두·모양·앞 간격 줄 동결 — 대표 문단(없거나 죽었으면 살아 있는 멤버 첫 것)에서
        for sl in t["slots"].values():
            cands = [sl["rep"]] + [m for m in sl["members"] if m != sl["rep"]]
            for pid in cands:
                pi = info(pid) if pid else None
                if pi is None:
                    continue
                lead, tok, gap = prefix_of(pi["text"], lines.get(pid, {}).get("letter") or sl["letter"] or None)
                if not tok:
                    continue
                sl["rep"], sl["prefix"], sl["attrs"] = pid, lead + tok + gap, pi["attrs"]
                sl["letter"] = tok
                break
            have = [info(m) for m in sl["members"] if info(m) is not None]
            with_sp = [pi for pi in have if pi.get("spacer")]
            if have and len(with_sp) * 2 > len(have):  # 멤버 과반이 앞에 순수 간격 문단 — 그 모양(대표 것 우선)
                rep_pi = info(sl["rep"]) if sl["rep"] else None
                sl["spacer"] = (rep_pi or {}).get("spacer") or with_sp[0]["spacer"]
            sl.pop("members", None)
    branches = {}
    for ins in g.get("instances") or []:
        pp = by_node.get(ins.get("parent"))
        if pp and pp in lines and str(ins.get("template")) in tpls:
            branches.setdefault(f"{lines[pp]['tpl']}|{lines[pp]['level']}", Counter())[str(ins["template"])] += 1
    return {"run": [meta.get("run"), meta.get("at")], "baseRev": rev, "rev": rev, "lines": lines, "templates": tpls,
            "branches": {k: [t for t, _ in c.most_common()] for k, c in branches.items()}}


def sync(ov, alive, text_of):
    """편집 뒤 오버레이 손질 — 떨어져 나갔거나 레터가 첫머리에서 사라진 줄을 뺀다(그 줄을 부모로 삼던 줄은 조부모로). -> 뺀 문단 id 들."""
    # 표 제목 줄(② §8-7)은 레터가 없다 — 문단이 살아 있는지만 본다(제목 글을 고쳐도 줄이 남는다)
    gone = [p for p, x in ov["lines"].items() if not alive(p) or (x.get("role") != TABLE and not prefix_of(text_of(p), x["letter"])[1])]
    for p in gone:
        x = ov["lines"].pop(p)
        for y in ov["lines"].values():
            if y["parent"] == p:
                y["parent"] = x["parent"]
    return gone


def view(ov):
    """화면용 요약 — 줄마다 {no, level, tpl, letter, role}, 템플릿마다 {no, chain, kind, max}."""
    return {"run": ov["run"], "rev": ov.get("rev"), "lines": {p: line_view(x) for p, x in ov["lines"].items()},
            "templates": {tid: {"no": t["no"], "chain": t["chain"], "kind": t["kind"], "max": t["max"]} for tid, t in ov["templates"].items()}}


def line_view(x):
    return {"no": x["no"], "level": x["level"], "tpl": x["tpl"], "letter": x["letter"], "role": x.get("role", "heading"), "key": x.get("key", "")}


def is_descendant(ov, pid, anc, limit=64):
    x = ov["lines"].get(pid)
    while x is not None and limit > 0:
        if x["parent"] == anc:
            return True
        x = ov["lines"].get(x["parent"]) if x["parent"] else None
        limit -= 1
    return False


def subtree(seq, i, ov):
    """seq[i](개요 줄)의 부분 트리 -> (end_excl, last_content): end_excl = X 의 자손이 아닌 다음 개요 줄 자리(없으면 len), last_content = 범위 안 마지막 글·개체 문단 자리."""
    pid, end = seq[i]["id"], len(seq)
    for j in range(i + 1, len(seq)):
        q = seq[j]["id"]
        if q in ov["lines"] and not is_descendant(ov, q, pid):
            end = j
            break
    last = i
    for j in range(i, end):
        if not seq[j]["blank"]:
            last = j
    return end, last


def _slot(ov, tid, level):
    return ov["templates"].get(str(tid), {}).get("slots", {}).get(str(level))


def _parent_letter(ov, parent):
    return ov["lines"][parent]["letter"] if parent and parent in ov["lines"] else None


def _succ(slot, letter, parent_letter):
    """슬롯이 번호형일 때만 다음 번호(기호 레터 「o」 는 알파벳이 아니다)."""
    return succ(letter, parent_letter) if is_numbered(slot.get("key")) else letter


def _first(slot, letter, parent_letter):
    return first(letter, parent_letter) if is_numbered(slot.get("key")) else letter


def _prefix_for(slot, letter):
    """동결한 슬롯 접두에서 레터만 letter 로 바꾼 글(앞 공백·뒤 공백은 그대로)."""
    lead, tok, gap = prefix_of(slot["prefix"], slot["letter"])
    return lead + letter + gap


def _own_spacer(seq, i, slot):
    """줄 i 의 앞 간격 줄 자리 — 슬롯이 앞 간격 줄을 갖고 바로 앞 문단이 순수 간격 문단이면 i−1."""
    return i - 1 if slot and slot.get("spacer") and i > 0 and seq[i - 1]["blank"] else None


def _line(ov, tid, level, parent, letter, flow="body"):
    t = ov["templates"][str(tid)]
    rep = ((t.get("slots") or {}).get(str(int(level))) or {}).get("rep")
    return {"tpl": str(tid), "no": t["no"], "level": int(level), "parent": parent, "letter": letter,
            "key": t["chain"][int(level) - 1] if int(level) - 1 < len(t["chain"]) else "", "role": "heading", "flow": flow,
            "fmt": (ov["lines"].get(rep) or {}).get("fmt", "") if rep else ""}  # 새 줄은 그 레벨 대표의 모양으로 생긴다 — 서식 라벨도 대표 것


def _need_slot(ov, tid, level):
    slot = _slot(ov, tid, level)
    if slot is None:
        return None
    if not slot.get("prefix") or not slot.get("attrs"):
        raise ValueError(f"템플릿 #{ov['templates'][str(tid)]['no']} 레벨 {level}의 본보기 문단이 문서에 없어 줄을 만들 수 없습니다")
    return slot


def _check_line(ov, pid, what):
    x = ov["lines"].get(pid)
    if x is None:
        raise ValueError("개요 줄이 아닙니다 — 헤딩 추출 2단계가 템플릿을 매긴 문단에서만 됩니다")
    if x.get("role") in ROOTED and what != "enter":  # 괄호 글 전체가 레터라 레벨 바꾸기·옮기기가 제목 글을 통째로 갈아 버린다
        raise ValueError(f"{'구분 라벨' if x['role'] == 'label' else '괄호 소제목'} 줄은 자식 줄 만들기(Enter)만 됩니다")
    if x.get("role") == TABLE and what != "enter":  # 표 제목 줄(② §8-7) — 표를 만들거나 옮기거나 지우는 개요 편집은 없다
        raise ValueError("표 제목 줄에서는 Enter(표 아래에 새 줄)만 됩니다")
    return x


# ---------------------------------------------------------------- 번호 다시 매김
def siblings(seq, ov, parent, tid, level, start=0, stop=None):
    """start 부터 같은 부모 아래 (tpl, level) 형제들(문서 순) — 부모의 부분 트리를 벗어나면 끝."""
    out = []
    if parent is not None:
        start = max(start, next((j + 1 for j, it in enumerate(seq) if it["id"] == parent), start))
    for j in range(start, stop if stop is not None else len(seq)):
        q = seq[j]["id"]
        x = ov["lines"].get(q)
        if x is None:
            continue
        if parent is not None and not is_descendant(ov, q, parent):
            break
        if x["parent"] == parent and x["tpl"] == str(tid) and x["level"] == int(level):
            out.append(j)
    return out


def _run_around(seq, idx, lines, text_of, anchor, fresh=()):
    """형제 자리들 중 anchor 가 든 **이어진 번호 묶음**(앞뒤로 번호가 1씩 이어지는 구간 — 그 밖은 다시 시작하는 다른 묶음, astra 「재시작 구간」) -> 자리 목록."""
    if anchor is None or anchor not in idx:
        return idx

    def num(j):  # 실제 번호(새 줄 = None — 앞뒤를 잇는 투명한 자리)
        if seq[j]["id"] in fresh:
            return None
        x = lines[seq[j]["id"]]
        _, tok, _ = prefix_of(text_of(seq[j]["id"]), x["letter"] or None)
        n = numbers_of(tok or x["letter"])
        return n[-1] if n else None
    k = idx.index(anchor)
    a, lo = k, num(idx[k])
    while a > 0:
        pv = num(idx[a - 1])
        if pv is None or (lo is not None and pv + 1 != lo):
            break
        a, lo = a - 1, pv
    b, hi = k, next((num(idx[j]) for j in range(k, a - 1, -1) if num(idx[j]) is not None), None)
    while b + 1 < len(idx):
        nx = num(idx[b + 1])
        if nx is None or (hi is not None and hi + 1 != nx):
            break
        b, hi = b + 1, nx
    return idx[a:b + 1]


def renumber(seq, ov, text_of, parent, tid, level, shadow=None, anchor=None, fresh=()):
    """같은 부모 아래 (tpl, level) 형제들의 번호를 첫 형제부터 차례로(합성 번호는 부모 번호 + 차례) — 바뀌는 줄의 retext 행동. 바뀐 줄 아래 합성 번호 자식도 연쇄.
    shadow = 계획 중인 줄 상태(없으면 ov.lines). anchor = 새로 넣거나 바꾼 줄의 seq 자리 — 그 줄이 든 이어진 번호 묶음만 매긴다(문서 안 다른 재시작 묶음은 안 건드림).
    fresh = 아직 번호가 없는 새 줄 id 들(묶음 판정에서 앞뒤를 잇는 것으로 봄). 번호형이 아니면 []."""
    lines = shadow if shadow is not None else ov["lines"]
    o2 = {**ov, "lines": lines}
    idx = siblings(seq, o2, parent, tid, level)
    if not idx:
        return []
    key = lines[seq[idx[0]]["id"]]["key"]
    if not is_numbered(key):
        return []
    if anchor is not None:  # 번호가 다시 시작하는 묶음(장 번호 「1. 2. 3.」, 레벨을 건너뛴 부모 아래 「(1)」 묶음들)은 안 건드린다 — anchor 가 든 이어진 구간만
        idx = _run_around(seq, idx, lines, text_of, anchor, fresh)
    pl = _parent_letter(o2, parent)
    acts, prev = [], None
    for j in idx:
        pid = seq[j]["id"]
        x = lines[pid]
        lead, tok, gap = prefix_of(text_of(pid), x["letter"] or None)
        if not tok:
            tok = x["letter"]
            lead, gap = "", " "
        want = first(tok, pl) if prev is None else succ(prev, pl)
        if want is None:
            raise ValueError("번호 열의 끝입니다")
        if want != tok:
            acts.append({"act": "retext", "id": pid, "old_len": len(lead) + len(tok) + len(gap), "prefix": lead + want + gap, "letter": want})
            x["letter"] = want
            child = _slot(ov, tid, int(level) + 1)
            if child and len(numbers_of(child.get("letter") or "")) == len(numbers_of(want)) + 1:  # 합성 번호 자식(「3.」 아래 「3-1.」)만 연쇄
                acts += renumber(seq, ov, _texts_with(text_of, acts), pid, tid, int(level) + 1, shadow=lines)
        prev = want
    return acts


def _texts_with(text_of, acts):
    """retext·restyle 이 바꾼 접두를 반영한 text_of(계획 안에서 뒤 행동이 앞 행동의 결과를 보게)."""
    changed = {}
    for a in acts:
        if a["act"] in ("retext", "restyle"):
            changed.setdefault(a["id"], []).append(a)

    def f(pid):
        t = text_of(pid)
        for a in changed.get(pid, ()):
            t = a["prefix"] + t[a["old_len"]:]
        return t
    return f


# ---------------------------------------------------------------- 계획
def plan_enter(seq, i, offset, end, ov, text_of):
    """Enter — 개요 줄 X 바로 아래 **하위 레벨** 새 줄(커서 뒤 글은 새 줄로 — 런·공백 보존). 다음 슬롯이 없으면 같은 레벨 줄(X 의 부분 트리 끝 뒤).
    고른 글(offset..end)은 같은 트랜잭션에서 지운다. -> {"actions", "focus"}"""
    pid = seq[i]["id"]
    x = _check_line(ov, pid, "enter")
    if x.get("role") == TABLE:
        return _plan_enter_table(seq, i, ov, text_of, x)
    text = text_of(pid)
    lead, tok, gap = prefix_of(text, x["letter"] or None)
    plen = len(lead) + len(tok) + len(gap)
    acts = []
    offset = int(offset or 0)
    if end is not None and int(end) > offset:
        acts.append({"act": "erase", "id": pid, "start": offset, "end": int(end)})
        text = text[:offset] + text[int(end):]
    at = max(offset, plen)
    tid, level = x["tpl"], x["level"]
    nxt = int(level) + 1
    if _slot(ov, tid, nxt) is None:  # 템플릿 마지막 슬롯 — 같은 레벨 형제(S2), 글은 나눈다
        slot = _need_slot(ov, tid, level)
        letter = _succ(slot, tok or slot["letter"], _parent_letter(ov, x["parent"]))
        if letter is None:
            raise ValueError("번호 열의 끝입니다")
        parent, lvl = x["parent"], int(level)
    else:
        slot = _need_slot(ov, tid, nxt)
        letter = _first(slot, slot["letter"], tok or None)
        parent, lvl = pid, nxt
    prefix = _prefix_for(slot, letter)
    line = _line(ov, tid, lvl, parent, letter, x.get("flow", "body"))
    acts.append({"act": "split_restyle", "id": pid, "at": at, "prefix": prefix, "attrs": slot["attrs"], "line": line})
    end_i, last = subtree(seq, i, ov)
    if lvl == int(level) and last > i:  # 잎 레벨인데 가지 자손이 있음 — 부분 트리 끝 뒤로
        acts.append({"act": "move", "first": "$last", "last": "$last", "ref": seq[last]["id"], "after": True})
    if slot.get("spacer"):
        acts.append({"act": "insert_blank", "after": seq[last]["id"] if lvl == int(level) and last > i else pid, "attrs": slot["spacer"], "before_new": True})
    shadow = {p: dict(v) for p, v in ov["lines"].items()}
    shadow["$new"] = dict(line)
    seq2 = seq[:i + 1] + [{"id": "$new", "text": prefix, "blank": False, "object": False}] + seq[i + 1:] if lvl != int(level) or last == i \
        else seq[:last + 1] + [{"id": "$new", "text": prefix, "blank": False, "object": False}] + seq[last + 1:]
    anchor = next(j for j, it in enumerate(seq2) if it["id"] == "$new")
    acts += renumber(seq2, ov, lambda p: prefix if p == "$new" else text_of(p), parent, tid, lvl, shadow=shadow, anchor=anchor, fresh=("$new",))
    return {"actions": acts, "focus": {"id": "$new", "offset": len(prefix)}}


def _plan_enter_table(seq, i, ov, text_of, x):
    """표 제목 줄의 Enter(② §8-7) — 표 **아래**(그 표를 품은 문단 뒤: 서버가 줄 id 를 호스트 문단으로 바꿔 넣는다)에 **첫 글 레벨**의 새 줄(새 첫 자식 — 그 슬롯의 앞 간격 줄과 함께).
    표 레벨이 여러 층이면 어느 층의 표 줄에서나 첫 글 레벨이다(그 사이 레벨의 줄은 표라 만들 수 없다). 제목 글은 나누지 않는다(커서 자리·고른 글과 무관)."""
    pid, tid, lvl = seq[i]["id"], x["tpl"], int(x["level"]) + 1
    while (_slot(ov, tid, lvl) or {}).get("table"):
        lvl += 1
    slot = _need_slot(ov, tid, lvl)
    if slot is None:
        raise ValueError("표 제목 아래 레벨이 없습니다")
    letter = _first(slot, slot["letter"], None)
    prefix = _prefix_for(slot, letter)
    line = _line(ov, tid, lvl, pid, letter, x.get("flow", "body"))
    acts, ref = [], pid
    if slot.get("spacer"):
        acts.append({"act": "insert_blank", "after": ref, "attrs": slot["spacer"]})
        ref = "$last"
    acts.append({"act": "insert", "after": ref, "text": prefix, "attrs": slot["attrs"], "line": line, "origin": pid, "head": True})
    shadow = {p: dict(v) for p, v in ov["lines"].items()}
    shadow["$first"] = dict(line)
    seq2 = seq[:i + 1] + [{"id": "$first", "text": prefix, "blank": False, "object": False}] + seq[i + 1:]
    acts += renumber(seq2, ov, lambda p: prefix if p == "$first" else text_of(p), pid, tid, lvl, shadow=shadow, anchor=i + 1, fresh=("$first",))
    return {"actions": acts, "focus": {"id": "$first", "offset": len(prefix)}}


def plan_sibling(seq, i, ov, text_of):
    """Alt+Enter — 같은 레벨 **트리(뼈대)**: X 의 부분 트리 끝 뒤에 (T, L), (T, L+1) … (T, 마지막) 빈 레터 줄(각각 그 슬롯의 앞 간격 줄과 함께). 마지막 레벨이면 줄 하나.
    X 의 글은 그대로."""
    pid = seq[i]["id"]
    x = _check_line(ov, pid, "sibling")
    tid, level = x["tpl"], int(x["level"])
    t = ov["templates"][tid]
    end_i, last = subtree(seq, i, ov)
    text = text_of(pid)
    lead, tok, gap = prefix_of(text, x["letter"] or None)
    pl = _parent_letter(ov, x["parent"])
    slot = _need_slot(ov, tid, level)
    letter = _succ(slot, tok or slot["letter"], pl)
    if letter is None:
        raise ValueError("번호 열의 끝입니다")
    acts, ref = [], seq[last]["id"]
    if slot.get("spacer"):
        acts.append({"act": "insert_blank", "after": ref, "attrs": slot["spacer"]})
        ref = "$last"
    first_prefix = _prefix_for(slot, letter)
    acts.append({"act": "insert", "after": ref, "text": first_prefix, "attrs": slot["attrs"], "line": _line(ov, tid, level, x["parent"], letter, x.get("flow", "body")),
                 "origin": pid, "head": True})
    parent_letter = letter
    new_seq_items = [{"id": "$first", "text": first_prefix, "blank": False, "object": False}]
    shadow = {p: dict(v) for p, v in ov["lines"].items()}
    shadow["$first"] = dict(acts[-1]["line"])
    for k in range(level + 1, t["max"] + 1):
        sl = _need_slot(ov, tid, k)
        if sl is None:
            break
        lt = _first(sl, sl["letter"], parent_letter)
        if sl.get("spacer"):
            acts.append({"act": "insert_blank", "after": "$last", "attrs": sl["spacer"]})
        acts.append({"act": "insert", "after": "$last", "text": _prefix_for(sl, lt), "attrs": sl["attrs"], "line": _line(ov, tid, k, "$prev", lt, x.get("flow", "body")),
                     "origin": pid})
        parent_letter = lt
    seq2 = seq[:last + 1] + new_seq_items + seq[last + 1:]
    acts += renumber(seq2, ov, lambda p: first_prefix if p == "$first" else text_of(p), x["parent"], tid, level, shadow=shadow, anchor=last + 1, fresh=("$first",))
    return {"actions": acts, "focus": {"id": "$first", "offset": len(first_prefix)}}


def _target(ov, x, delta):
    """레벨 한 단계 바꾼 (tpl, level) — 못 바꾸면 ValueError(astra S10·S12: 가지 자동 선택 없음)."""
    tid, level = x["tpl"], int(x["level"])
    base = int(ov["templates"].get(tid, {}).get("base") or 0)  # 종속 템플릿(「T1T3」 — 부모 템플릿의 L base 아래에서 시작, spec_hwpx_웹편집 ② §8-2)은 L base+1 이 제 첫 레벨
    if delta < 0:
        if level - 1 > base:
            if (_slot(ov, tid, level - 1) or {}).get("table"):  # 표 제목 레벨(② §8-7) — 그 레벨의 줄은 표다
                raise ValueError("표 제목 레벨로는 올릴 수 없습니다(그 레벨의 줄은 표입니다)")
            return tid, level - 1
        p = ov["lines"].get(x["parent"])
        if p is None:
            raise ValueError("더 올릴 개요 레벨이 없습니다(가장 바깥 레벨)")
        if p.get("role") in ROOTED:
            raise ValueError(f"{'구분 라벨' if p['role'] == 'label' else '괄호 소제목'} 자리로는 올릴 수 없습니다")
        return p["tpl"], int(p["level"])
    if _slot(ov, tid, level + 1) is not None:
        return tid, level + 1
    raise ValueError(f"템플릿 #{ov['templates'][tid]['no']}에 더 깊은 레벨이 없습니다")


def _resolve_parent(seq, i, o2, tid, level):
    """줄 i 가 (tid, level)일 때의 부모 — 앞으로 거슬러: 같은 (tid, level) 줄 → 그 부모, (tid, level−1) 줄 → 그 줄, 첫 레벨(L1 · 종속 템플릿은 L base+1)이면 그 템플릿이 매달리던 슬롯의 줄 → 그 줄,
    같은 템플릿의 더 얕은 줄 → 그 줄. 못 찾으면 None."""
    tp = o2["templates"].get(str(tid), {})
    first = int(tp.get("base") or 0) + 1  # 그 템플릿의 첫 레벨(종속 템플릿은 base + 1)
    firsts = (first, first + lift_depth(tp)) if tp.get("lift") else (first,)  # 표 제목을 표 레벨로 넣은 템플릿(② §8-7)은 첫 글 레벨 줄도 — 위에 표가 없으면 그 템플릿이 매달리던 슬롯의 줄로
    for j in range(i - 1, -1, -1):
        q = seq[j]["id"]
        y = o2["lines"].get(q)
        if y is None:
            continue
        if y["tpl"] == tid and y["level"] == level:
            return y["parent"]
        if y["tpl"] == tid and y["level"] == level - 1:
            return q
        if level in firsts and tid in (o2["branches"].get(f"{y['tpl']}|{y['level']}") or []):
            return q
        if y["tpl"] == tid and y["level"] < level - 1:
            return q
    return None


def plan_level(seq, idxs, delta, ov, text_of):
    """Alt+↑/↓ — 줄들(같은 그릇)의 개요 레벨을 한 단계(delta −1 올림 / +1 내림). 변경 전 상태에서 모두 계획하고 하나라도 못 바꾸면 전부 거절(ValueError).
    자식은 안 따라간다 — 영향 구간(옛 부모의 부분 트리) 줄들의 부모를 다시 붙인다."""
    idxs = sorted(set(idxs))
    targets = []
    for i in idxs:
        x = _check_line(ov, seq[i]["id"], "level")
        targets.append((i, x, *_target(ov, x, delta)))
    shadow = {p: dict(v) for p, v in ov["lines"].items()}
    o2 = {**ov, "lines": shadow}
    acts, focus = [], []
    for i, x, tid, level in targets:
        pid = seq[i]["id"]
        slot = _need_slot(ov, tid, level)
        text = text_of(pid)
        lead, tok, gap = prefix_of(text, x["letter"] or None)
        old_len = len(lead) + len(tok) + len(gap)
        old_parent = x["parent"]
        shadow[pid].update(tpl=tid, no=ov["templates"][tid]["no"], level=level,
                           key=ov["templates"][tid]["chain"][level - 1] if level - 1 < len(ov["templates"][tid]["chain"]) else "")
        parent = _resolve_parent(seq, i, o2, tid, level)
        if parent is None and not (level == 1 + lift_depth(ov["templates"][tid]) and ov["templates"][tid]["kind"] == "main"):  # 표를 표 레벨로 넣은 주 사슬(② §8-7)은 그 아래 첫 글 레벨이 바깥 글 레벨
            raise ValueError("이 자리에서 그 레벨로 바꾸면 매달릴 부모 줄이 없습니다")
        shadow[pid]["parent"] = parent
        letter = slot["letter"]
        if is_numbered(shadow[pid]["key"]):
            letter = first(letter, _parent_letter(o2, parent))  # 번호는 아래 renumber 가 형제 차례로 다시 매김
        shadow[pid]["letter"] = letter
        prefix = _prefix_for(slot, letter)
        acts.append({"act": "restyle", "id": pid, "old_len": old_len, "prefix": prefix, "attrs": slot["attrs"], "line": dict(shadow[pid])})
        focus.append({"id": pid, "offset": len(prefix), "shift": len(prefix) - old_len})
        for j in range(i + 1, len(seq)):  # 영향 구간 — 옛 부모의 부분 트리 안(옛 자식·뒤 형제)
            q = seq[j]["id"]
            if q not in shadow:
                continue
            if old_parent is not None and not is_descendant(o2, q, old_parent) and shadow[q]["parent"] != pid:
                break
            np = _resolve_parent(seq, j, o2, shadow[q]["tpl"], shadow[q]["level"])
            if np is not None and np != shadow[q]["parent"]:
                shadow[q]["parent"] = np
                acts.append({"act": "reparent", "id": q, "parent": np})
        groups = {(old_parent, x["tpl"], int(x["level"])), (parent, tid, level)}
        for gp, gt, gl in groups:
            anchor = i if (gp, gt, gl) == (parent, tid, level) else _nearest_sibling(seq, i, o2, gp, gt, gl)
            acts += renumber(seq, ov, _texts_with(text_of, acts), gp, gt, gl, shadow=shadow, anchor=anchor, fresh=(pid,))
    return {"actions": acts, "focus": focus[0] if focus else None, "focuses": focus}


def _nearest_sibling(seq, i, o2, parent, tid, level):
    """자리 i 에서 가장 가까운(앞 우선) 같은 묶음 형제 자리 — 번호 다시 매김의 기준(없으면 None)."""
    idx = siblings(seq, o2, parent, tid, level)
    if not idx:
        return None
    before = [j for j in idx if j <= i]
    return before[-1] if before else idx[0]


def plan_move(seq, i, k, where, ov, text_of):
    """끌어 놓기 — 줄 X(i)의 단위(앞 간격 줄 + 부분 트리의 마지막 내용 문단까지)를 같은 (tpl, level) 줄 Y(k)의 단위 앞/뒤로. 양쪽 형제 번호 다시 매김."""
    x, y = _check_line(ov, seq[i]["id"], "move"), _check_line(ov, seq[k]["id"], "move")
    if (x["tpl"], x["level"]) != (y["tpl"], y["level"]):
        raise ValueError("같은 템플릿·같은 레벨의 줄끼리만 옮길 수 있습니다")
    xe, xl = subtree(seq, i, ov)
    ye, yl = subtree(seq, k, ov)
    if i <= k < xe:
        raise ValueError("제 부분 트리 안으로는 옮길 수 없습니다")
    slot = _slot(ov, x["tpl"], x["level"])
    xs = _own_spacer(seq, i, slot)
    first_i = xs if xs is not None else i
    if where == "before":
        ks = _own_spacer(seq, k, slot)
        ref, after = seq[ks if ks is not None else k]["id"], False
    else:
        ref, after = seq[yl]["id"], True
    acts = [{"act": "move", "first": seq[first_i]["id"], "last": seq[xl]["id"], "ref": ref, "after": after}]
    shadow = {p: dict(v) for p, v in ov["lines"].items()}
    if x["parent"] != y["parent"]:
        shadow[seq[i]["id"]]["parent"] = y["parent"]
        acts.append({"act": "reparent", "id": seq[i]["id"], "parent": y["parent"]})
    unit = seq[first_i:xl + 1]
    rest = seq[:first_i] + seq[xl + 1:]
    kk = next(j for j, it in enumerate(rest) if it["id"] == ref)
    seq2 = rest[:kk] + unit + rest[kk:] if not after else rest[:kk + 1] + unit + rest[kk + 1:]
    o2 = {**ov, "lines": shadow}
    xi = next(j for j, it in enumerate(seq2) if it["id"] == seq[i]["id"])
    for gp in {x["parent"], y["parent"]}:
        anchor = xi if gp == y["parent"] else _nearest_sibling(seq2, xi, o2, gp, x["tpl"], x["level"])
        acts += renumber(seq2, ov, _texts_with(text_of, acts), gp, x["tpl"], x["level"], shadow=shadow, anchor=anchor, fresh=(seq[i]["id"],))
    return {"actions": acts, "focus": {"id": seq[i]["id"], "offset": None}}


def plan_remove(seq, i, ov, text_of):
    """빈 레터 줄 Backspace — 글 없는 기호·번호 줄(라벨 아님, 자손 없음)을 앞 간격 줄과 함께 지운다. 뒤 형제 번호 다시 매김."""
    pid = seq[i]["id"]
    x = _check_line(ov, pid, "remove")
    if body_of(text_of(pid), x["letter"] or None):
        raise ValueError("글이 있는 줄은 지우지 않습니다")
    end_i, last = subtree(seq, i, ov)
    if any(seq[j]["id"] in ov["lines"] for j in range(i + 1, end_i)):
        raise ValueError("하위 줄이 있는 줄은 지우지 않습니다 — 하위 줄부터")
    acts = [{"act": "remove", "id": pid}]
    xs = _own_spacer(seq, i, _slot(ov, x["tpl"], x["level"]))
    if xs is not None and seq[xs]["id"] not in ov["lines"]:
        acts.append({"act": "remove", "id": seq[xs]["id"]})
    shadow = {p: dict(v) for p, v in ov["lines"].items() if p != pid}
    for y in shadow.values():
        if y["parent"] == pid:
            y["parent"] = x["parent"]
    seq2 = [it for j, it in enumerate(seq) if j != i and j != xs]
    o2 = {**ov, "lines": shadow}
    anchor = _nearest_sibling(seq2, min(i, len(seq2) - 1), o2, x["parent"], x["tpl"], x["level"])
    acts += renumber(seq2, ov, text_of, x["parent"], x["tpl"], x["level"], shadow=shadow, anchor=anchor)
    j = next((j for j in range(i - 1, -1, -1) if not seq[j]["blank"] and j != xs), None)
    return {"actions": acts, "focus": {"id": seq[j]["id"] if j is not None else None, "offset": "end"}}
