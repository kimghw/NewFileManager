"""표 대응의 넣기 계획(spec_병합 ② §5-3 5 「항목」 — app/merge_table_map.py `plan` · `_record`) — 작은 표 두 개를 손으로 지어 본다(문서 · LLM 없음).

2026-11-22 실제 작성본(연구계획서 → 연차보고서)에서 난 것: 표 대응 LLM 이 행·열 짝을 맞게 냈는데 넣기 계획이 「순번이 다름」 · 「이름이 다름」 · 「본뜰 묶음이 빈 항목이 아님」 으로 거의 다 버렸다 —
계획서의 평가 항목 이름에 순번이 없고(「설계사양서 [인텍전기전자]」), 서식의 마지막 줄이 「n.」 이고, 서식의 지표 이름과 계획서의 지표 이름이 띄어쓰기만 달랐다(「기술 요약 정보」 ↔ 「기술요약정보」)."""
from app import merge_table_map as MM


def _table(tid, rows, heads=1):
    """rows = [[글 …] …] — 첫 heads 행은 열 머리, 그 아래 행의 첫 칸은 이름 칸(rowhead), 나머지는 값 칸. → (블록, 3단계 칸 역할 {칸 id: {role}})."""
    cells, s3 = [], {}
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            cid = f"{tid}c{r}_{c}"
            cells.append({"id": cid, "row": r, "col": c, "rowSpan": 1, "colSpan": 1, "text": text, "shaded": r < heads, "bf": "1"})
            s3[cid] = {"role": "colhead" if r < heads else "rowhead" if c == 0 else "field"}
    return {"id": tid, "type": "table", "cells": cells, "borderFills": {}}, s3


def _side(tid, rows, heads=1):
    b, s3 = _table(tid, rows, heads)
    return {"idx": {tid: b}, "s3": s3, "ops": {}, "tables": [{"id": tid, "cells": b["cells"], "owner": {"text": "표", "path": []}}], "names": [], "where": {tid: [b]}, "values": {"current": 2}, "hold": {}, "org_names": []}


def _map(T, F, records, grow=(), fields=((0, 0), (1, 1))):
    tv, fv = MM.view(T, "t"), MM.view(F, "f")
    return {"t": {"from": "f", "records": [{"to": a, "from": b, "example": False} for a, b in records], "grow": [{"like": k, "to": k, "from": b} for k, b in grow],
                  "fields": [{"to": a, "from": b, "kind": "text"} for a, b in fields], "mark": "", "reason": "", "top": {"to": tv["top"], "from": fv["top"]},
                  "sig": {"to": MM.sig(T["idx"]["t"], tv["top"]), "from": MM.sig(F["idx"]["f"], fv["top"])}}}


def _texts(plan):
    return {c["to"]: c["text"] for c in plan["cells"]}


def test_ordinal_slots_keep_their_number_when_the_source_name_has_none():
    """목적 「1.」 · 「n.」 ← 순번 없는 원본 이름: 순번을 둔 채 이름을 잇고, 「n.」 은 위 항목에서 이어 센다. 늘린 묶음도 그 뒤로 이어 센다."""
    T = _side("t", [["평가 항목", "단위"], ["1.", ""], ["n.", ""]])
    F = _side("f", [["평가 항목", "단위"], ["설계사양서 [인텍]", "건"], ["차단용량", "kA"], ["정격전압", "kV"], ["효율", "%"]])
    p = MM.plan(T, F, _map(T, F, [([1], [1]), ([2], [2])], grow=[([2], [3]), ([2], [4])]))
    assert p["skipped"] == [] and p["counts"]["records"] == 4
    assert _texts(p) == {"tc1_0": "1. 설계사양서 [인텍]", "tc1_1": "건", "tc2_0": "2. 차단용량", "tc2_1": "kA"}
    assert [(r["like"], {tuple(c["at"]): c["text"] for c in r["cells"]}) for r in p["rows"]] == [([2, 2], {(0, 0): "3. 정격전압", (0, 1): "kV"}), ([2, 2], {(0, 0): "4. 효율", (0, 1): "%"})]


