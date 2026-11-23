"""병합 — 빈 자리 검토(spec_병합 ② §5-4, 2026-11-12 사용자 「여기 들어가지 않은 것들은 LLM 이 검토하고 넣어주는 기능 없나?」 → 물어서 받은 답 「표 + 단락 모두」):
묶음 짝(merge_pairs)·같은 이름 자리(merge_fixed)·표 대응(merge_table_map)을 다 거치고도 **빈 채로 남는 목적 자리**를 모아, 계획서(원본 문서)의 어디에서 가져올지 LLM 에 묻는다.
LLM 은 **원본 자리만 고른다**(글을 쓰지 않는다) — 넣을 글은 스크립트가 원본 문서에서 그대로 읽고, 넣어도 되는지도 지금 문서에서 다시 본다.

- `targets(T, F, fixed_plan, orig=None)` = 빈 자리 {"tables": [빈 표], "slots": [빈 칸 · 빈 라벨 줄]} — T·F = merge_fixed._side 꼴, fixed_plan = merge_fixed.plan 결과(원본 표가 안 정해진 표 줄),
  orig = 등록된 빈 양식으로 올린 원본의 칸 {id: {text}} | None(merge_api._orig — 서식 예시가 그대로인 칸도 빈 칸으로 본다: 「2-1 추진 일정」 의 예시 행).
  빈 표 = 원본 표가 안 정해진 목적 표이고 필드 칸이 모두 빈 것(자리표시·글머리만 든 칸 · 서식 그대로인 칸 포함) — 제목이나 위 제목이 「실적」·「성과」·「달성」·「수행 결과」 인 표는 뺀다(계획서에 없는 내용 — 할 일 프롬프트).
  빈 칸 = 그 표가 작고(필드 칸 CELLS_MAX 이하) 서식이 **글머리 자리표시**(「ㅇ」 줄)를 둔 칸 — 글 줄을 받는 칸이다. 머리 글이 있어야 하고 머리에 「실적」·「달성」 이 든 칸은 뺀다 ·
  빈 라벨 줄 = 구분 기준 항목 밖의 본문 줄 가운데 글이 괄호 라벨뿐이고(「- (정의)」) 아래에 내용·하위 줄이 없는 것.
- `data(T, F, found)` = LLM 에 보낼 자료 단위들 + 검증에 쓸 것(`ctx`) — 빈 자리마다 후보(원본 표 · 원본 줄)를 스크립트가 골라 싣는다(글자 조각 겹침).
- `prepare(T, F, fixed_plan, saved, again)` → `ask(prep, job, links)`(둘을 이은 것 = `review`) = 묻고(`llm.ask_all` — 목적 문서의 장마다 · UNIT_MAX 개씩) 답을 검증해 → {"tables": {표 id: {from | None, reason}}, "slots": {id: {from | None, take, kind, was, reason}},
  "rejected", "units", "asked", …}. 이미 답이 있는 자리(saved — 「원본 없음」 포함)는 다시 안 묻는다(again 이면 전부).
  **물었는데 LLM 의 답에 빠진 자리**는 「원본 없음」 이 아니라 `missing: true`(까닭 `MISSING`)로 적는다 — 답이 있는 자리로 세지 않아(`_has`) 다음 검토가 다시 묻고 `open_count` 에 든다
  (spec_작업 ② §22 「구현 계약」 22-1 ⓑ: 「후보가 없어 안 물음 / LLM 이 없다고 답함 / 답 누락」 을 답을 만드는 곳부터 가른다).
- `plan(T, F, gaps)` = 넣기 계획(문서를 안 고침) — 답이 있는 빈 칸·빈 라벨 줄마다 원본 글을 **지금 문서에서** 읽어 넣을 글을 정한다 → {"cells", "lines", "items", "skipped", "counts", "todo"}.
  빈 표 ← 원본 표는 여기서 안 넣는다 — merge.json `tables`(표 짝)에 적혀 같은 이름 자리·표 대응이 넣는다.
- `apply(to_doc, plan, from_doc=None)` = 계획을 목적 문서에 → {"cells", "lines", "blocks", "inserted", "skipped", "dropped", "fitted"}. 지금 비어 있을 때만 쓴다.
다시 계획하면 넣은 자리는 글이 같아 일 없음.

**라벨 줄 아래의 내용 · 쪽 한도**(2026-11-22 사용자 「서식은 다르지만 매칭이 되잖아 … 2페이지 요약이라는 문구가 있으니 2페이지 내에서 개요를 매핑하도록」 — ② §5-6): 빈 라벨 줄(「- (정의)」)은
라벨과 내용이 한 줄인 원본(「o (정의) …」 — take line)만이 아니라 **제목 줄 아래에 내용을 적은 원본**(「□ 개발 기술(제품)의 정의」 아래 — take content)도 받는다: 그 내용 블록을 라벨 줄 뒤에
원본 모양 그대로 복사한다. 위 제목(또는 그 자리의 매칭 지침)에 「N page 이내」 가 있는 자리는 **줄 한도**(`budget` — N 쪽을 그 제목 아래 라벨 줄 수로 나눈 것)가 있고 한도 안의 앞부분만 넣는다(뒤는 기관이 작성) —
넣는 것은 **글과 글 상자(1칸 표)** 다: 표 · 그림은 요약 자리에 넣지 않고 건너뛴다(그림 하나가 반 쪽이다). 한도가 없는 자리의 내용은 전처럼 통째로만(길거나 표 · 그림이 들면 안 넣는다). `guides` = 목적 양식의 매칭 지침(app/link_guides.py `entries`) — 그 자리에 걸린 것을 자료의 `guide` 로 싣는다."""
import json
import math
import re

from app import job_prompts, llm, merge_guides
from app import link_guides as LG
from app import place_guides as PG
from app import merge_fill as MF
from app import merge_fixed as X
from app import merge_pairs as P
from app import merge_tables as MT
from app.division_profiles import _structure as structure

S_ = {"type": "string"}


