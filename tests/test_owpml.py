"""OWPML 검사·구조·서식 편집(spec_owpml_편집 ② §1~§3) — 어댑터 단계와 서버 API."""
import io
import time
import zipfile
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app import hwpx_struct, owpml_check as oc, server, verify
from app.hwpx_doc import HH, HP, HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, PLAN = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "연구개발계획서_양식.hwpx"
SECPR, T, RUN, P = f"{{{HP}}}secPr", f"{{{HP}}}t", f"{{{HP}}}run", f"{{{HP}}}p"


@cache
def _bytes(path):
    return path.read_bytes()


def _doc(path):
    d = HwpxDoc(_bytes(path))
    d.blocks()
    return d


@cache
def _base(path):
    return oc.counts(oc.check_doc(_doc(path)))


def _saved_verdict(d, path):
    """저장본을 다시 열어 문서 전체 판정(원본 대비) + 참조 규칙 위반 목록."""
    again = HwpxDoc(d.save())
    again.adopt_ids(d.id_state())
    res = oc.check_doc(again)
    return oc.verdict(again, _base(path), res), res["rules"]


def _paras(blocks):
    for b in blocks:
        if b["type"] == "paragraph":
            yield b
        for c in b.get("cells", ()):
            yield from _paras(c["blocks"])


def _body_para(d, min_len=20):
    """구역 바로 아래, 개체 없는 글 문단 하나."""
    for sec in d._sections:
        for p in sec.iterchildren(P):
            if p in d._rev and not d._has_object(p) and len(d._text(p).strip()) >= min_len and next(p.iter(SECPR), None) is None:
                return d._rev[p]
    raise AssertionError("본문 글 문단 없음")


# ---------------------------------------------------------------- 검사
@pytest.mark.parametrize("path", [SMALL, PLAN])
def test_original_is_its_own_baseline(path):
    """한글 저장본: 참조 규칙 위반 0, 스키마 위반은 있으나(공개 XSD 와 어긋남) 모두 요소에 붙고 자기 자신과는 「통과」."""
    d = _doc(path)
    res = oc.check_doc(d)
    assert res["rules"] == []
    assert res["schema"] and all(v["el"] is not None for v in res["schema"])
    assert not any(v["kind"][2] == "linesegarray" for v in res["schema"])  # 줄 배치 캐시 = OWPML 밖 한컴 확장 — 검사에서 뺌
    assert oc.verdict(d, oc.counts(res), res)["status"] == "ok"


def test_check_rejects_broken_xml():
    d = _doc(SMALL)
    p = d._ids["p7"]
    etree.SubElement(p, T)  # hp:t 는 hp:run 안에만
    v = oc.verdict(d, _base(SMALL), oc.check_hosts(d, [hwpx_struct.top_host(d, p)]), local=True)
    assert v["status"] == "fail" and any("p/t" in x["kind"] for x in v["new"])
    d = _doc(SMALL)
    d._ids["p7"].find(RUN).set("charPrIDRef", "99999")
    v = oc.verdict(d, _base(SMALL), oc.check_hosts(d, [hwpx_struct.top_host(d, d._ids["p7"])]), local=True)
    assert v["status"] == "fail" and v["rules"] and v["rules"][0]["examples"][0]["block"] == "p7"


def test_accepted_adds_missing_kinds_once():
    """받아들인 종류(세션 owpml_ok)를 기준선에 — 없는 종류만 개수 1 로, 더할 것이 없으면 같은 객체(spec_병합 ② §5-10 「가져온 스키마 위반 종류」)."""
    base = _base(SMALL)
    have = next(iter(base["schema"]))
    assert oc.accepted(base, ()) is base and oc.accepted(base, {have}) is base
    new = ("section", "pic", "inMargin", "", "SCHEMAV_TEST")
    got = oc.accepted(base, {new, have})
    assert got is not base and got["schema"][new] == 1 and got["schema"][have] == base["schema"][have] and got["rules"] is base["rules"]
    assert new not in base["schema"]   # 원본 기준선은 그대로


