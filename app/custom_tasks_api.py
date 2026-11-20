"""조립한 TASK 끝점(spec_워크플로우 ② §14) — 화면 `/workflow` 의 「TASK 조립」 이 쓴다. 저장 · 검사는 `app/custom_tasks.py`(가벼운 모듈), 단계의 뜻은 등록부 `app/workflow.py` `STAGE_MODULES`.

- `GET /api/tasks` → {tasks[조립한 워크플로우…], stages[고를 수 있는 단계 — id · 이름 · 하는 일 · 묶음 · 단계 줄 · cells(문서 역할마다의 칸)], pairs[조립할 수 있는 문서 쌍], blocked[아직 조립할 수 없는 틀과 까닭],
  shapes[문서 입출력의 틀 — id · io(「1」 · 「1 → 1」 · 「N → 1」) · name · slots[{role, title, many, kinds[{id, name}]}] · soon(아직 못 여는 까닭 | "") — custom_tasks.shapes()(SHAPES 그대로 · soon 은 지금 열려 있는지를 따른다 —
  문서 하나 = 스위치 custom_tasks.SINGLE_OPEN): spec_워크플로우 ② §18-8 「문서 입출력」],
  byShape{gather{units, homes, flow, pairs}, single{units, homes[{id, name}], flow(사업계획서의 처음 줄 목록), flows{plan, report}, pairs[{value(「>plan」 · 「>report」), source(""), target, name}], names{종류: {줄 key: 이름}}}} —
  틀마다의 고를 줄 · 처음 줄 목록 · 문서 종류 짝(문서 하나 = 원본 없음 — 줄의 roles 는 모두 ["target"] · 저장하는 줄의 on 은 늘 빈 목록),
  base(전제를 물려받는 붙박이 키), limits, broken(저장 파일을 못 읽음 — 그동안 목록은 비고 쓰기는 409), warn{fillNoFit(목적 문서에 「구성 맞추기」 없이 「내용 넣기」 를 고를 때의 경고 뒷부분 —
  등록부 app/workflow.py FILL_NO_FIT)}}
- `POST /api/tasks` {name, desc?, source?, target?, assign?{source[], target[], llm?[]}, stages?[](옛 꼴 — assign 이 없을 때만), premise?} → 201 {task} · `PUT /api/tasks/{key}`(보낸 키만 — 문서 쌍은 못 고침) → {task} ·
  `DELETE /api/tasks/{key}` → {deleted} · 400 = 값이 틀림(글이 화면에 그대로) · 409 = 쓰는 중(PUT 은 배정을 바꿀 때 · 지금 워크플로우로 둔 작업이 있으면 — 글 = editWhy /
  DELETE 는 지금 워크플로우로 둔 작업 + 목록에만 든 작업이 있으면 — 글 = deleteWhy) · 저장 파일을 못 읽음(쓰지 않음)
- 조립한 워크플로우의 꼴(view) = {key, name, desc, source, target, assign{source, target, llm}, stages(합집합), premise, at, sourceName, targetName, groups(합집합의 묶음 id), does{묶음 id: 묶음 설명},
  sig(단계의 지문 — custom_tasks.sig), descAuto(실제 배정에서 지은 한 줄 설명 — 등록부 app/workflow.py custom_desc)} + 목록 · POST · PUT 의 응답에는 쓰는 곳
  {inUse(그 키를 지금 워크플로우로 둔 작업 수), listed(문서의 워크플로우 목록에만 든 작업 수), editWhy(단계를 못 바꾸는 까닭 | null), deleteWhy(못 지우는 까닭 | null),
  uses[{wid, name, project, round, active}](그 작업들 — 지금 워크플로우로 둔 것(active true) 먼저 · 목록에만 든 것(active false) 뒤 · 저마다 최근 바뀐 차례 · 앞 USES_MAX 개),
  usesMore(uses 에 못 실은 나머지 수 — 0 이면 다 실음)}. name = 작업 리스트가 보이는 그 작업의 이름(works.shown — 올린 파일 이름 + 목적 문서의 프로젝트 이름 · 별칭 · 프레임 이름) ·
  화면 /workflow 의 조립 목록 줄이 그 작업을 여는 링크로 보인다(spec_워크플로우 ② §15 「조립」 「쓰는 중인 정의」).
  문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」): assign = 원본 · 목적 문서마다 고른 단계(원본은 「문서 검토」 만) + llm(1단계 「LLM 검증·보완」 을 할 문서) ·
  does = 그 정의의 묶음 설명(등록부 app/workflow.py assemble 과 같은 글 — 화면 실행이 묶음 머리 · 「한 번에 진행」 · 실행 카드에 그대로 쓴다).
- **쓰는 곳**(`_uses` — 작업마다 한 번: 셈 · 작업 목록을 같은 한 번의 작업 읽기에서) = 그 키를 지금 워크플로우로 둔 작업(task.job — inUse: 단계를 못 바꾸고 못 지움) · 문서의 워크플로우 목록(works 의 workflows[].job — 대시보드의
  「이 문서의 워크플로우」)에만 그 키가 든 작업(listed: 단계는 고치지만 못 지움 — 목록에서 빼면 지운다: DELETE /api/works/{wid}/workflows/{job}).
- **내가 만든 단계**(spec_워크플로우 ② §18-14 — app/custom_stages.py): `GET /api/tasks` 의 `userStages[{key, name, desc, steps, at, lines}]` · `stages[].lines`(붙박이 단계의 표준 줄) · `stagesBroken` ·
  `POST /api/stages/check {steps}` → {errors, steps} · `POST /api/stages {name, desc?, steps}` → 201 {stage} · `PUT /api/stages/{key}` · `DELETE /api/stages/{key}` — 400 = 값이 틀림 · 404 = 없음 · 409 = 저장 파일을 못 읽음.
- `GET /api/tasks.js` → 화면이 스크립트로 읽는 글(`taskCatalogCustom([...], {broken})` — task_catalog.js 다음 · app.js 앞: 화면의 목록 · 문서 칸이 처음부터 조립한 워크플로우를 안다 ·
  꼴은 view 그대로(쓰는 곳은 빼고 — 앱 화면은 그것을 쓰지 않고, 읽을 때마다 작업을 모두 훑지 않게) · broken = 저장 파일을 못 읽음). 캐시 안 함."""
