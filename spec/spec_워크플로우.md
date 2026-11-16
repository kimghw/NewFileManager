# 워크플로우 — TASK 마다의 과정을 한 페이지에서

TASK(할 일) 하나가 **어떤 차례로 무엇을 하는지** — 프로젝트 구성 → 문서 프레임 → 헤딩·표 분석 → 자리 연결 → 넣기 … — 를 한 웹페이지에서 보는 화면과 그 등록부의 사양.
단계가 하는 일 자체(알고리즘·저장·API)는 그 기능의 사양서가 원본이다 — 여기는 **차례의 지도·화면**만 적고 기능 사양은 링크한다.

## ① 질의·요청 히스토리

- 2026-11-15 사용자: **"워크플로우는 항시 내용을 workflow.md 로 갖고 있고, 에이전트는 이걸 항시 가지고 있다가 참조하도록"** → ② §8. 저장소 루트 `workflow.md` = 등록부에서 만든 글(시험이 등록부와 같은지 본다).
  「에이전트」 = 같은 날 이어진 요청의 **작업 에이전트**(첫 화면 오른쪽 대화창 — 파일을 올리면 작업 절차를 확인하고 직접 진행: [spec_작업에이전트.md](spec_작업에이전트.md))로 읽었다 — 그 에이전트의 프롬프트에 이 글이 붙는다. 코드 에이전트도 TASK 의 과정을 다루기 전에 이 글을 본다([CLAUDE.md](../CLAUDE.md)).
- 2026-11-15 사용자: "에이전트도 워크플로우 처럼 페이지로 해줘" → 원본 [spec_에이전트.md](spec_에이전트.md) ② §5. 이 페이지 쪽 바뀐 것: 상단 바의 「에이전트 설정」 이 단추에서 링크(`a#agentsLink` — `/agents`)로 · 단계 세부의 에이전트 이름이 `/agents#<id>` 링크(② §3·§4).
- 2026-11-15 사용자(`http://localhost:8114/workflow#overview` 를 가리키며): **"cladue.md 에 업데이트 시 이 페이지를 항상 업데이트 해주라고 해"** → ② §5 첫 줄 · [CLAUDE.md](../CLAUDE.md) 「워크플로우 페이지」. 기능을 더하거나 고칠 때마다 이 페이지를 함께 갱신한다(전에는 TASK · 단계 · 모듈 · 에이전트가 바뀔 때만).
- 2026-11-15 사용자: **"여기 높이가 너무 높아 여백이 많다는 거지."**(문서 일반 편집 다이어그램 상단 첨부) → ② §7. 제목·설명·입출력 접기·단계 묶음 사이의 세로 여백을 줄이고 단계 묶음 카드를 한 줄로 배치한다.
- 2026-11-15 사용자: **"uiux 다이어 그램으로 순차적으로 확인할 수 있도록 작성해줘."**(기존 워크플로우 목록 화면 첨부) → ② §7. 기본 보기를 단계 다이어그램으로 바꾸고 이전·다음으로 하나씩 살펴본다.
- 2026-11-15 사용자: **"현재 전체적인 워크플로우를 웹페이지에서 볼 수 있으면 좋겠거든 예로 서식을 추출학 헤딩을 추출하고 매핑을 하고 등등 task 별로 이 과정을 알 수 있는 웹페이지가 있었으면 좋겠어."** → ② 전부.
  - 살펴본 것: TASK 의 차례는 [spec_작업.md](spec_작업.md) ② §16 의 표(개발할 때 영향 범위를 찾는 지도 — 글)와 코드(`app.js` `taskSteps`·`TASK_STAGES` · `gather.js` `gatherSteps` · 서식 관리자의 단계 줄)에 흩어져 있었다.
    화면의 「순서 안내」·단계 묶음은 **지금 연 작업 하나의 진행**만 보인다 — TASK 일곱 가지와 그 아래 공통 모듈(헤딩 추출 · 프로젝트 구성 · 서식 관리자 …)을 한눈에 보는 곳은 없었다.
  - 에이전트 판단(사용자 확인 전 — ④): ⓐ 「웹페이지」 = 앱 서버의 **따로 선 페이지** `/workflow`(새 탭 — 문서 옆 열이 아니다: 문서와 무관한 지도이고 넓은 폭이 필요하다) ·
    ⓑ 과정의 낱 = **단계 묶음 › 단계** — 단계마다 「누가 하나(스크립트 · LLM · 사람)」 · 「문서가 바뀌나」 · 하는 일 한 줄, 펴면 모듈 · 에이전트(작업 번호) · 사양 자리 ·
    ⓒ **지도(읽기)** 다 — 지금 작업이 어디까지 갔는지는 보이지 않는다(그것은 작업 내용의 순서 안내 몫) · ⓓ 여러 TASK 가 같이 쓰는 것(헤딩 추출 · 프로젝트 구성 · 서식 관리자 · 에이전트 보기 · 표 도구 …)은 **공통 모듈**로 따로 적고 TASK 의 단계가 가리킨다 ·
    ⓔ 등록부는 에이전트 등록부(`app/agents.py`)와 같은 꼴 — 코드에 적고 시험이 코드와 어긋남을 잡는다.
  - 겹침 협의: newfilemanager-b9 「겹침 없음」(그쪽은 `app.js` `outlineLoad` · `outline_match.js` — 이 일은 두 파일을 고치지 않는다).
