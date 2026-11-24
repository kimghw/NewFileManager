"""작성 지침 저장(spec_작업 ② §21 「작성 지침 저장」 · app/form_guides.py · API …/form-guides) — 작성 요령 표 · <참고 N> 자료 · ※ 안내를 헤딩/표별로 모으고,
각주 번호를 작성 요령 표의 항목에 잇고, 「작성요령 삭제」 가 지운 뒤에도 저장해 둔 것이 남는다 — 실제 KEIT 연차보고서 서식으로."""
import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import form_guides as FG
from app import server
from app.hwpx_doc import HwpxDoc


def test_numbered_items_and_their_sub_items():
    got = FG._numbered("머리 글\n14. 연구개발기간: 전체를 1단계로\n1) 전체: 시작일부터\n  이어지는 줄\n2) 단계: 해당 단계\n15. 연구개발비\n16,17. 시작 및 목표 TRL\n")
    assert got["14"].startswith("14. 연구개발기간") and "2) 단계" in got["14"]            # 항목 글에는 딸린 항목도 든다
    assert got["14-1"] == "1) 전체: 시작일부터\n  이어지는 줄" and got["14-2"] == "2) 단계: 해당 단계"
    assert got["15"] == "15. 연구개발비" and got["16"] == got["17"] == "16,17. 시작 및 목표 TRL"   # 「16,17.」 은 두 번호 모두
    assert FG._numbered("1) 정성적 성과: …\n2) 정량적 성과: …") == {"1": "1) 정성적 성과: …", "2": "2) 정량적 성과: …"}   # 「N.」 항목 밖의 「k)」 는 그대로 번호 k
    assert FG._numbered("ㅇ 번호 없는 지침\n ※ 참조") == {}


def test_guide_table_lines_named_after_sections_go_to_those_headings():
    """작성 요령 표의 「절 이름」 항목 나누기(_parts — 2026-11-24). 헤딩 = (본문 차례, 문단 id, 글, 레터, 이름)."""
    H = lambda i, letter, name: (i, f"p{i}", f"{letter} {name}", letter, FG._norm(name))  # noqa: E731
    heads = [H(1, "1.", "개요"), H(2, "가.", "참여연구자 현황"), H(3, "□", "최종 목표"), H(4, "6.", "자체보안관리진단"), H(9, "□", "최종 목표")]
    text = ("작성 요령 | 작성 후 삭제\n[참여연구자 현황]\n◦ 연도별로 모두 기재\n - 신규채용 예정 포함\n\n[그 밖의 표]\n◦ 해당 시 작성\n"
            "◦ 최종 목표\n  - 정량적으로 기술\n  ※ 근거를 기술\n◦ 다른 줄\n1. 제품\n2. 시설ㆍ장비\n6. 기관별로 자체보안관리진단 표를 작성합니다.\n 이어지는 줄\n7) 딸린 줄\n[최종 목표]")
    parts, rest = FG._parts(text, heads, 0, 5)
    got = {h[1]: body for h, body in parts}
    assert got["p2"] == "[참여연구자 현황]\n◦ 연도별로 모두 기재\n - 신규채용 예정 포함"   # 「[이름]」 덩이 — 다음 「[…]」 줄 전까지(끝의 빈 줄은 뗀다)
    assert got["p3"] == "◦ 최종 목표\n  - 정량적으로 기술\n  ※ 근거를 기술" and "p9" not in got   # 「◦」 항목 — 다음 「◦」 전까지 · 같은 이름의 헤딩은 이 표가 맺는 구역(0~5)의 것만
    assert got["p4"] == "6. 기관별로 자체보안관리진단 표를 작성합니다.\n 이어지는 줄\n7) 딸린 줄" and "p1" not in got   # 「N.」 — 번호 + 헤딩 이름이 줄에 있을 때만(「1. 제품」 은 「1. 개요」 의 것이 아니다)
    assert rest == "작성 요령 | 작성 후 삭제\n[그 밖의 표]\n◦ 해당 시 작성\n◦ 다른 줄\n1. 제품\n2. 시설ㆍ장비\n[최종 목표]"   # 제목 줄 + 못 이은 줄 + 절 이름뿐인 줄
    assert [h[1] for h, _ in FG._parts("제목\n◦ 최종 목표: 정량적으로", heads, 20, 30)[0]] == ["p3", "p9"]   # 구역에 없으면 문서 전체의 같은 이름 헤딩 모두 · 「이름: 지침」 한 줄
    assert FG._parts("제목\nㅇ 번호 없는 지침", heads, 0, 5) == ([], "제목\nㅇ 번호 없는 지침")


