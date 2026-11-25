"""편집 구역 — LLM 검토(spec_구역 ② §8 「LLM 검토 — 스크립트가 못 정한 것」): 스크립트(app/zones.py 의 자동 판독)가 기관·차년도를 **못 정했거나 근거가 서로 달랐던** 본문 최상위 표·문단을
LLM 이 한 번 보고, **보낸 후보 id · 보낸 기관 열쇠 · 범위 안의 번호 · keep · none** 가운데서만 답한다. 글을 쓰지 않고 표의 칸·행 단위 값도 정하지 않는다(칸은 스크립트만).
순수 모듈 — `app.server` · 세션 · 작업 폴더를 모른다(끝점은 app/zones_api.py: 잠금 안에서 자료를 뜨고 → 잠금 밖에서 `ask` 한 번 → 다시 잠금 안에서 차례가 그대로일 때만 「LLM 이 지정」 으로 적는다).

- `candidates(info, view, blocks, tables=None)` = 보낼 후보(문서 차례 — 자르기 전): info = `zones.read` 의 결과 · view = `zones.build` 의 결과(지정·출처를 입힌 것) · blocks = 지금 문서의 블록 목록 ·
  tables = 3단계 표 구조(칸의 역할 — 이름표 칸의 값 칸을 가린다 · 작성요령 표를 뺀다).
  후보의 종류(`kind` — `KINDS`): `conflict`(근거가 서로 다름 — 블록의 기관이 conflict · 기준이 비워진 까닭(why)이 있음 · 표의 칸에 그런 것이 있음) · `unknown`(기관 자리인데 누구인지 못 읽음) ·
  `hint`(값이 안 붙은 표의 낌새 — `orgTag` 기관 이름표 칸의 값이 과제 기관 이름 그대로가 아니라 못 읽음 · `orgName` 이름표 칸 옆·아래가 아닌 짧은 칸에 과제 기관 이름이 하나만 있음 ·
  `yearTag` 차년도 이름표 칸의 값을 못 읽음(단계가 둘 이상인데 단계가 안 적힘 등)) · `alone`(같은 꼴의 이웃 표들은 기관이 붙었는데 혼자 빠진 표).
  **이미 지정된 블록(사람 · 앞선 LLM 검토)과 스크립트가 깨끗이 읽은 블록, 바꿀 수 있는 기준이 하나도 없는 블록(editable 이 모두 false)은 후보가 아니다.**
  한 표가 한 기관의 것일 수 없는 표(과제 기관 이름이 둘 이상 · 이름표 칸 아래의 값이 여럿)와 빈 양식도 후보가 아니다 —
  표 전체의 값만 물을 수 있어서다(칸은 스크립트만). 스크립트가 판정하지 못한 것 = 이 넷이다(CLAUDE.md 「분석 상태」 — LLM 단계는 스크립트가 판정한 것만 다시 보지 않는다).
- `cut(cands)` = 한 번에 `MAX` 개까지(넘으면 conflict → unknown → 나머지 차례로 남긴다) → (보낼 것, 잘렸나) · `kinds(cands)` = 종류마다 수 · `payload(info, cands)` = 보낼 자료.
- `ask(payload)` = 한 번 호출(`what` = "zones-llm") → {data, prompt, call, guide}. 프롬프트 = `CONTRACT` + 판단 지침(`merge_guides` zones — app/merge_guides_default/zones.md) + 자료(JSON).
  스키마는 보낸 것으로 좁힌다(`schema(payload)` — id · 기관 열쇠 · 번호를 enum 으로: 번호는 글 "1"·"2" …).
- `check(answer, payload)` = 답을 **보낸 자료에 대고** 검증 → (items[{id, label{org?, stage?, year?} — 지정으로 적을 기준만, reason, keep}], dropped[{id, dim?, value?, why}]).
  받는 것 = 그 후보의 `editable`(기준별로 바꿀 수 있는지 — `candidates` 가 계산해 자료에 싣는다)이 true 인 기준뿐: 기관은 정해지지 않았거나(모름 · 확인 필요) 기관이 안 붙은 낌새 후보이거나
  칸에서 **기관** 근거가 엇갈린 표일 때만 · 단계·차년도는 비어 있을 때만. 차년도·단계만 엇갈린 표의 기관은 못 바꾼다(astra 결과 검토 P1-3 — 넓은 「칸의 근거가 다른 표」 예외를 없앰).
  모르는 id · 같은 후보의 둘째 답 · 모르는 열쇠 · 범위 밖의 번호 · 바꿀 수 없는 기준에 적은 값·none · 서로 안 맞는 단계와 차년도는 버린다(그 기준만 그대로 — 나머지는 받는다).
- `parts()` = 화면 「지침」 이 보이는 글(계약 · 판단 지침)."""
import json
import re
from collections import Counter

from app import prompt_texts
from app import llm, merge_guides, zones
from app import merge_gather_frame as F

