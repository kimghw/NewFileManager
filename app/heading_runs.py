"""헤딩 추출 실행 관리(spec_헤딩_추출 ② §7) — 세션마다 헤딩 작업 하나(검증 작업 `s.jobs` 와 따로), 실행 결과는 불변으로 저장.

- 실행 = 단계 하나(1: 스크립트 추출 + 후보 규칙 시험 + 선택 LLM 규칙 보강, 2: 그래프). 시작 때 세션 rev·원본 sha256·지침(글째 — 프롬프트·오차 기준·기록)을
  고정, 규칙 version 은 결과를 뽑은(마지막) 추출의 저장소 것. 실행 번호는 작업 잠금 안에서 디스크·메모리 다음(겹치지 않음).
  1단계 레코드는 세션 잠금 안에서 뽑는다(편집과 겹치지 않게, 연구개발계획서 양식 1.6 s), LLM 은 잠금 밖.
- 저장: 작업 폴더 `headings/<n>/{run.json, stage1.json | graph.json, llm/<k>.json}` + `headings/current.json` {stage1, stage2}. 저장 끔이면 메모리만.
- 세션 속성(동적): `heads` = {"job": Job | None, "stage1": 결과, "stage2": 결과, "runs": [메타…]} — Session 클래스는 건드리지 않는다."""
import gzip
import json
import sys
import threading
import time
import traceback
import zlib

from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_llm as HL
from app import heading_rules as R
from app import heading_tables as HT
from app import works


class Busy(Exception):
    pass


class Job:
    def __init__(self, stage, use_llm, rev):
        self.stage, self.use_llm, self.rev = stage, use_llm, rev
        self.status, self.error, self.run = "running", None, None
        self.steps, self.started, self.ended = [], time.time(), None
        self.lock = threading.Lock()

    def step(self, name, status="running", msg=""):
        with self.lock:
            for s in self.steps:
                if s["name"] == name:
                    s.update(status=status, msg=msg, seconds=round(time.time() - s["t0"], 2))
                    return
            self.steps.append({"name": name, "status": status, "msg": msg, "t0": time.time(), "seconds": 0})

    def view(self):
        with self.lock:
            return {"stage": self.stage, "llm": self.use_llm, "status": self.status, "error": self.error, "run": self.run, "rev": self.rev,
                    "started": self.started, "ended": self.ended, "steps": [{k: v for k, v in s.items() if k != "t0"} for s in self.steps]}


def state(sess):
    st = getattr(sess, "heads", None)
    if st is None:
        st = sess.heads = {"job": None, "stage1": None, "stage2": None, "stage3": None, "runs": [], "loaded": False}
    if not st["loaded"]:
        st["loaded"] = True
        _load_current(sess, st)
    return st


def _dir(sess):
    f = works.folder(sess.id)
    return f / "headings" if f is not None and (f / "work.json").is_file() else None


def _live(sess):
    """서버가 지금 쥔 세션인가(server._persist 와 같은 검사) — 밀려났거나(_admit) 지운 세션의 늦게 끝난 실행은 작업 폴더에 쓰지 않는다
    (다시 연 세션의 결과·current.json 을 덮지 않게). 서버 없이 부르면(도구) 늘 참."""
    docs = getattr(sys.modules.get("app.server"), "DOCS", None)
    return docs is None or docs.get(sess.id) is sess


def _run_numbers(d):
    """디스크의 실행 번호(번호 폴더 — 쓰다 만 것도) 차례대로."""
    try:
        return sorted(int(p.name) for p in d.iterdir() if p.name.isascii() and p.name.isdigit() and p.is_dir())
    except OSError:
        return []


def _next_n(d, st):
    """다음 실행 번호 = 메모리 목록·디스크 번호 폴더 중 큰 것 다음 — 한 번 쓴 번호는 다시 안 쓴다(불변 결과, current.json·run.json 을 못 읽어도)."""
    mem = [r["n"] for r in st["runs"] if isinstance(r.get("n"), int)]
    return max(mem + (_run_numbers(d) if d is not None else []) + [0]) + 1


