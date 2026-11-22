"""매칭 지침 — 표 · 본문별(spec_병합 ② §5-6 · app/link_guides.py): 양식 정보 「자리 연결」 절의 글을 지침 하나하나로 읽고 · 그 자리에 걸린 것을 찾고 · 더하고 · 고치고 · 지운다(순수 함수 — 파일을 안 쓴다)."""
from pathlib import Path

import pytest

from app import heading_forms as HF
from app import link_guides as LG

RAW = """# 양식 정보 — 시험

```json
{"name": "시험", "match": {"names": ["*시험*"]}}
```

## 구분 기준 자리 — 값마다 늘리고 줄이는 곳

- **표가 아닌 절의 굵은 글** 은 지침이 아니다.

## 자리 연결 — 다른 문서에서 내용을 받는 자리
<!-- 주석 안의
- **「주석 안의 줄」** 은 안 읽는다 -->

표:
- **「2-1. 기술개발 추진 일정」 표** ← 계획서의 **같은 차년도** 일정 표.
  계획 선과 실적 선을 같게 긋는다.
- **2-2 「< 성능 목표 및 실적 >」 표** ← 최종목표의 표.

단락:
- **「1. 연구개발과제의 개요 ※ 2page 이내 요약 작성」** ← 계획서 1장. 서식이 달라도 잇는다.

코멘트 — 화면에서 남긴 것(새 것이 아래):
- (2026-11-12) **굵게 쓴 코멘트** 는 지침이 아니다.
"""


def test_entries_read_the_section_per_place():
    """지침 = 「자리 연결」 절의 `- **자리** 글` 줄(이어지는 줄은 들여 쓴 줄) — 묶음 머리(표: · 단락:/본문:)가 종류 · 굵은 글 안의 「…」 가 자리의 제목. 다른 절 · HTML 주석 · 코멘트 목록은 안 읽는다."""
    es = LG.entries(RAW)
    assert [(e["n"], e["kind"], e["title"]) for e in es] == [(0, "table", "2-1. 기술개발 추진 일정"), (1, "table", "< 성능 목표 및 실적 >"), (2, "body", "1. 연구개발과제의 개요 ※ 2page 이내 요약 작성")]
    assert "실적 선을 같게" in es[0]["text"] and es[0]["text"].startswith("←")   # 이어지는 줄까지 한 글
    assert [e["pages"] for e in es] == [None, None, 2]
    assert LG.entries("") == [] and LG.entries("# 제목\n\n## 표\n- **「가」** 나\n") == []   # 절이 없으면 지침도 없다
    assert (LG.pages("※ 2page 이내 요약 작성"), LG.pages("3쪽 이내"), LG.pages("5 페이지 이하"), LG.pages("2026년 2차년도")) == (2, 3, 5, None)


def test_match_finds_the_guides_of_a_place():
    """그 자리(제목 · 위 제목들의 글)에 걸린 지침 — 글자 · 숫자만 견준다. 한쪽이 다른 쪽을 품으면 같은 자리(문서 정리가 「※ 2page 이내 요약 작성」 을 지운 제목도). 짧은 글은 아무 데나 맞지 않는다."""
    es = LG.entries(RAW)
    hit = lambda texts, kind=None: [e["n"] for e in LG.match(es, texts, kind)]  # noqa: E731
    assert hit(["  2-1. 기술개발 추진 일정"]) == [0] and hit(["2-1. 기술개발 추진 일정"], "body") == []
    assert hit(["2. 해당연도 수행 내용", "< 성능 목표 및 실적 >"], "table") == [1]
    assert hit(["1. 연구개발과제의 개요 ※ 2page 이내 요약 작성", "o 연구개발기술의 정의 및 범위"], "body") == [2]
    assert hit(["1. 연구개발과제의 개요"], "body") == [2]   # 안내 글이 지워진 뒤의 제목
    assert hit(["개요"]) == [] and hit(["3-1. 정성적 연구개발성과"]) == [] and LG.match(None, ["가"]) == []


