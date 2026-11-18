"""화면 검사(임시 서버를 스스로 띄우는 tools/smoke_*_ui.py)를 **한꺼번에** 돌린다 — 검사마다 다른 포트·다른 폴더라 서로 안 겹친다(8114 는 안 건드림).

    python -X utf8 tools/run_ui_gates.py <그림·임시 폴더> [검사 이름 …] [--all] [--jobs 5] [--no-retry] [--list] [--timeout 900]

이름을 안 주면 기본 묶음(아래 GATES 의 기본 = True). 차례로 돌리면 걸린 시간의 합만큼 기다리지만, 같이 돌리면 가장 긴 검사만큼만 기다린다.
같이 돌 때의 부하로 떨어진 것인지 가르려고 **떨어진 검사는 끝난 뒤 혼자 한 번 더** 돌린다(--no-retry 로 끔). 끝에 검사마다 통과 수·걸린 시간과 전체 시간(차례로 돌렸다면 = 합)을 보이고,
쓴 포트에 듣는 프로세스가 남았는지 본다(임시 서버는 검사가 끝나면 꺼져 있어야 한다 — CLAUDE.md 「웹서버」). 하나라도 떨어지면 종료 코드 1."""
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 이름: (스크립트, 기본 묶음에 드나, 한마디). 모두 「<폴더> --port <포트>」 꼴 — 서버 주소를 받는 검사(smoke_commits_ui.py 등)는 여기 없다(서버를 따로 띄워야 함)
GATES = {
    "project": ("smoke_project_ui.py", False, "프로젝트 · TASK · 라운드 · 참고 파일 격리"),
    "workspace": ("smoke_workspace_ui.py", False, "문서 위 공용 도구행 · 파일명 행"),
    "task": ("smoke_task_ui.py", True, "작업 종류 · 이관 단계 · 연결 목록 · 넣기 계획"),
    "task_run": ("smoke_task_run_ui.py", True, "1단계 문서 프레임 작성 · 한 번에 진행(실제 서식 쌍)"),
    "panel_head": ("smoke_panel_head_ui.py", True, "패널 머리 — 작업 목록 · 도구 이름 줄"),
    "peer": ("smoke_peer_ui.py", True, "같이 보기 — 두 면"),
    "peer_follow": ("smoke_peer_follow_ui.py", True, "같이 보기 — 누른 자리 따라 보기(원본 자리 지도는 흉내)"),
    "gather": ("smoke_gather_ui.py", True, "취합 — 기관 문서 줄 · 배포 기준본 · 기관 작성 내용 · 넣기 계획 · 끌어 넣기 · 한 번에 진행(끝점은 흉내)"),
    "zones": ("smoke_zones_ui.py", True, "편집 구역 — 「작업 내용」 의 줄(체크 셋 = TASK 옵션 · 「구역 표시」 보기/감추기 · 칩) · 문서의 띠·오른쪽 여백 이름표 · 이름 줄 색 설명 · 「구역 지정…」(떠 있는 입력 · 고치기 · 해제 · 표 칸 = 표) · 목록 · 편집 뒤 다시 읽기 · 새로 고침 · 배율 · 옵션 409(진짜 끝점)"),
    "over": ("smoke_over_ui.py", True, "넘친 개요 레벨 — 넣기 계획의 절 · 처리 셋(덮은 템플릿 그대로 · 템플릿 수정 · 다른 템플릿) · 넣은 줄에 다시 맞추기(이관·취합 — 끝점은 흉내)"),
    "gather_quick": ("smoke_gather_quick_ui.py", True, "취합 간단 모드 — 시작 화면 목록에서 목적 문서 고르기 → 자동 진행이면 끝까지(진짜 끝점) · 끄면 올리고 등록만"),
    "home_files": ("smoke_home_files_ui.py", True, "시작 화면 문서 목록 — 모아 두기 · 목적 문서 · 별칭 · TASK 없이 열기 · 이관 두 문서 · 양식 표준화"),
    "first_run": ("smoke_first_run_ui.py", True, "첫 분석(헤딩 · 표 스크립트만 — 구분 기준 LLM 검토는 안 부름) · 구분 기준 LLM 검토 취합"),
    "doc_status": ("smoke_doc_status_ui.py", True, "분석 상태 — 문서 이름 줄의 「헤딩 · 템플릿 · 서식 · 표 · LLM · 구분 기준」 표시(없음 → 「분석」 → ✓ · 누르면 진행표 → 칸은 그 도구로 · 「LLM 검증·보완」(LLM 끔 → 멈춤) · 도는 중 · docx · 구분 기준 옵션 · 좁은 폭 · 둘째 면 머리)"),
    "heading_progress": ("smoke_heading_progress_ui.py", True, "헤딩 추출 진행 줄 — 스크립트(문단·라벨 · 헤딩 그래프 · 표 구조) · LLM(규칙 보강 · 헤딩 판정 · 표 판정) 두 층 · 누르면 그 단계 탭 · 1단계 카드 · 흉내 낸 상태(끝남 · 도는 중 · 실패 · 할 것 없음) · 좁은 폭"),
    "run_all": ("smoke_run_all_ui.py", True, "헤딩 추출 「전체 실행」(조정까지) · 「단계별 실행 ▾」 — 상태 줄 단추 둘 · 확인 창(취소) · 도는 동안 「멈추기」(반영 안 함 · 남은 것 알림) · 다시 누르면 거친 단계는 건너뛰고 표 · 서식 계획 → 「모두 반영」 까지 · 실행 취소 · 「단계별 실행」 고르기 목록(고른 것만 차례로 · 확인 창 한 번 · 멈추기 · LLM 답 없음이면 뒤는 남김)(LLM 은 가짜 · 끝점은 진짜)"),
    "adjust": ("smoke_adjust_ui.py", True,"헤딩 추출 진행 줄의 「조정」 층 — 템플릿 조정 · 서식 조정 · 계획 받기(서식 정리 계획만) → 계획 받음 · 칸을 누르면 계획 보기 → 「모두 반영」(모든 템플릿 · 실행 취소 1) → 실행 취소(서식 정리 LLM 만 기준대로 답하는 가짜 · 끝점은 진짜)"),
    "div_run": ("smoke_div_run_ui.py", True, "프로젝트 구성 실행 묶음 — 한 번에 진행 · ① 변경 계획 보기 › ② 반영 · 계획 다시 열기 · 멈추는 조건(진짜 끝점)"),
    "div_key": ("smoke_div_key_ui.py", False, "구분 기준 자리 표시 — 문서 이름 줄의 색 설명(칩 · 노트 · 감추기 · 좁은 폭)"),
    "agent": ("smoke_agent_ui.py", True, "에이전트 보기 — 탭·작업 내용 · 요청 → 제안 카드 · 미리보기 · 문서에 반영 · 자료(끝점은 흉내)"),
    "styles": ("smoke_styles_ui.py", True, "서식 관리자 — 종류 셋 · 형식마다 검증 꼬리표 · 받기 · 문서 서식 줄 · 이름 바꾸기 · 지우기 · 서식 복사(단계 줄 · 후보 저장 · 검증 요약) · 표 메뉴(끝점은 흉내)"),
    "style_copy": ("smoke_style_copy_ui.py", True, "TASK 「문서 서식 복사」 — 카드 일곱 장 · hwpx 로 시작(2열 「서식 복사」) · 한 번에 진행 · PDF 는 작업 없이 시작 화면 옆 2열 · 도구 줄 「서식」 묶음 · docx 문서 · 다시 열기(보관함 끝점은 흉내)"),
    "outline_match": ("smoke_outline_match_ui.py", True, "레벨 서식 갈래 · 대표 정하기 · 대표에 맞추기 · 하위로 넣기·떼기 · 문서를 열 때 「TN Lk」 · 도구 줄 「템플릿 관계」(진짜 끝점)"),
    "outline_preview": ("smoke_outline_preview_ui.py", True, "개요 레벨 미리보기·비교 창 — 자리 수정의 지금 → 바뀐 뒤 · 서식 갈래 비교 표 · 창에서 적용·맞추기 · 닫기·옮기기(진짜 끝점)"),
    "tpl_agent": ("smoke_tpl_agent_ui.py", True, "템플릿 트리(「템플릿」 탭 = 「템플릿 관계」 열) · 개요 레벨 그림 · 하위로 늘 보임 · 다른 서식 보기 · 대표 맞추기 · 문서 표시의 서식 라벨 · 템플릿 서식 정리 에이전트(스킬 저장 · 계획 · 적용 — LLM 답만 흉내)"),
    "agents": ("smoke_agents_ui.py", True, "에이전트 설정 페이지(/agents) — 상단 바 링크(새 탭) · 목차 · 전체 보기 18줄(작업 번호·역할·쓰는 곳·모델) · #주소 · 설정 저장·겹치는 번호 거절·기본으로 · 저장 안 한 값 기억 · 프롬프트의 차례와 고칠 수 있는 글 · 실행 기록 · 좁은 폭 · 상단 바 폭(진짜 끝점)"),
    "work_guide": ("smoke_work_guide_ui.py", True, "작업 진행 에이전트 — 첫 화면 오른쪽 대화창(파일 → TASK 질문 카드) · TASK 시작 → 패널 「에이전트」 의 시작 턴 · 진행 줄 · 질문 카드(프로젝트 구성 폼) · 바로 실행(읽기 · 변경 계획) · 실행 카드 「진행」(반영) · 다시 열기 · 「작업 설명」(LLM 끔 — 스크립트 답 · 끝점·편집은 진짜)"),
    "dash": ("smoke_dash_ui.py", True, "대시보드 — 패널 첫 탭(문서가 열려 있으면 늘) · 단계 흐름(등록부 그대로) · 상태 · 대시보드에서만 양식 표준화 1단계 끝까지(값 확정 → 변경 계획 → 적용) · 이관 묶음 넷 · 「그 단계로」 · TASK 가 없는 문서의 「TASK 고르기」 · 일반 편집 · 좁은 폭"),
    "agent_flow": ("smoke_agent_flow_ui.py", True, "진행 방식 둘 · 에이전트 보기의 진행 보고 — 취합 간단 모드와 에이전트(패널이 안 바뀜 · 진행 카드 · 겹치는 턴 없음 · 끝 보고) · 실행 카드는 그 계획에만(계획이 바뀌면 실행하지 않음) · 첫 화면 대화창 = 문서 목록 하나 · 취합 옵션 묶음(화면만 LLM 사용 가능 — 답은 스크립트 · 끝점은 진짜)"),
    "workflow": ("smoke_workflow_ui.py", True, "TASK 워크플로우 페이지(/workflow) — 상단 바 링크(새 탭) · 목차 · 전체 보기(TASK 마다 단계 묶음 사슬) · TASK 절의 묶음·단계 · 세부(에이전트 · 모듈 · 사양 자리) · 공통 모듈 · #주소 · 좁은 폭 · 상단 바 폭(진짜 끝점)"),
    "fmt_focus": ("smoke_fmt_focus_ui.py", True, "서식 라벨만 또렷이 · 템플릿만 또렷이 — 여백의 서식 라벨·템플릿 표기를 누르면 그 문단만 그대로(옅은 바탕)·나머지는 흐리게 · 대표와 여백이 다른 줄(여백만 주황 · 오른쪽 여백의 표) · 이름 줄 설명 · 다시 눌러 풀기 · 쪽 다시 나눔 · 다른 문서 · 좁은 폭 · 자리 옮기기(휠로 다음·앞 곳 · 문서 창의 「위 n곳」·「아래 n곳」 알약 · 「휠 이동」)(진짜 끝점)"),
    "pick_sync": ("smoke_pick_sync_ui.py", True, "「템플릿 관계」 의 고른 갈래(☐) ↔ 본문 표시 — 고른 갈래의 줄 전부만 또렷이(문단 id 집합 · 30줄 넘는 갈래 · 값 칸 제외) · 두 트리 동기화 · 갈래 번호 꼬리표 ↔ 카드(.sel) · 「본문에서 보기」 · 「끄기」 · 맞추기의 rev(409) · 다른 문서(진짜 끝점)"),
    "doc_diff": ("smoke_doc_diff_ui.py", True, "문서에서 고친 곳 보기(깃처럼) — 넣은 글 초록 · 지운 자리 빨간 물결 · 띠(M 주황 · A 초록) · 오른쪽 여백 꼬리표(무엇이 → 올리면 어떻게 → 누르면 「고친 문단」 항목) · 치는 대로 · 배율 · 켬·끔 기억 · 되돌리기 · 다른 문서(진짜 끝점)"),
    "doc_quick": ("smoke_doc_quick_ui.py", True, "문서 이름 줄의 표시 아이콘 — 여백의 템플릿 표시 「T1 L2」 · 서식 라벨 「S41」 을 따로 켜고 끔 · 열 위 단추와 같은 값 · 기억 · 좁은 폭 · docx·분석 전 문서(진짜 끝점)"),
    "outline_lift": ("smoke_outline_lift_ui.py", True, "표 제목을 템플릿의 L1 으로 — 「템플릿 관계」 의 「표를 L1 으로」(같은 꼴 1칸 제목 표 한 번에) · 여백 표시 · 표 줄의 Enter · 거절 · 떼기 · 실행 취소 · 넓힘(번호 칸 + 제목 칸 띠 · 3행 표 · 닻 없는 같은 꼴 · 표 레벨 여러 층)(진짜 끝점)"),
    "heading_bands": ("smoke_heading_bands_ui.py", True, "띠 표 줄 — 「별첨N | 제목」 이름표 띠 표를 헤딩 추출이 줄로(그래프 노드 · 맨 뒤 번호의 띠 표 템플릿) · 여백 표시 「TN L1」 · 「템플릿 관계」 의 「L1 = 별첨·부록 표 제목」·레벨 줄 「표 제목 · 별첨N」 · Enter 거절 · 「표를 L1 으로」 400(진짜 끝점)"),
    "caption_tpl": ("smoke_caption_tpl_ui.py", True,"캡션 템플릿 「CN」 — 여백의 보라 「C1」(다른 서식 「≠」 · TEMP 제외) · 「템플릿 관계」 끝의 「캡션 템플릿」 절(서식 목록 · 대표로 · 이 줄들만 맞추기 · 대표에 맞추기 · 실행 취소) · 표시를 눌러 그 서식으로(진짜 끝점)"),
    "outline_grow": ("smoke_outline_grow_ui.py", True,"개요 레벨 더하기 — 마지막 레벨 줄의 Alt+↓ → 후보 창(레터 · 레터 앞 빈칸 · 둘째 줄 · 직접 입력) · 키 · 더하기 · 거절 · 실행 취소(진짜 끝점)"),
    "para_letter": ("smoke_para_letter_ui.py", True, "레터 넣기 — 「문단 수정」 묶음의 단추 → 단추 아래 메뉴(개요 레벨 · 번호 · 기호 · 직접 입력 · 레터 빼기) · 이어서/처음부터 · 여러 문단 · 거절 · 실행 취소(진짜 끝점)"),
    "share": ("smoke_share_ui.py", True, "hwpx 공유 — 「공유」 단추 · 떠 있는 창 · 손님(공유 포트 = 포트 + 700)의 키 넣기 · 글이 오감 · 작성 중 · 줄 나누기/합치기 · 공유폴더 저장 · 끄기(진짜 끝점)"),
    "lead_space": ("smoke_lead_space_ui.py", True, "줄 앞 빈칸 — 양쪽 정렬 문단의 첫머리 빈칸이 안 늘어남(조각 .lead-sp) · 자리 = 왼쪽 정렬 자리 · 저장·새로 고침 · 조각 안 편집 · Home/End/화살표 · 한글 조합 · 빈칸 폭 = 한글 폭 0.5em(첫머리 · 줄 안 · 양쪽 정렬 아닌 문단)(진짜 끝점)"),
    "home": ("smoke_home_ui.py", False, "상단 로고 → 시작 화면"),
    "note_help": ("smoke_note_help_ui.py", False, "노트 도움말 — hover · 키보드 · 터치 · 좁은 화면 · 대화상자"),
    "table_menu": ("smoke_table_menu_ui.py", False, "표 메뉴"),
    "table_fill": ("smoke_table_fill_ui.py", False, "작성요령 세 묶음 · 표 채우기"),
    "table_style": ("smoke_table_style_ui.py", False, "표 서식 점검 · 맞추기"),
    "table_cells": ("smoke_table_cells_ui.py", False, "표 칸 고르기·행/열"),
    "heading_drift": ("smoke_heading_drift_ui.py", False, "뼈대 유지"),
    "zoom": ("smoke_zoom_lazy_ui.py", False, "배율 — 쪽 상자마다 · 보이는 쪽부터(옆 열 여닫기 · 맞춤 · 2쪽 · 창 크기)"),
    "text_pics": ("smoke_text_pics_ui.py", False, "글 속 그림 — 글과 같은 줄의 그 자리에(표 칸 · 본문 · 글 고치기 · 문단 나누기)"),
    "edit_speed": ("smoke_edit_speed_ui.py", False, "구조 편집 속도 — 시간을 재므로 같이 돌리면 수치가 부푼다(혼자 돌릴 것)"),
}
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("names", nargs="*")
ap.add_argument("--all", action="store_true")
ap.add_argument("--jobs", type=int, default=5)
ap.add_argument("--no-retry", action="store_true")
ap.add_argument("--list", action="store_true")
ap.add_argument("--timeout", type=int, default=900)
ap.add_argument("--port", type=int, default=18300, help="첫 포트 — 검사마다 하나씩 올려 쓴다")
args = ap.parse_args()
if args.list:
    for k, (f, d, note) in GATES.items():
        print(f"{'*' if d else ' '} {k:14} tools/{f} — {note}")
    sys.exit(0)
