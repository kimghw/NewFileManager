"""취합 자동 넣기의 틀 맞춤(spec_취합 ② §4-4 「틀 맞춤」 · app/merge_gather_fit.py · merge_convert.plan(sibling=True)) — 2026-11-12 사용자
"A(취합문서), B(취합대상문서) 인 경우 A에 맞추고, 다만 depth 나 레터 형식이 다른 경우 A에 맞추고 향후 다른 서식으로 변경할 수 있게 한다":
기관 문서 줄의 레터 꼴·개요 깊이가 취합본 틀과 다르면 그 자리의 틀로 바뀌어 들어가고, 틀 안에서 쓴 줄·레터 없는 줄은 그대로이며, 넣은 줄의 원래 꼴 ↔ 맞춘 자리가 반영 기록에 남는다.
자료 = gather_data(빈 양식 + 기관 셋 = 기준본) + 기관 문서의 2단계 그래프(merge_data 의 캐시 — 처음 한 번만 분석한다)."""
import pytest

import gather_data as D
import merge_data as M
from app import merge_gather as G

ALL = {"orgs": [D.LEAD, D.J1, D.J2], "common": True}
GOAL, SUB, BODY = "가나대 개발 목표", "가나대 세부 목표", "가나대가 쓴 설명 글"
BACK, PLAN, FINAL = "가나대가 쓴 배경", "추진 전략을 네모로 씀", "최종 목표를 빈 줄에 씀"


def _text(doc, bid):
    return next(b["text"] for b in D.top(doc) if b["id"] == bid)


def _slot(d, after, letter, far=12):
    """after 뒤에서 처음 만나는 「letter」 뿐인 자리표시 줄의 id."""
    return next(i for i in (D.nxt(d, after, k) for k in range(1, far)) if _text(d, i).strip() == letter)


def _edit(d):
    o = _slot(d, D.para(d, "[공동연구개발기관1(가나대)]", 0), "o")    # 기관 자리의 자리표시 줄 「  o 」 — 취합본 틀 [기관]›o›- 의 L2
    d.set_text(o, f"■ {GOAL}")                                         # 레터 꼴이 다름(■)
    d.insert_after(o, [{"kind": "paragraph", "text": f"  o {SUB}"},    # 깊이가 다름(■ 아래 o — 취합본 틀로는 o 아래 -)
                       {"kind": "paragraph", "text": BODY}])           # 레터 없는 본문 줄
    d.set_text(_slot(d, D.para(d, "□ 배경"), "o"), f"  o {BACK}")      # 틀 안에서 쓴 줄(공통 자리 — □›o 의 o)
    d.set_text(_slot(d, D.para(d, "3-1. 기술개발 추진방법·전략"), "o"), f"□ {PLAN}")   # 가지 템플릿의 뿌리 자리(3-1. 아래 「o›-」 의 o)에 □ 로 씀
    d.set_text(D.nxt(d, D.para(d, "(1) 최종목표", 0, start=True)), f"  o {FINAL}")   # 자리표시 줄 「□」 앞의 빈 줄에 씀 — 끼어든 내용(added) · 그 제목 아래는 서브 템플릿이 붙는 자리


def _part(graph=True):
    p = D.part(_edit, "fit")
    if graph:
        p["graph"], p["tables"] = M._cached("gather-fit", p["bytes"], p["doc"], "fit.hwpx")
    return p


@pytest.fixture(scope="module")
def S():
    frame, part, to = D.base()["frame"], _part(), D.master()
    before = D.texts(to["doc"])
    items = G.judge(G.links(frame, part)["items"], frame, to, ALL, None)
    plan = G.plan(items, frame, to, part)
    assert D.texts(to["doc"]) == before   # 계획은 문서를 안 바꾼다
    return {"frame": frame, "part": part, "to": to, "plan": plan, "res": G.apply(to["doc"], part["doc"], plan)}


def _item(plan, text):
    return next(it for it in plan["items"] if text in it["text"])


