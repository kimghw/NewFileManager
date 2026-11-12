"""병합 ③ 표 안 연결 + ④ 내용 반영의 표 몫(spec_병합 ② §0 「자리 두 갈래」 · §0-1 ③④ · §5 「표 묶음 항목」·「연구개발비」 · §6) — 짝지은 표 묶음 안에서
항목·행·칸을 잇고 목적 표를 채운다. 스크립트만(LLM 없음).

- `plan(to_side, from_side, to_values, from_values, pairs)` = 넣기 계획(문서를 안 고침). side = {"doc", "tables"(3단계 결과)}, pairs = `merge_pairs.pair` 결과 — status paired 이고
  종류가 표(rows·cols·list)인 묶음만. → {"tables": [묶음마다 {group, kind, mode, to, from, cells, rows, skipped}], "cells": [{to, from, text, table, group, item, calc}],
  "rows": [{table, after, cols, cells[{col, from, text}], group, item}], "skipped": [{group, item, why, detail, to?}], "counts"}.
  why = noSource(원본 항목·행 없음) · occupied(목적 칸·행에 다른 글) · ambiguous(같은 꼴·같은 기관 후보가 여럿, 원본 기관을 모름) · shape(칸·열을 못 맞춤 · 행을 못 늘림) · calc(아래).
  - **정해진 자리**(mode fixed — 목적 표에 그 항목·칸이 이미 있음): 항목 짝 안에서 필드 칸을 (행 머리 꼴, 열 머리 꼴)로 맞춰 칸 글을 옮긴다 — 목적 칸이 비었을 때만(자리표시
    「0,000,000」·「yyyy-yyyy」 는 빈 것), 글이 다르면 occupied. 머리 꼴 = 같은 띠에서 그 칸의 왼쪽·위로 걸친 머리 칸 글(코드·단위·각주·※·기관 이름·기호 뗌, 값만인 칸
    「1차년도」·「1단계」·「2027」 은 뺌). 꼴이 같은 원본 칸이 없으면 머리마다 한쪽이 다른 쪽을 품는 꼴(「지방자치단체」 ↔ 「지방자치단체 등」)이 하나뿐일 때만. 원본 칸은 필드이거나
    수인 칸(3단계가 머리로 잘못 본 합계 「648,000」 도).
  - **이어 넣는 자리**(mode append — 기관-연도 행 표 `orgYear`): 목적 기관 항목 × 연도 덩이마다 원본에서 같은 기관(이름 — 「공동1」 자리가 아님)·같은 차년도(연도 칸 「2027」·「2차년도」 →
    전체 차례 수)의 행을 원본 차례대로 — 같은 행이 이미 있으면 건너뛰고, 빈 행을 먼저 쓰고, 모자라면 덩이 끝 행 아래로 늘린다(기관·연도·연차 칸은 늘어남). 열은 열 머리 꼴로 맞춘다 —
    **첫 항목 행 위의 머리 칸만** 열 머리다(3단계는 자료 행의 칸도 행 머리로 볼 수 있다 — 「명칭(구분)」 열의 글. 그것까지 꼴에 넣으면 행마다 꼴이 달라 그 열의 글이 빠진다).
    같은 행 = 같은 열의 글이 하나는 같고 다른 것이 없음, **목적의 빈 칸은 안 따진다**(비워 두고 넣은 계산 칸 · 목적에 없던 열 때문에 「없는 행」 으로 보면 다시 계획할 때마다 한 줄이 또 들어간다).
    목적 덩이의 기관 차례(주관 → 공동k)는 반영이 만든 표 그대로. 원본에 같은 기관 항목이 여럿이면(같은 기관을 연도마다 따로 쓴 표) 차례대로 모두.
  - 계산 칸(heading_calc 수식이 걸린 합계·소계·비율 — 칸에 calc): 피연산자 칸이 모두 같은 항목 짝에서 이어졌을 때만 원본 값을 옮기고(같은 줄의 합 — 걸러진 줄이 없음),
    아니면 비워 두고 calc 로 보고한다(⑤ 합계 계산이 다시 셈). 이어 넣는 행의 계산 칸은 늘 비운다.
  - 항목 정체: 기관 = 이름(라벨·이름 칸·기관 칸 글 → 구분 값의 기관. 원본은 이름으로만 — 작성한 문서는 「주관」 자리에 KERI 가 있을 수 있다. 목적은 못 찾으면 엔진 차례 — 반영이 만든 자리),
    차년도·단계 = `merge_pairs._ident`(전체 차례 수, 「다음 연도」 표는 yearBase). 목적 항목에 있는 값만 채운다(당해·다음 연도 자리는 그 해만, 전 차년도 열은 모두).
- `apply(to_doc, from_doc, plan)` = 계획을 목적 문서에 → {"filled", "shaped", "rowsAdded", "new", "skipped"}. 칸은 **지금** 비었을 때만 쓴다(계획 뒤 사람이 쓴 글을 덮지 않음). 같은 `after` 의
  행은 차례대로 잇는다. 글은 계획의 것을 쓰고, 원본 문서에서는 **글자 모양만** 읽는다(고치지 않음): 글을 쓴 칸에 원본 칸(`from`)의 장평·자간·글자 크기를 함께 얹는다(shaped = 얹은 칸 수 —
  `HwpxDoc.fit_chars`, 글꼴·색·굵기 등은 목적 칸 것 그대로. 2026-11-12 사용자 결정 — 계획서에서 장평을 줄여 한 줄에 넣은 이메일·영문 과제명이 연차보고서 칸에서 여러 줄로 꺾였다).
  모양은 글을 쓴 칸에만 얹는다 — 글이 같고 모양만 다른 칸은 할 일이 아니다.
다시 계획하면 넣은 칸은 글이 같고 넣은 행은 같은 행이 있어 할 일이 없다(§6). 자리·글은 지금 문서에서, 칸 역할·띠·수식은 3단계 결과(칸 id)에서 읽는다 — 늘린 행의 칸은 3단계에 없어
역할·띠가 없다(머리가 아니고, 띠는 그 항목 라벨 칸의 것을 쓴다)."""
import re
from collections import Counter, defaultdict

