"""헤딩 추출 1단계 고침 시험(heading_extract) — 형제 묶음 키 · 레터 런 charPr id · 앞선 규칙 충돌 · pt 줄 간격 오차 · 쓸 자리 레터 뒤 공백 · 그릇 key.

LLM 은 늘 끈다. 규칙·지침 저장소는 시험마다 임시 폴더(NFM_HEADINGS). 큰 표본(연구개발계획서 양식)은 모듈에서 한 번만 뽑는다."""
import copy
from collections import defaultdict
from pathlib import Path

import pytest
from lxml import etree

from app import heading_extract as E
from app import heading_guides as G
from app import heading_rules as R
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
SMALL = SAMPLES / "기술수요조사서.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}
HPX = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _tol():
    return G.parse_tolerance(G.default_text("tolerance"))


@pytest.fixture(scope="module")
def rnd():
    return E.extract(HwpxDoc(RND.read_bytes()), store=copy.deepcopy(EMPTY), doc_key="rnd", tol=_tol())


def _fake_rec(n, size, **kw):
    rec = {"id": f"r{n}", "n": n, "kind": "plain", "blank": False, "gap": "", "leadCode": "", "gapCode": "", "leadSpaces": 0, "leadMm": 0.0,
           "para": {"align": "justify", "indentLeftMm": 0.0, "indentRightMm": 0.0, "firstLineMm": 0.0, "spaceBeforePt": 0.0, "spaceAfterPt": 0.0,
                    "lineSpacing": {"type": "PERCENT", "value": 160, "unit": "%"}},
           "char": {"text": {"charPr": "1", "font": "돋움", "sizePt": size, "bold": False}, "letter": None}}
    rec.update(kw)
    return rec


# ---- S1-sibkey: 형제 묶음 = 같은 부모 요소(임시 프록시 id 아님) ---------------------------------------------------------

def test_extract_sibling_groups_follow_parent_element(rnd):
    """_gaps 형제 묶음 = 같은 부모 hp:p 들 — 칸 subList 임시 프록시 id 로 묶으면 칸 문단이 흩어져 유효 간격이 0 이 된다."""
    recs = rnd["paras"]
    items, *_ = E.enumerate_paragraphs(HwpxDoc(RND.read_bytes()))  # 추출 뒤에 부모를 쥔다(추출 중에 쥐면 버그가 가려짐)
    real = defaultdict(list)
    for n, (p, *_r) in enumerate(items):
        real[p.getparent()].append(n)
    want = copy.deepcopy(recs)
    E._gaps([[want[i] for i in v] for v in real.values()])
    bad = [(r["id"], r.get("gaps"), w.get("gaps")) for r, w in zip(recs, want) if r.get("gaps") != w.get("gaps")]
    assert not bad, bad[:3]
    cell = next(r for r in recs if r["text"].startswith("관련 법령 및 규정과"))  # 칸 안 문단 — 위아래 빈 문단 하나씩
    assert cell["area"] == "cell" and cell["gaps"]["spacersAbove"] == 1 and cell["gaps"]["spacersBelow"] == 1 and cell["gaps"]["abovePt"] > 0


def test_extract_toc_inside_table_cell(monkeypatch):
    """표 칸 안 목차 줄 4개 — 같은 칸(형제 묶음)이므로 목차(toc)로 판정."""
    doc = HwpxDoc(RND.read_bytes())
    items, per_sec, blocks = E.enumerate_paragraphs(doc)
    by_par = defaultdict(list)
    for n, it in enumerate(items):
        by_par[it[0].getparent()].append(n)
    target = next(ns for par, ns in by_par.items() if E._local(par.tag) == "subList" and len(ns) >= 4
                  and ns[-1] - ns[0] == len(ns) - 1 and all(items[n][3] is not None for n in ns))
    del by_par  # 부모 프록시를 쥐면 id 가 안정돼 버그가 가려진다
    ids = []
    for n, line in zip(target, ["1. 서론\t1", "2. 본론\t5", "3. 결론\t9", "4. 부록\t12"]):
        items[n][3]["text"] = line
        ids.append(items[n][1])
    monkeypatch.setattr(E, "enumerate_paragraphs", lambda d: (items, per_sec, blocks))
    res = E.extract(doc, store=copy.deepcopy(EMPTY), doc_key="rnd", tol=_tol())
    by_id = {r["id"]: r for r in res["paras"]}
    assert [by_id[i]["kind"] for i in ids] == ["toc"] * 4


