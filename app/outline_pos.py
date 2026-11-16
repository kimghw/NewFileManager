"""개요 줄 자리(spec_hwpx_웹편집 ② §8-1) — 레터 위치 · 글 시작 · 둘째 줄.

- 자리(mm — 문단 상자 왼끝 = 본문·칸 안쪽 왼끝에서): 첫 줄 시작 x0 = 왼쪽 여백 + max(첫 줄, 0) · **레터 위치** = x0 + 앞 공백 폭 · **글 시작** = x0 + 접두(앞 공백·레터·뒤 공백) 폭 ·
  **둘째 줄** = 왼쪽 여백 + max(−첫 줄, 0)(한글 내어쓰기 = 첫 줄은 왼쪽 여백에 두고 나머지 줄을 더 들인다 — references/HWPX_포맷.md).
- 글자 폭(한글 2020 PDF 실측 — references/한글_문단모양_줄나눔.md 「글자 폭」): 글자 나아감 = 글꼴 글자 폭 × 장평 × (1 + 자간) × 글자 크기, 빈칸은 「글꼴에 어울리는 빈칸」 을 끈
  글자 모양이면 글꼴과 무관하게 0.5em, 글꼴에 없는 글자는 함초롬바탕(한글의 대체 글꼴)의 폭. 글꼴 파일은 웹 글꼴 계획(app/fonts.py)과 같은 차례로 찾는다. 탭·줄 바꿈이 든 접두는 못 잰다(None).
- 슬롯 규칙 `pos` = {"line2": "text"(글 시작에 맞춤 — 기본) | "mm"(직접 — "mm": 값) | "keep"(문단 서식 그대로), "letterMm": 레터 위치(없으면 그대로), "set": 사용자가 정함}.
  사용자가 정하지 않은 기본 규칙은 **둘째 줄을 따로 정하지 않은 문단(첫 줄 값 0)** 에만 걸린다(사용자 "딱히 언급되지 않으면" — 문서가 이미 준 들여쓰기·내어쓰기는 안 건드림).
  저절로 맞춘 문단은 오버레이 줄에 `first`(그때 넣은 첫 줄 값)를 적어 두어, 접두가 바뀌면(번호 다시 매김·레터 뒤 공백) 다시 맞춘다.
"""
import logging
import threading
import unicodedata
from collections import Counter

from app import fonts
from app import outline_edit as OE
from app.hwpx_format import _h

log = logging.getLogger("uvicorn.error")

PT_MM = 25.4 / 72
EPS = 0.02          # mm — 같은 자리로 보는 차(서식 요약은 0.01mm 로 반올림)
MAX_PREFIX_MM = 50  # 접두가 이보다 넓으면 맞추지 않는다(레터로 잘못 읽힌 긴 글)
BLANKS = "  　"  # 잴 수 있는 공백 — 반각 빈칸·줄 안 바꾸는 빈칸·전각 빈칸
FALLBACK_FACE = "함초롬바탕"  # 한글이 글꼴에 없는 글자를 찍는 글꼴(PDF 실측 — 돋움체의 「⋅」「⦁」「‧」)
LINE2 = ("text", "mm", "keep")

_FONTS, _ADV, _FONT_LOCK = {}, {}, threading.Lock()


def _glyph_em(face, ch):
    """글꼴 face(fonts.FontIndex.faces 항목)의 글자 폭(em) — 그 글꼴에 없는 글자·못 여는 글꼴이면 None. 글꼴은 프로세스에 한 번만 열고 폭은 기억한다
    (PyMuPDF 는 여러 스레드에서 함께 부르면 안 되므로 잠금 안에서만)."""
    fid = face["id"]
    with _FONT_LOCK:
        if (fid, ch) not in _ADV:
            if fid not in _FONTS:
                try:
                    import fitz
                    src = fonts.font_index().file_of(fid)
                    _FONTS[fid] = None if src is None else fitz.Font(fontbuffer=src) if isinstance(src, bytes) else fitz.Font(fontfile=str(src))
                except Exception as e:  # noqa: BLE001 — 깨진 글꼴 파일 하나가 편집을 막지 않게(어림 폭으로)
                    log.warning("[개요 줄 자리] 글꼴 %s 를 열지 못함: %r", face.get("path"), e)
                    _FONTS[fid] = None
            ft = _FONTS[fid]
            _ADV[fid, ch] = float(ft.glyph_advance(ord(ch))) if ft is not None and ft.has_glyph(ord(ch)) else None
        return _ADV[fid, ch]


