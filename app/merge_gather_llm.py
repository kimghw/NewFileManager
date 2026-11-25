"""취합 — LLM 순회 검토(spec_취합 ② §4-3): 스크립트가 넣기로 한 **기관 작성 내용**(hunk — status ready)을 넣기 전에 LLM 이 차례로 돌며 문단·표의 특성을 살핀다.

권한은 **좁히는 쪽뿐**(astra 협의 2026-11-12 「LLM의 권한」): `ready` → keep(유지)·skip(제외)·check(확인 필요). 스크립트가 막은 상태(overlap·otherOrg·unknownPlace·structure …)를
넣게 하지 못하고, 표를 넣는 방식(칸 ↔ 행)은 reason 에 의견으로만 남는다. 사람이 고른 것(decision.source user)은 보내지도 않는다. 글을 쓰지 않는다.
흐름(merge_llm.review 와 같은 길): prepare() 가 자료를 만들고(두 문서의 blocks 를 읽는 것은 여기까지 — LLM 은 안 부름) → run() 이 단위마다 한 호출로 병렬(llm.ask_all · Opus)
→ check() 가 답을 **보낸 자료에 대고** 검증한다. review() = 둘을 이어 부른 것.
- 단위 = 취합본의 장(`merge_chunks.units` — 20쪽 안) + 글자 수 상한(UNIT_CHARS): 한 장의 작성 내용이 상한을 넘으면 문서 순으로 이어 담아 호출을 더 나눈다 —
  **작성 내용 하나(딸린 표 포함)는 호출 사이에서 쪼개지 않는다**(혼자 상한을 넘으면 혼자 한 호출).
- 작성 내용마다 바뀐 내용 **전체**를 보낸다. 하나가 HUNK_CHARS 를 넘으면 줄 단위로 줄이고 「…(생략 n줄 · m자)」 를 남긴다 — 그런 것의 「제외」 는 받지 않는다(못 본 부분이 있다).
- 답이 안 온 단위(실패·시간 초과·빈 답)와 답에 빠진 작성 내용은 「검토함」 이 아니라 check + held(보류).
- inputHash = 보낸 자료(줄이기 전 전체)의 지문 — 답이 그 자료에 대한 것인지 가리고, 저장한 결정이 지금 자료의 것인지도 이것으로 본다(`hashes`).
- 프롬프트 = 계약(CONTRACT — 코드) + 판단 지침(`merge_guides` gather — app/merge_guides_default/gather.md) + 할 일 프롬프트(jobs/plan_merge.md) + 자료(JSON)."""
import hashlib
import json
from collections import Counter, defaultdict

from app import prompt_texts
from app import job_prompts, llm, merge_chunks, merge_guides, merge_llm
from app.division_llm import _short

MODEL = merge_llm.MODEL   # 이관 검토와 같은 모델(Opus — llm.call 의 model 이 env NFM_LLM_MODEL 보다 먼저)
GUIDE = "gather"          # merge_guides 의 지침 이름
NATURES = ("내용", "안내", "빈 틀", "서식만", "자리 이상", "복합", "모름")
VERDICT = {"유지": "keep", "제외": "skip", "확인 필요": "check"}
SKIPPABLE = ("안내", "빈 틀", "서식만")   # 「제외」 를 받는 성격 — 내용이 아님이 분명한 것만
TARGET, OPINION = ("ready",), ("overlap", "unknownPlace")   # 판정을 받는 상태 · 의견만 받는 상태(그 밖의 상태는 안 보냄)

S = {"type": "string"}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["reviews", "summary"], "properties": {
    "reviews": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "inputHash", "nature", "verdict", "reason"],
                                           "properties": {"id": S, "inputHash": S, "nature": {"type": "string", "enum": list(NATURES)},
                                                          "verdict": {"type": "string", "enum": list(VERDICT)}, "reason": S}}},
    "summary": S}}

