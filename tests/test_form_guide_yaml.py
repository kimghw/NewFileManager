"""양식 지침 YAML(app/form_guide_yaml.py — spec_양식작성 ② §5-8): 꼴 검사 · 정규화 · 문서 자리 잇기(절 · 표 · 서브 테이블 · 칸) · 후보 · 올리기 · 예시 · 판 충돌 · place_guides 로 읽기."""
import pytest

from app import form_guide_yaml as FG
from app import guide_write
from app import place_guides as PG


def _p(i, text=""):
    return {"id": i, "type": "paragraph", "text": text}


def _c(r, c, text, shaded=False):
    return {"id": f"c{r}{c}", "row": r, "col": c, "shaded": shaded, "blocks": [_p(f"q{r}{c}", text)]}


def _table(tid, heads, rows=1, cid=""):
    cells = [{**_c(0, j, h, True), "id": f"{tid}c0{j}", "blocks": [_p(f"{tid}q0{j}", h)]} for j, h in enumerate(heads)]
    for r in range(1, rows + 1):
        cells += [{**_c(r, j, f"값{r}{j}"), "id": f"{tid}c{r}{j}", "blocks": [_p(f"{tid}q{r}{j}", "")]} for j in range(len(heads))]
    return {"id": tid, "type": "table", "cells": cells}


# 문서: 「1. 개요」 › 「1-1. 목표」(표 t1 머리 「구분 | 목표」) · 「2. 수행 내용」 › 「[주관연구개발기관명 : 한국선급]」 · 「[공동연구개발기관명1 : 인텍]」(기관마다 되풀이 — 표 t2 · t3 같은 머리)
BLOCKS = [
    _p("h1", "1. 개요"), _p("h2", "1-1. 목표"), _table("t1", ["구분", "목표"]),
    _p("h3", "2. 수행 내용"),
    _p("h4", "[주관연구개발기관명 : 한국선급]"), _table("t2", ["평가항목", "1차년도 목표"]),
    _p("h5", "[공동연구개발기관명1 : 인텍]"), _table("t3", ["평가항목", "2차년도 목표"]),
    _p("h6", "3. 예산"), _table("t4", ["비목", "금액"]), _table("t5", ["비목", "금액"]),
]
GRAPH = {"nodes": [
    {"id": "n1", "para": "h1", "role": "heading", "area": "body", "parent": None, "text": "1. 개요"},
    {"id": "n2", "para": "h2", "role": "heading", "area": "body", "parent": "n1", "text": "1-1. 목표"},
    {"id": "n3", "para": "h3", "role": "heading", "area": "body", "parent": None, "text": "2. 수행 내용"},
    {"id": "n4", "para": "h4", "role": "heading", "area": "body", "parent": "n3", "text": "[주관연구개발기관명 : 한국선급]"},
    {"id": "n5", "para": "h5", "role": "heading", "area": "body", "parent": "n3", "text": "[공동연구개발기관명1 : 인텍]"},
    {"id": "n6", "para": "h6", "role": "heading", "area": "body", "parent": None, "text": "3. 예산"},
]}
T3 = [{"id": "t1", "subtables": [{"id": "b1", "rows": [0, 1], "cols": [0, 2], "headerRows": 1, "headerCols": 0},
                                 {"id": "b2", "rows": [1, 2], "cols": [0, 2], "headerRows": 1, "headerCols": 0}],
       "cells": [{"row": 0, "col": 0, "text": "구분", "role": "colhead"}, {"row": 0, "col": 1, "text": "목표", "role": "colhead"},
                 {"row": 1, "col": 0, "text": "세부", "role": "colhead"}, {"row": 1, "col": 1, "text": "", "role": "field"}]}]

YAML = """
schema: 1
form: 연차보고서
theme: rnd
keywords:
  - id: period
    name: 전체 연구개발기간
    output: period
    labels: ["1-1. 목표"]
sections:
  - id: s1
    path: ["1. 개요", "1-1. 목표"]
    guides:
      - text: 최종 목표를 한 문장으로.
    examples:
      - text: 선박 배출가스를 30% 줄이는 시스템 개발
        note: 문체 예
    tables:
      - id: s1.t1
        head: 구분 | 목표
        guides: [표는 차년도마다 한 행.]
        fields:
          - label: 목표
            guides: [정량 목표만.]
        subtables:
          - id: s1.t1.b2
            head: 세부
            guides: [세부 행에는 세부 목표.]
  - id: s2
    path: ["2. 수행 내용", "[주관연구개발기관명 : ]"]
    guides: [주관기관의 당해 실적만.]
    tables:
      - id: s2.t1
        head: 평가항목 | N차년도 목표
        guides: [평가항목마다 한 행.]
  - id: s3
    path: ["3. 예산"]
    tables:
      - id: s3.t1
        head: 비목 | 금액
        guides: [첫 표 = 정부지원.]
      - id: s3.t2
        head: 비목 | 금액
        guides: [둘째 표 = 기관부담.]
  - id: s9
    path: ["9. 없는 절"]
    guides: [안 닿음]
"""


