"""OWPML(KS X 6101) 검사 — 스키마(OWPML 2024 XSD) + 참조 규칙, 원본 대비 판정(spec_owpml_편집 ② §1).

한글이 저장한 원본도 공개 XSD 와 어긋나는 곳이 많다(줄 배치 캐시 linesegarray·hp:switch·불리언 값 등, references/OWPML_스키마.md) — 그래서
「위반이 있는가」가 아니라 「원본에 없던 종류의 위반이 생겼는가」로 판정한다. 위반 종류 = (부분, 부모 요소, 요소, 속성, 오류 형식)."""
import collections
import copy
import re
import threading
from pathlib import Path

from lxml import etree

SCHEMA_DIR = Path(__file__).with_name("owpml_schema")
OLD = "http://www.hancom.co.kr/hwpml/2011/"
NEW = "http://www.owpml.org/owpml/2024/"
REMAP = [(f'"{OLD}{k}"'.encode(), f'"{NEW}{k}"'.encode()) for k in ("head", "paragraph", "core", "section")]
HP, HH, HC, HS = (f"{OLD}{k}" for k in ("paragraph", "head", "core", "section"))
NONE_ID = "4294967295"  # 「없음」(bullet/numbering paraHead charPrIDRef 등)
def _parser():
    """검사 사본을 다시 읽는 파서 — 스레드마다 따로(lxml 파서 객체는 스레드끼리 나눠 쓰면 안 됨, schemas() 와 같은 이유)."""
    p = getattr(_LOCAL, "parser", None)
    if p is None:
        p = _LOCAL.parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)
    return p

# 값 → 그 정의 종류(hwpx_doc.DEFS 키). 스키마는 IDRef 가 실제 정의를 가리키는지 모른다.
REF_ATTRS = {"charPrIDRef": "charPr", "paraPrIDRef": "paraPr", "styleIDRef": "style", "charStyleIDRef": "style",
             "nextStyleIDRef": "style", "borderFillIDRef": "borderFill", "tabPrIDRef": "tabPr", "outlineShapeIDRef": "numbering"}
DEF_LISTS = {"borderFills": "borderFill", "charProperties": "charPr", "tabProperties": "tabPr", "numberings": "numbering",
             "bullets": "bullet", "paraProperties": "paraPr", "styles": "style"}
TYPE_KO = {"SCHEMAV_ELEMENT_CONTENT": "요소 자리·순서", "SCHEMAV_CVC_COMPLEX_TYPE_3_2_1": "허용 안 된 속성",
           "SCHEMAV_CVC_COMPLEX_TYPE_4": "필수 속성 없음", "SCHEMAV_CVC_PATTERN_VALID": "속성 값 모양",
           "SCHEMAV_CVC_DATATYPE_VALID_1_2_1": "속성 값 형식", "SCHEMAV_CVC_ENUMERATION_VALID": "속성 값 목록 밖",
           "SCHEMAV_CVC_ATTRIBUTE_3": "속성 값", "SCHEMAV_CVC_ELT_1": "정의 없는 요소"}
RULE_KO = {"ref": "없는 정의를 가리킴", "count": "개수 속성이 실제와 다름", "dup": "정의 id 중복", "secCnt": "구역 수(secCnt)가 다름",
           "secPr": "구역 설정(secPr) 자리·개수", "tbl": "표 격자"}


def _t(tag, ns=HP):
    return f"{{{ns}}}{tag}"


def _local(el):
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


_LOCAL = threading.local()


def schemas():
    """{"header": XMLSchema, "section": XMLSchema} — OWPML 2024 (app/owpml_schema, python-hwpx 6.11.0 사본).
    스레드마다 따로 — XMLSchema 의 error_log 는 검사마다 덮어써서, 가져오기 검증 스레드와 편집 요청이 같은 객체를 쓰면 오류 목록이 섞인다."""
    s = getattr(_LOCAL, "schemas", None)
    if s is None:
        s = _LOCAL.schemas = {"header": etree.XMLSchema(etree.parse(str(SCHEMA_DIR / "owpml-header.xsd"))),
                              "section": etree.XMLSchema(etree.parse(str(SCHEMA_DIR / "owpml-body.xsd")))}
    return s