CONTRACT = """당신은 여러 기관이 나눠 쓴 국가R&D 사업계획서(연구개발계획서)를 **취합본** 하나에 모을 때, 스크립트가 넣기로 한 **기관 작성 내용**을 넣기 전에 하나씩 살피는 검토자입니다.
글을 쓰거나 고치지 않고 자리를 옮기지도 않습니다 — 작성 내용마다 **성격과 판정만** 답합니다. 무엇을 내용으로 보고 무엇을 빼는지는 아래 「판단 지침」 을 따릅니다.

### 무엇을 보는가
기관 문서 = 나눠 준 **배포 기준본**(취합본의 틀 그대로 — 기관·차년도 자리가 모두 든 빈 양식)을 기관이 받아 자기 몫만 채워 돌려준 문서입니다. 스크립트가 기준본과 기관 문서를 견줘
달라진 덩어리를 기관 작성 내용(hunks)으로 뽑았고, 취합본의 같은 자리가 기준본 그대로일 때만 넣기로 했습니다(status ready). 넣는 일은 스크립트가 합니다(기관 문서의 그 블록을 취합본의
그 자리에 복사 · 표 칸 글 · 늘린 표 행). 당신은 그 가운데 **넣지 말아야 할 것과 사람이 봐야 할 것**을 가려냅니다.

### 자료
doc = {part: 기관 문서 이름, orgs: 과제의 기관 [{name, role}], assigned: 이 기관 문서에서 가져오기로 사람이 지정한 기관(있을 때)} ·
chapter = 이 검토 단위(취합본의 장 — title · pages(추정 쪽 [첫 쪽, 끝 쪽]) · piece([몇째, 모두 몇] — 장이 길어 나눠 보낼 때)). hunks 는 **이 단위의 것만**입니다.
hunks[] — 작성 내용 하나:
- id · inputHash = 답에 **글자 그대로** 돌려줄 값.
- review: true = 판정을 받는 것(스크립트가 넣기로 한 것) · false = **의견만**(스크립트가 넣지 않기로 한 것 — status overlap = 취합본의 그 자리에 이미 다른 내용이 있음 ·
  unknownPlace = 자리가 하나로 정해지지 않음. 무엇이라 답해도 넣게 되지 않습니다).
- kind: added = 기준본에 없던 블록(문단·표·그림)이 끼어듦 · filled = 기준본의 자리표시 줄이 글로 바뀜 · cells = 같은 표의 칸 글이 바뀜 · rows = 이어 넣는 표에 행이 늘어남.
- status = 스크립트 판정 · detail = 스크립트가 붙인 설명 · path = 소속(그 자리를 품은 제목 사슬, 바깥 → 안) ·
  scope = 그 자리의 구분 기준 값 {kind: common(기관이 갈리지 않는 공통 자리) · org(특정 기관의 자리) · unknown, org: 기관 이름, year: 차년도, stage: 단계}.
- place = 취합본에서 들어갈 자리: before·after = 앞·뒤 경계 줄 [갈래, 글](두 문서에서 맞은 줄 — 내용은 이 둘 사이에 들어갑니다) · frame = 기준본에서 그 사이에 있던 줄 [[갈래, 글] …] ·
  now = 지금 취합본의 그 사이 줄("same" = 기준본 그대로) · unique = 자리가 하나로 정해진 근거 · level = 그 자리를 품은 제목 줄의 {letter 레터, level 개요레벨, role, text}.
  갈래: title 양식의 제목 줄 · label 구분 라벨 · guide 자리표시 줄·빈 줄·「※」 안내 줄 · fixed 그 밖의 양식 글 · table 표 · pic 그림(지금 취합본의 줄은 p 문단 · table · pic).
- content = **기관이 쓴 내용 전체**(문서 순 줄 목록). 줄의 꼴:
  {p: 문단 글, letter·level: 그 문단의 레터·개요레벨(헤딩 추출 결과가 있을 때), role: heading 개요 줄 · subtitle 소제목 · label 구분 라벨 · title 제목(본문 줄이면 없음)} ·
  {caption: 표·그림 캡션 글} · {table: "행×열", nested: 칸 안에 표·그림이 있음} 와 그 뒤로 이어지는 {row: 그 표의 한 행 — 칸 글을 「 | 」 로 이음} · {picture: 그림(크기)} ·
  kind cells 면 {r, c: 행·열(0부터), text: 기관이 쓴 칸 글, was: 기준본의 칸 글, now: 지금 취합본의 칸 글(기준본과 다를 때만), cls: 칸의 역할, row·col: 그 칸의 행 머리·열 머리 글, object: 칸 안에 표·그림} ·
  kind rows 면 {r: 기관 문서 표에서의 행, cells: [칸 글 …]}.
  개요레벨(level)은 템플릿 안 레벨이라 서브 템플릿에서는 1부터 다시 셉니다 — 레터 꼴과 함께 보십시오.
  너무 길어 줄인 곳(또는 글을 읽지 못한 블록)은 {omitted: "…(생략 n줄 · m자)"} 줄이나 글 안의 「…(생략 n자)…」 로 표시되고, 그 작성 내용에 omitted(줄인 양)가 실립니다 — **못 본 부분이 있다**는 뜻입니다.
- table(kind cells·rows — 그 표의 기준본 정보): size "행×열" · list(이어 넣는 표인가) · merged(병합 칸 수) · roles{head 머리 칸 · input 적는 칸 · calc 계산 칸 · complex 칸 안에 표·그림 — 칸 수} ·
  heads = 머리 행의 글 · title = 표 바로 앞 줄 · rowsNow = 지금 취합본 그 표의 행 수(기준본과 다를 때 — 다른 기관 문서가 먼저 행을 넣음).
- objects = 딸린 것의 수 {paragraphs, tables, pictures, cells, rows} — 표·그림이 있으면 글만이 아니라 그 개체도 함께 들어갑니다(그림 속은 볼 수 없습니다).

### 답
reviews: hunks 마다 한 줄 — {id, inputHash, nature, verdict, reason}. summary = 이 단위 전체 판단 두세 문장.
- nature(성격): 내용 = 기관이 쓴 실제 내용 · 안내 = 양식의 안내 글·작성요령·예시 · 빈 틀 = 글 없이 틀(글머리·빈 줄·빈 표·빈 칸)만 · 서식만 = 글은 기준본과 같고 빈칸·줄 나눔·글자 모양만 다름 ·
  자리 이상 = 내용이지만 이 자리(기관·차년도·절)의 것이 아닌 듯함 · 복합 = 위 여럿이 섞임 · 모름.
- verdict(판정): 유지 = 그대로 넣는다 · 제외 = 넣지 않는다 · 확인 필요 = 사람이 보고 정한다.
- **권한은 좁히는 쪽뿐입니다.** 코드가 받는 짝은 둘 — 유지 ← 성격이 내용 · 제외 ← 성격이 안내·빈 틀·서식만이고 omitted 가 없을 때. 그 밖(자리 이상·복합·모름 · 어긋난 짝 · 못 본 부분이 있는 제외)은
  모두 **확인 필요**로 바뀝니다. review 가 false 인 것은 무엇이라 답해도 넣지 않습니다(의견으로만 남습니다).
  스크립트가 정한 자리와 넣는 방식은 바꾸지 못합니다 — 「칸이 아니라 행으로 넣어야 한다」 같은 생각은 reason 에 적고 verdict 는 확인 필요로 합니다.
- id·inputHash 는 **입력에 있는 것만**, 작성 내용마다 한 번. 입력에 없는 id · 다른 inputHash 의 답은 버려지고, 답이 없는 작성 내용은 「검토함」 이 아니라 보류(확인 필요)가 됩니다.
- **글을 쓰지 않습니다.** 고친 글·대신 넣을 글·요약을 내지 않습니다. reason = 그렇게 본 근거 한 문장(한국어 — 어느 줄·어느 칸·어느 기관·차년도를 보고).
- **확신이 없으면 확인 필요**입니다(실제 내용을 빼는 것도, 넣지 말 것을 넣는 것도 잘못입니다 — 사람이 보면 됩니다)."""

