"""헤딩 추출(spec_헤딩_추출 ② §1~§7) — 규칙식 판정·정규식 막이·규칙 저장소·지침, 1단계 추출(연구개발계획서 양식·기술수요조사서),
LLM 규칙 보강(가짜 LLM), 2단계 그래프(스크립트 대체·가짜 A/B/C 호출), API.

LLM 은 늘 끈다(NFM_LLM_BACKEND=off) — LLM 이 필요한 곳은 가짜 ask(jobs) 로 job["what"] 마다 답한다. 규칙·지침 저장소는 시험마다 임시 폴더(NFM_HEADINGS).
큰 표본(연구개발계획서 양식 7,638문단)은 모듈에서 한 번만 뽑고, 문단은 id 가 아니라 글로 찾는다."""
import copy
import json
import threading
import time
import warnings
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_llm as HL
from app import heading_rules as R
from app import heading_runs, server, works
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
SMALL = SAMPLES / "기술수요조사서.hwpx"
DOCX = SAMPLES / "기술수요조사서.docx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}
BR = "\u2028"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    """규칙·지침 저장소는 시험마다 빈 임시 폴더, LLM 은 끔, 메모리 저장소(저장 끔일 때)도 비움."""
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _tol():
    return G.parse_tolerance(G.default_text("tolerance"))


def _rules(store=None, **kw):
    return R.active(copy.deepcopy(store or EMPTY), **kw)


# ---- 표본(모듈에서 한 번) ----------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rnd_doc():
    return HwpxDoc(RND.read_bytes())


@pytest.fixture(scope="module")
def rnd(rnd_doc):
    """연구개발계획서 양식 1단계 결과 — 빈 규칙 저장소·기본 오차 기준(시험 사이에 바꾸지 않는다)."""
    return E.extract(rnd_doc, store=copy.deepcopy(EMPTY), doc_key="rnd", tol=_tol())


@pytest.fixture(scope="module")
def small():
    return E.extract(HwpxDoc(SMALL.read_bytes()), store=copy.deepcopy(EMPTY), doc_key="small", tol=_tol())


def _texty(res, rec, k):
    """rec 뒤의 글 있는 문단 k개(빈 문단·개체 문단 건너뜀)."""
    return [r for r in res["paras"][rec["n"] + 1:] if r["kind"] not in ("empty", "object")][:k]


def _find(res, prefix, *, area="body", kind=None, start=0):
    for r in res["paras"][start:]:
        if r["area"] == area and r["text"].strip().startswith(prefix) and (kind is None or r["kind"] == kind):
            return r
    raise AssertionError(f"문단을 못 찾음: {prefix!r}")


@pytest.fixture(scope="module")
def P(rnd):
    """그림 2·3 문단(글로 찾음) → 레코드."""
    out = {}
    out["toc1"] = _find(rnd, "1. 연구개발과제의 필요성", kind="toc")
    out["toc11"] = _find(rnd, "1-1. 개발 대상 기술", kind="toc")
    out["h1"] = _find(rnd, "1. 연구개발과제의 필요성", kind="marker")
    out["h11"] = _find(rnd, "1-1. 개발 대상 기술", kind="marker", start=out["h1"]["n"])
    out["sq"] = _find(rnd, "□ 연구개발기술(제품)의 정의 및 범위", start=out["h11"]["n"])
    out["o1"], out["dash"], out["dot"], out["o2"] = _texty(rnd, out["sq"], 4)
    out["stage"] = _find(rnd, "[1단계]")
    out["sec22"] = [r for r in rnd["paras"][:out["stage"]["n"]] if r["area"] == "body" and r["kind"] == "marker" and r["letter"].strip() == "2-2."][-1]
    out["year"] = _find(rnd, "(1) 1차년도", start=out["stage"]["n"])
    out["goal"] = _find(rnd, "① 개발 목표", start=out["year"]["n"])
    out["lead"] = _find(rnd, "[주관연구개발기관(기관명 기입)]", start=out["goal"]["n"])
    out["joint"] = _find(rnd, "[공동연구개발기관1(기관명 기입)]", start=out["goal"]["n"])
    out["joint_o"] = _texty(rnd, out["joint"], 1)[0]
    out["foreign"] = _find(rnd, "[국외기관(기관명 기입)]", start=out["goal"]["n"])
    out["content"] = _find(rnd, "② 개발 내용 및 범위", start=out["goal"]["n"])
    out["facility"] = _find(rnd, "(1-1) 연구시설")
    return out


# ---- 1. 규칙 판정(내장 규칙) -----------------------------------------------------------------------------

CASES = [
    ("□ 개요", {"kind": "marker", "rule": "b.square", "family": "square", "letter": "□", "lead": "", "gap": " ", "rest": "개요", "blank": False}),
    ("  o 내용", {"kind": "marker", "rule": "b.latin-o", "family": "latin-o", "letter": "o", "lead": "  ", "rest": "내용"}),
    ("     \u22c5", {"kind": "marker", "rule": "b.dot", "family": "dot", "letter": "\u22c5", "lead": "     ", "rest": "", "blank": True}),
    ("1. ", {"kind": "marker", "rule": "b.decimal", "letter": "1.", "blank": True, "ord": [1], "shape": "N."}),  # 번호 쓸 자리 — 값 아님
    ("1.", {"kind": "marker", "rule": "b.decimal", "blank": True}),
    ("(9)", {"kind": "marker", "rule": "b.paren-num", "letter": "(9)", "blank": True, "ord": [9], "shape": "(N)"}),
    ("10.0%", {"kind": "data", "rule": "b.data", "letter": ""}),
    ("\u25cb\u25cb명", {"kind": "placeholder", "rule": "b.placeholder"}),  # ○○명 — 동그라미 글머리가 아님
    ("20\u00d7\u00d7년", {"kind": "placeholder", "rule": "b.placeholder"}),
    ("[1단계]  \u203b 안내", {"kind": "label", "rule": "b.bracket-label", "letter": "[1단계]", "gap": "  ", "rest": "\u203b 안내"}),
    ("(우)", {"kind": "plain", "rule": None, "letter": ""}),
    ("o리", {"kind": "plain", "rule": None}),  # 기호 뒤가 글자로 붙음 — latin-o 아님
    ("-10", {"kind": "data", "rule": "b.data"}),
    ("* 각주", {"kind": "footnote", "rule": "b.footnote", "letter": "*", "rest": "각주"}),
    ("\u203b 참고", {"kind": "note", "rule": "b.note", "letter": "\u203b", "rest": "참고"}),
    ("② 둘", {"kind": "marker", "family": "circled", "ord": [2], "shape": "①"}),
    ("다) 셋", {"kind": "marker", "family": "hangul-paren", "ord": [3], "shape": "가)"}),
    ("1.2. 둘", {"kind": "marker", "rule": "b.decimal-multi", "ord": [1, 2], "shape": "N.N."}),
    ("[12] 열둘", {"kind": "marker", "family": "bracket-num", "ord": [12], "shape": "[N]"}),
    ("", {"kind": "empty"}),
    ("   ", {"kind": "empty"}),
]


@pytest.mark.parametrize("text,want", CASES, ids=[repr(c[0]) for c in CASES])
def test_classify_builtin(text, want):
    got = R.classify(text, _rules())
    assert {k: got[k] for k in want} == want


def test_classify_toc_caption_and_br():
    rules = _rules()
    assert R.classify("목차 줄", rules, toc=True)["kind"] == "toc"
    assert R.classify("그림 1", rules, caption=True)["kind"] == "caption"
    assert R.classify("", rules, toc=True)["kind"] == "empty"  # 빈 문단이 먼저
    c = R.classify("□ 제목" + BR + "  o 둘째 줄", rules)
    assert c["kind"] == "marker" and c["letter"] == "□" and c["rest"] == "제목" + BR + "  o 둘째 줄" and not c["blank"]
    assert R.classify("□" + BR + "둘째 줄", rules)["blank"]  # 첫 줄에 제목이 없으면 쓸 자리
    # 구간: 라벨 뒤 「※」 안내 · 강제 줄 바꿈 뒤 줄의 첫머리
    text = "[기관]  \u203b 안내" + BR + "  o 둘째" + BR + "보통 글"
    head = R.classify(text, rules)
    spans = E._spans(text, head, rules, R._Run())
    assert [(s["kind"], s["letter"], s["line"]) for s in spans] == [("label", "[기관]", 0), ("note", "\u203b", 0), ("marker", "o", 1)]
    assert spans[1]["start"] == text.index("\u203b") and spans[2]["start"] == text.index("  o")


def test_shape_and_ordinals():
    assert R.shape_of("circled", "②") == "①"
    assert R.shape_of("decimal", "12.3.") == "N.N."
    assert R.shape_of("hangul-paren", "다)") == "가)"
    assert R.shape_of("square", "■") == "■"
    o = R._ordinal
    assert o("decimal", "1.2.") == [1, 2]
    assert o("hyphen", "2-3.") == [2, 3]
    assert o("hangul-dot", "라.") == [4]
    assert o("circled", "③") == [3]
    assert o("circled", "\u3251") == [21]  # ㉑
    assert o("circled", "\u32b1") == [36]  # ㊱
    assert o("roman-upper", "IV.") == [4]
    assert o("roman-upper", "Ⅲ.") == [3]
    assert o("roman-lower", "ix)") == [9]
    assert o("alpha-lower", "c)") == [3]
    assert o("paren-alpha", "(B)") == [2]
    assert o("square", "□") is None


# ---- 2. 정규식 막이 ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("pattern,why", [
    ("a" * (R.PATTERN_MAX + 1), "너무 깁니다"),
    (r"a{1000}b{1000}", "되풀이"),
    (r"a*", "빈 글"),
    (r"(", "정규식 오류"),
    ("", "비었"),
])
def test_compile_pattern_guards(pattern, why):
    with pytest.raises(ValueError, match=why):
        R.compile_pattern(pattern)


