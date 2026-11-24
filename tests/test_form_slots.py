"""상자 안의 쓸 자리(app/form_slots.py — spec_양식작성 ② §5-3): 종류 가름 · 덩이 · 채울 수 있는 문단 · 새 글 판정 · 한번 채운 자리 · LLM 에 싣는 줄.
견본 = 사용자의 양식(연차 · 최종 · 단계보고서 요약 — artifacts/form_fill_slots_astra_2026-11-24/probe_chunks.py 의 꼴)을 본뜬 상자 둘. astra 1 · 2차의 반대 예는 음성 시험으로."""
from app import form_slots as FS


def para(i, text, **more):
    return {"id": i, "type": "paragraph", "text": text, **more}


def table(i, rows=2, cols=3):
    return {"id": i, "type": "table", "nRows": rows, "nCols": cols,
            "cells": [{"id": f"{i}r{r}c{c}", "row": r, "col": c, "blocks": [para(f"{i}p{r}{c}", "(   )" if r else "")]} for r in range(rows) for c in range(cols)]}


def box(i, blocks):
    return {"id": i, "type": "table", "nRows": 1, "nCols": 1, "cells": [{"id": f"{i}c", "row": 0, "col": 0, "blocks": list(blocks)}]}


# 「■ 세부 과제별 당해연도 성과목표 관리」 아래 상자(t44) — 앞쪽 빈 줄 · 제목 · 자리표시 · 글머리 줄 · 안쪽 표 · 캡션 · 같은 이름의 자리 둘
BOX44 = box("t44", [para("p46", ""), para("p47", "< 연구개발 과제명 작성 >"), para("p48", "주관(기업명 작성) : 개발목표 작성"), para("p49", "추진 내용 작성"), para("p50", "  : "), para("p51", ""), para("p52", ""),
                    table("t55"), para("p53", ""), para("p68", "그림 1 n차년도 연구개발 성과명"), para("p69", "공동(기업명 작성) : "), para("p70", ""), para("p71", ""),
                    para("p75", "공동(기업명 작성) : "), para("p76", " "), para("p77", ""), table("t81"), para("p82", "성과 사진", captionOf="t81")])
# 「■ 다음연도 연구개발 계획」 상자(t97) — 제목 사슬(L1 › L2 › L3) 아래 「000」 과 글머리 줄 · 안내(※) · 샘플 표
BOX97 = box("t97", [para("p99", "■ 다음연도 연구개발 계획"), para("p100", "※ 최종보고서 제출 기관은 작성하지 않으셔도 됩니다."), para("p101", "연구개발 목표 및 내용"), para("p102", "연구개발 목표"), para("p103", "000"),
                    para("p104", "    - "), para("p105", ""), para("p109", "    - "), para("p110", "연구개발 내용 및 범위"), para("p111", "000"), para("p112", "    - "), para("p113", ""), table("t117", 3, 3)])
LEVELS = {"p48": 4, "p49": 1, "p51": 1, "p69": 4, "p70": 1, "p75": 4, "p99": 1, "p101": 2, "p102": 3, "p103": 4, "p104": 5, "p105": 4, "p109": 5, "p110": 3, "p111": 4, "p112": 5, "p113": 4}
CHECK = "■ 작성 기준 보고서 ( □ 연차보고서 □ 최종보고서 □ 단계보고서)"


def _chunks(b, levels=LEVELS, orig=None):
    ents = FS.entries(FS.box_cell(b), levels, orig)
    return ents, FS.chunks(ents)


def test_box_cell_is_a_one_cell_table_only():
    assert FS.box_cell(BOX44)["id"] == "t44c" and FS.box_cell(table("t1")) is None and FS.box_cell(para("p", "글")) is None and FS.box_cell(None) is None


