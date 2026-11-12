"""취합 3방향 엔진(spec_취합 ② §4·§7 · app/merge_gather.py · app/merge_gather_frame.py) — 기준본(빈 계획서 양식에 기관 셋을 반영한 것) ↔ 기관 문서(그 사본을 고쳐 저장해 다시 연 것) ↔ 취합본.
넣는 길(자기 기관 자리 · 공통 자리 · 표 칸 · 이어 넣는 표의 행 · 그림)과 **틀리게 넣지 않고 보고해야 하는 입력**(astra 2026-11-12 — artifacts/gather_design_astra_2026-11-12/answer.md 의 음성 시험 표)을 본다.
실제 문서 시험은 저장소 안 자료만(gather_data), 글 줄만으로 되는 규칙은 손으로 만든 기준본(사전)으로."""
import io
import time

import pytest
from PIL import Image

import gather_data as D
from app import merge_gather as G
from app import merge_gather_frame as F
from app.hwpx_doc import HwpxDoc

ALL = {"orgs": [D.LEAD, D.J1, D.J2], "common": True}


def _png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 90, 160)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def frame():
    return D.base()["frame"]


def _run(frame, part, to, cfg, applied=None, do=True):
    """자리 연결 → 판정 → 계획(→ 반영) → (작성 내용, 계획, 반영 결과 | None)."""
    got = G.links(frame, part)
    assert got["reasons"] == []
    items = G.judge(got["items"], frame, to, cfg, applied)
    pl = G.plan(items, frame, to, part)
    return items, pl, (G.apply(to["doc"], part["doc"], pl) if do and pl["todo"] else None)


def _by(items, **want):
    return [h for h in items if all(h[k] == v for k, v in want.items())]


def _none_planned(frame, part, cfg=ALL):
    """아무것도 넣지 않는다 — 취합본은 그대로."""
    to = D.master()
    before = D.texts(to["doc"])
    items, pl, res = _run(frame, part, to, cfg)
    assert pl["todo"] == 0 and res is None and D.texts(to["doc"]) == before, [(h["kind"], h["status"]) for h in items]
    return items


# ---- 견줄 꼴 · 자리 정보 ----------------------------------------------------------------------------------------

def test_norm_absorbs_spacing_but_keeps_number_spaces():
    assert F.norm("개발  목표 및 내용 ") == F.norm("개발 목표 및 내용") == "개발목표및내용"
    assert F.norm("100 만원") != F.norm("100만원") and F.norm("1 000") != F.norm("1000") and F.norm("AI model") != F.norm("AImodel")   # 수·단위, 영문 낱말 사이 빈칸은 뜻이 있다
    assert F.para_key("(1) 최종목표 ※ 전체 목표를 요약하여 작성") == F.para_key("(1) 최종목표") and F.para_key("※ 안내") == "※안내" and F.para_key("    ") == ""
    assert F.placeholder(" o ") and F.placeholder("-") and F.placeholder("o 세부계획1 :") and not F.placeholder("") and not F.placeholder("o 내용을 씀")


def test_frame_has_place_info_and_an_untouched_copy_has_nothing_to_gather(frame):
    assert [o["key"] for o in frame["orgs"]] == [D.LEAD, D.J1, D.J2] and frame["orgs"][0]["role"] == "lead"
    by = {b["id"]: b for b in frame["blocks"]}
    assert all({"i", "id", "kind", "key", "text", "cls", "path", "scope"} <= set(b) for b in frame["blocks"]) and [b["i"] for b in frame["blocks"]] == list(range(len(frame["blocks"])))
    to = D.master()
    lab = by[D.para(to["doc"], "[공동연구개발기관1(가나대)]", 0)]
    slot = by[D.nxt(to["doc"], lab["id"])]
    assert lab["cls"] == "label" and slot["cls"] == "guide" and slot["scope"]["kind"] == "org" and slot["scope"]["org"] == D.J1 and slot["scope"]["year"] == 1 and lab["id"] in slot["scope"]["labels"]
    assert by[D.para(to["doc"], "□ 배경")]["scope"]["kind"] == "common" and by[D.para(to["doc"], "□ 배경")]["cls"] == "title"
    t = by[D.table_after(to["doc"], "(1) 연구시설·장비 구축(임차)계획")]["table"]   # 기관-연도 행 표 = 이어 넣는 표, 칸마다 그 행의 기관
    assert t["list"] and {c["scope"]["org"] for c in t["cells"] if c.get("scope") and c["scope"]["kind"] == "org"} == {D.LEAD, D.J1, D.J2}
    cost = by[D.table_after(to["doc"], "8-1. 연구개발비 지원·부담계획", 1)]["table"]
    assert {c["cls"] for c in cost["cells"]} >= {"head", "input", "calc"} and not cost["list"]
    assert {"common", "org"} <= {b["scope"]["kind"] for b in frame["blocks"]} and any(c.get("scope", {}).get("kind") == "unknown" for b in frame["blocks"] if b.get("table") for c in b["table"]["cells"])
    assert [(r["id"], r["key"]) for r in F.rows(to["blocks"], frame=frame, doc=to["doc"])] == [(b["id"], b["key"]) for b in frame["blocks"]]   # 취합본 = 기준본 그대로
    got = G.links(frame, D.part(lambda d: None))   # 다시 읽어 id 가 달라진 사본 — 달라진 곳 없음
    assert got["items"] == [] and got["coverage"]["ratio"] == 1.0 and got["coverage"]["anchors"] > 100