import json

from fastapi import APIRouter, Body, HTTPException, Response

from app import custom_stages, custom_tasks, tool_names, unit_help, works

router = APIRouter()

# 아직 조립할 수 없는 것 — 화면이 까닭과 함께 보인다(고를 수 없는 것을 감추지 않는다). 아직 못 여는 틀(「1」 문서 하나 · 「N → 1」 취합)은 조립 폼의 「문서 입출력」 이 그 틀의 까닭(custom_tasks.SHAPES soon)과 함께 보인다 — 여기 겹쳐 적지 않는다.
BLOCKED = (
    {"name": "다른 문서 쌍(사업계획서 → 사업계획서 · 연차보고서 → 연차보고서 · 연차보고서 → 사업계획서)",
     "why": "문서의 역할을 문서 종류(사업계획서 · 연차보고서 · 기관 문서)로만 가르고 있어 같은 종류끼리는 원본 · 목적을 가를 수 없고, 이관 실행의 글과 판정이 사업계획서 → 연차보고서에 맞춰져 있습니다."},
)


# 문서 역할 × 단계 표의 칸 글(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 조립 화면이 그대로 보인다). 칸의 꼴(mode)은 cells() 가 정한다:
# pick = 체크로 고름 · follow = 다른 역할이 이 단계를 고르면 따라오는 일(화면은 목적 문서가 골랐을 때만 이 글, 아니면 「—」) · no = 고를 수 없음(글 = 까닭)
CELL_TEXT = {
    "stage_review": {"source": "헤딩 · 표 분석 › LLM 검증·보완",
                     "target": "헤딩 · 표 분석 — LLM 검증·보완은 「구성 맞추기」 를 고르면 구조를 맞춘 뒤 「다시 문서 검토(LLM)」 에서, 안 고르면 여기서"},
    "stage_fit": {"source": "구성의 기준 — 구성 불러오기 › 프로젝트 구성 추출(문서는 안 바뀜)", "target": "프로젝트 구성 반영 › 다시 문서 검토(헤딩 · 표 분석 › LLM 검증·보완)"},   # 단계 사이 「 › 」(= 다음 — spec_워크플로우 ② §15 「이음 기호」)
    "stage_fill": {"source": "내용을 줌(바뀌지 않음)", "target": "← 원본 문서의 내용을 받음 — 자리 연결 › 넣기 계획 › 내용 반영"},
    "stage_clean": {"source": "원본은 바꾸지 않습니다", "target": "작성요령 삭제 — 지우기 전에 작성 지침을 저장"},
}


def cells(mid, steps):
    """단계 하나의 문서 역할마다 칸 → {역할: {mode, text}}. steps = 그 단계(모듈)의 단계들 — 하는 문서(on)가 적힌 것(app/workflow.py).
    그 역할이 고를 수 있으면 pick(custom_tasks.ROLE_STAGES), 아니면 그 단계의 일이 그 문서에 닿을 때(on 이 그 역할 · both · pair — 내용을 줌 · 구성의 기준 문서(custom_tasks.BASE_ROLE)면
    flow — 워크플로우 전체의 프로젝트 구성 추출) follow, 안 닿으면 no."""
    ons = {s["on"] for s in steps}
    touch = lambda r: {r, "both", "pair"} | ({"flow"} if r == custom_tasks.BASE_ROLE else set())  # noqa: E731
    return {r: {"mode": "pick" if mid in custom_tasks.ROLE_STAGES[r] else "follow" if ons & touch(r) else "no", "text": CELL_TEXT[mid][r]} for r in custom_tasks.ROLES}


