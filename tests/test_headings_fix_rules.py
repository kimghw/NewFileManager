"""헤딩 규칙(app/heading_rules.py) 고침 — 5b 검증 묶음 rules: S1-shape · S1-rulescorrupt · S1-classify · S1-loadlock · S3-patch(a).

LLM 은 끈다(NFM_LLM_BACKEND=off). 규칙 저장소는 시험마다 임시 폴더(NFM_HEADINGS)."""
import copy
import json
import os
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_graph as HG
from app import heading_rules as R
from app import server

EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}
BOX = {"kind": "marker", "family": "x", "pattern": "▣", "status": "global"}


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    yield
    R._MEMORY.clear()


def _rules(**kw):
    return R.active(copy.deepcopy(EMPTY), **kw)


def _rules_file(tmp_path):
    return tmp_path / "heads" / "rules.json"


# ---- S1-shape: 번호형(알파벳·로마자·둘레 번호) 레터는 번호를 첫 값으로 바꾼 모양 하나 ----------------------------

@pytest.mark.parametrize("family,a,b,want", [
    ("alpha-upper", "A.", "C.", "A."), ("alpha-lower", "a)", "b)", "a)"), ("paren-alpha", "(a)", "(c)", "(a)"),
    ("paren-alpha", "(B)", "(G)", "(A)"), ("roman-upper", "Ⅰ.", "Ⅲ.", "Ⅰ."), ("roman-upper", "II.", "IV.", "I."),
    ("roman-lower", "ii)", "ix)", "i)"), ("roman-lower", "ⅱ.", "ⅳ.", "ⅰ."), ("enclosed", "⑵", "⑸", "⑴"),
    ("enclosed", "❷", "❾", "❶"), ("enclosed", "㉯", "㉰", "㉮"), ("enclosed", "ⓑ", "ⓩ", "ⓐ"), ("enclosed", "Ⓑ", "Ⓩ", "Ⓐ"),
])
def test_ordinal_letters_share_one_shape(family, a, b, want):
    assert R.shape_of(family, a) == R.shape_of(family, b) == want


def test_shape_keeps_case_roman_kind_and_enclosed_series_apart():
    """대·소문자, 유니코드·ASCII 로마자, 둘레 번호 묶음은 다른 레벨일 수 있어 가른다. 기호형은 그대로."""
    assert R.shape_of("paren-alpha", "(A)") != R.shape_of("paren-alpha", "(a)")
    assert R.shape_of("roman-upper", "Ⅱ.") != R.shape_of("roman-upper", "II.")
    assert R.shape_of("enclosed", "⑵") != R.shape_of("enclosed", "⒉") != R.shape_of("enclosed", "❷")
    assert R.shape_of("square", "■") == "■" and R.shape_of("decimal", "12.3.") == "N.N."


def test_enclosed_ordinal():
    o = R._ordinal
    assert o("enclosed", "⑶") == [3] and o("enclosed", "㉡") == [2] and o("enclosed", "ⓒ") == [3]
    assert o("enclosed", "❿") == [10] and o("enclosed", "㉮") == [1] and o("enclosed", "⒛") == [20]


@pytest.mark.parametrize("a,b", [("A. 배경", "C. 범위"), ("⑴ 배경", "⑶ 범위"), ("(a) 배경", "(b) 목적"), ("Ⅰ. 서론", "Ⅲ. 결론")])
def test_classify_ordinal_shape(a, b):
    rules = _rules()
    ca, cb = R.classify(a, rules), R.classify(b, rules)
    assert ca["family"] == cb["family"] and ca["shape"] == cb["shape"]
    assert ca["ord"] is not None and cb["ord"] is not None and ca["ord"] < cb["ord"]


def _stage1(lines):
    rules = _rules()
    paras = []
    for i, t in enumerate(lines):
        c = R.classify(t, rules)
        paras.append({"id": f"p{i}", "n": i, "area": "body", "cell": None, "table": None, "path": [], "leadSpaces": len(c["lead"]),
                      "fmt": "S1", "char": {"text": {"sizePt": 10.0, "bold": False}}, "text": t, "spans": [{"i": 0, "line": 0, **c}],
                      **{k: c[k] for k in ("kind", "family", "shape", "letter", "blank", "rest", "ord")}})
    return {"paras": paras, "labels": {}}


@pytest.mark.parametrize("kids", [["A. 배경", "B. 목적", "C. 범위"], ["⑴ 배경", "⑵ 목적"], ["(a) 배경", "(b) 목적"]])
def test_ordinal_siblings_one_type_in_fallback(kids):
    """「1. / A. / B. / C.」 — A·B·C 는 한 유형의 형제(계단 p0 > p1 > p2 가 아님). 스크립트 대체(LLM 없음)."""
    g = HG.build(_stage1(["1. 서론"] + kids), use_llm=False, ask=lambda jobs: pytest.fail("LLM 을 부르면 안 됨"))
    N = {n["id"]: n for n in g["nodes"]}
    ids = [f"p{i}" for i in range(1, len(kids) + 1)]
    assert len({N[i]["type"] for i in ids}) == 1
    assert all(N[i]["parent"] == "p0" for i in ids)


