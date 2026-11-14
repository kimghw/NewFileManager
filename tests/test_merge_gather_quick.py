"""취합 간단 모드의 서버 쪽(spec_취합 ② §8 — `server.divisions_adopt` · `merge_gather_api.gather_part_auto`·`_name_org`): 구조 확인 · 파일 이름 대조 · 반영할 기관 자동 지정.
자료는 test_merge_gather_api 와 같다(gather_data — 값을 반영한 양식 = 기준본, 그 사본을 고쳐 다시 연 것 = 기관 문서). 화면 쪽은 tools/smoke_gather_quick_ui.py."""
import pytest
from fastapi.testclient import TestClient

import gather_data as D
import merge_data as M
from app import server
from app import merge_gather_api as GA
from test_merge_gather_api import _analysed, _bytes, _edit_a, _edit_b, _row, _texts, _upload

J1, J2, LEAD = D.J1, D.J2, D.LEAD


@pytest.fixture
def client():
    server.DOCS.clear()
    for box in (GA._MEM, GA._BLOB, GA._FRAMES, GA._LINKS, GA._JUDGE, GA._PLANS, GA._DROPS):
        box.clear()
    return TestClient(server.app)


def _adopted_master(c, name="취합본.hwpx"):
    """간단 모드의 목적 문서 — 기준본 바이트를 **새로** 올린 것(반영 기록 없음) → 값 저장 → 구조 확인 → 분석 → 기준본."""
    b = D.base()["side"]
    to = _upload(c, name, b["bytes"])
    assert c.put(f"/api/docs/{to}/divisions/settings", json={"values": D.VALUES}).status_code == 200
    r = c.post(f"/api/docs/{to}/divisions/adopt", json={})
    assert r.status_code == 200 and r.json()["adopted"] is True, r.text
    _analysed(to, b["graph"], b["tables"])
    r = c.post(f"/api/docs/{to}/gather/frame")
    assert r.status_code == 200, r.text
    return to


def _part(c, to, name, edit):
    pid = _upload(c, name, _bytes(edit))
    _analysed(pid)
    assert c.put(f"/api/docs/{to}/gather/parts/{pid}", json={}).status_code == 200
    return pid


# ---- 구조 확인(§8-4) ----------------------------------------------------------------------------------------------

def test_adopt_records_applied_when_the_structure_already_fits_and_unblocks_the_frame(client):
    c = client
    b = D.base()["side"]
    to = _upload(c, "프레임.hwpx", b["bytes"])
    got = c.get(f"/api/docs/{to}/divisions/read").json()["read"]
    assert got["orgs"]["lead"] == LEAD and got["orgs"]["joint"] == [J1, J2] and got["stages"] == [2]   # 간단 모드는 값을 문서에서 읽는다
    assert c.post(f"/api/docs/{to}/divisions/adopt", json={}).status_code == 400   # 값이 없으면
    assert c.put(f"/api/docs/{to}/divisions/settings", json={"values": D.VALUES}).status_code == 200
    plan = c.post(f"/api/docs/{to}/divisions/plan", json={}).json()
    nothing = c.post(f"/api/docs/{to}/divisions/apply", json={"planId": plan["planId"]}).json()
    assert nothing["nothing"] is True and server._sess(to).division["applied"] is None   # 이 빈 곳을 메운다 — 반영은 기록을 안 남긴다
    _analysed(to, b["graph"], b["tables"])
    assert c.post(f"/api/docs/{to}/gather/frame").json()["detail"]["reason"] == "notApplied"
    rev = server._sess(to).rev
    r = c.post(f"/api/docs/{to}/divisions/adopt", json={}).json()
    a = server._sess(to).division["applied"]
    assert r["adopted"] is True and r["why"] is None and r["rev"] == rev and r["summary"]["already"] > 0 and r["summary"]["changes"] == 0
    assert a["adopted"] is True and a["rev"] == rev and a["values"]["orgs"]["joint"] == [J1, J2] and a["planId"]
    assert server._sess(to).rev == rev   # 문서는 안 바뀐다
    again = c.post(f"/api/docs/{to}/divisions/adopt", json={}).json()
    assert again["adopted"] is False and again["why"] == "applied" and server._sess(to).division["applied"] == a   # 한 번만
    plan = c.post(f"/api/docs/{to}/divisions/plan", json={}).json()
    assert plan["summary"]["changes"] == 0 and plan["summary"]["groups"] == 0   # 채택 뒤의 계획(다시 본뜨지 않음)도 할 일 없음
    r = c.post(f"/api/docs/{to}/gather/frame")
    assert r.status_code == 200 and r.json()["frame"]["stale"] is False, r.text
    assert c.get(f"/api/docs/{to}/divisions").json()["applied"]["adopted"] is True


