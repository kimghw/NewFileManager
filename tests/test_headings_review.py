"""헤딩 추출 2단계 — 조정 재검토(D 호출)·템플릿 번호(spec_헤딩_추출 ② §6, 2026-11-09 사용자 「조정할 때 한번 하고 새로 다시 서브에이전트 호출해서
조정 다시 검토」·「템플릿 추출한건 넘버링」). 2026-11-09 템플릿 가지 규칙(A = role·parents·mainChain, 템플릿 = 사슬 하나 = 앵커, id 는 주 사슬 → 가지 → 라벨 → 칸)에 맞춤.
LLM 은 가짜 ask."""
import json

from app import heading_graph as HG
from app import heading_llm as HL


def _res(data=None, error=None, cost=0.0):
    return {"data": data, "backend": "fake", "model": "fake", "ms": 0, "costUsd": cost, "error": error}


def _data(job):
    return json.loads(job["content"].rsplit("## 자료(JSON)\n", 1)[1])


def fake_ask(**handlers):
    """job["what"] 의 「#」 앞 이름마다 handler(job, 자료) → 결과. 여기서는 heading_review 도 명시적으로 준다(기본 동의 없음)."""
    seen, jobs_seen = [], []

    def ask(jobs):
        out = []
        for job in jobs:
            seen.append(job["what"])
            jobs_seen.append(job)
            assert not any(k.startswith("_") for k in job), job.keys()
            out.append(handlers[job["what"].split("#", 1)[0]](job, _data(job)))
        return out
    ask.seen = seen
    ask.jobs = jobs_seen
    return ask


def _rec(i, text, letter, shape, family, fmt, lead=0):
    return {"id": f"p{i}", "n": i, "area": "body", "path": [], "table": None, "cell": None, "kind": "marker", "family": family, "shape": shape,
            "letter": " " * lead + letter, "rest": text[len(letter):].strip(), "text": " " * lead + text, "leadSpaces": lead, "fmt": fmt,
            "char": {"text": {"sizePt": 10.0, "bold": False}}, "blank": False,
            "spans": [{"i": 0, "line": 0, "kind": "marker", "family": family, "letter": letter}]}


def _stage1():
    """장 2 × 「가.」 3 × 「(N)」 3 — 「가.」 첫째와 「(3)」 은 S9, 나머지 S2 → (S2, S9) 쌍이 슬롯 main|L2(2문단)·main|L3(6문단)에."""
    paras = []
    for i in range(1, 3):
        paras.append(_rec(len(paras), f"{i}. 큰 제목", f"{i}.", "N.", "n.dot", "S1", 0))
        for j, g in enumerate("가나다"):
            paras.append(_rec(len(paras), f"{g}. 중간 제목", f"{g}.", "가.", "k.dot", "S2" if j else "S9", 1))
            for k in range(1, 4):
                paras.append(_rec(len(paras), f"({k}) 작은 제목", f"({k})", "(N)", "n.paren", "S2" if k < 3 else "S9", 2))
    return {"paras": paras, "labels": {"S1": {"name": "큰"}, "S2": {"name": "보통 10pt"}, "S9": {"name": "빨강 안내 10pt"}}}


def _shapes(stage1):
    types = HG.type_table(HG.candidates(stage1))
    return {t["shape"]: tid for tid, t in types.items()}


MAIN = "body:N.›가.›(N)"  # _stage1 의 주 사슬 앵커(= 템플릿 #1 의 name)


def _slot(level):
    return f"{MAIN}|L{level}"


def _a_main(by_shape, parents=None, main=("N.", "가.", "(N)")):
    par = parents or {"N.": ["root"], "가.": ["N."], "(N)": ["가."]}
    return {"types": [{"type": by_shape[s], "role": "heading", "parents": par[s], "variantOf": "", "basis": "", "reason": ""} for s in par],
            "mainChain": list(main), "summary": ""}


def _b_none(job, d):
    return _res({"changes": [], "summary": ""})


# ---- 재검토(D 호출) -----------------------------------------------------------------------------------------