# ---- 넣는 길 --------------------------------------------------------------------------------------------------

def _edit_j1(d):
    """가나대 문서 — 제 자리(1차년도 ① 개발 목표)의 자리표시 줄을 채우고 한 줄 더, 공통 자리(□ 필요성)에 글 + 넓은 그림, 제 표 칸, 기관-연도 행 표의 제 덩이에 행 하나."""
    o = D.nxt(d, D.para(d, "[공동연구개발기관1(가나대)]", 0))
    d.set_text(o, " o 가나대 1차년도 개발 목표")
    d.insert_after(o, [{"kind": "paragraph", "text": "   - 가나대 세부 목표"}])
    need = D.nxt(d, D.para(d, "□ 필요성"))
    d.set_text(need, " o 가나대가 쓴 필요성")
    d.insert_image(need, _png(2400, 300), "png", width_mm=300)
    d.set_text(D.cell(d, D.table_after(d, "[공동연구개발기관 : 가나대]"), 1, 1)["id"], "o 사업화 형태 : 기술이전")
    lt = D.table_after(d, "(1) 연구시설·장비 구축(임차)계획")
    m = d.clone_rows(lt, 3, 3, [1, 8], keep_text=False)["map"]   # 가나대 2026 행 아래에 한 행
    new = sorted((c for c in d.table_block(lt)["cells"] if c["id"] in m.values()), key=lambda c: c["col"])
    for c, text in zip(new, ["2026", "레이저 가공기", "구매", "가공", "1", "50,000", "26년 5월", "가나대 실험동"]):
        d.set_text(c["id"], text)


def test_own_place_common_place_cell_row_and_picture_then_replan_is_empty_and_undo_brings_them_back(frame):
    part, to = D.part(_edit_j1, "가나대"), D.master()
    cfg = {"orgs": [D.J1], "common": True}
    items, pl, res = _run(frame, part, to, cfg)
    assert sorted((h["kind"], h["status"], h["scope"]["kind"]) for h in items) == [("cells", "ready", "org"), ("filled", "ready", "common"), ("filled", "ready", "org"), ("rows", "ready", "org")]
    assert all(h["unique"] and h["key"] for h in items) and len({h["key"] for h in items}) == 4
    own = next(h for h in _by(items, kind="filled") if h["scope"]["org"] == D.J1)
    assert own["scope"]["orgName"] == D.J1 and own["scope"]["year"] == 1 and own["counts"]["paragraphs"] == 2 and "개발 목표" in " ".join(own["path"])
    assert pl["todo"] == 4 and pl["skipped"] == {} and len(pl["items"]) == 4
    assert res["counts"] == {**res["counts"], "hunks": 4, "paragraphs": 3, "pictures": 1, "placeholders": 2, "cells": 1, "rows": 1, "fitted": 1, "skipped": 0}
    assert D.save(part["doc"]) == part["bytes"]   # 기관 문서(원본)는 그대로
    doc = to["doc"]
    tx = D.texts(doc)
    i = tx.index("[공동연구개발기관1(가나대)]")
    assert tx[i + 1:i + 3] == ["o 가나대 1차년도 개발 목표", "- 가나대 세부 목표"] and tx[i - 2] == "o" and "[공동연구개발기관2(다라연)]" in tx[i + 3:i + 5]   # 제 라벨 아래에만 — 앞 기관의 자리표시 줄은 그대로
    i = tx.index("□ 필요성")
    assert tx[i + 1:i + 3] == ["o 가나대가 쓴 필요성", "image"]
    img = next(b for b in D.top(doc) if b["type"] == "image")
    assert 20 < img["widthMm"] < 200   # 300mm 그림이 본문 폭으로
    assert D.cell(doc, D.table_after(doc, "[공동연구개발기관 : 가나대]"), 1, 1)["text"] == "o 사업화 형태 : 기술이전"
    lt = next(b for b in D.top(doc) if b["id"] == D.table_after(doc, "(1) 연구시설·장비 구축(임차)계획"))
    assert lt["nRows"] == 8 and [D.cell(doc, lt["id"], 4, c)["text"] for c in (0, 1, 2, 6)] == ["가나대", "2026", "레이저 가공기", "50,000"] and D.cell(doc, lt["id"], 5, 1)["text"] == "2027"
    assert len(HwpxDoc(D.save(doc)).blocks()) == len(doc.blocks())   # 저장해 다시 열림

    again = G.judge(G.links(frame, part)["items"], frame, D.side(doc), cfg, res["applied"])   # 다시 계획 = 할 일 없음
    assert [h["status"] for h in again] == ["same"] * 4 and G.plan(again, frame, D.side(doc), part)["todo"] == 0
    assert [h["key"] for h in again] == [h["key"] for h in items]   # 다시 맞춰도 같은 열쇠
    bare = G.judge(G.links(frame, part)["items"], frame, D.side(doc), cfg)   # 넣은 기록이 없어도 본문·칸은 그 자리의 내용으로 안다(행은 기록으로만)
    assert sorted(h["status"] for h in bare) == ["ready", "same", "same", "same"] and _by(bare, status="ready")[0]["kind"] == "rows"

    undone = G.judge(G.links(frame, part)["items"], frame, D.master(), cfg, res["applied"])   # 실행 취소(넣은 블록이 없음) — 기록을 안 믿고 다시 할 일
    assert [h["status"] for h in undone] == ["ready"] * 4
    gone = res["applied"][own["key"]]["ids"]
    doc.delete_blocks(gone[1], gone[1])   # 넣은 두 줄 가운데 하나만 지움 — 「이미 넣음」 도 「넣을 수 있음」 도 아니다
    half = G.judge(G.links(frame, part)["items"], frame, D.side(doc), cfg, res["applied"])
    assert next(h for h in half if h["key"] == own["key"])["status"] == "overlap" and G.plan(half, frame, D.side(doc), part)["todo"] == 0


