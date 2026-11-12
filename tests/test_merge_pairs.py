"""자리 연결(spec_병합 ② §0-1 ①②③ · §4 · §9 정답지 시험) — app/merge_pairs.py."""
import pytest

import merge_data as M
from app import merge_pairs as P

V = {"stages": [2], "orgs": {"lead": "인텍㈜", "joint": ["가나대", "다라연"]}, "period": {"start": "2026-03-01", "end": "2027-12-31"}, "current": 1}


def test_values_diff_orgs_by_name_and_ignores_current():
    same = {**V, "orgs": {"lead": "인텍", "joint": ["다라연", "가나대"]}, "current": 2}   # ㈜·차례·당해 차년도는 다른 것이 아니다
    assert P.values_diff(V, same) == []
    assert [d["what"] for d in P.values_diff(V, {**V, "stages": [1, 1], "orgs": {"lead": "인텍", "joint": ["가나대"]}})] == ["stages", "orgs"]


def _g(key, dim="org", kind="paragraph", path=(), label="", ctx=None, sig=None, inner=(), items=()):
    s = {"key": key, "dim": dim, "kind": kind, "path": list(path), "label": label, "ctx": {"year": None, "org": None, **(ctx or {})},
         "items": [{"value": v, "id": f"{key}-{i}", "text": v, "ident": ident} for i, (v, ident) in enumerate(items)]}
    if sig is not None:
        s["table"] = {"id": "t" + key, "sig": list(sig)}
    else:
        s["inner"] = list(inner)
    return s


def test_pair_context_gates_and_item_identity():
    orgs = [("주관", ("org", "인텍")), ("공동1", ("org", "가나대"))]
    to = [_g("T1", path=["다음연도 연구개발비 사용계획"], label="주관연구개발기관 : ]", ctx={"year": 2}, items=orgs)]
    frm = [_g("F1", path=["연구개발비 사용계획", "연구개발기관별 사용계획"], label="주관연구개발기관 : ]", items=[("주관", ("org", "인텍")), ("공동2", ("org", "가나대"))]),
           _g("F2", path=["연구개발비 사용계획"], label="주관연구개발기관 : ]", ctx={"year": 1}),   # 맥락 차년도가 다르면 후보가 아니다
           _g("F3", dim="year", path=["연구개발비 사용계획"], label="주관연구개발기관 : ]")]       # 구분이 다르면 후보가 아니다
    r = P.pair(to, frm)
    g = r["groups"][0]
    assert (g["status"], g["from"]["key"], [c["key"] for c in g["candidates"]]) == ("paired", "F1", ["F1"])
    assert [(it["value"], it["from"]["value"]) for it in g["items"]] == [("주관", "주관"), ("공동1", "공동2")]   # 글(공동1·공동2)이 아니라 기관 이름으로
    assert r["counts"] == {"paired": 1, "ambiguous": 0, "toOnly": 0, "fromOnly": 2}


def test_pair_never_picks_between_equal_candidates_and_fixed_wins():
    to = [_g("T", dim="year", kind="cols", path=["사용계획"], sig=["비목", "합계"], items=[("1차년도", ("year", 1)), ("3차년도", ("year", 3))])]
    frm = [_g(k, dim="year", kind="cols", path=["사용계획"], sig=["비목", "합계"], items=[("1차년도", ("year", 1))]) for k in ("A", "B")]
    g = P.pair(to, frm)["groups"][0]
    assert g["status"] == "ambiguous" and g["from"] is None and {c["key"] for c in g["candidates"]} == {"A", "B"}
    g = P.pair(to, frm, fixed={"T": {"from": "B", "source": "user"}})["groups"][0]
    assert (g["status"], g["source"], g["from"]["key"], [it["status"] for it in g["items"]]) == ("paired", "user", "B", ["paired", "noSource"])
    assert P.pair(to, frm, fixed={"T": {"from": None, "source": "user"}})["groups"][0]["status"] == "toOnly"   # 사람이 끊음


@pytest.fixture(scope="module")
def real():
    d = M.real()
    if d is None:
        pytest.skip("실제 작성본 없음")
    s = {side: P.summarize(d[side]["doc"].blocks(), d[side]["graph"], d[side]["tables"], d["values"]) for side in ("to", "from")}
    return s, P.pair(s["to"], s["from"])


