"""구분 기준 LLM 재검토(spec_구분_기준 ② §11) — 사용자가 문서에서 표시한 「추가한 자리」(hint)를 보고 **hint 층만** 고친다(자동 묶음은 안 건드림).

흐름(server.divisions_llm_review): 잠금 안에서 data() 로 자료(JSON) 를 만들고 → 잠금 밖에서 ask() 한 번(수십 초) → 잠금 안에서 apply_revisions() 로
지금 문서의 문단 id 에 대고 검증해 반영. 보내는 자료 = 구분 값·묶음 요약(라벨 글·id)·추가한 자리(앞뒤 문단 글 포함)·헤딩 개요·라벨이 아닌데 값 낱말이 있는 문단(후보).
답 = revisions[{action add|change|remove, hintId, para, dim, value, reason}] + summary — 입력에 있는 문단 id 만."""
import copy
import json
import re
import time
import uuid

from app import prompt_texts
from app import heading_forms, llm
from app.division_profiles import _structure as structure
from app.division_profiles.rnd import core

S = {"type": "string"}
DIMS = ["stage", "year", "stageYear", "sub", "org", "other"]
DIM_NAME = {**core.DIM_NAME, "other": "기타"}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["revisions", "summary"], "properties": {
    "revisions": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "required": ["action", "hintId", "para", "dim", "value", "reason"],
                                             "properties": {"action": {"type": "string", "enum": ["add", "change", "remove"]}, "hintId": S, "para": S,
                                                            "dim": {"type": "string", "enum": DIMS}, "value": S, "reason": S}}},
    "summary": S}}

CONTRACT = """당신은 국가R&D 연구개발계획서·연차보고서(한글 양식)의 **구분 기준 자리**를 검토하는 도우미입니다.
구분 기준 = 단계(stage)·차년도(year)·단계-차년도(stageYear)·세부과제(sub)·기관(org — 주관, 공동1, 공동2 …, 외·국외·위탁). 자리(묶음) = 같은 꼴의 **라벨 문단**이 값 차례
(1, 2, 3 … / 주관, 공동1, 공동2 …)로 되풀이되는 곳이고, 라벨 문단부터 다음 라벨 앞까지가 한 항목입니다. 반영 엔진은 묶음의 항목 수를 구분 값 수에 맞춰 늘리고 줄입니다.
자료: groups = 스크립트가 글 꼴 규칙으로 자동 찾은 묶음(hinted = 사용자 표시의 꼴로 잡힌 것), hints = 사용자(by "user")나 이전 재검토(by "llm")가 문서에서 표시한 추가한 자리
(라벨 문단 하나씩 — text, 글에서 읽은 구분·값 read, 묶음의 라벨이 됐는지 inGroup, 앞뒤 문단 around), outline = 헤딩 개요, candidates = 라벨이 아닌데 구분 값 낱말이 있는 문단(id·구분·값·글).
할 일 — **hints 층만** 고칩니다(groups 는 못 건드림):
- 사용자가 표시한 자리의 **형제**(같은 꼴로 값만 다른 라벨 문단 — 「가. 1차년도 목표」를 표시했으면 「가. 2차년도 목표」·「가. N차년도 목표」)를 candidates·around·outline 의 id 에서 찾아
  action "add" 로 냅니다(hintId "", para = 그 문단 id, dim·value = 그 문단의 구분·값). 혼자인 자리는 묶음이 되지 않으므로 형제를 채우는 것이 핵심입니다. 이미 inGroup 인 자리의 형제는 더 안 내도 됩니다.
- 표시의 dim·value 가 글(read)과 맞지 않으면 action "change"(hintId = 그 hint 의 hintId, para = 같은 문단)로 고칩니다 — dim 은 글에서 읽은 구분을 따릅니다.
- 이전 재검토가 넣은 것(by "llm")이 틀렸으면 action "remove"(hintId). 사용자가 표시한 것은 지우지 않습니다 — 의심되면 "remove" 에 reason 만 적으세요(서버가 제안 메모로만 남깁니다).
- 입력에 있는 문단 id 만 씁니다. 본문 문장 안에 값 낱말이 있을 뿐인 문단(「1차년도에서 구축된 …」)은 라벨이 아닙니다. 확신이 없으면 내지 않습니다.
- value 는 「1단계」「2차년도」「1단계-2차년도」「세부1」「주관」「공동2」「N차년도」 같은 한글 표기, dim 이 other 면 자유 글. reason 은 한 문장(한국어). summary = 전체 판단 두세 문장."""

CONTEXT, CANDS_MAX, OUTLINE_MAX, LABELS_MAX, CAND_LEN = 6, 300, 400, 6, 120

