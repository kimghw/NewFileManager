"""표의 키-값 추출 · 다른 표에 매핑하는 계획(spec_테이블매니저 ② §7 「키-값 추출과 매핑」). 순수 함수 — 문서 · 세션 · 서버를 모른다
(`app.server` 를 import 하지 않는다 — 부르는 쪽이 `table_manager.judge()["table"]` 을 준다 · 세션 잠금도 부르는 쪽). 스크립트만(LLM 없음).

2026-11-19 사용자 "그리고 테이블을 키값 으로 추출하도록 하고 이걸 다른 테이블에 매핑하는. 기능도 추가해줘."

- **키-값**: 값 칸(역할이 필드인 칸)마다 「어느 헤더 아래의 칸인가」 가 키, 그 칸의 글이 값이다. 키 = 행 경로 · 열 경로의 머리 글을 각각 핵심 글(`heading_calc.key` —
  각주 번호 · 단위 괄호 · 코드를 떼고 빈칸 없이 소문자)로 바꿔 이은 것(「행1›행2|열1›열2」). 글이 없는 머리 칸은 투명하다. 경로가 둘 다 빈 칸은 키가 없다(`key` None).
- **매핑**(`plan`): 원본 표(src)의 값을 받을 표(dst)의 **키가 꼭 같은** 칸에. 어림 · 차례 짝은 없다 — 틀린 칸에 넣는 것보다 안 넣고 알리는 것이 낫다
  (이관의 표 잇기 `merge_fixed` 와 같은 원칙: 분명히 같을 때만 잇고 애매하면 비워 둔다 · 사람이 이미 쓴 글은 덮어쓰지 않는다).
  한 표에 같은 키가 둘 이상이면(`dups`) 그 키는 어느 쪽 표에서든 짝짓지 않는다.
- **매핑 규칙**(같은 날 사용자 "그리고 동일한 테이블이 아니면 매핑규칙은 관리되어야지"): 키가 서로 다른 칸을 어느 키로 읽을지를
  규칙 묶음(`{alias: [{from, to}], pairs: [{from, to}]}` — 저장은 `app/table_maps.py`)으로 준다. `plan(src, dst, rules)` 은 원본 키를 ① 칸 짝(`pairs`) ② 머리글 바꿔 읽기(`alias`)로
  바꿔 읽은 뒤 **꼭 같은 키끼리** 짝짓는다. 규칙은 짝만 정한다 — 상태와 넣는 조건(빈 칸만 · 겹치면 안 덮음 · 수식 칸 제외)은 규칙이 있든 없든 같다.
- **표 타입**(`type_key` — 같은 날 사용자 "같은 표 가 아니라 같은 타입 이런걸로 하면 되지"): 규칙 묶음은 (원본 타입 → 대상 타입) 짝으로 찾는다. 타입 = 머리글 지문(음영 칸의 글 —
  빈칸 · 숫자 · 문장 부호를 뺀 것)이라 값을 채워도 안 바뀐다. 처음에는 키 묶음의 해시(`form_key`)로 찾았는데, 값을 짧은 글로 채우면 스크립트 초안이 그 칸을 머리로 읽어
  견본 105표 가운데 54표의 키 묶음이 바뀌었다(저장한 규칙을 못 찾음). 같은 타입이어도 키는 다를 수 있다(「1차년도 › 현금」 ↔ 「2차년도 › 현금」) — 규칙은 같은 타입끼리도 둔다.
- 글이 같은지는 빈칸 · 줄 나눔 차이를 흡수해 견준다(`merge_gather_frame.norm` — 수 · 영문 낱말 사이의 빈칸은 뜻이 있어 남긴다).
- 문서에 쓰는 것은 끝점(`app/table_kv_api.py`)이다 — 여기는 계획까지."""
import hashlib
import json
import re
from collections import Counter

from app import heading_calc as HC
from app import table_prune
from app.heading_rules import BR
from app.merge_gather_frame import norm

STATUSES = ("fill", "same", "clash", "calc", "emptySrc", "nonnum")   # nonnum = 더하기 · 빼기(· 더해서 넣기)에서 수가 아닌 글
OPS = ("fill", "add", "sub", "replace")   # 칸마다 넣는 방식 — 빈 칸에만(기본) · 더하기 · 빼기 · 덮어쓰기
HEAD_MAX = 80                    # 머리 글 하나(보이는 것 — 키는 글 전체로 만든다)
PATH_SEP, AXIS_SEP = "›", "|"    # 키 「행1›행2|열1›열2」
TYPE_HEAD = 24                   # 표 타입의 머리글 지문에 싣는 칸마다의 글 길이
_TYPE_DROP = re.compile(r"[\W\d_]+")  # 머리글 지문에서 빼는 것 — 빈칸 · 숫자 · 문장 부호(`outline_match._FORM_DROP` 과 같은 규칙: 「1차년도」·「2차년도」 는 같은 머리글)
WHY = {"emptySrc": "원본 칸이 비어 있습니다", "emptyObj": "원본 칸에 글이 없습니다(표 · 그림만)", "calc": "수식으로 셈하는 칸(합계 · 비율)이라 넣지 않습니다",
       "obj": "칸 안에 표 · 그림이 있어 넣지 않습니다", "clash": "칸에 다른 글이 있어 덮지 않습니다",
       "nokey": "머리글이 없어 키가 없습니다", "dup": "이 표에 같은 키가 둘 이상입니다", "dupOther": "상대 표에 같은 키가 둘 이상입니다", "none": "상대 표에 같은 키가 없습니다",
       "dupRead": "매핑 규칙으로 바꿔 읽은 뒤 같은 키가 둘 이상입니다"}


def cell_lines(stage1, tb):
    """{칸 id: [그 칸의 글 줄…]} — 문단마다 한 줄(강제 줄 바꿈은 줄을 나눈다 · 빈 문단 · 개체 문단은 뺀다). 넣을 때 문단 나눔을 지키려는 것이다
    (`textFull` 은 문단을 빈칸으로 이어 붙인 글이라 그대로 넣으면 여러 문단이 한 문단이 된다).
    stage1 = 그 표의 문단 레코드({"paras": […]} — `table_excel.records`), tb = 그 레코드로 만든 collect 꼴 표(칸마다 `paras` = 문단 id 차례)."""
    recs = {r["id"]: r for r in (stage1 or {}).get("paras") or ()}
    out = {}
    for x in tb["cells"]:
        got = []
        for pid in x.get("paras") or ():
            r = recs.get(pid)
            if r is None or r.get("kind") in ("empty", "object"):
                continue
            got += [t.strip() for t in (r.get("text") or "").split(BR) if t.strip()]
        out[x["id"]] = got
    return out


def _heads(by, ids):
    """경로(머리 칸 id 사슬) → (보일 머리 글 목록, 키 조각 목록). 글이 없는 머리 칸 · 핵심 글이 빈 머리 칸(단위뿐)은 키에서 투명하다."""
    shown, keys = [], []
    for i in ids or ():
        h = by.get(i)
        text = HC.clean((h or {}).get("textFull") or "")
        if not text:
            continue
        shown.append(text if len(text) <= HEAD_MAX else text[:HEAD_MAX - 1] + "…")
        k = HC.key(text)
        if k:
            keys.append(k)
    return shown, keys


def _num(v):
    if v is None:
        return None
    return int(v) if float(v).is_integer() and abs(v) < 1e15 else round(v, 6)


def extract(tb, lines=None, objs=()):
    """표의 키-값 → {"table", "items": [{cell, ref, sub, row, col, key, label, text, empty, num, calc, obj?}], "dups": [키…], "counts": {items, keyed, empty, dups}}.

    tb = `table_manager.judge()["table"]`(칸마다 role · rowPath · colPath · formulas · textFull). **필드 칸만**, 표의 칸 차례(행 → 열)로.
    lines = {칸 id: [글 줄…]}(`cell_lines`) — 주면 값 글이 문단마다 줄로(「\\n」), 안 주면 `textFull`(문단을 빈칸으로 이은 글).
    objs = 칸 안에 표 · 그림이 있는 칸 id(부르는 쪽이 문서의 표 블록에서 읽어 준다 — 그런 칸은 글을 쓰지 않는다). collect 가 아는 것(칸 안 표 · 개체 문단)은 여기서도 본다.
    key = 「행1›행2|열1›열2」(핵심 글 — `heading_calc.key`) | None(경로가 둘 다 빔). label = 보일 키 글(「행1 › 행2 | 열1 › 열2」).
    empty = 빈 칸이거나 자리표시뿐(`table_prune.cell_empty`). calc = 수식으로 셈하는 칸(`formulas` 가 있음). obj = 칸 안에 표 · 그림이 있음(있을 때만 True).
    dups = 한 표에 둘 이상 나온 키(첫 차례대로) — 매핑에 쓰지 않는다."""
    by = {x["id"]: x for x in tb["cells"]}
    objs = set(objs or ())
    items, seen = [], Counter()
    for x in tb["cells"]:
        if x.get("role") != "field":
            continue
        row, rk = _heads(by, x.get("rowPath"))
        col, ck = _heads(by, x.get("colPath"))
        key = f"{PATH_SEP.join(rk)}{AXIS_SEP}{PATH_SEP.join(ck)}" if rk or ck else None
        label = " | ".join(" › ".join(p) for p in (row, col) if p) if key else ""
        got = (lines or {}).get(x["id"])
        text = "\n".join(got) if got is not None else (x.get("textFull") or "").strip()
        it = {"cell": x["id"], "ref": HC.ref(x), "sub": x.get("sub"), "row": row, "col": col, "key": key, "label": label, "text": text,
              "empty": table_prune.cell_empty(x), "num": _num(x.get("num")), "calc": bool(x.get("formulas"))}
        if x["id"] in objs or x.get("nested") or (x.get("kinds") or {}).get("object"):
            it["obj"] = True
        if key is not None:
            seen[key] += 1
        items.append(it)
    dups = [k for k, n in seen.items() if n > 1]
    return {"table": tb["id"], "items": items, "dups": dups,
            "counts": {"items": len(items), "keyed": sum(1 for i in items if i["key"] is not None), "empty": sum(1 for i in items if i["empty"]), "dups": len(dups)}}


def same_text(a, b):
    """두 칸 글이 같은가 — 빈칸 · 줄 나눔 차이는 같은 글."""
    return norm(a) == norm(b)


