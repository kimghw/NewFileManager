"""헤딩 추출 실행 관리(spec_헤딩_추출 ② §7) — 세션마다 헤딩 작업 하나(검증 작업 `s.jobs` 와 따로), 실행 결과는 불변으로 저장.

- 실행 = 단계 하나(1: 스크립트 추출 + 후보 규칙 시험 + 선택 LLM 규칙 보강, 2: 그래프). 시작 때 세션 rev·원본 sha256·지침(글째 — 프롬프트·오차 기준·기록)을
  고정, 규칙 version 은 결과를 뽑은(마지막) 추출의 저장소 것. 실행 번호는 작업 잠금 안에서 디스크·메모리 다음(겹치지 않음).
  1단계 레코드는 세션 잠금 안에서 뽑는다(편집과 겹치지 않게, 연구개발계획서 양식 1.6 s), LLM 은 잠금 밖.
- 저장: 작업 폴더 `headings/<n>/{run.json, stage1.json | graph.json, llm/<k>.json}` + `headings/current.json` {stage1, stage2}. 저장 끔이면 메모리만.
- 세션 속성(동적): `heads` = {"job": Job | None, "stage1": 결과, "stage2": 결과, "runs": [메타…]} — Session 클래스는 건드리지 않는다."""
import copy
import gzip
import json
import os
import sys
import threading
import time
import traceback
import zlib

from app import heading_extract as E
from app import heading_forms as F
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_llm as HL
from app import heading_rules as R
from app import heading_tables as HT
from app import heading_temp as TP
from app import works


class Busy(Exception):
    pass