GUIDE = "zones"            # merge_guides 의 지침 이름
WHAT = "zones-llm"         # llm.call 의 호출 이름(agent_settings.PREFIX → 에이전트 zone_review)
KINDS = ("conflict", "unknown", "hint", "alone")
SIGNS = ("orgTag", "orgName", "yearTag", "cells")
MAX = 150                  # 한 번에 보내는 후보 수
NEAR_SPAN = 80             # 「이웃한 같은 꼴의 표」 — 본문 최상위 블록으로 이만큼 안에 있는 것만
CELL_LEN, CELLS_MAX, PARA_LEN, NEAR_LEN, PATH_LEN, PATH_MAX, REASON_MAX = 40, 40, 80, 40, 40, 4, 200   # 칸 글 · 표마다 칸 수 · 문단 글 · 앞뒤 블록 글 · 윗 제목 글 · 윗 제목 수 · 까닭 글
TAGS_MAX, BELOW_MAX, HEAD_MAX, SIDE_MAX, NAMES_MAX, CONF_MAX = 4, 3, 12, 8, 5, 6                       # 표마다 싣는 이름표 칸 · 그 아래 칸 · 머리 줄 칸 · 첫 열 칸 · 기관 이름 · 근거가 다른 칸
WORD = ("none", "keep")    # 답의 낱말 — 그 기준 없음 · 스크립트 값 그대로
FIXED = "바꿀 수 없는 기준(editable false) — 스크립트가 읽은 값이거나 그 기준의 근거가 엇갈리지 않았다"   # 버린 까닭 — 후보의 editable 이 false 인 기준에 적은 값·none

S = {"type": "string"}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items", "summary"], "properties": {
    "items": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "org", "stage", "year", "reason"],
                                         "properties": {"id": S, "org": S, "stage": S, "year": S, "reason": S}}},
    "summary": S}}

CONTRACT = """당신은 국가R&D 사업계획서(연구개발계획서)의 **편집 구역**을 검토하는 검토자입니다. 편집 구역 = 문서의 표·문단이 과제의 **어느 기관 · 어느 단계 · 어느 차년도의 것인지** 식별한 것입니다
(편집기 안의 표시입니다 — 문서는 바뀌지 않습니다). 스크립트가 먼저 문서 전체를 읽어 값을 붙였고, 여기 온 후보는 그 가운데 스크립트가 **못 정했거나 근거가 서로 달랐던** 표·문단입니다.
후보마다 기준(기관 · 단계 · 차년도)별로 **스크립트 값 그대로(keep) · 값 하나 · 그 기준 없음(none)** 가운데 고르기만 합니다. 글을 쓰거나 고치지 않고, 표의 칸·행 단위 값도 정하지 않습니다
(행마다 기관이 다른 표의 행은 스크립트가 칸에서 읽습니다). 무엇을 그 기관·그 차년도의 표·글로 보는지는 아래 「판단 지침」 을 따릅니다.

### 자료
orgs = 과제의 기관 [{key: 답에 쓸 열쇠, name: 이름, role: lead 주관 · joint 공동}] · stages = 단계마다 차년도 수(예 [2, 3] = 1단계 2년 + 2단계 3년) · years = 차년도의 수 ·
period = 사업기간 {start, end}(값이 있을 때만 — 연도만 적힌 글을 차년도와 맞춰 볼 때 씁니다).
**차년도는 전체 차례의 번호**입니다 — stages 가 [2, 3] 이면 2단계 1차년도 = 3 입니다.
candidates[] — 후보 하나(본문의 표 또는 문단):
- id = 답에 **글자 그대로** 돌려줄 값 · type: table 표 · paragraph 문단.
- editable = 이 후보에서 **정할 수 있는 기준** {org, stage, year: true | false}. 기관(org)은 기관이 정해지지 않았거나(read 의 orgKind 가 unknown · conflict) 기관이 안 붙은 낌새 후보이거나
  표의 칸에서 **기관** 근거가 엇갈릴 때만 true 이고, 단계·차년도는 그 기준이 비어 있을 때만 true 입니다. false 인 기준은 스크립트 값이 그대로 쓰입니다.
- kind = 후보가 된 까닭: conflict(스크립트가 읽은 근거가 서로 다름) · unknown(기관 자리인데 누구인지 못 읽음) · hint(값이 안 붙었는데 낌새가 있는 표) · alone(같은 꼴의 이웃 표들은 기관이 붙었는데 혼자 빠진 표).
- signs = 낌새의 세부: orgTag(기관 이름표 칸 옆·아래의 값을 스크립트가 못 읽음 — 과제 기관 이름 그대로가 아님) · orgName(표의 짧은 칸에 과제 기관 이름이 한 기관만 적혀 있는데 규칙에 안 걸려 기관이 안 붙음) ·
  yearTag(차년도 이름표 칸 옆·아래의 값을 못 읽음 — 단계가 안 적힌 차년도 · 연도만 적힌 글) · cells(표의 칸에서 근거가 서로 다름).
- path = 윗 제목 사슬(바깥 → 안) · prev · next = 바로 앞·뒤 블록 {text: 글, org · stage · year: 그 블록의 구역 값 — org 는 열쇠 · "unknown"(기관 모름) · "conflict"(확인 필요), 값이 없으면 공통 자리}.
- read = 스크립트가 읽은 값 {orgKind: org(기관이 정해짐) · unknown · conflict, org: 열쇠, stage, year, ev: 기준마다 근거 — group(값마다 되풀이되는 자리) · cell(표의 칸) · path(윗 제목) · origin(취합으로 들어온 내용),
  why: 서로 달랐던 근거}. read 가 없으면 값이 하나도 안 붙은 것입니다.
  why 의 꼴: byNo = 자리의 번호(주관 · 공동 k)로 읽은 기관 · byName = 그 자리의 라벨 글에 적힌 기관들 · byGroup = 되풀이 자리가 말한 기관 · byPath = 윗 제목이 말한 기관 · byCell = 표의 칸이 말한 기관들 ·
  year · stage = {byGroup, byCell}(되풀이 자리와 표의 칸이 다르게 말함 — 그 기준은 비워 두었습니다).
- 문단: text = 문단 글.
- 표: size "행×열" · head = 첫 행의 칸 글 · side = 첫 열의 칸 글 · tags = 이름표 칸 [{tag: 이름표 칸 글, right: 그 옆(같은 행) 칸 글, below: 그 아래(같은 열) 칸 글들}] ·
  names = 칸에 적힌 과제 기관 [{org: 열쇠, n: 그런 칸 수}] · cells = 근거가 서로 다른 칸 [{r: 행(0부터), text: 칸 글, why}](cellsN = 그런 칸의 수) ·
  like = 같은 꼴의 이웃 표 {prev · next: {org: 그 표의 기관 열쇠, text: 첫 글}, n: 같은 꼴의 표 수}.
  글은 줄여 실었고 표의 모든 칸이 실린 것은 아닙니다 — 실린 것만으로 가릴 수 없으면 그대로(keep) 둡니다.

### 답
items: 후보마다 한 줄 {id, org, stage, year, reason} · summary = 전체 판단 두세 문장.
- org = orgs 의 key 하나 · "none"(어느 기관의 것도 아님 — 공통) · "keep"(스크립트 값 그대로).
- stage · year = 번호를 글로("1" · "2" … — stage 는 1부터 단계 수까지, year 는 1부터 years 까지의 **전체 차례**) · "none"(그 기준 없음) · "keep".
  차년도를 정하면 단계는 그 차년도에서 정해지므로 stage 는 "keep" 으로 둡니다(둘 다 번호로 적으면 서로 맞아야 합니다).
- **keep 이 기본입니다.** 근거가 약하면 keep 으로 두고 reason 에 무엇이 모자란지 적습니다 — 틀린 값을 붙이는 것이 안 붙이는 것보다 나쁩니다.
- **후보의 editable 이 false 인 기준은 keep 만 답합니다.** 정할 수 있는 것은 editable 이 true 인 기준뿐입니다 — 값이나 none 을 적어도 그 기준은 버려집니다(나머지 기준의 답은 받습니다).
  스크립트가 읽은 값은 바꾸지 못하고, 차년도·단계의 근거만 엇갈린 표의 기관도 바꾸지 못합니다.
- 표의 칸·행마다 값이 다르면(행마다 기관이 다른 표 · 차년도가 줄지어 있는 표) 표 전체의 값은 정하지 않습니다 — keep 과 그 까닭.
- id 는 **입력에 있는 것만**, 후보마다 한 번. 입력에 없는 id · orgs 에 없는 열쇠 · 범위 밖의 번호는 버려지고, 답이 없는 후보는 그대로 둡니다.
- **글을 쓰지 않습니다.** reason = 그렇게 본 근거 한 문장(한국어 — 어느 칸 · 어느 제목 · 어느 이웃을 보고).
- keep 이 아닌 답은 서버가 그 표·문단의 「LLM 이 지정」 으로 적습니다. 사람이 하나씩 또는 모두 해제할 수 있고, 사람이 지정한 것은 바뀌지 않습니다."""

