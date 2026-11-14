"""병합 — 넘친 개요 레벨(spec_병합 ② §5-5 — 이관 · 취합 자동 넣기 · 끌어 넣기 공통). 2026-11-13 사용자 "추가되는 쪽의 개요 레벨이 더 크다면 기존 목적문서에서 큰 부분에 대해서는
덮는 형식으로 개요레벨이 사용되고, 덮은 템플릿으로 사용할지 템플릿을 수정할지, 다른 템플릿을 선택할 수 있게". 스크립트만(LLM 없음).

넣는 개요 줄의 목적 레벨이 자리 템플릿의 길이 K 를 넘으면(merge_convert 의 tooDeep) 그 줄들은 **사례**(자리 템플릿 앵커 × 원본 사슬의 넘친 꼬리 — 열쇠는 merge_convert.plan 이 낸다)로 묶인다.
사례마다 사람이 고른다: `cover`(덮은 템플릿 그대로 = 원본 모양 그대로 — 기본) · `edit`(넘친 레벨마다 레터·본보기·앞 공백) · `template`(목적 문서의 다른 템플릿 — 시작 레벨부터 차례로).

- **저장**(목적 작업마다): `load(wid)` → {"version", "cases": {사례 열쇠: 선택}} · `put(wid, key, choice | None)` — 작업 폴더 `merge_over.json`(저장이 꺼져 있으면 메모리). 바뀔 때마다 version +1.
  선택 = {"mode", "levels": [{letter | None, like: {template, level} | None, lead | None} | None …](edit), "template": {anchor→template, level} | None(template), "at"}.
- `templates(to_graph, to_doc=None)` = 본보기·「다른 템플릿」 의 후보: 목적 문서 2단계 그래프의 **본문** 템플릿 [{anchor, no, kind, chain, levels[{level, key, letter(대표 줄의 실제 레터), text, rep, ok}]}].
  ok = 본보기로 쓸 수 있는 레벨(괄호 줄이 아니고 · 대표 줄이 개요 줄 하나뿐인 문단이고 · to_doc 을 주면 지금 문서에서 첫머리에 그 레터가 있음).
- `validate(body, tpls=None)` = PUT 바디 → 저장할 선택(잘못되면 ValueError — 사람에게 보일 글). `resolve(cases, to_graph)` = 저장한 선택 → `merge_convert.plan(over=)` 의 {사례 열쇠: [레벨 지정 | None …]}
  (레벨 지정 = {like: 본보기 문단 id, likeLetter, letter, lead, numbered, missing}). 본보기가 지금 그래프에 없으면 like 가 「?…」(merge_convert 가 noLike 로 둔다).
- `collect(overs)` = 넣기 하나하나의 `summary.over`(+ 자리)를 사례마다 모음 · `view(cases, store, to_graph, to_doc)` = 화면용 `over{version, cases[…], templates[…]}`(레벨마다 넣을 레터·본보기·`clash`·`missing`).
  `record_cases(records, to_doc)` = 넣은 줄의 기록에서 읽은 사례(이미 다 넣어 계획에 넘친 줄이 없어도 보이게) · `merged` = 둘을 열쇠로 합침 · `plan_view(cases, records, store, to_graph, to_doc)` = 넣기 계획 응답에 싣는 것(위 + `records{lines, cases}`).
  `preview(to_doc, from_doc, plan)` = 넣기 하나의 변환 미리보기 수 {converted, over, kept} · `fill_preview(to, frm, fill, specs)` = 이관 넣기 계획의 항목마다 미리보기 + 사례.
- `refit(to_doc, records, specs, only=None)` = **넣은 뒤 다시 맞추기**: 반영 때 남긴 넘친 줄 기록(merge_convert.apply 의 lines — {id, over, was, letter, parent, pl, orig{prefix, attrs}})과 지금 선택만으로
  넣은 줄의 접두·모양을 다시 입힌다(원본 문서·계획 없이). 지정이 없는 레벨은 `orig` 로 원본 모양을 되살린다. 문서에 없는 줄(gone) · 첫머리가 기록한 레터로 시작하지 않는 줄(edited — 사람이 고침)은 건너뛴다.
  → {"lines": 바꾼 줄 수, "kept": {까닭: n}, "ids", "records": 고친 기록(입력과 같은 차례)}. 트랜잭션·저장은 부르는 쪽(merge_over_api).
ponytail: 앞 공백 지정은 글자만 바꾼다(문단 여백·내어쓰기는 그대로) · 레터가 번호형인지는 글자로 가른다(`numbered` — 로마자 한 글자와 기호는 기호형)."""
import copy
import threading
import time
from collections import Counter

