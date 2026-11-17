"""서식 맞추기 · 서식 정리 계획의 안전 검사(2026-11-16 「세 층 · 전체 실행 검토」 — spec_헤딩_추출 ② §6 「값 칸」 · spec_hwpx_웹편집 ② §8-2 「값 칸」·「줄 맞춤 값」·「계획의 대표로」 · §8-4 「계획 검사」·「계획 모두 반영」).
실제 문서에서 틀린 결과가 난 것(표 칸의 혼자 있는 「-」 가 글머리 서식으로 · 자간으로 한 줄에 맞춘 줄이 넘침)과 astra 가 코드로 짚은 것(계획의 대표 · 사람이 정한 대표 · 못 본 갈래 · 본 것과 다른 계획)의
부정 시험 — 연구개발계획서 양식 + 2단계(LLM 끔 · 에이전트 답은 가짜)."""
import copy
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import analysis
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, llm, server
from app import outline_match as M
from app import tpl_agent as A

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
LONE = "p7384"   # 표 t7265(참여연구자 현황) 12열의 「-」 — 칸에 그 글 하나뿐(빈 값)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    monkeypatch.delenv("NFM_TPL_AGENT_MODEL", raising=False)
    for m in (R, G, A):
        m._MEMORY.clear()
    yield
    for m in (R, G, A):
        m._MEMORY.clear()


def _open(tmp, old_graph=False):
    """양식을 올리고 1·2단계(스크립트) → (client, doc id, session). old_graph = 값 칸 규칙이 없던 때의 헤딩 그래프를 흉내 낸다(이미 저장된 그래프 — 값 칸이 개요 줄로 들어 있다)."""
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
                     "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}.items():
            mp.setenv(k, str(v))
        if old_graph:
            mp.setattr(HG, "value_cell", lambda rec, filled: False)
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        assert c.get(f"/api/docs/{d}/outline").status_code == 200  # 오버레이를 만든다
        return c, d, s


@pytest.fixture(scope="module")
def sess(tmp_path_factory):
    server.DOCS.clear()
    yield _open(tmp_path_factory.mktemp("safety"))
    server.DOCS.clear()


@pytest.fixture(scope="module")
def old(tmp_path_factory):
    """값 칸이 개요 줄로 든 옛 헤딩 그래프의 작업 — 이미 저장된 그래프도 맞추기에서 지켜지는지."""
    return _open(tmp_path_factory.mktemp("safety_old"), old_graph=True)


def _slots(c, d):
    return c.get(f"/api/docs/{d}/outline/formats").json()["slots"]


@pytest.fixture(autouse=True)
def _fresh_plans(request):
    """받아 둔 서식 계획은 그 템플릿 줄의 지문에 묶여, 반영을 되돌리면 다시 쓸 수 있는 계획으로 살아난다 — 모듈 세션을 이어 쓰는 시험끼리 섞이지 않게 시험마다 비운다."""
    for name in ("sess", "old"):
        if name in request.fixturenames:
            from app import tpl_agent_api as TA
            s = request.getfixturevalue(name)[2]
            with TA._plans_lock:
                s.tpl_plans = {"graph": None, "plans": {}, "applies": []}
    yield


def _undo_all(c, d, s):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


# ---------------------------------------------------------------- 값 칸
def test_value_cells_are_not_heading_candidates(sess):
    """표 칸에 혼자 있는 제목 없는 레터(빈 값 「-」 · 번호 칸 「1.」)는 헤딩 후보가 아니다 — 같은 칸에 다른 글이 있는 쓸 자리(「ㅇ 」 여러 줄)는 그대로 후보."""
    _, _, s = sess
    s1 = heading_runs.state(s)["stage1"]
    filled = HG.filled_flows(s1["paras"])
    vals = [r for r in s1["paras"] if HG.value_cell(r, filled)]
    by = Counter("N." if r["letter"][:1].isdigit() else r["letter"] for r in vals)
    assert LONE in {r["id"] for r in vals} and by["-"] >= 70 and by["N."] >= 10 and set(by) == {"-", "N."}
    cand = {n["id"] for n in HG.candidates(s1)}
    assert not cand & {r["id"] for r in vals}
    assert {"p684", "p686"} <= cand   # 표 칸의 쓸 자리 「ㅇ 」 — 같은 칸에 여러 줄: 값 칸이 아니다
    assert LONE not in s.outline["lines"] and not any(v.get("values") for lvs in _slots(*sess[:2]).values() for v in lvs.values())


def test_value_cells_in_an_old_graph_are_not_grouped_or_matched(old):
    """이미 저장된 헤딩 그래프에는 값 칸이 개요 줄로 들어 있다 — 서식 갈래에 넣지 않고, 「대표에 맞추기」·「템플릿 맞추기」·서식 정리 계획이 건드리지 않는다(가운데 「-」 가 왼쪽 「- 」 가 되던 것)."""
    c, d, s = old
    x = s.outline["lines"][LONE]
    tid, lv = x["tpl"], int(x["level"])
    assert M.lone_value(s.doc, s.outline, LONE)
    vals = [p for p in M.slot_ids(s.outline, tid, lv) if M.lone_value(s.doc, s.outline, p)]
    v = _slots(c, d)[tid][str(lv)]
    assert v["values"] == len(vals) >= 1 and not any(set(g["paras"]) & set(vals) for g in v["groups"]) and v["total"] == len(M.slot_ids(s.outline, tid, lv)) - len(vals)
    before = {p: s.texts[p] for p in vals}
    looks = {p: M.look(s.doc, s.outline, p) for p in vals}
    r = c.post(f"/api/docs/{d}/outline/templates/{tid}/match", json={"place": False})   # 템플릿 맞추기(모든 레벨 · 대표와 다른 줄 모두)
    assert r.status_code in (200, 409), r.text   # 409 = 맞출 줄이 없음(값 칸뿐인 템플릿)
    changed = set(r.json().get("changed") or [])
    assert not changed & set(vals) and {p: s.texts[p] for p in vals} == before and {p: M.look(s.doc, s.outline, p) for p in vals} == looks
    # 옛 계획이 값 칸의 갈래를 가리켜도(likes = 그 줄) 맞추지 않는다
    rep = s.outline["templates"][tid]["slots"][str(lv)].get("rep")
    if rep and rep not in vals:
        assert M.match_set(s.doc, s.outline, tid, lv, None, [LONE])[1] == []
    assert M.split_targets(s.doc, s.outline, tid, lv, [LONE]) == []
    # 값 칸뿐인 레벨은 에이전트 자료에 없다
    mat = A.material(s.doc, s.outline, tid)
    assert all(lvl["lines"] > 0 for lvl in mat["levels"]) and all(LONE not in {g["para"] for g in lvl["groups"]} for lvl in mat["levels"])
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")


