"""개요 줄 맞추기 — 짝 표지(형광펜 · 필드 · 변경 추적)가 든 줄(spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」 · 문서 쪽 함수 spec_owpml_편집 ② §2 「짝 표지」).

연구개발계획서 양식의 개요 줄 몇 개에 형광펜을 넣은 문서를 올리고 2단계(LLM 끔)를 돌린 뒤 본다. 전에는 형광펜이 든 줄 하나 때문에 `replace_prefix` 의 가드에 걸려
「모두 반영」 · 템플릿 맞추기 전체가 400 으로 되돌려졌다(작업 2336f896d390 — 형광펜 든 괄호 줄 4개: artifacts/markers_astra_2026-11-17/).
- 레터가 그대로인 줄 → 레터 앞·뒤 빈칸만 제자리에서(`prefix_keep_marks`) — 완전히 맞춤 · 형광펜 짝 그대로 · 새로 넣는 빈칸은 형광펜 밖.
- 레터를 바꿔야 하는 줄 · 빈칸 사이에 표지 → 모양만(`prefix_shape_only`) · `left` 에 남김 — 예외를 내지 않는다.
- 레터 뒤 빈칸이 필드·변경 추적 범위 안 → 묶음 빈칸으로 안 바꾼다(`outline_conform._gap` — needs · place 가 같이 따른다)."""
import copy
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_conform as OC
from app import outline_match as M
from app import outline_pos as OP
from app import server
from app.hwpx_doc import HP, NB, HwpxDoc
from app.hwpx_struct import RUN, T, MarkBlock, _alen, _atoms, _fill, _p

PLAN = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
# 형광펜을 넣을 줄 → (시작, 끝 — None = 글 끝)
MARKED = {"p9209": (0, None),    # T9 L1 괄호 줄 「[주관연구개발기관 : 기관명]」 — 레터 앞 빈칸 0칸(대표 4칸) · 형광펜이 자리 0 부터(실물의 (0,17) 줄과 같은 꼴)
          "p6128": (3, None),    # T9 L1 괄호 줄 「   [공동연구개발기관 : 기업명2] 」 — 레터 앞 빈칸 3칸 뒤부터 끝까지(실물의 (2,·) 줄과 같은 꼴)
          "p7262": (5, None),    # T5 L2 「 (3) 참여연구자 …」 — 레터 앞 빈칸만 대표와 다름 · 형광펜은 본문
          "p13421": (1, 2),      # T14 L1 「 ㅇ ~~~」 — 대표는 「o」: 레터를 바꿔야 하는데 형광펜이 레터를 덮음
          "p12696": (2, None)}   # T23 L3 「     - 기술개요 …」 — 레터 앞 빈칸(5칸 → 대표 4칸) 사이에서 형광펜 시작


def _ins(doc, p, pos, el, end):
    """문단 p 의 글 자리 pos 에 길이 0 표지 el 을 hp:t 안에 넣는다 — 시작 표지(end 거짓)는 pos 글자 바로 앞 · 끝 표지는 pos-1 글자 바로 뒤."""
    q = 0
    for r in p.iterchildren(RUN):
        for c in r:
            n = doc._clen(c)
            if c.tag == T and ((q < pos <= q + n) if end else (q <= pos < q + n)):
                out, k, put = [], q, False
                for u in [x for a in _atoms(c) for x in (a if isinstance(a, str) else (a,))]:
                    w = 1 if isinstance(u, str) else _alen(u)
                    if not put and not end and w and k == pos:
                        out.append(el)
                        put = True
                    out.append(u)
                    k += w
                    if not put and end and w and k == pos:
                        out.append(el)
                        put = True
                _fill(c, out)
                doc._touch(p)
                return
            q += n
    raise AssertionError(f"글 자리 {pos} 가 없습니다")


def _pen(doc, p, a, b):
    _ins(doc, p, a, p.makeelement(_p("markpenBegin"), {"color": "#FFFF00"}), False)
    _ins(doc, p, b, p.makeelement(_p("markpenEnd"), {}), True)