def _load_current(sess, st):
    """다시 연 세션 — 작업 폴더의 지금 결과(current.json)와 실행 목록을 읽어 둔다. 못 읽는 파일은 그것만 빠진다(나머지는 남음)."""
    d = _dir(sess)
    if d is None or not d.is_dir():
        return
    cur = works._read_json(d / "current.json")
    for stage, fname in (("stage1", "stage1.json"), ("stage2", "graph.json"), ("stage3", "tables.json")):
        n = cur.get(stage) if isinstance(cur, dict) else None
        if isinstance(n, int) and n > 0:
            res = _read(d / str(n) / fname)
            if isinstance(res, dict):
                if isinstance(res.get("meta"), dict):  # 실행 번호 없이 저장한 옛 결과 — current.json 의 번호
                    res["meta"].setdefault("run", n)
                st[stage] = res
    st["runs"] = [r for r in (works._read_json(d / str(n) / "run.json") for n in _run_numbers(d)) if isinstance(r, dict)]


def _save_run(sess, st, meta, payload_name, payload, calls):
    """실행 하나 저장 → 실행 번호. 번호는 작업 잠금 안에서 정하고(_next_n) 새 폴더에만 쓴다 — 밀려난 세션과 다시 연 세션이 겹쳐도
    같은 번호를 두 번 쓰지 않는다. 지운 작업·살아 있지 않은 세션이면 쓰지 않는다. 저장 끔이면 메모리의 번호만."""
    d = _dir(sess)
    n = _next_n(d, st)
    payload["meta"]["run"] = n  # 파일에도 실행 번호(다시 열어도 남게)
    st["lastSaved"] = None if d is None else False  # None = 저장 끔(메모리 번호), True = 실행 폴더에 씀, False = 못 씀·안 씀 — 기록(works.log)이 번호를 남길지
    if d is not None and _live(sess):
        try:
            blobs = _blobs(payload_name, payload, calls, meta)  # 압축은 잠금 밖(연구개발계획서 1단계 0.4 s) — 편집 기록(works.log)이 같은 잠금
            with works._lock(sess.id):  # 다시 들어갈 수 없는 잠금 — 안에서 works.log·update 를 부르지 않는다
                if (d.parent / "work.json").is_file() and _live(sess):  # 그 사이 지운 작업·밀려난 세션 — 되살리거나 덮지 않는다
                    n2 = _next_n(d, st)
                    if n2 != n:  # 드문 경합(다른 세션이 먼저 씀) — 번호를 고쳐 다시 묶음
                        n = payload["meta"]["run"] = n2
                        blobs = _blobs(payload_name, payload, calls, meta)
                    run = d / str(n)
                    run.mkdir(parents=True)  # 있으면 FileExistsError — 남의 실행 폴더에 섞어 쓰지 않는다
                    for rel, b in blobs:
                        works._write(run / rel, b)
                    works._write_json(run / "run.json", {k: v for k, v in {**meta, "n": n}.items() if k != "guides"})
                    cur = works._read_json(d / "current.json")
                    cur = cur if isinstance(cur, dict) else {}
                    cur[meta["stage_key"]] = n
                    works._write_json(d / "current.json", cur)
                    st["persistError"] = None
                    st["lastSaved"] = True
        except OSError as e:  # 디스크가 가득 차는 등 — 결과는 메모리에 두고 화면에 알린다
            st["persistError"] = f"헤딩 추출 결과를 작업 폴더에 못 썼습니다: {e}"
    st["runs"].append({k: v for k, v in {**meta, "n": n}.items() if k != "guides"})
    return n


def _blobs(payload_name, payload, calls, meta):
    """실행 폴더에 쓸 [(상대 경로, 바이트)] — 큰 결과(1단계 레코드 수 MB·프롬프트)는 gzip, 이름 끝에 .gz."""
    objs = [(payload_name, payload)] + [(f"llm/{i + 1}-{c['what'].replace('#', '-')}.json", c) for i, c in enumerate(calls)]
    if meta.get("guides"):
        objs.append(("guides.json", meta["guides"]))
    return [(rel + ".gz", gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)) for rel, obj in objs]


def _read(path):
    """path(.json) 또는 path.gz → 객체 | None. 깨진 gzip(잘림 EOFError·바이트 깨짐 zlib.error)도 None."""
    gz = path.with_name(path.name + ".gz")
    try:
        if gz.is_file():
            return json.loads(gzip.decompress(gz.read_bytes()).decode("utf-8"))
        if path.is_file():
            return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError, EOFError, zlib.error):
        return None
    return None


