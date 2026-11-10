"""국가R&D 프로파일 — 핵심 엔진(FileMergeManager `app/divisions.py` 2026-11-09 사본, spec_구분_기준 ② §9).
구분 기준 자리 찾기(find)·계획(_plan)·반영(apply)·사업기간 날짜 채우기(period_fill)·문서에서 값 읽기(read_values). 양식 정리(cleanup_*)는 뺐다.
NFM 쪽 변경: `app.structure`·`app.tables` 대신 `division_profiles._structure` 심(iter_blocks·index_blocks·bare_bullet·is_footnote).
원본 사양: E:/dev/FileMergeManager/spec/spec_구분_초기화.md ② §1~§3·§8·§9. 아래 원문 주석의 「② §n」 은 그 사양서 절 번호다.

원문 머리말:
구분 초기화 (spec/spec_구분_초기화.md): 연구개발계획서 양식에서 단계·차년도·기관마다 되풀이되는 자리 — 문단 묶음, 표 행
묶음, 표 열 묶음 — 를 찾아 구분 값(단계마다 차년도 수, 기관)에 맞춰 늘리고 줄인다. 양식 정리(작성요령 상자·국외기관 항목·
「연구개발기관 외 기관」 행·위첨자 각주 번호 지우기, ② §7)도 여기.

문서는 어댑터(HwpxDoc/DocxDoc)의 clone_blocks·delete_blocks·clone_rows·delete_rows·clone_cols·delete_cols·set_text 로만
고친다. 블록 id 는 요소에 붙어 편집 뒤에도 그대로라, 한 차례(pass) 안에서 구조를 먼저 바꾸고 글은 끝에 한 번에 고친다."""
import re
from collections import Counter
from datetime import date, timedelta
from itertools import accumulate

from app.division_profiles import _structure as structure
from app import table_grid as grid

FORM = "연구개발계획서"
FORMS = (FORM, "연차보고서", "단계보고서", "최종보고서")   # 양식 이름(② §1) — 「…보고서」(KEIT 1. 서식, 10-30 [fb])는 보고서 자리 규칙(§2·§8)
STAGE, YEAR, STAGE_YEAR, SUB, ORG = "stage", "year", "stageYear", "sub", "org"
RANK = {STAGE: 0, STAGE_YEAR: 0, YEAR: 1, SUB: 2, ORG: 3}   # 구분 순서(바깥 → 안): 단계 > 차년도 > 세부과제 > 기관
DIM_NAME = {STAGE: "단계", YEAR: "차년도", STAGE_YEAR: "단계-차년도", SUB: "세부과제", ORG: "기관"}
N = "N"                      # 자리표시 값(N·n·x — 「끝까지 되풀이」)
LABEL_MAX = 40               # 라벨 글 길이 상한(빈칸 뺌)
FORM_SCAN = 120              # 양식 판정: 앞쪽 블록 수
MAX_STAGES, MAX_YEARS, MAX_TOTAL, MAX_JOINT, MAX_OUTSIDE, MAX_SUBS = 10, 10, 20, 20, 20, 20
# 이름 목록만 받는 기관 — 0곳이면 그 자리를 다 지움(위탁 = 혁신법 별지 1 서식, 10-30 [4f])
EXTRA = {"outside": "연구개발기관 외 기관", "overseas": "국외기관", "entrust": "위탁연구개발기관"}
OVERSEAS_SLOT = "기관명 기입"   # 국외기관·세부과제 라벨 괄호의 양식 자리표시 — 이름 없는 사본에 다시 씀
ORG_COLS = 4   # 7-3 기관 열 표의 기본 열 수(사용자 10-30) — 기관이 더 많으면 열을 늘림(표 너비 그대로)
PASSES = 6

STAGE_RE = re.compile(r"(?<![0-9A-Za-z])(\d+|[Nnx])(\s*단계)")
YEAR_RE = re.compile(r"(?<![0-9A-Za-z])(\d+|[Nnx])(\s*(?:차\s*년도|년차))")
# 「공동연구개발기관N」·「공동연구개발기관명N」(보고서 2-2) — 1 역할 · 2 번호 앞 「명」 · 3 빈칸 · 4 번호 · 5 번호 없는 「명」
ORG_RE = re.compile(r"(주관|공동)연구개발기관(명(?=\s*(?:\d+|[Nn])(?![0-9A-Za-z])))?(?:(\s*)(\d+|[Nn])(?![0-9A-Za-z]))?(명)?")
ROLE_RE = re.compile(r"\((주관|공동)\)")
SUB_RE = re.compile(r"\(\s*세부\s*(\d+|[Nn])\s*\)")   # 세부과제 「(세부1)」·「(세부n)」 — 기관 낱말과 함께여도 세부과제(10-30 [4f])
LEAD_NUM = re.compile(r"^(\s*\(?)(\d+)(?=[.)])")
ECHO_RE = re.compile(r"(?<![0-9A-Za-z])(\d+|[Nn])(?=차(?!\s*년))")
BARE = re.compile(r"^\s*(\d{1,2}|[Nnx])\s*$")
NOTE = re.compile(r"\s*※.*$", re.S)
# 연도 자리 — 꼴에서는 같게. 「(2026년)」도 「(20  년)」과 같게(사업기간을 먼저 채워도 묶음이 깨지지 않게, ② §8)
CALENDAR = re.compile(r"\(\s*20\s*(?:\d\d)?\s*년\s*\)|(?:19|20)(?:\d\d|xx|XX)|YYYY")
NOT_LABEL = re.compile(r"매출")   # 「매출액발생 1년차」 = 사업 끝난 뒤 연차, 차년도가 아님
# 문단 라벨은 머리처럼 시작해야 — 「[…]」·「(1)」·「1.」·구분 낱말로(본문 문장 「- 1차년도에서 구축된…」 제외)
# 글머리(ㅇ·o·○·□·■·•) 뒤 기관 낱말도 라벨(보고서 6. 자체보안관리진단 「ㅇ 주관연구개발기관 : ㅇㅇㅇㅇㅇㅇ」, 10-30 [fb])
PARA_LABEL = re.compile(r"^\s*(?:[\[【<(]|\d+[.)]|(?:\d+|[Nnx])\s*(?:단계|차\s*년도|년차)|(?:[ㅇoO○●◦•□■]\s*)?(?:주관|공동)연구개발기관)")
HEADS = {"단계": STAGE, "연차": YEAR, "차년도": YEAR, "년차": YEAR}   # 번호만 있는 칸의 머리 칸 글(빈칸 뺌)
SECTION = re.compile(r"^\s*(?:(?:\d+-)+\d+\.|\[\s*별첨\s*\d+\s*\])")   # 절 제목 「8-3.」「[별첨6]」 — 헤딩 레벨이 없어도 경계
LIST_LABEL = re.compile(r"^공동연구개발기관(?:\d+(?:-\d+)*\))?$")    # 기관마다 한 행인 목록의 라벨 칸(빈칸 뺌)
OUTSIDE_LIST = re.compile(r"^연구개발기관외기관(?:\d+(?:-\d+)*\))?$")   # 표지 「연구개발기관 외 기관18)」 — 외 기관마다 한 행
ENTRUST_LIST = re.compile(r"^위탁연구개발기관(?:\d+(?:-\d+)*\))?$")    # 혁신법 별지 1 표지 「위탁연구개발기관」 — 위탁마다 한 행
# 서명 줄 「위탁연구개발기관의 장: (직인)」 — 이름 괄호(한 겹 허용) 포함
ENTRUST_SIGN = re.compile(r"^(\s*위탁연구개발기관)(\s*\((?:[^()]|\([^()]*\))*\))?(?=\s*의\s*장)")
NAME_SLOT = re.compile(r"^\s*[Xx]{3,}\s*$")   # 기관명 자리표시 칸 「XXXXX」(4-3 기술기여도 표 — 작성 예시 「AAAAA」는 아님)
EXAMPLE_SLOT = re.compile(r"^\s*([A-WYZa-wyz])\1{2,}\s*$")   # 작성 예시 기관명 「AAAAA」·「BBBBB」
SLOT_PAREN = re.compile(r"((?:주관|공동)연구개발기관(?:\s*(?:\d+|[Nn]))?)\(((?:[^()]|\([^()]*\))*)\)")   # 괄호 한 겹 허용 — 「(주관기관(미입력))」
# 쌍점 뒤 이름 자리 — 「[…기관1 : 이름]」·보고서 「[…기관명N : 이름]」·「ㅇ …기관 : 이름」(「]」 앞 / ※ 앞 / 줄 끝)
SLOT_COLON = re.compile(r"((?:주관|공동)연구개발기관(?:명)?(?:\s*(?:\d+|[Nn]))?\s*:\s*)([^\]\n※]*?)(\s*\]|\s*(?=※)|\s*$)")
SLOT_OF = re.compile(r"((?:주관|공동)연구개발기관)(의)")
PER_ORG = re.compile(r"기관\s*별")   # 혼자인 주관 절의 실마리 — 앞 문단 「ㅇ 연구개발기관별 사용계획 총괄표」(보고서, ② §2)
NEXT_YEAR = re.compile(r"다음\s*연도")   # 보고서 「5. 다음 연도 연구개발계획」 — 그 아래 기관-연도 표는 다음 차년도 행 하나(② §2)
SOLO_MAX = 60   # 혼자인 기관 절 항목의 블록 수 상한


# ---- 구분 값 ------------------------------------------------------------------------------------------

def norm_values(v):
    """{"stages": [Y1, …], "orgs": {"lead": 이름, "joint": [이름, …], "nonprofit": [주관, 공동1, …: bool], "outside": [외 기관 이름, …],
    "overseas": [국외기관 이름, …], "entrust": [위탁 이름, …]}, "period"?, "subs"?: [세부과제 주관기관 이름, …], "current"?: 당해 차년도}
    검사·정리 — 틀리면 ValueError(문구는 화면에 그대로). nonprofit 은 기관 수만큼으로 맞춤(없으면 False), outside·overseas·entrust 가
    없으면 [], 수(예전 값 — 이름 없음)면 빈 이름 그 수만큼. subs 없음 = [], current 없음 = 1."""
    if not isinstance(v, dict):
        raise ValueError("values 가 필요합니다")
    stages = v.get("stages")
    if (not isinstance(stages, list) or not 1 <= len(stages) <= MAX_STAGES
            or not all(isinstance(y, int) and not isinstance(y, bool) and 1 <= y <= MAX_YEARS for y in stages)):
        raise ValueError(f"단계는 1~{MAX_STAGES}개, 단계마다 차년도 수는 1~{MAX_YEARS}")
    if sum(stages) > MAX_TOTAL:
        raise ValueError(f"전체 차년도 수는 {MAX_TOTAL} 이하")
    orgs = v.get("orgs") or {}
    lead, joint = orgs.get("lead") or "", orgs.get("joint") or []
    if not isinstance(lead, str) or not isinstance(joint, list) or len(joint) > MAX_JOINT \
            or not all(isinstance(x, str) for x in joint):
        raise ValueError(f"기관 = 주관 이름(글) + 공동 이름 목록(0~{MAX_JOINT}개)")
    out = {"stages": stages, "orgs": {"lead": lead.strip(), "joint": [x.strip() for x in joint]}}
    np_ = orgs.get("nonprofit") or []
    if not isinstance(np_, list) or not all(isinstance(x, bool) for x in np_):
        raise ValueError("비영리 = 기관마다 참/거짓")
    out["orgs"]["nonprofit"] = (np_ + [False] * (len(joint) + 1))[:len(joint) + 1]
    for k, name in EXTRA.items():
        xs = orgs.get(k) or []
        if isinstance(xs, int) and not isinstance(xs, bool):   # 예전 값 = 수
            xs = [""] * xs if 0 <= xs <= MAX_OUTSIDE else None
        if not isinstance(xs, list) or len(xs) > MAX_OUTSIDE or not all(isinstance(x, str) for x in xs):
            raise ValueError(f"{name}은 이름 목록(0~{MAX_OUTSIDE}곳)")
        out["orgs"][k] = [x.strip() for x in xs]
    period = v.get("period") or {}
    if not isinstance(period, dict):
        raise ValueError("사업기간 = {start, end}")
    if period.get("start") or period.get("end"):
        try:
            a, b = (date.fromisoformat(period.get(k) or "") for k in ("start", "end"))
        except (TypeError, ValueError):
            raise ValueError("사업기간 시작일·종료일을 모두 날짜(YYYY-MM-DD)로 넣으세요") from None
        if a > b:
            raise ValueError("사업기간 종료일이 시작일보다 앞입니다")
        if b.year - a.year + 1 != sum(stages):
            raise ValueError(f"사업기간은 {b.year - a.year + 1}개 연도인데 차년도 합은 {sum(stages)}입니다")
        out["period"] = {"start": a.isoformat(), "end": b.isoformat()}
    subs = v.get("subs") or []   # 세부과제 주관기관 이름 — 비면 세부과제 자리 그대로(10-30 [4f])
    if not isinstance(subs, list) or len(subs) > MAX_SUBS or not all(isinstance(x, str) for x in subs):
        raise ValueError(f"세부과제는 이름 목록(0~{MAX_SUBS}개)")
    out["subs"] = [x.strip() for x in subs]
    cur = v.get("current", 1)   # 당해 차년도 = 전체 차례(기본 1 — 신규 과제)
    if cur is None:
        cur = 1
    if not isinstance(cur, int) or isinstance(cur, bool) or not 1 <= cur <= sum(stages):
        raise ValueError(f"당해 차년도는 1~{sum(stages)}(전체 차례)")
    out["current"] = cur
    return out


def stage_year(values, k):
    """전체 차례 k차년도 → (단계, 단계 안 차년도)."""
    for s, n in enumerate(values["stages"], 1):
        if k <= n:
            return s, k
        k -= n
    return len(values["stages"]), values["stages"][-1]


def sub_name(values, k):
    """세부과제 k 의 주관기관 이름 — 없으면 ""."""
    xs = values.get("subs") or []
    return xs[k - 1] if isinstance(k, int) and 1 <= k <= len(xs) else ""


def org_name(values, k):
    """기관 이름 — k = 0 주관, 1.. 공동. 빈 이름 = 자리표시 기본값(사용자 10-30: 「주관기관(미입력)」, 「참여기관1」…)."""
    if k == 0:
        return values["orgs"]["lead"] or "주관기관(미입력)"
    joint = values["orgs"]["joint"]
    return (joint[k - 1] if k <= len(joint) else "") or f"참여기관{k}"


def org_names(values, kind="all"):
    """주관 → 공동 차례의 기관 이름 — kind = "all" 전부 | "firm" 비영리로 고른 기관을 뺌(7-3 기업 현황 표) | "np" 비영리로 고른
    기관만(7-3 비영리기관 현황 표, 사용자 10-30)."""
    np_ = values["orgs"].get("nonprofit") or []
    return [org_name(values, k) for k in range(len(values["orgs"]["joint"]) + 1)
            if kind == "all" or (k < len(np_) and np_[k]) == (kind == "np")]


def extra_name(values, kind, k):
    """외 기관·국외기관(kind = EXTRA 키) k 번째 이름 — 없으면 ""."""
    xs = values["orgs"].get(kind) or []
    return xs[k - 1] if k <= len(xs) else ""


def targets(dim, values, ctx=None, lead=False, extra=None):
    stages = values["stages"]
    if extra:   # 연구개발기관 외 기관·국외기관(EXTRA) — 0곳이면 빈 목록(그 자리를 다 지움)
        return [(extra, k) for k in range(1, len(values["orgs"].get(extra) or ()) + 1)]
    if dim == STAGE:
        return list(range(1, len(stages) + 1))
    if dim == YEAR:
        return list(range(1, (stages[ctx - 1] if ctx else sum(stages)) + 1))
    if dim == STAGE_YEAR:
        return [(s, y) for s, n in enumerate(stages, 1) for y in range(1, n + 1)]
    if dim == SUB:
        return list(range(1, len(values.get("subs") or ()) + 1))
    return ([("lead", 0)] if lead else []) + [("joint", k) for k in range(1, len(values["orgs"]["joint"]) + 1)]


# ---- 라벨 ---------------------------------------------------------------------------------------------

def form_of(blocks):
    """양식 이름(FORMS — 「연구개발계획서」(일반형·통합형)·「연차보고서」 등) — 앞쪽에 그 이름으로 시작하는 짧은 문단(② §1). 아니면 None."""
    for i, b in enumerate(structure.iter_blocks(blocks)):
        if i >= FORM_SCAN:
            break
        t = re.sub(r"\s+", "", b.get("text") or "") if b.get("type") == "paragraph" else ""
        if len(t) <= 30 and (name := next((f for f in FORMS if t.startswith(f)), None)):
            return name
    return None


def is_report(form):
    """보고서 양식(연차·단계·최종보고서)인가 — 당해 라벨·다음 연도 표 규칙(② §2·§8)이 켜짐."""
    return bool(form) and form.endswith("보고서")


def _val(tok):
    return int(tok) if tok.isdigit() else N