def test_kind_of_reads_the_raw_text_shape():
    k = FS.kind_of
    assert [k(""), k("   "), k(None)] == ["blank"] * 3
    assert [k("    - "), k("  : "), k("o"), k("□")] == ["stub"] * 4                              # 글머리 · 「:」 뿐
    assert [k("■ 연구개발과제명 : "), k("공동(기업명 작성) : "), k("기관명：")] == ["label"] * 3
    assert k(CHECK) == "check" and k("  " + CHECK) == "check" and k("■ 항목 □ 하나") == "text"   # 첫 글자의 ■ 는 글머리 — 「□」 가 둘 이상일 때만 표시 줄
    assert k("※ 최종보고서 제출 기관은 작성하지 않으셔도 됩니다.") == "note"
    assert k("그림 1 n차년도 연구개발 성과명") == "caption" and k("<표 2> 사용계획") == "caption" and k("성과 사진", caption=True) == "caption"
    assert [k("000"), k("주관(기업명 작성) : 개발목표 작성"), k("< 연구개발 과제명 작성 >"), k("그림을 넣습니다")] == ["text"] * 4


def test_entries_and_chunks_of_the_sample_boxes():
    ents, chs = _chunks(BOX44)
    assert [(e["id"], e["kind"]) for e in ents] == [("p46", "blank"), ("p47", "text"), ("p48", "text"), ("p49", "text"), ("p50", "stub"), ("p51", "blank"), ("p52", "blank"), ("t55", "table"), ("p53", "blank"),
                                                   ("p68", "caption"), ("p69", "label"), ("p70", "blank"), ("p71", "blank"), ("p75", "label"), ("p76", "blank"), ("p77", "blank"), ("t81", "table"), ("p82", "caption")]
    assert ents[7]["size"] == "2×3" and ents[4]["raw"] == "  : " and ents[3]["level"] == 1 and ents[0]["level"] is None          # 원문은 앞뒤 빈칸 그대로 · 안쪽 표는 자리만
    got = [(c["no"], c["head"]["id"], [e["id"] for e in c["slots"]], c["dup"]) for c in chs]
    # 앞쪽 빈 줄(p46)은 머리가 없어 자리가 아니다 · 안쪽 표 뒤의 빈 줄(p53)도 · 캡션은 머리가 아니다 · 같은 이름의 덩이 둘
    assert got == [(1, "p47", [], [1, 1]), (2, "p48", [], [1, 1]), (3, "p49", ["p50", "p51", "p52"], [1, 1]), (4, "p69", ["p70", "p71"], [1, 2]), (5, "p75", ["p76", "p77"], [2, 2])]
    ents, chs = _chunks(BOX97)
    got = [(c["head"]["id"], [e["id"] for e in c["slots"]], c["under"], c["dup"]) for c in chs]
    assert got == [("p99", [], "", [1, 1]), ("p101", [], "■ 다음연도 연구개발 계획", [1, 1]), ("p102", [], "연구개발 목표 및 내용", [1, 1]), ("p103", ["p104", "p105", "p109"], "연구개발 목표", [1, 1]),
                   ("p110", [], "연구개발 목표 및 내용", [1, 1]), ("p111", ["p112", "p113"], "연구개발 내용 및 범위", [1, 1])]   # 「000」 둘은 윗 제목이 달라 같은 자리가 아니다 · ※ 안내는 머리가 아니다
    _, flat = _chunks(BOX97, levels=None)
    assert [c["dup"] for c in flat if c["head"]["raw"] == "000"] == [[1, 2], [2, 2]]                                          # 레벨을 모르면 같은 이름으로 본다(사람이 고른다)


def test_targets_are_heads_and_slots_only():
    _, chs = _chunks(BOX97)
    tg = FS.targets(chs)
    assert list(tg) == ["p99", "p101", "p102", "p103", "p104", "p105", "p109", "p110", "p111", "p112", "p113"]               # 안내(p100) · 안쪽 표의 문단은 없다
    assert tg["p104"] == {"raw": "    - ", "kind": "stub", "chunk": 4, "head": "000", "under": "연구개발 목표", "dup": [1, 1], "nth": 1, "level": 5}
    assert (tg["p103"]["nth"], tg["p103"]["kind"], tg["p113"]["nth"], tg["p113"]["head"]) == (0, "text", 2, "000")
    _, chs = _chunks(BOX44)
    tg = FS.targets(chs)
    assert not {"p46", "p53", "p68", "p82", "t55p00"} & set(tg) and tg["p75"]["dup"] == [2, 2] and tg["p76"]["raw"] == " "   # 빈칸 한 칸도 원문 그대로