def _summary1(res):
    c = res["counts"]
    return {"paragraphs": c["paragraphs"], "xml": c["xml"], "check": c["check"], "labels": c["labels"], "formats": c["formats"],
            "kinds": c["kinds"], "unmatched": sum(g["count"] for g in res["review"]["unmatched"]), "unmatchedGroups": len(res["review"]["unmatched"]),
            "conflicts": len(res["review"]["conflicts"])}


def run_stage1(sess, job, use_llm, pinned=None):
    """pinned = 2단계가 시작 때 고정한 지침(heading_guides.snapshot() 꼴) — 없으면 여기서 고정(§7). 프롬프트·오차 기준·기록이 같은 지침."""
    st = state(sess)
    key = works.sha256(sess.original)
    guides0 = pinned or G.snapshot()
    tol = G.parse_tolerance(guides0["tolerance"]["text"])

    def extract():  # → (결과, 그 추출이 쓴 규칙 저장소 version, rev)
        store = R.load()
        with sess.lock:
            return E.extract(sess.doc, store=store, doc_key=key, tol=tol), store["version"], sess.rev
    job.step("추출")
    res, rules_v, rev = extract()
    job.step("추출", "ok", f"문단 {res['counts']['paragraphs']:,}개(XML {res['counts']['xml']:,}) · 서식 라벨 {res['counts']['labels']} · "
                          f"못 맞춤 {len(res['review']['unmatched'])}묶음 · 충돌 {len(res['review']['conflicts'])}묶음 · {res['seconds']} s")
    trial = E.trial_candidates(res, doc_key=key)
    passed = {rid: key for rid, t in trial.items() if t["passed"]}
    if passed:
        job.step("후보 규칙 시험")
        promoted = R.add_docs(passed, reason=f"{sess.name} 에서 통과")
        res, rules_v, _ = extract()
        job.step("후보 규칙 시험", "ok", f"다른 문서의 후보 규칙 {len(passed)}개 통과" + (f" · 전역으로 {len(promoted)}개" if promoted else ""))
    report = None
    if use_llm and (res["review"]["unmatched"] or res["review"]["conflicts"]):
        job.step("LLM 규칙 보강")
        report = HL.propose_rules(res, doc_key=key, doc_name=sess.name, run_id=None, pinned=guides0)
        msg = (f"묶음 {report['groups']} · 저장 {len(report['saved'])} · 그대로 {len(report['kept'])} · "
               f"거절 {sum(1 for i in report['items'] if i.get('verdict') == 'rejected')} · {report['seconds']} s · ${report['costUsd']}")
        if report["error"] and not report["items"]:
            job.step("LLM 규칙 보강", "failed", f"{report['error']}"[:300])
        else:
            job.step("LLM 규칙 보강", "ok", msg)
        if report["saved"] or report["kept"]:
            res, rules_v, _ = extract()
            job.step("다시 추출", "ok", f"못 맞춤 {len(res['review']['unmatched'])}묶음 · 충돌 {len(res['review']['conflicts'])}묶음")
    res["llm"] = {k: v for k, v in (report or {}).items() if k != "calls"} if report else None
    res["trial"] = trial
    res["meta"] = {"rev": rev, "sha256": key, "name": sess.name, "rulesVersion": rules_v,  # 마지막 추출이 쓴 저장소(실행 중 남이 바꿔도)
                   "guides": {n: g["sha1"] for n, g in guides0.items()}, "at": time.time()}
    meta = {"stage": 1, "stage_key": "stage1", "rev": rev, "llm": use_llm, "at": time.time(), "summary": _summary1(res),
            "costUsd": (report or {}).get("costUsd", 0), "guides": guides0 if use_llm else None}
    n = _save_run(sess, st, meta, "stage1.json", res, (report or {}).get("calls") or [])  # res["meta"]["run"] 도 넣음
    st["stage1"] = res
    return n