def test_put_and_drop_rewrite_only_that_entry():
    """더하기 = 그 종류의 묶음 끝에 · 고치기 = 그 지침의 줄만 · 지우기 = 그 지침의 줄만 — 절의 다른 글(주석 · 코멘트 · 다른 절)은 그대로다. 종류를 바꾸면 그 종류의 묶음으로 옮긴다."""
    added = LG.put(RAW, "body", "3-1. 정성적 연구개발성과", "계획서에 없는 내용 — 비워 둔다.\n기관이 작성한다.")
    es = LG.entries(added)
    assert [(e["kind"], e["title"]) for e in es][-1] == ("body", "3-1. 정성적 연구개발성과") and es[-1]["text"] == "계획서에 없는 내용 — 비워 둔다. 기관이 작성한다."
    assert HF.comments(added, HF.LINK_SECTION) == HF.comments(RAW, HF.LINK_SECTION) and added.count("주석 안의 줄") == 1 and "## 구분 기준 자리" in added
    assert added.index("3-1. 정성적") < added.index("코멘트 —")   # 코멘트 목록 앞
    edited = LG.put(added, "table", "2-1. 기술개발 추진 일정", "새 글", n=0)
    assert LG.entries(edited)[0]["text"] == "새 글" and "실적 선을 같게" not in edited and len(LG.entries(edited)) == 4
    moved = LG.put(edited, "body", "2-1. 기술개발 추진 일정", "본문으로", n=0)
    assert [(e["kind"], e["title"]) for e in LG.entries(moved)] == [("table", "< 성능 목표 및 실적 >"), ("body", "1. 연구개발과제의 개요 ※ 2page 이내 요약 작성"),
                                                                     ("body", "3-1. 정성적 연구개발성과"), ("body", "2-1. 기술개발 추진 일정")]
    gone = LG.drop(RAW, 1)
    assert [e["title"] for e in LG.entries(gone)] == ["2-1. 기술개발 추진 일정", "1. 연구개발과제의 개요 ※ 2page 이내 요약 작성"] and "성능 목표" not in gone
    with pytest.raises(ValueError):
        LG.drop(RAW, 9)
    with pytest.raises(ValueError):
        LG.put(RAW, "body", "제목", "  ")
    with pytest.raises(ValueError):
        LG.put(RAW, "cell", "제목", "글")


def test_put_makes_the_section_and_group_when_missing():
    """절이 없으면 글 끝에 절을 만들고(heading_forms.LINK_TITLE), 그 종류의 묶음이 없으면 코멘트 목록 앞에 묶음 머리부터 더한다. 만든 글은 다시 읽힌다."""
    made = LG.put("# 양식 정보 — 새 양식\n", "table", "표 제목", "원본의 같은 표에서")
    assert f"## {HF.LINK_TITLE}" in made and [(e["kind"], e["title"], e["text"]) for e in LG.entries(made)] == [("table", "표 제목", "원본의 같은 표에서")]
    only = "# 가\n\n## 자리 연결 — 받는 자리\n\n코멘트 — 화면에서 남긴 것(새 것이 아래):\n- (2026-11-12) 코멘트\n"
    both = LG.put(LG.put(only, "body", "1. 개요", "요약 자리"), "table", "일정 표", "같은 차년도")
    assert [(e["kind"], e["title"]) for e in LG.entries(both)] == [("body", "1. 개요"), ("table", "일정 표")] and HF.comments(both, HF.LINK_SECTION) == [{"date": "2026-11-12", "text": "코멘트"}]
    assert both.index("일정 표") < both.index("코멘트 —")


def test_repository_form_has_the_guides_the_review_reads():
    """저장소의 연차보고서 양식 정보 — 「1. 개요」 본문 지침에 쪽 한도(2)가 읽히고, 「2-1. 기술개발 추진 일정」 표 지침이 있다(빈 자리 검토 · 표 대응 · 자리 연결 LLM 검토가 그 자리에서 읽는 글 — spec_병합 ② §5-6 · §5-7)."""
    es = LG.entries((Path(__file__).parents[1] / "forms" / "연차보고서.md").read_text(encoding="utf-8"))
    body = LG.match(es, ["1. 연구개발과제의 개요 ※ 2page 이내 요약 작성"], "body")
    assert body and body[0]["pages"] == 2
    sched = LG.match(es, ["2-1. 기술개발 추진 일정"], "table")
    assert sched and "차년도" in sched[0]["text"] and "개발실적" in sched[0]["text"]
