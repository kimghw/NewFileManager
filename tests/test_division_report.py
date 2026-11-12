"""KEIT 연차보고서 서식(spec_구분_기준 ② §17 — FMM tests/test_division_report.py 이식: spec_구분_초기화 ② §1 FORMS·DIV-018, 10-30 [fb]) — 양식 이름, 보고서에만 있는 자리(2-2 「…기관명 : 」 절·
6. 글머리 기관 절·혼자인 주관 절·국외기관 뼈대 줄·「다음 연도」 기관-연도 표·단계 아래 연도 열·표지 「해당연도」 행·당해 라벨), 크게·작게 반영,
다시 반영하면 할 일 없음, 문서에서 읽기. ② §18(2026-11-11): 간접비 표 = 기관마다 첫 블록 꼴 · 「5. 다음 연도」 라벨 = 다음 차년도 · 요약문 차년도 라벨 = 전체 차년도 ·
2-2 평가항목별 표준 표 = 당해 차년도 행만."""
import io
from pathlib import Path

import docx
import pytest

from app.division_profiles import _structure as structure
from app.division_profiles import rnd
from app.division_profiles.rnd import core as divisions
from app.division_profiles.rnd.core import ORG, YEAR, N
from app.docx_doc import DocxDoc
from app.hwpx_doc import HwpxDoc

REPORT = Path(__file__).parents[1] / "samples" / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"
needs_report = pytest.mark.skipif(not REPORT.exists(), reason="KEIT 연차보고서 서식 hwpx 없음")
FULL = {"stages": [2, 3], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False],
        "outside": ["외A사"], "overseas": ["Fraunhofer (IPT)", "MIT"]}, "period": {"start": "2026-03-01", "end": "2030-12-31"}, "current": 1}
SMALL = {"stages": [3], "orgs": {"lead": "", "joint": []}, "period": {"start": "2026-03-01", "end": "2028-12-31"}}


def levels(blocks):
    return rnd.levels_of(blocks)


def paras(doc):
    return [b["text"] for b in structure.iter_blocks(doc.blocks()) if b.get("type") == "paragraph"]


def tables(doc):
    return [t for t in structure.iter_blocks(doc.blocks()) if t.get("type") == "table"]


def flat(c):
    return (c["text"] or "").replace("\n", "")


def row_texts(t, r):
    return [flat(c) for c in sorted(t["cells"], key=lambda c: c["col"]) if c["row"] == r]


def col_texts(t, col):
    return [c["text"] or "" for c in sorted(t["cells"], key=lambda c: c["row"]) if c["col"] == col and c["row"] > 0]


def applied(vals):
    doc = HwpxDoc(REPORT.read_bytes())
    return doc, divisions.apply(doc, divisions.norm_values(vals), levels_of=levels)


# ---------------------------------------------------------------- 양식 이름 · 라벨 · 이름 자리

def test_form_names():
    for name in ("연차보고서", "단계보고서", "최종보고서"):
        d = docx.Document()
        d.add_paragraph(name)
        d.add_paragraph("[  ] 일반형")
        buf = io.BytesIO()
        d.save(buf)
        assert divisions.form_of(DocxDoc(buf.getvalue()).blocks()) == name and divisions.is_report(name)
    assert not divisions.is_report(divisions.FORM) and not divisions.is_report(None)


def test_report_label_shapes():
    assert divisions._key("[공동연구개발기관명N : ]  ※ 표에 기재") == (ORG, ("joint", N))
    assert divisions._label("[주관연구개발기관명 : ]  ※ 표에 기재")[2] == divisions._label("[공동연구개발기관명N : ]")[2]
    assert divisions._label(" ㅇ 주관연구개발기관 : ㅇㅇㅇㅇㅇㅇ")[2] == divisions._label(" ㅇ 공동연구개발기관 : ㅇㅇㅇㅇㅇㅇ")[2]
    assert divisions.PARA_LABEL.match(" ㅇ 공동연구개발기관 : ㅇㅇㅇ") and not divisions.PARA_LABEL.match(" ㅇ (N단계-N차년도) 추진 내용")
    assert divisions._name("ㅇㅇㅇㅇㅇㅇ") == "" and divisions._name("가나대") == "가나대"


