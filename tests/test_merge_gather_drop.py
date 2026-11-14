"""끌어 넣기(spec_취합 ② §4-6 — app/merge_gather_drop.py). 저장소 안 자료만: 값을 반영한 계획서 양식(merge_data.small 의 원본 쪽 = 나눠 준 프레임)을 취합본으로,
그 사본의 「1-2. › □ 필요성」 절에 글·넓은 그림·표 캡션을 넣은 것을 기관 문서로 쓴다 — 블록 id 와 그래프는 프레임 그대로(새로 넣은 그림·캡션만 그래프에 없다).
양식의 그 절 = 「□ 필요성 › o › - › ⋅」 이고 마지막 「⋅」 줄 문단이 작성요령 표를 품는다(문단 + 제 표). 앞 절 「□ 배경」 도 같은 꼴(표 없음)."""
import io

import pytest
from lxml import etree
from PIL import Image

import merge_data as M
from app import hwpx_doc as H
from app import merge_gather_drop as D
from app.outline_edit import body_of, prefix_of

CAPTION = "표 1 ★끌어넣기 캡션"
WROTE = (" 기관이 쓴 필요성", " 세부 내용", " 표를 품은 줄")   # 「o」·「-」·「⋅」 줄 뒤에 붙인 글


def _fresh(side):
    doc = M.fresh(side)
    doc.blocks()   # 블록 id 는 읽을 때 매겨진다 — 읽어 두어야 그래프의 id 와 같다
    return doc


def _node(g, letter, text="", parent=None, role=None):
    """본문 노드 하나 — 레터 앞부분 · 글 · 부모 · 역할로."""
    return next(n for n in g["nodes"] if n["flow"] == "body" and (n["letter"] or "").startswith(letter) and text in (n["text"] or "")
                and (parent is None or n["parent"] == parent) and (role is None or n["role"] == role))


def _chain(g, top):
    """top 아래 외줄로 내려가는 줄들의 문단 id(「□ › o › - › ⋅」 의 o·-·⋅)."""
    out, cur = [], top
    while (kid := next((n for n in g["nodes"] if n["parent"] == cur), None)) is not None:
        out.append(kid["para"])
        cur = kid["id"]
    return out


def _seq(doc):
    return [b["id"] for b in doc.blocks() if not b.get("captionOf")]


def _caption(doc, table_id, text):
    """표에 캡션 한 줄(양식에는 캡션이 없다) → 캡션 문단의 블록 id."""
    tbl = doc._ids[table_id]
    host = doc._host(tbl)
    cap = etree.Element(H.CAPTION, {"side": "TOP", "fullSz": "0", "width": "8504", "gap": "850", "lastWidth": "0"})
    sub = etree.SubElement(cap, H.SUBLIST, {"id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK", "vertAlign": "TOP", "linkListIDRef": "0",
                                            "linkListNextIDRef": "0", "textWidth": "0", "textHeight": "0", "hasTextRef": "0", "hasNumRef": "0"})
    p = etree.SubElement(sub, H.P, dict(host.attrib))
    etree.SubElement(etree.SubElement(p, H.RUN, {"charPrIDRef": doc._char_id(host)}), H.T).text = text
    tbl.find(H._p("outMargin")).addnext(cap)
    doc._touch(tbl)
    return next(b["id"] for b in doc.blocks() if b.get("captionOf") == table_id)


@pytest.fixture(scope="module")
def S():
    """{base, g, to(취합본 쪽 — 안 고침), part(기관 문서 쪽 — 여기서만 고침), 그 절의 블록 id 들}."""
    base = M.small()["from"]
    g = base["graph"]
    back, need = _node(g, "□", "배경"), _node(g, "□", "필요성")
    o, dash, dot = _chain(g, need["id"])
    part = _fresh(base)
    for pid, add in zip((o, dash, dot), WROTE):
        part.set_text(pid, part._text(part._ids[pid]).rstrip() + add)
    buf = io.BytesIO()
    Image.new("RGB", (2400, 300), (30, 90, 160)).save(buf, "PNG")
    pic = part.insert_image(dash, buf.getvalue(), "png", width_mm=300)   # 본문보다 넓은 그림 — 넣은 뒤 본문 폭으로 줄어야 한다
    ids = _seq(part)
    table = ids[ids.index(dot) + 1]
    assert part._host(part._ids[table]) is part._ids[dot]   # 「⋅」 줄 문단이 표를 품는다
    cap = _caption(part, table, CAPTION)
    return {"base": base, "g": g, "to": {"doc": _fresh(base), "graph": g}, "part": {"doc": part, "graph": g},
            "sec": _node(g, "1-2.")["para"], "back": back["para"], "back_kids": _chain(g, back["id"]), "need": need["para"],
            "o": o, "dash": dash, "dot": dot, "pic": pic, "table": table, "cap": cap}