def test_compile_pattern_ok_and_backreference_rejected():
    assert R.compile_pattern(r"\(\d{1,2}-\d{1,2}\)").match("(1-1) 가")
    for bad in (r"(a)\1", r"(?P<x>a)(?P=x)"):
        with pytest.raises(ValueError, match="역참조"):
            R.add_rules([{"kind": "marker", "family": "x", "pattern": bad}], source="user")
    with pytest.raises(ValueError, match="kind"):
        R.add_rules([{"kind": "toc", "pattern": "x"}], source="user")
    with pytest.raises(ValueError, match="scope"):
        R.add_rules([{"kind": "marker", "pattern": "x", "scope": "all"}], source="user")
    assert R.load()["version"] == 0  # 하나도 안 들어감


def test_timed_matcher_skips_catastrophic_pattern():
    text = "a" * 30 + "b"
    # (a+)+$ 는 regex 패키지가 바로 끝냄(멈추지 않음) — 시간 초과가 아니므로 경고도 없음
    run = R._Run()
    t0 = time.perf_counter()
    assert run.match({"id": "l1", "rx": R.compile_pattern(r"(a+)+$")}, text, False) is None
    assert time.perf_counter() - t0 < 1.0
    # (a|aa)+$ 는 지수 되돌림 — 호출당 50 ms 에서 끊고 경고, 그 뒤로는 건너뜀
    rule = {"id": "l2", "rx": R.compile_pattern(r"(a|aa)+$")}
    t0 = time.perf_counter()
    assert run.match(rule, text, False) is None
    assert time.perf_counter() - t0 < 1.0
    assert run.skipped == {"l2"} and len(run.warnings) == 1 and "l2" in run.warnings[0]
    assert run.match(rule, "aaa", False) is None  # 건너뛴 규칙은 다시 안 돌림
    assert len(run.warnings) == 1
    # 배운 규칙으로 판정해도 멈추지 않고 plain + 경고
    rules = R.active(copy.deepcopy(EMPTY), [{"id": "l3", "kind": "marker", "family": "x", "pattern": r"(a|aa)+$", "status": "global"}])
    run = R._Run()
    c = R.classify(text, rules, run)
    assert c["kind"] == "plain" and c["rule"] is None and run.skipped == {"l3"}
    # 실행 예산을 다 쓰면 그 뒤 배운 규칙은 건너뜀
    run = R._Run(budget=0)
    assert run.match({"id": "l4", "rx": R.compile_pattern("a")}, "a", False) is None
    assert run.skipped == {"l4"} and "예산" in run.warnings[0]


# ---- 3. 규칙 저장소 ----------------------------------------------------------------------------------------

def _rule(pattern, kind="marker", **kw):
    return {"name": kw.pop("name", pattern), "kind": kind, "family": kw.pop("family", "test"), "pattern": pattern, **kw}


def test_rule_store_crud_and_history(tmp_path):
    st, ids = R.add_rules([_rule(r"\(\d-\d\)"), _rule(r"<[가-힣]+>", "label")], source="user")
    assert ids == ["l1", "l2"] and st["version"] == 1
    assert (tmp_path / "heads" / "rules.json").is_file()
    st, ids2 = R.add_rules([_rule(r"#\d")], source="llm", expect=1)
    assert ids2 == ["l3"] and st["version"] == 2
    r1 = next(r for r in R.load()["rules"] if r["id"] == "l1")
    assert r1["status"] == "candidate" and r1["source"] == "user" and r1["enabled"] and r1["docs"] == []
    # 켜고 끄기 — 내장(저장은 켜고 끄기만)·배운 것
    st = R.set_enabled("b.square", False, expect=2)
    assert st["version"] == 3 and st["builtin"]["b.square"] == {"enabled": False}
    assert "b.square" not in [r["id"] for r in R.active()]
    assert R.classify("□ 개요", R.active())["rule"] is None
    st = R.set_enabled("b.square", True)
    assert "b.square" in [r["id"] for r in R.active()]
    R.set_enabled("l1", False)
    assert next(r for r in R.load()["rules"] if r["id"] == "l1")["enabled"] is False
    with pytest.raises(KeyError):
        R.set_enabled("l99", True)
    # 상태
    R.set_status("l2", "global")
    assert next(r for r in R.load()["rules"] if r["id"] == "l2")["status"] == "global"
    with pytest.raises(ValueError):
        R.set_status("l2", "local")
    with pytest.raises(KeyError):
        R.set_status("l99", "global")
    # 조건부 저장
    v = R.load()["version"]
    with pytest.raises(R.StaleVersion):
        R.set_enabled("l1", True, expect=v - 1)
    with pytest.raises(R.StaleVersion):
        R.delete_rule("l3", expect=v + 5)
    assert R.load()["version"] == v
    # 지우기 — 내장은 못 지움, 지운 번호는 다시 안 씀
    with pytest.raises(ValueError, match="내장"):
        R.delete_rule("b.square")
    with pytest.raises(KeyError):
        R.delete_rule("l99")
    R.delete_rule("l3", expect=v)
    assert [r["id"] for r in R.load()["rules"]] == ["l1", "l2"]
    _, ids4 = R.add_rules([_rule(r"@\d")], source="user")
    assert ids4 == ["l4"]
    # 이력
    h = R.history("rules")
    acts = [e["action"] for e in h]
    assert acts == ["add", "add", "disable", "enable", "disable", "status", "delete", "add"]
    assert h[0]["ids"] == ["l1", "l2"] and h[-2]["id"] == "l3" and all(e["kind"] == "rules" for e in h)
    assert [e["version"] for e in h] == list(range(1, len(h) + 1))
    assert R.history("guide") == []


def test_rule_store_candidates_docs_and_promotion():
    R.add_rules([_rule(r"\(\d-\d\)", docs=["d1"], globalHint=True)], source="llm")
    rid = "l1"
    on = lambda key: rid in [r["id"] for r in R.active(doc_key=key)]  # noqa: E731
    assert on("d1") and not on("d2") and not on(None)  # 후보는 검증한 문서에만
    assert R.classify("(1-1) 시설", R.active(doc_key="d1"))["rule"] == rid
    assert R.classify("(1-1) 시설", R.active(doc_key="d2"))["kind"] == "plain"
    v = R.load()["version"]
    assert R.add_docs({rid: "d1"}) == [] and R.load()["version"] == v  # 이미 있는 문서 — 바뀐 것 없음, 저장 안 함
    assert R.add_docs({}) == []
    assert R.PROMOTE_DOCS == 2
    assert R.add_docs({rid: "d2"}, reason="시험") == [rid]
    r = R.load()["rules"][0]
    assert r["status"] == "global" and r["docs"] == ["d1", "d2"]
    assert on("d3") and on(None)  # 전역 — 모든 문서
    assert R.add_docs({rid: "d3"}) == []  # 전역은 더 안 바뀜
    e = R.history("rules")[-1]
    assert e["action"] == "docs" and e["promoted"] == [rid]
    # 꺼진 후보는 그 문서에도 안 걸림
    R.set_enabled(rid, False)
    assert not on("d1")


def test_rule_store_first_rule_and_order_and_keeps():
    # 보통 배운 규칙은 내장 뒤 — 「□」 를 label 로 바꾸지 못함
    R.add_rules([_rule("□", "label", status="global")], source="user")
    rules = R.active()
    assert R.classify("□ 개요", rules)["rule"] == "b.square"
    whole = [r["id"] for r in rules if r["scope"] == "whole"]
    assert whole == ["b.placeholder", "b.data"] and [r["id"] for r in rules][:2] == whole  # 글 전체 규칙이 먼저
    assert [r["id"] for r in rules][-1] == "l1"
    # 앞선(first) 배운 규칙은 내장보다 먼저
    R.add_rules([_rule("□", "label", status="global", first=True, family="first")], source="user")
    rules = R.active()
    assert rules[0]["id"] == "l2" and rules[0]["first"]
    c = R.classify("□ 개요", rules)
    assert c["kind"] == "label" and c["rule"] == "l2" and c["letter"] == "□"
    # 시험 규칙(extra)은 배운 규칙 뒤
    rules = R.active(extra=[{"id": "trial", "kind": "marker", "family": "x", "pattern": "#", "status": "candidate"}])
    assert [r["id"] for r in rules][-1] == "trial"
    # keeps
    R.add_keeps(["c:a>b:N", ""])
    R.add_keeps(["c:a>b:N", "c:x>y:M"], reason="시험")  # 이미 있는 key 는 다시 안 넣음
    assert R.load()["keeps"] == ["c:a>b:N", "c:x>y:M"]
    v = R.load()["version"]
    assert R.add_keeps([])["version"] == v  # 빈 목록은 저장 안 함


def test_add_keeps_dedupes_within_one_call():
    R.add_keeps(["c:a>b:N", "c:a>b:N"])
    assert R.load()["keeps"] == ["c:a>b:N"]