# ---- S1-rulescorrupt: 깨진 rules.json 은 덮어쓰지 않는다 ----------------------------------------------------

def _break(p, damage):
    good = p.read_text(encoding="utf-8")
    broken = {"truncate": good[:-3], "bom-garbage": "﻿{" + good[1:-3], "not-dict": "[1, 2]",
              "rules-not-list": json.dumps({**json.loads(good), "rules": "l1"}),
              "bad-version": json.dumps({**json.loads(good), "version": "abc"})}[damage]
    p.write_text(broken, encoding="utf-8")
    return p.read_bytes()


@pytest.mark.parametrize("damage", ["truncate", "bom-garbage", "not-dict", "rules-not-list", "bad-version"])
def test_update_refuses_to_overwrite_broken_rules_file(tmp_path, damage):
    R.add_rules([BOX], source="user")
    R.set_enabled("b.dash", False)
    p = _rules_file(tmp_path)
    raw = _break(p, damage)
    st = R.load()  # 읽는 쪽 — 빈 저장소 + 까닭(죽지 않음)
    assert st["rules"] == [] and st["version"] == 0 and st["broken"]
    with pytest.raises(R.StoreBroken, match="깨져"):
        R.add_keeps(["c:b.a>b.b:N"])  # 1단계 LLM 「그대로」
    with pytest.raises(ValueError):  # StoreBroken 은 ValueError — API 400
        R.add_rules([{"kind": "marker", "family": "z", "pattern": "◎"}], source="llm")
    with pytest.raises(R.StoreBroken):
        R.set_enabled("b.square", False, expect=0)  # 화면: GET 이 version 0 을 보였음
    with pytest.raises(R.StoreBroken):
        R.delete_rule("l1")
    assert p.read_bytes() == raw  # 그대로
    copies = list(p.parent.glob("rules.json.broken-*"))
    assert len(copies) == 1 and copies[0].read_bytes() == raw  # 사본 하나(같은 내용이면 다시 안 만듦)
    assert R.history("rules")[-1]["action"] == "disable"  # 거절한 쓰기는 이력에도 없음


def test_broken_rules_file_fixed_by_user_then_writes_resume(tmp_path):
    R.add_rules([BOX], source="user")
    p = _rules_file(tmp_path)
    good = p.read_bytes()
    p.write_bytes(good[:-5])
    with pytest.raises(R.StoreBroken):
        R.add_rules([{"kind": "marker", "family": "z", "pattern": "◎"}], source="llm")
    p.write_bytes(good)  # 사용자가 고침
    _, ids = R.add_rules([{"kind": "marker", "family": "z", "pattern": "◎"}], source="llm")
    assert ids == ["l2"] and [r["id"] for r in R.load()["rules"]] == ["l1", "l2"]


def test_rules_file_with_bom_is_read(tmp_path):
    """PowerShell 5.1 Set-Content -Encoding utf8 같은 BOM 은 깨짐이 아니다 — 읽히고 id 를 다시 쓰지 않는다."""
    R.add_rules([BOX], source="user")
    p = _rules_file(tmp_path)
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    st = R.load()
    assert [r["id"] for r in st["rules"]] == ["l1"] and "broken" not in st
    _, ids = R.add_rules([{"kind": "marker", "family": "z", "pattern": "◎"}], source="llm")
    assert ids == ["l2"]


def test_api_patch_with_broken_rules_file_is_400_and_keeps_file(tmp_path):
    R.add_rules([BOX], source="user")
    p = _rules_file(tmp_path)
    raw = _break(p, "truncate")
    c = TestClient(server.app, raise_server_exceptions=False)
    assert c.get("/api/headings/rules").json()["version"] == 0
    r = c.patch("/api/headings/rules/b.circle", json={"enabled": False, "version": 0})
    assert r.status_code == 400 and "깨져" in r.json()["detail"]
    assert p.read_bytes() == raw


# ---- S1-classify: 배운 첫머리 규칙은 첫머리(0)부터 · \g<…> 역참조 금지 ------------------------------------------

@pytest.mark.parametrize("pattern,text", [
    (r"▣\K\s*\S", "▣ 사업 개요"),
    (r"▣\K", "▣ 사업 개요"),
    (r"(?r)[가-힣]+", "다 1. 제목"),
    (r"(?r:[가-힣]+)", "다 1. 제목"),
])
def test_learned_prefix_rule_must_match_at_start(pattern, text):
    c = R._clean_rule({"kind": "marker", "family": "x", "pattern": pattern}, source="llm")
    rule = {**c, "id": "t", "rx": R.compile_pattern(pattern)}
    assert R._Run().match(rule, text, False) is None
    out = R.classify(text, _rules(extra=[{**c, "id": "t"}]))
    assert out["rule"] != "t", out
    assert out["letter"] + out["gap"] + out["rest"] == text


