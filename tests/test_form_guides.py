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


needs_form = pytest.mark.skipif(not M.REPORT_FORM.exists(), reason="KEIT 연차보고서 서식 hwpx 없음")


@needs_form
def test_collect_groups_guides_by_heading_and_table():
    data = M.REPORT_FORM.read_bytes()
    doc = HwpxDoc(data)
    graph, tables = M._cached("guides_report", data, doc, "연차보고서")
    got = FG.collect(doc, graph, tables)
    c = got["counts"]
    assert (c["items"], c["marks"]) == (39, 56), c   # 작성 요령 표 5(앞표지 작성 요령 포함 — 2026-11-22: 0행이 빈 줄인 표도 본다) + <참고 N> 4 + ※ 안내 30 · 각주 번호 56(form_cleanup 의 실측과 같은 수)
    kinds = [it["kind"] for it in got["items"]]
    assert (kinds.count("tables"), kinds.count("refs"), kinds.count("notes")) == (5, 4, 30)
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
    assert v["saved"]["counts"]["items"] == 39 and v["saved"]["rev"] == v["rev"] and "kept" not in v and v["groups"]["tables"]
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
    assert saved and saved["counts"]["items"] == 39 and saved["counts"]["marksLinked"] == 51   # 앞표지 작성 요령 표를 지침으로 읽게 되어 표지의 각주 번호(2) … 19))가 그 항목에 이어진다(전 22)