def test_rule_store_off_is_memory_only(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_HEADINGS", "off")
    assert R.store_dir() is None
    R.add_rules([_rule("#")], source="user")
    assert R.load()["rules"][0]["id"] == "l1" and R._MEMORY["rules"]["version"] == 1
    assert R.history() == []
    assert not (tmp_path / "heads").exists()
    G.save("graph", "메모리 지침")
    assert G.get("graph")["custom"] and G._MEMORY["graph"][0] == "메모리 지침"


# ---- 4. 지침 ------------------------------------------------------------------------------------------------

def test_guides_save_stale_history_reset(tmp_path):
    g = G.get("rules")
    assert not g["custom"] and g["version"] == 0 and g["text"] == g["default"] and g["text"].strip()
    assert g["sha1"] == g["defaultSha1"] and not g["defaultChanged"] and g["base"] is None
    s = G.save("rules", "# 규칙 지침\n사용자 글", expect=0, reason="시험")
    assert s["custom"] and s["version"] == 1 and s["text"] == "# 규칙 지침\n사용자 글" and s["base"] == g["defaultSha1"]
    assert s["sha1"] != s["defaultSha1"] and not s["defaultChanged"]
    with pytest.raises(R.StaleVersion):
        G.save("rules", "다른 글", expect=0)
    s2 = G.save("rules", "둘째 글", expect=1)
    assert s2["version"] == 2 and s2["base"] == g["defaultSha1"]
    hist = list((tmp_path / "heads" / "guides" / "history" / "rules").glob("*.md"))
    assert len(hist) == 1 and hist[0].read_text(encoding="utf-8") == "# 규칙 지침\n사용자 글"
    ev = R.history("guide")
    assert [(e["name"], e["action"], e["version"]) for e in ev] == [("rules", "save", 1), ("rules", "save", 2)]
    assert ev[0]["reason"] == "시험" and ev[1]["sha1"] == s2["sha1"]
    assert R.history("rules") == []  # 지침 이력은 규칙 이력과 따로 셈
    lst = G.listing()
    assert [x["name"] for x in lst] == list(G.NAMES) and all("text" not in x for x in lst)
    assert next(x for x in lst if x["name"] == "rules")["custom"]
    r = G.reset("rules", reason="시험")
    assert not r["custom"] and r["text"] == g["default"] and r["version"] == 3  # 되돌려도 판은 이어짐(0 이면 ABA)
    assert len(list((tmp_path / "heads" / "guides" / "history" / "rules").glob("*-reset.md"))) == 1
    assert R.history("guide")[-1]["action"] == "reset"
    with pytest.raises(KeyError):
        G.get("nope")
    with pytest.raises(ValueError):
        G.save("rules", "x" * (G.TEXT_MAX + 1))


def test_guides_tolerance_parse_and_save():
    assert G.parse_tolerance("json 블록 없음") == G.TOLERANCE_DEFAULT
    t = G.parse_tolerance('머리\n```json\n{"leadSpaces": 2, "sizePt": 0.25, "fontAliases": [["A", "B"]], "foo": 1}\n```\n꼬리')
    assert t["leadSpaces"] == 2 and t["sizePt"] == 0.25 and t["fontAliases"] == [["A", "B"]] and t["extra"] == {"foo": 1}
    assert t["gapPt"] == G.TOLERANCE_DEFAULT["gapPt"]
    for bad in ("```json\n{깨진\n```", "```json\n[1, 2]\n```", '```json\n{"sizePt": -1}\n```', '```json\n{"colors": "red"}\n```',
                '```json\n{"leadMm": "2"}\n```'):
        with pytest.raises(ValueError):
            G.parse_tolerance(bad)
    with pytest.raises(ValueError):
        G.save("tolerance", "```json\n{깨진\n```")
    assert not G.get("tolerance")["custom"]  # 깨진 글은 저장 안 됨
    assert G.tolerance()["sizePt"] == _tol()["sizePt"]  # 기본본의 json 블록
    G.save("tolerance", '```json\n{"sizePt": 1.5}\n```')
    assert G.tolerance()["sizePt"] == 1.5


def test_guides_default_changed_and_rebase(tmp_path, monkeypatch):
    d = tmp_path / "defaults"
    d.mkdir()
    for n in G.NAMES:
        (d / f"{n}.md").write_text(G.default_text(n), encoding="utf-8")
    monkeypatch.setattr(G, "DEFAULT_DIR", d)
    G.save("graph", "사용자 사본")
    assert not G.get("graph")["defaultChanged"]
    (d / "graph.md").write_text("바뀐 기본본", encoding="utf-8")
    g = G.get("graph")
    assert g["defaultChanged"] and g["default"] == "바뀐 기본본" and g["text"] == "사용자 사본"
    g = G.rebase("graph")
    assert not g["defaultChanged"] and g["base"] == g["defaultSha1"] and g["text"] == "사용자 사본"
    assert G.rebase("rules")["custom"] is False  # 사본 없으면 그대로


def test_guides_snapshot():
    G.save("templates", "틀 지침")
    snap = G.snapshot()
    assert set(snap) == set(G.NAMES)
    for n, v in snap.items():
        assert set(v) == {"sha1", "custom", "text", "version"}
    assert snap["templates"]["custom"] and snap["templates"]["text"] == "틀 지침" and snap["templates"]["version"] == 1
    assert not snap["graph"]["custom"]


# ---- 5. 1단계 추출 -------------------------------------------------------------------------------------------

def test_extract_counts_and_records(rnd):
    c = rnd["counts"]
    assert c["check"] and c["paragraphs"] == c["xml"] == sum(c["perSection"])
    if (c["paragraphs"], c["withBlock"]) != (7638, 7496):  # 사양서 ③ 실측 — 열거가 바뀌면 숫자를 보이고 check 만 강제
        warnings.warn(f"문단 수가 사양서 실측(7638 · 블록 7496)과 다름: {c['paragraphs']} · 블록 {c['withBlock']}")
    assert 0 < c["withBlock"] < c["paragraphs"]
    assert all(r.get("fmt") and r.get("fp") for r in rnd["paras"])
    assert [r["n"] for r in rnd["paras"]] == list(range(len(rnd["paras"])))
    assert len({r["id"] for r in rnd["paras"]}) == len(rnd["paras"])
    assert c["labels"] == len(rnd["labels"]) and c["formats"] == len(rnd["formats"]) and c["labels"] < c["formats"]
    assert sum(lab["count"] for lab in rnd["labels"].values()) == len(rnd["paras"])
    assert {f["label"] for f in rnd["formats"].values()} == set(rnd["labels"])
    assert c["kinds"]["toc"] >= 3 and c["kinds"]["object"] > 0 and c["areas"]["cell"] > c["areas"]["body"]
    assert rnd["warnings"] == [] and rnd["rules"]["version"] == 0
    for r in rnd["paras"]:
        if "\t(페이지 표기)" in r["text"]:
            assert r["kind"] == "toc", r["text"]
    json.dumps(rnd)  # 저장할 수 있어야(실행 폴더 gzip)


def test_extract_image2_chain(rnd, P):
    h1, toc1 = P["h1"], P["toc1"]
    assert h1["kind"] == "marker" and h1["area"] == "body" and h1["rule"] == "b.decimal" and h1["letter"] == "1." and h1["rest"] == "연구개발과제의 필요성"
    assert toc1["kind"] == "toc" and toc1["n"] < h1["n"]
    assert P["toc11"]["kind"] == "toc" and P["toc11"]["text"].endswith("\t(페이지 표기)")
    h11 = P["h11"]
    assert h11["kind"] == "marker" and h11["family"] == "hyphen" and h11["letter"] == "1-1." and h11["shape"] == "N-N."
    assert P["sq"]["kind"] == "marker" and P["sq"]["family"] == "square" and P["sq"]["leadSpaces"] == 0
    for key, letter, family, lead in (("o1", "o", "latin-o", 2), ("dash", "-", "dash", 4), ("dot", "\u22c5", "dot", 5), ("o2", "o", "latin-o", 2)):
        r = P[key]
        assert (r["kind"], r["letter"], r["family"], r["leadSpaces"], r["blank"]) == ("marker", letter, family, lead, True), key
        assert r["form"].startswith(r["leadCode"]) and r["leadCode"]
    # 유효 간격 — 위/아래 간격 0 인 양식, 빈 문단(간격 장치)으로 띄움
    g = P["o1"]["gaps"]
    assert g["abovePt"] > 0 and g["spacersAbove"] >= 1
    between = [r for r in rnd["paras"][P["sq"]["n"] + 1:P["o1"]["n"]] if r["kind"] == "empty"]
    assert between and all(r["spacer"]["pitchPt"] > 0 for r in between)
    assert P["sq"]["para"]["spaceBeforePt"] == 0 and P["sq"]["para"]["spaceAfterPt"] == 0


def test_extract_image3_labels_and_spans(P):
    st = P["stage"]
    assert st["kind"] == "label" and st["letter"] == "[1단계]" and st["rest"].startswith("\u203b")
    assert [(s["kind"], s["letter"]) for s in st["spans"]] == [("label", "[1단계]"), ("note", "\u203b")]
    assert st["spans"][1]["start"] == st["text"].index("\u203b")
    lead = P["lead"]
    assert lead["kind"] == "label" and lead["letter"] == "[주관연구개발기관(기관명 기입)]" and lead["blank"]
    assert [s["kind"] for s in lead["spans"]] == ["label"]
    fo = P["foreign"]
    assert fo["kind"] == "label" and fo["letter"] == "[국외기관(기관명 기입)]" and not fo["blank"]
    assert [s["kind"] for s in fo["spans"]] == ["label", "note"]
    yr = P["year"]
    assert (yr["kind"], yr["family"], yr["letter"], yr["ord"], yr["rest"]) == ("marker", "paren-num", "(1)", [1], "1차년도")
    gl = P["goal"]
    assert (gl["kind"], gl["family"], gl["shape"], gl["ord"]) == ("marker", "circled", "①", [1])
    assert P["content"]["family"] == "circled" and P["content"]["ord"] == [2]
    assert P["joint_o"]["letter"] == "o"


def test_extract_review_unmatched(rnd, P):
    fac = P["facility"]
    assert fac["kind"] == "plain" and fac["rule"] is None
    rv = rnd["review"]
    assert rv["unmatched"]
    grp = next(g for g in rv["unmatched"] if fac["id"] in g["ids"])
    assert grp["shape"] == "(N-N)" and grp["key"] == "u:(N-N)" and grp["count"] == len(grp["ids"]) >= 2
    assert 1 <= len(grp["examples"]) <= 6 and {"id", "text", "area", "fmt", "prev", "next"} <= set(grp["examples"][0])
    assert all(len(g["examples"]) <= 6 for g in rv["unmatched"] + rv["conflicts"])
    assert sum(1 for g in rv["unmatched"] if g["count"] == 1) <= E.SINGLE_MAX
    for g in rv["conflicts"]:  # 충돌 묶음 key = c:<이긴 규칙>><진 규칙>:<꼴>
        assert g["key"].startswith("c:") and len(g["rules"]) == 2 and g["count"] == len(g["ids"])


def _fake_rec(n, size):
    return {"id": f"r{n}", "n": n, "kind": "plain", "blank": False, "gap": "", "leadCode": "", "gapCode": "", "leadSpaces": 0, "leadMm": 0.0,
            "para": {"align": "justify", "indentLeftMm": 0.0, "indentRightMm": 0.0, "firstLineMm": 0.0, "spaceBeforePt": 0.0, "spaceAfterPt": 0.0,
                     "lineSpacing": {"type": "PERCENT", "value": 160, "unit": "%"}},
            "char": {"text": {"charPr": "1", "font": "돋움", "sizePt": size, "bold": False}, "letter": None}}


def test_label_formats_not_transitive():
    """A≈B·B≈C 이지만 A≉C, A 가 가장 많음 → A·B 는 한 S, C 는 따로(대표와만 견줌 — 연쇄 합치기 금지)."""
    tol = dict(G.TOLERANCE_DEFAULT)
    recs = [_fake_rec(0, 10.8), _fake_rec(1, 10.4), _fake_rec(2, 10.4)] + [_fake_rec(i, 10.0) for i in range(3, 6)]  # C 1 · B 2 · A 3
    labels, formats = E.label_formats(recs, tol)
    fmt = {r["id"]: r["fmt"] for r in recs}
    assert len(formats) == 3 and len({r["fp"] for r in recs}) == 3
    assert fmt["r3"] == fmt["r1"] != fmt["r0"]
    assert len(labels) == 2
    a_lab = labels[fmt["r3"]]
    assert a_lab["rep"] == recs[3]["fp"] and a_lab["count"] == 5 and len(a_lab["variants"]) == 2
    assert labels[fmt["r0"]]["count"] == 1
    assert fmt["r0"] == "S1"  # 라벨 번호 = 문서 첫 등장 순
    # 오차를 넓히면 셋이 한 라벨
    recs2 = [copy.deepcopy(r) for r in recs]
    labels2, _ = E.label_formats(recs2, {**tol, "sizePt": 1.0})
    assert len(labels2) == 1 and len({r["fmt"] for r in recs2}) == 1


def test_extract_small_auto_bullets_and_no_bracket_conflict(small):
    c = small["counts"]
    assert c["check"] and c["paragraphs"] == c["xml"]
    auto = [r for r in small["paras"] if (r.get("num") or {}).get("type") == "BULLET"]
    assert auto
    for r in auto:
        assert r["kind"] == "marker" and r.get("auto") is True and r["letter"] == "\u25e6" and r["rule"] == "auto.bullet", r["id"]
        assert r["family"] == "auto-bullet" and r["leadSpaces"] == 0 and r["form"].startswith("list:")
        assert r["blank"] == (not r["rest"].strip())
    assert any(r["blank"] for r in auto) and any(not r["blank"] for r in auto)
    one = next(r for r in small["paras"] if r["text"].strip() == "[1]")
    assert one["kind"] == "marker" and one["family"] == "bracket-num"
    guide = [r for r in small["paras"] if r["text"].startswith("[작성가이드라인]")]
    assert guide and all(r["kind"] == "label" for r in guide)
    assert small["review"]["conflicts"] == []  # 레터 ↔ 라벨은 둘 다 헤딩 후보 — 충돌 아님
    assert not any("bracket" in k for g in small["review"]["conflicts"] for k in g["rules"])


# ---- 6. LLM 규칙 보강(가짜 LLM) ----------------------------------------------------------------------------

def _res(data=None, error=None, cost=0.0):
    return {"data": data, "backend": "fake", "model": "fake", "ms": 0, "costUsd": cost, "error": error}


def _data(job):
    """프롬프트 끝 「## 자료(JSON)」 블록."""
    return json.loads(job["content"].rsplit("## 자료(JSON)\n", 1)[1])


def review_agree(job, data):
    """가짜 D(재검토) 기본 답 — 1차 판정에 모두 동의."""
    return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "verdict": "agree", "same": p["first"]["same"], "reason": "가짜 재검토 동의"}
                          for p in data["pairs"]], "summary": ""})


