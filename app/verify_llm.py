"""검증 LLM 검토(spec_hwpx_웹편집 ② §4-1) — 가져오기·출력파일 검증의 스크립트 단계가 끝난 뒤, 주의·실패 단계를 LLM 이 다시 보고
다름이 **실제 문제**인지 **기준 PDF 쪽 사정**(한글·Word 출력의 특성)인지 가려 그 단계 상태에 반영한다.
사용자 2026-11-16 "검증은 LLM 이 처리 하도록 해줘" → 답 「주의·실패 단계 모두」 · 「주의·실패 나면 저절로」 · 「상태를 바꾼다」.

- 측정은 스크립트 그대로 — LLM 은 대상 단계(주의·실패)마다 verdict(real · reference · mixed · unclear)와 상태를 **고르기만** 하고, 반영은 `apply` 가 검사한다:
  verdict 마다 둘 수 있는 상태(`ALLOWED`) · 스크립트 상태보다 무겁게 올리지 않음 · 모르는 key · 빠진 대상은 스크립트 그대로(`rejected`).
- 입력에는 통과·건너뜀 단계도 맥락으로, 단계마다 **스크립트가 판정하지 못한 것**(`unjudged` · 건너뛴 까닭)도 싣는다.
- 판단 기준은 `app/merge_guides_default/verify.md`(사람이 고치는 글 — merge_guides). 끄기 = env `NFM_VERIFY_LLM=off`(시험은 끈다).
- `review(job, fmt)` = verify.run_flow 의 마지막 단계 「LLM 검토」(키 `llm`) 몸통 — 예외를 내지 않고 단계에 적는다."""
import json
import os

from app import llm, merge_guides, pdf_render

KEY = "llm"
GUIDE = "verify"
WHAT = "verify-llm"
VERDICTS = ("real", "reference", "mixed", "unclear")
VERDICT_KO = {"real": "실제 문제", "reference": "기준 쪽 사정", "mixed": "섞임", "unclear": "판단 못 함"}
STATUS_KO = {"ok": "통과", "warn": "주의", "fail": "실패", "skip": "건너뜀"}
RANK = {"ok": 0, "warn": 1, "fail": 2}
ALLOWED = {"reference": ("ok", "warn"), "mixed": ("warn", "fail"), "real": ("warn", "fail")}   # unclear = 스크립트 그대로
LIST_MAX, TEXT_MAX, DEPTH_MAX, REASON_MAX = 12, 200, 6, 400   # 깊이: data › fonts › faces › 줄 › pdf·bold 가 5단 — 그보다 깊게만 줄인다
TIMEOUT, EFFORT = 180.0, "medium"
_PLAIN = ("key", "title", "about", "status", "detail", "seconds", "t0", "script", "llm")   # 자료(data)에 다시 싣지 않는 단계 키

S_ = {"type": "string"}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["steps", "summary"], "properties": {
    "steps": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["key", "verdict", "status", "reason"], "properties": {
        "key": S_, "verdict": {"type": "string", "enum": list(VERDICTS)}, "status": {"type": "string", "enum": ["ok", "warn", "fail"]}, "reason": S_}}},
    "summary": S_}}