def _key(text):
    """(구분 기준, 값) — 단계·차년도가 함께면 단계-차년도, 「(세부k)」면 세부과제(기관 낱말이 함께여도), 기관 값 = ("lead", 0) |
    ("joint", k | N | None)."""
    st = [_val(m.group(1)) for m in STAGE_RE.finditer(text)]
    yr = [_val(m.group(1)) for m in YEAR_RE.finditer(text)]
    if st and yr:
        return STAGE_YEAR, (st[0], yr[0])
    if st:
        return STAGE, st[0]
    if yr:
        return YEAR, yr[0]
    if (m := SUB_RE.search(text)):
        return SUB, _val(m.group(1))
    m = ORG_RE.search(text)
    if m:
        return ORG, ("lead", 0) if m.group(1) == "주관" else ("joint", _val(m.group(4)) if m.group(4) else None)
    return None


def _shape(text):
    # 이름 자리(「…기관(이름)」 괄호 안 · 「…기관 : 이름」 쌍점 뒤)는 꼴에서 뺀다 — 반영이 이름을 넣은 뒤에도, 자리표시가 서로 달라도(「기업명1」·「기업명2」) 같은 꼴(② §15)
    text = SLOT_COLON.sub(lambda m: f"{m.group(1)}{{이름}}{m.group(3)}", SLOT_PAREN.sub(lambda m: f"{m.group(1)}({{이름}})", text))
    s = STAGE_RE.sub("{단계}", CALENDAR.sub("{연도}", text))
    s = SUB_RE.sub("({세부})", YEAR_RE.sub("{차년도}", s))
    s = ROLE_RE.sub("({기관})", ORG_RE.sub("{기관}", s))
    s = ECHO_RE.sub("#", LEAD_NUM.sub(r"\1#", s))
    return re.sub(r"\s+", "", s)


def _label(text):
    """라벨이면 (구분 기준, 값, 꼴) — 「※」 뒤 주석을 뗀 글이 짧고 구분 낱말이 있음."""
    t = NOTE.sub("", text or "").strip()
    if not t or len(re.sub(r"\s+", "", t)) > LABEL_MAX or NOT_LABEL.search(t):
        return None
    k = _key(t)
    return (k[0], k[1], _shape(t)) if k else None


def hint_info(text):
    """추가한 자리(spec_구분_기준 ② §11) 후보 문단의 글 → {"dim", "value", "shape"} | None(값 낱말이 없음 — 표시만).
    라벨 관문(PARA_LABEL·LABEL_MAX)은 안 거친다 — 사용자가 라벨이라고 했으므로. NOT_LABEL 은 유지."""
    t = NOTE.sub("", text or "").strip()
    if not t or NOT_LABEL.search(t):
        return None
    k = _key(t)
    return {"dim": k[0], "value": k[1], "shape": _shape(t)} if k else None


def hint_shapes(idx, paras):
    """추가한 자리 문단 id 들 → {"ids": 표시한 문단 id, "shapes": {(구분, 꼴)}} — 표시한 문단과 같은 꼴·같은 구분의 글은 어디서나(사본·형제) 라벨로 본다
    (② §11 꼴 규칙). 라벨 꼴은 구분마다 하나(「hint:<구분>」)로 합쳐 — 꼴이 조금 달라도(「가. 1차년도 목표」·「가. 2차년도 목표 및 내용」) 같은 구분의 표시끼리
    값 차례로 한 묶음이 되게(LLM 재검토가 찾은 형제가 엔진 묶음에 들어가는 길)."""
    out = {"ids": set(), "shapes": set()}
    for pid in paras or ():
        b = idx.get(pid)
        if b is not None and b.get("type") == "paragraph" and (h := hint_info(b.get("text"))):
            out["ids"].add(pid)
            out["shapes"].add((h["dim"], h["shape"]))
    return out if out["ids"] else None


def _hint_label(b, hinted):
    """hinted = hint_shapes() 결과. 표시한 문단이거나 같은 꼴·같은 구분이면 (구분, 값, 「hint:구분」), 아니면 None."""
    if not hinted:
        return None
    h = hint_info(b.get("text"))
    if not h or not (b["id"] in hinted["ids"] or (h["dim"], h["shape"]) in hinted["shapes"]):
        return None
    return (h["dim"], h["value"], f"hint:{h['dim']}")


def _starts(dim, v):
    if dim in (STAGE, YEAR, SUB):
        return v == 1
    if dim == STAGE_YEAR:
        return v in ((1, 1), (N, 1))   # 양식이 항목마다 「N단계-1차년도…」로 보기를 든 곳도 있음
    return v[0] == "lead" or v[1] in (1, None)


def _follows(dim, prev, v):
    """v 가 prev 다음 값인가(② §2 값 차례)."""
    if dim in (STAGE, YEAR, SUB):
        return prev != N and v in (prev + 1, N)
    if dim == STAGE_YEAR:
        (s, y), (s2, y2) = prev, v
        if (s2, y2) == (N, N):
            return (s, y) != (N, N)
        if s2 == s:
            return y != N and y2 in (y + 1, N)
        return y2 == 1 and (s2 == N or (s != N and s2 == s + 1))
    if v[0] == "lead":
        return False
    if prev[0] == "lead":
        return v[1] in (1, None, N)
    if prev[1] is None:
        return v[1] is None
    return prev[1] != N and v[1] in (prev[1] + 1, N)


_SKELETON = re.compile(r"\{(?:단계|차년도|기관|연도|세부)\}|#|[ㅇoO○●◦•□■▪▫◇◆△▲\-–—·‧∙※*\s\[\]()（）:：.,、]+")


def _authored(content):
    """항목 비교용 글(_content)이 자리표시·글머리·빈 칸을 빼고도 두 글자 넘게 남으면 작성한 글로 본다(10-31 [2f])."""
    return len(_SKELETON.sub("", content or "")) > 2


def _content(text):
    """항목 비교용 글: 구분 낱말·번호만 있는 칸·앞 번호를 지운 꼴(값만 다른 양식 글은 같게)."""
    t = text or ""
    if BARE.match(t):
        return "#"
    t = STAGE_RE.sub("{단계}", re.sub(r"20xx|20XX|YYYY|\(20\s+년\)", "{연도}", t))
    t = ROLE_RE.sub("({기관})", ORG_RE.sub("{기관}", SUB_RE.sub("({세부})", YEAR_RE.sub("{차년도}", t))))
    return re.sub(r"\s+", "", re.sub(r"^\s*\(\d+\)", "(#)", t))   # 실제 값(날짜·금액)은 그대로 — 다르면 사용자 글


# ---- 블록 걷기 -----------------------------------------------------------------------------------------

def _under(b):
    """b 와 그 안(칸·칸 안 블록·중첩 표)의 블록 전부."""
    yield b
    for c in b.get("cells") or ():
        yield from _under(c)
    for x in b.get("blocks") or ():
        yield from _under(x)


def _paras(b):
    return [x for x in _under(b) if x.get("type") == "paragraph"]


def _containers(blocks):
    """(칸 id | None, 블록 목록) — 문서 본문과 칸마다."""
    yield None, blocks
    for b in structure.iter_blocks(blocks):
        if b.get("type") is None and "blocks" in b:
            yield b["id"], b["blocks"]


# ---- 자리 찾기 (② §2) ------------------------------------------------------------------------------------

class Run(list):
    """묶음 항목 목록 — irregular = 바로 뒤에 같은 꼴 라벨이 차례를 어기며 붙어 있음(이미 손댄 문서 — 건드리지 않음)."""
    irregular = False


def _runs(labs, dim_of, value_of, adjacent=lambda a, b: True):
    """labs(같은 꼴, 차례대로) -> 값 차례가 이어지는 묶음(2개 이상)."""
    out, cur = [], Run()
    for lab in labs:
        near = bool(cur) and adjacent(cur[-1], lab)
        if near and _follows(dim_of(lab), value_of(cur[-1]), value_of(lab)):
            cur.append(lab)
            continue
        starts = _starts(dim_of(lab), value_of(lab))
        if near and not starts:
            cur.irregular = True
        if len(cur) >= 2:
            out.append(cur)
        cur = Run([lab] if starts else [])
    if len(cur) >= 2:
        out.append(cur)
    return out


def _para_groups(cid, items, levels, hinted=None):
    """한 그릇의 문단 묶음 — 같은 꼴 라벨의 값 차례. 같거나 바깥 구분 기준의 다른 꼴 라벨이 오면 열린 안쪽 묶음은 닫힌다.
    hinted = 추가한 자리의 라벨 꼴 집합(hint_shapes, ② §11) — 그 꼴은 PARA_LABEL·LABEL_MAX 관문 없이 라벨."""
    labels = []
    for i, b in enumerate(items):
        if b.get("type") == "paragraph" and ((lab := _hint_label(b, hinted))
                                             or (PARA_LABEL.match(b["text"]) and (lab := _label(b["text"])))):
            labels.append((i, b, *lab))
        elif b.get("type") == "table" and (title := _table_title(b)):
            labels.append((i, title[0], *title[1:]))   # 라벨 = 머리 칸(칸 안 번호 「1」·「2」는 라벨이 아님)
    groups, open_ = [], {}

    def close(shape):
        g = open_.pop(shape, None)
        if g and len(g) >= 2:
            groups.append(g)
    for lab in labels:
        i, b, dim, v, shp = lab
        g = open_.get(shp)
        goes_on = bool(g) and g[0][2] == dim and _follows(dim, g[-1][3], v)
        if not goes_on and not _starts(dim, v):
            if g:
                g.irregular = True  # 같은 꼴인데 차례를 어김(손댄 문서)
            continue  # 묶음을 잇지도 시작하지도 않는 라벨(「학생인건비 현황표(x차년도)」)은 다른 묶음을 닫지 않는다
        for s in [s for s, h in open_.items() if RANK[h[0][2]] > RANK[dim]]:   # 바깥 라벨이 오면 안쪽 묶음은 끝
            close(s)
        if goes_on:
            g.append(lab)
            continue
        close(shp)
        open_[shp] = Run([lab])
    for s in list(open_):
        close(s)
    taken = {lab[0] for g in groups for lab in g}
    for lab in labels:   # 혼자인 주관 절(보고서 「[주관연구개발기관 : 기관명]」 — 앞 4블록 안 문단에 「기관별」, 이름 자리가 빈 것): 항목 하나짜리
        i, b, dim, v, shp = lab   # 기관 묶음(② §2). 이름을 넣은 라벨(반영한 뒤)·바로 뒤에 공동 라벨이 따로 있는 것은 아님(되풀이 복사 방지)
        slot = SLOT_COLON.search(b["text"]) or SLOT_PAREN.search(b["text"]) if dim == ORG and b.get("type") == "paragraph" else None
        if slot and v == ("lead", 0) and i not in taken and not _name(slot.group(2)) and _solo_ok(items, i, levels) \
                and any(items[k].get("type") == "paragraph" and PER_ORG.search(items[k]["text"]) for k in range(max(0, i - 4), i)):
            groups.append(Run([lab]))
    out = []
    for g in groups:
        dim, idx = g[0][2], [lab[0] for lab in g]
        spans = [(a, b - 1) for a, b in zip(idx, idx[1:])]
        stray = _stray_blanks(items, idx[-1], spans)   # 마지막(자리표시) 항목 라벨 바로 뒤에만 낀 빈 문단 — 항목 길이에 안 셈, 반영 때 지움
        spans.append((idx[-1], _solo_end(items, idx[-1], levels) if len(g) == 1
                      else _last_end(items, idx[-1], dim, spans, levels, len(stray))))
        strays = [[] for _ in spans[:-1]] + [stray]
        before = items[idx[0] - 1] if idx[0] else None   # 묶음 바로 앞 빈 문단 — 표 사이에 넣을 빈 줄의 본
        out.append({"kind": "paragraph", "dim": dim, "container": cid, "table": None, "irregular": g.irregular,
                    "hinted": str(g[0][4]).startswith("hint:"),   # 추가한 자리의 꼴로 잡은 묶음(② §11)
                    "blank": before["id"] if before and before.get("type") == "paragraph" and not before["text"].strip()
                    else None,
                    "items": [{"value": lab[3], "label": lab[1]["id"], "labelText": lab[1]["text"],
                               "roots": [items[k]["id"] for k in range(a, e + 1)],
                               "scope": {x["id"] for k in range(a, e + 1) for x in _under(items[k])},
                               "size": e - a + 1 - len(st), "solo": all(items[k].get("type") == "table" for k in range(a, e + 1)),
                               "stray": st,
                               "content": [_content(p["text"]) for k in range(a + 1, e + 1) for p in _paras(items[k])
                                           if p["id"] not in st]}
                              for lab, (a, e), st in zip(g, spans, strays)]})
    return out + _overseas_groups(cid, items, levels) + _entrust_groups(cid, items) + _outside_groups(cid, items)


OUTSIDE_LETTERS = "가나다라마바사아자차카타파하"
# 외 기관 절의 제목 줄 「가. 기관명:    (역할:    )」 — 1 앞 빈칸 · 2 차례 글자 · 3 「. 기관명:」 · 4 사이 빈칸 · 5 이름 · 6 「(역할: …)」
OUTSIDE_PARA = re.compile(rf"^(\s*)([{OUTSIDE_LETTERS}])(\.\s*기관명\s*:)(\s*)(.*?)(\s*\(\s*역할\s*:[^()]*\)\s*)$")
OUTSIDE_HEAD = re.compile(r"연구개발기관\s*외\s*기관|연구개발기관이\s*아닌")   # 그 절의 머리 「라. 연구개발기관이 아닌 관계 기관(연구개발기관 외 기관)」
OUTSIDE_NEAR, OUTSIDE_MAX = 4, 4   # 머리 문단을 찾는 앞쪽 블록 수 · 제목 줄 하나뿐일 때 항목에 넣을 뒤 블록 수


def _outside_groups(cid, items):
    """외 기관 절 묶음(spec_구분_기준 ② §15) — 「연구개발기관 외 기관」 머리 문단 아래 「가. 기관명: (역할: )」·「나. 기관명: (역할: )」 제목 줄과 그 아래 표가 한 벌씩
    되풀이되는 곳. 항목 = 제목 줄부터 다음 제목 줄 앞까지(사이는 표·빈 줄뿐이어야 이어진 것), 마지막 항목은 앞 항목 길이만큼(하나뿐이면 뒤따르는 표·빈 줄).
    값 = ("outside", k) — 외 기관 0곳이면 지우고 여럿이면 늘린다(국외기관 묶음·표지 외 기관 행과 같게)."""
    filler = lambda b: b.get("type") == "table" or b.get("type") == "paragraph" and not (b.get("text") or "").strip()  # noqa: E731
    marks = [i for i, b in enumerate(items) if b.get("type") == "paragraph" and OUTSIDE_PARA.match(b["text"])]
    runs = []
    for i in marks:
        if runs and all(filler(items[k]) for k in range(runs[-1][-1] + 1, i)):
            runs[-1].append(i)
        elif any(items[k].get("type") == "paragraph" and OUTSIDE_HEAD.search(items[k]["text"] or "") for k in range(max(0, i - OUTSIDE_NEAR), i)):
            runs.append([i])
    out = []
    for run in runs:
        spans = [(a, b - 1) for a, b in zip(run, run[1:])]
        cap = max((e - a for a, e in spans), default=OUTSIDE_MAX)
        j = run[-1] + 1
        while j < len(items) and j - run[-1] <= cap and filler(items[j]):
            j += 1
        spans.append((run[-1], j - 1))
        out.append({"kind": "paragraph", "dim": ORG, "container": cid, "table": None,
                    "items": [{"value": ("outside", k), "label": items[a]["id"], "labelText": items[a]["text"],
                               "roots": [items[x]["id"] for x in range(a, e + 1)],
                               "scope": {y["id"] for x in range(a, e + 1) for y in _under(items[x])}, "size": e - a + 1,
                               "content": [_content(p["text"]) for x in range(a + 1, e + 1) for p in _paras(items[x])]}
                              for k, (a, e) in enumerate(spans, 1)]})
    return out


def _entrust_groups(cid, items):
    """위탁 서명 줄 묶음(② §2, 10-30 [4f]) — 「위탁연구개발기관(…)의 장 …」 문단이 맞닿아 되풀이되는 곳, 줄마다 위탁 하나(하나도 묶음)."""
    out, end = [], None
    for i, b in enumerate(items):
        if b.get("type") != "paragraph" or not ENTRUST_SIGN.match(b["text"]):
            continue
        if i != end:
            out.append({"kind": "paragraph", "dim": ORG, "container": cid, "table": None, "items": []})
        its = out[-1]["items"]
        its.append({"value": ("entrust", len(its) + 1), "label": b["id"], "labelText": b["text"], "roots": [b["id"]],
                    "scope": {b["id"]}, "size": 1, "content": []})
        end = i + 1
    return out


def _overseas_end(items, i, levels):
    """국외기관 항목의 끝(그 다음 번호) — 라벨 + 뒤따르는 빈 줄·「o」 자리표시 줄·양식 뼈대 줄(쓴 글은 항목이 아님 — 남김, ② §7)."""
    j = i + 1
    # 글머리만 있는 「o」 줄은 헤딩 레벨이 있어도(structure.bare_bullet) 자리표시 — 개요 스타일 헤딩만 멈춤
    while j < len(items) and j - i <= OVERSEAS_MAX and items[j].get("type") == "paragraph" \
            and not items[j].get("outlineLevel") and not OVERSEAS.match(items[j]["text"]) \
            and (PLACEHOLDER.match(items[j]["text"]) or _skeleton(items, i, j)):
        j += 1
    return j