- 2026-11-15 등록부 글 바뀜(newfilemanager-2b — 「분석 상태 표준화」, 원본 [spec_작업.md](spec_작업.md) ① 같은 날 · ② §20): 공통 모듈 「문서 올리기 · 첫 분석」 의 단계가 「기본 분석(헤딩 · 표 — 스크립트)」 · 「분석 상태 표시」 ·
  「LLM 판정(분리)」 · 「구분 기준 LLM 검토(옵션)」 으로 — 전의 「첫 분석 — 구분 기준 LLM 검토(저절로)」 단계는 없앰(올릴 때 저절로 돌지 않는다). 양식 맞추기 · 문서 일반 편집 · 문서 서식 복사의 「준비」 단계 글도 그에 맞춤. 페이지·API 의 꼴은 그대로.
- 2026-11-16 사용자("첫 페이지에서 한번에 … task 에서 단계별로 … 에이전트가 UI 를 제공" — 원문 [spec_작업에이전트.md](spec_작업에이전트.md) ① 같은 날 · astra 검토) → ② §9(TASK 마다 「진행 방식」 — 등록부의 `ways`). astra: 절차를 다시 적지 않는 메타데이터여야 하고, 첫 화면 에이전트는 TASK 머리만 읽으므로 머리에 둔다.
- 2026-11-16 사용자(시작 화면 TASK 카드 그림과 함께): **"task 작업을 할때 초기에 자동으로 검토하는 사항이 명시되어 있나? task 별로 문서를 만들고 그게 정리가 되어 있으면 좋겠는데. 워크플로우가 전체적인거라면 이건 좀 세부적인거지?"** → ② §10(TASK 문서).
  - 답: 적혀는 있으나 TASK 별로 모은 글이 없었다 — 올릴 때 저절로 도는 것은 [spec_작업.md](spec_작업.md) ② §9·§20, 시작 화면의 시작 검사는 ② §15·§15-1, 다음 단계로 가는 조건은 ② §16 의 표, 에이전트가 시작할 때 보는 상태는 [spec_작업에이전트.md](spec_작업에이전트.md) ② §3.
  - 물어서 받은 답: 꼴 = 「등록부에서 만든 글」(손으로 쓰는 md · 답만 은 안 고름) · 범위 = 「시작 점검 + 단계마다 조건」(시작 점검만 은 안 고름).
  - 이어서 "그리고 에이전트는 references 로 이걸 가지고 있어야해. 그리고 모든 로그에 접근이 가능해야 하고" → [spec_작업에이전트.md](spec_작업에이전트.md) ② §8(참조 글 · 로그 읽기).
  - 겹침 협의: newfilemanager-ff 「겹침 없음」(`ways` · 진행 보고는 끝남 — 그 글은 안 바꿈).

## ② 확정 사양

### 1. 등록부 (`app/workflow.py`)

- **`TASKS`** = TASK 마다 하나(차례 = 화면 차례 = `task_catalog.js` 의 차례): `job`(서버 `TASK["job"]` 의 키) · `inputs`(받는 문서) · `output`(산출물) · `note`(그 TASK 에서 꼭 알 것 한두 줄) · `stages`(단계 묶음 …) · `soon`(준비 중 — 묶음 없음).
  **이름 · 한 줄 설명은 여기 적지 않는다** — 화면이 `TASK_CATALOG`(`app/static/task_catalog.js`)에서 읽는다(원본 하나).
- **단계 묶음** = `id` · 이름(`meta` = `TASK_STAGE_META` 의 키 `config`·`frame`·`map`·`clean` — 이관·취합의 「N단계 이름」 은 화면이 그 원본에서 읽는다 / 그 밖에는 `no`·`name` 을 직접) · `does`(한 줄) · `steps`.
- **단계** = `key` · `no`(화면의 번호 — ①②… · 없으면 빈 글) · `name` · `by`(누가: `script` 스크립트 · `llm` LLM · `human` 사람 — 여럿이면 차례대로) · `does`(하는 일 한두 줄) · `out`(나오는 것) ·
  `change`(`none` 문서 안 바뀜 · `doc` 문서 바뀜 · `store` 문서는 그대로이고 저장만) · `modules`(`app/<이름>.py`) · `agents`(에이전트 id — `app/agents.py`) · `uses`(공통 모듈 id) · `spec`(사양서 파일 · 자리) ·
  `auto`(사람이 누르지 않아도 도는 것) · `optional`(안 해도 다음으로 가는 것) · `soon`(아직 없는 단계).
- **`COMMON`** = 공통 모듈 — TASK 에 묶이지 않고 여러 TASK 가 쓰는 과정: `id` · `name` · `does` · `where`(화면에서 여는 곳) · `steps`(위와 같은 꼴). 지금:
  `intake` 문서 올리기 · 첫 분석 / `headings` 헤딩 추출 / `division` 프로젝트 구성(구분 기준) / `styles` 서식 관리자 / `agent` 에이전트 보기 / `tables` 표 도구 / `outline` 템플릿 관계 · 서식 정리 / `verify` 검증 · 확정 · 저장 / `share` hwpx 공유 — 같이 쓰기(2026-11-16 — 어느 TASK 의 단계도 `uses` 로 가리키지 않는다: TASK 에 묶이지 않은 일 · [spec_공유.md](spec_공유.md)).
- `listing()` → 화면이 쓰는 꼴(§2): 모듈은 그 파일의 설명 첫 줄(`doc`)을, 에이전트는 등록부·설정의 작업 번호 · 이름 · 역할 · 지금 모델 · 도는 때를, 공통 모듈은 그것을 쓰는 TASK(`usedBy`)를, TASK 는 할 일 프롬프트 파일(`jobs/<job>.md` — 있으면)을 붙여 준다.
- 등록부의 글은 **화면 말**로 적는다(프로젝트 구성 · 자리 연결 · 넣기 계획 · 내용 반영 · 배포 기준본 · 기관 작성 내용 · 목적 문서·원본 문서 · 서식 관리자 — CLAUDE.md 용어).