from app import heading_calc as HC
from app import merge_pairs as P
from app.division_profiles import _structure as structure
from app.division_profiles import rnd
from app.division_profiles.rnd import core

KINDS = ("rows", "cols", "list")
HEADS = ("colhead", "rowhead", "corner")
WHY = ("noSource", "occupied", "ambiguous", "shape", "calc")
_VAL = re.compile(r"(?:\d+|[Nnx])단계-?|(?:\d+|[Nnx])(?:차년도|년차|차)|(?:19|20)(?:\d\d|[xX]{2})년?|YYYY|yyyy")   # 빈칸 뺀 글의 구분 값 낱말
_SYM = re.compile(r"[^0-9A-Za-z가-힣]")
_CODE = re.compile(r"\([A-Z0-9+\-*/=().%]*\)?")   # 빈칸 뺀 글의 코드·식 괄호 — 짝이 안 맞아 heading_calc.core 가 못 뗀 「(L/(N+O+…+S)」 도
_DATE_SLOT = re.compile(r"[\sYyMmDd.\-~/]*[Yy]{2,}[\sYyMmDd.\-~/]*")   # 「yyyy-yyyy」·「YYYY. MM. DD」


# ---- 읽을거리 ------------------------------------------------------------------------------------------------

def _side(side, values):
    """한 문서 → 엔진 묶음(지금 문서, key → 묶음)·블록 색인·3단계 칸(id → 칸)·수식 피연산자(칸 id → id 모음)·기관 이름(빈칸 뺌, 긴 것 먼저)."""
    blocks = side["doc"].blocks()
    values = core.norm_values(values)
    s3, ops = {}, defaultdict(set)
    for t in (side.get("tables") or {}).get("tables") or ():
        s3.update((c["id"], c) for c in t["cells"])
        for f in t.get("formulas") or ():
            ops[f["cell"]].update(f["operands"])
    names = sorted({re.sub(r"\s+", "", n) for _, n in P._orgs(values) if n}, key=len, reverse=True)
    return {"groups": {g["key"]: g for g in core.find(blocks, rnd.levels_of(blocks), values)}, "idx": structure.index_blocks(blocks),
            "s3": s3, "ops": ops, "values": values, "names": names, "orgs": {P.org_key(n) for _, n in P._orgs(values) if P.org_key(n)}, "views": {}}