def test_added_table_travels_with_its_paragraph_in_order(frame):
    def edit(d):
        o = D.nxt(d, D.para(d, "□ 배경"), 2)
        d.set_text(o, " o 표와 함께 쓴 글")
        new = d.insert_after(o, [{"kind": "copy", "srcId": D.table_after(d, "다. 여성 참여연구자 비율")}, {"kind": "paragraph", "text": "표 아래 설명"}])   # 머리가 같은 표를 하나 더 — 그 구간에는 하나뿐
        d.set_text(d.table_block(new[0])["cells"][-1]["id"], "33%")
    part, to = D.part(edit), D.master()
    items, pl, res = _run(frame, part, to, ALL)
    assert [(h["kind"], h["status"], h["counts"]["paragraphs"], h["counts"]["tables"]) for h in items] == [("filled", "ready", 2, 1)]
    assert res["counts"] == {**res["counts"], "hunks": 1, "blocks": 3, "paragraphs": 2, "tables": 1, "placeholders": 1}
    tx = D.texts(to["doc"])
    i = tx.index("o 표와 함께 쓴 글")
    assert tx[i - 2:i + 3] == ["□ 배경", "", "o 표와 함께 쓴 글", "table", "표 아래 설명"]
    assert D.top(to["doc"])[i + 1]["cells"][-1]["text"] == "33%" and D.cell(to["doc"], D.table_after(to["doc"], "다. 여성 참여연구자 비율"), 1, 2)["text"] != "33%"   # 원래 표는 그대로
    again = G.judge(G.links(frame, part)["items"], frame, D.side(to["doc"]), ALL)   # 기록 없이도 그 자리의 내용(표 포함)으로 「이미 있음」
    assert [h["status"] for h in again] == ["same"]


def test_two_parts_in_sequence_first_takes_the_common_place_and_equal_list_rows_both_stay(frame):
    def edit(org, k, who):
        def run(d):
            d.set_text(D.nxt(d, D.para(d, f"[공동연구개발기관{k}({org})]", 0)), f" o {org} 개발 목표")
            d.set_text(D.nxt(d, D.para(d, "□ 배경"), 2), f" o {who}가 쓴 배경")   # 같은 공통 자리에 서로 다른 글
            t = D.table_after(d, "7-2. 연구시설·장비 보유현황", 1)                  # 공통 목록 표에 글이 같은 행
            m = d.clone_rows(t, 2, 2, None, keep_text=False)["map"]
            for c, text in zip(sorted((c for c in d.table_block(t)["cells"] if c["id"] in m.values()), key=lambda c: c["col"]), ["센서", "S1", "2025", "100"]):
                d.set_text(c["id"], text)
        return run
    a, b, to = D.part(edit(D.J1, 1, "A"), "A"), D.part(edit(D.J2, 2, "B"), "B"), D.master()
    ia, _, ra = _run(frame, a, to, {"orgs": [D.J1], "common": True})
    assert [h["status"] for h in ia] == ["ready"] * 3 and ra["counts"]["hunks"] == 3
    to = D.side(to["doc"])   # 앞 문서를 반영한 뒤의 취합본으로 다음 문서를 계획
    ib, pb, rb = _run(frame, b, to, {"orgs": [D.J2], "common": True})
    common = next(h for h in ib if h["scope"]["kind"] == "common" and h["kind"] == "filled")
    assert common["status"] == "overlap" and "A가 쓴 배경" in common["detail"] and pb["skipped"] == {"overlap": 1} and rb["counts"]["hunks"] == 2
    doc = to["doc"]
    tx = D.texts(doc)
    assert "o A가 쓴 배경" in tx and "o B가 쓴 배경" not in tx and "o 가나대 개발 목표" in tx and "o 다라연 개발 목표" in tx
    t = next(x for x in D.top(doc) if x["id"] == D.table_after(doc, "7-2. 연구시설·장비 보유현황", 1))
    assert t["nRows"] == 5 and [[D.cell(doc, t["id"], r, c)["text"] for c in (0, 1, 3)] for r in (3, 4)] == [["센서", "S1", "100"]] * 2   # 두 기관의 같은 행 — 둘 다 남는다
    to = D.side(doc)
    assert [h["status"] for h in G.judge(G.links(frame, a)["items"], frame, to, {"orgs": [D.J1], "common": True}, ra["applied"])] == ["same"] * 3
    left = G.judge(G.links(frame, b)["items"], frame, to, {"orgs": [D.J2], "common": True}, rb["applied"])
    assert sorted(h["status"] for h in left) == ["overlap", "same", "same"] and G.plan(left, frame, to, b)["todo"] == 0


