"""헤딩 추출 고침 후속 시험(2026-11-09 고침 검토에서 나온 것) — 라벨 뿌리 서브 템플릿 인스턴스 · 라벨이 된 부모 투명 ·
칸 안 상자 수 · 쓸 자리뿐인 F 가 S 대표가 되지 않음 · 되돌리기 실패 때 base 유지 · 자동 번호 모양 키.

LLM 은 늘 끈다. 규칙·지침 저장소는 시험마다 임시 폴더(NFM_HEADINGS)."""
import copy
from pathlib import Path

import pytest

from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app.hwpx_doc import HwpxDoc

RND = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _sub_graph(root_role="heading"):
    """① › □ › o,o 인스턴스 3개 — 확정 트리(assign_templates 입력). root_role="label" 이면 뿌리가 구분 라벨(제 템플릿 「[기관] › □ › o」 의 L1 — 2026-11-09 가지 규칙)."""
    fam = {"T1": ("circled", "①"), "T2": ("square", "□"), "T3": ("latin-o", "o")}
    rows = []
    for k in range(3):
        rows += [(f"r{k}", "T1", "root"), (f"s{k}", "T2", f"r{k}"), (f"o{k}a", "T3", f"s{k}"), (f"o{k}b", "T3", f"s{k}")]
    nodes = [{"id": i, "para": i, "n": n, "type": t, "fmt": "S1", "text": i, "kind": "marker", "family": fam[t][0], "shape": fam[t][1],
              "letter": "[기관]" if (t == "T1" and root_role == "label") else fam[t][1], "outline": None, "flow": "body", "lead": 0}
             for n, (i, t, _) in enumerate(rows)]
    keys = {"T1": "①", "T2": "□", "T3": "o"}
    if root_role == "label":
        keys["T1"] = "[기관]"
    graph = {i: {"id": i, "para": i, "type": t, "parent": p, "role": "label" if (t == "T1" and root_role == "label") else "heading", "key": keys[t],
                 "division": None} for i, t, p in rows}
    types = {t: {"shape": fam[t][1]} for t in fam}
    return nodes, graph, keys, types


def _fin(nodes, graph, keys, types):
    asg = HG.assign_templates(nodes, graph, keys)
    return HG.finish(nodes, graph, asg, types, {}, {})


def test_label_root_template_forms_instances():
    """뿌리가 구분 라벨인 템플릿(「[기관] › □ › o」)은 라벨마다 인스턴스 — 멤버는 라벨 아래 사슬(□·o·o), 라벨 템플릿은 kind label."""
    nodes, graph, keys, types = _sub_graph("label")
    fin = _fin(nodes, graph, keys, types)
    ins = {x["root"]: x for x in fin["instances"]}
    assert sorted(ins) == ["r0", "r1", "r2"]
    assert ins["r0"]["members"] == ["s0", "o0a", "o0b"] and ins["r0"]["basis"] == "[기관]"
    t = fin["templates"][0]
    assert (t["kind"], t["chain"], t["anchor"], t["instances"]) == ("label", ["[기관]", "□", "o"], "body:[기관]›□›o", 3)
    assert [s["level"] for s in t["slots"]] == [1, 2, 3] and t["slots"][0]["letter"] == "[기관]"  # 라벨 L1 도 슬롯


def test_demoted_to_label_stays_parent():
    """B 가 자식 있는 노드를 라벨로 바꿔도 라벨은 그대로 부모(제 템플릿의 뿌리) — 자식의 구분 소속(division)은 가장 가까운 라벨 조상."""
    nodes, graph, keys, types = _sub_graph()
    applied, rejected = HG.apply_changes([{"id": "s0", "role": "label"}], ["r0", "s0", "o0a", "o0b"], [], graph, set())
    assert not rejected and [a["id"] for a in applied] == ["s0"]
    assert graph["s0"]["role"] == "label" and graph["o0a"]["parent"] == "s0" and graph["o0b"]["parent"] == "s0"
    assert HG._division_of("o0a", graph) == "s0" and HG._division_of("s0", graph) is None
    nodes, graph, keys, types = _sub_graph()
    applied, rejected = HG.apply_changes([{"id": "o0b", "parent": "o0a"}, {"id": "o0a", "role": "label"}], ["r0", "s0", "o0a", "o0b"], [], graph, set())
    assert not rejected
    assert graph["o0b"]["parent"] == "o0a" and HG._division_of("o0b", graph) == "o0a"


@pytest.fixture(scope="module")
def rnd():
    tol = G.parse_tolerance(G.default_text("tolerance"))
    return E.extract(HwpxDoc(RND.read_bytes()), store=copy.deepcopy(EMPTY), doc_key="rnd", tol=tol)


def test_counts_include_boxes_in_cells(rnd):
    """여러 칸 표 칸 안 1칸 상자 노드(area box · 흐름 cell:…)도 칸 수에 든다 — 본문 + 칸 = 본문·칸 흐름 노드 전부."""
    g = HG.build(rnd, use_llm=False)
    nodes = g["nodes"]
    boxed = [n for n in nodes if n["area"] == "box" and n["flow"].startswith("cell:")]
    assert boxed  # 표본에 칸 안 상자 헤딩(「1. 위험성 추정…」)이 있다
    c = g["counts"]
    assert c["cell"] == sum(1 for n in nodes if n["flow"].startswith("cell:"))
    assert c["body"] + c["cell"] == sum(1 for n in nodes if n["flow"] == "body" or n["flow"].startswith("cell:"))


