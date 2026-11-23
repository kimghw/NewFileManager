"""포인터(spec_포인터 — app/pointer_api.py): 같은 문서(방)의 다른 연결에 움직임 · 클릭을 나눠 주는 WebSocket 끝점.
`app.server` 를 띄우지 않는다 — `pointer_api.router` 만 단 작은 앱으로 본다(그 모듈은 서버를 모른다: 아래 test_module_stands_alone).
연결 여럿이 한 이벤트 루프를 같이 쓰게 `with TestClient(app)` 안에서 붙는다(with 없이 붙으면 연결마다 루프가 따로라 방의 보낼 줄이 루프를 넘나든다 — 실제 서버는 루프 하나)."""
import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import pointer_api as P

AT = {"k": "p", "a": "p12", "n": 0, "x": 0.25, "y": 0.5}


def url(doc):
    return f"/api/docs/{doc}/pointer"


@pytest.fixture()
def client():
    P.ROOMS.clear()
    app = FastAPI()
    app.include_router(P.router)
    with TestClient(app) as c:
        yield c
    P.ROOMS.clear()


def join(ws, name="", color=""):
    ws.send_json({"t": "hello", "name": name, "color": color})
    hi = ws.receive_json()
    assert hi["t"] == "hi" and hi["id"] and hi["color"] in P.COLORS
    return hi


def test_move_click_off_reach_the_other_screen_only(client):
    with client.websocket_connect(url("doc1")) as a, client.websocket_connect(url("doc1")) as b:
        ha = join(a, "가")
        hb = join(b)
        assert ha["peers"] == [] and hb["peers"] == [{"id": ha["id"], "name": "가", "color": ha["color"], "at": None}]
        assert hb["name"] == "사용자 1" and ha["color"] != hb["color"] and ha["id"] != hb["id"]   # 이름을 안 주면 기본 이름 · 색은 방 안에서 안 겹친다
        assert a.receive_json() == {"t": "join", "id": hb["id"], "name": "사용자 1", "color": hb["color"]}
        a.send_json({"t": "move", **AT})
        assert b.receive_json() == {"t": "move", "id": ha["id"], **AT}
        a.send_json({"t": "click", **AT, "x": 0.3})
        assert b.receive_json() == {"t": "click", "id": ha["id"], **AT, "x": 0.3}
        b.send_json({"t": "move", "k": "s", "a": 3, "n": 0, "x": 0.5, "y": 0.5})   # 쪽 안의 비율(블록이 없는 곳)
        assert a.receive_json() == {"t": "move", "id": hb["id"], "k": "s", "a": 3, "n": 0, "x": 0.5, "y": 0.5}   # 내 움직임 · 클릭은 나에게 돌아오지 않는다 — 다음에 오는 것이 남의 것
        a.send_json({"t": "off"})
        assert b.receive_json() == {"t": "off", "id": ha["id"]}
        a.send_json({"t": "off"})   # 이미 안 보이는 포인터 — 다시 알리지 않는다
        a.send_json({"t": "move", **AT})
        assert b.receive_json()["t"] == "move"
    assert P.ROOMS == {}   # 모두 나가면 방도 없다(저장하지 않는다)


def test_other_room_does_not_receive(client):
    with client.websocket_connect(url("doc1")) as a, client.websocket_connect(url("doc1")) as b, client.websocket_connect(url("doc2")) as c:
        ha, _, hc = join(a), join(b), join(c)
        assert hc["peers"] == [] and a.receive_json()["t"] == "join"
        a.send_json({"t": "move", **AT})
        assert b.receive_json() == {"t": "move", "id": ha["id"], **AT}   # 같은 방은 받았다
        with client.websocket_connect(url("doc2")) as d:
            hd = join(d)
            assert c.receive_json() == {"t": "join", "id": hd["id"], "name": hd["name"], "color": hd["color"]}   # 다른 방에 처음 온 것은 그 방의 들어옴 — doc1 의 움직임이 아니다