@pytest.mark.parametrize("text, new, name, want", [
    ("[주관연구개발기관명 : ]  ※ 표에 기재", ("lead", 0), "인텍", "[주관연구개발기관명 : 인텍]  ※ 표에 기재"),
    ("[공동연구개발기관명N : ]", ("joint", 2), "다라연", "[공동연구개발기관명2 : 다라연]"),
    (" ㅇ 공동연구개발기관 : ㅇㅇㅇㅇㅇㅇ", ("joint", 1), "가나대", " ㅇ 공동연구개발기관 : 가나대"),
    ("[주관연구개발기관 : 기관명]", ("joint", 1), "가나대", "[공동연구개발기관1 : 가나대]"),   # 혼자인 주관 절의 사본
    ("[공동연구개발기관1 : 기관명]", ("joint", 2), "다라연", "[공동연구개발기관2 : 다라연]"),   # 계획서 8-2 (2) — 그대로
    ("주관연구개발기관명", ("lead", 0), "인텍", "인텍"),   # 8-1 표 기관 행 — 낱말째 이름
])
def test_org_text_colon(text, new, name, want):
    assert divisions._org_text(text, new, name) == want


# ---------------------------------------------------------------- 실제 서식 (hwpx)

@needs_report
def test_report_form_and_groups():
    doc = HwpxDoc(REPORT.read_bytes())
    blocks = doc.blocks()
    assert divisions.form_of(blocks) == "연차보고서"
    groups = divisions.find(blocks, levels(blocks), divisions.norm_values(FULL))
    org = next(g for g in groups if g["dim"] == ORG and g["items"][0]["labelText"].startswith("[주관연구개발기관명 : ]"))
    assert [it["value"] for it in org["items"]] == [("lead", 0), ("joint", N)] and org["items"][1]["size"] >= 10
    sec = next(g for g in groups if g["dim"] == ORG and g["items"][0]["labelText"].strip().startswith("ㅇ 주관연구개발기관 :"))
    assert [it["value"] for it in sec["items"]] == [("lead", 0), ("joint", None)] and [it["size"] for it in sec["items"]] == [2, 2]
    solo = next(g for g in groups if g["dim"] == ORG and g["items"][0]["labelText"] == "[주관연구개발기관 : 기관명]")
    assert len(solo["items"]) == 1 and solo["target"] == [("lead", 0), ("joint", 1), ("joint", 2)] and solo["items"][0]["size"] >= 8
    ov = next(g for g in groups if g["dim"] == ORG and g["items"][0]["value"][0] == "overseas")
    assert ov["items"][0]["size"] == 5   # 라벨 + 빈 줄 + 「ㅇ (N단계-N차년도) 추진 내용 및 실적」 + 「- (추진 내용)」 + 「- (추진 실적)」
    cols = [g for g in groups if g["dim"] == YEAR and g["kind"] == "cols" and g["items"][0]["labelText"] == "20xx"]
    assert [len(g["items"]) for g in cols] == [3, 3] and [g["ctx"] for g in cols] == [1, "?"]   # 정량적 연구개발성과표 1단계·n단계 아래
    nxt = [g for g in groups if g.get("orgYear") == "year" and g.get("yearBase") is not None]
    assert len({g["table"] for g in nxt}) == 6 and all(g["target"] == [1] and g["yearBase"] == 1 for g in nxt)   # 「다음 연도」 절 표 6개(기관 블록마다 묶음) — 다음 차년도 행 하나
    # 간접비 표(② §18): 끝 빈 행(1행)은 한 해 블록(7행)보다 작은 자리표시 — 주관 블록을 본뜨고 그 행은 지움. 목록형 표 5개의 빈 행은 그대로 본뜰 항목
    orgs = [g for g in groups if g.get("orgYear") == "org" and len(g["items"]) == 2]
    assert [(g["items"][1]["thin"], g["plan"]["template"], g["plan"]["drop"], g["plan"]["copies"]) for g in orgs] \
        == [(False, 1, [], 1)] * 5 + [(True, 0, [1], 2)]
    this = [g for g in groups if g.get("thisYear")]   # 2-2 평가항목별 표준 표(주관·공동N 절 × 평가항목 2) — 당해 차년도 행 하나
    assert len(this) == 4 and all(g["target"] == [(1, 1)] and len(g["items"]) == 4 and len(g["plan"]["keep"]) == 1 for g in this)
    goal = [g for g in groups if g["dim"] == YEAR and g["kind"] == "paragraph" and g["items"][0]["labelText"].startswith("[N차년도")]
    assert [len(g["items"]) for g in goal] == [1, 1] and all(g["target"] == [1, 2, 3, 4, 5] for g in goal)   # 요약문 「[N차년도 목표]」·「[N차년도 개발내용]」 — 전체 차년도마다