def _field(doc, pid, a, b, fid="901"):
    """하이퍼링크 필드 [a, b) — 표지는 런 안의 hp:ctrl(hp:t 밖)."""
    p = doc._ids[pid]
    for pos, xml in ((b, f'<hp:fieldEnd beginIDRef="{fid}"/>'), (a, f'<hp:fieldBegin id="{fid}" type="HYPERLINK"/>')):
        r, i = doc._cut(p, pos)
        r.insert(i, etree.fromstring(f'<hp:ctrl xmlns:hp="{HP}">{xml}</hp:ctrl>'))
    doc._touch(p)


def _spans(doc, pid, kind=None):
    return [(sp["start"], sp["end"]) if kind else (sp["kind"], sp["start"], sp["end"]) for sp in doc.mark_spans(doc._ids[pid])[0] if kind in (None, sp["kind"])]


def _pens(doc, pid):
    return _spans(doc, pid, "markpen")


def _text(doc, pid):
    return doc._text(doc._ids[pid])


@cache
def _base():
    """형광펜을 넣은 양식(올릴 바이트)."""
    doc = HwpxDoc(PLAN.read_bytes())
    doc.blocks()
    for pid, (a, b) in MARKED.items():
        p = doc._ids[pid]
        _pen(doc, p, a, len(doc._text(p)) if b is None else b)
    return doc.save()


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


