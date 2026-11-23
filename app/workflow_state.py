"""워크플로우의 지금 상태 — 정의(등록부의 묶음 › 단계 줄) + 문서마다의 재료 → 단계의 상태 · 묶음의 남은 단계 · 「한 번에 진행」 을 할 수 있나
(spec_워크플로우 ② §17-4 「파일 · 의존 규칙」 · 줄마다의 식은 ② §18-2 「실행 단위」 — app/workflow_units.py).

**순수** — 가져오는 앱 코드는 정의(app.workflow · app.custom_tasks)와 단위(app.workflow_units)뿐이다. 문서를 읽지 않는다: 재료(문서 쌍 · 문서마다의 사실 · LLM · 건너뛰기)는 부르는 쪽이
문(app/unit_steps.py)에서 받아 넘긴다. 서버가 아직 세지 않는 묶음(`server: false`)은 `steps: null` — 그 묶음은 화면이 센다(첫 화면의 대시보드는 「문서 화면에서 진행합니다」: spec_작업에이전트 ② §10).
- `definition(job)` = 그 워크플로우의 등록부 꼴(붙박이 · 조립한 것) | None · `sig(task)` = 정의의 지문(조립한 것 = custom_tasks.sig · 붙박이 = 묶음 id · 단계 key 의 sha1 10자).
- `need(task)` = 재료를 읽어야 하는 문서 역할(서버가 세는 묶음의 줄이 닿는 역할) — 부르는 쪽이 그 문서만 연다.
- `view(task, pair, facts, llm, skip)` = 화면에 내는 상태 `{job, sig, docs, ready, why, stages[…]}`(② §17-5 의 `GET …/flow`)."""
import contextvars
import hashlib
import json

from app import workflow
from app import workflow_units as U

WORD = {"done": "끝남", "now": "지금", "ready": "할 수 있음", "todo": "남음", "run": "진행 중", "skip": "건너뜀", "soon": "준비 중", "blocked": "막힘", "failed": "실패"}   # 상태의 화면 글(대시보드 DASH_ST 와 같은 말)


def definition(job):
    """키 → 등록부의 워크플로우(붙박이 · 조립한 것) | None(모르는 키 · 워크플로우 없음).
    사람이 화면에서 고친 도구 이름(spec_워크플로우 ② §18-19 「도구 이름 고치기」)을 얹은 꼴이다 — 줄의 `name` 이 실행 상태 · 실행 기록에 보일 이름(줄 key · 차례 · 지문은 그대로 · 고친 것이 없으면 등록부의 것 그대로).
    얹는 것은 등록부가 한다(`workflow.shown_of` — 이 층은 정의와 단위만 가져온다: tests/test_workflow_units.py 의 가져오기 경계)."""
    return workflow.shown_of(job) if job else None


# 실행기가 지금 도는 줄 = (가족, 줄 key) | None — 맥락 변수(스레드 · 실행마다 따로). `workflow_exec._line` 이 처리 함수를 부르는 동안 건다.
# 읽는 곳 = app/agent_notes.py: 그 줄이 부르는 LLM 호출에 **그 도구에 적어 둔 내용**(도구 공통 · 이 워크플로우 전용 — spec_에이전트 ② §6)을 붙인다. 실행 층은 그 모듈을 가져오지 않는다(이 변수만 건다).
LINE = contextvars.ContextVar("nfm_flow_line", default=None)