CONTRACT = """당신은 문서 편집기의 **검증 결과**를 다시 보는 검토자입니다. 편집기는 hwpx(한글) · docx(Word) 문서를 웹 화면에 읽어 보이고 고친 뒤 저장합니다.
검증은 스크립트가 합니다 — 문서를 한글 · Word 로 PDF 로 찍어 웹이 읽은 글 · 쪽 · 레터 · 글꼴 · 크기 · 굵게 · 색을 견주고, 저장본이 고친 곳만 바뀌었는지 봅니다.
PDF 는 그것을 재는 **기준**일 뿐 정답이 아닙니다 — 한글 · Word 가 PDF 를 찍는 방식 때문에 생기는 다름이 있습니다.

## 할 일
자료의 `targets`(스크립트가 주의 · 실패로 판정한 단계) 하나하나에 대해, 그 다름이
- `real` — **실제 문제**: 웹이 문서를 잘못 읽었거나 저장본이 잘못됨(문서의 서식 · 글을 따라 특정 자리에서 생긴 다름)
- `reference` — **기준 쪽 사정**: PDF 를 찍는 쪽(한글 · Word)의 특성으로 생긴 다름 — 웹 결과는 문서와 맞음
- `mixed` — 둘이 섞임
- `unclear` — 자료로 가릴 수 없음(짐작하지 않는다)
인지 가리고, 그 단계에 둘 상태를 고릅니다.

## 자료(JSON) 읽는 법
- `kind` = import(가져오기 검증 — 올린 원본을 웹이 제대로 읽었나) · edit(출력파일 검증 — 저장본이 고친 곳만 바뀌었나). `format` = hwpx · docx, `app` = PDF 를 찍은 프로그램.
- `steps` = 모든 단계(차례대로): `key` · `title` · `about`(단계가 보는 것) · `status`(스크립트 판정 ok · warn · fail · skip) · `detail`(스크립트의 설명 글) · `data`(단계가 남긴 자료를 줄인 것 —
  목록은 앞 12개와 「… 모두 n개」, 글은 200자까지) · `unjudged`(스크립트가 **판정하지 못한 것** — 건너뛴 까닭 · 모른 글자 수 등. 통과가 아니다).
  통과 · 건너뜀 단계도 맥락으로 실려 있습니다.
- 글꼴 대조(`fonts`)의 `data.fonts.faces`(한글 글자) · `latin`(영문 · 숫자) 줄마다: `web`(문서 글꼴) · `pdf`(PDF 글꼴 이름: 글자 수) · `verdict`(글꼴 판정) ·
  `bold`(굵게 짝 — 「웹→PDF」: 글자 수, 예 「보통→굵게」: 3355 · Type3 는 「→모름」). `missing` = 다른 글자가 있는 문단의 보기(문단마다 하나).

## 답의 꼴
- `steps`: `targets` 의 key 마다 하나 — {key, verdict, status, reason}. key 는 `targets` 에 있는 것만.
- `status` 는 verdict 에 따라 이 가운데서만: reference → ok · warn(기준 쪽 사정 말고도 눈으로 볼 것이 남으면 warn) · mixed → warn · fail · real → warn · fail · unclear → 스크립트 판정 그대로.
  **스크립트 판정보다 무겁게 올리지 않습니다**(스크립트가 warn 이면 fail 을 고르지 않는다).
- `reason`: 한국어 한두 문장 — 근거(어느 글꼴 · 몇 글자 · 어느 쪽 · 어떤 몰림)를 자료의 값으로 적습니다. 화면에 그대로 보입니다. 자료에 없는 사실을 지어내지 않습니다.
- `summary`: 검토 전체를 한 문장으로."""

FALLBACK_GUIDE = """- 다름이 PDF 글꼴 하나 · 한 종류의 글자 · 출력 프로그램의 동작에 몰려 있고 문서 서식과 무관하면 기준 쪽 사정, 특정 문단 · 런의 서식을 따르면 실제 문제다.
- 판정하지 못한 것(unjudged)은 통과로 셈하지 않는다. 가릴 수 없으면 unclear."""


def enabled():
    """env NFM_VERIFY_LLM 이 off·0 이면 False(시험) — 그 밖은 LLM 길이 있으면 부른다."""
    return os.environ.get("NFM_VERIFY_LLM", "").strip().lower() not in ("off", "0")


def _small(v, depth=0):
    """단계 자료를 프롬프트용으로 줄인다 — 목록은 앞 LIST_MAX 개 + 「… 모두 n개」, 글은 TEXT_MAX 자, 깊이 DEPTH_MAX."""
    if isinstance(v, str):
        return v if len(v) <= TEXT_MAX else v[:TEXT_MAX - 1] + "…"
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if depth >= DEPTH_MAX:
        return f"(… {len(v)}개)" if isinstance(v, (dict, list, tuple, set)) else _small(str(v), depth)
    if isinstance(v, dict):
        items = list(v.items())
        out = {str(k): _small(x, depth + 1) for k, x in items[:LIST_MAX * 2]}
        if len(items) > LIST_MAX * 2:
            out["…"] = f"모두 {len(items)}개"
        return out
    if isinstance(v, (list, tuple, set)):
        v = list(v)
        out = [_small(x, depth + 1) for x in v[:LIST_MAX]]
        if len(v) > LIST_MAX:
            out.append(f"… 모두 {len(v)}개")
        return out
    return _small(str(v), depth)


def _unjudged(s):
    """단계에서 스크립트가 판정하지 못한 것 — 단계가 적은 `unjudged` + 건너뛴 까닭."""
    out = list(s.get("unjudged") or ())
    if s.get("status") == "skip":
        out.append(f"이 단계를 건너뜀 — {s.get('detail') or '까닭 모름'}")
    return out


def targets(steps):
    """LLM 이 볼 단계 key — 주의·실패인 스크립트 단계(LLM 검토 단계 자신은 빼고)."""
    return [s["key"] for s in steps if s["key"] != KEY and s.get("status") in ("warn", "fail")]


def payload(steps, kind, fmt="hwpx"):
    """프롬프트의 자료(JSON 으로 보낼 dict)."""
    return {"kind": kind, "format": fmt, "app": pdf_render.app_name(fmt), "targets": targets(steps),
            "steps": [{"key": s["key"], "title": s.get("title"), "about": s.get("about"), "status": s.get("status"), "detail": _small(s.get("detail") or ""),
                       "data": _small({k: v for k, v in s.items() if k not in _PLAIN and k != "unjudged"}), "unjudged": _small(_unjudged(s))}
                      for s in steps if s["key"] != KEY]}


