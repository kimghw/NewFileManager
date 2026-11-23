"""표 서식 — 점검 · 맞추기(spec_헤딩_추출 ② §19 · app/table_style.py · tables_api 의 …/tables/{tid}/style)
+ 테이블 매니저 연결 · 묶기(rev · sig) · 보류 · 칸 전체 확인(spec_테이블매니저 ② §4 「지우거나 쓰는 도구」)."""
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import heading_tables as HT
from app import owpml_check as oc
from app import server, table_heads, tables_api
from app import table_excel as TX
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


# ---- 묶기(sig) · 칸 전체 확인(spec_테이블매니저 ② §4 「지우거나 쓰는 도구」) ----------------------------------------------------

def test_items_carry_sig_and_conform_skips_what_changed_since_the_check():
    d = _doc()
    dash, hyphen, _blank = _marks(d)
    r = _check(d, GRID)
    assert _odd(r) and all(isinstance(o["sig"], str) and len(o["sig"]) == 12 for o in _odd(r))
    mk = f"mark:{hyphen['id']}:"
    sig = next(o["sig"] for o in _odd(r) if o["key"] == mk)
    assert next(o["sig"] for o in _odd(_check(d, GRID)) if o["key"] == mk) == sig                 # 같은 문서 = 같은 sig
    stale = [{"key": mk, "why": "달라짐 — 다시 점검"}]
    assert TS.conform(d, r, [mk], sigs={mk: "0" * 12}) == {"done": [], "skipped": stale, "formatted": []}
    assert TS.conform(d, r, [mk], sigs={})["skipped"] == stale                                     # sigs 를 줬는데 그 키의 sig 가 없어도
    for x in dash:                                                                                 # 점검한 뒤 표의 표시가 바뀜(「–」 → 「—」) — 같은 키여도 맞출 값이 다르다
        d.set_text(x["id"], "—")
    r2 = _check(d, GRID)
    sig2 = next(o["sig"] for o in _odd(r2) if o["key"] == mk)
    assert r2["empty"]["mark"] == "—" and sig2 != sig
    assert TS.conform(d, r2, [mk], sigs={mk: sig})["skipped"] == stale                             # 화면이 본 것은 「–」 로 맞추기였다
    assert TS.places(d, table_heads.table(d, GRID))[1][hyphen["id"]] == "-"
    assert TS.conform(d, r2, [mk], sigs={mk: sig2})["done"] == [mk]
    assert TS.places(d, table_heads.table(d, GRID))[1][hyphen["id"]] == "—"


def test_mark_is_not_written_over_text_added_after_the_check():
    """결함 ㉠ — 옛 문단 목록(3단계 결과의 표)으로 점검해 그 칸을 아직 「-」 로 봐도, 쓰기 직전에 칸 전체를 문서에서 다시 봐서 더 쓴 글을 지우지 않는다."""
    d = _doc()
    _dash, hyphen, _blank = _marks(d)
    stored = table_heads.table(d, GRID)                                    # 이때의 문단 목록을 지닌 표
    first = next(c for c in stored["cells"] if c["id"] == hyphen["id"])["paras"][0]
    d.insert_after(first, [{"kind": "para", "text": "IMPORTANT CONTENT", "templateId": first}])   # 그 뒤 그 칸에 문단을 하나 더(칸 id · 자리 · 병합 그대로)
    mk = f"mark:{hyphen['id']}:"
    stale = TS.check(d, stored, source="stage3")
    assert mk in [o["key"] for o in _odd(stale)]                           # 옛 목록으로는 여전히 후보
    out = TS.conform(d, stale, [mk])
    assert out["done"] == [] and out["skipped"] == [{"key": mk, "why": "칸에 다른 글이 있습니다"}]
    assert TS.cell_now(d, hyphen["id"]) == ("- IMPORTANT CONTENT", False)   # 더 쓴 글이 남았다
    assert mk not in [o["key"] for o in _odd(_check(d, GRID))]             # 지금 문단 목록으로는 후보가 아니다
    assert TS.cell_now(d, "c0") is None