def test_adopt_refuses_a_blank_form_and_values_that_do_not_fit(client):
    c = client
    blank = _upload(c, "양식.hwpx", M.PLAN_FORM.read_bytes())
    assert c.put(f"/api/docs/{blank}/divisions/settings", json={"values": D.VALUES}).status_code == 200
    r = c.post(f"/api/docs/{blank}/divisions/adopt", json={}).json()
    assert r["adopted"] is False and r["why"] == "changes" and r["applied"] is None and server._sess(blank).division["applied"] is None
    to = _upload(c, "프레임.hwpx", D.base()["side"]["bytes"])
    fewer = {**D.VALUES, "orgs": {**D.VALUES["orgs"], "joint": [J1], "nonprofit": [False, True]}}   # 기관 하나가 빠진 값 — 문서의 다라연 절이 남는다
    r = c.post(f"/api/docs/{to}/divisions/adopt", json={"values": fewer}).json()
    assert r["adopted"] is False and r["why"] in ("changes", "unresolved") and server._sess(to).division["applied"] is None


# ---- 이름 대조(§8-3) ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, keys, base, others, want", [
    ("가나대_연구개발계획서.hwpx", ["인텍", "가나대", "다라연"], "", (), "가나대"),
    ("가나대 다라연 공동.hwpx", ["인텍", "가나대", "다라연"], "", (), None),                      # 둘이 걸리면 못 정함
    ("한국대병원 작성본.hwpx", ["한국대", "한국대병원"], "", (), "한국대병원"),                   # 긴 이름 안의 짧은 이름은 따로 안 걸림
    ("한국대 작성본.hwp", ["한국대", "한국대병원"], "", (), "한국대"),
    ("(주)인텍_계획서.hwpx", ["인텍", "가나대"], "", (), "인텍"),                                 # ㈜·빈칸은 org_key 가 뗀다
    ("인 텍 계획서.hwpx", ["인텍"], "", (), "인텍"),
    ("인텍과제_가나대.hwpx", ["인텍", "가나대"], "인텍과제_취합본.hwpx", (), "가나대"),           # 취합본 이름에 든 열쇠는 안 셈
    ("인텍과제_가나대.hwpx", ["인텍", "가나대", "다라연"], "", ("인텍과제_가나대.hwpx", "인텍과제_다라연.hwpx"), "가나대"),   # 모든 기관 문서 이름에 든 열쇠
    ("인텍과제_인텍.hwpx", ["인텍", "가나대"], "", ("인텍과제_인텍.hwpx", "인텍과제_가나대.hwpx"), None),
    ("A.hwpx", ["A", "가나대"], "", (), None),                                                    # 한 글자 열쇠는 안 봄
    ("계획서.hwpx", ["인텍", "가나대"], "", (), None),
    ("가나대.hwpx".replace("가", "가"), ["가나대"], "", (), "가나대"),
])
def test_name_org(name, keys, base, others, want):
    assert GA._name_org(name, keys, base, others) == want


def test_name_org_reads_decomposed_hangul_file_names():
    import unicodedata
    assert GA._name_org(unicodedata.normalize("NFD", "가나대_작성.hwpx"), ["가나대", "인텍"]) == "가나대"   # macOS 에서 온 이름


# ---- 자동 지정(§8-3) ----------------------------------------------------------------------------------------------

def test_auto_assigns_by_file_name_then_by_recommendation_and_keeps_people_choices(client):
    c = client
    to = _adopted_master(c)
    a = _part(c, to, f"{J1}_작성.hwpx", _edit_a)        # 이름으로
    b = _part(c, to, "기관2_작성.hwpx", _edit_b)        # 이름에 기관이 없음 → 추천(다라연 자리에 쓴 글이 가장 많음)
    v = c.post(f"/api/docs/{to}/gather/parts/{a}/auto").json()
    assert v["auto"] == {"part": a, "org": J1, "by": "name", "why": None}
    assert _row(v, a)["orgs"] == [J1] and _row(v, a)["orgsBy"] == "name"
    v = c.post(f"/api/docs/{to}/gather/parts/{b}/auto").json()
    assert v["auto"]["by"] == "recommend" and v["auto"]["org"] == J2 and _row(v, b)["orgsBy"] == "recommend", v["auto"]
    assert GA._store(to)["parts"][b]["orgsBy"] == "recommend"
    again = c.post(f"/api/docs/{to}/gather/parts/{b}/auto").json()["auto"]
    assert again["why"] == "assigned" and again["org"] == J2   # 이미 정함 — 그대로
    v = c.put(f"/api/docs/{to}/gather/parts/{b}", json={"orgs": [LEAD]}).json()
    assert _row(v, b)["orgs"] == [LEAD] and _row(v, b)["orgsBy"] is None and "orgsBy" not in GA._store(to)["parts"][b]   # 사람이 바꾸면 사람 지정
    assert c.post(f"/api/docs/{to}/gather/parts/{b}/auto").json()["auto"]["why"] == "assigned"
    assert _row(c.get(f"/api/docs/{to}/gather").json(), b)["orgs"] == [LEAD]


