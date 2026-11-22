"""기관·차년도 가리기(spec_병합 ② §4 「기관·차년도 가리기」 · §5-1 「표 짝 검토」 · spec_구분_기준 ② §21) — 2026-11-12 사용자 "테이블이 특정기관이나, 특정 년도에 대한 거라면 이게 식별되어서 매핑이 되어야지".
번호가 틀린 공동 라벨을 이름으로 잇기(core) · 절 제목의 기관 이름으로 맥락 기관(merge_pairs) · 내용이 든 후보 고르기 · 표 맥락과 어긋남(merge_fixed) · 표 짝 답 검증·지침(merge_llm·merge_guides)."""
import merge_data as M
from app import merge_fixed as X
from app import merge_guides as G
from app import merge_llm as L
from app import merge_pairs as P
from app.division_profiles import rnd
from app.division_profiles.rnd import core
from app.hwpx_doc import HwpxDoc

V = core.norm_values({"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연", "마바전자"]}})


def _para(i, text):
    return {"id": f"p{i}", "type": "paragraph", "text": text}


def test_joint_labels_with_repeated_number_are_joined_by_name():
    """작성자가 「공동연구개발기관1」 을 기관마다 되풀이해 쓴 절 — 번호는 못 잇지만 이름이 값의 다음 공동기관이면 그 기관의 항목(이름이 정체)."""
    of = core._joint_of(V)
    assert (of("[공동연구개발기관1 : 다라연]"), of("[공동연구개발기관1(주식회사 마바전자)]"), of("[공동연구개발기관1 : 기관명]"), of("[공동연구개발기관1 : 없는기관]")) == (2, 3, None, None)
    texts = ["[주관연구개발기관 : 인텍]", "주관 내용", "[공동연구개발기관1 : 가나대]", "가나대 내용", "[공동연구개발기관1 : 다라연]", "다라연 내용",
             "[공동연구개발기관1 : 주식회사 마바전자]", "마바전자 내용"]
    items = [_para(i, t) for i, t in enumerate(texts)]
    vals = lambda gs: [[it["value"] for it in g["items"]] for g in gs if g["dim"] == core.ORG]  # noqa: E731
    assert vals(core._para_groups(None, items, {})) == [[("lead", 0), ("joint", 1)]]   # 이름을 안 보면 둘뿐 — 뒤 두 절은 어느 묶음에도 안 든다(반영하면 빈 절이 새로 생겼다)
    got = core._para_groups(None, items, {}, joint_of=of)
    assert vals(got) == [[("lead", 0), ("joint", 1), ("joint", 2), ("joint", 3)]]
    assert [it["label"] for it in got[0]["items"]] == ["p0", "p2", "p4", "p6"]
    # 번호로 이어지는 라벨은 전과 같다 — 이름이 값의 차례와 달라도 번호가 먼저(자리 차례로 맞추는 기존 규칙)
    swapped = [_para(i, t) for i, t in enumerate(["[주관연구개발기관 : 인텍]", "가", "[공동연구개발기관1 : 다라연]", "나", "[공동연구개발기관2 : 가나대]", "다"])]
    assert vals(core._para_groups(None, swapped, {}, joint_of=of)) == [[("lead", 0), ("joint", 1), ("joint", 2)]]


def test_path_org_reads_the_org_section_title_but_stops_at_a_section_heading():
    names = ["인텍", "가나대", "주식회사 마바전자"]
    assert P._path_org(["8-2. 연구개발비 사용계획", "[공동연구개발기관1 : 가나대]", "o 연구개발기관별 사용계획 총괄표"], names) == "가나대"
    assert P._path_org(["[공동연구개발기관1 : 주식회사 마바전자]", "o 총괄표"], names) == "마바전자"   # ㈜·주식회사는 견줄 때 뗀다
    assert P._path_org(["[공동연구개발기관1 : 가나대]", "8-3. 연구개발비 세부 사용계획", "(2) 연구재료 구입비"], names) is None   # 절 제목이 먼저 — 바깥 기관 절은 이 표의 것이 아니다
    assert P._path_org(["가나대와의 협력 방안", "o 표"], names) is None   # 기관 절 제목(주관·공동연구개발기관 낱말)이 아닌 줄의 이름은 안 본다


