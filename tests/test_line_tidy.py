"""줄 정리(spec/spec_줄정리.md) — 규칙 · 갈림 찾기 · 문단 하나의 시도와 확인 · 자간 바꾸기(전의 장평 되돌리기) · 계획 길(가짜 한글 조판)."""
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
    return LT.Para(0, text, spans, rules, _width(text), lambda a, b: (0, 0)), text


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
    got = A.rules_put({"rules": {"minSpace": -10, "chain": 2}})
    assert got["rules"]["minSpace"] == -10 and got["rules"]["chain"] == 2 and "자간 -10~+10%" in got["text"]
    assert A.rules() == {**LT.DEFAULTS, "minSpace": -10, "chain": 2}
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        A.rules_put({"rules": {"maxSpace": 300}})
    assert e.value.status_code == 400 and "자간 상한" in e.value.detail
    with pytest.raises(HTTPException) as e:   # 전의 장평 규칙 키는 이제 없다(2026-11-23 「자간으로 당기기」)
        A.rules_put({"rules": {"minRatio": 90}})
    assert e.value.status_code == 400
    assert LT.rules_of({"minRatio": 90, "maxRatio": 120}) == LT.DEFAULTS   # 저장돼 있던 옛 키는 버린다
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


def test_paren_not_counted():
    """「… 공식 업무협 / 약(MOU) 체결」 — 괄호 안은 빼고 센다(2026-11-23 사용자 "() 빼고 계산해줘"): 「약(MOU)」 = 1자 → 당기기 · 「체결」 2자와 합 3자 → 마지막 줄까지."""
    t, sp = _spans("가" * 40 + " 업무협", "약(MOU) 체결")
    it = LT.issue_at(t, sp, 0, R)
    assert it["kind"] == "pull" and (it["a"], it["b"]) == (3, 1)
    assert LT.count(t, *sp[1]) == 3 and LT.letters(t[sp[1][0]:sp[1][1]]) == 6
    assert LT.issue_at(*_spans("가" * 40 + " 업무협", "약(MOUA) 체결"), 0, {**R, "pull": 1})["b"] == 1   # 괄호 안 글자 수와 무관
    t, sp = _spans("가" * 40 + " 업무협약(M", "OU) 체결")   # 줄을 넘어 짝지어진 괄호는 빼지 않음
    assert LT.count(t, sp[1][0], t.index(" 체결")) == 2 and LT.count(t, *sp[1]) == 4
    t, sp = _spans("1. 보호구(보안경, 안전모 ", "등) 착용")
    assert LT.count(t, *sp[1]) == 3 and LT.last_issue(t, sp, R) is None   # 「등) 착용」 — 윗줄에서 연 괄호
    assert LT.count("(MOU)", 0, 5) == 3   # 괄호 밖에 글자가 없으면 모두
    assert LT.count("가나(다", 0, 4) == 3   # 짝 없는 괄호는 안 봄
    j, t = _para("가" * 45 + " 업무협", "약(MOU) 체결")
    assert j.trial["kind"] == "pull+last" and j.trial["b"] == 3 and j.trial["re"] == len(t)


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
    j, t = _para("가" * 28 + " 예지보", "전 가동", rules={**R, "minSpace": -10})
    assert j.trial["pct"] == 90
    j.observe(j.spans)   # 89 는 하한 밑 → 그 자리는 그대로
    assert j.trial is None and j.finish() == [] and j.left[-1]["why"] == "limit"


def test_limits_follow_current_spacing():
    """한도는 **지금 자간** 에서 센다 — 이미 −10% 로 좁혀 둔 글은 하한 −15% 까지 5%p 만 더(배율 85/90 → 95%) · 하한에 있는 글은 더 줄이지 않는다."""
    text, spans = _spans("가" * 28 + " 예지보", "전 가동")
    j = LT.Para(0, text, spans, R, _width(text), lambda a, b: (-10, -10))
    assert j.trial is None and j.left[-1]["why"] == "limit"   # 어림 90% < 하한 94%(남은 자리를 넣어도 92%)
    j = LT.Para(0, text, spans, {**R, "minSpace": -25}, _width(text), lambda a, b: (-10, -10))
    assert j.trial["pct"] == 90 and j.trial["lo"] == 82   # 83% 까지(90 × 0.83 − 100 = −25.3 → 적히는 자간 −25%) → lo = 82
    j = LT.Para(0, text, spans, R, _width(text), lambda a, b: (-15, -15))
    assert j.trial is None and j.left[-1]["why"] == "limit"
    assert (LT.spacing_for(0, 96), LT.spacing_for(-5, 96), LT.spacing_for(-5, 104), LT.spacing_for(-45, 50)) == (-4, -9, -1, -50)


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


def _cell(*lines, rules=R):
    text, spans = _spans(*lines)
    return LT.Para(0, text, spans, rules, _width(text), lambda a, b: (0, 0), cell=True), text


def test_cell_short_word():
    """표 칸(2026-11-23 사용자 "테이블의 글자는 2자 또는 3자에서 1자 또는 2자가 넘어 가면 글자 장평 조절해서 붙어 있게"): 낱말 = 가운뎃점 · 괄호 사이의 토막 ·
    짧은 줄이어도(「고칠 줄의 길이」 밖) 당긴다 · 닫는 괄호까지 당긴다."""
    t, sp = _spans("화상·수침·조류", "계")
    assert LT.issue_at(t, sp, 0, R) == {"kind": "pull", "line": 0, "a": 6, "b": 1, "cut": 0, "at": len(t)}   # 본문 셈(빈칸까지)
    it = LT.issue_at(t, sp, 0, R, cell=True)
    assert (it["kind"], it["a"], it["b"], it["cell"]) == ("pull", 2, 1, True)
    t, sp = _spans("연속(트리", "거·이벤", "트)")
    assert LT.issue_at(t, sp, 0, R) is None   # 본문 셈 — 「거·이벤」 3자
    it = LT.issue_at(t, sp, 0, R, cell=True)
    assert (it["a"], it["b"], t[sp[1][0]:it["at"]]) == (2, 1, "거·")
    assert t[sp[2][0]:LT.issue_at(t, sp, 1, R, cell=True)["at"]] == "트)"
    assert "cell" not in LT.issue_at(*_spans("데이터베", "이스"), 0, R, cell=True)   # 6자 낱말 — 표 칸 규칙 밖(본문 규칙 · 「고칠 줄의 길이」 를 따른다)
    assert LT.issue_at(*_spans("화상·수침·조류", "계"), 0, {**R, "cellWord": 0}, cell=True).get("cell") is None   # 0 = 안 함
    j, t = _cell("화상·수침·조류", "계")
    assert j.trial["kind"] == "pull" and j.trial["re"] == len(t)   # 6자 줄 — 「고칠 줄의 길이」 8자보다 짧아도
    j, t = _para("화상·수침·조류", "계")
    assert j.trial is None and j.left[0]["why"] == "short"   # 표 칸이 아니면 전과 같다


