"""엑셀(xlsx) 문서 — 원본 XML 을 직접 읽고 고친다(spec_엑셀편집 ② §2~§4). 순수 — 웹 · 작업 폴더를 모른다(표준 라이브러리 + lxml).

openpyxl 로 다시 쓰지 않는다: 이 모듈이 모르는 것(그림 · 차트 · 조건부 서식 · 유효성 · 인쇄 설정 …)이 바이트 그대로 남게, 고친 XML 부분만 다시 쓴다.
행 번호 · 열 번호는 1 부터(엑셀과 같음)."""
import colorsys
import datetime as dt
import io
import posixpath
import re
import zipfile

from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
XML_NS = "http://www.w3.org/XML/1998/namespace"
STRICT = "http://purl.oclc.org/ooxml/spreadsheetml/main"
REL_SHEET = R_NS + "/worksheet"
REL_CALC = R_NS + "/calcChain"
REL_TABLE = R_NS + "/table"
REL_DRAW = R_NS + "/drawing"
REL_COMMENTS = R_NS + "/comments"
MAX_ROW, MAX_COL = 1048576, 16384
INT_DIGITS = 11   # 정수부가 이보다 긴 숫자 꼴은 글로(ISBN · 번호 — 엑셀이 지수로 보이거나 끝자리를 잃지 않게: ② §3)


def q(tag):
    return f"{{{NS}}}{tag}"


class SheetError(ValueError):
    """사람에게 보일 까닭이 있는 거절(끝점이 400 · 409 로)."""


_PARSER = etree.XMLParser(resolve_entities=False, huge_tree=True, remove_blank_text=False)


# ---- 칸 주소 ----------------------------------------------------------------------------------------------------

def col_name(c: int) -> str:
    s = ""
    while c > 0:
        c, m = divmod(c - 1, 26)
        s = chr(65 + m) + s
    return s


def col_num(s: str) -> int:
    n = 0
    for ch in s.upper():
        n = n * 26 + ord(ch) - 64
    return n


CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d+)$")


def parse_cell(ref: str):
    m = CELL.match(ref or "")
    if not m:
        raise ValueError(ref)
    return int(m.group(2)), col_num(m.group(1))


def cell_ref(r: int, c: int) -> str:
    return f"{col_name(c)}{r}"


def parse_range(ref: str):
    """「A1」 · 「A1:C3」 → (r0, c0, r1, c1)."""
    a, _, b = (ref or "").partition(":")
    r0, c0 = parse_cell(a)
    r1, c1 = parse_cell(b) if b else (r0, c0)
    return min(r0, r1), min(c0, c1), max(r0, r1), max(c0, c1)


def range_ref(r0, c0, r1, c1) -> str:
    a, b = cell_ref(r0, c0), cell_ref(r1, c1)
    return a if a == b else f"{a}:{b}"


# ---- 행 옮기기(넣기 · 지우기) — 한 가지 규칙을 칸 · 범위 · 수식이 같이 쓴다 --------------------------------------------

class Shift:
    """행 넣기(at 부터 n 행 아래로) 또는 지우기(d0..d1). 칸 하나 = row() · 범위 = span()."""

    def __init__(self, insert_at=None, n=0, d0=None, d1=None):
        self.ins, self.n, self.d0, self.d1 = insert_at, n, d0, d1

    def row(self, r):
        """옮긴 행 번호 — 지운 행이면 None."""
        if self.ins is not None:
            return r + self.n if r >= self.ins else r
        if r < self.d0:
            return r
        if r <= self.d1:
            return None
        return r - (self.d1 - self.d0 + 1)

    def point(self, r):
        """자리(그림 · 쪽 나눔) — 지운 행 안이면 지운 첫 행 자리로."""
        got = self.row(r)
        return self.d0 if got is None else got

    def span(self, r0, r1):
        """범위의 첫 · 끝 행 → 옮긴 (r0, r1) · 모두 지웠으면 None. 넣기는 범위 안에 넣으면 늘어난다(엑셀과 같음)."""
        if self.ins is not None:
            return self.row(r0), self.row(r1)
        k = self.d1 - self.d0 + 1
        if r0 >= self.d0 and r1 <= self.d1:
            return None
        a = r0 if r0 < self.d0 else (self.d0 if r0 <= self.d1 else r0 - k)
        b = r1 if r1 < self.d0 else (self.d0 - 1 if r1 <= self.d1 else r1 - k)
        return a, b

    def ref(self, ref):
        """칸 · 범위 주소 글 → 옮긴 글 · 모두 지웠으면 None."""
        r0, c0, r1, c1 = parse_range(ref)
        got = self.span(r0, r1)
        return None if got is None else range_ref(got[0], c0, got[1], c1)

    def sqref(self, text):
        """빈칸으로 나눈 범위 목록 → 옮긴 목록 · 다 지웠으면 None."""
        out = []
        for part in (text or "").split():
            try:
                got = self.ref(part)
            except ValueError:
                out.append(part)
                continue
            if got:
                out.append(got)
        return " ".join(out) or None


# 수식 안의 칸 · 범위 참조 — 시트 이름이 붙을 수 있다. 큰따옴표 글 안은 건너뛴다(_formula_parts).
REF = re.compile(r"(?<![A-Za-z0-9_.$'!\]\\])((?:'(?:[^']|'')+'|[A-Za-z_\u0080-￿][A-Za-z0-9_.\u0080-￿]*)!)?"
                 r"(\$?)([A-Z]{1,3})(\$?)(\d{1,7})(?::(\$?)([A-Z]{1,3})(\$?)(\d{1,7}))?(?![A-Za-z0-9_(!])")


