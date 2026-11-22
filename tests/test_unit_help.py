"""도구 설명(spec_워크플로우 ② §18-15 — app/unit_help.py): 조립에 놓을 수 있는 줄마다 쉬운 글이 있는지 · 글이 단위의 값(문서 바뀜 · 유료 · 사람이 하는 일)과 어긋나지 않는지 ·
글의 기준이 서버의 자동 진행인지(핵심 문구) · 화면 말 규칙(쓰지 않는 말) · 순수 모듈인지 · 조립 화면의 응답(units[].help)이 그 틀의 글을 싣는지.
화면이 그 글과 단위의 값으로 짓는 칸(누가 · 문서 · 어느 문서에 …)은 화면 검사가 본다(tools/smoke_flow_compose_ui.py ⑧)."""
import ast
import re
from pathlib import Path

import pytest

from app import custom_tasks as C
from app import unit_help as H
from app import workflow_units as U

APP = Path(H.__file__).parent
BANNED = ("모듈", "갈래", "라벨", "공백", "무료")   # 화면 글에 쓰지 않는 말(CLAUDE.md 「화면 말」 — 도구 · 다른 서식 · 이름 · 빈칸/여백) + 「무료」(paid 가 비어도 유료 길이 있는 줄이 있다)
DOC_CHANGES = re.compile(r"(문서|취합본)(가|이|를|도)?\s*(바뀝니다|바꿉니다)")   # 「문서가 바뀝니다」 · 「원본 문서를 바꿉니다」 · 「취합본이 바뀝니다」 — 문서를 바꾼다는 말
LIMIT = {"easy": 90, "first": 110, "care": 200, "see": 80, "why": 90, "eg": 80, "who": 50}   # 설명 열(320px)에서 한눈에 읽히는 길이 — 넘으면 글을 줄인다


def _offered():
    """틀(가족)마다 조립에 놓을 수 있는 줄 → [(가족, key, 단위)] — 맨 앞 묶음에 저절로 서는 준비 줄은 빼고(API 의 세 목록과 같은 줄: test_compose_response_carries_help 가 맞춘다)."""
    out = []
    for k in (*U.COMMON, *U.RELAY):   # 이관형 = 같이 쓰는 줄 + 이관의 줄
        if k not in C.AUTO_UNITS:
            out.append(("relay", k, U.unit(k, "relay")))
    for k in (*C.GATHER_UNITS, "hand"):   # 취합형 — 조립의 「사람이 하는 일」 은 같이 쓰는 단위(붙박이 취합의 hand = 「기관에 배포 · 회수」 는 줄로 놓지 않는다: custom_tasks_api.gather_units)
        out.append(("gather", k, U.COMMON["hand"] if k == "hand" else U.unit(k, "gather")))
    for k in C.SINGLE_UNITS:   # 문서 하나
        out.append(("single", k, U.COMMON["hand"] if k == "hand" else U.SINGLE[k]))
    return out


OFFERED = _offered()
IDS = [f"{f}.{k}" for f, k, _ in OFFERED]


def test_pure_module():
    """글 파일은 다른 앱 코드를 가져오지 않는다(조립 저장 · 화면 응답 어느 쪽에서도 부담 없이 읽게)."""
    tree = ast.parse((APP / "unit_help.py").read_text(encoding="utf-8"))
    assert [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))] == []


@pytest.mark.parametrize("fam,key,u", OFFERED, ids=IDS)
def test_every_offered_line_has_help(fam, key, u):
    hp = H.of(fam, key)
    assert hp is not None, f"{fam}.{key} — 조립에 놓을 수 있는 줄인데 도구 설명 글이 없습니다(app/unit_help.py 에 더하세요)"
    assert set(hp) == set(H.FIELDS) and all(isinstance(v, str) for v in hp.values())
    assert hp["easy"].strip() and hp["see"].strip(), "하는 일(easy) · 결과는 어디서 보나(see)는 줄마다 적습니다"
    assert hp["care"].strip() or hp["why"].strip()
    assert not {k: len(v) for k, v in hp.items() if len(v) > LIMIT[k]}
    for text in hp.values():
        assert not [w for w in BANNED if w in text], text
        assert "\n" not in text and text == text.strip()


