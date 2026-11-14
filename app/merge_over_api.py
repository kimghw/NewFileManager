"""넘친 개요 레벨 API(spec_병합 ② §5-5 8 — 2026-11-13 사용자 「덮은 템플릿으로 사용할지 템플릿을 수정할지, 다른 템플릿을 선택할 수 있게」). 목적 문서(이관의 연차보고서 · 취합의 취합본) id 기준.
server.py 가 include 한다. 규칙·저장·다시 맞추기의 엔진은 `app/merge_over.py`, 줄에 입히는 일은 `app/merge_convert.py`.

- `GET  /api/docs/{id}/merge-over` → {version, cases{사례 열쇠: 선택}, templates[본보기·「다른 템플릿」 후보], records{lines, cases{열쇠: 줄 수}}}(문서는 안 바뀜 — records = 다시 맞출 수 있는 넣은 줄).
- `PUT  /api/docs/{id}/merge-over` `{key, mode: cover|edit|template, levels?, template?}` 또는 `{key, reset: true}` → {version, key, case}. 400 잘못된 값 · 409 헤딩 2단계 결과 없음.
  저장하면 그 문서의 **세워 둔 넣기 계획을 버린다**(이관 · 취합의 기관 문서마다 · 끌어 넣기 — 화면이 다시 계획한다).
- `POST /api/docs/{id}/merge-over/refit` `{key?}` → 넣은 뒤 다시 맞추기: 넣은 넘친 줄의 기록과 지금 선택만으로 접두·모양을 다시 입힌다 — 편집 하나(`server._transact`: 실행 취소 1 · 문서 전체 표준 검사 ·
  걸리면 전부 복원·422 · 기록 `overRefit`) → {lines, kept{까닭: n}, labels, …편집 상태} | {nothing: true, …}(바뀔 줄이 없으면 편집을 열지 않는다).
  바꾼 뒤 기록의 지금 레터를 고쳐 적고(이관 merge.json `applied[항목].over` · 취합 gather.json `parts[].applied[열쇠].convert.over`), 취합은 넣은 결과 지문(`fp`)도 다시 적는다(다음 판정이 「같음」 으로 보게).
넣기 계획 끝점(merge_api · merge_gather_api)이 쓰는 것: `specs(doc_id, to_graph)` = (저장된 선택, merge_convert.plan 의 over) · `over_view(doc_id, cases, to_graph, to_doc, store)` = 계획 응답의 over · `forget(doc_id)`."""
from fastapi import APIRouter, Body, HTTPException

from app import heading_runs as HR
from app import merge_over as MO
from app import works

router = APIRouter()
KEY_MAX = 400
NO_GRAPH = "헤딩 2단계 결과가 없어 템플릿을 알 수 없습니다 — 먼저 헤딩을 분석하세요"


def _graph(s):
    return HR.graph(s) if s.fmt == "hwpx" else None


def records(doc_id):
    """넣은 넘친 줄의 기록 [(자리, 기록 {key, to, lines})] — 자리 = ("fill", 목적 항목) | ("gather", 기관 문서, 작성 내용 열쇠)."""
    from app import merge_api
    from app import merge_gather_api as GA
    out = [(("fill", k), v["over"]) for k, v in (merge_api._store(doc_id).get("applied") or {}).items() if isinstance(v, dict) and isinstance(v.get("over"), dict)]
    for pid, rec in (GA._store(doc_id).get("parts") or {}).items():
        for k, v in (rec.get("applied") or {}).items():
            ov = (v.get("convert") or {}).get("over") if isinstance(v, dict) else None
            if isinstance(ov, dict):
                out.append((("gather", pid, k), ov))
    return out


def specs(doc_id, to_graph):
    """(저장된 선택 {version, cases}, merge_convert.plan(over=) 에 넘길 지정) — 넣기 계획이 그때의 것을 실어 두고 반영이 그대로 쓴다."""
    store = MO.load(doc_id)
    return store, MO.resolve(store["cases"], to_graph or {})


def over_view(doc_id, cases, to_graph, to_doc, store=None):
    """넣기 계획 응답의 over{version, cases[], templates[], records} — 이번 계획의 사례(merge_over.collect) + 넣은 줄의 기록에서 읽은 사례."""
    return MO.plan_view(cases, [r for _, r in records(doc_id)], store or MO.load(doc_id), to_graph or {}, to_doc)