class Job:
    def __init__(self, stage, use_llm, rev):
        self.stage, self.use_llm, self.rev = stage, use_llm, rev
        self.first = False  # 첫 분석(2단계 → 3단계를 한 작업으로 — run_first, spec_작업 ② §9)
        self.chain = None  # 이어 돌리기 이름("llm" = LLM 검증·보완 — app/analysis_llm.py, spec_작업 ② §20) | None
        self.phase = None  # 이어 돌리기의 지금 일("heads" · "tables" · "formats") — 분석 상태가 어느 항목이 도는지 안다
        self.stop = False  # 이어 돌리기를 지금 단계가 끝나면 멈춤(DELETE …/analysis/llm)
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
            return {"stage": self.stage, "llm": self.use_llm, "first": self.first, "chain": self.chain, "phase": self.phase, "stopping": self.stop, "status": self.status, "error": self.error, "run": self.run, "rev": self.rev,
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
    st["hints"] = _read_hints(d)  # 지정(라벨 §13 · TEMP §15)도 여기서 — 실행 중에 작업 폴더를 다시 묻지 않게(1단계 끝의 TEMP 라벨이 쓴다)
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


def _guides(sess):
    """실행 시작 때 고정하는 지침 — 일반 지침 5개(heading_guides) + 이 문서의 양식 정보("form", 맞는 양식이 있을 때만 — spec ② §12)."""
    g = G.snapshot()
    form = F.pin(sess)
    if form:
        g["form"] = form
    return g


def run_stage1(sess, job, use_llm, pinned=None):
    """pinned = 2단계가 시작 때 고정한 지침(_guides 꼴) — 없으면 여기서 고정(§7). 프롬프트·오차 기준·기록이 같은 지침."""
    st = state(sess)
    key = getattr(sess, "doc_key", None) or works.sha256(sess.original)  # 문서 키 = 올린 원본의 sha256 — 확정으로 기준(sess.original)이 바뀌어도 같은 문서(spec_작업 ② §8)
    guides0 = pinned or _guides(sess)
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
    if use_llm:  # 규칙 보강을 어디까지 했나(§7 「진행 줄」) — 실행 목록에 남겨 그 뒤 스크립트로 다시 뽑아도 보인다(배운 규칙은 저장소에 남는다)
        meta["rules"] = _rules_meta(report)
    n = _save_run(sess, st, meta, "stage1.json", res, (report or {}).get("calls") or [])  # res["meta"]["run"] 도 넣음
    st["stage1"] = res
    job.step("TEMP 라벨", "ok", TP.summary_text(temp_label(sess)))  # 표 안 작성요령·쓸 자리(§15) — 2·3단계가 시작할 때 다시 셈한다(결과 파일에는 안 넣음)
    return n


def _rules_meta(report):
    """LLM 1단계 실행의 규칙 보강 요약(실행 목록 run.json 의 "rules") — report None = 물을 묶음이 없었음(groups 0).
    asked = 답을 받음(호출이 모두 실패하면 거짓 — _rules_asked 와 같은 기준)."""
    rep = report or {}
    items = rep.get("items") or []
    verdicts = [i.get("verdict") for i in items]
    return {"groups": rep.get("groups", 0), "asked": bool(items), "saved": len(rep.get("saved") or []), "kept": len(rep.get("kept") or []),
            "rejected": verdicts.count("rejected"), "unsure": verdicts.count("unsure"), "seconds": rep.get("seconds"), "error": rep.get("error")}


def rules_view(st):
    """이 문서에서 LLM 규칙 보강을 마지막으로 돌린 1단계 실행(spec ② §7 「진행 줄」) → None(한 번도 안 함) | {run, at, costUsd, groups, asked, saved, …}.
    지금 1단계 결과가 그 뒤 스크립트로 다시 뽑은 것이어도 보강은 한 것이다 — 배운 규칙·keeps 는 저장소에 남아 그 추출에 쓰였다.
    "rules" 가 없는 옛 실행(이 키 전)은 답을 받은 것으로 본다(asked None — 몇 개인지는 모름)."""
    last = next((r for r in reversed(st["runs"]) if r.get("stage") == 1 and r.get("llm")), None)
    if last is None:
        return None
    rr = last.get("rules") if isinstance(last.get("rules"), dict) else {"asked": None}
    return {"run": last.get("n"), "at": last.get("at"), "costUsd": last.get("costUsd", 0), **rr}


def _unjudged(s1):
    """1단계가 판정하지 못한 묶음 수(못 맞춤 + 충돌) — LLM 판정이 그래프보다 먼저 보는 것(spec ② §3 「LLM 판정은 스크립트가 판정하지 못한 것까지 본다」)."""
    rv = (s1 or {}).get("review") or {}
    return len(rv.get("unmatched") or []) + len(rv.get("conflicts") or [])


def _rules_asked(s1):
    """그 1단계 결과가 규칙 보강의 답을 받은 적이 있는가 — 받았으면 남은 묶음(LLM 이 모르겠다고 한 것 · 검증에 떨어진 제안)을 다시 묻지 않는다. 호출이 모두 실패한 결과는 안 받은 것."""
    return bool(((s1 or {}).get("llm") or {}).get("items"))


def pairs_on():
    """서식 쌍 판정(C)과 재검토(D)를 헤딩 그래프(LLM)에서 하나 — **기본은 안 한다**(env `NFM_HEADS_PAIRS=on` 일 때만).
    2026-11-16 사용자 「C·D 호출 제외 … 다 해줘」(spec ② §6 「서식 쌍 판정은 기본 실행에서 뺀다」): 그 판정(맞춤 · 다름 유지)은 문서도 서식 정리 계획도 바꾸지 않는데 2단계 비용의 절반 · 시간의 대부분이었고,
    같은 템플릿의 서식은 조정 층의 서식 정리 계획(기준 — 레터)이 정한다."""
    return os.environ.get("NFM_HEADS_PAIRS", "").strip().lower() in ("on", "1", "true", "yes")


def run_stage2(sess, job, use_llm):
    st = state(sess)
    guides0 = _guides(sess)  # 시작 때 고정(§7) — A·B·C 프롬프트와 기록이 같은 지침(+ 양식 정보)
    hints0 = copy.deepcopy(hints(sess))  # 라벨 지정도 시작 때 고정(§13) — 실행 중 바꿔도 이 실행은 이 지정으로
    s1 = st.get("stage1")
    stale = s1 is None or s1.get("meta", {}).get("rev") != sess.rev or s1.get("version") != E.VERSION  # 옛 추출 방식의 결과(모양 키·간격·그릇 key)도 다시
    # LLM 판정은 스크립트가 판정하지 못한 것(못 맞춤·충돌)까지 본다(§3, 2026-11-16) — 그래프를 짓기 전에 그 묶음의 규칙 보강을 먼저. 이미 답을 받은 1단계 결과는 다시 묻지 않는다
    ask_rules = bool(use_llm) and (stale or (_unjudged(s1) > 0 and not _rules_asked(s1)))
    rules = None
    if stale or ask_rules:
        name = "1단계 다시 — 못 맞춤·충돌 LLM 규칙 보강" if ask_rules else "1단계(스크립트) 다시"
        before = _unjudged(s1)
        job.step(name)
        n1 = run_stage1(sess, job, ask_rules, pinned=guides0)
        s1 = st["stage1"]
        rep = s1.get("llm") if ask_rules else None  # 보강 보고(호출 기록 뺌) — 물을 묶음이 없었으면 None
        if rep:
            rules = {"run": n1, "groups": rep.get("groups", 0), "saved": len(rep.get("saved") or []), "kept": len(rep.get("kept") or []),
                     "rejected": sum(1 for i in rep.get("items") or [] if i.get("verdict") == "rejected"), "left": _unjudged(s1),
                     "costUsd": rep.get("costUsd", 0), "error": rep.get("error")}
            works.log(sess.id, "headings", stage=1, llm=True, status="done", rev=s1["meta"]["rev"], within=2,
                      **({"n": n1} if st.get("lastSaved") is not False else {"saved": False}))
            job.step(name, "failed" if rules["error"] and not rep.get("items") else "ok",
                     f"판정하지 못한 묶음 {rules['groups']} → 규칙 저장 {rules['saved']} · 그대로 {rules['kept']} · 거절 {rules['rejected']} · 남은 묶음 {rules['left']}"
                     + (f" — {rules['error']}"[:200] if rules["error"] else ""))
        elif ask_rules:
            job.step(name, "ok", "결과가 없거나 문서·추출 방식이 바뀌어 1단계를 다시 뽑음 · 판정하지 못한 묶음 없음" if stale else f"판정하지 못한 묶음 {before} → 물을 것 없음")
        else:
            job.step(name, "ok", "결과가 없거나 문서·추출 방식이 바뀌어 1단계를 다시 뽑음")
    temp0 = TP.label(s1, hints0["temp"])  # TEMP 라벨(§15) — 본문 검토 전에: 그 문단들은 헤딩 후보에서 빠진다
    job.step("TEMP 라벨 — 헤딩 후보에서 뺌", "ok", TP.summary_text(temp0))
    job.step("헤딩 그래프" + (" — LLM" if use_llm else " — 스크립트"))
    g = HG.build(s1, use_llm=use_llm, doc_name=sess.name, pinned=guides0, hints=hints0, temp=temp0, pairs=pairs_on())
    calls = g.pop("_calls", [])
    lm = g["llm"]
    lm["rules"] = rules  # 이 LLM 판정이 먼저 돌린 규칙 보강(§3 — 판정하지 못한 묶음) | None(안 돎 — 스크립트 실행 · 물을 묶음 없음 · 이미 답을 받은 1단계)
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
    st.pop("bases2", None)  # 라벨 지정 반영(relabel)이 쥐고 있던 앞 추출 — 새 추출이 생겼으니 놓는다
    return n


def run_stage3(sess, job, use_llm):
    """3단계 표 구조(spec ② §8) — 1단계가 없거나 오래됐으면(문서 rev·추출 방식) 먼저 다시 뽑고, heading_tables.build 로 초안(+ T 호출) → tables.json."""
    st = state(sess)
    guides0 = _guides(sess)  # 시작 때 고정(§7)
    s1 = st.get("stage1")
    if s1 is None or s1.get("meta", {}).get("rev") != sess.rev or s1.get("version") != E.VERSION:
        job.step("1단계(스크립트) 다시")
        run_stage1(sess, job, False, pinned=guides0)
        s1 = st["stage1"]
        job.step("1단계(스크립트) 다시", "ok", "결과가 없거나 문서·추출 방식이 바뀌어 1단계를 다시 뽑음")
    s2 = st.get("stage2")
    if not (s2 and s2.get("meta", {}).get("stage1Run") == s1["meta"].get("run")):
        s2 = None  # 2단계가 없거나 다른 1단계 실행의 것 — 표의 소속은 1단계 어림(spec ② §9)
    temp0 = TP.label(s1, copy.deepcopy(hints(sess)["temp"]))  # TEMP 라벨(§15) — 표 검토 전에: TEMP 표는 표 구조를 만들지 않는다
    job.step("TEMP 라벨 — 표 구조에서 뺌", "ok", f"TEMP 표 {len(temp0['tables'])}개(안쪽 표·상자 포함) · " + TP.summary_text(temp0))
    name = "표 구조" + (" — LLM" if use_llm else " — 스크립트")
    job.step(name)
    from app import table_heads  # 사용자 헤더 지정(spec_owpml_편집 ② §5-4) — 부를 때 가져온다(table_heads 가 표 모듈들을 읽는다)
    t = HT.build(s1, use_llm=use_llm, doc_name=sess.name, pinned=guides0, stage2=s2, temp=temp0, roles=table_heads.load(sess.id)["tables"])
    calls = t.pop("_calls", [])
    lm, c = t["llm"], t["counts"]
    roles = c["roles"]
    msg = (f"표 {c['tables']}" + (f"(TEMP 표 {c['tempTables']} 뺌)" if c.get("tempTables") else "") + f" · 칸 {c['cells']:,} · 서브 테이블 {c['subtables']}(나뉜 표 {c['split']}) · 열헤더 {roles.get('colhead', 0)} · "
           f"행헤더 {roles.get('rowhead', 0)} · 필드 {roles.get('field', 0)}" +
           f" · 구분 헤더 표 {c['basisTables']} · 계산식 표 {c['calc']['tables']}(수식 {c['calc']['formulas']} · 불일치 {c['calc']['mismatch']} · "
           f"미기입 {c['calc']['missing']}) · 소속 = {'2단계 그래프' if s2 else '1단계 어림'}" +
           (f" · LLM 호출 {lm['calls']}(실패 {lm['failed']}) 보낸 표 {lm['sent']} 변경 {lm['applied']} 거절 {lm['rejected']} · ${lm['costUsd']}" if use_llm else "") +
           (" · LLM 없이 초안 그대로" if lm["fallback"] else ""))
    job.step(name, "failed" if use_llm and lm["fallback"] and lm.get("error") else "ok", msg + (f" — {lm['error']}" if lm.get("error") else ""))
    t["meta"] = {"rev": s1["meta"]["rev"], "stage1Run": s1["meta"].get("run"), "sha256": s1["meta"]["sha256"], "at": time.time(),
                 "stage2Run": (s2.get("meta") or {}).get("run") if s2 else None,  # 표 소속이 기댄 2단계 실행(없으면 1단계 어림) — 2단계가 바뀌면 소속이 옛것(§13)
                 "guides": {n: x["sha1"] for n, x in guides0.items()}}
    meta = {"stage": 3, "stage_key": "stage3", "rev": s1["meta"]["rev"], "llm": use_llm, "at": time.time(), "stage1Run": s1["meta"].get("run"),
            "summary": t["counts"], "costUsd": lm["costUsd"], "guides": guides0 if use_llm else None}
    n = _save_run(sess, st, meta, "tables.json", t, calls)  # t["meta"]["run"] 도 넣음
    st["stage3"] = t
    return n


def run_first(sess, job, use_llm=False):
    """첫 분석(spec_작업 ② §9) — 새 작업을 처음 열 때 2단계(헤딩 그래프) → 3단계(표 구조)를 한 작업으로, **스크립트만**(use_llm 은 받기만 한다 — LLM 은 사람이 단추로).
    1단계는 2단계가 스스로 뽑는다. 이미 결과가 있는 단계는 건너뛴다(유료 LLM 결과를 덮지 않게). 기록은 단계마다 여기서 → 마지막으로 저장한 실행 번호(둘 다 건너뛰면 None)."""
    st = state(sess)
    n = None
    for stage, key, run, name in ((2, "stage2", run_stage2, "헤딩 그래프"), (3, "stage3", run_stage3, "표 구조")):
        if st.get(key) is not None:
            job.step(f"{name} — 건너뜀", "ok", f"이미 {stage}단계 결과가 있습니다")
            continue
        n = run(sess, job, False)
        works.log(sess.id, "headings", stage=stage, llm=False, status="done", rev=job.rev, first=True,
                  **({"n": n} if st.get("lastSaved") is not False else {"saved": False}))
    return n


def _runner(stage):
    """단계 → 실행 함수(부를 때 찾는다 — 시험이 run_stage1·run_stage2 를 monkeypatch 한다)."""
    return run_stage1 if stage == 1 else run_stage2 if stage == 2 else run_stage3


_start_lock = threading.Lock()  # 「돌고 있나」 확인과 자리 잡기 사이에 다른 요청이 못 끼게(FastAPI 스레드 풀)


def start(sess, stage, use_llm, first=False, chain=None, runner=None):
    """first = 첫 분석(run_first — 2단계 → 3단계 스크립트, 한 작업 · spec_작업 ② §9): stage 는 3 으로 적고 use_llm 은 안 쓴다.
    chain · runner = 이어 돌리기(chain 이름 · runner(sess, job) — 단계 실행과 기록은 runner 가 한다: app/analysis_llm.py 「LLM 검증·보완」). 같은 작업 자리를 쓴다(겹치면 Busy)."""
    st = state(sess)
    with _start_lock:
        job0 = st.get("job")
        if job0 is not None and job0.status == "running":
            raise Busy("헤딩 추출이 이미 돌고 있습니다")
        job = Job(stage, use_llm, sess.rev)
        job.first = bool(first)
        job.chain = chain if runner is not None else None
        st["job"] = job

    def run():
        try:
            job.run = (runner(sess, job) if runner is not None else (run_first if first else _runner(stage))(sess, job, use_llm))  # run_first 도 부를 때 찾는다(시험이 바꿔 낀다)
            job.status = "done"
            if first or runner is not None:  # 첫 분석 · 이어 돌리기의 기록은 단계마다 그 실행이 적었다
                return
            saved = st.get("lastSaved")  # 저장이 실제로 한 일 — 안 쓴 실행(밀려난 세션·지운 작업·디스크 오류)의 번호는 다음 실행이 쓰므로 안 남김
            works.log(sess.id, "headings", stage=stage, llm=use_llm, status="done", rev=job.rev,
                      **({"n": job.run} if saved is not False else {"saved": False}))
        except Exception as e:  # 단계 실패 — 화면에 보이고 기록에 남김
            job.status, job.error = "failed", (str(e) if getattr(e, "plain", False) else f"{type(e).__name__}: {e}")  # plain = 사람이 읽는 까닭(analysis_llm.Stop)
            job.step("오류", "failed", traceback.format_exc()[-800:])
            works.log(sess.id, "headings", stage=job.stage, llm=use_llm, status="failed", error=job.error[:300], **({"chain": job.chain} if job.chain else {}))
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
    form = F.for_session(sess)  # 이 문서에 맞은 양식 정보(spec ② §12) — 실행이 쓴 판은 단계마다 meta.guides.form(sha1)
    temp = temp_label(sess)  # TEMP 라벨(§15) — (1단계 실행, 지정 판)마다 한 번 셈해 둔 것
    out = {"job": job.view() if job else None, "rev": sess.rev, "runs": st["runs"][-20:], "stage1": None, "stage2": None, "stage3": None,
           "rules": rules_view(st),  # LLM 규칙 보강을 마지막으로 돌린 실행(§7 「진행 줄」) — 실행 목록 전체에서(위 runs 는 끝 20개뿐)
           "persistError": st.get("persistError"), "form": {k: form[k] for k in ("key", "name", "how", "sha1")} if form else None,
           "temp": {"key": f"{(s1.get('meta') or {}).get('run')}|{(s1.get('meta') or {}).get('at')}|{temp['hintsVersion']}", "counts": temp["counts"],
                    "text": TP.summary_text(temp)} if temp and s1 else None}
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
                         "tempStale": bool(temp) and not TP.same_items(s2.get("temp"), temp),  # 이 결과가 뺀 TEMP ≠ 지금 TEMP(이 기능 전의 결과 포함) — 다시 셈하면 맞춰진다
                         "templates": [{k: t.get(k) for k in ("name", "kind", "root", "note", "slots")} for t in s2["templates"]],
                         "heterogeneous": s2["heterogeneous"][:50], "repeats": len(s2["repeats"]),
                         "adjust": sum(1 for a in s2["adjustments"] if a["decision"] == "adjust")}
    if s3:  # 표 목록은 요약만(칸은 GET /headings/tables)
        m3, m2 = s3.get("meta") or {}, (s2 or {}).get("meta") or {}
        # 표 소속(헤딩·구분 라벨)이 지금 2단계와 다른 실행의 것 — 실행 번호를 남기기 전(옛) 결과는 2단계가 더 뒤에 만들어졌으면
        owner_stale = bool(s2) and (m3["stage2Run"] != m2.get("run") if "stage2Run" in m3 else (m2.get("at") or 0) > (m3.get("at") or 0))
        out["stage3"] = {"meta": s3.get("meta"), "counts": s3["counts"], "llm": s3["llm"], "stale": s3.get("meta", {}).get("rev") != sess.rev,
                         "ownerStale": owner_stale,
                         "tempStale": bool(temp) and not TP.same_tables(s3, temp), "tempTables": len(s3.get("tempTables") or []),  # §15 — 이 결과가 뺀 TEMP 표 ≠ 지금 TEMP 표
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


# ---- 라벨 지정(spec ② §13) — 문서마다 작업 폴더 headings/hints.json, 반영은 LLM 호출 없는 새 실행 --------------------------

class Stale(Exception):
    """지금 2단계 결과로는 다시 셈할 수 없음(문서가 추출 뒤 바뀜 · 그 1단계 결과가 없음) — 지정은 저장돼 있고 다음 2단계 실행이 쓴다."""


def hints(sess):
    """이 문서의 지정 {"version", "bases": [사용자가 더한 구분 기준], "labels": {괄호 글 꼴: {role: label|subtitle, basis, by, at, text}},
    "temp": {"version", "set": {항목 id: {state: on|off, why, at, text}}}(TEMP 지정·해제 — §15, 판 번호는 라벨 지정과 따로)}."""
    st = state(sess)
    if st.get("hints") is None:  # 작업이 없는 세션 대역(닫힌 작업 미리보기 heading_compare 의 SimpleNamespace)은 빈 지정
        st["hints"] = _read_hints(_dir(sess) if getattr(sess, "id", None) else None)
    return st["hints"]


def _read_hints(d):
    """작업 폴더의 hints.json → 고른 꼴(없거나 못 읽으면 빈 지정)."""
    h = works._read_json(d / "hints.json") if d is not None else None
    h = h if isinstance(h, dict) else {}
    h = {**h, "version": h.get("version") or 0, "labels": h["labels"] if isinstance(h.get("labels"), dict) else {}}
    h["bases"] = [b for b in h.get("bases") or [] if isinstance(b, str)]
    h["temp"] = TP.clean_hints(h.get("temp"))
    return h


def _save_hints(sess, h):
    """지정을 작업 폴더에 쓰고(살아 있는 세션·있는 작업일 때만) 세션에 둔다."""
    d = _dir(sess)
    if d is not None and _live(sess):
        with works._lock(sess.id):
            if (d.parent / "work.json").is_file():
                works._write_json(d / "hints.json", h)
    state(sess)["hints"] = h


# ---- TEMP 라벨(spec ② §15) — 표 안 작성요령·쓸 자리: 2·3단계가 시작할 때 다시 셈하고, 화면·API 는 (1단계 실행, 지정 판)마다 한 번 셈해 둔 것을 쓴다 ------

def temp_label(sess):
    """지금 TEMP 라벨(heading_temp.label 결과) | None(1단계 결과가 없음)."""
    st = state(sess)
    s1 = st.get("stage1")
    if not s1:
        return None
    h = hints(sess)["temp"]
    m = s1.get("meta") or {}
    key = (m.get("run"), m.get("at"), h["version"])
    c = st.get("tempCache")
    if c is None or c[0] != key:
        c = st["tempCache"] = (key, TP.label(s1, h))
    return c[1]


def set_temp(sess, iid, to, why="guide"):
    """TEMP 지정 하나를 저장한다 → hints. to = "on"(그 표·칸·문단을 TEMP 로) · "off"(TEMP 아님 — 지금 TEMP 항목을 해제) · "auto"(지정 지움 — 규칙대로).
    on·off 는 그 블록이 지금 1단계 결과에 웹 블록으로 있어야 하고, off 는 지금 TEMP 항목(또는 이미 해제해 둔 것)이어야 한다. 잘못된 값은 ValueError."""
    unit, raw = TP.split_id(iid)
    if unit is None:
        raise ValueError("id 는 tbl:<표 id> · cell:<칸 id> · para:<문단 id>")
    if to not in ("on", "off", "auto"):
        raise ValueError('state 는 "on" · "off" · "auto"')
    if why not in TP.WHYS:
        raise ValueError('why 는 "guide"(작성요령) · "todo"(쓸 자리)')
    h = copy.deepcopy(hints(sess))
    if to == "auto":
        h["temp"]["set"].pop(iid, None)
    else:
        s1 = state(sess).get("stage1")
        text = TP.block_text(s1, unit, raw) if s1 else None
        if text is None:
            raise ValueError("그 표·칸·문단이 지금 추출 결과에 없습니다(웹 블록이 있는 것만 지정할 수 있습니다) — 1단계를 다시 추출한 뒤 지정하세요")
        if to == "off" and iid not in {it["id"] for it in (temp_label(sess) or {}).get("items") or ()} and (h["temp"]["set"].get(iid) or {}).get("state") != "off":
            # 해제는 항목 단위 — 더 큰 항목(표)이 덮은 칸·문단의 해제는 효과가 없어 받지 않는다
            raise ValueError("TEMP 항목이 아닙니다 — 해제는 항목 단위입니다(표 항목 안의 칸·문단만 따로 풀 수는 없습니다: 표를 해제한 뒤 칸·문단을 TEMP 로 지정하세요)")
        h["temp"]["set"][iid] = {"state": to, "why": why, "at": round(time.time(), 3), "text": text}
    h["temp"]["version"] = int(h["temp"].get("version") or 0) + 1
    _save_hints(sess, h)
    works.log(sess.id, "heading_temp", item=iid, state=to, why=why if to == "on" else None)
    return h


def temp_view(sess):
    """화면용 — 지금 TEMP 항목·수·지정과, 2·3단계 결과가 이 TEMP 로 만든 것인지(`tempStale`)."""
    st = state(sess)
    s1, s2, s3 = st.get("stage1"), st.get("stage2"), st.get("stage3")
    h = hints(sess)["temp"]
    t = temp_label(sess)
    out = {"key": None, "run": None, "rev": sess.rev, "stale": False, "version": h["version"], "hints": h["set"], "counts": {}, "items": [],
           "paras": {}, "tables": {},  # 문단 id → 그것을 덮은 항목 id · TEMP 표 id(안쪽 표 포함) → 항목 id — 화면의 여백 표시·표 표지·오른쪽 단추 메뉴
           "off": [{"id": i, "text": v["text"]} for i, v in h["set"].items() if v["state"] == "off"], "gone": [], "stage2": None, "stage3": None}
    if t is None:
        return out
    m = s1.get("meta") or {}
    out.update(key=f"{m.get('run')}|{m.get('at')}|{h['version']}", run=m.get("run"), stale=m.get("rev") != sess.rev or s1.get("version") != E.VERSION,
               counts=t["counts"], items=t["items"], paras=t["paras"], tables=t["tables"],
               off=[{"id": i, "text": h["set"][i]["text"]} for i in t["off"]], gone=t["gone"])
    if s2:
        out["stage2"] = {"run": (s2.get("meta") or {}).get("run"), "tempStale": not TP.same_items(s2.get("temp"), t)}
    if s3:
        out["stage3"] = {"run": (s3.get("meta") or {}).get("run"), "tempStale": not TP.same_tables(s3, t)}
    return out


def set_hint(sess, shape, role, basis="", text=""):
    """괄호 글 꼴 하나의 지정을 저장한다 → hints. role = "label"(구분 라벨 — basis 필요) · "subtitle"(괄호 소제목) · "auto"(지정 지움 — 자동 판정으로).
    basis 가 구분 기준 목록에 없는 새 이름이면 목록(bases)에 더한다(지정을 지워도 남는다). 잘못된 값은 ValueError."""
    if not isinstance(shape, str) or not shape.strip() or len(shape) > 80 or HG.label_shape(shape) != shape:
        raise ValueError("shape 는 괄호 글 꼴(숫자를 N 으로 적은 글)이어야 합니다")
    if role not in ("label", "subtitle", "auto"):
        raise ValueError('role 은 "label" · "subtitle" · "auto"')
    h = copy.deepcopy(hints(sess))
    if role == "auto":
        h["labels"].pop(shape, None)
    else:
        b = ""
        if role == "label":
            raw = str(basis or "").strip()
            b = HG.norm_basis(raw, HG.bases_of(h))
            if not b:  # 새 구분 기준 이름
                if not raw or len(raw) > 12 or HG.BASIS_BAD.search(raw):
                    raise ValueError("구분 기준 이름은 12자 안, 공백과 [ ] › | : - · / , + … 없이 적습니다" if raw else "구분 라벨로 지정하려면 구분 기준(단계·차년도·기관 …)이 필요합니다")
                h["bases"].append(raw)
                b = raw
        h["labels"][shape] = {"role": role, "basis": b, "by": "user", "at": round(time.time(), 3), "text": str(text or "")[:80]}
    h["version"] = int(h.get("version") or 0) + 1
    _save_hints(sess, h)
    works.log(sess.id, "heading_label", shape=shape, role=role, basis=h["labels"].get(shape, {}).get("basis", ""))
    return h


def relabel(sess, what="라벨 지정"):
    """지금 2단계 결과를 지정(구분 라벨 지정 §13 · TEMP 지정 §15 — what = 단계 줄에 적을 이름)으로 다시 셈해 **새 실행**으로 저장 → 실행 번호(2단계 결과가 없으면 None). LLM 호출 없음: LLM 실행은 앞 실행의 A 답·B 변경·C/D 판정을
    되풀이하고(HG.replay_of), 스크립트 실행은 그대로 다시 — 어느 쪽이든 부모 초안부터 다시라 새로 추출한 것과 같은 길이다.
    문서가 추출 뒤 바뀌었거나 그 1단계 결과가 없으면 Stale(개요 편집 오버레이는 2단계 실행에 매여 있어, 문서가 그대로일 때만 새 실행으로 바꿔도 잃는 것이 없다)."""
    st = state(sess)
    g = st.get("stage2")
    if g is None:
        return None
    meta0 = g.get("meta") or {}
    if meta0.get("rev") != sess.rev:
        raise Stale("문서가 추출 뒤 바뀌었습니다 — 2단계를 다시 돌리면 지정이 반영됩니다")
    s1 = st.get("stage1")
    if s1 is None or (s1.get("meta") or {}).get("run") != meta0.get("stage1Run"):  # 그 결과를 만든 1단계(서식 라벨·문단)로 다시 셈한다
        d = _dir(sess)
        s1 = _read(d / str(meta0.get("stage1Run")) / "stage1.json") if d is not None and isinstance(meta0.get("stage1Run"), int) else None
    if not isinstance(s1, dict) or s1.get("version") != E.VERSION:
        raise Stale("이 결과를 만든 1단계 결과가 없습니다 — 2단계를 다시 돌리면 지정이 반영됩니다")
    with _start_lock:
        job0 = st.get("job")
        if job0 is not None and job0.status == "running":
            raise Busy("헤딩 추출이 돌고 있습니다 — 끝난 뒤 다시 해 주세요")
        job = Job(2, False, sess.rev)
        st["job"] = job
    try:
        job.step(f"{what} 반영")
        h = copy.deepcopy(hints(sess))
        # 되풀이할 LLM 판정은 늘 **처음 추출한 실행**(base)의 것 — 지정을 거듭 바꿔도 (처음 실행 + 지금 지정)이라 차례에 안 매이고, 지정을 지우면 처음 결과로 돌아온다
        base_n = meta0.get("base") or meta0.get("run")
        base = g
        if meta0.get("base") is not None:
            d = _dir(sess)
            base = st.setdefault("bases2", {}).get(base_n) or (_read(d / str(base_n) / "graph.json") if d is not None else None) or g
        else:
            st.setdefault("bases2", {})[base_n] = g  # 저장 끔(메모리만)이어도 다음 반영이 처음 실행을 찾게
        replay = HG.replay_of(base)
        temp0 = TP.label(s1, h["temp"])  # TEMP 라벨도 지금 지정으로(§15) — TEMP 문단은 후보에서 빠지고, 풀린 문단은 후보로 돌아온다
        g2 = HG.build(s1, use_llm=False, doc_name=sess.name, hints=h, replay=replay, temp=temp0)
        g2.pop("_calls", None)
        g2["guides"] = g.get("guides") or {}
        g2["meta"] = {**{k: meta0.get(k) for k in ("rev", "stage1Run", "sha256", "guides")}, "at": time.time(), "derivedFrom": meta0.get("run"), "base": base_n,
                      "what": what}  # 무엇을 반영한 실행인가(「라벨 지정」·「TEMP 지정」) — 2단계 카드의 글
        c = g2["counts"]
        meta = {"stage": 2, "stage_key": "stage2", "rev": meta0.get("rev"), "llm": bool(replay), "at": time.time(), "stage1Run": meta0.get("stage1Run"),
                "summary": c, "costUsd": 0, "guides": None, "derivedFrom": meta0.get("run"), "base": base_n, "relabel": True}
        job.run = _save_run(sess, st, meta, "graph.json", g2, [])
        st["stage2"] = g2
        job.step(f"{what} 반영", "ok", f"실행 {base_n} 을 다시 셈 — 구분 라벨 {c['labels']} · 괄호 소제목 {c['subtitles']} · 템플릿 {c['templates']} · 인스턴스 {c['instances']}"
                 + (f" · 앞 실행의 LLM 판정을 이어 씀(조정 {g2['llm'].get('carried', 0)}쌍)" if replay else " · 스크립트 판정") + f" · {TP.summary_text(temp0)}")
        job.status = "done"
        works.log(sess.id, "headings", stage=2, llm=bool(replay), status="done", rev=job.rev, relabel=True, derivedFrom=meta0.get("run"),
                  **({"n": job.run} if st.get("lastSaved") is not False else {"saved": False}))
        return job.run
    except Exception as e:
        job.status, job.error = "failed", f"{type(e).__name__}: {e}"
        job.step("오류", "failed", traceback.format_exc()[-800:])
        raise
    finally:
        job.ended = time.time()


def div_labels(sess):
    """화면용 — 구분 기준 목록 · 지정 · 지금 2단계 결과의 괄호 줄을 꼴마다 {shape, text, count, role, basis, key, tplNos, para, hint}."""
    h = hints(sess)
    g = state(sess).get("stage2")
    items = {}
    for n in (g or {}).get("nodes") or []:
        if n.get("kind") != "label":
            continue
        shape = HG.label_shape(n.get("letter"))
        it = items.setdefault(shape, {"shape": shape, "text": (n.get("letter") or "").strip(), "count": 0, "roles": {}, "tplNos": [], "para": n.get("para"),
                                      "basis": "", "key": None})
        it["count"] += 1
        it["roles"][n.get("role")] = it["roles"].get(n.get("role"), 0) + 1
        if n.get("role") in HG.ROOTED and it["key"] is None:
            it.update(key=n.get("key"), basis=n.get("basis") or "")
        if n.get("tplNo") and n.get("level") == 1 and n["tplNo"] not in it["tplNos"]:
            it["tplNos"].append(n["tplNo"])
    out = []
    for it in items.values():
        roles = it.pop("roles")
        it["role"] = max(roles, key=lambda r: (roles[r], r in HG.ROOTED)) if roles else None
        it["hint"] = h["labels"].get(it["shape"])
        out.append(it)
    return {"bases": HG.bases_of(h), "version": h.get("version") or 0, "hints": h["labels"], "items": out,
            "run": ((g or {}).get("meta") or {}).get("run"), "stale": bool(g) and (g.get("meta") or {}).get("rev") != sess.rev,
            "bracketRule": (g or {}).get("bracketRule")}
