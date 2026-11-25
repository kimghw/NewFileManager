"""양식 안내 지우기(이관 3단계 ⑥ 작성요령 삭제 — spec_작업 ② §14 「3단계」 · app/form_cleanup.py · API …/form-cleanup).
지우는 패턴 목록(FC.PATTERNS)만 지운다: 첫 줄이 「작성 요령」 인 표 · 「<참고 N>」 자료(제목 줄 + 뒤 표) · 안내 색(검정 아닌) ※ 글 · 위첨자 각주 번호 — 실제 KEIT 연차보고서 서식으로."""
from collections import Counter

import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import form_cleanup as FC
from app import server
from app.division_profiles import _structure as S
from app.hwpx_doc import HwpxDoc

pytestmark = pytest.mark.skipif(not M.REPORT_FORM.exists(), reason="KEIT 연차보고서 서식 hwpx 없음")


def _paras(doc):
    return [b for b in S.iter_blocks(doc.blocks()) if b.get("type") == "paragraph"]


def test_find_three_kinds_and_apply_removes_them():
    doc = HwpxDoc(M.REPORT_FORM.read_bytes())
    f = FC.find(doc)
    c = f["counts"]
    assert (c["tables"], c["refs"], c["marks"], c["notes"], c["boxes"]) == (5, 4, 56, 30, 5) and c["total"] == 100, c   # 실측(2026-11-12 · 안내 상자 5 = 2026-11-23) — 서식의 ※ 33줄 가운데 3줄은 작성 요령 표 안(표와 함께)
    assert all("작성" in t["label"] and "요령" in t["label"] for t in f["tables"])
    assert any(t["label"].startswith("앞표지 작성 요령") for t in f["tables"])   # 0행이 빈 줄인 작성 요령 표 — 첫 줄 = 글이 있는 첫 행(2026-11-22: 0행만 봐서 이 표만 결과 문서에 남았다)
    assert all(n["color"] in ("#0000FF", "#FF0000") for n in f["notes"])
    inline = next(n for n in f["notes"] if "2page" in n["guide"])
    assert not inline["whole"] and inline["guide"] == "※ 2page 이내 요약 작성"   # 헤딩과 한 문단 — 헤딩은 남긴다
    done = FC.apply(doc, f)
    assert (done["tables"], done["refs"], done["marks"], done["notes"], done["boxes"]) == (5, 4, 56, 30, 5) and not done["skipped"]
    assert FC.find(doc)["counts"]["total"] == 0
    head = next(b for b in _paras(doc) if (b.get("text") or "").startswith("1. 연구개발과제의 개요") and "※" not in b["text"] and "페이지" not in b["text"])
    assert head["text"].strip() == "1. 연구개발과제의 개요"
    runs = head.get("runs") or [{"text": head["text"], "format": head.get("format") or {}}]
    assert all((r.get("format") or {}).get("color") in (None, "#000000") for r in runs if r["text"].strip())   # 남은 헤딩 글은 제 서식(검정) 그대로


def test_refs_caption_and_table_go_and_blank_lines_do_not_pile_up():
    """「<참고 N>」 자료(2026-11-12 사용자 "<참고 N> 이 패턴도 삭제하도록 해줘라") — 제목 줄 + 바로 뒤 표째. 서식: 성과 절 끝의 <참고 1~3>(빈 줄 · 제목 · 표 되풀이) + 부록의 <참고 1> 위험성 추정 예시.
    지운 뒤 그 자리에 빈 줄이 겹쳐 쌓이지 않는다(앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도) — <참고 1~3> 앞의 빈 줄 둘 바로 뒤가 「4. 연구개발비 사용실적」."""
    doc = HwpxDoc(M.REPORT_FORM.read_bytes())
    refs = FC.find(doc)["refs"]
    assert [r["label"][:8] for r in refs] == ["<참고 1> 연", "<참고 2> 국", "<참고 3> 국", "<참고 1> 위"] and all(r["tables"] == 1 for r in refs)
    FC.apply(doc, FC.find(doc))
    body = doc.blocks()
    texts = [(b.get("text") or "").strip() if b.get("type") == "paragraph" else "<표>" for b in body]
    assert not any(t.startswith("<참고") for t in texts)
    k = next(n for n, t in enumerate(texts) if t.startswith("4. 연구개발비 사용실적("))   # 본문 헤딩(차례의 「…	(페이지표기)」 줄 말고)
    assert texts[k - 2:k] == ["", ""] and texts[k - 3] != "", texts[k - 4:k + 1]   # 앞의 빈 줄 둘은 그대로 · 더 쌓이지 않음