def test_range_is_the_graph_subtree_not_a_level_number(S):
    g, to, part = S["g"], S["to"], S["part"]
    ids = _seq(part["doc"])
    cut = lambda a, b: ids[ids.index(a):ids.index(b)]  # noqa: E731
    src = lambda s: D.plan(to, part, s, S["back"])["src"]  # noqa: E731
    # 뒤 형제(□ 필요성)는 안 오고 더 깊은 줄(o › - › ⋅)은 온다
    got = src(S["back"])
    assert got == cut(S["back"], S["need"]) and len(S["back_kids"]) == 3 and set(S["back_kids"]) < set(got)
    # 윗 절 「1-2.」 = 두 □ 절 · 그림 · 문단에 딸린 표까지, 다음 장 「2.」 앞에서 멈춘다(캡션은 표에 딸려 가므로 목록에 없다)
    got = src(S["sec"])
    assert got == cut(S["sec"], _node(g, "2.", "목표 및 내용")["para"]) and {S["back"], S["need"], S["pic"], S["dot"], S["table"]} < set(got) and S["cap"] not in got
    # 서브 템플릿: 「(1)-1 …」((N)›o›- 의 L1) 아래 구분 라벨([단계]… 의 L1)과 그 아래 「o」 — 레벨 숫자는 같지만 그래프 자손이라 온다. 형제 「(2)」 앞에서 멈춘다
    step = _node(g, "(1)", "단계별 목표")
    label = _node(g, "[", parent=step["id"], role="label")
    assert label["template"] != step["template"] and label["level"] <= step["level"]
    got = src(step["para"])
    assert got == cut(step["para"], _node(g, "(2)", "정량적 목표")["para"]) and {label["para"], *_chain(g, label["id"])} < set(got)
    # 주 사슬 「2-1.」(L2) 아래 서브 템플릿 「(1)」(L1) — 숫자로는 윗 레벨이지만 멈추지 않는다
    fin = _node(g, "2-1.")
    got = src(fin["para"])
    assert got == cut(fin["para"], _node(g, "2-2.")["para"])
    assert any(n["para"] in got and n["parent"] == fin["id"] and n["level"] and n["template"] != fin["template"] and n["level"] < fin["level"] for n in g["nodes"])
    # 구분 라벨 절 = 그 라벨부터 다음 형제 라벨 앞까지
    lead = _node(g, "[주관연구개발기관", role="label")
    nxt = next(n for n in g["nodes"] if n["parent"] == lead["parent"] and n["role"] == "label" and n["id"] != lead["id"])
    assert src(lead["para"]) == cut(lead["para"], nxt["para"])


def test_plan_counts_and_single_block_fallback(S):
    to, part = S["to"], S["part"]
    ids = _seq(part["doc"])
    blank = ids[ids.index(S["o"]) + 1]
    p = D.plan(to, part, S["need"], S["back"])
    assert p["srcTop"] == S["need"] and p["src"] == [S["need"], S["o"], blank, S["dash"], S["pic"], S["dot"], S["table"]]   # 문서 순 — 문단에 딸린 표는 그 문단 다음에 한 번
    r = p["range"]
    assert (r["title"], r["blocks"], r["paragraphs"], r["tables"], r["pictures"], r["lines"], r["single"]) == ("□ 필요성", 7, 5, 1, 1, 4, False)
    assert p["dropped"] == [] and len(p["hash"]) == 16 and p["hash"] != D.plan(to, part, S["back"], S["back"])["hash"]
    for one in (blank, S["table"]):   # 제목 줄(그래프 노드)이 아닌 블록 = 그 블록 하나만
        p = D.plan(to, part, one, S["back"])
        assert p["src"] == [one] and p["range"]["single"] and p["range"]["blocks"] == 1
    p = D.plan({"doc": to["doc"]}, {"doc": part["doc"]}, S["need"], S["back"])   # 그래프가 없으면 블록 하나 · 틀 맞춤 없음
    assert p["src"] == [S["need"]] and p["range"]["single"] and p["owner"] == {"id": None, "text": ""} and p["convert"] is None