def _view(S, tid):
    """표 하나(지금 문서) → {"cells": [{id, row, col, rs, cs, text, role, sub}], "by", "heads"} — 역할·띠는 3단계 칸에서(없는 칸 = None)."""
    v = S["views"].get(tid)
    if v is None:
        cells = []
        for c in S["idx"][tid]["cells"]:
            s = S["s3"].get(c["id"]) or {}
            cells.append({"id": c["id"], "row": c["row"], "col": c["col"], "rs": c["rowSpan"], "cs": c["colSpan"], "text": c.get("text") or "",
                          "role": s.get("role"), "sub": s.get("sub")})
        v = S["views"][tid] = {"cells": cells, "by": {c["id"]: c for c in cells}, "heads": [c for c in cells if c["role"] in HEADS]}
    return v


def _hkey(text, names):
    """머리 칸 글 → 견줄 꼴 — 코드·단위·각주(heading_calc.core)·※ 꼬리·기관 이름·기호를 뗀 것. 값만인 칸(「1차년도」·「1단계」·「2027」·「2차 (1단계)」)과 수는 ""
    (항목 값은 항목 짝이 맞춘다). 값 낱말이 다른 글과 섞인 머리(「매출액발생 1년차」)는 그대로 — 열마다 다르다."""
    if not text or HC.parse_num(text).get("num") is not None:
        return ""
    s = _CODE.sub("", re.sub(r"\s+", "", HC.core(core.NOTE.sub("", text))))
    for n in names:
        s = s.replace(n, "")
    return _SYM.sub("", s).lower() if _SYM.sub("", _VAL.sub("", s)) else ""


def _key(v, c, names, top=None, sub=None):
    """칸 → (행 머리 꼴들, 열 머리 꼴들) — 같은 띠에서 그 행에 걸친 왼쪽 머리 칸(열 차례)·그 열에 걸친 위 머리 칸(행 차례). 띠를 모르는 칸(늘린 행)은 sub(그 덩이의 띠)로, 없으면 안 가린다.
    top = 이어 넣는 표의 첫 항목 행 — 그 위의 칸만 열 머리다: 3단계는 자료 행의 칸(「명칭(구분)」 열의 글)도 행 머리로 볼 수 있어, 그것까지 넣으면 윗 행의 글이 끼어 행마다 꼴이 달라진다."""
    band = c["sub"] if c["sub"] is not None else sub
    hs = [h for h in v["heads"] if band is None or h["sub"] == band]
    left = sorted((h for h in hs if h["col"] + h["cs"] <= c["col"] and h["row"] < c["row"] + c["rs"] and c["row"] < h["row"] + h["rs"]),
                  key=lambda h: (h["col"], h["row"]))
    up = sorted((h for h in hs if h["row"] + h["rs"] <= c["row"] and (top is None or h["row"] < top) and h["col"] < c["col"] + c["cs"] and c["col"] < h["col"] + h["cs"]),
                key=lambda h: (h["row"], h["col"]))
    return tuple(k for k in (_hkey(h["text"], names) for h in left) if k), tuple(k for k in (_hkey(h["text"], names) for h in up) if k)


def _loose(k, fk):
    """꼴이 같은 원본 칸이 없을 때 — 머리 수가 같고 자리마다 한쪽이 다른 쪽을 품는(「지방자치단체」 ↔ 「지방자치단체 등」) 원본 꼴의 칸들(하나뿐이어야 쓴다)."""
    def near(a, b):
        return len(a) == len(b) and all(x in y or y in x for x, y in zip(a, b))
    return [c for kk, cs in fk.items() if near(k[0], kk[0]) and near(k[1], kk[1]) for c in cs]


def _empty(text):
    """목적 칸이 비었나 — 빈 글 · 수 자리표시(「0,000,000」·「00%」) · 날짜 자리표시(「yyyy-yyyy」·「YYYY. MM. DD」)."""
    t = (text or "").strip()
    return not t or bool(HC.parse_num(t).get("placeholder")) or bool(_DATE_SLOT.fullmatch(t))


