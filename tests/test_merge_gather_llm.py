"""취합 LLM 순회 검토(spec_취합 ② §4-3) — app/merge_gather_llm.py · 지침 app/merge_guides_default/gather.md. LLM 은 부르지 않는다(가짜 ask).
자료는 손으로 만든 작은 사전(취합본·기준본·기관 문서·작성 내용) — 엔진(app/merge_gather.py)에 기대지 않는다."""
import copy
import json

from app import job_prompts as J
from app import merge_gather_llm as L
from app import merge_guides as G
from app import merge_llm


def _p(i, text, **kw):
    return {"id": i, "type": "paragraph", "text": text, "lines": [], "captionOf": None, **kw}


def _tbl(i, grid):
    return {"id": i, "type": "table", "nRows": len(grid), "nCols": len(grid[0]),
            "cells": [{"id": f"{i}.{r}.{c}", "row": r, "col": c, "rowSpan": 1, "colSpan": 1, "text": t, "blocks": []} for r, row in enumerate(grid) for c, t in enumerate(row)]}


def _node(i, para, role, letter, level, tpl="body:main", parent="root"):
    return {"id": f"n{i}", "para": para, "n": i, "flow": "body", "area": "body", "role": role, "letter": letter, "text": "", "template": tpl, "level": level, "parent": parent}


TEMPLATES = [{"key": "body:main", "kind": "main"}, {"key": "body:sub", "kind": "branch"}]
COST = [["구분", "1차년도", "2차년도", "합계"], ["인텍", "", "", ""], ["가나대", "", "", ""]]
ITEMS = [["품목", "수량", "금액(천원)"], ["", "", ""]]


def _to():
    """취합본 — 표지 · 1장(기관 자리 둘) · 2장(정해진 칸 표 · 이어 넣는 표) · 3장. 장마다 새 쪽. 가나대 자리(a5)에는 사람이 먼저 쓴 글이 있다(겹침)."""
    blocks = [_p("a0", "연구개발계획서", page=None),
              _p("a1", "1. 연구개발 목표 및 내용", pageStart=True), _p("a2", "[주관연구개발기관: 인텍]"), _p("a3", "ㅇ"), _p("a4", "[공동연구개발기관: 가나대]"), _p("a5", "ㅇ 사람이 먼저 쓴 글"),
              _p("a6", "2. 연구개발비 사용계획", pageStart=True), _p("a7", "< 기관별 연구개발비 > (단위: 천원)"), _tbl("t1", COST), _tbl("t2", ITEMS),
              _p("a8", "3. 기타 사항", pageStart=True), _p("a9", "ㅇ"), _p("a10", "※ 해당 사항이 없으면 「해당 없음」 으로 기재")]
    nodes = [_node(1, "a1", "heading", "1.", 1), _node(2, "a2", "label", "", 1, "body:sub", "n1"), _node(4, "a4", "label", "", 1, "body:sub", "n1"),
             _node(6, "a6", "heading", "2.", 1), _node(8, "a8", "heading", "3.", 1)]
    return {"id": "to1", "name": "사업계획서.hwpx", "rev": 3, "blocks": blocks, "graph": {"nodes": nodes, "templates": TEMPLATES}, "tables": None}


