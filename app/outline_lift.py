"""표 제목을 템플릿의 레벨로(spec_hwpx_웹편집 ② §8-7) — 본문 템플릿의 줄 **바로 위**에 있는 제목 표(1칸 상자 · 번호 칸 + 제목 칸 띠 · 3행 표)를 그 템플릿의 표 레벨로 넣는다.

2026-11-16 사용자 "그리고 이 테이블도 템플릿의 L1 으로 할 수 있도록 해줘. 이런 문서들이 꽥 많거든" → 답 「같은 꼴 표를 한 번에」 · 「표시·구조 + Enter 먼저」.
(제목이 표 안에 있는 문서 — 「사업과제 1(전략): …」 상자 아래 「□ › o › -」: 헤딩 추출은 1칸 상자를 투명하게 보고 레터 없는 글은 헤딩 후보가 아니라 그 표가 템플릿에 못 들었다.)
같은 날 넓힘 — 사용자 "테이블 1개 행 또는 3개 행에 3. N 이런식으로 헤딩을 주는 경우가 있어서 그래 동일한 테이블 서식과 헤딩 서식을 가지고 있으면 될거 같은데" → 답 「여러 칸·3행 표까지」
(② §8-7 「넓힘」): 여러 칸·3행 제목 표 · 꼴을 내용으로 견줌 · 같은 꼴이면 아래에 템플릿 줄이 없는 표도 · 표 레벨 여러 층(띠 › 상자 › □).

- **오버레이만** 바꾼다(문서·그래프는 그대로 — 템플릿 종속 §8-2 와 같은 자리): 표 레벨을 끼울 자리부터 템플릿의 레벨을 한 칸씩 밀고 거기에 **표 줄**을 둔다. 템플릿 번호는 그대로(「T1」).
  표 레벨은 L1 부터 d 층(`lift.tiers[층] = [꼴…]` — `depth`), 글 레벨은 L d+1 부터.
- **제목 표**(`title_of`) = 글 없는 문단이 표 하나만 품고, 그 표가 1~3행 · 칸 안에 개체가 없고 · 글 합이 200자까지이며, 글 있는 칸이 하나(제목 칸)이거나 같은 행의 둘(번호 칸 + 제목 칸).
- 표 줄 = **칸 안 제목 문단**(제목 칸의 글이 있는 첫 문단)의 id 를 열쇠로 한 줄 `{tpl, level, letter: "", key: "▦", role: "table", table: 표 id, base: 그 표가 들어선 자리의 옛 부모, num?: 번호 칸 문단 id}` —
  레터가 없으므로 `outline_edit.sync` 는 표 줄을 「문단이 살아 있나」 로만 본다(제목 글을 고쳐도 줄이 남는다). 본문 문단 열에서의 자리는 그 표를 품은 문단(호스트)이다(`host_of` · `aliases` — server `_outline_seq` 가 그 자리에 줄을 놓는다).
- **같은 꼴**(`sig_of`) = 표의 꼴(행 · 칸 · 제목 칸과 번호 칸의 자리) + 칸마다 테두리·바탕의 내용 + 제목 글의 겉모습. 정의 번호로 견주지 않는다.
- 후보(`candidates`) = **닻**(간격 문단만 사이에 두고 이 템플릿의 표 줄이나 첫 글 레벨 줄 바로 위에 있는 제목 표)이 있는 꼴의 본문 제목 표 **모두** — 꼴마다 묶음. 들어갈 레벨은 자리로 정한다
  (닻 아래 줄의 레벨 − 1 과 닻 바로 위 표 줄의 레벨 사이 — 그 사이에 표 레벨이 있으면 거기에 더하고 없으면 새 표 레벨을 끼운다). 묶음 하나를 통째로 넣는다(`lift`).
- 넣으면(`lift`): 표 줄과 첫 글 레벨 줄의 부모를 본문 차례로 다시 맨다(`_relink` — 표 줄의 부모 = 앞의 더 얕은 표 줄 · 글 줄의 부모 = 가장 가까운 앞 표 줄. 옛 부모는 `adopt` 에 — 떼면 되돌림).
- 떼기(`unlift`) = 표 줄을 모두 빼고 레벨을 되돌린다. 2단계를 다시 돌리면(`carry`) 같은 앵커의 템플릿에 기록한 층을 안쪽부터 같은 꼴로 다시 건다 — 새로 생긴 같은 꼴 표도 든다.
- 표 줄의 키: Enter = 표 **아래**에 첫 글 레벨의 새 줄(`outline_edit.plan_enter` 의 표 가지) — 그 밖(Alt+Enter · 레벨 · 끌기 · 지우기)은 거절. 첫 글 레벨 줄은 표 레벨로 못 올린다.
"""
import copy
import hashlib
import json
import re