# 지침 절의 머리 문장(merge_guides.NOTE 는 자리 연결 검토의 말이라 이 검토의 것으로).
GUIDE_NOTE = ("아래는 이 검토의 **판단 기준**입니다(사용자가 관리하는 지침). 무엇을 그 기관 · 그 차년도의 표·글로 보고 무엇을 공통으로 보는지는 이 글을 따릅니다. "
              "답의 꼴 · 권한(보낸 후보 · 보낸 열쇠 · 범위 안의 번호 가운데 고르기만) · 「keep 이 기본」 은 위 계약 그대로입니다.")

# 지침 파일이 없을 때(끔·지움)만 붙는 최소 기준 — 지침의 원본은 app/merge_guides_default/zones.md(merge_guides).
FALLBACK_GUIDE = """

## 판단 기준(지침 파일 없음 — 기본)
- 기관 이름표 칸(「연구개발기관명」 등) 바로 옆 칸에 과제 기관 이름이 하나 적혀 있으면 그 표는 그 기관의 것이다. 행마다 기관이 다른 표 · 기관을 견주는 표는 한 기관의 것이 아니다(keep 또는 none).
- 과제 기관 목록에 없는 이름으로는 기관을 정하지 않는다. 근거가 서로 다르고 글만으로 가릴 수 없으면 keep."""

_WS = re.compile(r"\s+")
_NOTE = re.compile(r"\s*※.*$", re.S)                       # 「※」 뒤 안내 글은 값이 아니다(zones 의 판독과 같게)
_DIGIT = re.compile(r"\d+")
_WORDY = re.compile(r"[가-힣A-Za-z]{2}")                    # 이름일 수 있는 글(글자 둘 이상)
_NOTHING = re.compile(r"^(?:해당(?:사항)?없음|없음|미정|\(.*\)|（.*）)$")   # 값이 아닌 글(빈칸 뗀 글) — 「해당 없음」 · 괄호로 싼 안내 글
_FILL = re.compile(r"[oO○◯●□■xX*_.…·‧∙~\-]+")              # 자리표시 글자(「○○○」·「xx」) — 뗀 뒤에도 글자가 남아야 값이다


def _bare(text):
    return _WS.sub("", _NOTE.sub("", str(text or "")))