def fake_ask(**handlers):
    """job["what"] 의 「#」 앞 이름(heading_rules·heading_types·heading_section·heading_formats·heading_review)마다 handler(job, 자료) → 결과.
    heading_review 를 안 주면 1차 판정에 모두 동의하는 기본 답."""
    seen = []
    handlers.setdefault("heading_review", review_agree)

    def ask(jobs):
        out = []
        for job in jobs:
            seen.append(job["what"])
            assert set(job) >= {"schema", "content", "what"}
            assert not any(k.startswith("_") for k in job), job.keys()  # 내부 칸(_section·_pairs)은 LLM 에 안 보낸다
            out.append(handlers[job["what"].split("#", 1)[0]](job, _data(job)))
        return out
    ask.seen = seen
    return ask


def _item(group, decision, pattern="", kind="", **kw):
    return {"group": group, "decision": decision, "name": kw.get("name", kind), "kind": kind, "family": kw.get("family", ""),
            "pattern": pattern, "scope": kw.get("scope", "prefix" if pattern else ""), "first": kw.get("first", False),
            "positives": kw.get("positives", []), "negatives": kw.get("negatives", []), "globalHint": kw.get("globalHint", False),
            "reason": kw.get("reason", "가짜")}


def _rules_plan(rnd):
    """묶음 key → 가짜 LLM 답. (N-N) 좋은 규칙 · 너무 넓은 규칙 · 자기 negatives 에 맞는 규칙 · 두 묶음에 같은 규칙 · 충돌 keep."""
    groups = {g["key"]: g for g in rnd["review"]["unmatched"] + rnd["review"]["conflicts"]}
    circles = [k for k, g in groups.items() if k.startswith("u:\u25ef\u25ef")]
    assert len(circles) >= 2, sorted(groups)
    conflict = next(k for k in groups if k.startswith("c:b.data>b.decimal-multi:"))
    return {"nn": "u:(N-N)", "broad": "u:(글/글)", "neg": "u:(글)", "c1": circles[0], "c2": circles[1], "conflict": conflict}, groups


def _rules_handler(plan, calls):
    def handle(job, data):
        calls.append(data)
        assert data["builtinRules"] and "learnedRules" in data
        items = []
        for g in data["groups"]:
            key, ex = g["group"], [e["id"] for e in g["examples"]]
            if key == plan["nn"]:
                items.append(_item(key, "rule", r"\(\d{1,2}-\d{1,2}\)", "marker", family="paren-hyphen", positives=ex,
                                   negatives=["(1) 하나", "(가) 나"], globalHint=True))
            elif key == plan["broad"]:
                items.append(_item(key, "rule", ".", "marker", family="any", positives=ex))
            elif key == plan["neg"]:
                items.append(_item(key, "rule", r"\([가-힣]+\)", "plain", family="paren-word", positives=ex, negatives=["(가) 항목"]))
            elif key in (plan["c1"], plan["c2"]):
                items.append(_item(key, "rule", "\u25ef{2,}", "placeholder", family="circle-ph", positives=ex))
            elif key == plan["conflict"]:
                items.append(_item(key, "keep"))
            else:
                items.append(_item(key, "unsure"))
        items.append(_item("u:없는묶음", "rule", "x", "marker"))  # 입력에 없는 group — 버림
        return _res({"items": items}, cost=0.01)
    return handle


