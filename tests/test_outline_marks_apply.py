"""짝 표지(형광펜)가 든 줄을 맞추는 반영 — spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」 · §8-4 「계획 모두 반영」 · spec_owpml_편집 ② §2 「짝 표지」.

연구개발계획서 양식의 개요 줄 둘에 형광펜을 칠해 올리고(LLM 끔 · 에이전트 답은 가짜) 서식 정리 계획을 「모두 반영」 한다:
  LETTER — 대표와 **레터가 다른** 줄(양식에서는 「   ㅇ 비영리기관 현황」 — 대표 「  o 」) → 글을 못 바꾸므로 모양만 맞추고 남긴다(left · why letter)
  LEAD   — 대표와 레터는 같고 **레터 앞 빈칸만** 다른 줄 → 표지를 지키며 빈칸만 바꿔 완전히 맞춘다(left 없음)
전에는 형광펜 든 줄 하나 때문에 replace_prefix 의 가드에 걸려 계획 전체가 400 으로 되돌려졌다(2026-11-17 — 작업 하나에서 괄호 줄 4개).
두 줄은 양식을 한 번 올려 헤딩 그래프를 지은 뒤 고른다(템플릿 번호는 그래프 규칙에 따라 바뀔 수 있다 — 문단 id 는 같은 문서라 같다)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, llm, server
from app import outline_edit as OE
from app import outline_match as M
from app import tpl_agent as A
from app.hwpx_doc import NB, HwpxDoc
from app.hwpx_struct import RUN, T, _p

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


def _open(c, data, name):
    """올리고 1·2단계(LLM 끔) → (문서 id, 세션)."""
    r = c.post("/api/docs", files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    s = server.DOCS[d]
    heading_runs.run_sync(s, 1, False)
    heading_runs.run_sync(s, 2, False)
    assert c.get(f"/api/docs/{d}/outline").status_code == 200  # 오버레이를 만든다
    return d, s


def _env_of(tmp):
    return {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
            "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}


def _plain_text_t(doc, pid, a):
    """문단 pid 의 글 자리 a 가 든, 글만 든 hp:t 와 그 안의 자리 | None."""
    n = 0
    for r in doc._ids[pid].iterchildren(RUN):
        for t in r.iterchildren(T):
            s = t.text or ""
            if len(t):  # 자식(탭 · 표지 …)이 든 hp:t 뒤의 자리는 세지 않는다 — 그런 줄은 고르지 않는다
                return None
            if n <= a <= n + len(s):
                return t, a - n
            n += len(s)
    return None


def _pick(s):
    """형광펜을 칠할 두 줄 → (LETTER, LEAD). 둘 다 글 문단 머리(괄호 줄 · 번호형 · 값 칸 아님)이고, 레터 자리가 글만 든 hp:t 안에 있다."""
    ov, doc = s.outline, s.doc
    letter = lead = None
    order = M._order(doc)
    for pid in sorted(ov["lines"], key=lambda q: order.get(q, 1 << 30)):
        x = ov["lines"][pid]
        sl = OE._slot(ov, x["tpl"], x["level"]) or {}
        rep = sl.get("rep")
        if not rep or rep == pid or rep not in ov["lines"] or x.get("role") in OE.ROOTED or x.get("role") == OE.TABLE or OE.is_numbered(x.get("key") or ""):
            continue
        try:
            if M.lone_value(doc, ov, pid) or M.lone_value(doc, ov, rep):
                continue
            l0, t0, g0, _, _ = M.parts(doc, ov, rep)
            l1, t1, g1, _, text = M.parts(doc, ov, pid)
        except (KeyError, ValueError):
            continue
        if not t1 or not text[len(l1) + len(t1) + len(g1):].strip() or _plain_text_t(doc, pid, len(l1)) is None or doc.own_marks(doc._ids[pid]):
            continue
        if letter is None and t1 != t0 and l1.strip() == "" and g1 == g0:
            letter = pid
        elif lead is None and t1 == t0 and l1 != l0 and l1.strip() == "" and l0.strip() == "" and g1 == g0 and (letter is None or ov["lines"][letter]["tpl"] != x["tpl"]):
            lead = pid
        if letter and lead:
            return letter, lead
    raise AssertionError(f"형광펜을 칠할 줄을 못 찾았습니다 — LETTER {letter} · LEAD {lead}")


def _highlight(doc, pid, a):
    """문단 pid 의 글 자리 a(레터 첫 글자)부터 끝까지 형광펜을 칠한다(markpenBegin 을 그 자리의 hp:t 안에 · markpenEnd 를 마지막 hp:t 끝에)."""
    t, k = _plain_text_t(doc, pid, a)
    s = t.text or ""
    b = etree.Element(_p("markpenBegin"))
    b.set("color", "#FFFF00")
    t.text, b.tail = s[:k], s[k:]
    t.insert(0, b)
    last = [t for r in doc._ids[pid].iterchildren(RUN) for t in r.iterchildren(T)][-1]
    etree.SubElement(last, _p("markpenEnd"))
    doc._touch(doc._ids[pid])


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """(c, d, s, marked, LETTER, LEAD) — 양식에서 두 줄을 고르고 형광펜을 칠한 바이트를 올린 세션. 글 · 글자 모양은 그대로(표지는 길이 0)라 헤딩 그래프는 양식과 같다."""
    tmp = tmp_path_factory.mktemp("outline_marks_apply")
    with pytest.MonkeyPatch.context() as mp:
        for k, v in _env_of(tmp).items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        _, s0 = _open(c, PLAN.read_bytes(), PLAN.name)
        letter, lead = _pick(s0)
        doc = HwpxDoc(PLAN.read_bytes())
        doc.blocks()
        for pid in (letter, lead):
            assert doc._text(doc._ids[pid]) == s0.doc._text(s0.doc._ids[pid])
            _highlight(doc, pid, len(M.parts(s0.doc, s0.outline, pid)[0]))   # 레터부터 끝까지 — 실물의 (2,20)(2,18)(2,19) 와 같은 꼴(레터 앞 빈칸 뒤부터)
        marked = doc.save()
        server.DOCS.clear()
        d, s = _open(c, marked, "형광펜_양식.hwpx")
        for pid in (letter, lead):
            assert (s.outline["lines"][pid]["tpl"], s.outline["lines"][pid]["level"]) == (s0.outline["lines"][pid]["tpl"], s0.outline["lines"][pid]["level"])
        yield c, d, s, marked, letter, lead
        server.DOCS.clear()


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch, request):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    monkeypatch.delenv("NFM_TPL_AGENT_MODEL", raising=False)
    monkeypatch.setattr(M, "merge_hints", lambda ov: [])   # 종속 제안은 이 시험이 보지 않는다(tests/test_outline_safety.py)
    R._MEMORY.clear()
    G._MEMORY.clear()
    A._MEMORY.clear()
    if "world" in request.fixturenames:   # 받아 둔 계획은 시험마다 비운다(모듈 세션을 이어 쓴다)
        from app import tpl_agent_api as TA
        s = request.getfixturevalue("world")[2]
        with TA._plans_lock:
            s.tpl_plans = {"graph": None, "plans": {}}
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()
    A._MEMORY.clear()


def _undo_all(c, d, s, marked):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == marked


def _fmt(c, d):
    return next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")["llm"]


def _at(s, pid):
    x = s.outline["lines"][pid]
    return x["tpl"], int(x["level"])


def _gids(s, tid, lv, pid):
    """계획 자료(tpl_agent.material)에서 그 레벨의 대표 갈래 id 와 줄 pid 가 든 갈래 id."""
    mat = A.material(s.doc, s.outline, tid)
    L = next(x for x in mat["levels"] if x["level"] == lv)
    key = next(g["key"] for g in M.variants(s.doc, s.outline, tid, lv, full=True)["groups"] if pid in g["paras"])
    return next(g["id"] for g in L["groups"] if g["rep"]), next(g["id"] for g in L["groups"] if g["para"] == key)


def _plan(c, d, s, monkeypatch, pids):
    """줄들이 든 갈래를 대표에 맞추는 계획을 템플릿마다 받는다(가짜 답) → {템플릿 id: 계획 답}."""
    want = {}
    for pid in pids:
        tid, lv = _at(s, pid)
        rep, gid = _gids(s, tid, lv, pid)
        lvs = want.setdefault(tid, {})
        lvs.setdefault(lv, {"level": lv, "rep": rep, "match": [], "keep": [], "split": [], "why": ""})["match"].append(gid)
    out = {}
    for tid, lvs in want.items():
        answer = {"summary": f"T{tid}", "levels": list(lvs.values())}
        monkeypatch.setattr(llm, "call", lambda schema, content, what, answer=answer, **kw: {"data": answer, "backend": "api", "ms": 3, "costUsd": 0.0, "error": None,
                                                                                           "model": kw.get("model"), "effort": kw.get("effort")})
        r = c.post(f"/api/docs/{d}/outline/agent/{tid}/plan", json={"skill": "tidy"})
        assert r.status_code == 200, r.text
        out[tid] = r.json()
    return out


def test_marked_lines_have_marks_and_differ_from_their_rep(world):
    c, d, s, _, letter, lead = world
    for pid in (letter, lead):
        assert [m["kind"] for m in s.doc.own_marks(s.doc._ids[pid])] == ["markpen", "markpen"] and s.doc.mark_names(s.doc._ids[pid]) == ["형광펜"]
    rep = lambda pid: OE._slot(s.outline, *_at(s, pid))["rep"]  # noqa: E731
    assert M.parts(s.doc, s.outline, letter)[1] != M.parts(s.doc, s.outline, rep(letter))[1]                              # 레터가 다르다
    assert M.parts(s.doc, s.outline, lead)[1:3] == M.parts(s.doc, s.outline, rep(lead))[1:3]                               # 레터 · 레터 뒤 빈칸은 같고
    assert M.parts(s.doc, s.outline, lead)[0] != M.parts(s.doc, s.outline, rep(lead))[0]                                   # 레터 앞 빈칸만 다르다


def test_apply_all_keeps_going_past_marked_lines(world, monkeypatch):
    """「모두 반영」 — 형광펜 든 줄 때문에 400 이 아니다: 레터를 바꿔야 하는 줄은 모양만 맞추고 남기고(left · 오버레이 agentLeft), 같은 갈래의 다른 줄과
    레터 앞 빈칸만 다른 형광펜 줄은 완전히 맞춘다. 분석 상태는 남긴 줄을 「표지 때문에 모양만 맞춘 줄」 로 세고, 실행 취소 한 번이면 그 표도 사라진다. 계획은 「반영함」 그대로."""
    c, d, s, marked, letter, lead = world
    tl, ll = _at(s, letter)
    tp, lp = _at(s, lead)
    rep_l, rep_p = OE._slot(s.outline, tl, ll)["rep"], OE._slot(s.outline, tp, lp)["rep"]
    tok_l, lead_p = M.parts(s.doc, s.outline, rep_l)[1], M.parts(s.doc, s.outline, rep_p)[0]
    mates = [p for g in M.variants(s.doc, s.outline, tl, ll, full=True)["groups"] if letter in g["paras"] for p in g["paras"] if p != letter]   # 형광펜이 없는 같은 갈래의 줄
    text0 = s.doc._text(s.doc._ids[letter])
    _plan(c, d, s, monkeypatch, [letter, lead])
    f0 = _fmt(c, d)
    seen = {x["tpl"]: x["at"] for x in f0["list"] if x["state"] == "planned"}
    assert set(seen) == {tl, tp} and "marked" not in f0["left"] and f0["leftMarked"] == []
    undo = s.state()["undo"]
    r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"rev": s.rev, "plans": seen})
    assert r.status_code == 200, r.text
    j = r.json()
    assert s.state()["undo"] == undo + 1 and j["plans"] == 2
    no_l = s.outline["templates"][tl]["no"]
    assert j["left"] == [{"id": letter, "tpl": tl, "no": no_l, "level": ll, "why": "letter", "kinds": ["형광펜"]}]
    by = {t["tpl"]: t for t in j["templates"]}
    lv_l = next(x for x in by[tl]["levels"] if x["level"] == ll)
    assert (by[tl]["left"], lv_l["left"], lv_l["changed"]) == (1, 1, len(mates))                               # 레벨 · 템플릿의 changed = 완전히 맞춘 줄만
    assert by[tp]["left"] == 0 and "left" not in next(x for x in by[tp]["levels"] if x["level"] == lp)
    assert {letter, lead, *mates} <= set(j["changed"])                                                          # 모양만 맞춘 줄도 바뀐 줄(문단 모양)
    # 문서: 남긴 줄은 글 · 형광펜 그대로 · 같은 갈래의 다른 줄은 대표 레터로 · 레터 앞 빈칸만 다르던 형광펜 줄은 빈칸만 바뀌고 형광펜은 남는다
    text1 = s.doc._text(s.doc._ids[letter])   # 레터 · 레터 앞 빈칸 · 본문 그대로(레터 뒤 빈칸은 묶음 빈칸이 될 수 있다 — 자리 맞춤은 표지를 지키며 돈다)
    assert text1.replace(NB, " ") == text0 and M.parts(s.doc, s.outline, letter)[1] != tok_l and len(s.doc.own_marks(s.doc._ids[letter])) == 2
    assert all(M.parts(s.doc, s.outline, p)[1] == tok_l for p in mates)
    assert M.parts(s.doc, s.outline, lead)[0] == lead_p and len(s.doc.own_marks(s.doc._ids[lead])) == 2
    assert s.outline["agentLeft"] == {tl: [{"id": letter, "level": ll, "why": "letter"}]}                    # 반영과 같은 트랜잭션에 · 남긴 줄이 없는 템플릿은 키가 없다
    # 분석 상태 — 계획은 「반영함」 그대로 · 남긴 줄을 따로 센다
    f = _fmt(c, d)
    row = next(x for x in f["list"] if x["tpl"] == tl)
    assert row["state"] == "applied" and row["left"]["marked"] == 1 and f["left"]["marked"] == 1 and f["leftMarked"] == [letter]
    assert "표지 때문에 모양만 맞춘 줄 1" in f["text"]
    plans = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]
    assert plans[tl]["state"] == "applied" and plans[tl]["applied"]["changed"] == by[tl]["changed"]
    rec = c.get(f"/api/docs/{d}/headings/llm-changes").json()["applies"][-1]   # 반영 기록에도 남긴 수
    assert next(t for t in rec["templates"] if t["tpl"] == tl)["left"] == 1
    # 실행 취소 — 표도 남긴 줄의 수도 함께 사라진다(계획은 다시 쓸 수 있는 「받음」)
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    back = _fmt(c, d)
    assert "agentLeft" not in s.outline and "marked" not in back["left"] and back["leftMarked"] == []
    assert c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"][tl]["state"] == "planned"
    _undo_all(c, d, s, marked)


def test_level_match_reports_the_line_it_left(world):
    """대표에 맞추기(슬롯) — 레터를 바꿔야 하는 형광펜 줄은 모양만 맞추고 답의 left 로(400 이 아니다)."""
    c, d, s, marked, letter, _ = world
    tl, ll = _at(s, letter)
    r = c.post(f"/api/docs/{d}/outline/slots/{tl}/{ll}/match", json={"like": letter})
    assert r.status_code == 200, r.text
    j = r.json()
    assert [(x["id"], x["why"], x["kinds"], x["tpl"], x["level"]) for x in j["left"]] == [(letter, "letter", ["형광펜"], tl, ll)] and letter in j["changed"]
    assert len(s.doc.own_marks(s.doc._ids[letter])) == 2
    _undo_all(c, d, s, marked)


def test_template_match_without_marks_has_empty_left(world):
    """표지가 없는 템플릿을 맞추면 left 는 빈 목록 · 레벨의 changed 는 전처럼(left 키 없음)."""
    c, d, s, marked, letter, lead = world
    busy = {_at(s, letter)[0], _at(s, lead)[0]}
    tid = next((t for t, lvs in M.all_variants(s.doc, s.outline).items() if t not in busy and any(v.get("others") for v in lvs.values())), None)
    if tid is None:
        pytest.skip("표지 없이 맞출 템플릿이 없다")
    r = c.post(f"/api/docs/{d}/outline/templates/{tid}/match", json={"place": False})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["left"] == [] and all("left" not in x for x in j["levels"]) and j["changed"]
    _undo_all(c, d, s, marked)


def test_failed_transaction_restores_the_overlay(world, monkeypatch):
    """편집 트랜잭션이 ValueError 로 끝나면 문서를 안 건드렸어도 오버레이는 시작 때 것으로(② §8-8 「실패 뒤 오버레이」) — 전에는 대표 바꿈이 남았다."""
    c, d, s, marked, _, lead = world
    tp, lp = _at(s, lead)
    was = OE._slot(s.outline, tp, lp)["rep"]
    real = M.set_rep

    def boom(*a, **kw):
        real(*a, **kw)   # 대표를 바꾼 **뒤에** 실패한다
        raise ValueError("시험 — 대표를 바꾼 뒤 실패")
    monkeypatch.setattr(M, "set_rep", boom)
    s.doc.blocks()   # 문서는 그대로(블록 캐시가 있다) — 전에는 이때 오버레이를 되돌리지 않았다
    assert s.doc._blocks_cache is not None
    undo = s.state()["undo"]
    r = c.put(f"/api/docs/{d}/outline/slots/{tp}/{lp}/rep", json={"para": lead})
    assert r.status_code == 400 and "시험" in r.json()["detail"]
    assert OE._slot(s.outline, tp, lp)["rep"] == was != lead and s.state()["undo"] == undo
    assert c.get(f"/api/docs/{d}/download").content == marked