def test_cell_no_new_lone_split():
    """표 칸 — 「기 / 반」 을 당겼더니 「예측 / 정비」 가 「예측정 / 비」 로 밀렸다(한 글자 갈림을 하나 고쳐 하나 만듦) → 나아지지 않음 · 되돌림."""
    j, t = _cell("가나다 AI 기", "반 선박 예측", "정비 서비스")
    assert j.trial["kind"] == "pull" and j.trial["it"]["cell"]
    a = t.index("선박")
    j.observe([(0, a), (a, t.index("비 서")), (t.index("비 서"), len(t))])   # 한글: 「…기반 / 선박 예측정 / 비 서비스」
    assert j.finish() == [] and j.left[-1]["why"] == "worse" and j.spans == j.spans0
    assert LT.lone(t, j.spans0) == {t.index("반 선")}
    j, t = _cell("가나다 AI 기", "반 선박 예측", "정비 서비스")
    j.observe([(0, a), (a, t.index("정비")), (t.index("정비"), len(t))])   # 「예측 / 정비」 그대로 → 한 글자 갈림 1 → 0
    assert [o["kind"] for o in j.finish()] == ["pull"]


def test_floor_try_when_guess_is_rough():
    """어림이 하한 밑이어도 줄 끝에 남았을 수 있는 자리(다음 줄 첫 글자 폭)만큼 보면 닿을 때는 하한에서 한 번 재어 본다 — 안 되면 「자간 한도」."""
    j, t = _cell("연속(트리", "거")   # 어림 5/6 = 83% < 85 · 남은 자리를 넣으면 6/6 → 하한 85% 에서 시도
    assert j.trial["pct"] == 85
    j.observe(j.spans)   # 한글: 안 올라옴 → 하한 밑은 안 함
    assert j.trial is None and j.left[-1]["why"] == "limit"
    j, t = _cell("기", "술")   # 1/2 = 50% · 남은 자리를 넣어도 2/2 → 시도(표 칸 낱말)
    assert j.trial["pct"] == 85
    j, t = _cell("가나다라마바사아", "자차카", rules={**R, "cellWord": 6, "pull": 3})   # 8/11 · 9/11 = 81% < 85 → 바로 「자간 한도」
    assert j.trial is None and j.left[-1]["why"] == "limit"


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


# ---------------------------------------------------------------- 자간 바꾸기 · 전의 장평 되돌리기(실제 문서)
def _vals(doc, p, tag, default):
    """글자 자리마다 그 글자 모양의 한글 값(tag = ratio | spacing)."""
    from app.heading_extract import _cid_at, run_ranges
    rr = run_ranges(doc, p)

    def at(i):
        e = doc._defs["charPr"][_cid_at(rr, i, "0")].find(LT._hh(tag))
        return int(e.get("hangul", default)) if e is not None else default
    return at


def test_scale_spacing_on_document():
    """자간으로 — 그 범위의 자간만 (100 + 지금) × 배율 − 100 으로 · 장평과 글은 그대로 · 저장한 바이트에도 남는다."""
    from app.hwpx_doc import HwpxDoc
    doc = HwpxDoc(PLAN.read_bytes())
    p = next(p for sec in doc._sections for p in sec.iter(A.P_TAG) if len(doc._text(p)) > 20 and not doc._has_object(p))
    text = doc._text(p)
    sp0, ra0 = _vals(doc, p, "spacing", 0), _vals(doc, p, "ratio", 100)
    base, ratio = [sp0(i) for i in range(13)], [ra0(i) for i in range(13)]
    n = LT.scale_spacing(doc, p, 2, 12, 95)
    assert n >= 1 and doc._text(p) == text   # 글은 그대로
    sp, ra = _vals(doc, p, "spacing", 0), _vals(doc, p, "ratio", 100)
    assert [sp(i) for i in range(2, 12)] == [LT.spacing_for(base[i], 95) for i in range(2, 12)] and sp(2) < base[2]
    assert (sp(0), sp(12)) == (base[0], base[12]) and [ra(i) for i in range(13)] == ratio   # 범위 밖 · 장평은 그대로
    again = HwpxDoc(doc.save())   # 저장한 바이트를 다시 연다
    want = str(LT.spacing_for(base[2], 95))
    assert any(c.find(LT._hh("spacing")).get("hangul") == want for c in again._defs["charPr"].values() if c.find(LT._hh("spacing")) is not None)


def _fix_case():
    """양식의 한 문단 + 「전의 줄 정리가 하던 것」(범위의 장평 × pct%) — 범위 뒤에 같은 런의 나머지가 남는다."""
    from app.hwpx_doc import HwpxDoc
    doc = HwpxDoc(PLAN.read_bytes())
    p = next(p for sec in doc._sections for p in sec.iter(A.P_TAG) if len(doc._text(p)) > 20 and not doc._has_object(p))
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    ids = lambda: [r.get("charPrIDRef") for r in p.iterchildren(HP + "run")]  # noqa: E731
    old = lambda a, b, pct: LT._rescale(doc, p, a, b, "ratio", 100, lambda cur: round(cur * pct / 100))  # noqa: E731
    return doc, p, ids, old


