"""표 제목을 템플릿의 L1 으로(spec_hwpx_웹편집 ② §8-7) — 본문 템플릿의 첫 레벨 줄 **바로 위**에 있는 1칸 제목 표(제목 상자)를 그 템플릿의 L1 로 넣는다.

2026-11-16 사용자 "그리고 이 테이블도 템플릿의 L1 으로 할 수 있도록 해줘. 이런 문서들이 꽥 많거든" → 답 「같은 꼴 표를 한 번에」 · 「표시·구조 + Enter 먼저」.
(제목이 표 안에 있는 문서 — 「사업과제 1(전략): …」 상자 아래 「□ › o › -」: 헤딩 추출은 1칸 상자를 투명하게 보고 레터 없는 글은 헤딩 후보가 아니라 그 표가 템플릿에 못 들었다.)

- **오버레이만** 바꾼다(문서·그래프는 그대로 — 템플릿 종속 §8-2 와 같은 자리): 템플릿의 레벨을 한 칸씩 밀고(□ L1 → L2 …) L1 에 **표 줄**을 둔다. 템플릿 번호는 그대로(「T1」).
- 표 줄 = **칸 안 제목 문단**(글이 있는 첫 문단)의 id 를 열쇠로 한 줄 `{tpl, level: 1, letter: "", key: "▦", role: "table", table: 표 id}` — 레터가 없으므로 `outline_edit.sync` 는 표 줄을
  「문단이 살아 있나」 로만 본다(제목 글을 고쳐도 줄이 남는다). 본문 문단 열에서의 자리는 그 표를 품은 문단(호스트)이다(`host_of` · `aliases` — server `_outline_seq` 가 그 자리에 줄을 놓는다).
- 후보(`candidates`) = 그 템플릿 첫 레벨 줄의 바로 앞 문단(사이는 순수 간격 문단만)이 **1칸 표 하나만 품은 문단**이고 칸에 글이 있는 것 — 같은 꼴(칸 테두리·바탕 + 제목 문단의 문단·글자 모양)끼리 묶는다.
  「같은 꼴 표를 한 번에」: 묶음 하나를 통째로 넣는다(`lift`). 다른 꼴의 묶음도 이어서 넣을 수 있다.
- 넣으면(`lift`): 그 표 아래의 첫 레벨 줄들(같은 부모 아래 형제 — 다음 표 줄 전까지)의 부모가 그 표 줄이 된다(`adopt` 에 옛 부모 — 떼면 되돌림). 표 줄의 부모 = 그 줄들의 옛 부모.
- 떼기(`unlift`) = 표 줄을 빼고 레벨을 되돌린다. 2단계를 다시 돌리면(`carry`) 같은 앵커의 템플릿에 같은 꼴로 다시 건다 — 새로 생긴 같은 꼴 표도 든다.
- 표 줄의 키: Enter = 표 **아래**에 L2 새 줄(`outline_edit.plan_enter` 의 표 가지) — 그 밖(Alt+Enter · 레벨 · 끌기 · 지우기)은 거절. 그 아래 L2 줄은 표 레벨로 못 올린다.
"""
import copy

from app import outline_edit as OE
from app.hwpx_doc import P, RUN, SUBLIST, TBL, TC, TR
from app.hwpx_struct import OBJECTS

KEY = "▦"       # 표 제목 레벨의 정규 키(레터 없음)
ROLE = "table"  # 표 줄의 role
TITLE_MAX = 200  # 제목 글이 이보다 길면 제목 표로 보지 않는다(본문을 담은 상자)


def box_of(doc, host):
    """host(문단)가 **1칸 표 하나만** 품은 글 없는 문단이고 그 칸에 글이 있으면 (표, 칸, 제목 문단 = 글이 있는 첫 문단) — 아니면 None.
    글이 있는 문단 · 개체가 둘 이상 · 여러 칸 표 · 그림 · 칸 안에 또 개체가 있거나 글이 긴 상자는 제목 표가 아니다."""
    if host is None or host.tag != P or doc._text(host).strip():
        return None
    objs = [o for r in host.iterchildren(RUN) for o in r if o.tag in OBJECTS]
    if len(objs) != 1 or objs[0].tag != TBL:
        return None
    cells = [c for tr in objs[0].iterchildren(TR) for c in tr.iterchildren(TC)]
    if len(cells) != 1:
        return None
    paras = [p for sl in cells[0].iterchildren(SUBLIST) for p in sl.iterchildren(P)]
    if any(doc._has_object(p) for p in paras):
        return None
    title = next((p for p in paras if doc._text(p).strip()), None)
    if title is None or sum(len(doc._text(p).strip()) for p in paras) > TITLE_MAX:
        return None
    return objs[0], cells[0], title


