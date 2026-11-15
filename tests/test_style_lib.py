"""서식 보관함 저장소(spec_일반편집 ② §2): 만들기 · revision(물려받기·치우기) · 낡은 revision 409 · 검증 기록 붙이기 · 깨진 파일 · 원자적 쓰기."""
import json
import re
import threading

import pytest

from app import style_lib as L

TABLE = {"kind": "table", "name": "  예산   총괄표 ", "rows": 4, "cols": 3, "bands": {"headerRows": 1, "headerCols": 9, "footRows": 1}, "losses": ["캡션", ""],
         "requirements": {"fonts": ["맑은 고딕", "맑은 고딕", "바탕"]}, "source": {"name": "a.hwpx", "format": "hwpx", "work": "w1", "block": "t3", "junk": 1},
         "preview": {"grid": {"rows": []}, "looks": {}}}
TEXT = {"kind": "text", "name": "본문 글", "items": [{"key": "i1", "name": "□", "level": 1}, {"key": "i2", "name": "o", "level": None}]}


def _root(tmp_path):
    return tmp_path / "styles"


def test_root_enabled_and_off(tmp_path, monkeypatch):
    assert L.enabled() and L.root() == _root(tmp_path) and L.listing() == {"styles": [], "broken": []}  # conftest: 시험마다 임시 폴더
    for off in ("off", "0", " OFF "):
        monkeypatch.setenv("NFM_STYLES", off)
        assert L.root() is None and not L.enabled() and L.listing() == {"styles": [], "broken": []} and L.get("0" * 12) is None and L.carrier("0" * 12) is None
        with pytest.raises(OSError):
            L.create(TABLE, b"x")
    monkeypatch.delenv("NFM_STYLES")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert L.root() == tmp_path / "local" / "NewFileManager" / "styles"


def test_add_seen_keeps_other_source_docs_without_new_revision(tmp_path):
    """같은 서식이 다른 문서에서 또 나오면 그 문서를 `seenIn` 에 남긴다(spec_서식복사 ② §17) — revision·고친 때·검증 기록은 그대로, 원본 문서·이미 적힌 문서는 다시 안 적는다."""
    src = {"name": "a.hwpx", "format": "hwpx", "work": "w1", "block": "t3", "sha256": "A" * 64, "project": "갑", "job": "style_copy", "round": 2, "where": "표 3번째", "at": 10.5}
    m = L.create({**TABLE, "source": src}, b"carrier-1")
    assert m["source"] == {**src, "page": None} and m["seenIn"] == []
    L.put_verify(m["id"], "r1", {"status": "ok"})
    assert L.add_seen(m["id"], {**src, "work": "w9"}) == L.get(m["id"]) and L.get(m["id"])["seenIn"] == []      # 같은 문서(해시가 같다 — 다른 작업으로 연 것)
    other = {"name": "b.docx", "format": "docx", "work": None, "sha256": "B" * 64, "project": "을", "where": "2쪽", "at": 20.0, "block": "t1", "junk": 1}
    got = L.add_seen(m["id"], other)
    seen = {"name": "b.docx", "format": "docx", "work": None, "sha256": "B" * 64, "project": "을", "job": None, "round": None, "where": "2쪽", "at": 20.0}
    assert got["seenIn"] == [seen] and (got["revision"], got["updated"], got["verify"]) == ("r1", m["updated"], {"status": "ok"}) and got == L.get(m["id"])
    assert L.add_seen(m["id"], {**other, "at": 30.0})["seenIn"] == [seen]                                        # 이미 적힌 문서
    assert L.add_seen(m["id"], {"name": "c.hwpx", "format": "hwpx"})["seenIn"][-1]["name"] == "c.hwpx"           # 해시가 없으면 이름·형식으로
    assert len(L.add_seen(m["id"], {"name": "c.hwpx", "format": "hwpx"})["seenIn"]) == 2
    assert L.add_seen(m["id"], {"format": "hwpx"}) == L.get(m["id"]) and L.add_seen("0" * 12, other) is None      # 이름 없는 기록은 안 적는다 · 없는 서식
    for i in range(L.SEEN_MAX + 3):
        L.add_seen(m["id"], {"name": f"d{i}.hwpx", "format": "hwpx"})
    kept = L.get(m["id"])["seenIn"]
    assert len(kept) == L.SEEN_MAX and kept[-1]["name"] == f"d{L.SEEN_MAX + 2}.hwpx"                             # 넘으면 옛 것부터 버린다
    r2 = L.revise(m["id"], "r1", {"name": "새 이름"})
    assert r2["revision"] == "r2" and r2["seenIn"] == kept and r2["source"] == m["source"]                        # 이름을 바꿔도 원본 기록은 남는다
    assert L.same_doc({"name": "x", "sha256": "1"}, {"name": "y", "sha256": "1"}) and not L.same_doc({"name": "x", "sha256": "1"}, {"name": "x", "sha256": "2"}) and not L.same_doc({}, {})