### 2. API · 페이지 (`app/workflow_api.py`)

- `GET /api/workflow` → `{tasks: [{job, inputs, output, note, soon, prompt: "jobs/….md" | null, stages: [{id, meta | null, no, name, does, steps: [단계]}]}], common: [{id, name, does, where, usedBy: [job…], steps: [단계]}],
  by: {script, llm, human}, change: {none, doc, store}}` — 단계 = `{key, no, name, by: […], does, out, change, auto, optional, soon, uses: […], spec: {file, at} | null, modules: [{name, path, doc}], agents: [{id, no, name, group, role, run, model: {id, source}}]}`.
  문서·작업과 무관하다(읽기만 — 시작 화면에서도 열린다). LLM 연결이 없어도 된다.
- `GET /workflow` → 페이지(`app/static/workflow.html` — `workflow.css`·`workflow.js`·`style.css`·`task_catalog.js` 주소에 수정 시각 `?v=` · `Cache-Control: no-cache` — 시작 화면과 같은 규칙).

### 3. 목록 화면 (`app/static/workflow.html` · `workflow.js` · `workflow.css`; 기본 다이어그램은 §7)

- **따로 선 페이지**(앱의 문서 화면과 다른 탭): 상단 줄(앱 이름 = 시작 화면으로 · 제목 「TASK 워크플로우」 · 「모두 펼치기」/「모두 접기」) + 왼쪽 목차(전체 보기 · TASK 일곱 · 공통 모듈 — 넓은 창에서 붙박이, 좁으면 위에 가로로) + 본문.
  색·글꼴·단추는 앱의 것(`style.css` 의 변수) — 보라 = LLM([design.md](../design.md) §13).
- **범례**(전체 보기 위 한 줄): 누가 — 「스크립트」(회색) · 「LLM」(보라) · 「사람」(파랑) / 「문서 바뀜」(주황 — 그 단계에서 문서가 바뀔 때만 줄에 붙는다. 「안 바뀜」 · 「안 바뀜 — 결과만 저장」 은 펼친 세부의 「문서」 줄) /
  「저절로」 · 「안 해도 됨」(점선 꼬리표 — 「준비 중」 도 같은 꼴) / 묶음의 점(보라 = LLM 단계가 있음 · 주황 = 문서를 바꾸는 단계가 있음).
- **전체 보기**: TASK 마다 한 줄 — TASK 이름(누르면 그 TASK 로) + 단계 묶음의 사슬(「1단계 프로젝트 구성 › 2단계 문서 프레임 작성 › …」 — 묶음마다 단계 수 · LLM 이 도는 묶음은 보라 점 · 문서를 바꾸는 묶음은 주황 점). 준비 중인 TASK 는 「준비 중」.
- **TASK 절**(TASK 마다): 이름 · 한 줄 설명(`TASK_CATALOG`) · 「받는 문서 → 산출물」 · 꼭 알 것(`note`) · 할 일 프롬프트 파일 이름 → 단계 묶음을 **세로 차례**로(왼쪽 레일에 묶음 번호).
  묶음 안의 단계는 줄마다 [번호] 이름 · 누가 · 문서 바뀜 표지 · 하는 일 한 줄이 **펴지 않아도 보인다**. 줄을 누르면(`<details>`) 그 아래에 나오는 것 · 공통 모듈(누르면 그 절로) · 에이전트(작업 번호 · 이름 · 모델 · 도는 때 · 역할 글) · 모듈(파일 이름 + 설명 첫 줄) · 사양 자리.
- **공통 모듈 절**: 이름 · 하는 일 · 여는 곳 · 「쓰는 TASK」(누르면 그 TASK 로) + 단계(같은 꼴).
- 주소 `#<job>` · `#common-<id>` 로 그 절이 바로 열린다(목차의 지금 절 표시도 따라간다).
- 폭: 1280px 이상 = 목차 + 본문 / 900px 아래 = 목차가 본문 위 가로 줄 / 360px 까지 가로 스크롤 없음([design.md](../design.md) §1 규칙 8).
- 읽기만 한다 — 실행 단추 · 진행 상태는 없다.
- **클래스는 모두 `wf-` 로 시작한다**(꾸밈 클래스도 `wf-t-doc` · `wf-soon` 처럼) — 색 변수를 쓰려고 `style.css` 를 함께 읽으므로 `.doc` · `.soon` 같은 이름은 앱의 규칙에 걸린다(③ 2026-11-15).

### 4. 들어가는 길

- 상단 바 「에이전트 설정」 링크(`a#agentsLink` — 2026-11-15 단추에서 링크로: [spec_에이전트.md](spec_에이전트.md) ② §5) **앞**의 링크 `a#workflowLink.btn.wf-link`(`href="/workflow"` · 새 탭 — 연 문서를 닫지 않는다): **글 없이 아이콘만**(18px · 이름 「TASK 워크플로우」 는 `title`·`aria-label` — 2026-11-16 사용자 「이건 아이콘으로 하면 되지 않냐?」: 원본 [spec_hwpx_웹편집.md](spec_hwpx_웹편집.md) ② §9 「상단 바 오른쪽 끝 아이콘」. 전에는 아이콘 + 글 · 1500px 아래에서만 아이콘). 문서가 없어도 보인다.
  문서를 연 상단 바(35px · 단추 26px)의 폭을 지킨다 — 541~880px 에서는 감춘다(「에이전트 설정」 링크가 780px 아래에서 숨는 것과 같은 까닭 — 줄 넘침을 키우지 않는다). 규칙은 `document_header.css` 의 상단 바 절.