def _rough(ch):
    """글꼴을 못 찾았을 때의 어림 폭(em) — 전각·넓은 글자·모호한 폭(한글 글꼴에선 전각 — □ ○ ① ※)은 1, 그 밖은 0.5."""
    return 1.0 if unicodedata.east_asian_width(ch) in "WFA" else 0.5


class Measure:
    """문서 하나의 글자 폭 재기 — 글자 모양·글꼴 찾기를 요청 한 번 동안 기억한다."""

    def __init__(self, doc):
        self.doc, self._chars, self._faces, self._table = doc, {}, {}, None

    def _char(self, cid):
        if cid not in self._chars:
            c = self.doc._defs["charPr"].get(str(cid))
            if c is None:
                self._chars[cid] = None
            else:
                fr = c.find(_h("fontRef"))

                def per(tag, default):  # 언어마다 값(% → 배)
                    e = c.find(_h(tag))
                    return {lang: (int(e.get(lang.lower(), default)) if e is not None else default) / 100 for lang in fonts.WEB_LANGS}
                self._chars[cid] = {"em": int(c.get("height", 1000)) / 100 * PT_MM, "half": c.get("useFontSpace") != "1", "bold": c.find(_h("bold")) is not None,
                                    "face": {lang: self.doc._face_name(lang, fr) for lang in fonts.WEB_LANGS},
                                    "ratio": per("ratio", 100), "rel": per("relSz", 100), "spacing": per("spacing", 0)}
        return self._chars[cid]

    def _face(self, name, lang, bold):
        key = (name, lang, bold)
        if key not in self._faces:
            ix = fonts.font_index()
            if self._table is None:
                self._table = self.doc.font_table()
            info = (self._table.get(lang) or {}).get(name) or {}
            r = ix.resolve(name, lang, info.get("type"), info.get("subst") or ()) if name else {"key": None}
            self._faces[key] = ((ix.face(r["key"], True) if bold else None) or ix.face(r["key"])) if r["key"] else None
        return self._faces[key]

    def _glyph(self, ch, name, lang, bold):
        """글자 하나의 글꼴 폭(em) — 문서 글꼴에 없으면 함초롬바탕, 그것도 없으면 어림."""
        for face in (self._face(name, lang, bold), self._face(FALLBACK_FACE, "HANGUL", bold)):
            w = _glyph_em(face, ch) if face else None
            if w is not None:
                return w
        return _rough(ch)

    def advance(self, ch, cid):
        """글자 하나가 차지하는 폭(mm) — 못 재는 글자(탭·줄 바꿈)·모르는 글자 모양이면 None."""
        c = self._char(cid)
        if c is None or ch in "\t\n\r  ":
            return None
        lang = fonts.lang_of(ch)
        k = c["em"] * c["rel"][lang] * c["ratio"][lang] * (1 + c["spacing"][lang])
        if ch in "  " and c["half"]:
            return 0.5 * k
        return self._glyph(ch, c["face"].get(lang) or c["face"].get("HANGUL"), lang, c["bold"]) * k

    def width(self, text, cid_at):
        """글의 폭(mm) — cid_at(i) = i 번째 글자의 글자 모양 id. 못 재면 None."""
        total = 0.0
        for i, ch in enumerate(text):
            w = self.advance(ch, cid_at(i))
            if w is None:
                return None
            total += w
        return total

    # ---- 자리 ----
    def _place(self, ppid, lead, tok, gap, cid_at):
        if not tok or any(ch not in BLANKS for ch in lead + gap):
            return None
        ps = self.doc._para_summary(self.doc._defs["paraPr"].get(str(ppid)))
        left, first = ps.get("indentLeftMm"), ps.get("firstLineMm")
        if left is None or first is None:  # HWPUNIT 이 아닌 단위(글자 수 등) — 안 건드린다
            return None
        lw = self.width(lead, cid_at)
        pw = self.width(lead + tok + gap, cid_at)
        if lw is None or pw is None:
            return None
        x0 = left + max(first, 0.0)
        return {"leftMm": left, "firstMm": first, "x0": x0, "leadMm": lw, "prefixMm": pw, "letterMm": x0 + lw, "textMm": x0 + pw,
                "line2Mm": left + max(-first, 0.0)}

    def place(self, pid, letter):
        """문단의 지금 자리 {leftMm, firstMm, x0, leadMm, prefixMm, letterMm, textMm, line2Mm} — 첫머리에 레터가 없거나 못 재면 None."""
        from app.heading_extract import _cid_at, run_ranges
        doc = self.doc
        p = doc._ids.get(pid)
        if p is None:
            return None
        lead, tok, gap = OE.prefix_of(doc._text(p), letter or None)
        rr, fb = run_ranges(doc, p), doc._char_id(p)
        return self._place(p.get("paraPrIDRef", "0"), lead, tok, gap, lambda i: _cid_at(rr, i, fb))

    def slot_place(self, slot):
        """슬롯이 새 줄에 주는 자리(동결한 접두·모양으로) — 대표가 없으면 None."""
        attrs = slot.get("attrs") or {}
        if not slot.get("prefix") or attrs.get("paraPrIDRef") is None:
            return None
        lead, tok, gap = OE.prefix_of(slot["prefix"], slot.get("letter") or None)
        cid = attrs.get("charPrIDRef", "0")
        return self._place(attrs["paraPrIDRef"], lead, tok, gap, lambda i: cid)