@pytest.mark.parametrize("fam,key,u", OFFERED, ids=IDS)
def test_help_agrees_with_unit(fam, key, u):
    """글이 단위의 값과 어긋나지 않는다(astra 2026-11-20): 문서를 안 바꾸는 줄이 문서를 바꾼다고 하지 않고 · 유료 줄은 유료라고 적고 · 사람이 하는 줄은 자동 진행이 어떻게 하는지 적는다.
    (paid 가 빈 줄이 「유료」 라 적는 것은 막지 않는다 — 단추로만 유료인 줄 · 조건부로 유료인 줄이 있다.)"""
    hp, text = H.of(fam, key), " ".join(H.of(fam, key).values())
    if u["change"] != "doc":
        assert not DOC_CHANGES.search(text), f"{fam}.{key}: change={u['change']} 인데 글은 문서를 바꾼다고 합니다"
    if u["paid"]:
        assert "유료" in hp["care"], f"{fam}.{key}: 유료 줄은 「알아 둘 것」 에 유료라고 적습니다"
    if u["kind"] == "hand":
        assert "멈춥니다" in hp["care"] and "했음" in hp["care"]
    if u["kind"] == "pick":
        assert "지나갑니다" in hp["care"] or "기다리지 않" in hp["care"], f"{fam}.{key}: 사람이 하는 줄 — 자동 진행은 기다리지 않는다고 적습니다"


def test_help_matches_the_automatic_run():
    """글의 기준 = 서버의 자동 진행(astra P1 — 등록부의 손으로 할 때 글을 옮기면 자동으로 문서가 바뀌는 줄을 「사람이 눌러야 한다」 고 안내하게 된다)."""
    of = H.of
    for fam in ("relay", "gather"):   # 이관 · 취합의 프로젝트 구성 추출 = 묻지 않고 확정(이미 확정돼 있으면 지나감) · 내용 반영 = 계획대로 바로
        assert "묻지 않고 확정" in of(fam, "config")["care"] and "이미 확정돼 있으면" in of(fam, "config")["care"] and "묻지 않" in of(fam, "apply")["care"]
        assert "계획 보기」 에서 확인하고" not in " ".join(of(fam, "apply").values())
        assert "사람의 확인을 기다리지 않" in of("relay", "plan")["care"]
    assert "원본 문서" in of("relay", "config")["easy"] and "취합본" in of("gather", "config")["easy"]   # 구성의 기준 문서가 틀마다 다르다
    assert "원본 문서에 불러오세요" in of("relay", "configLoad")["care"]   # 불러오기는 지금 연 문서의 입력 칸을 채운다 — 자동 추출이 읽는 것은 원본 문서
    assert "저절로 확정하지 않" in of("single", "values")["care"] and of("single", "values")["who"].startswith("사람이")   # 문서 하나는 사람이 확정
    assert "「반영」 을 눌러야" in of("gather", "drop")["care"]   # 끌어 넣기만은 사람이 「반영」
    for fam, key in (("relay", "division"), ("gather", "division"), ("single", "apply")):   # 줄어드는 항목의 글이 지워진다
        assert "함께 지워집니다" in of(fam, key)["care"], (fam, key)
    assert "간단 모드는 지울 곳이 있으면" in of("gather", "division")["care"]   # 취합 — 일반 자동 진행은 지우고 간단 모드만 멈춘다
    assert "원본 문서에 놓으면" in of("relay", "division")["care"]   # 원본 문서에 놓으면 원본 문서가 바뀐다
    assert "표째로 지웁니다" in of("relay", "guide")["care"] and "그 안에 쓴 글도" in of("relay", "guide")["care"]   # 작성 요령 표 · <참고 N> 자료 표는 안의 글까지(form_cleanup.PATTERNS 의 how 「표째」)
    assert "건너뛰기" in of("relay", "headsLlm")["care"] and "남은 일" in of("single", "headsLlm")["care"]   # 이관 = 건너뜀 · 문서 하나 = 남김
    assert "덮지 않" in of("gather", "plan")["care"] and "겹침" in of("gather", "plan")["care"]   # 취합본에 먼저 있던 글 보호
    assert "보류" in of("gather", "llm")["care"] and "쓸 수 없으면 기본 분석으로" in of("gather", "llm")["care"]   # LLM 을 못 씀 ≠ 답을 못 받음
    assert "이미 올린 기관 문서가 있으면 자동 진행이 멈춥니다" in of("gather", "frame")["care"]   # 낡은 기준본을 저절로 바꾸지 않는다
    assert "유료" in of("single", "adjust")["care"] and "횟수만큼" in of("single", "adjust")["care"] and "유료" in of("single", "adjust")["who"]   # 조건부 비용 · 실행 취소 횟수
    assert "유료" in of("single", "review")["care"] and "유료" in of("single", "review")["who"]
    assert "검산만 하면 문서는 그대로" in of("single", "tableTools")["care"]


