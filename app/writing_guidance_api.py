"""양식 작성 04의 자리별 작성 지침. 새 결과는 보낸 입력이 여전히 같을 때만 사용한다."""
import hashlib
import json
import threading
import time
from collections import Counter

from fastapi import APIRouter, HTTPException

from app import agent_notes, form_review, heading_runs, job_prompts, llm, works, writing_guidance as W

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


def attach(s, places, rev):
    """05·06·계획·초안이 쓰는 자리 목록에 유효한 보완 지침만 싣는다."""
    from app import form_examples_api
    stored, refs = _load(s.id), form_examples_api.listing(s.id)
    if not stored and not refs:
        return
    key = _key(s, places, rev, refs)
    current = stored if stored and stored.get("sig") == key else {}
    rules, judgments = current.get("rules", {}), current.get("judgments", {})
    for p in places:
        # 보완을 기다리는 동안에도 이전 예시로 세운 검토·계획은 오래된 판으로 보인다.
        p["writingGuidanceSig"] = key
        if p["id"] in judgments:
            p["writingJudgment"] = judgments[p["id"]]
        extra = []
        for rule in rules.get(p["id"], ()):
            basis = W.BASIS.get(rule.get("basis"))
            lead = f"[{basis}] " if basis else ""
            locs = [r["source"] + (f" ({r['label'] or '그림 ' + str(r['image'])})" if r["image"] else "") for r in rule.get("evidence", ())]
            extra.append({"src": "llm", "kind": "LLM 작성 지침", **rule,
                          "text": lead + rule["instruction"] + "\n근거 · " + " · ".join(dict.fromkeys(locs or rule["sources"]))})
        if extra:
            p["guides"] = sorted(p["guides"], key=lambda g: g.get("src") != "user")
            after_user = sum(g.get("src") == "user" for g in p["guides"])
            p["guides"][after_user:after_user] = extra
            p["n"] = len(p["guides"])


def _judge(batch, inputs, job, images, names, image_labels):
    decisions, errors, pending = {}, {}, batch
    for _ in range(2):
        data = {**inputs, "places": pending}
        if errors:
            data["recheck"] = errors
        got = llm.call(W.SCHEMA, W.prompt(data, job), "writing-guidance", timeout=600.0,
                       effort="medium", model=W.MODEL, **({"images": images} if images else {}))
        if got.get("data") is None:
            raise ValueError(f"LLM이 작성 지침을 반환하지 않았습니다 ({got.get('error') or '응답 없음'})")
        valid, errors = W.check(got["data"], {p["id"] for p in pending}, names, image_labels)
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
        refs = form_examples_api.evidence(s.id)
        sig = _key(s, places, rev, refs)
        form, cut = form_review.form_text(blocks, graph, orig=orig)
        # 같은 이름인 양식 그림·안쪽 예시도 근거에서 각각 식별할 수 있도록 블록 id를 보인다.
        sources, images = W.pack([{**r, "name": f"{r['name']} [{r['id']}]", "role": "embedded"} for r in embedded] + refs)
        repeats = Counter([s.name, *(r["name"] for r in sources)])
        for r in sources:
            if repeats[r["name"]] > 1:
                r["name"] += f" [{r['id']}]"
        briefs = W.briefs(places, blocks, graph, orig, cut)
        cut = cut or any(p.get("cut") for p in briefs)
        job = job_prompts.for_work(s.id)
        names = {"target": s.name, **{r["id"]: r["name"] for r in sources if r["text"] or r["imageNumbers"]}}
        image_labels = {r["id"]: {n["attached"]: n.get("label") or f"그림 {n['local']}" for n in r["imageNumbers"]} for r in sources}
        inputs = {"form": form, "cut": cut, "target": s.name, "references": sources}
        decisions = {}
        for i in range(0, len(briefs), W.BATCH_SIZE):
            batch = briefs[i:i + W.BATCH_SIZE]
            decisions.update(_judge(batch, inputs, job, images, names, image_labels))
        rules = {k: v["rules"] for k, v in decisions.items() if v["rules"]}
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
                  "placeCount": len(places), "cut": any(r["cut"] for r in detail), "sourceDetails": detail}
        with s.plock, _LOCK:
            if _RUNS.get(s.id) is not run:
                return
            if not heading_runs._live(s):
                raise ValueError("문서를 다시 연 뒤 작성 지침 보완을 다시 실행하세요")
            path = _path(s.id)
            if path is not None:
                works._write_json(path, record)
            else:
                _MEM[s.id] = record
            works.log(s.id, "writingGuidance", places=len(rules), images=len(images), sources=len(names), cut=record["cut"])
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
            "cut": bool((saved or {}).get("cut"))}
