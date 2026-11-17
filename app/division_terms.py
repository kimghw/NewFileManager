"""구분 기준 값의 글 꼴 — 구분 기준 판독(division_scan)과 헤딩 추출(heading_graph)이 함께 쓰는 엄격한 괄호 줄 꼴(spec_구분_기준 ② §23 「보완」 · spec_헤딩_추출 ② §13).
2026-11-18 사용자 "혹시 헤딩추출할때 이 구분기준을 찾는 스크립트가 있다면 구분기준 스크립트를 보완해 주고" — 헤딩 추출 안에 있던 `value_basis` 를 구분 기준 쪽(이 모듈)으로 옮기고
헤딩 추출은 여기서 가져다 쓴다(Fable 협의: 판독 모듈이 무거운 헤딩 모듈을 import 하지 않게). import 없음(re 만).
"""
import re

BASES = ("단계", "차년도", "기관")  # 기본 구분 기준(구분 순서 — 바깥 → 안) — 사용자가 더한 이름이 뒤에 붙는다(heading_graph.bases_of)
BASIS_SEP = "-"  # 겹친 구분 기준 이름을 잇는 글자(「단계-차년도」) — 구분 순서(바깥 → 안)대로
BRACKETS = {"[": "]", "【": "】", "<": ">", "〈": "〉", "《": "》"}
NUM = r"(?:\d{1,2}|[nNxX])"
V_SEP = re.compile(r"[\s\-–~·․⋅,/]*")
V_TERMS = (("단계", re.compile(rf"(?:제\s*)?{NUM}\s*단\s*계")), ("차년도", re.compile(rf"(?:제\s*)?{NUM}\s*(?:차\s*년\s*도|년\s*차|연\s*차)")),
           ("기관", re.compile(rf"(?:주관|공동|위탁|참여|협동|국외|해외)\s*(?:연구\s*개발\s*)?기관\s*{NUM}?")))
V_ORG_EACH = re.compile(r"(?:해당\s*)?기관\s*별")  # 「[해당 기관별 작성]」 — 기관마다 따로 쓰는 자리(사용자 2026-11-10 「해당기관별 … 기준라벨로」)
V_ORG_TAIL = re.compile(r"\s*(?:[(（:：].*)?")  # 기관 값 뒤 = 끝이거나 이름 자리(「(기관명 기입)」「 : 기업명1」) — 「… 기관 현황」 같은 주제 글은 아님


def inner(letter):
    """괄호 줄 레터의 안 글(괄호 한 겹을 벗김) — 괄호 꼴이 아니면 그대로."""
    s = (letter or "").strip()
    return s[1:-1].strip() if len(s) >= 2 and BRACKETS.get(s[0]) == s[-1] else s


def label_shape(letter):
    """대괄호 줄의 꼴 — 숫자를 N 으로(「[1차년도 목표]」 → 「[N차년도 목표]」). 헤딩 유형 표의 shape 이자 라벨 지정(hints)의 단위."""
    return re.sub(r"\d+", "N", (letter or "").strip())


def value_basis(letter):
    """괄호 줄의 글이 **구분 기준 값으로 시작하는 꼴**이면 그 구분 기준 이름 — 「단계」·「차년도」·「기관」, 겹치면 구분 순서대로 이은 「단계-차년도」 | ""(스크립트로는 확정 못 함).
    확정하는 꼴만(헤딩용 — 표 칸 후보를 넓게 찾는 heading_calc.label_basis 와 다르다, astra 2026-11-10): 「N단계 …」·「N차년도 …」(뒤 글은 자유 — 「[1단계(2027~2029) 목표]」
    「[1차년도목표]」) · 「주관|공동|위탁|참여|협동|국외|해외 (연구개발)기관(번호)」 뒤가 끝이거나 이름 자리(「[주관연구개발기관(기관명 기입)]」「[주관연구개발기관 : 기업명1]」) ·
    「(해당) 기관별 …」. 기관이라는 낱말이 든 주제 제목(「[연구개발기관의 안전관리 계획]」)·이름만 있는 글(「[한국선급]」)은 확정하지 않는다(LLM·사용자 지정 몫)."""
    s = inner(letter)
    found, pos = [], 0
    while True:
        p = V_SEP.match(s, pos).end()
        m = next(((name, pat.match(s, p)) for name, pat in V_TERMS if name not in found and pat.match(s, p)), None)
        if m is None:
            break
        found.append(m[0])
        pos = m[1].end()
    if found and found[-1] == "기관" and not V_ORG_TAIL.fullmatch(s, pos):
        found.pop()  # 기관 값 뒤에 주제 글이 이어짐(「[주관연구개발기관 현황]」)
    if not found and V_ORG_EACH.match(s):
        found = ["기관"]
    return BASIS_SEP.join(n for n in BASES if n in found)
