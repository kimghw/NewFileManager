"""DOCX format adapter (spec §2): block tree + edits on the raw OOXML zip.

Only the XML parts that changed are re-serialized (with their original XML declaration); every other zip
member is copied with its original bytes and ZipInfo. An unedited document saves to its original bytes."""
import copy
import hashlib
import posixpath
import re
import secrets
import threading
import zipfile
from io import BytesIO

from docx.image.exceptions import UnrecognizedImageError
from docx.image.image import Image  # python-docx's header parser, used only for pixel sizes
from lxml import etree

from app import block_ids
from app import docx_layout
from app import table_grid as grid
from app import zip_guard
from app.docx_struct import DocxStructMixin  # docx_struct 는 이 모듈을 쓸 때 읽는다(서로 import — 함수 안에서만 이 모듈 이름을 씀)
from app.textdiff import redistribute

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W, WP, A, R = (f"{{{ns}}}" for ns in (W_NS, WP_NS, A_NS, R_NS))
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
WP14 = "{http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_TLS = threading.local()


def _parser():
    """스레드마다 lxml 파서 하나 — 파서 객체를 스레드끼리 나눠 쓰면 병렬 검증 단계가 같은 바이트를 동시에 열 때 「Namespace prefix … not defined」
    같은 거짓 구문 오류가 난다(NFM 2026-11-08, AIP 서식 1.8 MB 가져오기 검증에서 재현 — lxml FAQ: 파서는 스레드마다)."""
    p = getattr(_TLS, "parser", None)
    if p is None:
        p = _TLS.parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)
    return p


_CHAR_REFS = ((b"&#10;", b"&#xA;"), (b"&#9;", b"&#x9;"), (b"&#13;", b"&#xD;"))  # lxml 이 쓰는 10진 ↔ Word 가 쓰는 16진
_DECL = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
_EMU_PER_MM = 36000
_HEADING = re.compile(r"^(?:heading|제목)\s*(\d)$", re.I)
_SEQ_KIND = {"그림": "figure", "figure": "figure", "표": "table", "table": "table", "수식": "equation", "equation": "equation"}
_SEQ_FMT = {"ROMAN": "upperRoman", "roman": "lowerRoman", "ALPHABETIC": "upperLetter", "alphabetic": "lowerLetter"}
_PUA_BULLET = {0xB7: "•", 0x9F: "•", 0xA7: "▪", 0x6C: "●", 0x6E: "■", 0xD8: "➢", 0xFC: "✓"}  # Symbol/Wingdings code points
_TEXT_TAGS = {W + "t", W + "tab", W + "br", W + "noBreakHyphen"}
_NOT_RUN_HOLDERS = {W + "pPr", W + "del", W + "moveFrom", W + "sdtPr", W + "sdtEndPr"}
_BEFORE_NUMPR = {W + t for t in ("pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl")}
_REVISIONS = ("sectPr", "pPrChange", "rPrChange", "ins", "del", "moveFrom", "moveTo")
# Things that only make sense inside their source document; removed from copies. Bookmarks/comments/notes point at
# ids or parts we don't copy, sectPr would add a section break, w:object is OLE (spec: not copied).
_COPY_DROP = tuple(W + t for t in ("sectPr", "bookmarkStart", "bookmarkEnd", "commentRangeStart", "commentRangeEnd",
                                   "commentReference", "footnoteReference", "endnoteReference", "object", "dataBinding"))
_DROP_UNITS = {MC + "AlternateContent", W + "drawing", W + "pict", W + "object"}
_UNIQUE_ATTRS = (W14 + "paraId", W14 + "textId", WP14 + "anchorId", WP14 + "editId")
MARK_RE = re.compile(r"^\s*\d{1,3}(?:-\d{1,3})*\)\s*$")  # superscript footnote mark 「15)」·「15-1)」 (= hwpx_doc.MARK_RE)
_INLINE = (
    f'<w:drawing xmlns:w="{W_NS}" xmlns:wp="{WP_NS}" xmlns:a="{A_NS}" xmlns:pic="{PIC_NS}" xmlns:r="{R_NS}">'
    '<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
    '<wp:docPr id="{id}" name="Picture {id}"/>'
    '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
    '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
    '<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
    '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
    '</a:graphicData></a:graphic></wp:inline></w:drawing>')


def _dark(fill):
    """칸 음영 #RRGGBB 가 어두운지 — Word 자동 글자색이 흰색이 되는 음영. 밝기 (76R + 151G + 29B) >> 8 ≤ 62(LibreOffice Color::IsDark 가 MS Office 와
    맞춘 문턱 — 빨강 FF0000 은 75 라 검은 글자 그대로, HAZID 위험도 칸 Word 16 PDF 와 같음)."""
    if not fill or len(fill) != 7:
        return False
    r, g, b = (int(fill[i:i + 2], 16) for i in (1, 3, 5))
    return (76 * r + 151 * g + 29 * b) >> 8 <= 62


def _val(parent, tag):
    e = parent.find(tag) if parent is not None else None
    return None if e is None else e.get(W + "val")


def _on(parent, tag):
    """OOXML on/off property: True/False, None when absent."""
    e = parent.find(tag) if parent is not None else None
    return None if e is None else e.get(W + "val", "true") not in ("0", "false", "off")


def _kids(el, tags):
    """Children with one of `tags`, looking through w:sdt / w:customXml wrappers."""
    for c in el:
        if c.tag in tags:
            yield c
        elif c.tag == W + "sdt":
            content = c.find(W + "sdtContent")
            if content is not None:
                yield from _kids(content, tags)
        elif c.tag == W + "customXml":
            yield from _kids(c, tags)


def _runs(el):
    """Runs of a paragraph in order, through hyperlink/ins/smartTag/fldSimple/sdt; deleted runs skipped."""
    for c in el:
        if c.tag == W + "r":
            yield c
        elif isinstance(c.tag, str) and c.tag.startswith(W) and c.tag not in _NOT_RUN_HOLDERS:
            yield from _runs(c)


def _is_text(c):
    return c.tag in _TEXT_TAGS and not (c.tag == W + "br" and c.get(W + "type") not in (None, "textWrapping"))


def _has_text(r):
    return any(_is_text(c) for c in r)


def _run_text(r):
    out = []
    for c in r:
        if _is_text(c):
            out.append({W + "t": c.text or "", W + "tab": "\t", W + "br": "\u2028"}.get(c.tag, "-"))
    return "".join(out)


def _text(p):
    return "".join(_run_text(r) for r in _runs(p))


def _write_run(r, text):
    """Replace the run's text children with `text` (\\t -> w:tab, U+2028 -> w:br), keeping other children in place."""
    kids = [c for c in r if _is_text(c)]
    pos = r.index(kids[0]) if kids else len(r)
    for c in kids:
        r.remove(c)
    for i, tok in enumerate(t for t in re.split("(\t|\u2028)", text) if t):
        if tok in ("\t", "\u2028"):
            e = etree.Element(W + ("tab" if tok == "\t" else "br"))
        else:
            e = etree.Element(W + "t")
            e.text = tok
            if tok != tok.strip():
                e.set(XML_SPACE, "preserve")
        r.insert(pos + i, e)


def _strip(el, *tags):
    for e in list(el.iter(*[W + t for t in tags])):
        if e is not el:
            e.getparent().remove(e)
    return el


def _unit(e):
    """Outermost drawing/shape wrapper (or e itself) - what has to go when e goes."""
    units = [a for a in (e, *e.iterancestors()) if a.tag in _DROP_UNITS]
    return units[-1] if units else e


def _grid_cells(rows):
    """Cells of a table's w:tr list -> ([[tc, row, col, gridSpan, rowSpan]] one per cell start in document order,
    grid width); a w:vMerge continuation adds a row to the cell above it."""
    cells, above, width = [], {}, 0  # above: grid col -> cell whose vMerge may continue into this row
    for ri, tr in enumerate(rows):
        col, below = int(_val(tr.find(W + "trPr"), W + "gridBefore") or 0), {}
        for tc in _kids(tr, (W + "tc",)):
            pr = tc.find(W + "tcPr")
            span = int(_val(pr, W + "gridSpan") or 1)
            vm = pr.find(W + "vMerge") if pr is not None else None
            if vm is not None and vm.get(W + "val") != "restart" and col in above:
                cell = above[col]
                cell[4] += 1
            else:
                cell = [tc, ri, col, span, 1]
                cells.append(cell)
            if vm is not None:
                below[col] = cell
            col += span
        above, width = below, max(width, col)
    return cells, width


def _vmerge(tc, restart):
    """Make a w:tc start (restart) or continue a vertical merge; a continuation keeps only an empty paragraph."""
    pr = tc.find(W + "tcPr")
    if pr is None:
        pr = etree.Element(W + "tcPr")
        tc.insert(0, pr)
    vm = pr.find(W + "vMerge")
    if vm is None:  # schema order: cnfStyle, tcW, gridSpan, hMerge, vMerge, ...
        vm = etree.Element(W + "vMerge")
        before = [c for c in pr if c.tag in (W + "cnfStyle", W + "tcW", W + "gridSpan", W + "hMerge")]
        if before:
            before[-1].addnext(vm)
        else:
            pr.insert(0, vm)
    if restart:
        vm.set(W + "val", "restart")
        return
    vm.attrib.pop(W + "val", None)
    for c in [c for c in tc if c is not pr]:
        tc.remove(c)
    etree.SubElement(tc, W + "p")


def _drop_ids(el):
    for e in el.iter(etree.Element):
        for a in _UNIQUE_ATTRS:
            e.attrib.pop(a, None)


_TCBORDERS = [W + t for t in ("top", "start", "left", "bottom", "end", "right", "insideH", "insideV", "tl2br", "tr2bl")]
_EDGES = (W + "bottom", W + "end", W + "right")


def _tc_prop(pr, tag, val):
    """tcPr child `tag` with w:val=val ('' = no w:val, as a vMerge continuation; None = no such child)."""
    e = pr.find(W + tag)
    if val is None:
        if e is not None:
            pr.remove(e)
        return
    if e is None:
        e = docx_format._place(pr, etree.Element(W + tag), docx_format._TCPR)
    if val:
        e.set(W + "val", val)
    else:
        e.attrib.pop(W + "val", None)


def _merge_borders(tc, other):
    """tc's own bottom and right lines become other's (a merged cell's edges are its bottom-right cell's, 한글처럼)."""
    take = [c for c in other.iterfind(f"{W}tcPr/{W}tcBorders/*") if c.tag in _EDGES]
    pr = tc.find(W + "tcPr")
    dst = pr.find(W + "tcBorders") if pr is not None else None
    if dst is None and not take:
        return
    if pr is None:
        pr = etree.Element(W + "tcPr")
        tc.insert(0, pr)
    if dst is None:
        dst = docx_format._place(pr, etree.Element(W + "tcBorders"), docx_format._TCPR)
    for c in [c for c in dst if c.tag in _EDGES]:
        dst.remove(c)
    for c in take:
        docx_format._place(dst, copy.deepcopy(c), _TCBORDERS)
    if not len(dst):
        pr.remove(dst)