def test_mark_items_only_for_the_cells_given():
    d = _doc()
    dash, hyphen, blank = _marks(d)
    tb = table_heads.table(d, GRID)
    fields = {x["id"] for x in tb["cells"] if x["role"] == "field"}
    r = TS.check(d, tb, source="stage3", mark_cells=frozenset(fields - {hyphen["id"], dash[0]["id"]}))
    assert r["empty"]["counts"] == {"–": 2} and r["empty"]["blanks"] == 1                  # 뺀 칸은 표시를 세지도 않는다
    assert [o["key"] for o in _odd(r) if o["what"] in ("mark", "blank")] == [f"blank:{blank['id']}:"]
    assert [p["cells"] for p in r["places"] if p["kind"] == "empty"] == [5]                # 서식을 견주는 자리(빈 값)의 칸은 그대로
    full = TS.check(d, tb, source="stage3", mark_cells=frozenset(fields))
    assert full["empty"] == _check(d, GRID)["empty"] and [o["key"] for o in _odd(full)] == [o["key"] for o in _odd(_check(d, GRID))]


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

HELD_MSG = "헤더 지정 1칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요"


@pytest.fixture()
def client():
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def _open(c):
    r = c.post("/api/docs", files={"file": (PLAN.name, _raw())})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    return d, server.DOCS[d], f"/api/docs/{d}/tables/{GRID}/style"


def _stage3(s, roles=None):
    """끝난 3단계 결과(스크립트만 — 그 표 하나)를 세션에 넣는다: 지금 문서 차례의 것(meta.rev). roles = 그때의 사람 헤더 지정 {칸 id: 역할} → 저장된 그 표."""
    t = HT.build(TX.records(s.doc, GRID, None, getattr(s, "doc_key", None)), use_llm=False, roles={GRID: roles} if roles else None)
    t.pop("_calls", None)
    t["meta"] = {"rev": s.rev, "run": 1}
    heading_runs.state(s)["stage3"] = t
    return t["tables"][0]


def _judged(s):
    """표 서식 점검이 쓰는 판정(tables_api._style_tb) → (출처, {칸 id: 역할}, 보류, 빈 값 표시를 볼 칸)."""
    with s.lock:
        j, held, marks = tables_api._style_tb(s, GRID)
    return j["source"], {x["id"]: x["role"] for x in j["table"]["cells"]}, held, marks


def _first_para(s, cid):
    return next(s.doc._id(p) for p in s.doc._ids[cid].iter(P))


def _sigs(v):
    return {o["key"]: o["sig"] for o in _odd(v)}


def test_api_style_get_and_apply(client):
    c = client
    d, s, url = _open(c)
    _marks(s.doc)
    v = c.get(url)
    assert v.status_code == 200, v.text
    v = v.json()
    assert v["source"] == "draft" and v["empty"]["mark"] == "–" and v["rev"] == s.rev and v["counts"]["odd"] == len(_odd(v))
    assert v["reuse"] == {"ok": False, "why": "3단계 결과에 이 표가 없음"} and v["held"] == [] and all(o["sig"] for o in _odd(v))
    mk = next(o["key"] for o in _odd(v) if o["what"] == "mark")
    a = c.post(f"{url}/apply", json={"keys": [mk, "para:c1:p2"], "rev": v["rev"], "sigs": _sigs(v)})   # 화면이 보내는 꼴(rev · sigs)
    assert a.status_code == 200, a.text
    st = a.json()["styled"]
    assert st["done"] == [mk] and st["skipped"][0]["key"] == "para:c1:p2" and st["table"] == GRID
    assert c.post(f"{url}/apply", json={"keys": [mk]}).status_code == 409                  # 이미 맞췄다
    assert c.post(f"{url}/apply", json={"keys": ["bad"]}).status_code == 400 and c.post(f"{url}/apply", json={"keys": []}).status_code == 400
    assert c.get(f"/api/docs/{d}/tables/t99999/style").status_code == 404
    assert c.post(f"/api/docs/{d}/undo").status_code == 200 and TS.places(s.doc, table_heads.table(s.doc, GRID))[1][next(o["cell"] for o in _odd(v) if o["key"] == mk)] == "-"