def _places():
    return FG.doc_places(BLOCKS, GRAPH, T3)


def test_norm_cuts_values_and_division_numbers_only():
    assert FG.norm("[주관연구개발기관명 : 한국선급]") == FG.norm("[주관연구개발기관명 : ]") == "[주관연구개발기관명]"
    assert FG.norm("[공동연구개발기관명1 : 인텍]") == FG.norm("[공동연구개발기관명2 : 다른곳]")
    assert FG.norm("ㅇ (1단계-2차년도) 추진 내용 및 실적") == FG.norm("ㅇ (2단계-3차년도) 추진 내용 및 실적")
    assert FG.norm("1단계 (해당 시 작성)") == FG.norm("1단계")
    assert FG.norm("2-2. 평가항목") != FG.norm("2-3. 평가항목")   # 개요 번호는 그대로
    assert FG.norm("<참고 1>") != FG.norm("<참고 2>")   # 구분 기준이 아닌 숫자는 그대로(Fable P1-4)
    assert FG.norm("가. 목표 ※ 1쪽 이내") == FG.norm("가. 목표")


def test_parse_dump_roundtrip_and_strict_errors():
    d = FG.parse(YAML, "연차보고서")
    assert [s["id"] for s in d["sections"]] == ["s1", "s2", "s3", "s9"]
    assert d["sections"][0]["guides"][0] == {"text": "최종 목표를 한 문장으로.", "origin": "user"}
    again = FG.parse(FG.dump(d), "연차보고서")
    assert again == d
    with pytest.raises(ValueError, match="양식 키"):
        FG.parse(YAML, "연구개발계획서")
    with pytest.raises(ValueError, match="두 번"):
        FG.parse("form: x\nsections:\n  - {id: a, path: [가]}\n  - {id: a, path: [나]}\n", "x")
    with pytest.raises(ValueError, match="output"):
        FG.parse("form: x\nkeywords:\n  - {id: k, name: 기관, output: 엉뚱}\n", "x")
    loose = FG.parse("form: x\nsections:\n  - {id: a, path: [가]}\n  - {id: a, path: [나]}\n  - {id: 'bad id', path: [다]}\n", "x", strict=False)
    assert [s["path"] for s in loose["sections"]] == [["가"]]   # 깨진 항목만 빠진다


def test_locate_sections_tables_subtables_fields():
    d = FG.parse(YAML, "연차보고서")
    got = FG.locate(d, _places(), BLOCKS)
    assert [g["text"] for g in got["heads"]["h2"]] == ["최종 목표를 한 문장으로."]
    t1 = got["tables"]["t1"]
    assert [g["text"] for g in t1] == ["표는 차년도마다 한 행.", "정량 목표만.", "세부 행에는 세부 목표."]
    field = next(g for g in t1 if g["text"] == "정량 목표만.")
    assert field["cell"] == "r0c1" and "목표" in field["label"]
    band = next(g for g in t1 if g["text"] == "세부 행에는 세부 목표.")
    assert band["band"] == "b2" and band["label"].startswith("서브 테이블")
    assert all(g["src"] == "form" and g["kind"] == FG.KIND for g in t1)
    assert got["examples"]["h2"][0]["note"] == "문체 예"


def test_repeated_section_reads_same_entry_and_tables_pair_in_order():
    got = FG.locate(FG.parse(YAML, "연차보고서"), _places(), BLOCKS)
    assert set(got["links"]["s2"]) == {"h4"}   # 공동기관 절은 주관 절과 경로가 다르다(정규화해도 「주관」 ≠ 「공동」)
    assert [g["text"] for g in got["tables"]["t2"]] == ["평가항목마다 한 행."]
    assert "t3" not in got["tables"]
    assert [g["text"] for g in got["tables"]["t4"]] == ["첫 표 = 정부지원."]   # 같은 머리글 둘 ↔ 문서도 둘 — 차례대로
    assert [g["text"] for g in got["tables"]["t5"]] == ["둘째 표 = 기관부담."]
    assert any(u["id"] == "s9" and u["kind"] == "section" for u in got["unmatched"])


def test_ambiguous_tables_are_not_guessed():
    d = FG.parse(YAML, "연차보고서")
    blocks = BLOCKS + [_table("t6", ["비목", "금액"])]   # 같은 절에 같은 머리글 표 셋 ↔ YAML 둘
    got = FG.locate(d, FG.doc_places(blocks, GRAPH, T3), blocks)
    assert "t4" not in got["tables"] and "t6" not in got["tables"]
    assert {u["id"] for u in got["unmatched"] if u["kind"] == "table"} >= {"s3.t1", "s3.t2"}


