"""넘친 줄의 템플릿 등록(spec_병합 ② §5-12 「넣은 줄의 템플릿 소속」 — 2026-11-23 사용자 "매핑해서 내용을 반영한 경우 그쪽 템플릿 이나 서식을 갖어오고, 만약 매칭되거나 그 자리(목적문서)에
템플릿이 있다면 그걸로 변경하면 된느데 왜 새서식이라고 나오지? 원본문서가 이미 템플릿/서식이 정리되어 있기 떄문에 그걸 복사해서 쓰던지 해야 하는데" · astra 협의 2회).

「내용 반영」 의 템플릿 변환(`merge_convert`)은 목적 템플릿이 받을 레벨이 있는 줄만 그 템플릿 서식으로 바꾸고, 넣을 자리가 그 템플릿의 마지막 레벨이면(연차보고서 「- (추진 내용)」) 그 아래 줄은
넘친 줄(tooDeep)로 **원본 모양 그대로** 둔다(§5-5 기본 — 원본은 이미 정리된 서식). 그런데 목적 문서의 오버레이에는 그 줄이 하나도 들지 않아(실제 작업 0/254) 뼈대 유지가 「새 서식」 으로 알렸다.
이 모듈은 그 넘친 줄을 **같은 편집 안에서** 목적 오버레이에 등록한다 — 서식은 안 바꾸고(원본에서 정리된 서식 그대로) 소속만:

- 넣을 자리 줄(anchor)의 **지금 오버레이** 템플릿 A · 레벨에서 A 의 끝(K)을 넘는 레벨 K+j 를, A 의 (K) 에 매달린 **종속 템플릿** 하나(id `var_id(A, K+1, sfx)` · 표기 「T{A}L{K+1}{a…}」 ·
  base K · 사슬 = A 의 사슬 K 까지 + 원본 꼬리의 레터 키 · variant {of A, level K+1, sfx, by "merge"})로. 같은 A · 같은 꼬리를 다시 넣으면 그 템플릿에 더한다(종속 중복 0).
- **등록 조건**(원본에서 검증): 원본 줄이 원본의 **지금 오버레이** 줄이고, 원본 슬롯 대표와 레터 계열 · 비교 값(`outline_match.same`)이 같다 · 넣은 줄의 첫머리에 그 레터가 있다 ·
  부모(함께 넣은 줄)도 등록됐거나 넣을 자리 줄이다. 아니면 등록 안 하고 까닭을 센다(`left`).
- 슬롯 K+j 의 대표 = 그 레벨에 등록된 줄 가운데 **원본 슬롯 대표와 같은 첫 줄** — 동결 모양은 목적 문서의 그 줄(`outline_match.rep_shape`). 이미 대표가 있는 슬롯은 그대로.
- 사람이 넘친 처리를 「본보기로 맞춤」 · 「레터만」 으로 고른 줄(바꾼 줄 — `merge_convert.apply` 의 ids)은 등록 안 함(그 줄은 사람이 고른 서식). 「덮은 템플릿 그대로」 를 고른 줄은 등록(서식 그대로 · 소속만).
- 오버레이는 편집의 실행 취소 묶음에 든다 — 반영을 되돌리면 등록도 돌아간다. 2단계를 다시 돌리면(넣은 뒤 정리 포함) 그래프가 소속을 다시 정한다(떼기 기록 `splits` 를 남기지 않는다 — carry 가 다시 걸지 않게).
- 같은 이름 자리 · 빈 라벨 아래 복사 · 통째 표의 넘친 줄은 아직 등록하지 않는다(④)."""
import copy

from app import outline_edit as OE
from app import outline_match as OM

BY = "merge"


def _level_map(ov, anchor_id, plan_summary):
    """넣을 자리 줄 → (A 템플릿 id, 오버레이의 K, 그래프 레벨 → 오버레이 레벨로 더할 값) | None(자리 줄이 오버레이에 없음 · 넘친 사례 없음)."""
    x = (ov.get("lines") or {}).get(anchor_id)
    s = plan_summary or {}
    if not x or not s.get("over") or not s.get("anchor"):
        return None
    shift = int(x["level"]) - int(s["anchor"][1])   # 오버레이 레벨 − 그래프 레벨(표 제목 레벨을 넣은 템플릿이면 다르다 — outline_edit.lift_depth)
    return str(x["tpl"]), int(s["over"]["to"][1]) + shift, shift


def _verified(from_doc, from_ov, src):
    """원본 줄 src 가 원본 오버레이 슬롯의 줄이고 그 슬롯 대표와 같은 서식인가 → (슬롯 레터 키, 슬롯 레터, 원본 대표와 같은가) | None."""
    x = (from_ov.get("lines") or {}).get(src)
    if not x or not OM._alive(from_doc, src):
        return None
    sl = OE._slot(from_ov, x.get("tpl"), x.get("level")) or {}
    r = sl.get("rep")
    if not r or r not in from_ov["lines"] or not OM._alive(from_doc, r):
        return None
    try:
        a, b = OM.look(from_doc, from_ov, src), OM.look(from_doc, from_ov, r)
    except (KeyError, ValueError):
        return None
    return (x.get("key") or sl.get("key") or ""), (sl.get("letter") or x.get("letter") or ""), a.get("kin") == b.get("kin") and OM.same(a, b)