def sig_of(doc, cell, title):
    """제목 표의 꼴 — 칸의 테두리·바탕(정의 번호) + 제목 글의 겉모습(글꼴 · 크기 · 굵게 · 기울임 · 색 · 정렬). 문단·글자 모양의 정의 번호로 견주지 않는다
    (같아 보이는 표도 여백 같은 값이 조금 달라 번호가 다르다 — 사용자 문서의 사업과제 1 과 2~4)."""
    f = doc._summary(title.get("paraPrIDRef"), doc._char_id(title)) or {}
    return "|".join(str(v) for v in [cell.get("borderFillIDRef", ""), f.get("font"), f.get("sizePt"), f.get("bold"), f.get("italic"), f.get("color"), f.get("align")])


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
    """템플릿의 줄이 시작하는 레벨(표 레벨을 뺀 것) — 종속 템플릿은 base + 1, 표를 넣은 템플릿은 2."""
    return int(t.get("base") or 0) + 1 + (1 if t.get("lift") else 0)


def _blocked(ov, tid):
    """표를 넣거나 뗄 수 없는 까닭 | None — 종속·서식 종속 템플릿이거나 그런 템플릿이 이 템플릿에 걸려 있으면(레벨을 밀면 그 기록이 어긋난다)."""
    t = ov["templates"][tid]
    if t.get("composite") or t.get("variant"):
        return f"T{t['no']} 는 종속 템플릿입니다 — 원래 템플릿에서 하세요"
    for o in ov["templates"].values():
        c, v = o.get("composite") or {}, o.get("variant") or {}
        if tid in (c.get("parent"), c.get("child")) or v.get("of") == tid:
            return f"T{t['no']} 에 걸린 종속 템플릿 T{o['no']} 가 있습니다 — 그것부터 떼고(합치고) 하세요"
    return None


def candidates(doc, ov, tid):
    """템플릿 tid 의 첫 레벨 줄 바로 위에 있는 1칸 제목 표를 같은 꼴끼리 →
    [{sig, count, lifted(이미 L1 로 넣은 꼴), look{font, sizePt, bold}, tables[{table, para, text, under}]}] — 표가 많은 꼴 먼저(표는 문서 순).
    본문(구역 바로 아래) 줄만 본다 · 제목 문단이 이미 다른 개요 줄이면(레터가 있는 제목 상자 — 2단계가 줄로 잡았다) 뺀다."""
    tid = str(tid)
    t = ov["templates"].get(tid)
    if t is None:
        raise KeyError(f"템플릿 {tid} 가 없습니다")
    first = _first_level(t)
    secs = set(doc._sections)
    done = {x.get("table") for x in ov["lines"].values() if x.get("role") == ROLE and x["tpl"] == tid}
    groups, seen = {}, set()
    for pid, x in ov["lines"].items():
        if x["tpl"] != tid or int(x["level"]) != first or x.get("role") == ROLE:
            continue
        el = doc._ids.get(pid)
        if el is None or el.getparent() not in secs:
            continue
        prev = el.getprevious()
        while prev is not None and (not isinstance(prev.tag, str) or (prev.tag == P and doc.is_spacer(prev))):
            prev = prev.getprevious()
        box = box_of(doc, prev)
        if box is None:
            continue
        tbl, cell, title = box
        table, para = doc._id(tbl), doc._id(title)
        if table in seen:
            continue
        seen.add(table)
        if table in done:  # 이미 넣은 표 — 그 꼴이 넣은 꼴임을 알리기만
            groups.setdefault(sig_of(doc, cell, title), {"tables": [], "lifted": True, "title": title})["lifted"] = True
            continue
        if para in ov["lines"]:
            continue
        g = groups.setdefault(sig_of(doc, cell, title), {"tables": [], "lifted": False, "title": title})
        g["tables"].append({"table": table, "para": para, "text": doc._text(title).strip()[:80], "under": pid, "_el": title})
    order = _order(doc)
    out = []
    for sig, g in groups.items():
        if not g["tables"]:
            continue
        g["tables"].sort(key=lambda r: order.get(r.pop("_el"), 1 << 30))
        title = g["title"]
        fmt = doc._summary(title.get("paraPrIDRef"), doc._char_id(title)) or {}
        out.append({"sig": sig, "count": len(g["tables"]), "lifted": bool(g["lifted"]) or sig in ((t.get("lift") or {}).get("sigs") or []),
                    "look": {k: fmt.get(k) for k in ("font", "sizePt", "bold")}, "tables": g["tables"]})
    out.sort(key=lambda g: -g["count"])
    return out


def _order(doc):
    """구역 바로 아래 문단 + 그 안의 표 칸 문단 → 문서 차례."""
    out = {}
    for sec in doc._sections:
        for p in sec.iter(P):
            out.setdefault(p, len(out))
    return out


