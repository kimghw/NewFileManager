"""줄 정리(spec/spec_줄정리.md) — 규칙 · 갈림 찾기 · 문단 하나의 시도와 확인 · 장평 바꾸기 · 계획 길(가짜 한글 조판)."""
from pathlib import Path

import pytest

from app import line_tidy as LT
from app import line_tidy_api as A

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
R = dict(LT.DEFAULTS)


def _spans(*lines):
    out, at = [], 0
    for ln in lines:
        out.append((at, at + len(ln)))
        at += len(ln)
    return "".join(lines), out


def _width(text):   # 글자 1 · 빈칸 0.5(한글의 0.5em 빈칸) — 모형 대신
    return lambda a, b: sum(0.5 if text[i].isspace() else 1.0 for i in range(a, b))


def _para(*lines, rules=R):
    text, spans = _spans(*lines)
    return LT.Para(0, text, spans, rules, _width(text), lambda a, b: (100, 100)), text


# ---------------------------------------------------------------- 규칙
def test_rules_clean_and_defaults():
    assert LT.clean_rules({}) == LT.DEFAULTS
    assert LT.clean_rules({"pull": 3})["pull"] == 3
    with pytest.raises(ValueError, match="당기기"):
        LT.clean_rules({"pull": 9})
    with pytest.raises(ValueError, match="모르는 규칙"):
        LT.clean_rules({"zzz": 1})
    with pytest.raises(ValueError, match="정수"):
        LT.clean_rules({"pull": 1.5})
    assert LT.rules_of({"pull": 99, "last": 1, "zzz": 3}) == {**LT.DEFAULTS, "last": 1}   # 범위 밖 · 모르는 키는 기본값


def test_rules_store_roundtrip():
    """규칙 저장(env NFM_LINE_TIDY — conftest 가 임시 파일로) — 기본값과 다른 키만 적고, 지우면 기본값."""
    assert A.rules_get()["rules"] == LT.DEFAULTS
    got = A.rules_put({"rules": {"minRatio": 90, "chain": 2}})
    assert got["rules"]["minRatio"] == 90 and got["rules"]["chain"] == 2 and "장평 90~110%" in got["text"]
    assert A.rules() == {**LT.DEFAULTS, "minRatio": 90, "chain": 2}
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        A.rules_put({"rules": {"maxRatio": 300}})
    assert e.value.status_code == 400 and "장평 상한" in e.value.detail
    assert A.rules_reset()["rules"] == LT.DEFAULTS


# ---------------------------------------------------------------- 갈림 찾기
def test_issue_kinds():
    t, sp = _spans("등 '선내 데이터 가", "이드라인' 최종 제정")
    it = LT.issue_at(t, sp, 0, R)
    assert it["kind"] == "push" and (it["a"], it["b"]) == (1, 4)   # 「가 / 이드라인」 — 줄 끝 1자 · 다음 줄 4자 → 밀기
    t, sp = _spans("CBM(예측", "정비) AI 서비스")
    assert LT.issue_at(t, sp, 0, R)["kind"] == "pull" and LT.issue_at(t, sp, 0, R)["b"] == 2   # 괄호는 안 셈
    t, sp = _spans("데이터 ", "베이스 구축")
    assert LT.issue_at(t, sp, 0, R) is None   # 빈칸에서 나뉨
    t, sp = _spans("통합 데이터", "베이스 구축")
    assert LT.issue_at(t, sp, 0, R) is None   # 3자 / 3자 — 규칙 밖
    t, sp = _spans("가나다\n", "라마")
    assert LT.issue_at(t, sp, 0, R) is None and LT.last_issue(t, sp, R) is None   # 강제 줄 바꿈
    t, sp = _spans("가나다라마바사 최종 ", "제정")
    assert LT.last_issue(t, sp, R)["kind"] == "last"
    assert LT.last_issue(t, sp, {**R, "last": 0}) is None


def test_protect_prefix():
    assert LT.protect("  - 실해역 데이터") == 4
    assert LT.protect("ㅇ 표준형") == 2
    assert LT.protect("가나다라마바사 글") == 0   # 긴 첫 토막은 레터가 아님


# ---------------------------------------------------------------- 문단 하나 — 시도와 확인
def test_pull_chain_to_one_line():
    """「예지보 / 전 가동」 — 「전」 1자를 당기면 「가동」 2자가 남는다 → 합 3자 ≤ 연속 3자 → 한 번에 마지막 줄까지."""
    j, t = _para("가" * 28 + " 예지보", "전 가동")
    op = j.trial
    assert op["kind"] == "pull+last" and op["b"] == 3 and op["re"] == len(t) and op["pct"] == 90   # 31.5 / 35
    j.observe([(0, len(t))])   # 한글: 한 줄
    assert j.trial is None and j.finish() == [op]


def test_pull_chain_limit_pulls_once():
    """「예지 / 보전 가동」 — 당길 조각 2자 + 남을 마지막 줄 2자 = 4자 > 3 → 한 번만(「보전」 만) · 남은 것은 「연속 당기기 한도」."""
    j, t = _para("가" * 28 + " 예지", "보전 가동")
    assert j.trial["kind"] == "pull" and j.trial["re"] == t.index(" 가동")
    assert any(x["why"] == "chain" for x in j.left)


