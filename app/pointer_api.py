"""포인터 — 같은 문서를 보는 다른 화면에 내 마우스 자리와 「클릭」 을 보인다(spec_포인터 ② §3 · 화면 app/static/pointer.js).
사용자 2026-11-23 "같은 계정으로 로그인되어 있는경우 한 사람이 포인터로 움직이면 다른 사람도 볼 수 있게 해줘, 포인터 상태에서 클릭 하면 클릭이라고 표시되게 해줘".

- 끝점은 WebSocket 하나: `/api/docs/{doc_id}/pointer`. **방 = 문서 id 하나**(메모리 안 — `ROOMS`) · 시작 화면은 방 이름 `home`(2026-11-23 사용자 "첫페이지 부터 포인터 기능 넣어줘" —
  자리 기준 `h` = 시작 화면 요소의 「속성=값」: 서버는 꼴만 본다 · spec_포인터 ② §6). 받은 것을 같은 방의 다른 연결에 나눠 줄 뿐이다:
  들어옴(hi · join) · 움직임(move) · 클릭(click) · 감춤(off) · 이름(name) · 나감(leave).
- **저장하지 않는다 · 문서를 읽거나 잠그지 않는다 · 문서를 바꾸지 않는다**(편집 차례를 올리는 `_bump` 를 지나지 않는다) · **`app.server` 를 import 하지 않는다**(server.py 가 `router` 를 달 뿐).
  그래서 문서 id 가 실제 작업인지도 보지 않는다 — 방에는 문서의 글이 없고 오가는 것은 자리(블록 id · 비율)와 이름뿐이다.
- 지금 앱에는 사용자 계정이 없다(바깥 주소는 Caddy 기본 인증의 계정 하나 — spec_배포) → 접속한 화면은 모두 같은 계정이고 방을 계정으로 나누지 않는다(앱 로그인이 생기면 방 열쇠에 계정을 더한다 — spec_포인터 ④).
- 안전(② §4): 손잡이의 `Origin` 이 있으면 요청의 `Host` 와 같은 출처일 때만 받는다(다른 사이트가 브라우저의 기본 인증을 업고 붙는 것을 막는다 — Caddy 의 「다른 출처 403」 은 GET 인 업그레이드를 안 막는다) ·
  메시지 크기 `MAX_BYTES` · 연결마다 초당 `MAX_RATE`(넘으면 버림) · 방마다 연결 `MAX_ROOM` · 이름 `MAX_NAME` 자 · **받은 JSON 은 정해진 키만 골라 다시 지어 보낸다**(받은 것을 그대로 중계하지 않는다).
- 느린 연결이 다른 연결을 붙잡지 않게 연결마다 보낼 줄(`Peer.q`)과 보내는 일(`_writer`)을 따로 둔다 — 줄이 차면 가장 오래된 것을 버린다(움직임은 새것이 옛것을 대신한다).
- 한 이벤트 루프 안에서만 방을 고친다(await 사이에 방을 고치는 곳이 없다) — 잠금이 없다. 서버 프로세스가 하나일 때의 설계다(8114 하나 — CLAUDE.md 「웹서버」)."""
import asyncio
import json
import math
import re
import secrets
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

MAX_BYTES = 1024      # 메시지 하나의 글자 수 상한 — 넘으면 그 연결을 닫는다(1009)
MAX_RATE = 40         # 연결마다 초당 받는 메시지 수 — 넘는 것은 버린다(화면은 초당 16번쯤 보낸다)
MAX_ROOM = 16         # 방(문서) 하나의 연결 수
MAX_NAME = 16         # 이름 글자 수
MAX_QUEUE = 64        # 연결마다 보낼 줄의 길이
MAX_SHEET = 100000    # 쪽 차례의 상한
MAX_PIECE = 9999      # 쪽에 걸쳐 나뉜 블록의 조각 차례 상한
HELLO_WAIT = 10.0     # 붙은 뒤 이 안에 hello 가 없으면 닫는다(초)
COLORS = ("#e11d48", "#2563eb", "#16a34a", "#d97706", "#9333ea", "#0891b2", "#db2777", "#4d7c0f")   # 흰 종이 위에서 서로 가려지는 여덟 색(이름표는 이 바탕에 흰 글)
KINDS = ("p", "c", "t", "s", "h", "u")   # 자리의 기준 — p 블록(data-id) · c 표 칸(data-cell) · t 표(data-tbl) · s 쪽(몇째 쪽 상자) · h 시작 화면의 요소(「속성=값」 — 방 "home": spec_포인터 ② §6)
#   · u 문서 · 시작 화면 밖의 화면 요소(상단 바 · 도구 줄 · 사이드 패널 · 옆 열 — 「속성=값」: 서버는 꼴만 본다 · ② §7 「화면 어디서나」)

