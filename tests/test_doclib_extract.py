"""문서 라이브러리 서버의 저장소 · 추출 흐름 · 끝점(doclib/store.py · extract.py · server.py — spec_양식작성 ② §2 · §3). LLM(Claude CLI)은 부르지 않는다 — `extract.agent.run` 을 가짜로 바꾼다."""
import io
import json
import threading
import zipfile

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from doclib import agent, extract, server, store


def _png(w, h, color):
    im = Image.new("RGB", (w, h), "white")
    ImageDraw.Draw(im).ellipse([8, 8, w - 8, h - 8], fill=color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _pdf(pages=3):
    """쪽마다 글 + 1쪽에 그림 하나(후보 p1_F1) · 2쪽에 네모 그림(후보 밖 — LLM 이 상자로 가리킨다)."""
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page(width=600, height=800)
        p.insert_text((60, 60), f"page {i + 1} body text", fontsize=12)
    doc[0].insert_image(fitz.Rect(100, 100, 300, 250), stream=_png(200, 150, (200, 60, 60)))
    if pages > 1:
        doc[1].draw_rect(fitz.Rect(120, 200, 360, 380), color=(0, 0, 0), fill=(0.1, 0.5, 0.3))
        doc[1].draw_circle((240, 290), 40, color=(1, 1, 1), fill=(1, 1, 0))
        doc[1].insert_text((150, 500), "E = m c 2  (1)", fontsize=16)
    return doc.tobytes()


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_DOCLIB", str(tmp_path / "lib"))
    monkeypatch.setenv("NFM_CLAUDE_CLI", "")
    return tmp_path / "lib"


def _fake(seen, extract_answer=None, verify="ok", latex=True):
    """agent.run 의 가짜 — 프롬프트로 어느 호출인지 가린다(추출 · 그림 확인 · 수식)."""
    def run(prompt, schema, *, cwd, tools=("Read",), images=(), effort="medium", timeout=0, stop=None):
        data = json.loads(prompt.rsplit("## 자료(JSON)\n", 1)[1])
        base = {"error": None, "ms": 5, "costUsd": 0.01, "model": "fake", "turns": 2, "reads": 1}
        if "keys" in data:   # 수식
            seen.append(("formula", data["keys"], len(images), tools))
            return {**base, "data": {"items": [{"key": k, "latex": "E = mc^{2} \\tag{1}" if latex else "", "ok": latex, "note": "" if latex else "읽을 수 없음"} for k in data["keys"]]}}
        if "focus" not in data and "scopes" not in data:   # 그림 확인
            seen.append(("verify", [f["key"] for f in data["figures"]], sorted(p.name for p in (cwd / "check").iterdir()) if hasattr(cwd, "iterdir") else None, tools))
            items = [{"key": f["key"], "verdict": verify, "box": [180, 230, 620, 490] if verify == "cut" else [], "why": "시험"} for f in data["figures"]]
            return {**base, "data": {"items": items}}
        seen.append(("extract", data["pages"], [f["key"] for f in data["figures"]], data["focus"] if "focus" in data else [x["focus"] for x in data["scopes"]], tools, schema))
        if extract_answer is None:
            return {**base, "data": None, "error": "exit 1: 가짜 실패"}
        return {**base, "data": extract_answer(data)}
    return run


def _answer(data):
    first = data["pages"][0]
    if first != 1:
        return {"relevant": False, "markdown": "", "figures": [], "formulas": [], "skipped": "범위 밖", "note": ""}
    md = ("<!-- p.1 -->\n\n## 개요\n\n본문 글\n\n{{fig:p1_F1}}\n< 그림 1 >\n\n<!-- p.2 -->\n\n{{fig:new1}}\n< 그림 2 >\n\n{{eq:eq1}}\n\n{{fig:ghost}}")
    return {"relevant": True, "markdown": md,
            "figures": [{"key": "p1_F1", "caption": "< 그림 1 >", "page": 1, "box": [], "join": []}, {"key": "new1", "caption": "< 그림 2 >", "page": 2, "box": [190, 240, 610, 480], "join": []},
                        {"key": "unused", "caption": "", "page": 1, "box": [0, 0, 500, 500], "join": []}],
            "formulas": [{"key": "eq1", "page": 2, "box": [230, 600, 480, 640], "near": "식"}], "skipped": "3쪽의 다른 기관 내용", "note": ""}


def test_store_keeps_documents_and_prompts(lib):
    with pytest.raises(ValueError):
        store.add_doc("a.txt", b"x")
    with pytest.raises(ValueError):
        store.add_doc("a.pdf", b"")
    data = _pdf(1)
    meta, created = store.add_doc("자료/문서?.pdf", data)
    assert created and meta["id"].startswith("d") and meta["name"] == "자료_문서_.pdf" and meta["ext"] == "pdf" and store.source(meta["id"])[1].read_bytes() == data
    assert store.add_doc("다른 이름.pdf", data) == (store.doc(meta["id"]), False)          # 같은 바이트 = 같은 문서
    assert store.patch_doc(meta["id"], {"org": "  한국  선급 ", "topic": "자율운항", "pages": 1, "bad": 1})["org"] == "한국 선급" and store.doc(meta["id"])["pages"] == 1
    assert [d["id"] for d in store.docs()] == [meta["id"]] and store.docs()[0]["extracts"] == [] and store.doc("d000000000000") is None and store.doc("../x") is None
    p = store.prompt("extract")
    assert p["custom"] is False and "뽑을 범위" in p["text"] and store.prompt("nope") is None
    assert store.put_prompt("extract", "# 제목\n내 기준")["custom"] is True and store.prompt("extract")["text"].endswith("내 기준")
    assert store.put_prompt("extract", "")["custom"] is False and store.put_prompt("nope", "x") is None
    with pytest.raises(ValueError):
        store.put_prompt("extract", "x" * (store.PROMPT_MAX + 1))
    e = store.new_extract(meta["id"], "범위", (1, 1))
    assert store.cut_running() == 1 and store.extract(e["id"])["state"] == "cut" and store.drop_extract(e["id"]) and store.drop_doc(meta["id"]) and store.docs() == []


def test_ppt_documents_are_kept_and_printed_with_powerpoint(lib, monkeypatch):
    """2026-11-26 사용자 "ppt 도 참조 문서로 넣을 수 있도록" — ppt · pptx 를 받고, 읽을 PDF 는 PowerPoint 로 찍는다(형식 그대로 넘긴다)."""
    from app import pdf_render
    seen, made = [], fitz.open()
    made.new_page()
    pdf_bytes = made.tobytes()

    def fake_export(data, limit=None, fmt="hwpx"):
        seen.append((fmt, data))
        out = store.root() / f"made-{fmt}.pdf"
        out.write_bytes(pdf_bytes)
        return out
    monkeypatch.setattr(pdf_render, "available", lambda fmt="hwpx": fmt in ("pptx", "ppt"))
    monkeypatch.setattr(pdf_render, "export_pdf", fake_export)
    for name, body in (("발표.pptx", b"PK-pptx"), ("옛 발표.PPT", b"\xd0\xcf-ppt")):
        meta, created = store.add_doc(name, body)
        assert created and meta["ext"] == name.rsplit(".", 1)[1].lower()
        assert extract.ensure_pdf(meta["id"]).read_bytes() == pdf_bytes and seen[-1] == (meta["ext"], body)
    assert [f for f, _ in seen] == ["pptx", "ppt"]
    monkeypatch.setattr(pdf_render, "available", lambda fmt="hwpx": False)
    meta, _ = store.add_doc("다른.pptx", b"PK-other")
    with pytest.raises(RuntimeError, match="PowerPoint가 없어"):
        extract.ensure_pdf(meta["id"])


def test_skill_text_drops_only_the_head_comment(lib):
    text = extract.skill("extract")
    assert not text.startswith("# ") and text.startswith("## 무엇을 뽑나") and "사용자 원문" not in text and "<!-- 범위 확인 필요 -->" in text and "<!-- p.N -->" in text   # 머리의 주석만 뺀다 — 글 안의 주석은 판단 기준의 일부
    assert "{first}" not in extract.CONTRACT.format(first=3, last=8, n=6) and "{{fig:KEY}}" in extract.CONTRACT.format(first=3, last=8, n=6)


def test_extract_runs_chunks_cuts_figures_verifies_boxes_and_converts_formulas(lib, monkeypatch):
    seen = []
    monkeypatch.setattr(extract.pdfkit, "SIZE", 2)               # 3쪽 → 묶음 둘(1–2 · 3)
    monkeypatch.setattr(extract.agent, "run", _fake(seen, _answer))
    monkeypatch.setattr(extract.agent, "slots_n", lambda: 1)
    meta, _ = store.add_doc("연차보고서.pdf", _pdf(3))
    e = store.new_extract(meta["id"], "한국선급의 연구 내용", None)
    extract.run(e["id"], threading.Event())
    got = store.extract(e["id"])
    assert got["state"] == "done" and got["span"] == [1, 3] and got["pages"] == 3 and got["figures"] == 2 and got["formulas"] == 1 and got["failed"] == 0 and got["relevant"] == 1
    assert got["open"] == 1 and got["costUsd"] == pytest.approx(0.04)          # 넣지 못한 그림 ghost 하나 · 호출 넷(추출 2 · 그림 확인 1 · 수식 1)
    kinds = [s[0] for s in seen]
    assert kinds.count("extract") == 2 and kinds.count("verify") == 1 and kinds.count("formula") == 1
    ex1 = next(s for s in seen if s[0] == "extract" and s[1] == [1, 2])
    assert "p1_F1" in ex1[2] and ex1[3] == "한국선급의 연구 내용" and ex1[4] == ("Read",)                  # 추출 호출 = Read 도구 하나
    assert next(s for s in seen if s[0] == "verify")[1] == ["p2_N1"]                                         # LLM 의 상자로 자른 그림만 다시 본다(후보 그대로 쓴 p1_F1 은 아님)
    f = next(s for s in seen if s[0] == "formula")
    assert f[1] == ["p2_Q1"] and f[2] == 1 and f[3] == ()                                                  # 수식 = 그림 입력 · 도구 없음
    folder = store.ext_dir(e["id"])
    md = (folder / "doc.md").read_text(encoding="utf-8")
    assert md.startswith("# 연차보고서.pdf\n") and "범위: 한국선급의 연구 내용 · 쪽 1–3" in md and "그림 2 · 수식 1 · 확인 필요 1곳" in md
    assert "![< 그림 1 >](images/p1_F1.png)" in md and "![< 그림 2 >](images/p2_N1.png)" in md and "<!-- 그림을 넣지 못함: ghost -->" in md
    assert "$$\nE = mc^{2} \\tag{1}\n$$\n<!-- 수식 캡처: images/p2_Q1.png -->" in md and "## 추출하며 뺀 것" in md and "- p.1–2: 3쪽의 다른 기관 내용" in md and "- p.3–3: 범위 밖" in md
    assert sorted(p.name for p in (folder / "images").iterdir()) == ["p1_F1.png", "p2_N1.png", "p2_Q1.png"]
    rec = json.loads((folder / "chunks" / "1.json").read_text(encoding="utf-8"))
    assert rec["relevant"] and rec["answer"]["figures"][0]["key"] == "p1_F1" and "## 판단 기준(스킬)" in rec["prompt"] and rec["verify"]["answer"]["items"][0]["verdict"] == "ok"
    assert not (store.root() / "tmp").exists() or list((store.root() / "tmp").iterdir()) == []            # 임시 폴더는 남기지 않는다
    eq = (folder / "equations.md").read_text(encoding="utf-8")                                              # 수식 목록 — 캡처와 LaTeX 를 나란히
    assert eq.startswith("# 수식 목록 — 연차보고서.pdf") and "## p2_Q1 — p.2" in eq and "![p2_Q1](images/p2_Q1.png)" in eq and "E = mc^{2}" in eq
    data = json.loads(rec["prompt"].rsplit("## 자료(JSON)\n", 1)[1])                                         # 묶음마다 문서를 훑은 것을 같이 준다
    # 견본의 「page N body text」 는 세 쪽의 위 띠에 되풀이된다 — 머리말로 판정
    assert data["running"] == ["page 1 body text"] and data["scanned"] == [] and set(data["headings"]) == {"body", "tiers", "hints"} and data["figures"][0]["caption"] == "" and "src" in (data["formulas"] or [{"src": 1}])[0]


def test_extract_marks_recut_figures_failed_formulas_and_failed_chunks(lib, monkeypatch):
    seen = []
    monkeypatch.setattr(extract.agent, "run", _fake(seen, _answer, verify="cut", latex=False))
    meta, _ = store.add_doc("a.pdf", _pdf(2))
    e = store.new_extract(meta["id"], "", (1, 2))
    extract.run(e["id"], threading.Event())
    md = (store.ext_dir(e["id"]) / "doc.md").read_text(encoding="utf-8")
    assert "범위: 문서 전체" in md and "<!-- 확인 필요: 그림 확인이 다시 자름 — 온전한지 볼 것 -->" in md and "![수식 — p.2](images/p2_Q1.png)\n<!-- 확인 필요: 읽을 수 없음 -->" in md
    assert store.extract(e["id"])["open"] == 3   # 다시 자른 그림 · 못 바꾼 수식 · 넣지 못한 그림

    seen.clear()
    monkeypatch.setattr(extract.agent, "run", _fake(seen, _answer, verify="drop"))
    e = store.new_extract(meta["id"], "", (1, 2))
    extract.run(e["id"], threading.Event())
    md = (store.ext_dir(e["id"]) / "doc.md").read_text(encoding="utf-8")
    assert "<!-- 그림을 넣지 못함: p2_N1 -->" in md and "그림 p2_N1: 그림 확인이 그림이 아니라고 판정" in md

    monkeypatch.setattr(extract.agent, "run", _fake(seen, None))          # LLM 이 답하지 못함 — 추출 실패(문서는 그대로)
    e = store.new_extract(meta["id"], "x", None)
    extract.run(e["id"], threading.Event())
    got = store.extract(e["id"])
    assert got["state"] == "failed" and "가짜 실패" in got["error"] and not (store.ext_dir(e["id"]) / "doc.md").exists()

    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(extract.agent, "run", _fake(seen, _answer))
    e = store.new_extract(meta["id"], "x", None)
    extract.run(e["id"], stop)
    assert store.extract(e["id"])["state"] == "stopped"


def test_agent_is_off_without_cli(lib, monkeypatch):
    monkeypatch.setenv("NFM_DOCLIB_LLM", "off")
    assert agent.status()["available"] is False and agent.run("p", {}, cwd=".")["error"] == "off"
    monkeypatch.setenv("NFM_DOCLIB_MODEL", "bad model!")
    assert agent.model() == agent.MODEL == "claude-opus-5-5"
    assert "ANTHROPIC_API_KEY" not in agent._env() and not any(k.startswith("CLAUDE") for k in agent._env())


def test_server_endpoints(lib, monkeypatch):
    monkeypatch.setenv("NFM_DOCLIB_LLM", "off")
    c = TestClient(server.app)
    h = c.get("/api/health").json()
    assert h["ok"] and h["llm"]["available"] is False and h["size"] == 20 and h["scopes"] == extract.FOCUSES_MAX
    assert c.get("/").status_code == 200 and "문서 라이브러리" in c.get("/").text and c.get("/static/doclib.js").status_code == 200
    pdf = _pdf(2)
    r = c.post("/api/docs", files={"file": ("보고서.pdf", pdf, "application/pdf")})
    assert r.status_code == 200 and r.json()["created"] and r.json()["doc"]["pages"] == 2
    did = r.json()["doc"]["id"]
    assert c.post("/api/docs", files={"file": ("보고서.pdf", pdf, "application/pdf")}).json()["created"] is False
    assert c.post("/api/docs", files={"file": ("a.txt", b"x")}).status_code == 400 and c.post("/api/docs", files={"file": ("a.pdf", b"not pdf")}).status_code == 400
    assert [d["id"] for d in c.get("/api/docs").json()["docs"]] == [did]                       # 깨진 PDF 는 보관하지 않는다
    assert c.patch(f"/api/docs/{did}", json={"org": "한국선급"}).json()["doc"]["org"] == "한국선급"
    assert c.get(f"/api/docs/{did}/pdf").headers["content-type"] == "application/pdf" and c.get(f"/api/docs/{did}/file").status_code == 200
    assert c.post(f"/api/docs/{did}/extracts", json={"focus": "x"}).status_code == 503        # LLM 꺼짐
    # 다른 출처의 페이지가 보내는 바꾸는 요청은 받지 않는다 · 제 출처와 출처 없는 요청(8114 서버)은 받는다
    assert c.patch(f"/api/docs/{did}", json={"org": "x"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.patch(f"/api/docs/{did}", json={"org": "y"}, headers={"Origin": "http://testserver"}).status_code == 200
    # 추출을 가짜 LLM 으로 — 끝점이 배경에서 돌리고 결과를 내준다
    monkeypatch.setenv("NFM_DOCLIB_LLM", "")
    monkeypatch.setattr(extract.agent, "status", lambda: {"available": True, "cli": "x", "model": "fake", "slots": 1})
    monkeypatch.setattr(extract.agent, "run", _fake([], _answer))
    assert c.post(f"/api/docs/{did}/extracts", json={"focus": "x", "first": 2, "last": 1}).status_code == 400
    eid = c.post(f"/api/docs/{did}/extracts", json={"focus": "한국선급", "first": 1, "last": 2}).json()["extract"]["id"]
    extract._RUNS[eid][0].join(30)
    got = c.get(f"/api/extracts/{eid}").json()
    assert got["extract"]["state"] == "done" and got["running"] is False and c.get("/api/docs").json()["docs"][0]["extracts"][0]["id"] == eid
    md = c.get(f"/api/extracts/{eid}/md")
    assert md.headers["content-type"].startswith("text/markdown") and "](images/p1_F1.png)" in md.text
    assert "](http://testserver/api/extracts/" + eid + "/images/p1_F1.png)" in c.get(f"/api/extracts/{eid}/md?abs=1").text
    assert c.get(f"/api/extracts/{eid}/images/p1_F1.png").headers["content-type"] == "image/png" and c.get(f"/api/extracts/{eid}/images/..%5Cmeta.json").status_code == 404
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/extracts/{eid}/zip").content))
    assert sorted(z.namelist()) == ["images/p1_F1.png", "images/p2_N1.png", "images/p2_Q1.png", "보고서_한국선급.equations.md", "보고서_한국선급.md"]   # MD 파일 이름 = 「<문서>_<범위>」
    ps = c.get("/api/prompts").json()
    assert [p["name"] for p in ps["prompts"]] == ["extract", "verify", "formula"] and set(ps["contracts"]) == {"extract", "verify", "formula"}
    assert c.put("/api/prompts/verify", json={"text": "내 기준"}).json()["prompt"]["custom"] and c.put("/api/prompts/nope", json={"text": "x"}).status_code == 404
    assert c.delete(f"/api/extracts/{eid}").json() == {"ok": True} and c.get(f"/api/extracts/{eid}").status_code == 404
    assert c.delete(f"/api/docs/{did}").json() == {"ok": True} and c.get("/api/docs").json()["docs"] == []


def test_extract_retries_a_failed_call_and_halves_a_chunk_that_timed_out(lib, monkeypatch):
    """앞선 구현(makemd)의 복구 규칙 — 실패하면 한 번 더 · 시간 초과면 묶음을 반으로 나눠 다시."""
    calls = []
    good = _fake([], _answer)

    def flaky(prompt, schema, **kw):   # 추출 호출의 첫 시도만 실패
        data = json.loads(prompt.rsplit("## 자료(JSON)\n", 1)[1])
        if "focus" in data:
            calls.append(tuple(data["pages"]))
            if len(calls) == 1:
                return {"data": None, "error": "exit 1: 한 번 실패", "ms": 1, "costUsd": None, "model": "fake", "turns": 0, "reads": 0}
        return good(prompt, schema, **kw)
    monkeypatch.setattr(extract.agent, "run", flaky)
    meta, _ = store.add_doc("a.pdf", _pdf(2))
    e = store.new_extract(meta["id"], "", None)
    extract.run(e["id"], threading.Event())
    got = store.extract(e["id"])
    assert calls == [(1, 2), (1, 2)] and got["state"] == "done" and got["failed"] == 0 and got["figures"] == 2

    calls.clear()

    def slow(prompt, schema, **kw):   # 두 쪽 묶음은 시간 초과 · 한 쪽씩은 답한다(2쪽은 실패)
        data = json.loads(prompt.rsplit("## 자료(JSON)\n", 1)[1])
        if "focus" in data:
            calls.append(tuple(data["pages"]))
            if data["pages"] == [1, 2]:
                return {"data": None, "error": "시간 초과 1500초", "ms": 1, "costUsd": None, "model": "fake", "turns": 0, "reads": 0}
            if data["pages"] == [2, 2]:
                return {"data": None, "error": "exit 1: 못 읽음", "ms": 1, "costUsd": None, "model": "fake", "turns": 0, "reads": 0}
            return {"data": {"relevant": True, "markdown": "<!-- p.1 -->\n\n한 쪽 글\n\n{{fig:p1_F1}}", "figures": [{"key": "p1_F1", "caption": "", "page": 1, "box": [], "join": []}], "formulas": [], "skipped": "", "note": ""},
                    "error": None, "ms": 1, "costUsd": 0.01, "model": "fake", "turns": 2, "reads": 1}
        return good(prompt, schema, **kw)
    monkeypatch.setattr(extract.agent, "run", slow)
    e = store.new_extract(meta["id"], "", None)
    extract.run(e["id"], threading.Event())
    got = store.extract(e["id"])
    md = (store.ext_dir(e["id"]) / "doc.md").read_text(encoding="utf-8")
    assert calls == [(1, 2), (1, 1), (2, 2), (2, 2)]                       # 시간 초과는 다시 부르지 않고 반으로 · 보통 실패는 한 번 더
    assert got["state"] == "done" and got["failed"] == 1 and got["figures"] == 1 and got["open"] == 1
    assert "한 쪽 글" in md and "![그림 p.1](images/p1_F1.png)" in md and "<!-- p.2–2: 추출하지 못함 — exit 1: 못 읽음 -->" in md


def test_write_retries_a_refused_replace_and_orphan_running_extract_is_cut(lib, monkeypatch):
    """Windows 는 화면이 meta.json 을 읽는 순간 바꿔 쓰기를 거절한다(WinError 5) — 다시 해서 적는다 ·
    끝 상태를 못 적고 죽은 「추출 중」 은 목록이 「끊김」 으로 거둔다(2026-11-24 254쪽 추출이 「준비하는 중」 에 남았던 것)."""
    import os
    real, tries = os.replace, []

    def flaky(a, b):
        tries.append(1)
        if len(tries) < 3:
            raise PermissionError(5, "Access is denied")
        return real(a, b)
    monkeypatch.setattr(store.os, "replace", flaky)
    p = store.root() / "x.json"
    store._write(p, {"a": 1})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1} and len(tries) == 3
    monkeypatch.setattr(store.os, "replace", real)

    meta, _ = store.add_doc("a.pdf", _pdf(1))
    e = store.new_extract(meta["id"], "", None)
    e["state"] = "running"
    store.save_extract(e)
    assert store.cut_orphans(lambda eid: True) == 0
    c = TestClient(server.app)
    got = c.get("/api/docs").json()["docs"][0]["extracts"][0]
    assert got["state"] == "cut" and got["error"]


def test_deleting_a_running_extract_stops_it_then_removes_it(lib, monkeypatch):
    """도는 카드의 「지우기」 — 멈추고, 스레드가 끝나면 지운다(2026-11-24 같은 범위로 두 번 시작한 것을 지우려던 사용자: 「삭제 이런게 없네」)."""
    monkeypatch.setenv("NFM_DOCLIB_LLM", "")
    monkeypatch.setattr(extract.agent, "status", lambda: {"available": True, "cli": "x", "model": "fake", "slots": 1})
    began = threading.Event()

    def slow(prompt, schema, *, cwd, tools=("Read",), images=(), effort="medium", timeout=0, stop=None):
        began.set()
        stop.wait(20)
        return {"data": None, "error": "stopped", "ms": 1, "costUsd": None, "model": "fake", "turns": 0, "reads": 0}
    monkeypatch.setattr(extract.agent, "run", slow)
    c = TestClient(server.app)
    did = c.post("/api/docs", files={"file": ("a.pdf", _pdf(2), "application/pdf")}).json()["doc"]["id"]
    eid = c.post(f"/api/docs/{did}/extracts", json={"focus": "x"}).json()["extract"]["id"]
    assert began.wait(20)
    assert c.delete(f"/api/extracts/{eid}").json() == {"ok": True, "pending": True}
    extract._RUNS[eid][0].join(30)
    assert c.get(f"/api/extracts/{eid}").status_code == 404 and c.get("/api/docs").json()["docs"][0]["extracts"] == []


def _answer_many(data):
    """범위 둘의 답 — 1~2쪽: s1 은 후보 그림 · s2 는 상자로 가리킨 그림과 수식 / 3쪽: s1 은 범위 밖 · s2 는 답에서 빠짐."""
    if data["pages"][0] != 1:
        return {"scopes": [{"id": "s1", "relevant": False, "markdown": "지워질 글", "skipped": "범위 밖"}], "figures": [], "formulas": [], "note": ""}
    return {"scopes": [{"id": "s2", "relevant": True, "markdown": "<!-- p.2 -->\n\nB 글\n\n{{fig:new1}}\n\n{{eq:eq1}}\n\n{{fig:p1_F1}}", "skipped": ""},
                       {"id": "s1", "relevant": True, "markdown": "<!-- p.1 -->\n\nA 글\n\n{{fig:p1_F1}}\n< 그림 1 >", "skipped": "인텍전기전자의 절"}],
            "figures": [{"key": "p1_F1", "caption": "< 그림 1 >", "page": 1, "box": [], "join": []}, {"key": "new1", "caption": "", "page": 2, "box": [190, 240, 610, 480], "join": []}],
            "formulas": [{"key": "eq1", "page": 2, "box": [230, 600, 480, 640], "near": "식"}], "note": "메모"}


def test_many_scopes_read_the_document_once_and_write_one_md_per_scope(lib, monkeypatch):
    """범위 여럿(2026-11-24 사용자 "1.한국선급, 2.인텍전기전자 이렇게 각각 의 md 파일로") — 추출 호출은 묶음마다 하나, MD · 그림은 범위마다."""
    assert extract.focuses_of("  한국  선급 ") == ["한국 선급"] and extract.focuses_of(None) == [""] and extract.focuses_of(["", " "]) == [""]
    assert extract.focuses_of(["한국선급", " ", "인텍전기전자", "한국선급"]) == ["한국선급", "인텍전기전자"]          # 빈 글 · 같은 글은 뺀다
    with pytest.raises(ValueError):
        extract.focuses_of([f"범위{i}" for i in range(extract.FOCUSES_MAX + 1)])
    with pytest.raises(ValueError):
        extract.focuses_of(["x" * (extract.FOCUS_MAX + 1)])
    with pytest.raises(ValueError):
        extract.focuses_of(["a", 3])
    many = extract.CONTRACT_MULTI.format(first=1, last=2, n=2)
    assert "scopes" in many and "{id, relevant, markdown, skipped}" in many and "focus 에 해당하는" not in many and "{{fig:KEY}}" in many and "{first}" not in many

    seen = []
    monkeypatch.setattr(extract.pdfkit, "SIZE", 2)
    monkeypatch.setattr(extract.agent, "run", _fake(seen, _answer_many))
    monkeypatch.setattr(extract.agent, "slots_n", lambda: 1)
    meta, _ = store.add_doc("계획서.pdf", _pdf(3))
    lead = extract.start(meta["id"], ["한국선급", "인텍전기전자, 1·2차년도"], None)
    extract._RUNS[lead["id"]][0].join(30)
    a, b = extract._members(store.extract(lead["id"]))
    assert a["id"] == lead["id"] and a["group"] == b["group"] and a["group"].startswith("g") and (a["part"], b["part"]) == ([1, 2], [2, 2]) and (a["focus"], b["focus"]) == ("한국선급", "인텍전기전자, 1·2차년도")
    ex = [s for s in seen if s[0] == "extract"]
    assert len(ex) == 2 and all(s[3] == ["한국선급", "인텍전기전자, 1·2차년도"] and s[5] is extract.MULTI_SCHEMA for s in ex)   # 문서는 한 번만 읽는다(묶음마다 호출 하나)
    assert [s[0] for s in seen].count("verify") == 1 and [s[0] for s in seen].count("formula") == 1                # 그림 확인 · 수식도 한 번(범위들이 같이 쓴다)
    assert a["state"] == b["state"] == "done" and a["costUsd"] == b["costUsd"] == pytest.approx(0.04) and a["span"] == b["span"] == [1, 3]
    assert (a["figures"], a["formulas"], a["failed"], a["relevant"]) == (1, 0, 0, 1) and (b["figures"], b["formulas"], b["failed"], b["relevant"]) == (2, 1, 1, 2)
    fa, fb = store.ext_dir(a["id"]), store.ext_dir(b["id"])
    ma, mb = (fa / "doc.md").read_text(encoding="utf-8"), (fb / "doc.md").read_text(encoding="utf-8")
    assert "범위: 한국선급 · 쪽 1–3" in ma and "> 함께 뽑은 범위 1/2" in ma and "A 글" in ma and "B 글" not in ma and "지워질 글" not in ma and "![< 그림 1 >](images/p1_F1.png)" in ma
    assert "- p.1–2: 인텍전기전자의 절" in ma and "- p.3–3: 범위 밖" in ma
    assert "범위: 인텍전기전자, 1·2차년도" in mb and "> 함께 뽑은 범위 2/2" in mb and "B 글" in mb and "A 글" not in mb and "images/p2_N1.png" in mb and "images/p1_F1.png" in mb and "E = mc^{2}" in mb
    assert "<!-- p.3–3: 추출하지 못함 — 이 범위의 답이 빠졌습니다 -->" in mb and b["open"] >= 1                     # 답에 빠진 범위는 「내용 없음」 이 아니라 남긴다
    assert sorted(p.name for p in (fa / "images").iterdir()) == ["p1_F1.png"] and not (fa / "equations.md").exists()   # 그림 · 수식은 그 범위의 글이 쓴 것만
    assert sorted(p.name for p in (fb / "images").iterdir()) == ["p1_F1.png", "p2_N1.png", "p2_Q1.png"] and (fb / "equations.md").is_file()
    ra, rb = (json.loads((f / "chunks" / "2.json").read_text(encoding="utf-8")) for f in (fa, fb))
    assert ra["relevant"] is False and ra["skipped"] == "범위 밖" and rb["relevant"] is True
    assert json.loads(ra["prompt"].rsplit("## 자료(JSON)\n", 1)[1])["scopes"] == [{"id": "s1", "focus": "한국선급"}, {"id": "s2", "focus": "인텍전기전자, 1·2차년도"}]
    c = TestClient(server.app)
    listed = c.get("/api/docs").json()["docs"][0]["extracts"]
    assert {(x["group"], tuple(x["part"])) for x in listed} == {(a["group"], (1, 2)), (a["group"], (2, 2))}
    one = zipfile.ZipFile(io.BytesIO(c.get(f"/api/extracts/{a['id']}/zip").content))
    assert sorted(one.namelist()) == ["images/p1_F1.png", "계획서_한국선급.md"]
    both = zipfile.ZipFile(io.BytesIO(c.get(f"/api/extracts/{b['id']}/zip?group=1").content))                       # 함께 뽑은 범위의 MD 를 한 zip 에
    assert sorted(both.namelist()) == ["images/p1_F1.png", "images/p2_N1.png", "images/p2_Q1.png", "계획서_인텍전기전자, 1·2차년도.equations.md", "계획서_인텍전기전자, 1·2차년도.md", "계획서_한국선급.md"]


def test_many_scopes_stop_stops_all_and_delete_of_a_running_scope_leaves_the_rest(lib, monkeypatch):
    monkeypatch.setenv("NFM_DOCLIB_LLM", "")
    monkeypatch.setattr(extract.agent, "status", lambda: {"available": True, "cli": "x", "model": "fake", "slots": 1})
    began = threading.Event()

    def slow(prompt, schema, *, cwd, tools=("Read",), images=(), effort="medium", timeout=0, stop=None):
        began.set()
        stop.wait(20)
        return {"data": None, "error": "stopped", "ms": 1, "costUsd": None, "model": "fake", "turns": 0, "reads": 0}
    monkeypatch.setattr(extract.agent, "run", slow)
    c = TestClient(server.app)
    did = c.post("/api/docs", files={"file": ("a.pdf", _pdf(2), "application/pdf")}).json()["doc"]["id"]
    assert c.post(f"/api/docs/{did}/extracts", json={"focuses": "한국선급"}).status_code == 400
    assert c.post(f"/api/docs/{did}/extracts", json={"focuses": [f"범위{i}" for i in range(9)]}).status_code == 400
    got = c.post(f"/api/docs/{did}/extracts", json={"focuses": ["가", "나", "다"]}).json()
    ids = [x["id"] for x in got["extracts"]]
    assert got["extract"]["id"] == ids[0] and len(ids) == 3 and began.wait(20) and all(extract.running(i) for i in ids)
    assert c.delete(f"/api/extracts/{ids[0]}").json() == {"ok": True, "left": True}                 # 도는 범위 하나의 「지우기」 = 그 범위만 뺀다(나머지는 계속)
    assert c.get(f"/api/extracts/{ids[0]}").status_code == 404 and extract.running(ids[1]) and extract.mates_n(ids[1]) == 2
    assert c.post(f"/api/extracts/{ids[1]}/stop").json() == {"ok": True, "stopping": True, "mates": 2}   # 「멈춤」 = 함께 뽑는 범위 모두
    extract._RUNS[ids[1]][0].join(30)
    assert [c.get(f"/api/extracts/{i}").json()["extract"]["state"] for i in ids[1:]] == ["stopped", "stopped"]
    assert sorted(x["id"] for x in c.get("/api/docs").json()["docs"][0]["extracts"]) == sorted(ids[1:])
