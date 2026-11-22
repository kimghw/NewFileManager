"""병합 — 묶음 짝 LLM 보정(spec_병합 ② §4 「LLM 보정」): 스크립트(`merge_pairs.pair`)가 못 정한 목적 묶음(ambiguous·toOnly)의 짝을 LLM 이 고른다.

흐름(division_llm 과 같은 길): 잠금 안에서 data() 로 자료(JSON)를 만들고 → 잠금 밖에서 ask() 한 번(수십 초) → check() 가 답을 **보낸 자료에 대고** 검증해
`merge_pairs.pair(..., fixed=)` 에 줄 fixed 항목(source llm)을 낸다 — 짝 결과를 여기서 고치지 않는다(스크립트가 낸 짝·사람이 고친 짝은 안 건드림).
보내는 자료 = 못 정한 목적 묶음(소속·라벨·종류·구분·맥락·표 머리·항목 값·후보) + 고를 수 있는 원본 묶음(그 구분·갈래인 것 전부 — 후보에 없는 것도 고를 수 있게)
+ 이미 정한 짝 몇 개(두 서식의 절 이름이 어떻게 대응하는지 보는 참고). 답 = decisions[{to, from("" = 짝 없음), anchor, reason}] + summary — 입력에 있는 key 만.
긴 문서는 `review()` — 목적 문서를 장(20쪽 안, `merge_chunks`)마다 나눠 Opus 로 병렬 호출하고, 단위마다 그 장의 개요·자리 글 앞부분을 함께 보낸다."""
import json
from collections import Counter

from app import division_llm, heading_forms, job_prompts, llm, merge_chunks, merge_guides, merge_pairs
from app import place_guides as PG

S = {"type": "string"}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["decisions", "tables", "summary"], "properties": {
    "decisions": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["to", "from", "anchor", "reason"],
                                             "properties": {"to": S, "from": S, "anchor": S, "reason": S}}},
    "tables": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["to", "from", "reason", "format"],
                                          "properties": {"to": S, "from": S, "reason": S, "format": S}}},
    "summary": S}}