def test_ratio_proof_restores_old_fix():
    """전에 장평으로 고친 줄(② §9) — 장평 × 96% 로 바꿔 둔 범위: 양 끝이 런 경계 · 되돌린 정의가 문서에 있음 · 바로 뒤 런이 그 정의 → 처음 글자 모양(같은 정의)으로 돌아온다."""
    doc, p, ids, old = _fix_case()
    before = ids()
    base = [_vals(doc, p, "ratio", 100)(i) for i in range(13)]
    old(2, 12, 96)
    assert _vals(doc, p, "ratio", 100)(2) == round(base[2] * 0.96)
    proof = LT.ratio_proof(doc, p, [(2, 12, 96)])
    assert proof and ids() != before   # 근거를 세는 것은 문서를 안 바꾼다
    assert LT.restore(doc, p, proof) >= 1
    assert [_vals(doc, p, "ratio", 100)(i) for i in range(13)] == base and ids() == before   # 나눈 런도 다시 합쳐진다
    assert LT._ratio_before(96, 96) == [100] and LT._ratio_before(91, 96) == [95] and LT._ratio_before(100, 96) == [104] and LT._ratio_before(50, 110) == []


def test_ratio_proof_needs_evidence_in_the_document():
    """기록은 반영을 「실행 취소」 해도 남는다 — 그 장평이 지금 문서에 있다는 근거가 없으면 되돌리지 않는다(astra 2026-11-23 의 반례들)."""
    import copy
    doc, p, ids, old = _fix_case()
    before = ids()
    assert LT.ratio_proof(doc, p, [(2, 12, 96)]) is None and ids() == before   # ① 실행 취소한 문서 — 범위의 끝이 런 경계가 아니다(100 → 104 로 넓히지 않는다)
    for cid in set(before):   # ② 나머지가 같고 장평만 ÷ 96% 인 정의가 **이미 있어도** — 실행 취소한 문서의 장평을 그 정의로 바꾸지 않는다
        c = copy.deepcopy(doc._defs["charPr"][cid])
        e = c.find(LT._hh("ratio"))
        for x in LT.LANGS:
            e.set(x, str(LT._ratio_before(int(e.get(x) or 100), 96)[0]))
        assert doc._add_def("charPr", c) not in before
    assert LT.ratio_proof(doc, p, [(2, 12, 96)]) is None
    doc._boundary(p, 12)
    doc._boundary(p, 2)   # 런이 그 자리에서 나뉘어 있어도(같은 글자 모양) — 옆 런이 104% 정의를 쓰지 않으니 근거가 아니다
    assert LT.ratio_proof(doc, p, [(2, 12, 96)]) is None and LT.ratio_proof(doc, p, [(2, 12, 96)], neighbor=False) is not None   # 옆 런 근거를 빼면 통과한다 — 그래서 그 길은 한글 줄로 먼저 본다
    doc._tidy(p)
    old(2, 12, 96)
    LT._rescale(doc, p, 6, 9, "ratio", 100, lambda cur: 77)   # ③ 그 뒤 범위의 일부를 다른 편집이 바꿨다 — 런 하나라도 아니면 근거 없음
    assert LT.ratio_proof(doc, p, [(2, 12, 96)]) is None
    doc, p, ids, old = _fix_case()
    old(2, 12, 96)
    old(12, 20, 96)   # ④ 맞닿은 같은 배율의 범위 둘(한 런으로 합쳐져 있다) — 합쳐서 본다
    assert LT.ratio_proof(doc, p, [(12, 20, 96), (2, 12, 96)]) is not None
    assert LT.ratio_proof(doc, p, [(2, 12, 96), (10, 20, 96)]) is None   # ⑤ 겹친 범위 — 되돌릴 차례를 알 수 없다


def test_ratio_proof_finds_mixed_language_ratio():
    """한글 87% · 영문 88% 처럼 언어마다 다른 장평(× 96% 면 둘 다 84%) — 같은 값이라고 같은 처음 값으로 넘겨짚지 않고, 문서에 있는 정의에서 찾는다."""
    import copy
    doc, p, ids, old = _fix_case()
    src = doc._defs["charPr"][ids()[0]]
    c = copy.deepcopy(src)
    c.find(LT._hh("ratio")).set("hangul", "87")
    c.find(LT._hh("ratio")).set("latin", "88")
    for x in LT.LANGS[2:]:
        c.find(LT._hh("ratio")).set(x, "87")
    mixed = doc._add_def("charPr", c)
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    for r in p.iterchildren(HP + "run"):
        r.set("charPrIDRef", mixed)
    old(2, 12, 96)
    e = doc._defs["charPr"][[r.get("charPrIDRef") for r in p.iterchildren(HP + "run")][1]].find(LT._hh("ratio"))
    assert (e.get("hangul"), e.get("latin")) == ("84", "84")
    proof = LT.ratio_proof(doc, p, [(2, 12, 96)])
    assert proof and {w for _, w in proof} == {mixed}


def test_spacing_limits_use_the_written_value():
    """한도는 **적힐 자간**(정수)으로 센다 — 식으로 세면 되는 값을 버린다: 지금 −10% · 하한 −15% 에서 94% 는 −15% 가 된다(식은 95%) · 지금 +5% · 상한 +10% 에서 105% 는 +10%(식은 104%)."""
    assert LT.pct_limit(-10, -15, up=False) == 94 and LT.spacing_for(-10, 94) == -15 and LT.spacing_for(-10, 93) < -15
    assert LT.pct_limit(5, 10, up=True) == 105 and LT.spacing_for(5, 105) == 10 and LT.spacing_for(5, 106) > 10
    assert LT.pct_limit(-20, -15, up=False) == 100 and LT.pct_limit(12, 10, up=True) == 100   # 이미 한도 밖 — 그 방향으로는 안 바꾼다
    assert LT.pct_limit(0, -15, up=False) == 85 and LT.pct_limit(0, 10, up=True) == 110


