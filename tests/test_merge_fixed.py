"""고정 자리 — 같은 이름 자리(spec_병합 ② §5-1·§5-2 · app/merge_fixed.py): 구분 기준이 안 걸린 표지 칸·칸 안 라벨의 내용(그림 포함)을 원본에서 목적으로.
저장소 안 자료만: 값을 반영한 계획서 양식의 표지 칸 몇 곳에 글을 쓰고 요약문 「[최종목표]」 아래에 (칸보다 넓은) 그림·글을 넣은 것(원본) ↔ 같은 값으로 반영한 연차보고서 서식(merge_data.small 의 목적).
규칙의 부정 시험(사람이 쓴 짧은 글 · 이미 한 체크 · 뒤바뀐 열 차례 · 책임자가 다른 「성명」)은 2026-11-12 astra 검토에서 온 것(artifacts/frame_map_astra_2026-11-12/)."""
import io
import re

import pytest
from PIL import Image

import merge_data as M
from app import hwpx_struct
from app import merge_api
from app import merge_fixed as X
from app.division_profiles import _structure as structure
from app.hwpx_doc import HwpxDoc

WRITE = {"중앙행정기관명": "산업통상부", "전문기관명": "한국산업기술기획평가원", "공고번호": "제2026-134호"}   # 머리 칸 글(빈칸·각주 번호 뺌) → 그 오른쪽 칸에 쓸 글
BODY = "★고정자리 최종목표 글"


def _png(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 90, 160)).save(buf, "PNG")
    return buf.getvalue()


def _bare(t):
    return re.sub(r"\d+\)$", "", re.sub(r"\s+", "", t or ""))   # 빈칸과 끝의 각주 번호(「공고번호6)」)를 뗀 글


def _right_of(doc, head):
    """첫 표(표지)에서 글이 head 인 머리 칸의 바로 오른쪽 칸 id."""
    tb = next(b for b in structure.iter_blocks(doc.blocks()) if b.get("type") == "table" and any(_bare(c.get("text")) == head for c in b["cells"]))
    h = next(c for c in tb["cells"] if _bare(c.get("text")) == head)
    return next(c["id"] for c in tb["cells"] if c["row"] <= h["row"] < c["row"] + c["rowSpan"] and c["col"] == h["col"] + h["colSpan"])


def _label(doc, text):
    return next(b["id"] for b in structure.iter_blocks(doc.blocks()) if b.get("type") == "paragraph" and _bare(b.get("text")) == text)


@pytest.fixture(scope="module")
def pair():
    """(values, 목적 쪽, 원본 쪽) — 원본 = 표지 칸 셋 + 주소(서식의 틀 「(우)」 뒤에 값) + 「[최종목표]」 아래 넓은 그림(300mm)과 글."""
    from app.division_profiles import rnd
    from app.division_profiles.rnd import core
    d = M.small()
    plan = HwpxDoc(M.PLAN_FORM.read_bytes())
    assert not core.apply(plan, d["values"], levels_of=rnd.levels_of)["errors"]
    for head, text in WRITE.items():
        plan.set_text(_right_of(plan, head), text)
    addr = _right_of(plan, "주소")
    was = next(b for b in structure.iter_blocks(plan.blocks()) if b["id"] == addr).get("text") or ""
    plan.set_text(addr, (was.strip() or "(우)") + "06178 서울특별시 강남구 테헤란로 84길 12")
    goal = _label(plan, "[최종목표]")
    plan.insert_after(goal, [{"kind": "paragraph", "text": BODY}])
    plan.insert_image(goal, _png(2400, 300), "png", width_mm=300)   # 어느 칸보다도 넓은 그림 — 목적 칸 폭으로 줄어야 한다
    frm = M._side("fixed-plan", plan, M.PLAN_FORM.name)
    return d["values"], {**d["to"], "values": d["values"]}, {**frm, "values": d["values"]}


def _fresh(side):
    doc = M.fresh(side)
    doc.blocks()   # 블록 id 는 읽을 때 매겨진다
    return doc