def _skeleton(items, i, j):
    """양식 뼈대 줄(② §2 국외기관 항목) — 국외기관 라벨 i 바로 앞 기관 라벨(같은 그릇)의 항목 안에 똑같은 글(※ 주석·빈칸 뺌)이 있는 문단 j:
    보고서 2-2 「ㅇ (N단계-N차년도) 추진 내용 및 실적」·「- (추진 내용)」(쓴 글은 되풀이되지 않음). 라벨·절 제목은 아님."""
    k0 = next((k for k in range(i - 1, -1, -1) if items[k].get("type") == "paragraph" and PARA_LABEL.match(items[k]["text"])
               and (lab := _label(items[k]["text"])) and lab[0] == ORG), None)
    b = items[j]
    if k0 is None or SECTION.match(b["text"]) or (PARA_LABEL.match(b["text"]) and _label(b["text"])):
        return False
    plain = lambda x: re.sub(r"\s+", "", NOTE.sub("", x.get("text") or ""))   # noqa: E731
    t = plain(b)
    return bool(t) and any(x.get("type") == "paragraph" and plain(x) == t for x in items[k0 + 1:i])


def _overseas_groups(cid, items, levels):
    """국외기관 묶음(② §2) — 「[국외기관(기관명 기입)] ※ … 없을 경우 삭제」 항목이 맞닿아 되풀이되는 곳. 항목 하나도 묶음(국외기관
    0곳이면 지우고, 여럿이면 늘림)."""
    out, i, end = [], 0, None
    while i < len(items):
        b = items[i]
        if b.get("type") != "paragraph" or not OVERSEAS.match(b["text"]):
            i += 1
            continue
        j = _overseas_end(items, i, levels)
        if i != end:
            out.append({"kind": "paragraph", "dim": ORG, "container": cid, "table": None, "items": []})
        its = out[-1]["items"]
        its.append({"value": ("overseas", len(its) + 1), "label": b["id"], "labelText": b["text"],
                    "roots": [items[k]["id"] for k in range(i, j)],
                    "scope": {x["id"] for k in range(i, j) for x in _under(items[k])}, "size": j - i,
                    "content": [_content(p["text"]) for k in range(i + 1, j) for p in _paras(items[k])]})
        i = end = j
    return out


def _stray_blanks(items, i, prev):
    """마지막(자리표시) 항목 i 의 라벨 바로 뒤에만 낀 빈 문단들(② §5 「항목 꼴 맞춤」) -> [블록 id]. 앞 항목들은 모두 라벨 바로 다음이 글 있는 문단인데
    이 항목만 라벨 → 빈 문단 → 그 글(앞 항목들의 라벨 다음 글과 같은 꼴)이면 양식의 군더더기로 본다 — KEIT 연구개발계획서 2-2 「[공동연구개발기관N(기관명
    기입)]」 아래 7pt 빈 줄(주관·공동1 에는 없음). 그대로 두면 이름을 넣은 항목·사본만 라벨과 「o」 사이가 벌어지고 뒤 빈 줄은 빠진다(2026-11-10 사용자
    "중간 줄이 맞지 않네"). 항목 길이(_last_end 의 cap)에 안 세고 반영 때 지운다(_unstray). 앞 항목이 없거나 꼴이 갈리면 []."""
    text_at = lambda k: items[k]["text"] if k < len(items) and items[k].get("type") == "paragraph" else None  # noqa: E731
    firsts = [text_at(a + 1) for a, e in prev if a + 1 <= e]
    if not prev or len(firsts) < len(prev) or not all(t and t.strip() for t in firsts):
        return []
    out, j = [], i + 1
    while (t := text_at(j)) is not None and not t.strip():
        out.append(items[j]["id"])
        j += 1
    after = text_at(j)
    if not out or not after or not after.strip() or SECTION.match(after) or (PARA_LABEL.match(after) and _label(after)) \
            or len({_content(after), *(_content(t) for t in firsts)}) != 1:
        return []
    return out


def _last_end(items, i, dim, prev, levels, extra=0):
    """마지막 항목의 끝(② §2): 그릇 끝 / 같거나 바깥 구분 기준의 라벨 / 헤딩·절 제목 / 앞 항목 중 가장 긴 길이(+ extra = 군더더기 빈 문단 수)."""
    cap = (max(e - a for a, e in prev) if prev else 0) + extra
    lv = levels.get(items[i]["id"])
    inner = [levels[items[k]["id"]] for a, e in prev for k in range(a + 1, e + 1) if items[k]["id"] in levels]
    limit = lv if lv else (min(inner) - 1 if inner else None)
    tables = any(items[k].get("type") == "table" for a, e in prev for k in range(a, e + 1))
    j = i + 1
    while j < len(items) and j - i <= cap:
        b = items[j]
        if b["id"] in levels and (limit is None or levels[b["id"]] <= limit):
            break
        if b.get("type") == "paragraph" and SECTION.match(b["text"]):  # KEIT 양식의 「8-3.」은 헤딩 레벨이 없음
            break
        if b.get("type") == "table" and not tables:  # 앞 항목에 없는 표 = 절 끝의 작성 요령 상자
            break
        if dim == ORG and b.get("type") == "paragraph" and (OVERSEAS.match(b["text"]) or ENTRUST_SIGN.match(b["text"])):
            break   # 국외기관 항목·위탁 서명 줄은 따로 묶음
        if b.get("type") == "paragraph" and PARA_LABEL.match(b["text"]) and (lab := _label(b["text"])) \
                and RANK[lab[0]] <= RANK[dim]:
            break
        j += 1
    return j - 1


def _solo_ok(items, i, levels):
    """혼자인 주관 라벨 i 뒤 같은 절 안에 공동 라벨이 따로 없는가 — 있으면(이름을 넣어 꼴이 갈린 묶음) 혼자가 아니라 되풀이 복사하지 않는다."""
    outer = _outer_level(items, i, levels)
    for k in range(i + 1, min(len(items), i + 1 + SOLO_MAX)):
        b = items[k]
        if b.get("type") != "paragraph" or PLACEHOLDER.match(b["text"]):
            continue
        if SECTION.match(b["text"]) or b["id"] in levels and (outer is None or levels[b["id"]] <= outer):
            return True
        if PARA_LABEL.match(b["text"]) and (lab := _label(b["text"])):
            return lab[0] != ORG or lab[1][0] != "joint"
    return True


def _outer_level(items, i, levels):
    """i 앞쪽 가장 가까운 헤딩(글머리만 있는 줄·「기관별」 실마리 줄은 빼고)의 레벨 | None. 실마리 「ㅇ 연구개발기관별 사용계획 총괄표」 가
    헤딩이면(글머리 「ㅇ」, 10-31 [a8]) 기관 절은 그 형제 「ㅇ 참여연구자 인건비 현황표」 까지 감싸므로 둘러싼 헤딩은 그 위 「□」."""
    return next((levels[items[k]["id"]] for k in range(i - 1, -1, -1)
                 if items[k]["id"] in levels and not PLACEHOLDER.match(items[k].get("text") or "")
                 and not PER_ORG.search(items[k].get("text") or "")), None)


def _solo_end(items, i, levels):
    """혼자인 기관 절의 끝(② §2 보고서) — 앞쪽 가장 가까운 헤딩과 같거나 바깥 레벨의 헤딩(없으면 어느 헤딩이나 — 글머리만 있는 줄은 빼고)·절 제목·
    같거나 바깥 구분 기준 라벨·국외기관 항목·위탁 서명 줄 앞까지(최대 SOLO_MAX 블록)."""
    outer = _outer_level(items, i, levels)
    j = i + 1
    while j < len(items) and j - i <= SOLO_MAX:
        b = items[j]
        if b["id"] in levels and not PLACEHOLDER.match(b.get("text") or "") and (outer is None or levels[b["id"]] <= outer):
            break
        if b.get("type") == "paragraph" and (SECTION.match(b["text"]) or OVERSEAS.match(b["text"]) or ENTRUST_SIGN.match(b["text"])):
            break
        if b.get("type") == "paragraph" and PARA_LABEL.match(b["text"]) and (lab := _label(b["text"])) and RANK[lab[0]] <= RANK[ORG]:
            break
        j += 1
    return j - 1


def _table_labels(t):
    """표의 칸 라벨 [(칸, 구분 기준, 값, 꼴, 번호만)] — 번호만 있는 칸(「1」·「n」)은 위 머리 칸이 「단계」·「연차」일 때."""
    heads = [(c, HEADS[k]) for c in t["cells"] if (k := re.sub(r"\s+", "", c["text"] or "")) in HEADS]
    out = []
    for c in t["cells"]:
        if (lab := _label(c["text"])):
            out.append((c, *lab, False))
        elif (m := BARE.match(c["text"] or "")):
            hs = [(h, d) for h, d in heads if h["row"] < c["row"] and h["col"] <= c["col"] < h["col"] + h["colSpan"]]
            if hs:
                d = max(hs, key=lambda x: x[0]["row"])[1]
                out.append((c, d, _val(m.group(1)), "{" + DIM_NAME[d] + "}", True))
        elif YEAR_ONLY.match(c["text"] or "") and len(_paras(c)) == 1 and (up := _stage_over(t, c)):
            # 단계 머리 칸 바로 아래 연도만 있는 칸 — 그 단계 안 차년도 열(순서가 값; 보고서 정량적 연구개발성과표 「1단계 | 20xx 20xx 20xx」, ② §2)
            out.append((c, YEAR, _year_col(t, c, up), "{연도열}", False))
    return out


def _stage_over(t, c):
    """c 바로 위에서 끝나며 c 의 열을 덮는 「s단계」 칸 | None."""
    return next((h for h in t["cells"] if h["row"] + h["rowSpan"] == c["row"] and h["col"] <= c["col"] < h["col"] + h["colSpan"]
                 and STAGE_CELL.match(_bare(h["text"]))), None)


def _year_col(t, c, up):
    """단계 칸 up 아래 연도만 있는 칸 c 의 차례(1부터) — 같은 행에서 up 의 왼쪽 끝부터 c 앞까지의 연도 칸 수 + 1."""
    return 1 + sum(1 for x in t["cells"] if x["row"] == c["row"] and up["col"] <= x["col"] < c["col"] and YEAR_ONLY.match(x["text"] or ""))


def _table_groups(t, title=""):
    """표 하나의 묶음 — title = 표 바로 앞 글 있는 문단(7-3 「ㅇ 비영리기관 현황」 — 기관 열이 받는 기관 종류)."""
    labs, out = _table_labels(t), []
    for axis in ("rows", "cols"):
        r, c = ("row", "col") if axis == "rows" else ("col", "row")
        rs, cs = ("rowSpan", "colSpan") if axis == "rows" else ("colSpan", "rowSpan")
        keys = {}
        for lab in labs:
            if axis == "cols" and lab[4]:
                continue
            keys.setdefault((lab[0][c], lab[0][cs], lab[3]), []).append(lab)
        def joined(a, b):
            """b 가 a 바로 다음 줄에서 시작하고, a 를 둘러싼 바깥 병합 칸(순번·평가항목 등)이 a 에서 끝나지 않음."""
            end = a[0][r] + a[0][rs] - 1
            return b[0][r] == end + 1 and not any(
                x[rs] >= 2 and x[r] < a[0][r] and x[r] + x[rs] - 1 == end
                and not x[c] <= a[0][c] < x[c] + x[cs] for x in t["cells"])
        for ls in keys.values():
            ls.sort(key=lambda x: x[0][r])
            for g in _runs(ls, lambda x: x[1], lambda x: x[2], joined):
                if g[0][1] == ORG and not all(re.search(r"연구개발기관\s*(?:\d+|[Nn]|명)", x[0]["text"]) for x in g):
                    continue  # 표의 기관 묶음은 번호·「…기관명」 자리가 있을 때만(채용 확인서의 「주관/공동연구개발기관」 고르기 행 제외)
                items = []
                for cell, dim, v, _, bare in g:
                    a, e = cell[r], cell[r] + cell[rs] - 1
                    # 항목 = 그 행(열) 범위 안에서 시작하고 끝나는 칸 — 바깥 칸(「1단계」 세로 병합이 「1년차」 행에서 시작)은 빼고
                    inside = [x for x in t["cells"] if a <= x[r] and x[r] + x[rs] - 1 <= e
                              and (axis == "rows" or x["row"] >= cell["row"])]
                    items.append({"value": v, "label": cell["id"], "labelText": cell["text"], "span": (a, e),
                                  "cross": (min(x[c] for x in inside), max(x[c] + x[cs] - 1 for x in inside)),
                                  "roots": [x["id"] for x in inside],
                                  "scope": {y["id"] for x in inside for y in _under(x)}, "size": e - a + 1,
                                  "content": sorted(_content(p["text"]) for x in inside for p in _paras(x)
                                                    if x["id"] != cell["id"])})
                out.append({"kind": axis, "dim": g[0][1], "container": None, "table": t["id"], "bare": g[0][4],
                            "items": items, "irregular": g.irregular, "_t": t})
    used = {x for g in out if g["kind"] == "rows" for it in g["items"] for x in it["scope"]} | \
        {it["label"] for g in out for it in g["items"]}   # 행 묶음 항목 안 칸(「[1단계 목표]」)은 구간 머리가 아님
    out += _section_rows(t, [lab for lab in labs if lab[0]["id"] not in used])
    for cell in t["cells"]:
        text = re.sub(r"\s+", "", cell["text"] or "")
        if cell["rowSpan"] >= 2 and LIST_LABEL.match(text):
            out.append(_list_rows(t, cell))
        elif OUTSIDE_LIST.match(text):   # 한 행만 남아도(외 기관 1곳) 다시 늘릴 수 있게 행 하나짜리도
            out.append(_list_rows(t, cell, "outside"))
        elif ENTRUST_LIST.match(text):   # 위탁(혁신법 별지 1) — 외 기관과 같게
            out.append(_list_rows(t, cell, "entrust"))
        elif text == "연구개발기관명":
            out.append(_name_rows(t, cell))
        elif text == "기관명구분":
            out.append(_org_cols(t, cell, title))
    out += _role_rows(t)   # 「이름 (주관)」·「이름 (공동)」 칸이 이어지는 열(② §12)
    if (oy := _org_year(t)):   # 기관-연도 표(8-3) — 간접비 「1차(1단계)」 칸 라벨 묶음은 이 묶음이 대신 맞춤
        out = oy
    return [g for g in out if g]


def _section_rows(t, labs):
    """구간 머리 행 묶음 — 「1단계 | 1차년도」 행 아래 품목 행·소계가 이어지고 다음 머리 행 「n단계 | n차년도」(맞닿지 않은 한 행
    라벨). 항목 = 머리 행부터 다음 머리 행 앞까지, 마지막은 앞 항목 높이만큼."""
    rows = {}
    for cell, dim, v, shp, bare in labs:
        if cell["rowSpan"] == 1 and dim != ORG and not bare:
            rows.setdefault(cell["row"], []).append((cell, dim, v, shp))
    cand = []
    for r in sorted(rows):
        cs = sorted(rows[r], key=lambda x: x[0]["col"])
        pick = lambda d: next((v for _, dd, v, _ in cs if dd == d), None)  # noqa: E731
        st, yr, sy = pick(STAGE), pick(YEAR), pick(STAGE_YEAR)
        dim, v = (STAGE_YEAR, sy) if sy else (STAGE_YEAR, (st, yr)) if st and yr else (STAGE, st) if st else (YEAR, yr)
        cand.append((r, cs, dim, v, "|".join(f"{x[0]['col']}:{x[3]}" for x in cs)))
    by, out = {}, []
    for x in cand:
        by.setdefault((x[4], x[2]), []).append(x)
    for xs in by.values():
        for g in _runs(xs, lambda x: x[2], lambda x: x[3], lambda a, b: b[0] > a[0] + 1):
            starts = [x[0] for x in g]
            spans = [(a, b - 1) for a, b in zip(starts, starts[1:])]
            size = max(e - a + 1 for a, e in spans)
            spans.append((starts[-1], min(starts[-1] + size - 1, t["nRows"] - 1)))
            items = []
            for (r, cs, dim, v, _), (a, e) in zip(g, spans):
                inside = [x for x in t["cells"] if a <= x["row"] and x["row"] + x["rowSpan"] - 1 <= e]
                heads = {x[0]["id"] for x in cs}
                items.append({"value": v, "label": cs[0][0]["id"], "labelText": " | ".join(x[0]["text"] for x in cs),
                              "span": (a, e), "roots": [x["id"] for x in inside],
                              "cross": (min(x["col"] for x in inside), max(x["col"] + x["colSpan"] - 1 for x in inside)),
                              "scope": {y["id"] for x in inside for y in _under(x)}, "size": e - a + 1,
                              "content": sorted(_content(p["text"]) for x in inside if x["id"] not in heads
                                                for p in _paras(x))})
            out.append({"kind": "rows", "dim": g[0][2], "container": None, "table": t["id"], "items": items,
                        "irregular": g.irregular, "_t": t})
    return out


