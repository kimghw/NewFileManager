"""규정 YAML(app/form_rules.py — spec_양식작성 ② §5-9) + 지침의 조립 규칙(app/place_guides.py: 같은 글 하나 · 출처 순위 · 끄기 · 문서 전체 묶음 · 세 소비자가 같은 결과) +
검토 P1 의 음성 시험(긴 머리글의 지문 · 후보 key · 블록 id 가 든 규칙 · 모르는 origin · 헤딩마다 짝짓기) + 지침 보정의 넓힘(조립된 지침 · 「맞음」)."""
import pytest

import test_form_guide_yaml as D
from app import form_guide_yaml as FG
from app import form_rules as FR
from app import guide_fix as GF
from app import guide_write
from app import place_guides as PG
from app import writing_guidance as W

RULES = """
schema: 1
form: 연차보고서
rules:
  - id: r1
    text: 목표는 정량 지표로 적는다.
    source: {name: 관리규정, clause: 제5조, date: 2026-01-01}
    required: true
    applies: 2차년도 이상 과제
    targets:
      - path: ["1. 개요", "1-1. 목표"]
  - id: r2
    text: 표의 목표 칸은 수치와 단위를 함께 적는다.
    required: false
    targets:
      - path: ["1. 개요", "1-1. 목표"]
        table: 구분 | 목표
        field: 목표
  - id: r3
    text: 본문은 10쪽 이내로 쓴다.
    source: {name: 작성지침서}
  - id: r4
    text: 없는 절의 요구
    targets:
      - path: ["9. 없는 절"]
  - id: r5
    text: 개요 전체에 닿는 요구
    targets:
      - path: ["1. 개요"]
"""


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    """헤딩 저장소(양식 파일의 이력 history.jsonl · forms_history)도 임시 폴더로 — 규정을 저장하는 시험이 사용자의 저장소(%LOCALAPPDATA%)에 쓰지 않게."""
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "headings"))


def _places():
    return FG.doc_places(D.BLOCKS, D.GRAPH, D.T3)


def test_parse_checks_the_shape_and_round_trips():
    d = FR.parse(RULES, "연차보고서")
    assert [r["id"] for r in d["rules"]] == ["r1", "r2", "r3", "r4", "r5"] and d["rules"][0]["required"] is True and d["rules"][1]["required"] is False
    assert d["rules"][2]["targets"] == [] and d["rules"][0]["source"] == {"name": "관리규정", "clause": "제5조", "date": "2026-01-01"}
    assert FR.parse(FR.dump(d), "연차보고서") == d   # 저장한 글을 다시 읽으면 같다 · 머리 주석은 사람이 읽는 안내
    assert FR.dump(d).startswith("# 규정 — 연차보고서")
    for bad in ("form: 연차보고서\nrules:\n  - {id: a, text: t, targets: [{table: 구분}]}\n",          # 자리에는 path 가 있어야 한다(표만으로 문서 전체를 뒤지지 않는다)
                "form: 연차보고서\nrules:\n  - {id: a, text: t, targets: [{path: [x], field: 목표}]}\n",   # 칸은 그 표와 함께
                "form: 연차보고서\nrules:\n  - {id: a, text: t, required: 가끔}\n",
                "form: 연차보고서\nrules:\n  - {id: a, text: t}\n  - {id: a, text: u}\n",
                "form: 연차보고서\nrules:\n  - {id: a}\n", "form: 다른양식\nrules: []\n"):
        with pytest.raises(ValueError):
            FR.parse(bad, "연차보고서")
    loose = FR.parse("form: 연차보고서\nrules:\n  - {id: a, text: t, targets: [{table: 구분}]}\n  - {id: b, text: u}\n", "연차보고서", strict=False)
    assert [r["id"] for r in loose["rules"]] == ["b"]   # 자리를 못 읽은 항목을 문서 전체로 넓혀 읽지 않는다