def _texts(doc):
    return {b["id"]: b.get("text") or "" for b in structure.iter_blocks(doc.blocks())}


def test_cells_by_header_path_form_label_picture_fit_table_flow_and_idempotent(pair):
    values, to, frm = pair
    pl = X.plan(to, frm)
    assert any(t["status"] == "paired" and t["cells"] >= len(WRITE) for t in pl["tables"]), pl["tables"]
    by_text = {c["text"]: c for c in pl["cells"]}
    assert all(t in by_text and by_text[t]["mode"] == "empty" for t in WRITE.values()), sorted(by_text)   # 머리 경로가 같은 빈 칸
    addr = next(c for c in pl["cells"] if "테헤란로" in c["text"])
    assert addr["mode"] == "form" and _bare(addr["was"]) and X._skeleton(addr["was"], addr["text"])   # 서식의 틀 글 「(우)」 → 원본 글로
    S = X._side(to)
    assert not {c["to"] for c in pl["cells"]} & S["cov"]   # 구분 기준 묶음의 칸은 안 건드린다(묶음 짝 몫)
    lab = next(r for r in pl["labels"] if _bare(r["title"]) == "[최종목표]")   # 칸 안 라벨 — 짝지은 칸끼리
    assert (lab["skip"], lab["pictures"], lab["paragraphs"]) == (None, 1, 1) and len(lab["placeholders"]) == 1, lab
    flow = [t for t in pl["tables"] if t["flow"]]   # 원본 요약문 표는 쪽을 넘어 나뉘는데 목적 표는 글자처럼 취급 + 나누지 않음
    assert flow and all(not to["doc"].table_flow(t["to"])["splits"] and frm["doc"].table_flow(t["from"])["splits"] for t in flow)
    assert pl["todo"] == len(pl["cells"]) + 1 + len(flow) and pl["counts"]["pictures"] == 1 and pl["counts"]["flow"] == len(flow)

    doc = _fresh(to)
    res = X.apply(doc, frm["doc"], pl)
    assert hwpx_struct.snapshot(frm["doc"])["bytes"] == frm["bytes"]   # 원본은 그대로
    assert res["filled"] == len(pl["cells"]) and res["labels"]["items"] == 1 and res["labels"]["placeholders"] == 1 and not res["skipped"]
    now = _texts(doc)
    assert all(now[c["to"]].strip() == c["text"].strip() for c in pl["cells"])
    cell = next(b for b in structure.iter_blocks(doc.blocks()) if any(x["id"] == lab["to"] for x in b.get("blocks") or ()))
    after = cell["blocks"][[x["id"] for x in cell["blocks"]].index(lab["to"]) + 1:][:2]
    assert sorted(x["type"] for x in after) == ["image", "paragraph"] and BODY in [x.get("text") for x in after]   # 라벨 바로 뒤에 그림 + 글
    img = next(x for x in after if x["type"] == "image")
    assert res["fitted"] == 1 and 20 < img["widthMm"] < 200 and abs(img["widthMm"] / img["heightMm"] - 8) < 0.1, img   # 300mm 그림이 칸 폭으로(비율 2400:300 그대로)
    assert not doc.fit_image(img["id"])   # 다시 맞출 것 없음
    assert lab["placeholders"][0] not in now   # 자리표시 「ㅇ」 줄은 지움
    assert res["flowed"] == len(flow) and all(doc.table_flow(t["to"])["splits"] for t in flow)   # 표가 쪽을 넘어 나뉘게

    again = X.plan({**to, "doc": doc}, frm, applied=res["applied"])   # 다시 계획 = 할 일 없음
    assert again["todo"] == 0 and next(r for r in again["labels"] if r["to"] == lab["to"])["skip"] == "applied"
    data = hwpx_struct.snapshot(doc)["bytes"]
    assert len(HwpxDoc(data).blocks()) == len(doc.blocks())   # 저장해 다시 열림