def test_ops_in_one_paragraph_do_not_overlap():
    """밀기가 어림보다 한 칸 더 밀리면 새 줄이 앞 범위 안에서 시작한다 — 다음 고침의 범위는 앞 범위 뒤부터다(그 글자에 배율이 두 번 걸려 자간이 0 → +4 → +14% 로 상한을 넘던 것: astra)."""
    j, t = _para("가" * 26 + " 데이터 가", "이드라인 나나나나 가", "이드라인 긴낱말입니다")
    first = j.trial
    cut = t.index("가이드")
    assert first["kind"] == "push" and (first["rs"], first["re"]) == (0, cut)
    cut2 = t.index("가이드", cut + 1)
    j.observe([(0, cut - 1), (cut - 1, cut2), (cut2, len(t))])   # 한글: 한 칸 더 밀려 둘째 줄이 「 가이드라인 …」 의 빈칸에서 시작
    assert j.ops == [first]
    if j.trial is not None:   # 둘째 줄을 또 고친다면 앞 범위(…cut) 뒤부터
        assert j.trial["rs"] >= first["re"]
    for a in j.ops + ([j.trial] if j.trial else []):
        for b in j.ops + ([j.trial] if j.trial else []):
            assert a is b or a["re"] <= b["rs"] or b["re"] <= a["rs"]


# ---------------------------------------------------------------- 끝점 — 재기 → 반영 → 실행 취소(가짜 한글 조판 · 진짜 서버 세션)
def test_plan_apply_undo_api(monkeypatch):
    """문서의 한 문단을 가짜 한글이 「…낱말의 앞 / 끝 1자」 로 나눈다(자간을 줄인 글자 모양이 걸리면 한 줄) → 계획 1문단 · 반영(실행 취소 1) · 기록 · 실행 취소로 되돌아옴."""
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

    def ratios(D, q, tag="spacing", default=0):   # 런마다 한글 자간(%) — tag="ratio" 면 장평
        out = []
        for r in q.iterchildren(HP + "run"):
            cp = D._defs["charPr"].get(r.get("charPrIDRef"))
            e = cp.find(LT._hh(tag)) if cp is not None else None
            out.append(int(e.get("hangul", default)) if e is not None else default)
        return out
    wide = set(ratios(s.doc, ps[pick], "ratio", 100))
    orig = set(ratios(s.doc, ps[pick]))

    def layout(b):
        D = HwpxDoc(b)
        q = A._paras(D)[pick]
        small = any(x not in orig for x in ratios(D, q))   # 자간을 바꾼 런이 있으면 한 줄로
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
    assert set(ratios(s.doc, p, "ratio", 100)) == wide   # 장평은 안 바뀐다(2026-11-23 「자간으로 당기기」)
    g = c.get(f"/api/docs/{d}/line-tidy").json()
    assert g["applied"]["planId"] == r["planId"] and g["applied"]["paras"] == 1 and g["facts"]["applied"]["paras"] == 1
    assert g["plan"]["by"] == "space" and g["facts"]["ratio"] == 0 and r["undo"] == [] and a["undone"] == []
    assert c.post(f"/api/docs/{d}/line-tidy/apply", json={"planId": r["planId"]}).status_code == 409   # 잰 뒤 문서가 바뀜(반영으로 rev 가 올랐다) — 다시 잰다
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    s2 = server._sess(d)
    assert set(ratios(s2.doc, A._paras(s2.doc)[pick])) <= orig


# ---------------------------------------------------------------- 계획 길(가짜 한글 조판)
def test_plan_bytes_with_fake_layout():
    """plan_bytes — 한글 대신 「줄 시작 자리를 정해 주는」 가짜 조판: 처음엔 갈린 줄 · 자간을 바꾼 사본엔 한 줄. 고친 문단 하나 · 배율은 처음 문단 기준."""
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
    wide = {**R, "minSpace": -30}   # 양식의 그 문단은 자간이 이미 −11% 다 — 기본 하한(−15%)으로는 4%p 밖에 못 줄인다(그 한도는 test_limits_follow_current_spacing)
    assert A.plan_bytes(data, R, lambda i, q, t: i == target[0], lambda b: layout(b) if not calls.clear() else b)["counts"]["why"] == {"자간 한도": 1}
    calls.clear()
    res = A.plan_bytes(data, wide, lambda i, q, t: i == target[0], layout)
    assert len(calls) == 2 and res["rounds"] == 1  # 쪽에 걸친 줄 걸음은 자간 걸음의 마지막 조판을 그대로 쓴다(걸린 문단이 없으면 다시 재지 않는다)
    (it,) = res["items"]
    assert it["ops"][0]["kind"] == "pull+last" and it["after"] == ["가" * 28 + " 예지보전 가동"]
    assert res["counts"]["fixed"] == 1 and res["counts"]["chain"] == 1
    assert res["pages"] == [] and res["blanks"] == [] and res["counts"]["pageSeen"] == 0
    assert res["undone"] == [] and res["counts"]["undone"] == 0


