"""HWPX adapter (spec §0, §2): block tree view of a .hwpx plus lossless, minimal edits.

The original zip is kept as-is; only touched XML members are re-serialized (lxml, original XML
declaration prepended), everything else is copied with its original ZipInfo."""
import copy
import io
import mimetypes
import random
import re
import threading
import zipfile
import zlib

from lxml import etree
from PIL import Image

from app import block_ids
from app import hwpx_layout
from app import table_grid as grid
from app import zip_guard
from app.hwpx_format import FormatMixin
from app.hwpx_struct import StructMixin
from app.textdiff import redistribute

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
NS = {"hp": HP, "hh": HH, "hc": HC}
HEADER, HPF = "Contents/header.xml", "Contents/content.hpf"
SECTION_RE = re.compile(r"Contents/section(\d+)\.xml")
# 패키지 XML 은 엔티티를 펼치지 않고 네트워크를 끈 파서로 — lxml 버전 기본값에 기대지 않는다(spec_왕복_어댑터 ② §1 「비신뢰 패키지 한도」).
# 파서는 스레드마다 따로: lxml 파서 객체를 스레드끼리 나눠 쓰면 병렬 검증 단계가 같은 바이트를 동시에 열 때 거짓 구문 오류가 난다
# (newfilemanager-6e 가 docx 같은 꼴에서 실측, 2026-11-08 — references/OWPML_스키마.md 「검사 도구 사실」).
_LOCAL = threading.local()


def _parser():
    p = getattr(_LOCAL, "parser", None)
    if p is None:
        p = _LOCAL.parser = etree.XMLParser(resolve_entities=False, no_network=True)
    return p


def _p(tag):
    return f"{{{HP}}}{tag}"


def _h(tag):
    return f"{{{HH}}}{tag}"


P, RUN, T, TBL, PIC, TR, TC = map(_p, ["p", "run", "t", "tbl", "pic", "tr", "tc"])
SUBLIST, CTRL, CAPTION, LINESEG, TAB, BREAK = map(_p, ["subList", "ctrl", "caption", "linesegarray", "tab", "lineBreak"])
AUTONUM_EL, CELLADDR, CELLSPAN = map(_p, ["autoNum", "cellAddr", "cellSpan"])
PREFIX = {P: "p", TBL: "t", TC: "c", PIC: "i"}
SPECIAL = {TAB: "\t", BREAK: "\u2028", _p("fwSpace"): " ", _p("nbSpace"): " ", _p("hyphen"): "-"}
OBJECTS = frozenset(map(_p, ["tbl", "pic", "ole", "container", "equation", "line", "rect", "ellipse", "arc",
                            "polygon", "curve", "connectLine", "textart", "chart", "video"]))
AUTONUM = {"PICTURE": "figure", "TABLE": "table", "EQUATION": "equation"}
# 새로 넣는 탭 — OWPML 은 type 필수(LEFT…·leader LineType2). 한글 2020 은 LEFT/NONE 을 제 숫자 0/0(왼쪽·채움 없음)으로 읽고, 폭은
# 조판 때 다시 잰다(references/OWPML_스키마.md). 속성 없는 <hp:tab/> 은 OWPML 위반(spec_owpml_편집 ② §1 검사가 찾음).
NEW_TAB = {"width": "4000", "leader": "NONE", "type": "LEFT"}

# header definition kind -> its list element under hh:refList (listed in schema order)
DEFS = {"borderFill": "borderFills", "charPr": "charProperties", "tabPr": "tabProperties",
        "numbering": "numberings", "bullet": "bullets", "paraPr": "paraProperties", "style": "styles"}
REFLIST_ORDER = ["fontfaces", "borderFills", "charProperties", "tabProperties", "numberings", "bullets",
                 "paraProperties", "styles", "memoProperties", "trackChanges", "trackChangeAuthors"]
ONE_BASED = {"borderFill", "numbering", "bullet"}
REF_ATTRS = {"charPrIDRef": "charPr", "paraPrIDRef": "paraPr", "styleIDRef": "style",
             "charStyleIDRef": "style", "borderFillIDRef": "borderFill", "tabPrIDRef": "tabPr"}
FONT_LANGS = {"hangul": "HANGUL", "latin": "LATIN", "hanja": "HANJA", "japanese": "JAPANESE",
              "other": "OTHER", "symbol": "SYMBOL", "user": "USER"}
# ponytail: section/page-level controls and OLE/chart/video objects are dropped from copied content
# (their binaries/parts aren't carried over); copy Chart/* parts + manifest if charts must survive.
DROP_ON_COPY = tuple(map(_p, ["secPr", "colPr", "header", "footer", "pageNum", "pageHiding",
                              "pageNumCtrl", "newNum", "ole", "chart", "video"]))
# 구역 첫 문단의 hp:ctrl 중 구역에 딸린 것 — 그 위로 줄을 넣으면 secPr 와 함께 새 첫 문단으로 옮긴다(insert_line)
SECTION_CTRL = frozenset(map(_p, ["colPr", "header", "footer", "pageNum", "pageHiding", "pageNumCtrl", "newNum"]))
MARK_RE = re.compile(r"^\s*\d{1,3}(?:-\d{1,3})*\)\s*$")  # superscript footnote mark 「15)」·「15-1)」 (spec_구분_초기화)

PIC_XML = f"""<hp:pic xmlns:hp="{HP}" xmlns:hc="{HC}" id="0" zOrder="0" numberingType="PICTURE"
textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0"
instid="0" reverse="0"><hp:offset x="0" y="0"/><hp:orgSz width="0" height="0"/><hp:curSz width="0" height="0"/>
<hp:flip horizontal="0" vertical="0"/><hp:rotationInfo angle="0" centerX="0" centerY="0" rotateimage="1"/>
<hp:renderingInfo><hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>
<hc:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/><hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>
</hp:renderingInfo><hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="0" y="0"/><hc:pt2 x="0" y="0"/><hc:pt3 x="0" y="0"/>
</hp:imgRect><hp:imgClip left="0" right="0" top="0" bottom="0"/><hp:inMargin left="0" right="0" top="0" bottom="0"/>
<hc:img binaryItemIDRef="" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/><hp:effects/>
<hp:sz width="0" widthRelTo="ABSOLUTE" height="0" heightRelTo="ABSOLUTE" protect="0"/>
<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA"
horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>
<hp:outMargin left="0" right="0" top="0" bottom="0"/></hp:pic>""".replace("\n", " ").replace("> <", "><")


def _sig(el):
    """Definition identity: canonical XML without the id attribute."""
    c = copy.deepcopy(el)
    c.attrib.pop("id", None)
    return etree.tostring(c, method="c14n", exclusive=True)