def _builtin_names():
    from app import workflow
    return [v["name"] for v in workflow.catalog()[0].values()]


def view(t, used=None):
    """조립한 워크플로우 → 화면에 내는 꼴(문서 이름 · 묶음 id · 묶음 설명 · 단계의 지문 · 지은 한 줄 설명을 더한다 — assign(llm 포함) · stages(합집합)는 저장된 그대로).
    does = {묶음 id: 그 정의의 묶음 설명} — 등록부(app/workflow.py assemble)가 실제 배정에서 지은 글 그대로(화면 실행이 그대로 쓴다) · sig = custom_tasks.sig · descAuto = workflow.custom_desc.
    used = _uses() 의 값이면 쓰는 곳(inUse · listed · editWhy · deleteWhy — PUT 409 · DELETE 409 와 같은 글 · uses · usesMore — 그 작업들)도 더한다."""
    from app import workflow
    groups = [g["id"] for g in t["flow"]] if t.get("flow") is not None else [custom_tasks.STAGE_GROUP[s] for s in t["stages"]]
    v = {**t, "sourceName": custom_tasks.kind_name(t["source"]), "targetName": custom_tasks.kind_name(t["target"]), "groups": groups,   # 문서 종류의 이름(취합형의 원본 = 기관 문서)
         "does": {g["id"]: g["does"] for g in workflow.assemble(t)["stages"]}, "sig": custom_tasks.sig(t), "descAuto": workflow.custom_desc(t)}
    if t.get("flow") is None:   # 옛 꼴(표준 차례) — 조립 화면이 줄 목록으로 연다(등록부가 그 배정으로 짓는 것 그대로: ② §18-12 ⑤)
        v.update(flow=custom_tasks.flow_of(t), shape="relay", v=1)
    if used is not None:
        n, m, rows = used[0].get(t["key"], 0), used[1].get(t["key"], 0), used[2].get(t["key"], [])
        v.update(inUse=n, listed=m, editWhy=custom_tasks.IN_USE.format(n=n) if n else None, deleteWhy=custom_tasks.DELETE_IN_USE.format(n=n + m) if n + m else None,
                 uses=[dict(r) for r in rows[:USES_MAX]], usesMore=max(0, len(rows) - USES_MAX))
    return v


USES_MAX = 20   # view 의 uses 에 싣는 작업 수 — 나머지는 usesMore(셈 inUse · listed 는 늘 다 센다)
NO_USES = ({}, {}, {})   # _uses() 의 꼴 — 쓰는 작업이 없음(새로 만든 정의)


def _uses():
    """조립한 정의의 키 → 쓰는 작업(작업마다 한 번 — 셈과 작업 목록을 같은 한 번의 작업 읽기에서) —
    ({키: 그 키를 지금 워크플로우로 둔 작업 수(task.job)}, {키: 문서의 워크플로우 목록(workflows[].job)에만 그 키가 든 작업 수},
     {키: [{wid, name, project, round, active} …] — 지금 워크플로우로 둔 작업(active true) 먼저 · 목록에만 든 작업 뒤 · 저마다 최근 바뀐 차례(works.list_works)}).
    지금 워크플로우로 둔 작업은 그 목록에 같은 키가 있어도 앞에만 센다. name = 작업 리스트가 보이는 이름(works.shown — 이름이 없는 작업은 id)."""
    from app import projects
    active, listed, now_rows, list_rows = {}, {}, {}, {}
    for w in works.list_works():
        task = w.get("task") if isinstance(w.get("task"), dict) else {}
        now, row = task.get("job"), None
        for k in {now} | {r.get("job") for r in w.get("workflows") or [] if isinstance(r, dict)}:
            if isinstance(k, str) and custom_tasks.KEY.fullmatch(k):
                box, rows = (active, now_rows) if k == now else (listed, list_rows)
                box[k] = box.get(k, 0) + 1
                row = row or {"wid": w["id"], "name": (works.shown(w) if w.get("name") else "") or w["id"], "project": str(task.get("project") or ""), "round": projects.round_of(task)}   # 작업마다 한 번
                rows.setdefault(k, []).append({**row, "active": k == now})
    return active, listed, {k: now_rows.get(k, []) + list_rows.get(k, []) for k in {*now_rows, *list_rows}}


def uses(key):
    """그 정의를 쓰는 작업 수 → (지금 워크플로우로 둔 것 — inUse, 목록에만 든 것 — listed)."""
    active, listed, _ = _uses()
    return active.get(key, 0), listed.get(key, 0)


def in_use(key):
    """그 키를 지금 워크플로우로 둔 작업 수(inUse) — 하나라도 있으면 단계(배정)를 바꾸지 못한다(PUT 409 · 「복제」). 지우기는 목록에만 든 작업도 센다(uses — DELETE 409)."""
    return uses(key)[0]