def _remap(xml: bytes) -> bytes:
    for a, b in REMAP:
        xml = xml.replace(a, b)
    return xml


def block_of(doc, el):
    """el 이 든 블록 id(가장 가까운 문단·칸·표·그림) — 없으면 None."""
    while el is not None:
        i = doc._rev.get(el)
        if i is not None:
            return i
        el = el.getparent()
    return None


# ---------------------------------------------------------------- 스키마
def _start_tag_lines(xml: bytes):
    """직렬화한 XML 에서 k 번째 시작 태그가 놓인 줄 번호 → {줄: k}(문서 순 = parsed.iter() 차례). 글·속성 값 안의 「<」 는 늘 이스케이프되므로
    「</」·「<?」·「<!」 가 아닌 「<」 = 시작 태그. 같은 줄에 둘 이상이면 첫 것(검사 사본은 자식마다 줄을 바꿔 보통 하나)."""
    out, k, line = {}, 0, 1
    for m in re.finditer(rb"\n|<(?!/|!\[)", xml):  # 주석 「<!--」·처리 지시 「<?」 도 iter() 가 내는 노드라 함께 센다(CDATA 「<![」 만 제외)
        if m.group() == b"\n":
            line += 1
        else:
            out.setdefault(line, k)
            k += 1
    return out


def schema_violations(root, part, originals=None):
    """root(hh:head·hs:sec 요소)를 XSD 로 검사 -> [{part, kind, type, el, message}]. root 는 바꾸지 않는다.
    originals: root.iter() 차례의 요소 목록 대신 오류를 붙일 요소들(같은 차례) — 작은 구역 문서를 산 문단에 붙일 때."""
    work = copy.deepcopy(root)
    src = originals if originals is not None else list(root.iter())
    # 줄 배치 캐시(hp:linesegarray)는 OWPML 밖 한컴 확장 — 검사 사본에서 뺀다. 두면 그 자리에서 검사가 멈춰 같은 문단의 뒤 요소 오류가 가려진다.
    drop = set()
    for e in work.iter(_t("linesegarray")):
        drop.update(e.iter())
    if drop:
        src = [s for w, s in zip(work.iter(), src) if w not in drop]
        for e in list(work.iter(_t("linesegarray"))):
            e.getparent().remove(e)
    for el in work.iter():  # 자식 요소마다 앞에 줄 바꿈 — 오류 줄 번호 = 요소 하나(섞인 내용·요소만 내용 모두 공백 글이 허용됨)
        prev = None
        for c in el:
            if prev is None:
                el.text = (el.text or "") + "\n"
            else:
                prev.tail = (prev.tail or "") + "\n"
            prev = c
    xml = _remap(etree.tostring(work, encoding="UTF-8"))
    parsed = etree.fromstring(xml, _parser())
    xs = schemas()[part]
    xs.validate(parsed)
    if not xs.error_log:
        return []
    els = list(parsed.iter())
    # 오류 → 요소: 먼저 오류의 XPath(err.path — libxml 이 노드에서 만든 절대 경로 「/hs:sec/hp:p[12]/…」)로, 없으면 줄 번호로. 줄 번호는 65,535줄을 넘으면
    # libxml2(16비트 줄 번호)가 어림잡아 부모·형제로 어긋나(2026-11-09 구분 기준 반영 뒤 전체 검사 — 늘어난 문서에서 「원본에 없던 종류」 오탐) 큰 문서엔 못 믿는다.
    # 줄 번호도 lxml sourceline 대신 직렬화한 글에서 직접 센다(_start_tag_lines).
    line_el = _start_tag_lines(xml)
    pos = {e: k for k, e in enumerate(els)}
    nsmap = {k: v for k, v in parsed.nsmap.items() if k}
    out = []
    for err in xs.error_log:
        k = None
        if err.path:
            try:
                hit = parsed.xpath(err.path, namespaces=nsmap)
                k = pos.get(hit[0]) if hit else None
            except (etree.XPathError, TypeError):
                k = None
        if k is None:
            k = line_el.get(err.line)
        el = els[k] if k is not None else None
        live = src[k] if k is not None and k < len(src) else None
        attr = re.search(r"attribute '([^']+)'", err.message)
        parent = el.getparent() if el is not None else None
        kind = (part, _local(parent) if parent is not None else "", _local(el) if el is not None else "",
                attr.group(1) if attr else "", err.type_name)
        out.append({"part": part, "kind": kind, "el": live, "message": err.message})
    return out