@needs_report
def test_report_full_apply_read_and_reapply():
    doc, rep = applied(FULL)
    assert not rep["errors"] and rep["passes"] >= 2
    ps = paras(doc)
    for want in ("[주관연구개발기관명 : 인텍]", "[공동연구개발기관명1 : 가나대]", "[공동연구개발기관명2 : 다라연]",
                 "[국외기관명1 : Fraunhofer (IPT)]", "[국외기관명2 : MIT]"):
        assert sum(p.startswith(want) for p in ps) == 1, want
    assert not any("기관명N" in p or "[국외기관명 : ]" in p or "(N단계-N차년도)" in p or "[N차년도" in p for p in ps)
    assert sum(p.strip().startswith("ㅇ (1단계-1차년도) 추진 내용 및 실적") for p in ps) == 5   # 주관·공동 2·국외 2 — 당해 차년도
    assert [p for p in ps if p in ("[주관연구개발기관 : 인텍]", "[공동연구개발기관1 : 가나대]", "[공동연구개발기관2 : 다라연]")] \
        == ["[주관연구개발기관 : 인텍]", "[공동연구개발기관1 : 가나대]", "[공동연구개발기관2 : 다라연]"]   # 혼자인 주관 절 → 기관마다
    for name in ("참여연구자 인건비", "학생인건비"):   # 「5. 다음 연도」 아래 = 다음 차년도(② §18)
        assert sum(p.strip().startswith(f"ㅇ {name} 현황표(1단계-2차년도)") for p in ps) == 3, name
    assert [p.strip() for p in ps if p.strip().startswith(("ㅇ 주관연구개발기관 :", "ㅇ 공동연구개발기관 :"))] \
        == ["ㅇ 주관연구개발기관 : 인텍", "ㅇ 공동연구개발기관 : 가나대", "ㅇ 공동연구개발기관 : 다라연"]
    for what in ("목표", "개발내용"):   # 요약문 — 전체 차년도마다 한 벌(당해 하나 아님)
        assert [p.strip() for p in ps if f"차년도 {what}]" in p] == [f"[{k}차년도 {what}]" for k in range(1, 6)], what
    ts = tables(doc)
    crit = [t for t in ts if {"구분", "평가환경"} <= {flat(c) for c in t["cells"] if c["row"] == 0}]   # 2-2 평가항목별 표준 표 — 평가항목마다 당해 차년도 행만
    assert len(crit) == 3 and all(col_texts(t, 1) == ["회수율", "정밀도"] and col_texts(t, 2) == ["1단계-1차년도"] * 2 for t in crit)
    cover = ts[1]
    r = next(c["row"] for c in cover["cells"] if (c["text"] or "").startswith("해당연도"))
    assert row_texts(cover, r)[1:] == ["1단계 1차년도14-3)", "2026. 03. 01 - 2026. 12. 31(10개월)"]
    perf = next(t for t in ts if any("성과지표명" in (c["text"] or "") for c in t["cells"]))
    assert row_texts(perf, 3) == ["2026", "2027", "2028", "2029", "2030"]
    assert [(flat(c), c["colSpan"]) for c in sorted(perf["cells"], key=lambda c: c["col"]) if c["row"] == 2 and flat(c).endswith("단계")] \
        == [("1단계", 2), ("2단계", 3)]
    nxt = [t for t in ts if any(c["row"] == 0 and c["col"] == 0 and flat(c) == "연구개발기관" for c in t["cells"])
           and any(c["row"] == 0 and c["col"] == 1 and flat(c).endswith("연도") for c in t["cells"])]
    assert len(nxt) == 6
    for t in nxt:
        assert col_texts(t, 0) == ["인텍", "가나대", "다라연"] and col_texts(t, 1) == ["2027", "2027", "2027"], t["id"]
    ind = next(t for t in nxt if any(flat(c) == "세부항목" for c in t["cells"]))   # 간접비 표 — 기관마다 첫 블록과 같은 꼴(연차(단계) 칸 + 세부항목 행)
    assert ind["nRows"] == 1 + 3 * 7 and [flat(c) for c in ind["cells"] if c["col"] == 2 and c["row"]] == ["2차(1단계)"] * 3 \
        and sum(flat(c) == "연구개발능률성과급" for c in ind["cells"]) == 3 and all(c["colSpan"] == 1 for c in ind["cells"])
    got = divisions.read_values(doc.blocks(), levels(doc.blocks()))
    assert got["stages"] == [2, 3] and got["current"] == 1 and got["period"] == FULL["period"]
    assert got["orgs"]["lead"] == "인텍" and got["orgs"]["joint"] == ["가나대", "다라연"] \
        and got["orgs"]["overseas"] == ["Fraunhofer (IPT)", "MIT"]
    again = divisions.apply(doc, divisions.norm_values(FULL), levels_of=levels)
    assert not again["groups"] and not again["changes"] and not again["errors"]


