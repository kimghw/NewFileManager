"""에이전트 등록부(spec_에이전트 ② §1) — 앱이 LLM 에 맡기는 일(에이전트) 하나하나가 **어떤 역할**을 하고 **어디서** 돌며 **무슨 프롬프트**로 도는지를 한곳에 적는다.
사용자 2026-11-15 "에이전트 설정을 만들고, 어떤 역할을 하고 프롬프트가 무엇인지 작업번호등을 관리할 수 있는 관리를 우측 상단에 배치해줘".

- `AGENTS` = 코드 등록값(차례 = 화면 차례): id · 작업 번호(기본) · 묶음 · 이름 · 역할 · 쓰는 곳 · 도는 때 · 코드가 정한 모델·생각 깊이 · 계약(코드의 CONTRACT — 답의 꼴과 한 몸이라 고칠 수 없음) ·
  프롬프트에 붙는 글들(parts — 지침·스킬·할 일 프롬프트·양식 정보·표 지침). 새 LLM 호출을 만들면 여기와 `agent_settings.PREFIX` 에 한 줄씩 더한다.
- 사용자가 고치는 것(`agent_settings` — `agents.json`): 작업 번호 · 역할 글 · 모델 · 생각 깊이. 프롬프트의 고칠 수 있는 글(헤딩 지침 · 템플릿 정리 스킬)은 제 저장소의 끝점으로 고친다.
- `listing()`(목록) · `detail(id)`(프롬프트 글 포함) · `update(id, patch)`(작업 번호가 다른 에이전트와 겹치면 ValueError)."""
import importlib
from pathlib import Path

from app import agent_settings as S
from app import llm

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("헤딩 추출", "프로젝트 구성", "이관 · 취합", "표", "문서 편집", "서식", "검증")
RUN = {"manual": "눌러야 돎", "auto": "저절로 돌기도 함"}
H = "app.heading_llm"

