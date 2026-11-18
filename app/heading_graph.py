"""헤딩 추출 2단계 — 헤딩 그래프 · 템플릿(가지 규칙) · 조정(spec_헤딩_추출 ② §6). 문서를 바꾸지 않는다.

흐름(2026-11-09 사용자 확정 「템플릿 가지 규칙」 + astra 협의): 1단계 결과 → 후보 노드 → 헤딩 유형 표 → **A 호출**(유형마다 role·basis·variantOf·
**parents** = 보통 매달리는 부모 레터, 본문 **주 사슬** 확인) → **부모 초안**(스크립트 — 흐름마다 열린 노드 스택, 같은 레터 = 형제, 부모로 받아들여지는 항목의
자식, 라벨은 제 템플릿의 뿌리) → **B 호출**(본문 구간마다 초안과 다른 노드만 — 부모·역할 + 슬롯 예외) → 확정 트리 위에서 **사슬 학습 ↔ 슬롯 배정**(고정점) →
템플릿 **id 동결**·앵커 → **C**(슬롯 서식 쌍 조정) → **D**(재검토) → 인스턴스·이종 형제·조정.
템플릿 = 레터 계열 **사슬** 하나(key = scope:사슬 = 앵커). 가지 자리(한 부모 아래 레터가 둘 이상)마다 새 템플릿이 뿌리(L1)를 내리고, 같은 사슬 꼴은 어디에 매달려도
같은 템플릿(정의 1 + 인스턴스 여럿). 구분 라벨은 그 라벨부터 새 템플릿(라벨 = L1). LLM 이 없거나 실패하면 역할·부모는 스크립트 어림(`heuristic` 표지).
**잇닿은 사슬**(2026-11-17 사용자 "레터가 다르거나 하지 않고 늘어나면 같은 템플릿으로" — spec ② §6 「잇닿은 사슬」): 템플릿을 가르는 것은 레터가 다를 때뿐 — 문서 맨 위에 매달린 줄의 레터가
주 사슬에 있으면 주 사슬의 그 레벨, 부모 템플릿의 더 깊은 레벨 레터면(레벨 건너뜀) 그 레벨이고(`assign_templates`), 받아 줄 부모가 열려 있지 않은 줄은 문서 맨 위로 보내며 열린 줄을 닫지 않고
가장 가까운 더 얕은 줄에 어림으로 붙인다(`_shallower`).
**띠 표 줄**(2026-11-17 사용자 "테이블도 헤딩레벨로 … 별첨, 부록 appendix" → 답 「제 템플릿으로」 · 「헤딩 추출이 스스로」 — spec ② §6 「띠 표 줄」): 본문의 이름표 띠 표(「별첨2 | 제목」 —
`heading_bands.find`)는 kind `band` 의 본문 흐름 노드다(열쇠 = 이름표 문단 · 레터 = 이름표 글 · 제목 = 제목 칸의 글). 역할·부모·템플릿은 스크립트가 정한다 — 늘 헤딩이고 문서 맨 위,
이름표 꼴(「별첨N」)이 레터인 제 템플릿(kind band — 번호는 맨 뒤)의 L1. 그 아래 줄은 다음 띠 표나 주 사슬 첫 레터(장)가 올 때까지 그 줄의 자식이고, 띠 표 줄은 템플릿 사슬에 투명하다
(자식의 템플릿·레벨은 문서 맨 위에 매달린 줄처럼 — 띠 표 템플릿은 L1 하나뿐)."""
import json
import re
import time
from collections import Counter, defaultdict

from app import division_terms as DT
from app import heading_bands as HB
from app import heading_llm as HL
from app import heading_rules as R
from app import llm
from app.division_terms import BASES, BASIS_SEP, label_shape, value_basis  # noqa: F401 — 구분 기준 값의 글 꼴은 구분 기준 쪽(division_terms)이 원본(2026-11-18) · 이 모듈 이름으로도 그대로 부른다

TITLE_MAX = 60
SECTION_MAX = 120
CHANGE_RATE_RETRY = 0.3
MAX_ROUNDS = 12
SENT_END = re.compile(r"(?:다|음|함|요|임)\.\s*$")
VARIANTS = {"circle": "o", "latin-o": "o", "jamo-o": "o", "dash": "-", "dot": "·", "square": "□", "triangle": "△", "small-square": "▫",
            "diamond": "◇", "arrow": "▶", "colon": ":"}
ROLES = ("heading", "label", "subtitle", "title", "note", "not_heading")
ROOTED = ("label", "subtitle")  # 대괄호 줄 — 구분 라벨·괄호 소제목: 둘 다 그 줄부터 새 템플릿(L1). 구분 소속(division)은 구분 라벨만(spec ② §13)
SUB_KEY = "[…]"  # 괄호 소제목의 정규 키
BARE_KEYS = (SUB_KEY, "[라벨]")  # 구분 기준 이름이 없는 대괄호 키 — 묶음을 (키, 앞 공백)으로 가른다(「[라벨]」 = 옛 결과·basis 없는 라벨)
BRACKET_RULE = 2  # 괄호 줄 판정 규칙(bracket_role)의 판 — 결과에 남긴다(규칙이 바뀌면 올림). 2 = 구분 기준 판독(2026-11-18 — 글 꼴 다음 차례)
KIND_ORDER = {"main": 0, "branch": 1, "label": 2, "cell": 3, HB.KIND: 4}  # 띠 표 템플릿은 맨 뒤 번호(있던 템플릿의 번호를 밀지 않는다)
MAIN = ("body", "main")  # 주 사슬 템플릿 키


# ---- 후보 노드 · 유형 ------------------------------------------------------------------------------------

_SPECIAL = ("shape", "caption", "header", "footer", "footnote", "endnote", "master")


def _flow(rec):
    """흐름 — 본문은 "body", 표 칸은 칸마다, 글상자·머리말·각주 …는 그 그릇마다(1단계 사슬의 key — 없는 옛 결과는 옛 꼴).
    1칸 상자는 투명 — 바깥 그릇의 흐름(본문이면 본문, 여러 칸 표 칸 안이면 그 칸)."""
    path = rec.get("path") or []
    for i in range(len(path) - 1, -1, -1):  # 안쪽 그릇부터
        c = path[i]
        if c["t"] == "cell":
            if i and path[i - 1]["t"] == "tbl" and path[i - 1].get("cells") == 1:
                continue  # 1칸 상자 — 건너뜀
            return f"cell:{c['id']}" if c.get("id") else (f"cell:k{c['key']}" if c.get("key") else "cell:None")
        if c["t"] in _SPECIAL:
            return f"{c['t']}:{c['key'] if c.get('key') else json.dumps(c, sort_keys=True)}"
    return "body"


def _scope(flow):
    """템플릿 scope — 본문(글상자·머리말 같은 다른 그릇 포함) | 표 칸."""
    return "cell" if flow.startswith("cell:") else "body"


def _body_size(paras):
    c = Counter((r["char"]["text"] or {}).get("sizePt") for r in paras if r["kind"] == "plain" and r["area"] == "body" and r["text"].strip())
    return c.most_common(1)[0][0] if c else 10.0


def filled_flows(paras):
    """흐름(본문 · 표 칸 …)마다 「내용이 있는」 문단 수 — 글이 있거나, 개체(표 · 그림 · 상자)를 지녔거나, 자동 번호가 붙은 문단. 값 칸은 그 칸의 흐름에 그런 문단이 하나뿐일 때다
    (개요 오버레이 쪽의 같은 셈: outline_match.lone_value — 그 칸의 다른 문단에 글·개체가 있으면 값 칸이 아니다)."""
    return Counter(_flow(r) for r in paras if r["text"].strip() or r.get("objects") or r.get("num"))


def value_cell(rec, filled):
    """값 칸(spec ② §6 「값 칸」 — 2026-11-16): 여러 칸 표의 칸(1칸 상자는 투명)에 **글이 있는 문단이 그것 하나뿐이고 레터만 있는**(제목 없음) 문단 — 표의 빈 값 「-」 · 번호 칸 「1.」.
    레터 꼴이어도 개요 줄이 아니라 값이라 헤딩 후보에 넣지 않는다(노드·유형·템플릿을 주지 않는다 — 그 칸이 글머리 서식으로 맞춰지던 것: ① 2026-11-16 검토).
    filled = 흐름마다 글이 있는 문단 수. 구분 라벨(대괄호 줄)은 값이 아니다."""
    if rec["kind"] != "marker" or not rec["blank"] or (rec.get("rest") or "").strip():
        return False
    flow = _flow(rec)
    return flow.startswith("cell:") and filled.get(flow, 0) == 1


def candidates(stage1, skip=()):
    """헤딩 후보 노드(문서 순) — marker·label 구간, 개요·번호 문단, 제목 같은 plain(본문·상자, 짧고 굵거나 본문보다 큰 글), 강제 줄 바꿈 뒤 marker·label 줄.
    skip = 후보에서 뺄 문단 id(TEMP 라벨 — 표 안 작성요령·쓸 자리, spec ② §15): 노드·유형·템플릿을 주지 않는다."""
    paras = stage1["paras"]
    body = _body_size(paras)
    filled = filled_flows(paras)  # 흐름(칸)마다 글·개체가 있는 문단 수 — 값 칸을 가린다
    bands = HB.find(paras, skip)  # 이름표 띠 표(「별첨N | 제목」 — spec ② §6 「띠 표 줄」): 이름표 문단 id → 띠 표
    out = []
    for rec in paras:
        if rec["id"] in skip:
            continue
        b = bands.get(rec["id"])
        if b is not None:  # 띠 표 줄 — 그 표가 놓인 본문 흐름의 줄: 레터 = 이름표 글(「별첨2」), 제목 = 제목 칸의 글. 열쇠는 이름표 문단
            ch = rec["char"]["text"] or {}
            out.append({"para": rec["id"], "n": rec["n"], "area": rec["area"], "flow": "body", "table": rec["table"], "cell": rec["cell"], "lead": 0, "fmt": rec["fmt"],
                        "bold": bool(ch.get("bold")), "size": ch.get("sizePt") or 0, "id": rec["id"], "span": 0, "kind": HB.KIND, "family": HB.KIND, "shape": b["key"],
                        "letter": b["letter"], "blank": False, "text": b["text"][:80], "outline": None,
                        "band": {"table": b["table"], "title": b["title"], "host": b["host"]}})
            continue
        if value_cell(rec, filled):
            continue
        size = (rec["char"]["text"] or {}).get("sizePt") or 0
        bold = bool((rec["char"]["text"] or {}).get("bold"))
        first = rec["text"].strip().split(R.BR, 1)[0]
        base = {"para": rec["id"], "n": rec["n"], "area": rec["area"], "flow": _flow(rec), "table": rec["table"], "cell": rec["cell"],
                "lead": rec["leadSpaces"], "fmt": rec["fmt"], "bold": bold, "size": size}
        kind = None
        if rec["kind"] in ("marker", "label"):
            kind = rec["kind"]
        elif rec.get("num") or rec.get("outlineLevel"):
            kind = "outline"
        elif (rec["kind"] == "plain" and base["flow"] == "body" and 0 < len(first) <= TITLE_MAX and not SENT_END.search(first)
              and (bold or size >= body + 1)):  # 칸 안 상자 글은 칸 글처럼 제목 후보 아님
            kind = "title"
        if kind:
            out.append({**base, "id": rec["id"], "span": 0, "kind": kind, "family": rec["family"], "shape": rec["shape"], "letter": rec["letter"],
                        "blank": rec["blank"], "text": (rec["rest"] if kind in ("marker", "label") else rec["text"]).strip().split(R.BR, 1)[0][:80],
                        "outline": rec.get("outlineLevel")})
        for sp in rec["spans"][1:]:
            if sp.get("inline") and kind == "marker" and sp["kind"] == "marker":  # 줄 안 레터(spec ② §2 — 「o (제목) ① …」 의 「①」): 그 줄 노드 아래 노드 · 글 = 둘째 레터 뒤
                after = rec["text"][sp["start"] + len(sp["letter"]):].split(R.BR, 1)[0]
                out.append({**base, "id": f"{rec['id']}#{sp['i']}", "span": sp["i"], "kind": "marker", "family": sp["family"],
                            "shape": R.shape_of(sp["family"], sp["letter"]), "letter": sp["letter"], "blank": False, "text": after.strip()[:80],
                            "outline": None, "inline": True})
            elif sp["line"] and sp["kind"] in ("marker", "label"):
                line = rec["text"].split(R.BR)[sp["line"]]
                out.append({**base, "id": f"{rec['id']}#{sp['i']}", "span": sp["i"], "kind": sp["kind"], "family": sp["family"],
                            "shape": R.shape_of(sp["family"], sp["letter"]), "letter": sp["letter"], "blank": False, "text": line.strip()[:80],
                            "outline": None})
    return out