# ---- 틀리게 넣지 않고 보고(§7 음성 시험) ---------------------------------------------------------------------------

def test_deleting_own_section_is_reported_and_other_orgs_content_stays_out(frame):
    def edit(d):
        a, z = D.para(d, "[공동연구개발기관1 : 가나대]"), D.para(d, "[공동연구개발기관2 : 다라연]")
        blocks = D.top(d)
        d.delete_blocks(a, blocks[next(n for n, x in enumerate(blocks) if x["id"] == z) - 1]["id"])   # 8-2 (2) 의 가나대 절을 통째로
        d.set_text(D.cell(d, D.table_after(d, "[공동연구개발기관2 : 다라연]"), 2, 4)["id"], "1,000")   # 다라연 표의 칸
    part = D.part(edit)
    items = _none_planned(frame, part, {"orgs": [D.J1], "common": True})
    gone = _by(items, kind="removed")
    assert len(gone) == 1 and gone[0]["status"] == "removed" and gone[0]["scope"]["org"] == D.J1 and "가나대" in gone[0]["text"]
    cells = _by(items, kind="cells")
    assert len(cells) == 1 and cells[0]["scope"]["org"] == D.J2 and cells[0]["status"] == "otherOrg"   # 다라연 것은 다라연으로만 — 가나대 문서의 반영 범위 밖
    to = D.master()
    _, pl, res = _run(frame, part, to, {"orgs": [D.J2], "common": False})   # 다라연을 반영할 기관으로 지정하면 그 칸만 — 취합본의 가나대 절은 그대로
    assert pl["todo"] == 1 and res["counts"]["cells"] == 1 and "[공동연구개발기관1 : 가나대]" in D.texts(to["doc"])
    assert D.cell(to["doc"], D.table_after(to["doc"], "[공동연구개발기관2 : 다라연]"), 2, 4)["text"] == "1,000"


def test_writing_under_a_deleted_label_is_not_given_to_the_org_above(frame):
    def edit(d):
        lab = D.para(d, "[공동연구개발기관1(가나대)]", 0)
        d.set_text(D.nxt(d, lab), " o B 전용 문장")
        d.delete_blocks(lab, lab)   # 같은 뼈대가 되풀이되는 곳에서 제 라벨만 지우고 그 아래에 씀
    items = _none_planned(frame, D.part(edit))
    assert [(h["kind"], h["status"]) for h in items] == [("removed", "removed"), ("filled", "unknownPlace")]
    assert "구분 라벨" in items[1]["detail"] and items[1]["text"] == "o B 전용 문장" and items[1]["unique"] == ""


def test_blank_lines_spacing_and_line_breaks_alone_are_not_content(frame):
    def edit(d):
        head = D.para(d, "1-1. 개발 대상 기술·제품의 개요")
        blank = D.nxt(d, head)
        d.delete_blocks(blank, blank)                                                       # 빈 문단을 지움(합침)
        d.insert_after(D.para(d, "□ 배경"), [{"kind": "paragraph", "text": ""}, {"kind": "paragraph", "text": "   "}])   # 빈 문단을 더함
        d.set_text(head, "  1-1.  개발 대상 기술·제품의   개요 ")                          # 빈칸·줄 나눔만
        d.set_text(D.para(d, "□ 필요성"), "□  필 요 성")
    got = G.links(frame, D.part(edit))
    assert got["items"] == [] and got["coverage"]["ratio"] == 1.0


def test_edited_title_is_reported_and_text_under_it_is_held(frame):
    def edit(d):
        t = D.para(d, "o 안전책임자의 지정·운영")
        d.set_text(t, " o 안전책임자의 지정·운영(확정)")
        d.set_text(D.nxt(d, t), "   - 책임자를 지정함")
    items = _none_planned(frame, D.part(edit))
    assert [(h["kind"], h["status"]) for h in items] == [("changed", "changed"), ("filled", "unknownPlace")] and "제목 줄" in items[1]["detail"]
    kept = G.judge(G.links(frame, D.part(edit))["items"], frame, D.master(), {**ALL, "decisions": {items[1]["key"]: {"value": "keep", "source": "user"}}})
    assert kept[1]["status"] == "unknownPlace" and kept[1]["decision"]["value"] == "keep"   # 결정은 막힌 것을 넣게 하지 못한다


