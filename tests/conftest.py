import pytest


@pytest.fixture(autouse=True)
def _no_hangul(tmp_path, monkeypatch):
    """시험은 한글을 띄우지 않고(PDF 단계 건너뜀) 사용자 렌더 캐시(%LOCALAPPDATA%)를 건드리지 않는다. PDF 를 시험하는 테스트는 직접 바꾼다."""
    monkeypatch.setenv("NFM_PDF", "off")
    monkeypatch.setenv("NFM_RENDER", str(tmp_path / "render"))
    monkeypatch.setenv("NFM_WORKS", str(tmp_path / "works"))  # 작업 저장(spec_작업)도 시험마다 임시 폴더
    monkeypatch.setenv("NFM_DIVISION_PRESETS", str(tmp_path / "division_presets.json"))  # 저장한 구분 기준(spec_구분_기준)도 임시 파일
