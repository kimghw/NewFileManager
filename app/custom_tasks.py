"""조립한 TASK — 사용자가 화면(`/workflow` 의 「TASK 조립」)에서 단계를 골라 만든 TASK(spec_워크플로우 ② §14).

2026-11-19 사용자 "각 단계를 , 여기 모듈로 두고,, task 모듈로 조립할 수 있도록" → "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」: 일반 단계(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리)를
골라 이름 붙인 TASK 를 화면에서 만든다 — 만든 TASK 는 TASK 카드 · 워크플로우 · 대시보드에 서고, 고른 단계만으로 실행된다.
**가벼운 모듈**(works · server · workflow · job_prompts 가 가져온다 — 다른 app 모듈을 가져오지 않는다).

- 저장 = `%LOCALAPPDATA%\\NewFileManager\\tasks.json`(env `NFM_TASKS` 가 파일 경로 · `off`·`0` 이면 메모리만) =
  `{version, tasks: [{key, name, desc, source, target, assign{source[단계 id…], target[단계 id…], llm[역할…]}, stages[단계 id…], premise, at}]}`.
  이 PC 의 모든 문서가 같이 쓴다. 고친 시각 기준으로 다시 읽는다(다른 프로세스가 고쳐도 다음 호출에 반영).
- **저장 파일 보호**(astra 검토 2026-11-19 — 조용한 소실): 파일이 있는데 못 읽으면(JSON 이 깨짐 · 머리가 사전이 아님 · tasks 가 목록이 아님) 읽기는 빈 목록(`broken()` 이 참)이고
  **쓰지 않는다**(`Refused` — API 409: 다음 쓰기가 파일을 빈 목록으로 덮지 않게). 읽기 오류(다른 프로세스가 바꿔 넣는 중 · 권한 — OSError)는 **그 호출만** 못 읽은 것으로 보고 남기지 않는다
  (다음 호출이 다시 읽는다 — 남기는 것은 읽어서 해석한 결과뿐: 정상 · JSON 이 깨짐). 꼴이 틀린 줄(모르는 문서 쌍 · 고른 단계가 없음 · 겹친 키 · `TASKS_MAX` 뒤 · stages 가 목록이 아닌 옛 줄 …)은
  화면 목록에 안 보이고 **원래 모습 그대로** 남는다 — 쓸 때는 만들거나 고치거나 지운 줄만 바뀌고 그 밖의 줄은 읽은 그대로 쓴다(머리의 모르는 키도).
  고친 줄도 **고친 칸만** 다시 쓴다 — 배정이 그대로인 고치기(이름 · 설명 · 전제만)는 저장된 assign · stages 를 읽은 그대로 둔다(이 판이 모르는 단계 id 도). 지우기는 그 키의 줄을 모두 뺀다
  (보이는 줄 · 같은 키로 숨은 뒤 줄 · 꼴이 틀린 같은 키의 줄 — 지운 키가 다른 내용으로 되살아나지 않게).
- **문서마다 단위문서 TASK**(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 2026-11-19 사용자 "목적문서랑 원본문서에 대해서 각각 task 를 할당할 수 있도록 해줘"):
  `assign` = 문서 역할(원본 · 목적)마다 고른 단계(일반 단계의 차례 — 원본 문서는 「문서 검토」 만: `ROLE_STAGES` — 원본은 그 워크플로우에서 바뀌지 않는다) +
  `llm` = 1단계 「LLM 검증·보완」 을 할 문서 역할(`llm_rule` 이 허락하는 것만 — 「문서 검토」 를 고른 원본 · 「문서 검토」 를 골랐고 「구성 맞추기」 는 안 고른 목적).
  `llm` 은 저장할 때 **역할마다** 정한다: 규칙이 그 역할을 보는 입력(원본 = 「문서 검토」 · 목적 = 「문서 검토」 · 「구성 맞추기」)이 저장된 것과 같으면 그 역할의 저장된 결정을 지키고,
  입력이 바뀐 역할만 규칙(`llm_rule`)으로 다시 센다 — 결과는 늘 규칙의 부분(옛 줄의 「원본만」 에 다른 단계를 더해도 넓어지지 않는다 · 새로 만들 때 보낸 값은 받는다 — 「복제」).
  `sig` = 배정(원본 · 목적 · llm)과 합집합의 짧은 지문 — 단계가 바뀔 때만 바뀐다(화면이 연 뒤 정의가 바뀌었는지 견준다).
  `stages` = 두 역할의 합집합(같이 적는다 — 묶음 id `groups` 와 옛 서버가 그것을 읽는다).
  **옛 줄**(`assign` 없이 `stages` 만 — ② §14 의 꼴)은 버리지 않고 원본 = 「문서 검토」 가 있으면 [문서 검토] · 목적 = stages · llm = 「문서 검토」 가 있으면 [원본] 으로 읽는다(`from_stages` —
  옛 뜻 그대로: 1단계의 LLM 검증·보완은 원본 문서만 · astra P1 ⓐ). **옛 꼴 요청**(assign 없이 stages 만 — 옛 화면)은 합집합이 저장된 것과 같으면 저장된 배정을 그대로 두고, 다르면 옛 줄 규칙으로 읽는다.
- 거절(ValueError — API 400): 원본에 「문서 검토」 밖의 단계(`SOURCE_ONLY`) · 고른 것 없음 · **원본 문서를 쓰는 단계가 없음**(원본이 비었고 목적에 「구성 맞추기」 · 「내용 넣기」 가 없음 — `NO_SOURCE`).
  **쓰는 중인 정의**(그 키를 지금 워크플로우로 둔 작업이 있음 — 부르는 쪽이 `busy` 로 센다: app/custom_tasks_api.py `in_use`)는 실제 배정(원본 · 목적 · llm)을 바꾸지 않는다(`Refused` — API 409 · 「복제」 로 새 정의를) —
  이름 · 설명 · 전제는 고친다. 문서의 워크플로우 목록에만 든 정의는 단계를 고칠 수 있지만 지우지는 못한다(지우기는 부르는 쪽이 둘 다 센다 — `DELETE_IN_USE`).
- **지금 조립할 수 있는 틀 = 이관형 하나**(원본 문서 하나 → 목적 문서 하나) · **문서 쌍 = `PAIRS`**(지금 사업계획서 → 연차보고서 하나):
  문서의 역할을 첨부 파일 종류(plan · report · part)로만 가르고 있어 같은 종류끼리(계획서 → 계획서)는 원본 · 목적을 가를 수 없고, 화면 · 서버의 이관 실행이 두 종류의 이름에 묶여 있다 —
  다른 쌍 · 취합형(원본 여럿)은 그 묶임을 푼 뒤에 더한다(사양 ④).
- 키 = `u_` + 16진 8자(server.TASK["job"] 의 붙박이 키와 겹치지 않는다). 단계는 일반 단계의 차례(`STAGES`)로만 선다 — 고르는 것은 「쓰느냐」 뿐이다.
- 전제(`premise` — 그 TASK 의 LLM 호출이 읽는 글)는 비우면 틀이 같은 붙박이 TASK 의 전제(`BASE` — jobs/plan_to_report.md)를 쓴다(app/job_prompts.py)."""
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

KEY = re.compile(r"u_[0-9a-f]{8}")
STAGES = ("stage_review", "stage_fit", "stage_fill", "stage_clean")   # 일반 단계의 차례 — app/workflow.py STAGE_MODULES 와 같아야 한다(tests/test_custom_tasks.py)
STAGE_GROUP = {"stage_review": "review", "stage_fit": "frame", "stage_fill": "map", "stage_clean": "clean"}   # 단계 → 이관 실행의 묶음 id(화면 app.js TASK_STAGES · 서버 …/merge-links/reset)
FILES = {"plan": "사업계획서", "report": "연차보고서"}   # 문서 종류의 이름(works.FILE_LABEL 과 같게)
PAIRS = (("plan", "report"),)   # 지금 조립할 수 있는 (원본, 목적) 문서 쌍 — 이관 실행이 받는 쌍
BASE = "plan_to_report"         # 틀이 같은 붙박이 TASK — 전제를 비우면 이 TASK 의 전제를 쓴다
BASE_ROLE = "source"            # 조립한 워크플로우의 구성의 기준 문서 역할(이관형 — 원본: 조립 표의 「구성의 기준」 칸 · app/workflow.py 의 base 는 목적 문서에 「구성 맞추기」 가 있을 때만 이것)
ROLES = ("source", "target")    # 문서 역할 — 원본 문서 · 목적 문서(차례 = 원본 → 목적: app/workflow.py ROLES)
ROLE_STAGES = {"source": ("stage_review",), "target": STAGES}   # 역할마다 고를 수 있는 단계(spec_워크플로우 ② §15) — 원본 문서는 「문서 검토」 만(원본은 바뀌지 않는다)
SOURCE_USE = ("stage_fit", "stage_fill")   # 목적 문서의 단계 가운데 원본 문서를 쓰는 것(구성의 기준 · 내용을 줌) — 원본이 비었으면 이 가운데 하나는 있어야 한다
SOURCE_ONLY = "원본 문서는 이 워크플로우에서 바뀌지 않아 「문서 검토」 만 고를 수 있습니다"   # 원본에 문서 검토 밖의 단계를 고르면(화면에 그대로 보이는 글)
NO_SOURCE = "원본 문서를 쓰는 단계가 없습니다 — 원본 문서의 「문서 검토」 나 목적 문서의 「구성 맞추기」 · 「내용 넣기」 를 고르세요"
BAD_LLM = "LLM 검증·보완을 할 문서의 꼴이 틀립니다"
IN_USE = "이 워크플로우로 하던 작업이 {n}개 있어 단계를 바꿀 수 없습니다 — 「복제」 로 새 워크플로우를 만들어 고치세요"   # 지금 워크플로우로 둔 작업이 있는 정의의 배정을 바꾸려 하면(API PUT 409 · 화면의 editWhy)
DELETE_IN_USE = ("이 워크플로우를 쓰는 작업이 {n}개 있어 지울 수 없습니다 — 지금 워크플로우로 둔 작업은 다른 워크플로우로 바꾸고, "
                 "대시보드 「이 문서의 워크플로우」 목록에서 빼면 지울 수 있습니다")   # n = 지금 워크플로우로 둔 작업 + 목록에만 든 작업(API DELETE 409 · 화면의 deleteWhy)