def test_propose_rules_fake_llm(rnd, rnd_doc):
    plan, groups = _rules_plan(rnd)
    calls = []
    ask = fake_ask(heading_rules=_rules_handler(plan, calls))
    rep = HL.propose_rules(rnd, doc_key="rnd", doc_name="연구개발계획서_양식.hwpx", ask=ask, run_id=7)
    assert rep["error"] is None and rep["groups"] == len(groups)
    assert ask.seen == [f"heading_rules#{i + 1}" for i in range(-(-len(groups) // HL.BATCH_GROUPS))]
    assert sum(len(d["groups"]) for d in calls) == len(groups)
    assert len(rep["calls"]) == len(ask.seen) and rep["calls"][0]["prompt"].startswith(HL.RULES_CONTRACT[:20])
    assert rep["guides"] == {"rules": G.get("rules")["sha1"]} and rep["costUsd"] == round(0.01 * len(ask.seen), 4)
    by = {i["group"]: i for i in rep["items"]}
    assert "u:없는묶음" not in by and len(rep["items"]) == len(groups)
    assert by[plan["nn"]]["verdict"] == "saved" and by[plan["nn"]]["test"]["fixed"] == groups[plan["nn"]]["count"]
    assert by[plan["broad"]]["verdict"] == "rejected" and "너무 넓음" in by[plan["broad"]]["why"], by[plan["broad"]]
    assert by[plan["neg"]]["verdict"] == "rejected" and "negatives" in by[plan["neg"]]["why"], by[plan["neg"]]
    assert by[plan["c1"]]["verdict"] == "saved"
    assert by[plan["c2"]]["verdict"] == "duplicate" and "이번 실행" in by[plan["c2"]]["why"]
    assert by[plan["conflict"]]["verdict"] == "kept"
    assert all(i["verdict"] == "unsure" for k, i in by.items() if k not in plan.values())
    # 저장: 후보 규칙 2개(docs = 이 문서) + keeps
    assert rep["saved"] == [by[plan["nn"]]["id"], by[plan["c1"]]["id"]] == ["l1", "l2"]
    assert rep["kept"] == [plan["conflict"]]
    st = R.load()
    nn = next(r for r in st["rules"] if r["id"] == "l1")
    assert (nn["pattern"], nn["kind"], nn["status"], nn["docs"], nn["source"], nn["globalHint"]) == \
        (r"\(\d{1,2}-\d{1,2}\)", "marker", "candidate", ["rnd"], "llm", True)
    assert nn["provenance"]["group"] == plan["nn"] and nn["provenance"]["run"] == 7 and nn["examples"]
    assert st["keeps"] == [plan["conflict"]]
    assert [e["action"] for e in R.history("rules")] == ["add", "keep"]
    # 다시 추출: 이 문서에서 (N-N) 은 marker, 충돌 묶음은 다시 안 나옴
    again = E.extract(rnd_doc, store=st, doc_key="rnd", tol=_tol())
    ids = set(groups[plan["nn"]]["ids"])
    assert all(r["kind"] == "marker" and r["rule"] == "l1" for r in again["paras"] if r["id"] in ids)
    assert plan["conflict"] not in {g["key"] for g in again["review"]["conflicts"]}
    assert plan["nn"] not in {g["key"] for g in again["review"]["unmatched"]}
    assert again["rules"]["version"] == st["version"] and "l1" in again["rules"]["active"]
    # 다른 문서에서 후보 시험 — globalHint 인 (N-N) 규칙만, 통과하면 docs 에 더하고 전역으로
    trial = E.trial_candidates(rnd, doc_key="other")
    assert set(trial) == {"l1"} and trial["l1"]["passed"] and trial["l1"]["fixed"] == len(ids) and trial["l1"]["broken"] == 0
    assert E.trial_candidates(rnd, doc_key="rnd") == {}  # 이미 검증한 문서는 시험 안 함
    assert R.add_docs({rid: "other" for rid, t in trial.items() if t["passed"]}) == ["l1"]
    nn = next(r for r in R.load()["rules"] if r["id"] == "l1")
    assert nn["docs"] == ["rnd", "other"] and nn["status"] == "global"
    # 같은 제안을 다시 받으면 이미 있는 규칙과 같음(duplicate) — 새로 저장 안 함
    rep2 = HL.propose_rules(rnd, doc_key="rnd", ask=fake_ask(heading_rules=_rules_handler(plan, [])))
    by2 = {i["group"]: i for i in rep2["items"]}
    assert by2[plan["nn"]]["verdict"] == "duplicate" and by2[plan["nn"]]["id"] == "l1"
    assert rep2["saved"] == []


def test_propose_rules_save_false_and_failure(rnd):
    plan, groups = _rules_plan(rnd)
    rep = HL.propose_rules(rnd, doc_key="rnd", ask=fake_ask(heading_rules=_rules_handler(plan, [])), save=False)
    by = {i["group"]: i for i in rep["items"]}
    assert by[plan["nn"]]["verdict"] == "saved" and "id" not in by[plan["nn"]]  # 판정만
    assert rep["saved"] == [] and rep["kept"] == []
    assert R.load()["version"] == 0 and R.history() == []
    # LLM 실패 — 항목 없음, error
    rep = HL.propose_rules(rnd, doc_key="rnd", ask=fake_ask(heading_rules=lambda job, data: _res(None, "가짜 실패")))
    assert rep["error"] == "가짜 실패" and rep["items"] == [] and rep["saved"] == [] and rep["calls"][0]["response"] is None
    # 보강 대상이 없으면 LLM 을 부르지 않음
    none = {**rnd, "review": {"unmatched": [], "conflicts": []}}
    rep = HL.propose_rules(none, doc_key="rnd", ask=lambda jobs: pytest.fail("부르면 안 됨"))
    assert rep["groups"] == 0 and rep["calls"] == []


def test_check_proposal_first_rule_must_not_take(rnd):
    """앞선(first) 규칙은 충돌 묶음에서만, 묶음 밖 문단을 하나도 바꾸면 안 됨."""
    g = next(g for g in rnd["review"]["conflicts"] if g["key"].startswith("c:b.data>b.decimal-multi:"))
    item = _item(g["key"], "rule", r"\d{1,2}\.\d", "marker", family="decimal", first=True, positives=g["ids"][:2])
    rule, verdict = HL.check_proposal(item, {**g, "type": "conflict"}, rnd, copy.deepcopy(EMPTY), "rnd")
    assert rule is None and verdict["verdict"] == "rejected"
    assert verdict["test"]["broken"] > 0 or verdict["test"]["taken"] > 0
    # 못 맞춤 묶음에서는 first 를 무시(보통 규칙)
    u = next(g for g in rnd["review"]["unmatched"] if g["key"] == "u:(N-N)")
    item = _item(u["key"], "rule", r"\(\d-\d\)", "marker", first=True, positives=u["ids"])
    rule, verdict = HL.check_proposal(item, {**u, "type": "unmatched"}, rnd, copy.deepcopy(EMPTY), "rnd")
    assert rule is not None and rule["first"] is False and verdict["verdict"] == "saved"
    # 정규식 오류
    rule, verdict = HL.check_proposal(_item(u["key"], "rule", "(", "marker"), {**u, "type": "unmatched"}, rnd, copy.deepcopy(EMPTY), "rnd")
    assert rule is None and "규칙 오류" in verdict["why"]


# ---- 7. 2단계 그래프 ----------------------------------------------------------------------------------------

def test_graph_fallback_script(rnd, P):
    """LLM 없이 — 어림 부모(heuristic 표지) + 사슬 학습. 1-1. 아래 □ 는 가지 템플릿(주 사슬 L3 은 더 많이 쓰인 (N)), 구분 라벨은 제 템플릿의 뿌리(2026-11-09 가지 규칙)."""
    g = HG.build(rnd, use_llm=False, ask=lambda jobs: pytest.fail("LLM 을 부르면 안 됨"))
    json.dumps(g)
    assert g["version"] == 2 and g["llm"]["fallback"] and g["llm"]["calls"] == 0 and g["_calls"] == [] and g["counts"]["heuristic"] > 0
    N = {n["id"]: n for n in g["nodes"]}
    par = lambda k: N[P[k]["id"]]["parent"]  # noqa: E731
    tpl = lambda k: (N[P[k]["id"]]["tplNo"], N[P[k]["id"]]["level"])  # noqa: E731
    # 그림 2 사슬
    assert par("h1") == "root" and par("h11") == P["h1"]["id"] and par("sq") == P["h11"]["id"]
    assert par("o1") == P["sq"]["id"] and par("dash") == P["o1"]["id"] and par("dot") == P["dash"]["id"]
    assert par("o2") == P["sq"]["id"]  # 둘째 o 는 첫 o 의 형제
    assert tpl("h1") == (1, 1) and tpl("h11") == (1, 2) and g["llm"]["mainChain"][:3] == ["N.", "N-N.", "(N)"]
    sq_t = N[P["sq"]["id"]]["tplNo"]
    assert sq_t != 1 and N[P["sq"]["id"]]["template"].startswith("body:□›o›-") and tpl("sq") == (sq_t, 1)
    assert tpl("o1") == (sq_t, 2) and tpl("dash") == (sq_t, 3) and tpl("dot") == (sq_t, 4) and tpl("o2") == (sq_t, 2)
    # 그림 3 — 구분 라벨은 제 템플릿의 뿌리(L1), 아래 내용은 라벨을 부모로
    assert N[P["stage"]["id"]]["role"] == "label" and par("stage") == P["sec22"]["id"]
    assert N[P["stage"]["id"]]["template"].startswith("body:[") and tpl("stage")[1] == 1
    assert par("year") == P["stage"]["id"] and N[P["year"]["id"]]["division"] == P["stage"]["id"] and N[P["year"]["id"]]["tplNo"] != 1
    for k in ("lead", "joint", "foreign"):
        assert N[P[k]["id"]]["role"] == "label" and par(k) == P["goal"]["id"], k
    jo = N[P["joint_o"]["id"]]
    assert jo["parent"] == P["joint"]["id"] and jo["division"] == P["joint"]["id"]
    assert (jo["tplNo"], jo["level"]) == (N[P["joint"]["id"]]["tplNo"], 2)  # 라벨 템플릿의 L2
    assert par("goal") == P["year"]["id"] and par("content") == P["year"]["id"]  # ① · ② 형제
    assert tpl("goal") == tpl("content")
    # 그릇(표·칸) · 간선
    kinds = {c["id"].split(":", 1)[0] for c in g["containers"]}
    assert {"tbl", "cell"} <= kinds
    cells = {c["id"] for c in g["containers"] if c["kind"] == "cell"}
    assert any(n["area"] == "cell" and n["parent"] in cells for n in g["nodes"])
    et = {e["t"] for e in g["edges"]}
    assert {"contains", "parent", "division", "instance"} <= et
    assert {"t": "parent", "from": P["sq"]["id"], "to": P["o2"]["id"]} in g["edges"]
    assert {"t": "division", "from": P["joint"]["id"], "to": P["joint_o"]["id"]} in g["edges"]
    assert any(e["t"] == "contains" and e["from"].startswith("tbl:") and e["to"].startswith("cell:") for e in g["edges"])
    assert g["counts"]["nodes"] == len(g["nodes"]) and g["counts"]["types"] == len(g["types"])
    # 템플릿 — id 순서: 주 사슬 #1 → 가지 → 라벨 → 칸, 앵커 = scope:사슬, 인스턴스는 L1 자리마다
    kinds_t = [t["kind"] for t in g["templates"]]
    assert kinds_t[0] == "main" and g["templates"][0]["id"] == 1 and {"branch", "label", "cell"} <= set(kinds_t)
    assert kinds_t == sorted(kinds_t, key=lambda k: HG.KIND_ORDER[k])
    assert all(t["anchor"] == t["name"] == f"{t['scope']}:{'›'.join(t['chain'])}" for t in g["templates"])
    assert len({t["anchor"] for t in g["templates"]}) == len(g["templates"])  # 앵커는 중복 없음
    assert g["instances"] and all(i["template"] in {t["id"] for t in g["templates"]} for i in g["instances"])
    assert all(a["decision"] == "undecided" for a in g["adjustments"])


def _types_of(rnd):
    nodes = HG.candidates(rnd)
    types = HG.type_table(nodes)
    return {nd["id"]: nd["type"] for nd in nodes}, types


def _a_answer(rnd, P):
    """가짜 A(2026-11-09 꼴) — 유형마다 role·parents(보통 매달리는 부모 레터)·basis, 본문 주 사슬 1. › 1-1. › (1) › o › - › ⋅."""
    T, types = _types_of(rnd)
    K = HG.type_keys(types, HG.fallback_roles(types))
    t = lambda k: T[P[k]["id"]]  # noqa: E731
    key = lambda k: K[t(k)]  # noqa: E731
    par = {"h1": ["root"], "h11": [key("h1")], "sq": [key("h11"), key("year")], "year": [key("h11"), "[단계]"], "goal": [key("year")],
           "o1": [key("sq"), key("year"), "[기관]"], "dash": [key("o1")], "dot": [key("dash")]}
    types_ = [{"type": t(k), "role": "heading", "parents": p, "variantOf": "", "basis": "차년도" if k == "year" else "", "reason": ""} for k, p in par.items()]
    types_ += [{"type": t("stage"), "role": "label", "parents": [], "variantOf": "", "basis": "단계", "reason": ""}]
    types_ += [{"type": t(k), "role": "label", "parents": [], "variantOf": "", "basis": "기관", "reason": ""} for k in ("lead", "joint", "foreign")]
    types_ += [{"type": "T9999", "role": "heading", "parents": [], "variantOf": "", "basis": "", "reason": "모르는 유형 — 버림"}]
    assert len({t(k) for k in par}) == 8
    return {"types": types_, "mainChain": [key(k) for k in ("h1", "h11", "year", "o1", "dash", "dot")], "summary": "가짜 A"}, T


def test_graph_llm_fake(rnd, P):
    A, T = _a_answer(rnd, P)
    ids = {k: P[k]["id"] for k in P}
    st = {"failed": None, "b": 0, "c": {}}
    MAIN = "body:" + "›".join(A["mainChain"])

    def a(job, data):
        assert job["what"] == "heading_types" and job["schema"] is HL.TYPES_SCHEMA
        assert {r["type"] for r in data["types"]} == set(T.values()) and data["sketch"] and data["mainChainProposal"]
        assert all("key" in r for r in data["types"]) and "formatPairs" not in data
        return _res(A, cost=0.1)

    def b(job, data):
        st["b"] += 1
        rows = [r[0] for r in data["nodes"]]
        assert job["schema"] is HL.SECTION_SCHEMA and set(data) == {"bases", "types", "templates", "ancestors", "nodes", "preview"}
        assert data["bases"] == ["단계", "차년도", "기관"]
        assert all(len(r) == 7 for r in data["nodes"]) and all("anchor" in t and "chain" in t for t in data["templates"])
        if ids["h1"] in rows:  # 그림 2 구간 — 바른 변경 1 + 틀린 변경 4
            return _res({"changes": [
                {"id": ids["o2"], "parent": ids["o1"], "template": "", "level": 0, "role": "heading", "reason": "가짜 — 바른 변경"},
                {"id": "없는id", "parent": "root", "template": "", "level": 0, "role": "heading", "reason": ""},
                {"id": ids["sq"], "parent": ids["o1"], "template": "", "level": 0, "role": "heading", "reason": "부모가 뒤"},
                {"id": ids["dash"], "parent": ids["goal"], "template": "", "level": 0, "role": "heading", "reason": "구간 밖 부모"},
                {"id": ids["dot"], "parent": "", "template": "없는틀", "level": 1, "role": "heading", "reason": "모르는 템플릿"},
            ], "summary": ""})
        if ids["goal"] in rows or st["failed"] is not None:
            return _res({"changes": [], "summary": ""})
        st["failed"] = rows
        return _res(None, "가짜 B 실패")

    def c(job, data):
        pairs = []
        for i, p in enumerate(data["pairs"]):
            assert p["slot"] == f"{p['template']}|L{p['level']}" and p["a"] != p["b"] and p["tplNo"]
            st["c"][(p["slot"], p["a"], p["b"])] = i % 2 == 0  # C 답은 슬롯마다(같은 쌍이 두 슬롯에 올 수 있음)
            pairs.append({"slot": p["slot"], "a": p["a"], "b": p["b"], "same": i % 2 == 0, "reason": "가짜 C"})
        return _res({"pairs": pairs, "summary": ""})

    ask = fake_ask(heading_types=a, heading_section=b, heading_formats=c)
    g = HG.build(rnd, use_llm=True, ask=ask, doc_name="시험")
    json.dumps(g)
    lm = g["llm"]
    assert not lm["fallback"] and lm["error"] is None and lm["summary"] == "가짜 A" and lm["mainChain"] == A["mainChain"]
    assert ask.seen[0] == "heading_types" and lm["sections"] == st["b"] >= 3
    assert lm["calls"] == len(ask.seen) == len(g["_calls"]) and lm["failed"] == 1 and lm["costUsd"] == 0.1
    assert set(g["guides"]) == {"graph", "templates", "tolerance"}
    N = {n["id"]: n for n in g["nodes"]}
    # A 의 parents·주 사슬대로 부모 — 템플릿·레벨은 스크립트가 셈
    assert (N[ids["h1"]]["template"], N[ids["h1"]]["level"], N[ids["h1"]]["parent"]) == (MAIN, 1, "root")
    assert N[ids["h11"]]["parent"] == ids["h1"] and N[ids["sq"]]["parent"] == ids["h11"]
    assert N[ids["o1"]]["parent"] == ids["sq"] and N[ids["dash"]]["parent"] == ids["o1"] and N[ids["dot"]]["parent"] == ids["dash"]
    sq = N[ids["sq"]]
    assert sq["tplNo"] != 1 and sq["template"].startswith("body:□›o›-") and sq["level"] == 1  # 1-1. 아래 □ = 가지 템플릿 뿌리
    assert [(N[ids[k]]["tplNo"], N[ids[k]]["level"]) for k in ("o1", "dash", "dot")] == [(sq["tplNo"], 2), (sq["tplNo"], 3), (sq["tplNo"], 4)]
    year, stage = N[ids["year"]], N[ids["stage"]]
    assert stage["role"] == "label" and stage["template"].startswith("body:[단계]") and stage["level"] == 1
    assert (year["parent"], year["division"], year["tplNo"], year["level"]) == (ids["stage"], ids["stage"], stage["tplNo"], 2)  # 라벨 템플릿 「[단계] › (N) › ①」
    goal, content = N[ids["goal"]], N[ids["content"]]
    assert goal["parent"] == content["parent"] == ids["year"] and (goal["tplNo"], goal["level"]) == (content["tplNo"], content["level"]) == (stage["tplNo"], 3)
    assert content["division"] == ids["stage"]
    for k in ("lead", "joint", "foreign"):
        assert N[ids[k]]["role"] == "label" and N[ids[k]]["parent"] == ids["goal"] and N[ids[k]]["template"].startswith("body:[기관]›o"), k
    jo = N[ids["joint_o"]]
    assert (jo["parent"], jo["division"], jo["tplNo"], jo["level"]) == (ids["joint"], ids["joint"], N[ids["joint"]]["tplNo"], 2)
    ty = {t["type"]: t for t in g["types"]}
    assert ty[T[ids["stage"]]]["basis"] == "단계" and ty[T[ids["joint"]]]["basis"] == "기관" and "T9999" not in ty
    assert ty[T[ids["joint"]]]["key"] == "[기관]" and ty[T[ids["sq"]]]["parents"] == A["types"][2]["parents"]
    filled = [t for t in g["types"] if t["type"] not in {x["type"] for x in A["types"]}]
    assert filled and all("스크립트 대체" in t["reason"] for t in filled if t["kind"] != "band")  # A 가 빠뜨린 유형은 대체 역할
    assert all(t["role"] == "heading" and t["parents"] == ["root"] and "별첨·부록 표 제목" in t["reason"] for t in g["types"] if t["kind"] == "band")  # 띠 표 줄(「별첨N」 — ② §6)의 역할·부모는 A 의 답과 무관하게 스크립트가
    # 인스턴스 — 템플릿 L1 자리마다: 「[1단계]」 라벨이 뿌리(① · ② 는 그 L3 멤버), 「[기관]」 라벨은 제 인스턴스(단계 인스턴스의 childInstances)
    by_root = {i["root"]: i for i in g["instances"]}
    assert ids["stage"] in by_root and ids["joint"] in by_root and ids["goal"] not in by_root
    si, ji = by_root[ids["stage"]], by_root[ids["joint"]]
    assert si["template"] == stage["tplNo"] and si["parent"] == ids["sec22"] and {ids["year"], ids["goal"], ids["content"]} <= set(si["members"])
    assert ji["parent"] == ids["goal"] and ji["i"] in si["childInstances"] and ids["joint_o"] in ji["members"] and ji["basis"].startswith("[공동")
    assert {"t": "instance", "from": ids["stage"], "to": f"tpl:{stage['tplNo']}"} in g["edges"]
    tp = {t["anchor"]: t for t in g["templates"]}
    lab = tp[N[ids["joint"]]["template"]]
    assert lab["kind"] == "label" and lab["rootRole"] == "label" and lab["root"] == "[기관]" and [s["level"] for s in lab["slots"]][:2] == [1, 2]
    assert tp[MAIN]["kind"] == "main" and tp[MAIN]["id"] == 1 and tp[MAIN]["chain"] == A["mainChain"]
    # B: 바른 변경 하나만 적용, 나머지는 까닭과 함께 버림
    assert lm["applied"] == 1 and lm["rejected"] == 4
    ch = g["changes"][0]
    assert ch["id"] == ids["o2"] and ch["before"]["parent"] == ids["sq"] and ch["after"]["parent"] == ids["o1"] and ch["after"]["slot"] is None
    assert N[ids["o2"]]["changed"] and N[ids["o2"]]["parent"] == ids["o1"] and N[ids["o2"]]["reason"] == "가짜 — 바른 변경"
    assert {"t": "parent", "from": ids["o1"], "to": ids["o2"]} in g["edges"]
    assert {"t": "parent", "from": ids["sq"], "to": ids["o2"]} not in g["edges"]
    whys = {r["id"]: r["why"] for r in g["rejected"]}
    assert whys["없는id"] == "구간 밖 id"
    assert whys[ids["sq"]] == "부모가 문서 순으로 뒤"
    assert "구간·조상 밖" in whys[ids["dash"]]
    assert "모르는 템플릿" in whys[ids["dot"]]
    assert N[ids["sq"]]["parent"] == ids["h11"] and not N[ids["sq"]]["changed"]
    # 실패한 B 구간 — 초안 + 미판정
    assert st["failed"] and all(N[i]["undecided"] for i in st["failed"])
    assert g["counts"]["undecided"] == len(st["failed"]) and lm["failedSections"] == 1
    assert not N[ids["h1"]]["undecided"]
    # C: 슬롯 서식 쌍 → 조정(같음 adjust · 다름 keep) — 슬롯마다
    assert any(w.startswith("heading_formats#") for w in ask.seen) and st["c"] and lm["formatPairs"] == len(st["c"])
    decided = 0
    for adj in g["adjustments"]:
        key = (f"{adj['template']}|L{adj['level']}", adj["to"], adj["from"])
        assert key in st["c"], adj
        assert adj["decision"] == ("adjust" if st["c"][key] else "keep"), adj
        decided += 1
    assert decided and {"adjust", "keep"} <= {a["decision"] for a in g["adjustments"]}
    assert g["counts"]["adjust"] == sum(1 for a in g["adjustments"] if a["decision"] == "adjust")


def test_graph_llm_retry_high_change_rate(rnd, P):
    """B 가 구간의 30% 넘게 바꾸면(노드 10개 이상 구간) 한 번 더 묻고 둘째 답을 쓴다."""
    A, _ = _a_answer(rnd, P)
    ids = {k: P[k]["id"] for k in P}
    asked = []

    def b(job, data):
        rows = data["nodes"]
        if ids["h1"] not in [r[0] for r in rows]:
            return _res({"changes": [], "summary": ""})
        asked.append(len(rows))
        if len(asked) == 1:  # 첫 답: 모든 노드(초안 그대로) — 변경률 100%
            return _res({"changes": [{"id": r[0], "parent": r[3] or "root", "template": "", "level": 0, "role": "heading",
                                      "reason": "첫 답"} for r in rows], "summary": ""})
        return _res({"changes": [{"id": ids["o2"], "parent": ids["o1"], "template": "", "level": 0, "role": "heading", "reason": "둘째 답"}], "summary": ""})

    ask = fake_ask(heading_types=lambda job, data: _res(A), heading_section=b,
                   heading_formats=lambda job, data: _res({"pairs": [], "summary": ""}))
    g = HG.build(rnd, use_llm=True, ask=ask)
    assert len(asked) == 2 and asked[0] >= 10
    assert g["llm"]["applied"] == 1 and g["changes"][0]["reason"] == "둘째 답"
    assert sum(1 for w in ask.seen if w.startswith("heading_section#")) == g["llm"]["sections"] + 1
    N = {n["id"]: n for n in g["nodes"]}
    assert N[ids["o2"]]["parent"] == ids["o1"] and not N[ids["o1"]]["changed"]


def test_graph_llm_a_failure_falls_back(rnd, P):
    ask = fake_ask(heading_types=lambda job, data: _res(None, "가짜 A 실패"))
    g = HG.build(rnd, use_llm=True, ask=ask)
    assert ask.seen == ["heading_types"]  # A 가 실패하면 B·C 를 안 부름
    assert g["llm"]["fallback"] and g["llm"]["error"] == "가짜 A 실패" and g["llm"]["failed"] == 1
    N = {n["id"]: n for n in g["nodes"]}
    assert N[P["o2"]["id"]]["parent"] == P["sq"]["id"]


def test_apply_changes_validation():
    """B 변경 검증 — 순환은 문서 순 검사를 지나는 조상 쪽에서만 생길 수 있어(초안 부모는 늘 앞 노드) 만든 그래프로 본다. 라벨 부모는 그대로 부모, template·level 은
    아는 앵커 + 레벨 ≥ 1 일 때만 슬롯 예외."""
    graph = {i: {"id": i, "parent": p, "role": r, "key": "x", "division": None}
             for i, p, r in (("a0", "root", "heading"), ("a1", "n2", "heading"), ("lab", "a0", "label"), ("n1", "a0", "heading"), ("n2", "n1", "heading"))}
    applied, rejected = HG.apply_changes([
        {"id": "zz", "parent": "root"},
        {"id": "n1", "parent": "n2"},
        {"id": "n1", "parent": "x9"},
        {"id": "n2", "parent": "a1"},  # 조상 a1 의 부모가 n2(만든 그래프) — 순환
        {"id": "n1", "parent": "root", "template": "nope", "level": 1, "role": "heading"},
        {"id": "n1", "parent": "root", "level": 3},  # 템플릿 없이 레벨만 — 슬롯 예외가 아니다
        {"id": "n2", "parent": "lab", "template": "body:x", "level": 2, "reason": "바름"},  # 라벨 부모 그대로 + 슬롯 예외
        {"id": "n1", "parent": "root", "template": "", "level": 0},
    ], ["n1", "n2"], ["a0", "a1", "lab"], graph, {"body:x"})
    assert [(r["id"], r["why"]) for r in rejected] == [("zz", "구간 밖 id"), ("n1", "부모가 문서 순으로 뒤"), ("n1", "부모 x9 가 구간·조상 밖"),
                                                         ("n2", "순환"), ("n1", "모르는 템플릿 nope"), ("n1", "모르는 템플릿 (없음)")]
    assert [a["id"] for a in applied] == ["n2", "n1"]
    assert graph["n2"]["parent"] == "lab" and graph["n2"]["slot"] == {"template": "body:x", "level": 2} and graph["n2"]["changed"] and graph["n2"]["reason"] == "바름"
    assert graph["n1"]["parent"] == "root" and graph["n1"].get("slot") is None
    assert HG._division_of("n2", graph) == "lab" and HG._division_of("n1", graph) is None


# ---- 8. API ---------------------------------------------------------------------------------------------------

@pytest.fixture
def client():
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _wait_heads(c, d, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/headings").json()
        if v["job"] and v["job"]["status"] != "running":
            return v
        time.sleep(0.05)
    raise AssertionError("헤딩 추출이 끝나지 않음")


def test_api_stage1_stage2(client):
    d = _upload(client, RND)
    v = client.get(f"/api/docs/{d}/headings").json()
    assert v["job"] is None and v["stage1"] is None and v["stage2"] is None
    assert client.get(f"/api/docs/{d}/headings/graph").status_code == 404
    assert client.get(f"/api/docs/{d}/headings/paras").json() == {"total": 0, "offset": 0, "items": []}
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 4}).status_code == 400  # 3 은 표 구조(3단계)
    r = client.post(f"/api/docs/{d}/headings", json={"stage": 1})
    assert r.status_code == 202 and r.json()["stage"] == 1 and r.json()["llm"] is False
    v = _wait_heads(client, d)
    assert v["job"]["status"] == "done", v["job"]
    s1 = v["stage1"]
    assert s1["summary"]["check"] and s1["summary"]["paragraphs"] == s1["summary"]["xml"] == 7638
    assert not s1["stale"] and s1["llm"] is None and s1["review"]["unmatched"] and v["runs"][-1]["stage"] == 1
    assert s1["meta"]["run"] == 1 and s1["meta"]["rulesVersion"] == 0 and set(s1["meta"]["guides"]) == set(G.NAMES)
    # 문단 목록 쪽 나눔
    r = client.get(f"/api/docs/{d}/headings/paras", params={"kind": "label", "limit": 5})
    j = r.json()
    assert r.status_code == 200 and len(j["items"]) == 5 and j["total"] > 5 and all(i["kind"] == "label" for i in j["items"])
    assert {"id", "text", "para", "char", "line", "spans", "fmt"} <= set(j["items"][0])
    j2 = client.get(f"/api/docs/{d}/headings/paras", params={"kind": "label", "limit": 5, "offset": 5}).json()
    assert j2["total"] == j["total"] and j2["offset"] == 5 and j2["items"][0]["id"] not in {i["id"] for i in j["items"]}
    q = client.get(f"/api/docs/{d}/headings/paras", params={"q": "연구개발과제의 필요성"}).json()
    assert q["total"] >= 2 and {i["kind"] for i in q["items"]} >= {"toc", "marker"}
    lab = client.get(f"/api/docs/{d}/headings/labels").json()
    assert lab["labels"] and lab["formats"] >= len(lab["labels"]) and {"id", "name", "count", "para", "char"} <= set(lab["labels"][0])
    # 2단계(스크립트)
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 2, "llm": False}).status_code == 202
    v = _wait_heads(client, d)
    assert v["job"]["status"] == "done" and v["job"]["stage"] == 2, v["job"]
    g = client.get(f"/api/docs/{d}/headings/graph")
    assert g.status_code == 200
    g = g.json()
    assert g["nodes"] and g["llm"]["fallback"] and "_calls" not in g and g["meta"]["stage1Run"] == 1 and g["meta"]["run"] == 2
    assert v["stage2"]["counts"]["nodes"] == len(g["nodes"]) and not v["stage2"]["stale"]
    # 작업 폴더에 실행 저장 + 기록
    hd = works.folder(d) / "headings"
    assert json.loads((hd / "current.json").read_text("utf-8")) == {"stage1": 1, "stage2": 2}
    assert (hd / "1" / "stage1.json.gz").is_file() and (hd / "2" / "graph.json.gz").is_file() and (hd / "1" / "run.json").is_file()
    end = time.time() + 10  # 기록(log)은 상태를 done 으로 바꾼 뒤 같은 스레드가 쓴다
    while len([e for e in works.events(d) if e["kind"] == "headings"]) < 2 and time.time() < end:
        time.sleep(0.05)
    ev = [e for e in works.events(d) if e["kind"] == "headings"]
    assert [(e["stage"], e["status"]) for e in ev] == [(1, "done"), (2, "done")]