def _table_title(t):
    """표 첫 행의 넓은 단계-차년도 칸(「1단계-1차년도(개월)」) — 표 하나가 통째로 항목인 묶음의 라벨 → (칸, 구분 기준, 값, 꼴)."""
    for c in t["cells"]:
        if c["row"] == 0 and c["colSpan"] * 2 >= t["nCols"] >= 3 and (lab := _label(c["text"])) and lab[0] == STAGE_YEAR:
            return c, *lab
    return None


def _list_rows(t, cell, kind="joint"):
    """기관마다 한 행(또는 세트)인 목록 — 라벨 칸 「공동연구개발기관」·「연구개발기관 외 기관」이 걸친 행을 칸이 끊기는 곳마다
    항목으로(② §2). kind = 항목 값의 종류("joint" | "outside" | "entrust"). 공동·외 기관·위탁 모두 위 머리 칸 「기관명」 열의 칸에
    이름을 씀(공동은 10-30 [57]) — 항목의 nameAt = roots 안 그 칸 자리(사본에서도 같은 자리)."""
    a0, e0 = cell["row"], cell["row"] + cell["rowSpan"] - 1
    # 라벨만큼 긴 칸(라벨 칸·나란한 바깥 칸)은 항목이 아님 — 라벨이 한 행이면 그 행에서 라벨 오른쪽 칸
    starts = [x for x in t["cells"] if a0 <= x["row"] and x["row"] + x["rowSpan"] - 1 <= e0
              and (x["rowSpan"] < cell["rowSpan"] or cell["rowSpan"] == 1 and x["col"] >= cell["col"] + cell["colSpan"])]
    if not starts:
        return None
    name = {"outside": "외 기관 ", "entrust": "위탁 "}.get(kind, "")
    head = max((x for x in t["cells"] if x["row"] < a0 and _bare(x["text"]) == "기관명"), key=lambda x: x["row"],
               default=None)
    items, a, e = [], a0, a0
    for r in range(a0, e0 + 1):
        e = max([e] + [x["row"] + x["rowSpan"] - 1 for x in starts if x["row"] == r])
        if r == e:
            inside = [x for x in starts if a <= x["row"] <= e]
            at = next((k for k, x in enumerate(inside) if head and x["row"] == a and x["col"] == head["col"]
                       and x["colSpan"] == head["colSpan"]), None)
            items.append({"value": (kind, len(items) + 1), "label": None, "labelText": f"{name}{len(items) + 1}번째 행",
                          "span": (a, e), "nameAt": at,
                          "cross": (min(x["col"] for x in inside), max(x["col"] + x["colSpan"] - 1 for x in inside)),
                          "roots": [x["id"] for x in inside], "scope": {y["id"] for x in inside for y in _under(x)},
                          "size": e - a + 1, "content": sorted(_content(p["text"]) for x in inside for p in _paras(x))})
            a = e = r + 1
    if len(items) < 1:
        return None
    return {"kind": "rows", "dim": ORG, "container": None, "table": t["id"], "list": cell["id"], "items": items, "_t": t}


def _name_rows(t, head):
    """머리 칸 「연구개발기관명」 바로 아래로 그 열 칸이 기관명 자리표시 「XXXXX」인 행이 이어지는 표 — 연구개발기관(주관 +
    공동)마다 한 행(② §2). 첫 행 = 주관. 기관명 칸 = 그 자리 기관 이름(10-30 [57], 항목 nameAt — 이름이 없으면 「XXXXX」). 이름을
    넣은 뒤에도 다시 찾게 「기술기여도」 표에선 이름 칸도 행으로 센다(작성 예시 「AAAAA」·합계 행은 아님)."""
    named = any("기술기여도" in _bare(x["text"]) for x in t["cells"])
    ok = lambda s: NAME_SLOT.match(s) or named and _name(s) and not EXAMPLE_SLOT.match(s) and _bare(s) not in TOTAL  # noqa: E731
    items, r = [], head["row"] + head["rowSpan"]
    while (c := next((x for x in t["cells"] if x["row"] == r and x["col"] == head["col"]
                      and x["colSpan"] == head["colSpan"] and ok(x["text"] or "")), None)):
        a, e = r, r + c["rowSpan"] - 1
        inside = [x for x in t["cells"] if a <= x["row"] and x["row"] + x["rowSpan"] - 1 <= e]
        k = len(items)
        items.append({"value": ("joint", k) if k else ("lead", 0), "label": None, "labelText": f"연구개발기관명 {k + 1}번째 행",
                      "span": (a, e), "nameAt": inside.index(c), "nameSlot": "XXXXX",
                      "cross": (min(x["col"] for x in inside), max(x["col"] + x["colSpan"] - 1 for x in inside)),
                      "roots": [x["id"] for x in inside], "scope": {y["id"] for x in inside for y in _under(x)},
                      "size": e - a + 1, "content": sorted(_content(p["text"]) for x in inside for p in _paras(x))})
        r = e + 1
    if not items:
        return None
    return {"kind": "rows", "dim": ORG, "container": None, "table": t["id"], "list": head["id"], "items": items, "_t": t}


def _org_cols(t, head, title=""):
    """7-3 「비영리기관 현황」·「기업 현황」 표 — 대각선 머리 칸 「기관명 / 구분」 오른쪽 열이 기관마다 하나(② §2). 표에 「기업유형」
    칸이 있으면 기업 현황(비영리 아닌 기관만), 표 앞 제목에 「비영리」가 있으면 비영리기관 현황(비영리 기관만), 아니면 전부. 머리 칸
    글은 기관 이름으로 바꾸므로 다시 찾을 때도 머리 칸으로 찾는다."""
    r, c0 = head["row"], head["col"] + head["colSpan"]
    heads = sorted((c for c in t["cells"] if c["row"] == r and c["col"] >= c0), key=lambda c: c["col"])
    if not heads or any(h["colSpan"] != 1 or h["col"] != c0 + k for k, h in enumerate(heads)) or c0 + len(heads) != t["nCols"]:
        return None
    kind = ("firm" if any("기업유형" in re.sub(r"\s+", "", c["text"] or "") for c in t["cells"])
            else "np" if "비영리" in re.sub(r"\s+", "", title or "") else "all")
    items = []
    for k, h in enumerate(heads):
        inside = [x for x in t["cells"] if x["col"] == h["col"] and x["colSpan"] == 1 and x["row"] >= r]
        items.append({"value": ("col", k + 1), "label": h["id"], "labelText": (h["text"] or "").strip() or f"{k + 1}번째 열",
                      "span": (h["col"], h["col"]), "cross": (r, max(x["row"] + x["rowSpan"] - 1 for x in inside)),
                      "roots": [x["id"] for x in inside], "scope": {y["id"] for x in inside for y in _under(x)}, "size": 1,
                      "content": sorted(_content(p["text"]) for x in inside if x["id"] != h["id"] for p in _paras(x))})
    return {"kind": "cols", "dim": ORG, "container": None, "table": t["id"], "items": items, "irregular": False, "_t": t,
            "orgCols": kind}


ROLE_END = re.compile(r"^(.*?)\((주관|공동)\)$", re.S)   # 칸 글(빈칸 뺌) 「이름(역할)」 — 1 이름 · 2 역할
ROLE_SLOT = re.compile(r"^(?:KEIT|KIAT|KETEP|[OoＯ○ㅇ]{2,}대학교|주관기관\(미입력\)|참여기관\d+)?$")   # 역할 칸의 이름이 비었거나 양식 예시·기본 이름


def _role_rows(t):
    """역할 칸 행 묶음(spec_구분_기준 ② §12) — 머리 칸에 「기관」과 「역할」(또는 「주관」)이 있는 열(7-1 (3) 가. 참여연구자 현황 「소속 기관 (역할)」·
    신규채용 표 「기관명 (주관/공동)」)에서 「이름 (주관)」·「이름 (공동)」 칸이 위아래로 맞닿아 이어지는 표: 기관마다 그 칸이 걸친 행. 같은 이름·역할 칸이
    이어지면 한 기관(양식 예시 「KETEP (공동)」 두 칸 — 사람마다 칸을 나눔). 라벨 낱말이 든 칸(「주관연구개발기관명 (주관)」)이 있는 열은 칸 라벨 묶음
    (_table_groups) 몫 — 반영이 이름을 넣은 뒤에는 이 규칙이 다시 찾는다. 「(주관)」이 처음이 아니거나 같은 이름이 떨어져 두 번 나오면 표째 그대로
    (irregular). 항목의 name = 이름(빈칸 뺌), nameAts = roots 안 이름 칸 자리(사본에서도 같은 자리)."""
    by, out = {}, []
    for c in t["cells"]:
        if (m := ROLE_END.match(_bare(c["text"]))):
            by.setdefault((c["col"], c["colSpan"]), []).append((c, m.group(1), m.group(2)))
    for (col, _), cells in by.items():
        cells.sort(key=lambda x: x[0]["row"])
        head = max((h for h in t["cells"] if h["row"] + h["rowSpan"] <= cells[0][0]["row"] and h["col"] <= col < h["col"] + h["colSpan"]),
                   key=lambda h: h["row"], default=None)
        ht = _bare(head["text"]) if head else ""
        if "기관" not in ht or not ("역할" in ht or "주관" in ht) or any(_label(c["text"]) for c, _, _ in cells) \
                or any(b[0]["row"] != a[0]["row"] + a[0]["rowSpan"] for a, b in zip(cells, cells[1:])):
            continue
        runs = []   # [(이름, 역할, [칸 …])]
        for c, name, role in cells:
            if runs and name and runs[-1][:2] == (name, role):
                runs[-1][2].append(c)
            else:
                runs.append((name, role, [c]))
        names = [n for n, _, _ in runs if n]
        items, k = [], 0
        for name, role, cs in runs:
            a, e = cs[0]["row"], cs[-1]["row"] + cs[-1]["rowSpan"] - 1
            inside = [x for x in t["cells"] if a <= x["row"] and x["row"] + x["rowSpan"] - 1 <= e]
            ids = {c["id"] for c in cs}
            k += role == "공동"
            items.append({"value": ("lead", 0) if role == "주관" else ("joint", k), "label": cs[0]["id"], "labelText": cs[0]["text"],
                          "name": name, "span": (a, e), "nameAts": [i for i, x in enumerate(inside) if x["id"] in ids],
                          "cross": (min(x["col"] for x in inside), max(x["col"] + x["colSpan"] - 1 for x in inside)),
                          "roots": [x["id"] for x in inside], "scope": {y["id"] for x in inside for y in _under(x)}, "size": e - a + 1,
                          "content": sorted(_content(p["text"]) for x in inside if x["id"] not in ids for p in _paras(x)
                                            if (p["text"] or "").strip())})
        out.append({"kind": "rows", "dim": ORG, "container": None, "table": t["id"], "items": items, "_t": t, "roleRows": True,
                    "irregular": any(role == "주관" for _, role, _ in runs[1:]) or len(set(names)) < len(names)})
    return out


def _role_fit(groups, values):
    """역할 칸 행 묶음이 구분 값과 어긋나면(작성한 표) 그대로 둔다(② §12) — 이름 칸에 구분 값에 없는 이름(빈 칸·양식 예시·기본 이름 말고)이 있을 때.
    기관-연도 표(_org_year_fit)와 같은 뜻. 보호는 여기까지 — 이름이 모두 값에 있으면 자리 차례로 맞춘다(차례를 바꾸거나 끼운 값이면 이름이 자리대로 다시 쓰임, ② §12 「이 보호의 범위」)."""
    names = {_bare(org_name(values, k)) for k in range(len(values["orgs"]["joint"]) + 1)}
    for g in groups:
        if g.get("roleRows") and any(not ROLE_SLOT.match(it["name"]) and it["name"] not in names for it in g["items"]):
            g["irregular"], g["target"] = True, None


def _label_fit(groups, values):
    """기관 라벨 묶음(문단·칸 라벨)의 라벨에 구분 값에 없는 이름이 적혀 있으면(작성한 문서) 그대로 둔다(② §15). 꼴에서 이름 자리를 빼면서(_shape) 이름 든
    라벨도 묶음이 되므로, 반영이 넣은 이름(값에 있음)과 남이 쓴 이름을 가른다(_role_fit·_org_year_fit 과 같은 뜻). 자리표시(「기관명 기입」·「기업명1」)·
    기본 이름(「참여기관k」)은 이름이 아님(_name). 역할 칸·기관-연도·기관 열·목록 행·외/국외/위탁 묶음은 저마다의 규칙."""
    names = {_bare(org_name(values, k)) for k in range(len(values["orgs"]["joint"]) + 1)}
    for g in groups:
        if g["dim"] != ORG or g.get("roleRows") or g.get("orgYear") or g.get("orgCols") or g.get("list") or g["items"][0]["value"][0] in EXTRA:
            continue
        for it in g["items"]:
            m = SLOT_COLON.search(it.get("labelText") or "") or SLOT_PAREN.search(it.get("labelText") or "")
            if m and (n := _name(m.group(2))) and _bare(n) not in names:
                g["irregular"], g["target"] = True, None
                break


def _qualify(groups, year_cells):
    """번호만 있는 칸 묶음은 자리표시(n)가 있거나, 단계 묶음이면 항목 안에 차년도 라벨 칸이 있거나(초기화 뒤 「1·2」), 같은 표에서
    바깥 구분 기준의 쓸 묶음 항목 안에 있을 때만(「단계」 머리 아래 1~9 같은 TRL 표를 건드리지 않게)."""
    ok = [g for g in groups if not g.get("bare") or any(it["value"] == N for it in g["items"])
          or g["dim"] == STAGE and all(year_cells & it["scope"] for it in g["items"]) or _one_stage(g)]
    for _ in range(3):
        more = [g for g in groups if g.get("bare") and g not in ok and any(
            h["table"] == g["table"] and RANK[h["dim"]] < RANK[g["dim"]]
            and any(g["items"][0]["label"] in it["scope"] for it in h["items"]) for h in ok)]
        if not more:
            break
        ok += more
    return [g for g in groups if g in ok]


def _one_stage(g):
    """번호만 있는 연차 행 묶음이 「단계」 머리 아래 번호 칸 하나(단계 하나만 남아 묶음이 아닌 「1」) 안 — 바깥 단계 묶음 항목 안과
    같게 본다(8-1 표: 1단계로 줄인 뒤에도 「연차 1·2」를 맞춤, 사용자 10-30)."""
    if g["dim"] != YEAR or g["kind"] != "rows":
        return False
    a, e = g["items"][0]["span"][0], g["items"][-1]["span"][1]
    return any(lab[1] == STAGE and lab[4] and lab[0]["row"] <= a and e <= lab[0]["row"] + lab[0]["rowSpan"] - 1
               and lab[0]["col"] < g["items"][0]["cross"][0] for lab in _table_labels(g["_t"]))


def _ctx(g, groups):
    """차년도 묶음의 맥락(② §2): 둘러싼 단계 항목 값 — None = 단계 밖(전체), "?" = 자리표시 단계 안(아직 모름)."""
    first = g["items"][0]["label"] or g["items"][0]["roots"][0]
    best = None
    for h in groups:
        if h["dim"] != STAGE or h is g:
            continue
        for it in h["items"]:
            if first in it["scope"] and (best is None or len(it["scope"]) < len(best["scope"])):
                best = it
    if best is None:
        return None
    return best["value"] if best["value"] != N else "?"