def _g(key, **kw):
    s = {"key": key, "dim": "year", "kind": "cols", "path": ["사용계획"], "label": "", "ctx": {"year": None, "org": None}, "table": {"id": "t" + key, "sig": ["비목", "합계"]},
         "items": [{"value": "1차년도", "id": key + "-0", "text": "1차년도", "ident": ("year", 1)}]}
    return {**s, **kw}


def test_pair_prefers_the_only_candidate_with_content_and_org_context_gates():
    to = [_g("T")]
    assert P.pair(to, [_g("A"), _g("B")])["groups"][0]["status"] == "ambiguous"                       # 둘 다 모름 — 임의로 고르지 않는다
    assert P.pair(to, [_g("A", blank=False), _g("B", blank=False)])["groups"][0]["status"] == "ambiguous"   # 둘 다 내용이 있음
    g = P.pair(to, [_g("A", blank=True), _g("B", blank=False)])["groups"][0]                          # 빈 양식 그대로인 쪽에서는 가져올 것이 없다
    assert (g["status"], g["from"]["key"], g["source"]) == ("paired", "B", "script") and "내용이 든" in g["reason"]
    # 맥락 기관 — 같은 기관의 묶음만 후보(다른 기관은 머리가 같아도 아님)
    to = [_g("T", ctx={"year": None, "org": "다라연"})]
    g = P.pair(to, [_g("A", ctx={"year": None, "org": "가나대"}), _g("B", ctx={"year": None, "org": "다라연"})])["groups"][0]
    assert (g["status"], g["from"]["key"], [c["key"] for c in g["candidates"]]) == ("paired", "B", ["B"])


def test_table_context_clash_and_note():
    assert X._ctx_clash({"org": "가나대", "year": 2}, {"org": "가나대", "year": 1}) == "year"
    assert X._ctx_clash({"org": "가나대", "year": None}, {"org": "다라연", "year": None}) == "org"
    assert X._ctx_clash({"org": "가나대", "year": 2}, {"org": None, "year": None}) is None   # 한쪽을 모르는 것은 「어긋남」 이 아니다(스크립트는 안 잇지만 LLM·사람은 이을 수 있다)
    assert X._ctx_note("year", {"org": None, "year": 2}, {"org": None, "year": 1}) == "차년도가 다른 표 — 목적 2차년도 ↔ 원본 1차년도"