def test_learned_prefix_rule_at_start_still_works():
    c = R._clean_rule({"kind": "marker", "family": "box", "pattern": "▣"}, source="llm")
    out = R.classify("  ▣ 사업 개요", _rules(extra=[{**c, "id": "t"}]))
    assert (out["rule"], out["lead"], out["letter"], out["gap"], out["rest"]) == ("t", "  ", "▣", " ", "사업 개요")


@pytest.mark.parametrize("bad", [r"(\d)\.\g<1>", r"(?P<n>\d)\.\g<n>"])
def test_backreference_g_form_rejected(bad):
    with pytest.raises(ValueError, match="역참조"):
        R.add_rules([{"kind": "marker", "family": "x", "pattern": bad}], source="user")
    assert R.load()["version"] == 0


# ---- S1-loadlock: 읽기는 update 의 os.replace 와 겹치지 않게(잠금) · PermissionError 는 잠깐 쉬고 다시 ----------------

def test_load_excludes_concurrent_update(monkeypatch):
    """load() 가 rules.json 을 연 채 읽는 동안 update() 는 잠금에서 기다린다(Windows: 아니면 쓰는 쪽 PermissionError)."""
    _, ids = R.add_rules([BOX], source="user")
    inside, release = threading.Event(), threading.Event()
    real = Path.read_text

    def slow_read_text(self, *a, **k):  # 읽는 중(핸들 열림)에 멈춤
        if self.name == "rules.json" and threading.current_thread().name == "reader":
            with open(self, encoding="utf-8") as f:
                inside.set()
                release.wait(5)
                return f.read()
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", slow_read_text)
    got, err = {}, []
    reader = threading.Thread(target=lambda: got.update(R.load()), name="reader")
    reader.start()
    assert inside.wait(5)

    def write():
        try:
            R.set_enabled(ids[0], False)
        except Exception as e:  # noqa: BLE001
            err.append(e)
    writer = threading.Thread(target=write)
    writer.start()
    writer.join(0.3)
    waited = writer.is_alive()
    release.set()
    reader.join(5)
    writer.join(5)
    assert not err, err
    assert waited
    assert got["version"] == 1 and got["rules"]
    assert R.load()["version"] == 2


def test_load_retries_permission_error(monkeypatch):
    """다른 프로세스가 os.replace 하는 중(Errno 13) — 빈 저장소로 오판하지 않고 다시 읽는다."""
    R.add_rules([BOX], source="user")
    real, fails = Path.read_text, [2]

    def flaky(self, *a, **k):
        if self.name == "rules.json" and fails[0]:
            fails[0] -= 1
            raise PermissionError(13, "Permission denied")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", flaky)
    st = R.load()
    assert fails[0] == 0 and st["version"] == 1 and [r["id"] for r in st["rules"]] == ["l1"]


def test_write_retries_permission_error_on_replace(monkeypatch):
    """다른 프로세스가 rules.json 을 열고 있어 os.replace 가 잠깐 막혀도 쓰기는 된다."""
    real, fails = os.replace, [2]

    def flaky(src, dst):
        if Path(dst).name == "rules.json" and fails[0]:
            fails[0] -= 1
            raise PermissionError(13, "Access is denied")
        return real(src, dst)
    monkeypatch.setattr(R.os, "replace", flaky)
    st, ids = R.add_rules([BOX], source="user")
    assert fails[0] == 0 and ids == ["l1"] and R.load()["version"] == 1
    assert not list(R.store_dir().glob("*.tmp"))


# ---- S3-patch (a): 기대 버전이 정수가 아니면 ValueError(→ 400) — 아무것도 안 씀 ----------------------------------

def test_expect_version():
    ev = R.expect_version
    assert ev(None) is None and ev(3) == 3 and ev("2") == 2 and ev(1.7) == 1 and ev(True) == 1
    for bad in ([1], {}, "x", float("inf"), float("nan")):
        with pytest.raises(ValueError, match="정수"):
            ev(bad)


@pytest.mark.parametrize("bad", [[1], {}, "x"])
def test_update_non_numeric_version_is_value_error_and_writes_nothing(bad):
    with pytest.raises(ValueError, match="정수"):
        R.set_enabled("b.square", False, expect=bad)
    with pytest.raises(ValueError, match="정수"):
        R.add_rules([BOX], source="user", expect=bad)
    assert R.load()["version"] == 0 and R.history("rules") == []


@pytest.mark.parametrize("bad", [[1], {}])
def test_api_rule_patch_non_numeric_version_is_400(bad):
    c = TestClient(server.app, raise_server_exceptions=False)
    assert c.patch("/api/headings/rules/b.square", json={"enabled": False, "version": bad}).status_code == 400
    assert c.get("/api/headings/rules").json()["version"] == 0
