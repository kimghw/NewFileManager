"""표 서식 — 점검 · 맞추기(spec_헤딩_추출 ② §19 · app/table_style.py · tables_api 의 …/tables/{tid}/style)."""
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import owpml_check as oc
from app import server, table_heads
from app import table_style as TS
from app.hwpx_doc import P, TBL, HwpxDoc

PLAN = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
GRID = "t10834"   # 7×9 「연구시설·장비」 표 — 머리행 + 값 행(열 「구축연도」·「연구시설·장비명」 …)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


@cache
def _raw():
    return PLAN.read_bytes()


def _doc():
    d = HwpxDoc(_raw())
    d.blocks()
    return d


def _tables(d):
    return [i for i, el in d._ids.items() if el.tag == TBL and d._attached(el)]


def _check(d, tid, skip=frozenset()):
    return TS.check(d, table_heads.table(d, tid), skip=skip, source="draft")


def _odd(r):
    return [o for p in r["places"] for o in p["odd"]]


def _ok(d):
    """저장본을 다시 열어 문서 전체 판정 — 실패 아님 · 참조 규칙 위반 0."""
    base = oc.counts(oc.check_doc(HwpxDoc(_raw())))
    again = HwpxDoc(d.save())
    again.adopt_ids(d.id_state())
    res = oc.check_doc(again)
    assert oc.verdict(again, base, res)["status"] != "fail" and not res["rules"], res["rules"][:3]


def _fields(d, tid):
    pls, _ = TS.places(d, table_heads.table(d, tid))
    return [x for p in pls.values() if p["kind"] in ("col", "empty", "foot") for x in p["cells"]]


# ---- 값 꼴 ------------------------------------------------------------------------------------------------------------

def test_empty_mark_families():
    assert TS.empty_mark("") == ("blank", "") and TS.empty_mark("  ") == ("blank", "")
    assert TS.empty_mark(" – ") == ("dash", "–") and TS.empty_mark("-") == ("dash", "-") and TS.empty_mark("ㅡ") == ("dash", "ㅡ")
    assert TS.empty_mark("해당 없음") == ("word", "해당 없음") and TS.empty_mark("N/A") == ("word", "N/A")
    assert TS.empty_mark("-12") is None and TS.empty_mark("2024") is None and TS.empty_mark("- 산출근거") is None


def test_show_and_ref():
    assert TS.show("lineSpacingPct", 160) == "160%" and TS.show("align", "center") == "가운데" and TS.show("valign", "top") == "위"
    assert TS.show("margins", {"l": 1.8, "r": 1.8, "t": 0.5, "b": 0.5}) == "왼 1.8 · 오 1.8 · 위 0.5 · 아래 0.5mm"
    assert TS.show("mark", "") == "빈 칸" and TS.show("mark", "–") == "「–」" and TS.show("bold", True) == "켬"
    assert TS.ref(0, 0) == "A1" and TS.ref(2, 27) == "AB3"


# ---- 점검 ------------------------------------------------------------------------------------------------------------

def test_check_every_sample_table_keys_unique_and_well_formed():
    d = _doc()
    n = 0
    for tid in _tables(d):
        tb = table_heads.table(d, tid)
        if tb is None:
            continue
        r = TS.check(d, tb, source="draft")
        keys = [o["key"] for o in _odd(r)]
        assert len(keys) == len(set(keys)) and all(TS.KEY_RE.match(k) for k in keys)
        assert r["counts"]["odd"] == len(keys) and r["counts"]["check"] == sum(o["check"] for o in _odd(r))
        for p in r["places"]:
            assert p["kind"] in TS.KINDS and (p["odd"] == [] or p["rep"]["para"] or p["rep"]["cell"])
            for o in p["odd"]:
                assert o["diff"] and all(x["now"] != x["want"] for x in o["diff"])
                assert not {x["key"] for x in o["diff"]} & {"ratioPct", "spacingPct"}   # 장평 · 자간은 견주지 않는다(칸 폭 맞춤)
        n += 1
    assert n > 100