def test_forced_table_pairs_win_and_review_data_lists_all_tables():
    """LLM·사람이 정한 표 짝(forced)이 스크립트보다 먼저 — 끊은 표는 안 잇고, 정한 표는 그 원본과. 검토 자료 = 남는 칸이 있는 목적 표 전부 × 원본 표 전부(사람이 정한 표만 뺌 —
    2026-11-22 사용자 "테이블 매칭을 LLM이 모두 읽고 하길 바램": 후보가 없는 표 · 스크립트가 이은 표도 LLM 이 본다)."""
    d = M.small()
    plan = HwpxDoc(M.PLAN_FORM.read_bytes())
    assert not core.apply(plan, d["values"], levels_of=rnd.levels_of)["errors"]
    to, frm = {**d["to"], "values": d["values"]}, {**M._side("scope-plan", plan, M.PLAN_FORM.name), "values": d["values"]}
    base = X.plan(to, frm)
    paired = [t for t in base["tables"] if t["status"] == "paired"]
    assert paired and all(t["source"] == "script" and t["ctx"] == {"org": None, "year": None} for t in paired[:1])   # 표지 표 — 과제 전체 표끼리
    assert all({"cands", "why", "reason", "fromTitle", "format"} <= set(t) for t in base["tables"])
    first = paired[0]
    cut = X.plan(to, frm, forced={first["to"]: {"from": None, "source": "user"}})
    row = next(t for t in cut["tables"] if t["to"] == first["to"])
    assert (row["status"], row["source"], row["cells"]) == ("none", "user", 0) and not any(c["table"] == first["to"] for c in cut["cells"])
    kept = X.plan(to, frm, forced={first["to"]: {"from": first["from"], "source": "llm", "reason": "같은 표", "format": "행 수가 다름"}})
    row = next(t for t in kept["tables"] if t["to"] == first["to"])
    assert (row["status"], row["source"], row["reason"], row["format"]) == ("paired", "llm", "같은 표", "행 수가 다름") and kept["counts"]["tablesLlm"] == 1
    bad = X.plan(to, frm, forced={first["to"]: {"from": "t-없는-표", "source": "llm"}})   # 없는 표를 가리키는 짝은 안 받는다 — 스크립트 결과 그대로
    assert next(t for t in bad["tables"] if t["to"] == first["to"])["source"] == "script"
    rv = X.review_tables(to, frm)
    rows = {t["to"]: t for t in base["tables"]}
    assert base["counts"]["tablesOpen"] == sum(t["status"] != "paired" for t in base["tables"])   # 못 정한 표 = 후보가 없는 표도(LLM 이 원본 표를 모두 읽고 정한다)
    assert any(not t["cands"] for t in base["tables"] if t["status"] != "paired")                  # 이 쌍에도 후보 없는 표가 있다 — 전에는 LLM 이 못 본 표
    assert set(rows) <= {t["key"] for t in rv["targets"]} and rv["open"] == sum(t["status"] != "paired" for t in rv["targets"]) >= base["counts"]["tablesOpen"]
    assert all({"key", "title", "path", "ctx", "heads", "shape", "status", "why", "candidates"} <= set(t) for t in rv["targets"])
    assert all((t["status"], t.get("paired")) == (rows[t["key"]]["status"], rows[t["key"]]["from"] if rows[t["key"]]["status"] == "paired" else None) for t in rv["targets"] if t["key"] in rows)
    assert next(t for t in rv["targets"] if t["key"] == first["to"])["paired"] == first["from"]   # 스크립트가 이은 표도 LLM 이 확인한다(paired = 스크립트 짝)
    extra = [t for t in rv["targets"] if t["key"] not in rows]   # 표 짝 줄에 못 든 표 — 남는 칸은 있는데 머리 꼴이 둘 미만
    assert all(t["status"] == "none" and not t["candidates"] and len(t["heads"]) < 2 for t in extra)
    F = X._side(frm)
    srcs = {f["id"] for f in F["tables"] if f["id"] in F["idx"]}
    assert {s["key"] for s in rv["sources"]} == srcs and len(srcs) > 5                            # 원본 문서의 표 전부 — 후보로 든 표만이 아니다
    assert all("form" in s and "status" not in s and all(len(h) <= X.REVIEW_HEAD_LEN for h in s["heads"]) for s in rv["sources"])
    forms = [s["form"] for s in rv["sources"] if s["form"]]
    assert len(set(forms)) < len(forms)                                                            # 같은 꼴 표(머리·소속 제목 꼴이 같은 표)는 같은 form — merge_llm 이 한 줄로 묶는다
    cut_rv = X.review_tables(to, frm, forced={first["to"]: {"from": None, "source": "user"}})
    assert not any(t["key"] == first["to"] for t in cut_rv["targets"])                             # 사람이 정한 표는 검토 대상이 아니다
    # 머리 꼴이 둘 미만인 표 — 스크립트는 줄을 안 내지만 LLM·사람이 정한 짝이 있으면 줄이 선다(그 뒤 칸은 표 대응이 맞춘다)
    if extra:
        src = rv["sources"][0]["key"]
        got = X.plan(to, frm, forced={extra[0]["key"]: {"from": src, "source": "llm", "reason": "같은 표", "format": ""}})
        row = next(t for t in got["tables"] if t["to"] == extra[0]["key"])
        assert (row["status"], row["source"], row["from"]) == ("paired", "llm", src)