def form_key(ex):
    """키 묶음의 해시 — 그 표의 키(중복 없이 · 정렬)의 해시(`extract` 의 결과에서). `type_key` 의 **마지막 대체**로만 쓴다(머리글로 타입을 못 정한 표):
    값을 짧은 글로 채우면 초안이 그 칸을 머리로 읽어 키 묶음이 바뀔 수 있다(모듈 설명)."""
    keys = sorted({i["key"] for i in ex["items"] if i["key"] is not None})
    return hashlib.sha1(json.dumps(keys, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]


def type_key(tb, ex=None):
    """표 타입 — 그 표의 **머리글 지문**(12자리). 매핑 규칙 묶음은 (원본 타입 → 대상 타입) 짝으로 찾는다(`table_maps.find`).

    tb = `table_manager.judge()["table"]`(collect 꼴 — 칸마다 shaded · row · col · textFull). 음영이 있는 칸의 글을 (행, 열) 차례로, 빈칸 · 숫자 · 문장 부호를 빼고(`_TYPE_DROP`)
    칸마다 24자까지 이은 것의 해시. 뺀 뒤 빈 글인 칸은 건너뛴다. 음영 칸의 글이 하나도 없으면 첫 행의 글, 그것도 없으면 키 묶음의 해시(`form_key` — ex = 그 표의 `extract` 결과, 안 주면 여기서 뽑는다).
    「표 양식」(`outline_match._read_form` 의 머리글 지문 — spec_hwpx_웹편집 ② §8-11)과 같은 규칙이다(그 모듈을 부르지는 않는다 — 문서 요소가 아니라 판정된 표를 읽는다).
    칸 역할(초안)을 안 보므로 값을 채워도 안 바뀌고(값 칸은 음영이 없다), 숫자를 빼므로 기관 · 연도마다 되풀이되는 같은 표(「1차년도」 표 · 「2차년도」 표)는 같은 타입이다."""
    cells = sorted(tb["cells"], key=lambda x: (x["row"], x["col"]))
    heads = [x.get("textFull") or "" for x in cells if x.get("shaded")]
    if not any(h.strip() for h in heads):
        top = min((x["row"] for x in cells), default=0)
        heads = [x.get("textFull") or "" for x in cells if x["row"] == top]
    sig = "|".join(s[:TYPE_HEAD] for s in (_TYPE_DROP.sub("", h) for h in heads) if s)
    if not sig:
        return form_key(ex if ex is not None else extract(tb))
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]


def key_parts(key):
    """키 「행1›행2|열1›열2」 → (행 조각 목록, 열 조각 목록)."""
    r, _, c = (key or "").partition(AXIS_SEP)
    return [p for p in r.split(PATH_SEP) if p], [p for p in c.split(PATH_SEP) if p]


def _reader(rules, dst):
    """규칙 묶음 → 원본 키를 바꿔 읽는 함수 key → (바꿔 읽은 키, by: pair | alias | key). 칸 짝(`pairs`)이 머리글 바꿔 읽기(`alias`)보다 먼저다.
    alias 의 from 은 키의 **조각**(머리글의 핵심 글)과 꼭 같을 때만 듣는다 — 머리글을 그대로 적은 규칙(「1 차년도」)도 듣게 핵심 글로도 한 번 더 견준다.
    to 는 대상 표에 그 조각이 그대로 있으면 그것, 아니면 핵심 글로 바꾼 것."""
    rules = rules if isinstance(rules, dict) else {}
    pairs = {p["from"]: p["to"] for p in rules.get("pairs") or () if isinstance(p, dict) and isinstance(p.get("from"), str) and isinstance(p.get("to"), str) and p["from"] and p["to"]}
    frags = {f for i in dst["items"] if i["key"] is not None for part in key_parts(i["key"]) for f in part}
    alias = {}
    for a in rules.get("alias") or ():
        f, t = (a.get("from"), a.get("to")) if isinstance(a, dict) else (None, None)
        if not (isinstance(f, str) and isinstance(t, str) and f.strip() and t.strip()):
            continue
        to = t if t in frags else (HC.key(t) or t.strip())
        for k in dict.fromkeys((f, HC.key(f) or f.strip())):
            alias.setdefault(k, to)

    def read(key):
        if key in pairs:
            return pairs[key], "pair"
        if alias:
            rk, ck = key_parts(key)
            nr, nc = [alias.get(p, p) for p in rk], [alias.get(p, p) for p in ck]
            if nr != rk or nc != ck:
                return f"{PATH_SEP.join(nr)}{AXIS_SEP}{PATH_SEP.join(nc)}", "alias"
        return key, "key"
    return read


def _ops(rules):
    """규칙 묶음의 `ops`(칸마다 넣는 방식 — 같은 사양서 ② §7) → 받을 칸의 키 → 방식(fill · add · sub · replace)을 주는 함수. 없는 칸은 fill.
    `key` 로 적은 칸이 먼저고, 그다음 그 키의 조각(행 쪽 · 열 쪽 머리글)에 `part` 로 적은 것 — 여러 조각에 걸리면 **목록에서 뒤에 적은 것**(나중에 정한 것)이 이긴다.
    `part` 는 키의 조각과 꼭 같을 때와 핵심 글로 바꾼 것이 같을 때 듣는다(`alias` 와 같다)."""
    rules = rules if isinstance(rules, dict) else {}
    by_key, by_part = {}, {}
    for n, o in enumerate(rules.get("ops") or ()):
        if not isinstance(o, dict) or o.get("op") not in OPS:
            continue
        if isinstance(o.get("key"), str) and o["key"]:
            by_key[o["key"]] = o["op"]
        elif isinstance(o.get("part"), str) and o["part"].strip():
            for k in dict.fromkeys((o["part"], HC.key(o["part"]) or o["part"].strip())):
                by_part[k] = (n, o["op"])

    def of(key):
        if key is None:
            return "fill"
        if key in by_key:
            return by_key[key]
        hit = [by_part[p] for part in key_parts(key) for p in part if p in by_part]
        return max(hit)[1] if hit else "fill"
    return of


WHY_OP = {"srcText": "원본이 수가 아닌 글이라 셈하지 않습니다", "dstText": "받을 칸의 글이 수가 아니라 셈하지 않습니다"}


def _num_of(text, empty):
    """글을 수로 → ("num", 읽은 것) | ("empty", None)(빈 칸 · 자리표시) | ("text", None)(수가 아닌 글)."""
    return _read_num({"empty": empty, "text": text})


def _put(op, s, d):
    """방식 op 로 원본 항목 s 를 받을 항목 d 에 넣을 때 → {status, text: 넣을 글, why?, check?, expr?}(같은 사양서 ② §7 「칸마다 넣는 방식」).
    fill = `_status`(빈 칸에만 — 전과 같다). replace: 원본이 빔 → 글이 같음 → 수식 칸 → 칸 안 표 · 그림 → 넣을 수 있음. add · sub: 원본이 빔 → 수식 칸 → 칸 안 표 · 그림 →
    원본 · 받을 칸이 수가 아님(nonnum) → 받을 칸의 수(비었으면 0) ± 원본의 수 = 지금 글과 같음(same) | 넣을 수 있음. 넣을 수 있는 것은 모두 status `fill` 이고,
    **받을 칸에 이미 값이 있는 add · sub · replace 는 check**(화면이 처음에는 고르지 않는다 — 같은 매핑을 두 번 하면 두 번 더해진다) + had(그 까닭이 「이미 값이 있음」 — 더해서 넣기의 「일부만 값」 과 가른다).
    expr = 셈의 풀이 「= 500 + 700」."""
    if op not in ("add", "sub", "replace"):
        status, why = _status(s, d)
        return {"status": status, "text": s["text"], **({"why": why} if why else {})}
    if s["empty"] or not s["text"].strip():
        return {"status": "emptySrc", "text": s["text"], "why": WHY["emptyObj" if s.get("obj") and not s["empty"] else "emptySrc"]}
    if op == "replace" and same_text(s["text"], d["text"]):
        return {"status": "same", "text": s["text"]}
    if d["calc"]:
        return {"status": "calc", "text": s["text"], "why": WHY["calc"]}
    if d.get("obj"):
        return {"status": "clash", "text": s["text"], "why": WHY["obj"]}
    if op == "replace":
        return {"status": "fill", "text": s["text"], **({} if d["empty"] else {"check": True, "had": True})}
    (ks, rs), (kd, rd) = _num_of(s["text"], False), _num_of(d["text"], d["empty"])
    if ks != "num" or kd == "text":
        return {"status": "nonnum", "text": "", "why": WHY_OP["srcText" if ks != "num" else "dstText"]}
    return _calc_put(op, [(rs, s["text"])], d, rd)


def _calc_put(op, nums, d, rd):
    """받을 칸의 수(rd — 읽은 것 | None = 빈 칸: 0 으로 본다) ± 원본들의 수(nums = [(읽은 것, 글)…]) → {status, text, expr, check?, had?, why?}.
    **셈하는 수의 단위**(같은 사양서 ② §7): 셈하는 수들(원본들 + 값이 있는 받을 칸)의 뒤 글이 서로 다르면 셈하지 않는다(`nonnum` — 환산하지 않는다), 뒤 글을 적은 수와 안 적은 수가 섞이면 셈하되 check + why,
    넣을 글에는 뒤 글을 지킨다(`_units`)."""
    sign = -1 if op == "sub" else 1
    mine = [(rd, d["text"])] if rd is not None else []
    tail, kinds, mixed = _units([*mine, *nums], "" if rd is not None else d["text"])
    if tail is None:
        return {"status": "nonnum", "text": "", "why": WHY_UNIT["differ"] % " · ".join(kinds)}
    _total, text = _sum_text([*mine, *(({**g, "num": sign * g["num"]}, t) for g, t in nums)], "" if rd is not None else d["text"], tail)
    body = " + ".join(HC.clean(t).strip() for _, t in nums)
    expr = f"= {HC.clean(d['text']).strip() if rd is not None else '0'} {'−' if sign < 0 else '+'} {f'({body})' if sign < 0 and len(nums) > 1 else body}"
    if rd is not None and same_text(text, d["text"]):
        return {"status": "same", "text": text, "expr": expr}
    return {"status": "fill", "text": text, "expr": expr, **({"check": True, "had": True} if rd is not None else {}), **({"check": True, "why": WHY_UNIT["mixed"]} if mixed else {})}