_NO_TASK = "그런 워크플로우가 없습니다"   # 없는 키(API 404 — 화면에 그대로)


def units():
    """조립 화면의 고를 줄(② §18-5 「API」) — 이관형 · 공통 단위(준비는 빼고 — 맨 앞 묶음에 저절로) · 이름 · 사는 단계 · 놓을 자리 · 하는 문서 · 꼴 · 문서 바뀜 · 유료 · 선택 · 서버가 돌리나."""
    from app import workflow_units as WU
    names, homes = custom_tasks.unit_names(), custom_tasks.unit_homes()
    out = []
    for fam, box in (("common", WU.COMMON), ("relay", WU.RELAY)):
        for k, u in box.items():
            if k in custom_tasks.AUTO_UNITS:
                continue
            out.append({"key": k, "family": fam, "home": homes.get(k, u["home"]), "name": names.get(k, k), "place": u["place"], "roles": list(u["roles"]), "kind": u["kind"], "change": u["change"],
                        "paid": u["paid"], "needs": list(u["needs"]), "gives": list(u["gives"]), "optional": u["optional"], "server": u["server"],
                        **({"col": custom_tasks.col_of(k)} if u["place"] == "flow" else {}),   # 워크플로우 전체 줄이 처음 서는 문서 칸(② §18-6 「행 × 두 칸」 「워크플로우 전체 줄」 — 화면은 이것만 읽는다)
                        "help": unit_help.of("relay", k),   # 그 줄(도구)의 쉬운 설명(조립 폼의 「도구 설명」 열 — app/unit_help.py: 같이 쓰는 단위도 이관형의 글로)
                        "only": unit_help.only("relay", k),   # 그 도구가 어느 문서 전용인가({kind, label, why} | None = 문서를 가리지 않음 — spec_워크플로우 ② §18-17 「전용 표시」)
                        "uses": custom_tasks.uses_of(u)})   # 먼저 있어야 할 줄 — 그 줄이 쓰는 앞 줄들(② §18-6 「대상 잇기」 의 (나): 화면이 이것만 읽는다)
    order = {m: i for i, m in enumerate((*custom_tasks.STAGES, "hand"))}
    return sorted(out, key=lambda x: order.get(x["home"], 9))   # 사는 일반 단계의 차례(문서 검토 → 구성 맞추기 → 내용 넣기 → 문서 정리 → 사람이 하는 일) · 그 안은 등록부의 줄 차례


def gather_units():
    """취합형(N → 1)의 고를 줄 — 등록부 「사업계획서 취합」 의 줄 차례(custom_tasks.GATHER_UNITS) + 「사람이 하는 일」 → (줄들, 묶음들 [{id, name}]).
    줄의 home = 붙박이 취합에서 그 줄이 사는 묶음(gather_config · gather_frame · gather_map — 화면의 고르기 목록이 그 이름으로 묶는다) · each = 기관 문서마다 도는 줄(한 묶음에 잇달아 놓는다)."""
    from app import workflow
    from app import workflow_state as WS
    from app import workflow_units as WU
    names, base = custom_tasks.unit_names("gather"), workflow.BY_JOB["plan_merge"]
    home = {s["key"]: f"gather_{g['id']}" for g in base["stages"] for s in g["steps"]}
    out = []
    for k in custom_tasks.GATHER_UNITS:
        u = WU.unit(k, "gather")
        out.append({"key": k, "family": "gather", "home": home.get(k, "gather_map"), "name": names.get(k, k), "place": u["place"], "roles": list(WU.roles_in(u, "gather")), "kind": u["kind"], "change": u["change"],
                    "paid": u["paid"], "needs": list(u["needs"]), "gives": list(u["gives"]), "optional": u["optional"], "server": u["server"], "each": bool(u.get("each")),
                    **({"col": custom_tasks.col_of(k, "gather")} if u["place"] == "flow" else {}),   # 워크플로우 전체 줄이 처음 서는 문서 칸(취합 = 목적 문서: 취합본이 구성의 기준)
                    "help": unit_help.of("gather", k),   # 그 줄(도구)의 쉬운 설명(조립 폼의 「도구 설명」 열)
                    "only": unit_help.only("gather", k),   # 어느 문서 전용인가(② §18-17)
                    "uses": custom_tasks.uses_of(u, "gather")})   # 먼저 있어야 할 줄(② §18-6 「대상 잇기」 의 (나))
    h = WU.COMMON["hand"]
    out.append({"key": "hand", "family": "common", "home": "hand", "name": names["hand"], "place": h["place"], "roles": list(h["roles"]), "kind": h["kind"], "change": h["change"], "paid": h["paid"],
                "needs": [], "gives": [], "optional": h["optional"], "server": h["server"], "each": False, "help": unit_help.of("gather", "hand"), "only": None, "uses": []})
    homes = [{"id": f"gather_{g['id']}", "name": " ".join(x for x in WS.stage_label(g) if x)} for g in base["stages"]] + [{"id": "hand", "name": "사람이 하는 일"}]
    return out, homes


