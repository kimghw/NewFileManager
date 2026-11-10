"""OOXML(DOCX) 참조 검사 — owpml_check 의 DOCX 짝(spec_docx_웹편집 ② §3). 공개 모양은 owpml_check 와 같다:
check_doc(doc) / check_hosts(doc, hosts, header) -> {"schema": [], "rules": [...]}, counts, verdict, summary_text, kind_text.

OOXML XSD 는 넣지 않았다 — 그래서 schema 는 늘 빈 목록이고, Word 가 「읽을 수 없는 내용」으로 거절하거나 고쳐 여는 자리만 규칙으로 본다:
관계 id(r:*)·관계 대상 파트·콘텐츠 형식, 스타일·번호 참조, 표 구조(칸 끝 문단·빈 행·세로 병합·격자 폭), 문단·런 속성 자리,
고유 id(wp:docPr·w14:paraId) 중복, pPr·rPr·tcPr 자식 순서. 판정은 owpml 과 같이 「원본에 없던 종류·늘어난 개수」.
위반 종류 = ("rule", 규칙, 값 없는 자리 — 「pPr/jc」 같은 요소 이름) — 값·위치는 빼서 편집 전후 개수를 견준다."""
import posixpath
from urllib.parse import unquote

from lxml import etree

from app.docx_doc import W, WP, _kids
from app.docx_format import _PPR, _RPR, _TCPR
from app.owpml_check import block_of, counts  # noqa: F401 — counts 는 같은 모양(schema·rules Counter)