def find(blocks, levels, values, settled=(), rebuild=True, hints=None):
    """한 차례의 묶음 목록 — 각 묶음에 key·ctx·target(목표 값 목록 | None)·plan. settled = 이미 구조를 맞춘 묶음 key(다시
    본뜨지 않고 수·이름만 맞춤 — 안쪽 묶음이 자라 크기가 달라져도 되풀이하지 않게). rebuild=False = 모든 묶음을 그렇게(양식 자리표시를
    다시 본뜨지 않음 — 같은 값을 이미 전체 반영한 문서, ② §3). hints = 추가한 자리 문단 id 들(② §11 — 그 꼴을 라벨로)."""
    groups, year_cells, titles, heads = [], set(), {}, {}
    idx = structure.index_blocks(blocks)
    hinted = hint_shapes(idx, hints) if hints else None
    for cid, items in _containers(blocks):
        groups += _para_groups(cid, items, levels, hinted)
        prev, chain = "", {}   # 표 제목 = 같은 그릇에서 바로 앞 글 있는 문단(빈 문단은 건너뜀, 앞이 표면 없음) · chain = 둘러싼 헤딩(레벨 → 글)
        for b in items:
            if b.get("type") == "table":
                titles[b["id"]], prev = prev, ""
                heads[b["id"]] = " ".join(chain.values())
            elif (b.get("text") or "").strip():
                prev = b["text"]
                if (lv := levels.get(b["id"])):
                    chain = {k: v for k, v in chain.items() if k < lv} | {lv: b["text"]}
    for b in structure.iter_blocks(blocks):
        if b.get("type") == "table":
            groups += _table_groups(b, titles.get(b["id"], ""))
            year_cells |= {lab[0]["id"] for lab in _table_labels(b) if lab[1] in (YEAR, STAGE_YEAR)}
    groups = _qualify(groups, year_cells)
    for g in groups:   # 같은 구분 기준 묶음이 항목 안에 또 있으면(별첨 채용 확인서의 단계-차년도 안 단계-차년도) 값 바꾸기가 섞여 못 함
        inner = {it["label"] for h in groups if h is not g and h["dim"] == g["dim"] for it in h["items"]}
        if any(x in it["scope"] for it in g["items"] for x in inner):
            g["irregular"] = True
    for g in groups:
        g["key"] = g["items"][0]["label"] or g.get("list")
        g["ctx"] = _ctx(g, groups) if g["dim"] == YEAR else None
        if g["ctx"] not in (None, "?") and g["ctx"] > len(values["stages"]):
            g["ctx"] = "?"  # 지워질 단계 안 — 바깥 단계 묶음이 먼저 줄인다
        if g.get("irregular") or g["dim"] == YEAR and g["ctx"] == "?":
            g["target"] = None
        elif g.get("orgCols"):   # 7-3 기관 열: 기본 4열, 기관이 더 많으면 그만큼 — 남는 열 머리 칸은 자리표시
            names = org_names(values, g["orgCols"])
            n = max(ORG_COLS, len(names))
            g["target"] = [("col", k) for k in range(1, n + 1)]
            g["names"] = names + ["○○○" if g["orgCols"] == "firm" else ""] * (n - len(names))
        elif g["dim"] == SUB and not values.get("subs"):
            g["target"], g["unset"] = None, True   # 세부과제를 정하지 않았으면 그대로(세부과제 없는 서식·아직 모름 — 10-30 [4f])
        elif g["dim"] == ORG and g["items"][0]["value"][0] in EXTRA:
            g["target"] = targets(ORG, values, extra=g["items"][0]["value"][0])   # 0곳이면 다 지움(사용자 10-30)
        elif g["dim"] == ORG:
            lead = g["items"][0]["value"][0] == "lead"
            g["target"] = targets(ORG, values, lead=lead)
            if g.get("list"):
                g["target"] = g["target"][:] or [("joint", 1)]   # 공동 목록 행은 하나는 남김
        elif g.get("orgYear") == "year" and NEXT_YEAR.search(heads.get(g["table"], "")):   # 보고서 「다음 연도」 절의 기관-연도 표:
            k = min((values.get("current") or 1) + 1, sum(values["stages"]))                 # 기관마다 다음 차년도 행 하나(마지막 해면 그 해)
            g["target"], g["yearBase"] = [1], k - 1
        else:
            g["target"] = targets(g["dim"], values, ctx=g["ctx"])
    _org_year_fit(groups, values)
    _role_fit(groups, values)
    _label_fit(groups, values)
    for g in groups:
        g["plan"] = _plan(g, values, idx, rebuild=rebuild and g["key"] not in settled) if g["target"] is not None else None
    return groups


# ---- 계획 (② §3) ----------------------------------------------------------------------------------------

def _plan(g, values, idx, rebuild=True):
    """{"keep": [항목 번호], "drop": [항목 번호], "template": 본뜰 항목 번호, "copies": n, "order": 최종 차례, "done"}.
    본뜰 항목 = 가장 큰 항목(같으면 뒤 — 기관은 공동 항목 중). 그보다 뒤에 있는 작은 항목이 양식 글뿐(본뜰 항목에 없는 글이 없음)이면
    지우고 본뜬 사본으로 대신 — 양식의 「n단계」처럼 덜 갖춘 자리표시 항목. 남는 항목은 끝에서부터 지움."""
    items, tg = g["items"], g["target"]
    pool = [i for i, it in enumerate(items) if not (g["dim"] == ORG and it["value"][0] == "lead")] or [0]
    big = max(items[i]["size"] for i in pool)
    tpl = max(i for i in pool if items[i]["size"] == big)
    have = set(items[tpl]["content"])
    drop = [i for i in range(tpl + 1, len(items)) if items[i]["size"] < big and set(items[i]["content"]) <= have] \
        if rebuild else []
    keep = [i for i in range(len(items)) if i not in drop]
    while len(keep) > len(tg):
        drop.append(keep.pop())
    copies = len(tg) - len(keep)
    if copies and tpl not in keep:  # 본뜰 항목을 지우는 일은 없다(늘릴 때는 keep 이 줄지 않음)
        tpl = keep[-1]
    order = [("item", i) for i in keep if i <= tpl] + [("copy", k) for k in range(copies)] + \
            [("item", i) for i in keep if i > tpl]
    plan = {"keep": keep, "drop": sorted(drop), "template": tpl, "copies": copies, "order": order}
    plan["done"] = not drop and not copies and not any(
        _changes(g, values, items[i], i + 1, pos + 1, tg[pos], idx) for pos, (_, i) in enumerate(order))
    if g["table"] and not plan["done"]:
        plan["blocked"] = _simulate(g, plan)
    return plan


def _changes(g, values, it, ord_old, ord_new, new, idx):
    """항목 하나의 글 바꾸기 [(문단 id, 새 글)] — idx 는 지금 블록 색인(사본은 apply 가 새 색인으로 다시 부름)."""
    out, label = [], it["label"]
    if g.get("names") is not None:   # 7-3 기관 열: 머리 칸 글 = 그 자리 기관 이름(첫 문단, 나머지 문단은 비움)
        ps = [b for b in (idx.get(label) or {}).get("blocks") or () if b.get("type") == "paragraph"]
        want = [g["names"][ord_new - 1]] + [""] * (len(ps) - 1)
        return [(p["id"], w) for p, w in zip(ps, want) if p["text"] != w]
    if g.get("orgYear"):   # 기관-연도 표: 기관 칸 = 기관 이름, 연도 칸 = 연도·차년도
        return _org_year_changes(g, values, it, new, idx)
    if g.get("roleRows"):   # 역할 칸 행 묶음(② §12): 이름 칸 = 그 자리 기관 이름, 역할 괄호는 새 값의 역할
        name, role = org_name(values, new[1]), "주관" if new[0] == "lead" else "공동"
        return [ch for at in it["nameAts"] for ch in _put_role(idx.get(it["roots"][at]), name, role)]
    if it.get("nameAt") is not None:   # 목록 행·4-3 기관명 행: 기관명 칸 = 그 자리 이름(이름이 없으면 그대로 — 사본이면 자리표시)
        kind, k = new
        name = values["orgs"]["lead"] if kind == "lead" else extra_name(values, kind, k)   # 공동 = 넣은 이름만(기본 이름 아님)
        return _put(idx.get(it["roots"][it["nameAt"]]), name or it.get("nameSlot", "")) if name or it.get("copy") else []
    labels = {p["id"] for p in _paras(idx[label])} if label and label in idx else set()
    for root in it["roots"]:
        if root not in idx:
            continue
        for p in _paras(idx[root]):
            is_label = p["id"] in labels
            if g["dim"] == ORG and not is_label:
                continue
            text = _rename(p["text"], g["dim"], it["value"], new, is_label, (ord_old, ord_new), values, it.get("copy"))
            if text != p["text"]:
                out.append((p["id"], text))
    if label in idx and idx[label].get("type") is None and g["dim"] != ORG:   # 칸 라벨: 칸 글 전체로(「1차\n년도」)
        cell = idx[label]
        ps = [b for b in cell["blocks"] if b.get("type") == "paragraph"]
        joined = "\n".join(p["text"] for p in ps)
        new_text = _rename(joined, g["dim"], it["value"], new, True, (ord_old, ord_new), values)
        lines = new_text.split("\n")
        if new_text != joined and len(lines) == len(ps):
            done = {pid for pid, _ in out}
            out += [(p["id"], line) for p, line in zip(ps, lines) if line != p["text"] and p["id"] not in done]
    return out


def _same(tok, old):
    return tok in "Nnx" if old == N else tok == str(old)


def _rename(text, dim, old, new, label, ords, values, copy=False):
    """구분 낱말 중 옛 값과 같은 것만 새 값으로(② §3). 라벨이면 앞 번호·「k차」·기관 번호·이름 자리도. copy = 늘린 사본의 글."""
    if BARE.match(text) and label:
        tok = BARE.match(text).group(1)
        o, n = (old[0], new[0]) if dim == STAGE_YEAR else (old, new)
        return text.replace(tok, str(n), 1) if _same(tok, o) else text
    if dim in (STAGE, STAGE_YEAR):
        so, sn = (old[0], new[0]) if dim == STAGE_YEAR else (old, new)
        text = STAGE_RE.sub(lambda m: f"{sn}{m.group(2)}" if _same(m.group(1), so) else m.group(0), text)
        if label:
            text = ECHO_RE.sub(lambda m: str(sn) if _same(m.group(1), so) else m.group(0), text)
    if dim in (YEAR, STAGE_YEAR):
        yo, yn = (old[1], new[1]) if dim == STAGE_YEAR else (old, new)
        text = YEAR_RE.sub(lambda m: f"{yn}{m.group(2)}" if _same(m.group(1), yo) else m.group(0), text)
    if dim == ORG and label and new[0] == "overseas":   # 국외기관이 둘 이상이면 「[국외기관1(…)]」처럼 번호, 하나면 번호 없음
        n = len(values["orgs"].get("overseas") or ())
        # 괄호 = 이름. 이름이 없으면 그대로(사본이면 양식 자리표시 — 본뜬 항목의 이름이 따라오지 않게)
        if (m := OVERSEAS_COLON.match(text)):   # 보고서 「[국외기관명 : 이름]」 — 이름은 쌍점 뒤(없으면 그대로, 사본은 비움)
            name = extra_name(values, *new) or ("" if copy else m.group(3))
            return m.group(1) + (str(new[1]) if n >= 2 else "") + m.group(2) + name + text[m.end():]
        name = extra_name(values, *new) or (OVERSEAS_SLOT if copy else None)
        return OVERSEAS_NO.sub(lambda m: m.group(1) + (str(new[1]) if n >= 2 else "")
                               + (f"({name})" if name is not None else m.group(2) or ""), text, count=1)
    if dim == ORG and label and new[0] == "outside":   # 외 기관 절 제목 줄 「가. 기관명: (역할: )」(② §15) — 차례 글자 = 자리, 이름이 있으면 「기관명:」 뒤에(없으면 그대로, 사본이면 비움)
        if not (m := OUTSIDE_PARA.match(text)):
            return text
        letter = OUTSIDE_LETTERS[new[1] - 1] if 1 <= new[1] <= len(OUTSIDE_LETTERS) else m.group(2)
        if (name := extra_name(values, *new)):
            return f"{m.group(1)}{letter}{m.group(3)} {name} {m.group(6).strip()}"
        return f"{m.group(1)}{letter}{m.group(3)}{m.group(4)}{'' if copy else m.group(5)}{m.group(6)}"
    if dim == ORG and label and new[0] == "entrust":   # 위탁 서명 줄 「위탁연구개발기관(이름)의 장」 — 이름이 없으면 그대로(사본이면 괄호 뺌)
        name = extra_name(values, *new)
        return ENTRUST_SIGN.sub(lambda m: m.group(1) + (f"({name})" if name else ""), text, count=1) if name or copy else text
    if dim == SUB:   # 「(세부k)」 번호, 라벨의 「주관연구개발기관(…)」 괄호 = 세부 k 이름(없으면 그대로 — 사본이면 양식 자리표시)
        text = SUB_RE.sub(lambda m: m.group(0)[:m.start(1) - m.start()] + str(new) + m.group(0)[m.end(1) - m.start():]
                          if _same(m.group(1), old) else m.group(0), text)
        name = sub_name(values, new) or (OVERSEAS_SLOT if copy else None)
        if label and name is not None:
            text = SLOT_PAREN.sub(lambda m: f"{m.group(1)}({name})", text, count=1)
    if dim == ORG and label:
        text = _org_text(text, new, org_name(values, new[1]))
    if label:
        text = LEAD_NUM.sub(lambda m: m.group(1) + str(ords[1]) if int(m.group(2)) == ords[0] else m.group(0), text,
                            count=1)
    return text


def _org_text(text, new, name):
    """기관 라벨: 공동 번호 → k, 이름 자리 → 이름(괄호 안 / 쌍점 뒤 / 「…기관명」 낱말 / 「…기관의」 앞에 괄호로 넣음)."""
    kind, k = new
    colon = SLOT_COLON.search(text) is not None   # 「[…기관명 : ]」 — 낱말은 두고 쌍점 뒤에 이름

    def tok(m):
        if m.group(5) and not colon:
            return name
        if kind == "joint" and (m.group(4) or m.group(1) == "주관"):   # 번호 → k, 혼자인 주관 절의 사본은 「공동연구개발기관k」
            return f"공동연구개발기관{m.group(2) or ''}{m.group(3) or ''}{k}"
        return m.group(0)
    text, n = ORG_RE.subn(tok, text, count=1)
    if not n or ORG_RE.search(text) is None:
        return text
    if SLOT_PAREN.search(text):
        return SLOT_PAREN.sub(lambda m: f"{m.group(1)}({name})", text, count=1)
    if SLOT_COLON.search(text):
        return SLOT_COLON.sub(lambda m: f"{m.group(1)}{name}{m.group(3)}", text, count=1)
    return SLOT_OF.sub(lambda m: f"{m.group(1)}({name}){m.group(2)}", text, count=1)


# ---- 미리보기 · 초기화 -------------------------------------------------------------------------------------

def _nested(g, work):
    first = g["items"][0]["label"] or g.get("list")
    return any(h is not g and any(first in it["scope"] for it in h["items"]) for h in work)


def _pending(groups, skip):
    """이번 차례에 고칠 묶음 — 계획이 있고, 끝나지 않았고, 끄지 않았고, 다른 고칠 묶음 안에 들지 않은 것."""
    work = [g for g in groups if g["plan"] and not g["plan"]["done"] and not g["plan"].get("blocked")
            and g["key"] not in skip]
    return [g for g in work if not _nested(g, work)]


def spot(g, work=()):
    """화면용 자리 요약(② §5). reason = 지금 고치지 않는 까닭 — "done"(이미 맞음) | "irregular"(같은 꼴 라벨이 차례를 어김 —
    손댄 문서) | "unset"(세부과제 값이 비어 그대로) | "stage"(자리표시 단계 안 — 단계가 정해진 뒤) | "blocked"(병합 칸 때문에 표를
    못 고침 — message) |
    "nested"(바깥 묶음 뒤 다음 차례) | null."""
    nested = _nested(g, work)
    plan = g["plan"] or {}
    done = bool(plan.get("done"))
    reason = "done" if done else "irregular" if g.get("irregular") else "unset" if g.get("unset") \
        else "stage" if g["target"] is None else "blocked" if plan.get("blocked") else "nested" if nested else None
    # 줄일 때 지워질 항목 중 작성한 글이 든 것 — 화면은 ⚠ 로 보이고 「모두 반영」 에서 처음엔 뺀다(10-31 [2f], astra A2·A-4). 글 = 남는 항목들(keep)에 없는 content 중
    # 자리표시·글머리·빈 칸을 뺀 실제 글이 있는 것(남는 항목에 있는 양식 공통 글은 양식 글로 봄, 빈 뼈대 「o 」·빈 행은 아님). 한계(사양 §5): 다른 항목에 똑같이 쓴 글은 못
    # 잡고, 항목마다 다른 양식 예시 글은 잡는다(보수적). 본뜰 항목(template)과 견주지 않는다 — 줄일 때는 본뜰 항목 자체가 지워지는 항목일 수 있다(가장 큰 항목 중 마지막)
    items = g["items"]
    have = set().union(*(set(items[i]["content"]) for i in plan.get("keep") or () if i < len(items)))
    written = sum(1 for i in plan.get("drop") or () if i < len(items) and any(_authored(c) for c in set(items[i]["content"]) - have))
    return {"key": g["key"], "kind": "list" if g.get("list") else g["kind"], "dim": g["dim"],
            "where": {"table": g["table"], "cell": g["container"]},
            "labels": [re.sub(r"\s+", " ", it["labelText"] or "").strip()[:30] for it in g["items"]],
            "count": len(g["items"]), "target": len(g["target"]) if g["target"] is not None else None,
            "done": done, "nested": nested, "reason": reason, "message": plan.get("blocked"), "written": written,
            "hinted": bool(g.get("hinted"))}


def preview(blocks, levels, values, rebuild=True, hints=None):
    groups = find(blocks, levels, values, rebuild=rebuild, hints=hints)
    work = [g for g in groups if g["plan"] and not g["plan"]["done"] and not g["plan"].get("blocked")]
    fill = period_fill(blocks, values, is_report(form_of(blocks)))
    return [spot(g, work) for g in groups] + ([_period_spot(fill)] if fill else [])


def _within(groups, key, inside=()):
    """key 묶음과 그 항목 안에 든 묶음만 — 자리 하나만 반영할 때(② §5 only). 차례마다 다시 찾아도 key(첫 라벨)는 그대로.
    inside = 앞 차례에 고친 묶음의 범위·사본 id — 다시 찾은 마지막 항목 범위가 「앞 항목 중 가장 긴 블록 수」로 잘려도 안쪽으로 봄."""
    root = next((g for g in groups if g["key"] == key), None)
    if root is None:
        return []
    scope = set(inside).union(*(it["scope"] for it in root["items"]))
    return [g for g in groups if g is root or (g["items"][0]["label"] or g.get("list")) in scope]


def _short(text, n=40):
    return re.sub(r"\s+", " ", text or "").strip()[:n]