CONTRACT = """당신은 국가R&D 사업계획서(연구개발계획서 — **원본 문서**)의 내용을 연차보고서(**목적 문서**)에 옮길 때 **어느 자리가 어느 자리와 같은 자리인지** 고르는 검토자입니다. 글을 쓰거나 옮기지 않고 짝만 고릅니다.
보는 것은 둘입니다 — ① **묶음 짝**(구분 기준이 걸린 자리 묶음끼리 — decisions) ② **표 짝**(구분 기준 묶음이 아닌 표끼리 — tables). 무엇을 같은 자리·같은 표로 보는지는 아래 「판단 지침」 을 따릅니다.

### ① 묶음 짝
구분 기준 = 단계(stage)·차년도(year)·단계-차년도(stageYear)·세부과제(sub)·기관(org — 주관, 공동1, 공동2 …). 자리 묶음 = 같은 꼴의 라벨 문단이나 표의 행·열이 구분 값마다 되풀이되는 곳
(kind: paragraph 문단 묶음 · rows 표 행 · cols 표 열 · list 목록 행). 묶음마다: path = **소속**(그 묶음을 품은 절 제목 경로, 바깥 → 안, 번호 뗌) · label = 라벨 꼴(값 낱말·기관 이름을 뺀 글) ·
table = 표 묶음이면 그 표의 행·열 머리 칸 꼴(값 낱말 뺌) · inner = 문단 묶음이면 항목 안 소제목 꼴 · values = 항목 값(n = 항목 수) ·
ctx = 맥락(year = 묶음이 통째로 속한 차년도, org = 통째로 속한 기관 이름 — 없으면 전 차년도·전 기관에 걸친 묶음).
묶음 짝 = 목적 문서의 묶음 하나 ↔ 원본 문서의 묶음 하나. 짝이 되면 그 안에서 값이 같은 항목끼리(「2차년도」 ↔ 「2차년도」) 스크립트가 원본의 내용을 목적 자리에 넣습니다.
자료: targets = 스크립트가 짝을 정하지 못한 목적 묶음(status ambiguous = 후보가 여럿이라 못 고름 · toOnly = 후보를 못 찾음, candidates = 스크립트가 낸 후보의 원본 key 와 점수),
sources = 고를 수 있는 원본 묶음 전부(candidates 에 없는 것도 고를 수 있습니다. used = 이미 다른 목적 묶음의 짝인 횟수 — 한 원본 묶음이 여러 목적 묶음의 짝일 수 있습니다),
examples = 이미 정해진 짝 몇 개(두 서식의 절 이름이 어떻게 대응하는지 보는 참고용 — 답에 넣지 않습니다).
답 decisions: targets 마다 한 줄 — {to, from, anchor, reason}.
- to·from 은 **입력에 있는 key 만** 씁니다(to = targets 의 key, from = sources 의 key 또는 "" = 짝 없음). targets 에 없는 묶음은 답하지 않습니다.
- 구분(dim)·종류(문단 묶음끼리 / 표 묶음 rows·cols·list 끼리)가 다르거나 맥락 차년도가 어긋나는 짝은 받지 않습니다(스크립트가 거릅니다).
- anchor = 문단 묶음에서 원본 내용을 넣을 자리 — 목적 묶음의 inner 가운데 하나를 글자 그대로 적으면 그 소제목 뒤에 넣습니다(예 「- (추진 내용)」). 기본값(첫 소제목 뒤, 소제목이 없으면 라벨 뒤)이
  맞으면 "" — 표 묶음과 from 을 비운 줄도 "".

### ② 표 짝
**표는 모두 읽고 정합니다** — tableTargets = 내용을 받을 칸이 있는 목적 문서의 표 **전부**(구분 기준 묶음에 안 든 칸이 있는 표 — 표지·요약문의 칸, 기관 절 안의 표, 절 아래 표), tableSources = 원본 문서의 표 **전부**입니다.
tableTargets 표마다: key = 표 id · title = 표 제목(소속 제목 줄) · path = 소속 경로 · ctx = 그 표의 맥락(org = 어느 기관의 표인지 · year = 어느 차년도의 표인지 — 없으면 과제 전체·전 차년도) ·
heads = 행·열 머리 칸 꼴 · shape = {rows, cols, splits(쪽을 넘어 나뉘는 표인가)} · status(none = 스크립트가 같은 표를 못 정함 · ambiguous = 스크립트 후보가 여럿 · paired = 스크립트가 이미 이음 — paired = 그 원본 표 key) ·
why(스크립트가 안 이은 까닭 — org·year = 머리는 같은데 기관·차년도가 다른 표가 있었음) · candidates = 스크립트가 머리 글자의 겹침으로 추린 **참고 후보**(key 와 겹침 점수 — 비어 있을 수 있습니다).
candidates 는 참고일 뿐입니다 — **후보에 없는 표도 tableSources 에서 찾아 고릅니다**(머리 글자가 달라 스크립트가 못 추린 같은 표가 있습니다). 후보가 비어 있어도 tableSources 를 모두 읽고 판단합니다.
tableSources 표마다: 같은 꼴의 설명(status·why·candidates 없음) + same = **이 표와 머리·소속 제목이 같은 꼴로 되풀이되는 다른 표들**(기관마다·차년도마다 한 표씩 있는 표 — [{key, ctx, rows(행 수), title?}]):
같은 꼴 표가 여럿이면 그 가운데 **목적 표와 기관·차년도가 맞는 표의 key** 를 고릅니다(맨 앞 표의 key 를 그냥 쓰지 않습니다). 이 단위의 모든 목적 표와 기관·차년도가 어긋나는 원본 표는 실리지 않습니다(sourcesLeft = 상한에 걸려 못 실은 수).
짝이 되면 스크립트가 두 표에서 **행·열 머리 경로가 같은 칸끼리** 원본 글을 목적의 빈 칸에 옮기고 서식(칸의 글자 모양·문단 모양, 쪽 나눔)을 맞춥니다 — 행·열 구성이 다른 표는 그 뒤 「표 대응」 이 행·열을 맞춥니다(같은 내용을 적는 표면 구성이 달라도 잇습니다).
답 tables: tableTargets 마다 한 줄 — {to, from, reason, format}. to = tableTargets 의 key, from = tableSources 의 key(same 에 든 key 포함) 또는 ""(같은 표 없음). **입력에 있는 key 만** 씁니다.
status 가 paired 인 표는 스크립트 짝이 맞으면 from 에 그 paired key 를 그대로 적고, 다른 표가 맞으면 그 표의 key 를 적습니다("" 로 답하면 스크립트 짝을 그대로 둡니다).
기관(ctx.org)이나 차년도(ctx.year)가 서로 어긋나는 짝은 받지 않습니다. format = 두 표의 서식·모양 차이 가운데 사람이 확인해야 할 것 한 문장("" = 없음). tableTargets 가 없으면 tables 는 [].

### 공통
- **확신이 없으면 from 을 비웁니다**("" — 틀린 짝은 엉뚱한 내용을 문서에 넣게 되고, 비워 두면 사람이 정합니다).
- reason = 그렇게 본 근거 한 문장(한국어 — 어느 소속·라벨·표 머리·기관·차년도를 보고). summary = 전체 판단 두세 문장."""

# 지침 파일이 없을 때(끔·지움)만 붙는 최소 기준 — 지침의 원본은 app/merge_guides_default/links.md(merge_guides).
FALLBACK_GUIDE = """

## 판단 기준(지침 파일 없음 — 기본)
- 같은 내용을 적는 자리끼리만 잇습니다. 두 서식은 절 제목이 다르므로 글자가 아니라 뜻으로 봅니다. 연차보고서에만 있는 자리(실적·성과)는 짝이 없습니다.
- 맥락 기관(ctx.org)·맥락 차년도(ctx.year)가 둘 다 있으면 같아야 합니다. 특정 기관·특정 차년도의 표는 같은 기관·같은 차년도의 표하고만 잇습니다.
- 행·열 머리가 같은 뜻이고 적는 내용이 같으면 같은 표입니다. 머리 구성이 다른 표는 소속이 비슷해도 짝이 아닙니다."""

GUIDE = "links"   # merge_guides 의 지침 이름