# ---------------------------------------------------------------- 참조 규칙
def _rule(out, name, detail, el, message, part="section"):
    out.append({"part": part, "kind": ("rule", name, detail), "el": el, "message": message})


def _refs(doc, scope, out, part):
    fonts = {}
    for ff in doc._reflist.iter(_t("fontface", HH)):
        fonts[ff.get("lang")] = {f.get("id") for f in ff.iterchildren(_t("font", HH))}
    for el in scope.iter():
        if not isinstance(el.tag, str):
            continue
        for attr, kind in REF_ATTRS.items():
            v = el.get(attr)
            if v is not None and v != NONE_ID and v not in doc._defs[kind]:
                _rule(out, "ref", attr, el, f"{_local(el)} {attr}={v} — 그 {kind} 정의가 없음", part)
        tag = el.tag
        if tag == _t("heading", HH) and el.get("type") in ("BULLET", "NUMBER"):
            kind = "bullet" if el.get("type") == "BULLET" else "numbering"
            if el.get("idRef") not in doc._defs[kind]:
                _rule(out, "ref", f"heading.{kind}", el, f"heading idRef={el.get('idRef')} — 그 {kind} 정의가 없음", part)
        elif tag == _t("fontRef", HH):
            for attr, v in el.attrib.items():
                lang = attr.upper()
                if lang in fonts and v not in fonts[lang]:
                    _rule(out, "ref", f"fontRef.{attr}", el, f"fontRef {attr}={v} — {lang} 글꼴 목록에 없음", part)
        elif tag == _t("img", HC):
            v = el.get("binaryItemIDRef")
            if v and v not in doc._items:
                _rule(out, "ref", "binaryItemIDRef", el, f"그림 binaryItemIDRef={v} — content.hpf 목록에 없음", part)


def _header_rules(doc, out):
    head = doc._roots["Contents/header.xml"]
    for lst in doc._reflist:
        if not isinstance(lst.tag, str) or lst.get("itemCnt") is None:
            continue
        n = sum(1 for c in lst if isinstance(c.tag, str))
        if lst.get("itemCnt") != str(n):
            _rule(out, "count", _local(lst), lst, f"{_local(lst)} itemCnt={lst.get('itemCnt')} — 실제 {n}개", "header")
        kind = DEF_LISTS.get(_local(lst))
        if kind:
            ids = collections.Counter(c.get("id") for c in lst if isinstance(c.tag, str))
            for i, c in ids.items():
                if c > 1:
                    _rule(out, "dup", kind, lst, f"{kind} id={i} 가 {c}번", "header")
    for ff in doc._reflist.iter(_t("fontface", HH)):
        n = sum(1 for _ in ff.iterchildren(_t("font", HH)))
        if ff.get("fontCnt") is not None and ff.get("fontCnt") != str(n):
            _rule(out, "count", "fontCnt", ff, f"fontface {ff.get('lang')} fontCnt={ff.get('fontCnt')} — 실제 {n}개", "header")
    if head.get("secCnt") is not None and head.get("secCnt") != str(len(doc._sections)):
        _rule(out, "secCnt", "", head, f"secCnt={head.get('secCnt')} — 구역 파일 {len(doc._sections)}개", "header")


def _section_rules(doc, out):
    for sec in doc._sections:
        found = list(sec.iter(_t("secPr")))
        first = next(sec.iterchildren(_t("p")), None)
        if len(found) != 1:
            _rule(out, "secPr", "count", found[1] if len(found) > 1 else first, f"구역 하나에 secPr {len(found)}개")
        for s in found:
            host = s
            while host is not None and host.getparent() is not sec:
                host = host.getparent()
            if host is not first:
                _rule(out, "secPr", "place", s, "secPr 가 구역 첫 문단에 있지 않음")