def _obj(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def _arr(item):
    return {"type": "array", "items": item}


SCHEMA = _obj({"tables": _arr(_obj({"to": S_, "from": S_, "reason": S_})), "slots": _arr(_obj({"to": S_, "from": S_, "take": S_, "reason": S_}))})
GUIDE, MODEL = "gaps", "claude-opus-5-5"
CELLS_MAX, TABLE_CANDS, LINE_CANDS, UNIT_MAX = 12, 5, 8, 14   # 빈 칸을 낱낱이 보는 표의 빈 칸 수 · 빈 표의 원본 표 후보 · 빈 칸/줄의 원본 줄 후보 · 한 호출의 빈 자리 수
TABLE_HIT, OWN_MIN = 4, 10   # 원본 표 후보가 되려면 겹쳐야 하는 글자 조각 수 · 줄 자체의 글(line)로 옮기려면 라벨을 뗀 뒤 남아야 하는 글자 수
LINES_MAX, CHARS_MAX, PREVIEW, TEXT = 20, 2000, 160, 90   # 옮길 내용의 줄 수·글자 수 상한(넘으면 긴 절 — 기관이 작성) · 후보 미리보기 · 줄 글 길이
CELL_LINES_MAX, CELL_CHARS_MAX = 60, 6000   # 빈 **칸**에 옮길 내용의 상한 — 기관마다의 목표 줄이 한 칸에 모이는 자리(「추진목표」 ← 그 차년도의 기관별 개발 목표: 실제 작성본 7기관이 20줄을 넘었다)
PAGE_LINES, LINE_CHARS, LINE_MM, BUDGET_MIN = 36, 42, 7.0, 4   # 한 쪽의 줄 수 · 한 줄의 글자 수 · 한 줄의 높이(A4 본문 12pt · 줄 간격 160% 어림) · 라벨 줄 하나의 줄 한도 바닥
TITLE_LEN = 45   # 이 글자 수 이하의 그래프 줄은 제목 꼴로 본다(한도에 잘린 끝에 남기지 않는다)
WHY = ("occupied", "noSource", "long", "object", "year", "org")

CONTRACT = """당신은 국가R&D 사업계획서(연구개발계획서 — **원본 문서**)의 내용을 연차보고서(**목적 문서**)에 옮긴 뒤에도 **빈 채로 남은 자리**를 보고,
그 자리에 들어갈 내용이 원본 문서의 **어디에 있는지** 고르는 검토자입니다. 글을 쓰지 않습니다 — 원본의 표나 줄을 **고르기만** 하면 스크립트가 그 글을 그대로 옮깁니다.

### 자료
tables = 빈 표 [{key, title(소속 제목), path(그 위 제목들), ctx(year = 어느 차년도의 표인지 · org = 어느 기관의 표인지 — null 이면 모름/전체), heads(머리 칸 글), shape{rows, cols},
  candidates[원본 표 — {key, title, path, ctx, heads, shape}]}].
slots = 빈 글 자리 [{id, kind("cell" = 빈 표의 칸 · "line" = 라벨만 있는 줄), label(칸의 머리 글 · 줄의 라벨), path(그 위 제목들), table(칸이면 그 표의 key), ctx,
  candidates[원본 줄 — {id, path, text(그 줄의 글), year, lines(그 줄 **아래** 내용 줄 수), preview(아래 내용의 앞부분)}]}].
자리(tables · slots)에 guide 가 있으면 **그 표 · 그 본문 자리에 사용자가 적어 둔 매칭 지침**입니다 — 그 자리는 판단 지침보다 그 글을 먼저 따릅니다.
slots 의 budget = 그 자리에 넣을 수 있는 **줄 수**(서식이 「N page 이내」 로 적으라고 한 자리 — 스크립트가 쪽 수를 그 제목 아래 라벨 줄들에 나눈 것).
current = 목적 문서의 당해 차년도(「해당연도」 = 이 차년도 · 「다음 연도」 = 그 다음).

### 답
- tables = 빈 표마다 한 줄 [{to: 빈 표 key, from: 같은 내용을 적는 원본 표의 key(그 표의 candidates 가운데) | "", reason}] — 같은 표가 없으면 from 은 "".
- slots = 빈 글 자리마다 한 줄 [{to: 자리 id, from: 원본 줄 id(그 자리의 candidates 가운데) | "", take, reason}] — 들어갈 내용이 없으면 from 은 "".
  take = "line"(그 줄 **자체의 글**을 옮김 — 「o (정의) …」 처럼 라벨과 내용이 한 줄에 있는 것) 또는 "content"(그 줄 **아래의 내용 줄들**을 옮김 — 「[1차년도 목표]」 아래 줄들).
  kind 가 "line" 인 자리(라벨만 있는 줄 「- (정의)」)도 둘 다 받습니다: 라벨과 내용이 한 줄이면 "line"(그 문단이 라벨 줄에 이어짐), 내용이 **제목 줄 아래**에 있으면(「□ … 의 정의」 아래 문단들) "content" —
  아래 내용이 라벨 줄 뒤에 원본 모양 그대로 들어갑니다. 두 서식의 제목 꼴 · 글머리가 달라도 **같은 내용을 적은 자리**면 고릅니다.
  budget 이 있는 자리는 그 줄 수까지만 **앞에서부터** 글과 글 상자가 옮겨지고(표 · 그림은 건너뜁니다 — 뒤는 기관이 작성), budget 이 없는 자리의 "content" 는 표 · 그림 없는 글일 때만 받습니다 — 줄 자리(kind "line")는 20줄 이하,
  **표 칸 자리(kind "cell")는 60줄 이하**(기관마다의 목표 줄이 한 칸에 모이는 「추진목표」 ← 그 차년도의 「개발 목표」 아래 줄들 — 30줄쯤이어도 고릅니다. 줄 수는 스크립트가 다시 셉니다).
- 한 빈 표에 원본 표를 고르면 그 표의 칸(slots 의 table 이 그 표인 것)은 from 을 "" 로 둡니다(표째로 옮깁니다).
- 입력에 있는 key·id 만 씁니다. 확신이 없으면 "" 로 둡니다 — 틀린 내용이 들어가는 것보다 비어 있는 것이 낫습니다.
- reason 은 왜 그렇게 골랐는지(또는 왜 비웠는지) 한 문장."""

FALLBACK_GUIDE = """- 같은 내용을 적는 자리끼리만 잇는다(제목의 글자가 달라도 뜻이 같으면 같은 자리). 계획서에 없는 내용(실적·달성·성과)은 비운다.
- 특정 차년도의 자리는 그 차년도의 내용하고만, 특정 기관의 자리는 그 기관의 내용하고만 잇는다."""

LINK_NOTE = ("아래는 목적 문서 양식의 **양식 정보 「자리 연결」 절**입니다 — 사용자가 「어느 표·단락을 어디와 이을지」 를 적어 둔 것(연결 코멘트). 판단 지침보다 먼저 따릅니다. "
             "답의 꼴과 「입력에 있는 key·id 만」 은 위 계약 그대로입니다.")

_BULLET = re.compile(r"^[\sㅇoO○●◦·ㆍ∙⋅•\-–—▪■□◇*]*$")   # 글머리만 든 줄(서식의 자리표시)
_LABEL = re.compile(r"^\(\s*([^()]{1,30}?)\s*\)\s*:?$")   # 괄호 라벨뿐인 줄 「(정의)」
_LABELED = re.compile(r"^\(\s*[^()]{1,30}?\s*\)")   # 괄호 라벨로 시작하는 줄 — 채운 뒤에도 그 제목 아래 라벨 줄의 수가 같게(줄 한도를 나누는 수)
_RESULT = re.compile(r"실적|달성")   # 결과를 적는 자리 — 계획서에 없는 내용(할 일 프롬프트)
_RESULT_TITLE = re.compile(r"실적|성과|달성|수행\s*결과")   # 그 제목 아래의 표는 결과를 적는 표 — 원본 표를 찾지 않는다(칸의 글머리 자리표시는 따로 본다)
_TOC = re.compile(r"\t\s*\d+\s*$")   # 차례의 줄(「2-1. 최종목표\t 11」)
_KEEP = re.compile(r"[0-9A-Za-z가-힣]")
_YEAR = re.compile(r"(\d+)\s*차\s*년도")


# ---- 읽을거리 ------------------------------------------------------------------------------------------------

def _blank(text):
    """칸·줄이 비었나 — 빈 글 · 자리표시(merge_tables._empty) · 글머리만 든 줄들."""
    return MT._empty(text) or all(_BULLET.fullmatch(x) for x in (text or "").split("\n"))


def _bi(text):
    """글의 두 글자 조각 모음(글자·숫자만 — 띄어쓰기·기호 무시). 한 글자면 그 글자."""
    s = "".join(_KEEP.findall(text or ""))
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def _nodes(S):
    """그 쪽의 그래프 색인(S 에 한 번 담아 둔다) → {"by": id → 노드, "kids": 부모 id → [자식 id]}."""
    g = S.get("_gaps")
    if g is None:
        by = {n["id"]: n for n in S["nodes"]}
        kids = {}
        for n in S["nodes"]:
            kids.setdefault(n.get("parent"), []).append(n["id"])
        g = S["_gaps"] = {"by": by, "kids": kids}
    return g


def _ups(S, nid, limit=12):
    """노드의 조상(안 → 바깥)."""
    by, out, seen = _nodes(S)["by"], [], {nid}
    p = by.get((by.get(nid) or {}).get("parent"))
    while p is not None and p["id"] not in seen and len(out) < limit:
        seen.add(p["id"])
        out.append(p)
        p = by.get(p.get("parent"))
    return out


def _line(n):
    return P._ws(f"{n.get('letter') or ''} {n.get('text') or ''}")


def _path(S, nid, keep=3):
    """위 제목들(바깥 → 안, 끝 keep 개)."""
    return [x for x in (_line(p)[:60] for p in _ups(S, nid)[::-1]) if x][-keep:]


def _node_ctx(S, nid):
    """줄의 맥락 {"year", "org"} — 그 줄을 품은 차년도 절·기관 절(merge_fixed._side 의 hold), 없으면 그 줄과 위 제목들에 적힌 「N차년도」(가까운 것부터)·「다음 연도」·「해당연도」·기관 이름."""
    held = S["hold"].get(nid) or {}
    by = _nodes(S)["by"]
    chain = [n for n in (by.get(nid), *_ups(S, nid)) if n]
    texts = [_line(n) for n in chain]
    cur = S["values"].get("current") or 1
    year = held.get("year") or next((y for y in (MT._year_no(t, S["values"]) for t in texts if _YEAR.search(t)) if y is not None), None)
    if year is None:
        joined = " ".join(texts)
        year = cur + 1 if P._NEXT.search(joined) else cur if P._THIS.search(joined) else None
    return {"year": year, "org": held.get("org") or P._path_org(texts[::-1], S["org_names"])}


def content(S, nid):
    """원본 줄 **아래의 내용** = 그 줄 다음 형제 블록 가운데 그 줄의 하위(그래프의 자손)이거나 그래프 줄이 아닌 것 — 다음 같은·윗 레벨 줄 앞까지. 캡션 블록은 뺀다(표·그림과 함께 간다)."""
    seq = S["where"].get(nid) or ()
    k = next((i for i, b in enumerate(seq) if b["id"] == nid), None)
    by, out = _nodes(S)["by"], []
    for b in seq[k + 1:] if k is not None else ():
        if b["id"] in S["heads"] and not any(p["id"] == nid for p in _ups(S, b["id"])):
            break
        if b["id"] in by and by[b["id"]].get("role") == "title":
            break
        if not b.get("captionOf"):
            out.append(b)
    return out


def _lines(blocks):
    """내용 블록 → (글 줄 목록, 표·그림이 들었나)."""
    obj = any(b.get("type") in ("table", "image") for b in blocks)
    return [P._ws(b.get("text") or "") for b in blocks if b.get("type") not in ("table", "image") and (b.get("text") or "").strip()], obj


def _live(S, n):
    """그 줄의 **지금 글**(그래프의 글은 분석 때 것)."""
    return P._ws((S["idx"].get(n["id"]) or {}).get("text") or _line(n))


def _unlettered(S, n):
    """지금 글에서 앞 레터(글머리)를 뗀 것."""
    live, letter = _live(S, n), P._ws(n.get("letter") or "")
    return live[len(letter):].strip() if letter and live.startswith(letter) else live


def _budget(T, nid, guides=None):
    """라벨 줄 자리의 **줄 한도** | None(모듈 설명 「쪽 한도」) — 그 줄 위 제목(가까운 것부터)의 지금 글이나 그 제목에 걸린 매칭 지침에 「N page 이내」 가 있으면,
    N 쪽의 줄 수에서 그 제목 아래 서식 줄(제목 · 라벨 줄)을 빼고 **그 제목 아래 라벨 줄 수로 나눈 것**(자리마다 같은 몫 — 다른 자리를 넣었는지와 무관하게 같은 값이라 다시 계획해도 안 바뀐다)."""
    for p in _ups(T, nid):
        text = _live(T, p)
        n = LG.pages(text) or next((g["pages"] for g in LG.match(guides, [text], "body") if g.get("pages")), None)
        if not n:
            continue
        under = [x for x in T["nodes"] if x["id"] in T["heads"] and x["id"] in T["idx"] and any(a["id"] == p["id"] for a in _ups(T, x["id"]))]
        labels = sum(1 for x in under if _LABELED.match(_unlettered(T, x)))
        return max(BUDGET_MIN, (n * PAGE_LINES - len(under) - 1) // max(1, labels))
    return None


def _cost(b):
    """내용 블록 하나가 차지하는 줄 수 어림 — 글 = 글자 수 / 한 줄 글자 수 · 표 = 행 수(와 칸 글의 줄 수 가운데 큰 것) + 1 · 그림 = 높이 / 한 줄 높이."""
    if b.get("type") == "image":
        return max(2, math.ceil((b.get("heightMm") or 60) / LINE_MM))
    if b.get("type") == "table":
        cells = b.get("cells") or ()
        rows = max((c["row"] + (c.get("rowSpan") or 1) for c in cells), default=1)
        return max(rows, math.ceil(sum(len(c.get("text") or "") for c in cells) / LINE_CHARS)) + 1
    return max(1, math.ceil(len(P._ws(b.get("text") or "")) / LINE_CHARS))


def _sig(b):
    """내용 블록의 견줄 꼴(종류 · 글 — 표는 칸 글) — 「이미 넣었나」 를 자리의 지금 글로 가린다."""
    text = P._ws(b.get("text") or "") or P._ws(" ".join(c.get("text") or "" for c in b.get("cells") or ()))
    return b.get("type"), text[:200]


def _own(S, nid, label=""):
    """원본 줄 자체의 글에서 앞 글머리와 (목적 라벨과 같은) 라벨을 뗀 것 — 「o (정의) 운항 중인 …」 → 「운항 중인 …」."""
    n = _nodes(S)["by"].get(nid) or {}
    text = P._ws((S["idx"].get(nid) or {}).get("text") or "")
    letter = P._ws(n.get("letter") or "")
    if letter and text.startswith(letter):
        text = text[len(letter):].strip()
    m = re.match(r"^\(\s*([^()]{1,30}?)\s*\)\s*:?\s*", text)
    if m and label and "".join(_KEEP.findall(m.group(1))) == "".join(_KEEP.findall(label)):
        text = text[m.end():]
    return text.strip()


# ---- 빈 자리 -------------------------------------------------------------------------------------------------

def _tight(text):
    """머리 글 다듬기 — 글자마다 띄어 쓴 머리(「추 진 목 표」)는 붙인다."""
    t = P._ws(text)
    return "".join(t.split(" ")) if t and all(len(w) == 1 for w in t.split(" ")) else t


def targets(T, F, fixed_plan, orig=None, guides=None, skip=()):
    """빈 자리(모듈 설명) → {"tables": [{key, t(3단계 표), ctx, free}], "slots": [{id, kind, label, table | None, ctx, was, budget(라벨 줄의 줄 한도 | None)}]}. guides = 목적 양식의 매칭 지침(쪽 한도를 읽는다) ·
    skip = 다른 길이 통째로 맡은 목적 표 id(일정 표 스크립트 merge_schedule — 그 표와 그 칸은 빈 자리가 아니다: LLM 에 다시 묻지 않는다)."""
    rows = {r["to"]: r for r in (fixed_plan or {}).get("tables") or ()}
    tables, slots = [], []
    asis = lambda cid, text: bool(orig) and cid in orig and P._ws(orig[cid].get("text") or "") == P._ws(text)  # noqa: E731 — 올린 빈 양식의 글 그대로(서식 예시·안내)
    for t in T["tables"]:
        if t["id"] not in T["idx"] or t["id"] in skip:
            continue
        row = rows.get(t["id"])
        if row and (row.get("status") == "paired" or row.get("mapped") or row.get("source") == "user"):
            continue   # 원본 표가 정해졌거나 · 표 대응이 맡았거나 · 사람이 끊은 표
        ctx = X._ctx(T, t)
        own = t.get("owner") or {}
        if row and not row.get("why") and not any(c["id"] in T["cov_tab"] for c in t["cells"]):   # 빈 표 — 같은 이름 자리의 표 줄에 있고(남는 칸 · 머리 칸이 있는 표) 맥락이 다른 원본뿐인 표가 아닌 것.
            free = X._free(T, t)                                                                    # 표 묶음(행·열)이 걸린 표는 뺀다 — 묶음 짝이 맡는 표다(남는 칸만 비어 있을 뿐)
            if free and all(_blank(X._text(T, c["id"])) or asis(c["id"], X._text(T, c["id"])) for c, _ in free) \
                    and not any(_RESULT_TITLE.search(P._ws(x)) for x in (*(own.get("path") or ()), own.get("text") or "")):
                tables.append({"key": t["id"], "t": t, "ctx": ctx, "free": free})
        # 빈 칸 — 서식이 글머리 자리표시(「ㅇ」 줄)를 둔 칸: 글 줄을 받는 칸이다. 3단계가 머리 칸을 못 읽은 표(모든 칸이 필드)도 본다 — 머리 글이 없으면 첫 행의 같은 열 칸
        live = T["idx"][t["id"]].get("cells") or ()
        marks = [c for c in live if c["id"] not in T["cov_tab"] and (c.get("text") or "").strip() and all(_BULLET.fullmatch(x) for x in c["text"].split("\n"))]
        if not marks or len(marks) > CELLS_MAX:
            continue
        s3 = {c["id"]: c for c in t["cells"]}
        top = {c["col"]: c for c in live if c["row"] == 0}
        for c in marks:
            heads = [_tight(X._text(T, i)) for i in (*((s3.get(c["id"]) or {}).get("rowPath") or ()), *((s3.get(c["id"]) or {}).get("colPath") or ()))]
            heads = [h for h in heads if h]
            h = top.get(c["col"])
            if not heads and c["row"] > 0 and h is not None and h["id"] != c["id"]:
                ht = _tight(h.get("text") or "")
                heads = [ht] if ht and len(ht) <= 30 and not _BULLET.fullmatch(ht) else []
            if not heads or any(_RESULT.search(x.replace(" ", "")) for x in heads):
                continue   # 머리 글이 없는 칸 · 결과를 적는 칸(「달성내용」·「달성도」 — 계획서에 없는 내용)
            slots.append({"id": c["id"], "kind": "cell", "label": " › ".join(heads)[:TEXT], "table": t["id"], "ctx": ctx, "was": P._ws(c.get("text") or "")})
    kids = _nodes(T)["kids"]
    for n in T["nodes"]:
        if n["id"] not in T["heads"] or n["id"] in T["cov"] or n.get("flow") != "body" or n["id"] not in T["idx"] or kids.get(n["id"]):
            continue
        live, letter = P._ws(T["idx"][n["id"]].get("text") or ""), P._ws(n.get("letter") or "")   # 지금 문서의 글(그래프의 글은 분석 때 것 — 넣은 뒤에도 라벨뿐으로 보인다)
        m = _LABEL.fullmatch(live[len(letter):].strip() if letter and live.startswith(letter) else live)
        if not m or _RESULT.search(m.group(1)):
            continue
        if any((b.get("text") or "").strip() or b.get("type") in ("table", "image") for b in X._slot(T, n["id"])):
            continue   # 라벨 아래에 이미 내용이 있다
        slots.append({"id": n["id"], "kind": "line", "label": m.group(1), "table": None, "ctx": _node_ctx(T, n["id"]), "was": P._ws(T["idx"][n["id"]].get("text") or ""),
                      "budget": _budget(T, n["id"], guides)})
    return {"tables": tables, "slots": slots}


MISSING = "LLM 답에 이 자리가 없음"   # 물었는데 답에 빠진 자리의 까닭(`missing: true` 와 함께 — ask)


def _has(gaps, kind, key):
    """저장된 답(gaps)에 그 자리의 **답이 있는가** — 「원본 없음」 도 답이다. 물었는데 답에 빠진 자리(`missing`)는 답이 아니다(다음에 다시 묻는다 — spec_작업 ② §22 「구현 계약」 22-1 ⓑ)."""
    rows = (gaps or {}).get(kind) or {}
    return key in rows and not (isinstance(rows[key], dict) and rows[key].get("missing"))


def open_count(found, gaps):
    """아직 안 물은 빈 자리 수 — 저장된 답(gaps — 「원본 없음」 포함)에 없는 것 + 물었는데 답에 빠진 것(`missing` — _has)."""
    return sum(not _has(gaps, "tables", t["key"]) for t in found["tables"]) + sum(not _has(gaps, "slots", s["id"]) for s in found["slots"])


# ---- LLM 에 보낼 자료 ----------------------------------------------------------------------------------------

def _table_brief(S, t, ctx=None):
    cells = S["idx"][t["id"]].get("cells") or ()
    own = t.get("owner") or {}
    heads = list(dict.fromkeys(h for h in (P._ws(X._text(S, c["id"]))[:30] for c in t["cells"] if c.get("role") in MT.HEADS) if h))[:24]
    return {"key": t["id"], "title": P._ws(X._title_of(S, t))[:P.TEXT_MAX], "path": [P._ws(x)[:60] for x in (own.get("path") or ())][-3:], "ctx": ctx or X._ctx(S, t), "heads": heads,
            "shape": {"rows": max((c["row"] + c.get("rowSpan", 1) for c in cells), default=0), "cols": max((c["col"] + c.get("colSpan", 1) for c in cells), default=0)}}


def _table_cands(T, F, tg, src):
    """빈 표의 원본 표 후보 — 맥락이 안 어긋나는 원본 표 가운데 「소속 제목 + 머리 글」 의 글자 조각 겹침이 큰 차례(같은 차년도면 조금 더)."""
    b = tg["brief"]
    mine = _bi(" ".join([b["title"], *b["path"][-1:], *b["heads"]]))
    out = []
    for f, fb, bits in src:
        if not mine or not bits or X._ctx_clash(tg["ctx"], fb["ctx"]):
            continue
        hit = len(mine & bits)
        if hit < TABLE_HIT:
            continue
        score = hit / (len(mine) * len(bits)) ** 0.5 + (0.1 if tg["ctx"]["year"] is not None and tg["ctx"]["year"] == fb["ctx"]["year"] else 0)
        out.append((score, fb))
    return [fb for _, fb in sorted(out, key=lambda x: -x[0])[:TABLE_CANDS]]


def _line_cands(F, slot, src):
    """빈 칸·빈 라벨 줄의 원본 줄 후보 — 라벨 글과 글자 조각이 겹치는 계획서 줄(차년도·기관이 어긋나는 줄은 뺌). 줄이 그 라벨로 시작하면 먼저, 차년도가 같으면 먼저, 제목 꼴의 줄(라벨·짧은 줄)이 먼저."""
    words = [w for w in re.split(r"\s*›\s*", slot["label"]) if w]
    mine = _bi(words[-1]) if words else set()   # 칸은 가장 안쪽 머리 글(「추진목표」)
    key = "".join(_KEEP.findall(words[-1])) if words else ""
    out = []
    for n, bits, head, ctx in src:
        if not mine or X._ctx_clash(slot["ctx"], ctx):
            continue
        hit = len(mine & bits)
        if not hit or (len(mine) > 3 and hit < (len(mine) + 1) // 2):
            continue   # 짧은 라벨(「추진목표」 — 조각 셋)은 조각 하나(「목표」)만 겹쳐도 후보 · 긴 라벨은 절반
        text = P._ws((F["idx"].get(n["id"]) or {}).get("text") or "")
        score = (hit / len(mine) + (1 if key and head.startswith(key) else 0) + (0.5 if slot["ctx"]["year"] is not None and slot["ctx"]["year"] == ctx["year"] else 0)
                 + (0.5 if n.get("role") in ("label", "subtitle") else 0) + (0.3 if len(text) <= 25 else 0))   # 제목 꼴의 줄(라벨·짧은 줄)을 본문 문장보다 먼저
        out.append((score, n, ctx))
    res = []
    for _, n, ctx in sorted(out, key=lambda x: -x[0])[:LINE_CANDS]:
        lines, obj = _lines(content(F, n["id"]))
        res.append({"id": n["id"], "path": _path(F, n["id"]), "text": P._ws((F["idx"].get(n["id"]) or {}).get("text") or "")[:TEXT * 2], "year": ctx["year"],
                    "lines": len(lines), "preview": " / ".join(lines)[:PREVIEW] + (" (표·그림 포함)" if obj else "")})
    return res


def data(T, F, found, skip=None, guides=None, places=None):
    """빈 자리 → (단위마다 보낼 자료 [{title, payload}], 검증에 쓸 것 ctx). skip = 다시 안 물을 자리 {"tables": {…}, "slots": {…}}(저장된 답).
    guides = 목적 양식의 매칭 지침 — 그 표 · 그 본문 자리에 걸린 것을 그 자리의 `guide`(글 목록)로 싣는다(② §5-6: LLM 이 그 자리를 볼 때 그 지침을 같이 본다).
    places = 자리 → 작성 지침(place_guides.resolver — spec_병합 ② §5-11): 그 자리의 `guides`(문서 · 사람이 적은 작성 지침 — `guide` 와 따로)로 싣고 판(guideSig)을 ctx 에 둔다 —
    저장된 답의 판이 지금 판과 다르면 그 자리는 다시 묻는다(판이 없는 옛 답은 지침 없이 받은 답 — 판 "")."""
    skip = skip or {}
    note = lambda texts, kind: [f"「{g['title']}」 {g['text']}"[:LG.TEXT_MAX] for g in LG.match(guides, texts, kind)]  # noqa: E731
    mine = lambda kind, x: (places(kind, x) if places else [])  # noqa: E731
    sigs = {"tables": {t["key"]: PG.sig(mine("table", t["key"])) for t in found["tables"]}, "slots": {s["id"]: PG.sig(mine("block", s["id"])) for s in found["slots"]}}

    def kept(kind, key):   # 저장된 답이 있고 그 답의 지침 판이 지금과 같다 — 다시 안 묻는다(판이 없는 옛 답 = 지침 없이 받은 답: 판 "" — 그 자리에 지금 지침이 있으면 다시 묻는다 · astra 3차)
        old = (skip.get(kind) or {}).get(key)
        if isinstance(old, dict) and old.get("missing"):   # 물었는데 답에 빠졌던 자리 — 답이 있는 자리가 아니다: 다시 묻는다(_has 와 같은 뜻)
            return False
        return old is not None and (places is None or not isinstance(old, dict) or old.get("guideSig", "") == sigs[kind].get(key, ""))
    tabs = [t for t in found["tables"] if not kept("tables", t["key"])]
    slots = [s for s in found["slots"] if not kept("slots", s["id"])]
    fsrc = []
    for f in F["tables"]:
        if f["id"] in F["idx"]:
            fb = _table_brief(F, f)
            fsrc.append((f, fb, _bi(" ".join([fb["title"], *fb["path"][-1:], *fb["heads"]]))))
    nsrc = []
    for n in F["nodes"]:
        b = F["idx"].get(n["id"])
        if n["id"] not in F["heads"] or b is None or _TOC.search(b.get("text") or ""):
            continue
        text = P._ws(b.get("text") or "")
        letter = P._ws(n.get("letter") or "")
        rest = text[len(letter):] if letter and text.startswith(letter) else text
        nsrc.append((n, _bi(text[:40]), "".join(_KEEP.findall(rest))[:20], _node_ctx(F, n["id"])))
    cur = T["values"].get("current") or 1
    units, ctx = {}, {"tables": {}, "slots": {}, "F": F, "T": T}
    chapter = lambda path: (path[0] if path else "(표지·요약문)")  # noqa: E731

    def unit(key):
        u = units.setdefault(key, [{"current": cur, "tables": [], "slots": []}])
        if len(u[-1]["tables"]) + len(u[-1]["slots"]) >= UNIT_MAX:
            u.append({"current": cur, "tables": [], "slots": []})
        return u[-1]
    home, tby = {}, {t["id"]: t for t in T["tables"]}
    for tg in tabs:
        tg["brief"] = _table_brief(T, tg["t"], tg["ctx"])
        cands = _table_cands(T, F, tg, fsrc)
        own = tg["t"].get("owner") or {}
        ch = chapter([P._ws(x)[:60] for x in (own.get("path") or ())] or [tg["brief"]["title"]])
        home[tg["key"]] = ch
        ctx["tables"][tg["key"]] = {"ctx": tg["ctx"], "cands": {c["key"]: c["ctx"] for c in cands}, "guideSig": sigs["tables"].get(tg["key"], "")}
        if cands:
            g = note([tg["brief"]["title"], P._ws(own.get("text") or ""), *(P._ws(x) for x in (own.get("path") or ())[-2:])], "table")
            gs = mine("table", tg["key"])
            unit(ch)["tables"].append({**tg["brief"], **({"guide": g} if g else {}), **({"guides": gs} if gs else {}), "candidates": cands})
    for s in slots:
        cands = _line_cands(F, s, nsrc)
        own = (tby.get(s["table"]) or {}).get("owner") or {}
        path = _path(T, s["id"]) if s["kind"] == "line" else [x for x in [*[P._ws(x)[:60] for x in (own.get("path") or ())][-3:], P._ws(own.get("text") or "")[:P.TEXT_MAX]] if x]
        ch = home.get(s["table"]) or chapter([_line(p)[:60] for p in _ups(T, s["id"])[::-1]] if s["kind"] == "line" else path)
        ctx["slots"][s["id"]] = {**s, "cands": {c["id"]: c for c in cands}, "guideSig": sigs["slots"].get(s["id"], "")}
        if cands:
            g = note([_live(T, p) for p in _ups(T, s["id"])], "body") if s["kind"] == "line" else note([P._ws(own.get("text") or ""), *(P._ws(x) for x in (own.get("path") or ())[-2:])], None)
            gs = mine("block", s["id"])
            unit(ch)["slots"].append({"id": s["id"], "kind": s["kind"], "label": s["label"], "path": path, "table": s["table"], "ctx": s["ctx"],
                                      **({"budget": s["budget"]} if s.get("budget") else {}), **({"guide": g} if g else {}), **({"guides": gs} if gs else {}), "candidates": cands})
    out = [{"title": k, "payload": p} for k, ps in units.items() for p in ps if p["tables"] or p["slots"]]
    for u in out:   # 한 호출의 작성 지침 합을 자른다(② §5-11)
        PG.budget([*u["payload"]["tables"], *u["payload"]["slots"]])
    return out, ctx


def guide_part(g=None):
    g = merge_guides.get(GUIDE) if g is None else g
    return merge_guides.part(g) or f"\n\n## 판단 지침 — 기본\n\n{FALLBACK_GUIDE}"


def links_part(links):
    return f"\n\n## 양식 정보 — 자리 연결\n{LINK_NOTE}\n\n{links.strip()}" if (links or "").strip() else ""


def prompt(payload, job=None, links="", guide=None):
    """프롬프트 글 = 계약(+ 자리에 작성 지침 `guides` 가 있으면 그 한 줄 — spec_병합 ② §5-11) + 판단 지침 + 할 일 프롬프트 + 자리 연결 절 + 자료(JSON)."""
    note = PG.CONTRACT_LINE if any(x.get("guides") for k in ("tables", "slots") for x in payload.get(k) or ()) else ""
    return CONTRACT + note + guide_part(guide) + job_prompts.part(job) + links_part(links) + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parts(job=None, links="", guide=None):
    """화면 「지침」 보기에 싣는 글들(자료 빼고) — merge_table_map.parts 와 같은 꼴."""
    g = merge_guides.get(GUIDE) if guide is None else guide
    out = [{"key": "contract", "title": "계약 — 역할 · 자료 설명 · 답의 꼴", "text": CONTRACT, "source": "app/merge_gaps.py",
            "note": "코드에 든 글입니다(답을 검증하는 코드와 한 몸) — 판단 기준은 아래 지침에 있습니다"}]
    if g and merge_guides.body(g):
        out.append({"key": "guide", "title": f"판단 지침 — {g['title']}", "text": merge_guides.body(g), "source": g["path"], "note": "이 파일을 고치면 다음 실행부터 적용됩니다"})
    else:
        out.append({"key": "guide", "title": "판단 지침 — (지침 파일 없음: 기본 기준)", "text": FALLBACK_GUIDE.strip(), "source": "app/merge_gaps.py", "note": "app/merge_guides_default/gaps.md 가 없어 기본 기준만 보냅니다"})
    if job and job_prompts.part(job):
        out.append({"key": "job", "title": f"할 일 프롬프트 — {job['name']}", "text": job_prompts.body(job.get("text")), "source": job.get("path") or "", "note": "이 작업의 전제 — 먼저 따릅니다"})
    if (links or "").strip():
        out.append({"key": "form", "title": "양식 정보 — 자리 연결", "text": links.strip(), "source": "", "note": "목적 문서 양식의 「자리 연결」 절(연결 코멘트)"})
    return out


# ---- 답 검증 -------------------------------------------------------------------------------------------------

def _take_text(F, slot, frm, take):
    """고른 원본 줄에서 넣을 글 → (줄 목록, 거절 까닭 | None). 지금 원본 문서에서 읽는다."""
    if frm not in F["idx"]:
        return [], "noSource"
    if take == "line":
        text = _own(F, frm, slot["label"] if slot["kind"] == "line" else "")
        return ([text], None) if len(_KEEP.findall(text)) >= OWN_MIN else ([], "noSource")   # 제목뿐인 줄(「□ 배경」)은 내용이 아니다
    lines, obj = _lines(content(F, frm))
    if obj:
        return [], "object"
    if not lines:
        return [], "noSource"
    cell = slot["kind"] == "cell"   # 칸은 기관마다의 줄이 모이는 자리라 한도가 넓다(CELL_*)
    if len(lines) > (CELL_LINES_MAX if cell else LINES_MAX) or sum(map(len, lines)) > (CELL_CHARS_MAX if cell else CHARS_MAX):
        return [], "long"
    return lines, None


def _take_blocks(F, slot, frm):
    """빈 라벨 줄에 옮길 **내용 블록**(고른 원본 줄 아래 — 라벨 줄 뒤에 원본 모양 그대로 복사) → (블록 목록, 안 넣은 블록 수, 거절 까닭 | None). 지금 원본 문서에서 읽는다.
    줄 한도(`budget` — 「N page 이내」 자리)가 있으면 그 안의 **앞부분만**(글과 글 상자 — 표 · 그림은 건너뛴다 · 끝에 걸린 제목 줄 · 빈 줄은 뗀다), 없으면 전처럼 통째로만 — 표 · 그림이 들었거나 길면 안 넣는다."""
    if frm not in F["idx"]:
        return [], 0, "noSource"
    blocks = []
    for b in content(F, frm):
        if MF._placeholder(b) or (b.get("type") == "paragraph" and (b.get("text") or "").strip() and _BULLET.fullmatch(b["text"])):
            continue   # 글머리만 있는 자리표시 줄(원본 양식의 빈 줄 「o」·「-」·「⋅」)은 내용이 아니다
        if MF._blank(b) and (not blocks or MF._blank(blocks[-1])):
            continue   # 맨 앞 · 잇단 빈 줄
        blocks.append(b)
    while blocks and MF._blank(blocks[-1]):
        blocks.pop()
    if not blocks:
        return [], 0, "noSource"
    budget = slot.get("budget")
    if not budget:
        lines, obj = _lines(blocks)
        return ([], 0, "object") if obj else ([], 0, "long") if len(lines) > LINES_MAX or sum(map(len, lines)) > CHARS_MAX else (blocks, 0, None)
    # 줄 한도가 있는 자리(「N page 이내 요약」) — **글과 글 상자(1칸 표)만** 앞에서부터 한도까지. 표 · 그림은 요약 자리에 넣지 않는다(그림 하나가 반 쪽이다 — 건너뛰고 그 뒤의 글을 잇는다).
    out, used, cut = [], 0, False
    for b in blocks:
        if b.get("type") == "image" or (b.get("type") == "table" and len(b.get("cells") or ()) != 1):
            continue
        n = _cost(b)
        if used + n > budget:
            cut = True
            break
        if MF._blank(b) and (not out or MF._blank(out[-1])):
            continue   # 표 · 그림을 건너뛴 자리에 빈 줄이 겹치지 않게
        out.append(b)
        used += n
    kids = _nodes(F)["kids"]
    title = lambda b: b["id"] in F["heads"] and (bool(kids.get(b["id"])) or len(P._ws(b.get("text") or "")) <= TITLE_LEN)  # noqa: E731 — 내용을 거느린 제목 줄(글머리 문단은 그래프의 줄이어도 내용이다)
    while out and (MF._blank(out[-1]) or (cut and title(out[-1]))):   # 잘린 끝에 내용 없는 제목 줄 · 빈 줄이 남지 않게
        out.pop()
    full = lambda seq: sum(1 for b in seq if not MF._blank(b))  # noqa: E731 — 빈 줄은 세지 않는다(안 넣은 「블록 수」 는 글 · 표 · 그림의 수)
    return (out, full(blocks) - full(out), None) if out else ([], full(blocks), "long")


NOTE = {"occupied": "목적 자리에 이미 글이 있음", "noSource": "원본 줄에 옮길 글이 없음", "long": "내용이 길다(그 자리의 한도를 넘음) — 기관이 작성", "object": "내용에 표·그림이 들어 있음 — 기관이 작성",
        "year": "차년도가 다른 내용", "org": "기관이 다른 내용"}


def check(ctx, answer):
    """LLM 답 하나(한 단위)를 보낸 자료에 대고 검증 → ({"tables": {…}, "slots": {…}}, rejected[{to, why}]). 입력에 있는 key·id 만 · 자리마다 한 번 · 차년도·기관이 어긋나면 거절."""
    out, rejected = {"tables": {}, "slots": {}}, []
    ans = answer if isinstance(answer, dict) else {}
    for a in ans.get("tables") or ():
        to, frm = a.get("to"), a.get("from") or ""
        c = ctx["tables"].get(to)
        if c is None or to in out["tables"]:
            rejected.append({"to": to, "why": "보낸 빈 표가 아니거나 두 번 답함"})
            continue
        if frm and frm not in c["cands"]:
            rejected.append({"to": to, "why": f"후보에 없는 원본 표 {frm}"})
            continue
        if frm and (bad := X._ctx_clash(c["ctx"], c["cands"][frm])):
            rejected.append({"to": to, "why": NOTE[bad]})
            continue
        out["tables"][to] = {"from": frm or None, "reason": str(a.get("reason") or "")[:300]}
    whole = {t for t, v in out["tables"].items() if v["from"]}
    for a in ans.get("slots") or ():
        to, frm, take = a.get("to"), a.get("from") or "", a.get("take") or "line"
        s = ctx["slots"].get(to)
        if s is None or to in out["slots"]:
            rejected.append({"to": to, "why": "보낸 빈 자리가 아니거나 두 번 답함"})
            continue
        base = {"kind": s["kind"], "was": s["was"], "label": s["label"], "table": s["table"], "reason": str(a.get("reason") or "")[:300]}
        if not frm or s["table"] in whole:   # 원본 없음 · 그 표를 표째로 옮김
            out["slots"][to] = {**base, "from": None, "take": None}
            continue
        if frm not in s["cands"] or take not in ("line", "content"):
            rejected.append({"to": to, "why": f"후보에 없는 원본 줄이거나 받을 수 없는 take({take})"})
            continue
        cy = s["cands"][frm].get("year")
        if s["ctx"]["year"] is not None and cy is not None and s["ctx"]["year"] != cy:
            rejected.append({"to": to, "why": NOTE["year"]})
            continue
        below = s["kind"] == "line" and take == "content"   # 라벨 줄 ← 제목 줄 아래의 내용(블록째 — 줄 한도 안에서)
        why = _take_blocks(ctx["F"], s, frm)[2] if below else _take_text(ctx["F"], s, frm, take)[1]
        if why:
            rejected.append({"to": to, "why": NOTE[why]})
            out["slots"][to] = {**base, "from": None, "take": None, "reason": f"{NOTE[why]} — {base['reason']}"[:300]}
            continue
        out["slots"][to] = {**base, "from": frm, "take": take, **({"budget": s["budget"]} if s.get("budget") else {})}
    return out, rejected


def prepare(T, F, fixed_plan, saved=None, again=False, orig=None, guides=None, skip=(), places=None):
    """물을 것을 만든다(문서를 읽는 곳 — 세션 잠금 안에서 부른다) → {"found", "units", "ctx"}. 그 뒤 `ask` 는 읽어 둔 것만 쓴다(잠금 밖 — LLM 호출이 수십 초).
    guides = 목적 양식의 매칭 지침(link_guides.entries — 자리마다의 `guide` · 쪽 한도) · places = 자리마다의 작성 지침(place_guides.resolver — data 의 `guides` · 판)."""
    found = targets(T, F, fixed_plan, orig, guides, skip)
    units, ctx = data(T, F, found, None if again else saved, guides, places)
    return {"found": found, "units": units, "ctx": ctx}


def review(T, F, fixed_plan, saved=None, job=None, links="", again=False, orig=None, guides=None, **kw):
    """빈 자리 검토 한 번(모듈 설명) = prepare + ask."""
    return ask(prepare(T, F, fixed_plan, saved, again, orig, guides), job, links, **kw)


def ask(prep, job=None, links="", model=MODEL, effort="medium", timeout=300.0):
    """prepare 가 만든 것을 묻고 답을 검증 → {"tables", "slots", "rejected", "units"[{title, targets, error, prompt, answer, call}], "asked", "found"{tables, slots}, "guide", "job"}.
    답이 없는 자리는 셋으로 가른다(spec_작업 ② §22 「구현 계약」 22-1 ⓑ):
    - 후보가 하나도 없어 **안 물은** 빈 자리 → 「원본 없음」(다음에 다시 세지 않게 — 전과 같다)
    - 물었고 LLM 이 그 자리를 답에 적었는데 검증이 거절한 것 → 전처럼 「원본 없음」(답은 왔다 — 못 정함)
    - 물었는데 **답에 그 자리가 없는** 것 → `missing: true` · 까닭 `MISSING`(「원본 없음」 이 아니다 — 저장하는 쪽이 앞 답을 갈지 않고, 다음 검토가 다시 묻는다)
    호출이 실패한 단위의 자리는 결과에 없다(안 물은 것으로 — 저장하는 쪽이 앞 답을 그대로 둔다)."""
    found, units, ctx = prep["found"], prep["units"], prep["ctx"]
    g = merge_guides.get(GUIDE)
    jobs = [{"schema": SCHEMA, "content": prompt(u["payload"], job, links, g), "what": f"merge-gaps-{i + 1}", "timeout": timeout, "effort": effort, "model": model} for i, u in enumerate(units)]
    res = llm.ask_all(jobs) if jobs else []
    out = {"tables": {}, "slots": {}, "rejected": [], "units": [], "asked": len(jobs), "found": {"tables": len(found["tables"]), "slots": len(found["slots"])},
           "guide": merge_guides.brief(g), "job": {k: job[k] for k in ("job", "name", "sha1") if k in job} if job and job_prompts.part(job) else None}
    answered, named = {"tables": set(), "slots": set()}, {"tables": set(), "slots": set()}   # answered = 답이 온 단위에 실어 보낸 자리 · named = LLM 이 답에 적은 자리(검증이 거절한 것 포함)
    for i, (u, j, r) in enumerate(zip(units, jobs, res)):
        call = {k: r.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error", "retried")}
        sent = {"tables": {t["key"] for t in u["payload"]["tables"]}, "slots": {s["id"] for s in u["payload"]["slots"]}}
        out["units"].append({"n": i, "title": u["title"], "pages": None, "targets": len(sent["tables"]) + len(sent["slots"]), "tables": len(sent["tables"]), "error": call.get("error"),
                             "prompt": j["content"], "answer": r.get("data"), "call": call})
        if r.get("data") is None:
            continue   # 그 단위의 호출이 실패 — 그 자리는 안 물은 것으로 둔다(다음에 다시)
        got, rejected = check({**ctx, "tables": {k: v for k, v in ctx["tables"].items() if k in sent["tables"]}, "slots": {k: v for k, v in ctx["slots"].items() if k in sent["slots"]}}, r["data"])
        out["tables"].update(got["tables"])
        out["slots"].update(got["slots"])
        out["rejected"] += rejected
        ans = r["data"] if isinstance(r["data"], dict) else {}
        for kind in ("tables", "slots"):
            answered[kind] |= sent[kind]
            named[kind] |= {a.get("to") for a in ans.get(kind) or () if isinstance(a, dict)}

    def rest(kind, k, cands, none):   # 답이 없는 자리 하나 → 적을 것 | None(호출이 실패한 단위 — 안 적는다)
        if not cands:   # 후보가 없어 안 물음
            return {"from": None, "reason": none}
        if k in named[kind]:   # 답에 적혔는데 검증이 거절(rejected) — 전처럼 「원본 없음」
            return {"from": None, "reason": ""}
        if k in answered[kind]:   # 물었는데 답에 빠짐 — 「원본 없음」 이 아니다
            return {"from": None, "missing": True, "reason": MISSING}
        return None
    for k, c in ctx["tables"].items():
        if k not in out["tables"] and (row := rest("tables", k, c["cands"], "원본 표 후보가 없음")) is not None:
            out["tables"][k] = row
    for k, s in ctx["slots"].items():
        if k not in out["slots"] and (row := rest("slots", k, s["cands"], "원본 줄 후보가 없음")) is not None:
            out["slots"][k] = {"kind": s["kind"], "was": s["was"], "label": s["label"], "table": s["table"], "take": None, **row}
    return out


# ---- 넣기 계획 · 반영 ----------------------------------------------------------------------------------------

def _to_text(slot, lines):
    """목적 자리에 쓸 글 — 칸은 줄마다 한 문단, 라벨 줄은 「- (정의)」 뒤에 한 문단을 잇는다."""
    return "\n".join(lines) if slot["kind"] == "cell" else f"{slot['was']} {lines[0]}"


def plan(T, F, gaps):
    """넣기 계획(모듈 설명) — 문서를 안 고친다. gaps = merge.json `gaps`. 빈 표 ← 원본 표는 표 짝(merge.json tables)이 넣으므로 여기 없다.
    → {"cells": [{to, text, from}], "lines": [{to, text, from}], "items": [{to, kind, label, from, fromText, lines, skip, detail}], "skipped", "counts", "todo"}."""
    out = {"cells": [], "lines": [], "blocks": [], "items": [], "skipped": []}
    for sid, g in ((gaps or {}).get("slots") or {}).items():
        if not isinstance(g, dict) or not g.get("from"):
            continue
        slot = {"kind": g.get("kind"), "label": g.get("label") or "", "was": g.get("was") or "", "budget": g.get("budget")}
        row = {"to": sid, "kind": slot["kind"], "label": slot["label"], "from": g["from"], "fromText": P._ws((F["idx"].get(g["from"]) or {}).get("text") or "")[:TEXT], "lines": 0, "skip": None, "detail": ""}
        out["items"].append(row)
        b = T["idx"].get(sid)
        if slot["kind"] == "line" and g.get("take") == "content":   # 라벨 줄 ← 제목 줄 아래의 내용: 블록째 라벨 줄 뒤에(모듈 설명 「라벨 줄 아래의 내용 · 쪽 한도」)
            blocks, left, why = _take_blocks(F, slot, g["from"])
            place = X._slot(T, sid) if b is not None else []
            there = [x for x in place if not (MF._blank(x) or MF._placeholder(x))]
            if b is None:
                why, row["detail"] = "occupied", "목적 자리가 지금 문서에 없음"
            elif not why and there:   # 라벨 아래에 이미 내용 — 넣을 내용의 첫 블록과 같으면 넣은 것, 다르면 사람 글
                if _sig(there[0]) == _sig(blocks[0]):
                    row["skip"], row["detail"] = "done", "이미 넣음"
                    continue
                why = "occupied"
            elif not why and P._ws(b.get("text") or "") != slot["was"]:
                why = "occupied"
            if why:
                row["skip"], row["detail"] = why, row["detail"] or NOTE[why]
                out["skipped"].append({"to": sid, "why": why, "detail": row["detail"]})
                continue
            row["lines"] = len(blocks)
            row["detail"] = f"줄 한도({slot['budget']}줄) 안의 앞부분만(글 · 글 상자) — 표 · 그림과 뒤 {left}개 블록은 넣지 않음(기관이 작성)" if left else ""
            out["blocks"].append({"to": sid, "src": [x["id"] for x in blocks], "from": g["from"], "was": slot["was"], "left": left, "placeholders": [x["id"] for x in place if MF._placeholder(x)]})
            continue
        lines, why = _take_text(F, slot, g["from"], g.get("take") or "line")
        if b is None:
            why = "occupied"
            row["detail"] = "목적 자리가 지금 문서에 없음"
        if not why:
            cur, new = P._ws(b.get("text") or ""), _to_text(slot, lines)
            if cur == P._ws(new):
                row["skip"], row["detail"] = "done", "이미 넣음"
                continue
            if not (_blank(b.get("text") or "") if slot["kind"] == "cell" else cur == slot["was"]):
                why = "occupied"
        if why:
            row["skip"], row["detail"] = why, row["detail"] or NOTE[why]
            out["skipped"].append({"to": sid, "why": why, "detail": row["detail"]})
            continue
        row["lines"] = len(lines)
        out["cells" if slot["kind"] == "cell" else "lines"].append({"to": sid, "text": new, "from": g["from"], "was": slot["was"]})
    out["counts"] = {"cells": len(out["cells"]), "lines": len(out["lines"]), "blocks": len(out["blocks"]), "tables": sum(1 for v in ((gaps or {}).get("tables") or {}).values() if isinstance(v, dict) and v.get("from")),
                     "skipped": {k: sum(s["why"] == k for s in out["skipped"]) for k in WHY}}
    out["todo"] = len(out["cells"]) + len(out["lines"]) + len(out["blocks"])
    return out


def apply(to_doc, plan, from_doc=None):
    """계획을 목적 문서에(모듈 설명) → {"cells", "lines", "blocks"(내용을 넣은 라벨 줄 수), "inserted"{라벨 줄 id: [새 블록 id]}, "skipped": [{to, why, detail}], "dropped", "fitted"}.
    자리는 **지금** 비어 있을 때만 쓴다(계획 뒤 사람이 쓴 글을 덮지 않음). from_doc = 원본 문서(라벨 줄 아래의 내용을 복사할 때만 쓴다 — 읽기만)."""
    done, skipped, inserted, dropped = {"cells": 0, "lines": 0, "blocks": 0}, [], {}, []
    below = list((plan or {}).get("blocks") or ())
    todo = [("cells", c) for c in (plan or {}).get("cells") or ()] + [("lines", c) for c in (plan or {}).get("lines") or ()]
    idx = structure.index_blocks(to_doc.blocks()) if todo or below else {}
    for c in below:   # 라벨 줄 뒤에 원본의 내용 블록을 원본 차례로 복사(merge_fill 과 같은 길 — 글 · 표 · 그림이 원본 모양 그대로)
        b = idx.get(c["to"])
        if b is None or from_doc is None or P._ws(b.get("text") or "") != c["was"]:
            skipped.append({"to": c["to"], "why": "occupied", "detail": "원본 문서를 못 읽음" if b is not None and from_doc is None else "계획 뒤 목적 자리의 글이 바뀜" if b is not None else "목적 자리가 지금 문서에 없음"})
            continue
        try:
            new = to_doc.insert_after(c["to"], [{"kind": "copy", "srcId": s} for s in c["src"]], src=from_doc)
        except (KeyError, ValueError) as x:
            skipped.append({"to": c["to"], "why": "occupied", "detail": str(x)})
            continue
        dropped += [{"item": c["to"], "src": s, "what": w} for s in c["src"] for w in MF._dropped(from_doc, s)]
        for pid in c.get("placeholders") or ():
            to_doc.delete_blocks(pid, pid)
        inserted[c["to"]] = new
        done["blocks"] += 1
    for kind, c in todo:
        b = idx.get(c["to"])
        cur = (b or {}).get("text") or ""
        if b is None or not (_blank(cur) if kind == "cells" else P._ws(cur) == c["was"]):
            skipped.append({"to": c["to"], "why": "occupied", "detail": "계획 뒤 목적 자리에 글이 생김" if b is not None else "목적 자리가 지금 문서에 없음"})
            continue
        try:
            to_doc.set_text(c["to"], c["text"])
            done[kind] += 1
        except (KeyError, ValueError) as x:
            skipped.append({"to": c["to"], "why": "occupied", "detail": str(x)})
    fitted = sum(to_doc.fit_image(i) for ids in inserted.values() for i in ids)   # 넣은 그림이 본문 폭보다 넓으면 그 폭으로(② §5-2)
    return {**done, "inserted": inserted, "skipped": skipped, "dropped": dropped, "fitted": fitted}