# 양식 정보(spec_구분_기준 ② §16 · 원본 spec_헤딩_추출 ② §12) — 양식마다 md 하나(forms/<양식 키>.md)에 사용자가 관리하는 사실·요청. 두 검토의 프롬프트에 계약 뒤·자료 앞 한 절로 붙는다.
FORM_NOTE = ("아래는 **이 문서의 양식**에 대해 사용자가 따로 관리하는 사실·요청입니다(헤딩 추출·표와 함께 쓰는 글이라 구분 기준과 무관한 절은 배경 지식으로만 읽으세요). "
             "「구분 기준 자리」 절에 적힌 자리 · 자리가 아닌 곳 · 제목이나 칸에 넣을 것은 위 판정 기준보다 먼저 따릅니다 — 자리라고 적힌 곳이 자료에 있는데 묶음(groups)에 안 보이면 냅니다"
             "(그 절의 「(엔진)」 = 스크립트가 이미 찾아 맞추는 자리라는 표시). "
             "그 절 끝의 「코멘트」 줄은 사용자가 화면에서 남긴 요청입니다 — 어디가 자리인지에 관한 것이면 그 절의 다른 줄과 같은 무게로 따릅니다. "   # 양식별 코멘트(② §18)
             "답의 꼴과 「입력에 있는 id 만」 은 위 계약을 따릅니다.")


# 재검토(§11)는 답이 곧 추가한 자리 층에 반영되므로(apply_revisions) 양식 정보를 「형제 찾기」 의 배경으로만 쓴다 — 양식 정보에 적힌 자리라고 형제가 아닌 문단을 새로 더하지 않는다(빠진 자리는 빠진 자리 검토의 몫).
FORM_NOTE_REVIEW = ("아래는 **이 문서의 양식**에 대해 사용자가 따로 관리하는 사실·요청입니다(헤딩 추출·표와 함께 쓰는 글이라 구분 기준과 무관한 절은 배경 지식으로만 읽으세요). "
                    "할 일은 위 계약 그대로입니다 — 표시한 자리의 형제만 더하고, 「구분 기준 자리」 절에 자리라고 적혀 있다는 것만으로 형제가 아닌 문단을 더하지 않습니다. "
                    "그 절이 「자리가 아닌 곳」 이라고 한 문단은 더하지 않고, 어느 문단이 어떤 구분의 라벨인지 헷갈릴 때 이 글을 참고합니다. "
                    "그 절 끝의 「코멘트」 줄은 사용자가 화면에서 남긴 요청입니다 — 어디가 자리인지에 관한 것이면 그 절의 다른 줄과 같은 무게로 읽되, "   # 양식별 코멘트(② §18)
                    "여기서는 마찬가지로 배경으로만 씁니다(코멘트에 적혀 있다는 것만으로 형제가 아닌 문단을 더하지 않습니다).")


def form_part(form, note=FORM_NOTE):
    """양식 정보(heading_forms.pin 꼴 {key, name, sha1, text} | None) → 프롬프트에 붙일 절 글 | ""(맞는 양식 없음 · 보낼 글 없음 — 프롬프트는 전과 같다).
    note = 머리 문장 — 빠진 자리 검토는 FORM_NOTE, 재검토는 FORM_NOTE_REVIEW."""
    text = heading_forms.prompt_body(form)
    return f"\n\n## 양식 정보 — {form.get('name') or form.get('key')} (이 양식에만 해당)\n{note}\n\n{text}" if text else ""


