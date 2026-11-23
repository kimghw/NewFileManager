"""같은 양식 취합 — 순수 셈(app/merge_collect.py) · 자리 연결의 strict 규칙(app/merge_pairs.py) · 범위(app/merge_take.py Allowed 의 common). spec_취합 ② §10.
음성 시험(astra R1 · R2 — artifacts/plan_gather_astra_2026-11-24/): 틀리게 넣지 않고 남겨야 하는 입력."""
from app import merge_collect as MC
from app import merge_pairs as P
from app import merge_take as TK

VALUES = {"stages": [4], "orgs": {"lead": "한국선급", "joint": ["씨드로닉스", "유엔젤", "주식회사 랩오투원"]}, "current": 1}


# ---- 등록부 ----

def test_registry_clean_drops_bad_revisions_and_keeps_order():
    G = MC.clean({"version": 3, "order": ["b", "a", "zz"], "parts": {"a": {"orgs": ["유엔젤", "유엔젤"], "orgsBy": "name"}, "b": {"orgs": [], "orgsBy": "name", "revOf": "a", "common": True},
                                                                   "c": {"orgs": ["x"], "revOf": "c"}, "d": {"orgs": ["x"], "revOf": "없는것"}}})
    assert G["version"] == 3 and G["order"] == ["b", "a", "c", "d"]
    assert G["parts"]["a"]["orgs"] == ["유엔젤"] and G["parts"]["a"]["orgsBy"] == "name"
    assert G["parts"]["b"] == {"orgs": [], "orgsBy": "", "common": True, "revOf": "a", "added": None, "done": None}   # 기관이 없으면 orgsBy 도 없다
    assert G["parts"]["c"]["revOf"] is None and G["parts"]["d"]["revOf"] is None   # 자기 자신 · 없는 문서
    assert MC.clean(None) == MC.blank() and MC.clean({"parts": []}) == MC.blank()


def test_revision_chain_and_later_and_cycles_are_cut():
    G = MC.clean({"parts": {"s1": {"orgs": ["a"]}, "s2": {"orgs": ["a"], "revOf": "s1"}, "s3": {"orgs": ["a"], "revOf": "s2"}}})
    assert MC.chain(G, "s3") == ["s2", "s1"] and MC.chain(G, "s1") == []
    assert MC.later(G, "s1") == ["s2"] and MC.later(G, "s3") == []
    loop = MC.clean({"parts": {"a": {"orgs": ["x"], "revOf": "b"}, "b": {"orgs": ["x"], "revOf": "a"}}})   # 고리 — 한쪽은 끊긴다(둘 다 서로의 수정본일 수 없다)
    assert [loop["parts"][k]["revOf"] for k in ("a", "b")].count(None) >= 1


def test_auto_org_by_file_name_then_single_label_else_unassigned():
    others = ["본 계획서_데이터플랫폼.hwpx", "다른 기관.hwpx"]
    assert MC.auto_org("1. 연구개발계획서_1세부_유엔젤_260320.hwpx", others, VALUES, {"유엔젤"})[:2] == ("유엔젤", "name")
    assert MC.auto_org("(랩오투원) 연구개발계획서_v0.2.hwpx", others, VALUES, set())[:2] == ("랩오투원", "name")   # 「주식회사」 는 뗀 꼴로 견준다
    assert MC.auto_org("연구개발계획서_SDX_4차년도 수정.hwpx", others, VALUES, {"씨드로닉스"})[:2] == ("씨드로닉스", "label")   # 파일 이름에 없음 → 문서의 기관 라벨이 하나
    org, by, why = MC.auto_org("(75%수정) 연구개발계획서_0325 예산.hwpx", others, VALUES, {"한국선급", "씨드로닉스", "유엔젤", "랩오투원"})
    assert org is None and "여러 기관" in why   # 여러 기관의 절이 든 문서 — 짐작하지 않는다
    assert MC.auto_org("유엔젤_계획서.hwpx", others, VALUES, {"씨드로닉스"})[0] is None   # 파일 이름과 라벨이 다른 기관을 가리킴
    assert MC.auto_org("유엔젤_씨드로닉스.hwpx", others, VALUES, set())[0] is None   # 이름이 둘
    every = ["한국선급 과제_유엔젤.hwpx", "한국선급 과제_본.hwpx"]
    assert MC.auto_org("한국선급 과제_씨드로닉스.hwpx", every, VALUES, set())[:2] == ("씨드로닉스", "name")   # 모든 문서 이름에 든 이름(과제 이름)은 뺀다