def apply(doc, values, skip=(), levels_of=None, only=None, rebuild=True, hints=None):
    """구분 값에 맞춰 문서를 고친다(② §3) — 차례마다 바깥 묶음만, 다시 찾기. levels_of(blocks) -> {블록 id: 헤딩 레벨}.
    rebuild=False = 양식 자리표시(본뜰 항목보다 작은 뒤 항목)를 지우고 다시 본뜨지 않음 — 같은 값을 이미 전체 반영한 문서(서버가 정함).
    only = 묶음 key 하나 — 그 묶음과 그 안쪽 묶음만(오른쪽 패널의 자리별 「반영」). 사업기간이 있으면 차례가 끝난 뒤 날짜를 채움
    (② §8 — only "period" = 날짜만, skip 에 "period" = 날짜 빼기). hints = 추가한 자리 문단 id 들(② §11 — find 에 그대로).
    -> {"groups": [{key, dim, kind, from, to, table, labels, added: [사본 라벨 id], removed: [지운 항목 라벨]}], "added",
    "removed", "passes", "errors", "changes": [{id, old, new, key}] (글을 바꾼 문단 — 처음 글 → 마지막 글),
    "tables": {표 id: {"removed": [칸], "origin": {새 칸: 원본 칸}}}}."""
    skip = set(skip or ())
    report = {"groups": [], "added": 0, "removed": 0, "passes": 0, "errors": [], "changes": [], "tables": {}}
    changed = {}   # 문단 id → {id, old, new, key} — 여러 차례에 걸쳐 바뀌어도 하나로
    shaped = set()   # 구조를 바꾼 묶음 — 다음 차례에 또 늘리거나 줄여야 하면 맞추지 못한 것(멈추고 보고)
    inside = set() if only is not None else None   # only: 고친 묶음의 범위 + 사본 id(_within)
    for _ in range(PASSES if only != PERIOD else 0):
        blocks = doc.blocks()
        groups = find(blocks, levels_of(blocks) if levels_of else {}, values, settled=shaped, rebuild=rebuild, hints=hints)
        if only is not None:
            groups = _within(groups, only, inside)
        work = _pending(groups, skip)
        for g in [g for g in work if g["key"] in shaped and (g["plan"]["copies"] or g["plan"]["drop"])]:
            skip.add(g["key"])
            report["errors"].append({"key": g["key"], "dim": g["dim"], "message": "한 번 맞춘 뒤에도 수가 맞지 않아 멈췄습니다"})
        work = [g for g in work if g["key"] not in skip]
        if not work:
            break
        report["passes"] += 1
        tasks = []
        for g in sorted(work, key=lambda g: (g["table"] or "", -(g["items"][0].get("span") or (0, 0))[0])):
            if g["plan"]["copies"] or g["plan"]["drop"]:
                shaped.add(g["key"])
            if inside is not None:
                inside.update(*(it["scope"] for it in g["items"]))
            try:
                tasks += _apply_group(doc, g, values, report, inside)
            except ValueError as x:
                skip.add(g["key"])
                report["errors"].append({"key": g["key"], "dim": g["dim"], "message": str(x)})
        idx = structure.index_blocks(doc.blocks())
        for g, it, ord_old, ord_new, new in tasks:
            for pid, text in _changes(g, values, it, ord_old, ord_new, new, idx):
                c = changed.setdefault(pid, {"id": pid, "old": (idx.get(pid) or {}).get("text"), "key": g["key"]})
                c["new"] = text
                doc.set_text(pid, text)
        for g in work:   # 역할 칸 행 묶음의 행을 늘리거나 줄였으면 「번호」 열을 1부터 다시(② §12)
            if g.get("roleRows") and g["key"] not in skip and (g["plan"]["copies"] or g["plan"]["drop"]):
                for pid, text in _renumber(idx.get(g["table"])):
                    changed.setdefault(pid, {"id": pid, "old": (idx.get(pid) or {}).get("text"), "key": g["key"]})["new"] = text
                    doc.set_text(pid, text)
    if only is None:
        _even_cols(doc, values, report, levels_of)
        if values["orgs"]["lead"]:   # 표지 「주관연구개발기관 | 기관명」 칸 = 주관 이름(10-30 [57])
            blocks = doc.blocks()
            idx = structure.index_blocks(blocks)
            for pid, text in _put(_cover_lead_cell(blocks), values["orgs"]["lead"]):
                changed.setdefault(pid, {"id": pid, "old": (idx.get(pid) or {}).get("text"), "key": "lead"})["new"] = text
                doc.set_text(pid, text)
    if PERIOD not in skip and only in (None, PERIOD):
        blocks = doc.blocks()
        for f in period_fill(blocks, values, is_report(form_of(blocks))):
            if f["new"] != f["old"]:
                changed.setdefault(f["id"], {"id": f["id"], "old": f["old"], "key": PERIOD})["new"] = f["new"]
                doc.set_text(f["id"], f["new"])
    report["changes"] = [c for c in changed.values() if c["new"] != c["old"]]
    return report


# ---- 기관-연도 표 (② §2·§3 — 8-3 연구개발비 세부 사용계획) -------------------------------------------------

YEAR_COL = re.compile(r"연도$")   # 기관 열 바로 오른쪽 머리 칸 「구축연도」·「구매연도」·「연도」
STEP_CELL = re.compile(r"^(\d+|[Nnx])차\((\d+|[Nnx])단계\)$")   # 간접비 「연차(단계)」 칸 「1차\n(1단계)」(빈칸 뺌)
STEP_NO = re.compile(r"(?<![0-9A-Za-z])(\d+|[Nnx])(?=\s*차(?!\s*년))")
YEAR_SLOT = re.compile(r"^(?:YYYY|yyyy|20[xX]{2}|(?:19|20)\d\d|(?:(?:\d+|[Nnx])단계-?)?(?:\d+|[Nnx])차년도)?$")   # 연도 칸 글(빈칸 뺌)
REAL_YEAR = re.compile(r"^(?:19|20)\d\d$")
ORG_SLOT = re.compile(r"^(?:KEIT|주관기관\(미입력\)|참여기관\d+)?$")   # 기관 칸(빈칸 뺌)이 비었거나 양식 예시·기본 이름
TOTAL = {"계", "소계", "합계", "총계"}


def _org_year(t):
    """기관-연도 표 묶음(② §2) — 첫 칸 머리가 「연구개발기관」인 표: 그 아래 기관 칸(세로 병합)마다 기관 하나(첫 = 주관), 오른쪽
    머리가 「…연도」면 기관 안 연도 칸마다 차년도 하나(한 해 한 행). 같은 기관 이름이 두 번 나오거나, 한 기관 안에서 연도가 겹치거나
    건너뛰거나 연도 칸이 기관 행을 다 덮지 않으면(품목마다 행을 쓴 표) 표째 그대로(irregular). 기관-연도 표가 아니면 []."""
    cells = t["cells"]
    head = next((c for c in cells if c["row"] == 0 and c["col"] == 0 and _bare(c["text"]) == "연구개발기관"), None)
    if head is None:
        return []
    yh = next((c for c in cells if c["row"] == 0 and c["col"] == head["colSpan"] and YEAR_COL.search(_bare(c["text"]))),
              None)
    orgs, r = [], head["rowSpan"]
    while (c := next((x for x in cells if x["row"] == r and x["col"] == 0 and x["colSpan"] == head["colSpan"]), None)) \
            and _bare(c["text"]) not in TOTAL:
        orgs.append(c)
        r += c["rowSpan"]
    if not orgs:
        return []
    names = [x for x in (_bare(c["text"]) for c in orgs) if x]
    org_items, out, bad = [], [], len(set(names)) < len(names)
    for k, c in enumerate(orgs):
        a, e = c["row"], c["row"] + c["rowSpan"] - 1
        inside = [x for x in cells if a <= x["row"] and x["row"] + x["rowSpan"] - 1 <= e]
        ys = sorted((x for x in inside if yh and x["col"] == yh["col"]), key=lambda x: x["row"])
        fixed = {c["id"]} | {x["id"] for x in ys} | {x["id"] for x in inside if STEP_CELL.match(_bare(x["text"]))}
        org_items.append({**_org_year_item(("joint", k) if k else ("lead", 0), c, inside, fixed, f"기관 {k + 1}"),
                          "name": _bare(c["text"])})
        if not yh:
            continue
        texts = [_bare(y["text"]) for y in ys]
        filled = [x for x in texts if x]
        real = [int(x) - i for i, x in enumerate(texts) if REAL_YEAR.match(x)]
        if not ys or [y["row"] for y in ys] != list(accumulate([a] + [y["rowSpan"] for y in ys[:-1]])) \
                or ys[-1]["row"] + ys[-1]["rowSpan"] - 1 != e \
                or not all(YEAR_SLOT.match(x) for x in texts) or len(set(filled)) < len(filled) or len(set(real)) > 1:
            bad = True
            continue
        items = []
        for i, y in enumerate(ys):
            ya, ye = y["row"], y["row"] + y["rowSpan"] - 1
            ins = [x for x in inside if ya <= x["row"] and x["row"] + x["rowSpan"] - 1 <= ye and x["col"] >= yh["col"]]
            items.append({**_org_year_item(i + 1, y, ins, fixed, f"연도 {i + 1}"),
                          "year": int(texts[i]) if REAL_YEAR.match(texts[i]) else None})
        out.append({"kind": "rows", "dim": YEAR, "container": None, "table": t["id"], "items": items, "_t": t,
                    "orgYear": "year"})
    out.insert(0, {"kind": "rows", "dim": ORG, "container": None, "table": t["id"], "items": org_items, "_t": t,
                   "orgYear": "org"})
    for g in out:
        g["irregular"] = bad
    return out


def _org_year_item(value, cell, inside, fixed, blank):
    """기관-연도 표 항목 — 라벨 = 기관 칸·연도 칸(행 범위), 비교 글은 기관·연도·연차 칸과 빈 글을 뺀 것."""
    a, e = cell["row"], cell["row"] + cell["rowSpan"] - 1
    return {"value": value, "label": cell["id"], "labelText": _short(cell["text"]) or blank, "span": (a, e),
            "cross": (min(x["col"] for x in inside), max(x["col"] + x["colSpan"] - 1 for x in inside)),
            "roots": [x["id"] for x in inside], "scope": {y["id"] for x in inside for y in _under(x)},
            "size": e - a + 1,
            "content": sorted(_content(p["text"]) for x in inside if x["id"] not in fixed for p in _paras(x)
                              if (p["text"] or "").strip())}


def _org_year_fit(groups, values):
    """기관-연도 표가 구분 값과 어긋나면(작성한 표 — 경비가 있는 기관만 적은 표 등) 그 표의 묶음을 모두 그대로 둔다(② §2): 기관 칸에
    구분 값에 없는 이름(빈 칸·양식 예시 「KEIT」·기본 이름 말고)이 있거나, 사업기간 안 실제 연도가 행 차례(k차년도 = 시작 연도 + k − 1)와
    다름."""
    names = {_bare(org_name(values, k)) for k in range(len(values["orgs"]["joint"]) + 1)}
    years = _period(values)
    y0, n = (years[0][0].year, len(years)) if years else (0, 0)
    bad = {g["table"] for g in groups if g.get("orgYear") == "org"
           and any(not ORG_SLOT.match(it["name"]) and it["name"] not in names for it in g["items"])}
    bad |= {g["table"] for g in groups if g.get("orgYear") == "year"
            and any(it["year"] and y0 <= it["year"] < y0 + n and it["year"] - y0 != i + g.get("yearBase", 0)
                    for i, it in enumerate(g["items"]))}
    for g in groups:
        if g.get("orgYear") and g["table"] in bad:
            g["irregular"], g["target"] = True, None


def _org_year_changes(g, values, it, new, idx):
    """기관-연도 표 항목의 글(② §3) — 기관 칸 = 기관 이름, 연도 칸 = 사업기간이 있으면 연도, 없으면 「k차년도」(단계가 둘 이상이면
    「s단계-y차년도」), 간접비 「k차\n(s단계)」 칸 = 단계 안 차년도·단계. 칸 글은 첫 문단에 쓰고 나머지 문단은 비움."""
    if g["dim"] == ORG:
        return _put(idx.get(it["label"]), org_name(values, new[1]))
    stages, years = values["stages"], _period(values)
    new = new + g.get("yearBase", 0)   # 「다음 연도」 절의 표는 행 하나가 다음 차년도(② §2)
    s = next(i for i in range(1, len(stages) + 1) if new <= sum(stages[:i]))
    y = new - sum(stages[:s - 1])
    out = _put(idx.get(it["label"]), str(years[new - 1][0].year) if years
               else f"{new}차년도" if len(stages) == 1 else f"{s}단계-{y}차년도")
    for root in it["roots"]:
        x = idx.get(root)
        if x and x.get("type") is None and STEP_CELL.match(_bare(x.get("text"))):
            for p in _paras(x):
                text = STAGE_RE.sub(lambda m: f"{s}{m.group(2)}", STEP_NO.sub(str(y), p["text"]))
                if text != p["text"]:
                    out.append((p["id"], text))
    return out


# ---- 사업기간 — 날짜·연도 채우기 (② §8) ------------------------------------------------------------------

PERIOD = "period"   # 날짜 자리의 key·구분 기준 — 미리보기 자리 하나, only·skip
YR = r"(?:YYYY|yyyy|20[xX]{2}|(?:19|20)\d\d)"
DAY = r"(?:YYYY|\d{4})\s*\.\s*(?:MM|\d{1,2})\s*\.\s*(?:DD|\d{1,2})"
SPAN_RE = re.compile(rf"{DAY}\s*[-~～]\s*{DAY}(?:\s*\(\s*(?:\d*\s*년)?\s*(?:\d*\s*개월)?\s*\))?")   # 「YYYY. MM. DD - …(  년  개월)」
RANGE_RE = re.compile(rf"\(\s*{YR}\s*[~～-]\s*{YR}\s*\)")                     # 단계 연도 범위 「(20xx~20xx)」
YEAR_PAREN = re.compile(r"\(\s*20\s*(?:\d\d)?\s*년\s*\)")                     # 「(20  년)」·「(2026년)」
YEAR_ONLY = re.compile(rf"^\s*{YR}\s*$")
YEAR_HEAD = re.compile(rf"^\s*{YR}(?=\s*\()")                                 # 「2021 (1단계-1차년도)」 앞 연도
YEAR_TOK = re.compile(YR)
SY_RE = re.compile(r"(?<![0-9A-Za-z])(\d+|[Nnx])\s*단계\s*-?\s*(\d+|[Nnx])\s*차\s*년도")
STAGE_END = re.compile(r"(?<![0-9A-Za-z])(\d+|[Nnx])\s*단계\s*$")
STAGE_CELL = re.compile(r"^(\d+|[Nnx])단계$")                                  # 칸 글(빈칸·각주 번호 뺌)
YEAR_CELL = re.compile(r"^(\d+|[Nnx])(?:년차|차년도)$")
# 당해연도 라벨 「(n단계, x차년도)」·보고서 표지 「n단계 x차년도14-3)」 — 1 단계 · 2 사이 · 3 차년도 · 4 뒤
THIS_SY = re.compile(r"(?<![0-9A-Za-z])(\d+|[Nnx])(\s*단계\s*[,\-]?\s*)(\d+|[Nnx])(\s*차\s*년도)")
CUR_PARA = re.compile(r"^(\s*[ㅇoO○●◦•]\s*)\(\s*(?:(?:\d+|[Nnx])\s*단계\s*-?\s*)?(?:\d+|[Nnx])\s*차\s*년도\s*\)")   # 보고서 2-2 「ㅇ (N단계-N차년도) 추진 내용 및 실적」
CUR_SUMMARY = re.compile(r"^(\s*\[\s*)(\d+|[Nnx])(\s*차\s*년도\s*(?:목표|개발\s*내용)\s*\])")   # 보고서 요약문 「[N차년도 목표]」·「[N차년도 개발내용]」
# 당해 차년도 표 제목 「…현황표(x차년도)」 — 채운 「(1차년도)」·「(2단계-1차년도)」도(다시 씀)
CUR_TABLE = re.compile(r"현황표\s*(\(\s*(?:(?:\d+|[Nnx])\s*단계\s*-\s*)?(?:\d+|[Nnx])\s*차\s*년도\s*\))")


def _period(values):
    """차년도마다 (시작일, 종료일) — 회계연도로 나눔(첫해는 시작일부터, 마지막 해는 종료일까지). 사업기간이 없으면 None."""
    p = values.get("period")
    if not p:
        return None
    a, b = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
    return [(max(a, date(y, 1, 1)), min(b, date(y, 12, 31))) for y in range(a.year, b.year + 1)]


def _span_text(a, b):
    """「2026. 04. 01 - 2026. 12. 31(9개월)」 — 개월 = 시작일부터 끝날 다음 날까지 달 수(남는 날 버림), 0 인 부분은 뺌."""
    n = b + timedelta(days=1)
    y, m = divmod((n.year - a.year) * 12 + n.month - a.month - (n.day < a.day), 12)
    dur = " ".join(x for x in (f"{y}년" if y else "", f"{m}개월" if m else "") if x) or "0개월"
    return f"{a.year}. {a.month:02d}. {a.day:02d} - {b.year}. {b.month:02d}. {b.day:02d}({dur})"