names = args.names or [k for k, v in GATES.items() if v[1] or args.all]
bad = [n for n in names if n not in GATES]
if bad:
    sys.exit(f"모르는 검사: {', '.join(bad)} — --list 로 이름을 보세요")
OUT = Path(args.out).resolve()
OUT.mkdir(parents=True, exist_ok=True)


def listening(port):
    with socket.socket() as s:
        s.settimeout(.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port(start, taken):
    p = start
    while p in taken or listening(p):
        p += 1
    return p


def start(name, port):
    log = (OUT / f"{name}.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-X", "utf8", str(ROOT / "tools" / GATES[name][0]), str(OUT / name), "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, cwd=ROOT,
                            env={**os.environ, "PYTHONUTF8": "1"}, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    return {"name": name, "port": port, "proc": proc, "log": log, "t0": time.time()}


def kill(job):  # 시간 초과 — 검사와 그것이 띄운 임시 서버까지
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(job["proc"].pid), "/T", "/F"], capture_output=True)
    else:
        job["proc"].kill()


def finish(job, code):
    job["log"].close()
    text = (OUT / f"{job['name']}.log").read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return {"name": job["name"], "port": job["port"], "code": code, "secs": time.time() - job["t0"], "passed": sum(x.startswith("PASS ") for x in lines),
            "fails": [x[:300] for x in lines if x.startswith("FAIL ")], "tail": [x[:300] for x in lines[-4:]]}


