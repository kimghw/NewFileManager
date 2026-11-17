"""자동 글머리 줄(spec_hwpx_웹편집 ② §8-8 「자동 글머리 줄」 — 2026-11-17 사용자 답 「친 레터로 바꿔 맞춤」).

레터가 글이 아니라 문단 모양의 글머리표 · 문단 번호인 헤딩 줄은 개요 오버레이의 줄(ov["lines"])이 못 돼 서식 갈래 · 정리 계획 · 조정이 건너뛰었다.
이제 ov["autos"] 에 따로 들고 그 레벨의 서식 갈래에 들며(다른 값 「자동 글머리」), 맞추면 대표의 접두가 글로 들어가 친 레터의 보통 줄이 된다.
시험 문서 = 연구개발계획서 양식의 친 레터 줄 몇 개를 자동 글머리표(기술수요조사서의 글머리표 정의 — 글자를 「-」 로) · 문단 번호(양식의 번호 정의 「^1.」)로 바꾼 것."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_edit as OE
from app import outline_match as M
from app import server
from app import tpl_agent
from app.hwpx_doc import HwpxDoc, _h

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
TECH = ROOT / "samples" / "기술수요조사서.hwpx"


def _auto_doc():
    """→ (hwpx 바이트, 자동 글머리표로 바꾼 줄 id 들, 문단 번호로 바꾼 줄 id 들)."""
    doc, src = HwpxDoc(PLAN.read_bytes()), HwpxDoc(TECH.read_bytes())
    doc.blocks()
    text = lambda pid: doc._text(doc._ids[pid])  # noqa: E731
    dash = [pid for pid in doc._ids if pid.startswith("p") and text(pid).startswith("   - ") and OE.body_of(text(pid), "-").strip()]
    bullets = dash[1:3]  # 첫 줄(친 레터)은 남긴다
    bid = doc._import(src, "bullet", "1", {})
    doc._defs["bullet"][bid].set("char", "-")
    nums = [pid for pid in doc._ids if pid.startswith("p") and text(pid).startswith(("2. 연구개발과제의 목표", "3. 연구개발과제의 추진"))][-2:]  # 앞 둘은 목차 — 본문의 큰 제목 둘
    assert len(bullets) == 2 and len(nums) == 2, (bullets, nums)

    def to_auto(pid, kind, ref, letter):
        p = doc._ids[pid]
        pp = copy.deepcopy(doc._defs["paraPr"][p.get("paraPrIDRef")])
        h = pp.find(_h("heading"))
        h.set("type", kind)
        h.set("idRef", ref)
        h.set("level", "0")
        p.set("paraPrIDRef", doc._add_def("paraPr", pp))
        lead, tok, gap = OE.prefix_of(text(pid), letter)
        assert tok
        doc.replace_prefix(pid, len(lead + tok + gap), "")
    for pid in bullets:
        to_auto(pid, "BULLET", bid, "-")
    for pid, letter in zip(nums, ("2.", "3.")):
        to_auto(pid, "NUMBER", "1", letter)
    return doc.save(), bullets, nums


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
def built():
    return _auto_doc()


@pytest.fixture(scope="module")
def sess(tmp_path_factory, built):
    data, bullets, nums = built
    tmp = tmp_path_factory.mktemp("outline_auto")
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
                     "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}.items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": ("auto.hwpx", data, "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        assert c.get(f"/api/docs/{d}/outline").status_code == 200  # 오버레이를 만든다
        yield c, d, s, data, bullets, nums
        server.DOCS.clear()


def _undo_all(c, d, s, data):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == data


# ---------------------------------------------------------------- 오버레이
def test_only_autos_that_make_the_same_letter_are_taken():
    """그 레벨과 **같은 레터가 생기는** 자동 글머리 줄만 든다(2026-11-17 사용자 「숫자, 영문, 문자는 그대로 갖어오고 동일한 레터가 생기는 자동만 처리하면 되잖아?」):
    기호는 글자까지 같아야 하고(「-」 레벨의 「•」 는 아님) · 번호형은 번호만 다를 수 있다(「1.」 레벨의 「2.」 는 됨 · 「3)」 은 아님) · 글 없는 줄 · 자동 글머리가 아닌 줄은 아님."""
    def node(pid, tpl, letter, key):
        return {"id": pid, "para": pid, "role": "heading", "template": tpl, "tplNo": 1 if tpl == "A" else 2, "level": 1, "letter": letter, "key": key, "parent": None, "flow": "body"}
    g = {"meta": {"run": 1, "at": 0}, "instances": [],
         "templates": [{"id": 1, "no": 1, "anchor": "A", "chain": ["-"], "slots": [{"level": 1, "letter": "-", "rep": "p1", "count": 5}]},
                       {"id": 2, "no": 2, "anchor": "B", "chain": ["N."], "slots": [{"level": 1, "letter": "1.", "rep": "q1", "count": 3}]}],
         "nodes": [node("p1", "A", "-", "-"), node("p2", "A", "-", "-"), node("p3", "A", "•", "-"), node("p4", "A", "-", "-"), node("p5", "A", "-", "-"),
                   node("q1", "B", "1.", "N."), node("q2", "B", "2.", "N."), node("q3", "B", "3)", "N.")]}
    probe = {"p1": ("- 가", None), "p2": ("나", "bullet"), "p3": ("다", "bullet"), "p4": ("  ", "bullet"), "p5": ("라", None),
             "q1": ("1. 가", None), "q2": ("나", "number"), "q3": ("다", "number")}
    ov = OE.build_overlay(g, lambda pid: {"text": probe[pid][0], "attrs": {}, "spacer": None, "auto": probe[pid][1]})
    assert set(ov["lines"]) == {"p1", "q1"}
    assert set(ov["autos"]) == {"p2", "q2"}
    assert ov["autos"]["q2"]["letter"] == "2." and ov["autos"]["p2"]["auto"] == "bullet"


def test_auto_lines_go_to_autos_not_lines_and_follow_their_parent(sess):
    c, d, s, data, bullets, nums = sess
    ov = s.outline
    autos = ov.get("autos") or {}
    for pid in bullets + nums:
        assert pid in autos and pid not in ov["lines"]                 # ov["lines"] 의 꼴·뜻은 그대로 — 자동 글머리 줄은 따로
    for pid in bullets:
        a = autos[pid]
        assert a["auto"] == "bullet" and a["letter"] == "-" and a["parent"] in ov["lines"] and a["d"] == 1
        par = ov["lines"][a["parent"]]
        assert OE.auto_slot(ov, pid) == (par["tpl"], int(par["level"]) + 1)  # 부모를 따라간다
        assert pid in M.slot_ids(ov, par["tpl"], int(par["level"]) + 1)
    assert {autos[p]["auto"] for p in nums} == {"number"}
    assert M.auto_kind(s.doc, bullets[0]) == "bullet" and M.auto_kind(s.doc, nums[0]) == "number" and M.auto_kind(s.doc, "p1") is None


def test_saved_overlay_without_autos_gets_them_on_next_read(sess):
    """자동 글머리 줄이 생기기 전에 저장된 작업의 오버레이(`autosv` 없음)는 다음에 읽을 때 한 번 채운다 — 헤딩 그래프를 다시 돌리지 않아도(그 오버레이는 그래프 실행이 같으면 다시 안 만든다)."""
    c, d, s, data, bullets, nums = sess
    want = copy.deepcopy(s.outline["autos"])
    saved = s.outline
    old = copy.deepcopy(saved)
    old.pop("autos")
    old.pop("autosv")
    s.outline = old
    try:
        ov = server._outline_ov(s)
        assert ov is old and ov["autosv"] == 1 and ov["autos"] == want
        assert OE.add_autos(ov, heading_runs.graph(s), server._outline_probe(s)) is False  # 한 번만
    finally:
        s.outline = saved


def test_auto_lines_are_their_own_format_with_auto_first_in_diff(sess):
    c, d, s, data, bullets, nums = sess
    tid, lv = OE.auto_slot(s.outline, bullets[0])
    v = M.variants(s.doc, s.outline, tid, lv)
    assert v["rep"] not in bullets
    autos = [g for g in v["groups"] if set(g["paras"]) & set(bullets)]
    assert autos and all(set(g["paras"]) <= set(bullets) for g in autos)  # 친 레터 줄과 같은 갈래에 섞이지 않는다
    for g in autos:
        assert g["diff"][0] == ["auto", M.AUTO, "친 글자", "자동 글머리표"]
        assert all(row[0] != "letter" for row in g["diff"])               # 레터는 라벨 — 「레터」 가 다른 것이 아니다(떼는 기준이 아님)
        assert not M.near(M.look(s.doc, s.outline, v["rep"]), g["raw"], M._tolerance())  # 「≈」 가 아니다
        assert g["raw"]["auto"] == "bullet" and "auto" not in g["look"]
    assert M.same(M.look(s.doc, s.outline, bullets[0]), M.look(s.doc, s.outline, bullets[0]))


def test_auto_lines_cannot_be_rep_or_split(sess):
    c, d, s, data, bullets, nums = sess
    tid, lv = OE.auto_slot(s.outline, bullets[0])
    with pytest.raises(ValueError, match="대표가 될 수 없습니다"):
        M.set_rep(s.doc, s.outline, tid, lv, bullets[0])
    assert M.split_block(s.outline, tid, lv, [bullets[0]], doc=s.doc) == M.AUTO_SPLIT
    r = c.put(f"/api/docs/{d}/outline/slots/{tid}/{lv}/rep", json={"para": bullets[0]})
    assert r.status_code == 400 and "대표가 될 수 없습니다" in r.json()["detail"]


def test_all_auto_level_has_no_rep(tmp_path, monkeypatch):
    """그래프가 자동 글머리 줄을 대표로 뽑은 레벨(기술수요조사서의 「◦」 — 그 레벨이 모두 자동 글머리)은 「대표 없음」 — 맞출 친 레터가 없다."""
    for k, v in {"NFM_PDF": "off", "NFM_WORKS": tmp_path / "works", "NFM_RENDER": tmp_path / "render", "NFM_FORMS": tmp_path / "forms",
                 "NFM_DIVISION_PRESETS": tmp_path / "presets.json"}.items():
        monkeypatch.setenv(k, str(v))
    c = TestClient(server.app, raise_server_exceptions=False)
    r = c.post("/api/docs", files={"file": (TECH.name, TECH.read_bytes(), "application/octet-stream")})
    d = r.json()["docId"]
    s = server.DOCS[d]
    try:
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        assert c.get(f"/api/docs/{d}/outline").status_code == 200
        autos = s.outline.get("autos") or {}
        assert autos
        tid, lv = OE.auto_slot(s.outline, next(iter(autos)))
        v = M.variants(s.doc, s.outline, tid, lv)
        assert v["rep"] is None and v["repMissing"] and v["total"] == len(M.slot_ids(s.outline, tid, lv))
        r = c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={})
        assert r.status_code == 400  # 대표가 없다
    finally:
        server.DOCS.pop(d, None)


# ---------------------------------------------------------------- 맞추기
def test_match_turns_auto_bullets_into_typed_letters_and_undo_restores(sess):
    c, d, s, data, bullets, nums = sess
    tid, lv = OE.auto_slot(s.outline, bullets[0])
    v0 = M.variants(s.doc, s.outline, tid, lv)
    rep = v0["rep"]
    sh = M.rep_shape(s.doc, s.outline, rep)
    r = c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={})
    assert r.status_code == 200, r.text
    got = r.json()
    assert set(bullets) <= set(got["changed"]) and got["left"] == []
    for pid in bullets:
        x = s.outline["lines"][pid]                                      # 보통 개요 줄로 옮겼다
        assert pid not in (s.outline.get("autos") or {}) and x["tpl"] == str(tid) and x["level"] == lv and x["letter"] == sh["tok"]
        assert M.auto_kind(s.doc, pid) is None                            # 글머리표가 꺼졌다(대표의 문단 모양)
        assert s.doc._text(s.doc._ids[pid]).startswith(sh["lead"] + sh["tok"])
        assert pid in got["outline"]["lines"]
    v1 = M.variants(s.doc, s.outline, tid, lv)
    assert len(v1["groups"]) == 1 and v1["groups"][0]["rep"]               # 한 레벨 = 한 서식
    c.post(f"/api/docs/{d}/undo")
    assert all(p in (s.outline.get("autos") or {}) for p in bullets)      # 실행 취소 — 자동 글머리 줄로 돌아온다
    _undo_all(c, d, s, data)


def test_match_freezes_the_numbers_shown_before_matching(sess):
    """자동 번호 줄 둘(번호 정의 1 — 한글에 「1.」 「2.」)을 함께 맞추면 「1.」 「2.」 — 한 줄을 바꾸면 그 줄이 번호 매김에서 빠지므로 바꾸기 전에 함께 센다(「1.」 「1.」 이 아니다)."""
    c, d, s, data, bullets, nums = sess
    tid, lv = OE.auto_slot(s.outline, nums[0])
    assert OE.auto_slot(s.outline, nums[1]) == (tid, lv)
    assert M.auto_numbers(s.doc, s.outline) == 0 and [s.outline["autos"][p]["letter"] for p in nums] == ["1.", "2."]
    r = c.post(f"/api/docs/{d}/outline/slots/{tid}/{lv}/match", json={"paras": nums})
    assert r.status_code == 200, r.text
    for pid, n in zip(nums, ("1.", "2.")):
        assert s.outline["lines"][pid]["letter"] == n and M.auto_kind(s.doc, pid) is None
        assert OE.prefix_of(s.doc._text(s.doc._ids[pid]), n)[1] == n
    _undo_all(c, d, s, data)


def test_sync_drops_auto_lines_whose_bullet_was_turned_off(sess):
    c, d, s, data, bullets, nums = sess
    ov = copy.deepcopy(s.outline)
    kinds = {bullets[0]: None}
    gone = OE.sync_autos(ov, lambda p: True, lambda p: kinds.get(p, "bullet" if p in bullets else "number"), lambda p: "글")
    assert gone == [bullets[0]] and bullets[0] not in ov["autos"] and bullets[1] in ov["autos"]
    gone = OE.sync_autos(ov, lambda p: False, lambda p: "bullet", lambda p: "글")
    assert set(gone) == set(bullets[1:] + nums) and "autos" not in ov


# ---------------------------------------------------------------- 서식 정리 에이전트
def test_tidy_material_marks_auto_groups_and_check_plan_keeps_them_off_rep(sess):
    c, d, s, data, bullets, nums = sess
    tid, lv = OE.auto_slot(s.outline, bullets[0])
    mat = tpl_agent.material(s.doc, s.outline, tid)
    row = next(x for x in mat["levels"] if x["level"] == lv)
    auto = [g for g in row["groups"] if g["cannotBeRep"]]
    assert auto and all(set([g["para"]]) <= set(bullets) for g in auto) and all(g["noSplit"] for g in auto)
    pm = tpl_agent.prompt_material(mat)
    items = next(x for x in pm["levels"] if x["level"] == lv)["groups"]
    assert all(i.get("cannotBeRep") for i in items if i["id"] in {g["id"] for g in auto})
    assert any(dr[0] == M.AUTO for i in items if i["id"] in {g["id"] for g in auto} for dr in i["differsFromRep"])
    was = next(g["id"] for g in row["groups"] if g["rep"])
    plan = tpl_agent.check_plan(mat, {"levels": [{"level": lv, "rep": auto[0]["id"], "match": [], "keep": [], "split": [], "why": ""}]})
    got = next(x for x in plan["levels"] if x["level"] == lv)
    assert got["rep"]["group"] == was and any("대표가 될 수 없음" in n for n in plan["notes"])