- 에이전트 설정 페이지(`/agents`)의 상단 줄 「워크플로우」 도 이 페이지로 온다. 거꾸로 이 페이지의 단계 세부 「에이전트」 이름은 `/agents#<에이전트 id>` 로 간다(등록부에 있는 에이전트만 — `workflow.js` `a.wf-agent-link`).

### 5. 갱신 규칙 · 검사

- **기능을 더하거나 고칠 때마다 이 페이지를 항상 함께 갱신한다**(2026-11-15 사용자 지시). 일을 끝내기 전에 페이지(전체 보기 · TASK 절 · 공통 모듈)가 지금 동작과 맞는지 보고, 다르면 `app/workflow.py` 의 글을 고친다 —
  TASK · 단계가 늘고 줄 때만이 아니라 단계가 하는 일 · 차례 · 누가 하나 · 문서가 바뀌나 · 산출물 · 공통 모듈의 여는 곳이 바뀔 때도다. 페이지는 등록부에서 그려지므로 전체 보기는 따로 고치지 않는다. 바뀔 것이 없으면 그대로 둔다.
- **TASK 를 더하거나 TASK 의 단계 · 쓰는 모듈 · 에이전트를 바꾸면 `app/workflow.py` 도 함께 고친다**([spec_작업.md](spec_작업.md) ② §16 「모듈 변경 시」 와 같은 때). 새 LLM 호출(에이전트)은 그것이 도는 단계의 `agents` 에 적는다.
- `tests/test_workflow.py` 가 잡는 것: 서버 `TASK["job"]` 의 키와 `TASKS` 가 같다 · 묶음의 `meta` 가 `TASK_STAGE_META` 에 있다 · 준비 중(`soon`)이 `TASK_CATALOG` 와 같다 · `modules` 의 파일이 있다 · `agents` 의 id 가 등록부에 있고 **등록된 에이전트가 모두 어느 단계에든 적혀 있다** ·
  `uses` 의 공통 모듈이 있다 · `spec` 의 사양서 파일이 있다 · 글(`name`·`does`)이 비지 않았다 · API 왕복 · 페이지가 열린다.
- 화면 검사 `tools/smoke_workflow_ui.py`(검사 이름 `workflow`): 상단 바 링크 · 목차 · 전체 보기 · TASK 절의 묶음·단계 · 펴기(에이전트 · 모듈) · 공통 모듈의 「쓰는 TASK」 · `#job` 주소 · 좁은 폭 · 콘솔 오류 없음.

### 6. 하지 않는 것(v1)

- 지금 작업의 진행 상태를 이 페이지에 보이기(작업 내용의 순서 안내가 맡는다) · 이 페이지에서 단계를 실행하기 · 등록부를 화면에서 고치기 · 사양서 글을 페이지에서 열기(파일 이름과 자리만 보인다).

### 7. 순차 확인 다이어그램

- 기본 보기 = **다이어그램**. 전체 보기에서 TASK·단계 묶음을 선택하거나 왼쪽 목차에서 공통 모듈을 선택하면 그 과정 하나를 보여 준다. 기존 긴 설명은 **목록** 보기로 유지한다.
- 상단은 조밀하게 배치한다: 본문 위 여백 12px · 설명 위아래 4px · 입출력 접기 아래 10px · 단계 묶음 아래 12px. 단계 묶음의 번호·이름·개수는 한 줄로 보이며 긴 이름은 줄바꿈한다. 글자 크기는 유지하고 여백을 줄여 단계 흐름이 먼저 보이게 한다.
- TASK의 단계 묶음은 가로 화살표로 잇고, 선택한 묶음의 낱단계는 번호·세로 화살표로 잇는다. 공통 모듈은 낱단계 흐름부터 보인다. 노드를 누르면 해당 단계 설명으로 이동한다.
- 상세 영역은 **지금 확인하는 단계**의 이름·담당(복수 유지)·하는 일·나오는 것(등록된 경우)·문서 변경 여부·연결된 공통 모듈을 보여 준다. 에이전트·모듈 경로·사양은 접힌 「기술 상세」 안에 둔다.
- **이전 / 다음**은 TASK 전체 낱단계를 등록 순서대로 탐색한다(묶음 경계도 이동). 「단계 i / n」은 읽는 위치이며 실제 실행·완료 상태가 아니다. 처음·끝에서는 해당 이동 단추가 꺼진다. 준비 중 TASK는 빈 다이어그램 대신 안내를 보인다.
- 기존 `#job`·`#job--stage`·`#common-id`에 더해 `#job--stage--step`·`#common-id--step`으로 단계를 직접 열고 브라우저 뒤로/앞으로 이동한다. 보기 전환도 같은 위치를 유지한다.
- 360px에서 가로 넘침 없이 흐름과 상세를 세로로 배치한다. 키보드로 노드·이동 단추를 조작할 수 있고 선택 상태를 `aria-current`로 알린다. 이 화면은 서버 데이터를 읽기만 하며 확인 버튼으로 문서를 실행·수정하지 않는다.

### 8. `workflow.md` — 등록부를 글로

2026-11-15 사용자 "워크플로우는 항시 내용을 workflow.md 로 갖고 있고, 에이전트는 이걸 항시 가지고 있다가 참조하도록".

