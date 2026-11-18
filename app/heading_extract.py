"""헤딩 추출 1단계 — 모든 문단 레코드 · 앞머리 규칙 판정 · 서식 라벨(spec_헤딩_추출 ② §1·§2). 문서를 바꾸지 않는다(읽기만).

- **문단 열거**: 블록 트리가 아니라 구역 XML 의 hp:p 전부(문서 순 — 표 칸·글상자(drawText)·캡션·머리말·꼬리말·각주·미주 안까지, 표·그림만 품은 문단도).
  웹 블록 id 가 있으면 그것(화면·편집과 연결), 없으면 `x<구역>.<순번>`(블록 id 상태를 건드리지 않게 따로 붙임). 구역마다 「XML hp:p 수 = 레코드 수」 를
  `counts.check` 로 센다.
- **레코드**(문단 하나): 자리(area·path), 글, 앞머리 판정(규칙 → kind·family·레터·앞 공백·레터 뒤 공백 — spans 에 안내 「※」·강제 줄 바꿈 뒤 줄도),
  문단 모양(paraPr 원본 값 + mm/pt), 글자 모양(레터 런·글 런 — charPr id 와 요약), 런 범위, 줄 배치 관측(linesegarray 줄마다 — 캐시 없으면 null),
  번호(개요·자동 번호 정의), 정확한 서식 지문(fp)과 라벨(S1… — 문서 첫 등장 순 별칭).
- 서식 라벨 = 문단 모양 + 글자 모양(글 런, 레터 런이 다르면 그것도) + 앞 공백·레터 뒤 공백 꼴. **레터 글자 자체는 넣지 않는다**(레터는 kind·family·shape).
  값은 원본 정수에서 바꾼 그대로(반올림 묶기 없음) — 오차로 같게 볼 묶음은 2단계(오차 기준 지침)."""
import hashlib
import json
import re
import time
from collections import Counter, defaultdict

from app import headings, heading_rules as R
from app.hwpx_format import ALIGN, _spacing_boxes

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
P, RUN, TBL, TC, SUBLIST, LINESEG = (HP + t for t in ("p", "run", "tbl", "tc", "subList", "linesegarray"))
HU_MM = 25.4 / 7200
VERSION = 4  # 2 (2026-11-09): 번호형 모양 키 정규화·형제 묶음 간격·그릇 key·S 묶기 고침 · 3 (2026-11-09): 칸 사슬에 fill(3단계 표 구조) — 옛 결과는 2·3단계가 1단계를 다시 뽑음
#              4 (2026-11-17): 내장 규칙에 줄 첫머리 「:」 레터(b.colon) — 옛 결과는 그 줄을 보통 글로 두었다
OBJECT_TAGS = {"tbl", "pic", "ole", "container", "equation", "line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine",
               "textart", "chart", "video"}
# hp:subList 를 품은 요소 → 자리 이름(블록 트리가 안 걷는 곳 포함)
AREA_OF = {"tc": "cell", "drawText": "shape", "caption": "caption", "header": "header", "footer": "footer", "footNote": "footnote",
           "endNote": "endnote", "masterPage": "master"}
CHAR_KEYS = ("font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct", "script")
LINE_FIELDS = ("textpos", "vertpos", "vertsize", "textheight", "baseline", "spacing", "horzpos", "horzsize", "flags")
FLAG_INDENT = 1 << 20  # lineseg flags bit 20 — 그 줄이 들여쓰기/내어쓰기 자리(references/HWPX_포맷.md 조판 규칙)


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _mm(v, scale=1):
    return round(int(v or 0) / scale * HU_MM, 2)


# ---- 문단 모양(원본 paraPr) ------------------------------------------------------------------------

def para_shape(doc, pid, cache):
    """paraPr id → 문단 모양 dict(원본 값 그대로 — 단위가 HWPUNIT 이 아니면 그 단위와 값을 따로 둔다). cache 는 같은 실행 안에서 재사용."""
    if pid in cache:
        return cache[pid]
    pp = doc._defs["paraPr"].get(pid)
    out = {"paraPr": pid}
    if pp is None:
        cache[pid] = out
        return out
    a = pp.find(HH + "align")
    out["align"] = (a.get("horizontal") or "").lower() or None if a is not None else None
    out["valign"] = (a.get("vertical") or "").lower() or None if a is not None else None
    box, scale = _spacing_boxes(pp)[0]
    m, ls = box.find(HH + "margin"), box.find(HH + "lineSpacing")
    for key, tag, mm in (("firstLineMm", "intent", True), ("indentLeftMm", "left", True), ("indentRightMm", "right", True),
                         ("spaceBeforePt", "prev", False), ("spaceAfterPt", "next", False)):
        e = m.find(HC + tag) if m is not None else None
        if e is None:
            out[key] = 0.0
            continue
        unit = e.get("unit", "HWPUNIT")
        if unit != "HWPUNIT":
            out[key], out.setdefault("units", {})[key] = None, {"unit": unit, "value": e.get("value")}
            continue
        v = int(e.get("value", 0)) / scale
        out[key] = round(v * HU_MM, 2) if mm else round(v / 100, 2)
    if ls is not None:
        t, v = ls.get("type") or "PERCENT", int(ls.get("value") or 0)
        # PERCENT 는 ×1, 그 밖(FIXED·AT_LEAST·BETWEEN_LINES)은 HWPUNIT(switch 없는·default 는 ×2) → pt
        out["lineSpacing"] = {"type": t, "value": v if t == "PERCENT" else round(v / scale / 100, 2), "unit": "%" if t == "PERCENT" else "pt"}
    else:
        out["lineSpacing"] = None
    first = out.get("firstLineMm") or 0.0
    out["hangMm"] = round(-first, 2) if first else 0.0  # 둘째 줄이 첫 줄보다 들어간 폭(내어쓰기 양수, 들여쓰기 음수)
    h = pp.find(HH + "heading")
    if h is not None and h.get("type", "NONE") != "NONE":
        out["heading"] = {"type": h.get("type"), "idRef": h.get("idRef"), "level": int(h.get("level", 0)) + 1}
    bs = pp.find(HH + "breakSetting")
    if bs is not None:
        out["break"] = {k: bs.get(k) for k in ("breakLatinWord", "breakNonLatinWord", "widowOrphan", "keepWithNext", "keepLines",
                                               "pageBreakBefore", "lineWrap") if bs.get(k) is not None}
    b = pp.find(HH + "border")
    if b is not None and b.get("borderFillIDRef") not in (None, "0"):
        out["border"] = {"borderFill": b.get("borderFillIDRef"), "connect": b.get("connect"), "ignoreMargin": b.get("ignoreMargin")}
    if pp.get("tabPrIDRef") not in (None, "0"):
        out["tabPr"] = pp.get("tabPrIDRef")
    for k in ("condense", "fontLineHeight", "snapToGrid"):
        if pp.get(k) not in (None, "0"):
            out[k] = pp.get(k)
    cache[pid] = out
    return out