def _band(host):
    """host(문단)가 1행짜리 표를 품었나 — 제목 띠로 본다(여러 행 표는 본문 자료 표)."""
    return any(o.tag == TBL and len(o.findall(TR)) == 1 for r in host.iterchildren(RUN) for o in r)


def _shift(ov, tid, by):
    """템플릿 tid 의 레벨을 by(+1 넣기 · −1 떼기)만큼 민다 — 줄 · 슬롯 · 가지 열쇠 · 더한 레벨 기록. 사슬·max 는 부른 쪽이."""
    t = ov["templates"][tid]
    for x in ov["lines"].values():
        if x["tpl"] == tid and x.get("role") != ROLE:
            x["level"] = int(x["level"]) + by
    t["slots"] = {str(int(k) + by): sl for k, sl in t["slots"].items() if not sl.get("table")}
    br = ov.get("branches") or {}
    for key in sorted((k for k in br if k.split("|")[0] == tid), key=lambda k: -by * int(k.split("|")[1])):  # 겹쳐 쓰지 않게 — 넣기는 깊은 레벨부터
        br[f"{tid}|{int(key.split('|')[1]) + by}"] = br.pop(key)
    for r in ov.get("grows") or []:
        if r.get("tid") == tid:
            r["level"] = int(r["level"]) + by


def _adopt(doc, ov, tid):
    """표 줄 아래의 첫 레벨 줄을 그 표 줄 아래로 — 본문 문단 열에서 가장 가까운 앞 표 줄을 찾아, 줄의 부모가 그 표 줄의 부모와 같으면(그 표가 그 줄들의 자리에 들어선 것) 부모를 표 줄로.
    -> {줄 id: 옛 부모}(이번에 바뀐 것만)."""
    t = ov["templates"][tid]
    first = _first_level(t)
    changed = {}
    for sec in doc._sections:
        al = aliases(doc, ov, sec)
        if not any(ov["lines"][p]["tpl"] == tid for p in al.values()):
            continue
        cur = None
        for c in sec.iterchildren(P):
            if c in al and ov["lines"][al[c]]["tpl"] == tid:
                cur = al[c]
                continue
            if cur is not None and _band(c):  # 다른 제목 띠(1행 표 — 「2 . | 부서사업과제 추진내용」 · 다른 꼴 상자)를 만나면 그 표 줄의 구간은 끝
                cur = None
                continue
            pid = doc._rev.get(c)
            x = ov["lines"].get(pid) if pid else None
            if x is None or cur is None or x["tpl"] != tid or int(x["level"]) != first:
                continue
            if x.get("parent") == ov["lines"][cur].get("parent") and x.get("parent") != cur:
                changed[pid] = x.get("parent")
                x["parent"] = cur
    return changed


def lift(doc, ov, tid, sig=None):
    """템플릿 tid 의 첫 레벨 줄 위 제목 표(꼴 sig — 없으면 표가 가장 많은 꼴)를 L1 로 넣는다 → 기록 {tid, no, sig, tables[표 id…], paras[줄 id…], adopted(부모가 바뀐 줄 수), levels[2, max]}.
    처음 넣을 때 템플릿의 레벨을 한 칸 민다(□ L1 → L2). 오버레이만 바꾼다 — 검사는 바꾸기 전에 다 한다(ValueError · KeyError)."""
    tid = str(tid)
    t = ov["templates"].get(tid)
    if t is None:
        raise KeyError(f"템플릿 {tid} 가 없습니다")
    why = _blocked(ov, tid)
    if why:
        raise ValueError(why)
    groups = [g for g in candidates(doc, ov, tid) if g["tables"]]
    g = next((x for x in groups if x["sig"] == sig), None) if sig else (groups[0] if groups else None)
    if g is None:
        raise ValueError(f"T{t['no']} 의 첫 레벨 줄 바로 위에 넣을 1칸 제목 표가 없습니다" + (" — 그 꼴의 표가 지금 문서에 없습니다(다시 읽어 주세요)" if sig else ""))
    # ---- 여기부터 오버레이를 바꾼다
    if not t.get("lift"):
        _shift(ov, tid, +1)
        t["chain"] = [KEY] + list(t.get("chain") or [])
        t["max"] = int(t.get("max") or 0) + 1
        t["slots"]["1"] = {"letter": "", "key": KEY, "rep": None, "count": 0, "prefix": None, "attrs": None, "spacer": None, "table": True}
        ov["seq"] = int(ov.get("seq") or 0) + 1
        t["lift"] = {"sigs": [], "adopt": {}, "n": ov["seq"]}
        ov.setdefault("lifts", []).append({"anchor": t.get("anchor"), "tid": tid, "sigs": t["lift"]["sigs"], "n": ov["seq"]})
    if g["sig"] not in t["lift"]["sigs"]:
        t["lift"]["sigs"].append(g["sig"])
    for r in ov.get("lifts") or []:  # 기록의 꼴 목록도(작업 저장을 거치면 템플릿의 목록과 다른 객체다)
        if r.get("tid") == tid:
            r["sigs"] = list(t["lift"]["sigs"])
    paras = []
    for r in g["tables"]:
        u = ov["lines"][r["under"]]
        ov["lines"][r["para"]] = {"tpl": tid, "no": t["no"], "level": 1, "parent": u.get("parent"), "letter": "", "key": KEY, "role": ROLE, "flow": u.get("flow", "body"),
                                 "table": r["table"]}
        paras.append(r["para"])
    sl = t["slots"]["1"]
    sl["rep"] = sl.get("rep") or paras[0]
    sl["count"] = sum(1 for x in ov["lines"].values() if x["tpl"] == tid and x.get("role") == ROLE)
    got = _adopt(doc, ov, tid)
    t["lift"]["adopt"].update({p: v for p, v in got.items() if p not in t["lift"]["adopt"]})
    return {"tid": tid, "no": t["no"], "sig": g["sig"], "tables": [r["table"] for r in g["tables"]], "paras": paras, "adopted": len(got), "levels": [2, t["max"]]}