def _org(text, S):
    """글 → 구분 값의 기관(이름 꼴 — merge_pairs.org_key) | None. 같은 이름, 아니면 한쪽이 다른 쪽을 품는 이름이 하나뿐일 때(「한양대학교」 ⊂ 「한양대학교 에리카산학협력단」 ·
    「사단법인 한국선급」 ⊃ 「한국선급」 · 「[주관연구개발기관 : 인텍]」). 약칭(「KERI」)은 못 찾는다."""
    k = P.org_key(text)
    if not k:
        return None
    if k in S["orgs"]:
        return k
    hit = [n for n in S["orgs"] if n in k or (len(k) >= 2 and k in n)]
    return hit[0] if len(hit) == 1 else None


def _name(S, it):
    """기관 항목의 이름 글(지금 문서) — 역할 칸 이름 · 목록 행 이름 칸(nameAt) · 라벨 칸."""
    if it.get("name"):
        return it["name"]
    b = S["idx"].get(it["roots"][it["nameAt"]] if it.get("nameAt") is not None else it.get("label"))
    return b.get("text") if b else it.get("labelText")


def _own(it):
    """항목의 정체 칸(라벨·목록 행 이름 칸) id — 옮길 칸이 아니다(이름 글은 정체로 맞췄다)."""
    return {it.get("label"), it["roots"][it["nameAt"]] if it.get("nameAt") is not None else None}


def _ident(S, g, it, target=False):
    """항목의 문서와 무관한 값(모듈 설명 「항목 정체」) | None(원본 기관을 모름)."""
    if g["dim"] == core.ORG:
        org = _org(_name(S, it), S)
        if org or not target:
            return ("org", org) if org else None
    return P._ident(g["dim"], it["value"], it.get("labelText"), S["values"], g.get("yearBase") or 0)


def _year_no(text, values):
    """연도 칸 글 → 전체 차례 차년도 수 | None — 「2027」(사업기간 연도로) · 「1단계-2차년도」 · 「2차년도」."""
    s = core._bare(text)
    if core.REAL_YEAR.match(s):
        return next((k for k, (a, _) in enumerate(core._period(values) or (), 1) if a.year == int(s)), None)
    if (m := core.SY_RE.search(text or "")) and m.group(1).isdigit() and m.group(2).isdigit():
        return core._year_no(values, int(m.group(1)), int(m.group(2)))
    if (m := core.YEAR_RE.search(text or "")) and m.group(1).isdigit():
        return core._year_no(values, None, int(m.group(1)))
    return None


# ---- 계획 ----------------------------------------------------------------------------------------------------

class _Out:
    """계획 모으기 — 묶음 하나씩(group·kind·mode 를 붙여 적는다)."""

    def __init__(self):
        self.cells, self.rows, self.skipped, self.tables = [], [], [], []
        self.pairs = []   # 칸 짝 [(목적 칸 id, 원본 칸 id)] — 넣을 것이 없는 칸(글이 같음·이미 넣음)도 든다: 원본 자리 지도(merge_origins)가 읽는다

    def start(self, gp, mode, tid, fid):
        self.gp, self.n = gp, (len(self.cells), len(self.rows), len(self.skipped))
        self.tables.append({"group": gp["id"], "kind": gp["kind"], "mode": mode, "to": tid, "from": fid})

    def skip(self, item, why, detail, to=None):
        self.skipped.append({"group": self.gp["id"], "item": item, "why": why, "detail": detail, **({"to": to} if to else {})})

    def end(self):
        a, b, c = self.n
        self.tables[-1].update(cells=len(self.cells) - a, rows=len(self.rows) - b, skipped=len(self.skipped) - c)


def _items(o, T, F, tg, fg):
    """항목 짝 [(목적 항목, 값 글, [원본 항목…])] — 정체가 같은 것끼리. 정체를 모르는 원본 항목·짝 없는 목적 항목은 보고."""
    src = defaultdict(list)
    for it in fg["items"]:
        k = _ident(F, fg, it)
        if k is None:
            o.skip(None, "ambiguous", f"원본 항목 「{P._ws(_name(F, it))[:30]}」 — 구분 값의 어느 기관인지 모름")
        else:
            src[k].append(it)
    out = []
    for it in tg["items"]:
        value = rnd.value_text(tg["dim"], it["value"])
        got = src.get(_ident(T, tg, it, target=True))
        if got:
            out.append((it, value, got))
        else:
            o.skip(value, "noSource", "원본에 같은 값의 항목이 없음")
    return out


