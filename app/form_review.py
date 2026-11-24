"""양식 검토(spec_양식작성 ② §5-1) — **양식 전체를 읽고 어떻게 작성할지 검토**하고, 쓰기 전에 **사람이 정해 줄 것을 묻는** 도구의 순수 계산.
2026-11-24 사용자(「지침 작성」 열을 보며) "양식을 전부 읽고 어떻게 작성해야할지 검토한다, 그리고 사용자가 문서를 제공하면 작성하는데,, 이전에 사용자가 정해줄 내용을 물어 본다. ... 이게 도구에 포함되었냐? . 이렇게 하도록 해줘".
문서를 고치지 않는다 — 자료(양식 전체 글 · 자리 · 작성 지침 · 고른 자료) · 프롬프트 · 답 검증 · 지침 작성 요청에 붙일 글만(묻기 · 저장은 `app/form_review_api.py`).

- `form_text(blocks, graph)` → 양식 전체를 문서 차례로 읽는 글(헤딩 = 「#」 × 깊이 + [id] · 문단 · 표 = 행마다 칸 글) — FORM_MAX 자까지(넘으면 본문 문단부터 줄인다).
- `payload(...)` → 프롬프트의 자료: 양식 글 · 자리(지침 작성의 자리 목록 — 작성 지침 포함) · 앞서 정한 것(사람의 답) · 자료(고른 것 — 있으면 물음의 답 후보를 자료에서 찾는다).
- 두 걸음(2026-11-24 사용자 "일단 양식에서 다 읽고 어떻게 쓸건지 검토하고, 문서를 제공하면 어떻게 쓸지 계획을 쓰고, 다만 확인해야할 사항은 사용자에게 물어본다"): **양식 검토**(자료 없이 — 요약 · 자리마다 how · needs) →
  **작성 계획**(자료를 주고 — 자리마다 use(자료에서 쓸 것) · gap(자료에 없는 것) + 확인할 것의 답 후보). 같은 호출 · 같은 계약이고 자료가 있나로 갈린다(`planned`).
- `check(answer, place_ids, has_materials)` → 검토(요약 · 자리마다 작성 방향 · 물음[{key, text, why, places, choices, suggest, source}]) — 모르는 자리 id 는 버리고 물음은 QUESTIONS_MAX 개까지.
- `plan_for(review, decided, place_id)` → 그 자리의 지침 작성 요청에 붙일 것 {how, facts[(물음, 답)]} — 자리를 정해 묻지 않은 물음(문서 전체)의 답은 모든 자리에.
- `open_questions(review, decided)` → 아직 답하지 않은 물음 — 지침 작성의 「제안 받기」 는 이것이 비어야 돈다(쓰기 전에 묻는다 — 사용자 말).
- 스크립트가 판정하지 못한 것 = 양식 전체에서 무엇을 어떻게 써야 하고 무엇을 사람이 정해야 하는가(지침과 양식 글을 다 읽어야 안다) — LLM 이 판정한다. LLM 은 내용을 짓지 않는다(답 후보는 자료에 있는 것만 · 출처 구절)."""
import hashlib
import json

from app import job_prompts, merge_guides
from app.headings import iter_blocks

S_ = {"type": "string"}