def _shape_key(node):
    if node["kind"] == "label":
        return label_shape(node["letter"])
    if node["kind"] == "title":
        return "제목"
    if node["kind"] == "outline":
        return f"개요{node['outline'] or '?'}"
    return node["shape"] or node["letter"].strip()


def type_table(nodes):
    """노드마다 유형 id 를 달고 유형 표 → {Tn: {type, area, kind, shape, bold, size, count, examples, lead, labels, prev, next, blank, family}}."""
    keys, types = {}, {}
    for nd in nodes:
        key = ("cell" if nd["flow"].startswith("cell:") else "body", nd["kind"], _shape_key(nd), nd["bold"], round(nd["size"] or 0))  # 칸 안 상자도 칸
        if key not in keys:
            keys[key] = f"T{len(keys) + 1}"
            types[keys[key]] = {"type": keys[key], "area": key[0], "kind": key[1], "shape": key[2], "bold": key[3], "size": key[4],
                                "family": nd["family"], "count": 0, "examples": [], "lead": Counter(), "labels": Counter(), "prev": Counter(),
                                "next": Counter(), "blank": 0}
        nd["type"] = keys[key]
        t = types[nd["type"]]
        t["count"] += 1
        t["lead"][nd["lead"]] += 1
        t["labels"][nd["fmt"]] += 1
        t["blank"] += nd["blank"]
        if len(t["examples"]) < 3 and nd["text"] and nd["text"] not in t["examples"]:
            t["examples"].append(nd["text"][:50])
    last = {}
    for nd in nodes:
        p = last.get(nd["flow"])
        if p is not None:
            types[p["type"]]["next"][nd["type"]] += 1
            types[nd["type"]]["prev"][p["type"]] += 1
        last[nd["flow"]] = nd
    for t in types.values():
        for k in ("lead", "labels", "prev", "next"):
            t[k] = dict(t[k].most_common(3))
    return types


def sketch(nodes, limit=260):
    """A 호출 맥락 — 본문 흐름 후보를 문서 순 한 줄씩(「T3 _2 □ 연구개발…」). 많으면 앞에서 limit 줄 + 드문 유형(3회 이하)의 나머지."""
    body = [nd for nd in nodes if nd["flow"] == "body"]
    cnt = Counter(nd["type"] for nd in body)
    pick = body[:limit] + [nd for nd in body[limit:] if cnt[nd["type"]] <= 3]
    return [f"{nd['type']} _{nd['lead']} {nd['letter'] or ''} {nd['text'][:40]}".strip() for nd in pick]


# ---- 역할 · 정규 레터 키 -----------------------------------------------------------------------------------

_CHECK = re.compile(r"[\s√✓✔☑☐vVoOㅇ○●◯xX×✗✘□■]*")  # 빈 대괄호·체크 표시뿐인 대괄호 안(「[  ]」「[ √ ]」)
_SENTENCE = re.compile(r"(?:을|를|은|는|의|에|에서|으로|로|와|과|에게|부터|까지)\s")  # 괄호 뒤 글이 조사로 시작 = 문장 속 괄호
BY_USER = "사용자 지정"  # 역할의 까닭 — 사용자 라벨 지정으로 정한 것(문장 속 괄호 판정보다 앞선다)
_BRACKETS = DT.BRACKETS
_inner = DT.inner
BASIS_BAD = re.compile(r"[\[\]›|:\s\-–·․/,+…]|^라벨$")  # 사용자가 더하는 구분 기준 이름에 못 쓰는 글자·예약어(정규 키·앵커의 구분자)
# 구분 기준 값의 글 꼴(value_basis · label_shape · BASES · BASIS_SEP)은 app/division_terms.py 가 원본(2026-11-18 — 구분 기준 판독과 함께 씀)


def bases_of(hints=None):
    """구분 기준 목록 — 기본(단계·차년도·기관) + 사용자가 더한 이름(hints.bases — 지정을 지워도 남는다) + 지정에 적힌 이름."""
    out = list(BASES)
    extra = list((hints or {}).get("bases") or []) + [h.get("basis") for h in ((hints or {}).get("labels") or {}).values() if h.get("role") == "label"]
    for b in extra:
        for part in str(b or "").split(BASIS_SEP):
            if part.strip() and part.strip() not in out:
                out.append(part.strip())
    return out


_BASIS_ALIAS = (("차년도", re.compile(r"차년도|연차|년차")), ("기관", re.compile(r"기관")), ("단계", re.compile(r"단계")))


def norm_basis(basis, bases=BASES):
    """LLM 이 적은 구분 기준 이름 → 목록(bases)의 이름(겹친 것은 목록 차례로 이음 「단계-차년도」) | ""(목록 밖 — 지어낸 이름이 하나라도 섞임).
    흔한 다른 적기(연차·년차 → 차년도, 연구개발기관 → 기관)는 맞춘다."""
    parts = [x for x in re.split(r"[\s\-–·․/,+]+", str(basis or "")) if x]
    got = []
    for x in parts:
        name = x if x in bases else next((n for n, pat in _BASIS_ALIAS if n in bases and pat.search(x)), None)
        if name is None:
            return ""
        got.append(name)
    return BASIS_SEP.join(n for n in bases if n in got)


def hint_of(hints, letter):
    """그 대괄호 글 꼴에 사용자가 한 지정 {role: label|subtitle, basis, …} | None."""
    h = ((hints or {}).get("labels") or {}).get(label_shape(letter))
    if not h or h.get("role") not in ROOTED or (h["role"] == "label" and not str(h.get("basis") or "").strip()):
        return None
    return h


BY_SCAN = "구분 기준 판독"  # 역할의 까닭 — 구분 기준 판독(division_scan — 연구개발과제 문서에서 헤딩 앞에 도는 스크립트)이 이 유형의 줄 모두를 그 구분 기준 값으로 확인한 것


def bracket_role(letter, hints=None, role=None, basis="", div=None):
    """괄호 줄(1단계 kind label — 「[…]」「【…】」·배운 괄호 규칙) 하나의 역할 → (role, basis, 까닭). A·B·사용자 지정·LLM 없는 판정이 모두 이 한 규칙을 거친다(spec ② §13).
    role·basis = LLM(A·B)이 본 것(없으면 None). div = 구분 기준 판독이 **이 유형의 줄 모두**를 같은 구분 기준으로 확인했을 때 그 이름(division_scan.type_bases — 일부만이면 None).
    차례: ① 사용자 지정 ② 빈 대괄호·체크 칸 = 헤딩 아님 ③ 글이 구분 기준 값으로 시작하는 꼴(value_basis) = 구분 라벨
    ④ 구분 기준 판독(div) = 구분 라벨(2026-11-18 사용자 「구분기준은 첫번째 … 헤딩은 마지막 결과를 참조」 — 글 꼴 다음: 엔진은 「[주관연구개발기관(1단계)]」 를 단계로 읽는다(Fable 협의).
    판독이 못 정한 것은 「아님」 이 아니라 「모름」 — 아래로) ⑤ LLM 이 헤딩 아님·안내로 본 것은 그대로 ⑥ LLM 이 label 로 보고 적은 basis 가 구분 기준 목록에 있음 = 구분 라벨(「[한국선급]」 → 기관)
    ⑦ 그 밖 = 괄호 소제목(LLM 이 목록 밖 이름을 지어냈으면 까닭에 남김)."""
    h = hint_of(hints, letter)
    if h:
        return h["role"], (str(h["basis"]).strip() if h["role"] == "label" else ""), BY_USER
    s = (letter or "").strip()
    if s[:1] in ("[", "【") and _CHECK.fullmatch(_inner(s)):
        return "not_heading", "", "빈 대괄호·체크 칸"
    b = value_basis(s)
    if b:
        return "label", b, ""
    if div:
        return "label", div, BY_SCAN
    if role in ("not_heading", "note"):
        return role, "", ""
    b = norm_basis(basis, bases_of(hints)) if role == "label" else ""
    if b:
        return "label", b, ""
    return "subtitle", "", (f"구분 기준이 아닌 「{str(basis)[:20]}」 — 괄호 소제목" if role == "label" and basis else "")


def _div_basis(divt, tid, bases=BASES):
    """구분 기준 판독(divt = hints["_divTypes"] — division_scan.type_bases)이 그 유형의 줄 **모두**를 같은 구분 기준으로 확인했으면 그 이름(구분 기준 목록에 있는 것만 — 세부과제는 아님) | None."""
    b = ((divt or {}).get(tid) or {}).get("basis")
    return norm_basis(b, bases) or None if b else None


def _bracket_key(role, basis):
    """대괄호 줄의 정규 키 — 구분 라벨 「[기준]」 · 괄호 소제목 「[…]」 · 헤딩 아님·안내 None."""
    return "[" + (basis or "라벨") + "]" if role == "label" else SUB_KEY if role == "subtitle" else None


def is_label_key(k):
    """구분 라벨의 정규 키(「[기관]」)인가 — 괄호 소제목 「[…]」 과 대괄호 번호 레터(「[N]」「[가]」)는 아니다."""
    return bool(k) and k.startswith("[") and k not in (SUB_KEY, "[N]", "[가]")


def _norm_parents(parents, bases):
    """A 가 적은 부모 레터 키 가운데 대괄호 키를 맞춘다 — 구분 기준이면 「[기준]」, 아니면(지어낸 「[측면]」·옛 「[라벨]」) 괄호 소제목 키 「[…]」
    (소제목 키만 「[…]」 로 바꾸고 내용 레터의 parents 를 그대로 두면 「o」 가 소제목에 안 붙는다 — astra 2026-11-10)."""
    out = []
    for p in parents or []:
        if p.startswith("[") and p.endswith("]") and p not in (SUB_KEY, "[N]", "[가]"):
            b = norm_basis(p[1:-1], bases)
            p = "[" + b + "]" if b else SUB_KEY
        if p not in out:
            out.append(p)
    return out


def _band_role():
    """띠 표 줄(이름표 띠 표 — heading_bands)의 유형 역할 — 늘 헤딩이고 부모는 문서 맨 위."""
    return {"role": "heading", "parents": ["root"], "variantOf": "", "basis": "", "reason": "별첨·부록 표 제목 — 문서 맨 위의 줄(스크립트)"}  # 화면(유형 표)에 보이는 글 — 「띠 표」 는 안쪽 말이라 쓰지 않는다


def settle_roles(types, roles, hints=None):
    """A 가 답한 역할을 규칙에 맞춘다(roles 를 고침; A 가 본 것은 aRole·aBasis 로 남김 — 사용자 지정을 지우면 여기로 돌아간다). 괄호 유형(kind label)은 bracket_role 이
    정하고, 그 밖의 유형이 구분 라벨이 되려면 basis 가 구분 기준 목록에 있어야 한다(아니면 스크립트 대체 역할 — 소제목은 괄호 줄만). parents 의 대괄호 키도 맞춘다."""
    bases = bases_of(hints)
    divt = (hints or {}).get("_divTypes")  # 구분 기준 판독(있을 때만 — 연구개발과제 문서): {유형 id: {basis, confirmed, total, conflict}}
    for tid, t in types.items():
        r = roles.get(tid) or {}
        raw = (r.get("role"), r.get("basis") or "")
        if t["kind"] == HB.KIND:  # 띠 표 줄 — 역할·부모는 스크립트가 정한다(A 의 답과 무관: 늘 헤딩 · 문서 맨 위 — spec ② §6 「띠 표 줄」)
            roles[tid] = {**r, **_band_role()}
            continue
        if t["kind"] == "label":
            role, basis, why = bracket_role(t["shape"], hints, raw[0], raw[1], div=_div_basis(divt, tid, bases))
            old = r.get("reason", "")
            roles[tid] = {**r, "aRole": raw[0], "aBasis": raw[1], "aReason": old, "role": role, "basis": basis, "parents": [], "variantOf": "", "hint": why == BY_USER,
                          "reason": f"{old} · {why}" if why and old.startswith("A 판정 없음") else why or old}
            continue
        r = roles[tid] = {**r, "parents": _norm_parents(r.get("parents"), bases)}
        if r.get("role") in ROOTED:
            b = norm_basis(r.get("basis"), bases) if r["role"] == "label" else ""
            if b and divt is not None and _div_basis(divt, tid, bases) != b:
                # 괄호 줄이 아닌 유형(「(N)」 — 「(1) 1차년도」 와 「(2) 기술목표」 가 한 유형)을 A 가 구분 라벨로 답해도 판독이 그 유형의 줄 **모두**를 그 구분 기준으로 확인하지 않았으면
                # 유형 전체로 퍼뜨리지 않는다(2026-11-18 astra P1). 판독이 없는 문서(연구개발과제가 아님)는 전과 같다
                d = (divt or {}).get(tid) or {}
                r.update(role="title" if t["kind"] == "title" else "heading", basis="", aRole=raw[0], aBasis=raw[1],
                         reason=f"구분 기준 판독이 이 유형의 줄 {d.get('total', 0)}개 가운데 {d.get('confirmed', 0)}개만 「{b}」 값으로 확인 — 유형 전체를 구분 라벨로 보지 않음")
                continue
            if b:
                r["basis"] = b
            else:
                r.update(role="title" if t["kind"] == "title" else "heading", basis="",
                         reason=f"구분 기준이 아닌 「{str(r.get('basis') or '')[:20]}」 — 구분 라벨로 보지 않음" if r["role"] == "label" else "괄호 줄이 아니라 소제목으로 보지 않음")