def _fixed(o, T, F, tg, fg):
    """정해진 자리 — 항목 짝마다 필드 칸을 머리 꼴로 맞춰 칸 글(모듈 설명)."""
    tv, fv = _view(T, tg["table"]), _view(F, fg["table"])
    for ti, value, fis in _items(o, T, F, tg, fg):
        if len(fis) > 1:
            o.skip(value, "ambiguous", f"원본에 같은 값의 항목이 {len(fis)}개")
            continue
        fi = fis[0]
        fk = defaultdict(list)
        for c in (fv["by"][i] for i in fi["roots"] if i in fv["by"] and i not in _own(fi)):
            if c["role"] == "field" or HC.parse_num(c["text"]).get("num") is not None:
                fk[_key(fv, c, F["names"])].append(c)
        got, miss = {}, []
        for c in (tv["by"][i] for i in ti["roots"] if i in tv["by"] and i not in _own(ti)):
            if c["role"] != "field":
                continue
            k = _key(tv, c, T["names"])
            hit = (fk.get(k) or _loose(k, fk)) if any(k) else []
            if len(hit) == 1:
                got[c["id"]] = hit[0]
            elif hit:
                o.skip(value, "ambiguous", f"꼴이 같은 원본 칸 {len(hit)}개 — {' › '.join(k[0] + k[1])}", c["id"])
            else:
                miss.append(" › ".join(k[0] + k[1]) or "(머리 없음)")
        if miss:
            o.skip(value, "shape", f"원본에서 못 맞춘 칸 {len(miss)}: " + " / ".join(miss[:3]))
        o.pairs += [(cid, s["id"]) for cid, s in got.items()]
        for cid, s in got.items():
            c, ops = tv["by"][cid], T["ops"].get(cid)
            if _empty(s["text"]) or P._ws(s["text"]) == P._ws(c["text"]):
                continue
            if ops and not ops <= got.keys():
                o.skip(value, "calc", "계산 칸 — 피연산자 일부가 원본과 이어지지 않아 비워 둠(합계 계산이 셈)", cid)
            elif not _empty(c["text"]):
                o.skip(value, "occupied", f"목적 칸에 「{P._ws(c['text'])[:30]}」 — 원본 「{P._ws(s['text'])[:30]}」", cid)
            else:
                o.cells.append({"to": cid, "from": s["id"], "text": s["text"], "table": tg["table"], "group": o.gp["id"], "item": value, "calc": bool(ops)})


def _year_col(v):
    """기관-연도 표의 연도 열 머리 칸 | None — core._org_year 와 같은 규칙(첫 칸 「연구개발기관」 바로 오른쪽 머리가 「…연도」)."""
    head = next((c for c in v["cells"] if c["row"] == 0 and c["col"] == 0 and core._bare(c["text"]) == "연구개발기관"), None)
    return head and next((c for c in v["cells"] if c["row"] == 0 and c["col"] == head["cs"] and core.YEAR_COL.search(core._bare(c["text"]))), None)


def _blocks(v, it, yc):
    """기관 항목 → (자리 칸 id 모음, [(연도 칸 | None, 첫 행, 끝 행)]) — 자리 칸 = 기관 칸·연도 칸·「2차 (1단계)」 연차 칸(행을 늘리면 늘어나고 글을 안 옮김).
    연도 칸이 없으면 항목 전체가 한 덩이."""
    a, e = it["span"]
    inside = [c for c in v["cells"] if a <= c["row"] <= e]
    ys = sorted((c for c in inside if yc and c["col"] == yc["col"]), key=lambda c: c["row"])
    fixed = {it["label"]} | {c["id"] for c in ys} | {c["id"] for c in inside if core.STEP_CELL.match(core._bare(c["text"]))}
    return fixed, [(y, y["row"], y["row"] + y["rs"] - 1) for y in ys] or [(None, a, e)]