- 저장소 루트의 [workflow.md](../workflow.md) = 워크플로우의 내용 전체를 글로 옮긴 것. **등록부(`app/workflow.py`)에서 만든 글**이다 — 손으로 고치지 않는다(원본은 등록부 하나 — 페이지와 이 글이 같은 것을 보인다).
  담는 것: 「한눈에」 표(TASK · 키 · 단계 묶음 사슬) · TASK 마다 한 줄 설명 · 받는 문서 · 산출물 · 알아 둘 것 · 전제(`jobs/<job>.md` — 있을 때) · 단계 묶음 › 단계(번호 이름 — 누가(차례대로) · 문서가 바뀌나 · 저절로/안 해도 됨/준비 중 · 하는 일,
  `→` 줄에 나오는 것 | 에이전트(작업 번호 이름) | 공통 모듈 | 모듈 | 사양 자리) · 공통 모듈마다 하는 일 · 여는 곳 · 쓰는 TASK · 단계.
- 만드는 곳 `workflow.markdown()` — 등록부 + `task_catalog.js`(TASK 이름 · 한 줄 설명 · 「N단계 이름」: `workflow.catalog()`) + 에이전트 등록부의 **기본** 작업 번호·이름 + `jobs/` 의 파일. 사람의 설정(에이전트 설정에서 고친 번호·모델)과 모듈 설명 글은 넣지 않는다 — 어느 PC 에서나 같은 글.
- **다시 만들기** `python -X utf8 tools/workflow_md.py`(같으면 그대로 · `--check` 는 쓰지 않고 견주기만 — 다르면 종료 코드 1). 등록부 · TASK 이름 · 에이전트 번호·이름 · `jobs/` 를 고치면 다시 만든다.
  `tests/test_workflow.py` `test_workflow_md_is_the_registry_written_out` 가 파일이 `markdown()` 과 같은지 본다(안 만들면 떨어진다 — 「항시」 의 보장).
- **읽는 쪽**: ⓐ 작업 에이전트(첫 화면·작업 화면의 대화창 — [spec_작업에이전트.md](spec_작업에이전트.md))의 프롬프트에 이 글이 붙는다(그 에이전트가 작업 절차를 여기서 안다) · ⓑ 코드 에이전트는 TASK 의 과정을 만들거나 고치거나 설명하기 전에 이 글을 읽는다(CLAUDE.md).
  CLAUDE.md 가 이 파일을 세션마다 통째로 불러오지는 않는다(43KB — 지침이 두 배가 된다): 가리키기만 한다.

### 9. 진행 방식 — TASK 마다 `ways` (2026-11-16)

- 등록부 `TASKS` 의 TASK 마다 `ways = {quick, asks, stops, detail}`(준비 중인 TASK 는 없음) — 이름은 `WAYS`: 「한 번에 진행」(누가 끝까지 가고 어디서 확인받나) · 「에이전트가 묻는 것」 · 「멈추거나 남기는 곳 · 보정」 · 「단계별(세부 작업)」(어디서 · 언제).
  **절차를 다시 적지 않는다** — 차례는 `stages` 가 원본이고, 여기는 두 방식이 그 TASK 에서 무엇을 뜻하는지의 설명뿐이다. 뜻의 원본은 [spec_작업에이전트.md](spec_작업에이전트.md) ② §7.
- 나가는 곳: `listing()` 의 `tasks[].ways = [{key, name, text}]` · `waysNote`(두 방식 한 줄) → 페이지의 TASK 절 「진행 방식」(`dl.wf-ways` — 받는 문서·산출물 아래) · 전체 보기의 한 줄(`#waysNote`) /
  `markdown()` 의 머리 글 한 줄 + TASK 머리(첫 단계 묶음 앞)의 네 줄 — 첫 화면 에이전트의 프롬프트는 TASK 머리만 싣는다(`work_guide.workflow_part`).
- 갱신 규칙(§5 에 더함): 한 번에 진행의 범위 · 확인받는 곳 · 멈추는 조건 · 남기는 것 · 보정하는 화면이 바뀌면 그 TASK 의 `ways` 도 고친다.

### 10. TASK 문서 — `tasks/<TASK 키>.md`: 시작 점검 · 단계마다 조건 (2026-11-16)

2026-11-16 사용자 "task 작업을 할때 초기에 자동으로 검토하는 사항이 명시되어 있나? task 별로 문서를 만들고 그게 정리가 되어 있으면 좋겠는데. 워크플로우가 전체적인거라면 이건 좀 세부적인거지?" → 물어서 받은 답 「등록부에서 만든 글」 · 「시작 점검 + 단계마다 조건」.

- **두 글의 몫**: [workflow.md](../workflow.md) = 모든 TASK 의 차례를 보이는 **전체 지도** · `tasks/<job>.md`(**TASK 문서**) = TASK 하나의 **세부**. TASK 문서는 그 TASK 의 workflow.md 절(머리 · 단계)을 그대로 담고 그 위에 둘을 더한다:
  - **시작 점검** = 시작할 때 **저절로 확인하는 것**. 전에는 [spec_작업.md](spec_작업.md) ② §9·§15·§15-1·§16·§20 과 [spec_작업에이전트.md](spec_작업에이전트.md) ② §3 에 흩어져 있었고 TASK 별로 모은 글이 없었다.
  - **단계마다 조건** = 그 단계를 하려면 · 끝난 것으로 보는 때 · 멈추는 때 · 남기는 것과 보정.