def test_locate_reuses_the_form_guide_keys_and_reports_what_did_not_link():
    got = FR.locate(FR.parse(RULES, "연차보고서")["rules"], _places(), D.BLOCKS)
    g = got["heads"]["h2"][0]
    assert (g["src"], g["kind"], g["required"], g["source"], g["applies"], g["rule"]) == ("rule", "규정", True, "관리규정 제5조 (2026-01-01)", "2차년도 이상 과제", "r1")
    cell = [x for x in got["tables"]["t1"] if x["rule"] == "r2"]
    assert cell and cell[0]["required"] is False and cell[0]["label"] == "칸 「목표」" and cell[0]["cell"] == "r0c1"
    assert [x["rule"] for x in got["doc"]] == ["r3"] and got["doc"][0]["source"] == "작성지침서"   # targets 없는 항목 = 문서 전체(자리마다 되풀이하지 않는다)
    assert got["links"] == {"r1": 1, "r2": 1, "r5": 1} and [(u["id"], u["kind"]) for u in got["unmatched"]] == [("r4", "section")]


def test_save_keeps_the_version_and_refuses_a_stale_write():
    d, sha = FR.save_text("연차보고서", RULES, expect="")
    assert FR.read("연차보고서")[2] == sha and FR.load("연차보고서") == d and FR.path_of("연차보고서").name == "연차보고서.rules.yaml"
    with pytest.raises(FG.StaleVersion):
        FR.save_text("연차보고서", RULES + "\n", expect="x" * 40)
    with pytest.raises(ValueError):
        FR.save_text("연차보고서", "rules: 글", expect=sha)
    assert FR.read("연차보고서")[2] == sha   # 틀린 글 · 낡은 판은 파일을 안 바꾼다


def _index(user=None, form=None):
    rules = FR.locate(FR.parse(RULES, "연차보고서")["rules"], _places(), D.BLOCKS)
    purpose = {"heads": {"h2": [{"src": "purpose", "kind": "문서 목적 — 프로젝트 지침", "text": "이번 공고의 탄소 저감 관점으로 쓴다."}]}, "tables": {},
               "doc": [{"src": "purpose", "kind": "문서 목적", "text": "공고의 목적에 맞춘다."}]}
    saved = {"items": [{"id": "x1", "kind": "notes", "name": "※ 안내", "text": "※ 목표는 한 문장으로", "heading": {"id": "h2", "text": "1-1. 목표"}, "table": None, "top": 1}], "marks": []}
    return PG.index(saved, D.BLOCKS, ["t1"], user, None, D.T3, form, [rules, purpose])


def test_pack_keeps_one_of_the_same_text_and_cuts_by_source_rank():
    same = "한 문장으로 적는다"
    got, cut = PG.pack([{"src": "user", "kind": "사용자 지침", "text": same}, {"src": "form", "kind": "양식 지침", "text": "한 문장으로  적는다"}, {"src": "doc", "kind": "※ 안내", "text": same, "cell": "r0c1"}])
    assert [(g["src"], g.get("cell")) for g in got] == [("user", None), ("doc", "r0c1")] and cut == 0   # 같은 글은 출처가 달라도 하나(앞의 것) · 다른 칸의 것은 따로
    rows = [{"src": "llm", "kind": "k", "text": "가" * 300}, {"src": "form", "kind": "k", "text": "나" * 300}, {"src": "rule", "kind": "규정", "required": False, "text": "다" * 300},
            {"src": "rule", "kind": "규정", "required": True, "text": "라" * 300}, {"src": "purpose", "kind": "문서 목적", "text": "마" * 300}, {"src": "user", "kind": "k", "text": "바" * 300}]
    got, cut = PG.pack(rows, limit=950)
    assert [g["text"][0] for g in got] == ["라", "마", "바"] and cut == 3   # 사람 › 규정(필수) › 문서 목적이 남고 — 차례는 그대로 · 04 › 규정(권고) › 양식 지침 차례로 빠진다
    assert [PG.rank(g) for g in rows] == [6, 4, 5, 1, 2, 0] and PG.rank({"src": "doc"}) == 3
    small = [{"src": "doc", "kind": "k", "text": "가" * 500}, {"src": "doc", "kind": "k", "text": "나" * 500}, {"src": "doc", "kind": "k", "text": "다" * 50}]
    assert [g["text"][0] for g in PG.pack(small, limit=600)[0]] == ["가", "다"]   # 큰 것 하나를 빼느라 작은 것까지 잃지 않는다


