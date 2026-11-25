"""양식 정보(spec_헤딩_추출 ② §12) — 양식마다 md 하나: 조건 블록·프롬프트 글 · 저장(기대 sha1) · 문서 ↔ 양식 맞추기 · 프롬프트에 따로 한 절 ·
실행 고정·기록 · API · 저장소의 forms/연구개발계획서.md.

LLM 은 늘 끈다(NFM_LLM_BACKEND=off) — LLM 이 필요한 곳은 가짜 llm.ask_all. 양식 정보 폴더는 conftest 의 NFM_FORMS(시험마다 임시 폴더)."""
import gzip
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_forms as F
from app import heading_guides as G
from app import heading_llm as HL
from app import heading_rules as R
from app import heading_runs, llm, server, works

ROOT = Path(__file__).parents[1]
SMALL = ROOT / "samples" / "기술수요조사서.hwpx"
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"

TEXT = """# 양식 정보 — 시험

```json
{"name": "시험 양식", "match": {"names": ["*기술수요조사서*"], "sha256": ["ABC123"]}}
```

<!-- 사람만 보는 메모 MEMO -->

## 개요 체계
- 주 사슬은 FORMFACT 이다.
"""


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    F._CHOICE.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()
    F._CHOICE.clear()


@pytest.fixture
def c():
    server.DOCS.clear()
    yield TestClient(server.app, raise_server_exceptions=False)
    server.DOCS.clear()