@pytest.fixture(scope="module")
def sess(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("outline_marks")
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
                     "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}.items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": (PLAN.name, _base(), "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        assert c.get(f"/api/docs/{d}/outline").status_code == 200  # 오버레이를 만든다
        ov = s.outline
        # 형광펜이 든 줄도 전과 같은 자리(템플릿 · 레벨)의 개요 줄이다 — 표지는 글을 바꾸지 않는다
        assert {pid: (ov["lines"][pid]["tpl"], ov["lines"][pid]["level"]) for pid in MARKED} == {
            "p9209": ("9", 1), "p6128": ("9", 1), "p7262": ("5", 2), "p13421": ("14", 1), "p12696": ("23", 3)}
        assert [ov["templates"][t]["slots"][lv]["rep"] for t, lv in (("9", "1"), ("5", "2"), ("14", "1"), ("23", "3"))] == ["p1691", "p6929", "p6109", "p12684"]
        yield c, d, s, copy.deepcopy(ov)
        server.DOCS.clear()


def _fresh(sess):
    """올린 바이트를 따로 연 문서 + 처음 오버레이 사본 — 끝점을 거치지 않고 함수를 바로 부르는 시험이 세션을 안 건드리게."""
    doc = HwpxDoc(_base())
    doc.blocks()
    return doc, copy.deepcopy(sess[3])


def _undo_all(c, d, s):
    while s.state()["undo"]:
        assert c.post(f"/api/docs/{d}/undo").status_code == 200
    assert c.get(f"/api/docs/{d}/download").content == _base()


# ---------------------------------------------------------------- 레터가 그대로 — 빈칸만 제자리에서(완전히 맞춤)
def test_marked_label_lines_get_the_rep_blanks_and_keep_the_highlight(sess):
    doc, ov = _fresh(sess)
    sh = M.rep_shape(doc, ov, "p1691")
    assert (sh["lead"], sh["gap"]) == ("    ", "")
    left = []
    assert _pens(doc, "p9209") == [(0, 16)] and _text(doc, "p9209") == "[주관연구개발기관 : 기관명]"
    assert M.match_one(doc, ov, "p9209", sh, left) == "[주관연구개발기관 : 기관명]"
    assert _text(doc, "p9209") == "    [주관연구개발기관 : 기관명]" and _pens(doc, "p9209") == [(4, 20)]   # 새 레터 앞 빈칸은 형광펜 밖(시작 표지가 자리 0 이던 줄)
    assert M.same(M.look(doc, ov, "p9209"), M.look(doc, ov, "p1691"))                                    # 글자 모양까지 대표와 같다(대표 갈래로)
    assert _pens(doc, "p6128") == [(3, 21)] and _text(doc, "p6128") == "   [공동연구개발기관 : 기업명2] "
    assert M.match_one(doc, ov, "p6128", sh, left) == "[공동연구개발기관 : 기업명2]"
    assert _text(doc, "p6128") == "    [공동연구개발기관 : 기업명2]" and _pens(doc, "p6128") == [(4, 21)]   # 레터 바로 앞에서 시작하던 형광펜은 바꾼 뒤에도 레터 바로 앞
    assert M.same(M.look(doc, ov, "p6128"), M.look(doc, ov, "p1691"))
    assert left == []
    begin = doc._ids["p9209"].find(".//" + _p("markpenBegin"))
    assert begin is not None and begin.get("color") == "#FFFF00" and len(list(doc._ids["p9209"].iter(_p("markpenEnd")))) == 1
    again = HwpxDoc(doc.save())                                                                            # 저장 → 다시 열기: 짝이 그대로
    again.blocks()
    assert _pens(again, "p9209") == [(4, 20)] and _pens(again, "p6128") == [(4, 21)]
    assert _text(again, "p9209") == "    [주관연구개발기관 : 기관명]"


def test_settle_matches_a_marked_line_fully(sess):
    doc, ov = _fresh(sess)
    m, left = OP.Measure(doc), []
    assert _pens(doc, "p7262") == [(5, 19)]
    assert [k for k, *_ in M.diff(M.look(doc, ov, "p6929"), M.look(doc, ov, "p7262"))] == ["lead"]
    done = OC.settle(doc, ov, "5", 2, ["p7262"], m, left=left)
    assert "p7262" in done and left == []
    lead, tok, gap, plen, text = M.parts(doc, ov, "p7262")
    assert (lead, tok, gap) == ("  ", "(3)", NB) and text[plen:] == "참여연구자 및 연구지원인력"           # 대표의 레터 앞 빈칸 · 레터 뒤 묶음 빈칸 · 제 번호
    assert _pens(doc, "p7262") == [(6, 20)]                                                                # 본문의 형광펜은 그대로(자리만 한 칸 밀림)
    assert M.same(M.look(doc, ov, "p7262"), M.look(doc, ov, "p6929")) and not OC.needs(doc, ov, "p7262", m)
    assert ov["lines"]["p7262"]["letter"] == "(3)"


# ---------------------------------------------------------------- 못 바꾸는 줄 — 모양만 · left
def test_letter_change_under_a_highlight_is_shape_only_and_left(sess):
    doc, ov = _fresh(sess)
    sh = M.rep_shape(doc, ov, "p6109")
    assert sh["tok"] == "o"
    p = doc._ids["p13421"]
    text0, fmt0 = doc._text(p), ov["lines"]["p13421"].get("fmt")
    before = {k for k, *_ in M.diff(M.look(doc, ov, "p6109"), M.look(doc, ov, "p13421"))}
    assert {"letter", "align", "L.font", "font"} <= before and _pens(doc, "p13421") == [(1, 2)]
    left = []
    assert M.match_one(doc, ov, "p13421", sh, left) == "ㅇ"                                                 # 옛 레터 — 예외를 내지 않는다
    assert left == [{"id": "p13421", "why": "letter", "kinds": ["형광펜"]}]
    assert doc._text(p) == text0 and _pens(doc, "p13421") == [(1, 2)]                                      # 글 · 형광펜 그대로
    x = ov["lines"]["p13421"]
    assert x["letter"] == "ㅇ" and x.get("fmt") == fmt0                                                   # 오버레이의 레터 · 서식 라벨도 그대로
    assert (p.get("paraPrIDRef"), p.get("styleIDRef")) == (sh["attrs"]["paraPrIDRef"], sh["attrs"]["styleIDRef"])   # 문단 모양 · 스타일은 대표 것
    after = {k for k, *_ in M.diff(M.look(doc, ov, "p6109"), M.look(doc, ov, "p13421"))}
    assert "letter" in after and after <= {"lead", "letter", "gap", "line2Mm", "form"}                            # 문단 모양 · 레터 글자 · 본문 바탕 글자는 대표 것 — 남은 다름은 접두뿐(form = 두 줄이 다른 표에 있다는 「표」 줄: spec_hwpx_웹편집 ② §8-11)
    assert M.match_one(doc, ov, "p13429", sh, left) == "o"                                                 # 같은 서식의 표지 없는 줄은 전처럼 완전히
    assert _text(doc, "p13429").startswith("o ") and ov["lines"]["p13429"]["letter"] == "o" and len(left) == 1


def test_mark_between_the_blanks_is_shape_only_and_left(sess):
    doc, ov = _fresh(sess)
    sh = M.rep_shape(doc, ov, "p12684")
    p = doc._ids["p12696"]
    text0 = doc._text(p)
    assert M.parts(doc, ov, "p12696")[:3] == ("     ", "-", " ") and sh["lead"] == "    " and _pens(doc, "p12696") == [(2, 21)]
    left = []
    assert M.match_one(doc, ov, "p12696", sh, left) == "-"
    assert left == [{"id": "p12696", "why": "inside", "kinds": ["형광펜"]}]                               # 바꿀 레터 앞 빈칸 사이에 시작 표지(MarkBlock)
    assert doc._text(p) == text0 and _pens(doc, "p12696") == [(2, 21)] and p.get("paraPrIDRef") == sh["attrs"]["paraPrIDRef"]


# ---------------------------------------------------------------- 확정 서식 ①(묶음 빈칸) — 필드 · 변경 추적 범위 안의 레터 뒤 빈칸
def test_place_leaves_a_gap_inside_a_hyperlink_or_tracked_change(sess):
    doc, ov = _fresh(sess)
    p2 = doc._ids["p12686"]                                                                                # 형광펜은 막지 않는다 — set_chars 가 표지를 지킨다
    _pen(doc, p2, 4, len(doc._text(p2)))
    m = OP.Measure(doc)
    assert OC.place(doc, ov, "p12686", m) and M.parts(doc, ov, "p12686")[2] == NB
    assert _pens(doc, "p12686") == [(4, len(doc._text(p2)))] and not OC.needs(doc, ov, "p12686", m)
    pid = "p12684"                                                                                         # T23 L3 대표 「    - 특허출원번호/발명명칭 : 」
    n = len(_text(doc, pid))
    m = OP.Measure(doc)                                                                                    # 레벨 판정(_held)은 재개 하나에 레벨마다 한 번 — 문서를 바꿨으니 새 재개로
    assert M.parts(doc, ov, pid)[:3] == ("    ", "-", " ") and OC._gap(doc, pid, "-") == (5, " ") and OC.needs(doc, ov, pid, m)
    _field(doc, pid, 5, n)                                                                                 # 레터 뒤 빈칸부터 글 끝까지 하이퍼링크
    m = OP.Measure(doc)
    assert _spans(doc, pid) == [("field", 5, n)] and OC._gap(doc, pid, "-") is None and OC._held(doc, ov, "23", 3, m)
    OC.place(doc, ov, pid, m)
    assert M.parts(doc, ov, pid)[2] == " " and _spans(doc, pid) == [("field", 5, n)]                       # 묶음 빈칸으로 안 바꿈 · 필드 그대로
    assert not OC.needs(doc, ov, pid, m)                                                                   # needs 도 같이 따른다(자리 규칙은 걸렸다)
    p3 = doc._ids["p12688"]                                                                              # 변경 추적(넣음) 범위가 레터 뒤 빈칸을 덮음
    _ins(doc, p3, 4, p3.makeelement(_p("insertBegin"), {"Id": "9", "TcId": "1"}), False)
    _ins(doc, p3, 6, p3.makeelement(_p("insertEnd"), {"Id": "9", "TcId": "1"}), True)
    assert _spans(doc, "p12688") == [("track", 4, 6)] and OC._gap(doc, "p12688", "-") is None
    OC.place(doc, ov, "p12688", m)
    assert M.parts(doc, ov, "p12688")[2] == " " and not OC.needs(doc, ov, "p12688", m)
    assert M.parts(doc, ov, "p12698")[:3] == ("     ", "-", " ")                                           # 레터까지만 덮는 필드(레터 뒤 빈칸 앞에서 끝남)는 막지 않는다
    _field(doc, "p12698", 0, 6, fid="902")
    assert _spans(doc, "p12698") == [("field", 0, 6)] and OC._gap(doc, "p12698", "-") == (6, " ")


def _groups(doc, ov, tid, lv):
    return [(g["count"], g["look"]["gap"]) for g in M.variants(doc, ov, tid, lv)["groups"]]


@pytest.mark.parametrize("who", ["rep", "mate"])
def test_gap_inside_a_field_on_the_rep_side_keeps_the_level_in_one_format(sess, who):
    """대표(또는 대표와 서식이 같은 줄)의 레터 뒤 빈칸이 필드 안이면 그 레벨은 묶음 빈칸으로 안 바꾼다(`_held` — 한 레벨 = 한 서식).
    전에는 막힌 줄만 보통 빈칸으로 남고 나머지가 묶음 빈칸이 되어 같은 서식이던 줄이 「다른 서식」 으로 갈라졌고(남긴 줄로도 안 잡힘), 대표가 막혔으면 맞추기를 거듭해도
    대표와 다른 줄이 4 → 6 → 6 으로 안 줄었다(2026-11-17 검토 — artifacts/markers_astra_2026-11-17/tmp_stateR/probe_rep_field.py · tmp_regress/probe_rep_field_drift.py)."""
    doc, ov = _fresh(sess)
    rep = "p12684"                                                                                         # T23 L3 대표
    mates = OC._mates(doc, ov, "23", 3, rep)
    pid = rep if who == "rep" else mates[0]
    lead, tok, gap, plen, text = M.parts(doc, ov, pid)
    assert gap == " "
    _field(doc, pid, len(lead) + len(tok), len(text))                                                      # 레터 뒤 빈칸부터 글 끝까지 하이퍼링크
    g0 = _groups(doc, ov, "23", 3)
    left = []
    OC.settle(doc, ov, "23", 3, (), OP.Measure(doc), left=left)
    assert _groups(doc, ov, "23", 3) == g0 and left == []                                                  # 대표 갈래가 안 갈라짐(모두 보통 빈칸 그대로)
    assert all(M.same(M.look(doc, ov, p), M.look(doc, ov, rep)) for p in mates)
    _, ids = M.match_set(doc, ov, "23", 3, None, None)
    OC.settle(doc, ov, "23", 3, ids, OP.Measure(doc), left=left)
    v = M.variants(doc, ov, "23", 3)                                                                       # 다른 서식을 맞추면 한 서식으로 모인다 — 빈칸 사이에 형광펜이 든 p12696(MARKED)만 남긴 줄
    assert [x["id"] for x in left] == ["p12696"] and [g["paras"] for g in v["groups"][1:]] == [["p12696"]]
    assert M.match_set(doc, ov, "23", 3, None, None)[1] == ["p12696"]                                      # 다시 맞출 것은 그 줄뿐(맞추기가 끝난다)
    assert not [p for p in OC.pending(doc, ov, {"23"}) if int(ov["lines"][p]["level"]) == 3]
    assert _spans(doc, pid) == [("field", len(lead) + len(tok), len(text))]


def test_gap_under_a_field_that_crosses_the_paragraph_is_left(sess):
    """짝이 이 문단 밖에 있는 표지(문단을 넘는 책갈피 · 변경 추적) — `_gap` 도 prefix_keep_marks(unpaired)처럼 막는다: 짝 없는 시작 표지는 그 자리부터 문단 끝까지 ·
    짝 없는 끝 표지는 문단 처음부터 그 자리까지(2026-11-17 검토: 전에는 짝지은 범위만 보아 묶음 빈칸으로 바꿨다 — tmp_advxml/r4_gap_unpaired.py)."""
    doc, ov = _fresh(sess)
    pid = "p12698"                                                                                         # T23 L3 「     - …」(대표 갈래 아님)
    assert M.parts(doc, ov, pid)[:3] == ("     ", "-", " ") and OC._gap(doc, pid, "-") == (6, " ")
    p = doc._ids[pid]

    def ctrl(pos, xml):
        r, i = doc._cut(p, pos)
        r.insert(i, etree.fromstring(f'<hp:ctrl xmlns:hp="{HP}">{xml}</hp:ctrl>'))
        doc._touch(p)
    ctrl(3, '<hp:fieldEnd beginIDRef="904"/>')                                                             # 끝 표지만(시작은 앞 문단) — 레터 앞에서 끝나면 막지 않는다
    assert doc.mark_spans(p) == ([], False) and OC._gap(doc, pid, "-") == (6, " ")
    ctrl(0, '<hp:fieldBegin id="903" type="BOOKMARK"/>')                                                   # 시작 표지만(끝은 다음 문단) — 문단 끝까지 덮음
    assert OC._gap(doc, pid, "-") is None and OC._blocked(doc, pid, "-") == "field"
    with pytest.raises(MarkBlock) as e:
        doc.prefix_keep_marks(pid, "     ", "-", " ", "    ", NB, None)
    assert e.value.why == "unpaired"                                                                        # 같은 줄에 두 판정이 같은 편
    OC.place(doc, ov, pid, OP.Measure(doc))
    assert M.parts(doc, ov, pid)[2] == " "
    q = doc._ids["p12688"]                                                                                 # 변경 추적(넣기) 끝 표지만 — 레터 뒤 빈칸 뒤에서 끝남 → 막음
    _ins(doc, q, 7, q.makeelement(_p("insertEnd"), {"Id": "9", "TcId": "1"}), True)
    assert doc.mark_spans(q)[1] is False and OC._gap(doc, "p12688", "-") is None and OC._blocked(doc, "p12688", "-") == "track"


def test_measure_cache_lets_the_document_go(sess):
    """outline_match._MEASURES 의 글자 폭 재개가 문서를 약하게 쥔다 — 서식 갈래를 읽은(look → _at_text) 문서도 버리면 풀린다
    (전에는 Measure(doc).doc 가 약한 키를 강하게 쥐어 실행 취소 · 되돌림이 새 문서를 열 때마다 옛 문서 전체가 남았다 — 2026-11-17 검토 tmp_stateR/probe_measure_leak.py)."""
    import gc
    import weakref
    doc, ov = _fresh(sess)
    M.variants(doc, ov, "23", 3)
    assert doc in M._MEASURES
    ref = weakref.ref(doc)
    del doc
    gc.collect()
    assert ref() is None


# ---------------------------------------------------------------- 끝점 — 400 이 아니라 반영 · 실행 취소
def test_slot_match_endpoint_keeps_marked_lines_and_undo_restores_the_bytes(sess):
    c, d, s, _ = sess
    assert c.get(f"/api/docs/{d}/download").content == _base()
    r = c.post(f"/api/docs/{d}/outline/slots/9/1/match", json={"like": "p9209"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert {"p9209", "p10021"} <= set(j["changed"])
    assert _text(s.doc, "p9209") == "    [주관연구개발기관 : 기관명]" and _pens(s.doc, "p9209") == [(4, 20)]
    assert M.same(M.look(s.doc, s.outline, "p9209"), M.look(s.doc, s.outline, "p1691"))
    assert not [x for x in j.get("left") or [] if x["id"] in ("p9209", "p10021")]                         # 완전히 맞춘 줄은 남긴 줄이 아니다
    text0 = _text(s.doc, "p13421")
    r = c.post(f"/api/docs/{d}/outline/slots/14/1/match", json={"like": "p13421"})                         # 레터를 바꿔야 하는데 형광펜이 레터를 덮은 줄 — 400 이 아니다
    assert r.status_code == 200, r.text
    j = r.json()
    assert _text(s.doc, "p13421") == text0[:2] + NB + text0[3:] and _pens(s.doc, "p13421") == [(1, 2)]    # 레터는 그대로 — 확정 서식 ①(레터 뒤 묶음 빈칸)만 걸림
    assert s.outline["lines"]["p13421"]["letter"] == "ㅇ" and _text(s.doc, "p13429").startswith("o" + NB)  # 같이 고른 표지 없는 줄은 대표 레터로
    if "left" in j:
        assert [(x["id"], x["why"]) for x in j["left"]] == [("p13421", "letter")]
    _undo_all(c, d, s)                                                                                     # 실행 취소로 처음 바이트


def test_template_match_does_not_roll_back_for_marked_lines(sess):
    """템플릿 맞추기(「모두 반영」 과 같은 몸 apply_templates)가 형광펜 든 줄 때문에 400 으로 통째 되돌려지지 않는다."""
    c, d, s, _ = sess
    r = c.post(f"/api/docs/{d}/outline/templates/9/match", json={"levels": [{"level": 1, "likes": ["p9209", "p6128"]}]})
    assert r.status_code == 200, r.text
    assert _text(s.doc, "p9209") == "    [주관연구개발기관 : 기관명]" and _pens(s.doc, "p9209") == [(4, 20)]
    assert _text(s.doc, "p6128") == "    [공동연구개발기관 : 기업명2]" and _pens(s.doc, "p6128") == [(4, 21)]
    r = c.post(f"/api/docs/{d}/outline/templates/23/match", json={"levels": [{"level": 3, "likes": ["p12696"]}]})
    assert r.status_code == 200, r.text
    assert _pens(s.doc, "p12696") == [(2, 21)] and M.parts(s.doc, s.outline, "p12698")[0] == "    "      # 표지 사이 줄은 남고 같은 서식의 다른 줄은 맞춤
    _undo_all(c, d, s)