def _asked(res, content, form, part):
    return {"data": res.get("data"), "prompt": content, "call": {k: res.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error")},
            "form": {k: form.get(k) for k in ("key", "name", "sha1")} if part else None}   # 실제로 보낸 양식 글(없으면 None)


def _short(text, n=80):
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= n else t[:n] + "…"


def index(blocks):
    return structure.index_blocks(blocks)


def _read(text, value_text):
    h = core.hint_info(text)
    return {"dim": h["dim"], "value": value_text(h["dim"], h["value"])} if h else None


def data(blocks, levels, values, hints, groups, value_text):
    """LLM 에 보낼 자료(JSON 으로 낼 dict) — 잠금 안에서 만든다(blocks 를 밖으로 들고 나가지 않게). value_text = 프로파일의 값 → 글."""
    idx = index(blocks)
    cont = {}   # 문단 id → (그릇 id | None, 그릇 블록 목록, 차례)
    for cid, items in core._containers(blocks):
        for i, b in enumerate(items):
            if b.get("type") == "paragraph":
                cont[b["id"]] = (cid, items, i)
    label_ids = {it["label"] for g in groups for it in g["items"] if it.get("label")}
    rows = []
    for h in hints:
        b = idx.get(h.get("para"))
        text = (b or {}).get("text") or ""
        c = cont.get(h.get("para"))
        around = []
        if c:
            cid, items, i = c
            for x in items[max(0, i - CONTEXT): i + CONTEXT + 1]:
                if x.get("type") == "paragraph" and (x.get("text") or "").strip():
                    around.append({"id": x["id"], "text": _short(x["text"]), **({"this": True} if x["id"] == h.get("para") else {})})
                elif x.get("type") == "table":
                    around.append({"id": x["id"], "table": True})
        rows.append({"hintId": h["id"], "para": h.get("para"), "dim": h.get("dim"), "value": h.get("value"), "by": h.get("by"), "note": h.get("note") or "",
                     "reason": h.get("reason") or "", "text": _short(text), "read": _read(text, value_text), "inGroup": h.get("para") in label_ids,
                     "where": "cell" if c and c[0] else "body", "exists": b is not None, "around": around})
    group_rows = [{"key": g["key"], "dim": g["dim"], "kind": "list" if g.get("list") else g["kind"], "hinted": bool(g.get("hinted")), "count": len(g["items"]),
                   "where": "table" if g.get("table") else "body",
                   "labels": [{"id": it.get("label"), "text": _short(it.get("labelText"), 50)} for it in g["items"][:LABELS_MAX]]} for g in groups]
    outline = [{"id": pid, "level": lv, "text": _short((idx[pid].get("text") or ""), 60)} for pid, lv in levels.items() if pid in idx][:OUTLINE_MAX]
    cands = []
    for pid, b in idx.items():
        if b.get("type") != "paragraph" or pid in label_ids:
            continue
        t = (b.get("text") or "").strip()
        if not t or len(t) > CAND_LEN:
            continue
        h = core.hint_info(t)
        if h:
            cands.append({"id": pid, "dim": h["dim"], "value": value_text(h["dim"], h["value"]), "text": _short(t, 60),
                          "where": "cell" if (cont.get(pid) or (None,))[0] else "body"})
            if len(cands) >= CANDS_MAX:
                break
    orgs = values.get("orgs") or {}
    return {"values": {"stages": values.get("stages"), "lead": orgs.get("lead"), "joint": orgs.get("joint"), "subs": values.get("subs") or []},
            "dims": [{"id": d, "name": DIM_NAME.get(d, d)} for d in DIMS], "hints": rows, "groups": group_rows, "outline": outline, "candidates": cands}


def ask(payload, *, call=None, effort="medium", timeout=240.0, form=None):
    """한 번 호출(잠금 밖) → {"data": 응답 | None, "prompt", "call": {backend, model, effort, ms, costUsd, error}, "form": {key, name, sha1} | None}.
    form = 이 문서의 양식 정보(heading_forms.pin) — 있으면 프롬프트에 한 절(② §16 — 머리 문장은 재검토용: 형제 찾기의 배경으로만)."""
    part = form_part(form, FORM_NOTE_REVIEW)
    content = prompt_texts.contract(__name__) + part + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    res = (call or llm.call)(SCHEMA, content, "divisions-llm", timeout=timeout, effort=effort)
    return _asked(res, content, form, part)


USER_NOTE = "사용자 표시 — 제안 메모로만"   # applied 줄의 note — 사람이 표시한 자리라 값을 안 바꾸고 제안만 남긴 줄


def _note(h, text, now):
    """사람이 표시한 자리에 LLM 제안 글(llmNote)을 적는다 — 같은 답 안에서 그 자리에 제안이 둘이면(고치기 + 지우기) 뒤의 것이 앞의 것을 지우지 않게 잇는다.
    앞선 재검토의 글 · 제안 값(llmSuggest)은 이번 것으로 바꾼다(llmAt 이 이번 것이 아님 — 글과 값이 서로 다른 재검토의 것으로 남지 않게)."""
    old = h.get("llmNote") if h.get("llmAt") == now else ""
    if not old:
        h.pop("llmSuggest", None)
    h["llmNote"], h["llmAt"] = f"{old} · {text}" if old and text not in old else old or text, now


def apply_revisions(hints, revisions, idx, hint_read, now=None):
    """응답의 revisions 를 지금 문서(idx)에 대고 검증해 hint 목록에 반영 → (새 hints, applied[], skipped[{…, why}]).
    add = 새 hint(by llm) · change = LLM 이 넣은 자리(by llm)만 dim·value·reason 고침 · remove = llm 것만 지움.
    **사람이 표시한 자리(by 가 llm 이 아님)는 change 도 remove 도 값을 바꾸지 않는다** — 제안으로만 남긴다(spec_작업 ② §22 「구현 계약」 22-2 ⓑ: 사람 지정과 LLM 값을 같은 칸에 쓰지 않는다):
    change → llmSuggest{dim, value, reason — 답에 있던 것만} + llmNote 「기준 … · 값 …: 까닭」, remove → llmNote. 둘 다 applied 줄에 note 「사용자 표시 — 제안 메모로만」
    (그 줄은 hint 층의 기준 · 값을 바꾸지 않은 줄이다 — 부르는 쪽이 「바뀐 것」 을 셀 때 가를 수 있게)."""
    now = now or time.time()
    hints = copy.deepcopy(list(hints or ()))
    applied, skipped = [], []
    by_id = {h["id"]: h for h in hints}
    for r in revisions or ():
        if not isinstance(r, dict):
            continue
        act, hid, para = r.get("action"), str(r.get("hintId") or ""), str(r.get("para") or "")
        dim, value, reason = str(r.get("dim") or ""), str(r.get("value") or "").strip()[:60], str(r.get("reason") or "").strip()[:300]
        if act == "add":
            b = idx.get(para)
            if b is None or b.get("type") != "paragraph":
                skipped.append({**r, "why": "문단 id 가 문서에 없음"})
                continue
            if any(h.get("para") == para for h in hints):
                skipped.append({**r, "why": "이미 표시한 문단"})
                continue
            read = hint_read(b.get("text"))
            if dim in ("", "other") and read:
                dim = read["dim"]
            if not dim:
                skipped.append({**r, "why": "구분 기준 없음"})
                continue
            h = {"id": uuid.uuid4().hex[:8], "para": para, "dim": dim, "value": value or (read["value"] if read else ""), "note": "", "by": "llm", "at": now,
                 "reason": reason}
            hints.append(h)
            by_id[h["id"]] = h
            applied.append({**r, "hintId": h["id"]})
        elif act in ("change", "remove"):
            h = by_id.get(hid) or next((x for x in hints if para and x.get("para") == para), None)
            if h is None:
                skipped.append({**r, "why": "그 hint 가 없음"})
                continue
            mine = h.get("by") == "llm"   # LLM 이 넣은 자리만 LLM 이 고치고 지운다
            new_dim = dim if dim and not (dim == "other" and h.get("dim") not in DIMS) else ""   # 기타(사용자 이름) 구분은 이름을 지킨다
            if act == "change" and mine:
                if new_dim:
                    h["dim"] = new_dim
                if value:
                    h["value"] = value
                h["reason"], h["llmAt"] = reason, now
                applied.append({**r, "hintId": h["id"]})
            elif act == "change":   # 사람이 표시한 자리 — 기준 · 값 · 까닭은 그대로, 제안만 남긴다
                suggest = {k: v for k, v in (("dim", new_dim), ("value", value), ("reason", reason)) if v}
                if not suggest:
                    skipped.append({**r, "why": "제안할 기준 · 값이 없음"})
                    continue
                what = " · ".join(x for x in (f"기준 {DIM_NAME.get(new_dim, new_dim)}" if new_dim else "", f"값 {value}" if value else "") if x)
                _note(h, f"{what}: {reason}" if what and reason else what or reason, now)   # 화면이 「LLM 제안: 」 을 앞에 붙여 보인다(app.js) — 여기서 머리말을 또 붙이지 않는다
                h["llmSuggest"] = suggest   # _note 뒤에 — 앞선 재검토의 제안 값을 거기서 치운다
                applied.append({**r, "hintId": h["id"], "note": USER_NOTE})
            elif mine:
                hints.remove(h)
                by_id.pop(h["id"], None)
                applied.append({**r, "hintId": h["id"]})
            else:
                _note(h, reason or "LLM 이 지우기를 제안함", now)
                applied.append({**r, "hintId": h["id"], "note": USER_NOTE})
        else:
            skipped.append({**r, "why": "모르는 action"})
    return hints, applied, skipped


# ---- 빠진 자리 검토(spec_구분_기준 ② §13) — 어느 묶음에도 안 든 표·문단 가운데 구분 기준 자리로 보이는 곳을 LLM 이 판정한다(문서·묶음·hint 는 그대로) --------

SIGNAL = re.compile(r"기관|주관|공동|위탁|단계|차\s*년도|년차|연차|세부")   # 구분 낱말 — 이 낱말이 있는 묶음 밖 표·문단만 보낸다
CONF = ("high", "medium", "low")
MISSING_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["missing", "summary"], "properties": {
    "missing": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "dim", "pattern", "reason", "confidence"],
                                           "properties": {"id": S, "dim": {"type": "string", "enum": DIMS}, "pattern": S, "reason": S,
                                                          "confidence": {"type": "string", "enum": list(CONF)}}}},
    "summary": S}}