# ---- 글자 모양 · 런 범위 -------------------------------------------------------------------------------

def _char(doc, cid, cache):
    if cid not in cache:
        s = doc._char_summary(doc._defs["charPr"].get(cid))
        cache[cid] = {"charPr": cid, **{k: s.get(k) for k in CHAR_KEYS if s.get(k) not in (None, False) or k in ("bold", "font", "sizePt")},
                      **({"fontLatin": s["fontLatin"]} if s.get("fontLatin") and s.get("fontLatin") != s.get("font") else {})}
    return cache[cid]


def run_ranges(doc, p):
    """[[시작, 끝, charPr id], …] — 블록 글(doc._text)과 같은 글자 위치(파이썬 글자), 글 없는 런은 뺀다."""
    out, pos = [], 0
    for r in p.iterchildren(RUN):
        t = "".join(doc._slot_text(s) for s in doc._run_slots(r))
        if t:
            cid = r.get("charPrIDRef", "0")
            if out and out[-1][2] == cid and out[-1][1] == pos:
                out[-1][1] = pos + len(t)
            else:
                out.append([pos, pos + len(t), cid])
            pos += len(t)
    return out


def _cid_at(ranges, i, fallback):
    for a, b, cid in ranges:
        if a <= i < b:
            return cid
    return ranges[-1][2] if ranges else fallback


# ---- 줄 배치 관측(linesegarray) -------------------------------------------------------------------------

def line_info(p, text, block):
    """{"cache": bool, "count", "starts"(2번째 줄부터 줄 시작 글자 위치 — 블록 lines 와 같은 UTF-16 값), "segs": [[textpos, vertpos, vertsize,
    textheight, baseline, spacing, horzpos, horzsize, flags], …], "indentLine": first|rest|None}. 캐시 없으면 {"cache": False}(줄 수 모름)."""
    la = p.find(LINESEG)
    segs = list(la) if la is not None else []
    if not segs:
        return {"cache": False}
    rows = [[int(s.get(k) or 0) for k in LINE_FIELDS] for s in segs]
    starts = (block or {}).get("lines")
    if starts is None and len(segs) > 1:
        from app import hwpx_layout  # 블록 없는 문단(머리말·글상자 …)

        class _D:  # hwpx_layout.lines 는 doc._slot_text·_an_val 만 쓴다 — 자동 번호 값은 블록 읽기에서만 셈
            _an_val = {}

            @staticmethod
            def _slot_text(k):
                return k.get("num", "")
        starts = hwpx_layout.lines(_D, p, text)
    # 한 줄 = 첫 조각(flags bit 17)이 하나 — 개체 줄은 bit 17 이 없을 수도 있어 줄 시작 수와 견줘 큰 쪽
    count = max(1 + len(starts or []), sum(1 for r in rows if r[8] & (1 << 17)) or 1)
    ind = None
    if any(r[8] & FLAG_INDENT for r in rows[1:]):
        ind = "rest"
    elif rows[0][8] & FLAG_INDENT:
        ind = "first"
    return {"cache": True, "count": count, "starts": starts or [], "segs": rows, "indentLine": ind}


# ---- 열거 ------------------------------------------------------------------------------------------------

def _index_blocks(blocks):
    out = {}

    def walk(bs, table=None):
        for b in bs:
            out[b["id"]] = b
            if b.get("type") == "table":
                for c in b.get("cells") or ():
                    out[c["id"]] = c
                    walk(c.get("blocks") or [], b)
    walk(blocks)
    return out


def _container_path(doc, p, root, blk, keys=None):
    """p 의 그릇 사슬(바깥 → 안) — [{"t": "tbl", "id", "rows", "cols"}, {"t": "cell", "id", "row", "col", "rs", "cs"}, {"t": "shape", "kind"}, …].
    keys = {그릇 요소: 번호} — 주면 그릇마다 "key"(문서 안 유일 정수, 1부터 문서 순 — id 없는 글상자·각주·표도 그릇마다 갈림)."""
    chain, els, el = [], [], p.getparent()
    while el is not None and el is not root:
        name = _local(el.tag)
        if name == "tc":
            addr, span = el.find(HP + "cellAddr"), el.find(HP + "cellSpan")
            cid = doc._rev.get(el)
            chain.append({"t": "cell", "id": cid, "row": int(addr.get("rowAddr", 0)) if addr is not None else None,
                          "col": int(addr.get("colAddr", 0)) if addr is not None else None,
                          "rs": int(span.get("rowSpan", 1)) if span is not None else 1, "cs": int(span.get("colSpan", 1)) if span is not None else 1,
                          "fill": doc._fill(el.get("borderFillIDRef"))})  # 칸 음영(#RRGGBB | None) — 3단계 표 구조의 헤더 신호(heading_tables)
        elif name == "tbl":
            tid = doc._rev.get(el)
            host = el.getparent().getparent() if el.getparent() is not None else None  # hp:tbl → hp:run → hp:p
            chain.append({"t": "tbl", "id": tid, "rows": int(el.get("rowCnt", 0)), "cols": int(el.get("colCnt", 0)),
                          "cells": len(blk[tid]["cells"]) if tid in blk else len(el.findall(f"{HP}tr/{HP}tc")), "_host": host})
        elif name in AREA_OF and name != "tc":
            item = {"t": AREA_OF[name]}
            if name == "drawText":
                item["kind"] = _local(el.getparent().tag) if el.getparent() is not None else None
            chain.append(item)
        if len(chain) > len(els):
            els.append(el)
        el = el.getparent()
    chain, els = chain[::-1], els[::-1]
    if keys is not None:
        for item, e in zip(chain, els):  # 바깥 먼저 매김 → 번호 = 그릇이 문서에 처음 나오는 순
            item["key"] = keys.setdefault(e, len(keys) + 1)
    return chain


def _area(chain):
    """자리: 가장 안쪽 그릇 기준 — body · cell · box(칸 1개 표) · shape · caption · header · footer · footnote · endnote."""
    for i in range(len(chain) - 1, -1, -1):
        c = chain[i]
        if c["t"] == "cell":
            tbl = chain[i - 1] if i > 0 and chain[i - 1]["t"] == "tbl" else None
            return "box" if tbl and tbl.get("cells") == 1 else "cell"
        if c["t"] in ("shape", "caption", "header", "footer", "footnote", "endnote", "master"):
            return c["t"]
    return "body"