R_NS = ("http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "http://purl.oclc.org/ooxml/officeDocument/relationships")
O_RELID = "{urn:schemas-microsoft-com:office:office}relid"  # VML 그림(v:imagedata o:relid)도 관계 id
W14_PARAID = "{http://schemas.microsoft.com/office/word/2010/wordml}paraId"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
STORY_TYPES = ("/header", "/footer", "/footnotes", "/endnotes", "/comments")  # 본문처럼 r:id·스타일을 쓰는 이야기 파트
_R_ATTRS = etree.XPath("descendant-or-self::*/@*[namespace-uri()=$a or namespace-uri()=$b]")
_O_RELIDS = etree.XPath("descendant-or-self::*/@o:relid", namespaces={"o": "urn:schemas-microsoft-com:office:office"})
_PARAIDS = etree.XPath("descendant-or-self::*/@w14:paraId",
                       namespaces={"w14": "http://schemas.microsoft.com/office/word/2010/wordml"})
ORDER = {"pPr": {t: i for i, t in enumerate(_PPR)}, "rPr": {t: i for i, t in enumerate(_RPR)},
         "tcPr": {t: i for i, t in enumerate(_TCPR)}}
NUMBERING_ORDER = {W + "numPicBullet": 0, W + "abstractNum": 1, W + "num": 2, W + "numIdMacAtCleanup": 3}
RULE_KO = {"rel": "관계 없는 r:id", "relTarget": "관계 대상 파트 없음", "contentType": "콘텐츠 형식 없는 파트",
           "style": "정의 없는 스타일", "num": "번호 정의", "tbl": "표 구조", "p": "문단 속성(pPr) 자리", "r": "런 속성(rPr) 자리",
           "dup": "고유 id 중복", "order": "속성 자식 순서"}
DETAIL_KO = {"endP": "칸이 문단으로 끝나지 않음", "emptyRow": "칸 없는 행", "vMerge": "위 칸 없는 세로 병합 이어짐",
             "gridSpan": "행 폭이 격자 열 수보다 넓음", "numId": "없는 numId", "abstractNumId": "없는 abstractNum",
             "order": "abstractNum·num 순서", "first": "첫 자식이 아님", "many": "두 개 이상"}


def _local(el):
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _rule(out, doc, name, detail, el, message, part):
    out.append({"part": part, "kind": ("rule", name, detail), "el": el, "message": message,
                "block": block_of(doc, el) if el is not None else None})


# ---------------------------------------------------------------- 파트
def _rels_name(name):
    d, b = posixpath.split(name)
    return f"{d}/_rels/{b}.rels" if d else f"_rels/{b}.rels"


def _rel_root(doc, part):
    return doc._part(doc._rels_name if part == doc._doc else _rels_name(part))


def stories(doc):
    """본문과 그 관계로 이어진 이야기 파트(머리말·꼬리말·각주·미주·메모) [(이름, 뿌리)]."""
    out = [(doc._doc, doc._part(doc._doc))]
    rels = _rel_root(doc, doc._doc)
    for r in rels if rels is not None else ():
        if r.get("TargetMode") != "External" and r.get("Type", "").endswith(STORY_TYPES):
            name = doc._resolve(doc._dir, unquote(r.get("Target", "")))
            root = doc._part(name)
            if root is not None:
                out.append((name, root))
    return out


def _names_lower(doc):
    return {n.lower() for n in doc._names}


def _rel_ids(doc, part):
    rels = _rel_root(doc, part)
    return {r.get("Id") for r in rels} if rels is not None else set()


# ---------------------------------------------------------------- 패키지 규칙(늘 문서 전체 — 싸다)
def _package_rules(doc, out):
    names = _names_lower(doc)
    # 관계 대상 파트: 안쪽 관계(TargetMode 없음·Internal)의 Target 이 패키지에 있는지
    rel_parts = [("_rels/.rels", "")] + [(n, posixpath.dirname(posixpath.dirname(n)))
                                          for n in sorted(doc._names) if n.endswith(".rels") and n != "_rels/.rels"]
    for rname, base in rel_parts:
        root = doc._part(rname)
        if root is None:
            continue
        owner = posixpath.join(base, posixpath.basename(rname)[:-5]) if base or rname != "_rels/.rels" else ""
        owner_dir = posixpath.dirname(owner) if owner else ""
        for r in root.iterchildren(PKG_REL + "Relationship"):
            if r.get("TargetMode") == "External":
                continue
            target = unquote(r.get("Target") or "")
            if not target or target.startswith("#"):
                continue
            name = doc._resolve(owner_dir, target)
            if name.lower() not in names:
                _rule(out, doc, "relTarget", r.get("Type", "").rsplit("/", 1)[-1], None,
                      f"{rname} {r.get('Id')} → {target} — 패키지에 그 파트가 없음", "package")
    # 콘텐츠 형식: 모든 멤버가 Override 나 확장자 Default 로 덮이는지
    ct = doc._part("[Content_Types].xml")
    if ct is not None:
        over = {(o.get("PartName") or "").lstrip("/").lower() for o in ct.iterchildren(CT + "Override")}
        dflt = {(d.get("Extension") or "").lower() for d in ct.iterchildren(CT + "Default")}
        for n in sorted(doc._names):
            if n == "[Content_Types].xml" or n.endswith("/") or n.lower().startswith("[trash]/"):  # [trash] = Office 가 버린 파트 자리(무시함)
                continue
            base = posixpath.basename(n)
            ext = base.rsplit(".", 1)[1].lower() if "." in base else ""  # 「.rels」 도 확장자 rels(splitext 는 점으로 시작한 이름을 확장자 없음으로 봄)
            if n.lower() not in over and ext not in dflt:
                _rule(out, doc, "contentType", ext or "(없음)", None, f"{n} — [Content_Types].xml 에 형식이 없음", "package")
    # 번호: num → abstractNum, numbering 자식 순서(numPicBullet < abstractNum < num)
    numbering = doc._sub_part("numbering")
    if numbering is not None:
        abstracts = {a.get(W + "abstractNumId") for a in numbering.iterchildren(W + "abstractNum")}
        top = -1
        for el in numbering:
            k = NUMBERING_ORDER.get(el.tag)
            if k is None:
                continue
            if k < top:
                _rule(out, doc, "num", "order", el, f"numbering: {_local(el)} 가 뒤 종류 다음에 옴(abstractNum 은 모든 num 앞)", "numbering")
            top = max(top, k)
            if el.tag == W + "num":
                a = el.find(W + "abstractNumId")
                if a is None or a.get(W + "val") not in abstracts:
                    _rule(out, doc, "num", "abstractNumId", el,
                          f"num {el.get(W + 'numId')} → abstractNum {a.get(W + 'val') if a is not None else '(없음)'} — 정의가 없음", "numbering")


def _dup_rules(doc, out, parts):
    """wp:docPr id·w14:paraId 가 문서(이야기 파트 모두)에서 한 번뿐인지 — 둘째 것부터 하나씩. mc:Fallback 안은 뺀다: Word 는
    mc:AlternateContent 의 가지 하나만 읽고, Word 가 쓴 Fallback(VML 글상자)은 Choice 의 문단·그림을 같은 id 로 되풀이한다."""
    seen_pr, seen_para = {}, {}
    for name, root in parts:
        fallback = {e for f in root.iter(MC + "Fallback") for e in f.iter()}
        for e in root.iter(WP + "docPr"):
            i = e.get("id")
            if i is None or e in fallback:
                continue
            if i in seen_pr:
                _rule(out, doc, "dup", "docPr", e, f"{name}: wp:docPr id={i} 가 두 번(첫 자리 {seen_pr[i]})", "document")
            else:
                seen_pr[i] = name
        for v in _PARAIDS(root):
            if v.getparent() in fallback:
                continue
            if v in seen_para:
                el = v.getparent()
                _rule(out, doc, "dup", "paraId", el, f"{name}: {_local(el)} w14:paraId={v} 가 두 번(첫 자리 {seen_para[v]})", "document")
            else:
                seen_para[v] = name


# ---------------------------------------------------------------- 요소 규칙(전체 또는 편집이 닿은 범위)
def _scope_rules(doc, out, part, scope, rel_ids, style_ids, num_ids):
    for v in _R_ATTRS(scope, a=R_NS[0], b=R_NS[1]) + _O_RELIDS(scope):
        if v and v not in rel_ids:
            el = v.getparent()
            _rule(out, doc, "rel", f"{_local(el)}@{etree.QName(v.attrname).localname}", el,
                  f"{part}: {_local(el)} {etree.QName(v.attrname).localname}={v} — 관계(.rels)에 없음", part)
    for tag in ("pStyle", "rStyle", "tblStyle"):
        for e in scope.iter(W + tag):
            v = e.get(W + "val")
            if v is not None and v not in style_ids:
                _rule(out, doc, "style", tag, e, f"{part}: {tag}={v} — styles 에 정의가 없음", part)
    for e in scope.iter(W + "numId"):
        v = e.get(W + "val")
        if e.getparent() is not None and e.getparent().tag == W + "numPr" and v not in (None, "0") and v not in num_ids:
            _rule(out, doc, "num", "numId", e, f"{part}: numId={v} — numbering 에 num 이 없음", part)
    for tbl in scope.iter(W + "tbl"):
        _table(doc, out, part, tbl)
    for p in scope.iter(W + "p"):
        _first(doc, out, part, p, "pPr", "p")
    for r in scope.iter(W + "r"):
        _first(doc, out, part, r, "rPr", "r")
    _order(doc, out, part, scope)


def _first(doc, out, part, el, prop, name):
    pr = el.find(W + prop)
    if pr is None:
        return
    first = next((c for c in el if isinstance(c.tag, str)), None)
    if first is not pr:
        _rule(out, doc, name, "first", pr, f"{part}: {name} 의 {prop} 가 첫 자식이 아님", part)
    if next(pr.itersiblings(W + prop), None) is not None:
        _rule(out, doc, name, "many", pr, f"{part}: {name} 에 {prop} 가 두 개 이상", part)


def _order(doc, out, part, scope):
    for prop, rank in ORDER.items():
        for pr in scope.iter(W + prop):
            top, prev = -1, None
            for c in pr:
                k = rank.get(c.tag)
                if k is None:
                    continue
                if k < top:
                    _rule(out, doc, "order", f"{prop}/{_local(c)}", c,
                          f"{part}: {prop} 안 {_local(c)} 가 {_local(prev)} 뒤에 옴(스키마 순서 어김)", part)
                else:
                    top, prev = k, c


def _block_last(el):
    """칸(또는 sdt·customXml 내용)의 마지막 블록 요소 태그 — p·tbl·None."""
    last = None
    for c in el:
        if c.tag in (W + "p", W + "tbl"):
            last = c.tag
        elif c.tag == W + "sdt":
            content = c.find(W + "sdtContent")
            last = _block_last(content) if content is not None else last
        elif c.tag == W + "customXml":
            last = _block_last(c) or last
    return last


def _table(doc, out, part, tbl):
    n_grid = sum(1 for _ in tbl.iterfind(f"{W}tblGrid/{W}gridCol"))
    above = {}  # 격자 열 -> 위 행에서 그 열에 시작한 칸이 세로 병합인지
    for tr in _kids(tbl, (W + "tr",)):
        tcs = list(_kids(tr, (W + "tc",)))
        if not tcs:
            _rule(out, doc, "tbl", "emptyRow", tr, f"{part}: 칸 없는 w:tr", part)
        pr = tr.find(W + "trPr")
        g = lambda tag: int((pr.find(W + tag).get(W + "val") or 0) if pr is not None and pr.find(W + tag) is not None else 0)  # noqa: E731
        col, below = g("gridBefore"), {}
        for tc in tcs:
            tpr = tc.find(W + "tcPr")
            span_el = tpr.find(W + "gridSpan") if tpr is not None else None
            try:
                span = max(1, int(span_el.get(W + "val") or 1)) if span_el is not None else 1
            except ValueError:
                span = 1
            vm = tpr.find(W + "vMerge") if tpr is not None else None
            if vm is not None and vm.get(W + "val", "continue") != "restart" and col not in above:
                _rule(out, doc, "tbl", "vMerge", tc, f"{part}: 세로 병합 이어짐 칸(격자 {col}열) 위에 병합 칸이 없음", part)
            if vm is not None:
                below[col] = True
            if _block_last(tc) != W + "p":
                _rule(out, doc, "tbl", "endP", tc, f"{part}: w:tc 가 w:p 로 끝나지 않음(Word 오류)", part)
            col += span
        width = col + g("gridAfter")
        if n_grid and width > n_grid:
            _rule(out, doc, "tbl", "gridSpan", tr, f"{part}: 행 폭 {width}열 > tblGrid {n_grid}열", part)
        above = below


def _refs(doc):
    styles = doc._sub_part("styles")
    numbering = doc._sub_part("numbering")
    style_ids = {s.get(W + "styleId") for s in styles.iterchildren(W + "style")} if styles is not None else set()
    num_ids = {n.get(W + "numId") for n in numbering.iterchildren(W + "num")} if numbering is not None else set()
    return style_ids, num_ids


def rule_violations(doc, hosts=None, header=True):
    """규칙 위반 — hosts=None 이면 문서 전체, 아니면 그 최상위 요소들(+ 패키지·번호·고유 id 는 늘 전체). header = styles·numbering 의
    속성 자식 순서·numId 참조도 볼지(서식 편집이 정의를 더했을 때)."""
    out = []
    parts = stories(doc)
    style_ids, num_ids = _refs(doc)
    _package_rules(doc, out)
    _dup_rules(doc, out, parts)
    if hosts is None:
        for name, root in parts:
            _scope_rules(doc, out, name, root, _rel_ids(doc, name), style_ids, num_ids)
    else:
        rel_ids = _rel_ids(doc, doc._doc)
        for h in hosts:
            _scope_rules(doc, out, doc._doc, h, rel_ids, style_ids, num_ids)
    if header:
        for kind in ("styles", "numbering"):
            root = doc._sub_part(kind)
            if root is None:
                continue
            _order(doc, out, kind, root)
            for e in root.iter(W + "numId"):
                v = e.get(W + "val")
                if kind == "styles" and v not in (None, "0") and v not in num_ids:
                    _rule(out, doc, "num", "numId", e, f"styles: numId={v} — numbering 에 num 이 없음", kind)
    return out


# ---------------------------------------------------------------- 묶음·판정 (owpml_check 와 같은 모양)
def check_doc(doc):
    """문서 전체 검사 -> {"schema": [], "rules": [...]} (OOXML XSD 없음 — schema 는 늘 빈 목록)."""
    return {"schema": [], "rules": rule_violations(doc)}


def check_hosts(doc, hosts, header=False):
    """편집 한 번이 닿은 최상위 요소(w:body 아래 w:p·w:tbl)들만 + 패키지·번호·고유 id 규칙."""
    hosts = [h for h in dict.fromkeys(hosts) if h is not None and h.getparent() is not None]
    return {"schema": [], "rules": rule_violations(doc, hosts, header=header)}


def kind_text(kind):
    if kind and kind[0] == "rule":
        name, detail = kind[1], kind[2]
        return RULE_KO.get(name, name) + (f" · {DETAIL_KO.get(detail, detail)}" if detail else "")
    return " ".join(map(str, kind))


def _examples(doc, res, kinds, n=3):
    out = {}
    for v in res["schema"] + res["rules"]:
        if v["kind"] in kinds and len(out.setdefault(v["kind"], [])) < n:
            blk = v.get("block") or (block_of(doc, v["el"]) if v.get("el") is not None else None)
            out[v["kind"]].append({"block": blk, "message": v["message"][:240]})
    return out


def verdict(doc, base, res, local=False):
    """owpml_check.verdict 와 같은 판정·키 — base = counts(원본 검사), res = 지금 검사. 참조 규칙 위반 개수가 원본보다 늘면(local 이면
    원본에 없던 종류면) fail. -> {"status", "new", "rules", "grown", "schemaTotal", "baseTotal", "ruleTotal", "baseRuleTotal"}."""
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
        grew = sum(x["count"] - x["base"] for x in v["rules"])
        return f"OOXML 참조 규칙 위반이 원본보다 {grew}건 늚 — 예: {v['rules'][0]['kind']}" if v["rules"] else "OOXML 검사 실패"
    return f"원본에 없던 위반 없음 · OOXML 참조 규칙 위반 {v['ruleTotal']:,}건(원본 {v['baseRuleTotal']:,}건) · OOXML XSD 검사는 없음"


def baseline(doc):
    """원본 기준선 — counts(check_doc(doc)). 블록 id(예시 자리)는 doc.blocks() 뒤에만 붙는다."""
    return counts(check_doc(doc))