MISSING_CONTRACT = """당신은 국가R&D 연구개발계획서·연차보고서(한글 양식)에서 **구분 기준 자리가 빠진 곳**을 찾는 검토자입니다.
구분 기준 = 단계(stage)·차년도(year)·단계-차년도(stageYear)·세부과제(sub)·기관(org — 주관, 공동1, 공동2 …, 외·국외·위탁). 구분 기준 자리 = 그 값마다 같은 구조(문단 묶음·표 행·표 열)가
되풀이되어야 하는 곳 — 과제의 단계·차년도 수나 참여 기관 수가 바뀌면 행·열·절을 그만큼 늘리거나 줄이고 이름을 바꿔야 하는 곳입니다. 반영 엔진은 스크립트(글 꼴 규칙)로 이런 자리를 찾아
묶음으로 만드는데, 라벨 꼴이 낯설면 놓칩니다.
자료: values = 이 과제의 구분 값, groups = 스크립트가 이미 찾은 묶음 요약(같은 꼴은 n 으로 합침 — 어떤 꼴이 이미 잡히는지 참고용), tables = **어느 묶음에도 안 든 표**와 **묶음이 일부만 잡은 표**(id · 크기 size ·
바로 앞 제목 title · 둘러싼 헤딩 path · 머리 칸 head · 첫 열 칸 side · 구분 낱말이 든 칸 표본 marks · 일부만 잡힌 표는 partial · rest · 같은 헤딩 아래 같은 꼴 표 siblings), paragraphs = **어느 묶음에도 안 든 본문 문단** 중 구분 낱말이 있는 짧은 줄
(id · text · path · 바로 다음 블록 next).
할 일: tables·paragraphs 가운데 **구분 기준 자리로 보이는데 빠진 것**만 missing 에 냅니다.
- 내는 것: 행·열·절이 기관·단계·차년도 값마다 하나씩(또는 한 묶음씩) 있어야 하는 곳. 표라면 기관(또는 단계·차년도)을 적는 열·행이 있고 그 값마다 행 묶음이나 열이 이어지는 표,
  문단이라면 값만 다르고 꼴이 같은 제목 줄이 되풀이되는 곳(기관마다 「가. …」「나. …」, 단계마다 「[1단계 …]」「[n단계 …]」).
- 내지 않는 것: 작성 안내·예시 설명 상자, 구분 값과 상관없이 건·실적을 나열하는 목록(논문·특허·수행 과제처럼 기관·단계 축이 없는 것), 값 하나만 적는 칸(표지의 기관명·연구개발기간),
  본문 문장 안에 낱말이 있을 뿐인 줄, 합계·총괄 한 줄. 낱말이 있다는 것만으로 내지 않습니다 — **값마다 되풀이되는 구조**가 자료에 보여야 합니다.
- 사람·건을 나열하는 목록이라도 **기관(또는 단계·차년도)을 적는 칸이 행을 묶으면** 구분 기준 자리입니다 — 그 칸에 역할이 붙은 기관 값(「이름 (주관)」「이름 (공동)」)이나 값마다 다른 기관 이름이
  위아래로 이어져 기관마다 행 묶음을 이루면 냅니다(기관 수가 바뀌면 그 행 묶음이 늘거나 줄어야 하므로). 기관 칸이 비어 있거나 한 값뿐이면 내지 않습니다.
- 다만 다음은 기관 칸이 행을 묶어 보여도 내지 않습니다: **지난 실적·이력을 적는 목록**(국가연구개발사업 수행실적·기술이전·사업화 실적·지식재산권처럼 이 과제의 계획이 아니라 이미 한 일을 적는 표),
  **편성도·조직도 꼴 표**(기관·책임자·담당 내용을 그림처럼 배치한 표), **작성 예시 표**(기관명 칸이 「AAAAA」·「BBBBB」 같은 예시 글자뿐인 표).
- 제목 줄(문단)과 그 바로 아래 표가 한 벌로 되풀이되면 **제목 줄만** 냅니다(표는 그 항목에 딸린 것이라 따로 내지 않습니다). 제목 줄이 paragraphs 에 없을 때만 표를 냅니다.
- **값이 1부터 다 있지 않아도 자리입니다**: 스크립트의 묶음은 값이 1부터 이어지는 곳(1~4차년도)만 잡습니다. 평가항목마다 그 항목의 차년도 행만 있는 표(어느 항목은 1~4차년도, 어느 항목은 3·4차년도만 ·
  4차년도 하나)도 그 값이 행·열을 가르는 머리면 차년도 자리입니다 — 표에 partial: true 가 있으면 묶음이 이미 일부를 잡은 표이고, rest = 묶음 밖에 남은 구분 값 칸(id · 행 row · 열 col · 글)입니다. 그 표를 냅니다
  (pattern 에 남은 칸이 무엇마다 되풀이되는지 · 「평가항목마다 그 항목의 차년도 행」 처럼).
- **단계 값이 하나뿐인 머리도 자리입니다**: 「추진 일정 › 1단계 › 1차년도 … 4차년도」 처럼 단계 머리가 그 아래 차년도 열을 거느리면, 과제가 1단계뿐이어도 그 「1단계」 는 단계 자리입니다(단계가 늘면 그 열 묶음이 단계마다 서야 한다).
- **조건이 붙은 자리는 values 와 견줍니다**: 머리·라벨에 「(해당 시 작성)」 이 붙거나 칸 안내가 「…로 구분된 경우(만) 작성합니다」 인 자리(요약문의 「1단계 (해당 시 작성) | 목표 [1단계 목표] · 내용 [1단계 개발내용]」)는
  그 조건이 맞는 과제만 쓰는 자리입니다 — values.stages 의 길이가 1(단계 하나)이면 그 과제는 단계로 구분되지 않아 그 단계 자리는 **지울 자리**입니다. 스크립트 묶음에 안 든 그런 곳이 rest · marks 에 보이면 냅니다
  (pattern 에 「조건 자리: 단계로 구분된 과제만 — 이 과제는 단계 하나라 해당 없음(지울 자리)」 처럼 · 단계가 둘 이상이면 「행: 단계마다 목표·내용 한 벌」).
- **같은 헤딩 아래 표들은 함께 봅니다**: siblings = 같은 헤딩 아래 머리 줄 꼴이 같은 다른 표 id(숫자만 다름 — 「1차년도(9개월)」 표 · 「2차년도(12개월)」 표 …). 표마다 구분 값 머리 하나씩이고 그 값이 표마다 다르면
  그 표들이 「값마다 표 하나」 자리입니다 — 표 하나만 보면 안 보입니다. 첫 표 id 하나만 내고 pattern 에 「표: 차년도마다 표 하나(n개 — 표 id …)」 처럼 적습니다. 표의 용도(제목 title)가 서로 다르면 묶지 않습니다.
- 이 검토의 답은 사람이 볼 후보입니다 — 행·열·표 수를 바꾸는 근거가 아닙니다(값이 일부만 있는 항목을 전체 차년도로 늘리라는 뜻이 아닙니다).
- dim = 되풀이의 기준(여럿이면 가장 바깥), pattern = 무엇마다 무엇이 되풀이되는지 한 줄(예 「행: 기관 칸마다 그 기관의 줄들」「열: 차년도마다」), reason = 그렇게 본 근거 한 문장(자료의 어느 글을 보고),
  confidence = high(되풀이가 자료에 분명히 보임) · medium(그럴 법함) · low(낱말은 있으나 구조가 흐림). 확신이 없으면 low 로 내거나 내지 않습니다.
- 입력에 있는 id 만 씁니다. summary = 전체 판단 두세 문장(빠진 것이 없으면 그렇게 적습니다)."""

