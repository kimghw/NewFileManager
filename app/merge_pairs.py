"""병합 — 구분 기준 확인 + 자리 연결(spec_병합 ② §0-1 ①②③, §3·§4·§5): 두 문서의 자리 묶음을 잇는다. 스크립트만 — 문서를 고치지 않고 LLM 도 부르지 않는다.

- `values_diff(frm, to)` = 두 문서의 구분 값이 다른 곳(단계·차년도 수 · 기관 — **이름으로** · 사업기간 · 세부과제. 당해 차년도는 안 견줌 — 목적 문서 것을 쓴다).
- `summarize(blocks, graph, tables, values)` = 문서 하나 → 묶음 요약 [{key, dim, kind, label, path, table{id, sig}, inner, ctx{year, org}, items[{value, id, text, ident}]}].
  path = 소속(그 묶음을 품은 절 제목 — 번호·값 낱말 뗌), label = 라벨 꼴, table.sig = 그 표(띠)의 머리 칸 꼴, inner = 문단 묶음 첫 항목 안 소제목(글 그대로 — 넣을 자리 anchor 로 쓴다),
  ctx = 맥락(그 묶음이 통째로 든 다른 묶음의 항목 — year 는 전체 차례 차년도 수, org 는 기관 이름. 목적 문서의 「다음 연도」·「해당연도」 절은 당해 차년도에서 셈).
  ident = 문서와 무관한 항목 값(기관 = 이름 · 차년도 = 전체 차례 수) — 「공동1」 이 문서마다 다른 기관일 수 있어 글이 아니라 이것으로 맞춘다.
- `pair(to_groups, from_groups, fixed=None)` = 묶음 짝 제안 → {"groups": [...], "counts": {...}}(§8 꼴). 목적 묶음마다 원본 후보 = 같은 구분 갈래 · 같은 종류 갈래 · 맥락이 어긋나지 않는 것.
  점수 = 표 묶음은 표 머리 + 소속(+ 라벨), 문단 묶음은 소속 + 라벨 + 안쪽 소제목. 1등이 문턱을 넘고 2등과 벌어지면 paired, 아니면 ambiguous(확인 필요 — 임의로 고르지 않는다), 후보가 없으면 toOnly.
  fixed = {목적 key: {"from": 원본 key | None, "source": llm|saved|user, "anchor", "reason"}} — 스크립트 점수보다 먼저(merge_llm.check · merge_saved.fixed_from · 사람 고침).
  짝이 된 묶음 안에서 ident 가 같은 항목끼리 항목 짝(없으면 noSource)."""
import math
import re
from collections import Counter

from app.division_profiles import rnd
from app.division_profiles.rnd import core

PAIR_MIN, PAIR_GAP, CAND_MIN, CANDS_MAX = 0.45, 0.10, 0.20, 5   # ponytail: 실제 쌍 하나로 잰 문턱 — 서식 쌍이 늘면 정답지로 다시 잰다
PATH_MAX, TEXT_MAX, INNER_MAX, SIG_MAX = 6, 60, 12, 300
YEARLY = (core.YEAR, "stageYear")

_WS = re.compile(r"\s+")
_NOTE = re.compile(r"\s*[※\n].*$", re.S)
_DIGITS = re.compile(r"\d+")
_LEAD = re.compile(r"^(?:[\s\-.·()（）\[\]<>〈〉①-⑳□■ㅇ○◦▪※~,:]|[oO가-하](?=[.)\s]))+")
_NEXT, _THIS = re.compile(r"다음\s*연도|차기\s*연도"), re.compile(r"해당\s*연도|당해\s*연도")
_CORP = re.compile(r"㈜|\(주\)|（주）|주식회사|\s+")


def _ws(text):
    return _WS.sub(" ", str(text or "")).strip()


def org_key(name):
    """기관 이름 → 견줄 글(㈜·(주)·빈칸 뗌)."""
    return _CORP.sub("", str(name or "")).strip()


def _orgs(values):
    """[(자리 글, 이름)] — 주관 → 공동 차례."""
    return [("주관" if k == 0 else f"공동{k}", core.org_name(values, k)) for k in range(len(values["orgs"]["joint"]) + 1)]