def test_review_disagree_becomes_undecided_and_agree_keeps_first():
    """C 가 두 슬롯 다 「조정」 → D 가 L2 동의 · L3 불일치(다름) → L2 는 조정(review agree), L3 는 미판정(first=adjust, review disagree)."""
    st1 = _stage1()
    A = _a_main(_shapes(st1))
    seen_d = []

    def c(job, d):
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": True, "reason": "C " + p["slot"]} for p in d["pairs"]], "summary": ""})

    def review(job, d):
        assert job["schema"] is HL.REVIEW_SCHEMA and job["effort"] == "medium" and job["what"] == "heading_review#1"
        assert "## 지침 — " in job["content"] and "## 재검토(조정 판정을 다시 보기)" in job["content"]  # 재검토 계약 + 지침(templates 의 재검토 절·tolerance)
        for p in d["pairs"]:
            seen_d.append((p["slot"], p["a"], p["b"]))
            assert p["first"] == {"same": True, "reason": "C " + p["slot"]}  # 1차 판정·까닭이 붙어 온다
            assert p["aName"] == "보통 10pt" and p["bName"] == "빨강 안내 10pt" and p["examples"] and p["tplNo"] == 1
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "verdict": "agree" if p["slot"] == _slot(2) else "disagree",
                                "same": p["slot"] == _slot(2), "reason": "D " + p["slot"]} for p in d["pairs"]], "summary": "재검토"})

    ask = fake_ask(heading_types=lambda job, d: _res(A), heading_section=_b_none, heading_formats=c, heading_review=review)
    g = HG.build(st1, use_llm=True, ask=ask)
    json.dumps(g)
    assert not g["llm"]["fallback"] and g["llm"]["mainChain"] == ["N.", "가.", "(N)"]
    assert ask.seen.count("heading_review#1") == 1 and ask.seen.index("heading_review#1") > ask.seen.index("heading_formats#1")  # C 뒤에 D 한 번
    assert sorted(seen_d) == [(_slot(2), "S2", "S9"), (_slot(3), "S2", "S9")]
    adj = [a for a in g["adjustments"] if a["from"] == "S9"]
    l2 = [a for a in adj if a["level"] == 2]
    l3 = [a for a in adj if a["level"] == 3]
    assert len(l2) == 2 and len(l3) == 6 and len(adj) == len(g["adjustments"])
    for a in l2:
        assert a["decision"] == "adjust" and "first" not in a and a["reason"] == "C " + _slot(2)
        assert a["review"] == {"verdict": "agree", "same": True, "reason": "D " + _slot(2)}
    for a in l3:
        assert a["decision"] == "undecided" and a["first"] == "adjust" and a["reason"] == "C " + _slot(3)  # 1차 판정은 그대로 남고 결론만 미판정
        assert a["review"] == {"verdict": "disagree", "same": False, "reason": "D " + _slot(3)}
        assert a["tplNo"] == 1 and a["template"] == MAIN
    c_ = g["counts"]
    assert (c_["adjust"], c_["reviewed"], c_["disagreed"]) == (2, 8, 6)
    lm = g["llm"]
    assert (lm["reviewPairs"], lm["reviewDisagree"], lm["reviewFailed"], lm["failed"]) == (2, 1, 0, 0)
    assert set(g["guides"]) == {"graph", "templates", "tolerance"}


def test_c_decides_every_slot_pair_and_review_failure_keeps_first_decision():
    """조정 판정은 C 가 슬롯마다(A 는 서식 쌍을 보지 않음 — 2026-11-09 astra: 슬롯 밖 답 재사용 금지). D 가 실패하면 1차 판정 그대로 + review failed."""
    st1 = _stage1()
    A = _a_main(_shapes(st1))
    seen_c, seen_d = [], []

    def a(job, d):
        assert "formatPairs" not in d and d["mainChainProposal"] and all("key" in r for r in d["types"])
        return _res(A)

    def c(job, d):
        seen_c.extend(p["slot"] for p in d["pairs"])
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": True, "reason": "C 오차"} for p in d["pairs"]], "summary": ""})

    def review(job, d):
        seen_d.extend((p["slot"], p["first"]) for p in d["pairs"])
        return _res(None, error="가짜 D 실패")

    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=a, heading_section=_b_none, heading_formats=c, heading_review=review))
    assert sorted(seen_c) == [_slot(2), _slot(3)]
    assert sorted(seen_d) == [(_slot(2), {"same": True, "reason": "C 오차"}), (_slot(3), {"same": True, "reason": "C 오차"})]
    adj = g["adjustments"]
    assert adj and all(a["decision"] == "adjust" and "first" not in a for a in adj)
    assert all(a["review"] == {"verdict": "failed", "same": None, "reason": "가짜 D 실패"} for a in adj)
    assert (g["counts"]["adjust"], g["counts"]["reviewed"], g["counts"]["disagreed"]) == (8, 0, 0)
    lm = g["llm"]
    assert lm["formatPairs"] == 2 and (lm["reviewPairs"], lm["reviewFailed"], lm["reviewDisagree"]) == (2, 2, 0) and lm["failed"] == 1