# 지침 파일이 없을 때(끔·지움)만 붙는 최소 기준 — 지침의 원본은 app/merge_guides_default/gather.md(merge_guides).
FALLBACK_GUIDE = """

## 판단 기준(지침 파일 없음 — 기본)
- 넣는 것 = 기관이 쓴 내용(글 · 표 칸 · 늘린 표 행 · 그림). 넣지 않는 것 = 기준본에 원래 있던 것(제목 줄 · 빈 틀 · 안내 글 · 작성요령)과 서식만 바뀐 것.
- 내용과 안내·빈 틀이 한 작성 내용에 섞였으면 복합 — 실제 내용이 들어 있을 수 있으므로 제외하지 않고 확인 필요.
- 글이 말하는 기관·차년도가 그 자리(scope)와 다르면 자리 이상 — 확인 필요."""

# 지침 절의 머리 문장(merge_guides.NOTE 는 자리 연결 검토의 말이라 이 검토의 것으로).
GUIDE_NOTE = ("아래는 이 검토의 **판단 기준**입니다(사용자가 관리하는 지침). 무엇을 기관이 쓴 내용으로 보고 무엇을 안내 글·빈 틀·서식만 바뀐 것으로 보는지, 문단과 표에서 무엇을 살피는지는 이 글을 따릅니다. "
              "답의 꼴 · 권한(좁히는 쪽만) · 「입력에 있는 id 만」 은 위 계약 그대로입니다.")

# 글자 수 상한(JSON 길이 — 한글 한 자를 한 자로 센다): 호출 하나의 작성 내용 합 · 작성 내용 하나의 내용 줄 합(같은 값 — 혼자 한 호출을 채우는 작성 내용까지는 줄이지 않고 통째로 보낸다).
# 자리 줄(앞뒤 경계·기준본·취합본)은 참고라 짧게 싣는다. 계약·지침·할 일 프롬프트(약 9천 자)는 이 셈 밖.
UNIT_CHARS, HUNK_CHARS, LINE_MIN = 40_000, 40_000, 400
PLACE_MAX, PLACE_LINES, PLACE_LEN = 60, 12, 300      # 경계 사이 블록이 이보다 많으면 자리가 아니라 구간(안 실음) · 싣는 줄 수 · 줄 길이
HEAD_ROWS, HEAD_LEN, HEAD_PATH, LOOKBACK = 4, 30, 4, 40   # 표 머리 행 수 · 머리 칸 글 길이 · 칸마다 머리 사슬 길이 · 자리의 제목 줄을 찾아 올라가는 블록 수
WHOLE = {"title": "문서 전체", "start": 0, "end": 0, "pages": [1, 1], "over": False}   # 취합본 블록이 없을 때(시험)의 한 단위


def _size(x):
    return len(json.dumps(x, ensure_ascii=False, separators=(",", ":")))


def _flat(text):
    return " ".join((text or "").split())


def _by_id(blocks):
    """블록 id · 표 칸 id(칸 안 블록까지) → 그 사전."""
    out = {}

    def walk(lst):
        for b in lst:
            out[b.get("id")] = b
            for c in b.get("cells") or ():
                out[c.get("id")] = c
                walk(c.get("blocks") or [])
    walk(blocks or [])
    return out


def _nodes(graph):
    """2단계 그래프 → 문단 id 마다 첫 노드(레터·개요레벨·역할을 읽는다)."""
    out = {}
    for n in sorted((graph or {}).get("nodes") or (), key=lambda n: n.get("n", 0)):
        if n.get("para") is not None:
            out.setdefault(n["para"], n)
    return out


def _outline(n):
    """그래프 노드 → {letter, level, role(제목 줄 갈래일 때만)} — 없는 것은 뺀다."""
    if not n:
        return {}
    return {**({"letter": n["letter"]} if n.get("letter") else {}), **({"level": n["level"]} if n.get("level") is not None else {}),
            **({"role": n["role"]} if n.get("role") in merge_chunks.HEADS else {})}


def _context(frame, to, part):
    """자료를 만들 때 쓰는 찾기표 — 기준본 블록 차례 · 취합본 블록(자리·사전) · 기관 문서 블록 사전 · 두 문서의 그래프 노드."""
    fb = list((frame or {}).get("blocks") or [])
    tb = (to or {}).get("blocks") or []
    return {"fblocks": fb, "frame": {b.get("id"): k for k, b in enumerate(fb)}, "at": merge_chunks.index(tb), "to": _by_id(tb),
            "part": _by_id((part or {}).get("blocks")), "nodes": _nodes((part or {}).get("graph")), "tnodes": _nodes((to or {}).get("graph"))}


# ---- 작성 내용 하나 → 보낼 꼴 ---------------------------------------------------------------

def _block_lines(b, nodes):
    """기관 문서 블록 하나 → 내용 줄(계약의 content 줄 꼴). 표는 머리 줄 하나 + 행마다 한 줄."""
    t = b.get("type")
    if t == "table":
        rows = defaultdict(list)
        for c in b.get("cells") or ():
            rows[c.get("row", 0)].append(c)
        nested = any(x.get("type") in ("table", "image") for c in b.get("cells") or () for x in c.get("blocks") or ())
        size = f"{b.get('nRows') or len(rows)}×{b.get('nCols') or max((len(v) for v in rows.values()), default=0)}"
        return [{"table": size, **({"nested": True} if nested else {})},
                *({"row": " | ".join(_flat(c.get("text")) for c in sorted(rows[r], key=lambda c: c.get("col", 0)))} for r in sorted(rows))]
    if t == "image":
        w, h = b.get("widthMm"), b.get("heightMm")
        return [{"picture": f"{w:g}×{h:g}mm" if w and h else "그림"}]
    if b.get("captionOf"):
        return [{"caption": b.get("text") or ""}]
    return [{"p": b.get("text") or "", **_outline(nodes.get(b.get("id")))}]


def _span(c, a, n):
    """기준본 표 칸 c 가 축 a(r|c)에서 덮는 범위 (처음, 끝 — 끝 제외)."""
    return c.get(a, 0), c.get(a, 0) + (c.get(n) or 1)


def _cell_at(cells, r, k):
    return next((c for c in cells if _span(c, "r", "rs")[0] <= r < _span(c, "r", "rs")[1] and _span(c, "c", "cs")[0] <= k < _span(c, "c", "cs")[1]), None)