BROKEN = "저장 파일({name})을 읽지 못해 쓰지 않습니다 — 파일을 고치거나 옮긴 뒤 다시 하세요"   # 못 읽은 파일에 쓰려 하면(API 409)
NAME_MAX, DESC_MAX, PREMISE_MAX, TASKS_MAX = 40, 200, 8000, 50
_FIELDS = ("key", "name", "desc", "source", "target", "assign", "stages", "premise", "at")   # 저장하는 줄의 키(이 밖의 키는 고칠 때도 그대로 둔다)


class Refused(ValueError):
    """쓰지 않음(API 409 — 글은 화면에 그대로) — 저장 파일을 못 읽었거나(BROKEN) · 쓰는 중인 정의의 배정을 바꾸려 함(IN_USE). 그 밖의 ValueError 는 값이 틀림(400)."""


_LOCK = threading.RLock()
_MEMORY = {"version": 0, "tasks": []}   # 메모리만(NFM_TASKS=off) — 파일의 JSON 과 같은 꼴(줄은 원래 모습 그대로)
_CACHE = {"path": None, "mtime": None, "data": None}


def path():
    """저장 파일 Path | None(메모리만)."""
    env = os.environ.get("NFM_TASKS", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "tasks.json"


def llm_rule(core):
    """원본 · 목적이 고른 단계 → 1단계 「LLM 검증·보완」 을 할 문서 역할(규칙 — 역할 차례): 「문서 검토」 를 고른 원본 · 「문서 검토」 를 골랐고 「구성 맞추기」 는 안 고른 목적
    (구성을 맞추면 목적 문서의 LLM 검증·보완은 구조를 맞춘 뒤 「다시 문서 검토(LLM)」 에서 한다 — app/workflow.py _st_fit). 저장하는 llm 은 늘 이것의 부분이다(`_llm_of`)."""
    return [r for r in ROLES if "stage_review" in core[r] and not (r == "target" and "stage_fit" in core[r])]


def _llm_of(raw, core):
    """llm 값 → 규칙(llm_rule)이 허락하는 역할만(역할 차례) — 넓히지 않는다(「문서 검토」 를 안 고른 문서 · 구조를 맞출 목적 문서의 1단계 LLM 은 없다). 좁히는 것은 된다(옛 줄 — 원본만)."""
    allowed = llm_rule(core)
    return [r for r in ROLES if r in raw and r in allowed]


def from_stages(stages):
    """옛 꼴(단계 하나 목록 — assign 없음: ② §14 의 줄 · 옛 화면의 요청) → assign: 원본 = 「문서 검토」 가 있으면 [문서 검토] · 목적 = 그 단계들(일반 차례) ·
    llm = 「문서 검토」 가 있으면 [원본](옛 뜻 그대로 — 1단계는 두 문서 분석 + 원본 문서의 LLM 검증·보완이었다: 「구성 맞추기」 가 없는 옛 줄도 목적 문서의 1단계 LLM 을 더하지 않는다 · astra P1 ⓐ)."""
    picked = [s for s in STAGES if s in stages]
    review = "stage_review" in picked
    return {"source": ["stage_review"] if review else [], "target": picked, "llm": ["source"] if review else []}


def union(assign):
    """두 역할에서 고른 단계의 합집합(일반 차례) — 저장의 `stages` · 화면의 묶음(groups)."""
    return [s for s in STAGES if any(s in assign[r] for r in ROLES)]


# ---------------------------------------------------------------- 정의 v2 — 문서 칸 + 묶음 › 줄(spec_워크플로우 ② §18-5 · 고친 규칙 ② §18-12 ④ · ⑤ — 2026-11-20 사용자 「1권장으로 진행하도록해 …」)
# 저장 꼴: {key, name, desc, source, target, shape, v: 2, flow: [{id, name, steps: [{unit, on: [역할…], id?, name?, note?, tool?}]}], premise, at} — assign · stages 는 적지 않는다(옛 서버가 숨기고 그대로 둔다).
# **표준 정의는 한 표현만**: 줄 목록이 어떤 배정(assign)으로 만든 표준 차례와 꼭 같으면(묶음 id · 이름 · 경계 · 줄 · 하는 문서 · 차례) 옛 꼴(assign + stages)로 저장한다 — 옛 서버 · 옛 화면이 그대로 읽는다.
# 표준이 아닌 줄 목록(차례를 바꿈 · 줄을 뺌 · 사람이 하는 일 …)만 v2 로 — 그 실행은 서버 실행기만(옛 화면의 이관 실행 코드는 표준 차례만 안다: § 18-11 위험 ⓑ).
# 틀 = 문서 입출력의 꼴(② §18-8 「문서 입출력」 — 2026-11-20 사용자 "1->N, N-1 문서 입출력 … 입력을 설정할 수 있어야"): io = 화면의 꼴 · slots = 문서 칸(차례 = 원본 → 목적 · 칸마다 수 · 고를 수 있는 문서 종류).
# 화면은 이 목록을 그대로 그린다(셈하지 않는다) · 아직 못 여는 틀(soon)은 까닭과 함께 보이되 고를 수 없다. 이관의 종류 짝은 PAIRS 가 본다(칸의 kinds 는 그 짝에서).
KIND_NAMES = {**FILES, "part": "기관 문서"}   # 문서 칸의 종류 이름(works.FILE_LABEL 과 같게 — 기관 문서 = 취합의 원본)
_kinds = lambda ids: [{"id": k, "name": KIND_NAMES[k]} for k in ids]  # noqa: E731
# 취합형(N → 1 — 2026-11-20 사용자 「왜 이거 N-1 은 왜 없냐?」: spec_워크플로우 ② §18-13 갈래 「라」 ⓶): 원본 = 기관 문서(여럿) → 목적 = 사업계획서(취합본) 하나. 「연차보고서 취합」 은 근거가 없어 아직(§18-12 ⑥).
GATHER_PAIRS = (("part", "plan"),)
GATHER_UNITS = ("config", "division", "frame", "part", "heads", "link", "llm", "plan", "apply", "drop")   # 취합형에 놓을 수 있는 줄 — 이 차례가 곧 놓는 차례(등록부 「사업계획서 취합」 의 줄 차례 · 「기관에 배포 · 회수」 는 앱 밖의 일이라 줄로 놓지 않는다 — 확인이 필요하면 「사람이 하는 일」)
GATHER_EACH = ("기관 문서마다 도는 줄(반영할 기관 지정 · 헤딩 · 표 분석 · 자리 연결 · LLM 검토 · 넣기 계획 · 내용 반영)은 한 묶음에 잇달아 놓으세요 — "
               "기관 문서 하나를 끝낸 뒤 다음 문서로 갑니다(사이에 다른 줄을 둘 수 없습니다)")


def pairs_of(shape):
    """그 틀에서 조립할 수 있는 (원본, 목적) 문서 종류 짝들 — 이관형 PAIRS · 취합형 GATHER_PAIRS."""
    return GATHER_PAIRS if shape == "gather" else PAIRS


def kind_name(kind):
    return KIND_NAMES.get(kind, kind)
SHAPES = (
    {"id": "single", "io": "1", "name": "문서 하나 — 목적 문서 하나를 분석 · 구조화", "family": "single", "many": False,
     "slots": [{"role": "target", "title": "목적 문서", "many": False, "kinds": _kinds(("plan", "report"))}],
     "soon": "문서 하나 워크플로우는 아직 조립할 수 없습니다 — 문서 하나에 하는 일(헤딩 추출 · 표 · 조정)을 서버가 차례로 돌리게 된 뒤에 엽니다 · "
             "지금은 붙박이 「사업계획서 양식 표준화」 · 「연차보고서 양식 맞추기」 로 합니다"},   # 그 뒤 = spec_워크플로우 ② §18-10 걸음 6
    {"id": "relay", "io": "1 → N", "name": "이관 — 원본 문서 하나 → 목적 문서 여럿", "family": "relay", "many": False,   # 2026-11-20 사용자 「이관은 1-N으로 해줘」 — 실행은 지금 목적 문서 하나씩(spec ② §18-8 · ④)
     "slots": [{"role": "source", "title": "원본 문서", "many": False, "kinds": _kinds(dict.fromkeys(a for a, _ in PAIRS))},
               {"role": "target", "title": "목적 문서", "many": True, "kinds": _kinds(dict.fromkeys(b for _, b in PAIRS))}], "soon": ""},
    {"id": "gather", "io": "N → 1", "name": "취합 — 원본 문서 여럿 → 목적 문서 하나", "family": "gather", "many": True,
     "slots": [{"role": "source", "title": "원본 문서", "many": True, "kinds": _kinds(("part",))},
               {"role": "target", "title": "목적 문서", "many": False, "kinds": _kinds(dict.fromkeys(b for _, b in GATHER_PAIRS))}], "soon": ""},   # 2026-11-20 엶(② §18-13 갈래 「라」 — 서버가 원본 문서마다의 덩이 · 배포 기준본을 돈다) · 목적 = 사업계획서(취합본)뿐
)
GROUPS_MAX, LINES_MAX, GROUP_NAME_MAX, HAND_NAME_MAX, HAND_NOTE_MAX = 8, 40, 20, 30, 200
AUTO_UNITS = ("files",)   # 맨 앞 묶음에 저절로 서는 줄(준비 — 문서 칸) — 사람이 놓지 않는다
HAND_ID = re.compile(r"hand[1-9][0-9]?")
TOOL_ID = re.compile(r"[a-z][a-z0-9_]{0,39}")
NO_SOURCE_FLOW = "원본 문서를 쓰는 줄이 없습니다 — 원본 문서의 「헤딩 · 표 분석」 이나 「프로젝트 구성 확정」(구성의 기준) · 「자리 연결」 같은 원본 → 목적 줄을 넣으세요"
FLOW_LOCKED = "이 워크플로우는 줄 목록으로 조립한 것이라 이 화면에서 단계를 고칠 수 없습니다 — 워크플로우 페이지를 새로 읽은 뒤 고치세요"   # 옛 화면(assign 꼴)이 v2 정의를 고치려 할 때(409)
# 먼저 있어야 할 줄(spec_워크플로우 ② §18-6 「대상 잇기」 의 (나) — 2026-11-20 「잘 연결될 수 있도록」 에 에이전트가 더한 것: 사용자의 「대상」 은 상대 문서다 — 그 절의 (가) 쌍 줄): 줄이 쓰는 앞 줄 = 단위의 needs 를 그것을 주는 줄로 옮긴 것.
# 조립 화면이 이것(GET /api/tasks 의 units[].uses)만 읽어 그 앞 줄이 없는 줄을 고르기에서 끄고(「먼저 「…」 을 넣으세요」) · 그 앞 줄 뒤 제자리에 넣는다 — 화면에 규칙을 새로 적지 않는다. 거절 · 경고의 판정은 아래 check 그대로다(시험이 둘을 맞춘다).
NEED_UNIT = {"heads": "heads", "config": "config", "fit": "division", "fresh": "reheads", "links": "link", "plan": "plan", "filled": "apply"}   # 사실 → 그것을 주는 줄(check 의 title 과 같은 짝)
NEED_SOFT = ("heads", "fresh", "config", "filled")   # 그것을 주는 줄이 앞에 없어도 거절하지 않는 사실(경고 · 실행의 안전망 — check 의 elif 가지들)
NEED_MUST = (("reheadsLlm", "reheads"),)   # 사실로는 무른(fresh) 대상이지만 따로 거절하는 짝(check 「「다시 문서 검토(LLM)」 은 「다시 문서 검토」 뒤에」)
GATHER_USES = {"apply": ("plan",), "plan": ("link",), "llm": ("link",)}   # 취합형의 대상(모두 must — _gather_rules 의 「앞 줄 없이 놓은 줄」 과 같은 짝)


def uses_of(u, family="relay"):
    """그 줄(단위 u)이 쓰는 앞 줄 → [{unit(그 결과를 만드는 줄의 key), must(그 줄이 앞에 없으면 조립 검사가 거절)}] — 차례 = 단위의 needs 차례. 취합형은 GATHER_USES."""
    if family == "gather":
        return [{"unit": k, "must": True} for k in GATHER_USES.get(u["key"], ())]
    return [{"unit": NEED_UNIT[f], "must": f not in NEED_SOFT or (u["key"], NEED_UNIT[f]) in NEED_MUST} for f in u["needs"] if f in NEED_UNIT]


def unit_names(family="relay"):
    """줄(단위 key) → 화면 이름 — 등록부의 일반 단계가 만든 줄의 이름(app/workflow.py STAGE_MODULES) + 「사람이 하는 일」. 줄의 글은 등록부에만 둔다.
    취합형(family gather)은 등록부 「사업계획서 취합」 의 줄 이름(그 줄들이 취합형의 단위다 — 「기관에 배포 · 회수」 자리의 hand 는 조립에서는 「사람이 하는 일」)."""
    from app import workflow
    out = {}
    if family == "gather":
        for g in workflow.BY_JOB["plan_merge"]["stages"]:
            for s in g["steps"]:
                out.setdefault(s["key"], s["name"])
        out["hand"] = "사람이 하는 일"
        return out
    for mid, _name, make, _does in workflow.STAGE_MODULES:
        opts = {"stage_review": {"llm": ("source", "target")}}.get(mid, {})   # 두 문서의 「LLM 검증·보완」 까지 서게
        for s in make(*workflow._GENERIC, **opts):
            out.setdefault(s["key"], s["name"])
    out["hand"] = "사람이 하는 일"
    return out


def unit_homes():
    """줄(단위 key) → 사는 일반 단계(STAGES 의 id) — 등록부의 일반 단계 함수가 만든 줄에서."""
    from app import workflow
    out = {}
    for mid, _name, make, _does in workflow.STAGE_MODULES:
        for s in make(*workflow._GENERIC, **({"llm": ("source", "target")} if mid == "stage_review" else {})):
            out.setdefault(s["key"], mid)
    return out


def _flow_in(raw):
    """보낸 · 저장된 줄 목록 → 정리한 꼴(꼴만 본다 — 뜻의 검사는 check). ValueError = 꼴이 틀림(화면에 그대로).
    묶음 = {id(저장소가 정함 — 받은 것은 견줄 때만), name(1~20자 · 비면 「묶음 N」), steps} · 줄 = {unit, on[역할 — 차례 원본 → 목적]} + 사람이 하는 일은 {id(hand1 … — 겹치거나 비면 차례로 새로), name, note, tool}."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("묶음을 하나 이상 두세요")
    if len(raw) > GROUPS_MAX:
        raise ValueError(f"묶음은 {GROUPS_MAX}개까지입니다")
    out, n = [], 0
    for i, g in enumerate(raw):
        if not isinstance(g, dict) or not isinstance(g.get("steps"), list):
            raise ValueError("묶음의 꼴이 틀립니다")
        steps = []
        for s in g["steps"]:
            if not isinstance(s, dict) or not isinstance(s.get("unit"), str) or not s["unit"]:
                raise ValueError("줄의 꼴이 틀립니다")
            on = s.get("on", [])
            if not isinstance(on, list) or any(r not in ROLES for r in on):
                raise ValueError("줄의 「하는 문서」 꼴이 틀립니다")
            line = {"unit": s["unit"], "on": [r for r in ROLES if r in on]}
            if s["unit"] == "hand":
                line.update(id=s["id"] if isinstance(s.get("id"), str) and HAND_ID.fullmatch(s["id"]) else "", name=" ".join(str(s.get("name") or "").split())[:HAND_NAME_MAX],
                            note=" ".join(str(s.get("note") or "").split())[:HAND_NOTE_MAX], tool=s["tool"] if isinstance(s.get("tool"), str) and TOOL_ID.fullmatch(s["tool"]) else "")
            steps.append(line)
        n += len(steps)
        name = " ".join(str(g.get("name") or "").split())[:GROUP_NAME_MAX] or f"묶음 {i + 1}"
        out.append({"id": g["id"] if isinstance(g.get("id"), str) else "", "name": name, "steps": steps})
    if n > LINES_MAX:
        raise ValueError(f"줄은 모두 {LINES_MAX}개까지입니다")
    hands = [s for g in out for s in g["steps"] if s["unit"] == "hand"]   # 사람이 하는 일의 줄 id — 받은 것을 지키고(확인 기록이 그 id 에 묶인다) 겹치거나 빈 것은 차례로 새로
    keep, used = [], set()
    for s in hands:
        keep.append(bool(s["id"]) and s["id"] not in used)
        used.add(s["id"])
    k = 1
    for s, ok in zip(hands, keep):
        if not ok:
            while f"hand{k}" in used:
                k += 1
            s["id"] = f"hand{k}"
            used.add(s["id"])
    return out


def flow_of(c):
    """옛 꼴 정의(assign — 표준 차례)의 줄 목록 = 지금 등록부가 그 배정으로 짓는 것(workflow.assemble — ② §18-12 ⑤ 「옛 줄을 읽는 기준」)에서 준비 · 준비 중인 줄을 뺀 것."""
    from app import workflow
    from app import workflow_units as WU
    return [{"id": g["id"], "name": g["name"], "steps": [{"unit": s["key"], "on": list(WU.roles_of(s["on"]))} for s in g["steps"] if s["key"] not in AUTO_UNITS and not s.get("soon")]}
            for g in workflow.assemble(c)["stages"]]


def guess_assign(flow):
    """줄 목록 → 그 줄들이 닿는 일반 단계로 읽은 배정(표준인지 견줄 후보 · 등록부 글의 바탕) — 실행은 이것을 쓰지 않는다(줄 목록 그대로 돈다)."""
    on, homes = {}, unit_homes()
    for g in flow:
        for s in g["steps"]:
            on.setdefault(s["unit"], set()).update(s["on"] or (ROLES if s["unit"] != "hand" else ()))
    has = lambda mid: any(homes.get(u) == mid for u in on)  # noqa: E731
    src = ["stage_review"] if "source" in on.get("heads", ()) else []
    dst = [m for m in STAGES if (m == "stage_review" and "target" in on.get("heads", ())) or (m != "stage_review" and has(m))]
    return {"source": src, "target": dst, "llm": [r for r in ROLES if r in on.get("headsLlm", ())]}


def _plain(flow):
    return [[g["name"], [[s["unit"], list(s["on"])] for s in g["steps"]]] for g in flow]


def standard(source, target, flow):
    """줄 목록이 표준 차례인가 → 그 배정(assign — llm 포함) | None. 후보 배정으로 등록부가 짓는 줄 목록과 묶음 이름 · 경계 · 줄 · 하는 문서 · 차례가 모두 같을 때만(② §18-12 ⑤ — 같은 줄을 두 묶음으로 쪼개면 표준이 아니다)."""
    if any(s["unit"] == "hand" for g in flow for s in g["steps"]):
        return None
    A = guess_assign(flow)
    if not union(A) or (not A["source"] and not any(s in A["target"] for s in SOURCE_USE)):
        return None
    A = {**A, "llm": _llm_of(A["llm"], A)}
    try:
        std = flow_of({"key": "u_00000000", "name": "_", "desc": "", "source": source, "target": target, "assign": A, "stages": union(A), "premise": "", "at": 0})
    except Exception:  # noqa: BLE001 — 표준 차례를 지을 수 없는 배정은 표준이 아니다
        return None
    return A if _plain(std) == _plain(flow) else None


def _facts_of(s, u, key):
    """줄 하나가 그 사실 이름(gives · needs · spoils)에서 닿는 사실들 — 문서마다의 사실(heads · checked · 구조 fit · 분석의 신선함 fresh)은 줄의 하는 문서마다(원본 → 목적 줄은 두 문서) · 그 밖은 워크플로우에 하나.
    구조 · 신선함도 문서마다다(2026-11-20 — 「프로젝트 구성 반영」 · 「다시 문서 검토」 를 원본 문서에도 놓는다: spec_워크플로우 ② §18-2 「원본 문서에 놓는 줄」 · 전에는 목적 문서 하나)."""
    out = []
    for f in u[key]:
        if f in ("heads", "checked", "fit", "fresh"):
            out += [f"{f}@{r}" for r in (s["on"] if u["place"] == "doc" else ROLES)]
        else:
            out.append(f)
    return out


def check(shape, source, target, raw_flow):
    """조립 검사(② §18-3 을 § 18-12 ④ 로 고친 것 — 규칙은 서버 한 곳) → {errors[], warns[], flow(정리한 꼴 | None), std(표준이면 그 배정 | None)}. 글은 화면에 그대로.
    거절: 꼴 · 모르는 줄 · 그 틀에 없는 줄 · 놓을 수 없는 문서 · 같은 대상에 같은 줄 두 번 · 먼저 있어야 할 것을 주는 줄보다 앞 · 효과의 차례(구조 반영은 연결 · 넣기 · 정리보다 앞 · 작성요령 삭제는 내용 반영 뒤) ·
    원본 문서를 쓰는 줄이 없음 · 서버가 아직 못 돌리는 줄 · 아직 못 여는 틀. 경고(저장은 됨): 먼저 있어야 할 것을 주는 줄이 정의에 없음 · 구조를 바꾼 뒤 다시 검토가 없음 · 유료 줄 · 문서를 바꾸는 줄."""
    from app import workflow_units as WU
    errors, warns = [], []
    try:
        flow = _flow_in(raw_flow)
    except ValueError as e:
        return {"errors": [str(e)], "warns": [], "flow": None, "std": None}
    sh = next((x for x in SHAPES if x["id"] == shape), None)
    if sh is None:
        errors.append("모르는 틀입니다")
    elif sh["soon"]:
        errors.append(sh["soon"])
    pairs = pairs_of(shape)   # 그 틀의 문서 종류 짝(이관형 = 사업계획서 → 연차보고서 · 취합형 = 기관 문서 → 사업계획서)
    if (source, target) not in pairs:
        errors.append("지금 조립할 수 있는 문서 쌍은 " + " · ".join(f"{kind_name(a)} → {kind_name(b)}" for a, b in pairs) + " 입니다")
    fam = sh["family"] if sh and not sh["soon"] else "relay"   # 아직 못 여는 틀은 그 거절 하나로(줄마다 겹쳐 적지 않는다)
    names, docs = unit_names(fam), {"source": "원본 문서", "target": "목적 문서"}
    nm = lambda s: s.get("name") or names.get(s["unit"], s["unit"])  # noqa: E731
    q = lambda s, a, b: f"「{nm(s)}」 {_jo(nm(s), a, b)}"  # noqa: E731 — 「이름」 + 조사(받침으로)
    seq, seen = [], set()
    for gi, g in enumerate(flow):
        if not g["steps"]:
            errors.append(f"「{g['name']}」 에 줄이 없습니다 — 줄을 넣거나 묶음을 빼세요")
        for s in g["steps"]:
            # 「사람이 하는 일」(hand)은 어느 틀에서나 같은 단위다(취합 등록부의 「기관에 배포 · 회수」 도 key 가 hand 지만 그것은 줄로 놓지 않는다) · 취합형에 놓을 수 있는 줄은 GATHER_UNITS 뿐(같이 쓰는 「다시 문서 검토」 · 「작성요령 삭제」 는 이관형의 것)
            u = None if s["unit"] in AUTO_UNITS else WU.COMMON["hand"] if s["unit"] == "hand" else WU.unit(s["unit"], fam)
            if u is not None and fam == "gather" and s["unit"] != "hand" and s["unit"] not in GATHER_UNITS:
                u = None
            if u is None:
                errors.append(f"놓을 수 없는 줄입니다 — {names.get(s['unit'], s['unit'])}" + (" (맨 앞 묶음에 저절로 섭니다)" if s["unit"] in AUTO_UNITS else ""))
                continue
            if u["place"] == "doc":
                roles = WU.roles_in(u, fam)   # 그 틀에서 놓을 수 있는 문서 — 구조 · 정리 줄을 원본 문서에 놓는 것은 이관형뿐(취합의 원본 = 기관 문서는 바뀌지 않는다)
                bad = [r for r in s["on"] if r not in roles]
                if not s["on"]:
                    errors.append(f"{q(s, '을', '를')} 할 문서를 고르세요")
                elif bad:
                    errors.append(f"{q(s, '은', '는')} {' · '.join(docs[r] for r in roles)}에만 놓을 수 있습니다")
            else:
                s["on"] = list(ROLES) if u["place"] == "pair" else []
            if u["kind"] == "hand":
                if not u["server"]:
                    errors.append(f"「{nm(s)}」 — 사람이 하는 일은 아직 놓을 수 없습니다(실행기가 그 줄에서 멈추는 길을 만드는 중)")
            elif not u["server"]:
                errors.append(f"{q(s, '은', '는')} 아직 서버가 돌리지 못하는 줄입니다")
            if u["kind"] != "hand":
                for tgt in (s["on"] if u["place"] == "doc" else [u["place"]]):
                    if (s["unit"], tgt) in seen:
                        errors.append(f"{q(s, '을', '를')} 같은 문서에 두 번 놓았습니다" if u["place"] == "doc" else f"{q(s, '을', '를')} 두 번 놓았습니다")
                    seen.add((s["unit"], tgt))
            seq.append((gi, s, u))
    if fam == "gather":   # 취합형 — 줄의 차례 · 기관 문서마다 도는 덩이(② §18-12 ⑥): 아래의 사실 걷기 · 효과의 차례는 이관형의 것이라 타지 않는다
        _gather_rules(seq, names, errors, warns)
        paid = [nm(s) for _, s, u in seq if u["paid"]]
        if paid:
            warns.append("유료 LLM 을 부르는 줄: " + " · ".join(dict.fromkeys(paid)))
        change = [nm(s) for _, s, u in seq if u["change"] == "doc" and u["kind"] == "auto"]
        if change:
            warns.append("목적 문서(취합본)를 바꾸는 줄: " + " · ".join(dict.fromkeys(change)) + " — 원본 문서(기관 문서)는 바뀌지 않습니다")
        _ids(flow, None)
        return {"errors": list(dict.fromkeys(errors)), "warns": list(dict.fromkeys(warns)), "flow": flow, "std": None}   # 취합형은 늘 줄 목록(v2)으로 저장한다(표준 차례의 옛 꼴은 이관형의 것)
    # 먼저 있어야 할 것 — 차례대로 걸으며 생긴 사실(무르는 줄은 지운다)과 견준다 · 처음부터 참 = 문서 칸 · 구조를 아직 안 바꿈(fresh)
    have, ever, gives_at = {"slots", "fresh@source", "fresh@target"}, set(), {}   # ever = 앞 줄이 한 번이라도 준 사실(무른 뒤에도 — 실행기가 그것을 주는 앞 줄로 한 번 새로 얻는다: ② §18-4 「무르기」)
    for i, (_, s, u) in enumerate(seq):
        for f in _facts_of(s, u, "gives"):
            gives_at.setdefault(f, []).append(i)
    unit_at = lambda key: [i for i, (_, s, _u) in enumerate(seq) if s["unit"] == key]  # noqa: E731
    title = {f: "「" + names.get(k, k) + "」" for f, k in (("heads@source", "heads"), ("heads@target", "heads"), ("config", "config"), ("fit@target", "division"), ("fresh@target", "reheads"),
                                                            ("fit@source", "division"), ("fresh@source", "reheads"), ("links", "link"), ("plan", "plan"), ("filled", "apply"))}
    for i, (_, s, u) in enumerate(seq):
        for f in _facts_of(s, u, "needs"):
            if f in have or (f in ever and not f.startswith("fresh@")):
                continue
            later = [j for j in gives_at.get(f, ()) if j > i]
            if later and f not in ever:
                errors.append(f"{q(s, '은', '는')} {title.get(f, f)} 뒤에 와야 합니다")
            elif f in ("heads@source", "heads@target"):
                warns.append(f"이 워크플로우에는 {docs[f.split('@')[1]]}의 「헤딩 · 표 분석」 이 「{nm(s)}」 앞에 없습니다 — 분석이 없으면 실행이 스크립트로 먼저 분석합니다(LLM 검증·보완은 하지 않음)")
            elif f == "fresh@target":
                warns.append(f"구조를 바꾼 뒤 「다시 문서 검토」 가 「{nm(s)}」 앞에 없습니다 — 그 줄이 분석을 쓸 때 스크립트로 다시 분석합니다(LLM 검증·보완은 하지 않음)")
            elif f == "fresh@source":
                warns.append(f"원본 문서의 구조를 바꾼 뒤 원본 문서의 「다시 문서 검토」 가 「{nm(s)}」 앞에 없습니다 — 그 줄이 분석을 쓸 때 스크립트로 다시 분석합니다(LLM 검증·보완은 하지 않음)")
            elif f == "config":
                warns.append(f"이 워크플로우에는 「프로젝트 구성 확정」 이 없습니다 — 「{nm(s)}」 은 시작할 때 이미 확정돼 있어야 하고, 아니면 그 줄에서 멈춥니다")
            elif f == "filled":
                pass   # 「문서 정리」 만 고른 정의는 된다(내용 넣기 줄이 없으면 반영을 기다리지 않는다 — ② §18-12 ②)
            else:
                errors.append(f"「{nm(s)}」 에는 {title.get(f, f)}{_jo(title.get(f, f).strip('「」'), '이', '가')} 앞에 있어야 합니다")
        have.update(_facts_of(s, u, "gives"))
        ever.update(_facts_of(s, u, "gives"))
        have.difference_update(_facts_of(s, u, "spoils"))
    # 효과의 차례(② §18-12 ④) — 같은 목적 문서: 구조 바꿈 → 그 구조를 쓰는 분석 → 연결 · 계획 → 내용 반영 → 정리
    late = [i for i, (_, s, u) in enumerate(seq) if u["place"] == "pair" or s["unit"] == "guide"]
    for i in unit_at("division"):
        if any(j < i for j in late):
            errors.append("「프로젝트 구성 반영」 은 「자리 연결」 · 「내용 반영」 · 「작성요령 삭제」 보다 앞에 와야 합니다 — 뒤에 두면 방금 넣은 내용의 행을 줄일 수 있습니다")
    for i in unit_at("guide"):
        if any(j > i for j in unit_at("apply")):
            errors.append("「작성요령 삭제」 는 「내용 반영」 뒤에 와야 합니다")
    for i in unit_at("reheadsLlm"):
        before = [j for j in unit_at("reheads") if j < i]
        if not before:
            errors.append("「다시 문서 검토(LLM)」 은 「다시 문서 검토」 뒤에 와야 합니다")   # 「(LLM)」 — 읽는 소리 「엘엘엠」 의 받침 ㅁ
            continue
        for r in seq[i][1]["on"]:   # 문서마다 — 그 문서의 「다시 문서 검토」 가 앞에 있어야 한다(다른 문서의 것만 있으면 그 문서의 LLM 줄은 끝내 남는다)
            if not any(r in seq[j][1]["on"] for j in before):
                errors.append(f"{docs[r]}의 「다시 문서 검토(LLM)」 은 그 문서의 「다시 문서 검토」 뒤에 와야 합니다")
    # 문서끼리의 차례는 자유다(2026-11-20 사용자 「프로젝트 구성을 완료하고 문서 검토하고 다른문서 프로젝트 구성할 수도 있잖아」 — 「원본의 구성 반영이 목적의 것보다 앞」 을 거절하던 것을 뺌:
    # 원본 문서도 구조 반영하는 정의에서는 목적 문서가 원본의 제 값에 맞춘다 — workflow_units.basis_of: 차례와 무관하게 두 문서가 같은 확정 값으로)
    on_at = lambda key, role: [i for i in unit_at(key) if role in seq[i][1]["on"]]  # noqa: E731
    if "config" in [s["unit"] for _, s, _u in seq] and any(j > min(unit_at("config")) for j in unit_at("configLoad")):
        warns.append("「구성 불러오기」 는 「프로젝트 구성 확정」 앞에 두세요 — 뒤에 두면 불러온 값이 이번 확정에 들지 않습니다")
    if "link" in [s["unit"] for _, s, _u in seq] and not on_at("division", "target"):
        from app import workflow
        warns.append(f"이 워크플로우에는 「프로젝트 구성 반영」 이 없습니다 — {workflow.FILL_NO_FIT}" if not unit_at("division")
                     else f"이 워크플로우는 「프로젝트 구성 반영」 을 원본 문서에만 합니다 — {workflow.FILL_NO_FIT}")
    if seq and not any("source" in s["on"] or s["unit"] == "config" for _, s, u in seq):
        errors.append(NO_SOURCE_FLOW)
    paid = [nm(s) for _, s, u in seq if u["paid"]]
    if paid:
        warns.append("유료 LLM 을 부르는 줄: " + " · ".join(dict.fromkeys(paid)))
    for role in ("target", "source"):   # 문서를 바꾸는 줄 — 문서마다 따로 알린다(원본 → 목적 줄은 목적 문서만 바꾼다)
        change = [nm(s) for _, s, u in seq if u["change"] == "doc" and (role in s["on"] if u["place"] == "doc" else role == "target")]
        if change:
            warns.append(f"{docs[role]}를 바꾸는 줄: " + " · ".join(dict.fromkeys(change)))
    errors = list(dict.fromkeys(errors))
    std = standard(source, target, flow) if not errors else None
    _ids(flow, std)
    return {"errors": errors, "warns": list(dict.fromkeys(warns)), "flow": flow, "std": std}


def _gather_rules(seq, names, errors, warns):
    """취합형의 조립 검사(② §18-12 ⑥ · §18-13 갈래 「라」 ⓶) — seq = [(묶음 자리, 줄, 단위)]. 거절: 차례가 거꾸로(프로젝트 구성 확정 → 구성 반영 → 배포 기준본 → 기관 문서마다: 반영할 기관 → 헤딩 · 표 분석 →
    자리 연결 → LLM 검토 → 넣기 계획 → 내용 반영 → 끌어 넣기) · 기관 문서마다 도는 줄이 한 묶음에 잇달아 있지 않음(원본 문서 하나를 끝내는 범위를 쪼갠 배치) · 앞 줄 없이 놓은 줄(반영 ← 계획 ← 자리 연결).
    경고: 그 줄이 기대는 것을 만드는 줄이 정의에 없음(시작할 때 이미 되어 있어야 하고, 아니면 그 줄에서 멈춘다). 「사람이 하는 일」 은 어디에나 놓는다(기관 문서마다의 덩이 안만 빼고)."""
    order = {k: i for i, k in enumerate(GATHER_UNITS)}
    nm = lambda k: "「" + names.get(k, k) + "」"  # noqa: E731
    last = None
    for _gi, s, u in seq:
        if s["unit"] == "hand":
            continue
        if last is not None and order[s["unit"]] < order[last]:
            errors.append(f"{nm(s['unit'])} {_jo(names.get(s['unit'], ''), '은', '는')} {nm(last)} 앞에 와야 합니다")
        else:
            last = s["unit"]
    each = [i for i, (_gi, _s, u) in enumerate(seq) if u.get("each")]
    if each and (each != list(range(each[0], each[-1] + 1)) or len({seq[i][0] for i in each}) > 1):
        errors.append(GATHER_EACH)
    has = {s["unit"] for _gi, s, _u in seq}
    for a, b in (("apply", "plan"), ("plan", "link"), ("llm", "link")):
        if a in has and b not in has:
            errors.append(f"{nm(a)} 에는 {nm(b)}{_jo(names.get(b, ''), '이', '가')} 앞에 있어야 합니다")
    if "division" in has and "config" not in has:
        warns.append(f"이 워크플로우에는 {nm('config')} 이 없습니다 — {nm('division')} 은 시작할 때 이미 확정돼 있어야 하고, 아니면 그 줄에서 멈춥니다")
    if "frame" in has and "division" not in has:
        warns.append(f"이 워크플로우에는 {nm('division')} 이 없습니다 — {nm('frame')} 는 취합본의 구조가 이미 값에 맞춰져(반영돼) 있어야 하고, 아니면 그 줄에서 멈춥니다")
    if "link" in has and "frame" not in has:
        warns.append(f"이 워크플로우에는 {nm('frame')} 가 없습니다 — 배포 기준본이 이미 있어야 하고, 없으면 {nm('link')} 에서 멈춥니다")
    if "link" in has and "part" not in has:
        warns.append(f"이 워크플로우에는 {nm('part')} 줄이 없습니다 — 반영할 기관이 이미 정해진 기관 문서만 넣습니다")


def _ids(flow, std):
    """묶음 id 를 정한다 — 표준이면 그 배정의 묶음 id(review · frame · map · clean — 화면 · 서버가 쓰는 키), 아니면 g1 …(지금 초기화 …/merge-links/reset 의 frame · map 과 겹치지 않게 — ② §18-12 ⑤)."""
    if std is not None:
        mids = [m for m in STAGES if m in union(std)]
        for g, m in zip(flow, mids):
            g["id"] = STAGE_GROUP[m]
    else:
        for i, g in enumerate(flow):
            g["id"] = f"g{i + 1}"


def _jo(word, a, b):
    """이름 뒤 조사 — 끝 글자에 받침이 있으면 a, 없으면 b(한글 · 숫자로 가린다 · 「…(LLM)」 처럼 괄호로 끝나면 괄호 안 끝 글자 — 화면 task_catalog.js taskJosa 와 같은 셈)."""
    w = str(word or "").rstrip(")」 ")
    c = w[-1:]
    if "가" <= c <= "힣":
        return a if (ord(c) - 0xAC00) % 28 else b
    if c.isdigit():
        return a if c in "013678" else b
    return a if c.upper() in "LMN" else b


def _same(a, b):
    """두 배정이 실제로 같은가(원본 · 목적 · llm). 이 모듈의 all() 이 내장 all 을 가린다 — 목록끼리 견준다."""
    return [list(a[k]) for k in (*ROLES, "llm")] == [list(b[k]) for k in (*ROLES, "llm")]


def _assign_copy(a):
    return {k: list(a[k]) for k in (*ROLES, "llm")}


def sig(t):
    """정의의 단계 지문 — 정리한 배정(원본 · 목적 · llm)과 합집합 stages 의 sha1 앞 10자. 단계가 바뀔 때만 바뀐다(이름 · 설명 · 전제를 고쳐도 그대로 —
    화면이 연 뒤 정의의 단계가 바뀌었는지 견준다: GET /api/tasks 의 sig).
    줄 목록 정의(v2 — 아래 절)는 틀 · 문서 종류 · 묶음 id · 경계 · 줄 차례 · 줄마다의 단위 · 하는 문서(차례 없는 모음) · 사람이 하는 일의 줄 id 의 지문(묶음 이름 · 사람이 하는 일의 글은 넣지 않는다 — ② §18-12 ⑤)."""
    if t.get("flow") is not None:
        core = [t.get("shape") or "relay", t["source"], t["target"], [[g["id"], [[s["unit"], sorted(s["on"]), s.get("id") or ""] for s in g["steps"]]] for g in t["flow"]]]
        return hashlib.sha1(json.dumps(core, separators=(",", ":")).encode("utf-8")).hexdigest()[:10]
    a = t["assign"]
    return hashlib.sha1(json.dumps([a["source"], a["target"], a["llm"], t["stages"]], separators=(",", ":")).encode("utf-8")).hexdigest()[:10]


def _eun(word):
    """「…」 뒤 조사 「은」 · 「는」 — 끝 글자에 받침이 있으면 「은」(한글 · 숫자로 가린다 — 그 밖의 글자는 「는」)."""
    c = (word or "")[-1:]
    if "가" <= c <= "힣":
        return "은" if (ord(c) - 0xAC00) % 28 else "는"
    return "은" if c and c in "013678" else "는"


def _copy(t):
    """저장된 한 줄의 사본(목록까지 — 돌려받은 값을 고쳐도 저장소 · 캐시는 그대로) · 저장하는 키만(_FIELDS · 줄 목록 정의는 + shape · v · flow — assign 은 None · stages 는 빈 목록)."""
    if t.get("flow") is not None:
        return {**{k: t[k] for k in _FIELDS if k not in ("assign", "stages")}, "assign": None, "stages": [], "shape": t["shape"], "v": 2, "flow": _flow_copy(t["flow"])}
    return {**{k: t[k] for k in _FIELDS}, "stages": list(t["stages"]), "assign": _assign_copy(t["assign"])}


def _flow_text(flow):
    """줄 목록의 글(묶음 이름 · 사람이 하는 일의 이름 · 글 · 도구) — 지문에 안 드는 것이 바뀌었나 견줄 때."""
    return None if flow is None else [[g["name"], [[s.get("name", ""), s.get("note", ""), s.get("tool", "")] for s in g["steps"]]] for g in flow]


def _flow_copy(flow):
    return [{**g, "steps": [{**s, "on": list(s["on"])} for s in g["steps"]]} for g in flow]


def _clean_one(t):
    """저장된 한 줄 → 정리한 사전 | None(꼴이 틀림 — 목록에 안 보이고 줄은 원래 모습 그대로 남는다: _parse).
    새 꼴(assign 이 사전) = 역할마다 고를 수 있는 단계만 · llm 이 없으면(2026-11-19 첫 판이 적은 줄) 규칙(llm_rule) / 옛 줄(assign 없이 stages 목록만) = from_stages.
    새 꼴인데 고른 것이 없으면 stages 로 되살리지 않는다(지우려던 배정이 살아난다 — astra 검토)."""
    if not isinstance(t, dict) or not isinstance(t.get("key"), str) or not KEY.fullmatch(t["key"]) or not isinstance(t.get("name"), str) or not t["name"].strip():
        return None
    if (t.get("source"), t.get("target")) not in pairs_of(t.get("shape", "relay") if (t.get("v") == 2 or "flow" in t) else "relay"):   # 문서 종류 짝은 틀마다(취합형 = 기관 문서 → 사업계획서)
        return None
    if t.get("v") == 2 or "flow" in t:   # 줄 목록 정의(v2 — ② §18-5): assign · stages 없이 flow 만 — 옛 서버는 assign 이 없고 stages 가 목록이 아니라 「꼴이 틀림」 으로 숨기고 그대로 둔다
        if "assign" in t or "stages" in t or t.get("shape", "relay") not in [s["id"] for s in SHAPES]:
            return None
        try:
            flow = _flow_in(t.get("flow"))
        except ValueError:
            return None
        return {"key": t["key"], "name": t["name"].strip()[:NAME_MAX], "desc": str(t.get("desc") or "")[:DESC_MAX], "source": t["source"], "target": t["target"], "assign": None, "stages": [],
                "shape": t.get("shape", "relay"), "v": 2, "flow": flow, "premise": str(t.get("premise") or "")[:PREMISE_MAX],
                "at": t.get("at") if isinstance(t.get("at"), (int, float)) and not isinstance(t.get("at"), bool) else 0}
    a = t.get("assign")
    if isinstance(a, dict):
        core = {r: [s for s in ROLE_STAGES[r] if isinstance(a.get(r), list) and s in a[r]] for r in ROLES}   # 역할마다 고를 수 있는 단계만(일반 차례)
        assign = {**core, "llm": _llm_of(a["llm"], core) if isinstance(a.get("llm"), list) else llm_rule(core)}
    elif "assign" in t or not isinstance(t.get("stages"), list):   # assign 이 사전이 아님 · stages 가 목록이 아닌 옛 줄 — 꼴이 틀림(지우지 않고 그대로 둔다)
        return None
    else:
        assign = from_stages(t["stages"])
    stages = union(assign)
    if not stages:
        return None
    return {"key": t["key"], "name": t["name"].strip()[:NAME_MAX], "desc": str(t.get("desc") or "")[:DESC_MAX], "source": t["source"], "target": t["target"], "assign": assign, "stages": stages,
            "premise": str(t.get("premise") or "")[:PREMISE_MAX], "at": t.get("at") if isinstance(t.get("at"), (int, float)) and not isinstance(t.get("at"), bool) else 0}


def _broken():
    return {"version": 0, "rows": [], "tasks": [], "at": [], "extra": {}, "broken": True}


def _parse(obj):
    """파일의 JSON(또는 메모리의 같은 꼴) → {version, rows[줄 — 읽은 그대로], tasks[보이는 줄 — 정리한 것 · 만든 차례], at[그 줄의 rows 자리], extra{머리의 그 밖의 키}, broken}.
    보이는 줄 = 꼴이 맞고(_clean_one) 키가 앞에 안 나왔고 TASKS_MAX 안의 것. 머리가 사전이 아니거나 tasks 가 목록이 아니면 못 읽은 것(broken — 쓰지 않는다)."""
    if not isinstance(obj, dict) or not isinstance(obj.get("tasks", []), list):
        return _broken()
    rows, tasks, at, seen = list(obj.get("tasks", [])), [], [], set()
    for i, row in enumerate(rows):
        c = _clean_one(row)
        if c is None or c["key"] in seen or len(tasks) >= TASKS_MAX:
            continue
        seen.add(c["key"])
        tasks.append(c)
        at.append(i)
    v = obj.get("version")
    return {"version": v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0, "rows": rows, "tasks": tasks, "at": at,
            "extra": {k: x for k, x in obj.items() if k not in ("version", "tasks")}, "broken": False}


def _load():
    p = path()
    if p is None:
        return _parse(_MEMORY)
    try:
        st = p.stat()
        m = (st.st_mtime_ns, st.st_size)   # 크기도 — 같은 시계 눈금 안에 다시 쓴 파일을 옛 읽기로 보지 않게
    except FileNotFoundError:
        return _parse({})
    except OSError:   # 있는지도 모름 — 이 호출만 못 읽은 것으로(덮어쓰지 않는다 · 남기지 않는다)
        return _broken()
    if _CACHE["path"] == str(p) and _CACHE["mtime"] == m and _CACHE["data"] is not None:
        return _CACHE["data"]
    try:
        raw = p.read_bytes()
    except FileNotFoundError:   # 본 사이에 없어짐
        return _parse({})
    except OSError:   # 읽기 오류(다른 프로세스가 바꿔 넣는 중 · 권한) — 이 호출만 못 읽은 것으로(쓰지 않는다). 남기지 않는다: 파일이 그대로여도 다음 호출이 다시 읽는다
        return _broken()
    try:
        data = _parse(json.loads(raw.decode("utf-8")))
    except ValueError:   # JSON 이 깨짐 · 글자 꼴이 틀림 — 읽어서 해석한 결과라 남긴다(파일이 바뀌면 다시 읽는다) · 빈 목록으로 보이되 쓰지 않는다(broken)
        data = _broken()
    _CACHE.update(path=str(p), mtime=m, data=data)
    return data


def broken():
    """저장 파일을 못 읽었나(있는데 JSON · 꼴이 틀림) — 그동안 목록은 비어 보이고 쓰기는 거절한다(API 409 · 화면은 폼 위에 까닭)."""
    with _LOCK:
        return _load()["broken"]


def _writable(data):
    if data["broken"]:
        raise Refused(BROKEN.format(name=(path() or Path("tasks.json")).name))


def writable():
    """쓸 수 있나 — 못 읽은 저장 파일이면 Refused(API 409). 지우기처럼 다른 검사(404 · 쓰는 중)보다 먼저 볼 때."""
    with _LOCK:
        _writable(_load())


def _save(data, rows):
    """줄들을 쓴다(version + 1 · 머리의 다른 키는 그대로) — data = 이 쓰기 앞에 읽은 _load() 의 값. 못 읽은 파일이면 쓰지 않는다(Refused)."""
    _writable(data)
    data = {**data["extra"], "version": data["version"] + 1, "tasks": list(rows)}
    p = path()
    if p is None:
        _MEMORY.clear()
        _MEMORY.update(data)
        return data
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _CACHE.update(path=None, mtime=None, data=None)
    return data


def all():   # noqa: A001 — 모듈 안의 이름(custom_tasks.all())
    """조립한 TASK 들(만든 차례) — 사본(assign · stages 목록까지)."""
    with _LOCK:
        return [_copy(t) for t in _load()["tasks"]]


def get(key):
    """키 → 조립한 TASK | None."""
    if not isinstance(key, str) or not KEY.fullmatch(key):
        return None
    return next((t for t in all() if t["key"] == key), None)


def is_key(job):
    """그 할 일 키가 조립한 TASK 인가(저장소에 있는 것만)."""
    return get(job) is not None


def source_file(job):
    """그 TASK 의 원본 문서 종류 — 조립한 TASK 는 제 것, 그 밖(붙박이 이관)은 사업계획서."""
    t = get(job)
    return t["source"] if t else "plan"


def target_file(job):
    """조립한 TASK 의 목적 문서 종류 | None(조립한 TASK 가 아님 — 붙박이는 works.TARGET_FILE)."""
    t = get(job)
    return t["target"] if t else None


def is_gather(job):
    """그 키가 취합형으로 조립한 워크플로우인가(원본 문서 여럿 → 목적 문서 하나 — 틀 shape gather). 붙박이 「사업계획서 취합」 은 아니다(그 키는 부르는 쪽이 따로 안다 —
    `job == "plan_merge" or custom_tasks.is_gather(job)`: 취합인지를 붙박이 키 글자만으로 가르지 않게 — spec_워크플로우 ② §18-13 갈래 「라」 ⓷)."""
    t = get(job)
    return bool(t) and t.get("shape") == "gather"


def base_of(t):
    """조립한 정의가 전제를 비웠을 때 물려받는 붙박이 워크플로우의 키 — 취합형 = 사업계획서 취합 · 그 밖(이관형) = BASE."""
    return "plan_merge" if (t or {}).get("shape") == "gather" else BASE


def _llm_kept(core, old):
    """고치는 배정의 llm — 역할마다 따진다: 규칙(llm_rule)이 그 역할에서 보는 입력(원본 = 「문서 검토」 를 골랐나 · 목적 = 「문서 검토」 와 「구성 맞추기」 를 골랐나)이
    저장된 배정(old)과 같은 역할은 저장된 결정(그 역할이 llm 에 있었나)을 지키고, 입력이 바뀐 역할만 규칙으로 다시 센다. 결과는 늘 llm_rule(core) 의 부분 —
    옛 줄 [문서 검토 · 내용 넣기](llm = 원본만)에 목적의 「문서 정리」 를 더해도 목적 문서의 1단계 LLM(유료)이 더해지지 않는다."""
    seen = lambda a, r: ("stage_review" in a[r], r == "target" and "stage_fit" in a[r])  # noqa: E731 — llm_rule 이 그 역할에서 보는 것
    allowed = llm_rule(core)
    return [r for r in ROLES if r in allowed and (r in old["llm"] if seen(core, r) == seen(old, r) else True)]


def _assign_in(body, old):
    """보낸 값의 단계 → assign {source, target, llm}(역할마다 일반 차례). assign 은 한 값이다 — 보낸 assign 에 없는 역할은 고른 것이 없는 것으로 본다.
    - `assign` 이 먼저: 고칠 때(old 있음)는 llm 을 역할마다 따진다(_llm_kept — 입력이 그대로인 역할은 저장된 결정 · 바뀐 역할만 규칙 · 보낸 llm 은 쓰지 않는다).
      새로 만들 때(old 없음)는 보낸 llm 을 받는다(규칙이 허락하는 것만 — 「복제」) · 안 보냈으면 규칙.
    - 없으면 옛 꼴 `stages`(옛 화면): 합집합이 저장된 것과 같으면 저장된 배정 그대로, 다르면(또는 새로 만들 때) 옛 줄 규칙(from_stages).
    - 둘 다 없으면 지금 값(이름 · 설명 · 전제만 고침)."""
    if "assign" in body:
        a = body["assign"]
        if not isinstance(a, dict) or any(not isinstance(a.get(r, []), list) or any(not isinstance(s, str) or s not in STAGES for s in a.get(r, [])) for r in ROLES):
            raise ValueError("단계를 고르세요")
        if any(s not in ROLE_STAGES["source"] for s in a.get("source", [])):
            raise ValueError(SOURCE_ONLY)
        llm = a.get("llm")
        if llm is not None and (not isinstance(llm, list) or any(not isinstance(r, str) or r not in ROLES for r in llm)):
            raise ValueError(BAD_LLM)
        core = {r: [s for s in ROLE_STAGES[r] if s in a.get(r, [])] for r in ROLES}
        if old is not None:
            return {**core, "llm": _llm_kept(core, old["assign"])}   # 원본 · 목적이 그대로면 저장된 llm 그대로(옛 줄의 「원본만」 도) — 바뀐 역할만 다시 센다
        return {**core, "llm": _llm_of(llm, core) if llm is not None else llm_rule(core)}
    if "stages" in body or old is None:
        picked = body.get("stages")
        if not isinstance(picked, list) or any(not isinstance(s, str) or s not in STAGES for s in picked):
            raise ValueError("단계를 고르세요")
        got = from_stages(picked)
        if old is not None and union(got) == union(old["assign"]):   # 옛 화면이 이름만 고쳐 같은 합집합을 보냄 — 문서마다 고른 배정을 펼치지 않는다
            return _assign_copy(old["assign"])
        return got
    return _assign_copy(old["assign"])


def _checked(body, taken, old=None):
    """화면이 보낸 값 → 저장할 값(틀리면 ValueError — 화면에 그대로 보이는 글). taken = 쓸 수 없는 이름들(붙박이 TASK · 다른 조립한 TASK).
    단계는 `assign`(문서 역할마다 — spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) 또는 옛 꼴 `stages`(assign 이 없을 때만)로 받는다 — 저장하는 `stages` 는 늘 두 역할의 합집합.
    배정을 새로 정할 때만(만들 때 · 배정이 바뀔 때) 「하나 이상」 · 「원본 문서를 쓰는 단계」 를 따진다 — 배정이 그대로인 고치기(이름만)는 옛 줄도 받는다."""
    h = _head(body, taken, old)
    name, desc, source, target, premise = h["name"], h["desc"], h["source"], h["target"], h["premise"]
    if old is not None and old.get("flow") is not None and ("assign" in body or "stages" in body):
        raise Refused(FLOW_LOCKED)   # 옛 화면(assign 꼴)이 줄 목록 정의를 고치려 함 — 표준 차례로 덮지 않는다(② §18-12 ⑤)
    assign = _assign_in(body, old)
    stages = union(assign)   # 고른 것만 — 차례는 일반 단계의 차례
    if old is None or not _same(assign, old["assign"]):   # 배정을 새로 정함
        if not stages:
            raise ValueError("단계를 하나 이상 고르세요")
        if not assign["source"] and not any(s in assign["target"] for s in SOURCE_USE):
            raise ValueError(NO_SOURCE)
    return {"name": name, "desc": desc, "source": source, "target": target, "assign": assign, "stages": stages, "premise": premise}


def _head(body, taken, old=None, shape="relay"):
    """보낸 값의 이름 · 설명 · 문서 쌍 · 전제 → 정리한 값(틀리면 ValueError — 화면에 그대로). 옛 꼴 · 줄 목록이 같이 쓴다. shape = 틀(문서 종류 짝이 틀마다 다르다 — pairs_of)."""
    if not isinstance(body, dict):
        raise ValueError("값의 꼴이 틀립니다")
    name = " ".join(str(body.get("name") if "name" in body else (old or {}).get("name") or "").split())
    if not name:
        raise ValueError("워크플로우 이름을 적으세요")
    if len(name) > NAME_MAX:
        raise ValueError(f"워크플로우 이름은 {NAME_MAX}자까지입니다")
    if name in taken:
        raise ValueError(f"「{name}」{_eun(name)} 이미 있는 워크플로우 이름입니다")
    desc = " ".join(str(body.get("desc") if "desc" in body else (old or {}).get("desc") or "").split())[:DESC_MAX]
    pairs = pairs_of(shape)
    source = body.get("source") if "source" in body else (old or {}).get("source") or pairs[0][0]
    target = body.get("target") if "target" in body else (old or {}).get("target") or pairs[0][1]
    if (source, target) not in pairs:
        raise ValueError("지금 조립할 수 있는 문서 쌍은 " + " · ".join(f"{kind_name(a)} → {kind_name(b)}" for a, b in pairs) + " 입니다")
    premise = str(body.get("premise") if "premise" in body else (old or {}).get("premise") or "").strip()
    if len(premise) > PREMISE_MAX:
        raise ValueError(f"전제 글은 {PREMISE_MAX}자까지입니다")
    return {"name": name, "desc": desc, "source": source, "target": target, "premise": premise}


def _checked_flow(body, taken, old=None):
    """줄 목록(flow)으로 보낸 정의 → 저장할 값(틀리면 ValueError — 검사의 첫 거절 글). 이름 · 설명 · 전제는 옛 꼴과 같은 검사(_checked).
    표준 차례면 옛 꼴(assign · stages — 한 표현만: ② §18-12 ⑤), 아니면 v2(shape · v · flow)."""
    shape = body.get("shape") if "shape" in body else (old or {}).get("shape") or "relay"
    base = _head(body, taken, old, shape)
    got = check(shape, base["source"], base["target"], body["flow"])
    if got["errors"]:
        raise ValueError(got["errors"][0])
    head = {k: base[k] for k in ("name", "desc", "source", "target", "premise")}
    if got["std"] is not None:
        return {**head, "assign": got["std"], "stages": union(got["std"])}
    return {**head, "shape": shape, "v": 2, "flow": got["flow"]}


def create(body, builtin_names=()):
    """새 조립한 TASK → 그 TASK. builtin_names = 붙박이 TASK 의 이름들(같은 이름을 못 쓰게). 못 읽은 저장 파일이면 Refused(쓰지 않음).
    단계는 줄 목록(flow — 정의 v2: 표준 차례면 옛 꼴로 저장) 또는 옛 꼴(assign · stages)로 받는다."""
    with _LOCK:
        data = _load()
        _writable(data)
        if len(data["tasks"]) >= TASKS_MAX:
            raise ValueError(f"조립한 워크플로우는 {TASKS_MAX}개까지입니다")
        taken = set(builtin_names) | {x["name"] for x in data["tasks"]}
        if isinstance(body, dict) and "flow" not in body and body.get("shape", "relay") != "relay":   # 옛 꼴(assign)은 이관의 표준 차례뿐 — 다른 틀을 조용히 이관으로 저장하지 않는다
            sh = next((x for x in SHAPES if x["id"] == body.get("shape")), None)
            raise ValueError(sh["soon"] if sh and sh["soon"] else "이 틀은 줄 목록으로 조립합니다 — 줄을 놓아 보내세요" if sh else "모르는 틀입니다")
        t = _checked_flow(body, taken) if "flow" in body else _checked(body, taken)
        keys = {r.get("key") for r in data["rows"] if isinstance(r, dict)}   # 안 보이는 줄(꼴이 틀림 · 겹침)의 키와도 겹치지 않게
        key = next(k for k in (f"u_{uuid.uuid4().hex[:8]}" for _ in range(100)) if k not in keys)
        t = {"key": key, **t, "at": time.time()}
        _save(data, data["rows"] + [t])
        return _copy(t)


def update(key, body, builtin_names=(), busy=0):
    """조립한 워크플로우 고치기(보낸 키만) → 그 정의(정리한 것) | None(없음). 문서 쌍은 고칠 수 없다(그 정의로 하던 작업의 문서 역할이 달라진다).
    busy = 그 키를 지금 워크플로우로 둔 작업 수(부르는 쪽이 센다 — app/custom_tasks_api.py in_use): 하나라도 있으면 실제 배정(원본 · 목적 · llm)을 바꾸지 않는다(Refused — 「복제」 로 새 정의를).
    **고친 칸만** 다시 쓴다 — 읽은 줄 그대로에 바뀐 이름 · 설명 · 전제만 얹고, 배정이 바뀌었을 때만 assign · stages 를 새로 쓴다(배정이 그대로면 저장된 assign · stages 를
    읽은 그대로 둔다 — 이 판이 모르는 단계 id · 옛 꼴 줄도). 바뀐 것이 없으면 쓰지 않는다. 그 밖의 줄은 읽은 그대로. 못 읽은 저장 파일이면 Refused."""
    with _LOCK:
        data = _load()
        _writable(data)
        i = next((n for n, x in enumerate(data["tasks"]) if x["key"] == key), None)
        if i is None:
            return None
        old = data["tasks"][i]
        if any(k in body and body[k] != old[k] for k in ("source", "target")):
            raise ValueError("문서 쌍은 고칠 수 없습니다 — 새 워크플로우로 만드세요")
        if "shape" in body and body["shape"] != (old.get("shape") or "relay"):
            raise ValueError("틀은 고칠 수 없습니다 — 새 워크플로우로 만드세요")
        taken = set(builtin_names) | {x["name"] for x in data["tasks"] if x["key"] != key}
        v2 = old.get("flow") is not None
        if v2 and ("assign" in body or "stages" in body):
            raise Refused(FLOW_LOCKED)
        if "flow" in body:
            new = _checked_flow(body, taken, old)
        elif v2:
            new = {**_head(body, taken, old, old["shape"]), "shape": old["shape"], "v": 2, "flow": old["flow"]}
        else:
            new = _checked(body, taken, old)
        moved = sig(new) != sig(old)   # 단계(배정 · 줄 목록)가 바뀜 — 이름 · 설명 · 전제 · 묶음 이름 · 사람이 하는 일의 글은 지문에 안 든다
        if busy and moved:
            raise Refused(IN_USE.format(n=busy))
        at, rows = data["at"][i], list(data["rows"])
        row = {**rows[at], **{k: new[k] for k in ("name", "desc", "premise") if k in body and new[k] != old[k]}}   # 읽은 줄 그대로 + 보내서 바뀐 칸
        if "flow" in body and new.get("flow") is not None and (moved or _flow_text(new["flow"]) != _flow_text(old.get("flow"))):   # v2 로(또는 v2 그대로 · 이름 · 글만 바뀜)
            for k in ("assign", "stages"):
                row.pop(k, None)
            row.update(shape=new["shape"], v=2, flow=new["flow"])
        elif moved:   # 옛 꼴로(표준 차례 — v2 였으면 줄 목록을 걷는다: 한 표현만)
            for k in ("shape", "v", "flow"):
                row.pop(k, None)
            row.update(assign=new["assign"], stages=new["stages"])
        if row != rows[at]:
            rows[at] = row
            _save(data, rows)
        return _copy(_clean_one(row))


def delete(key):
    """조립한 워크플로우 지우기 → 지웠나(보이는 줄이 없으면 False). 그 키의 줄을 **모두** 뺀다 — 보이는 줄 · 같은 키로 숨은 뒤 줄 · 꼴이 틀렸지만 key 가 같은 줄
    (보이던 줄만 빼면 숨은 줄이 그 키로 다른 내용이 되어 되살아난다). 그 키로 하던 작업이 있는지는 부르는 쪽이 본다(app/custom_tasks_api.py). 못 읽은 저장 파일이면 Refused."""
    with _LOCK:
        data = _load()
        _writable(data)
        if not any(x["key"] == key for x in data["tasks"]):
            return False
        _save(data, [r for r in data["rows"] if not (isinstance(r, dict) and r.get("key") == key)])
        return True