def _sheet_of(prefix: str) -> str:
    p = prefix[:-1]
    return p[1:-1].replace("''", "'") if p.startswith("'") else p


def shift_formula(text: str, here: str, target: str, sh: Shift) -> str:
    """수식 글 안에서 시트 target 을 가리키는 참조를 옮긴다(here = 이 수식이 있는 시트). 지운 행만 가리키는 참조 → #REF!."""
    def one(m):
        pre = m.group(1) or ""
        sheet = _sheet_of(pre) if pre else here
        if sheet != target:
            return m.group(0)
        r0 = int(m.group(5))
        if m.group(7) is None:
            got = sh.row(r0)
            return f"{pre}#REF!" if got is None else f"{pre}{m.group(2)}{m.group(3)}{m.group(4)}{got}"
        r1 = int(m.group(9))
        lo, hi = min(r0, r1), max(r0, r1)
        got = sh.span(lo, hi)
        if got is None:
            return f"{pre}#REF!"
        a, b = (got if r0 <= r1 else (got[1], got[0]))
        return f"{pre}{m.group(2)}{m.group(3)}{m.group(4)}{a}:{m.group(6)}{m.group(7)}{m.group(8)}{b}"
    return "".join(part if quoted else REF.sub(one, part) for quoted, part in _formula_parts(text))


def move_formula(text: str, dr: int, dc: int) -> str:
    """공유 수식을 칸마다 풀 때 — 상대 참조를 (dr, dc) 만큼 옮긴다($ 붙은 쪽은 그대로)."""
    def one(m):
        pre = m.group(1) or ""

        def pt(dc_, col, dr_, row):
            c = col if dc_ else col_name(col_num(col) + dc)
            r = row if dr_ else str(int(row) + dr)
            return f"{dc_}{c}{dr_}{r}"
        out = pre + pt(m.group(2), m.group(3), m.group(4), m.group(5))
        if m.group(7) is not None:
            out += ":" + pt(m.group(6), m.group(7), m.group(8), m.group(9))
        return out
    return "".join(part if quoted else REF.sub(one, part) for quoted, part in _formula_parts(text))


def _formula_parts(text):
    """수식 → [(큰따옴표 글인가, 조각)]."""
    out, i, buf = [], 0, ""
    while i < len(text):
        ch = text[i]
        if ch == '"':
            if buf:
                out.append((False, buf))
                buf = ""
            j = i + 1
            while j < len(text):
                if text[j] == '"':
                    if j + 1 < len(text) and text[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            out.append((True, text[i:j + 1]))
            i = j + 1
            continue
        buf += ch
        i += 1
    if buf:
        out.append((False, buf))
    return out


# ---- 색 · 표시 형식 ------------------------------------------------------------------------------------------------

INDEXED = ("000000 FFFFFF FF0000 00FF00 0000FF FFFF00 FF00FF 00FFFF 000000 FFFFFF FF0000 00FF00 0000FF FFFF00 FF00FF 00FFFF "
           "800000 008000 000080 808000 800080 008080 C0C0C0 808080 9999FF 993366 FFFFCC CCFFFF 660066 FF8080 0066CC CCCCFF "
           "000080 FF00FF FFFF00 00FFFF 800080 800000 008080 0000FF 00CCFF CCFFFF CCFFCC FFFF99 99CCFF FF99CC CC99FF FFCC99 "
           "3366FF 33CCCC 99CC00 FFCC00 FF9900 FF6600 666699 969696 003366 339966 003300 333300 993300 993366 333399 333333").split()
THEME_ORDER = ("lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink")
DATE_IDS = set(range(14, 23)) | set(range(27, 37)) | {45, 46, 47} | set(range(50, 59))
BUILTIN = {0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 9: "0%", 10: "0.00%", 11: "0.00E+00", 12: "# ?/?", 13: "# ??/??",
           37: "#,##0 ;(#,##0)", 38: "#,##0 ;[Red](#,##0)", 39: "#,##0.00;(#,##0.00)", 40: "#,##0.00;[Red](#,##0.00)", 48: "##0.0E+0", 49: "@"}


def _tint(hex6, tint):
    if not tint:
        return hex6
    r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = l * (1 + tint) if tint < 0 else l * (1 - tint) + tint
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), s)
    return "".join(f"{round(x * 255):02X}" for x in (r, g, b))


def _fmt_kind(code: str) -> str:
    """표시 형식 글 → date · time · datetime · percent · text · number · general."""
    if not code or code == "General":
        return "general"
    sec = code.split(";")[0]
    bare = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.', "", sec)
    if bare.strip() == "@":
        return "text"
    low = bare.lower()
    has_d = any(ch in low for ch in "yd") or ("m" in low and not any(ch in low for ch in "hs"))
    has_t = any(ch in low for ch in "hs")
    if has_d or has_t:
        return "datetime" if has_d and has_t else ("date" if has_d else "time")
    if "%" in bare:
        return "percent"
    if "0" in bare or "#" in bare:
        return "number"
    return "general"


def _general(v: float) -> str:
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    s = f"{v:.10g}"
    if "e" in s:
        return s.upper()
    return s