# ---------------------------------------------------------------- 나누기·합치기
def test_split_and_merge_in_cell():
    d = _doc(SMALL)
    text = d._text(d._ids["p7"])
    new = d.split_para("p7", 3)
    assert (d._text(d._ids["p7"]), d._text(d._ids[new])) == (text[:3], text[3:])
    assert d._ids[new].getparent() is d._ids["p7"].getparent()
    v, rules = _saved_verdict(d, SMALL)
    assert v["status"] != "fail" and not rules, v
    r = d.merge_paras("p7")
    assert r == {"id": "p7", "offset": 3, "removed": new} and d._text(d._ids["p7"]) == text
    assert len(list(d._ids["p7"].iterchildren(RUN))) == 1  # 나눴던 런이 다시 하나로
    assert _saved_verdict(d, SMALL)[0]["status"] != "fail"


def test_split_keeps_tabs_breaks_and_run_shapes():
    d = _doc(SMALL)
    d.set_text("p7", "가나\t다라 마바")
    d.format_chars("p7", 0, 2, {"bold": True})
    new = d.split_para("p7", 4)  # 「가나⇥다」 | 「라↵마바」
    assert d._text(d._ids["p7"]) == "가나\t다" and d._text(d._ids[new]) == "라 마바"
    assert d._ids["p7"].find(f".//{{{HP}}}tab") is not None and d._ids[new].find(f".//{{{HP}}}lineBreak") is not None
    runs = [b for b in _paras(d.blocks()) if b["id"] == "p7"][0]["runs"]
    assert [(r["text"], r["format"]["bold"]) for r in runs] == [("가나", True), ("\t다", False)]
    assert _saved_verdict(d, SMALL)[0]["status"] != "fail"


def test_split_at_edges_keeps_section_settings():
    """구역 첫 문단을 맨 앞에서 나눠도 secPr 는 앞(첫) 문단에 남고, 글 끝에서 나누면 빈 새 문단이 뒤에 생긴다."""
    d = _doc(PLAN)
    first = next(p for sec in d._sections for p in [next(sec.iterchildren(P))] if d._text(p).strip() and p in d._rev)
    pid, text = d._rev[first], d._text(first)
    new = d.split_para(pid, 0)
    assert d._text(first) == "" and d._text(d._ids[new]) == text
    assert next(first.iter(SECPR), None) is not None and next(d._ids[new].iter(SECPR), None) is None
    assert d.merge_paras(pid)["offset"] == 0 and d._text(first) == text
    end = d.split_para(pid, len(text))
    assert d._text(d._ids[end]) == "" and d._ids[end].find(f"{RUN}/{T}") is not None
    v, rules = _saved_verdict(d, PLAN)
    assert v["status"] != "fail" and not rules, (v, rules)


def test_merge_refusals():
    d = _doc(SMALL)
    with pytest.raises(ValueError, match="다음 문단이 없습니다"):
        d.merge_paras("p7")  # 칸의 마지막(하나뿐인) 문단
    d = _doc(PLAN)
    host = next(p for sec in d._sections for p in sec.iterchildren(P) if d._has_object(p) and p.getprevious() is not None
                and p.getprevious().tag == P and not d._has_object(p.getprevious()))
    with pytest.raises(ValueError, match="개체"):
        d.merge_paras(d._id(host.getprevious()))


# ---------------------------------------------------------------- 글자·문단 모양
def test_format_chars_range_toggle_and_back():
    d = _doc(SMALL)
    orig_cid, n0 = d._ids["p7"].find(RUN).get("charPrIDRef"), len(d._defs["charPr"])
    text = d._text(d._ids["p7"])
    d.format_chars("p7", 1, 3, {"bold": "toggle", "color": "#C00000"})
    runs = [b for b in _paras(d.blocks()) if b["id"] == "p7"][0]["runs"]
    assert [(r["text"], r["format"]["bold"], r["format"]["color"]) for r in runs] == [
        (text[:1], False, "#000000"), (text[1:3], True, "#C00000"), (text[3:], False, "#000000")]
    assert len(d._defs["charPr"]) == n0 + 1  # 새 charPr 하나(itemCnt 갱신)
    v, rules = _saved_verdict(d, SMALL)
    assert v["status"] != "fail" and not rules
    d.format_chars("p7", 1, 3, {"bold": "toggle", "color": "#000000"})
    runs = list(d._ids["p7"].iterchildren(RUN))
    assert len(runs) == 1 and runs[0].get("charPrIDRef") == orig_cid  # 같은 정의를 다시 찾아 런도 다시 하나