# ---- S1-charpr: 레터 런은 값이 다를 때만(charPr id 만 다르면 같은 글자 모양) -------------------------------------------

def _lrec(n, letter):
    text = {"charPr": "7", "font": "Dotum", "sizePt": 8.0, "bold": False, "spacingPct": -10}
    return _fake_rec(n, 8.0, kind="marker", gapCode="_1", gap=" ",
                     para={"align": "center", "indentLeftMm": 0, "indentRightMm": 0, "firstLineMm": 0, "spaceBeforePt": 0, "spaceAfterPt": 0,
                           "lineSpacing": {"type": "PERCENT", "value": 120, "unit": "%"}},
                     char={"text": text, "letter": letter(text)})


def test_letter_run_same_values_other_charpr_id_is_same_format():
    recs = [_lrec(0, lambda t: t), _lrec(1, lambda t: t),
            _lrec(2, lambda t: {**t, "charPr": "9"}),                 # charPr id 만 다름
            _lrec(3, lambda t: {**t, "charPr": "9", "bold": True})]   # 정말 다른 레터 런
    labels, formats = E.label_formats(recs, _tol())
    assert recs[2]["fp"] == recs[0]["fp"] and recs[2]["fmt"] == recs[0]["fmt"]
    assert "레터" not in labels[recs[0]["fmt"]]["name"]
    assert recs[3]["fmt"] != recs[0]["fmt"] and "레터 Dotum 8pt 굵게" in labels[recs[3]["fmt"]]["name"]
    assert len(formats) == 2
    assert recs[2]["char"]["letter"]["charPr"] == "9"  # 레코드의 레터 런(charPr id + 요약)은 그대로 남김


def test_rnd_identical_letter_run_not_named_as_letter(rnd):
    strip = lambda d: {k: v for k, v in (d or {}).items() if k != "charPr"}  # noqa: E731
    same = [r for r in rnd["paras"] if r["char"].get("letter") and strip(r["char"]["letter"]) == strip(r["char"]["text"])]
    assert same
    assert all("레터" not in rnd["formats"][r["fp"]]["name"] for r in same)
    assert all("레터" not in rnd["labels"][r["fmt"]]["name"] for r in same if rnd["labels"][r["fmt"]]["rep"] == r["fp"])


# ---- S1-firstconflict: 앞선(first) 배운 규칙이 이긴 문단은 충돌로 다시 묻지 않음 ------------------------------------------

def test_first_rule_fix_not_reported_again(rnd):
    g = next(g for g in rnd["review"]["conflicts"] if g["key"].startswith("c:b.placeholder>b.data:"))
    st = {**copy.deepcopy(EMPTY), "rules": [{"id": "l1", "name": "연도 자리", "kind": "data", "family": "year", "pattern": "20××년", "scope": "whole",
                                             "first": True, "status": "global", "enabled": True}], "lastId": 1}
    again = E.extract(HwpxDoc(RND.read_bytes()), store=st, doc_key="rnd", tol=_tol())
    ids = set(g["ids"])
    by_id = {r["id"]: r for r in again["paras"]}
    assert all(by_id[i]["rule"] == "l1" and by_id[i]["kind"] == "data" for i in ids)
    assert not [c["key"] for c in again["review"]["conflicts"] if set(c["ids"]) & ids]  # 고치기 전: ['c:l1>b.placeholder:N××']
    assert sorted(c["key"] for c in again["review"]["conflicts"]) == sorted(c["key"] for c in rnd["review"]["conflicts"] if c["key"] != g["key"])


def test_review_set_skips_only_first_rule_winners():
    """같은 문단이라도 이긴 규칙이 first 가 아니면(뒤에 붙은 배운 규칙) 충돌로 남는다."""
    def run(first):
        rule = {"id": "l1", "kind": "data", "family": "year", "pattern": "20××년", "scope": "whole", "first": first, "status": "global"}
        rules = R.active({**copy.deepcopy(EMPTY), "rules": [rule]})
        rn = R._Run()
        recs = []
        for n, t in enumerate(["20××년", "본문"]):
            c = R.classify(t, rules, rn)
            recs.append({"id": f"r{n}", "n": n, "text": t, "area": "body", "fmt": "S1", **{k: c[k] for k in ("kind", "rule", "letter", "lead")}})
        return recs, E.review_set(recs, rules, rn)["conflicts"]
    recs, conf = run(True)
    assert recs[0]["rule"] == "l1" and conf == []
    recs, conf = run(False)
    assert recs[0]["rule"] == "b.placeholder" and [c["ids"] for c in conf] == [["r0"]]