def test_keep_old_keeps_split_parts_after_cleanup():
    """「작성요령 삭제」 로 작성 요령 표가 사라진 뒤 다시 모아도, 그 표에서 절 이름으로 나눠 둔 항목(id 「표#k」)과 나머지는 저장본의 것이 남는다."""
    old = {"items": [{"id": "t9", "kind": "tables", "text": "본문 작성 요령", "heading": {"id": "p8", "text": "7. 끝"}, "table": None, "top": 9, "parts": 1},
                     {"id": "t9#1", "of": "t9", "kind": "tables", "text": "1) 연구개발 목표 및 내용: …", "heading": {"id": "p5", "text": "5-1 연구개발 목표 및 내용"}, "table": None, "top": 5}], "marks": []}
    got = FG.keep_old({"version": 1, "items": [], "marks": [], "counts": {}}, old)
    assert [x["id"] for x in got["items"]] == ["t9#1", "t9"] and got["counts"]["items"] == 2 and got["counts"]["headings"] == 2


needs_form = pytest.mark.skipif(not M.REPORT_FORM.exists(), reason="KEIT 연차보고서 서식 hwpx 없음")


@pytest.mark.skipif(not M.PLAN_FORM.exists(), reason="연구개발계획서 양식 hwpx 없음")
def test_plan_form_section_guides_reach_named_headings_not_blank_bullets():
    """연구개발계획서 양식(2026-11-24) — 절 끝의 작성 요령 표가 빈 글머리 줄(「o」·「-」·「⋅」)이 아니라 글 있는 헤딩에 붙고, 「[참여연구자 현황]」 덩이는 그 이름의 헤딩에 간다."""
    data = M.PLAN_FORM.read_bytes()
    doc = HwpxDoc(data)
    graph, tables = M._cached("guides_plan", data, doc, "연구개발계획서")
    got = FG.collect(doc, graph, tables)
    blank = {n["para"] for n in graph["nodes"] if n.get("role") == "heading" and n.get("area") == "body" and n.get("blank")}
    assert blank and not any(x[k] and x[k]["id"] in blank for x in got["items"] + got["marks"] for k in ("heading",))
    first = next(it for it in got["items"] if it["kind"] == "tables" and "◦ 연구개발과제와 관련되는 연구개발과제의 배경 및 필요성" in it["text"])
    assert first["heading"]["text"].startswith("□ 필요성") and first["parts"] == 1   # 전에는 그 아래의 빈 「⋅」 줄
    people = next(it for it in got["items"] if it.get("of") and it["text"].startswith("[참여연구자 현황]"))
    assert people["heading"]["text"].startswith("가. 참여연구자 현황") and "[연구지원인력 현황]" not in people["text"]
    assert not any(it.get("of") and it["text"].startswith(("1. 제품", "2. 시설")) for it in got["items"])   # 법령 인용의 번호 줄은 잇지 않는다
    assert sum(1 for it in got["items"] if it.get("of")) == 14 and sum(1 for it in got["items"] if it["kind"] == "hints") == 26