from app import outline_edit as OE
from app.hwpx_doc import P, RUN, SUBLIST, TBL, TC, TR
from app.hwpx_struct import OBJECTS

KEY = "▦"       # 표 제목 레벨의 정규 키(레터 없음)
ROLE = "table"  # 표 줄의 role
TITLE_MAX = 200  # 제목 글이 이보다 길면 제목 표로 보지 않는다(본문을 담은 상자)
ROWS_MAX = 3     # 제목 표의 행 수 — 1행(상자 · 번호 칸 + 제목 칸 띠) ~ 3행(위·아래 띠 + 가운데 제목)
CELLS_MAX = 12   # 칸이 이보다 많으면 자료 표
NUM_MAX = 10     # 번호 칸의 글 길이
# 번호 칸의 글 — 「1 .」 · 「3.1」 · 「3-1.」 · 「Ⅱ」 · 「IV.」 · 「가.」 · 「A)」 · 「(2)」 · 「①」 · 「제2장」
NUM = re.compile(r"(?:제\s*\d{1,2}\s*[장절편부항관]|\(\s*\d{1,2}\s*\)|\d{1,2}(?:\s*[.\-]\s*\d{1,2}){0,3}\s*[.)]?|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+\s*[.)]?|[IVX]{1,4}\s*[.)]?"
                 r"|[가나다라마바사아자차카타파하A-Za-z]\s*[.)]|[①-⑳])")

depth = OE.lift_depth  # 표 레벨 수(글 레벨은 그만큼 밀려 있다)


def _numlike(doc, x):
    """글 있는 칸 x 가 번호 칸인가 — 글 문단 하나에 번호 글만."""
    s = doc._text(x["paras"][0]).strip()
    return len(x["paras"]) == 1 and len(s) <= NUM_MAX and NUM.fullmatch(s) is not None


def title_of(doc, host):
    """host(문단)가 **제목 표 하나만** 품은 글 없는 문단이면 그 표의 뼈대 —
    {tbl, cell(제목 칸), title(제목 문단 = 제목 칸의 글이 있는 첫 문단), num(번호 칸의 문단 | None), rows, cells[행마다 칸 수], at(제목 칸 차례), numAt, all[칸…]} — 아니면 None.
    제목 표 = 1~3행 · 칸 안에 개체가 없고 · 글 합 200자까지 · 글 있는 칸이 하나(1칸 상자 · 3행 표의 가운데 제목)이거나 같은 행의 둘(번호 칸 + 제목 칸).
    글이 있는 문단 · 개체가 둘 이상 · 그림 · 글 있는 칸이 셋 이상인 표(결재란 · 자료 표) · 두 칸인데 번호 칸이 없는 표(제목 + 내용 상자) · 글이 긴 상자는 제목 표가 아니다."""
    if host is None or host.tag != P or doc._text(host).strip():
        return None
    objs = [o for r in host.iterchildren(RUN) for o in r if o.tag in OBJECTS]
    if len(objs) != 1 or objs[0].tag != TBL:
        return None
    rows = [list(tr.iterchildren(TC)) for tr in objs[0].iterchildren(TR)]
    cells = [c for r in rows for c in r]
    if not 1 <= len(rows) <= ROWS_MAX or not 1 <= len(cells) <= CELLS_MAX:
        return None
    full, total, k = [], 0, 0
    for ri, r in enumerate(rows):
        for c in r:
            paras = [p for sl in c.iterchildren(SUBLIST) for p in sl.iterchildren(P)]
            if any(doc._has_object(p) for p in paras):
                return None
            text = [p for p in paras if doc._text(p).strip()]
            total += sum(len(doc._text(p).strip()) for p in text)
            if text:
                full.append({"row": ri, "at": k, "cell": c, "paras": text})
            k += 1
    if not full or len(full) > 2 or total > TITLE_MAX:
        return None
    num = None
    if len(full) == 2:
        a, b = full
        if a["row"] != b["row"]:
            return None
        num = a if _numlike(doc, a) else b if _numlike(doc, b) else None
        if num is None:
            return None
    ttl = next(x for x in full if x is not num)
    return {"tbl": objs[0], "cell": ttl["cell"], "title": ttl["paras"][0], "num": num["paras"][0] if num else None, "rows": len(rows), "cells": [len(r) for r in rows],
            "at": ttl["at"], "numAt": num["at"] if num else None, "all": cells}