def test_create_fills_meta_and_writes_revision_folder(tmp_path):
    m = L.create(TABLE, b"carrier-1", {"proof.png": b"png"})
    assert re.fullmatch(r"[0-9a-f]{12}", m["id"]) and m["revision"] == "r1" and m["schemaVersion"] == 1 and m["created"] == m["updated"] > 0
    assert m["name"] == "예산 총괄표" and m["note"] == "" and m["fidelity"] == "native" and m["verify"] is None and m["carrierSha256"] == L.sha256(b"carrier-1")
    assert m["bands"] == {"headerRows": 1, "headerCols": 3, "footRows": 1} and m["blueprint"] is None and m["losses"] == ["캡션"]  # 띠 수는 표 크기 안으로
    assert m["requirements"] == {"fonts": ["맑은 고딕", "바탕"]} and m["source"] == {"name": "a.hwpx", "format": "hwpx", "work": "w1", "block": "t3", "page": None, "sha256": None,
                                                                                     "project": None, "job": None, "round": None, "where": None, "at": None} and m["seenIn"] == []  # 원본 기록의 키(② §17) — 모르는 키(junk)는 버린다
    d = _root(tmp_path) / m["id"]
    assert json.loads((d / "current.json").read_text("utf-8")) == {"revision": "r1"}
    assert sorted(p.name for p in (d / "revisions" / "r1").iterdir()) == ["carrier.hwpx", "meta.json", "proof.png"]
    assert json.loads((d / "revisions" / "r1" / "meta.json").read_text("utf-8")) == m == L.get(m["id"])
    assert L.carrier(m["id"]) == b"carrier-1" == L.carrier(m["id"], "r1") and L.carrier(m["id"], "r2") is None
    assert L.file(m["id"], "proof.png").read_bytes() == b"png" and L.file(m["id"], "proof.pdf") is None and L.file(m["id"], "../current.json") is None
    t = L.create(TEXT, b"carrier-2")
    assert t["kind"] == "text" and "bands" not in t and [i["key"] for i in t["items"]] == ["i1", "i2"]
    got = L.listing()
    assert [x["id"] for x in got["styles"]] == [t["id"], m["id"]] and got["broken"] == []  # 고친 때가 새것부터
    assert not [p.name for p in _root(tmp_path).iterdir() if p.name.startswith(".")]  # 임시 폴더가 안 남는다


@pytest.mark.parametrize("bad", [
    {**TABLE, "kind": "chart"}, {**TABLE, "name": "  "}, {**TABLE, "name": "가" * 61}, {**TABLE, "note": "가" * 401}, {**TABLE, "fidelity": "exact"},
    {**TABLE, "rows": 0}, {**TABLE, "cols": "3"}, {"kind": "text", "name": "글"}, {**TEXT, "items": []}, {**TEXT, "items": [{"key": "i1"}, {"key": "i1"}]}, {**TEXT, "items": [{"name": "x"}]}, "meta"])