def serial_to_dt(v: float, date1904=False):
    base = dt.datetime(1904, 1, 1) if date1904 else dt.datetime(1899, 12, 30)
    return base + dt.timedelta(days=v)


def dt_to_serial(d: dt.datetime, date1904=False) -> float:
    base = dt.datetime(1904, 1, 1) if date1904 else dt.datetime(1899, 12, 30)
    delta = d - base
    return delta.days + delta.seconds / 86400


def format_number(v: float, code: str, date1904=False) -> str:
    kind = _fmt_kind(code)
    if kind in ("date", "time", "datetime"):
        try:
            d = serial_to_dt(v, date1904)
        except (OverflowError, ValueError):
            return _general(v)
        if kind == "date":
            return d.strftime("%Y-%m-%d")
        if kind == "time":
            return d.strftime("%H:%M:%S" if "s" in code.lower() else "%H:%M")
        return d.strftime("%Y-%m-%d %H:%M")
    sec = code.split(";")[0] if code else ""
    if kind == "percent":
        dec = _decimals(sec)
        return f"{v * 100:.{dec}f}%"
    if kind == "number":
        if "E+" in sec.upper():
            return f"{v:.{_decimals(sec)}E}"
        dec = _decimals(sec)
        bare = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.', "", sec)
        if "," in bare.split(".")[0]:
            return f"{v:,.{dec}f}"
        return f"{v:.{dec}f}"
    return _general(v)


def _decimals(sec):
    bare = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.', "", sec)
    if "." not in bare:
        return 0
    return len(re.match(r"[0#?]*", bare.split(".", 1)[1]).group(0))