# parts 의 꼴: ("heading", 지침 이름) · ("merge", 지침 이름) · ("job", 할 일 키 | "*") · ("form",) · ("table",) · ("skill",) — 프롬프트에 붙는 차례대로
AGENTS = (
    dict(id="heading_rules", no="01", group="헤딩 추출", name="레터 규칙식 제안", run="manual", effort="low", contract=(H, "RULES_CONTRACT"), parts=(("heading", "rules"),),
         role="문단 첫머리의 레터(개요 기호·번호·라벨·안내 표지) 가운데 내장 규칙과 배운 규칙으로 판정하지 못한 묶음을 보고, 그것을 판정할 정규식 규칙을 제안합니다. 제안은 스크립트가 검증한 뒤에만 배운 규칙이 됩니다.",
         where="헤딩 추출 1단계 「추출(LLM)」 — 규칙 보강 · 2단계 「헤딩 그래프(LLM)」 이 그래프보다 먼저", data="내장·배운 규칙 목록 + 판정하지 못한 첫머리 묶음(묶음마다 견본 글)"),
    dict(id="heading_types", no="02", group="헤딩 추출", name="헤딩 유형 판정 (A)", run="manual", effort="medium", contract=(H, "TYPES_CONTRACT"), parts=(("heading", "graph"), ("heading", "templates"), ("heading", "tolerance"), ("form",)),
         role="스크립트가 헤딩 후보 문단을 꼴이 같은 것끼리 묶은 「유형」 마다 구실(헤딩·제목·구분 라벨·안내·헤딩 아님)과 개요 사슬에서의 자리를 정합니다. 이 판정으로 개요템플릿과 서브 템플릿이 만들어집니다.",
         where="헤딩 추출 2단계 「헤딩 그래프(LLM)」 — A 호출(한 번)", data="유형 표(유형마다 레터 꼴·서식·수·견본·앞뒤 유형) + 문서 요약"),
    dict(id="heading_section", no="03", group="헤딩 추출", name="구간 그래프 검토 (B)", run="manual", effort="medium", contract=(H, "SECTION_CONTRACT"), parts=(("heading", "graph"), ("heading", "templates"), ("form",)),
         role="A 판정과 부모 규칙으로 쌓은 초안 헤딩 그래프를 구간마다 읽고, 부모·레벨이 틀린 노드를 바로잡습니다(바꿀 노드와 까닭만 답하고 반영·검증은 스크립트).",
         where="헤딩 추출 2단계 「헤딩 그래프(LLM)」 — B 호출(구간마다)", data="구간의 노드 목록(레터·글·서식·지금 부모·레벨)"),
    dict(id="heading_formats", no="04", group="헤딩 추출", name="서식 조정 판정 (C)", run="manual", effort="low", contract=(H, "FORMAT_CONTRACT"), parts=(("heading", "templates"), ("heading", "tolerance")),
         role="같은 템플릿·같은 레벨인데 서식 라벨이 다른 쌍마다, 그 차이가 오차(같은 서식으로 통일할 것)인지 일부러 준 다름인지 판정합니다. 결과는 「조정」 목록이 됩니다.",
         where="헤딩 추출 2단계 「헤딩 그래프(LLM)」 — C 호출(서식 쌍 묶음마다). 기본 실행에서는 돌지 않습니다(서버 설정 NFM_HEADS_PAIRS=on 일 때만 — 같은 템플릿의 서식은 조정 층의 서식 정리 계획이 정합니다)", data="서식 쌍(두 서식의 값 · 다른 항목 · 견본 글)"),
    dict(id="heading_review", no="05", group="헤딩 추출", name="조정 재검토 (D)", run="manual", effort="medium", contract=(H, "REVIEW_CONTRACT"), parts=(("heading", "templates"), ("heading", "tolerance")),
         role="C 호출이 내린 서식 조정 판정을 다른 호출이 다시 봅니다. 동의하지 않으면 「재검토 불일치」 로 남겨 사람이 확인하게 합니다.",
         where="헤딩 추출 2단계 「헤딩 그래프(LLM)」 — D 호출(C 뒤). 기본 실행에서는 돌지 않습니다(C 와 함께 — 서버 설정 NFM_HEADS_PAIRS=on 일 때만)", data="C 가 판정한 서식 쌍과 그 판정·까닭"),
    dict(id="heading_tables", no="06", group="헤딩 추출", name="표 구조 판정", run="manual", effort="medium", contract=(H, "TABLES_CONTRACT"), parts=(("heading", "tables"), ("heading", "tolerance"), ("form",)),
         role="표마다 칸의 역할(열헤더·행헤더·귀퉁이·필드·제목·안내·간격)과 서브 테이블 나눔을 스크립트 초안과 견줘 판정합니다. 없는 칸·모르는 역할은 스크립트가 거릅니다.",
         where="헤딩 추출 3단계 「표 구조(LLM)」 — 표 묶음마다", data="표의 격자(행마다 칸 토큰) + 스크립트 초안"),
    dict(id="div_review", no="07", group="프로젝트 구성", name="구분 기준 자리 재검토", run="manual", effort="medium", contract=("app.division_llm", "CONTRACT"), parts=(("form",),),
         role="스크립트가 찾은 구분 기준 자리(단계·차년도·기관이 되풀이되는 절·표 행·표 열)가 맞는지 재검토합니다 — 자리가 아닌 것, 기준이 다른 것, 형제가 빠진 것을 짚습니다.",
         where="프로젝트 구성(구분 기준) 「LLM 검토」 · 「LLM 재검토」 — 옵션(저절로 돌지 않음 · 이름 줄의 「구분 기준」 표시로도 엶)", data="자리 후보 목록(글·둘레 문맥·기준) + 문서의 구분 값"),
    dict(id="div_missing", no="08", group="프로젝트 구성", name="빠진 구분 기준 자리 검토", run="manual", effort="medium", contract=("app.division_llm", "MISSING_CONTRACT"), parts=(("form",),),
         role="스크립트가 자리로 잡지 못했지만 구분 기준이 되풀이되어야 할 곳(빠진 자리)을 문서에서 찾아 후보로 냅니다. 사람이 「자리로 추가」 해야 자리가 됩니다.",
         where="프로젝트 구성(구분 기준) 「LLM 검토」 · 「빠진 자리 검토(LLM)」 — 옵션(저절로 돌지 않음 · 2026-11-15 부터 첫 분석이 부르지 않는다)", data="문서 개요와 이미 잡힌 자리 목록"),
    dict(id="merge_links", no="09", group="이관 · 취합", name="자리 연결 검토", run="manual", effort="medium", contract=("app.merge_llm", "CONTRACT"), model=("app.merge_llm", "MODEL"), parts=(("merge", "links"), ("job", "plan_to_report"), ("form",)),
         role="사업계획서(원본 문서)의 내용을 연차보고서(목적 문서)에 옮길 때 어느 자리가 어느 자리인지 — 묶음 짝·표 짝·서식 — 를 스크립트가 잇지 못한 곳에서 판정합니다. 입력에 있는 key 만 고릅니다.",
         where="워크플로우 사업계획서 → 연차보고서 이관 · 3단계 내용 넣기 「자리 연결 LLM 검토」(쪽 묶음마다)", data="두 문서의 자리 목록(개요 경로·글머리·표 머리) + 스크립트가 이은 짝"),
    dict(id="merge_table_map", no="10", group="이관 · 취합", name="표 대응 연결", run="manual", effort="medium", contract=("app.merge_table_map", "CONTRACT"), model=("app.merge_table_map", "MODEL"), parts=(("merge", "table_map"), ("job", "plan_to_report")),
         role="서식이 서로 다른 원본 표와 목적 표 사이에서 어느 행·열·칸이 서로 같은 것인지 대응을 정합니다. 값은 옮기지 않고 대응만 답합니다.",
         where="워크플로우 이관 · 3단계 내용 넣기 「표 대응 연결」(표 쌍마다)", data="두 표의 격자와 머리 경로"),
    dict(id="merge_gaps", no="11", group="이관 · 취합", name="빈 자리 검토", run="manual", effort="medium", contract=("app.merge_gaps", "CONTRACT"), model=("app.merge_gaps", "MODEL"), parts=(("merge", "gaps"), ("job", "plan_to_report")),
         role="내용을 옮긴 뒤에도 빈 채로 남은 목적 문서의 자리마다, 원본 문서에서 그 자리에 들어갈 내용이 있는 곳을 찾습니다. 없으면 없다고 답합니다.",
         where="워크플로우 이관 · 3단계 내용 넣기 「빈 자리 검토(LLM)」", data="빈 자리 목록 + 원본 문서의 아직 안 쓴 자리"),
    dict(id="gather", no="12", group="이관 · 취합", name="취합 검토", run="manual", effort="medium", contract=("app.merge_gather_llm", "CONTRACT"), model=("app.merge_gather_llm", "MODEL"), parts=(("merge", "gather"), ("job", "plan_merge")),
         role="기관이 채워 돌려준 문서에서 스크립트가 취합본에 넣기로 한 「기관 작성 내용」 이 실제로 기관이 쓴 내용인지, 양식의 안내 글·빈 틀인지 판정합니다. 겹치는 자리는 덮지 않습니다.",
         where="워크플로우 사업계획서 취합 · 「기관 작성 내용」 LLM 검토(기관 문서마다)", data="기관 문서의 넣을 묶음(글·표) + 배포 기준본의 같은 자리"),
    dict(id="table_formula", no="13", group="표", name="표 수식 판정", run="manual", effort=None, contract=("app.table_excel_llm", "CONTRACT"), parts=(("table",),),
         role="표 하나를 엑셀 시트로 옮길 때 어느 칸이 다른 칸들로 계산되는 칸(합계·소계·비율)인지와 그 수식을 판정합니다. 계산·검산은 스크립트가 합니다.",
         where="표 메뉴 「엑셀식 보기」 — 「LLM 수식 판정」", data="표 격자(칸 주소·글·수) + 스크립트가 이미 찾은 수식"),
    dict(id="table_fill", no="14", group="표", name="표 채우기", run="manual", effort=None, contract=("app.table_fill", "CONTRACT"), parts=(("table",), ("job", "*")),
         role="받은 자료에서 값을 찾아 표의 빈 칸에 넣을 글을 제안합니다. 자료에 없는 값은 만들지 않고, 사람이 고른 칸만 문서에 들어갑니다.",
         where="표 메뉴 「에이전트로 표 채우기」 · 에이전트 보기의 표 채우기 제안", data="표의 빈 칸(행·열 머리 경로) + 작성요령 + 받은 자료"),
    dict(id="table_make", no="15", group="표", name="표 만들기 · 서식 변환", run="manual", effort=None, contract=("app.table_llm", "CONTRACT"), parts=(("table",),),
         role="글이나 다른 표를 고른 표 양식에 맞는 격자로 정리합니다. 괘선·음영·글자 모양은 양식에서 오고, 에이전트는 칸의 글과 배치만 답합니다.",
         where="도구 줄 「표 만들기 · 서식 변환」 — 「LLM 정리」", data="원본(글 또는 표 격자) + 고른 표 양식의 구조"),
    dict(id="doc_agent", no="16", group="문서 편집", name="문서 에이전트", run="manual", effort=None, contract=("app.doc_agent", "CONTRACT"), parts=(("merge", "agent"), ("job", "*")),
         role="사람의 요청과 받은 자료를 읽고 문서에 넣을 것(글 · 새 표 · 표 채우기 · 서식 입히기 · 서식 복사)을 제안하거나 물음에 답합니다. 제안은 스크립트 검사를 거쳐 사람이 고른 것만 반영됩니다.",
         where="에이전트 보기(상단 바 에이전트 아이콘의 창 · 패널 「에이전트」 탭에 넣었으면 그 탭) — 요청을 보낼 때마다", data="요청 · 고른 자리 · 문서 개요 · 받은 자료 · 서식 목록 · 앞선 대화"),
    dict(id="style_review", no="17", group="서식", name="서식 복사 검토", run="manual", effort=None, contract=("app.style_extract", "CONTRACT_TABLES"), parts=(("job", "style_copy"),),
         more=(("테이블 서식 후보", ("app.style_extract", "CONTRACT_TABLES")), ("내용·문단 서식 후보", ("app.style_extract", "CONTRACT_TEXTS")), ("쪽 설정·표지 후보", ("app.style_extract", "CONTRACT_PAGES"))),
         role="스크립트가 문서에서 뽑은 서식 후보(표지 · 내용 · 테이블 · 문단 · 쪽 설정)를 검토합니다 — 이름·역할·저장할 만한가. 서식 값은 만들지 않고 스크립트가 보낸 후보·id·코드 가운데 고릅니다.",
         where="워크플로우 문서 서식 복사 · 「② LLM 검토」(후보 종류마다 한 번씩)", data="후보 목록(종류마다 — 서식 요약 · 견본 글 · 쓰인 곳)"),
    dict(id="tpl_agent", no="18", group="서식", name="템플릿 서식 정리", run="manual", effort="medium", contract=("app.tpl_agent", "CONTRACT"), model=("app.tpl_agent", "MODEL"), pin=True, parts=(("skill",),),
         role="개요 템플릿 하나의 레벨마다 쓰인 서식을 보고 대표로 삼을 서식 · 그 대표에 맞출 서식 · 서식 종속 템플릿으로 뗄 서식 · 그대로 둘 서식을 정합니다(기본 스킬의 기준: 레터가 대표와 같으면 맞추고 다르면 뗌 · 표 안의 줄은 표마다 — 다른 표의 서식은 맞추지 않고 표마다 뗌). "
              "문서에 있는 서식 가운데 고르기만 하고, 계획은 사람이 반영해야 문서에 들어갑니다.",
         where="「헤딩 그래프(LLM)」 이 헤딩 판정 뒤에 이어서(템플릿마다) · 진행표의 「LLM 검증·보완」 · 헤딩 추출 탭 진행 줄 「조정」 의 「계획 받기」 · 템플릿 트리(헤딩 추출 「템플릿」 탭 · 「템플릿 관계」 열)의 별 아이콘 → 「정리 계획 받기」",
         data="템플릿의 레벨마다 쓰인 서식(값 · 줄 수 · 견본 글)"),
    dict(id="work_guide", no="19", group="문서 편집", name="작업 진행", run="manual", effort="low", contract=("app.work_guide", "CONTRACT"), parts=(("workflow",), ("taskdoc", "*"), ("job", "*"), ("logs",)),
         more=(("작업 화면(워크플로우 진행)", ("app.work_guide", "CONTRACT")), ("첫 화면(워크플로우 정하기)", ("app.work_guide", "HOME_CONTRACT"))),
         role="워크플로우를 시작하면 사전 준비와 진행 상황을 설명하고, 다음 단계를 제안하고, 입력이 필요하면 질문 카드로 묻습니다. 절차는 참조 글(workflow.md · 워크플로우 상세 문서 · 할 일 프롬프트)에서 확인하고, "
              "무슨 일이 있었는지는 로그(작업 기록 · 검증 · 에이전트 대화 · LLM 호출 · 서버 경고)를 읽어 설명합니다. 화면이 보낸 「지금 할 수 있는 행동」 가운데서만 고릅니다 — 실행은 화면이 하고, 문서를 바꾸는 행동은 사람이 카드에서 확인해야 실행됩니다.",
         where="에이전트 보기(상단 바 에이전트 아이콘의 창 · 패널 탭에 넣었으면 그 탭)와 첫 화면 오른쪽 대화창 — 워크플로우를 시작할 때 · 글을 보낼 때 · 카드에 답하거나 행동이 끝날 때",
         data="사건(시작 · 글 · 답 · 결과) · 워크플로우 · 단계의 지금 상태 · 지금 할 수 있는 행동 · 사실(프로젝트 구성 · 계획 요약) · 앞선 대화 · 로그(목록 · 작업 기록의 끝 몇 줄 · 에이전트가 청해 읽은 줄)"),
    dict(id="verify_review", no="20", group="검증", name="검증 LLM 검토", run="auto", effort="medium", contract=("app.verify_llm", "CONTRACT"), parts=(("merge", "verify"),),
         role="가져오기 검증 · 출력파일 검증에서 스크립트가 주의 · 실패로 판정한 단계를 다시 보고, 그 다름이 실제 문제(웹이 문서를 잘못 읽음 · 저장본이 잘못됨)인지 기준 PDF 쪽 사정(한글 · Word 가 PDF 를 찍는 방식)인지 가립니다. "
              "판정에 따라 그 단계의 상태를 바꾸되 스크립트보다 무겁게 올리지 않고, 스크립트의 원래 판정은 옆에 남깁니다.",
         where="검증 패널 — 가져오기 검증(올리면 저절로) · 출력파일 검증의 마지막 단계 「LLM 검토」: 주의 · 실패 단계가 있을 때만 저절로 돎",
         data="검증 단계마다 스크립트 판정 · 설명 · 단계가 남긴 자료(줄인 것 — 글꼴 판정의 PDF 글꼴 · 굵게 짝 포함) · 스크립트가 판정하지 못한 것 + 대상(주의 · 실패 단계)"),
    dict(id="zone_review", no="21", group="프로젝트 구성", name="편집 구역 검토", run="manual", effort="medium", contract=("app.zones_llm", "CONTRACT"), parts=(("merge", "zones"),),
         role="편집 구역(문서의 표·문단이 어느 기관 · 단계 · 차년도의 것인지)에서 스크립트가 값을 못 정했거나 근거가 서로 달랐던 표·문단을 다시 봅니다 — 기관 이름표 칸 옆의 이름 · 윗 제목 · 앞뒤 구역을 보고 그 기관·그 차년도의 것인지 가립니다. "
              "보낸 후보 · 보낸 기관 · 범위 안의 번호 가운데 고르기만 하고(근거가 약하면 그대로 둡니다), 고른 값은 「LLM 이 지정」 으로 적혀 사람이 하나씩 또는 모두 해제할 수 있습니다. 문서는 바뀌지 않고 사람이 지정한 구역도 바뀌지 않습니다.",
         where="패널 「작업 개요」 의 「편집 구역」 줄(취합에서는 취합 카드 안) — 「LLM 검토」 단추(저절로 돌지 않음 · 연구개발 워크플로우의 hwpx 문서)",
         data="과제 기관(열쇠 · 이름 · 역할) · 단계마다 차년도 수 + 후보(표·문단마다 종류 · 윗 제목 · 앞뒤 블록의 구역 · 스크립트가 읽은 값과 근거 · 표의 머리 줄·첫 열·이름표 칸과 그 옆 칸 — 줄인 글) · "
              "스크립트가 판정하지 못한 것 = 후보 자체(근거가 서로 다름 · 기관 모름 · 값이 안 붙었는데 낌새가 있는 표 · 같은 꼴의 이웃 표 가운데 혼자 빠진 표)"),
)
BY_ID = {a["id"]: a for a in AGENTS}
assert tuple(BY_ID) == S.IDS, "agents.AGENTS 와 agent_settings.PREFIX 의 에이전트가 다릅니다"