def _short(text, n):
    t = _WS.sub(" ", str(text or "")).strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def _int(x):
    return isinstance(x, int) and not isinstance(x, bool)


# ---- 후보 고르기 ------------------------------------------------------------------------------------------------------

def _look(b, keys, stages, roles=None):
    """본문 최상위 표 하나를 낌새를 보려고 읽는다 → {"g": 격자(merge_gather_frame.grid), "at": {(행, 열): 칸}, "tags": [(이름표 칸, 종류들, 옆 칸 | None, [아래 칸 …])],
    "names": Counter(열쇠 → 그 이름이 적힌 짧은 칸 수), "roles": 칸 id → 역할(3단계 표 구조 — 없으면 {}), "sig": 꼴 | None} | None(격자를 못 읽는 꼴).
    이름표 칸 = `zones._tag_kinds`(스크립트의 판독과 같은 낱말 · 같은 길이) · 이름 = `zones._names`. 꼴(sig) = 열 수 + 첫 두 행의 짧은 글(값 — 기관 이름 · 차년도 — 과 숫자는 뗀다: 기관마다 한 장씩 쓰는 표가 같은 꼴이 되게)."""
    try:
        g = F.grid(b)
    except (KeyError, TypeError, ValueError):
        return None
    at = {}
    for c in g["cells"]:
        for r in range(c["r"], c["r"] + c["rs"]):
            for k in range(c["c"], c["c"] + c["cs"]):
                at[(r, k)] = c
    tags, names, words = [], Counter(), []
    for c in g["cells"]:
        t = _bare(c["text"])
        kinds = zones._tag_kinds(c["text"], keys) if t else ()
        named = zones._names(c["text"], keys) if t and not kinds and len(t) <= CELL_LEN else []
        if kinds:
            below, seen = [], {c["id"]}
            for r in range(c["r"] + c["rs"], g["rows"]):
                x = at.get((r, c["c"]))
                if x is not None and x["id"] not in seen:
                    seen.add(x["id"])
                    below.append(x)
            right = at.get((c["r"], c["c"] + c["cs"]))
            tags.append((c, kinds, right if right is not None and right["id"] != c["id"] else None, below))
        if len(t) <= zones.CELL_MAX:   # 이름만 적은 짧은 칸 — 문장 속에 이름이 나온 긴 칸은 세지 않는다
            for k in named:
                names[k] += 1
        if c["r"] <= 1 and t and len(t) <= CELL_LEN and not named and zones._year_value(c["text"], stages) is None and (w := _DIGIT.sub("", t)):
            words.append(w)
    sig = (g["cols"], tuple(words)) if len(words) >= 2 and sum(map(len, words)) >= 4 else None
    return {"g": g, "at": at, "tags": tags, "names": names, "roles": roles or {}, "sig": sig}


def _value(look, tag, kind, keys, stages):
    """이름표 칸의 값인데 스크립트가 못 읽은 글 | None(그런 값이 없음 — 빈 양식 · 행마다 값이 다른 표 · 값마다 열이 있는 머리 행 · 값 칸이 아닌 머리 칸).
    이름표 칸이 **행 머리**(3단계 표 구조의 rowhead)면 값은 옆(같은 행) 칸이고 그 칸이 적는 칸(field)이어야 한다 · **열 머리**(colhead · corner)면 아래(같은 열) 칸들이고 그 글이 하나뿐이어야 한다
    (세로로 합친 칸 · 같은 글의 되풀이 — 여럿이면 행마다 값이 다른 표다). 표 구조가 없으면(그 표의 분석이 없음) 옆·아래 칸이 값인지 다른 머리 칸인지 가릴 수 없어 낌새로 치지 않는다.
    기관 값 = 글자가 있고 과제 기관 이름이 안 든 글(이름이 든 글은 스크립트가 일부러 안 읽은 것이다 — 값마다 열이 있는 머리 행 등) · 차년도 값 = 숫자가 있는데 스크립트가 못 읽은 글."""
    h, _, right, below = tag
    roles = look["roles"]

    def ok(c):
        t = _bare(c["text"]) if c is not None else ""
        if not t or len(t) > zones.CELL_MAX or zones._tag_kinds(c["text"], keys):
            return None
        if kind == "org":
            return t if _WORDY.search(_FILL.sub("", t)) and not _NOTHING.match(t) and not zones._names(c["text"], keys) else None
        return t if _DIGIT.search(t) and zones._year_value(c["text"], stages) is None else None
    role = roles.get(h["id"])
    if role in ("colhead", "corner"):
        filled = [x for x in below if _bare(x["text"]) and roles.get(x["id"]) not in ("title", "note", "spacer")]
        return ok(filled[0]) if len({_bare(x["text"]) for x in filled}) == 1 else None
    if role != "rowhead" or right is None or roles.get(right["id"]) != "field" or not (v := ok(right)):
        return None
    nxt = look["at"].get((h["r"], right["c"] + right["cs"]))
    if kind == "year" and nxt is not None and nxt["id"] not in (h["id"], right["id"]) and _DIGIT.search(_bare(nxt["text"])) and _bare(nxt["text"]) != v:
        return None   # 값이 옆으로 이어진다 — 차년도마다 열이 있는 머리 행
    return v


def _zone(lab):
    """앞뒤 블록의 구역 값(줄인 꼴) — org: 열쇠 | "unknown" | "conflict"."""
    if not lab:
        return {}
    out = {}
    if lab.get("orgKind"):
        out["org"] = lab.get("org") if lab["orgKind"] == "org" else lab["orgKind"]
    out.update({d: lab[d] for d in ("stage", "year") if lab.get(d) is not None})
    return out


