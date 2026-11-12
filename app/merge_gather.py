"""취합 — 3방향 엔진(spec_취합 ② §4-1 자리 연결 · §4-2 판정 · §4-4 넣기 계획 → 반영 · §4-5 계산 칸). 기준본 B(배포한 프레임의 자리 정보 — merge_gather_frame.make) ·
기관 문서 S · 지금 취합본 T. 스크립트만(LLM 없음). 이관 엔진(merge_pairs 의 점수 짝)을 쓰지 않는다 — 같은 기준본에서 나온 문서끼리 **달라진 곳만** 찾아 원래 자리에 넣는다.

- `links(frame, part)` = 기준본 ↔ 기관 문서 맞춤(취합본을 안 본다) → `{"coverage": {anchors, blocks, ratio}, "items": [작성 내용], "reasons": [] | ["noMatch"]}`.
  ① **닻**: 기준본의 title·label·table 줄 가운데 열쇠가 그 범위에서 두 문서에 하나씩인 것을 차례를 지켜(가장 긴 늘어나는 열 — patience) 잡고, 닻 사이 구간에서 되풀이한다.
     기관마다 되풀이되는 뼈대는 기관 라벨이 닻이 된 뒤에야 그 구간에서 하나뿐이 된다. 닻이 하나도 없으면 `noMatch`(끌어 넣기만).
  ② **구간 맞춤**: 닻 사이에서 앞·뒤의 자리대로 같은 줄을 떼고 가운데만 `difflib.SequenceMatcher(autojunk=False)`(가운데가 DIFF_CELLS 를 넘으면 안 맞춘다 — 거의 줄 수에 비례).
     같은 열쇠 짝은 그 구간의 수가 두 문서에서 같고 몇째인지도 같을 때만 믿는다(「해당 없음」 ×3 → ×1 은 어느 줄인지 모른다).
     글머리만 있는 자리표시 줄(「o」·「-」)끼리는 수가 달라도 믿는다 — 서로 바꿔도 결과가 같다. 못 믿는 같은 글 줄이 남은 틈은 통째로 `unknownPlace`.
  ③ **틈**(믿는 맞춤 사이) → 작성 내용: `filled`(기준본의 자리표시 줄 대신 든 글 — 자리표시 줄은 지운다) · `added`(끼어든 블록들) · `removed`(기준본 블록이 없어짐 — 안내 줄·작성요령 표는 말하지 않는다) ·
     `changed`(제목·라벨·양식 글이 비슷한 글로 바뀜 — 보고만 · 잇달아 바뀐 양식 글은 한 줄로 묶음). 그 틈에서 기준본의 제목·구분 라벨·표가 없어졌거나 바뀌었으면 그 틈의 내용은 `unknownPlace`
     (기관이 제 라벨을 지우고 쓴 글을 앞 기관 것으로 삼지 않는다). 양식 글·그림이 없어진 바로 그 자리의 글도 `unknownPlace`(고쳐 쓴 것인지 새 내용인지 모른다).
     지운 표 자리에 다른 표가 있으면 「다시 그린 표」 로 짝지어 `structure`. 자리의 구분 라벨(scope.labels)이 기관 문서에서 안 맞았어도 · 자리가 서로 다른 기관에 걸쳐도 `unknownPlace`.
     끼어들기만 한 내용의 자리 = 앞 경계의 자리(뒤 경계가 다음 항목의 라벨·제목인 「항목 끝에 덧붙임」 은 앞 항목 것).
  ④ **표**(같은 열쇠로 맞은 표): 격자(행·열·병합)가 같으면 칸마다 — input 칸은 `cells`(자리의 기관·차년도마다 하나), 머리 칸은 `changed`, 계산 칸은 `calc`(복사 안 함), 칸 안 표·그림은 `structure`.
     이어 넣는 표(list)에서 기준본 행이 차례대로 다 있고 행만 늘었으면 `rows`(닻 행 뒤 — 머리 행뿐이면 아래 행 위). 그 밖은 `structure`. 기관이 비운 칸은 취합본에서 지우지 않는다.
  links 의 status 는 스크립트의 자리 판정뿐이다 — `ready`(넣을 수 있는 후보) | `unknownPlace`·`structure`·`changed`·`removed`·`calc`(막힘).
- `judge(items, frame, to, cfg, applied=None)` = 3방향 판정(§4-2) → 사본 목록. 막힌 상태는 그대로 두고 후보(`ready`)만: 반영할 기관 미지정 `unassigned` → 다른 기관 자리·끈 공통 자리 `otherOrg` →
  모르는 자리 `unknownPlace` → 넣은 기록이 지금 문서와 맞거나(넣은 블록이 모두 그 자리에 있고 지문이 같음) T == S 면 `same` → T == B(경계와 그 사이가 기준본의 id·글 그대로)면 `ready` → 그 밖 `overlap`.
  `to{prev, next}` = 지금 취합본에서 넣을 자리(prev = 그 뒤에 넣을 블록 — 넣지 않는 것은 화면이 갈 경계·표). cells 는 칸마다 상태(`from.cells[].status`)를 달고 넣을 칸이 하나라도 있으면 ready.
  rows 는 넣은 기록으로만 `same`(글이 같은 행을 다른 기관이 넣었을 수 있다 — 넣은 칸이 일부만 남았거나 바뀌었으면 `overlap`, 하나도 없으면 다시 `ready`).
  넣을 자리의 글과 그 뒤 표·그림이 한 문단(hp:p)에 묶여 있으면 그 사이에 넣을 수 없어 `unknownPlace`. 결정(cfg.decisions)은 `decision` 에 붙일 뿐 상태를 못 바꾼다.
- `plan(items, frame, to, part)` = 넣기 계획(문서는 안 바뀜) — `ready` 이고 결정이 skip·check 가 아닌 것만 → `{todo, ops[내부], items[화면 줄], skipped{상태: n}, calc[], dropped[], formulas[]}`.
- `apply(to_doc, part_doc, plan)` = 반영(server._transact 안에서 불린다 — 트랜잭션·잠금은 부르는 쪽) → `{applied{열쇠: {ids, fp, kind}}, counts, calc[], dropped[], skipped[]}`.
  본문 = 넣을 자리 뒤에 `insert_after(kind=copy, src=기관 문서)`(문단·표·그림을 기관 문서 차례대로) + **틀 맞춤**(개요 깊이·레터 꼴이 취합본 틀과 다른 줄만 그 자리의 틀로 — `merge_gather_fit`,
  두 문서의 2단계 그래프가 있을 때. 넣은 줄의 원래 꼴 ↔ 맞춘 자리는 `applied[열쇠].convert`) + 자리표시 줄 지움 + 그림 `fit_image`.
  칸 = `set_text` + `fit_chars`(지금 글이 기준본 글일 때만). 행 = 닻 행(먼저 넣은 행들의 뒤)을 `clone_rows` 로 본뜬 뒤 칸 글(계산 칸은 비움).
  계산 칸(§4-5): 쓴 칸을 피연산자로 둔 수식 칸은 단순 합이면 다시 계산해 넣고(수만 든 칸일 때), 그 밖은 「다시 계산 필요」(`calc[].action = needed`)로 싣는다 — 수를 지어내지 않는다.
원본(기관 문서)은 읽기만 한다."""
import copy
import difflib
import hashlib
import json
import re
from bisect import bisect_left
from collections import Counter, defaultdict

from lxml import etree

from app import heading_calc as HC
from app import merge_gather_fit as FIT
from app import merge_gather_frame as F
from app.hwpx_doc import DROP_ON_COPY

BLOCKED = ("unknownPlace", "structure", "changed", "removed", "calc")
BODY = ("added", "filled")
DEPTH = 40                 # 닻 되풀이 깊이 상한
DIFF_CELLS = 400_000       # 닻 사이 구간 맞춤 상한(앞·뒤 같은 줄을 뗀 가운데의 기준본 줄 × 기관 문서 줄) — 넘으면 맞추지 않고 「확인 필요」(SequenceMatcher 는 같은 글 줄이 많으면 제곱으로 느리다: 2000 × 2000 에 4초~28초)
FUZZY, FUZZY_SURE, FUZZY_CELLS = 0.6, 0.85, 2500   # 「고쳐 쓴 줄」 로 볼 닮음 · 틈 크기 상한
TEXT_MAX = 200
PASSES = 6
_PLAIN_NUM = re.compile(r"^\d[\d,]*(?:\.\d+)?$")