def _frame():
    """기준본 자리 정보 — 취합본을 나눠 줄 때의 블록(a5 는 그때 자리표시 줄)."""
    org = lambda name: {"kind": "org", "org": name, "year": None, "stage": None}   # noqa: E731
    common = {"kind": "common", "org": None, "year": None, "stage": None}

    def fb(i, bid, text, cls, scope=common, **kw):
        return {"i": i, "id": bid, "kind": "tbl" if cls == "table" else "p", "key": text, "text": text, "cls": cls, "path": [], "scope": scope, **kw}

    def cells(tid, grid, cls):
        return [{"r": r, "c": c, "rs": 1, "cs": 1, "id": f"{tid}.{r}.{c}", "cls": cls(r, c), "text": t} for r, row in enumerate(grid) for c, t in enumerate(row)]
    cost = {"rows": 3, "cols": 4, "list": False, "cells": cells("t1", COST, lambda r, c: "head" if r == 0 or c == 0 else "calc" if c == 3 else "input")}
    items = {"rows": 2, "cols": 3, "list": True, "cells": cells("t2", ITEMS, lambda r, c: "head" if r == 0 else "input")}
    return {"frameId": "f1", "values": {}, "orgs": [{"key": "인텍", "name": "인텍", "role": "주관"}, {"key": "가나대", "name": "가나대", "role": "공동1"}],
            "blocks": [fb(0, "a0", "연구개발계획서", "fixed"), fb(1, "a1", "1. 연구개발 목표 및 내용", "title"), fb(2, "a2", "[주관연구개발기관: 인텍]", "label", org("인텍")),
                       fb(3, "a3", "ㅇ", "guide", org("인텍")), fb(4, "a4", "[공동연구개발기관: 가나대]", "label", org("가나대")), fb(5, "a5", "ㅇ", "guide", org("가나대")),
                       fb(6, "a6", "2. 연구개발비 사용계획", "title"), fb(7, "a7", "< 기관별 연구개발비 > (단위: 천원)", "fixed"), fb(8, "t1", "구분|1차년도|2차년도|합계", "table", table=cost),
                       fb(9, "t2", "품목|수량|금액(천원)", "table", table=items), fb(10, "a8", "3. 기타 사항", "title"), fb(11, "a9", "ㅇ", "guide"),
                       fb(12, "a10", "※ 해당 사항이 없으면 「해당 없음」 으로 기재", "guide")]}


def _part(long=""):
    """기관 문서(다시 읽어 블록 id 가 다르다) — 작성 내용이 든 블록만."""
    table = _tbl("bt9", [["시험 항목", "기준"], ["내압", "1.5배"]])
    blocks = [_p("b3", "ㅇ 선박 운항 데이터 수집 체계를 구축한다" + long), _p("b3x", "- 1차년도: 센서 12종 설치"), _p("b5", "ㅇ 가나대는 해석 모델을 개발한다"),
              _tbl("bt1", [COST[0], ["인텍", "15,000", "20,000", "35,000"], COST[2]]), _tbl("bt2", [ITEMS[0], ["", "", ""], ["센서", "12", "36,000"]]),
              _p("b9", "ㅇ 해당 없음"), _p("b9a", "□ 시험 계획"), table, _p("b9c", "<표 1> 시험 항목", captionOf="bt9"), {"id": "bimg", "type": "image", "media": None, "widthMm": 80.0, "heightMm": 50.0}]
    return {"id": "pt1", "name": "인텍_작성본.hwpx", "rev": 1, "blocks": blocks, "graph": {"nodes": [_node(1, "b9a", "heading", "□", 2)], "templates": TEMPLATES}, "tables": None}


def _hunk(key, kind, status, org, base, frm, to, **kw):
    scope = {"kind": "org" if org else "common", "org": org, "orgName": org, "year": None, "stage": None}
    return {"key": key, "kind": kind, "status": status, "detail": "", "scope": scope, "path": ["1. 연구개발 목표 및 내용"], "base": {"prev": None, "next": None, "ids": [], "table": None, **base},
            "from": {"ids": [], "table": None, "cells": [], "rows": [], **frm}, "to": to, "text": "", "counts": {}, "unique": "앞뒤 경계가 구간에 하나씩", "decision": None, **kw}