def test_api_stage3_roles_are_reused_but_paragraphs_are_read_now(client):
    """결함 ㉠ — 3단계 결과가 있는 세션에서 그 뒤 칸에 문단을 더 쓰면: 점검이 그 칸을 후보로 안 내고, 그 키를 억지로 보내도 글이 안 지워진다."""
    d, s, url = _open(client)
    _dash, hyphen, _blank = _marks(s.doc)
    stored = _stage3(s)
    v = client.get(url).json()
    mk = f"mark:{hyphen['id']}:"
    assert v["source"] == "stage3" and v["reuse"] == {"ok": True, "why": "문서가 그대로"}
    sig = _sigs(v)[mk]                                                           # 「-」 칸 — 이때는 맞출 후보
    first = _first_para(s, hyphen["id"])
    s.doc.insert_after(first, [{"kind": "para", "text": "IMPORTANT CONTENT", "templateId": first}])   # 그 뒤 그 칸에 문단을 더 씀(칸 id 집합은 그대로)
    assert len(next(c for c in stored["cells"] if c["id"] == hyphen["id"])["paras"]) == 1             # 저장된 표의 문단 목록은 옛것
    v2 = client.get(url).json()
    assert v2["source"] == "stage3" and mk not in _sigs(v2)                      # 역할은 다시 쓰되 문단은 지금 것 — 후보가 아니다
    for body in ({"keys": [mk]}, {"keys": [mk], "rev": v["rev"], "sigs": {mk: sig}}):
        assert client.post(f"{url}/apply", json=body).status_code == 409         # 억지로 보내도
    assert TS.cell_now(s.doc, hyphen["id"]) == ("- IMPORTANT CONTENT", False)
    heading_runs.state(s)["stage3"]["meta"]["rev"] = -1                          # 그 결과가 옛 문서 차례의 것이고 이 표의 자료(칸 글)가 달라졌어도 — 판정을 버리지 않고 칸마다 이어 쓴다(2026-11-23 · spec_테이블매니저 ② §2 「판정 이어 쓰기」)
    v3 = client.get(url).json()
    assert v3["source"] == "stage3" and v3["reuse"]["ok"] and v3["reuse"]["why"].startswith("판정을 이어 씀 — 판정 때 있던 칸") and mk not in _sigs(v3)   # 문단은 지금 것 — 여전히 후보가 아니다
    assert heading_runs.state(s)["stage3"]["tables"][0] == stored                # 저장된 결과는 안 고친다


def test_api_released_designation_gives_the_role_back(client):
    """결함 ㉡ — 지정이 있는 채 3단계를 돌린 뒤 지정을 풀면 자동 역할로 돌아온다(전에는 저장된 최종 역할을 그대로 썼다)."""
    d, s, url = _open(client)
    heads = f"/api/docs/{d}/tables/{GRID}/heads"
    cell = next(x["id"] for x in table_heads.table(s.doc, GRID)["cells"] if x["role"] == "field" and x["textFull"])
    assert client.put(heads, json={"cells": [cell], "role": "rowhead"}).status_code == 200
    stored = next(c for c in _stage3(s, table_heads.get(s.id, GRID))["cells"] if c["id"] == cell)
    assert (stored["role"], stored["auto"], stored["reason"]) == ("rowhead", "field", "사용자 지정")       # 최종 역할에 지정이 녹아 있다
    src, roles, held, _ = _judged(s)
    assert (src, roles[cell], held) == ("stage3", "rowhead", [])

    def stub(v):
        return sum(p["cells"] for p in v["places"] if p["kind"] == "stub")
    n = stub(client.get(url).json())
    assert client.put(heads, json={"cells": [cell], "role": None}).status_code == 200                      # 지정을 푼다
    src, roles, held, _ = _judged(s)
    assert (src, roles[cell], held) == ("stage3", "field", [])
    assert stub(client.get(url).json()) == n - 1


