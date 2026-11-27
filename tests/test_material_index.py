"""자료의 절 색인 · 근거 위치(app/material_index.py — spec_양식작성 ② §5-12 2~5)."""
from app import material_index as MI

MD = """머리말 한 줄

<!-- p.12 -->
# 1. 연구개발과제의 개요

## 총괄 목표

주관기관은 12kV급 직류 차단기 보호협조 검증을 한다.

<!-- p.46 -->
# 3. 연구개발 내용

## 3-2. 한국선급(1차년도)

보호협조 시험 절차서(안) 검토 및 위험도 식별 8건.

<!-- p.88 -->
# 4. 차년도 계획

## 4-2. 한국선급(2차년도 계획)

실선 적용 안전성 평가 기준(안) 제정 및 검증 시험 12건.
"""


def _mat(text=MD, mid="m0000000a", name="계획서.md"):
    return {"id": mid, "name": name, "text": text}


def test_sections_follow_headings_and_pages():
    secs = MI.sections(MD)
    titles = [s["title"] for s in secs]
    assert titles == ["", "1. 연구개발과제의 개요", "총괄 목표", "3. 연구개발 내용", "3-2. 한국선급(1차년도)", "4. 차년도 계획", "4-2. 한국선급(2차년도 계획)"]
    by = {s["title"]: s for s in secs}
    assert by["총괄 목표"]["path"] == ["1. 연구개발과제의 개요"] and by["총괄 목표"]["page"] == 12
    assert by["3-2. 한국선급(1차년도)"]["page"] == 46 and by["4-2. 한국선급(2차년도 계획)"]["page"] == 88
    assert by[""]["page"] == 12   # 쪽 표시가 뒤에 처음 나오는 머리말 — 그 절 안의 첫 쪽
    assert [s["id"] for s in secs] == [f"s{i}" for i in range(1, 8)]
    assert all(MD[s["start"]:s["end"]].strip() for s in secs)
    assert secs[0]["start"] == 0 and secs[-1]["end"] == len(MD)


def test_sections_split_long_and_plain_text():
    para = "가나다라마바사 " * 100   # 800자
    plain = "\n\n".join([para] * 6)
    secs = MI.sections(plain)
    assert len(secs) >= 2 and all(s["end"] - s["start"] <= MI.SEC_MAX + 2 for s in secs)
    assert "".join(plain[s["start"]:s["end"]] for s in secs) == plain   # 빠지는 글자 없이 이어진다
    one = "긴줄" * 4000   # 빈 줄이 없는 긴 덩이는 한 조각
    assert len(MI.sections(one)) == 1
    assert MI.sections("") == () and MI.sections("  \n ") == ()


def test_heading_inside_code_fence_is_not_a_section():
    text = "# 가\n\n```\n# 주석\n```\n\n# 나\n글"
    assert [s["title"] for s in MI.sections(text)] == ["가", "나"]


def test_locate_gives_place_and_counts_hits():
    got = MI.locate("보호협조 시험 절차서(안) 검토", [_mat()])
    assert got["mat"] == "m0000000a" and got["page"] == 46 and got["title"] == "3-2. 한국선급(1차년도)" and got["hits"] == 1
    assert MD[got["start"]:got["end"]] == "보호협조 시험 절차서(안) 검토"
    spaced = MI.locate("보호협조시험   절차서(안)검토", [_mat()])   # 공백을 접은 견줌
    assert (spaced["start"], spaced["end"]) == (got["start"], got["end"])
    assert MI.locate("없는 구절입니다", [_mat()]) is None and MI.locate("가", [_mat()]) is None


def test_locate_same_quote_twice_reports_hits_and_prefers_planned_section():
    two = MI.locate("한국선급", [_mat()])
    assert two["hits"] == 2 and two["title"] == "3-2. 한국선급(1차년도)"   # 첫 자리 — hits 로 알린다(확정 아님)
    later = MI.sections(MD)[-1]["id"]
    liked = MI.locate("한국선급", [_mat()], prefer=[{"mat": "m0000000a", "sec": later}])
    assert liked["sec"] == later and liked["hits"] == 2
    across = MI.locate("12kV급", [_mat(mid="m0000000b", name="둘째", text="다른 글"), _mat()])
    assert across["mat"] == "m0000000a" and across["hits"] == 1


