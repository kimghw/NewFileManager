"""헤딩 추출 2단계 — **이름표 띠 표**(spec_헤딩_추출 ② §6 「띠 표 줄」): 「별첨2 | 시약·재료구입 및 활용계획서」 처럼 **이름표 칸**(별첨N · 부록N · 붙임N · 별지 · 별표 ·
Appendix · Annex …)과 제목 칸으로 된 본문의 1행 표를 찾는다. 문서를 바꾸지 않는다 — 1단계 레코드만 읽는다.

2026-11-17 사용자 "테이블도 헤딩레벨로 간주할 수 있도록 해달라는 거였거든, 별첨, 부록 appendix 이런게 … 지금 템플릿 문서 구조상에서는 잡히질 않아" →
답 「제 템플릿으로」(「별첨N」 이 레터인 따로 선 템플릿의 L1 — 문서 맨 위에서 장들과 나란히 · 그 아래 줄은 그 별첨 아래로) · 「헤딩 추출이 스스로」.
(그 전: 2026-11-09 "여기서 별첨은 왜 헤딩 그래프에 포함되지 않냐?" — 칸 안의 레터 없는 글은 헤딩 후보가 아니라 노드가 없었다.)

- **이름표** = 이름말(별첨 · 부록 · 붙임 · 별지 · 별표 · 첨부 · Appendix · Annex · Attachment · Exhibit) + 번호(없어도 된다 — 「별첨」) — 괄호로 싸도 같다(「[별첨 1]」).
  정규 키 = 이름말 + 번호의 갈래(숫자 N · 로마자·라틴 글자 A · 한글 가): 「별첨N」 · 「부록A」 · 「AppendixA」. 이름말이 다르면 키가 다르다(레터가 다르면 다른 템플릿).
- **띠 표** = 본문(구역 바로 아래 — 칸 안 표 · 글상자 · 머리말의 표는 아님)의 **1행 · 2~6칸** 표이고, 칸 안에 개체(표 · 그림)가 없으며, 글 있는 칸이 **이름표 칸 하나**(글 문단 하나에 이름표만)
  이거나 **이름표 칸 + 제목 칸**(글 합 200자까지)인 것. 글 있는 칸이 셋 이상이면 자료 표다.
- 줄의 열쇠는 **이름표 문단**이다(「별첨2」 문단 — 레터가 그 문단의 글 그대로라 살아 있는지 견주기 쉽고, 제목 칸의 글이 대괄호 줄이어서 이미 노드인 「[해당 기관별 작성] …」 과 겹치지 않는다).
- 그래프(`heading_graph`)는 이 줄을 kind `band` 의 본문 흐름 노드로 넣는다 — 부모는 늘 문서 맨 위 · 그 아래 줄은 다음 띠 표나 주 사슬 첫 레터(장)가 올 때까지 그 줄의 자식 ·
  템플릿 사슬에는 투명하다(자식의 템플릿·레벨은 문서 맨 위에 매달린 줄처럼 정한다 — 띠 표 템플릿은 L1 하나뿐). 오버레이(`outline_edit.build_overlay`)는 표 줄(role table)로 둔다.
"""
import re
from collections import defaultdict

KIND = "band"      # 후보 노드·유형·템플릿의 kind
CELLS_MAX = 6      # 띠 표의 칸 수 — 이보다 많으면 자료 표
NAME_MAX = 24      # 이름표 글 길이
TITLE_MAX = 200    # 제목 칸의 글 합 — 이보다 길면 본문을 담은 표

_KO = "별첨|부록|붙임|별지|별표|첨부"
_EN = "appendix|annexure|annex|attachment|exhibit"
_NO = r"(?:제\s*)?(?P<no>\d{1,3}(?:\s*[-.]\s*\d{1,2})?|[A-Za-z]|[가나다라마바사아자차카타파하]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+|[IVXivx]{2,4})"
NAME = re.compile(rf"[\[【<〈《(（]?\s*(?P<word>{_KO}|{_EN})\s*(?:{_NO}\s*(?:호\s*(?:서식)?)?)?\s*[\]】>〉》)）]?\s*[.:]?", re.I)
_KEY = re.compile(rf"(?:{_KO}|{_EN})(?:N(?:-N)?|A|가)?", re.I)


def name_of(text):
    """이름표 글 → (이름표 글(앞뒤 빈칸 뺌), 정규 키) | None. 「별첨2」 → ("별첨2", "별첨N") · 「[부록 A]」 → ("[부록 A]", "부록A") · 「Appendix II.」 → (…, "AppendixA")."""
    s = (text or "").strip()
    if not s or len(s) > NAME_MAX:
        return None
    m = NAME.fullmatch(s)
    if m is None:
        return None
    word, no = m.group("word"), (m.group("no") or "").strip()
    word = word.capitalize() if word.isascii() else word
    if not no:
        cls = ""
    elif no[0].isdigit():
        cls = "N-N" if re.search(r"[-.]", no) else "N"
    elif no[0] in "가나다라마바사아자차카타파하":
        cls = "가"
    else:
        cls = "A"  # 라틴 글자 · 로마자(「Appendix I」 은 글자인지 로마자인지 가를 수 없다 — 한 갈래로)
    return s, word + cls


def is_key(key):
    """정규 레터 키가 이름표 키인가(「별첨N」 · 「부록A」 · 「Appendix」) — 띠 표 템플릿을 가린다."""
    return bool(key) and _KEY.fullmatch(key) is not None


def find(paras, skip=()):
    """1단계 문단 레코드 → {이름표 문단 id: {table, host, cell, letter(이름표 글), key(정규 키), title(제목 문단 id | None), titleCell, text(제목 글)}}.
    skip = 후보에서 뺄 문단 id(TEMP — 그 문단이 든 표는 띠 표가 아니다)."""
    tables = defaultdict(list)
    for rec in paras:
        path = rec.get("path") or []
        if len(path) == 2 and path[0].get("t") == "tbl" and path[1].get("t") == "cell" and path[0].get("id") and path[0].get("rows") == 1 \
                and 2 <= int(path[0].get("cells") or 0) <= CELLS_MAX:
            tables[path[0]["id"]].append(rec)
    out = {}
    for tid, recs in tables.items():
        if any(r["id"] in skip or r.get("objects") for r in recs):
            continue
        cells = defaultdict(list)  # 칸 → 글 있는 문단(문서 순)
        for r in recs:
            if (r.get("text") or "").strip():
                cells[r["path"][1].get("id") or r.get("cell")].append(r)
        if not 1 <= len(cells) <= 2:
            continue
        named = [(cid, rs[0], name_of(rs[0]["text"])) for cid, rs in cells.items() if len(rs) == 1]
        named = [x for x in named if x[2] is not None]
        if len(named) != 1:  # 이름표 칸이 없거나 둘(「별첨1 | 별첨2」 — 제목 띠가 아니다)
            continue
        cid, rec, (letter, key) = named[0]
        rest = [rs for c, rs in cells.items() if c != cid]
        title = rest[0][0] if rest else None
        if rest and sum(len(r["text"].strip()) for r in rest[0]) > TITLE_MAX:
            continue
        out[rec["id"]] = {"table": tid, "host": rec["path"][0].get("host"), "cell": cid, "letter": letter, "key": key,
                          "title": title["id"] if title else None, "titleCell": (title["path"][1].get("id") if title else None),
                          "text": " ".join(title["text"].split()) if title else ""}
    return out