def test_review_sends_every_table_and_folds_repeated_forms():
    """표 짝 검토의 자료(merge_llm.review) — 단위마다 그 단위의 목적 표 전부(후보 없는 표 포함)와 원본 표 전부를 보낸다: 같은 꼴 표는 한 줄(same)로 묶고, 그 단위의 모든 목적 표와 맥락이 어긋나는 원본 표만 뺀다."""
    import json
    d = M.small()
    plan = HwpxDoc(M.PLAN_FORM.read_bytes())
    assert not core.apply(plan, d["values"], levels_of=rnd.levels_of)["errors"]
    to, frm = {**d["to"], "values": d["values"]}, {**M._side("scope-plan", plan, M.PLAN_FORM.name), "values": d["values"]}
    rv = X.review_tables(to, frm)
    ts, fs = (P.summarize(x["doc"].blocks(), x["graph"], x["tables"], d["values"]) for x in (to, frm))
    jobs = []

    def ask(js):
        jobs.extend(js)
        out = []
        for j in js:
            p = json.loads(j["content"].split("## 자료(JSON)\n", 1)[1])
            keys = [s["key"] for s in p["tableSources"]] + [m["key"] for s in p["tableSources"] for m in s.get("same") or ()]
            ans = [{"to": t["key"], "from": t.get("paired") or "", "reason": "시험", "format": ""} for t in p["tableTargets"]]
            free = next((t for t in p["tableTargets"] if not t.get("paired") and not t["candidates"]), None)   # 후보가 없는 표에도 답할 수 있다 — 맥락이 안 어긋나는 원본 표 하나
            if free:
                by = {s["key"]: s for s in p["tableSources"]}
                by.update({m["key"]: m for s in p["tableSources"] for m in s.get("same") or ()})
                pick = next((k for k in keys if not L._table_clash(free, by[k])), "")
                next(a for a in ans if a["to"] == free["key"])["from"] = pick
            out.append({"data": {"decisions": [], "tables": ans, "summary": ""}, "backend": "fake", "model": j["model"], "error": None})
        return out
    r = L.review({"blocks": to["doc"].blocks(), "graph": to["graph"]}, {"blocks": frm["doc"].blocks(), "graph": frm["graph"]}, P.pair(ts, fs), ts, fs, ask=ask, tables=rv)
    ps = [json.loads(j["content"].split("## 자료(JSON)\n", 1)[1]) for j in jobs]
    sent_t = [t["key"] for p in ps for t in p.get("tableTargets") or ()]
    assert sorted(sent_t) == sorted(t["key"] for t in rv["targets"])                                # 목적 표마다 꼭 한 단위 — 후보가 없는 표도
    assert any(not t["candidates"] for p in ps for t in p.get("tableTargets") or ())
    all_src = {s["key"] for s in rv["sources"]}
    for p in ps:
        if not p.get("tableTargets"):
            continue
        rows = p["tableSources"]
        keys = [s["key"] for s in rows] + [m["key"] for s in rows for m in s.get("same") or ()]
        assert len(keys) == len(set(keys)) and set(keys) <= all_src and "form" not in rows[0] and all("excerpt" in s for s in rows)
        gone = all_src - set(keys)                                                                    # 빠진 원본 표 = 이 단위의 모든 목적 표와 맥락이 어긋나는 표뿐
        by = {s["key"]: s for s in rv["sources"]}
        assert all(all(L._table_clash(t, by[k]) for t in p["tableTargets"]) for k in gone)
        hints = {c["key"] for t in p["tableTargets"] for c in t["candidates"]} | {t["paired"] for t in p["tableTargets"] if t.get("paired")}
        assert hints <= {s["key"] for s in rows}                                                      # 스크립트 후보 · 스크립트 짝은 묶지 않고 제 줄로(긴 excerpt)
        assert all(len(s["excerpt"]) <= (L.TARGET_LINES if s["key"] in hints else L.SOURCE_TABLE_LINES) for s in rows)
    assert any(s.get("same") for p in ps for s in p.get("tableSources") or ())                      # 같은 꼴 표는 한 줄로 묶인다
    paired = {t["key"] for t in rv["targets"] if t.get("paired")}
    assert set(r["tables"]["kept"]) == paired and not (set(r["tables"]["fixed"]) & paired)          # 스크립트 짝 그대로 답한 표 = kept(fixed 를 내지 않는다)
    assert r["tables"]["fixed"] and all(v["source"] == "llm" for v in r["tables"]["fixed"].values())  # 후보가 없던 표에 고른 원본 표가 받아들여진다
    assert sum(u["tables"] for u in r["units"]) == len(rv["targets"]) and "표는 모두 읽고" in jobs[0]["content"]