def run_stage2(sess, job, use_llm):
    st = state(sess)
    guides0 = G.snapshot()  # 시작 때 고정(§7) — A·B·C 프롬프트와 기록이 같은 지침
    s1 = st.get("stage1")
    if s1 is None or s1.get("meta", {}).get("rev") != sess.rev or s1.get("version") != E.VERSION:  # 옛 추출 방식의 결과(모양 키·간격·그릇 key)도 다시
        job.step("1단계(스크립트) 다시")
        run_stage1(sess, job, False, pinned=guides0)
        s1 = st["stage1"]
        job.step("1단계(스크립트) 다시", "ok", "결과가 없거나 문서·추출 방식이 바뀌어 1단계를 다시 뽑음")
    job.step("헤딩 그래프" + (" — LLM" if use_llm else " — 스크립트"))
    g = HG.build(s1, use_llm=use_llm, doc_name=sess.name, pinned=guides0)
    calls = g.pop("_calls", [])
    lm = g["llm"]
    msg = (f"노드 {g['counts']['nodes']} · 유형 {g['counts']['types']} · 템플릿 {g['counts']['templates']} · 인스턴스 {g['counts']['instances']} · "
           f"이종 형제 {g['counts']['heterogeneous']} · 조정 {g['counts']['adjust']}" +
           (f" · 재검토 {g['counts'].get('reviewed', 0)}(불일치 {g['counts'].get('disagreed', 0)})" if use_llm and lm.get("reviewPairs") else "") +
           (f" · LLM 호출 {lm['calls']}(실패 {lm['failed']}) 변경 {lm['applied']} 거절 {lm['rejected']} · ${lm['costUsd']}" if use_llm else "") +
           (" · LLM 없이 스크립트 대체 판정" if lm["fallback"] else ""))
    job.step("헤딩 그래프" + (" — LLM" if use_llm else " — 스크립트"), "failed" if use_llm and lm["fallback"] and lm.get("error") else "ok",
             msg + (f" — {lm['error']}" if lm.get("error") else ""))
    g["meta"] = {"rev": s1["meta"]["rev"], "stage1Run": s1["meta"].get("run"), "sha256": s1["meta"]["sha256"], "at": time.time(),
                 "guides": {n: x["sha1"] for n, x in guides0.items()}}
    meta = {"stage": 2, "stage_key": "stage2", "rev": s1["meta"]["rev"], "llm": use_llm, "at": time.time(), "stage1Run": s1["meta"].get("run"),
            "summary": g["counts"], "costUsd": lm["costUsd"], "guides": guides0 if use_llm else None}
    n = _save_run(sess, st, meta, "graph.json", g, calls)  # g["meta"]["run"] 도 넣음
    st["stage2"] = g
    return n


def run_stage3(sess, job, use_llm):
    """3단계 표 구조(spec ② §8) — 1단계가 없거나 오래됐으면(문서 rev·추출 방식) 먼저 다시 뽑고, heading_tables.build 로 초안(+ T 호출) → tables.json."""
    st = state(sess)
    guides0 = G.snapshot()  # 시작 때 고정(§7)
    s1 = st.get("stage1")
    if s1 is None or s1.get("meta", {}).get("rev") != sess.rev or s1.get("version") != E.VERSION:
        job.step("1단계(스크립트) 다시")
        run_stage1(sess, job, False, pinned=guides0)
        s1 = st["stage1"]
        job.step("1단계(스크립트) 다시", "ok", "결과가 없거나 문서·추출 방식이 바뀌어 1단계를 다시 뽑음")
    s2 = st.get("stage2")
    if not (s2 and s2.get("meta", {}).get("stage1Run") == s1["meta"].get("run")):
        s2 = None  # 2단계가 없거나 다른 1단계 실행의 것 — 표의 소속은 1단계 어림(spec ② §9)
    name = "표 구조" + (" — LLM" if use_llm else " — 스크립트")
    job.step(name)
    t = HT.build(s1, use_llm=use_llm, doc_name=sess.name, pinned=guides0, stage2=s2)
    calls = t.pop("_calls", [])
    lm, c = t["llm"], t["counts"]
    roles = c["roles"]
    msg = (f"표 {c['tables']} · 칸 {c['cells']:,} · 서브 테이블 {c['subtables']}(나뉜 표 {c['split']}) · 열헤더 {roles.get('colhead', 0)} · "
           f"행헤더 {roles.get('rowhead', 0)} · 필드 {roles.get('field', 0)}" +
           f" · 구분 헤더 표 {c['basisTables']} · 계산식 표 {c['calc']['tables']}(수식 {c['calc']['formulas']} · 불일치 {c['calc']['mismatch']} · "
           f"미기입 {c['calc']['missing']}) · 소속 = {'2단계 그래프' if s2 else '1단계 어림'}" +
           (f" · LLM 호출 {lm['calls']}(실패 {lm['failed']}) 보낸 표 {lm['sent']} 변경 {lm['applied']} 거절 {lm['rejected']} · ${lm['costUsd']}" if use_llm else "") +
           (" · LLM 없이 초안 그대로" if lm["fallback"] else ""))
    job.step(name, "failed" if use_llm and lm["fallback"] and lm.get("error") else "ok", msg + (f" — {lm['error']}" if lm.get("error") else ""))
    t["meta"] = {"rev": s1["meta"]["rev"], "stage1Run": s1["meta"].get("run"), "sha256": s1["meta"]["sha256"], "at": time.time(),
                 "guides": {n: x["sha1"] for n, x in guides0.items()}}
    meta = {"stage": 3, "stage_key": "stage3", "rev": s1["meta"]["rev"], "llm": use_llm, "at": time.time(), "stage1Run": s1["meta"].get("run"),
            "summary": t["counts"], "costUsd": lm["costUsd"], "guides": guides0 if use_llm else None}
    n = _save_run(sess, st, meta, "tables.json", t, calls)  # t["meta"]["run"] 도 넣음
    st["stage3"] = t
    return n