def enumerate_paragraphs(doc):
    """구역 XML 의 hp:p 전부 → [(el, id, 구역 번호, 블록 dict | None, 그릇 사슬)] 문서 순 + 구역마다 hp:p 수."""
    blocks = doc.blocks()
    blk = _index_blocks(blocks)
    out, per_sec, keys = [], [], {}
    for si, root in enumerate(doc._sections):
        n = 0
        for p in root.iter(P):
            bid = doc._rev.get(p)
            b = blk.get(bid) if bid else None
            pid = bid if b is not None and b.get("type") == "paragraph" else f"x{si}.{n}"
            out.append((p, pid, si, b if b is not None and b.get("type") == "paragraph" else None, _container_path(doc, p, root, blk, keys)))
            n += 1
        per_sec.append(n)
    pid_of = {id(p): pid for p, pid, *_ in out}
    for *_, chain in out:  # 표를 품은 문단 id(host) — 그래프에서 표 그릇을 그 문단에 잇는다
        for c in chain:
            if "_host" in c:
                h = c.pop("_host")
                c["host"] = pid_of.get(id(h)) if h is not None else None
    return out, per_sec, blocks


# ---- 레코드 ---------------------------------------------------------------------------------------------

def _auto_shape(label, rules, run):
    """자동 번호·글머리 라벨의 모양 키 — 글로 친 레터와 같은 규칙(R.shape_of: 「B.」 → A., 「⑵」 → ⑴). 규칙이 라벨 전체를 못 맞추면 headings._shape."""
    c = R.classify(label + " 가", rules, run)
    if c["letter"].strip() == label.strip() and c["shape"]:
        return c["shape"]
    return headings._shape(label) or label


def _num_info(doc, ps, block):
    h = ps.get("heading")
    if not h:
        return None
    out = dict(h)
    if block is not None:
        if block.get("list"):
            out["label"] = block["list"].get("label")
        out["resolved"] = bool(block.get("list") and block["list"].get("label"))
    else:
        out["resolved"] = False
    if h["type"] == "OUTLINE":
        out["resolved"] = False  # 개요 번호 글자는 블록이 계산하지 않는다(spec_hwpx_웹편집 ④)
    return out


INLINE_TITLE_MAX = 40  # 줄 안 레터 앞 괄호 제목의 글자 수(괄호 안) — spec_헤딩_추출 ② §2 「줄 안 레터」
_INLINE_CLOSE = {"(": ")", "[": "]"}


def _inline_letter(head, rest_at, rules, run):
    """헤딩 꼴 「레터 (제목) 둘째 레터 …」(spec ② §2 「줄 안 레터」 — 2026-11-18 사용자 "O ( 제목) 둥근1... 이게 패턴이라고 헤딩패턴 단순히 레터만 있는게 아니라")
    → 둘째 레터 구간 {start, kind, rule, family, letter} | None. 첫머리가 기호·번호 레터이고, 그 뒤 첫 줄이 닫힌 괄호 제목(40자까지)으로 시작하고, 빈칸 뒤에
    다른 계열의 기호·번호 레터 + 글이 올 때만. 둘째 레터 하나만 — 한 문단 안에 늘어놓은 「②」「③」 은 구간이 아니다."""
    rest = head["rest"].split(R.BR, 1)[0]
    close = _INLINE_CLOSE.get(rest[:1])
    if not close:
        return None
    j = rest.find(close, 1)
    if j < 2 or j - 1 > INLINE_TITLE_MAX or not rest[1:j].strip():
        return None
    after = rest[j + 1:]
    if not after[:1].isspace():
        return None
    c = R.classify(after, rules, run)
    if c["kind"] != "marker" or not c["letter"] or c["blank"] or c["family"] == head["family"]:
        return None
    return {"start": rest_at + j + 1 + len(c["lead"]), "kind": "marker", "rule": c["rule"], "family": c["family"], "letter": c["letter"]}


def _spans(text, head, rules, run):
    """문단 안 구간: 0 = 첫머리 판정, 그 뒤 「※」 안내가 이어지면 안내 구간 · 괄호 제목 뒤 둘째 레터면 줄 안 레터 구간(`inline` — _inline_letter),
    강제 줄 바꿈(U+2028) 뒤 줄마다 그 줄의 첫머리 판정(글 있는 줄만)."""
    spans = [{"i": 0, "start": 0, "kind": head["kind"], "rule": head["rule"], "family": head["family"], "letter": head["letter"],
              "line": 0}]
    if head["kind"] in ("marker", "label") and head["rest"]:
        rest_at = len(text) - len(head["rest"])
        first_rest = head["rest"].split(R.BR, 1)[0]
        inner = R.classify(first_rest, [r for r in rules if r.get("kind") in ("note", "footnote")], run)
        if inner["kind"] in ("note", "footnote"):
            spans.append({"i": len(spans), "start": rest_at, "kind": inner["kind"], "rule": inner["rule"], "family": inner["family"],
                          "letter": inner["letter"], "line": 0})
        elif head["kind"] == "marker":
            inl = _inline_letter(head, rest_at, rules, run)
            if inl:
                spans.append({"i": len(spans), **inl, "line": 0, "inline": True})
    if R.BR in text:
        pos = 0
        for li, line in enumerate(text.split(R.BR)):
            if li and line.strip():
                c = R.classify(line, rules, run)
                if c["kind"] not in ("plain", "empty"):
                    spans.append({"i": len(spans), "start": pos, "kind": c["kind"], "rule": c["rule"], "family": c["family"],
                                  "letter": c["letter"], "line": li})
            pos += len(line) + 1
    return spans


def _letter_run(rec):
    """레터 런 글자 — 글 런과 값이 다를 때만(charPr id 만 다르면 같은 글자 모양 → None)."""
    c, lt = rec["char"]["text"] or {}, rec["char"].get("letter")
    if not lt or {k: v for k, v in lt.items() if k != "charPr"} == {k: v for k, v in c.items() if k != "charPr"}:
        return None
    return lt


def _fp(rec):
    """정확한 서식 지문(문자열) — 문단 모양 + 글 런 글자 모양(+ 다르면 레터 런) + 앞 공백·레터 뒤 공백 꼴."""
    p = rec["para"]
    para = [p.get(k) for k in ("align", "indentLeftMm", "indentRightMm", "firstLineMm", "spaceBeforePt", "spaceAfterPt")]
    ls = p.get("lineSpacing") or {}
    ch = rec["char"]["text"] or {}
    lt = _letter_run(rec)
    char = [ch.get(k) for k in CHAR_KEYS]
    letter = [lt.get(k) for k in CHAR_KEYS] if lt else None
    return json.dumps([para, [ls.get("type"), ls.get("value")], (p.get("border") or {}).get("borderFill"), char, letter,
                       rec["leadCode"], rec["gapCode"]], ensure_ascii=False, separators=(",", ":"))


def _brief(v):
    return f"{v:g}" if isinstance(v, (int, float)) else "?"