def test_index_holds_rule_and_purpose_per_place_and_whole_document_ones_once():
    ix = _index()
    assert [g["src"] for g in ix["heads"]["h2"]] == ["rule", "purpose", "doc"]   # 사람의 것 다음 — 규정 · 문서 목적 · 양식의 것
    assert [g["src"] for g in ix["doc"]] == ["rule", "purpose"] and all(g["text"] != "본문은 10쪽 이내로 쓴다." for v in ix["heads"].values() for g in v)   # 문서 전체의 것은 자리마다 되풀이하지 않는다
    text = PG.doc_text(ix["doc"])
    assert text.splitlines()[0] == "- (규정 · 필수 · 작성지침서) 본문은 10쪽 이내로 쓴다." and "(문서 목적) 공고의 목적에 맞춘다." in text
    at = PG.resolver(ix, D.BLOCKS, D.GRAPH)
    assert at.doc == ix["doc"] and [g.get("rule") for g in at("block", "h2") if g["src"] == "rule"] == ["r1", "r5"]   # 그 자리의 것 → 윗 절(1. 개요)의 것


def test_off_list_drops_a_guide_everywhere_and_the_sig_follows():
    base = _index()
    key = PG.fp(base["heads"]["h2"][0])
    user = PG.off_put({"version": 3, "heads": {}}, key)
    assert user == {"version": 4, "heads": {}, "off": [key]} and PG.user_put(user, "h2", "내 지침")["off"] == [key]   # 헤딩 지침을 적어도 끈 목록은 남는다
    ix = _index(user)
    assert [g["src"] for g in ix["heads"]["h2"]] == ["purpose", "doc"] and [g["rule"] for g in ix["offed"]["h2"]] == ["r1"] and ix["off"] == [key]
    at0, at1 = PG.resolver(base, D.BLOCKS, D.GRAPH), PG.resolver(ix, D.BLOCKS, D.GRAPH)
    assert PG.sig(at0("block", "h2")) != PG.sig(at1("block", "h2")) and PG.sig(at0("block", "h6")) == PG.sig(at1("block", "h6"))   # 판은 고른 뒤의 목록으로 — 끈 자리만 다시 묻는다
    whole = PG.fp(base["doc"][0])
    ix2 = _index(PG.off_put(user, whole))
    assert [g["src"] for g in ix2["doc"]] == ["purpose"] and [g["rule"] for g in ix2["docOffed"]] == ["r3"]
    assert PG.off_put(PG.off_put(user, whole), key, False).get("off") == [whole]
    with pytest.raises(ValueError):
        PG.off_put({}, "지문이 아님")


def test_the_three_consumers_read_the_same_assembly():
    """이관 3단계(resolver) · 양식 작성(guide_write.places 의 guides + up) · 화면(chain 의 층)이 같은 지침을 읽는다 — 양식 작성 초안도 윗 절의 것을 받는다."""
    ix = _index()
    at = PG.resolver(ix, D.BLOCKS, D.GRAPH)
    ps = {p["id"]: p for p in guide_write.places(D.BLOCKS, D.GRAPH, ix)}
    for pid in ("h2", "h4", "h6"):
        want = {PG.fp(g) for g in at("block", pid)}
        assert {PG.fp(g) for g in [*ps[pid]["guides"], *ps[pid]["up"]]} == want, pid
        layers = PG.chain(ix, D.BLOCKS, D.GRAPH, pid)
        assert {PG.fp(g) for ly in layers if ly["key"] != "doc" for g in ly["items"]} == want, pid
        assert [ly["items"] for ly in layers if ly["key"] == "doc"] == [ix["doc"]] and ps[pid]["docGuides"] == ix["doc"]
    assert [g.get("rule") for g in ps["h2"]["up"]] == ["r5"]   # 윗 절(1. 개요)에 붙은 규정이 초안 요청에도 간다
    req = guide_write.request(ps["h2"])
    assert "(규정 · 필수 · 관리규정 제5조 (2026-01-01) · 적용: 2차년도 이상 과제) 목표는 정량 지표로 적는다." in req and "개요 전체에 닿는 요구" in req
    assert req.count("본문은 10쪽 이내로 쓴다.") == 1 and "문서 전체에 닿는 지침" in req