JOB_NAMES = {"plan_to_report": "사업계획서 → 연차보고서 이관", "plan_merge": "사업계획서 취합", "doc_edit": "문서 일반 편집", "style_copy": "문서 서식 복사"}


def _attr(ref):
    try:
        return getattr(importlib.import_module(ref[0]), ref[1])
    except Exception:  # noqa: BLE001 — 한 모듈이 안 열려도 목록은 보인다
        return None


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")
    except (ValueError, OSError):
        return str(path)


def model_of(a, user=None):
    """에이전트 a 가 지금 부를 모델 → {id, source}: user(여기서 정함) · pin(이 에이전트에 고정) · force(서버 전체 강제) · code(코드가 정함) · default(서버 기본)."""
    user = user if user is not None else S.get(a["id"]).get("model")
    code = _attr(a["model"]) if a.get("model") else None
    if user:
        return {"id": user, "source": "user"}
    if a.get("pin") and code:
        return {"id": code, "source": "pin"}
    if llm.forced():
        return {"id": llm.forced(), "source": "force"}
    if code:
        return {"id": code, "source": "code"}
    return {"id": llm.settings()["model"], "source": "default"}


def effort_of(a, user=None):
    user = user if user is not None else S.get(a["id"]).get("effort")
    if user:
        return {"id": user, "source": "user"}
    return {"id": a["effort"], "source": "code"} if a.get("effort") else {"id": llm.settings()["effort"], "source": "default"}