def test_api_busy_409(client, monkeypatch):
    go, started = threading.Event(), threading.Event()

    def slow(sess, job, use_llm):
        started.set()
        go.wait(10)
        return 0
    monkeypatch.setattr(heading_runs, "run_stage1", slow)
    d = _upload(client, SMALL)
    try:
        assert client.post(f"/api/docs/{d}/headings", json={"stage": 1}).status_code == 202
        assert started.wait(5)
        r = client.post(f"/api/docs/{d}/headings", json={"stage": 2})
        assert r.status_code == 409
        assert client.get(f"/api/docs/{d}/headings").json()["job"]["status"] == "running"
    finally:
        go.set()
    v = _wait_heads(client, d)
    assert v["job"]["status"] == "done" and v["job"]["stage"] == 1
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 1}).status_code == 202  # 끝난 뒤엔 다시 시작
    _wait_heads(client, d)


def test_api_stage_failure_is_reported(client, monkeypatch):
    def boom(sess, job, use_llm):
        raise RuntimeError("가짜 오류")
    monkeypatch.setattr(heading_runs, "run_stage2", boom)
    d = _upload(client, SMALL)
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 2}).status_code == 202
    v = _wait_heads(client, d)
    assert v["job"]["status"] == "failed" and "가짜 오류" in v["job"]["error"]
    assert v["job"]["steps"][-1]["name"] == "오류"


