"""표 매핑 규칙의 저장(spec_테이블매니저 ② §7 「키-값 추출과 매핑」 — 「매핑 규칙」 · app/table_maps.py): 묶음 만들기 · 고치기(기대 version) · 표 타입의 짝으로 찾기(같은 타입끼리도) · 지우기 · 파일/메모리 · 손상 파일."""
import json

import pytest

from app import heading_rules as R
from app import table_maps as M

FA, FB, FC = "a" * 12, "b" * 12, "c" * 12


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    M._MEMORY.clear()
    yield
    M._MEMORY.clear()


def _bundle(a=FA, b=FB, **kw):
    return {"from": {"type": a, "label": "계획서 표"}, "to": {"type": b, "label": "보고서 표"}, "alias": [{"from": "1차년도", "to": "1년차"}],
            "pairs": [{"from": "재료비|1차년도›현금", "to": "연구재료비|1년차›현금", "fromLabel": "재료비 | 1차년도 › 현금", "toLabel": "연구재료비 | 1년차 › 현금"}], **kw}


def test_put_makes_a_bundle_and_saves_it_in_the_headings_folder(tmp_path):
    assert M.list() == [] and M.find(FA, FB) is None
    m = M.put(_bundle())
    assert M._ID.match(m["id"]) and m["version"] == 1 and m["updated"] and m["name"] == "계획서 표 → 보고서 표"
    assert m["from"] == {"type": FA, "label": "계획서 표"} and m["alias"] == [{"from": "1차년도", "to": "1년차"}] and m["pairs"][0]["toLabel"] == "연구재료비 | 1년차 › 현금"
    saved = json.loads((tmp_path / "heads" / M.FILE).read_text(encoding="utf-8"))
    assert saved["version"] == M.VERSION and list(saved["maps"]) == [m["id"]] and saved["maps"][m["id"]]["alias"] == m["alias"]
    assert M.find(FA, FB) == m and M.get(m["id"]) == m and M.list() == [m]
    assert M.find(FB, FA) is None and M.find(FA, FC) is None and M.find(None, FB) is None       # 방향이 있다 — 거꾸로 짝은 다른 묶음
    back = M.put(_bundle(FB, FA, name="  거꾸로   읽기 ", alias=[], pairs=[]))
    assert back["id"] != m["id"] and back["name"] == "거꾸로 읽기" and back["alias"] == [] and {x["id"] for x in M.list()} == {m["id"], back["id"]}


def test_same_type_to_same_type_is_one_pair_too():
    other = M.put(_bundle())
    same = M.put(_bundle(FA, FA, alias=[{"from": "1차년도", "to": "2차년도"}], pairs=[]))   # 같은 타입이어도 키는 다를 수 있다(「1차년도 › 현금」 ↔ 「2차년도 › 현금」)
    assert same["from"]["type"] == same["to"]["type"] == FA and same["id"] != other["id"] and same["version"] == 1
    assert M.find(FA, FA)["id"] == same["id"] and M.find(FA, FB)["id"] == other["id"] and M.find(FB, FB) is None
    with pytest.raises(M.StaleVersion):
        M.put(_bundle(FA, FA))                                        # 같은 타입끼리의 짝도 하나뿐 — version 없이 덮지 않는다
    again = M.put(_bundle(FA, FA, version=1, alias=[], pairs=[{"from": "a|", "to": "b|"}]))
    assert again["id"] == same["id"] and again["version"] == 2 and len(M.list()) == 2