def gather_lines():
    """취합형의 처음 줄 목록(조립 폼이 「N → 1」 을 고르면 이것으로 채운다) — 붙박이 「사업계획서 취합」 의 묶음 · 줄 그대로(준비 · 기관에 배포 · 회수는 빼고)."""
    from app import workflow
    from app import workflow_state as WS
    from app import workflow_units as WU
    flow = []
    for g in workflow.BY_JOB["plan_merge"]["stages"]:
        steps = [{"unit": s["key"], "on": list(WU.roles_of(s["on"]))} for s in g["steps"] if s["key"] in custom_tasks.GATHER_UNITS and s["key"] != "drop"]
        if steps:
            flow.append({"name": WS.stage_label(g)[1] or g["id"], "steps": steps})
    return flow


def single_units():
    """문서 하나(「1」 — 목적 문서 하나 · 원본 없음: spec_워크플로우 ② §18-13 걸음 6)의 고를 줄 — 등록부 「사업계획서 양식 표준화」 의 줄 차례(custom_tasks.SINGLE_UNITS — 맨 앞 묶음에 저절로 서는 「준비」 는 빼고)
    + 「사람이 하는 일」 → (줄들, 묶음들 [{id, name}]). 칸은 취합형(gather_units)과 같다 · **roles 는 모든 줄이 ["target"]**(칸이 하나다 — 저장하는 줄의 on 은 늘 빈 목록) · each 는 늘 거짓 ·
    home = 붙박이 「양식 표준화」 에서 그 줄이 사는 묶음(single_config · single_heads · single_tables — 고르기 목록이 그 이름으로 묶는다) · name = 그 붙박이의 줄 이름(문서 종류마다의 이름은 single_names) ·
    uses = 그 줄이 쓰는 앞 줄(모두 must 가 아니다 — 정의에 없으면 경고일 뿐 · 정의에 있는데 뒤에 있으면 검사가 거절한다: custom_tasks._single_rules)."""
    from app import workflow
    from app import workflow_state as WS
    from app import workflow_units as WU
    names, base = custom_tasks.unit_names("single"), workflow.BY_JOB["plan_fit"]
    home = {s["key"]: f"single_{g['id']}" for g in base["stages"] for s in g["steps"]}
    out = []
    for k in custom_tasks.SINGLE_UNITS:
        if k == "hand":
            continue
        u = WU.SINGLE[k]
        out.append({"key": k, "family": "single", "home": home.get(k, "single_config"), "name": names.get(k, k), "place": u["place"], "roles": ["target"], "kind": u["kind"], "change": u["change"],
                    "paid": u["paid"], "needs": list(u["needs"]), "gives": list(u["gives"]), "optional": u["optional"], "server": u["server"], "each": False,
                    **({"col": custom_tasks.col_of(k, "single")} if u["place"] == "flow" else {}),   # 워크플로우 전체 줄이 서는 칸 — 문서 하나는 그 한 칸(목적 문서)
                    "help": unit_help.of("single", k),   # 그 줄(도구)의 쉬운 설명(조립 폼의 「도구 설명」 열)
                    "only": unit_help.only("single", k),   # 어느 문서 전용인가(② §18-17)
                    "uses": custom_tasks.uses_of(u, "single")})
    h = WU.COMMON["hand"]
    out.append({"key": "hand", "family": "common", "home": "hand", "name": names["hand"], "place": h["place"], "roles": ["target"], "kind": h["kind"], "change": h["change"], "paid": h["paid"],
                "needs": [], "gives": [], "optional": h["optional"], "server": h["server"], "each": False, "help": unit_help.of("single", "hand"), "only": None, "uses": []})
    homes = [{"id": f"single_{g['id']}", "name": " ".join(x for x in WS.stage_label(g) if x)} for g in base["stages"]] + [{"id": "hand", "name": "사람이 하는 일"}]
    return out, homes


def single_lines(kind="plan"):
    """문서 하나의 처음 줄 목록(조립 폼이 「1」 과 그 문서 종류를 고르면 이것으로 채운다) — 그 종류의 붙박이(사업계획서 = 양식 표준화 · 연차보고서 = 양식 맞추기)의 묶음 · 줄 그대로(준비 open 은 빼고 — 줄 `{unit, on: []}`)."""
    from app import workflow
    from app import workflow_state as WS
    flow = []
    for g in workflow.BY_JOB[custom_tasks.SINGLE_BASE[kind]]["stages"]:
        steps = [{"unit": s["key"], "on": []} for s in g["steps"] if s["key"] in custom_tasks.SINGLE_UNITS and s["key"] != "hand" and not s.get("soon")]
        if steps:
            flow.append({"name": WS.stage_label(g)[1] or g["id"], "steps": steps})
    return flow