# ---- S1-linespacing: 고정·최소·여백 줄 간격(pt)은 pt 오차(lineSpacingPt)로 ----------------------------------------------

def test_label_formats_pt_line_spacing_not_compared_with_pct_tolerance():
    """FIXED·AT_LEAST·BETWEEN_LINES 줄 간격 값은 pt — lineSpacingPct(10) 문턱으로 견주면 12pt 와 21pt 가 한 S 가 된다."""
    base = {k: v for k, v in G.TOLERANCE_DEFAULT.items() if k != "lineSpacingPt"}  # 키가 없으면 1.0pt
    for tol in (base, {**base, "lineSpacingPt": 1.0}):
        for t in ("FIXED", "AT_LEAST", "BETWEEN_LINES"):
            for kind in ("plain", "empty"):
                recs = [_fake_rec(0, 10.0), _fake_rec(1, 10.0)]
                for r, v in zip(recs, (12.0, 21.0)):
                    r["kind"] = kind
                    r["para"]["lineSpacing"] = {"type": t, "value": v, "unit": "pt"}
                labels, _ = E.label_formats(recs, tol)
                assert recs[0]["fmt"] != recs[1]["fmt"] and len(labels) == 2, (t, kind)
        # 작은 pt 차이는 여전히 오차 안
        recs = [_fake_rec(0, 10.0), _fake_rec(1, 10.0)]
        for r, v in zip(recs, (16.0, 16.5)):
            r["para"]["lineSpacing"] = {"type": "FIXED", "value": v, "unit": "pt"}
        E.label_formats(recs, tol)
        assert recs[0]["fmt"] == recs[1]["fmt"]
    # 지침의 lineSpacingPt 를 따른다
    recs = [_fake_rec(0, 10.0), _fake_rec(1, 10.0)]
    for r, v in zip(recs, (12.0, 21.0)):
        r["para"]["lineSpacing"] = {"type": "FIXED", "value": v, "unit": "pt"}
    E.label_formats(recs, {**base, "lineSpacingPt": 10})
    assert recs[0]["fmt"] == recs[1]["fmt"]
    # PERCENT 는 그대로 % 문턱(160 ≈ 170, 160 ≉ 171)
    recs = [_fake_rec(0, 10.0), _fake_rec(1, 10.0), _fake_rec(2, 10.0)]
    recs[1]["para"]["lineSpacing"] = {"type": "PERCENT", "value": 170, "unit": "%"}
    recs[2]["para"]["lineSpacing"] = {"type": "PERCENT", "value": 171, "unit": "%"}
    E.label_formats(recs, base)
    assert recs[0]["fmt"] == recs[1]["fmt"] != recs[2]["fmt"]


# ---- S1-minor (a): 쓸 자리(blank) 레터는 같은 서식의 제목 있는 레터와 한 S — F 첫 문단 순서에 안 달림 -----------------------

def _marker(n, blank, gap):
    return _fake_rec(n, 13.0, kind="marker", blank=blank, gap=gap, gapCode=f"_{len(gap)}" if gap else "")


def test_label_formats_blank_marker_shares_label():
    tol = _tol()
    recs = [_marker(0, False, " "), _marker(1, False, " "), _marker(2, True, "")]
    E.label_formats(recs, tol)
    assert len({r["fp"] for r in recs}) == 2 and len({r["fmt"] for r in recs}) == 1
    # F1(레터 뒤 1칸) 첫 문단이 쓸 자리든 아니든 같은 결과 — 2칸(오차 안)은 한 S, 3칸(오차 밖)은 따로
    for gap, n_labels in (("  ", 1), ("   ", 2)):
        got = []
        for first_blank in (False, True):
            recs = [_marker(0, first_blank, " "), _marker(1, False, " "), _marker(2, False, " "), _marker(3, False, gap)]
            E.label_formats(recs, tol)
            got.append([r["fmt"] for r in recs])
            assert len({r["fmt"] for r in recs}) == n_labels, (gap, first_blank)
        assert got[0] == got[1], gap