@needs_form
def test_collect_groups_guides_by_heading_and_table():
    data = M.REPORT_FORM.read_bytes()
    doc = HwpxDoc(data)
    graph, tables = M._cached("guides_report", data, doc, "연차보고서")
    got = FG.collect(doc, graph, tables)
    c = got["counts"]
    assert (c["items"], c["marks"]) == (89, 56), c   # 작성 요령 표 5(앞표지 작성 요령 포함 — 2026-11-22: 0행이 빈 줄인 표도 본다) + 그 표에서 절 이름으로 나눈 항목 14(2026-11-24) + <참고 N> 4 + ※ 안내 30 + 안내 상자 5(2026-11-23) + 설명 줄 31(2026-11-24) · 각주 번호 56(form_cleanup 의 실측과 같은 수)
    kinds = [it["kind"] for it in got["items"]]
    assert (kinds.count("tables"), kinds.count("refs"), kinds.count("notes"), kinds.count("boxes"), kinds.count("hints")) == (19, 4, 30, 5, 31)
    # 절 이름 항목(2026-11-24) — 문서 끝의 「본문 작성 요령」 표가 절마다 적은 지침은 그 절의 헤딩에(전에는 통째로 마지막 헤딩 한 곳에만 붙어 그 절에는 닿지 않았다)
    whole = next(it for it in got["items"] if it["kind"] == "tables" and it["text"].startswith("본문 작성 요령"))
    parts = [it for it in got["items"] if it.get("of") == whole["id"]]
    assert whole["parts"] == len(parts) == 14 and [it for it in got["items"] if it.get("of") and it not in parts] == []   # 나눈 표는 이것 하나(절 이름을 적지 않은 작성 요령 표는 통째로)
    at = lambda start: next(it for it in parts if it["text"].startswith(start))["heading"]["text"]  # noqa: E731
    assert at("1) 연구개발 목표 및 내용:").startswith("5-1 연구개발 목표 및 내용") and at("연구개발과제의 개요:").startswith("1. 연구개발과제의 개요")
    assert at("2) 국내외 관련 분야 환경변화:").startswith("5-2 국내외 관련 분야 환경변화(해당 시 작성합니다)")   # 헤딩의 괄호 안내 · ※ 뒤는 이름이 아니다
    assert at("6. 연구개발기관별로 자체보안관리진단").startswith("6. 자체보안관리진단")   # 「N. …」 줄 — 번호가 레터와 같고 그 헤딩 이름이 줄에 들어 있음
    safety = next(it for it in parts if it["text"].startswith("7. 연구개발기관 별로 안전관리"))
    assert safety["text"].rstrip().endswith("추가로 기재합니다.") and safety["table"] is None and all(it["id"] == f"{whole['id']}#{k}" for k, it in enumerate(sorted(parts, key=lambda it: int(it["id"].split("#")[1])), 1))
    assert whole["text"].startswith("본문 작성 요령") and "7) 연구개발 활용방안 및 기대효과:" in whole["text"] and "1) 연구개발 목표 및 내용" not in whole["text"]   # 나머지 = 제목 줄 + 못 이은 줄
    assert "\n5. 다음 연도 연구개발계획" in whole["text"]   # 절 이름뿐인 줄은 지침이 아니다(나머지에 둔다)
    # 설명 줄(2026-11-24) — 표 아래의 검정 「* …」 줄(지우지 않는다 · 모으기만): 모두 바로 위 표에
    hints = [it for it in got["items"] if it["kind"] == "hints"]
    assert all(it["table"] and it["name"] == "설명 줄" for it in hints) and sum(1 for it in hints if it["text"].startswith("*")) == 29
    ks = next(it for it in hints if it["text"].startswith("* 1」 한국산업표준(KS)"))
    assert ks["heading"]["text"].startswith("ㅇ 국내표준") and len([it for it in hints if it["table"]["id"] == ks["table"]["id"]]) == 2   # 표 아래에 이어진 두 줄이 같은 표에
    assert len({it["table"]["id"] for it in hints if it["text"].startswith("* 협약용 연구개발계획서 대비 변경이 있을 경우 기재합니다")}) == 6   # 표마다 되풀이된 같은 줄은 제 표에
    plain = next(it for it in hints if it["text"].startswith("* 개발, 구매, 임대 등"))   # 안내 낱말이 없어도 표 바로 아래의 「*」 줄
    assert plain["table"]["id"] == next(it for it in hints if it["text"].startswith("** 협약용"))["table"]["id"]
    assert not any("페이지표기" in it["text"] or it["text"].startswith("[") for it in hints)   # 목차 · 소제목은 설명 줄이 아니다
    ratio = next(it for it in got["items"] if it["text"].startswith("※ 비율은 필수적으로 작성하여야 함"))
    assert ratio["kind"] == "notes" and ratio["table"]   # 표 바로 아래의 ※ 줄 — 뒤가 일부 본문 색이어도 앞 표를 본다(2026-11-24)
    box = next(it for it in got["items"] if it["kind"] == "boxes")   # 안내 상자 — 그 상자가 놓인 절(서식의 글 「5-1 연구개발 목표 및 내용」)의 지침 · 표의 지침이 아니다 · 글 = 상자의 두 줄
    assert box["heading"]["text"].startswith("5-1 연구개발 목표 및 내용") and box["table"] is None and box["name"] == "안내 상자"
    assert box["text"].startswith("당초계획 대비 변경사항이 있는 경우 작성") and box["text"].rstrip().endswith("(예시: N차년도 수정계획서 p.10~13)")
    inline = next(it for it in got["items"] if it["text"] == "※ 2page 이내 요약 작성")
    assert inline["heading"]["text"].startswith("1. 연구개발과제의 개요") and inline["table"] is None   # 제목 줄 안의 ※ — 그 헤딩의 지침이고 앞 표의 것이 아니다
    cell = next(it for it in got["items"] if it["text"].startswith("※ 요약문은 5쪽"))
    assert cell["table"] and cell["table"]["label"].replace(" ", "").startswith("<요약문>")   # 표 칸 안의 ※ — 그 표
    above = next(it for it in got["items"] if it["text"].startswith("※ 연차별 동일항목"))
    assert above["heading"]["text"].startswith("(2) 연구재료") and above["table"]   # 제목 줄 아래 · 표 위의 ※ — 그 헤딩과 바로 다음 표
    guide = next(it for it in got["items"] if it["kind"] == "tables" and it["text"].startswith("요약문 작성 요령"))
    assert guide["table"] is None and "22. 연구시설" in guide["text"]   # 작성 요령 표는 통째로(절의 것)
    # 각주 번호 — 표마다 1 부터 다시 매긴 번호가 **그 표 바로 뒤의 작성 요령 표** 항목에 이어진다: 표지 표(본문 첫 블록)의 29개 ← 「앞표지 작성 요령」 · 요약문 표(셋째 블록)의 22개 ← 「요약문 작성 요령」.
    # (2026-11-22 전에는 0행이 빈 줄인 「앞표지 작성 요령」 표를 작성 요령 표로 못 읽어 표지의 번호가 글 없이 남았다 — form_cleanup._guide_tables)
    linked = [m for m in got["marks"] if m["text"]]
    cover = next(it for it in got["items"] if it["kind"] == "tables" and it["text"].startswith("앞표지 작성 요령"))
    assert c["marksLinked"] == len(linked) == 51 and {(m["top"], m["guide"]) for m in linked} == {(0, cover["id"]), (2, guide["id"])}
    assert [len([m for m in linked if m["top"] == k]) for k in (0, 2)] == [29, 22]
    first = next(m for m in linked if m["no"] == "1" and m["top"] == 2)
    assert first["label"].startswith("세부사업명") and first["text"].startswith("1. 세부사업명") and first["table"]["id"] == cell["table"]["id"]
    assert next(m for m in linked if m["no"] == "17" and m["top"] == 2)["text"].startswith("16,17.")
    assert next(m for m in linked if m["no"] == "1" and m["top"] == 0)["text"].startswith("1. 보안등급")
    g = FG.groups(got)
    assert len(g["headings"]) == c["headings"] and len(g["tables"]) == c["tables"] and [x["top"] for x in g["tables"]] == sorted(x["top"] for x in g["tables"])
    summary = next(t for t in g["tables"] if t["id"] == cell["table"]["id"])
    assert len(summary["marks"]) == 22 and summary["items"] == [cell]
    bare = FG.collect(doc)   # 분석이 없으면 헤딩은 비운다(짐작하지 않는다) — 표는 문서에서 그대로
    assert bare["counts"]["headings"] == 0 and bare["counts"]["tables"] == c["tables"] and bare["counts"]["marksLinked"] == 51