def _heads(cells, r, k):
    """그 칸의 (행 머리 글, 열 머리 글) — 같은 행의 왼쪽 · 같은 열의 위쪽 머리 칸(cls head)의 글을 바깥 → 안으로 「 › 」."""
    row = [c for c in cells if c.get("cls") == "head" and _span(c, "r", "rs")[0] <= r < _span(c, "r", "rs")[1] and _span(c, "c", "cs")[1] <= k]
    col = [c for c in cells if c.get("cls") == "head" and _span(c, "c", "cs")[0] <= k < _span(c, "c", "cs")[1] and _span(c, "r", "rs")[1] <= r]

    def join(cs, a):
        return " › ".join(list(dict.fromkeys(t for c in sorted(cs, key=lambda c: c.get(a, 0)) if (t := _short(c.get("text"), HEAD_LEN))))[-HEAD_PATH:])
    return join(row, "c"), join(col, "r")


def _table_info(fb, cx, to_table):
    """기준본의 표 블록 → 계약의 table 꼴(격자·병합·칸 역할·이어 넣는 표인지·머리 행·표 제목)."""
    ft = fb.get("table") or {}
    cells = ft.get("cells") or []
    rows = defaultdict(list)
    for c in cells:
        rows[c.get("r", 0)].append(c)
    heads = [" | ".join(_short(c.get("text"), HEAD_LEN) for c in sorted(rows[r], key=lambda c: c.get("c", 0)))
             for r in sorted(rows) if all(c.get("cls") == "head" for c in rows[r])][:HEAD_ROWS]
    k = cx["frame"].get(fb.get("id"), 0)
    before = cx["fblocks"][k - 1] if k else None
    out = {"size": f"{ft.get('rows') or len(rows)}×{ft.get('cols') or 0}", "list": bool(ft.get("list")),
           "merged": sum(1 for c in cells if (c.get("rs") or 1) > 1 or (c.get("cs") or 1) > 1),
           "roles": dict(Counter(c.get("cls") or "input" for c in cells)), "heads": heads}
    if before is not None and before.get("kind") == "p" and (before.get("text") or "").strip():
        out["title"] = _short(before["text"], PLACE_LEN)
    if to_table and ft.get("rows") and to_table.get("nRows") not in (None, ft["rows"]):
        out["rowsNow"] = to_table["nRows"]
    return out


def _between(lst, a, z):
    """목록에서 a 뒤부터 z 앞까지(둘 다 제외) — a·z = 차례 | None(목록의 처음·끝). 너무 많으면 자리가 아니라 구간이므로 None."""
    seg = lst[(0 if a is None else a + 1):(len(lst) if z is None else z)]
    return seg if len(seg) <= PLACE_MAX else None


def _now_line(b):
    if b.get("type") == "table":
        return ["table", f"{b.get('nRows')}×{b.get('nCols')} " + " | ".join(_short(c.get("text"), HEAD_LEN) for c in (b.get("cells") or ()) if c.get("row", 0) == 0)]
    return ["pic", ""] if b.get("type") == "image" else ["p", b.get("text") or ""]


def _place(h, cx, table):
    """그 작성 내용이 취합본에서 들어갈 자리 — 앞·뒤 경계 줄, 기준본에서 그 사이에 있던 줄, 지금 취합본의 그 사이 줄(기준본 그대로면 "same"), 자리 근거, 그 자리를 품은 제목 줄."""
    base, to = h.get("base") or {}, h.get("to") or {}
    fb, fi, at = cx["fblocks"], cx["frame"], cx["at"]
    out = {}
    for name, key in (("before", "prev"), ("after", "next")):
        if base.get(key) in fi:
            b = fb[fi[base[key]]]
            out[name] = [b.get("cls") or b.get("kind") or "", b.get("text") or ""]
        elif to.get(key) in cx["to"]:
            out[name] = _now_line(cx["to"][to[key]])
    ends = lambda d, known: all(d.get(k) is None or d.get(k) in known for k in ("prev", "next")) and any(d.get(k) is not None for k in ("prev", "next"))  # noqa: E731
    was = now = None
    if not table:   # 표 칸·표 행은 그 표가 자리다(칸마다 was·now 를 싣는다)
        if ends(base, fi):
            was = _between(fb, fi.get(base.get("prev")), fi.get(base.get("next")))
        if was is None and base.get("ids"):
            was = [fb[fi[i]] for i in base["ids"] if i in fi]
        p, n = at.get(to.get("prev")), at.get(to.get("next"))
        lst = (p or n or (0, None, 0))[1]
        if ends(to, at) and lst is not None and all(x is None or x[1] is lst for x in (p, n)):
            now = _between(lst, p[2] if p else None, n[2] if n else None)
    if was is not None:
        out["frame"] = [[b.get("cls") or b.get("kind") or "", b.get("text") or ""] for b in was]
    if now is not None:
        same = was is not None and [b.get("id") for b in now] == [b.get("id") for b in was] and all(
            _flat(a.get("text")) == _flat(b.get("text")) for a, b in zip(now, was) if a.get("type") == "paragraph")
        out["now"] = "same" if same else [_now_line(b) for b in now]
    if h.get("unique"):
        out["unique"] = str(h["unique"])
    hit = at.get(to.get("prev")) or at.get(base.get("prev")) or at.get(base.get("table")) or at.get(to.get("next"))
    if hit and hit[1] is not None:   # 그 자리를 품은 제목 줄 — 앞 경계부터 거슬러 올라가 처음 만나는 제목 갈래 줄
        for b in reversed(hit[1][max(0, hit[2] - LOOKBACK + 1):hit[2] + 1]):
            n = cx["tnodes"].get(b.get("id"))
            if n and n.get("role") in merge_chunks.HEADS and not n.get("blank"):
                out["level"] = {**_outline(n), "text": _short(b.get("text"), 40)}
                break
    return out