def _obj(props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def _arr(item):
    return {"type": "array", "items": item}


SCHEMA = _obj({"summary": S_,
               "places": _arr(_obj({"id": S_, "how": S_, "needs": S_, "use": S_, "gap": S_})),
               "questions": _arr(_obj({"text": S_, "why": S_, "places": _arr(S_), "choices": _arr(S_), "suggest": S_, "source": S_}))})
GUIDE, MODEL = "form_review", "claude-opus-5-5"
FORM_MAX = 45000        # 양식 글
PARA_MAX, CELL_MAX, ROWS_MAX = 400, 80, 12   # 문단 하나 · 칸 하나 · 표 하나에 싣는 행
GUIDE_MAX = 600         # 자리 하나의 지침(합쳐 — 자리 목록에)
MATERIAL_MAX = 60000    # 고른 자료(합쳐)
QUESTIONS_MAX = 12
HOW_MAX, Q_MAX, CHOICE_MAX, ANSWER_MAX = 300, 200, 6, 500
PLAN_MAX = 1100         # 지침 작성 요청 하나에 붙이는 검토 글(작성 방향 + 정한 것)
SKIP = "자료대로"        # 「따로 정하지 않음 — 자료에 있는 대로」 (사람이 고르는 답 — 물음을 건너뛴다는 뜻을 적어 둔다)

CONTRACT = """당신은 정해진 **양식 문서**(사업계획서 · 보고서 · 신청서 등)를 채우기 전에, 양식 전체를 읽고 **어떻게 작성할지 검토**하는 검토자입니다. 문서를 쓰지 않습니다 —
검토 결과는 사람이 보고 답한 뒤, 자리마다 따로 도는 작성 에이전트가 그 결과를 읽고 씁니다.

### 자료
- form = 양식 전체의 글(문서 차례 — 「#」 줄 = 헤딩(# 수 = 깊이 · 끝의 [id]) · 「[표 id]」 아래 행마다 「칸 | 칸」 · 그 밖 = 본문 문단(양식의 안내 · 예시 글일 수 있음)). cut 이 참이면 길어서 줄였습니다.
- places = 채울 자리 [{id, kind("head" 헤딩 아래 · "table" 표), text, depth, guides[작성 지침 — (양식 · 종류) 또는 (사람)], filled(이미 글이 있음)}].
- decided = 사람이 이미 정해 준 것 [{q, a}] — 다시 묻지 않습니다.
- materials = 사람이 준 자료(있을 때만 — 특정 기관 · 특정 연구에 대해 뽑은 글). 없으면 자료는 아직 오지 않았습니다.

### 답
- summary = 이 양식이 무엇이고 전체를 어떻게 쓰면 되는지(3~6문장 — 분량 · 문체(개조식 등) · 자리 사이의 관계 · 꼭 지킬 지침).
- places = 자리마다 [{id, how, needs, use, gap}] — id 는 places 에 있는 것만. how = 그 자리에 무엇을 어떤 꼴로 쓸지 한두 문장(지침을 따름 — 지침의 예시 글 · 예시 수는 내용이 아님).
  needs = 그 자리를 쓰려면 자료에 있어야 할 정보(짧게). 쓸 것이 분명하지 않은 자리도 넣되 how 에 그렇게 적습니다.
  **작성 계획**(materials 가 있을 때만 — 없으면 둘 다 ""): use = 자료의 어느 내용을 이 자리에 쓸지(자료에 있는 것만 — 어느 절 · 어느 표 · 핵심 말로 짧게 가리킴: 글을 미리 쓰지 않습니다) ·
  gap = 이 자리에 필요한데 자료에 없는 것(없으면 ""). 자료에 이 자리의 내용이 전혀 없으면 use 는 "" 이고 gap 에 그렇게 적습니다.
- questions = **쓰기 전에 사람이 정해 줘야 할 것** [{text, why, places, choices, suggest, source}] — 양식 · 지침 · 자료만으로는 정할 수 없고 사람의 결정이 있어야 하는 것만
  (예: 어느 기관 · 어느 과제 · 몇 차년도 몫을 쓰는가 · 기준일 · 금액 단위 · 분량 · 강조할 점 · 자료가 서로 다를 때 어느 것을 따를지 · 표 줄을 무엇으로 나눌지).
  - 자료나 지침에 답이 분명히 있는 것은 묻지 않습니다. decided 에 있는 것은 묻지 않습니다. 사소한 표기는 묻지 않습니다. 가장 중요한 것부터 많아야 12개.
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
    for c in b.get("cells") or ():
        t = " ".join(x.get("text") or "" for x in iter_blocks(c.get("blocks") or ()) if x.get("type") == "paragraph").strip()
        rows.setdefault(c.get("row") or 0, []).append((c.get("col") or 0, _short(t, CELL_MAX)))
    return [" | ".join(t for _, t in sorted(cs)) for _, cs in sorted(rows.items())]


def form_text(blocks, graph, limit=FORM_MAX):
    """양식 전체 글(문서 차례) → (글, cut). 넘치면 문단을 더 짧게 줄여 다시 짓고(헤딩 줄은 늘 남긴다), 그래도 넘치면 뒤를 자른다."""
    text = ""
    for n, para_max in enumerate((PARA_MAX, 200, 100, 60)):
        text = _form_text(blocks, graph, para_max)
        if len(text) <= limit:
            return text, n > 0
    return text[:limit], True


def _form_text(blocks, graph, para_max):
    depth = {n["para"]: n.get("depth") or 1 for n in (graph or {}).get("nodes") or ()
             if isinstance(n, dict) and n.get("role") == "heading" and n.get("area") == "body" and n.get("para")}
    lines = []
    for b in blocks or ():
        if b.get("type") == "paragraph":
            t = " ".join((b.get("text") or "").split())
            if not t:
                continue
            lines.append(f"{'#' * min(6, depth[b['id']])} {_short(t, 200)} [{b['id']}]" if b["id"] in depth else _short(t, para_max))
        elif b.get("type") == "table":
            rows = _cells_rows(b)
            lines.append(f"[표 {b['id']}]" + "".join(f"\n  {r}" for r in rows[:ROWS_MAX] if r.strip(" |")) + (f"\n  … ({len(rows) - ROWS_MAX}행 더)" if len(rows) > ROWS_MAX else ""))
    return "\n".join(lines)


def _place_brief(p):
    gs, used = [], 0
    for g in sorted(p.get("guides") or (), key=lambda g: g.get("src") != "user"):
        t = _short(g.get("text"), GUIDE_MAX - used)
        if used >= GUIDE_MAX or not t:
            break
        gs.append(f"({'사람' if g.get('src') == 'user' else '양식' + (' · ' + g['kind'] if g.get('kind') else '')}) {t}")
        used += len(t)
    return {"id": p["id"], "kind": p["kind"], "text": p.get("text") or "", "depth": p.get("depth"), "guides": gs, "filled": bool(p.get("filled"))}


def sig(places):
    """자리 목록의 지문 — 검토 뒤 양식(자리 · 지침)이 바뀌었나 보인다(바뀌어도 검토 · 답은 버리지 않는다)."""
    raw = json.dumps([[p["id"], p.get("text"), [g.get("text") for g in p.get("guides") or ()]] for p in places or ()], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def payload(blocks, graph, places, decided, materials_text=""):
    text, cut = form_text(blocks, graph)
    out = {"form": text, "cut": cut, "places": [_place_brief(p) for p in places or ()],
           "decided": [{"q": d["q"], "a": d["a"]} for d in decided or () if d.get("a")]}
    if materials_text:
        out["materials"] = materials_text[:MATERIAL_MAX]
    return out


def guide_part(g=None):
    g = merge_guides.get(GUIDE) if g is None else g
    return merge_guides.part(g) or f"\n\n## 판단 지침 — 기본\n\n{FALLBACK_GUIDE}"


def prompt(data, job=None, guide=None):
    """프롬프트 글 = 계약 + 판단 지침 + 할 일 프롬프트 + 자료(JSON)."""
    return CONTRACT + guide_part(guide) + job_prompts.part(job) + "\n\n## 자료(JSON)\n" + json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def parts(job=None, guide=None):
    """에이전트 설정 · 화면 「지침」 보기에 싣는 글들(자료 빼고) — guide_fix.parts 와 같은 꼴."""
    g = merge_guides.get(GUIDE) if guide is None else guide
    out = [{"key": "contract", "title": "계약 — 역할 · 자료 설명 · 답의 꼴", "text": CONTRACT, "source": "app/form_review.py",
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
        qs.append({"key": f"q{len(qs) + 1}", "text": text, "why": _short(q.get("why"), Q_MAX), "places": [i for i in dict.fromkeys(q.get("places") or ()) if i in ids],
                   "choices": choices, "suggest": sug, "source": _short(q.get("source"), 200) if sug else ""})
    return {"summary": _short(a.get("summary"), 1200), "places": ps, "questions": qs}


def planned(review):
    """작성 계획이 있나 — 자료를 주고 한 검토(자리마다 use · gap 을 받은 것). 양식만 읽은 검토는 계획이 아니다."""
    return bool(review and review.get("materials"))


def _answered(q, decided):
    return next((d for d in decided or () if d.get("a") and (d.get("key") == q["key"] or d.get("q") == q["text"])), None)


def open_questions(review, decided):
    """아직 답하지 않은 물음들(검토가 없으면 빈 목록)."""
    return [q for q in (review or {}).get("questions") or () if _answered(q, decided) is None]


def plan_for(review, decided, place_id):
    """그 자리의 지침 작성 요청에 붙일 것 → {how, facts[(물음, 답)]} | None. facts = 그 자리에 닿는 답 + 문서 전체에 닿는 답 + 검토 밖에서 정한 것(자리 모름 — 모두에)."""
    if not review and not decided:
        return None
    qs = {q["key"]: q for q in (review or {}).get("questions") or ()}
    facts = []
    for d in decided or ():
        if not d.get("a") or d["a"] == SKIP:
            continue
        q = qs.get(d.get("key")) or next((x for x in qs.values() if x["text"] == d.get("q")), None)
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