def test_04_reads_rules_as_reference_and_does_not_echo_them():
    ix = _index()
    ps = guide_write.places(D.BLOCKS, D.GRAPH, ix)
    p = next(x for x in ps if x["id"] == "h2")
    assert all(g["src"] not in ("rule", "purpose") for g in W.form_place(p)["guides"])   # 04 의 「양식 원문의 지침」 에는 안 든다
    # 그 자리의 것 + 윗 절(1. 개요)에서 내려온 규정(「개요 전체에 닿는 요구」 — 2026-11-27 astra P1-3: 전에는 `up` 이 04 의 자리 참조에 안 실렸다)
    assert [(r["from"].split(" · ")[0], r["text"]) for r in W.reference_of(p)] == [
        ("규정", "목표는 정량 지표로 적는다."), ("규정", "개요 전체에 닿는 요구"), ("문서 목적 — 프로젝트 지침", "이번 공고의 탄소 저감 관점으로 쓴다.")]
    echo = W.echo_texts(ps)
    assert "본문은 10쪽 이내로 쓴다." in echo
    kept = W.drop_echo([{"instruction": "목표는  정량 지표로 적는다."}, {"instruction": "표는 차년도마다 한 행"}], echo)
    assert [r["instruction"] for r in kept] == ["표는 차년도마다 한 행"]   # 규정의 글을 그대로 되낸 규칙은 버린다(되먹임)


# ---- 검토 P1 · P2 의 음성 시험 ---------------------------------------------------------------------------------

def test_a_wide_table_keeps_its_link_through_the_cut_head_text():
    heads = [f"머리글 항목 번호 {chr(0xAC00 + i * 7)}{chr(0xB000 + i * 11)} 구분" for i in range(40)]   # 머리글 글이 400자를 넘는 표
    blocks = [D._p("h1", "1. 개요"), D._table("tw", heads)]
    graph = {"nodes": [D.GRAPH["nodes"][0]]}
    places = FG.doc_places(blocks, graph, [])
    d = FG.parse("form: 연차보고서\n", "연차보고서")
    assert FG.skeleton(d, places) == 2 and FG.skeleton(d, places) == 0   # 다시 깔아도 같은 표의 항목이 새로 생기지 않는다
    tab = d["sections"][0]["tables"][0]
    assert len(tab["head"]) == FG.HEAD_MAX and tab["sig"] == places["tables"]["tw"]["sig"] != FG._sig_of_text(tab["head"])   # 지문은 자르기 전에 만든다
    tab["guides"].append({"text": "넓은 표의 지침", "origin": "user"})
    again = FG.parse(FG.dump(d), "연차보고서")
    assert FG.locate(again, places, blocks)["tables"]["tw"][0]["text"] == "넓은 표의 지침"
    short = FG.parse("form: 연차보고서\n", "연차보고서")
    FG.skeleton(short, _places())
    assert all("sig" not in t for s in short["sections"] for t in s["tables"])   # 안 잘린 머리글은 사람이 읽는 head 만


