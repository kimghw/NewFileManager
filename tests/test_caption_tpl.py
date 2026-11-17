"""캡션 템플릿 「CN」(spec_hwpx_웹편집 ② §8-10) — 연구개발계획서 양식 + 2단계(LLM 끔).
양식의 글 캡션: 표 위의 화살괄호 줄 「 <연구개발성과 성능 목표> 」(p1020) · 「<기술개발 핵심어>」(p1311) · 「<핵심기술요소(CTE) 목록>」(p11871) — 서식이 저마다 다르다.
작성요령 표(TEMP) 안의 「<표 1> 노출수준(가능성)」(p6361) · 「<표 2> …」(p6387) · 「<표 3> …」(p6423) · 「<표 4> …」(p6468)은 끝점이 캡션 줄에서 뺀다(모듈만 부르면 보인다).
개체 캡션(hp:caption)은 양식에 없어 `_with_captions` 가 표 다섯에 붙여 만든 문서로 본다."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app import caption_tpl as C
from app import heading_guides as G
from app import heading_rules as R
from app import caption_tpl_api, heading_runs, server
from app.hwpx_doc import CAPTION, PIC, RUN, SUBLIST, TBL, HwpxDoc, P, T, _p

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
MADE = ["< 첫째 표 >", "<　둘째 표　＞", " <셋째 표> ", "표 1-1 넷째 표", "표 1-2  다섯째 표"]  # _with_captions 가 붙이는 개체 캡션


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _top_tables(doc):
    return [o for sec in doc._sections for p in sec.iterchildren(P) for r in p.iterchildren(RUN) for o in r.iterchildren(TBL)]


def _caption(tbl, text, like):
    """표 tbl 에 위쪽 캡션(hp:caption — outMargin 바로 뒤)을 붙인다. 문단 모양·글자 모양은 like 문단 것."""
    cap = tbl.makeelement(CAPTION, {"side": "TOP", "fullSz": "0", "width": "8504", "gap": "850", "lastWidth": "47624"})
    sub = etree.SubElement(cap, SUBLIST, {"id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK", "vertAlign": "TOP", "linkListIDRef": "0",
                                          "linkListNextIDRef": "0", "textWidth": "0", "textHeight": "0", "hasTextRef": "0", "hasNumRef": "0"})
    p = etree.SubElement(sub, P, {"id": "0", "paraPrIDRef": like.get("paraPrIDRef"), "styleIDRef": like.get("styleIDRef", "0"), "pageBreak": "0", "columnBreak": "0", "merged": "0"})
    run = etree.SubElement(p, RUN, {"charPrIDRef": next(like.iterchildren(RUN)).get("charPrIDRef")})
    etree.SubElement(run, T).text = text
    tbl.find(_p("outMargin")).addnext(cap)
    return p


def _with_captions(src):
    """양식의 본문 표 다섯에 개체 캡션을 붙인 문서 → (bytes, 다섯 캡션의 글). 넷째까지는 「<표 2>」 줄(p6387)의 모양, 다섯째만 「<표 1>」 줄(p6361)의 모양(서식이 다른 줄)."""
    doc = HwpxDoc(src)
    doc.blocks()
    a, b = doc._ids["p6387"], doc._ids["p6361"]
    tables = [t for t in _top_tables(doc) if len(list(t.iter(TBL))) == 1][2:7]
    for i, (t, text) in enumerate(zip(tables, MADE)):
        _caption(t, text, b if i == 4 else a)
        doc._touch(t)
    return doc.save()


def _open(tmp, data, name):
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
                     "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}.items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": (name, data, "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        assert c.get(f"/api/docs/{d}/outline").status_code == 200  # 오버레이를 만든다(캡션 템플릿의 번호·대표가 여기에 든다)
        yield c, d, s
        server.DOCS.clear()


@pytest.fixture(scope="module")
def sess(tmp_path_factory):
    yield from _open(tmp_path_factory.mktemp("caption_tpl"), PLAN.read_bytes(), PLAN.name)


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    yield from _open(tmp_path_factory.mktemp("caption_made"), _with_captions(PLAN.read_bytes()), "캡션_붙인_양식.hwpx")


def _caps(c, d, **params):
    r = c.get(f"/api/docs/{d}/captions", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _tpl(caps, name, kind="table"):
    return next(t for t in caps["templates"] if t["name"] == name and t["kind"] == kind)


def _undo_all(c, d, s, data):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == data


# ---------------------------------------------------------------- 꼴 읽기
def test_parse_reads_caption_shapes():
    f = C.parse("<표 1> 노출수준")
    assert (f["shape"], f["tok"], f["gap"], f["plen"], f["key"], f["word"]) == ("label", "<표 1>", " ", 6, "<표n>", "table")
    assert C.parse("< 표 12 >  제목")["key"] == "<표n>" and C.parse("＜표 3＞ 제목")["key"] == "<표n>"  # 안쪽 빈칸·전각 괄호는 같은 레터(서식의 다름)
    assert C.parse("표 5-2 국내 주요 기관")["tok"] == "표 5-2" and C.parse("표 5-2 국내 주요 기관")["key"] == "표n-n"
    assert C.parse("  [그림 2] 구성도")["lead"] == "  " and C.parse("[그림 2] 구성도")["word"] == "figure" and C.parse("그림 3. 개념도")["tok"] == "그림 3."
    assert C.parse("Fig. 4 Overview")["key"] == "fig.n" and C.parse("Table 2: Results")["tok"] == "Table 2:"
    assert C.parse("표 1. 2024년 실적")["tok"] == "표 1."  # 번호 구분자 뒤에 빈칸이 있으면 번호가 아니다
    w = C.parse(" <　데이터 항목 표준(안)　＞ ")
    assert (w["shape"], w["lead"], w["tok"], w["gap"], w["close"], w["key"]) == ("wrap", " ", "<", "　", "　＞ ", "<…>")
    assert C.parse("<표 1. 제목>")["shape"] == "wrap"  # 번호 뒤에 닫는 괄호가 없으면 머리가 아니라 줄 전체 괄호
    assert C.parse("〈 제목 〉")["key"] == "〈…〉" and C.parse("[ 제목 ]")["key"] == "[…]"
    n = C.parse("*. 출처 : 한국해양안보포럼")
    assert (n["shape"], n["tok"], n["gap"], n["key"]) == ("note", "*.", " ", "*.") and C.parse("※ 2024년 기준")["shape"] == "note" and C.parse("출처: 시사저널")["key"] == "출처:"
    assert C.parse("Hybrid 차단기 시제품")["key"] == "글" and C.parse("이어지는 글", first=False)["key"] == "글+" and C.parse("  ") is None
    # 글 캡션(본문 문단)은 번호 붙은 머리와 화살괄호 줄만 — 문장·대괄호 줄·출처 줄은 아님
    assert C.parse("Table 2에 따른 시험 수행", struct=False) is None and C.parse("[ 제목 ]", struct=False) is None and C.parse("*. 출처", struct=False) is None
    assert C.parse("< A > 와 < B >", struct=False) is None and C.parse("<표 1> 제목", struct=False)["shape"] == "label"


def test_names_shown_and_renumber():
    assert C._name("label", "<표n>", "< 표 12 >") == "< 표 N >" and C._name("wrap", "<…>", "＜") == "< … >" and C._name("plain", "글+", "") == "이어지는 줄"
    assert C.shown("close", " >") == "1칸 + 「>」" and C.shown("close", "　＞") == "전각 1칸 + 「＞」" and C.shown("close", "") == "—" and C.shown("lead", "  ") == "2칸"
    assert C._renumber("< 표 1 >", "<표12>") == "< 표 12 >" and C._renumber("표 1-1.", "표 3-12") == "표 3-12." and C._renumber("표 1-1", "표 3") == "표 3"
    assert C.LABELS["lead"] == "앞 빈칸" and C.LABELS["close"] == "닫는 괄호" and C.KEYS[:4] == ("lead", "letter", "gap", "close")


def test_text_caption_needs_a_table_or_figure_next_to_it():
    """글 캡션 — 이웃 문단이 표·그림이어야 한다: 「표 N」 은 표(아래가 먼저), 「그림 N」 은 개체(위가 먼저), 화살괄호 줄은 표 위 · 그림 아래만."""
    class Doc:
        def is_spacer(self, q):
            return not len(q)

    def flow(*items):
        root = etree.Element("root")
        out = []
        for it in items:
            p = etree.SubElement(root, P)
            if it in (TBL, PIC):
                etree.SubElement(etree.SubElement(p, RUN), it)
            elif it is not None:
                etree.SubElement(etree.SubElement(p, RUN), T).text = it
            out.append(p)
        return out
    at = lambda items, i: (lambda ps: (r := C._text_caption(Doc(), ps[i], items[i])) and (r[0]["shape"], r[1], r[2]))(flow(*items))  # noqa: E731
    assert at(["표 1 제목", TBL], 0) == ("label", "table", "top") and at([TBL, "표 1 제목"], 1) == ("label", "table", "bottom")
    assert at([TBL, None, "표 1 제목", None, None, TBL], 2) == ("label", "table", "top")  # 사이의 간격 문단은 둘까지 건너뛴다
    assert at(["표 1 제목", None, None, None, TBL], 0) is None and at(["표 1 은 다음과 같다", "본문"], 0) is None and at([PIC, "표 1 제목"], 1) is None
    assert at([PIC, "그림 2. 구성도"], 1) == ("label", "figure", "bottom") and at(["그림 2. 구성도", PIC], 0) == ("label", "figure", "top")
    assert at([PIC, "< 구성도 >", "본문"], 1) == ("wrap", "figure", "bottom") and at(["< 표 제목 >", TBL], 0) == ("wrap", "table", "top")
    assert at([TBL, "< 표 아래 글 >", "본문"], 1) is None and at(["< 그림 위 글 >", PIC], 0) is None  # 화살괄호 줄은 표 위 · 그림 아래만
    assert at([PIC, "< 제목 >", TBL], 1) == ("wrap", "table", "top")


# ---------------------------------------------------------------- 양식의 글 캡션
def test_templates_group_text_captions(sess):
    c, d, s = sess
    caps = _caps(c, d)
    t = _tpl(caps, "< … >")
    assert t["id"].startswith("C") and t["kindName"] == "표" and t["shape"] == "wrap" and t["total"] == 3 and t["sides"] == {"top": 3} and t["text"] == 3 and t["struct"] == 0
    assert t["rep"] == "p1020" and t["repSet"] is False and t["others"] == 2 and t["frozen"] == 0 and caps["stored"] is True  # 서식이 저마다 다르면 문서에 먼저 나온 줄이 대표
    rep, *rest = t["groups"]
    assert rep["rep"] and rep["paras"] == ["p1020"] and rep["diff"] == []
    by = {g["key"]: g for g in rest}
    assert set(by) == {"p1311", "p11871"} and by["p1311"]["diff"][0] == ["lead", "앞 빈칸", "1칸", "없음"] and ["sizePt", "크기", "13pt", "10pt"] in by["p11871"]["diff"]
    assert rep["look"]["letter"] == "<" and rep["raw"]["close"] == ">" and rep["look"]["close"] == "「>」" and rep["look"]["lead"] == "1칸"  # 닫는 괄호 뒤 빈칸은 견주지 않는다
    assert all(caps["lines"][p] == {"tpl": t["id"], "no": t["no"], "shape": "wrap"} for p in ("p1020", "p1311", "p11871"))
    assert caps["keys"][:4] == [["lead", "앞 빈칸"], ["letter", "레터"], ["gap", "레터 뒤 빈칸"], ["close", "닫는 괄호"]]
    assert not set(caps["lines"]) & set(s.outline["lines"])  # 개요 줄은 캡션 줄이 아니다
    one = _caps(c, d, tpl=t["id"])  # 그 템플릿만 — 다른 템플릿은 갈래를 셈하지 않는다
    assert _tpl(one, "< … >")["groups"] and all(not x["groups"] for x in one["templates"] if x["id"] != t["id"])
    # 작성요령 표(TEMP) 안의 「<표 N>」 줄은 캡션 줄이 아니다(헤딩 후보에서 빼는 것과 같다) — 모듈은 거르지 않고, 끝점이 TEMP 문단을 빼고 부른다
    assert not {"p6361", "p6387", "p6423", "p6468"} & set(caps["lines"]) and not any(x["name"] == "<표 N>" for x in caps["templates"])
    lab = _tpl(C.model(s.doc, {}), "<표 N>")
    assert lab["shape"] == "label" and lab["total"] == 4 and lab["rep"] == "p6387" and lab["others"] == 2 and lab["groups"][0]["paras"] == ["p6387", "p6423"]
    assert ["line2Mm", "2번째 줄", "0mm", "14.8mm"] in next(g for g in lab["groups"] if g["key"] == "p6361")["diff"] and lab["groups"][0]["look"]["letter"] == "<표 #>"


def test_set_rep_is_model_only_and_undoable(sess):
    c, d, s = sess
    t = _tpl(_caps(c, d), "< … >")
    r = c.put(f"/api/docs/{d}/captions/{t['id']}/rep", json={"para": "p1311"})
    assert r.status_code == 200, r.text
    now = _tpl(r.json()["captions"], "< … >")
    assert now["rep"] == "p1311" and now["repSet"] is True and now["others"] == 2 and now["id"] == t["id"] and now["groups"][0]["paras"] == ["p1311"]
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()  # 문서는 안 바뀐다
    assert s.outline["caps"]["reps"] == {t["key"]: "p1311"} and r.json()["undo"] >= 1
    assert c.put(f"/api/docs/{d}/captions/{t['id']}/rep", json={"para": "p970"}).status_code == 400  # 그 템플릿의 줄이 아님
    assert c.put(f"/api/docs/{d}/captions/{t['id']}/rep", json={"para": "p6361"}).status_code == 400  # TEMP 문단은 캡션 줄이 아니다
    assert c.put(f"/api/docs/{d}/captions/C99/rep", json={"para": "p1311"}).status_code == 404
    assert c.put(f"/api/docs/{d}/captions/{t['id']}/rep", json={}).status_code == 400
    _undo_all(c, d, s, PLAN.read_bytes())
    back = _tpl(_caps(c, d), "< … >")
    assert back["rep"] == "p1020" and back["repSet"] is False and back["id"] == t["id"]  # 실행 취소 — 대표도 돌아오고 번호는 그대로


def test_match_conforms_other_lines_to_the_rep(sess):
    c, d, s = sess
    t = _tpl(_caps(c, d), "< … >")
    rep = s.doc._ids["p1020"]
    want = (rep.get("paraPrIDRef"), rep.get("styleIDRef"))
    r = c.post(f"/api/docs/{d}/captions/{t['id']}/match", json={})
    assert r.status_code == 200, r.text
    r = r.json()
    assert r["changed"] == ["p1311", "p11871"] and r["frozen"] == [] and {b["id"] for b in r["tops"]["blocks"]} >= {"p1311", "p11871"}
    now = _tpl(r["captions"], "< … >")
    assert now["others"] == 0 and len(now["groups"]) == 1 and now["groups"][0]["count"] == 3
    for pid, text in (("p1311", " <기술개발 핵심어>"), ("p11871", " <핵심기술요소(CTE) 목록>")):  # 앞 빈칸 1칸이 대표처럼 · 제목은 그대로
        p = s.doc._ids[pid]
        assert (p.get("paraPrIDRef"), p.get("styleIDRef")) == want and s.doc._text(p) == text
    assert s.doc._text(rep) == " <연구개발성과 성능 목표> "  # 대표는 안 바뀐다
    assert c.post(f"/api/docs/{d}/captions/{t['id']}/match", json={}).json()["nothing"] is True  # 다시 — 맞출 줄 없음(편집을 열지 않는다)
    HwpxDoc(c.get(f"/api/docs/{d}/download").content).blocks()  # 저장본이 다시 열린다
    assert s.state()["undo"] == 1
    _undo_all(c, d, s, PLAN.read_bytes())


def test_match_like_takes_only_that_variant(sess):
    c, d, s = sess
    t = _tpl(_caps(c, d), "< … >")
    r = c.post(f"/api/docs/{d}/captions/{t['id']}/match", json={"like": "p11871"})
    assert r.status_code == 200, r.text
    assert r.json()["changed"] == ["p11871"] and _tpl(r.json()["captions"], "< … >")["others"] == 1
    assert c.post(f"/api/docs/{d}/captions/{t['id']}/match", json={"like": "p970"}).status_code == 400
    assert c.post(f"/api/docs/{d}/captions/C99/match", json={}).status_code == 404
    assert c.post(f"/api/docs/{d}/captions/{t['id']}/match", json={"paras": "p1311"}).status_code == 400
    _undo_all(c, d, s, PLAN.read_bytes())


# ---------------------------------------------------------------- 개체 캡션(hp:caption)
def test_object_captions_become_templates(made):
    c, d, s = made
    caps = _caps(c, d)
    w = _tpl(caps, "< … >")
    assert w["shape"] == "wrap" and w["struct"] >= 3 and w["sides"].get("top", 0) >= 3
    texts = {s.doc._text(s.doc._ids[p]): p for p, x in caps["lines"].items() if x["tpl"] == w["id"]}
    assert set(MADE[:3]) <= set(texts)
    rep = next(g for g in w["groups"] if g["rep"])
    d2 = next(g for g in w["groups"] if texts[MADE[1]] in g["paras"])["diff"]
    if texts[MADE[0]] in rep["paras"]:  # 대표가 「< 첫째 표 >」 의 서식이면 — 전각 빈칸·전각 괄호가 다른 값으로 보인다
        assert ["gap", "레터 뒤 빈칸", "1칸", "전각 1칸"] in d2 and ["close", "닫는 괄호", "1칸 + 「>」", "전각 1칸 + 「＞」"] in d2
    lab = _tpl(caps, "표 N-N")
    assert lab["total"] == 2 and lab["struct"] == 2 and lab["others"] == 1 and caps["missed"] == 0


def test_match_rewrites_brackets_and_blanks_of_wrapped_captions(made):
    c, d, s = made
    data = c.get(f"/api/docs/{d}/download").content
    caps = _caps(c, d)
    w = _tpl(caps, "< … >")
    ids = {s.doc._text(s.doc._ids[p]): p for p, x in caps["lines"].items() if x["tpl"] == w["id"]}
    first, second, third = (ids[x] for x in MADE[:3])
    assert c.put(f"/api/docs/{d}/captions/{w['id']}/rep", json={"para": first}).status_code == 200
    r = c.post(f"/api/docs/{d}/captions/{w['id']}/match", json={"likes": [second, third]})
    assert r.status_code == 200, r.text
    assert set(r.json()["changed"]) >= {second, third}
    assert s.doc._text(s.doc._ids[second]) == "< 둘째 표 >" and s.doc._text(s.doc._ids[third]) == "< 셋째 표 >"  # 괄호 글자 · 안쪽 빈칸 · 앞뒤 빈칸이 대표 꼴로
    lab = _tpl(_caps(c, d), "표 N-N")
    r = c.post(f"/api/docs/{d}/captions/{lab['id']}/match", json={})
    assert r.status_code == 200, r.text
    rep_p, other = (s.doc._ids[p] for p in (lab["rep"], r.json()["changed"][0]))
    assert other.get("paraPrIDRef") == rep_p.get("paraPrIDRef") and {s.doc._text(rep_p), s.doc._text(other)} == {"표 1-1 넷째 표", "표 1-2 다섯째 표"}  # 레터 뒤 빈칸 2칸 → 1칸 · 번호는 제 번호
    again = HwpxDoc(c.get(f"/api/docs/{d}/download").content)
    again.blocks()
    assert sum(1 for sec in again._sections for _ in sec.iter(CAPTION)) == 5
    _undo_all(c, d, s, data)


def test_numbers_stay_and_carry_to_a_new_overlay(made):
    c, d, s = made
    caps = _caps(c, d)
    ids = dict(s.outline["caps"]["ids"])
    assert sorted(ids.values()) == list(range(1, len(ids) + 1)) and {t["key"] for t in caps["templates"]} == set(ids)
    st = {"ids": {"table|label|없는꼴": 1, **{k: v + 1 for k, v in ids.items()}}, "reps": {}}  # 문서에 없는 템플릿의 번호는 비워 둔 채 지킨다
    m = C.model(s.doc, st, set(s.outline["lines"]) | caption_tpl_api._temp(s))  # 끝점과 같은 거르기(개요 줄 · TEMP 문단)
    assert [t["no"] for t in m["templates"]] == sorted(v + 1 for v in ids.values()) and C.key_of(st, "C1") == "table|label|없는꼴" and C.key_of(st, "T1") is None
    new = {"lines": {}}
    C.carry(s.outline, new)
    assert new["caps"] == s.outline["caps"] and new["caps"] is not s.outline["caps"]
    C.carry(None, new)
    C.carry({}, {"lines": {}})


def test_frozen_head_keeps_its_text(made):
    """머리에 자동 번호(hp:autoNum)가 든 캡션 — 글은 다시 쓰지 않고 모양만 맞춘다."""
    c, d, s = made
    doc = HwpxDoc(c.get(f"/api/docs/{d}/download").content)  # 세션의 문서는 안 건드린다 — 저장본을 따로 열어서
    doc.blocks()
    lines, _ = C.scan(doc)
    a, b = [ln for ln in lines if ln["shape"] == "label" and ln["struct"]]
    p = doc._ids[b["id"]]
    run = next(p.iterchildren(RUN))
    t = next(run.iterchildren(T))
    t.text, tail = "표 ", t.text[len("표 1-2"):]
    ctrl = etree.SubElement(run, _p("ctrl"))
    etree.SubElement(ctrl, _p("autoNum"), {"num": "7", "numType": "TABLE"})
    etree.SubElement(run, T).text = tail
    doc._touch(p)
    doc.blocks()
    b2 = next(ln for ln in C.scan(doc)[0] if ln["id"] == b["id"])
    assert b2["shape"] == "label" and C.frozen(doc, b2) and not C.frozen(doc, a)
    was = doc._text(p)
    r = C.conform(doc, b2, C.shape(doc, a))
    assert r == {"id": b["id"], "text": False, "frozen": True} and doc._text(p) == was and p.get("paraPrIDRef") == doc._ids[a["id"]].get("paraPrIDRef")
    assert p.find(f"{RUN}/{_p('ctrl')}/{_p('autoNum')}") is not None


def test_docx_and_no_overlay(tmp_path):
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp_path / "works", "NFM_RENDER": tmp_path / "render", "NFM_HEADINGS": tmp_path / "heads"}.items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        dx = c.post("/api/docs", files={"file": ("기술수요조사서.docx", (ROOT / "samples" / "기술수요조사서.docx").read_bytes(), "application/octet-stream")}).json()["docId"]
        assert c.get(f"/api/docs/{dx}/captions").json()["off"] is True and c.post(f"/api/docs/{dx}/captions/C1/match", json={}).status_code == 400
        hx = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}).json()["docId"]
        if server._outline_ov(server.DOCS[hx]) is None:  # 2단계 전 — 템플릿은 보이지만(번호는 문서 차례) 대표는 못 정한다
            caps = c.get(f"/api/docs/{hx}/captions").json()
            t = _tpl(caps, "< … >")
            assert caps["stored"] is False and t["total"] == 3
            assert c.put(f"/api/docs/{hx}/captions/{t['id']}/rep", json={"para": "p1311"}).status_code == 409
        server.DOCS.clear()