OPEN = {"relay", "gather"}   # 서버 실행기를 연 틀(가족) — 화면(실행의 거울 · 두 대시보드 · 울타리의 고치던 글 보고)이 그 틀을 따라올 때 더한다: gather(취합 — 걸음 5)는 2026-11-20 갈래 「라」 에서 엶
#                    (거울 = workflow_exec.js gatherRunServer · gatherRunFollow) · single(문서 하나 — 걸음 6)은 아직(검토 의견의 P1 을 본 뒤 — spec ④).
#                    닫힌 틀의 묶음은 `server: false`(화면이 돈다) — 화면이 따라오기 전에 열면 문서 화면이 그 실행을 못 보고(거울 없음) 고치던 글을 보고하지 않아 울타리가 지켜 주지 못한다. 시험은 이 집합을 넓혀 본다
OPEN_CUSTOM = {"single", "collect"}   # **조립한 워크플로우에만** 서버 실행기를 연 틀(가족) · collect(같은 양식 취합 — 2026-11-24: 붙박이가 없다 · 화면의 실행 코드가 없어 서버 실행기만 돈다: spec_취합 ② §10) — 2026-11-20 사용자 「그리고 문서 하나는 왜 안되냐?」 → 답 「조립한 것만 서버로」: 조립 폼에서 만든 문서 하나만 서버가 돈다(같은 날 켬 —
#                       화면이 따라옴: workflow_exec.js singleRunServer · 3초 확인의 고치던 글 보고 · dashboard.js dashSingleLive). OPEN 에 single 을 넣지 않는다 — 붙박이 「사업계획서 양식 표준화」 · 「연차보고서 양식 맞추기」 가 같이 열린다(그 둘은 지금처럼 화면에서 돈다)


def family(task):
    """그 워크플로우의 단위 가족 — 등록부가 적은 것(`units` — 문서 하나인 양식 표준화 · 양식 맞추기 = single · 같은 양식 취합으로 조립한 것 = collect)이 먼저 · 원본 문서가 여럿이면 gather(취합형) · 원본 문서가 있으면 relay(이관형) ·
    그 밖(단위가 없는 문서 하나 워크플로우 — 일반 편집 · 서식 복사)은 ""(가족 없음 — 줄 key 가 다른 틀의 단위와 겹쳐도 그 단위로 읽지 않는다)."""
    if task.get("units"):
        return task["units"]
    roles = {r["role"]: r for r in task.get("roles") or ()}
    if "source" not in roles:
        return ""
    return "gather" if roles["source"].get("many") else "relay"


def roles_on(task, on):
    """그 줄이 닿는 문서 역할 — 문서 하나인 워크플로우(single)는 줄의 on 이 빈 값이고 그 문서가 곧 목적 문서다(등록부는 문서 하나인 워크플로우의 on 을 적지 않는다)."""
    return ("target",) if not on and family(task) == "single" else U.roles_of(on)


def base(task):
    """구성의 기준 문서 역할 — 등록부의 base(이관 = source · 취합 = target) · 안 적힌 것은 원본 문서가 있으면 source, 없으면(문서 하나) target(그 문서 자신)."""
    return task.get("base") or ("source" if any(r["role"] == "source" for r in task.get("roles") or ()) else "target")


def sig(task):
    """정의의 지문 — 줄 · 차례 · 하는 문서가 바뀔 때만 바뀐다. 조립한 것은 저장소의 지문(custom_tasks.sig — 화면이 견주는 값), 붙박이는 묶음 id · 단계 key · on 의 sha1 앞 10자."""
    if task.get("custom"):
        from app import custom_tasks
        c = custom_tasks.get(task["job"])
        return custom_tasks.sig(c) if c else ""
    return hashlib.sha1(json.dumps([[g["id"], [[s["key"], s["on"]] for s in g["steps"]]] for g in task.get("stages") or ()], separators=(",", ":")).encode("utf-8")).hexdigest()[:10]


def _role(task, role):
    return next((r for r in task.get("roles") or () if r["role"] == role), None)


_META = {}   # (화면 목록 파일의 고친 때) → 묶음 meta 의 {no, name} — 파일이 바뀔 때만 다시 읽는다


def stage_label(g):
    """묶음의 (번호, 이름) — 등록부에 적힌 것이 먼저 · 취합의 묶음은 등록부에 없고 화면의 목록(task_catalog.js TASK_STAGE_META — 묶음의 meta)에 있다(등록부는 그 이름을 화면에서 읽는다: app/workflow.py 머리 글).
    서버가 짓는 글(「2단계 「문서 프레임 작성」 이 먼저입니다」 · 실행의 끝 글)이 화면의 말과 같게."""
    if g.get("no") or g.get("name") or not g.get("meta"):
        return g.get("no") or "", g.get("name") or ""
    try:
        at = workflow._CATALOG.stat().st_mtime
        if _META.get("at") != at:
            _META.update(at=at, meta=workflow.catalog()[1])
        m = _META["meta"].get(g["meta"]) or {}
    except OSError:
        m = {}
    return m.get("no") or "", m.get("name") or ""