@pytest.fixture
def client():
    yield TestClient(server.app)


@needs_form
def test_api_saves_and_keeps_guides_after_cleanup(client):
    d = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    v = client.get(f"/api/docs/{d}/form-guides").json()
    assert v["saved"] is None and v["groups"] == {"headings": [], "tables": [], "loose": []}   # 읽기는 모으지 않는다
    v = client.post(f"/api/docs/{d}/form-guides").json()
    assert v["saved"]["counts"]["items"] == 75 and v["saved"]["rev"] == v["rev"] and "kept" not in v and v["groups"]["tables"]   # 44 + 설명 줄 31(2026-11-24 — 헤딩 분석 전이라 절 이름 항목은 없다)
    assert client.get(f"/api/docs/{d}/form-guides").json()["saved"]["counts"] == v["saved"]["counts"]
    assert client.post(f"/api/docs/{d}/form-cleanup", json={}).json()["done"]["tables"] == 5   # 4단계 「작성요령 삭제」 — 문서에서는 사라진다
    assert client.get(f"/api/docs/{d}/form-cleanup").json()["counts"]["total"] == 0
    after = client.post(f"/api/docs/{d}/form-guides").json()   # 지운 뒤 다시 모아도 저장해 둔 것을 빈 목록으로 덮지 않는다
    assert after["kept"] is True and after["saved"]["counts"] == v["saved"]["counts"] and after["saved"]["rev"] == v["saved"]["rev"]