def _runner(stage):
    """단계 → 실행 함수(부를 때 찾는다 — 시험이 run_stage1·run_stage2 를 monkeypatch 한다)."""
    return run_stage1 if stage == 1 else run_stage2 if stage == 2 else run_stage3


_start_lock = threading.Lock()  # 「돌고 있나」 확인과 자리 잡기 사이에 다른 요청이 못 끼게(FastAPI 스레드 풀)


def start(sess, stage, use_llm):
    st = state(sess)
    with _start_lock:
        job0 = st.get("job")
        if job0 is not None and job0.status == "running":
            raise Busy("헤딩 추출이 이미 돌고 있습니다")
        job = Job(stage, use_llm, sess.rev)
        st["job"] = job

    def run():
        try:
            job.run = _runner(stage)(sess, job, use_llm)
            job.status = "done"
            saved = st.get("lastSaved")  # 저장이 실제로 한 일 — 안 쓴 실행(밀려난 세션·지운 작업·디스크 오류)의 번호는 다음 실행이 쓰므로 안 남김
            works.log(sess.id, "headings", stage=stage, llm=use_llm, status="done", rev=job.rev,
                      **({"n": job.run} if saved is not False else {"saved": False}))
        except Exception as e:  # 단계 실패 — 화면에 보이고 기록에 남김
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"
            job.step("오류", "failed", traceback.format_exc()[-800:])
            works.log(sess.id, "headings", stage=stage, llm=use_llm, status="failed", error=job.error[:300])
        finally:
            job.ended = time.time()
    threading.Thread(target=run, daemon=True).start()
    return job


def run_sync(sess, stage, use_llm):
    """시험·도구용 — 같은 일을 이 스레드에서."""
    job = Job(stage, use_llm, sess.rev)
    state(sess)["job"] = job
    job.run = _runner(stage)(sess, job, use_llm)
    job.status, job.ended = "done", time.time()
    return job


# ---- 화면용 요약 · 목록 ------------------------------------------------------------------------------------

PARA_KEYS = ("id", "block", "n", "sec", "area", "table", "cell", "row", "col", "depth", "kind", "rule", "family", "shape", "letter", "leadCode",
             "gapCode", "leadSpaces", "leadMm", "form", "blank", "fmt", "fp", "outlineLevel", "num", "gaps", "spacer")


def para_view(r):
    out = {k: r.get(k) for k in PARA_KEYS if r.get(k) is not None}
    out["text"] = r["text"][:200]
    p = r["para"]
    out["para"] = {k: p.get(k) for k in ("align", "indentLeftMm", "indentRightMm", "firstLineMm", "hangMm", "spaceBeforePt", "spaceAfterPt",
                                         "lineSpacing", "paraPr") if p.get(k) is not None}
    out["char"] = r["char"]
    ln = r["line"]
    out["line"] = {"cache": ln.get("cache"), "count": ln.get("count"), "indentLine": ln.get("indentLine")}
    out["spans"] = [{k: s[k] for k in ("i", "kind", "letter", "line")} for s in r["spans"]]
    return out


