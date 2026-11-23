"""확정 서식으로 바꾸기(spec_hwpx_웹편집 ② §8-8 — app/outline_conform.py) · 묶음 빈칸 글 모델(hwpx_doc.SPECIAL · hwpx_struct.set_chars) — 연구개발계획서 양식 + 2단계(LLM 끔).
템플릿과 서식이 정해지면 줄을 그 서식으로 바꾸는 스크립트는 하나다: 레터 뒤 빈칸 = 묶음 빈칸(hp:nbSpace ↔ 블록 글의 U+2002) · 둘째 줄 = 글 시작(자리 규칙).
서식 맞추기(레벨 · 템플릿) · 조정의 「모두 반영」 · 템플릿 변환(넣은 줄)이 같이 쓴다. 한글 실물(PDF)로 잰 것은 사양서 ③ 에 있다 — 여기서는 문서 값과 끝점의 약속을 본다."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_conform as OC
from app import outline_edit as OE
from app import outline_match as M
from app import outline_pos as OP
from app import server
from app.hwpx_doc import NB, NBSPACE, HwpxDoc

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


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
    tmp = tmp_path_factory.mktemp("outline_conform")
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
                     "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}.items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        assert c.get(f"/api/docs/{d}/outline").status_code == 200  # 오버레이를 만든다
        yield c, d, s
        server.DOCS.clear()


def _undo_all(c, d, s):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


def _formats(c, d):
    return next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")


def _para(doc, starts):
    doc.blocks()
    return next(pid for pid, el in doc._ids.items() if pid.startswith("p") and doc._text(el).startswith(starts))


# ---------------------------------------------------------------- 묶음 빈칸 글 모델
def test_nbspace_is_u2002_in_block_text_and_is_written_back_as_an_element():
    doc = HwpxDoc(PLAN.read_bytes())
    pid = _para(doc, "   - ")
    p = doc._ids[pid]
    text = doc._text(p)
    runs = [r.get("charPrIDRef") for r in p.iterchildren(M.RUN)]
    assert doc.set_chars(pid, 4, NB) is True and doc.set_chars(pid, 4, NB) is False            # 레터 뒤 빈칸 한 글자만 — 같은 값이면 안 바꾼다
    assert doc._text(p) == text[:4] + NB + text[5:] and len(list(p.iter(NBSPACE))) == 1          # 길이 그대로 · 글자는 hp:nbSpace 요소
    assert [r.get("charPrIDRef") for r in p.iterchildren(M.RUN)] == runs                         # 런·글자 모양은 그대로
    with pytest.raises(ValueError):
        doc.set_chars(pid, len(text), "xx")                                                       # 범위를 벗어남
    again = HwpxDoc(doc.save())                                                                   # 저장 → 다시 읽기
    q = _para(again, "   -" + NB)
    assert again._text(again._ids[q]) == doc._text(p)
    again.set_text(q, doc._text(p) + " 덧붙임")                                                   # 글을 고쳐도(그 hp:t 를 다시 써도) 묶음 빈칸은 남는다 — 전에는 보통 빈칸이 됐다
    assert again._text(again._ids[q]).startswith("   -" + NB) and len(list(again._ids[q].iter(NBSPACE))) == 1
    again.replace_prefix(q, 5, "  ㅇ" + NB + NB)                                                 # 접두를 다시 쓸 때도(맞추기 · 개요 편집)
    assert again._text(again._ids[q]).startswith("  ㅇ" + NB + NB) and len(list(again._ids[q].iter(NBSPACE))) == 2
    assert again.set_chars(q, 3, "  ") and again._text(again._ids[q]).startswith("  ㅇ  ") and not list(again._ids[q].iter(NBSPACE))   # 되돌리면 보통 빈칸


def test_nbspace_counts_as_blank_in_prefix_and_letter_rules():
    assert OE.prefix_of(" ㅇ" + NB + "글", "ㅇ") == (" ", "ㅇ", NB) and OE.prefix_of("1." + NB + NB + "개요", "1.") == ("", "1.", NB + NB)
    assert NB in R.WS and NB in OP.BLANKS and M.ws(NB) == "묶음 1칸" and M.ws(" " + NB) == "1칸 + 묶음 1칸"
    from app import headings
    assert headings.ws_code(" " + NB) == "_2"   # 레터 꼴(헤딩 규칙)에서는 반각 빈칸과 같은 꼴 — 조정 뒤에도 같은 레터로 읽힌다


def test_nbspace_width_is_half_em_times_ratio_without_spacing():
    """한글 PDF 실측(references/한글_문단모양_줄나눔.md 「묶음 빈칸」): 묶음 빈칸 = 0.5em × 장평 — 자간 · 「글꼴에 어울리는 빈칸」 과 무관. 보통 빈칸 = 0.5em × 장평 × (1 + 자간)."""
    doc = HwpxDoc(PLAN.read_bytes())
    m = OP.Measure(doc)
    tight = next(cid for cid in doc._defs["charPr"] if (c := m._char(cid)) and c["half"] and abs(c["spacing"]["LATIN"]) > 0.01)
    c = m._char(tight)
    half = 0.5 * c["em"] * c["rel"]["LATIN"] * c["ratio"]["LATIN"]
    assert abs(m.advance(NB, tight) - half) < 1e-9
    assert abs(m.advance(" ", tight) - half * (1 + c["spacing"]["LATIN"])) < 1e-9 and abs(m.advance(" ", tight) - m.advance(NB, tight)) > 1e-4


# ---------------------------------------------------------------- 확정 서식 — 줄 · 레벨
def test_settle_level_places_rep_and_its_group_and_freezes_the_slot(sess):
    c, d, s = sess
    ov = s.outline
    # T1 L5 「-」(2026-11-17 「잇닿은 사슬」 전의 T3 L2 — 「1-1.」 아래 o 의 「-」 가 주 사슬 L5 로): 대표 p5209 「    - 」 9줄 · p6502 「   - 」 5줄 · p5765 「    -」
    before = c.get(f"/api/docs/{d}/outline/formats").json()["slots"]["1"]["5"]
    assert before["rep"] == "p5209" and [g["count"] for g in before["groups"]] == [9, 5, 1]
    assert OC.pending(s.doc, ov, {"1"}) and "p5209" in OC.pending(s.doc, ov, {"1"})          # 대표와 그 갈래 — 아직 보통 빈칸
    r = c.post(f"/api/docs/{d}/outline/slots/1/5/match", json={"like": "p6502"})              # 갈래 하나만 맞춰도 대표와 대표 갈래는 확정 서식으로
    assert r.status_code == 200, r.text
    j = r.json()
    moved = set(j["changed"]) - set(j["placed"])
    assert "p6502" in moved and len(moved) == 5 and "p5765" not in j["changed"] and len(j["placed"]) == 9 and j["undo"] == 1
    m = OP.Measure(s.doc)
    for pid in j["changed"]:
        lead, tok, gap, plen, text = M.parts(s.doc, ov, pid)
        at = m.place(pid, tok)
        assert gap == NB and abs(at["line2Mm"] - at["textMm"]) < 0.02, pid                       # 레터 뒤 = 묶음 빈칸 · 둘째 줄 = 글 시작
    sl = ov["templates"]["1"]["slots"]["5"]
    assert sl["prefix"] == "    -" + NB and sl["attrs"]["paraPrIDRef"] == s.doc._ids["p5209"].get("paraPrIDRef")   # 새 줄(Enter)도 확정 서식
    after = c.get(f"/api/docs/{d}/outline/formats").json()["slots"]["1"]["5"]
    assert [g["count"] for g in after["groups"]] == [14, 1] and after["groups"][1]["paras"] == ["p5765"]                    # 안 고른 갈래는 그대로
    assert ["gap", "레터 뒤 빈칸", "묶음 1칸", "없음"] in after["groups"][1]["diff"]
    assert not [p for p in OC.pending(s.doc, ov, {"1"}) if int(ov["lines"][p]["level"]) == 5]
    enter = c.post(f"/api/docs/{d}/outline", json={"op": "sibling", "id": "p5209"})             # 같은 레벨 새 줄
    if enter.status_code == 200:
        new = enter.json()["focus"]["id"]
        assert s.texts[new].startswith("    -" + NB) and M.same(M.look(s.doc, ov, new), M.look(s.doc, ov, "p5209"))
    _undo_all(c, d, s)
    assert s.texts["p5209"].startswith("    - ") and s.texts["p6502"].startswith("   - ")


def test_apply_all_places_every_template_even_without_plans(sess):
    """조정의 「모두 반영」 — 받아 둔 계획이 없어도 스크립트가 자리를 맞춘다(문서 전체 · 실행 취소 1). 번호형 레벨은 줄마다 접두 폭이 달라도 같은 서식(규칙)이다."""
    c, d, s = sess
    ov = s.outline
    f0 = _formats(c, d)
    n0 = f0["place"]
    assert n0 > 100 and f"자리 안 맞은 줄 {n0}" in f0["apply"]["text"] and f0["apply"]["state"] == "none"
    groups0 = {(t, lv): len(v["groups"]) for t, lvs in c.get(f"/api/docs/{d}/outline/formats").json()["slots"].items() for lv, v in lvs.items()}
    counts0 = c.get(f"/api/docs/{d}/headings").json()["stage1"]["counts"]
    url, undo = f"/api/docs/{d}/outline/agent/apply", s.state()["undo"]
    assert c.post(url, json={"rev": s.rev, "relations": False, "place": "x"}).status_code == 400
    assert c.post(url, json={"rev": s.rev, "relations": False, "place": False}).status_code == 409   # 계획도 종속도 자리도 안 걸라 했으면 할 것이 없다
    r = c.post(url, json={"rev": s.rev, "relations": False})
    assert r.status_code == 200, r.text
    j = r.json()
    assert sorted(j["placed"]) == sorted(j["changed"]) and len(j["placed"]) == n0 and j["templates"] == [] and j["plans"] == 0 and s.state()["undo"] == undo + 1
    f1 = _formats(c, d)
    assert f1["place"] == 0 and "자리 안 맞은 줄" not in f1["apply"]["text"] and not OC.pending(s.doc, s.outline)
    m = OP.Measure(s.doc)
    for pid in j["placed"]:
        lead, tok, gap, plen, text = M.parts(s.doc, s.outline, pid)
        at = m.place(pid, tok)
        assert " " not in gap and (at is None or at["prefixMm"] > OP.MAX_PREFIX_MM or abs(at["line2Mm"] - at["textMm"]) < 0.02
                                   or (OP.free(s.doc, s.outline, pid) and abs(at["firstMm"]) < 0.02)), (pid, text[:12])   # 가운데 · 오른쪽 정렬 줄은 묶음 빈칸만(기본 자리 규칙 없음)
    groups1 = {(t, lv): len(v["groups"]) for t, lvs in c.get(f"/api/docs/{d}/outline/formats").json()["slots"].items() for lv, v in lvs.items()}
    assert set(groups1) == set(groups0) and all(groups1[k] <= groups0[k] for k in groups0)        # 확정 서식을 걸어도 갈래가 늘지 않는다(규칙이 같으면 같은 서식)
    # 「2번째 줄」 은 값이 아니라 규칙으로 견준다: 둘째 줄이 제 글 시작에 있으면 「글 시작」 — 번호 폭 · 줄 맞춤 자간으로 mm 값이 달라도 같은 서식
    v = c.get(f"/api/docs/{d}/outline/formats", params={"tpl": "1", "level": 2}).json()["slots"]["1"]["2"]
    looks = [M.look(s.doc, s.outline, p) for p in v["groups"][0]["paras"]]
    assert all(x.get("line2At") == M.AT_TEXT for x in looks) and v["groups"][0]["look"]["line2Mm"].startswith("글 시작(")
    a, b = dict(looks[0]), {**looks[0], "line2Mm": looks[0]["line2Mm"] + 3.5}                         # 접두가 넓은 줄(「10-12.」) — 둘째 줄 mm 는 다르다
    assert M.same(a, b) and M.diff(a, b) == [] and M.cval(a, "line2Mm") == M.AT_TEXT
    off = {k: v_ for k, v_ in b.items() if k != "line2At"}                                           # 둘째 줄이 글 시작이 아닌 줄
    assert not M.same(a, off) and M.diff(a, off)[0][:2] == ["line2Mm", "2번째 줄"] and M.diff(a, off)[0][2].startswith("글 시작(")
    assert c.post(url, json={"rev": s.rev, "relations": False}).status_code == 409                   # 다 걸렸다 — 다시 할 것이 없다
    heading_runs.run_sync(s, 1, False)                                                             # 헤딩 규칙(1단계)은 조정 뒤 글(레터 뒤 묶음 빈칸)도 전과 같이 읽는다 — 종류·레터 수가 그대로
    counts1 = c.get(f"/api/docs/{d}/headings").json()["stage1"]["counts"]
    vary = ("labels", "formats")                                                                   # 서식 가짓수 · 라벨 수는 달라진다(레벨마다 내어쓰기가 제 접두 폭이 됐다 — 전에는 여러 레벨이 「첫 줄 0」 을 같이 썼다)
    assert {k: v for k, v in counts1.items() if k not in vary} == {k: v for k, v in counts0.items() if k not in vary}
    assert c.post(f"/api/docs/{d}/undo").status_code == 200 and _formats(c, d)["place"] == n0       # 실행 취소 한 번
    _undo_all(c, d, s)
    heading_runs.run_sync(s, 1, False)


def test_template_match_places_only_when_it_matches(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline/templates/1/match", json={"levels": [{"level": 5, "rep": "p6502", "likes": []}]})   # 대표만 — 문서는 그대로(오버레이만)
    assert r.status_code == 200 and r.json()["changed"] == [] and r.json()["reps"] == 1 and c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()
    c.post(f"/api/docs/{d}/undo")
    r = c.post(f"/api/docs/{d}/outline/templates/1/match", json={})                                                      # 모든 레벨 — 맞추고 그 템플릿의 줄을 확정 서식으로
    assert r.status_code == 200, r.text
    j = r.json()
    assert {"p6502", "p5765"} <= set(j["changed"]) - set(j["placed"]) and "p5209" in j["placed"]
    assert all(s.outline["lines"][p]["tpl"] == "1" for p in j["placed"]) and not OC.pending(s.doc, s.outline, {"1"})      # 그 템플릿만
    assert OC.pending(s.doc, s.outline, {"2"})                                                                             # 다른 템플릿은 그대로
    _undo_all(c, d, s)


def test_after_insert_gives_an_inserted_line_its_own_hanging_when_the_model_follows_the_rule(sess):
    """템플릿 변환(이관·취합이 넣은 줄 — merge_convert.apply 가 본보기 모양을 입힌 뒤): 본보기가 「둘째 줄 = 글 시작」 꼴이면 접두 폭이 다른 줄(번호형)도 제 접두 폭으로."""
    c, d, s = sess
    like, other = "p968", "p5930"                                             # T1 L2 「 1-1. 」(대표) · 「5-3. 」
    doc = HwpxDoc(PLAN.read_bytes())
    doc.blocks()
    m = OP.Measure(doc)
    plen = len("5-3. ")
    doc.replace_prefix(other, plen, " 10-12." + NB, like_id=like)             # 본보기가 조정 전 — 본보기 모양 그대로 두고 건드리지 않는다
    assert OC.after_insert(doc, other, "10-12.", like, "1-1.", m) is False
    doc.set_chars(like, len(" 1-1."), NB)
    at = m.place(like, "1-1.")
    doc.format_para([like], {"indentLeftMm": round(at["x0"], 2), "firstLineMm": round(-at["prefixMm"], 2)})   # 본보기를 규칙대로(조정 뒤 문서)
    doc.replace_prefix(other, len(" 10-12." + NB), " 10-12." + NB, like_id=like)
    assert OC.after_insert(doc, other, "10-12.", like, "1-1.", m) is True
    a, b = m.place(other, "10-12."), m.place(like, "1-1.")
    assert abs(a["line2Mm"] - a["textMm"]) < 0.02 and a["prefixMm"] > b["prefixMm"] + 1 and abs(a["letterMm"] - b["letterMm"]) < 0.02


# ---------------------------------------------------------------- 조정 길의 빈 곳(2026-11-16 astra 검토 — 손으로 한 것과 조정이 같은 결과를 내게)
def _t1_l5(c, d):
    """T1 L5 「-」(2026-11-17 「잇닿은 사슬」 전의 T3 L2) — 대표 p5209 「    - 」 9줄 · p6502 「   - 」 5줄 · p5765 「    -」 1줄."""
    return c.get(f"/api/docs/{d}/outline/formats", params={"tpl": "1", "level": 5}).json()["slots"]["1"]["5"]


def test_template_match_places_a_matched_line_whose_prefix_width_differs_from_the_rep(sess, monkeypatch):
    """템플릿 맞추기 · 조정(apply_templates)은 방금 맞춘 줄의 자리를 놓치지 않는다. 대표가 이미 확정 서식(둘째 줄 = 글 시작)일 때 맞춘 줄은 대표의 내어쓰기 값을 그대로 받는데,
    그 줄의 접두 폭이 대표와 다르면(제 번호를 지키는 번호형 「10.」 · 제 자간을 지키는 줄 — outline_match.keep_fit) 둘째 줄이 제 글 시작이 아니라서 대표 갈래에서 빠진다 —
    대표 갈래를 다시 찾아(_mates) 거는 것만으로는 그 줄이 안 걸렸다(방금 맞췄는데 「대표와 다른 줄」 로 남음). 레벨 하나 맞추기는 고른 줄을 직접 넘겨 놓치지 않는다."""
    from app import hwpx_struct
    monkeypatch.setattr(hwpx_struct, "CHAR_EDIT", hwpx_struct.CHAR_EDIT | {"spacingPct"})   # 시험에서만 — 자간(줄 맞춤 값)을 끝점으로 준다(실행 취소로 되돌리게)
    c, d, s = sess
    assert c.post(f"/api/docs/{d}/outline/agent/apply", json={"rev": s.rev, "relations": False}).status_code == 200   # ① 대표를 먼저 확정 서식으로(받아 둔 계획 없이 자리만)
    rep = OP.Measure(s.doc).place("p5209", "-")
    assert abs(rep["line2Mm"] - rep["textMm"]) < 0.02 and not OC.pending(s.doc, s.outline, {"1"}) and s.outline["templates"]["1"]["slots"]["5"].get("pos") is None
    assert c.post(f"/api/docs/{d}/format/chars", json={"id": "p5765", "start": 0, "end": 5, "changes": {"spacingPct": 40}}).status_code == 200   # ② 다른 갈래(레터 뒤 빈칸 없음)의 줄 — 레터에 자간
    assert [g["count"] for g in _t1_l5(c, d)["groups"]] == [9, 5, 1]
    r = c.post(f"/api/docs/{d}/outline/templates/1/match", json={"levels": [{"level": 5, "likes": ["p5765"]}]})   # ③ 템플릿 맞추기 — 조정의 「모두 반영」 과 같은 몸
    assert r.status_code == 200, r.text
    j = r.json()
    assert "p5765" in j["changed"] and "p5765" not in j["placed"]                               # 대표에 맞춘 줄 — placed(자리만 건 줄)에는 안 든다
    m = OP.Measure(s.doc)
    a, b = m.place("p5765", "-"), m.place("p5209", "-")
    assert M.parts(s.doc, s.outline, "p5765")[:3] == M.parts(s.doc, s.outline, "p5209")[:3] == ("    ", "-", NB)   # 접두 글은 대표와 같다
    assert a["prefixMm"] == pytest.approx(b["prefixMm"], abs=0.01) and a["letterMm"] == pytest.approx(b["letterMm"], abs=0.01)   # 접두는 대표 것 — 레터의 제 자간을 지키지 않는다(2026-11-23: 폭이 달라 레터 · 글 시작이 줄마다 달랐다)
    assert abs(a["line2Mm"] - a["textMm"]) < 0.02, (a["line2Mm"], a["textMm"], b["line2Mm"])    # 그래도 둘째 줄 = **제** 글 시작(대표의 값이 아니라 규칙)
    assert M.same(M.look(s.doc, s.outline, "p5765"), M.look(s.doc, s.outline, "p5209")) and [g["count"] for g in _t1_l5(c, d)["groups"]] == [10, 5]   # 규칙이 같으니 대표 갈래
    _undo_all(c, d, s)


def test_split_only_apply_places_the_new_templates_rep(sess):
    """떼기만 하는 계획 반영(문서를 맞출 줄이 없음)도 **새 템플릿의 대표와 그 갈래**를 같은 반영에서 확정 서식으로 — 전에는 바꾸기 전의 대표로만 「자리가 안 맞은 줄」 을 세어
    오버레이만 바꾸는 길로 가고, 새 서식 종속 템플릿의 대표(대표가 아니던 갈래의 줄 — 한 번도 안 걸린 줄)는 그대로 남았다. 실행 취소는 그대로 한 번."""
    c, d, s = sess
    assert c.post(f"/api/docs/{d}/outline/agent/apply", json={"rev": s.rev, "relations": False}).status_code == 200   # 대표와 그 갈래는 이미 확정 서식
    assert not OC.pending(s.doc, s.outline)
    v = c.get(f"/api/docs/{d}/outline/formats").json()["slots"]["4"]["3"]        # T4 L3 「-」 — 대표 ×9 · ×7 · ×1 · ×1
    assert [g["count"] for g in v["groups"]] == [9, 7, 1, 1]
    big = v["groups"][1]["key"]
    undo = s.state()["undo"]
    r = c.post(f"/api/docs/{d}/outline/templates/4/match", json={"by": "agent", "levels": [{"level": 3, "likes": [], "splits": [{"likes": [big], "rep": big, "sfx": "a"}]}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert [x["no"] for x in j["splits"]] == ["4L3a"] and s.state()["undo"] == undo + 1 and s.outline["templates"]["4~3a"]["slots"]["3"]["rep"] == big
    assert not OC.pending(s.doc, s.outline, {"4~3a"}) and not OC.pending(s.doc, s.outline)        # 새 템플릿의 대표와 그 갈래도 걸렸다
    m, ov = OP.Measure(s.doc), s.outline
    mine = [p for p in M.slot_ids(ov, "4~3a", 3) if M._alive(s.doc, p)]
    assert len(mine) == 7
    for p in mine:
        at = m.place(p, ov["lines"][p]["letter"])
        assert M.parts(s.doc, ov, p)[2] == NB and abs(at["line2Mm"] - at["textMm"]) < 0.02, p
    assert set(mine) <= set(j["placed"]) and sorted(j["placed"]) == sorted(j["changed"])          # 대표에 맞춘 줄은 없다 — 자리만(placed)
    assert c.post(f"/api/docs/{d}/undo").status_code == 200                                       # 한 번에 되돌아간다 — 템플릿도 줄의 자리도
    assert "4~3a" not in s.outline["templates"] and s.state()["undo"] == undo and M.parts(s.doc, s.outline, big)[2] != NB
    other = v["groups"][3]["key"]                                                                 # 떼면서 다른 갈래 한 줄을 새 대표에 맞춘다 — 맞춘 줄도 새 템플릿의 규칙으로 걸린다
    r = c.post(f"/api/docs/{d}/outline/templates/4/match", json={"by": "agent", "levels": [{"level": 3, "likes": [], "splits": [{"likes": [big, other], "rep": big, "sfx": "a"}]}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert other in set(j["changed"]) - set(j["placed"]) and s.outline["lines"][other]["tpl"] == "4~3a" and not OC.pending(s.doc, s.outline, {"4~3a"})
    at = OP.Measure(s.doc).place(other, s.outline["lines"][other]["letter"])
    assert M.parts(s.doc, s.outline, other)[2] == NB and abs(at["line2Mm"] - at["textMm"]) < 0.02 and M.same(M.look(s.doc, s.outline, other), M.look(s.doc, s.outline, big))
    _undo_all(c, d, s)


def test_sure_merge_leaves_the_new_templates_placed_in_the_same_apply(sess):
    """확실한 종속(「T1T5」 …)을 저절로 넣는 반영 — 새 종속 템플릿의 레벨마다 대표가 그 템플릿의 줄이고, 대표와 그 갈래는 같은 반영에서 확정 서식이다.
    자리를 먼저 다 맞춘 뒤 종속만 남은 반영(문서를 안 바꿀 수도 있는 길)에서도 같다."""
    c, d, s = sess
    url = f"/api/docs/{d}/outline/agent/apply"
    assert [h for h in M.merge_hints(s.outline) if h["sure"]]

    def check(j):
        ov = s.outline
        made = [x["id"] for x in j["merged"]]
        assert made and not [h for h in M.merge_hints(ov) if h["sure"]]
        for cid in made:
            for lv, sl in ov["templates"][cid]["slots"].items():
                ids = M.slot_ids(ov, cid, lv)
                assert not ids or sl.get("rep") in ids, (cid, lv)                                  # 새 템플릿의 대표는 그 템플릿의 줄
        assert not OC.pending(s.doc, ov)                                                          # 대표와 그 갈래가 모두 확정 서식
    undo = s.state()["undo"]
    r = c.post(url, json={"rev": s.rev})                                                          # 자리 맞춤 + 종속을 한 번에
    assert r.status_code == 200 and s.state()["undo"] == undo + 1, r.text
    check(r.json())
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    assert c.post(url, json={"rev": s.rev, "relations": False}).status_code == 200                # 자리만 먼저
    r = c.post(url, json={"rev": s.rev})                                                          # 종속만 남음
    assert r.status_code == 200, r.text
    check(r.json())
    _undo_all(c, d, s)


def test_settle_keeps_the_position_rule_a_person_set(sess):
    """조정의 자리 맞춤은 사람이 그 레벨에 정해 둔 자리 규칙(슬롯의 pos — ② §8-1)이 먼저다: 「둘째 줄 12mm」 는 12mm 그대로 · 「문단 서식 그대로」 는 여백을 안 건드린다.
    기본 「둘째 줄 = 글 시작」 은 정한 규칙이 없는 레벨에만. 레터 뒤 빈칸은 규칙과 무관하게 묶음 빈칸이 된다."""
    c, d, s = sess
    assert c.put(f"/api/docs/{d}/outline/slots/1/5", json={"line2": "mm", "mm": 12}).status_code == 200     # T1 L5 「-」 — 둘째 줄 12mm
    assert c.put(f"/api/docs/{d}/outline/slots/1/4", json={"line2": "keep"}).status_code == 200            # T1 L4 「o」 — 문단 서식 그대로
    ov = s.outline
    assert ov["templates"]["1"]["slots"]["5"]["pos"] == {"line2": "mm", "mm": 12.0, "set": True} and ov["templates"]["1"]["slots"]["4"]["pos"] == {"line2": "keep", "set": True}
    m = OP.Measure(s.doc)
    was = {p: (at["leftMm"], at["firstMm"]) for p in M.slot_ids(ov, "1", 4) if (at := m.place(p, ov["lines"][p]["letter"])) is not None}
    assert len(was) == 22
    r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"rev": s.rev, "relations": False})
    assert r.status_code == 200, r.text
    m, ov = OP.Measure(s.doc), s.outline
    assert ov["templates"]["1"]["slots"]["5"]["pos"] == {"line2": "mm", "mm": 12.0, "set": True}             # 규칙은 그대로
    group = _t1_l5(c, d)["groups"][0]["paras"]
    assert len(group) == 9 and group[0] == "p5209"
    for p in group:
        at = m.place(p, "-")
        assert M.parts(s.doc, ov, p)[2] == NB and abs(at["line2Mm"] - 12) < 0.02 and abs(at["textMm"] - 12) > 0.5, (p, at["line2Mm"], at["textMm"])   # 12mm 그대로(글 시작이 아니다)
    for p, (left, first) in was.items():
        at = m.place(p, ov["lines"][p]["letter"])
        assert (at["leftMm"], at["firstMm"]) == (left, first), p                                             # 「그대로」 — 여백은 안 바뀐다
    assert M.parts(s.doc, ov, "p5208")[2] == NB and not OC.pending(s.doc, ov, {"1"})                        # T1 L4 대표 — 「그대로」 여도 레터 뒤는 묶음 빈칸
    free = m.place("p972", "o")                                                                              # 정한 규칙이 없는 레벨(T2 L2) — 기본: 둘째 줄 = 글 시작
    assert ov["templates"]["2"]["slots"]["2"].get("pos") is None and abs(free["line2Mm"] - free["textMm"]) < 0.02
    _undo_all(c, d, s)


def test_same_plan_gives_the_same_rep_whether_or_not_another_level_has_pending_lines(sess, monkeypatch):
    """같은 계획은 다른 레벨에 「자리가 안 걸린 줄」 이 있든 없든 같은 결과를 낸다(2026-11-17 astra 2차 검토 1번). 윗레벨 떼기가 아랫레벨의 **계획 대표를 데려가는** 계획:
    T4 「[…] › o › -」 — b = p6251(L1 · 대표와 다른 갈래) 아래의 L2 줄 a = p6253(지금 L2 대표 · 확정 서식 A) · r = p6341(확정 안 된 서식 R), 남는 L2 줄 p = p1603(확정 서식 P · 남는 줄의 첫 줄) ·
    q = p6210(r 와 같은 R). 계획 = L1 의 b 떼기 + L2 의 rep = r(맞출 갈래 없음). 전에는 오버레이만 바꾸는 길이 떠난 r 의 대표 바꿈을 건너뛰어 **대표 = p · 동결 모양 = 옛 A · q 는 안 걸린 채**였고,
    다른 레벨(L4)에 안 걸린 줄이 한 줄만 있어도 문서 편집 길이 q 를 대표로 뽑아 확정 서식을 걸었다 — L3 맞추기 하나를 더해도(편집 길) 마찬가지였다. 세 길이 대표 결정 · 동결 모양을 같이 쓴다."""
    from app import hwpx_struct
    monkeypatch.setattr(hwpx_struct, "CHAR_EDIT", hwpx_struct.CHAR_EDIT | {"spacingPct"})   # 시험에서만 — 자간(줄 맞춤 값)을 끝점으로 준다
    c, d, s = sess
    b, a, r, p, q, deep, x = "p6251", "p6253", "p6341", "p1603", "p6210", "p6202", "p5772"

    def ok(res):
        assert res.status_code == 200, res.text
        return res.json()

    def run(pend=False, more=False):
        at = OP.Measure(s.doc).place(r, "o")
        ok(c.post(f"/api/docs/{d}/format/para", json={"ids": [q], "changes": {"indentLeftMm": at["leftMm"], "firstLineMm": at["firstMm"]}}))   # q 를 r 와 같은 서식 R 로
        ok(c.put(f"/api/docs/{d}/outline/slots/4/2/rep", json={"para": a}))                                                              # 지금 L2 대표 = a(b 아래의 줄)
        ok(c.post(f"/api/docs/{d}/outline/agent/apply", json={"rev": s.rev, "relations": False}))                                         # 대표 갈래는 모두 확정 서식
        ok(c.post(f"/api/docs/{d}/format/chars", json={"id": p, "start": 0, "end": 0, "changes": {"color": "#112233"}}))                  # p = 확정 서식이지만 다른 갈래 P
        if pend:
            ok(c.post(f"/api/docs/{d}/format/para", json={"ids": [deep], "changes": {"firstLineMm": 0}}))                               # 다른 레벨(L4)의 한 줄만 자리가 안 걸린 채
        if more:
            ok(c.post(f"/api/docs/{d}/format/chars", json={"id": x, "start": 0, "end": 5, "changes": {"spacingPct": 40}}))               # L3 의 다른 갈래 줄 — 접두 폭이 대표와 다르게(제 자간)
        ov = s.outline
        v = c.get(f"/api/docs/{d}/outline/formats", params={"tpl": "4", "level": 2}).json()["slots"]["4"]["2"]
        assert [(g["key"], g["count"]) for g in v["groups"]] == [(a, 15), (q, 2), (p, 1)] and M.same(M.look(s.doc, ov, q), M.look(s.doc, ov, r))
        assert OC.pending(s.doc, ov) == ([deep] if pend else [])
        levels = [{"level": 1, "likes": [], "splits": [{"likes": [b]}]}, {"level": 2, "rep": r, "likes": []}] + ([{"level": 3, "likes": [x]}] if more else [])
        undo = s.state()["undo"]
        j = ok(c.post(f"/api/docs/{d}/outline/templates/4/match", json={"by": "agent", "levels": levels}))
        ov, m = s.outline, OP.Measure(s.doc)
        sl = ov["templates"]["4"]["slots"]["2"]
        sh = M.rep_shape(s.doc, ov, sl["rep"])
        lines = {}
        for pid in sorted(M.slot_ids(ov, "4", 2)):
            at = m.place(pid, ov["lines"][pid]["letter"])
            lines[pid] = (M.parts(s.doc, ov, pid)[2] == NB, abs(at["line2Mm"] - at["textMm"]) < 0.02)                 # 남은 L2 줄마다 (묶음 빈칸인가, 둘째 줄 = 글 시작인가)
        got = {"rep": sl["rep"], "level": next(L for L in j["levels"] if L["level"] == 2), "new": ov["templates"]["4~1a"]["slots"]["2"]["rep"], "lines": lines,
               "frozen": (sl["prefix"], sl["letter"], s.doc._summary(sl["attrs"]["paraPrIDRef"], sl["attrs"]["charPrIDRef"])),   # 동결 모양(새 줄이 물려받는다 — 값으로 견준다: 정의 id 는 실행마다 다를 수 있다)
               "frozenIsRep": sl["attrs"] == sh["attrs"] and sl["prefix"] == sh["prefix"] and sl.get("bodyChar") == sh["body"],
               "look": M.look(s.doc, ov, sl["rep"]), "pending": OC.pending(s.doc, ov, {"4", "4~1a"})}
        assert s.state()["undo"] == undo + 1 and ov["lines"][r]["tpl"] == ov["lines"][a]["tpl"] == "4~1a"                # 한 번의 반영 · a 와 r 는 새 템플릿으로 떠났다
        if more:
            ax = m.place(x, "-")
            assert x in set(j["changed"]) - set(j["placed"]) and abs(ax["line2Mm"] - ax["textMm"]) < 0.02               # 맞춘 줄은 제 접두 폭으로(방금 맞춘 줄의 자리)
        _undo_all(c, d, s)
        return got
    plain, pending, extra = run(), run(pend=True), run(more=True)
    assert plain["rep"] == pending["rep"] == extra["rep"] == q, (plain["rep"], pending["rep"], extra["rep"])   # 남은 줄 가운데 계획의 대표(R)와 서식이 같은 줄이 대표 — 어느 길이든
    assert plain == pending                                                                                      # 다른 레벨에 안 걸린 줄이 있든 없든 같은 결과(대표 · 동결 모양 · 남은 L2 줄의 자리)
    assert plain == extra                                                                                        # L3 맞추기 하나를 더해도 L2 의 결과는 같다
    assert plain["frozenIsRep"] and plain["lines"][q] == (True, True) and plain["lines"][p] == (True, True) and plain["pending"] == []
    assert plain["level"] == {"level": 2, "rep": q, "repChanged": True, "changed": 0} and plain["new"] == a      # 답의 대표 = 실제로 대표가 된 줄(떠난 줄이 아니다)


# ---------------------------------------------------------------- 넣은 뒤 정리(spec_병합 ② §5-9)의 한글 출력에서 나온 것(2026-11-22)
def _mini(*pids, pos=None, level=5, letter="-"):
    """T1 L5 「-」 줄들(PLAN 의 p5209 「    - 」 · p6502 「   - 」 — 본문 없음) · T1 L4 「o」(p6501 · p6504 — 본문 굵게)만 든 작은 개요 오버레이 — 첫 줄이 대표."""
    sl = {"letter": letter, "key": letter, "rep": pids[0], **({"pos": pos} if pos else {})}
    return {"lines": {p: {"tpl": "1", "no": 1, "level": level, "letter": letter, "key": letter, "role": "heading"} for p in pids},
            "templates": {"1": {"no": 1, "slots": {str(level): sl}}}}


def _bold_body(doc, ov, pid, bold=True):
    """원본의 굵은 소제목처럼 — 본문 런만 굵게(또는 보통) · 레터 런은 그대로."""
    lead, tok, gap, plen, text = M.parts(doc, ov, pid)
    doc.format_chars(pid, plen, len(text), {"bold": bold})


def test_settle_keep_holds_each_lines_own_body_emphasis():
    """넣는 쪽의 서식을 받는 레벨(merge_retidy.KEEP): 문단 · 접두 · 레터 런 · 본문의 다른 글자 값은 대표를 따르고 본문 강조만 그 줄의 것 — keep 이 없으면 전처럼 대표의 것."""
    got = {}
    for keep in (M.EMPH, None):
        doc = HwpxDoc(PLAN.read_bytes())
        doc.blocks()
        rep, pid = "p6501", "p6504"                                                               # T1 L4 「  o 보안관리체계 …」 · 「  o 참여연구자 …」(본문 굵게)
        ov = _mini(rep, pid, level=4, letter="o")
        _bold_body(doc, ov, pid, not M.look(doc, ov, rep)["bold"])                               # 대표와 본문 굵기가 다른 줄
        assert M.look(doc, ov, pid)["bold"] is not M.look(doc, ov, rep)["bold"] and M.look(doc, ov, pid)["L.bold"] is M.look(doc, ov, rep)["L.bold"]
        n0 = len(doc._defs["charPr"])
        OC.settle(doc, ov, "1", 4, [pid], OP.Measure(doc), [], keep)
        got[keep is not None] = [k for k, *_ in M.diff(M.look(doc, ov, rep), M.look(doc, ov, pid))]
        if keep:
            body = M._cid_at(doc, doc._ids[pid], M.parts(doc, ov, pid)[3])
            assert M.keep_emph(doc, M.rep_shape(doc, ov, rep)["body"], body) == body                # 같은 정의를 다시 쓴다(header 에 또 만들지 않음)
            assert M.keep_emph(doc, body, body) == body and len(doc._defs["charPr"]) <= n0 + 1
    assert got == {True: ["bold"], False: []}                                                # 강조만 다르다 · keep 없이는 대표와 같다(굵기를 잃음 — 전의 동작)


def test_center_aligned_line_gets_no_default_hanging_but_a_person_set_rule_applies():
    """가운데 · 오른쪽 정렬 줄은 기본 자리 규칙(둘째 줄 = 글 시작)을 안 건다 — 좁은 가운데 칸의 「① 항만 접근」 에 내어쓰기가 들어가 한 줄에 2~3자만 남았다. 사람이 정한 규칙은 건다."""
    def first_of(doc, pid):
        p = doc._ids[pid]
        return doc._summary(p.get("paraPrIDRef"), doc._char_id(p))["firstLineMm"]
    for align, pos, hang in (("center", None, False), ("right", None, False), ("left", None, True), ("center", {"line2": "text", "set": True}, True)):
        doc = HwpxDoc(PLAN.read_bytes())
        doc.blocks()
        ov = _mini("p5209", "p6502", pos=pos)
        doc.format_para(["p6502"], {"align": align, "indentLeftMm": 0, "firstLineMm": 0})
        m = OP.Measure(doc)
        assert OC.needs(doc, ov, "p6502", m) is True                                          # 레터 뒤 빈칸은 묶음 빈칸으로(정렬과 무관)
        OC.place(doc, ov, "p6502", m)
        assert (first_of(doc, "p6502") < -0.5) is hang, (align, pos)
        assert M.parts(doc, ov, "p6502")[2] == NB and OC.needs(doc, ov, "p6502", m) is False   # 두 번째는 할 것 없음


def _margins(doc, pid):
    """(왼쪽 여백, 첫 줄) mm."""
    p = doc._ids[pid]
    s = doc._summary(p.get("paraPrIDRef"), doc._char_id(p))
    return s["indentLeftMm"], s["firstLineMm"]


def _numbered_old_hang(align):
    """T1 L4 번호형 레벨(PLAN 의 p6501 「  1.」 대표 · p6504 「  10.」 — 레터 뒤 묶음 빈칸) · 둘 다 align · 왼쪽 여백 3mm — 대표에만 옛 확정 서식이 넣은 내어쓰기(대표의 접두 폭),
    「10.」 은 대표와 다른 서식(문단 뒤 간격). → (doc, ov, 대표, 「10.」)."""
    doc = HwpxDoc(PLAN.read_bytes())
    doc.blocks()
    rep, n = "p6501", "p6504"
    for pid, tok in ((rep, "1."), (n, "10.")):
        lead, t, gap = OE.prefix_of(doc._text(doc._ids[pid]), "o")
        doc.replace_prefix(pid, len(lead + t + gap), "  " + tok + NB)
    ov = {"lines": {p: {"tpl": "1", "no": 1, "level": 4, "letter": tok, "key": "N.", "role": "heading"} for p, tok in ((rep, "1."), (n, "10."))},
          "templates": {"1": {"no": 1, "slots": {"4": {"letter": "1.", "key": "N.", "rep": rep}}}}}
    doc.format_para([rep, n], {"align": align, "indentLeftMm": 3, "firstLineMm": 0})
    at = OP.Measure(doc).place(rep, "1.")
    doc.format_para([rep], {"indentLeftMm": round(at["x0"], 2), "firstLineMm": round(-at["prefixMm"], 2)})   # 옛 확정 서식이 대표에 넣은 내어쓰기
    doc.format_para([n], {"spaceAfterPt": 7})                                                                 # 대표와 다른 서식의 「10.」 줄
    return doc, ov, rep, n


@pytest.mark.parametrize("align", ["center", "right", "justify"])
@pytest.mark.parametrize("way", ["level", "plan"])
def test_center_level_conformed_before_converges_and_loses_the_old_hanging(align, way):
    """이 변경 전의 확정 서식은 가운데 정렬 대표에도 「둘째 줄 = 글 시작」 내어쓰기(대표의 접두 폭)를 넣었다 — 접두 폭이 다른 줄(「10.」)을 그 대표에 맞추면 그 값을 받아
    둘째 줄이 제 글 시작이 아니라 끝내 「다른 서식」 으로 남았다(2026-11-22 검토 — 맞추기 · 조정을 거듭해도). 확정 서식은 가운데 · 오른쪽 정렬 줄의 내어쓰기를 없앤다
    (첫 줄 0 · 왼쪽 여백 그대로 — outline_pos.unhang): 한 번에 모이고 두 번째는 바꿀 것이 없다. 「자리 맞춤」(pending)도 그 내어쓰기를 센다 · 글 고침 길(align)은 그대로.
    way = level(대표에 맞추기 — settle) · plan(조정 「모두 반영」 — 바꾸기 전의 대표 모양으로 맞춘 뒤 settle_templates + 맞춘 줄에 place). 양쪽 정렬은 전처럼 줄마다 제 접두 폭."""
    doc, ov, rep, n = _numbered_old_hang(align)
    m = OP.Measure(doc)
    hang = align == "justify"
    assert M.look(doc, ov, rep).get("line2At") == M.AT_TEXT
    assert OC.pending(doc, ov, {"1"}) == ([] if hang else [rep])                                             # 가운데 · 오른쪽: 남은 내어쓰기를 「자리 맞춤」 이 센다
    assert OP.align(doc, ov, rep, measure=m) is None and _margins(doc, rep)[1] < -0.5                           # 글 고침 · 새 줄 길은 그대로(문서가 준 값)
    if way == "level":
        OC.settle(doc, ov, "1", 4, [n], m)
    else:
        M.match_one(doc, ov, n, M.rep_shape(doc, ov, rep))                                                   # 계획의 대표 모양(바꾸기 전) — 내어쓰기째
        OC.settle_templates(doc, ov, ["1"], m)
        OC.place(doc, ov, n, m)
    assert M.same(M.look(doc, ov, rep), M.look(doc, ov, n)), M.diff(M.look(doc, ov, rep), M.look(doc, ov, n))
    if hang:
        assert _margins(doc, rep)[1] < -0.5 and _margins(doc, n)[1] < _margins(doc, rep)[1] - 0.5                    # 줄마다 제 접두 폭(「10.」 이 더 넓다)
    else:
        assert _margins(doc, rep) == _margins(doc, n) == (pytest.approx(3.0, abs=0.01), 0.0)                      # 내어쓰기 없음 · 첫 줄 자리(왼쪽 여백) 그대로
        assert OP.Measure(doc).slot_place(ov["templates"]["1"]["slots"]["4"])["firstMm"] == 0.0              # Enter 의 새 줄도 그 꼴
    m2 = OP.Measure(doc)
    assert M.match_targets(doc, ov, "1", 4) == [] and OC.pending(doc, ov, {"1"}) == [] and not OC.needs(doc, ov, n, m2)
    assert OC.settle(doc, ov, "1", 4, (), m2) == []                                                           # 두 번째는 바꿀 것이 없다


@pytest.mark.parametrize("align", ["center", "right", "justify"])
def test_gather_kept_level_follows_the_old_hanging_rep_and_converges(align):
    """취합의 넣은 뒤 정리 — 취합본의 줄이 있는 레벨(merge_retidy_api._kept_level)은 대표(취합본의 줄)가 ①② 를 갖추지 않았으면 넣은 줄에 대표의 모양만 건다
    (conform rules=False — `_full` = 대표가 넣은 줄 아님 · needs(대표)). 가운데 · 오른쪽 정렬 대표가 옛 확정 서식의 내어쓰기를 가지면 needs 가 참(unhang)이라 그 길로 오는데,
    대표의 모양을 그대로 받은 「10.」 은 둘째 줄이 제 글 시작이 아니어서 누를 때마다 다시 「다른 서식」 이었다(2026-11-22 검토). 넣은 줄은 대표의 「글 시작」 꼴을 제 접두 폭으로
    따르고(outline_conform._follow) 취합본의 대표는 그대로 — 한 번에 모인다. 「자리 맞춤」(settle) 뒤에는 둘 다 내어쓰기 없는 꼴이고 그 뒤의 정리도 모인다. 양쪽 정렬은 전처럼(rules 참)."""
    doc, ov, rep, n = _numbered_old_hang(align)
    free = align != "justify"
    before = (doc._ids[rep].get("paraPrIDRef"), doc._text(doc._ids[rep]))

    def press():   # merge_retidy_api 의 취합본 레벨 가지(대표 = 취합본의 줄 — r["same"] 에 없음)
        m = OP.Measure(doc)
        full = not OC.needs(doc, ov, rep, m)
        was = M.same(M.look(doc, ov, rep), M.look(doc, ov, n))
        if not was:
            OC.conform(doc, ov, n, M.rep_shape(doc, ov, rep), m, [], None, rules=full)
        return full, was

    assert press() == (not free, False)
    assert M.same(M.look(doc, ov, rep), M.look(doc, ov, n)), M.diff(M.look(doc, ov, rep), M.look(doc, ov, n))
    assert M.look(doc, ov, n).get("line2At") == M.AT_TEXT                                                     # 「10.」 도 제 글 시작(대표와 같은 규칙)
    assert _margins(doc, n)[1] < _margins(doc, rep)[1] - 0.5                                                  # 내어쓰기 = 제 접두 폭(대표보다 넓다)
    if free:
        assert (doc._ids[rep].get("paraPrIDRef"), doc._text(doc._ids[rep])) == before                        # 취합본의 대표는 안 바뀐다
    assert press() == (not free, True) and M.match_targets(doc, ov, "1", 4) == []                              # 두 번째는 바꿀 것이 없다
    if free:   # 「자리 맞춤」 — 대표 · 대표 갈래(이제 「10.」 도)의 옛 내어쓰기를 없앤다 → 그 뒤의 정리는 rules 참으로 모인다
        assert OC.pending(doc, ov, {"1"}) == [rep, n]
        OC.settle(doc, ov, "1", 4, (), OP.Measure(doc))
        assert _margins(doc, rep) == _margins(doc, n) == (pytest.approx(3.0, abs=0.01), 0.0)
        assert press() == (True, True) and OC.pending(doc, ov, {"1"}) == []


# ---------------------------------------------------------------- 접두의 줄 맞춤 값 = 대표 것(② §8-2 「줄 맞춤 값 — 접두는 대표 것」 · §8-8 ③ — 2026-11-23 사용자 「레터 앞 너비가 왜 조금씩 다르냐」)
def _fit(doc, pid, a, b, pct):
    """그 문단의 글 a..b 를 자간 pct 인 글자 모양으로(한 줄에 넣으려고 자간을 줄인 줄을 흉내 낸다) — 런을 그 자리에서 가른다."""
    import copy
    p = doc._ids[pid]
    doc._boundary(p, b)
    doc._boundary(p, a)
    for x, y, r in M._runs_pos(doc, p):
        if y > x and a <= x and y <= b:
            cp = copy.deepcopy(doc._defs["charPr"][r.get("charPrIDRef")])
            doc._set_chars(cp, {"spacingPct": pct})
            r.set("charPrIDRef", doc._add_def("charPr", cp))
    doc._drop_cache(p)


def _sp(doc, pid, i):
    """글 자리 i 의 한글 자간(%)."""
    return int(dict(M._fit_of(doc, M._cid_at(doc, doc._ids[pid], i))[1])["hangul"])


def _l4():
    """T1 L4 「  o …」 두 줄(대표 p6501 · p6504 — 같은 서식)."""
    doc = HwpxDoc(PLAN.read_bytes())
    doc.blocks()
    return doc, _mini("p6501", "p6504", level=4, letter="o"), "p6501", "p6504"


def test_a_tightened_line_gets_the_reps_prefix_fit_and_keeps_its_body_fit():
    """실제 작성본의 꼴(레터 앞 빈칸 6칸 · 레터부터 자간 −9): 접두 전체가 자간을 받으면 빈칸이 좁아진 만큼 레터가 왼쪽에 선다 — 확정 서식은 접두의 장평·자간을 대표 레터 런의 값으로,
    본문의 자간은 그 줄 것 그대로. 비교 값(갈래)은 처음부터 같다(줄 맞춤 값은 서식이 아니다) — 그래도 「자리 맞춤」 이 센다. 두 번째는 할 것 없음."""
    doc, ov, rep, pid = _l4()
    m = OP.Measure(doc)
    OC.settle(doc, ov, "1", 4, (), m)                                                              # 먼저 확정 서식(묶음 빈칸 · 둘째 줄 = 글 시작)
    assert OC.pending(doc, ov, {"1"}) == []
    lead, tok, gap, plen, text = M.parts(doc, ov, pid)
    _fit(doc, pid, 0, len(text), -9)                                                               # 줄 전체(레터 앞 빈칸까지) 자간 −9
    OP.align(doc, ov, pid, measure=OP.Measure(doc), force=True)                                    # 전의 확정 서식이 하던 대로 — 둘째 줄 = 제(좁아진) 글 시작
    m = OP.Measure(doc)
    assert M.same(M.look(doc, ov, pid), M.look(doc, ov, rep))                                      # 갈래는 같다(자간만 다른 줄)
    assert m.place(pid, "o")["letterMm"] < m.place(rep, "o")["letterMm"] - 0.1                     # 레터가 왼쪽에 서 있다
    assert OC.needs(doc, ov, pid, m) and OC.pending(doc, ov, {"1"}) == [pid]
    assert OC.place(doc, ov, pid, m) is True
    m = OP.Measure(doc)
    assert [_sp(doc, pid, i) for i in range(plen)] == [0] * plen                                   # 접두 = 대표 레터 런의 값
    assert [_sp(doc, pid, i) for i in range(plen, len(text))] == [-9] * (len(text) - plen)         # 본문은 제 값
    assert doc._text(doc._ids[pid]) == text
    a, b = m.place(pid, "o"), m.place(rep, "o")
    assert (a["letterMm"], a["textMm"], a["line2Mm"]) == pytest.approx((b["letterMm"], b["textMm"], b["line2Mm"]), abs=0.01)
    assert not OC.needs(doc, ov, pid, m) and OC.place(doc, ov, pid, m) is False and OC.pending(doc, ov, {"1"}) == []


def test_the_rep_itself_gets_its_letter_runs_fit_on_its_blanks_and_a_pattern_line_follows_a_given_base():
    """대표 자신: 레터 앞 빈칸의 런이 레터 런과 줄 맞춤 값이 다르면 레터 런의 값으로(대표의 레터 런이 그 레벨의 기준) · base 를 주면 그 줄이 본보기(넣은 줄끼리 맞추는 묶음의 대표)."""
    doc, ov, rep, pid = _l4()
    lead = M.parts(doc, ov, rep)[0]
    _fit(doc, rep, 0, len(lead), -10)                                                              # 대표: 레터 앞 빈칸만 −10 · 레터 0
    m = OP.Measure(doc)
    assert OC.needs(doc, ov, rep, m)
    OC.settle(doc, ov, "1", 4, (), m)
    assert [_sp(doc, rep, i) for i in range(M.parts(doc, ov, rep)[3])] == [0] * M.parts(doc, ov, rep)[3]
    assert OC.pending(doc, ov, {"1"}) == []
    plen, text = M.parts(doc, ov, rep)[3:]
    _fit(doc, rep, 0, plen, -5)                                                                    # 대표의 접두가 통째로 −5 면 그것이 기준
    OC.place(doc, ov, rep, OP.Measure(doc))                                                        # 좁아진 접두 폭으로 둘째 줄을 다시
    m = OP.Measure(doc)
    assert not OC.needs(doc, ov, rep, m) and OC.needs(doc, ov, pid, m)
    assert not OC.needs(doc, ov, pid, m, pid)                                                      # 제가 본보기면(묶음의 대표) 맞출 것이 없다
    OC.place(doc, ov, pid, m)
    assert [_sp(doc, pid, i) for i in range(M.parts(doc, ov, pid)[3])] == [-5] * M.parts(doc, ov, pid)[3]
    assert _sp(doc, pid, M.parts(doc, ov, pid)[3]) == 0                                            # 본문은 그대로


def test_conform_gives_the_reps_prefix_but_never_the_reps_body_fit():
    """맞추기(match_one): ① 줄의 레터에 걸려 있던 자간을 새 접두에 얹지 않는다(전에는 레터 앞 빈칸 전체로 번졌다) ② 본문 자간 0 인 줄이 대표의 본문 자간(−8)을 받지 않는다
    (전에는 대표의 레터 런이 0 이라 「대표와 같은 값」 으로 걸러져 대표의 본문 바탕 글자 모양을 그대로 받았다 — 2026-11-23 astra 재현) ③ 본문의 제 자간(−7)은 지킨다."""
    for own in (0, -7):
        doc, ov, rep, pid = _l4()
        rl, rplen, rtext = M.parts(doc, ov, rep)[0], *M.parts(doc, ov, rep)[3:]
        _fit(doc, rep, rplen, len(rtext), -8)                                                      # 대표: 접두 0 · 본문 −8
        lead, tok, gap, plen, text = M.parts(doc, ov, pid)
        _fit(doc, pid, len(lead), len(text), own or -4)                                            # 줄: 레터부터 끝까지 자간(레터 앞 빈칸은 0)
        if not own:
            _fit(doc, pid, plen, len(text), 0)                                                     # 본문만 0 으로 되돌림(레터 · 레터 뒤 빈칸은 −4)
        doc.format_para([pid], {"indentLeftMm": 7.0})                                              # 대표와 다른 서식(맞출 줄)
        OC.place(doc, ov, rep, OP.Measure(doc))                                                    # 대표를 확정 서식으로(묶음 빈칸 · 둘째 줄 = 글 시작)
        assert not M.same(M.look(doc, ov, pid), M.look(doc, ov, rep))
        OC.conform(doc, ov, pid, M.rep_shape(doc, ov, rep), OP.Measure(doc), [])
        lead2, tok2, gap2, plen2, text2 = M.parts(doc, ov, pid)
        assert text2[plen2:] == text[plen:]
        assert [_sp(doc, pid, i) for i in range(plen2)] == [0] * plen2, own                        # 접두 = 대표의 레터 런(자간 0)
        assert [_sp(doc, pid, i) for i in range(plen2, len(text2))] == [own] * (len(text2) - plen2), own   # 본문 = 제 값(대표의 −8 이 아니다)
        assert M.same(M.look(doc, ov, pid), M.look(doc, ov, rep)) and not OC.needs(doc, ov, pid, OP.Measure(doc))


def test_reletter_swaps_the_letter_in_place_and_does_not_spread_its_fit_over_the_blanks():
    """레터 바꾸기(넣은 뒤 정리 「⋅ → ▷」): 레터 글자만 제자리에서 — 레터부터 자간을 줄인 줄의 레터 앞 빈칸은 자간 0 그대로(전에는 접두를 런 하나로 다시 써서 빈칸까지 −9 가 됐다).
    그 뒤의 확정 서식(place)이 레터 런의 값도 대표 것으로 모은다."""
    from app import merge_retidy as MR
    doc, ov, rep, pid = _l4()
    lead, tok, gap, plen, text = M.parts(doc, ov, pid)
    _fit(doc, pid, len(lead), len(text), -9)                                                       # 레터부터 −9 · 레터 앞 빈칸 0
    rows = [{"tpl": "1", "level": 4, "was": "o", "now": "▷", "key": "▷", "lines": [rep, pid]}]
    assert MR.reletter(doc, ov, rows) == [rep, pid]
    assert doc._text(doc._ids[pid]) == lead + "▷" + text[len(lead) + 1:] and ov["lines"][pid]["letter"] == "▷" == ov["templates"]["1"]["slots"]["4"]["letter"]
    assert [_sp(doc, pid, i) for i in range(len(text))] == [0] * len(lead) + [-9] * (len(text) - len(lead))   # 런마다 제 값 그대로
    m = OP.Measure(doc)
    assert OC.needs(doc, ov, pid, m) and OC.place(doc, ov, pid, m)                                 # 레터 · 레터 뒤 빈칸의 −9 → 대표 것
    plen2 = M.parts(doc, ov, pid)[3]
    assert [_sp(doc, pid, i) for i in range(plen2)] == [0] * plen2 and _sp(doc, pid, plen2) == -9
    assert MR._swap(doc, ov, pid, "(가)") is False                                                  # 글자 수가 다른 레터는 제자리에서 못 바꾼다(전의 길)


def test_prefix_fit_leaves_held_lines_marked_lines_and_the_last_empty_run_alone(monkeypatch):
    """astra 2차(2026-11-23)가 재현한 것: ① 사람이 처리를 고른 줄(skip)은 대표 갈래여도 안 건드린다 ② 「①② 를 갖췄나」(fit=False)는 접두의 줄 맞춤 값을 안 본다(취합의 _full)
    ③ 접두만 고칠 때 문단 끝의 빈 런(마지막 줄 높이)을 지우지 않는다 ④ 넣은 줄끼리 맞춘 줄(RETIDY_DEEP)의 본보기는 그 묶음의 대표 — 「자리 맞춤」 이 레벨 대표의 값으로 되돌리지 않는다
    ⑤ 제 짝 표지가 든 줄은 레터를 안 바꾸고 문서도 안 바꾼다 — 한 줄도 못 바꾼 레벨은 슬롯의 레터도 그대로."""
    from app import merge_retidy as MR
    doc, ov, rep, pid = _l4()
    OC.settle(doc, ov, "1", 4, (), OP.Measure(doc))
    lead, tok, gap, plen, text = M.parts(doc, ov, pid)
    _fit(doc, pid, 0, len(text), -9)
    OP.align(doc, ov, pid, measure=OP.Measure(doc), force=True)
    assert OC.settle(doc, ov, "1", 4, (), OP.Measure(doc), skip=[pid]) == [] and _sp(doc, pid, 0) == -9          # ① 그대로
    m = OP.Measure(doc)
    assert OC.needs(doc, ov, pid, m) and not OC.needs(doc, ov, pid, m, fit=False)                                # ② ①② 는 갖췄다
    sl = ov["templates"]["1"]["slots"]["4"]
    sl[M.RETIDY_DEEP] = {"rep": pid, "lines": [pid]}                                                             # ④ 넣은 줄끼리 맞춘 줄 — 제가 그 묶음의 대표
    assert OC._fit_off(doc, ov, pid) is None and not OC.needs(doc, ov, pid, m) and OC.pending(doc, ov, {"1"}) == []
    del sl[M.RETIDY_DEEP]
    p = doc._ids[pid]
    end = p.makeelement(M.RUN, {"charPrIDRef": M._cid_at(doc, p, 0)})                                           # ③ 문단 끝의 빈 런
    p.append(end)
    assert OC.place(doc, ov, pid, OP.Measure(doc)) and _sp(doc, pid, 0) == 0 and _sp(doc, pid, plen) == -9
    assert end.getparent() is p and list(p.iterchildren(M.RUN))[-1] is end
    monkeypatch.setattr(MR, "_marked", lambda d, q: q == pid)                                                    # ⑤ 표지가 든 줄
    before, left = doc._text(p), []
    rows = [{"tpl": "1", "level": 4, "was": "o", "now": "▷", "key": "▷", "lines": [pid]}]
    assert MR.reletter(doc, ov, rows, left) == [] and doc._text(p) == before and [x["id"] for x in left] == [pid]
    assert ov["lines"][pid]["letter"] == "o" == sl["letter"] and sl["key"] == "o"                                # 한 줄도 못 바꿨다 — 슬롯도 그대로
    assert MR.reletter(doc, ov, [{**rows[0], "lines": [rep, pid]}], left) == [rep] and sl["letter"] == "▷" and ov["lines"][pid]["letter"] == "o"   # 일부만 — 슬롯은 새 레터 · 막힌 줄은 제 레터


def test_prefix_fit_ignores_a_stale_bundle_rep_and_a_run_it_cannot_split():
    """astra 3차(2026-11-23): ① 적어 둔 묶음(RETIDY_DEEP)의 대표가 다른 레벨로 옮겨졌거나 없어졌으면 그 줄에는 ③ 을 안 건다(옮겨진 대표의 값 · 레벨 대표의 값을 받지 않는다)
    ② 접두 끝에서 가를 수 없는 런(접두 끝이 hp:t 가 아닌 자식의 한가운데)이 있으면 그 런은 통째로 그대로 — 앞의 런만 고친다(가를 수 없는데 _boundary 를 부르면 그 런의 빈칸까지 바뀐다)."""
    doc, ov, rep, pid = _l4()
    OC.settle(doc, ov, "1", 4, (), OP.Measure(doc))
    text = M.parts(doc, ov, pid)[4]
    _fit(doc, pid, 0, len(text), -9)
    OP.align(doc, ov, pid, measure=OP.Measure(doc), force=True)
    sl = ov["templates"]["1"]["slots"]["4"]
    for stale in ({"rep": None, "lines": [pid]}, {"rep": "p5209", "lines": [pid]}, {"rep": "p-gone", "lines": [pid]}):   # 대표 없음(carry) · 다른 레벨의 줄 · 없어진 줄
        if stale["rep"] == "p5209":
            ov["lines"]["p5209"] = {"tpl": "1", "no": 1, "level": 5, "letter": "-", "key": "-", "role": "heading"}
        sl[M.RETIDY_DEEP] = stale
        assert OC._fit_off(doc, ov, pid) is None and not OC.place(doc, ov, pid, OP.Measure(doc)) and _sp(doc, pid, 0) == -9, stale
    del sl[M.RETIDY_DEEP]
    assert OC._fit_off(doc, ov, pid) is not None
    # ② 가를 수 없는 런: _splits 가 거짓이면 _fit_fix 는 경계를 만들지 않는다
    lead, tok, gap, plen, _ = M.parts(doc, ov, pid)
    p = doc._ids[pid]
    doc._boundary(p, 1)                                                                            # 첫 빈칸 | 나머지
    runs = [(a, b, r) for a, b, r in M._runs_pos(doc, p) if b > a]
    assert runs[0][:2] == (0, 1) and runs[1][0] == 1 and runs[1][1] > plen
    n = len(list(p.iterchildren(M.RUN)))
    real = OC._splits
    try:
        OC._splits = lambda d, r, a, at: False                                                     # 접두 끝에 걸친 런은 못 가른다고 치고
        assert OC._fit_off(doc, ov, pid) is not None and OC.place(doc, ov, pid, OP.Measure(doc))   # 첫 런(빈칸 하나)만 고칠 수 있다
    finally:
        OC._splits = real
    assert len(list(p.iterchildren(M.RUN))) == n and _sp(doc, pid, 0) == 0 and [_sp(doc, pid, i) for i in range(1, plen + 1)] == [-9] * plen   # 런을 가르지 않았고 걸친 런은 그대로


def test_conform_takes_body_runs_that_differ_only_in_fit_as_the_same_base():
    """줄 정리가 문단의 한 줄에만 자간을 걸면 같은 바탕의 본문이 글자 모양 id 가 다른 런 둘이 된다(「−9%」 · 「−5%」) — 맞출 때 둘 다 대표의 본문 바탕을 받고(전에는 첫 런과 id 가 같은 런만:
    뒤쪽 런이 옛 크기로 남았다 — 2026-11-23 astra 재현) 런마다 제 자간은 그대로. 따로 모양을 준 런(굵게)은 전처럼 그대로."""
    doc, ov, rep, pid = _l4()
    OC.place(doc, ov, rep, OP.Measure(doc))
    lead, tok, gap, plen, text = M.parts(doc, ov, pid)
    n = len(text)
    mid, last = plen + 3, n - 2
    doc.format_chars(pid, plen, n, {"sizePt": 9})                                                  # 본문 9pt(대표와 다른 바탕)
    _fit(doc, pid, plen, mid, -9)                                                                  # 같은 바탕 · 자간만 다른 런 둘
    _fit(doc, pid, mid, last, -5)
    doc.format_chars(pid, last, n, {"bold": not M.look(doc, ov, rep)["bold"]})                     # 따로 모양을 준 런
    size = lambda q, i: doc._char_summary(doc._defs["charPr"][M._cid_at(doc, doc._ids[q], i)])["sizePt"]  # noqa: E731
    want = size(rep, M.parts(doc, ov, rep)[3])
    assert size(pid, plen) == size(pid, mid) == 9 != want
    OC.conform(doc, ov, pid, M.rep_shape(doc, ov, rep), OP.Measure(doc), [])
    plen2 = M.parts(doc, ov, pid)[3]
    d = plen2 - plen
    assert size(pid, plen2) == size(pid, mid + d) == want                                          # 두 런 모두 대표의 바탕
    assert (_sp(doc, pid, plen2), _sp(doc, pid, mid + d - 1), _sp(doc, pid, mid + d), _sp(doc, pid, last + d - 1)) == (-9, -9, -5, -5)   # 자간은 런마다 제 값
    assert size(pid, last + d) == 9                                                                # 따로 모양을 준 런은 그대로