def test_create_rejects_bad_meta(bad):
    with pytest.raises(ValueError):
        L.create(bad, b"x")
    assert L.listing() == {"styles": [], "broken": []}


def test_create_rejects_empty_carrier_and_bad_file_names():
    for carrier, files in ((b"", None), (None, None), (b"x", {"../a.png": b"1"}), (b"x", {"meta.json": b"{}"}), (b"x", {"proof.png": "글"})):
        with pytest.raises(ValueError):
            L.create(TABLE, carrier, files)
    assert L.listing()["styles"] == []


def test_revise_makes_next_revision_and_inherits_verify_only_for_same_carrier(tmp_path):
    m = L.create(TABLE, b"c1")
    sid = m["id"]
    rec = {"status": "ok", "revision": "r1", "subjectHash": "h"}
    assert L.put_verify(sid, "r1", rec, {"proof.png": b"png1"}) is True and L.get(sid)["verify"] == rec and L.get(sid)["updated"] == m["updated"]
    r2 = L.revise(sid, "r1", {"name": "새 이름", "note": "메모", "bands": {"headerRows": 2}, "id": "x" * 12, "kind": "text", "revision": "r9", "verify": None, "created": 0})
    assert r2["revision"] == "r2" and r2["name"] == "새 이름" and r2["note"] == "메모" and r2["bands"] == {"headerRows": 2, "headerCols": 0, "footRows": 0}
    assert r2["id"] == sid and r2["kind"] == "table" and r2["created"] == m["created"] and r2["updated"] >= m["updated"]  # 저장소가 정하는 키는 못 바꾼다
    assert r2["verify"] == rec and L.file(sid, "proof.png").read_bytes() == b"png1" and L.carrier(sid) == b"c1" and r2["carrierSha256"] == m["carrierSha256"]  # 운반 문서가 같다 — 검증·그림을 물려받음
    assert L.get(sid) == r2 and json.loads((_root(tmp_path) / sid / "current.json").read_text("utf-8")) == {"revision": "r2"}
    r3 = L.revise(sid, "r2", None, b"c2", {"note.txt": b"n"})
    assert r3["revision"] == "r3" and r3["verify"] is None and L.file(sid, "proof.png") is None and L.file(sid, "note.txt") is not None  # 운반 문서가 바뀌면 검증은 버린다
    assert L.carrier(sid) == b"c2" and L.carrier(sid, "r1") == b"c1" and r3["name"] == "새 이름" and r3["carrierSha256"] == L.sha256(b"c2")
    r4 = L.revise(sid, "r3", {"name": "넷째"}, b"c2")  # 같은 바이트를 다시 줘도 「같은 운반 문서」
    assert r4["revision"] == "r4" and L.file(sid, "note.txt") is not None
    with pytest.raises(ValueError):
        L.revise(sid, "r4", {"name": ""})
    assert L.get(sid)["revision"] == "r4"


def test_stale_revision_and_unknown_id():
    sid = L.create(TABLE, b"c")["id"]
    L.revise(sid, "r1", {"name": "둘"})
    with pytest.raises(L.Stale):
        L.revise(sid, "r1", {"name": "늦은 쪽"})
    with pytest.raises(L.Stale):
        L.delete(sid, "r1")
    assert L.get(sid)["name"] == "둘" and L.get(sid)["revision"] == "r2"
    for bad in ("0" * 12, "nope", "../x", None, 5):
        assert L.get(bad) is None and L.carrier(bad) is None and L.file(bad, "proof.png") is None and L.delete(bad) is False and L.put_verify(bad, "r1", {}) is False
        with pytest.raises(KeyError):
            L.revise(bad, None, {"name": "x"})
    assert L.delete(sid, "r2") is True and L.get(sid) is None and L.delete(sid) is False and L.listing() == {"styles": [], "broken": []}