def test_apply_review_derives_verdict_from_same_and_marks_missing_as_failed():
    """verdict 는 재검토 same 과 1차 same 을 견줘 스크립트가 정한다(응답의 verdict 칸이 어긋나도 same 을 믿음). 답이 빠진 쌍·슬롯을 비운 답은 failed(슬롯 밖 답은 안 씀)."""
    pairs = [{"slot": "main|L2", "a": "S2", "b": "S9", "first": {"same": True, "reason": "1"}},
             {"slot": "main|L3", "a": "S2", "b": "S9", "first": {"same": False, "reason": "2"}},
             {"slot": "sub|L1", "a": "S2", "b": "S7", "first": {"same": True, "reason": "3"}},
             {"slot": "sub|L2", "a": "S2", "b": "S8", "first": {"same": True, "reason": "4"}}]
    res = _res({"pairs": [{"slot": "main|L2", "a": "S2", "b": "S9", "verdict": "agree", "same": False, "reason": "실은 다름"},  # verdict 칸이 틀림 → same 기준 disagree
                          {"slot": "main|L3", "a": "S2", "b": "S9", "verdict": "disagree", "same": False, "reason": "같다"},  # same 이 1차와 같음 → agree
                          {"slot": "", "a": "S2", "b": "S7", "verdict": "agree", "same": True, "reason": "슬롯 비움"}], "summary": ""})
    out = HG.apply_review(pairs, res)
    assert out[("main|L2", "S2", "S9")] == {"verdict": "disagree", "same": False, "reason": "실은 다름"}
    assert out[("main|L3", "S2", "S9")] == {"verdict": "agree", "same": False, "reason": "같다"}
    assert out[("sub|L1", "S2", "S7")] == {"verdict": "failed", "same": None, "reason": "재검토 답 없음"}  # 슬롯을 비운 답은 그 슬롯의 답이 아니다
    assert out[("sub|L2", "S2", "S8")] == {"verdict": "failed", "same": None, "reason": "재검토 답 없음"}
    failed = HG.apply_review(pairs[:1], _res(None, error="시간 초과"))
    assert failed[("main|L2", "S2", "S9")] == {"verdict": "failed", "same": None, "reason": "시간 초과"}


def test_pairs_without_first_decision_are_not_reviewed():
    """C 호출이 실패해 1차 판정이 없는 쌍은 재검토 대상이 아니다(어차피 미판정) — D 호출 없음, reviewPairs 0, 조정은 review 없이 undecided."""
    st1 = _stage1()
    A = _a_main(_shapes(st1))
    ask = fake_ask(heading_types=lambda job, d: _res(A), heading_section=_b_none, heading_formats=lambda job, d: _res(None, error="가짜 C 실패"),
                   heading_review=lambda job, d: (_ for _ in ()).throw(AssertionError("1차 판정 없는 쌍을 재검토하면 안 됨")))
    g = HG.build(st1, use_llm=True, ask=ask)
    assert "heading_formats#1" in ask.seen and not any(w.startswith("heading_review") for w in ask.seen)
    assert g["llm"]["reviewPairs"] == 0 and g["llm"]["failed"] == 1
    assert g["adjustments"] and all(a["decision"] == "undecided" and "review" not in a and "first" not in a for a in g["adjustments"])
    assert (g["counts"]["reviewed"], g["counts"]["disagreed"]) == (0, 0)