def _type_key(t, role):
    """유형 → 정규 레터 키(변형군 합침). 구분 라벨은 "[basis]", 괄호 소제목은 "[…]". 헤딩 아님·안내·제목(잎)은 None."""
    r = role.get("role") or "heading"
    if r in ("not_heading", "note", "title"):
        return None
    if r == "label":
        return "[" + (role.get("basis") or "라벨") + "]"
    if r == "subtitle" or t["kind"] == "label":
        return SUB_KEY
    if t["kind"] == "outline":
        return t["shape"]
    if t["kind"] == "title":
        return "제목"
    return VARIANTS.get(t.get("family") or "") or t["shape"] or "?"


def type_keys(types, roles):
    """{Tn: 정규 레터 키 | None} — A 의 variantOf(같은 레터로 볼 다른 유형)는 그 유형의 키. 구분 라벨·괄호 소제목은 변형군으로 합치지 않는다(키 = 역할·구분 기준)."""
    out = {tid: _type_key(t, roles.get(tid) or {}) for tid, t in types.items()}
    for tid, r in roles.items():
        v = r.get("variantOf")
        if v and v in out and out[v] and out.get(tid) and r.get("role") not in ROOTED and (roles.get(v) or {}).get("role") not in ROOTED \
                and HB.KIND not in (types[tid]["kind"], types[v]["kind"]):  # 띠 표 줄은 변형군으로 합치지 않는다
            out[tid] = out[v]
    return out


def fallback_roles(types, hints=None):
    """LLM 없이 — 대괄호 꼴은 bracket_role(구분 라벨·괄호 소제목·헤딩 아님 — 구분 기준 판독이 있으면 그것부터), 제목 꼴은 title, 그 밖 heading. 부모 지식 없음(초안은 어림)."""
    out, divt, bases = {}, (hints or {}).get("_divTypes"), bases_of(hints)
    for tid, t in types.items():
        role, basis, why = bracket_role(t["shape"], hints, div=_div_basis(divt, tid, bases)) if t["kind"] == "label" else ("title" if t["kind"] == "title" else "heading", "", "")
        out[tid] = {"role": role, "parents": [], "variantOf": "", "basis": basis, "reason": why or "스크립트 대체 판정", **({"hint": True} if why == BY_USER else {})}
        if t["kind"] == HB.KIND:
            out[tid] = _band_role()
    return out


# LLM 없는 어림의 계열 서열(얕음 → 깊음) — 한국어 개요의 흔한 차례. 보조 근거(앞 공백이 같을 때)로만 쓴다.
_RANK = {"chapter": 1, "roman-upper": 2, "section": 2, "hyphen": 4, "hangul-dot": 6, "paren-num": 7, "num-paren": 7, "hangul-paren": 8,
         "paren-hangul": 8, "circled": 9, "square": 10, "circle": 11, "latin-o": 11, "jamo-o": 11, "dash": 12, "dot": 13}


def _rank(nd):
    if nd["kind"] != "marker":
        return None
    if nd["family"] == "decimal":
        return 2 + (nd["shape"] or "N.").count("N")  # N. = 3, N.N. = 4, N.N.N. = 5
    return _RANK.get(nd["family"])


# ---- A 호출 --------------------------------------------------------------------------------------------

def a_job(types, nodes, keys, proposal, doc_name="", pinned=None, bases=BASES, division=None):
    rows = [{**{k: t[k] for k in ("type", "area", "kind", "shape", "bold", "size", "count", "examples", "lead", "prev", "next", "blank")}, "key": keys.get(t["type"]) or ""}
            for t in types.values()]
    data = {"document": doc_name, "bases": list(bases), "types": rows, "sketch": sketch(nodes), "mainChainProposal": list(proposal or [])}
    if division is not None:   # 구분 기준 판독(연구개발과제 문서 — §13 「구분 기준 판독」): 확인한 줄 · 엇갈린 줄 · 기관 이름 후보 줄의 수(근거가 있는 유형만)
        data["division"] = [{"type": tid, "basis": d.get("basis") or "", "confirmed": d["confirmed"], "of": d["total"], "conflict": d["conflict"], "names": d.get("names", 0)}
                            for tid, d in division.items() if d.get("confirmed") or d.get("conflict") or d.get("names")]
    content, used = HL.prompt(HL.TYPES_CONTRACT, ["graph", "templates", "tolerance"], data, pinned)
    return {"schema": HL.TYPES_SCHEMA, "content": content, "what": "heading_types", "timeout": 900.0, "effort": "medium"}, used, data


def apply_types(data, types):
    """A 응답 → (역할 {Tn: {role, parents[키…], variantOf, basis, reason}}, 주 사슬 [키…] | None). 모르는 유형은 버림, 레터 키는 아래서 다시 정규화."""
    roles = {}
    for it in (data or {}).get("types") or []:
        tid = it.get("type")
        if tid not in types:
            continue
        role = it.get("role") if it.get("role") in ROLES else "heading"
        parents = [str(p).strip() for p in (it.get("parents") or []) if str(p).strip()][:12]
        roles[tid] = {"role": role, "parents": parents, "variantOf": it.get("variantOf") if it.get("variantOf") in types else "",
                      "basis": str(it.get("basis") or "")[:20], "reason": str(it.get("reason") or "")[:200]}
    main = [str(k).strip() for k in (data or {}).get("mainChain") or [] if str(k).strip()]
    return roles, (main[:12] or None)


# ---- 부모 초안 -----------------------------------------------------------------------------------------

def _accepts(e, k, nd, rk, parents, main_next, trusted=True):
    """스택 항목 e 가 레터 k 노드의 부모로 받아들여지는가 → (받아들임, 어림이었나).
    지식(A 의 parents·주 사슬)이 있으면 그것만, 없으면 어림 — 서열이 더 얕은 항목(서열을 모르면 앞 공백이 더 적은 항목)이 부모. trusted = 주 사슬이 A 가 확인한 것
    (아니면 스크립트 제안이라 그것으로 정한 부모도 어림)."""
    if parents:
        if e["key"] in parents or main_next.get(e["key"]) == k:
            return True, False
        if e["label"] and any(p.startswith("[") for p in parents):
            # 괄호 줄(구분 라벨·소제목)인데 A 의 parents 에 그 키가 없다(소제목 키 「[…]」 를 빠뜨림 · 사용자가 새 구분 기준으로 지정한 라벨 「[관점]」) —
            # 괄호 줄 아래 오는 레터면 다른 괄호 줄 아래에도 온다: 닻보다 깊은 서열일 때 그 줄의 내용(어림)
            return (rk is not None and e["anchorRank"] is not None and rk > e["anchorRank"]), True
        return False, False
    if main_next.get(e["key"]) == k:
        return True, not trusted
    if e["label"]:  # 대괄호 줄(구분 라벨·괄호 소제목)의 닻(부모) 레터보다 깊은 서열이면 그 줄의 내용
        ar = e["anchorRank"]
        return (rk is None or ar is None or rk > ar), True
    er = e["rank"]
    if er is not None and rk is not None:  # 서열을 둘 다 알면 서열 — 더 얕은 레터만 부모(앞 공백이 거꾸로여도 — 양식은 「1-1.」 보다 「□」 를 덜 들여 쓰기도)
        return er < rk, True
    return e["lead"] <= nd["lead"], True  # 서열을 모르면 앞 공백 — 덜(또는 같게) 들여 쓴 쪽이 부모


def _shallower(st, k, rk, main_chain):
    """열린 줄 스택 st 에서 레터 k(서열 rk) 줄보다 **더 얕은** 가장 가까운 항목의 자리 | None — 받아 줄 부모가 열려 있지 않은 줄을 어림으로 붙일 곳(draft_parents).
    더 얕다 = 둘 다 주 사슬의 레터면 주 사슬에서 앞선 레벨, 아니면 둘 다 서열을 알 때 서열이 더 얕음. 서열을 모르는 레터(「▸」「∘」 — 주 사슬에도 없음)는 깊은 글머리로 보고
    가장 가까운 열린 줄. 괄호 줄(구분 라벨·소제목)은 건너뛴다(그 줄의 내용이 아니라고 이미 판정됨)."""
    at = {key: i for i, key in reversed(list(enumerate(main_chain or [])))}
    for i in range(len(st) - 1, -1, -1):
        e = st[i]
        if e["label"]:
            continue
        if k in at and e["key"] in at:
            if at[e["key"]] < at[k]:
                return i
        elif e["rank"] is not None and rk is not None:
            if e["rank"] < rk:
                return i
        elif rk is None and k not in at:
            return i
    return None