def test_judge_append_only_after_the_existing_text():
    j = FS.judge
    assert j("■ 연구개발과제명 : ", "■ 연구개발과제명 : 가나다") == ("append", "가나다")
    assert j("    - ", "    - 값") == ("append", "값") and j("  : ", "  : 추진 내용") == ("append", "추진 내용")
    assert j("", "  새 글") == ("append", "새 글") and j(" ", "새 글") == ("append", "새 글")
    assert j("", "첫 줄\n둘째 줄") == ("append", "첫 줄 둘째 줄")                                                              # 줄 나눔은 빈칸으로(문단 하나)
    assert j("공동(기업명 작성) : ", "공동(기업명 작성) : 목표") == ("append", "목표")


def test_judge_rejects_or_marks_replace_for_the_astra_counterexamples():
    j = FS.judge
    assert j("000", "000개발목표") == ("replace", "000개발목표")                               # 자리표시 글 뒤에 덧붙인 것은 붙이기가 아니다(astra 2차 G4)
    assert j("■ 다음연도 연구개발 계획", "■ 다음연도 연구개발 계획 목표 가")[0] == "replace"      # 고정 제목 끝에 덧붙이기
    assert j("주관(기업명 작성) : 개발목표 작성", "주관(한국선급) : 목표")[0] == "replace"
    assert j("공동(기업명 작성) : ", "공동(한국선급) : 목표") == ("replace", "공동(한국선급) : 목표")   # 같은 줄 자리의 고정 글을 바꿈
    assert isinstance(j("    - ", "- 값"), str) and isinstance(j("    - ", "값"), str)             # 글머리 줄은 그 첫머리 그대로
    assert isinstance(j("    - ", "    - "), str) and isinstance(j("", "   "), str) and isinstance(j("■ 과제명 : ", "■ 과제명 :"), str)   # 지금 글과 같음 · 값 없음
    assert isinstance(j("■ 과제명 : ", "■ 과제명 :  "), str)


def test_judge_check_changes_exactly_one_box():
    j = FS.judge
    one = CHECK.replace("□ 연차보고서", "■ 연차보고서")
    assert j(CHECK, one) == ("check", "연차보고서") and j(CHECK, CHECK.replace("□ 단계보고서", "■ 단계보고서")) == ("check", "단계보고서")
    assert j("  " + CHECK, "  " + one) == ("check", "연차보고서")                                # 들여 쓴 줄 — 앞 빈칸 뒤의 ■ 가 글머리다(표시로 세지 않는다)
    assert isinstance(j(CHECK, one.replace("□ 최종보고서", "■ 최종보고서")), str)                 # 둘을 한꺼번에(astra 2차 G7 ②)
    assert isinstance(j(one, one.replace("□ 최종보고서", "■ 최종보고서")), str)                   # 이미 표시한 줄 — 사람이 확인
    assert isinstance(j(CHECK, one + " 제출"), str) and isinstance(j(CHECK, one.replace("연차", "년차")), str)   # 글을 더함 · 다른 글자를 바꿈
    assert isinstance(j(CHECK, "□" + CHECK[1:]), str) and isinstance(j("  " + CHECK, "  □" + CHECK[1:]), str)     # 글머리를 바꿈
    assert isinstance(j(CHECK, CHECK), str)