def lines(task):
    """정의의 줄들(준비 중인 줄은 뺀다) → [{stage, key, name, on, optional, unit(단위 | None), beside}] — 묶음 차례 · 줄 차례.
    beside = 앞 줄과 같은 차례(조립한 정의의 같은 행 — spec_워크플로우 ② §18-6 「행 × 두 칸」: 실행기가 그 두 줄을 함께 돌지 본다 — workflow_exec._together)."""
    fam = family(task)
    return [{"stage": g["id"], "key": s["key"], "name": s["name"], "on": s["on"], "optional": s["optional"], "unit": U.unit(s["key"], fam), "beside": bool(s.get("beside"))}
            for g in task.get("stages") or () for s in g["steps"] if not s["soon"]]


def relay_pair(task):
    """이관형(원본 문서 하나 → 목적 문서 하나)인가 — 지금 서버 실행기가 돌릴 수 있는 틀은 이것뿐이다(취합형은 걸음 5 · 문서 하나는 걸음 6).
    단계 key 는 워크플로우마다 겹친다(취합의 「프로젝트 구성 추출」 config · 양식 맞추기의 plan · apply …) — 틀을 보지 않으면 그 묶음을 이관의 처리 함수로 돌리게 된다."""
    roles = {r["role"]: r for r in task.get("roles") or ()}
    return family(task) == "relay" and set(roles) == {"source", "target"} and not roles["source"].get("many")


def framed(task):
    """그 워크플로우의 문서 칸이 그 가족의 틀인가 — relay = 원본 하나 → 목적 하나(relay_pair) · single = 목적 문서 하나뿐 · gather = (걸음 5)."""
    fam, roles = family(task), {r["role"]: r for r in task.get("roles") or ()}
    if fam in ("gather", "collect"):   # 원본 문서 여럿 → 목적 문서 하나(걸음 5 · 같은 양식 취합)
        return set(roles) == {"source", "target"} and bool(roles["source"].get("many")) and not roles["target"].get("many")
    return relay_pair(task) if fam == "relay" else set(roles) == {"target"} if fam == "single" else False


def served(task, gid):
    """그 묶음을 서버 실행기가 맡는가 — 서버 실행기를 연 틀(OPEN)이고 · 문서 칸이 그 틀이고(framed) · 준비 중이 아닌 모든 줄에 서버가 돌릴 수 있는 단위가 있을 때.
    조립한 워크플로우(`custom`)는 조립한 것에만 연 틀(OPEN_CUSTOM)이어도 맡는다 — 나머지 조건은 같다(같은 가족의 붙박이는 그대로 화면이 돈다)."""
    mine = [x for x in lines(task) if x["stage"] == gid]
    fam = family(task)
    opened = fam in OPEN or (fam in OPEN_CUSTOM and bool(task.get("custom")))
    return opened and framed(task) and bool(mine) and all(x["unit"] is not None and x["unit"]["server"] for x in mine)


def need(task):
    """재료를 읽어야 하는 문서 역할들(차례 = 원본 → 목적) — 서버가 맡는 묶음의 줄이 닿는 역할만(안 닿는 문서는 열지 않는다)."""
    got = {r for x in lines(task) if served(task, x["stage"]) for r in (*roles_on(task, x["on"]), *((x["unit"] or {}).get("reads") or ()))}   # 줄이 닿는 문서 + 상태를 셀 때 함께 읽는 문서(구성 · 구조 반영 — 단위의 reads)
    return [r for r in U.ROLES if r in got]