@needs_form
def test_cleanup_saves_guides_first_even_when_nobody_asked(client):
    d = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    assert client.get(f"/api/docs/{d}/form-guides").json()["saved"] is None
    assert client.post(f"/api/docs/{d}/form-cleanup", json={}).status_code == 200
    saved = client.get(f"/api/docs/{d}/form-guides").json()["saved"]   # 지우기 바로 전에 남긴 것
    assert saved and saved["counts"]["items"] == 75 and saved["counts"]["marksLinked"] == 51   # (44 + 설명 줄 31 — 설명 줄은 지우지 않지만 지침으로 남긴다) 앞표지 작성 요령 표를 지침으로 읽게 되어 표지의 각주 번호(2) … 19))가 그 항목에 이어진다(전 22)


# ---- 작성 지침을 헤딩 · 표 LLM 판정 자료로(spec_헤딩_추출 ② §20 — 2026-11-22 사용자 "당연히 넣어줘") ----------------------------------------------------------

def test_places_split_table_and_body_guides():
    saved = {"items": [{"id": "t1", "kind": "tables", "name": "작성 요령 표", "text": "작성 요령\n1. 과제명", "heading": {"id": "p3", "text": "1. 개요"}, "table": None, "top": 5},
                       {"id": "p9", "kind": "notes", "name": "※ 안내", "text": "※ 단위: 천원", "heading": None, "table": {"id": "t2", "label": "예산"}, "top": 7}],
             "marks": [{"no": "1", "at": "p12", "label": "과제명1)", "heading": None, "table": {"id": "t2", "label": "예산"}, "guide": "t1", "text": "1. 과제명", "top": 8},
                       {"no": "2", "at": "p13", "label": "기간2)", "heading": None, "table": None, "guide": None, "text": "", "top": 9}]}
    got = FG.places(saved)
    assert [g["at"] for g in got["tables"]["t2"]] == ["p9", "p12"] and got["tables"]["t2"][1]["kind"] == "각주 번호 1)"   # 표에 붙은 것은 그 표의 것(표 판정)
    assert got["body"] == [{"at": "t1", "head": "p3", "kind": "작성 요령 표", "text": "작성 요령\n1. 과제명"}]   # 나머지는 구간 판정 · 글 없는 각주 번호는 싣지 않는다
    assert FG.places({"items": [], "marks": []}) is None and FG.places(None) is None