def test_written_cells_are_kept_even_when_a_prefix_of_the_source(pair):
    values, to, frm = pair
    base = X.plan(to, frm)
    a, b, c = (next(x for x in base["cells"] if x["text"] == t) for t in WRITE.values())
    doc = _fresh(to)
    doc.set_text(a["to"], "사람이 쓴 글")
    doc.set_text(c["to"], c["text"][:3])   # 원본 글의 앞부분 — 사람이 쓰다 만 글일 수 있다(뼈대로 보고 덮으면 안 된다)
    pl = X.plan({**to, "doc": doc}, frm)
    assert not {a["to"], c["to"]} & {x["to"] for x in pl["cells"]} and {s["to"] for s in pl["skipped"] if s["why"] == "occupied"} >= {a["to"], c["to"]}
    doc.set_text(b["to"], "계획 뒤에 쓴 글")   # 계획과 반영 사이에 사람이 씀
    res = X.apply(doc, frm["doc"], pl)
    now = _texts(doc)
    assert (now[a["to"]], now[b["to"]], now[c["to"]]) == ("사람이 쓴 글", "계획 뒤에 쓴 글", c["text"][:3]) and res["filled"] == len(pl["cells"]) - 1


def test_skeleton_and_check_rules():
    assert X._skeleton("(우)", "(우)06178 서울특별시") and not X._skeleton("(우)", "(우)")
    assert not X._skeleton("김민수", "김민수석") and not X._skeleton("서울", "서울특별시 강남구") and not X._skeleton("1", "13,800,000")   # 괄호 밖에 글자가 있으면 사람이 쓴 글일 수 있다
    assert not X._skeleton("징수[ ] 비징수[ ]", "징수[√]비징수[ ]")   # 체크 칸은 뼈대가 아니라 체크 규칙으로
    into = X._checked_into
    assert into("[ ] 일반형", "[ √ ] 일반형 (해당항목 체크)") == "[ √ ] 일반형"   # 체크만 — 원본의 안내 글은 안 딸려 온다
    assert into("일반[ ], 보안[ ]", "일반[√] 보안[ ]") == "일반[√], 보안[ ]" and into("기준[ ] 목표[ ] 해당없음[ ]", "기준[3] 목표[7] 해당없음[ ]") == "기준[3] 목표[7] 해당없음[ ]"
    assert into("원천기술형[ ] 혁신제품형[ ] 해당없음[ ]", "원천기술형[ ] 혁신제품형[√]") == "원천기술형[ ] 혁신제품형[√] 해당없음[ ]"   # 목적에만 있는 보기는 그대로
    assert into("[ ] 통합형(세부)", "[√] 통합형(세부)") == "[√] 통합형(세부)" and into("[ ] 통합형(총괄)", "[√] 통합형(세부)") is None   # 라벨의 괄호는 라벨의 일부
    assert into("R&D 샌드박스(일반)[ ] 해당없음[ ]", "R&D 자율성트랙(일반)[√] 해당없음[ ]") is None   # 체크한 라벨이 목적에 없음
    assert into("국내[ ] 해당없음[ ]", "국내외[√] 해당없음[ ]") is None   # 라벨은 글자가 모두 같아야(앞부분만 같은 것은 다른 보기)
    assert into("일반[√] 보안[ ]", "일반[ ] 보안[√]") is None and into("기준[5] 목표[8]", "기준[3] 목표[7]") is None   # 목적에 이미 체크·수 — 안 건드린다
    assert into("[ ] 일반형", "[ ] 일반형 (해당항목 체크)") is None and into("[최종목표]", "[최종목표] 글") is None   # 옮길 체크 없음 · 글이 든 대괄호는 체크 칸이 아님
    assert X._checked("일반[√], 보안[ ]") == {"일반": "[√]"} == X._checked("일반 [ √ ] 보안[ ]")