def test_partial_c_answer_leaves_other_slot_undecided():
    """C 가 한 슬롯(L3)의 답을 빠뜨리면 같은 (a, b) 의 다른 슬롯 답을 끌어오지 않는다 — L3 는 미판정이고 재검토도 L2 만 받는다(astra 2026-11-09)."""
    st1 = _stage1()
    A = _a_main(_shapes(st1))
    seen_d = []

    def c(job, d):
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": True, "reason": "C L2"} for p in d["pairs"] if p["slot"] == _slot(2)], "summary": ""})

    def review(job, d):
        seen_d.extend((p["slot"], p["first"]["reason"]) for p in d["pairs"])
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "verdict": "agree", "same": True, "reason": "D"} for p in d["pairs"]], "summary": ""})

    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A), heading_section=_b_none, heading_formats=c, heading_review=review))
    assert seen_d == [(_slot(2), "C L2")] and g["llm"]["reviewPairs"] == 1
    l2 = [a for a in g["adjustments"] if a["level"] == 2]
    l3 = [a for a in g["adjustments"] if a["level"] == 3]
    assert l2 and all(a["decision"] == "adjust" and a["review"]["verdict"] == "agree" for a in l2)
    assert l3 and all(a["decision"] == "undecided" and "review" not in a for a in l3)
    assert (g["counts"]["adjust"], g["counts"]["reviewed"], g["counts"]["disagreed"]) == (2, 2, 0)


def test_review_batches_follow_pair_batch(monkeypatch):
    """D 도 C 처럼 PAIR_BATCH 개씩 묶어 부른다(쌍 2개 · PAIR_BATCH 1 → heading_review#1·#2), 묶음마다 _pairs 로 답을 맞춘다."""
    monkeypatch.setattr(HG, "PAIR_BATCH", 1)
    st1 = _stage1()
    A = _a_main(_shapes(st1))
    sizes = []

    def c(job, d):
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": True, "reason": "C"} for p in d["pairs"]], "summary": ""})

    def review(job, d):
        sizes.append(len(d["pairs"]))
        p = d["pairs"][0]
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "verdict": "disagree", "same": False, "reason": "D"}], "summary": ""})

    ask = fake_ask(heading_types=lambda job, d: _res(A), heading_section=_b_none, heading_formats=c, heading_review=review)
    g = HG.build(st1, use_llm=True, ask=ask)
    assert sizes == [1, 1] and ask.seen.count("heading_review#1") == 1 and ask.seen.count("heading_review#2") == 1
    assert ask.seen.count("heading_formats#1") == 1 and ask.seen.count("heading_formats#2") == 1
    assert g["llm"]["reviewPairs"] == 2 and g["llm"]["reviewDisagree"] == 2
    assert all(a["decision"] == "undecided" and a["first"] == "adjust" for a in g["adjustments"])


def test_review_not_called_without_llm_or_when_no_pairs():
    """스크립트만(LLM 없음)이면 재검토 없음. LLM 이어도 슬롯 서식 쌍이 없으면 D 호출 없음(reviewPairs 0)."""
    st1 = _stage1()
    g = HG.build(st1, use_llm=False)
    assert "reviewPairs" not in g["llm"] and all("review" not in a for a in g["adjustments"]) and g["counts"]["reviewed"] == 0
    for r in st1["paras"]:
        r["fmt"] = "S2"  # 서식 라벨 하나 → 쌍 없음
    ask = fake_ask(heading_types=lambda job, d: _res(_a_main(_shapes(st1))), heading_section=_b_none,
                   heading_formats=lambda job, d: _res({"pairs": [], "summary": ""}), heading_review=lambda job, d: (_ for _ in ()).throw(AssertionError("D 불림")))
    g = HG.build(st1, use_llm=True, ask=ask)
    assert g["llm"]["reviewPairs"] == 0 and not g["adjustments"] and "heading_review#1" not in ask.seen


# ---- 템플릿 번호(id) -------------------------------------------------------------------------------------------

def _stage1_branches():
    """장 2 × (□ 2 · 가. 1 · (1) 1) — 1. 아래 가지 자리: □ 가 주 사슬 L2, 「가.」·「(N)」 은 가지 템플릿(문서 순 첫 등장 = 가. → (N))."""
    paras = []
    for i in range(1, 3):
        paras.append(_rec(len(paras), f"{i}. 큰 제목", f"{i}.", "N.", "n.dot", "S2", 0))
        paras.append(_rec(len(paras), "□ 네모 하나", "□", "□", "square", "S2", 1))
        paras.append(_rec(len(paras), "□ 네모 둘", "□", "□", "square", "S2", 1))
        paras.append(_rec(len(paras), "가. 가나다", "가.", "가.", "hangul-dot", "S2", 1))
        paras.append(_rec(len(paras), "(1) 괄호", "(1)", "(N)", "paren-num", "S2", 1))
    return {"paras": paras, "labels": {"S2": {"name": "보통"}}}