def _docs(task, pair, facts, on):
    """그 줄이 닿는 문서들 → [{role, title, id, facts}] — 묶음에 그 역할의 문서가 없으면 뺀다(준비가 먼저)."""
    out = []
    for r in roles_on(task, on):
        role = _role(task, r)
        many = bool(role and role.get("many"))   # 여럿인 역할(취합의 원본 문서) = 그 묶음의 문서 목록(등록한 차례) — 문서마다의 재료는 열지 않는다(목적 문서의 취합 상태가 준다)
        for d in ((pair or {}).get("sources") or ()) if many else [(pair or {}).get(r)]:
            if d and role:
                out.append({"role": r, "title": d.get("name") or role["name"] if many else role["name"], "id": d["id"], "facts": facts.get(d["id"])})
    return out


def _feeds(fam, early, mine):
    """앞 묶음(early)이 이 묶음(mine)보다 먼저 끝나야 하나 — 둘 다 [(줄의 상태, 단위)]. 이관형 · 취합형 = 모든 앞 묶음(정의의 차례가 곧 조건: ② §18-4 「범위」) ·
    문서 하나(single) = 앞 묶음의 **남은 필수 줄이 주는 사실**을 이 묶음의 줄이 먼저 요구할 때만 — 양식 표준화의 헤딩 · 표 묶음은 프로젝트 구성이 남아도 돌고(② §18-13 「묶음 규칙」),
    양식 맞추기의 「구조 반영」 은 「프로젝트 구성」 의 확정이 먼저다."""
    if fam != "single":
        return True
    gives = {f for x, u in early if u and not x["done"] and not x["optional"] for f in u["gives"]}
    return bool(gives & {f for x, u in mine if u for f in u["needs"]})


def solo_line(task, line_unit, on, role):
    """그 줄이 **그 문서 하나만 따로** 돌 수 있는 줄인가(spec_워크플로우 ② §18-21 「한 문서만 진행」 — 2026-11-21 사용자 「목적문서 따로 원본 문서 작업 따로 할 수 있는 것들은 … 각각 따로 진행할 수 있도록 … 하나의 문서만 작업」):
    문서마다 하는 단위(place doc)이고 · 실행기가 하거나 사람이 「했음」 으로 지나는 줄(auto · hand — 사람이 고르는 pick 은 실행기가 지나간다)이고 · 원본 문서마다 도는 덩이(each — 취합)가 아니고 · 그 줄이 그 역할의 문서에 닿을 때.
    워크플로우 전체 줄(프로젝트 구성 추출 …) · 원본 → 목적 줄(자리 연결 · 내용 반영 …)은 한 문서의 일이 아니다."""
    u = line_unit
    return bool(u and u["place"] == "doc" and u["kind"] in ("auto", "hand") and not u.get("each") and role in roles_on(task, on))


def lane_of(task, mine):
    """그 줄들을 도는 실행이 **문서 하나만** 쓰나 → 그 문서의 역할(source | target) | ""(두 문서를 다 쓴다)(spec_워크플로우 ② §18-22 「문서마다 따로 도는 실행」 — 2026-11-21 사용자
    「원본문서랑, 목적문서를 따로따로 실행해서 처리할 수 있잖아? 매칭은 1개 실행이 같이 해야하고 .. 본문,표 분석은 따로 할 수 있고」). mine = [{on, unit}](workflow_state.lines 의 줄 · 등록부의 줄에 단위를 얹은 것).
    문서 하나만 = 원본 문서 하나 → 목적 문서 하나인 틀(relay_pair)에서 실행기가 하는 줄(사람이 고르는 줄 pick 은 지나간다)이 모두 **같은 한 문서의 줄**(place doc · 그 문서 하나에 닿음)일 때.
    워크플로우 전체 줄 · 원본 → 목적 줄(매칭) · 두 문서에 하는 줄 · 서로 다른 문서의 줄이 섞인 것은 두 문서를 다 쓴다 — 그런 실행은 묶음에 하나뿐이다."""
    if not relay_pair(task):
        return ""
    got = set()
    for x in mine:
        u = x.get("unit")
        if u is None or u["kind"] == "pick":
            continue
        rs = roles_on(task, x["on"])
        if u["place"] != "doc" or u.get("each") or len(rs) != 1:
            return ""
        got.add(rs[0])
    return next(iter(got)) if len(got) == 1 else ""