def test_fold_groups_same_form_tables_under_the_first():
    rows = [{"key": "f1", "title": "총괄표", "path": [], "ctx": {"org": "가나대", "year": None}, "heads": ["a", "b"], "shape": {"rows": 5, "cols": 2, "splits": False}, "form": "x"},
            {"key": "f2", "title": "총괄표", "path": [], "ctx": {"org": "다라연", "year": None}, "heads": ["a", "b"], "shape": {"rows": 6, "cols": 2, "splits": False}, "form": "x"},
            {"key": "f3", "title": "홀로 선 표", "path": [], "ctx": {"org": None, "year": None}, "heads": ["c"], "shape": {"rows": 1, "cols": 1, "splits": False}, "form": None},
            {"key": "f4", "title": "총괄표", "path": [], "ctx": {"org": "마바전자", "year": None}, "heads": ["a", "b"], "shape": {"rows": 7, "cols": 2, "splits": False}, "form": "x"},
            {"key": "f5", "title": "같은 꼴 · 맥락 없음", "path": [], "ctx": {"org": None, "year": None}, "heads": ["a", "b"], "shape": {"rows": 8, "cols": 2, "splits": False}, "form": "x"}]
    got = L._fold(rows, {"f4"}, lambda k, n: [k] * n)
    assert [s["key"] for s in got] == ["f1", "f3", "f4"] and all("form" not in s for s in got)        # 후보(f4)는 묶지 않는다
    assert got[0]["same"] == [{"key": "f2", "ctx": {"org": "다라연"}, "rows": 6}, {"key": "f5", "ctx": {}, "rows": 8, "title": "같은 꼴 · 맥락 없음"}]   # 제목은 묶은 줄의 제목과 다를 때만 싣는다
    assert (len(got[0]["excerpt"]), len(got[2]["excerpt"])) == (L.SOURCE_TABLE_LINES, L.TARGET_LINES) and "same" not in got[1]


def test_check_tables_keeps_script_pairs_and_reads_folded_keys():
    payload = {"tableTargets": [{"key": "t1", "ctx": {"org": "가나대", "year": None}, "paired": "f1"}, {"key": "t2", "ctx": {"org": "다라연", "year": None}, "paired": "f1"},
                                {"key": "t3", "ctx": {"org": "다라연", "year": None}}, {"key": "t4", "ctx": {"org": None, "year": None}, "paired": "f9"}],
               "tableSources": [{"key": "f1", "ctx": {"org": "가나대", "year": None}, "same": [{"key": "f2", "ctx": {"org": "다라연"}, "rows": 6}]}, {"key": "f9", "ctx": {"org": None, "year": None}}]}
    ans = {"tables": [{"to": "t1", "from": "f1", "reason": "스크립트 짝이 맞음", "format": ""},     # 스크립트 짝 그대로 — kept
                      {"to": "t2", "from": "f2", "reason": "같은 꼴 가운데 다라연의 표", "format": ""},   # 스크립트 짝과 다른 표(묶인 key) — fixed
                      {"to": "t3", "from": "f1", "reason": "맨 앞 표를 그냥 고름", "format": ""},       # 묶음의 맨 앞 표는 가나대의 표 — 기관이 다름
                      {"to": "t4", "from": "", "reason": "모르겠음", "format": ""}]}                    # 스크립트가 이은 표에 빈 답 — 스크립트 짝 그대로
    r = L.check_tables(payload, ans)
    assert r["kept"] == ["t1", "t4"] and r["none"] == [] and set(r["fixed"]) == {"t2"} and r["fixed"]["t2"]["from"] == "f2"
    assert [x["why"] for x in r["rejected"]] == ["기관이 다른 표"]


