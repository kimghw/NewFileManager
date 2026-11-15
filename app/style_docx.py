"""docx 운반 문서(spec_서식복사 ② §4 · §10) — 서식 템플릿의 **docx 형식**: 형식 중립 명세에서 지은 작은 docx 하나. 순수 함수(파일·세션을 모른다).

- 표 서식 = 표 명세(`style_carrier.spec_of_block` 의 꼴 — hwpx 운반 문서의 표에서 읽은 것: 칸 글 포함) → 빈 문단 + `w:tbl` 하나 + 빈 문단.
  글 서식 = `meta.items` → item 차례대로 견본 문단 하나씩(글 = `sample`). 문서 서식 = `meta.page`·`meta.body` → 쪽 설정(`w:sectPr`) + 바탕 글 모양의 견본 문단 3줄.
  표지 서식(② §14) = `style_cover.view` 의 부분들 → 그 쪽 설정 위에 글 부분은 견본 문단(앞 간격 = 문단 위 간격), 표 부분은 표 명세의 표(`from_cover`).
- 원본 XML 을 옮기지 않는다(원본이 docx 여도 명세로 짓는다). 표준 라이브러리 + lxml 로 OOXML 을 직접 쓴다 — 패키지 = `[Content_Types].xml` · `_rels/.rels` ·
  `word/document.xml` · `word/styles.xml` · `word/settings.xml`(호환 모드 15 하나 — 없으면 Word 가 옛 호환 모드로 열어 표가 왼쪽 여백 밖으로 칸 여백만큼 나간다) · `word/_rels/document.xml.rels`.
  같은 명세는 같은 바이트(zip 시각 고정).
- **모양은 모두 직접 서식으로 쓴다**(스타일을 가리키지 않는다) — 이 문서의 표·문단을 다른 docx 로 복사(`DocxDoc.insert_after(copy, src=)`)해도 받는 문서의 스타일에 물들지 않게.
  문단마다 줄 간격·위아래 간격·정렬을 늘 적는다(안 준 값 = 100% · 0 · 왼쪽).
- 서식 요약의 뜻은 **한글의 것**이다(명세가 hwpx 운반 문서에서 온다): 첫 줄이 음수(내어쓰기)면 한글은 첫 줄을 왼쪽 여백에 두고 둘째 줄부터 들인다(`style_verify.check_text` 의 왼끝 식) —
  Word 로는 `w:ind left = 왼쪽 여백 + |첫 줄|` · `hanging = |첫 줄|`. 그래서 `DocxDoc` 이 다시 읽은 왼쪽 여백은 그만큼 크다(내어쓰기 문단만).
- 못 옮기는 것은 losses 에: 자동 번호 · Word 에 없는 선 종류 · 0.5pt 단위가 아닌 글자 크기 · 글 폭보다 넓은 표 · 격자와 어긋난 칸. 명세에 없는 것(행 높이 · 칸 안 표·그림)은 처음부터 없다."""
import copy
import io
import re
import zipfile

from lxml import etree

from app import style_page
from app import table_make as M

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
DECL = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
STAMP = (1980, 1, 1, 0, 0, 0)  # zip 멤버 시각 — 고정(같은 명세 → 같은 바이트 → 같은 sha256)
TW_MM, PT_MM = 1440 / 25.4, 25.4 / 72  # mm → twip · pt → mm
PAGE = {"widthMm": 210, "heightMm": 297, "marginsMm": {"l": 20, "r": 20, "t": 20, "b": 20, "header": 10, "footer": 10, "gutter": 0}}  # 표·글 서식의 바탕 = A4 세로 · 여백 20mm
SAMPLE = "견본 글입니다"
HEX6 = re.compile(r"#[0-9A-Fa-f]{6}")
_BAD = re.compile("[\x00-\x08\x0b-\x1f￾￿]")  # XML 에 못 쓰는 글자(탭·줄 바꿈은 따로 다룬다)
ALIGN = {"left": "left", "center": "center", "right": "right", "justify": "both", "distribute": "distribute"}  # 서식 요약 → w:jc(docx_format._ALIGN_OUT)
# 한글 선 종류(hc:LineType2) → Word w:val. 앞 여섯은 이 앱이 docx 에서 다시 읽어도 같은 종류(docx_layout.BORDER), NEAR = Word 에 같은 선이 없어 가장 가까운 것(losses)
LINES = {"SOLID": "single", "DOT": "dotted", "DASH": "dashed", "DASH_DOT": "dotDash", "DASH_DOT_DOT": "dotDotDash", "DOUBLE_SLIM": "double",
         "SLIM_THICK": "thinThickSmallGap", "THICK_SLIM": "thickThinSmallGap", "SLIM_THICK_SLIM": "thinThickThinSmallGap"}