def _items():
    return [
        _hunk("K_FILL", "filled", "ready", "인텍", {"prev": "a2", "next": "a4", "ids": ["a3"]}, {"ids": ["b3", "b3x"]}, {"prev": "a2", "next": "a4"}),
        _hunk("K_OTHER", "filled", "otherOrg", "가나대", {"prev": "a4", "next": "a6", "ids": ["a5"]}, {"ids": ["b5"]}, {"prev": "a4", "next": "a6"}),
        _hunk("K_OVER", "filled", "overlap", "가나대", {"prev": "a4", "next": "a6", "ids": ["a5"]}, {"ids": ["b5"]}, {"prev": "a4", "next": "a6"}),
        _hunk("K_CELLS", "cells", "ready", "인텍", {"prev": "a7", "next": "t2", "table": "t1"},
              {"table": "bt1", "cells": [{"r": 1, "c": 1, "id": "bt1.1.1", "text": "15,000", "base": ""}, {"r": 1, "c": 2, "id": "bt1.1.2", "text": "20,000", "base": ""}]}, {"prev": "a7", "next": "t2"},
              path=["2. 연구개발비 사용계획"], counts={"cells": 2}),
        _hunk("K_ROWS", "rows", "ready", None, {"prev": "t1", "next": "a8", "table": "t2"}, {"table": "bt2", "rows": [{"r": 2, "cells": ["센서", "12", "36,000"]}]}, {"prev": "t1", "next": "a8"},
              path=["2. 연구개발비 사용계획"], counts={"rows": 1}),
        _hunk("K_USER", "filled", "ready", None, {"prev": "a8", "next": "a10", "ids": ["a9"]}, {"ids": ["b9"]}, {"prev": "a8", "next": "a10"}, path=["3. 기타 사항"],
              decision={"value": "skip", "source": "user"}),
        _hunk("K_ADD", "added", "ready", None, {"prev": "a9", "next": "a10"}, {"ids": ["b9a", "bt9", "b9c", "bimg"]}, {"prev": "a9", "next": "a10"}, path=["3. 기타 사항"],
              counts={"paragraphs": 1, "tables": 1, "pictures": 1}),
    ]


def _payload(job):
    return json.loads(job["content"].split("## 자료(JSON)\n", 1)[1])


def _fake(answer, seen=None, fail=(), extra=()):
    """가짜 llm.ask_all — 보낸 hunk 마다 answer(hunk) → (nature, verdict) | None(답 안 함). fail = 실패시킬 호출 차례 · extra = 모든 답에 덧붙일 줄(남의 id 등)."""
    def ask(jobs):
        if seen is not None:
            seen.extend(jobs)
        out = []
        for k, j in enumerate(jobs):
            if k in fail:
                out.append({"data": None, "backend": None, "error": "시간 초과 600s", "model": j["model"]})
                continue
            rows = [{"id": h["id"], "inputHash": h["inputHash"], "nature": a[0], "verdict": a[1], "reason": "시험"} for h in _payload(j)["hunks"] if (a := answer(h))]
            out.append({"data": {"reviews": [*rows, *extra], "summary": ""}, "backend": "fake", "model": j["model"], "error": None})
        return out
    return ask