def values_diff(frm, to):
    """두 문서의 구분 값이 다른 곳 → [{"what": stages|orgs|period|subs, "from", "to"}] — 빈 목록 = 같음. 기관은 차례가 아니라 **이름의 모음**으로 견준다(§0-1 ①)."""
    frm, to = core.norm_values(frm), core.norm_values(to)
    out = []
    if list(frm["stages"]) != list(to["stages"]):
        out.append({"what": "stages", "from": list(frm["stages"]), "to": list(to["stages"])})
    names = [sorted(org_key(n) for _, n in _orgs(v)) for v in (frm, to)]
    if names[0] != names[1] or org_key(frm["orgs"]["lead"]) != org_key(to["orgs"]["lead"]):
        out.append({"what": "orgs", "from": [n for _, n in _orgs(frm)], "to": [n for _, n in _orgs(to)]})
    for what in ("period", "subs"):
        if (frm.get(what) or None) != (to.get(what) or None):
            out.append({"what": what, "from": frm.get(what), "to": to.get(what)})
    return out


def _shape(text, names=()):
    """글 → 꼴: 작성요령 꼬리(※ 뒤)·기관 이름·숫자·앞머리 번호/글머리를 뗀 글."""
    s = _ws(_NOTE.sub("", str(text or "")) or text)
    for n in names:
        if n:
            s = s.replace(n, "")
    return _ws(_LEAD.sub("", _DIGITS.sub("", s)))[:TEXT_MAX]


def _grams(text):
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", text)
    return Counter(s[i:i + 2] for i in range(len(s) - 1)) if len(s) > 1 else Counter({s: 1} if s else {})


def _cos(a, b, idf=None):
    """2글자 묶음 코사인(idf = 흔한 묶음의 무게를 낮춤 — 「연구개발」 은 어디에나 있다)."""
    if not a or not b:
        return 0.0
    w = (lambda k: idf.get(k, 1.0)) if idf else (lambda k: 1.0)
    dot = sum(v * b[k] * w(k) ** 2 for k, v in a.items() if k in b)
    na, nb = (math.sqrt(sum((v * w(k)) ** 2 for k, v in x.items())) for x in (a, b))
    return dot / (na * nb) if na and nb else 0.0


