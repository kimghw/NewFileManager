"""헤딩 추출 API·지침 고침(5b 검증) — S3-postinput · S3-patch · S3-poller · S1-minor(b·c) · S1-linespacing(지침 쪽).

LLM 은 늘 끈다(NFM_LLM_BACKEND=off) — 단계 실행은 가짜 run_stage1·run_stage2. 규칙·지침 저장소는 시험마다 임시 폴더(NFM_HEADINGS).
헤딩 poll(app.js headsStart·headsPoll)은 node 로 그 함수만 떼어 가짜 api 로 돌린다(node 없으면 건너뜀)."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, server

ROOT = Path(__file__).parents[1]
SMALL = ROOT / "samples" / "기술수요조사서.hwpx"
APP_JS = Path(os.environ.get("NFM_APP_JS") or ROOT / "app" / "static" / "app.js")


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    """규칙·지침 저장소는 시험마다 빈 임시 폴더, LLM 은 끔, 메모리 저장소(저장 끔일 때)도 비움."""
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


@pytest.fixture
def c():
    server.DOCS.clear()
    yield TestClient(server.app, raise_server_exceptions=False)  # 처리 못 한 예외는 500 으로 보이게
    server.DOCS.clear()


def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _wait_heads(c, d, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/headings").json()
        if v["job"] and v["job"]["status"] != "running":
            return v
        time.sleep(0.02)
    raise AssertionError("헤딩 추출이 끝나지 않음")


def _square(v):
    return next(x for x in v["builtin"] if x["id"] == "b.square")["enabled"]


def _learned():
    R.add_rules([{"name": "t", "kind": "marker", "family": "test", "pattern": r"\(\d-\d\)"}], source="user")
    return R.load()["version"]


# ---- S3-postinput: stage 는 정수 1·2, llm 은 진짜 bool ---------------------------------------------------------

def test_api_start_rejects_loose_types(c, monkeypatch):
    seen = []
    monkeypatch.setattr(heading_runs, "run_stage1", lambda sess, job, use_llm: seen.append((1, use_llm)) or 0)
    monkeypatch.setattr(heading_runs, "run_stage2", lambda sess, job, use_llm: seen.append((2, use_llm)) or 0)
    d = _upload(c, SMALL)
    for body in ({"stage": True}, {"stage": 1.0}, {"stage": "1"}, {"stage": 1, "llm": "false"}, {"stage": 2, "llm": "0"},
                 {"stage": 1, "llm": 1}, {"stage": 1, "llm": None}):
        assert c.post(f"/api/docs/{d}/headings", json=body).status_code == 400, body
    assert seen == []  # 아무 실행도(특히 LLM 실행) 시작 안 됨
    r = c.post(f"/api/docs/{d}/headings", json={"stage": 1, "llm": False})
    assert r.status_code == 202 and r.json()["stage"] == 1 and r.json()["llm"] is False
    _wait_heads(c, d)
    r = c.post(f"/api/docs/{d}/headings", json={"stage": 2})  # llm 안 주면 false
    assert r.status_code == 202 and r.json()["llm"] is False
    _wait_heads(c, d)
    assert seen == [(1, False), (2, False)]


# ---- S3-patch: 거절한 요청은 아무것도 안 바꿈 · 정수 아닌 version 은 400 · 쓰기 실패는 503 ------------------------------

def test_api_rule_patch_is_all_or_nothing(c):
    r = c.patch("/api/headings/rules/b.square", json={"enabled": False, "status": "global", "version": 0})
    assert r.status_code == 404  # 내장은 상태 없음
    v = c.get("/api/headings/rules").json()
    assert v["version"] == 0 and _square(v)  # 거절했으면 아무것도 안 바뀜
    assert c.get("/api/headings/history", params={"kind": "rules"}).json() == []
    ver = _learned()
    assert c.patch("/api/headings/rules/l1", json={"enabled": False, "status": "bogus", "version": ver}).status_code == 400
    assert c.patch("/api/headings/rules/l1", json={"enabled": "false", "version": ver}).status_code == 400  # "false" 는 bool 아님
    v = c.get("/api/headings/rules").json()
    assert v["version"] == ver and v["learned"][0]["enabled"] is True and v["learned"][0]["status"] == "candidate"
    # 둘 다 맞으면 둘 다
    r = c.patch("/api/headings/rules/l1", json={"enabled": False, "status": "global", "version": ver})
    assert r.status_code == 200 and r.json()["learned"][0]["enabled"] is False and r.json()["learned"][0]["status"] == "global"


@pytest.mark.parametrize("bad", [[1], {}, "x"])
def test_api_non_numeric_version_is_400(c, bad):
    assert c.patch("/api/headings/rules/b.square", json={"enabled": False, "version": bad}).status_code == 400
    assert c.put("/api/headings/guides/rules", json={"text": "x", "version": bad}).status_code == 400
    assert c.get("/api/headings/rules").json()["version"] == 0 and not G.get("rules")["custom"]
    with pytest.raises(ValueError):
        G.save("graph", "x", expect=bad)
    assert not G.get("graph")["custom"]


def test_api_write_oserror_is_503(c, monkeypatch):
    assert c.put("/api/headings/guides/graph", json={"text": "# g"}).status_code == 200
    ver = _learned()

    def boom(*a, **k):
        raise PermissionError(13, "잠김")
    with monkeypatch.context() as m:  # 저장소 env 는 그대로 두고 이것만 되돌림
        m.setattr(R, "_write_json", boom)  # rules.json·지침 메타 쓰기가 막힘
        assert c.patch("/api/headings/rules/b.square", json={"enabled": False, "version": ver}).status_code == 503
        assert c.delete("/api/headings/rules/l1", params={"version": ver}).status_code == 503
        assert c.delete("/api/headings/guides/graph").status_code == 503
    v = c.get("/api/headings/rules").json()
    assert v["version"] == ver and _square(v) and [r["id"] for r in v["learned"]] == ["l1"]
    g = c.get("/api/headings/guides/graph").json()
    assert g["custom"] and g["text"] == "# g" and g["version"] == 1  # 못 되돌렸으면 사본·판 그대로


# ---- S1-minor (b): 되돌리기 뒤에도 version 이 이어진다(ABA 막기) ---------------------------------------------------

def test_guides_reset_keeps_version_monotonic(tmp_path):
    a = G.save("graph", "A 의 글", expect=0)
    r = G.reset("graph")
    assert not r["custom"] and r["version"] == a["version"] + 1 and r["text"] == r["default"]
    assert r["base"] is None and not r["defaultChanged"]
    assert R.history("guide")[-1]["action"] == "reset" and R.history("guide")[-1]["version"] == r["version"]
    assert not (tmp_path / "heads" / "guides" / "graph.md").exists()
    assert G.reset("graph")["version"] == r["version"]  # 사본이 없으면 글이 안 바뀜 — 판도 그대로
    assert G.rebase("graph")["custom"] is False
    b = G.save("graph", "B 의 글", expect=r["version"])
    assert b["version"] == r["version"] + 1 and b["custom"] and b["base"] == b["defaultSha1"]
    with pytest.raises(R.StaleVersion):
        G.save("graph", "A 의 오래된 편집", expect=a["version"])
    assert G.get("graph")["text"] == "B 의 글"
    assert G.get("templates")["version"] == 0 and G.reset("templates")["version"] == 0  # 손댄 적 없는 지침


def test_guides_reset_keeps_version_memory_mode(monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", "off")
    a = G.save("rules", "메모리 글", expect=0)
    r = G.reset("rules")
    assert not r["custom"] and r["version"] == a["version"] + 1
    with pytest.raises(R.StaleVersion):
        G.save("rules", "오래된 편집", expect=a["version"])
    assert G.save("rules", "새 글", expect=r["version"])["version"] == r["version"] + 1


def test_api_guide_reset_then_stale_put_is_409(c):
    a = c.put("/api/headings/guides/graph", json={"text": "A", "version": 0}).json()
    r = c.delete("/api/headings/guides/graph")
    assert r.status_code == 200 and not r.json()["custom"] and r.json()["version"] == a["version"] + 1
    assert c.put("/api/headings/guides/graph", json={"text": "B", "version": r.json()["version"]}).status_code == 200
    assert c.put("/api/headings/guides/graph", json={"text": "A 오래됨", "version": a["version"]}).status_code == 409
    assert c.get("/api/headings/guides/graph").json()["text"] == "B"


# ---- S1-minor (c): 오차 문턱은 0 이상의 유한한 숫자 ---------------------------------------------------------------

@pytest.mark.parametrize("val", ["NaN", "Infinity", "-Infinity", "true", "-1"])
def test_parse_tolerance_rejects_non_finite_and_bool(val):
    bad = f'```json\n{{"sizePt": {val}}}\n```'
    with pytest.raises(ValueError):
        G.parse_tolerance(bad)
    with pytest.raises(ValueError):
        G.save("tolerance", bad)
    assert not G.get("tolerance")["custom"]


def test_parse_tolerance_accepts_zero_and_floats():
    t = G.parse_tolerance('```json\n{"sizePt": 0, "leadMm": 1.25}\n```')
    assert t["sizePt"] == 0 and t["leadMm"] == 1.25


# ---- S1-linespacing(지침 쪽): 고정·최소·여백 줄 간격(pt) 문턱 lineSpacingPt -------------------------------------------

def test_tolerance_line_spacing_pt_default_and_guide():
    assert G.TOLERANCE_DEFAULT["lineSpacingPt"] == 1.0
    text = G.default_text("tolerance")
    block = json.loads(G._JSON_BLOCK.search(text).group(1))
    assert block == G.TOLERANCE_DEFAULT  # 기본본 json 블록과 코드 기본값이 같다
    assert "lineSpacingPt:" in text.split("```")[2]  # 설명 줄
    assert G.parse_tolerance(text)["lineSpacingPt"] == 1.0
    assert G.parse_tolerance('```json\n{"sizePt": 1}\n```')["lineSpacingPt"] == 1.0  # 옛 사본(키 없음)은 기본값
    assert G.parse_tolerance('```json\n{"lineSpacingPt": 2.5}\n```')["lineSpacingPt"] == 2.5


# ---- S3-poller: POST 뒤에 보낸 GET 이 작업 없음이면 멈춘다(POST 전에 보낸 GET 의 늦은 응답은 그대로 건너뜀) -------------------

HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync(process.argv[2], "utf8"), mode = process.argv[3];
function grab(name) { // app.js 에서 함수 하나를 중괄호 짝으로 떼어 냄
  let i = src.indexOf(`async function ${name}(`);
  if (i < 0) i = src.indexOf(`function ${name}(`);
  if (i < 0) i = src.indexOf(`const ${name} =`);
  if (i < 0) throw new Error(`없음: ${name}`);
  let depth = 0;
  for (let k = src.indexOf("{", i); k < src.length; k++) {
    if (src[k] === "{") depth++;
    else if (src[k] === "}" && --depth === 0) { let e = k + 1; if (src[e] === ")") e++; if (src[e] === ";") e++; return src.slice(i, e); }
  }
}
const J0 = { stage: 1, status: "done", started: 999.0, steps: [] };
const J1 = (status) => ({ stage: 1, status, started: 1000.25, steps: [] });
const view = (job) => ({ rev: 3, runs: [], stage1: null, stage2: null, job });
let gets = 0, posts = 0, pending = null;
const renders = [], out = { logTouched: 0, failed: 0, toasts: 0 };
const ctx = { state: { id: "d1", epoch: 1, serverRev: 3 }, H_JSON: {}, JSON, Promise,
  flushAll: async () => {}, toast: () => { out.toasts++; }, logTouched: () => { out.logTouched++; }, headsFailed: () => { out.failed++; },
  headsRender: (r) => renders.push(r.job ? `${r.job.started}:${r.job.status}` : null), setTimeout: (fn) => { fn(); return 0; },
  api: async (url, opts) => {
    if (opts && opts.method === "POST") {
      posts++;
      if (mode === "prepost" && posts === 1) { const e = new Error("가짜 500"); e.status = 500; throw e; }
      return J1("running");
    }
    if (++gets >= 30) ctx.state.epoch = 2; // 멈추지 않는 고리 끊기
    if (mode === "lost") return view(null); // 서버가 세션을 잃음(재시작·밀려남)
    if (mode === "late" && gets === 1) return view(J0); // 앞선 작업의 늦은 응답
    if (mode === "prepost") {
      if (gets === 1) return new Promise((res) => { pending = () => res(view(null)); }); // POST 전에 보낸 GET — 아직 작업 없음
      return view(J1("done"));
    }
    return view(J1(gets >= 3 ? "done" : "running"));
  } };
vm.createContext(ctx);
vm.runInContext(["headsFresh", "headsStart", "headsPoll"].map(grab).join("\n") + "\nlet heads = headsFresh(); this.H = () => heads;", ctx);
const tick = async (n) => { for (let i = 0; i < n; i++) await new Promise((r) => setImmediate(r)); };
(async () => {
  await vm.runInContext("headsStart(1, false)", ctx); // prepost: POST 500 → 그래도 poll 시작, 첫 GET 은 붙잡아 둠
  await tick(50);
  if (mode === "prepost") {
    if (!pending) throw new Error("첫 GET 이 안 나감");
    await vm.runInContext("headsStart(1, false)", ctx); // 다시 눌러 POST 성공 — 고리는 이미 돌고 있음
    await tick(50);
    pending(); // 그 뒤에야 POST 전 GET 의 「작업 없음」 응답이 옴
  }
  await tick(300);
  console.log(JSON.stringify({ gets, posts, renders, ...out, expect: ctx.H().expect, polling: ctx.H().pollEpoch }));
})();
"""


