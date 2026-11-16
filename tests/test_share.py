"""hwpx 공유(spec_공유) — 키 · 키 넣기 제한 · 사람들·작성 중 · 변경 알림(순수 로직 app/share.py) + 주인 끝점(8114 앱)과 손님 앱(app/share_api.py)."""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import server, share, share_api, works

SAMPLES = Path(__file__).parents[1] / "samples"
NAME = "기술수요조사서.hwpx"
X = {"X-Share": "1"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """시험마다 공유의 메모리 상태를 비우고 공유 포트는 실제로 열지 않는다(여는 시험만 따로)."""
    monkeypatch.setattr(share_api.LISTENER, "start", lambda: True)
    for d in (share._rooms, share._fails, share._wide, share_api.FEEDS, share_api._seen):
        d.clear()
    share.configure(works.root)   # 기록 파일 = 이 시험의 임시 작업 폴더 옆(순수 로직 시험이 다른 자리로 바꿔 둔 것을 되돌린다)
    yield
    share_api._saver["stop"].set()
    share.configure(works.root)


@pytest.fixture
def client():
    return TestClient(server.app)


def _open(client):
    r = client.post("/api/docs", files={"file": (NAME, (SAMPLES / NAME).read_bytes())}, params={"new": True})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _start(client, folder, host="김주인"):
    doc = _open(client)
    r = client.post(f"/api/docs/{doc}/share", json={"folder": str(folder), "host": host})
    assert r.status_code == 200, r.text
    return doc, r.json()


def _guest(st, name="손님"):
    g = TestClient(share_api.guest)
    r = g.post(f"/s/{st['id']}/join", json={"key": st["key"], "name": name}, headers=X)
    assert r.status_code == 200, r.text
    return g, r.json()["me"]


def _first_para(blocks):
    for b in blocks:
        if b["type"] == "paragraph":
            return b
        for c in b.get("cells") or ():
            p = _first_para(c["blocks"])
            if p:
                return p
    return None


# ---- 순수 로직 ---------------------------------------------------------------------------------------

def test_key_is_twelve_unambiguous_letters_and_only_the_hash_is_kept(tmp_path):
    share.configure(lambda: tmp_path / "works")
    rec, key = share.create("a" * 12, "문서.hwpx", tmp_path, "문서.hwpx", "  김   주인  ")
    assert len(key) == 12 and set(key) <= set(share.KEY_ABC) and not set(key) & set("IO01")
    assert share.show_key(key) == f"{key[:4]}-{key[4:8]}-{key[8:]}"
    assert key not in (tmp_path / "shares.json").read_text("utf-8") and rec["host"] == "김 주인"
    assert share.key_ok(rec, share.show_key(key).lower()) and share.key_ok(rec, f" {key} ")   # 줄표·공백·소문자로 넣어도
    assert not share.key_ok(rec, key[:-1] + ("A" if key[-1] != "A" else "B")) and not share.key_ok(rec, "") and not share.key_ok(rec, None)
    with pytest.raises(share.ShareError) as e:   # 문서 하나에 켜진 공유는 하나
        share.create("a" * 12, "문서.hwpx", tmp_path, "문서.hwpx", "x")
    assert e.value.code == 409
    old = share.get(rec["id"])
    new = share.rekey(rec["id"])
    assert new != key and not share.key_ok(share.get(rec["id"]), key) and share.key_ok(share.get(rec["id"]), new) and old["salt"] != share.get(rec["id"])["salt"]
    assert share.stop(rec["id"])["active"] is False and share.by_doc("a" * 12) is None and share.last_of("a" * 12)["id"] == rec["id"]


def test_shares_file_sits_beside_the_work_store_and_off_turns_sharing_off(tmp_path, monkeypatch):
    share.configure(lambda: tmp_path / "w" / "works")
    assert share.path() == tmp_path / "w" / "shares.json" and share.enabled()
    share.configure(lambda: None)
    assert share.path() is None and not share.enabled()          # 작업 저장이 꺼지면 공유도
    monkeypatch.setenv("NFM_SHARES", str(tmp_path / "x.json"))
    assert share.path() is None                                  # env 가 파일 경로여도 — 공유할 작업이 없다
    share.configure(lambda: tmp_path / "works")
    assert share.path() == tmp_path / "x.json"
    monkeypatch.setenv("NFM_SHARES", "off")
    assert share.path() is None


def test_wrong_keys_lock_the_address_then_the_whole_share():
    sid, t = "s" * 16, 1000.0
    for _ in range(share.FAIL_MAX - 1):
        share.failed(sid, "1.1.1.1", t)
    assert share.locked(sid, "1.1.1.1", t) == 0
    share.failed(sid, "1.1.1.1", t)
    assert share.locked(sid, "1.1.1.1", t) == share.FAIL_LOCK and share.locked(sid, "2.2.2.2", t) == 0   # 다른 주소는 그대로
    share.failed(sid, "1.1.1.1", t)
    assert share.locked(sid, "1.1.1.1", t) == share.FAIL_LOCK * 2                                        # 틀릴 때마다 두 배
    share.passed(sid, "1.1.1.1")
    assert share.locked(sid, "1.1.1.1", t) == 0
    for k in range(share.SHARE_FAILS):                                                                   # 주소를 바꿔 가며 틀려도 공유 하나에 상한
        share.failed(sid, f"9.9.{k}.1", t)
    assert share.locked(sid, "3.3.3.3", t) == share.SHARE_LOCK and share.locked(sid, "3.3.3.3", t + share.SHARE_LOCK + 1) == 0
    sid2 = "t" * 16                                                                                      # 주소를 모르는 요청(터널이 주소를 안 적어 줌)은 주소별로 세지 않는다
    for _ in range(share.FAIL_MAX + 3):
        share.failed(sid2, "", t)
    assert share.locked(sid2, "", t) == 0 and not [k for k in share._fails if k[0] == sid2]              # 한 사람이 틀린 것으로 모두를 잠그지 않는다
    for _ in range(share.SHARE_FAILS):
        share.failed(sid2, "", t)
    assert share.locked(sid2, "", t) == share.SHARE_LOCK                                                 # 공유 하나의 상한은 그대로


def test_one_paragraph_one_writer_and_holds_expire():
    sid, t = "r" * 16, 500.0
    ta, a = share.join(sid, "가", t)
    tb, b = share.join(sid, " 나 ", t)
    assert a["color"] != b["color"] and b["name"] == "나" and share.who(sid, ta, t)["id"] == a["id"] and share.who(sid, "없는토큰", t) is None
    assert share.touch(sid, a["id"], "p1", t) is None
    assert share.touch(sid, b["id"], "p1", t + 1)["id"] == a["id"]            # 늦게 잡으려 한 쪽은 못 잡는다
    assert share.holder(sid, "p1", t + 1, but=b["id"])["id"] == a["id"] and share.holder(sid, "p1", t + 1, but=a["id"]) is None
    assert [p["block"] for p in share.people(sid, t + 1)] == ["p1", None]
    assert share.touch(sid, b["id"], "p1", t + share.HOLD + 1) is None        # 소식이 끊기면 풀린다
    assert share.holder(sid, "p1", t + share.HOLD + 1, but=a["id"])["id"] == b["id"]
    assert [p["id"] for p in share.people(sid, t + share.ONLINE + 5)] == [b["id"]] or share.people(sid, t + share.ONLINE + 5) == []
    share.host_in(sid, "주인", t)
    assert share.people(sid, t)[0]["host"] is True                           # 주인이 맨 앞
    share.drop_guests(sid)
    assert share.who(sid, ta, t) is None and [p["id"] for p in share.people(sid, t)] == [share.HOST]
    tc, c = share.join(sid, "다", t)
    assert share.who(sid, tc, t + share.TOKEN_IDLE - 1)["id"] == c["id"]      # 소식이 있으면 이어진다
    assert share.who(sid, tc, t + 2 * share.TOKEN_IDLE) is None and share.who(sid, tc, t + 2 * share.TOKEN_IDLE + 1) is None   # 12시간 소식이 없던 세션은 그 자리에서 끝
    with pytest.raises(share.ShareError):
        share.join(sid, "   ", t)


def test_room_is_full_at_the_limit():
    sid = "f" * 16
    for k in range(share.GUESTS_MAX):
        share.join(sid, f"손님{k}", 10.0)
    with pytest.raises(share.ShareError) as e:
        share.join(sid, "늦은 손님", 10.0)
    assert e.value.code == 409
    share.join(sid, "나중 손님", 10.0 + share.ONLINE + 1)                    # 소식이 끊긴 자리는 빈다


def test_feed_keeps_edits_in_rev_order_and_skips_my_own():
    f = share.Feed(10)
    ep = f.epoch
    f.note(11, "text", "g1", {"id": "p1", "after": "가"}, now=0)
    f.note(12, "split", "host", {"req": {}}, now=0)
    f.note(13, "text", "g1", {"id": "p2", "after": "나"}, now=0)
    r = f.read(10, ep, "g2", now=0.1)
    assert [i["rev"] for i in r["items"]] == [11] and r["rev"] == 11            # 안 채워진 자리 앞에서 멈춘다
    assert f.fill(12, {"rev": 12, "tops": {"drop": ["p1"], "blocks": [{"id": "p1"}, {"id": "p9"}]}, "undo": 3})
    r = f.read(11, ep, "g2", now=0.2)
    assert [(i["rev"], i["t"]) for i in r["items"]] == [(12, "tops"), (13, "text")] and r["items"][0]["drop"] == ["p1"] and "resp" not in r["items"][0]
    assert f.read(11, ep, "g2", full=True, now=0.2)["items"][0]["resp"]["undo"] == 3    # 주인 화면에는 응답을 통째로
    mine = f.read(10, ep, "g1", now=0.2)
    assert [i["rev"] for i in mine["items"]] == [12] and mine["rev"] == 13      # 내 편집은 건너뛴다
    assert f.read(13, ep, "g2", now=0.2) == {"epoch": ep, "rev": 13, "items": []}
    assert not f.fill(12, {"rev": 12, "tops": {"blocks": []}}) and not f.fill(99, {"tops": {"blocks": []}}) and not f.fill(13, {"tops": {"blocks": []}})


def test_feed_says_reload_when_it_cannot_replay():
    f = share.Feed(5)
    ep = f.epoch
    assert f.read(4, ep, "g", now=0)["reload"] and f.read(5, "다른묶음", "g", now=0)["reload"] and f.read(None, ep, "g", now=0)["reload"]
    assert f.read(5, "", "g", now=0) == {"epoch": ep, "rev": 5, "items": []}      # 빈 묶음 = 방금 문서를 읽었다 — rev 만 본다
    f.note(6, "undo", "host", {}, now=0)
    assert f.read(5, ep, "g", now=0.5) == {"epoch": ep, "rev": 5, "items": []}   # 응답을 기다린다
    assert f.read(5, ep, "host", now=0.5)["rev"] == 6                           # 한 사람은 제 응답으로 이미 안다
    assert f.read(5, ep, "g", now=share.FEED_WAIT + 0.1)["reload"]              # 안 채워지면 다시 읽기
    assert f.read(6, ep, "g", now=9)["items"] == []
    f.note(8, "text", "g", {"id": "p", "after": "x"}, now=9)                    # 못 본 편집(7)이 있다
    assert f.read(6, ep, "h", now=9)["reload"] and f.read(8, ep, "h", now=9)["items"] == []
    f.note(3, "restore", "host", {}, now=9)                                     # 차례가 뒤로 갔다 — 묶음을 새로
    assert f.epoch != ep and f.read(8, ep, "g", now=9)["reload"]
    g = share.Feed(0)
    for k in range(1, share.FEED_KEEP + 30):
        g.note(k, "text", "a", {"id": "p", "after": str(k)}, now=0)
    assert len(g.items) == share.FEED_KEEP and g.read(1, g.epoch, "b", now=0)["reload"] and len(g.read(g.base, g.epoch, "b", now=0)["items"]) == share.FEED_KEEP
    h = share.Feed(0)
    h.note(1, "revert", "a", {"id": "p", "after": "원래", "format": True}, now=0)   # 모양을 되돌린 것은 글만으로 못 옮긴다
    assert h.items[0]["t"] == "wait"


def test_an_older_edit_never_overwrites_my_newer_one():
    """남의 편집이 그 뒤 차례의 내 편집과 같은 문단에 닿으면 — 글은 버리고, 블록 바꿔 끼우기는 다시 읽기."""
    f = share.Feed(0)
    ep = f.epoch
    f.note(1, "text", "g", {"id": "p1", "after": "손님 글"}, now=0)
    f.note(2, "text", "host", {"id": "p1", "after": "주인 글"}, now=0)
    f.note(3, "text", "g", {"id": "p2", "after": "다른 문단"}, now=0)
    r = f.read(0, ep, "host", now=0)
    assert [(i["rev"], i["id"]) for i in r["items"]] == [(3, "p2")] and r["rev"] == 3      # p1 의 옛 글은 안 온다
    f.note(4, "split", "g", {}, now=0)
    f.fill(4, {"rev": 4, "tops": {"drop": ["t1"], "blocks": [{"id": "t1", "type": "table", "cells": [{"blocks": [{"id": "p7", "type": "paragraph"}]}]}]}})
    f.note(5, "text", "host", {"id": "p9", "after": "먼 문단"}, now=0)
    assert [i["t"] for i in f.read(3, ep, "host", now=0)["items"]] == ["tops"]            # 내 뒤 편집이 다른 문단이면 그대로 받는다
    f.note(6, "text", "host", {"id": "p7", "after": "그 표 안의 문단"}, now=0)
    assert f.read(3, ep, "host", now=0)["reload"]                                          # 그 블록 안을 내가 뒤에 고쳤다 — 옛 블록으로 덮지 않는다
    assert [i["t"] for i in f.read(3, ep, "g2", now=0)["items"]] == ["tops", "text", "text"]   # 다른 사람은 차례대로 다 받는다
    f.note(7, "text", "g", {"id": "p3", "after": "x"}, now=10)
    f.note(8, "split", "host", {}, now=10)                                                 # 내 편집의 응답이 아직 안 왔다
    assert f.read(6, ep, "host", now=10.1) == {"epoch": ep, "rev": 6, "items": []}         # 곧 오니 기다린다
    f.fill(8, {"rev": 8, "tops": {"drop": [], "blocks": [{"id": "p5", "type": "paragraph"}]}})
    assert [i["rev"] for i in f.read(6, ep, "host", now=10.2)["items"]] == [7]
    f.note(9, "text", "g", {"id": "p3", "after": "y"}, now=20)
    f.note(10, "undo", "host", {}, now=20)                                                 # 어디가 바뀌었는지 모르는 내 편집
    assert f.read(8, ep, "host", now=20 + share.FEED_WAIT + 1)["reload"]


def test_folder_names_never_overwrite(tmp_path):
    assert share.safe_stem('사업 계획서: 1/2 "최종"?. ') == "사업 계획서 1 2 최종" and share.safe_stem("...") == "문서"
    assert share.free_name(tmp_path, "문서", ".hwpx") == "문서.hwpx"
    (tmp_path / "문서.hwpx").write_bytes(b"x")
    (tmp_path / "문서 (2).hwpx").write_bytes(b"x")
    assert share.free_name(tmp_path, "문서", ".hwpx") == "문서 (3).hwpx"
    assert share.url_file("http://h:1/s/ab") == b"[InternetShortcut]\r\nURL=http://h:1/s/ab\r\n"
    share.write_file(tmp_path / "문서.hwpx", b"new")
    assert (tmp_path / "문서.hwpx").read_bytes() == b"new" and not list(tmp_path.glob("~$*"))


# ---- 주인 끝점 ---------------------------------------------------------------------------------------

def test_start_writes_the_copy_and_the_link_then_shows_the_key_once(client, tmp_path):
    folder = tmp_path / "SharePoint 공유"
    folder.mkdir()
    (folder / NAME).write_bytes(b"someone else's file")
    doc = _open(client)
    off = client.get(f"/api/docs/{doc}/share").json()
    assert off["available"] and not off["active"] and off["folder"] == ""
    assert client.post(f"/api/docs/{doc}/share", json={"folder": str(tmp_path / "없는 폴더")}).status_code == 400
    assert client.post(f"/api/docs/{doc}/share", json={"folder": "상대/경로"}).status_code == 400
    st = client.post(f"/api/docs/{doc}/share", json={"folder": str(folder), "host": "김주인"}).json()
    assert st["active"] and st["file"] == "기술수요조사서 (2).hwpx" and (folder / NAME).read_bytes() == b"someone else's file"   # 있는 파일은 안 덮는다
    assert (folder / st["file"]).read_bytes()[:2] == b"PK" and st["saved"]["error"] is None and not st["saved"]["behind"]
    assert len(st["key"]) == 14 and st["link"].endswith(f"/s/{st['id']}") and st["host"] == "김주인"
    assert (folder / st["linkFile"]).read_bytes() == share.url_file(st["link"]) and st["key"] not in (folder / st["linkFile"]).read_text("utf-8")
    again = client.get(f"/api/docs/{doc}/share").json()
    assert again["active"] and again["key"] is None                                    # 키는 켠 직후에만
    assert client.post(f"/api/docs/{doc}/share", json={"folder": str(folder)}).status_code == 409
    key2 = client.post(f"/api/docs/{doc}/share/key").json()["key"]
    assert key2 and key2 != st["key"]
    end = client.delete(f"/api/docs/{doc}/share").json()
    assert not end["active"] and end["folder"] == str(folder) and end["host"] == "김주인"    # 다시 켤 때 폴더·이름을 미리 채운다
    assert (folder / st["file"]).exists() and not (folder / st["linkFile"]).exists()   # 저장본은 남고 링크 바로가기는 지운다
    assert client.post(f"/api/docs/{doc}/share/key").status_code == 409 and client.get(f"/api/docs/{doc}/share/changes").json() == {"active": False}
    # 다시 켜면 지난번에 우리가 쓴 저장본을 이어 쓴다(번호가 늘지 않는다) — 그 파일이 밖에서 바뀌었으면 새 이름
    st2 = client.post(f"/api/docs/{doc}/share", json={"folder": str(folder)}).json()
    assert st2["file"] == st["file"] and st2["id"] != st["id"] and st2["key"] != st["key"] and st2["host"] == "주인"
    client.delete(f"/api/docs/{doc}/share")
    (folder / st["file"]).write_bytes(b"changed outside")
    st3 = client.post(f"/api/docs/{doc}/share", json={"folder": str(folder)}).json()
    assert st3["file"] == "기술수요조사서 (3).hwpx" and (folder / st["file"]).read_bytes() == b"changed outside"


def test_a_share_of_a_deleted_work_is_retired(client, tmp_path):
    doc, st = _start(client, tmp_path)
    g, _ = _guest(st)
    share_api._orphans()
    assert share.by_doc(doc) is not None                                               # 작업이 있으면 그대로
    assert client.delete(f"/api/works/{doc}").status_code == 200
    share_api._orphans()
    assert share.by_doc(doc) is None and not (tmp_path / st["linkFile"]).exists() and (tmp_path / st["file"]).exists()
    assert g.get(f"/s/{st['id']}/doc").status_code == 410 and g.get(f"/s/{st['id']}/info").json()["active"] is False


def test_a_removed_paragraph_is_404_but_a_removed_work_is_410(client, tmp_path):
    """손님 화면은 404(그 문단이 없어짐 → 문서 다시 읽기)와 410(공유가 끝남)을 갈라 쓴다."""
    doc, st = _start(client, tmp_path)
    sid = st["id"]
    g, _ = _guest(st)
    d = g.get(f"/s/{sid}/doc").json()
    p = _first_para(d["blocks"])
    assert g.patch(f"/s/{sid}/blocks/{p['id']}", json={"text": "앞글뒷글"}, headers=X).status_code == 200
    new = g.post(f"/s/{sid}/split", json={"id": p["id"], "offset": 2}, headers=X).json()["focus"]["id"]
    assert client.post(f"/api/docs/{doc}/undo").status_code == 200                       # 주인의 실행 취소 — 손님이 만든 줄이 없어진다
    gone = g.patch(f"/s/{sid}/blocks/{new}", json={"text": "쓰던 글"}, headers=X)
    assert gone.status_code == 404 and g.post(f"/s/{sid}/split", json={"id": new, "offset": 0}, headers=X).status_code == 404
    assert g.get(f"/s/{sid}/doc").status_code == 200                                     # 공유는 이어진다
    assert client.delete(f"/api/works/{doc}").status_code == 200                         # 작업을 지움 — 아직 걷기 전
    assert g.get(f"/s/{sid}/doc").status_code == 410 and "문서" in g.get(f"/s/{sid}/doc").json()["detail"]
    assert g.patch(f"/s/{sid}/blocks/{p['id']}", json={"text": "x"}, headers=X).status_code == 410 and g.get(f"/s/{sid}/changes").status_code == 410


def test_nothing_is_left_in_the_folder_when_the_port_cannot_open(client, tmp_path, monkeypatch):
    doc = _open(client)
    monkeypatch.setattr(share_api.LISTENER, "start", lambda: False)
    monkeypatch.setattr(share_api.LISTENER, "error", "공유 포트 8119 을(를) 열지 못했습니다")
    folder = tmp_path / "공유"
    folder.mkdir()
    r = client.post(f"/api/docs/{doc}/share", json={"folder": str(folder)})
    assert r.status_code == 503 and "열지 못했습니다" in r.json()["detail"] and not list(folder.iterdir()) and share.by_doc(doc) is None


def test_guest_address_comes_from_the_tunnel_header_only_for_local_requests():
    class Req:
        def __init__(self, host, **headers):
            self.client, self.headers = type("C", (), {"host": host})(), headers
    assert share_api._addr(Req("10.0.0.7", **{"x-forwarded-for": "1.2.3.4"})) == "10.0.0.7"            # 밖에서 직접 온 요청의 머리말은 안 믿는다
    assert share_api._addr(Req("127.0.0.1", **{"cf-connecting-ip": "5.6.7.8", "x-forwarded-for": "1.2.3.4"})) == "5.6.7.8"
    assert share_api._addr(Req("127.0.0.1", **{"x-forwarded-for": " 1.2.3.4 , 9.9.9.9"})) == "1.2.3.4"
    assert share_api._addr(Req("127.0.0.1")) == ""                                                       # 터널이 안 적어 줌 — 모름


def test_public_address_is_validated_and_rewrites_the_link_file(client, tmp_path):
    doc, st = _start(client, tmp_path)
    assert client.put(f"/api/docs/{doc}/share", json={"url": "javascript:alert(1)"}).status_code == 400
    got = client.put(f"/api/docs/{doc}/share", json={"url": "https://share.example.com/"}).json()
    assert got["link"] == f"https://share.example.com/s/{st['id']}" and (tmp_path / st["linkFile"]).read_bytes() == share.url_file(got["link"])
    assert client.put(f"/api/docs/{doc}/share", json={"url": ""}).json()["link"] == st["link"]   # 비우면 사내망 주소로


def test_a_file_changed_outside_is_not_overwritten(client, tmp_path):
    doc, st = _start(client, tmp_path)
    target = tmp_path / st["file"]
    p = _first_para(client.get(f"/api/docs/{doc}").json()["blocks"])
    assert client.patch(f"/api/docs/{doc}/blocks/{p['id']}", json={"text": "고친 글"}).status_code == 200
    assert client.get(f"/api/docs/{doc}/share").json()["saved"]["behind"]
    rec = share.by_doc(doc)
    share_api._autosave(rec, 100.0)
    assert share.by_doc(doc)["saved"]["rev"] == rec["saved"]["rev"]                    # 조용해질 때까지 기다린다
    share_api._autosave(share.by_doc(doc), 100.0 + share_api.SAVE_QUIET)
    saved = share.by_doc(doc)["saved"]
    assert saved["rev"] == server._sess(doc).rev and target.read_bytes() != b"" and share.sha256(target.read_bytes()) == saved["sha"]
    target.write_bytes(b"edited in Hangul by someone")
    assert client.patch(f"/api/docs/{doc}/blocks/{p['id']}", json={"text": "또 고친 글"}).status_code == 200
    got = client.post(f"/api/docs/{doc}/share/save", json={}).json()["saved"]
    assert got["conflict"] and "밖에서" in got["error"] and target.read_bytes() == b"edited in Hangul by someone"
    share_api._autosave(share.by_doc(doc), 999.0)                                      # 주인이 정할 때까지 저절로 덮지 않는다
    assert target.read_bytes() == b"edited in Hangul by someone"
    got = client.post(f"/api/docs/{doc}/share/save", json={"force": True}).json()["saved"]
    assert not got["conflict"] and got["error"] is None and target.read_bytes()[:2] == b"PK"


# ---- 손님 앱 -----------------------------------------------------------------------------------------

def test_guest_needs_the_key_and_gets_locked_out_after_wrong_tries(client, tmp_path):
    doc, st = _start(client, tmp_path)
    g, sid = TestClient(share_api.guest), st["id"]
    assert g.get(f"/s/{sid}").status_code == 200 and "같이 쓰기" in g.get(f"/s/{sid}").text
    assert g.get(f"/s/{sid}/info").json() == {"active": True, "joined": False}
    assert g.get(f"/s/{'0' * 16}/info").json() == {"active": False, "joined": False}
    for path in ("doc", "changes", "media?name=a.png"):
        assert g.get(f"/s/{sid}/{path}").status_code == 401
    assert g.get(f"/s/{'0' * 16}/doc").status_code == 410                                                 # 없는 공유 = 410(없어진 문단의 404 와 가른다)
    assert g.patch(f"/s/{sid}/blocks/p1", json={"text": "x"}, headers=X).status_code == 401
    assert g.post(f"/s/{sid}/join", json={"key": st["key"], "name": "손님"}).status_code == 400          # X-Share 머리말 없음
    assert g.post(f"/s/{sid}/join", json={"key": st["key"], "name": " "}, headers=X).status_code == 400   # 이름 없음(키 횟수를 안 쓴다)
    for _ in range(share.FAIL_MAX):
        assert g.post(f"/s/{sid}/join", json={"key": "AAAA-AAAA-AAAA", "name": "손님"}, headers=X).status_code == 403
    r = g.post(f"/s/{sid}/join", json={"key": st["key"], "name": "손님"}, headers=X)
    assert r.status_code == 429 and r.json()["wait"] > 0                                                  # 맞는 키도 잠긴 동안은 안 받는다
    share._fails.clear()
    r = g.post(f"/s/{sid}/join", json={"key": st["key"].lower(), "name": "손님"}, headers=X)
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower() and f"path=/s/{sid}" in r.headers["set-cookie"].lower()
    assert "samesite=strict" in r.headers["set-cookie"].lower()
    assert g.get(f"/s/{sid}/info").json()["joined"]
    d = g.get(f"/s/{sid}/doc")
    assert d.headers["x-content-type-options"] == "nosniff" and d.headers["x-frame-options"] == "DENY" and "sandbox" in d.headers["content-security-policy"]
    assert "script-src 'self'" in g.get(f"/s/{sid}").headers["content-security-policy"]
    for path in ("/api/docs", f"/api/docs/{doc}", "/api/works", "/docs", "/openapi.json", "/static/app.js", "/"):   # 8114 의 것은 하나도 없다
        assert g.get(path).status_code == 404, path
    assert g.get("/share-static/guest.js").status_code == 200
    big = g.post(f"/s/{sid}/blocks/x", content=b"x" * (share_api.BODY_MAX + 1), headers=X)
    assert big.status_code == 413 and big.headers["x-content-type-options"] == "nosniff"                  # 거절 응답에도 머리말
    client.post(f"/api/docs/{doc}/share/key")                                                             # 키를 바꾸면 모두 나간다
    assert g.get(f"/s/{sid}/doc").status_code == 401
    client.delete(f"/api/docs/{doc}/share")
    assert g.get(f"/s/{sid}/info").json()["active"] is False and g.post(f"/s/{sid}/join", json={"key": st["key"], "name": "손님"}, headers=X).status_code == 410


def test_guest_sees_slim_blocks_and_text_goes_both_ways(client, tmp_path):
    doc, st = _start(client, tmp_path)
    sid = st["id"]
    g, me = _guest(st, "이손님")
    d = g.get(f"/s/{sid}/doc").json()
    p = _first_para(d["blocks"])
    assert d["name"] == NAME and d["host"] == "김주인" and d["me"] == me and p and set(p) <= {"id", "type", "text", "format", "runs", "label", "align", "inlineRow", "captionOf", "page"}
    assert "lines" not in p and d["rev"] == server._sess(doc).rev
    host = client.get(f"/api/docs/{doc}/share/changes", params={"since": d["rev"], "epoch": d["epoch"]}).json()
    assert host["active"] and host["items"] == [] and [x["name"] for x in host["people"]] == ["김주인", "이손님"]
    r = g.patch(f"/s/{sid}/blocks/{p['id']}", json={"text": "손님이 쓴 글\n둘째 줄\x07"}, headers=X)
    assert r.status_code == 200 and r.json()["text"] == "손님이 쓴 글 둘째 줄" and r.json()["rev"] == d["rev"] + 1
    assert g.patch(f"/s/{sid}/blocks/{p['id']}", json={"text": "x"}).status_code == 400                   # X-Share 없음
    assert g.patch(f"/s/{sid}/blocks/{p['id']}", json={"text": "가" * (share_api.TEXT_MAX + 1)}, headers=X).status_code == 400
    assert g.patch(f"/s/{sid}/blocks/없는문단", json={"text": "x"}, headers=X).status_code == 404
    host = client.get(f"/api/docs/{doc}/share/changes", params={"since": d["rev"], "epoch": d["epoch"]}).json()
    assert [(i["t"], i["id"], i["text"], i["by"]) for i in host["items"]] == [("text", p["id"], "손님이 쓴 글 둘째 줄", me["id"])] and host["rev"] == d["rev"] + 1
    assert server._sess(doc).texts[p["id"]] == "손님이 쓴 글 둘째 줄"
    mine = g.get(f"/s/{sid}/changes", params={"since": d["rev"], "epoch": d["epoch"]}).json()
    assert mine["items"] == [] and mine["rev"] == d["rev"] + 1                                            # 내 편집은 내게 다시 오지 않는다
    assert client.patch(f"/api/docs/{doc}/blocks/{p['id']}", json={"text": "주인이 고친 글"}).status_code == 200
    got = g.get(f"/s/{sid}/changes", params={"since": mine["rev"], "epoch": d["epoch"]}).json()
    assert [(i["t"], i["text"], i["by"]) for i in got["items"]] == [("text", "주인이 고친 글", share.HOST)]
    assert client.get(f"/api/docs/{doc}/share/changes", params={"since": mine["rev"], "epoch": d["epoch"]}).json()["items"] == []


def test_split_and_merge_reach_everyone_as_changed_blocks(client, tmp_path, monkeypatch):
    doc, st = _start(client, tmp_path)
    sid = st["id"]
    a, me_a = _guest(st, "가")
    b, _ = _guest(st, "나")
    d = a.get(f"/s/{sid}/doc").json()
    p = _first_para(d["blocks"])
    assert a.patch(f"/s/{sid}/blocks/{p['id']}", json={"text": "앞글뒷글"}, headers=X).status_code == 200
    r = a.post(f"/s/{sid}/split", json={"id": p["id"], "offset": 2}, headers=X)
    assert r.status_code == 200, r.text
    sp = r.json()
    new = sp["focus"]["id"]
    assert not sp["reload"] and sp["blocks"] and sp["rev"] == d["rev"] + 2 and new != p["id"]
    assert server._sess(doc).texts[p["id"]] == "앞글" and server._sess(doc).texts[new] == "뒷글"
    for who, full in ((b, False), (client, True)):                                                        # 다른 손님 · 주인
        url = f"/s/{sid}/changes" if not full else f"/api/docs/{doc}/share/changes"
        got = who.get(url, params={"since": d["rev"], "epoch": d["epoch"]}).json()
        assert [i["t"] for i in got["items"]] == ["text", "tops"] and got["rev"] == sp["rev"], got
        top = got["items"][1]
        blocks = top["resp"]["tops"]["blocks"] if full else top["blocks"]
        assert ("resp" in top) == full and _texts(blocks)[p["id"]] == "앞글" and _texts(blocks)[new] == "뒷글"
    # 주인이 8114 에서 합친 것은 미들웨어가 응답을 읽어 채운다 — 손님은 「다시 읽기」 가 아니라 바뀐 블록을 받는다
    m = client.post(f"/api/docs/{doc}/merge", json={"id": p["id"], "dir": "next"})
    assert m.status_code == 200 and m.json()["rev"] == sp["rev"] + 1
    got = b.get(f"/s/{sid}/changes", params={"since": sp["rev"], "epoch": d["epoch"]}).json()
    assert [i["t"] for i in got["items"]] == ["tops"] and _texts(got["items"][0]["blocks"])[p["id"]] == "앞글뒷글" and new not in _texts(got["items"][0]["blocks"])
    assert a.post(f"/s/{sid}/split", json={"id": p["id"], "offset": "2"}, headers=X).status_code == 400
    assert a.post(f"/s/{sid}/merge", json={"id": p["id"], "dir": "up"}, headers=X).status_code == 400
    # 실행 취소처럼 바뀐 블록을 안 주는 편집은 기다린 뒤 「다시 읽기」
    assert client.post(f"/api/docs/{doc}/undo").status_code == 200
    monkeypatch.setattr(share, "FEED_WAIT", 0.0)
    assert b.get(f"/s/{sid}/changes", params={"since": m.json()["rev"], "epoch": d["epoch"]}).json()["reload"] is True
    assert client.get(f"/api/docs/{doc}/share/changes", params={"since": m.json()["rev"], "epoch": d["epoch"]}).json()["rev"] == m.json()["rev"] + 1   # 주인은 제 응답으로 이미 안다


def _texts(blocks, out=None):
    out = {} if out is None else out
    for b in blocks:
        if b["type"] == "paragraph":
            out[b["id"]] = b["text"]
        for c in b.get("cells") or ():
            _texts(c["blocks"], out)
    return out


def test_a_paragraph_someone_is_writing_is_closed_to_other_guests(client, tmp_path):
    doc, st = _start(client, tmp_path)
    sid = st["id"]
    a, me_a = _guest(st, "가")
    b, me_b = _guest(st, "나")
    d = a.get(f"/s/{sid}/doc").json()
    p = _first_para(d["blocks"])
    q = {"since": d["rev"], "epoch": d["epoch"], "block": p["id"]}
    assert a.get(f"/s/{sid}/changes", params=q).json()["denied"] is None
    got = b.get(f"/s/{sid}/changes", params=q).json()
    assert got["denied"]["id"] == me_a["id"] and {x["id"]: x["block"] for x in got["people"]}[me_a["id"]] == p["id"]
    r = b.patch(f"/s/{sid}/blocks/{p['id']}", json={"text": "끼어들기"}, headers=X)
    assert r.status_code == 409 and "가 님이 작성 중" in r.json()["detail"]
    assert b.post(f"/s/{sid}/split", json={"id": p["id"], "offset": 0}, headers=X).status_code == 409
    assert a.patch(f"/s/{sid}/blocks/{p['id']}", json={"text": "가가 쓴 글"}, headers=X).status_code == 200
    host = client.get(f"/api/docs/{doc}/share/changes", params={"since": d["rev"], "epoch": d["epoch"], "block": p["id"]}).json()
    assert host["denied"]["id"] == me_a["id"]                                                              # 주인 화면도 같은 표시를 받는다
    a.post(f"/s/{sid}/leave", headers=X)
    assert a.get(f"/s/{sid}/doc").status_code == 401
    assert b.patch(f"/s/{sid}/blocks/{p['id']}", json={"text": "이제 됨"}, headers=X).status_code == 200


def test_the_share_port_serves_only_the_guest_app(client, tmp_path, monkeypatch):
    """공유 포트를 실제로 연다 — 손님 화면은 나오고 8114 의 끝점은 없다. 끄면 닫힌다."""
    import socket

    import requests
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        free = sk.getsockname()[1]
    monkeypatch.setenv("NFM_SHARE_PORT", str(free))
    monkeypatch.setenv("NFM_SHARE_HOST", "127.0.0.1")
    lis = share_api._Listener()                                                             # 진짜로 여는 것(_clean 이 막은 것은 원래 것의 start)
    monkeypatch.setattr(share_api, "LISTENER", lis)
    try:
        doc, st = _start(client, tmp_path)
        assert st["listen"] == {"port": free, "host": "127.0.0.1", "running": True, "error": None} and st["link"] == f"http://127.0.0.1:{free}/s/{st['id']}"
        assert requests.get(f"{st['link']}/info", timeout=5).json() == {"active": True, "joined": False}
        assert requests.get(f"http://127.0.0.1:{free}/api/docs/{doc}", timeout=5).status_code == 404
        other = share_api._Listener()
        assert other.start() is False and "열지 못했습니다" in other.error                  # 이미 쓰는 포트
        monkeypatch.setattr(share_api, "CLOSE_AFTER", 0.6)
        client.delete(f"/api/docs/{doc}/share")
        assert requests.get(f"{st['link']}/info", timeout=5).json() == {"active": False, "joined": False}   # 잠깐은 열어 둔다 — 손님 화면이 끝난 것을 안다
        time.sleep(1.5)
        with pytest.raises(requests.ConnectionError):                                      # 그 뒤 켜진 공유가 없으면 닫는다
            requests.get(f"http://127.0.0.1:{free}/s/{st['id']}/info", timeout=2)
    finally:
        lis.stop()