# ---- 자리 연결: 기관은 이름으로 · 맥락이 같은 후보만 · 원본 하나는 한 자리에만 ----

def test_org_identity_in_a_part_document_is_the_name_not_the_number():
    v = P.core.norm_values(VALUES)
    own = {"유엔젤"}
    assert P._ident(P.core.ORG, ("joint", 1), "[공동연구개발기관1 : 유엔젤]", v) == ("org", "씨드로닉스")   # 이관(번호) — 그대로
    assert P._ident(P.core.ORG, ("joint", 1), "[공동연구개발기관1 : 유엔젤]", v, own=own) == ("org", "유엔젤")   # 기관 문서 — 이름이 먼저
    assert P._ident(P.core.ORG, ("lead", 0), "[주관연구개발기관 : 유엔젤] ※ 기업만 작성", v, own=own) == ("org", "유엔젤")
    assert P._ident(P.core.ORG, ("joint", 2), "[공동연구개발기관2]", v, own=own) == ("org", "유엔젤")   # 이름 없음 · 역할(공동)이 반영할 기관의 역할과 같다
    assert P._ident(P.core.ORG, ("lead", 0), "(1) 주관연구개발기관책임자", v, own=own) is None   # 이름 없음 · 역할이 다르다(주관 ≠ 공동) — 모름
    assert P._ident(P.core.ORG, ("joint", 1), "[공동연구개발기관1]", v, own={"유엔젤", "씨드로닉스"}) is None   # 반영할 기관이 둘 — 모름
    assert P._ident(P.core.ORG, ("lead", 0), "[주관연구개발기관]", v, own={"한국선급"}) == ("org", "한국선급")


def _g(key, ctx=None, path=("연구개발 목표 및 내용",), items=(("org", "유엔젤"),), kind="paragraph", label="공동연구개발기관"):
    return {"key": key, "dim": P.core.ORG, "kind": kind, "label": label, "path": list(path), "inner": [], "ctx": {"year": None, "org": None, **(ctx or {})},
            "items": [{"value": "공동", "id": f"{key}-{i}", "text": "", "ident": x} for i, x in enumerate(items)]}


def test_strict_pairing_needs_the_same_context_and_never_fans_out():
    to = [_g(f"t{y}", {"year": y}) for y in (1, 2, 3, 4)]
    frm = [_g("f")]   # 차년도 구분 없이 쓴 원본 절 하나
    loose = P.pair(to, frm)
    assert [g["status"] for g in loose["groups"][:4]] == ["paired"] * 4   # 이관의 규칙 — 네 자리 모두에(실측의 오매핑)
    strict = P.pair(to, frm, strict=True)
    assert [g["status"] for g in strict["groups"][:4]] == ["ambiguous"] * 4 and strict["groups"][0]["reason"] == P.STRICT_CTX
    assert strict["groups"][0]["candidates"] and strict["groups"][-1]["status"] == "fromOnly"   # 후보는 보인다(사람이 고른다) · 원본 묶음은 안 쓰였다
    same = P.pair(to, [_g("f4", {"year": 4})], strict=True)   # 맥락이 같은 자리 하나에만
    assert [g["status"] for g in same["groups"][:4]] == ["toOnly", "toOnly", "toOnly", "paired"]   # 차년도가 다른 자리에는 후보도 아니다(score — 전부터)
    two = P.pair([_g("a", {"year": 4}), _g("b", {"year": 4})], [_g("f4", {"year": 4})], strict=True)   # 맥락까지 같은 자리가 둘 — 임의로 한 자리를 고르지 않는다
    assert [g["status"] for g in two["groups"][:2]] == ["ambiguous", "ambiguous"] and two["groups"][0]["reason"] == P.STRICT_FAN
    user = P.pair([_g("a", {"year": 4}), _g("b", {"year": 4})], [_g("f4", {"year": 4})], fixed={"a": {"from": "f4", "source": "user"}}, strict=True)   # 사람이 고른 짝은 그대로 · 나머지는 확인 필요
    assert [(g["status"], g["source"]) for g in user["groups"][:2]] == [("paired", "user"), ("ambiguous", "script")]