def _job(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_JOBS", str(tmp_path))
    (tmp_path / "plan_merge.md").write_text("# 할 일 프롬프트 — 시험 취합\n\n<!-- 메모 -->\n\n- 겹치면 덮지 않는다\n", encoding="utf-8")
    return J.get("plan_merge")


def test_prompt_is_contract_guide_job_data_and_carries_the_whole_hunk(tmp_path, monkeypatch):
    job, jobs = _job(tmp_path, monkeypatch), []
    r = L.review(_items(), _frame(), _to(), _part(), job=job, ask=_fake(lambda h: ("내용", "유지"), jobs), orgs=["인텍"])
    assert len(jobs) == 3 and all(j["model"] == L.MODEL == merge_llm.MODEL == "claude-opus-5-5" and j["schema"] is L.SCHEMA for j in jobs)   # 장마다 한 호출 · Opus
    assert [j["what"] for j in jobs] == ["gather-llm-1", "gather-llm-2", "gather-llm-3"]
    text = jobs[0]["content"]
    order = [text.index(x) for x in ("당신은 여러 기관이", "## 판단 지침 — 취합 검토", "## 할 일 — 시험 취합", "## 자료(JSON)")]
    assert text.startswith(L.CONTRACT) and order == sorted(order) and "겹치면 덮지 않는다" in text and "성격 가리기" in text and "메모" not in text   # 계약 → 지침 → 할 일 → 자료
    assert r["job"] == J.brief(job) and r["guide"] == G.brief(G.get("gather")) and r["guide"]["name"] == "gather"
    assert [(u["title"].split(" ")[0], u["targets"], u["opinions"], bool(u["call"])) for u in r["units"]] == [("첫", 0, 0, False), ("1.", 1, 1, True), ("2.", 2, 0, True), ("3.", 1, 0, True)]
    assert all(u["prompt"] == j["content"] for u, j in zip([u for u in r["units"] if u["call"]], jobs)) and "prompt" not in r["units"][0]
    p1, p2, p3 = map(_payload, jobs)
    assert p1["doc"] == {"part": "인텍_작성본.hwpx", "orgs": [{"name": "인텍", "role": "주관"}, {"name": "가나대", "role": "공동1"}], "assigned": ["인텍"]}
    assert [h["id"] for h in p1["hunks"]] == ["K_FILL", "K_OVER"] and [h["review"] for h in p1["hunks"]] == [True, False]   # 넣지 않는 상태(otherOrg)는 안 보낸다 · overlap 은 의견만
    fill, over = p1["hunks"]
    assert fill["content"] == [{"p": "ㅇ 선박 운항 데이터 수집 체계를 구축한다"}, {"p": "- 1차년도: 센서 12종 설치"}] and "omitted" not in fill   # 바뀐 내용 전체
    assert fill["place"] == {"before": ["label", "[주관연구개발기관: 인텍]"], "after": ["label", "[공동연구개발기관: 가나대]"], "frame": [["guide", "ㅇ"]], "now": "same",
                             "unique": "앞뒤 경계가 구간에 하나씩", "level": {"level": 1, "role": "label", "text": "[주관연구개발기관: 인텍]"}}   # 자리 줄: 앞뒤 경계 · 기준본 · 취합본 · 근거
    assert (fill["kind"], fill["status"], fill["scope"], fill["path"]) == ("filled", "ready", {"kind": "org", "org": "인텍"}, ["1. 연구개발 목표 및 내용"])
    assert over["status"] == "overlap" and over["place"]["frame"] == [["guide", "ㅇ"]] and over["place"]["now"] == [["p", "ㅇ 사람이 먼저 쓴 글"]]   # 취합본의 그 자리 글
    cells, rows = p2["hunks"]
    assert cells["content"] == [{"r": 1, "c": 1, "text": "15,000", "was": "", "cls": "input", "row": "인텍", "col": "1차년도"},
                                {"r": 1, "c": 2, "text": "20,000", "was": "", "cls": "input", "row": "인텍", "col": "2차년도"}]
    assert cells["table"] == {"size": "3×4", "list": False, "merged": 0, "roles": {"head": 6, "input": 4, "calc": 2}, "heads": ["구분 | 1차년도 | 2차년도 | 합계"],
                              "title": "< 기관별 연구개발비 > (단위: 천원)"} and "frame" not in cells["place"]   # 표의 격자·칸 역할·계산 칸·이어 넣는 표인지
    assert rows["content"] == [{"r": 2, "cells": ["센서", "12", "36,000"]}] and rows["table"]["list"] is True and rows["table"]["heads"] == ["품목 | 수량 | 금액(천원)"]
    (add,) = p3["hunks"]   # 사람이 고른 것(K_USER)은 보내지 않는다
    assert add["content"] == [{"p": "□ 시험 계획", "letter": "□", "level": 2, "role": "heading"}, {"table": "2×2"}, {"row": "시험 항목 | 기준"}, {"row": "내압 | 1.5배"},
                              {"caption": "<표 1> 시험 항목"}, {"picture": "80×50mm"}]   # 문단의 레터·개요레벨 · 딸린 표·캡션·그림
    assert add["objects"] == {"paragraphs": 1, "tables": 1, "pictures": 1} and add["place"]["level"] == {"letter": "3.", "level": 1, "role": "heading", "text": "3. 기타 사항"}
    assert "K_USER" not in text + jobs[1]["content"] + jobs[2]["content"] and "K_OTHER" not in text
    assert r["counts"] == {"targets": 4, "opinions": 1, "user": 1} and r["left"] == 0 and r["held"] == [] and r["rejected"] == []
    assert {k: v["value"] for k, v in r["decisions"].items()} == {"K_FILL": "keep", "K_CELLS": "keep", "K_ROWS": "keep", "K_ADD": "keep"}


def test_answers_only_narrow_ready_hunks_and_never_touch_user_or_blocked_ones():
    items = _items()
    before = copy.deepcopy(items)
    said = {"K_FILL": ("안내", "제외"), "K_OVER": ("내용", "유지"), "K_CELLS": ("내용", "제외"), "K_ROWS": ("복합", "유지"), "K_ADD": ("자리 이상", "확인 필요")}
    extra = [{"id": "K_USER", "inputHash": "x", "nature": "내용", "verdict": "유지", "reason": "사람이 뺀 것을 넣자"}, {"id": "K_OTHER", "inputHash": "x", "nature": "내용", "verdict": "유지", "reason": "다른 기관 것"}]
    r = L.review(items, _frame(), _to(), _part(), ask=_fake(lambda h: said[h["id"]], extra=extra))
    assert items == before   # 받은 자료는 안 고친다
    d = r["decisions"]
    assert set(d) == {"K_FILL", "K_CELLS", "K_ROWS", "K_ADD"}   # 겹침(K_OVER) · 다른 기관(K_OTHER) · 사람이 고른 것(K_USER)은 결정이 되지 않는다
    assert d["K_FILL"] == {"value": "skip", "source": "llm", "nature": "안내", "reason": "시험", "inputHash": L.hashes(items, _frame(), _to(), _part())["K_FILL"]}
    assert (d["K_CELLS"]["value"], d["K_CELLS"]["nature"]) == ("check", "내용") and "제외는" in d["K_CELLS"]["note"]      # 내용이라면서 제외 — 확인 필요로
    assert (d["K_ROWS"]["value"], d["K_ROWS"]["nature"]) == ("check", "복합") and "유지는" in d["K_ROWS"]["note"]         # 복합을 유지 — 확인 필요로
    assert d["K_ADD"]["value"] == "check" and "note" not in d["K_ADD"]
    assert all(v["source"] == "llm" and len(v["inputHash"]) == 12 and "held" not in v for v in d.values())
    assert r["opinions"] == {"K_OVER": {"verdict": "keep", "nature": "내용", "reason": "시험", "inputHash": r["opinions"]["K_OVER"]["inputHash"]}}   # 「유지」 라 답해도 의견으로만
    assert sorted((x["id"], x["why"]) for x in r["rejected"]) == [("K_OTHER", "입력에 없는 id")] * 3 + [("K_USER", "입력에 없는 id")] * 3 and r["held"] == []


def test_cells_are_looked_up_by_the_frame_cell_id_not_by_the_part_coordinates():
    """엔진의 `from.cells[].r/c` 는 **기관 문서의 자리**, `to` 가 기준본(= 취합본) 칸 id — 기관 문서에서 위에 행이 늘어 자리가 밀려도 그 칸의 역할·머리 글·지금 취합본 글은 기준본의 그 칸 것이어야 한다."""
    to = _to()
    next(c for c in to["blocks"][8]["cells"] if c["id"] == "t1.2.1")["text"] = "8,000"   # 취합본의 그 칸(가나대 · 1차년도)에 먼저 든 글
    moved = _hunk("K_MOVED", "cells", "ready", "가나대", {"prev": "a7", "next": "t2", "table": "t1"},
                  {"table": "bt1", "cells": [{"r": 3, "c": 1, "id": "bt1.3.1", "text": "9,000", "base": "", "to": "t1.2.1"}]}, {"prev": "a7", "next": "t2"}, path=["2. 연구개발비 사용계획"], counts={"cells": 1})
    e = L._entry(moved, L._context(_frame(), to, _part()))
    assert e["content"] == [{"r": 2, "c": 1, "text": "9,000", "was": "", "now": "8,000", "cls": "input", "row": "가나대", "col": "1차년도"}]
    bare = {**moved, "from": {**moved["from"], "cells": [{k: v for k, v in moved["from"]["cells"][0].items() if k != "to"}]}}   # 칸 id 없이 자리로만(옛 길) — 기준본에 없는 행이라 역할·행 머리를 못 단다
    assert L._entry(bare, L._context(_frame(), to, _part()))["content"] == [{"r": 3, "c": 1, "text": "9,000", "was": "", "col": "1차년도"}]


def test_wrong_id_wrong_hash_and_missing_answers_are_rejected_and_held():
    def ask(jobs):
        out = []
        for j in jobs:
            rows = []
            for h in _payload(j)["hunks"]:
                if h["id"] == "K_FILL":   # 다른 자료에 대한 답(해시가 다름)
                    rows.append({"id": h["id"], "inputHash": "000000000000", "nature": "안내", "verdict": "제외", "reason": "옛 자료"})
                elif h["id"] == "K_CELLS":   # 같은 것을 두 번, 판정이 갈림
                    rows += [{"id": h["id"], "inputHash": h["inputHash"], "nature": "내용", "verdict": v, "reason": "두 번"} for v in ("유지", "확인 필요")]
                elif h["id"] == "K_ROWS":   # 모르는 판정
                    rows.append({"id": h["id"], "inputHash": h["inputHash"], "nature": "내용", "verdict": "넣기", "reason": "?"})
                elif h["id"] == "K_ADD":   # 모르는 성격은 「모름」 으로 — 유지는 내용일 때만이라 확인 필요
                    rows.append({"id": h["id"], "inputHash": h["inputHash"], "nature": "좋음", "verdict": "유지", "reason": " 까닭 "})
            rows.append({"id": "없는것", "inputHash": "x", "nature": "내용", "verdict": "유지", "reason": ""})
            out.append({"data": {"reviews": [*rows, "글"], "summary": ""}, "error": None})
        return out
    r = L.review(_items(), _frame(), _to(), _part(), ask=ask)
    assert sorted(x["why"] for x in r["rejected"]) == sorted(["inputHash 가 다름(보낸 자료에 대한 답이 아님)", "같은 작성 내용을 두 번", "모르는 verdict", *["입력에 없는 id"] * 3])
    assert all("unit" in x for x in r["rejected"]) and sorted(r["held"]) == ["K_FILL", "K_ROWS"]   # 받을 답이 없는 것은 「검토함」 이 아니라 보류
    d = r["decisions"]
    assert all(d[k]["value"] == "check" and d[k]["held"] is True and d[k]["nature"] == "모름" and "보류" in d[k]["reason"] for k in r["held"])
    assert d["K_CELLS"]["value"] == "check" and d["K_CELLS"]["note"] == "같은 작성 내용에 판정이 둘로 갈림" and "held" not in d["K_CELLS"]
    assert (d["K_ADD"]["value"], d["K_ADD"]["nature"], d["K_ADD"]["reason"]) == ("check", "모름", "까닭")
    assert [u.get("held") for u in r["units"]] == [None, 1, 1, 0]


def test_failed_or_silent_unit_is_held_not_reviewed():
    r = L.review(_items(), _frame(), _to(), _part(), ask=_fake(lambda h: ("내용", "유지"), fail=(1,)))   # 2장 호출이 시간 초과
    assert sorted(r["held"]) == ["K_CELLS", "K_ROWS"] and r["units"][2]["call"]["error"] == "시간 초과 600s" and r["units"][2]["answer"] is None and r["units"][2]["held"] == 2
    assert all(r["decisions"][k] == {"value": "check", "source": "llm", "nature": "모름", "reason": "LLM 검토 호출 실패(시간 초과 600s) — 검토하지 못해 보류",
                                     "inputHash": r["decisions"][k]["inputHash"], "held": True} for k in r["held"])
    assert {k: v["value"] for k, v in r["decisions"].items() if k not in r["held"]} == {"K_FILL": "keep", "K_ADD": "keep"}   # 다른 단위의 결과는 남는다
    for ask in (lambda jobs: [], lambda jobs: [{"data": {"reviews": [], "summary": ""}}] * len(jobs), lambda jobs: 1 / 0):   # 결과가 모자람 · 빈 답 · 예외 — 모두 보류
        r = L.review(_items(), _frame(), _to(), _part(), ask=ask)
        assert sorted(r["held"]) == ["K_ADD", "K_CELLS", "K_FILL", "K_ROWS"] and all(v["value"] == "check" and v["held"] for v in r["decisions"].values())
    assert L.review([], _frame(), _to(), _part(), ask=lambda jobs: 1 / 0)["decisions"] == {}   # 보낼 것이 없으면 부르지 않는다
    only_user = [h for h in _items() if h["key"] in ("K_USER", "K_OTHER", "K_OVER")]
    r = L.review(only_user, _frame(), _to(), _part(), ask=lambda jobs: 1 / 0)
    assert r["decisions"] == {} and r["left"] == 1 and all(u["call"] is None for u in r["units"])   # 판정 대상이 없는 장은 의견만 받자고 부르지 않는다


def test_char_cap_splits_units_between_hunks_and_marks_omitted_text():
    items = _items()
    items[3:3] = [_hunk(f"K_MORE{n}", "filled", "ready", "인텍", {"prev": "a2", "next": "a4", "ids": ["a3"]}, {"ids": ["b3", "b3x"]}, {"prev": "a2", "next": "a4"}, detail=f"사본 {n}") for n in range(3)]
    jobs = []
    plan = L.prepare(items, _frame(), _to(), _part(), chars=10**6)
    one = max(u["chars"] for u in plan["units"] if u.get("chars"))
    r = L.review(items, _frame(), _to(), _part(), ask=_fake(lambda h: ("내용", "유지"), jobs), chars=one // 2)   # 1장의 넷이 한 호출에 안 들어간다
    sent = [[h["id"] for h in _payload(j)["hunks"] if h["review"]] for j in jobs]
    assert len(jobs) > 3 and sorted(k for ks in sent for k in ks) == sorted(h["key"] for h in items if h["status"] == "ready" and not h["decision"])   # 판정 대상마다 꼭 한 호출
    whole = {h["key"]: e for h, e in ((h, L._entry(h, L._context(_frame(), _to(), _part()))) for h in items)}
    assert all(h["content"] == whole[h["id"]]["content"] and "omitted" not in h for j in jobs for h in _payload(j)["hunks"])   # 작성 내용은 쪼개지 않는다(통째로 한 호출에)
    first = [u for u in r["units"] if u["title"].startswith("1.")]
    assert len(first) > 1 and first[0]["title"].endswith(f"(1/{len(first)})") and _payload(jobs[0])["chapter"]["piece"] == [1, len(first)]
    assert sum(u["opinions"] for u in r["units"]) + r["left"] == 1 and set(r["decisions"]) == set(k for ks in sent for k in ks)

    part, jobs = _part("가나다라마바사 " * 2000), []   # 작성 내용 하나가 아주 길다 — 줄여 보내고 줄였다고 적는다
    r = L.review(_items(), _frame(), _to(), part, ask=_fake(lambda h: ("안내", "제외"), jobs), hunk_chars=1000)
    fill = _payload(jobs[0])["hunks"][0]
    assert fill["id"] == "K_FILL" and fill["omitted"] > 14000 and "…(생략 " in fill["content"][0]["p"] and fill["content"][0]["p"].endswith("가나다라마바사 ")
    assert fill["content"][1] == {"p": "- 1차년도: 센서 12종 설치"} and len(jobs[0]["content"]) < len(L.prompt({})) + 4000
    assert fill["inputHash"] == L.hashes(_items(), _frame(), _to(), part)["K_FILL"] != L.hashes(_items(), _frame(), _to(), _part())["K_FILL"]   # 지문은 줄이기 전 전체의 것
    assert r["decisions"]["K_FILL"]["value"] == "check" and "다 보지 못하고" in r["decisions"]["K_FILL"]["note"] and r["decisions"]["K_CELLS"]["value"] == "skip"   # 못 본 부분이 있는 제외는 안 받는다
    lines, cut = L._clip([{"row": f"행 {n} " + "값 " * 30} for n in range(40)], 1200)   # 줄이 많으면 줄 단위로 — 가운데를 빼고 표시
    assert cut and lines[0] == {"row": "행 0 " + "값 " * 30} and lines[-1]["row"].startswith("행 39 ") and [x for x in lines if "omitted" in x][0]["omitted"].startswith("…(생략 ")
    assert sum(map(L._size, lines)) <= 1300 and L._clip(lines, 10**6) == (lines, 0)
    lost = _hunk("K_LOST", "added", "ready", None, {"prev": "a9", "next": "a10"}, {"ids": ["없는 블록"]}, {"prev": "a9", "next": "a10"}, text="ㅇ 앞부분만 …")
    r = L.review([lost], _frame(), _to(), _part(), ask=_fake(lambda h: ("빈 틀", "제외"), jobs))
    assert _payload(jobs[-1])["hunks"][0]["omitted"] and r["decisions"]["K_LOST"]["value"] == "check"   # 기관 문서에서 글을 못 읽은 것도 못 본 것


def test_parts_for_the_guide_view(tmp_path, monkeypatch):
    job = _job(tmp_path, monkeypatch)
    ps = L.parts(job=job)
    assert [p["key"] for p in ps] == ["contract", "guide", "job"] and all(set(p) == {"key", "title", "text", "source", "note"} for p in ps)   # merge_llm.parts 와 같은 꼴
    assert ps[0]["text"] == L.CONTRACT and ps[0]["source"] == "app/merge_gather_llm.py"
    assert ps[1]["title"] == "판단 지침 — 취합 검토" and ps[1]["source"].endswith("gather.md") and ps[1]["text"] == G.body(G.get("gather"))
    assert ps[2]["title"] == "할 일 프롬프트 — 시험 취합" and ps[2]["text"] == "- 겹치면 덮지 않는다" and ps[2]["source"].endswith("plan_merge.md")
    assert [p["key"] for p in L.parts()] == ["contract", "guide"]
    (tmp_path / "gather.md").write_text("# 병합 지침 — 내 취합 지침\n<!-- 메모 -->\n- 내가 고친 기준\n", encoding="utf-8")
    monkeypatch.setenv("NFM_MERGE_GUIDES", str(tmp_path))   # 파일을 고치면 다음 실행부터(부를 때마다 읽는다)
    text = L.prompt({"hunks": []})
    assert "## 판단 지침 — 내 취합 지침" in text and "- 내가 고친 기준" in text and "메모" not in text and L.parts()[1]["text"] == "- 내가 고친 기준"
    monkeypatch.setenv("NFM_MERGE_GUIDES", "off")   # 지침이 없으면 최소 기준
    assert "지침 파일 없음" in L.prompt({"hunks": []}) and L.parts()[1]["title"].startswith("판단 지침 — (지침 파일 없음") and L.review([], {}, {}, {})["guide"] is None


def test_repo_guide_and_job_prompt_load(monkeypatch):
    monkeypatch.delenv("NFM_MERGE_GUIDES", raising=False)   # 저장소의 app/merge_guides_default/ 를 본다
    g = G.get("gather")
    body = G.body(g)
    assert g and g["title"] == "취합 검토" and "<!--" not in body and not body.startswith("# ") and "사용자 원문" not in body   # 주석과 제목 줄은 프롬프트에 안 들어간다
    for word in ("내용", "안내", "빈 틀", "서식만", "복합", "자리 이상", "확인 필요", "개요 줄", "표 캡션", "정해진 칸", "이어 넣는 행", "계산 칸", "머리 칸", "단위", "차년도 열", "기관 행"):
        assert word in body, word   # 판단 기준(성격 · 문단의 특성 · 표의 특성 · 자리 이상)이 지침에 있다
    assert not [w for w in ("매핑", "매칭", "차원") if w in body + L.CONTRACT]   # 프로젝트 용어(CLAUDE.md)
    assert all(n in L.CONTRACT for n in L.NATURES) and all(v in L.CONTRACT for v in L.VERDICT) and "글을 쓰지 않습니다" in L.CONTRACT
    monkeypatch.delenv("NFM_JOBS")   # 저장소의 jobs/ 를 본다(conftest 는 시험마다 빈 임시 폴더)
    job = J.get("plan_merge")
    assert job and job["name"] == "사업계획서 취합"
    text = L.prompt({"hunks": []}, job=job)
    order = [text.index(x) for x in ("### 답", "## 판단 지침 — 취합 검토", "## 할 일 — 사업계획서 취합", "## 자료(JSON)")]
    assert order == sorted(order) and "덮어쓰지 않는다" in text and text.endswith('{"hunks":[]}')