def _poll(tmp_path, mode, app_js=APP_JS):
    h = tmp_path / "heads_poll.js"
    h.write_text(HARNESS, encoding="utf-8")
    p = subprocess.run(["node", str(h), str(app_js), mode], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


@needs_node
def test_heads_poll_stops_when_job_vanishes(tmp_path):
    r = _poll(tmp_path, "lost")
    assert r["gets"] == 1 and r["renders"] == ["1000.25:running", None], r  # 고치기 전: GET 30번(끝없이) · 그리기 1번
    assert r["logTouched"] == 1 and r["expect"] is None and r["polling"] is None and r["failed"] == 0


@needs_node
def test_heads_poll_still_skips_late_answer_of_previous_job(tmp_path):
    r = _poll(tmp_path, "late")
    assert r["renders"] == ["1000.25:running", "1000.25:running", "1000.25:done"], r
    assert r["gets"] == 3 and r["logTouched"] == 1 and r["polling"] is None


@needs_node
def test_heads_poll_skips_job_less_answer_sent_before_post(tmp_path):
    """POST 전에 보낸 GET 의 「작업 없음」은 늦은 응답 — 건너뛰고 새 작업을 끝까지 따라간다(그리고 멈추면 새 작업을 놓침)."""
    r = _poll(tmp_path, "prepost")
    assert r["posts"] == 2 and r["toasts"] == 1
    assert r["renders"] == ["1000.25:running", "1000.25:done"], r
    assert r["gets"] == 2 and r["logTouched"] == 1 and r["polling"] is None