def _brief(a, own, tally):
    code = _attr(a["model"]) if a.get("model") else None
    t = tally.get(a["id"]) or {}
    return {"id": a["id"], "no": own.get("no") or a["no"], "noDefault": a["no"], "group": a["group"], "name": a["name"], "role": own.get("role") or a["role"], "roleDefault": a["role"],
            "where": a["where"], "run": a["run"], "runText": RUN[a["run"]], "model": model_of(a, own.get("model") or ""), "modelCode": code, "pin": bool(a.get("pin")),
            "effort": effort_of(a, own.get("effort") or ""), "effortCode": a.get("effort"), "custom": sorted(own), "user": {k: own.get(k) for k in ("no", "role", "model", "effort")},
            "whats": [p for p, i in S.PREFIX if i == a["id"]], "runs": t.get("runs", 0), "fails": t.get("fails", 0), "last": t.get("last")}


def listing():
    """{version, groups, models, efforts, llm{backend, model(서버 기본), forced, available, active}, agents[…]} — 프롬프트 글은 없다(detail)."""
    data, tally = S.load(), S.tally()
    st = llm.status()
    return {"version": data["version"], "groups": list(GROUPS), "models": list(S.MODELS), "efforts": list(S.EFFORTS),
            "llm": {"backend": st.get("backend"), "active": st.get("active"), "available": bool(st.get("available")), "model": llm.settings()["model"], "forced": llm.forced()},
            "agents": [_brief(a, data["agents"].get(a["id"]) or {}, tally) for a in AGENTS]}