def test_put_changes_only_with_the_expected_version():
    m = M.put(_bundle())
    with pytest.raises(R.StaleVersion):
        M.put(_bundle())                                              # 그 짝의 묶음이 이미 있다 — version 없이 덮지 않는다
    with pytest.raises(M.StaleVersion):
        M.put(_bundle(id=m["id"], version=3))
    with pytest.raises(ValueError):
        M.put(_bundle(id=m["id"], version="x"))
    new = M.put(_bundle(version=1, name="새 이름", alias=[{"from": "1차년도", "to": "1년차"}, {"from": "2차년도", "to": "2년차"}]))   # id 없이도 같은 짝이면 그 묶음
    assert (new["id"], new["version"], new["name"], len(new["alias"])) == (m["id"], 2, "새 이름", 2) and len(M.list()) == 1
    moved = M.put({**_bundle(FC, FA), "id": m["id"], "version": 2, "from": {"type": FC, "label": ""}})   # 고칠 때 두 표의 타입은 그대로 · 빈 이름은 전 이름
    assert moved["from"] == {"type": FA, "label": "계획서 표"} and moved["to"]["type"] == FB and moved["version"] == 3
    with pytest.raises(KeyError):
        M.put(_bundle(id="m0000000000", version=1))
    gone = M.delete(m["id"])
    assert gone["id"] == m["id"] and M.list() == [] and M.find(FA, FB) is None
    with pytest.raises(KeyError):
        M.delete(m["id"])
    with pytest.raises(M.StaleVersion):
        M.put(_bundle(version=3))                                     # 지워진 묶음을 고치려 함
    assert M.put(_bundle())["version"] == 1


@pytest.mark.parametrize("patch", [
    {"from": {"type": "zz", "label": "x"}}, {"from": None}, {"to": {"form": FB, "label": "x"}},   # 타입 꼴이 아님 · 없음 · 옛 이름(form)
    {"alias": [{"from": "a", "to": "a"}]}, {"alias": [{"from": "a", "to": "b"}, {"from": " a ", "to": "c"}]}, {"alias": [{"from": "", "to": "b"}]}, {"alias": "x"},
    {"pairs": [{"from": "k|", "to": ""}]}, {"pairs": [{"from": "k|", "to": "a|"}, {"from": "k|", "to": "b|"}]}, {"pairs": [3]},
    {"name": "가" * 61}, {"id": "nope"},
])
def test_put_refuses_bad_bundles(patch):
    with pytest.raises(ValueError):
        M.put(_bundle(**patch))
    assert M.list() == []


