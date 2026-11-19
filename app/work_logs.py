"""작업 진행 에이전트가 읽는 로그(spec_작업에이전트 ② §8) — 사용자 2026-11-16 "에이전트는 … 모든 로그에 접근이 가능해야 하고".

에이전트(`app/work_guide.py`)가 「무슨 일이 있었나 · 왜 멈췄나」 를 설명할 때 읽는 **읽기 전용** 창구다. 로그를 새로 만들지 않는다 — 이미 남는 기록을 한 꼴(글 줄)로 읽어 줄 뿐이다.

- 로그의 종류는 `SOURCES`(이름 · 화면 말 · 무엇이 적히나): `work` 작업 기록(log.jsonl) · `peers` 함께 쓰는 문서의 작업 기록 · `verify` 검증 기록 · `agent` 에이전트 대화 기록 ·
  `zones` 편집 구역 LLM 검토 기록(마지막 실행 — 작업 폴더 `zones/llm-last.json`) ·
  `llm` LLM 호출 기록(서버를 켠 뒤) · `server` 서버 로그(경고 · 오류 — 서버를 켠 뒤, `install()` 이 붙인 듣는 이가 모은다).
- `index(wid)` = 로그마다 지금 몇 줄인가(프롬프트의 `logs.index`) · `recent(wid)` = 작업 기록의 끝 몇 줄(프롬프트에 늘 싣는다) · `read(wid, name, n, find)` = 그 로그의 끝 n 줄(find 가 있으면 그 글이 든 줄만).
- 한 줄은 `LINE` 자까지, 한 번에 `N_MAX` 줄까지 — 문단 글(글 고침 기록의 before · after)은 짧게 줄이고, 키처럼 보이는 글(`sk-…`)은 가린다. 문서 · 기록은 바꾸지 않는다.
새 로그(기록 파일 · 실행 기록)를 만들면 `SOURCES` 와 읽는 함수에 더한다 — 「모든 로그」 가 이 목록이다."""
import json
import logging
import re
import threading
import time
from collections import deque

from app import agent_settings, works

LINE = 240          # 한 줄의 길이
N_MAX = 80          # 한 번에 읽는 줄 수
N_DEFAULT = 30
RECENT = 12         # 프롬프트에 늘 싣는 작업 기록의 끝 줄 수
PEERS_MAX = 12      # 함께 쓰는 문서 수
SERVER_MAX = 400    # 서버 로그로 모아 두는 줄 수
SOURCES = (
    ("work", "작업 기록", "이 문서의 기록 — 올리기 · 글 고침 · 구조·서식 편집 · 헤딩·표 분석 · 프로젝트 구성(확정 · 계획 · 반영) · 취합·이관의 실행 · LLM 호출(모델 · 시간 · 비용) · 검증 · 내려받기"),
    ("peers", "함께 쓰는 문서의 작업 기록", "같은 프로젝트 · 워크플로우 · 라운드의 다른 문서(이관의 사업계획서 · 취합의 기관 문서 …)의 기록 — 줄 머리에 그 문서의 이름"),
    ("verify", "검증 기록", "가져오기 검증 · 출력파일 검증의 실행마다 결과(상태 · 걸린 시간 · 단계마다 상태)"),
    ("agent", "에이전트 대화 기록", "이 문서의 에이전트 턴(작업 진행 · 편집) — 사람의 글 · 에이전트의 답 · 고른 행동 · 끝(실행함 · 멈춤 · 건너뜀) · 오류"),
    ("zones", "편집 구역 LLM 검토 기록", "이 문서의 마지막 편집 구역 LLM 검토 — 보낸 후보 수 · 지정 · 그대로 · 버린 답 · 요약, 후보마다 LLM 이 정한 값(또는 그대로)과 까닭, 버린 답과 까닭"),
    ("llm", "LLM 호출 기록", "서버를 켠 뒤의 모든 LLM 호출(어느 에이전트 · 모델 · 걸린 시간 · 비용 · 오류) — 문서를 가리지 않는다"),
    ("server", "서버 로그", "서버를 켠 뒤의 경고 · 오류(Traceback 포함) — 문서를 가리지 않는다"),
)
NAMES = tuple(s[0] for s in SOURCES)
TITLE = {s[0]: s[1] for s in SOURCES}
_SECRET = re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}")
_TEXT_KEYS = ("before", "after", "text", "prompt", "response")   # 문서·대화의 글 — 짧게 줄인다(기록을 읽는 목적은 무슨 일이 있었나이지 글 자체가 아니다)


def _clip(text, n=LINE):
    s = _SECRET.sub("sk-…", " ".join(str(text if text is not None else "").split()))
    return s if len(s) <= n else s[:n - 1] + "…"