def test_plan_fits_only_the_lines_whose_letter_or_depth_differs(S):
    org = _item(S["plan"], GOAL)
    cv = org["convert"]
    assert org["kind"] == "filled" and [(r["was"], r["letter"]) for r in cv["rows"]] == [("■", "o"), ("o", "-")]   # ■ → 그 자리의 o · 그 아래 o → -
    assert cv["rows"][0]["to"][1] == 2 and cv["rows"][1]["to"][1] == 3 and cv["rows"][0]["to"][0] == cv["rows"][1]["to"][0]   # 취합본 [기관] 템플릿의 L2·L3
    assert (cv["converted"], cv["same"], cv["kept"]) == (2, 0, {}) and org["counts"]["converted"] == 2 and org["counts"]["paragraphs"] == 3   # 레터 없는 본문 줄은 세지 않는다
    back = _item(S["plan"], BACK)["convert"]
    assert (back["converted"], back["same"], back["kept"]) == (0, 1, {})   # 틀 안에서 쓴 줄은 건드리지 않는다
    root = _item(S["plan"], PLAN)["convert"]
    assert [(r["was"], r["letter"], r["to"][1]) for r in root["rows"]] == [("□", "o", 1)]   # 가지 템플릿의 뿌리 자리 — 자리표시 줄이 가리키는 (템플릿, 레벨)로
    ops = {op["key"]: op for op in S["plan"]["ops"]}
    assert ops[org["key"]]["convert"]["mode"] == "slot" and ops[_item(S["plan"], PLAN)["key"]]["convert"]["mode"] == "slot"
    added = _item(S["plan"], FINAL)
    assert added["kind"] == "added" and ops[added["key"]]["convert"]["mode"] == "owner"
    assert added["convert"]["converted"] == 0 and added["convert"]["kept"] == {"branch": 1} and "서브 템플릿" in added["convert"]["labels"]["branch"]   # 못 맞추는 자리는 쓴 대로 두고 까닭을 보인다


def test_apply_writes_the_frame_shape_keeps_the_rest_and_records_the_original(S):
    to, res = S["to"], S["res"]
    texts = D.texts(to["doc"])
    for want in (f"o {GOAL}", f"- {SUB}", BODY, f"o {BACK}", f"o {PLAN}", f"o {FINAL}"):
        assert texts.count(want) == 1, want
    assert not [t for t in texts if "■" in t and GOAL in t] and f"□ {PLAN}" not in texts
    i = texts.index(f"o {GOAL}")
    assert texts[i + 1:i + 3] == [f"- {SUB}", BODY]   # 차례는 기관 문서 그대로
    assert res["counts"] == {**res["counts"], "hunks": 4, "paragraphs": 6, "converted": 3, "kept": 1, "skipped": 0}
    rec = next(r for r in res["applied"].values() if any(GOAL in _text(to["doc"], x) for x in r["ids"]))
    rows = rec["convert"]["rows"]   # 넣은 줄의 원래 꼴 ↔ 맞춘 자리 — 나중에 다른 서식으로 바꿀 근거
    assert rec["convert"]["mode"] == "slot" and [(r["was"], r["letter"]) for r in rows] == [("■", "o"), ("o", "-")]
    assert [_text(to["doc"], r["id"]).strip() for r in rows] == [f"o {GOAL}", f"- {SUB}"] and all(r["id"] in rec["ids"] and r["from"] and r["to"] for r in rows)
    assert [_text(S["part"]["doc"], r["src"]).strip() for r in rows] == [f"■ {GOAL}", f"o {SUB}"]   # 기관 문서(원본)는 그대로
    slot = _text(D.master()["doc"], _slot(D.master()["doc"], D.para(D.master()["doc"], "[공동연구개발기관1(가나대)]", 0), "o"))
    lead = slot[:len(slot) - len(slot.lstrip())]
    assert _text(to["doc"], rows[0]["id"]).startswith(lead + "o")   # 앞 공백·레터는 취합본 그 자리의 것


def test_replan_is_empty_and_without_the_record_it_is_an_overlap_not_a_second_copy(S):
    to = D.side(S["to"]["doc"])
    links = G.links(S["frame"], S["part"])["items"]
    again = G.judge(links, S["frame"], to, ALL, S["res"]["applied"])
    assert {h["status"] for h in again} == {"same"} and G.plan(again, S["frame"], to, S["part"])["todo"] == 0
    lost = G.judge(links, S["frame"], to, ALL, None)   # 넣은 기록이 없으면 — 레터가 바뀐 자리는 「같음」 을 못 보지만 다시 넣지도 않는다(겹침)
    by = {h["text"]: h["status"] for h in lost}
    assert next(v for k, v in by.items() if GOAL in k) == "overlap" and next(v for k, v in by.items() if BACK in k) == "same"
    assert G.plan(lost, S["frame"], to, S["part"])["todo"] == 0