def summary(sess):
    st = state(sess)
    job = st.get("job")
    s1, s2, s3 = st.get("stage1"), st.get("stage2"), st.get("stage3")
    out = {"job": job.view() if job else None, "rev": sess.rev, "runs": st["runs"][-20:], "stage1": None, "stage2": None, "stage3": None,
           "persistError": st.get("persistError")}
    if s1:
        labels = sorted(s1["labels"].values(), key=lambda l: -l["count"])
        out["stage1"] = {"meta": s1.get("meta"), "counts": s1["counts"], "summary": _summary1(s1),
                         "stale": s1.get("meta", {}).get("rev") != sess.rev or s1.get("version") != E.VERSION,
                         "review": {"unmatched": [{k: g[k] for k in ("key", "shape", "count", "examples")} for g in s1["review"]["unmatched"]],
                                    "conflicts": [{k: g[k] for k in ("key", "rules", "shape", "count", "examples")} for g in s1["review"]["conflicts"]]},
                         "labelsTop": [{k: l[k] for k in ("id", "name", "count", "kinds", "sample")} | {"variants": len(l["variants"])} for l in labels[:30]],
                         "llm": s1.get("llm"), "trial": s1.get("trial"), "warnings": s1.get("warnings")}
    if s2:
        out["stage2"] = {"meta": s2.get("meta"), "counts": s2["counts"], "llm": s2["llm"], "stale": s2.get("meta", {}).get("rev") != sess.rev,
                         "templates": [{k: t.get(k) for k in ("name", "kind", "root", "note", "slots")} for t in s2["templates"]],
                         "heterogeneous": s2["heterogeneous"][:50], "repeats": len(s2["repeats"]),
                         "adjust": sum(1 for a in s2["adjustments"] if a["decision"] == "adjust")}
    if s3:  # 표 목록은 요약만(칸은 GET /headings/tables)
        out["stage3"] = {"meta": s3.get("meta"), "counts": s3["counts"], "llm": s3["llm"], "stale": s3.get("meta", {}).get("rev") != sess.rev,
                         "tables": [{"id": t["id"], "host": t["host"], "before": t["before"], "rows": t["rows"], "cols": t["cols"], "depth": t["depth"],
                                     "cells": len(t["cells"]), "counts": t["counts"], "issues": len(t["issues"]),
                                     "subtables": [{k: s.get(k) for k in ("id", "rows", "cols", "kind", "headerRows", "headerCols", "source")} for s in t["subtables"]],
                                     "owner": t.get("owner"), "basis": t.get("basis"), "calc": t.get("calc"),  # §9
                                     "notes": len(t.get("notes") or []),  # §10 작성요령 수(「표」 탭 목록)
                                     "llm": {k: t["llm"].get(k) for k in ("sent", "changed", "undecided")}} for t in s3["tables"]],
                         "repeats": s3["repeats"][:20]}
    return out


def paras(sess, *, kind=None, fmt=None, rule=None, area=None, q=None, offset=0, limit=100):
    s1 = state(sess).get("stage1")
    if not s1:
        return {"total": 0, "offset": offset, "items": []}
    items = [r for r in s1["paras"] if (not kind or r["kind"] == kind) and (not fmt or r["fmt"] == fmt) and (not rule or r["rule"] == rule)
             and (not area or r["area"] == area) and (not q or q in r["text"])]
    return {"total": len(items), "offset": offset, "items": [para_view(r) for r in items[offset:offset + max(1, min(limit, 500))]]}


def labels(sess):
    s1 = state(sess).get("stage1")
    if not s1:
        return {"labels": [], "formats": 0}
    return {"labels": [{k: v for k, v in l.items() if k not in ("para", "char")} | {"para": l["para"], "char": l["char"]} for l in s1["labels"].values()],
            "formats": len(s1["formats"])}


def graph(sess):
    return state(sess).get("stage2")


def tables(sess):
    return state(sess).get("stage3")