TABLES_MAX, PARAS_MAX, HEAD_CELLS, SIDE_CELLS, MARK_CELLS, CELL_LEN, PARA_LEN = 80, 120, 16, 12, 8, 16, 60


def _table_brief(t, title, path):
    """묶음 밖 표 하나의 요약 | None(작성요령 상자·칸 2개 이하·구분 낱말 없음)."""
    cells = sorted(t["cells"], key=lambda c: (c["row"], c["col"]))
    filled = [c for c in cells if (c.get("text") or "").strip()]
    if len(cells) <= 2 or not filled or "작성요령" in core._bare(filled[0]["text"])[:12]:   # 첫 글 있는 칸이 「작성요령」·「앞표지 작성 요령」
        return None
    head = [_short(c["text"], CELL_LEN) for c in filled if c["row"] <= 1][:HEAD_CELLS]
    side = [_short(c["text"], CELL_LEN) for c in filled if c["col"] == 0 and c["row"] >= 1][:SIDE_CELLS]
    marks = [_short(c["text"], 24) for c in filled if c["row"] >= 1 and c["col"] >= 1 and SIGNAL.search(c["text"]) and len(core._bare(c["text"])) <= 30][:MARK_CELLS]
    if not SIGNAL.search(" ".join([title or "", *head, *side, *marks])):
        return None
    return {"id": t["id"], "size": f"{t['nRows']}x{t['nCols']}", "title": _short(title, 80), "path": [_short(x, 40) for x in path[-2:]],
            "head": head, "side": side, "marks": marks}