from app import merge_convert as MC
from app import works
from app.outline_edit import NUM_CLASSES, _NUM_RE, first, is_numbered, numbers_of, prefix_of, succ

MODES = ("cover", "edit", "template")
LEVELS_MAX, LETTER_MAX, LEAD_MAX, TEXT_LEN = 12, 12, 40, 24
FILE = "merge_over.json"
WHY = {"gone": "넣은 줄이 지금 문서에 없음", "edited": "첫머리가 바뀐 줄(사람이 고침)", "noLike": "본보기 줄이 지금 문서에 없음", "numEnd": "번호 열이 끝남",
       "marker": "형광펜·변경 추적 표지가 든 줄"}   # 다시 맞추기가 건너뛴 까닭 — 화면에 보일 글
_LOCK = threading.Lock()
_MEM = {}   # 작업 저장이 꺼졌을 때의 merge_over.json
_VARIANT = {**dict.fromkeys("oㅇ○◦Oｏ", "o"), **dict.fromkeys("-–—−‐", "-"), **dict.fromkeys("·⋅•․ㆍ∙", "·"), **dict.fromkeys("□■", "□"), **dict.fromkeys("△▲", "△")}   # 같은 레터로 보는 변형군(spec_헤딩_추출 ② §0)


# ---- 저장 -----------------------------------------------------------------------------------------------------------

def load(wid):
    """그 작업의 선택 {"version", "cases"} — 없으면 빈 것."""
    d = works.folder(wid)
    data = (works._read_json(d / FILE) if d is not None and (d / FILE).is_file() else _MEM.get(wid)) or {}
    return {"version": int(data.get("version") or 0), "cases": {k: v for k, v in (data.get("cases") or {}).items() if isinstance(v, dict)}}