def test_candidate_keys_follow_the_text_and_block_ids_are_not_promoted():
    d, places = FG.parse("form: 연차보고서\n", "연차보고서"), _places()
    one = FG.candidates(d, places, rules={"h2": [{"instruction": "한 문장 요약", "basis": "explicit"}]})
    two = FG.candidates(d, places, rules={"h2": [{"instruction": "두 문장 요약", "basis": "explicit"}]})   # 04 를 다시 돌려 같은 순번의 글이 바뀜
    assert one[0]["key"] != two[0]["key"] and one[0]["key"] == FG.candidates(d, places, rules={"h2": [{"instruction": "한 문장 요약", "basis": "explicit"}]})[0]["key"]
    assert one[0]["key"] != FG.candidates(d, places, rules={"h2": [{"instruction": "한 문장 요약", "basis": "example"}]})[0]["key"]   # 출처(근거 성격)가 달라도
    bad = FG.candidates(d, places, rules={"h2": [{"instruction": "p48 줄은 한 문장으로, p50~p52 에는 수치를"}]})[0]
    assert "p48" in bad["blocked"] and any("줄 id" in w for w in bad["warn"]) and FG.promote(d, places, [bad]) == 0 and not d["sections"]
    band = FG.candidates(d, places, rules={"t1": [{"instruction": "띠에만", "band": "b2"}, {"instruction": "없는 띠", "band": "zz"}]})
    assert [c.get("band") for c in band] == ["b2"]   # 띠에만 닿는 후보는 그 띠가 있을 때만 — 표 전체로 넓히지 않는다
    assert FG.promote(d, places, band) == 1 and d["sections"][0]["tables"][0]["guides"] == [] and d["sections"][0]["tables"][0]["subtables"][0]["guides"][0]["text"] == "띠에만"


def test_an_unknown_origin_is_an_error_not_a_person():
    text = "form: 연차보고서\nsections:\n  - id: s1\n    path: [가]\n    guides:\n      - {text: 규정의 글, origin: rule}\n"
    with pytest.raises(ValueError):
        FG.parse(text, "연차보고서")
    assert FG.parse(text, "연차보고서", strict=False)["sections"][0]["guides"][0]["origin"] == "rule"   # 저장된 파일 읽기도 「user」 로 바꾸지 않는다
    assert FG.parse("form: 연차보고서\nguides: [어느 과제에나 맞는 일반 지침]\n", "연차보고서")["guides"] == [{"text": "어느 과제에나 맞는 일반 지침", "origin": "user"}]


def test_tables_pair_within_each_repeated_heading():
    blocks = [D._p("a", "(1) 기관1 실적"), D._table("a1", ["항목", "값"]), D._table("a2", ["항목", "값"]), D._p("b", "(1) 기관2 실적"), D._table("b1", ["항목", "값"]), D._table("b2", ["항목", "값"])]
    graph = {"nodes": [{"id": "na", "para": "a", "role": "heading", "area": "body", "parent": None, "text": "(1) 기관1 실적"},
                       {"id": "nb", "para": "b", "role": "heading", "area": "body", "parent": None, "text": "(1) 기관2 실적"}]}
    d = FG.parse("form: 연차보고서\nguides: [문서 전체의 일반 지침]\nsections:\n  - id: s1\n    path: [\"(1) 기관N 실적\"]\n    tables:\n"
                 "      - {id: t1, head: 항목 | 값, guides: [첫 표]}\n      - {id: t2, head: 항목 | 값, guides: [둘째 표]}\n", "연차보고서")
    got = FG.locate(d, FG.doc_places(blocks, graph, []), blocks)
    assert {t: [g["text"] for g in v] for t, v in got["tables"].items()} == {"a1": ["첫 표"], "a2": ["둘째 표"], "b1": ["첫 표"], "b2": ["둘째 표"]} and not got["unmatched"]
    assert got["links"]["t1"] == ["a1", "b1"] and [g["kind"] for g in got["doc"]] == [FG.KIND_DOC]   # 루트 guides = 문서 전체(자리에 안 붙는다)