def test_newcomer_sees_pointers_already_shown_and_leave_is_told(client):
    with client.websocket_connect(url("doc1")) as b:
        hb = join(b)
        with client.websocket_connect(url("doc1")) as a:
            ha = join(a)
            assert b.receive_json()["t"] == "join"
            a.send_json({"t": "move", **AT})
            assert b.receive_json()["t"] == "move"
            with client.websocket_connect(url("doc1")) as c:
                hc = join(c)
                assert {p["id"]: p["at"] for p in hc["peers"]} == {hb["id"]: None, ha["id"]: AT}   # 늦게 온 화면도 지금 보이는 포인터를 안다
            assert b.receive_json()["t"] == "join" and b.receive_json() == {"t": "leave", "id": hc["id"]}
        assert b.receive_json() == {"t": "leave", "id": ha["id"]}   # 나가면 「나감」 — 그 화면의 포인터를 걷는다


def test_only_known_keys_are_rebuilt_and_bad_messages_dropped(client):
    with client.websocket_connect(url("doc1")) as a, client.websocket_connect(url("doc1")) as b:
        ha = join(a)
        join(b)
        a.send_json({"t": "move", "k": "p", "a": "p1", "n": 2, "x": 5, "y": -3, "id": "spoof", "name": "x", "evil": "<script>"})
        assert b.receive_json() == {"t": "move", "id": ha["id"], "k": "p", "a": "p1", "n": 2, "x": 1.0, "y": 0.0}   # 정해진 키만 · 비율은 0~1 · id 는 서버가 붙인다
        a.send_text("not json")
        a.send_text("[1, 2]")
        a.send_text('{"t":"move","k":"p","a":"p1","n":0,"x":NaN,"y":0}')
        for bad in ({"t": "zzz"}, {"t": "move", "k": "q", "a": "p1", "x": 0, "y": 0}, {"t": "move", "k": "s", "a": "3", "x": 0, "y": 0}, {"t": "move", "k": "s", "a": -1, "x": 0, "y": 0},
                    {"t": "move", "k": "s", "a": True, "x": 0, "y": 0}, {"t": "move", "k": "p", "a": "a b", "x": 0, "y": 0}, {"t": "move", "k": "p", "a": "p" * 81, "x": 0, "y": 0},
                    {"t": "move", "k": "p", "a": "p1", "n": -1, "x": 0, "y": 0}, {"t": "click", "k": "p", "a": "p1", "x": "0", "y": 0}, {"t": "hello", "name": "또"}):
            a.send_json(bad)
        a.send_json({"t": "off"})
        assert b.receive_json() == {"t": "off", "id": ha["id"]}   # 사이의 것은 모두 버려졌다


def test_names_and_colors(client):
    assert P.clean_name("  김\t거화\n님  ") == "김 거화 님" and P.clean_name("가" * 40) == "가" * P.MAX_NAME and P.clean_name(12) == "" and P.clean_name("\x00\x1f") == ""
    with client.websocket_connect(url("doc1")) as a, client.websocket_connect(url("doc1")) as b, client.websocket_connect(url("doc1")) as c:
        ha = join(a, "가" * 40, P.COLORS[3])
        hb = join(b, "", P.COLORS[3])   # 같은 색을 바람 — 이미 쓰는 색이라 다른 색
        hc = join(c, "", "red;x")       # 모르는 색 — 서버의 색
        assert ha["name"] == "가" * P.MAX_NAME and ha["color"] == P.COLORS[3] and hb["color"] == P.COLORS[0] and hc["color"] == P.COLORS[1]
        assert (hb["name"], hc["name"]) == ("사용자 1", "사용자 2")
        assert [a.receive_json()["t"], a.receive_json()["t"], b.receive_json()["t"]] == ["join", "join", "join"]
        b.send_json({"t": "name", "name": " 새  이름 "})
        new = {"t": "name", "id": hb["id"], "name": "새 이름"}
        assert a.receive_json() == new and b.receive_json() == new and c.receive_json() == new   # 나에게도 — 서버가 다듬은 이름
        a.send_json({"t": "name", "name": ""})   # 비우면 기본 이름 — 방에서 안 쓰는 가장 작은 수(1 은 b 가 놓았다)
        assert b.receive_json() == {"t": "name", "id": ha["id"], "name": "사용자 1"}