def test_marked_and_narrow_keep_section_headers():
    m = _mat()
    secs = MI.sections(MD)
    full = MI.marked(m)
    assert full.count("[[m0000000a/") == len(secs) and "| p.46 | 3. 연구개발 내용 › 3-2. 한국선급(1차년도)]]" in full
    target = next(s for s in secs if s["title"].startswith("3-2"))
    got = MI.narrow([m], [{"mat": "m0000000a", "sec": target["id"]}, {"mat": "m0000000a", "sec": "s999"}, {"mat": "mffffffff", "sec": "s1"}], cap=60000)
    text = got[0]["text"]
    assert got[0]["narrowed"] and "보호협조 시험 절차서" in text and "실선 적용" not in text.split(MI.NARROW_TOC)[0]   # 근거 절 + 앞뒤 하나씩뿐
    assert "3. 연구개발 내용]]" in text and "4. 차년도 계획]]" in text                                      # 앞뒤 절(near 1)
    assert "4-2. 한국선급(2차년도 계획)" in text.split(MI.NARROW_TOC)[1]                                      # 목차에는 모든 절
    assert MI.narrow([m], [{"mat": "m0000000a", "sec": "s999"}], cap=60000) is None                           # 아는 근거가 없으면 None(자료 전체로)
    assert MI.narrow([m], [], cap=60000) is None


def test_narrow_material_without_evidence_gets_toc_only_and_cap():
    a, b = _mat(), _mat(mid="m0000000b", name="둘째.md", text="# 다른 자료\n\n다른 글")
    got = MI.narrow([a, b], [{"mat": "m0000000a", "sec": "s3"}], cap=60000)
    assert "다른 글" not in got[1]["text"] and "m0000000b/s1" in got[1]["text"]
    small = MI.narrow([a, b], [{"mat": "m0000000a", "sec": "s3"}], cap=200)
    assert sum(len(x["text"]) for x in small) <= 200 and small[0]["cut"]


def test_parse_ref():
    assert MI.parse_ref("m0000000a/s14") == ("m0000000a", "s14")
    assert MI.parse_ref(" m0000000a/s14 ") == ("m0000000a", "s14")
    for bad in ("s14", "m1/s1", "m0000000a/14", "", None, "m0000000a/s1/x"):
        assert MI.parse_ref(bad) is None


def test_field_clash_only_when_both_sides_say_and_disagree():
    assert MI.field_clash("당해연도(1차년도) 연구개발실적 요약", "4. 차년도 계획 › 4-2. 한국선급(2차년도 계획)") == ["차년도 — 자리 1 · 근거 2"]
    assert MI.field_clash("1차년도 실적", "3-2. 한국선급(1차년도)") == []
    assert MI.field_clash("연구개발 목표", "4-2. 한국선급(2차년도 계획)") == []          # 자리가 안 적음 — 모른다
    assert MI.field_clash("2차년도 계획", "1단계(1~2차년도) 추진 내용") == []            # 범위 안
    assert MI.field_clash("1단계 목표", "2단계 추진 계획") == ["단계 — 자리 1 · 근거 2"]
    assert MI.field_clash("2025년 실적", "2024년 추진 실적") == ["연도 — 자리 2025 · 근거 2024"]
    assert MI.field_tokens("3-2단계") == {"단계": {2}}                                  # 「3-2」 는 범위가 아니다