def test_pull_steps_down_until_it_fits():
    j, t = _para("가" * 28 + " 예지보", "전 가동")
    first = j.trial["pct"]
    j.observe(j.spans)   # 한글: 그대로(아직 안 올라옴) → 1% 더
    assert j.trial["pct"] == first - 1
    j.observe([(0, len(t))])
    assert [o["pct"] for o in j.finish()] == [first - 1]


def test_pull_gives_up_at_floor():
    j, t = _para("가" * 28 + " 예지보", "전 가동", rules={**R, "minRatio": 90})
    assert j.trial["pct"] == 90
    j.observe(j.spans)   # 89 는 하한 밑 → 그 자리는 그대로
    assert j.trial is None and j.finish() == [] and j.left[-1]["why"] == "limit"


def test_push_tail_to_next_line():
    j, t = _para("가" * 26 + " 데이터 가", "이드라인 최종 제정")
    op = j.trial
    cut = t.index("가이드")
    assert op["kind"] == "push" and op["re"] == cut and op["pct"] > 100
    j.observe([(0, cut), (cut, len(t))])   # 한글: 「가」 가 다음 줄로
    assert j.finish() == [op]


def test_short_line_left_alone():
    j, _ = _para("기", "술")
    assert j.trial is None and j.left[0]["why"] == "short"


def test_no_better_is_reverted():
    """고친 뒤에도 규칙에 걸린 자리 수가 줄지 않으면(밀기가 아래에 새 갈림을 만들고 못 고침) 그 문단은 고치지 않는다."""
    j, t = _para("가" * 26 + " 데이터 가", "이드라인 최종 제정 나머지 글")
    cut = t.index("가이드")
    k = t.index("정 나머지")
    j.observe([(0, cut), (cut, k), (k, len(t))])   # 밀었더니 아래가 「…최종 제 / 정 나머지」 로 새로 갈림 — 그 자리의 당기기는 한글에서 끝내 안 맞음
    assert j.ops   # 밀기는 맞았다
    while j.trial:   # 아래 갈림의 시도는 계속 실패
        j.observe(j.spans)
    assert j.finish() == [] and any(x["why"] == "worse" for x in j.left)


# ---------------------------------------------------------------- 장평 바꾸기(실제 문서)
def test_scale_ratio_on_document():
    from app.hwpx_doc import HwpxDoc
    doc = HwpxDoc(PLAN.read_bytes())
    p = next(p for sec in doc._sections for p in sec.iter(A.P_TAG) if len(doc._text(p)) > 20 and not doc._has_object(p))
    text = doc._text(p)
    n = LT.scale_ratio(doc, p, 2, 12, 95)
    assert n >= 1 and doc._text(p) == text   # 글은 그대로
    from app.heading_extract import _cid_at, run_ranges
    rr = run_ranges(doc, p)
    ratio = lambda i: int(doc._defs["charPr"][_cid_at(rr, i, "0")].find(LT._hh("ratio")).get("hangul"))  # noqa: E731
    base = ratio(0)
    assert ratio(2) == round(base * 0.95) and ratio(11) == round(base * 0.95) and ratio(12) == base
    again = HwpxDoc(doc.save())   # 저장한 바이트를 다시 연다
    assert any(c.find(LT._hh("ratio")).get("hangul") == str(round(base * 0.95)) for c in again._defs["charPr"].values() if c.find(LT._hh("ratio")) is not None)