def _read(lab):
    """스크립트가 읽은 값(후보의 read) | None(값이 하나도 없음) — 근거(ev)에는 취합 출처로 채운 기준도 적는다(origin)."""
    if not lab:
        return None
    out = {}
    if lab.get("orgKind"):
        out["orgKind"] = lab["orgKind"]
        if lab.get("org") is not None:
            out["org"] = lab["org"]
    out.update({d: lab[d] for d in ("stage", "year") if lab.get(d) is not None})
    ev = {**(lab.get("ev") or {}), **{d: v for d, v in (lab.get("src") or {}).items() if v != "auto"}}
    if ev:
        out["ev"] = ev
    if lab.get("why"):
        out["why"] = lab["why"]
    return out or None


def _odd(lab):
    """근거가 서로 달랐던 라벨인가 — 기관이 conflict 이거나 비워진 기준의 까닭(why)이 남았다(값이 하나도 없고 why 만 있는 라벨도)."""
    return bool(lab) and (lab.get("orgKind") == "conflict" or bool(lab.get("why")))


def _org_odd(lab):
    """**기관**의 근거가 엇갈린 라벨인가 — 기관이 conflict 이거나 why 에 기관 근거(zones.WHY_ORG)가 있다. 차년도·단계만 엇갈린 것(why.year · why.stage)은 아니다."""
    return bool(lab) and (lab.get("orgKind") == "conflict" or any(k in (lab.get("why") or {}) for k in zones.WHY_ORG))


def candidates(info, view, blocks, tables=None):
    """보낼 후보(문서 차례 · 자르기 전) → [{"id", "type": table|paragraph, "kind", "editable"{org, stage, year: 그 기준을 정할 수 있나}, "signs"?, "path"?, "prev"?, "next"?, "read"?,
    문단: "text" · 표: "size", "head", "side", "tags"?, "names"?, "cells"?, "cellsN"?, "like"?}].
    tables = 3단계 표 구조(heading_runs.tables — 없어도 된다): 칸의 역할로 이름표 칸의 값 칸을 가리고(`_value`), 작성요령 표(tempTables)는 낌새·이웃 후보에서 뺀다.
    프로젝트 구성 값이 없으면(기관·단계 목록이 없다) 빈 목록 — 고를 것이 없다. 지정된 블록(view 의 marks — 사람 · 앞선 LLM 검토)은 후보가 아니다."""
    info, view = info or {}, view or {}
    stages = [n for n in info.get("stages") or () if _int(n)]
    orgs = [o for o in info.get("orgs") or () if isinstance(o, dict) and o.get("key")]
    keys = sorted({o["key"] for o in orgs}, key=len, reverse=True)
    if not keys or not stages:
        return []
    order, kind_of, auto = list(info.get("order") or ()), info.get("kinds") or {}, info.get("auto") or {}
    cells_of, paths, texts = info.get("cellsOf") or {}, info.get("path") or {}, info.get("text") or {}
    labels, cell_labels = view.get("blocks") or {}, view.get("cells") or {}
    marked = {i for m in view.get("marks") or () if isinstance(m, dict) for i in m.get("ids") or ()}
    by_id = {b["id"]: b for b in blocks or () if isinstance(b, dict) and b.get("id") is not None and not b.get("captionOf")}
    s3 = tables if isinstance(tables, dict) else {}
    roles = {t["id"]: {c["id"]: c.get("role") for c in t.get("cells") or () if isinstance(c, dict) and "id" in c} for t in s3.get("tables") or () if isinstance(t, dict) and "id" in t}
    guides = {t["id"] for t in s3.get("tempTables") or () if isinstance(t, dict) and "id" in t}   # 작성요령 표·상자 — 내용이 아니다
    at_doc = {i: n for n, i in enumerate(order)}
    looks, has_org, groups = {}, {}, {}   # 표 id → _look · 표에 기관이 붙었나(표 또는 칸) · 꼴 → [표 id — 문서 차례]
    for i in order:
        if kind_of.get(i) != "tbl" or i not in by_id:
            continue
        looks[i] = _look(by_id[i], keys, stages, roles.get(i))
        lab = labels.get(i)
        has_org[i] = bool(lab and lab.get("orgKind")) or any((auto.get(c) or {}).get("orgKind") for c in cells_of.get(i) or ())
        if looks[i] and looks[i]["sig"] and i not in guides:
            groups.setdefault(looks[i]["sig"], []).append(i)
    filled = [i for i in order if kind_of.get(i) in ("p", "tbl") and (texts.get(i) or "").strip()]   # 앞뒤 블록 — 글이 있는 문단·표만
    pos = {i: n for n, i in enumerate(filled)}

    def near(i, step):
        n = pos.get(i)
        if n is None:   # 빈 문단 — 문서 차례에서 가장 가까운 글 있는 블록
            at = at_doc[i]
            seq = order[at + 1:] if step > 0 else reversed(order[:at])
            j = next((x for x in seq if x in pos), None)
        else:
            j = filled[n + step] if 0 <= n + step < len(filled) else None
        return {"text": _short(texts.get(j), NEAR_LEN), **_zone(labels.get(j))} if j is not None else None

    def owner(i):
        lab = labels.get(i)
        return lab.get("org") if lab and lab.get("orgKind") == "org" else None
    out = []
    for i in order:
        k = kind_of.get(i)
        if k not in ("p", "tbl") or i in marked or i not in by_id:
            continue
        lab, look, extra = labels.get(i) or {}, looks.get(i), {}
        org_kind = lab.get("orgKind")
        odd_cells = [(c, cl) for c, cl in (cell_labels.get(i) or {}).items() if _odd(cl)] if k == "tbl" else []
        signs = ["cells"] if odd_cells else []
        if k == "tbl" and look and i not in guides:   # 값이 안 붙은 표의 낌새 — 근거가 엇갈린 표에서도 본다(기관이 안 붙었으면 기관을 정할 수 있는지가 여기서 갈린다)
            if not has_org[i]:
                if any("org" in t[1] and _value(look, t, "org", keys, stages) for t in look["tags"]):
                    signs.append("orgTag")
                if len(look["names"]) == 1:
                    signs.append("orgName")
                if not {"orgTag", "orgName"} & set(signs) and look["sig"]:
                    same = groups.get(look["sig"]) or []
                    at = same.index(i)
                    sides = [same[j] for j in (at - 1, at + 1) if 0 <= j < len(same)]
                    if sides and all(owner(j) and abs(at_doc[j] - at_doc[i]) <= NEAR_SPAN for j in sides) and sum(1 for j in same if owner(j)) >= 2:
                        extra["like"] = {**{w: {"org": owner(j), "text": _short(texts.get(j), NEAR_LEN)} for w, j in (("prev", same[at - 1] if at else None), ("next", same[at + 1] if at + 1 < len(same) else None)) if j},
                                         "n": len(same)}
            if lab.get("year") is None and not any((auto.get(c) or {}).get("year") is not None for c in cells_of.get(i) or ()):
                if any("year" in t[1] and _value(look, t, "year", keys, stages) for t in look["tags"]):
                    signs.append("yearTag")
        hinted = bool({"orgTag", "orgName", "yearTag"} & set(signs))
        kind = "conflict" if _odd(lab) or odd_cells else "unknown" if org_kind == "unknown" else "hint" if hinted else "alone" if "like" in extra else None
        if kind is None:
            continue
        # 기준별로 바꿀 수 있는지 — 기관: 정해지지 않았거나(모름 · 확인 필요) · 기관이 안 붙은 낌새 후보이거나 · 칸에서 **기관** 근거가 엇갈릴 때만(차년도·단계만 엇갈린 것은 기관을 바꿀 권한을 주지 않는다).
        # 단계·차년도: 그 기준이 비어 있을 때만. 바꿀 수 있는 기준이 하나도 없으면 후보가 아니다(보내도 LLM 이 못 바꾼다).
        edit = {"org": org_kind in ("conflict", "unknown") or (org_kind is None and (kind in ("hint", "alone") or bool({"orgTag", "orgName"} & set(signs)) or "like" in extra))
                or any(_org_odd(cl) for _, cl in odd_cells), "stage": lab.get("stage") is None, "year": lab.get("year") is None}
        if not any(edit.values()):
            continue
        c = {"id": i, "type": "table" if k == "tbl" else "paragraph", "kind": kind, "editable": edit}
        if signs:
            c["signs"] = signs
        if paths.get(i):
            c["path"] = [_short(x, PATH_LEN) for x in paths[i][-PATH_MAX:]]
        for w, step in (("prev", -1), ("next", 1)):
            if (n := near(i, step)):
                c[w] = n
        if (r := _read(lab)):
            c["read"] = r
        if k == "p":
            c["text"] = _short(by_id[i].get("text"), PARA_LEN)
        else:
            c.update(_table_part(look, odd_cells) if look else {"head": [_short(texts.get(i), CELL_LEN)]})
            c.update(extra)
        out.append(c)
    return out