def test_llm_defined_theme_hows_wait_for_a_person():
    from app import writing_guidance_api as WA
    record = {"theme": {"id": "x"}, "templates": []}
    mine = [{"id": "x", "name": "새 테마", "src": "llm", "division": [{"name": "예산", "how": "LLM 이 지은 다루는 법"}]}]
    assert "LLM 이 지은" not in WA._theme_text(record, mine) and "예산" in WA._theme_text(record, mine)   # 이름은 보이고 방법은 확인 뒤에
    assert "기본본의 법" in WA._theme_text(record, [{"id": "x", "name": "테마", "division": [{"name": "예산", "how": "기본본의 법", "src": "default"}]}])


# ---- 지침 보정의 넓힘(지침 검토 · 수정) -------------------------------------------------------------------------

def test_guide_fix_units_take_the_assembled_guides_and_report_ok():
    para = lambda i, t: {"id": i, "type": "paragraph", "text": t}  # noqa: E731
    blocks = [para("h1", "1. 개요"), para("p1", "내용 하나"), para("h3", "2. 다음"), para("p3", "다른 절")]
    graph = {"nodes": [{"id": "n1", "role": "heading", "area": "body", "para": "h1", "depth": 1, "parent": None}, {"id": "n3", "role": "heading", "area": "body", "para": "h3", "depth": 1, "parent": None}]}
    saved = {"items": [{"id": "zz", "kind": "notes", "name": "※ 안내", "text": "※ 2page 이내", "heading": {"id": "h1", "text": "1. 개요"}, "table": None, "top": 1}], "marks": []}
    rule = {"src": "rule", "kind": "규정", "text": "날짜는 YYYY.MM.DD", "required": True, "source": "관리규정 제5조"}
    ix = PG.index(saved, blocks, [], extra=[{"heads": {"h3": [rule]}, "tables": {}, "doc": [{"src": "purpose", "kind": "문서 목적", "text": "공고의 목적"}]}])
    assert [u["where"] for u in GF.units(blocks, graph, saved, {})[0]] == ["1. 개요"]   # 조립 없이 = 전처럼 저장한 작성 지침의 자리만
    us, ctx = GF.units(blocks, graph, saved, {}, ix=ix)
    assert [u["where"] for u in us] == ["1. 개요", "2. 다음"]   # 문서에 작성요령이 없어도 규정이 붙은 자리를 본다
    assert us[0]["guides"] == [{"kind": "※ 안내", "text": "※ 2page 이내", "src": "doc"}] and us[1]["guides"] == [{"kind": "규정 · 필수 · 관리규정 제5조", "text": "날짜는 YYYY.MM.DD", "src": "rule"}]
    answer = {"fixes": [{"unit": "u2", "id": "p3", "new": "다른", "rule": "날짜는 YYYY.MM.DD", "src": "rule", "why": "덜기"}], "left": [], "ok": [{"unit": "u1", "why": "분량 안"}, {"unit": "u2", "why": "맞음"}, {"unit": "zz", "why": ""}]}
    fixes, left, _ = GF.check(ctx, answer)
    assert fixes[0]["src"] == "rule" and "src" not in GF.check(ctx, {"fixes": [{"unit": "u2", "id": "p3", "new": "다른", "src": "어디선가"}]})[0][0]
    ok = GF.oks(ctx, answer, fixes, left)
    assert ok == [{"unit": "u1", "where": "1. 개요", "why": "분량 안"}]   # 고침이 있는 자리는 「맞음」 이 아니다 · 모르는 자리는 버린다
    assert [(p["unit"], p["state"]) for p in GF.places(ctx, fixes, left, ok)] == [("u1", "ok"), ("u2", "fix")]
    assert [(p["state"], p["why"]) for p in GF.places(ctx, failed=["u1"])] == [("none", "LLM 이 답을 내지 못했습니다"), ("none", "")]
    assert "ok" in GF.SCHEMA["properties"] and "docGuides" in GF.CONTRACT
