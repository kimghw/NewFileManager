"""문서 목적 YAML(app/purpose_yaml.py — spec_양식작성 ② §5-9): 꼴 검사 · 프로젝트마다의 파일(계정의 작업 뿌리 아래) · 판 충돌 · 이름 바꾸기 · 지우기 따라가기 · 자리 잇기 · 문서 전체 묶음."""
import pytest

import test_form_guide_yaml as D
from app import form_guide_yaml as FG
from app import projects
from app import purpose_yaml as PY
from app import works

TEXT = """
schema: 1
project: 그린선박 2026
announcement: {name: 2026년 친환경선박 기술개발 공고, agency: 산업부, date: 2026-03-02}
purpose: |
  탄소 저감 효과를 정량으로 보이는 연차보고서.
evaluation:
  - 목표 대비 실적의 정량 근거
requirements:
  - {text: 실증 계획을 차년도별로 적는다, source: 공고문 4.2}
  - 참여기업의 역할을 밝힌다
guides:
  - text: 이번 과제는 수소 연료에 초점을 둔다
  - id: g-goal
    text: 목표 절에는 저감률(%)을 먼저 적는다
    targets:
      - path: ["1. 개요", "1-1. 목표"]
"""


def test_parse_checks_the_shape_and_round_trips():
    d = PY.parse(TEXT, "그린선박 2026")
    assert d["announcement"]["agency"] == "산업부" and d["purpose"].startswith("탄소 저감") and d["evaluation"] == ["목표 대비 실적의 정량 근거"]
    assert d["requirements"] == [{"text": "실증 계획을 차년도별로 적는다", "source": "공고문 4.2"}, {"text": "참여기업의 역할을 밝힌다"}]
    assert [(g["id"], bool(g["targets"])) for g in d["guides"]] == [("g1", False), ("g-goal", True)]
    assert PY.parse(PY.dump(d), "그린선박 2026") == d and PY.dump(d).startswith("# 문서 목적 — 프로젝트 「그린선박 2026」")
    for bad in ("purpose: [목록]\n", "evaluation: 글\n", "requirements:\n  - {source: 출처만}\n", "guides:\n  - {text: t, targets: [{table: 표만}]}\n",
                "guides:\n  - {id: a, text: t}\n  - {id: a, text: u}\n", "announcement: 글\n"):
        with pytest.raises(ValueError):
            PY.parse(bad, "그린선박 2026")


def test_the_file_lives_per_project_under_the_works_root_and_keeps_its_version():
    assert PY.safe("과제 A/1") != PY.safe("과제 A 1") and PY.safe("과제 A/1").startswith("과제_A_1-")   # 다른 이름이 같은 파일로 겹치지 않는다
    assert PY.load("그린선박 2026") is None and PY.read("그린선박 2026")[1] is None
    d, sha = PY.save_text("그린선박 2026", TEXT, expect="")
    p = PY.path_of("그린선박 2026")
    assert p.is_file() and p.parent == works.root() / PY.DIR and PY.load("그린선박 2026") == d and PY.read("그린선박 2026")[2] == sha
    with pytest.raises(FG.StaleVersion):
        PY.save_text("그린선박 2026", TEXT + "\n", expect="")   # 그 사이 생긴 파일을 「새 파일」 로 덮지 않는다
    with pytest.raises(ValueError):
        PY.save_text("그린선박 2026", "purpose: [목록]", expect=sha)
    _, sha2 = PY.save_text("그린선박 2026", TEXT.replace("수소", "암모니아"), expect=sha)
    assert sha2 != sha and list((p.parent / "_history" / p.stem).glob("*.yaml"))   # 고치기 전 글은 이력에
    assert PY.load("다른 프로젝트") is None and PY.path_of("") is None


def test_the_file_follows_a_project_rename_and_removal():
    assert projects.create("옛 이름")
    PY.save_text("옛 이름", TEXT.replace("그린선박 2026", "옛 이름"), expect="")
    assert projects.rename("옛 이름", "새 이름")
    assert PY.load("옛 이름") is None and PY.load("새 이름")["project"] == "새 이름" and PY.load("새 이름")["purpose"].startswith("탄소 저감")
    assert projects.remove("새 이름")
    assert PY.load("새 이름") is None and list((works.root() / PY.DIR / "_removed").glob("*.yaml"))   # 지우지 않고 옮긴다


def test_whole_document_items_come_once_and_targeted_guides_reach_their_place():
    d = PY.parse(TEXT, "그린선박 2026")
    got = PY.locate(d, FG.doc_places(D.BLOCKS, D.GRAPH, D.T3), D.BLOCKS)
    assert [(g["kind"], g["text"].strip()) for g in got["doc"]] == [
        ("문서 목적", "탄소 저감 효과를 정량으로 보이는 연차보고서."), ("문서 목적 — 평가 관점", "목표 대비 실적의 정량 근거"),
        ("문서 목적 — 요구 사항", "실증 계획을 차년도별로 적는다"), ("문서 목적 — 요구 사항", "참여기업의 역할을 밝힌다"), ("문서 목적 — 프로젝트 지침", "이번 과제는 수소 연료에 초점을 둔다")]
    assert got["doc"][0]["source"] == "2026년 친환경선박 기술개발 공고 · 산업부 · 2026-03-02" and got["doc"][2]["source"] == "공고문 4.2" and all(g["src"] == "purpose" for g in got["doc"])
    g = got["heads"]["h2"][0]
    assert (g["src"], g["kind"], g["text"], g["rule"]) == ("purpose", "문서 목적 — 프로젝트 지침", "목표 절에는 저감률(%)을 먼저 적는다", "g-goal") and "required" not in g
    assert got["links"] == {"g-goal": 1} and not got["unmatched"]
    assert PY.locate(None, {"heads": {}, "tables": {}, "bands": {}})["doc"] == []