def test_expected_revision_is_required_for_healthy_templates(tmp_path):
    """astra 14: expected 를 빼면 revision 검사를 건너뛰어, 오래된 화면이 남의 고침을 덮어쓰거나 지웠다 — 성한 템플릿은 꼭 준다(깨진 것을 지울 때만 없이)."""
    sid = L.create(TABLE, b"c")["id"]
    for missing in (None, "", "3", "r0", "../r1", 1):
        with pytest.raises(ValueError, match="expectedRevision"):
            L.revise(sid, missing, {"name": "몰래 덮어쓰기"})
    with pytest.raises(ValueError, match="expectedRevision"):
        L.delete(sid)
    assert L.get(sid)["name"] == "예산 총괄표" and L.get(sid)["revision"] == "r1"  # 아무것도 안 바뀌었다
    with pytest.raises(L.Stale):
        L.revise(sid, "r7", {"name": "없는 revision"})
    broken = L.create(TABLE, b"c")["id"]
    (_root(tmp_path) / broken / "current.json").unlink()
    assert L.delete(broken) is True and L.delete(sid, "r1") is True  # 깨진 것만 expected 없이


def test_missing_or_altered_carrier_is_broken(tmp_path):
    """astra 14: 운반 문서가 없거나 바이트가 meta 의 carrierSha256 과 다른 템플릿을 정상 목록에 섞지 않는다 — 읽기·고치기·적용의 원본이 되지 못한다."""
    good, lost, altered = (L.create({**TABLE, "name": n}, b"carrier") for n in ("성함", "운반 문서 없음", "운반 문서 바뀜"))
    root = _root(tmp_path)
    (root / lost["id"] / "revisions" / "r1" / "carrier.hwpx").unlink()
    (root / altered["id"] / "revisions" / "r1" / "carrier.hwpx").write_bytes(b"other bytes")
    got = L.listing()
    assert [m["id"] for m in got["styles"]] == [good["id"]] and sorted(got["broken"]) == sorted([lost["id"], altered["id"]])
    for m in (lost, altered):
        assert L.get(m["id"]) is None and L.carrier(m["id"]) is None and L.carrier(m["id"], "r1") is None
        with pytest.raises(KeyError):
            L.revise(m["id"], "r1", {"name": "바뀐 운반 문서를 성한 것으로"})  # 새 revision 이 바뀐 바이트의 해시를 적어 주지 않는다
        with pytest.raises(KeyError):
            L.revise(m["id"], "r1", None, b"new carrier")
    assert (root / altered["id"] / "revisions" / "r1" / "carrier.hwpx").read_bytes() == b"other bytes" and not (root / altered["id"] / "revisions" / "r2").exists()
    assert L.delete(lost["id"]) is True and L.delete(altered["id"]) is True and L.listing()["broken"] == []  # 깨진 것은 expected 없이 지운다
    assert L.get(good["id"]) == good and L.carrier(good["id"]) == b"carrier"


def test_pinned_revision_survives_pruning_until_unpinned(tmp_path):
    """astra 14: 검증이 도는 동안 revision 이 다섯 번 넘게 바뀌면 시작 때의 revision 이 치워져 결과가 버려졌다 — 붙든 revision 은 놓을 때까지 남는다."""
    sid = L.create(TEXT, b"c1")["id"]
    revs = _root(tmp_path) / sid / "revisions"
    assert L.pin(sid, "r1") is True and L.pin(sid, "r1") is True  # 두 번 붙듦(센다)
    assert L.pin(sid, "r9") is False and L.pin("0" * 12, "r1") is False and L.pin(sid, None) is False and L.pin(sid, "../r1") is False
    for n in range(2, 9):
        L.revise(sid, f"r{n - 1}", {"note": f"{n}"}, f"c{n}".encode())
    assert sorted(p.name for p in revs.iterdir()) == ["r1", "r4", "r5", "r6", "r7", "r8"]  # 최근 5개 + 붙든 r1
    assert L.put_verify(sid, "r1", {"status": "ok", "revision": "r1"}, {"proof.png": b"p"}) is True and L.carrier(sid, "r1") == b"c1"  # 결과를 붙일 자리가 있다
    L.unpin(sid, "r1")
    assert (revs / "r1").is_dir()  # 아직 한 번 더 붙들려 있다
    L.unpin(sid, "r1")
    assert sorted(p.name for p in revs.iterdir()) == ["r4", "r5", "r6", "r7", "r8"] and L.get(sid)["revision"] == "r8"  # 놓으면 밀린 것을 치운다
    L.unpin(sid, "r1")
    L.unpin("0" * 12, "r3")  # 안 붙든 것을 놓아도 아무 일 없다
    assert L.pin(sid, "r8") is True and L.delete(sid, "r8") is True
    L.unpin(sid, "r8")  # 지운 템플릿의 것을 놓아도 아무 일 없다
    assert not [k for k in L._PINS if k[0] == sid] and L.listing() == {"styles": [], "broken": []}