def test_other_origin_and_bad_doc_id_are_refused(client):
    assert P.same_origin(None, "files.rndsscb.com") and P.same_origin("https://files.rndsscb.com", "files.rndsscb.com") and P.same_origin("http://127.0.0.1:8114", "127.0.0.1:8114")
    assert P.same_origin("https://FILES.rndsscb.com", "files.rndsscb.com")
    assert not P.same_origin("https://evil.example", "files.rndsscb.com") and not P.same_origin("null", "files.rndsscb.com") and not P.same_origin("https://files.rndsscb.com", "")
    assert not P.same_origin("http://127.0.0.1:9999", "127.0.0.1:8114")   # 같은 PC 의 다른 포트도 다른 출처
    for headers in ({"origin": "https://evil.example"}, {"origin": "null"}):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(url("doc1"), headers=headers):
                pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url("a.b")):
            pass
    assert P.ROOMS == {}
    with client.websocket_connect(url("doc1"), headers={"origin": "http://testserver"}) as a:   # 같은 출처(TestClient 의 Host = testserver)
        assert join(a)["peers"] == []


def test_big_message_closes_and_first_must_be_hello(client):
    with client.websocket_connect(url("doc1")) as b:
        join(b)
        with client.websocket_connect(url("doc1")) as a:
            ha = join(a)
            assert b.receive_json()["t"] == "join"
            a.send_text("x" * (P.MAX_BYTES + 1))
            with pytest.raises(WebSocketDisconnect) as e:
                a.receive_json()
            assert e.value.code == 1009
            assert b.receive_json() == {"t": "leave", "id": ha["id"]}
        with client.websocket_connect(url("doc1")) as c:
            c.send_json({"t": "move", **AT})   # hello 없이 움직임부터
            with pytest.raises(WebSocketDisconnect) as e:
                c.receive_json()
            assert e.value.code == 1008
        assert list(P.ROOMS) == ["doc1"] and len(P.ROOMS["doc1"]) == 1   # 방에는 b 만


def test_room_is_capped(client, monkeypatch):
    monkeypatch.setattr(P, "MAX_ROOM", 2)
    with client.websocket_connect(url("doc1")) as a, client.websocket_connect(url("doc1")) as b:
        join(a)
        hb = join(b)
        assert a.receive_json()["t"] == "join"
        with client.websocket_connect(url("doc1")) as c:
            c.send_json({"t": "hello", "name": "셋째"})
            assert c.receive_json() == {"t": "full"}
            with pytest.raises(WebSocketDisconnect):
                c.receive_json()
        b.send_json({"t": "move", **AT})
        assert a.receive_json() == {"t": "move", "id": hb["id"], **AT}   # 못 들어온 화면의 들어옴 · 나감은 방에 알리지 않는다


def test_rate_limit_counts_per_second():
    r = P.Rate()
    assert [r.ok(100.0, 3) for _ in range(5)] == [True, True, True, False, False]
    assert r.ok(100.9, 3) is False and r.ok(101.0, 3) is True   # 1초가 지나면 다시 센다


def test_clean_at():
    assert P.clean_at({"k": "c", "a": "t3:r1c2", "x": 0.123456, "y": 1}) == {"k": "c", "a": "t3:r1c2", "n": 0, "x": 0.1235, "y": 1.0}
    assert P.clean_at({"k": "t", "a": "t3", "n": 4, "x": 0, "y": 0})["n"] == 4 and P.clean_at({"k": "s", "a": 0, "x": 0, "y": 0})["a"] == 0
    assert P.clean_at({"k": "p", "a": "p1", "x": float("inf"), "y": 0}) is None and P.clean_at({"k": "p", "a": "", "x": 0, "y": 0}) is None and P.clean_at({"a": "p1", "x": 0, "y": 0}) is None
    assert P.clean_at({"k": "p", "a": "p1", "n": P.MAX_PIECE + 1, "x": 0, "y": 0}) is None and P.clean_at({"k": "p", "a": "p1", "x": True, "y": 0}) is None


def test_module_stands_alone():
    """포인터 모듈은 앱의 다른 코드를 가져오지 않는다(spec_포인터 ② §3 — `app.server` 를 import 하지 않는다 · 문서를 읽지도 바꾸지도 않는다)."""
    tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
    names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [m for m in names if m == "app" or m.startswith("app.")], names
