"""줄 안의 빈 자리 채우기(spec_병합 ② §5-13 · app/merge_inline.py) — 순수 계산: 빈 자리 찾기 · 같은 라벨의 값 · 짝지은 줄의 값 · 안 넣는 것(날짜 줄 · 모호한 라벨 · 긴 글)."""
from app import merge_inline as IL

FORM = " 총    천원 (정부지원연구개발비 :  천원, 기관부담 연구개발비 :  천원, \n 지방자치단체지원연구개발비 :    천원)"
SRC = " 총 15,133,337천원 (정부지원연구개발비 : 13,800,000 천원, 기관부담 연구개발비 : 1,333,337 천원)"


def test_slots_labels_and_tails():
    got = [(s["label"], s["tail"], s["colon"]) for ln in FORM.split("\n") for s in IL.slots(ln)]
    assert got == [("총", "천원", False), ("정부지원연구개발비", "천원", True), ("기관부담연구개발비", "천원", True), ("지방자치단체지원연구개발비", "천원", True)]
    assert IL.slots("  들여쓴 글  ") == [] and IL.slots("빈칸 하나 뿐") == []   # 줄 처음 · 끝의 빈칸 · 빈칸 하나는 빈 자리가 아니다
    assert IL.slots("       년        월        일") == []   # 날짜 줄은 보지 않는다
    assert IL.lone("연구책임자:                (서명) ")["label"] == "연구책임자" and IL.lone(FORM.split("\n")[0]) is None   # 빈 자리가 여럿이면 lone 아님


def test_fill_keeps_the_form_and_puts_values_only():
    text, n = IL.fill(FORM, SRC)
    assert n == 3 and text.split("\n")[1] == FORM.split("\n")[1]   # 원본에 없는 라벨(지방자치단체지원연구개발비)은 빈 채로
    assert text.split("\n")[0] == " 총 15,133,337 천원 (정부지원연구개발비 : 13,800,000 천원, 기관부담 연구개발비 : 1,333,337 천원, "
    assert IL.fill(text, SRC) is None   # 다시 — 넣을 것이 없다(남은 빈 자리는 원본에 없는 라벨)
    assert IL.fill(FORM, FORM) is None and IL.fill(FORM, "") is None   # 원본도 빈 서식 · 원본 없음
    assert IL.fill("성명 :    (인)", "성명 : 홍길동 (인) 성명 : 김철수 (인)") is None   # 원본에 같은 라벨이 둘 — 어느 것인지 모른다
    assert IL.fill("성명 :    (인)   성명 :    (인)", "성명 : 홍길동 (인)") is None   # 서식에 같은 라벨의 빈 자리가 둘
    assert IL.fill("기간 :    (월)", "기간 : " + "가" * 50 + " (월)") is None   # 값이 길다 — 한 토막이 아니다
    assert IL.fill("기간 :    (월)", "기간 : 시작: 3 (월)") is None   # 값에 콜론 — 다른 라벨을 넘었다
    assert IL.fill("성명  홍길동", "성명 김철수 과장") is None   # 빈칸 뒤 토큰(꼬리)이 원본의 값 뒤에 없다 — 이미 글이 든 자리는 안 건드린다


def test_fill_at_paired_lines_by_position():
    line = "공동연구개발기관의 장:               (직인) "
    assert IL.fill_at(line, "주관연구개발기관의 장:    박별터     (직인생략)20) ") == "공동연구개발기관의 장:    박별터     (직인) "   # 라벨이 달라도(차례로 짝지은 줄) · 「(직인)」 은 목적 것 그대로
    assert IL.fill_at("연구책임자:                (서명) ", "연구책임자:               조연화   (직인생략)20) ") == "연구책임자:     조연화     (서명) "
    assert IL.fill_at(line, "공동연구개발기관의 장:               (직인) ") is None   # 원본 줄도 비어 있다
    assert IL.fill_at("공동연구개발기관의 장:    박별터     (직인) ", "공동연구개발기관의 장:    박별터     (직인생략)") is None   # 이미 넣은 줄 — 빈 자리가 하나(콜론 뒤)가 아니다
    assert IL.family(line) == "장" == IL.family("주관연구개발기관의 장:    이영석     (직인생략)20)") and IL.family("연구책임자: 조연화") == "연구책임자"
    assert IL.family("콜론이 없는 줄") is None and IL.family("       년        월        일") is None