def test_candidates_promote_and_example():
    d = FG.parse("form: 연차보고서\n", "연차보고서")
    places = _places()
    cands = FG.candidates(d, places, user_heads={"h4": {"text": "한국선급의 실적만 적는다", "label": "x"}},
                          table_user={"t1": "행은 차년도마다"}, rules={"h2": [{"instruction": "한 문장 요약", "basis": "explicit"}], "zz": [{"instruction": "자리 없음"}]},
                          words=FG._value_words({"orgs": {"names": ["한국선급", "인텍"]}}))
    by = {c["key"].rsplit(":", 1)[0]: c for c in cands}   # key = 「출처:자리:지문」 — 지문은 글 · 대상 · 출처로 만든다(2026-11-26: 전의 「l:<자리>:<순번>」 은 04 를 다시 돌리면 다른 글을 가리켰다 — tests/test_form_rules.py 가 따로 본다)
    assert set(by) == {"u:h4", "u:t1", "l:h2"}   # 자리를 못 정한 것은 후보가 아니다
    assert by["u:h4"]["warn"] and "한국선급" in by["u:h4"]["warn"][0]
    assert by["u:t1"]["kind"] == "table" and by["l:h2"]["origin"] == "llm"
    n = FG.promote(d, places, [by["u:t1"], by["l:h2"], by["u:h4"]], work="w1", date="2026-11-26")
    assert n == 3
    again = FG.candidates(d, places, table_user={"t1": "행은 차년도마다"})
    assert again[0]["saved"] is True
    assert FG.promote(d, places, [by["u:t1"]]) == 0   # 같은 글은 두 번 안 올린다
    sec = next(s for s in d["sections"] if s["path"] == ["1. 개요", "1-1. 목표"])
    assert sec["guides"][0]["origin"] == "llm" and sec["tables"][0]["guides"][0]["from"] == "w1"
    nid = FG.add_example(d, places, "t1", "예시 글", band_id="b2", note="세부 꼴")
    assert nid.startswith(sec["tables"][0]["id"] + ".b")
    with pytest.raises(ValueError):
        FG.add_example(d, places, "t1", "x", band_id="없음")
    d2 = FG.parse(FG.dump(d), "연차보고서")
    got = FG.locate(d2, places, BLOCKS)
    assert "한국선급의 실적만 적는다" in [g["text"] for g in got["heads"]["h4"]]
    assert got["examples"]["t1"][0]["label"].startswith("서브 테이블")


def test_save_expect_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_FORMS", str(tmp_path))
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "h"))
    d, text, sha = FG.read("연차보고서")
    assert text is None and sha == ""
    sha1 = FG.save("연차보고서", FG.parse(YAML, "연차보고서"), expect="")
    with pytest.raises(FG.StaleVersion):
        FG.save("연차보고서", d, expect="")
    d2, text2, sha2 = FG.read("연차보고서")
    assert sha2 == sha1 and len(d2["sections"]) == 4 and text2.startswith("# 양식 지침")
    with pytest.raises(ValueError):
        FG.save_text("연차보고서", "form: 연차보고서\nsections: [{id: a}]\n", expect=sha1)
    FG.save_text("연차보고서", "form: 연차보고서\n", expect=sha1)
    assert list((tmp_path / "h" / "forms_history" / "연차보고서.guide").glob("*.yaml"))


def test_place_guides_index_and_guide_write_read_form_layer():
    got = FG.locate(FG.parse(YAML, "연차보고서"), _places(), BLOCKS)
    ix = PG.index({"items": [{"id": "g1", "text": "문서의 ※", "heading": {"id": "h2", "text": "1-1. 목표"}, "top": 1}]}, BLOCKS, ["t1"],
                  {"heads": {"h2": {"text": "사람 지침"}}}, None, None, got)
    assert [g["src"] for g in ix["heads"]["h2"]] == ["user", "form", "doc"]   # 사람 → 양식 지침 → 문서
    assert ix["examples"]["h2"]
    pl = guide_write.places(BLOCKS, GRAPH, ix)
    head = next(p for p in pl if p["id"] == "h2")
    req = guide_write.request(head)
    assert "(양식 지침) 최종 목표를 한 문장으로." in req
    assert "작성 예시(양식 지침" in req and "선박 배출가스" in req
    text = guide_write.guides_text(ix["tables"]["t1"])
    assert "(양식 지침 · 서브 테이블 「세부」" in text
    assert PG.sig(ix["heads"]["h2"]) != PG.sig([g for g in ix["heads"]["h2"] if g["src"] != "form"])   # 양식 지침이 바뀌면 그 자리를 다시 묻는다