NEAR = {"LONG_DASH": "dashed", "CIRCLE": "dotted"}
SZ_MIN, SZ_MAX = 2, 96  # w:sz(1/8pt) — Word 가 받는 범위(0.25pt ~ 12pt)
NUM_RANGES = (("sizePt", 1, 400), ("lineSpacingPct", 50, 500), ("ratioPct", 50, 200), ("spacingPct", -50, 50), ("firstLineMm", -200, 200),
              ("indentLeftMm", 0, 200), ("indentRightMm", 0, 200), ("spaceBeforePt", 0, 200), ("spaceAfterPt", 0, 200))  # style_carrier.NUM_RANGES 와 같다

CONTENT_TYPES = (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
    '</Types>')
RELS = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '</Relationships>')
DOC_RELS = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
    '</Relationships>')
# 스타일 = 문서 기본값(맑은 고딕 10pt · 문단 간격 0 · 줄 간격 1줄) + 기본 문단 스타일 + 기본 표 스타일(Word 의 기본 칸 여백) — 견본은 이것을 가리키지 않는다(직접 서식)
STYLES = (
    f'<w:styles xmlns:w="{W_NS}">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="맑은 고딕" w:hAnsi="맑은 고딕" w:eastAsia="맑은 고딕" w:cs="Times New Roman"/>'
    '<w:sz w:val="20"/><w:szCs w:val="20"/><w:lang w:val="en-US" w:eastAsia="ko-KR" w:bidi="ar-SA"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="a"><w:name w:val="Normal"/><w:qFormat/></w:style>'
    '<w:style w:type="table" w:default="1" w:styleId="a1"><w:name w:val="Normal Table"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/>'
    '<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
    '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>'
    '</w:styles>')
SETTINGS = (
    f'<w:settings xmlns:w="{W_NS}"><w:compat>'
    '<w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>'
    '</w:compat></w:settings>')


# ---- XML · 패키지 ---------------------------------------------------------------------------------------------------

def _sub(parent, tag, **attrs):
    """parent 아래 `w:tag`(속성도 w: — 값은 글로)."""
    return etree.SubElement(parent, W + tag, {W + k: str(v) for k, v in attrs.items()})


def _tw(mm) -> int:
    return round(float(mm) * TW_MM)