def test_auto_leaves_the_part_unassigned_when_nothing_decides(client, monkeypatch):
    c = client
    to = _adopted_master(c)
    p = _part(c, to, "기관_작성.hwpx", _edit_a)
    real = GA._judged

    def tie(*a, **k):   # 두 기관의 작성 내용 수가 같다
        out = real(*a, **k)
        return {**out, "recommend": {**(out["recommend"] or {"org": J1, "n": 1}), "tie": True}}
    monkeypatch.setattr(GA, "_judged", tie)
    GA._JUDGE.clear()
    r = c.post(f"/api/docs/{to}/gather/parts/{p}/auto").json()
    assert r["auto"] == {"part": p, "org": None, "by": None, "why": "tie"} and _row(r, p)["orgs"] == []
    monkeypatch.setattr(GA, "_judged", real)
    GA._JUDGE.clear()
    blank = _upload(c, "빈문서.hwpx", D.base()["side"]["bytes"])   # 기준본에서 나왔지만 아무것도 안 씀 — 추천이 없다
    _analysed(blank)
    c.put(f"/api/docs/{to}/gather/parts/{blank}", json={})
    r = c.post(f"/api/docs/{to}/gather/parts/{blank}/auto").json()
    assert r["auto"]["org"] is None and r["auto"]["why"] == "noOrg" and _row(r, blank)["orgs"] == []
    assert c.post(f"/api/docs/{to}/gather/parts/nonexistent0/auto").status_code in (400, 404)


def test_auto_without_a_frame_reports_why(client):
    c = client
    b = D.base()["side"]
    to = _upload(c, "취합본.hwpx", b["bytes"])
    p = _part(c, to, "기관_작성.hwpx", _edit_a)
    r = c.post(f"/api/docs/{to}/gather/parts/{p}/auto").json()
    assert r["auto"]["org"] is None and r["auto"]["why"] == "noFrame"
    q = _part(c, to, f"{J2} 작성.hwpx", _edit_b)   # 이름으로 정하는 것은 기준본이 없어도 된다(기관은 입력 중인 값)
    assert c.put(f"/api/docs/{to}/divisions/settings", json={"values": D.VALUES}).status_code == 200
    r = c.post(f"/api/docs/{to}/gather/parts/{q}/auto").json()
    assert r["auto"] == {"part": q, "org": J2, "by": "name", "why": None}


def test_quick_mode_path_end_to_end_puts_each_part_in_its_own_place(client):
    """간단 모드의 서버 쪽 차례: 새로 올린 프레임 → 구조 확인 → 기준본 → 기관 문서 등록 → 자동 지정 → 자리 연결 → 계획 → 반영. 기관 문서는 그대로 · 다시 계획하면 0."""
    c = client
    to = _adopted_master(c)
    a, b = _part(c, to, f"{J1}.hwpx", _edit_a), _part(c, to, "두번째.hwpx", _edit_b)
    before = {p: server._sess(p).doc.save() for p in (a, b)}
    for p in (a, b):
        assert c.post(f"/api/docs/{to}/gather/parts/{p}/auto").json()["auto"]["org"] in (J1, J2)
        assert c.post(f"/api/docs/{to}/gather/parts/{p}/links").status_code == 200
        P = c.post(f"/api/docs/{to}/gather/parts/{p}/plan").json()
        assert P["todo"] > 0, P
        r = c.post(f"/api/docs/{to}/gather/parts/{p}/apply", json={"planId": P["planId"]})
        assert r.status_code == 200, r.text
    texts = _texts(to)
    assert any(f"{J1} 1차년도 개발 목표" in t for t in texts) and any(f"{J2} 1차년도 개발 목표" in t for t in texts)
    assert any(f"{J1}가 쓴 필요성" in t for t in texts) and not any(f"{J2}가 쓴 필요성" in t for t in texts)   # 공통 자리는 먼저 온 문서 — 뒤의 것은 겹침
    for p in (a, b):
        assert c.post(f"/api/docs/{to}/gather/parts/{p}/plan").json()["todo"] == 0
        assert server._sess(p).doc.save() == before[p]