def _when(t):
    try:
        return time.strftime("%m-%d %H:%M:%S", time.localtime(float(t)))
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def _value(k, v):
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, (int, float)) or v is None:
        return str(v)
    if isinstance(v, str):
        return _clip(v, 40 if k in _TEXT_KEYS else 90)
    return _clip(json.dumps(v, ensure_ascii=False, separators=(",", ":")), 100)


def _event(e, head=""):
    """기록 한 줄(`works.log` 의 사건) → 글 한 줄 「11-16 14:02:05 divisionPlan applied=12 …」."""
    rest = " ".join(f"{k}={_value(k, v)}" for k, v in e.items() if k not in ("t", "kind") and v not in (None, "", [], {}))
    return _clip(f"{_when(e.get('t'))} {head}{e.get('kind') or '?'} {rest}".rstrip())


# ---- 로그마다 읽기(옛 것부터의 글 줄) ---------------------------------------------------------------------------------

def _work(wid):
    return [_event(e) for e in works.events(wid)]


def _peers(wid):
    t = (works.work(wid) or {}).get("task") or {}
    if not (t.get("project") and t.get("job")):
        return []
    same = [w for w in works.list_works() if w.get("id") != wid and all(((w.get("task") or {}).get(k) or (1 if k == "round" else "")) == (t.get(k) or (1 if k == "round" else "")) for k in ("project", "job", "round"))]
    rows = []
    for w in same[:PEERS_MAX]:
        name = _clip(works.shown(w) if w.get("name") else w.get("id"), 40)
        rows += [(e.get("t") or 0, _event(e, f"[{name}] ")) for e in works.events(w["id"])]
    return [line for _, line in sorted(rows, key=lambda r: r[0])]


def _verify(wid):
    out = []
    for r in sorted(works.runs(wid), key=lambda r: r.get("n") or 0):
        full = works.run(wid, r.get("n")) or {}
        steps = " · ".join(f"{s.get('title') or s.get('key')}={s.get('status')}" for s in full.get("steps") or [] if isinstance(s, dict))
        out.append(_clip(f"{_when(r.get('at'))} 검증 {r.get('n')}({ {'import': '가져오기', 'edit': '출력파일'}.get(r.get('kind'), r.get('kind')) }) 상태={r.get('status')}"
                         + (f" {full['seconds']}초" if full.get("seconds") is not None else "") + (f" — {steps}" if steps else "")))
    return out


def _agent(wid):
    from app import doc_agent   # doc_agent 가 무겁다 — 부를 때 가져온다
    out = []
    store = doc_agent.Store(wid)
    for row in store.turns():
        rec = store.turn(row.get("id")) or row
        guide = rec.get("kind") == "guide"
        bits = [f"사건={rec.get('event')}" if guide else "편집 턴"]
        said = (rec.get("request") or {}).get("text") if isinstance(rec.get("request"), dict) else rec.get("request")
        if said:
            bits.append(f"사람=「{_clip(said, 60)}」")
        if rec.get("result"):
            bits.append(f"결과=「{_clip(rec['result'], 80)}」")
        if rec.get("reply"):
            bits.append(f"답=「{_clip(rec['reply'], 80)}」")
        if isinstance(rec.get("act"), dict):
            bits.append(f"행동={rec['act'].get('name')}")
        if isinstance(rec.get("ask"), dict):
            bits.append(f"질문={rec['ask'].get('kind')}")
        if guide:
            bits.append(f"끝={rec.get('state')}" + (f"(「{_clip(rec['outcome'], 60)}」)" if rec.get("outcome") else ""))
        if rec.get("llm") is False and guide:
            bits.append("스크립트 답")
        if rec.get("error"):
            bits.append(f"오류={_clip(rec['error'], 100)}")
        out.append(_clip(f"{_when(rec.get('at'))} {rec.get('id')} " + " ".join(bits)))
    return out


def _zones(wid):
    """편집 구역 LLM 검토의 마지막 실행(작업 폴더 `zones/llm-last.json` — app/zones_api.py 가 남긴다: spec_구역 ② §8 「LLM 검토 — 스크립트가 못 정한 것」) → 머리 한 줄 + 후보마다 한 줄 + 버린 답마다 한 줄.
    파일을 바로 읽는다(zones_api 를 가져오지 않는다 — 이 모듈은 가볍게). 프롬프트·답 전문은 싣지 않는다(화면 「지침」 이 맡는다)."""
    d = works.folder(wid)
    p = d / "zones" / "llm-last.json" if d is not None else None
    rec = works._read_json(p) if p is not None and p.is_file() else None
    if not isinstance(rec, dict):
        return []
    when, call = _when(rec.get("t")), rec.get("call") if isinstance(rec.get("call"), dict) else {}
    out = [_clip(f"{when} 편집 구역 LLM 검토 후보={rec.get('candidates')} 지정={rec.get('marked')} 그대로={rec.get('kept')} 버림={rec.get('dropped')}" + (" (후보가 많아 잘라 보냄)" if rec.get("truncated") else "")
                 + f" 모델={call.get('model')} {call.get('ms')}ms" + (f" ${call['costUsd']}" if call.get("costUsd") is not None else "") + (f" 오류={rec['error']}" if rec.get("error") else "")
                 + (f" — {rec['summary']}" if rec.get("summary") else ""), LINE * 2)]
    for it in rec.get("items") or ():
        if isinstance(it, dict):
            label = it.get("label") if isinstance(it.get("label"), dict) else {}
            value = "그대로" if not label else " ".join(f"{k}={'없음' if v is None else v}" for k, v in label.items())
            out.append(_clip(f"{when} {it.get('id')}({it.get('type')} · {it.get('kind')}) {value} — {it.get('reason') or ''}"))
    for r in rec.get("droppedRows") or ():
        if isinstance(r, dict):
            out.append(_clip(f"{when} 버림 {r.get('id')} " + (f"{r.get('dim')}={r.get('value')} " if r.get("dim") else "") + f"— {r.get('why') or ''}"))
    return out