def single_names(base=False):
    """문서 종류마다의 줄 이름 {종류: {줄 key: 이름}} — 등록부가 그 정의를 지을 때 쓰는 이름(그 종류의 붙박이 줄 이름이 먼저 — 연차보고서는 「프로젝트 구성 값 정하기」 · 「반영」: custom_tasks.unit_names).
    사람이 고친 도구 이름이 얹힌 화면 이름이다(② §18-19 — 도구 하나 = 이름 하나: 고친 도구는 어느 종류에서나 그 이름) · base=True = 기본 이름."""
    return {kind: {k: n for k, n in custom_tasks.unit_names("single", kind, base=base).items() if k in custom_tasks.SINGLE_UNITS} for _src, kind in custom_tasks.SINGLE_PAIRS}


def _based(units, family):
    """고를 줄마다 기본 이름(`base` — 등록부의 줄 이름)을 적는다. `name` 은 사람이 고친 도구 이름이 얹힌 화면 이름(custom_tasks.unit_names — spec_워크플로우 ② §18-19 「도구 이름 고치기」) → 받은 목록 그대로."""
    base = custom_tasks.unit_names(family, base=True)
    for u in units:
        u["base"] = base.get(u["key"], u["name"])
    return units


def _v2(v):
    """GET 의 판 — `?v=2` 면 줄 목록 정의(v2)도 싣는다. 옛 탭(판 없이 읽음)에는 표준 정의만 — 옛 화면의 이관 실행 코드가 v2 를 표준 차례로 돌리지 못하게(② §18-12 ⑤)."""
    return str(v or "") == "2"


# ---------------------------------------------------------------- 내가 만든 단계(spec_워크플로우 ② §18-14 「단계 만들기」 — app/custom_stages.py: 있는 줄을 골라 이름 붙여 둔 묶음 · 조립의 「＋ 단계 넣기…」 가 넣는다)
def _stage_names():
    """붙박이 단계의 이름들(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리) — 내가 만든 단계가 같은 이름을 못 쓰게."""
    from app import workflow
    return [name for _mid, name, _make, _does in workflow.STAGE_MODULES]


def _stage_lines():
    """붙박이 단계마다의 표준 줄 {단계 id: [{unit, on}]} — 두 문서에 모두 고른 표준 차례의 그 묶음(조립의 「＋ 단계 넣기…」 가 붙박이 단계도 같은 꼴로 넣는다)."""
    A = {"source": ["stage_review"], "target": list(custom_tasks.STAGES)}
    A["llm"] = custom_tasks.llm_rule(A)
    flow = custom_tasks.flow_of({"key": "u_00000000", "name": "_", "desc": "", "source": custom_tasks.PAIRS[0][0], "target": custom_tasks.PAIRS[0][1], "assign": A,
                                 "stages": custom_tasks.union(A), "premise": "", "at": 0})
    by = {g["id"]: g["steps"] for g in flow}
    return {mid: by.get(custom_tasks.STAGE_GROUP[mid], []) for mid in custom_tasks.STAGES}


def stage_view(s):
    """내가 만든 단계의 꼴 = {key, name, desc, steps[{unit, on …}], at, lines[줄 이름 — 화면의 요약]}."""
    names = custom_tasks.unit_names()
    return {**s, "lines": [x.get("name") or names.get(x["unit"], x["unit"]) for x in s["steps"]]}


def _stage_call(fn):
    try:
        return fn()
    except custom_stages.Refused as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/stages/check")
def stages_check(body: dict = Body(...)):
    """단계의 줄 검사(저장 전 미리 보기) {steps} → {errors[], steps(정리한 줄 | None)} — 조립과 같은 규칙에서 단계 하나로 볼 수 있는 것만(custom_stages.check)."""
    return custom_stages.check(body.get("steps"))


@router.post("/api/stages", status_code=201)
def stages_post(body: dict = Body(...)):
    """{name, desc?, steps[{unit, on}]} → 201 {stage} — 400 = 값이 틀림(글이 화면에 그대로) · 409 = 저장 파일을 못 읽음."""
    return {"stage": stage_view(_stage_call(lambda: custom_stages.create(body, _stage_names())))}


@router.put("/api/stages/{key}")
def stages_put(key: str, body: dict = Body(...)):
    s = _stage_call(lambda: custom_stages.update(key, body, _stage_names()))
    if s is None:
        raise HTTPException(404, "그런 단계가 없습니다")
    return {"stage": stage_view(s)}


@router.delete("/api/stages/{key}")
def stages_delete(key: str):
    if not _stage_call(lambda: custom_stages.delete(key)):
        raise HTTPException(404, "그런 단계가 없습니다")
    return {"deleted": True}