def test_filled_slots_keep_their_role_and_are_not_targets():
    assert FS.was_kind("■ 과제명 : 값", "■ 과제명 : ") == "label" and FS.was_kind("채운 줄", "") == "blank" and FS.was_kind("    - 값", "    - ") == "stub"
    assert FS.was_kind("■ 과제명 : ", "■ 과제명 : ") is None and FS.was_kind("값", None) is None and FS.was_kind("", "■ 과제명 : ") is None and FS.was_kind("다른 제목", "제목") is None
    filled = box("t44", [{**b, "text": {"p69": "공동(기업명 작성) : 한국선급 목표", "p70": "채운 줄"}.get(b["id"], b.get("text"))} if b["type"] == "paragraph" else b for b in BOX44["cells"][0]["blocks"]])
    orig = {b["id"]: b["text"] for b in BOX44["cells"][0]["blocks"] if b["type"] == "paragraph"}
    ents, chs = _chunks(filled, orig=orig)
    by = {e["id"]: e for e in ents}
    assert (by["p69"]["kind"], by["p69"]["was"], by["p70"]["kind"], by["p70"]["was"], by["p71"]["kind"]) == ("filled", "label", "filled", "blank", "blank")
    c69 = next(c for c in chs if c["head"]["id"] == "p69")
    assert [e["id"] for e in c69["slots"]] == ["p71"]                                             # 채운 머리는 덩이의 머리로 남고 · 채운 줄은 자리가 아니며 · 그 아래 빈 줄은 같은 덩이의 자리다
    tg = FS.targets(chs)
    assert "p69" not in tg and "p70" not in tg and tg["p71"]["chunk"] == c69["no"] and "p75" in tg
    # 같은 이름의 자리 둘 가운데 하나를 채워도 「같은 이름」 은 그대로다 — 남은 자리가 누구의 것인지는 여전히 사람이 정한다(astra 2차 G5)
    assert c69["dup"] == [1, 2] and next(c for c in chs if c["head"]["id"] == "p75")["dup"] == [2, 2]
    plain, _ = _chunks(filled)                                                                    # 올린 원본을 모르면 가리지 않는다
    assert {e["id"]: e["kind"] for e in plain}["p69"] == "text" and "was" not in plain[10]
    assert FS.line_slot(para("h", "■ 과제명 : ")) == "label" and FS.line_slot(para("h", CHECK)) == "check" and FS.line_slot(para("h", "1. 개요")) is None and FS.line_slot(table("t")) is None
    assert FS.line_slot(para("h", "■ 과제명 : 값"), "■ 과제명 : ") == "filled" and FS.line_slot(para("h", "■ 과제명 : 값")) is None
    assert FS.line_slot(para("h", CHECK.replace("□ 연차", "■ 연차")), CHECK) == "filled" and FS.line_slot(para("h", "1. 개요 고침"), "1. 개요") is None


def test_view_text_marks_only_real_slots():
    ents, _ = _chunks(BOX44)
    lines = FS.view_text(ents).splitlines()
    assert lines[0] == "  (빈 줄 1)"                                                               # 머리 없는 앞쪽 빈 줄 — id 도 「쓸 자리」 도 없다
    assert "  [p50] 「  : 」 (쓸 자리 — 글머리 줄)" in lines and "  [p51 p52] (쓸 자리 — 빈 줄 2 · L1)" in lines   # 빈 줄 묶음은 id 를 모두 · 원문의 앞 빈칸 그대로
    assert "  [p69] (L4) 「공동(기업명 작성) : 」 (쓸 자리 — 같은 줄 뒤에 값)" in lines and "  [p70 p71] (쓸 자리 — 빈 줄 2 · L1)" in lines and "  [p76 p77] (쓸 자리 — 빈 줄 2)" in lines
    assert "  [표 t55 2×3 — 표 · 그림 자리: 여기서는 채우지 않습니다]" in lines and lines[lines.index("  [표 t55 2×3 — 표 · 그림 자리: 여기서는 채우지 않습니다]") + 1] == "  (빈 줄 1)"   # 안쪽 표 뒤의 빈 줄
    assert "  [p68] 「그림 1 n차년도 연구개발 성과명」 (캡션 — 채우지 않음)" in lines and "  [p47] 「< 연구개발 과제명 작성 >」" in lines
    ents, _ = _chunks(BOX97)
    text = FS.view_text(ents)
    assert "  [p100] 「※ 최종보고서 제출 기관은 작성하지 않으셔도 됩니다.」 (안내 — 채우지 않음)" in text and "  [p103] (L4) 「000」\n  [p104] (L5) 「    - 」 (쓸 자리 — 글머리 줄)\n  [p105] (쓸 자리 — 빈 줄 1 · L4)" in text
    orig = {b["id"]: b["text"] for b in BOX97["cells"][0]["blocks"] if b["type"] == "paragraph"}
    again = box("t97", [{**b, "text": "    - 채운 목표"} if b["id"] == "p104" else b for b in BOX97["cells"][0]["blocks"]])
    assert "  [p104] (L5) 「    - 채운 목표」 (이미 채움 — 다시 쓰지 않음)" in FS.view_text(FS.entries(FS.box_cell(again), LEVELS, orig))
    long = FS.view_text([{"id": "p1", "raw": "가" * 300, "kind": "text", "level": None}])
    assert len(long) < 220 and long.endswith("…」")