def format_name(rec):
    """사람이 읽는 서식 이름 — 레터 글자는 넣지 않는다."""
    p, c = rec["para"], rec["char"]["text"] or {}
    ls = p.get("lineSpacing") or {}
    parts = [f"{c.get('font') or '?'} {_brief(c.get('sizePt'))}pt" + (" 굵게" if c.get("bold") else "") + (" 기울임" if c.get("italic") else "")
             + (f" {c['color']}" if c.get("color") and c.get("color") != "#000000" else "")
             + (f" 장평{c['ratioPct']}" if c.get("ratioPct") not in (None, 100) else "") + (f" 자간{c['spacingPct']}" if c.get("spacingPct") else ""),
             {"justify": "양쪽", "left": "왼쪽", "right": "오른쪽", "center": "가운데", "distribute": "배분", "distribute_space": "나눔"}.get(
                 p.get("align"), p.get("align") or "?"),
             f"왼{_brief(p.get('indentLeftMm'))}"
             + (f" 내어{_brief(-p['firstLineMm'])}" if (p.get("firstLineMm") or 0) < 0 else f" 들여{_brief(p['firstLineMm'])}" if p.get("firstLineMm") else "")
             + (f" 오른{_brief(p['indentRightMm'])}" if p.get("indentRightMm") else ""),
             f"위{_brief(p.get('spaceBeforePt'))} 아래{_brief(p.get('spaceAfterPt'))}",
             f"{ls.get('value')}{ls.get('unit')}" + ("" if ls.get("type") in (None, "PERCENT") else f"({ls['type']})")]
    lt = _letter_run(rec)
    if lt:
        parts.append("레터 " + f"{lt.get('font') or '?'} {_brief(lt.get('sizePt'))}pt" + (" 굵게" if lt.get("bold") else ""))
    if rec["leadCode"] or rec["gapCode"]:
        parts.append(f"앞{rec['leadCode'] or '0'} 뒤{rec['gapCode'] or '0'}")
    return " · ".join(parts)


def _lead_mm(lead, char):
    """앞 공백 폭 추정(mm) — 「글꼴에 어울리는 빈칸」 끈 글자(halfSpace)만 계산(빈칸 = 0.5em × 장평 × (1+자간)), 전각 공백 = 1em.
    탭·글꼴 빈칸은 계산 못 함 → None. 근거는 spec_hwpx_웹편집 ③ 실측(본문 `_2o_1` 12pt 앞 공백 4.3mm)."""
    if not lead:
        return 0.0
    if "\t" in lead or not char or not char.get("sizePt"):
        return None
    em = char["sizePt"] * 25.4 / 72
    half = 0.5 * em * (char.get("ratioPct") or 100) / 100 * (1 + (char.get("spacingPct") or 0) / 100)
    if not char.get("halfSpace") and any(ch != "\u3000" for ch in lead):
        return None
    return round(sum(em if ch == "\u3000" else half for ch in lead), 2)


# ---- \ubaa9\ucc28 \u00b7 \uc720\ud6a8 \uac04\uaca9 ------------------------------------------------------------------------------------

_TOC_REF = re.compile(r"\S *\t[ .\u00b7\u2026\-]*(?:\d{1,4}|\(\s*\ud398\uc774\uc9c0\s*\ud45c\uae30\s*\)|-\s*\d{1,4}\s*-)\s*$")  # \ud0ed + \ucabd \ud45c\uae30\ub85c \ub05d\ub098\ub294 \ubaa9\ucc28 \uc904


def toc_ids(groups):
    """\ubaa9\ucc28 \ubb38\ub2e8 id \u2014 \ud615\uc81c \ubb38\ub2e8 \uc5f4\uc5d0\uc11c \ucabd \ud45c\uae30 \uc904\u00b7\ube48 \uc904\u00b7\ucabd \ud45c\uae30 \uc904 \ubc14\ub85c \uc55e \uc904\uc774 \uc774\uc5b4\uc9c4 \ubb36\uc74c \uc911 \ucabd \ud45c\uae30 \uc904\uc774 3\uac1c \uc774\uc0c1\uc778 \uac83(headings.toc_ids \ub97c \u300c(\ud398\uc774\uc9c0 \ud45c\uae30)\u300d \uae4c\uc9c0 \ub113\ud798)."""
    out = set()
    for items in groups:
        ref = [bool(_TOC_REF.search(t)) for _, t in items] + [False]
        run, n = [], 0
        for i, it in enumerate(items + [None]):
            if it and (ref[i] or ref[i + 1] or not it[1].strip()):
                run.append(it[0])
                n += ref[i]
            else:
                out |= set(run) if n >= 3 else set()
                run, n = [], 0
    return out


def _pitch(rec):
    """\ube48 \ubb38\ub2e8 \ud55c \uc904\uc758 \ub192\uc774(pt) \u2014 \uc904 \ubc30\uce58 \uad00\uce21(vertsize + spacing)\uc774 \uc788\uc73c\uba74 \uadf8\uac83, \uc5c6\uc73c\uba74 \uae00\uc790 \ud06c\uae30 \u00d7 \uc904 \uac04\uaca9."""
    segs = rec["line"].get("segs")
    if segs:
        return round(sum(s[2] + s[5] for s in segs) / 100, 2)
    size = (rec["char"]["text"] or {}).get("sizePt") or 10.0
    ls = rec["para"].get("lineSpacing") or {}
    if ls.get("type") in (None, "PERCENT"):
        return round(size * (ls.get("value") or 160) / 100, 2)
    return round(max(ls.get("value") or size, size), 2)


def _gaps(groups_recs):
    """\ud615\uc81c \ubb38\ub2e8 \uc5f4\ub9c8\ub2e4 \uae00 \uc788\ub294 \ubb38\ub2e8\uc758 \uc720\ud6a8 \uac04\uaca9 \u2014 gaps{abovePt, belowPt, spacersAbove, spacersBelow}: \uc0ac\uc774 \ube48 \ubb38\ub2e8(\uac04\uaca9 \uc7a5\uce58)\uc758 \uc904 \ub192\uc774 + \uadf8 \uc704\u00b7\uc544\ub798 \uac04\uaca9 +
    \uc774 \ubb38\ub2e8 \uc704 \uac04\uaca9 + \uc55e(\ub4a4) \uae00 \ubb38\ub2e8\uc758 \uc544\ub798(\uc704) \uac04\uaca9. \ube48 \ubb38\ub2e8\uc740 spacer{pitchPt}."""
    for recs in groups_recs:
        texts = [i for i, r in enumerate(recs) if r["kind"] not in ("empty", "object")]
        for r in recs:
            if r["kind"] in ("empty", "object"):
                r["spacer"] = {"pitchPt": _pitch(r)}
        for k, i in enumerate(texts):
            r = recs[i]
            prev, nxt = (texts[k - 1] if k else -1), (texts[k + 1] if k + 1 < len(texts) else len(recs))

            def between(a, b):
                return [recs[j] for j in range(a + 1, b) if recs[j]["kind"] == "empty"]
            up, down = between(prev, i), between(i, nxt)
            sp = lambda x: (x["para"].get("spaceBeforePt") or 0) + (x["para"].get("spaceAfterPt") or 0)  # noqa: E731
            above = (r["para"].get("spaceBeforePt") or 0) + (recs[prev]["para"].get("spaceAfterPt") or 0 if prev >= 0 else 0) \
                + sum(_pitch(e) + sp(e) for e in up)
            below = (r["para"].get("spaceAfterPt") or 0) + (recs[nxt]["para"].get("spaceBeforePt") or 0 if nxt < len(recs) else 0) \
                + sum(_pitch(e) + sp(e) for e in down)
            r["gaps"] = {"abovePt": round(above, 2), "belowPt": round(below, 2), "spacersAbove": len(up), "spacersBelow": len(down)}