def test_ref_caption_without_table_stays():
    """뒤에 표가 없는 「<참고 N>」 줄은 무엇을 가리키는지 꼴로 알 수 없어 안 지운다."""
    doc = HwpxDoc(M.REPORT_FORM.read_bytes())
    p = next(b for b in _paras(doc) if (b.get("text") or "").startswith("4. 연구개발비 사용실적("))   # 뒤는 빈 줄 · 「5. 다음 연도 …」 — 표 없음
    doc.set_text(p["id"], "<참고 9> 표 없는 참고 줄")
    assert p["id"] not in {r["id"] for r in FC.find(doc)["refs"]}


def test_patterns_list_is_the_registry():
    """지우는 패턴 목록(2026-11-12 사용자 "문서 정리에는 어떤 패턴을 삭제해야하는지 목록이 있어야함") — 종류마다 이름·찾는 것·처리·보기, find 의 counts 와 같은 키."""
    doc = HwpxDoc(M.REPORT_FORM.read_bytes())
    f = FC.find(doc)
    assert [p["key"] for p in f["patterns"]] == ["tables", "refs", "notes", "boxes", "marks"] == list(FC.KINDS)
    assert all(p["name"] and p["rule"] and p["how"] and p["example"] for p in f["patterns"])
    assert {p["key"]: p["count"] for p in f["patterns"]} == {k: f["counts"][k] for k in FC.KINDS}
    e = FC.empty()
    assert e["counts"]["total"] == 0 and len(e["patterns"]) == len(FC.PATTERNS) and all(e[k] == [] for k in FC.KINDS)


def _box(doc, tid):
    return next(b for b in S.iter_blocks(doc.blocks()) if b["id"] == tid)["cells"][0]["blocks"]


def test_guide_box_text_goes_and_the_box_stays_as_a_plain_place_to_write():
    """안내 상자(2026-11-23 사용자 「왜 작성 지침은 4단계에서 정리가 안되지?」 — 「5-1. 연구개발 목표 및 내용」 아래 상자의 빨간 글 「당초계획 대비 변경사항이 있는 경우 작성 … (예시: …)」: 「※」 가 없어 안 지워졌다).
    1칸 상자의 글이 모두 본문 색이 아닌 한 가지 색이고 안내 낱말이 있다 → 글만 지운다. 상자는 쓸 자리로 남고, 남은 빈 줄은 본문 글 모양(검정 · 보통 굵기 · 양쪽 맞춤)이다."""
    doc = HwpxDoc(M.REPORT_FORM.read_bytes())
    boxes = FC.find(doc)["boxes"]
    assert len(boxes) == 5 and all(b["color"] == "#FF0000" and not b["whole"] and b["text"].startswith("당초계획 대비 변경사항이 있는 경우 작성") for b in boxes)
    assert all(len(b["paras"]) == 2 and (b["first"], b["last"]) == (b["paras"][0], b["paras"][-1]) for b in boxes)
    tables = sum(1 for b in S.iter_blocks(doc.blocks()) if b.get("type") == "table")
    FC.apply(doc, {**FC.empty(), "boxes": boxes})   # 상자만
    assert sum(1 for b in S.iter_blocks(doc.blocks()) if b.get("type") == "table") == tables   # 상자(표)는 그대로
    for b in boxes:
        left = _box(doc, b["id"])
        assert [x.get("text") or "" for x in left] == [""], left
        f = left[0]["format"]
        assert (f["color"], f["bold"], f["align"], f["firstLineMm"]) == ("#000000", False, "justify", 0.0)   # 안내의 빨강 · 굵게 · 가운데 · 내어쓰기를 물려받지 않는다
    assert FC.find(doc)["boxes"] == []


def test_guide_box_rule_leaves_boxes_with_written_text_and_colored_title_boxes():
    """사람이 쓴 내용(본문 색 글)이 한 줄이라도 섞인 상자 · 색 글이어도 안내 낱말이 없는 상자(색 글 제목 상자) · 흰 글 상자는 안내 상자가 아니다 — 건드리지 않는다."""
    doc = HwpxDoc(M.REPORT_FORM.read_bytes())
    a, b, c = FC.find(doc)["boxes"][:3]
    black = next(p for p in _paras(doc) if (p.get("text") or "").strip() and not p.get("runs") and (p.get("format") or {}).get("color") in (None, "#000000"))
    doc.apply_format([a["paras"][1]], doc.get_format(black["id"]))   # ⓐ 둘째 줄이 본문 색 — 쓴 내용이 섞인 상자
    doc.set_text(b["paras"][0], "과제 개요")                          # ⓑ 빨간 글이지만 안내 낱말이 없다(색 글 제목 상자)
    doc.set_text(b["paras"][1], "")
    for p in c["paras"]:                                              # ⓒ 흰 글(짙은 바탕 위의 제목)
        doc.apply_format([p], doc.derive_format(doc.get_format(p), {"color": "#FFFFFF"}))
    left = {x["id"] for x in FC.find(doc)["boxes"]}
    assert not left & {a["id"], b["id"], c["id"]} and len(left) == 2
    FC.apply(doc, FC.find(doc))
    assert [x.get("text") for x in _box(doc, b["id"])][0] == "과제 개요" and len(_box(doc, a["id"])) == 2 and all((x.get("text") or "").strip() for x in _box(doc, c["id"]))


