"""구조 편집 뒤 문서 전체를 다시 읽지 않기(spec_owpml_편집 ② §3 「닿은 블록만 다시 읽기」, 2026-11-11 — 개요 줄 Enter 가 3초):
HwpxDoc.host_blocks 가 blocks() 의 그 항목과 같은 값인지 · 서버 편집(_edit)이 번호·자동 번호가 없는 문단에서는 blocks() 를 부르지 않는지 ·
그래도 세션 글(s.texts)·응답 블록이 전체를 다시 읽은 것과 같은지. 다른 편집 시험은 conftest 의 NFM_BLOCKS_CHECK=1 로 편집마다 둘을 견준다."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, hwpx_struct, server, verify
from app.hwpx_doc import P, HwpxDoc

ROOT = Path(__file__).parents[1]
SMALL = ROOT / "samples" / "기술수요조사서.hwpx"
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


@pytest.mark.parametrize("path", [SMALL, PLAN])
def test_host_blocks_equal_blocks(path):
    d = HwpxDoc(path.read_bytes())
    full = d.blocks()
    by = {}  # 최상위 문단 → 그 문단이 낸 최상위 블록들(문서 순)
    for b in full:
        by.setdefault(hwpx_struct.top_host(d, d._ids[b["id"]]), []).append(b)
    hosts = [p for sec in d._sections for p in sec.iterchildren(P)]
    assert set(by) == set(hosts)
    plain = []
    for h in hosts:
        got = d.host_blocks([h])
        if got is None:  # 문서 순서로 세는 값(번호 문단·자동 번호)이 든 문단 — 따로 못 읽는다
            assert d.order_bound([h])
            continue
        assert not d.order_bound([h])
        assert got == by[h], f"{d._rev.get(h)} 의 블록이 blocks() 와 다름"
        plain.append(h)
    assert len(plain) > len(hosts) // 2  # 대부분의 문단은 따로 읽힌다
    some = plain[:: max(1, len(plain) // 7)]
    assert d.host_blocks(list(reversed(some))) == [b for h in some for b in by[h]]  # 여러 문단 — 준 차례와 상관없이 문서 순
    assert d._blocks_cache is full  # 캐시는 안 건드린다


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    server.DOCS.clear()
    return TestClient(server.app)


def _texts_full(s):
    """문서 전체를 다시 읽어 만든 글 사전(_transact 의 옛 길과 같은 것)."""
    cur = verify.flat_texts(s.doc.blocks())
    for i in s.texts:
        el = s.doc._ids.get(i)
        if i not in cur and s.doc._attached(el) and el.tag == P:
            cur[i] = s.doc._text(el)
    return cur


@pytest.mark.parametrize("path", [SMALL, PLAN])
def test_server_edit_reads_only_touched_blocks(client, monkeypatch, path):
    r = client.post("/api/docs", files={"file": (path.name, path.read_bytes(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    s = server.DOCS[d]
    host_of = lambda i: hwpx_struct.top_host(s.doc, s.doc._ids[i])  # noqa: E731
    pid = next(i for i, t in s.texts.items() if len(t.strip()) >= 12 and s.doc._ids[i].tag == P and not s.doc.order_bound([host_of(i)]))  # 본문 문단이든 표 칸 문단이든
    drop = hwpx_struct.top_ids(s.doc, host_of(pid))
    monkeypatch.setenv("NFM_BLOCKS_CHECK", "0")  # 교차 검사는 blocks() 를 부른다 — 여기서는 끄고 직접 센다
    real, calls = HwpxDoc.blocks, []

    def counted(self):
        if self is s.doc:  # 세션 문서만 — 올린 직후의 가져오기 검증 스레드는 따로 연 문서의 blocks() 를 부른다
            calls.append(1)
        return real(self)
    monkeypatch.setattr(HwpxDoc, "blocks", counted)

    r = client.post(f"/api/docs/{d}/split", json={"id": pid, "offset": 5})
    assert r.status_code == 200, r.text
    assert not calls, "문단 나누기가 문서 전체 블록을 다시 읽음"
    new = r.json()["focus"]["id"]
    tops = r.json()["tops"]
    assert tops["drop"] == drop and {pid, new} <= set(verify.flat_texts(tops["blocks"]))
    monkeypatch.setattr(HwpxDoc, "blocks", real)
    assert s.texts == _texts_full(s)  # 닿은 블록만 고친 글 = 전체를 다시 읽은 글
    whole = {b["id"]: b for b in client.get(f"/api/docs/{d}").json()["blocks"]}
    assert tops["blocks"] and all(whole[b["id"]] == b for b in tops["blocks"])  # 응답 블록 = 전체에서 읽은 그 블록

    monkeypatch.setattr(HwpxDoc, "blocks", counted)
    s.doc._blocks_cache = None
    calls.clear()
    r2 = client.post(f"/api/docs/{d}/format/chars", json={"id": new, "start": 0, "end": 3, "changes": {"bold": True}})
    assert r2.status_code == 200 and not calls, "글자 모양이 문서 전체 블록을 다시 읽음"
    r = client.post(f"/api/docs/{d}/merge", json={"id": pid, "dir": "next"})
    assert r.status_code == 200 and not calls, "문단 합치기가 문서 전체 블록을 다시 읽음"
    monkeypatch.setattr(HwpxDoc, "blocks", real)
    assert new not in s.texts and s.texts == _texts_full(s)
    assert client.post(f"/api/docs/{d}/undo").status_code == 200  # 실행 취소는 문서를 통째로 되돌린다(전체를 다시 읽음)
    assert new in s.texts and s.texts == _texts_full(s)


# ---------------------------------------------------------------- 응답 tops 의 범위(개요 편집) — 화면이 하는 대로 갈아 끼우면 서버 문서와 같아야 한다
@pytest.fixture(scope="module")
def plan(tmp_path_factory):
    # 모듈 픽스처는 conftest 의 시험별 자동 픽스처보다 먼저 돈다 — 여기서 임시 폴더로 두지 않으면 사용자 작업 폴더에 작업이 쌓인다(test_outline_edit.py sess 와 같은 꼴)
    tmp = tmp_path_factory.mktemp("tops")
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render", "NFM_HEADINGS": tmp / "heads",
                     "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json", "NFM_BLOCKS_CHECK": "1"}.items():
            mp.setenv(k, str(v))
        R._MEMORY.clear()
        G._MEMORY.clear()
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        yield c, d, s
        server.DOCS.clear()
        R._MEMORY.clear()
        G._MEMORY.clear()


def _swap(model, tops):
    """화면(app.js applyTops)이 하는 대로 — drop 과 응답 블록의 id 가 걸친 옛 구간을 통째로 응답 블록으로. 그 구간에 응답에도 drop 에도 없는 블록이 끼어 있으면 안 된다(화면에서 사라진다)."""
    ids = set(tops["drop"]) | {b["id"] for b in tops["blocks"]}
    at = [k for k, i in enumerate(model) if i in ids]
    assert at, "응답이 화면의 어느 블록도 가리키지 않음"
    lo, hi = at[0], at[-1]
    lost = [i for i in model[lo:hi + 1] if i not in ids]
    assert not lost, f"응답이 옛 구간을 다 덮지 않음 — 화면에서 사라질 블록 {lost[:5]}"
    model[lo:hi + 1] = [b["id"] for b in tops["blocks"]]


def test_outline_tops_cover_what_the_screen_must_replace(plan):
    c, d, s = plan
    top = lambda: [b["id"] for b in s.doc.blocks()]  # noqa: E731
    model = top()

    def op(body, code=200):
        r = c.post(f"/api/docs/{d}/outline", json=body)
        assert r.status_code == code, r.text
        if code == 200:
            _swap(model, r.json()["tops"])
            assert model == top(), f"{body}: 응답대로 갈아 끼운 화면이 서버 문서와 다름"
        return r.json()

    op({"op": "enter", "id": "p972", "offset": len(s.texts["p972"])})  # 하위 줄(간격 줄과 함께)
    op({"op": "remove", "id": "p975"})  # 빈 ⋅ 줄 지움 — 닿은 문단이 남지 않는다(전에는 구역의 첫 문단을 돌려줬다)
    v = op({"op": "remove", "id": "p974"})  # 빈 - 줄 + 앞 간격 줄(p973) — 둘 다 drop 에
    assert {"p973", "p974"} <= set(v["tops"]["drop"])
    op({"op": "move", "id": "p977", "target": "p972", "where": "before"})  # 여러 줄(단위 p976~p980)을 건너 옮김 — 옛 자리와 새 자리 사이의 줄도 응답에
    op({"op": "move", "id": "p982", "target": "p968", "where": "before"})  # 1-2. 를 1-1. 앞으로(번호 다시 매김)
    op({"op": "level", "ids": ["p972"], "delta": 1})
    op({"op": "level", "ids": ["p972"], "delta": -1})
    while s.state()["undo"]:
        assert c.post(f"/api/docs/{d}/undo").status_code == 200
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()
