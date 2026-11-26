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


def _settle(judged, decisions, wid):
    """LLM 이 새로 정의한 테마 · 템플릿 · 테이블 타입을 테마 사본에 더하고(같은 이름이 있으면 그것을 쓴다) 판정을 id 로 맞춘다 →
    (테마 id | None, [템플릿 id], {자리 id: [{table, type}]}, defined[{kind, id, name}] — 이번에 새로 더한 것). 더하지 못한 새 정의는 버린다(판정 전체를 실패로 두지 않는다)."""
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
    home = theme or "common"   # 새 항목을 더할 테마 — 문서의 테마, 못 정했으면 공통

    def put(kind, new):
        key = T.by_name(kind, new["name"])
        if key:
            return key
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
    rules, judgments = current.get("rules", {}), current.get("judgments", {})
    types, themes = current.get("tableTypes") or {}, None
    llm_defined = {x.get("id") for x in current.get("defined") or () if isinstance(x, dict) and x.get("kind") == "tables"}   # 이 실행에서 LLM 이 새로 정의한 테이블 타입(테마에서 지워졌어도 확인 전으로 본다)
    if types or current.get("theme") or current.get("templates"):   # 테마의 글은 지금 것으로 읽는다(사람이 YAML 을 고치면 바로 닿는다 — 지워진 항목은 판정 때 적어 둔 글로)
        themes = T.listing()
        doc_theme = _theme_text(current, themes)
    for p in places:
        # 보완을 기다리는 동안에도 이전 예시로 세운 검토·계획은 오래된 판으로 보인다.
        p["writingGuidanceSig"] = key
        if p["id"] in judgments:
            p["writingJudgment"] = judgments[p["id"]]
        if themes is not None and doc_theme:
            p["docTheme"] = doc_theme   # 문서의 테마 · 중요 항목 · 개요 템플릿 — 자리마다의 지침 목록에 넣지 않는다(모든 자리에 같은 줄이 붙지 않게: 06 은 한 번 · 초안 요청은 자리마다 읽는다)
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
                          images=images or None, on=run.__setitem__ if run is not None else None)
        got = out["got"]
        if run is not None and out["rec"]:
            run.setdefault("duo", []).append([{k: r.get(k) for k in ("slot", "model", "ok", "error", "ms")} for r in out["rec"]])
        if got.get("data") is None:
            raise ValueError(f"LLM이 작성 지침을 반환하지 않았습니다 ({got.get('error') or '응답 없음'})")
        if doc is not None:
            doc.setdefault("got", got["data"])
        valid, errors = W.check(got["data"], {p["id"] for p in pending}, names, image_labels, tables, types)
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
        themes = T.brief()   # 미리 적어 둔 테마(테이블 타입 · 구분 기준 타입 · 개요 템플릿 — spec_양식작성 ② §5-7)
        inputs = {"form": form, "cut": cut, "target": s.name, "references": sources, "themes": themes}
        from app import place_guides as PG
        whole = PG.doc_text([g for g in next((p["docGuides"] for p in places if p.get("docGuides")), ()) if g.get("src") in W.REFERENCE])
        if whole:   # 문서 전체에 닿는 규정 · 문서 목적 — 참조 자료(판단 지침 writing_guidance.md 「규정 · 문서 목적」: 요구 사항 · 범위로 읽고 규칙으로 다시 내지 않는다 · ② §5-9)
            inputs["reference"] = whole
        echo = W.echo_texts(places)
        types, doc = {x["id"] for t in themes for x in t["tables"]}, {}
        decisions = {}
        for i in range(0, len(briefs), W.BATCH_SIZE):
            batch = briefs[i:i + W.BATCH_SIZE]
            decisions.update(_judge(batch, inputs, job, images, names, image_labels, types, doc, run))
        judged = W.doc_judgment(doc.get("got"), themes)
        table_text = {t["id"]: t.get("text") or "" for p in briefs for t in p.get("tables") or ()}
        rules = {k: kept for k, v in decisions.items() if (kept := W.drop_echo(v["rules"], echo))}   # 규정 · 문서 목적의 글을 그대로 되낸 규칙은 버린다(되먹임 — 그 글은 제 출처로 이미 실린다)
        judgments = {k: {"status": v["status"], "reason": v["reason"]} for k, v in decisions.items()}
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
                  **({"llms": run["duo"][-12:]} if run.get("duo") else {})}   # 묶음마다 자리(LLM1 · LLM2 · 협의)의 기록 — 어느 모델이 답했고 협의했나
        with s.plock, _LOCK:
            if _RUNS.get(s.id) is not run:
                return
            if not heading_runs._live(s):
                raise ValueError("문서를 다시 연 뒤 작성 지침 보완을 다시 실행하세요")
            # 테마 · 템플릿 · 표마다의 테이블 타입 — 새로 정의된 것은 테마 사본에 「LLM 이 정의함」 으로 더하고(이 실행이 버려지지 않을 때만), 판정은 그때의 이름 · 작성 방법과 함께 기록에
            theme, templates, types_by, defined = _settle(judged, decisions, s.id)
            now_themes = T.listing()
            got_theme = next((t for t in now_themes if t["id"] == theme), None)
            record["theme"] = {"id": theme, "name": got_theme["name"], "text": _theme_head(got_theme)} if got_theme else None
            record["templates"] = [{"id": k, "name": x["name"], "levels": x["levels"]} for k in templates for _, x in [T.find("templates", k, now_themes)] if x]
            record["tableTypes"] = {pid: [{**r, "text": table_text.get(r["table"], ""), "name": x["name"], "how": x["how"]} for r in rows for _, x in [T.find("tables", r["type"], now_themes)] if x]
                                    for pid, rows in types_by.items()}
            record["defined"] = defined
            path = _path(s.id)
            if path is not None:
                works._write_json(path, record)
            else:
                _MEM[s.id] = record
            works.log(s.id, "writingGuidance", places=len(rules), images=len(images), sources=len(names), cut=record["cut"],
                      theme=theme or "", tableTypes=sum(len(v) for v in record["tableTypes"].values()), defined=len(defined))
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
    current = False
    if saved:
        places, rev = guide_write_api._base_places(s)
        current = saved.get("sig") == _key(s, places, rev, form_examples_api.listing(doc_id))
    audited = bool(saved and saved.get("judgments"))
    return {"ready": current and audited, "audited": audited, "stale": bool(saved and not current), "run": run,
            "judgmentCounts": (saved or {}).get("judgmentCounts", {}),
            "count": (saved or {}).get("count", 0), "placeCount": (saved or {}).get("placeCount", 0), "sources": (saved or {}).get("sources", []),
            "sourceDetails": (saved or {}).get("sourceDetails", []), "images": (saved or {}).get("images", 0),
            "cut": bool((saved or {}).get("cut")),
            # 테마 · 템플릿 · 테이블 타입의 판정(② §5-7 — 표마다의 타입은 자리 목록의 `tableTypes` 에도)
            "theme": (saved or {}).get("theme"), "templates": (saved or {}).get("templates", []),
            "tableTypeCount": sum(len(v) for v in ((saved or {}).get("tableTypes") or {}).values()), "defined": (saved or {}).get("defined", [])}
