"""사양 관리 점검(tools/spec_check.py — spec_워크플로우 ② §11): 문서의 깨진 링크 · 코드가 가리키는 사양 절이 사양서에 있는지."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("spec_check", ROOT / "tools" / "spec_check.py")
SC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SC)

HOW = " — python -X utf8 tools/spec_check.py 로 본다(spec_워크플로우 ② §11)"


def test_doc_links_point_at_files_that_exist():
    bad = SC.links()
    assert not bad, "관리 문서의 깨진 링크: " + " · ".join(f"{d} → {t}" for d, t in bad) + HOW


def test_spec_sections_cited_in_code_exist():
    no_sec, _ = SC.sections()
    assert not no_sec, ("코드가 가리키는 절 이름이 사양서에 없다(절을 사양서에 만들거나 코드의 글을 고친다): "
                        + " · ".join(f"{n} ② §{s} 「{t}」 ← {', '.join(fs)}" for n, s, t, fs in no_sec) + HOW)


def test_spec_files_cited_in_code_exist():
    _, no_spec = SC.sections()
    assert not no_spec, "코드가 가리키는 사양서가 없다: " + " · ".join(f"{n} ← {', '.join(fs)}" for n, fs in no_spec) + HOW


def test_checker_finds_what_is_missing(tmp_path):
    """검사 자체 — 흉내 저장소에서 있는 것은 지나치고 없는 것만 잡는다."""
    (tmp_path / "spec").mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "spec" / "spec_가나.md").write_text("## ② 확정 사양\n- **있는 절**: …\n[옆](spec_다라.md) · [없음](spec_없음.md) · [밖](https://example.com/a.md) · [글](§8-5)\n", encoding="utf-8")
    (tmp_path / "spec" / "spec_다라.md").write_text("글\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("[사양](spec/spec_가나.md#2) · [옛](spec/spec_옛것.md) · [저장소 밖](../다른_프로젝트/spec/spec_서식.md) · [작업 기록](artifacts/없는_기록/)\n", encoding="utf-8")
    (tmp_path / "app" / "x.py").write_text(
        "# spec_가나 ② §3 「있는 절」 · spec_가나 ② §3 「있는  절」 · spec_가나 ② §4 「없는 절」 · spec_가나의 글 · spec_가나 ② §5 「<이름>: <꼴>」\n"
        "# spec_서식 ② §3 「옛 프로젝트의 절」 · spec_모르는것 · spec_of_block\n", encoding="utf-8")
    assert sorted(SC.links(tmp_path)) == [("CLAUDE.md", "spec/spec_옛것.md"), ("spec/spec_가나.md", "spec_없음.md")]
    no_sec, no_spec = SC.sections(tmp_path)
    assert no_sec == [("spec_가나", "4", "없는 절", ["app/x.py"])]
    assert no_spec == [("spec_모르는것", ["app/x.py"])]