def test_format_chars_empty_range_is_whole_paragraph():
    d = _doc(SMALL)
    d.format_chars("p7", 2, 2, {"sizePt": 14, "underline": True})
    b = [b for b in _paras(d.blocks()) if b["id"] == "p7"][0]
    assert b["format"]["sizePt"] == 14 and b["format"]["underline"] and b["runs"] is None
    with pytest.raises(ValueError):
        d.format_chars("p7", 0, 1, {"font": "굴림"})


def test_format_para_keeps_runs_and_numbering():
    d = _doc(PLAN)
    # 이 양식은 □·o·- 를 글로 쓰고 문단 번호(heading)는 안 쓴다 — 런이 여럿인 문단으로, heading 은 있는 그대로 비교
    b = next(b for b in _paras(d.blocks()) if b.get("runs") and b["format"].get("align") != "center")
    p = d._ids[b["id"]]
    runs_before = [r.get("charPrIDRef") for r in p.iterchildren(RUN)]
    head_before = dict(d._heading(p).attrib) if d._heading(p) is not None else None
    assert d.format_para([b["id"]], {"align": "center", "indentLeftMm": 10, "lineSpacingPct": 150}) == [b["id"]]
    f = d.get_format(b["id"])["summary"]
    assert (f["align"], f["indentLeftMm"], f["lineSpacingPct"]) == ("center", 10.0, 150)
    assert [r.get("charPrIDRef") for r in p.iterchildren(RUN)] == runs_before
    assert (dict(d._heading(p).attrib) if d._heading(p) is not None else None) == head_before
    pp = d._defs["paraPr"][p.get("paraPrIDRef")]
    sw = pp.find(f"{{{HP}}}switch")
    if sw is not None:  # hp:case = HWPUNIT, hp:default = ×2
        lefts = [int(c.find(f"{{{HH}}}margin/{{http://www.hancom.co.kr/hwpml/2011/core}}left").get("value")) for c in sw]
        assert lefts == [round(10 * 7200 / 25.4), round(10 * 7200 / 25.4 * 2)]
    assert _saved_verdict(d, PLAN)[0]["status"] != "fail"


# ---------------------------------------------------------------- 표
def _clean_cell(d, min_rows=1):
    """병합이 걸치지 않는 행·열의 1×1 칸 -> (표 id, 칸 안 첫 문단 id, 격자 칸) — 문서 앞 표부터."""
    for tbl in (e for sec in d._sections for e in sec.iter(f"{{{HP}}}tbl")):
        _, cells, nr, nc = d._tgrid(tbl)
        rows_ok = {r for r in range(nr) if all(not (x.r <= r < x.r + x.rs) or x.rs == 1 for x in cells)}
        cols_ok = {c for c in range(nc) if all(not (x.c <= c < x.c + x.cs) or x.cs == 1 for x in cells)}
        x = next((x for x in cells if x.rs == x.cs == 1 and x.r in rows_ok and x.c in cols_ok), None)
        if x is not None and nr >= min_rows:
            return d._id(tbl), d._id(next(x.el.iter(P))), x
    raise AssertionError("병합 안 걸친 칸이 있는 표 없음")