- **등록부**(`app/workflow.py`):
  - TASK 의 `entry` = 점검 항목들 `_c(key, when, name, does, miss, by, uses, spec)` — `when`(언제 보나 — `WHEN`): `start` 「TASK 를 시작할 때」(카드 · 문서 목록 · 첫 화면 대화창 — 올리기 전, 안 맞으면 시작하지 않는다) ·
    `upload` 「문서를 올릴 때」(저절로 도는 것 — 유료 LLM 없음) · `enter` 「TASK 화면을 열 때」(작업 내용 · 에이전트의 시작 턴이 셈하는 지금 상태 — 모자란 것이 사전 준비) · `manual` 「저절로 돌지 않는 것」(돌 것 같지만 사람이 단추로 — 유료 LLM).
    `does` = 무엇을 확인하나 · `miss` = 안 맞으면 어떻게 되나(없으면 빈 글). 준비 중인 TASK 는 `entry` 가 없다.
  - 단계의 `need`(하려면) · `done`(끝난 것으로 보는 때) · `stop`(멈추는 때) · `left`(남기는 것 · 보정) — 이름은 `COND`. TASK 의 단계(준비 중 아님)는 `need`·`done` 이 꼭 있고 `stop`·`left` 는 있을 때만. 공통 모듈의 단계에는 적지 않는다.
  - **근거는 코드다 — 지어내지 않는다**: 시작 검사 = `home_files.js` `homeFilesGo` · `app.js` `homeTaskStart` / 올릴 때 = `firstRun`(spec_작업 ② §9) / 지금 상태 = `doc_agent_work.js` `agwStatus`(양식 맞추기 `agwFitStatus` · 이관 `agwRelayStatus` · 취합 `agwGatherStatus`) ·
    단계의 끝남 = `app.js` `taskSteps` · `gather.js` `gatherSteps` · `style_lib.js` `slStepState` · 멈춤 = `divRunWhy` · `divAutoStops`. 그 함수들을 고치면 이 글도 함께 본다.
- **나가는 곳**: `listing()` 의 `tasks[].entry = [{when, name, note, items: [{key, name, by, does, miss, uses, spec}]}]`(항목이 있는 때만) · `tasks[].doc = "tasks/<job>.md"` · 단계의 `cond = [{key, name, text}]`(적힌 것만) →
  페이지 TASK 절의 「시작 점검」 과 단계 세부의 조건 줄 / `task_markdown(job)` → `tasks/<job>.md` / `markdown()` 의 TASK 머리에 두 줄(「시작 점검」 = 때마다 항목 이름만 · 「세부」 = TASK 문서 경로 — 첫 화면 에이전트가 머리만 읽는다).
- **다시 만들기**: §8 과 같은 명령 `python -X utf8 tools/workflow_md.py` 가 `workflow.md` 와 `tasks/*.md` 를 함께 만든다(`--check` 는 견주기만). 등록부에 없는 TASK 의 파일이 `tasks/` 에 남아 있으면 알린다(지우지는 않는다).
- **읽는 쪽**: ⓐ 작업 진행 에이전트 — 작업 화면의 프롬프트는 그 TASK 의 workflow.md 절 대신 **TASK 문서**를 싣는다(참조 글 — [spec_작업에이전트.md](spec_작업에이전트.md) ② §8) · ⓑ 코드 에이전트 — 그 TASK 를 만들거나 고치거나 설명하기 전에 읽는다(CLAUDE.md) · ⓒ 사람 — 파일이나 `/workflow` 의 TASK 절.
- **시험**(`tests/test_workflow.py`): 준비 중이 아닌 TASK 마다 `entry` 가 있고 `start`·`upload`·`enter` 항목이 하나 이상 · 항목의 key 가 겹치지 않고 글이 비지 않음 · `uses`·`spec` 이 있는 것 · TASK 단계의 `need`·`done` · `tasks/<job>.md` 가 `task_markdown(job)` 과 같고 남는 파일이 없음.
- **갱신 규칙**(§5 에 더함): 시작 화면의 시작 검사 · 올릴 때 저절로 도는 것 · 에이전트가 시작할 때 보는 상태 · 단계가 끝난 것으로 보는 조건 · 멈추는 조건 · 남기는 것이 바뀌면 그 TASK 의 `entry` 와 단계 조건을 고치고 다시 만든다.
- 하지 않는 것: 지금 작업의 점검 결과를 이 페이지에 보이기(그것은 에이전트 보기의 시작 턴과 「작업 내용」 의 몫 — §6) · 점검 항목을 코드와 자동으로 견주기(글은 사람이 맞춘다 — 근거 함수를 위에 적어 둠).


## ③ 구현 상태

- 2026-11-16 등록부 글 바뀜(newfilemanager-d3 — hwpx 공유: [spec_공유.md](spec_공유.md)): 공통 모듈 `share`(「hwpx 공유 — 같이 쓰기」 — 단계 다섯: 공유 켜기 · 손님 들어오기 · 같이 쓰기 · 공유폴더에 저장 · 키 새로 만들기·끄기)를 더함 · `SP_SHARE` ·
  `workflow.md` 다시 만듦 · `tools/smoke_workflow_ui.py` 의 공통 모듈 수 여덟 → 아홉(목차 링크 16 → 17).
