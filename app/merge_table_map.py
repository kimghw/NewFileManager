"""병합 — 표 대응 에이전트(spec_병합 ② §5-3, 2026-11-12 사용자 「그 테이블을 저테이블에 매핑해주는 에이전트를 하나 호출해서 넣도록 해줘. 폼이 같거나 반복적이면 함께 해도 되는데
이렇게 다른 경우는」 · astra 설계 협의 `artifacts/table_map_astra_2026-11-12/`): 같은 내용을 적는 표인데 두 서식의 행·열 구성이 달라 머리 경로(merge_fixed·merge_tables)로는 칸을 못 맞춘 표를
**표마다 LLM 한 번**으로 맞춘다. LLM 은 **행 짝·열 짝만** 고르고(글·값을 쓰지 않는다), 칸마다 넣을지는 스크립트가 지금 격자를 다시 읽어 정한다 — 좌표만 믿으면 다른 차년도·예시 실적이 들어간다.

- `targets(tabs_plan, fixed_plan)` = 대응이 필요한 표 [(목적 표 id, 원본 표 id)] — 원본 표는 정해졌는데 스크립트가 한 칸도 못 맞춘 표(같은 이름 자리의 `shape` · 표 묶음 짝의 칸 0 + `shape`).
- `data(T, F, to_side, from_side, tid, fid)` = LLM 에 보낼 자료 + 검증에 쓸 것(`ctx`) — 목적 표의 격자·맥락·표시 목록·표 뒤 줄, 원본 후보 표(이어진 표 + 같은 소속 제목 아래의 다른 표)의 격자.
- `ask(payload, …)` · `check(ctx, answer)` → 저장할 대응 `{from, records, grow, fields, mark, reason, rejected, top, sig}` | None. 꼴(좌표·겹침)과 **열 짝의 뜻**(수 머리 · 차년도 · 단위 · 실적 열)을 격자에서 다시 읽어 거른다.
- `plan(T, F, maps, orig=None)` = 넣기 계획(문서를 안 고침) — 대응마다 항목(records)·열 짝(fields)을 칸 짝으로 풀어 **지금 글**에 대고 정한다: 빈 칸·틀·자리표시 이름(순번·「···」)·서식 예시일 때만 쓰고,
  한 항목에 사람이 쓴 글이 하나라도 있으면 그 항목은 통째로 안 넣는다. 표시(일정 막대)는 원본 칸의 채움 → 목적 서식의 선(경계의 지금 선이 기대와 다를 때만 일).
  → {"tables", "cells", "clears", "lines", "rows", "skipped", "counts", "todo", "owned"(대응이 맡은 표 id)}.
- `apply(to_doc, from_doc, plan)` = 계획을 목적 문서에 → {"filled", "shaped", "lines", "rowsAdded", "cleared", "skipped", "grown"{표 id: [[늘린 행 …] …]}}.
다시 계획하면: 칸은 글이 같고 선은 기대와 같아 일 없음 · 늘린 묶음은 반영 뒤 대응의 records 로 옮겨 적는다(merge_api). 표의 행·열 수·병합·열 머리(`sig`)가 달라지면 그 대응은 낡음(안 쓴다).
서식 예시(목적 서식의 예시 행)를 덮는 조건 = `orig`(등록된 빈 양식으로 올린 원본의 칸 — merge_api._orig) 가 있고 그 칸의 지금 글·선이 원본 그대로일 때(아니면 사람 글로 본다)."""
import hashlib
import json
import re
from collections import Counter, defaultdict

from app import heading_calc as HC
from app import job_prompts, llm, merge_guides
from app import merge_fixed as X
from app import merge_pairs as P
from app import merge_tables as MT

S_, I_, B_ = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}


