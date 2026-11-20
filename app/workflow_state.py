"""워크플로우의 지금 상태 — 정의(등록부의 묶음 › 단계 줄) + 문서마다의 재료 → 단계의 상태 · 묶음의 남은 단계 · 「한 번에 진행」 을 할 수 있나
(spec_워크플로우 ② §17-4 「파일 · 의존 규칙」 · 줄마다의 식은 ② §18-2 「실행 단위」 — app/workflow_units.py).

**순수** — 가져오는 앱 코드는 정의(app.workflow · app.custom_tasks)와 단위(app.workflow_units)뿐이다. 문서를 읽지 않는다: 재료(문서 쌍 · 문서마다의 사실 · LLM · 건너뛰기)는 부르는 쪽이
문(app/unit_steps.py)에서 받아 넘긴다. 서버가 아직 세지 않는 묶음(`server: false`)은 `steps: null` — 그 묶음은 화면이 센다(첫 화면의 대시보드는 「문서 화면에서 진행합니다」: spec_작업에이전트 ② §10).
- `definition(job)` = 그 워크플로우의 등록부 꼴(붙박이 · 조립한 것) | None · `sig(task)` = 정의의 지문(조립한 것 = custom_tasks.sig · 붙박이 = 묶음 id · 단계 key 의 sha1 10자).
- `need(task)` = 재료를 읽어야 하는 문서 역할(서버가 세는 묶음의 줄이 닿는 역할) — 부르는 쪽이 그 문서만 연다.
- `view(task, pair, facts, llm, skip)` = 화면에 내는 상태 `{job, sig, docs, ready, why, stages[…]}`(② §17-5 의 `GET …/flow`)."""
import hashlib
import json

from app import workflow
from app import workflow_units as U

WORD = {"done": "끝남", "now": "지금", "ready": "할 수 있음", "todo": "남음", "run": "진행 중", "skip": "건너뜀", "soon": "준비 중", "blocked": "막힘", "failed": "실패"}   # 상태의 화면 글(대시보드 DASH_ST 와 같은 말)


def definition(job):
    """키 → 등록부의 워크플로우(붙박이 · 조립한 것) | None(모르는 키 · 워크플로우 없음)."""
    return workflow.task_of(job) if job else None


def family(task):
    """그 워크플로우의 단위 가족 — 원본 문서가 여럿이면 gather(취합형), 아니면 relay(이관형 · 문서 하나)."""
    return "gather" if any(r["many"] for r in task.get("roles") or () if r["role"] == "source") else "relay"


def sig(task):
    """정의의 지문 — 줄 · 차례 · 하는 문서가 바뀔 때만 바뀐다. 조립한 것은 저장소의 지문(custom_tasks.sig — 화면이 견주는 값), 붙박이는 묶음 id · 단계 key · on 의 sha1 앞 10자."""
    if task.get("custom"):
        from app import custom_tasks
        c = custom_tasks.get(task["job"])
        return custom_tasks.sig(c) if c else ""
    return hashlib.sha1(json.dumps([[g["id"], [[s["key"], s["on"]] for s in g["steps"]]] for g in task.get("stages") or ()], separators=(",", ":")).encode("utf-8")).hexdigest()[:10]


def _role(task, role):
    return next((r for r in task.get("roles") or () if r["role"] == role), None)


def lines(task):
    """정의의 줄들(준비 중인 줄은 뺀다) → [{stage, key, name, on, optional, unit(단위 | None)}] — 묶음 차례 · 줄 차례."""
    fam = family(task)
    return [{"stage": g["id"], "key": s["key"], "name": s["name"], "on": s["on"], "optional": s["optional"], "unit": U.unit(s["key"], fam)}
            for g in task.get("stages") or () for s in g["steps"] if not s["soon"]]


def served(task, gid):
    """그 묶음을 서버 실행기가 맡는가 — 준비 중이 아닌 모든 줄에 서버가 돌릴 수 있는 단위가 있을 때."""
    mine = [x for x in lines(task) if x["stage"] == gid]
    return bool(mine) and all(x["unit"] is not None and x["unit"]["server"] for x in mine)


def need(task):
    """재료를 읽어야 하는 문서 역할들(차례 = 원본 → 목적) — 서버가 맡는 묶음의 줄이 닿는 역할만(안 닿는 문서는 열지 않는다)."""
    got = {r for x in lines(task) if served(task, x["stage"]) for r in U.roles_of(x["on"])}
    return [r for r in U.ROLES if r in got]


def _docs(task, pair, facts, on):
    """그 줄이 닿는 문서들 → [{role, title, id, facts}] — 묶음에 그 역할의 문서가 없으면 뺀다(준비가 먼저)."""
    out = []
    for r in U.roles_of(on):
        d, role = (pair or {}).get(r), _role(task, r)
        if d and role:
            out.append({"role": r, "title": role["name"], "id": d["id"], "facts": facts.get(d["id"])})
    return out