def _row(v, r, fixed, names, top, sub):
    """행 r 에서 시작하는 칸(자리 칸 빼고) → {열 머리 꼴: 칸} | None(같은 꼴 칸이 둘 — 못 맞춤). top·sub = 표의 첫 항목 행 · 그 항목의 띠(_key — 열 머리 꼴이 행마다 같게)."""
    out = {}
    for c in v["cells"]:
        if c["row"] == r and c["id"] not in fixed and (k := _key(v, c, names, top, sub)[1]):
            if k in out:
                return None
            out[k] = c
    return out


def _append(o, T, F, tg, fg, ctx_year):
    """이어 넣는 자리 — 기관 × 연도 덩이마다 원본 행을 잇는다(모듈 설명)."""
    tv, fv = _view(T, tg["table"]), _view(F, fg["table"])
    tyc, fyc = _year_col(tv), _year_col(fv)
    recs, lost = defaultdict(list), set()   # (기관, 차년도 | None) → [{열 꼴: 원본 칸}]
    top = lambda g: min(it["span"][0] for it in g["items"])   # noqa: E731 — 첫 항목 행(그 위가 열 머리)
    band = lambda v, it: (v["by"].get(it["label"]) or {}).get("sub")   # noqa: E731 — 그 항목의 띠(라벨 칸의 것 — 늘린 행의 칸은 띠를 모른다)
    ftop, ttop = top(fg), top(tg)
    for it in fg["items"]:
        org, n = _org(_name(F, it), F), 0
        fixed, blocks = _blocks(fv, it, fyc)
        for y, a, e in blocks:
            yn = _year_no(y["text"], F["values"]) if y else None
            for r in range(a, e + 1):
                rec = _row(fv, r, fixed, F["names"], ftop, band(fv, it))
                if rec is None:
                    o.skip(None, "shape", f"원본 {r + 1}행 — 열 머리가 같은 칸이 둘")
                elif any(not _empty(c["text"]) for c in rec.values()):
                    n += 1
                    if org:
                        recs[(org, yn)].append(rec)
        if org is None and n:   # 빈 기관 덩이(양식 그대로)는 말하지 않는다
            o.skip(None, "ambiguous", f"원본 기관 「{P._ws(_name(F, it))[:30]}」 — 구분 값의 어느 기관인지 모름 (글 있는 행 {n}개를 못 넣음)")
    for it in tg["items"]:
        value = rnd.value_text(tg["dim"], it["value"])
        org = (_ident(T, tg, it, target=True) or (None, None))[1]
        fixed, blocks = _blocks(tv, it, tyc)
        for y, a, e in blocks:
            yn = (_year_no(y["text"], T["values"]) if y else None) or ctx_year
            where = f"{value} · {rnd.value_text(core.YEAR, yn)}" if yn else value
            if fyc is None:   # 원본에 연도 칸이 없음 — 목적이 한 해 자리면 가를 수 없다
                want = recs.get((org, None), [])
                if want and yn is not None:
                    o.skip(where, "shape", "원본 표에 연도 칸이 없어 차년도를 못 가름")
                    continue
            else:
                want = recs.get((org, yn), []) if yn is not None else [x for (g, _), rs in recs.items() if g == org for x in rs]
            if not want:
                o.skip(where, "noSource", "원본에 이 기관·차년도의 행이 없음")
                continue
            rowmap = {r: _row(tv, r, fixed, T["names"], ttop, band(tv, it)) for r in range(a, e + 1)}
            cov = lambda r: [c for c in tv["cells"] if c["row"] <= r < c["row"] + c["rs"] and c["id"] not in fixed]  # noqa: E731
            blank = [r for r, rec in rowmap.items() if rec is not None and all(c["row"] == r and c["rs"] == 1 and _empty(c["text"]) for c in cov(r))]
            have = [rec for r, rec in rowmap.items() if rec and r not in blank and any(not _empty(c["text"]) for c in rec.values())]
            todo = []
            for rec in want:
                lost |= {k for k, c in rec.items() if not _empty(c["text"])} - {k for x in rowmap.values() if x for k in x}
                # 같은 행 = 같은 열의 글이 하나는 같고 다른 것이 없음. 목적의 빈 칸은 안 따진다 — 넣을 때 비워 둔 칸(계산 칸 등)이 있는 행을 「없는 행」 으로 보면 다시 계획할 때마다 한 줄이 또 들어간다
                eq = lambda h, k, c: P._ws(h[k]["text"]) == P._ws(c["text"])   # noqa: E731
                same = next((i for i, h in enumerate(have) if any(k in h and not _empty(c["text"]) and eq(h, k, c) for k, c in rec.items())
                             and all(_empty(h[k]["text"]) or eq(h, k, c) for k, c in rec.items() if k in h)), None)
                if same is None:
                    todo.append(rec)
                else:
                    o.pairs += [(have[same][k]["id"], c["id"]) for k, c in rec.items() if k in have[same]]   # 이미 있는 같은 행 — 같은 열의 칸끼리
                    del have[same]
            if have:
                o.skip(where, "occupied", f"목적 행 {len(have)}개에 다른 글 — 「{P._ws(' '.join(c['text'] for c in have[0].values()))[:40]}」 (양식 예시일 수 있음)")
            for r, rec in zip(blank, todo):
                for k, s in rec.items():
                    c = rowmap[r].get(k)
                    if c is not None and not _empty(s["text"]):
                        if T["ops"].get(c["id"]):
                            o.skip(where, "calc", "계산 칸 — 이어 넣는 행은 비워 둠(합계 계산이 셈)", c["id"])
                        else:
                            o.cells.append({"to": c["id"], "from": s["id"], "text": s["text"], "table": tg["table"], "group": o.gp["id"], "item": where, "calc": False})
            more = todo[len(blank):]
            if not more:
                continue
            slot = sorted(cov(e), key=lambda c: c["col"])
            tmpl = rowmap[e]
            if not slot or not tmpl or any(c["row"] != e or c["rs"] != 1 for c in slot):
                o.skip(where, "shape", f"덩이 끝 행에 병합 칸이 걸려 행 {len(more)}개를 늘릴 수 없음")
                continue
            for rec in more:
                cells = [{"col": tmpl[k]["col"], "from": s["id"], "text": s["text"]} for k, s in rec.items()
                         if k in tmpl and not _empty(s["text"]) and not T["ops"].get(tmpl[k]["id"])]
                o.rows.append({"table": tg["table"], "after": slot[0]["id"], "cols": [slot[0]["col"], max(c["col"] + c["cs"] - 1 for c in slot)],
                               "cells": cells, "group": o.gp["id"], "item": where})
    if lost:
        o.skip(None, "shape", "목적 표에 없는 원본 열: " + ", ".join(" › ".join(k) for k in sorted(lost)[:5]))   # lost 의 원소 = 열 머리 꼴들(_row 의 키 — 글의 튜플)