# ---- \uc11c\uc2dd \ub77c\ubca8(F \uc815\ubc00 \u00b7 S \uc624\ucc28 \ubb36\uc74c) ---------------------------------------------------------------------

def _alias(tol):
    out = {}
    for i, grp in enumerate(tol.get("fontAliases") or ()):
        for name in grp:
            out[str(name).casefold()] = f"\uae00\uaf34\uad70{i + 1}"
    return out


def _color_group(c, tol):
    for i, grp in enumerate(tol.get("colors") or ()):
        if c in grp or (c and str(c).upper() in [str(x).upper() for x in grp if x]):
            return f"\uc0c9\uad70{i + 1}"
    return c


def _category(rec, tol, alias):
    p, c, lt = rec["para"], rec["char"]["text"] or {}, _letter_run(rec)
    font = lambda x: alias.get(str((x or {}).get("font") or "").casefold(), (x or {}).get("font"))  # noqa: E731
    if rec["kind"] in ("empty", "object"):
        return ("spacer", rec["kind"], (p.get("lineSpacing") or {}).get("type"))
    first = p.get("firstLineMm") or 0
    lcat = (bool(lt.get("bold")), font(lt), _color_group(lt.get("color"), tol)) if lt else None
    return (p.get("align"), bool(c.get("bold")), bool(c.get("italic")), bool(c.get("underline")), font(c), _color_group(c.get("color"), tol),
            (first > 0) - (first < 0), (p.get("lineSpacing") or {}).get("type"), c.get("script"), (p.get("border") or {}).get("borderFill"), lcat)


_NUM_TOL = {"indentLeftMm": "indentMm", "indentRightMm": "indentMm", "firstLineMm": "firstLineMm", "spaceBeforePt": "spacePt",
            "spaceAfterPt": "spacePt", "lineSpacing": "lineSpacingPct", "lineSpacingPt": "lineSpacingPt", "sizePt": "sizePt",
            "ratioPct": "ratioPct", "spacingPct": "spacingPct", "leadSpaces": "leadSpaces", "leadMm": "leadMm", "gapSpaces": "leadSpaces",
            "letterSizePt": "sizePt"}
_TOL_FALLBACK = {"lineSpacingPt": 1.0}  # \uc624\ucc28 \uae30\uc900\uc5d0 \uadf8 \ud0a4\uac00 \uc5c6\uc744 \ub54c(\uc0c8 \ud0a4 \u2014 \uc61b \uc800\uc7a5\ubcf8\u00b7\uc9c1\uc811 \uc900 dict)


def _ls_num(p):
    """\uc904 \uac04\uaca9 (\ud0a4, \uac12) \u2014 PERCENT \ub294 %(lineSpacingPct \ub85c \uacac\uc90c), \uace0\uc815\u00b7\ucd5c\uc18c\u00b7\uc5ec\ubc31(FIXED\u00b7AT_LEAST\u00b7BETWEEN_LINES)\uc740 pt(lineSpacingPt)."""
    ls = p.get("lineSpacing") or {}
    return ("lineSpacing" if ls.get("type") in (None, "PERCENT") else "lineSpacingPt"), ls.get("value")


def _numbers(rec, titled=None):
    """S \ubb36\uc74c\uc5d0\uc11c \uc624\ucc28\ub85c \uacac\uc904 \uac12. titled = \uadf8 F \uc5d0 \uc81c\ubaa9 \uc788\ub294 \ubb38\ub2e8\uc774 \uc788\ub098(None = \uc774 \ubb38\ub2e8\ub9cc \ubd04) \u2014 \uc4f8 \uc790\ub9ac(blank)\ubfd0\uc774\uba74 \ub808\ud130 \ub4a4 \uacf5\ubc31 \uce78 \uc218\ub97c \uc548 \ub123\ub294\ub2e4."""
    p, c, lt = rec["para"], rec["char"]["text"] or {}, _letter_run(rec)
    lk, lv = _ls_num(p)
    if rec["kind"] in ("empty", "object"):
        return {"sizePt": c.get("sizePt"), lk: lv}
    out = {k: p.get(k) for k in ("indentLeftMm", "indentRightMm", "spaceBeforePt", "spaceAfterPt")}
    out.update(firstLineMm=abs(p.get("firstLineMm") or 0), sizePt=c.get("sizePt"), ratioPct=c.get("ratioPct", 100),
               spacingPct=c.get("spacingPct", 0), leadSpaces=rec["leadSpaces"], leadMm=rec.get("leadMm"))
    out[lk] = lv
    if (not rec["blank"]) if titled is None else titled:
        out["gapSpaces"] = len(rec["gap"])
    if lt:
        out["letterSizePt"] = lt.get("sizePt")
    return out


def _within(a, b, tol):
    for k, v in a.items():
        w = b.get(k)
        if v is None or w is None:
            if k in ("leadMm", "gapSpaces"):
                continue  # \ud3ed\uc744 \ubaa8\ub974\uba74 \uce78 \uc218\ub85c\ub9cc \u00b7 \uc4f8 \uc790\ub9ac(blank)\ubfd0\uc778 F \ub294 \ub808\ud130 \ub4a4 \uacf5\ubc31\uc744 \uacac\uc8fc\uc9c0 \uc54a\uc74c
            if v != w:
                return False
            continue
        name = _NUM_TOL.get(k, "")
        if abs(float(v) - float(w)) > float(tol.get(name, _TOL_FALLBACK.get(name, 0)) or 0) + 1e-9:
            return False
    return set(a) - {"gapSpaces"} == set(b) - {"gapSpaces"}