def box_of(doc, host):
    """title_of 의 (표, 제목 칸, 제목 문단) | None."""
    info = title_of(doc, host)
    return (info["tbl"], info["cell"], info["title"]) if info else None


def _cell_look(doc, cell):
    """칸의 테두리·바탕 **내용** — [바탕색(흰 바탕 = 없음), 위·아래·왼·오른 선(종류/굵기/색 | "")]. 정의 번호가 달라도 내용이 같으면 같다."""
    bf = cell.get("borderFillIDRef")
    lines = doc._border_lines(bf) or {}
    fill = doc._fill(bf)
    return ["" if not fill or fill.upper() == "#FFFFFF" else fill.upper()] + ["/".join(str(lines[k][f]) for f in ("type", "widthMm", "color")) if lines.get(k) else "" for k in "tblr"]


def _title_look(doc, title):
    f = doc._summary(title.get("paraPrIDRef"), doc._char_id(title)) or {}
    align = f.get("align")
    return f, [f.get("font"), f.get("sizePt"), bool(f.get("bold")), bool(f.get("italic")), f.get("color"), "left" if align in (None, "justify") else align]  # 한 줄 제목의 양쪽 정렬 = 왼쪽 정렬


def sig_of(doc, info):
    """제목 표의 꼴(「동일한 테이블 서식 + 헤딩 서식」) — 표의 꼴(행 · 행마다 칸 수 · 제목 칸과 번호 칸의 자리) + 칸마다 테두리·바탕의 내용 + 제목 글의 겉모습(글꼴 · 크기 · 굵게 · 기울임 · 색 · 정렬).
    정의 번호로 견주지 않는다(같아 보이는 표도 번호가 다르다 — 사용자 문서의 띠 둘: 제목 칸 테두리 정의 9 · 17, 정렬 양쪽 · 왼쪽) · 칸 폭은 안 본다. -> 「▦행×칸(n = 번호 칸):해시」."""
    body = [info["cells"], info["at"], info["numAt"], [_cell_look(doc, c) for c in info["all"]], _title_look(doc, info["title"])[1]]
    h = hashlib.sha1(json.dumps(body, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    return f"{KEY}{info['rows']}x{max(info['cells'])}{'n' if info['num'] is not None else ''}:{h}"


def legacy_sig(doc, info):
    """1칸 상자의 옛 꼴 이름(넓히기 전 — 칸의 테두리·바탕 정의 번호 + 제목 글의 겉모습) | None(1칸 상자가 아님). 옛 기록(`lifts[].sigs`)을 지금 묶음에 잇는 데만 쓴다."""
    if len(info["all"]) != 1:
        return None
    f = _title_look(doc, info["title"])[0]
    return "|".join(str(v) for v in [info["cell"].get("borderFillIDRef", ""), f.get("font"), f.get("sizePt"), f.get("bold"), f.get("italic"), f.get("color"), f.get("align")])


def _host_el(doc, el):
    """칸 안 문단 el 을 품은 표의 호스트 문단(제목 문단 → subList → tc → tr → tbl → run → p) | None."""
    cur = el
    while cur is not None and cur.tag != TBL:
        cur = cur.getparent()
    run = cur.getparent() if cur is not None else None
    host = run.getparent() if run is not None else None
    return host if host is not None and host.tag == P else None


def host_of(doc, ov, pid, el=None):
    """개요 줄 pid 가 표 줄이면 그 표를 품은 문단 요소, 아니면 el(그 문단 요소 그대로) — 그릇 문단 열에서의 줄 자리."""
    x = (ov or {}).get("lines", {}).get(pid)
    if x is None or x.get("role") != ROLE:
        return el
    p = doc._ids.get(pid)
    host = _host_el(doc, p) if p is not None else None
    return host if host is not None else el


def aliases(doc, ov, par):
    """그릇 par(구역·칸) 바로 아래 문단 가운데 표 줄의 호스트 → {호스트 문단 요소: 줄 id}."""
    out = {}
    for pid, x in (ov or {}).get("lines", {}).items():
        if x.get("role") != ROLE:
            continue
        p = doc._ids.get(pid)
        host = _host_el(doc, p) if p is not None and doc._attached(p) else None
        if host is not None and host.getparent() is par:
            out[host] = pid
    return out


def _first_level(t):
    """템플릿의 글 줄이 시작하는 레벨(표 레벨을 뺀 것) — 종속 템플릿은 base + 1, 표를 넣은 템플릿은 표 레벨 수만큼 더."""
    return int(t.get("base") or 0) + 1 + depth(t)


def _tiers(t):
    """표를 넣은 템플릿의 층 목록 `lift.tiers`(층마다 꼴 목록 — [0] = L1) — 옛 기록(층 없이 `sigs` 만)은 한 층으로."""
    lf = t["lift"]
    if "tiers" not in lf:
        lf["tiers"] = [list(lf.get("sigs") or [])]
    return lf["tiers"]


def _blocked(ov, tid):
    """표를 넣거나 뗄 수 없는 까닭 | None — 종속·서식 종속 템플릿이거나 그런 템플릿이 이 템플릿에 걸려 있으면(레벨을 밀면 그 기록이 어긋난다)."""
    t = ov["templates"][tid]
    if t.get("kind") == OE.BAND:  # 띠 표 템플릿(「별첨N」 — spec_헤딩_추출 ② §6 「띠 표 줄」)은 줄이 이미 표다 — 그 위에 표 레벨을 더 끼우지 않는다
        return f"T{t['no']} 는 별첨·부록 표 제목 템플릿입니다 — 줄이 이미 표 제목입니다(헤딩 추출이 스스로 잡은 「{(t.get('chain') or ['?'])[0]}」 표)"
    if t.get("composite") or t.get("variant"):
        return f"T{t['no']} 는 종속 템플릿입니다 — 원래 템플릿에서 하세요"
    for o in ov["templates"].values():
        c, v = o.get("composite") or {}, o.get("variant") or {}
        if tid in (c.get("parent"), c.get("child")) or v.get("of") == tid:
            return f"T{t['no']} 에 걸린 종속 템플릿 T{o['no']} 가 있습니다 — 그것부터 떼고(합치고) 하세요"
    return None


def _band(host):
    """host(문단)가 1행짜리 표를 품었나 — 제목 띠로 본다(여러 행 표는 본문 자료 표)."""
    return any(o.tag == TBL and len(o.findall(TR)) == 1 for r in host.iterchildren(RUN) for o in r)


def _flow(doc, ov, tid):
    """본문(구역 바로 아래) 문단을 구역마다 차례로 — 간격 문단은 뺀 [(종류, 문단 요소, 값)]:
    "line"(템플릿 tid 의 표 줄을 품은 문단 → 줄 id) · "text"(tid 의 글 줄 → 줄 id) · "title"(아직 줄이 아닌 제목 표 → title_of 의 뼈대) · "other"(그 밖 — 다른 템플릿의 줄 · 보통 글 · 자료 표)."""
    out = []
    for sec in doc._sections:
        al = aliases(doc, ov, sec)
        row = []
        for c in sec.iterchildren(P):
            if doc.is_spacer(c):
                continue
            pid = al.get(c)
            if pid is None:
                info = title_of(doc, c)
                if info is not None:
                    pid = doc._id(info["title"])
                    if pid not in ov["lines"]:
                        row.append(("title", c, info))
                        continue
                else:
                    pid = doc._rev.get(c)
                x = ov["lines"].get(pid) if pid else None
                row.append(("text", c, pid) if x is not None and x["tpl"] == tid else ("other", c, None))
                continue
            row.append(("line", c, pid) if ov["lines"][pid]["tpl"] == tid else ("other", c, None))
        out.append(row)
    return out


def _shape_name(info):
    return {"rows": info["rows"], "cells": len(info["all"]), "num": info["num"] is not None}


def candidates(doc, ov, tid):
    """템플릿 tid 의 줄 바로 위에 있는 제목 표를 같은 꼴끼리 →
    [{sig, was[옛 꼴 이름…], count, lifted(이미 넣은 꼴), level(들어갈 레벨), new(새 표 레벨을 끼우나), look{font, sizePt, bold}, shape{rows, cells, num},
      tables[{table, para, text, num(번호 글 | ""), numPara, under(바로 아래 줄 | None)}]}] — 표가 많은 꼴 먼저(표는 문서 순).
    닻 = 간격 문단만 사이에 두고 tid 의 표 줄이나 첫 글 레벨 줄 바로 위에 있는 제목 표. 묶음 = 닻이 있는 꼴(이미 넣은 꼴 포함)의 본문 제목 표 모두(아래에 이 템플릿의 줄이 없어도 — under None).
    제목 문단이 이미 다른 개요 줄이면(레터가 있는 제목 상자 — 2단계가 줄로 잡았다) 뺀다."""
    tid = str(tid)
    t = ov["templates"].get(tid)
    if t is None:
        raise KeyError(f"템플릿 {tid} 가 없습니다")
    floor, first = int(t.get("base") or 0), _first_level(t)
    lf = t.get("lift") or {}
    tiers = (lf["tiers"] if "tiers" in lf else [lf.get("sigs") or []]) if lf else []  # 읽기만 — 옛 기록(층 목록 없음)을 여기서 고쳐 적지 않는다(`_tiers` 는 넣을 때)
    tier_of = {s: floor + k + 1 for k, sigs in enumerate(tiers) for s in sigs}
    found = {}
    for row in _flow(doc, ov, tid):
        for i, (kind, _, info) in enumerate(row):
            if kind != "title":
                continue
            g = found.setdefault(sig_of(doc, info), {"info": info, "tables": [], "hi": [], "lo": [], "was": set()})
            old = legacy_sig(doc, info)
            if old:
                g["was"].add(old)
            under, nxt = None, row[i + 1] if i + 1 < len(row) else None
            if nxt is not None and nxt[0] in ("line", "text") and int(ov["lines"][nxt[2]]["level"]) <= first:
                under, prev = nxt[2], row[i - 1] if i else None
                g["hi"].append(int(ov["lines"][under]["level"]) - 1)
                g["lo"].append(int(ov["lines"][prev[2]]["level"]) if prev is not None and prev[0] == "line" else floor)
            g["tables"].append({"table": doc._id(info["tbl"]), "para": doc._id(info["title"]), "text": doc._text(info["title"]).strip()[:80],
                                "num": doc._text(info["num"]).strip() if info["num"] is not None else "", "numPara": doc._id(info["num"]) if info["num"] is not None else None, "under": under})
    out = []
    for sig, g in found.items():
        lv = tier_of.get(sig) or next((tier_of[s] for s in sorted(g["was"]) if s in tier_of), None)
        lifted, new = lv is not None, False
        if lv is None:
            if not g["hi"]:  # 닻이 없는 꼴
                continue
            hi, lo = min(g["hi"]), max(g["lo"])
            lv, new = (hi, False) if lo < hi else (hi + 1, True)
        fmt = _title_look(doc, g["info"]["title"])[0]
        out.append({"sig": sig, "was": sorted(g["was"]), "count": len(g["tables"]), "lifted": lifted, "level": lv, "new": new,
                    "look": {k: fmt.get(k) for k in ("font", "sizePt", "bold")}, "shape": _shape_name(g["info"]), "tables": g["tables"]})
    out.sort(key=lambda g: -g["count"])
    return out


def _table_slot():
    """표 제목 레벨의 슬롯 — 레터·접두·서식이 없다(자리 규칙 · 서식 갈래 · 서식 정리의 대상이 아니다)."""
    return {"letter": "", "key": KEY, "rep": None, "count": 0, "prefix": None, "attrs": None, "spacer": None, "table": True}


def _shift(ov, tid, at):
    """템플릿 tid 의 레벨 at 부터를 한 칸씩 민다(새 표 레벨을 at 에 끼울 자리) — 줄(표 줄도) · 슬롯 · 가지 열쇠 · 더한 레벨 기록(§8-6). 사슬·max 는 부른 쪽이."""
    t = ov["templates"][tid]
    for x in ov["lines"].values():
        if x["tpl"] == tid and int(x["level"]) >= at:
            x["level"] = int(x["level"]) + 1
    t["slots"] = {str(int(k) + (1 if int(k) >= at else 0)): sl for k, sl in t["slots"].items()}
    br = ov.get("branches") or {}
    for key in sorted((k for k in br if k.split("|")[0] == tid and int(k.split("|")[1]) >= at), key=lambda k: -int(k.split("|")[1])):  # 겹쳐 쓰지 않게 깊은 레벨부터
        br[f"{tid}|{int(key.split('|')[1]) + 1}"] = br.pop(key)
    for r in ov.get("grows") or []:
        if r.get("tid") == tid and int(r["level"]) >= at:
            r["level"] = int(r["level"]) + 1


def _unshift(ov, tid, d):
    """템플릿 tid 의 표 레벨 d 층을 걷어 낸 자리로 글 레벨을 당긴다(표 줄은 부른 쪽이 먼저 뺀다) — 줄 · 슬롯(표 슬롯은 버림) · 가지 열쇠 · 더한 레벨 기록."""
    t = ov["templates"][tid]
    for x in ov["lines"].values():
        if x["tpl"] == tid:
            x["level"] = int(x["level"]) - d
    t["slots"] = {str(int(k) - d): sl for k, sl in t["slots"].items() if not sl.get("table")}
    br = ov.get("branches") or {}
    for key in sorted((k for k in br if k.split("|")[0] == tid and int(k.split("|")[1]) > d), key=lambda k: int(k.split("|")[1])):  # 얕은 레벨부터
        br[f"{tid}|{int(key.split('|')[1]) - d}"] = br.pop(key)
    for r in ov.get("grows") or []:
        if r.get("tid") == tid:
            r["level"] = int(r["level"]) - d


def _orig(ov, t, pid):
    """줄 pid 가 표를 넣기 전에 매달리던 부모 — 표 줄이면 `base` · 글 줄이면 `adopt` 의 옛 부모(없으면 지금 부모 — 그것이 표 줄이면 그 표 줄의 `base`)."""
    x = ov["lines"][pid]
    if x.get("role") == ROLE:
        return x.get("base", x.get("parent"))
    adopt = (t.get("lift") or {}).get("adopt") or {}
    if pid in adopt:
        return adopt[pid]
    p = ov["lines"].get(x.get("parent"))
    if p is not None and p.get("role") == ROLE and p["tpl"] == x["tpl"]:
        return p.get("base", p.get("parent"))
    return x.get("parent")


def _table_lines(doc, ov, tid):
    """템플릿 tid 의 표 줄 id — 문서 순."""
    return [v for row in _flow(doc, ov, tid) for kind, _, v in row if kind == "line"]


def _bases(doc, ov, tid, fresh):
    """새 표 줄 fresh{줄 id: 바로 아래 줄 | None}의 `base`(그 표가 들어선 자리의 옛 부모) — 닻이 있으면 아래 줄의 옛 부모, 없으면 가장 가까운 앞(없으면 뒤) 표 줄의 것."""
    lines, t = ov["lines"], ov["templates"][tid]
    for pid, under in fresh.items():
        if under is not None:
            lines[pid]["base"] = _orig(ov, t, under)
    order = _table_lines(doc, ov, tid)
    for i, pid in enumerate(order):
        if pid in fresh and fresh[pid] is None:
            near = next((q for q in reversed(order[:i]) if "base" in lines[q]), None) or next((q for q in order[i + 1:] if "base" in lines[q]), None)
            lines[pid]["base"] = lines[near]["base"] if near is not None else None


def _relink(doc, ov, tid):
    """표 줄과 첫 글 레벨 줄의 부모를 본문 차례로 다시 맨다 — 표 줄의 부모 = 앞의 더 얕은 표 줄(그 줄과 `base` 가 같을 때) 아니면 `base` ·
    첫 글 레벨 줄의 부모 = 가장 가까운 앞 표 줄(옛 부모가 그 표 줄의 `base` 와 같을 때 — 그 표가 그 줄들의 자리에 들어선 것). 안 넣은 제목 표나 다른 1행 표를 만나면 구간이 끝난다
    (다른 제목 띠 — 여러 행 자료 표는 끊지 않는다). 옛 부모는 `lift.adopt` 에(처음 것만). -> {줄 id: 바뀌기 전 부모}(이번에 부모가 바뀐 글 줄)."""
    t = ov["templates"][tid]
    lines, adopt, first = ov["lines"], t["lift"].setdefault("adopt", {}), _first_level(t)
    changed = {}
    for row in _flow(doc, ov, tid):
        cur = {}
        for kind, c, v in row:
            if kind == "line":
                x, k = lines[v], int(lines[v]["level"])
                up = next((cur[j] for j in range(k - 1, 0, -1) if j in cur), None)
                x["parent"] = up if up is not None and lines[up].get("base") == x.get("base") else x.get("base")
                cur = {j: p for j, p in cur.items() if j < k}
                cur[k] = v
                continue
            if kind == "title" or (kind == "other" and _band(c)):
                cur = {}
                continue
            if kind != "text" or not cur or int(lines[v]["level"]) != first:
                continue
            x, top = lines[v], cur[max(cur)]
            if x.get("parent") == top:
                continue
            old = _orig(ov, t, v)
            if old == lines[top].get("base"):
                adopt.setdefault(v, old)
                changed[v] = x.get("parent")
                x["parent"] = top
    return changed


def lift(doc, ov, tid, sig=None):
    """템플릿 tid 의 줄 위 제목 표(꼴 sig — 없으면 표가 가장 많은 꼴 · 옛 꼴 이름도 받는다)를 표 레벨로 넣는다 →
    기록 {tid, no, sig, tables[표 id…], paras[줄 id…], adopted(부모가 바뀐 글 줄 수), levels[첫 글 레벨, max], level(들어간 레벨), new(새 표 레벨을 끼웠나), depth(표 레벨 수), more(더 넣을 수 있는 묶음 수)}.
    새 표 레벨을 끼울 때 그 레벨부터 한 칸 민다(처음이면 □ L1 → L2). 오버레이만 바꾼다 — 검사는 바꾸기 전에 다 한다(ValueError · KeyError)."""
    tid = str(tid)
    t = ov["templates"].get(tid)
    if t is None:
        raise KeyError(f"템플릿 {tid} 가 없습니다")
    why = _blocked(ov, tid)
    if why:
        raise ValueError(why)
    groups = candidates(doc, ov, tid)
    g = next((x for x in groups if sig == x["sig"] or sig in x["was"]), None) if sig else (groups[0] if groups else None)
    if g is None:
        raise ValueError(f"T{t['no']} 의 줄 바로 위에 넣을 제목 표가 없습니다" + (" — 그 꼴의 표가 지금 문서에 없습니다(다시 읽어 주세요)" if sig else ""))
    # ---- 여기부터 오버레이를 바꾼다
    lv = g["level"]
    if not t.get("lift"):
        ov["seq"] = int(ov.get("seq") or 0) + 1
        t["lift"] = {"sigs": [], "tiers": [], "adopt": {}, "n": ov["seq"]}
        ov.setdefault("lifts", []).append({"anchor": t.get("anchor"), "tid": tid, "sigs": [], "tiers": [], "n": ov["seq"]})
    lf, tiers = t["lift"], _tiers(t)
    for x in ov["lines"].values():  # 옛 기록의 표 줄 — `base` 가 없으면 지금 부모(한 층일 때는 표 줄이 아닌 옛 부모)
        if x["tpl"] == tid and x.get("role") == ROLE:
            x.setdefault("base", x.get("parent"))
    if g["new"]:
        at = lv - int(t.get("base") or 0)  # 층 차례(1 = 가장 바깥)
        _shift(ov, tid, lv)
        chain = list(t.get("chain") or [])
        t["chain"] = chain[:lv - 1] + [KEY] + chain[lv - 1:]
        t["max"] = int(t.get("max") or 0) + 1
        t["slots"][str(lv)] = _table_slot()
        tiers.insert(at - 1, [])
    k = lv - int(t.get("base") or 0) - 1
    for i in range(len(tiers)):  # 옛 꼴 이름(1칸 상자 — legacy_sig)은 새 이름으로 바꿔 적는다
        tiers[i] = [s for s in tiers[i] if s not in g["was"]]
    if g["sig"] not in tiers[k]:
        tiers[k].append(g["sig"])
    lf["sigs"] = [s for sigs in tiers for s in sigs]
    for r in ov.get("lifts") or []:  # 기록의 꼴 목록도(작업 저장을 거치면 템플릿의 목록과 다른 객체다)
        if r.get("tid") == tid:
            r["sigs"], r["tiers"] = list(lf["sigs"]), [list(s) for s in tiers]
    paras, fresh = [], {}
    for r in g["tables"]:
        u = ov["lines"].get(r["under"]) or {}
        ov["lines"][r["para"]] = {"tpl": tid, "no": t["no"], "level": lv, "parent": None, "letter": "", "key": KEY, "role": ROLE, "flow": u.get("flow", "body"), "table": r["table"],
                                 **({"num": r["numPara"]} if r["numPara"] else {})}
        paras.append(r["para"])
        fresh[r["para"]] = r["under"]
    _bases(doc, ov, tid, fresh)
    got = _relink(doc, ov, tid)
    order = _table_lines(doc, ov, tid)
    for sl_lv, sl in t["slots"].items():
        if sl.get("table"):
            ids = [p for p in order if int(ov["lines"][p]["level"]) == int(sl_lv)]
            sl["count"] = len(ids)
            if sl.get("rep") not in ids:
                sl["rep"] = ids[0] if ids else None
    return {"tid": tid, "no": t["no"], "sig": g["sig"], "tables": [r["table"] for r in g["tables"]], "paras": paras, "adopted": len(got), "levels": [_first_level(t), t["max"]],
            "level": lv, "new": bool(g["new"]), "depth": len(tiers), "more": len(candidates(doc, ov, tid))}


def unlift(ov, tid, force=False):
    """lift 를 거꾸로 — 표 줄을 **모두**(모든 층) 빼고(그 아래 줄의 부모는 넣기 전 것 · 넣은 뒤 만든 줄은 그 표 줄의 `base`) 레벨을 되돌린다. -> 뺀 표 줄 수.
    force = 종속 템플릿이 걸려 있어도(2단계 다시 실행 뒤 못 건 템플릿의 옛 오버레이 사본을 맞출 때)."""
    tid = str(tid)
    t = ov["templates"].get(tid)
    if t is None:
        raise KeyError(f"템플릿 {tid} 가 없습니다")
    if not t.get("lift"):
        raise ValueError(f"T{t['no']} 에는 표 레벨로 넣은 표가 없습니다")
    why = None if force else _blocked(ov, tid)
    if why:
        raise ValueError(why)
    d = depth(t)
    adopt = t["lift"].get("adopt") or {}
    gone = {p: x for p, x in ov["lines"].items() if x["tpl"] == tid and x.get("role") == ROLE}
    for p in gone:
        ov["lines"].pop(p)
    for pid, x in ov["lines"].items():
        if x.get("parent") in gone:
            was = gone[x["parent"]]
            x["parent"] = adopt[pid] if pid in adopt else was.get("base", was.get("parent"))
    _unshift(ov, tid, d)
    t["chain"] = list(t.get("chain") or [])[d:]
    t["max"] = int(t.get("max") or d) - d
    t.pop("lift", None)
    ov["lifts"] = [r for r in ov.get("lifts") or [] if r.get("tid") != tid]
    return len(gone)


def _align_old(out, tid, d):
    """옛 오버레이 사본 out 의 템플릿 tid 를 「표 레벨 d 층」 꼴로 맞춘다(뒤의 carry 들이 앵커 + 레벨로 읽는다) — 표 줄을 걷고 글 레벨을 d 칸 민 것."""
    try:
        unlift(out, tid, force=True)
    except (KeyError, ValueError):
        return
    t = out["templates"][tid]
    at = int(t.get("base") or 0) + 1
    for _ in range(d):
        _shift(out, tid, at)
        t["slots"][str(at)] = _table_slot()
        t["chain"] = [KEY] + list(t.get("chain") or [])
        t["max"] = int(t.get("max") or 0) + 1


def carry(old, new, doc):
    """2단계를 다시 돌려 오버레이를 새로 만들 때 — 옛 오버레이에서 표를 넣은 템플릿(같은 앵커)에 기록한 층을 **안쪽(글 레벨 쪽)부터** 같은 꼴로 다시 건다(새로 생긴 같은 꼴 표도 든다 ·
    들어갈 레벨은 그때의 자리로 다시 정한다). **다른 carry 들보다 먼저** 부른다(자리 규칙·종속·더한 레벨은 앵커 + 레벨로 옮기므로 레벨이 먼저 맞아야 한다).
    -> 뒤의 carry 들이 읽을 옛 오버레이 — 다시 건 층 수가 옛것과 다른 템플릿이 있으면(못 걸었거나 일부만) 그 템플릿의 레벨을 새것에 맞춘 사본, 아니면 old 그대로."""
    if not old or not new or not old.get("lifts"):
        return old
    out = old
    for rec in sorted(old["lifts"], key=lambda r: r.get("n") or 0):
        by_anchor = {t.get("anchor"): tid for tid, t in new.get("templates", {}).items()}
        tid = by_anchor.get(rec.get("anchor"))
        for sigs in reversed(rec.get("tiers") or [rec.get("sigs") or []]) if tid is not None else []:
            for sig in sigs:
                try:
                    lift(doc, new, tid, sig)
                except (KeyError, ValueError):
                    continue
        got = depth(new["templates"][tid]) if tid is not None else 0
        was = (out.get("templates") or {}).get(rec.get("tid"))
        if was is not None and was.get("lift") and depth(was) != got:
            if out is old:
                out = copy.deepcopy(old)
            _align_old(out, rec["tid"], got)
    return out


def view_extra(ov):
    """오버레이 요약에 더할 것 — {템플릿 id: {lift: {tables(표 줄 수), sigs, depth(표 레벨 수)}}}(표를 넣은 템플릿만)."""
    out = {}
    for tid, t in (ov.get("templates") or {}).items():
        if t.get("lift"):
            n = sum(1 for x in ov["lines"].values() if x["tpl"] == tid and x.get("role") == ROLE)
            out[tid] = {"lift": {"tables": n, "sigs": list(t["lift"].get("sigs") or []), "depth": depth(t)}}
    return out