def plan(to_side, from_side, to_values, from_values, pairs, skip=()):
    """넣기 계획(모듈 설명) — 문서를 안 고친다. skip = 표 대응(merge_table_map — spec_병합 ② §5-3)이 통째로 맡은 목적 표 id: 그 표의 묶음은 여기서 안 낸다."""
    T, F = _side(to_side, to_values), _side(from_side, from_values)
    o = _Out()
    for gp in pairs["groups"]:
        if gp["status"] != "paired" or gp["kind"] not in KINDS or not gp.get("to") or not gp.get("from"):
            continue
        tg, fg = T["groups"].get(gp["to"]["key"]), F["groups"].get(gp["from"]["key"])
        if tg and tg.get("table") in skip:
            continue
        mode = "append" if tg and tg.get("orgYear") == "org" else "fixed"
        o.start(gp, mode, (tg or {}).get("table"), (fg or {}).get("table"))
        if tg is None or fg is None or not tg.get("table") or not fg.get("table"):
            o.skip(None, "shape", "묶음을 지금 문서에서 다시 못 찾음(짝을 다시 내야 함)")
        elif mode == "append":
            _append(o, T, F, tg, fg, (gp.get("ctx") or {}).get("year"))
        else:
            _fixed(o, T, F, tg, fg)
        o.end()
    why = Counter(s["why"] for s in o.skipped)
    return {"tables": o.tables, "cells": o.cells, "rows": o.rows, "skipped": o.skipped, "pairs": o.pairs,
            "counts": {"groups": len(o.tables), "cells": len(o.cells), "calc": sum(c["calc"] for c in o.cells), "rows": len(o.rows),
                       "rowCells": sum(len(r["cells"]) for r in o.rows), "skipped": {k: why.get(k, 0) for k in WHY}}}