def unlift(ov, tid, force=False):
    """lift 를 거꾸로 — 표 줄을 모두 빼고(그 아래 줄의 부모는 넣기 전 것 · 넣은 뒤 만든 줄은 표 줄의 부모) 레벨을 되돌린다. -> 뺀 표 줄 수.
    force = 종속 템플릿이 걸려 있어도(2단계 다시 실행 뒤 못 건 템플릿의 옛 오버레이 사본을 맞출 때)."""
    tid = str(tid)
    t = ov["templates"].get(tid)
    if t is None:
        raise KeyError(f"템플릿 {tid} 가 없습니다")
    if not t.get("lift"):
        raise ValueError(f"T{t['no']} 에는 L1 로 넣은 표가 없습니다")
    why = None if force else _blocked(ov, tid)
    if why:
        raise ValueError(why)
    adopt = t["lift"].get("adopt") or {}
    gone = {p: x for p, x in ov["lines"].items() if x["tpl"] == tid and x.get("role") == ROLE}
    for p in gone:
        ov["lines"].pop(p)
    for pid, x in ov["lines"].items():
        if x.get("parent") in gone:
            x["parent"] = adopt[pid] if pid in adopt else gone[x["parent"]].get("parent")
    _shift(ov, tid, -1)
    t["chain"] = list(t.get("chain") or [])[1:]
    t["max"] = int(t.get("max") or 1) - 1
    t.pop("lift", None)
    ov["lifts"] = [r for r in ov.get("lifts") or [] if r.get("tid") != tid]
    return len(gone)


def carry(old, new, doc):
    """2단계를 다시 돌려 오버레이를 새로 만들 때 — 옛 오버레이에서 표를 L1 로 넣은 템플릿(같은 앵커)에 같은 꼴로 다시 건다(새로 생긴 같은 꼴 표도 든다).
    **다른 carry 들보다 먼저** 부른다(자리 규칙·종속·더한 레벨은 앵커 + 레벨로 옮기므로 레벨이 먼저 맞아야 한다).
    -> 뒤의 carry 들이 읽을 옛 오버레이 — 다시 걸지 못한 템플릿이 있으면 그 템플릿의 레벨을 되돌린 사본, 아니면 old 그대로."""
    if not old or not new or not old.get("lifts"):
        return old
    out = old
    for rec in sorted(old["lifts"], key=lambda r: r.get("n") or 0):
        by_anchor = {t.get("anchor"): tid for tid, t in new.get("templates", {}).items()}
        tid, ok = by_anchor.get(rec.get("anchor")), False
        for sig in (rec.get("sigs") or []) if tid is not None else []:
            try:
                lift(doc, new, tid, sig)
                ok = True
            except (KeyError, ValueError):
                continue
        if not ok and rec.get("tid") in (out.get("templates") or {}):
            if out is old:
                out = copy.deepcopy(old)
            try:
                unlift(out, rec["tid"], force=True)
            except (KeyError, ValueError):
                pass
    return out


def view_extra(ov):
    """오버레이 요약에 더할 것 — {템플릿 id: {lift: {tables(표 줄 수), sigs}}}(표를 넣은 템플릿만)."""
    out = {}
    for tid, t in (ov.get("templates") or {}).items():
        if t.get("lift"):
            n = sum(1 for x in ov["lines"].values() if x["tpl"] == tid and x.get("role") == ROLE)
            out[tid] = {"lift": {"tables": n, "sigs": list(t["lift"].get("sigs") or [])}}
    return out
