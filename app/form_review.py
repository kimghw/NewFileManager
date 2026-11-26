"""양식 검토(spec_양식작성 ② §5-1) — **양식 전체를 읽고 어떻게 작성할지 검토**하고, 쓰기 전에 **사람이 정해 줄 것을 묻는** 도구의 순수 계산.
2026-11-24 사용자(「지침 작성」 열을 보며) "양식을 전부 읽고 어떻게 작성해야할지 검토한다, 그리고 사용자가 문서를 제공하면 작성하는데,, 이전에 사용자가 정해줄 내용을 물어 본다. ... 이게 도구에 포함되었냐? . 이렇게 하도록 해줘".
문서를 고치지 않는다 — 자료(양식 전체 글 · 자리 · 작성 지침 · 고른 자료) · 프롬프트 · 답 검증 · 지침 작성 요청에 붙일 글만(묻기 · 저장은 `app/form_review_api.py`).

- `form_text(blocks, graph)` → 양식 전체를 문서 차례로 읽는 글(헤딩 = 「#」 × 깊이 + [id] · 문단 · 표 = 행마다 칸 글) — FORM_MAX 자까지(넘으면 본문 문단부터 줄인다).
- `payload(...)` → 프롬프트의 자료: 양식 글 · 자리(지침 작성의 자리 목록 — 작성 지침 포함) · 앞서 정한 것(사람의 답) · 자료(고른 것 — 있으면 물음의 답 후보를 자료에서 찾는다).
- 두 걸음(2026-11-24 사용자 "일단 양식에서 다 읽고 어떻게 쓸건지 검토하고, 문서를 제공하면 어떻게 쓸지 계획을 쓰고, 다만 확인해야할 사항은 사용자에게 물어본다"): **양식 검토**(자료 없이 — 요약 · 자리마다 how · needs) →
  **작성 계획**(자료를 주고 — 자리마다 use(자료에서 쓸 것) · gap(자료에 없는 것) + 확인할 것의 답 후보). 같은 호출 · 같은 계약이고 자료가 있나로 갈린다(`planned`).
- `check(answer, place_ids, has_materials)` → 검토(요약 · 자리마다 작성 방향 · 물음[{key, text, why, places, choices, suggest, source}]) — 모르는 자리 id 는 버리고 물음은 QUESTIONS_MAX 개까지.
- `plan_for(review, decided, place_id)` → 그 자리의 지침 작성 요청에 붙일 것 {how, facts[(물음, 답)]} — 자리를 정해 묻지 않은 물음(문서 전체)의 답은 모든 자리에.
- `topics(raw, place_ids)` → 자료에서 찾을 테마 · 키워드(② §5-2 — 2026-11-24 사용자 "여기서 작성 테마/키워드를 추출해줘 … 테마/키워드 그리고 맥락을 함께") · `scope_line(topic, lead)` → 문서 라이브러리의 「뽑을 범위」 에 붙일 한 줄.
- `place_sig` · `sigs` · `sig` → 자리의 지문(상자는 줄 차례 · 역할 · 원문까지) · `lost(review, decided, place_ids)` → 자리를 잃은 답(어느 자리에도 싣지 않는다).
- `open_questions(review, decided)` → 아직 답하지 않은 물음 — 지침 작성의 「제안 받기」 는 이것이 비어야 돈다(쓰기 전에 묻는다 — 사용자 말).
- 스크립트가 판정하지 못한 것 = 양식 전체에서 무엇을 어떻게 써야 하고 무엇을 사람이 정해야 하는가(지침과 양식 글을 다 읽어야 안다) — LLM 이 판정한다. LLM 은 내용을 짓지 않는다(답 후보는 자료에 있는 것만 · 출처 구절)."""
import hashlib
import json

from app import prompt_texts
from app import form_slots as FS
from app import job_prompts, merge_guides
from app.headings import iter_blocks

S_ = {"type": "string"}