@router.get("/api/tasks")
def tasks_get(v: str = ""):
    from app import workflow
    lines = _stage_lines()
    shown = custom_tasks.unit_names()   # 줄의 화면 이름(사람이 고친 도구 이름이 얹힌 것 — ② §18-19)
    stages = [{"id": mid, "name": name, "does": does, "group": custom_tasks.STAGE_GROUP[mid], "steps": [{"key": s["key"], "name": shown.get(s["key"], s["name"]), "optional": s["optional"]} for s in steps],
               "cells": cells(mid, steps), "lines": lines.get(mid, [])}   # cells = 문서 역할 × 단계 표의 칸(② §15) · lines = 그 단계의 표준 줄(조립의 「＋ 단계 넣기…」)
              for mid, name, make, does in workflow.STAGE_MODULES for steps in [make(*workflow._GENERIC)]]
    used = _uses()
    g_units, g_homes = gather_units()
    s_units, s_homes = single_units()
    _based(g_units, "gather"), _based(s_units, "single")
    s_flows = {kind: single_lines(kind) for _src, kind in custom_tasks.SINGLE_PAIRS}
    return {"tasks": [view(t, used) for t in custom_tasks.all() if _v2(v) or t.get("flow") is None], "stages": stages, "units": _based(units(), "relay"), "shapes": custom_tasks.shapes(),   # shapes 의 soon 은 지금 열려 있는지를 따른다(문서 하나 = 스위치)
            # 틀마다의 고를 줄 · 처음 줄 목록 · 문서 종류 짝(units · pairs 는 이관형의 것 그대로 — 옛 화면) — 취합형(N → 1: spec_워크플로우 ② §18-13 갈래 「라」 ⓶)
            "byShape": {"gather": {"units": g_units, "homes": g_homes, "flow": gather_lines(),
                                   "pairs": [{"source": a, "target": b, "name": f"{custom_tasks.kind_name(a)} → {custom_tasks.kind_name(b)}"} for a, b in custom_tasks.GATHER_PAIRS]},
                        # 문서 하나(「1」 — 원본 없음: 같은 절 걸음 6) — flow = 사업계획서의 처음 줄 목록 · flows = 문서 종류마다 · pairs 의 value = 「>목적 종류」(원본 자리가 빈 글) · names = 문서 종류마다의 줄 이름
                        "single": {"units": s_units, "homes": s_homes, "flow": s_flows[custom_tasks.SINGLE_PAIRS[0][1]], "flows": s_flows,
                                   "pairs": [{"value": f"{a}>{b}", "source": a, "target": b, "name": custom_tasks.kind_name(b)} for a, b in custom_tasks.SINGLE_PAIRS], "names": single_names(), "baseNames": single_names(base=True)}},   # baseNames = 문서 종류마다의 기본 이름(② §18-19)
            "userStages": [stage_view(s) for s in custom_stages.all()], "stagesBroken": custom_stages.broken(),   # 내가 만든 단계(② §18-14)
            "hidden": 0 if _v2(v) else sum(1 for t in custom_tasks.all() if t.get("flow") is not None),
            "pairs": [{"source": a, "target": b, "name": f"{custom_tasks.FILES[a]} → {custom_tasks.FILES[b]}"} for a, b in custom_tasks.PAIRS], "blocked": list(BLOCKED), "base": custom_tasks.BASE,
            "limits": {"name": custom_tasks.NAME_MAX, "desc": custom_tasks.DESC_MAX, "premise": custom_tasks.PREMISE_MAX, "tasks": custom_tasks.TASKS_MAX, "toolName": tool_names.NAME_MAX},
            "broken": custom_tasks.broken(), "warn": {"fillNoFit": workflow.FILL_NO_FIT}}


@router.post("/api/tasks", status_code=201)
def tasks_post(body: dict = Body(...)):
    try:
        return {"task": view(custom_tasks.create(body, _builtin_names()), NO_USES)}   # 새 키 — 쓰는 작업이 없다
    except custom_tasks.Refused as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/tasks/check")