def _tables(scope, out):
    for tbl in scope.iter(_t("tbl")):
        try:
            nr, nc = int(tbl.get("rowCnt")), int(tbl.get("colCnt"))
        except (TypeError, ValueError):
            _rule(out, "tbl", "cnt", tbl, "rowCnt·colCnt 가 없거나 숫자가 아님")
            continue
        trs = list(tbl.iterchildren(_t("tr")))
        if len(trs) != nr:
            _rule(out, "tbl", "rows", tbl, f"rowCnt={nr} — hp:tr {len(trs)}개")
        cover = {}
        for tr in trs:
            tcs = list(tr.iterchildren(_t("tc")))
            if not tcs:
                _rule(out, "tbl", "emptyRow", tr, "칸 없는 hp:tr(한글 저장 시 죽음)")
            for tc in tcs:
                a, s = tc.find(_t("cellAddr")), tc.find(_t("cellSpan"))
                if a is None or s is None:
                    _rule(out, "tbl", "addr", tc, "cellAddr·cellSpan 없음")
                    continue
                r, c = int(a.get("rowAddr", 0)), int(a.get("colAddr", 0))
                rs, cs = int(s.get("rowSpan", 1)), int(s.get("colSpan", 1))
                if r < 0 or c < 0 or rs < 1 or cs < 1 or r + rs > nr or c + cs > nc:
                    _rule(out, "tbl", "bounds", tc, f"칸 ({r},{c}) {rs}×{cs} 이 {nr}×{nc} 표 밖")
                    continue
                for y in range(r, r + rs):
                    for x in range(c, c + cs):
                        if (y, x) in cover:
                            _rule(out, "tbl", "overlap", tc, f"격자 ({y},{x}) 를 두 칸이 덮음")
                        cover[y, x] = tc
                if tc.find(_t("subList")) is not None and tc.find(_t("subList")).find(_t("p")) is None:
                    _rule(out, "tbl", "emptyCell", tc, "칸 안에 문단이 없음")
        holes = nr * nc - len(cover)
        if holes > 0:
            _rule(out, "tbl", "hole", tbl, f"어느 칸도 덮지 않은 격자 {holes}개")
        for z in (z for zl in tbl.iterchildren(_t("cellzoneList")) for z in zl.iterchildren(_t("cellzone"))):  # 안 표의 것은 그 표에서
            try:
                ok = 0 <= int(z.get("startRowAddr")) <= int(z.get("endRowAddr")) < nr and 0 <= int(z.get("startColAddr")) <= int(z.get("endColAddr")) < nc
            except (TypeError, ValueError):
                ok = False
            if not ok:
                _rule(out, "tbl", "cellzone", z, "cellzone 범위가 표 밖")


def rule_violations(doc, hosts=None):
    """참조 규칙 위반 — hosts=None 이면 문서 전체, 아니면 그 문단들(+ header 목록 개수·구역 설정은 늘 전체)."""
    out = []
    _header_rules(doc, out)
    _section_rules(doc, out)
    if hosts is None:
        _refs(doc, doc._roots["Contents/header.xml"], out, "header")
        for sec in doc._sections:
            _refs(doc, sec, out, "section")
            _tables(sec, out)
    else:
        for h in hosts:
            _refs(doc, h, out, "section")
            _tables(h, out)
    return out


# ---------------------------------------------------------------- 묶음·판정
def check_doc(doc):
    """문서 전체 검사 -> {"schema": [...], "rules": [...]}."""
    schema = schema_violations(doc._roots["Contents/header.xml"], "header")
    for sec in doc._sections:
        schema += schema_violations(sec, "section")
    return {"schema": schema, "rules": rule_violations(doc)}


def check_hosts(doc, hosts, header=False):
    """편집 한 번이 닿은 최상위 문단들(+ header)만 — 작은 구역 문서로 묶어 검사."""
    hosts = [h for h in dict.fromkeys(hosts) if h is not None and h.getparent() is not None]
    schema = schema_violations(doc._roots["Contents/header.xml"], "header") if header else []
    if hosts:
        sec = etree.Element(_t("sec", HS), nsmap=hosts[0].getroottree().getroot().nsmap)
        for h in hosts:
            sec.append(copy.deepcopy(h))
        schema += schema_violations(sec, "section", [sec] + [e for h in hosts for e in h.iter()])
    return {"schema": schema, "rules": rule_violations(doc, hosts)}