def test_table_rows_and_cols_keep_grid_and_width():
    d = _doc(SMALL)
    tid, pid, x = _clean_cell(d)
    tbl = d._ids[tid]
    nr, nc, width = int(tbl.get("rowCnt")), int(tbl.get("colCnt")), tbl.find(f"{{{HP}}}sz").get("width")
    text = d._text(d._ids[pid])
    d.table_edit(pid, "row_below")
    assert int(tbl.get("rowCnt")) == nr + 1 and len(tbl.findall(f"{{{HP}}}tr")) == nr + 1
    d.table_edit(pid, "col_left")
    assert int(tbl.get("colCnt")) == nc + 1 and tbl.find(f"{{{HP}}}sz").get("width") == width
    cell = d._ids[pid].getparent().getparent()  # 글은 오른쪽(사본 자리)으로 — 같은 문단 id
    assert d._text(d._ids[pid]) == text and int(cell.find(f"{{{HP}}}cellAddr").get("colAddr")) == x.c + 1
    left = [tc for tc in tbl.iter(f"{{{HP}}}tc") if tc.find(f"{{{HP}}}cellAddr").get("colAddr") == str(x.c)
            and tc.find(f"{{{HP}}}cellAddr").get("rowAddr") == str(x.r)]
    assert left and not "".join(d._text(p) for p in left[0].iter(P)).strip()
    v, rules = _saved_verdict(d, SMALL)
    assert v["status"] != "fail" and not rules, (v, rules)

    def para_at(r, c):
        tc = next(tc for tc in tbl.iterchildren(f"{{{HP}}}tr") for tc in tc.iterchildren(f"{{{HP}}}tc")
                  if (tc.find(f"{{{HP}}}cellAddr").get("rowAddr"), tc.find(f"{{{HP}}}cellAddr").get("colAddr")) == (str(r), str(c)))
        return d._id(next(tc.iter(P)))
    d.table_edit(para_at(x.r, x.c), "col_delete")       # 왼쪽에 넣은 빈 열
    d.table_edit(para_at(x.r + 1, x.c), "row_delete")   # 아래에 넣은 빈 행
    assert (int(tbl.get("rowCnt")), int(tbl.get("colCnt"))) == (nr, nc) and d._text(d._ids[pid]) == text
    assert tbl.find(f"{{{HP}}}sz").get("width") == width
    assert not _saved_verdict(d, SMALL)[1]


def test_table_refusals():
    d = _doc(SMALL)
    with pytest.raises(ValueError, match="모든 행"):
        d.table_edit("p3", "row_delete")  # 1행 표
    with pytest.raises(ValueError, match="표 칸 안이 아닙니다"):
        d.table_edit("t1", "row_below")  # 표 자체(최상위 표 — 바깥에 칸 없음)
    plan = _doc(PLAN)
    with pytest.raises(ValueError, match="표 칸 안이 아닙니다"):
        plan.table_edit(_body_para(plan), "row_below")


def test_table_range_ops_use_the_dragged_cells():
    # 끌어 고른 칸 묶음(range, 격자 좌표)이 그 칸 대신 행·열 기준이 된다 — 아래에 넣은 빈 행은 같은 구조라 두 행 범위가 병합에 안 걸림
    d = _doc(SMALL)
    tid, pid, x = _clean_cell(d)
    tbl = d._ids[tid]
    nr, nc, width = int(tbl.get("rowCnt")), int(tbl.get("colCnt")), tbl.find(f"{{{HP}}}sz").get("width")
    d.table_edit(pid, "row_below")
    d.table_edit(pid, "row_below", {"r0": x.r, "c0": x.c, "r1": x.r + 1, "c1": x.c})
    assert int(tbl.get("rowCnt")) == nr + 3
    d.table_edit(pid, "row_delete", {"r0": x.r + 1, "c0": x.c, "r1": x.r + 3, "c1": x.c})
    assert int(tbl.get("rowCnt")) == nr
    d.table_edit(pid, "col_right", {"r0": x.r, "c0": x.c, "r1": x.r, "c1": x.c})
    assert int(tbl.get("colCnt")) == nc + 1 and tbl.find(f"{{{HP}}}sz").get("width") == width
    d.table_edit(pid, "col_delete", {"r0": x.r, "c0": x.c + 1, "r1": x.r, "c1": x.c + 1})
    assert int(tbl.get("colCnt")) == nc and tbl.find(f"{{{HP}}}sz").get("width") == width
    with pytest.raises(ValueError, match="표 밖"):
        d.table_edit(pid, "row_below", {"r0": 0, "c0": 0, "r1": nr, "c1": 0})
    with pytest.raises(ValueError, match="표 밖"):
        d.table_edit(pid, "row_below", {"r0": 1, "c0": 0, "r1": 0, "c1": 0})  # 뒤집힌 범위
    with pytest.raises(ValueError, match="range"):
        d.table_edit(pid, "row_below", {"r0": "a"})
    assert not _saved_verdict(d, SMALL)[1]