def ready(task, pair):
    """문서 칸이 찼나 → (참 · 거짓, 빈 칸의 문서 이름들, 까닭 글). 문서 여럿인 워크플로우는 역할마다 문서가 있어야 하고 hwpx 여야 한다(이관의 시작 조건 — ② §17-7 「시작」 ①)."""
    roles = [r for r in task.get("roles") or ()]
    lack = [r["name"] for r in roles if not (pair or {}).get(r["role"])]
    if lack:
        return False, lack, f"{' · '.join(lack)} 칸이 비었습니다 — 문서를 고르거나 올리세요"
    bad = [r["name"] for r in roles if ((pair or {}).get(r["role"]) or {}).get("format") not in ("hwpx", "hwp")]
    if bad:
        return False, [], f"{' · '.join(bad)}가 hwpx 문서가 아닙니다"
    return True, [], ""


def view(task, pair, facts, *, llm=None, skip=(), running=None):
    """지금 상태 → {job, sig, docs{target, source}, ready, why, stages[{id, no, name, does, server, steps[…] | None, total, done, left, can, why, paid[문서 id], change}]}.
    facts = {문서 id: unit_steps.facts 의 값 | None(못 읽음)}(need 의 역할 문서) · llm = LLM 을 쓸 수 있나(None = 모름) · skip = 건너뛴 문서 id 들 · running = 도는 실행의 요약({stage, key} | None — 그 줄을 「진행 중」 으로).
    단계의 st = done · now(그 묶음의 첫 남은 줄) · todo · run(도는 중) · blocked · failed, skipped = 「건너뜀」 으로 끝남. 끝난 수 = 필수 줄만(준비 · 선택 줄은 빼고 — 대시보드의 셈과 같다)."""
    fam, ok, lack, why = family(task), *ready(task, pair)
    ctx0 = {"ready": ok, "lack": lack, "llm": llm, "skip": set(skip or ())}
    stages, before = [], None
    for g in task.get("stages") or ():
        mine = [s for s in g["steps"] if not s["soon"]]
        srv = served(task, g["id"])
        row = {"id": g["id"], "no": g.get("no") or "", "name": g.get("name") or "", "does": g.get("does") or "", "server": srv, "steps": None, "total": 0, "done": 0, "left": 0, "can": False, "why": "", "paid": [],
               "change": any(s["change"] == "doc" for s in mine)}
        if srv:
            steps, opened = [], True
            for s in mine:
                docs = _docs(task, pair, facts, s["on"]) if s["on"] not in ("flow", "") else [{"role": r["role"], "title": r["name"], "id": ((pair or {}).get(r["role"]) or {}).get("id"), "facts": None}
                                                                                         for r in task.get("roles") or () if (pair or {}).get(r["role"])]
                got = U.state(s["key"], {**ctx0, "docs": docs}, fam) or {"st": "todo", "text": ""}
                done = got["st"] == "done"
                live = running is not None and running.get("stage") == g["id"] and running.get("key") == s["key"]
                st = "run" if got["st"] == "busy" or live else "done" if done else got["st"] if got["st"] in ("blocked", "failed") else "now" if opened and not s["optional"] else "todo"
                if not done and not s["optional"]:
                    opened = False
                steps.append({"key": s["key"], "name": s["name"], "on": s["on"], "optional": s["optional"], "st": st, "done": done, "skipped": bool(got.get("skipped")), "busy": got["st"] == "busy",
                              "text": got.get("text") or "", **({"per": got["per"]} if got.get("per") else {}), **({"paid": got["paid"]} if got.get("paid") else {})})
            work = [x for x in steps if x["key"] != "files" and not x["optional"]]   # 세는 줄 — 준비 · 선택 줄은 뺀다
            row.update(steps=steps, total=len(work), done=sum(1 for x in work if x["done"]), left=sum(1 for x in work if not x["done"]),
                       paid=sorted({d for x in steps for d in x.get("paid") or ()}))
            busy = any(x["busy"] for x in steps)
            row["why"] = ("지금 진행 중인 작업이 끝나면 쓸 수 있습니다" if busy else why if not ok else f"{before['no']} 「{before['name']}」 이 먼저입니다" if before else "" if row["left"] else "남은 단계가 없습니다")
            row["can"] = not row["why"]
            if row["left"] and before is None:
                before = row
        stages.append(row)
    docs = {"target": (pair or {}).get("target"), "source": (pair or {}).get("source")}
    return {"job": task["job"], "sig": sig(task), "docs": docs, "ready": ok, "why": why, "stages": stages}