def test_places_split_head_stub_columns():
    d = _doc()
    r = _check(d, GRID)
    kinds = {p["kind"] for p in r["places"]}
    assert {"head", "col"} <= kinds
    names = [p["name"] for p in r["places"] if p["kind"] == "col"]
    assert "열 「구축연도」" in names and "열 「연구시설·장비명」" in names


def test_line_spacing_odd_and_conform_keeps_fit():
    d = _doc()
    cells = [x for x in _fields(d, GRID) if x["col"] == 1][:4]
    assert len(cells) == 4
    for i, x in enumerate(cells):
        d.set_text(x["id"], f"장비{i}")
    odd_cell = cells[2]
    pid = next(d._id(p) for p in d._ids[odd_cell["id"]].iter(P))
    fmt = d.get_format(pid)
    d.apply_format([pid], d.derive_format(fmt, {"lineSpacingPct": 200, "spacingPct": -10}))   # 줄 간격(다름) + 자간(칸 폭 맞춤 — 견주지 않음)
    r = _check(d, GRID)
    hit = [o for o in _odd(r) if o["para"] == pid]
    assert len(hit) == 1 and [x["key"] for x in hit[0]["diff"]] == ["lineSpacingPct"] and hit[0]["diff"][0]["now"] == "200%" and not hit[0]["check"]
    out = TS.conform(d, r, [hit[0]["key"]])
    assert out["done"] == [hit[0]["key"]] and out["formatted"] == [pid] and not out["skipped"]
    s = d.get_format(pid)["summary"]
    assert s["lineSpacingPct"] == fmt["summary"]["lineSpacingPct"] and s["spacingPct"] == -10   # 줄 간격은 대표로 · 자간은 그 문단 것
    assert not [o for o in _odd(_check(d, GRID)) if o["para"] == pid]
    _ok(d)


def test_big_difference_needs_check():
    d = _doc()
    cells = [x for x in _fields(d, GRID) if x["col"] == 1][:3]
    for i, x in enumerate(cells):
        d.set_text(x["id"], f"장비{i}")
    sub = d._ids[cells[0]["id"]]
    pid = next(d._id(p) for p in sub.iter(P))
    d.apply_format([pid], d.derive_format(d.get_format(pid), {"sizePt": 16, "bold": True}))
    hit = [o for o in _odd(_check(d, GRID)) if o["para"] == pid]
    assert hit and hit[0]["check"] and "일부러" in hit[0]["why"]


def test_skip_outline_lines():
    d = _doc()
    cells = [x for x in _fields(d, GRID) if x["col"] == 1][:3]
    for i, x in enumerate(cells):
        d.set_text(x["id"], f"장비{i}")
    pid = next(d._id(p) for p in d._ids[cells[0]["id"]].iter(P))
    d.apply_format([pid], d.derive_format(d.get_format(pid), {"lineSpacingPct": 220}))
    assert [o for o in _odd(_check(d, GRID)) if o["para"] == pid]
    assert not [o for o in _odd(_check(d, GRID, skip=frozenset({pid}))) if o["para"] == pid]   # 개요 줄(템플릿이 다룸)은 안 견준다


# ---- 빈 값 표시 -------------------------------------------------------------------------------------------------------

def _marks(d):
    """GRID 의 필드를 값으로 채우고 몇 칸에 빈 값 표시를 심는다 → (「–」 칸들, 「-」 칸, 빈 칸)."""
    fields = sorted(_fields(d, GRID), key=lambda x: (x["row"], x["col"]))
    for i, x in enumerate(fields):
        d.set_text(x["id"], f"값{i}")
    pool = [x for x in fields if x["col"] >= 4]   # 왼쪽 열은 짧은 글로 채우면 초안이 머리열로 읽는다 — 값 열에만 심는다
    dash, hyphen, blank = pool[0:3], pool[4], pool[6]
    for x in dash:
        d.set_text(x["id"], "–")
    d.set_text(hyphen["id"], "-")
    for p in list(d._ids[blank["id"]].iter(P)):
        for t in [t for t in p.iter() if t.tag.endswith("}t")]:
            t.getparent().remove(t)
    d._touch(d._ids[blank["id"]])
    return dash, hyphen, blank