_TRPR_ORDER = ("cnfStyle divId gridBefore gridAfter wBefore wAfter cantSplit trHeight tblHeader tblCellSpacing jc hidden ins del "
               "trPrChange")  # w:trPr child order (schema) — set_line_sizes puts w:trHeight at its place (docx_format._seq)


def _row_like(tr):
    """Empty w:tr with tr's row properties (tblPrEx, trPr) — a new grid row."""
    new = etree.Element(tr.tag, {k: v for k, v in tr.attrib.items() if k not in _UNIQUE_ATTRS})
    for c in tr:
        if c.tag in (W + "tblPrEx", W + "trPr"):
            new.append(copy.deepcopy(c))
    return new


def _seq_kind(instr):
    parts = instr.split()
    return _SEQ_KIND.get(parts[1].lower()) if len(parts) > 1 and parts[0].upper() == "SEQ" else None


def _roman(n):
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                 (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + s, n - v
    return out


def _fmt_num(n, fmt):
    """Number text for a w:numFmt value, None when the format isn't supported."""
    if fmt == "decimal":
        return str(n)
    if fmt == "decimalZero":
        return f"{n:02d}"
    if fmt in ("upperRoman", "lowerRoman"):
        return _roman(n) if fmt == "upperRoman" else _roman(n).lower()
    if fmt in ("upperLetter", "lowerLetter") and n > 0:
        s = chr(65 + (n - 1) % 26) * ((n - 1) // 26 + 1)
        return s if fmt == "upperLetter" else s.lower()
    if fmt in ("ganada", "chosung") and n > 0:
        return ("가나다라마바사아자차카타파하" if fmt == "ganada" else "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ")[(n - 1) % 14]
    if fmt == "decimalEnclosedCircle" and 1 <= n <= 20:
        return chr(0x245F + n)
    if fmt == "none":
        return ""
    return None


def _label(text, counters, levels):
    """Expand %1..%9 in a w:lvlText; None if a referenced level has an unsupported format."""
    def one(m):
        k = int(m[1]) - 1
        fmt, _, start = levels.get(k, ("decimal", "", 1))
        v = _fmt_num(counters.get(k, start), fmt)
        if v is None:
            raise ValueError
        return v
    try:
        return re.sub(r"%([1-9])", one, text) or None
    except ValueError:
        return None


def _bullet(text):
    return "".join(_PUA_BULLET.get(ord(c) - 0xF000, c) if 0xF000 <= ord(c) < 0xF100 else c for c in text) or None


def _number_off(p):
    """Turn automatic numbering off for p: w:numPr -> numId 0."""
    ppr = p.find(W + "pPr")
    if ppr is None:
        ppr = etree.Element(W + "pPr")
        p.insert(0, ppr)
    num_pr = ppr.find(W + "numPr")
    if num_pr is None:
        num_pr = etree.Element(W + "numPr")
        ppr.insert(max([i + 1 for i, c in enumerate(ppr) if c.tag in _BEFORE_NUMPR], default=0), num_pr)
    num_pr.clear()
    etree.SubElement(num_pr, W + "numId").set(W + "val", "0")


def _add_num_def(root, el):
    """Append a w:abstractNum / w:num keeping the schema order (all abstractNums before all nums)."""
    same = root.findall(el.tag)
    first_num = root.find(W + "num")
    if same:
        same[-1].addnext(el)
    elif el.tag == W + "abstractNum" and first_num is not None:
        first_num.addprevious(el)
    else:
        root.append(el)


class DocxDoc(DocxStructMixin):  # 구조·서식 편집·글꼴 표(NFM spec_docx_웹편집 ② §2·§3 — app/docx_struct.py)
    format = "docx"

    def __init__(self, data: bytes):
        self._data = data
        self._zip = zipfile.ZipFile(BytesIO(data))
        zip_guard.check(self._zip)  # 멤버를 읽기 전에 한도(spec_왕복_어댑터 ② §1 「비신뢰 패키지 한도」)
        self._names = set(self._zip.namelist())
        self._xml, self._decl, self._blobs, self._dirty = {}, {}, {}, set()
        self._tail = {}  # 뿌리 요소 뒤 공백(줄 바꿈) — lxml tostring 이 버리므로 저장 때 되붙인다(NFM spec_docx_웹편집 ② §4 XML 재직렬화)
        self._hexref = {}  # 부분마다 16진으로 되돌릴 문자 참조 [(10진, 16진)]
        self._ids, self._rev, self._n = {}, {}, 0
        self._memo = {}  # (src doc, kind, src id) -> target id, so repeated copies share styles/lists/media
        self._starts = {}  # numId -> {ilvl: startOverride} (_levels 가 채움, _list 가 그 w:num 첫 문단에서만 씀)
        self._seq = {}  # SEQ field key element -> (field, computed number text), refreshed by blocks()
        self._media = None  # sha1 -> media part name, built on first image import
        self._doc = next(self._resolve("", r.get("Target")) for r in self._part("_rels/.rels")
                         if r.get("Type", "").endswith("/officeDocument"))
        self._dir = posixpath.dirname(self._doc)
        self._rels_name = f"{self._dir}/_rels/{posixpath.basename(self._doc)}.rels"
        rels = self._part(self._rels_name)
        self._rels = {r.get("Id"): r for r in (rels if rels is not None else [])}
        self._sub = {}  # "styles"/"numbering" -> part name
        for r in self._rels.values():
            kind = r.get("Type", "").rsplit("/", 1)[-1]
            if kind in ("styles", "numbering") and r.get("TargetMode") != "External":
                self._sub[kind] = self._resolve(self._dir, r.get("Target"))
        self._body = self._part(self._doc).find(W + "body")
        styles, numbering = self._sub_part("styles"), self._sub_part("numbering")
        self._styles = {s.get(W + "styleId"): s for s in styles.findall(W + "style")} if styles is not None else {}
        self._default_pstyle = next((k for k, s in self._styles.items() if s.get(W + "type") == "paragraph"
                                     and s.get(W + "default") in ("1", "true", "on")), None)
        self._default_bold = _on(styles.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr"), W + "b") \
            if styles is not None else None
        self._nums = {n.get(W + "numId"): n for n in numbering.findall(W + "num")} if numbering is not None else {}
        self._abstracts = {a.get(W + "abstractNumId"): a for a in numbering.findall(W + "abstractNum")} \
            if numbering is not None else {}

    # ---- package plumbing -------------------------------------------------------------------------------

    @staticmethod
    def _resolve(base_dir, target):
        return target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base_dir, target))

    def _part(self, name):
        """Parsed root of an XML member (cached), None if missing."""
        if name not in self._xml:
            if name not in self._names:
                return None
            raw = zip_guard.read_xml(self._zip, name)  # 조각 읽기 + 이름과 무관한 XML 상한 — 관계·콘텐츠 형식으로 찾은 이름을 바꾼 부분도(② §1 「비신뢰 패키지 한도」)
            m = re.match(rb"(?:\xef\xbb\xbf)?<\?xml[^>]*\?>\s*", raw)
            self._decl[name] = m.group(0) if m else b""
            self._tail[name] = re.search(rb"\s*\Z", raw).group(0)
            # Word 는 속성 값 안 줄 바꿈·탭을 16진 문자 참조(&#xA;)로, lxml 은 10진(&#10;)으로 쓴다 — 원본이 16진만 썼으면 저장 때 16진으로
            self._hexref[name] = [(d, h) for d, h in _CHAR_REFS if h in raw and d not in raw]
            self._xml[name] = etree.fromstring(raw, _parser())
        return self._xml[name]

    def _sub_part(self, kind, create=False):
        """styles.xml / numbering.xml root; with create=True adds the part, its relationship and content type."""
        if kind in self._sub:
            return self._part(self._sub[kind])
        if not create:
            return None
        name = self._sub[kind] = f"{self._dir}/{kind}.xml"
        self._xml[name], self._decl[name] = etree.Element(W + kind, nsmap={"w": W_NS}), _DECL
        self._names.add(name)
        self._dirty.add(name)
        self._add_rel(RT + kind, f"{kind}.xml")
        ct = self._part("[Content_Types].xml")
        etree.SubElement(ct, CT + "Override", PartName="/" + name,
                         ContentType=f"application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml")
        self._dirty.add("[Content_Types].xml")
        return self._xml[name]

    def _add_rel(self, rel_type, target, external=False):
        root = self._part(self._rels_name)
        if root is None:
            root = self._xml[self._rels_name] = etree.Element(PKG_REL + "Relationships", nsmap={None: PKG_REL[1:-1]})
            self._decl[self._rels_name] = _DECL
            self._names.add(self._rels_name)
        n = 1
        while f"rId{n}" in self._rels:
            n += 1
        rel = etree.SubElement(root, PKG_REL + "Relationship", Id=f"rId{n}", Type=rel_type, Target=target)
        if external:
            rel.set("TargetMode", "External")
        self._rels[f"rId{n}"] = rel
        self._dirty.add(self._rels_name)
        return f"rId{n}"

    def _content_type(self, name):
        ct = self._part("[Content_Types].xml")
        for o in ct.iter(CT + "Override"):
            if o.get("PartName", "").lower() == "/" + name.lower():
                return o.get("ContentType")
        ext = posixpath.splitext(name)[1][1:].lower()
        return next((d.get("ContentType") for d in ct.iter(CT + "Default") if d.get("Extension", "").lower() == ext),
                    None)

    def _add_media(self, data, ext, content_type):
        """Store an image part, reusing an existing part with identical bytes; returns its zip name."""
        if self._media is None:
            self._media = {hashlib.sha1(self.media(n)).digest(): n for n in sorted(self._names)
                           if n.startswith(f"{self._dir}/media/")}
        key = hashlib.sha1(data).digest()
        if key not in self._media:
            n = 1
            while f"{self._dir}/media/image{n}.{ext}" in self._names:
                n += 1
            name = self._media[key] = f"{self._dir}/media/image{n}.{ext}"
            self._blobs[name] = data
            self._names.add(name)
            if self._content_type(name) is None:
                self._part("[Content_Types].xml").insert(0, etree.Element(CT + "Default", Extension=ext,
                                                                          ContentType=content_type))
                self._dirty.add("[Content_Types].xml")
        return self._media[key]

    def media(self, name: str) -> bytes:
        return self._blobs[name] if name in self._blobs else zip_guard.read(self._zip, name)

    def changes(self) -> dict:
        """연 바이트와 달라진 zip 멤버 {"parts": {이름: 바이트}, "new": {이름: 바이트}} — save() 가 쓸 그 바이트(작업 저장, spec_작업 ② §5)."""
        if not self._dirty:
            return {"parts": {}, "new": {}}
        self._refresh_seq()
        return {"parts": {n: self._dump(n) for n in self._dirty}, "new": dict(self._blobs)}

    def save(self) -> bytes:
        if not self._dirty:
            return self._data
        self._refresh_seq()
        out = BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for info in self._zip.infolist():  # copy: writestr mutates the ZipInfo it is given
                z.writestr(copy.copy(info), self._dump(info.filename) if info.filename in self._dirty
                           else zip_guard.read(self._zip, info))
            stamp = self._zip.getinfo(self._doc).date_time
            for name in sorted(n for n in self._dirty if n not in self._zip.NameToInfo):
                z.writestr(zipfile.ZipInfo(name, stamp), self._dump(name), zipfile.ZIP_DEFLATED)
            for name, data in self._blobs.items():
                z.writestr(zipfile.ZipInfo(name, stamp), data, zipfile.ZIP_DEFLATED)
        return out.getvalue()

    def _dump(self, name):
        body = etree.tostring(self._xml[name], encoding="UTF-8", xml_declaration=False)
        for dec, hexa in self._hexref.get(name, ()):
            body = body.replace(dec, hexa)
        return self._decl[name] + body + self._tail.get(name, b"")

    # ---- styles / numbering lookups ---------------------------------------------------------------------

    def _chain(self, sid):
        """Style elements from sid up its basedOn chain."""
        seen = set()
        while sid in self._styles and sid not in seen:
            seen.add(sid)
            yield self._styles[sid]
            sid = _val(self._styles[sid], W + "basedOn")

    def _pchain(self, p):
        return list(self._chain(_val(p.find(W + "pPr"), W + "pStyle") or self._default_pstyle))

    def _style_name(self, p):
        sid = _val(p.find(W + "pPr"), W + "pStyle")
        return _val(self._styles[sid], W + "name") if sid in self._styles else sid

    def _outline(self, p, direct=True):
        """Outline level 1..9 from pPr (unless direct=False) or the style chain (outlineLvl / 'heading N' name)."""
        v = _val(p.find(W + "pPr"), W + "outlineLvl") if direct else None
        if v is None:
            for st in self._pchain(p):
                v = _val(st.find(W + "pPr"), W + "outlineLvl")
                if v is not None:
                    break
                m = _HEADING.match(_val(st, W + "name") or "") or _HEADING.match(st.get(W + "styleId") or "")
                if m:
                    return int(m[1])
        return int(v) + 1 if v is not None and v.isdigit() and int(v) < 9 else None

    def _num_ref(self, p):
        """(numId, ilvl) from the paragraph's numPr or its style chain; None when not numbered."""
        num = lvl = None
        for ppr in [p.find(W + "pPr")] + [st.find(W + "pPr") for st in self._pchain(p)]:
            num_pr = ppr.find(W + "numPr") if ppr is not None else None
            if num_pr is not None:
                num = num if num is not None else _val(num_pr, W + "numId")
                lvl = lvl if lvl is not None else _val(num_pr, W + "ilvl")
                if num is not None:
                    break
        return (num, int(lvl or 0)) if num in self._nums else None

    def _levels(self, num_id, depth=0):
        """(counter key, {ilvl: (numFmt, lvlText, start)}) of a w:num, with lvlOverride/startOverride applied."""
        num = self._nums.get(num_id)
        absn = self._abstracts.get(_val(num, W + "abstractNumId")) if num is not None else None
        if absn is None:
            return None
        link = _val(absn, W + "numStyleLink")
        if link and depth < 3:  # list style: the levels live on the numbering the style points to
            num_pr = self._styles[link].find(f"{W}pPr/{W}numPr") if link in self._styles else None
            return self._levels(_val(num_pr, W + "numId"), depth + 1) if num_pr is not None else None
        lvls = {lv.get(W + "ilvl"): lv for lv in absn.findall(W + "lvl")}
        starts = {}
        for o in num.findall(W + "lvlOverride"):
            if o.find(W + "lvl") is not None:
                lvls[o.get(W + "ilvl")] = o.find(W + "lvl")
            if _val(o, W + "startOverride") is not None:
                starts[o.get(W + "ilvl")] = int(_val(o, W + "startOverride"))
        levels = {int(k): (_val(lv, W + "numFmt") or "decimal", _val(lv, W + "lvlText") or "",
                           starts.get(k, int(_val(lv, W + "start") or 0))) for k, lv in lvls.items() if k.isdigit()}
        # w:num instances of one abstractNum share its counters (Word continues the list); a startOverride only resets the
        # level of the first paragraph that uses that w:num (NFM 2026-11-08, Word 16 PDF: HAZID 보고서 numId 12 = abstractNum 6 +
        # startOverride 1 on every level, first used at ilvl 1 → Word prints 「5.1.」 then 「6.」 — _list applies it).
        # ponytail: lvlRestart/isLgl are ignored.
        self._starts[num_id] = starts
        return "a" + absn.get(W + "abstractNumId"), levels

    def _list(self, p, counters):
        ref = self._num_ref(p)
        lv = self._levels(ref[0]) if ref else None
        if lv is None or ref[1] not in lv[1]:
            return None
        (key, levels), ilvl = lv, ref[1]
        fmt, text, start = levels[ilvl]
        if fmt == "bullet":
            return {"kind": "bullet", "level": ilvl + 1, "label": _bullet(text)}
        c = counters.setdefault(key, {})
        seen = counters.setdefault("_used", set())  # w:num 마다 처음 쓰인 곳에서만 startOverride(그 문단 수준)
        if ref[0] not in seen:
            seen.add(ref[0])
            over = self._starts.get(ref[0], {}).get(str(ilvl))
            if over is not None:
                c[ilvl] = over - 1
                for k in [k for k in c if k > ilvl]:
                    del c[k]
        c[ilvl] = c.get(ilvl, start - 1) + 1
        for k in [k for k in c if k > ilvl]:
            del c[k]
        return {"kind": "number", "level": ilvl + 1, "label": _label(text, c, levels)}

    def _bold(self, p):
        runs = [r for r in _runs(p) if _run_text(r).strip()]
        pchain = self._pchain(p)
        return bool(runs) and all(self._run_bold(r, pchain) for r in runs)

    def _run_bold(self, r, pchain):
        """Direct w:b, else the run style chain, else the paragraph style chain, else docDefaults."""
        rpr = r.find(W + "rPr")
        chain = [rpr] + [st.find(W + "rPr") for st in [*self._chain(_val(rpr, W + "rStyle")), *pchain]]
        return next((v for v in (_on(x, W + "b") for x in chain) if v is not None), bool(self._default_bold))

    # ---- fields / images inside paragraphs --------------------------------------------------------------

    def _seq_fields(self, p):
        """run -> SEQ field {kind, instr, runs, key, el} for runs of recognised SEQ fields (complex or fldSimple)."""
        owner, stack, simple = {}, [], {}
        for r in _runs(p):
            fs = next(r.iterancestors(W + "fldSimple"), None)
            if fs is not None and _seq_kind(fs.get(W + "instr", "")):
                if fs not in simple:
                    simple[fs] = {"kind": _seq_kind(fs.get(W + "instr")), "instr": fs.get(W + "instr"), "runs": [],
                                  "key": fs, "el": fs}
                simple[fs]["runs"].append(r)
                owner[r] = simple[fs]
                continue
            ended = []
            for c in r:
                if c.tag == W + "fldChar" and c.get(W + "fldCharType") == "begin":
                    stack.append({"instr": "", "runs": [], "key": r, "el": None})
                elif c.tag == W + "fldChar" and c.get(W + "fldCharType") == "end" and stack:
                    ended.append(stack.pop())
                elif c.tag == W + "instrText" and stack:
                    stack[-1]["instr"] += c.text or ""
            for f in stack + ended:
                f["runs"].append(r)
            for f in ended:
                f["kind"] = _seq_kind(f["instr"])
                if f["kind"]:
                    for x in f["runs"]:
                        owner.setdefault(x, f)
        return owner

    def _slots(self, p):
        """redistribute() slots in order: ("run", r) per text run, ("seq", field) once per SEQ field."""
        owner, out = self._seq_fields(p), []
        for r in _runs(p):
            f = owner.get(r)
            if f is None and _has_text(r):
                out.append(("run", r))
            elif f is not None and f["runs"][0] is r:
                out.append(("seq", f))
        return out

    def _seq_value(self, f, ctx):
        """Running SEQ count per kind in document order (\\r n resets, \\c repeats, \\s n restarts per heading)."""
        instr, kind = f["instr"], f["kind"]
        n = ctx["seq"].get(kind, 0)
        m = re.search(r"\\r\s*(\d+)", instr)
        n = int(m[1]) if m else n if re.search(r"\\c\b", instr) else n + 1
        ctx["seq"][kind] = n
        m = re.search(r"\\s\s*(\d)", instr)
        if m:
            ctx["reset"][kind] = int(m[1])
        fmt = re.search(r"\\\*\s*(\w+)", instr)
        v = "" if re.search(r"\\h\b", instr) else _fmt_num(n, _SEQ_FMT.get(fmt[1] if fmt else "", "decimal")) or str(n)
        self._seq[f["key"]] = (f, v)
        return v

    def _refresh_seq(self):
        """Write the computed SEQ numbers into stale cached field results, so Word shows what blocks() showed."""
        self.blocks()
        for f, v in self._seq.values():
            runs = [r for r in f["runs"] if _has_text(r)]
            old = [_run_text(r) for r in runs]
            if runs and "".join(old) != v:
                for r, t in zip(runs, redistribute(old, v)):
                    _write_run(r, t)

    def _replace_field(self, f, text):
        """Swap a SEQ field (fldSimple, or its begin..end runs) for a plain run holding `text`."""
        fmt = next((r for r in f["runs"] if _has_text(r)), f["runs"][0]).find(W + "rPr")
        r = etree.Element(W + "r")
        if fmt is not None:
            r.append(copy.deepcopy(fmt))
        _write_run(r, text)
        doomed = [f["el"]] if f["el"] is not None else f["runs"]
        doomed[0].addprevious(r)
        for x in doomed:
            x.getparent().remove(x)

    @staticmethod
    def _drawings(p):
        return [d for r in _runs(p) for d in r.iter(W + "drawing") if d.find(f".//{A}blip") is not None]

    def _image_block(self, d):
        rel = self._rels.get(d.find(f".//{A}blip").get(R + "embed"))
        ext = d.find(f".//{WP}extent")
        mm = (lambda a: round(int(ext.get(a)) / _EMU_PER_MM, 1) if ext is not None and ext.get(a) else None)
        media = self._resolve(self._dir, rel.get("Target")) \
            if rel is not None and rel.get("TargetMode") != "External" else None
        return {"id": self._id(d, "i"), "type": "image", "media": media, "widthMm": mm("cx"), "heightMm": mm("cy")}

    # ---- blocks -----------------------------------------------------------------------------------------

    def _id(self, el, prefix=None):
        """prefix 없이 부르면 태그로(서버 구조 편집이 HwpxDoc 과 같은 모양으로 부름 — spec_docx_웹편집 ② §3)."""
        if el not in self._rev:
            prefix = prefix or {W + "p": "p", W + "tbl": "t", W + "tc": "c", W + "drawing": "i"}.get(el.tag, "x")
            self._n += 1
            self._rev[el] = f"{prefix}{self._n}"
            self._ids[self._rev[el]] = el
        return self._rev[el]

    def id_state(self) -> dict:
        """블록 id 자리표 — save() 한 바이트를 다시 열어 adopt_ids 하면 같은 id(작업 저장, spec_작업 ② §5)."""
        return block_ids.state(self._xml, self._rev, self._n)

    def adopt_ids(self, state) -> bool:
        """막 연 문서에 id_state 를 되붙인다 — 트리가 다르면 False(id 는 새로 붙음)."""
        got = block_ids.adopt(self._part, state)
        if got is None:
            return False
        self._ids, self._rev, self._n = got
        return True

    def blocks(self) -> list[dict]:
        self._seq = {}
        return docx_layout.annotate(self, self._blocks(self._body, {"num": {}, "seq": {}, "reset": {}}))

    def _blocks(self, container, ctx):
        out = []
        for el in _kids(container, (W + "p", W + "tbl")):
            out += self._para_blocks(el, ctx) if el.tag == W + "p" else [self._table_block(el, ctx)]
        return out

    def _para_blocks(self, p, ctx):
        outline, styled = self._outline(p), self._outline(p, direct=False)
        if styled is not None:  # SEQ \s n restarts at heading styles of level <= n (Word ignores direct outlineLvl)
            for kind, lvl in ctx["reset"].items():
                if styled <= lvl:
                    ctx["seq"][kind] = 0
        texts, auto, runs = [], None, []
        for kind, x in self._slots(p):
            texts.append(_run_text(x) if kind == "run" else self._seq_value(x, ctx))
            runs.append(x if kind == "run" else x["runs"][0])  # a SEQ field shows in its first run's look
            auto = auto or (x["kind"] if kind == "seq" else None)
        text = "".join(texts)
        block = {"id": self._id(p, "p"), "type": "paragraph", "text": text, "style": self._style_name(p),
                 "outlineLevel": outline, "list": self._list(p, ctx["num"]), "bold": self._bold(p),
                 "autoNum": auto, "captionOf": None, "format": docx_format.para_summary(self, p),
                 "runs": docx_format.run_looks(self, p, zip(texts, runs))}
        images = [self._image_block(d) for d in self._drawings(p)]
        return ([block] if text.strip() or not images else []) + images  # like hwpx: image-only paragraph -> images

    def _table_block(self, tbl, ctx):
        grid = tbl.find(W + "tblGrid")
        rows = list(_kids(tbl, (W + "tr",)))
        starts, width = _grid_cells(rows)
        cells = [{**self._cell_block(tc, ri, col, span, ctx), "rowSpan": n} for tc, ri, col, span, n in starts]
        n_cols = max(len(grid.findall(W + "gridCol")) if grid is not None else 0, width)
        return {"id": self._id(tbl, "t"), "type": "table", "nRows": len(rows), "nCols": n_cols, "cells": cells}

    def _cell_block(self, tc, row, col, span, ctx):
        blocks = self._blocks(tc, ctx)
        paras = [b for b in blocks if b["type"] == "paragraph"]
        texted = [b for b in paras if b["text"].strip()]
        shd = tc.find(f"{W}tcPr/{W}shd")
        fill = (shd.get(W + "fill") if shd is not None else None) or "auto"
        # ponytail: "shaded" = direct cell shading only; the drawn fill (cell_props) includes table-style conditional formats.
        look = docx_format.cell_props(self, tc)
        if _dark(look["fill"]):  # Word 자동 글자색은 어두운 칸 음영 위에서 흰색(NFM — Word 16 PDF: AIP 서식 첫 열)
            for b in paras:
                for f in [b["format"], *(r["format"] for r in b.get("runs") or ())]:
                    if not f.get("color"):
                        f["color"] = "#FFFFFF"
        return {"id": self._id(tc, "c"), "row": row, "col": col, "rowSpan": 1, "colSpan": span,
                "shaded": fill.upper() not in ("AUTO", "FFFFFF"),
                "bold": bool(texted) and all(b["bold"] for b in texted),
                "text": "\n".join(b["text"] for b in paras), "blocks": blocks, **look}

    # ---- editing ----------------------------------------------------------------------------------------

    def set_text(self, block_id: str, text: str, templates=None) -> None:
        """`templates` (cells): per line, a paragraph id whose shape a NEW paragraph for that line copies (None = the cell's first)."""
        el = self._ids[block_id]
        if el.tag == W + "p":
            self._set_para(el, text.replace("\n", "\u2028"))
        elif el.tag == W + "tc":
            self._set_cell(el, text, templates or ())
        else:
            raise ValueError(f"{block_id} is not a paragraph or cell")
        self._dirty.add(self._doc)

    def _set_para(self, p, text):
        slots = self._slots(p)
        if any(kind == "seq" and x["key"] not in self._seq for kind, x in slots):
            self.blocks()  # computed SEQ numbers (else those of the last blocks() call, i.e. what the caller saw)
        old = [_run_text(x) if kind == "run" else self._seq.get(x["key"], (None, ""))[1] for kind, x in slots]
        if not slots and text:
            slots, old = [("run", self._empty_run(p))], [""]
        for (kind, x), was, new in zip(slots, old, redistribute(old, text)):
            if new != was:
                _write_run(x, new) if kind == "run" else self._replace_field(x, new)

    @staticmethod
    def _empty_run(p):
        """Run to receive text in a paragraph without text runs: its last bare run, else a new run."""
        bare = [r for r in _runs(p) if all(c.tag == W + "rPr" for c in r)]
        if bare:
            return bare[-1]
        r = etree.SubElement(p, W + "r")
        mark = p.find(f"{W}pPr/{W}rPr")  # paragraph-mark formatting is what Word gives newly typed text
        if mark is not None:
            r.append(_strip(copy.deepcopy(mark), *_REVISIONS))
        return r

    def _set_cell(self, tc, text, templates=()):
        if tc.find(f".//{W}tbl") is not None:
            raise ValueError("cell contains a nested table")
        all_p = list(_kids(tc, (W + "p",)))
        paras = [p for p in all_p if _text(p).strip() or not self._drawings(p)]  # the cell's paragraph blocks
        lines = text.split("\n")
        tpl = (paras or all_p or [None])[0]
        last = (paras or all_p or [None])[-1]
        for i, line in enumerate(lines):
            if i < len(paras):
                self._set_para(paras[i], line)
                continue
            own = self._ids.get(templates[i]) if i < len(templates) and templates[i] else None
            new = self._new_para(own if own is not None and own.tag == W + "p" else tpl, line)
            last.addnext(new) if last is not None else tc.append(new)
            last = new
        for p in paras[len(lines):]:
            self._set_para(p, "") if self._drawings(p) else p.getparent().remove(p)

    def _new_para(self, tpl, text):
        """New paragraph with tpl's paragraph properties and its first text run's character properties."""
        p = etree.Element(W + "p")
        if tpl is None:
            _write_run(etree.SubElement(p, W + "r"), text)
            return p
        if tpl.find(W + "pPr") is not None:
            p.append(_strip(copy.deepcopy(tpl.find(W + "pPr")), *_REVISIONS))
        runs = list(_runs(tpl))
        src = next((r for r in runs if _has_text(r)), None)
        if src is None:
            src = next((r for r in reversed(runs) if r.find(W + "rPr") is not None), None)
        r = etree.SubElement(p, W + "r")
        if src is not None and src.find(W + "rPr") is not None:
            r.append(_strip(copy.deepcopy(src.find(W + "rPr")), *_REVISIONS))
        _write_run(r, text)
        return p

    def _block(self, el):
        """Block element for an insert reference: an image id resolves to its paragraph."""
        if el.tag == W + "drawing":
            el = next(a for a in el.iterancestors(W + "p") if a.getparent().tag != W + "txbxContent")
        if el.tag not in (W + "p", W + "tbl"):
            raise ValueError("reference must be a paragraph, table or image")
        return el

    def _body_template(self):
        """First plain body paragraph (has text, no outline level, no numbering)."""
        paras = list(_kids(self._body, (W + "p",)))
        return next((p for p in paras if _text(p).strip() and self._outline(p) is None and self._num_ref(p) is None),
                    paras[0] if paras else None)

    def _next_docpr(self):
        return max((int(e.get("id")) for e in self._body.iter(WP + "docPr") if (e.get("id") or "").isdecimal()),   # isdigit 은 「²」 를 통과시켜 int 가 실패(astra G20)
                   default=0) + 1

    def insert_after(self, ref_id: str, items: list[dict], src=None) -> list[str]:
        ref, new_ids = self._block(self._ids[ref_id]), []
        for it in items:
            if it["kind"] == "copy":
                if src is None:
                    raise ValueError("copy items need src")
                el = self._copy_from(src, src._ids[it["srcId"]])
            elif it["kind"] in ("heading", "paragraph"):
                tpl = self._block(self._ids[it["templateId"]]) if it.get("templateId") else self._body_template()
                el = self._new_para(tpl, it.get("text", "").replace("\n", "\u2028"))
                if not it.get("keepNumbering", it["kind"] != "heading") and self._num_ref(el):
                    _number_off(el)
            else:
                raise ValueError(f"unknown item kind {it['kind']!r}")
            ref.addnext(el)
            ref = el
            image_only = el.tag == W + "p" and self._drawings(el) and not _text(el).strip()
            new_ids.append(self._id(self._drawings(el)[0], "i") if image_only
                           else self._id(el, "t" if el.tag == W + "tbl" else "p"))
        cell = ref.getparent()
        if cell.tag == W + "tc" and cell[-1].tag == W + "tbl":
            etree.SubElement(cell, W + "p")  # a table cell must end with a paragraph
        self._dirty.add(self._doc)
        return new_ids

    def insert_line(self, ref_id: str, text: str = "", before: bool = False, after_id: str | None = None) -> str:
        """ref 문단과 같은 문단·글자 모양의 새 문단 하나를 ref 위/아래에(문단 줄 추가 — spec_웹UI ② UI-010) -> 새 id.
        after_id = 아래로 넣을 자리(그 블록 바로 뒤 — 헤딩 구간 끝, 표·그림이면 그 블록 뒤), 없으면 ref 바로 뒤. 서식은 늘 ref.
        앞에서 쪽 나눔은 위로 넣으면 새 문단이 넘겨받고 아래로 넣으면 새 문단에 안 붙인다. ref 가 구역 끝 문단(pPr/sectPr)이고 바로 아래로
        넣으면 구역 끝을 새 문단으로 옮긴다(새 줄이 같은 구역; after_id 자리는 그 자리의 구역 그대로) — _new_para 는 sectPr 를 베끼지 않는다."""
        ref = self._ids[ref_id]
        if ref.tag != W + "p":
            raise ValueError("문단이 아닙니다")
        new = self._new_para(ref, text.replace("\n", " "))
        ppr = (ref if before else new).find(W + "pPr")
        brk = ppr.find(W + "pageBreakBefore") if ppr is not None else None
        if brk is not None and brk.get(W + "val") not in ("0", "false", "off"):
            ppr.remove(brk)
        sect = ref.find(f"{W}pPr/{W}sectPr")
        if not before and not after_id and sect is not None:
            new.find(W + "pPr").append(sect)  # lxml: 옮김 — sectPr 는 pPr 끝(pPrChange 는 _new_para 가 뺌)
        (ref.addprevious if before else (self._block(self._ids[after_id]) if after_id else ref).addnext)(new)
        self._dirty.add(self._doc)
        return self._id(new, "p")

    def append_rows(self, table_id: str, rows: list[list[str]]) -> list[str]:
        tbl = self._ids[table_id]
        last = list(_kids(tbl, (W + "tr",)))[-1]
        for vm in last.iter(W + "vMerge"):
            if vm.get(W + "val") != "restart":
                raise ValueError("last row has vertically merged cells")
        ids, ref = [], last
        for values in rows:
            tr = copy.deepcopy(last)
            _drop_ids(tr)
            for vm in list(tr.iter(W + "vMerge")):
                vm.getparent().remove(vm)
            tcs = list(_kids(tr, (W + "tc",)))
            values = list(values) + [""] * (len(tcs) - len(values))
            values[len(tcs) - 1:] = [" | ".join(values[len(tcs) - 1:])]  # surplus values go to the last cell
            for tc, v in zip(tcs, values):
                self._set_cell(tc, v)
            n = self._next_docpr()
            for e in tr.iter(WP + "docPr"):
                e.set("id", str(n))
                n += 1
            ref.addnext(tr)
            ref = tr
            ids += [self._id(tc, "c") for tc in tcs]
        self._dirty.add(self._doc)
        return ids

    def insert_rows(self, table_id: str, first: int, last: int, values: list[dict], grow=()) -> list[dict]:
        """Copy rows first..last once per `values` item, right after `last` (spec_표_분류 §5 끼우기). values[k] =
        {cell id: text} for copy k, other cells keep their text. A cell from above reaching `last` grows by itself (its
        w:vMerge continuations are copied too); the `grow` cell ids become a vertical merge whose copies continue it.
        -> [{cell id: copy's cell id}]; ValueError when a merged cell crosses."""
        rows = list(_kids(self._ids[table_id], (W + "tr",)))
        starts, _ = _grid_cells(rows)
        grown = {id(tc) for tc, *_ in starts if self._rev.get(tc) in grow}
        if any(r < first <= r + n - 1 < last or first <= r <= last < r + n - 1
               for tc, r, _, _, n in starts if id(tc) not in grown):
            raise ValueError("a merged cell crosses the rows to copy")
        if not 0 <= first <= last < len(rows):
            raise ValueError(f"no rows {first}..{last}")
        start_ids = {id(tc): self._id(tc, "c") for tc, r, *_ in starts if first <= r <= last and id(tc) not in grown}
        # 복사본을 먼저 다 만든다(글 쓰기까지 — 표에 아직 안 붙임): 여기서 실패하면 표는 그대로(11-03 astra F07)
        staged = []
        for vals in values:
            made, pairs = [], []
            for tr in rows[first:last + 1]:
                cp = copy.deepcopy(tr)
                _drop_ids(cp)
                for o, c in list(zip(_kids(tr, (W + "tc",)), _kids(cp, (W + "tc",)))):
                    if id(o) in grown:
                        _vmerge(c, restart=False)
                    elif (oid := start_ids.get(id(o))) is not None:
                        if oid in vals:
                            self._set_cell(c, vals[oid])
                        pairs.append((oid, c))
                made.append(cp)
            staged.append((made, pairs))
        n = self._next_docpr()   # 고치기 전에 — 여기서 실패해도 표 그대로(astra G20)
        for tc, *_ in starts:
            if id(tc) in grown:
                _vmerge(tc, restart=True)
        out, ref = [], rows[last]
        for made, pairs in staged:
            for cp in made:
                for e in cp.iter(WP + "docPr"):
                    e.set("id", str(n))
                    n += 1
                ref.addnext(cp)
                ref = cp
            out.append({oid: self._id(c, "c") for oid, c in pairs})
        self._dirty.add(self._doc)
        return out

    # ---- table cell editing (spec_표_편집 ② §2·§3) -----------------------------------------------------------------
    # Same calls and results as HwpxDoc (grid.result: {"cell", "new", "removed", "grown", "map"}). Grid lines stay as
    # Word keeps them (a row of vMerge continuations is fine in Word); w:tblGrid holds the column widths.

    def merge_cells(self, table_id: str, r0: int, c0: int, r1: int, c1: int, keep: str | None = None) -> dict:
        """One cell over rows r0..r1 × columns c0..c1 — the top-left cell (keeps its id and tcPr; gridSpan, vMerge, tcW
        set). The other cells' content follows its own top→bottom, left→right (empty cells left out; an empty top-left
        cell gives way to the first filled one); keep = a cell id inside the range: only that cell's content stays (매직
        브러쉬 규칙 C9). Its bottom and right lines become the bottom-right cell's. ValueError when a merged cell sticks
        out of the range or `keep` is not inside it."""
        tbl = self._tbl(table_id)
        trs, cells, widths = self._tgrid(tbl)
        tl, br, others = grid.merge(cells, len(trs), len(widths), int(r0), int(c0), int(r1), int(c1))
        inside = [tl, *others]
        full = grid.kept(inside, keep, lambda el: self._id(el, "c")) if keep is not None else [x for x in inside if not self._tc_empty(x.el)]
        if not others:
            return grid.result(self._cid, tl)
        body = lambda tc: [c for c in tc if c.tag != W + "tcPr"]  # noqa: E731
        if full and full[0] is not tl:
            for c in body(tl.el):
                tl.el.remove(c)
        for x in others:
            if x in full:
                tl.el.extend(body(x.el))
        if tl.el[-1].tag != W + "p":  # a cell ends with a paragraph
            etree.SubElement(tl.el, W + "p")
        removed = [self._id(x.el, "c") for x in others]
        _merge_borders(tl.el, br.rows[max(br.rows)])
        tl.rows = {tl.r: tl.el}  # its continuations are made anew from the merged tcPr
        self._tput(tbl, trs, cells, widths, sized=[tl])
        return grid.result(self._cid, tl, removed=removed)

    def unmerge_cell(self, cell_id: str) -> dict:
        """A merged cell back to its grid: it stays the top-left piece with its content; the other pieces are empty
        copies of it (its tcPr, its first paragraph's shape). Not merged: nothing changes."""
        tc = docx_format._el(self, cell_id, "tc")
        tbl = next(tc.iterancestors(W + "tbl"))
        trs, cells, widths = self._tgrid(tbl)
        x = next(c for c in cells if c.el is tc)
        if x.rs == x.cs == 1:
            return grid.result(self._cid, x)
        new = grid.unmerge(cells, x)
        for y in new:
            y.el = self._blank_tc(tc, tc)
            y.rows = {y.r: y.el}
        x.rows = {x.r: tc}  # its vMerge continuations go: the rows below hold the new pieces
        self._tput(tbl, trs, cells, widths, sized=[x, *new])
        return grid.result(self._cid, x, new)

    def split_cell(self, cell_id: str, rows: int, cols: int) -> dict:
        """한글 「셀 나누기」 (HwpxDoc.split_cell): rows × cols pieces sharing the cell's width (w:tblGrid) evenly; a
        new row copies the cell's row properties, trHeight shared out."""
        tc = docx_format._el(self, cell_id, "tc")
        tbl = next(tc.iterancestors(W + "tbl"))
        trs, cells, widths = self._tgrid(tbl)
        x = next(c for c in cells if c.el is tc)
        new, grown, added = grid.split(cells, x, int(rows), int(cols))
        for axis, at, k in added:
            if axis == "c":
                widths[at:at + 1] = grid.share(widths[at], k + 1)
                continue
            h = trs[at].find(f"{W}trPr/{W}trHeight")
            if h is not None and (h.get(W + "val") or "").isdigit():
                h.set(W + "val", str(int(h.get(W + "val")) // (k + 1)))
            rows_new = [_row_like(trs[at]) for _ in range(k)]
            for tr in reversed(rows_new):
                trs[at].addnext(tr)
            trs[at + 1:at + 1] = rows_new
        x.rows = {i: t for i, t in x.rows.items() if i < x.r + x.rs}
        for y in new:
            y.el = self._blank_tc(tc, tc)
            y.rows = {y.r: y.el}
        self._tput(tbl, trs, cells, widths, sized=[x, *new])
        return grid.result(self._cid, x, new, grown=grown)

    def clone_rows(self, table_id: str, r0: int, r1: int, cols=None, keep_text: bool = True, above: bool = False,
                   lenient: bool = False, fit: bool = False) -> dict:
        """HwpxDoc.clone_rows: rows r0..r1 copied right below r1 (keep_text=False: empty cells, same shapes); cols =
        [c0, c1] copies only those columns, the cells outside them on row r1 grow (vMerge) over the new rows; above=True:
        the copy goes right above r0 and the outside cells on r0 grow; lenient=True: a merged cell partly over the rows
        grows instead of raising (grid.clone — 행 전체 넣기); fit=True: a divided row inside the picked cells instead of
        new rows when they span rows the other columns divide (grid.clone_inside — 고른 칸만 넣기)."""
        tbl = self._tbl(table_id)
        trs, cells, widths = self._tgrid(tbl)
        r0, r1 = int(r0), int(r1)
        c0, c1 = (int(cols[0]), int(cols[1])) if cols is not None else (0, len(widths) - 1)
        inside = grid.clone_inside(cells, len(trs), len(widths), r0, r1, c0, c1, above=above) if fit and cols is not None else None
        if inside is not None:
            new, picked = inside
            n = self._next_docpr()
            for y in new:
                y.el = copy.deepcopy(y.src.el) if keep_text else self._blank_tc(y.src.el, y.src.el)
                y.rows = {y.r: y.el}  # 아래 줄의 vMerge 잇기는 _tput 이 만든다
                _drop_ids(y.el)
                for e in y.el.iter(WP + "docPr"):
                    e.set("id", str(n))
                    n += 1
            self._tput(tbl, trs, cells, widths, sized=[*picked, *new])
            return grid.result(self._cid, None, new, mapping=True)
        new, grown = grid.clone(cells, len(trs), len(widths), r0, r1, c0, c1, above=above, lenient=lenient)
        d, ref, rows_new = r1 - r0 + 1, trs[r1], [_row_like(t) for t in trs[r0:r1 + 1]]
        for t in rows_new:
            if above:
                trs[r0].addprevious(t)
            else:
                ref.addnext(t)
                ref = t
        at = r0 if above else r1 + 1
        trs[at:at] = rows_new
        n = self._next_docpr()
        for y in new:
            s = y.src
            y.el = copy.deepcopy(s.el) if keep_text else self._blank_tc(s.el, s.el)
            y.rows = {y.r: y.el, **{i + (y.r - s.r): copy.deepcopy(t) for i, t in s.rows.items() if i != s.r}}
            for t in y.rows.values():
                _drop_ids(t)
                for e in t.iter(WP + "docPr"):
                    e.set("id", str(n))
                    n += 1
        self._tput(tbl, trs, cells, widths)
        return grid.result(self._cid, None, new, grown=grown, mapping=True)

    # ---- 구분 초기화 (spec_구분_초기화 ② §4) -------------------------------------------------------------

    def delete_rows(self, table_id: str, r0: int, r1: int, cols=None) -> dict:
        """HwpxDoc.delete_rows: grid rows r0..r1 out (their w:tr), cells from above lose those rows' vMerge
        continuations; cols = [c0, c1]: grid.drop_band (outside the columns a cell starting inside the rows keeps its
        start w:tc on the first row after). -> {"removed": [cell ids], "shrunk": [cell ids]}."""
        tbl = self._tbl(table_id)
        trs, cells, widths = self._tgrid(tbl)
        r0, r1 = int(r0), int(r1)
        if cols is None:
            gone, shrunk = grid.drop_rows(cells, len(trs), r0, r1)
        else:
            gone, shrunk = grid.drop_band(cells, len(trs), len(widths), r0, r1, int(cols[0]), int(cols[1]))
        removed = [self._cid(x) for x in gone]
        for t in trs[r0:r1 + 1]:
            t.getparent().remove(t)  # a row may sit in a w:sdt / w:customXml wrapper (_kids looks through them)
        del trs[r0:r1 + 1]
        self._tput(tbl, trs, cells, widths)
        return {"removed": removed, "shrunk": [self._cid(x[0]) for x in shrunk]}

    def move_rows(self, table_id: str, r0: int, r1: int, cols, to: int) -> dict:
        """HwpxDoc.move_rows: rows r0..r1 of columns cols (None = whole rows) to the row line `to`. Whole rows move
        their w:tr (row height and properties along); a column band moves its w:tc between the rows."""
        tbl = self._tbl(table_id)
        trs, cells, widths = self._tgrid(tbl)
        r0, r1, to = int(r0), int(r1), int(to)
        c0, c1 = (int(cols[0]), int(cols[1])) if cols is not None else (0, len(widths) - 1)
        perm = grid.move_band(cells, len(trs), len(widths), r0, r1, c0, c1, to)
        if (c0, c1) == (0, len(widths) - 1):
            order = list(trs)
            for i, t in enumerate(order):
                trs[perm.get(i, i)] = t
            anchor = order[max(perm) + 1] if max(perm) + 1 < len(order) else None
            for t in trs[min(perm):max(perm) + 1]:
                if anchor is not None:
                    anchor.addprevious(t)
                else:
                    t.getparent().append(t)
        self._tput(tbl, trs, cells, widths)
        return {"moved": perm}

    def move_blocks(self, first_id: str, last_id: str, ref_id: str, before: bool = False) -> dict:
        """HwpxDoc.move_blocks: the body blocks first..last right after (before=True: before) block ref_id; ids stay.
        ValueError when the range holds a section break or ref is inside it. -> {"moved": [ids]}."""
        els = self._range(first_id, last_id)
        ref = self._block(self._ids[ref_id])
        if ref in els:
            raise ValueError("옮길 범위 안으로는 옮길 수 없습니다")
        if any(next(el.iter(W + "sectPr"), None) is not None for el in els):
            raise ValueError("구역 나누기가 든 문단은 옮길 수 없습니다")
        for el in (els if before else reversed(els)):
            (ref.addprevious if before else ref.addnext)(el)
        self._dirty.add(self._doc)
        return {"moved": [self._rev[e] for el in els for e in el.iter() if e in self._rev]}

    def clone_cols(self, table_id: str, c0: int, c1: int, keep=None) -> dict:
        """HwpxDoc.clone_cols: grid columns c0..c1 (every row, with text) copied right after c1 — each copied cell's w:tc
        in every row it covers (vMerge continuations too); keep = (a, b) pre-op columns keeping their total width, None:
        the table gets wider (w:tblW in dxa too). -> grid.result(), "map" = {copied cell: its copy}."""
        tbl = self._tbl(table_id)
        trs, cells, widths = self._tgrid(tbl)
        c0, c1 = int(c0), int(c1)
        new, grown = grid.clone_cols(cells, len(widths), c0, c1)
        after, fit = grid.col_widths(widths, c0, c1, keep, add=True)
        n = self._next_docpr()
        for y in new:
            y.rows = {i: copy.deepcopy(t) for i, t in y.src.rows.items()}
            y.el = y.rows[y.r]
            for t in y.rows.values():
                _drop_ids(t)
                for e in t.iter(WP + "docPr"):
                    e.set("id", str(n))
                    n += 1
        self._col_put(tbl, trs, cells, widths, after, fit, [*new, *grown])
        return grid.result(self._cid, None, new, grown=grown, mapping=True)

    def delete_cols(self, table_id: str, c0: int, c1: int, keep=None) -> dict:
        """HwpxDoc.delete_cols: grid columns c0..c1 out (their w:tc go), cells from the left across them get narrower;
        keep = (a, b) pre-op columns keeping their total width, None: the table gets narrower.
        -> {"removed": [cell ids], "shrunk": [cell ids]}."""
        tbl = self._tbl(table_id)
        trs, cells, widths = self._tgrid(tbl)
        c0, c1 = int(c0), int(c1)
        gone, shrunk = grid.drop_cols(cells, len(widths), c0, c1)
        after, fit = grid.col_widths(widths, c0, c1, keep, add=False)
        removed = [self._cid(x) for x in gone]
        self._col_put(tbl, trs, cells, widths, after, fit, [x for x, _ in shrunk])
        return {"removed": removed, "shrunk": [self._cid(x) for x, _ in shrunk]}

    def even_cols(self, table_id: str, spans) -> dict:
        """HwpxDoc.even_cols: column spans [(c0, c1)…] share their total width equally (w:tblGrid·tcW), the table width
        stays. -> {"widths": new widths}."""
        tbl = self._tbl(table_id)
        trs, cells, widths = self._tgrid(tbl)
        after, fit = grid.even(widths, [(int(a), int(b)) for a, b in spans])
        self._col_put(tbl, trs, cells, widths, after, fit, [])
        return {"widths": after}

    def set_line_sizes(self, table_id: str, axis: str, sizes) -> dict:
        """HwpxDoc.set_line_sizes: grid lines take the given sizes {line: mm} — rows = w:trHeight(atLeast — Word 가 내용보다 줄이지 않음),
        columns = w:tblGrid·tcW(표 너비는 열의 합을 따름) (표 서식 정리, spec_표_서식_정리 ② §3). -> {"sizes": every line in mm}."""
        tbl = self._tbl(table_id)
        trs, cells, widths = self._tgrid(tbl)
        want = {int(k): float(v) for k, v in dict(sizes).items()}
        n = len(trs) if axis == "r" else len(widths)
        if not want or any(k < 0 or k >= n for k in want):
            raise ValueError(grid.OUTSIDE)
        if any(v <= 0 for v in want.values()):
            raise ValueError("크기는 0 보다 커야 합니다")
        tw = docx_format._TW_MM
        if axis == "r":
            for k, mm in want.items():
                tr = trs[k]
                pr = tr.find(W + "trPr")
                if pr is None:
                    pr = etree.Element(W + "trPr")
                    ex = tr.find(W + "tblPrEx")
                    tr.insert(0 if ex is None else 1, pr)
                h = pr.find(W + "trHeight")
                if h is None:
                    h = docx_format._place(pr, etree.Element(W + "trHeight"), docx_format._seq(_TRPR_ORDER))
                h.attrib.clear()
                h.attrib.update({W + "val": str(round(mm * tw)), W + "hRule": "atLeast"})
            out = []
            for tr in trs:
                h = tr.find(f"{W}trPr/{W}trHeight")
                out.append(round(int(h.get(W + "val")) / tw, 2) if h is not None and (h.get(W + "val") or "").isdigit() else 0)
            return {"sizes": out}
        after = list(widths)
        for k, mm in want.items():
            after[k] = round(mm * tw)
        self._col_put(tbl, trs, cells, widths, after, (min(want), max(want)), [])
        return {"sizes": [round(w / tw, 2) for w in after]}

    # ---- 매직 브러쉬 행 높이·기준 칸 크기 (spec_매직브러쉬 ② §3 — 2026-11-01 DOCX 켬, ④ D1) --------------------------------------

    def _tr_height(self, tr):
        """A row's w:trHeight in twips (0 = none — Word sizes the row by its content)."""
        h = tr.find(f"{W}trPr/{W}trHeight")
        return int(h.get(W + "val")) if h is not None and (h.get(W + "val") or "").isdigit() else 0

    def _tr_set_height(self, tr, twips):
        """w:trPr/w:trHeight val (same shape as set_line_sizes); an existing hRule (exact) stays, otherwise atLeast."""
        pr = tr.find(W + "trPr")
        if pr is None:
            pr = etree.Element(W + "trPr")
            ex = tr.find(W + "tblPrEx")
            tr.insert(0 if ex is None else 1, pr)
        h = pr.find(W + "trHeight")
        if h is None:
            h = docx_format._place(pr, etree.Element(W + "trHeight"), docx_format._seq(_TRPR_ORDER))
        rule = h.get(W + "hRule") or "atLeast"
        h.attrib.clear()
        h.attrib.update({W + "val": str(int(twips)), W + "hRule": rule})

    def even_rows(self, table_id: str, spans) -> dict:
        """HwpxDoc.even_rows: grid row spans [(r0, r1)…] share their total height (w:trHeight) equally — rows inside a span keep
        their proportions, rows without a height share evenly (매직 브러쉬 「높이 같게」, 규칙 C2). Word gives a row without
        w:trHeight its content's height, so when no row in the spans has one there is nothing to even -> ValueError.
        -> {"heights": new heights (twips)}."""
        tbl = self._tbl(table_id)
        trs = list(_kids(tbl, (W + "tr",)))
        spans = [(int(a), int(b)) for a, b in spans]
        if not spans or any(a < 0 or b >= len(trs) or a > b for a, b in spans):
            raise ValueError(grid.OUTSIDE)
        heights = [self._tr_height(tr) for tr in trs]
        a, b = spans[0][0], spans[-1][1]
        total = sum(heights[a:b + 1])
        if total <= 0:
            raise ValueError("높이가 정해진 행이 없습니다 — Word 표는 행 높이(최소)가 정해진 행만 같게 할 수 있습니다")
        after = list(heights)
        for (r0, r1), h in zip(spans, grid.share(total, len(spans))):
            if sum(after[r0:r1 + 1]) <= 0:
                after[r0:r1 + 1] = grid.share(h, r1 - r0 + 1)
            else:
                grid.refit(after, r0, r1, h)
        for k in range(a, b + 1):
            if after[k] != heights[k] or heights[k] == 0:
                self._tr_set_height(trs[k], after[k])
        return {"heights": after}

    def size_lines(self, table_id: str, axis: str, lines, ref_cell_id: str) -> dict:
        """HwpxDoc.size_lines: grid lines (axis "r" rows / "c" columns) take the reference cell's line size (its size on that
        axis ÷ its span) — rows = w:trHeight, columns = w:tblGrid·tcW with a dxa w:tblW following (매직 브러쉬 기준 칸 높이·폭
        맞추기, 규칙 J3·J4). -> {"sizes": every line (twips), "size"}."""
        tbl = self._tbl(table_id)
        trs, cells, widths = self._tgrid(tbl)
        ref = next((x for x in cells if self._cid(x) == ref_cell_id), None)
        if ref is None:
            raise ValueError("기준 칸이 이 표에 없습니다")
        arr = [self._tr_height(tr) for tr in trs] if axis == "r" else list(widths)
        s, n = ref.at(axis)
        size = sum(arr[s:s + n]) // n
        lines = sorted({int(k) for k in lines})
        if not lines or any(k < 0 or k >= len(arr) for k in lines):
            raise ValueError(grid.OUTSIDE)
        if size <= 0:
            raise ValueError("기준 칸의 행 높이가 정해져 있지 않습니다 — Word 표는 높이(최소)가 정해진 행만 기준이 됩니다" if axis == "r"
                             else "기준 칸의 열 너비를 알 수 없습니다")
        if axis == "r":
            for k in lines:
                arr[k] = size
                self._tr_set_height(trs[k], size)
            return {"sizes": arr, "size": size}
        for k in lines:
            arr[k] = size
        touched = [x for x in cells if any(x.c <= k < x.c + x.cs for k in lines)]
        self._col_put(tbl, trs, cells, widths, arr, None, touched)
        return {"sizes": arr, "size": size}

    def _col_put(self, tbl, trs, cells, before, widths, fit, touched):
        """Write a column copy/delete back (_tput rebuilds each row from `cells`, so a dropped cell's w:tc go): tcW of the
        `touched` cells and of every cell over the refit columns `fit`; without `fit` a dxa w:tblW follows the columns."""
        a, b = fit or (len(widths), -1)
        sized = [x for x in cells if x in touched or x.c <= b and x.c + x.cs - 1 >= a]
        tw = tbl.find(f"{W}tblPr/{W}tblW")
        if fit is None and tw is not None and tw.get(W + "type") == "dxa" and (tw.get(W + "w") or "").isdigit():
            tw.set(W + "w", str(max(0, int(tw.get(W + "w")) + sum(widths) - sum(before))))
        self._tput(tbl, trs, cells, widths, sized=sized)

    def _marks(self):
        """(paragraph, [runs], text) per footnote mark: consecutive superscript runs (w:vertAlign superscript, direct or
        from the run style) of a paragraph whose text is like 「15)」·「15-1)」 — the whole body, cells too."""
        def sup(r):
            pr = r.find(W + "rPr")
            v = _val(pr, W + "vertAlign")
            if v is None:
                v = next((x for s in self._chain(_val(pr, W + "rStyle")) if (x := _val(s.find(W + "rPr"), W + "vertAlign"))),
                         None)
            return v == "superscript"
        out = []
        for p in self._body.iter(W + "p"):
            seq = []
            for r in [*_runs(p), None]:
                if r is not None and sup(r):
                    seq.append(r)
                    continue
                text = "".join(_run_text(x) for x in seq)
                if seq and MARK_RE.match(text):
                    out.append((p, seq, text))
                seq = []
        return out

    def superscript_marks(self) -> list[dict]:
        """HwpxDoc.superscript_marks: [{"id": paragraph id, "text": mark}] in document order."""
        return [{"id": self._id(p, "p"), "text": text} for p, _, text in self._marks()]

    def strip_superscript_marks(self) -> int:
        """HwpxDoc.strip_superscript_marks: the marks' w:t (and non-breaking hyphens) go, the runs stay. -> count."""
        marks = self._marks()
        for _, seq, _ in marks:
            for r in seq:
                for t in r.findall(W + "t") + r.findall(W + "noBreakHyphen"):
                    r.remove(t)
        if marks:
            self._dirty.add(self._doc)
        return len(marks)

    def _range(self, first_id, last_id):
        """Sibling elements from first's block element to last's (w:p / w:tbl, and whatever lies between)."""
        a, b = self._block(self._ids[first_id]), self._block(self._ids[last_id])
        if a.getparent() is not b.getparent():
            raise ValueError("같은 그릇(본문·칸)의 블록이 아닙니다")
        out, el = [], a
        while el is not None:
            out.append(el)
            if el is b:
                return out
            el = el.getnext()
        raise ValueError("블록 범위가 거꾸로입니다")

    def clone_blocks(self, first_id: str, last_id: str) -> dict:
        """HwpxDoc.clone_blocks: copy of the range right after it -> {"map": {block id: its copy's id}}. The copy loses
        w14 ids, bookmarks and section breaks; its drawings get new docPr ids."""
        els, mapping, n = self._range(first_id, last_id), {}, self._next_docpr()
        ref = els[-1]
        for el in els:
            new = copy.deepcopy(el)
            for o, c in zip(el.iter(), new.iter()):
                if o in self._rev:
                    old = self._rev[o]
                    mapping[old] = self._id(c, old.rstrip("0123456789"))
            _drop_ids(new)
            for e in list(new.iter(W + "bookmarkStart", W + "bookmarkEnd", W + "sectPr")):
                e.getparent().remove(e)
            for e in new.iter(WP + "docPr"):
                e.set("id", str(n))
                n += 1
            ref.addnext(new)
            ref = new
        self._dirty.add(self._doc)
        return {"map": mapping}

    def delete_blocks(self, first_id: str, last_id: str) -> dict:
        """HwpxDoc.delete_blocks: the range out; ValueError when it holds a section break; a cell keeps ending with a
        paragraph. -> {"removed": [ids]}."""
        els = self._range(first_id, last_id)
        if any(next(el.iter(W + "sectPr"), None) is not None for el in els):
            raise ValueError("구역 나누기가 든 문단은 지울 수 없습니다")
        parent = els[0].getparent()
        removed = [self._rev[e] for el in els for e in el.iter() if e in self._rev]
        for el in els:
            parent.remove(el)
        if parent.tag == W + "tc" and (not len(parent) or parent[-1].tag != W + "p"):
            parent.append(self._new_para(els[0] if els[0].tag == W + "p" else None, ""))
        self._dirty.add(self._doc)
        return {"removed": removed}

    def _cid(self, x):
        return self._id(x.el, "c")

    def _tbl(self, table_id):
        tbl = self._ids.get(table_id)
        if tbl is None or tbl.tag != W + "tbl":
            raise ValueError("표가 아닙니다")
        return tbl

    def _tgrid(self, tbl):
        """(w:tr list, cells, column widths): grid.Cell per cell with .rows = its w:tc per row (start, vMerge
        continuations) — the reading of _grid_cells; w:tblGrid widths in twips, padded to the grid width."""
        trs, cells, above, width = list(_kids(tbl, (W + "tr",))), [], {}, 0
        for ri, tr in enumerate(trs):
            col, below = int(_val(tr.find(W + "trPr"), W + "gridBefore") or 0), {}
            for tc in _kids(tr, (W + "tc",)):
                pr = tc.find(W + "tcPr")
                span = int(_val(pr, W + "gridSpan") or 1)
                vm = pr.find(W + "vMerge") if pr is not None else None
                if vm is not None and vm.get(W + "val") != "restart" and col in above:
                    x = above[col]
                    x.rs += 1
                else:
                    x = grid.Cell(tc, ri, col, 1, span)
                    cells.append(x)
                x.rows[ri] = tc
                if vm is not None:
                    below[col] = x
                col += span
            above, width = below, max(width, col)
        g = tbl.find(W + "tblGrid")
        widths = [int(c.get(W + "w") or 0) for c in g.findall(W + "gridCol")] if g is not None else []
        widths += [widths[-1] if widths else 1440] * (width - len(widths))
        return trs, cells, widths

    def _tput(self, tbl, trs, cells, widths, sized=()):
        """Write the grid back: w:tblGrid widths; per row its cells' w:tc in column order — a cell's own tc on its first
        row, below it a vMerge continuation (the cell's tc there, else an empty copy of its tc above); gridSpan/vMerge
        of each, tcW of the `sized` cells and of new continuations, gridBefore/gridAfter."""
        n, sized = len(widths), set(sized)
        g = tbl.find(W + "tblGrid")
        if g is not None and [int(c.get(W + "w") or 0) for c in g.findall(W + "gridCol")] != widths:
            for c in g.findall(W + "gridCol"):
                g.remove(c)
            for i, w in enumerate(widths):
                g.insert(i, etree.Element(W + "gridCol", {W + "w": str(w)}))
        for ri, tr in enumerate(trs):
            row, tcs = sorted((x for x in cells if x.r <= ri < x.r + x.rs), key=lambda x: x.c), []
            for x in row:
                tc = x.rows.get(ri)
                made = tc is None
                if made:
                    tc = x.rows[ri] = self._blank_tc(x.rows[max(i for i in x.rows if i < ri)], x.el)
                pr = tc.find(W + "tcPr")
                if pr is None:
                    pr = etree.Element(W + "tcPr")
                    tc.insert(0, pr)
                if (_val(pr, W + "gridSpan") or "1") != str(x.cs):
                    _tc_prop(pr, "gridSpan", str(x.cs) if x.cs > 1 else None)
                vm = pr.find(W + "vMerge")
                if ri > x.r:
                    _tc_prop(pr, "vMerge", "")
                elif x.rs > 1:
                    _tc_prop(pr, "vMerge", "restart")
                elif vm is not None and vm.get(W + "val") != "restart":
                    pr.remove(vm)  # a stray continuation would join the cell above
                if made or x in sized:
                    e = pr.find(W + "tcW")
                    if e is None:
                        e = docx_format._place(pr, etree.Element(W + "tcW"), docx_format._TCPR)
                    e.attrib.clear()
                    e.attrib.update({W + "w": str(sum(widths[x.c:x.c + x.cs])), W + "type": "dxa"})
                if not len(pr) and not pr.attrib:
                    tc.remove(pr)
                tcs.append(tc)
            old = list(_kids(tr, (W + "tc",)))
            rebuilt = old != tcs
            if rebuilt:
                for tc in old:
                    tc.getparent().remove(tc)
                at = sum(1 for c in tr if c.tag in (W + "tblPrEx", W + "trPr"))
                for i, tc in enumerate(tcs):
                    tr.insert(at + i, tc)
            trpr = tr.find(W + "trPr")
            for tag, v in (("gridBefore", row[0].c if row else 0),
                           ("gridAfter", n - row[-1].c - row[-1].cs if row else 0)):
                cur = int(_val(trpr, W + tag) or 0)
                if cur == v or (tag == "gridAfter" and not cur and not rebuilt):  # a short row may stay implicit
                    continue
                if trpr is None:
                    trpr = etree.Element(W + "trPr")
                    tr.insert(1 if len(tr) and tr[0].tag == W + "tblPrEx" else 0, trpr)
                e = trpr.find(W + tag)
                if not v:
                    trpr.remove(e)
                    continue
                if e is None:
                    e = etree.Element(W + tag)
                    trpr.insert(0 if tag == "gridBefore" else int(trpr.find(W + "gridBefore") is not None), e)
                e.set(W + "val", str(v))
        self._dirty.add(self._doc)

    @staticmethod
    def _tc_empty(tc):
        return (not "".join(_text(p) for p in tc.iter(W + "p")).strip()
                and next(tc.iter(W + "drawing", W + "pict", W + "object", W + "tbl"), None) is None)

    def _blank_tc(self, shape, para_src):
        """Empty w:tc: shape's tcPr (minus gridSpan/vMerge/hMerge) and one empty paragraph shaped like para_src's first
        text paragraph (else its first), with that paragraph's first text run's rPr."""
        tc = etree.Element(W + "tc")
        pr = shape.find(W + "tcPr")
        if pr is not None:
            tc.append(_strip(copy.deepcopy(pr), "gridSpan", "vMerge", "hMerge"))
        paras = list(_kids(para_src, (W + "p",)))
        tc.append(self._new_para(next((p for p in paras if _text(p).strip()), paras[0] if paras else None), ""))
        return tc

    def insert_image(self, ref_id: str, data: bytes, ext: str, width_mm: float | None = None) -> str:
        ref = self._block(self._ids[ref_id])
        try:
            img = Image.from_blob(data)
        except UnrecognizedImageError:
            raise ValueError("unsupported image format") from None
        w_mm, h_mm = img.px_width * 25.4 / 96, img.px_height * 25.4 / 96
        limit = width_mm or self._text_width_mm()
        if w_mm > limit:
            w_mm, h_mm = limit, h_mm * limit / w_mm
        name = self._add_media(data, ext.lower().lstrip(".") or img.ext, img.content_type)
        rid = self._add_rel(RT + "image", posixpath.relpath(name, self._dir))
        drawing = etree.fromstring(_INLINE.format(cx=round(w_mm * _EMU_PER_MM), cy=round(h_mm * _EMU_PER_MM),
                                                  id=self._next_docpr(), rid=rid, name=posixpath.basename(name)))
        first = next((d for d in self._body.iter(W + "drawing") if d.find(f".//{A}blip") is not None), None)
        p = self._new_para(self._block(first) if first is not None else self._body_template(), "")
        p.find(W + "r").append(drawing)
        ref.addnext(p)
        self._dirty.add(self._doc)
        return self._id(drawing, "i")

    def _text_width_mm(self):
        """Text width of the document's last section (page width minus side margins)."""
        sect = self._body.find(W + "sectPr")
        size = sect.find(W + "pgSz") if sect is not None else None
        mar = sect.find(W + "pgMar") if sect is not None else None
        if size is None or mar is None:
            return 160.0
        twips = int(size.get(W + "w", 0)) - int(mar.get(W + "left", 0)) - int(mar.get(W + "right", 0))
        return twips * 25.4 / 1440 if twips > 0 else 160.0

    # ---- formats (spec §8; implemented in app/docx_format.py) ----------------------------------------------

    def get_format(self, para_id: str) -> dict:
        return docx_format.get_format(self, para_id)

    def derive_format(self, fmt: dict, changes: dict) -> dict:
        return docx_format.derive_format(self, fmt, changes)

    def apply_format(self, para_ids: list[str], fmt: dict, keep_numbering: bool = False, runs: dict | None = None) -> None:
        docx_format.apply_format(self, para_ids, fmt, keep_numbering, runs)

    def get_cell_format(self, cell_id: str) -> dict:
        return docx_format.get_cell_format(self, cell_id)

    def apply_cell_format(self, cell_ids: list[str], cell_fmt: dict, parts, keep_numbering: bool = True) -> None:
        docx_format.apply_cell_format(self, cell_ids, cell_fmt, parts, keep_numbering)

    # ---- copying from another document ------------------------------------------------------------------

    def _copy_from(self, src, el):
        """Deep copy of src's paragraph/table/image with styles, numbering and images remapped into this doc."""
        if el.tag == W + "drawing":  # an image block alone, in a paragraph shaped like its own
            new = etree.Element(W + "p")
            ppr, rpr = src._block(el).find(W + "pPr"), next(el.iterancestors(W + "r")).find(W + "rPr")
            if ppr is not None:
                new.append(copy.deepcopy(ppr))
            run = etree.SubElement(new, W + "r")
            if rpr is not None:
                run.append(copy.deepcopy(rpr))
            run.append(copy.deepcopy(el))
        elif el.tag in (W + "p", W + "tbl"):
            new = copy.deepcopy(el)
            if el.tag == W + "p":  # its pictures are image blocks of their own and get copied as such
                for u in {_unit(d) for d in self._drawings(new)}:
                    u.getparent().remove(u)
        else:
            raise ValueError("copy source must be a paragraph, table or image")
        for e in list(new.iter(*_COPY_DROP)):
            e.getparent().remove(e)
        self._remap_rels(src, new)
        for e in new.iter(W + "pStyle", W + "rStyle", W + "tblStyle"):
            e.set(W + "val", self._import_style(src, e.get(W + "val")))
        for e in new.iter(W + "numId"):
            if e.get(W + "val") not in (None, "0"):
                e.set(W + "val", self._import_num(src, e.get(W + "val")))
        _drop_ids(new)
        n = self._next_docpr()
        for e in new.iter(WP + "docPr"):
            e.set("id", str(n))
            n += 1
        return new

    def _remap_rels(self, src, new):
        """Re-point r:* attributes at copied relationships; drop what holds a relationship we don't copy."""
        def copyable(rid):
            rel = src._rels.get(rid)
            return rel is not None and rel.get("Type", "").rsplit("/", 1)[-1] in ("image", "hyperlink")

        doomed = []
        for e in new.iter(etree.Element):
            if e.tag != W + "hyperlink" and any(k.startswith(R) and not copyable(v) for k, v in e.attrib.items()):
                # ponytail: OLE objects, charts, diagrams, ActiveX and alt-chunks are not copied - the whole
                # drawing/shape holding the reference is dropped. Copy their parts + rels to lift this.
                doomed.append(_unit(e))
        for e in doomed:
            if e.getparent() is not None:
                e.getparent().remove(e)
        for e in new.iter(etree.Element):
            for k, v in list(e.attrib.items()):
                if k.startswith(R):
                    rid = self._import_rel(src, v) if copyable(v) else None
                    if rid:
                        e.set(k, rid)
                    else:
                        del e.attrib[k]  # only a hyperlink to a non-copyable target gets here

    def _import_rel(self, src, rid):
        key = (src, "rel", rid)
        if key not in self._memo:
            rel = src._rels[rid]
            if rel.get("TargetMode") == "External":
                self._memo[key] = self._add_rel(rel.get("Type"), rel.get("Target"), external=True)
            else:
                name = self._resolve(src._dir, rel.get("Target"))
                ext = posixpath.splitext(name)[1][1:]
                media = self._add_media(src.media(name), ext, src._content_type(name) or f"image/{ext.lower()}")
                self._memo[key] = self._add_rel(rel.get("Type"), posixpath.relpath(media, self._dir))
        return self._memo[key]

    def _import_style(self, src, sid):
        """Target id for src style `sid`: a same-type same-name target style, else a copy (with its references)."""
        key = (src, "style", sid)
        if key in self._memo:
            return self._memo[key]
        st = src._styles.get(sid)
        if st is None:
            return sid
        name = (_val(st, W + "name") or "").lower()
        same = next((k for k, s in self._styles.items() if name and s.get(W + "type") == st.get(W + "type")
                     and (_val(s, W + "name") or "").lower() == name), None)
        if same is not None:
            self._memo[key] = same
            return same
        new_id, n = sid, 1
        while new_id in self._styles:
            new_id, n = f"{sid}_{n}", n + 1
        self._memo[key] = new_id
        c = copy.deepcopy(st)
        c.set(W + "styleId", new_id)
        c.attrib.pop(W + "default", None)
        self._styles[new_id] = c
        self._sub_part("styles", create=True).append(c)
        self._dirty.add(self._sub["styles"])
        for e in c.iter(W + "basedOn", W + "link", W + "next"):
            e.set(W + "val", self._import_style(src, e.get(W + "val")))
        for e in c.iter(W + "numId"):
            if e.get(W + "val") not in (None, "0"):
                e.set(W + "val", self._import_num(src, e.get(W + "val")))
        return new_id

    def _import_num(self, src, num_id):
        """Copy src's w:num (and its abstractNum, once per src abstractNum) under new ids; '0' if unresolvable."""
        key = (src, "num", num_id)
        if key in self._memo:
            return self._memo[key]
        num = src._nums.get(num_id)
        absn = src._abstracts.get(_val(num, W + "abstractNumId")) if num is not None else None
        if absn is None:
            return "0"
        root = self._sub_part("numbering", create=True)
        self._dirty.add(self._sub["numbering"])
        new_num = self._memo[key] = str(max((int(k) for k in self._nums if k.isdigit()), default=0) + 1)
        akey = (src, "abstract", absn.get(W + "abstractNumId"))
        if akey not in self._memo:
            new_abs = self._memo[akey] = str(max((int(k) for k in self._abstracts if k.isdigit()), default=-1) + 1)
            a = copy.deepcopy(absn)
            a.set(W + "abstractNumId", new_abs)
            # ponytail: picture bullets (numPicBullet) aren't copied; such levels fall back to their text bullet.
            # Level->style back-links go too: numbering is driven by the paragraph/style numPr.
            _strip(a, "lvlPicBulletId", "styleLink", "pStyle")
            if a.find(W + "nsid") is not None:
                a.find(W + "nsid").set(W + "val", secrets.token_hex(4).upper())  # Word keys lists by nsid
            self._abstracts[new_abs] = a
            _add_num_def(root, a)
            for e in a.iter(W + "numStyleLink"):
                e.set(W + "val", self._import_style(src, e.get(W + "val")))
        n = copy.deepcopy(num)
        n.set(W + "numId", new_num)
        n.find(W + "abstractNumId").set(W + "val", self._memo[akey])
        self._nums[new_num] = n
        _add_num_def(root, n)
        return new_num


from app import docx_format  # noqa: E402 - at the bottom: docx_format imports this module's helpers