def test_api_held_designation_is_reported_and_blocks_apply(client):
    d, s, url = _open(client)
    _dash, hyphen, _blank = _marks(s.doc)
    heads = f"/api/docs/{d}/tables/{GRID}/heads"
    cell = next(x for x in _fields(s.doc, GRID) if x["col"] == 5 and x["row"] == 3)
    cid, pid, mk = cell["id"], _first_para(s, cell["id"]), f"mark:{hyphen['id']}:"
    assert client.put(heads, json={"cells": [cid], "role": "rowhead"}).status_code == 200
    assert table_heads.load(s.id)["stamps"][GRID][cid] == {"at": [3, 5, 1, 1], "text": cell["textFull"]}   # 지정할 때의 자리 · 글
    v = client.get(url).json()
    assert v["held"] == [] and _judged(s)[1][cid] == "rowhead" and mk in _sigs(v)
    assert client.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": "다른 값을 씀"}).status_code == 200    # 지정한 칸의 글이 바뀜
    v = client.get(url).json()
    assert v["held"] == [{"cell": cid, "role": "rowhead", "why": "글이 바뀜"}]
    assert _judged(s)[1][cid] == "field"                                         # 보류된 지정은 판정에 안 쓴다(그 칸은 자동 역할)
    a = client.post(f"{url}/apply", json={"keys": [mk], "rev": v["rev"], "sigs": _sigs(v)})
    assert a.status_code == 409 and a.json()["detail"] == HELD_MSG               # 문서를 바꾸는 요청은 멈춘다
    assert TS.cell_now(s.doc, hyphen["id"])[0] == "-" and table_heads.get(s.id, GRID) == {cid: "rowhead"}   # 안 바뀜 · 지정을 버리지도 않는다
    assert client.put(heads, json={"cells": [cid], "role": "rowhead"}).status_code == 200                  # 다시 지정 — 새 도장
    v = client.get(url).json()
    assert v["held"] == [] and _judged(s)[1][cid] == "rowhead"
    a = client.post(f"{url}/apply", json={"keys": [mk], "rev": v["rev"], "sigs": _sigs(v)})
    assert a.status_code == 200 and a.json()["styled"]["done"] == [mk]


def test_api_column_insert_leaves_the_designation_on_the_old_cell_and_holds_it(client):
    """「-」 칸을 머리열로 지정 → 왼쪽에 열 넣기: 옛 칸 id 는 빈 새 자리에 남고 글은 새 id 로 간다 — 그 지정은 보류, 새 칸의 「-」 를 맞추는 요청은 멈춘다."""
    d, s, url = _open(client)
    _dash, hyphen, _blank = _marks(s.doc)
    heads = f"/api/docs/{d}/tables/{GRID}/heads"
    assert client.put(heads, json={"cells": [hyphen["id"]], "role": "rowhead"}).status_code == 200
    v = client.get(url).json()
    assert v["held"] == [] and not [o for o in _odd(v) if o["what"] == "mark"]                 # 머리열로 지정한 칸 — 빈 값 표시 후보가 아니다
    assert client.post(f"/api/docs/{d}/table", json={"id": _first_para(s, hyphen["id"]), "op": "col_left"}).status_code == 200
    assert TS.cell_now(s.doc, hyphen["id"])[0] == ""                                           # 옛 id 의 칸은 비었다
    v = client.get(url).json()
    assert v["held"] == [{"cell": hyphen["id"], "role": "rowhead", "why": "글이 바뀜"}]
    moved = [o for o in _odd(v) if o["what"] == "mark"]
    assert len(moved) == 1 and moved[0]["cell"] != hyphen["id"] and TS.cell_now(s.doc, moved[0]["cell"])[0] == "-"   # 글이 간 새 칸 — 지정이 안 따라와 후보로 보인다
    a = client.post(f"{url}/apply", json={"keys": [moved[0]["key"]], "rev": v["rev"], "sigs": _sigs(v)})
    assert a.status_code == 409 and a.json()["detail"] == HELD_MSG
    assert TS.cell_now(s.doc, moved[0]["cell"])[0] == "-"                                      # 문서는 안 바뀐다