def test_edited_form_lines_are_one_report_and_a_place_tied_to_a_table_is_held(frame):
    def edit(d):
        for k, text in enumerate(("1-1. 개발 대상 기술·제품의 개요", "1-2. 연구개발과제의 배경 및 필요성", "2-1. 최종목표")):   # 목차의 쪽 번호를 줄마다 고침 — 양식 글이 바뀐 것
            d.set_text(D.para(d, text + " (페이지 표기)"), f" {text} ····· {k + 3}")
        dot = D.nxt(d, D.para(d, "□ 필요성"), 4)   # 「⋅」 자리표시 줄 — 취합본에서는 작성요령 표와 한 문단에 묶여 있다
        d.set_text(dot, "   ⋅ 세부 내용을 씀")
        d.set_text(D.para(d, "(단위 : 천원)", 0), "우리 기관은 백만원 단위로 적었습니다")   # 양식 글을 전혀 다른 글로 — 고쳐 쓴 것인지 새 내용인지 모른다
    part = D.part(edit)
    items = _none_planned(frame, part)
    assert [(h["kind"], h["status"], h["counts"]["paragraphs"]) for h in items] == [("changed", "changed", 2), ("changed", "changed", 1), ("filled", "unknownPlace", 1),
                                                                                       ("removed", "removed", 0), ("added", "unknownPlace", 1)]
    assert "외 1줄" in items[0]["detail"] and "한 문단에 묶여" in items[2]["detail"] and items[2]["to"]["prev"]   # 넣지 않아도 화면이 갈 자리는 준다
    assert "양식 글" in items[4]["detail"]


def test_changed_merge_or_columns_make_the_table_structure_only(frame):
    def merged(d):
        t = D.table_after(d, "7-2. 연구시설·장비 보유현황", 1)
        d.merge_cells(t, 1, 0, 1, 1)                       # 같은 머리 글 · 병합만 달라짐
        d.set_text(D.cell(d, t, 2, 3)["id"], "쓴 글")
    items = _none_planned(frame, D.part(merged))
    assert [(h["kind"], h["status"]) for h in items] == [("cells", "structure")] and "병합" in items[0]["detail"]

    def narrower(d):
        t = D.table_after(d, "7-2. 연구시설·장비 보유현황", 1)
        d.delete_cols(t, 6, 7)                             # 열이 달라짐 = 다시 그린 표
        d.set_text(D.cell(d, t, 1, 0)["id"], "가나대")
    items = _none_planned(frame, D.part(narrower))
    assert [(h["kind"], h["status"]) for h in items] == [("cells", "structure")] and items[0]["base"]["table"] and items[0]["from"]["table"]

    def shorter(d):
        d.delete_rows(D.table_after(d, "7-2. 연구시설·장비 보유현황", 1), 2, 2)   # 이어 넣는 표라도 행이 줄면 넣을 것이 아니다
    assert [(h["kind"], h["status"]) for h in _none_planned(frame, D.part(shorter))] == [("cells", "structure")]


def test_row_above_a_blank_row_unknown_column_and_nested_table_cell(frame):
    to0 = D.master()
    unknown = next(c["id"] for b in frame["blocks"] if b.get("table") for c in b["table"]["cells"] if c.get("scope", {}).get("kind") == "unknown" and c["cls"] == "input")
    box, deep = next((b["id"], c["id"]) for b in frame["blocks"] if b.get("table") for c in b["table"]["cells"] if c["cls"] == "complex")
    del to0

    def edit(d):
        t = D.table_after(d, "o 동 과제와 관련된 기보유 지재권")
        m = d.clone_rows(t, 1, 1, None, keep_text=False, above=True)["map"]   # 머리 행 바로 아래(빈 행 위)에 한 행
        for c, text in zip(sorted((c for c in d.table_block(t)["cells"] if c["id"] in m.values()), key=lambda c: c["col"]), ["가나대", "특허A", "한국", "10-1234"]):
            d.set_text(c["id"], text)
        d.set_text(unknown, "어느 기관의 열인지 모르는 칸")   # 7-3 기관 열 표의 자리표시 열
        cell = next(c for b in D.top(d) if b["id"] == box for c in b["cells"] if c["id"] == deep)
        d.set_text(next(x for x in cell["blocks"] if x["type"] == "table")["cells"][0]["id"], "칸 안 표에 쓴 글")
    part, to = D.part(edit), D.master()
    items, pl, res = _run(frame, part, to, ALL)
    st = {(h["kind"], h["status"]): h for h in items}
    assert set(st) == {("cells", "structure"), ("cells", "unknownPlace"), ("rows", "ready")} and st[("rows", "ready")]["base"]["above"] is True
    assert "표·그림" in st[("cells", "structure")]["detail"] and "알아내지 못한" in st[("cells", "unknownPlace")]["detail"]
    doc, t = to["doc"], D.table_after(to["doc"], "o 동 과제와 관련된 기보유 지재권")
    assert res["counts"]["rows"] == 1 and [[D.cell(doc, t, r, c)["text"] for c in (0, 3)] for r in (1, 2, 3)] == [["가나대", "10-1234"], ["", ""], ["", ""]]   # 머리 행을 본뜨지 않는다 — 빈 자료 행 위에
    key = st[("rows", "ready")]["key"]
    assert _by(G.judge(G.links(frame, part)["items"], frame, D.side(doc), ALL, res["applied"]), key=key)[0]["status"] == "same"
    doc.set_text(res["applied"][key]["ids"][1], "사람이 고친 특허")   # 넣은 행을 그 뒤 고침 — 다시 넣지도 「그대로」 라 하지도 않는다
    assert _by(G.judge(G.links(frame, part)["items"], frame, D.side(doc), ALL, res["applied"]), key=key)[0]["status"] == "overlap"