def _table_part(look, odd_cells):
    """표 후보에 싣는 글 — 이름표 칸과 그 옆·아래 → 머리 줄 → 첫 열 차례로 CELLS_MAX 칸까지(칸마다 CELL_LEN 자) + 칸에 적힌 과제 기관 + 근거가 다른 칸."""
    g = look["g"]
    txt = lambda c: _short(c["text"], CELL_LEN)  # noqa: E731
    out, left, tags = {"size": f"{g['rows']}x{g['cols']}"}, CELLS_MAX, []
    for h, _, right, below in look["tags"][:TAGS_MAX]:
        row = {"tag": txt(h)}
        if right is not None and _bare(right["text"]):
            row["right"] = txt(right)
        if (b := [txt(x) for x in below if _bare(x["text"])][:BELOW_MAX]):
            row["below"] = b
        left -= 1 + ("right" in row) + len(row.get("below") or ())
        tags.append(row)
    out["head"] = [txt(c) for c in g["cells"] if c["r"] == 0 and _bare(c["text"])][:max(0, min(HEAD_MAX, left))]
    left -= len(out["head"])
    out["side"] = [txt(c) for c in g["cells"] if c["c"] == 0 and c["r"] >= 1 and _bare(c["text"])][:max(0, min(SIDE_MAX, left))]
    if tags:
        out["tags"] = tags
    if look["names"]:
        out["names"] = [{"org": k, "n": n} for k, n in look["names"].most_common(NAMES_MAX)]
    if odd_cells:
        by = {c["id"]: c for c in g["cells"]}
        rows, seen = [], set()
        for cid, lab in sorted(odd_cells, key=lambda x: (by[x[0]]["r"], by[x[0]]["c"]) if x[0] in by else (0, 0)):
            why = lab.get("why") or {}
            mark = (by[cid]["r"] if cid in by else None, json.dumps(why, ensure_ascii=False, sort_keys=True))
            if cid in by and mark not in seen and len(rows) < CONF_MAX:   # 한 행의 칸들은 까닭이 같다 — 행마다 한 줄
                seen.add(mark)
                rows.append({"r": by[cid]["r"], "text": txt(by[cid]), "why": why})
        out["cells"], out["cellsN"] = rows, len(odd_cells)
    return out