def test_see_names_real_screen_places():
    """「결과는 어디서 보나요?」 는 화면에 실제로 있는 이름으로 적는다(astra 2차 — 기관 문서 줄에 없는 「남긴 것 보기」 를 적었었다): 글이 인용한 「…」 이름이 화면 코드에 그 글자로 있다."""
    static = "".join(p.read_text(encoding="utf-8") for p in (APP / "static").glob("*.js")) + (APP / "static" / "index.html").read_text(encoding="utf-8")
    asked = {name for box in H.HELP.values() for hp in box.values() for name in re.findall(r"「([^」]+)」", hp["see"])}
    assert {"연결 목록", "넣기 계획", "기관 작성 내용", "헤딩 추출", "테이블", "템플릿 관계", "문서 반영 상태", "변경 계획 보기", "기준본 내려받기", "했음", "확정함"} <= asked
    lost = sorted(n for n in asked if n not in static and n not in ("헤딩 · 표 분석",))   # 「헤딩 · 표 분석」 = 등록부의 줄 이름(대시보드가 그 이름으로 그린다)
    assert not lost, f"화면 코드에 없는 이름 — {lost}"
    assert "남긴 것 보기" not in asked


def test_no_orphan_help():
    """글이 있는 줄은 모두 그 틀에 놓을 수 있는 줄이다(없어진 줄 · 그 틀에 없는 줄의 글이 남지 않게) · 문서 하나는 제 줄만(같이 쓰는 줄로 새지 않는다)."""
    offered = {fam: {k for f, k, _ in OFFERED if f == fam} for fam in ("relay", "gather", "single")}
    assert set(H.COMMON) <= offered["relay"] and set(H.RELAY) <= offered["relay"] - set(H.COMMON)   # 같이 쓰는 줄의 글 = 이관형의 글
    assert set(H.GATHER) <= offered["gather"] and set(H.SINGLE) <= offered["single"]
    assert H.of("single", "config") is None and H.of("single", "division") is None
    assert H.of("relay", "hand3") == H.of("relay", "hand") == H.of("gather", "hand") == H.of("single", "hand") and H.of("relay", "nope") is None
    for auto in ("files", "open", "later"):   # 사람이 놓지 않는 줄(준비 · 아직 없는 단계)은 설명 목록에 없다
        assert all(H.of(fam, auto) is None for fam in ("relay", "gather", "single")), auto
    assert H.of("gather", "link") != H.of("relay", "link")   # 같은 key 도 틀마다 글이 다르다