def test_memory_when_the_store_is_off(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_HEADINGS", "off")
    m = M.put(_bundle())
    assert M.find(FA, FB)["id"] == m["id"] and not (tmp_path / "heads").exists()
    m["alias"].clear()
    assert M.find(FA, FB)["alias"]                                    # 돌려준 묶음을 고쳐도 저장소는 그대로
    M.delete(m["id"])
    assert M.list() == []


def test_broken_file_reads_empty_and_is_not_overwritten(tmp_path):
    p = tmp_path / "heads" / M.FILE
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    assert M.list() == [] and M.find(FA, FB) is None
    with pytest.raises(M.Broken):
        M.put(_bundle())
    with pytest.raises(M.Broken):
        M.delete("m0000000000")
    assert p.read_text(encoding="utf-8") == "{not json"
    p.write_text(json.dumps({"version": 99, "maps": {}}), encoding="utf-8")   # 모르는 판도 손상으로 본다
    with pytest.raises(M.Broken):
        M.put(_bundle())


# ---- 꺼 둔 값(같은 사양서 ② §7 의 「구분 기준의 값 고르기」 — 「꺼 둔 값을 기억한다」): 표 타입마다 · 규칙 묶음과 따로 ----------------------------------

def test_offs_are_saved_per_table_type_in_the_same_file(tmp_path):
    from app import table_kv
    assert M.OFF_BASES == table_kv.BASES                              # 기준의 이름은 추출 쪽과 같다(이 모듈은 table_kv 를 부르지 않는다)
    assert M.get_offs(FA) == {} and M.get_offs(None) == {} and M.get_offs("zz") == {}
    got = M.put_offs(FA, {"year": ["2026", "2028", "2026"], "org": []})          # 같은 조각은 한 번 · 빈 기준은 뺀다
    assert got == {"year": ["2026", "2028"]} and M.get_offs(FA) == got and M.get_offs(FB) == {}
    saved = json.loads((tmp_path / "heads" / M.FILE).read_text(encoding="utf-8"))
    assert saved == {"version": M.VERSION, "maps": {}, "offs": {FA: {"year": ["2026", "2028"]}}}
    assert M.put_offs(FA, {"org": ["주관 연구개발기관"], "year": ["2027"]}) == {"year": ["2027"], "org": ["주관 연구개발기관"]}   # 통째로 바꾼다 · 기준은 정해진 차례 · 조각의 글은 그대로
    got["year"].clear()
    assert M.get_offs(FA)["year"] == ["2027"]                         # 돌려준 것을 고쳐도 저장소는 그대로


def test_offs_empty_removes_the_type(tmp_path):
    M.put_offs(FA, {"year": ["2026"]})
    M.put_offs(FB, {"stage": ["1단계"]})
    assert M.put_offs(FA, {}) == {} and M.get_offs(FA) == {} and M.get_offs(FB) == {"stage": ["1단계"]}
    assert M.put_offs(FB, {"stage": [], "year": []}) == {} and M.put_offs(FB, None) == {}
    p = tmp_path / "heads" / M.FILE
    assert json.loads(p.read_text(encoding="utf-8"))["offs"] == {}
    at = p.stat().st_mtime_ns
    assert M.put_offs(FC, {}) == {} and p.stat().st_mtime_ns == at    # 지울 것이 없으면 파일을 다시 쓰지 않는다


@pytest.mark.parametrize("table_type, offs", [
    ("zz", {"year": ["2026"]}), (None, {"year": ["2026"]}), (FA.upper(), {"year": ["2026"]}),      # 타입 꼴이 아님
    (FA, ["2026"]), (FA, {"month": ["1월"]}), (FA, {"year": "2026"}), (FA, {"year": [2026]}), (FA, {"year": [""]}),
    (FA, {"year": ["가" * 1001]}), (FA, {"year": [str(i) for i in range(201)]}),
])
def test_put_offs_refuses_bad_shapes(table_type, offs):
    with pytest.raises(ValueError):
        M.put_offs(table_type, offs)
    assert M.load()["offs"] == {}


def test_offs_and_bundles_do_not_touch_each_other(tmp_path):
    m = M.put(_bundle())
    M.put_offs(FB, {"year": ["2026"]})
    assert M.find(FA, FB)["version"] == 1 and M.find(FA, FB)["alias"] == m["alias"]            # 꺼 둔 값을 저장해도 묶음은 그대로(판도)
    m2 = M.put({**_bundle(), "id": m["id"], "version": 1, "name": "새 이름"})
    assert m2["version"] == 2 and M.get_offs(FB) == {"year": ["2026"]}                          # 묶음을 고쳐도 꺼 둔 값은 그대로
    M.put_offs(FB, {})
    assert [b["id"] for b in M.list()] == [m["id"]] and M.find(FA, FB)["name"] == "새 이름"
    M.put_offs(FB, {"org": ["한국선급"]})
    M.delete(m["id"])
    assert M.list() == [] and M.get_offs(FB) == {"org": ["한국선급"]}                           # 묶음을 지워도
    saved = json.loads((tmp_path / "heads" / M.FILE).read_text(encoding="utf-8"))
    assert saved["maps"] == {} and saved["offs"] == {FB: {"org": ["한국선급"]}}


def test_offs_old_file_memory_and_broken_file(monkeypatch, tmp_path):
    p = tmp_path / "heads" / M.FILE
    m = M.put(_bundle())
    old = json.loads(p.read_text(encoding="utf-8"))
    old.pop("offs")
    p.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")        # `offs` 가 없는 옛 파일 — 빈 것으로 읽고 묶음은 그대로
    assert M.get_offs(FA) == {} and M.find(FA, FB)["id"] == m["id"]
    assert M.put_offs(FA, {"period": ["2027"]}) == {"period": ["2027"]} and M.find(FA, FB)["id"] == m["id"]
    p.write_text(json.dumps({"version": M.VERSION, "maps": {}, "offs": {FA: {"month": ["1월"]}}}), encoding="utf-8")   # 꼴이 틀린 offs = 손상된 파일
    text = p.read_text(encoding="utf-8")
    assert M.get_offs(FA) == {} and M.list() == []
    with pytest.raises(M.Broken):
        M.put_offs(FA, {"year": ["2026"]})
    with pytest.raises(M.Broken):
        M.put(_bundle())
    assert p.read_text(encoding="utf-8") == text                               # 덮지 않는다
    monkeypatch.setenv("NFM_HEADINGS", "off")                                  # 저장이 꺼져 있으면 메모리
    assert M.get_offs(FA) == {} and M.put_offs(FA, {"year": ["2026"]}) == {"year": ["2026"]} and M.get_offs(FA) == {"year": ["2026"]}
    M.put(_bundle())
    assert M.get_offs(FA) == {"year": ["2026"]} and len(M.list()) == 1
    assert M.put_offs(FA, {}) == {} and M.get_offs(FA) == {} and len(M.list()) == 1


# ---- 칸마다 넣는 방식(같은 사양서 ② §7 「칸마다 넣는 방식」): 묶음의 ops ----------------------------------------------------------------------------

def test_bundle_keeps_ops_and_old_bundles_have_none(tmp_path):
    from app import table_kv
    assert M.OPS == table_kv.OPS
    m = M.put(_bundle())
    assert m["ops"] == []                                              # ops 를 안 준 묶음 = 빈 목록
    ops = [{"part": "현금", "op": "add"}, {"key": "연구재료비|1년차›현물", "op": "replace", "label": " 연구재료비 |  1년차 › 현물 "}, {"key": "합계|현금", "op": "fill"}]
    m2 = M.put({**_bundle(), "id": m["id"], "version": 1, "ops": ops})
    assert m2["version"] == 2 and m2["ops"] == [{"part": "현금", "op": "add"}, {"key": "연구재료비|1년차›현물", "op": "replace", "label": "연구재료비 | 1년차 › 현물"}, {"key": "합계|현금", "op": "fill", "label": ""}]
    assert m2["alias"] == m["alias"] and M.find(FA, FB)["ops"] == m2["ops"]
    only = M.put({"from": {"type": FA, "label": "a"}, "to": {"type": FA, "label": "a"}, "ops": [{"part": "현물", "op": "sub"}]})   # 방식만 있는 묶음(같은 타입끼리)
    assert only["alias"] == [] and only["pairs"] == [] and only["ops"] == [{"part": "현물", "op": "sub"}]
    p = tmp_path / "heads" / M.FILE
    old = json.loads(p.read_text(encoding="utf-8"))
    for b in old["maps"].values():
        b.pop("ops")
    p.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")       # `ops` 가 없는 옛 파일
    assert M.find(FA, FB)["ops"] == [] and M.find(FA, FA)["ops"] == []


@pytest.mark.parametrize("ops", [
    "x", [3], [{"part": "현금"}], [{"part": "현금", "op": "mul"}], [{"op": "add"}], [{"part": "현금", "key": "a|현금", "op": "add"}],     # 목록이 아님 · 방식 없음 · 모르는 방식 · 어디에 · 둘 다
    [{"part": "", "op": "add"}], [{"key": 3, "op": "add"}], [{"part": "가" * 1001, "op": "add"}],
    [{"part": "현금", "op": "add"}, {"part": "현금", "op": "sub"}], [{"key": "a|현금", "op": "add"}, {"key": "a|현금", "op": "add"}],   # 같은 머리글 · 같은 칸에 둘
    [{"part": str(i), "op": "add"} for i in range(501)],
])
def test_put_refuses_bad_ops(ops):
    with pytest.raises(ValueError):
        M.put(_bundle(ops=ops))
    assert M.list() == []