def test_rows_grown_from_a_numbered_slot_continue_the_numbering():
    T = _side("t", [["평가 항목", "단위"], ["1.", ""], ["2.", ""]])
    F = _side("f", [["평가 항목", "단위"], ["가", "건"], ["나", "건"], ["다", "식"]])
    p = MM.plan(T, F, _map(T, F, [([1], [1]), ([2], [2])], grow=[([2], [3])]))
    assert p["skipped"] == [] and _texts(p)["tc2_0"] == "2. 나"
    assert p["rows"][0]["cells"][0]["text"] == "3. 다"


def test_a_different_ordinal_in_the_source_is_still_refused():
    """원본 이름에 순번이 있고 목적의 순번과 다르면 한 칸 밀린 짝이다 — 그 항목은 통째로 안 넣는다(같은 순번이면 원본 글 그대로)."""
    T = _side("t", [["평가 항목", "단위"], ["1.", ""], ["2.", ""]])
    F = _side("f", [["평가 항목", "단위"], ["2. 나", "건"], ["2. 둘", "식"]])
    p = MM.plan(T, F, _map(T, F, [([1], [1]), ([2], [2])]))
    assert [(s["record"], s["why"]) for s in p["skipped"]] == [(0, "name")] and "순번이 다름" in p["skipped"][0]["detail"]
    assert _texts(p) == {"tc2_0": "2. 둘", "tc2_1": "식"}


def test_a_fixed_name_that_differs_only_by_spacing_is_the_same_item():
    """서식에 박힌 이름과 원본 이름이 띄어쓰기·기호만 다르면 같은 항목 — 이름은 서식 것을 두고 값만 넣는다. 정말 다른 이름은 전처럼 그 항목을 통째로 안 넣는다."""
    T = _side("t", [["성과지표명", "2027"], ["기술 요약 정보", ""], ["지식재산권(출원)", ""]])
    F = _side("f", [["성과지표명", "2027"], ["기술요약정보", "3"], ["특허", "2"]])
    p = MM.plan(T, F, _map(T, F, [([1], [1]), ([2], [2])]))
    assert _texts(p) == {"tc1_1": "3"}
    assert [(s["record"], s["why"]) for s in p["skipped"]] == [(1, "name")]


def _grid(tid, cells, names=(), labels=()):
    """cells = [(행, 열, 행 병합, 글, 역할)] → 한쪽(side). labels = 구성 반영이 적은 라벨 칸의 (행, 열)."""
    cs = [{"id": f"{tid}c{r}_{c}", "row": r, "col": c, "rowSpan": rs, "colSpan": 1, "text": text, "shaded": role != "field", "bf": "1"} for r, c, rs, text, role in cells]
    b = {"id": tid, "type": "table", "cells": cs, "borderFills": {}}
    return {"idx": {tid: b}, "s3": {f"{tid}c{r}_{c}": {"role": role} for r, c, _, _, role in cells}, "ops": {}, "tables": [{"id": tid, "cells": cs, "owner": {"text": "표", "path": []}}],
            "names": list(names), "where": {tid: [b]}, "values": {"current": 2}, "hold": {},
            "groups": {"g": {"items": [{"label": f"{tid}c{r}_{c}"} for r, c in labels]}}}


def _orig(T, texts=None):
    """올린 빈 양식의 칸 — 지금 글 그대로(texts = {칸 id: 원본 글} 로 몇 칸만 다르게 · None 값 = 원본에 없던 칸)."""
    out = {c["id"]: {"text": c["text"], "top": None, "bottom": None} for c in T["idx"]["t"]["cells"]}
    for k, v in (texts or {}).items():
        if v is None:
            out.pop(k)
        else:
            out[k]["text"] = v
    return out


def test_footnote_marks_on_form_names_do_not_make_a_different_name_and_a_named_row_fails_alone():
    """머리 글 끝의 각주 번호(「공고번호6)」)는 이름이 아니다. 이름으로 짝지어진 항목(표지 같은 양식 표)은 예시를 못 바꿔도 그 항목만 건너뛴다 — 차례로 선 표(순번 줄)는 전처럼 표 전체."""
    T = _side("t", [["항목", "값"], ["공고번호6)", ""], ["선정방식9)", "사람이 쓴 글"]])
    F = _side("f", [["항목", "값"], ["공고번호", "2026-1"], ["선정방식", "지정공모"]])
    m = _map(T, F, [([1], [1]), ([2], [2])])
    m["t"]["records"][1]["example"] = True   # LLM 은 예시라고 봤지만 등록된 빈 양식이 아니다(orig None) — 그 칸은 사람 글
    p = MM.plan(T, F, m)
    assert _texts(p) == {"tc1_1": "2026-1"}
    assert [(s.get("record"), s["why"]) for s in p["skipped"]] == [(1, "occupied")]
    T = _side("t", [["항목", "값"], ["1.", "사람이 쓴 글"], ["2.", ""]])
    F = _side("f", [["항목", "값"], ["가", "1"], ["나", "2"]])
    m = _map(T, F, [([1], [1]), ([2], [2])])
    m["t"]["records"][0]["example"] = True
    p = MM.plan(T, F, m)
    assert p["todo"] == 0 and [s["why"] for s in p["skipped"]] == ["example"]