def draft_parents(nodes, roles, keys, main_chain, stage1, trusted=False):
    """부모 초안 → (graph {id: {id, para, type, role, key, parent, division, depth, heuristic}}, edges(contains·parent 그릇 간선), containers).
    흐름마다 열린 노드 스택: 노드마다 스택 위에서부터 — 같은 키 = 형제, 부모로 받아들여지는 항목 = 자식, 아니면 닫고 아래로. 라벨 = 같은 묶음 라벨이 열려 있으면
    그 닻까지 닫고 형제, 아니면 자식(라벨은 제 템플릿의 뿌리이므로 스택에 올린다). 헤딩 아님·안내·제목(잎)은 스택에 안 올림. trusted = main_chain 이 A 가 확인한 것."""
    by_para = defaultdict(list)
    for nd in nodes:
        by_para[nd["para"]].append(nd)
    graph, edges, containers = {}, [], {}
    stacks, divs = defaultdict(list), defaultdict(list)
    main_chain = list(main_chain or [])
    main_next = {main_chain[i]: main_chain[i + 1] for i in range(len(main_chain) - 1)}

    def flow_root(flow):
        return "root" if flow == "body" else (f"cell:{flow[5:]}" if flow.startswith("cell:") else f"area:{flow}")

    def top(flow):
        st = stacks[flow]
        return st[-1]["id"] if st else flow_root(flow)

    def div(dv):  # 열린 대괄호 줄 가운데 가장 안쪽 **구분 라벨**(괄호 소제목은 구분 소속이 아님)
        return next((x["id"] for x in reversed(dv) if x["label"]), None)

    for rec in stage1["paras"]:
        chain = rec["path"]
        for i, c in enumerate(chain):
            if c["t"] == "tbl" and c.get("id"):
                tid = f"tbl:{c['id']}"
                if tid not in containers:
                    outer = [x for x in chain[:i] if x["t"] == "cell"]
                    special = any(x["t"] in ("shape", "header", "footer", "footnote", "endnote", "caption") for x in chain[:i])
                    outer_flow = f"cell:{outer[-1]['id']}" if outer else (_flow(rec) if special else "body")
                    box = c.get("cells") == 1
                    containers[tid] = {"id": tid, "kind": "box" if box else "table", "parent": top(outer_flow), "host": c.get("host")}
                    edges.append({"t": "contains", "from": c.get("host") or top(outer_flow), "to": tid})
                    if not box:
                        edges.append({"t": "parent", "from": top(outer_flow), "to": tid})
            if c["t"] == "cell" and c.get("id"):
                cid = f"cell:{c['id']}"
                if cid not in containers:
                    tbl = chain[i - 1] if i and chain[i - 1]["t"] == "tbl" else None
                    containers[cid] = {"id": cid, "kind": "cell", "table": f"tbl:{tbl['id']}" if tbl else None, "row": c.get("row"), "col": c.get("col"),
                                       "parent": f"tbl:{tbl['id']}" if tbl else None}
                    if tbl:
                        edges.append({"t": "contains", "from": f"tbl:{tbl['id']}", "to": cid})
                        if tbl.get("cells") != 1:
                            edges.append({"t": "parent", "from": f"tbl:{tbl['id']}", "to": cid})
        for nd in by_para.get(rec["id"], ()):
            role = (roles.get(nd["type"]) or {}).get("role") or "heading"
            k = keys.get(nd["type"])
            flow = nd["flow"]
            st, dv = stacks[flow], divs[flow]
            g = {"id": nd["id"], "para": nd["para"], "type": nd["type"], "role": role, "key": k, "parent": None, "division": None, "depth": None,
                 "heuristic": False}
            if nd["kind"] == "label" and role in ROOTED and _SENTENCE.match(nd["text"]) and not (roles.get(nd["type"]) or {}).get("hint"):
                # 괄호 뒤에 조사로 문장이 이어짐(「[기술도입비 현물산정] 을 위해 아래와 같이 …」) — 문장 속 괄호이지 제목 줄이 아니다(유형이 아니라 이 줄만)
                role, k = "not_heading", None
                g.update(role=role, key=k, reason="괄호 뒤에 문장이 이어짐 — 헤딩 아님")
            if nd["area"] == "cell":
                edges.append({"t": "contains", "from": flow_root(flow), "to": nd["id"]})
            if k is None:  # 헤딩 아님·안내·제목 — 잎(스택을 흔들지 않음)
                g.update(parent=top(flow), division=div(dv), depth=float(len(st) + 1))
                graph[nd["id"]] = g
                continue
            if role in ROOTED:  # 구분 라벨·괄호 소제목 — 구조는 같다(그 줄부터 새 템플릿의 뿌리)
                cls = (k, nd["lead"]) if k in BARE_KEYS else k
                # 닫을 자리 = 열린 괄호 줄 가운데 ⓐ 같은 묶음(구분 라벨은 같은 구분 기준, 소제목은 같은 앞 공백)이거나 ⓑ 이 줄보다 덜 들여 쓰지 않은 **소제목**(소제목은 같은 깊이의
                # 다음 괄호 줄을 품지 않는다 — 「[최종목표]」 뒤 「[1차년도 목표]」 는 형제; 구분 라벨은 다른 기준의 라벨·소제목을 품는다 「[1단계] › [주관…]」) 중 가장 바깥.
                # 본문 루트에 닻 내린 소제목(문서 맨 앞 「[별지 제1호서식]」)은 다른 유형의 줄로는 안 닫는다(열린 개요를 루트까지 지우지 않게).
                same = min((j for j, e in enumerate(dv) if (e["cls"] == cls or (not e["label"] and e["lead"] >= nd["lead"]))
                            and not (not e["label"] and flow == "body" and e["anchor"] == "root" and e["type"] != nd["type"])), default=None)
                if same is not None:  # 그 줄의 닻까지 닫는다(이 줄은 그 줄의 형제)
                    anchor = dv[same]["anchor"]
                    del dv[same:]
                    ids = [e["id"] for e in st]
                    if anchor in ids:
                        del st[ids.index(anchor) + 1:]
                    elif anchor == flow_root(flow):
                        st.clear()
                parent = top(flow)
                st.append({"id": nd["id"], "key": k, "lead": nd["lead"], "rank": None, "label": True, "parent": parent,
                           "anchorRank": next((e["rank"] for e in reversed(st) if not e["label"]), None)})
                g.update(parent=parent, division=div(dv), depth=float(len(st)))
                dv.append({"id": nd["id"], "cls": cls, "anchor": parent, "type": nd["type"], "label": role == "label", "lead": nd["lead"]})
                graph[nd["id"]] = g
                continue
            if nd.get("inline") and st and st[-1]["id"] == nd["para"] and not st[-1]["label"]:
                # 줄 안 레터(spec ② §2 「줄 안 레터」 — 「o (제목) ① …」 의 「①」): 한 줄에 적은 것이 곧 부모·자식 — 그 줄의 첫 레터 아래(서열 · A 의 parents 와 상관없이:
                # 「①」 은 서열로는 「o」 보다 얕다). 뒤에 따로 선 「②」 는 같은 키라 이 노드의 형제(부모 = 그 줄)가 된다.
                # 스택의 서열은 그 줄보다 한 칸 깊게(sub) — 형제(「②」「③」)도 물려받아, 다음 「o」 줄이 서열로 「③」 아래에 들지 않고 「o」 의 형제가 된다
                hr = st[-1]["rank"]
                st.append({"id": nd["id"], "key": k, "lead": nd["lead"], "rank": (hr + 0.5) if hr is not None else _rank(nd), "label": False, "parent": nd["para"],
                           "anchorRank": None, "band": False, "sub": hr is not None})
                g.update(parent=nd["para"], division=div(dv), depth=float(len(st)), heuristic=False)
                graph[nd["id"]] = g
                continue
            parents = set((roles.get(nd["type"]) or {}).get("parents") or [])
            rk = _rank(nd)
            parent, heuristic, sub = None, False, False
            band = nd["kind"] == HB.KIND  # 띠 표 줄 — 늘 문서 맨 위(열린 줄을 모두 닫는다)
            for i in (() if band else range(len(st) - 1, -1, -1)):
                e = st[i]
                if not e["label"] and e["key"] == k:  # 같은 레터 = 형제
                    parent = e["parent"]
                    if e.get("sub"):  # 줄 안 레터의 형제 — 그 서열(그 줄보다 한 칸 깊게)을 물려받는다
                        rk, sub = e["rank"], True
                    del st[i:]
                    break
                if e.get("band"):  # 열린 띠 표 줄 — 다음 띠 표·주 사슬 첫 레터(장)가 올 때까지 그 아래 줄은 모두 그 줄의 것(spec ② §6 「띠 표 줄」)
                    ok, guessed = not (main_chain and main_chain[0] == k), False
                else:
                    ok, guessed = _accepts(e, k, nd, rk, parents, main_next, trusted)
                if ok:
                    parent, heuristic = e["id"], guessed
                    del st[i + 1:]
                    break
            if parent is None and parents and "root" not in parents and not (main_chain and main_chain[0] == k):
                # A 가 적은 부모 레터가 하나도 열려 있지 않다(「(3)」 바로 아래 「-」 — o 를 건너뜀). 문서 맨 위로 보내며 스택을 비우면 뒤의 형제 절(「5-3.」「5-4.」)까지
                # 열린 「5.」 를 잃고 맨 위에 매달려 따로 템플릿이 된다 — 가장 가까운 **더 얕은** 열린 줄에 어림으로 붙이고(레벨 건너뜀) 그 위 스택은 그대로 둔다
                i = _shallower(st, k, rk, main_chain)
                if i is not None:
                    parent, heuristic = st[i]["id"], True
                    del st[i + 1:]
            if parent is None:
                parent = flow_root(flow)
                heuristic = not parents and not (trusted and main_chain and main_chain[0] == k)
                st.clear()
            ids = {e["id"] for e in st}
            while dv and dv[-1]["id"] not in ids:  # 스택에서 빠진 라벨 = 범위 끝
                dv.pop()
            st.append({"id": nd["id"], "key": k, "lead": nd["lead"], "rank": rk, "label": False, "parent": parent, "anchorRank": None, "band": band,
                       **({"sub": True} if sub else {})})
            g.update(parent=parent, division=div(dv), depth=float(len(st)), heuristic=heuristic)
            graph[nd["id"]] = g
    for g in graph.values():
        if g["parent"] is not None:
            edges.append({"t": "parent", "from": g["parent"], "to": g["id"]})
        if g.get("division"):
            edges.append({"t": "division", "from": g["division"], "to": g["id"]})
    return graph, edges, containers


# ---- 사슬 학습 ↔ 슬롯 배정 -----------------------------------------------------------------------------------

def _eff_parent(g, graph):
    """의미 부모 — 헤딩 아님·안내는 투명(그 자식은 그 위 노드에 붙는다; 그래프 부모는 그대로)."""
    p, seen = g.get("parent"), set()
    while p in graph and graph[p]["role"] in ("not_heading", "note") and p not in seen:
        seen.add(p)
        p = graph[p].get("parent")
    return p


def _kind(tk):
    return "main" if tk == MAIN else "cell" if tk[0] == "cell" else "label" if is_label_key(tk[1]) else "branch"


_KEY_ORDER = ["제N장", "제N절", "R.", "N.", "N-N.", "N.N.", "N.N.N.", "가.", "N)", "가)", "(N)", "(가)", "①", "□", "○", "o", "△", "-", "·", "▫", "*"]


def _key_rank(k):
    """사슬 학습 동률 때의 차례 — 한국어 개요에서 얕은 레터가 먼저, 모르는 레터는 글자 순."""
    return (_KEY_ORDER.index(k) if k in _KEY_ORDER else len(_KEY_ORDER)), k


def anchor_of(tk, chain):
    return f"{tk[0]}:{'›'.join(chain)}"