NUM = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
NUM_COMMA = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
DATE = re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})\.?(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


# ---- 문서 ---------------------------------------------------------------------------------------------------------

class XlsxDoc:
    def __init__(self, data: bytes):
        try:
            self.zip = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise SheetError("xlsx(zip) 파일이 아닙니다 — 엑셀에서 .xlsx 로 저장해 올려 주세요") from e
        self.names = self.zip.namelist()
        self.parts: dict[str, etree._Element] = {}
        self.dirty: set[str] = set()
        self.dropped: set[str] = set()
        self.edited = False
        self.unshared: set[str] = set()
        self.wb_path = self._main()
        if self.wb_path not in self.names:
            raise SheetError("엑셀 통합 문서(workbook.xml)를 찾지 못했습니다")
        self.wb = self._xml(self.wb_path)
        if self.wb.tag.startswith("{" + STRICT):
            raise SheetError("「엄격한 Open XML」 형식의 xlsx 는 아직 못 엽니다 — 엑셀에서 「Excel 통합 문서(.xlsx)」 로 저장해 올려 주세요")
        pr = self.wb.find(q("workbookPr"))
        self.date1904 = pr is not None and pr.get("date1904") in ("1", "true")
        rels = self._rels(self.wb_path)
        self.sheets = []
        for s in self.wb.iter(q("sheet")):
            rid = s.get(f"{{{R_NS}}}id")
            tgt = rels.get(rid)
            if tgt and tgt[1] == REL_SHEET and tgt[0] in self.names:
                self.sheets.append({"name": s.get("name") or "", "path": tgt[0], "hidden": s.get("state") in ("hidden", "veryHidden")})
        if not self.sheets:
            raise SheetError("이 파일에는 워크시트가 없습니다")
        self._load_strings(rels)
        self._load_styles(rels)

    # -- zip · XML 부분 --
    def _main(self):
        try:
            root = self._xml("_rels/.rels")
        except KeyError:
            return "xl/workbook.xml"
        for r in root:
            if r.get("Type", "").endswith("/officeDocument"):
                return r.get("Target", "").lstrip("/")
        return "xl/workbook.xml"

    def _xml(self, name):
        if name not in self.parts:
            self.parts[name] = etree.fromstring(self.zip.read(name), _PARSER)
        return self.parts[name]

    def _touch(self, name):
        self.dirty.add(name)
        self.edited = True

    @staticmethod
    def _rels_name(path):
        d, b = posixpath.split(path)
        return posixpath.join(d, "_rels", b + ".rels")

    def _rels(self, path) -> dict:
        """부분의 관계 → {rId: (경로, 종류)}."""
        name = self._rels_name(path)
        if name not in self.names:
            return {}
        out, base = {}, posixpath.dirname(path)
        for r in self._xml(name):
            if r.get("TargetMode") == "External":
                continue
            t = r.get("Target", "")
            full = t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join(base, t))
            out[r.get("Id")] = (full, r.get("Type", ""))
        return out

    def _load_strings(self, rels):
        self.sst = []
        path = next((p for p, t in rels.values() if t.endswith("/sharedStrings")), None)
        if not path or path not in self.names:
            return
        for si in self._xml(path).iter(q("si")):
            self.sst.append(_rich_text(si))

    def _load_styles(self, rels):
        self.xfs, self.fonts, self.fills, self.borders, self.numfmts = [], [], [], [], dict(BUILTIN)
        self.theme = {}
        theme = next((p for p, t in rels.values() if t.endswith("/theme")), None)
        if theme and theme in self.names:
            sch = self._xml(theme).find(f".//{{{A_NS}}}clrScheme")
            if sch is not None:
                for el in sch:
                    name = etree.QName(el).localname
                    srgb, sys_ = el.find(f"{{{A_NS}}}srgbClr"), el.find(f"{{{A_NS}}}sysClr")
                    val = srgb.get("val") if srgb is not None else (sys_.get("lastClr") if sys_ is not None else None)
                    if val:
                        self.theme[name] = val.upper()
        path = next((p for p, t in rels.values() if t.endswith("/styles")), None)
        if not path or path not in self.names:
            return
        st = self._xml(path)
        for nf in st.iter(q("numFmt")):
            try:
                self.numfmts[int(nf.get("numFmtId"))] = nf.get("formatCode") or "General"
            except (TypeError, ValueError):
                pass
        fonts = st.find(q("fonts"))
        for f in (fonts if fonts is not None else ()):
            if f.tag != q("font"):
                continue
            d = {}
            for k in ("b", "i", "strike"):
                el = f.find(q(k))
                if el is not None and el.get("val", "1") not in ("0", "false"):
                    d[k] = True
            u = f.find(q("u"))
            if u is not None and u.get("val", "single") != "none":
                d["u"] = True
            sz = f.find(q("sz"))
            if sz is not None:
                try:
                    d["sz"] = float(sz.get("val"))
                except (TypeError, ValueError):
                    pass
            col = self._color(f.find(q("color")))
            if col:
                d["color"] = col
            self.fonts.append(d)
        fills = st.find(q("fills"))
        for f in (fills if fills is not None else ()):
            pf = f.find(q("patternFill"))
            col = None
            if pf is not None and pf.get("patternType") not in (None, "none"):
                col = self._color(pf.find(q("fgColor"))) or ("000000" if pf.get("patternType") == "solid" and pf.find(q("fgColor")) is None else None)
            self.fills.append(col)
        borders = st.find(q("borders"))
        for b in (borders if borders is not None else ()):
            d = {}
            for side in ("left", "right", "top", "bottom"):
                el = b.find(q(side))
                if el is not None and el.get("style"):
                    d[side] = (el.get("style"), self._color(el.find(q("color"))) or "000000")
            self.borders.append(d)
        xfs = st.find(q("cellXfs"))
        for x in (xfs if xfs is not None else ()):
            al = x.find(q("alignment"))
            self.xfs.append({"numFmtId": int(x.get("numFmtId") or 0), "fontId": int(x.get("fontId") or 0), "fillId": int(x.get("fillId") or 0),
                             "borderId": int(x.get("borderId") or 0), "align": dict(al.attrib) if al is not None else {}})

    def _color(self, el):
        if el is None:
            return None
        if el.get("rgb"):
            v = el.get("rgb").upper()
            return v[-6:] if len(v) >= 6 else None
        tint = float(el.get("tint") or 0)
        if el.get("theme") is not None:
            try:
                name = THEME_ORDER[int(el.get("theme"))]
            except (ValueError, IndexError):
                return None
            base = self.theme.get(name)
            return _tint(base, tint) if base else None
        if el.get("indexed") is not None:
            try:
                i = int(el.get("indexed"))
            except ValueError:
                return None
            return INDEXED[i] if i < len(INDEXED) else None
        return None

    def numfmt(self, s: int) -> str:
        xf = self.xfs[s] if 0 <= s < len(self.xfs) else None
        return self.numfmts.get(xf["numFmtId"], "General") if xf else "General"

    def css(self, s: int) -> dict:
        """칸 서식 번호 → 화면 스타일(필요한 것만)."""
        if not (0 <= s < len(self.xfs)):
            return {}
        xf, out = self.xfs[s], {}
        f = self.fonts[xf["fontId"]] if xf["fontId"] < len(self.fonts) else {}
        if f.get("b"):
            out["fontWeight"] = "bold"
        if f.get("i"):
            out["fontStyle"] = "italic"
        deco = " ".join(x for x, k in (("underline", "u"), ("line-through", "strike")) if f.get(k))
        if deco:
            out["textDecoration"] = deco
        if f.get("sz"):
            out["fontSize"] = f"{f['sz']}pt"
        if f.get("color") and f["color"] != "000000":
            out["color"] = "#" + f["color"]
        fill = self.fills[xf["fillId"]] if xf["fillId"] < len(self.fills) else None
        if fill:
            out["background"] = "#" + fill
        al = xf["align"]
        h = al.get("horizontal")
        if h in ("left", "center", "right", "justify"):
            out["textAlign"] = h
        elif h == "centerContinuous":
            out["textAlign"] = "center"
        v = al.get("vertical")
        out["verticalAlign"] = {"top": "top", "center": "middle", "bottom": "bottom"}.get(v, "bottom")
        if al.get("wrapText") in ("1", "true"):
            out["whiteSpace"] = "pre-wrap"
        if al.get("indent"):
            out["paddingLeft"] = f"{int(al['indent']) * 9 + 3}px"
        b = self.borders[xf["borderId"]] if xf["borderId"] < len(self.borders) else {}
        for side, (style, col) in b.items():
            w = "2px" if style in ("medium", "thick", "double", "mediumDashed", "mediumDashDot", "mediumDashDotDot") else "1px"
            line = "dashed" if "ash" in style else "dotted" if style in ("dotted", "hair") else "double" if style == "double" else "solid"
            out["border" + side.capitalize()] = f"{'3px' if style == 'double' else w} {line} #{col}"
        return out

    # -- 시트 --
    def sheet(self, i: int):
        if not (0 <= i < len(self.sheets)):
            raise SheetError("그런 시트가 없습니다")
        return self._xml(self.sheets[i]["path"])

    def _data(self, i):
        sd = self.sheet(i).find(q("sheetData"))
        if sd is None:
            raise SheetError("시트에 칸 자료(sheetData)가 없습니다")
        return sd

    def cell_value(self, c):
        """→ (보이는 글, 고칠 글, 종류 s|n|f|b|e|d)."""
        t, s = c.get("t"), int(c.get("s") or 0)
        f, v = c.find(q("f")), c.find(q("v"))
        vt = v.text if v is not None and v.text is not None else None
        if t == "inlineStr":
            is_ = c.find(q("is"))
            text = _rich_text(is_) if is_ is not None else ""
            shown, edit, kind = text, text, "s"
        elif t == "s":
            try:
                text = self.sst[int(vt)]
            except (TypeError, ValueError, IndexError):
                text = ""
            shown, edit, kind = text, text, "s"
        elif t == "str":
            shown, edit, kind = vt or "", vt or "", "s"
        elif t == "b":
            shown = edit = "TRUE" if vt == "1" else "FALSE"
            kind = "b"
        elif t == "e":
            shown = edit = vt or ""
            kind = "e"
        elif vt is None:
            shown, edit, kind = "", "", "s"
        else:
            try:
                num = float(vt)
            except ValueError:
                shown, edit, kind = vt, vt, "s"
            else:
                code = self.numfmt(s)
                shown = format_number(num, code, self.date1904)
                kind = "d" if _fmt_kind(code) in ("date", "time", "datetime") else "n"
                edit = shown if kind == "d" else _general(num)
        if f is not None and (f.text or f.get("t") == "shared"):
            if f.text:
                edit = "=" + f.text
            kind = "f"
        return shown, edit, kind

    def view(self, i: int, max_rows=2000, max_cols=200) -> dict:
        ws = self.sheet(i)
        sd = self._data(i)
        fmt = ws.find(q("sheetFormatPr"))
        def_h = float(fmt.get("defaultRowHeight") or 15) if fmt is not None else 15.0
        if fmt is not None and fmt.get("defaultColWidth"):
            def_w = float(fmt.get("defaultColWidth"))
        else:
            def_w = (float(fmt.get("baseColWidth")) if fmt is not None and fmt.get("baseColWidth") else 8) + 0.43   # 엑셀 기본(8 + 여백)
        cells, used_r, used_c, row_h, hidden_r = [], 0, 0, {}, []
        styles, smap = [], {}
        stale = self.edited

        def sid(s):
            if s not in smap:
                smap[s] = len(styles)
                styles.append(self.css(s))
            return smap[s]
        for row in sd.iter(q("row")):
            r = int(row.get("r") or 0)
            if r <= 0:
                continue
            if row.get("hidden") in ("1", "true"):
                hidden_r.append(r)
            if row.get("ht") and row.get("customHeight") in ("1", "true"):
                row_h[r] = round(float(row.get("ht")) * 4 / 3)
            if r > max_rows:
                used_r = max(used_r, r)
                continue
            for c in row.iter(q("c")):
                try:
                    rr, cc = parse_cell(c.get("r"))
                except ValueError:
                    continue
                shown, edit, kind = self.cell_value(c)
                s = int(c.get("s") or 0)
                if not shown and not edit and s == 0:
                    continue
                used_r, used_c = max(used_r, rr), max(used_c, cc)
                if cc > max_cols:
                    continue
                item = [rr, cc, shown, edit, sid(s), kind]
                if kind == "f" and stale:
                    item.append(1)
                cells.append(item)
        merges = []
        mc = ws.find(q("mergeCells"))
        for m in (mc if mc is not None else ()):
            try:
                r0, c0, r1, c1 = parse_range(m.get("ref"))
            except ValueError:
                continue
            used_r, used_c = max(used_r, r1), max(used_c, c1)
            merges.append([r0, c0, r1, c1])
        n_rows, n_cols = min(max(used_r, 1), max_rows), min(max(used_c, 1), max_cols)
        col_w, hidden_c = [round(def_w * 7 + 5)] * (n_cols + 1), []
        cols = ws.find(q("cols"))
        for col in (cols if cols is not None else ()):
            try:
                a, b = int(col.get("min")), int(col.get("max"))
            except (TypeError, ValueError):
                continue
            for k in range(a, min(b, n_cols) + 1):
                if col.get("width"):
                    col_w[k] = round(float(col.get("width")) * 7 + 5)
                if col.get("hidden") in ("1", "true"):
                    hidden_c.append(k)
        frozen = {"rows": 0, "cols": 0}
        pane = ws.find(f"{q('sheetViews')}/{q('sheetView')}/{q('pane')}")
        if pane is not None and pane.get("state") in ("frozen", "frozenSplit"):
            frozen = {"rows": int(float(pane.get("ySplit") or 0)), "cols": int(float(pane.get("xSplit") or 0))}
        return {"index": i, "name": self.sheets[i]["name"], "rows": n_rows, "cols": n_cols, "colW": col_w[1:], "rowH": row_h,
                "defaultRowH": round(def_h * 4 / 3), "hiddenRows": hidden_r, "hiddenCols": hidden_c, "merges": merges, "cells": cells,
                "styles": styles, "frozen": frozen, "truncated": used_r > max_rows or used_c > max_cols, "used": [used_r, used_c]}

    # -- 칸 고치기 --
    def _row_el(self, sd, r, create=True):
        for row in sd.iter(q("row")):
            rr = int(row.get("r") or 0)
            if rr == r:
                return row
            if rr > r:
                if not create:
                    return None
                new = etree.Element(q("row"), r=str(r))
                row.addprevious(new)
                return new
        if not create:
            return None
        new = etree.SubElement(sd, q("row"), r=str(r))
        return new

    def _cell_el(self, row, r, c, create=True):
        for el in row.iter(q("c")):
            try:
                cc = parse_cell(el.get("r"))[1]
            except ValueError:
                continue
            if cc == c:
                return el
            if cc > c:
                if not create:
                    return None
                new = etree.Element(q("c"), r=cell_ref(r, c))
                s = row.get("s") if row.get("customFormat") in ("1", "true") else None
                if s:
                    new.set("s", s)
                el.addprevious(new)
                return new
        if not create:
            return None
        new = etree.SubElement(row, q("c"), r=cell_ref(r, c))
        s = row.get("s") if row.get("customFormat") in ("1", "true") else None
        if s:
            new.set("s", s)
        return new

    def _merge_at(self, ws, r, c):
        mc = ws.find(q("mergeCells"))
        for m in (mc if mc is not None else ()):
            try:
                r0, c0, r1, c1 = parse_range(m.get("ref"))
            except ValueError:
                continue
            if r0 <= r <= r1 and c0 <= c <= c1:
                return r0, c0
        return None

    def set_cells(self, i: int, cells: list) -> list:
        """[(r, c, 글)] → 고친 칸의 보기 [[r, c, 보이는 글, 고칠 글, 화면 스타일, 종류(, 1 = 다시 계산 전)]]. 한 칸이라도 안 되면 아무것도 안 바꾼다."""
        ws = self.sheet(i)
        for r, c, _ in cells:
            if not (1 <= r <= MAX_ROW and 1 <= c <= MAX_COL):
                raise SheetError("시트 밖의 칸입니다")
            at = self._merge_at(ws, r, c)
            if at and at != (r, c):
                raise SheetError(f"{cell_ref(r, c)} 는 병합된 칸입니다 — 왼쪽 위 칸({cell_ref(*at)})을 고치세요")
        self._unshare(i)
        sd = self._data(i)
        for r, c, _ in cells:
            row = self._row_el(sd, r, create=False)
            el = self._cell_el(row, r, c, create=False) if row is not None else None
            f = el.find(q("f")) if el is not None else None
            if f is not None and f.get("t") == "array":
                raise SheetError(f"{cell_ref(r, c)} 는 배열 수식 칸입니다 — 엑셀에서 고치세요")
        out = []
        for r, c, text in cells:
            row = self._row_el(sd, r)
            el = self._cell_el(row, r, c)
            self._write(el, "" if text is None else str(text))
            if el.get("s") in (None, "0") and len(el) == 0 and el.get("t") is None:
                row.remove(el)
            shown, edit, kind = self.cell_value(el) if el.getparent() is not None else ("", "", "s")
            item = [r, c, shown, edit, self.css(int(el.get("s") or 0)), kind]
            if kind == "f":
                item.append(1)
            out.append(item)
        self._touch(self.sheets[i]["path"])
        self._fix_dimension(i)
        return out

    def _write(self, el, text: str):
        for k in ("f", "v", "is"):
            for x in el.findall(q(k)):
                el.remove(x)
        if "t" in el.attrib:
            del el.attrib["t"]
        if text == "":
            return
        s = int(el.get("s") or 0)
        kind = _fmt_kind(self.numfmt(s))
        if text.startswith("=") and len(text) > 1:
            etree.SubElement(el, q("f")).text = text[1:]
            return
        if text.startswith("'"):
            return self._inline(el, text[1:])
        if kind != "text":
            m = DATE.match(text.strip())
            if m and kind in ("date", "datetime", "time"):
                try:
                    d = dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0))
                except ValueError:
                    d = None
                if d is not None:
                    etree.SubElement(el, q("v")).text = _general(dt_to_serial(d, self.date1904))
                    return
            num = _as_number(text.strip())
            if num is not None:
                etree.SubElement(el, q("v")).text = _general(num) if abs(num) < 1e15 else repr(num)
                return
        self._inline(el, text)

    @staticmethod
    def _inline(el, text):
        el.set("t", "inlineStr")
        t = etree.SubElement(etree.SubElement(el, q("is")), q("t"))
        t.text = text
        if text != text.strip() or "\n" in text:
            t.set(f"{{{XML_NS}}}space", "preserve")

    def _unshare(self, i):
        """공유 수식을 칸마다의 수식으로 푼다(② §2) — 그 시트를 처음 고칠 때 한 번."""
        path = self.sheets[i]["path"]
        if path in self.unshared:
            return
        self.unshared.add(path)
        masters, deps = {}, []
        for c in self._data(i).iter(q("c")):
            f = c.find(q("f"))
            if f is None or f.get("t") != "shared":
                continue
            if f.text:
                masters[f.get("si")] = (parse_cell(c.get("r")), f.text)
            deps.append((c, f))
        if not deps:
            return
        for c, f in deps:
            got = masters.get(f.get("si"))
            if got is None:
                continue
            (r0, c0), text = got
            r, cc = parse_cell(c.get("r"))
            f.text = move_formula(text, r - r0, cc - c0) if (r, cc) != (r0, c0) else text
            for k in ("t", "ref", "si"):
                f.attrib.pop(k, None)
        self._touch(path)

    def _fix_dimension(self, i):
        ws = self.sheet(i)
        dim = ws.find(q("dimension"))
        if dim is None:
            return
        r1 = c1 = 0
        r0 = c0 = None
        for c in self._data(i).iter(q("c")):
            try:
                r, cc = parse_cell(c.get("r"))
            except ValueError:
                continue
            r0, c0 = (r if r0 is None else min(r0, r)), (cc if c0 is None else min(c0, cc))
            r1, c1 = max(r1, r), max(c1, cc)
        dim.set("ref", "A1" if r0 is None else range_ref(r0, c0, r1, c1))

    # -- 행 넣기 · 지우기 --
    def insert_rows(self, i: int, at: int, n: int = 1):
        """at 행 위에 n 행 — 새 행은 바로 위 행(맨 위면 그 아래 행)의 칸 서식 · 높이를 받는다(② §3)."""
        if not (1 <= at <= MAX_ROW) or not (1 <= n <= 1000):
            raise SheetError("행 넣기의 자리 · 수가 맞지 않습니다")
        sd = self._data(i)
        last = max((int(r.get("r") or 0) for r in sd.iter(q("row"))), default=0)
        if last + n > MAX_ROW:
            raise SheetError("시트의 마지막 행(1,048,576)을 넘습니다")
        self._unshare(i)
        model = self._row_el(sd, at - 1, create=False) if at > 1 else None
        if model is None or not len(model):
            below = self._row_el(sd, at, create=False)
            model = below if below is not None else model
        self._shift(i, Shift(insert_at=at, n=n))
        for k in range(n):
            r = at + k
            row = self._row_el(sd, r)
            if model is not None:
                for a in ("s", "customFormat", "ht", "customHeight", "spans"):
                    if model.get(a) is not None:
                        row.set(a, model.get(a))
                for mc in model.iter(q("c")):
                    if mc.get("s") not in (None, "0"):
                        etree.SubElement(row, q("c"), r=cell_ref(r, parse_cell(mc.get("r"))[1]), s=mc.get("s"))
        self._fix_dimension(i)

    def delete_rows(self, i: int, r0: int, r1: int):
        if not (1 <= r0 <= r1 <= MAX_ROW):
            raise SheetError("지울 행이 맞지 않습니다")
        for path in self._tables(i):
            t = self._xml(path)
            tr0, _, tr1, _ = parse_range(t.get("ref"))
            if r0 <= tr0 <= r1:
                raise SheetError(f"표 「{t.get('displayName') or t.get('name')}」 의 머리 행은 지우지 않습니다 — 엑셀에서 표를 고치세요")
        self._unshare(i)
        sd = self._data(i)
        for row in list(sd.iter(q("row"))):
            if r0 <= int(row.get("r") or 0) <= r1:
                sd.remove(row)
        self._shift(i, Shift(d0=r0, d1=r1))
        self._fix_dimension(i)

    def _tables(self, i):
        rels = self._rels(self.sheets[i]["path"])
        return [p for p, t in rels.values() if t == REL_TABLE and p in self.names]

    def _shift(self, i: int, sh: Shift):
        """행을 옮길 때 그 시트를 가리키는 것 모두(② §3 「행 넣기 · 지우기」)."""
        path, name = self.sheets[i]["path"], self.sheets[i]["name"]
        for k in range(len(self.sheets)):   # 다른 시트의 공유 수식이 이 시트를 가리키면 칸마다 옮김이 달라진다 — 먼저 푼다
            self._unshare(k)
        ws = self.sheet(i)
        sd = self._data(i)
        rows = list(sd.iter(q("row")))
        for row in (reversed(rows) if sh.ins is not None else rows):
            r = int(row.get("r") or 0)
            nr = sh.row(r)
            if nr is None or nr == r:
                continue
            row.set("r", str(nr))
            for c in row.iter(q("c")):
                try:
                    c.set("r", cell_ref(nr, parse_cell(c.get("r"))[1]))
                except ValueError:
                    pass
        mc = ws.find(q("mergeCells"))
        if mc is not None:
            for m in list(mc):
                got = sh.ref(m.get("ref")) if m.get("ref") else None
                if got is None or ":" not in got:
                    mc.remove(m)
                else:
                    m.set("ref", got)
            if len(mc):
                mc.set("count", str(len(mc)))
            else:
                ws.remove(mc)
        for tag in ("conditionalFormatting", "dataValidation", "selection", "protectedRange", "ignoredError"):
            for el in list(ws.iter(q(tag))):
                got = sh.sqref(el.get("sqref"))
                if got is None:
                    if tag == "selection":
                        el.set("sqref", "A1")
                        el.set("activeCell", "A1")
                    else:
                        el.getparent().remove(el)
                    continue
                el.set("sqref", got)
                if tag == "selection" and el.get("activeCell"):
                    el.set("activeCell", sh.ref(el.get("activeCell")) or got.split()[0].split(":")[0])
        dvs = ws.find(q("dataValidations"))
        if dvs is not None:
            dvs.set("count", str(len(dvs))) if len(dvs) else ws.remove(dvs)
        for tag in ("hyperlink",):
            for el in list(ws.iter(q(tag))):
                got = sh.ref(el.get("ref")) if el.get("ref") else None
                el.set("ref", got) if got else el.getparent().remove(el)
        af = ws.find(q("autoFilter"))
        if af is not None and af.get("ref"):
            got = sh.ref(af.get("ref"))
            af.set("ref", got) if got else ws.remove(af)
        for brk in ws.iter(q("brk")):
            if brk.getparent().tag == q("rowBreaks") and brk.get("id"):
                brk.set("id", str(sh.point(int(brk.get("id")))))
        # 수식 — 모든 시트(이 시트를 가리키는 다른 시트의 수식까지) · 이름 정의 · 조건부 서식 · 유효성의 수식
        for k, sh_ in enumerate(self.sheets):
            here = sh_["path"]
            w = self.sheet(k)
            changed = False
            for f in w.iter(q("f"), q("formula"), q("formula1"), q("formula2")):
                if f.text:
                    new = shift_formula(f.text, sh_["name"], name, sh)
                    if new != f.text:
                        f.text, changed = new, True
                if f.tag == q("f") and f.get("ref") and k == i:
                    got = sh.ref(f.get("ref"))
                    if got:
                        f.set("ref", got)
                    changed = True
            if changed:
                self._touch(here)
        for dn in self.wb.iter(q("definedName")):
            if dn.text:
                new = shift_formula(dn.text, "\0", name, sh)   # 이름 정의는 시트 이름이 늘 붙는다(here 없음)
                if new != dn.text:
                    dn.text = new
                    self._touch(self.wb_path)
        # 표 · 메모 · 그림의 자리
        for tp in self._tables(i):
            t = self._xml(tp)
            got = sh.ref(t.get("ref"))
            if got:
                t.set("ref", got)
            af = t.find(q("autoFilter"))
            if af is not None and af.get("ref"):
                g2 = sh.ref(af.get("ref"))
                af.set("ref", g2) if g2 else t.remove(af)
            self._touch(tp)
        rels = self._rels(path)
        for p, typ in rels.values():
            if p not in self.names:
                continue
            if typ == REL_COMMENTS:
                root = self._xml(p)
                for cm in list(root.iter(q("comment"))):
                    got = sh.ref(cm.get("ref")) if cm.get("ref") else None
                    cm.set("ref", got) if got else cm.getparent().remove(cm)
                self._touch(p)
            elif typ == REL_DRAW:
                root = self._xml(p)
                for tag in ("from", "to"):
                    for pt in root.iter(f"{{{XDR}}}{tag}"):
                        row = pt.find(f"{{{XDR}}}row")
                        if row is not None and row.text and row.text.strip().isdigit():
                            row.text = str(sh.point(int(row.text) + 1) - 1)
                self._touch(p)
        self._touch(path)

    # -- 저장 --
    def save(self) -> bytes:
        if self.edited:
            self._drop_calc_chain()
            self._full_calc()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for info in self.zip.infolist():
                if info.filename in self.dropped:
                    continue
                if info.filename in self.dirty:
                    data = etree.tostring(self.parts[info.filename], xml_declaration=True, encoding="UTF-8", standalone=True)
                else:
                    data = self.zip.read(info.filename)
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type, zi.external_attr = info.compress_type, info.external_attr
                out.writestr(zi, data)
        return buf.getvalue()

    def _drop_calc_chain(self):
        rels_name = self._rels_name(self.wb_path)
        if rels_name in self.names:
            root = self._xml(rels_name)
            base = posixpath.dirname(self.wb_path)
            for r in list(root):
                if r.get("Type") == REL_CALC:
                    t = r.get("Target", "")
                    self.dropped.add(t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join(base, t)))
                    root.remove(r)
                    self.dirty.add(rels_name)
        if self.dropped and "[Content_Types].xml" in self.names:
            ct = self._xml("[Content_Types].xml")
            for o in list(ct):
                if (o.get("PartName") or "").lstrip("/") in self.dropped:
                    ct.remove(o)
                    self.dirty.add("[Content_Types].xml")

    def _full_calc(self):
        cp = self.wb.find(q("calcPr"))
        if cp is None:
            cp = etree.Element(q("calcPr"), calcId="191029")
            after = self.wb.find(q("definedNames"))
            if after is None:
                after = self.wb.find(q("sheets"))
            after.addnext(cp)
        if cp.get("fullCalcOnLoad") != "1":
            cp.set("fullCalcOnLoad", "1")
            self.dirty.add(self.wb_path)


def _rich_text(el) -> str:
    """si · is → 글(발음 rPh 는 뺌)."""
    out = []
    for ch in el:
        if ch.tag == q("t"):
            out.append(ch.text or "")
        elif ch.tag == q("r"):
            t = ch.find(q("t"))
            out.append(t.text or "" if t is not None else "")
    return "".join(out)


def _as_number(text: str):
    """숫자로 넣을 글이면 그 값(② §3 — 0 으로 시작 · 정수부가 긴 것은 글)."""
    s = text
    pct = s.endswith("%")
    if pct:
        s = s[:-1].strip()
    if NUM_COMMA.match(s):
        s = s.replace(",", "")
    elif not NUM.match(s):
        return None
    body = s.lstrip("+-")
    intpart = body.split(".")[0].split("e")[0].split("E")[0]
    if len(intpart) > 1 and intpart.startswith("0"):
        return None
    if len(intpart) > INT_DIGITS:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v / 100 if pct else v