def _year_no(values, s, y):
    """단계 s 안 y차년도(s None = 전체 차례) → 전체 차례 1..T | None(자리표시·값 밖)."""
    stages = values["stages"]
    if not isinstance(y, int) or s is not None and not isinstance(s, int):
        return None
    if s is None:
        return y if 1 <= y <= sum(stages) else None
    return sum(stages[:s - 1]) + y if 1 <= s <= len(stages) and 1 <= y <= stages[s - 1] else None


def _put(cell, text):
    """칸 글을 text 로 — 첫 문단에 쓰고 나머지 문단은 비움 -> [(문단 id, 새 글)] (바뀌는 것만)."""
    ps = [b for b in (cell or {}).get("blocks") or () if b.get("type") == "paragraph"]
    want = [text] + [""] * (len(ps) - 1)
    return [(p["id"], w) for p, w in zip(ps, want) if p["text"] != w]


def _put_role(cell, name, role):
    """「이름 (역할)」 칸 글(② §12) — 역할 괄호가 든 문단 앞까지가 이름(첫 문단에 쓰고 사이 문단은 비움), 괄호 안은 role, 그 뒤 문단은 그대로
    -> [(문단 id, 새 글)] (바뀌는 것만). 역할 괄호가 없으면 []."""
    ps = [b for b in (cell or {}).get("blocks") or () if b.get("type") == "paragraph"]
    j = max((i for i, p in enumerate(ps) if ROLE_RE.search(p["text"] or "")), default=None)
    if j is None:
        return []
    text = ps[j]["text"]
    m = list(ROLE_RE.finditer(text))[-1]
    head, tail = text[:m.start()], f"({role})" + text[m.end():]
    if j == 0:   # 한 문단 「이름 (역할)」 — 사이 빈칸은 그대로
        want = [name + (head[len(head.rstrip()):] or " ") + tail]
    else:        # 「이름」 문단(들) + 「(역할)」 문단
        want = [name] + [""] * (j - 1) + [head[:len(head) - len(head.lstrip())] + tail]
    return [(p["id"], w) for p, w in zip(ps, want) if p["text"] != w]


def _renumber(t):
    """「번호」 머리 칸 아래 그 열의 칸이 모두 숫자면 위에서부터 1, 2, … 로(② §12 — 행을 늘리거나 줄인 뒤) -> [(문단 id, 새 글)] (바뀌는 것만)."""
    head = next((c for c in (t or {}).get("cells") or () if _bare(c["text"]) == "번호"), None)
    if head is None:
        return []
    cs = sorted((c for c in t["cells"] if c["col"] == head["col"] and c["colSpan"] == head["colSpan"]
                 and c["row"] >= head["row"] + head["rowSpan"]), key=lambda c: c["row"])
    if not cs or not all(re.fullmatch(r"\d+", _bare(c["text"])) for c in cs):
        return []
    return [ch for k, c in enumerate(cs, 1) for ch in _put(c, str(k))]


def _bare(text):
    """칸 글 비교용 — 빈칸·※ 주석·끝 각주 번호(「14-1)」·「8)」) 뺌."""
    return re.sub(r"(?:\d+(?:-\d+)*\))+$", "", re.sub(r"\s+", "", NOTE.sub("", text or "")))


def period_fill(blocks, values, report=False):
    """사업기간으로 채울 문단 [{id, old, new, kind, where: {table, cell}}] — 이미 맞은 문단도(old == new). 사업기간이 없으면 [].
    kind = 자리(② §8): "whole"(전체 기간) | "this"(당해연도 = 1차년도 기간) | "year"(차년도 기간 행) | "stage"(단계 연도 범위) |
    "stageYear"(단계-차년도 연도) | "column"(차년도 열 연도). report = 보고서 양식(is_report) — 당해 라벨 「ㅇ (N단계-N차년도) …」·「[N차년도 목표]」도."""
    years = _period(values)
    if not years:
        return []
    stages = values["stages"]
    year_of = lambda k: years[k - 1][0].year   # noqa: E731 — 전체 차례 k차년도의 연도
    out = {}

    def put(p, new, kind, table=None, cell=None):
        if p["id"] not in out:   # 먼저 정한 것(표 행 기간)이 이김
            out[p["id"]] = {"id": p["id"], "old": p.get("text") or "", "new": new, "kind": kind, "where": {"table": table, "cell": cell}}

    def stage_span(s):
        if not isinstance(s, int) or not 1 <= s <= len(stages):
            return None
        first = sum(stages[:s - 1]) + 1
        return year_of(first), year_of(first + stages[s - 1] - 1)

    for t in structure.iter_blocks(blocks):
        if t.get("type") == "table":
            _period_table(t, values, years, year_of, put)
    ck = min(values.get("current") or 1, len(years))
    cs, cy = stage_year(values, ck)
    cur = f"({cy}차년도)" if len(stages) == 1 else f"({cs}단계-{cy}차년도)"   # 당해 차년도 표 제목 꼴(8-3 연도 칸과 같게)
    for cid, items in _containers(blocks):
        paras = [x for x in items if x.get("type") == "paragraph"]
        for i, p in enumerate(paras):
            text = p.get("text") or ""
            near = [text] + ([paras[i - 1].get("text") or ""] if cid and i else []) \
                + ([paras[i + 1].get("text") or ""] if cid and i + 1 < len(paras) else [])
            if (m := CUR_TABLE.search(text)):   # 「참여연구자 인건비 현황표(x차년도) ※ 당해연도 내용만 작성」 — 당해 차년도(10-30 [4f])
                put(p, text[:m.start(1)] + cur + text[m.end(1):], "this", cell=cid)
                continue
            if report and (m := CUR_PARA.match(text)):   # 보고서 2-2 「ㅇ (N단계-N차년도) 추진 내용 및 실적」 = 당해 차년도(② §8 1-1)
                put(p, m.group(1) + cur + text[m.end():], "this", cell=cid)
                continue
            if report and (m := CUR_SUMMARY.match(text)):   # 보고서 요약문 「[N차년도 목표]」·「[N차년도 개발내용]」 = 당해 차년도(전체 차례)
                put(p, f"{m.group(1)}{ck}{m.group(3)}", "this", cell=cid)
                continue
            m = RANGE_RE.search(text)
            if m:   # 단계 연도 범위 — 같은 문단 바로 앞 「s단계」, 없으면 같은 칸 앞 문단 끝 「s단계」
                st = list(STAGE_RE.finditer(text[:m.start()]))
                prev = STAGE_END.search(paras[i - 1].get("text") or "") if cid and i else None
                s = _val(st[-1].group(1)) if st else _val(prev.group(1)) if prev else None
                span = stage_span(s)
                if span:
                    put(p, f"{text[:m.start()]}({span[0]}~{span[1]}){text[m.end():]}", "stage", cell=cid)
                continue
            m = YEAR_PAREN.search(text) or YEAR_ONLY.match(text) or YEAR_HEAD.match(text)
            if not m:
                continue
            sy = next((x for x in map(SY_RE.search, near) if x), None)   # 단계-차년도 — 같은 문단, 앞 문단, 뒤 문단
            k = _year_no(values, _val(sy.group(1)), _val(sy.group(2))) if sy else None
            if k:
                y = year_of(k)
                put(p, text[:m.start()] + (f"({y}년)" if m.re is YEAR_PAREN else YEAR_TOK.sub(str(y), m.group(), 1))
                    + text[m.end():], "stageYear", cell=cid)
    return list(out.values())


def _period_table(t, values, years, year_of, put):
    """표 자리(② §8 1·2·5) — 행 기간(왼쪽 라벨 칸), 「전체 연구개발기간」 오른쪽 빈 칸, 위 「k차년도」 칸 아래 연도만 있는 칸."""
    cells = t["cells"]

    def rows(c):
        return range(c["row"], c["row"] + (c.get("rowSpan") or 1))

    def over(c):   # 바로 위 칸
        return next((x for x in cells if c["row"] - 1 in rows(x) and x["col"] <= c["col"] < x["col"] + (x.get("colSpan") or 1)), None)

    def paras(c):
        return [x for x in c.get("blocks") or () if x.get("type") == "paragraph"]

    def first(rx, texts):
        return next((m for m in map(rx.match, texts) if m), None)

    whole = (years[0][0], years[-1][1])
    for c in cells:
        bare = _bare(c.get("text"))
        for p in paras(c):
            m = SPAN_RE.search(p.get("text") or "")
            if not m:
                continue
            lefts = [x for x in cells if x["col"] + (x.get("colSpan") or 1) <= c["col"] and set(rows(x)) & set(rows(c))]
            left = [_bare(x.get("text")) for x in lefts]
            st, yr = first(STAGE_CELL, left), first(YEAR_CELL, left)
            this = next((x for x, b in zip(lefts, left) if b.startswith(("당해연도", "해당연도"))), None)
            if this:   # 당해연도(보고서 「해당연도」) = 당해 차년도(기본 1 — 신규 과제) — 왼쪽 칸들의 라벨 「(n단계, x차년도)」·「n단계 x차년도」도
                k = min(values.get("current") or 1, len(years))   # 그 차년도로(10-30 [fb] → [4f])
                kind, span = "this", years[k - 1]
                s, y = stage_year(values, k)
                for x in lefts:
                    for q in paras(x):
                        lab = q.get("text") or ""
                        if THIS_SY.search(lab):
                            put(q, THIS_SY.sub(lambda m: f"{s}{m.group(2)}{y}{m.group(4)}", lab, 1), "this", t["id"], x["id"])
            elif any(x.startswith("전체") for x in left):
                kind, span = "whole", whole
            else:
                k = _year_no(values, _val(st.group(1)) if st else None, _val(yr.group(1))) if yr else None
                kind, span = "year", years[k - 1] if k else None
            if span:
                text = p.get("text") or ""
                put(p, text[:m.start()] + _span_text(*span) + text[m.end():], kind, t["id"], c["id"])
        if bare.startswith("전체연구개발기간") and len(bare) <= 15:   # 요약문 「전체 연구개발기간」 | (빈 칸)
            right = next((x for x in cells if x["row"] == c["row"] and x["col"] == c["col"] + (c.get("colSpan") or 1)), None)
            ps = paras(right) if right else []
            if ps and not (right.get("text") or "").strip():
                put(ps[0], _span_text(*whole), "whole", t["id"], right["id"])
        if YEAR_ONLY.match(c.get("text") or "") and len(paras(c)) == 1:   # 위 「k차년도」(그 위 「s단계」) 칸 아래 연도
            up = over(c)
            yr = YEAR_CELL.match(_bare(up.get("text"))) if up else None
            k = None
            if yr:
                top = over(up)
                st = STAGE_CELL.match(_bare(top.get("text"))) if top else None
                k = _year_no(values, _val(st.group(1)) if st else None, _val(yr.group(1)))
            elif (st := _stage_over(t, c)):   # 단계 칸 바로 아래 연도만 있는 칸 — 그 단계 안 차례(보고서 정량적 연구개발성과표, ② §8 5)
                k = _year_no(values, _val(STAGE_CELL.match(_bare(st["text"])).group(1)), _year_col(t, c, st))
            if k:
                p = paras(c)[0]
                put(p, YEAR_TOK.sub(str(year_of(k)), p.get("text") or "", 1), "column", t["id"], c["id"])


def _period_spot(fill):
    """미리보기 자리(② §5) — 라벨 = 채울 글(빈 칸이 많아 옛 글로는 알 수 없음), 바꿀 문단이 없으면 「이미 맞음」."""
    todo = [f for f in fill if f["new"] != f["old"]] or fill
    n = sum(f["new"] != f["old"] for f in fill)
    return {"key": PERIOD, "kind": "date", "dim": PERIOD, "where": todo[0]["where"], "ids": [f["id"] for f in todo],
            "labels": [_short(f["new"], 30) for f in todo[:12]], "count": n, "target": None, "done": not n,
            "nested": False, "reason": None if n else "done", "message": None}


def _apply_group(doc, g, values, report, born=None):
    """묶음 하나의 구조 편집(지우기 → 사본) — 글 바꾸기 할 일 [(묶음, 항목, 옛 순번, 새 순번, 새 값)]. born = 사본 id 를 모을 곳."""
    items, plan, tg = g["items"], g["plan"], g["target"]
    kind, tid = g["kind"], g["table"]
    if kind == "paragraph" and plan["copies"]:
        items = _apart(doc, g, items, plan["keep"], born)
    if kind == "paragraph":
        items = _unstray(doc, items, plan)
    tbl = report["tables"].setdefault(tid, {"removed": [], "origin": {}}) if tid else None
    region = list(_region(items)) if kind == "cols" else None   # 열 묶음 전체 열 — 표 너비를 지킬 범위
    labels = [_short(it["labelText"]) for it in items]
    for i in sorted(plan["drop"], key=lambda i: -items[i].get("span", (i, i))[0]):   # 아래(오른쪽)부터
        it = items[i]
        if kind == "paragraph":
            res = doc.delete_blocks(it["roots"][0], it["roots"][-1])
        elif kind == "rows":
            res = doc.delete_rows(tid, *it["span"])
        else:
            res = doc.delete_cols(tid, *it["span"], keep=tuple(region))
            region[1] -= it["span"][1] - it["span"][0] + 1
        if tbl is not None:
            tbl["removed"] += res.get("removed", [])
    copies, t = [], items[plan["template"]]
    roots, label = list(t["roots"]), t["label"]
    span = t.get("span")
    for k in range(plan["copies"]):
        if kind == "paragraph":
            m = doc.clone_blocks(roots[0], roots[-1])["map"]
            if t.get("solo"):   # 표 하나짜리 항목(추진일정 표) — 앞 표와 사본 사이에 빈 줄(사용자 10-30)
                gap = _gap(doc, g, roots[-1])
                if born is not None:
                    born.update(gap)
        elif kind == "rows":  # 항목 칸의 열만 복사 — 그 밖 칸(바깥 라벨)은 늘어나 공유(spec_표_편집 clone_rows)
            d = span[1] - span[0] + 1
            m = doc.clone_rows(tid, span[0] + k * d, span[1] + k * d, list(t["cross"]))["map"]
        else:
            d = span[1] - span[0] + 1
            m = doc.clone_cols(tid, span[0] + k * d, span[1] + k * d, keep=tuple(region))["map"]
            region[1] += d
        roots, label = [m.get(r, r) for r in roots], m.get(label, label)
        if born is not None:
            born.update(m.values())
        if tbl is not None:
            tbl["origin"].update({new: tbl["origin"].get(old, old) for old, new in m.items()})
        copies.append({**t, "roots": roots, "label": label, "copy": True})
    report["added"] += plan["copies"]
    report["removed"] += len(plan["drop"])
    report["groups"].append({"key": g["key"], "dim": g["dim"], "kind": kind, "from": len(items), "to": len(tg),
                             "table": tid, "labels": labels, "added": [c["label"] or c["roots"][0] for c in copies],
                             "removed": [labels[i] for i in sorted(plan["drop"])]})
    out = []
    for pos, (what, i) in enumerate(plan["order"]):
        it, ord_old = (items[i], i + 1) if what == "item" else (copies[i], plan["template"] + 1)
        out.append((g, it, ord_old, pos + 1, tg[pos]))
    return out


def _even_cols(doc, values, report, levels_of):
    """열을 늘리거나 줄인 표: 맨 안쪽 열 묶음(다른 열 묶음을 품지 않는 — 차년도·기관 열)의 항목들을 같은 폭으로, 그 열들의 너비 합·표
    너비는 그대로(10-30 [57] 「구분 기준에 따라 폭을 같게」). 항목 열이 맞닿아 이어질 때만 — 사이에 다른 열이 끼면 그대로."""
    tids = {g["table"] for g in report["groups"] if g["kind"] == "cols" and (g["added"] or g["removed"])}
    if not tids or not hasattr(doc, "even_cols"):
        return
    blocks = doc.blocks()
    by = {}
    for g in find(blocks, levels_of(blocks) if levels_of else {}, values):
        if g["kind"] == "cols" and g["table"] in tids:
            by.setdefault(g["table"], []).append(g)
    inside = lambda o, s: s != o and s[0] <= o[0] and o[1] <= s[1]  # noqa: E731
    for tid, gs in by.items():
        spans = [{it["span"] for it in g["items"]} for g in gs]
        leaf = sorted(set().union(*(ss for ss in spans
                                    if not any(inside(o, s) for s in ss for other in spans if other is not ss for o in other))))
        if len(leaf) < 2 or any(b[0] != a[1] + 1 for a, b in zip(leaf, leaf[1:])):
            continue
        try:
            doc.even_cols(tid, leaf)
        except ValueError as x:
            report["errors"].append({"key": tid, "dim": None, "message": str(x)})


def _gap(doc, g, after):
    """after 블록 뒤에 빈 문단 하나(묶음 앞 빈 문단을 본뜸) -> [새 id]."""
    return doc.insert_after(after, [{"kind": "paragraph", "text": "", **({"templateId": g["blank"]} if g.get("blank") else {})}])