def test_keeps_last_five_revisions_and_put_verify_only_on_that_revision(tmp_path):
    sid = L.create(TEXT, b"c1")["id"]
    for n in range(2, 8):
        L.revise(sid, f"r{n - 1}", {"note": f"{n}"}, f"c{n}".encode())
    revs = _root(tmp_path) / sid / "revisions"
    assert sorted(p.name for p in revs.iterdir()) == ["r3", "r4", "r5", "r6", "r7"] and L.get(sid)["revision"] == "r7"
    assert L.put_verify(sid, "r1", {"status": "ok"}) is False and L.put_verify(sid, "r9", {"status": "ok"}) is False and L.put_verify(sid, "r7", "글") is False  # 치워진·없는 revision · 기록이 아님
    assert L.put_verify(sid, "r6", {"status": "warn"}, {"proof.png": b"old"}) is True  # 옛 revision 이 아직 있으면 **거기에만**
    assert L.get(sid)["verify"] is None and L.file(sid, "proof.png") is None and L.file(sid, "proof.png", "r6").read_bytes() == b"old"
    assert json.loads((revs / "r6" / "meta.json").read_text("utf-8"))["verify"] == {"status": "warn"} and L.carrier(sid, "r6") == b"c6" and L.carrier(sid, "r2") is None


def test_put_verify_reaches_a_later_revision_only_when_the_carrier_is_the_same():
    sid = L.create(TABLE, b"c1")["id"]
    L.revise(sid, "r1", {"name": "검증이 도는 동안 이름만 바꿈"})  # r2 — 운반 문서는 r1 과 같다
    assert L.put_verify(sid, "r1", {"status": "ok", "revision": "r1"}, {"proof.png": b"p1"}) is True
    assert L.get(sid)["revision"] == "r2" and L.get(sid)["verify"] == {"status": "ok", "revision": "r1"} and L.file(sid, "proof.png").read_bytes() == b"p1"
    assert L.put_verify(sid, "r1", {"status": "fail", "revision": "r1"}) is True and L.get(sid)["verify"]["status"] == "ok"  # 새 revision 에 이미 기록이 있으면 안 덮는다
    L.revise(sid, "r2", None, b"c2")  # r3 — 운반 문서가 바뀜
    assert L.put_verify(sid, "r2", {"status": "warn"}) is True and L.get(sid)["verify"] is None and L.file(sid, "proof.png") is None  # 검증한 운반 문서가 아니다