# ---------------------------------------------------------------- 실행 취소 묶음
def test_snapshot_restore_keeps_original_baseline():
    data = _bytes(SMALL)
    d = HwpxDoc(data)
    d.blocks()
    clean = hwpx_struct.snapshot(d)
    d.set_text("p3", "별첨 수정")
    mid = hwpx_struct.snapshot(d)
    d.split_para("p7", 2)
    back = hwpx_struct.restore(HwpxDoc, data, mid)
    assert back.save() == mid["bytes"] and back._data is data  # 기준은 원본 — 원본 복원·바이트 동일 판정이 계속 맞다
    assert back._text(back._ids["p3"]) == "별첨 수정" and len(list(back._ids["p7"].getparent().iterchildren(P))) == 1
    assert hwpx_struct.restore(HwpxDoc, data, clean).save() == data


# ---------------------------------------------------------------- 서버
@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _open(c, path=SMALL):
    return c.post("/api/docs", files={"file": (path.name, path.read_bytes())}).json()["docId"]


def _wait(c, d, kind, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/verify").json()
        if kind in v and not v[kind]["running"]:
            return v
        time.sleep(0.1)
    raise AssertionError("검증이 끝나지 않음")


def test_server_split_merge_undo_roundtrip(client):
    d = _open(client)
    r = client.post(f"/api/docs/{d}/split", json={"id": "p7", "offset": 3})
    assert r.status_code == 200, r.text
    r = r.json()
    new = r["focus"]["id"]
    assert r["owpml"]["status"] in ("ok", "warn") and r["kinds"] == {"p7": "struct", new: "new"}
    assert "t8" in r["tops"]["drop"] or "t1" in r["tops"]["drop"]
    assert {b["id"] for b in r["tops"]["blocks"]} >= {"t1", "t8"}  # 칸 안 편집 = 그 표를 품은 본문 문단의 최상위 블록 전부
    orig = {b["id"]: b["text"] for b in _paras(HwpxDoc(SMALL.read_bytes()).blocks())}
    assert r["texts"]["p7"] + r["texts"][new] == orig["p7"] and len(r["texts"]["p7"]) == 3
    assert r["undo"] == 1 and not r["pristine"]
    # 새 문단에도 글을 쓸 수 있다
    assert client.patch(f"/api/docs/{d}/blocks/{new}", json={"text": "새 글"}).json()["edited"]
    saved = client.get(f"/api/docs/{d}/download").content
    again = HwpxDoc(saved)
    assert "새 글" in [b["text"] for b in _paras(again.blocks())]
    # 합치기(prev) → 실행 취소 두 번이 아니라 한 번(나누기 직전)으로 원본 바이트
    r = client.post(f"/api/docs/{d}/merge", json={"id": new, "dir": "prev"}).json()
    assert r["focus"] == {"id": "p7", "offset": 3} and r["undo"] == 2
    assert new not in r["kinds"] and new not in server.DOCS[d].texts  # 합쳐 지운 새 문단은 남지 않는다(lxml 떼어 낸 요소 판정)
    assert r["kinds"] == {"p7": "struct"}
    client.post(f"/api/docs/{d}/undo")
    g = client.post(f"/api/docs/{d}/undo").json()
    assert g["pristine"] and g["undo"] == 0 and g["edited"] == []
    assert client.get(f"/api/docs/{d}/download").content == SMALL.read_bytes()


def test_server_format_and_table_ops(client):
    d = _open(client)
    r = client.post(f"/api/docs/{d}/format/chars", json={"id": "p7", "start": 1, "end": 3, "changes": {"bold": "toggle"}}).json()
    assert "focus" in r, r
    assert r["focus"] == {"id": "p7", "offset": 1, "end": 3} and r["kinds"]["p7"] == "format"
    r = client.post(f"/api/docs/{d}/format/para", json={"ids": ["p7"], "changes": {"align": "right"}}).json()
    assert r["kinds"]["p7"] == "format"
    # 모양을 바꾼 문단도 「원본으로 되돌리기」 — 원본 문단 XML(런·모양)로
    rv = client.post(f"/api/docs/{d}/blocks/p7/revert").json()
    assert rv["restored"] and not rv["edited"]
    assert client.get(f"/api/docs/{d}/download").content == SMALL.read_bytes()
    doc = HwpxDoc(SMALL.read_bytes())
    doc.blocks()
    tid, pid, _ = _clean_cell(doc)
    rows = int(doc._ids[tid].get("rowCnt"))
    bad = client.post(f"/api/docs/{d}/table", json={"id": "p3", "op": "row_delete"})  # 1행 표(t1)
    assert bad.status_code == 400 and "모든 행" in bad.json()["detail"]
    r = client.post(f"/api/docs/{d}/table", json={"id": pid, "op": "row_above"})
    assert r.status_code == 200, r.text
    tb = next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)
    assert tb["nRows"] == rows + 1 and r.json()["kinds"] and set(r.json()["kinds"].values()) == {"new"}
    x = _clean_cell(doc)[2]
    r = client.post(f"/api/docs/{d}/table", json={"id": pid, "op": "row_below", "range": {"r0": x.r, "c0": x.c, "r1": x.r + 1, "c1": x.c}})
    assert r.status_code == 200, r.text  # 끌어 고른 두 행(원래 칸 + 위에 넣은 빈 행) → 두 행 추가
    assert next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)["nRows"] == rows + 3
    bad = client.post(f"/api/docs/{d}/table", json={"id": pid, "op": "row_delete", "range": {"r0": 0, "c0": 0, "r1": 99, "c1": 0}})
    assert bad.status_code == 400 and "표 밖" in bad.json()["detail"]
    # 기준 칸 자신의 행을 지움 — 기준 문단이 사라져도 응답·검사 대상은 표를 품은 본문 문단(tops 에 표가 있고, 잠금 밖 재조회 없음 — astra P1 2026-11-10)
    r = client.post(f"/api/docs/{d}/table", json={"id": pid, "op": "row_delete"})
    assert r.status_code == 200, r.text
    assert next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)["nRows"] == rows + 2
    assert r.json()["focus"] is None and pid not in r.json()["texts"] and r.json()["kinds"].get(pid) == "removed"