def test_old_ratio_fix_is_undone_and_redone_with_spacing(monkeypatch):
    """전에 **장평으로** 고친 문단(② §9 — 2026-11-23 사용자(장평 96% 인 줄을 한글에서 보며) "폰트가 좀 이상한거 같은데" → 「자간으로 당기기」):
    옛 기록(장평 계획 + 그 반영)이 있으면 상태 재료가 그 문단 수를 알리고, 다시 재면 그 장평을 되돌린 사본에서 재고, 반영이 장평을 되돌리고 자간을 입힌다.
    장평으로 잰 옛 계획은 반영하지 않는다(409)."""
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
    for pick, p in enumerate(ps):
        t = s.doc._text(p)
        m = list(re.finditer(r"[가-힣]{3,}", t))
        if s.doc._rev.get(p) and not s.doc._has_object(p) and len(t) > 30 and len(m) >= 2 and LT.letters(t[:m[-2].end() - 1]) >= 12 and t[m[-2].end():m[-2].end() + 1] == " ":
            cut = m[-2].end() - 1
            break
    p, text, bid = ps[pick], s.doc._text(ps[pick]), s.doc._rev[ps[pick]]
    rs = LT.protect(text)

    def vals(D, q, tag, default):
        out = []
        for r in q.iterchildren(HP + "run"):
            e = D._defs["charPr"][r.get("charPrIDRef")].find(LT._hh(tag))
            out.append(int(e.get("hangul", default)) if e is not None else default)
        return out
    ratio0, space0 = vals(s.doc, p, "ratio", 100), set(vals(s.doc, p, "spacing", 0))

    def make(sess):   # 전의 줄 정리가 하던 반영 — 그 줄의 장평 × 96%
        q = sess.doc._ids[bid]

        def run():
            LT._rescale(sess.doc, q, rs, cut + 1, "ratio", 100, lambda cur: round(cur * 96 / 100))
            return {"hosts": [q], "formatted": {bid}, "struct": set(), "origin": {}, "anchor": bid, "log": {}}
        return [q], run
    server._edit(d, make, "lineTidy", {})
    s = server._sess(d)
    assert vals(s.doc, s.doc._ids[bid], "ratio", 100) != ratio0
    old = {"planId": "old000000001", "at": 1.0, "rev": s.rev - 1, "rules": {}, "counts": {},
           "items": [{"id": bid, "text": text, "ops": [{"kind": "pull", "rs": rs, "re": cut + 1, "pct": 96}], "before": [], "after": []}]}
    A._save(d, {"version": A.VERSION, "plan": old, "applied": {"at": 2.0, "planId": old["planId"], "rev": s.rev, "fill": None, "paras": 1, "ops": 1, "counts": {}}})
    assert A.facts(d)["ratio"] == 1
    assert c.post(f"/api/docs/{d}/line-tidy/apply", json={"planId": old["planId"]}).status_code == 409   # 장평으로 잰 옛 계획
    seen = []

    def layout(b):
        D = HwpxDoc(b)
        q = A._paras(D)[pick]
        seen.append(vals(D, q, "ratio", 100))
        small = any(x not in space0 for x in vals(D, q, "spacing", 0))   # 자간을 바꾼 런이 있으면 한 줄로
        for la in q.findall(HP + "linesegarray"):
            q.remove(la)
        arr = etree.SubElement(q, HP + "linesegarray")
        etree.SubElement(arr, HP + "lineseg", {"textpos": "0"})
        if not small:
            etree.SubElement(arr, HP + "lineseg", {"textpos": str(cut)})
        D._mark(D._name_of[q.getroottree().getroot()])
        return D.save()
    monkeypatch.setattr(A, "_hwp_ok", lambda: True)
    monkeypatch.setattr(A, "_layout", layout)
    r = c.post(f"/api/docs/{d}/line-tidy/plan").json()
    assert seen[0] == ratio0   # 장평을 되돌린 사본에서 쟀다
    assert [x["id"] for x in r["undo"]] == [bid] and r["counts"]["undone"] == 1 and len(r["items"]) == 1, r
    assert A.facts(d)["ratio"] == 1 and r["undo"][0]["by"] == "runs"   # 재기만 했다 — 아직 장평으로 고친 줄이다(새 계획이 옛 계획을 덮어도 잃지 않는다)
    a = c.post(f"/api/docs/{d}/line-tidy/apply", json={"planId": r["planId"]}).json()
    assert a["undone"] == [bid] and a["done"] == [bid]
    s = server._sess(d)
    q = s.doc._ids[bid]
    assert set(vals(s.doc, q, "ratio", 100)) == set(ratio0) and any(x not in space0 for x in vals(s.doc, q, "spacing", 0))   # 장평은 처음대로 · 자간으로
    assert A.facts(d)["ratio"] == 0 and len(A.load(d)["ratio"]) == 1   # 「옛 줄」 은 문서에서 센다 — 기록은 남긴다
    assert c.post(f"/api/docs/{d}/undo").status_code == 200   # 자간으로 바꾼 것을 실행 취소 — 장평이 돌아왔으니 다시 「옛 줄」 이다(기록이 아니라 문서에서 세니 저절로)
    assert A.facts(d)["ratio"] == 1


def test_old_ratio_record_of_an_undone_fix_is_dropped(monkeypatch):
    """장평 반영을 「실행 취소」 한 문서 — 기록은 남아 있지만 그 장평은 문서에 없다: 다시 재도 되돌리지 않고(100 → 104 로 넓히지 않는다) 그 기록은 「옛 줄」 에서 뺀다
    (남겨 두면 그 줄 때문에 늘 「할 일」 로 선다)."""
    import re

    from fastapi.testclient import TestClient
    from lxml import etree

    from app import server
    from app.hwpx_doc import HwpxDoc
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    c = TestClient(server.app)
    d = c.post("/api/docs?new=1", files={"file": (PLAN.name, PLAN.read_bytes())}).json()["docId"]
    s = server._sess(d)
    for pick, p in enumerate(A._paras(s.doc)):
        t = s.doc._text(p)
        m = list(re.finditer(r"[가-힣]{3,}", t))
        if s.doc._rev.get(p) and not s.doc._has_object(p) and len(t) > 30 and len(m) >= 2 and LT.letters(t[:m[-2].end() - 1]) >= 12 and t[m[-2].end():m[-2].end() + 1] == " ":
            cut = m[-2].end() - 1
            break
    text, bid = s.doc._text(p), s.doc._rev[p]

    def ratios(D, q):
        return [int(D._defs["charPr"][r.get("charPrIDRef")].find(LT._hh("ratio")).get("hangul", 100)) for r in q.iterchildren(HP + "run")]
    ratio0 = ratios(s.doc, p)
    old = {"planId": "old000000002", "at": 1.0, "rev": s.rev, "rules": {}, "counts": {},
           "items": [{"id": bid, "text": text, "ops": [{"kind": "pull", "rs": LT.protect(text), "re": cut + 1, "pct": 96}], "before": [], "after": []}]}
    A._save(d, {"version": A.VERSION, "plan": old, "applied": {"at": 2.0, "planId": old["planId"], "rev": s.rev, "fill": None, "paras": 1, "ops": 1, "counts": {}}})
    assert A.facts(d)["ratio"] == 0   # 기록은 있지만 그 장평은 문서에 없다 — 「옛 줄」 로 안 센다(「할 일」 로 안 선다)
    seen = []

    def layout(b):
        D = HwpxDoc(b)
        q = A._paras(D)[pick]
        seen.append(ratios(D, q))
        for la in q.findall(HP + "linesegarray"):
            q.remove(la)
        etree.SubElement(etree.SubElement(q, HP + "linesegarray"), HP + "lineseg", {"textpos": "0"})   # 한 줄 — 고칠 것 없음
        D._mark(D._name_of[q.getroottree().getroot()])
        return D.save()
    monkeypatch.setattr(A, "_hwp_ok", lambda: True)
    monkeypatch.setattr(A, "_layout", layout)
    r = c.post(f"/api/docs/{d}/line-tidy/plan").json()
    assert r["undo"] == [] and r["counts"]["undone"] == 0 and r["counts"]["ratioLeft"] == 1 and r.get("nothing") is True, r
    assert all(x == ratio0 for x in seen)   # 넓힌 사본을 재지 않았다
    assert A.facts(d)["ratio"] == 0 and len(A.load(d)["ratio"]) == 1   # 재기만으로 기록을 지우지 않는다
    assert c.post(f"/api/docs/{d}/line-tidy/apply", json={"planId": r["planId"]}).json().get("nothing") is True
    s = server._sess(d)
    assert ratios(s.doc, s.doc._ids[bid]) == ratio0