# ---- 반영 ----------------------------------------------------------------------------------------------------

def _shape(to_doc, from_doc, to, frm):
    """글을 쓴 목적 칸에 원본 칸(frm)의 장평·자간·글자 크기를 얹는다(`HwpxDoc.fit_chars` — 글꼴·색·굵기는 목적 칸 것 그대로) → 얹었나(세 값이 이미 같으면 False).
    모양은 글에 딸린 덤이다 — 원본 칸을 못 찾으면 글만 두고 넘어간다(넣기를 막지 않는다)."""
    try:
        return bool(frm) and to_doc.fit_chars(to, from_doc, frm)
    except (KeyError, ValueError):
        return False


def apply(to_doc, from_doc, plan):
    """계획을 목적 문서에(모듈 설명) → {"filled": 쓴 칸 수, "shaped": 그 가운데 원본 칸의 장평·자간·글자 크기를 얹은 칸 수, "rowsAdded", "new": [새 칸 id],
    "skipped": [{to | after, why, detail}]}. from_doc 은 글자 모양만 읽고 안 고친다."""
    filled, added, new, skipped = 0, 0, [], []
    fit = []   # 글을 쓴 (목적 칸, 원본 칸) — 모양은 행을 다 늘린 뒤에 얹는다: 늘리는 행은 앞 행을 본뜨므로(clone_rows) 먼저 얹으면 그 모양이 글 없는 새 칸에도 따라간다
    to_doc.blocks()   # 블록 id 는 읽을 때 붙는다 — 막 연 문서도 table_block 이 id 로 찾게(읽은 문서면 캐시)
    by = defaultdict(list)
    for c in plan["cells"]:
        by[c["table"]].append(c)
    for tid, cs in by.items():
        now = {c["id"]: c.get("text") or "" for c in (to_doc.table_block(tid) or {}).get("cells") or ()}
        for c in cs:
            cur = now.get(c["to"])
            if cur is None:
                skipped.append({"to": c["to"], "why": "shape", "detail": "목적 칸이 지금 문서에 없음"})
                continue
            if P._ws(cur) == P._ws(c["text"]):
                continue
            if not _empty(cur):
                skipped.append({"to": c["to"], "why": "occupied", "detail": "계획 뒤 목적 칸에 글이 생김"})
                continue
            try:
                to_doc.set_text(c["to"], c["text"])
                filled += 1
                fit.append((c["to"], c.get("from")))
            except ValueError as x:
                skipped.append({"to": c["to"], "why": "shape", "detail": str(x)})
    chain = {}   # 같은 자리(after)에 잇는 행 — 바로 앞에 늘린 행의 같은 칸
    for r in plan["rows"]:
        anchor = chain.get(r["after"], r["after"])
        tb = to_doc.table_block(r["table"]) or {"cells": []}
        a = next((c for c in tb["cells"] if c["id"] == anchor), None)
        if a is None:
            skipped.append({"after": r["after"], "why": "shape", "detail": "행을 늘릴 자리 칸이 없음"})
            continue
        try:
            m = to_doc.clone_rows(r["table"], a["row"], a["row"], r["cols"], keep_text=False)["map"]
        except ValueError as x:
            skipped.append({"after": r["after"], "why": "shape", "detail": str(x)})
            continue
        at = {c["col"]: m[c["id"]] for c in tb["cells"] if c["row"] == a["row"] and c["id"] in m}
        for x in r["cells"]:
            if x["col"] in at:
                to_doc.set_text(at[x["col"]], x["text"])
                filled += 1
                fit.append((at[x["col"]], x.get("from")))
        chain[r["after"]] = m[anchor]
        new += m.values()
        added += 1
    shaped = sum(_shape(to_doc, from_doc, to, frm) for to, frm in fit)
    return {"filled": filled, "shaped": shaped, "rowsAdded": added, "new": new, "skipped": skipped}