def test_form_text_left_on_a_row_the_division_relabelled_is_an_example_value():
    """구성 반영이 기관 이름을 적은 행에 남은 서식 글(「기관유형」 「대기업」 · 본뜬 행의 같은 글)은 예시 값 — LLM 이 그 항목을 예시로 안 적었어도 덮는다. 기관 이름 칸은 안 건드린다."""
    H, R, V = "colhead", "rowhead", "field"
    T = _grid("t", [(0, 0, 1, "기관", H), (0, 1, 1, "기관유형", H), (0, 2, 1, "금액", H),
                    (1, 0, 1, "인텍", V), (1, 1, 1, "중소기업", R), (1, 2, 1, "800", V),
                    (2, 0, 1, "전기연구원", V), (2, 1, 1, "대기업", R), (2, 2, 1, "", V),
                    (3, 0, 1, "새 기관", V), (3, 1, 1, "대기업", R), (3, 2, 1, "", V)], labels=[(1, 0), (2, 0), (3, 0)])
    F = _grid("f", [(0, 0, 1, "기관", H), (0, 1, 1, "기관유형", H), (0, 2, 1, "금액", H),
                    (1, 0, 1, "인텍(주)", V), (1, 1, 1, "중소기업", R), (1, 2, 1, "1,700", V),
                    (2, 0, 1, "KERI", V), (2, 1, 1, "정부 출연연", R), (2, 2, 1, "500", V),
                    (3, 0, 1, "새기관", V), (3, 1, 1, "전문연", R), (3, 2, 1, "300", V)])
    orig = _orig(T, {"tc1_0": "A기업", "tc2_0": "B기업", "tc3_0": None, "tc3_1": None, "tc3_2": None})   # 3행은 구성 반영이 본떠 만든 행
    m = _map(T, F, [([1], [1]), ([2], [2]), ([3], [3])], fields=((0, 0), (1, 1), (2, 2)))
    m["t"]["records"][0]["example"] = True
    p = MM.plan(T, F, m, orig)
    assert p["skipped"] == []
    assert _texts(p) == {"tc1_2": "1,700", "tc2_1": "정부 출연연", "tc2_2": "500", "tc3_1": "전문연", "tc3_2": "300"}
    assert MM.plan(T, F, m)["counts"]["skipped"]["name"] == 2   # 등록된 빈 양식이 아니면(orig 없음) 전처럼 사람 글로 본다


def test_an_item_does_not_clear_what_another_item_writes():
    """이름 칸 하나에 두 행이 걸린 예시 항목을 행마다 따로 짝지어도 서로의 행을 「남은 예시」 로 지우지 않는다(지우면 쓴 글이 반영 끝에 사라진다)."""
    H, R, V = "colhead", "rowhead", "field"
    T = _grid("t", [(0, 0, 1, "분류", H), (0, 1, 1, "이름", H), (0, 2, 1, "비중", H),
                    (1, 0, 2, "기술분류", R), (1, 1, 1, "1순위 소분류 명칭", V), (1, 2, 1, "00%", V), (2, 1, 1, "1순위 소분류 코드", V), (2, 2, 1, "00%", V)])
    F = _grid("f", [(0, 0, 1, "분류", H), (0, 1, 1, "이름", H), (0, 2, 1, "비중", H),
                    (1, 0, 2, "기술분류", R), (1, 1, 1, "보호/감시장치", V), (1, 2, 1, "60%", V), (2, 1, 1, "ED0307", V), (2, 2, 1, "60%", V)])
    m = _map(T, F, [([1], [1]), ([2], [2])], fields=((1, 1), (2, 2)))
    for r in m["t"]["records"]:
        r["example"] = True
    p = MM.plan(T, F, m, _orig(T))
    assert _texts(p) == {"tc1_1": "보호/감시장치", "tc1_2": "60%", "tc2_1": "ED0307", "tc2_2": "60%"}
    assert p["clears"] == [] and p["counts"]["cleared"] == 0 and p["tables"][0]["cleared"] == 0