def test_api_rules(client):
    v = client.get("/api/headings/rules").json()
    assert v["version"] == 0 and v["learned"] == [] and v["keeps"] == []
    assert next(r for r in v["builtin"] if r["id"] == "b.square")["enabled"]
    r = client.patch("/api/headings/rules/b.square", json={"enabled": False, "version": 0})
    assert r.status_code == 200 and r.json()["version"] == 1
    assert not next(x for x in r.json()["builtin"] if x["id"] == "b.square")["enabled"]
    assert client.patch("/api/headings/rules/b.square", json={"enabled": True, "version": 0}).status_code == 409
    r = client.patch("/api/headings/rules/b.square", json={"enabled": True, "version": 1})
    assert r.status_code == 200 and next(x for x in r.json()["builtin"] if x["id"] == "b.square")["enabled"]
    assert client.patch("/api/headings/rules/l9", json={"enabled": False}).status_code == 404
    assert client.patch("/api/headings/rules/b.square", json={"status": "global"}).status_code == 404  # 내장은 상태 없음
    assert client.delete("/api/headings/rules/b.square").status_code == 400
    R.add_rules([_rule(r"\(\d-\d\)")], source="user")
    ver = client.get("/api/headings/rules").json()["version"]
    assert client.patch("/api/headings/rules/l1", json={"status": "bogus", "version": ver}).status_code == 400
    r = client.patch("/api/headings/rules/l1", json={"status": "global", "version": ver})
    assert r.status_code == 200 and r.json()["learned"][0]["status"] == "global"
    assert client.delete("/api/headings/rules/l1", params={"version": ver}).status_code == 409
    r = client.delete("/api/headings/rules/l1", params={"version": ver + 1})
    assert r.status_code == 200 and r.json()["learned"] == []
    assert client.delete("/api/headings/rules/l1").status_code == 404
    h = client.get("/api/headings/history", params={"kind": "rules"}).json()
    assert [e["action"] for e in h] == ["disable", "enable", "add", "status", "delete"]