def test_guide_box_that_starts_with_the_note_mark_goes_as_a_whole():
    """첫 글이 「※」 로 시작하는 안내 상자(「※ AI 관련 R&D 과제의 경우 … 작성 요망」 꼴 — 안내뿐인 상자)는 상자째 · 그 안의 ※ 줄은 ※ 안내로 따로 세지 않는다(전에는 ※ 줄만 지워져 그 아래 줄이 상자에 남는 꼴)."""
    doc = HwpxDoc(M.REPORT_FORM.read_bytes())
    notes = len(FC.find(doc)["notes"])
    a = FC.find(doc)["boxes"][0]
    doc.set_text(a["paras"][0], "※ AI 관련 R&D 과제의 경우 아래의 사항을 고려하여 작성 요망")   # 글자 모양(빨강)은 그대로
    f = FC.find(doc)
    box = next(b for b in f["boxes"] if b["id"] == a["id"])
    assert box["whole"] and len(f["notes"]) == notes and not set(box["paras"]) & {n["id"] for n in f["notes"]}
    done = FC.apply(doc, f)
    assert done["boxes"] == 5 and not done["skipped"]
    ids = {b["id"] for b in S.iter_blocks(doc.blocks())}
    assert a["id"] not in ids and not ids & set(a["paras"]) and all(b["id"] in ids for b in f["boxes"] if b["id"] != a["id"])   # 그 상자만 상자째 · 나머지 넷은 상자가 남는다


def test_body_color_note_is_content_and_stays():
    """본문 색(검정) ※ 줄은 내용(계획서에서 옮겨 온 「※ 차도선 하루 10회 …」 같은 줄) — 안 지운다."""
    doc = HwpxDoc(M.REPORT_FORM.read_bytes())
    p = next(b for b in _paras(doc) if (b.get("text") or "").strip() and "※" not in b["text"] and not b.get("runs")
             and ((b.get("format") or {}).get("color") in (None, "#000000")))
    doc.set_text(p["id"], "※ 차도선 하루 10회 이상 접안 → 고빈도 Edge Case 자동 축적")
    assert p["id"] not in {n["id"] for n in FC.find(doc)["notes"]}
    FC.apply(doc, FC.find(doc))
    assert any(b["id"] == p["id"] and b["text"].startswith("※ 차도선") for b in _paras(doc))


@pytest.fixture
def client():
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def test_api_list_apply_undo(client):
    d = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    v = client.get(f"/api/docs/{d}/form-cleanup").json()
    assert v["counts"]["total"] == 100 and len(v["tables"]) == 5 and len(v["refs"]) == 4 and {"id", "guide", "whole", "color"} <= set(v["notes"][0])
    assert len(v["boxes"]) == 5 and {"id", "first", "text", "color", "whole"} <= set(v["boxes"][0])   # 안내 상자(2026-11-23)
    assert client.post(f"/api/docs/{d}/form-cleanup", json={"expectRev": v["rev"] + 1}).status_code == 409   # 목록을 읽은 뒤 바뀜
    r = client.post(f"/api/docs/{d}/form-cleanup", json={"expectRev": v["rev"]})
    assert r.status_code == 200, r.text[:600]
    out = r.json()
    assert out["done"]["tables"] == 5 and out["done"]["refs"] == 4 and out["done"]["notes"] == 30 and out["done"]["marks"] == 56 and out["done"]["boxes"] == 5 and out["rev"] == v["rev"] + 1
    assert client.get(f"/api/docs/{d}/form-cleanup").json()["counts"]["total"] == 0
    assert client.post(f"/api/docs/{d}/form-cleanup", json={}).json()["nothing"] is True   # 지울 것 없음 — 편집 안 함
    assert client.post(f"/api/docs/{d}/undo").status_code == 200   # 편집 하나 — 실행 취소 한 번이면 다 돌아온다
    assert client.get(f"/api/docs/{d}/form-cleanup").json()["counts"]["total"] == 100