def test_broken_files_are_listed_as_broken_and_never_overwritten(tmp_path):
    good, bad_meta, no_current, bad_current = (L.create({**TABLE, "name": n}, b"c")["id"] for n in ("좋음", "meta 깨짐", "current 없음", "current 깨짐"))
    root = _root(tmp_path)
    (root / bad_meta / "revisions" / "r1" / "meta.json").write_text("{ 깨진 JSON", "utf-8")
    (root / no_current / "current.json").unlink()
    (root / bad_current / "current.json").write_text('{"revision": "../r1"}', "utf-8")
    (root / "not-a-style").mkdir()
    (root / "readme.txt").write_text("x", "utf-8")
    got = L.listing()
    assert [m["id"] for m in got["styles"]] == [good] and sorted(got["broken"]) == sorted([bad_meta, no_current, bad_current])
    for sid in (bad_meta, no_current, bad_current):
        assert L.get(sid) is None and L.put_verify(sid, "r1", {"status": "ok"}) is (sid != bad_meta)  # meta 가 성한 revision 에는 붙는다(current 만 깨진 것)
        with pytest.raises(KeyError):
            L.revise(sid, None, {"name": "덮어쓰기"})
    assert (root / bad_meta / "revisions" / "r1" / "meta.json").read_text("utf-8") == "{ 깨진 JSON" and not (root / no_current / "current.json").exists()
    with pytest.raises(L.Stale):
        L.delete(no_current, "r1")  # 깨진 것은 expected 로는 못 지운다
    assert L.delete(no_current) is True and L.delete(bad_meta) is True and L.listing()["broken"] == [bad_current]
    wrong = L.create(TABLE, b"c")["id"]  # meta 의 id 가 폴더와 다르면(손으로 복사한 폴더) 깨진 것
    p = root / wrong / "revisions" / "r1" / "meta.json"
    p.write_text(json.dumps({**json.loads(p.read_text("utf-8")), "id": good}), "utf-8")
    assert wrong in L.listing()["broken"] and L.get(wrong) is None


def test_failed_write_keeps_current_revision_and_retries_locked_files(tmp_path, monkeypatch):
    sid = L.create(TABLE, b"c1")["id"]
    real = L._write

    def fail_on_current(path, data):
        if path.name == "current.json":
            raise OSError("디스크 가득")
        return real(path, data)
    monkeypatch.setattr(L, "_write", fail_on_current)
    with pytest.raises(OSError):
        L.revise(sid, "r1", {"name": "실패"}, b"c2")
    monkeypatch.setattr(L, "_write", real)
    assert L.get(sid)["revision"] == "r1" and L.get(sid)["name"] == "예산 총괄표" and L.carrier(sid) == b"c1" and L.listing()["broken"] == []  # current.json 이 마지막 — 그 전에 죽으면 그대로
    ok = L.revise(sid, "r1", {"name": "다시"}, b"c3")
    assert ok["revision"] == "r3" and L.carrier(sid) == b"c3"  # 쓰다 만 r2 번호는 다시 쓰지 않는다
    calls, replace = [], L.os.replace

    def locked_once(a, b):
        calls.append(b)
        if len(calls) == 1:
            raise PermissionError("잠김")
        return replace(a, b)
    monkeypatch.setattr(L.os, "replace", locked_once)
    assert L.revise(sid, "r3", {"name": "잠긴 뒤"})["revision"] == "r4" and len(calls) >= 3  # 잠긴 파일은 잠깐 뒤 다시(heading_rules._retry)
    monkeypatch.setattr(L.os, "replace", replace)

    real_json = L._json

    def boom(*a, **k):
        raise OSError("쓰기 실패")
    monkeypatch.setattr(L, "_json", boom)
    with pytest.raises(OSError):
        L.create(TABLE, b"c")
    monkeypatch.setattr(L, "_json", real_json)
    assert [m["id"] for m in L.listing()["styles"]] == [sid] and L.listing()["broken"] == []  # 쓰다 만 새 템플릿은 목록에 안 남는다
    assert not [p.name for p in (_root(tmp_path) / sid / "revisions").iterdir() if p.name.startswith(".")]


