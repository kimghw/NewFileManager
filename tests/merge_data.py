"""병합 시험 자료(spec_병합 ② §9) — 두 문서(원본 사업계획서 · 목적 연차보고서)와 그 추출 결과(헤딩 그래프·표 구조, 스크립트만)를 만든다.

- `analyze(doc)` = 서버의 첫 분석(heading_runs.run_first)과 같은 차례를 세션 없이: 1단계 추출 → TEMP 라벨 → 2단계 그래프 → 3단계 표 구조. LLM 없음.
- `real()` = 실제 작성본(FMM `연구계획서.hwpx` — 없으면 None) ↔ 그 문서에서 읽은 구분 값으로 반영한 연차보고서 서식.
- `small()` = 저장소 안 자료만: 빈 계획서 양식에 값을 반영하고 몇 자리에 글을 넣은 것 ↔ 같은 값으로 반영한 연차보고서 서식.
추출 결과는 느리므로(작성본 47 MB) 문서 바이트 sha 로 `artifacts/merge_fixture/` 에 gz 로 둔다(git 무시 폴더)."""
import gzip
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).parents[1]
REAL_PLAN = Path(os.environ.get("NFM_MERGE_REAL_PLAN") or r"E:\dev\FileMergeManager\연구계획서.hwpx")
PLAN_FORM = ROOT / "samples" / "연구개발계획서_양식.hwpx"
REPORT_FORM = ROOT / "samples" / "국가RnD_서식" / "KEIT_표준서식_260320" / "1. 산업기술혁신사업 연차보고서 서식_260319.hwpx"
CACHE = ROOT / "artifacts" / "merge_fixture"
SMALL_VALUES = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]},
                "period": {"start": "2026-03-01", "end": "2027-12-31"}, "current": 1}
_MEMO = {}


def analyze(doc, name=""):
    """문서 → (stage1, graph, tables) — 스크립트만(지침은 지금 저장소 것, 사용자 지정 없음)."""
    from app import heading_extract as E
    from app import heading_graph as HG
    from app import heading_guides as G
    from app import heading_rules as R
    from app import heading_tables as HT
    from app import heading_temp as TP
    guides = G.snapshot()
    s1 = E.extract(doc, store=R.load(), doc_key=None, tol=G.parse_tolerance(guides["tolerance"]["text"]))
    s1["meta"] = {"rev": 0, "run": 1}
    temp = TP.label(s1, None)
    hints = {"version": 0, "labels": {}, "bases": [], "temp": TP.clean_hints(None)}
    g = HG.build(s1, use_llm=False, doc_name=name, pinned=guides, hints=hints, temp=temp)
    g.pop("_calls", None)
    g["meta"] = {"rev": 0, "stage1Run": 1, "run": 2}
    t = HT.build(s1, use_llm=False, doc_name=name, pinned=guides, stage2=g, temp=temp, roles={})
    t.pop("_calls", None)
    return s1, g, t


def _cached(tag, data, doc, name):
    """문서 바이트 sha 로 (graph, tables)를 캐시 — 추출 코드가 바뀌어 결과가 달라져야 하면 폴더를 지운다."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{tag}-{hashlib.sha256(data).hexdigest()[:16]}.json.gz"
    if p.is_file():
        d = json.loads(gzip.decompress(p.read_bytes()))
        return d["graph"], d["tables"]
    _, g, t = analyze(doc, name)
    p.write_bytes(gzip.compress(json.dumps({"graph": g, "tables": t}, ensure_ascii=False).encode("utf-8")))
    return g, t


def _side(tag, doc, name):
    """그 문서를 바이트로 낸 뒤 **다시 읽은 것**이 기준이다 — 블록 id 는 읽을 때 차례로 매겨져, 구조를 고친 메모리 문서와 그 바이트를 다시 읽은 문서의 id 가 다르다.
    추출 결과(graph·tables)의 id 와 `fresh()` 사본의 id 가 같아야 하므로 다시 읽은 문서로 추출한다."""
    from app import hwpx_struct
    from app.hwpx_doc import HwpxDoc
    data = hwpx_struct.snapshot(doc)["bytes"]
    doc = HwpxDoc(data)
    g, t = _cached(tag, data, doc, name)
    return {"doc": doc, "bytes": data, "graph": g, "tables": t, "name": name}


def _report(values):
    """연차보고서 서식에 values 를 반영한 문서(목적 문서의 사전 조건 — spec_병합 ② §3)."""
    from app.division_profiles import rnd
    from app.division_profiles.rnd import core
    from app.hwpx_doc import HwpxDoc
    doc = HwpxDoc(REPORT_FORM.read_bytes())
    rep = core.apply(doc, values, levels_of=rnd.levels_of)
    assert not rep["errors"], rep["errors"]
    return doc


def real():
    """실제 작성본 쌍 {"values", "from": {doc, bytes, graph, tables, name}, "to": {…}} | None(작성본 없음). 한 번 만들면 프로세스 안에서 다시 쓴다(문서를 고치는 시험은 `fresh` 로 사본을)."""
    if "real" not in _MEMO:
        if not REAL_PLAN.is_file() or not REPORT_FORM.is_file():
            _MEMO["real"] = None
        else:
            from app.division_profiles import rnd
            from app.division_profiles.rnd import core
            from app.hwpx_doc import HwpxDoc
            plan = HwpxDoc(REAL_PLAN.read_bytes())
            blocks = plan.blocks()
            values = core.norm_values(rnd.read_values(blocks, rnd.levels_of(blocks)))
            _MEMO["real"] = {"values": values, "from": _side("real-plan", plan, REAL_PLAN.name), "to": _side("real-report", _report(values), REPORT_FORM.name)}
    return _MEMO["real"]


SMALL_MARK = "★병합시험"


def small():
    """저장소 안 자료만으로 만든 쌍 — 빈 계획서 양식에 SMALL_VALUES 를 반영하고, 구분 기준 문단 묶음의 항목마다 라벨 바로 뒤에
    「★병합시험 <묶음 key> <값>」 한 줄을 넣은 것(원본) ↔ 같은 값으로 반영한 연차보고서(목적). 넣은 줄로 「어느 항목의 내용이 어디로 갔나」를 시험이 센다."""
    if "small" not in _MEMO:
        from app.division_profiles import rnd
        from app.division_profiles.rnd import core
        from app.hwpx_doc import HwpxDoc
        values = core.norm_values(SMALL_VALUES)
        plan = HwpxDoc(PLAN_FORM.read_bytes())
        assert not core.apply(plan, values, levels_of=rnd.levels_of)["errors"]
        blocks = plan.blocks()
        top = {b["id"] for b in blocks}
        for g in rnd.members(blocks, rnd.levels_of(blocks), values)["groups"]:
            if g["kind"] != "paragraph" or g["where"].get("cell"):
                continue
            for it in g["items"]:
                if it.get("label") in top:
                    plan.insert_after(it["label"], [{"kind": "paragraph", "text": f"{SMALL_MARK} {g['key']} {it['value']}"}])
        _MEMO["small"] = {"values": values, "from": _side("small-plan", plan, PLAN_FORM.name), "to": _side("small-report", _report(values), REPORT_FORM.name)}
    return _MEMO["small"]


def fresh(side):
    """그 쪽 문서의 독립 사본(문서를 고치는 시험용) — 블록 id 는 같다."""
    from app.hwpx_doc import HwpxDoc
    return HwpxDoc(side["bytes"])