def test_example_text_and_keywords():
    assert FG.example_text([]) == ""
    long = FG.example_text([{"text": "가" * 900, "note": "n"}])
    assert len(long.split("\n", 1)[1]) == FG.EXAMPLE_SEND and "옮기지 않습니다" in long
    kw = FG.keywords_found(FG.parse(YAML, "연차보고서"), BLOCKS)
    assert kw == [{"id": "period", "name": "전체 연구개발기간", "output": "period", "at": ["h2"]}]


# ---- 끝점(실제 샘플 문서) --------------------------------------------------------------------------------------

def test_api_promote_reads_back_as_form_layer(monkeypatch):
    import time as _t
    from pathlib import Path
    from fastapi.testclient import TestClient
    from app import heading_forms as HF
    from app import server
    sample = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
    server.DOCS.clear()
    c = TestClient(server.app)
    d = c.post("/api/docs", files={"file": (sample.name, sample.read_bytes())}).json()["docId"]
    assert c.post(f"/api/docs/{d}/headings", json={"first": True}).status_code == 202
    end = _t.time() + 120
    while _t.time() < end:
        v = c.get(f"/api/docs/{d}/headings").json()
        if v["job"] and v["job"]["status"] != "running":
            break
        _t.sleep(0.05)
    assert c.get(f"/api/docs/{d}/form-guide").json()["form"] is None   # 양식이 없으면 쓰지 않는다
    HF.save("시험", '# 시험\n\n```json\n{"name": "시험", "match": {"names": ["*연구개발계획서*"], "sha256": []}}\n```\n', expect="")
    v = c.get(f"/api/docs/{d}/form-guide").json()
    assert v["form"]["how"] == "name" and v["writable"] is False and "파일 이름" in v["why"]
    HF.set_choice(d, "시험")
    s = server.DOCS[d]
    from app import heading_runs
    pid = next(n["para"] for n in heading_runs.graph(s)["nodes"] if FG._is_head(n))
    assert c.put(f"/api/docs/{d}/place-guides/heads/{pid}", json={"text": "이 절은 1쪽 이내"}).status_code == 200
    v = c.get(f"/api/docs/{d}/form-guide").json()
    assert v["writable"] and v["exists"] is False
    cand = next(x for x in v["candidates"] if x["place"] == pid)
    assert c.post(f"/api/docs/{d}/form-guide/promote", json={"keys": [cand["key"]], "sha1": "zzz"}).status_code == 409
    r = c.post(f"/api/docs/{d}/form-guide/promote", json={"keys": [cand["key"]], "sha1": v["sha1"]}).json()
    assert r["added"] == 1 and r["exists"] and r["counts"]["guides"] == 1
    y = c.get("/api/form-guides/시험/yaml").json()
    assert "이 절은 1쪽 이내" in y["text"] and y["sha1"] == r["sha1"]
    assert c.put(f"/api/docs/{d}/place-guides/heads/{pid}", json={"text": ""}).status_code == 200   # 작업의 사람 지침을 지워도
    at = c.get(f"/api/docs/{d}/place-guides/at/{pid}").json()
    items = [i for L in at["layers"] for i in L["items"]]
    assert any(i["src"] == "form" and i["text"] == "이 절은 1쪽 이내" for i in items)   # 양식 지침으로 남아 읽힌다
    bad = c.put("/api/form-guides/시험/yaml", json={"text": "form: 다른\n", "sha1": y["sha1"]})
    assert bad.status_code == 400
    ok = c.post(f"/api/docs/{d}/form-guide/example", json={"place": pid, "text": "예: 한 문단 요약", "sha1": y["sha1"]})
    assert ok.status_code == 200 and ok.json()["counts"]["examples"] == 1
    server.DOCS.clear()


def test_skeleton_lays_sections_tables_and_subtables_in_doc_order():
    d = FG.parse("form: 연차보고서\nsections:\n  - id: s1\n    path: ['1. 개요', '1-1. 목표']\n    guides: [있던 지침]\n", "연차보고서")
    n = FG.skeleton(d, _places())
    assert n > 0 and FG.skeleton(d, _places()) == 0   # 두 번째는 더할 것이 없다
    paths = [s["path"] for s in d["sections"]]
    assert paths[0] == ["1. 개요", "1-1. 목표"] and d["sections"][0]["guides"][0]["text"] == "있던 지침"   # 있던 것은 그대로
    assert ["1. 개요"] in paths and ["3. 예산"] in paths
    s1 = d["sections"][0]
    assert s1["tables"][0]["head"] == "구분 | 목표" and [b["head"] for b in s1["tables"][0]["subtables"]] == ["구분 | 목표", "세부"]
    budget = next(s for s in d["sections"] if s["path"] == ["3. 예산"])
    assert len(budget["tables"]) == 1   # 같은 머리글 표 둘은 항목 하나(둘 다 그것을 읽는다)
    FG.parse(FG.dump(d), "연차보고서")   # 깐 것도 꼴 검사를 지난다
