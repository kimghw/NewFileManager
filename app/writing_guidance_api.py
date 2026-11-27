"""양식 작성 04의 자리별 작성 지침. 새 결과는 보낸 입력이 여전히 같을 때만 사용한다."""
import hashlib
import json
import threading
import time
from collections import Counter

from fastapi import APIRouter, HTTPException

from app import agent_notes, agent_settings, form_review, heading_runs, job_prompts, llm, llm_duo, works, writing_guidance as W
from app import form_themes as T

router = APIRouter()
FILE = "writing_guidance.json"
_LOCK = threading.Lock()
_RUNS, _MEM = {}, {}


def _path(wid):
    folder = works.folder(wid)
    return folder / FILE if folder is not None and (folder / "work.json").is_file() else None


def _load(wid):
    p = _path(wid)
    return (works._read_json(p) if p.is_file() else None) if p is not None else _MEM.get(wid)


def _key(s, places, rev, refs):
    stages = [((r or {}).get("meta") or {}).get("run") for r in (heading_runs.graph(s), heading_runs.tables(s))]
    raw = [rev, stages, [(p["id"], form_review.place_sig(W.form_place(p)), p.get("head"), p.get("boxed"), p.get("tables")) for p in places],
           [(r["id"], r["sha256"], r["name"]) for r in refs]]
    return hashlib.sha256(json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _ref_sigs(places):
    """(문서 전체 참조 글, {자리 id: 그 자리에 실제로 보내는 참조 글의 지문}) — 규정 · 문서 목적(04 는 참조로 읽는다: ② §5-9). 참조가 하나도 안 실리는 자리는 사전에 없다.
    **위 `_key`(실행 전체의 지문)에는 넣지 않는다** — 넣으면 규정 한 줄을 고쳐도 모든 자리의 판정이 낡고, 규정 · 문서 목적을 안 쓰는 문서의 지문은 그대로여야 한다. 자리마다 따로 적어 두고(기록의 `refSigs`)
    달라진 자리만 낡은 것으로 본다(astra 2026-11-27 P1-3 — 전에는 규정을 고쳐도 종전 판정이 그대로 유효했다 · spec_작업 ② §22 ⓑ: 항목마다)."""
    from app import place_guides as PG
    whole = PG.doc_text([g for g in next((p["docGuides"] for p in places if p.get("docGuides")), ()) if g.get("src") in W.REFERENCE])
    return whole, {p["id"]: k for p in places if (k := W.reference_sig(whole, W.reference_of(p)))}


def _ref_stale(stored, now, places):
    """참조(규정 · 문서 목적)가 판정 때와 달라진 자리 id 들 — 그 자리의 판정만 낡았다(다른 자리의 것은 그대로 쓴다). stored = 저장된 기록 · now = `_ref_sigs` 의 지금 지문.
    `refSigs` 가 없는 옛 기록: 참조가 실리는 자리는 그때 무엇을 읽었는지 모르니 낡은 것으로(참조가 없는 자리 · 문서는 전과 같다)."""
    was = (stored or {}).get("refSigs") or {}
    return {p["id"] for p in places if was.get(p["id"], "") != now.get(p["id"], "")}


TYPE_KIND = "테이블 타입"   # 자리의 지침 목록에 얹는 테이블 타입 줄의 종류(화면 말 — spec_양식작성 ② §5-7)
THEME_MAX = 900


def _theme_head(theme):
    """「연구개발과제 — 중요하게 볼 항목: 참여기관 · 연차 · 연구목표 · 예산 · 단계」(항목이 없으면 이름만)."""
    names = " · ".join(x["name"] for x in theme.get("division") or ())
    return theme["name"] + (f" — 중요하게 볼 항목: {names}" if names else "")


def _theme_text(record, themes):
    """문서의 테마(구분 기준 타입)와 개요 템플릿 → 06 · 초안 요청에 싣는 글 | "" — 「연구개발과제 — 중요하게 볼 항목: 참여기관 · 연차 …」 · 「문서가 쓰는 개요 템플릿: 이름(레터 › 레터)」 · 「항목마다: 참여기관: 다루는 법 / …」.
    짧은 것이 앞이다(초안 요청은 앞 400자만 싣는다 — 항목 이름과 템플릿의 레터가 남게)."""
    saved = record.get("theme") or {}
    theme = next((t for t in themes if t["id"] == saved.get("id")), None)
    lines = [_theme_head(theme) if theme else saved.get("text") or ""]
    names = []
    for x in record.get("templates") or ():
        _, item = T.find("templates", x.get("id"), themes)
        item = item or x
        if item.get("name") and item.get("levels"):
            names.append(f"{item['name']}({' › '.join(item['levels'])})")
    if names:
        lines.append("문서가 쓰는 개요 템플릿: " + " · ".join(names))
    hows = " / ".join(f"{x['name']}: {x['how']}" for x in (theme or {}).get("division") or () if x.get("how") and x.get("src") != "llm" and (theme or {}).get("src") != "llm")   # LLM 이 정의한 항목 · 테마의 「다루는 법」 은 사람이 확인하기 전에는 싣지 않는다(이름만 — ② §5-9)
    if hows:
        lines.append("항목마다: " + hows)
    text = "\n".join(x for x in lines if x)
    return text if len(text) <= THEME_MAX else text[:THEME_MAX - 1] + "…"


def _settle(judged, decisions, wid, clashes=None):
    """LLM 이 새로 정의한 테마 · 템플릿 · 테이블 타입을 테마 사본에 더하고(같은 이름의 **같은 정의**가 있으면 그것을 쓴다) 판정을 id 로 맞춘다 →
    (테마 id | None, [템플릿 id], {자리 id: [{table, type}]}, defined[{kind, id, name}] — 이번에 새로 더한 것). 더하지 못한 새 정의는 버린다(판정 전체를 실패로 두지 않는다).
    이름은 같은데 내용(템플릿 = 레터 · 테이블 타입 = 판별 단서 · 작성 방법)이 다른 새 정의는 있는 항목에 잇지 않고 버린다 — clashes(목록)를 주면 [{kind, name, id(이름이 같은 있는 항목)}] 를 적는다
    (astra 2026-11-27 P2-3: 전에는 이름만 같으면 이었다 — 이름이 같은 다른 정의의 작성 방법이 그 표에 실렸다)."""
    at, defined, theme = time.strftime("%Y-%m-%d"), [], None
    t = judged.get("theme")
    if t and t["id"] == W.NEW:
        try:
            theme, made = T.define(t["new"], "llm", wid, at)
            if made:
                defined.append({"kind": "theme", "id": theme, "name": t["new"]["name"]})
        except (ValueError, OSError):
            theme = None
    elif t:
        theme = t["id"]
    home = theme or W.COMMON   # 새 항목을 더할 테마 — 문서의 테마, 못 정했으면 공통

    def put(kind, new):
        key = T.by_name(kind, new["name"])
        if key:
            if T.same_def(kind, T.find(kind, key)[1], new):
                return key
            if clashes is not None:
                clashes.append({"kind": kind, "name": new["name"], "id": key})
            return None
        try:
            iid, made = T.add(home, kind, new, "llm", wid, at)
        except (ValueError, OSError):
            return None
        if made:
            defined.append({"kind": kind, "id": T.ref(home, iid), "name": new["name"]})
        return T.ref(home, iid)

    templates = []
    for x in judged.get("templates") or ():
        key = x["id"] if x["id"] != W.NEW else put("templates", x["new"])
        if key and key not in templates:
            templates.append(key)
    types = {}
    for pid, v in decisions.items():
        rows = [{"table": x["table"], "type": key} for x in v.get("tables") or ()
                if (key := x["type"] if x["type"] != W.NEW else put("tables", x["new"]))]
        if rows:
            types[pid] = rows
    return theme, templates, types, defined


def attach(s, places, rev):
    """05·06·계획·초안이 쓰는 자리 목록에 유효한 보완 지침만 싣는다. 자리의 표에 밝힌 테이블 타입(이름 · 작성 방법)도 같은 길로 싣고(`tableTypes` = 화면의 꼬리표), 문서의 테마는 `docTheme` 에."""
    from app import form_examples_api
    stored, refs = _load(s.id), form_examples_api.listing(s.id)
    if not stored and not refs:
        return
    key = _key(s, places, rev, refs)
    current = stored if stored and stored.get("sig") == key else {}
    off = _ref_stale(current, _ref_sigs(places)[1], places) if current else set()   # 규정 · 문서 목적이 판정 때와 달라진 자리 — 그 자리의 판정 · 규칙 · 타입만 싣지 않는다(다른 자리는 그대로)
    rules, judgments = current.get("rules", {}), current.get("judgments", {})
    image_texts = current.get("imageTexts") or {}
    types, themes = current.get("tableTypes") or {}, None
    llm_defined = {x.get("id") for x in current.get("defined") or () if isinstance(x, dict) and x.get("kind") == "tables"}   # 이 실행에서 LLM 이 새로 정의한 테이블 타입(테마에서 지워졌어도 확인 전으로 본다)
    if types or current.get("theme") or current.get("templates"):   # 테마의 글은 지금 것으로 읽는다(사람이 YAML 을 고치면 바로 닿는다 — 지워진 항목은 판정 때 적어 둔 글로)
        themes = T.listing()
        doc_theme = _theme_text(current, themes)
    for p in places:
        # 보완을 기다리는 동안에도 이전 예시로 세운 검토·계획은 오래된 판으로 보인다.
        p["writingGuidanceSig"] = key
        fresh = p["id"] not in off
        if fresh and p["id"] in judgments:
            p["writingJudgment"] = judgments[p["id"]]
        if themes is not None and doc_theme:
            p["docTheme"] = doc_theme   # 문서의 테마 · 중요 항목 · 개요 템플릿 — 자리마다의 지침 목록에 넣지 않는다(모든 자리에 같은 줄이 붙지 않게: 06 은 한 번 · 초안 요청은 자리마다 읽는다)
        if not fresh:
            continue
        shots = image_texts.get(p["id"]) or ()
        if shots:   # 그림에서 복원한 문구(② §5-13 5) — 화면용 `imageTexts` + 자리의 예시 **끝**에(양식 지침의 사람 예시가 먼저 · 초안 요청만 읽는다: form_guide_yaml.example_text)
            p["imageTexts"] = [dict(x) for x in shots]
            p["examples"] = [*(p.get("examples") or ()),
                             *({"src": "image", "text": x["text"], "label": f"{x['source']} · {x.get('label') or '그림 ' + str(x['image'])}", "check": x.get("check") or "single"} for x in shots)]
        extra = []
        for rule in rules.get(p["id"], ()):
            basis = W.BASIS.get(rule.get("basis"))
            lead = f"[{basis}] " if basis else ""
            locs = [r["source"] + (f" ({r['label'] or '그림 ' + str(r['image'])})" if r["image"] else "") for r in rule.get("evidence", ())]
            extra.append({"src": "llm", "kind": "LLM 작성 지침", **rule,
                          "text": lead + rule["instruction"] + "\n근거 · " + " · ".join(dict.fromkeys(locs or rule["sources"]))})
        for row in types.get(p["id"], ()):   # 그 자리 표의 테이블 타입 — 이름 · 작성 방법을 04 지침과 같은 길로(06 · 계획 · 초안이 읽는다)
            theme, item = T.find("tables", row.get("type"), themes)
            name, how = (item["name"], item["how"]) if item else (row.get("name") or "", row.get("how") or "")
            if not name:
                continue
            # LLM 이 정의한 타입의 작성 방법(how)은 사람이 확인하기 전에는 글 쓰는 호출에 싣지 않는다(② §5-9 · 검토 P2-8 — 이름 · 꼬리표만). 확인 = 테마 YAML 에서 그 항목의 src 를 user 로 고침
            unconfirmed = (item or {}).get("src") == "llm" or (item is None and row.get("type") in llm_defined)
            if unconfirmed:
                how = ""
            where = "이 표" if row["table"] == p["id"] else f"표 「{row.get('text') or row['table']}」({row['table']})"
            source = f"테마 「{theme['name']}」" if theme else "테마"
            instruction = f"{TYPE_KIND} — {where}: {name}" + (f". {how}" if how else "")
            extra.append({"src": "llm", "kind": TYPE_KIND, "table": row["table"], "type": row.get("type"), "instruction": instruction, "sources": [source],
                          "text": f"{instruction}\n근거 · {source}"})
            p.setdefault("tableTypes", []).append({"table": row["table"], "type": row.get("type"), "name": name, "src": (item or {}).get("src", ""), **({"unconfirmed": True} if unconfirmed else {})})
        if extra:
            from app import place_guides as PG
            # 차례 = 출처 순위(사람 › 규정(필수) › 문서 목적 › 양식 명시 › 양식 지침 › 규정(권고) › 04 — place_guides.RANK). 전에는 04 규칙을 사람 것 바로 뒤에 끼워 사람이 확인한 양식 지침 · 양식의 명시 요건보다 앞에 섰다(검토 P2-4)
            p["guides"] = sorted([*p["guides"], *extra], key=PG.rank)
            p["n"] = len(p["guides"])


def _picture(row, embedded):
    """그림 문구 하나가 가리키는 **목적 문서 안의 그림** 블록 id | None(사람이 올린 서식의 그림 — 문서에 없다). embedded = {출처 id: 목적 문서 안 예시의 블록 id}.
    목적 문서 안 그림의 label 은 「그림 [블록 id]」(form_example_evidence.evidence) — 그 꼴이 아니면 예시의 블록으로."""
    if row.get("ref") not in embedded:
        return None
    label = row.get("label") or ""
    return label[4:-1] if label.startswith("그림 [") and label.endswith("]") and len(label) > 5 else embedded[row["ref"]]


def _judge(batch, inputs, job, images, names, image_labels, types=(), doc=None, run=None):
    """types = 테이블 타입 id 들 · doc = 문서 단위의 답(테마 · 템플릿)을 받아 둘 사전(처음 받은 답 하나 — 묶음마다 다시 묻지만 첫 답을 쓴다).
    **두 모델이 따로 판정하고 협의한다**(LLM1 · LLM2 — `agent_settings.duo`: 2026-11-26 사용자 「문서의 지침을 작성할 떄는 2가지 모델을 같이 사용 … 불가피한 경우 1개만 선택」 · 공통 함수 app/llm_duo.py —
    한쪽만 답하면 그 답 · 사람이 「한 모델만」 으로 두었으면 전과 같은 한 번). run = 실행 상태(자리마다의 진행 `llms` · `consult` 와 묶음마다의 기록 `duo` 를 적는다)."""
    decisions, errors, pending = {}, {}, batch
    tables = {p["id"]: W.table_ids(p) for p in batch}
    for _ in range(2):
        data = {**inputs, "places": pending}
        if errors:
            data["recheck"] = errors
        out = llm_duo.ask(W.SCHEMA, W.prompt(data, job), "writing-guidance", agent_settings.duo("writing_guidance"), timeout=600.0, effort="medium", default_model=W.MODEL,
                          images=images or None, on=run.__setitem__ if run is not None else None,
                          ordered=("levels",))   # 템플릿의 levels 는 위 → 아래 차례가 뜻이다 — 차례가 다르면 다른 판정(협의한다: astra 2026-11-27 P1-6)
        got = out["got"]
        if run is not None and out["rec"]:
            run.setdefault("duo", []).append([{k: r.get(k) for k in ("slot", "model", "ok", "error", "ms")} for r in out["rec"]])
        if got.get("data") is None:
            raise ValueError(f"LLM이 작성 지침을 반환하지 않았습니다 ({got.get('error') or '응답 없음'})")
        if doc is not None:
            doc.setdefault("got", got["data"])
        valid, errors = W.check(got["data"], {p["id"] for p in pending}, names, image_labels, tables, types)
        W.image_text_checks(valid, out["drafts"])   # 그림에서 복원한 문구 — 두 모델이 따로 낸 답을 견줘 check 를 적는다(스크립트 · spec_양식작성 ② §5-13 3)
        decisions.update(valid)
        if not errors:
            return decisions
        pending = [p for p in pending if p["id"] in errors]
    raise ValueError("자동 재판정 후에도 자리별 판정을 확인할 수 없습니다 — " +
                     " / ".join(f"{p['text'] or p['id']}: {errors[p['id']]}" for p in pending[:3]))


def _go(s, run):
    from app import form_example_evidence, form_examples_api, guide_write_api as GW
    try:
        places, rev = GW._base_places(s)
        if not places:
            raise ValueError("채울 자리가 없습니다. 먼저 헤딩 · 표 분석을 마치세요")
        graph, orig = heading_runs.graph(s), GW.uploaded_texts(s)
        with s.lock:
            if s.rev != rev:
                raise ValueError("목적문서가 바뀌었습니다. 작성 지침 보완을 다시 실행하세요")
            blocks = s.doc.blocks()
            embedded = form_example_evidence.evidence(s.doc, blocks, graph)
            examples = form_example_evidence.example_ids(blocks, {n.get("para") for n in (graph or {}).get("nodes") or () if isinstance(n, dict) and n.get("role") == "heading" and n.get("area") == "body"})
        refs = form_examples_api.evidence(s.id)
        sig = _key(s, places, rev, refs)
        form, cut = form_review.form_text(blocks, graph, orig=orig)
        # 같은 이름인 양식 그림·안쪽 예시도 근거에서 각각 식별할 수 있도록 블록 id를 보인다.
        sources, images = W.pack([{**r, "name": f"{r['name']} [{r['id']}]", "role": "embedded"} for r in embedded] + refs)
        repeats = Counter([s.name, *(r["name"] for r in sources)])
        for r in sources:
            if repeats[r["name"]] > 1:
                r["name"] += f" [{r['id']}]"
        briefs = W.briefs(places, blocks, graph, orig, cut, examples)
        cut = cut or any(p.get("cut") for p in briefs)
        job = job_prompts.for_work(s.id)
        names = {"target": s.name, **{r["id"]: r["name"] for r in sources if r["text"] or r["imageNumbers"]}}
        image_labels = {r["id"]: {n["attached"]: n.get("label") or f"그림 {n['local']}" for n in r["imageNumbers"]} for r in sources}
        # 미리 적어 둔 테마(테이블 타입 · 구분 기준 타입 · 개요 템플릿 — spec_양식작성 ② §5-7). LLM 이 정의했고 사람이 확인하지 않은 항목은 작성 방법(how) 없이 이름 · 판별 단서 · 레터만 —
        # 04 가 확인 전의 작성 방법을 자리 규칙으로 바꿔 뒤 단계에 넘기지 않게(astra 2026-11-27 P1-4)
        themes = T.brief(unconfirmed_how=False)
        inputs = {"form": form, "cut": cut, "target": s.name, "references": sources, "themes": themes}
        whole, ref_sigs = _ref_sigs(places)
        if whole:   # 문서 전체에 닿는 규정 · 문서 목적 — 참조 자료(판단 지침 writing_guidance.md 「규정 · 문서 목적」: 요구 사항 · 범위로 읽고 규칙으로 다시 내지 않는다 · ② §5-9)
            inputs["reference"] = whole
        # 규정 · 문서 목적만 달라진 실행 — 달라진 자리만 다시 묻고 나머지 자리의 앞 판정은 이어 쓴다(astra 2026-11-27 P1-3 · spec_작업 ② §22 ⓑ ⓓ). 다른 입력이 바뀌었으면(sig) 전처럼 모두 ·
        # 달라진 자리가 없으면(사람이 그냥 다시 실행) 전처럼 모두 다시 묻는다
        prior = _load(s.id) or {}
        prior = prior if prior.get("sig") == sig and isinstance(prior.get("judgments"), dict) and prior["judgments"] else {}
        redo = _ref_stale(prior, ref_sigs, places) if prior else set()
        keep = {p["id"] for p in places if p["id"] in prior["judgments"]} - redo if redo else set()
        types, doc = {x["id"] for t in themes for x in t["tables"]}, {}
        decisions = {}
        asked = [b for b in briefs if b["id"] not in keep]
        for i in range(0, len(asked), W.BATCH_SIZE):
            batch = asked[i:i + W.BATCH_SIZE]
            decisions.update(_judge(batch, inputs, job, images, names, image_labels, types, doc, run))
        # 규정 · 문서 목적의 글을 그대로 되낸 규칙은 버린다(되먹임 — 그 글은 제 출처로 이미 실린다): 그 자리에 실린 참조와만 견주고, 규칙이 안 남은 apply 자리는 상태 · 이유를 고친 **끝 판정으로 집계**한다(astra 2026-11-27 P1-2)
        decisions = W.settle_echo(decisions, places, names["target"])
        judged = W.doc_judgment(doc.get("got"), themes)
        if keep:   # 이어 쓰는 실행 — 문서 단위의 판정(테마 · 템플릿)은 앞 기록 그대로다(아래에서 되넣는다). 새 테이블 타입이 갈 테마만 앞 기록의 것으로
            was = (prior.get("theme") or {}).get("id")
            judged = {"theme": {"id": was} if was in {t["id"] for t in themes} else None, "templates": []}
        table_text = {t["id"]: t.get("text") or "" for p in briefs for t in p.get("tables") or ()}
        rules = {k: v["rules"] for k, v in decisions.items() if v["rules"]}
        judgments = {k: {"status": v["status"], "reason": v["reason"], **({"llm": v["llm"]} if v.get("llm") else {})} for k, v in decisions.items()}   # llm = 스크립트가 상태를 고친 자리의 LLM 답 그대로
        # 그림에서 복원한 문구(② §5-13) — 적용하는 자리의 것만 · 목적 문서 안의 그림이면 그 블록 id 를 함께(화면이 문서의 그 그림으로 간다)
        embedded_ids = {row["id"]: r["id"] for row, r in zip(sources, embedded)}   # pack 은 준 차례대로 ref1 … 을 매긴다 — 목적 문서 안의 예시가 앞이다
        image_texts = {k: [{**x, **({"block": b} if (b := _picture(x, embedded_ids)) else {})} for x in v["imageTexts"]]
                       for k, v in decisions.items() if v.get("imageTexts") and v["status"] == "apply"}
        rules.update({k: v for k, v in (prior.get("rules") or {}).items() if k in keep})
        judgments.update({k: v for k, v in (prior.get("judgments") or {}).items() if k in keep})
        image_texts.update({k: v for k, v in (prior.get("imageTexts") or {}).items() if k in keep})
        counts = Counter(v["status"] for v in judgments.values())
        current, now = GW._base_places(s)
        if sig != _key(s, current, now, form_examples_api.listing(s.id)):
            raise ValueError("분석하는 동안 목적문서 또는 참고 서식이 바뀌었습니다. 다시 실행하세요")
        detail = [{"id": "target", "name": s.name, "images": 0, "cut": cut}]
        detail.extend({"id": r["id"], "name": r["name"], "images": len(r["imageNumbers"]), "cut": r["cut"],
                       "included": r["id"] in names} for r in sources)
        for row in detail:
            row["citedPlaces"] = sum(any(row["name"] in r["sources"] for r in items) for items in rules.values())
        record = {"sig": sig, "rules": rules, "judgments": judgments, "judgmentCounts": {k: counts[k] for k in W.STATUSES},
                  "count": len(rules), "images": len(images), "sources": list(names.values()),
                  "placeCount": len(places), "cut": any(r["cut"] for r in detail), "sourceDetails": detail,
                  "refSigs": ref_sigs,   # 자리마다 보낸 참조(규정 · 문서 목적)의 지문 — 달라진 자리만 낡는다(_ref_stale)
                  **({"imageTexts": image_texts} if image_texts else {}),   # 자리마다 그림에서 복원한 문구 + 두 모델 견줌(check · alt) — 없으면 키를 두지 않는다
                  **({"carried": len(keep)} if keep else {}),   # 앞 판정을 이어 쓴 자리의 수(이번에 다시 묻지 않았다 — 직접 판정한 것으로 세지 않는다)
                  **({"llms": run["duo"][-12:]} if run.get("duo") else {})}   # 묶음마다 자리(LLM1 · LLM2 · 협의)의 기록 — 어느 모델이 답했고 협의했나
        with s.plock, _LOCK:
            if _RUNS.get(s.id) is not run:
                return
            if not heading_runs._live(s):
                raise ValueError("문서를 다시 연 뒤 작성 지침 보완을 다시 실행하세요")
            # 테마 · 템플릿 · 표마다의 테이블 타입 — 새로 정의된 것은 테마 사본에 「LLM 이 정의함」 으로 더하고(이 실행이 버려지지 않을 때만), 판정은 그때의 이름 · 작성 방법과 함께 기록에
            clashes = []
            theme, templates, types_by, defined = _settle(judged, decisions, s.id, clashes)
            now_themes = T.listing()
            got_theme = next((t for t in now_themes if t["id"] == theme), None)
            record["theme"] = {"id": theme, "name": got_theme["name"], "text": _theme_head(got_theme)} if got_theme else None
            record["templates"] = [{"id": k, "name": x["name"], "levels": x["levels"]} for k in templates for _, x in [T.find("templates", k, now_themes)] if x]
            record["tableTypes"] = {pid: [{**r, "text": table_text.get(r["table"], ""), "name": x["name"], "how": x["how"]} for r in rows for _, x in [T.find("tables", r["type"], now_themes)] if x]
                                    for pid, rows in types_by.items()}
            record["defined"] = defined
            if keep:   # 이어 쓴 실행 — 문서 단위의 판정과 이어 쓴 자리의 테이블 타입 · 앞 실행이 새로 정의한 것의 목록은 앞 기록 그대로(이번 묶음의 답으로 덮지 않는다)
                record["theme"], record["templates"] = prior.get("theme"), prior.get("templates") or []
                record["tableTypes"] = {**{k: v for k, v in (prior.get("tableTypes") or {}).items() if k in keep}, **record["tableTypes"]}
                record["defined"] = [*(prior.get("defined") or ()), *defined]
            if clashes:   # 이름은 같은데 내용이 다른 새 정의 — 있는 항목에 잇지 않고 버렸다(그 표는 타입 없이 남는다)
                record["nameClashes"] = clashes
            path = _path(s.id)
            if path is not None:
                works._write_json(path, record)
            else:
                _MEM[s.id] = record
            works.log(s.id, "writingGuidance", places=len(rules), images=len(images), sources=len(names), cut=record["cut"],
                      theme=theme or "", tableTypes=sum(len(v) for v in record["tableTypes"].values()), defined=len(defined),
                      imageTexts=sum(len(v) for v in image_texts.values()))
            run.update(state="done", ended=time.time())
    except Exception as e:
        with _LOCK:
            run.update(state="failed", error=str(e)[:400], ended=time.time())


def start(s):
    from app import server
    if s.fmt != "hwpx":
        raise HTTPException(400, "작성 지침 보완은 HWPX 양식에서 사용할 수 있습니다")
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM을 사용할 수 없습니다")
    run = {"state": "running", "error": "", "at": time.time()}
    with server._reopen_lock, _LOCK:
        if server.DOCS.get(s.id) is not s:
            raise HTTPException(409, "작업을 다시 열고 실행하세요")
        if (_RUNS.get(s.id) or {}).get("state") == "running":
            raise HTTPException(409, "이 문서의 작성 지침을 보완하고 있습니다")
        _RUNS[s.id] = run
        threading.Thread(target=agent_notes.carry(_go), args=(s, run), name=f"writing-guidance-{s.id}", daemon=True).start()
        return {"run": dict(run)}


@router.post("/api/docs/{doc_id}/writing-guidance")
def run_post(doc_id: str):
    from app import server
    return start(server._sess(doc_id))


@router.get("/api/docs/{doc_id}/writing-guidance")
def view(doc_id: str):
    from app import form_examples_api, guide_write_api, server
    s = server._sess(doc_id)
    with _LOCK:
        run = dict(_RUNS[doc_id]) if doc_id in _RUNS else None
        saved = _load(doc_id)
    current, off = False, 0
    if saved:
        places, rev = guide_write_api._base_places(s)
        current = saved.get("sig") == _key(s, places, rev, form_examples_api.listing(doc_id))
        off = len(_ref_stale(saved, _ref_sigs(places)[1], places)) if current else 0   # 규정 · 문서 목적이 판정 때와 달라진 자리의 수 — 다시 실행하면 그 자리만 묻는다
        current = current and not off
    audited = bool(saved and saved.get("judgments"))
    shots = [x for rows in ((saved or {}).get("imageTexts") or {}).values() for x in rows]   # 그림에서 복원한 문구(② §5-13) — 수 · 자리 수 · 사람이 견줘 볼 것(두 모델이 다르게 복원 · 한 모델만 복원)
    return {"ready": current and audited, "audited": audited, "stale": bool(saved and not current), "run": run, "refStale": off,
            "imageTexts": {"items": len(shots), "places": len((saved or {}).get("imageTexts") or {}), "check": sum(x.get("check") in W.CHECK_OPEN for x in shots)},
            "judgmentCounts": (saved or {}).get("judgmentCounts", {}),
            "count": (saved or {}).get("count", 0), "placeCount": (saved or {}).get("placeCount", 0), "sources": (saved or {}).get("sources", []),
            "sourceDetails": (saved or {}).get("sourceDetails", []), "images": (saved or {}).get("images", 0),
            "cut": bool((saved or {}).get("cut")),
            # 테마 · 템플릿 · 테이블 타입의 판정(② §5-7 — 표마다의 타입은 자리 목록의 `tableTypes` 에도)
            "theme": (saved or {}).get("theme"), "templates": (saved or {}).get("templates", []),
            "tableTypeCount": sum(len(v) for v in ((saved or {}).get("tableTypes") or {}).values()), "defined": (saved or {}).get("defined", [])}