def _open_ready(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    end = time.time() + 60
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/verify").json()
        if "import" in v and not v["import"]["running"]:
            return d
        time.sleep(0.05)
    raise AssertionError("가져오기 검증이 끝나지 않음")


def _res(data=None, error=None):
    return {"data": data, "backend": "fake", "model": "fake", "ms": 0, "costUsd": 0.0, "error": error}


# ---- 글: 조건 블록 · 프롬프트에 넣는 글 ---------------------------------------------------------------------------

def test_parse_reads_match_block_and_body_drops_block_and_comments():
    head = F.parse(TEXT)
    assert head == {"name": "시험 양식", "names": ["*기술수요조사서*"], "sha256": ["abc123"]}
    b = F.body(TEXT)
    assert "FORMFACT" in b and b.startswith("# 양식 정보 — 시험")
    assert "```json" not in b and "sha256" not in b and "MEMO" not in b
    assert F.parse("# 조건 없는 글\n- 내용") == {"name": "", "names": [], "sha256": []}


@pytest.mark.parametrize("block", ['{"name": 3}', '[1]', '{"match": []}', '{"match": {"names": "x"}}', '{"match": {"sha256": [1]}}', '{깨짐'])
def test_parse_rejects_broken_block(block):
    with pytest.raises(ValueError):
        F.parse(f"```json\n{block}\n```\n글")


@pytest.mark.parametrize("key", ["../x", "a/b", "a\\b", ".숨김", "끝점.", "a..b", "CON", "README", "", "x" * 61, "별*표", "a:b", "줄바꿈\n", "끝빈칸 "])
def test_bad_keys_are_rejected(key):
    with pytest.raises(ValueError):
        F.check_key(key)


def test_unclosed_block_is_rejected_not_silently_dropped():
    """여는 울타리만 있는 json 블록 — 「블록 없음」 으로 보면 조건이 사라지고 그 글이 LLM 에 들어간다."""
    text = '# 양식\n\n```json\n{"match": {"names": ["*x*"]}}\n\n## 절\n- 내용\n'
    with pytest.raises(ValueError):
        F.parse(text)
    with pytest.raises(ValueError):
        F.save("시험", text, expect="")
    assert F.listing() == []


def test_untouched_skeleton_sends_nothing():
    sk = F.suggest("새 양식.hwpx", "aa")["text"]
    assert F.body(sk) == ""  # 제목 줄·빈 글머리뿐
    assert "첫 사실" in F.body(sk.replace("## 문서 특성\n-", "## 문서 특성\n- 첫 사실"))


# ---- 저장: 파일 하나가 원본 · 기대 sha1 · 이전 글 남김 ------------------------------------------------------------------

def test_save_creates_file_and_stale_sha_is_refused(tmp_path):
    assert F.listing() == []
    g = F.save("시험", TEXT, expect="", reason="t")
    p = Path(g["path"])
    assert p == F.forms_dir() / "시험.md" and p.read_text("utf-8") == TEXT
    assert g["name"] == "시험 양식" and g["match"]["names"] == ["*기술수요조사서*"] and g["broken"] is None
    assert [f["key"] for f in F.listing()] == ["시험"] and "text" not in F.listing()[0]
    with pytest.raises(R.StaleVersion):  # 새로 만든다고 했는데 이미 있음
        F.save("시험", TEXT + "x", expect="")
    with pytest.raises(R.StaleVersion):  # 옛 판을 든 저장
        F.save("시험", TEXT + "x", expect="0" * 40)
    g2 = F.save("시험", TEXT + "- 덧붙임\n", expect=g["sha1"], reason="t2")
    assert g2["sha1"] != g["sha1"] and F.get("시험")["text"].endswith("- 덧붙임\n")
    kept = list((R.store_dir() / "forms_history" / "시험").glob("*.md"))
    assert len(kept) == 1 and kept[0].read_text("utf-8") == TEXT  # 고치기 전 글
    hist = [e for e in R.history() if e.get("kind") == "form"]
    assert [e["action"] for e in hist] == ["create", "save"] and hist[-1]["sha1"] == g2["sha1"]


def test_save_rejects_broken_block_and_long_text():
    with pytest.raises(ValueError):
        F.save("시험", "```json\n{깨짐\n```\n", expect="")
    with pytest.raises(ValueError):
        F.save("시험", "x" * (F.TEXT_MAX + 1), expect="")
    assert F.listing() == []


def test_file_edited_outside_is_read_fresh_and_crlf_is_normalized():
    g = F.save("시험", TEXT, expect="")
    Path(g["path"]).write_bytes(TEXT.replace("FORMFACT", "밖에서 고침").replace("\n", "\r\n").encode("utf-8-sig"))  # 편집기(CRLF·BOM)
    g2 = F.get("시험")
    assert "밖에서 고침" in g2["text"] and "\r" not in g2["text"] and not g2["text"].startswith("﻿") and g2["sha1"] != g["sha1"]


def test_forms_off(monkeypatch):
    monkeypatch.setenv("NFM_FORMS", "off")
    assert F.forms_dir() is None and F.listing() == [] and F.match("기술수요조사서.hwpx") is None
    with pytest.raises(ValueError):
        F.save("시험", TEXT, expect="")


# ---- 문서 ↔ 양식 ------------------------------------------------------------------------------------------

def test_match_order_choice_then_sha_then_longest_name():
    F.save("넓은", '```json\n{"match": {"names": ["*조사서*"]}}\n```\n넓은 글', expect="")
    F.save("좁은", '```json\n{"match": {"names": ["*기술수요조사서*"]}}\n```\n좁은 글', expect="")
    F.save("원본", '```json\n{"match": {"sha256": ["FFEE"]}}\n```\n원본 글', expect="")
    assert F.match("2027_기술수요조사서_최종.HWPX")["key"] == "좁은" and F.match("2027_기술수요조사서_최종.HWPX")["how"] == "name"
    assert F.match("시장조사서.hwpx")["key"] == "넓은"
    m = F.match("기술수요조사서.hwpx", "ffee")
    assert m["key"] == "원본" and m["how"] == "sha256"  # 올린 원본 일치가 이름보다 먼저
    m = F.match("기술수요조사서.hwpx", "ffee", "넓은")
    assert m["key"] == "넓은" and m["how"] == "manual"
    assert F.match("기술수요조사서.hwpx", "ffee", "") is None  # 양식 없음으로 고정
    assert F.match("기술수요조사서.hwpx", None, "없어진 양식")["key"] == "좁은"  # 고른 파일이 없으면 자동
    assert F.match("다른 문서.hwpx") is None


def test_name_pattern_brackets_are_literal():
    F.save("괄호", '```json\n{"match": {"names": ["[양식]*계획서?hwpx"]}}\n```\n글', expect="")
    assert F.match("[양식] 사업계획서.hwpx")["key"] == "괄호"
    assert F.match("양 사업계획서.hwpx") is None


def test_suggest_key_and_skeleton():
    s = F.suggest("연구개발계획서_양식.hwpx", "aa11")
    assert s["key"] == "연구개발계획서"
    assert F.parse(s["text"]) == {"name": "연구개발계획서", "names": ["*연구개발계획서*"], "sha256": ["aa11"]}
    assert F.suggest("이상한:이름?.hwpx")["key"] == "이상한_이름_"
    assert F.suggest(".hwpx")["key"] == "양식"
    F.check_key(F.suggest("a" * 100 + ".hwpx")["key"])


# ---- 프롬프트: 일반 지침 뒤에 따로 한 절 ----------------------------------------------------------------------------

def test_prompt_adds_form_section_after_guides_only_when_pinned():
    pinned = G.snapshot()
    plain, used0 = HL.prompt("계약", ["graph", "templates"], {"k": 1}, pinned)
    assert "양식 정보" not in plain and set(used0) == {"graph", "templates"}
    f = F.save("시험", TEXT, expect="")
    pinned["form"] = {"sha1": f["sha1"], "text": f["text"], "key": f["key"], "name": f["name"], "how": "name", "custom": True, "version": 0}
    text, used = HL.prompt("계약", ["graph", "templates"], {"k": 1}, pinned)
    assert used == {**used0, "form": f["sha1"]}
    i_guide, i_form, i_data = text.index("## 지침 — "), text.index("## 양식 정보 — 시험 양식"), text.index("## 자료(JSON)")
    assert i_guide < i_form < i_data and HL.FORM_NOTE in text
    assert "FORMFACT" in text and "MEMO" not in text and "ABC123" not in text  # 메모·조건 블록은 안 보냄
    pinned["form"] = {**pinned["form"], "text": '```json\n{"match": {}}\n```\n<!-- 메모만 -->\n'}
    text2, used2 = HL.prompt("계약", ["graph"], {"k": 1}, pinned)
    assert "양식 정보" not in text2 and "form" not in used2  # 보낼 글이 없으면 절도 없음


# ---- 실행: 시작 때 고정 · 기록 · 요약 ------------------------------------------------------------------------------

def test_run_pins_form_into_prompts_and_records(c, monkeypatch):
    d = _open_ready(c, SMALL)
    s = server.DOCS[d]
    assert heading_runs.summary(s)["form"] is None
    heading_runs.run_sync(s, 1, False)
    assert "form" not in heading_runs.state(s)["stage1"]["meta"]["guides"]  # 맞는 양식이 없으면 지금과 같음
    f = F.save("시험", TEXT, expect="")
    assert heading_runs.summary(s)["form"] == {"key": "시험", "name": "시험 양식", "how": "name", "sha1": f["sha1"]}
    seen = []

    def ask(jobs):  # LLM 호출 중 양식 정보를 고쳐도 이 실행은 시작 때 글
        seen.extend(j["content"] for j in jobs)
        F.save("시험", TEXT.replace("FORMFACT", "실행 중 고침"), reason="mid-run")
        return [_res(None, "가짜 실패") for _ in jobs]
    monkeypatch.setattr(llm, "ask_all", ask)
    job = heading_runs.run_sync(s, 2, True)
    assert seen and all("## 양식 정보 — 시험 양식" in p and "FORMFACT" in p and "실행 중 고침" not in p for p in seen)
    g = heading_runs.state(s)["stage2"]
    assert g["meta"]["guides"]["form"] == f["sha1"] and g["guides"]["form"] == f["sha1"]
    snap = json.loads(gzip.decompress((works.folder(d) / "headings" / str(job.run) / "guides.json.gz").read_bytes()).decode("utf-8"))
    assert snap["form"]["key"] == "시험" and "FORMFACT" in snap["form"]["text"] and set(snap) - {"place"} == set(G.NAMES) | {"form"}   # place = 그 자리의 작성 지침(spec ② §20 — LLM 실행 · 문서에 지침이 있을 때만)
    assert heading_runs.summary(s)["form"]["sha1"] != f["sha1"]  # 요약은 지금 글 — 화면이 실행의 판과 견준다


def test_summary_of_a_session_stand_in_has_no_form():
    """문서 비교(heading_compare.preview)는 name·id·original 없는 대역으로 summary 를 부른다 — 양식은 None, 예외 없음."""
    from types import SimpleNamespace
    F.save("시험", TEXT, expect="")
    proxy = SimpleNamespace(rev=0, heads={"job": None, "stage1": None, "stage2": None, "stage3": None, "runs": [], "loaded": True})
    assert F.for_session(proxy) is None and F.pin(proxy) is None
    assert heading_runs.summary(proxy)["form"] is None


def test_doc_choice_is_kept_in_work_folder_and_memory_when_off(c, monkeypatch):
    d = _open_ready(c, SMALL)
    F.save("시험", TEXT, expect="")
    F.save("다른", "다른 양식 글", expect="")
    assert F.choice(d) is None
    F.set_choice(d, "다른")
    assert json.loads((works.folder(d) / "headings" / "form.json").read_text("utf-8"))["form"] == "다른"
    assert F.for_session(server.DOCS[d])["key"] == "다른"
    F.set_choice(d, "")
    assert F.choice(d) == "" and F.for_session(server.DOCS[d]) is None
    F.set_choice(d, None)
    assert F.choice(d) is None and F.for_session(server.DOCS[d])["key"] == "시험"
    with pytest.raises(KeyError):
        F.set_choice(d, "없는 양식")
    monkeypatch.setenv("NFM_WORKS", "off")  # 작업 저장 끔 — 메모리에
    F.set_choice("mem", "다른")
    assert F.choice("mem") == "다른"
    F.set_choice("mem", None)
    assert F.choice("mem") is None


# ---- API -------------------------------------------------------------------------------------------------

def test_selected_form_prompt_uses_agent_sections(c):
    doc = _open_ready(c, SMALL)
    endpoint = f"/api/docs/{doc}/headings/form/prompt"
    assert c.get(endpoint, params={"agent": "heading_types"}).json()["form"] is None
    assert c.get(endpoint, params={"agent": "writing_guidance"}).status_code == 404
    text = TEXT + f"\n## {F.DIVISION_SECTION}\n- DIV_ONLY\n\n## {F.LINK_SECTION}\n- LINK_ONLY\n"
    record = F.save("양식별지침", text, expect="")
    F.set_choice(doc, record["key"])
    view = c.get(endpoint, params={"agent": "heading_types"}).json()["form"]
    prompt, _ = HL.prompt("계약", [], {}, {"form": record})
    assert view["text"] == text and view["sha1"] == record["sha1"] and view["applied"] in prompt
    assert "FORMFACT" in view["applied"] and all(mark not in view["applied"] for mark in ("DIV_ONLY", "LINK_ONLY", "MEMO"))
    for agent in ("merge_links", "div_review"):
        applied = c.get(endpoint, params={"agent": agent}).json()["form"]["applied"]
        assert "DIV_ONLY" in applied and "LINK_ONLY" not in applied


def test_api_forms_and_doc_form(c):
    d = _open_ready(c, SMALL)
    v = c.get(f"/api/docs/{d}/headings/form").json()
    assert v["form"] is None and v["choice"] is None and v["forms"] == [] and v["suggest"]["key"] == "기술수요조사서"
    sha = works.work(d)["sha256"]
    assert F.parse(v["suggest"]["text"])["sha256"] == [sha]
    r = c.put("/api/headings/forms/기술수요조사서", json={"text": v["suggest"]["text"], "sha1": ""})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert c.put("/api/headings/forms/기술수요조사서", json={"text": "x", "sha1": ""}).status_code == 409
    assert c.put("/api/headings/forms/기술수요조사서", json={"text": "```json\n{깨짐\n```", "sha1": saved["sha1"]}).status_code == 400
    assert c.put("/api/headings/forms/a..b", json={"text": "x", "sha1": ""}).status_code == 400
    assert c.get("/api/headings/forms/없는양식").status_code == 404
    assert c.get("/api/headings/forms/기술수요조사서").json()["text"] == v["suggest"]["text"]
    assert [f["key"] for f in c.get("/api/headings/forms").json()["forms"]] == ["기술수요조사서"]
    v = c.get(f"/api/docs/{d}/headings/form").json()
    assert v["form"]["key"] == "기술수요조사서" and v["form"]["how"] == "sha256" and "text" not in v["form"]
    assert c.get(f"/api/docs/{d}/headings").json()["form"]["key"] == "기술수요조사서"
    v = c.put(f"/api/docs/{d}/headings/form", json={"form": ""}).json()
    assert v["form"] is None and v["choice"] == ""
    assert c.get(f"/api/docs/{d}/headings").json()["form"] is None
    assert c.put(f"/api/docs/{d}/headings/form", json={"form": "없는양식"}).status_code == 404
    assert c.put(f"/api/docs/{d}/headings/form", json={"form": 3}).status_code == 400
    assert c.put(f"/api/docs/{d}/headings/form", json={}).status_code == 400
    v = c.put(f"/api/docs/{d}/headings/form", json={"form": None}).json()
    assert v["choice"] is None and v["form"]["key"] == "기술수요조사서"


# ---- 저장소의 양식 정보(forms/연구개발계획서.md) -----------------------------------------------------------------------

def test_repo_form_matches_the_rnd_sample(monkeypatch):
    monkeypatch.delenv("NFM_FORMS")
    assert F.forms_dir() == ROOT / "forms"
    f = F.get("연구개발계획서")
    assert f["broken"] is None and f["size"] <= F.TEXT_MAX
    assert F.match("연구개발계획서_양식.hwpx")["key"] == "연구개발계획서"
    m = F.match("이름이 바뀐 파일.hwpx", works.sha256(RND.read_bytes()))
    assert m["key"] == "연구개발계획서" and m["how"] == "sha256"
    b = F.body(f["text"])
    assert "주 사슬" in b and "<!--" not in b and "```json" not in b
    assert "## 구분 기준 자리" in b and "공동연구개발기관책임자(기관이름)" in b and "기관이름 (주관)" in b   # 구분 기준에서 사용자가 요청한 것(spec_구분_기준 ② §16)


# ---- 「표」 절 — 표 도구 LLM 의 양식 표 지침(② §12 「미치는 범위」) -----------------------------------------------------------

TABLE_TEXT = TEXT + """
## 표지
- 표지 이야기 COVERFACT

## 표 — 작성 기준
- 금액은 천원 단위 TABLEFACT
### 세부
- 합계 행은 맨 아래

## 표 · 빈 절
-

## 그 밖
- 다른 절 OTHERFACT
"""


def test_section_picks_sections_whose_title_starts_with_the_word():
    sec = F.section(F.body(TABLE_TEXT), "표")
    assert sec.startswith("## 표 — 작성 기준") and "TABLEFACT" in sec and "### 세부" in sec and sec.endswith("합계 행은 맨 아래")
    assert "COVERFACT" not in sec and "OTHERFACT" not in sec and "FORMFACT" not in sec and "빈 절" not in sec   # 「표지」 는 다른 낱말 · 글머리뿐인 절은 뺌
    assert F.section(F.body(TEXT), "표") == "" and F.section("", "표") == ""
    assert "## 구분 기준 자리" in F.suggest("새 양식.hwpx")["text"] and F.body(F.suggest("새 양식.hwpx")["text"]) == ""


def test_heading_prompt_leaves_out_the_division_section():
    """「구분 기준 자리」 로 시작하는 절은 구분 기준 검토에만 간다 — 헤딩 추출 프롬프트(heading_llm.prompt)에는 그 절을 뺀 글. 그 절뿐인 양식 정보면 헤딩 프롬프트에 양식 절이 없다."""
    text = TEXT + "\n## 구분 기준 자리 — 값마다 늘리고 줄이는 곳\n- 책임자 절은 기관마다 DIVFACT\n\n## 구분 기준 자리표\n- 다른 낱말 KEEPFACT\n\n## 표\n- 표 이야기 TABLEFACT\n"
    kept = F.without(F.body(text), F.DIVISION_SECTION)
    assert "FORMFACT" in kept and "TABLEFACT" in kept and "KEEPFACT" in kept and "DIVFACT" not in kept and "값마다 늘리고" not in kept
    pinned = {**G.snapshot(), "form": {"sha1": "s", "text": text, "key": "시험", "name": "시험 양식"}}
    p, used = HL.prompt("CONTRACT", ["graph"], {"x": 1}, pinned)
    assert "FORMFACT" in p and "DIVFACT" not in p and used["form"] == "s"
    only = "# 양식 정보 — 시험\n\n## 구분 기준 자리\n- 책임자 절은 기관마다 DIVFACT\n\n## 표\n-\n"
    assert F.body(only) and F.without(F.body(only), F.DIVISION_SECTION) == ""
    p2, used2 = HL.prompt("CONTRACT", ["graph"], {"x": 1}, {**G.snapshot(), "form": {"sha1": "s", "text": only, "key": "시험", "name": "시험 양식"}})
    assert "양식 정보" not in p2 and "form" not in used2


# ---- 양식별 코멘트(spec_구분_기준 ② §18) — 「구분 기준 자리」 절 끝의 목록 --------------------------------------------------------

def test_comments_are_appended_to_the_division_section():
    line = F.comment_line("  첫\n코멘트\t글   끝 ")
    assert line == "첫 코멘트 글 끝" and len(F.comment_line("가" * 500)) == 500
    for bad in ("", " \n\t", None, "가" * 501):
        with pytest.raises(ValueError):
            F.comment_line(bad)
    # 절 없음 → 글 끝에 절 + 머리 줄 + 코멘트
    t1 = F.add_comment(TEXT, line, "2026-11-11")
    assert t1 == f"{TEXT.rstrip()}\n\n## {F.DIVISION_TITLE}\n\n{F.COMMENT_HEAD}\n- (2026-11-11) 첫 코멘트 글 끝\n"
    assert F.comments(TEXT) == [] and F.comments(t1) == [{"date": "2026-11-11", "text": "첫 코멘트 글 끝"}]
    # 머리 줄이 있으면 마지막 코멘트 줄 뒤 — 뒤의 다른 절은 그대로
    t2 = F.add_comment(t1 + "\n## 표\n- 표 이야기\n", "둘째", "2026-11-12")
    assert [x["text"] for x in F.comments(t2)] == ["첫 코멘트 글 끝", "둘째"] and t2.count(F.COMMENT_HEAD) == 1
    assert "- (2026-11-11) 첫 코멘트 글 끝\n- (2026-11-12) 둘째\n\n## 표\n- 표 이야기\n" in t2 and t2.endswith("## 표\n- 표 이야기\n")
    # 절은 있고 머리 줄이 없음(뼈대) → 절 끝에 머리 줄부터, 나머지 글은 그대로
    sk = F.suggest("새 양식.hwpx")["text"]
    t3 = F.add_comment(sk, "뼈대에", "2026-11-11")
    added = f"\n{F.COMMENT_HEAD}\n- (2026-11-11) 뼈대에\n"
    assert f"## {F.DIVISION_TITLE}\n-\n{added}\n## 헤딩이 아닌 것" in t3 and t3.replace(added, "") == sk
    # 머리 줄 앞의 날짜 줄 · 주석 안 · 날짜 없는 줄 · 다른 절의 줄은 코멘트가 아니다
    odd = (f"## 구분 기준 자리\n- (2026-01-01) 머리 줄 앞\n{F.COMMENT_HEAD}\n<!-- - (2026-01-02) 주석 안 -->\n- (2026-01-03) 진짜\n- 날짜 없음\n\n"
           "## 표\n- (2026-01-04) 다른 절\n")
    assert F.comments(odd) == [{"date": "2026-01-03", "text": "진짜"}]
    assert "- (2026-01-03) 진짜\n- (2026-01-05) 뒤\n- 날짜 없음\n" in F.add_comment(odd, "뒤", "2026-01-05")   # 마지막 코멘트 줄 바로 뒤
    # 코멘트로 처음 생기는 양식 글 — 제목 + 조건 블록뿐(빈 뼈대 절 없음): 구분 기준 검토에는 가고 헤딩 추출 프롬프트에는 양식 절이 없다
    b = F.bare("연차보고서", "aa11")
    assert b["key"] == "연차보고서" and b["text"].startswith("# 양식 정보 — 연차보고서\n\n```json\n") and b["text"].endswith("\n```\n")
    assert F.parse(b["text"]) == {"name": "연차보고서", "names": ["*연차보고서*"], "sha256": ["aa11"]} and F.body(b["text"]) == ""
    made = F.add_comment(b["text"], "글 COMMENTFACT", "2026-11-11")
    assert made.count("## ") == 1 and "COMMENTFACT" in F.body(made) and F.without(F.body(made), F.DIVISION_SECTION) == ""
    p, used = HL.prompt("CONTRACT", ["graph"], {"x": 1}, {**G.snapshot(), "form": {"sha1": "s", "text": made, "key": "연차보고서", "name": "연차보고서"}})
    assert "양식 정보" not in p and "form" not in used


def test_repo_annual_report_form_matches_and_lists_its_comments(monkeypatch):
    """forms/연차보고서.md — 「구분 기준 자리」 절(끝에 코멘트 목록)을 든 양식 정보: 서식 파일 이름에 맞고 코멘트가 읽히며, 그 절은 헤딩 추출 프롬프트에 안 간다."""
    monkeypatch.delenv("NFM_FORMS")
    f = F.get("연차보고서")
    assert f["broken"] is None and f["size"] <= F.TEXT_MAX and F.parse(f["text"])["names"] == ["*연차보고서*"]
    m = F.match("1. 산업기술혁신사업 연차보고서 서식_260319.hwpx")
    assert m["key"] == "연차보고서" and m["how"] == "name"
    cs = F.comments(f["text"])
    assert cs and cs[0]["date"] == "2026-11-11" and cs[0]["text"].startswith("연구개발 목표 및 내용은")
    b = F.body(f["text"])
    kept = F.without(F.without(b, F.DIVISION_SECTION), F.LINK_SECTION)   # 헤딩 추출 프롬프트에 가는 글 — 「자리 연결」 절(연결 코멘트: spec_병합 ② §5-3)도 뺀다
    assert F.COMMENT_HEAD in b and "(엔진)" in b and "코멘트" not in kept and "(엔진)" not in kept and "<!--" not in b
    links = F.comments(f["text"], F.LINK_SECTION)   # 연결 코멘트는 「자리 연결」 절의 목록 — 구분 기준 코멘트와 안 섞인다
    assert links and links[0]["text"].startswith("2-1 기술개발 추진 일정") and all(c["text"] != links[0]["text"] for c in cs)
    assert "자리 연결" in F.section(b, F.LINK_SECTION) and F.blank_fps(f["text"]) and F.blank_fps("# 조건 없는 글") == []   # 빈 서식의 내용 지문(표 대응의 예시 판정 — 조건 parse 와 따로)


def test_table_tools_get_the_form_table_section(c):
    """양식 정보의 「표」 절 = 표 도구의 「양식 지침」: 표 지침 묶음 글(에이전트 입력)에 [양식 지침] 으로, 수식 판정·표 만들기 지침 글에 맨 앞 묶음으로 — 맞는 양식이 없으면 전과 같다."""
    from app import table_agent, table_excel_llm, table_llm
    d = _open_ready(c, SMALL)
    a0 = c.get(f"/api/docs/{d}/headings/tables/_common/agent").json()
    assert a0["form"] == "" and "[양식 지침]" not in a0["prompt"]
    F.save("시험", TABLE_TEXT, expect="")
    a = c.get(f"/api/docs/{d}/headings/tables/_common/agent").json()
    assert a["form"].startswith("## 표 — 작성 기준") and "TABLEFACT" in a["form"] and "COVERFACT" not in a["form"]
    assert a["prompt"].index("[양식 지침]") < a["prompt"].index("TABLEFACT") < a["prompt"].index("[공통 지침]")
    assert F.table_guide(server._sess(d)) == a["form"]
    g = table_excel_llm.guide_text("공통", "", form=a["form"])
    assert g.index("### 양식 표 지침") < g.index("TABLEFACT") < g.index("### 공통 표 지침\n공통") and table_excel_llm.guide_text("", " ", form="") == "(없음)"
    g2 = table_llm.guide_text("공통", "", "이번만", form=a["form"])
    assert g2.index("### 문서 양식의 표 지침") < g2.index("TABLEFACT") < g2.index("### 공통 표 지침\n공통") < g2.index("### 이번 지침\n이번만")
    assert "[양식 지침]" not in table_agent.prompt(None, {"instructions": ""}, None, tid="_common", form="  ")