def missing_data(blocks, levels, values, groups, value_text):
    """빠진 자리 검토에 보낼 자료(잠금 안에서) — 구분 값 · 묶음 요약 · 어느 묶음 항목에도 안 든 **본문 바로 아래** 표·문단 중 구분 낱말(SIGNAL)이 있는 것.
    묶음 안(항목의 scope)에 든 표·문단과 칸 안 중첩 표는 보내지 않는다(② §13 1차)."""
    covered, grouped, labels = set(), set(), set()
    for g in groups:
        if g.get("table"):
            grouped.add(g["table"])
        for it in g["items"]:
            covered |= set(it.get("scope") or ())
            covered.update(it.get("roots") or ())
            if it.get("label"):
                labels.add(it["label"])
    tables, paras, prev, chain, sec = [], [], "", {}, None
    for i, b in enumerate(blocks):
        if b.get("type") == "table":
            title, prev = prev, ""
            if b["id"] in covered:
                continue   # 묶음 항목 안의 표(기관 절 아래 표 …) — 그 항목에 딸린 것
            part = b["id"] in grouped or any(x["id"] in covered for x in core._under(b))
            rest = _rest(b, covered, labels) if part else None
            if part and not rest:
                continue   # 묶음이 다 잡은 표
            if (brief := _table_brief(b, title, list(chain.values()))):
                brief["_sec"], brief["_sig"] = sec, _head_sig(b)
                if rest:
                    brief.update(partial=True, rest=rest)
                tables.append(brief)
        elif b.get("type") == "paragraph" and (b.get("text") or "").strip():
            text = prev = b["text"]
            if (lv := levels.get(b["id"])):
                chain = {k: v for k, v in chain.items() if k < lv} | {lv: text}
                sec = b["id"]
            bare = re.sub(r"\s+", "", core.NOTE.sub("", text))
            if b["id"] not in covered and bare and len(bare) <= PARA_LEN and SIGNAL.search(bare):
                nxt = next((x for x in blocks[i + 1:i + 4] if x.get("type") == "table" or (x.get("text") or "").strip()), None)
                read = _read(text, value_text)
                paras.append({"id": b["id"], "text": _short(text, 70), "path": [_short(x, 40) for k, x in chain.items() if k != lv][-2:],
                              "next": "" if nxt is None else f"표 {nxt['nRows']}x{nxt['nCols']}" if nxt.get("type") == "table" else _short(nxt["text"], 30),
                              **({"read": read} if read else {}), "_len": len(bare)})
    if len(paras) > PARAS_MAX:   # 넘치면 짧은 줄부터(라벨에 가까움) — 문서 차례는 유지
        keep = {p["id"] for p in sorted(paras, key=lambda p: p["_len"])[:PARAS_MAX]}
        paras = [p for p in paras if p["id"] in keep]
    for p in paras:
        del p["_len"]
    fam = {}
    for t in tables:   # 같은 헤딩 아래 머리 줄 꼴이 같은 표(숫자만 다름 — 「1차년도(9개월)」 표 · 「2차년도(12개월)」 표): 함께 봐야 「값마다 표 하나」 가 보인다(② §13 — 2026-11-23 사용자)
        if t["_sec"] is not None and t["_sig"]:
            fam.setdefault((t["_sec"], t["_sig"]), []).append(t["id"])
    for t in tables:
        ids = fam.get((t.pop("_sec"), t.pop("_sig")), ())
        if len(ids) >= 2:
            t["siblings"] = [x for x in ids if x != t["id"]]
    keep = tables[:TABLES_MAX]
    if len(tables) > TABLES_MAX:   # 넘쳐 자를 때 형제 표가 반만 남지 않게
        want = {x for t in keep for x in t.get("siblings") or ()} - {t["id"] for t in keep}
        keep += [t for t in tables[TABLES_MAX:] if t["id"] in want]
    seen = {}
    for g in groups:
        k = (g["dim"], "list" if g.get("list") else g["kind"], tuple(_short(it.get("labelText"), 24) for it in g["items"][:2]))
        seen[k] = seen.get(k, 0) + 1
    orgs = values.get("orgs") or {}
    return {"values": {"stages": values.get("stages"), "lead": orgs.get("lead"), "joint": orgs.get("joint"), "subs": values.get("subs") or []},
            "dims": [{"id": d, "name": DIM_NAME.get(d, d)} for d in DIMS],
            "groups": [{"dim": d, "kind": kind, "labels": list(labels), "n": n} for (d, kind, labels), n in seen.items()],
            "tables": keep, "paragraphs": paras}