def kinds(cands):
    """종류마다 후보 수 {conflict, unknown, hint, alone}."""
    n = Counter(c.get("kind") for c in cands or ())
    return {k: n.get(k, 0) for k in KINDS}


def cut(cands, limit=MAX):
    """한 번에 limit 개까지 → (보낼 후보 — 문서 차례, 잘렸나). 넘으면 conflict → unknown → 나머지(문서 차례) 순으로 남긴다."""
    cands = list(cands or ())
    if len(cands) <= limit:
        return cands, False
    rank = {"conflict": 0, "unknown": 1}
    keep = sorted(sorted(range(len(cands)), key=lambda n: (rank.get(cands[n].get("kind"), 2), n))[:max(0, limit)])
    return [cands[n] for n in keep], True


def payload(info, cands, period=None):
    """LLM 에 보낼 자료(JSON 으로 낼 dict) — 과제 기관 · 단계마다 차년도 수 · 차년도 수(전체 차례) · 후보. period = 사업기간 {start, end}(프로젝트 구성 값에 있을 때만 싣는다 — 연도만 적힌 값을 차년도와 맞춰 볼 때)."""
    info = info or {}
    stages = [n for n in info.get("stages") or () if _int(n)]
    out = {"orgs": [{"key": o["key"], "name": o.get("name") or o["key"], "role": o.get("role")} for o in info.get("orgs") or () if isinstance(o, dict) and o.get("key")],
           "stages": stages, "years": sum(stages)}
    if isinstance(period, dict) and all(isinstance(period.get(k), str) and period[k] for k in ("start", "end")):
        out["period"] = {"start": period["start"], "end": period["end"]}
    return {**out, "candidates": list(cands or ())}


# ---- 프롬프트 · 「지침」 보기 · 호출 --------------------------------------------------------------------------------------

def guide_part(guide=None):
    """프롬프트의 지침 절 — guide = merge_guides.get 꼴(None = 지금의 `zones` 지침을 읽음, False = 지침 없이). 지침 파일이 없으면 최소 기준(FALLBACK_GUIDE)."""
    if guide is False:
        return FALLBACK_GUIDE
    return merge_guides.part(merge_guides.get(GUIDE) if guide is None else guide, GUIDE_NOTE) or FALLBACK_GUIDE


def prompt(payload, guide=None):
    """프롬프트 글 = 계약 + 판단 지침 절 + 자료(JSON)."""
    return prompt_texts.contract(__name__) + guide_part(guide) + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parts(guide=None):
    """화면의 「지침」 보기에 싣는 것 — 이 검토의 프롬프트를 이루는 글들(자료 빼고) [{key: contract|guide, title, text, source, note}]. prompt() 와 같은 차례(merge_gather_llm.parts 와 같은 꼴)."""
    g = merge_guides.get(GUIDE) if guide is None else guide
    out = [{"key": "contract", "title": "계약 — 역할 · 자료 설명 · 답의 꼴 · 권한", "text": prompt_texts.contract(__name__), "source": "app/zones_llm.py",
            "note": "코드에 든 글입니다(답을 검증하는 코드와 한 몸) — 판단 기준은 아래 지침에 있습니다"}]
    if g and merge_guides.body(g):
        out.append({"key": "guide", "title": f"판단 지침 — {g['title']}", "text": merge_guides.body(g), "source": g["path"], "note": "이 파일을 고치면 다음 실행부터 적용됩니다"})
    else:
        out.append({"key": "guide", "title": "판단 지침 — (지침 파일 없음: 기본 기준)", "text": FALLBACK_GUIDE.strip(), "source": "app/zones_llm.py",
                    "note": "app/merge_guides_default/zones.md 가 없어 기본 기준만 보냅니다"})
    return out


def schema(payload):
    """보낸 자료로 좁힌 스키마 — id = 보낸 후보 · org = 보낸 열쇠 + none·keep · stage·year = 범위 안의 번호(글) + none·keep. 답의 꼴은 SCHEMA 와 같다."""
    pick = lambda xs: {"type": "string", "enum": [*dict.fromkeys(x for x in xs if x not in WORD), *WORD]}  # noqa: E731
    stages = [n for n in payload.get("stages") or () if _int(n)]
    ids = list(dict.fromkeys(c["id"] for c in payload.get("candidates") or ()))
    item = {"id": {"type": "string", "enum": ids} if ids else S, "org": pick(o["key"] for o in payload.get("orgs") or ()),
            "stage": pick(str(n) for n in range(1, len(stages) + 1)), "year": pick(str(n) for n in range(1, sum(stages) + 1)), "reason": S}
    return {**SCHEMA, "properties": {**SCHEMA["properties"], "items": {"type": "array", "items": {**SCHEMA["properties"]["items"]["items"], "properties": item}}}}