def _edit_scope(d):
    d.set_text(D.nxt(d, D.para(d, "[공동연구개발기관1(가나대)]", 0)), " o 가나대 글")
    d.set_text(D.nxt(d, D.para(d, "[공동연구개발기관2(다라연)]", 0)), " o 남의 자리에 쓴 글")
    d.set_text(D.nxt(d, D.para(d, "□ 배경"), 2), " o 공통 자리 글")


def test_unassigned_other_org_common_switch_and_decisions(frame):
    part = D.part(_edit_scope)
    assert [h["status"] for h in _none_planned(frame, part, {"orgs": [], "common": True})] == ["unassigned"] * 3   # 미지정 = 아무것도 안 넣음(「가리지 않음」 이 아니다)
    to = D.master()
    items = G.judge(G.links(frame, part)["items"], frame, to, {"orgs": [D.J1], "common": False})
    st = {(h["scope"]["kind"], h["scope"]["org"]): h["status"] for h in items}
    assert st == {("org", D.J1): "ready", ("org", D.J2): "otherOrg", ("common", None): "otherOrg"}
    own = next(h for h in items if h["status"] == "ready")
    for value in ("skip", "check"):   # 사람·LLM 이 뺀 것은 계획에 안 든다
        cut = G.judge(G.links(frame, part)["items"], frame, to, {"orgs": [D.J1], "common": True, "decisions": {own["key"]: {"value": value, "source": "llm", "reason": "안내 글"}}})
        pl = G.plan(cut, frame, to, part)
        assert pl["todo"] == 1 and pl["skipped"] == {"otherOrg": 1, value: 1} and pl["items"][0]["scope"]["kind"] == "common"
    items, pl, res = _run(frame, part, to, {"orgs": [D.J1], "common": True})
    tx = D.texts(to["doc"])
    assert pl["todo"] == 2 and "o 가나대 글" in tx and "o 공통 자리 글" in tx and "o 남의 자리에 쓴 글" not in tx


def test_place_written_by_a_person_first_is_overlap_not_overwritten(frame):
    def edit(d):
        _edit_scope(d)
        t = D.table_after(d, "[공동연구개발기관 : 가나대]")
        d.set_text(D.cell(d, t, 1, 1)["id"], "가나대 전략")
        d.set_text(D.cell(d, t, 2, 1)["id"], "가나대 계획")
    part, to = D.part(edit), D.master()
    doc = to["doc"]
    doc.set_text(D.nxt(doc, D.para(doc, "[공동연구개발기관1(가나대)]", 0)), " o 사람이 먼저 쓴 글")
    doc.insert_after(D.nxt(doc, D.para(doc, "□ 배경"), 2), [{"kind": "paragraph", "text": "사람이 덧붙인 줄"}])
    t = D.table_after(doc, "[공동연구개발기관 : 가나대]")
    doc.set_text(D.cell(doc, t, 1, 1)["id"], "사람이 쓴 칸")
    to = D.side(doc)
    items, pl, res = _run(frame, part, to, {"orgs": [D.J1], "common": True})
    body = [h for h in items if h["kind"] == "filled" and h["status"] != "otherOrg"]
    assert [h["status"] for h in body] == ["overlap", "overlap"] and "사람이 먼저 쓴 글" in " ".join(h["detail"] for h in body)
    cells = _by(items, kind="cells")[0]
    assert cells["status"] == "ready" and sorted(c["status"] for c in cells["from"]["cells"]) == ["overlap", "ready"] and "겹침 1" in cells["detail"]
    assert pl["todo"] == 1 and res["counts"]["cells"] == 1 and D.cell(doc, t, 1, 1)["text"] == "사람이 쓴 칸" and D.cell(doc, t, 2, 1)["text"] == "가나대 계획"
    tx = D.texts(doc)
    assert "o 사람이 먼저 쓴 글" in tx and "o 가나대 글" not in tx and "o 공통 자리 글" not in tx
    after = G.judge(G.links(frame, part)["items"], frame, D.side(doc), {"orgs": [D.J1], "common": True}, res["applied"])
    assert _by(after, kind="cells")[0]["status"] == "overlap" and G.plan(after, frame, D.side(doc), part)["todo"] == 0