def counts(res):
    return {"schema": collections.Counter(v["kind"] for v in res["schema"]),
            "rules": collections.Counter(v["kind"] for v in res["rules"])}


def accepted(base, kinds):
    """기준선 base(counts 꼴)에 작업이 받아들인 스키마 위반 종류 kinds(세션의 `owpml_ok` — 다른 문서에서 가져온 내용이 물고 온 종류)를 더한 것.
    base 에 없는 종류만 개수 1 로 더한다(정확한 개수는 남기지 않는다 — 그 종류가 늘어난 것은 「물려받음」 주의). 더할 것이 없으면 base 그대로(같은 객체 — 캐시를 그대로 쓴다).
    편집 판정(server.owpml_base)과 수정본 OWPML 검사(verify.eowpml)가 같은 셈을 쓴다(spec_병합 ② §5-10 「가져온 스키마 위반 종류」)."""
    extra = [k for k in kinds if k not in base["schema"]]
    if not extra:
        return base
    schema = base["schema"].copy()
    for k in extra:
        schema[k] = 1
    return {"schema": schema, "rules": base["rules"]}


def kind_text(kind):
    if kind[0] == "rule":
        return f"{RULE_KO.get(kind[1], kind[1])}" + (f" · {kind[2]}" if kind[2] else "")
    part, parent, el, attr, typ = kind
    where = f"{parent}/{el}" if parent else el
    return f"{part} {where}" + (f" @{attr}" if attr else "") + f" — {TYPE_KO.get(typ, typ)}"


def _examples(doc, res, kinds, n=3):
    out = {}
    for v in res["schema"] + res["rules"]:
        if v["kind"] in kinds and len(out.setdefault(v["kind"], [])) < n:
            out[v["kind"]].append({"block": block_of(doc, v["el"]) if v["el"] is not None else None, "message": v["message"][:240]})
    return out


def verdict(doc, base, res, local=False):
    """base = counts(원본 검사), res = 지금 검사(check_doc 또는 check_hosts).
    -> {"status": ok|warn|fail, "new": [...], "grown": [...], "rules": [...], "schemaTotal", "baseTotal", ...}.
    local=True(편집 한 범위만 본 검사)는 개수 비교를 못 하므로 종류만 본다."""
    now = counts(res)
    new = [k for k in now["schema"] if k not in base["schema"]]
    grown = [] if local else [k for k in now["schema"] if k in base["schema"] and now["schema"][k] > base["schema"][k]]
    if local:
        rules = [k for k in now["rules"] if not base["rules"].get(k)]
    else:
        rules = [k for k in now["rules"] if now["rules"][k] > base["rules"].get(k, 0)]
    status = "fail" if new or rules else "warn" if grown else "ok"
    ex = _examples(doc, res, set(new) | set(rules) | set(grown))

    def item(k, src):
        return {"kind": kind_text(k), "count": src[k], "base": (base["schema"] if k[0] != "rule" else base["rules"]).get(k, 0),
                "examples": ex.get(k, [])}
    return {"status": status,
            "new": [item(k, now["schema"]) for k in new], "rules": [item(k, now["rules"]) for k in rules],
            "grown": [item(k, now["schema"]) for k in grown],
            "schemaTotal": sum(now["schema"].values()), "baseTotal": sum(base["schema"].values()),
            "ruleTotal": sum(now["rules"].values()), "baseRuleTotal": sum(base["rules"].values())}


def summary_text(v):
    """검증 단계·알림용 한 줄."""
    if v["status"] == "fail":
        parts = [f"원본에 없던 종류의 스키마 위반 {len(v['new'])}가지"] if v["new"] else []
        parts += [f"참조 규칙 위반 {sum(x['count'] - x['base'] for x in v['rules'])}건"] if v["rules"] else []
        first = (v["new"] + v["rules"])[0]
        return " · ".join(parts) + f" — 예: {first['kind']}"
    s = f"원본에 없던 위반 없음 · 스키마 위반 {v['schemaTotal']:,}건(원본 {v['baseTotal']:,}건)"
    if v["grown"]:
        s += f" · 원본에도 있던 종류가 늘어남 {len(v['grown'])}가지(물려받음 — 예: {v['grown'][0]['kind']})"
    return s
