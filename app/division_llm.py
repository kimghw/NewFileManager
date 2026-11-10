"""구분 기준 LLM 재검토(spec_구분_기준 ② §11) — 사용자가 문서에서 표시한 「추가한 자리」(hint)를 보고 **hint 층만** 고친다(자동 묶음은 안 건드림).

흐름(server.divisions_llm_review): 잠금 안에서 data() 로 자료(JSON) 를 만들고 → 잠금 밖에서 ask() 한 번(수십 초) → 잠금 안에서 apply_revisions() 로
지금 문서의 문단 id 에 대고 검증해 반영. 보내는 자료 = 구분 값·묶음 요약(라벨 글·id)·추가한 자리(앞뒤 문단 글 포함)·헤딩 개요·라벨이 아닌데 값 낱말이 있는 문단(후보).
답 = revisions[{action add|change|remove, hintId, para, dim, value, reason}] + summary — 입력에 있는 문단 id 만."""
import copy
import json
import re
import time
import uuid

from app import llm
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

CONTRACT = """당신은 국가R&D 연구개발계획서(한글 양식)의 **구분 기준 자리**를 검토하는 도우미입니다.
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


def ask(payload, *, call=None, effort="medium", timeout=240.0):
    """한 번 호출(잠금 밖) → {"data": 응답 | None, "prompt", "call": {backend, model, effort, ms, costUsd, error}}."""
    content = CONTRACT + "\n\n## 자료(JSON)\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    res = (call or llm.call)(SCHEMA, content, "divisions-llm", timeout=timeout, effort=effort)
    return {"data": res.get("data"), "prompt": content,
            "call": {k: res.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error")}}


def apply_revisions(hints, revisions, idx, hint_read, now=None):
    """응답의 revisions 를 지금 문서(idx)에 대고 검증해 hint 목록에 반영 → (새 hints, applied[], skipped[{…, why}]).
    add = 새 hint(by llm) · change = dim·value·reason 고침(출처 유지) · remove = llm 것만 지움, 사용자 것은 llmNote 로 제안만."""
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
            if act == "change":
                if dim and not (dim == "other" and h.get("dim") not in DIMS):   # 기타(사용자 이름) 구분은 이름을 지킨다
                    h["dim"] = dim
                if value:
                    h["value"] = value
                h["reason"], h["llmAt"] = reason, now
                applied.append({**r, "hintId": h["id"]})
            elif h.get("by") == "llm":
                hints.remove(h)
                by_id.pop(h["id"], None)
                applied.append({**r, "hintId": h["id"]})
            else:
                h["llmNote"], h["llmAt"] = reason or "LLM 이 지우기를 제안함", now
                applied.append({**r, "hintId": h["id"], "note": "사용자 표시 — 제안 메모로만"})
        else:
            skipped.append({**r, "why": "모르는 action"})
    return hints, applied, skipped