def run(batch, jobs):
    """batch 의 검사를 jobs 개씩 같이 돌린다 → {이름: 결과}."""
    todo, live, done, taken = list(batch), [], {}, set()
    while todo or live:
        while todo and len(live) < jobs:
            port = free_port(args.port, taken)
            taken.add(port)
            live.append(start(todo.pop(0), port))
            print(f"  ▶ {live[-1]['name']} (포트 {port})", flush=True)
        time.sleep(.5)
        for job in list(live):
            code = job["proc"].poll()
            if code is None and time.time() - job["t0"] > args.timeout:
                kill(job)
                code = -9
            if code is None:
                continue
            live.remove(job)
            r = done[job["name"]] = finish(job, code)
            mark = "통과" if code == 0 and not r["fails"] else "시간 초과" if code == -9 else "실패"
            print(f"  ■ {r['name']} — {mark} · 통과 {r['passed']} · 실패 {len(r['fails'])} · {r['secs']:.0f}초", flush=True)
    return done


t0 = time.time()
print(f"화면 검사 {len(names)}개를 {min(args.jobs, len(names))}개씩 같이 — {', '.join(names)}", flush=True)
res = run(names, max(1, args.jobs))
wall, serial = time.time() - t0, sum(r["secs"] for r in res.values())
failed = [n for n in names if res[n]["code"] != 0 or res[n]["fails"]]
retried = {}
if failed and not args.no_retry:
    print(f"떨어진 검사 {len(failed)}개를 혼자 다시 — {', '.join(failed)}", flush=True)
    for n in failed:
        first = res[n]
        res[n] = run([n], 1)[n]
        retried[n] = first