def test_compose_response_carries_help():
    """조립 화면의 응답(GET /api/tasks?v=2 의 몸) — 세 틀의 고를 줄마다 help(쉬운 글)가 그 틀의 글로 실린다(astra: 시험의 출발점은 API 의 고를 수 있는 줄) · 그 줄 = 이 시험이 글을 본 줄."""
    from app import custom_tasks_api as A
    body = A.tasks_get("2")
    lists = {"relay": body["units"], "gather": body["byShape"]["gather"]["units"], "single": body["byShape"]["single"]["units"]}
    for fam, units in lists.items():
        keys = [u["key"] for u in units]
        assert len(keys) == len(set(keys)) and set(keys) == {k for f, k, _ in OFFERED if f == fam}, (fam, keys)
        for u in units:
            assert u.get("help") == H.of(fam, u["key"]) and u["help"]["easy"], (fam, u["key"])
    assert {fam: len(units) for fam, units in lists.items()} == {"relay": 20, "gather": 12, "single": 14}   # 지금의 수 — 줄을 더하면 이 수와 글을 함께 고친다(19 = 2026-11-22 「넣은 뒤 템플릿 · 서식 정리」 · 20 = 2026-11-23 「캡션 맞추기」 · gather 12 = 같은 날 취합의 그 도구)
    by = lambda fam: {u["key"]: u["help"]["easy"] for u in lists[fam]}  # noqa: E731
    assert by("relay")["link"] != by("gather")["link"] and by("relay")["plan"] != by("single")["plan"] and by("relay")["heads"] != by("single")["heads"]   # 같은 key 도 틀마다 다른 글
    assert by("gather")["hand"] == by("relay")["hand"] == by("single")["hand"] and "기관에 나눠" not in by("gather")["hand"]   # 취합의 「사람이 하는 일」 ≠ 붙박이 취합의 「기관에 배포 · 회수」
    assert {u["key"]: u["name"] for u in lists["gather"]}["hand"] == "사람이 하는 일"


def test_hand_line_stops_like_its_help_says():
    """도구 설명은 세 틀 모두 「「했음」 기록이 없으면 자동 진행이 여기서 멈춥니다」 라 한다 — 조립한 정의의 그 줄(hand1 …)이 어느 틀에서나 실제로 멈추는 단위(kind hand)여야 한다.
    (astra 2차 P1 — 취합형의 hand1 이 붙박이 취합의 「기관에 배포 · 회수」(kind pick — 지나감)로 찾아져 「했음」 없이 지나갔다: ea 가 workflow_units.unit 에서 고침 2026-11-20.)"""
    assert "멈춥니다" in H.of("gather", "hand")["care"]
    for fam in ("relay", "gather", "single"):
        assert U.unit("hand1", fam)["kind"] == "hand", fam
    assert U.unit("hand", "gather")["kind"] == "pick"   # 대조 — 붙박이 취합의 번호 없는 hand(배포 · 회수: 앱 밖의 일)는 지금대로 지나간다


# ---------------------------------------------------------------- 전용 표시 — 그 도구가 받는 문서(spec_워크플로우 ② §18-17 · 2026-11-20 사용자 「도구에 *** 전용 이라고 명시를 해야 한다고봄」)
@pytest.mark.parametrize("fam,key,u", OFFERED, ids=IDS)
def test_only_is_decided_for_every_offered_line(fam, key, u):
    """조립에 놓을 수 있는 줄마다 「어느 문서 전용인가」 가 정해져 있다(전용이 아니면 빈 글 — 빠뜨린 줄이 없게) · 응답에 실리는 꼴 · 글 규칙."""
    kind = H.only_kind(fam, key)
    assert kind is not None, f"{fam}.{key} — 전용 표시가 없습니다(app/unit_help.py ONLY 에 더하세요: 문서를 가리지 않으면 빈 글)"
    assert kind in ("", *H.ONLY_TEXT)
    got = H.only(fam, key)
    if not kind:
        assert got is None
        return
    assert got == {"kind": kind, "label": H.ONLY_TEXT[kind][0], "why": H.ONLY_TEXT[kind][1]} and got["label"].endswith(" 전용") and len(got["why"]) <= 130
    for text in (got["label"], got["why"]):
        assert not [w for w in BANNED if w in text] and "\n" not in text and text == text.strip()