def _llm(_wid):
    rows = list(reversed(agent_settings.runs(None, agent_settings.RUNS_MAX)))   # 옛 것부터
    return [_clip(f"{_when(r.get('t'))} #{r.get('n')} {r.get('agent') or '(등록 안 된 호출)'}({r.get('what')}) 모델={r.get('model')} {r.get('ms')}ms"
                  + (f" ${r['costUsd']}" if r.get("costUsd") is not None else "") + (" 됨" if r.get("ok") else " 답 없음") + (f" 오류={r['error']}" if r.get("error") else "")) for r in rows]


# ---- 서버 로그 — 경고 · 오류를 모아 두는 듣는 이(서버를 켠 뒤의 것만) --------------------------------------------------

_SERVER = deque(maxlen=SERVER_MAX)
_SERVER_LOCK = threading.Lock()


class _Keep(logging.Handler):
    def emit(self, record):
        try:
            text = record.getMessage()
            if record.exc_info:
                text += " | " + " / ".join(x.strip() for x in logging.Formatter().formatException(record.exc_info).splitlines()[-6:])   # Traceback 의 끝 여섯 줄
            with _SERVER_LOCK:
                _SERVER.append(_clip(f"{_when(record.created)} {record.levelname} {record.name} — {text}", LINE * 3))
        except Exception:  # noqa: BLE001 — 기록을 모으다 서버를 멈추지 않는다
            pass


_KEEP = _Keep(level=logging.WARNING)


def install():
    """서버 로그를 모으기 시작한다(여러 번 불러도 한 번만) — 루트와 uvicorn 로거에 경고 이상을 듣는 이를 붙인다."""
    for name in ("", "uvicorn"):
        lg = logging.getLogger(name)
        if _KEEP not in lg.handlers:
            lg.addHandler(_KEEP)


def _server(_wid):
    with _SERVER_LOCK:
        return list(_SERVER)


_READ = {"work": _work, "peers": _peers, "verify": _verify, "agent": _agent, "zones": _zones, "llm": _llm, "server": _server}
assert tuple(_READ) == NAMES


def _lines(wid, name):
    try:
        return _READ[name](wid)
    except Exception as e:  # noqa: BLE001 — 깨진 기록 하나가 에이전트의 답을 막지 않는다
        return [f"(이 로그를 읽지 못했습니다: {type(e).__name__})"]


# ---- 에이전트가 쓰는 꼴 -----------------------------------------------------------------------------------------------

def index(wid):
    """로그마다 → [{log, title, what, lines(지금 줄 수)}] — 프롬프트의 `logs.index`."""
    return [{"log": name, "title": title, "what": what, "lines": len(_lines(wid, name))} for name, title, what in SOURCES]


def recent(wid, n=RECENT):
    """작업 기록의 끝 n 줄 — 프롬프트에 늘 싣는다(읽기를 따로 청하지 않아도 방금 있던 일은 안다)."""
    return _lines(wid, "work")[-max(1, min(int(n), N_MAX)):]


def read(wid, name, n=N_DEFAULT, find=""):
    """그 로그의 끝 n 줄(find 가 있으면 그 글이 든 줄만) → {log, title, find, total(조건에 맞는 줄 수), lines[…]} | {log, error}(그런 로그가 없음)."""
    name = str(name or "").strip()
    if name not in _READ:
        return {"log": _clip(name, 40), "error": "그런 로그가 없습니다 — logs.index 의 log 가운데서 고릅니다: " + " · ".join(NAMES)}
    try:
        n = max(1, min(int(n), N_MAX))
    except (TypeError, ValueError):
        n = N_DEFAULT
    find = _clip(find, 60)
    rows = _lines(wid, name)
    if find:
        rows = [r for r in rows if find.lower() in r.lower()]
    return {"log": name, "title": TITLE[name], "find": find, "total": len(rows), "lines": rows[-n:]}