def test_api_guides_and_llm_and_docx(client):
    lst = client.get("/api/headings/guides").json()
    assert [x["name"] for x in lst] == list(G.NAMES)
    g = client.get("/api/headings/guides/rules").json()
    assert not g["custom"] and g["version"] == 0 and g["text"]
    r = client.put("/api/headings/guides/rules", json={"text": "# 지침\n시험", "version": 0})
    assert r.status_code == 200 and r.json()["custom"] and r.json()["version"] == 1
    assert client.put("/api/headings/guides/rules", json={"text": "x", "version": 0}).status_code == 409
    assert client.put("/api/headings/guides/tolerance", json={"text": "```json\n{깨진\n```"}).status_code == 400
    assert client.put("/api/headings/guides/rules", json={"text": 3}).status_code == 400
    assert client.get("/api/headings/guides/nope").status_code == 404
    assert client.put("/api/headings/guides/rules", json={"rebase": True}).json()["custom"]
    r = client.delete("/api/headings/guides/rules")
    assert r.status_code == 200 and not r.json()["custom"]
    h = client.get("/api/headings/history", params={"kind": "guide"}).json()
    assert [e["action"] for e in h] == ["save", "rebase", "reset"]
    st = client.get("/api/headings/llm").json()
    assert st["backend"] == "off" and st["available"] is False
    d = _upload(client, DOCX)
    r = client.post(f"/api/docs/{d}/headings", json={"stage": 1})
    assert r.status_code == 400 and "hwpx" in r.json()["detail"]


def test_sections_never_exceed_max():
    """본문 구간은 SECTION_MAX 를 넘지 않고(깊이 2 경계 우선, 경계가 없으면 그냥 자름) 순서·빠짐 없이 노드를 덮는다."""
    from app import heading_graph as HG

    def build(depths):
        nodes = [{"id": f"n{i}", "flow": "body"} for i in range(len(depths))]
        graph = {f"n{i}": {"role": "heading", "depth": d} for i, d in enumerate(depths)}
        return nodes, graph

    # 깊이 1 하나 아래 깊이 2 가 50 노드마다 — 300 노드
    depths = [1.0] + [2.0 if i % 50 == 0 else 3.0 for i in range(1, 300)]
    nodes, graph = build(depths)
    secs = HG.sections(nodes, graph, {})
    assert all(len(s) <= HG.SECTION_MAX for s in secs)
    assert [n for s in secs for n in s] == [n["id"] for n in nodes]
    assert all(graph[s[0]]["depth"] in (1.0, 2.0) for s in secs)  # 깊이 2 경계에서 잘림
    # 깊이 2 경계가 없는 250 노드 조각 — SECTION_MAX 씩 그냥 자름
    nodes, graph = build([1.0] + [3.0] * 249)
    secs = HG.sections(nodes, graph, {})
    assert [len(s) for s in secs] == [HG.SECTION_MAX, HG.SECTION_MAX, 250 - 2 * HG.SECTION_MAX]


# ---- 첫 분석(spec_작업 ② §9) — 새 작업을 처음 열 때 2단계 → 3단계를 스크립트로, 한 작업에 ------------------------------------------------

def test_api_first_run_chain(client):
    """{first: true} 한 번에 2단계(헤딩 그래프) → 3단계(표 구조)를 스크립트만으로 — 1단계는 2단계가 뽑고, 기록은 단계마다, 이미 결과가 있는 단계는 건너뛴다(LLM 결과를 덮지 않게)."""
    d = _upload(client, SMALL)
    r = client.post(f"/api/docs/{d}/headings", json={"first": True, "stage": 9, "llm": "x"})  # first 면 stage·llm 은 안 본다
    assert r.status_code == 202 and r.json()["first"] is True and r.json()["stage"] == 3 and r.json()["llm"] is False
    v = _wait_heads(client, d)
    assert v["job"]["status"] == "done" and v["job"]["first"] is True and v["job"]["run"] == 3, v["job"]
    assert v["stage1"] and v["stage2"] and v["stage3"] and not v["stage2"]["stale"] and not v["stage3"]["stale"]
    assert [x["stage"] for x in v["runs"]] == [1, 2, 3] and v["stage3"]["meta"]["stage2Run"] == v["stage2"]["meta"]["run"] == 2  # 표 소속 = 방금 만든 2단계 그래프
    assert client.get(f"/api/docs/{d}/outline").json().get("off") is not True  # 2단계가 생겼으니 개요 편집이 켜진다
    ev = [e for e in works.events(d) if e["kind"] == "headings"]
    assert [(e["stage"], e.get("first"), e["n"], e["llm"]) for e in ev] == [(2, True, 2, False), (3, True, 3, False)]
    # 다시 부르면 둘 다 건너뛴다 — 실행이 늘지 않고 기록도 없다
    r2 = client.post(f"/api/docs/{d}/headings", json={"first": True})
    assert r2.status_code == 202
    v2 = _wait_heads(client, d)
    assert v2["job"]["status"] == "done" and v2["job"]["run"] is None and len(v2["runs"]) == 3
    assert [s["name"] for s in v2["job"]["steps"]] == ["헤딩 그래프 — 건너뜀", "표 구조 — 건너뜀"]
    assert len([e for e in works.events(d) if e["kind"] == "headings"]) == 2
    # 여느 실행은 그대로 — first 가 아니면 보기에 first: false
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 1}).json()["first"] is False
    _wait_heads(client, d)