# ---- 범위: 기관을 모르는 자리(공통)는 「공통 자리 포함」 일 때만 ----

def test_allowed_common_flag_only_changes_unknown_org_places():
    relay = TK.Allowed(None, VALUES)
    assert not relay.active and relay.org(None) and relay.ctx({"org": None, "year": None}) and relay.ctx(None)   # 이관 — 전과 같다
    part = TK.Allowed({"org": ["유엔젤"]}, VALUES, common=False)
    assert part.active and part.org("유엔젤") and not part.org("씨드로닉스") and not part.org(None)
    assert not part.ctx({"org": None, "year": 2}) and part.ctx({"org": None, "year": 2}, org_items=True)   # 기관을 늘어놓는 묶음은 항목마다 본다
    assert part.ident(("org", "유엔젤")) and not part.ident(("org", "한국선급"))
    assert TK.Allowed({"org": ["유엔젤"]}, VALUES, common=True).ctx({"org": None, "year": None})
    none = TK.Allowed({"org": []}, VALUES, common=False)   # 교집합이 빔 — 아무 기관도 아님(「전부」 가 아니다)
    assert none.active and not none.org("유엔젤") and not none.ident(("org", "유엔젤"))


def test_narrow_keeps_org_item_groups_and_drops_common_groups_without_common():
    view = P.pair([_g("orgs", {"year": 4}, items=(("org", "유엔젤"), ("org", "씨드로닉스"))), {**_g("years", items=(("year", 1), ("year", 2))), "dim": P.core.YEAR}],
                  [_g("f", {"year": 4}), {**_g("fy", items=(("year", 1),)), "dim": P.core.YEAR}], strict=True)
    to_groups = [_g("orgs", {"year": 4}, items=(("org", "유엔젤"), ("org", "씨드로닉스"))), {**_g("years", items=(("year", 1), ("year", 2))), "dim": P.core.YEAR}]
    TK.narrow(view, to_groups, TK.Allowed({"org": ["유엔젤"]}, VALUES, common=False))
    orgs, years = view["groups"][0], view["groups"][1]
    assert orgs["status"] == "paired" and [it["status"] for it in orgs["items"]] == ["paired", "outside"]   # 다른 기관의 항목만 범위 밖
    assert years["status"] == "outside"   # 기관이 안 걸린 차년도 묶음 = 공통 자리


# ---- 수정본의 3방향 ----

def _row(t, s, s_text, t_text=None, place="K", letter=None):
    return MC.led_row(t, s, s_text, s_text if t_text is None else t_text, place, letter)


def test_cell_three_way():
    r = _row("c17", "x1", "100")
    assert MC.cell_item(r, "y1", "100", "100") is None                              # 수정본이 그대로 — 건드리지 않는다
    assert MC.cell_item(r, "y1", "100", "사람이 고침") is None                       # 그대로면 사람이 고친 것도 둔다
    assert MC.cell_item(r, "y1", "120", "100")["status"] == "ready"
    assert MC.cell_item(r, "y1", "120", "120")["status"] == "same"                   # 이미 수정본의 글
    assert MC.cell_item(r, "y1", "120", "110")["status"] == "overlap"                # 사람이 고친 자리 — 덮지 않는다
    assert MC.cell_item(r, None, None, "100")["status"] == "missing"                 # 수정본에 짝이 없음 — 그대로
    assert MC.cell_item(_row("c1", "x", "[ √ ]", "■"), "y", "[  ]", "■")["status"] == "hold"   # 바꿔 적어 넣은 칸 — 저절로 못 고침
    assert MC.cell_item(MC.led_row("c1", "x", None, None, "t"), "y", "a", "b")["status"] == "hold"