CONFIG_NAME = "프로젝트 구성 추출"   # 구성 값을 확정하는 줄(config)의 기본 이름 — 정의에 그 줄이 있으면 그 줄의 이름(사람이 고친 도구 이름)으로 적는다


def _config_wait(task, fam, ctx0, both):
    """구성 값이 있어야 하는 줄(단위의 needs 에 config — 프로젝트 구성 반영)이 기다릴 까닭 | ""(확정됨 · 셀 수 없음)(② §18-22 「구성 값 — 추출될 때까지」 — 2026-11-21 사용자
    「구성같은 경우 불러와서 처리해야하니깐. 그 값이 추출돌때까지 실행이 되면 안되고」). 확정됐나는 「프로젝트 구성 추출」 줄의 상태 식 그대로(workflow_units.state("config") — 그 줄이 정의에 없어도 값으로 센다:
    처리 함수 _division_target 의 검사와 같은 재료 · 같은 식). 못 읽었으면(blocked) 까닭을 지어내지 않는다 — 그 줄의 상태가 스스로 알린다."""
    got = U.state("config", {**ctx0, "docs": both}, fam)
    if not got or got["st"] != "todo":
        return ""
    name = next((s["name"] for g in task.get("stages") or () for s in g["steps"] if s["key"] == "config"), CONFIG_NAME)
    return f"「{name}」 이 먼저입니다 — 프로젝트 구성(단계 · 차년도 · 기관)이 확정된 뒤에 진행합니다"


def _solo(task, fam, ctx0, aux, role):
    """묶음 하나의 「그 문서만」 몫 → ({total, left, paid[문서 id], change, busy, wait} | None(따로 돌 것이 없음 · 묶음 전체와 같음), 그 문서의 눈으로 본 남은 줄 수 leftBy).
    aux = [(등록부의 줄, 단위, 닿는 역할들, 줄의 상태, 줄의 문서들, 기다릴 까닭)] — 묶음의 줄 차례. 두 문서에 하는 줄은 그 문서만의 상태를 따로 센다(같은 식 · 그 문서 하나로).
    leftBy = 다른 문서만의 줄을 뺀 남은 필수 줄(그 문서의 줄은 그 문서의 것으로 · 워크플로우 전체 줄 · 원본 → 목적 줄은 그대로) — 뒤 묶음의 「그 문서만」 이 이 묶음을 기다릴지를 이것으로 센다.
    busy = **그 문서의** 줄에 도는 배경 일이 있나(다른 문서의 일은 세지 않는다 — 문서마다 따로 돈다: ② §18-22) · wait = 그 문서의 첫 남은 필수 줄이 기다릴 까닭(구성 값 — _config_wait)."""
    own, left_by, other = [], 0, False
    for s, u, rs, got, docs, wait in aux:
        mine = solo_line(task, u, s["on"] or ("target" if fam == "single" else ""), role)
        if mine and len(rs) > 1:   # 두 문서에 하는 줄 — 그 문서만의 상태
            got = U.state(s["key"], {**ctx0, "docs": [d for d in docs if d["role"] == role]}, fam) or {"st": "todo", "text": ""}
        if mine:
            own.append((s, u, got, wait))
        if u and u["kind"] != "pick" and not (mine and rs == (role,)):
            other = True   # 「그 문서만」 이 하지 않는 줄이 이 묶음에 있다(다른 문서의 줄 · 두 문서의 줄 · 전체 줄 · 원본 → 목적 줄)
        if s["key"] != "files" and not s["optional"] and got["st"] != "done" and (mine or not (u and u["place"] == "doc" and u["kind"] in ("auto", "hand") and not u.get("each"))):
            left_by += 1
    if not own or not other:
        return None, left_by
    work = [(s, got, wait) for s, _u, got, wait in own if not s["optional"]]
    first = next(((s, got, wait) for s, got, wait in work if got["st"] != "done"), None)   # 그 문서의 첫 남은 필수 줄 — 그 줄이 기다리면 「그 문서만」 은 시작하지 않는다
    return {"total": len(work), "left": sum(1 for _s, got, _w in work if got["st"] != "done"), "paid": sorted({d for _s, _u, got, _w in own for d in got.get("paid") or ()}),
            "change": any(u and U.changes(u, role) for _s, u, _g, _w in own), "busy": any(got["st"] == "busy" for _s, _u, got, _w in own), "wait": first[2] if first else ""}, left_by