def _sha(x):
    return hashlib.sha1(json.dumps(x, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def _short(text, n=TEXT_MAX):
    return F._short(text, n)


def _fp_blocks(blocks):
    """넣은 본문 블록들의 지문 — 문단은 견줄 글(빈 줄은 뺌), 표는 칸 글·격자 전체, 그림은 있음만."""
    out = []
    for b in blocks:
        t = b.get("type")
        if t == "table":
            out.append(["t", F.table_full(F.grid(b))])
        elif t == "image":
            out.append(["i"])
        elif k := F.para_key(b.get("text")):
            out.append(["p", k])
    return _sha(out)


def _fp_rows(rows):
    """맞춤 줄(F.rows)의 지문 — _fp_blocks 와 같은 값."""
    return _sha([["t", F.table_full(r["table"])] if r["kind"] == "tbl" else ["i"] if r["kind"] == "pic" else ["p", r["key"]] for r in rows if r["key"]])


def _fp_texts(texts):
    return _sha([F.norm(t) for t in texts])


# ---- 자리 연결(§4-1) -------------------------------------------------------------------------------------------

class _Ctx:
    """자리 연결 한 번의 자료 — B·S = 빈 줄을 뺀 기준본·기관 문서 줄, matched = 맞은 기준본 블록 id → 기관 문서 줄."""

    def __init__(self, frame, part):
        self.frame, self.tag = frame, str(frame.get("frameId") or frame.get("rev") or "")
        self.fb = frame["blocks"]
        self.B = [b for b in self.fb if b["key"]]
        self.sr = F.rows(part["blocks"], frame=frame, doc=part.get("doc"))
        self.S = [r for r in self.sr if r["key"]]
        self.fat = {b["id"]: b for b in self.fb}
        self.names = {o["key"]: o["name"] for o in frame.get("orgs") or ()}
        self.matched, self.items, self.n = {}, [], 0

    def match(self, bi, si):
        self.matched[self.B[bi]["id"]] = self.S[si]

    def scope(self, sc):
        sc = sc or {"kind": "unknown"}
        return {"kind": sc.get("kind") or "unknown", "org": sc.get("org"), "orgName": self.names.get(sc.get("org")) if sc.get("org") else None,
                "year": sc.get("year"), "stage": sc.get("stage")}

    def hunk(self, kind, status, detail, *, at, scope, path, prev=None, nxt=None, base=None, frm=None, text="", counts=None, unique="", fp=None, labels=()):
        """작성 내용 하나를 적는다 — 열쇠 = 기준 판 + 앞·뒤 경계 id + 종류 + 내용 지문(§4-1)."""
        base = {"prev": prev, "next": nxt, "ids": [], "table": None, **(base or {})}
        frm = {"ids": [], "table": None, "cells": [], "rows": [], **(frm or {})}
        c = {"paragraphs": 0, "tables": 0, "pictures": 0, "cells": 0, "rows": 0, **(counts or {})}
        self.n += 1
        h = {"key": _sha([self.tag, prev, nxt, base["table"], kind, fp]), "kind": kind, "status": status, "detail": detail, "scope": self.scope(scope),
             "path": list(path or ()), "base": base, "from": frm, "to": {"prev": None, "next": None}, "text": _short(text), "counts": c,
             "unique": unique if status == "ready" else "", "decision": None, "_at": (at, self.n), "_labels": list(labels or ())}
        self.items.append(h)
        return h


def _lis(pairs):
    """(기준본 차례, 기관 문서 차례) 짝들(기준본 차례순)에서 기관 문서 차례가 가장 길게 늘어나는 것 — 차례를 지키는 닻."""
    tails, at, back = [], [], [None] * len(pairs)
    for k, (_, s) in enumerate(pairs):
        j = bisect_left(tails, s)
        if j == len(tails):
            tails.append(s)
            at.append(k)
        else:
            tails[j], at[j] = s, k
        back[k] = at[j - 1] if j else None
    out, k = [], at[-1] if at else None
    while k is not None:
        out.append(pairs[k])
        k = back[k]
    return out[::-1]


def _anchors(B, S, b0, b1, s0, s1, out, depth=0):
    """B[b0:b1] ↔ S[s0:s1] 에서 닻을 잡고 닻 사이 구간에서 되풀이(모듈 설명 ①). 열쇠의 수는 그 범위의 **모든 줄**에서 센다(목차의 같은 글도 센다)."""
    if b0 >= b1 or s0 >= s1 or depth > DEPTH:
        return
    cb, cs = Counter(B[i]["key"] for i in range(b0, b1)), Counter(S[j]["key"] for j in range(s0, s1))
    one = {S[j]["key"]: j for j in range(s0, s1) if cs[S[j]["key"]] == 1}
    got = _lis([(i, one[B[i]["key"]]) for i in range(b0, b1)
                if B[i]["cls"] in F.ANCHOR and cb[B[i]["key"]] == 1 and B[i]["key"] in one and S[one[B[i]["key"]]]["kind"] == B[i]["kind"]])
    if not got:
        return
    edges = [(b0 - 1, s0 - 1), *got, (b1, s1)]
    for (pb, ps), (nb, ns) in zip(edges, edges[1:]):
        _anchors(B, S, pb + 1, nb, ps + 1, ns, out, depth + 1)
    out.extend(got)


def _nth(keys):
    seen, out = Counter(), []
    for k in keys:
        out.append(seen[k])
        seen[k] += 1
    return out


def _ph(b):
    """기준본 줄이 채우면 지울 자리표시 줄인가."""
    return b["kind"] == "p" and b["cls"] == "guide" and F.placeholder(b["text"])


def _quiet(b):
    """없어져도 말하지 않는 기준본 줄 — 안내·자리표시 줄, 작성요령 표."""
    return b["cls"] == "guide" or (b["kind"] == "tbl" and bool(b["table"].get("guide")))


def _diff(ctx, b0, b1, s0, s1):
    """닻 사이 구간 하나 — 믿는 맞춤을 적고 그 사이 틈마다 작성 내용을 낸다(모듈 설명 ②)."""
    B, S = ctx.B, ctx.S
    kb, ks = [B[i]["key"] for i in range(b0, b1)], [S[j]["key"] for j in range(s0, s1)]
    trusted = []
    if kb == ks:
        trusted = [(b0 + k, s0 + k) for k in range(len(kb))]
    elif kb and ks:
        p, q, lim = 0, 0, min(len(kb), len(ks))
        while p < lim and kb[p] == ks[p]:   # 앞·뒤에서 자리대로 같은 줄은 그대로 맞춘다 — 고친 곳이 몇 군데뿐인 문서에서 가운데만 견준다(거의 줄 수에 비례)
            p += 1
        while q < lim - p and kb[-1 - q] == ks[-1 - q]:
            q += 1
        same = [(k, k) for k in range(p)]
        ma, mb = kb[p:len(kb) - q], ks[p:len(ks) - q]
        if ma and mb and len(ma) * len(mb) <= DIFF_CELLS:
            same += [(p + a + k, p + b + k) for a, b, n in difflib.SequenceMatcher(None, ma, mb, autojunk=False).get_matching_blocks() for k in range(n)]
        same += [(len(kb) - q + k, len(ks) - q + k) for k in range(q)]
        cb, cs, nb, ns = Counter(kb), Counter(ks), _nth(kb), _nth(ks)
        trusted = [(b0 + a, s0 + b) for a, b in same if (cb[kb[a]] == cs[kb[a]] and nb[a] == ns[b]) or _ph(B[b0 + a])]
    pb, ps = b0, s0
    for bi, si in [*trusted, (b1, s1)]:
        if bi > pb or si > ps:
            _gap(ctx, pb, bi, ps, si)
        if bi < b1:
            ctx.match(bi, si)
        pb, ps = bi + 1, si + 1


def _edge(ctx, g0, g1):
    B = ctx.B
    return (B[g0 - 1] if g0 else None), (B[g1] if g1 < len(B) else None)


def _path_of(b):
    """그 줄이 자리의 앞 경계일 때의 소속 사슬 — 제목·라벨이면 그 줄까지."""
    if b is None:
        return []
    return [*b["path"], F._short(F._NOTE.sub("", b["text"]) or b["text"], F.TITLE_MAX)] if b["cls"] in ("title", "label") else list(b["path"])


def _count(rows):
    c = Counter(r["kind"] for r in rows)
    return {"paragraphs": c["p"], "tables": c["tbl"], "pictures": c["pic"]}


def _span_ids(ctx, rows):
    """기관 문서 줄들(이어진 것)의 첫 줄부터 끝 줄까지 — 사이에 낀 빈 줄도 함께 복사한다."""
    return [r["id"] for r in ctx.sr[rows[0]["i"]:rows[-1]["i"] + 1]] if rows else []


def _ambiguous(ctx, g0, g1, h0, h1, shared):
    """같은 글 줄이 여럿이라 어느 줄이 바뀌었는지 못 정하는 틈 — 달라진 것만 추려 「확인 필요」 하나."""
    B, S = ctx.B, ctx.S
    base, part = B[g0:g1], S[h0:h1]
    need, have = Counter(r["key"] for r in part), Counter(b["key"] for b in base)
    b_only, s_only = [], []
    for b in base:
        if need[b["key"]] > 0:
            need[b["key"]] -= 1
        elif not _quiet(b):
            b_only.append(b)
    full = {F.table_full(b["table"]) for b in base if b["kind"] == "tbl"}
    for r in part:
        if have[r["key"]] > 0:
            have[r["key"]] -= 1
            if r["kind"] == "tbl" and F.table_full(r["table"]) not in full:
                s_only.append(r)   # 머리는 같은데 칸이 달라진 표 — 어느 표인지 못 정한다
        else:
            s_only.append(r)
    if not b_only and not s_only:
        return
    prev, nxt = _edge(ctx, g0, g1)
    word = next((b["text"] for b in base if b["key"] in shared), "")
    why = f"같은 글 줄(「{_short(word, 30)}」)이 이 구간에 여럿이라(또는 구간이 너무 커) 자리를 하나로 정할 수 없음"
    first = b_only[0] if b_only else base[0] if base else None
    sc = (first or prev or nxt or {}).get("scope")
    ctx.hunk("added" if s_only else "removed", "unknownPlace" if s_only else "removed", why, at=g0, scope=sc, path=first["path"] if first else _path_of(prev),
             prev=prev and prev["id"], nxt=nxt and nxt["id"], base={"ids": [b["id"] for b in b_only]}, frm={"ids": [r["id"] for r in s_only]},
             text=" / ".join(r["text"] for r in s_only) or " / ".join(b["text"] for b in b_only), counts=_count(s_only),
             fp=[[b["id"] for b in b_only], [[r["kind"], r["key"]] for r in s_only]])


def _gap(ctx, g0, g1, h0, h1):
    """믿는 맞춤 사이의 틈 하나 B[g0:g1] ↔ S[h0:h1](모듈 설명 ③)."""
    B, S = ctx.B, ctx.S
    shared = {B[i]["key"] for i in range(g0, g1)} & {S[j]["key"] for j in range(h0, h1)}
    if shared:
        return _ambiguous(ctx, g0, g1, h0, h1, shared)
    base, part = B[g0:g1], S[h0:h1]
    lost = next((b for b in base if b["cls"] in ("title", "label") or (b["kind"] == "tbl" and not b["table"].get("guide"))), None)
    poison = lost and f"그 틈에서 기준본의 {'표' if lost['kind'] == 'tbl' else '구분 라벨' if lost['cls'] == 'label' else '제목 줄'} 「{_short(lost['text'], 40)}」 이 없어졌거나 바뀜"
    before, after = _edge(ctx, g0, g1)
    pairs = _pairs(base, part)
    edges = [(-1, -1, None), *pairs, (len(base), len(part), None)]
    run = []   # 잇달아 바뀐 양식 글(목차의 쪽 번호처럼 줄마다 고친 것) — 한 줄로 묶어 보고한다

    def flush():
        if run:
            (k, b, r, prev), rest = run[0], run[1:]
            ctx.hunk("changed", "changed", f"「{_short(b['text'], 60)}」 → 「{_short(r['text'], 60)}」" + (f" 외 {len(rest)}줄" if rest else ""), at=k, scope=b["scope"], path=b["path"],
                     prev=prev and prev["id"], base={"ids": [x[1]["id"] for x in run]}, frm={"ids": [x[2]["id"] for x in run]}, text=" / ".join(x[2]["text"] for x in run),
                     counts={"paragraphs": len(run)}, fp=[[x[1]["id"], x[2]["key"]] for x in run])
            run.clear()
    for (pi, pj, _), (ni, nj, how) in zip(edges, edges[1:]):
        prev = base[pi] if pi >= 0 else before
        nxt = base[ni] if ni < len(base) else after
        if ni > pi + 1 or nj > pj + 1 or how != "changed" or base[ni]["cls"] != "fixed":
            flush()
        _segment(ctx, g0 + pi + 1, base[pi + 1:ni], part[pj + 1:nj], prev, nxt, poison)
        if how == "changed":
            run.append((g0 + ni, base[ni], part[nj], prev))
            if base[ni]["cls"] != "fixed":
                flush()   # 제목·라벨이 바뀐 것은 하나씩
        elif how:
            b, r = base[ni], part[nj]
            ctx.hunk("cells", "structure", "표를 다시 그렸거나 머리 칸·열이 달라짐 — 칸을 하나씩 이을 수 없음", at=g0 + ni, scope=b["scope"], path=b["path"],
                     prev=prev and prev["id"], nxt=nxt and nxt["id"], base={"ids": [b["id"]], "table": b["id"]}, frm={"ids": [r["id"]], "table": r["id"]},
                     text=r["text"], counts=_count([r]), fp=[b["id"], r["key"], F.table_full(r["table"])])
    flush()


def _ratio(a, b):
    """두 줄(견줄 꼴)의 닮음 — 앞머리가 길게 같으면(번호 붙은 줄의 꼬리만 고친 것 — 목차의 「(페이지 표기)」 → 쪽 번호) 닮은 것으로 친다."""
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    if n >= max(4, min(len(a), len(b)) // 2):
        return max(FUZZY, n / max(len(a), len(b)))
    m = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return m.ratio() if m.real_quick_ratio() >= FUZZY and m.quick_ratio() >= FUZZY else 0.0


def _pairs(base, part):
    """틈 안에서 차례를 지켜 짝짓는 것 [(기준본 차례, 기관 문서 차례, how)] — 고쳐 쓴 제목·라벨·양식 글(`changed` — 글이 닮음) · 지운 표 자리의 다른 표(`structure` — 다시 그린 표)."""
    out, last = [], -1
    fuzzy = len(base) * len(part) <= FUZZY_CELLS
    for i, b in enumerate(base):
        j = None
        if b["kind"] == "tbl" and not b["table"].get("guide"):
            j, how = next((j for j in range(last + 1, len(part)) if part[j]["kind"] == "tbl"), None), "structure"
        elif fuzzy and b["kind"] == "p" and b["cls"] in ("title", "label", "fixed"):
            best, how = 0.0, "changed"
            for k in range(last + 1, len(part)):
                if part[k]["kind"] != "p":
                    continue
                v = _ratio(b["key"], part[k]["key"])
                if v > best:
                    best, j = v, k
                if v >= FUZZY_SURE:
                    break
        if j is not None:
            out.append((i, j, how))
            last = j
    return out


def _sk(sc):
    return (sc.get("kind"), sc.get("org"), sc.get("year"), sc.get("stage"))


def _segment(ctx, at, seg_b, seg_s, prev, nxt, poison):
    """틈의 한 토막(고쳐 쓴 줄 사이) — 없어진 기준본 줄은 `removed`, 든 내용은 `filled`(자리표시 줄 대신)·`added`."""
    gone = [b for b in seg_b if not _quiet(b)]
    pid, nid = prev and prev["id"], nxt and nxt["id"]
    if gone:
        ctx.hunk("removed", "removed", f"기준본의 블록 {len(gone)}개가 기관 문서에 없음", at=at, scope=gone[0]["scope"], path=gone[0]["path"], prev=pid, nxt=nid,
                 base={"ids": [b["id"] for b in gone]}, text=" / ".join(b["text"] for b in gone[:6]), fp=[b["id"] for b in gone])
    if not seg_s:
        return
    drop = [b for b in seg_b if _ph(b)]
    spot = drop[0] if drop else seg_b[-1] if seg_b else None   # 그 뒤에 넣을 기준본 줄(없으면 앞 경계 뒤)
    status, detail, labels = "ready", "", []
    if seg_b:
        sc = seg_b[0]["scope"]
        labels = [x for b in seg_b for x in b["scope"].get("labels") or ()]
        if len({_sk(b["scope"]) for b in seg_b}) > 1:
            status, detail = "unknownPlace", "자리가 서로 다른 기관·차년도의 자리에 걸쳐 있음"
    else:   # 끼어들기만 한 내용 — 앞 경계의 자리(뒤 경계가 다음 항목의 라벨·제목인 「항목 끝에 덧붙임」 은 앞 항목 것)
        sc = (prev or nxt or {}).get("scope") or {"kind": "unknown"}
        labels = list(sc.get("labels") or ())
        a, b = (prev or {}).get("scope") or {}, (nxt or {}).get("scope") or {}
        if a.get("kind") == "org" and b.get("kind") == "org" and a.get("org") != b.get("org") and nxt["cls"] not in ("label", "title"):
            status, detail = "unknownPlace", "앞뒤 경계가 서로 다른 기관의 자리"
    if poison:
        status, detail = "unknownPlace", poison
    elif gone:   # 양식 글·그림이 없어진 바로 그 자리의 글 — 그 글을 고쳐 쓴 것인지 새 내용인지 정할 수 없다
        status, detail = "unknownPlace", f"그 자리에서 기준본의 {'그림' if gone[0]['kind'] == 'pic' else '양식 글'} 「{_short(gone[0]['text'], 40)}」 이 없어짐 — 고쳐 쓴 것인지 새 내용인지 정할 수 없음"
    elif prev is None and spot is None:
        status, detail = "unknownPlace", "문서 맨 앞 — 앞 경계가 없음"
    lead = 0
    if spot is None and prev is not None:   # 앞 경계와 내용 사이의 빈 줄 수(기관 문서) — 취합본에서도 그만큼 건너뛰고 넣는다(기준본에 있는 빈 줄까지만)
        k = seg_s[0]["i"] - 1
        while k >= 0 and not ctx.sr[k]["key"]:
            k, lead = k - 1, lead + 1
    unique = (f"자리표시 줄 「{_short(drop[0]['text'], 20)}」 을 대신함" if drop else
              f"앞 경계 「{_short((prev or {}).get('text'), 40)}」 · 뒤 경계 「{_short((nxt or {}).get('text'), 40)}」 — 둘 다 기준본과 맞은 줄")
    ctx.hunk("filled" if drop else "added", status, detail, at=at, scope=sc, path=_path_of(prev) if not seg_b else seg_b[0]["path"], prev=pid, nxt=nid,
             base={"ids": [b["id"] for b in drop], "gap": [[b["id"], b["key"]] for b in seg_b], "edge": [prev and prev["key"], nxt and nxt["key"]],
                   "spot": spot and spot["id"], "lead": lead},
             frm={"ids": _span_ids(ctx, seg_s), "keys": [r["key"] for r in seg_s], "fp": _fp_rows(seg_s)},
             text=" / ".join(r["text"] for r in seg_s if r["text"].strip()), counts=_count(seg_s), unique=unique, labels=labels,
             fp=[[r["kind"], r["key"]] for r in seg_s])


# ---- 표(§4-1 「표」) ---------------------------------------------------------------------------------------------

def _by_row(t):
    rows = defaultdict(list)
    for c in t["cells"]:
        rows[c["r"]].append(c)
    return rows


def _lay(cells):
    return [(c["c"], c["cs"]) for c in cells]


def _row_anchor(ft, brow, new, up, down):
    """늘어난 행 new(기관 문서의 그 행에서 시작하는 칸들)를 본뜰 기준본 행 → (행, 위에 넣나, [첫 열, 끝 열]) | None. 위 행(up)이 같은 모양의 자료 행이면 그 뒤,
    위가 머리 행뿐이거나 모양이 다르면 아래 행(down)의 위."""
    if not new or any(c["rs"] != 1 for c in new):
        return None
    c0, c1 = new[0]["c"], new[-1]["c"] + new[-1]["cs"] - 1

    def fit(r):
        cells = [c for c in brow.get(r, ()) if c0 <= c["c"] <= c1] if r is not None and 0 <= r < ft["rows"] else []
        return cells if cells and _lay(cells) == _lay(new) and all(c["rs"] == 1 for c in cells) else None
    for r, above in ((up, False), (down, True)):
        cells = fit(r)
        if cells and any(c["cls"] != "head" for c in cells):
            return r, above, [c0, c1]
    return None


def _rowmap(ft, st):
    """이어 넣는 표의 행 맞춤 → ({기준본 행: 기관 문서 행}, [(기관 문서 행, 닻 행, 위에 넣나, 열 범위)]) | None(행만 늘어난 것이 아님 — `structure`).
    기준본 행이 차례대로 다 있어야 한다. 글이 바뀐 행은 모양(열·열 병합)이 같을 때 자리대로 잇고(빈 행을 채운 것), 남는 행이 늘어난 행이다."""
    brow, srow = _by_row(ft), _by_row(st)
    sig = lambda rows, n: [tuple((c["c"], c["cs"], F.norm(c["text"])) for c in rows.get(r, ())) for r in range(n)]  # noqa: E731
    rowmap, ins = {}, []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, sig(brow, ft["rows"]), sig(srow, st["rows"]), autojunk=False).get_opcodes():
        if tag == "equal":
            rowmap.update((i1 + k, j1 + k) for k in range(i2 - i1))
            continue
        n = i2 - i1
        if j2 - j1 < n:
            return None   # 행이 줄어듦
        for k in range(n):
            if _lay(brow.get(i1 + k, ())) != _lay(srow.get(j1 + k, ())):
                return None
            rowmap[i1 + k] = j1 + k
        for j in range(j1 + n, j2):
            hit = _row_anchor(ft, brow, srow.get(j, []), i1 + n - 1 if i1 + n else None, i2 if i2 < ft["rows"] else None)
            if hit is None:
                return None
            ins.append((j, *hit))
    return rowmap, ins


def _table(ctx, fb, sr, at):
    """같은 열쇠로 맞은 표 한 쌍 → 작성 내용(모듈 설명 ④)."""
    ft, st = fb["table"], sr["table"]
    if F.table_full(ft) == F.table_full(st):
        return
    path = fb["path"]

    def structure(why):
        ctx.hunk("cells", "structure", why, at=at, scope=fb["scope"], path=path, base={"table": fb["id"]}, frm={"table": sr["id"]}, text=sr["text"],
                 fp=[fb["id"], "structure", F.table_full(st)])
    same = ft["rows"] == st["rows"] and ft["cols"] == st["cols"] and {(c["r"], c["c"], c["rs"], c["cs"]) for c in ft["cells"]} == {(c["r"], c["c"], c["rs"], c["cs"]) for c in st["cells"]}
    rowmap, ins = None, []
    if not same:
        got = _rowmap(ft, st) if ft.get("list") and ft["cols"] == st["cols"] else None
        if got is None:
            why = [f"행 {ft['rows']}→{st['rows']}" if ft["rows"] != st["rows"] else "", f"열 {ft['cols']}→{st['cols']}" if ft["cols"] != st["cols"] else ""]
            return structure("표의 격자가 기준본과 다름(" + (" · ".join(x for x in why if x) or "병합 칸이 달라짐") + ")" + ("" if ft.get("list") or ft["rows"] == st["rows"] else " — 이어 넣는 표가 아님"))
        rowmap, ins = got
    sat = {(c["r"], c["c"]): c for c in st["cells"]}
    fid = {c["id"]: c for c in ft["cells"]}
    pair = {}
    for c in ft["cells"]:
        x = sat.get((rowmap[c["r"]] if rowmap else c["r"], c["c"]))
        if x is None or x["cs"] != c["cs"]:
            return structure("표의 격자가 기준본과 다름(행을 맞춘 뒤에도 칸이 어긋남)")
        pair[c["id"]] = x
    diffs = defaultdict(list)
    for c in ft["cells"]:
        x = pair[c["id"]]
        odd = x["cx"] and c["cls"] != "complex"   # 기준본에서는 글만 있던 칸에 표·그림이 들어옴
        if F.norm(x["text"]) == F.norm(c["text"]) and not odd:
            continue
        cls = "complex" if odd or c["cls"] == "complex" else c["cls"]
        if cls == "input" and not F.norm(x["text"]):
            continue   # 기관이 비운 칸 — 취합본에서 지우지 않는다(§1)
        sc = c.get("scope") or fb["scope"]
        diffs[(cls, _sk(sc)) if cls == "input" else (cls,)].append((c, x, sc))

    def cells(rows):
        return [{"r": x["r"], "c": x["c"], "id": x["id"], "text": x["text"], "base": c["text"], "to": c["id"]} for c, x, _ in rows]
    for k, rows in diffs.items():
        cs, sc = cells(rows), rows[0][2]
        text = " / ".join(_short(c["text"], 40) for c in cs[:8])
        fp = [fb["id"], k[0], [[c["to"], F.norm(c["text"])] for c in cs]]
        kw = dict(at=at, path=path, base={"table": fb["id"], "ids": [c["to"] for c in cs]}, frm={"table": sr["id"], "cells": cs}, text=text, counts={"cells": len(cs)}, fp=fp)
        if k[0] == "head":
            ctx.hunk("changed", "changed", f"표 머리 칸 {len(cs)}개의 글이 바뀜", scope=fb["scope"], **kw)
        elif k[0] == "calc":
            ctx.hunk("cells", "calc", f"계산 칸 {len(cs)}개 — 기관 문서의 값을 복사하지 않음(취합본의 합계가 아니다)", scope=fb["scope"], **kw)
        elif k[0] == "complex":
            ctx.hunk("cells", "structure", f"칸 안에 표·그림이 든 칸 {len(cs)}개 — 저절로 넣지 않음", scope=fb["scope"], **kw)
        else:
            lost = next((i for i in sc.get("labels") or () if i in fid and F.norm(fid[i]["text"]) and F.norm(pair[i]["text"]) != F.norm(fid[i]["text"])), None)
            ctx.hunk("cells", "unknownPlace" if lost else "ready", f"이 칸들의 구분 라벨 칸 「{_short(fid[lost]['text'], 30)}」 이 기관 문서에서 바뀜" if lost else "",
                     scope=sc, unique="격자(행·열·병합)가 같은 표의 같은 칸" if rowmap is None else "행을 맞춘 표의 같은 칸", labels=[i for i in sc.get("labels") or () if i not in fid], **kw)
    brow = _by_row(ft)
    groups = defaultdict(list)
    for j, r, above, cols in ins:
        groups[(r, above, tuple(cols))].append(j)
    srow = _by_row(st)
    for (r, above, cols), js in groups.items():
        tmpl = [c for c in brow[r] if cols[0] <= c["c"] <= cols[1]]
        calc = {c["c"] for c in tmpl if c["cls"] == "calc"}
        sc = tmpl[0].get("scope") or fb["scope"]
        rows = []
        for j in js:
            new = srow[j]
            if not any(F.norm(c["text"]) for c in new):
                continue   # 빈 행을 늘린 것은 내용이 아니다
            rows.append({"r": j, "cells": [c["text"] for c in new], "cols": [c["c"] for c in new], "ids": [c["id"] for c in new]})
        if not rows:
            continue
        lost = next((i for i in sc.get("labels") or () if i in fid and F.norm(fid[i]["text"]) and F.norm(pair[i]["text"]) != F.norm(fid[i]["text"])), None)
        ctx.hunk("rows", "unknownPlace" if lost else "ready", f"이 행들의 구분 라벨 칸 「{_short(fid[lost]['text'], 30)}」 이 기관 문서에서 바뀜" if lost else "",
                 at=at, scope=sc, path=path, base={"table": fb["id"], "after": tmpl[0]["id"], "above": above, "cols": list(cols), "calc": sorted(calc)},
                 frm={"table": sr["id"], "rows": rows}, text=" / ".join(" | ".join(x for x in r["cells"] if x.strip()) for r in rows[:4]),
                 counts={"rows": len(rows), "cells": sum(1 for r in rows for x in r["cells"] if x.strip())},
                 unique=f"이어 넣는 표 — 닻 행 「{_short(' | '.join(c['text'] for c in tmpl if c['text'].strip()), 40)}」 {'위' if above else '뒤'}",
                 labels=[i for i in sc.get("labels") or () if i not in fid], fp=[fb["id"], tmpl[0]["id"], above, [[F.norm(x) for x in r["cells"]] for r in rows]])


def links(frame, part):
    """자리 연결(모듈 설명) — 기준본 ↔ 기관 문서. part = 기관 문서 쪽(merge_api._read 의 꼴 — blocks 만 읽는다, doc 이 있으면 그림 바이트도)."""
    ctx = _Ctx(frame, part)
    B, S = ctx.B, ctx.S
    got = []
    _anchors(B, S, 0, len(B), 0, len(S), got)
    got.sort()
    cov = {"anchors": len(got), "blocks": 0, "ratio": 0.0}
    if not got:
        return {"coverage": cov, "items": [], "reasons": ["noMatch"]}
    edges = [(-1, -1), *got, (len(B), len(S))]
    for (pb, ps), (nb, ns) in zip(edges, edges[1:]):
        _diff(ctx, pb + 1, nb, ps + 1, ns)
        if nb < len(B):
            ctx.match(nb, ns)
    for k, b in enumerate(B):
        r = ctx.matched.get(b["id"])
        if r is not None and b["kind"] == "tbl" and r["kind"] == "tbl":
            _table(ctx, b, r, k)
    for h in ctx.items:   # 자리의 구분 라벨이 기관 문서에서 안 맞았으면 그 자리를 못 믿는다(기관마다 되풀이되는 뼈대 — 라벨이 잡혀야 그 구간의 자리다)
        lost = next((i for i in h.pop("_labels") if i in ctx.fat and i not in ctx.matched), None)
        if lost and h["status"] == "ready":
            h.update(status="unknownPlace", detail=f"이 자리의 구분 라벨 「{_short(ctx.fat[lost]['text'], 40)}」 을 기관 문서에서 찾지 못함", unique="")
    ctx.items.sort(key=lambda h: h["_at"])
    for h in ctx.items:
        del h["_at"]
    cov.update(blocks=len(ctx.matched), ratio=round(len(ctx.matched) / len(B), 3) if B else 0.0)
    return {"coverage": cov, "items": ctx.items, "reasons": []}


# ---- 3방향 판정(§4-2) -------------------------------------------------------------------------------------------

class _Target:
    """지금 취합본 — 맞춤 줄(F.rows)과 자리 색인."""

    def __init__(self, frame, to):
        blocks = to.get("blocks")
        if blocks is None:
            blocks = to["doc"].blocks()
        self.rows = F.rows(blocks, frame=frame, doc=to.get("doc"))
        self.pos = {r["id"]: k for k, r in enumerate(self.rows)}
        self.raw = {b["id"]: b for b in blocks}
        self.cells = {c["id"]: (r, c) for r in self.rows if r["kind"] == "tbl" for c in r["table"]["cells"]}
        doc, self.host = to.get("doc"), {}   # 블록 id → 그 블록이 든 최상위 문단(hp:p) — 글과 표·그림이 한 문단에 묶인 곳은 그 사이에 넣을 수 없다(insert_after 는 문단 뒤에 넣는다)
        if doc is not None and hasattr(doc, "_host"):
            for r in self.rows:
                el = doc._ids.get(r["id"])
                if el is not None:
                    self.host[r["id"]] = doc._host(el)


def _expected(base, frm):
    """넣은 뒤 그 자리(경계 사이)의 열쇠 차례 — 기준본 틈에서 자리표시 줄을 빼고 넣을 자리에 기관 문서 줄을."""
    out, drop, spot = [], set(base.get("ids") or ()), base.get("spot")
    if spot is None:
        out += frm.get("keys") or ()
    for i, k in base.get("gap") or ():
        if i not in drop:
            out.append(k)
        if i == spot:
            out += frm.get("keys") or ()
    return out


def _judge_body(h, T, rec):
    base, frm = h["base"], h["from"]
    prev, nxt = base["prev"], base["next"]
    tp, tn = (T.pos.get(prev) if prev else -1), (T.pos.get(nxt) if nxt else len(T.rows))
    if tp is None or tn is None or tp >= tn:
        return "overlap", "취합본에서 이 자리의 경계 줄을 찾지 못함(지워졌거나 차례가 바뀜)"
    ids = (rec or {}).get("ids") or ()
    if ids and all(i in T.pos and tp < T.pos[i] < tn for i in ids) and rec.get("fp") == _fp_blocks([T.raw[i] for i in sorted(ids, key=T.pos.get)]):
        return "same", "이 기관 문서에서 넣은 내용이 그 자리에 그대로 있음"
    edge = [T.rows[tp]["key"] if prev else None, T.rows[tn]["key"] if nxt else None]
    gap = [[r["id"], r["key"]] for r in T.rows[tp + 1:tn] if r["key"]]
    if edge == base.get("edge") and gap == base.get("gap"):
        spot = base.get("spot")
        k = T.pos[spot] if spot else tp
        if not spot:
            n = 0
            while n < (base.get("lead") or 0) and k + 1 < tn and not T.rows[k + 1]["key"]:
                k, n = k + 1, n + 1
        if k < 0:
            return "unknownPlace", "문서 맨 앞 — 그 앞에 넣을 블록이 없음"
        if k + 1 < len(T.rows) and T.host.get(T.rows[k]["id"]) is not None and T.host.get(T.rows[k]["id"]) is T.host.get(T.rows[k + 1]["id"]):
            return "unknownPlace", "넣을 자리의 글과 그 뒤 표·그림이 한 문단에 묶여 있어 그 사이에 넣을 수 없음(끌어 넣기로)"
        h["to"] = {"prev": T.rows[k]["id"], "next": T.rows[k + 1]["id"] if k + 1 < len(T.rows) else None}
        return "ready", ""
    if edge == base.get("edge") and [k for _, k in gap] == _expected(base, frm):
        return "same", "취합본의 그 자리에 같은 내용이 이미 있음"
    was = {(i, k) for i, k in base.get("gap") or ()}
    other = next((r for r in T.rows[tp + 1:tn] if r["key"] and (r["id"], r["key"]) not in was), None)   # 새로 든 줄 · 글이 바뀐 자리표시 줄
    return "overlap", (f"취합본의 그 자리에 다른 내용 「{_short(other['text'], 60)}」" if other else "취합본의 그 자리가 기준본과 다름(줄이 지워졌거나 경계 글이 바뀜)")


def _judge_cells(h, T):
    n = Counter()
    for c in h["from"]["cells"]:
        hit = T.cells.get(c["to"])
        if hit is None or hit[0]["id"] != h["base"]["table"]:
            c["status"] = "overlap"
        else:
            now = F.norm(hit[1]["text"])
            c["status"] = "same" if now == F.norm(c["text"]) and not hit[1]["cx"] else "ready" if now == F.norm(c["base"]) and not hit[1]["cx"] else "overlap"
        n[c["status"]] += 1
    status = "ready" if n["ready"] else "overlap" if n["overlap"] else "same"
    mixed = len([k for k in n if n[k]]) > 1
    names = (("ready", "넣을 칸"), ("overlap", "겹침"), ("same", "이미 같음"))
    detail = " · ".join(f"{t} {n[k]}" for k, t in names if n[k]) if mixed else {"overlap": "취합본의 그 칸에 다른 글이 있음", "same": "취합본의 그 칸에 같은 글이 이미 있음"}.get(status, "")
    return status, detail


def _judge_rows(h, T, rec):
    base, ids = h["base"], (rec or {}).get("ids") or ()
    alive = [i for i in ids if i in T.cells and T.cells[i][0]["id"] == base["table"]]
    if ids and len(alive) == len(ids) and rec.get("fp") == _fp_texts(T.cells[i][1]["text"] for i in ids):
        return "same", "이 기관 문서에서 넣은 행이 그대로 있음"
    if alive:
        return "overlap", "이 기관 문서에서 넣은 행이 그 뒤 바뀜 — 직접 확인"
    hit = T.cells.get(base["after"])
    if hit is None or hit[0]["id"] != base["table"] or hit[1]["rs"] != 1 or hit[0]["table"]["cols"] <= base["cols"][1]:
        return "overlap", "취합본의 표에서 닻 행을 찾지 못함(표가 기준본과 달라짐)"
    h["to"] = {"prev": base["after"], "next": None}
    return "ready", ""


def judge(items, frame, to, cfg, applied=None):
    """3방향 판정(모듈 설명) → 상태·detail·to·decision 이 붙은 사본. cfg = {"orgs": [기관 열쇠…], "common": bool, "decisions": {열쇠: {value, source, …}}},
    applied = gather.json parts[part].applied({열쇠: {ids, fp, kind}}) — 지금 문서와 맞는 기록만 믿는다."""
    cfg, applied = cfg or {}, applied or {}
    orgs, common, decisions = set(cfg.get("orgs") or ()), cfg.get("common", True), cfg.get("decisions") or {}
    T, out = None, []
    for it in items:
        h = copy.deepcopy(it)
        d = decisions.get(h["key"])
        h["decision"] = dict(d) if isinstance(d, dict) and d.get("value") else None
        out.append(h)
        if h["status"] != "ready":
            continue
        sc = h["scope"]
        if not orgs:
            h.update(status="unassigned", detail="반영할 기관을 아직 정하지 않음")
        elif sc["kind"] == "unknown":
            h.update(status="unknownPlace", detail="어느 기관의 자리인지 알아내지 못한 곳")
        elif sc["kind"] == "org" and sc["org"] not in orgs:
            h.update(status="otherOrg", detail=f"{sc.get('orgName') or sc['org']} 의 자리 — 이 문서에서 반영할 기관이 아님")
        elif sc["kind"] == "common" and not common:
            h.update(status="otherOrg", detail="공통 자리 — 이 문서에서는 공통 자리를 가져오지 않음")
        else:
            T = T or _Target(frame, to)
            rec = applied.get(h["key"])
            status, detail = _judge_cells(h, T) if h["kind"] == "cells" else _judge_rows(h, T, rec) if h["kind"] == "rows" else _judge_body(h, T, rec)
            h.update(status=status, detail=detail)
        if h["status"] != "ready":
            h["unique"] = ""
    for h in out:   # 넣지 않는 것도 화면이 그 자리로 갈 수 있게 — 취합본에 있는 경계(표면 그 표)
        if h["to"]["prev"] is None and h["to"]["next"] is None and (h["base"]["prev"] or h["base"]["next"] or h["base"]["table"]):
            T = T or _Target(frame, to)
            near = [h["base"]["table"]] if h["base"]["table"] else [h["base"]["prev"], h["base"]["next"]]
            h["to"] = {"prev": near[0] if near[0] in T.pos else None, "next": near[1] if len(near) > 1 and near[1] in T.pos else None}
    return out


# ---- 넣기 계획 → 반영(§4-4 · §4-5) ------------------------------------------------------------------------------

def _dropped(doc, sid):
    """기관 문서 블록 sid 를 복사할 때 빠지는 개체 이름들(OLE·차트·구역 설정 …) — 문단은 제 표·그림(따로 복사되는 블록)을 빼고 센다."""
    el = doc._ids.get(sid)
    if el is None:
        return []
    if etree.QName(el).localname != "p":
        return [etree.QName(e).localname for e in el.iter(*DROP_ON_COPY)]
    return [etree.QName(e).localname for r in el for c in r if etree.QName(c).localname not in ("tbl", "pic") for e in c.iter(*DROP_ON_COPY)]


def _formulas(to):
    """취합본 3단계 결과의 수식 → {표 id: [{table, cell, kind, operands}]}."""
    out = {}
    for t in ((to or {}).get("tables") or {}).get("tables") or ():
        fs = [{"table": t["id"], "cell": f["cell"], "kind": f.get("kind"), "operands": list(f.get("operands") or ())} for f in t.get("formulas") or () if f.get("cell")]
        if fs:
            out[t["id"]] = fs
    return out


def plan(items, frame, to, part):
    """넣기 계획(모듈 설명) — items = judge 결과. 문서는 안 바뀐다."""
    pdoc = (part or {}).get("doc")
    if pdoc is not None:
        pdoc.blocks()   # 블록 id 는 읽을 때 붙는다
    ops, view, skipped, calc, dropped = [], [], Counter(), [], []
    written, grown = {}, set()
    known = {b["id"]: [c["id"] for c in b["table"]["cells"]] for b in frame["blocks"] if b.get("table")}   # 기준본 표의 칸 — 반영이 「먼저 넣은 행」(기준본에 없던 칸)을 가린다
    for h in items:
        base, frm = h["base"], h["from"]
        if h["status"] == "calc":
            calc += [{"table": base["table"], "cell": c["to"], "why": "partValue", "kind": None, "text": c["text"], "key": h["key"]} for c in frm["cells"]]
        value = (h.get("decision") or {}).get("value")
        if h["status"] != "ready" or value in ("skip", "check"):
            skipped[h["status"] if h["status"] != "ready" else value] += 1
            continue
        counts = dict(h["counts"])
        if h["kind"] in BODY:
            op = {"key": h["key"], "kind": h["kind"], "after": h["to"]["prev"], "src": list(frm["ids"]), "drop": list(base["ids"]),
                  "guard": {"prev": base["prev"], "next": base["next"], "ids": [i for i, _ in base.get("gap") or ()]}}
            counts["placeholders"] = len(op["drop"])
            if pdoc is not None:
                dropped += [{"key": h["key"], "src": s, "what": w} for s in op["src"] for w in _dropped(pdoc, s)]
                cv = FIT.plan(to, part, op)   # 틀 맞춤(§4-4) — 개요 깊이·레터 꼴이 취합본 틀과 다른 줄을 그 자리의 틀로. 그래프가 없으면 None(쓴 대로)
                if cv is not None:
                    op["convert"], fit = cv, FIT.view(cv)
                    counts["converted"], counts["kept"] = fit["converted"], sum(fit["kept"].values())
        elif h["kind"] == "cells":
            cs = [{"to": c["to"], "from": c["id"], "text": c["text"], "base": c["base"]} for c in frm["cells"] if c.get("status", "ready") == "ready"]
            op = {"key": h["key"], "kind": "cells", "table": base["table"], "cells": cs}
            counts["cells"] = len(cs)
            written.update((c["to"], base["table"]) for c in cs)
        else:
            op = {"key": h["key"], "kind": "rows", "table": base["table"], "after": base["after"], "above": bool(base.get("above")), "cols": list(base["cols"]),
                  "known": known.get(base["table"]) or [],
                  "rows": [[{"col": c, "text": t, "from": i} for c, t, i in zip(r["cols"], r["cells"], r["ids"]) if c not in (base.get("calc") or ())] for r in frm["rows"]]}
            grown.add(base["table"])
        ops.append(op)
        view.append({"key": h["key"], "kind": h["kind"], "scope": h["scope"], "path": h["path"], "text": h["text"], "to": h["to"], "counts": counts,
                     "decision": h.get("decision"), **({"convert": FIT.view(op["convert"])} if op.get("convert") else {})})
    touched = grown | set(written.values())
    formulas = [f for tid, fs in _formulas(to).items() if tid in touched for f in fs]
    for f in formulas:   # 반영하면 다시 계산해야 할 칸(미리 보기 — 실제 결과는 apply 의 calc)
        if f["table"] in grown:
            calc.append({"table": f["table"], "cell": f["cell"], "why": "rows", "kind": f["kind"], "text": None, "key": None})
        elif set(f["operands"]) & written.keys():
            calc.append({"table": f["table"], "cell": f["cell"], "why": "operands", "kind": f["kind"], "text": None, "key": None})
    return {"todo": len(ops), "ops": ops, "items": view, "skipped": dict(skipped), "calc": calc, "dropped": dropped, "formulas": formulas}


def _fit(to_doc, part_doc, to, frm):
    """글을 쓴 칸에 기관 문서 칸의 장평·자간·글자 크기를 얹는다(덤 — 못 찾으면 글만)."""
    try:
        return bool(frm) and to_doc.fit_chars(to, part_doc, frm)
    except (KeyError, ValueError, AttributeError):
        return False


def _apply_rows(to_doc, op, out):
    """행 넣기 하나 → 새 칸 id 들 | None. 닻 행 뒤 = 이미 다른 기관 문서가 넣은 행들(기준본에 없던 행 — 닻 행과 같은 모양)의 뒤. 위에 넣는 닻이면 닻 행 바로 위(먼저 넣은 행들의 아래)."""
    c0, c1 = op["cols"]
    new, fit, base_ids = [], [], set(op.get("known") or ())
    for row in op["rows"]:
        tb = to_doc.table_block(op["table"])
        a = next((c for c in (tb or {}).get("cells") or () if c["id"] == op["after"]), None)
        if a is None:
            out["skipped"].append({"key": op["key"], "why": "shape", "detail": "행을 늘릴 닻 행이 지금 표에 없음"})
            return None
        by = defaultdict(list)
        for c in tb["cells"]:
            if c0 <= c["col"] <= c1:
                by[c["row"]].append(c)
        r = a["row"]
        if not op["above"]:   # 먼저 넣은 행들(기준본에 없던 칸만 있는 같은 모양의 행)을 지나 그 뒤에
            lay = sorted((c["col"], c["colSpan"]) for c in by[r])
            while by.get(r + 1) and all(c["id"] not in base_ids and c["rowSpan"] == 1 for c in by[r + 1]) and sorted((c["col"], c["colSpan"]) for c in by[r + 1]) == lay:
                r += 1
        try:
            m = to_doc.clone_rows(op["table"], r, r, [c0, c1], keep_text=False, above=op["above"])["map"]
        except ValueError as e:
            out["skipped"].append({"key": op["key"], "why": "shape", "detail": str(e)})
            return None
        at = {c["col"]: m[c["id"]] for c in by[r] if c["id"] in m}
        for x in row:
            if x["col"] in at and x["text"].strip():
                to_doc.set_text(at[x["col"]], x["text"])
                out["written"].add(at[x["col"]])
                fit.append((at[x["col"]], x.get("from")))
        new += [at[k] for k in sorted(at)]
    out["fit"] += fit
    return new


def _number(text):
    """칸 글 → ("num", 값, 소수 자리) | ("blank",) | ("text",) — 단위·기호가 붙은 수는 다시 쓸 꼴을 몰라 글로 본다."""
    t = (text or "").strip()
    p = HC.parse_num(t)
    if not t or p.get("placeholder") or p.get("dash"):
        return ("blank",)
    if p.get("num") is None or not _PLAIN_NUM.match(t):
        return ("text",)
    return ("num", p["num"], p.get("dec") or 0)


def _recalc(to_doc, formulas, written, grown):
    """계산 칸(§4-5) — 쓴 칸을 피연산자로 둔 수식 칸: 단순 합(피연산자가 모두 수이거나 빈 칸이고 수가 하나는 있음)은 다시 계산해 넣고, 그 밖은 「다시 계산 필요」.
    행을 늘린 표의 수식 칸은 모두 「다시 계산 필요」(합의 범위가 달라졌을 수 있다). → [{table, cell, kind, action: recalculated|needed, was, now, note}]"""
    texts, out, dirty, stale, done = {}, [], set(written), set(), set()

    def text(tid, cid):
        if tid not in texts:
            texts[tid] = {c["id"]: c.get("text") or "" for c in (to_doc.table_block(tid) or {}).get("cells") or ()}
        return texts[tid].get(cid)

    def need(f, note):
        stale.add(f["cell"])
        done.add(f["cell"])
        out.append({"table": f["table"], "cell": f["cell"], "kind": f["kind"], "action": "needed", "was": text(f["table"], f["cell"]), "now": None, "note": note})
    for f in formulas:
        if f["table"] in grown and text(f["table"], f["cell"]) is not None:
            need(f, "행이 늘어남 — 합의 범위를 확인")
    for _ in range(PASSES):
        moved = False
        for f in formulas:
            ops = set(f["operands"])
            if f["cell"] in done or not ops & (dirty | stale) or text(f["table"], f["cell"]) is None:
                continue
            moved = True
            vals = [_number(text(f["table"], o)) for o in f["operands"]]
            was = text(f["table"], f["cell"])
            if f["kind"] != "sum":
                need(f, "합이 아닌 식(비율 등)")
            elif ops & stale:
                need(f, "피연산자에 다시 계산해야 할 칸이 있음")
            elif any(v[0] == "text" for v in vals) or not any(v[0] == "num" for v in vals) or _number(was)[0] == "text":
                need(f, "수가 아닌 글이 있어 합을 내지 못함")
            else:
                total, dec = sum(v[1] for v in vals if v[0] == "num"), max(v[2] for v in vals if v[0] == "num")
                if total < 0:
                    need(f, "음수 — 적는 꼴을 몰라 넣지 않음")
                    continue
                plain = any(v[0] == "num" and v[1] >= 1000 and "," not in (text(f["table"], o) or "") for v, o in zip(vals, f["operands"]))   # 쉼표 없이 적은 표면 합도 쉼표 없이
                now = f"{total:.{dec}f}" if plain else f"{total:,.{dec}f}"
                done.add(f["cell"])
                if F.norm(now) != F.norm(was):
                    to_doc.set_text(f["cell"], now)
                    texts[f["table"]][f["cell"]] = now
                    dirty.add(f["cell"])
                    out.append({"table": f["table"], "cell": f["cell"], "kind": f["kind"], "action": "recalculated", "was": was, "now": now, "note": "피연산자 칸의 합"})
        if not moved:
            break
    return out


def apply(to_doc, part_doc, plan):
    """계획을 취합본에 반영(모듈 설명). 넣기 전에 자리를 다시 본다 — 계획 뒤 자리가 달라졌으면(경계·틈의 블록이 없거나 차례가 다름 · 칸 글이 바뀜) 그 작성 내용은 건너뛰고 skipped 에 싣는다."""
    part_doc.blocks()
    top = [b for b in to_doc.blocks() if not b.get("captionOf")]
    order = [b["id"] for b in top if b.get("type") != "paragraph" or F.para_key(b.get("text"))]
    pos = {i: k for k, i in enumerate(order)}
    out = {"skipped": [], "fit": [], "written": set()}
    done, counts, grown = {}, Counter(), set()
    body = []
    for op in plan["ops"]:   # 본문 자리는 고치기 전의 문서로 한꺼번에 확인(틈끼리 안 겹친다)
        if op["kind"] not in BODY:
            continue
        g = op["guard"]
        a, b = (pos.get(g["prev"]) if g["prev"] else -1), (pos.get(g["next"]) if g["next"] else len(order))
        if a is None or b is None or order[a + 1:b] != g["ids"] or op["after"] not in to_doc._ids or any(s not in part_doc._ids for s in op["src"]):
            out["skipped"].append({"key": op["key"], "why": "moved", "detail": "계획 뒤 그 자리가 달라짐 — 다시 계획"})
        else:
            body.append(op)
    for op in plan["ops"]:
        if op["kind"] != "cells":
            continue
        now = {c["id"]: c.get("text") or "" for c in (to_doc.table_block(op["table"]) or {}).get("cells") or ()}
        ids = []
        for c in op["cells"]:
            cur = now.get(c["to"])
            if cur is None or F.norm(cur) not in (F.norm(c["base"]), F.norm(c["text"])):
                out["skipped"].append({"key": op["key"], "to": c["to"], "why": "occupied", "detail": "계획 뒤 그 칸의 글이 바뀜"})
                continue
            if F.norm(cur) != F.norm(c["text"]):
                try:
                    to_doc.set_text(c["to"], c["text"])
                except ValueError as e:
                    out["skipped"].append({"key": op["key"], "to": c["to"], "why": "shape", "detail": str(e)})
                    continue
                out["written"].add(c["to"])
                out["fit"].append((c["to"], c.get("from")))
                counts["cells"] += 1
            ids.append(c["to"])
        if ids:
            done[op["key"]] = {"ids": ids, "fp": _sha([[c["to"], F.norm(c["text"])] for c in op["cells"] if c["to"] in ids]), "kind": "cells"}
    for op in plan["ops"]:
        if op["kind"] != "rows":
            continue
        new = _apply_rows(to_doc, op, out)
        if new:
            grown.add(op["table"])
            counts["rows"] += len(op["rows"])
            done[op["key"]] = {"ids": new, "fp": None, "kind": "rows"}
    counts["shaped"] = sum(_fit(to_doc, part_doc, to, frm) for to, frm in out["fit"])   # 모양은 행을 다 늘린 뒤에 — 늘리는 행은 앞 행을 본뜬다(merge_tables.apply 와 같은 까닭)
    for op in body:
        new = to_doc.insert_after(op["after"], [{"kind": "copy", "srcId": s} for s in op["src"]], src=part_doc)
        fit = FIT.apply(to_doc, op, new)   # 틀 맞춤 — 자리표시 줄을 지우기 전에(본보기가 그 줄일 수 있다)
        if fit:
            counts["converted"] += len(fit["rows"])
            counts["kept"] += sum(fit["kept"].values())
        for pid in op["drop"]:
            try:
                to_doc.delete_blocks(pid, pid)
                counts["placeholders"] += 1
            except (KeyError, ValueError):
                pass   # 구역 설정이 든 문단 등 — 자리표시 줄을 둔 채로
        counts["fitted"] += sum(to_doc.fit_image(i) for i in new)   # 넣은 그림이 본문 폭보다 넓으면 그 폭으로
        counts["blocks"] += len(new)
        done[op["key"]] = {"ids": new, "fp": None, "kind": op["kind"], **({"convert": fit} if fit else {})}   # convert = 넣은 줄의 원래 꼴 ↔ 맞춘 자리(나중에 다른 서식으로 바꿀 근거)
    calc = _recalc(to_doc, plan.get("formulas") or (), out["written"], grown)
    counts["recalculated"] = sum(c["action"] == "recalculated" for c in calc)
    idx, cell = {}, {}
    for b in to_doc.blocks():   # 넣은 결과의 지문(§4-2 — 다음 판정이 넣은 기록을 이것으로 확인한다)
        idx[b["id"]] = b
        if b.get("type") == "table":
            cell.update((c["id"], c.get("text") or "") for c in b.get("cells") or ())
    for key, rec in done.items():
        if rec["kind"] in BODY:
            got = [idx[i] for i in rec["ids"] if i in idx]
            rec["fp"] = _fp_blocks(got)
            c = Counter(b.get("type") for b in got if b.get("type") != "paragraph" or F.para_key(b.get("text")))
            counts.update(paragraphs=c["paragraph"], tables=c["table"], pictures=c["image"])   # Counter.update 는 더한다
        elif rec["kind"] == "rows":
            rec["fp"] = _fp_texts(cell.get(i, "") for i in rec["ids"])
    counts["hunks"], counts["skipped"] = len(done), len(out["skipped"])
    keys = ("hunks", "blocks", "paragraphs", "tables", "pictures", "placeholders", "cells", "rows", "shaped", "fitted", "converted", "kept", "recalculated", "skipped")
    return {"applied": done, "counts": {k: int(counts[k]) for k in keys}, "calc": calc, "dropped": list(plan.get("dropped") or ()), "skipped": out["skipped"]}