def test_without_the_part_graph_lines_go_in_as_written():
    frame, part, to = D.base()["frame"], _part(graph=False), D.master()
    plan = G.plan(G.judge(G.links(frame, part)["items"], frame, to, ALL, None), frame, to, part)
    assert all("convert" not in it and "converted" not in it["counts"] for it in plan["items"]) and all("convert" not in op for op in plan["ops"])
    res = G.apply(to["doc"], part["doc"], plan)
    assert f"■ {GOAL}" in D.texts(to["doc"]) and res["counts"]["converted"] == 0 and all("convert" not in r for r in res["applied"].values())


# ---- 넘친 개요 레벨(spec_병합 ② §5-5): 취합본 틀보다 깊게 쓴 줄 = 사례 · 사람의 선택(to["over"]) · 반영 기록 --------------------------------

OGOAL, OSUB, ODEEP = "가나대 넘침 목표", "가나대 넘침 세부", "가나대 넘침 더 깊은 줄"


def _edit_over(d):
    o = _slot(d, D.para(d, "[공동연구개발기관1(가나대)]", 0), "o")   # 취합본 틀 [기관]›o›- 의 L2 자리 — o · - 까지는 틀 안, 그 아래 「·」 는 틀에 없는 레벨
    d.set_text(o, f"  o {OGOAL}")
    d.insert_after(o, [{"kind": "paragraph", "text": f"    - {OSUB}"}, {"kind": "paragraph", "text": f"      · {ODEEP}"}])


def test_overflow_level_is_reported_recorded_and_follows_the_choice():
    frame, part = D.base()["frame"], D.part(_edit_over, "fit-over")
    part["graph"], part["tables"] = M._cached("gather-fit-over", part["bytes"], part["doc"], "fit-over.hwpx")

    def run(over=None):
        to = D.master() if over is None else {**D.master(), "over": over}
        plan = G.plan(G.judge(G.links(frame, part)["items"], frame, to, ALL, None), frame, to, part)
        return to, plan, _item(plan, OGOAL)["convert"]

    to, plan, cv = run()   # 선택이 없으면 전처럼 쓴 대로 — 사례로 보이고 넣은 줄이 기록에 남는다
    ov = cv["over"]
    assert (ov["lines"], cv["kept"], cv["converted"]) == (1, {"tooDeep": 1}, 0) and ov["to"][1] == 3 and ov["key"].startswith(f"{ov['to'][0]}<") and [x["n"] for x in ov["levels"]][:1] == [4]
    res = G.apply(to["doc"], part["doc"], plan)
    assert f"· {ODEEP}" in D.texts(to["doc"]) and res["counts"]["kept"] == 1
    rec = next(r["convert"]["over"] for r in res["applied"].values() if (r.get("convert") or {}).get("over"))
    (line,) = rec["lines"]
    assert rec["key"] == ov["key"] and rec["to"] == ov["to"] and (line["over"], line["was"], line["letter"]) == (1, "·", "·") and ODEEP in _text(to["doc"], line["id"]) and line["orig"]["prefix"].strip() == "·"

    to, plan, cv = run({ov["key"]: [{"like": None, "letter": "▪", "lead": None, "numbered": False}]})   # 사람이 그 레벨의 레터를 정함 — 제 모양은 그대로
    assert cv["kept"] == {} and [(r["was"], r["letter"], r.get("over")) for r in cv["rows"]] == [("·", "▪", 1)] and cv["over"]["key"] == ov["key"]
    res = G.apply(to["doc"], part["doc"], plan)
    texts = D.texts(to["doc"])
    assert f"▪ {ODEEP}" in texts and f"· {ODEEP}" not in texts and f"o {OGOAL}" in texts and f"- {OSUB}" in texts and res["counts"]["converted"] == 1
    rec = next(r["convert"]["over"] for r in res["applied"].values() if (r.get("convert") or {}).get("over"))
    assert [(x["was"], x["letter"]) for x in rec["lines"]] == [("·", "▪")]