def test_api_apply_is_bound_to_rev_and_sig(client):
    d, s, url = _open(client)
    dash, hyphen, _blank = _marks(s.doc)
    cell = next(x for x in _fields(s.doc, GRID) if x["col"] == 4 and x["row"] == 4)
    pid = _first_para(s, cell["id"])
    s.doc.apply_format([pid], s.doc.derive_format(s.doc.get_format(pid), {"lineSpacingPct": 200}))   # 열 자리의 다른 서식 하나(빈 값 표시와 무관)
    v = client.get(url).json()
    mk, pk = f"mark:{hyphen['id']}:", f"para:{cell['id']}:{pid}"
    assert {mk, pk} <= set(_sigs(v))
    for x in dash:                                                               # 점검한 뒤 표의 표시가 바뀜(문서 차례는 그대로 — 직접 고침): 같은 키여도 맞출 값이 다르다
        s.doc.set_text(x["id"], "—")
    a = client.post(f"{url}/apply", json={"keys": [mk, pk], "rev": v["rev"], "sigs": _sigs(v)})
    assert a.status_code == 200, a.text
    st = a.json()["styled"]
    assert st["done"] == [pk] and st["skipped"] == [{"key": mk, "why": "달라짐 — 다시 점검"}]
    assert TS.cell_now(s.doc, hyphen["id"])[0] == "-"                            # 본 것과 다른 값으로는 안 맞춘다
    assert client.post(f"{url}/apply", json={"keys": [mk], "rev": v["rev"], "sigs": _sigs(v)}).status_code == 409   # 맞출 것이 안 남음(sig 가 다른 것뿐)
    v2 = client.get(url).json()
    assert v2["rev"] == v["rev"] + 1 and _sigs(v2)[mk] != _sigs(v)[mk]
    old = client.post(f"{url}/apply", json={"keys": [mk], "rev": v["rev"], "sigs": _sigs(v2)})
    assert old.status_code == 409 and "점검한 뒤 문서가 바뀌었습니다" in old.json()["detail"]             # 옛 문서 차례
    ok = client.post(f"{url}/apply", json={"keys": [mk], "rev": v2["rev"], "sigs": _sigs(v2)})
    assert ok.status_code == 200 and ok.json()["styled"]["done"] == [mk] and TS.cell_now(s.doc, hyphen["id"])[0] == "—"
    for bad in ({"rev": "3"}, {"rev": True}, {"sigs": [mk]}, {"sigs": {mk: 3}}):
        assert client.post(f"{url}/apply", json={"keys": [mk], **bad}).status_code == 400


def test_api_mark_items_follow_draft_roles_even_when_stage3_is_reused(client):
    """빈 값 표시 항목은 「초안 + 유효한 사람 지정」 에서 필드인 칸에만 — LLM 이 헤더를 필드로 고친 칸(3단계 결과)은 서식만 견주고 글은 안 쓴다."""
    d, s, url = _open(client)
    _marks(s.doc)
    head = next(x for x in table_heads.table(s.doc, GRID)["cells"] if x["role"] == "rowhead" and x["row"] == 6)   # 왼쪽 아래 머리열 칸
    s.doc.set_text(head["id"], "-")
    assert next(x for x in table_heads.table(s.doc, GRID)["cells"] if x["id"] == head["id"])["role"] == "rowhead"   # 초안은 여전히 머리열
    hk = f"mark:{head['id']}:"
    assert hk not in _sigs(client.get(url).json())
    t = _stage3(s)
    next(c for c in t["cells"] if c["id"] == head["id"]).update(role="field", changed=True, reason="값으로 읽힘")   # LLM 이 그 칸을 필드로 고쳤다고 치자
    v = client.get(url).json()
    src, roles, _held, marks = _judged(s)
    assert v["source"] == src == "stage3" and roles[head["id"]] == "field" and head["id"] not in marks
    assert [p["cells"] for p in v["places"] if p["kind"] == "empty"] == [6]      # 서식 견주기는 3단계 역할로 — 그 칸도 빈 값 자리에(「–」 3 · 「-」 1 · 빈 칸 1 + 그 칸)
    assert v["empty"]["counts"] == {"–": 3, "-": 1} and hk not in _sigs(v)       # 표시는 초안에서 필드인 칸만 세고, 그 칸에 표시를 쓰는 항목은 안 낸다
    assert client.post(f"{url}/apply", json={"keys": [hk]}).status_code == 409
    assert TS.cell_now(s.doc, head["id"])[0] == "-"