def _status(s, d):
    """짝 하나의 상태 → (status, 까닭 글 | ""). 차례: 원본이 빔 → 글이 같음 → 받을 칸이 수식 칸 → 받을 칸에 표 · 그림 → 받을 칸이 빔(넣을 수 있음) → 겹침."""
    if s["empty"] or not s["text"].strip():
        return "emptySrc", WHY["emptyObj" if s.get("obj") and not s["empty"] else "emptySrc"]
    if same_text(s["text"], d["text"]):
        return "same", ""
    if d["calc"]:
        return "calc", WHY["calc"]
    if d.get("obj"):
        return "clash", WHY["obj"]
    if d["empty"]:
        return "fill", ""
    return "clash", WHY["clash"]


def plan(src, dst, rules=None):
    """src 의 값을 dst 에 넣는 계획(둘 다 `extract` 의 결과 — 문서는 안 바뀐다) →
    {"pairs": [{key, label, from, to, text, was, status, by, why?, fromKey?, fromLabel?}], "unmatched": {"src": [항목 + why (+ as)…], "dst": [항목 + why…]},
     "counts": {fill, same, clash, calc, emptySrc, unmatched, unmatchedSrc, unmatchedDst, byRule}}.

    rules = 매핑 규칙 묶음 {alias: [{from: 원본 머리글, to: 대상 머리글}], pairs: [{from: 원본 키, to: 대상 키}]} | None — 있으면 원본 키를 ① 칸 짝 ② 머리글 바꿔 읽기로
    바꿔 읽은 뒤 짝짓는다(`_reader`). 바꿔 읽은 뒤 같은 키가 둘 이상이 되면 그 키는 짝짓지 않는다.
    짝 = (바꿔 읽은) 키가 **꼭 같고** 두 표에서 그 키가 하나씩인 칸(받을 표의 칸 차례로). from · to = 칸 id, text = 넣을 글(원본 칸 글), was = 받을 칸의 지금 글,
    key · label = 받을 표의 키 · 보일 키 글. by = `key`(그대로 같음) | `alias` | `pair` — 규칙으로 맺은 짝에는 fromKey · fromLabel(원본의 키 · 보일 키 글)이 붙는다.
    status: `fill`(받을 칸이 비었고 — 자리표시 포함 — 원본에 값이 있음: 넣을 수 있음) · `same`(글이 같음) · `clash`(받을 칸에 다른 글 · 칸 안 표 · 그림 — **덮지 않는다**) ·
    `calc`(받을 칸이 수식으로 셈하는 칸 — 안 넣음) · `emptySrc`(원본이 빔 · 자리표시뿐). why = 넣지 않는 까닭(fill · same 에는 없다).
    규칙은 짝만 정한다 — 규칙으로 맺은 짝도 상태는 같은 차례로 정한다.
    **칸마다 넣는 방식**: 규칙 묶음의 `ops` 가 받을 칸의 키에 정한 방식(`_ops` — 없으면 fill)으로 상태 · 넣을 글을 정한다(`_put`). 짝에 `op` 가 늘 붙고, add · sub 에는 `expr`(셈의 풀이),
    받을 칸에 이미 값이 있는 add · sub · replace 에는 `check: True` 가 붙는다. 넣을 수 있는 짝은 방식이 무엇이든 status `fill` 이다(`text` = 넣을 글). 수가 아닌 글은 `nonnum`. counts 에 `nonnum` · `check`(확인이 붙은 넣을 수 있는 짝).
    unmatched = 짝을 못 얻은 항목(키 없음 · 같은 키가 둘 이상 · 상대 표에 없음) — 항목 사본 + why. 원본 항목에서 규칙이 키를 바꿔 읽었으면 as = 바꿔 읽은 키."""
    read = _reader(rules, dst) if rules else (lambda k: (k, "key"))
    op_of = _ops(rules)
    s_raw, d_cnt = Counter(i["key"] for i in src["items"] if i["key"] is not None), Counter(i["key"] for i in dst["items"] if i["key"] is not None)
    seen = {i["cell"]: read(i["key"]) for i in src["items"] if i["key"] is not None}   # 원본 칸 → (바꿔 읽은 키, by)
    s_cnt = Counter(k for k, _ in seen.values())
    s_ok = {seen[i["cell"]][0]: i for i in src["items"] if i["key"] is not None and s_cnt[seen[i["cell"]][0]] == 1}
    pairs, used = [], set()
    counts = {**{k: 0 for k in STATUSES}, "check": 0}
    for d in dst["items"]:
        s = s_ok.get(d["key"]) if d["key"] is not None and d_cnt[d["key"]] == 1 else None
        if s is None:
            continue
        op = op_of(d.get("okey", d["key"]))   # okey = 값 머리의 조각을 빼기 전의 키(묶어 넣기가 준다 — 방식은 받을 표의 제 키로 찾는다)
        got = _put(op, s, d)
        by = seen[s["cell"]][1]
        counts[got["status"]] += 1
        counts["check"] += got["status"] == "fill" and bool(got.get("check"))
        used.add(s["cell"])
        pairs.append({"key": d["key"], "label": d["label"], "from": s["cell"], "to": d["cell"], "was": d["text"], "by": by, "op": op, **got,
                      **({"src": s["text"]} if op in ("add", "sub", "replace") else {}), **({"fromKey": s["key"], "fromLabel": s["label"]} if by != "key" else {})})
    paired = {p["key"] for p in pairs}
    left_s = []
    for i in src["items"]:
        if i["cell"] in used:
            continue
        k, (tk, _by) = i["key"], seen.get(i["cell"], (None, "key"))
        why = "nokey" if k is None else "dup" if s_raw[k] > 1 else "dupRead" if s_cnt[tk] > 1 else "dupOther" if d_cnt[tk] > 1 else "none"
        left_s.append({**i, "why": WHY[why], **({"as": tk} if k is not None and tk != k else {})})
    s_keys = set(s_cnt)
    left_d = []
    for i in dst["items"]:
        k = i["key"]
        if k is not None and k in paired:
            continue
        why = "nokey" if k is None else "dup" if d_cnt[k] > 1 else "dupOther" if k in s_keys else "none"
        left_d.append({**i, "why": WHY[why]})
    return {"pairs": pairs, "unmatched": {"src": left_s, "dst": left_d},
            "counts": {**counts, "unmatched": len(left_s) + len(left_d), "unmatchedSrc": len(left_s), "unmatchedDst": len(left_d),
                       "byRule": sum(1 for p in pairs if p["by"] != "key")}}