def put(wid, key, choice):
    """사례 하나의 선택을 적는다(choice None = 지움 — 기본으로) → 고친 {"version", "cases"}."""
    with _LOCK:
        data = load(wid)
        if choice is None:
            data["cases"].pop(key, None)
        else:
            data["cases"][key] = {**choice, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        data["version"] += 1
        d = works.folder(wid)
        if d is not None:
            works._write_json(d / FILE, data)
        else:
            _MEM[wid] = data
        return data


# ---- 레터 글 ---------------------------------------------------------------------------------------------------------

def numbered(letter):
    """레터 글이 번호형인가 — 숫자·원문자·「가.」·「a.」 꼴. 로마자 한 글자(기호 「o」)와 기호는 아니다."""
    t = (letter or "").strip()
    return bool(numbers_of(t)) and not (len(t) == 1 and t.isascii() and t.isalpha())


def shape(letter):
    """레터 글 → 견줄 꼴(2단계의 정규 레터 키와 같은 적기 — 번호는 「N」·「가」·「①」…, 기호는 변형군을 합침). 윗 레벨과 같은 레터인지(clash) 볼 때 쓴다."""
    t = (letter or "").strip()
    if not numbered(t):
        return "".join(_VARIANT.get(c, c) for c in t)

    def head(m):
        tok = m.group()
        return "N" if tok.isascii() and tok.isdigit() else next((k for k, seq in NUM_CLASSES.items() if tok in seq), tok)
    return _NUM_RE.sub(head, t)


# ---- 후보 템플릿 -----------------------------------------------------------------------------------------------------

def _lines(graph):
    """그래프 → ({문단: 그 문단의 첫 개요 노드}, {문단: 개요 노드 수})."""
    by, per = {}, Counter()
    for n in (graph or {}).get("nodes") or ():
        if n.get("template") and n.get("level"):
            by.setdefault(n["para"], n)
            per[n["para"]] += 1
    return by, per


def templates(to_graph, to_doc=None):
    """본보기·「다른 템플릿」 의 후보(모듈 설명) — 목적 문서의 본문 템플릿. 쓸 수 있는 레벨이 하나도 없는 템플릿은 뺀다."""
    by, per = _lines(to_graph)
    out = []
    for t in (to_graph or {}).get("templates") or ():
        anchor = t.get("anchor") or t.get("name") or ""
        if t.get("scope", "body" if str(anchor).startswith("body:") else "") != "body":
            continue   # 표 칸 템플릿은 본문 줄의 본보기가 아니다
        slots = {int(s["level"]): s for s in t.get("slots") or () if s.get("level")}
        levels = []
        for i, key in enumerate(t.get("chain") or (), 1):
            rep = (slots.get(i) or {}).get("rep")
            n = by.get(rep) if rep else None
            letter = (n or {}).get("letter") or ""
            ok = bool(n) and bool(letter.strip()) and not str(key).startswith("[") and n.get("role") == "heading" and per[rep] == 1
            if ok and to_doc is not None:
                el = to_doc._ids.get(rep)
                ok = el is not None and to_doc._attached(el) and bool(prefix_of(to_doc._text(el), letter)[1])   # 지운 문단도 id 표에는 남는다
            levels.append({"level": i, "key": key, "letter": letter.strip(), "text": " ".join(str((n or {}).get("text") or "").split())[:TEXT_LEN], "rep": rep, "ok": ok})
        if any(x["ok"] for x in levels):
            out.append({"anchor": anchor, "no": t.get("no", t.get("id")), "kind": t.get("kind"), "chain": list(t.get("chain") or ()), "levels": levels})
    return out


# ---- 선택: 검증 · 풀기 ------------------------------------------------------------------------------------------------

def _slot(x, what, by):
    if not isinstance(x, dict) or not isinstance(x.get("template"), str) or isinstance(x.get("level"), bool) or not isinstance(x.get("level"), int) or x["level"] < 1:
        raise ValueError(f"{what}: {{template, level}} 꼴이어야 합니다")
    if by is not None:
        lv = (by.get(x["template"]) or {}).get(x["level"])
        if lv is None:
            raise ValueError(f"{what}: 목적 문서에 그 템플릿·레벨이 없습니다")
        if not lv["ok"]:
            raise ValueError(f"{what}: 본보기로 쓸 수 없는 레벨입니다(괄호 줄이거나 본보기 줄이 문서에 없음)")
    return {"template": x["template"], "level": x["level"]}


def validate(body, tpls=None):
    """PUT 바디 → 저장할 선택 {"mode", "levels", "template"}(모듈 설명). tpls = templates() 결과 — 주면 본보기·템플릿이 지금 문서에 있는지도 본다."""
    mode = (body or {}).get("mode")
    if mode not in MODES:
        raise ValueError("mode 는 cover · edit · template 가운데 하나여야 합니다")
    by = None if tpls is None else {t["anchor"]: {x["level"]: x for x in t["levels"]} for t in tpls}
    out = {"mode": mode, "levels": [], "template": None}
    if mode == "template":
        out["template"] = _slot(body.get("template"), "템플릿", by)
    elif mode == "edit":
        levels = body.get("levels")
        if not isinstance(levels, list) or not levels or len(levels) > LEVELS_MAX:
            raise ValueError(f"levels 는 넘친 레벨마다 하나씩(1~{LEVELS_MAX}개)이어야 합니다")
        for i, x in enumerate(levels, 1):
            if x is None:
                out["levels"].append(None)
                continue
            if not isinstance(x, dict):
                raise ValueError(f"넘친 레벨 {i}: 지정은 {{letter, like, lead}} 이어야 합니다")
            letter, lead = x.get("letter"), x.get("lead")
            if letter is not None:
                if not isinstance(letter, str):
                    raise ValueError(f"넘친 레벨 {i}: 레터는 글이어야 합니다")
                letter = letter.strip() or None
                if letter and (len(letter) > LETTER_MAX or any(c.isspace() for c in letter)):
                    raise ValueError(f"넘친 레벨 {i}: 레터는 빈칸 없는 {LETTER_MAX}자 이내의 글이어야 합니다")
            if lead is not None and (isinstance(lead, bool) or not isinstance(lead, int) or not 0 <= lead <= LEAD_MAX):
                raise ValueError(f"넘친 레벨 {i}: 앞 공백은 0~{LEAD_MAX} 칸이어야 합니다")
            like = _slot(x["like"], f"넘친 레벨 {i}의 본보기", by) if x.get("like") is not None else None
            out["levels"].append({"letter": letter, "like": like, "lead": lead} if letter or like or lead is not None else None)   # 아무것도 안 고친 레벨 = 원본 그대로
        if not any(out["levels"]):
            out.update(mode="cover", levels=[])
    return out


def _levels(choice, depth):
    """선택 → 넘친 레벨마다의 지정 [{letter, like{template, level}, lead} | None …]. depth(템플릿 앵커) = 그 템플릿의 레벨 수(「다른 템플릿」 이 차례로 채울 끝)."""
    mode = (choice or {}).get("mode")
    if mode == "edit":
        return [x if isinstance(x, dict) else None for x in choice.get("levels") or ()]
    if mode == "template" and isinstance(choice.get("template"), dict):
        t = choice["template"]
        return [{"letter": None, "like": {"template": t["template"], "level": lv}, "lead": None} for lv in range(int(t["level"]), depth(t["template"]) + 1)]
    return []


def _depths(graph):
    d = {(t.get("anchor") or t.get("name")): len(t.get("chain") or ()) for t in (graph or {}).get("templates") or ()}
    return lambda anchor: d.get(anchor, 0)


def resolve(cases, to_graph):
    """저장한 선택 {사례 열쇠: 선택} → merge_convert.plan(over=) 의 {사례 열쇠: [레벨 지정 | None …]}(모듈 설명). 지정이 하나도 없는 사례(cover)는 싣지 않는다."""
    by, _ = _lines(to_graph)
    reps = {(t.get("anchor") or t.get("name"), int(s["level"])): s.get("rep") for t in (to_graph or {}).get("templates") or () for s in t.get("slots") or () if s.get("level")}
    depth, out = _depths(to_graph), {}
    for key, choice in (cases or {}).items():
        specs = []
        for x in _levels(choice, depth):
            if not x:
                specs.append(None)
                continue
            spec = {"like": None, "likeLetter": None, "letter": x.get("letter") or None, "lead": x.get("lead"), "numbered": False, "missing": False}
            like, n = x.get("like"), None
            if like:
                rep = reps.get((like["template"], like["level"]))
                n = by.get(rep) if rep else None
                if n is None:   # 지금 그래프에 그 본보기가 없다 — merge_convert 가 noLike 로 원본 모양에 둔다
                    spec.update(like=f"?{like['template']}|{like['level']}", missing=True)
                else:
                    spec.update(like=rep, likeLetter=n.get("letter") or "")
            spec["numbered"] = numbered(spec["letter"]) if spec["letter"] else bool(n) and is_numbered(n.get("key"))
            specs.append(spec)
        if any(specs):
            out[key] = specs
    return out


# ---- 계획에 보일 것 ---------------------------------------------------------------------------------------------------

def collect(overs):
    """넣기 하나하나의 넘침 [(merge_convert.plan 의 summary.over | None, 그 자리의 목적 블록 id | None)] → 사례마다 하나 [{key, to, tail, levels[{n, key, was, lines}], lines, places, at, under, from}]."""
    out = {}
    for ov, at in overs:
        if not ov:
            continue
        c = out.setdefault(ov["key"], {"key": ov["key"], "to": list(ov["to"]), "tail": list(ov.get("tail") or ()), "levels": {}, "lines": 0, "places": 0, "at": at, "under": [], "from": []})
        c["lines"] += int(ov.get("lines") or 0)
        c["places"] += 1
        c["under"] += [u for u in ov.get("under") or () if u not in c["under"]]
        if ov.get("from") and list(ov["from"]) not in c["from"]:
            c["from"].append(list(ov["from"]))
        for lv in ov.get("levels") or ():
            x = c["levels"].setdefault(int(lv["n"]), {"n": int(lv["n"]), "key": lv.get("key") or "", "was": lv.get("was") or "", "lines": 0})
            x["lines"] += int(lv.get("lines") or 0)
            x["was"] = x["was"] or lv.get("was") or ""
    return [{**c, "levels": [c["levels"][n] for n in sorted(c["levels"])]} for c in out.values()]


def record_cases(records, to_doc):
    """넣은 넘친 줄의 기록 → 사례(collect 와 같은 꼴 + applied = 지금 문서에 남은 넣은 줄 수). 이미 다 넣어 계획에 넘친 줄이 없는 문서에서도 사례를 보이고 고르게 한다(다시 맞추기)."""
    out = {}
    for rec in records or ():
        key, to = rec.get("key"), rec.get("to") or ()
        live = [ln for ln in rec.get("lines") or () if to_doc._attached(to_doc._ids.get(ln.get("id")))]
        if not key or len(to) != 2 or not live:
            continue
        tail = key[len(to[0]) + 1:].split(MC.SEP) if key.startswith(f"{to[0]}<") and "@" not in key[len(to[0]) + 1:] else []
        c = out.setdefault(key, {"key": key, "to": list(to), "tail": tail, "levels": {}, "lines": 0, "places": 0, "at": live[0]["id"], "under": [], "from": [], "applied": 0})
        c["places"] += 1
        c["applied"] += len(live)
        for ln in live:
            j = int(ln["over"])
            x = c["levels"].setdefault(int(to[1]) + j, {"n": int(to[1]) + j, "key": tail[j - 1] if j - 1 < len(tail) else shape(ln.get("was")), "was": ln.get("was") or "", "lines": 0, "applied": 0})
            x["applied"] += 1
    return [{**c, "levels": [c["levels"][n] for n in sorted(c["levels"])]} for c in out.values()]


def merged(cases, done):
    """계획의 사례(collect)와 넣은 줄의 사례(record_cases)를 열쇠로 합친다 — 넣을 줄 수(lines)는 계획 것, 넣은 줄 수(applied)는 기록 것."""
    out = {c["key"]: {**c, "applied": 0, "levels": [{**x, "applied": 0} for x in c["levels"]]} for c in cases}
    for d in done:
        c = out.get(d["key"])
        if c is None:
            out[d["key"]] = d
            continue
        c["applied"] = d["applied"]
        by = {x["n"]: x for x in c["levels"]}
        for x in d["levels"]:
            if x["n"] in by:
                by[x["n"]]["applied"] = x["applied"]
            else:
                c["levels"].append(x)
        c["levels"].sort(key=lambda x: x["n"])
    return list(out.values())


def plan_view(cases, records, store, to_graph, to_doc):
    """넣기 계획에 실을 over{version, cases[…], templates[…], records{lines, cases{열쇠: 줄 수}}} — cases = 이번 계획의 사례(collect), records = 넣은 넘친 줄의 기록들."""
    left = alive(to_doc, records)
    return {**view(merged(cases, record_cases(records, to_doc)), store, to_graph, to_doc), "records": {"lines": sum(left.values()), "cases": left}}


def view(cases, store, to_graph, to_doc=None):
    """화면용 over{version, cases[…], templates[…]}(spec_병합 ② §5-5 4) — cases = collect()(또는 merged()) 결과, store = load() 결과."""
    tpls = templates(to_graph, to_doc)
    slots = {t["anchor"]: {x["level"]: x for x in t["levels"]} for t in tpls}
    defs = {(t.get("anchor") or t.get("name")): t for t in (to_graph or {}).get("templates") or ()}
    depth, out = _depths(to_graph), []
    for c in cases:
        choice = (store.get("cases") or {}).get(c["key"]) or {}
        specs = _levels(choice, depth)
        t = defs.get(c["to"][0]) or {}
        used, levels = [str(k) for k in t.get("chain") or ()], []
        for i, lv in enumerate(c["levels"]):
            sp = (specs[i] if i < len(specs) else None) or {}
            like, missing, got = sp.get("like"), False, lv["key"]
            if like:
                slot = (slots.get(like["template"]) or {}).get(like["level"])
                missing = not (slot and slot["ok"])
                like = {**like, "letter": (slot or {}).get("letter") or "", "text": (slot or {}).get("text") or ""}
                got = lv["key"] if missing else slot["key"]
            if sp.get("letter") and not missing:
                got = shape(sp["letter"])
            levels.append({"n": lv["n"], "key": lv["key"], "was": lv["was"] or lv["key"], "lines": lv["lines"], "applied": lv.get("applied", 0), "letter": sp.get("letter") or None, "like": like or None,
                           "lead": sp.get("lead"), "clash": got in used, "missing": missing})
            used.append(got)
        out.append({"key": c["key"], "to": {"template": c["to"][0], "no": t.get("no", t.get("id")), "chain": list(t.get("chain") or ()), "level": c["to"][1]}, "tail": c["tail"], "levels": levels,
                    "lines": c["lines"], "applied": c.get("applied", 0), "places": c["places"], "at": c.get("at"), "mode": choice.get("mode") or "cover", "template": choice.get("template"),
                    "under": c.get("under") or []})
    return {"version": store.get("version", 0), "cases": out, "templates": tpls}


def preview(to_doc, from_doc, plan):
    """넣기 하나(merge_convert.plan 결과)의 변환 미리보기 수 {converted, over(넘친 줄), kept{까닭: n}} — merge_convert.apply 와 같은 셈(문서는 안 고치고 첫머리 레터만 읽는다)."""
    kept, n, over = Counter(), 0, 0
    for r in plan["rows"]:
        over += bool(r.get("over"))
        why = r["why"]
        if not why:
            src = from_doc._ids.get(r["src"])
            if src is None or not prefix_of(from_doc._text(src), r["was"] or None)[1]:
                why = "noLetter"
            elif not r.get("own"):
                like = to_doc._ids.get(r["like"])
                if like is None or not to_doc._attached(like) or not prefix_of(to_doc._text(like), r["likeLetter"] or None)[1]:
                    why = "noLike"
        if why:
            kept[why] += 1
            kept["cell"] += r["cells"]
        else:
            n += 1
    return {"converted": n, "over": over, "kept": {k: v for k, v in kept.items() if v}}


def fill_preview(to, frm, fill, specs):
    """이관 넣기 계획(merge_fill.plan)의 할 일 항목마다 템플릿 변환 미리보기 → ({목적 항목 key: {converted, over, kept}}, 사례(collect 결과)). to·frm = {"doc", "graph"}."""
    tg, fg = to.get("graph") or {}, frm.get("graph") or {}
    items, overs = {}, []
    if not tg.get("nodes") or not fg.get("nodes"):
        return items, []
    for row in fill["items"]:
        if row.get("skip") is not None or not row.get("anchor") or not row.get("src"):
            continue
        p = MC.plan(tg, fg, row["anchor"], row["src"], over=specs)
        items[row["to"]] = preview(to["doc"], frm["doc"], p)
        overs.append((p["summary"].get("over"), row["anchor"]))
    return items, collect(overs)


# ---- 넣은 뒤 다시 맞추기 ----------------------------------------------------------------------------------------------

def alive(to_doc, records):
    """기록 가운데 지금 문서에 남은 넘친 줄 수 {사례 열쇠: 줄 수}(다시 맞출 수 있는 것 — 화면의 「넣은 줄에 다시 맞추기(n줄)」)."""
    out = Counter()
    for rec in records or ():
        out[rec.get("key")] += sum(1 for ln in rec.get("lines") or () if to_doc._attached(to_doc._ids.get(ln.get("id"))))
    return {k: v for k, v in out.items() if k and v}


def refit(to_doc, records, specs, only=None, dry=False):
    """넣은 넘친 줄에 지금 선택을 다시 입힌다(모듈 설명) — records 는 안 고치고 고친 사본을 돌려준다. dry = 문서를 안 고치고 바뀔 줄만 센다(끝점이 편집을 열기 전에 본다)."""
    kept, ids, out = Counter(), [], []
    for rec in records:
        rec = copy.deepcopy(rec)
        out.append(rec)
        if only is not None and rec.get("key") != only:
            continue
        sp = specs.get(rec.get("key")) or []
        now, last = {}, {}   # 이번에 정한 줄의 레터 · (부모, 넘친 레벨) → 마지막 번호
        for ln in rec.get("lines") or ():
            nid, j = ln["id"], int(ln["over"])
            el = to_doc._ids.get(nid)
            if el is None or not to_doc._attached(el):   # 지운 문단도 id 표에는 남는다
                kept["gone"] += 1
                continue
            text = to_doc._text(el)
            cur = next((c for c in (ln.get("letter"), ln.get("was"), *reversed(ln.get("seen") or ())) if c and prefix_of(text, c)[1]), None)
            if cur is None:
                kept["edited"] += 1
                continue
            lead, tok, gap = prefix_of(text, cur)
            olead, _, ogap = prefix_of(ln["orig"]["prefix"], ln["was"])
            spec = sp[j - 1] if j - 1 < len(sp) else None
            if not spec:   # 덮은 그대로 — 넣은 그대로의 접두와 모양으로 되돌린다
                letter, prefix, like_id, attrs = ln["was"], ln["orig"]["prefix"], None, ln["orig"]["attrs"]
            else:
                like = to_doc._ids.get(spec["like"]) if spec.get("like") else None
                llead, ltok, lgap = prefix_of(to_doc._text(like), spec.get("likeLetter") or None) if like is not None and to_doc._attached(like) else ("", "", "")
                if spec.get("like") and not ltok:
                    kept["noLike"] += 1
                    continue
                letter = spec.get("letter") or (ltok if spec.get("like") else ln["was"])
                if spec.get("numbered") and (spec.get("letter") or spec.get("like")) and rec.get("keepNumbers") and shape(letter) == shape(ln["was"]):
                    letter = ln["was"]   # 취합 — 같은 번호 꼴이면 기관이 쓴 번호를 둔다(넣을 때와 같은 규칙: spec_취합 ② §4-4 · merge_gather_fit)
                elif spec.get("numbered") and (spec.get("letter") or spec.get("like")):
                    pl = MC._numpl(now.get(ln.get("parent"), ln.get("pl")))
                    prev = last.get((ln.get("parent"), j))
                    letter = first(letter, pl) if prev is None else succ(prev, pl)
                    if letter is None:
                        kept["numEnd"] += 1
                        continue
                    last[(ln.get("parent"), j)] = letter
                space = " " * int(spec["lead"]) if spec.get("lead") is not None else None
                if spec.get("like"):
                    prefix, like_id, attrs = (llead if space is None else space) + letter + lgap, spec["like"], None
                else:
                    prefix, like_id, attrs = (olead if space is None else space) + letter + ogap, None, ln["orig"]["attrs"]
            now[nid] = letter
            want = to_doc.para_attrs(like_id) if like_id else {k: str(v) for k, v in attrs.items()}
            if lead + tok + gap == prefix and to_doc.para_attrs(nid) == want:
                ln["letter"] = letter   # 이미 그 모양 — 건드리지 않는다
                continue
            try:
                if not dry:
                    to_doc.replace_prefix(nid, len(lead) + len(tok) + len(gap), prefix, like_id=like_id, attrs=attrs)
            except ValueError:
                kept["marker"] += 1
                continue
            ids.append(nid)
            ln["seen"] = [c for c in dict.fromkeys([*(ln.get("seen") or ()), cur]) if c not in (letter, ln["was"])][-4:]   # 앞서 입힌 레터(실행 취소 뒤에도 첫머리를 알아보게)
            ln["letter"] = letter
    return {"lines": len(ids), "kept": dict(kept), "ids": ids, "records": out}