def assign_templates(nodes, graph, keys, main_chain=None, fixed_main=False):
    """확정 트리 위에서 템플릿 사슬을 배우고 노드마다 (템플릿, 레벨, 인스턴스)를 매긴다(고정점) → {"templates", "instances", "nodes": {id: {template, tplNo, level, instance}},
    "chains", "ties", "conflicts", "unresolved"}. main_chain = A 가 확인한 주 사슬(fixed_main 이면 제약 — 학습은 그 뒤 레벨만 잇고, 다르게 셈한 자리는 conflicts 에 기록).
    노드 규칙: 라벨 → (scope:[basis], 1) · 본문 흐름 뿌리 아래(열린 부모 없음) 주 사슬에 있는 레터 → (main, 주 사슬에서 그 레터의 레벨 — 첫 레터면 1, 「5.」 없이 온 「5-4.」 면 2:
    잇닿은 사슬) · 부모 사슬의 다음 레터 = 내 레터 → (부모 템플릿, L+1) · 부모 사슬의 더 깊은 레벨 레터 = 내 레터 → (부모 템플릿, 그 레벨 — 레벨 건너뜀도 잇닿은 사슬) ·
    그 밖 → (scope:레터, 1).
    B 의 슬롯 예외(graph[id]["slot"] = {template: 앵커, level}) 가 있으면 그대로(앵커를 못 찾으면 기록하고 규칙대로)."""
    by_id = {nd["id"]: nd for nd in nodes}
    order = [nd for nd in nodes if nd["id"] in graph and graph[nd["id"]].get("key") and graph[nd["id"]]["role"] not in ("not_heading", "note", "title")]
    chains = {MAIN: list(main_chain)} if main_chain else {}

    def tk_of_anchor(anchor, chains):
        """B 가 적은 앵커(초안 때의 사슬 글) → 템플릿 키 — 사슬이 그 뒤 더 배워져도 scope 와 뿌리 레터로 찾는다."""
        if ":" not in anchor:
            return None
        sc, chain = anchor.split(":", 1)
        root = chain.split("›", 1)[0]
        if sc == "body" and (chains.get(MAIN) or [None])[0] == root:
            return MAIN
        return (sc, root) if (sc, root) in chains else None

    def one_pass(chains):
        asg, instances, unresolved = {}, [], []
        for nd in order:
            g = graph[nd["id"]]
            k = g["key"]  # 노드의 정규 레터 키(초안이 유형 키를 적고, B 가 역할을 바꾸면 따라 바뀜)
            sc = _scope(nd["flow"])
            p = _eff_parent(g, graph)
            pa = asg.get(p)
            if pa is not None and by_id[p]["kind"] == HB.KIND:
                pa = None  # 띠 표 줄은 템플릿 사슬에 투명하다 — 그 아래 줄의 템플릿·레벨은 문서 맨 위에 매달린 줄처럼 정한다(띠 표 템플릿은 L1 하나뿐 — spec ② §6 「띠 표 줄」)
            ov = g.get("slot")
            tk = lv = None
            if ov:
                otk = tk_of_anchor(ov["template"], chains)
                if otk is not None and 1 <= ov["level"] <= len(chains.get(otk) or []):
                    tk, lv = otk, ov["level"]
                else:
                    unresolved.append({"id": nd["id"], "slot": ov, "why": "앵커·레벨을 못 찾음"})
            if tk is None:
                if g["role"] in ROOTED:
                    tk, lv = (sc, k), 1
                elif pa is None:
                    # 문서 맨 위에 매달린 줄(열린 부모가 없음) — 레터가 주 사슬에 있으면 새 가지가 아니라 **주 사슬의 그 레벨**이다(잇닿은 사슬 — spec ② §6):
                    # 「5.」 를 못 찾은 「5-4.」 = L2, 그 아래 (N)·o·-·· 는 L3… 로 이어지고 사슬보다 더 내려가면 주 사슬이 그만큼 늘어난다. 인스턴스는 윗 레벨이 빠진 편차(missing)
                    # 첫 레터가 아닌 주 사슬 레터는 **본문 흐름**에서만(글상자·머리말·각주 그릇의 맨 위 줄은 전처럼 — 그 그릇의 첫 줄이 주 사슬의 일부라고 볼 근거가 없다)
                    main = (chains.get(MAIN) or []) if sc == "body" else []
                    at = main.index(k) if k in main and (nd["flow"] == "body" or main[0] == k) else None
                    tk, lv = (MAIN, at + 1) if at is not None else ((sc, k), 1)
                else:
                    # 부모 사슬의 다음 레터면 L+1. 다음 레터가 아니어도 **부모 템플릿의 더 깊은 레벨 레터**면 그 레벨이다(잇닿은 사슬 — 레벨을 건너뜀: 「1-1.」 바로 아래 「o」 = 주 사슬 L4,
                    # 2026-11-17 사용자 답 「T1 에 넣기」 — 전에는 가지 템플릿). 부모 사슬에 없거나 더 얕은 레터만 새 가지(L1)
                    ptk, plv, _ = pa
                    ch = chains.get(ptk) or []
                    tk, lv = (ptk, ch.index(k, plv) + 1) if k in ch[plv:] else ((sc, k), 1)
            if lv == 1 or pa is None or pa[0] != tk:
                instances.append({"tk": tk, "root": nd["id"], "parent": p if p in graph else (p or "root")})
                inst = len(instances) - 1
            else:
                inst = pa[2]
            asg[nd["id"]] = (tk, lv, inst)
        return asg, instances, unresolved

    def learn(asg, chains):
        kids, rootkeys, ties, conflicts = defaultdict(Counter), Counter(), [], []
        for nid, (tk, lv, _) in asg.items():
            g = graph[nid]
            if g["role"] in ROOTED:
                continue  # 구분 라벨·괄호 소제목은 부모 사슬을 잇는 후보가 아니다(늘 새 템플릿)
            p = _eff_parent(g, graph)
            if by_id[nid]["kind"] == HB.KIND or (p in asg and by_id[p]["kind"] == HB.KIND):
                continue  # 띠 표 줄과 그 아래 줄 — 주 사슬 첫 레터 셈에도 부모 사슬 잇기에도 넣지 않는다(띠 표 템플릿은 L1 하나뿐)
            if p in asg:
                ptk, plv, _ = asg[p]
                kids[(ptk, plv)][g["key"]] += 1
            elif _scope(by_id[nid]["flow"]) == "body":
                rootkeys[g["key"]] += 1
        new = {}
        if fixed_main and main_chain:
            new[MAIN] = list(main_chain)
        elif rootkeys:
            top = rootkeys.most_common()
            new[MAIN] = [top[0][0]]
            if len(top) > 1 and top[1][1] == top[0][1]:
                ties.append({"template": "main", "level": 1, "letters": [k for k, n in top if n == top[0][1]]})
        for tk in {tk for tk, _, _ in asg.values()} | set(new):
            ch = list(new.get(tk) or [tk[1]])
            start = len(ch) if (tk == MAIN and fixed_main and main_chain) else 1
            if tk == MAIN and fixed_main and main_chain:  # 제약과 다르게 셈한 자리는 기록만
                for L in range(1, len(ch)):
                    c = kids.get((tk, L))
                    if c and c.most_common(1)[0][0] != ch[L]:
                        conflicts.append({"template": "main", "level": L + 1, "fixed": ch[L], "counted": dict(c.most_common(3))})
            L = start
            while kids.get((tk, L)):
                # 동률이면 한국어 개요 차례가 얕은 레터. 바로 위 레벨과 같은 레터는 사슬을 잇지 못한다(같은 레터 = 형제 — 「o」 아래 「o」 는 가지)
                top = sorted(((k, n) for k, n in kids[(tk, L)].items() if k != ch[L - 1]), key=lambda kv: (-kv[1], _key_rank(kv[0])))
                if not top:
                    break
                nxt = top[0][0]
                if len(top) > 1 and top[1][1] == top[0][1]:
                    ties.append({"template": anchor_of(tk, ch[:L]), "level": L + 1, "letters": [k for k, n in top if n == top[0][1]]})
                if len(ch) <= L:
                    ch.append(nxt)
                else:
                    ch[L] = nxt
                L += 1
            new[tk] = ch[:max(L, 1)]
        return new, ties, conflicts

    ties = conflicts = []
    asg, instances, unresolved = one_pass(chains)
    for _ in range(MAX_ROUNDS):
        new, ties, conflicts = learn(asg, chains)
        asg2, instances2, unresolved2 = one_pass(new)
        if new == chains and asg2 == asg:
            break
        chains, asg, instances, unresolved = new, asg2, instances2, unresolved2
    # 템플릿 id — 주 사슬 → 가지(문서 순 첫 등장) → 라벨 → 표 칸
    first_n = {}
    for nid, (tk, _, _) in asg.items():
        first_n[tk] = min(first_n.get(tk, 1 << 30), by_id[nid]["n"])
    used = {tk for tk, _, _ in asg.values()}
    band_tks = {a[0] for nid, a in asg.items() if by_id[nid]["kind"] == HB.KIND}  # 띠 표 템플릿(kind band)

    def kind_of(tk):
        return HB.KIND if tk in band_tks and tk != MAIN else _kind(tk)
    tkeys = sorted(used, key=lambda tk: (KIND_ORDER[kind_of(tk)], first_n.get(tk, 1 << 30), str(tk)))
    tid = {tk: i + 1 for i, tk in enumerate(tkeys)}
    anchors = {tk: anchor_of(tk, chains.get(tk) or [tk[1]]) for tk in tkeys}
    # 인스턴스 — 템플릿 L1 이 나타나는 모든 자리; 멤버 = 직접 소속(안쪽 인스턴스 경계까지)
    for i, ins in enumerate(instances):
        ins.update(i=i, template=tid[ins["tk"]], anchor=anchors[ins["tk"]], members=[], childInstances=[])
    inst_of = {nid: a[2] for nid, a in asg.items()}
    for nd in order:
        a = asg[nd["id"]]
        if instances[a[2]]["root"] != nd["id"]:
            instances[a[2]]["members"].append(nd["id"])
    for ins in instances:
        p = ins["parent"]
        if p in inst_of:
            instances[inst_of[p]]["childInstances"].append(ins["i"])
    per_tpl = Counter()
    for ins in instances:
        per_tpl[ins["template"]] += 1
        ins["no"] = per_tpl[ins["template"]]
        chain = chains.get(ins["tk"]) or [ins["tk"][1]]
        levels = {asg[x][1] for x in [ins["root"]] + ins["members"]}
        ins["missing"] = [L for L in range(1, len(chain) + 1) if L not in levels]
        ins["deviates"] = bool(ins["missing"])
        root = by_id[ins["root"]]
        ins["text"] = root["text"][:50]
        ins["basis"] = root["letter"].strip() if graph[ins["root"]]["role"] == "label" else ""
        path, p, seen = [], ins["parent"], set()
        while p in graph and p not in seen and len(path) < 4:
            seen.add(p)
            if p in by_id:
                path.append(((by_id[p]["letter"] or "").strip() + " " + by_id[p]["text"][:20]).strip())
            p = graph[p].get("parent")
        ins["path"] = " › ".join(reversed(path))
        del ins["tk"]
    node_out = {nid: {"template": anchors[a[0]], "tplNo": tid[a[0]], "level": a[1], "instance": a[2]} for nid, a in asg.items()}
    templates = []
    for tk in tkeys:
        chain = chains.get(tk) or [tk[1]]
        templates.append({"id": tid[tk], "no": tid[tk], "anchor": anchors[tk], "name": anchors[tk], "key": anchors[tk], "kind": kind_of(tk), "scope": tk[0],
                          "rootRole": "label" if is_label_key(tk[1]) else "subtitle" if tk[1] == SUB_KEY else "heading", "root": tk[1], "chain": chain,
                          "displayName": "",
                          "instances": per_tpl[tid[tk]], "where": [], "slots": [], "note": ""})
    where = defaultdict(Counter)
    for ins in instances:
        p = ins["parent"]
        where[ins["template"]][graph[p]["key"] if p in graph and graph[p].get("key") else ("root" if p == "root" or p is None else "칸")] += 1
    for t in templates:
        t["where"] = [{"parent": k, "count": n} for k, n in where[t["id"]].most_common(6)]
    return {"templates": templates, "instances": instances, "nodes": node_out, "chains": {anchors[tk]: ch for tk, ch in chains.items() if tk in anchors},
            "ties": ties, "conflicts": conflicts, "unresolved": unresolved}


def propose_main(nodes, roles, keys, stage1):
    """A 호출 앞 — 지식 없는 어림 초안에서 셈한 본문 주 사슬 제안(A 가 확인·수정)."""
    graph, _, _ = draft_parents(nodes, roles, keys, None, stage1)
    asg = assign_templates(nodes, graph, keys)
    main = next((t for t in asg["templates"] if t["kind"] == "main"), None)
    return main["chain"] if main else []


# ---- B 호출(본문 구간) ---------------------------------------------------------------------------------

def sections(nodes, graph, tmap=None):
    """본문 흐름 노드를 구간으로 — 깊이 1(최상위) 노드에서 끊고, 작은 최상위 구간은 이어서 SECTION_MAX 안에서 합치며(호출 수),
    SECTION_MAX 넘는 최상위 구간은 깊이 2 에서 더 끊는다. → [[노드 id…]…]."""
    body = [nd for nd in nodes if nd["flow"] == "body" and graph.get(nd["id"], {}).get("role") != "not_heading"]
    cuts, cur = [], []
    for nd in body:
        g = graph[nd["id"]]
        if cur and g.get("depth") == 1.0:
            cuts.append(cur)
            cur = []
        cur.append(nd["id"])
    if cur:
        cuts.append(cur)
    out, part = [], []
    for sec in cuts:
        if len(sec) <= SECTION_MAX:  # 작은 최상위 구간은 이어서 합친다
            if part and len(part) + len(sec) > SECTION_MAX:
                out.append(part)
                part = []
            part += sec
            continue
        if part:
            out.append(part)
            part = []
        # 깊이 2 경계에서 조각으로 나눈 뒤, 이어진 조각을 SECTION_MAX 안에서 합친다. 한 조각이 SECTION_MAX 를 넘으면 그 조각은 SECTION_MAX 씩 그냥 자른다.
        chunks, cur2 = [], []
        for nid in sec:
            if cur2 and graph[nid].get("depth") == 2.0:
                chunks.append(cur2)
                cur2 = []
            cur2.append(nid)
        if cur2:
            chunks.append(cur2)
        p2 = []
        for ch in chunks:
            if p2 and len(p2) + len(ch) > SECTION_MAX:
                out.append(p2)
                p2 = []
            if len(ch) > SECTION_MAX:
                out += [ch[i:i + SECTION_MAX] for i in range(0, len(ch), SECTION_MAX)]
                continue
            p2 += ch
        if p2:
            out.append(p2)
    if part:
        out.append(part)
    return out


def _ancestors(nid, graph, stop):
    out, seen = [], set()
    p = graph[nid]["parent"]
    while p and p in graph and p not in seen and p not in stop:
        seen.add(p)
        out.append(p)
        p = graph[p]["parent"]
    return out[::-1]


def b_jobs(secs, nodes, graph, prov, types, roles, keys, pinned=None, bases=BASES):
    """구간마다 B 호출 — 행 = [id, 유형, 글, 초안 부모, 초안 템플릿(앵커), 초안 레벨, 초안 구분 라벨]. prov = 초안 위 임시 배정(assign_templates 결과)."""
    by_id = {nd["id"]: nd for nd in nodes}
    brief = {t: {"role": v["role"], "key": keys.get(t) or "", "basis": v.get("basis", ""), "parents": v.get("parents", []), "shape": types[t]["shape"]}
             for t, v in roles.items() if t in types}
    tpls = [{"anchor": t["anchor"], "kind": t["kind"], "chain": t["chain"]} for t in prov["templates"]]
    jobs, used = [], {}
    for i, sec in enumerate(secs):
        inside = set(sec)
        anc = _ancestors(sec[0], graph, inside)
        rows = [[nid, graph[nid]["type"], ((by_id[nid]["letter"] or "") + " " + by_id[nid]["text"]).strip()[:60], graph[nid]["parent"] or "",
                 prov["nodes"].get(nid, {}).get("template", ""), prov["nodes"].get(nid, {}).get("level", 0), graph[nid].get("division") or ""] for nid in sec]
        nxt = secs[i + 1][:5] if i + 1 < len(secs) else []
        data = {"bases": list(bases), "types": brief, "templates": tpls, "ancestors": [[a, graph[a]["type"], by_id[a]["text"][:40] if a in by_id else ""] for a in anc],
                "nodes": rows, "preview": [[n, graph[n]["type"], by_id[n]["text"][:40]] for n in nxt]}
        content, u = HL.prompt(HL.SECTION_CONTRACT, ["graph", "templates"], data, pinned)
        used.update(u)
        jobs.append({"schema": HL.SECTION_SCHEMA, "content": content, "what": f"heading_section#{i + 1}", "timeout": 600.0, "effort": "medium",
                     "_section": sec, "_ancestors": anc})
    return jobs, used