def test_a_form_name_that_touches_the_source_name_takes_the_values_and_keeps_its_name():
    """서식에 박힌 이름과 글자는 다르지만 닿는 이름(「지식재산권(출원)」 ↔ 「특허 › 출원」 · 「사업화실적」 ↔ 「사업화」)은 LLM 이 이은 대로 값만 넣는다 — 이름은 서식 것 그대로, 계획에 적는다.
    닿지 않는 이름(서식의 예시 이름일 수 있다)은 전처럼 그 항목을 안 넣는다."""
    H, R, V = "colhead", "rowhead", "field"
    T = _grid("t", [(0, 0, 1, "성과지표명", H), (0, 1, 1, "구분", H), (0, 2, 1, "2027", H),
                    (1, 0, 1, "지식재산권(출원)", R), (1, 1, 1, "목표", R), (1, 2, 1, "", V),
                    (2, 0, 1, "사업화실적", R), (2, 1, 1, "목표", R), (2, 2, 1, "", V),
                    (3, 0, 1, "계획수립 및 자료조사", R), (3, 1, 1, "목표", R), (3, 2, 1, "", V)])
    F = _grid("f", [(0, 0, 1, "성과지표명", H), (0, 1, 1, "구분", H), (0, 2, 1, "2027", H),
                    (1, 0, 1, "특허", R), (1, 1, 1, "출원", R), (1, 2, 1, "3", V),
                    (2, 0, 1, "사업화", R), (2, 1, 1, "목표(단계별)", R), (2, 2, 1, "1", V),
                    (3, 0, 1, "서브모듈 시작품 제작", R), (3, 1, 1, "목표(단계별)", R), (3, 2, 1, "2", V)])
    p = MM.plan(T, F, _map(T, F, [([1], [1]), ([2], [2]), ([3], [3])], fields=((0, 0), (2, 2))))
    assert _texts(p) == {"tc1_2": "3", "tc2_2": "1"}
    assert [(n["record"], n["why"]) for n in p["notes"]] == [(0, "renamed"), (1, "renamed")] and "지식재산권(출원)" in p["notes"][0]["detail"] and p["counts"]["renamed"] == 2
    assert [(s["record"], s["why"]) for s in p["skipped"]] == [(2, "name")]


def test_an_example_row_leaves_no_example_sum_beside_real_values():
    """예시 항목을 실제 값으로 바꿀 때: 계산 칸(합계)은 피연산자가 모두 이 항목의 짝이면 원본 값을 옮기고, 짝은 됐는데 원본이 빈 칸의 예시 값은 지운다 — 실제 금액 옆에 예시 합계가 남지 않게.
    여러 항목에 걸친 자리표시 머리 칸(「연차 n」)은 항목들의 원본 값이 같으면 한 번 적는다."""
    H, R, V = "colhead", "rowhead", "field"
    T = _grid("t", [(0, 0, 1, "연차", H), (0, 1, 1, "기관", H), (0, 2, 1, "현금", H), (0, 3, 1, "현물", H), (0, 4, 1, "합계", H), (0, 5, 1, "비고", H),
                    (1, 0, 2, "n", R), (1, 1, 1, "인텍", R), (1, 2, 1, "800", V), (1, 3, 1, "200", V), (1, 4, 1, "1,000", V), (1, 5, 1, "예시 비고", V),
                    (2, 1, 1, "전기연", R), (2, 2, 1, "", V), (2, 3, 1, "", V), (2, 4, 1, "", V), (2, 5, 1, "", V)], names=["인텍", "전기연"])
    T["ops"] = {"tc1_4": {"tc1_2", "tc1_3"}, "tc2_4": {"tc2_2", "tc2_3"}}
    F = _grid("f", [(0, 0, 1, "연차", H), (0, 1, 1, "기관", H), (0, 2, 1, "현금", H), (0, 3, 1, "현물", H), (0, 4, 1, "합계", H), (0, 5, 1, "비고", H),
                    (1, 0, 2, "3", R), (1, 1, 1, "인텍", R), (1, 2, 1, "1,700", V), (1, 3, 1, "756", V), (1, 4, 1, "2,456", V), (1, 5, 1, "", V),
                    (2, 1, 1, "전기연", R), (2, 2, 1, "398", V), (2, 3, 1, "0", V), (2, 4, 1, "398", V), (2, 5, 1, "", V)], names=["인텍", "전기연"])
    m = _map(T, F, [([1], [1]), ([2], [2])], fields=((0, 0), (2, 2), (3, 3), (4, 4), (5, 5)))
    m["t"]["records"][0]["example"] = True
    p = MM.plan(T, F, m, _orig(T, {"tc1_1": "주관기관명", "tc2_1": "공동기관명"}))
    assert p["skipped"] == []
    assert _texts(p) == {"tc1_2": "1,700", "tc1_3": "756", "tc1_4": "2,456", "tc2_2": "398", "tc2_3": "0", "tc2_4": "398", "tc1_0": "3"}
    assert [(c["to"], c["was"]) for c in p["clears"]] == [("tc1_5", "예시 비고")]
    m["t"]["fields"] = [f for f in m["t"]["fields"] if f["to"] != 3]   # 현물 열이 짝이 아니면 합계의 피연산자가 다 이어지지 않는다 — 합계는 안 옮기고(계산 몫) 예시 합계는 지운다
    p = MM.plan(T, F, m, _orig(T, {"tc1_1": "주관기관명", "tc2_1": "공동기관명"}))
    assert "tc1_4" not in _texts(p) and "tc2_4" not in _texts(p) and {c["to"] for c in p["clears"]} == {"tc1_3", "tc1_4", "tc1_5"}