def ask(payload, *, call=None, effort="medium", timeout=240.0, guide=None):
    """한 번 호출(잠금 밖) → {"data": 응답 | None, "prompt", "call": {backend, model, effort, ms, costUsd, error}, "guide": {name, title, sha1} | None(지침 글 없이 보냄)}."""
    g = merge_guides.get(GUIDE) if guide is None else guide
    content = prompt(payload, g if g else False)
    res = (call or llm.call)(schema(payload), content, WHAT, timeout=timeout, effort=effort)
    return {"data": res.get("data"), "prompt": content, "call": {k: res.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error")},
            "guide": merge_guides.brief(g) if g else None}


# ---- 답 검증 ----------------------------------------------------------------------------------------------------------

def _num(v):
    """답의 번호 → 정수 | None(번호가 아님) — 글 "2" 도 수 2 도 받는다."""
    if _int(v):
        return v
    if isinstance(v, str) and v.strip().isdigit() and len(v.strip()) <= 3:
        return int(v.strip())
    return None


def check(answer, payload):
    """응답(호출의 data)을 **보낸 자료에 대고** 검증 → (items, dropped).
    items = 받은 답(보낸 차례) [{"id", "label": {org?: 열쇠 | None(기관 없음), stage?: n, year?: n} — 지정으로 적을 기준만, "reason"(REASON_MAX 자), "keep": 적을 기준이 없음}].
    기준마다: keep · 빈 값 = 그대로 · none = 그 기준 없음 · 값 = 그 값. **받는 것은 그 후보의 editable 이 true 인 기준뿐이다**(`candidates` 가 기준마다 계산해 실은 것 — 없으면 아무 기준도 못 바꾼다):
    기관은 정해지지 않았거나(모름 · 확인 필요) 기관이 안 붙은 낌새 후보이거나 칸에서 기관 근거가 엇갈린 표일 때만, 단계·차년도는 비어 있을 때만. 차년도·단계만 엇갈린 표의 기관을 바꾸는 답은 버린다.
    스크립트가 읽은 값(후보의 read)과 같은 답은 그대로로 친다(값이 안 바뀌는 지정을 만들지 않는다 — 버린 것으로 세지도 않는다).
    dropped = 버린 것 [{"id", "dim"?, "value"?, "why"}] — 보낸 후보에 없는 id · 같은 후보의 둘째 답(첫 답을 쓴다) · orgs 에 없는 열쇠 · 범위 밖의 번호 · 바꿀 수 없는 기준에 적은 값·none(FIXED) ·
    서로 안 맞는 단계와 차년도(둘 다 버림) · 스크립트가 읽은 단계의 것이 아닌 차년도. 버린 기준만 그대로이고 나머지 기준은 받는다."""
    sent = {c["id"]: c for c in payload.get("candidates") or ()}
    orgs = [o for o in payload.get("orgs") or () if o.get("key")]
    keys, names = {o["key"] for o in orgs}, {o.get("name"): o["key"] for o in orgs if o.get("name")}
    stages = [n for n in payload.get("stages") or () if _int(n)]
    top = {"stage": len(stages), "year": sum(stages)}
    got, dropped = {}, []
    for r in (answer.get("items") if isinstance(answer, dict) else None) or ():
        if not isinstance(r, dict):
            continue
        rid = r.get("id") if isinstance(r.get("id"), str) else ""
        if rid not in sent or rid in got:
            dropped.append({"id": rid, "why": "같은 후보를 두 번" if rid in got else "보낸 후보에 없는 id"})
            continue
        cand = sent[rid]
        read = cand.get("read") or {}
        edit = cand.get("editable") if isinstance(cand.get("editable"), dict) else {}
        kind, label = read.get("orgKind"), {}

        def drop(d, v, why):
            dropped.append({"id": rid, "dim": d, "value": _short(v, CELL_LEN), "why": why})
        v = r.get("org")
        if v not in (None, "", "keep"):
            key = None if v == "none" else (v if v in keys else names.get(v)) if isinstance(v, str) else None
            if v != "none" and key is None:
                drop("org", v, "과제 기관에 없는 열쇠")
            elif kind in (None, "org") and key == (read.get("org") if kind == "org" else None):
                pass   # 스크립트 값과 같다(기관이 안 붙은 곳의 none · 같은 기관)
            elif edit.get("org") is not True:
                drop("org", v, FIXED)
            else:
                label["org"] = key
        for d in ("stage", "year"):
            v, have = r.get(d), read.get(d)
            if v in (None, "", "keep"):
                continue
            if v == "none":
                if have is not None:
                    drop(d, v, FIXED)
                continue
            n = _num(v)
            if n is None or not 1 <= n <= top[d]:
                drop(d, v, f"범위 밖의 번호(1~{top[d]})")
            elif have == n:
                pass   # 스크립트 값과 같다
            elif have is not None or edit.get(d) is not True:
                drop(d, v, FIXED)
            else:
                label[d] = n
        y = label.get("year")
        want = label.get("stage", read.get("stage"))
        if y is not None and want is not None and zones._stage_of(stages, y) != want:
            if "stage" in label:
                for d in ("stage", "year"):
                    drop(d, label.pop(d), "단계와 차년도가 서로 안 맞음")
            else:
                drop("year", label.pop("year"), f"스크립트가 읽은 단계({want}단계)의 차년도가 아니다")
        got[rid] = {"id": rid, "label": label, "reason": _short(r.get("reason"), REASON_MAX), "keep": not label}
    return [got[i] for i in sent if i in got], dropped