- 2026-11-15 등록부 글 바뀜(newfilemanager-b8 — 작업 진행 에이전트: [spec_작업에이전트.md](spec_작업에이전트.md)): 공통 모듈 「에이전트 보기」 에 단계 「작업 진행 — 설명 · 다음 단계 제안 · 실행」(에이전트 19) · 여는 곳에 「첫 화면 오른쪽 대화창」 · 양식 맞추기의 「문서 올리기 · 첫 분석」 과 이관·취합의 「준비」 단계에 「LLM 을 쓸 수 있으면 패널 「에이전트」 가 열려 …」 와 공통 모듈 「에이전트 보기」 연결 → `workflow.md` 371줄. `catalog()` 는 TASK 가 받는 확장자(`accept`)도 읽는다(첫 화면 에이전트가 쓴다).
- 2026-11-15 ② §8 `workflow.md` 구현(newfilemanager-b8): `app/workflow.py` 에 `MD` · `catalog()` · `markdown()` · 새 `tools/workflow_md.py` · 새 `workflow.md`(369줄 · 22,341자) · `tests/test_workflow.py` 에 시험 하나(9개 통과).
  같은 날 에이전트 설정 페이지에 맞춰 `workflow.js` 의 에이전트 이름을 `/agents#<id>` 링크로(`workflow.css` `.wf-agent-link`) · `smoke_workflow_ui.py` 의 상단 바 끝 요소(`agentsLink`)와 세부의 에이전트 이름 읽기를 맞춤.
- 2026-11-15 상단 여백 축소: `workflow.css`의 제목·설명·입출력 접기 간격과 단계 묶음 카드 padding을 줄이고 번호·이름·개수를 한 줄로 배치. 1500px 「문서 일반 편집」에서 흐름 시작 위치가 본문 위 271px → 181px, 카드 높이는 65px → 42px. 실제 8114에서 3개 흐름·1500/900/760/480/360px·접기 펼침·단계 이동을 확인했고 가로 넘침·페이지 오류 없음.
- 2026-11-15 순차 확인 다이어그램(② §7) 구현: TASK 묶음 연결 · 낱단계 화살표 · 선택한 단계 설명 · 이전/다음 · 기술 상세 접기 · 목록 전환 · 상세 주소. 기존 등록부와 API를 그대로 사용한다.
  - 확인: `tests/test_workflow.py` 8개 통과, 다이어그램 탐색·읽기 전용·360px 반응형 및 기존 목록 화면 검사 통과. 추가 탐색 검사 3개(뒤로/앞으로 · 스크롤 후 보기 전환의 주소 · 같은 주소 재선택)와 실제 8114 화면 확인도 통과. 화면 전환 시 브라우저 기본 fragment 스크롤과 겹치지 않도록 내부 링크를 공통 탐색 함수로 처리한다.
  - 정적 파일만 변경하므로 8114 서버 재시작 없이 `/workflow` 새로고침으로 반영된다.
- 2026-11-15 ② §1~§5 구현.
  - 등록부 `app/workflow.py`: TASK 7(`plan_fit` · `plan_merge` · `plan_to_report` · `report_fit` · `report_merge`(준비 중 — 묶음 없음) · `doc_edit` · `style_copy`) + 공통 모듈 8. 단계 79개(TASK 47 · 공통 32) — 에이전트 18개가 모두 어느 단계에든 적혀 있다.
    차례의 근거: 이관 = `app.js` `taskSteps`·`TASK_STAGES` · 취합 = `gather.js` `gatherSteps` · 양식 맞추기 = [spec_구분_기준.md](spec_구분_기준.md) ② §22 실행 묶음 · 일반 편집 = [spec_일반편집.md](spec_일반편집.md) ② §8~§11 · 서식 복사 = [spec_서식복사.md](spec_서식복사.md) ② §1 「단계」 ·
    전제 = `jobs/*.md` · 모듈 = [spec_작업.md](spec_작업.md) ② §16 표.
  - API·페이지 `app/workflow_api.py`(`GET /api/workflow` · `GET /workflow`) — `server.py` 는 include 한 줄. 화면 `app/static/workflow.html` · `workflow.js` · `workflow.css`(새 파일 셋 — `app.js`·`style.css` 는 안 고침).
  - 들어가는 길: `index.html` 의 `a#workflowLink`(「에이전트 설정」 앞) + `document_header.css` 의 상단 바 절 네 줄.
  - 시험 `tests/test_workflow.py` 8개 통과(§5 의 계약). 화면 검사 `tools/smoke_workflow_ui.py`(검사 이름 `workflow` — 기본 묶음) 17개 통과.
  - 만들며 고친 것: ⓐ 꾸밈 클래스 `.doc`(「문서 바뀜」 꼬리표 · 묶음의 주황 점)가 `style.css` 의 `.doc`(문서 상자)에 걸려 꼬리표가 줄 전체로 늘어나고 좁은 폭에서 본문이 가로로 넘쳤다 → 모든 클래스를 `wf-` 로(② §3).
    ⓑ 목차의 「지금 절」 을 `offsetTop` 으로 셈해 처음에 아무 절도 표시되지 않았다(본문이 자리 기준 상자가 아님) → 본문 상자 기준의 화면 자리로 셈.
  - 상단 바를 고쳤으므로 함께 돌린 화면 검사: `workflow` 17 · `agents` 21 · `panel_head` 44 · `home` 81 · `workspace` 32 · `task` 113 · `doc_quick` 19 — 모두 통과(`tools/run_ui_gates.py`).
  - 8114 재시작(같은 날 — 새 라우트 `/workflow` · `/api/workflow` 라 필요. 물어서 받은 답 「지금 재시작」): 띄우개째 끄고 1개만 다시 띄움 → `api · claude-fable-5-2 · available true` · `/workflow` 200 · 콘솔 오류 없음.
