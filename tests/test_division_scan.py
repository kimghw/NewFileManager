"""구분 기준 판독(app/division_scan.py · app/division_scan_api.py · app/division_terms.py — spec_구분_기준 ② §23)과 헤딩 추출의 쓰임(spec_헤딩_추출 ② §13 「구분 기준 판독」).
2026-11-18 사용자 "구분기준은 첫번째하고 언제든지 다시 돌릴 수 있고 헤딩은 마지막 결과를 참조" · "연구개발과제 에서만 구분 기준엔진을 쓸거야". 반례는 astra · Fable 협의(artifacts/division_first_astra_2026-11-18/)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import division_scan as DS
from app import division_scan_api as DSA
from app import division_terms as DT
from app import heading_graph as HG
from app import server
from app.division_profiles.rnd import core
from app.hwpx_doc import HwpxDoc

FORM = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
SAMPLE = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"
_MEMO = {}


def _form_blocks():
    if "form" not in _MEMO:
        _MEMO["form"] = HwpxDoc(FORM.read_bytes()).blocks()
    return _MEMO["form"]


def _vals(**kw):
    return core.norm_values({"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대"]}, **kw})


def _p(pid, text):
    return {"id": pid, "type": "paragraph", "text": text}


# ---- 순수 판독 --------------------------------------------------------------------------------------------------------

def test_value_basis_moved_to_division_terms_and_heading_uses_the_same():
    assert HG.value_basis is DT.value_basis and HG.label_shape is DT.label_shape and HG.BASES is DT.BASES   # 원본 하나(구분 기준 쪽)
    assert DT.value_basis("[1차년도 목표]") == "차년도" and DT.value_basis("[주관연구개발기관(기관명 기입)]") == "기관" and DT.value_basis("[한국선급]") == ""


def test_scan_on_the_blank_form_keeps_the_engine_and_adds_only_identifying_evidence():
    blocks = _form_blocks()
    r = DS.scan(blocks, None, _vals())
    groups = core.find(blocks, __import__("app.division_profiles.rnd", fromlist=["levels_of"]).levels_of(blocks), _vals())
    assert len(r["_groups"]) == len(groups) == r["counts"]["groups"]           # 엔진은 그대로(반영의 입력을 바꾸지 않는다)
    assert r["tables"] == {} and r["cells"] == {} and r["_values"] is None     # 귀속 값이 없으면 표 안 판독·이름 라벨은 안 한다(기본 값은 묶음 찾기에만)
    pats = [x for x in r["extra"] if x["src"] == "pattern"]
    assert pats and all(x["basis"] and x["dim"] in ("stage", "year", "org", "stageYear") for x in pats)
    texts = {x["text"]: x for x in pats}
    assert any(t.startswith("[1단계") for t in texts) and all(x.get("inGroup") for t, x in texts.items() if t.startswith("[1단계") or t.startswith("[n단계"))   # 단계 행 묶음 안 — 판독만이 아니다(Fable 반례)
    assert any(t.startswith("[해당 기관별") and not x.get("inGroup") for t, x in texts.items())
    # 엔진 라벨이 칸이면 그 칸의 문단을 라벨로(칸 id 와 문단 id — astra P2)
    cell_labels = [it["label"] for g in groups for it in g["items"] if it.get("label") and not str(it["label"]) in {b["id"] for b in blocks}]
    assert cell_labels and r["counts"]["engine"] > 69


def test_name_labels_need_values_a_whole_line_and_a_single_current_org():
    keys = ["가나대", "인텍"]
    assert DS.name_key("[가나대]", keys) == "가나대" and DS.name_key("【인텍】", keys) == "인텍"
    assert DS.name_key("[가나대 연구 내용]", keys) is None and DS.name_key("[DNV]", keys) is None and DS.name_key("[가나대]", []) is None
    assert DS.name_key("[가나]", ["가나", "가나"]) == "가나"   # 같은 열쇠 둘은 하나로 센다(목록에 겹쳐 들어온 것)
    blocks = [_p("p1", "[가나대]"), _p("p2", "[가나대] 시험 성적서 발급 절차"), _p("p3", "[DNV]")]
    r = DS.scan(blocks, _vals(), None)
    assert [(x["para"], x["src"]) for x in r["extra"]] == [("p1", "name")]       # 줄이 괄호 글뿐일 때만(Fable 반례 5)
    assert DS.scan(blocks, None, _vals())["extra"] == []                           # 귀속 값이 없으면 이름 라벨 없음


def _nd(nid, para, letter, typ, kind="label", text=""):
    return {"id": nid, "para": para, "letter": letter, "type": typ, "kind": kind, "text": text}


def test_node_basis_reads_the_line_itself_not_the_paragraph():
    pin = {"labels": {"p1": [{"dim": "year", "src": "engine", "text": "[기관A] [1차년도 목표]"}], "p2": [{"dim": "org", "src": "hint"}],
                      "p3": [{"dim": "org", "src": "name", "text": "[가나대]"}], "p4": [{"dim": "stage", "src": "engine", "text": "(1) 1단계"}]}}
    assert DS.node_basis(_nd("n1", "p1", "[기관A]", "T1"), pin)[:2] == (None, False)          # 한 문단 두 줄 — 문단의 근거(차년도)가 「[기관A]」 로 번지지 않는다
    assert DS.node_basis(_nd("n1#1", "p1", "[1차년도 목표]", "T2"), pin)[:2] == ("차년도", False)
    assert DS.node_basis(_nd("n2", "p2", "[수행단위]", "T3"), pin)[:2] == ("기관", False)        # 추가한 자리는 사람이 고른 것 — 글을 안 본다
    assert DS.node_basis(_nd("n3", "p3", "[가나대]", "T4"), pin) == (None, False, True)          # 이름 라벨은 확인이 아니라 후보(LLM A 가 본다)
    assert DS.node_basis(_nd("n4", "p4", "(1)", "T5", kind="outline", text="1단계"), pin)[:2] == ("단계", False)
    assert DS.node_basis(_nd("n5", "p9", "[1차년도 목표]", "T2"), pin) == (None, False, False)   # 근거 없음 = 모름


def test_type_bases_confirm_a_type_only_when_every_line_is_confirmed():
    pin = {"labels": {"a": [{"dim": "year", "src": "engine"}], "b": [{"dim": "year", "src": "engine"}], "c": [{"dim": "org", "src": "hint"}]}}
    nodes = [_nd("1", "a", "(1)", "TN", kind="outline", text="1차년도"), _nd("2", "x", "(2)", "TN", kind="outline", text="기술목표"),   # 「(N)」 에 섞임
             _nd("3", "b", "[2차년도 목표]", "TB"), _nd("4", "c", "[수행단위]", "TC"), _nd("5", "y", "[수행단위]", "TD")]                  # 같은 글 · 다른 유형(표 칸)
    tb = DS.type_bases(nodes, pin)
    assert tb["TN"]["basis"] is None and (tb["TN"]["confirmed"], tb["TN"]["total"]) == (1, 2)
    assert tb["TB"]["basis"] == "차년도" and tb["TC"]["basis"] == "기관" and tb["TD"]["basis"] is None   # 유형 id 로 가른다(꼴이 같아도 번지지 않음)


def test_bracket_role_puts_the_scan_after_the_text_pattern():
    assert HG.bracket_role("[가나대 수행 내용]", None, div="기관") == ("label", "기관", HG.BY_SCAN)
    assert HG.bracket_role("[주관연구개발기관(1단계)]", None, div="단계")[:2] == ("label", "기관")   # 글 꼴이 먼저(엔진은 단계로 읽는다 — Fable 반례 4)
    assert HG.bracket_role("[  ]", None, div="기관")[0] == "not_heading"
    hints = {"labels": {"[가나대 수행 내용]": {"role": "subtitle"}}}
    assert HG.bracket_role("[가나대 수행 내용]", hints, div="기관")[0] == "subtitle"                    # 사용자 지정이 먼저
    assert HG.bracket_role("[가나대 수행 내용]", None)[0] == "subtitle"                                 # 판독이 없으면 전과 같다


def test_settle_roles_does_not_spread_an_llm_label_over_a_mixed_numbered_type():
    types = {"TN": {"kind": "outline", "shape": "(N)"}, "TL": {"kind": "label", "shape": "[가나대 수행 내용]"}}
    answer = lambda: {"TN": {"role": "label", "basis": "차년도", "parents": [], "reason": "A"}, "TL": {"role": "subtitle", "basis": "", "parents": [], "reason": "A"}}  # noqa: E731
    roles = answer()
    HG.settle_roles(types, roles, {"_divTypes": {"TN": {"basis": None, "confirmed": 1, "total": 2, "conflict": 0}, "TL": {"basis": "기관", "confirmed": 3, "total": 3, "conflict": 0}}})
    assert roles["TN"]["role"] == "heading" and "1개만" in roles["TN"]["reason"] and roles["TN"]["aRole"] == "label"
    assert roles["TL"]["role"] == "label" and roles["TL"]["basis"] == "기관" and roles["TL"]["reason"] == HG.BY_SCAN
    roles = answer()
    HG.settle_roles(types, roles, {"_divTypes": {"TN": {"basis": "차년도", "confirmed": 2, "total": 2, "conflict": 0}}})
    assert roles["TN"]["role"] == "label" and roles["TN"]["basis"] == "차년도"                          # 줄 모두 확인 — A 의 답대로
    roles = answer()
    HG.settle_roles(types, roles, None)
    assert roles["TN"]["role"] == "label" and roles["TL"]["role"] == "subtitle"                          # 판독이 없는 문서(연구개발과제 아님)는 전과 같다


def test_pin_keeps_only_the_label_evidence():
    r = DS.scan([_p("p1", "[1차년도 목표]"), _p("p2", "[가나대]")], _vals(), None)
    pin = DS.pin(r, "k1", 1.0)
    assert pin["key"] == "k1" and set(pin["labels"]) == {"p1", "p2"} and all(set(x) <= {"dim", "src", "text", "value", "basis"} for rows in pin["labels"].values() for x in rows)
    assert DS.pin(None) is None


# ---- 서비스 · 끝점 ----------------------------------------------------------------------------------------------------

@pytest.fixture
def client():
    server.DOCS.clear()
    DSA._CACHE.clear()
    return TestClient(server.app)


def _open(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text[:300]
    return r.json()["docId"]


def test_scan_endpoint_is_lazy_cached_and_forced_again(client):
    c = client
    d = _open(c, FORM)
    assert DSA.last(server._sess(d)) is None                                     # 열기만 해서는 세지 않는다(지연)
    a = c.get(f"/api/docs/{d}/divisions/scan").json()
    assert a["enabled"] and a["scan"]["counts"]["groups"] > 50 and a["scan"]["fresh"] and a["scan"]["basis"] is None
    e1 = DSA.last(server._sess(d))
    assert c.get(f"/api/docs/{d}/divisions/scan").json()["scan"]["at"] == a["scan"]["at"] and DSA.last(server._sess(d)) is e1   # 같은 입력 = 읽어 둔 것
    b = c.post(f"/api/docs/{d}/divisions/scan", json={}).json()
    assert b["scan"]["at"] >= a["scan"]["at"] and DSA.last(server._sess(d)) is not e1 and b["scan"]["counts"] == a["scan"]["counts"]   # 다시 판독 = 다시 셈(결과는 같다)
    assert c.put(f"/api/docs/{d}/divisions/settings", json={"values": {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대"]}}}).status_code == 200
    s2 = c.get(f"/api/docs/{d}/divisions/scan").json()["scan"]
    assert s2["basis"] == "settings" and s2["at"] > b["scan"]["at"]              # 값이 바뀌면 다시 센다
    m = c.get(f"/api/docs/{d}/divisions/members").json()
    assert "reads" in m and m["scan"]["fresh"] and any(x["kind"] == "label" and x["src"] == "pattern" for x in m["reads"])
    assert all({"kind", "dim", "dimName", "value", "src", "inGroup", "paras"} <= set(x) for x in m["reads"])
    assert any(it.get("labelParas") for g in m["groups"] for it in g["items"])


def test_scan_is_only_for_research_tasks(client):
    c = client
    d = _open(c, FORM)
    assert c.put(f"/api/works/{d}/task", json={"kind": "general", "file": "", "job": "doc_edit", "project": ""}).status_code == 200
    assert c.get(f"/api/docs/{d}/divisions/scan").json() == {"enabled": False, "scan": None}
    m = c.get(f"/api/docs/{d}/divisions/members").json()
    assert "reads" not in m                                                       # 일반 문서 TASK — 판독 보탬 없음
    z = c.get(f"/api/docs/{d}/zones").json()
    assert z["counts"]["blocks"] == 0 and not z["blocks"]                          # 편집 구역의 자동 판독도 엔진을 안 쓴다
    d2 = _open(c, SAMPLE)                                                          # 양식이 아닌 문서(TASK 없음 · 양식 판정 없음)
    assert c.get(f"/api/docs/{d2}/divisions/scan").json()["enabled"] is False


def test_heading_stage2_runs_the_scan_first_and_pins_it(client):
    from app import heading_runs
    c = client
    d = _open(c, FORM)
    s = server._sess(d)
    heading_runs.run_sync(s, 1, False)
    j = heading_runs.run_sync(s, 2, False)
    steps = j.view()["steps"]
    assert steps[0]["name"] == "구분 기준 판독" and "엔진 묶음" in steps[0]["msg"]
    g = heading_runs.graph(s)
    assert g["division"] and g["division"]["pin"]["labels"] and g["bracketRule"] == 2
    assert "_divTypes" not in (g.get("hints") or {}) and "division" not in heading_runs.hints(s)   # 사용자 지정(hints.json)에는 안 쓴다
    labels = sum(1 for n in g["nodes"] if n.get("role") == "label")
    assert labels > 30