def test_cell_pair_rules():
    cell = lambda i, r, c: {"id": i, "row": r, "col": c}  # noqa: E731
    text = lambda i: ""  # noqa: E731
    ids = lambda pairs: sorted((a["id"], b["id"]) for a, b in pairs)  # noqa: E731
    k = (("국문핵심어",), ())
    t = [(cell("t1", 3, 1), k), (cell("t2", 3, 2), k), (cell("t3", 5, 1), (("실무책임자", "성명"), ()))]
    f = [(cell("f1", 3, 1), k), (cell("f2", 3, 3), k), (cell("f3", 5, 1), (("실무책임자", "성명"), ("직위",)))]
    pairs, amb = X._cell_pairs(t, f, text, text)
    assert ids(pairs) == [("t1", "f1"), ("t2", "f2"), ("t3", "f3")] and amb == 0   # 같은 경로 2↔2 = 자리대로 · ㉡ 이어진 행 머리 경로가 같고 한쪽에 열 머리 없음
    pairs, amb = X._cell_pairs(t, f[:1] + f[2:], text, text)   # 같은 경로 2↔1 = 모호(비워 둠)
    assert ids(pairs) == [("t3", "f3")] and amb == 2
    rp = ("성과",)   # 열 머리의 차례가 뒤바뀐 표 — 자리대로 이으면 현재 ← 목표 가 된다(astra 반례): 모호로 남긴다
    t = [(cell(f"t{i}", 2, i), (rp, (h,))) for i, h in enumerate(("현재", "현재", "목표", "목표"))]
    f = [(cell(f"f{i}", 2, i), (rp, (h,))) for i, h in enumerate(("목표", "목표", "현재", "현재"))]
    pairs, amb = X._cell_pairs(t, f, text, text)
    assert pairs == [] and amb == 4
    one = [(cell("t", 2, 9), (("중앙행정기관명", "세부사업명"), ("보안등급",)))], [(cell("f", 2, 7), (("사업명", "세부사업명"), ("보안등급",)))]
    assert ids(X._cell_pairs(*one, text, text, {"세부사업명": 1}, {"세부사업명": 1})[0]) == [("t", "f")]   # ㉠ 바로 붙은 머리가 두 표에서 하나뿐
    who = [(cell("t", 9, 3), (("실무책임자", "성명"), ("x",)))], [(cell("f", 7, 3), (("연구책임자", "성명"), ("x",)))]
    assert X._cell_pairs(*who, text, text, {"성명": 2}, {"성명": 2})[0] == []   # 「성명」 은 책임자마다 있다 — 다른 책임자의 성명을 잇지 않는다
    box = {"t": "[ ] 일반형", "f": "[ √ ] 일반형 (해당항목 체크)"}.get
    top = lambda r: ([(cell("t", r, 5), (("연차보고서",), ()))], [(cell("f", r, 5), (("연구개발계획서",), ()))])  # noqa: E731
    assert ids(X._cell_pairs(*top(0), box, box)[0]) == [("t", "f")] and X._cell_pairs(*top(4), box, box)[0] == []   # ㉢ 문서 제목 줄의 체크 칸만


def test_table_pair_needs_clear_winner_and_applied_records_die_with_their_blocks(pair):
    values, to, frm = pair
    T, F = X._side(to), X._side(frm)
    rows = X._table_pairs(T, F)
    assert all(r["status"] != "paired" or r["score"] >= X.TABLE_MIN for r in rows)
    twin = dict(F, tables=[*F["tables"], *[{**t, "id": t["id"]} for t in F["tables"]]])   # 원본의 표가 모두 둘씩 = 1등과 2등이 같음 → 아무 표도 안 잇는다
    assert not any(r["status"] == "paired" for r in X._table_pairs(T, twin))
    # 넣은 기록 — 넣은 블록이 지금 문서에 없으면(실행 취소) 안 믿는다. ids 가 없는 옛 기록은 그대로
    applied = {"p1": {"from": "x", "hash": "h", "ids": ["p90", "i91"]}, "p2": {"from": "y", "hash": "g"}}
    side = lambda *more: {"blocks": [{"id": "p1", "type": "paragraph"}, {"id": "p2", "type": "paragraph"}, *({"id": i, "type": "paragraph"} for i in more)]}  # noqa: E731
    assert set(merge_api._alive(applied, side())) == {"p2"} and set(merge_api._alive(applied, side("i91"))) == {"p1", "p2"} and merge_api._alive(None, side()) == {}