def clean_pos(body, cur=None):
    """화면이 보낸 슬롯 규칙을 검사해 저장 꼴로 — {line2, mm?, letterMm?, set: True}. 잘못된 값은 ValueError."""
    line2 = body.get("line2", "text")
    if line2 not in LINE2:
        raise ValueError(f"line2 는 {', '.join(LINE2)} 중 하나")
    out = {"line2": line2, "set": True}

    def num(key, what):
        v = body.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not 0 <= v <= 300:
            raise ValueError(f"{what}는 0~300 mm 의 숫자")
        return round(float(v), 2)
    if line2 == "mm":
        out["mm"] = num("mm", "둘째 줄 위치")
    if body.get("letterMm") is not None:
        out["letterMm"] = num("letterMm", "레터 위치")
    return out


def target(cur, pos, full=False, was=None):
    """자리 cur(place 결과)와 슬롯 규칙 pos → 넣을 (왼쪽 여백, 첫 줄) mm | None(그대로).
    full = 슬롯 서식을 통째로(사용자가 정한 규칙을 그 레벨 줄에 적용 · 개요 편집이 만든 새 줄) — 레터 위치도 옮기고 문단이 이미 준 값도 덮는다.
    아니면 저절로 맞추는 길: 문단이 둘째 줄을 정하지 않았거나(첫 줄 0) 앞서 저절로 넣은 값(was) 그대로일 때만, 레터 위치는 안 옮긴다."""
    pos = pos or {}
    mode = pos.get("line2", "text")
    full = full and bool(pos.get("set"))
    if not full:
        if mode == "keep" or (abs(cur["firstMm"]) > EPS and (was is None or abs(cur["firstMm"] - was) > EPS)):
            return None
        x0 = cur["x0"]
    else:
        x0 = cur["x0"] if pos.get("letterMm") is None else pos["letterMm"] - cur["leadMm"]
        if x0 < -EPS:
            raise ValueError(f"레터 위치 {pos['letterMm']:g}mm 는 앞 공백 폭 {cur['leadMm']:.1f}mm 보다 작을 수 없습니다")
        x0 = max(x0, 0.0)
    if mode == "text":
        if cur["prefixMm"] > MAX_PREFIX_MM:
            return None
        l2 = x0 + cur["prefixMm"]
    elif mode == "mm":
        l2 = float(pos["mm"])
    else:  # keep — 레터 위치만 옮기면 둘째 줄도 같이 민다
        l2 = cur["line2Mm"] + (x0 - cur["x0"])
    left, first = round(min(x0, l2), 2), round(x0 - l2, 2)
    if abs(left - cur["leftMm"]) <= EPS and abs(first - cur["firstMm"]) <= EPS:
        return None
    return left, first


def align(doc, ov, pid, full=False, measure=None):
    """개요 줄 pid 를 슬롯 규칙대로 — 바꿨으면 그 문단의 새 서식 요약, 아니면 None. 괄호 줄(구분 라벨·괄호 소제목 — 글 전체가 레터)은 안 건드린다.
    문단 여백만 바꾼다(format_para — 런마다 글자 모양·문단 번호는 그대로). full 의 잘못된 규칙은 ValueError."""
    line = ov["lines"].get(pid)
    if line is None or line.get("role") in OE.ROOTED or line.get("role") == OE.TABLE:  # 표 제목 줄(② §8-7)도 자리 규칙 없음
        return None
    slot = OE._slot(ov, line["tpl"], line["level"]) or {}
    m = measure or Measure(doc)
    cur = m.place(pid, line.get("letter"))
    if cur is None:
        return None
    t = target(cur, slot.get("pos"), full=full, was=line.get("first"))
    if t is None:
        return None
    left, first = t
    doc.format_para([pid], {"indentLeftMm": left, "firstLineMm": first})
    p = doc._ids[pid]
    fmt = doc._summary(p.get("paraPrIDRef"), doc._char_id(p))
    if abs((fmt.get("firstLineMm") or 0.0) - first) > EPS or abs((fmt.get("indentLeftMm") or 0.0) - left) > EPS:
        return None  # 문단 모양에 여백 항목이 없어 못 넣음
    line["first"] = first
    return fmt