@needs_report
def test_report_small_apply():
    doc, rep = applied(SMALL)
    assert not rep["errors"]
    ps = paras(doc)
    assert not any(p.startswith("[국외기관") for p in ps)   # 국외기관 0곳 — 항목(뼈대 줄 포함)을 지움
    assert sum(p.strip().startswith("ㅇ (1차년도) 추진 내용 및 실적") for p in ps) == 1   # 주관만 · 단계 하나 = 「(y차년도)」
    assert not any(p.startswith("[공동연구개발기관") for p in ps)
    assert [p.strip() for p in ps if p.strip().startswith(("ㅇ 주관연구개발기관 :", "ㅇ 공동연구개발기관 :"))] == ["ㅇ 주관연구개발기관 : 주관기관(미입력)"]
    assert ps.count("[주관연구개발기관 : 주관기관(미입력)]") == 1
    ts = tables(doc)
    perf = next(t for t in ts if any("성과지표명" in (c["text"] or "") for c in t["cells"]))
    assert row_texts(perf, 3) == ["2026", "2027", "2028"]
    r = next(c["row"] for c in ts[1]["cells"] if (c["text"] or "").startswith("해당연도"))
    assert row_texts(ts[1], r)[1:] == ["1단계 1차년도14-3)", "2026. 03. 01 - 2026. 12. 31(10개월)"]
    nxt = [t for t in ts if any(c["row"] == 0 and c["col"] == 0 and flat(c) == "연구개발기관" for c in t["cells"])
           and any(c["row"] == 0 and c["col"] == 1 and flat(c).endswith("연도") for c in t["cells"])]
    assert len(nxt) == 6 and all(col_texts(t, 0) == ["주관기관(미입력)"] and col_texts(t, 1) == ["2027"] for t in nxt)