def sig(pair, mark=None):
    """짝의 도장 — 받을 칸 · 넣을 글 · 지금 글 · 원본(칸, 여러 원본이면 표와 칸) · 넣는 방식(op)의 해시. 계획을 본 뒤 어느 하나라도 바뀌면 달라진다(반영 때 다시 세운 계획의 것과 견준다).
    mark = 두 표의 판정이 어디서 왔는가(초안 | 양식의 확정본과 그 판 — 끝점이 준다): 확정본이 바뀌면 칸 역할 · 키가 달라질 수 있어 도장도 달라지게 한다(spec_테이블매니저 ② §10 「양식의 표 판정」)."""
    src = json.dumps([pair["to"], pair["text"], pair["was"], pair.get("from"), pair.get("op") or "fill", *([mark] if mark is not None else [])], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha1(src.encode("utf-8")).hexdigest()[:12]


def div_of(bases, key):
    """그 키의 칸이 놓인 구분 기준의 값 → {기준(year · org · stage · period): 값 머리의 키 조각 | [조각…]}. 그 기준의 값 머리 아래가 아니면 그 기준은 없다.
    bases = `bases(그 표)` · key = 그 표의 항목 키. 같은 기준이 두 곳(행 쪽 · 열 쪽 · 다른 자리)에 있으면 그 칸이 놓인 **모든** 값 머리의 조각이다 — 하나면 글, 둘 이상이면 목록
    (「2026년 행 × 2027년 열」 → ["2027년", "2026년"]: 화면은 그 가운데 하나라도 꺼져 있으면 그 짝을 뺀다)."""
    out = {}
    if key is None:
        return out
    parts = key_parts(key)
    for b in bases or ():
        ps = parts[0 if b["on"] == "row" else 1]
        if b["level"] < len(ps) and any(v["part"] == ps[b["level"]] for v in b["values"]):
            got = out.setdefault(b["basis"], [])
            if ps[b["level"]] not in got:
                got.append(ps[b["level"]])
    return {k: v[0] if len(v) == 1 else v for k, v in out.items()}


def with_div(bases, pairs, key_of=None):
    """구분 기준의 값 고르기(같은 사양서 ② §7 의 「구분 기준의 값 고르기」)에 쓸 것 — 짝마다 `div`(`div_of`)를 붙이고(제자리), 기준마다 값마다 짝 수 · 넣을 수 있는 수를 실은 bases 사본을 돌려준다
    (값마다 `pairs` · `fill`). bases = 값을 받을 표(나눠 넣기에서는 원본 표)의 기준, key_of(짝) = 그 표에서의 키(안 주면 짝의 `key` — 받을 표의 키)."""
    key_of = key_of or (lambda p: p["key"])
    out = [{**b, "values": [{**v, "pairs": 0, "fill": 0} for v in b["values"]]} for b in bases or ()]
    for p in pairs:
        key = key_of(p)
        p["div"] = div_of(bases, key)
        parts = key_parts(key) if key is not None else ([], [])
        for b in out:
            ps = parts[0 if b["on"] == "row" else 1]
            v = next((v for v in b["values"] if b["level"] < len(ps) and v["part"] == ps[b["level"]]), None)
            if v is not None:
                v["pairs"] += 1
                v["fill"] += p["status"] == "fill"
    return out


# ---- 구분 기준으로 묶어 넣기(다대일 — spec_테이블매니저 ② §7 「키-값 추출과 매핑」 의 「구분 기준으로 묶어 넣기」) ---------------------------------------------------
# 2026-11-19 사용자 "구분기준에 따라 열헤더가 있을거 아냐? 거기 분류대로 넣으면 되지.. 넣을때 팝업으로 기준을 뭘로 할래 , 년차로 할래, 기관으로 할래 또 뭐가 있으면 어떤 기준으로 각각 그룹핑해서 넣으면 되지."
# 값을 받을 표에 구분 기준의 값 머리(「1차년도 | 2차년도」 · 기관 이름 열 …)가 있으면, 원본 표(그 머리글이 없는 표 — 한 차년도 · 한 기관의 표)를 그 기준의 값마다 묶어 그 값 머리 아래 칸에 넣는다.
# 값이 정해지지 않은 원본은 넣지 않는다(짐작하지 않는다) · 값을 더하는 것(셀 값 합산)은 여기 없다.

BASES = ("year", "org", "stage", "period")   # 묻는 차례(차년도 · 기관 · 단계 · 연도)
_VALUE_NUM = {"year": re.compile(r"(?<!\d)(\d{1,2})\s*(?:차\s*년\s*도|년\s*차|연\s*차|차\s*년|차(?![가-힣]))"), "stage": re.compile(r"(?<!\d)(\d{1,2})\s*단계"),
              "period": re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")}   # 값 머리의 글에서 읽는 수(「2차년도」 · 「2차」 · 「2단계」 · 「2026」)
_TEXT_NUM = {**_VALUE_NUM, "year": re.compile(r"(?<!\d)(\d{1,2})\s*(?:차\s*년\s*도|년\s*차|연\s*차|차\s*년)")}   # 다른 글(표 앞 문단 · 구분 줄)에서는 「N차」 홀로는 안 읽는다(「1차 시험」)
WHY_SRC = {"novalue": "어느 값의 것인지 정해지지 않았습니다 — 값을 고르세요", "nohead": "값을 받을 표에 그 값의 머리글이 없습니다"}
WHY_DST = {"other": "이 기준의 머리글 아래 칸이 아닙니다", "nosrc": "이 값의 원본 표가 없습니다", "two": "원본 둘이 같은 칸에 걸립니다 — 어느 것도 넣지 않습니다"}


def _key_heads(by, ids):
    """경로(머리 칸 id 사슬) → [(머리 칸, 키 조각)] — 키에 드는 머리만(글 · 핵심 글이 빈 머리는 투명: `_heads` 와 같은 규칙이라 차례가 키의 조각 차례와 같다)."""
    out = []
    for i in ids or ():
        h = by.get(i)
        k = HC.key(HC.clean((h or {}).get("textFull") or ""))
        if k:
            out.append((h, k))
    return out


def bases(tb):
    """값을 받을 표의 기준 — 구분 기준의 **값 머리**가 둘 이상 있는 곳마다 [{basis, on: "row" | "col", level, values: [{part, label, cells}]}](없으면 빈 목록 — 묶어 넣기를 권하지 않는다).

    tb = `table_manager.judge()["table"]`(머리 칸마다 basis[] · basisKind — `heading_calc.band_basis`). 값 머리 = `basisKind == "value"` 이고 basis 에 year · org · stage · period 가 든 머리
    (「1차년도」 · 「2단계」 · 「주관연구개발기관」 · 「2026」 — 「차년도」 처럼 기준의 **이름**만 적은 머리는 아니다). level = 필드의 행 · 열 경로에서 그 머리가 놓이는 자리(키의 조각 차례 —
    글이 빈 머리는 세지 않는다). part = 그 머리의 키 조각(`heading_calc.key`) · label = 머리 글 · cells = 그 머리 아래 필드 수. 차례는 차년도 · 기관 · 단계 · 연도, 열 쪽 먼저."""
    by = {x["id"]: x for x in tb["cells"]}
    found = {}
    for x in tb["cells"]:
        if x.get("role") != "field":
            continue
        for on, path in (("row", x.get("rowPath")), ("col", x.get("colPath"))):
            for lv, (h, part) in enumerate(_key_heads(by, path)):
                if h.get("basisKind") != "value":
                    continue
                for b in h.get("basis") or ():
                    if b not in BASES:
                        continue
                    text = HC.clean(h.get("textFull") or "")
                    v = found.setdefault((b, on, lv), {}).setdefault(part, {"part": part, "label": text if len(text) <= HEAD_MAX else text[:HEAD_MAX - 1] + "…", "cells": 0})
                    v["cells"] += 1
    out = [{"basis": b, "on": on, "level": lv, "values": [*vals.values()]} for (b, on, lv), vals in found.items() if len(vals) >= 2]
    return sorted(out, key=lambda g: (BASES.index(g["basis"]), g["on"] != "col", g["level"]))


def value_of(base, text):
    """글이 가리키는 그 기준의 값 → 값 머리의 키 조각(part) | None. 대상의 값 머리(`bases` 의 한 항목) 가운데 **하나만** 맞을 때만 — 둘 이상이 맞거나 하나도 안 맞으면 None(짐작하지 않는다).
    수가 있는 값 머리(「2차년도」 · 「2단계」 · 「2026」)는 글에 적힌 그 기준의 수와 견주고, 수가 없는 값 머리(기관 이름)는 그 글이 통째로 들어 있는지 본다(빈칸은 뺀다)."""
    squash = "".join(str(text or "").split()).lower()
    if not squash:
        return None
    b = base["basis"]
    said = {int(n) for n in _TEXT_NUM[b].findall(squash)} if b in _TEXT_NUM else set()
    hits = []
    for v in base["values"]:
        lab = "".join(v["label"].split()).lower()
        nums = {int(n) for n in _VALUE_NUM[b].findall(lab)} if b in _VALUE_NUM else set()
        if (nums & said) if nums else (len(lab) >= 2 and lab in squash):
            hits.append(v["part"])
    return hits[0] if len(hits) == 1 else None


def suggest(base, hints):
    """원본 표가 그 기준의 어느 값의 것인지 **권한다** → {"value": part | None, "valueLabel": 머리 글 | None, "by": "zone" | "owner" | "text" | None}.
    hints = {"zone": 편집 구역이 그 표에 준 귀속 {year: 전체 차례, stage, orgName} | None, "owner": 표의 소속 구분 줄 글(3단계 `owner.division.text`) | None, "before": [표 앞 문단 글 — 문서 차례]}.
    차례: ① 편집 구역 ② 표의 소속 ③ 표 앞 문단(가까운 문단부터). 대상의 값 머리와 맞는 것이 없으면 값 없음 — 사람이 고른다."""
    z = hints.get("zone") or {}
    b = base["basis"]
    num = z.get(b) if b in ("year", "stage") else None
    ztext = (f"{num}{'차년도' if b == 'year' else '단계'}" if isinstance(num, int) and not isinstance(num, bool) else None) if b in ("year", "stage") else z.get("orgName") if b == "org" else None
    labels = {v["part"]: v["label"] for v in base["values"]}
    for by, texts in (("zone", [ztext]), ("owner", [hints.get("owner")]), ("text", [*(hints.get("before") or ())][::-1])):
        for t in texts:
            part = value_of(base, t) if t else None
            if part is not None:
                return {"value": part, "valueLabel": labels[part], "by": by}
    return {"value": None, "valueLabel": None, "by": None}


def _cut(key, axis, level):
    """키에서 (행 | 열)의 level 째 조각을 뺀 키 | None(조각이 하나도 안 남음)."""
    parts = [[*p] for p in key_parts(key)]
    del parts[axis][level]
    return f"{PATH_SEP.join(parts[0])}{AXIS_SEP}{PATH_SEP.join(parts[1])}" if parts[0] or parts[1] else None


def plan_grouped(sources, dst, group=None, rules=None):
    """여러 원본 표의 값을 dst 에 넣는 계획(문서는 안 바뀐다) — 기준(group)의 값마다 묶어 그 값 머리 아래 칸에. group None = 기준 없이(원본마다 키 그대로 1대1).

    sources = [{"ex": 추출(`extract`), "value": 그 원본이 어느 값의 것인가(값 머리의 키 조각) | None, "table": 표 id, "doc"?: 다른 문서 id}], dst = 받을 표의 추출,
    group = `bases(받을 표)` 의 한 항목({basis, on, level, values}), rules = 매핑 규칙 묶음 — 원본마다의 목록([묶음 | None …] — 원본 타입 → 대상 타입 짝마다 다른 묶음) 또는 묶음 하나 | None.
    원본마다: 받을 표의 항목 가운데 **그 값 머리 아래의 칸**만 보고, 받을 키에서 그 조각을 뺀 키와 원본 키가 꼭 같을 때 짝짓는다(`plan` — 매핑 규칙은 그 뒤에 같이: 칸 짝의 대상 키가 그 값 머리를
    품고 있으면 같은 조각을 빼고 견준다). value 가 None 인 원본은 짝짓지 않는다(짐작하지 않는다). 두 원본이 같은 칸에 걸리면 그 칸의 짝은 모두 `clash`(why 「원본 둘이 같은 칸」).
    상태 · 넣는 조건은 1대1 과 같다.
    → {"pairs": [`plan` 의 짝 + {from: {table, cell(, doc)}, src: 원본 차례, group: 값의 머리 글 | None, value: 값의 키 조각 | None}](받을 표의 칸 차례),
       "unmatched": {"src": [항목 + why + table + src…], "dst": [항목 + why…]}, "counts": {fill, same, clash, calc, emptySrc, unmatched, unmatchedSrc, unmatchedDst, byRule},
       "groups": [{value, label, tables: [표 id…], counts: {fill, same, clash, calc, emptySrc}}](값마다 — 기준 없이면 원본마다 {table, label, …}),
       "sources": [{table, (doc,) value, valueLabel, why?, counts: {fill, …, byRule, unmatched}}]}."""
    axis, level = (0 if group["on"] == "row" else 1, group["level"]) if group else (None, None)
    labels = {v["part"]: v["label"] for v in (group or {}).get("values") or ()}
    rules = rules if isinstance(rules, (list, tuple)) else [rules] * len(sources)
    full = {i["cell"]: i for i in dst["items"]}

    def under(it):   # 그 항목이 놓인 값 조각 | None
        ps = key_parts(it["key"])[axis] if it["key"] is not None else ()
        return ps[level] if level < len(ps) else None

    pairs, left_s, info, taken = [], [], [], set()
    for n, s in enumerate(sources):
        v, rec = s.get("value"), {"table": s.get("table"), **({"doc": s["doc"]} if s.get("doc") else {}), "value": s.get("value"), "valueLabel": None}
        info.append(rec)
        sub, rule = dst, rules[n] if n < len(rules) else None
        if group:
            rec["valueLabel"] = labels.get(v, v)
            items = [{**it, "key": _cut(it["key"], axis, level), "okey": it["key"]} for it in dst["items"] if v is not None and under(it) == v]
            if v is None or not items:
                rec["why"] = WHY_SRC["novalue" if v is None else "nohead"]
                rec["counts"] = {**{k: 0 for k in STATUSES}, "byRule": 0, "unmatched": 0}
                continue
            taken.add(v)
            sub = {"table": dst["table"], "items": items}
            if isinstance(rule, dict) and rule.get("pairs"):   # 칸 짝의 대상 키가 이 값 머리를 품고 있으면 같은 조각을 빼고 견준다(1대1 에서 맺은 칸 짝이 그 값에서 듣게)
                cut = lambda k: _cut(k, axis, level) if isinstance(k, str) and under({"key": k}) == v else k   # noqa: E731
                rule = {**rule, "pairs": [{**p, "to": cut(p.get("to"))} if isinstance(p, dict) else p for p in rule["pairs"]]}
        p = plan(s["ex"], sub, rule)
        for x in p["pairs"]:
            d = full[x["to"]]
            pairs.append({**x, "key": d["key"], "label": d["label"], "from": {"table": s.get("table"), "cell": x["from"], **({"doc": s["doc"]} if s.get("doc") else {})},
                          "src": n, "group": labels.get(v, v) if group else None, "value": v if group else None})
        left_s += [{**i, "table": s.get("table"), "src": n} for i in p["unmatched"]["src"]]
        rec["_left"] = {i["cell"]: i["why"] for i in p["unmatched"]["dst"]}
    hit = Counter(x["to"] for x in pairs)
    for x in pairs:
        if hit[x["to"]] > 1:   # 두 원본이 같은 칸 — 어느 것도 넣지 않는다
            x["status"], x["why"] = "clash", WHY_DST["two"]
    order = {i["cell"]: k for k, i in enumerate(dst["items"])}
    pairs.sort(key=lambda x: (order[x["to"]], x["src"]))
    left_d = []
    for i in dst["items"]:
        if i["cell"] in hit:
            continue
        v = under(i) if group else None
        whys = [r["_left"][i["cell"]] for r in info if i["cell"] in r.get("_left", ())]
        why = whys[0] if whys else (WHY_DST["other"] if v is None or (labels and v not in labels) else WHY_DST["nosrc"]) if group else WHY["none"]
        left_d.append({**i, "why": why})

    def tally(xs):
        c = {k: 0 for k in STATUSES}
        for x in xs:
            c[x["status"]] += 1
        return c
    for n, rec in enumerate(info):
        rec.pop("_left", None)
        if "counts" not in rec:
            mine = [x for x in pairs if x["src"] == n]
            rec["counts"] = {**tally(mine), "byRule": sum(1 for x in mine if x["by"] != "key"), "unmatched": sum(1 for i in left_s if i["src"] == n)}
    if group:
        groups = [{"value": v["part"], "label": v["label"], "tables": [r["table"] for r in info if r["value"] == v["part"] and "why" not in r],
                   "counts": tally([x for x in pairs if x["value"] == v["part"]])} for v in (group.get("values") or ()) if v["part"] in taken]
    else:
        groups = [{"table": r["table"], "label": None, "tables": [r["table"]], "counts": tally([x for x in pairs if x["src"] == n])} for n, r in enumerate(info)]
    return {"pairs": pairs, "unmatched": {"src": left_s, "dst": left_d},
            "counts": {**tally(pairs), "check": sum(1 for x in pairs if x["status"] == "fill" and x.get("check")),
                       "unmatched": len(left_s) + len(left_d), "unmatchedSrc": len(left_s), "unmatchedDst": len(left_d), "byRule": sum(1 for x in pairs if x["by"] != "key")},
            "groups": groups, "sources": info}


# ---- 더해서 넣기(다대일 — 셀 값 합산: spec_테이블매니저 ② §7 「키-값 추출과 매핑」 의 「더해서 넣기」) ------------------------------------------------------------------
# 원본 표 여럿의 **같은 키** 칸의 수를 더해 받을 표의 그 키 칸에 넣는다(기관이 갈리지 않은 공통 숫자 표 — 기관마다 낸 값을 같은 칸에 더한다). 합계 줄(수식으로 셈하는 칸)에는 넣지 않는다 —
# 표의 수식이 셈한다. 원본 가운데 일부만 값이 있으면 있는 것만 더하되 「확인」 을 붙인다(화면이 처음에는 고르지 않는다). 수가 아닌 글이 든 칸은 더하지 않는다(짐작하지 않는다).

SUM_STATUSES = STATUSES
WHY_SUM = {"nonnum": "원본에 수가 아닌 글이 있어 더하지 않습니다", "emptySrc": "원본 칸이 모두 비어 있습니다", "clash": "칸에 다른 값이 있어 덮지 않습니다",
           "calc": "수식으로 셈하는 칸 — 넣은 뒤 다시 계산합니다"}
_NUM_TAIL = re.compile(r"^[+\-−▲△]?\s*\(?\s*[\d,]+(?:\.\d+)?\s*\)?\s*(.*)$")   # 수 글의 뒤 글(「%」 · 「천원」 · 「명」)


def _read_num(it):
    """항목의 글을 수로 → ("num", 읽은 것 {num, dec?, dash?, pct?}) | ("empty", None)(빈 칸 · 자리표시) | ("text", None)(수가 아닌 글). 읽기는 `heading_calc.parse_num`(쉼표 · 단위 · 「-」 = 0)."""
    if it["empty"] or not it["text"].strip():
        return "empty", None
    got = HC.parse_num(it["text"])
    if got.get("num") is not None:
        return "num", got
    return ("empty" if got.get("placeholder") else "text"), None


WHY_UNIT = {"differ": "단위가 다릅니다(%s)", "mixed": "단위를 적지 않은 수가 섞여 있습니다"}
DEC_MAX = 6   # 넣을 글의 소수 자리를 늘려 보는 끝


def _tail(text):
    """수 글의 뒤 글(단위) — 「1,200천원」 → 「천원」 · 「12.5 %」 → 「%」 · 없으면 ""(빈칸은 뺀다 · 「％」 는 「%」). 수 글이 아니면 ""."""
    m = _NUM_TAIL.match(HC.clean(text or "").strip())
    return re.sub(r"\s+", "", m.group(1)).replace("％", "%") if m else ""


def _units(nums, shape=""):
    """셈하는 수들의 단위 — nums = [(읽은 것, 글)…], shape = 값을 받을 칸의 꼴(자리표시 글 · 다시 계산에서는 그 칸의 지금 글).
    → (넣을 글에 붙일 뒤 글 | None(뒤 글이 서로 달라 셈하지 않는다 — 환산하지 않는다), 나온 뒤 글들(적은 차례), 뒤 글을 적은 수와 안 적은 수가 섞였는가).
    「-」(0)는 단위를 따지지 않는다. 받을 칸의 꼴에 적힌 뒤 글도 같아야 한다(「00%」 자리에 「천원」 의 합을 넣지 않는다)."""
    tails = [_tail(t) for g, t in nums if not g.get("dash")]
    kinds = list(dict.fromkeys(t for t in tails if t))
    mixed = bool(kinds) and any(not t for t in tails)
    own = _tail(shape)
    every = list(dict.fromkeys([*kinds, *([own] if own else [])]))
    return (None if len(every) > 1 else every[0] if every else ""), every, mixed


def _fmt(value, dec, comma, tail="", strip=False):
    """수를 글로 — 소수 dec 자리 · 천 단위 쉼표 · 뒤 글. strip = 끝의 0 을 뺀다(꼴을 모르는 비율)."""
    v = round(float(value), dec)
    body = f"{abs(v):,.{dec}f}" if comma else f"{abs(v):.{dec}f}"
    if strip and dec:
        body = body.rstrip("0").rstrip(".")
    return ("-" if v < 0 else "") + body + tail


def _sum_text(nums, was, tail=""):
    """합을 넣을 글로 — nums = [(읽은 것, 원본 글)…](수인 원본만), was = 받을 칸의 지금 글(자리표시), tail = 붙일 뒤 글(`_units` 가 정한 것). → (합, 글).
    소수 자리 = 원본들의 최대 · 천 단위 쉼표 = 원본이나 받을 칸의 자리표시 가운데 쉼표를 쓴 것이 있으면 쓰고, 쉼표 없이 네 자리 넘게 적은 원본이 있으면(「1200」) 안 쓴다 —
    어느 쪽도 아니면(원본이 모두 세 자리 이하라 꼴을 알 수 없음) 쓴다(「500 + 700」 → 「1,200」). 원본이 모두 「-」 면 그 「-」."""
    dec = max((g.get("dec") or 0) for g, _ in nums)
    total = round(sum(g["num"] for g, _ in nums), dec)
    solid = [(g, t) for g, t in nums if not g.get("dash")]
    if not solid:
        return total, nums[0][1].strip()
    comma = any("," in t for _, t in solid) or "," in (was or "") or not any(abs(g["num"]) >= 1000 for g, _ in solid)
    return total, _fmt(total, dec, comma, tail)


def plan_sum(sources, dst, rules=None):
    """여러 원본 표의 **같은 키** 칸의 수를 더해 dst 의 그 키 칸에 넣는 계획(문서는 안 바뀐다).

    sources = [{"ex": 추출, "table": 표 id, "doc"?: 다른 문서 id}], dst = 받을 표의 추출, rules = 매핑 규칙 묶음(원본마다의 목록 또는 하나 | None — 짝은 `plan` 과 같은 길: 꼭 같은 키 · 규칙).
    → {"pairs": [{key, label, to, text: 넣을 글(합), was, status, by, why?, parts: [{table, cell, text, num(, doc)}](그 키의 원본 칸들 — 원본 차례), sum: 합 | None, from: [{table, cell}](도장에 든다),
                 missing?: 값이 없는 원본 수, check?: True}](받을 표의 칸 차례),
       "unmatched": {"src": [항목 + why + table + src…], "dst": [항목 + why…]}, "counts": {fill, same, clash, calc, emptySrc, nonnum, check, unmatched, unmatchedSrc, unmatchedDst, byRule},
       "sources": [{table, (doc,) counts: {pairs, nums, byRule, unmatched}}]}.
    status: `nonnum`(원본에 수가 아닌 글 — 안 넣는다) · `emptySrc`(원본이 모두 빔 · 자리표시) · `same`(받을 칸의 수 = 합) · `calc`(받을 칸이 수식으로 셈하는 칸 — 안 넣는다) ·
    `fill`(받을 칸이 비었고 — 자리표시 포함 — 수인 원본이 하나 이상) · `clash`(받을 칸에 다른 값 · 칸 안 표 · 그림 — 덮지 않는다). 이 차례로 정한다.
    원본 가운데 **일부만** 수가 있으면(빈 칸이거나 그 키의 칸이 없는 원본이 있음) 있는 것만 더하고 missing 과 check 를 붙인다 — 화면이 처음에는 고르지 않는다.
    **단위**: 원본들의 뒤 글이 서로 다르면 더하지 않는다(`nonnum` — 「단위가 다릅니다(천원 · 백만원)」), 뒤 글을 적은 수와 안 적은 수가 섞이면 더하되 check + why. **같음**은 받을 칸의 수가 합과 꼭 같을 때만이다."""
    rules = rules if isinstance(rules, (list, tuple)) else [rules] * len(sources)
    op_fns = [_ops(rules[n] if n < len(rules) else None) for n in range(len(sources))]   # 칸마다 넣는 방식 — 그 칸에 걸린 원본의 묶음 가운데 먼저 정한 것(원본 차례)
    hits, left_s, info = {}, [], []
    for n, s in enumerate(sources):
        cells = {i["cell"]: i for i in s["ex"]["items"]}
        p = plan(s["ex"], dst, rules[n] if n < len(rules) else None)
        for x in p["pairs"]:
            hits.setdefault(x["to"], []).append((n, cells[x["from"]], x["by"]))
        left_s += [{**i, "table": s.get("table"), "src": n} for i in p["unmatched"]["src"]]
        info.append({"table": s.get("table"), **({"doc": s["doc"]} if s.get("doc") else {}),
                     "counts": {"pairs": len(p["pairs"]), "nums": 0, "byRule": p["counts"]["byRule"], "unmatched": len(p["unmatched"]["src"])}, "_left": {i["cell"]: i["why"] for i in p["unmatched"]["dst"]}})
    pairs, left_d = [], []
    counts = {**{k: 0 for k in SUM_STATUSES}, "check": 0}
    for d in dst["items"]:
        got = hits.get(d["cell"])
        if not got:
            whys = [r["_left"][d["cell"]] for r in info if d["cell"] in r["_left"]]
            left_d.append({**d, "why": whys[0] if whys else WHY["none"]})
            continue
        parts, nums, bad = [], [], False
        for n, it, _by in got:
            kind, read = _read_num(it)
            parts.append({"table": sources[n].get("table"), "cell": it["cell"], "text": it["text"], "num": _num(read["num"]) if read else None, **({"doc": sources[n]["doc"]} if sources[n].get("doc") else {})})
            if kind == "num":
                nums.append((read, it["text"]))
                info[n]["counts"]["nums"] += 1
            bad = bad or kind == "text"
        op = next((o for o in (op_fns[n](d["key"]) for n, _, _ in got) if o != "fill"), "fill")
        total, text, why, extra = None, "", "", {}
        if bad:
            status, why = "nonnum", WHY_SUM["nonnum"]
        elif not nums:
            status, why = "emptySrc", WHY_SUM["emptySrc"]
        else:
            tail, kinds, mixed = _units(nums, d["text"] if d["empty"] else "")   # 셈하는 수의 단위 — 서로 다르면 더하지 않는다(더하기 · 빼기는 받을 칸의 수까지 `_calc_put` 이 다시 본다)
            total, text = _sum_text(nums, d["text"] if d["empty"] else "", tail or "")
            now = None if d["empty"] else HC.parse_num(d["text"]).get("num")
            if tail is None and op not in ("add", "sub"):
                total, text, status, why = None, "", "nonnum", WHY_UNIT["differ"] % " · ".join(kinds)
            elif op in ("add", "sub"):   # 방식은 원본들의 합에 걸린다 — 받을 칸의 수(비었으면 0) ± 합
                kd, rd = _num_of(d["text"], d["empty"])
                if d["calc"]:
                    status, why = "calc", WHY_SUM["calc"]
                elif d.get("obj"):
                    status, why = "clash", WHY["obj"]
                elif kd == "text":
                    status, text, why = "nonnum", "", WHY_OP["dstText"]
                else:
                    put = _calc_put(op, nums, d, rd)
                    status, text, extra = put["status"], put["text"], {k: put[k] for k in ("expr", "check", "had") if k in put}
                    why = put.get("why") or ""
                    total = total if tail is not None else None
            elif now is not None and abs(now - total) <= 1e-9 * max(1.0, abs(total)):   # 「같음」 은 수가 꼭 같을 때만(검산의 허용 오차를 쓰지 않는다 — 「40 + 60」 과 「100.4」 는 겹침)
                status = "same"
            elif d["calc"]:
                status, why = "calc", WHY_SUM["calc"]
            elif d.get("obj"):
                status, why = "clash", WHY["obj"]
            elif d["empty"]:
                status = "fill"
            elif op == "replace":   # 덮어쓰기 — 받을 칸에 다른 값이 있어도 합으로 바꾼다(확인)
                status, extra = "fill", {"check": True, "had": True}
            else:
                status, why = "clash", WHY_SUM["clash"]
            if status == "fill" and mixed and op not in ("add", "sub"):   # 뒤 글을 적은 수와 안 적은 수가 섞임 — 셈하되 확인
                extra, why = {**extra, "check": True}, WHY_UNIT["mixed"]
        by = next((b for _, _, b in got if b != "key"), "key")
        pair = {"key": d["key"], "label": d["label"], "to": d["cell"], "text": text, "was": d["text"], "status": status, "by": by, "op": op, **extra, **({"why": why} if why else {}),
                "parts": parts, "sum": _num(total), "from": [{"table": x["table"], "cell": x["cell"], **({"doc": x["doc"]} if x.get("doc") else {})} for x in parts]}
        if nums and len(nums) < len(sources) and not bad:
            pair["missing"], pair["check"] = len(sources) - len(nums), True
        counts["check"] += status == "fill" and bool(pair.get("check"))
        counts[status] += 1
        pairs.append(pair)
    for r in info:
        r.pop("_left")
    return {"pairs": pairs, "unmatched": {"src": left_s, "dst": left_d},
            "counts": {**counts, "unmatched": len(left_s) + len(left_d), "unmatchedSrc": len(left_s), "unmatchedDst": len(left_d), "byRule": sum(1 for x in pairs if x["by"] != "key")},
            "sources": info}


# ---- 나눠 넣기(일대다: 같은 사양서 ② §7 의 「나눠 넣기」) — 「구분 기준으로 묶어 넣기」 의 반대 방향 ---------------------------------------------------------------------
# 구분 기준의 값 머리가 **있는** 표 하나의 값을, 그 기준의 값마다 받을 표 여럿(그 머리글이 없는 표 — 한 기관 · 한 차년도의 표)에 나눠 넣는다. 값이 정해지지 않은 받을 표에는 넣지 않는다.

WHY_SPLIT = {"novalue": "어느 값의 것인지 정해지지 않았습니다 — 값을 고르세요", "nohead": "원본 표에 그 값의 머리글이 없습니다", "other": "이 기준의 머리글 아래 칸이 아닙니다", "notgt": "이 값의 받을 표가 없습니다"}


def plan_split(src, targets, group, rules=None):
    """원본 표(src — 기준의 값 머리가 있는 표)의 값을 받을 표 여럿에 나눠 넣는 계획(문서는 안 바뀐다).

    src = 원본 표의 추출, targets = [{"ex": 추출, "value": 그 받을 표가 어느 값의 것인가(값 머리의 키 조각) | None, "table": 표 id}], group = `bases(원본 표)` 의 한 항목({basis, on, level, values}),
    rules = 매핑 규칙 묶음 — 받을 표마다의 목록([묶음 | None …] — 원본 타입 → 받을 표 타입 짝마다) 또는 묶음 하나 | None.
    받을 표마다: 원본 항목 가운데 **그 값 머리 아래의 칸**만 보고, 원본 키에서 그 조각을 뺀 키와 받을 표의 키가 꼭 같을 때 짝짓는다(`plan` — 칸 짝 규칙의 원본 키가 그 값 머리를 품고 있으면 같은 조각을 빼고 견준다).
    value 가 None 인 받을 표는 짝짓지 않는다. 상태 · 넣는 조건은 1대1 과 같다(빈 칸만 · 겹치면 안 덮음 · 수식 칸 제외).
    → {"pairs": [`plan` 의 짝 + {from: 원본 칸, fromRef, to: {table, cell}, ref: 받을 칸의 A1, tgt: 받을 표 차례, group: 값의 머리 글, value: 값의 키 조각}](받을 표 차례 · 그 표의 칸 차례),
       "unmatched": {"src": [원본 항목 + why…], "dst": [받을 표의 항목 + why + table + tgt…]}, "counts": {fill, same, clash, calc, emptySrc, unmatched, unmatchedSrc, unmatchedDst, byRule},
       "groups": [{table, value, label, counts}](받을 표마다), "targets": [{table, value, valueLabel, why?, counts: {fill, …, byRule, unmatched}}]}."""
    axis, level = (0 if group["on"] == "row" else 1), group["level"]
    labels = {v["part"]: v["label"] for v in group.get("values") or ()}
    rules = rules if isinstance(rules, (list, tuple)) else [rules] * len(targets)
    refs = {i["cell"]: i["ref"] for i in src["items"]}

    def under(it):   # 그 원본 항목이 놓인 값 조각 | None
        ps = key_parts(it["key"])[axis] if it["key"] is not None else ()
        return ps[level] if level < len(ps) else None

    def tally(xs):
        c = {k: 0 for k in STATUSES}
        for x in xs:
            c[x["status"]] += 1
        return c

    pairs, left_d, info, used, why_s, taken = [], [], [], set(), {}, set()
    for n, t in enumerate(targets):
        v = t.get("value")
        rec = {"table": t.get("table"), "value": v, "valueLabel": labels.get(v, v)}
        info.append(rec)
        items = [{**it, "key": _cut(it["key"], axis, level)} for it in src["items"] if v is not None and under(it) == v]
        if v is None or not items:
            rec["why"] = WHY_SPLIT["novalue" if v is None else "nohead"]
            rec["counts"] = {**{k: 0 for k in STATUSES}, "byRule": 0, "unmatched": 0}
            continue
        taken.add(v)
        rule = rules[n] if n < len(rules) else None
        if isinstance(rule, dict) and rule.get("pairs"):   # 칸 짝의 원본 키가 이 값 머리를 품고 있으면 같은 조각을 빼고 견준다
            cut = lambda k: _cut(k, axis, level) if isinstance(k, str) and under({"key": k}) == v else k   # noqa: E731
            rule = {**rule, "pairs": [{**x, "from": cut(x.get("from"))} if isinstance(x, dict) else x for x in rule["pairs"]]}
        p = plan({"table": src["table"], "items": items}, t["ex"], rule)
        dref = {i["cell"]: i["ref"] for i in t["ex"]["items"]}
        mine = [{**x, "fromRef": refs[x["from"]], "to": {"table": t.get("table"), "cell": x["to"]}, "ref": dref[x["to"]], "tgt": n, "group": labels.get(v, v), "value": v} for x in p["pairs"]]
        pairs += mine
        used.update(x["from"] for x in mine)
        for i in p["unmatched"]["src"]:
            why_s.setdefault(i["cell"], i["why"])
        left_d += [{**i, "table": t.get("table"), "tgt": n} for i in p["unmatched"]["dst"]]
        rec["counts"] = {**tally(mine), "byRule": sum(1 for x in mine if x["by"] != "key"), "unmatched": len(p["unmatched"]["dst"])}
    left_s = []
    for i in src["items"]:
        if i["cell"] in used:
            continue
        v = under(i)
        why = why_s.get(i["cell"]) or (WHY_SPLIT["other"] if v is None or (labels and v not in labels) else WHY_SPLIT["notgt"] if v not in taken else WHY["none"])
        left_s.append({**i, "why": why})
    groups = [{"table": r["table"], "value": r["value"], "label": r["valueLabel"], "counts": tally([x for x in pairs if x["tgt"] == n])} for n, r in enumerate(info) if "why" not in r]
    return {"pairs": pairs, "unmatched": {"src": left_s, "dst": left_d},
            "counts": {**tally(pairs), "check": sum(1 for x in pairs if x["status"] == "fill" and x.get("check")),
                       "unmatched": len(left_s) + len(left_d), "unmatchedSrc": len(left_s), "unmatchedDst": len(left_d), "byRule": sum(1 for x in pairs if x["by"] != "key")},
            "groups": groups, "targets": info}


# ---- 계산 칸 다시 계산(같은 사양서 ② §7 의 「계산 칸 다시 계산」) ------------------------------------------------------------------------------------------------
# 2026-11-19 사용자 "어떤건 더해서 합이되는 필드가 있고 어떤건 다른걸 덮어 씌우면 합하거나 빼는게 있고 하잖아" → 답 「둘 다」. 한글 문서에는 살아 있는 수식이 없어, 값을 넣거나 덮은 뒤
# 합계 · 소계 · 코드 식 · 비율 칸(표 의미의 수식이 걸린 칸 — `heading_calc.annotate`)은 누가 다시 채워야 한다. 여기서는 그 수식대로 다시 셈해 넣을 글을 만든다(문서는 안 바뀐다).

RECALC_STATUSES = ("missing", "mismatch", "ok", "incomplete", "conflict")
RECALC_PASSES = 5   # 여러 겹(소계 → 합계)을 푸는 횟수
WHY_RECALC = {"shape": "계산한 값을 이 칸의 꼴로 적을 수 없습니다", "blank": "셈할 칸이 모두 비어 있습니다", "div": "셈하지 못했습니다(0 으로 나눔 · 못 읽는 식)", "text": "지금 글이 수가 아닙니다 — 계산한 값으로 바꾸려면 고르세요",
              "mismatch": "지금 값이 계산한 값과 다릅니다 — 맞으면 고르세요", "conflict": "이 칸의 두 수식(가로 · 세로)이 서로 다른 값을 냅니다 — 넣지 않습니다", "obj": "칸 안에 표 · 그림이 있어 넣지 않습니다"}
_DEC_IN = re.compile(r"\.(\d+)")
_COMMA_IN = re.compile(r"\d,\d{3}")


def _like_text(value, like):
    """계산값을 넣을 글로 — 그 칸의 지금 글 · 자리표시(like)의 꼴을 따른다(엑셀식 보기의 「문서에 반영」 과 같은 규칙): 소수 자리는 like 의 것, 없으면 정수는 0 · 아니면 2자리까지(끝의 0 은 뺀다) ·
    천 단위 쉼표는 like 에 쉼표가 있거나 like 가 수가 아닌데(빈 칸 · 자리표시) 1,000 이상일 때 · 끝의 % 는 like 가 % 로 끝나면."""
    like = HC.clean(like or "").strip()
    m = _DEC_IN.search(like)
    dec = len(m.group(1)) if m else (0 if float(value).is_integer() else 2)
    v = round(float(value), dec)
    body = f"{abs(v):.{dec}f}"
    if dec and not m:
        body = body.rstrip("0").rstrip(".")
    if _COMMA_IN.search(like) or (HC.parse_num(like).get("num") is None and abs(v) >= 1000):
        whole, dot, frac = body.partition(".")
        body = f"{int(whole):,}{dot}{frac}"
    return ("-" if v < 0 else "") + body + ("%" if like.endswith(("%", "％")) else "")


def _recalc_text(rec, cells, base):
    """수식 하나가 셈한 값을 넣을 글로 → (글, 붙일 것 {check?, why?}) | (None, 못 적는 까닭 글). **넣을 글은 계산한 수와 같은 수여야 한다**(같은 사양서 ② §7).
    더하고 빼는 식(합 · 곱셈 · 나눗셈이 없는 코드 식): 소수 자리 = 셈에 든 칸들 · 이 칸의 글 가운데 가장 긴 것, 쉼표 = 「더해서 넣기」 와 같은 규칙, 뒤 글 = `_units`(서로 다르면 안 넣음 · 섞이면 확인) —
    그렇게 적은 글을 다시 읽은 수가 계산한 수와 다르면 같아질 때까지 자리를 늘린다(`DEC_MAX` 까지 — 안 되면 못 적음).
    비율 · 나눗셈 · 곱셈이 든 식: 이 칸의 꼴(소수 자리 — 없으면 정수는 0 · 아니면 2자리까지 · 뒤 글은 「%」 만)대로 반올림한다 — 반올림해 0 이 되어 버릴 때만 자리를 늘린다."""
    value, like = rec["expected"], HC.clean(base["textFull"]).strip()
    nums = [({"num": c["num"], "dec": c.get("dec") or 0, **({"dash": True} if c.get("dash") else {})}, c["textFull"]) for c in (cells[o] for o in rec.get("operands") or () if o in cells) if c.get("num") is not None]
    m, f = _DEC_IN.search(like), rec.get("formula") or ""
    additive, extra = rec.get("kind") == "sum" or (rec.get("kind") == "expr" and "*" not in f and "/" not in f), {}
    if additive:
        tail, kinds, mixed = _units(nums, like)
        if tail is None:
            return None, WHY_UNIT["differ"] % " · ".join(kinds)
        if mixed:
            extra = {"check": True, "why": WHY_UNIT["mixed"]}
        solid = [(g, t) for g, t in nums if not g.get("dash")]
        dec = max([g.get("dec") or 0 for g, _ in nums] + [len(m.group(1)) if m else 0])
        comma = any("," in t for _, t in solid) or "," in like or not any(abs(g["num"]) >= 1000 for g, _ in solid)
    else:
        tail = "%" if like.endswith(("%", "％")) else ""
        dec = len(m.group(1)) if m else (0 if float(value).is_integer() else 2)
        comma = bool(_COMMA_IN.search(like)) or (HC.parse_num(like).get("num") is None and abs(value) >= 1000)
    for d in range(min(dec, DEC_MAX), DEC_MAX + 1):
        text = _fmt(value, d, comma, tail, strip=not additive and not m)
        got = HC.parse_num(text).get("num")
        if got is None:
            break
        if abs(got - value) <= 1e-9 * max(1.0, abs(value)) if additive else not (got == 0 and abs(value) > 0):
            return text, extra
    return None, WHY_RECALC["shape"]


def _recalc_run(table, subs, filled):
    """채운 값(filled = {칸 id: 글})을 메모리의 표 사본에 넣고 표 의미를 다시 셈한다 → (칸 id → 칸, 수식 목록). 문서 · 받은 표는 안 건드린다."""
    tb = {**table, "cells": [dict(x) for x in table["cells"]]}
    for x in tb["cells"]:
        if x["id"] in filled:
            x["textFull"] = x["text"] = filled[x["id"]]
            x["kinds"] = {**(x.get("kinds") or {}), "placeholder": False, "data": True}   # 자리표시였던 칸 — 이제 값이 든 칸으로 읽게
    sem = HC.annotate(tb, [dict(b) for b in subs], None)
    return {x["id"]: x for x in tb["cells"]}, sem["formulas"]


def _recalc_cell(b, recs, cells):
    """수식 칸 하나의 판정 — b = 지금 문서의 그 칸, recs = 이번 셈의 그 칸 수식들(축마다 하나), cells = 이번 셈의 칸들(채운 값이 든 것). `_ops` = 그 값을 낸 수식이 셈에 쓴 칸(기대는 칸을 따질 때 쓴다 — `recalc`)."""
    out = {"cell": b["id"], "ref": HC.ref(b), "now": " ".join(HC.clean(b["textFull"]).split())}
    done = [r for r in recs if r.get("expected") is not None]
    if not done:
        r = next((x for x in recs if x.get("excel")), recs[0])
        empty = [cells[o] for o in r.get("operands") or () if o in cells and cells[o].get("num") is None]
        why = (WHY_RECALC["blank"] if r.get("status") == "blank" else f"셈할 칸 가운데 빈 칸이 있습니다: {' · '.join(HC.ref(c) for c in empty[:8])}{' …' if len(empty) > 8 else ''}") if empty else WHY_RECALC["div"]
        return {**out, "formula": r["formula"], "note": r.get("note") or "", "value": None, "text": "", "status": "incomplete", "why": why, "_ops": []}
    made = [_recalc_text(r, cells, b) for r in done]   # [(글 | None, 붙일 것 | 못 적는 까닭)]
    if any(abs(r["expected"] - done[0]["expected"]) > 1e-6 and (t is None or t != made[0][0]) for r, (t, _x) in zip(done[1:], made[1:])):
        r = done[0]
        return {**out, "formula": r["formula"], "note": r.get("note") or "", "value": None, "text": "", "status": "conflict", "why": WHY_RECALC["conflict"],
                "both": [{"axis": x.get("axis"), "formula": x["formula"], "note": x.get("note") or "", "value": _num(x["expected"]), "text": t if t is not None else _like_text(x["expected"], b["textFull"])}
                         for x, (t, _x) in zip(done, made)], "_ops": []}
    k = next((i for i, x in enumerate(done) if x.get("excel")), 0)
    r, (text, extra) = done[k], made[k]
    if text is None:   # 단위가 다르거나 이 칸의 꼴로 적을 수 없다 — 넣지 않는다
        return {**out, "formula": r["formula"], "note": r.get("note") or "", "value": _num(r["expected"]), "text": "", "status": "incomplete", "why": extra, "_ops": []}
    out.update(formula=r["formula"], note=r.get("note") or "", value=_num(r["expected"]), text=text, _ops=[o for o in r.get("operands") or ()])
    now = HC.parse_num(b["textFull"], b.get("kinds"))
    if now.get("num") is None:
        if now.get("text"):
            return {**out, "status": "mismatch", "check": True, "why": WHY_RECALC["text"]}
        return {**out, "status": "missing", **extra}
    tol = 0.5 * 10 ** (-int(now.get("dec") or 0)) + (0.05 if r.get("kind") == "ratio" or "/" in r["formula"] else 0.0) + 1e-9
    if abs(now["num"] - r["expected"]) <= tol or same_text(text, b["textFull"]):
        return {**out, "status": "ok"}
    return {**out, "status": "mismatch", "check": True, "why": " · ".join(x for x in (WHY_RECALC["mismatch"], extra.get("why")) if x)}


def recalc(table, sem, subs=None, objs=()):
    """표의 계산 칸(수식이 걸린 칸)을 수식대로 다시 셈한 계획(문서는 안 바뀐다) → {"items": [칸마다…](표의 칸 차례), "counts": {missing, mismatch, ok, incomplete, conflict}, "passes": 채워 가며 다시 셈한 횟수,
    "more": 그 횟수를 다 쓰고도 더 풀 겹이 남았는가}.

    table · sem · subs = `table_manager.judge()` 의 표 · 표 의미(`sem["formulas"]` — `heading_calc` 의 수식: cell · formula · operands · expected · status · axis · excel · note) · 띠.
    objs = 칸 안에 표 · 그림이 있는 칸 id(쓰지 않는다). 항목 = {cell, ref, formula(엑셀 수식 글), note(근거), now(지금 글), value(계산한 수 | None), text(넣을 글), status, why?, check?, needs?, both?}.
    status: `missing`(칸이 비었고 — 자리표시 포함 — 계산됨: 넣을 수 있음) · `mismatch`(지금 값과 계산이 다름 · 지금 글이 수가 아님 — check: 화면이 처음에는 안 고른다) · `ok`(같음) ·
    `incomplete`(셈할 칸 가운데 빈 것이 있음 · 셈하지 못함 — 안 넣음) · `conflict`(그 칸의 두 수식(가로 · 세로)이 서로 다른 값 — 안 넣고 both 에 둘 다).
    한 칸에 수식이 둘이면: 둘 다 셈되고 같으면 그 값(엑셀 수식 쪽의 글) · 다르면 conflict · 하나만 셈되면 그 하나.
    **여러 겹**(소계 → 합계): 비어 있어 계산된 칸(missing)의 값을 메모리의 표 사본에 넣고 표 의미를 다시 셈한다(`heading_calc.annotate` — subs 가 있어야 한다, 없으면 한 겹만) — 더 채울 것이 없을 때까지,
    `RECALC_PASSES` 번까지. 지금 값이 있는 칸(다름 포함)은 그 값 그대로 윗겹의 셈에 든다(다른 값을 넣기로 고르면 넣은 뒤 다시 읽어 윗겹이 「다름」 으로 나온다).
    needs = 그 값이 기대는 **이번에 채울 칸**(거쳐서 기대는 것까지) — 그 칸들을 같이 넣을 때만 이 값이 맞다(반영 끝점이 본다). 한 번 conflict 로 본 칸은 채우지 않는다(되돌아가며 흔들리지 않게).
    **기대는 칸을 모두 따진다**: 기대는 수식 칸이 ⓐ missing → needs ⓑ mismatch(지금 값이 계산과 다름) → 이 값은 그 칸의 **지금 값으로** 셈한 것이다: stale = [그 칸…] + check + why —
    그 칸을 이번에 같이 고치면 이 칸은 넣지 않는다(반영 끝점이 건너뛴다 · 넣은 뒤 다시 읽으면 새 값으로 나온다) ⓒ conflict · incomplete → 이 칸도 incomplete(「기대는 칸 B4 를 셈하지 못했습니다」).
    따지는 것은 그 값을 낸 수식(엑셀 수식 쪽)이 셈에 쓴 칸이고, 겹겹이 따라간다(소계 → 합계 → 총계). check 가 붙은 missing(단위를 적지 않은 수가 섞임 · stale)도 화면이 처음에는 안 고른다."""
    base = {x["id"]: x for x in table["cells"]}
    first = [r for r in (sem or {}).get("formulas") or () if r.get("cell") in base]
    counts = {k: 0 for k in RECALC_STATUSES}
    if not first:
        return {"items": [], "counts": counts, "passes": 0, "more": False}
    objs = set(objs or ())
    filled, blocked, passes, settled = {}, {}, 0, False
    cells, forms = base, first
    for n in range(RECALC_PASSES + 1):
        by = {}
        for r in forms:
            by.setdefault(r["cell"], []).append(r)
        got = {c: _recalc_cell(base[c], rs, cells) for c, rs in by.items() if c in base}
        for c, it in got.items():
            if it["status"] == "conflict":
                blocked.setdefault(c, it)
        fresh = {c: it["text"] for c, it in got.items() if it["status"] == "missing" and c not in blocked and c not in objs}
        moved = {c for c in set(fresh) | set(filled) if fresh.get(c) != filled.get(c)}   # 이번에 새로 채울 칸 · 물러난 칸 · 값이 달라진 칸
        if subs is None or not moved & {o for r in forms for o in r.get("operands") or ()}:   # 그 칸에 기대는 수식이 없으면 더 셈할 것이 없다
            settled = True
            break
        if n == RECALC_PASSES:   # 더 풀 겹이 남았다 — 넣은 뒤 다시 계산하면 이어서 풀린다
            break
        filled = fresh
        cells, forms = _recalc_run(table, subs, filled)
        passes = n + 1
    got.update(blocked)
    order = {x["id"]: i for i, x in enumerate(table["cells"])}
    uses = {c: it.pop("_ops", []) for c, it in got.items()}   # 그 값을 낸 수식이 셈에 쓴 칸
    for c in objs & set(got):
        if got[c]["status"] in ("missing", "mismatch"):
            got[c] = {**{k: v for k, v in got[c].items() if k != "check"}, "status": "incomplete", "why": WHY_RECALC["obj"]}
    seen = set()

    def settle(c, path=()):
        """기대는 칸을 모두 따진다 — 기대는 수식 칸이 이번에 채울 칸이면 needs, 지금 값이 계산과 다른 칸이면 stale(+ check), 셈하지 못한 칸이면 이 칸도 못 센다. 겹겹이(소계 → 합계 → 총계)."""
        if c in seen or c in path:
            return
        it = got[c]
        if it["status"] in ("missing", "mismatch"):
            needs, stale = set(), set()
            for o in uses.get(c) or ():
                if o not in got:   # 값 칸 — 수식 칸이 아니다
                    continue
                settle(o, (*path, c))
                dep = got[o]
                if dep["status"] in ("conflict", "incomplete"):
                    got[c] = {k: v for k, v in it.items() if k not in ("check", "both")} | {"value": None, "text": "", "status": "incomplete", "why": f"기대는 칸 {dep['ref']} 를 셈하지 못했습니다"}
                    seen.add(c)
                    return
                if dep["status"] == "mismatch":
                    stale.add(o)
                elif dep["status"] == "missing":
                    needs |= {o, *(dep.get("needs") or ())}
                    stale |= set(dep.get("stale") or ())
            if needs:
                it["needs"] = sorted(needs, key=order.get)
            if stale:
                it["stale"] = sorted(stale, key=order.get)
                refs, nows = " · ".join(got[o]["ref"] for o in it["stale"]), " · ".join(got[o]["now"] for o in it["stale"])
                why = f"기대는 칸 {refs} 의 지금 값({nows})으로 셈했습니다 — {refs} 는 계산과 다릅니다"
                it["check"], it["why"] = True, " · ".join(x for x in (it.get("why"), why) if x)
        seen.add(c)

    for c in sorted(got, key=order.get):
        settle(c)
    items = []
    for c in sorted(got, key=order.get):
        counts[got[c]["status"]] += 1
        items.append(got[c])
    return {"items": items, "counts": counts, "passes": passes, "more": not settled}


def recalc_sig(item, mark=None):
    """다시 계산한 칸의 도장 — 칸 · 넣을 글 · 지금 글 · 기대는 칸(needs · stale) · 수식의 해시. 계획을 본 뒤 어느 하나라도 바뀌면 달라진다(반영 때 다시 세운 계획의 것과 견준다)."""
    src = json.dumps([item["cell"], item.get("text"), item.get("now"), item.get("needs") or [], item.get("stale") or [], item.get("formula"), *([mark] if mark is not None else [])],
                     ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha1(src.encode("utf-8")).hexdigest()[:12]