def _find(ov, tid, k1, chain):
    """같은 A · 같은 꼬리로 전에 등록한 종속 템플릿 id 들 — 꼬리 한쪽이 다른 쪽의 앞부분이면 같은 꼬리다(두 번째 넣기가 더 깊거나 얕아도 한 템플릿: 종속 중복 0)."""
    out = []
    for cid, t in (ov.get("templates") or {}).items():
        v = t.get("variant") or {}
        have = list(t.get("chain") or [])
        n = min(len(have), len(chain))
        if v.get("by") == BY and str(v.get("of")) == tid and int(v.get("level") or 0) == k1 and have[:n] == chain[:n]:
            out.append(cid)
    return out


def _fits(doc, ov, C, good, K, flow, toks):
    """이미 있는 종속 템플릿 C 에 이번 대표 후보(good — 레벨 j → 넣은 줄)를 더해도 되나 — 두 쪽에 다 있는 레벨마다 C 의 살아 있는 대표와 비교 값이 같아야 한다(`outline_match.same` · 레터 계열).
    아직 오버레이에 없는 줄의 비교 값은 그 줄을 C 의 그 레벨에 둔 사본 오버레이로 잰다(오버레이는 안 바뀐다). toks = 넣은 줄 → (그 줄의 레터, 키)."""
    for j, g in good.items():
        sl = (C.get("slots") or {}).get(str(K + j)) or {}
        r = sl.get("rep")
        if not r or r not in ov["lines"] or not OM._alive(doc, r):
            continue
        tok, key = toks.get(g) or (sl.get("letter") or "", sl.get("key") or "")
        tmp = {**ov, "lines": {**ov["lines"], g: {"tpl": ov["lines"][r]["tpl"], "no": C.get("no"), "level": K + j, "parent": None, "letter": tok, "key": key, "role": "heading", "flow": flow}}}
        try:
            a, b = OM.look(doc, tmp, g), OM.look(doc, ov, r)
        except (KeyError, ValueError):
            return False
        if a.get("kin") != b.get("kin") or not OM.same(a, b):
            return False
    return True