def _content(h, cx, fb_table):
    """기관이 쓴 내용 전체 → (줄들, 기관 문서에서 못 찾은 블록 수). from.ids = 블록(문단·표·그림) · from.cells = 바뀐 칸 · from.rows = 늘어난 행."""
    base, frm = h.get("base") or {}, h.get("from") or {}
    lines, lost = [], 0
    for i in frm.get("ids") or ():
        b = cx["part"].get(i)
        if b is None:
            lost += 1
        else:
            lines += _block_lines(b, cx["nodes"])
    tcells = ((fb_table or {}).get("table") or {}).get("cells") or []
    by = {c.get("id"): c for c in tcells}
    now = {(c.get("row"), c.get("col")): c.get("text") or "" for c in (cx["to"].get(base.get("table")) or {}).get("cells") or ()}
    for c in frm.get("cells") or ():
        r, k = c.get("r"), c.get("c")
        if c.get("to") is not None:   # 엔진이 싣는 기준본(= 취합본) 칸 id — r·c 는 **기관 문서의 자리**라 행이 늘어난 표에서는 기준본의 그 칸이 아니다(머리 글·역할·지금 글이 다른 행 것으로 나갔다)
            fc, tc = by.get(c["to"]), cx["to"].get(c["to"])
            r, k = (fc.get("r"), fc.get("c")) if fc else (r, k)   # 싣는 r·c 도 기준본의 자리로(table.size · 머리 글과 같은 격자)
            cur = (tc.get("text") or "") if tc is not None else None   # 지금 취합본의 그 칸(칸 id 로 — 먼저 넣은 행이 있어도 같은 칸)
        else:
            fc = by.get(c.get("base")) if isinstance(c.get("base"), str) and c["base"] in by else _cell_at(tcells, r, k) if r is not None and k is not None else None
            cur = now.get((r, k))
        pc = cx["part"].get(c.get("id")) or {}
        was = (fc.get("text") or "") if fc else c["base"] if isinstance(c.get("base"), str) else ""   # base = 기준본 칸 글(칸 id 로 와도 받는다)
        row, col = _heads(tcells, r, k) if r is not None and k is not None and (fc or {}).get("cls") != "head" else ("", "")   # 머리 칸 자신에게는 머리 사슬을 안 붙인다
        ln = {"r": r, "c": k, "text": c["text"] if c.get("text") is not None else pc.get("text") or "", "was": was}
        if cur is not None and _flat(cur) != _flat(was):
            ln["now"] = cur
        ln.update({k_: v for k_, v in (("cls", (fc or {}).get("cls")), ("row", row), ("col", col)) if v})
        if any(x.get("type") in ("table", "image") for x in pc.get("blocks") or ()):
            ln["object"] = True
        lines.append(ln)
    lines += [{"r": r.get("r"), "cells": [str(x) if x is not None else "" for x in r.get("cells") or ()]} for r in frm.get("rows") or ()]
    if not lines and h.get("text"):   # 내용을 하나도 못 모음 — 스크립트가 낸 앞부분만(못 본 부분이 있는 것으로 센다)
        lines, lost = [{"p": str(h["text"])}], lost + 1
    return lines, lost


def _entry(h, cx):
    """작성 내용 하나 → 보낼 자료 **전체**(줄이기 전 — id·inputHash 빼고). 이것의 지문이 inputHash."""
    base, sc = h.get("base") or {}, h.get("scope") or {}
    fb_table = cx["fblocks"][cx["frame"][base["table"]]] if base.get("table") in cx["frame"] else None
    table = h.get("kind") in ("cells", "rows")
    e = {"review": h.get("status") in TARGET, "kind": h.get("kind"), "status": h.get("status")}
    if h.get("detail"):
        e["detail"] = str(h["detail"])
    e["path"] = [str(p) for p in h.get("path") or ()]
    e["scope"] = {k: v for k, v in (("kind", sc.get("kind")), ("org", sc.get("orgName") or sc.get("org")), ("year", sc.get("year")), ("stage", sc.get("stage"))) if v is not None}
    e["place"] = _place(h, cx, table)
    e["content"], lost = _content(h, cx, fb_table)
    if lost:
        e["content"].append({"omitted": f"…(기관 문서에서 블록 {lost}개의 글을 읽지 못함)"})
        e["omitted"] = lost
    if table and fb_table is not None:
        e["table"] = _table_info(fb_table, cx, cx["to"].get(base["table"]))
    counts = {k: v for k, v in (h.get("counts") or {}).items() if v}
    if not counts:
        counts = {k: v for k, v in (("tables", sum("table" in x for x in e["content"])), ("pictures", sum("picture" in x for x in e["content"]))) if v}
    if counts:
        e["objects"] = counts
    return e


def _hash(entry):
    return hashlib.sha1(json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]


def _cut(text, cap):
    """글 하나를 cap 자 안으로 — 앞 2/3 · 뒤 1/3 을 남기고 사이에 「…(생략 n자)…」 → (글, 줄인 글자 수)."""
    text = text or ""
    if len(text) <= cap:
        return text, 0
    a = cap * 2 // 3
    return f"{text[:a]}…(생략 {len(text) - cap}자)…{text[len(text) - (cap - a):]}", len(text) - cap


def _trim(x, cap):
    """줄 하나(사전·목록·글) 안의 긴 글을 cap 자로 → (줄인 것, 줄인 글자 수)."""
    if isinstance(x, str):
        return _cut(x, cap)
    if isinstance(x, list):
        got = [_trim(v, cap) for v in x]
        return [g[0] for g in got], sum(g[1] for g in got)
    if isinstance(x, dict):
        got = {k: _trim(v, cap) for k, v in x.items()}
        return {k: g[0] for k, g in got.items()}, sum(g[1] for g in got.values())
    return x, 0