REST_MAX = 16
_SIG_DROP = re.compile(r"[\s\d.,·:\-–~()\[\]<>]+")


def _rest(t, covered, labels):
    """묶음이 일부만 잡은 표의 남은 구분 값 칸 → [{id, row, col, text}](REST_MAX 까지) — 칸 글이 구분 값 낱말로 읽히고(`core.hint_info`) 짧으며,
    묶음의 라벨도 항목 안도 아닌 칸(그 표의 「3·4차년도」 · 「4차년도」 처럼 값이 1부터 다 있지 않아 묶음이 못 된 행 — ② §13 2026-11-23)."""
    out = []
    for c in sorted(t.get("cells") or (), key=lambda c: (c["row"], c["col"])):
        if c["id"] in covered or c["id"] in labels:
            continue
        text = (c.get("text") or "").strip()
        if not text or len(core._bare(text)) > 30 or not core.hint_info(text):
            continue
        out.append({"id": c["id"], "row": c["row"], "col": c["col"], "text": _short(text, 24)})
        if len(out) >= REST_MAX:
            break
    return out


def _head_sig(t):
    """표의 머리 줄 꼴 — 첫 두 행의 칸 글에서 숫자 · 빈칸 · 문장 부호를 뺀 것(같은 헤딩 아래 형제 표 가름 — 「1차년도(9개월)」 ↔ 「2차년도(12개월)」 은 같다)."""
    return "|".join(s for c in sorted(t.get("cells") or (), key=lambda c: (c["row"], c["col"])) if c["row"] <= 1 and (s := _SIG_DROP.sub("", c.get("text") or "")))[:200]