def _obj(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def _arr(item):
    return {"type": "array", "items": item}


SCHEMA = _obj({"summary": S_,
               "sees": _obj({"write": S_, "guides": S_, "asks": S_}),   # 양식 검토가 보는 셋(2026-11-25 사용자 「목적문서의 양식에 뭘 작성해야하는지, 어떤 지침이 있는지 사용자가 요청하는건 뭔지를 봐야지」)
               "places": _arr(_obj({"id": S_, "how": S_, "needs": S_, "use": S_, "gap": S_})),
               "topics": _arr(_obj({"name": S_, "keywords": _arr(S_), "context": S_, "scope": S_, "places": _arr(S_)})),
               "questions": _arr(_obj({"text": S_, "why": S_, "places": _arr(S_), "choices": _arr(S_), "suggest": S_, "source": S_}))})
GUIDE, MODEL = "form_review", "claude-opus-5-5"
FORM_MAX = 45000        # 양식 글
PARA_MAX, CELL_MAX, ROWS_MAX = 400, 80, 12   # 문단 하나 · 칸 하나 · 표 하나에 싣는 행
GUIDE_MAX = 600         # 자리 하나의 지침(합쳐 — 자리 목록에)
MATERIAL_MAX = 60000    # 고른 자료(합쳐)
QUESTIONS_MAX = 12
TOPICS_MAX, KEYWORDS_MAX, TOPIC_NAME, KEYWORD_MAX, SCOPE_MAX = 12, 6, 40, 30, 200   # 자료에서 찾을 테마 · 키워드(② §5-2)
HOW_MAX, Q_MAX, CHOICE_MAX, ANSWER_MAX = 300, 200, 6, 500
PLAN_MAX = 1100         # 지침 작성 요청 하나에 붙이는 검토 글(작성 방향 + 정한 것)
REQUEST_MAX = 1000      # 사람의 요청(「이번 작성의 지침」 — guide_write.NOTE_MAX 와 같다)
SEES_MAX = 700          # 「보는 셋」 한 칸
SKIP = "자료대로"        # 「따로 정하지 않음 — 자료에 있는 대로」 (사람이 고르는 답 — 물음을 건너뛴다는 뜻을 적어 둔다)

CONTRACT = """당신은 정해진 **양식 문서**(사업계획서 · 보고서 · 신청서 등)를 채우기 전에, 양식 전체를 읽고 **어떻게 작성할지 검토**하는 검토자입니다. 문서를 쓰지 않습니다 —
검토 결과는 사람이 보고 답한 뒤, 자리마다 따로 도는 작성 에이전트가 그 결과를 읽고 씁니다.

### 자료
- form = 양식 전체의 글(문서 차례 — 「#」 줄 = 헤딩(# 수 = 깊이 · 끝의 [id]) · 「[표 id]」 아래 행마다 「칸 | 칸」 · 그 밖 = 본문 문단(양식의 안내 · 예시 글일 수 있음)). cut 이 참이면 길어서 줄였습니다.
  「[상자 id]」 = 1칸 표(상자) — 그 아래 줄마다 상자 안 문단 「[문단 id] (L레벨) 「원문」」: 레벨은 그 줄의 개요 깊이(작을수록 윗 제목), 「쓸 자리」 라고 적힌 줄(빈 줄 · 글머리 줄 · 같은 줄 뒤에 값 · 표시 줄)이 글을 쓸 곳이고
  그 위의 제목 줄이 그 자리의 항목입니다. 「000」 · 「○○ 작성」 같은 글은 자리표시(양식의 글)입니다. 상자 안의 표 · 그림 자리는 여기서 채우지 않습니다.
- places = 채울 자리 [{id, kind("head" 헤딩 아래 · "box" 상자 안의 쓸 자리 · "table" 표), text, depth, guides[작성 지침 — (양식 · 종류) 또는 (사람)], filled(이미 글이 있음),
  slot?("label" 그 줄 뒤에 값을 쓰는 줄 · "check" 항목 하나에 표시하는 줄 · "filled" 이미 채운 줄), slots?(상자 — 쓸 수 있는 줄 수), boxed?(그 헤딩 아래에 따로 선 상자 자리가 있음 — 상자에 들어갈 내용은 상자 자리에 적습니다)}].
- request = **사람이 이번 작성에 대해 요청한 것**(「이번 작성의 지침」 — 있을 때만). 자리의 guides 가운데 「(사람)」 도 사람이 그 자리에 적은 요청입니다. 검토는 이것을 따릅니다(양식의 지침과 어긋나면 어긋난다고 적습니다).
- planRequest = **사람이 작성 계획에 대해 요청한 것**(「작성 계획에 줄 요청」 — 작성 계획 때 · 있을 때만: 자료의 무엇을 먼저 쓸지 · 어느 자료를 따를지 · 무엇을 묻지 말지 등). 작성 계획(use · gap · questions)은 이것을 따릅니다 —
  양식의 지침 · request 와 어긋나면 어긋난다고 해당 자리의 gap 이나 물음에 적습니다. 이것으로 자료에 없는 내용을 만들지 않습니다.
- writingJudgment = 04에서 해당 자리의 작성 규칙을 판정한 결과입니다. apply이면 writingGuidance에 채택한 규칙과 출처가 있습니다. basis의 explicit은 명시 요건, example은 샘플에서 관찰한 관례입니다. not_applicable이나 insufficient이면 이 자리의 원래 양식 지침을 사용합니다. 이 판정은 작성 방법에만 적용되며 실제로 채울 내용은 자료에서 찾습니다.
  writingGuidance 의 instruction 이 「테이블 타입 —」 으로 시작하면 그 자리의 표가 어떤 꼴의 표이고(본문 · 헤딩 · 그림 · 값 등) 어떻게 쓰는지입니다(04 가 밝힌 것).
- theme = 04 가 밝힌 **이 문서의 테마**(있을 때만) — 그 종류의 문서에서 중요하게 볼 항목(구분 기준 타입: 항목 이름과 다루는 법)과 문서가 쓰는 개요 템플릿(레벨마다 레터).
- docGuides = **문서 전체에 닿는 지침**(있을 때만 · 한 번만 실었습니다) — 줄 머리의 「규정 · 필수|권고 · 출처」 는 다른 규칙이 이 양식에 요구하는 것, 「문서 목적 …」 은 이 과제의 공고 · 목적 · 평가 관점 · 요구 사항, 「양식 지침 — 문서 전체」 는 일반 가이드라인입니다. 자리의 guides 에도 「(규정 …)」 · 「(문서 목적 …)」 으로 그 자리에 닿는 것이 섞여 있습니다.
- decided = 사람이 이미 정해 준 것 [{q, a}] — 다시 묻지 않습니다.
- materials = 사람이 준 자료(있을 때만 — 특정 기관 · 특정 연구에 대해 뽑은 글). 없으면 자료는 아직 오지 않았습니다.

### 답
- summary = 이 양식이 무엇이고 전체를 어떻게 쓰면 되는지(3~6문장 — 분량 · 문체(개조식 등) · 자리 사이의 관계 · 꼭 지킬 지침).
- sees = 양식 검토가 보는 셋 {write, guides, asks} — 칸마다 2~5문장:
  write = **목적 문서의 양식에 무엇을 써야 하는지**(쓸 자리들과 자리마다 들어갈 내용의 종류 · 이미 채운 곳) ·
  guides = **어떤 작성 지침이 있는지**(양식의 작성 요령 · ※ 안내 · 각주 · 참고와 사람이 자리에 적은 지침 — 꼭 지킬 형식 · 분량 · 단위를 지침 이름과 함께. 지침이 없는 자리도 그렇게) ·
  asks = **사람이 요청한 것**(request 와 「(사람)」 지침 — 무엇을 요청했고 검토가 그것을 어떻게 따르는지 · 양식의 지침과 어긋나는 곳). 요청이 없으면 「사람의 요청 없음」.
- places = 자리마다 [{id, how, needs, use, gap}] — id 는 places 에 있는 것만. how = 그 자리에 무엇을 어떤 꼴로 쓸지 한두 문장(지침을 따름 — 지침의 예시 글 · 예시 수는 내용이 아님).
  needs = 그 자리를 쓰려면 자료에 있어야 할 정보(짧게). 쓸 것이 분명하지 않은 자리도 넣되 how 에 그렇게 적습니다.
  **작성 계획**(materials 가 있을 때만 — 없으면 둘 다 ""): use = 자료의 어느 내용을 이 자리에 쓸지(자료에 있는 것만 — 어느 절 · 어느 표 · 핵심 말로 짧게 가리킴: 글을 미리 쓰지 않습니다) ·
  gap = 이 자리에 필요한데 자료에 없는 것(없으면 ""). 자료에 이 자리의 내용이 전혀 없으면 use 는 "" 이고 gap 에 그렇게 적습니다.
- topics = **자료에서 찾을 테마 · 키워드** [{name, keywords, context, scope, places}] — 이 양식을 쓰려면 자료 문서에서 무엇을 찾아 뽑아야 하는지. 사람이 이것을 보고 자료 문서에서 그 내용을 추출합니다.
  - name = 테마(찾을 내용의 짧은 이름 — 「당해연도 개발목표」) · keywords = 자료에서 그 내용을 부르는 표현 2~6개(양식의 말 + 흔한 다른 표현 — 「개발 목표」 · 「세부 목표」) ·
    context = 맥락(어느 자리에 · 무엇이 · 어떤 꼴로 필요한지 한두 문장) · scope = 자료 추출의 범위 칸에 붙일 한 줄(테마의 **내용만** — 기관 이름 · 기간 · 「개조식으로」 같은 작성 꼴은 넣지 않습니다) · places = 그 테마가 닿는 자리 id.
  - 같은 근거로 여러 자리를 채우면 한 테마로 묶고, 연도 · 누구의 몫 · 필요한 증거가 다르면 나눕니다. 자리마다 하나씩 잘게 쪼개지 않고, 양식 전체를 하나로 뭉치지도 않습니다. 많아야 12개.
  - 자료가 있든 없든 냅니다(양식만 읽고 정하는 것입니다). 양식에 없는 항목을 지어내지 않습니다.
- questions = **쓰기 전에 사람이 정해 줘야 할 것** [{text, why, places, choices, suggest, source}] — 양식 · 지침 · 자료만으로는 정할 수 없고 사람의 결정이 있어야 하는 것만
  (예: 어느 기관 · 어느 과제 · 몇 차년도 몫을 쓰는가 · 기준일 · 금액 단위 · 분량 · 강조할 점 · 자료가 서로 다를 때 어느 것을 따를지 · 표 줄을 무엇으로 나눌지).
  - 자료나 지침에 답이 분명히 있는 것은 묻지 않습니다. decided 에 있는 것은 묻지 않습니다. 사소한 표기는 묻지 않습니다. 가장 중요한 것부터 많아야 12개.
  - 상자 안에 **같은 이름의 자리가 여럿**(「공동(기업명 작성) : 」 이 두 곳)일 때 **어느 자리에 쓸지는 묻지 않습니다** — 사람이 화면에서 쓸 자리를 직접 고릅니다. 누구의 내용을 쓸지(어느 기관 · 어느 연도)는 묻습니다.
  - places = 그 물음이 닿는 자리 id(문서 전체에 닿으면 빈 목록) · choices = 고를 만한 답(있으면 2~5개 — 양식 · 지침 · 자료에 나온 값만) ·
    suggest = 자료에서 찾은 답 후보(자료에 있을 때만 · 없으면 "") · source = suggest 의 근거가 된 자료 구절(짧게 인용 · 없으면 "").
  - **내용을 짓지 않습니다** — suggest · choices 에 자료 · 양식에 없는 이름 · 수 · 날짜를 넣지 않습니다."""

FALLBACK_GUIDE = """- 양식의 안내 글 · 작성 요령 · ※ 안내 · 각주를 모두 읽고, 자리마다 무엇을 쓰라는지 정리한다. 예시 글 · 예시 수는 내용이 아니다.
- 사람에게 묻는 것은 사람만 정할 수 있는 것(범위 · 기준 · 우선순위)이다. 자료를 읽으면 알 수 있는 사실은 묻지 않는다."""


def _short(text, n):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def _cells_rows(b):
    rows = {}
    clipped = False
    for c in b.get("cells") or ():
        t = " ".join(x.get("text") or "" for x in iter_blocks(c.get("blocks") or ()) if x.get("type") == "paragraph").strip()
        clipped |= len(" ".join(t.split())) > CELL_MAX
        rows.setdefault(c.get("row") or 0, []).append((c.get("col") or 0, _short(t, CELL_MAX)))
    return [" | ".join(t for _, t in sorted(cs)) for _, cs in sorted(rows.items())], clipped


def form_text(blocks, graph, limit=FORM_MAX, orig=None):
    """양식 전체 글(문서 차례) → (글, cut). 넘치면 문단을 더 짧게 줄여 다시 짓고(헤딩 줄은 늘 남긴다), 그래도 넘치면 뒤를 자른다. orig = 올린 원본의 문단 원문(채운 자리를 가린다 — form_slots)."""
    text = ""
    for n, para_max in enumerate((PARA_MAX, 200, 100, 60)):
        text, clipped = _form_text(blocks, graph, para_max, orig)
        if len(text) <= limit:
            return text, clipped or n > 0
    return text[:limit], True


def _form_text(blocks, graph, para_max, orig=None):
    levels = {n["para"]: n["level"] for n in (graph or {}).get("nodes") or () if isinstance(n, dict) and n.get("para") and n.get("level")}   # 상자 안 줄의 레벨(헤딩 추출이 매긴 것 — area box)
    depth = {n["para"]: n.get("depth") or 1 for n in (graph or {}).get("nodes") or ()
             if isinstance(n, dict) and n.get("role") == "heading" and n.get("area") == "body" and n.get("para")}
    lines, clipped = [], False
    for b in blocks or ():
        if b.get("type") == "paragraph":
            t = " ".join((b.get("text") or "").split())
            if not t:
                continue
            clipped |= len(t) > (200 if b["id"] in depth else para_max)
            lines.append(f"{'#' * min(6, depth[b['id']])} {_short(t, 200)} [{b['id']}]" if b["id"] in depth else _short(t, para_max))
        elif FS.box_cell(b) is not None:   # 상자(1칸 표) — 칸을 80자로 뭉개지 않고 문단마다(쓸 자리 · 제목 · 안쪽 표의 자리): 2026-11-24 사용자 「작성지침에서 필드에 있는 값을 못 읽는다는거지?」
            entries = FS.entries(FS.box_cell(b), levels, orig)
            clipped |= any(len(e.get("raw", "")) > FS.RAW_MAX for e in entries)
            lines.append(f"[상자 {b['id']}]\n" + FS.view_text(entries))
        elif b.get("type") == "table":
            rows, cells_cut = _cells_rows(b)
            clipped |= cells_cut or len(rows) > ROWS_MAX
            lines.append(f"[표 {b['id']}]" + "".join(f"\n  {r}" for r in rows[:ROWS_MAX] if r.strip(" |")) + (f"\n  … ({len(rows) - ROWS_MAX}행 더)" if len(rows) > ROWS_MAX else ""))
    return "\n".join(lines), clipped


def _place_brief(p):
    gs, used = [], 0
    guides = p.get("guides") or ()
    from app import place_guides as PG
    for g in sorted((g for g in guides if g.get("src") != "llm"), key=PG.rank):   # 출처 순위(사람 › 규정(필수) › 문서 목적 › 양식 명시 › 양식 지침 › 규정(권고) — spec_양식작성 ② §5-9)
        t = _short(g.get("text"), GUIDE_MAX - used)
        if used >= GUIDE_MAX or not t:
            break
        who = ("사람" if g.get("src") == "user" else PG.tag(g) if g.get("src") in ("rule", "purpose")   # 규정 · 문서 목적(② §5-9 — 「규정 · 필수 · 출처」)
               else "양식 지침" + (" · " + g["label"] if g.get("label") else "") if g.get("src") == "form"   # 양식 지침 YAML(spec_양식작성 ② §5-8)
               else "양식" + (" · " + g["kind"] if g.get("kind") else ""))
        gs.append(f"({who}) {t}")
        used += len(t)
    llm_rules = [{"instruction": g.get("instruction") or g["text"], "sources": g.get("sources") or [],
                  **({"basis": g["basis"]} if g.get("basis") else {})} for g in guides if g.get("src") == "llm"]
    return {"id": p["id"], "kind": p["kind"], "text": p.get("text") or "", "depth": p.get("depth"), "guides": gs, "filled": bool(p.get("filled")),
            **({"writingGuidance": llm_rules} if llm_rules else {}),
            **({"writingJudgment": {"status": p["writingJudgment"]["status"]}} if p.get("writingJudgment") else {}),
            **{k: p[k] for k in ("slot", "slots", "boxed") if p.get(k)}}


def place_sig(p):
    """자리 하나의 지문 — id · 종류 · 글 · 지침 · 같은 줄 자리 · 상자의 줄 차례(문단 id · 종류 · 원문: `guide_write.places` 가 준 fp). 고정 제목을 맞바꾸거나 줄의 역할이 달라지면 달라진다
    (astra 2차 G11 — 자리 id 와 덩이 수만으로는 「연구개발 목표」 ↔ 「내용 및 범위」 를 맞바꾼 양식을 못 가린다)."""
    inputs = [p["id"], p.get("kind"), p.get("text"), [g.get("text") for g in p.get("guides") or ()], p.get("slot"), p.get("fp")]
    if p.get("writingGuidanceSig"):
        inputs.append(p["writingGuidanceSig"])
    if p.get("writingJudgment"):
        inputs.append(p["writingJudgment"]["status"])
    raw = json.dumps(inputs, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def sigs(places):
    """자리마다의 지문 {자리 id: 지문} — 검토에 함께 적어 두고, 초안을 받을 때 고른 자리가 검토한 때와 같은지 견준다(guide_write_api — 다르면 그 자리만 409)."""
    return {p["id"]: place_sig(p) for p in places or ()}


def sig(places):
    """자리 목록의 지문 — 검토 뒤 양식(자리 · 지침)이 바뀌었나 보인다(바뀌어도 검토 · 답은 버리지 않는다)."""
    raw = json.dumps(sorted(sigs(places).items()), ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def request_text(note):
    """사람의 요청(「이번 작성의 지침」) → 한 칸 글(줄 나눔은 남김 · REQUEST_MAX 자까지)."""
    t = "\n".join(" ".join(x.split()) for x in str(note or "").splitlines()).strip()
    return t[:REQUEST_MAX]


def fed(places, request=""):
    """검토에 실은 것의 셈 — {places, formGuides, userGuides, request}: 화면이 「검토가 본 것」 으로 보인다."""
    gs = [g for p in places or () for g in p.get("guides") or ()]
    enriched = sum(g.get("src") == "llm" for g in gs)
    return {"places": len(places or ()), "formGuides": sum(g.get("src") not in ("user", "llm") for g in gs),
            "userGuides": sum(g.get("src") == "user" for g in gs), **({"llmGuides": enriched} if enriched else {}), "request": bool(request)}


def payload(blocks, graph, places, decided, materials_text="", orig=None, request="", plan_request=""):
    """plan_request = 사람이 작성 계획에 줄 요청(「작성 계획에 줄 요청」 — 자료가 있을 때만 싣는다: 양식 검토에는 안 간다)."""
    text, cut = form_text(blocks, graph, orig=orig)
    out = {"form": text, "cut": cut, "places": [_place_brief(p) for p in places or ()],
           "decided": [{"q": d["q"], "a": d["a"]} for d in decided or () if d.get("a")]}
    theme = next((p["docTheme"] for p in places or () if p.get("docTheme")), "")   # 04 가 밝힌 문서의 테마 · 중요 항목 · 개요 템플릿(자리마다 같은 글 — 한 번만 싣는다: spec_양식작성 ② §5-7)
    if theme:
        out["theme"] = theme
    doc = next((p["docGuides"] for p in places or () if p.get("docGuides")), None)   # 문서 전체에 닿는 지침(규정 · 문서 목적 · 일반 가이드라인 — 자리마다 같은 목록: 한 번만 싣는다 · ② §5-9)
    if doc:
        from app import place_guides as PG
        out["docGuides"] = PG.doc_text(doc)
    if request:
        out["request"] = request
    if materials_text:
        out["materials"] = materials_text[:MATERIAL_MAX]
        if plan_request:
            out["planRequest"] = plan_request
    return out


def guide_part(g=None):
    g = merge_guides.get(GUIDE) if g is None else g
    return merge_guides.part(g) or f"\n\n## 판단 지침 — 기본\n\n{FALLBACK_GUIDE}"


def prompt(data, job=None, guide=None):
    """프롬프트 글 = 계약 + 판단 지침 + 할 일 프롬프트 + 자료(JSON)."""
    return prompt_texts.contract(__name__) + guide_part(guide) + job_prompts.part(job) + "\n\n## 자료(JSON)\n" + json.dumps(data, ensure_ascii=False, separators=(",", ":"))


LLMS = ("claude-fable-5-2", "gpt-6-astra")   # 함께 검토하는 모델의 기본(LLM1 · LLM2 — 에이전트 설정 `models` 가 먼저: agents.AGENTS 의 llms 와 같다)
CONSULT = """

## 두 검토자의 답 — 협의
아래는 위 양식 · 자료를 **따로** 검토한 검토자들의 답(같은 꼴)입니다. 판단 지침의 「두 검토자의 협의」 에 따라 **하나의 답**을 위와 같은 꼴로 내세요.
답에 없는 자리 id · 자료에 없는 사실을 새로 만들지 않습니다. 검토자마다의 답(JSON):
"""


def consult_prompt(base, drafts):
    """협의 프롬프트 = 검토 프롬프트 그대로 + 검토자들의 답(LLM1 · LLM2 …) — 협의 기준은 지침 글(form_review.md 「두 검토자의 협의」)."""
    return base + CONSULT + "\n".join(f"### {d['slot']} ({d['model']})\n" + json.dumps(d["data"], ensure_ascii=False, separators=(",", ":")) for d in drafts)


def parts(job=None, guide=None):
    """에이전트 설정 · 화면 「지침」 보기에 싣는 글들(자료 빼고) — guide_fix.parts 와 같은 꼴."""
    g = merge_guides.get(GUIDE) if guide is None else guide
    out = [{"key": "contract", "title": "계약 — 역할 · 자료 설명 · 답의 꼴", "text": prompt_texts.contract(__name__), "source": "app/form_review.py",
            "note": "코드에 든 글입니다(답을 검증하는 코드와 한 몸) — 판단 기준은 아래 지침에 있습니다"}]
    if g and merge_guides.body(g):
        out.append({"key": "guide", "title": f"판단 지침 — {g['title']}", "text": merge_guides.body(g), "source": g["path"], "note": "이 파일을 고치면 다음 실행부터 적용됩니다"})
    else:
        out.append({"key": "guide", "title": "판단 지침 — (지침 파일 없음: 기본 기준)", "text": FALLBACK_GUIDE.strip(), "source": "app/form_review.py", "note": "app/merge_guides_default/form_review.md 가 없어 기본 기준만 보냅니다"})
    if job and job_prompts.part(job):
        out.append({"key": "job", "title": f"할 일 프롬프트 — {job['name']}", "text": job_prompts.body(job.get("text")), "source": job.get("path") or "", "note": "이 작업의 전제 — 먼저 따릅니다"})
    return out


def check(answer, place_ids, has_materials):
    """LLM 답 → 검토 {summary, places{id: {how, needs}}, questions[{key, text, why, places, choices, suggest, source}]}. 모르는 자리는 버리고 · 자료가 없으면 답 후보를 버린다."""
    ids = set(place_ids or ())
    a = answer if isinstance(answer, dict) else {}
    ps = {}
    for p in a.get("places") or ():
        if isinstance(p, dict) and p.get("id") in ids and p["id"] not in ps:
            ps[p["id"]] = {"how": _short(p.get("how"), HOW_MAX), "needs": _short(p.get("needs"), HOW_MAX),
                           "use": _short(p.get("use"), HOW_MAX) if has_materials else "", "gap": _short(p.get("gap"), HOW_MAX) if has_materials else ""}   # 작성 계획은 자료가 있을 때만
    qs, seen = [], set()
    for q in a.get("questions") or ():
        if not isinstance(q, dict) or len(qs) >= QUESTIONS_MAX:
            continue
        text = _short(q.get("text"), Q_MAX)
        if not text or text in seen:
            continue
        seen.add(text)
        choices = [c for c in dict.fromkeys(_short(c, 80) for c in q.get("choices") or () if isinstance(c, str)) if c][:CHOICE_MAX]
        sug = _short(q.get("suggest"), ANSWER_MAX) if has_materials else ""
        named = [i for i in dict.fromkeys(q.get("places") or ()) if isinstance(i, str) and i]
        where = [i for i in named if i in ids]
        qs.append({"key": f"q{len(qs) + 1}", "text": text, "why": _short(q.get("why"), Q_MAX), "places": where,
                   "choices": choices, "suggest": sug, "source": _short(q.get("source"), 200) if sug else "",
                   **({"unplaced": True} if named and not where else {})})   # 자리를 적었는데 모두 모르는 id — 「문서 전체」 가 아니다: 어느 자리에도 싣지 않는다(astra 2차 「빠뜨린 2」 의 검토 시점 쪽)
    sees = a.get("sees") if isinstance(a.get("sees"), dict) else {}
    sees = {k: _short(sees.get(k), SEES_MAX) for k in ("write", "guides", "asks")}
    return {"summary": _short(a.get("summary"), 1200), **({"sees": sees} if any(sees.values()) else {}), "places": ps, "questions": qs, "topics": topics(a.get("topics"), ids)}


def keep_review(rv, prev):
    """작성 계획(자료를 주고 한 검토)의 답 rv 에 앞 양식 검토 prev 의 것을 지닌다 — 요약 · 보는 셋 · 자리마다 작성 방향(how · needs) · 테마는 **양식 검토의 것**이고,
    계획이 받는 것은 자리마다 use · gap 과 물음뿐이다(2026-11-25 사용자 「양식검토만 하는데 왜 다른걸 돌려」 — 두 걸음을 섞지 않는다). 양식이 바뀐 뒤면(지문이 다름) 부르지 않는다(새 답 그대로)."""
    if not prev:
        return rv
    rv["summary"] = prev.get("summary") or rv["summary"]
    if prev.get("sees"):
        rv["sees"] = prev["sees"]
    old = prev.get("places") if isinstance(prev.get("places"), dict) else {}
    for pid, p in rv["places"].items():
        o = old.get(pid) or {}
        p.update(how=o.get("how") or p["how"], needs=o.get("needs") or p["needs"])
    if prev.get("topics") is not None:
        rv["topics"], rv["topicsKept"] = prev["topics"], True
    return rv


def topics(raw, place_ids):
    """LLM 답의 topics → [{key, name, keywords[], context, scope, places[]}] — 이름이 없거나 겹치는 것 · 범위 글이 빈 것은 버리고 TOPICS_MAX 개까지. scope 는 한 줄(줄 나눔 → 빈칸).
    모르는 자리 id 는 뺀다(자리를 모두 잃어도 테마는 남긴다 — 무엇을 찾을지는 그대로다)."""
    ids, out, seen = set(place_ids or ()), [], set()
    for t in raw if isinstance(raw, list) else ():
        if not isinstance(t, dict) or len(out) >= TOPICS_MAX:
            continue
        name, scope = _short(t.get("name"), TOPIC_NAME), _short(t.get("scope"), SCOPE_MAX)
        if not name or name in seen:
            continue
        seen.add(name)
        kws = [k for k in dict.fromkeys(_short(k, KEYWORD_MAX) for k in t.get("keywords") or () if isinstance(k, str)) if k and k != name][:KEYWORDS_MAX]
        out.append({"key": f"t{len(out) + 1}", "name": name, "keywords": kws, "context": _short(t.get("context"), HOW_MAX), "scope": scope or name,
                    "places": [i for i in dict.fromkeys(t.get("places") or ()) if i in ids]})
    return out


def scope_line(topic, lead=""):
    """문서 라이브러리의 「뽑을 범위」 에 붙일 한 줄 — 「<앞말>, <범위 글> (키워드 · 키워드)」. 앞말(기관 · 연구 · 기간 — 사람이 적는다)이 비면 쉼표도 없다 · 줄 나눔 없음 · 600자까지(그 서버의 범위 한도)."""
    lead, scope = " ".join(str(lead or "").split()), " ".join(str(topic.get("scope") or topic.get("name") or "").split())
    kws = [k for k in topic.get("keywords") or () if k and k not in scope]
    line = (f"{lead}, " if lead else "") + scope + (f" ({' · '.join(kws)})" if kws else "")
    return " ".join(line.split())[:600]   # 한 줄 — 키워드에 든 줄 나눔도 빈칸으로(문서 라이브러리는 줄마다 범위 하나로 읽는다)


def planned(review):
    """작성 계획이 있나 — 자료를 주고 한 검토(자리마다 use · gap 을 받은 것). 양식만 읽은 검토는 계획이 아니다."""
    return bool(review and review.get("materials"))


def _answered(q, decided):
    return next((d for d in decided or () if d.get("a") and (d.get("key") == q["key"] or d.get("q") == q["text"])), None)


def open_questions(review, decided):
    """아직 답하지 않은 물음들(검토가 없으면 빈 목록)."""
    return [q for q in (review or {}).get("questions") or () if _answered(q, decided) is None]


def lost(review, decided, place_ids):
    """자리를 잃은 답들 — 답할 때는 닿는 자리가 있었는데(decided.places) 지금 그 자리가 하나도 없고, 같은 물음이 지금 검토에도 없는 답. 어느 자리의 것인지 모르므로 **어느 자리에도 싣지 않는다**
    (astra 2차 「빠뜨린 2」 — 전에는 모르는 자리를 걸러 빈 목록으로 만들고 빈 목록을 「문서 전체」 로 읽어 한 자리의 답이 모든 자리로 퍼졌다). 화면이 「자리를 못 찾은 답」 으로 보인다."""
    ids, qs = set(place_ids or ()), (review or {}).get("questions") or ()
    return [d for d in decided or () if d.get("a") and d["a"] != SKIP and (d.get("unplaced") or (d.get("places") and not (set(d["places"]) & ids)))
            and not any((q["key"] == d.get("key") or q["text"] == d.get("q")) and not q.get("unplaced") and q.get("places") for q in qs)]


def plan_for(review, decided, place_id, place_ids=None):
    """그 자리의 지침 작성 요청에 붙일 것 → {how, facts[(물음, 답)]} | None. facts = 그 자리에 닿는 답 + 문서 전체에 닿는 답 + 검토 밖에서 정한 것(자리 모름 — 모두에).
    place_ids(지금의 자리 id 들)를 주면 자리를 잃은 답(`lost`)은 뺀다."""
    if not review and not decided:
        return None
    qs = {q["key"]: q for q in (review or {}).get("questions") or ()}
    gone = {id(d) for d in lost(review, decided, place_ids)} if place_ids is not None else set()
    facts = []
    for d in decided or ():
        if not d.get("a") or d["a"] == SKIP or id(d) in gone:
            continue
        q = qs.get(d.get("key")) or next((x for x in qs.values() if x["text"] == d.get("q")), None)
        if (q or {}).get("unplaced") or (q is None and d.get("unplaced")):   # 자리를 잃은 물음 · 답 — 물음이 사라진 뒤에도 「문서 전체」 로 되살아나지 않는다(답에 적어 둔 표시: astra 3차)
            continue
        where = (q or {}).get("places") or d.get("places") or []
        if not where or place_id in where:
            facts.append((d["q"], d["a"]))
    how = ((review or {}).get("places") or {}).get(place_id) or {}
    if not facts and not how.get("how") and not how.get("use"):
        return None
    return {"how": how.get("how") or "", "needs": how.get("needs") or "", "use": how.get("use") or "", "gap": how.get("gap") or "", "facts": facts}


def plan_text(plan, limit=PLAN_MAX):
    """plan_for 결과 → 요청 글에 넣는 글(limit 자까지 — 정한 것이 앞: 자르면 작성 방향이 먼저 줄어든다)."""
    if not plan:
        return ""
    facts = "\n".join(f"- {_short(q, 160)} → {_short(a, 300)}" for q, a in plan["facts"])
    parts = []
    if facts:
        parts.append("사람이 정해 준 것(이대로 따릅니다):\n" + facts)
    if plan.get("how"):
        parts.append("양식 검토의 작성 방향(이 자리): " + plan["how"])
    if plan.get("use"):
        parts.append("작성 계획 — 자료에서 쓸 것: " + plan["use"] + (" / 자료에 없는 것(짓지 않습니다): " + plan["gap"] if plan.get("gap") else ""))
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[:limit - 1] + "…"