def align_quiet(doc, ov, pid, measure=None):
    """글 고침 뒤 저절로 맞추기 — 어떤 오류도 글 반영을 막지 않는다(기록만)."""
    try:
        return align(doc, ov, pid, measure=measure)
    except Exception as e:  # noqa: BLE001
        log.warning("[개요 줄 자리] %s 맞추기 실패: %r", pid, e)
        return None


def slot_lines(ov, tid, level):
    return [pid for pid, x in ov["lines"].items() if x["tpl"] == str(tid) and int(x["level"]) == int(level)]


def apply_slot(doc, ov, tid, level, pos):
    """슬롯 (tid, level)의 규칙을 pos 로 정하고 그 레벨 줄 모두에 적용 → {바뀐 문단 id: 새 서식 요약}. 잘못된 규칙은 ValueError(슬롯 규칙은 그대로)."""
    slot = OE._slot(ov, tid, level)
    if slot is None:
        raise ValueError("그런 템플릿 레벨이 없습니다")
    old = slot.get("pos")
    slot["pos"] = pos
    m, out = Measure(doc), {}
    try:
        for pid in slot_lines(ov, tid, level):
            fmt = align(doc, ov, pid, full=True, measure=m)
            if fmt is not None:
                out[pid] = fmt
    except ValueError:
        if not out:  # 문서를 아직 안 건드렸다 — 규칙만 되돌린다(건드렸으면 트랜잭션이 통째로 되돌림)
            if old is None:
                slot.pop("pos", None)
            else:
                slot["pos"] = old
        raise
    return out


PREVIEW_MAX = 30  # 미리보기 묶음마다 보내는 줄 id 수


def _spot(cur, left=None, first=None):
    """자리 요약 {letterMm, textMm, line2Mm, leftMm, firstMm}(0.1mm) — left·first 를 주면 그 여백을 넣은 뒤의 자리."""
    if left is None:
        left, first = cur["leftMm"], cur["firstMm"]
    x0 = left + max(first, 0.0)
    return {"letterMm": _r1(x0 + cur["leadMm"]), "textMm": _r1(x0 + cur["prefixMm"]), "line2Mm": _r1(left + max(-first, 0.0)),
            "leftMm": _r1(left), "firstMm": _r1(first)}


def preview(doc, ov, tid, level, pos, order=None):
    """「자리 수정 → 적용」 을 하면 어떻게 되나 — 문서·오버레이를 안 바꾼다(apply_slot 과 같은 계산: target(full=True)).
    → {lines, changed, same, skipped, error, rep{para, before, after}|None, slot{before, after}|None(새 줄의 자리),
       groups[{count, changed, before, after, paras(문서 순 PREVIEW_MAX 개까지), more}]} — 바뀌는 묶음 먼저, 줄 수 순."""
    slot = OE._slot(ov, tid, level)
    if slot is None:
        raise ValueError("그런 템플릿 레벨이 없습니다")
    pos = dict(pos or {}, set=True)
    m = Measure(doc)
    ids = slot_lines(ov, tid, level)
    if order is not None:
        ids.sort(key=lambda p: order.get(p, 1 << 30))
    groups, skipped, error, rep = {}, 0, None, None
    for pid in ids:
        line = ov["lines"][pid]
        if line.get("role") in OE.ROOTED:
            skipped += 1
            continue
        try:
            cur = m.place(pid, line.get("letter"))
        except Exception:  # noqa: BLE001 — 줄 하나를 못 재도 미리보기는 계속
            cur = None
        if cur is None:
            skipped += 1
            continue
        try:
            t = target(cur, pos, full=True)
        except ValueError as e:
            error = error or str(e)
            skipped += 1
            continue
        before = _spot(cur)
        after = _spot(cur, *t) if t else dict(before)
        key = (tuple(before.values()), tuple(after.values()))
        g = groups.setdefault(key, {"count": 0, "changed": t is not None, "before": before, "after": after, "paras": []})
        g["count"] += 1
        g["paras"].append(pid)
        if pid == slot.get("rep"):
            rep = {"para": pid, "before": before, "after": after}
    out = []
    for g in groups.values():
        g["more"] = max(0, len(g["paras"]) - PREVIEW_MAX)
        g["paras"] = g["paras"][:PREVIEW_MAX]
        out.append(g)
    out.sort(key=lambda g: (not g["changed"], -g["count"]))
    sl = None
    try:
        at = m.slot_place(slot)
        if at:
            tg = target(at, pos, full=True)
            sl = {"before": _spot(at), "after": _spot(at, *tg) if tg else _spot(at)}
    except ValueError as e:
        error = error or str(e)
    except Exception:  # noqa: BLE001
        sl = None
    changed = sum(g["count"] for g in out if g["changed"])
    return {"lines": len(ids), "changed": changed, "same": sum(g["count"] for g in out) - changed, "skipped": skipped, "error": error,
            "rep": rep, "slot": sl, "groups": out}