def _parts(a):
    """프롬프트에 들어가는 글을 차례대로 [{kind, title, source, editable, text?, note?, …}] — 계약 → 붙는 글들 → 자료."""
    out = []
    for title, ref in (a.get("more") or ((None, a["contract"]),)):
        text = _attr(ref)
        out.append({"kind": "contract", "title": "계약" + (f" — {title}" if title else ""), "source": f"{ref[0].replace('.', '/')}.py · {ref[1]}", "editable": False, "text": text if isinstance(text, str) else "",
                    "note": "입력의 뜻 · 답의 꼴 · 지킬 것 — 답을 검증하는 코드와 한 몸이라 화면에서 고치지 않습니다"})
    for part in a["parts"]:
        kind = part[0]
        if kind == "heading":
            from app import heading_guides
            g = heading_guides.get(part[1])
            out.append({"kind": "heading", "name": part[1], "title": f"지침 — {g['title']}", "source": "헤딩 지침" + (" · 내 사본" if g["custom"] else " · 기본본"), "editable": True, "text": g["text"],
                        "custom": g["custom"], "version": g["version"], "defaultChanged": g["defaultChanged"], "api": f"/api/headings/guides/{part[1]}"})
        elif kind == "merge":
            from app import merge_guides
            g = merge_guides.get(part[1])
            out.append({"kind": "merge", "name": part[1], "title": f"판단 지침 — {g['title'] if g else part[1]}", "source": _rel(g["path"]) if g else f"app/merge_guides_default/{part[1]}.md(없음)", "editable": False,
                        "text": merge_guides.body(g) if g else "", "note": "저장소의 이 파일이 원본입니다 — 파일을 고치면 다음 실행부터 쓰입니다"})
        elif kind == "job":
            from app import job_prompts
            keys = list(JOB_NAMES) if part[1] == "*" else [part[1]]
            for k in keys:
                p = job_prompts.get(k)
                if p is None and part[1] == "*":
                    continue
                out.append({"kind": "job", "name": k, "title": f"할 일 프롬프트 — {(p or {}).get('name') or JOB_NAMES.get(k, k)}", "source": _rel(p["path"]) if p else f"jobs/{k}.md(없음)", "editable": False,
                            "text": job_prompts.body(p["text"]) if p else "", "note": ("작업의 워크플로우가 이것일 때만 붙습니다 · " if part[1] == "*" or len(keys) > 1 else "") + "저장소의 이 파일이 원본입니다(워크플로우의 전제·기준)"})
        elif kind == "workflow":
            from app import work_guide
            out.append({"kind": "workflow", "title": "워크플로우 전체 지도 — workflow.md", "source": "workflow.md", "editable": False, "text": work_guide.workflow_text(),
                        "note": "워크플로우 등록부(app/workflow.py)에서 만든 글입니다 — 부를 때 이 가운데 「한눈에」 와 그 워크플로우가 쓰는 도구의 절만 붙습니다(그 워크플로우의 절은 아래 워크플로우 상세 문서가 대신합니다 · 첫 화면은 「한눈에」 와 워크플로우마다의 머리 · 맨 위 「업무 흐름」 절은 사용자가 직접 쓴 글이고 붙지 않습니다)"})
        elif kind == "taskdoc":   # 참조 글 — 그 TASK 의 TASK 문서(tasks/<job>.md: 시작 점검 · 단계마다 조건 — spec_워크플로우 ② §10 · spec_작업에이전트 ② §8)
            from app import work_guide, workflow
            cat = workflow.catalog()[0]
            for t in workflow.TASKS:
                out.append({"kind": "taskdoc", "name": t["job"], "title": f"워크플로우 상세 문서 — {(cat.get(t['job']) or {}).get('name') or t['job']}", "source": f"{workflow.TASK_DIR.name}/{t['job']}.md", "editable": False,
                            "text": work_guide.task_doc_text(t["job"]),
                            "note": "작업의 워크플로우가 이것일 때만 붙습니다(작업 화면) · 워크플로우 등록부에서 만든 글입니다 — 그 워크플로우의 절(머리 · 단계)에 시작 점검(시작할 때 저절로 확인하는 것)과 단계마다 조건을 더한 글"})
        elif kind == "logs":      # 로그 — 글이 아니라 읽을 수 있는 기록의 목록(spec_작업에이전트 ② §8)
            from app import work_logs
            out.append({"kind": "logs", "title": "로그 — 문서마다", "source": "app/work_logs.py", "editable": False,
                        "text": "\n".join(f"- {name} · {title} — {what}" for name, title, what in work_logs.SOURCES),
                        "note": "자료에 로그의 목록과 작업 기록의 끝 몇 줄이 늘 실리고, 더 봐야 하면 에이전트가 답의 read 로 청해 읽습니다(한 턴에 두 번까지 · 한 번에 80줄까지) — 문서와 기록은 바뀌지 않습니다"})
        elif kind == "form":
            out.append({"kind": "form", "title": "양식 정보 — 문서의 양식마다", "source": "forms/<양식>.md", "editable": False, "text": "",
                        "note": "문서가 아는 양식(연구개발계획서 · 연차보고서 …)일 때 그 양식의 글이 한 절로 붙습니다 — 헤딩 추출 「추출·설정」 의 「양식 정보」 에서 보고 고칩니다"})
        elif kind == "table":
            out.append({"kind": "table", "title": "표 지침 · 작성요령 — 문서·표마다", "source": "작업에 저장", "editable": False, "text": "",
                        "note": "표 손잡이의 연필 아이콘(작성요령 · 표 지침)에서 공통 지침과 그 표의 지침을 적습니다 — 문서마다 저장되고 그 표를 부를 때 붙습니다"})
        elif kind == "skill":
            from app import tpl_agent
            for s in tpl_agent.skills():
                sk = tpl_agent.skill(s["key"])
                out.append({"kind": "skill", "name": sk["key"], "title": f"스킬 — {sk['name']}", "source": ("기본 스킬" if sk["builtin"] else "내 스킬") + (" · 고침" if sk["builtin"] and sk["custom"] else ""), "editable": True,
                            "text": sk["text"], "custom": sk["custom"], "builtin": sk["builtin"], "version": sk["version"], "skillName": sk["name"], "api": f"/api/outline/agent/skills/{sk['key']}",
                            "note": "부를 때 고른 스킬 하나가 붙습니다 — 새 스킬은 「템플릿 서식 정리」 열에서 만듭니다"})
    out.append({"kind": "data", "title": "자료 (JSON)", "source": "스크립트가 만듦", "editable": False, "text": "", "note": a["data"]})
    return out