# ---------------------------------------------------------------- 끝점 — 재기 → 반영 → 실행 취소(가짜 한글 조판 · 진짜 서버 세션)
def test_plan_apply_undo_api(monkeypatch):
    """문서의 한 문단을 가짜 한글이 「…낱말의 앞 / 끝 1자」 로 나눈다(장평을 줄인 글자 모양이 걸리면 한 줄) → 계획 1문단 · 반영(실행 취소 1) · 기록 · 실행 취소로 되돌아옴."""
    import re

    from fastapi.testclient import TestClient
    from lxml import etree

    from app import server
    from app.hwpx_doc import HwpxDoc
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    c = TestClient(server.app)
    d = c.post("/api/docs?new=1", files={"file": (PLAN.name, PLAN.read_bytes())}).json()["docId"]
    s = server._sess(d)
    ps = A._paras(s.doc)
    pick = None
    for i, p in enumerate(ps):   # 줄 하나로 나눌 수 있는 문단 — 끝에서 둘째 낱말의 마지막 글자 앞에서 나누면 「다음 줄 조각 1자」
        t = s.doc._text(p)
        m = list(re.finditer(r"[가-힣]{3,}", t))
        if s.doc._rev.get(p) and not s.doc._has_object(p) and len(t) > 30 and len(m) >= 2 and LT.letters(t[:m[-2].end() - 1]) >= 12 and t[m[-2].end():m[-2].end() + 1] == " ":
            pick, cut = i, m[-2].end() - 1
            break
    assert pick is not None
    text = s.doc._text(ps[pick])

    def ratios(D, q):   # 런마다 한글 장평(%)
        out = []
        for r in q.iterchildren(HP + "run"):
            cp = D._defs["charPr"].get(r.get("charPrIDRef"))
            e = cp.find(LT._hh("ratio")) if cp is not None else None
            out.append(int(e.get("hangul", 100)) if e is not None else 100)
        return out
    orig = set(ratios(s.doc, ps[pick]))

    def layout(b):
        D = HwpxDoc(b)
        q = A._paras(D)[pick]
        small = any(x not in orig for x in ratios(D, q))   # 장평을 바꾼 런이 있으면 한 줄로
        for la in q.findall(HP + "linesegarray"):   # 양식이 지닌 캐시는 갈아 끼운다
            q.remove(la)
        arr = etree.SubElement(q, HP + "linesegarray")
        etree.SubElement(arr, HP + "lineseg", {"textpos": "0"})
        if not small:
            etree.SubElement(arr, HP + "lineseg", {"textpos": str(cut)})
        D._mark(D._name_of[q.getroottree().getroot()])
        return D.save()
    monkeypatch.setattr(A, "_hwp_ok", lambda: True)   # 줄 정리의 문만(pdf_render.available 을 바꾸면 서버의 검증 PDF 가 진짜 한글을 띄운다)
    monkeypatch.setattr(A, "_layout", layout)
    r = c.post(f"/api/docs/{d}/line-tidy/plan").json()
    assert len(r["items"]) == 1 and r["items"][0]["text"] == text and r["items"][0]["ops"][0]["kind"] in ("pull", "pull+last"), r
    assert c.post(f"/api/docs/{d}/line-tidy/apply", json={"planId": "nope"}).status_code == 409
    rev0, undo0 = s.rev, len(s.undo)
    a = c.post(f"/api/docs/{d}/line-tidy/apply", json={"planId": r["planId"]}).json()
    assert a["done"] == [r["items"][0]["id"]] and s.rev == rev0 + 1 and len(s.undo) == undo0 + 1
    p = ps[pick]
    assert s.doc._text(p) == text and any(x not in orig for x in ratios(s.doc, p))
    g = c.get(f"/api/docs/{d}/line-tidy").json()
    assert g["applied"]["planId"] == r["planId"] and g["applied"]["paras"] == 1 and g["facts"]["applied"]["paras"] == 1
    assert c.post(f"/api/docs/{d}/line-tidy/apply", json={"planId": r["planId"]}).status_code == 409   # 잰 뒤 문서가 바뀜(반영으로 rev 가 올랐다) — 다시 잰다
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    s2 = server._sess(d)
    assert set(ratios(s2.doc, A._paras(s2.doc)[pick])) <= orig


# ---------------------------------------------------------------- 계획 길(가짜 한글 조판)
def test_plan_bytes_with_fake_layout():
    """plan_bytes — 한글 대신 「줄 시작 자리를 정해 주는」 가짜 조판: 처음엔 갈린 줄 · 장평을 바꾼 사본엔 한 줄. 고친 문단 하나 · 배율은 처음 문단 기준."""
    from lxml import etree

    from app.hwpx_doc import HwpxDoc
    doc = HwpxDoc(PLAN.read_bytes())
    p = next(p for sec in doc._sections for p in sec.iter(A.P_TAG) if not doc._has_object(p) and len(doc._text(p)) > 12)
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    runs = list(p.iterchildren(HP + "run"))
    for r in runs[1:]:
        p.remove(r)
    for c in list(runs[0]):
        runs[0].remove(c)
    etree.SubElement(runs[0], HP + "t").text = "가" * 28 + " 예지보전 가동"
    doc._touch(p)   # 고쳤다고 표시해야 save() 가 그 부분을 다시 쓴다
    data = doc.save()
    D0 = HwpxDoc(data)
    target = [i for i, q in enumerate(A._paras(D0)) if D0._text(q).startswith("가" * 28)]
    assert len(target) == 1
    calls = []

    def layout(b):
        d = HwpxDoc(b)
        q = A._paras(d)[target[0]]
        for la in q.findall(HP + "linesegarray"):
            q.remove(la)
        arr = etree.SubElement(q, HP + "linesegarray")
        etree.SubElement(arr, HP + "lineseg", {"textpos": "0"})
        if not calls:   # 처음 문서 — 「…예지보 / 전 가동」
            etree.SubElement(arr, HP + "lineseg", {"textpos": str(len("가" * 28 + " 예지보"))})
        calls.append(1)
        d._mark(d._name_of[q.getroottree().getroot()])
        return d.save()
    res = A.plan_bytes(data, R, lambda i, q, t: i == target[0], layout)
    assert len(calls) == 2 and res["rounds"] == 1
    (it,) = res["items"]
    assert it["ops"][0]["kind"] == "pull+last" and it["after"] == ["가" * 28 + " 예지보전 가동"]
    assert res["counts"]["fixed"] == 1 and res["counts"]["chain"] == 1