def _b_role(g, nd, want, basis="", hints=None):
    """B 가 노드 역할을 want(+ basis)로 바꾸려 할 때의 (역할, 정규 키) — A·사용자 지정과 같은 판정 규칙을 거친다. 괄호 줄(kind label)은 bracket_role 이 정한다
    (B 가 적은 basis, 없으면 지금 키의 구분 기준을 LLM 이 본 것으로). 그 밖의 줄이 구분 라벨이 되려면 B 가 적은 basis 가 구분 기준 목록에 있어야 하고(없으면 그대로),
    괄호 소제목은 될 수 없다. 나머지는 역할을 따라 키가 바뀐다(헤딩 아님·안내·제목 = 없음, 제목 → 헤딩 = 「제목」)."""
    divt = (hints or {}).get("_divTypes")
    if nd.get("kind") == "label":
        role, b, _ = bracket_role(nd.get("letter"), hints, want, basis or ((g.get("key") or "")[1:-1] if is_label_key(g.get("key")) else ""),
                                  div=_div_basis(divt, nd.get("type"), bases_of(hints)))
        return role, _bracket_key(role, b)
    if want in ROOTED:
        b = norm_basis(basis, bases_of(hints)) if want == "label" else ""
        if b and divt is not None and _div_basis(divt, nd.get("type"), bases_of(hints)) != b:
            return g["role"], g.get("key")   # 판독이 이 유형의 줄 모두를 그 구분 기준으로 확인하지 않음 — 괄호 줄이 아닌 줄을 구분 라벨로 바꾸지 않는다(settle_roles 와 같은 까닭)
        return ("label", "[" + b + "]") if b else (g["role"], g.get("key"))
    return want, (None if want in ("not_heading", "note", "title") else (g.get("key") or "제목"))


def apply_changes(changes, sec, anc, graph, anchors, by_id=None, hints=None):
    """B 응답 변경을 검증해 적용 → (적용 [{id, before, after, reason}], 버림 [{id, why}]). 부모·역할은 바로 적용, template·level 은 슬롯 예외(둘 다 있을 때만 —
    앵커는 초안 템플릿 목록(anchors)에 있어야 함). 라벨 부모는 그대로 부모(라벨은 제 템플릿의 뿌리), 헤딩 아님·안내 부모·순환·문서 순 뒤 부모는 버림.
    by_id = 후보 노드(역할이 바뀐 노드의 키를 정할 때 글·종류를 봄 — _b_role), hints = 사용자 라벨 지정."""
    inside, allowed = set(sec), set(sec) | set(anc) | {"root"}
    order = {nid: i for i, nid in enumerate(sec)}
    applied, rejected = [], []
    for ch in changes or []:
        nid = ch.get("id")
        if nid not in inside:
            rejected.append({"id": nid, "why": "구간 밖 id"})
            continue
        g = graph[nid]
        nd = (by_id or {}).get(nid) or {}
        if nd.get("kind") == HB.KIND:  # 띠 표 줄의 역할·부모·템플릿은 스크립트가 정한다(늘 헤딩 · 문서 맨 위 · 제 템플릿 L1 — spec ② §6 「띠 표 줄」)
            rejected.append({"id": nid, "why": "별첨·부록 표 제목 줄 — 스크립트가 정한다"})
            continue
        role, key = g["role"], g.get("key")
        if ch.get("role") in ROLES and ch["role"] != g["role"]:
            role, key = _b_role(g, nd, ch["role"], str(ch.get("basis") or "")[:20], hints)
        parent = ch.get("parent") or g["parent"]
        if nd.get("inline") and g["parent"] == nd.get("para") and parent != g["parent"]:  # 줄 안 레터의 부모는 그 줄(spec ② §2 — draft_parents)
            rejected.append({"id": nid, "why": "줄 안 레터 — 부모는 그 줄의 첫 레터(스크립트가 정한다)"})
            continue
        if parent not in allowed:
            rejected.append({"id": nid, "why": f"부모 {parent} 가 구간·조상 밖"})
            continue
        if parent in order and order[parent] >= order[nid]:
            rejected.append({"id": nid, "why": "부모가 문서 순으로 뒤"})
            continue
        if parent in graph and graph[parent]["role"] in ("not_heading", "note"):
            rejected.append({"id": nid, "why": f"부모 {parent} 가 헤딩 아님·안내"})
            continue
        p, seen = parent, {nid}
        while p in graph and p not in seen:  # 순환 검사
            seen.add(p)
            p = graph[p]["parent"]
        if p == nid:
            rejected.append({"id": nid, "why": "순환"})
            continue
        tpl = str(ch.get("template") or "")
        lv = ch.get("level")
        lvl = lv if isinstance(lv, int) and not isinstance(lv, bool) else 0
        slot = None
        if role in ("heading", "title") and (tpl or lvl):
            if not tpl or tpl not in anchors:
                rejected.append({"id": nid, "why": f"모르는 템플릿 {tpl or '(없음)'}"})
                continue
            if lvl < 1:
                rejected.append({"id": nid, "why": f"레벨 {lvl} 이 범위 밖"})
                continue
            slot = {"template": tpl, "level": lvl}
        before = {"parent": g["parent"], "role": g["role"], "slot": g.get("slot")}
        # 역할이 바뀌면 정규 레터 키도 따라간다(_b_role). B 가 적은 줄의 부모는 어림이 아니다(스크립트가 어림으로 붙인 줄을 B 가 보고 정한 것)
        g.update(parent=parent, role=role, key=key, changed=True, heuristic=False, reason=str(ch.get("reason") or "")[:200])
        if slot or role not in ("heading", "title"):
            g["slot"] = slot
        # asked = B 가 적은 그대로(역할·basis·슬롯 예외) — 다시 셈(replay)의 입력: 사용자 지정을 지우면 여기로 돌아가고, 슬롯 예외를 안 적은 변경도 그대로 되풀이된다
        applied.append({"id": nid, "before": before, "after": {"parent": g["parent"], "role": g["role"], "slot": g.get("slot")}, "reason": g["reason"],
                        "asked": {"role": ch.get("role") if ch.get("role") in ROLES else "", "basis": str(ch.get("basis") or "")[:20], "template": tpl, "level": lvl}})
    return applied, rejected


def _division_of(nid, graph):
    """구분 소속 = 가장 가까운 라벨 조상(라벨 자신은 그 위 라벨)."""
    p, seen = graph[nid].get("parent"), set()
    while p in graph and p not in seen:
        seen.add(p)
        if graph[p]["role"] == "label":
            return p
        p = graph[p].get("parent")
    return None


# ---- C 호출(슬롯 서식 쌍 — 조정 판단) --------------------------------------------------------------------

PAIR_BATCH = 60


def _slot_rep(ids, by_id, graph):
    """슬롯 서식 수(모든 노드) + 대표 서식 — 미판정(B 실패 구간) 노드는 대표의 근거로 안 씀(spec ② §6)."""
    fm = Counter(by_id[i]["fmt"] for i in ids if i in by_id)
    basis = Counter(by_id[i]["fmt"] for i in ids if i in by_id and not graph.get(i, {}).get("undecided"))
    return fm, (basis.most_common(1)[0][0] if basis else None)


def _slots(graph, asg_nodes, by_id):
    slots = defaultdict(list)
    for nid, a in asg_nodes.items():
        if nid in by_id and graph[nid]["role"] in ("heading", "title") + ROOTED:
            slots[(a["template"], a["level"])].append(nid)
    return slots


def slot_pairs(nodes, graph, asg_nodes, labels, decided):
    """슬롯(템플릿 앵커, 레벨)마다 대표 서식 a 와 다른 서식 b 쌍 — 이미 그 슬롯에서 판정한 쌍(decided)은 뺌
    → [{slot, template, tplNo, level, a, aName, aCount, b, bName, bCount, examples}]."""
    by_id = {nd["id"]: nd for nd in nodes}
    out = []
    for (tn, level), ids in _slots(graph, asg_nodes, by_id).items():
        fm, a = _slot_rep(ids, by_id, graph)
        if len(fm) < 2 or a is None:
            continue
        slot = f"{tn}|L{level}"
        for b, bn in fm.most_common():
            if b == a or (slot, a, b) in decided or (slot, b, a) in decided:
                continue
            ex = [((by_id[i]["letter"] or "") + " " + by_id[i]["text"]).strip()[:50] for i in ids if by_id[i]["fmt"] == b][:3]
            out.append({"slot": slot, "template": tn, "tplNo": asg_nodes[ids[0]]["tplNo"], "level": level, "a": a, "aName": labels.get(a, {}).get("name", "")[:100],
                        "aCount": fm[a], "b": b, "bName": labels.get(b, {}).get("name", "")[:100], "bCount": bn, "examples": ex})
    return out


def c_jobs(pairs, pinned=None):
    jobs, used = [], {}
    for i in range(0, len(pairs), PAIR_BATCH):
        content, u = HL.prompt(HL.FORMAT_CONTRACT, ["templates", "tolerance"], {"pairs": pairs[i:i + PAIR_BATCH]}, pinned)
        used.update(u)
        jobs.append({"schema": HL.FORMAT_SCHEMA, "content": content, "what": f"heading_formats#{i // PAIR_BATCH + 1}", "timeout": 600.0, "effort": "low"})
    return jobs, used


# ---- D 호출(재검토 — 1차 조정 판정을 새 호출이 반박 검증) --------------------------------------------------

def _same_of(same, slot, a, b):
    """쌍의 같음 판정 — 그 슬롯의 답만(어느 순서로 적혔든). 다른 슬롯·전역 쌍 답은 재사용하지 않는다(astra 2026-11-09)."""
    return same.get((slot, a, b)) or same.get((slot, b, a))


def review_pairs(nodes, graph, asg_nodes, labels, same):
    """재검토 대상 — 모든 슬롯 서식 쌍에 1차 판정(C 의 same)을 붙인 것. 1차 판정이 없는 쌍(C 실패 — 어차피 미판정)은 뺀다."""
    out = []
    for p in slot_pairs(nodes, graph, asg_nodes, labels, set()):
        d = _same_of(same, p["slot"], p["a"], p["b"])
        if d:
            out.append({**p, "first": {"same": bool(d["same"]), "reason": d.get("reason", "")}})
    return out


def d_jobs(pairs, pinned=None):
    """재검토 호출 — 쌍 PAIR_BATCH 개씩, 1차(C: effort low)보다 깊게(effort medium). 호출마다 새 에이전트(세션 없음)라 1차 판정의 맥락을 모른다."""
    jobs, used = [], {}
    for i in range(0, len(pairs), PAIR_BATCH):
        batch = pairs[i:i + PAIR_BATCH]
        content, u = HL.prompt(HL.REVIEW_CONTRACT, ["templates", "tolerance"], {"pairs": batch}, pinned)
        used.update(u)
        jobs.append({"schema": HL.REVIEW_SCHEMA, "content": content, "what": f"heading_review#{i // PAIR_BATCH + 1}", "timeout": 600.0, "effort": "medium",
                     "_pairs": batch})
    return jobs, used


def apply_review(pairs, res):
    """D 응답 → {(slot, a, b): {verdict: agree|disagree|failed, same, reason}}. verdict 는 재검토의 same 과 1차 same 을 견줘 스크립트가 정한다
    (응답의 verdict 칸은 모델이 스스로 견주게 하는 장치 — 어긋나면 same 을 믿음). 답이 없는 쌍·호출 실패는 failed(1차 판정 유지). 답은 그 슬롯의 것만 쓴다."""
    got = {}
    for it in (res.get("data") or {}).get("pairs") or []:
        if it.get("a") and it.get("b"):
            got[(str(it.get("slot") or ""), it["a"], it["b"])] = it
    out = {}
    for p in pairs:
        key = (p["slot"], p["a"], p["b"])
        it = got.get(key)
        if it is None:
            out[key] = {"verdict": "failed", "same": None, "reason": str(res.get("error") or "재검토 답 없음")[:200]}
            continue
        s = bool(it.get("same"))
        out[key] = {"verdict": "agree" if s == bool(p["first"]["same"]) else "disagree", "same": s, "reason": str(it.get("reason") or "")[:200]}
    return out


# ---- 템플릿 슬롯 · 되풀이 · 이종 형제 · 조정 -------------------------------------------------------------------