# ---- S2-flowkey (1): 그릇마다 문서 안 유일 key ---------------------------------------------------------------------------

def _el(tag, parent=None, **a):
    a = {k: str(v) for k, v in a.items()}
    return etree.SubElement(parent, HPX + tag, a) if parent is not None else etree.Element(HPX + tag, a)


def _doc_with_containers():
    """작은 표본 끝에 글상자 A·B, 각주 A·B, 글상자 안 1×2 표(블록이 안 걷는 곳 — 표·칸 id 없음)를 붙인다."""
    doc = HwpxDoc(SMALL.read_bytes())
    sec = doc._sections[0]
    ref = list(sec.iter(HPX + "p"))[3]
    ppr, cpr = ref.get("paraPrIDRef"), next(ref.iter(HPX + "run")).get("charPrIDRef")

    def para(text):
        p = _el("p", paraPrIDRef=ppr, styleIDRef="0")
        _el("t", _el("run", p, charPrIDRef=cpr)).text = text
        return p

    def host():
        p = _el("p", paraPrIDRef=ppr, styleIDRef="0")
        sec.append(p)
        return _el("run", p, charPrIDRef=cpr)

    def sub(parent, paras):
        s = _el("subList", parent)
        for x in paras:
            s.append(x)

    sub(_el("drawText", _el("rect", host(), id="9001")), [para("1. 상자A 제목"), para("가. 상자A 하위")])
    sub(_el("drawText", _el("rect", host(), id="9002")), [para("□ 상자B 항목")])
    sub(_el("footNote", _el("ctrl", host())), [para("1. 각주A 제목")])
    sub(_el("footNote", _el("ctrl", host())), [para("□ 각주B 항목")])
    inner = _el("p", paraPrIDRef=ppr, styleIDRef="0")
    tr = _el("tr", _el("tbl", _el("run", inner, charPrIDRef=cpr), rowCnt=1, colCnt=2))
    for ci, txt in enumerate(("□ 칸1 항목", "o 칸2 항목")):
        tc = _el("tc", tr)
        sub(tc, [para(txt)])
        _el("cellAddr", tc, colAddr=ci, rowAddr=0)
        _el("cellSpan", tc, colSpan=1, rowSpan=1)
    sub(_el("drawText", _el("rect", host(), id="9003")), [inner])  # blocks() 는 drawText 를 안 걷는다 → 표·칸 id 없음
    doc._blocks_cache = None
    return doc


def _sig(c):
    return tuple(sorted((k, str(v)) for k, v in c.items() if k != "key"))


def test_extract_container_keys_unique_per_instance():
    st1 = E.extract(_doc_with_containers(), store=copy.deepcopy(EMPTY), doc_key="syn", tol=_tol())
    recs = st1["paras"]
    for r in recs:
        assert all(isinstance(c.get("key"), int) and c["key"] >= 1 for c in r["path"]), r["path"]
    # 같은 그릇 = 같은 key, 다른 그릇 = 다른 key(종류·속성이 같아도)
    keys = defaultdict(set)
    for r in recs:
        for c in r["path"]:
            keys[c["key"]].add(_sig(c))
    assert all(len(v) == 1 for v in keys.values())
    by = {r["text"]: r for r in recs if r["text"]}
    last = lambda t: by[t]["path"][-1]  # noqa: E731
    assert last("1. 상자A 제목")["key"] == last("가. 상자A 하위")["key"]
    for a, b in (("1. 상자A 제목", "□ 상자B 항목"), ("1. 각주A 제목", "□ 각주B 항목"), ("□ 칸1 항목", "o 칸2 항목")):
        assert last(a)["t"] == last(b)["t"] and last(a)["key"] != last(b)["key"], (a, b)
    assert last("□ 칸1 항목")["id"] is None  # id 없는 칸도 key 로 갈림
    assert by["□ 칸1 항목"]["path"][-2]["key"] == by["o 칸2 항목"]["path"][-2]["key"]  # 같은 표
    # 번호 = 그릇이 문서에 처음 나오는 순(바깥 먼저), 1부터 빈틈 없이
    seen = []
    for r in recs:
        for c in r["path"]:
            if c["key"] not in seen:
                seen.append(c["key"])
    assert seen == list(range(1, len(seen) + 1))