@needs_report
def test_report_current_year_and_next_year():
    """당해 2차년도(② §18, 사용자 2026-11-11): 2-2 「해당연도」 = 당해 차년도 · 「5. 다음 연도」 = 다음 차년도 · 평가항목 표는 그 차년도의 행을 글째 남김
    (첫 행 = 왼쪽 병합 칸이 시작하는 행도 지움) · 문서에서 읽은 당해 차년도 = 2 · 다시 반영하면 할 일 없음."""
    vals = {"stages": [3, 3], "orgs": {"lead": "가나", "joint": ["다라"]}, "period": {"start": "2027-04-01", "end": "2032-12-10"}, "current": 2}
    doc, rep = applied(vals)
    assert not rep["errors"]
    ps = [p.strip() for p in paras(doc)]
    assert sum(p.startswith("ㅇ (1단계-2차년도) 추진 내용 및 실적") for p in ps) == 2   # 주관·공동 1
    assert sum(p.startswith("ㅇ 참여연구자 인건비 현황표(1단계-3차년도)") for p in ps) == 2 \
        and sum(p.startswith("ㅇ 학생인건비 현황표(1단계-3차년도)") for p in ps) == 2 and not any("현황표(1단계-2차년도)" in p for p in ps)
    assert [p for p in ps if "차년도 목표]" in p] == [f"[{k}차년도 목표]" for k in range(1, 7)]
    ts = tables(doc)
    crit = [t for t in ts if {"구분", "평가환경"} <= {flat(c) for c in t["cells"] if c["row"] == 0}]
    assert len(crit) == 2
    for t in crit:
        assert t["nRows"] == 3 and row_texts(t, 1) == ["1", "회수율", "1단계-2차년도", "수요기업 평가", "수요기업의 품질요구서"] \
            and row_texts(t, 2)[:3] == ["2", "정밀도", "1단계-2차년도"], t["id"]
    ind = next(t for t in ts if any(c["row"] == 0 and flat(c) == "세부항목" for c in t["cells"]))
    assert col_texts(ind, 0) == ["가나", "다라"] and col_texts(ind, 1) == ["2029", "2029"] \
        and [flat(c) for c in ind["cells"] if c["col"] == 2 and c["row"]] == ["3차(1단계)"] * 2
    assert divisions.read_values(doc.blocks(), levels(doc.blocks()))["current"] == 2
    again = divisions.apply(doc, divisions.norm_values(vals), levels_of=levels, rebuild=False)
    assert not again["groups"] and not again["changes"] and not again["errors"]


# ---------------------------------------------------------------- 서버 — 지원 양식(spec_구분_기준 ② §17)

@needs_report
def test_report_api_plan_apply_change_and_same():
    """연차보고서를 올려 계획 → 반영(표준 검사 통과) → 값을 바꿔 다시 계획·반영(자리표시를 다시 본뜨는 길) → 같은 값 재계획 = 할 일 없음."""
    from fastapi.testclient import TestClient

    from app import server
    server.DOCS.clear()
    c = TestClient(server.app)
    d = c.post("/api/docs", files={"file": (REPORT.name, REPORT.read_bytes())}).json()["docId"]
    prof = c.get(f"/api/docs/{d}/divisions").json()["profile"]
    assert prof["form"] == "연차보고서" and prof["supported"] is True and "연차보고서" in prof["supportedForms"]
    for vals in (FULL, {**FULL, "stages": [3, 2], "orgs": {**FULL["orgs"], "joint": ["가나대", "다라연", "마바사"], "nonprofit": [False, True, False, False]}}):
        p = c.post(f"/api/docs/{d}/divisions/plan", json={"values": vals})
        assert p.status_code == 200, p.text
        s = p.json()["summary"]
        assert s["applied"] and not s["errors"] and not s["unresolved"] and not s["unsupported"]
        a = c.post(f"/api/docs/{d}/divisions/apply", json={"planId": p.json()["planId"]})
        assert a.status_code == 200, a.text
        assert a.json()["owpml"]["status"] == "ok" and a.json()["unresolved"] == []
    same = c.post(f"/api/docs/{d}/divisions/plan", json={}).json()
    assert same["summary"]["applied"] == 0 and same["summary"]["changes"] == 0
    texts = [b["text"] for b in c.get(f"/api/docs/{d}").json()["blocks"] if b["type"] == "paragraph"]
    assert [t for t in texts if t.startswith(("[주관연구개발기관 :", "[공동연구개발기관1 :", "[공동연구개발기관2 :", "[공동연구개발기관3 :"))] \
        == ["[주관연구개발기관 : 인텍]", "[공동연구개발기관1 : 가나대]", "[공동연구개발기관2 : 다라연]", "[공동연구개발기관3 : 마바사]"]   # 혼자인 주관 절 — 다시 반영해도 기관마다 하나
    assert sum(t.strip().startswith("ㅇ 참여연구자 인건비 현황표(") for t in texts) == 4   # 기관마다 하나(뒷부분이 쌓이지 않음)
    server.DOCS.clear()


# ---------------------------------------------------------------- 반영이 넣은 이름·연도(spec_구분_기준 ② §19) — 이름·당해 차년도를 바꾼 값으로 다시 반영

RENAMED = {**FULL, "orgs": {**FULL["orgs"], "lead": "새주관", "joint": ["새공동가", "새공동나"]}, "current": 2}
OLD_NAMES, NEW_NAMES = ["인텍", "가나대", "다라연"], ["새주관", "새공동가", "새공동나"]


