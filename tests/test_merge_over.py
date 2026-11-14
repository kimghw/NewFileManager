"""넘친 개요 레벨(spec_병합 ② §5-5 — app/merge_over.py): 사례마다의 선택(저장 · 검증 · 풀기) · 후보 템플릿 · 계획에 보일 것 · 넣은 뒤 다시 맞추기.
자료 = 작은 쌍(tests/merge_data.small): 원본 계획서의 □›o›-›· 사슬을 연차보고서 기관 소제목([…]›□›o›- 의 L1) 아래 넣으면 「·」 줄이 넘치고(사례 「…<·」),
마지막 레벨 자리 「- (추진 내용)」 아래 넣으면 네 줄이 모두 넘친다(사례 「…<□›o›-›·」)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app import merge_convert as MC
from app import merge_over as MO
from app.outline_edit import body_of, prefix_of
from tests import merge_data as M

SRC_TPL, TO_TPL = "body:□›o›-›·", "body:[…]›□›o›-"
ONE, ALL = f"{TO_TPL}<·", f"{TO_TPL}<□›o›-›·"
JS = Path(__file__).parents[1] / "app" / "static" / "merge_over.js"


@pytest.fixture(scope="module")
def S():
    return M.small()


def _src(S):
    nodes = S["from"]["graph"]["nodes"]
    top = next(n for n in nodes if n["template"] == SRC_TPL and n["level"] == 1)
    leaf = next(n for n in nodes if n["template"] == SRC_TPL and n["level"] == 4 and n["instance"] == top["instance"])
    ids = [b["id"] for b in S["from"]["doc"].blocks()]
    return ids[ids.index(top["para"]):ids.index(leaf["para"]) + 1]


def _anchor(S, leaf=False):
    nodes = S["to"]["graph"]["nodes"]
    if leaf:
        return next(n["para"] for n in nodes if n["template"] == TO_TPL and (n.get("text") or "").startswith("(추진 내용)"))
    return next(n["para"] for n in nodes if n["template"] == TO_TPL and n["level"] == 1 and "주관" in (n.get("letter") or ""))


def _docs(S, src):
    letters = {n["para"]: n["letter"] for n in S["from"]["graph"]["nodes"] if n["para"] in src and n.get("level")}
    frm, to = M.fresh(S["from"]), M.fresh(S["to"])
    frm.blocks(), to.blocks()
    for k, s in enumerate(src):
        if s in letters:
            frm.set_text(s, frm._text(frm._ids[s]).rstrip() + f" 넘침{k}")
    return to, frm, letters


def test_store_keeps_a_choice_per_case_and_bumps_the_version():
    wid = "넘침 시험(작업 id 꼴이 아니라 메모리에)"
    assert MO.load(wid) == {"version": 0, "cases": {}}
    a = MO.put(wid, ONE, {"mode": "cover", "levels": [], "template": None})
    assert a["version"] == 1 and a["cases"][ONE]["mode"] == "cover" and a["cases"][ONE]["at"]
    b = MO.put(wid, ALL, {"mode": "template", "levels": [], "template": {"template": "body:o›-", "level": 1}})
    assert b["version"] == 2 and set(MO.load(wid)["cases"]) == {ONE, ALL}
    assert MO.put(wid, ONE, None) == MO.load(wid) and MO.load(wid)["version"] == 3 and set(MO.load(wid)["cases"]) == {ALL}   # 지움 = 기본으로


def test_letter_kind_and_shape():
    assert [MO.numbered(x) for x in ("(1)", "①", "가.", "a.", "2-3.", "o", "ㅇ", "-", "▪", "A")] == [True, True, True, True, True, False, False, False, False, False]
    assert [MO.shape(x) for x in ("(3)", "③", "다.", "2-3.", "b)", "ㅇ", "○", "–", "⋅", "■", "▪")] == ["(N)", "①", "가.", "N-N.", "a)", "o", "o", "-", "·", "□", "▪"]


def test_templates_are_the_target_body_templates_with_usable_levels(S):
    to = M.fresh(S["to"])
    to.blocks()
    tpls = {t["anchor"]: t for t in MO.templates(S["to"]["graph"], to)}
    assert TO_TPL in tpls and "body:o›-" in tpls and not [a for a in tpls if a.startswith("cell:")]   # 표 칸 템플릿은 후보가 아니다
    lv = {x["level"]: x for x in tpls[TO_TPL]["levels"]}
    assert [lv[i]["ok"] for i in (1, 2, 3, 4)] == [False, True, True, True] and lv[3]["key"] == "o" and lv[3]["letter"] and lv[3]["rep"]   # 괄호 줄 레벨은 본보기로 못 쓴다
    assert tpls[TO_TPL]["chain"] == ["[…]", "□", "o", "-"] and tpls[TO_TPL]["no"]
    to.set_text(lv[3]["rep"], "레터를 지운 줄")   # 대표 줄의 첫머리에서 레터가 사라지면 못 쓴다
    assert not {x["level"]: x for x in next(t for t in MO.templates(S["to"]["graph"], to) if t["anchor"] == TO_TPL)["levels"]}[3]["ok"]


def test_validate_normalizes_or_refuses(S):
    tpls = MO.templates(S["to"]["graph"])
    like = {"template": TO_TPL, "level": 3}
    assert MO.validate({"mode": "cover", "levels": [{"letter": "x"}]}) == {"mode": "cover", "levels": [], "template": None}
    got = MO.validate({"mode": "edit", "levels": [{"letter": " ▪ ", "like": like, "lead": 4}, None, {"letter": "", "lead": None}, {"lead": 0}]}, tpls)
    assert got == {"mode": "edit", "template": None, "levels": [{"letter": "▪", "like": like, "lead": 4}, None, None, {"letter": None, "like": None, "lead": 0}]}
    assert MO.validate({"mode": "edit", "levels": [{}, None]}) == {"mode": "cover", "levels": [], "template": None}   # 아무것도 안 고침 = 덮은 그대로
    assert MO.validate({"mode": "template", "template": {"template": "body:o›-", "level": 1}}, tpls)["template"] == {"template": "body:o›-", "level": 1}
    for bad, word in (({"mode": "x"}, "mode"), ({"mode": "edit", "levels": []}, "levels"), ({"mode": "edit", "levels": [{"letter": "가 나"}]}, "빈칸"),
                      ({"mode": "edit", "levels": [{"letter": "x" * 13}]}, "12자"), ({"mode": "edit", "levels": [{"lead": 41}]}, "앞 공백"), ({"mode": "edit", "levels": [{"lead": True}]}, "앞 공백"),
                      ({"mode": "edit", "levels": [{"like": {"template": "body:없는 템플릿", "level": 1}}]}, "없습니다"), ({"mode": "edit", "levels": [{"like": {"template": TO_TPL, "level": 1}}]}, "본보기로 쓸 수 없는"),
                      ({"mode": "template", "template": {"template": TO_TPL, "level": 9}}, "없습니다"), ({"mode": "template"}, "템플릿"), ({"mode": "edit", "levels": [{"like": {"template": TO_TPL, "level": "3"}}]}, "level")):
        with pytest.raises(ValueError, match=word):
            MO.validate(bad, tpls)
    assert MO.validate({"mode": "edit", "levels": [{"like": {"template": "body:없는 템플릿", "level": 1}}]})["levels"][0]["like"]["level"] == 1   # 후보를 안 주면 꼴만 본다


def test_resolve_turns_choices_into_level_specs(S):
    tg = S["to"]["graph"]
    rep = {int(s["level"]): s["rep"] for s in next(t for t in tg["templates"] if t["anchor"] == TO_TPL)["slots"]}
    letter = {n["para"]: n["letter"] for n in tg["nodes"]}
    cases = {ONE: {"mode": "edit", "levels": [{"letter": None, "like": {"template": TO_TPL, "level": 4}, "lead": 5}]},
             ALL: {"mode": "template", "template": {"template": TO_TPL, "level": 3}},
             "cover 사례": {"mode": "cover", "levels": []},
             "없는 본보기": {"mode": "edit", "levels": [None, {"letter": "(1)", "like": {"template": "body:없는 템플릿", "level": 2}, "lead": None}]}}
    got = MO.resolve(cases, tg)
    assert set(got) == {ONE, ALL, "없는 본보기"}   # 지정이 없는 사례(cover)는 싣지 않는다
    assert got[ONE] == [{"like": rep[4], "likeLetter": letter[rep[4]], "letter": None, "lead": 5, "numbered": False, "missing": False}]
    assert [(x["like"], x["likeLetter"]) for x in got[ALL]] == [(rep[3], letter[rep[3]]), (rep[4], letter[rep[4]])]   # 「다른 템플릿」 = 시작 레벨부터 그 템플릿의 끝까지 차례로
    none, miss = got["없는 본보기"]
    assert none is None and miss["missing"] and miss["like"].startswith("?") and miss["numbered"] and miss["letter"] == "(1)"
    num = next(t for t in tg["templates"] if t["anchor"].startswith("body:N.›N-N."))["anchor"]
    assert MO.resolve({"k": {"mode": "template", "template": {"template": num, "level": 2}}}, tg)["k"][0]["numbered"]   # 번호형 레벨을 본보기로 고르면 번호형


def test_plan_view_lists_cases_with_what_goes_in(S):
    fg, tg = S["from"]["graph"], S["to"]["graph"]
    src = _src(S)
    to, frm, _ = _docs(S, src)
    fill = {"items": [{"to": "가", "skip": None, "anchor": _anchor(S), "src": src}, {"to": "나", "skip": None, "anchor": _anchor(S, leaf=True), "src": src},
                      {"to": "다", "skip": "occupied", "anchor": _anchor(S), "src": src}, {"to": "라", "skip": None, "anchor": _anchor(S, leaf=True), "src": src}]}
    n_body = sum(1 for s in src if s not in {n["para"] for n in fg["nodes"] if n.get("level")})
    items, cases = MO.fill_preview({"doc": to, "graph": tg}, {"doc": frm, "graph": fg}, fill, {})
    assert items == {"가": {"converted": 3, "over": 1, "kept": {"body": n_body, "tooDeep": 1}}, "나": {"converted": 0, "over": 4, "kept": {"body": n_body, "tooDeep": 4}},
                     "라": {"converted": 0, "over": 4, "kept": {"body": n_body, "tooDeep": 4}}}   # 건너뛴 항목은 안 센다
    by = {c["key"]: c for c in cases}
    assert set(by) == {ONE, ALL} and (by[ONE]["lines"], by[ONE]["places"], by[ONE]["at"]) == (1, 1, _anchor(S)) and (by[ALL]["lines"], by[ALL]["places"]) == (8, 2)   # 같은 사례는 자리가 여럿이어도 하나
    assert [(x["n"], x["key"], x["lines"]) for x in by[ALL]["levels"]] == [(5, "□", 2), (6, "o", 2), (7, "-", 2), (8, "·", 2)]

    store = {"version": 3, "cases": {ALL: {"mode": "edit", "levels": [{"letter": "▪", "like": None, "lead": None}, None, {"letter": None, "like": {"template": "body:N.›N-N.›o", "level": 1}, "lead": None},
                                                                      {"letter": None, "like": {"template": "body:없는 템플릿", "level": 1}, "lead": 2}]}}}
    v = MO.view(cases, store, tg, to)
    assert v["version"] == 3 and [t["anchor"] for t in v["templates"]] == [t["anchor"] for t in MO.templates(tg, to)]
    one, deep = {c["key"]: c for c in v["cases"]}[ONE], {c["key"]: c for c in v["cases"]}[ALL]
    assert (one["mode"], one["template"], one["to"]["chain"], one["to"]["level"], one["to"]["template"]) == ("cover", None, ["[…]", "□", "o", "-"], 4, TO_TPL)
    assert [(x["letter"], x["like"], x["clash"], x["missing"]) for x in one["levels"]] == [(None, None, False, False)] and one["levels"][0]["was"]
    assert deep["mode"] == "edit" and [(x["letter"], x["clash"], x["missing"], x["lead"]) for x in deep["levels"]] == [("▪", False, False, None), (None, True, False, None), (None, False, False, None), (None, False, True, 2)]
    assert deep["levels"][2]["like"]["letter"] and deep["levels"][3]["like"] == {"template": "body:없는 템플릿", "level": 1, "letter": "", "text": ""}   # 「o」 는 자리 템플릿 L3 과 같은 레터(clash) · 없는 본보기는 missing
    cover = {c["key"]: c for c in MO.view(cases, {"version": 0, "cases": {}}, tg, to)["cases"]}[ALL]
    assert [x["clash"] for x in cover["levels"]] == [True, True, True, False]   # 덮은 그대로 — □·o·- 가 윗 레벨과 겹친다


def test_refit_reshapes_inserted_lines_and_restores_the_source_shape(S):
    fg, tg = S["from"]["graph"], S["to"]["graph"]
    src, anchor = _src(S), _anchor(S, leaf=True)
    to, frm, letters = _docs(S, src)
    new = to.insert_after(anchor, [{"kind": "copy", "srcId": s} for s in src], src=frm)
    res = MC.converter(to, tg, fg)(anchor, list(zip(src, new)))   # 덮은 그대로 넣음 — 네 줄 모두 넘친 줄로 적힌다
    rec, ids = res["over"], [x["id"] for x in res["over"]["lines"]]
    before = {i: (to._text(to._ids[i]), to.para_attrs(i)) for i in ids}
    assert rec["key"] == ALL and [x["over"] for x in rec["lines"]] == [1, 2, 3, 4] and MO.alive(to, [rec]) == {ALL: 4}
    assert MO.refit(to, [rec], {})["lines"] == 0 and {i: (to._text(to._ids[i]), to.para_attrs(i)) for i in ids} == before   # 선택이 없으면 할 일도 없다

    specs = MO.resolve({ALL: {"mode": "edit", "levels": [{"letter": "(5)", "like": None, "lead": None}, {"letter": None, "like": {"template": TO_TPL, "level": 4}, "lead": None}, None, {"letter": "▪", "like": None, "lead": 9}]}}, tg)
    like = specs[ALL][1]["like"]
    out = MO.refit(to, [rec], specs)
    text = lambda i: to._text(to._ids[i])  # noqa: E731
    assert out["lines"] == 3 and out["kept"] == {} and out["ids"] == [ids[0], ids[1], ids[3]] and rec["lines"][0]["letter"] == letters[src[0]]   # 받은 기록은 안 고친다
    assert prefix_of(text(ids[0]), "(1)")[1] == "(1)" and to.para_attrs(ids[0]) == before[ids[0]][1]   # 번호형 레터 — 처음부터 · 제 모양 그대로
    assert to.para_attrs(ids[1]) == to.para_attrs(like) and prefix_of(text(ids[1]), specs[ALL][1]["likeLetter"])[1]   # 본보기의 모양
    assert text(ids[2]) == before[ids[2]][0] and text(ids[3]).startswith(" " * 9 + "▪") and to.para_attrs(ids[3]) == before[ids[3]][1]
    assert [body_of(text(i), x["letter"]) for i, x in zip(ids, out["records"][0]["lines"])] == [body_of(before[i][0], x["was"]) for i, x in zip(ids, rec["lines"])]   # 글은 그대로
    assert [x["letter"] for x in out["records"][0]["lines"]] == ["(1)", specs[ALL][1]["likeLetter"], letters[next(s for s, n in zip(src, new) if n == ids[2])], "▪"]

    again = MO.refit(to, out["records"], specs)   # 같은 선택으로 한 번 더 — 바꿀 것이 없다
    assert again["lines"] == 0 and again["kept"] == {}
    to.set_text(ids[3], "사람이 첫머리를 고친 줄")
    to.delete_blocks(ids[1], ids[1])
    back = MO.refit(to, out["records"], {})   # 덮은 그대로로 — 원본 접두·모양을 되살린다(고친 줄·없는 줄은 건너뜀)
    assert back["lines"] == 1 and back["kept"] == {"gone": 1, "edited": 1} and (text(ids[0]), to.para_attrs(ids[0])) == before[ids[0]]
    assert back["records"][0]["lines"][0]["letter"] == letters[src[0]] and MO.alive(to, back["records"]) == {ALL: 3}
    only = MO.refit(to, back["records"], specs, only="다른 사례")
    assert only["lines"] == 0 and only["kept"] == {}


def test_refit_finds_the_line_after_an_undo_by_the_letters_it_wrote(S):
    fg, tg = S["from"]["graph"], S["to"]["graph"]
    src, anchor = _src(S), _anchor(S)
    to, frm, letters = _docs(S, src)
    new = to.insert_after(anchor, [{"kind": "copy", "srcId": s} for s in src], src=frm)
    rec = MC.converter(to, tg, fg)(anchor, list(zip(src, new)))["over"]
    nid = rec["lines"][0]["id"]
    a = MO.refit(to, [rec], {ONE: [{"like": None, "letter": "▪", "lead": None, "numbered": False}]})
    b = MO.refit(to, a["records"], {ONE: [{"like": None, "letter": "◆", "lead": None, "numbered": False}]})
    assert to._text(to._ids[nid]).lstrip().startswith("◆") and b["records"][0]["lines"][0]["seen"] == ["▪"]
    lead, tok, gap = prefix_of(to._text(to._ids[nid]), "◆")
    to.replace_prefix(nid, len(lead) + len(tok) + len(gap), lead + "▪" + gap)   # 실행 취소를 흉내 — 문서는 앞 모양(▪)인데 기록의 지금 레터는 ◆
    c = MO.refit(to, b["records"], {})
    assert c["lines"] == 1 and c["kept"] == {} and to._text(to._ids[nid]).lstrip().startswith(letters[rec["lines"][0]["src"]])


def test_refit_keeps_the_written_number_for_gather_records(S):
    """취합의 기록(keepNumbers)은 다시 맞출 때도 같은 번호 꼴이면 기관이 쓴 번호를 둔다 — 이관의 기록은 부모마다 처음부터 다시 매긴다."""
    fg, tg = S["from"]["graph"], S["to"]["graph"]
    src, anchor = _src(S), _anchor(S)
    to, frm, _ = _docs(S, src)
    new = to.insert_after(anchor, [{"kind": "copy", "srcId": s} for s in src], src=frm)
    rec = MC.converter(to, tg, fg)(anchor, list(zip(src, new)))["over"]
    line = rec["lines"][0]
    to.set_text(line["id"], "  (3) 기관이 쓴 번호 줄")   # 넣은 줄이 번호 줄이었다고 놓는다(기록도 그렇게)
    line.update(was="(3)", letter="(3)", orig={**line["orig"], "prefix": "  (3) "})
    spec = {ONE: [{"like": None, "letter": "(1)", "lead": None, "numbered": True}]}
    kept = MO.refit(to, [{**rec, "keepNumbers": True}], spec)
    assert kept["lines"] == 0 and to._text(to._ids[line["id"]]) == "  (3) 기관이 쓴 번호 줄"
    again = MO.refit(to, [rec], spec)
    assert again["lines"] == 1 and to._text(to._ids[line["id"]]) == "  (1) 기관이 쓴 번호 줄" and again["records"][0]["lines"][0]["seen"] == []


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js 가 없다")
def test_screen_helpers_build_the_put_body():
    """화면(app/static/merge_over.js)의 글·PUT 바디 — DOM 없이 도는 함수만(Node.js)."""
    script = "const fs=require('fs');global.window=global;eval(fs.readFileSync(process.argv[1],'utf8')+';globalThis.__mo={mergeOverBody,mergeOverCaseText,mergeOverDraft,mergeOverLevelText,MERGE_OVER_MODE}');" \
             "const c=JSON.parse(process.argv[2]);const d=__mo.mergeOverDraft(c,JSON.parse(process.argv[3]));" \
             "console.log(JSON.stringify({text:__mo.mergeOverCaseText(c),draft:d,edit:__mo.mergeOverBody(c,{...d,mode:'edit'}),tpl:__mo.mergeOverBody(c,{mode:'template',template:{template:'body:o›-',level:1},levels:[]})," \
             "cover:__mo.mergeOverBody(c,{mode:'cover',levels:[]}),level:c.levels.map(__mo.mergeOverLevelText),modes:Object.keys(__mo.MERGE_OVER_MODE)}))"
    case = {"key": ALL, "to": {"template": TO_TPL, "no": 3, "chain": ["[…]", "□", "o", "-"], "level": 4}, "tail": ["□", "o", "-", "·"], "lines": 8, "places": 2, "mode": "edit", "template": None, "under": [],
            "levels": [{"n": 5, "key": "□", "was": "□", "lines": 2, "letter": "▪", "like": None, "lead": None, "clash": False, "missing": False},
                       {"n": 6, "key": "o", "was": "o", "lines": 2, "letter": None, "like": {"template": "body:o›-", "level": 2, "letter": "-", "text": ""}, "lead": 4, "clash": True, "missing": False},
                       {"n": 7, "key": "-", "was": "-", "lines": 2, "letter": None, "like": None, "lead": None, "clash": True, "missing": False}]}
    tpls = [{"anchor": "body:o›-", "no": 2, "kind": "branch", "chain": ["o", "-"], "levels": [{"level": 1, "key": "o", "letter": "ㅇ", "text": "", "rep": "p1", "ok": True}, {"level": 2, "key": "-", "letter": "-", "text": "", "rep": "p2", "ok": True}]}]
    out = json.loads(subprocess.run(["node", "-e", script, str(JS), json.dumps(case, ensure_ascii=False), json.dumps(tpls, ensure_ascii=False)], capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert out["modes"] == ["cover", "edit", "template"] and "[…] › □ › o › -" in out["text"] and "□ › o › -" in out["text"]
    assert out["edit"] == {"key": ALL, "mode": "edit", "levels": [{"letter": "▪", "like": None, "lead": None}, {"letter": None, "like": {"template": "body:o›-", "level": 2}, "lead": 4}, None]}
    assert out["tpl"] == {"key": ALL, "mode": "template", "template": {"template": "body:o›-", "level": 1}} and out["cover"] == {"key": ALL, "mode": "cover"}
    assert "▪" in out["level"][0] and "윗 레벨과 같은 레터" in out["level"][1] and "원본 그대로" in out["level"][2]