def _num(v, lo=None, hi=None):
    """수(참·거짓 아님 · 범위 안)면 그 값, 아니면 None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return None
    return v if (lo is None or v >= lo) and (hi is None or v <= hi) else None


def _note(losses, text) -> None:
    if text not in losses:
        losses.append(text)


def _package(body) -> bytes:
    """본문(`w:body` 요소) → docx 바이트."""
    parts = (("[Content_Types].xml", CONTENT_TYPES.encode("utf-8")), ("_rels/.rels", RELS.encode("utf-8")),
             ("word/document.xml", etree.tostring(body.getparent(), encoding="UTF-8", xml_declaration=False)),
             ("word/styles.xml", STYLES.encode("utf-8")), ("word/settings.xml", SETTINGS.encode("utf-8")), ("word/_rels/document.xml.rels", DOC_RELS.encode("utf-8")))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in parts:
            info = zipfile.ZipInfo(name, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, DECL + data)
    return out.getvalue()


def _body():
    return etree.SubElement(etree.Element(W + "document", nsmap={"w": W_NS}), W + "body")


def _sect(body, page) -> None:
    """본문 끝의 쪽 설정 `w:sectPr` — page 는 `style_page.clean` 을 지난 것. 가로면 `w:orient="landscape"`(폭·높이는 보이는 방향 그대로).
    위·아래 여백은 종이 끝에서 본문까지(= Word 의 top·bottom), 머리말·꼬리말은 그 안의 몫 → Word 의 header·footer(종이 끝에서의 거리) = 여백 − 그 몫(`style_page` 모듈 설명)."""
    m = page["marginsMm"]
    sect = _sub(body, "sectPr")
    size = _sub(sect, "pgSz", w=_tw(page["widthMm"]), h=_tw(page["heightMm"]))
    if page["landscape"]:
        size.set(W + "orient", "landscape")
    _sub(sect, "pgMar", top=_tw(m["t"]), right=_tw(m["r"]), bottom=_tw(m["b"]), left=_tw(m["l"]),
         header=max(0, _tw(m["t"] - m["header"])), footer=max(0, _tw(m["b"] - m["footer"])), gutter=_tw(m["gutter"]))


# ---- 글 모양 --------------------------------------------------------------------------------------------------------

def _format(fmt) -> dict:
    """서식 요약 사전에서 옮길 값만 — 꼴이 틀리거나 범위 밖인 값은 버린다(`style_carrier._clean_format` 과 같은 규칙)."""
    f, out = fmt if isinstance(fmt, dict) else {}, {}
    if isinstance(f.get("font"), str) and f["font"].strip():
        out["font"] = _BAD.sub("", f["font"]).strip()[:60]
    for k, lo, hi in NUM_RANGES:
        if (v := _num(f.get(k), lo, hi)) is not None:
            out[k] = v
    out.update({k: f[k] for k in ("bold", "italic", "underline") if isinstance(f.get(k), bool)})
    if isinstance(f.get("color"), str) and HEX6.fullmatch(f["color"]):
        out["color"] = f["color"].upper()
    if f.get("align") in ALIGN:
        out["align"] = f["align"]
    return out


def _rpr(f, losses):
    """글자 모양 `w:rPr`(자식 차례 = CT_RPr: rFonts b bCs i iCs color spacing w sz szCs u). 값이 없으면 빈 요소."""
    rpr = etree.Element(W + "rPr", nsmap={"w": W_NS})
    if f.get("font"):
        _sub(rpr, "rFonts", ascii=f["font"], hAnsi=f["font"], eastAsia=f["font"], cs=f["font"])
    if f.get("bold"):
        _sub(rpr, "b"), _sub(rpr, "bCs")
    if f.get("italic"):
        _sub(rpr, "i"), _sub(rpr, "iCs")
    if f.get("color"):
        _sub(rpr, "color", val=f["color"][1:])
    size = f.get("sizePt")
    half = max(2, round(size * 2)) if size is not None else None
    if f.get("spacingPct"):  # 자간 = 글자 크기 대비 % → twip(docx_format._set_chars)
        _sub(rpr, "spacing", val=round(f["spacingPct"] / 100 * (half / 2 if half else 10) * 20))
    if f.get("ratioPct") is not None and round(f["ratioPct"]) != 100:  # 장평
        _sub(rpr, "w", val=round(f["ratioPct"]))
    if half is not None:
        _sub(rpr, "sz", val=half), _sub(rpr, "szCs", val=half)
        if abs(half / 2 - size) > 0.01:
            _note(losses, f"글자 크기 {size:g}pt 를 {half / 2:g}pt 로 옮겼습니다(Word 는 0.5pt 단위)")
    if f.get("underline"):
        _sub(rpr, "u", val="single")
    return rpr


def _ppr(p, f) -> etree._Element:
    """문단 모양 `w:pPr`(자식 차례 = CT_PPr: spacing ind jc) — 줄 간격·위아래 간격·정렬은 늘 적는다(받는 문서의 스타일에 물들지 않게)."""
    ppr = _sub(p, "pPr")
    _sub(ppr, "spacing", before=round((f.get("spaceBeforePt") or 0) * 20), after=round((f.get("spaceAfterPt") or 0) * 20),
         line=round((f.get("lineSpacingPct") or 100) * 2.4), lineRule="auto")
    left, right, first = f.get("indentLeftMm") or 0, f.get("indentRightMm") or 0, f.get("firstLineMm") or 0
    ind = {"left": _tw(left + max(0.0, -first)), "right": _tw(right)}  # 내어쓰기: 한글은 첫 줄이 왼쪽 여백 자리 → Word 의 left 는 그만큼 더(모듈 설명)
    ind.update({"hanging": _tw(-first)} if first < 0 else {"firstLine": _tw(first)})
    _sub(ppr, "ind", **ind)
    _sub(ppr, "jc", val=ALIGN.get(f.get("align"), "left"))
    return ppr


def _para(parent, text, fmt, losses):
    """문단 하나 — 글자 모양은 글 런과 문단 끝 표식(pPr/rPr — 글 없는 문단의 높이 · 뒤에 칠 글의 모양)에 같이 둔다. 탭은 `w:tab`, 앞뒤 빈칸은 지킨다."""
    f = _format(fmt)
    p = _sub(parent, "p")
    ppr, rpr = _ppr(p, f), _rpr(f, losses)
    if len(rpr):
        ppr.append(copy.deepcopy(rpr))
    text = _BAD.sub("", str(text or "")).replace("\n", " ")
    if text:
        r = _sub(p, "r")
        if len(rpr):
            r.append(rpr)
        for tok in (t for t in re.split("(\t)", text) if t):
            if tok == "\t":
                _sub(r, "tab")
                continue
            t = _sub(r, "t")
            t.text = tok
            if tok != tok.strip():
                t.set(XML_SPACE, "preserve")
    return p


# ---- 표 ------------------------------------------------------------------------------------------------------------

def _border(tcb, tag, e, losses) -> None:
    """칸 변 하나 `w:top|left|bottom|right` — e = 명세의 선 `{type, widthMm | width: "0.12 mm", color}` | None(선 없음 → nil)."""
    kind = str(e.get("type") or "NONE").upper() if isinstance(e, dict) else "NONE"
    if kind == "NONE":
        _sub(tcb, tag, val="nil")
        return
    val = LINES.get(kind) or NEAR.get(kind)
    if kind not in LINES:
        _note(losses, f"Word 에 없는 선 종류({kind})는 가장 가까운 선({val or 'single'})으로 옮겼습니다")
    mm = _num(e.get("widthMm"), 0)
    if mm is None and isinstance(e.get("width"), str) and (got := re.match(r"\s*([\d.]+)", e["width"])):
        try:
            mm = float(got.group(1))
        except ValueError:
            mm = None
    sz = min(SZ_MAX, max(SZ_MIN, round((mm or 0.12) / PT_MM * 8)))
    color = e["color"][1:].upper() if isinstance(e.get("color"), str) and HEX6.fullmatch(e["color"]) else "000000"
    _sub(tcb, tag, val=val or "single", sz=sz, space=0, color=color)


def _tc(tr, cell, width, span, merge, losses) -> None:
    """칸 하나(`w:tc`). merge = None | "restart"(세로로 합친 칸의 첫 칸) | "continue"(그 아래 칸 — 글 없이 빈 문단, 모양은 첫 칸과 같게: Word 는 합친 칸의 아래 선·음영을 칸마다 따로 읽는다)."""
    tc = _sub(tr, "tc")
    pr = _sub(tc, "tcPr")  # 자식 차례 = CT_TcPr: tcW gridSpan vMerge tcBorders shd tcMar vAlign
    _sub(pr, "tcW", w=width, type="dxa")
    if span > 1:
        _sub(pr, "gridSpan", val=span)
    if merge:
        _sub(pr, "vMerge", **({"val": "restart"} if merge == "restart" else {}))
    if isinstance(cell.get("edges"), dict):
        tcb = _sub(pr, "tcBorders")
        for tag, k in (("top", "t"), ("left", "l"), ("bottom", "b"), ("right", "r")):
            _border(tcb, tag, cell["edges"].get(k), losses)
    if isinstance(cell.get("fill"), str) and HEX6.fullmatch(cell["fill"]):
        _sub(pr, "shd", val="clear", color="auto", fill=cell["fill"][1:].upper())
    m = cell.get("marginsMm")
    if isinstance(m, dict) and all(_num(m.get(k), 0, 50) is not None for k in "lrtb"):
        mar = _sub(pr, "tcMar")
        for tag, k in (("top", "t"), ("left", "l"), ("bottom", "b"), ("right", "r")):
            _sub(mar, tag, w=_tw(m[k]), type="dxa")
    if cell.get("valign") in ("top", "center", "bottom"):
        _sub(pr, "vAlign", val=cell["valign"])
    for line in ([""] if merge == "continue" else str(cell.get("text") or "").split("\n")):  # 칸 글의 줄바꿈 = 문단 나눔
        _para(tc, line, cell.get("format"), losses)


def from_table_spec(spec) -> tuple[bytes, list[str]]:
    """표 명세(`style_carrier.spec_of_block` 의 꼴 — `{rows, cols, bands, widthsMm, cells: [{row, col, rowSpan, colSpan, text, fill, valign, marginsMm, edges{t,r,b,l}, format}]}`) →
    (docx 바이트, losses). 본문 = 빈 문단 + 표 하나 + 빈 문단 · 쪽 = A4 세로 · 여백 20mm(글 폭 170mm).
    표 = 격자(`tblGrid` · 가로로 합친 칸 `gridSpan` · 세로로 합친 칸 `vMerge`) · 열 폭(고정 배치) · 칸마다 폭·괘선·음영·칸 여백·세로 정렬 + 칸 글(줄마다 문단 — 그 칸의 글 모양).
    칸 글은 명세의 것 그대로(자료값은 hwpx 운반 문서를 만들 때 이미 견본으로 바뀌었다). 열 폭이 없으면 글 폭을 고르게 나누고, 표가 글 폭보다 넓으면 비율대로 줄인다(losses).
    격자 밖·겹치는 칸은 버리고 빈 자리는 빈 칸으로 메운다(losses). 명세가 틀리면 ValueError."""
    if not isinstance(spec, dict) or not isinstance(spec.get("cells"), list) or not spec["cells"]:
        raise ValueError("표 명세에 칸이 없습니다")
    try:
        rows, cols = int(spec.get("rows")), int(spec.get("cols"))
        given = sorted(((int(c["row"]), int(c["col"]), max(1, int(c.get("rowSpan") or 1)), max(1, int(c.get("colSpan") or 1)), c) for c in spec["cells"]), key=lambda x: x[:2])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"표 명세의 행·열 값이 틀렸습니다: {e}") from e
    if not (1 <= rows <= M.ROWS_MAX and 1 <= cols <= M.COLS_MAX):
        raise ValueError(f"표 명세의 크기가 한도 밖입니다({rows}행 × {cols}열)")
    losses, owner, starts, bad = [], {}, {}, 0  # owner: 격자 자리 → 그 자리를 덮는 칸의 시작 자리 · starts: 시작 자리 → (칸, 행 수, 열 수)
    for r, k, rs, cs, c in given:
        rs, cs = min(rs, rows - r), min(cs, cols - k)
        area = [(y, x) for y in range(r, r + rs) for x in range(k, k + cs)]
        if not (0 <= r < rows and 0 <= k < cols) or any(a in owner for a in area):
            bad += 1
            continue
        starts[r, k] = (c, rs, cs)
        owner.update(dict.fromkeys(area, (r, k)))
    holes = [(r, k) for r in range(rows) for k in range(cols) if (r, k) not in owner]
    for rk in holes:
        starts[rk], owner[rk] = ({}, 1, 1), rk
    if bad or holes:
        losses.append(f"명세의 칸 자리가 격자와 어긋났습니다 — 버린 칸 {bad}개 · 빈 칸으로 메운 자리 {len(holes)}곳")
    page = style_page.clean(PAGE)
    avail = page["widthMm"] - page["marginsMm"]["l"] - page["marginsMm"]["r"]
    widths = spec.get("widthsMm")
    if not (isinstance(widths, list) and len(widths) == cols and all(_num(w, 0.01) is not None for w in widths)):
        widths = [avail / cols] * cols
    if (total := sum(widths)) > avail + 0.05:
        losses.append(f"표 폭 {total:.0f}mm 를 바탕 쪽의 글 폭({avail:g}mm)에 맞춰 줄였습니다(열 폭 비율은 그대로)")
        widths = [w * avail / total for w in widths]
    grid = [max(1, _tw(w)) for w in widths]

    body = _body()
    _para(body, "", None, losses)
    tbl = _sub(body, "tbl")
    pr = _sub(tbl, "tblPr")  # 자식 차례 = CT_TblPr: tblW tblInd tblLayout
    _sub(pr, "tblW", w=sum(grid), type="dxa")
    _sub(pr, "tblInd", w=0, type="dxa")
    _sub(pr, "tblLayout", type="fixed")  # 열 폭을 글에 맞춰 다시 잡지 않게
    tg = _sub(tbl, "tblGrid")
    for w in grid:
        _sub(tg, "gridCol", w=w)
    for r in range(rows):
        tr, k = _sub(tbl, "tr"), 0
        while k < cols:
            at = owner[r, k]
            cell, rs, cs = starts[at]
            _tc(tr, cell, sum(grid[k:k + cs]), cs, None if rs == 1 else "restart" if at[0] == r else "continue", losses)
            k += cs
    _para(body, "", None, losses)
    _sect(body, page)
    return _package(body), losses


# ---- 글 · 문서 서식 ---------------------------------------------------------------------------------------------------

def from_text_items(items) -> tuple[bytes, list[str]]:
    """글 서식의 `meta.items`(`{format: 서식 요약 사전, marker{mode, literal, lead, gap}, sample}` …) → (docx 바이트, losses) — item 차례대로 견본 문단 하나씩
    (n번째 문단 ↔ `items[n]`: 본문에 다른 문단은 없다). 글 = `sample`(레터가 든 글 그대로 — 비었으면 레터 + 「견본 글입니다」).
    자동 번호(`marker.mode == "auto"`)는 되살리지 않는다 — 문단 모양만 옮기고 losses 에 적는다. 쪽 = A4 세로 · 여백 20mm."""
    if not isinstance(items, list) or not items or not all(isinstance(i, dict) for i in items):
        raise ValueError("글 서식에 항목이 없습니다")
    losses, body, auto = [], _body(), []
    for n, it in enumerate(items, 1):
        mk = it.get("marker") if isinstance(it.get("marker"), dict) else {}
        if mk.get("mode") == "auto":
            auto.append(str(it.get("name") or it.get("key") or f"{n}번째 항목"))
        lead = "".join(str(mk.get(k) or "") for k in ("lead", "literal", "gap")) if mk.get("mode") == "literal" else ""
        _para(body, str(it.get("sample") or "") or lead + SAMPLE, it.get("format"), losses)
    if auto:
        losses.append("자동 번호는 되살리지 않았습니다(문단 모양만) — " + " · ".join(auto[:5]) + (f" 외 {len(auto) - 5}개" if len(auto) > 5 else ""))
    _sect(body, style_page.clean(PAGE))
    return _package(body), losses


def from_page(page, body=None) -> tuple[bytes, list[str]]:
    """문서 서식(`meta.page` · `meta.body`) → (docx 바이트, losses). 쪽 설정 = `w:sectPr`(`pgSz` — 가로면 `w:orient="landscape"` · `pgMar` top·right·bottom·left·header·footer·gutter),
    본문 = 바탕 글 모양(`body.format`)의 견본 문단 3줄(`style_page.SAMPLES` — 첫 줄 = 검증이 자리를 재는 줄). page 가 틀리면 ValueError(`style_page.clean`)."""
    page = style_page.clean(page)
    losses, root = [], _body()
    fmt = body.get("format") if isinstance(body, dict) else None
    for text in style_page.SAMPLES:
        _para(root, text, fmt, losses)
    _sect(root, page)
    return _package(root), losses


def _spacer(body, mm) -> None:
    """높이가 mm 인 빈 문단(줄 높이 고정 — 0 이면 가장 얇게 1pt) — 표 앞의 간격(표는 위 간격을 못 갖는다) · 잇단 표 사이(Word 는 문단 없이 이어진 표를 하나로 붙인다) ·
    표로 끝나는 본문의 마지막 문단(Word 는 표 뒤에 문단이 있어야 한다)."""
    ppr = _sub(_sub(body, "p"), "pPr")
    _sub(ppr, "spacing", before=0, after=0, line=min(31680, max(20, _tw(mm))), lineRule="exact")
    rpr = _sub(ppr, "rPr")
    _sub(rpr, "sz", val=2), _sub(rpr, "szCs", val=2)


def _cover_table(spec, avail, losses):
    """표지의 표 부분 하나 → `w:tbl` 요소 — 기존 표 짓기(`from_table_spec`)로 지은 문서에서 표만 꺼낸다(모양이 모두 직접 서식이라 다른 본문에 옮겨도 같다).
    `from_table_spec` 은 A4·여백 20mm(글 폭 170mm) 바탕에 맞추므로, 표지 쪽의 글 폭(avail)이 그보다 좁으면 여기서 먼저 줄인다(losses)."""
    if not isinstance(spec, dict):
        raise ValueError("표지의 표 부분에 표 명세가 없습니다")
    base = style_page.clean(PAGE)
    cap = min(avail, base["widthMm"] - base["marginsMm"]["l"] - base["marginsMm"]["r"])
    widths = spec.get("widthsMm")
    if isinstance(widths, list) and widths and all(_num(w, 0.01) is not None for w in widths):
        if (total := sum(widths)) > cap + 0.05:
            _note(losses, f"표 폭 {total:.0f}mm 를 {cap:g}mm 로 줄였습니다(열 폭 비율은 그대로 — 표지 쪽의 글 폭과 170mm 가운데 좁은 쪽까지)")
            spec = {**spec, "widthsMm": [w * cap / total for w in widths]}
    else:
        try:
            cols = int(spec.get("cols"))
        except (TypeError, ValueError):
            cols = 0
        if cols > 0:
            spec = {**spec, "widthsMm": [cap / cols] * cols}
    data, more = from_table_spec(spec)
    for x in more:
        _note(losses, x)
    return etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml")).find(f"{W}body/{W}tbl")


def from_cover(parts, page) -> tuple[bytes, list[str]]:
    """표지 서식(spec_서식복사 ② §14 — `style_cover.view(...)` 의 parts · page) → (docx 바이트, losses). 쪽 설정 = page(`w:sectPr`), 본문 = 부분 차례대로:
    글 부분(`{type: "text", sample, format, gapBeforeMm}`) = 그 서식의 견본 문단 하나 — `gapBeforeMm`(앞의 빈 줄들이 차지하던 높이)는 문단 위 간격에 더한다 ·
    표 부분(`{type: "table", spec, gapBeforeMm}`) = 표 명세의 표(`from_table_spec` 과 같은 표) — 앞 간격이 있거나 바로 앞이 표면 그 높이의 빈 문단을 사이에 둔다.
    표로 끝나면 가장 얇은 빈 문단 하나로 닫는다. 글·표 부분이 하나도 없거나 page 가 틀리면 ValueError."""
    page = style_page.clean(page)
    parts = [p for p in parts if isinstance(p, dict) and p.get("type") in ("text", "table")] if isinstance(parts, list) else []
    if not parts:
        raise ValueError("표지 서식에 글·표 부분이 없습니다")
    m = page["marginsMm"]
    avail = page["widthMm"] - m["l"] - m["r"] - m["gutter"]
    losses, body, after_table = [], _body(), False
    for part in parts:
        gap = _num(part.get("gapBeforeMm"), 0, 500) or 0
        if part["type"] == "table":
            tbl = _cover_table(part.get("spec"), avail, losses)
            if gap or after_table:
                _spacer(body, gap)
            body.append(tbl)
            after_table = True
            continue
        p = _para(body, part.get("sample"), part.get("format"), losses)
        if gap:
            spacing = p.find(f"{W}pPr/{W}spacing")
            spacing.set(W + "before", str(int(spacing.get(W + "before")) + _tw(gap)))
        after_table = False
    if after_table:
        _spacer(body, 0)
    _sect(body, page)
    return _package(body), losses


def build(meta, carrier) -> tuple[bytes, list[str]]:
    """보관함 템플릿(meta + hwpx 운반 문서 바이트) → (docx 운반 문서 바이트, losses) — `meta["kind"]` 로 가른다: `table` = hwpx 운반 문서의 표 명세
    (`style_carrier.view(carrier, meta)["spec"]` — 라벨·견본 글 포함) · `text` = `meta["items"]` · `page` = `meta["page"]`·`meta.get("body")` ·
    `cover` = hwpx 운반 문서의 보기(`style_cover.view(carrier, meta)` 의 parts·page — ② §14). 못 지으면 ValueError."""
    kind = meta.get("kind") if isinstance(meta, dict) else None
    try:
        if kind == "cover":
            from app import style_cover  # 함수 안에서 — 표지 모듈이 이 모듈을 읽어도 서로 물리지 않게
            got = style_cover.view(carrier, meta)
            return from_cover(got["parts"], got["page"])
        if kind == "table":
            from app import style_carrier  # 함수 안에서 — style_carrier 쪽이 이 모듈을 읽어도 서로 물리지 않게
            return from_table_spec(style_carrier.view(carrier, meta)["spec"])
        if kind == "text":
            return from_text_items(meta.get("items"))
        if kind == "page":
            return from_page(meta.get("page"), meta.get("body"))
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"docx 서식을 짓지 못했습니다: {type(e).__name__}: {e}") from e
    raise ValueError(f"docx 서식으로 지을 수 없는 서식 종류입니다({kind!r})")


# ---- 읽기 ----------------------------------------------------------------------------------------------------------

def table_id(doc) -> str:
    """`DocxDoc` 으로 연 운반 문서의 (하나뿐인) 표 블록 id — 없으면 ValueError. 적용 때의 `srcId`(`DocxDoc.insert_after([{kind: "copy", srcId}], src=운반 문서)`)."""
    tbl = doc._body.find(W + "tbl")
    if tbl is None:
        raise ValueError("docx 운반 문서에 표가 없습니다")
    return doc._id(tbl, "t")


def para_ids(doc) -> list[str]:
    """`DocxDoc` 으로 연 운반 문서의 본문 문단 블록 id 들(문서 차례) — 글 서식 = `items` 차례의 견본 문단 · 문서 서식 = 견본 3줄 · 표 서식 = 표 앞뒤의 빈 문단 둘."""
    return [doc._id(p, "p") for p in doc._body.iterchildren(W + "p")]