def _obj(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def _arr(item):
    return {"type": "array", "items": item}


SCHEMA = _obj({"from": S_, "records": _arr(_obj({"to": _arr(I_), "from": _arr(I_), "example": B_})), "grow": _arr(_obj({"like": _arr(I_), "to": _arr(I_), "from": _arr(I_)})),
               "fields": _arr(_obj({"to": I_, "from": I_, "kind": S_})), "mark": S_, "reason": S_})

CONTRACT = """당신은 국가R&D 사업계획서(연구개발계획서 — **원본 문서**)의 표 내용을 연차보고서(**목적 문서**)의 표에 옮길 때, 서식이 서로 달라 스크립트가 칸을 못 맞춘 표 한 쌍에서
**어느 행이 어느 행과, 어느 열이 어느 열과 같은 것인지** 고르는 검토자입니다. 글이나 값을 쓰지 않습니다 — 행 짝과 열 짝만 고르면 스크립트가 그 칸들의 원본 글을 목적 칸에 옮깁니다.

### 자료
target = 목적 표, sources = 원본 후보 표들(paired = 앞 단계가 이어 둔 표 · 나머지는 같은 절에 있는 다른 표 — 실제로 옮길 표 **하나**를 고릅니다). 표마다:
key · title(소속 제목) · path(그 위 제목들) · ctx(year = 어느 차년도의 표인지 · org = 어느 기관의 표인지 — null 이면 모름/전체) · top(자료 행이 시작하는 행 번호 — 그 위는 머리 행) · grid.
grid = 행마다 한 줄 「r행번호: 칸 | 칸 | …」. 칸 = 「c열번호」(+ 「-끝열」 = 열 병합 · 「↓행수」 = 아래로 행 병합) + 역할(H 머리·이름 칸 · F 값 칸 · T 표 제목) + 글 「…」 + 표시.
「c2..c15 F」 처럼 「..」 으로 묶은 것은 그 열들이 **각각** 한 칸(같은 꼴의 빈 칸)이라는 뜻입니다. 행·열 번호는 0부터이고 병합 칸은 왼쪽 위 좌표 한 번만 적힙니다.
표시(자료 행에만): 「■」 = 칸 채움(일정 막대처럼 칠한 칸) · 「▔종류」·「▁종류」 = 칸 위·아래 가장자리의 특수 선(DASH·DASH_DOT …).
target.marks = 목적 서식이 일정·진행을 나타내는 표시 목록 [{name(범례의 이름 — 「당초계획」·「개발실적」), line(선 종류)}] — 비어 있으면 목적 표는 표시를 쓰지 않습니다.
target.after = 표 바로 뒤 줄(주석·범례). target.current = 목적 문서의 당해 차년도(「해당연도」 = 이 차년도 · 「다음 연도」 = 그 다음).

### 답
- from = 옮길 원본 표의 key(sources 가운데 하나). 옮길 표가 없으면 "" 이고 나머지는 빈 목록.
- records = 항목 짝 [{to: [목적 행 번호…], from: [원본 행 번호…], example}] — **항목 하나**끼리. to 와 from 의 행 수는 같아야 하고 차례대로 한 행씩 대응합니다(두 표에서 항목이 같은 수의 행이면 그 행들 전부,
  목적 항목이 「목표」·「실적」 두 행이고 원본 항목이 한 행이면 to 는 목표 행 하나). 여러 행에 걸친 이름·단위 칸은 그 항목의 행 가운데 하나만 짝이어도 함께 옮겨집니다.
  example = 그 목적 행들에 **서식이 보기로 적어 둔 예시 내용**이 들어 있어 실제 내용으로 바꿔야 하면 true(이름·값·표시가 다 채워져 있는 예시 항목). 이름만 박혀 있고 값 칸이 빈 항목(서식의 고정 항목)은 false.
- grow = 목적 표에 자리가 모자라 **행을 늘려야 하는** 항목 [{like: [본뜰 목적 행 번호…], to: [그 가운데 원본 행과 짝이 되는 행 번호…], from: [원본 행 번호…]}] — like 는 목적 표의 **빈 항목 하나**(그 항목의 행 전부, 이어진 행들)이고,
  스크립트가 그 묶음을 바로 아래에 본떠 넣은 뒤 본뜬 묶음에서 to 자리의 행에 from 을 넣습니다(to 와 from 의 행 수는 같아야 합니다 — 항목의 모든 행이 짝이면 to 는 like 와 같습니다. 「목표」·「실적」 두 행 가운데 목표 행만 짝이면 to 는 그 한 행).
  빈 자리가 남아 있으면 records 를 먼저 쓰고, 남는 원본 항목만 grow 에 적습니다. 본뜰 빈 항목이 없으면 적지 않습니다.
- fields = 열 짝 [{to: 목적 열 번호, from: 원본 열 번호, kind}] — kind 는 "text"(그 열의 칸 글을 옮김 — 이름·단위·수) 또는 "mark"(그 열은 일정 칸 — 원본 칸의 표시가 있는지만 옮김).
  병합된 머리 아래의 열은 열마다 따로 적습니다(한 달이 두 열이면 두 줄). 목적 열은 한 번씩만, 원본 열은 여러 목적 열이 읽어도 됩니다.
- mark = kind "mark" 열이 있으면 target.marks 의 name 가운데 **원본의 표시가 뜻하는 것**(계획서의 일정은 계획입니다), 없으면 "".
- reason = 그렇게 본 근거 두세 문장(한국어 — 어느 머리·어느 항목·어느 차년도를 보고).

### 지켜야 할 것
- 입력 격자에 있는 행·열 번호만 씁니다. 머리 행(top 위)은 records 에 넣지 않습니다.
- **뜻이 같은 열만** 잇습니다: 월·연도처럼 머리가 수인 열은 같은 수끼리(「4」 ↔ 「4」), 차년도는 같은 차년도끼리, 단위가 다른 열은 잇지 않습니다.
- 계획서에 없는 내용의 자리(「실적」·「달성도」 열과 행)는 잇지 않습니다 — 비워 둡니다. 합계·비율처럼 계산해서 적는 칸도 잇지 않아도 됩니다.
- 목적 항목에 서식이 정해 둔 이름이 있으면(예시가 아닌 고정 항목) 원본에서 **같은 이름의 항목**하고만 잇습니다. 이름이 비었거나 순번(「1.」)·「···」 뿐인 항목은 원본 차례대로 잇습니다.
- 확신이 없으면 그 항목·그 열을 빼십시오. 틀린 짝은 엉뚱한 값을 문서에 넣게 되고, 빼면 사람이 채웁니다."""

FALLBACK_GUIDE = """

## 판단 기준(지침 파일 없음 — 기본)
- 목적 표가 특정 차년도의 표면 원본에서도 그 차년도의 표·열만 고릅니다. 기관은 이름으로 가립니다.
- 원본의 표시(칠한 칸)는 계획입니다 — 목적의 계획 쪽 표시로만 옮기고 실적 쪽은 비웁니다."""

GUIDE = "table_map"   # merge_guides 의 지침 이름(app/merge_guides_default/table_map.md)
MODEL = "claude-opus-5-5"
LINK_NOTE = ("아래는 목적 문서 양식의 **양식 정보 「자리 연결」 절**입니다 — 사용자가 「어느 표·단락을 어디와 이을지」 를 적어 둔 것(연결 코멘트 포함). 이 표에 대한 줄이 있으면 위 판단 기준보다 먼저 따릅니다. "
             "답의 꼴과 「입력에 있는 번호만」 은 위 계약 그대로입니다.")

TEXT, AFTER_MAX, AFTER_LEN, SIBLINGS_MAX, GRID_CELLS_MAX = 60, 6, 120, 4, 4000
ROLE = {"field": "F", "rowhead": "H", "colhead": "H", "corner": "H", "title": "T"}
HEADISH = ("rowhead", "colhead", "corner")
OFF = {"type": "NONE", "width": "0.1 mm", "color": "#000000"}
WHY = ("occupied", "name", "calc", "shape", "stale", "org", "example")
_RESULT = re.compile(r"^(?:개발|추진)?실적$|^달성(?:도|률|율)")       # 계획서에 없는 내용의 머리(빈칸·괄호·기호 뗀 글) — 「실적」·「달성도(%)」. 「사업화실적」 같은 지표 이름은 아니다
_ORD = re.compile(r"^\(?(\d{1,3})[.)]?$")                              # 순번뿐인 이름 칸 「1.」·「(2)」·「3」
_ORD_LEAD = re.compile(r"^\(?(\d{1,3})[.)]")                           # 원본 이름의 앞 순번 「1. 선내 데이터 …」
_ORD_N = re.compile(r"^\(?[nN][.)]?$")                                 # 서식의 「n.」 — 「몇 번째든」 의 순번 자리(마지막 항목 줄)
_FOOT = re.compile(r"(?<![(\d])\d{1,2}\s*[)」]\s*$")                    # 머리 글 끝의 각주 번호 「중앙행정기관명2)」 · 「표준구분1」」 — 「항목(1)」 의 괄호 번호는 아니다
_DOTS = re.compile(r"^[.·…⋯∙ㆍ‥]+$")                                  # 「···」·「…」 — 서식의 「더 적을 자리」
_UNIT = re.compile(r"[(\[]\s*(%|주|건|건수|천원|백만원|원|명|개월|월|일|년|척|식|종)\s*[)\]]")
_PAREN = re.compile(r"\([^()]*\)|\[[^\[\]]*\]")
_SYM = re.compile(r"[^0-9A-Za-z가-힣%]")


def _bare(text):
    return _SYM.sub("", re.sub(r"\s+", "", text or ""))


def _head_word(text):
    """머리 글에서 괄호(단위·주석)와 기호를 뗀 낱말 — 「달성도 (%)」 → 「달성도」."""
    return _bare(_PAREN.sub("", text or ""))


# ---- 표 읽기 -------------------------------------------------------------------------------------------------

def view(S, tid):
    """표 하나(지금 문서) → {"id", "cells"[{id, r, c, rs, cs, text, role, fill, top, bottom}], "at"{(행, 열): 칸}, "rows", "cols", "top"(첫 자료 행)} | None.
    role = 3단계 칸 역할(늘린 행처럼 3단계에 없는 칸은 그 열 자료 칸의 다수 역할). top·bottom = 그 칸 위·아래 테두리 {type, widthMm, color} | None(선 없음)."""
    b = S["idx"].get(tid)
    if not b or b.get("type") != "table" or not b.get("cells"):
        return None
    lines = b.get("borderFills") or {}
    cells, at = [], {}
    for c in b["cells"]:
        ln = lines.get(c.get("bf")) or {}
        x = {"id": c["id"], "r": c["row"], "c": c["col"], "rs": c.get("rowSpan") or 1, "cs": c.get("colSpan") or 1, "text": c.get("text") or "",
             "role": (S["s3"].get(c["id"]) or {}).get("role"), "fill": bool(c.get("shaded")), "top": ln.get("t"), "bottom": ln.get("b"),
             "calc": bool(S["ops"].get(c["id"])) if c["id"] in S["s3"] else None}
        cells.append(x)
        for r in range(x["r"], x["r"] + x["rs"]):
            for k in range(x["c"], x["c"] + x["cs"]):
                at[(r, k)] = x
    rows, cols = max(r for r, _ in at) + 1, max(k for _, k in at) + 1
    top = min((x["r"] for x in cells if x["role"] == "field"), default=rows)
    by_col, calc_col = defaultdict(Counter), defaultdict(Counter)
    for x in cells:
        if x["role"] and x["r"] >= top:
            by_col[x["c"]][x["role"]] += 1
            if x["role"] == "field":
                calc_col[x["c"]][bool(x["calc"])] += 1
    for x in cells:   # 3단계에 없는 칸(늘린 행) — 역할·계산 칸 여부는 그 열 자료 칸의 다수를 따른다(본뜬 합계 칸을 값 칸으로 보면 다시 계획할 때 원본의 합계를 넣으려 든다)
        if not x["role"]:
            x["role"] = by_col[x["c"]].most_common(1)[0][0] if by_col[x["c"]] else "field"
        if x["calc"] is None:
            x["calc"] = bool(calc_col[x["c"]]) and calc_col[x["c"]].most_common(1)[0][0]
    return {"id": tid, "cells": cells, "at": at, "rows": rows, "cols": cols, "top": top}


def _heads_key(v):
    """머리 행(자료 행 위)의 꼴 — 열 수 + 머리 칸마다 (행, 열, 병합, 글). 이어진 표인지 견주는 데 쓴다."""
    return v["cols"], tuple(sorted((x["r"], x["c"], x["rs"], x["cs"], P._ws(x["text"])) for x in v["cells"] if x["r"] < v["top"]))


def _continued(S, tid):
    """그 표 **바로 뒤에 이어진 표**들의 id(쪽이 넘어가 둘로 나뉜 같은 표) — 같은 형제 목록에서 사이에 빈 문단만 두고 잇따르고, 열 수와 머리 행의 칸 배치 · 글이 꼭 같은 표. 머리 행이 없는 표는 못 가린다(빈 목록)."""
    seq = (S.get("where") or {}).get(tid) or ()
    k = next((i for i, b in enumerate(seq) if b["id"] == tid), None)
    v = view(S, tid)
    out = []
    if k is None or v is None or not v["top"]:
        return out
    key = _heads_key(v)
    for b in seq[k + 1:]:
        if b.get("type") == "table":
            w = view(S, b["id"])
            if w is None or not w["top"] or _heads_key(w) != key:
                break
            out.append(b["id"])
        elif b.get("type") != "paragraph" or (b.get("text") or "").strip():
            break
    return out


def _chain_head(S, tid):
    """이어진 표 사슬의 **첫 표** id — 그 표가 앞 표에 이어진 표면(앞 표의 `_continued` 에 든다) 앞으로 거슬러 간다. 표 짝이 사슬의 뒤쪽 표에 걸려 있어도 원본은 사슬 전체다."""
    seq = (S.get("where") or {}).get(tid) or ()
    k = next((i for i, b in enumerate(seq) if b["id"] == tid), None)
    head = tid
    for b in reversed(seq[:k] if k else ()):
        if b.get("type") == "table":
            if tid not in _continued(S, b["id"]):
                break
            head = b["id"]
        elif b.get("type") != "paragraph" or (b.get("text") or "").strip():
            break
    return head


def source_view(S, tid):
    """원본 표의 읽을거리 — 그 표가 든 **이어진 표 사슬 전체**(첫 표 `_chain_head` + 바로 뒤에 이어진 표들 `_continued`)를 한 표로: 이어진 표의 자료 행을 아래에 잇는다(행 번호는 이어서 · 칸 id 는 제 것 그대로).
    v["id"] 는 받은 tid 그대로 · v["parts"] = 사슬의 표 id 들. 2026-11-22: 계획서의 성능 목표 표가 쪽 넘김으로 두 표(같은 머리)로 나뉘어 있는데 표 대응이 원본 표 하나만 읽어 다른 쪽 표의 항목이 빠졌다."""
    if view(S, tid) is None:
        return None
    head = _chain_head(S, tid)
    v = view(S, head)
    v = {**v, "id": tid, "cells": list(v["cells"]), "at": dict(v["at"]), "parts": [head]}
    for cid in _continued(S, head):
        w = view(S, cid)
        off = v["rows"] - w["top"]
        for x in w["cells"]:
            if x["r"] < w["top"]:
                continue
            y = {**x, "r": x["r"] + off}
            v["cells"].append(y)
            for r in range(y["r"], y["r"] + y["rs"]):
                for k in range(y["c"], y["c"] + y["cs"]):
                    v["at"][(r, k)] = y
        v["rows"] += w["rows"] - w["top"]
        v["parts"].append(cid)
    return v


def _sig_from(S, tid, top):
    """원본 표의 구조 서명 — 이어진 표가 있으면 그 표들의 서명을 함께(이어진 표가 없으면 전과 같은 값: 앞서 저장한 대응이 낡지 않는다)."""
    head = _chain_head(S, tid)
    parts = [head, *_continued(S, head)]
    sigs = [sig(S["idx"][p], top) for p in parts if p in S["idx"]]
    return sigs[0] if len(sigs) == 1 else hashlib.sha1("|".join(sigs).encode("utf-8")).hexdigest()[:16]


def blank_fp(blocks):
    """문서 내용의 지문 — 블록·칸의 글과 칸 배치만(바이트가 아니라). 빈 양식을 다시 저장하거나 hwp 에서 바꿔 올려도 같다 — 양식 정보 `match.blank` 에 적어 둔 지문과 같으면 「등록된 빈 양식」(② §5-3 6)."""
    out = []

    def walk(seq):
        for b in seq:
            out.append(f"{b.get('type')}:{(b.get('text') or '').strip()}")
            for c in b.get("cells") or ():
                out.append(f"c{c['row']},{c['col']},{c.get('rowSpan')},{c.get('colSpan')}:{(c.get('text') or '').strip()}")
                walk(c.get("blocks") or ())
    walk(blocks)
    return hashlib.sha256(chr(10).join(out).encode("utf-8")).hexdigest()


def sig(block, top):
    """표의 구조 서명 — 행·열·병합 배치 + 머리 행(top 위)의 글. 자료 칸의 글은 안 넣는다(넣은 내용 때문에 대응이 낡지 않게)."""
    cells = sorted((c["row"], c["col"], c.get("rowSpan") or 1, c.get("colSpan") or 1) for c in block.get("cells") or ())
    heads = sorted((c["row"], c["col"], P._ws(c.get("text"))) for c in block.get("cells") or () if c["row"] < top)
    return hashlib.sha1(json.dumps([cells, heads], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _col_heads(v, c):
    """열 c 위의 머리 칸들(위 → 아래, 표 제목 줄 뺌)."""
    out = []
    for r in range(v["top"]):
        x = v["at"].get((r, c))
        if x is not None and x["role"] != "title" and all(x is not y for y in out):
            out.append(x)
    return out


def _row_heads(v, r, c=None):
    """행 r 에 걸친 머리·이름 칸들(왼쪽 → 오른쪽) — c 를 주면 그 열 왼쪽의 것만."""
    out = []
    for k in range(v["cols"] if c is None else c):
        x = v["at"].get((r, k))
        if x is not None and x["role"] in HEADISH and all(x is not y for y in out):
            out.append(x)
    return out


def _year(text, values):
    """머리 글 → 전체 차례 차년도 수 | None — 「해당연도」 = 당해 · 「다음 연도」 = 당해 + 1 · 「2차년도」·「1단계-2차년도」·「2027」."""
    s = re.sub(r"\s+", "", text or "")
    cur = values.get("current") or 1
    if "다음연도" in s or "차기연도" in s:
        return cur + 1
    if "해당연도" in s or "당해연도" in s:
        return cur
    return MT._year_no(s, values)


def _col_year(v, c, values):
    return next((y for h in reversed(_col_heads(v, c)) if (y := _year(h["text"], values)) is not None), None)


def _unit(v, c):
    return next((m.group(1).replace("건수", "건") for h in reversed(_col_heads(v, c)) if (m := _UNIT.search(h["text"] or ""))), None)


def _special(line):
    return bool(line) and line.get("type") not in (None, "NONE", "SOLID")


def _kind(line):
    return (line["type"], f"{line.get('widthMm', 0.1):g} mm", line.get("color") or "#000000") if line else None


def _label_of(v, r):
    """행 r 이 든 항목의 이름 칸(여러 행에 걸친 머리 칸 가운데 가장 작은 묶음) | None — 표시가 항목 안 어느 행 사이 경계인지 읽는 데 쓴다."""
    hs = [x for x in _row_heads(v, r) if x["rs"] > 1 and x["r"] >= v["top"]]
    return min(hs, key=lambda x: x["rs"]) if hs else None


def marks(S, v):
    """목적 표의 표시 목록(② §5-3 7) → [{name, type, width, color, boundary(항목 안 몇째 행 아래 경계 — 0부터), off{type, width, color}, cells}].
    표시 = 자료 칸 위·아래 가장자리의 특수 선(SOLID·NONE 이 아닌 것) — 종류마다 항목 안 경계 자리는 예시 칸의 다수결, 이름은 표 뒤 범례 표에서 그 선 옆의 글(없으면 선 종류)."""
    seen, base = defaultdict(Counter), Counter()   # seen = 특수 선 종류 → 경계 자리마다 칸 수 · base = (경계 자리, 보통 선 종류 | None) → 칸 수
    for x in v["cells"]:
        if x["r"] < v["top"] or x["role"] != "field":
            continue
        lab = _label_of(v, x["r"])
        if lab is None:
            continue
        for edge, at in (("bottom", x["r"] + x["rs"] - 1 - lab["r"]), ("top", x["r"] - lab["r"] - 1)):
            if not 0 <= at < lab["rs"] - 1:
                continue
            if _special(x[edge]):
                seen[_kind(x[edge])][at] += 1
            else:
                base[(at, _kind(x[edge]))] += 1
    out = []
    for kind, where in seen.items():
        at = where.most_common(1)[0][0]
        offs = Counter({k[1]: n for k, n in base.items() if k[0] == at})
        off = offs.most_common(1)[0][0] if offs else None
        out.append({"name": _legend(S, v, kind) or kind[0], "type": kind[0], "width": kind[1], "color": kind[2], "boundary": at,
                    "off": {"type": off[0], "width": off[1], "color": off[2]} if off else dict(OFF), "cells": sum(where.values())})
    return sorted(out, key=lambda m: m["boundary"])


def _after(S, tid):
    seq = (S.get("where") or {}).get(tid) or ()
    k = next((i for i, b in enumerate(seq) if b["id"] == tid), None)
    return list(seq[k + 1:k + 1 + AFTER_MAX]) if k is not None else []


def _legend(S, v, kind):
    """표 뒤 범례 표에서 그 선(kind) 옆의 글 | None."""
    for b in _after(S, v["id"]):
        if b.get("type") != "table":
            continue
        lines = b.get("borderFills") or {}
        for c in b.get("cells") or ():
            ln = lines.get(c.get("bf")) or {}
            if kind in (_kind(ln.get("t")) if _special(ln.get("t")) else None, _kind(ln.get("b")) if _special(ln.get("b")) else None):
                a, e = c["row"], c["row"] + (c.get("rowSpan") or 1)
                hit = next((P._ws(o.get("text")) for o in b["cells"] if o is not c and P._ws(o.get("text")) and o["row"] < e and a < o["row"] + (o.get("rowSpan") or 1)), None)   # 같은 행에 걸친 글 칸
                if hit:
                    return hit[:20]
    return None


def _tok(v, x):
    span = (f"-{x['c'] + x['cs'] - 1}" if x["cs"] > 1 else "") + (f"↓{x['rs']}" if x["rs"] > 1 else "")
    text = P._ws(x["text"])
    out = f"{span} {ROLE.get(x['role'], 'F')}" + (f"「{text[:TEXT]}{'…' if len(text) > TEXT else ''}」" if text else "")
    if x["r"] >= v["top"]:
        out += (" ■" if x["fill"] else "") + (f" ▔{x['top']['type']}" if _special(x["top"]) else "") + (f" ▁{x['bottom']['type']}" if _special(x["bottom"]) else "")
    return out


def grid(v):
    """표 격자 → 행마다 한 줄(계약의 꼴). 같은 꼴의 한 칸짜리 빈 칸이 이어지면 「c2..c15 F」 로 묶는다(좌표는 그대로 읽힌다)."""
    out = []
    for r in range(v["rows"]):
        toks, run = [], None
        flush = lambda: toks.append((f"c{run[0]}" if run[0] == run[1] else f"c{run[0]}..c{run[1]}") + run[2]) if run else None  # noqa: E731
        for x in sorted((x for x in v["cells"] if x["r"] == r), key=lambda x: x["c"]):
            tok, plain = _tok(v, x), x["rs"] == 1 and x["cs"] == 1 and not x["text"].strip()
            if plain and run and run[2] == tok and run[1] + 1 == x["c"]:
                run[1] = x["c"]
                continue
            flush()
            run = [x["c"], x["c"], tok] if plain else None
            if not plain:
                toks.append(f"c{x['c']}{tok}")
        flush()
        out.append(f"r{r}: " + " | ".join(toks))
    return out


# ---- 대상 · 자료 ---------------------------------------------------------------------------------------------

def targets(tabs_plan, fixed_plan):
    """대응이 필요한 표 [(목적 표 id, 원본 표 id)] — 원본 표는 정해졌는데 스크립트가 한 칸도 못 맞춘 표(② §5-3 2)."""
    out = {}
    shape = {s.get("table") for s in (fixed_plan or {}).get("skipped") or () if s.get("why") == "shape"}
    for t in (fixed_plan or {}).get("tables") or ():
        if t.get("status") == "paired" and t.get("from") and t["to"] in shape and not t.get("cells"):
            out.setdefault(t["to"], t["from"])
    shape_g = {s.get("group") for s in (tabs_plan or {}).get("skipped") or () if s.get("why") == "shape"}
    for t in (tabs_plan or {}).get("tables") or ():
        if t.get("mode") == "fixed" and t.get("to") and t.get("from") and not t.get("cells") and not t.get("rows") and t.get("group") in shape_g:
            out.setdefault(t["to"], t["from"])
    return list(out.items())


def _table(S, tid):
    return next((t for t in S["tables"] if t["id"] == tid), None)


def _brief(S, t, v):
    own = t.get("owner") or {}
    return {"key": t["id"], "title": P._ws(X._title_of(S, t))[:P.TEXT_MAX], "path": [P._ws(p)[:40] for p in (own.get("path") or ())[-3:]], "ctx": X._ctx(S, t), "top": v["top"], "grid": grid(v)}


def data(T, F, tid, fid):
    """대응 한 건의 자료(모듈 설명) → (payload, ctx) | (None, 까닭 글). T·F = merge_fixed._side 꼴. ctx = check 가 답을 대어 볼 것 {T, F, tv, fviews, marks, tctx}.
    원본 후보 = 이어진 표 fid + 같은 소속 제목 아래의 다른 표(맥락이 목적 표와 어긋나지 않는 것, SIBLINGS_MAX 개까지 — 한 절에 차년도마다 표가 따로 있는 일정 표)."""
    tt, ft = _table(T, tid), _table(F, fid)
    tv = view(T, tid) if tt else None
    if tv is None or ft is None:
        return None, "표를 지금 문서에서 못 찾음"
    tctx = X._ctx(T, tt)
    own = lambda t: (P._ws((t.get("owner") or {}).get("text")), tuple((t.get("owner") or {}).get("path") or ()))  # noqa: E731
    sib = [t for t in F["tables"] if t["id"] != fid and t["id"] in F["idx"] and own(t)[0] and own(t) == own(ft) and not X._ctx_clash(tctx, X._ctx(F, t))][:SIBLINGS_MAX]
    fviews, sources, n, tails = {}, [], len(tv["cells"]), set()
    for t in [ft, *sib]:
        if t["id"] in tails:
            continue   # 앞 표에 이어진 표 — 그 표의 격자에 이미 이어 실었다
        v = source_view(F, t["id"])   # 이어진 표(쪽 넘김으로 나뉜 같은 표)는 한 표로 보낸다
        tails |= set((v or {}).get("parts") or ()) - {t["id"]}   # 같은 사슬의 다른 표 — 이 격자에 이미 들어 있다
        if v is None or n + len(v["cells"]) > GRID_CELLS_MAX:
            continue
        n += len(v["cells"])
        fviews[t["id"]] = v
        sources.append({**_brief(F, t, v), "paired": t["id"] == fid})
    if fid not in fviews:
        return None, "표가 너무 커서 보내지 못함"
    ms = marks(T, tv)
    after = [P._ws(x.get("text") or " / ".join(P._ws(c.get("text")) for c in x.get("cells") or () if P._ws(c.get("text"))))[:AFTER_LEN] for x in _after(T, tid)]
    payload = {"target": {**_brief(T, tt, tv), "current": T["values"].get("current") or 1, "marks": [{"name": m["name"], "line": m["type"]} for m in ms], "after": [a for a in after if a]},
               "sources": sources}
    return payload, {"T": T, "F": F, "tv": tv, "fviews": fviews, "marks": ms, "tctx": tctx, "to": tid, "paired": fid}


def guide_part(guide=None):
    if guide is False:
        return FALLBACK_GUIDE
    return merge_guides.part(merge_guides.get(GUIDE) if guide is None else guide) or FALLBACK_GUIDE


def links_part(text):
    """목적 양식의 「자리 연결」 절 글 → 프롬프트에 붙일 절 | ""."""
    return f"\n\n## 자리 연결 — 사용자가 적어 둔 연결(이 양식에만 해당)\n{LINK_NOTE}\n\n{text.strip()}" if (text or "").strip() else ""


def prompt(payload, job=None, links="", guide=None):
    """프롬프트 글 = 계약(+ 목적 표에 작성 지침이 있으면 그 한 줄 — spec_병합 ② §5-11) + 판단 지침 + 할 일 프롬프트 + 자리 연결 절 + 자료(JSON)."""
    from app import place_guides as PG
    note = PG.CONTRACT_LINE if (payload.get("target") or {}).get("guides") else ""
    return CONTRACT + note + guide_part(guide) + job_prompts.part(job) + links_part(links) + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parts(job=None, links="", guide=None):
    """화면 「지침」 보기에 싣는 글들(자료 빼고) — merge_llm.parts 와 같은 꼴."""
    g = merge_guides.get(GUIDE) if guide is None else guide
    out = [{"key": "contract", "title": "계약 — 역할 · 자료 설명 · 답의 꼴", "text": CONTRACT, "source": "app/merge_table_map.py",
            "note": "코드에 든 글입니다(답을 검증하는 코드와 한 몸) — 판단 기준은 아래 지침에 있습니다"}]
    if g and merge_guides.body(g):
        out.append({"key": "guide", "title": f"판단 지침 — {g['title']}", "text": merge_guides.body(g), "source": g["path"], "note": "이 파일을 고치면 다음 실행부터 적용됩니다"})
    else:
        out.append({"key": "guide", "title": "판단 지침 — (지침 파일 없음: 기본 기준)", "text": FALLBACK_GUIDE.strip(), "source": "app/merge_table_map.py", "note": "app/merge_guides_default/table_map.md 가 없어 기본 기준만 보냅니다"})
    if job and job_prompts.part(job):
        out.append({"key": "job", "title": f"할 일 프롬프트 — {job['name']}", "text": job_prompts.body(job["text"]), "source": job["path"],
                    "note": "이 작업의 전제(무엇이 원본·목적인지, 무엇을 넣는지) — 이 파일을 고치면 다음 실행부터 적용됩니다"})
    if (links or "").strip():
        out.append({"key": "form", "title": "양식 정보 — 「자리 연결」 절(연결 코멘트)", "text": links.strip(), "source": "",
                    "note": "어느 표·단락을 어디와 이을지 사용자가 적어 둔 것 — 2단계 묶음의 연결 코멘트 칸이나 「양식 정보」 에서 고칩니다"})
    return out


def jobs_for(payloads, job=None, links="", guide=None, model=MODEL, effort="medium", timeout=420.0):
    """llm.ask_all 에 줄 호출 목록 — 표마다 하나."""
    return [{"schema": SCHEMA, "content": prompt(p, job, links, guide), "what": f"merge-table-map-{i + 1}", "timeout": timeout, "effort": effort, "model": model} for i, p in enumerate(payloads)]


# ---- 답 검증 -------------------------------------------------------------------------------------------------

def _ints(x, lo, hi):
    """정수 목록(lo ≤ n < hi · 오름차순 · 겹치지 않음) | None."""
    if not isinstance(x, list) or not x or not all(isinstance(n, int) and not isinstance(n, bool) and lo <= n < hi for n in x):
        return None
    return x if all(a < b for a, b in zip(x, x[1:])) else None


def _field_why(ctx, fv, to, frm, kind):
    """열 짝 하나가 뜻이 맞는지 격자에서 다시 읽는다 → 거절 까닭 | None(② §5-3 5 「열」)."""
    tv, T, F = ctx["tv"], ctx["T"], ctx["F"]
    th, fh = _col_heads(tv, to), _col_heads(fv, frm)
    if any(_RESULT.match(_head_word(h["text"])) for h in th):
        return "목적 열이 실적·달성 자리(계획서에 없는 내용)"
    if th and fh:
        a, b = th[-1], fh[-1]
        na, nb = HC.parse_num(P._ws(a["text"])).get("num"), HC.parse_num(P._ws(b["text"])).get("num")
        digits = lambda x: bool(re.fullmatch(r"\d{1,4}", P._ws(x["text"])))  # noqa: E731 — 월·연도처럼 수뿐인 머리
        if digits(a) and digits(b):
            if na != nb:
                return f"머리의 수가 다름(목적 {P._ws(a['text'])} ↔ 원본 {P._ws(b['text'])})"
            if a["cs"] > 1 and a["cs"] == b["cs"] and to - a["c"] != frm - b["c"]:
                return f"머리 「{P._ws(a['text'])}」 안의 열 차례가 다름"
    ty, fy = _col_year(tv, to, T["values"]), _col_year(fv, frm, F["values"])
    if ty is not None and fy is not None and ty != fy:
        return f"차년도가 다름(목적 {ty}차년도 ↔ 원본 {fy}차년도)"
    tu, fu = _unit(tv, to), _unit(fv, frm)
    if tu and fu and tu != fu:
        return f"단위가 다름(목적 {tu} ↔ 원본 {fu})"
    return None


def check(ctx, answer):
    """답을 보낸 격자에 대고 검증(② §5-3 5 — 꼴 · 맥락 · 열) → (대응 | None, 거절 [{…, why}]). 대응 = {from, records[{to, from, example}], grow[{like, from}],
    fields[{to, from, kind}], mark, reason, rejected, top{to, from}, sig{to, from}}. 항목(records)의 이름·칸은 계획 때 지금 글에 대고 다시 본다(plan)."""
    a = answer if isinstance(answer, dict) else {}
    key, rejected = str(a.get("from") or ""), []
    fv = ctx["fviews"].get(key)
    if not key:
        return None, [{"why": "옮길 원본 표 없음", "reason": str(a.get("reason") or "")[:300]}]
    if fv is None:
        return None, [{"from": key, "why": "입력에 없는 원본 표 key"}]
    tv, T, F = ctx["tv"], ctx["T"], ctx["F"]
    ft = _table(F, key)
    if clash := X._ctx_clash(ctx["tctx"], X._ctx(F, ft)):
        return None, [{"from": key, "why": "기관이 다른 표" if clash == "org" else "차년도가 다른 표"}]
    fields, seen = [], set()
    for f in a.get("fields") or ():
        to, frm, kind = (f or {}).get("to"), (f or {}).get("from"), str((f or {}).get("kind") or "text")
        ok = isinstance(to, int) and isinstance(frm, int) and 0 <= to < tv["cols"] and 0 <= frm < fv["cols"] and kind in ("text", "mark")
        why = "입력에 없는 열·모르는 kind" if not ok else "같은 목적 열을 두 번" if to in seen else _field_why(ctx, fv, to, frm, kind)
        if why:
            rejected.append({"field": f, "why": why})
        else:
            seen.add(to)
            fields.append({"to": to, "from": frm, "kind": kind})
    mark = str(a.get("mark") or "").strip()
    names = {m["name"] for m in ctx["marks"]}
    if any(f["kind"] == "mark" for f in fields) and (mark not in names or _RESULT.match(_head_word(mark))):
        rejected.append({"mark": mark, "why": "목적 표에 없는 표시이거나 실적 쪽 표시" if mark else "표시 이름 없음"})
        fields = [f for f in fields if f["kind"] != "mark"]
        mark = ""
    records, grow, used, used_from = [], [], set(), set()
    for r in a.get("records") or ():
        to, frm = _ints((r or {}).get("to"), tv["top"], tv["rows"]), _ints((r or {}).get("from"), fv["top"], fv["rows"])
        why = ("입력에 없는 행(머리 행 포함)" if to is None or frm is None else "행 수가 다름" if len(to) != len(frm)
               else "같은 목적 행을 두 번" if used & set(to) else "같은 원본 행을 두 번" if used_from & set(frm) else None)
        if why:
            rejected.append({"record": r, "why": why})
            continue
        used |= set(to)
        used_from |= set(frm)
        records.append({"to": to, "from": frm, "example": bool(r.get("example"))})
    for g in a.get("grow") or ():
        like, frm = _ints((g or {}).get("like"), tv["top"], tv["rows"]), _ints((g or {}).get("from"), fv["top"], fv["rows"])
        to = _ints((g or {}).get("to"), tv["top"], tv["rows"]) if (g or {}).get("to") else like   # 안 적으면 묶음의 모든 행이 짝
        why = ("입력에 없는 행" if like is None or frm is None or to is None else "본뜰 행이 이어져 있지 않음" if like[-1] - like[0] != len(like) - 1
               else "짝이 되는 행이 본뜰 묶음 밖" if not set(to) <= set(like) else "행 수가 다름" if len(to) != len(frm) else "같은 원본 행을 두 번" if used_from & set(frm) else None)
        if why:
            rejected.append({"grow": g, "why": why})
            continue
        used_from |= set(frm)
        grow.append({"like": like, "to": to, "from": frm})
    if not fields or not (records or grow):
        return None, rejected + [{"why": "남은 열 짝·항목 짝이 없음"}]
    return {"from": key, "records": records, "grow": grow, "fields": fields, "mark": mark, "reason": str(a.get("reason") or "").strip()[:400], "rejected": rejected[:40],
            "top": {"to": tv["top"], "from": fv["top"]}, "sig": {"to": sig(T["idx"][tv["id"]], tv["top"]), "from": _sig_from(F, key, fv["top"])}}, rejected


# ---- 계획 ----------------------------------------------------------------------------------------------------

def _same_line(cur, want):
    """칸 가장자리의 지금 선(view 의 top·bottom) 이 기대(want {type, width, color})와 같은가."""
    if want["type"] == "NONE":
        return not cur
    return bool(cur) and cur.get("type") == want["type"] and abs(cur.get("widthMm", 0) - float(want["width"].split()[0])) < 1e-6 and (cur.get("color") or "").upper() == want["color"].upper()


def _inside(x, rows):
    """칸 x 가 그 항목의 행들 안에 통째로 드는가(항목 밖으로 걸친 갈래 칸은 그 항목의 칸이 아니다)."""
    return rows[0] <= x["r"] and x["r"] + x["rs"] - 1 <= rows[-1]


def _slot(text):
    t = P._ws(text)
    return not t or bool(_DOTS.fullmatch(t)) or bool(_ORD.fullmatch(t)) or bool(_ORD_N.fullmatch(t))


def _lead(text):
    """이름 글 → (앞 순번 수 | None, 순번을 뗀 이름) — 「1. 선내 데이터」 → (1, 「선내 데이터」) · 「3.」 → (3, 「」) · 「설계사양서」 → (None, 「설계사양서」)."""
    t = P._ws(text)
    if m := _ORD_LEAD.match(t):
        return int(m.group(1)), t[m.end():].strip()
    if m := _ORD.fullmatch(t):
        return int(m.group(1)), ""
    return None, t


def _ordinal(tv, tc, seq=0):
    """순번 자리 칸 tc 에 적을 순번 수 | None(모름) — 「3.」 = 3 · 「n.」 = 바로 위 항목의 순번 + 1(위에 순번이 없으면 모름). seq = 그 칸을 본뜬 몇째 묶음인가(0 = 그 칸 자체 — 늘린 묶음은 그 뒤로 이어 센다)."""
    t = P._ws(tc["text"])
    if m := _ORD.fullmatch(t):
        return int(m.group(1)) + seq
    if not _ORD_N.fullmatch(t):
        return None
    up = tv["at"].get((tc["r"] - 1, tc["c"]))
    k = _lead(up["text"])[0] if up is not None and up is not tc and up["r"] >= tv["top"] else None
    return None if k is None else k + 1 + seq


def _ord_text(cur, n):
    """순번 자리의 꼴(「1.」·「(1)」·「n.」)을 그대로 두고 수만 n 으로."""
    return re.sub(r"\d+|[nN]", str(n), P._ws(cur), count=1)


def _name_key(text):
    """이름을 견줄 꼴 — 앞 순번 · 끝의 각주 번호 · 빈칸 · 기호를 뗀 글(「기술 요약 정보」 = 「기술요약정보」 · 「중앙행정기관명2)」 = 「중앙행정기관명」 · 「1. 설계사양서」 = 「설계사양서」)."""
    return _bare(_FOOT.sub("", _lead(text)[1]))


def _labels(S):
    """구성 반영이 적은 라벨 칸 id(구분 기준 묶음 항목의 라벨 — 기관 이름 · 차년도 칸). 그 칸의 글은 프로젝트 구성의 값이라 올린 빈 양식과 다른 것이 정상이고, 표 대응이 덮지도 않는다."""
    return {it["label"] for g in (S.get("groups") or {}).values() for it in g.get("items") or () if it.get("label")}


def _form_text(tv, tc, orig):
    """그 값 칸의 글이 **올린 빈 양식의 글 그대로**인가(② §5-3 6 의 칸 조건) — 원본에 있던 칸이면 그 칸의 원본 글과 같고, 구성 반영이 본떠 만든 칸(원본에 없는 id)이면 같은 열의 원본 칸 글 가운데 하나와 같다
    (본뜬 예시 — 지원·부담계획의 「기관유형」 「대학」 이 늘어난 기관 행마다 따라간 것). 사람이 쓴 글은 원본 글과 달라 여기 안 든다."""
    t = P._ws(tc["text"])
    if not orig or not t:
        return False
    if (o := orig.get(tc["id"])) is not None:
        return P._ws(o.get("text")) == t
    return any(x["c"] == tc["c"] and x["id"] in orig and P._ws(orig[x["id"]].get("text")) == t for x in tv["cells"])


def _keyed(tv, fv, rec):
    """그 항목이 **이름으로** 짝지어졌나 — 목적 행의 머리 칸에 서식의 이름(순번 · 빈 칸 · 「···」 아님)이 있고 원본 행의 머리 칸 이름과 같다(표지처럼 행마다 이름이 박힌 양식 표).
    이런 항목은 차례가 아니라 이름으로 서 있어, 하나를 못 넣어도 다른 항목이 어긋나지 않는다."""
    a = {k for r in rec["to"] for h in _row_heads(tv, r) if not _slot(h["text"]) and (k := _name_key(h["text"]))}
    return bool(a & {k for r in rec["from"] for h in _row_heads(fv, r) if (k := _name_key(h["text"]))})


def _original(x, orig):
    """그 칸이 올린 원본(등록된 빈 양식)에 있던 칸이고 지금 글·선이 원본 그대로인가."""
    o = (orig or {}).get(x["id"])
    return o is not None and P._ws(o.get("text")) == P._ws(x["text"]) and o.get("top") == _kind(x["top"]) and o.get("bottom") == _kind(x["bottom"])


def _is_example(tv, rows, orig, own=()):
    """서식 예시 항목인가(② §5-3 6) — 그 행들의 칸이 모두 원본 그대로이고, 값 칸에 글이나 표시가 하나라도 있다(이름만 박힌 고정 항목은 예시가 아니다).
    own = 구성 반영이 적은 라벨 칸(_labels) — 그 칸은 「원본 그대로」 에서 뺀다(기관 이름이 프로젝트 구성의 이름으로 바뀐 예시 행도 예시다 — 전에는 그 행을 사람 글로 봐 표 전체를 버렸다)."""
    cells = [x for x in tv["cells"] if _inside(x, rows)]
    return (bool(orig) and bool(cells) and all(_original(x, orig) for x in cells if x["id"] not in own)
            and any(x["role"] == "field" and x["id"] not in own and (P._ws(x["text"]) or _special(x["top"]) or _special(x["bottom"])) for x in cells))


def _orgs(S, cells):
    text = _bare(" ".join(x["text"] for x in cells))
    return {n for n in S["names"] if n and _bare(n) in text}


def _extent(v, rows):
    """항목의 행 범위 — 짝지은 행들 + 그 행들을 품은 가장 작은 이름 칸 묶음(「목표」 행 하나만 짝이어도 두 행에 걸친 이름·단위 칸은 그 항목의 칸이다). 갈래처럼 더 큰 묶음은 안 넣는다."""
    lab = _label_of(v, rows[0])
    if lab is not None and lab["r"] <= rows[0] and rows[-1] <= lab["r"] + lab["rs"] - 1:
        return list(range(lab["r"], lab["r"] + lab["rs"]))
    return list(range(rows[0], rows[-1] + 1))


def _toks(text):
    """이름의 낱말(두 글자 이상 — 각주 번호 뗌): 「지식재산권(출원)」 → {지식재산권, 출원}."""
    return {t for t in re.split(r"[^0-9A-Za-z가-힣]+", _FOOT.sub("", P._ws(text))) if len(t) >= 2}


def _related(cur, new_text, fheads):
    """서식에 박힌 이름 cur 와 원본 이름이 **닿는 이름**인가 — 한쪽이 다른 쪽을 품거나(「사업화실적」 ⊃ 「사업화」 · 「전체14-1)」 ⊃ 「전체」), 서식 이름의 낱말이 원본 그 행의 머리 글 낱말과 하나라도 같다
    (「지식재산권(출원)」 ↔ 「특허 › 출원」). 닿지 않는 이름(「계획수립 및 자료조사」 ↔ 「서브모듈 시작품 제작」)은 다른 항목이다 — 서식의 예시 이름일 수 있어 그 항목을 안 넣는다."""
    a, b = _name_key(cur), _name_key(new_text)
    if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
        return True
    return bool(_toks(cur) & {t for h in fheads for t in _toks(h)})


def _record(T, F, tv, fv, m, rec, mk, orig, new=False, seq=0, notes=None, outer=None):
    """항목 하나 → (칸 쓰기 [{to | (행 차례, 열), from, text, mode, was}], 지울 예시 칸 [칸], 표시 [(열, 있음)], 예시인가, 항목의 행 범위) | 까닭 글(통째로 안 넣음).
    new = 늘릴 묶음(rec["like"] 를 본뜬 빈 행들 — 목적 칸은 like 의 칸으로 보고 (like 첫 행에서의 차례, 열) 좌표로 적는다) · seq = 같은 묶음을 본뜬 몇째인가(1부터 — 순번을 이어 세는 데 쓴다).
    **순번 자리**(② §5-3 5 「항목」 — 2026-11-22 고침): 목적 이름 칸이 순번(「1.」)이고 원본 이름에도 순번이 있으면 같은 순번이어야 한다(다르면 한 칸 밀린 짝 — 거절). 원본 이름에 순번이 **없으면** 목적의 순번을 둔 채
    이름을 잇는다(「1.」 + 「설계사양서」 → 「1. 설계사양서」 — 전에는 거절해 순번 없는 계획서의 항목이 하나도 못 들어갔다). 서식의 「n.」 줄과 늘린 묶음은 위 항목에서 이어 센 순번을 적는다."""
    trows, frows = rec["to"], rec["from"]
    text_ = rec["like"] if new else _extent(tv, trows)   # 목적 항목의 행 범위
    fext = _extent(fv, frows)
    # 구성 반영이 적은 칸 = 구분 기준 묶음의 라벨 칸 + 그 항목의 머리 꼴 칸 가운데 글이 프로젝트 구성의 기관 이름인 칸(반영 뒤에는 묶음으로 다시 안 읽히는 표가 있다 — 지원·부담계획의 「연구개발기관」 열)
    names = {_bare(n) for n in T["names"] if n}
    own = _labels(T) | ({x["id"] for x in tv["cells"] if _inside(x, text_) and (_bare(x["text"]) in names or (x["role"] in HEADISH and _orgs(T, [x])))} if not new else set())   # 값 꼴 칸은 글이 기관 이름뿐일 때만(표지의 「기관명」 칸)
    example = not new and bool(rec.get("example")) and _is_example(tv, text_, orig, own)
    owned = not new and any(x["id"] in own for x in tv["cells"] if _inside(x, text_))   # 구성 반영이 기관 · 차년도를 적은 항목(기관 행) — 그 행의 다른 칸에 남은 서식 글은 서식이 보기로 든 다른 기관의 값이다
    if new and not all(_slot(x["text"]) and x["role"] != "title" for x in tv["cells"] if _inside(x, text_)):
        return "본뜰 묶음이 빈 항목이 아님"
    if _orgs(T, [h for r in trows for h in _row_heads(tv, r)]) and (fo := _orgs(F, [h for r in frows for h in _row_heads(fv, r)])) and not (_orgs(T, [h for r in trows for h in _row_heads(tv, r)]) & fo):
        return "기관이 다른 행"
    writes, hit, marks_, same = [], {}, [], set()
    paired = {tc["id"] for f in m["fields"] if f["kind"] == "text" for tr, fr in zip(trows, frows)   # 이 항목에서 원본 칸과 짝이 된 목적 칸 — 계산 칸의 피연산자가 모두 여기 들면 그 계산 칸도 원본 값을 옮긴다
              if (tc := tv["at"].get((tr, f["to"]))) is not None and (sc := fv["at"].get((fr, f["from"]))) is not None and _inside(tc, text_) and _inside(sc, fext)}
    for f in m["fields"]:
        if f["kind"] == "mark":
            if mk is not None and mk["boundary"] + 1 < len(text_):
                marks_.append((f["to"], any((x := fv["at"].get((r, f["from"]))) is not None and x["fill"] for r in fext)))
            continue
        for tr, fr in zip(trows, frows):
            tc, sc = tv["at"].get((tr, f["to"])), fv["at"].get((fr, f["from"]))
            if tc is None or sc is None or tc["role"] == "title":
                continue
            if not _inside(tc, text_) or not _inside(sc, fext):
                if outer is not None and not new and not _inside(tc, text_) and tc["role"] in HEADISH and _slot(tc["text"]):
                    outer[tc["id"]].append((tc, sc))   # 여러 항목에 걸친 자리표시 머리 칸(「단계 n」 · 「연차 n」) — 항목마다의 원본 값이 모두 같으면 계획이 한 번 적는다(plan)
                continue
            if tc["id"] in own and not new:
                continue   # 구성 반영이 적은 라벨 칸(기관 이름 · 차년도) — 프로젝트 구성의 값이다: 덮지도, 원본과 다르다고 그 항목을 버리지도 않는다(「한양대학교 에리카산학협력단」 ↔ 「한양대학교」)
            if hit.setdefault(tc["id"], sc["id"]) != sc["id"]:
                return f"목적 칸 하나에 원본 칸이 둘(열 {f['to']})"
            if any(w["cell"] is tc for w in writes):
                continue
            new_text, cur = sc["text"], tc["text"]
            head = tc["role"] in HEADISH
            if any(_RESULT.match(_head_word(h["text"])) for h in _row_heads(tv, tr, tc["c"])[-1:]):
                continue   # 「실적」 행 — 계획서에 없는 내용
            if P._ws(new_text) == P._ws(cur):
                same.add(tc["id"])   # 이미 원본 글과 같다(넣은 뒤 다시 계획 · 서식 글이 우연히 같음)
                continue
            if MT._empty(new_text):
                continue
            if tc["calc"] and (new or not (ops := T["ops"].get(tc["id"])) or not set(ops) <= paired):
                continue   # 계산 칸 — 피연산자 칸이 이 항목의 짝에서 모두 이어졌을 때만 원본 값을 옮긴다(merge_tables 와 같은 규칙 — 같은 줄의 합). 아니면 비워 둔다(합계 계산 몫) · 늘린 묶음의 계산 칸은 늘 비운다
            if head and not MT._empty(cur) and (k := _name_key(cur)) and k == _name_key(new_text):
                continue   # 같은 이름 — 띄어쓰기·기호·각주 번호만 다르거나(「기술 요약 정보」 ↔ 「기술요약정보」 · 「공고번호6)」 ↔ 「공고번호」: 서식의 이름을 둔다) 순번을 붙여 이미 넣은 이름(「1. 설계사양서」 ↔ 「설계사양서」: 다시 계획하면 일 없음)
            if MT._empty(cur):
                mode = "empty"
            elif head and _slot(cur):
                if not _DOTS.fullmatch(P._ws(cur)):   # 순번 자리(「1.」 · 「n.」)
                    a, (b, name) = _ORD.fullmatch(P._ws(cur)), _lead(new_text)
                    if a and not new and b is not None and int(a.group(1)) != b:
                        return f"순번이 다름(목적 「{P._ws(cur)}」 ↔ 원본 「{P._ws(new_text)[:20]}」)"
                    if b is None and name:   # 원본 이름에 순번이 없다 — 목적의 순번(늘린 묶음·「n.」 은 이어 센 수)을 둔 채 이름을 잇는다. 원본에 순번이 있으면 그 글 그대로
                        n = _ordinal(tv, tc, seq)
                        new_text = f"{_ord_text(cur, n)} {name}" if n is not None else name
                mode = "slot"
            elif example:
                mode = "example"
            elif not head and X._skeleton(cur, new_text):
                mode = "form"
            elif (not head or owned) and _form_text(tv, tc, orig):
                mode = "example"   # 그 칸의 글이 올린 빈 양식의 글 그대로(예시 값) — LLM 이 항목 전체를 예시로 안 적었어도 그 칸은 덮는다. 머리 꼴 칸은 구성 반영이 기관을 적은 행에서만(다른 기관 행에 남은 「기관유형」 「대기업」 · 「대학」 — 서식에 박힌 항목 이름은 그런 행이 아니다)
            elif head and _related(cur, new_text, [h["text"] for h in _row_heads(fv, fr)]):
                if notes is not None:   # 서식에 박힌 이름과 글자는 다른데 닿는 이름(「지식재산권(출원)」 ↔ 「특허 › 출원」 · 「사업화실적」 ↔ 「사업화」) — LLM 이 같은 항목으로 이은 것을 받아들인다: 이름은 서식 것을 두고 값만 넣고, 계획에 적어 사람이 본다
                    notes.append(f"목적 「{P._ws(cur)[:24]}」 ← 원본 「{' › '.join(P._ws(h['text'])[:16] for h in _row_heads(fv, fr)[-2:])}」")
                continue
            elif head:
                return f"이름이 다름(목적 「{P._ws(cur)[:20]}」 ↔ 원본 「{P._ws(new_text)[:20]}」)"
            else:
                return f"목적 칸에 다른 글(「{P._ws(cur)[:20]}」 — 원본 「{P._ws(new_text)[:20]}」)"
            writes.append({"cell": tc, "to": (tc["r"] - text_[0], tc["c"]) if new else tc["id"], "from": sc["id"], "text": new_text, "mode": mode, "was": cur})
    clears = []
    if example:   # 예시 항목을 실제 내용으로 바꾸면 그 항목에 남은 예시 글(달성도 100%)도 지운다 — 짝은 됐는데 못 쓴 칸(원본 칸이 빔 · 못 옮긴 계산 칸 · 실적 행)의 예시 값도(남기면 실제 금액 옆에 예시 합계 · 비율이 선다)
        done = {w["cell"]["id"] for w in writes} | same | own
        clears = [x for x in tv["cells"] if _inside(x, text_) and x["role"] == "field" and x["id"] not in done and P._ws(x["text"])]
    return writes, clears, marks_, example, text_


def _items_in(tv, rec):
    """LLM 이 목적 표의 **여러 항목을 한 항목으로** 이은 답 → 항목마다 나눈 답들 | None(한 항목 · 목적과 원본의 행 수가 달라 행 짝을 못 가름).
    항목 = 그 행의 이름 칸 묶음(_extent — 「중앙행정기관명」 2행 · 「전문기관명」 1행 · 「기술 분류」 2행). 행 짝은 답의 차례대로(to[k] ↔ from[k])."""
    to, fr = list(rec.get("to") or ()), list(rec.get("from") or ())
    if len(to) < 2 or len(to) != len(fr):
        return None
    parts = []
    for t, f in zip(to, fr):
        key = tuple(_extent(tv, [t]))
        if parts and parts[-1][0] == key:
            parts[-1][1].append(t)
            parts[-1][2].append(f)
        else:
            parts.append((key, [t], [f]))
    return [{**rec, "to": a, "from": b} for _, a, b in parts] if len(parts) > 1 else None


def _record_parts(T, F, tv, fv, m, rec, mk, orig, outer):
    """항목 하나 → [(항목, _record 의 답, 이은 이름들)]. 답이 통째로 안 들어가고(까닭 글) 그 답이 목적 표의 여러 항목을 묶은 것이면 **항목마다 나눠 다시 본다** —
    칸 하나가 안 맞은 항목만 건너뛰고 나머지 항목은 넣는다(2026-11-22 실제 이관: Opus 5.5 가 표지의 2~9행을 한 항목으로 답해, 3행의 칸 하나 때문에
    기술분류 두 행(8·9행 — 예시 「1순위 소분류 명칭」)까지 빠졌다. 행마다 답한 Fable 5.2 때는 들어갔다 — 모델에 따라 결과가 갈리지 않게).
    나눈 항목끼리 같은 목적 칸에 다른 원본 칸을 쓰면 나누지 않은 까닭 그대로 둔다(한 항목을 반씩 넣지 않는다)."""
    note = []
    got = _record(T, F, tv, fv, m, rec, mk, orig, notes=note, outer=outer)
    parts = _items_in(tv, rec) if isinstance(got, str) else None
    if not parts:
        return [(rec, got, note)]
    out = []
    for sub in parts:
        n = []
        out.append((sub, _record(T, F, tv, fv, m, sub, mk, orig, notes=n, outer=outer), n))
    seen = {}
    for _, g, _ in out:
        for w in g[0] if not isinstance(g, str) else ():
            if seen.setdefault(w["cell"]["id"], w["from"]) != w["from"]:
                return [(rec, got, note)]
    return out


def _mark_ops(tv, rows, marks_, mk, others, example):
    """그 항목의 표시 → [{to, edge, line}] — 고른 표시는 있음·없음을 모두 맞추고, 예시 항목이면 다른 표시(개발실적)는 지운다. 지금 선이 기대와 같으면 일 없음."""
    out = []

    def put(row_at, col, line):
        up, down = tv["at"].get((rows[row_at], col)), tv["at"].get((rows[row_at + 1], col))
        if up is not None and not _same_line(up["bottom"], line):
            out.append({"to": up["id"], "edge": "bottom", "line": line})
        if down is not None and down is not up and not _same_line(down["top"], line):
            out.append({"to": down["id"], "edge": "top", "line": line})
    on = {k: mk[k] for k in ("type", "width", "color")} if mk else None
    for col, has in marks_:
        put(mk["boundary"], col, on if has else mk["off"])
    if example:   # 예시 항목 — 대응 안 한 열에 남은 예시 선(고른 표시의 다른 달 · 다른 표시 「개발실적」)을 모두 지운다
        mapped = {col for col, _ in marks_}
        for o in ([mk] if mk else []) + list(others):
            if o["boundary"] + 1 >= len(rows):
                continue
            kind = (o["type"], o["width"], o["color"])
            for col in range(tv["cols"]):
                if o is mk and col in mapped:
                    continue
                up = tv["at"].get((rows[o["boundary"]], col))
                down = tv["at"].get((rows[o["boundary"] + 1], col))
                if (up is not None and _kind(up["bottom"]) == kind) or (down is not None and _kind(down["top"]) == kind):
                    put(o["boundary"], col, o["off"])
    return out


def stale(S_to, S_from, tid, m):
    """그 대응이 낡았나 — 두 표가 지금 문서에 있고 구조 서명이 저장한 것과 같아야 쓴다."""
    a, b = S_to["idx"].get(tid), S_from["idx"].get(m.get("from"))
    return (not a or not b or sig(a, (m.get("top") or {}).get("to", 0)) != (m.get("sig") or {}).get("to")
            or _sig_from(S_from, m["from"], (m.get("top") or {}).get("from", 0)) != (m.get("sig") or {}).get("from"))   # 원본 = 그 표 + 이어진 표(source_view) — 이어진 표가 생기거나 달라져도 낡음


def plan(T, F, maps, orig=None):
    """넣기 계획(모듈 설명) — 문서를 안 고친다. T·F = merge_fixed._side 꼴, maps = merge.json `tableMaps`, orig = 등록된 빈 양식으로 올린 원본의 칸 {id: {text, top, bottom}} | None."""
    out = {"tables": [], "cells": [], "clears": [], "lines": [], "rows": [], "skipped": [], "owned": [], "notes": []}
    for tid, m in (maps or {}).items():
        if not isinstance(m, dict) or not m.get("from"):
            continue
        tt, ft = _table(T, tid), _table(F, m["from"])
        row = {"to": tid, "from": m["from"], "title": P._ws(X._title_of(T, tt))[:P.TEXT_MAX] if tt else "", "fromTitle": P._ws(X._title_of(F, ft))[:P.TEXT_MAX] if ft else "",
               "stale": False, "records": 0, "cells": 0, "lines": 0, "rows": 0, "cleared": 0, "skipped": 0, "mark": m.get("mark") or "", "reason": m.get("reason") or ""}
        out["tables"].append(row)
        if tt is None or ft is None or stale(T, F, tid, m):
            row["stale"] = True
            row["skipped"] = 1
            out["skipped"].append({"table": tid, "why": "stale", "detail": "표의 행·열 구성이 대응을 낸 뒤 바뀜 — 「표 대응」 을 다시 돌리세요"})
            continue
        out["owned"].append(tid)
        tv, fv = view(T, tid), source_view(F, m["from"])
        ms = marks(T, tv)
        mk = next((x for x in ms if x["name"] == m.get("mark")), None)
        others = [x for x in ms if x is not mk]
        n0 = len(out["skipped"])
        outer = defaultdict(list)                       # 여러 항목에 걸친 자리표시 머리 칸 id → [(목적 칸, 원본 칸)]
        recs, said, nos = [], [], []                    # (항목, _record 의 답) · 항목마다 이름이 닿는 다른 이름과 이은 것(_related) · LLM 답의 몇째 항목인가
        for i, rec in enumerate(m.get("records") or ()):
            for sub, got, note in _record_parts(T, F, tv, fv, m, rec, mk, orig, outer):
                recs.append((sub, got))
                said.append(note)
                nos.append(i)
        if bad := next(((rec, got) for rec, got in recs if rec.get("example") and isinstance(got, str) and not _keyed(tv, fv, rec)), None):
            # LLM 이 서식 예시라고 본 항목을 바꿀 수 없다(등록된 빈 양식으로 올린 문서가 아니거나 사람이 그 행을 고쳤다) — 예시 행을 둔 채 뒤 항목만 넣으면 차례가 어긋난 표가 된다: 표 전체를 안 넣는다.
            # 이름으로 짝지어진 항목(_keyed — 표지처럼 행마다 서식의 이름이 박힌 표)은 차례로 선 것이 아니라 그 항목만 건너뛴다(아래의 항목별 까닭으로 — 2026-11-22: 표지 표가 한 행 때문에 통째로 빠졌다)
            row["skipped"] = 1
            out["skipped"].append({"table": tid, "why": "example", "detail": f"{bad[0]['to'][0] + 1}행의 예시 항목을 바꿀 수 없어 표 전체를 넣지 않음 — {bad[1]}"
                                   + ("" if orig else " (목적 문서로 올린 원본이 등록된 빈 양식이 아니라 예시인지 확인할 수 없음)")})
            continue
        for k, (rec, got) in enumerate(recs):
            i = nos[k]
            if isinstance(got, str):
                why = "name" if got.startswith(("이름", "순번")) else "org" if got.startswith("기관") else "shape" if got.startswith("목적 칸 하나") else "occupied"
                out["skipped"].append({"table": tid, "record": i, "why": why, "detail": f"{rec['to'][0] + 1}행 항목 — {got}"})
                continue
            writes, clears, marks_, example, ext = got
            lines = _mark_ops(tv, ext, marks_, mk, others, example)
            out["notes"] += [{"table": tid, "record": i, "why": "renamed", "detail": f"{rec['to'][0] + 1}행 항목 — 이름이 다른 항목을 같은 항목으로 이음({x}) · 이름은 서식 것 그대로"} for x in dict.fromkeys(said[k])]
            row["records"] += 1
            out["cells"] += [{"to": w["to"], "from": w["from"], "text": w["text"], "table": tid, "mode": w["mode"], "was": w["was"]} for w in writes]
            out["clears"] += [{"to": x["id"], "was": x["text"], "table": tid} for x in clears]
            out["lines"] += [{**ln, "table": tid} for ln in lines]
            row["cells"] += len(writes)
            row["cleared"] += len(clears)
            row["lines"] += len(lines)
        if row["records"]:   # 여러 항목에 걸친 자리표시 머리 칸(지원·부담계획의 「단계 n」 · 「연차 n」) — 그 칸에 걸린 항목들의 원본 값이 모두 같으면 한 번 적는다(항목 하나의 칸이 아니라 _record 가 못 쓴다)
            wrote = {c["to"] for c in out["cells"]}
            for cid, items in outer.items():
                texts = {P._ws(sc["text"]) for _, sc in items if not MT._empty(sc["text"])}
                tc, sc = items[0]
                if len(texts) == 1 and cid not in wrote and (text := next(iter(texts))) != P._ws(tc["text"]):
                    out["cells"].append({"to": cid, "from": sc["id"], "text": text, "table": tid, "mode": "slot", "was": tc["text"]})
                    row["cells"] += 1
        nth = Counter()   # 본뜰 묶음(첫 행) → 지금까지 늘린 수 — 늘린 묶음의 순번은 본뜬 묶음의 순번에서 이어 센다(못 늘린 것은 안 센다)
        for i, rec in enumerate(m.get("grow") or ()):
            got = _record(T, F, tv, fv, m, rec, mk, orig, new=True, seq=nth[rec["like"][0]] + 1)
            if isinstance(got, str):
                out["skipped"].append({"table": tid, "grow": i, "why": "shape", "detail": f"늘릴 항목(원본 {rec['from'][0] + 1}행) — {got}"})
                continue
            nth[rec["like"][0]] += 1
            writes, _, marks_, _, _ = got
            out["rows"].append({"table": tid, "like": [rec["like"][0], rec["like"][-1]], "n": len(rec["like"]), "index": i, "from": rec["from"],
                                "cells": [{"at": list(w["to"]), "from": w["from"], "text": w["text"]} for w in writes],
                                "marks": [[col, has] for col, has in marks_], "mark": mk})
            row["records"] += 1
            row["rows"] += 1
            row["cells"] += len(writes)
        row["skipped"] = len(out["skipped"]) - n0
    # 한 항목이 「남은 예시」 로 지우려는 칸을 다른 항목이 쓰면 지우지 않는다 — 이름 칸 하나에 두 행이 걸린 항목(표지의 기술분류 2행)을 행마다 따로 짝지으면 서로의 행을 예시로 지웠다(쓴 글이 반영 끝에 지워짐 — 2026-11-22)
    written = {c["to"] for c in out["cells"]}
    for t in out["tables"]:
        t["cleared"] -= sum(1 for c in out["clears"] if c["table"] == t["to"] and c["to"] in written)
    out["clears"] = [c for c in out["clears"] if c["to"] not in written]
    why = Counter(s["why"] for s in out["skipped"])
    out["counts"] = {"tables": len(out["owned"]), "stale": sum(t["stale"] for t in out["tables"]), "records": sum(t["records"] for t in out["tables"]), "cells": len(out["cells"]) + sum(len(r["cells"]) for r in out["rows"]),
                     "lines": len(out["lines"]), "rows": len(out["rows"]), "cleared": len(out["clears"]), "renamed": len(out["notes"]), "skipped": {k: why.get(k, 0) for k in WHY}}
    out["todo"] = len(out["cells"]) + len(out["clears"]) + len(out["lines"]) + len(out["rows"])
    return out


# ---- 반영 ----------------------------------------------------------------------------------------------------

def apply(to_doc, from_doc, plan):
    """계획을 목적 문서에(모듈 설명) → {"filled", "shaped", "lines", "rowsAdded", "cleared", "skipped", "grown": {표 id: [[늘린 행 번호 …] — grow 차례]}}.
    차례 = 행 늘리기(빈 묶음을 본뜸 — 글을 쓰기 전에) → 칸 글 → 예시 지움 → 선. 칸은 **지금** 계획 때 글 그대로일 때만 쓴다."""
    filled, shaped, lined, cleared, added, skipped, grown = 0, 0, 0, 0, 0, [], defaultdict(list)
    to_doc.blocks()
    fit = []
    last = {}   # (표, 본뜰 첫 행) → 바로 앞에 늘린 묶음의 [(행 차례, 열) → 칸 id] · 그 묶음의 첫 행 — 같은 묶음을 여러 번 본뜨면 차례로 아래에
    for r in plan.get("rows") or ():
        tb = to_doc.table_block(r["table"]) or {"cells": []}
        key = (r["table"], r["like"][0])
        base, a0 = last.get(key) or ({(c["row"] - r["like"][0], c["col"]): c["id"] for c in tb["cells"] if r["like"][0] <= c["row"] <= r["like"][1]}, r["like"][0])
        try:
            m = to_doc.clone_rows(r["table"], a0, a0 + r["n"] - 1, keep_text=True)["map"]
        except (ValueError, KeyError) as x:
            skipped.append({"table": r["table"], "why": "shape", "detail": f"행을 늘릴 수 없음 — {x}"})
            continue
        new = {k: m[i] for k, i in base.items() if i in m}
        last[key] = (new, a0 + r["n"])
        grown[r["table"]].append({"index": r.get("index"), "rows": list(range(a0 + r["n"], a0 + 2 * r["n"]))})
        added += 1
        for c in r["cells"]:
            cid = new.get(tuple(c["at"]))
            if cid is None:
                continue
            try:
                to_doc.set_text(cid, c["text"])
                filled += 1
                fit.append((cid, c.get("from")))
            except ValueError as x:
                skipped.append({"to": cid, "why": "shape", "detail": str(x)})
        mk = r.get("mark")
        for col, has in r.get("marks") or ():
            line = {k: mk[k] for k in ("type", "width", "color")} if has else mk["off"]
            for off, edge in ((mk["boundary"], "bottom"), (mk["boundary"] + 1, "top")):
                cid = new.get((off, col))
                if cid is not None:
                    lined += bool(to_doc.set_cell_edges(cid, {edge: line}))
    now = {}

    def text_of(tid, cid):
        if tid not in now:
            now[tid] = {c["id"]: c.get("text") or "" for c in (to_doc.table_block(tid) or {}).get("cells") or ()}
        return now[tid].get(cid)
    for c in plan.get("cells") or ():
        cur = text_of(c["table"], c["to"])
        if cur is None or P._ws(cur) != P._ws(c["was"]):
            if cur is None or P._ws(cur) != P._ws(c["text"]):
                skipped.append({"to": c["to"], "why": "occupied", "detail": "계획 뒤 목적 칸의 글이 바뀜"})
            continue
        try:
            to_doc.set_text(c["to"], c["text"])
            filled += 1
            fit.append((c["to"], c.get("from")))
        except ValueError as x:
            skipped.append({"to": c["to"], "why": "shape", "detail": str(x)})
    for c in plan.get("clears") or ():
        if P._ws(text_of(c["table"], c["to"]) or "") == P._ws(c["was"]):
            try:
                to_doc.set_text(c["to"], "")
                cleared += 1
            except ValueError as x:
                skipped.append({"to": c["to"], "why": "shape", "detail": str(x)})
    edges = defaultdict(dict)
    for ln in plan.get("lines") or ():
        edges[ln["to"]][ln["edge"]] = ln["line"]
    for cid, e in edges.items():
        try:
            lined += len(e) if to_doc.set_cell_edges(cid, e) else 0
        except (ValueError, KeyError) as x:
            skipped.append({"to": cid, "why": "shape", "detail": str(x)})
    shaped = sum(MT._shape(to_doc, from_doc, to, frm) for to, frm in fit)
    return {"filled": filled, "shaped": shaped, "lines": lined, "rowsAdded": added, "cleared": cleared, "skipped": skipped, "grown": dict(grown)}


def settle(m, grown, block):
    """반영 뒤 저장할 대응 — 늘린 묶음을 records 로 옮기고(다시 계획하면 그 행들을 본다) 구조 서명을 지금 표로 새로 적는다. grown = apply 의 그 표 몫, block = 반영 뒤의 표 블록."""
    done = {g["index"]: g["rows"] for g in grown or ()}
    recs = list(m.get("records") or ()) + [{"to": [done[i][r - g["like"][0]] for r in g.get("to") or g["like"]], "from": g["from"], "example": False}
                                             for i, g in enumerate(m.get("grow") or ()) if i in done]
    return {**m, "records": recs, "grow": [g for i, g in enumerate(m.get("grow") or ()) if i not in done], "sig": {**(m.get("sig") or {}), "to": sig(block, (m.get("top") or {}).get("to", 0))}}