def test_empty_mark_of_table_and_conform():
    d = _doc()
    dash, hyphen, blank = _marks(d)
    r = _check(d, GRID)
    e = r["empty"]
    assert e["mark"] == "–" and e["family"] == "dash" and e["counts"] == {"–": 3, "-": 1} and e["blanks"] == 1 and e["fillBlanks"] and not e["mixed"]
    by = {o["key"]: o for o in _odd(r)}
    mk, bk = f"mark:{hyphen['id']}:", f"blank:{blank['id']}:"
    assert by[mk]["diff"][0]["now"] == "「-」" and by[mk]["diff"][0]["want"] == "「–」" and not by[mk]["check"]
    assert by[bk]["check"] and by[bk]["diff"][0]["now"] == "빈 칸"                       # 빈 칸은 양식의 쓸 자리일 수 있다 — 확인
    out = TS.conform(d, r, [mk, bk])
    assert sorted(out["done"]) == sorted([mk, bk]) and not out["skipped"]
    texts = TS.places(d, table_heads.table(d, GRID))[1]
    assert texts[hyphen["id"]] == "–" and texts[blank["id"]] == "–"
    r2 = _check(d, GRID)
    assert r2["empty"]["counts"] == {"–": 5} and r2["empty"]["blanks"] == 0 and not [o for o in _odd(r2) if o["what"] in ("mark", "blank")]
    _ok(d)


def test_blanks_left_alone_when_marks_are_few():
    d = _doc()
    r = _check(d, GRID)   # 빈 양식 — 필드가 거의 다 빈 칸: 쓸 자리로 본다
    assert r["empty"]["mark"] is None and r["empty"]["blanks"] > 10 and not r["empty"]["fillBlanks"]
    assert not [o for o in _odd(r) if o["what"] in ("mark", "blank")]


def test_conform_skips_stale_key():
    d = _doc()
    r = _check(d, GRID)
    out = TS.conform(d, r, ["para:c1:p2"])
    assert out["done"] == [] and out["skipped"][0]["why"].startswith("이미 같거나")


def test_conform_everything_converges_and_saves_clean():
    d = _doc()
    before = after = 0
    for tid in _tables(d)[:60]:
        tb = table_heads.table(d, tid)
        if tb is None:
            continue
        r = TS.check(d, tb, source="draft")
        keys = [o["key"] for o in _odd(r)]
        if not keys:
            continue
        before += len(keys)
        out = TS.conform(d, r, keys)
        assert not out["skipped"], out["skipped"][:3]
        after += len(_odd(TS.check(d, table_heads.table(d, tid), source="draft")))
    assert before > 20 and after == 0
    _ok(d)


# ---- API -------------------------------------------------------------------------------------------------------------

def test_api_style_get_and_apply():
    server.DOCS.clear()
    c = TestClient(server.app)
    try:
        r = c.post("/api/docs", files={"file": (PLAN.name, _raw())})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        url = f"/api/docs/{d}/tables/{GRID}/style"
        _marks(s.doc)
        v = c.get(url)
        assert v.status_code == 200, v.text
        v = v.json()
        assert v["source"] == "draft" and v["empty"]["mark"] == "–" and v["rev"] == s.rev and v["counts"]["odd"] == len(_odd(v))
        mk = next(o["key"] for o in _odd(v) if o["what"] == "mark")
        a = c.post(f"{url}/apply", json={"keys": [mk, "para:c1:p2"]})
        assert a.status_code == 200, a.text
        st = a.json()["styled"]
        assert st["done"] == [mk] and st["skipped"][0]["key"] == "para:c1:p2" and st["table"] == GRID
        assert c.post(f"{url}/apply", json={"keys": [mk]}).status_code == 409                  # 이미 맞췄다
        assert c.post(f"{url}/apply", json={"keys": ["bad"]}).status_code == 400 and c.post(f"{url}/apply", json={"keys": []}).status_code == 400
        assert c.get(f"/api/docs/{d}/tables/t99999/style").status_code == 404
        assert c.post(f"/api/docs/{d}/undo").status_code == 200 and TS.places(s.doc, table_heads.table(s.doc, GRID))[1][next(o["cell"] for o in _odd(v) if o["key"] == mk)] == "-"
    finally:
        server.DOCS.clear()