def test_value_cell_rep_of_an_old_graph_is_never_the_matching_base(old):
    """옛 그래프는 값 칸을 대표로 잡은 레벨이 있다(「-」 79칸 + 글 줄 3 → 대표 = 「-」 칸). 그 모양(가운데 「-」)으로 글 줄을 맞추지 않는다 — 대표를 글 줄로 정한 뒤에만 맞춘다."""
    c, d, s = old
    x = s.outline["lines"][LONE]
    tid, lv = x["tpl"], int(x["level"])
    sl = s.outline["templates"][tid]["slots"][str(lv)]
    assert M.lone_value(s.doc, s.outline, sl["rep"])                               # 이 레벨의 대표가 값 칸이다
    v = _slots(c, d)[tid][str(lv)]
    assert v["rep"] is None and v["repMissing"] and v["total"] >= 2                # 화면에는 「대표 없음」 — 글 줄 가운데서 고르게
    text = [p for g in v["groups"] for p in g["paras"]]
    before = {p: (s.texts[p], M.look(s.doc, s.outline, p)) for p in text}
    r = c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={"place": False})
    assert r.status_code == 400 and "값 칸" in r.json()["detail"]
    assert c.post(f"/api/docs/{d}/outline/templates/{tid}/match", json={"place": False}).status_code in (200, 409)   # 「모든 레벨」 은 그 레벨을 건너뛴다
    assert {p: (s.texts[p], M.look(s.doc, s.outline, p)) for p in text} == before
    assert c.put(f"/api/docs/{d}/outline/slots/{tid}/{lv}/rep", json={"para": LONE}).status_code == 400   # 값 칸은 대표가 될 수 없다
    assert c.put(f"/api/docs/{d}/outline/slots/{tid}/{lv}/rep", json={"para": text[0]}).status_code == 200
    r = c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={"place": False})
    assert r.status_code in (200, 409) and not set(r.json().get("changed") or []) - set(text)          # 글 줄끼리만
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")


def test_lone_value_needs_a_multi_cell_table_and_no_other_text(sess):
    _, _, s = sess
    ov = s.outline
    body = next(p for p, x in ov["lines"].items() if M._cell_of(s.doc._ids[p]) is None)
    assert not M.lone_value(s.doc, ov, body)                      # 본문 줄
    assert not M.lone_value(s.doc, ov, "p684")                    # 칸에 다른 글이 있다(쓸 자리 여러 줄)
    assert not M.lone_value(s.doc, {"lines": {}}, LONE)           # 개요 줄이 아니면 물을 것이 없다
    fake = {"lines": {LONE: {"letter": "-", "key": "-", "tpl": "x", "level": 1}}}
    assert M.lone_value(s.doc, fake, LONE)                        # 개요 줄로 들어 있었다면 값 칸
    assert not M.lone_value(s.doc, {"lines": {LONE: {**fake["lines"][LONE], "role": next(iter(M.OE.ROOTED))}}}, LONE)   # 괄호 줄(구분 라벨)은 값이 아니다


# ---------------------------------------------------------------- 줄 맞춤 값(장평·자간)
def _tighten(s, pid, pct):
    """그 문단의 글 런을 자간 pct 인 글자 모양으로(한 줄에 넣으려고 자간을 줄인 줄을 흉내 낸다) — 시험이 문서를 직접 고친다."""
    p = s.doc._ids[pid]
    made = {}
    for r in p.iterchildren(M.RUN):
        old = r.get("charPrIDRef")
        if old not in made:
            cp = copy.deepcopy(s.doc._defs["charPr"][old])
            s.doc._set_chars(cp, {"spacingPct": pct})
            made[old] = s.doc._add_def("charPr", cp)
        r.set("charPrIDRef", made[old])
    s.doc._drop_cache(p)


def test_fit_keys_do_not_split_groups_and_survive_match(tmp_path):
    """자간·장평은 갈래를 가르지 않고(자간만 다른 줄 = 같은 갈래 — 맞출 줄이 아니다), 다른 값이 달라 맞추는 줄도 제 자간을 지킨다(대표의 0% 가 되어 줄이 넘치던 것)."""
    c, d, s = _open(tmp_path)
    try:
        assert "spacingPct" not in M.KEYS and "L.ratioPct" not in M.KEYS and set(M.FIT_KEYS) == {"ratioPct", "spacingPct"}
        v = _slots(c, d)["1"]["5"]   # T1 L5 「-」 — 대표 p5209 ×9 · 「   - 」 p6502 ×5 · 「    -」 p5765(2026-11-17 「잇닿은 사슬」 전에는 가지 T3 L2)
        assert [g["count"] for g in v["groups"]] == [9, 5, 1] and v["rep"] == "p5209"
        peer = next(p for p in v["groups"][0]["paras"] if p != "p5209")
        _tighten(s, peer, -10)      # 대표와 값이 같은 줄 — 자간만 줄임
        _tighten(s, "p6502", -7)    # 레터 앞 빈칸이 다른 줄 — 자간도 줄임
        v = _slots(c, d)["1"]["5"]
        assert [g["count"] for g in v["groups"]] == [9, 5, 1] and peer in v["groups"][0]["paras"] and v["others"] == 6   # 자간만 다른 줄은 제 갈래 그대로
        assert M.look(s.doc, s.outline, peer)["spacingPct"] == -10 and M.same(M.look(s.doc, s.outline, peer), M.look(s.doc, s.outline, "p5209"))
        assert all(x[0] not in ("spacingPct", "L.spacingPct") for g in v["groups"] for x in g["diff"])
        five = next(g for g in v["groups"] if "p6502" in g["paras"])["paras"]
        r = c.post(f"/api/docs/{d}/outline/slots/1/5/match", json={"place": False})
        assert r.status_code == 200, r.text
        assert sorted(r.json()["changed"]) == sorted(five + ["p5765"])   # 자간만 다른 줄(peer)은 건드리지 않는다
        got, rep = M.look(s.doc, s.outline, "p6502"), M.look(s.doc, s.outline, "p5209")
        assert M.same(got, rep) and got["lead"] == rep["lead"]                       # 비교 값은 대표와 같아졌다
        assert got["spacingPct"] == -7 and got["L.spacingPct"] == -7 and rep["spacingPct"] == 0   # 줄 맞춤 값은 그 줄 것
        assert M.look(s.doc, s.outline, peer)["spacingPct"] == -10
        assert len(_slots(c, d)["1"]["5"]["groups"]) == 1
    finally:
        server.DOCS.pop(d, None)


def _fit_run(s, pid, start, end, attrs):
    """그 문단의 글 start..end 를 장평·자간이 attrs({"spacing": {언어: 값}} · {"ratio": …})인 글자 모양으로 — 런마다 · 언어마다 다른 줄 맞춤 값을 흉내 낸다."""
    p = s.doc._ids[pid]
    s.doc._boundary(p, end)
    s.doc._boundary(p, start)
    pos = 0
    for r in p.iterchildren(M.RUN):
        k = sum(s.doc._clen(x) for x in r)
        if k and start <= pos and pos + k <= end:
            cp = copy.deepcopy(s.doc._defs["charPr"][r.get("charPrIDRef")])
            s.doc._set_chars(cp, {"ratioPct": 100, "spacingPct": 0})
            for tag, vals in attrs.items():
                for lang, val in vals.items():
                    cp.find(M._h(tag)).set(lang, str(val))
            r.set("charPrIDRef", s.doc._add_def("charPr", cp))
        pos += k
    s.doc._drop_cache(p)


def _fits(s, pid):
    """그 문단의 글 런마다 (글, 한글 자간, 영문 자간) — 차례로."""
    p, out = s.doc._ids[pid], []
    for r in p.iterchildren(M.RUN):
        text = "".join(x.text or "" for x in r if x.tag == M.RUN.replace("run", "t"))
        if text:
            sp = dict(M._fit_of(s.doc, r.get("charPrIDRef"))[1])
            out.append((text, sp["hangul"], sp["latin"]))
    return out