def label_formats(recs, tol):
    """F(\uc815\ubc00 \uc9c0\ubb38) \u2192 S(\uc624\ucc28 \ubb36\uc74c) \ub77c\ubca8\uc744 \ub808\ucf54\ub4dc\uc5d0 \ub2e8\ub2e4(fp\u00b7fmt) \u2192 (labels S dict, formats F dict)."""
    alias = _alias(tol)
    formats, order = {}, []
    for rec in recs:
        key = _fp(rec)
        f = formats.get(key)
        if f is None:
            f = formats[key] = {"id": f"F{len(formats) + 1}", "count": 0, "rec": rec, "titled": False}
            order.append(key)
        f["count"] += 1
        f["titled"] = f["titled"] or not rec["blank"]  # F 안은 gapCode 가 같다 — 첫 문단이 쓸 자리인지에 안 달리게 F 전체로 봄
        rec["fp"] = f["id"]
    by_cat, labels, f_to_s = defaultdict(list), {}, {}
    # 제목 있는 F 먼저 — 쓸 자리(blank)뿐인 F 가 대표가 되면 레터 뒤 공백(gapSpaces) 기준이 없어 공백이 다른 제목 F 들이 한 S 로 묶인다
    for key in sorted(order, key=lambda k: (not formats[k]["titled"], -formats[k]["count"], formats[k]["rec"]["n"])):
        f = formats[key]
        rec = f["rec"]
        cat, num = _category(rec, tol, alias), _numbers(rec, f["titled"])
        sid = next((s for s, rep in by_cat[cat] if _within(num, rep, tol)), None)
        if sid is None:
            sid = f"S{len(labels) + 1}"
            by_cat[cat].append((sid, num))
            labels[sid] = {"id": sid, "name": format_name(rec), "rep": f["id"], "sample": rec["id"], "count": 0, "kinds": Counter(),
                           "variants": {}, "para": rec["para"], "char": rec["char"], "leadCode": rec["leadCode"], "gapCode": rec["gapCode"],
                           "spacer": rec["kind"] in ("empty", "object")}
        f_to_s[f["id"]] = sid
        labels[sid]["variants"][f["id"]] = f["count"]
    for rec in recs:
        lab = labels[f_to_s[rec["fp"]]]
        rec["fmt"] = lab["id"]
        lab["count"] += 1
        lab["kinds"][rec["kind"]] += 1
    # \ub77c\ubca8 \ubc88\ud638\ub97c \ubb38\uc11c \uccab \ub4f1\uc7a5 \uc21c\uc73c\ub85c \ub2e4\uc2dc \ub9e4\uae40(S1 = \ubb38\uc11c\uc5d0\uc11c \ucc98\uc74c \ub098\uc624\ub294 \ub77c\ubca8)
    first = {}
    for rec in recs:
        first.setdefault(rec["fmt"], rec["n"])
    remap = {old: f"S{i + 1}" for i, old in enumerate(sorted(labels, key=lambda s: first.get(s, 1 << 30)))}
    labels = {remap[k]: {**v, "id": remap[k], "kinds": dict(v["kinds"].most_common())} for k, v in labels.items()}
    for rec in recs:
        rec["fmt"] = remap[rec["fmt"]]
    fdict = {f["id"]: {"id": f["id"], "count": f["count"], "sample": f["rec"]["id"], "label": remap[f_to_s[f["id"]]], "name": format_name(f["rec"])}
             for f in formats.values()}
    return dict(sorted(labels.items(), key=lambda kv: int(kv[0][1:]))), fdict


# ---- 1\ub2e8\uacc4 \uc2e4\ud589 ------------------------------------------------------------------------------------------

def _classify_all(texts, rules, run, flags):
    return [R.classify(t, rules, run, caption=c, toc=tc) for t, (c, tc) in zip(texts, flags)]


def extract(doc, store=None, extra_rules=(), *, doc_key=None, tol=None):
    """1\ub2e8\uacc4 \u2014 \ubb38\uc11c \u2192 {"version", "counts", "paras": [\ub808\ucf54\ub4dc\u2026], "labels": {S\u2026}, "formats": {F\u2026}, "review": {...}, "rules": {...}, "warnings", "seconds"}.
    store = \uaddc\uce59 \uc800\uc7a5\uc18c(None = \uc9c0\uae08 \uc804\uc5ed), extra_rules = \uc2dc\ud5d8\ud560 \uc784\uc2dc \uaddc\uce59(\ubc30\uc6b4 \uaddc\uce59 \ub4a4), doc_key = \uc774 \ubb38\uc11c sha256(\ud6c4\ubcf4 \uaddc\uce59), tol = \uc624\ucc28 \uae30\uc900(None = \uc9c0\uce68)."""
    from app import heading_guides
    t0 = time.monotonic()
    st = store if store is not None else R.load()
    tol = tol or heading_guides.tolerance()
    rules = R.active(st, extra_rules, doc_key=doc_key)
    run = R._Run()
    items, per_sec, blocks = enumerate_paragraphs(doc)
    texts = [b["text"] if b is not None else doc._text(p) for p, pid, si, b, chain in items]
    # 형제 묶음 = 같은 부모 요소 — 요소 자체를 키로(id() 는 칸 subList 처럼 아무도 안 쥔 임시 프록시면 매번 달라 묶음이 흩어짐)
    parents = [p.getparent() for p, *_ in items]
    siblings = defaultdict(list)
    for (p, pid, si, b, chain), text, par in zip(items, texts, parents):
        siblings[par].append((pid, text))
    toc = toc_ids(list(siblings.values()))
    pcache, ccache, char_summ = {}, {}, {}
    recs, groups = [], defaultdict(list)
    for n, ((p, pid, si, b, chain), text) in enumerate(zip(items, texts)):
        objects = sorted({_local(o.tag) for r in p.iterchildren(RUN) for o in r if _local(o.tag) in OBJECT_TAGS})
        caption = bool(b and headings.is_caption(b)) or any(c["t"] == "caption" for c in chain)
        head = R.classify(text, rules, run, caption=caption and bool(text.strip()), toc=pid in toc)
        if head["kind"] == "empty" and objects:
            head["kind"] = "object"
        ps = para_shape(doc, p.get("paraPrIDRef"), pcache)
        ranges = run_ranges(doc, p)
        first_cid = doc._char_id(p)
        letter_cid = _cid_at(ranges, len(head["lead"]), first_cid) if head["letter"] else None
        rest_at = len(text) - len(head["rest"]) if head["rest"] else None
        text_cid = _cid_at(ranges, rest_at, first_cid) if rest_at is not None and rest_at < len(text) else first_cid
        tc = _char(doc, text_cid, ccache)
        lc = _char(doc, letter_cid, ccache) if letter_cid else None
        if text_cid not in char_summ:
            char_summ[text_cid] = doc._char_summary(doc._defs["charPr"].get(text_cid))
        cell = next((c for c in reversed(chain) if c["t"] == "cell"), None)
        tbl = next((c for c in reversed(chain) if c["t"] == "tbl"), None)
        rec = {
            "id": pid, "block": b is not None, "n": n, "sec": si, "area": _area(chain), "path": chain,
            "table": tbl["id"] if tbl else None, "cell": cell["id"] if cell else None, "row": cell["row"] if cell else None,
            "col": cell["col"] if cell else None, "depth": sum(1 for c in chain if c["t"] == "tbl"),
            "text": text, "objects": objects,
            "kind": head["kind"], "rule": head["rule"], "family": head["family"], "shape": head["shape"], "letter": head["letter"],
            "lead": head["lead"], "gap": head["gap"], "rest": head["rest"], "blank": head["blank"], "ord": head["ord"],
            "leadCode": headings.ws_code(head["lead"]), "gapCode": headings.ws_code(head["gap"]), "leadSpaces": len(head["lead"]),
            "skeleton": headings.skeleton(text.split(R.BR, 1)[0])["full"] if text.strip() else "",
            "para": ps, "char": {"text": tc, "letter": lc}, "runs": ranges,
            "line": line_info(p, text, b), "style": (b or {}).get("style"),
        }
        rec["form"] = rec["leadCode"] + (rec["shape"] or "") + rec["gapCode"] if rec["letter"] else rec["leadCode"]
        rec["leadMm"] = _lead_mm(head["lead"], {**char_summ[text_cid], "sizePt": tc.get("sizePt")})
        rec["spans"] = _spans(text, head, rules, run)
        num = _num_info(doc, ps, b)
        if num:
            rec["num"] = num
            if num["type"] in ("BULLET", "NUMBER") and num.get("label") and rec["kind"] in ("plain", "empty"):
                # 자동 번호·글머리: 레터 = 한글이 글 앞에 찍는 라벨(글에는 없음), 앞 공백 없음, 레터 뒤 공백 = 글 앞 공백(headings.head_of 와 같음)
                lead, rest = R.split_lead(text)
                fam = "auto-bullet" if num["type"] == "BULLET" else "auto-number"
                rec.update(kind="marker", rule=f"auto.{num['type'].lower()}", family=fam, letter=num["label"],
                           shape=_auto_shape(num["label"], rules, run), lead="", gap=lead, rest=rest, blank=not rest.strip(), auto=True,
                           leadCode="", gapCode=headings.ws_code(lead), leadSpaces=0)
                rec["form"] = "list:" + rec["shape"] + rec["gapCode"]
                rec["spans"][0].update(kind="marker", rule=rec["rule"], family=fam, letter=num["label"])
        if b is not None and b.get("outlineLevel"):
            rec["outlineLevel"] = b["outlineLevel"]
        recs.append(rec)
        groups[parents[n]].append(rec)
    _gaps(list(groups.values()))
    labels, formats = label_formats(recs, tol)
    kinds = Counter(r["kind"] for r in recs)
    total_xml = sum(per_sec)
    return {
        "version": VERSION, "paras": recs, "labels": labels, "formats": formats,
        "counts": {"paragraphs": len(recs), "xml": total_xml, "check": len(recs) == total_xml, "perSection": per_sec,
                   "withBlock": sum(r["block"] for r in recs), "kinds": dict(kinds.most_common()),
                   "areas": dict(Counter(r["area"] for r in recs).most_common()), "labels": len(labels), "formats": len(formats),
                   "rules": Counter(r["rule"] for r in recs if r["rule"]).most_common()},
        "review": review_set(recs, rules, run, st),
        "rules": {"version": st.get("version", 0), "active": [r["id"] for r in rules]},
        "tolerance": tol, "warnings": run.warnings, "seconds": round(time.monotonic() - t0, 3),
    }