def test_calc_cells_are_never_copied_and_sums_over_written_cells_are_recalculated(frame):
    def edit(d):
        t = D.table_after(d, "8-1. 연구개발비 지원·부담계획", 1)
        for c, text in ((4, "500,000"), (5, "30,000"), (6, "70,000"), (7, "999")):   # 가나대 행: 현금(A)·현금(B)·현물(C) + 계산 칸 소계(D)에 쓴 수
            d.set_text(D.cell(d, t, 6, c)["id"], text)
        d.set_text(D.cell(d, t, 4, 5)["id"], "50,000")   # 주관 행의 현금(B) — 그 행에는 비율(식) 칸이 걸려 있다
    part, to = D.part(edit), D.master()
    items, pl, res = _run(frame, part, to, ALL)
    calc = _by(items, status="calc")
    assert len(calc) == 1 and calc[0]["kind"] == "cells" and [c["text"] for c in calc[0]["from"]["cells"]] == ["999"]
    assert pl["todo"] == 1 and pl["skipped"] == {"calc": 1} and {c["why"] for c in pl["calc"]} == {"partValue", "operands"}
    doc, t = to["doc"], D.table_after(to["doc"], "8-1. 연구개발비 지원·부담계획", 1)
    assert [D.cell(doc, t, 6, c)["text"] for c in (4, 5, 6, 7, 8, 9, 10)] == ["500,000", "30,000", "70,000", "100,000", "530,000", "70,000", "600,000"]   # 기관의 999 가 아니라 쓴 칸의 합
    assert [D.cell(doc, t, 4, c)["text"] for c in (5, 7, 8, 10)] == ["50,000", "230,000", "850,000", "1,030,000"] and D.cell(doc, t, 16, 5)["text"] == "100,000"   # 합의 합(소계 행)까지
    need = [c for c in res["calc"] if c["action"] == "needed"]
    assert res["counts"]["cells"] == 4 and res["counts"]["recalculated"] == len(res["calc"]) - len(need) >= 8
    assert len(need) == 4 and all(c["kind"] == "expr" and c["now"] is None for c in need) and D.cell(doc, t, 5, 5)["text"].startswith("10.0%")   # 비율은 「다시 계산 필요」 로만 — 수를 지어내지 않는다
    again = G.judge(G.links(frame, part)["items"], frame, D.side(doc), ALL, res["applied"])
    assert sorted(h["status"] for h in again) == ["calc", "same"] and G.plan(again, frame, D.side(doc), part)["todo"] == 0


def test_apply_skips_a_place_that_moved_after_the_plan(frame):
    part, to = D.part(_edit_scope), D.master()
    items, pl, _ = _run(frame, part, to, {"orgs": [D.J1], "common": True}, do=False)
    doc = to["doc"]
    doc.insert_after(D.nxt(doc, D.para(doc, "□ 배경"), 2), [{"kind": "paragraph", "text": "계획 뒤에 든 줄"}])
    res = G.apply(doc, part["doc"], pl)
    assert res["counts"]["hunks"] == 1 and [s["why"] for s in res["skipped"]] == ["moved"] and "o 공통 자리 글" not in D.texts(doc) and "o 가나대 글" in D.texts(doc)


# ---- 손으로 만든 기준본 — 글 줄만으로 되는 규칙 -------------------------------------------------------------------

def _fb(rows):
    """[(id, 글, cls, 기관 | None)] → 기준본 자리 정보(기관 자리의 라벨 = 그 기관의 첫 label 줄)."""
    out, label = [], {}
    for i, (bid, text, cls, org) in enumerate(rows):
        if cls == "label" and org:
            label[org] = bid
        sc = {"kind": "org" if org else "common", "org": org, "year": None, "stage": None, "labels": [label[org]] if org else []}
        out.append({"i": i, "id": bid, "kind": "p", "key": F.para_key(text), "text": text, "cls": cls, "path": [], "scope": sc})
    return {"rev": 1, "orgs": [{"key": k, "name": k, "role": "joint"} for k in label], "blocks": out}


def _ps(texts, prefix="s"):
    return {"blocks": [{"id": f"{prefix}{i}", "type": "paragraph", "text": t} for i, t in enumerate(texts)]}


def _to(frame):
    return {"blocks": [{"id": b["id"], "type": "paragraph", "text": b["text"]} for b in frame["blocks"]]}


def test_repeated_same_lines_do_not_fix_a_place():
    fr = _fb([("a", "1. 검토", "title", None), ("n1", "해당 없음", "fixed", None), ("n2", "해당 없음", "fixed", None), ("n3", "해당 없음", "fixed", None), ("z", "2. 결론", "title", None)])
    got = G.links(fr, _ps(["1. 검토", "검토 완료", "해당 없음", "2. 결론"]))
    assert [(h["kind"], h["status"], h["text"]) for h in got["items"]] == [("added", "unknownPlace", "검토 완료")] and "여럿" in got["items"][0]["detail"]
    assert G.plan(G.judge(got["items"], fr, _to(fr), {"orgs": ["x"], "common": True}), fr, _to(fr), None)["todo"] == 0
    # 글머리만 있는 자리표시 줄은 여럿이어도 된다 — 어느 줄을 대신했다고 봐도 결과가 같다
    fr = _fb([("a", "□ 배경", "title", None), ("o1", " o ", "guide", None), ("d1", " - ", "guide", None), ("o2", " o ", "guide", None), ("d2", " - ", "guide", None), ("z", "□ 필요성", "title", None)])
    got = G.links(fr, _ps(["□ 배경", "o 첫째", "-", "o 둘째", "- 둘째의 세부", "□ 필요성"]))
    items = G.judge(got["items"], fr, _to(fr), {"orgs": ["x"], "common": True})
    assert [(h["kind"], h["status"], h["base"]["ids"]) for h in items] == [("filled", "ready", ["o1"]), ("filled", "ready", ["o2", "d2"])]
    assert [h["to"]["prev"] for h in items] == ["o1", "o2"]