# 양식 정보(spec_헤딩_추출 ② §12 — forms/<양식 키>.md)를 붙일 때의 머리 문장. 두 문서의 양식이 다르면 양식마다 한 절.
FORM_NOTE = ("아래는 두 문서 가운데 **이 양식의 문서**에 대해 사용자가 따로 관리하는 사실·요청입니다(헤딩 추출·표·구분 기준과 함께 쓰는 글이라 짝짓기와 무관한 절은 배경 지식으로만 읽으세요). "
             "어느 절·표가 무슨 내용을 적는 자리인지 판단할 때 참고하고, 짝에 대해 적힌 것(어느 자리가 다른 문서의 어느 자리와 같은지 · 짝이 없는 자리)은 위 판단 기준보다 먼저 따릅니다. "
             "답의 꼴과 「입력에 있는 key 만」 은 위 계약을 따릅니다.")

UNDECIDED = ("ambiguous", "toOnly")
# 자료 크기 상한 — 실제 쌍(계획서 묶음 66 · 연차보고서 묶음 79)은 다 들어간다. 넘치면 후보가 있는 것부터 보내고 남은 수를 left 로 알린다.
TARGETS_MAX, SOURCES_MAX, EXAMPLES_MAX, CANDS_MAX = 60, 150, 8, 5
PATH_MAX, PATH_LEN, LABEL_LEN, SIG_MAX, SIG_LEN, INNER_MAX, INNER_LEN, VALUES_MAX = 4, 40, 60, 16, 20, 6, 60, 12

_short = division_llm._short


def family(kind):
    """갈래 — 문단 묶음끼리 / 표 묶음(rows·cols·list)끼리 짝이다(② §4)."""
    return "paragraph" if kind == "paragraph" else "table"


def _dim(dim):
    """구분 갈래 — 차년도·단계-차년도는 한 갈래(merge_pairs.score 와 같음: 항목은 전체 차례 차년도 ident 로 맞춘다)."""
    return "year" if dim in merge_pairs.YEARLY else dim


def _where(x):
    return {"path": [_short(p, PATH_LEN) for p in (x.get("path") or [])[-PATH_MAX:]], "label": _short(x.get("label"), LABEL_LEN)}


def _brief(s):
    """묶음 요약 하나 → 보낼 꼴(key 와 문서와 무관한 글만). inner 는 자르지 않는다(anchor 로 그대로 돌아와야 하므로 — 긴 것은 뺌)."""
    items = s.get("items") or []
    out = {"key": s["key"], "dim": s["dim"], "kind": s["kind"], **_where(s), "values": [it.get("value") for it in items[:VALUES_MAX]], "n": len(items)}
    if ctx := {k: v for k, v in (s.get("ctx") or {}).items() if v is not None}:
        out["ctx"] = ctx
    if s.get("table"):
        out["table"] = [_short(x, SIG_LEN) for x in (s["table"].get("sig") or [])[:SIG_MAX]]
    if inner := [x for x in s.get("inner") or () if len(x) <= INNER_LEN][:INNER_MAX]:
        out["inner"] = inner
    return out


def _cap(rows, n, first):
    """n 개까지 — 넘치면 first(row) 가 참인 것부터 고르되 차례(문서 순)는 지킨다."""
    if len(rows) <= n:
        return rows
    keep = {id(r) for r in sorted(rows, key=lambda r: not first(r))[:max(0, n)]}
    return [r for r in rows if id(r) in keep]


def data(pairs, to_groups, from_groups, *, limit=TARGETS_MAX):
    """LLM 에 보낼 자료(JSON 으로 낼 dict). pairs = `merge_pairs.pair` 결과, to_groups·from_groups = 두 문서의 묶음 요약(`merge_pairs.summarize`).
    → {"targets": [못 정한 목적 묶음 — _brief + status + candidates[{key, score}]], "sources": [고를 수 있는 원본 묶음 — _brief(+ used)],
       "examples": [{dim, kind, to{path, label}, from{path, label}}], "left": limit 에 걸려 못 보낸 목적 묶음 수}.
    사람이 고친 묶음(source user — 끊은 것 포함)은 보내지 않는다. targets 가 비면 부를 것이 없다."""
    to_by, from_by = {s["key"]: s for s in to_groups}, {s["key"]: s for s in from_groups}
    groups = pairs.get("groups") or []
    und = [g for g in groups if g.get("status") in UNDECIDED and g.get("source") != "user" and (g.get("to") or {}).get("key") in to_by]
    picked = _cap(und, limit, lambda g: g["status"] == "ambiguous")
    listed = {c.get("key") for g in picked for c in (g.get("candidates") or [])[:CANDS_MAX]}
    want = {(_dim(to_by[g["to"]["key"]]["dim"]), family(to_by[g["to"]["key"]]["kind"])) for g in picked}
    pool = _cap([s for s in from_groups if (_dim(s["dim"]), family(s["kind"])) in want], SOURCES_MAX, lambda s: s["key"] in listed)
    sent = {s["key"] for s in pool}
    used = Counter(g["from"]["key"] for g in groups if g.get("status") == "paired" and g.get("from"))
    targets = [{**_brief(to_by[g["to"]["key"]]), "status": g["status"],
                "candidates": [{"key": c["key"], "score": c.get("score")} for c in (g.get("candidates") or [])[:CANDS_MAX] if c.get("key") in sent]} for g in picked]
    sources = [{**_brief(s), **({"used": used[s["key"]]} if used[s["key"]] else {})} for s in pool]
    examples, seen = [], set()
    paired = [g for g in groups if g.get("status") == "paired" and g.get("to") and g.get("from")]
    for g in sorted(paired, key=lambda g: g.get("source") not in ("user", "saved")):   # 사람이 확정한 짝부터, 소속이 서로 다른 것으로
        k = tuple(g["to"].get("path") or ())
        if k not in seen and len(examples) < EXAMPLES_MAX:
            seen.add(k)
            examples.append({"dim": g.get("dim"), "kind": g.get("kind"), "to": _where(g["to"]), "from": _where(g["from"])})
    return {"targets": targets, "sources": sources, "examples": examples, "left": len(und) - len(picked)}