def forget(doc_id):
    """세워 둔 넣기 계획을 버린다(선택이 바뀜 · 다시 맞춤) — 이관 · 취합의 기관 문서마다 · 끌어 넣기."""
    from app import merge_api
    from app import merge_gather_api as GA
    merge_api._PLANS.pop(doc_id, None)
    with GA._LOCK:
        for k in [k for k in GA._PLANS if k[0] == doc_id]:
            del GA._PLANS[k]
        GA._DROPS.pop(doc_id, None)


@router.get("/api/docs/{doc_id}/merge-over")
def over_get(doc_id: str):
    from app import server   # server 가 이 모듈을 include 한다(순환 import 피함)
    s = server._sess(doc_id)
    with s.lock:
        g = _graph(s)
        store = MO.load(doc_id)
        left = MO.alive(s.doc, [r for _, r in records(doc_id)]) if s.fmt == "hwpx" else {}
        return {"version": store["version"], "cases": store["cases"], "templates": MO.templates(g, s.doc) if g else [], "records": {"lines": sum(left.values()), "cases": left}}


@router.put("/api/docs/{doc_id}/merge-over")
def over_put(doc_id: str, body: dict = Body(...)):
    from app import server
    key = body.get("key")
    if not isinstance(key, str) or not key or len(key) > KEY_MAX:
        raise HTTPException(400, "key(사례 열쇠)가 있어야 합니다")
    s = server._sess(doc_id)
    with s.lock:
        g = _graph(s)
        if g is None:
            raise HTTPException(409, NO_GRAPH)
        choice = None
        if not body.get("reset"):
            try:
                choice = MO.validate(body, MO.templates(g, s.doc))
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        data = MO.put(doc_id, key, choice)
        rev = s.rev
    forget(doc_id)
    works.log(doc_id, "mergeOver", rev=rev, key=key, mode=(choice or {}).get("mode") or "reset")
    return {"version": data["version"], "key": key, "case": data["cases"].get(key)}


@router.post("/api/docs/{doc_id}/merge-over/refit")
def over_refit(doc_id: str, body: dict = Body(default={})):
    from app import merge_api, server
    from app import merge_gather as MG
    from app import merge_gather_api as GA
    only = body.get("key")
    if only is not None and not isinstance(only, str):
        raise HTTPException(400, "key 는 사례 열쇠(글)여야 합니다")
    s = server._sess(doc_id)
    with s.lock:
        g = _graph(s)
        if g is None:
            raise HTTPException(409, NO_GRAPH)
        recs = records(doc_id)
        sp = MO.resolve(MO.load(doc_id)["cases"], g)
        pre = MO.refit(s.doc, [r for _, r in recs], sp, only=only, dry=True)   # 바뀔 줄이 없으면 편집(실행 취소 단위)을 열지 않는다
        labels = lambda kept: {k: MO.WHY.get(k, k) for k in kept}  # noqa: E731
        if not pre["lines"]:
            return {"nothing": True, "lines": 0, "kept": pre["kept"], "labels": labels(pre["kept"]), **s.state()}
        done = {}

        def run():
            done.update(MO.refit(s.doc, [r for _, r in recs], sp, only=only))
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None, "log": {"key": only, "lines": done["lines"], "kept": done["kept"]}}
        out, after = server._transact(s, run, "overRefit", req={"key": only}, check=server._full_check)
        if after is None:
            return out
        new = dict(zip([where for where, _ in recs], done["records"]))
        saved, dirty = merge_api._store(doc_id), False
        for where, rec in new.items():
            if where[0] == "fill" and isinstance((saved.get("applied") or {}).get(where[1]), dict):
                saved["applied"][where[1]]["over"], dirty = rec, True
        if dirty:
            merge_api._store(doc_id, saved)
        gather = {where[1:]: rec for where, rec in new.items() if where[0] == "gather"}
        if gather:
            idx = {b["id"]: b for b in after}

            def fn(G):
                for (pid, k), rec in gather.items():
                    v = ((G["parts"].get(pid) or {}).get("applied") or {}).get(k)
                    if not isinstance(v, dict):
                        continue
                    v.setdefault("convert", {})["over"] = rec
                    if v.get("kind") in MG.BODY:   # 넣은 결과의 지문 — 레터가 바뀌었다(다음 판정이 넣은 기록을 이것으로 확인한다)
                        v["fp"] = MG._fp_blocks([idx[i] for i in v.get("ids") or () if i in idx])
            GA._change(doc_id, fn, bump=False)
        forget(doc_id)   # 문서 차례가 바뀌었다 — 세워 둔 계획은 어차피 낡는다
        return {"lines": done["lines"], "kept": done["kept"], "labels": labels(done["kept"]), **s.state()}