def test_server_rejects_non_owpml_edit_and_rolls_back(client, monkeypatch):
    d = _open(client)
    real = HwpxDoc.split_para

    def broken(self, block_id, offset):
        new = real(self, block_id, offset)
        etree.SubElement(self._ids[new], T)  # hp:p 바로 아래 hp:t — OWPML 위반
        return new
    monkeypatch.setattr(HwpxDoc, "split_para", broken)
    r = client.post(f"/api/docs/{d}/split", json={"id": "p7", "offset": 2})
    assert r.status_code == 422 and "OWPML" in r.json()["detail"] and r.json()["owpml"]["new"]
    g = client.get(f"/api/docs/{d}").json()
    assert g["undo"] == 0 and g["pristine"]
    assert client.get(f"/api/docs/{d}/download").content == SMALL.read_bytes()


def test_verify_steps_after_structural_edits(client):
    d = _open(client)
    v = _wait(client, d, "import")
    st = {s["key"]: s for s in v["import"]["steps"]}
    assert st["owpml"]["status"] == "ok", st["owpml"]
    new = client.post(f"/api/docs/{d}/split", json={"id": "p7", "offset": 3}).json()["focus"]["id"]
    client.patch(f"/api/docs/{d}/blocks/{new}", json={"text": "나눈 뒤 고친 글"})
    client.post(f"/api/docs/{d}/format/chars", json={"id": "p3", "start": 0, "end": 1, "changes": {"italic": True}})
    doc = HwpxDoc(SMALL.read_bytes())
    doc.blocks()
    client.post(f"/api/docs/{d}/table", json={"id": _clean_cell(doc)[1], "op": "col_right"})
    assert client.post(f"/api/docs/{d}/verify", json={"kind": "edit"}).status_code == 200
    v = _wait(client, d, "edit")
    st = {s["key"]: s for s in v["edit"]["steps"]}
    assert st["epackage"]["status"] == "ok", st["epackage"]
    assert st["eowpml"]["status"] in ("ok", "warn"), st["eowpml"]
    assert client.get(f"/api/docs/{d}/owpml").json()["status"] in ("ok", "warn")