def _fmt_num(n, fmt):
    if fmt == "DIGIT":
        return str(n)
    table = {"CIRCLED_DIGIT": "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳", "HANGUL_SYLLABLE": "가나다라마바사아자차카타파하",
             "LATIN_SMALL": "abcdefghijklmnopqrstuvwxyz", "LATIN_CAPITAL": "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}.get(fmt)
    return table[n - 1] if table and 1 <= n <= len(table) else None  # unknown format -> label None


def _remove(el):
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


class HwpxDoc(FormatMixin, StructMixin):  # StructMixin: 구조·서식 편집(spec_owpml_편집 ② §2)
    format = "hwpx"

    def __init__(self, data: bytes):
        self._data = data
        self._zip = zipfile.ZipFile(io.BytesIO(data))
        zip_guard.check(self._zip)
        self._infos = {zi.filename: zi for zi in self._zip.infolist()}
        self._roots, self._decl, self._cr = {}, {}, {}
        sections = sorted((n for n in self._infos if SECTION_RE.fullmatch(n)),
                          key=lambda n: int(SECTION_RE.fullmatch(n).group(1)))
        for name in [HEADER, HPF, *sections]:
            raw = zip_guard.read_xml(self._zip, name)  # 조각 읽기 + 이름과 무관한 XML 상한(② §1 「비신뢰 패키지 한도」)
            m = re.match(rb"\s*<\?xml[^>]*\?>", raw)
            self._decl[name] = m.group(0) if m else b""
            # XML parsing turns raw CR into LF; protect CRs as char refs and restore them on save
            self._cr[name] = b"&#13;" not in raw
            self._roots[name] = etree.fromstring(raw.replace(b"\r", b"&#13;") if self._cr[name] else raw, _parser())
        self._sections = [self._roots[n] for n in sections]
        self._name_of = {r: n for n, r in self._roots.items()}
        self._dirty, self._new_members = set(), {}
        self._blocks_cache = None   # blocks() 결과 — 고치면(_mark) 버림
        self._ids, self._rev, self._n = {}, {}, 0
        self._an_val, self._num_ctr, self._an_ctr, self._sigs, self._summ = {}, {}, {}, {}, {}
        self._reflist = self._roots[HEADER].find(_h("refList"))
        self._defs = {}
        for kind, lst in DEFS.items():
            c = self._reflist.find(_h(lst))
            self._defs[kind] = {d.get("id"): d for d in (c.iterchildren(_h(kind)) if c is not None else ())}
        self._hpf = self._roots[HPF]
        self._items = {i.get("id"): i for i in self._hpf.iter("{*}item")}

    # ---------------------------------------------------------------- ids / bookkeeping
    def _id(self, el):
        i = self._rev.get(el)
        if i is None:
            self._n += 1
            i = f"{PREFIX[el.tag]}{self._n}"
            self._rev[el], self._ids[i] = i, el
        return i

    def id_state(self) -> dict:
        """블록 id 자리표 — save() 한 바이트를 다시 열어 adopt_ids 하면 같은 id(작업 저장, spec_작업 ② §5)."""
        return block_ids.state(self._roots, self._rev, self._n)

    def adopt_ids(self, state) -> bool:
        """막 연 문서에 id_state 를 되붙인다 — 트리가 다르면 False(id 는 새로 붙음)."""
        got = block_ids.adopt(self._roots.get, state)
        if got is None:
            return False
        self._ids, self._rev, self._n = got
        self._blocks_cache = None
        return True

    def _mark(self, name):
        """부분 name 을 고쳤다고 표시 — 저장 때 다시 쓰고, blocks() 캐시를 버린다(고치는 길은 모두 여기를 지난다)."""
        self._dirty.add(name)
        self._blocks_cache = None

    def _touch(self, el):
        name = self._name_of.get(el.getroottree().getroot())
        if name:
            self._mark(name)

    def _host(self, el):
        """The hp:p a block lives in (a table/picture is anchored in a run of a paragraph)."""
        if el.tag == P:
            return el
        if el.tag in (TBL, PIC):
            return el.getparent().getparent()
        raise ValueError("ref must be a paragraph, table or image block")

    # ---------------------------------------------------------------- reading
    def blocks(self) -> list[dict]:
        """문서 전체 블록. 고치기 전까지는 같은 열을 다시 돌려준다(캐시 — 고치는 메서드는 모두 _mark 를 지나 비움. 연구개발계획서 양식
        499 KB 도 한 번 읽기 0.6~1 s 인데 구분 초기화가 차례마다 되풀이해 읽음, spec_구분_초기화 ② §4). 받은 쪽은 사전을 고치지 말 것."""
        if self._blocks_cache is None:
            self._num_ctr, self._an_ctr = {}, {}
            self._blocks_cache = hwpx_layout.annotate(self, [b for sec in self._sections for b in self._list_blocks(sec)])
        return self._blocks_cache

    def table_block(self, table_id: str):
        """표 하나의 블록을 지금 XML 에서 다시 읽는다 — blocks() 의 그 항목과 같은 키(쪽·쪽 시작 키는 바깥에서 붙이므로 없음). 표 편집 뒤 문서 전체를
        다시 읽지 않게(연구계획서 47MB: blocks() 2.9 s → 0.02 s, spec_매직브러쉬 ② §5). 표 안 자동 번호 슬롯은 전에 센 문서 순서 값을 지킨다(_keep_an)."""
        tbl = self._ids.get(table_id)
        if tbl is None or tbl.tag != TBL:
            return None
        self._keep_an = True
        try:
            b = self._table(tbl)
        finally:
            self._keep_an = False
        hwpx_layout._walk(self, [b])
        return b

    def _list_blocks(self, parent, caption_of=None):
        return [b for p in parent.iterchildren(P) for b in self._para_blocks(p, caption_of)]

    def _para_blocks(self, p, caption_of):
        for a in self._slots(p):
            if a.tag == AUTONUM_EL and not getattr(self, "_keep_an", False):  # running value per numType in document order
                k = a.get("numType")
                self._an_ctr[k] = self._an_ctr.get(k, 0) + 1
                self._an_val[a] = str(self._an_ctr[k])
        text = self._text(p)
        objs = [o for r in p.iterchildren(RUN) for o in r.iterchildren(TBL, PIC)]
        out = [self._para_dict(p, text, caption_of)] if text.strip() or not objs else []
        inline = [o for o in objs if (pos := o.find(_p("pos"))) is not None and pos.get("treatAsChar") == "1"]
        row = None
        for o in objs:
            oid = self._id(o)
            caps = [b for c in o.iterchildren(CAPTION) for s in c.iterchildren(SUBLIST)
                    for b in self._list_blocks(s, oid)]
            blk = self._table(o) if o.tag == TBL else self._image(o)
            if len(inline) > 1 and o in inline:  # 글자처럼 취급한 개체가 한 문단에 둘 이상 — 한글은 한 줄에 나란히 놓는다
                blk["inlineRow"] = row = row or oid
            out.append(blk)
            out += caps
        return out

    def _para_dict(self, p, text, caption_of):
        h = self._heading(p)
        htype = h.get("type") if h is not None else "NONE"
        style = self._defs["style"].get(p.get("styleIDRef"))
        return {"id": self._id(p), "type": "paragraph", "text": text,
                "style": style.get("name") if style is not None else None,
                "outlineLevel": int(h.get("level", 0)) + 1 if htype == "OUTLINE" else None,
                "list": self._list_info(h) if htype in ("BULLET", "NUMBER") else None,
                "bold": self._bold([p]),
                "autoNum": next((AUTONUM[a.get("numType")] for a in self._slots(p) if a.tag == AUTONUM_EL), None),
                "captionOf": caption_of,
                "format": self._summary(p.get("paraPrIDRef"), self._char_id(p)), "runs": self._runs(p),
                **({"endSizePt": e} if (e := self._end_size(p)) else {})}

    def _end_size(self, p):
        """문단 끝 빈 런(글 없는 hp:run)의 글자 크기(pt)가 글보다 크면 그 크기 — 한글은 문단 끝 표시도 마지막 줄 높이에 넣는다
        (보이는 글 8pt + 끝 빈 런 10pt → 줄 높이 10pt × 줄 간격, lineseg 실측 — spec_hwpx_웹편집 ② §3-4). 아니면 None(읽기만)."""
        runs = list(p.iterchildren(RUN))
        if not runs or any(c.tag != T or c.text for c in runs[-1]):
            return None
        size = lambda r: int(self._defs["charPr"][r.get("charPrIDRef")].get("height", 1000)) / 100 \
            if r.get("charPrIDRef") in self._defs["charPr"] else 0  # noqa: E731
        text = [size(r) for r in runs if any(t.text for t in r.iter(T))]
        return size(runs[-1]) if text and size(runs[-1]) > max(text) else None

    def _table(self, tbl):
        cells = []
        for r, tr in enumerate(tbl.iterchildren(TR)):
            for c, tc in enumerate(tr.iterchildren(TC)):
                addr, span, sub = tc.find(CELLADDR), tc.find(CELLSPAN), tc.find(SUBLIST)
                ps = self._text_paras(sub) if sub is not None else []
                # ponytail: without cellAddr the column is the index in the row (ignores spans); Hancom always writes it
                cells.append({"id": self._id(tc),
                              "row": int(addr.get("rowAddr", r)) if addr is not None else r,
                              "col": int(addr.get("colAddr", c)) if addr is not None else c,
                              "rowSpan": int(span.get("rowSpan", 1)) if span is not None else 1,
                              "colSpan": int(span.get("colSpan", 1)) if span is not None else 1,
                              "shaded": self._shaded(tc.get("borderFillIDRef")), "bold": self._bold(ps),
                              "bf": tc.get("borderFillIDRef"),
                              "blocks": self._list_blocks(sub) if sub is not None else [],
                              "text": "\n".join(self._text(p) for p in ps), **self._cell_look(tc)})
        # cell lines: cells carry only their borderFill id (bf); the lines go once per table (hundreds of cells share one)
        om = tbl.find(_p("outMargin"))  # 표 바깥 여백(한글 표 속성) — 웹이 표 위·아래 간격에 쓴다(연구개발계획서 양식 0.5mm·일부 0, spec_hwpx_웹편집 ② §3-5)
        return {"id": self._id(tbl), "type": "table", "nRows": int(tbl.get("rowCnt", 0)),
                "nCols": int(tbl.get("colCnt", 0)), "cells": cells,
                "outMarginMm": {k: round(int(om.get(a, 0)) * 25.4 / 7200, 2) for k, a in
                                (("t", "top"), ("b", "bottom"), ("l", "left"), ("r", "right"))} if om is not None else None,
                "borderFills": {i: self._border_lines(i) for i in dict.fromkeys(c["bf"] for c in cells) if i is not None}}

    def _image(self, pic):
        img, sz = pic.find(f"{{{HC}}}img"), pic.find(_p("sz"))
        href = self._href(img.get("binaryItemIDRef")) if img is not None else None

        def mm(attr):
            return round(int(sz.get(attr)) * 25.4 / 7200, 1) if sz is not None and sz.get(attr) else None
        return {"id": self._id(pic), "type": "image", "media": href if self._has(href) else None,
                "widthMm": mm("width"), "heightMm": mm("height")}

    def _slots(self, p):
        """Text slots in order: every hp:t, plus each figure/table/equation autoNum control."""
        return [s for r in p.iterchildren(RUN) for s in self._run_slots(r)]

    def _run_slots(self, r):
        out = []
        for c in r:
            if c.tag == T:
                out.append(c)
            elif c.tag == CTRL:
                out += [a for a in c.iterchildren(AUTONUM_EL) if a.get("numType") in AUTONUM]
        return out

    def _runs(self, p):
        """spec_서식 §1 `runs`: text per character look (neighbours with the same look merged), None for one look."""
        out = []
        for r in p.iterchildren(RUN):
            text = "".join(self._slot_text(s) for s in self._run_slots(r))
            if not text:
                continue
            cid = r.get("charPrIDRef")
            if cid not in self._summ:  # str keys beside FormatMixin's (paraPr, charPr) tuples
                self._summ[cid] = self._char_summary(self._defs["charPr"].get(cid))
            if out and out[-1]["format"] == self._summ[cid]:
                out[-1]["text"] += text
            else:
                out.append({"text": text, "format": dict(self._summ[cid])})
        return out if len(out) > 1 else None

    def _slot_text(self, s):
        if s.tag == AUTONUM_EL:
            return self._an_val.get(s, s.get("num", ""))
        return (s.text or "") + "".join(SPECIAL.get(c.tag, "") + (c.tail or "") for c in s)

    def _text(self, p):
        return "".join(self._slot_text(s) for s in self._slots(p))

    def _has_object(self, p):
        return any(o.tag in OBJECTS for r in p.iterchildren(RUN) for o in r)

    def _text_paras(self, sub):
        return [p for p in sub.iterchildren(P) if not self._has_object(p) or self._text(p).strip()]

    def _heading(self, p):
        pp = self._defs["paraPr"].get(p.get("paraPrIDRef"))
        return pp.find(_h("heading")) if pp is not None else None

    def _list_info(self, h):
        level = int(h.get("level", 0)) + 1
        if h.get("type") == "BULLET":
            b = self._defs["bullet"].get(h.get("idRef"))
            return {"kind": "bullet", "level": level, "label": b.get("char") if b is not None else None}
        num = self._defs["numbering"].get(h.get("idRef"))
        heads = {ph.get("level"): ph for ph in num.iterchildren(_h("paraHead"))} if num is not None else {}
        head = heads.get(str(level))
        if head is None:
            return {"kind": "number", "level": level, "label": None, "numFmt": None}
        # ponytail: counters run per numbering id in document order; hp:newNum restarts are ignored
        ctr = self._num_ctr.setdefault(h.get("idRef"), {})
        ctr[level] = ctr.get(level, int(head.get("start", 1)) - 1) + 1
        for k in [k for k in ctr if k > level]:
            del ctr[k]
        parts = {}
        for m in re.finditer(r"\^(\d+)", head.text or ""):
            hk = heads.get(m.group(1))
            parts[m.group(0)] = _fmt_num(ctr.get(int(m.group(1)), 1), hk.get("numFormat") if hk is not None else None)
        label = None if None in parts.values() else re.sub(r"\^\d+", lambda m: parts[m.group(0)], head.text or "")
        return {"kind": "number", "level": level, "label": label or None, "numFmt": head.get("numFormat")}

    def _bold(self, ps):
        runs = [r for p in ps for r in p.iterchildren(RUN)
                if any(self._slot_text(t).strip() for t in r.iterchildren(T))]
        return bool(runs) and all(self._is_bold(r.get("charPrIDRef")) for r in runs)

    def _is_bold(self, cid):
        c = self._defs["charPr"].get(cid)
        return c is not None and c.find(_h("bold")) is not None

    def _shaded(self, bf_id):
        return self._fill(bf_id) not in (None, "#FFFFFF")

    def _first_run(self, p):
        """First run with text, else the first run (None if the paragraph has no runs)."""
        runs = list(p.iterchildren(RUN))
        return next((r for r in runs if any(self._slot_text(t) for t in r.iterchildren(T))), runs[0] if runs else None)

    def _char_id(self, p):
        r = self._first_run(p)
        return r.get("charPrIDRef", "0") if r is not None else "0"

    # ---------------------------------------------------------------- media
    def _href(self, item_id):
        item = self._items.get(item_id)
        return item.get("href") if item is not None else None

    def _has(self, name):
        return name in self._new_members or name in self._infos

    def media(self, name: str) -> bytes:
        return self._new_members[name] if name in self._new_members else zip_guard.read(self._zip, name)

    def _add_bin(self, data, ext, media_type):
        """Manifest item id holding these bytes: an existing identical one, else a new BinData member."""
        crc = zlib.crc32(data)
        for iid, item in self._items.items():
            href, zi = item.get("href"), self._infos.get(item.get("href"))
            if (self._new_members.get(href) == data
                    or zi and zi.CRC == crc and zi.file_size == len(data) and zip_guard.read(self._zip, href) == data):
                return iid
        names = [*self._items, *self._infos, *self._new_members]
        n = 1 + max((int(m) for s in names for m in re.findall(r"image(\d+)", s)), default=0)
        iid, href = f"image{n}", f"BinData/image{n}.{ext}"
        manifest = next(self._hpf.iter("{*}manifest"))
        item = etree.SubElement(manifest, f"{{{etree.QName(manifest).namespace}}}item",
                                {"id": iid, "href": href, "media-type": media_type, "isEmbeded": "1"})
        self._items[iid], self._new_members[href] = item, data
        self._mark(HPF)
        return iid

    # ---------------------------------------------------------------- set_text
    def set_text(self, block_id: str, text: str, templates=None) -> None:
        """`templates` (cells): per line, a paragraph id whose shape a NEW paragraph for that line copies (None = the cell's first)."""
        el = self._ids[block_id]
        if el.tag == TC:
            changed = self._set_cell(el, text, templates or ())
        elif el.tag == P:
            changed = self._set_para(el, text.replace("\n", " "))
        else:
            raise ValueError(f"{block_id} is not a paragraph or cell")
        if changed:
            self._touch(el)

    def _set_para(self, p, text):
        slots = self._slots(p)
        if not slots:
            runs = p.findall(RUN)
            run = runs[-1] if runs else p.makeelement(RUN, {"charPrIDRef": "0"})
            if not runs:
                p.insert(0, run)
            slots = [etree.SubElement(run, T)]
        old = [self._slot_text(s) for s in slots]
        new = redistribute(old, text)
        if new == old:
            return False
        for s, o, n in zip(slots, old, new):
            if o == n:
                continue
            if s.tag == T:
                self._write_t(s, n)
            else:  # autoNum slot edited: replace the control with its literal text
                ctrl = s.getparent()
                if n:
                    t = ctrl.makeelement(T, {})
                    ctrl.addnext(t)
                    self._write_t(t, n)
                ctrl.remove(s)
                if len(ctrl) == 0:
                    _remove(ctrl)
        for ls in p.findall(LINESEG):
            p.remove(ls)
        return True

    def _write_t(self, t, text):
        """Rewrite an hp:t; preserve tabs' attributes and explicit line breaks."""
        tabs = [c for c in t if c.tag == TAB]
        for c in list(t):
            t.remove(c)
        parts = re.split(r"([\t\u2028])", text)
        t.text = parts[0] or None
        for sep, part in zip(parts[1::2], parts[2::2]):
            old = tabs.pop(0) if sep == "\t" and tabs else None
            attrs = dict(old.attrib) if old is not None else dict(NEW_TAB) if sep == "\t" else {}
            etree.SubElement(t, TAB if sep == "\t" else BREAK, attrs).tail = part or None

    def _set_cell(self, tc, text, templates=()):
        sub = tc.find(SUBLIST)
        if next(sub.iter(TBL), None) is not None:
            raise ValueError("cell contains a nested table")
        all_p, ps, lines = list(sub.iterchildren(P)), self._text_paras(sub), text.split("\n")
        if not ps and not text:
            return False
        tpl, last = (ps or all_p)[0], (ps or all_p)[-1]
        changed = len(ps) != len(lines)
        while len(ps) < len(lines):
            own = self._ids.get(templates[len(ps)]) if len(ps) < len(templates) and templates[len(ps)] else None
            new = self._new_para(own if own is not None and own.tag == P else tpl, "")
            last.addnext(new)
            ps.append(new)
            last = new
        for extra in ps[len(lines):]:
            if self._has_object(extra):  # 개체가 있는 초과 문단은 글자만 비운다.
                self._set_para(extra, "")
            else:
                sub.remove(extra)
        for p, line in zip(ps, lines):
            changed |= self._set_para(p, line)
        return changed

    def _new_para(self, tpl, text):
        """Paragraph with tpl's paragraph attributes and the char shape of its first text run."""
        p = tpl.makeelement(P, tpl.attrib)
        run = etree.SubElement(p, RUN, {"charPrIDRef": self._char_id(tpl)})
        self._write_t(etree.SubElement(run, T), text)
        return p

    # ---------------------------------------------------------------- insert_after / copy
    def insert_after(self, ref_id: str, items: list[dict], src=None) -> list[str]:
        if src is not None and not isinstance(src, HwpxDoc):
            raise ValueError("copy source must be an HwpxDoc")
        anchor = self._host(self._ids[ref_id])
        cache, out = {}, []
        for it in items:
            if it["kind"] == "copy":
                new, block = self._copy(src or self, it["srcId"], cache)
            else:
                tpl = self._host(self._ids[it["templateId"]]) if it.get("templateId") else self._default_template()
                new = block = self._new_para(tpl, it.get("text", "").replace("\n", " "))
                if not it.get("keepNumbering", it["kind"] != "heading"):
                    self._no_numbering(new)
            anchor.addnext(new)
            anchor = new
            self._touch(new)
            out.append(self._id(block))
        return out

    def insert_line(self, ref_id: str, text: str = "", before: bool = False, after_id: str | None = None) -> str:
        """ref 문단과 같은 문단·글자 모양의 새 문단 하나를 ref 위/아래에(문단 줄 추가 — spec_웹UI ② UI-010) -> 새 id.
        after_id = 아래로 넣을 자리(그 블록 바로 뒤 — 헤딩 구간 끝, 표·그림이면 그 문단 뒤), 없으면 ref 바로 뒤. 서식은 늘 ref.
        쪽·단 나눔은 위로 넣으면 새 문단이 넘겨받고 아래로 넣으면 새 문단에 안 붙인다. 구역 첫 문단(secPr) 위로 넣으면 구역 설정과
        그 문단의 구역 제어(단·머리말·꼬리말·쪽 번호)를 새 첫 문단으로 옮긴다."""
        ref = self._ids[ref_id]
        if ref.tag != P:
            raise ValueError("문단이 아닙니다")
        new = self._new_para(ref, text.replace("\n", " "))
        for a in ("pageBreak", "columnBreak"):
            if (ref if before else new).get(a) not in (None, "0"):
                (ref if before else new).set(a, "0")
        if before and next(ref.iter(_p("secPr")), None) is not None:
            run = new.find(RUN)
            parts = [x for r in ref.iterchildren(RUN) for x in r
                     if x.tag == _p("secPr") or x.tag == CTRL and len(x) and all(c.tag in SECTION_CTRL for c in x)]
            for i, x in enumerate(parts):
                run.insert(i, x)  # lxml: 옮김
        (ref.addprevious if before else self._host(self._ids[after_id or ref_id]).addnext)(new)
        self._touch(new)
        return self._id(new)

    def _default_template(self):
        """First body paragraph with text (top level first, then anywhere, e.g. inside cells)."""
        for deep in (False, True):
            for sec in self._sections:
                for p in sec.iter(P) if deep else sec.iterchildren(P):
                    h = self._heading(p)
                    if (h is None or h.get("type") == "NONE") and self._text(p).strip():
                        return p
        return next(self._sections[0].iter(P))

    def _no_numbering(self, p):
        h = self._heading(p)
        if h is None or h.get("type") == "NONE":
            return
        pp = copy.deepcopy(h.getparent())
        hh = pp.find(_h("heading"))
        hh.set("type", "NONE")
        hh.set("idRef", "0")
        p.set("paraPrIDRef", self._add_def("paraPr", pp))

    def _copy(self, src, sid, cache):
        """Deep copy of a src paragraph (without its table/picture blocks) or table/picture (in a new
        paragraph), with header/BinData references remapped into this document."""
        el = src._ids[sid]
        if el.tag == P:
            new = block = copy.deepcopy(el)
            for r in new.iterchildren(RUN):
                for o in r.findall(TBL) + r.findall(PIC):  # those are their own blocks
                    r.remove(o)
        elif el.tag in (TBL, PIC):
            block = copy.deepcopy(el)
            new = self._obj_para(el, block)
        else:
            raise ValueError(f"cannot copy {sid}")
        for e in list(new.iter(*DROP_ON_COPY, LINESEG)):
            parent = e.getparent()
            parent.remove(e)
            if parent.tag == CTRL and len(parent) == 0:
                _remove(parent)
        if src is not self:
            self._remap(src, new, cache)
        return new, block

    def _obj_para(self, obj, new_obj):
        """New paragraph holding only new_obj, shaped like obj's host paragraph and run."""
        run, host = obj.getparent(), obj.getparent().getparent()
        p = host.makeelement(P, host.attrib)
        r = etree.SubElement(p, RUN, run.attrib)
        r.append(new_obj)
        etree.SubElement(r, T)
        return p

    def _remap(self, src, root, cache):
        for e in root.iter(tag=etree.Element):
            for attr, kind in REF_ATTRS.items():
                v = e.get(attr)
                if v is not None:
                    e.set(attr, self._import(src, kind, v, cache))
            v = e.get("binaryItemIDRef")
            if v is not None:
                e.set("binaryItemIDRef", self._import_bin(src, v, cache))

    def _import(self, src, kind, sid, cache):
        if (kind, sid) not in cache:
            cache[kind, sid] = self._import_def(src, kind, sid, cache)
        return cache[kind, sid]

    def _import_def(self, src, kind, sid, cache):
        d = src._defs[kind].get(sid)
        if d is None:  # e.g. 4294967295 = "none"
            return sid
        if kind == "style":  # a style is identified by its name; reuse the same-named one
            same = next((s for s in self._defs["style"].values() if s.get("name") == d.get("name")), None)
            if same is not None:
                return same.get("id")
        new = copy.deepcopy(d)
        for brush in list(new.iter(f"{{{HC}}}imgBrush")):  # ponytail: image fills not carried over
            _remove(brush)
        self._remap(src, new, cache)
        h = new.find(_h("heading"))
        if kind == "paraPr" and h is not None and h.get("type") in ("BULLET", "NUMBER"):
            h.set("idRef", self._import(src, "bullet" if h.get("type") == "BULLET" else "numbering",
                                        h.get("idRef"), cache))
        fr = new.find(_h("fontRef"))
        if kind == "charPr" and fr is not None:
            for attr, lang in FONT_LANGS.items():
                if fr.get(attr) is not None:
                    fr.set(attr, self._import_font(src, lang, fr.get(attr)))
        nid = self._add_def(kind, new)
        if kind == "style" and self._defs["style"][nid] is new:
            new.set("nextStyleIDRef", nid)  # ponytail: imported style's "next style" becomes itself
        return nid

    def _add_def(self, kind, el):
        """Id of an identical existing definition (XML minus id), else append el with a new id."""
        sigs = self._sigs.get(kind)
        if sigs is None:
            sigs = self._sigs[kind] = {}
            for i, d in self._defs[kind].items():
                sigs.setdefault(_sig(d), i)
        s = _sig(el)
        if s in sigs:
            return sigs[s]
        nid = str(max((int(i) for i in self._defs[kind]), default=0 if kind in ONE_BASED else -1) + 1)
        el.set("id", nid)
        lst = self._container(DEFS[kind])
        lst.append(el)
        lst.set("itemCnt", str(len(lst)))
        self._defs[kind][nid], sigs[s] = el, nid
        self._mark(HEADER)
        return nid

    def _container(self, name):
        c = self._reflist.find(_h(name))
        if c is None:
            c = self._reflist.makeelement(_h(name), {"itemCnt": "0"})
            later = REFLIST_ORDER[REFLIST_ORDER.index(name) + 1:]
            nxt = next((e for e in self._reflist if etree.QName(e).localname in later), None)
            if nxt is not None:
                nxt.addprevious(c)
            else:
                self._reflist.append(c)
        return c

    def _fontface(self, lang):
        ffs = self._reflist.find(_h("fontfaces"))
        return next((f for f in ffs.iterchildren(_h("fontface")) if f.get("lang") == lang), None) if ffs is not None else None

    def _import_font(self, src, lang, fid):
        sface = src._fontface(lang)
        sf = next((f for f in sface.iterchildren(_h("font")) if f.get("id") == fid), None) if sface is not None else None
        return (self._font_id(lang, sf.get("face"), sf) if sf is not None else None) or fid

    def _font_id(self, lang, name, tpl=None):
        """Id of the font named name in lang's fontface, appending it (copy of tpl, else bare TTF) if missing."""
        face = self._fontface(lang)
        if face is None:
            return None
        for f in face.iterchildren(_h("font")):
            if f.get("face") == name:
                return f.get("id")
        nid = str(1 + max((int(f.get("id")) for f in face.iterchildren(_h("font"))), default=-1))
        if tpl is not None:
            new = copy.deepcopy(tpl)
            new.set("id", nid)
        else:
            new = face.makeelement(_h("font"), {"id": nid, "face": name, "type": "TTF", "isEmbedded": "0"})
        face.append(new)
        face.set("fontCnt", str(len(face.findall(_h("font")))))
        self._mark(HEADER)
        return nid

    def _import_bin(self, src, item_id, cache):
        if ("bin", item_id) not in cache:
            href = src._href(item_id)
            if href and src._has(href):
                mt = src._items[item_id].get("media-type") or mimetypes.guess_type(href)[0] or "image/png"
                cache["bin", item_id] = self._add_bin(src.media(href), href.rsplit(".", 1)[-1], mt)
            else:  # ponytail: linked (non-embedded) images keep their item id; copy the manifest item if needed
                cache["bin", item_id] = item_id
        return cache["bin", item_id]

    # ---------------------------------------------------------------- images
    def insert_image(self, ref_id: str, data: bytes, ext: str, width_mm: float | None = None) -> str:
        anchor = self._host(self._ids[ref_id])
        with Image.open(io.BytesIO(data)) as im:
            wpx, hpx = im.size
        ext = ext.lower().lstrip(".")
        iid = self._add_bin(data, ext, mimetypes.guess_type("x." + ext)[0] or f"image/{ext}")
        w, h = wpx * 25.4 / 96, hpx * 25.4 / 96
        limit = width_mm or self._body_width_mm(anchor)
        if w > limit:
            w, h = limit, h * limit / w
        tpl = next((x for sec in self._sections for x in sec.iter(PIC) if x.getparent().tag == RUN), None)
        if tpl is not None:
            pic = copy.deepcopy(tpl)
            for c in pic.findall(CAPTION) + pic.findall(_p("shapeComment")):
                pic.remove(c)
            p = self._obj_para(tpl, pic)
        else:
            pic = etree.fromstring(PIC_XML)
            p = self._new_para(self._default_template(), "")
            p.find(RUN).insert(0, pic)
        self._size_pic(pic, iid, wpx, hpx, w, h)
        anchor.addnext(p)
        self._touch(p)
        return self._id(p.find(RUN).find(PIC))

    def _size_pic(self, pic, iid, wpx, hpx, wmm, hmm):
        W, H = round(wmm * 7200 / 25.4), round(hmm * 7200 / 25.4)  # HWPUNIT = 1/7200 inch
        OW, OH = wpx * 75, hpx * 75  # original size at 96 dpi

        def put(path, **kv):
            e = pic.find(path, NS)
            if e is not None:
                for k, v in kv.items():
                    e.set(k, str(v))
        pic.set("id", str(random.randrange(1, 2**31)))
        pic.set("instid", str(random.randrange(1, 2**31)))
        put("hp:orgSz", width=OW, height=OH)
        put("hp:curSz", width=W, height=H)
        put("hp:sz", width=W, height=H)
        put("hp:imgRect/hc:pt1", x=OW, y=0)
        put("hp:imgRect/hc:pt2", x=OW, y=OH)
        put("hp:imgRect/hc:pt3", x=0, y=OH)
        put("hp:imgClip", left=0, top=0, right=OW, bottom=OH)
        put("hp:imgDim", dimwidth=OW, dimheight=OH)
        put("hp:rotationInfo", centerX=W // 2, centerY=H // 2)
        put("hp:renderingInfo/hc:scaMatrix", e1=f"{W / OW:.6f}", e5=f"{H / OH:.6f}")
        put("hc:img", binaryItemIDRef=iid)
        put("hp:pos", treatAsChar=1, vertOffset=0, horzOffset=0)

    def _body_width_mm(self, p):
        tc = next(p.iterancestors(TC), None)
        if tc is not None:
            sz, m = tc.find(_p("cellSz")), tc.find(_p("cellMargin"))
            w = int(sz.get("width")) - (int(m.get("left", 0)) + int(m.get("right", 0)) if m is not None else 0)
            return w * 25.4 / 7200
        pp = next(p.getroottree().getroot().iter(_p("pagePr")), None)
        if pp is None:
            return 150.0
        m = pp.find(_p("margin"))
        # ponytail: assumes landscape="NARROWLY" means width/height are stored portrait-wise
        w = int(pp.get("height" if pp.get("landscape") == "NARROWLY" else "width"))
        if m is not None:
            w -= int(m.get("left", 0)) + int(m.get("right", 0)) + int(m.get("gutter", 0))
        return w * 25.4 / 7200

    # ---------------------------------------------------------------- append_rows
    def append_rows(self, table_id: str, rows: list[list[str]]) -> list[str]:
        tbl = self._ids[table_id]
        if tbl.tag != TBL:
            raise ValueError(f"{table_id} is not a table")
        last = tbl.findall(TR)[-1]
        cells = last.findall(TC)
        last_row = int(cells[0].find(CELLADDR).get("rowAddr"))
        for tc in (tc for tr in tbl.iterchildren(TR) for tc in tr.iterchildren(TC)):
            r, span = int(tc.find(CELLADDR).get("rowAddr")), int(tc.find(CELLSPAN).get("rowSpan", 1))
            if span > 1 and r <= last_row < r + span:  # last row is part of a multi-row span
                raise ValueError("last row has row-spanning cells")
        if any(len(row) > len(cells) for row in rows):
            raise ValueError("row has more values than the template row has cells")
        if next(last.iter(TBL), None) is not None:
            raise ValueError("template row contains a nested table")
        ids, anchor = [], last
        for i, row in enumerate(rows):
            tr = copy.deepcopy(last)
            anchor.addnext(tr)
            anchor = tr
            for j, tc in enumerate(tr.iterchildren(TC)):
                tc.find(CELLADDR).set("rowAddr", str(last_row + 1 + i))
                for ls in list(tc.iter(LINESEG)):
                    _remove(ls)
                self._set_cell(tc, row[j] if j < len(row) else "")
                ids.append(self._id(tc))
        tbl.set("rowCnt", str(int(tbl.get("rowCnt", 0)) + len(rows)))
        self._touch(tbl)
        return ids

    def insert_rows(self, table_id: str, first: int, last: int, values: list[dict], grow=()) -> list[dict]:
        """Copy rows first..last once per `values` item, right after `last` (spec_표_분류 §5 끼우기). values[k] =
        {cell id: text} for copy k, other cells keep their text; cells from above reaching `last` and the `grow` cell
        ids grow instead of being copied. -> [{cell id: copy's cell id}]; ValueError when a merged cell crosses."""
        tbl = self._ids[table_id]
        if tbl.tag != TBL:
            raise ValueError(f"{table_id} is not a table")
        row = lambda tc: int(tc.find(CELLADDR).get("rowAddr"))
        span = lambda tc: int(tc.find(CELLSPAN).get("rowSpan", 1))
        cells = [tc for tr in tbl.iterchildren(TR) for tc in tr.iterchildren(TC)]
        grow = [tc for tc in cells if row(tc) < first and row(tc) + span(tc) - 1 >= last or self._rev.get(tc) in grow]
        if any(row(tc) < first <= row(tc) + span(tc) - 1 < last or first <= row(tc) <= last < row(tc) + span(tc) - 1
               for tc in cells if tc not in grow):
            raise ValueError("a merged cell crosses the rows to copy")
        trs = [tr for tr in tbl.iterchildren(TR) if (tcs := tr.findall(TC)) and first <= row(tcs[0]) <= last]
        if not trs:
            raise ValueError(f"no rows {first}..{last}")
        d = (last - first + 1) * len(values)
        heights = {}  # row -> height of its one-row cells (merged cells' heights are the sum of their rows)
        for tc in cells:
            if span(tc) == 1 and (sz := tc.find(_p("cellSz"))) is not None:
                heights[row(tc)] = max(heights.get(row(tc), 0), int(sz.get("height", 0)))
        # 복사본을 먼저 다 만든다(글 쓰기까지 — 표에 아직 안 붙임): 여기서 실패하면 표는 그대로(11-03 astra F07 — 전엔 행 주소를 민 뒤 중첩 표 칸에서
        # 실패해 rowAddr 가 [0,1,3] 로 남았음)
        staged = []
        for k, vals in enumerate(values):
            made, pairs = [], []
            for tr in trs:
                cp = copy.deepcopy(tr)
                for o, c in list(zip(tr.iterchildren(TC), cp.iterchildren(TC))):
                    if o in grow:
                        cp.remove(c)
                        continue
                    c.find(CELLADDR).set("rowAddr", str(row(o) + (last - first + 1) * (k + 1)))
                    for ls in list(c.iter(LINESEG)):
                        _remove(ls)
                    oid = self._id(o)
                    if oid in vals:
                        self._set_cell(c, vals[oid])
                    pairs.append((oid, c))
                made.append(cp)
            staged.append((made, pairs))
        zones = [(z, int(z.get("startRowAddr")), int(z.get("endRowAddr")))   # 고치기 전에 해석 — 깨진 값이면 여기서 실패해 표 그대로(astra G20)
                 for zl in tbl.iterchildren(_p("cellzoneList")) for z in zl.iterchildren(_p("cellzone"))]
        for tc in cells:
            if row(tc) > last:
                tc.find(CELLADDR).set("rowAddr", str(row(tc) + d))
        for tc in grow:
            tc.find(CELLSPAN).set("rowSpan", str(span(tc) + d))
            if (sz := tc.find(_p("cellSz"))) is not None and int(sz.get("height", 0)):
                sz.set("height", str(int(sz.get("height")) + sum(heights.get(r, 0) for r in range(first, last + 1)) * len(values)))
            for ls in list(tc.iter(LINESEG)):  # stale layout of the taller cell: Hancom lays it out again
                _remove(ls)
        for z, s, e in zones:
            if s > last:
                z.set("startRowAddr", str(s + d))
            if e > last or (e == last and s < first):
                z.set("endRowAddr", str(e + d))
        out, ref = [], trs[-1]
        for made, pairs in staged:
            for cp in made:
                ref.addnext(cp)
                ref = cp
            out.append({oid: self._id(c) for oid, c in pairs})
        tbl.set("rowCnt", str(int(tbl.get("rowCnt", 0)) + d))
        self._touch(tbl)
        return out

    # ---------------------------------------------------------------- table cell editing (spec_표_편집 ② §2·§3)
    # Each returns grid.result(): {"cell", "new", "removed", "grown", "map"} (cell ids). Grid lines on which no cell
    # starts any more are dropped, as 한글 does (an empty hp:tr makes 한글 fail to save).
    def merge_cells(self, table_id: str, r0: int, c0: int, r1: int, c1: int, keep: str | None = None) -> dict:
        """One cell over rows r0..r1 × columns c0..c1 — the top-left cell, keeping its id, attributes and margins. The
        other cells' paragraphs follow its own top→bottom, left→right (empty cells left out; an empty top-left cell
        gives way to the first filled one). keep = a cell id inside the range: only that cell's paragraphs stay (매직
        브러쉬 규칙 C9 — the same text once, or the one the user chose). borderFill = the top-left cell's with the right
        and bottom lines of the bottom-right cell (한글 셀 합치기). ValueError when a merged cell sticks out of the range
        or `keep` is not inside it."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        heights, widths = self._tsizes(cells, nr, nc)
        tl, br, others = grid.merge(cells, nr, nc, int(r0), int(c0), int(r1), int(c1))
        inside = [tl, *others]
        full = grid.kept(inside, keep, self._id) if keep is not None else [x for x in inside if not self._cell_empty(x.el)]
        if not others:
            return grid.result(self._cid, tl)
        sub = tl.el.find(SUBLIST)
        if full and full[0] is not tl:
            for p in list(sub.iterchildren(P)):
                sub.remove(p)
        for x in others:
            if x in full:
                for p in list(x.el.find(SUBLIST).iterchildren(P)):
                    sub.append(p)
        removed = [self._id(x.el) for x in others]
        for x in others:
            _remove(x.el)
        tl.el.set("borderFillIDRef", self._merged_bf(tl.el.get("borderFillIDRef"), br.el.get("borderFillIDRef")))
        self._tput(tbl, cells, heights, widths, sized=[tl])
        return grid.result(self._cid, tl, removed=removed)

    def unmerge_cell(self, cell_id: str) -> dict:
        """A merged cell back to its grid: it stays the top-left piece with its text; the other pieces are empty copies
        of it (borderFill, margins, its first paragraph's shape). A cell that isn't merged: nothing changes."""
        tc = self._cell(cell_id)
        tbl, cells, nr, nc = self._tgrid(tc.getparent().getparent())
        x = next(c for c in cells if c.el is tc)
        if x.rs == x.cs == 1:
            return grid.result(self._cid, x)
        heights, widths = self._tsizes(cells, nr, nc)
        new = grid.unmerge(cells, x)
        for y in new:
            y.el = self._blank(tc)
        self._tput(tbl, cells, heights, widths, sized=[x, *new])
        return grid.result(self._cid, x, new)

    def split_cell(self, cell_id: str, rows: int, cols: int) -> dict:
        """한글 「셀 나누기」: the cell into rows × cols pieces sharing its height/width evenly — it stays the top-left
        piece with its text, the others are empty copies. On a line the cell spans alone, new grid lines go in and the
        other cells of that line span them; a span divisible by the count is shared out instead (ValueError otherwise)."""
        tc = self._cell(cell_id)
        tbl, cells, nr, nc = self._tgrid(tc.getparent().getparent())
        x = next(c for c in cells if c.el is tc)
        heights, widths = self._tsizes(cells, nr, nc)
        new, grown, added = grid.split(cells, x, int(rows), int(cols))
        for axis, at, k in added:
            lines = heights if axis == "r" else widths
            lines[at:at + 1] = grid.share(lines[at], k + 1)
            self._zones(tbl, axis, lambda s, e: (s + k * (s > at), e + k * (e >= at)))
        for y in new:
            y.el = self._blank(tc)
        self._tput(tbl, cells, heights, widths, sized=[x, *new])
        return grid.result(self._cid, x, new, grown=grown)

    def clone_rows(self, table_id: str, r0: int, r1: int, cols=None, keep_text: bool = True, above: bool = False) -> dict:
        """Copy rows r0..r1 right below r1 (spec ② §2 클론; keep_text=False = 행 추가: empty cells, same paragraph and
        cell shapes). cols = [c0, c1]: only those columns get new cells, the cells outside them on row r1 grow over the
        new rows (None = whole rows). above=True: the copy goes right above r0 (outside cells on r0 grow — ② §2a).
        ValueError when a merged cell crosses the range. "map" = {copied cell: its copy}."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        r0, r1 = int(r0), int(r1)
        c0, c1 = (int(cols[0]), int(cols[1])) if cols is not None else (0, nc - 1)
        heights, widths = self._tsizes(cells, nr, nc)
        new, grown = grid.clone(cells, nr, nc, r0, r1, c0, c1, above=above)
        d, add = r1 - r0 + 1, sum(heights[r0:r1 + 1])
        for y in new:
            y.el = copy.deepcopy(y.src.el) if keep_text else self._blank(y.src.el)
            for ls in list(y.el.iter(LINESEG)):
                _remove(ls)
        for y in grown:
            if (sz := y.el.find(_p("cellSz"))) is not None and int(sz.get("height", 0)):
                sz.set("height", str(int(sz.get("height")) + add))
            for ls in list(y.el.iter(LINESEG)):  # stale layout of the taller cell: 한글 lays it out again
                _remove(ls)
        if above:
            heights[r0:r0] = heights[r0:r1 + 1]
            self._zones(tbl, "r", lambda s, e: (s + d * (s > r0 or s == r0 and e <= r1), e + d * (e >= r0)))
        else:
            heights[r1 + 1:r1 + 1] = heights[r0:r1 + 1]
            self._zones(tbl, "r", lambda s, e: (s + d * (s > r1), e + d * (e > r1 or e == r1 and s < r0)))
        if (sz := tbl.find(_p("sz"))) is not None and int(sz.get("height", 0)):
            sz.set("height", str(int(sz.get("height")) + add))
        self._tput(tbl, cells, heights, widths)
        return grid.result(self._cid, None, new, grown=grown, mapping=True)

    # ---------------------------------------------------------------- 구분 초기화 (spec_구분_초기화 ② §4)
    def delete_rows(self, table_id: str, r0: int, r1: int, cols=None) -> dict:
        """Grid rows r0..r1 out: cells inside them go, cells from above across them get shorter (cellSz too), a cell
        starting inside and reaching below is a ValueError — with cols = [c0, c1] (끌어 지우기, ② §2a) only inside
        those columns; outside them such a cell keeps its text and starts after the rows (grid.drop_band).
        -> {"removed": [cell ids], "shrunk": [cell ids]}."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        r0, r1 = int(r0), int(r1)
        heights, widths = self._tsizes(cells, nr, nc)
        if cols is None:
            gone, shrunk = grid.drop_rows(cells, nr, r0, r1)
            shrunk = [(x, r0, r0 + lost - 1) for x, lost in shrunk]
        else:
            gone, shrunk = grid.drop_band(cells, nr, nc, r0, r1, int(cols[0]), int(cols[1]))
        removed = [self._id(x.el) for x in gone]
        for x in gone:
            _remove(x.el)
        for x, a, b in shrunk:
            if (sz := x.el.find(_p("cellSz"))) is not None and int(sz.get("height", 0)):
                sz.set("height", str(max(0, int(sz.get("height")) - sum(heights[a:b + 1]))))
            for ls in list(x.el.iter(LINESEG)):
                _remove(ls)
        cut = sum(heights[r0:r1 + 1])
        self._zones_cut(tbl, "r", r0, r1)
        if (sz := tbl.find(_p("sz"))) is not None and int(sz.get("height", 0)):
            sz.set("height", str(max(0, int(sz.get("height")) - cut)))
        del heights[r0:r1 + 1]
        self._tput(tbl, cells, heights, widths)
        return {"removed": removed, "shrunk": [self._id(x.el) for x, _, _ in shrunk]}

    def move_rows(self, table_id: str, r0: int, r1: int, cols, to: int) -> dict:
        """Rows r0..r1 of columns cols = [c0, c1] (None = whole rows) to the row line `to` — right above row `to`
        (끌어 옮기기, ② §2a): the cells keep their ids and text, outside the columns nothing moves (grid.move_band).
        Whole rows take their row heights along. -> {"moved": {old row: new row}}."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        r0, r1, to = int(r0), int(r1), int(to)
        c0, c1 = (int(cols[0]), int(cols[1])) if cols is not None else (0, nc - 1)
        heights, widths = self._tsizes(cells, nr, nc)
        perm = grid.move_band(cells, nr, nc, r0, r1, c0, c1, to)
        if (c0, c1) == (0, nc - 1):
            moved = [0] * nr
            for i, v in enumerate(heights):
                moved[perm.get(i, i)] = v
            heights[:] = moved
        lo, hi = min(perm), max(perm)
        for z in (z for zl in tbl.iterchildren(_p("cellzoneList")) for z in zl.iterchildren(_p("cellzone"))):
            s, e = int(z.get("startRowAddr")), int(z.get("endRowAddr"))
            if c0 <= int(z.get("startColAddr")) and int(z.get("endColAddr")) <= c1 and lo <= s and e <= hi and perm[e] - perm[s] == e - s:
                z.set("startRowAddr", str(perm[s]))
                z.set("endRowAddr", str(perm[e]))
        for x in cells:
            if x.r in perm.values() and c0 <= x.c <= c1:
                for ls in list(x.el.iter(LINESEG)):
                    _remove(ls)
        self._tput(tbl, cells, heights, widths)
        return {"moved": perm}

    def move_blocks(self, first_id: str, last_id: str, ref_id: str, before: bool = False) -> dict:
        """The top-level blocks first..last (their whole hosts — 개요 끌기, spec_서식 ② §6) right after (before=True: right
        before) block ref_id's host; ids stay. ValueError when a host is shared with blocks outside the range, holds the
        section settings, or ref is inside the range. -> {"moved": [ids]}."""
        hosts = self._host_range(first_id, last_id)
        first, last = self._ids[first_id], self._ids[last_id]
        if any(self._parts_out(h, first, last, hosts) for h in hosts):
            raise ValueError("옮길 범위가 다른 블록과 문단을 나눠 씁니다")
        ref = self._host(self._ids[ref_id])
        if ref in hosts:
            raise ValueError("옮길 범위 안으로는 옮길 수 없습니다")
        if any(next(h.iter(_p("secPr")), None) is not None for h in hosts):
            raise ValueError("구역 설정이 든 문단은 옮길 수 없습니다")
        if before and next(ref.iter(_p("secPr")), None) is not None:
            raise ValueError("구역 설정이 든 문단 앞에는 놓을 수 없습니다")
        old = hosts[0].getparent()
        for h in (hosts if before else reversed(hosts)):
            (ref.addprevious if before else ref.addnext)(h)
            for ls in list(h.iter(LINESEG)):  # 쪽 안 자리(vertpos)가 바뀜 — 한글이 다시 배치
                _remove(ls)
        self._touch(old)
        self._touch(ref)
        return {"moved": [self._rev[e] for h in hosts for e in h.iter() if e in self._rev]}

    def _zones_cut(self, tbl, axis, a, b):
        """hp:cellzone ranges after lines a..b of axis go: later lines move back, a zone inside them goes."""
        sa, ea = ("startRowAddr", "endRowAddr") if axis == "r" else ("startColAddr", "endColAddr")
        d = b - a + 1
        for zl in list(tbl.iterchildren(_p("cellzoneList"))):
            for z in list(zl.iterchildren(_p("cellzone"))):
                s, e = int(z.get(sa)), int(z.get(ea))
                s, e = (s if s < a else s - d if s > b else a), (e if e < a else e - d if e > b else a - 1)
                if e < s:
                    zl.remove(z)
                else:
                    z.set(sa, str(s))
                    z.set(ea, str(e))
            if not len(zl):
                tbl.remove(zl)

    def clone_cols(self, table_id: str, c0: int, c1: int, keep=None) -> dict:
        """Copy grid columns c0..c1 (every row, with text) right after c1: a cell inside them is copied, one spanning all
        of them from the left grows; ValueError when a merged cell crosses them. keep = (a, b): pre-op columns a..b
        (holding c0..c1) keep their total width — a..b+d share it in proportion after the op; None: the table gets
        wider by the copied columns. -> grid.result(), "map" = {copied cell: its copy}."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        c0, c1 = int(c0), int(c1)
        heights, widths = self._tsizes(cells, nr, nc)
        new, grown = grid.clone_cols(cells, nc, c0, c1)
        after, fit = grid.col_widths(widths, c0, c1, keep, add=True)
        for y in new:
            y.el = copy.deepcopy(y.src.el)
            for ls in list(y.el.iter(LINESEG)):
                _remove(ls)
        d = c1 - c0 + 1
        zones = [z for zl in tbl.iterchildren(_p("cellzoneList")) for z in zl.iterchildren(_p("cellzone"))
                 if c0 <= int(z.get("startColAddr")) and int(z.get("endColAddr")) <= c1]
        self._zones(tbl, "c", lambda s, e: (s + d * (s > c1), e + d * (e > c1 or e == c1 and s < c0)))
        for z in zones:  # a zone over copied cells only: its copy goes over the copies
            cp = copy.deepcopy(z)
            cp.set("startColAddr", str(int(z.get("startColAddr")) + d))
            cp.set("endColAddr", str(int(z.get("endColAddr")) + d))
            z.addnext(cp)
        self._col_put(tbl, cells, heights, widths, after, fit, [*new, *grown])
        return grid.result(self._cid, None, new, grown=grown, mapping=True)

    def delete_cols(self, table_id: str, c0: int, c1: int, keep=None) -> dict:
        """Grid columns c0..c1 out: cells inside them go, cells from the left across them get narrower; ValueError when
        a cell starts inside and reaches past c1. keep = (a, b): pre-op columns a..b keep their total width (a..b-d
        share it after the op); None: the table gets narrower. -> {"removed": [cell ids], "shrunk": [cell ids]}."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        c0, c1 = int(c0), int(c1)
        heights, widths = self._tsizes(cells, nr, nc)
        gone, shrunk = grid.drop_cols(cells, nc, c0, c1)
        after, fit = grid.col_widths(widths, c0, c1, keep, add=False)
        removed = [self._id(x.el) for x in gone]
        for x in gone:
            _remove(x.el)
        self._zones_cut(tbl, "c", c0, c1)
        self._col_put(tbl, cells, heights, widths, after, fit, [x for x, _ in shrunk])
        return {"removed": removed, "shrunk": [self._id(x.el) for x, _ in shrunk]}

    def even_cols(self, table_id: str, spans) -> dict:
        """Grid column spans [(c0, c1)…] (side by side) share their total width equally — columns inside a span keep their
        proportions, the table width stays (구분 초기화 차년도·기관 열, spec_구분_초기화 ② §3). -> {"widths": new widths}."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        heights, widths = self._tsizes(cells, nr, nc)
        after, fit = grid.even(widths, [(int(a), int(b)) for a, b in spans])
        self._col_put(tbl, cells, heights, widths, after, fit, [])
        return {"widths": after}

    def even_rows(self, table_id: str, spans) -> dict:
        """Grid row spans [(r0, r1)…] share their total height equally — rows inside a span keep their proportions, the table
        height stays (매직 브러쉬 「높이 같게」, spec_매직브러쉬 ② §3 · 규칙 C2). -> {"heights": new heights}."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        heights, widths = self._tsizes(cells, nr, nc)
        after, (a, b) = grid.even(heights, [(int(x), int(y)) for x, y in spans])
        touched = [x for x in cells if x.r <= b and x.r + x.rs - 1 >= a]
        self._tput(tbl, cells, after, widths, sized=touched)
        return {"heights": after}

    def size_lines(self, table_id: str, axis: str, lines, ref_cell_id: str) -> dict:
        """Grid lines (axis "r" rows / "c" columns) take the size of the reference cell's lines (its size on that axis ÷ its span);
        the table's hp:sz grows or shrinks by the difference (매직 브러쉬 기준 칸 높이·폭 맞추기, 규칙 J3·J4). -> {"sizes", "size"}."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        heights, widths = self._tsizes(cells, nr, nc)
        arr = heights if axis == "r" else widths
        ref = next((x for x in cells if self._id(x.el) == ref_cell_id), None)
        if ref is None:
            raise ValueError("기준 칸이 이 표에 없습니다")
        s, n = ref.at(axis)
        size = sum(arr[s:s + n]) // n
        lines = sorted({int(k) for k in lines})
        if not lines or any(k < 0 or k >= len(arr) for k in lines):
            raise ValueError(grid.OUTSIDE)
        delta = sum(size - arr[k] for k in lines)
        for k in lines:
            arr[k] = size
        touched = [x for x in cells if any(x.at(axis)[0] <= k < sum(x.at(axis)) for k in lines)]
        key = "height" if axis == "r" else "width"
        if (sz := tbl.find(_p("sz"))) is not None and int(sz.get(key, 0)):
            sz.set(key, str(max(0, int(sz.get(key)) + delta)))
        self._tput(tbl, cells, heights, widths, sized=touched)
        return {"sizes": arr, "size": size}

    def set_line_sizes(self, table_id: str, axis: str, sizes) -> dict:
        """Grid lines (axis "r" rows / "c" columns) take the given sizes {line: mm}; the table's hp:sz grows or shrinks by the
        difference (표 서식 정리 — 기준 표 행 높이·열 너비 맞추기, spec_표_서식_정리 ② §3). -> {"sizes": every line in mm}."""
        tbl, cells, nr, nc = self._tgrid(self._ids.get(table_id))
        heights, widths = self._tsizes(cells, nr, nc)
        arr = heights if axis == "r" else widths
        want = {int(k): round(float(v) * 7200 / 25.4) for k, v in dict(sizes).items()}
        if not want or any(k < 0 or k >= len(arr) for k in want):
            raise ValueError(grid.OUTSIDE)
        if any(v <= 0 for v in want.values()):
            raise ValueError("크기는 0 보다 커야 합니다")
        delta = sum(v - arr[k] for k, v in want.items())
        for k, v in want.items():
            arr[k] = v
        touched = [x for x in cells if any(x.at(axis)[0] <= k < sum(x.at(axis)) for k in want)]
        key = "height" if axis == "r" else "width"
        if (sz := tbl.find(_p("sz"))) is not None and int(sz.get(key, 0)):
            sz.set(key, str(max(0, int(sz.get(key)) + delta)))
        self._tput(tbl, cells, heights, widths, sized=touched)
        return {"sizes": [round(v * 25.4 / 7200, 2) for v in arr]}

    def _col_put(self, tbl, cells, heights, before, widths, fit, touched):
        """Write a column copy/delete back: cellSz width (not height) of the `touched` cells and of every cell over the
        refit columns `fit` (their layout caches go); without `fit` the table's hp:sz width follows the columns."""
        a, b = fit or (len(widths), -1)
        for x in cells:
            if x in touched or x.c <= b and x.c + x.cs - 1 >= a:
                if (sz := x.el.find(_p("cellSz"))) is not None:
                    sz.set("width", str(sum(widths[x.c:x.c + x.cs])))
                for ls in list(x.el.iter(LINESEG)):
                    _remove(ls)
        if fit is None and (sz := tbl.find(_p("sz"))) is not None and int(sz.get("width", 0)):
            sz.set("width", str(max(0, int(sz.get("width")) + sum(widths) - sum(before))))
        self._tput(tbl, cells, heights, widths)

    def _host_range(self, first_id, last_id):
        """Sibling hp:p from first's host to last's host."""
        a, b = self._host(self._ids[first_id]), self._host(self._ids[last_id])
        if a.getparent() is not b.getparent():
            raise ValueError("같은 그릇(본문·칸)의 블록이 아닙니다")
        out, el = [], a
        while el is not None:
            out.append(el)
            if el is b:
                return out
            el = el.getnext()
        raise ValueError("블록 범위가 거꾸로입니다")

    def _parts_out(self, host, first, last, hosts):
        """Parts of `host` outside the block range first..last: "text" (its paragraph block) and/or its tables·pictures.
        A host's blocks run [text, object 1, object 2, …] — one hp:p can hold several tables (한글 「글자처럼」 개체가 나란히)."""
        parts = ["text", *(o for r in host.iterchildren(RUN) for o in r.iterchildren(TBL, PIC))]
        a = parts.index(first) if host is hosts[0] and first in parts else 0
        b = parts.index(last) if host is hosts[-1] and last in parts else len(parts) - 1
        if host is hosts[0] and first is host:
            a = 0
        if host is hosts[-1] and last is host:
            b = 0
        return parts[:a] + parts[b + 1:]

    def _drop_parts(self, host, parts):
        for x in parts:
            if x == "text":
                for r in host.iterchildren(RUN):
                    for t in r.findall(T):
                        r.remove(t)
            else:
                x.getparent().remove(x)
        for ls in host.findall(LINESEG):
            host.remove(ls)

    def clone_blocks(self, first_id: str, last_id: str) -> dict:
        """Copy of the blocks first..last (paragraphs, tables, pictures — hosts from first's to last's) right after last's
        host; a host shared with blocks outside the range is copied without them. -> {"map": {block id: its copy's id}}
        for every element with an id in the copy (paragraphs, tables, cells, pictures). Section/page controls and layout
        caches stay out of the copy."""
        first, last = self._ids[first_id], self._ids[last_id]
        hosts, mapping = self._host_range(first_id, last_id), {}
        ref = hosts[-1]
        for host in hosts:
            new = copy.deepcopy(host)
            pairs = [(o, c) for o, c in zip(host.iter(), new.iter()) if o in self._rev]
            twin = dict(zip(host.iter(), new.iter()))
            self._drop_parts(new, [x if x == "text" else twin[x] for x in self._parts_out(host, first, last, hosts)])
            kept = set(new.iter())
            mapping.update({self._rev[o]: self._id(c) for o, c in pairs if c in kept})
            for e in list(new.iter(*DROP_ON_COPY, LINESEG)):
                parent = e.getparent()
                parent.remove(e)
                if parent.tag == CTRL and len(parent) == 0:
                    _remove(parent)
            ref.addnext(new)
            ref = new
        self._touch(ref)
        return {"map": mapping}

    def delete_blocks(self, first_id: str, last_id: str) -> dict:
        """The blocks first..last out (hosts from first's to last's with their tables and pictures; a host shared with
        blocks outside the range keeps those). ValueError when a host to delete holds the section settings; a cell left
        without paragraphs gets an empty one. -> {"removed": [ids]}."""
        first, last = self._ids[first_id], self._ids[last_id]
        hosts = self._host_range(first_id, last_id)

        def outside(h):   # 범위 밖에 남길 부분 — 빈 글만 남는 표·그림 문단은 문단째 지움(구역·쪽 제어가 든 문단은 남김)
            out = self._parts_out(h, first, last, hosts)
            if out == ["text"] and not self._text(h).strip() and next(h.iter(*DROP_ON_COPY), None) is None:
                return []
            return out
        shared = {h: out for h in hosts if (out := outside(h))}
        whole = [h for h in hosts if h not in shared]
        if any(next(h.iter(_p("secPr")), None) is not None for h in whole):
            raise ValueError("구역 설정이 든 문단은 지울 수 없습니다")
        parent = hosts[0].getparent()
        removed = [self._rev[e] for h in whole for e in h.iter() if e in self._rev]
        for h, out in shared.items():
            parts = ["text", *(o for r in h.iterchildren(RUN) for o in r.iterchildren(TBL, PIC))]
            gone = [x for x in parts if x not in out and not (x == "text" and not self._text(h).strip())]
            removed += [self._rev[e] for x in gone if x != "text" for e in x.iter() if e in self._rev]
            self._drop_parts(h, gone)
        for h in whole:
            parent.remove(h)
        if parent.find(P) is None:
            p = parent.makeelement(P, hosts[0].attrib)
            etree.SubElement(p, RUN, {"charPrIDRef": self._char_id(hosts[0])})
            parent.append(p)
        self._touch(parent)
        return {"removed": removed}

    def _marks(self):
        """(paragraph, [runs], text) per footnote mark: consecutive superscript runs (charPr hh:supscript) of a
        paragraph whose text is like 「15)」·「15-1)」 — the whole document, cells and nested tables too."""
        def sup(r):
            c = self._defs["charPr"].get(r.get("charPrIDRef"))
            return c is not None and c.find(_h("supscript")) is not None
        out = []
        for sec in self._sections:
            for p in sec.iter(P):
                runs = [*p.iterchildren(RUN), None]
                seq = []
                for r in runs:
                    if r is not None and sup(r):
                        seq.append(r)
                        continue
                    text = "".join(self._slot_text(s) for x in seq for s in self._run_slots(x))
                    if seq and MARK_RE.match(text):
                        out.append((p, seq, text))
                    seq = []
        return out

    def superscript_marks(self) -> list[dict]:
        """Footnote marks in superscript (「연구개발비15)」의 「15)」): [{"id": paragraph id, "text": mark}] in order."""
        return [{"id": self._id(p), "text": text} for p, _, text in self._marks()]

    def strip_superscript_marks(self) -> int:
        """Remove the text of every superscript footnote mark (the runs stay, empty). -> marks removed."""
        marks = self._marks()
        for p, seq, _ in marks:
            for r in seq:
                for t in r.findall(T):
                    r.remove(t)
            for ls in p.findall(LINESEG):
                p.remove(ls)
            self._touch(p)
        return len(marks)

    def _cid(self, x):
        return self._id(x.el)

    def _tgrid(self, tbl):
        if tbl is None or tbl.tag != TBL:
            raise ValueError("표가 아닙니다")
        cells = [grid.Cell(tc, int(a.get("rowAddr")), int(a.get("colAddr")), int(s.get("rowSpan", 1)),
                           int(s.get("colSpan", 1)))
                 for tr in tbl.iterchildren(TR) for tc in tr.iterchildren(TC)
                 for a, s in [(tc.find(CELLADDR), tc.find(CELLSPAN))]]
        return tbl, cells, int(tbl.get("rowCnt")), int(tbl.get("colCnt"))

    def _tsizes(self, cells, nr, nc):
        """(row heights, column widths) in HWPUNIT from the cells' hp:cellSz."""
        def size(dim):
            return lambda x: int(sz.get(dim, 0)) if (sz := x.el.find(_p("cellSz"))) is not None else 0
        return grid.sizes(cells, nr, "r", size("height")), grid.sizes(cells, nc, "c", size("width"))

    def _zones(self, tbl, axis, fn):
        """hp:cellzone ranges on axis through fn(start, end) -> (start, end)."""
        a, b = ("startRowAddr", "endRowAddr") if axis == "r" else ("startColAddr", "endColAddr")
        for z in (z for zl in tbl.iterchildren(_p("cellzoneList")) for z in zl.iterchildren(_p("cellzone"))):
            s, e = fn(int(z.get(a)), int(z.get(b)))
            z.set(a, str(s))
            z.set(b, str(e))

    def _tput(self, tbl, cells, heights, widths, sized=()):
        """Write the grid back, after dropping lines no cell starts on: cellAddr/cellSpan of every cell, cellSz of the
        `sized` ones (their paragraphs' layout cache goes), each hp:tr holding its row's cells in column order,
        rowCnt/colCnt."""
        for axis, lines in (("r", heights), ("c", widths)):
            for k in grid.squeeze(cells, len(lines), axis):
                v = lines.pop(k)
                lines[max(k - 1, 0)] += v
                self._zones(tbl, axis, lambda s, e: (s - (s >= k > 0), e - (e >= k > 0)))
        for x in cells:
            x.el.find(CELLADDR).attrib.update({"colAddr": str(x.c), "rowAddr": str(x.r)})
            x.el.find(CELLSPAN).attrib.update({"colSpan": str(x.cs), "rowSpan": str(x.rs)})
        for x in sized:
            if (sz := x.el.find(_p("cellSz"))) is not None:
                sz.attrib.update({"width": str(sum(widths[x.c:x.c + x.cs])), "height": str(sum(heights[x.r:x.r + x.rs]))})
            for p in x.el.find(SUBLIST).iterchildren(P):
                for ls in p.findall(LINESEG):
                    p.remove(ls)
        trs = list(tbl.iterchildren(TR))
        while len(trs) < len(heights):
            trs[-1].addnext(tbl.makeelement(TR, trs[-1].attrib))
            trs.append(trs[-1].getnext())
        rows = [[] for _ in heights]
        for x in sorted(cells, key=lambda x: (x.r, x.c)):
            rows[x.r].append(x.el)
        for tr, want in zip(trs, rows):
            if list(tr.iterchildren(TC)) != want:
                for tc in want:  # appending moves a tc out of the row it was in
                    tr.append(tc)
        for tr in trs[len(heights):]:
            tbl.remove(tr)
        tbl.set("rowCnt", str(len(heights)))
        tbl.set("colCnt", str(len(widths)))
        self._touch(tbl)

    def _cell_empty(self, tc):
        sub = tc.find(SUBLIST)
        return sub is None or not any(self._text(p).strip() or self._has_object(p) for p in sub.iterchildren(P))

    def _blank(self, src):
        """Empty copy of cell src: its attributes (borderFill…), margins and size, one empty paragraph in the shape of its
        first text paragraph (else its first) with that paragraph's char shape."""
        tc = copy.deepcopy(src)
        sub = tc.find(SUBLIST)
        ps = list(sub.iterchildren(P))
        tpl = next((p for p in ps if self._text(p).strip()), ps[0] if ps else None)
        p = sub.makeelement(P, tpl.attrib if tpl is not None else {"paraPrIDRef": "0", "styleIDRef": "0"})
        etree.SubElement(p, RUN, {"charPrIDRef": self._char_id(tpl) if tpl is not None else "0"})
        for q in ps:
            sub.remove(q)
        sub.append(p)
        return tc

    def _merged_bf(self, tl_bf, br_bf):
        """borderFill id of a merged cell: the top-left cell's, with the bottom-right cell's right and bottom lines."""
        a, b = self._defs["borderFill"].get(tl_bf), self._defs["borderFill"].get(br_bf)
        if a is None or b is None or tl_bf == br_bf:
            return tl_bf
        new = copy.deepcopy(a)
        for side in ("rightBorder", "bottomBorder"):
            old, line = new.find(_h(side)), b.find(_h(side))
            if old is not None and line is not None:
                new.replace(old, copy.deepcopy(line))
        return self._add_def("borderFill", new)

    # ---------------------------------------------------------------- save
    def _dump(self, name):
        xml = etree.tostring(self._roots[name].getroottree(), encoding="UTF-8", xml_declaration=False)
        return self._decl[name] + (xml.replace(b"&#13;", b"\r") if self._cr[name] else xml)

    def changes(self) -> dict:
        """연 바이트와 달라진 zip 멤버 {"parts": {이름: 바이트}, "new": {이름: 바이트}} — save() 가 쓸 그 바이트. 작업 저장이 zip 을 다시 쓰지 않고(47MB 4.7 s)
        바뀐 것만 남긴다(spec_작업 ② §5)."""
        return {"parts": {n: self._dump(n) for n in self._dirty}, "new": dict(self._new_members)}

    def save(self) -> bytes:
        if not self._dirty and not self._new_members:
            return self._data
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as out:
            for name, zi in self._infos.items():  # original order; mimetype stays first and STORED
                out.writestr(copy.copy(zi), self._dump(name) if name in self._dirty else zip_guard.read(self._zip, name))
            for name, data in self._new_members.items():
                zi = zipfile.ZipInfo(name, next(iter(self._infos.values())).date_time)
                zi.compress_type = zipfile.ZIP_DEFLATED
                out.writestr(zi, data)
        return buf.getvalue()