def _new(*texts, letters=None):
    return [{"id": f"n{i}", "text": t, "letter": (letters or {}).get(i), "key": P._ws(t) if t is not None else f"\0table:{i}"} for i, t in enumerate(texts)]


def test_body_three_way_changes_only_what_the_revision_changed():
    rows = [_row("t1", "s1", "센서 개발"), _row("t2", "s2", "시험 수행"), _row("t3", "s3", "예산 집행")]
    now = {"t1": "센서 개발", "t2": "시험 수행", "t3": "예산 집행"}
    order = {"t1": 10, "t2": 11, "t3": 12}
    assert MC.body_items(rows, _new("센서 개발", "시험 수행", "예산 집행"), now, order) == []
    got = MC.body_items(rows, _new("센서 개발", "시험 수행(개정)", "예산 집행"), now, order)
    assert [(g["kind"], g["to"], g["status"], g["text"]) for g in got] == [("para", "t2", "ready", "시험 수행(개정)")]
    got = MC.body_items(rows, _new("센서 개발", "시험 수행(개정)", "예산 집행"), {**now, "t2": "사람이 고친 글"}, order)
    assert got[0]["status"] == "overlap"                                              # 사람이 고친 자리 — 덮지 않는다
    got = MC.body_items(rows, _new("센서 개발", "시험 수행(개정)", "예산 집행"), {**now, "t2": "시험 수행(개정)"}, order)
    assert got[0]["status"] == "same"


def test_body_excerpt_revision_never_deletes():   # ㉣ 같은 항목의 발췌 — 수정본에 한 줄만 있다
    rows = [_row("t1", "s1", "센서"), _row("t2", "s2", "시험"), _row("t3", "s3", "예산")]
    got = MC.body_items(rows, _new("시험 개정"), {"t1": "센서", "t2": "시험", "t3": "예산"}, {"t1": 0, "t2": 1, "t3": 2})
    assert all(g["status"] in ("missing", "hold") for g in got) and not [g for g in got if g["status"] == "ready"]   # 지우기 0 · 못 정한 것은 확인 필요


def test_body_duplicate_lines_are_held():   # ㉠ 같은 글 여러 줄
    rows = [_row("t1", "s1", "시작"), _row("t2", "s2", "검증"), _row("t3", "s3", "검증"), _row("t4", "s4", "끝")]
    got = MC.body_items(rows, _new("시작", "검증", "끝"), {"t1": "시작", "t2": "검증(메모)", "t3": "검증", "t4": "끝"}, {f"t{i}": i for i in range(1, 5)})
    assert got and all(g["status"] in ("hold", "missing") for g in got)


def test_body_added_block_needs_clear_neighbours():
    rows = [_row("t1", "s1", "A"), _row("t2", "s2", "B")]
    now = {"t1": "A", "t2": "B"}
    ok = MC.body_items(rows, _new("A", "새 줄", "B"), now, {"t1": 5, "t2": 6})
    assert [(g["kind"], g["status"], g["after"]) for g in ok] == [("add", "ready", "t1")]
    between = MC.body_items(rows, _new("A", "새 줄", "B"), now, {"t1": 5, "t2": 7})   # 앞뒤 줄 사이에 사람이 쓴 블록
    assert between[0]["status"] == "hold"
    head = MC.body_items(rows, _new("새 줄", "A", "B"), now, {"t1": 5, "t2": 6})      # 항목의 맨 앞 — 앞 줄이 없다
    assert head[0]["status"] == "hold"
    tail = MC.body_items(rows, _new("A", "B", "끝에 더함"), now, {"t1": 5, "t2": 6})
    assert [(g["status"], g["after"]) for g in tail] == [("ready", "t2")]