def test_a_source_table_split_over_two_pages_is_read_as_one_table():
    """원본 표가 쪽 넘김으로 둘로 나뉘어 있으면(바로 잇따르고 머리 행이 꼭 같다) 한 표로 읽는다 — 뒤쪽 표의 항목도 행 번호를 이어서 짝짓는다. 머리가 다른 다음 표는 잇지 않는다."""
    T = _side("t", [["평가 항목", "단위"], ["1.", ""], ["2.", ""], ["3.", ""]])
    F = _side("f", [["평가 항목", "단위"], ["가 [인텍]", "건"], ["나 [인텍]", "식"]])
    b2, s3 = _table("f2", [["평가 항목", "단위"], ["다 [선급]", "종"]])
    b3, s3b = _table("f3", [["다른 표", "값"], ["라", "1"]])
    blank = {"id": "p1", "type": "paragraph", "text": ""}
    seq = [F["idx"]["f"], blank, b2, b3]
    F["idx"].update({"f2": b2, "f3": b3, "p1": blank})
    F["s3"].update({**s3, **s3b})
    F["where"] = {"f": seq, "f2": seq, "f3": seq, "p1": seq}
    F["tables"] += [{"id": "f2", "cells": b2["cells"], "owner": {"text": "표", "path": []}}, {"id": "f3", "cells": b3["cells"], "owner": {"text": "표", "path": []}}]
    v = MM.source_view(F, "f")
    assert v["parts"] == ["f", "f2"] and v["rows"] == 4 and v["at"][(3, 0)]["text"] == "다 [선급]" and v["at"][(3, 0)]["id"] == "f2c1_0"
    tail = MM.source_view(F, "f2")   # 표 짝이 사슬의 뒤쪽 표에 걸려 있어도 원본은 사슬 전체다(행 번호는 첫 표부터)
    assert tail["id"] == "f2" and tail["parts"] == ["f", "f2"] and tail["at"][(1, 0)]["text"] == "가 [인텍]" and MM.source_view(F, "f3")["parts"] == ["f3"]
    payload, ctx = MM.data(T, F, "t", "f")
    assert [s["key"] for s in payload["sources"]] == ["f", "f3"] and any("다 [선급]" in ln for ln in payload["sources"][0]["grid"])   # 이어진 표는 앞 표의 격자에 · 따로 싣지 않는다
    m, rejected = MM.check(ctx, {"from": "f", "records": [{"to": [1], "from": [1], "example": False}, {"to": [2], "from": [2], "example": False}, {"to": [3], "from": [3], "example": False}],
                                 "grow": [], "fields": [{"to": 0, "from": 0, "kind": "text"}, {"to": 1, "from": 1, "kind": "text"}], "mark": "", "reason": ""})
    assert m and not rejected
    p = MM.plan(T, F, {"t": m})
    assert p["skipped"] == [] and _texts(p) == {"tc1_0": "1. 가 [인텍]", "tc1_1": "건", "tc2_0": "2. 나 [인텍]", "tc2_1": "식", "tc3_0": "3. 다 [선급]", "tc3_1": "종"}
    assert {c["to"]: c["from"] for c in p["cells"]}["tc3_1"] == "f2c1_1"   # 칸 id 는 뒤쪽 표의 제 것 — 서식도 그 칸에서 가져온다
    F["idx"]["f2"]["cells"][0]["text"] = "평가항목(바뀜)"   # 이어진 표의 머리가 달라지면 그 대응은 낡음
    assert MM.plan(T, F, {"t": m})["counts"]["stale"] == 1