# ---- 양식의 확정본(spec_테이블매니저 ② §10 「양식의 표 판정」) — 판정의 출처 · 확정본의 판이 항목의 sig 에 든다 ------------------------------

def test_item_sig_carries_the_judgment_origin():
    d = _doc()
    _marks(d)
    tb = table_heads.table(d, GRID)
    draft = _sigs(TS.check(d, tb, source="draft"))
    assert draft and draft == _sigs(TS.check(d, tb, source="draft"))             # 같은 점검이면 같은 값
    one = _sigs(TS.check(d, tb, source="template", template={"id": "e1", "rev": 1}))
    two = _sigs(TS.check(d, tb, source="template", template={"id": "e1", "rev": 2}))
    other = _sigs(TS.check(d, tb, source="template", template={"id": "e2", "rev": 1}))
    assert set(one) == set(two) == set(other) == set(draft)                      # 항목은 같다 — 값(지금 · 맞출 값 · 대표)도 같다
    assert all(len({draft[k], one[k], two[k], other[k]}) == 4 for k in draft)    # 그래도 판정의 출처 · 확정본 · 그 판이 다르면 sig 가 다르다


def test_api_template_judgment_and_sig_follow_the_entry_rev(client, tmp_path, monkeypatch):
    """양식의 확정본이 있으면 점검이 그 판정을 쓰고(source template · template {id, rev}), 점검한 뒤 확정본이 생기거나 고쳐지면 — 문서 차례는 그대로여도 — 맞추기가 건너뛴다."""
    forms = tmp_path / "forms"
    forms.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NFM_FORMS", str(forms))
    (forms / "시험계획서.md").write_text('# 양식 정보 — 시험\n\n```json\n{"name": "시험 계획서", "match": {"names": ["*연구개발계획서*"]}}\n```\n', encoding="utf-8")
    d, s, url = _open(client)
    _dash, hyphen, _blank = _marks(s.doc)
    mk, typ = f"mark:{hyphen['id']}:", f"/api/docs/{d}/tables/{GRID}/type"
    v0 = client.get(url).json()
    assert v0["source"] == "draft" and v0["template"] is None and mk in _sigs(v0)
    put = client.put(typ, json={"rev": s.rev, "match": None})                    # 지금 판정으로 확정(문서는 안 바뀐다)
    assert put.status_code == 200, put.text
    eid = put.json()["saved"]["id"]
    v1 = client.get(url).json()
    assert v1["source"] == "template" and v1["template"] == {"id": eid, "rev": 1} and v1["rev"] == v0["rev"]
    assert set(_sigs(v1)) == set(_sigs(v0)) and all(_sigs(v1)[k] != _sigs(v0)[k] for k in _sigs(v0))   # 같은 항목이어도 본 판정이 다르다
    src, _roles, held, marks = _judged(s)
    assert (src, held, marks) == ("template", [], None)                          # 빈 값 표시도 확정본의 필드 칸 그대로
    early = client.post(f"{url}/apply", json={"keys": [mk], "rev": v0["rev"], "sigs": _sigs(v0)})   # 확정본이 생기기 전에 본 점검
    assert early.status_code == 409 and TS.cell_now(s.doc, hyphen["id"])[0] == "-"
    again = client.put(typ, json={"rev": s.rev, "match": {"id": eid, "rev": 1}})  # 확정본을 고침 → 판 2
    assert again.status_code == 200 and again.json()["saved"] == {"id": eid, "rev": 2, "created": False, "overlaps": []}
    v2 = client.get(url).json()
    assert v2["template"] == {"id": eid, "rev": 2} and _sigs(v2)[mk] != _sigs(v1)[mk]
    stale = client.post(f"{url}/apply", json={"keys": [mk], "rev": v1["rev"], "sigs": _sigs(v1)})   # 고쳐지기 전의 판으로 본 점검
    assert stale.status_code == 409 and TS.cell_now(s.doc, hyphen["id"])[0] == "-"
    ok = client.post(f"{url}/apply", json={"keys": [mk], "rev": v2["rev"], "sigs": _sigs(v2)})
    assert ok.status_code == 200 and ok.json()["styled"]["done"] == [mk] and TS.cell_now(s.doc, hyphen["id"])[0] == "–"