def _clip(lines, cap):
    """내용 줄 목록을 cap 자(JSON 길이) 안으로 → (줄들, 줄인 글자 수). 줄 하나가 cap 의 절반을 넘으면 그 줄 안의 긴 글부터 줄이고(「…(생략 n자)…」),
    그래도 넘치면 **줄 단위로** 앞 2/3 · 뒤 1/3 을 남기고 사이에 {omitted: "…(생략 n줄 · m자)"} 한 줄 — 줄(문단 · 표의 행 · 칸)을 말없이 자르지 않는다."""
    if sum(map(_size, lines)) <= cap:
        return lines, 0
    one, out, cut = max(LINE_MIN, cap // 2), [], 0
    for ln in lines:
        if _size(ln) > one:
            ln, n = _trim(ln, max(LINE_MIN // 2, one // 2))
            cut += n
        out.append(ln)
    sizes = [_size(x) for x in out]
    if sum(sizes) <= cap:
        return out, cut
    head = used = 0
    while head < len(out) and (not head or used + sizes[head] <= cap * 2 // 3):
        used += sizes[head]
        head += 1
    tail, used = len(out), 0
    while tail > head and used + sizes[tail - 1] <= cap - cap * 2 // 3:
        tail -= 1
        used += sizes[tail]
    if tail == head:
        return out, cut
    gone = sum(sizes[head:tail])
    return [*out[:head], {"omitted": f"…(생략 {tail - head}줄 · {gone}자)"}, *out[tail:]], cut + gone


def _pairs(lines):
    """자리 줄 [[갈래, 글] …] 을 싣는 꼴로 — PLACE_LINES 줄 · 줄마다 PLACE_LEN 자(참고 자료라 짧게, 줄인 곳은 표시)."""
    out = [[c, _cut(t, PLACE_LEN)[0]] for c, t in lines[:PLACE_LINES]]
    return out + ([["…", f"(생략 {len(lines) - PLACE_LINES}줄)"]] if len(lines) > PLACE_LINES else [])


def _fit(entry, cap):
    """보낼 자료 전체(_entry) → 실제로 보내는 꼴: 내용 줄을 cap 자 안으로(_clip — 줄였으면 omitted 에 글자 수), 자리 줄은 짧게."""
    e = {**entry, "place": dict(entry["place"])}
    for k in ("before", "after"):
        if k in e["place"]:
            e["place"][k] = [e["place"][k][0], _cut(e["place"][k][1], PLACE_LEN)[0]]
    for k in ("frame", "now"):
        if isinstance(e["place"].get(k), list):
            e["place"][k] = _pairs(e["place"][k])
    e["content"], cut = _clip(entry["content"], cap)
    if cut:
        e["omitted"] = entry.get("omitted", 0) + cut
    return e


def hashes(items, frame, to, part):
    """작성 내용 열쇠 → 지금 자료의 inputHash(검토에 보내는 상태 — ready·overlap·unknownPlace — 인 것만). 저장한 LLM 결정의 inputHash 와 다르면 그 결정은 낡은 자료의 것이다."""
    cx = _context(frame, to, part)
    return {h["key"]: _hash(_entry(h, cx)) for h in items or () if h.get("status") in TARGET + OPINION}


# ---- 프롬프트 · 「지침」 보기 ------------------------------------------------------------------

def guide_part(guide=None):
    """프롬프트의 지침 절 — guide = merge_guides.get 꼴(None = 지금의 `gather` 지침을 읽음, False = 지침 없이). 지침 파일이 없으면 최소 기준(FALLBACK_GUIDE)."""
    if guide is False:
        return FALLBACK_GUIDE
    return merge_guides.part(merge_guides.get(GUIDE) if guide is None else guide, GUIDE_NOTE) or FALLBACK_GUIDE


def prompt(payload, job=None, guide=None):
    """프롬프트 글 = 계약 + 판단 지침 절 + 할 일 프롬프트 절 + 자료(JSON)(merge_llm.prompt 와 같은 차례).
    job = 이 작업의 할 일 프롬프트(job_prompts.get 꼴 | None — jobs/plan_merge.md) · guide = 판단 지침(guide_part — 기본은 gather.md 를 부를 때마다 읽음)."""
    return prompt_texts.contract(__name__) + guide_part(guide) + job_prompts.part(job) + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parts(job=None, guide=None):
    """화면의 「지침」 보기에 싣는 것 — 이 검토의 프롬프트를 이루는 글들(자료 빼고) [{key: contract|guide|job, title, text, source, note}]. prompt() 와 같은 차례(merge_llm.parts 와 같은 꼴)."""
    g = merge_guides.get(GUIDE) if guide is None else guide
    out = [{"key": "contract", "title": "계약 — 역할 · 자료 설명 · 답의 꼴 · 권한", "text": prompt_texts.contract(__name__), "source": "app/merge_gather_llm.py",
            "note": "코드에 든 글입니다(답을 검증하는 코드와 한 몸) — 판단 기준은 아래 지침에 있습니다"}]
    if g and merge_guides.body(g):
        out.append({"key": "guide", "title": f"판단 지침 — {g['title']}", "text": merge_guides.body(g), "source": g["path"], "note": "이 파일을 고치면 다음 실행부터 적용됩니다"})
    else:
        out.append({"key": "guide", "title": "판단 지침 — (지침 파일 없음: 기본 기준)", "text": FALLBACK_GUIDE.strip(), "source": "app/merge_gather_llm.py",
                    "note": "app/merge_guides_default/gather.md 가 없어 기본 기준만 보냅니다"})
    if job and job_prompts.part(job):
        out.append({"key": "job", "title": f"할 일 프롬프트 — {job['name']}", "text": job_prompts.body(job["text"]), "source": job["path"],
                    "note": "이 작업의 전제(무엇이 취합본·기관 문서인지, 무엇을 넣고 겹치면 어떻게 하는지) — 이 파일을 고치면 다음 실행부터 적용됩니다"})
    return out


# ---- 답 검증 --------------------------------------------------------------------------------

def _narrow(value, nature, h):
    """LLM 의 판정 → 코드가 받는 값(좁히는 쪽만) (값, 바꾼 까닭 | "")."""
    if value == "keep" and nature != "내용":
        return "check", f"유지는 성격이 「내용」 일 때만 받는다(성격 {nature})"
    if value == "skip" and nature not in SKIPPABLE:
        return "check", f"제외는 성격이 안내·빈 틀·서식만일 때만 받는다(성격 {nature})"
    if value == "skip" and h.get("omitted"):
        return "check", "내용을 다 보지 못하고 낸 제외(자료를 줄여 보냄)"
    return value, ""


def check(payload, answer):
    """응답(호출의 data)을 **보낸 자료에 대고** 검증 → {"decisions": {id: {"value": keep|skip|check, "source": "llm", "nature", "reason", "inputHash"[, "note"]}} — 판정 대상(review true)만,
    "opinions": {id: {"verdict", "nature", "reason", "inputHash"}} — 의견만 받는 것(review false: 결정이 되지 않는다), "rejected": [{…답 그대로, "why"}], "missing": [받을 답이 없는 판정 대상 id]}.
    받는 것: id 가 보낸 hunks 에 있고 inputHash 가 보낸 값과 같고 verdict 가 셋 가운데 하나인 것. 판정은 _narrow 로 좁힌다(바꿨으면 note). 같은 id 의 답이 둘이고 판정이 갈리면 check."""
    sent = {h["id"]: h for h in payload.get("hunks") or ()}
    out = {"decisions": {}, "opinions": {}, "rejected": [], "missing": []}
    seen = {}
    for r in (answer.get("reviews") if isinstance(answer, dict) else None) or ():
        if not isinstance(r, dict):
            continue
        hid = r.get("id") if isinstance(r.get("id"), str) else ""
        h = sent.get(hid)
        if h is None:
            why = "입력에 없는 id"
        elif str(r.get("inputHash") or "") != h["inputHash"]:
            why = "inputHash 가 다름(보낸 자료에 대한 답이 아님)"
        elif r.get("verdict") not in VERDICT:
            why = "모르는 verdict"
        elif hid in seen:
            why = "같은 작성 내용을 두 번"
            if seen[hid] != r["verdict"] and hid in out["decisions"] and out["decisions"][hid]["value"] != "check":
                out["decisions"][hid].update(value="check", note="같은 작성 내용에 판정이 둘로 갈림")
        else:
            seen[hid] = r["verdict"]
            nature = r.get("nature") if r.get("nature") in NATURES else "모름"
            reason = str(r.get("reason") or "").strip()[:300]
            if h.get("review"):
                value, note = _narrow(VERDICT[r["verdict"]], nature, h)
                out["decisions"][hid] = {"value": value, "source": "llm", "nature": nature, "reason": reason, "inputHash": h["inputHash"], **({"note": note} if note else {})}
            else:
                out["opinions"][hid] = {"verdict": VERDICT[r["verdict"]], "nature": nature, "reason": reason, "inputHash": h["inputHash"]}
            continue
        out["rejected"].append({**r, "why": why})
    out["missing"] = [i for i, h in sent.items() if h.get("review") and i not in out["decisions"]]
    return out


# ---- 단위로 나눠 병렬 검토 -------------------------------------------------------------------

def _unit(us, at, h):
    """그 작성 내용이 든 단위 차례 — 취합본에서의 앞 경계(없으면 뒤 경계 · 그 표 · 기준본 쪽 id)가 든 장. 못 찾으면 첫 단위."""
    base, to = h.get("base") or {}, h.get("to") or {}
    bid = next((i for i in (to.get("prev"), to.get("next"), base.get("table"), base.get("prev"), base.get("next"), *(base.get("ids") or ())) if i in at), None)
    return merge_chunks.assign(us, at, [bid])[0]


def _pack(rows, cap):
    """판정 대상 줄들(단위 차례, 차례, 보낼 꼴, 크기)을 문서 순으로 호출 묶음에 이어 담는다 — 묶음의 크기 합이 cap 을 넘기 전에 새 묶음(하나가 혼자 넘으면 혼자)."""
    packs = []
    for r in sorted(rows, key=lambda r: r[1]):
        if not packs or packs[-1]["size"] + r[3] > cap:
            packs.append({"rows": [], "size": 0})
        packs[-1]["rows"].append(r)
        packs[-1]["size"] += r[3]
    return packs


def prepare(items, frame, to, part, *, job=None, guide=None, model=MODEL, pages=merge_chunks.PAGES, chars=UNIT_CHARS, hunk_chars=HUNK_CHARS, effort="medium", timeout=600.0, orgs=None):
    """보낼 자료를 만든다(LLM 은 안 부름 — 두 문서의 blocks·그래프를 읽는 것은 여기까지라 문서 잠금 안에서 불러도 된다) → run() 에 줄 것
    {"units": [단위 줄], "sent": [(단위 줄 차례, 자료)], "jobs": [llm.ask_all 의 job], "left", "counts", "job", "guide"}. 인자는 review() 와 같다."""
    cx = _context(frame, to, part)
    us = merge_chunks.units((to or {}).get("blocks") or [], (to or {}).get("graph"), pages=pages) or [WHOLE]
    g = merge_guides.get(GUIDE) if guide is None else guide
    hunk_chars = max(LINE_MIN, min(hunk_chars, chars))
    plan = {"units": [], "sent": [], "jobs": [], "left": 0, "counts": {"targets": 0, "opinions": 0, "user": 0}, "job": job_prompts.brief(job), "guide": merge_guides.brief(g) if g else None}
    rows = []
    for n, h in enumerate(items or ()):
        if h.get("status") not in TARGET + OPINION:
            continue
        if (h.get("decision") or {}).get("source") == "user":   # 사람이 고른 것은 보내지 않는다(답이 와도 입력에 없는 id 로 버려진다)
            plan["counts"]["user"] += 1
            continue
        full = _entry(h, cx)
        e = {"id": h["key"], "inputHash": _hash(full), **_fit(full, hunk_chars)}
        rows.append((_unit(us, cx["at"], h), n, e, _size(e)))
    doc = {"part": (part or {}).get("name") or "", "orgs": [{"name": o.get("name"), "role": o.get("role")} for o in (frame or {}).get("orgs") or ()], **({"assigned": list(orgs)} if orgs else {})}
    for i, u in enumerate(us):
        mine = [r for r in rows if r[0] == i]
        packs = _pack([r for r in mine if r[2]["review"]], chars)
        extra = [r for r in mine if not r[2]["review"]]
        if not packs:   # 판정 대상이 없는 장은 부르지 않는다 — 의견만 받는 것을 위해 따로 부르지 않음
            plan["units"].append({"title": u["title"], "pages": u["pages"], "over": u["over"], "targets": 0, "opinions": 0, "call": None})
            plan["left"] += len(extra)
            continue
        for r in extra:   # 의견만 받는 것 — 어차피 부르는 호출에 자리가 남을 때만 얹는다(호출을 늘리지 않음)
            pk = next((pk for pk in packs if pk["size"] + r[3] <= chars), None)
            if pk is None:
                plan["left"] += 1
            else:
                pk["rows"].append(r)
                pk["size"] += r[3]
        for k, pk in enumerate(packs):
            hunks = [r[2] for r in sorted(pk["rows"], key=lambda r: r[1])]
            many = len(packs) > 1
            payload = {"doc": doc, "chapter": {"title": u["title"], "pages": u["pages"], **({"piece": [k + 1, len(packs)]} if many else {})}, "hunks": hunks}
            content = prompt(payload, job, g if g else False)
            n_t = sum(1 for x in hunks if x["review"])
            plan["counts"]["targets"] += n_t
            plan["counts"]["opinions"] += len(hunks) - n_t
            plan["sent"].append((len(plan["units"]), payload))
            plan["units"].append({"title": u["title"] + (f" ({k + 1}/{len(packs)})" if many else ""), "pages": u["pages"], "over": u["over"], "targets": n_t, "opinions": len(hunks) - n_t,
                                  "chars": pk["size"], "call": None, "prompt": content})
            plan["jobs"].append({"schema": SCHEMA, "content": content, "what": f"gather-llm-{len(plan['jobs']) + 1}", "timeout": timeout, "effort": effort, "model": model})
    return plan


def run(plan, *, ask=None):
    """prepare() 의 자료를 단위마다 한 호출로 병렬로 묻고(잠금 밖 — 호출이 수십 초~수 분) 답을 검증한다 → review() 의 결과. ask = llm.ask_all 대신(시험)."""
    units = [dict(u) for u in plan["units"]]
    out = {"decisions": {}, "opinions": {}, "units": units, "held": [], "rejected": [], "left": plan["left"], "counts": dict(plan["counts"]), "job": plan["job"], "guide": plan["guide"]}
    jobs = plan["jobs"]
    try:
        res = list((ask or llm.ask_all)(jobs)) if jobs else []
    except Exception as e:   # llm.ask_all 은 예외를 안 낸다 — 그래도 났으면 모든 단위를 보류로(「검토함」 으로 넘어가지 않게)
        res = [{"data": None, "error": f"예외: {type(e).__name__}: {e}"[:300]}] * len(jobs)
    res += [{"data": None, "error": "결과 없음"}] * (len(jobs) - len(res))
    for (n, p), r in zip(plan["sent"], res):
        r = r if isinstance(r, dict) else {"data": None, "error": "결과 없음"}
        row = units[n]
        row["call"] = {k: r.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error", "retried")}
        row["answer"] = r.get("data")
        if isinstance(r.get("data"), dict):
            c = check(p, r["data"])
            out["decisions"].update(c["decisions"])
            out["opinions"].update(c["opinions"])
            out["rejected"] += [{**x, "unit": n} for x in c["rejected"]]
            missing, why = c["missing"], "LLM 답에 이 작성 내용이 없음(또는 받을 수 없는 답) — 검토하지 못해 보류"
        else:   # 실패 · 시간 초과 · 빈 답 — 그 단위의 판정 대상 전부
            missing, why = [h["id"] for h in p["hunks"] if h["review"]], f"LLM 검토 호출 실패({r.get('error') or '답 없음'}) — 검토하지 못해 보류"
        by = {h["id"]: h for h in p["hunks"]}
        for k in missing:
            out["decisions"][k] = {"value": "check", "source": "llm", "nature": "모름", "reason": why[:300], "inputHash": by[k]["inputHash"], "held": True}
            out["held"].append(k)
        row["held"] = len(missing)
    return out


def review(items, frame, to, part, *, job=None, guide=None, ask=None, model=MODEL, pages=merge_chunks.PAGES, chars=UNIT_CHARS, hunk_chars=HUNK_CHARS, effort="medium", timeout=600.0,
           orgs=None):
    """기관 문서 하나의 작성 내용을 **취합본의 장마다 한 호출**(글자 수 상한을 넘으면 더 나눔)로 병렬 검토한다(spec_취합 ② §4-3).
    items = 판정이 붙은 작성 내용 [{key, kind, status, detail, scope{kind, org, orgName, year, stage}, path[], base{prev, next, ids[], table}, from{ids[], table, cells[{r, c, id, text, base}],
    rows[{r, cells[]}]}, to{prev, next}, text, counts{}, unique, decision | None}] · frame = 기준본 자리 정보 {blocks[{i, id, kind, key, text, cls, path, scope, table?}], values, orgs[{key, name, role}]} ·
    to·part = 취합본·기관 문서 {id, name, blocks, graph, …}(merge_api._read 꼴). orgs = 이 기관 문서에서 가져오기로 지정한 기관 이름들(자료의 doc.assigned — 없어도 됨).
    보내는 것: status ready(판정 대상) + 그 장을 어차피 부를 때 자리가 남으면 overlap·unknownPlace(의견만 — 못 실은 수는 left). 사람이 고른 것(decision.source user)과 그 밖의 상태는 안 보낸다.
    → {"decisions": {열쇠: {"value": keep|skip|check, "source": "llm", "nature", "reason", "inputHash"[, "note": 코드가 좁힌 까닭][, "held": True]}} — **판정 대상만**(사람이 고른 것 · ready 아닌 것은 없다),
       "opinions": {열쇠: {"verdict": keep|skip|check, "nature", "reason", "inputHash"}} — overlap·unknownPlace 에 대한 의견(결정 아님),
       "units": [{title, pages, over, targets, opinions, call{backend, model, effort, ms, costUsd, error, retried} | None(부르지 않은 장), + 부른 것만 chars, prompt, answer, held}],
       "held": [검토하지 못해 보류한 열쇠 — 그 결정은 check + held], "rejected": [{…답, why, unit}], "left": 못 실은 의견 대상 수, "counts": {targets, opinions, user},
       "job": 함께 보낸 할 일 프롬프트 {job, name, sha1} | None, "guide": 함께 보낸 지침 {name, title, sha1} | None}.
    한 단위의 호출이 실패해도 다른 단위의 결과는 남는다(그 단위 call.error — 그 단위의 판정 대상은 held). prompt 는 크다 — gather.json 에는 안 싣고 따로 둔다(`gather/llm-<기관 문서 id>.json`)."""
    return run(prepare(items, frame, to, part, job=job, guide=guide, model=model, pages=pages, chars=chars, hunk_chars=hunk_chars, effort=effort, timeout=timeout, orgs=orgs), ask=ask)