def _rec(n, blank, gap):
    return {"id": f"r{n}", "n": n, "kind": "marker", "blank": blank, "gap": gap, "leadCode": "", "gapCode": f"_{len(gap)}" if gap else "",
            "leadSpaces": 0, "leadMm": 0.0,
            "para": {"align": "justify", "indentLeftMm": 0.0, "indentRightMm": 0.0, "firstLineMm": 0.0, "spaceBeforePt": 0.0, "spaceAfterPt": 0.0,
                     "lineSpacing": {"type": "PERCENT", "value": 160, "unit": "%"}},
            "char": {"text": {"charPr": "1", "font": "돋움", "sizePt": 13.0, "bold": False}, "letter": None}}


@pytest.mark.parametrize("nblank", [0, 4, 6, 20])
def test_blank_only_format_never_rep_for_titled(nblank):
    """레터 뒤 공백 1칸 「□ 제목」 ×5 · 4칸 ×2 는 쓸 자리 「□」 가 몇 개든 다른 S — 쓸 자리는 제목 있는 S 에 붙는다."""
    tol = dict(G.TOLERANCE_DEFAULT)
    recs = [_rec(i, False, " ") for i in range(5)] + [_rec(5 + i, False, "    ") for i in range(2)] + [_rec(7 + i, True, "") for i in range(nblank)]
    E.label_formats(recs, tol)
    assert recs[0]["fmt"] != recs[5]["fmt"]
    if nblank:
        assert recs[7]["fmt"] in (recs[0]["fmt"], recs[5]["fmt"])


def test_guide_reset_unlink_failure_keeps_base(monkeypatch):
    """되돌리기에서 사본을 못 지우면(파일 잠김) 사본의 base 가 남는다 — 다음 저장이 기준을 몰래 바꾸지 않는다."""
    G.save("graph", "내 지침", reason="시험")
    base = G.get("graph")["base"]
    assert base
    real = Path.unlink

    def locked(self, *a, **k):
        if self.name == "graph.md":
            raise PermissionError("잠김")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "unlink", locked)
    with pytest.raises(OSError):
        G.reset("graph", reason="시험")
    g = G.get("graph")
    assert g["custom"] and g["base"] == base
    monkeypatch.setattr(Path, "unlink", real)
    G.reset("graph", reason="시험")
    g = G.get("graph")
    assert not g["custom"] and g["base"] is None


@pytest.fixture
def c():
    from fastapi.testclient import TestClient
    from app import server
    server.DOCS.clear()
    yield TestClient(server.app, raise_server_exceptions=False)
    server.DOCS.clear()


def _open_ready(c, path):
    import time
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


def test_unsaved_run_logged_without_number(c):
    """밀려난 세션에서 끝난 실행은 저장 안 됨 — 기록에 번호를 안 남긴다(다음 실행이 그 번호를 쓰므로). 저장된 실행은 번호를 남긴다."""
    import time
    from app import heading_runs, server, works
    small = RND.parent / "기술수요조사서.hwpx"
    d = _open_ready(c, small)
    a = server.DOCS[d]
    heading_runs.state(a)
    server.DOCS.pop(d)  # = _admit 이 A 를 비움
    heading_runs.start(a, 1, False)
    end = time.time() + 60
    while heading_runs.state(a)["job"].status == "running" and time.time() < end:
        time.sleep(0.05)
    b = server._sess(d)
    heading_runs.start(b, 1, False)
    while heading_runs.state(b)["job"].status == "running" and time.time() < end:
        time.sleep(0.05)
    ev = [e for e in works.events(d) if e.get("kind") == "headings"]
    assert [(e.get("n"), e.get("saved")) for e in ev] == [(None, False), (1, None)]


def test_stage2_reruns_old_version_stage1(c):
    """옛 추출 방식(version 1)의 1단계 결과는 오래됨 — 2단계가 1단계를 다시 뽑는다."""
    from app import heading_runs, server
    d = _open_ready(c, RND.parent / "기술수요조사서.hwpx")
    s = server.DOCS[d]
    heading_runs.run_sync(s, 1, False)
    st = heading_runs.state(s)
    st["stage1"]["version"] = 1  # 고치기 전 결과처럼
    assert heading_runs.summary(s)["stage1"]["stale"]
    job = heading_runs.run_sync(s, 2, False)
    assert any("1단계(스크립트) 다시" in str(x) for x in job.view()["steps"])
    assert st["stage1"]["version"] == E.VERSION and not heading_runs.summary(s)["stage1"]["stale"]


@pytest.mark.parametrize("label,want", [("B.", "A."), ("c)", "a)"), ("Ⅲ.", "Ⅰ."), ("⑵", "⑴"), ("3.", "N."), ("다.", "가."), ("●", "●")])
def test_auto_number_label_shape_matches_typed(label, want):
    """자동 번호 라벨(「B.」 등)의 모양 키 = 글로 친 같은 레터의 모양 키."""
    rules = R.active(copy.deepcopy(EMPTY), [], doc_key=None)
    run = R._Run()
    assert E._auto_shape(label, rules, run) == want
    typed = R.classify(label + " 제목", rules, run)
    if typed["shape"]:
        assert E._auto_shape(label, rules, run) == typed["shape"]