def test_view_text_only_marks_closed_slots():
    """이번 턴에 쓸 수 있는 문단(only)만 「쓸 자리」 로 적는다 — 사람이 고르지 않은 같은 이름 자리는 「이번에는 쓰지 않는 자리」 이고 빈 줄의 id 도 싣지 않는다(2026-11-24 실제 실행: LLM 이 고르지 않은 「공동」 자리에 써서 줄이 모두 버려졌다)."""
    P = lambda i, t: {"id": i, "type": "paragraph", "text": t}  # noqa: E731
    ents = FS.entries({"blocks": [P("a", "공동(기업명 작성) : "), P("a1", ""), P("a2", ""), P("b", "공동(기업명 작성) : "), P("b1", ""), P("b2", "    - ")]})
    text = FS.view_text(ents, only={"b", "b1", "b2"})
    assert "[a] 「공동(기업명 작성) : 」 (이번에는 쓰지 않는 자리)" in text and "[a1" not in text and "(이번에는 쓰지 않는 자리 — 빈 줄 2)" in text
    assert "[b] 「공동(기업명 작성) : 」 (쓸 자리 — 같은 줄 뒤에 값)" in text and "[b1] (쓸 자리 — 빈 줄 1)" in text and "[b2] 「    - 」 (쓸 자리 — 글머리 줄)" in text
    assert FS.view_text(ents) == FS.view_text(ents, only=None) and "이번에는" not in FS.view_text(ents)


def test_round3_counterexamples():
    """astra 3차의 반례 — 표시 줄의 선택지 · 글머리 줄의 길이 · 윗 제목을 채워도 풀리지 않는 같은 이름 자리."""
    k, j = FS.kind_of, FS.judge
    # 선택지 이름의 괄호는 이름의 것이다 — 「승인」 과 「미승인」 이 같은 이름으로 잘리지 않는다
    line = "■ 승인 구분 ( □ 정규(형식) 승인 □ 정규(형식) 미승인 □ 기타 )"
    assert j(line, line.replace("□ 정규(형식) 미승인", "■ 정규(형식) 미승인")) == ("check", "정규(형식) 미승인") and j(line, line.replace("□ 기타", "■ 기타")) == ("check", "기타")
    # 첫 기호부터 선택지인 줄(제목 없음) — 첫 ■ 는 글머리가 아니라 이미 한 표시다
    assert k("  ■ 연차 □ 최종 □ 기타") == "check" and "이미 표시" in j("  ■ 연차 □ 최종 □ 기타", "  ■ 연차 ■ 최종 □ 기타")
    assert "이미 표시" in j("구분 ( ☒ 연차 □ 최종 □ 기타 )", "구분 ( ☒ 연차 ■ 최종 □ 기타 )")           # ☒ 도 표시
    assert k("■ 항목 □ 하나") == "text"                                                                  # 표시할 □ 가 하나뿐 — 표시 줄이 아니다
    # 글머리 줄 = 글머리 둘까지 — 구분선 · 기호 줄은 쓸 자리가 아니다
    assert [k("------"), k("■ □ ▷"), k("- :"), k("o")] == ["text", "text", "stub", "stub"]
    # 윗 제목(L1 「연차:」)을 채워도 그 아래의 같은 이름 자리(L2 「공동:」)는 여전히 같은 이름이다
    P = lambda i, t: {"id": i, "type": "paragraph", "text": t}  # noqa: E731
    cell = {"blocks": [P("y1", "연차: 1차년도"), P("a", "공동: "), P("a1", ""), P("y2", "연차: "), P("b", "공동: "), P("b1", "")]}
    lv, orig = {"y1": 1, "a": 2, "y2": 1, "b": 2}, {"y1": "연차: ", "a": "공동: ", "a1": "", "y2": "연차: ", "b": "공동: ", "b1": ""}
    chs = FS.chunks(FS.entries(cell, lv, orig))
    assert [c["dup"] for c in chs if c["head"]["id"] in ("a", "b")] == [[1, 2], [2, 2]]