def name_counts(doc, names):
    t = paras(doc)
    return {n: sum(n in x for x in t) for n in names}


def reasons(doc, vals, prior=None):
    return {c["reason"] for c in rnd.candidates(doc.blocks(), levels(doc.blocks()), vals, rebuild=False, prior=prior)}


@needs_report
def test_report_rename_reapply_needs_prior():
    """반영 뒤 기관 이름·당해 차년도를 바꾼 값 — 앞서 반영한 값을 안 넘기면(prior 없음) 옛 이름 자리는 작성한 문서로 보고 그대로(까닭 named),
    넘기면 자리 차례대로 새 이름·새 연도로: 깨끗한 서식에 새 값을 한 번 반영한 것과 같은 수. 이미 그렇게 남은 문서도 같은 값으로 다시 계획하면 고쳐진다."""
    old, new = divisions.norm_values(FULL), divisions.norm_values(RENAMED)
    clean = HwpxDoc(REPORT.read_bytes())
    assert not divisions.apply(clean, new, levels_of=levels, prior=[])["errors"]
    want = name_counts(clean, NEW_NAMES)
    assert all(want.values()) and reasons(clean, new, []) == {"done"}

    doc = HwpxDoc(REPORT.read_bytes())
    divisions.apply(doc, old, levels_of=levels)
    divisions.apply(doc, new, levels_of=levels)   # prior 없음 — 전과 같은 보호
    assert all(name_counts(doc, OLD_NAMES).values())
    left = reasons(doc, new)
    assert "named" in left and "irregular" not in left

    r = divisions.apply(doc, new, levels_of=levels, rebuild=False, prior=[old])   # 그 문서를 같은 값으로 다시 — 앞서 반영한 값을 넘김(서버가 하는 일)
    assert not r["errors"] and r["groups"]
    assert name_counts(doc, OLD_NAMES) == {n: 0 for n in OLD_NAMES} and name_counts(doc, NEW_NAMES) == want
    assert reasons(doc, new, [old]) == {"done"}

    direct = HwpxDoc(REPORT.read_bytes())   # 고친 뒤의 보통 길: 옛 값 → 새 값
    divisions.apply(direct, old, levels_of=levels, prior=[])
    r = divisions.apply(direct, new, levels_of=levels, prior=[old])
    assert not r["errors"]
    assert name_counts(direct, OLD_NAMES) == {n: 0 for n in OLD_NAMES} and name_counts(direct, NEW_NAMES) == want
    assert reasons(direct, new, [old]) == {"done"}


@needs_report
def test_report_foreign_names_stay_protected():
    """앞서 반영한 값에도 없는 이름(사람이 적은 이름)이 든 자리는 prior 를 넘겨도 그대로 둔다 — 보호의 뜻은 그대로(② §19 「판정」)."""
    old, new = divisions.norm_values(FULL), divisions.norm_values(RENAMED)
    stranger = divisions.norm_values({**FULL, "orgs": {**FULL["orgs"], "lead": "남의주관", "joint": ["남의공동가", "남의공동나"]}})
    doc = HwpxDoc(REPORT.read_bytes())
    divisions.apply(doc, stranger, levels_of=levels)   # 문서에 「남의…」 이름이 적힘 — 엔진에는 이 값을 알리지 않는다
    divisions.apply(doc, new, levels_of=levels, prior=[old])
    assert all(name_counts(doc, ["남의주관", "남의공동가", "남의공동나"]).values())
    assert "named" in reasons(doc, new, [old])


def _cell(i, row, col, text, rs=1):
    return {"id": f"c{i}", "row": row, "col": col, "rowSpan": rs, "colSpan": 1, "text": text, "blocks": [{"id": f"p{i}", "type": "paragraph", "text": text}]}


def _name_table(names, head="연구개발기관"):
    cells = [_cell(0, 0, 0, head), _cell(1, 0, 1, "금액")]
    for r, n in enumerate(names, 1):
        cells += [_cell(10 + r, r, 0, n), _cell(20 + r, r, 1, "")]
    return {"id": "t1", "type": "table", "cells": cells, "nRows": len(names) + 1, "nCols": 2}