# ---------------------------------------------------------------- 쪽에 걸친 줄(② §8)
def _flow(*rows):
    """(idx, 줄 자리들, 빈 줄인가) → 흐름. 줄 자리 = (vertpos, vertsize, spacing)."""
    return [{"idx": i, "segs": list(segs), "blank": blank, "obj": False, "ok": True} for i, segs, blank in rows]


def test_page_issue_and_blanks():
    """쪽 나눔 = 줄 자리가 위로 되돌아간 곳 · 넘어간 줄이 규칙 이하일 때만 · 빈 줄은 같은 쪽(줄 자리가 이어지는 데까지)의 것만."""
    two = [(70790, 1000, 200), (0, 1000, 200)]
    assert LT.page_breaks(two) == [1] and LT.page_breaks([(0, 1000, 200), (1200, 1000, 200)]) == []
    assert LT.page_issue(two, R) == {"k": 1, "tail": 1, "need": 1200}
    assert LT.page_issue(two, {**R, "pageTail": 0}) is None   # 0 = 안 함
    assert LT.page_issue([(5000, 1000, 200), (0, 1000, 200), (1200, 1000, 200)], R) is None   # 넘어간 줄 2 > 규칙 1
    assert LT.page_issue([(5000, 1000, 200), (0, 1000, 200), (1200, 1000, 200)], {**R, "pageTail": 2})["need"] == 2400
    assert LT.page_issue([(9000, 1000, 200), (0, 1000, 200), (0, 1000, 200)], R) is None   # 세 쪽에 걸침
    flow = _flow((0, [(9000, 1000, 200)], True),    # 앞 쪽의 빈 줄(다음 문단의 줄 자리가 더 위다)
                 (1, [(0, 1000, 200)], False),
                 (2, [(1200, 1000, 200)], True),
                 (3, [(2400, 1000, 200), (3600, 1000, 200)], False),
                 (4, [(4800, 500, 100)], True),
                 (5, [(5400, 1000, 200), (0, 1000, 200)], False))
    assert LT.page_blanks(flow, 5) == [4, 2]
    assert LT.page_blanks(_flow((0, [(100, 1000, 200)], True), (1, [(5000, 1000, 200), (0, 1000, 200)], False), (2, [(1200, 1000, 200), (0, 1000, 200)], False)), 2) == []   # 윗 문단도 쪽에 걸침 — 그 위는 앞 쪽
    assert LT.blank_scale(1200, [1200] * 4, [100] * 4, 60) == [75] * 4   # 같은 비율로 조금씩
    assert LT.blank_scale(1200, [1200] * 2, [100] * 2, 60) == [60] * 2   # 하한보다 낮게는 안 함
    assert LT.blank_scale(1200, [720] * 2, [60] * 2, 60) is None and LT.blank_scale(1200, [1200] * 4, [100] * 4, 60, force=True) == [60] * 4