def register(to_doc, ov, from_doc, from_ov, anchor_id, lines, converted=(), plan_summary=None):
    """넘친 줄 기록 lines(`merge_convert.apply` 의 lines — {id, src, over(j), parent, letter}) 가운데 등록할 수 있는 것을 목적 오버레이 ov 에 등록 →
    {"lines": 등록한 줄 수, "templates": [종속 템플릿 id…], "new": 새로 만든 수, "left": {까닭: 수}}. ov · from_ov 는 세션의 오버레이(dict — ov 를 고친다). 문서는 안 바꾼다."""
    out = {"lines": 0, "templates": [], "new": 0, "left": {}}

    def left(why, n=1):
        out["left"][why] = out["left"].get(why, 0) + n
    if not ov or not from_ov or not lines:
        if lines:
            left("noOverlay", len(lines))
        return out
    lm = _level_map(ov, anchor_id, plan_summary)
    if lm is None:
        left("noAnchor", len(lines))
        return out
    tid, K, shift = lm
    A = (ov.get("templates") or {}).get(tid)
    if A is None:
        left("noAnchor", len(lines))
        return out
    if (A.get("slots") or {}).get(str(K + 1)) is not None:   # 지금 오버레이의 A 에 K+1 레벨이 이미 있다(그래프와 오버레이의 끝이 다름) — 그 레벨을 건너뛰어 종속을 만들지 않는다(astra 3차)
        left("levelMismatch", len(lines))
        return out
    done = set(converted or ())
    rows, keys, letters = [], {}, {}
    for rec in lines:
        nid = rec.get("id")
        if not nid or nid in done:
            left("chosen" if nid in done else "missing")   # 사람이 고른 처리로 바꾼 줄 — 그 서식 그대로(등록 안 함)
            continue
        j = int(rec.get("over") or 0)
        if j < 1:
            continue
        v = _verified(from_doc, from_ov, rec.get("src"))
        if v is None:
            left("srcUnknown")   # 원본 오버레이에 없는 줄 — 소속을 확인할 수 없다
            continue
        key, sletter, same = v
        if not OM._alive(to_doc, nid):
            left("missing")
            continue
        tok = OE.prefix_of(to_doc._text(to_doc._ids[nid]), rec.get("letter") or None)[1]
        if not tok:
            left("noLetter")
            continue
        rows.append((nid, j, rec.get("parent"), tok, key, same, sletter))
    keep, put_ids = [], set()   # 등록할 줄 — 넣을 자리 바로 아래(j 1) · 아니면 함께 넣은 부모가 등록될 때만(문서 차례 = 부모가 먼저)
    up = {}   # 등록할 줄 → 오버레이 부모
    for row in rows:
        nid, j, parent = row[:3]
        if parent in put_ids:
            par = parent
        elif j == 1 and (parent is None or parent in (ov.get("lines") or {})):   # 넘친 첫 레벨 — 넣을 자리 줄(넣을 자리가 그 템플릿의 끝) · 함께 넣어 이미 오버레이에 든 부모
            par = parent or anchor_id
        else:
            left("parent")   # 함께 넣은 부모 줄을 등록하지 못했다(사람이 고른 처리로 바꾼 줄 · 오버레이 밖) — 그 아래 줄도 소속을 정하지 않는다
            continue
        keep.append(row)
        put_ids.add(nid)
        up[nid] = par
    rows = keep
    if not rows:
        return out   # 등록할 줄이 없으면 템플릿도 만들지 않는다
    good = {}   # 레벨 → 대표 후보(부모 거르기를 지난 줄 가운데 원본 슬롯 대표와 같은 첫 줄 — astra 3차: 거르기 전에 고르면 떨어진 줄이 뒤의 후보를 밀어냈다)
    toks = {}
    for nid, j, _, tok, key, same, sletter in rows:
        keys.setdefault(j, key)
        letters.setdefault(j, sletter or tok)
        toks[nid] = (tok, key)
        if same:
            good.setdefault(j, nid)
    m = max(r[1] for r in rows)
    ptail = list(((plan_summary or {}).get("over") or {}).get("tail") or [])
    tail = [keys.get(j) or (ptail[j - 1] if j - 1 < len(ptail) else "") for j in range(1, m + 1)]
    chain = list(A.get("chain") or [])[:K] + tail
    k1 = K + 1
    flow = (ov["lines"].get(anchor_id) or {}).get("flow") or "body"
    cid = None
    for c in _find(ov, tid, k1, chain):   # 같은 꼬리의 템플릿이라도 이미 있는 대표와 서식이 같을 때만 더한다(아니면 새 종속 — 뒤의 「대표에 맞추기」 가 다른 서식을 덮지 않게)
        if _fits(to_doc, ov, ov["templates"][c], good, K, flow, toks):
            cid = c
            break
    if cid is None:
        sfx = OM._free_sfx(ov, tid, k1)
        if not sfx:
            left("noSuffix", len(rows))
            return out
        cid = OM.var_id(tid, k1, sfx)
        ov["templates"][cid] = {"no": f"{A['no']}L{k1}{sfx}", "kind": A.get("kind"), "anchor": f"{A.get('anchor')}~L{k1}{sfx}", "chain": chain, "max": K + m, "base": K,
                                "slots": {str(K + j): {"letter": letters.get(j) or tail[j - 1], "key": tail[j - 1], "rep": None, "count": 0, "prefix": None, "attrs": None, "spacer": None}
                                          for j in range(1, m + 1)},
                                "variant": {"of": tid, "level": k1, "sfx": sfx, "by": BY}}
        br = ov.setdefault("branches", {}).setdefault(f"{tid}|{K}", [])
        if cid not in br:
            br.append(cid)
        out["new"] += 1
    C = ov["templates"][cid]
    if len(chain) > len(C.get("chain") or []):   # 같은 꼬리를 더 깊게 넣었다 — 사슬을 늘린다
        C["chain"] = chain
    for j in range(1, m + 1):   # 같은 꼬리를 다시 넣을 때 더 깊어졌으면 슬롯을 더한다
        if str(K + j) not in C["slots"]:
            C["slots"][str(K + j)] = {"letter": letters.get(j) or tail[j - 1], "key": tail[j - 1], "rep": None, "count": 0, "prefix": None, "attrs": None, "spacer": None}
            C["max"] = max(int(C.get("max") or 0), K + j)
    put = set()
    for nid, j, parent, tok, key, *_ in rows:
        ov["lines"][nid] = {"tpl": cid, "no": C["no"], "level": K + j, "parent": up[nid], "letter": tok, "key": key, "role": "heading", "flow": flow}
        put.add(nid)
    for j in range(1, m + 1):   # 대표 · 동결 모양 — 비었을 때만(이미 정한 대표는 그대로)
        sl = C["slots"][str(K + j)]
        sl["count"] = sum(1 for x in ov["lines"].values() if x.get("tpl") == cid and int(x.get("level") or 0) == K + j)
        r = good.get(j)
        if r in put and not (sl.get("rep") and sl["rep"] in ov["lines"] and OM._alive(to_doc, sl["rep"])):
            try:
                sh = OM.rep_shape(to_doc, ov, r)
            except (KeyError, ValueError):
                continue
            sl.update(rep=r, prefix=sh["prefix"], letter=sh["tok"], attrs=copy.deepcopy(sh["attrs"]), bodyChar=sh["body"])
    out["lines"] = len(put)
    out["templates"] = [cid]
    return out
