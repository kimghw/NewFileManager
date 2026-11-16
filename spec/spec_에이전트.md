# 에이전트 설정 — 에이전트 등록부 · 작업 번호 · 역할 · 프롬프트 · 모델 · 실행 기록

앱이 LLM 에 맡기는 일 하나하나(**에이전트**)가 어떤 역할을 하고 어디서 돌며 무슨 프롬프트로 도는지를 한곳에서 보고 고치는 화면과 그 저장소의 사양.
에이전트가 하는 일 자체(무엇을 판정하고 답이 어떤 꼴인지)는 그 기능의 사양서가 원본이다 — 여기는 **등록부·설정·화면**만 적고 기능 사양은 링크한다.

## ① 질의·요청 히스토리

- 2026-11-15 사용자(템플릿 서식 정리 에이전트 — [spec_hwpx_웹편집.md](spec_hwpx_웹편집.md) ② §8-4 — 를 쓴 뒤): **"에이전트 설정을 만들고,, 어떤 역할을 하고 프롬프트가 무엇인지 작업번호등을 관리할 수 있는 관리를 우측 상단에 배치해줘."** → ② 전부.
  - 살펴본 것: 앱에는 LLM 호출이 18가지 있었고(헤딩 추출 6 · 프로젝트 구성 2 · 이관·취합 4 · 표 3 · 문서 편집 1 · 서식 2) 저마다 프롬프트를 보는 곳이 달랐다 — 헤딩 지침 편집 열 · 병합 「지침」 단추 · 에이전트 보기의 「보낸 글」 ·
    표 지침 열 · 템플릿 서식 정리 열의 스킬 칸. 모델은 서버 전체 설정 하나(`NFM_LLM_MODEL_FORCE` — 8114 는 Fable)와 템플릿 정리의 고정(Opus 5.5)뿐이었다. 앞선 프로젝트(FileMergeManager `spec_에이전트.md`)의
    「에이전트」 탭(에이전트마다 용도 · 실행 위치 · 프롬프트·스킬)이 같은 요청의 선례다.
  - 에이전트 판단(사용자 확인 전 — ④): ⓐ 「에이전트」 = LLM 호출 단위 하나(호출 이름 `what` 의 첫머리로 가른다 — 2단계의 A·B·C·D 호출은 저마다 에이전트) ·
    ⓑ **「작업번호」 = 에이전트(가 하는 일)마다 붙는 번호**(기본 「01」~「18」 — 목록·실행 기록에서 그 번호로 부르고, 사람이 고칠 수 있다). 「쓰는 곳」(어느 TASK·단계에서 도는가)과 실행마다의 **실행 번호**(#1 …)도 함께 보인다 —
    「작업번호」 가 그 둘 가운데 하나를 뜻했더라도 화면에 있다 · ⓒ 「관리」 = 보기 + 고치기: 작업 번호 · 역할 글 · **모델 · 생각 깊이**(에이전트마다 — 「설정」 이라는 말에서 읽음) · 프롬프트 가운데 사람이 관리하는 글 ·
    ⓓ 프롬프트의 **계약**(입력의 뜻 · 답의 꼴)은 답을 검증하는 코드와 한 몸이라 보기만 한다 · 저장소 파일이 원본인 글(병합 판단 지침 `app/merge_guides_default/*.md` · 할 일 프롬프트 `jobs/*.md` — CLAUDE.md 「파일이 원본」)도 보기만 하고 파일 경로를 보인다 ·
    제 저장소와 저장 끝점이 있는 글(헤딩 지침 · 템플릿 정리 스킬)은 그 자리에서 고친다 · ⓔ 「우측 상단」 = 상단 바 오른쪽 끝의 단추(문서가 없어도 보인다) → 문서 옆 열(2열 — 팝업 아님).
  - 겹침 협의: newfilemanager-f3 「겹침 없음」 · newfilemanager-e9 「겹침 없음」 + 상단 바에서 지킬 것(직계 `.btn` · 문서를 연 줄은 35px·단추 26px·꺾이지 않음 · 접기 묶음은 안 건드림 · `smoke_panel_head_ui` 의 1600·1280·1100px 넘침 검사) ·
    newfilemanager-9d(같은 날 서식 갈래의 「대표와 다른 값」 글 꼴을 고치는 중 — `outline_match.js`·`tpl_agent.js` 의 title 줄: 이 일과 줄이 안 겹침).
- 2026-11-15 등록부 글 바뀜(newfilemanager-2b — 「분석 상태 표준화」, 원본 [spec_작업.md](spec_작업.md) ① 같은 날 · ② §9·§20): `div_review`·`div_missing` 이 「저절로 돌기도 함」 에서 **「눌러야 돎」** 으로(`run: manual`) — 새 작업의 첫 분석이 구분 기준 LLM 검토를
  더 부르지 않는다(사용자 「구분 기준은 옵션」 · 답 「저절로 안 돌림」). ② §1 표의 「쓰는 곳」 두 칸을 맞추고, `div_missing` 의 기능 사양 자리를 ② §13 으로 바로잡음(§12 는 다른 절).
- 2026-11-15 사용자(문서 옆 열로 뜬 「에이전트 설정」 화면 첨부): **"에이전트도 워크플로우 처럼 페이지로 해줘"** → ② §5 를 다시 씀. 문서 옆 열(2열 kind `agents`)을 없애고 **따로 선 페이지 `/agents`**(새 탭)로 옮긴다 — 상단 바의 단추는 링크가 된다.
  - 에이전트 판단(사용자 확인 전 — ④): ⓐ 열은 남기지 않는다(같은 설정을 고치는 곳이 둘이면 판이 어긋난다 — 페이지 하나) · ⓑ 틀은 워크플로우 페이지와 같게 — 상단 줄 + [왼쪽 목차 | 본문], 주소의 `#` 로 바로 열림 ·
    ⓒ 넓은 폭을 써서 한 에이전트는 두 단(왼쪽 = 설정 ①②③ · 오른쪽 = ④ 프롬프트 ⑤ 최근 실행) · ⓓ 저장 안 한 설정 값은 다른 에이전트로 갔다 와도 남는다(목차가 늘 보여 잘못 누르기 쉽다) ·
    ⓔ 워크플로우 페이지의 단계 세부 「에이전트」 이름을 이 페이지의 그 에이전트로 잇는다. API · 등록부 · 설정 파일은 그대로.
  - 겹침 협의: newfilemanager-e9 「겹침 없음」 + 상단 바에서 지킬 것(직계 `.btn` 이면 35px·26px 규칙을 그대로 받음 · 1500px 아래 아이콘만 · 541~780px 감춤을 잃지 않기 · `smoke_panel_head_ui` 넘침 검사) · newfilemanager-2b 「겹침 없음」(`index.html` 의 `doc_status` 줄을 남길 것).
- 2026-11-15 에이전트 19 「작업 진행」(`work_guide`)을 더함(newfilemanager-b8) — 사용자 "첫 화면 우측에 에이전트 대화할 수 있는 대화창 …" 의 LLM 호출. 원본 [spec_작업에이전트.md](spec_작업에이전트.md). 프롬프트 조각 종류 `workflow`(= `workflow.md` — 읽기만)를 더했다(② §3).

## ② 확정 사양

### 1. 에이전트 등록부 (`app/agents.py` `AGENTS`)

- 에이전트 하나 = 코드 등록값: `id` · **작업 번호**(기본) · 묶음 · 이름 · 역할 글 · 쓰는 곳 · 도는 때(눌러야 돎 | 저절로 돌기도 함) · 코드가 정한 모델·생각 깊이 · **계약**(코드의 `CONTRACT` — 모듈·이름) ·
  프롬프트에 붙는 글(지침 · 스킬 · 할 일 프롬프트 · 양식 정보 · 표 지침) · 자료 설명. 차례 = 화면 차례.
- **새 LLM 호출을 만들면** `agents.AGENTS` 와 `agent_settings.PREFIX`(호출 이름 첫머리 → 에이전트 id)에 한 줄씩 더한다 — 시험 `test_every_llm_call_label_in_the_code_has_an_agent` 가 코드의 호출 이름을 모아 등록 안 된 것이 있으면 떨어진다.

| 작업 번호 | id | 묶음 | 이름 | 쓰는 곳 | 호출 이름 | 코드의 모델 · 생각 깊이 | 붙는 글 | 기능 사양 |
|---|---|---|---|---|---|---|---|---|
| 01 | `heading_rules` | 헤딩 추출 | 레터 규칙식 제안 | 1단계 「추출(LLM)」 — 규칙 보강 | `heading_rules#n` | — · low | 헤딩 지침 rules | [spec_헤딩_추출.md](spec_헤딩_추출.md) ② §3 |
| 02 | `heading_types` | 헤딩 추출 | 헤딩 유형 판정 (A) | 2단계 「헤딩 그래프(LLM)」 A 호출 | `heading_types` | — · medium | 헤딩 지침 graph·templates·tolerance · 양식 정보 | 같은 사양서 ② §6 |
| 03 | `heading_section` | 헤딩 추출 | 구간 그래프 검토 (B) | 2단계 B 호출(구간마다) | `heading_section#n` | — · medium | graph·templates · 양식 정보 | ② §6 |
| 04 | `heading_formats` | 헤딩 추출 | 서식 조정 판정 (C) | 2단계 C 호출(서식 쌍 묶음마다) | `heading_formats#n` | — · low | templates·tolerance | ② §6 |
| 05 | `heading_review` | 헤딩 추출 | 조정 재검토 (D) | 2단계 D 호출(C 뒤) | `heading_review#n` | — · medium | templates·tolerance | ② §6 「재검토(D 호출)」 |
| 06 | `heading_tables` | 헤딩 추출 | 표 구조 판정 | 3단계 「표 구조(LLM)」 | `heading_tables#n` | — · medium | tables·tolerance · 양식 정보 | ② §8 |
| 07 | `div_review` | 프로젝트 구성 | 구분 기준 자리 재검토 | 구분 기준 「LLM 검토」 · 「LLM 재검토」 — 옵션(저절로 돌지 않음 — 2026-11-15) | `divisions-llm` | — · medium | 양식 정보 | [spec_구분_기준.md](spec_구분_기준.md) ② §14 |
| 08 | `div_missing` | 프로젝트 구성 | 빠진 구분 기준 자리 검토 | 「LLM 검토」 · 「빠진 자리 검토(LLM)」 — 옵션(저절로 돌지 않음 — 2026-11-15) | `divisions-missing` | — · medium | 양식 정보 | 같은 사양서 ② §13 |
| 09 | `merge_links` | 이관 · 취합 | 자리 연결 검토 | TASK 이관 2단계 「자리 연결 LLM 검토」 | `merge-llm`·`merge-llm-n` | Opus 5.5 · medium | 판단 지침 links · 할 일 plan_to_report · 양식 정보 | [spec_병합.md](spec_병합.md) ② §4 |
| 10 | `merge_table_map` | 이관 · 취합 | 표 대응 연결 | TASK 이관 2단계 「표 대응 연결」 | `merge-table-map-n` | Opus 5.5 · medium | 판단 지침 table_map · 할 일 plan_to_report | 같은 사양서 |
| 11 | `merge_gaps` | 이관 · 취합 | 빈 자리 검토 | TASK 이관 2단계 「빈 자리 검토(LLM)」 | `merge-gaps-n` | Opus 5.5 · medium | 판단 지침 gaps · 할 일 plan_to_report | 같은 사양서 |
| 12 | `gather` | 이관 · 취합 | 취합 검토 | TASK 취합 「기관 작성 내용」 LLM 검토 | `gather-llm-n` | Opus 5.5 · medium | 판단 지침 gather · 할 일 plan_merge | [spec_취합.md](spec_취합.md) |
| 13 | `table_formula` | 표 | 표 수식 판정 | 엑셀식 보기 「LLM 수식 판정」 | `table-formula` | — · 서버 기본 | 표 지침 | [spec_헤딩_추출.md](spec_헤딩_추출.md) ② §14 |
| 14 | `table_fill` | 표 | 표 채우기 | 표 메뉴 「에이전트로 표 채우기」 · 에이전트 보기 | `table-fill` | — · 서버 기본 | 표 지침·작성요령 · 할 일(작업의 TASK) | 같은 사양서 ② §18 |
| 15 | `table_make` | 표 | 표 만들기 · 서식 변환 | 「표 만들기·서식 변환」 「LLM 정리」 | `table-make-…` | — · 서버 기본 | 표 지침 | 같은 사양서 ② §11 |
| 16 | `doc_agent` | 문서 편집 | 문서 에이전트 | 에이전트 보기 — 요청마다 | `doc-agent` | — · 서버 기본 | 판단 지침 agent · 할 일(작업의 TASK) | [spec_일반편집.md](spec_일반편집.md) ② §8 |
| 17 | `style_review` | 서식 | 서식 복사 검토 | TASK 문서 서식 복사 「② LLM 검토」 | `style-review-…` | — · 서버 기본 | 할 일 style_copy(계약은 후보 종류마다 셋) | [spec_서식복사.md](spec_서식복사.md) ② §15 |
| 18 | `tpl_agent` | 서식 | 템플릿 서식 정리 | 템플릿 트리의 별 아이콘 | `tpl-agent` | **Opus 5.5 고정** · medium | 스킬(고른 것 하나) | [spec_hwpx_웹편집.md](spec_hwpx_웹편집.md) ② §8-4 |
| 19 | `work_guide` | 문서 편집 | 작업 진행 | 에이전트 보기 · 첫 화면 대화창 — TASK 시작 · 글 · 카드의 답 · 행동의 결과 | `work-guide` | — · low | 워크플로우(`workflow.md` 의 그 TASK 절) · 할 일(작업의 TASK) — 계약 둘(작업 화면 · 첫 화면) | [spec_작업에이전트.md](spec_작업에이전트.md) ② §2 |

### 2. 사용자 설정 (`app/agent_settings.py` — `agents.json`)

- 파일 `%LOCALAPPDATA%\NewFileManager\agents.json`(env `NFM_AGENTS` = 파일 경로 · `off`·`0` 이면 메모리만 — 시험은 conftest 가 시험마다 임시 파일) = `{version, updated, agents: {id: {no?, role?, model?, effort?}}}`.
  없는 키 = 기본(등록값). **이 PC 의 모든 문서가 같이 쓴다**(문서·작업과 무관). 고친 시각으로 다시 읽는다 · 깨진 파일은 빈 설정으로 읽고 다음 저장 때 새로 쓴다 · 모르는 id·키는 버린다.
- 고칠 수 있는 것: **작업 번호** `no`(글자·숫자로 시작 · 12자 · 글자·숫자·`.`·`_`·`-` · 다른 에이전트의 번호(고친 것이든 기본이든)와 겹치면 거절) · **역할 글** `role`(600자 — 사람이 읽는 설명, LLM 에 안 간다) ·
  **모델** `model`(화면은 Fable 5.2 · Opus 5.5 · Sonnet 5.5 · Haiku 5.5 가운데 — 저장은 모델 id 꼴이면 됨) · **생각 깊이** `effort`(low · medium · high · xhigh · max). 빈 값·null = 그 값을 지워 기본으로 · 기본과 같은 번호·역할은 따로 적지 않는다.
  저장마다 `version` +1(옛 판을 든 저장은 409).
- **모델·생각 깊이의 차례**(`llm.call` — 뒤가 이긴다): env 기본(`NFM_LLM_MODEL`) → 호출이 준 값(코드) → 서버 전체 설정 `NFM_LLM_MODEL_FORCE`(고정 `pin` 호출은 건너뜀 — 템플릿 서식 정리) → **이 설정에서 그 에이전트에 사람이 정한 값**.
  `llm.call` 이 호출 이름(`what`)의 첫머리로 에이전트를 찾는다(`agent_settings.override` — 긴 첫머리부터 · 등록 안 된 호출은 설정 없음). 설정을 못 읽어도 호출은 기본값으로 돈다.
  화면에 보이는 「지금 부르는 모델」 의 출처 = `user`(여기서 정함) · `pin`(이 에이전트에 고정) · `force`(서버 전체 설정) · `code`(코드가 정함) · `default`(서버 기본).

### 3. API (`app/agents_api.py`)

| 끝점 | 몸 | 답 |
|---|---|---|
| `GET /api/agents` | — | `{version, groups, models, efforts, llm{backend, active, available, model, forced}, agents[{id, no, noDefault, group, name, role, roleDefault, where, run, runText, model{id, source}, modelCode, pin, effort{id, source}, effortCode, custom[고친 키], user{…}, whats, runs, fails, last}]}` — 프롬프트 글 없음 |
| `GET /api/agents/{id}` | — | 위 한 줄 + `version` · `prompt[{kind, title, source, editable, text, note, …}]` · `recent`(그 에이전트의 최근 실행 30). 404 없는 에이전트 |
| `PUT /api/agents/{id}` | `{no?, role?, model?, effort?, version?}` | 그 에이전트(GET 꼴). 400 꼴·겹치는 작업 번호 · 404 · 409 판 어긋남 · 503 파일 저장 실패 |
| `GET /api/agents/runs` | `?agent=&limit=` | `{runs[{n, t, agent, what, model, effort, backend, ms, costUsd, error, ok}]}`(새 것부터) |

- `prompt` 의 조각(**보내는 글의 차례**): `contract`(계약 — 코드, 읽기만: 서식 복사 검토는 후보 종류마다 셋) → `heading`(헤딩 지침 — 고침: `api` = `/api/headings/guides/{이름}` PUT `{text, version}` · DELETE = 기본본으로) ·
  `merge`(병합 판단 지침 — 저장소 파일, 읽기만 + 경로) · `job`(할 일 프롬프트 — 저장소 파일, 읽기만: 「작업의 TASK」 인 에이전트는 있는 것 모두) · `form`(양식 정보 — 안내만: 문서의 양식마다) · `table`(표 지침·작성요령 — 안내만: 문서·표마다) ·
  `skill`(템플릿 정리 스킬 — 고침: `api` = `/api/outline/agent/skills/{키}` PUT `{name, text, version}` · DELETE) · `workflow`(워크플로우 `workflow.md` — 등록부에서 만든 글, 읽기만: 작업 진행 에이전트) → `data`(자료 — 스크립트가 만드는 것의 설명).

### 4. 실행 기록 (`agent_settings.record`·`runs`·`tally`)

- **모든** `llm.call` 의 결과 한 줄을 메모리 고리(최근 300)에 남긴다: **실행 번호** `n`(서버를 켠 뒤 1부터 — 모든 에이전트가 함께 쓰는 차례) · 시각 · 에이전트 id(등록 안 된 호출은 null) · 호출 이름 · 모델 · 생각 깊이 · 길 · 걸린 시간 · 비용(길이 돌려줄 때만) · 오류 · 성공 여부.
  LLM 이 꺼져 있거나(off) 자리가 없어(busy) 안 부른 것도 남는다. 파일에는 안 남긴다 — 서버를 다시 켜면 비워진다(문서마다의 기록은 그 작업의 `log.jsonl` 이 원본).
- 목록의 에이전트마다 `runs`(켠 뒤 호출 수) · `fails` · `last`(마지막 실행).

### 5. 화면 — 따로 선 페이지 `/agents` (`app/static/agents.html` · `agents.js` · `agents.css` — 상단 바 `a#agentsLink`)

2026-11-15 사용자 "에이전트도 워크플로우 처럼 페이지로 해줘" 로 다시 씀 — 전에는 문서 옆 열(2열 kind `agents` · 상단 바 단추 `#agentsBtn`)이었다. 열은 없앴다(설정을 고치는 곳은 이 페이지 하나).

- **여는 곳 = 상단 바 오른쪽 끝의 링크 「에이전트 설정」**(`a#agentsLink.btn.ags-link` — `href="/agents"` · 새 탭(`target="_blank"` — 연 문서를 닫지 않는다) · `header.topbar` 의 직계 `.btn`, 「워크플로우」 다음 · 「도구 닫기」 앞 · 별+톱니 아이콘 18px(보라)).
  문서가 없어도(시작 화면) 보인다. **어느 폭에서나 글 없이 아이콘만**(이름은 `title`·`aria-label` — 2026-11-16 사용자 「이건 아이콘으로 하면 되지 않냐?」: 원본 [spec_hwpx_웹편집.md](spec_hwpx_웹편집.md) ② §9 「상단 바 오른쪽 끝 아이콘」. 전에는 아이콘 + 글 · 1500px 아래에서만 아이콘). **541~780px 에서는 감춘다** — 문서를 연 상단 바는 꺾이지 않는 한 줄(35px)이고 그 폭에서는 이 링크가 없어도 710px 아래에서 줄이 넘친다(더 키우지 않는다) ·
  540px 아래(두 줄로 꺾이는 폭)에서는 다시 보인다. 규칙은 `document_header.css` 의 상단 바 절(워크플로우 링크 다음). 링크라 JS 가 없다 — `index.html` 은 `agents.js`·`agents.css` 를 읽지 않는다.
- **페이지** `GET /agents`(`app/agents_api.py` — `agents.html` 의 `style.css`·`agents.css`·`agents.js` 주소에 수정 시각 `?v=` 를 붙인다 · `Cache-Control: no-cache`: 워크플로우 페이지와 같은 규칙). 문서·작업과 무관하다(LLM 연결이 없어도 열린다).
  틀 = 워크플로우 페이지와 같다: **상단 줄**(로고 = 시작 화면으로 · 제목 「에이전트 설정」 · 「에이전트 18개」 · LLM 칩 · 「워크플로우」 링크) + **[왼쪽 목차 248px | 본문(혼자 스크롤)]**. 900px 아래에서는 목차가 본문 위의 가로 줄.
- **주소**: `#overview`(전체 보기 — 기본) · `#runs`(실행 기록) · `#<에이전트 id>`(한 에이전트 — 예 `/agents#merge_links`). 모르는 id 는 전체 보기. 에이전트 id 는 `overview`·`runs` 를 쓰지 않는다(시험이 본다).
- **목차**: 「전체 보기」 · 「실행 기록」 · 묶음 이름 아래 에이전트 줄 [작업 번호] 이름 — 고친 것이 있는 에이전트는 「고침」, 저장 안 한 값이 있는 에이전트는 주황 「저장 안 됨」(글로 — 색만으로 가르지 않는다). 지금 보는 곳 = `aria-current`.
- **전체 보기**: LLM 칩(「연결 API · 모든 에이전트 Fable 5.2」 | 「연결 API · 기본 Opus 5.5」 | 주황 「LLM 꺼짐」)은 상단 줄. 몸 = 묶음마다(「헤딩 추출 6」 …) 에이전트 줄(1px 선으로 나눈 한 상자) —
  넓은 폭에서는 네 칸 [작업 번호] | **이름** · 모델 칩(여기서 정함 = 파랑 · 이 에이전트에 고정 = 보라 · 그 밖 = 회색) · 생각 깊이 · 「고침」 + 「마지막 실행 #3 · 11/15 14:02 · 19.0초 · 켠 뒤 2번」 | 쓰는 곳 | 역할(두 줄까지), 900px 아래에서는 한 칸으로 쌓인다. 줄(링크)을 누르면 그 에이전트.
- **한 에이전트**(「‹ 전체 보기」 · 머리 = [작업 번호] 이름 · 묶음 · 도는 때): 넓은 폭(1100px 위)에서는 **두 단** — 왼쪽 = 설정, 오른쪽 = 프롬프트 · 최근 실행.
  ① 작업 — 번호 칸 · 쓰는 곳 · 호출 이름 ② 역할 — 글 칸 ③ 모델 · 생각 깊이 — 고르기 둘(첫 항목 「따로 정하지 않음 — 지금 Fable 5.2(서버 전체 설정)」) + 「지금 …」 한 줄. 절마다 한두 줄 설명 글(넓은 페이지라 노트 도움말 단추 대신 글로 보인다).
  ①②③ 은 **저장 줄 하나**(높이 고정): 「기본값 그대로」/「저장됨 — 고친 것: …」/주황 「고침 — 저장 안 됨」 + 「저장」 · 「고친 것 버리기」 · 「모두 기본으로」(줄 안에서 두 번). **저장 안 한 값은 에이전트마다 기억한다** — 다른 에이전트·전체 보기로 갔다 와도 남고(목차에 「저장 안 됨」), 페이지를 닫으면 버린다(묻는 창 없음).
  ④ 프롬프트 — 보내는 글의 차례: 조각마다 접는 줄 [차례] **이름** · 출처 · 글자 수 · 꼬리표(「읽기만」/「고칠 수 있음」/「고침」) → 펼치면 안내 글 + 글(읽기 전용 칸). 고칠 수 있는 조각(헤딩 지침 · 스킬 — 왼쪽 보라 띠)은 「고치기」 → 그 자리에서 고쳐 「저장」(그 글의 저장소에 — 다음 실행부터) ·
  「기본으로 되돌리기」(두 번) · 「내 사본 · 판 n」. ⑤ 최근 실행 — 표(실행 번호 · 시각 · 모델·생각 깊이 · 시간 · 결과).
- **실행 기록**(모든 에이전트): 같은 표 + 에이전트 칸(「18 템플릿 서식 정리」 — 누르면 그 에이전트) · 「다시 읽기」.
- 헤딩 지침을 여기서 고치면 헤딩 추출의 지침 편집 열과 같은 저장소라 그쪽에도 「내 사본」 으로 보인다. 문서 화면과는 다른 탭이라 문서를 열고 닫는 것과 무관하다.
- **워크플로우 페이지에서**: 단계 세부의 「에이전트」 이름이 `/agents#<id>` 링크다(`workflow.js`) — 그 에이전트의 설정으로 바로 간다. 이 페이지의 상단 줄 「워크플로우」 는 `/workflow` 로 간다.
- 화면 글·클래스: 페이지의 클래스는 모두 `ags-`·`agp-` 로 시작한다(`style.css` 가 함께 읽혀 앱의 규칙에 걸리지 않게). `agents.js` 는 `app.js` 없이 혼자 돈다(작은 도우미 `api`·`toast`·`el` 을 제 안에 둔다).

## ③ 구현 상태

- 2026-11-15 **② §5 페이지로 옮김 — 구현 끝**(newfilemanager-b8): 새 `app/static/agents.html` · `agents.js`·`agents.css` 를 페이지용으로 다시 씀(`app.js` 의 도우미 없이 혼자 돎 · 주소 `#overview`·`#runs`·`#<id>` · 저장 안 한 값 기억 · 두 단) ·
  `app/agents_api.py` 에 `GET /agents`(파일 주소에 `?v=`) · `index.html` 의 단추 `#agentsBtn` → 링크 `a#agentsLink`, `agents.css`·`agents.js` 읽기 줄을 뺌 · `document_header.css` 에 링크 규칙 넷(폭 규칙은 전과 같다) ·
  `workflow.js`·`workflow.css` 의 에이전트 이름 링크(`/agents#<id>`). 문서 옆 열(2열 kind `agents`)의 코드는 없앴다. API · 등록부 · 설정 파일은 그대로.
  시험: `tests/test_agents.py` 9개(새 `test_page_and_the_start_page_link`) · `tests/test_workflow.py` 9개 통과. 화면 검사 `tools/run_ui_gates.py` 로 함께 — `agents` 27(다시 씀: 링크 · 페이지 · 목차 · 주소 · 저장 안 한 값 · 좁은 폭 · 상단 바 폭) ·
  `workflow` 36 · `panel_head` 44 통과(그림 `artifacts/agents_page_2026-11-15/agents/01~06`).
  8114 재시작(같은 날 — 물어서 받은 답 「지금 재시작」): 띄우개째 끄고 1개만 다시 → `api · claude-fable-5-2 · available true` · `/agents` 200. 그 뒤 에이전트 19(`work_guide`)를 더하고 한 번 더 다시 켬(11-16 — [spec_작업에이전트.md](spec_작업에이전트.md) ③).
- 2026-11-15 **② 전부 — 구현 끝**(newfilemanager-cf): 새 `app/agent_settings.py`(설정 파일 · 호출 이름 → 에이전트 · override · 실행 기록) · `app/agents.py`(등록부 18 · 프롬프트 조각 · 모델 출처 · update) · `app/agents_api.py`(끝점 넷) ·
  `app/llm.py`(`call` = `_call` + 기록 · 에이전트 설정의 모델·생각 깊이를 맨 뒤에 적용) · `app/tpl_agent.py` `status()`(설정한 모델을 반영) · `app/server.py` include 한 줄 · `tests/conftest.py`(`NFM_AGENTS` 를 시험마다 임시 파일) ·
  화면 새 `agents.js`·`agents.css` · `index.html`(상단 바 단추 · link · script).
  시험 새 `tests/test_agents.py` 8개(코드의 모든 호출 이름이 등록됨 · 18개의 역할·쓰는 곳·프롬프트 차례 · 강제 모델 표시 · 번호·역할·모델·생각 깊이 저장·겹침 거절·판·기본으로 · **설정한 모델이 강제·고정보다 먼저** · 실행 기록 · 깨진 파일 · 메모리 · API) —
  `test_tpl_agent.py` 12개와 함께 20개 통과. 화면 검사 새 `tools/smoke_agents_ui.py`(run_ui_gates 이름 `agents` — 21개: 임시 서버 · 끝점은 모두 진짜) 통과 · 같이 돌린 `tpl_agent` 31 · `panel_head` 44(상단 바 넘침·겹침 포함) · `workspace` 32 ·
  `outline_match` 16 · `agent` 78 · `home` 81 통과. `styles` 는 52/2 — 떨어진 둘은 이 일과 무관한 기존 것(서식 관리자 도구 줄의 단추가 셋인데 검사는 둘을 기대 — `style_lib.js`·검사 모두 HEAD 그대로).
  전체 pytest(`tools/run_pytest.py` — 501초): **1247 통과 · 12 실패** — 12개는 서식 복사 시험(`test_style_extract` 3 · `test_style_copy` 5 · `test_style_api` 4)이고 이 일 전에도, HEAD 를 내보낸 사본에서도 같은 12개다(무관). 한글·Word 묶음 69개 통과.
  같은 날 사용자 답 「지금 재시작」 으로 **8114 를 다시 켰다**: 그때 newfilemanager-b1 이 「서식 갈래를 다른 템플릿으로」(split) 서버 코드를 고치는 중이라 먼저 작업 트리로 `import app.server`(경로 159 — b1 의 split·unsplit 끝점 포함) ·
  `test_tpl_agent`·`test_outline_match`·`test_agents` 37개 통과를 확인하고 b1 에 「지금 코드가 함께 올라간다」 고 알린 뒤 → 띄우개째 끔 → 포트가 빈 뒤 1개만(WMI) · `/api/headings/llm` 200(api · claude-fable-5-2 · available) · 듣는 프로세스 1.
  8114 의 `GET /api/agents` = 에이전트 18 · 17개는 「Fable 5.2(서버 전체 설정)」 · 템플릿 서식 정리만 「Opus 5.5(이 에이전트에 고정)」 · 설정 파일은 아직 없음(아무것도 안 고침). 사용자 작업(`ce455d64bf44`)을 읽기만 하는 헤드리스로 단추 → 목록 18줄 → 작업 18 의 프롬프트 차례를 봄(콘솔 오류 0 ·
  그림 `artifacts/tpl_agent_2026-11-15/look/11·12`). 화면에서 값을 고쳐 저장하는 것은 임시 서버의 검사로만 봤다(8114 의 설정 파일은 사용자가 처음 고칠 때 생긴다).

## ④ 미결/후속

- 사용자 확인 대상(① 의 에이전트 판단 ⓐ~ⓔ): 가장 큰 것은 ⓑ 「작업번호」 를 **에이전트마다의 번호**로 읽은 것(쓰는 곳·실행 번호도 화면에 있음)과 ⓒ 에이전트마다 **모델·생각 깊이**를 고르게 한 것(요청 글에는 없음 — 「설정」 에서 읽음).
- 남은 것: ① 병합 판단 지침·할 일 프롬프트는 여기서 보기만 한다(저장소 파일이 원본 — 화면에서 고치게 하려면 「파일이 원본」 원칙을 바꾸는 결정이 먼저) · ② 양식 정보·표 지침은 안내 글뿐(문서마다 달라 이 화면에 글이 없다) ·
  ③ 실행 기록은 메모리(서버를 다시 켜면 비움 · 문서 이름이 없다) · ④ 에이전트를 끄는 설정(자동 실행 끔)은 없다 · ⑤ 541~780px 폭에서는 단추가 안 보인다(그 폭의 상단 바가 이미 넘친다 — 상단 바 전체를 손봐야 풀린다) ·
  ⑥ 모델을 바꿔도 그 에이전트의 프롬프트·시간 한도는 그대로다(작은 모델에서 답이 스키마에 안 맞으면 그 기능의 「실패」 로 보인다).