def test_branch_templates_numbered_in_document_order():
    """가지 템플릿 번호는 문서에 먼저 나온 순 — main #1(N. › □), 「가.」 #2, 「(N)」 #3. 2. 안의 「가.」 는 #2 의 둘째 인스턴스(같은 사슬 = 같은 id)."""
    st1 = _stage1_branches()
    by = _shapes(st1)
    A = {"types": [{"type": by[s], "role": "heading", "parents": ["root"] if s == "N." else ["N."], "variantOf": "", "basis": "", "reason": ""} for s in by],
         "mainChain": ["N.", "□"], "summary": ""}
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A), heading_section=_b_none,
                                                  heading_formats=lambda job, d: _res({"pairs": [], "summary": ""})))
    assert [(t["id"], t["no"], t["name"], t["kind"], t["chain"]) for t in g["templates"]] == [(1, 1, "body:N.›□", "main", ["N.", "□"]), (2, 2, "body:가.", "branch", ["가."]),
                                                                                             (3, 3, "body:(N)", "branch", ["(N)"])]
    N = {n["id"]: n for n in g["nodes"]}
    assert (N["p0"]["tplNo"], N["p1"]["tplNo"], N["p3"]["tplNo"], N["p4"]["tplNo"]) == (1, 1, 2, 3)
    assert (N["p1"]["level"], N["p3"]["level"], N["p4"]["level"]) == (2, 1, 1) and N["p3"]["parent"] == N["p4"]["parent"] == "p0"
    ins = [i for i in g["instances"] if i["template"] == 2]
    assert [(i["no"], i["root"]) for i in ins] == [(1, "p3"), (2, "p8")] and all(i["anchor"] == "body:가." for i in ins)
    assert [i["root"] for i in g["instances"] if i["template"] == 1] == ["p0", "p5"]  # 1.·2. 도 #1 의 인스턴스
    het = {h["parent"]: sorted(x["key"] for x in h["letters"]) for h in g["heterogeneous"]}
    assert het["p0"] == ["(N)", "□", "가."]  # 가지 자리 = 이종 형제


def test_templates_numbered_main_branch_and_nodes_carry_tpl_no():
    """A 가 「(N)」 의 부모를 N. 로 보면(가. 와 형제) (N) 은 가지 #2 — templates[].no = 주 사슬 → 가지, nodes[].tplNo·adjustments[].tplNo·instances[].no."""
    st1 = _stage1()
    by_shape = _shapes(st1)
    A = _a_main(by_shape, parents={"N.": ["root"], "가.": ["N."], "(N)": ["N."]}, main=("N.", "가."))
    ask = fake_ask(heading_types=lambda job, d: _res(A), heading_section=_b_none,
                   heading_formats=lambda job, d: _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": True, "reason": "C"} for p in d["pairs"]], "summary": ""}),
                   heading_review=lambda job, d: _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "verdict": "agree", "same": True, "reason": "D"}
                                                                for p in d["pairs"]], "summary": ""}))
    g = HG.build(st1, use_llm=True, ask=ask)
    assert [(t["no"], t["name"], t["kind"]) for t in g["templates"]] == [(1, "body:N.›가.", "main"), (2, "body:(N)", "branch")]
    N = {n["id"]: n for n in g["nodes"]}
    assert all(N[f"p{i}"]["tplNo"] == (2 if st1["paras"][i]["shape"] == "(N)" else 1) for i in range(len(st1["paras"])))
    assert {a["tplNo"] for a in g["adjustments"] if a["template"] == "body:(N)"} == {2} and {a["tplNo"] for a in g["adjustments"] if a["template"] == "body:N.›가."} == {1}
    ins = [i for i in g["instances"] if i["template"] == 2]
    assert [i["no"] for i in ins] == list(range(1, len(ins) + 1)) and len(ins) == 18
    assert "tplNo" not in g  # 노드·조정에만 붙고 그래프 맨 위에는 없음


def test_templates_numbered_in_script_fallback():
    """LLM 없이도 번호 — 어림 주 사슬 N. › 가. › (N) 하나(#1), 모든 노드 tplNo 1, 어림 부모는 heuristic 표지."""
    g = HG.build(_stage1(), use_llm=False)
    assert [(t["no"], t["name"], t["kind"]) for t in g["templates"]] == [(1, MAIN, "main")]
    assert all(n["tplNo"] == 1 for n in g["nodes"]) and g["counts"]["heuristic"] > 0