def test_check_tables_accepts_only_sent_keys_and_rejects_context_clash():
    payload = {"tableTargets": [{"key": "t1", "ctx": {"org": "가나대", "year": 2}}, {"key": "t2", "ctx": {"org": None, "year": None}}, {"key": "t3", "ctx": {"org": None, "year": 2}}],
               "tableSources": [{"key": "f1", "ctx": {"org": "가나대", "year": 1}}, {"key": "f2", "ctx": {"org": None, "year": None}}, {"key": "f3", "ctx": {"org": "다라연", "year": None}}]}
    ans = {"tables": [{"to": "t1", "from": "f1", "reason": "같은 인건비 표", "format": ""},      # 차년도가 다름 — 거절
                      {"to": "t2", "from": "f2", "reason": "머리가 같음", "format": "원본은 12행"},
                      {"to": "t2", "from": "f3", "reason": "두 번", "format": ""},
                      {"to": "t3", "from": "", "reason": "계획서에 그 차년도 표가 없음", "format": ""},
                      {"to": "t9", "from": "f2", "reason": "모르는 표", "format": ""},
                      {"to": "t1", "from": "f9", "reason": "모르는 원본", "format": ""}]}
    r = L.check_tables(payload, ans)
    assert r["fixed"] == {"t2": {"from": "f2", "source": "llm", "reason": "머리가 같음", "format": "원본은 12행"}}
    assert r["none"] == [{"to": "t3", "reason": "계획서에 그 차년도 표가 없음"}]
    assert [x["why"] for x in r["rejected"]] == ["차년도가 다른 표", "같은 표를 두 번", "검토 대상이 아닌 표(이미 짝이 있거나 입력에 없는 key)", "입력에 없는 원본 표 key"]
    assert r["kept"] == [] and L.check_tables(payload, {"decisions": []}) == {"fixed": {}, "rejected": [], "none": [], "kept": []}   # tables 가 없는 답(옛 꼴)


def test_guide_file_is_the_source_and_goes_into_the_prompt(tmp_path, monkeypatch):
    g = G.get("links")
    assert g and g["title"] == "자리 연결 LLM 검토" and "<!--" not in G.body(g) and not G.body(g).startswith("# ")   # 주석과 제목 줄은 프롬프트에 안 들어간다
    for word in ("같은 표는 같게", "특정 기관의 표", "특정 차년도의 표", "서식"):   # 사용자 요청(2026-11-12)의 세 기준이 지침에 있다
        assert word in G.body(g)
    assert G.get("../links") is None and G.get("없는것") is None
    text, _ = L.prompt({"targets": []})
    assert "## 판단 지침 — 자리 연결 LLM 검토" in text and text.index("## 판단 지침") < text.index("## 자료(JSON)") and "특정 차년도의 표" in text
    assert [p["key"] for p in L.parts()] == ["contract", "guide"] and L.parts()[1]["source"].endswith("links.md")
    (tmp_path / "links.md").write_text("# 병합 지침 — 내 지침\n<!-- 메모 -->\n- 내가 고친 기준\n", encoding="utf-8")
    monkeypatch.setenv("NFM_MERGE_GUIDES", str(tmp_path))   # 파일을 고치면 다음 실행부터(부를 때마다 읽는다)
    text, _ = L.prompt({"targets": []})
    assert "## 판단 지침 — 내 지침" in text and "- 내가 고친 기준" in text and "메모" not in text
    monkeypatch.setenv("NFM_MERGE_GUIDES", "off")   # 지침이 없으면 최소 기준
    assert "지침 파일 없음" in L.prompt({"targets": []})[0] and L.parts()[1]["title"].startswith("판단 지침 — (지침 파일 없음")