def test_cells_and_captions_are_refused(S):
    g, to, part = S["g"], S["to"], S["part"]
    tbl = next(b for b in to["doc"].blocks() if b["type"] == "table" and any(c["blocks"] for c in b["cells"]))
    cell = next(c for c in tbl["cells"] if c["blocks"])
    line = next(n["para"] for n in g["nodes"] if n["flow"].startswith("cell:"))   # 표 칸 안 개요 줄(그래프 노드여도 안 됨)
    for inside in (cell["id"], cell["blocks"][0]["id"], line):
        with pytest.raises(D.DropError, match="표 칸 안에는 놓을 수 없습니다"):
            D.plan(to, part, S["need"], inside)
        with pytest.raises(D.DropError, match="표 칸 안의 줄은 끌 수 없습니다"):
            D.plan(to, part, inside, S["back"])
    with pytest.raises(D.DropError, match="취합본에 없습니다"):
        D.plan(to, part, S["need"], "없는 id")
    with pytest.raises(D.DropError, match="기관 문서에 없습니다"):
        D.plan(to, part, "없는 id", S["back"])
    with pytest.raises(D.DropError, match="캡션"):
        D.plan(to, part, S["cap"], S["back"])
    assert issubclass(D.DropError, ValueError)   # server._transact 가 400 으로 돌려준다


def test_drop_lands_after_the_whole_host_paragraph(S):
    g, base, part = S["g"], S["base"], S["part"]
    p = D.plan(S["to"], part, S["need"], S["dot"])   # 「⋅」 줄 문단이 표를 품는다 → 그 표 뒤(문단과 제 표 사이에 끼우지 않는다)
    assert (p["after"]["id"], p["after"]["given"]) == (S["table"], S["dot"]) and p["after"]["text"].startswith("표 ")
    assert p["owner"]["id"] == S["need"]   # 그 자리까지의 마지막 줄들(⋅ · - · o)은 글 없는 글머리 줄 — 그 위 「□ 필요성」
    assert D.plan(part, S["to"], S["back"], S["cap"])["after"]["id"] == S["table"]   # 캡션 위에 놓음 = 그 표 뒤(기관 문서 쪽을 놓는 문서로 — 계획만)
    doc = _fresh(base)
    res = D.apply(doc, part["doc"], D.plan({"doc": doc, "graph": g}, part, S["need"], S["dot"]), g, g, convert=False)
    seq = _seq(doc)
    assert seq[seq.index(S["table"]) + 1] == res["ids"][0] and seq[seq.index(S["dot"]) + 1] == S["table"]


def test_plan_changes_neither_document(S):
    to, part = S["to"], S["part"]
    before = to["doc"].save(), part["doc"].save()
    D.plan(to, part, S["sec"], S["back"])
    D.plan(to, part, S["need"], S["dot"])
    assert (to["doc"].save(), part["doc"].save()) == before and before[0] == S["base"]["bytes"]


def test_apply_copies_paragraphs_table_and_picture_in_order_once(S):
    g, part = S["g"], S["part"]["doc"]
    doc = _fresh(S["base"])
    after = S["back_kids"][-1]   # 취합본 「□ 배경」 절의 마지막 줄
    pl = D.plan({"doc": doc, "graph": g}, S["part"], S["need"], after)
    was, tables = part.save(), sum(b["type"] == "table" for b in doc.blocks())
    res = D.apply(doc, part, pl, g, g, convert=False)
    assert part.save() == was   # 기관 문서(원본)는 그대로
    blocks, seq = doc.blocks(), _seq(doc)
    by, src = {b["id"]: b for b in blocks}, {b["id"]: b for b in part.blocks()}
    k = seq.index(after) + 1
    assert seq[k:k + 7] == res["ids"] and res["blocks"] == 7   # 놓은 자리 바로 뒤에, 기관 문서 차례로
    assert [by[i]["type"] for i in res["ids"]] == [src[s]["type"] for s in pl["src"]] == ["paragraph"] * 4 + ["image", "paragraph", "table"]
    assert [by[i].get("text") for i in res["ids"]] == [src[s].get("text") for s in pl["src"]]   # 틀 맞춤을 끄면 기관 문서 모양 그대로
    assert (res["converted"], res["kept"], res["dropped"]) == (0, {}, pl["dropped"])
    new_pic, new_dot, new_tbl = res["ids"][4:]
    assert not doc._has_object(doc._ids[new_dot]) and sum(b["type"] == "table" for b in blocks) == tables + 1   # 문단 사본에는 표가 없다 — 표는 제 블록으로 한 번
    assert [b["captionOf"] for b in blocks if b.get("text") == CAPTION] == [new_tbl]   # 캡션은 표에 딸려 한 번
    assert res["fitted"] == 1 and by[new_pic]["widthMm"] < src[S["pic"]]["widthMm"] == 300   # 넓은 그림은 본문 폭으로
    again = H.HwpxDoc(doc.save()).blocks()   # 저장한 결과가 다시 열린다
    assert [sum(w.strip() in (b.get("text") or "") for b in again) for w in WROTE] == [1, 1, 1] and sum(b.get("text") == CAPTION for b in again) == 1