def _unstray(doc, items, plan):
    """자리표시 항목의 라벨 바로 뒤 군더더기 빈 문단(_stray_blanks)을 지운다 — 남길 항목(이름을 넣을 것·본뜰 것)만, 지울 항목은 통째로 지워진다.
    -> 지운 블록을 뺀 항목 목록(roots·scope 갱신). 빈 문단만 지우므로 지워지는 글은 없다."""
    out = list(items)
    for i, it in enumerate(items):
        if not it.get("stray") or i in plan["drop"]:
            continue
        for sid in it["stray"]:
            doc.delete_blocks(sid, sid)
        gone = set(it["stray"])
        out[i] = {**it, "roots": [r for r in it["roots"] if r not in gone], "scope": it["scope"] - gone, "stray": []}
    return out


def _apart(doc, g, items, keep, born):
    """표 하나짜리 남길 항목이 앞 항목의 표와 한 문단에 나란히 들었으면(hwpx 글자처럼 — 양식의 추진일정 표 「1단계-1차년도」·
    「N단계-n차년도」) 그 표를 제 문단으로 옮기고 사이에 빈 줄 — 늘린 사본 사이 빈 줄과 같게. 뒤에서부터(셋 이상 나란해도 차례 유지).
    -> 옮긴 표의 새 id 로 바꾼 항목 목록. 나란할 수 있는 짝(남길 표 하나짜리 항목이 이어진 곳)이 없으면 문서를 읽지 않는다."""
    if not any(i in keep and i - 1 in keep and items[i].get("solo") and items[i - 1].get("solo") for i in range(1, len(items))):
        return list(items)
    idx, out = structure.index_blocks(doc.blocks()), list(items)
    for i in range(len(items) - 1, 0, -1):
        it, prev = items[i], items[i - 1]
        a, b = idx.get(prev["roots"][-1]) or {}, idx.get(it["roots"][0]) or {}
        if not (i in keep and i - 1 in keep and it.get("solo") and prev.get("solo")
                and a.get("inlineRow") and a.get("inlineRow") == b.get("inlineRow")):
            continue
        m = doc.clone_blocks(it["roots"][0], it["roots"][-1])["map"]
        doc.delete_blocks(it["roots"][0], it["roots"][-1])
        new = _gap(doc, g, prev["roots"][-1])
        out[i] = {**it, "roots": [m.get(r, r) for r in it["roots"]], "label": m.get(it["label"], it["label"])}
        if born is not None:
            born.update(m.values(), new)
    return out


def _region(items):
    """열 묶음 전체 열 범위(표 너비를 지킬 범위)."""
    spans = [it["span"] for it in items]
    return min(a for a, _ in spans), max(e for _, e in spans)


def _simulate(g, plan):
    """표 묶음의 지우기·사본을 격자에서 먼저 해 봄(table_grid) — 병합 칸이 걸려 못 하면 그 문구, 되면 None."""
    t, items = g["_t"], g["items"]
    cells = [grid.Cell(None, c["row"], c["col"], c["rowSpan"], c["colSpan"]) for c in t["cells"]]
    nr, nc = t["nRows"], t["nCols"]
    try:
        for i in sorted(plan["drop"], key=lambda i: -items[i]["span"][0]):
            a, e = items[i]["span"]
            if g["kind"] == "rows":
                grid.drop_rows(cells, nr, a, e)
                nr -= e - a + 1
            else:
                grid.drop_cols(cells, nc, a, e)
                nc -= e - a + 1
        a, e = items[plan["template"]]["span"]
        d = e - a + 1
        for k in range(plan["copies"]):
            if g["kind"] == "rows":
                c0, c1 = items[plan["template"]]["cross"]
                grid.clone(cells, nr, nc, a + k * d, e + k * d, c0, c1)
                nr += d
            else:
                grid.clone_cols(cells, nc, a + k * d, e + k * d)
                nc += d
    except ValueError as x:
        return str(x)
    return None


# ---- 양식 정리 (② §7) ---------------------------------------------------------------------------------------

OVERSEAS = re.compile(r"^\s*\[\s*국외기관")
OVERSEAS_NO = re.compile(r"^(\s*\[\s*국외기관)\s*\d*(\s*\((?:[^()]|\([^()]*\))*\))?")   # 번호 + 이름 괄호(괄호 한 겹 허용)
OVERSEAS_COLON = re.compile(r"^(\s*\[\s*국외기관명?)(?:\s*\d+)?(\s*:\s*)([^\]\n※]*?)(?=\s*\])")   # 보고서 「[국외기관명 : 이름]」 — 이름 = 쌍점 뒤
OUTSIDE = "연구개발기관외기관"
OVERSEAS_MAX = 10   # 국외기관 항목 블록 수 상한
PLACEHOLDER = re.compile(r"^\s*[oOㅇ○◦•\-]?\s*$")   # 빈 줄·글머리만 있는 자리표시 줄
# 각주 안내 줄 중 지시문(「… 기재합니다」·「… 기재할 것」·「건별로 작성」·「행을 추가‧삭제할 수 있음」·「… 해당하는 사항을」) — 기본으로
# 지움. 정의·공식(「* 기술료 산정방식 : …」·「* 수정직접비 = …」)·값 보기(「* 개발, 구매, 임대 등」)는 설명 줄 — force 로만(10-30 [f5])
INSTRUCT = re.compile(r"(?:기재|작성|입력|표기|표시|기술|선택|체크|첨부|제출|삭제|추가|수정|반영|기입)"
                      r"(?:합니다|할\s*것|하며|하고|함|하여|하세요|바람|요망|가능|할\s*수|\s*(?:$|[.)(]))|해당\s*하는\s*사항|해당사항")


# (FMM 의 양식 정리 cleanup_find·_notes·_guides·cleanup_apply 는 1차 범위 밖 — spec_구분_기준 ② §7, 여기 없음)

DATE_RE = re.compile(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})")
NO_NAME = re.compile(r"^(?:기관명(?:기입)?|기업명\d*|주관기관\(미입력\)|참여기관\d+|[○ㅇ]+|[Xx]{3,})?$")   # 빈칸 뺀 글 — 이름 아닌 자리표시


def read_values(blocks, levels):
    """문서에 들어 있는 구분 값 -> {"stages"?, "period"?, "subs"?, "current"?, "orgs": {"lead"?, "joint"?, "nonprofit"?, "outside",
    "overseas", "entrust"}} — 못 읽은
    것은 키가 없다(화면은 그 값을 지금 값 그대로 둠). 범위 검사는 하지 않는다(화면에서 적용할 때 norm_values 와 같은 검사)."""
    groups = find(blocks, levels, norm_values({"stages": [1] * MAX_STAGES}))   # 단계 10개 — 차년도 묶음 맥락(ctx)이 잘리지 않게
    out = {"orgs": _read_orgs(blocks, groups)}
    if st := _read_stages(groups):
        out["stages"] = st
    if p := _read_period(blocks):
        out["period"] = p
    if subs := _read_subs(blocks):
        out["subs"] = subs
    cur = _vote(_read_current(blocks))
    if cur and st and 1 <= cur[0] <= len(st) and 1 <= cur[1] <= st[cur[0] - 1]:
        out["current"] = sum(st[:cur[0] - 1]) + cur[1]
    return out


SUB_SLOT = re.compile(r"\(\s*세부\s*(\d+)\s*\)\s*주관연구개발기관\s*\(((?:[^()]|\([^()]*\))*)\)")
CUR_NUM = re.compile(r"(?<![0-9A-Za-z])(\d+)\s*단계\s*[,\-]?\s*(\d+)\s*차\s*년도")   # 채운 당해 라벨 「(1단계, 1차년도)」·「1단계 1차년도」


def _read_current(blocks):
    """표지 당해연도 행 — 「당해연도 개발기간(s단계, y차년도)」 칸, 또는 「해당연도」 칸 바로 오른쪽 칸(보고서)의 숫자 라벨 [(s, y)]."""
    out = []
    for t in structure.iter_blocks(blocks):
        if t.get("type") != "table":
            continue
        for c in t["cells"]:
            if not _bare(c["text"]).startswith(("당해연도", "해당연도")):
                continue
            right = next((x for x in t["cells"] if x["row"] == c["row"] and x["col"] == c["col"] + c["colSpan"]), None)
            m = CUR_NUM.search(c["text"] or "") or (right and CUR_NUM.search(right["text"] or ""))
            if m:
                out.append((int(m.group(1)), int(m.group(2))))
    return out


def _read_subs(blocks):
    """세부과제 주관기관 이름 — 「(세부k)주관연구개발기관(이름)」 라벨, 번호마다 가장 많은 것. 이름이 하나도 없으면 None."""
    names = {}
    for b in structure.iter_blocks(blocks):
        if b.get("type") == "paragraph":
            for m in SUB_SLOT.finditer(b.get("text") or ""):
                if (x := _name(m.group(2))):
                    names.setdefault(int(m.group(1)), []).append(x)
    return [_vote(names.get(k, [])) or "" for k in range(1, max(names) + 1)] if names else None


def _vote(xs):
    """가장 많은 값(같으면 먼저 나온 것) — 없으면 None."""
    return Counter(xs).most_common(1)[0][0] if xs else None


def _seq(g):
    """묶음 항목 값이 1, 2, … 차례인 정수면 그 수 — 아니면 None(자리표시 N·어긋난 차례)."""
    vals = [it["value"] for it in g["items"]]
    return len(vals) if vals == list(range(1, len(vals) + 1)) else None


def _name(text):
    t = re.sub(r"\s+", " ", (text or "").strip())
    return "" if NO_NAME.match(t.replace(" ", "")) else t


def _read_stages(groups):
    """단계별 차년도 — 어긋나지 않은 묶음마다 한 표, 가장 많은 것: 단계-차년도 묶음(값이 (1,1)…(S,n) 차례), 단계 묶음 수 × 단계마다
    그 안 차년도 묶음 수. 둘 다 없으면 차년도 묶음 수 하나(단계 라벨이 없는 1단계 과제). 자리표시(N)만 있는 양식이면 None."""
    ok = [g for g in groups if not g.get("irregular")]
    votes = []
    for g in ok:
        vals = [it["value"] for it in g["items"]]
        if g["dim"] == STAGE_YEAR and all(isinstance(s, int) and isinstance(y, int) for s, y in vals):
            st = [sum(s == k for s, _ in vals) for k in range(1, max(s for s, _ in vals) + 1)]
            if all(st) and vals == targets(STAGE_YEAR, {"stages": st}):
                votes.append(tuple(st))
    n = _vote([k for g in ok if g["dim"] == STAGE and (k := _seq(g))])
    if n:
        st = [_vote([k for g in ok if g["dim"] == YEAR and g["ctx"] == s and (k := _seq(g))]) for s in range(1, n + 1)]
        if all(st):
            votes.append(tuple(st))
    if not votes and not n:
        t = _vote([k for g in ok if g["dim"] == YEAR and g["ctx"] is None and (k := _seq(g))])
        if t:
            votes.append((t,))
    st = _vote(votes)
    return list(st) if st else None


def _read_period(blocks):
    """사업기간 — 표 「전체」 라벨 행의 「YYYY. MM. DD - YYYY. MM. DD」(표지 연구개발기간)·「전체 연구개발기간」 오른쪽 칸(② §8 의 전체 기간
    자리)에 적힌 날짜 중 가장 많은 것 -> {start, end} | None(자리표시 「YYYY. MM. DD」뿐)."""
    spans = []

    def add(text):
        d = DATE_RE.findall(text or "")
        if len(d) >= 2:
            try:
                a, b = (date(*map(int, x)) for x in d[:2])
            except ValueError:
                return
            if a <= b:
                spans.append((a.isoformat(), b.isoformat()))

    for t in structure.iter_blocks(blocks):
        if t.get("type") != "table":
            continue
        cells = t["cells"]
        rows = lambda c: set(range(c["row"], c["row"] + (c.get("rowSpan") or 1)))   # noqa: E731
        for c in cells:
            for p in _paras(c):
                m = SPAN_RE.search(p.get("text") or "")
                if m and any(_bare(x.get("text")).startswith("전체") for x in cells
                             if x["col"] + (x.get("colSpan") or 1) <= c["col"] and rows(x) & rows(c)):
                    add(m.group())
            bare = _bare(c.get("text"))
            if bare.startswith("전체연구개발기간") and len(bare) <= 15:
                right = next((x for x in cells if x["row"] == c["row"] and x["col"] == c["col"] + (c.get("colSpan") or 1)), None)
                if right:
                    add(right.get("text"))
    p = _vote(spans)
    return {"start": p[0], "end": p[1]} if p else None


def _read_orgs(blocks, groups):
    """기관 — 이름은 문서 곳곳의 「주관/공동연구개발기관k(이름)」·「… : 이름」 라벨(구분 반영이 이름을 쓰는 자리)에서 k 마다 가장 많은 것,
    주관은 없으면 표지 「주관연구개발기관 | 기관명 | 이름」. 공동 수 = 번호 붙은 공동 라벨의 가장 큰 번호(이름이 있는 번호 우선) — 번호
    라벨이 없으면 모름. 비영리 = 7-3 비영리기관 현황(또는 종류 없는 일반 현황) 표 기관 열엔 있고 기업 현황 표엔 없는 기관(두 표 다
    이름이 없으면 모름).
    외 기관 = 표지 외 기관 행 중 글이 있는 행의 기관명 칸, 국외기관 = 2-2 「[국외기관k(이름)]」 — 자리표시 이름은 세지 않는다."""
    idx = structure.index_blocks(blocks)
    text = lambda i: (idx.get(i) or {}).get("text") or ""   # noqa: E731
    lead, joint, top = [], {}, 0
    for b in structure.iter_blocks(blocks):
        if b.get("type") != "paragraph":
            continue
        for rx in (SLOT_PAREN, SLOT_COLON):
            for m in rx.finditer(b.get("text") or ""):
                if SUB_RE.search(b["text"][max(0, m.start() - 8):m.start()]):
                    continue   # 「(세부k)주관연구개발기관(…)」 = 세부과제 주관기관(_read_subs)
                role, k = ORG_RE.match(m.group(1)).group(1, 4)
                name = _name(m.group(2))
                if role == "주관":
                    lead += [name] if name else []
                elif k and k.isdigit():
                    if name or re.fullmatch(r"참여기관\d+", m.group(2).strip()):   # 이름 없이 반영한 공동(기본 이름) — 양식 자리표시는 안 셈
                        top = max(top, int(k))
                    if name:
                        joint.setdefault(int(k), []).append(name)
    out = {}
    lead = _vote(lead) or _cover_lead(blocks)
    if lead:
        out["lead"] = lead
    if n := max(joint, default=0) or top:
        out["joint"] = [_vote(joint.get(k, [])) or "" for k in range(1, n + 1)]
        heads = {kind: [_bare(text(it["label"])) for g in groups if g.get("orgCols") == kind for it in g["items"]
                        if _name(text(it["label"]))] for kind in ("all", "firm", "np")}
        hit = lambda name, kind: any(name and (name in h or h in name) for h in heads[kind])   # noqa: E731
        if heads["firm"] or heads["np"]:   # 기업 현황 표에도 있으면 비영리 아님(비영리기관 현황 표에 전부 넣던 예전 반영본)
            out["nonprofit"] = [(hit(x, "np") or hit(x, "all")) and not hit(x, "firm")
                                for x in map(_bare, [out.get("lead", "")] + out["joint"])]
    for kind in ("outside", "entrust"):   # 표지 외 기관·위탁 목록 행 — 글이 있는 행의 기관명 칸
        rows = next((g for g in groups if g["dim"] == ORG and g["items"][0]["value"][0] == kind and g["table"]), None)
        out[kind] = [x for it in (rows["items"] if rows else ()) if any(text(r).strip() for r in it["roots"])
                     and it.get("nameAt") is not None and (x := _name(text(it["roots"][it["nameAt"]])))]
    named = [tuple(x for it in g["items"] if (x := _overseas_name(text(it["label"]))))
             for g in groups if g["dim"] == ORG and g["items"][0]["value"][0] == "overseas"]
    out["overseas"] = list(_vote(named) or ())
    return out


def _overseas_name(label):
    """국외기관 라벨의 이름 — 「[국외기관k(이름)]」 괄호 안, 보고서 「[국외기관명k : 이름]」 쌍점 뒤(자리표시·빈 것은 "")."""
    if (m := OVERSEAS_COLON.match(label)):
        return _name(m.group(3))
    m = OVERSEAS_NO.match(label)
    return _name((m.group(2) or "").strip()[1:-1]) if m else ""


def _cover_lead(blocks):
    """표지 「주관연구개발기관」 칸이 걸친 행의 「기관명」 오른쪽 칸 글(자리표시면 "")."""
    return _name(c["text"]) if (c := _cover_lead_cell(blocks)) else ""


def _cover_lead_cell(blocks):
    """표지 「주관연구개발기관 | 기관명 | (칸)」의 그 칸 — 없으면 None."""
    for t in structure.iter_blocks(blocks):
        if t.get("type") != "table":
            continue
        for c in t["cells"]:
            if _bare(c["text"]).startswith("주관연구개발기관") and len(_bare(c["text"])) <= 12:
                rs = range(c["row"], c["row"] + c["rowSpan"])
                k = next((x for x in t["cells"] if x["row"] in rs and _bare(x["text"]) == "기관명"), None)
                r = k and next((x for x in t["cells"] if x["row"] == k["row"] and x["col"] == k["col"] + k["colSpan"]), None)
                if r:
                    return r
    return None