def test_own_rows_only_whole_name_order():
    """이름 칸 행 묶음(② §19)은 한 열의 맞닿은 칸 글이 한 값의 기관 이름 차례와 통째로 같을 때만 — 일부만·차례가 다른 표(작성한 표)·머리에 「기관」 없는 열·
    다른 기관 묶음이 이미 가진 칸은 안 잡는다. 이름이 하나뿐인 값은 차례를 만들지 않는다."""
    sigs = divisions._name_sigs(divisions.norm_values({"stages": [1], "orgs": {"lead": "가", "joint": ["나", "다"]}}),
                                [divisions.norm_values({"stages": [1], "orgs": {"lead": "혼자", "joint": []}})])
    assert sigs == [["가", "나", "다"]]
    g = divisions._own_rows(_name_table(["가", "나", "다"]), set(), sigs)
    assert len(g) == 1 and g[0]["ownRows"] and g[0]["dim"] == ORG and g[0]["kind"] == "rows"
    assert [it["value"] for it in g[0]["items"]] == [("lead", 0), ("joint", 1), ("joint", 2)]
    assert [it["label"] for it in g[0]["items"]] == ["c11", "c12", "c13"] and all(it["nameAts"] == [0] for it in g[0]["items"])
    assert divisions._own_rows(_name_table(["가", "다"]), set(), sigs) == []          # 일부만
    assert divisions._own_rows(_name_table(["나", "가", "다"]), set(), sigs) == []    # 차례가 다름
    assert divisions._own_rows(_name_table(["가", "나", "다"]), {"c12"}, sigs) == []  # 다른 기관 묶음이 가진 칸
    assert divisions._own_rows(_name_table(["가", "나", "다"], head="구분"), set(), sigs) == []   # 머리 칸에 「기관」 없음
    more = divisions._own_rows(_name_table(["가", "나", "다", "소계"]), set(), sigs)   # 뒤에 소계 행이 있어도 이름 줄만
    assert len(more) == 1 and len(more[0]["items"]) == 3


@needs_report
def test_report_api_rename_reapply():
    """서버: 반영 뒤 이름·당해 차년도를 바꾼 값으로 다시 계획하면 지원 안 됨 없이 새 이름으로 — 반영한 값을 서버가 쌓아 엔진에 넘긴다(② §19).
    쌓은 값이 없는 옛 작업은 작업 폴더의 반영 상세 기록에서 모은다."""
    from fastapi.testclient import TestClient

    from app import server
    server.DOCS.clear()
    c = TestClient(server.app)
    d = c.post("/api/docs", files={"file": (REPORT.name, REPORT.read_bytes())}).json()["docId"]
    for vals in (FULL, RENAMED):
        p = c.post(f"/api/docs/{d}/divisions/plan", json={"values": vals})
        assert p.status_code == 200, p.text
        s = p.json()["summary"]
        assert s["applied"] and not s["errors"] and not s["unresolved"] and not s["unsupported"], s
        a = c.post(f"/api/docs/{d}/divisions/apply", json={"planId": p.json()["planId"]})
        assert a.status_code == 200, a.text
        assert a.json()["unresolved"] == []
    texts = [t for t in server.verify.flat_texts(server.DOCS[d].doc.blocks()).values()]
    assert not any(n in t for t in texts for n in OLD_NAMES) and all(any(n in t for t in texts) for n in NEW_NAMES)
    same = c.post(f"/api/docs/{d}/divisions/plan", json={}).json()
    assert same["summary"]["applied"] == 0 and same["summary"]["changes"] == 0 and same["summary"]["unsupported"] == 0
    s = server.DOCS[d]
    assert [v["orgs"]["lead"] for v in s.division["prior"]] == ["인텍", "새주관"]
    if server.works.folder(d) is not None:   # 옛 작업 — 쌓은 값이 없으면 반영 상세 기록에서
        s.division["prior"] = None
        assert [v["orgs"]["lead"] for v in server._division_prior(s)] == ["인텍", "새주관"]
    assert c.get(f"/api/docs/{d}/divisions").json()["profile"]["version"] == rnd.VERSION >= 6
    server.DOCS.clear()
