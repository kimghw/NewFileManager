import pytest


@pytest.fixture(autouse=True)
def _no_hangul(tmp_path, monkeypatch):
    """시험은 한글을 띄우지 않고(PDF 단계 건너뜀) 사용자 렌더 캐시(%LOCALAPPDATA%)를 건드리지 않는다. PDF 를 시험하는 테스트는 직접 바꾼다."""
    monkeypatch.setenv("NFM_PDF", "off")
    monkeypatch.setenv("NFM_VERIFY_LLM", "off")  # 검증 LLM 검토(spec_hwpx_웹편집 ② §4-1)는 주의·실패가 나면 저절로 LLM 을 부른다 — 시험은 끄고, 보는 시험만 켜고 llm.call 을 바꾼다
    monkeypatch.setenv("NFM_RENDER", str(tmp_path / "render"))
    monkeypatch.setenv("NFM_WORKS", str(tmp_path / "works"))  # 작업 저장(spec_작업)도 시험마다 임시 폴더
    monkeypatch.setenv("NFM_DIVISION_PRESETS", str(tmp_path / "division_presets.json"))  # 저장한 구분 기준(spec_구분_기준)도 임시 파일
    monkeypatch.setenv("NFM_BLOCKS_CHECK", "1")  # 구조 편집마다 「닿은 블록만 다시 읽기」를 문서 전체를 다시 읽은 것과 견준다(server._transact — spec_owpml_편집 ② §3)
    monkeypatch.setenv("NFM_FORMS", str(tmp_path / "forms"))  # 양식 정보(spec_헤딩_추출 ② §12)도 임시 폴더 — 저장소 forms/ 의 글이 시험 프롬프트에 섞이지 않게
    monkeypatch.setenv("NFM_JOBS", str(tmp_path / "jobs"))  # 할 일 프롬프트(spec_작업 ② §13)도 — 저장소 jobs/ 의 글은 그것을 보는 시험만 직접 읽는다
    monkeypatch.setenv("NFM_AGENTS", str(tmp_path / "agents.json"))  # 에이전트 설정(spec_에이전트 ② §2)도 시험마다 임시 파일 — 사용자가 정한 모델·생각 깊이가 시험의 LLM 호출에 섞이지 않게
    monkeypatch.setenv("NFM_STYLES", str(tmp_path / "styles"))  # 서식 보관함(spec_일반편집 ② §2)도 시험마다 임시 폴더 — 사용자 보관함(%LOCALAPPDATA%)을 안 건드린다
    monkeypatch.setenv("NFM_TASKS", str(tmp_path / "tasks.json"))  # 화면에서 조립한 TASK(spec_워크플로우 ② §14)도 시험마다 임시 파일 — 사용자가 만든 TASK 가 등록부 · TASK 검사에 섞이지 않게