DOC_OK = re.compile(r"[A-Za-z0-9_-]{1,64}")
AT_OK = re.compile(r"[^\x00-\x20\x7f]{1,80}")   # 블록 · 칸 · 표 id — 빈칸 · 제어 글자 없는 80자 안
_CTRL = re.compile(r"[\x00-\x1f\x7f  ]")
_now = time.monotonic

ROOMS: dict = {}   # 문서 id → {연결 id: Peer}


class Peer:
    """연결 하나 — id(방 안에서 그 화면) · name · color · auto(기본 이름 「사용자 N」 의 N — 이름을 정했으면 0) · at(지금 보이는 자리 | None = 안 보임) · q(보낼 줄)."""
    __slots__ = ("id", "name", "color", "auto", "at", "q")

    def __init__(self, name, color, auto):
        self.id, self.name, self.color, self.auto, self.at = secrets.token_hex(4), name, color, auto, None
        self.q = asyncio.Queue(maxsize=MAX_QUEUE)

    def card(self):
        return {"id": self.id, "name": self.name, "color": self.color}


class Rate:
    """초당 상한 — 1초 창 안의 수를 센다(`ok(지금, 상한)` → 받아도 되나)."""
    __slots__ = ("t", "n")

    def __init__(self):
        self.t, self.n = -1.0, 0

    def ok(self, now, limit):
        if now - self.t >= 1.0:
            self.t, self.n = now, 0
        self.n += 1
        return self.n <= limit


def same_origin(origin, host):
    """손잡이의 Origin 과 Host 가 같은 출처인가 — Origin 이 없으면(브라우저가 아닌 손님) 받는다 · 「null」 이나 다른 호스트면 안 받는다."""
    if origin is None:
        return True
    try:
        net = urlsplit(origin).netloc
    except ValueError:
        return False
    return bool(net) and bool(host) and net.lower() == host.lower()


def clean_name(v):
    """받은 이름 → 제어 글자를 빼고 빈칸을 하나로 줄인 `MAX_NAME` 자 안의 글(글이 아니면 빈 글)."""
    if not isinstance(v, str):
        return ""
    return " ".join(_CTRL.sub(" ", v[:MAX_NAME * 8]).split())[:MAX_NAME].strip()