def test_only_follows_the_code_it_names():
    """전용의 근거는 코드다 — 구분 기준 엔진을 쓰는 줄 = 등록부의 그 줄이 도구 「프로젝트 구성」 을 쓴다 · 엔진이 지원하는 양식 · 이관 · 취합의 문서 쌍이 바뀌면 이 시험이 떨어져 글을 다시 보게 한다."""
    from app import agent_notes, custom_tasks
    from app.division_profiles import rnd
    assert set(rnd.SUPPORTED) == {"연구개발계획서", "연차보고서"}   # 엔진이 지원하는 양식(연구개발계획서 = 화면의 「사업계획서」)
    F = custom_tasks.FILES
    assert H.ONLY_TEXT["rnd"][0] == f"{F['plan']} · {F['report']} 전용"
    assert custom_tasks.PAIRS == (("plan", "report"),) and H.ONLY_TEXT["relay"][0] == f"{custom_tasks.kind_name('plan')} → {custom_tasks.kind_name('report')} 전용"
    assert custom_tasks.GATHER_PAIRS == (("part", "plan"),) and H.ONLY_TEXT["gather"][0] == f"{custom_tasks.kind_name('part')} → {custom_tasks.kind_name('plan')} 전용"
    tools = agent_notes.tool_map()
    for fam, key, u in OFFERED:
        if u["kind"] == "hand":
            assert H.only_kind(fam, key) == ""
            continue
        engine = any(t["id"] == "division" for t in tools[fam][key]["tools"])   # 등록부의 그 줄이 도구 「프로젝트 구성(구분 기준)」 을 쓰나
        assert (H.only_kind(fam, key) == "rnd") == engine, f"{fam}.{key}: 구분 기준 엔진을 쓰는 줄만 「사업계획서 · 연차보고서 전용」 입니다"
        if fam == "relay":
            assert (H.only_kind(fam, key) == "relay") == (u["place"] == "pair"), f"{fam}.{key}: 이관형의 원본 → 목적 줄만 「사업계획서 → 연차보고서 전용」 입니다"
        if fam == "gather" and u["place"] == "pair":
            assert H.only_kind(fam, key) == "gather", f"{fam}.{key}: 취합의 원본 → 목적 줄은 「기관 문서 → 사업계획서 전용」 입니다"
    assert H.only_kind("single", "config") is None and H.only_kind("relay", "hand3") == "" and H.only("relay", "heads") is None   # 문서 하나는 제 줄만 · 사람이 하는 일 · 문서를 가리지 않는 줄


def test_compose_response_carries_only():
    from fastapi.testclient import TestClient

    from app import server
    T = TestClient(server.app).get("/api/tasks", params={"v": "2"}).json()
    by = {"relay": T["units"], "gather": T["byShape"]["gather"]["units"], "single": T["byShape"]["single"]["units"]}
    for fam, units in by.items():
        for u in units:
            assert u.get("only") == H.only(fam, u["key"]), (fam, u["key"])
    assert {u["key"]: (u["only"] or {}).get("label") for u in by["relay"] if u.get("only")} == {
        "configLoad": "사업계획서 · 연차보고서 전용", "config": "사업계획서 · 연차보고서 전용", "division": "사업계획서 · 연차보고서 전용", "take": "사업계획서 · 연차보고서 전용",   # take = 「넣을 구성 선택」(프로젝트 구성의 값을 고른다)
        "zonePrune": "사업계획서 · 연차보고서 전용",   # 빈 구역 지우기 = 구분 기준 엔진의 묶음(② §18-23)
        "link": "사업계획서 → 연차보고서 전용", "llm": "사업계획서 → 연차보고서 전용", "plan": "사업계획서 → 연차보고서 전용", "gaps": "사업계획서 → 연차보고서 전용",
        "tableMap": "사업계획서 → 연차보고서 전용", "apply": "사업계획서 → 연차보고서 전용"}