def test_converted_prefix_is_kept_only_when_the_letter_is_unchanged():   # astra R2 물음 2
    r = _row("t1", "s1", "■ 시험 계획", "o 시험 계획", letter="■")   # 넣을 때 「■」 를 목적 틀의 「o」 로
    assert MC._para_new(r, "■ 시험 계획(개정)", "■") == ("o 시험 계획(개정)", "")
    assert MC._para_new(r, "□ 시험 계획(개정)", "□")[0] is None            # 레터가 달라짐 — 확인 필요
    num = _row("t2", "s2", "1. 시험", "2. 시험", letter="1.")
    assert MC._para_new(num, "1) 검증", "1)")[0] is None                    # 「1.」 → 「1)」: 본문만 바꿔 「2) 검증」 을 만들지 않는다
    assert MC._para_new(num, "1. 검증", "1.") == ("2. 검증", "")
    plain = _row("t3", "s3", "본문 글")
    assert MC._para_new(plain, "본문 글 수정", None) == ("본문 글 수정", "")   # 넣을 때 안 바꾼 줄 — 수정본 글 그대로
    got = MC.body_items([r], _new("■ 시험 계획(개정)", letters={0: "■"}), {"t1": "o 시험 계획"}, {"t1": 0})
    assert [(g["status"], g["text"]) for g in got] == [("ready", "o 시험 계획(개정)")]
    held = MC.body_items([r], _new("□ 다른 글", letters={0: "□"}), {"t1": "o 시험 계획"}, {"t1": 0})
    assert held[0]["status"] == "hold"


def test_table_or_picture_blocks_are_never_auto_replaced():   # ㉢ 표가 든 본문
    rows = [_row("t1", "s1", "글"), MC.led_row("t2", "s2", None, None, "K")]
    got = MC.body_items(rows, [*_new("글"), {"id": "n1", "text": None, "letter": None, "key": "\0table:다른 표"}], {"t1": "글", "t2": ""}, {"t1": 0, "t2": 1})
    assert [g["status"] for g in got] == ["hold"]


def test_led_rows_filters_by_chain_and_alive_ids():
    ev = [{"part": "s1", "kind": "cells", "ids": ["a", "b"], "led": [["a", "x", "1", "1", "t"], ["b", "y", "2", "2", "t"], ["gone", "z", "3", "3", "t"]]},
          {"part": "other", "kind": "cells", "ids": ["c"], "led": [["c", "x", "1", "1", "t"]]}, {"part": "s1", "kind": "filled", "ids": ["p"]}]
    assert [r[0] for _, r in MC.led_rows(ev, ["s1"])] == ["a", "b"]           # 이벤트의 ids 에 없는 줄(gone)은 안 믿는다
    assert [r[0] for _, r in MC.led_rows(ev, ["s1"], alive={"b"})] == ["b"]
    assert MC.count_text(MC.counts([{"status": "ready"}, {"status": "overlap"}])) == "고칠 곳 1 · 겹침(사람이 고친 자리 — 그대로 둠) 1"


# ---- astra 결과 검토(R3)에서 나온 반례 ----

def test_blank_revision_cell_and_calc_cell_are_not_written():
    assert MC.cell_item(_row("c1", "x", "5,000"), "y", "", "5,000")["status"] == "missing"        # 수정본의 칸이 비어 있음 — 값을 지우지 않는다(발췌 · 빈 양식일 수 있다)
    assert MC.cell_item(_row("c1", "x", "5,000"), "y", "   ", "5,000")["status"] == "missing"
    calc = MC.led_row("c2", "x", "30", "30", "t", calc=True)
    assert MC.cell_item(calc, "y", "32", "30")["status"] == "hold"                                # 계산 칸 — 피연산자가 겹침이면 합계만 바뀐다(15 + 20 = 32)
    assert MC.meta(calc) == {"calc": True} and MC.meta(["a", "b", "c", "d", "e"]) == {}