def test_skeleton_repeated_per_org_needs_its_label():
    rows = [("t", "① 개발 목표", "title", None)]
    for k in "ABC":
        rows += [(f"L{k}", f"[기관 {k}]", "label", k), (f"h{k}", "가. 계획", "title", k), (f"o{k}", " o ", "guide", k)]
    fr = _fb([*rows, ("e", "② 개발 내용", "title", None)])
    full = ["① 개발 목표", "[기관 A]", "가. 계획", "o", "[기관 B]", "가. 계획", "o B 내용", "[기관 C]", "가. 계획", "o", "② 개발 내용"]
    ok = G.links(fr, _ps(full))["items"]
    assert [(h["kind"], h["status"], h["scope"]["org"], h["base"]["prev"]) for h in ok] == [("filled", "ready", "B", "hB")]
    lost = G.links(fr, _ps([t for t in full if t != "[기관 B]"]))   # B 의 라벨만 없음 — 「가. 계획」 이 둘이라 닻이 못 되고, 쓴 글은 A 것으로 삼지 않는다
    assert all(h["status"] != "ready" for h in lost["items"]) and any(h["status"] == "unknownPlace" and "B 내용" in h["text"] for h in lost["items"])
    tail = G.links(fr, _ps([*full[:4], "A 가 항목 끝에 덧붙인 글", *full[4:6], "o", *full[7:]]))["items"]   # 뒤 경계가 다음 항목의 라벨 — 앞 항목 것
    assert [(h["kind"], h["status"], h["scope"]["org"], h["base"]["next"]) for h in tail] == [("added", "ready", "A", "LB")]
    assert G.links(fr, _ps(["전혀", "다른", "문서"])) == {"coverage": {"anchors": 0, "blocks": 0, "ratio": 0.0}, "items": [], "reasons": ["noMatch"]}


def _tbl(bid, grid, prefix="c"):
    """[[글 …] …] → 표 블록(HwpxDoc.blocks 의 꼴)."""
    cells = [{"id": f"{prefix}{bid}{r}{c}", "row": r, "col": c, "rowSpan": 1, "colSpan": 1, "text": t, "blocks": []} for r, row in enumerate(grid) for c, t in enumerate(row)]
    return {"id": bid, "type": "table", "nRows": len(grid), "nCols": len(grid[0]), "cells": cells}


def _fb_table(i, block, head_rows=1, **flags):
    g = F.grid(block)
    for c in g["cells"]:
        c.pop("cx")
        c["cls"] = "head" if c["r"] < head_rows else "input"
    g.update({"list": False, "guide": False, **flags})
    return {"i": i, "id": block["id"], "kind": "tbl", "key": F._head_key(g["cols"], F._heads(g)), "text": "", "cls": "table", "path": [],
            "scope": {"kind": "common", "org": None, "year": None, "stage": None, "labels": []}, "table": g}


def test_redrawn_transposed_table_with_the_same_header_words_is_structure_only():
    fr = _fb([("a", "(1) 부담 계획", "title", None), ("z", "(2) 다음", "title", None)])
    fr["blocks"].insert(1, _fb_table(1, _tbl("t1", [["항목", "현금", "현물"], ["", "", ""]])))
    part = {"blocks": [{"id": "s0", "type": "paragraph", "text": "(1) 부담 계획"}, _tbl("u1", [["항목", "장비"], ["현금", "100"], ["현물", "200"]], "d"),
                       {"id": "s2", "type": "paragraph", "text": "(2) 다음"}]}
    got = G.links(fr, part)["items"]
    assert [(h["kind"], h["status"], h["base"]["table"], h["from"]["table"]) for h in got] == [("cells", "structure", "t1", "u1")]
    same = {"blocks": [part["blocks"][0], _tbl("u1", [["항목", "현금", "현물"], ["장비", "100", ""]], "d"), part["blocks"][2]]}   # 같은 격자면 칸마다
    got = G.links(fr, same)["items"]
    assert [(h["kind"], h["status"], [(c["to"], c["text"]) for c in h["from"]["cells"]]) for h in got] == [("cells", "ready", [("ct110", "장비"), ("ct111", "100")])]


def test_links_stays_fast_on_thousands_of_blocks():
    rows, texts, n = [], [], 0
    for ch in range(40):
        rows.append((f"c{ch}", f"{ch + 1}. 장 제목 {ch + 1}", "title", None))
        texts.append(rows[-1][1])
        for k in range(12):
            org = f"기관{k}"
            rows.append((f"L{ch}_{k}", f"[{org}]", "label", org))
            texts.append(rows[-1][1])
            for sec in ("가. 개요", "나. 내용", "다. 계획"):
                rows += [(f"h{n}", sec, "title", org), (f"o{n}", " o ", "guide", org), (f"d{n}", " - ", "guide", org), (f"x{n}", "", "guide", org)]
                texts += [sec, f"o {org} {ch} {sec} 내용" if (n % 37) == 0 else "o", "-", ""]
                n += 1
    fr = _fb(rows)
    assert len(rows) > 6000
    t0 = time.perf_counter()
    got = G.links(fr, _ps(texts))
    took = time.perf_counter() - t0
    want = sum(1 for k in range(n) if k % 37 == 0)
    assert len(got["items"]) == want and all(h["kind"] == "filled" and h["status"] == "ready" for h in got["items"]) and took < 5, took