def test_match_keeps_fit_per_language_and_per_run(tmp_path):
    """맞춰도 줄 맞춤 값은 **언어마다 · 런마다** 그 줄 것이다 — 한글 −10 · 영문 0 인 줄이 영문까지 −10 이 되거나(한글 값만 읽어 모든 언어에 덮음),
    접두 교체가 글자 모양을 같이 쓰던 뒤쪽 런의 자간을 레터 것으로 바꾸지 않는다(astra 2026-11-16 결과 검토)."""
    c, d, s = _open(tmp_path)
    try:
        tid, lv, pid, rep = next((t, int(lvl), g["paras"][0], v["rep"]) for t, lvs in _slots(c, d).items() for lvl, v in lvs.items() if v["rep"]   # 대표와 다른 갈래의, 본문 글이 있는 줄
                                 for g in v["groups"] if not g["rep"] and len(s.texts[g["paras"][0]]) - M.parts(s.doc, s.outline, g["paras"][0])[3] >= 8
                                 and not M.OE.is_numbered(s.outline["lines"][g["paras"][0]].get("key") or ""))
        lead, tok, gap, plen, text = M.parts(s.doc, s.outline, pid)
        n = len(text)
        mid = plen + (n - plen) // 2
        _fit_run(s, pid, 0, plen, {"spacing": {"hangul": -10, "latin": 0}})        # 접두(앞 공백 · 레터 · 뒤 공백): 한글 −10 · 영문 0
        _fit_run(s, pid, plen, mid, {"spacing": {"hangul": -5, "latin": -5}})      # 본문 앞쪽: −5
        _fit_run(s, pid, mid, n, {"spacing": {"hangul": -7, "latin": 3}})          # 본문 뒤쪽: 한글 −7 · 영문 3
        assert c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={"place": False, "paras": [pid]}).status_code == 200
        assert M.same(M.look(s.doc, s.outline, pid), M.look(s.doc, s.outline, rep))
        lead2, tok2, gap2, plen2, text2 = M.parts(s.doc, s.outline, pid)
        assert text2[plen2:] == text[plen:]                                          # 본문 글은 그대로
        got, pos = [], 0
        for run_text, han, lat in _fits(s, pid):
            got.append((pos, pos + len(run_text), han, lat))
            pos += len(run_text)
        mid2 = plen2 + (mid - plen)
        at = lambda i: next((h, la) for a, b, h, la in got if a <= i < b)  # noqa: E731
        assert at(plen2 - len(gap2) - 1) == ("-10", "0")                             # 레터: 한글 −10 · 영문 0 그대로(영문까지 −10 이 되지 않는다)
        assert at(plen2) == ("-5", "-5") and at(mid2 - 1) == ("-5", "-5")            # 본문 앞쪽
        assert at(mid2) == ("-7", "3") and at(len(text2) - 1) == ("-7", "3")         # 본문 뒤쪽 — 런마다 제 값
    finally:
        server.DOCS.pop(d, None)


def test_plan_uses_the_actual_rep_line_not_the_first_line_of_its_group(sess):
    """사람이 정한 대표가 그 갈래의 첫 줄이 아니어도 계획은 **그 줄**을 대표로 든다 — 전에는 갈래의 첫 줄로 바꿔 넣어, 반영하면 대표 줄이 바뀌었다."""
    c, d, s = sess
    v = _slots(c, d)["1"]["5"]                                                       # T1 L5 「-」 — 대표 갈래 ×9
    other = next(p for p in v["groups"][0]["paras"] if p != v["rep"])              # 대표 갈래의 다른 줄
    assert v["groups"][0]["paras"][0] == v["rep"] != other
    assert c.put(f"/api/docs/{d}/outline/slots/1/5/rep", json={"para": other}).status_code == 200
    v = _slots(c, d)["1"]["5"]
    assert v["rep"] == other and v["groups"][0]["key"] == other and v["groups"][0]["paras"][0] != other   # 열쇠 줄 = 대표 줄(갈래의 첫 줄이 아니다)
    mat = A.material(s.doc, s.outline, "1")
    lv = next(x for x in mat["levels"] if x["level"] == 5)
    assert lv["repSet"] and lv["groups"][0]["rep"] and lv["groups"][0]["para"] == other
    plan = A.check_plan(mat, {"summary": "", "levels": [{"level": 5, "rep": "g1", "match": ["g2", "g3"], "keep": [], "split": [], "why": ""}]})
    todo = A.todo(plan)
    assert next(x for x in todo["levels"] if x["level"] == 5)["rep"] == other and not next(x for x in plan["levels"] if x["level"] == 5)["rep"]["changed"]
    _undo_all(c, d, s)


def test_keep_fit_returns_the_rep_shape_when_fit_is_the_same(sess):
    _, _, s = sess
    cid = s.doc._ids["p6502"].find(M.RUN).get("charPrIDRef")
    assert M.keep_fit(s.doc, cid, cid) == cid and M.keep_fit(s.doc, cid, None) == cid and M.keep_fit(s.doc, cid, "no-such") == cid