def detail(aid):
    """목록의 한 줄 + prompt[…](글 포함) · runs(이 에이전트의 최근 실행 30). 없는 id 는 KeyError."""
    a = BY_ID[aid]
    data = S.load()
    return {**_brief(a, data["agents"].get(aid) or {}, S.tally()), "version": data["version"], "prompt": _parts(a), "recent": S.runs(aid, 30)}


def update(aid, patch, expect=None):
    """작업 번호 · 역할 · 모델 · 생각 깊이를 고친다(None·"" = 기본으로) → detail(aid). 작업 번호가 다른 에이전트의 것과 같으면 ValueError · 없는 id 는 KeyError."""
    a = BY_ID[aid]
    clean = S.check(patch)
    if clean.get("no"):
        data = S.load()["agents"]
        for other in AGENTS:
            if other["id"] != aid and ((data.get(other["id"]) or {}).get("no") or other["no"]) == clean["no"]:
                raise ValueError(f"작업 번호 「{clean['no']}」 는 「{other['name']}」 이 쓰고 있습니다")
    if clean.get("no") == a["no"]:
        clean["no"] = None   # 기본 번호와 같으면 따로 적지 않는다
    if clean.get("role") == a["role"]:
        clean["role"] = None
    S.save(aid, clean, expect)
    return detail(aid)