def test_convert_follows_the_owner_or_leaves_as_written(S):
    g, base, part = S["g"], S["base"], S["part"]
    text = lambda d, i: d._text(d._ids[i])  # noqa: E731
    # 「□ 배경」 줄 바로 뒤 → 품은 제목 줄 = 그 줄. 복사한 개요 줄은 그 자식으로: □ → o, o → -, - → ⋅, ⋅ 는 받을 레벨이 없어 그대로
    doc = _fresh(base)
    pl = D.plan({"doc": doc, "graph": g}, part, S["need"], S["back"])
    cv = pl["convert"]
    letters = [text(doc, i).split()[0] for i in S["back_kids"]]   # 취합본 그 자리의 실제 레터(o · - · ⋅)
    assert pl["owner"] == {"id": S["back"], "text": "□ 배경"} and cv["converted"] == 3 and cv["kept"] == {"body": 2, "table": 1, "tooDeep": 1}
    assert [(r["src"], r["letter"], r["why"]) for r in cv["rows"]] == [(S["need"], letters[0], None), (S["o"], letters[1], None), (S["dash"], letters[2], None), (S["dot"], None, "tooDeep")]
    assert cv["labels"] == {k: D.WHY[k] for k in cv["kept"]} and cv["anchor"][1] == 1 and cv["more"] == 0   # 그대로 두는 까닭은 화면에 보일 글과 함께
    res = D.apply(doc, part["doc"], pl, g, g)   # convert 기본 켬
    assert (res["converted"], res["kept"], res["labels"]) == (cv["converted"], cv["kept"], cv["labels"])
    new = dict(zip(pl["src"], res["ids"]))
    for r in cv["rows"]:
        now, was = text(doc, new[r["src"]]), text(part["doc"], r["src"])
        if r["why"]:
            assert now == was
        else:   # 레터는 취합본 것, 글은 기관 문서 것
            assert prefix_of(now, r["letter"])[1] == r["letter"] != r["was"] and body_of(now, r["letter"]) == body_of(was, r["was"])
    assert doc.para_attrs(new[S["need"]]) == doc.para_attrs(S["back_kids"][0])   # 문단 모양 = 같은 자리의 취합본 줄(「□ 배경」 의 첫 o)
    # 같은 계획이라도 끄면 그대로
    off = _fresh(base)
    r2 = D.apply(off, part["doc"], D.plan({"doc": off, "graph": g}, part, S["need"], S["back"]), g, g, convert=False)
    assert r2["converted"] == 0 and [text(off, i) for i in r2["ids"][:4]] == [text(part["doc"], s) for s in pl["src"][:4]]
    # 절 끝의 글 없는 글머리 줄(자리표시) 뒤에 놓아도 품은 제목 줄은 그 위 「□ 배경」
    assert D.plan(S["to"], part, S["need"], S["back_kids"][-1])["owner"]["id"] == S["back"]
    # 「1-2.」 줄 바로 뒤: 그 아래는 서브 템플릿(□ …)이 붙는 자리 — merge_convert 는 주 사슬 다음 레벨(가.)로 보내려 하므로 바꾸지 않고 까닭(branch)만 센다
    doc = _fresh(base)
    pl = D.plan({"doc": doc, "graph": g}, part, S["need"], S["sec"])
    assert pl["owner"]["id"] == S["sec"] and pl["convert"]["converted"] == 0 and pl["convert"]["kept"]["branch"] == 2
    res = D.apply(doc, part["doc"], pl, g, g)
    assert res["converted"] == 0 and res["kept"] == pl["convert"]["kept"] and [text(doc, i) for i in res["ids"][:4]] == [text(part["doc"], s) for s in pl["src"][:4]]
    # 첫 제목 줄 앞(표지 표 뒤): 품은 제목 줄이 없다 → 틀 맞춤 없이 그대로
    doc = _fresh(base)
    pl = D.plan({"doc": doc, "graph": g}, part, S["need"], doc.blocks()[0]["id"])
    assert pl["owner"] == {"id": None, "text": ""} and pl["convert"] is None
    res = D.apply(doc, part["doc"], pl, g, g)
    assert (res["converted"], res["kept"], res["blocks"]) == (0, {}, 7) and text(doc, res["ids"][0]) == text(part["doc"], S["need"])