def tasks_check(body: dict = Body(...)):
    """조립 검사(저장 전 미리 보기 — ② §18-5 「API」): {flow, shape?, source?, target?, key?(고치는 정의 — 문서 쌍 · 틀을 그것에서)} → {errors[], warns[], flow(정리한 꼴 · 묶음 id), std(표준 차례인가), sig}.
    화면은 셈하지 않고 이것을 그대로 보인다 — POST · PUT 도 같은 검사를 지난다."""
    old = custom_tasks.get(body.get("key")) if isinstance(body.get("key"), str) else None
    shape = body.get("shape") or (old or {}).get("shape") or "relay"
    pair = custom_tasks.pairs_of(shape)[0]   # 그 틀의 문서 종류 짝(안 보냈을 때의 값)
    source, target = body.get("source") or (old or {}).get("source") or pair[0], body.get("target") or (old or {}).get("target") or pair[1]
    flow = body.get("flow")
    # 표준 차례로 채우기(조립 화면의 문서 역할 × 단계 표) — 그 배정으로 등록부가 짓는 줄 목록을 검사한다. 이관형의 것이다(취합형 · 문서 하나는 늘 줄 목록 — 그 틀에 배정을 보내면 줄 목록이 없는 것으로 검사한다:
    # 이관의 표준 차례를 짓는 길은 문서 종류의 이름이 있어야 한다 — 원본이 빈 글인 문서 하나로는 못 짓는다)
    if "flow" not in body and isinstance(body.get("assign"), dict) and custom_tasks.family_of(shape) == "relay" and all(isinstance(k, str) and k in custom_tasks.FILES for k in (source, target)):
        a = body["assign"]
        core = {r: [s for s in custom_tasks.ROLE_STAGES[r] if isinstance(a.get(r), list) and s in a[r]] for r in custom_tasks.ROLES}
        A = {**core, "llm": custom_tasks._llm_of(a["llm"], core) if isinstance(a.get("llm"), list) else custom_tasks.llm_rule(core)}
        if not custom_tasks.union(A):
            return {"errors": ["단계를 하나 이상 고르세요"], "warns": [], "flow": None, "std": False, "sig": None}
        flow = custom_tasks.flow_of({"key": "u_00000000", "name": "_", "desc": "", "source": source, "target": target, "assign": A, "stages": custom_tasks.union(A), "premise": "", "at": 0})
    got = custom_tasks.check(shape, source, target, flow)
    s = None
    if got["flow"] is not None and not got["errors"]:
        s = custom_tasks.sig({"assign": got["std"], "stages": custom_tasks.union(got["std"])} if got["std"] is not None else {"flow": got["flow"], "shape": shape, "source": source, "target": target})
    return {"errors": got["errors"], "warns": got["warns"], "flow": got["flow"], "std": got["std"] is not None, "sig": s}


@router.put("/api/tasks/{key}")
def tasks_put(key: str, body: dict = Body(...)):
    used = _uses()
    try:
        t = custom_tasks.update(key, body, _builtin_names(), busy=used[0].get(key, 0))   # 단계를 못 바꾸는 것은 지금 워크플로우로 둔 작업이 있을 때만(목록에만 든 정의는 고친다)
    except custom_tasks.Refused as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if t is None:
        raise HTTPException(404, _NO_TASK)
    return {"task": view(t, used)}


@router.delete("/api/tasks/{key}")
def tasks_delete(key: str):
    try:
        custom_tasks.writable()   # 못 읽은 저장 파일 — 「없음」 이 아니라 「쓰지 않음」(409)
    except custom_tasks.Refused as e:
        raise HTTPException(409, str(e)) from e
    if custom_tasks.get(key) is None:
        raise HTTPException(404, _NO_TASK)
    n, m = uses(key)
    if n + m:   # 지금 워크플로우로 둔 작업 + 목록에만 든 작업(지우면 그 줄이 모르는 키로 남는다) — 화면의 deleteWhy 와 같은 글
        raise HTTPException(409, custom_tasks.DELETE_IN_USE.format(n=n + m))
    try:
        gone = custom_tasks.delete(key)
    except custom_tasks.Refused as e:
        raise HTTPException(409, str(e)) from e
    if gone:
        from app import form_files
        form_files.forget_job(key)   # 그 워크플로우에 건 양식 설정도 푼다(spec_워크플로우 ② §18-9 — 지운 키의 설정이 남아 양식을 못 지우지 않게)
        from app import agent_notes
        agent_notes.forget_job(key)   # 그 워크플로우 전용으로 적어 둔 에이전트의 덧붙이는 글도 지운다(spec_에이전트 ② §6)
    return {"deleted": gone}


@router.get("/api/tasks.js")
def tasks_js(v: str = ""):
    """화면의 워크플로우 목록에 조립한 워크플로우를 더하는 스크립트 — task_catalog.js 의 `taskCatalogCustom(목록, {broken})` 을 부른다(그 함수가 없으면 아무 일도 안 함).
    목록의 꼴 = view(쓰는 곳은 빼고) · broken = 저장 파일을 못 읽음(그동안 목록은 비어 있다 — 화면이 까닭을 보일 수 있게)."""
    made, broken = [view(t) for t in custom_tasks.all() if _v2(v) or t.get("flow") is None], custom_tasks.broken()   # 판 없이 읽는 옛 탭에는 표준 정의만(② §18-12 ⑤)
    body = ("if (typeof taskCatalogCustom === \"function\") taskCatalogCustom(" + json.dumps(made, ensure_ascii=False).replace("</", "<\\/")
            + ", " + json.dumps({"broken": broken}) + ");\n")
    return Response(body, media_type="text/javascript; charset=utf-8", headers={"Cache-Control": "no-store"})
