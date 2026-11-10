"""HWPX formats (spec §8): paragraph/char shape summaries, derive/apply, table cell look.

FormatMixin is mixed into HwpxDoc and uses its bookkeeping (_ids, _defs, _add_def, _font_id, _touch, ...).
token = "p{paraPrIDRef}|c{charPrIDRef}". apply_format keeps each paragraph's own styleIDRef: the paraPr/charPr
pair is the whole look (incl. heading/numbering), the style only names it."""
import copy
import re

from lxml import etree

# same XML names as app/hwpx_doc.py, kept local because hwpx_doc imports this module
HP, HH, HC = (f"http://www.hancom.co.kr/hwpml/2011/{n}" for n in ("paragraph", "head", "core"))


def _p(tag):
    return f"{{{HP}}}{tag}"


def _h(tag):
    return f"{{{HH}}}{tag}"


def _c(tag):
    return f"{{{HC}}}{tag}"


P, RUN, T, TBL, PIC, TC, SUBLIST, CTRL, AUTONUM_EL, LINESEG = map(
    _p, ["p", "run", "t", "tbl", "pic", "tc", "subList", "ctrl", "autoNum", "linesegarray"])
ALIGN = {"JUSTIFY": "justify", "LEFT": "left", "RIGHT": "right", "CENTER": "center",
         "DISTRIBUTE": "distribute", "DISTRIBUTE_SPACE": "distribute"}
CHAR_ORDER = ["fontRef", "ratio", "spacing", "relSz", "offset", "italic", "bold", "underline", "strikeout",
              "outline", "shadow", "emboss", "engrave", "supscript", "subscript"]  # charPr child order (schema)
PARA_MARGIN = {"firstLineMm": "intent", "indentLeftMm": "left", "indentRightMm": "right",
               "spaceBeforePt": "prev", "spaceAfterPt": "next"}
CELL_MARGIN = {"l": "left", "r": "right", "t": "top", "b": "bottom"}
SUMMARY_KEYS = {"font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct", "align", "lineSpacingPct", *PARA_MARGIN}
CHAR_KEYS = {"font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct"}  # the charPr part of SUMMARY_KEYS
CHAR_LANGS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")  # hh:ratio·hh:spacing attributes (per language)
LANG_FONT_KEYS = {"fontLatin": "LATIN", "fontHanja": "HANJA", "fontJapanese": "JAPANESE", "fontSymbol": "SYMBOL"}  # read-only: 웹이 언어 글꼴로 그리는 글자(app/fonts.py LANG_RANGE)
HEX6 = re.compile(r"#[0-9A-Fa-f]{6}")


def _spacing_boxes(pp):
    """(element holding hh:margin/hh:lineSpacing, scale) of a paraPr. Inside hp:switch the HwpUnitChar
    hp:case holds HWPUNIT; hp:default and the plain (switch-less) form hold 2×HWPUNIT."""
    sw = pp.find(_p("switch"))
    return [(c, 1 if c.tag == _p("case") else 2) for c in sw] if sw is not None else [(pp, 2)]


def _flag(c, name, on):
    """Add/remove a charPr flag child (hh:bold, hh:italic, hh:underline) at its schema position."""
    e = c.find(_h(name))
    if on and e is None:
        e = c.makeelement(_h(name), {})
        before = [x for x in c if etree.QName(x).localname in CHAR_ORDER[:CHAR_ORDER.index(name)]]
        if before:
            before[-1].addnext(e)
        else:
            c.insert(0, e)
    elif not on and e is not None:
        c.remove(e)
    return e


def _set_fill(bf, color):
    """Replace a borderFill's brush by a plain winBrush of color (None = no fill)."""
    old = bf.find(_c("fillBrush"))
    wb = old.find(_c("winBrush")) if old is not None else None
    if old is not None:
        bf.remove(old)
    if color is not None:
        attrs = dict(wb.attrib) if wb is not None else {"faceColor": "", "hatchColor": "#000000", "alpha": "0"}
        attrs["faceColor"] = color
        etree.SubElement(etree.SubElement(bf, _c("fillBrush")), _c("winBrush"), attrs)