def test_apply_refuses_a_stale_plan_before_touching_the_document(S):
    g, base = S["g"], S["base"]
    doc, src = _fresh(base), _fresh(base)
    pl = D.plan({"doc": doc, "graph": g}, {"doc": src, "graph": g}, S["need"], S["back"])
    src.set_text(S["o"], "  o 계획 뒤에 고친 글")   # 범위 안의 글이 바뀜
    with pytest.raises(D.DropError, match="다시 끌어"):
        D.apply(doc, src, pl, g, g)
    gone = _fresh(base)
    gone.delete_blocks(S["dash"], S["dash"])   # 범위 안의 블록이 없어짐
    with pytest.raises(D.DropError, match="다시 끌어"):
        D.apply(doc, gone, pl, g, g)
    with pytest.raises(D.DropError, match="다시 끌어"):   # 분석 결과(그래프)가 달라짐 — 복사 범위가 달라진다
        D.apply(doc, _fresh(base), pl, g, None)
    assert doc.save() == base["bytes"]   # 취합본은 건드리지 않았다
    doc.delete_blocks(S["back"], S["back"])   # 놓을 자리가 없어짐
    with pytest.raises(D.DropError, match="놓을 자리가 취합본에 없습니다"):
        D.apply(doc, _fresh(base), pl, g, g)


def test_overflow_level_is_reported_and_follows_the_choice(S):
    """넘친 개요 레벨(spec_병합 ② §5-5): 「□ 배경」 아래로 끌어 넣으면 □ → o · o → - · - → ⋅ 까지는 틀 안이고 마지막 「⋅」 줄은 틀에 없는 레벨 — 사례로 보이고, 선택(to["over"])이 있으면 그대로 입힌다."""
    g, base, part = S["g"], S["base"], S["part"]
    text = lambda d, i: d._text(d._ids[i])  # noqa: E731
    doc = _fresh(base)
    pl = D.plan({"doc": doc, "graph": g}, part, S["need"], S["back"])
    ov = pl["convert"]["over"]
    assert ov["lines"] == 1 and ov["to"][1] == 4 and ov["key"] == f"{ov['to'][0]}<{ov['tail'][0]}" and pl["convert"]["rows"][-1]["over"] == 1 and pl["convert"]["rows"][-1]["why"] == "tooDeep"
    res = D.apply(doc, part["doc"], pl, g, g)   # 선택이 없으면 그대로 두고, 넣은 줄을 적어 둔다
    (line,) = res["over"]["lines"]
    new = dict(zip(pl["src"], res["ids"]))
    assert res["over"]["key"] == ov["key"] and (line["id"], line["over"], line["letter"]) == (new[S["dot"]], 1, line["was"]) and text(doc, new[S["dot"]]) == text(part["doc"], S["dot"])
    off = _fresh(base)
    assert D.apply(off, part["doc"], D.plan({"doc": off, "graph": g}, part, S["need"], S["back"]), g, g, convert=False)["over"] is None   # 틀 맞춤을 끄면 기록도 없다

    over = {ov["key"]: [{"like": None, "letter": "▪", "lead": None, "numbered": False}]}
    doc = _fresh(base)
    pl = D.plan({"doc": doc, "graph": g, "over": over}, part, S["need"], S["back"])
    cv = pl["convert"]
    assert cv["converted"] == 4 and cv["kept"] == {"body": 2, "table": 1} and (cv["rows"][-1]["src"], cv["rows"][-1]["letter"], cv["rows"][-1]["why"], cv["rows"][-1]["over"]) == (S["dot"], "▪", None, 1)
    res = D.apply(doc, part["doc"], pl, g, g, over=over)
    new = dict(zip(pl["src"], res["ids"]))
    assert res["converted"] == 4 and "tooDeep" not in res["kept"] and text(doc, new[S["dot"]]).lstrip().startswith("▪") and [x["letter"] for x in res["over"]["lines"]] == ["▪"]