def finish(nodes, graph, asg, types, labels, same, review=None):
    """배정 결과(asg = assign_templates) 에 슬롯 요약(대표 서식·유형)·되풀이·이종 형제·조정을 붙인다.
    review = D 호출의 재검토 {(slot, a, b): {verdict, same, reason}} — disagree 인 쌍의 조정은 미판정(undecided)으로 두고 1차 판정(first)·재검토를 함께 남긴다."""
    by_id = {nd["id"]: nd for nd in nodes}
    an = asg["nodes"]
    children = defaultdict(list)
    for g in graph.values():
        if g["role"] in ("not_heading", "note"):
            continue
        p = _eff_parent(g, graph)
        if p:
            children[p].append(g["id"])
    # 이종 형제 = 같은 의미 부모 아래 레터 키가 다른 헤딩·라벨 — 가지 템플릿이 뿌리를 내리는 자리
    hetero = []
    for p, kids in children.items():
        ks = {}
        for k in kids:
            if graph[k]["role"] in ("heading", "title") + ROOTED and graph[k].get("key"):
                ks.setdefault(graph[k]["key"], []).append(k)
        if len(ks) > 1:
            hetero.append({"parent": p, "letters": [{"key": key, "type": graph[ids[0]]["type"], "shape": types.get(graph[ids[0]]["type"], {}).get("shape", key),
                                                     "count": len(ids)} for key, ids in ks.items()]})
    # 슬롯 요약
    slots = _slots(graph, an, by_id)
    templates = asg["templates"]
    by_anchor = {t["anchor"]: t for t in templates}
    by_tid = {t["id"]: t for t in templates}
    for (tn, level), ids in sorted(slots.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        t = by_anchor.get(tn)
        if t is None:
            continue
        fm, rep = _slot_rep(ids, by_id, graph)
        ty = Counter(graph[i]["type"] for i in ids)
        rep_id = next((i for i in ids if by_id[i]["fmt"] == rep), ids[0])
        t["slots"].append({"level": level, "letter": t["chain"][level - 1] if level - 1 < len(t["chain"]) else graph[ids[0]].get("key"), "count": len(ids),
                           "types": [{"type": k, "shape": types.get(k, {}).get("shape", ""), "count": n} for k, n in ty.most_common()],
                           "format": rep, "formats": dict(fm.most_common(5)), "rep": by_id[rep_id]["para"]})
    # 되풀이 = 같은 부모 아래 같은 템플릿 인스턴스 2개 이상
    groups = defaultdict(list)
    for ins in asg["instances"]:
        groups[(ins["parent"], ins["template"])].append(ins["root"])
    repeats = [{"parent": p, "template": t, "roots": roots, "signature": by_tid[t]["chain"], "count": len(roots)}
               for (p, t), roots in groups.items() if len(roots) >= 2 and t in by_tid]
    # 조정: 슬롯 대표 서식과 다른 서식 라벨 — C 의 슬롯별 판정만. D 재검토가 다르게 봤으면(disagree) 미판정으로 — 1차·재검토를 함께 남김
    adjustments = []
    review = review or {}
    for (tn, level), ids in slots.items():
        fm, rep = _slot_rep(ids, by_id, graph)
        if len(fm) < 2 or rep is None:
            continue
        slot = f"{tn}|L{level}"
        for i in ids:
            f = by_id[i]["fmt"] if i in by_id else None
            if not f or f == rep:
                continue
            d = _same_of(same, slot, rep, f)
            dec = "adjust" if d and d["same"] else "keep" if d else "undecided"
            adj = {"id": i, "para": graph[i]["para"], "template": tn, "tplNo": an[i]["tplNo"], "level": level, "from": f, "to": rep,
                   "decision": dec, "reason": (d or {}).get("reason", ""),
                   "fromName": labels.get(f, {}).get("name", ""), "toName": labels.get(rep, {}).get("name", "")}
            r = review.get((slot, rep, f)) or review.get((slot, f, rep))
            if r:
                adj["review"] = r
                if r["verdict"] == "disagree":
                    adj["first"] = dec
                    adj["decision"] = "undecided"
            adjustments.append(adj)
    return {"templates": templates, "instances": asg["instances"], "repeats": repeats[:200], "heterogeneous": hetero, "adjustments": adjustments}


# ---- 2단계 실행 ------------------------------------------------------------------------------------------

def build(stage1, *, use_llm=True, ask=None, doc_name="", pinned=None, hints=None, replay=None, temp=None, pairs=True):
    """2단계 — 1단계 결과 → graph dict(spec ② §6). ask = llm.ask_all 대신(시험). use_llm False 면 스크립트 어림만.
    temp = TEMP 라벨(heading_temp.label 결과 — §15): 그 문단들은 헤딩 후보에서 빠진다(결과 `temp` 에 쓴 요약을 남김).
    pinned = 실행 시작 때 고정한 지침(heading_guides.snapshot() 꼴 {이름: {text, sha1, …}}) — 주면 A·B·C·D 프롬프트가 그 글을 쓴다(§7).
    hints = 사용자 라벨 지정 {"bases": [더한 구분 기준], "labels": {괄호 글 꼴: {role: label|subtitle, basis}}}(§13) — LLM 답과 달라도 지정이 이긴다.
      + "division" = 실행 시작 때 고정한 **구분 기준 판독**(division_scan.pin 꼴 — 연구개발과제 문서만, §13 「구분 기준 판독」): 유형의 줄 모두가 같은 구분 기준으로 확인되면 그 유형은 구분 라벨(글 꼴 다음 차례).
    replay = replay_of(같은 1단계에서 만든 앞 결과) — LLM 을 다시 부르지 않고 앞 실행의 A 답·B 변경·C/D 판정을 되풀이해 **새 추출과 같은 길**로 다시 셈한다
    (라벨 지정을 곧바로 반영 — 부모 초안부터 다시이므로 새로 추출한 것과 같은 트리가 된다, astra 2026-11-10)."""
    t0 = time.monotonic()
    ask = ask or llm.ask_all
    use_llm = bool(use_llm or replay)
    nodes = candidates(stage1, frozenset((temp or {}).get("paras") or ()))
    types = type_table(nodes)
    labels = stage1.get("labels") or {}
    pin = (hints or {}).get("division")
    if pin:   # 구분 기준 판독(2026-11-18) — 유형마다 확인한 줄 수(유형 전체로는 줄 모두가 같은 구분일 때만 — astra · Fable 협의)
        from app import division_scan as DS
        hints = {**hints, "_divTypes": DS.type_bases(nodes, pin)}
    bases = bases_of(hints)
    calls, guides, info = [], {}, {"requested": bool(use_llm), "fallback": False, "error": None, "summary": "", "sections": 0, "applied": 0, "rejected": 0,
                                    "failedSections": 0}
    roles = fallback_roles(types, hints)
    keys = type_keys(types, roles)
    proposal = propose_main(nodes, roles, keys, stage1) if nodes else []
    main_chain, fixed = proposal, False
    a_data = None
    if replay and nodes:
        a_data = {**replay["a"], "types": _remap_types(replay["a"]["types"], types)}
        info["replay"] = {k: replay.get(k) for k in ("from", "calls", "costUsd")}
    elif use_llm and nodes:
        job, used, _ = a_job(types, nodes, keys, proposal, doc_name, pinned, bases, (hints or {}).get("_divTypes"))
        guides.update(used)
        res = ask([job])[0]
        calls.append(HL._call_record(job, res))
        a_data = res.get("data")
        if not a_data:
            info["error"] = res.get("error") or "A 호출 실패"
            info["fallback"] = True
    elif not use_llm:
        info["fallback"] = True
    if a_data:
        got, main = apply_types(a_data, types)
        for tid in types:  # A 가 빠뜨린 유형은 어림 역할
            roles[tid] = got.get(tid) or {**roles[tid], "reason": "A 판정 없음 — 스크립트 대체"}
        settle_roles(types, roles, hints)  # 괄호 줄 = 구분 라벨·괄호 소제목 규칙(§13), 그 밖의 라벨은 basis 가 구분 기준일 때만
        keys = type_keys(types, roles)
        known = set(k for k in keys.values() if k)
        bandkeys = {keys[tid] for tid, t in types.items() if t["kind"] == HB.KIND}
        if main and all(k in known for k in main) and not bandkeys & set(main):  # 띠 표 줄의 레터는 주 사슬에 들지 않는다
            main_chain, fixed = main, True
        elif main:
            info["mainChainRejected"] = main  # 모르는 레터가 든 주 사슬 — 제안으로 대신
        info["summary"] = str(a_data.get("summary") or "")[:600]
    info["mainChain"], info["mainChainProposal"], info["mainChainFixed"] = list(main_chain or []), list(proposal or []), fixed
    graph, edges, containers = draft_parents(nodes, roles, keys, main_chain, stage1, trusted=fixed)
    by_id = {nd["id"]: nd for nd in nodes}
    changes, rejected = [], []
    if replay and not info["fallback"]:  # 앞 실행에서 B 가 적은 변경을 그대로 — 구간 경계는 초안에 따라 달라지므로 본문 전체를 한 구간으로 검증
        prov = assign_templates(nodes, graph, keys, main_chain, fixed)
        body = [nd["id"] for nd in nodes if nd["flow"] == "body" and nd["id"] in graph]
        changes, rejected = apply_changes(_refold(replay["changes"], prov["templates"]), body, [], graph, {t["anchor"] for t in prov["templates"]}, by_id, hints)
        for nid in replay.get("undecided") or []:
            if nid in graph:
                graph[nid]["undecided"] = True
        info.update(sections=replay.get("sections") or 0, applied=len(changes), rejected=len(rejected))
    elif use_llm and not info["fallback"]:
        prov = assign_templates(nodes, graph, keys, main_chain, fixed)  # B 에 보일 초안 배정(앵커·레벨)
        anchors = {t["anchor"] for t in prov["templates"]}
        secs = sections(nodes, graph)
        info["sections"] = len(secs)
        jobs, used = b_jobs(secs, nodes, graph, prov, types, roles, keys, pinned, bases)
        guides.update(used)
        results = ask([{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs]) if jobs else []
        retry, batch = [], []
        for job, res in zip(jobs, results):
            calls.append(HL._call_record(job, res))
            if not res.get("data"):
                info["failedSections"] += 1
                for nid in job["_section"]:
                    graph[nid]["undecided"] = True
                continue
            ch = res["data"].get("changes") or []
            if len(ch) > CHANGE_RATE_RETRY * len(job["_section"]) and len(job["_section"]) >= 10:
                retry.append((job, ch))
                continue
            batch.append((job, ch))
        if retry:  # 변경률이 높은 구간은 한 번 더 묻고 둘째 답을 쓴다
            again = ask([{k: v for k, v in j.items() if not k.startswith("_")} for j, _ in retry])
            for (job, first), res in zip(retry, again):
                calls.append(HL._call_record(job, res))
                ch = (res.get("data") or {}).get("changes")
                batch.append((job, ch if ch is not None else first))
        for job, ch in batch:  # 모든 구간의 답을 같은 초안에 대해 모아 적용(부모 변경 보존)
            a, r = apply_changes(ch, job["_section"], job["_ancestors"], graph, anchors, by_id, hints)
            changes += a
            rejected += r
        info["applied"], info["rejected"] = len(changes), len(rejected)
    for g in graph.values():
        g["division"] = _division_of(g["id"], graph)
    edges = [e for e in edges if e["t"] not in ("parent", "division") or e["to"] not in graph] + \
        [{"t": "parent", "from": g["parent"], "to": g["id"]} for g in graph.values() if g.get("parent")] + \
        [{"t": "division", "from": g["division"], "to": g["id"]} for g in graph.values() if g.get("division")]
    edges = _dedupe(edges)
    asg = assign_templates(nodes, graph, keys, main_chain, fixed)  # 확정 트리 → 사슬·슬롯·인스턴스 → id 동결
    info["ties"], info["mainChainConflicts"], info["slotUnresolved"] = asg["ties"][:50], asg["conflicts"][:50], asg["unresolved"][:50]
    same, review = {}, {}
    if replay and not info["fallback"]:  # 앞 실행의 조정 판정(C·D) — 슬롯 멤버가 그대로인 슬롯만 이어받는다(바뀐 슬롯은 미판정)
        same, review = _carry(replay, _slots(graph, asg["nodes"], by_id), by_id, graph)
        info["carried"] = len(same)
    # pairs = 서식 쌍 판정(C)과 재검토(D)를 하나 — 기본 실행(heading_runs.run_stage2)은 하지 않는다(2026-11-16: 그 판정은 문서도 서식 정리 계획도 바꾸지 않는데 2단계 비용의 절반이었다 — spec ② §6 「서식 쌍 판정은 기본 실행에서 뺀다」).
    # 안 하면 조정 목록은 스크립트가 낸 그대로(미판정)이고 llm.pairs = False 로 적는다(화면이 「하지 않음」 으로 보인다). 앞 실행의 판정을 이어 쓰는 다시 셈(replay)은 그대로.
    asked = bool(replay.get("pairs", True)) if replay else bool(pairs)  # 다시 셈(replay)은 앞 실행이 판정을 했는지를 그대로 잇는다(안 한 실행을 다시 세어 「함」 이 되지 않게 — astra)
    if use_llm and not info["fallback"]:
        info["pairs"] = asked
    if pairs and use_llm and not info["fallback"] and not replay:  # C: 슬롯 서식 쌍 — 조정 판단(슬롯마다)
        found = slot_pairs(nodes, graph, asg["nodes"], labels, set())
        info["formatPairs"] = len(found)
        if found:
            jobs, used = c_jobs(found, pinned)
            guides.update(used)
            for job, res in zip(jobs, ask(jobs)):
                calls.append(HL._call_record(job, res))
                for it in (res.get("data") or {}).get("pairs") or []:
                    if it.get("a") and it.get("b") and it.get("slot"):
                        same[(str(it["slot"]), it["a"], it["b"])] = {"same": bool(it.get("same")), "reason": str(it.get("reason") or "")[:200]}
    if use_llm and not info["fallback"] and asked:  # D: 재검토 — 1차 조정 판정(C)을 새 호출(1차 맥락이 없는 다른 에이전트)이 반박 검증(2026-11-09 사용자)
        todo = [] if replay else review_pairs(nodes, graph, asg["nodes"], labels, same)
        info["reviewPairs"] = len(review) if replay else len(todo)
        if todo:
            jobs, used = d_jobs(todo, pinned)
            guides.update(used)
            for job, res in zip(jobs, ask([{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs])):
                calls.append(HL._call_record(job, res))
                review.update(apply_review(job["_pairs"], res))
        info["reviewFailed"] = sum(1 for r in review.values() if r["verdict"] == "failed")
        info["reviewDisagree"] = sum(1 for r in review.values() if r["verdict"] == "disagree")
    fin = finish(nodes, graph, asg, types, labels, same, review)
    out_nodes = []
    for nd in nodes:
        g = graph.get(nd["id"]) or {}
        a = asg["nodes"].get(nd["id"]) or {}
        out_nodes.append({"id": nd["id"], "para": nd["para"], "span": nd["span"], "n": nd["n"], "area": nd["area"], "flow": nd["flow"], "type": nd["type"],
                          "kind": nd["kind"], "letter": nd["letter"], "shape": nd["shape"], "key": g.get("key"), "text": nd["text"], "blank": nd["blank"],
                          "lead": nd["lead"], "fmt": nd["fmt"], "role": g.get("role"), "template": a.get("template"), "tplNo": a.get("tplNo"),
                          "level": a.get("level"), "instance": a.get("instance"), "parent": g.get("parent"), "division": g.get("division"),
                          "sourceOutlineLevel": nd.get("outline"), "changed": g.get("changed", False), "undecided": g.get("undecided", False),
                          "heuristic": g.get("heuristic", False), "reason": g.get("reason", ""),
                          **({"basis": g["key"][1:-1]} if g.get("role") == "label" and is_label_key(g.get("key")) else {}),  # 구분 라벨의 구분 기준 이름(3단계 표 소속이 그대로 씀)
                          **({"band": nd["band"]} if nd.get("band") else {}),  # 띠 표 줄 — {table, title(제목 문단), host}(오버레이가 표 줄로 둔다)
                          **({"inline": True} if nd.get("inline") else {})})  # 줄 안 레터(spec ② §2) — 오버레이는 줄로 두지 않고 그 문단 줄에 잇는다
    edges += [{"t": "instance", "from": ins["root"], "to": f"tpl:{ins['template']}"} for ins in fin["instances"]]
    cost = sum((c.get("costUsd") or 0) for c in calls)
    return {"version": 2, "nodes": out_nodes, "containers": list(containers.values()), "edges": edges,
            "types": [{**t, **(roles.get(tid) or {}), "key": keys.get(tid)} for tid, t in types.items()],
            **fin, "changes": changes, "rejected": rejected, "bases": bases, "bracketRule": BRACKET_RULE,
            "hints": {"bases": list((hints or {}).get("bases") or []), "labels": {k: {"role": v.get("role"), "basis": v.get("basis") or ""}
                                                                               for k, v in ((hints or {}).get("labels") or {}).items()}},
            "division": _division_brief(pin, (hints or {}).get("_divTypes"), types, roles),   # 이 결과가 쓴 구분 기준 판독(고정본 — 라벨 지정 반영이 그대로 되풀이) | None(판독 없음)
            "counts": _counts(out_nodes, len(types), fin, len(changes)),
            "llm": {**info, "calls": len(calls), "failed": sum(1 for c in calls if c["response"] is None), "costUsd": round(cost, 4),
                    "seconds": round(time.monotonic() - t0, 2)},
            "temp": _temp_brief(temp),  # 이 결과가 뺀 TEMP(§15) — None = TEMP 없이 만든 결과
            "guides": guides, "_calls": calls}


def _division_brief(pin, divt, types, roles):
    """결과에 남기는 구분 기준 판독 — {pin(고정본 그대로 — relabel 이 되풀이), types{유형 id: {basis, confirmed, total, conflict}}(근거가 있는 유형만), decided[판독이 구분 라벨로 정한 유형 id]} | None."""
    if not pin:
        return None
    tb = {tid: d for tid, d in (divt or {}).items() if d.get("confirmed") or d.get("conflict") or d.get("names")}
    return {"pin": pin, "types": tb, "decided": [tid for tid in types if (roles.get(tid) or {}).get("reason") == BY_SCAN]}


def _temp_brief(temp):
    """결과에 남기는 TEMP 요약(heading_temp.brief 와 같은 꼴 — 항목 본문은 빼고 수와 id)."""
    if temp is None:
        return None
    return {"version": temp.get("version"), "hintsVersion": temp.get("hintsVersion"), "counts": temp.get("counts") or {},
            "items": [it["id"] for it in temp.get("items") or ()], "off": list(temp.get("off") or ())}


def _counts(out_nodes, ntypes, fin, nchanges):
    return {"nodes": len(out_nodes), "body": sum(1 for n in out_nodes if n["flow"] == "body"), "cell": sum(1 for n in out_nodes if n["flow"].startswith("cell:")),  # 칸 안 상자 포함
            "types": ntypes, "templates": len(fin["templates"]), "branches": sum(1 for t in fin["templates"] if t["kind"] == "branch"),
            "labelTemplates": sum(1 for t in fin["templates"] if t["kind"] == "label"), "instances": len(fin["instances"]), "repeats": len(fin["repeats"]),
            "labels": sum(1 for n in out_nodes if n["role"] == "label"), "subtitles": sum(1 for n in out_nodes if n["role"] == "subtitle"),
            "heterogeneous": len(fin["heterogeneous"]), "adjust": sum(1 for a in fin["adjustments"] if a["decision"] == "adjust"),
            "reviewed": sum(1 for a in fin["adjustments"] if (a.get("review") or {}).get("verdict") in ("agree", "disagree")),
            "disagreed": sum(1 for a in fin["adjustments"] if (a.get("review") or {}).get("verdict") == "disagree"),
            "changed": nchanges, "undecided": sum(1 for n in out_nodes if n["undecided"]), "heuristic": sum(1 for n in out_nodes if n["heuristic"])}


# ---- 다시 셈(replay) — 라벨 지정을 LLM 호출 없이 반영(§13) ---------------------------------------------------------

def replay_of(g):
    """저장된 2단계 결과 g → build(replay=…) 입력. A 가 답한 유형 지식(괄호 유형은 규칙에 맞추기 전 A 가 본 그대로 aRole·aBasis·aReason) · 주 사슬(A 가 확인한 것만) ·
    B 가 적은 변경(asked — 없는 옛 결과는 적용된 값) · 미판정 노드 · 조정 판정과 그때의 슬롯 멤버(멤버가 그대로인 슬롯만 이어받게).
    LLM 없이 만든 결과(스크립트 대체 판정)는 None — 그때는 build(use_llm=False, hints=…) 가 곧 같은 길이다."""
    lm = g.get("llm") or {}
    if lm.get("fallback") or not lm.get("requested"):
        return None
    types = [{"type": t["type"], "ident": [t.get(k) for k in _TYPE_IDENT], "role": t["aRole"] if "aRole" in t else t.get("role"),
              "basis": (t.get("aBasis") if "aRole" in t else t.get("basis")) or "", "parents": list(t.get("parents") or []), "variantOf": t.get("variantOf") or "",
              "reason": (t.get("aReason") if "aRole" in t else t.get("reason")) or ""} for t in g.get("types") or []]
    fixed = lm["mainChainFixed"] if "mainChainFixed" in lm else bool(lm.get("mainChain")) and "mainChainRejected" not in lm  # 옛 결과엔 표지가 없어 어림
    changes = []
    for c in g.get("changes") or []:
        a, q = c.get("after") or {}, c.get("asked") or {}
        slot = a.get("slot") or {}
        changes.append({"id": c["id"], "parent": a.get("parent") or "", "role": q.get("role") or a.get("role") or "", "basis": q.get("basis") or "",
                        "template": q["template"] if "template" in q else slot.get("template") or "", "level": q["level"] if "level" in q else slot.get("level") or 0,
                        "reason": c.get("reason") or ""})
    members = defaultdict(lambda: defaultdict(list))  # 슬롯 → 서식 라벨 → 그 서식인 노드
    for n in g.get("nodes") or []:
        if n.get("template") and n.get("level") and n.get("role") in ("heading", "title") + ROOTED:
            members[f"{n['template']}|L{n['level']}"][n.get("fmt")].append(n["id"])
    return {"pairs": lm.get("pairs", True),  # 그 실행이 서식 쌍 판정(C·D)을 했는가(이 표지가 없는 옛 결과 = 함)
            "a": {"types": types, "mainChain": list(lm.get("mainChain") or []) if fixed else [], "summary": lm.get("summary") or ""},
            "changes": changes, "undecided": [n["id"] for n in g.get("nodes") or [] if n.get("undecided")], "slots": {k: dict(v) for k, v in members.items()},
            "adjustments": list(g.get("adjustments") or []), "sections": lm.get("sections") or 0,
            "from": (g.get("meta") or {}).get("run"), "calls": (lm.get("replay") or {}).get("calls", lm.get("calls")),
            "costUsd": (lm.get("replay") or {}).get("costUsd", lm.get("costUsd"))}


def _refold(changes, templates):
    """다시 셈 — 앞 실행의 B 슬롯 예외가 가리킨 앵커가 지금 없는 템플릿이고 그 사슬이 본문 주 사슬의 **첫 레터가 아닌 어느 레벨부터 레터 그대로**(그 슬롯 레벨까지) 이어지면
    **주 사슬의 같은 자리**로 옮겨 읽는다(잇닿은 사슬 규칙 전의 결과 — 「5-4.」 가 문서 맨 위에서 따로 템플릿 「N-N.›(N)›o」 이던 때 그 L3 으로 적은 「o」 = 지금 주 사슬 L4).
    레터가 어긋나면(옛 사슬이 주 사슬의 꼬리와 다름) 옮기지 않는다 — 전처럼 apply_changes 가 「모르는 템플릿」 으로 버린다. 그 밖의 변경은 그대로."""
    main = next((t for t in templates if t["kind"] == "main"), None)
    known = {t["anchor"] for t in templates}
    if main is None:
        return changes
    mc = list(main["chain"])
    out = []
    for c in changes or []:
        tpl, lv = str(c.get("template") or ""), c.get("level")
        if tpl.startswith("body:") and tpl not in known and isinstance(lv, int) and not isinstance(lv, bool) and lv >= 1:
            old = tpl[5:].split("›")
            at = mc.index(old[0]) if old[0] in mc else 0
            if at and old[:lv] == mc[at:at + lv]:
                c = {**c, "template": main["anchor"], "level": at + lv}
        out.append(c)
    return out


_TYPE_IDENT = ("area", "kind", "shape", "bold", "size")  # 유형의 정체(type_table 의 묶음 키) — 유형 id(Tn)는 후보 차례에 따라 달라질 수 있다


def _remap_types(a_types, types):
    """replay 의 유형 지식을 지금 유형 표의 id 로 옮긴다 — 정체(자리·종류·꼴·굵게·크기)가 같은 유형끼리. 지금 표에 없는 유형은 버린다(variantOf 도 함께 옮김)."""
    now = {tuple(t.get(k) for k in _TYPE_IDENT): tid for tid, t in types.items()}
    to = {x["type"]: now.get(tuple(x.get("ident") or ())) for x in a_types}
    return [{**x, "type": to[x["type"]], "variantOf": to.get(x.get("variantOf")) or ""} for x in a_types if to.get(x["type"])]


def _carry(replay, slots, by_id, graph):
    """앞 실행의 조정 판정을 되살린다 → (same, review) — build 의 C·D 결과 꼴. 쌍(슬롯, 대표 서식, 다른 서식)의 판정은 그 근거가 그대로일 때만 이어받는다:
    같은 슬롯(템플릿 앵커·레벨)이 있고 · 대표 서식이 그대로이고 · 그 다른 서식을 쓴 노드(판정 때 본 예문)가 같을 때. 아니면 미판정으로 둔다(astra 2026-11-10).
    미판정이던 쌍은 판정 없음 그대로, D 가 다르게 본 쌍의 1차 판정은 first 에서."""
    old = replay.get("slots") or {}
    reps = {}
    same, review = {}, {}
    for a in replay.get("adjustments") or []:
        slot, sk = f"{a['template']}|L{a['level']}", (a["template"], a["level"])
        ids = slots.get(sk)
        if not ids:
            continue
        if sk not in reps:
            reps[sk] = _slot_rep(ids, by_id, graph)[1]
        if reps[sk] != a["to"] or {i for i in ids if by_id[i]["fmt"] == a["from"]} != set((old.get(slot) or {}).get(a["from"]) or ()):
            continue
        k = (slot, a["to"], a["from"])
        r = a.get("review")
        first = a.get("first") if (r or {}).get("verdict") == "disagree" else a.get("decision")
        if first in ("adjust", "keep"):
            same[k] = {"same": first == "adjust", "reason": a.get("reason", "")}
        if r:
            review[k] = r
    return same, review


def _dedupe(edges):
    seen, out = set(), []
    for e in edges:
        k = (e["t"], e["from"], e["to"])
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out