def test_pages_try_confirm_and_give_up():
    """Pages — 걸린 문단의 쪽에 있는 빈 줄을 낮춰 보고, 다시 잰 줄에서 안 걸치면 고침 · 하한까지 낮춰도 걸쳐 있으면 되돌리고 둔다."""
    def flows(h, fits):   # 빈 줄 넷(높이 h) + 두 줄 문단
        rows, y = [], 0
        for i in range(4):
            rows.append((i, [(y, h, h // 5)], True))
            y += h + h // 5
        rows.append((4, [(y, 1000, 200), ((y + 1200) if fits else 0, 1000, 200)], False))
        return [_flow(*rows)]
    P = LT.Pages(R)
    assert P.step(flows(1000, False)) and P.scale == {0: 75, 1: 75, 2: 75, 3: 75} and P.first == 1
    assert not P.step(flows(750, True))   # 다시 잰 줄 — 안 걸침
    done, left, blanks = P.result(flows(750, True))
    assert done == [{"idx": 4, "tail": 1, "blanks": [{"idx": b, "pct": 75} for b in range(4)]}] and left == [] and len(blanks) == 4
    P = LT.Pages(R)
    assert P.step(flows(1000, False)) and P.step(flows(750, False)) and set(P.scale.values()) == {60}   # 어림이 모자람 — 하한까지 한 번 더
    assert P.step(flows(600, False)) and P.scale == {}   # 그래도 걸침 — 되돌린다
    assert not P.step(flows(1000, False))
    done, left, blanks = P.result(flows(1000, False))
    assert done == [] and blanks == [] and left == [{"idx": 4, "tail": 1, "why": "floor"}]
    P = LT.Pages(R)   # 빈 줄이 없는 쪽
    assert not P.step([_flow((0, [(100, 1000, 200)], False), (1, [(1300, 1000, 200), (0, 1000, 200)], False))])
    assert P.result([_flow((1, [(1300, 1000, 200), (0, 1000, 200)], False))])[1] == [{"idx": 1, "tail": 1, "why": "noBlank"}]


def test_scale_height_on_document():
    from app.hwpx_doc import RUN, HwpxDoc
    doc = HwpxDoc(PLAN.read_bytes())
    p = next(p for sec in doc._sections for p in sec.iter(A.P_TAG) if not doc._text(p).strip() and not doc._has_object(p) and list(p.iterchildren(RUN)))
    h = lambda: [int(doc._defs["charPr"][r.get("charPrIDRef")].get("height")) for r in p.iterchildren(RUN)]  # noqa: E731
    h0 = h()
    assert LT.scale_height(doc, p, 75) == len(h0) and h() == [max(100, round(x * 0.075) * 10) for x in h0]
    assert LT.scale_height(doc, p, 100) == 0   # 같은 크기 — 새 글자 모양을 들이지 않는다
    again = HwpxDoc(doc.save())
    assert any(c.get("height") == str(h()[0]) for c in again._defs["charPr"].values())


def _page_case(doc):
    """양식에서 「빈 줄 + 바로 아래 글 문단」(같은 흐름 · 둘 다 블록 문단) 한 쌍 → (빈 줄 차례, 글 문단 차례, 글에서 줄을 나눌 자리 — 빈칸 뒤)."""
    from app.division_profiles import _structure as structure
    ids = {b["id"] for b in structure.iter_blocks(doc.blocks()) if b.get("type") == "paragraph"}
    ps = A._paras(doc)
    for i in range(1, len(ps)):
        q, p = ps[i - 1], ps[i]
        t = doc._text(p)
        cut = t.find(" ", len(t) // 2) + 1
        if (q.getparent() is p.getparent() and not doc._text(q).strip() and not doc._has_object(q) and not doc._has_object(p) and doc._rev.get(q) in ids and doc._rev.get(p) in ids
                and len(t) > 40 and 0 < cut < len(t) - 8 and all(ord(c) <= 0xFFFF for c in t) and "\t" not in t):
            return i - 1, i, cut
    raise AssertionError("양식에 빈 줄 + 글 문단 쌍이 없습니다")


def _page_layout(bi, pi, cut, calls=None):
    """가짜 한글 조판 — 빈 줄의 높이(글자 크기)가 처음의 80% 이하면 글 문단의 둘째 줄이 같은 쪽에, 아니면 다음 쪽(줄 자리 0)에. 다른 문단의 캐시는 지운다(양식의 쪽 나눔이 섞이지 않게)."""
    from lxml import etree

    from app.hwpx_doc import LINESEG, RUN, HwpxDoc
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    first = []

    def layout(b):
        d = HwpxDoc(b)
        qs = A._paras(d)
        for q in qs:
            for la in q.findall(LINESEG):
                q.remove(la)
            d._touch(q)
        h = int(d._defs["charPr"][next(qs[bi].iterchildren(RUN)).get("charPrIDRef")].get("height"))
        first.append(h)

        def put(q, rows):
            arr = etree.SubElement(q, HP + "linesegarray")
            for tp, vp, vs, sp in rows:
                etree.SubElement(arr, HP + "lineseg", {"textpos": str(tp), "vertpos": str(vp), "vertsize": str(vs), "spacing": str(sp)})
        put(qs[bi], [(0, 0, h, h // 5)])
        y = h + h // 5
        put(qs[pi], [(0, y, 1000, 200), (cut, y + 1200 if h <= first[0] * 0.8 else 0, 1000, 200)])
        if calls is not None:
            calls.append(h)
        return d.save()
    return layout


def test_plan_bytes_page_fit_with_fake_layout():
    """plan_bytes — 장평으로 고칠 것은 없고 한 줄이 다음 쪽으로 넘어간 문단 하나: 그 쪽의 빈 줄을 하한(60%)까지 낮춰 한 쪽으로. 조판은 처음 + 낮춘 뒤 한 번."""
    from app.hwpx_doc import HwpxDoc
    data = PLAN.read_bytes()
    bi, pi, cut = _page_case(HwpxDoc(data))
    calls = []
    res = A.plan_bytes(data, R, lambda i, q, t: i in (bi, pi), _page_layout(bi, pi, cut, calls))
    assert res["items"] == [] and res["rounds"] == 0 and res["pageRounds"] == 1 and len(calls) == 2
    assert res["blanks"] == [{"idx": bi, "pct": 60}] and calls[1] == max(100, round(calls[0] * 0.06) * 10)   # 빈 줄 하나 — 어림(한 줄 높이)이 빈 줄보다 커서 하한까지
    (pg,) = res["pages"]
    assert pg["idx"] == pi and pg["tail"] == 1 and pg["blanks"] == [{"idx": bi, "pct": 60}] and res["pageLeft"] == []
    c = res["counts"]
    assert (c["pageSeen"], c["pageFixed"], c["pageLeft"], c["pageBlanks"]) == (1, 1, 0, 1)
    off = A.plan_bytes(data, {**R, "pageTail": 0}, lambda i, q, t: i in (bi, pi), _page_layout(bi, pi, cut))   # 규칙 0 = 안 함
    assert off["pages"] == [] and off["blanks"] == [] and off["counts"]["pageSeen"] == 0
    from app.workflow_units import line_tidy_text
    assert "쪽에 걸친 문단 1곳을 한 쪽으로(높이를 낮춘 빈 줄 1)" in line_tidy_text(c)


def test_page_fit_plan_apply_undo_api(monkeypatch):
    """끝점 — 쪽에 걸친 문단만 있는 계획: 재기(문서 그대로) → 반영(빈 줄의 글자 크기 60% · 실행 취소 1 · 기록) → 실행 취소로 되돌아옴. 빈 줄에 글이 생기면 반영은 409."""
    from fastapi.testclient import TestClient

    from app import server
    from app.hwpx_doc import RUN
    c = TestClient(server.app)
    d = c.post("/api/docs?new=1", files={"file": (PLAN.name, PLAN.read_bytes())}).json()["docId"]
    s = server._sess(d)
    bi, pi, cut = _page_case(s.doc)
    ps = A._paras(s.doc)
    bid, pid = s.doc._rev[ps[bi]], s.doc._rev[ps[pi]]
    height = lambda S: int(S.doc._defs["charPr"][next(A._paras(S.doc)[bi].iterchildren(RUN)).get("charPrIDRef")].get("height"))  # noqa: E731
    h0 = height(s)
    monkeypatch.setattr(A, "_hwp_ok", lambda: True)
    monkeypatch.setattr(A, "_layout", _page_layout(bi, pi, cut))
    r = c.post(f"/api/docs/{d}/line-tidy/plan").json()
    assert "nothing" not in r and r["items"] == [] and r["blanks"] == [{"id": bid, "pct": 60}], r
    assert r["pages"] == [{"id": pid, "text": s.doc._text(ps[pi]), "tail": 1, "blanks": [{"id": bid, "pct": 60}]}] and height(s) == h0
    rev0, undo0 = s.rev, len(s.undo)
    a = c.post(f"/api/docs/{d}/line-tidy/apply", json={"planId": r["planId"]}).json()
    assert a["tidy"]["blanks"] == [{"id": bid, "pct": 60}] and a["done"] == [] and s.rev == rev0 + 1 and len(s.undo) == undo0 + 1
    assert height(s) == max(100, round(h0 * 0.06) * 10)
    g = c.get(f"/api/docs/{d}/line-tidy").json()
    assert g["applied"]["blanks"] == 1 and g["applied"]["pages"] == 1 and g["applied"]["counts"]["pageFixed"] == 1
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    assert height(server._sess(d)) == h0


# ---------------------------------------------------------------- astra 검증(2026-11-23)의 반례 — 반영이 쓰다 말지 않는다 · 안 쓰인 언어의 자간도 한도 안
def test_apply_checks_every_old_fix_before_writing(monkeypatch):
    """반영은 옛 장평을 되돌릴 근거를 **쓰기 전에** 모두 다시 센다 — 둘째 문단에서 409 를 내면서 첫 문단은 바뀐 채 남던 것(_transact 는 KeyError · ValueError 만 되돌린다)."""
    from fastapi.testclient import TestClient

    from app import server
    HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    c = TestClient(server.app)
    d = c.post("/api/docs?new=1", files={"file": (PLAN.name, PLAN.read_bytes())}).json()["docId"]
    s = server._sess(d)
    two = [p for p in A._paras(s.doc) if s.doc._rev.get(p) and not s.doc._has_object(p) and len(s.doc._text(p)) > 30][:2]
    ids = [s.doc._rev[p] for p in two]

    def make(sess):   # 첫 문단에만 전의 장평 고침(× 96%)
        q = sess.doc._ids[ids[0]]

        def run():
            LT._rescale(sess.doc, q, 2, 12, "ratio", 100, lambda cur: round(cur * 96 / 100))
            return {"hosts": [q], "formatted": {ids[0]}, "struct": set(), "origin": {}, "anchor": ids[0], "log": {}}
        return [q], run
    server._edit(d, make, "lineTidy", {})
    s = server._sess(d)
    shape = lambda: [[r.get("charPrIDRef") for r in s.doc._ids[i].iterchildren(HP + "run")] for i in ids]  # noqa: E731
    before, rev0, undo0 = shape(), s.rev, len(s.undo)
    plan = {"planId": "p00000000001", "at": 1.0, "rev": s.rev, "by": "space", "rules": {}, "items": [], "left": [], "counts": {}, "pages": [], "pageLeft": [], "blanks": [],
            "undo": [{"id": ids[0], "text": s.doc._text(s.doc._ids[ids[0]]), "ops": [{"rs": 2, "re": 12, "pct": 96}], "by": "runs"},
                     {"id": ids[1], "text": s.doc._text(s.doc._ids[ids[1]]), "ops": [{"rs": 2, "re": 12, "pct": 96}], "by": "runs"}]}   # 둘째는 고친 적이 없다 — 근거 없음
    A._save(d, {"version": A.VERSION, "plan": plan, "applied": None})
    r = c.post(f"/api/docs/{d}/line-tidy/apply", json={"planId": plan["planId"]})
    assert r.status_code == 409 and "서식이 바뀌었습니다" in r.json()["detail"]
    s = server._sess(d)
    assert shape() == before and (s.rev, len(s.undo)) == (rev0, undo0)   # 첫 문단도 그대로


def test_unused_language_spacing_stays_in_limit():
    """자간은 언어 일곱에 다 적힌다 — 한도도 일곱 모두에서 센다: 한글 0% · 영문 −14% 인 글자 모양의 한글 줄을 90% 로 당기면 영문이 −23% 가 되던 것 → 「자간 한도」 로 둔다."""
    import copy

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
    c = copy.deepcopy(doc._defs["charPr"][runs[0].get("charPrIDRef")])
    for x in LT.LANGS:
        c.find(LT._hh("spacing")).set(x, "-14" if x == "latin" else "0")
    runs[0].set("charPrIDRef", doc._add_def("charPr", c))
    doc._touch(p)
    data = doc.save()
    D0 = HwpxDoc(data)
    (target,) = [i for i, q in enumerate(A._paras(D0)) if D0._text(q).startswith("가" * 28)]

    def layout(b):
        d = HwpxDoc(b)
        q = A._paras(d)[target]
        for la in q.findall(HP + "linesegarray"):
            q.remove(la)
        arr = etree.SubElement(q, HP + "linesegarray")
        etree.SubElement(arr, HP + "lineseg", {"textpos": "0"})
        etree.SubElement(arr, HP + "lineseg", {"textpos": str(len("가" * 28 + " 예지보"))})
        d._mark(d._name_of[q.getroottree().getroot()])
        return d.save()
    res = A.plan_bytes(data, R, lambda i, q, t: i == target, layout)
    assert res["items"] == [] and res["counts"]["why"] == {"자간 한도": 1}   # 한글만 보면 0% → −10% 로 될 일이지만 영문 −14% 가 하한(−15%)을 넘는다