# ---- \ubcf4\uac15 \ub300\uc0c1(LLM \uaddc\uce59 \uc81c\uc548 \uc785\ub825) -------------------------------------------------------------------------

SINGLE_MAX = 20  # 1\ud68c\uc9dc\ub9ac \ubabb \ub9de\ucda4 \ubb36\uc74c\uc744 \uba87 \uac1c\uae4c\uc9c0 \ubb3b\ub098


def _excerpt(rec, n=80):
    t = rec["text"].replace(R.BR, "\u21b5").replace("\t", "\u21e5")
    return t[:n] + ("\u2026" if len(t) > n else "")


def _example(rec, recs):
    i = rec["n"]
    near = lambda j: (recs[j]["kind"], recs[j]["letter"]) if 0 <= j < len(recs) else None  # noqa: E731
    return {"id": rec["id"], "text": _excerpt(rec), "area": rec["area"], "fmt": rec.get("fmt"), "prev": near(i - 1), "next": near(i + 1)}


def _first_line(rec):
    return rec["text"][len(rec["lead"]):].split(R.BR, 1)[0]


def review_set(recs, rules, run, store=None):
    """\uaddc\uce59 \ubcf4\uac15 \ub300\uc0c1 \ubb36\uc74c \u2014 {"unmatched": [{key, shape, count, ids, examples}], "conflicts": [{key, rules, shape, count, ids, examples}]}.
    unmatched = \uc5b4\ub5a4 \uaddc\uce59\uc5d0\ub3c4 \uc548 \ub9de\uc558\ub294\ub370(plain\u00b7\uaddc\uce59 \uc5c6\uc74c) \uc55e\uba38\ub9ac\uc5d0 \uae30\ud638\u00b7\uc9e7\uc740 \ud1a0\ud070\uc774 \uc788\ub294 \ubb38\ub2e8(headings.skeleton core) \u2014 \uaf34\ubcc4, 2\ud68c \uc774\uc0c1 \ub610\ub294 \uc81c\ubaa9\uc774 \ubd99\uc740 \uae30\ud638 1\ud68c(SINGLE_MAX \uac1c\uae4c\uc9c0).
    conflicts = \uccab\uba38\ub9ac\uc5d0 \uc885\ub958\uac00 \ub2e4\ub978 \uaddc\uce59 \ub458 \uc774\uc0c1\uc774 \ub9de\ub294 \ubb38\ub2e8(\uba3c\uc800 \uc628 \uaddc\uce59\uc774 \uc774\uacbc\ub2e4) \u2014 (\uc774\uae34 \uaddc\uce59, \uc9c4 \uaddc\uce59, \uaf34)\ubcc4. \uc800\uc7a5\uc18c keeps(LLM \uc774 \u300c\uadf8\ub300\ub85c\u300d \ub77c\uace0 \ud55c \uac83)\ub294 \ube80\ub2e4.
    \uc55e\uc120(first) \ubc30\uc6b4 \uaddc\uce59\uc774 \uc774\uae34 \ubb38\ub2e8\ub3c4 \ube80\ub2e4(\uadf8 \uaddc\uce59\uc774 \uace7 \ucda9\ub3cc\uc744 \ubc14\ub85c\uc7a1\uc740 \ud310\uc815)."""
    keeps = set((store or {}).get("keeps") or ())
    groups = defaultdict(list)
    for rec in recs:
        if rec["kind"] != "plain" or rec["rule"]:
            continue
        core = headings.skeleton(rec["text"].split(R.BR, 1)[0])["core"]
        if core:
            groups[core].append(rec)
    unmatched, singles = [], 0
    for k, v in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(v) == 1:
            sym = not k[:1].isalnum()
            titled = bool(headings.skeleton(_first_line(v[0]))["rest"].strip())
            if not (sym and titled) or singles >= SINGLE_MAX:
                continue
            singles += 1
        unmatched.append({"key": f"u:{k}", "shape": k, "count": len(v), "ids": [r["id"] for r in v], "examples": [_example(r, recs) for r in v[:6]]})
    conflicts = defaultdict(list)
    firsts = {r["id"] for r in rules if r.get("first")}
    for rec in recs:
        if rec["kind"] in ("empty", "object", "toc", "caption", "plain") or not rec["rule"]:
            continue
        if rec.get("auto") or rec["rule"] in firsts:
            continue  # 앞선 배운 규칙(first)이 이긴 문단 = 이미 충돌을 바로잡은 판정 — 다시 묻지 않음
        first = _first_line(rec)
        for r in rules:
            if r["id"] == rec["rule"] or r["kind"] == rec["kind"] or {r["kind"], rec["kind"]} <= set(R.HEADISH):
                continue  # 레터 ↔ 라벨(「[1]」 = 괄호 번호이자 괄호 라벨)은 둘 다 헤딩 후보라 충돌로 안 봄
            whole = r.get("scope") == "whole"
            probe = first.strip() if whole else first[:R.MATCH_TEXT_MAX]
            if r.get("builtin"):
                m = r["rx"].fullmatch(probe) if whole else r["rx"].match(probe)
            else:
                m = run.match(r, probe, whole)
            if m is not None and (whole or m.end() > 0):
                shape = headings.skeleton(first)["core"] or first.strip()[:8]
                key = f"c:{rec['rule']}>{r['id']}:{shape}"
                if key not in keeps:
                    conflicts[key].append(rec)
                break
    conf = [{"key": k, "rules": k[2:].split(":", 1)[0].split(">"), "shape": k.split(":", 2)[2], "count": len(v), "ids": [r["id"] for r in v],
             "examples": [_example(r, recs) for r in v[:6]]} for k, v in sorted(conflicts.items(), key=lambda kv: -len(kv[1]))]
    return {"unmatched": unmatched, "conflicts": conf}