def ready(task, pair):
    """문서 칸이 찼나 → (참 · 거짓, 빈 칸의 문서 이름들, 까닭 글). 문서 여럿인 워크플로우는 역할마다 문서가 있어야 하고 hwpx 여야 한다(이관의 시작 조건 — ② §17-7 「시작」 ①)."""
    roles = [r for r in task.get("roles") or () if not r.get("many")]   # 여럿인 역할(취합의 원본 문서)은 시작 조건이 아니다 — 목적 문서 하나로 먼저 시작하고 원본은 들어오는 대로(② §18-12 ②)
    lack = [r["name"] for r in roles if not (pair or {}).get(r["role"])]
    if lack:
        return False, lack, f"{' · '.join(lack)} 칸이 비었습니다 — 문서를 고르거나 올리세요"
    bad = [r["name"] for r in roles if ((pair or {}).get(r["role"]) or {}).get("format") not in ("hwpx", "hwp")]
    if bad:
        return False, [], f"{' · '.join(bad)}가 hwpx 문서가 아닙니다"
    return True, [], ""


def context(task, pair, facts, *, llm=None, skip=()):
    """줄의 상태 함수(workflow_units.state)가 읽는 재료 — {ready, lack, llm, skip, pair{역할: {role, title(문서 이름), id, facts}}}(docs 는 줄마다 view 가 더한다).
    실행기의 처리 함수도 이것으로 그 줄의 지금 상태를 센다(화면에 보이는 셈과 같은 재료 · 같은 식)."""
    ok, lack, _ = ready(task, pair)
    both = {r["role"]: {"role": r["role"], "title": r["name"], "id": d["id"], "facts": facts.get(d["id"])}   # 그 묶음의 문서마다 — 두 문서를 함께 보는 줄(구성 · 구조 반영)이 읽는다
            for r in task.get("roles") or () for d in [((pair or {}).get(r["role"]) or None)] if d}
    return {"ready": ok, "lack": lack, "llm": llm, "skip": set(skip or ()), "pair": both, "base": base(task)}   # base = 구성의 기준 문서 역할(구성 확정 · 구조 반영의 식이 읽는다)