def test_scan_edges_crlf_fences_heading_pages_and_page_marks_are_not_text():
    """astra R2: 줄 끝의 CR · ~~~ 울타리 · 헤딩 줄에 붙은 쪽 표시 · 쪽 표시는 자료의 글이 아니다."""
    assert [s["title"] for s in MI.sections("# 가\r\n글\r\n# 나\r\n끝")] == ["가", "나"]
    assert [s["title"] for s in MI.sections("# 가\n\n~~~\n# 예시\n~~~\n\n````\n# 또 예시\n<!-- p.99 -->\n````\n\n# 나\n글")] == ["가", "나"]
    two = MI.sections("# 가 <!-- p.1 -->\n글 하나\n# 나 <!-- p.2 -->\n글 둘")
    assert [(s["title"], s["page"]) for s in two] == [("가", 1), ("나", 2)]   # 헤딩 줄에 붙은 쪽 표시가 그 절의 쪽(앞 절의 쪽이 아니다)
    over = "# 가 <!-- p.1 -->\n앞 글\n<!-- p.2 -->\n뒤 글의 구절"
    assert MI.locate("뒤 글의 구절", [{"id": "m0000000a", "name": "", "text": over}])["page"] == 2   # 절이 쪽을 넘어가면 그 구절이 놓인 쪽
    assert MI.find_all("<!-- p.46 -->", MD) == [] and MI.find_all("p.46", MD) == [] and MI.find_all("46", MD) == []   # 쪽 표시의 글은 근거 구절이 못 된다
    assert MI.sections("<!-- p.3 -->\n# 가\n글")[0]["title"] == "가"                                                   # 쪽 표시뿐인 앞머리는 절이 아니다
    assert MI.find_all("ΟΣ", "가 ΟΣ 나") == [(2, 4)]                                                                    # 구절과 자료를 같은 접기로(끝 시그마)


def test_narrow_reports_what_was_really_sent_and_field_tokens_edges():
    m = _mat()
    secs = MI.sections(MD)
    target = next(s for s in secs if s["title"].startswith("3-2"))
    got = MI.narrow([m], [{"mat": "m0000000a", "sec": target["id"]}], cap=60000)[0]
    assert target["id"] in got["secs"] and len(got["secs"]) == 3 and (target["start"], target["end"]) in got["spans"]
    spot = MI.locate("위험도 식별", [m])
    assert MI.inside(spot, {"m0000000a": got["spans"]}) and not MI.inside(MI.locate("실선 적용", [m]), {"m0000000a": got["spans"]})
    tight = MI.narrow([m], [{"mat": "m0000000a", "sec": target["id"]}], cap=len(MI.NARROW_HEAD) + 40)[0]   # 근거 절이 안 들어가는 분량 — 실었다고 적지 않는다
    assert tight["secs"] == [] and tight["spans"] == [] and tight["cut"]
    assert MI.field_tokens("2025년 차세대 사업") == {"연도": {2025}}          # 「25년 차」 를 차년도로 읽지 않는다
    assert MI.field_tokens("1·2차년도 실적") == {"차년도": {1, 2}} and MI.field_tokens("3.2차년도") == {} and MI.field_tokens("2년차 계획") == {"차년도": {2}}
    assert MI.field_clash("1차년도 실적", "2차년도 검증 완료 12건", "시험 실적", "") == ["차년도 — 자리 1 · 근거 2"]   # 가까운 글(근거 구절)이 먼저
    assert MI.field_clash("1차년도 실적", "검증 완료 12건", "2차년도", "1~2차년도 추진") == ["차년도 — 자리 1 · 근거 2"]   # 윗 제목이 넓어도 그 절이 2차년도면 2
    assert MI.field_clash("1차년도 실적", "검증 완료 12건", "추진 내용", "1~2차년도 추진") == []


def test_excerpt_cuts_at_line_boundaries():
    got = MI.locate("위험도 식별", [_mat()])
    ex = MI.excerpt(MD, got["start"], got["end"], around=10)
    assert ex["hit"] == "위험도 식별" and (ex["before"] + ex["hit"] + ex["after"]) == MD[ex["from"]:ex["to"]]
    assert ex["from"] == 0 or MD[ex["from"] - 1] == "\n"
    whole = MI.excerpt(MD, got["start"], got["end"], around=10 ** 6)
    assert whole["from"] == 0 and whole["to"] == len(MD)