# ---------------------------------------------------------------- 계획의 대표로(윗레벨 떼기가 아랫레벨 대표 줄을 데려갈 때)
def test_lower_level_is_matched_to_the_planned_rep_even_when_an_upper_split_moves_it(sess):
    """T4 L2 의 갈래 p6341 을 떼면 그 아래 L3 줄 p6342 가 새 템플릿으로 간다. L3 대표가 p6342 인 계획에서 L3 의 다른 갈래(p1604 …)는 **p6342 의 모양**으로 맞아야 한다 —
    전에는 떼기가 슬롯 대표를 남은 첫 줄(p1604)로 바꾼 뒤 그 줄 모양으로 맞춰(= 안 바뀜) 계획과 달랐다."""
    c, d, s = sess
    ov = s.outline
    assert ov["lines"]["p6342"]["tpl"] == "4" and int(ov["lines"]["p6342"]["level"]) == 3 and int(ov["lines"]["p6341"]["level"]) == 2
    want = M.look(s.doc, ov, "p6342")
    assert not M.same(M.look(s.doc, ov, "p1604"), want)
    assert c.put(f"/api/docs/{d}/outline/slots/4/3/rep", json={"para": "p6342"}).status_code == 200
    r = c.post(f"/api/docs/{d}/outline/templates/4/match", json={"place": False, "levels": [{"level": 2, "likes": [], "splits": [{"likes": ["p6341"]}]}, {"level": 3, "likes": ["p1604"]}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert s.outline["lines"]["p6342"]["tpl"] != "4" and "p1604" in j["changed"]            # 대표 줄은 새 템플릿으로 갔고, 남은 갈래는 바뀌었다
    assert M.same(M.look(s.doc, s.outline, "p1604"), want)                                  # 계획한 대표(p6342)의 모양으로
    sl = s.outline["templates"]["4"]["slots"]["3"]
    assert s.outline["lines"][sl["rep"]]["tpl"] == "4" and M.same(M.look(s.doc, s.outline, sl["rep"]), want)   # 남은 줄 가운데 그 모양인 줄이 대표
    _undo_all(c, d, s)


def test_lower_split_whose_lines_an_upper_split_took_sets_that_templates_rep(sess):
    """2026-11-18 사용자 「모두 반영」 400 「그 문단은 T17 L2 줄이 아닙니다(지금 T17L1a L2)」 — 계획이 L1 에서 표 하나의 「①」 을 떼고(그 아래 「-」 가 함께 감) L2 에서 그 「-」 를 또 뗐다.
    윗레벨 떼기가 먼저 데려간 갈래는 새 템플릿을 또 만들지 않고 **데려간 템플릿의 그 레벨**에서 그 서식을 대표로 삼는다(뗀 줄 맞추기도 그 대표 모양으로 — 문서를 고치는 길)."""
    c, d, s = sess
    ov = s.outline
    took = M.split_targets(s.doc, ov, "4", 2, ["p6194"])                                   # T4 L2 의 큰 갈래(17줄) — 그 아래 L3 줄 17줄이 함께 간다
    assert "p6341" not in took and {"p1604", "p5772"} <= M._members(ov, "4", took)
    assert c.put(f"/api/docs/{d}/outline/slots/4/2/rep", json={"para": "p6341"}).status_code == 200
    assert c.put(f"/api/docs/{d}/outline/slots/4/3/rep", json={"para": "p6342"}).status_code == 200
    want = M.look(s.doc, ov, "p5772")
    assert not M.same(M.look(s.doc, ov, "p1604"), want)
    r = c.post(f"/api/docs/{d}/outline/templates/4/match", json={"place": False, "levels": [
        {"level": 2, "likes": [], "splits": [{"likes": ["p6194"]}]},
        {"level": 3, "likes": [], "splits": [{"likes": ["p5772", "p1604"], "rep": "p5772"}]}]})                # L3 의 「p5772 갈래 + p1604」 — 모두 윗레벨 떼기가 데려가는 줄
    assert r.status_code == 200, r.text
    j, ov = r.json(), s.outline
    vid = ov["lines"]["p5772"]["tpl"]
    assert vid != "4" and ov["templates"][vid]["variant"]["level"] == 2 and ov["lines"]["p1604"]["tpl"] == vid
    assert [x["level"] for x in j["splits"]] == [2]                                                     # 새로 만든 서식 종속 템플릿은 L2 의 것 하나뿐
    assert not any((t.get("variant") or {}).get("of") == "4" and int(t["variant"]["level"]) == 3 for t in ov["templates"].values())
    assert [(x["level"], x["id"], x["whole"], x["lines"]) for x in j["into"]] == [(3, vid, True, 8)]
    sl = ov["templates"][vid]["slots"]["3"]
    assert sl["rep"] == "p5772" and not sl.get("repSet") and "p1604" in j["changed"]                      # 데려간 템플릿의 L3 대표 = 계획한 떼기의 대표
    assert M.same(M.look(s.doc, ov, "p1604"), want)                                                     # 뗀 줄 맞추기도 그 대표 모양으로
    assert ov["templates"]["4"]["slots"]["3"]["rep"] == "p6342"
    _undo_all(c, d, s)


def test_lower_split_partly_taken_by_an_upper_split(sess):
    """아랫레벨 떼기의 줄 일부만 윗레벨 떼기가 데려간 경우 — 데려간 줄은 그 템플릿의 그 레벨 대표로, 남은 줄은 전처럼 새 서식 종속 템플릿으로(계획한 대표가 떠났으면 남은 줄 가운데 같은 서식의 첫 줄이 대표)."""
    c, d, s = sess
    ov = s.outline
    assert c.put(f"/api/docs/{d}/outline/slots/4/3/rep", json={"para": "p1604"}).status_code == 200
    rest = [p for p in M.split_targets(s.doc, ov, "4", 3, ["p6342"]) if p != "p6342"]
    r = c.post(f"/api/docs/{d}/outline/templates/4/match", json={"place": False, "levels": [
        {"level": 2, "likes": [], "splits": [{"likes": ["p6341"]}]},                                    # p6341 을 떼면 그 아래 p6342 가 함께 간다
        {"level": 3, "likes": [], "splits": [{"likes": ["p6342"]}]}]})                                  # p6342 의 갈래(9줄) — p6342 만 이미 떠났다
    assert r.status_code == 200, r.text
    j, ov = r.json(), s.outline
    up, low = (next(x for x in j["splits"] if x["level"] == lv) for lv in (2, 3))
    assert ov["lines"]["p6342"]["tpl"] == up["id"] and ov["templates"][up["id"]]["slots"]["3"]["rep"] == "p6342"
    assert [(x["level"], x["id"], x["whole"], x["lines"]) for x in j["into"]] == [(3, up["id"], False, 1)]
    assert {p for p in rest if ov["lines"][p]["tpl"] == low["id"]} == set(rest) and ov["templates"][low["id"]]["slots"]["3"]["rep"] == rest[0]
    _undo_all(c, d, s)


def test_planned_rep_taken_by_an_upper_split(sess):
    """같은 문서의 T19(「모두 반영」 400 「T19 L2 의 대표 서식은 뗄 수 없습니다」) — 윗레벨 떼기가 아랫레벨의 **계획한 대표와 그 서식의 줄을 모두** 데려가면:
    ① 계획한 대표는 데려간 템플릿의 그 레벨 대표로 따라가고(맞춘 줄도 그 모양) ② 남은 줄 가운데 떼기로 고른 갈래는 떼지 않고 이 템플릿 그 레벨의 대표가 되며(떼면 대표가 될 줄이 없다)
    ③ 그 떼기 갈래 가운데 데려간 템플릿으로 간 줄은 그 템플릿의 계획한 대표에 져서 다른 서식으로 그대로 남는다."""
    c, d, s = sess
    ov = s.outline
    assert c.put(f"/api/docs/{d}/outline/slots/4/2/rep", json={"para": "p6341"}).status_code == 200
    assert c.put(f"/api/docs/{d}/outline/slots/4/3/rep", json={"para": "p1604"}).status_code == 200      # 계획한 L3 대표 — L2 떼기가 데려가는 줄
    want, mine = M.look(s.doc, ov, "p1604"), M.look(s.doc, ov, "p6342")
    away = [p for p in M.split_targets(s.doc, ov, "4", 3, ["p6342"]) if p != "p6342"]
    r = c.post(f"/api/docs/{d}/outline/templates/4/match", json={"place": False, "levels": [
        {"level": 2, "likes": [], "splits": [{"likes": ["p6194"]}]},
        {"level": 3, "likes": ["p5772"], "splits": [{"likes": ["p6342"]}]}]})
    assert r.status_code == 200, r.text
    j, ov = r.json(), s.outline
    vid = ov["lines"]["p1604"]["tpl"]
    assert vid != "4" and [x["level"] for x in j["splits"]] == [2] and ov["lines"]["p6342"]["tpl"] == "4"
    assert ov["templates"][vid]["slots"]["3"]["rep"] == "p1604" and M.same(M.look(s.doc, ov, "p5772"), want) and "p5772" in j["changed"]   # ①
    assert ov["templates"]["4"]["slots"]["3"]["rep"] == "p6342" and M.same(M.look(s.doc, ov, "p6342"), mine)                                # ②
    assert [(x["id"], bool(x.get("stayed")), bool(x.get("aside")), x["lines"], x["whole"]) for x in j["into"]] == [("4", True, False, 1, True), (vid, False, True, len(away), True)]
    assert all(ov["lines"][p]["tpl"] == vid and p not in j["changed"] for p in away)                                                      # ③
    _undo_all(c, d, s)


# ---------------------------------------------------------------- 계획 검사
def test_check_plan_keeps_the_rep_a_person_chose(sess):
    _, _, s = sess
    mat = A.material(s.doc, s.outline, "1")                                      # T1 L5 「-」 — g1 대표 ×9 · g2 ×5 · g3 ×1
    lv = next(x for x in mat["levels"] if x["level"] == 5)
    data = {"summary": "", "levels": [{"level": 5, "rep": "g2", "match": ["g1", "g3"], "keep": [], "split": [], "why": ""}]}
    free = next(x for x in A.check_plan(mat, data)["levels"] if x["level"] == 5)
    assert free["rep"]["group"] == "g2" and free["rep"]["changed"]            # 사람이 정하지 않은 대표는 답이 바꿀 수 있다
    lv["repSet"] = True
    plan = A.check_plan(mat, data)
    held = next(x for x in plan["levels"] if x["level"] == 5)
    assert held["rep"]["group"] == "g1" and not held["rep"]["changed"] and [m["group"] for m in held["match"]] == ["g3"]
    assert any("사람이 정한" in n for n in plan["notes"]) and [k["group"] for k in held["keep"]] == ["g2"] and held["keep"][0]["auto"]


def test_plan_reports_unseen_groups_and_unanswered_lines(sess, monkeypatch):
    """갈래가 한도를 넘어 못 본 것(omitted) · 답이 말하지 않아 그대로 둔 줄(unanswered)을 계획이 센다 — 못 본 갈래가 있는 계획은 반영해도 「반영함」 으로 닫지 않는다(다시 받을 계획)."""
    _, _, s = sess
    monkeypatch.setattr(A, "GROUP_MAX", 2)
    mat = A.material(s.doc, s.outline, "2")                                      # T2 L1 「□」 — g1 대표 p970 ×3 · g2 p11850 ×3 · g3 p1014 ×1(다른 레벨은 갈래 하나)
    lv = next(x for x in mat["levels"] if x["level"] == 1)
    assert len(lv["groups"]) == 2 and lv["more"] == 1
    plan = A.check_plan(mat, {"summary": "", "levels": [{"level": 1, "rep": "g1", "match": ["g2"], "keep": [], "split": [], "why": ""}]})
    assert plan["omitted"] >= 1 and next(x for x in plan["levels"] if x["level"] == 1)["omitted"] == 1
    none = A.check_plan(mat, {"summary": "", "levels": []})
    assert none["left"]["unanswered"] >= 1 and none["left"]["kept"] == 0 and none["change"] == 0
    kept = A.check_plan(mat, {"summary": "", "levels": [{"level": 1, "rep": "g1", "match": [], "keep": [{"group": "g2", "why": "남김"}], "split": [], "why": ""}]})
    assert kept["left"]["kept"] == 3
    rec = {"tpl": "2", "at": 5.0, "rev": 1, "applied": {"at": 6.0}, "plan": {"omitted": 1}}
    ov = {"agent": {"2": 5.0}}
    assert analysis.plan_state(rec, 2, ov) == "stale"                                             # 반영했지만 못 본 갈래가 남았다
    assert analysis.plan_state({**rec, "plan": {"omitted": 0}}, 2, ov) == "applied" and analysis.plan_state({**rec, "plan": {}}, 2, ov) == "applied"


# ---------------------------------------------------------------- 「모두 반영」 — 화면이 본 계획 그대로
def test_apply_plans_only_the_plan_the_screen_saw(sess, monkeypatch):
    c, d, s = sess
    answer = {"summary": "T2 정리", "levels": [{"level": 1, "rep": "g1", "match": ["g2", "g3"], "keep": [], "split": [], "why": ""}]}   # T2 L1 — p11850 ×3 · p1014 ×1 을 대표에
    monkeypatch.setattr(llm, "call", lambda schema, content, what, **kw: {"data": answer, "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")})
    assert c.post(f"/api/docs/{d}/outline/agent/2/plan", json={"skill": "tidy"}).status_code == 200
    row = lambda: next(x for x in next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")["llm"]["list"] if x["tpl"] == "2")  # noqa: E731
    seen = row()
    assert seen["state"] == "planned" and isinstance(seen["at"], float) and (seen["change"], seen["kept"], seen["unanswered"], seen["omitted"]) == (4, 0, 0, 0)
    url = f"/api/docs/{d}/outline/agent/apply"
    assert c.post(url, json={"place": False, "rev": s.rev, "plans": ["2"]}).status_code == 400 and c.post(url, json={"place": False, "rev": s.rev, "plans": {"2": "x"}}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/agent/2/plan", json={"skill": "tidy"}).status_code == 200   # 그 사이 계획을 다시 받았다(문서 차례는 같다)
    r = c.post(url, json={"place": False, "rev": s.rev, "plans": {"2": seen["at"]}})
    assert r.status_code == 409 and "바뀌었습니다" in r.json()["detail"] and s.state()["undo"] == 0   # 화면이 본 계획이 아니다 — 반영하지 않는다
    assert c.post(url, json={"place": False, "rev": s.rev, "plans": {"999": 1.0}}).status_code == 409
    r = c.post(url, json={"place": False, "rev": s.rev, "plans": {"2": row()["at"]}})
    assert r.status_code == 200 and r.json()["plans"] == 1 and len(r.json()["changed"]) == 4
    _undo_all(c, d, s)


def test_undo_reverts_only_the_result_and_the_plan_is_used_again(sess, monkeypatch):
    """되돌리기는 **조정의 결과만** 되돌린다(2026-11-16 사용자 「되돌려도 … 보강했던 내용들은 되돌릴 필요는 없지」) — 받아 둔 계획은 남고 줄 지문이 같으니 **다시 받지 않고** 그대로 반영한다.
    반영 기록(결과 화면)은 실행마다 남는다: 갈래마다 [이름, 전, 후] 값 · 같은 계획을 되돌렸다가 다시 반영하면 「지금 문서에 남아 있음」 은 마지막 반영만."""
    c, d, s = sess
    answer = {"summary": "T2 정리", "levels": [{"level": 1, "rep": "g1", "match": ["g2", "g3"], "keep": [], "split": [], "why": ""}]}   # T2 L1 — p11850 ×3 · p1014 ×1 을 대표에
    calls = []

    def call(schema, content, what, **kw):
        calls.append(what)
        return {"data": answer, "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", call)
    assert c.post(f"/api/docs/{d}/outline/agent/2/plan", json={"skill": "tidy"}).status_code == 200
    row = lambda: next(x for x in next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")["llm"]["list"] if x["tpl"] == "2")  # noqa: E731
    recs = lambda: c.get(f"/api/docs/{d}/headings/llm-changes").json()["applies"]  # noqa: E731
    url, n, at, graph = f"/api/docs/{d}/outline/agent/apply", len(calls), row()["at"], list(s.outline["run"])
    r = c.post(url, json={"place": False, "rev": s.rev, "relations": False, "plans": {"2": at}})
    assert r.status_code == 200 and len(r.json()["changed"]) == 4 and s.outline["agent"]["2"] == at   # 반영함(다 맞춘 템플릿은 「정리할 템플릿」 목록에서 빠진다 — 표로 본다)
    one = recs()[-1]
    assert (one["by"], one["lines"], one["relations"]) == ("all", 4, []) and [(t["tpl"], t["plan"], t["live"]) for t in one["templates"]] == [("2", at, True)]
    lv = one["templates"][0]["levels"][0]
    assert lv["level"] == 1 and sum(g["count"] for g in lv["match"]) == 4 and lv["keep"] == [] and all(len(x) == 3 and x[1] != x[2] for g in lv["match"] for x in g["diff"])
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    back = row()
    assert (back["state"], back["at"], back["change"]) == ("planned", at, 4) and [t["live"] for t in recs()[-1]["templates"]] == [False]   # 계획은 그대로 · 기록은 「되돌림」
    assert list(s.outline["run"]) == graph and c.get(f"/api/docs/{d}/headings").json()["stage2"] is not None                                                              # 헤딩 그래프(스크립트 · LLM 판정)도 그대로
    r = c.post(url, json={"place": False, "rev": s.rev, "relations": False, "plans": {"2": at}})
    assert r.status_code == 200 and len(r.json()["changed"]) == 4 and len(calls) == n            # LLM 을 다시 부르지 않고 같은 계획으로
    assert [[t["live"] for t in x["templates"]] for x in recs()[-2:]] == [[False], [True]]        # 같은 계획의 기록 둘 — 남아 있는 것은 마지막 반영
    _undo_all(c, d, s)


# ---------------------------------------------------------------- 서식 라벨(여백의 「S41」)은 지금 서식을 따른다
def _odd_label(c, d, s):
    """대표와 서식 라벨이 다른 갈래가 있는 슬롯 하나 → (tid, level, 대표 줄, 그 갈래의 첫 줄)."""
    ov = s.outline
    for tid, lvs in _slots(c, d).items():
        for lv, v in lvs.items():
            rep = v.get("rep")
            want = (ov["lines"].get(rep) or {}).get("fmt") if rep else ""
            for g in v["groups"]:
                if want and not g["rep"] and ov["lines"][g["paras"][0]].get("fmt") not in ("", want):
                    return tid, int(lv), rep, g["paras"][0]
    raise AssertionError("대표와 서식 라벨이 다른 갈래가 없다")


def test_matched_lines_take_the_rep_format_label(sess):
    """대표에 맞춘 줄의 서식 라벨은 대표의 라벨이 된다 — 전에는 추출한 때의 라벨(S46 …)이 그대로 남아 「서식 1가지」 인 레벨에 다른 번호가 보였다."""
    c, d, s = sess
    assert s.outline.get("fmtv") == 1 and any(x.get("fmt") for x in s.outline["lines"].values())   # 오버레이 줄마다 그래프의 라벨
    tid, lv, rep, odd = _odd_label(c, d, s)
    want, was = s.outline["lines"][rep]["fmt"], s.outline["lines"][odd]["fmt"]
    assert c.get(f"/api/docs/{d}/outline").json()["fmts"][odd] == was != want and "fmt" not in c.get(f"/api/docs/{d}/outline").json()["lines"][odd]
    r = c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={"place": False, "like": odd})
    assert r.status_code == 200, r.text
    j = r.json()
    assert odd in j["changed"] and all(s.outline["lines"][p]["fmt"] == want for p in j["changed"])
    assert all(j["outline"]["fmts"][p] == want for p in j["changed"])                       # 화면이 받는 줄에도(여백 표시를 그 자리에서 다시 그린다)
    c.post(f"/api/docs/{d}/undo")
    assert s.outline["lines"][odd]["fmt"] == was                                                    # 되돌리면 라벨도
    _undo_all(c, d, s)


def test_label_sync_repairs_an_overlay_matched_before_labels_followed(sess):
    """라벨이 따라오기 전에 맞춰 둔 작업(오버레이 줄에 라벨이 없다) — 오버레이를 읽을 때 한 번: 그래프의 라벨을 싣고, 지금 서식이 대표와 같은 줄은 대표의 라벨로."""
    c, d, s = sess
    tid, lv, rep, odd = _odd_label(c, d, s)
    want, was = s.outline["lines"][rep]["fmt"], s.outline["lines"][odd]["fmt"]
    assert c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={"place": False, "like": odd}).status_code == 200
    for x in s.outline["lines"].values():   # 옛 오버레이를 흉내 낸다 — 줄에 라벨이 없고 맞춘 줄은 그래프에 옛 라벨로 남아 있다
        x.pop("fmt", None)
    s.outline.pop("fmtv", None)
    g = heading_runs.graph(s)
    assert next(n["fmt"] for n in g["nodes"] if n["para"] == odd) == was
    assert server._outline_ov(s) is s.outline and s.outline["fmtv"] == 1
    assert s.outline["lines"][odd]["fmt"] == want and s.outline["lines"][rep]["fmt"] == want
    assert M.label_sync(s.doc, s.outline, g) is False                                               # 한 번만
    _undo_all(c, d, s)


def test_manual_format_change_shows_the_line_as_different(sess):
    """맞춘 뒤 **손으로** 서식을 바꾼 줄은 대표의 라벨 그대로 숨지 않는다 — 보일 라벨은 저장된 값이 아니라 **지금 비교**로 정한다: 대표와 달라지면 「≠」, 다시 같아지면 대표의 라벨.
    대표 줄을 바꾸면 그 레벨의 줄 전부가 달라진다. 편집 응답과 GET …/outline/fmts 가 같은 값을 준다."""
    c, d, s = sess
    tid, lv, rep, odd = _odd_label(c, d, s)
    want = s.outline["lines"][rep]["fmt"]
    now = lambda: c.get(f"/api/docs/{d}/outline/fmts").json()["fmts"]  # noqa: E731
    assert now()[odd] not in ("", want, M.OFF)                                                                     # 맞추기 전 — 제 라벨(대표와 다른 번호)
    assert c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={"place": False, "like": odd}).status_code == 200 and now()[odd] == want
    r = c.post(f"/api/docs/{d}/format/chars", json={"id": odd, "start": 0, "end": 0, "changes": {"sizePt": 31}})   # 글자 크기를 손으로
    assert r.status_code == 200, r.text
    assert r.json()["fmts"][odd] == "≠" and now()[odd] == "≠" and c.get(f"/api/docs/{d}/outline").json()["fmts"][odd] == "≠"   # 대표와 달라졌다 — 편집 응답에도
    assert s.outline["lines"][odd]["fmt"] == want                                                                   # 저장된 라벨은 그대로(보일 때 셈한다)
    c.post(f"/api/docs/{d}/undo")
    assert now()[odd] == want                                                                                       # 서식을 되돌리면 다시 대표의 라벨
    mates = [p for p in M.slot_ids(s.outline, tid, lv) if p != rep and now().get(p) == want]
    r = c.post(f"/api/docs/{d}/format/chars", json={"id": rep, "start": 0, "end": 0, "changes": {"sizePt": 31}})   # 대표 줄을 손으로 — 대표를 따르던 줄이 모두 대표와 달라진다
    assert r.status_code == 200 and mates and all(r.json()["fmts"][p] == "≠" for p in mates) and r.json()["fmts"][rep] == want
    # 「≠」 인 두 줄 가운데 하나를 대표로 정해도 다른 줄이 「같은 라벨」 이라고 숨지 않는다(저장된 라벨이 아니라 비교로 — astra)
    c.post(f"/api/docs/{d}/undo")
    a2, b2 = mates[0], next((p for p in mates[1:]), None)
    if b2:
        assert c.post(f"/api/docs/{d}/format/chars", json={"id": a2, "start": 0, "end": 0, "changes": {"sizePt": 31}}).status_code == 200
        assert c.post(f"/api/docs/{d}/format/chars", json={"id": b2, "start": 0, "end": 0, "changes": {"sizePt": 33}}).status_code == 200
        assert now()[a2] == "≠" and now()[b2] == "≠"
        assert c.put(f"/api/docs/{d}/outline/slots/{tid}/{lv}/rep", json={"para": a2}).status_code == 200
        f = now()
        assert f[b2] != f[a2] or f[b2] == "≠"                                                                       # 대표(a2)와 서식이 다른 b2 는 대표의 라벨로 보이지 않는다
    _undo_all(c, d, s)


def test_a_line_within_tolerance_of_the_rep_shows_as_near(sess):
    """번호로 구별되지 않는 줄을 둘로 가른다(2026-11-16 사용자 「≠ 이거는 유사한 의미가 아니라 ≈ 이걸로」) — 레터가 같고 다른 값이 오차 안이면 「≈」(대표와 거의 같음),
    레터가 다르거나 오차 밖이면 「≠」. 편집 응답 · GET …/outline/fmts 가 같은 값을 준다."""
    c, d, s = sess
    tid, lv, rep, odd = _odd_label(c, d, s)
    want, tol = s.outline["lines"][rep]["fmt"], G.tolerance()
    now = lambda: c.get(f"/api/docs/{d}/outline/fmts").json()["fmts"]  # noqa: E731
    assert c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={"place": False, "like": odd}).status_code == 200 and now()[odd] == want
    base = M.look(s.doc, s.outline, rep)
    size = lambda v: c.post(f"/api/docs/{d}/format/chars", json={"id": odd, "start": 0, "end": 0, "changes": {"sizePt": v}})  # noqa: E731
    r = size(base["sizePt"] + tol["sizePt"])                                                                        # 글자 크기를 오차만큼만 — 추출이 같은 번호로 묶는 차이
    assert r.status_code == 200, r.text
    assert M.NEAR == "≈" and r.json()["fmts"][odd] == "≈" and now()[odd] == "≈" and c.get(f"/api/docs/{d}/outline").json()["fmts"][odd] == "≈"
    assert s.outline["lines"][odd]["fmt"] == want                                                                   # 저장된 라벨은 그대로(보일 때 셈한다)
    c.post(f"/api/docs/{d}/undo")
    r = size(base["sizePt"] + tol["sizePt"] + 1)                                                                    # 오차 밖 — 전처럼 「≠」
    assert r.status_code == 200 and r.json()["fmts"][odd] == "≠" == M.OFF
    c.post(f"/api/docs/{d}/undo")
    assert now()[odd] == want
    # 판정 함수 — 레터 · 범주(정렬·굵게)가 다르면 오차와 무관하게 아님 · 보통 빈칸과 묶음 빈칸은 같은 한 칸 · 글꼴은 같은 군이면 같음
    near = lambda **ch: M.near(base, {**base, **ch}, tol)  # noqa: E731
    assert near() and near(gap=base["gap"].replace(" ", "\u2002")) and near(lead=base["lead"] + " ") and not near(lead=base["lead"] + "   ")
    assert not near(letter=base["letter"] + "x") and not near(bold=not base["bold"]) and not near(align="?")
    if isinstance(base["line1Mm"], float):
        assert near(line1Mm=base["line1Mm"] + tol["indentMm"]) and not near(line1Mm=round(base["line1Mm"] + tol["indentMm"] + 0.2, 1))
    assert M.near({**base, "font": "함초롬바탕"}, {**base, "font": "HCR Batang"}, tol) and not M.near({**base, "font": "함초롬바탕"}, {**base, "font": "돋움"}, tol)
    _undo_all(c, d, s)


def test_unseen_groups_reach_the_agent_past_the_group_limit(sess, monkeypatch):
    """갈래가 한도를 넘는 레벨: 앞 계획이 **보낸 적 있는** 갈래는 다음 자료에서 뒤로 돌아 못 본 갈래가 에이전트에 닿는다 — 전에는 줄 수 많은 앞 갈래만 되풀이해 보내 뒤쪽에 닿지 못했다.
    못 보낸 갈래 가운데 검토해 그대로 둔 것은 계획에 「그대로」 로, 답이 없던 것은 답 없음 그대로 이어받고, 한 번도 못 보낸 갈래가 없으면 못 본 수가 0 이 된다(「다시 받기」 가 끝난다).
    이력은 **지문이 같은 갈래**에만 잇는다(열쇠 줄이 같아도 서식이 바뀌어 다른 갈래가 됐으면 새 갈래다 — astra)."""
    _, _, s = sess
    monkeypatch.setattr(A, "GROUP_MAX", 2)
    paras = lambda rows: [r["para"] for r in rows]  # noqa: E731
    mat = A.material(s.doc, s.outline, "2")                                           # T2 L1: 대표 p970 ×3 · p11850 ×3 · p1014 ×1 — 한도 2 면 뒤의 한 갈래를 못 보낸다
    lv = next(x for x in mat["levels"] if x["level"] == 1)
    assert paras(lv["groups"]) == ["p970", "p11850"] and lv["more"] == 1 and lv["held"] == [] and lv["heldAuto"] == []
    first = A.check_plan(mat, {"summary": "", "levels": [{"level": 1, "rep": "g1", "match": [], "keep": [{"group": "g2", "why": "남김"}], "split": [], "why": ""}]})
    assert first["omitted"] == 1 and paras(first["reviewed"]) == ["p11850"] and paras(first["sent"]) == ["p11850"] and all(r["sig"] for r in first["reviewed"])
    mat2 = A.material(s.doc, s.outline, "2", reviewed=first["reviewed"], sent=first["sent"])
    lv2 = next(x for x in mat2["levels"] if x["level"] == 1)
    assert paras(lv2["groups"]) == ["p970", "p1014"]                                 # 이번에는 못 봤던 갈래가 간다
    assert lv2["more"] == 0 and paras(lv2["held"]) == ["p11850"] and lv2["heldAuto"] == []
    second = A.check_plan(mat2, {"summary": "", "levels": [{"level": 1, "rep": "g1", "match": ["g2"], "keep": [], "split": [], "why": ""}]})
    L1 = next(x for x in second["levels"] if x["level"] == 1)
    assert second["omitted"] == 0 and paras(L1["match"]) == ["p1014"]
    assert [(k["para"], k["auto"], k.get("carried")) for k in L1["keep"]] == [("p11850", False, True)] and paras(second["reviewed"]) == ["p11850"]   # 앞 계획의 「그대로」 를 이어받는다
    assert sorted(paras(second["sent"])) == ["p1014", "p11850"] and not L1["single"] and second["left"]["kept"] == 3
    # 지문이 다른 이력(그 줄의 서식이 바뀌어 다른 갈래가 됐다)은 잇지 않는다 — 새 갈래로 다시 보낸다
    stale = [{"para": "p11850", "sig": "다른-갈래"}]
    lv3 = next(x for x in A.material(s.doc, s.outline, "2", reviewed=stale, sent=stale)["levels"] if x["level"] == 1)
    assert paras(lv3["groups"]) == ["p970", "p11850"] and lv3["more"] == 1 and lv3["held"] == []
    # 보냈지만 답이 없던 갈래도 뒤로 돈다(뒤쪽을 막지 않는다) — 답 없음으로 이어진다(검토해 남긴 것이 아니다)
    none = A.check_plan(mat, {"summary": "", "levels": []})
    assert none["reviewed"] == [] and paras(none["sent"]) == ["p11850"] and none["left"]["unanswered"] >= 1
    lv4 = next(x for x in A.material(s.doc, s.outline, "2", reviewed=none["reviewed"], sent=none["sent"])["levels"] if x["level"] == 1)
    assert paras(lv4["groups"]) == ["p970", "p1014"] and lv4["more"] == 0 and lv4["held"] == [] and paras(lv4["heldAuto"]) == ["p11850"]
    mat4 = A.material(s.doc, s.outline, "2", reviewed=none["reviewed"], sent=none["sent"])
    fourth = A.check_plan(mat4, {"summary": "", "levels": [{"level": 1, "rep": "g1", "match": ["g2"], "keep": [], "split": [], "why": ""}]})
    k4 = next(x for x in fourth["levels"] if x["level"] == 1)["keep"]
    assert [(k["para"], k["auto"]) for k in k4] == [("p11850", True)] and fourth["omitted"] == 0 and fourth["left"]["unanswered"] == 3 and fourth["reviewed"] == []


def test_pair_judgment_calls_are_off_by_default(sess, monkeypatch):
    """서식 쌍 판정(C)과 재검토(D)는 기본 실행에서 뺐다 — 그 판정은 문서도 서식 계획도 바꾸지 않았다. 안 하면 그 호출이 없고 `llm.pairs` = False(화면이 「하지 않음」 으로 보인다). 설정으로 켜면 전처럼."""
    _, _, s = sess
    monkeypatch.delenv("NFM_HEADS_PAIRS", raising=False)
    assert heading_runs.pairs_on() is False
    monkeypatch.setenv("NFM_HEADS_PAIRS", "on")
    assert heading_runs.pairs_on() is True
    s1 = heading_runs.state(s)["stage1"]
    seen = []

    def ask(jobs):
        out = []
        for j in jobs:
            what = j["what"].split("#")[0]
            seen.append(what)
            data = {"heading_types": {"types": [], "mainChain": [], "same": [], "summary": "가짜"}, "heading_section": {"changes": [], "summary": ""},
                    "heading_formats": {"pairs": [], "summary": ""}, "heading_review": {"pairs": [], "summary": ""}}[what]
            out.append({"data": data, "error": None, "backend": "api", "model": "m", "effort": "low", "ms": 1, "costUsd": 0.0})
        return out
    g = HG.build(s1, use_llm=True, ask=ask, pairs=False)
    assert not g["llm"]["fallback"] and g["llm"]["pairs"] is False and g["llm"].get("formatPairs") is None and g["llm"].get("reviewPairs") is None
    assert "heading_types" in seen and "heading_formats" not in seen and "heading_review" not in seen
    assert all(x["decision"] == "undecided" for x in g["adjustments"]) and g["adjustments"]   # 조정 목록은 스크립트가 낸 그대로(판정 안 함)
    seen.clear()
    g2 = HG.build(s1, use_llm=True, ask=ask)                                               # 켜면(인자 기본 — 시험 · 설정 on) 전처럼 C 를 부른다
    assert g2["llm"]["pairs"] is True and "heading_formats" in seen


def test_sure_relations_are_merged_by_apply_all_and_ambiguous_only_hinted(sess):
    """템플릿 사이 관계 — **확실한 것은 저절로, 애매한 것만 제안**(2026-11-16 사용자 「확실이 구분되는건 자동으로 하고 애매한것만 제안 … 다시 되돌리면 되는 거잖아」):
    한 자리 (A, Lk) 의 줄 아래에만 매달린 가지 템플릿은 「모두 반영」 이 그 자리의 템플릿 아래 종속 템플릿으로 넣는다 — 트랜잭션 하나(실행 취소 1번으로 통째로 돌아온다) ·
    사람이 「하위로」 를 푼 쌍은 다시 걸지 않는다 · 번호가 윗줄을 넘어 이어지는 번호형 가지는 제안만(저절로 안 건다)."""
    c, d, s = sess
    hints = M.merge_hints(s.outline)
    sure = [h for h in hints if h["sure"]]
    assert len(sure) >= 2 and all(s.outline["templates"][h["child"]]["kind"] == "branch" for h in hints)
    for h in hints:   # 제안의 조건 — 그 템플릿의 첫 레벨 줄이 모두 그 한 자리의 줄 아래에 있다 · 본문 줄
        firsts = [x for x in s.outline["lines"].values() if x["tpl"] == h["child"] and int(x["level"]) == 1]
        assert len(firsts) == h["places"] and all((x.get("flow") or "body") == "body" for x in firsts)
        assert {(s.outline["lines"][x["parent"]]["tpl"], int(s.outline["lines"][x["parent"]]["level"])) for x in firsts} == {(h["parent"], h["at"])}
        assert h["sure"] == (not h["why"])
    tmpl = next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "templates")
    assert [(h["child"], h["parent"], h["at"], h["sure"]) for h in tmpl["hints"]] == [(h["child"], h["parent"], h["at"], h["sure"]) for h in hints]   # 분석 상태에도(조정 층 · 결과 화면)
    # 애매한 것 — 번호형 가지의 한 윗줄 아래 줄들이 「가.」 가 아니라 뒤 번호부터(앞 자리의 번호를 이음): 제안으로는 남고 저절로는 안 건다(오버레이 사본에서 — 규칙만 본다)
    amb = next(h for h in sure if M.OE.is_numbered(h["chain"][0]))
    ov2 = copy.deepcopy(s.outline)
    kids = [(pid, x) for pid, x in ov2["lines"].items() if x["tpl"] == amb["child"] and int(x["level"]) == 1]
    for pid, x in kids:
        if x["parent"] == kids[0][1]["parent"]:
            x["letter"] = M.OE.with_numbers(x["letter"], [M.OE.numbers_of(x["letter"])[-1] + 5]) or x["letter"]
    h2 = next(h for h in M.merge_hints(ov2) if h["child"] == amb["child"])
    assert h2["sure"] is False and "이어지는" in h2["why"]
    done = M.auto_merge(ov2)
    assert {m["child"] for m in done} == {h["child"] for h in sure} - {amb["child"]}          # 확실한 것만 — 애매한 것은 안 건다
    assert [(h["child"], h["sure"]) for h in M.merge_hints(ov2)] == [(amb["child"], False)]      # 남은 것은 애매한 제안 하나
    # 「모두 반영」 — 받아 둔 서식 계획이 없어도 확실한 종속은 건다: 오버레이만 · 트랜잭션 하나
    url, undo, before = f"/api/docs/{d}/outline/agent/apply", s.state()["undo"], c.get(f"/api/docs/{d}/download").content
    assert c.post(url, json={"place": False, "rev": s.rev, "relations": False}).status_code == 409            # 서식 계획이 없고 종속도 안 걸라 했으면 할 것이 없다
    r = c.post(url, json={"place": False, "rev": s.rev})
    assert r.status_code == 200, r.text
    j = r.json()
    assert {m["child"] for m in j["merged"]} == {h["child"] for h in sure}
    assert j["changed"] == [] and s.state()["undo"] == undo + 1 and c.get(f"/api/docs/{d}/download").content == before   # 문서는 그대로 · 실행 취소 1
    for m in j["merged"]:
        assert m["id"] in s.outline["templates"] and s.outline["templates"][m["id"]]["composite"]["parent"] == m["parent"] and m["moved"] >= 1
    assert not M.merge_hints(s.outline)                                                         # 다 걸었다(한 건마다 다시 셈)
    last = c.get(f"/api/docs/{d}/headings/llm-changes").json()
    assert last["applies"][-1]["by"] == "all" and [m["id"] for m in last["applies"][-1]["relations"]] == [m["id"] for m in j["merged"]] and "ids" not in last["applies"][-1]["relations"][0]
    assert last["relations"] == []                                                              # 결과 화면의 제안 절 — 남은 제안 없음
    assert c.post(f"/api/docs/{d}/undo").status_code == 200                                    # 실행 취소 한 번으로 통째로
    assert all(m["id"] not in s.outline["templates"] for m in j["merged"])
    assert [h["child"] for h in M.merge_hints(s.outline) if h["sure"]] == [h["child"] for h in sure]
    # 사람이 넣었다가 푼 쌍은 다시 제안하지도 걸지도 않는다
    h0 = sure[0]
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": h0["child"], "parent": h0["parent"], "at": h0["at"]}).status_code == 200
    assert c.post(f"/api/docs/{d}/outline/unmerge", json={"child": h0["child"], "parent": h0["parent"]}).status_code == 200
    assert (h0["child"], h0["parent"], h0["at"]) not in {(h["child"], h["parent"], h["at"]) for h in M.merge_hints(s.outline)}
    r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev})
    assert r.status_code == 200 and h0["child"] not in {m["child"] for m in r.json()["merged"]} and r.json()["merged"]
    _undo_all(c, d, s)


def test_analysis_tells_undecided_heading_nodes(sess):
    """헤딩 판정의 미판정(LLM 구간 검증 실패 — 스크립트 초안 그대로)을 분석 상태가 알린다 — 「전체 실행」 이 그 수가 있으면 조정(반영)을 하지 않는다."""
    c, d, s = sess
    st = heading_runs.state(s)
    heads = lambda: next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "heads")  # noqa: E731
    assert heads()["undecided"] == 0
    g = st["stage2"]
    keep = (dict(g["llm"]), g["counts"].get("undecided"))
    try:
        g["llm"].update(requested=True, fallback=False, calls=3, failed=1)
        g["counts"]["undecided"] = 7
        h = heads()
        assert h["undecided"] == 7 and h["llm"]["state"] == "done" and "미판정 7" in h["llm"]["text"]
        g["llm"].update(requested=False)
        assert heads()["undecided"] == 0   # LLM 판정을 거친 결과가 아니면 묻지 않는다
    finally:
        g["llm"].clear()
        g["llm"].update(keep[0])
        g["counts"]["undecided"] = keep[1]