def _jac(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def _ident(dim, value, text, values, base=0):
    """항목 값 → 문서와 무관한 값. 기관 = ("org", 이름 꼴) — 차례 없는 「공동」·열 묶음은 라벨 글에 든 이름으로, 차년도 = ("year", 전체 차례 수), 단계 = ("stage", n)."""
    if dim == core.ORG:
        k = value[1] if isinstance(value, tuple) and value[0] in ("lead", "joint") else None
        if isinstance(k, int) and k <= len(values["orgs"]["joint"]):
            return ("org", org_key(core.org_name(values, k)))
        t = org_key(text)
        hit = [org_key(n) for _, n in _orgs(values) if org_key(n) and org_key(n) in t]
        return ("org", max(hit, key=len)) if hit else None
    if dim == core.YEAR and isinstance(value, int):
        return ("year", value + base)
    if dim == "stageYear" and isinstance(value, tuple) and all(isinstance(x, int) for x in value):
        return ("year", sum(values["stages"][:value[0] - 1]) + value[1])
    if dim == core.STAGE and isinstance(value, int):
        return ("stage", value)
    return ("raw", str(value))


def _node_path(nodes, nid, names):
    """그래프에서 nid 의 조상 제목 꼴(바깥 → 안, nid 자신은 뺌)."""
    out, seen = [], set()
    n = nodes.get((nodes.get(nid) or {}).get("parent"))
    while n is not None and n["id"] not in seen and len(out) < 12:
        seen.add(n["id"])
        if s := _shape(n.get("text") or n.get("letter"), names):
            out.append(s)
        n = nodes.get(n.get("parent"))
    return out[::-1]


def _inner(nodes, item):
    """문단 묶음 항목 안 소제목 — 「레터 글」 그대로(넣을 자리 anchor), 문서 순."""
    scope, out = item.get("scope") or (), []
    for n in nodes.values():
        if n["id"] in scope and n["id"] != item.get("label") and n.get("role") in ("heading", "subtitle", "label") and not n.get("blank"):
            out.append((n.get("n", 0), _ws(f"{n.get('letter') or ''} {n.get('text') or ''}")[:TEXT_MAX]))
    return [t for _, t in sorted(out)][:INNER_MAX]


def summarize(blocks, graph, tables, values):
    """문서 하나 → 묶음 요약(모듈 설명). values = 그 문서의 구분 값(정리한 꼴)."""
    values = core.norm_values(values)
    groups = core.find(blocks, rnd.levels_of(blocks), values)
    nodes = {n["id"]: n for n in (graph or {}).get("nodes") or ()}
    tabs = {t["id"]: t for t in (tables or {}).get("tables") or ()}
    names = sorted({n for _, n in _orgs(values) if n}, key=len, reverse=True)
    cur = values.get("current") or 1
    out = []
    for g in groups:
        if g.get("orgYear") == "year":   # 기관 행 묶음 안의 연도 행(품목표 — 이어 넣는 자리): 표는 기관 행 묶음이 잇고, 기관 × 연도 행은 표 안 연결(§0-1 ③)에서 맞춘다
            continue
        first = g["items"][0]
        kind = "list" if g.get("list") else g["kind"]
        base = g.get("yearBase") or 0
        s = {"key": g["key"], "dim": g["dim"], "kind": kind, "label": _shape(first.get("labelText"), names), "ctx": {"year": None, "org": None},
             "items": [{"value": rnd.value_text(g["dim"], it["value"]), "id": it.get("label"), "text": _ws(it.get("labelText"))[:TEXT_MAX],
                        "ident": _ident(g["dim"], it["value"], it.get("labelText"), values, base)} for it in g["items"]]}
        t = tabs.get(g.get("table"))
        if t is not None:
            owner = t.get("owner") or {}
            raw = [*(owner.get("path") or ()), owner.get("text")]
            cell = next((c for c in t["cells"] if c["id"] in (first.get("label"), g.get("list"), g["key"])), None)
            sub = (cell or {}).get("sub")
            heads = [_shape(c["text"], names) for c in t["cells"] if c.get("role") in ("colhead", "rowhead", "corner") and (sub is None or c.get("sub") == sub)]
            s["table"] = {"id": t["id"], "sig": sorted({h for h in heads if h})[:SIG_MAX]}
        else:
            raw = _node_path(nodes, first.get("label"), ())
            s["inner"] = _inner(nodes, first)
        s["path"] = [p for p in (_shape(x, names) for x in raw) if p][-PATH_MAX:]
        s["_org"] = _path_org(raw if t is not None else _node_titles(nodes, first.get("label")), names)
        s["blank"] = _blank(t, g)   # 내용이 하나도 없는 묶음(빈 양식 그대로) — 같은 꼴 후보가 여럿일 때 내용이 든 쪽을 고르는 데만 쓴다(pair)
        text = " ".join(_ws(x) for x in raw)
        s["_hint"] = cur + 1 if _NEXT.search(text) else cur if _THIS.search(text) or g.get("thisYear") else None
        s["_anchors"] = [a for a in (g.get("table"), g.get("container"), first.get("label")) if a]
        s["_scopes"] = [(it.get("scope") or (), x["ident"]) for it, x in zip(g["items"], s["items"])]
        out.append(s)
    for s in out:   # 맥락 — 이 묶음이 통째로 든 다른 묶음의 항목(같은 표의 묶음끼리는 아님)
        for h in out:
            if h is s or (s.get("table") and h.get("table") and s["table"]["id"] == h["table"]["id"]):
                continue
            hit = next((ident for scope, ident in h["_scopes"] if ident and any(a in scope for a in s["_anchors"])), None)
            if hit and hit[0] in ("year", "org") and s["ctx"][hit[0]] is None:
                s["ctx"][hit[0]] = hit[1]
        if s["ctx"]["year"] is None:
            s["ctx"]["year"] = s["_hint"]
        if s["ctx"]["org"] is None and s["dim"] != core.ORG:   # 어느 기관 항목에도 안 든 묶음 — 그 묶음을 품은 절 제목에 기관 이름이 적혀 있으면 그 기관의 자리다(§4 「기관·차년도 가리기」). 기관을 늘어놓는 묶음은 한 기관의 것이 아니다
            s["ctx"]["org"] = s["_org"]
    for s in out:
        for k in ("_hint", "_anchors", "_scopes", "_org"):
            del s[k]
    return out


def _node_titles(nodes, nid):
    """그래프에서 nid 의 조상 제목(바깥 → 안, 「레터 글」 그대로 — 번호를 안 뗀다: _path_org 가 절 제목을 가린다)."""
    out, seen = [], set()
    n = nodes.get((nodes.get(nid) or {}).get("parent"))
    while n is not None and n["id"] not in seen and len(out) < 12:
        seen.add(n["id"])
        out.append(_ws(f"{n.get('letter') or ''} {n.get('text') or ''}"))
        n = nodes.get(n.get("parent"))
    return out[::-1]


def _path_org(raw, names):
    """소속 제목들(바깥 → 안, 글 그대로) 가운데 **기관 절 제목**(「[공동연구개발기관1 : 유엔젤]」 — 주관·공동연구개발기관 낱말이 있는 줄)에 적힌 구분 값의 기관 이름(견줄 꼴) | None.
    가장 안쪽 제목부터 본다. 작성자가 번호를 틀리게 적었거나(기관마다 「공동연구개발기관1」) 엔진이 그 절을 기관 항목으로 못 읽은 문서에서도 그 절의 표·문단이 어느 기관 것인지 안다."""
    keys = [k for k in (org_key(n) for n in names) if k]
    for x in reversed([str(x or "") for x in raw]):
        if core.SECTION.match(x) or _CHAPTER.match(x):
            return None   # 절 제목(「8-3.」·「8.」)이 먼저 나옴 — 그 바깥의 기관 절 제목은 이 묶음의 것이 아니다(그래프가 절을 앞 기관 절 아래에 건 문서가 있다)
        if core.ORG_RE.search(x):
            hit = [k for k in keys if k in org_key(x)]
            if hit:
                return max(hit, key=len)
    return None


_CHAPTER = re.compile(r"^\s*\d+\.\s")   # 장 제목 「8. 연구개발비 사용에 관한 계획」
_CONTENT = re.compile(r"[1-9A-Za-z가-힣]")


def _blank(t, g):
    """묶음에 내용이 하나도 없나 — 표 묶음: 그 표의 필드 칸(3단계 role field)에 글자·0 아닌 숫자가 하나도 없음(「0,000,000」·「-」 자리표시만) · 문단 묶음: 항목마다 라벨 뒤 글이 없음.
    3단계 결과에 없는 표(분석 뒤 생긴 표)는 모른다(None)."""
    if g.get("table") or g["kind"] != "paragraph":
        if t is None:
            return None
        return not any(_CONTENT.search(c.get("text") or "") for c in t["cells"] if c.get("role") == "field")
    return not any(_CONTENT.search(str(x or "")) for it in g["items"] for x in it.get("content") or ())


def family(kind):
    return "paragraph" if kind == "paragraph" else "table"


def _dim(dim):
    return "year" if dim in YEARLY else dim


def _idf(groups):
    df, n = Counter(), 0
    for s in groups:
        n += 1
        df.update(set(_grams(" ".join(s.get("path") or ()))))
    return {k: math.log(1 + n / v) for k, v in df.items()}


def score(t, f, idf=None):
    """목적 묶음 t ↔ 원본 묶음 f 의 닮음(0~1) | None(후보가 아님 — 구분·종류 갈래나 맥락이 어긋남)."""
    if _dim(t["dim"]) != _dim(f["dim"]) or family(t["kind"]) != family(f["kind"]):
        return None
    ct, cf = t.get("ctx") or {}, f.get("ctx") or {}
    for k in ("year", "org"):
        if ct.get(k) is not None and cf.get(k) is not None and ct[k] != cf[k]:
            return None
    pt, pf = " ".join(t.get("path") or ()), " ".join(f.get("path") or ())
    path = 1.0 if not pt and not pf else _cos(_grams(pt), _grams(pf), idf)   # 둘 다 소속이 없음(표지 표) = 같은 자리
    label = _cos(_grams(t.get("label") or ""), _grams(f.get("label") or ""))
    if family(t["kind"]) == "table":
        sig = _jac((t.get("table") or {}).get("sig") or (), (f.get("table") or {}).get("sig") or ())
        v = 0.55 * sig + 0.30 * path + 0.10 * label + (0.05 if t["kind"] == f["kind"] else 0.0)
    else:   # 목적 자리의 안쪽 소제목은 거기에 무엇을 적는지 말해 준다(「- (추진 내용)」 ↔ 「② 개발 내용 및 범위」) — 목적의 소속과 한데 놓고 원본의 소속에 견준다
        inner = _cos(_grams(" ".join([pt, *(_shape(x) for x in t.get("inner") or ())])), _grams(pf), idf)   # 원본의 안쪽 소제목은 쓴 내용이라 안 쓴다
        v = 0.45 * path + 0.20 * label + 0.35 * inner
    for k in ("year", "org"):   # 한쪽만 맥락이 있음(전 차년도 자리 ↔ 한 차년도의 절 · 기관 절 안의 표 ↔ 총괄표): 가능은 하나 덜 그럴듯
        if (ct.get(k) is None) != (cf.get(k) is None) and not (k == "year" and cf.get(k) is None):
            v *= 0.8
    return round(v, 3)


def _side(s):
    out = {"key": s["key"], "path": s.get("path") or [], "label": s.get("label") or ""}
    if s.get("table"):
        out["table"] = s["table"]["id"]
    return out


def _items(t, f):
    by = {}
    for it in (f or {}).get("items") or ():
        if it.get("ident"):
            by.setdefault(it["ident"], it)
    out = []
    for it in t["items"]:
        src = by.get(it.get("ident")) if f else None
        out.append({"value": it["value"], "to": {"id": it["id"], "text": it["text"]}, "from": {"id": src["id"], "text": src["text"], "value": src["value"]} if src else None,
                    "status": "paired" if src else "noSource" if f else "unpaired"})
    return out


def pair(to_groups, from_groups, fixed=None):
    """묶음 짝 제안(모듈 설명) → {"groups", "counts"}. groups 차례 = 목적 문서 차례, 끝에 원본에만 있는 묶음(fromOnly)."""
    fixed = fixed or {}
    idf = _idf([*to_groups, *from_groups])
    by_from = {f["key"]: f for f in from_groups}
    groups, used = [], set()
    for t in to_groups:
        cands = sorted(((v, f) for f in from_groups if (v := score(t, f, idf)) is not None and v >= CAND_MIN), key=lambda x: -x[0])
        fx = fixed.get(t["key"])
        src, source, reason, anchor = None, "script", "", None
        if fx is not None and (fx.get("from") is None or fx["from"] in by_from):
            src, source, reason, anchor = by_from.get(fx.get("from")), fx.get("source") or "user", fx.get("reason") or "", fx.get("anchor")
            status = "paired" if src else "toOnly"
        elif not cands:
            status = "toOnly"
        elif cands[0][0] >= PAIR_MIN and (len(cands) == 1 or cands[0][0] - cands[1][0] >= PAIR_GAP):
            status, src = "paired", cands[0][1]
        elif len(full := [f for v, f in cands if v >= PAIR_MIN and cands[0][0] - v < PAIR_GAP and f.get("blank") is not True]) == 1 \
                and any(f.get("blank") is True for v, f in cands if cands[0][0] - v < PAIR_GAP):
            # 같은 꼴 후보가 여럿인데 내용이 든 것은 하나뿐(나머지는 빈 양식 그대로 — 반영이 본뜬 빈 절 등): 빈 쪽에서는 가져올 것이 없으므로 임의로 고르는 것이 아니다
            status, src, reason = "paired", full[0], "같은 꼴 후보 가운데 내용이 든 것은 하나"
        else:
            status, reason = "ambiguous", "후보가 여럿이거나 닮음이 낮음"
        if src:
            used.add(src["key"])
        groups.append({"id": t["key"], "dim": t["dim"], "dimName": rnd.DIM_NAME.get(t["dim"], t["dim"]), "kind": t["kind"], "status": status, "source": source, "reason": reason,
                       "anchor": anchor, "ctx": t.get("ctx"), "to": _side(t), "from": _side(src) if src else None,
                       "candidates": [{**_side(f), "score": v} for v, f in cands[:CANDS_MAX]], "items": _items(t, src)})
    for f in from_groups:
        if f["key"] not in used:
            groups.append({"id": "from:" + f["key"], "dim": f["dim"], "dimName": rnd.DIM_NAME.get(f["dim"], f["dim"]), "kind": f["kind"], "status": "fromOnly", "source": "script",
                           "reason": "", "anchor": None, "ctx": f.get("ctx"), "to": None, "from": _side(f), "candidates": [], "items": []})
    counts = Counter(g["status"] for g in groups)
    return {"groups": groups, "counts": {k: counts.get(k, 0) for k in ("paired", "ambiguous", "toOnly", "fromOnly")}}