def test_concurrent_revisions_get_distinct_numbers():
    sid = L.create(TABLE, b"c")["id"]
    out, errs, stale = [], [], []

    def work(k):
        try:
            for _ in range(200):  # 읽은 revision 으로 고친다 — 그 사이 남이 고쳤으면(Stale) 다시 읽고
                try:
                    out.append(L.revise(sid, L.get(sid)["revision"], {"note": f"{k}"})["revision"])
                    return
                except L.Stale:
                    stale.append(k)
            raise AssertionError("끝내 못 고침")
        except Exception as e:  # noqa: BLE001
            errs.append(e)
    ts = [threading.Thread(target=work, args=(k,)) for k in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errs and sorted(out, key=lambda r: int(r[1:])) == [f"r{n}" for n in range(2, 10)] and L.get(sid)["revision"] == "r9"


# ---- 2차: 문단 서식의 role · 표지 서식(spec_서식복사 ② §12·§14) -------------------------------------------------------------

def test_text_role_is_kept_only_on_styles_without_levels():
    para = {"kind": "text", "name": "캡션 글", "items": [{"key": "i1", "name": "문단 1", "level": None}]}
    m = L.create({**para, "role": "caption"}, b"c1")
    assert m["role"] == "caption" and not L.leveled(m) and L.create(para, b"c2")["role"] is None          # 역할을 안 주면 null(모름)
    for bad in ("title", "", 3, ["body"]):
        with pytest.raises(ValueError):
            L.create({**para, "role": bad}, b"c")
    assert set(L.ROLES) == {"body", "caption", "note", "box", "toc", "other"}
    r2 = L.revise(m["id"], "r1", {"role": "note"})
    assert r2["role"] == "note" and L.get(m["id"])["role"] == "note" and r2["revision"] == "r2"
    with pytest.raises(ValueError):
        L.revise(m["id"], "r2", {"role": "제목"})
    r3 = L.revise(m["id"], "r2", {"items": [{"key": "i1", "name": "1수준", "level": 1}]})                  # 레벨이 붙으면 내용 서식 — 역할은 없다
    assert L.leveled(r3) and r3["role"] is None
    t = L.create({**TEXT, "role": "body"}, b"c3")                                                        # 레벨이 있는 글 서식에 준 역할은 버린다
    assert L.leveled(t) and t["role"] is None
    assert not L.leveled(TABLE) and not L.leveled(None) and not L.leveled({"kind": "text"})


def test_cover_kind_needs_parts_and_keeps_page():
    page = {"widthMm": 210.0, "heightMm": 297.0, "landscape": False, "marginsMm": {"l": 20.0, "r": 20.0, "t": 20.0, "b": 15.0}}
    parts = [{"key": "p1", "type": "text", "role": "title", "sample": "제목", "format": {"sizePt": 22.0}}, {"key": "p2", "type": "table", "rows": 2, "cols": 3}]
    assert "cover" in L.KINDS
    m = L.create({"kind": "cover", "name": " 보고서  표지 ", "page": page, "parts": parts, "losses": ["그림은 옮기지 않았습니다"]}, b"cover-1", {"carrier.docx": b"docx"})
    assert (m["kind"], m["name"], m["page"], m["parts"]) == ("cover", "보고서 표지", page, parts) and "bands" not in m and "items" not in m and "role" not in m
    assert m["docx"]["sha256"] == L.sha256(b"docx") and L.get(m["id"]) == m and [s["id"] for s in L.listing()["styles"]] == [m["id"]] and L.listing()["broken"] == []
    assert L.create({"kind": "cover", "name": "쪽 설정 없이", "parts": parts, "page": "A4"}, b"c")["page"] is None   # 쪽 설정을 못 읽은 표지 — 부분만
    for bad in ({"kind": "cover", "name": "x"}, {"kind": "cover", "name": "x", "parts": []}, {"kind": "cover", "name": "x", "parts": [{"type": "image"}]}, {"kind": "cover", "name": "x", "parts": ["p"]}):
        with pytest.raises(ValueError):
            L.create(bad, b"c")
    r2 = L.revise(m["id"], "r1", {"name": "새 이름"})                                                     # 이름만 — 부분·쪽 설정·docx 는 그대로
    assert (r2["name"], r2["parts"], r2["page"], r2["docx"]) == ("새 이름", parts, page, m["docx"])