def test_api_does_not_delete_when_the_guides_cannot_be_kept(client, monkeypatch):
    """지우기 전 작성 지침 저장이 실패하면 지우지 않는다(지운 지침이 어디에도 안 남게 하지 않는다 — spec_워크플로우 ② §18-12 ② · 전에는 지웠다)."""
    from app import form_guides_api
    d = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    v = client.get(f"/api/docs/{d}/form-cleanup").json()

    def boom(s, found=None):
        raise OSError("디스크가 가득 참")
    real_keep = form_guides_api.keep
    monkeypatch.setattr(form_guides_api, "keep", boom)
    r = client.post(f"/api/docs/{d}/form-cleanup", json={"expectRev": v["rev"]})
    assert r.status_code == 503 and "지우지 않았습니다" in r.json()["detail"]
    after = client.get(f"/api/docs/{d}/form-cleanup").json()
    assert after["counts"]["total"] == v["counts"]["total"] and after["rev"] == v["rev"]   # 문서는 그대로
    monkeypatch.setattr(form_guides_api, "keep", real_keep)
    monkeypatch.setattr(form_guides_api, "_path", lambda wid: None)   # 저장할 곳이 없다(작업 저장 끔) — keep 은 예외 없이 쓰지 않고 돌아온다
    r = client.post(f"/api/docs/{d}/form-cleanup", json={"expectRev": v["rev"]})
    assert r.status_code == 503 and "저장할 곳이 없어" in r.json()["detail"]
    assert client.get(f"/api/docs/{d}/form-cleanup").json()["counts"]["total"] == v["counts"]["total"]


def test_api_baseline_is_the_document_before_the_edit(client, monkeypatch):
    """2단계 내용 반영이 사업계획서에서 옮겨 온 위반 종류(그림의 renderingInfo 등)는 이 지우기 탓이 아니다 — 올린 원본에 없던 종류가 이미 있어도 지운다
    (2026-11-12 실측: 원본 기준선만 보는 전체 검사 편집(TEMP 삭제)이 반영 뒤 문서에서 422). 흉내: 원본 기준선을 비워 지금 문서의 위반이 모두 「원본에 없던 종류」 가 되게."""
    d = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    s = server._sess(d)
    chk = s.kit["check"]
    assert sum(chk.counts(chk.check_doc(s.doc))["schema"].values()) > 0   # 이 서식은 원본부터 스키마 위반이 있다 — 비운 기준선이면 원본 대비 검사는 걸린다
    monkeypatch.setattr(server, "owpml_base", lambda s_: {"schema": Counter(), "rules": Counter()})
    r = client.post(f"/api/docs/{d}/form-cleanup", json={})
    assert r.status_code == 200, r.text[:600]
    assert r.json()["done"]["tables"] == 5


def test_samples_only_for_form_write_and_removed_whole():
    """작성 샘플(spec_양식작성 ② §5-6) — find(doc, sample_heads) 일 때만 찾고(이관 · 취합의 작성요령 삭제는 그대로), 제목 줄부터 표까지 통째로 지운다 · 제목 없는 그림은 남긴다."""
    def para(i, t):
        return {"id": i, "type": "paragraph", "text": t, "runs": [{"text": t, "format": {}}]}

    def table(i, t):
        return {"id": i, "type": "table", "nRows": 1, "nCols": 2, "cells": [{"id": i + "c", "row": 0, "col": 0, "blocks": [para(i + "p", t)]}, {"id": i + "d", "row": 1, "col": 0, "blocks": [para(i + "q", "값")]}]}

    class Doc:
        def __init__(self):
            self.b = [para("p1", "1. 개요"), table("t2", "작성을 위한 샘플자료"), para("p3", "■ 작성 예시"), para("p4", ""), table("t5", "가 | 나"),
                      {"id": "i6", "type": "image"}, para("p7", "실제 내용")]
            self.cut = []

        def blocks(self):
            return self.b

        def delete_blocks(self, a, z):
            ids = [x["id"] for x in self.b]
            self.cut.append((a, z))
            del self.b[ids.index(a):ids.index(z) + 1]

    doc = Doc()
    plain = FC.find(doc)
    assert "samples" not in plain and "samples" not in plain["counts"] and all(p["key"] != "samples" for p in plain["patterns"])
    f = FC.find(doc, {"p1"})
    assert [(x["id"], x["last"]) for x in f["samples"]] == [("t2", "t2"), ("p3", "t5")] and f["counts"]["samples"] == 2 and f["counts"]["total"] == 2
    assert next(p for p in f["patterns"] if p["key"] == "samples")["count"] == 2
    done = FC.apply(doc, f)
    assert done["samples"] == 2 and not done["skipped"] and [x["id"] for x in doc.b] == ["p1", "i6", "p7"]   # 제목 없는 그림 · 내용은 남김