def _where(s):
    return " ".join([*s["path"], s["label"]])


def test_real_truth_pairs(real):
    """정답지(FMM 대응표 #16·#28·#31 · 표지): 자동 연결됐거나, 못 정했으면 정답이 후보 3등 안에 있다 — 틀린 묶음으로 자동 연결된 것은 없다."""
    s, r = real
    frm = {x["key"]: x for x in s["from"]}
    truth = [  # (목적 묶음을 고르는 조건, 원본 묶음을 고르는 조건, 자동 연결이어야 하나)
        (lambda t: t["kind"] == "paragraph" and t["dim"] == "org" and "추진 실적" in _where(t), lambda f: f["path"][-1:] == ["개발 내용 및 범위"] and f["ctx"]["year"] == 1, False),
        (lambda t: t["kind"] == "paragraph" and t["dim"] == "org" and "다음연도 연구개발비 사용계획" in _where(t), lambda f: f["kind"] == "paragraph" and "연구개발기관별 사용계획" in _where(f), True),
        (lambda t: t["kind"] == "cols" and "사용계획 총괄표" in _where(t) and t["ctx"]["org"] == "인텍전기전자", lambda f: f["kind"] == "cols" and "사용계획 총괄표" in _where(f) and f["ctx"]["org"] == "인텍전기전자", True),
        (lambda t: t["kind"] == "rows" and t["dim"] == "org" and t["path"][-1:] == ["간접비"], lambda f: f["kind"] == "rows" and f["dim"] == "org" and f["path"][-1:] == ["간접비"], True),
        (lambda t: t["kind"] == "list" and not t["path"] and t["dim"] == "org", lambda f: f["kind"] == "list" and not f["path"], True),
    ]
    for pick_t, pick_f, auto in truth:
        ts =[g for g in r["groups"] if g["to"] and pick_t(next(x for x in s["to"] if x["key"] == g["to"]["key"]))]
        assert ts, "목적 묶음을 못 찾음"
        g = ts[0]
        want = {k for k, f in frm.items() if pick_f(f)}
        assert want, "원본 묶음을 못 찾음"
        if g["status"] == "paired":
            assert g["from"]["key"] in want, (g["to"], g["from"])
        else:
            assert not auto and want & {c["key"] for c in g["candidates"][:3]}, (g["status"], g["to"], g["candidates"][:3])


def test_real_org_tables_pair_inside_their_org(real):
    """기관 절 안의 표(연구개발비 총괄표)는 같은 기관의 원본 표와 이어진다 — 「총괄표」 나 다른 기관의 표가 아니다."""
    s, r = real
    frm = {x["key"]: x for x in s["from"]}
    got = [(g["ctx"]["org"], frm[g["from"]["key"]]["ctx"]["org"]) for g in r["groups"]
           if g["status"] == "paired" and g["kind"] == "cols" and g["to"] and (g["ctx"] or {}).get("org") and "사용계획" in " ".join(g["to"]["path"])]
    assert len(got) >= 6 and all(a == b for a, b in got), got
    for g in r["groups"]:   # 항목 짝은 값이 같은 것끼리
        assert all(it["from"] is None or it["from"]["value"] == it["value"] or g["dim"] == "org" for it in g["items"]), g["id"]


def test_small_pair_runs_without_real_file():
    d = M.small()
    s = {side: P.summarize(d[side]["doc"].blocks(), d[side]["graph"], d[side]["tables"], d["values"]) for side in ("to", "from")}
    r = P.pair(s["to"], s["from"])
    assert sum(r["counts"].values()) == len(r["groups"]) and r["counts"]["paired"] >= 5
    assert all(g["from"] is None or g["status"] in ("paired", "fromOnly") for g in r["groups"])   # 못 정한 묶음에는 원본을 달지 않는다
    assert all("_scopes" not in x and "_anchors" not in x for x in s["to"])
    from app import merge_llm, merge_saved   # 먼저 만들어 둔 LLM 보정·서식 쌍 저장이 이 꼴을 그대로 읽는다
    sent = merge_llm.data(r, s["to"], s["from"])
    assert {t["key"] for t in sent["targets"]} <= {g["id"] for g in r["groups"] if g["status"] in ("ambiguous", "toOnly")}
    assert len({merge_saved.group_key(x, d["values"]["current"]) for x in s["to"]}) > 1