def carry(old, new):
    """2단계를 다시 돌려 오버레이를 새로 만들 때 — 사용자가 정한 슬롯 규칙(같은 앵커·레벨)과 저절로 맞춘 줄의 기억을 옮긴다."""
    if not old or not new:
        return
    by_anchor = {t.get("anchor"): t for t in old.get("templates", {}).values()}
    for t in new.get("templates", {}).values():
        o = by_anchor.get(t.get("anchor"))
        for lv, sl in t.get("slots", {}).items():
            pos = ((o or {}).get("slots", {}).get(lv) or {}).get("pos")
            if pos and pos.get("set"):
                sl["pos"] = dict(pos)
    for pid, x in new.get("lines", {}).items():
        f = (old.get("lines", {}).get(pid) or {}).get("first")
        if f is not None:
            x["first"] = f


def _r1(v):
    return None if v is None else round(v, 1)


def view(doc, ov):
    """화면용 요약(outline_edit.view) + 템플릿마다 slots{레벨: {letter, lines(그 레벨 줄 수), rooted(괄호 줄 — 자리 규칙 없음), pos(규칙), at(대표 서식의 자리 mm), to(규칙을 건 뒤 — 새 줄의 자리)}}."""
    out = OE.view(ov)
    m = Measure(doc)
    counts = Counter((x["tpl"], int(x["level"])) for x in ov["lines"].values())
    roles = {}
    for x in ov["lines"].values():
        roles.setdefault((x["tpl"], int(x["level"])), set()).add(x.get("role"))
    for tid, t in ov["templates"].items():
        slots = {}
        for lv, sl in t.get("slots", {}).items():
            rs = roles.get((tid, int(lv)), set())
            rooted = bool(rs) and rs <= set(OE.ROOTED) or (not rs and t.get("kind") == "label" and lv == "1") or bool(sl.get("table"))  # 표 제목 레벨(② §8-7)도 자리 규칙 없음
            item = {"letter": sl.get("letter") or "", "lines": counts.get((tid, int(lv)), 0), "rooted": rooted, **({"table": True} if sl.get("table") else {}),
                    "pos": {k: v for k, v in (sl.get("pos") or {"line2": "text"}).items()}}
            try:
                at = None if rooted else m.slot_place(sl)
            except Exception as e:  # noqa: BLE001 — 보기 하나가 문서 열기를 막지 않게
                log.warning("[개요 줄 자리] T%s L%s 자리 계산 실패: %r", t.get("no"), lv, e)
                at = None
            if at:
                item["at"] = {k: _r1(at[k]) for k in ("letterMm", "textMm", "line2Mm", "leadMm", "leftMm", "firstMm")}
                try:
                    tg = target(at, sl.get("pos"), full=True)
                except ValueError:
                    tg = None
                left, first = tg if tg else (at["leftMm"], at["firstMm"])
                x0 = left + max(first, 0.0)
                item["to"] = {"letterMm": _r1(x0 + at["leadMm"]), "textMm": _r1(x0 + at["prefixMm"]), "line2Mm": _r1(left + max(-first, 0.0))}
            slots[lv] = item
        out["templates"][tid]["slots"] = slots
    from app import outline_match  # 레벨의 대표 · 넣어 온 레벨 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2) — outline_match 는 이 모듈을 안 읽는다
    for tid, ex in outline_match.view_extra(ov, outline_match.context(doc, ov)).items():
        t = out["templates"].get(tid)
        if t is None:
            continue
        for lv, sx in ex.pop("slots").items():
            if lv in t["slots"]:
                t["slots"][lv].update(sx)
        t.update(ex)
    from app import outline_lift  # 표 제목을 L1 로 넣은 템플릿(② §8-7) — lift{tables, sigs}
    for tid, ex in outline_lift.view_extra(ov).items():
        if tid in out["templates"]:
            out["templates"][tid].update(ex)
    return out
