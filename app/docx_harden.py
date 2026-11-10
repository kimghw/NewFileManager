"""렌더 사본 docx 하드닝 — Word COM 이 비신뢰 docx 를 열 때 바깥(원격 템플릿·연결 그림·하위 문서·바깥을 부르는 필드 등)을 부르지 않게
렌더 사본에서 바깥 관계·참조를 뗀다. FileMergeManager `app/render_anchors.py` 의 strip_external 과 그 도우미를 그대로 옮긴 것
(FileMergeManager spec_병합 ② §2-4 「렌더 하드닝」, 포맷 사실은 FileMergeManager references/DOCX_포맷.md 「열 때 Word 가 바깥에서
가져오는 것」). 사용자 문서·다운로드 바이트는 건드리지 않는다 — PDF 출력·Word 다시 저장(app/pdf_render.py)에 넘기는 사본에만 쓴다."""
import copy
import io
import posixpath
import re
import zipfile
import zlib
from urllib.parse import unquote

from lxml import etree

from app import zip_guard

from app.docx_doc import _parser  # noqa: E402 — 스레드마다 파서(병렬 검증의 원본·재구성 렌더 사본을 동시에 만듦)
_W_NS = ("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "http://purl.oclc.org/ooxml/wordprocessingml/main")
_REL_NS = ("http://schemas.openxmlformats.org/officeDocument/2006/relationships",
           "http://purl.oclc.org/ooxml/officeDocument/relationships")  # r: (Transitional·Strict)
_O_RELID = "{urn:schemas-microsoft-com:office:office}relid"  # VML 그림의 관계 참조
_RELS = re.compile(r"(?:^|/)_rels/([^/]*)\.rels$")
_SETTINGS = re.compile(r"(?:^|/)settings\.xml$")  # 관계로 찾은 settings 파트에 더해 옛 고정 이름도(관계 없는 것은 Word 가 안 읽지만 고쳐도 무해)
_DECL_RE = re.compile(rb"(?:\xef\xbb\xbf)?<\?xml[^>]*\?>\s*")
_UTF8_DECL = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'  # 원래 선언이 UTF-8 이 아니면(다시 쓰는 글은 UTF-8)
# settings 파트에서 어디에 있든(mc:AlternateContent 의 모든 가지 안까지) 빼는 요소 — 원격 템플릿·편지 병합 데이터(열 때 SQL 확인 창·바깥
# 데이터)·열 때 필드 갱신(확인 창·INCLUDETEXT 등 바깥 글)
_DROP_SETTINGS = ("attachedTemplate", "mailMerge", "updateFields")
_UNLINK_ATTR = ("blip", "imagedata", "fill")  # 연결 그림 — 참조 속성만 뗀다(속성이 모두 선택, 박힌 그림 r:embed 는 그대로)
_UNLINK_EL = ("attachedTemplate", "subDoc", "OLEObject", "externalData")  # 요소째 빼도 문서가 성립 — 원격 템플릿·하위 문서·연결 OLE·차트 연결 통합 문서
_UNLINK_UP = {"sourceFileName": "frame"}  # 그 위 요소째 — 프레임(w:frameset 은 프레임 0개도 성립)
_NOWHERE = "external-link-removed"  # 모르는 요소가 참조하는 바깥 관계의 새 대상 — 문서 폴더 기준 없는 파일(원격을 부르지 않고 참조는 살아 있음)
_LINK_EL = ("hyperlink", "hlinkClick", "hlinkHover", "hlinkMouseOver")  # 하이퍼링크 관계를 참조해도 누를 때만 가는 요소
# 패키지 밖 주소 — 직접 URL(http·https·ftp·file 등 두 글자 이상 scheme, 안에 담긴 data: 는 빼고)·UNC(\\server, //server)·드라이브 절대
# 경로(연결된 네트워크 드라이브일 수 있음)
_ABS = re.compile(r"\s*(?:(?!data:)[a-z][a-z0-9+.\-]+:|[\\/]{2}|[a-z]:[\\/])", re.I)
_VML_NS = ("urn:schemas-microsoft-com:vml", "urn:schemas-microsoft-com:office:office", "urn:schemas-microsoft-com:office:word")
_VML_ATTR = ("src", "href", "althref")  # VML 이 주소를 직접 적는 속성(v:imagedata·v:fill src, o:href 등) — 관계 참조(r:id 등)와 따로
# 바깥 주소를 부르는 필드 종류(명령 첫 낱말, 대소문자 무관) — INCLUDE·IMPORT 는 INCLUDETEXT·INCLUDEPICTURE 의 옛 이름
_FETCH_FIELD = re.compile(r"\s*(?:INCLUDEPICTURE|INCLUDETEXT|INCLUDE|IMPORT|LINK|DDEAUTO|DDE)(?!\w)", re.I)
_QUOTE = ' QUOTE "" '  # 무해한 필드 명령 — 바꾼 필드도 캐시된 결과를 그대로 보인다
_FIELD_EL = ("fldChar", "instrText", "delInstrText", "t", "delText", "fldSimple")


def _ns(key):
    return key[1:].split("}", 1)[0] if key[:1] == "{" else None


def _local(key):
    return key.rsplit("}", 1)[-1]


def _external(rel):
    """관계 대상이 패키지 밖 — TargetMode="External" 이거나 Target 이 직접 URL·UNC·드라이브 절대 경로(내부 관계로 적어도)."""
    return (rel.get("TargetMode") or "").lower() == "external" or bool(_ABS.match(rel.get("Target") or ""))


def _remote(rel):
    """Word 가 열 때 바깥에서 가져오는 관계 — 패키지 밖 대상(_external) 중 하이퍼링크(누를 때만 감) 아닌 것, 그리고 붙인 템플릿."""
    kind = (rel.get("Type") or "").rsplit("/", 1)[-1]
    return kind == "attachedTemplate" or (_external(rel) and kind != "hyperlink")


def _hits(root, ids):
    """부분 XML 에서 관계 ids 를 참조하는 [(요소, 속성 이름들)] — r:* 속성과 VML o:relid."""
    return [(el, keys) for el in root.iter() if isinstance(el.tag, str)
            for keys in [[k for k, v in el.attrib.items() if v in ids and (k == _O_RELID or etree.QName(k).namespace in _REL_NS)]]
            if keys]


def _unlink(root, ids):
    """부분 XML 에서 관계 ids 의 참조를 뗀다 -> (참조가 남은 id — 모르는 요소, 고쳤는지)."""
    kept, changed = set(), False
    for el, keys in _hits(root, ids):
        name = etree.QName(el).localname
        up = el.getparent()
        if name in _UNLINK_ATTR:
            for k in keys:
                del el.attrib[k]
        elif (name in _UNLINK_EL or name in _UNLINK_UP) and up is not None:
            if name in _UNLINK_UP and etree.QName(up).localname == _UNLINK_UP[name] and up.getparent() is not None:
                el, up = up, up.getparent()
            up.remove(el)
        else:
            kept |= {el.get(k) for k in keys}
            continue
        changed = True
    return kept, changed


def _drop_settings(root):
    """settings 파트의 _DROP_SETTINGS 를 어디에 있든 뺀다 — mc:AlternateContent 의 mc:Choice·mc:Fallback 모든 가지 안까지(Word 가 어느
    가지를 고를지 미리 모름). 빈 가지는 남긴다(그대로 성립). -> 고쳤는지"""
    hits = [el for el in root.iter() if isinstance(el.tag, str) and _ns(el.tag) in _W_NS and _local(el.tag) in _DROP_SETTINGS]
    for el in hits:
        if (up := el.getparent()) is not None:
            up.remove(el)
    return bool(hits)


def _scrub_vml(root):
    """VML(v:·o:·w10:) 요소의 src·href·althref 중 패키지 밖 주소(_ABS — 직접 URL·UNC·드라이브 절대 경로)를 뗀다. 요소는 남긴다(XML·그림
    자리가 그대로 성립하고 박힌 그림 r:id 는 그대로). -> 고쳤는지"""
    changed = False
    for el in root.iter(*(f"{{{ns}}}*" for ns in _VML_NS)):
        for k in [k for k, v in el.attrib.items() if _local(k).lower() in _VML_ATTR and _ns(k) in (None, *_VML_NS) and _ABS.match(v)]:
            del el.attrib[k]
            changed = True
    return changed


def _fields(root):
    """부분 XML 의 필드 -> (복합 필드 [{"begin": fldChar|None, "nodes": 명령 글 요소, "items": 명령 글·안긴 필드, "result": 결과 글}],
    단순 필드 w:fldSimple, w:dirty 가 붙은 fldChar·fldSimple). 복합 필드 = begin … separate … end — begin 과 separate 사이 런의 글은 모두
    명령(런에 나뉜 instrText, 지운 delInstrText, w:t 까지 — Word 는 그 사이를 필드 코드로 읽는다), 안긴 필드는 명령 안 그 자리에 필드째.
    끝나지 않은 필드·필드 밖 instrText 도 하나씩."""
    stack, done, simple, dirty = [], [], [], []
    for el in root.iter(*(f"{{{ns}}}{n}" for ns in _W_NS for n in _FIELD_EL)):
        name, ns = _local(el.tag), _ns(el.tag)
        if name in ("fldChar", "fldSimple") and el.get(f"{{{ns}}}dirty") is not None:
            dirty.append(el)
        if name == "fldSimple":
            simple.append(el)
        elif name == "fldChar":
            kind = el.get(f"{{{ns}}}fldCharType")
            if kind == "begin":
                f = {"begin": el, "nodes": [], "items": [], "result": []}
                if stack and "sep" not in stack[-1]:
                    stack[-1]["items"].append(f)
                stack.append(f)
            elif kind == "separate" and stack:
                stack[-1]["sep"] = True
            elif kind == "end" and stack:
                done.append(stack.pop())
        elif stack and "sep" not in stack[-1]:
            stack[-1]["nodes"].append(el)
            stack[-1]["items"].append(el.text or "")
        elif stack:
            stack[-1]["result"].append(el.text or "")
        elif name in ("instrText", "delInstrText"):
            done.append({"begin": None, "nodes": [el], "items": [el.text or ""], "result": []})
    return done + stack, simple, dirty


def _fetches(field):
    """바깥 주소를 부르는 복합 필드인지 — 명령(안긴 필드는 그 캐시된 결과 글로 이어)이 _FETCH_FIELD 로 시작하거나, 필드 종류를 안긴 필드가
    정한다(명령 첫머리가 안긴 필드 — Word 는 안긴 필드 결과로 명령을 만든다)."""
    code = "".join(x if isinstance(x, str) else "".join(x["result"]) for x in field["items"])
    first = next((x for x in field["items"] if not isinstance(x, str) or x.strip()), "")
    return bool(_FETCH_FIELD.match(code)) or isinstance(first, dict)


def _neutralize_fields(root):
    """바깥 주소를 부르는 필드(_FETCH_FIELD — INCLUDEPICTURE·INCLUDETEXT·LINK·DDE·DDEAUTO 등)의 명령을 무해한 _QUOTE 로 바꾼다. 복합 필드는
    begin 바로 뒤에 QUOTE instrText 를 넣고 자기 명령 글은 비운다(안긴 필드가 뒤에 남아도 필드 종류는 QUOTE), 단순 필드는 w:instr 를 바꾼다.
    런·fldChar(begin·separate·end) 구조와 캐시된 결과는 그대로. 필드마다의 열 때 갱신 표시(w:dirty — settings 의 updateFields 와 같은 확인
    창·갱신)도 뗀다. -> 고쳤는지"""
    fields, simple, dirty = _fields(root)
    for el in dirty:
        del el.attrib[f"{{{_ns(el.tag)}}}dirty"]
    changed = bool(dirty)
    for el in simple:
        key = f"{{{_ns(el.tag)}}}instr"
        if _FETCH_FIELD.match(el.get(key) or ""):
            el.set(key, _QUOTE)
            changed = True
    for f in fields:
        if not _fetches(f):
            continue
        for el in f["nodes"]:
            el.text = ""
        if f["begin"] is not None:
            q = f["begin"].makeelement(f"{{{_ns(f['begin'].tag)}}}instrText")
            q.text = _QUOTE
            q.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            f["begin"].addnext(q)
        changed = True
    return changed


_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")  # UTF-8·UTF-16LE·UTF-16BE
_LEAD = b" \t\r\n\x00"  # XML 앞 공백 — UTF-16 의 0 바이트까지(BOM 없는 UTF-16 은 lxml 이 못 읽어 parse 에서 가려진다)


def _xml_type(ct):
    """Content_Types 의 ContentType 이 XML 인지 — …+xml·application/xml·text/xml(매개변수는 뗀다)."""
    ct = (ct or "").split(";", 1)[0].strip().lower()
    return ct.endswith("+xml") or ct in ("application/xml", "text/xml")


def _xmlish(zin, info):
    """멤버 내용이 XML 같은지 — BOM(UTF-8·UTF-16)과 공백(UTF-16 의 0 바이트 포함)을 건너뛴 첫 글자가 '<'. 앞 몇 바이트만 보지 않는다
    (재검토 — 루트 앞 공백 512개로 검사를 피했다). 1 MiB 조각으로 끝까지 풀어 선언 크기·CRC 를 확인하고(그림 같은 바이너리도 메모리에
    쌓지 않음) 읽을 수 없으면 ValueError — 렌더 실패(원본을 그대로 넘기지 않는다)."""
    first, size = b"", 0
    try:
        with zin.open(info) as f:
            while chunk := f.read(1 << 20):
                if not first:
                    head = chunk if size else next((chunk[len(b):] for b in _BOMS if chunk.startswith(b)), chunk)
                    first = head.lstrip(_LEAD)[:1]
                size += len(chunk)
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as e:  # zip_guard.read 와 같은 「읽을 수 없는 멤버」
        raise ValueError(f"zip 멤버를 읽을 수 없음({info.filename}: {e})") from e
    if size != info.file_size:
        raise ValueError(f"zip 멤버 크기가 선언과 다름({info.filename}: {size} ≠ {info.file_size})")
    return first == b"<"


def _target(rels, target, lower):
    """관계 파일 rels 의 내부 Target -> 패키지 멤버 이름(없으면 None) — 원본 부분 폴더 기준, '/' 로 시작하면 패키지 뿌리 기준. OPC 부분
    이름처럼 대소문자·% 인코딩은 가리지 않는다(lower: 소문자 이름 → 멤버 이름)."""
    m = _RELS.search(rels)
    t = (target or "").replace("\\", "/").split("#", 1)[0]
    path = posixpath.normpath("/" + posixpath.join(rels[:m.start()], t)).lstrip("/")
    return lower.get(path.lower()) or lower.get(unquote(path).lower())


def strip_external(data):
    """렌더 사본 docx 바이트 → Word 가 열 때 바깥을 부르지 않는 바이트(spec_병합 ② §2-4 「렌더 하드닝」). 바깥 관계(_remote — 원격 템플릿
    attachedTemplate·프레임·하위 문서·연결 그림·연결 OLE 등, 하이퍼링크는 남김 — 단 하이퍼링크 관계를 그림·데이터 자리에서 참조하면 그것도)는
    관계와 참조를 함께 뺀다 — 연결 그림은 r:link 만 떼어 박힌 그림을 남긴다. 모르는 요소가 참조하는 것은 참조가 끊기지 않게(Word 가 손상
    파일로 봄) 관계를 남기고 대상만 _NOWHERE 로. settings 파트(관계 Type …/settings 로 찾음 — 이름은 무엇이든, 옛 고정 이름도)에서
    _DROP_SETTINGS 를 mc:AlternateContent 의 모든 가지 안까지 빼고, XML 부분마다 VML 의 직접 URL·UNC(_scrub_vml)와 바깥을 부르는 필드
    코드(_neutralize_fields)를 무해하게 한다. XML 부분 판정(재검토)은 [Content_Types].xml 이 XML 로 적은 것(Default 확장자·Override 부분
    이름)·.xml/.rels 이름·settings 관계 대상(이것들은 XML 이어야 함)과, 나머지 멤버(관계 대상 포함)는 내용(BOM·공백 뒤 '<' — _xmlish)으로.
    멤버는 조각 읽기(zip_guard.read — 선언 크기를 속인 멤버가 메모리를 다 쓰지 않게, 바이너리는 _xmlish 의 조각 풀기)로만 읽고, 읽을 수
    없는 멤버나 XML 이어야 하는데 못 읽는 부분이 있으면 ValueError(렌더 실패 — 원본을 그대로 넘기지 않음; 내용만 '<' 로 시작한 바이너리는
    그대로). 고친 멤버만 다시 쓰고 나머지는 원래 바이트·ZipInfo 순서 그대로, 고칠 것이 없거나 zip 이 아니면 받은 바이트 그대로. 사용자
    문서가 아니라 렌더 사본에만 쓴다(export_pdf)."""
    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return data
    with zin:
        infos = zin.infolist()
        names, roots, decl, dirty = {i.filename for i in infos}, {}, {}, set()
        lower = {n.lower(): n for n in sorted(names)}

        def part(name, need=True):
            """멤버 → XML 뿌리. XML 로 못 읽으면 need 면 ValueError(렌더 실패), 아니면 None(내용만 '<' 로 시작한 바이너리)."""
            if name not in roots:
                raw = zip_guard.read(zin, name)
                try:
                    root = etree.fromstring(raw, _parser())
                except etree.XMLSyntaxError as e:
                    if need:
                        raise ValueError(f"렌더 사본의 XML 부분을 읽을 수 없음({name}: {e})") from e
                    return None
                m = _DECL_RE.match(raw)
                d = m.group(0) if m else b""
                enc = re.search(rb"""encoding\s*=\s*["']([^"']*)""", d)
                decl[name] = _UTF8_DECL if enc and enc.group(1).lower() not in (b"utf-8", b"utf8") else d
                roots[name] = root
            return roots[name]

        # XML 이어야 하는 멤버 — .xml·.rels 이름, Content_Types 가 XML 로 적은 것(Default 확장자·Override 부분 이름 — 대소문자·% 인코딩 무관)
        must = {n for n in names if n.lower().endswith((".xml", ".rels"))}
        ct = lower.get("[content_types].xml")
        for el in part(ct) if ct else ():
            if not isinstance(el.tag, str) or not _xml_type(el.get("ContentType")):
                continue
            if _local(el.tag) == "Default" and (ext := (el.get("Extension") or "").lower()):
                must |= {n for n in names if (leaf := n.rsplit("/", 1)[-1].lower()).rpartition(".")[1] and leaf.rpartition(".")[2] == ext}
            elif _local(el.tag) == "Override" and (p := (el.get("PartName") or "").replace("\\", "/").lstrip("/")):
                must |= {n for n in [lower.get(p.lower()) or lower.get(unquote(p).lower())] if n}
        all_rels = sorted(n for n in names if _RELS.search(n))
        settings = {n for n in names if _SETTINGS.search(n)}
        for rels in all_rels:  # settings 파트 = 관계 Type …/settings 의 대상(astra: word/options.xml 을 가리키면 이름으로는 못 찾음)
            rows = [r for r in part(rels) if isinstance(r.tag, str)]
            settings |= {t for r in rows if (r.get("Type") or "").rsplit("/", 1)[-1].lower() == "settings" and not _external(r)
                         for t in [_target(rels, r.get("Target"), lower)] if t}
        must |= settings
        for name in dict.fromkeys(i.filename for i in infos):  # XML 부분마다 — settings 요소, VML 직접 주소, 바깥을 부르는 필드
            info = zin.getinfo(name)
            if info.is_dir() or _RELS.search(name) or name == ct:
                continue
            if name not in must and not _xmlish(zin, info):  # 나머지(관계 대상 포함)는 내용으로 — 끝까지 풀어 읽을 수 있는지도
                continue
            if (root := part(name, name in must)) is None:
                continue
            word = _ns(root.tag) in _W_NS
            changed = _scrub_vml(root)
            if word and name in settings:
                changed |= _drop_settings(root)
            if word:
                changed |= _neutralize_fields(root)
            if changed:
                dirty.add(name)
            elif not word:
                del roots[name]  # 다시 쓸 일 없는 다른 XML(SVG 그림·customXml 등)은 놓아준다
        for rels in all_rels:
            rows = [r for r in part(rels) if isinstance(r.tag, str)]
            drop = {r.get("Id"): r for r in rows if _remote(r)}
            links = {r.get("Id"): r for r in rows if _external(r) and r.get("Id") not in drop}  # 하이퍼링크 — 누를 때만 감
            m = _RELS.search(rels)
            src, root = lower.get(f"{rels[:m.start()]}/{m.group(1)}".lstrip("/").lower()), None
            if src and (drop or links):
                root = part(src, src in must)  # XML 아닌 원본 부분(바이너리)이면 None — 모두 대상만 바꾼다
            if links and root is not None:  # 하이퍼링크 관계를 그림·데이터 자리에서 참조하면 열 때 가져온다 — 그것도 뺀다
                drop |= {rid: links[rid] for el, keys in _hits(root, set(links)) if _local(el.tag) not in _LINK_EL
                         for rid in (el.get(k) for k in keys)}
            if not drop:
                continue
            kept, changed = (set(drop), False) if root is None else _unlink(root, set(drop))
            if changed:
                dirty.add(src)
            for rid, rel in drop.items():
                if rid not in kept:
                    rel.getparent().remove(rel)
                elif rel.get("Target") != _NOWHERE or rel.get("TargetMode") != "External":
                    rel.set("Target", _NOWHERE)
                    rel.set("TargetMode", "External")
                else:
                    continue
                dirty.add(rels)
        if not dirty:
            return data
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for info in infos:  # copy: writestr 가 받은 ZipInfo 를 고친다
                body = (decl[info.filename] + etree.tostring(roots[info.filename], encoding="UTF-8", xml_declaration=False)
                        if info.filename in dirty else zip_guard.read(zin, info))
                z.writestr(copy.copy(info), body)
        return out.getvalue()