wall_all = time.time() - t0
print("\n검사            통과  실패  시간   비고")
for n in names:
    r, note = res[n], ""
    if n in retried:
        note = "같이 돌 때 떨어졌다가 혼자서는 통과(부하)" if r["code"] == 0 and not r["fails"] else "혼자서도 실패"
    print(f"{n:14} {r['passed']:4} {len(r['fails']):5} {r['secs']:5.0f}초  {note}")
    for f in r["fails"][:5]:
        print(f"    {f}")
    if r["code"] != 0 and not r["fails"]:
        print(f"    종료 코드 {r['code']} — {' / '.join(r['tail'])}")
left = sorted({r["port"] for r in list(res.values()) + list(retried.values()) if listening(r["port"])})
still = [n for n in names if res[n]["code"] != 0 or res[n]["fails"]]
print(f"\n같이 돌린 시간 {wall:.0f}초 — 차례로 돌렸다면 {serial:.0f}초({serial / max(wall, 1):.1f}배)" + (f" · 다시 돌리기까지 {wall_all:.0f}초" if retried else ""))
print("남은 임시 서버: " + (", ".join(map(str, left)) + " 포트가 아직 듣고 있습니다 — 끄세요" if left else "없음"))
print(f"{'FAIL ' + str(len(still)) + ' — ' + ', '.join(still) if still else 'ALL PASS'} · 기록 {OUT}")
sys.exit(1 if still or left else 0)