# ---- \uaddc\uce59 \uc2dc\ud5d8(LLM \uc81c\uc548 \uac80\uc99d \u00b7 \ud6c4\ubcf4 \uaddc\uce59\uc744 \ub2e4\ub978 \ubb38\uc11c\uc5d0) ------------------------------------------------------

def test_rule(rule, result, store=None, *, doc_key=None, targets=()):
    """\uc784\uc2dc \uaddc\uce59 \ud558\ub098\ub97c \uc9c0\uae08 \ud310\uc815 \uc704\uc5d0 \ub354\ud588\uc744 \ub54c \ubc14\ub00c\ub294 \ubb38\ub2e8 \u2192 {"ok"(\uc548\uc804 \uac80\uc0ac \ud1b5\uacfc), "error", "changed": [{id, before, after}], "fixed"(\ub300\uc0c1 \uc548\uc5d0\uc11c \ubc14\ub010 \uc218),
    "taken"(\ub300\uc0c1 \ubc16 plain \uc744 \uac00\uc838\uac04 \uc218), "broken"(\ub300\uc0c1 \ubc16 plain \uc544\ub2cc \ud310\uc815\uc744 \ubc14\uafbc \uc218), "takenExamples", "brokenExamples", "warnings"}.
    rule \uc774 \ub9de\ub294 \ubb38\ub2e8\ub9cc \ub2e4\uc2dc \ud310\uc815\ud55c\ub2e4(\ub9de\uc9c0 \uc54a\uc73c\uba74 \ud310\uc815\uc774 \ubc14\ub014 \uc218 \uc5c6\uc74c)."""
    st = store if store is not None else R.load()
    out = {"ok": False, "error": None, "changed": [], "fixed": 0, "taken": 0, "broken": 0, "takenExamples": [], "brokenExamples": [], "warnings": []}
    try:
        trial = {**R._clean_rule({**rule, "status": "candidate"}, source=rule.get("source") or "llm"), "id": rule.get("id") or "trial"}
    except ValueError as e:
        out["error"] = str(e)
        return out
    rules = R.active(st, [trial], doc_key=doc_key)
    run = R._Run()
    probe = next(r for r in rules if r["id"] == trial["id"])
    targets = set(targets)
    for rec in result["paras"]:
        if rec["kind"] in ("empty", "object", "toc", "caption"):
            continue
        body = rec["text"][len(rec["lead"]):]
        first = body.split(R.BR, 1)[0]
        whole = probe.get("scope") == "whole"
        m = run.match(probe, first.strip() if whole else first[:R.MATCH_TEXT_MAX], whole)
        if m is None or (not whole and m.end() == 0):
            continue
        new = R.classify(rec["text"], rules, run)
        if new["rule"] != rec["rule"] or new["kind"] != rec["kind"]:
            item = {"id": rec["id"], "before": [rec["kind"], rec["rule"]], "after": [new["kind"], new["rule"]], "text": _excerpt(rec, 50)}
            out["changed"].append(item)
            if rec["id"] in targets:
                out["fixed"] += 1
            elif rec["kind"] == "plain" and not rec["rule"]:
                out["taken"] += 1
                out["takenExamples"].append(item)
            else:
                out["broken"] += 1
                out["brokenExamples"].append(item)
    out["warnings"] = run.warnings
    out["takenExamples"], out["brokenExamples"] = out["takenExamples"][:5], out["brokenExamples"][:5]
    out["ok"] = not run.warnings
    return out


def trial_candidates(result, store=None, *, doc_key):
    """\ub2e4\ub978 \ubb38\uc11c\uc5d0\uc11c \uac80\uc99d\ub41c \ud6c4\ubcf4 \uaddc\uce59(status candidate, globalHint)\uc744 \uc774 \ubb38\uc11c\uc5d0 \uc2dc\ud5d8 \u2192 {rid: {"passed", "fixed", "taken", "broken"}}.
    \ud1b5\uacfc = \ubabb \ub9de\ucda4 \ubb38\ub2e8\uc744 \ud558\ub098 \uc774\uc0c1 \uace0\uce58\uace0 \ub2e4\ub978 \ud310\uc815\uc744 \ud558\ub098\ub3c4 \uc548 \ubc14\uafb8\uba70 plain \uc744 \uac00\uc838\uac04 \uc218 \u2264 \ubb38\ud131. \ud638\ucd9c\ud55c \ucabd\uc774 R.add_docs \ub85c \uae30\ub85d\ud55c\ub2e4."""
    st = store if store is not None else R.load()
    unmatched = {i for g in result["review"]["unmatched"] for i in g["ids"]}
    plain = sum(1 for r in result["paras"] if r["kind"] == "plain" and not r["rule"])
    out = {}
    for rule in st.get("rules") or ():
        if rule.get("status") != "candidate" or not rule.get("enabled", True) or not rule.get("globalHint") or doc_key in (rule.get("docs") or ()):
            continue
        t = test_rule({**rule, "first": rule.get("first")}, result, {**st, "rules": [r for r in st["rules"] if r["id"] != rule["id"]]},
                      doc_key=doc_key, targets=unmatched)
        passed = t["ok"] and t["fixed"] > 0 and t["broken"] == 0 and t["taken"] <= max(3, plain // 100)
        out[rule["id"]] = {"passed": passed, **{k: t[k] for k in ("fixed", "taken", "broken", "error")}}
    return out