def test_replanning_after_the_fill_has_nothing_to_do():
    """넣은 뒤(이름 칸 = 「1. 설계사양서」)에 다시 계획하면 일도 못 넣은 것도 없다 — 순번을 붙여 넣은 이름을 「이름이 다름」 으로 세지 않는다."""
    T = _side("t", [["평가 항목", "단위"], ["1. 설계사양서 [인텍]", "건"], ["2. 차단용량", "kA"]])
    F = _side("f", [["평가 항목", "단위"], ["설계사양서 [인텍]", "건"], ["차단용량", "kA"]])
    p = MM.plan(T, F, _map(T, F, [([1], [1]), ([2], [2])]))
    assert p["todo"] == 0 and p["skipped"] == [] and p["counts"]["records"] == 2


def test_an_answer_that_lumps_several_items_is_split_and_only_the_bad_item_is_skipped():
    """LLM 이 목적 표의 여러 항목(이름 칸마다 — 「가」 2행 · 「나」 · 「다」)을 한 항목으로 답했는데 「가」 의 칸 하나가 안 맞으면(두 행에 걸친 목적 칸 하나에 원본 칸 둘)
    「가」 만 건너뛰고 「나」 · 「다」 는 넣는다 — 2026-11-22 실제 이관: Opus 5.5 가 표지 2~9행을 한 항목으로 답해 기술분류 두 행까지 빠졌다(spec_병합 ② §5-3 5 「항목」).
    나눠도 같은 까닭으로 안 되는 진짜 한 항목은 전처럼 통째로 건너뛴다."""
    H, R, V = "colhead", "rowhead", "field"
    T = _grid("t", [(0, 0, 1, "항목", H), (0, 1, 1, "값", H),
                    (1, 0, 2, "가", R), (1, 1, 2, "", V),
                    (3, 0, 1, "나", R), (3, 1, 1, "", V),
                    (4, 0, 1, "다", R), (4, 1, 1, "", V)])
    F = _side("f", [["항목", "값"], ["가", "1"], ["가", "2"], ["나", "3"], ["다", "4"]])
    p = MM.plan(T, F, _map(T, F, [([1, 2, 3, 4], [1, 2, 3, 4])]))
    assert _texts(p) == {"tc3_1": "3", "tc4_1": "4"} and p["counts"]["records"] == 2
    assert [(s["record"], s["why"], s["detail"]) for s in p["skipped"]] == [(0, "shape", "2행 항목 — 목적 칸 하나에 원본 칸이 둘(열 0)")]   # 두 행에 걸친 이름 칸이 먼저 걸린다
    p = MM.plan(T, F, _map(T, F, [([1, 2], [1, 2])]))   # 한 항목(「가」) — 나눌 것이 없다
    assert p["cells"] == [] and [s["why"] for s in p["skipped"]] == ["shape"]


def test_prompt_carries_the_table_guides_and_the_contract_line_only_when_there_are_some():
    """표 대응의 자료 — 목적 표의 작성 지침 `target.guides`(spec_병합 ② §5-11)가 있으면 계약에 그 한 줄. 없으면 전과 같다."""
    from app import merge_table_map as MT
    from app import place_guides as PG
    base = {"target": {"key": "t1", "title": "표", "grid": []}, "sources": []}
    assert PG.CONTRACT_LINE not in MT.prompt(base)
    got = MT.prompt({**base, "target": {**base["target"], "guides": [{"src": "doc", "kind": "각주 번호 3)", "label": "사업비3)", "cell": "r0c2", "text": "3. 해당 연도만"}]}})
    assert PG.CONTRACT_LINE in got and '"cell":"r0c2"' in got