def guide_part(guide=None):
    """프롬프트의 지침 절 — guide = merge_guides.get 꼴(None = 지금의 `links` 지침을 읽음, False = 지침 없이). 지침 파일이 없으면 최소 기준(FALLBACK_GUIDE)."""
    if guide is False:
        return FALLBACK_GUIDE
    return merge_guides.part(merge_guides.get(GUIDE) if guide is None else guide) or FALLBACK_GUIDE


def prompt(payload, form=None, note="", job=None, guide=None, links=""):
    """프롬프트 글 = 계약 + note + 판단 지침 절 + 할 일 프롬프트 절 + 양식 정보 절 + 자료(JSON) → (글, 실제로 보낸 양식 [{key, name, sha1} …]).
    form = 양식 정보(heading_forms.pin 꼴) 하나 또는 [원본 문서 것, 목적 문서 것] — 보낼 글이 있는 것마다 한 절(같은 양식은 한 번).
    job = 이 작업의 할 일 프롬프트(job_prompts.get 꼴 | None — spec_작업 ② §13): 보낼 글이 있으면 지침 바로 뒤 한 절(보낸 것의 기록은 job_prompts.brief).
    guide = 판단 지침(guide_part — 기본은 app/merge_guides_default/links.md 를 부를 때마다 읽음).
    links = 목적 양식의 양식 정보 「자리 연결」 절 글(연결 코멘트 — spec_병합 ② §5-3 1: 사용자가 「어느 표·단락을 어디와 이을지」 적어 둔 것) — 할 일 프롬프트 바로 뒤 한 절."""
    from app import merge_table_map   # 「자리 연결」 절의 머리 문장은 표 대응 에이전트와 같은 글을 쓴다(늦게 가져온다 — 그 모듈이 merge_fixed 를 끌어온다)
    forms, parts = [], []
    for f in form if isinstance(form, (list, tuple)) else [form]:
        part = division_llm.form_part(f, FORM_NOTE) if f else ""
        if part and all(x["key"] != f.get("key") for x in forms):
            forms.append({k: f.get(k) for k in ("key", "name", "sha1")})
            parts.append(part)
    return (CONTRACT + note + guide_part(guide) + job_prompts.part(job) + merge_table_map.links_part(links) + "".join(parts)
            + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")), forms)


def parts(form=None, job=None, guide=None, links=""):
    """화면의 「지침」 보기에 싣는 것 — 이 검토의 프롬프트를 이루는 글들(자료 빼고) [{key: contract|guide|job|form, title, text, source, note}]. prompt() 와 같은 차례."""
    g = merge_guides.get(GUIDE) if guide is None else guide
    out = [{"key": "contract", "title": "계약 — 역할 · 자료 설명 · 답의 꼴", "text": CONTRACT + UNIT_NOTE, "source": "app/merge_llm.py",
            "note": "코드에 든 글입니다(답을 검증하는 코드와 한 몸) — 판단 기준은 아래 지침에 있습니다"}]
    if g and merge_guides.body(g):
        out.append({"key": "guide", "title": f"판단 지침 — {g['title']}", "text": merge_guides.body(g), "source": g["path"], "note": "이 파일을 고치면 다음 실행부터 적용됩니다"})
    else:
        out.append({"key": "guide", "title": "판단 지침 — (지침 파일 없음: 기본 기준)", "text": FALLBACK_GUIDE.strip(), "source": "app/merge_llm.py", "note": "app/merge_guides_default/links.md 가 없어 기본 기준만 보냅니다"})
    if job and job_prompts.part(job):
        out.append({"key": "job", "title": f"할 일 프롬프트 — {job['name']}", "text": job_prompts.body(job["text"]), "source": job["path"],
                    "note": "이 작업의 전제(무엇이 원본·목적인지, 무엇을 넣는지) — 이 파일을 고치면 다음 실행부터 적용됩니다"})
    if (links or "").strip():
        out.append({"key": "form", "title": "양식 정보 — 「자리 연결」 절(연결 코멘트)", "text": links.strip(), "source": "",
                    "note": "어느 표·단락을 어디와 이을지 사용자가 적어 둔 것 — 2단계 묶음의 연결 코멘트 칸이나 「양식 정보」 에서 고칩니다"})
    seen = set()
    for f in form if isinstance(form, (list, tuple)) else [form]:
        if f and division_llm.form_part(f, FORM_NOTE) and f.get("key") not in seen:
            seen.add(f.get("key"))
            out.append({"key": "form", "title": f"양식 정보 — {f.get('name') or f.get('key')}", "text": heading_forms.body(f.get("text")), "source": "", "note": "양식마다 관리하는 사실·요청(헤딩 추출·구분 기준과 함께 쓰는 글 — 「양식 정보」 에서 고칩니다)"})
    return out


def ask(payload, *, call=None, effort="medium", timeout=240.0, form=None, job=None):
    """한 번 호출(잠금 밖) → {"data": 응답 | None, "prompt", "call": {backend, model, effort, ms, costUsd, error}, "form": [{key, name, sha1} …], "job": {job, name, sha1} | None}.
    form·job 은 prompt() 와 같고, 결과의 form 은 실제로 보낸 것의 목록(없으면 [] — 문서가 둘이라 division_llm 과 달리 목록), job 은 실제로 보낸 할 일 프롬프트."""
    content, forms = prompt(payload, form, job=job)
    res = (call or llm.call)(SCHEMA, content, "merge-llm", timeout=timeout, effort=effort)
    return {"data": res.get("data"), "prompt": content, "call": {k: res.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error")}, "form": forms,
            "job": job_prompts.brief(job)}


def check(payload, answer):
    """응답(ask 의 data)을 보낸 자료에 대고 검증 → {"fixed": {to key: {"from": 원본 key, "source": "llm", "anchor": 소제목 꼴 | None, "reason"}},
    "rejected": [{…답 그대로, "why"}], "none": [{"to", "status", "reason"}]}.
    받는 것: to 가 targets 에 있고(= 못 정한 묶음만 — 이미 짝이 있는 묶음은 거절) from 이 sources 에 있고 구분·갈래가 같고 맥락 차년도가 어긋나지 않는 것, 묶음마다 한 번.
    from 이 빈 답은 fixed 를 내지 않는다 — toOnly 는 「짝 없음」, ambiguous 는 그대로 「확인 필요」(none 에 까닭만 남김). anchor 는 그 목적 묶음의 inner 에 있는 글만(아니면 기본값 None)."""
    targets = {t["key"]: t for t in payload.get("targets") or ()}
    sources = {s["key"]: s for s in payload.get("sources") or ()}
    fixed, rejected, none = {}, [], []
    for r in (answer or {}).get("decisions") or ():
        if not isinstance(r, dict):
            continue
        to, frm, reason = str(r.get("to") or ""), str(r.get("from") or ""), str(r.get("reason") or "").strip()[:300]
        t, s = targets.get(to), sources.get(frm)
        if t is None:
            why = "보정 대상이 아닌 묶음(이미 짝이 있거나 입력에 없는 key)"
        elif to in fixed or any(n["to"] == to for n in none):
            why = "같은 묶음을 두 번"
        elif not frm:
            none.append({"to": to, "status": t["status"], "reason": reason})
            continue
        elif s is None:
            why = "입력에 없는 원본 key"
        elif _dim(s["dim"]) != _dim(t["dim"]):
            why = "구분이 다름"
        elif family(s["kind"]) != family(t["kind"]):
            why = "종류가 다름(문단 묶음 ↔ 표 묶음)"
        elif (clash := _table_clash(t, s)) is not None:   # 둘 다 알고 다른 기관 · 차년도(표와 같은 기준 — spec_병합 ② §5-11 G4: 전에는 차년도만 봐 다른 기관의 같은 이름 절이 짝으로 들어왔다)
            why = "맥락 차년도가 다름" if clash == "year" else "맥락 기관이 다름"
        else:
            anchor = str(r.get("anchor") or "").strip()
            fixed[to] = {"from": frm, "source": "llm", "anchor": anchor if anchor in (t.get("inner") or ()) else None, "reason": reason}
            continue
        rejected.append({**r, "why": why})
    return {"fixed": fixed, "rejected": rejected, "none": none}


TABLE_TARGETS_MAX, TABLE_SOURCES_MAX = 60, 400   # 단위 하나에 보내는 목적 표 수 · 원본 표 수(same 에 묶인 표 포함 — 실제 쌍: 목적 표 84 · 원본 표 256)
SOURCE_TABLE_LINES = 2   # 스크립트 후보가 아닌 원본 표의 excerpt 줄 수(표 제목 줄 + 첫 행) — 후보는 TARGET_LINES 줄


def _table_clash(t, s):
    """목적 표 t 와 원본 표 s 의 맥락이 어긋나는가 → "org"|"year"|None — 둘 다 알고 다를 때만(merge_fixed._ctx_clash 와 같은 규칙: 보낸 자료의 ctx 로 본다)."""
    a, b = t.get("ctx") or {}, s.get("ctx") or {}
    return next((k for k in ("org", "year") if a.get(k) is not None and b.get(k) is not None and a[k] != b[k]), None)


def _fold(rows, hints, excerpt):
    """원본 표 목록(merge_fixed.review_tables 의 sources 꼴 — form 포함)을 보낼 꼴로 → [{key, title, path, ctx, heads, shape, excerpt, same?}].
    같은 꼴 표(form 이 같음 — 머리 꼴·소속 제목 꼴이 같은 표: 기관마다·차년도마다 되풀이되는 표)는 **첫 표 한 줄에 묶는다**(same[{key, ctx, rows, title?}] — title 은 묶은 줄의 제목과 다를 때만: 제목에 적힌 기관 이름이 표를 가른다).
    스크립트 후보(hints)는 묶지 않고 제 줄로 싣는다(excerpt 가 길다 — TARGET_LINES 줄). 그 밖은 SOURCE_TABLE_LINES 줄. excerpt = (표 id, 줄 수) → 글 줄 목록."""
    out, head = [], {}
    for s in rows:
        f = s.get("form")
        if f and f in head and s["key"] not in hints:
            ctx = {k: v for k, v in (s.get("ctx") or {}).items() if v is not None}
            head[f].setdefault("same", []).append({"key": s["key"], "ctx": ctx, "rows": (s.get("shape") or {}).get("rows"), **({} if s.get("title") == head[f].get("title") else {"title": s.get("title")})})
            continue
        row = {**{k: v for k, v in s.items() if k != "form"}, "excerpt": excerpt(s["key"], TARGET_LINES if s["key"] in hints else SOURCE_TABLE_LINES)}
        out.append(row)
        if f:
            head.setdefault(f, row)
    return out


def check_tables(payload, answer):
    """표 짝 답(ask 의 data["tables"])을 보낸 자료에 대고 검증 → {"fixed": {목적 표 id: {"from": 원본 표 id, "source": "llm", "reason", "format"}}, "rejected": [{…답, "why"}],
    "none": [{"to", "reason"}], "kept": [목적 표 id — 스크립트 짝 그대로]}. 받는 것: to 가 tableTargets 에 있고 from 이 tableSources 에(same 에 묶인 표 포함) 있고 **맥락(기관·차년도)이 어긋나지 않는** 것
    (둘 다 알고 다르면 거절), 표마다 한 번. from 이 빈 답은 fixed 를 내지 않는다(none 에 까닭만).
    스크립트가 이미 이은 표(tableTargets 의 paired)는 답이 그 표 그대로이거나 비었으면 kept(스크립트 짝 그대로 — fixed 를 내지 않는다 · 앞선 LLM 짝은 지운다: merge_api), 다른 표를 고르면 fixed(스크립트보다 먼저 쓴다)."""
    targets = {t["key"]: t for t in payload.get("tableTargets") or ()}
    sources = {}
    for s in payload.get("tableSources") or ():
        sources[s["key"]] = s
        for m in s.get("same") or ():
            sources.setdefault(m["key"], {**s, **m})   # 같은 꼴로 묶인 표 — 맥락은 그 표의 것
    fixed, rejected, none, kept = {}, [], [], []
    for r in (answer or {}).get("tables") or ():
        if not isinstance(r, dict):
            continue
        to, frm, reason = str(r.get("to") or ""), str(r.get("from") or ""), str(r.get("reason") or "").strip()[:300]
        t, s = targets.get(to), sources.get(frm)
        if t is None:
            why = "검토 대상이 아닌 표(이미 짝이 있거나 입력에 없는 key)"
        elif to in fixed or to in kept or any(n["to"] == to for n in none):
            why = "같은 표를 두 번"
        elif t.get("paired") and frm in ("", t["paired"]):
            kept.append(to)
            continue
        elif not frm:
            none.append({"to": to, "reason": reason})
            continue
        elif s is None:
            why = "입력에 없는 원본 표 key"
        elif clash := _table_clash(t, s):
            why = "기관이 다른 표" if clash == "org" else "차년도가 다른 표"
        else:
            fixed[to] = {"from": frm, "source": "llm", "reason": reason, "format": str(r.get("format") or "").strip()[:200]}
            continue
        rejected.append({**r, "why": why})
    return {"fixed": fixed, "rejected": rejected, "none": none, "kept": kept}


# ---- 장별 병렬 검토(2026-11-11 사용자 "LLM으로 검토할 떄는 멀티에이전트로 챕터별로 해줘. 20페이지 내로 나눠서 검토하면 좋을듯." · "opus 모델로") ----------

MODEL = "claude-opus-5-5"   # env NFM_LLM_MODEL 과 무관하게 이 검토는 Opus(llm.call 의 model 이 env 보다 먼저)
TARGET_LINES, SOURCE_LINES = 8, 4   # excerpt 줄 수(줄마다 merge_chunks.LINE_LEN 자) — 단위 하나의 자료 = 목적 묶음 60 · 원본 묶음 150 · 개요 40줄 이하
UNIT_NOTE = """

## 검토 단위
목적 문서가 길어 장(chapter) 단위로 나눠 여러 검토자가 나눠 봅니다 — 이 자료의 targets·tableTargets 는 **이 단위에 든 목적 묶음·표만**입니다(다른 단위의 것은 답하지 않습니다).
chapter = 이 단위의 제목 · pages(추정 쪽 — 첫 쪽, 끝 쪽) · outline(단위 안 본문 헤딩 「레터 글」, 문서 순, 같은 줄은 한 번 — outlineLeft = 못 실은 줄 수).
targets·sources 의 excerpt = 그 자리의 **실제 글 앞부분**: 문단 묶음은 첫 항목의 라벨 줄부터 이어지는 줄, 표 묶음은 표 바로 앞 줄(표 제목)과 표의 앞 행들(한 행의 칸은 「 | 」 로 이음). 긴 줄은 「…」 로 잘렸습니다.
tableTargets·tableSources 의 excerpt = 그 표 바로 앞 줄(표 제목)과 표의 앞 행들 — tableSources 는 원본 문서의 표 전부라, 스크립트 후보가 아닌 표의 excerpt 는 짧습니다(표 제목 줄과 첫 행 — 머리 줄). same 에 묶인 표는 excerpt 가 없습니다(묶은 표와 같은 꼴).
원본(sources·tableSources)의 excerpt 는 계획서에 실제로 적힌 내용이라 그 자리에 무엇을 적는지 보여 줍니다. 소속·라벨·표 머리만으로 뜻이 갈리지 않으면 excerpt 로 판단하십시오. 판단 기준·답의 꼴은 위 계약 그대로입니다."""


def _anchor(s):
    """묶음 요약의 자리 블록 id — 표 묶음은 그 표, 문단 묶음은 첫 항목 라벨."""
    return (s.get("table") or {}).get("id") or next((it["id"] for it in s.get("items") or () if it.get("id")), s["key"])


def review(to_side, from_side, pairs, to_groups, from_groups, *, pages=merge_chunks.PAGES, ask=None, model=MODEL, effort="medium", timeout=600.0, form=None, job=None,
           tables=None, guide=None, links="", places=None, again=()):
    """places = 자리 → 작성 지침(place_guides.resolver — 「group」 묶음 요약 · 「table」 목적 표 id): 주면 targets · tableTargets 마다 `guides`(+ 자른 수 guidesCut)를 싣고 계약에 그 한 줄을 붙인다(spec_병합 ② §5-11) ·
    결과의 `sigs` {groups{key: 판}, tables{key: 판}} = 물을 때 그 자리의 지침 판(자르기 전 — 부르는 쪽이 늦은 답 · 다음 실행의 다시 묻기를 가른다).
    again = 이미 LLM 짝이 있어도 다시 물을 목적 묶음 key(그 짝을 낸 뒤 그 자리의 지침이 바뀜 — 짝을 지우지 않고 다시 묻는다: astra 3차).
    못 정한 목적 묶음과 **못 정한 표**를 **목적 문서의 장(쪽 상한 pages 안)마다 한 호출**로 나눠 병렬로 보정한다(잠금 밖 — 호출이 수십 초~수 분).
    to_side·from_side = {"blocks": 문서 blocks(), "graph": 2단계 결과}, pairs = `merge_pairs.pair` 결과, to_groups·from_groups = `merge_pairs.summarize`.
    tables = 표 짝 검토 자료(`merge_fixed.review_tables` — {"targets": [{key, title, path, ctx, heads, shape, status, why, candidates, paired?}], "sources": [{key, …, form}]} | None = 표는 안 봄).
    **표는 모두 읽고 정한다**(2026-11-22 사용자 "테이블 매칭을 LLM이 모두 읽고 하길 바램"): 단위마다 그 단위의 목적 표 **전부**(후보가 없는 표 · 스크립트가 이은 표도)와 **원본 문서의 표 전부**를 보낸다 —
    그 단위의 모든 목적 표와 기관·차년도가 어긋나는 원본 표만 빼고, 같은 꼴 표는 한 줄로 묶어(_fold). 전에는 후보가 있는 목적 표와 후보로 든 원본 표만 보냈다.
    ask = llm.ask_all 대신(시험). 단위 = merge_chunks.units, 묶음·표는 자리 블록(_anchor · 표 id)이 든 단위로. 단위마다 data() 를 그 단위 targets 로 좁힌 자료 +
    chapter{title, pages, outline} + targets·sources 의 excerpt + 그 단위의 tableTargets·tableSources(excerpt 포함 — 스크립트 후보는 길게)를 보내고, 답은 **그 단위에 보낸 자료에 대고**
    check()·check_tables() 한다(다른 단위 key 는 거절).
    → {"fixed", "rejected"[+unit], "none" — check() 를 합친 것, "tables": {"fixed": {목적 표 id: {from, source, reason, format}}, "rejected", "none", "kept"} — check_tables() 를 합친 것,
       "units": [{title, pages, over, targets, tables(보낸 표 수), call{backend, model, effort, ms, costUsd, error, retried} | None(부르지 않음), prompt, answer}],
       "left": 상한에 걸려 못 보낸 수, "form", "job": 단위마다 함께 보낸 할 일 프롬프트 {job, name, sha1} | None, "guide": 함께 보낸 지침 {name, title, sha1} | None}.
    한 단위의 호출이 실패해도 다른 단위의 결과는 남는다(그 단위 call.error).
    job = 이 작업의 할 일 프롬프트(job_prompts.get 꼴 — spec_작업 ② §13) · guide = 판단 지침(guide_part): 모든 단위의 프롬프트에 같은 절로 붙는다.
    결과의 prompt 는 크다(단위마다 수십 KB) — merge.json 에는 안 싣고 따로 둔다(merge_api — 화면의 「마지막으로 보낸 프롬프트」)."""
    to_by, from_by = {s["key"]: s for s in to_groups}, {s["key"]: s for s in from_groups}
    us = merge_chunks.units(to_side["blocks"], to_side["graph"], pages=pages)
    at, at_from = merge_chunks.index(to_side["blocks"]), merge_chunks.index(from_side["blocks"])
    groups = pairs.get("groups") or []
    again = set(again or ())
    redo = lambda g_: g_.get("status") in UNDECIDED or (g_.get("source") == "llm" and (g_.get("to") or {}).get("key") in again)  # noqa: E731 — 못 정한 묶음 + 지침이 바뀐 자리의 LLM 짝
    und = [g["to"]["key"] for g in groups if redo(g) and g.get("source") != "user" and (g.get("to") or {}).get("key") in to_by]
    where = merge_chunks.assign(us, at, [_anchor(to_by[k]) for k in und])
    tt = list((tables or {}).get("targets") or ())   # 남는 칸이 있는 목적 표 전부 — 후보가 없는 표도 LLM 이 원본 표를 모두 읽고 정한다
    ts_all = list((tables or {}).get("sources") or ())   # 원본 문서의 표 전부(문서 차례)
    twhere = merge_chunks.assign(us, at, [t["key"] for t in tt])
    g = merge_guides.get(GUIDE) if guide is None else guide
    out = {"fixed": {}, "rejected": [], "none": [], "tables": {"fixed": {}, "rejected": [], "none": [], "kept": []}, "units": [], "left": 0, "form": [], "job": job_prompts.brief(job),
           "guide": merge_guides.brief(g) if g else None, "sigs": {"groups": {}, "tables": {}}}
    sent, jobs = [], []
    for i, u in enumerate(us):
        row = {"title": u["title"], "pages": u["pages"], "over": u["over"], "targets": 0, "tables": 0, "call": None}
        out["units"].append(row)
        keys = {k for k, w in zip(und, where) if w == i}
        mine = [t for t, w in zip(tt, twhere) if w == i]
        if not keys and not mine:
            continue
        p = data({"groups": [({**g_, "status": "ambiguous", "candidates": [{"key": (g_.get("from") or {}).get("key"), "score": None}, *(g_.get("candidates") or [])]}
                              if g_.get("status") not in UNDECIDED and (g_.get("to") or {}).get("key") in keys and g_.get("from") else g_)   # 다시 묻는 LLM 짝은 「확인 필요」 로 보낸다(그 짝의 원본이 후보 맨 앞)
                                for g_ in groups if g_.get("status") not in UNDECIDED or (g_.get("to") or {}).get("key") in keys]}, to_groups, from_groups)
        lines, more = merge_chunks.outline(to_side["graph"], at, u)
        p["chapter"] = {"title": u["title"], "pages": u["pages"], "outline": lines, **({"outlineLeft": more} if more else {})}
        for t in p["targets"]:
            t["excerpt"] = merge_chunks.excerpt(at, _anchor(to_by[t["key"]]), TARGET_LINES)
        for s in p["sources"]:
            s["excerpt"] = merge_chunks.excerpt(at_from, _anchor(from_by[s["key"]]), SOURCE_LINES)
        if mine:
            picked = _cap(mine, TABLE_TARGETS_MAX, lambda t: t["status"] != "paired")   # 넘치면 스크립트가 못 정한 표부터
            hints = {c["key"] for t in picked for c in t["candidates"]} | {t["paired"] for t in picked if t.get("paired")}   # 스크립트 후보 · 스크립트 짝 — excerpt 를 길게
            fit = [s for s in ts_all if any(not _table_clash(t, s) for t in picked)]   # 이 단위의 모든 목적 표와 기관·차년도가 어긋나는 원본 표는 고를 수 없다 — 뺀다
            kept = _cap(fit, TABLE_SOURCES_MAX, lambda s: s["key"] in hints)
            shown = {s["key"] for s in kept}
            p["tableTargets"] = [{**t, "candidates": [c for c in t["candidates"] if c["key"] in shown], "excerpt": merge_chunks.excerpt(at, t["key"], TARGET_LINES)} for t in picked]
            p["tableSources"] = _fold(kept, hints, lambda k, n: merge_chunks.excerpt(at_from, k, n))
            if len(fit) > len(kept):
                p["sourcesLeft"] = len(fit) - len(kept)
            out["left"] += len(mine) - len(picked)
        note = UNIT_NOTE
        if places is not None:   # 자리마다의 작성 지침(② §5-11) — 묶음은 항목 모두에게 있는 것만 · 한 호출의 합을 자른다
            for t in p["targets"]:
                gs = places("group", to_by[t["key"]])
                out["sigs"]["groups"][t["key"]] = PG.sig(gs)
                if gs:
                    t["guides"] = gs
            for t in p.get("tableTargets") or ():
                gs = places("table", t["key"])
                out["sigs"]["tables"][t["key"]] = PG.sig(gs)
                if gs:
                    t["guides"] = gs
            places_cut = PG.budget([*p["targets"], *(p.get("tableTargets") or ())])
            row["guides"] = sum(1 for t in [*p["targets"], *(p.get("tableTargets") or ())] if t.get("guides"))
            if places_cut:
                row["guidesCut"] = places_cut
            if row["guides"]:
                note += PG.CONTRACT_LINE
        content, out["form"] = prompt(p, form, note, job, g if g else False, links)
        row.update(targets=len(p["targets"]), tables=len(p.get("tableTargets") or ()), prompt=content)
        out["left"] += p["left"]
        sent.append((i, row, p))
        jobs.append({"schema": SCHEMA, "content": content, "what": f"merge-llm-{i + 1}", "timeout": timeout, "effort": effort, "model": model})
    for (i, row, p), r in zip(sent, (ask or llm.ask_all)(jobs) if jobs else []):
        row["call"] = {k: r.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error", "retried")}
        row["answer"] = r.get("data")
        if r.get("data") is None:
            continue
        c = check(p, r["data"])
        out["fixed"].update(c["fixed"])
        out["rejected"] += [{**x, "unit": i} for x in c["rejected"]]
        out["none"] += c["none"]
        ct = check_tables(p, r["data"])
        out["tables"]["fixed"].update(ct["fixed"])
        out["tables"]["rejected"] += [{**x, "unit": i} for x in ct["rejected"]]
        out["tables"]["none"] += ct["none"]
        out["tables"]["kept"] += ct["kept"]
    return out