def view(task, pair, facts, *, llm=None, skip=(), running=None):
    """지금 상태 → {job, sig, docs{target, source}, ready, why, stages[{id, no, name, does, server, steps[…] | None, total, done, left, can, why, paid[문서 id], change}]}.
    facts = {문서 id: unit_steps.facts 의 값 | None(못 읽음)}(need 의 역할 문서) · llm = LLM 을 쓸 수 있나(None = 모름) · skip = 건너뛴 문서 id 들 ·
    running = 도는 실행의 「지금 줄」({stage, key} | None — 그 줄을 「진행 중」 으로) · 문서마다 따로 도는 실행이 둘이면 그 목록(② §18-22).
    묶음마다 lane(그 묶음을 도는 실행이 쓰는 문서 — source | target | "" 두 문서: lane_of) · wait(첫 남은 줄이 구성 값을 기다리는 까닭 | "") · 줄마다 wait?(그 줄이 기다릴 까닭 — _config_wait).
    단계의 st = done · now(그 묶음의 첫 남은 줄) · todo · run(도는 중) · blocked · failed, skipped = 「건너뜀」 으로 끝남. 끝난 수 = 필수 줄만(준비 · 선택 줄은 빼고 — 대시보드의 셈과 같다)."""
    fam, (ok, _lack, why) = family(task), ready(task, pair)
    ctx0 = context(task, pair, facts, llm=llm, skip=skip)
    nows = [r for r in (running if isinstance(running, (list, tuple)) else [running]) if r]   # 도는 실행들의 「지금 줄」 — 문서마다 따로 도는 실행은 둘일 수 있다(② §18-22)
    pairs = relay_pair(task)
    both = [{"role": r["role"], "title": r["name"], "id": ((pair or {}).get(r["role"]) or {}).get("id"), "facts": None} for r in task.get("roles") or () if (pair or {}).get(r["role"])]
    cfg = None   # 구성 값을 기다릴 까닭(_config_wait) — 그 값을 요구하는 줄이 있을 때 한 번만 센다
    stages, units = [], {}   # units = 묶음 id → [(줄의 상태, 단위)] — 묶음 사이의 「먼저」 를 센다(_feeds)
    for g in task.get("stages") or ():
        mine = [s for s in g["steps"] if not s["soon"]]
        srv = served(task, g["id"])
        no, name = stage_label(g)
        row = {"id": g["id"], "no": no, "name": name, "does": g.get("does") or "", "server": srv, "steps": None, "total": 0, "done": 0, "left": 0, "can": False, "why": "", "paid": [],
               "change": any(s["change"] == "doc" and (s["key"] not in U.TIDY_ROLES or set(U.roles_of(s["on"])) & set(U.TIDY_ROLES[s["key"]])) for s in mine), "after": []}   # 1단계 「LLM 검증·보완」 을 목적 문서에만 놓은 묶음은 문서가 안 바뀐다
        if srv:
            steps, opened, aux = [], True, []
            for s in mine:
                on = s["on"] or ("target" if fam == "single" else "")   # 문서 하나 — 빈 on = 그 문서(roles_on)
                docs = _docs(task, pair, facts, on) if on not in ("flow", "") else both
                got = U.state(s["key"], {**ctx0, "docs": docs, "roles": tuple(roles_on(task, on))}, fam) or {"st": "todo", "text": ""}   # roles = 그 줄이 닿는 문서 역할(여럿인 원본 문서가 아직 없어도 줄의 몫을 안다 — 같은 양식 취합의 헤딩 · 표 분석)
                u = U.unit(s["key"], fam)
                done = got["st"] == "done"
                wait = ""
                if pairs and not done and u and u["place"] == "doc" and u["kind"] == "auto" and "config" in u["needs"]:   # 구성 값이 있어야 하는 줄(프로젝트 구성 반영) — 그 값이 확정될 때까지 기다린다(② §18-22)
                    cfg = _config_wait(task, fam, ctx0, both) if cfg is None else cfg
                    wait = cfg
                aux.append((s, u, tuple(roles_on(task, on)), got, docs, wait))   # 「한 문서만 진행」 의 셈(_solo)이 읽는다
                live = any(r.get("stage") == g["id"] and r.get("key") == s["key"] for r in nows)
                st = "run" if got["st"] == "busy" or live else "done" if done else got["st"] if got["st"] in ("blocked", "failed") else "now" if opened and not s["optional"] else "todo"
                if not done and not s["optional"]:
                    opened = False
                steps.append({"key": s["key"], "name": s["name"], "on": s["on"], "optional": s["optional"], "st": st, "done": done, "skipped": bool(got.get("skipped")), "busy": got["st"] == "busy",
                              "text": got.get("text") or "", **({"per": got["per"]} if got.get("per") else {}), **({"paid": got["paid"]} if got.get("paid") else {}),
                              "kind": (u or {}).get("kind") or "",   # 그 줄을 누가 하나(auto 실행기가 한다 · pick 사람이 고르는 줄 — 실행기는 지나감 · hand 사람이 하고 「했음」) — 화면이 「이 단계만 진행」 을 둘 줄을 이것으로 가른다
                              **({"wait": wait} if wait else {}),   # 이 줄이 기다릴 까닭(구성 값이 아직 확정되지 않음) — 화면은 그 줄의 실행 단추를 끄고 이 글을 보인다 · 시작 요청은 거절(needs)
                              **({"beside": True} if s.get("beside") else {})})   # 앞 줄과 같은 차례(조립한 정의의 같은 행 — 화면이 한 차례로 묶어 보인다)
            work = [x for x in steps if x["key"] != "files" and not x["optional"]]   # 세는 줄 — 준비 · 선택 줄은 뺀다
            row.update(steps=steps, total=len(work), done=sum(1 for x in work if x["done"]), left=sum(1 for x in work if not x["done"]),
                       paid=sorted({d for x in steps for d in x.get("paid") or ()}))
            busy = any(x["busy"] for x in steps)
            units[g["id"]] = [(x, U.unit(x["key"], fam)) for x in steps]
            row["after"] = [e["id"] for e in stages if e["server"] and _feeds(fam, units[e["id"]], units[g["id"]])]   # 먼저 끝나야 하는 앞 묶음(실행기의 경계 검사도 이것으로)
            # lane = 이 묶음을 도는 실행이 쓰는 문서(② §18-22 — 문서 하나의 줄뿐인 묶음은 그 문서만 쓴다: 다른 문서의 실행과 같이 돈다) · 그런 묶음은 앞 묶음의 남은 일도 그 문서의 눈으로 센다(leftBy — 다른 문서만의 줄은 기다리지 않는다)
            lane = row["lane"] = lane_of(task, [{"on": s["on"], "unit": u} for s, u, *_ in aux])
            left_of = (lambda e: (e.get("leftBy") or {}).get(lane, e["left"])) if lane else (lambda e: e["left"])
            before = next((e for e in stages if e["id"] in row["after"] and left_of(e)), None)
            head = next((x for x in work if not x["done"] and x["kind"] != "pick"), None)   # 이 묶음의 첫 남은 필수 줄(실행기가 하는 것) — 그 줄이 기다리면 묶음도 시작하지 않는다
            row["wait"] = (head or {}).get("wait") or ""
            row["why"] = ("지금 진행 중인 작업이 끝나면 쓸 수 있습니다" if busy else why if not ok else f"{before['no']} 「{before['name']}」 이 먼저입니다".strip() if before
                          else "남은 단계가 없습니다" if not row["left"] else row["wait"])
            row["can"] = not row["why"]
            if pairs:   # 「한 문서만 진행」(② §18-21) — 원본 문서 하나 → 목적 문서 하나인 틀에서: 묶음마다 그 문서만 따로 돌 수 있는 몫(solo) · 그 문서의 눈으로 본 남은 줄(leftBy — 실행기의 경계 검사도 이것으로)
                row["leftBy"], row["solo"] = {}, []
                for r in U.ROLES:
                    one, row["leftBy"][r] = _solo(task, fam, ctx0, aux, r)
                    if one is None:
                        continue
                    role, bf = _role(task, r) or {}, next((e for e in stages if e["id"] in row["after"] and (e.get("leftBy") or {}).get(r, e["left"])), None)   # 앞 묶음 — 그 문서의 일 · 전체 줄 · 원본 → 목적 줄이 남았을 때만 기다린다(다른 문서만의 줄은 안 기다림)
                    cant = ("지금 진행 중인 작업이 끝나면 쓸 수 있습니다" if one["busy"] else why if not ok else f"{bf['no']} 「{bf['name']}」 이 먼저입니다".strip() if bf   # 도는 배경 일은 **그 문서의 것만** 센다(다른 문서의 일은 따로 돈다 — ② §18-22)
                            else "남은 단계가 없습니다" if not one["left"] else one["wait"])
                    row["solo"].append({"role": r, "title": role.get("title") or "", "name": role.get("name") or "", "total": one["total"], "left": one["left"], "paid": one["paid"], "change": one["change"],
                                        "can": not cant, "why": cant, **({"wait": one["wait"]} if one["wait"] else {})})
        stages.append(row)
    docs = {"target": (pair or {}).get("target"), "source": (pair or {}).get("source"), **({"sources": list((pair or {}).get("sources") or ())} if fam in ("gather", "collect") else {})}   # sources = 취합 · 같은 양식 취합의 원본 문서들(등록한 차례)
    return {"job": task["job"], "sig": sig(task), "docs": docs, "ready": ok, "why": why, "stages": stages}