@needs_form
def test_heading_and_table_llm_jobs_carry_place_guides():
    """실제 연차보고서 서식 — B(구간) 자료에 본문의 작성 지침이, T(표) 자료에 그 표의 지침(각주 번호가 가리키는 항목 · 칸 id)이 실린다. 지침이 없으면 자료는 전과 같다."""
    import json

    from app import heading_extract as E
    from app import heading_graph as HG
    from app import heading_guides as G
    from app import heading_rules as R
    from app import heading_tables as HT
    from app import heading_temp as TP
    data = M.REPORT_FORM.read_bytes()
    doc = HwpxDoc(data)
    graph, tables = M._cached("guides_report", data, doc, "연차보고서")
    guides = G.snapshot()
    s1 = E.extract(doc, store=R.load(), doc_key=None, tol=G.parse_tolerance(guides["tolerance"]["text"]))
    s1["meta"] = {"rev": 0, "run": 1}
    temp = TP.label(s1, None)
    hints = {"version": 0, "labels": {}, "bases": [], "temp": TP.clean_hints(None)}
    pinned = {**guides, "place": {"sha1": "s", **FG.places(FG.collect(doc, graph, tables))}}
    seen = {}

    def ask(jobs):
        out = []
        for j in jobs:
            w = j["what"].split("#")[0]
            seen.setdefault(w, []).append(json.loads(j["content"].rsplit("## 자료(JSON)\n", 1)[1]))
            out.append({"data": {"types": [], "mainChain": [], "summary": ""}} if w == "heading_types" else {"data": {"changes": [], "summary": ""}} if w == "heading_section" else {"data": None, "error": "시험"})
        return out
    g = HG.build(s1, use_llm=True, ask=ask, pinned=pinned, hints=hints, temp=temp, pairs=False)
    secs = seen["heading_section"]
    body = [x for d in secs for x in d.get("guides") or ()]
    assert any(x["text"] == "※ 2page 이내 요약 작성" and x["head"] for x in body)   # 제목 줄 안의 ※ — 그 헤딩 id 와 함께
    assert g["llm"]["placeGuides"] == {"sections": sum(1 for d in secs if d.get("guides")), "items": len(body)} and g["guides"]["place"] == "s"
    asked = HT.ask_tables(s1, ask=ask, pinned=pinned, temp=temp)
    tabs = [t for d in seen["heading_tables"] for t in d["tables"]]
    summary = next(t for t in tabs if any(x["text"].startswith("※ 요약문은 5쪽") for x in t.get("guides") or ()))   # <요약문> 표 — 칸 안의 ※ 와 그 표의 각주 번호
    first = next(x for x in summary["guides"] if x.get("label", "").startswith("세부사업명"))
    assert first["kind"] == "각주 번호 1)" and first["text"].startswith("1. 세부사업명") and first["cell"]   # 각주 번호 → 작성 요령 항목 · 그 칸 id
    cover = next(t for t in tabs if any(x.get("label", "").startswith("세부사업명4)") for x in t.get("guides") or ()))   # 표지 — 다른 표의 같은 이름 칸은 제 번호(4)의 항목
    assert cover["table"] != summary["table"]
    placed = sum(len(v) for v in pinned["place"]["tables"].values())
    assert asked["placeGuides"]["items"] == sum(len(t.get("guides") or ()) for t in tabs) == placed   # 표에 붙은 지침이 모두 실린다(표지 표의 겉 상자 안 각주 번호도 — 가장 안쪽 표로)
    assert asked["guides"]["place"] == "s"
    seen.clear()   # 지침이 없으면 자료에 칸이 없다(전과 같은 프롬프트)
    HG.build(s1, use_llm=True, ask=ask, pinned=guides, hints=hints, temp=temp, pairs=False)
    HT.ask_tables(s1, ask=ask, pinned=guides, temp=temp)
    assert not any("guides" in d for d in seen["heading_section"]) and not any("guides" in t for d in seen["heading_tables"] for t in d["tables"])


@needs_form
def test_run_pins_place_guides_from_doc_then_saved(client):
    """실행 시작 때 고정하는 지침(heading_runs._guides) — LLM 을 부르는 실행만 그 자리의 작성 지침을 싣는다 · 「작성요령 삭제」 뒤에는 저장본에서 · 작업 폴더에는 쓰지 않는다."""
    from app import form_guides_api, heading_runs
    d = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    s = server._sess(d)
    assert "place" not in heading_runs._guides(s)   # 스크립트 실행은 싣지 않는다
    pl = heading_runs._guides(s, place=True)["place"]
    assert pl["from"] == "doc" and pl["tables"] and pl["body"] and len(pl["sha1"]) == 40
    assert form_guides_api.load(d) is None   # 판정 자료로 모아도 저장하지는 않는다
    assert client.post(f"/api/docs/{d}/form-cleanup", json={}).status_code == 200   # 지우기 바로 전에 저장한다
    after = heading_runs._guides(s, place=True)["place"]
    assert after["from"] == "saved" and sum(map(len, after["tables"].values())) == sum(map(len, pl["tables"].values()))