def _unit(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return round(min(1.0, max(0.0, float(v))), 4)


def clean_at(d):
    """받은 자리 → 정해진 키만 다시 지은 자리 {k, a, n, x, y} | None(쓸 수 없는 것 — 버린다).
    k = 기준(KINDS) · a = 그 블록·칸·표의 id(쪽이면 몇째 쪽 — 0부터) · n = 쪽에 걸쳐 나뉜 것의 몇째 조각 · x · y = 그 요소 안의 비율(0~1)."""
    k, a = d.get("k"), d.get("a")
    if k not in KINDS:
        return None
    if k == "s":
        if isinstance(a, bool) or not isinstance(a, int) or not 0 <= a <= MAX_SHEET:
            return None
    elif not isinstance(a, str) or not AT_OK.fullmatch(a):
        return None
    n = d.get("n", 0)
    if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= MAX_PIECE:
        return None
    x, y = _unit(d.get("x")), _unit(d.get("y"))
    if x is None or y is None:
        return None
    return {"k": k, "a": a, "n": n, "x": x, "y": y}


def _dump(m):
    return json.dumps(m, ensure_ascii=False, separators=(",", ":"))


def _push(peer, text):
    """그 연결의 보낼 줄에 — 줄이 찼으면 가장 오래된 것을 버린다."""
    if peer.q.full():
        try:
            peer.q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    peer.q.put_nowait(text)


def _cast(room, m, skip=None):
    """방의 연결 모두에(skip 빼고)."""
    text = _dump(m)
    for p in room.values():
        if p is not skip:
            _push(p, text)


def _color(room, want):
    """그 방에서 쓸 색 — 바란 색이 비어 있으면 그것, 아니면 안 쓰는 첫 색, 다 쓰면 가장 덜 쓰는 색."""
    used = [p.color for p in room.values()]
    if want in COLORS and want not in used:
        return want
    return min(COLORS, key=lambda c: (used.count(c), COLORS.index(c)))


def _auto(room):
    """기본 이름 「사용자 N」 의 N — 그 방에서 안 쓰는 가장 작은 수."""
    taken = {p.auto for p in room.values()}
    n = 1
    while n in taken:
        n += 1
    return n


def _named(room, peer, raw):
    """이름을 정한다 — 비었으면 기본 이름 「사용자 N」(이미 기본 이름이면 그 수 그대로)."""
    name = clean_name(raw)
    if name:
        peer.name, peer.auto = name, 0
    else:
        if not peer.auto:
            peer.auto = _auto(room)
        peer.name = f"사용자 {peer.auto}"


def _load(text):
    """받은 글 → dict | None(JSON 이 아니거나 객체가 아님)."""
    try:
        m = json.loads(text)
    except ValueError:
        return None
    return m if isinstance(m, dict) else None


async def _writer(ws, peer):
    """그 연결의 보낼 줄을 차례로 보낸다 — 못 보내면(끊김) 그만둔다(받는 쪽 고리가 끊김을 본다)."""
    try:
        while True:
            await ws.send_text(await peer.q.get())
    except Exception:   # noqa: BLE001 — 끊긴 연결에 보내기: 까닭을 가리지 않고 그만둔다
        return


async def _text(ws, wait=None):
    """다음 글 메시지 → 글 | None(끊김 · 글이 아닌 것 · 너무 큰 것 — 닫아야 하면 닫는다)."""
    msg = await (asyncio.wait_for(ws.receive(), wait) if wait else ws.receive())
    if msg.get("type") != "websocket.receive":
        return None   # 끊김
    text = msg.get("text")
    if text is None:
        await ws.close(code=1003)   # 글이 아닌 것(바이트)
        return None
    if len(text) > MAX_BYTES:
        await ws.close(code=1009)   # 너무 큼
        return None
    return text


@router.websocket("/api/docs/{doc_id}/pointer")
async def pointer(ws: WebSocket, doc_id: str):
    if not DOC_OK.fullmatch(doc_id) or not same_origin(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=1008)   # 받기 전에 닫는다 → 손잡이가 403 으로 끝난다
        return
    await ws.accept()
    room = peer = task = None
    try:
        try:
            text = await _text(ws, HELLO_WAIT)
        except asyncio.TimeoutError:
            await ws.close(code=1008)
            return
        first = _load(text) if text is not None else None
        if text is None:
            return
        if not first or first.get("t") != "hello":
            await ws.close(code=1008)   # 첫 메시지는 hello 여야 한다
            return
        room = ROOMS.setdefault(doc_id, {})
        if len(room) >= MAX_ROOM:
            if not room:
                ROOMS.pop(doc_id, None)
            room = None
            await ws.send_text(_dump({"t": "full"}))
            await ws.close(code=1013)
            return
        want = first.get("color")
        peer = Peer("", _color(room, want if isinstance(want, str) else ""), 0)
        _named(room, peer, first.get("name"))
        others = [dict(p.card(), at=p.at) for p in room.values()]
        room[peer.id] = peer
        _push(peer, _dump(dict(peer.card(), t="hi", peers=others)))   # 내 것이 먼저 — 그 뒤의 알림이 이 뒤에 선다
        _cast(room, dict(peer.card(), t="join"), skip=peer)
        task = asyncio.create_task(_writer(ws, peer))
        rate = Rate()
        while True:
            text = await _text(ws)
            if text is None:
                return
            if not rate.ok(_now(), MAX_RATE):
                continue
            m = _load(text)
            t = m.get("t") if m else None
            if t in ("move", "click"):
                at = clean_at(m)
                if at:
                    peer.at = at
                    _cast(room, dict(at, t=t, id=peer.id), skip=peer)
            elif t == "off":
                if peer.at is not None:
                    peer.at = None
                    _cast(room, {"t": "off", "id": peer.id}, skip=peer)
            elif t == "name":
                _named(room, peer, m.get("name"))
                _cast(room, {"t": "name", "id": peer.id, "name": peer.name})   # 나에게도 — 서버가 다듬은 이름(비웠으면 기본 이름)을 화면이 안다
    except WebSocketDisconnect:
        pass
    finally:
        if task:
            task.cancel()
        if room is not None and peer is not None and room.pop(peer.id, None) is not None:
            _cast(room, {"t": "leave", "id": peer.id})
            if not room and ROOMS.get(doc_id) is room:
                del ROOMS[doc_id]