class FormatMixin:
    # ---------------------------------------------------------------- paragraph formats
    def get_format(self, para_id: str) -> dict:
        p = self._para(para_id)
        return self._fmt(p.get("paraPrIDRef"), self._char_id(p))

    def _fmt(self, pid, cid):
        return {"token": f"p{pid}|c{cid}", "summary": self._summary(pid, cid)}

    def _para(self, block_id):
        el = self._ids[block_id]
        if el.tag != P:
            raise ValueError(f"{block_id} is not a paragraph")
        return el

    def _parse(self, fmt):
        m = re.fullmatch(r"p(\d+)\|c(\d+)", str(fmt.get("token")))
        if not m or m[1] not in self._defs["paraPr"] or m[2] not in self._defs["charPr"]:
            raise ValueError("format token is not from this document")
        return m[1], m[2]

    def _summary(self, pid, cid):
        if (pid, cid) not in self._summ:
            self._summ[pid, cid] = {**self._char_summary(self._defs["charPr"].get(cid)),
                                    **self._para_summary(self._defs["paraPr"].get(pid))}
        return dict(self._summ[pid, cid])

    def _char_summary(self, c):
        if c is None:
            return {"font": None, "sizePt": None, "bold": False, "italic": False, "underline": False, "color": None,
                    "ratioPct": 100, "spacingPct": 0}
        fr, u = c.find(_h("fontRef")), c.find(_h("underline"))
        font = self._face_name("HANGUL", fr)
        color = c.get("textColor", "")
        # 장평·자간 are per language; the hangul value stands for the run (Korean documents: hangul ≠ latin in 4/439 charPr)
        ratio, spacing = c.find(_h("ratio")), c.find(_h("spacing"))
        out = {"font": font, **{key: self._face_name(lang, fr) for key, lang in LANG_FONT_KEYS.items()},
               "sizePt": int(c.get("height", 1000)) / 100,
               "bold": c.find(_h("bold")) is not None, "italic": c.find(_h("italic")) is not None,
               "underline": u is not None and u.get("type", "NONE") != "NONE",
               "color": color.upper() if HEX6.fullmatch(color) else None,
               "ratioPct": int(ratio.get("hangul", 100)) if ratio is not None else 100,
               "spacingPct": int(spacing.get("hangul", 0)) if spacing is not None else 0}
        if c.get("useFontSpace") != "1":  # read-only: 「글꼴에 어울리는 빈칸」 끔 = 빈칸 폭 0.5em × (1 + 자간), 글꼴 무관
            out["halfSpace"] = True
        for tag, val in (("supscript", "sup"), ("subscript", "sub")):  # read-only 윗·아래첨자(웹은 크기 × 0.64, app/fonts.py SCRIPT_SIZE)
            if c.find(_h(tag)) is not None:
                out["script"] = val
                break
        return out

    def _face_name(self, lang, fr):
        """charPr fontRef 의 lang 글꼴 이름(hh:fontface lang 의 hh:font face)."""
        face = self._fontface(lang) if fr is not None else None
        fid = fr.get(lang.lower()) if fr is not None else None
        return next((f.get("face") for f in face.iterchildren(_h("font")) if f.get("id") == fid), None) if face is not None else None

    def font_table(self) -> dict:
        """{lang: {face: {"type": TTF|HFT, "subst": [대체 글꼴]}}} — header 의 언어별 글꼴 목록(읽기만, 웹 글꼴 계획 app/fonts.py)."""
        out = {}
        for lang in ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"):
            face = self._fontface(lang)
            for f in face.iterchildren(_h("font")) if face is not None else ():
                if f.get("face"):
                    out.setdefault(lang, {}).setdefault(f.get("face"), {
                        "type": f.get("type") or "TTF", "subst": [s.get("face") for s in f.iterchildren(_h("substFont")) if s.get("face")]})
        return out

    def _para_summary(self, pp):
        out = {"align": None, "lineSpacingPct": None, **dict.fromkeys(PARA_MARGIN, 0.0)}
        if pp is None:
            return out
        a = pp.find(_h("align"))
        out["align"] = ALIGN.get(a.get("horizontal")) if a is not None else None
        box, scale = _spacing_boxes(pp)[0]
        m, ls = box.find(_h("margin")), box.find(_h("lineSpacing"))
        for key, tag in PARA_MARGIN.items():
            e = m.find(_c(tag)) if m is not None else None
            # ponytail: only HWPUNIT values are read; another unit (e.g. CHAR) reports None
            v = int(e.get("value", 0)) / scale if e is not None and e.get("unit", "HWPUNIT") == "HWPUNIT" else None
            out[key] = None if v is None else round(v * 25.4 / 7200 if key.endswith("Mm") else v / 100, 2)
        if ls is not None and ls.get("type") == "PERCENT":
            out["lineSpacingPct"] = int(ls.get("value"))
        bs = pp.find(_h("breakSetting"))  # read-only: 한글 줄 나눔 단위 — BREAK_WORD = 어절, KEEP_WORD = 글자(이름과 반대)
        out["wordBreak"] = "word" if bs is not None and bs.get("breakNonLatinWord") == "BREAK_WORD" else "char"
        for key in ("keepWithNext", "keepLines", "widowOrphan"):  # read-only 쪽 나눔(다음 문단과 함께·문단 보호·외톨이줄 보호): 켜진 것만
            if bs is not None and bs.get(key) == "1":
                out[key] = True
        return out

    def derive_format(self, fmt: dict, changes: dict) -> dict:
        pid, cid = self._parse(fmt)
        ch = {k: v for k, v in changes.items() if v is not None and v != ""}  # None/"" = keep
        if set(ch) - SUMMARY_KEYS:
            raise ValueError(f"unknown format keys: {sorted(set(ch) - SUMMARY_KEYS)}")
        c, pp = copy.deepcopy(self._defs["charPr"][cid]), copy.deepcopy(self._defs["paraPr"][pid])
        self._set_chars(c, ch)
        if "align" in ch:
            horizontal = {v: k for k, v in ALIGN.items() if k != "DISTRIBUTE_SPACE"}.get(ch["align"])
            if horizontal is None:
                raise ValueError(f"unknown align {ch['align']!r}")
            pp.find(_h("align")).set("horizontal", horizontal)
        for box, scale in _spacing_boxes(pp):
            m, ls = box.find(_h("margin")), box.find(_h("lineSpacing"))
            for key, tag in PARA_MARGIN.items():
                e = m.find(_c(tag)) if m is not None else None
                if key in ch and e is not None:
                    hwp = float(ch[key]) * (7200 / 25.4 if key.endswith("Mm") else 100)
                    e.attrib.update({"value": str(round(hwp * scale)), "unit": "HWPUNIT"})
            if "lineSpacingPct" in ch and ls is not None:
                ls.attrib.update({"type": "PERCENT", "value": str(round(float(ch["lineSpacingPct"])))})
        return self._fmt(self._add_def("paraPr", pp), self._add_def("charPr", c))

    def _set_chars(self, c, ch):
        """Char summary keys of `ch` onto charPr element c (in place)."""
        if "sizePt" in ch:
            c.set("height", str(round(float(ch["sizePt"]) * 100)))
        if "color" in ch:
            if not HEX6.fullmatch(ch["color"]):
                raise ValueError("color must be #RRGGBB")
            c.set("textColor", ch["color"].upper())
        for key in ("italic", "bold"):
            if key in ch:
                _flag(c, key, bool(ch[key]))
        if "underline" in ch:
            u = c.find(_h("underline"))
            if ch["underline"] and u is None:
                u = _flag(c, "underline", True)
                u.attrib.update({"type": "BOTTOM", "shape": "SOLID", "color": c.get("textColor", "#000000")})
            elif u is not None:
                u.set("type", "BOTTOM" if ch["underline"] else "NONE")
        for key, tag, lo, hi in (("ratioPct", "ratio", 50, 200), ("spacingPct", "spacing", -50, 50)):   # 장평·자간: 모든 언어에 같은 값
            if key in ch:
                v = round(float(ch[key]))
                if not lo <= v <= hi:
                    raise ValueError(f"{key} 는 {lo}~{hi}: {ch[key]!r}")
                e = c.find(_h(tag))
                if e is None:
                    e = _flag(c, tag, True)
                for attr in list(e.attrib) or CHAR_LANGS:
                    e.set(attr, str(v))
        fr = c.find(_h("fontRef"))
        if "font" in ch and fr is not None:
            for attr in list(fr.attrib):  # hangul/latin/... -> fontface lang HANGUL/LATIN/...
                fid = self._font_id(attr.upper(), ch["font"])
                if fid is not None:
                    fr.set(attr, fid)

    def apply_format(self, para_ids: list[str], fmt: dict, keep_numbering: bool = False, runs: dict | None = None) -> None:
        """keep_numbering: each paragraph keeps its own hh:heading (outline/bullet/number) inside fmt's paraPr.
        runs: None = every text run takes fmt's charPr; a dict of char keys = fmt gives the paragraph shape only and each
        text run keeps its own charPr with just those keys changed (spec_서식 ② §3 적용 — 런 강조 보존)."""
        pid, cid = self._parse(fmt)
        if runs is not None:
            runs = {k: v for k, v in runs.items() if v is not None and v != ""}
            if bad := set(runs) - CHAR_KEYS:
                raise ValueError(f"runs takes char keys only: {sorted(bad)}")
        own = {}  # run charPr -> charPr with `runs` applied

        def char_of(r):
            if runs is None:
                return cid
            old = r.get("charPrIDRef")
            if old not in own:
                c = copy.deepcopy(self._defs["charPr"].get(old))
                if c is not None:
                    self._set_chars(c, runs)
                own[old] = old if c is None else self._add_def("charPr", c)
            return own[old]
        for p in [self._para(i) for i in para_ids]:
            ppid = self._with_heading(pid, p.get("paraPrIDRef")) if keep_numbering else pid
            # text runs only: runs holding a table/picture block keep their char shape
            text_runs = [r for r in p.iterchildren(RUN) if r.find(TBL) is None and r.find(PIC) is None
                         and (r.find(T) is not None or r.find(f"{CTRL}/{AUTONUM_EL}") is not None or len(r) == 0)]   # 빈 런(글 없는 칸)도 — 뒤에 칠 글의 모양(표 서식 정리)
            want = [char_of(r) for r in text_runs]
            if p.get("paraPrIDRef") == ppid and all(r.get("charPrIDRef") == c for r, c in zip(text_runs, want)):
                continue
            p.set("paraPrIDRef", ppid)
            for r, c in zip(text_runs, want):
                r.set("charPrIDRef", c)
            for ls in p.findall(LINESEG):
                p.remove(ls)
            self._touch(p)

    def _with_heading(self, pid, own_pid):
        """Id of paraPr pid carrying own_pid's hh:heading (deduped; pid itself when the headings match)."""
        own, base = self._defs["paraPr"].get(own_pid), self._defs["paraPr"][pid]
        h_own, h_base = (x.find(_h("heading")) if x is not None else None for x in (own, base))
        if h_own is None or h_base is None or dict(h_own.attrib) == dict(h_base.attrib):
            return pid
        pp = copy.deepcopy(base)
        pp.replace(pp.find(_h("heading")), copy.deepcopy(h_own))
        return self._add_def("paraPr", pp)

    # ---------------------------------------------------------------- table cells
    def _cell(self, block_id):
        el = self._ids[block_id]
        if el.tag != TC:
            raise ValueError(f"{block_id} is not a table cell")
        return el

    def _fill(self, bf_id):
        """'#RRGGBB' of a borderFill's winBrush; None for none, #AARRGGBB (CLR_DEFAULT-style) or no brush."""
        bf = self._defs["borderFill"].get(bf_id)
        wb = bf.find(f"{_c('fillBrush')}/{_c('winBrush')}") if bf is not None else None
        color = wb.get("faceColor", "none") if wb is not None else "none"
        return color.upper() if HEX6.fullmatch(color) else None

    def _cell_look(self, tc):
        sub = tc.find(SUBLIST)
        m = self._cell_margin(tc)
        return {"fill": self._fill(tc.get("borderFillIDRef")),
                "valign": (sub.get("vertAlign", "CENTER") if sub is not None else "CENTER").lower(),
                "marginsMm": {k: round(int(m.get(a, 0)) * 25.4 / 7200, 2) if m is not None else 0.0
                              for k, a in CELL_MARGIN.items()}}

    def _border_lines(self, bf_id):
        """{t,r,b,l} of a borderFill's lines: {type, widthMm, color} (Hancom type e.g. SOLID/DASH/DOT), None = no line;
        None for an unknown id. Read-only view data (web draws the original cell lines)."""
        bf = self._defs["borderFill"].get(bf_id)
        if bf is None:
            return None
        out = {}
        for k, side in CELL_MARGIN.items():
            el = bf.find(_h(f"{side}Border"))
            kind = el.get("type", "NONE") if el is not None else "NONE"
            if kind == "NONE":
                out[k] = None
                continue
            width = re.match(r"\s*([\d.]+)", el.get("width", ""))
            color = el.get("color", "")
            out[k] = {"type": kind, "widthMm": float(width.group(1)) if width else 0.1,
                      "color": color.upper() if HEX6.fullmatch(color) else "#000000"}
        return out

    def _cell_margin(self, tc):
        m = tc.find(_p("cellMargin")) if tc.get("hasMargin") == "1" else None
        if m is None:  # hasMargin="0": the table's inner margin applies
            m = tc.getparent().getparent().find(_p("inMargin"))
        return m

    def get_cell_format(self, cell_id: str) -> dict:
        tc = self._cell(cell_id)
        return {"text": self.get_format(self._id(tc.find(SUBLIST).find(P))), **self._cell_look(tc)}

    def apply_cell_format(self, cell_ids: list[str], cell_fmt: dict, parts, keep_numbering: bool = True) -> None:
        parts = set(parts)
        if parts - {"text", "fill", "valign", "margins"}:
            raise ValueError(f"unknown parts: {sorted(parts)}")
        fill, valign = cell_fmt.get("fill"), str(cell_fmt.get("valign")).upper()
        if "fill" in parts and fill is not None and not HEX6.fullmatch(fill):
            raise ValueError("fill must be #RRGGBB or null")
        if "valign" in parts and valign not in ("TOP", "CENTER", "BOTTOM"):
            raise ValueError("valign must be top, center or bottom")
        for tc in [self._cell(i) for i in cell_ids]:
            sub, new = tc.find(SUBLIST), []  # (element, attr, value) to set
            margin_changed = False
            if "text" in parts:
                self.apply_format([self._id(p) for p in sub.iterchildren(P)], cell_fmt["text"], keep_numbering)
            if "fill" in parts:  # clone the cell's own borderFill (keeps its borders), change only the brush
                bf = copy.deepcopy(self._defs["borderFill"][tc.get("borderFillIDRef")])
                _set_fill(bf, fill and fill.upper())
                new.append((tc, "borderFillIDRef", self._add_def("borderFill", bf)))
            if "valign" in parts:
                new.append((sub, "vertAlign", valign))
            if "margins" in parts:
                old = self._cell_margin(tc)
                values = {a: int(old.get(a, 0)) if old is not None else 0 for a in CELL_MARGIN.values()}
                for k, mm in cell_fmt["marginsMm"].items():
                    a = CELL_MARGIN[k]
                    if float(mm) != round(values[a] * 25.4 / 7200, 2):
                        value = round(float(mm) * 7200 / 25.4)
                        margin_changed |= value != values[a]
                        values[a] = value
                m = tc.find(_p("cellMargin"))
                if m is None:
                    m = etree.SubElement(tc, _p("cellMargin"))
                new += [(m, a, str(v)) for a, v in values.items()]
                new.append((tc, "hasMargin", "1"))
            new = [(el, a, v) for el, a, v in new if el.get(a) != v]
            for el, a, v in new:
                el.set(a, v)
            if margin_changed:
                for ls in list(sub.iter(LINESEG)):
                    ls.getparent().remove(ls)
            if new:
                self._touch(tc)