def guide_part(g=None):
    g = merge_guides.get(GUIDE) if g is None else g
    return merge_guides.part(g, note="아래는 이 검토의 **판단 기준**입니다(사용자가 관리하는 지침). 답의 꼴과 둘 수 있는 상태는 위 계약 그대로입니다.") \
        or f"\n\n## 판단 기준 — 기본\n\n{FALLBACK_GUIDE}"


def prompt(data, g=None):
    return CONTRACT + guide_part(g) + "\n\n## 자료(JSON)\n" + json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def apply(steps, answer):
    """LLM 답을 검사해 단계마다 반영할 것 → ({key: {"status", "llm": {verdict, status, reason}}}, rejected[글]).
    대상이 아닌 key · 둘 수 없는 상태 · 스크립트보다 무거운 상태 · 같은 key 두 번은 버리고(rejected), 답이 없는 대상은 반영하지 않는다."""
    want = {s["key"]: s.get("status") for s in steps if s["key"] in set(targets(steps))}
    out, rejected = {}, []
    for a in (answer or {}).get("steps") or ():
        if not isinstance(a, dict):
            continue
        k, verdict, status = a.get("key"), a.get("verdict"), a.get("status")
        reason = " ".join(str(a.get("reason") or "").split())[:REASON_MAX]
        if k not in want:
            rejected.append(f"대상이 아닌 단계 「{k}」")
            continue
        if k in out:
            rejected.append(f"「{k}」 답이 두 번 — 앞의 것만")
            continue
        if verdict not in VERDICTS:
            rejected.append(f"「{k}」 모르는 판정 「{verdict}」")
            continue
        script = want[k]
        if verdict == "unclear":
            status = script
        elif status not in ALLOWED[verdict]:
            rejected.append(f"「{k}」 {VERDICT_KO[verdict]} 인데 상태 「{status}」 — 스크립트 판정 그대로")
            status = script
        elif RANK[status] > RANK[script]:
            rejected.append(f"「{k}」 스크립트 판정({STATUS_KO[script]})보다 무거운 「{STATUS_KO[status]}」 — 스크립트 판정 그대로")
            status = script
        out[k] = {"status": status, "llm": {"verdict": verdict, "status": status, "reason": reason}}
    for k in want:
        if k not in out:
            rejected.append(f"「{k}」 답 없음 — 스크립트 판정 그대로")
    return out, rejected


def review(job, fmt="hwpx"):
    """verify 작업의 「LLM 검토」 단계 — 주의·실패 단계가 없으면 부르지 않고, 있으면 한 번 불러 그 단계들의 상태를 바꾼다(스크립트 판정은 단계의 script 에)."""
    steps = job.view()["steps"]
    keys = targets(steps)
    if not keys:
        job.set(KEY, "skip", "주의·실패 단계 없음 — 부르지 않음")
        return
    if not enabled():
        job.set(KEY, "skip", "검증 LLM 검토가 꺼져 있음(NFM_VERIFY_LLM) — 스크립트 판정 그대로")
        return
    if not llm.status().get("available"):
        job.set(KEY, "skip", "LLM 을 쓸 수 없음 — 스크립트 판정 그대로")
        return
    job.set(KEY, "run", f"주의·실패 {len(keys)}단계를 LLM 이 보는 중")
    g = merge_guides.get(GUIDE)
    r = llm.call(SCHEMA, prompt(payload(steps, job.kind, fmt), g), f"{WHAT}-{job.kind}", timeout=TIMEOUT, effort=EFFORT)
    call = {k: r.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error")}
    if r.get("data") is None:
        job.set(KEY, "skip", f"LLM 호출 실패 — {str(r.get('error') or '까닭 모름')[:200]} · 스크립트 판정 그대로", review={"call": call})
        return
    got, rejected = apply(steps, r["data"])
    by = {s["key"]: s for s in steps}
    for k, x in got.items():
        s = by[k]
        job.set(k, x["status"], s.get("detail") or "", script={"status": s.get("status"), "detail": s.get("detail") or ""}, llm=x["llm"])
    tally = {}
    for x in got.values():
        tally[x["llm"]["verdict"]] = tally.get(x["llm"]["verdict"], 0) + 1
    summary = " ".join(str(r["data"].get("summary") or "").split())[:REASON_MAX]
    secs = f" · {call['ms'] / 1000:.0f}초" if call.get("ms") else ""
    parts = [f"주의·실패 {len(keys)}단계 검토"] + [f"{VERDICT_KO[v]} {tally[v]}" for v in VERDICTS if tally.get(v)]
    job.set(KEY, "ok", " · ".join(parts) + f" — {call.get('model') or ''}{secs}" + (f" · {summary}" if summary else ""),
            review={"call": call, "summary": summary, "rejected": rejected, "guide": merge_guides.brief(g)})