- 2026-11-16 ② §9 — 구현(newfilemanager-ff): `app/workflow.py`(`WAYS` · `WAYS_NOTE` · `_ways` · TASK 여섯의 `ways` · `listing()` · `markdown()`) → `workflow.md` 다시 만듦(398줄 — 공통 모듈 「에이전트 보기」 에 단계 「진행 보고」 를 더함) · `workflow.js`(TASK 절 「진행 방식」 · 전체 보기 한 줄) · `workflow.css`(`.wf-ways`).
  `tests/test_workflow.py` 통과 · 화면 검사 `workflow`(이관 절의 줄에 진행 방식 넷을 더해 고침).
- 2026-11-16 ② §10 — 구현(newfilemanager-78).
  - 등록부 `app/workflow.py`: `WHEN`(때 넷) · `COND`(조건 이름 넷) · `_c()` + 여러 TASK 가 같이 쓰는 항목(`_c_format` · `_C_TARGET` · `_C_ONE` · `_C_WORK` · `_c_role` · `_C_TASK` · `_C_IMPORT` · `_C_ANALYSIS` · `_c_status` · `_C_AGENT` · `_C_RUNNING` · `_C_LLM` · `_C_DIVLLM` · `_c_task_llm`) ·
    TASK 여섯의 `entry`(양식 맞추기 18 · 취합 21 · 이관 23 · 일반 편집 12 · 서식 복사 12 — 준비 중인 「연차보고서 취합」 은 없음) · `_s()` 에 `need`·`done`·`stop`·`left`(TASK 의 단계 46개 가운데 준비 중 하나를 뺀 45개에 `need`·`done`) ·
    `entry(t)` · `listing()` 의 `tasks[].entry`·`doc` · 단계의 `cond` · `_md_tools()`(markdown · task_markdown 이 같이 쓰는 글 조각) · `task_md()`·`task_markdown()`·`task_docs()` · `TASK_DIR`.
    글의 근거로 읽은 코드: `home_files.js` `homeFilesGo`·`hfOpenTarget`·`hfAddSource` · `app.js` `homeTaskStart`·`taskEnter`·`firstRun`·`taskSteps`·`taskStepsCalc`·`divRunWhy`·`divPlanState`·`divAutoStops` · `doc_agent_work.js` `agwFitStatus`·`agwRelayStatus`·`agwGatherStatus`·`agentWorkEnter` ·
    `gather.js` `gatherSteps`·`gatherCalc` · `style_lib.js` `slStepState`·`styleSaveAuto` 의 설명. 공통 모듈 「에이전트 보기」 에 단계 「참조 글 · 로그 읽기」 를 더함([spec_작업에이전트.md](spec_작업에이전트.md) ② §8).
  - 만든 글: `tools/workflow_md.py` 가 `workflow.md`(414줄 — TASK 머리에 「시작 점검」 한 줄 · 「세부」 한 줄, 머리글에 TASK 문서 안내 한 줄)와 새 `tasks/*.md` 일곱(양식 맞추기 둘 135줄 · 취합 180줄 · 이관 188줄 · 일반 편집 125줄 · 서식 복사 123줄 · 연차보고서 취합 12줄)을 함께 쓴다.
  - 페이지 `workflow.js`·`workflow.css`: 목록 보기의 TASK 절에 「시작 점검」(진행 방식 아래 · 단계 묶음 위 — 때마다 묶음 `details.wf-entry-group`: 접힘 · 항목 = 이름 · 누가 · 무엇을 확인하나 · 「안 맞으면」) · 단계 세부에 조건(`dl.wf-cond` — 세부 `.wf-more` 앞) ·
    다이어그램 보기에 접힌 「시작 점검 — … n가지 보기」(`details.wf-entry-context`) · 고른 단계의 「이 단계의 조건」 · 「모두 펼치기」·「모두 접기」 가 시작 점검 묶음도 함께. 공통 모듈 · 준비 중 TASK 에는 없다.
  - 시험 `tests/test_workflow.py` 11개(새 둘 — 시작 점검·단계 조건의 계약 · TASK 문서가 등록부와 같음 + listing 검사에 `doc`·`entry`·`cond`) · 화면 검사 `workflow`(이관 절의 시작 점검 · 항목 · 조건 · 모두 펼치기/접기 · 다이어그램의 조건과 시작 점검 · 공통 모듈에는 없음 · 좁은 폭에서 시작 점검을 편 채 넘침 없음).
  - 서버 코드(등록부 · 새 모듈)를 고쳤으므로 8114 에는 다시 켠 뒤에 보인다(다시 켜기는 사용자가 말할 때 — 페이지의 js·css 는 새로 고침만으로 읽히지만 `/api/workflow` 의 `entry`·`cond` 가 없으면 시작 점검이 그려지지 않는다: 없는 필드는 빈 목록으로 본다).

## ④ 미결/후속

- (사용자 확인 전 — ① 의 에이전트 판단 ⓐ~ⓔ) 따로 선 페이지가 아니라 문서 옆 열이어야 하는지 · 지금 작업의 진행 상태도 얹을지 · 연 작업의 TASK 로 바로 열기(`/workflow#<job>` — 지금은 늘 맨 위).
- TASK 사이의 차례(양식 맞추기로 만든 프레임 → 취합 → 이관처럼 한 프로젝트에서 TASK 를 잇는 길)는 적지 않았다 — 사양에 정해진 것이 없다(정하면 전체 보기에 더한다).
- 사양서 글을 페이지에서 바로 열기(지금은 파일 이름 · 자리만) · 등록부의 글을 화면에서 고치기.