def test_deleted_lines_keep_their_place_and_are_not_resurrected():
    rows = [_row("t1", "s1", "A"), _row("t2", "s2", "B"), _row("t3", "s3", "C")]
    now = {"t1": "A", "t3": "C"}                                                                  # 사람이 B 를 지웠다(t2 는 지금 문서에 없다)
    assert MC.body_items(rows, _new("A", "B", "C"), now, {"t1": 0, "t3": 1}) == []                # 수정본이 그대로 — B 를 「새로 생긴 줄」 로 되살리지 않는다
    got = MC.body_items(rows, _new("A", "B 개정", "C"), now, {"t1": 0, "t3": 1})
    assert [(g["to"], g["status"]) for g in got] == [("t2", "hold")]                              # 지운 줄이 수정본에서 바뀜 — 넣지 않고 확인 필요
    again = MC.body_items([_row("t1", "s1", "A"), _row("t9", "s2", "B")], _new("A", "B"), {"t1": "A", "t9": "B"}, {"t1": 0, "t9": 1})
    assert again == []                                                                            # 같은 수정본을 다시 계획(이 수정본이 넣은 B 도 원장에 있다) — 할 일 0


def test_paragraph_with_footnotes_or_fields_is_held():
    rows = [_row("t1", "s1", "그림 1 설명")]
    got = MC.body_items(rows, _new("그림 2 설명"), {"t1": "그림 1 설명"}, {"t1": 0}, plain=set())      # 글만 든 문단이 아니다(자동 번호 · 각주 · 필드)
    assert [g["status"] for g in got] == ["hold"]
    assert MC.body_items(rows, _new("그림 2 설명"), {"t1": "그림 1 설명"}, {"t1": 0}, plain={"t1"})[0]["status"] == "ready"


def test_added_rows_carry_a_position_after_their_neighbour():
    rows = [MC.led_row("t1", "s1", "A", "A", "K", pos=0), MC.led_row("t2", "s2", "B", "B", "K", pos=1)]
    got = MC.body_items(rows, _new("A", "새1", "새2", "B"), {"t1": "A", "t2": "B"}, {"t1": 3, "t2": 4})
    assert [g["status"] for g in got] == ["ready", "ready"] and 0 < got[0]["pos"] < got[1]["pos"] < 1   # 다음 수정본이 제자리에서 견준다


def test_tail_keeps_meaningful_parentheses_and_blank_tail_is_not_eliminated():
    assert P._tail({"path": ["연구개발 목표 및 내용(필수)"]}) == P._tail({"path": ["연구개발 목표 및 내용"]})
    assert P._tail({"path": ["연구개발비(현금)"]}) != P._tail({"path": ["연구개발비(현물)"]})
    # 소속이 없는 묶음(표지 표) — 다른 자리가 제 원본을 가져간 뒤에도 「남은 후보 하나」 로 잇지 않는다
    a, b = _g("a", path=()), _g("b", path=())
    f1, f2 = _g("f1", path=()), _g("f2", path=())
    got = P.pair([a, b], [f1, f2], fixed={"a": {"from": "f1", "source": "user"}}, strict=True)
    assert [(g["status"], g["source"]) for g in got["groups"][:2]] == [("paired", "user"), ("ambiguous", "script")]


def test_saved_pairs_must_also_be_the_same_place_in_strict_mode():
    to, frm = [_g("t", {"year": 4})], [_g("f", {"year": 2})]
    assert P.pair(to, frm, fixed={"t": {"from": "f", "source": "saved"}})["groups"][0]["status"] == "paired"          # 이관 — 전과 같다
    assert P.pair(to, frm, fixed={"t": {"from": "f", "source": "saved"}}, strict=True)["groups"][0]["status"] != "paired"
    assert P.pair(to, frm, fixed={"t": {"from": "f", "source": "user"}}, strict=True)["groups"][0]["status"] == "paired"    # 사람이 고른 짝은 그대로