def ask_missing(payload, *, call=None, effort="medium", timeout=240.0, form=None):
    """한 번 호출(잠금 밖) → {"data": 응답 | None, "prompt", "call": {backend, model, effort, ms, costUsd, error}, "form": {key, name, sha1} | None}.
    form = 이 문서의 양식 정보(heading_forms.pin) — 있으면 프롬프트에 한 절(② §16)."""
    part = form_part(form)
    content = prompt_texts.contract(__name__, "MISSING_CONTRACT") + part + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    res = (call or llm.call)(MISSING_SCHEMA, content, "divisions-missing", timeout=timeout, effort=effort)
    return _asked(res, content, form, part)


def check_missing(data, payload):
    """응답의 missing 을 보낸 자료에 대고 검증 → (후보[{id, kind, dim, dimName, title, text, size, path, pattern, reason, confidence}], skipped[{…, why}]).
    보낸 id 만 받고 같은 id 는 한 번만, 확신 순 → 문서(보낸) 순."""
    known = {t["id"]: ("table", t) for t in payload.get("tables") or ()} | {p["id"]: ("paragraph", p) for p in payload.get("paragraphs") or ()}
    order = {k: i for i, k in enumerate(known)}
    items, skipped, seen = [], [], set()
    for r in (data or {}).get("missing") or ():
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id") or "")
        if rid not in known or rid in seen:
            skipped.append({**r, "why": "같은 자리를 두 번" if rid in seen else "보낸 자료에 없는 id"})
            continue
        seen.add(rid)
        kind, src = known[rid]
        dim = r.get("dim") if r.get("dim") in DIMS else "other"
        items.append({"id": rid, "kind": kind, "dim": dim, "dimName": DIM_NAME.get(dim, dim), "title": src.get("title") or "",
                      "text": src.get("text") or " · ".join((src.get("head") or [])[:5]), "size": src.get("size") or "", "path": src.get("path") or [],
                      "pattern": str(r.get("pattern") or "").strip()[:200], "reason": str(r.get("reason") or "").strip()[:300],
                      "confidence": r.get("confidence") if r.get("confidence") in CONF else "low"})
    items.sort(key=lambda x: (CONF.index(x["confidence"]), order[x["id"]]))
    return items, skipped


# ---- LLM 검토 취합(spec_구분_기준 ② §14) — 재검토와 빠진 자리 검토를 함께 돌린 결과를 한 목록으로 ---------------------------------------------

def merge_review(applied, missing, idx, para_of=None):
    """재검토가 추가한 자리 층에 반영한 것(apply_revisions 의 applied — 응답 차례) + 빠진 자리 후보(check_missing 의 items — 확신 순) → 한 목록
    [{id, kind, sources[review|missing], dim, dimName, text, title, size, path, pattern, reason, confidence, action, value, hintId, note}].
    재검토 줄 먼저(같은 문단의 여러 고침은 한 줄 — 처음 action, 까닭은 이어 붙임), 이어서 빠진 자리 후보. 같은 문단이 둘 다에 있으면 한 줄(sources 둘 —
    재검토의 구분·값에 빠진 자리 검토의 꼴·확신·헤딩을 붙임). para_of = {hintId: 문단 id}(change·remove 는 응답에 문단 id 가 없을 수 있다)."""
    items, by_id = [], {}
    for r in applied or ():
        para = str(r.get("para") or "") or str((para_of or {}).get(r.get("hintId")) or "")
        if not para:
            continue
        reason = str(r.get("reason") or "").strip()
        it = by_id.get(para)
        if it is None:
            dim = r.get("dim") or "other"
            it = by_id[para] = {"id": para, "kind": "paragraph", "sources": ["review"], "dim": dim, "dimName": DIM_NAME.get(dim, dim),
                                "text": _short((idx.get(para) or {}).get("text"), 70), "title": "", "size": "", "path": [], "pattern": "", "reason": reason,
                                "confidence": "", "action": r.get("action"), "value": str(r.get("value") or ""), "hintId": r.get("hintId") or "",
                                "note": r.get("note") or ""}
            items.append(it)
        else:
            if reason and reason not in it["reason"]:
                it["reason"] = f"{it['reason']} · {reason}" if it["reason"] else reason
            it["note"] = it["note"] or r.get("note") or ""
    for x in missing or ():
        it = by_id.get(x["id"]) if x.get("kind") == "paragraph" else None
        if it is None:
            items.append({**x, "sources": ["missing"], "action": None, "value": "", "hintId": "", "note": ""})
            continue
        it["sources"].append("missing")
        it.update(pattern=x.get("pattern") or "", confidence=x.get("confidence") or "", path=x.get("path") or [])
        if x.get("reason") and x["reason"] not in it["reason"]:
            it["reason"] = f"{it['reason']} · {x['reason']}" if it["reason"] else x["reason"]
    return items
