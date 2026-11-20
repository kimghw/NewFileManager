"""도구 이름의 끝점(spec_워크플로우 ② §18-19 「도구 이름 고치기」) — server.py 가 include 한다.
저장 · 얹기는 `app/tool_names.py`(가벼운 모듈), 그 틀에 그 줄이 있는지 · 기본 이름은 워크플로우 등록부의 그 줄에서(`app/agent_notes.py` `tool_map` — 「도구에 적어 두는 내용」 과 같은 단위: (틀, 줄 key)).

- `GET /api/tool-names` → {version, max(이름의 길이), names{"<틀>.<줄 key>": 고친 이름}} — 고친 것만.
- `PUT /api/tool-names/{틀}/{줄 key}` {name, version?} → {family, unit, name(고친 이름 | "" = 기본 이름), base(기본 이름), shown(화면에 보일 이름), same[그 틀에서 이름이 같아진 다른 도구의 기본 이름…],
  also[같이 고친 다른 틀 — 줄 key 와 기본 이름이 같은 같은 도구…], version}
  · 빈 이름 · 기본 이름과 같은 이름 = 기본 이름으로 되돌림. **그 도구를 쓰는 모든 워크플로우(붙박이 포함)의 화면에 적용된다** — 코드의 이름(등록부)과 만든 글(workflow.md · tasks/)은 그대로.
  `same` 은 알림이다(막지 않는다 — 같은 틀의 다른 도구와 이름이 같으면 카드로 가르기 어렵다고 화면이 알린다).
- `DELETE /api/tool-names/{틀}/{줄 key}` → 같은 꼴(name "") — 기본 이름으로.
  400 = 이름의 꼴(글이 아님 · 너무 김 · 「 」 · 줄바꿈) · 「사람이 하는 일」 · 404 = 그 틀에 없는 줄 · 409 = 그 사이에 바뀜(version) · 503 = 저장 실패."""
from fastapi import APIRouter, Body, HTTPException

from app import tool_names as T

router = APIRouter()


def bases(family):
    """그 틀의 줄 key → 기본 이름(등록부의 그 줄 — agent_notes.tool_map) | None(없는 틀)."""
    from app import agent_notes
    rows = agent_notes.tool_map().get(family)
    return None if rows is None else {k: v["name"] for k, v in rows.items()}


@router.get("/api/tool-names")
def names_get():
    return {**T.load(), "max": T.NAME_MAX}


def _save(family, unit, name, ver):
    rows = bases(family)
    if rows is None or unit not in rows:
        raise HTTPException(404, "그 틀에 그런 도구가 없습니다")
    if ver is not None and (isinstance(ver, bool) or not isinstance(ver, int)):
        raise HTTPException(400, "version 은 정수")
    also = [f for f in T.FAMILIES if f != family and (bases(f) or {}).get(unit) == rows[unit]]   # 같은 도구 — 줄 key 와 기본 이름이 같은 다른 틀(이관형 · 취합형이 같이 쓰는 줄): 같이 고친다
    try:
        got = T.save(family, unit, name, rows[unit], ver, also)
    except T.Stale as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"도구 이름을 저장하지 못했습니다: {e}") from e
    now, shown = T.names(family), got["name"] or rows[unit]
    same = [b for k, b in rows.items() if k != unit and k not in T.FIXED and (now.get(k) or b) == shown]
    return {"family": family, "unit": unit, "name": got["name"], "base": rows[unit], "shown": shown, "same": same, "also": also, "version": got["version"]}


@router.put("/api/tool-names/{family}/{unit}")
def name_put(family: str, unit: str, body: dict = Body(...)):
    return _save(family, unit, body.get("name"), body.get("version"))


@router.delete("/api/tool-names/{family}/{unit}")
def name_delete(family: str, unit: str):
    return _save(family, unit, "", None)
