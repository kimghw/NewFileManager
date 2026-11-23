"""사용자 요구사항의 끝점(spec_워크플로우 ② §18-20) — server.py 가 include 한다. 저장은 `app/user_reqs.py`(가벼운 모듈 · 저장소 파일 `reqs/requirements.json`).

- `GET /api/reqs` → {version, items[{id, date, said, note, state, targets[…], spec, src, at}], counts{대상: {n, open}}, targets{대상: {kind, name, group}}, steps{단계 줄의 주소: 도구 대상}, states{open: 요청 …}, max{said, note, spec, targets}}
  — `targets` = 지금 등록부에 있는 대상 모두(도구 · 단계 · 워크플로우의 이름 — 화면이 「모든 요구사항」 을 대상마다 묶을 때 · 대상을 고를 때 쓴다). 항목의 대상이 여기 없으면 없어진 대상이다(화면이 「없어진 대상」 으로 보인다).
  `steps` = 워크플로우 · 일반 단계 절의 단계 줄(주소 `plan_to_report--review--heads`) → 그 줄의 도구(`tool:relay.heads`) — 그 줄을 눌러도 같은 도구의 요구사항이 보이게.
- `POST /api/reqs` {targets[…], said, note?, state?, date?, spec?} → 201 그 항목(src web) · `PUT /api/reqs/{id}` {said? · note? · state? · date? · spec? · targets?} → 그 항목 · `DELETE /api/reqs/{id}` → {ok}.
  400 = 값의 꼴 · 404 = 없는 항목 · 등록부에 없는 대상 · 503 = 저장 실패 · 파일이 깨짐.
요구사항은 기록이다 — 이 끝점은 문서 · 실행 · LLM 호출을 건드리지 않는다."""
from fastapi import APIRouter, Body, HTTPException

from app import user_reqs as R

router = APIRouter()
FAMILY_NAME = {"relay": "1 → N", "gather": "N → 1", "single": "문서 하나", "collect": "N → 1 · 같은 양식"}   # 틀의 화면 이름(조립 폼의 문서 입출력과 같은 말)


def targets():
    """지금 있는 대상 {"<종류>:<키>": {kind, name, group}} — 등록부(붙박이 + 조립한 워크플로우)와 조립에 놓는 도구에서. 이름은 등록부의 기본 이름(사람이 고친 도구 이름은 화면이 제 값으로 덮는다)."""
    from app import agent_notes, workflow
    out = {}
    names, _ = workflow.catalog()
    listing = workflow.listing()
    for t in listing["tasks"]:
        job = t["job"]
        flow = t.get("name") or (names.get(job) or {}).get("name") or job
        out[f"flow:{job}"] = {"kind": "flow", "name": flow, "group": "워크플로우"}
        for g in t.get("stages") or []:
            label = " ".join(x for x in (g.get("no") or "", g.get("name") or "") if x) or g["id"]
            out[f"stage:{job}.{g['id']}"] = {"kind": "stage", "name": label, "group": flow}
    for c in listing["common"]:
        stage = c.get("kind") == "stage"
        out[f"common:{c['id']}"] = {"kind": "stage" if stage else "tool", "name": c["name"], "group": "단계" if stage else "도구"}
    for fam, rows in agent_notes.tool_map().items():
        for unit, v in rows.items():
            out[f"tool:{fam}.{unit}"] = {"kind": "tool", "name": v["name"], "group": f"워크플로우 도구 · {FAMILY_NAME.get(fam, fam)}"}
    return out


def steps():
    """등록부의 단계 줄의 주소(`<워크플로우 키>--<묶음 id>--<줄 key>` · 일반 단계는 `common-<단계 id>--<줄 key>`) → 그 줄의 도구 대상("tool:<틀>.<줄 key>") —
    그 줄이 조립에 놓는 도구와 같은 줄일 때만(틀이 없는 워크플로우(일반 편집 · 서식 복사)와 등록부의 도구(COMMON)의 줄은 없다 — 화면은 그 묶음 · 그 도구의 요구사항을 보인다)."""
    from app import agent_notes, workflow
    tools, out = agent_notes.tool_map(), {}
    listing = workflow.listing()
    for t in listing["tasks"]:
        fam = agent_notes.family_of(t["job"])[0]
        rows = tools.get(fam) or {}
        for g in t.get("stages") or []:
            for s in g["steps"]:
                if s["key"] in rows:
                    out[f"{t['job']}--{g['id']}--{s['key']}"] = f"tool:{fam}.{s['key']}"
    for c in listing["common"]:
        if c.get("kind") == "stage":   # 일반 단계 = 이관형의 줄
            for s in c["steps"]:
                if s["key"] in tools["relay"]:
                    out[f"common-{c['id']}--{s['key']}"] = f"tool:relay.{s['key']}"
    return out


def _load():
    try:
        return R.load()
    except ValueError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/api/reqs")
def reqs_get():
    data = _load()
    return {**data, "counts": R.counts(data["items"]), "targets": targets(), "steps": steps(), "states": R.STATE_NAME,
            "max": {"said": R.SAID_MAX, "note": R.NOTE_MAX, "spec": R.SPEC_MAX, "targets": R.TARGETS_MAX}}


def _known(body):
    ts = body.get("targets") if isinstance(body, dict) else None
    if isinstance(ts, list):
        have = targets()
        gone = [t for t in ts if isinstance(t, str) and R.target_ok(t) and t not in have]
        if gone:
            raise HTTPException(404, f"그런 도구 · 단계 · 워크플로우가 없습니다: {', '.join(gone)}")


def _save(fn):
    _load()   # 깨진 파일이면 503(덮어쓰지 않는다)
    try:
        return fn()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"요구사항을 저장하지 못했습니다: {e}") from e


@router.post("/api/reqs", status_code=201)
def reqs_post(body: dict = Body(...)):
    _known(body)
    return _save(lambda: R.add(body, "web"))


@router.put("/api/reqs/{rid}")
def reqs_put(rid: str, body: dict = Body(...)):
    _known(body)
    item = _save(lambda: R.edit(rid, body))
    if item is None:
        raise HTTPException(404, "그런 요구사항이 없습니다")
    return item


@router.delete("/api/reqs/{rid}")
def reqs_delete(rid: str):
    if not _save(lambda: R.remove(rid)):
        raise HTTPException(404, "그런 요구사항이 없습니다")
    return {"ok": True}
