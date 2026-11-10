"""헤딩 추출 — LLM 지침 · 판단 기준 관리(spec_헤딩_추출 ② §5).

- 지침 4개: rules(규칙식 제안) · graph(헤딩 그래프·개요레벨) · templates(개요템플릿·서브 템플릿·조정) · tolerance(오차 판단 기준).
  기본본은 저장소 `app/heading_guides_default/<이름>.md`(읽기만), 사용자 사본은 `%LOCALAPPDATA%\\NewFileManager\\headings\\guides\\<이름>.md`
  + 메타 `<이름>.json` {base: 고칠 때의 기본본 sha1, version, updated}. 기본본이 그 뒤 바뀌면 defaultChanged.
- 저장마다 이전 글을 `guides\\history\\<이름>\\<시각>.md` 로 남기고 history.jsonl 에 한 줄. 되돌리기 = 사본 지움(메타 `<이름>.json` 은
  {version, updated} 만 남겨 version 이 0 으로 안 돌아감 — 되돌리기 전 판을 든 저장은 409).
- tolerance 지침 맨 앞 ```json 블록 = 스크립트가 읽는 숫자 문턱의 단일 원본(`tolerance()`)."""
import hashlib
import json
import math
import re
import threading
import time
from pathlib import Path

from app import heading_rules as R

NAMES = ("rules", "graph", "templates", "tolerance", "tables")
TITLES = {"rules": "규칙식 제안 지침", "graph": "헤딩 그래프·개요레벨 지침", "templates": "개요템플릿·서브 템플릿·조정 지침",
          "tolerance": "오차(같은 서식) 판단 기준", "tables": "표 구조(행헤더·열헤더·필드·서브 테이블) 지침"}
DEFAULT_DIR = Path(__file__).with_name("heading_guides_default")
TEXT_MAX = 40_000
_LOCK = threading.RLock()
_MEMORY = {}  # 저장 끔일 때 {이름: (글, 메타)}

TOLERANCE_DEFAULT = {
    "leadSpaces": 1, "leadMm": 2.5, "indentMm": 1.0, "firstLineMm": 1.0, "sizePt": 0.5, "spacePt": 2.0, "gapPt": 4.0,
    "lineSpacingPct": 10, "lineSpacingPt": 1.0, "ratioPct": 5, "spacingPct": 5,
    "fontAliases": [["돋움", "돋움체", "Dotum", "DotumChe"], ["바탕", "바탕체", "Batang", "BatangChe"], ["굴림", "굴림체", "Gulim", "GulimChe"],
                    ["한양중고딕", "HY중고딕", "HYGothic-Medium"], ["한양견고딕", "HY견고딕", "HYGothic-Extra"], ["함초롬바탕", "HCR Batang"],
                    ["함초롬돋움", "HCR Dotum"], ["맑은 고딕", "Malgun Gothic"]],
    "colors": [["#000000", None]],
}


def _sha1(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _check(name):
    if name not in NAMES:
        raise KeyError(name)


def _dir():
    d = R.store_dir()
    return d / "guides" if d is not None else None


def default_text(name):
    _check(name)
    p = DEFAULT_DIR / f"{name}.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _saved(name):
    """(사용자 글, 메타) | (None, 메타 — 되돌린 뒤 남은 {version, updated}) | (None, None)."""
    d = _dir()
    if d is None:
        return _MEMORY.get(name, (None, None))
    p, m = d / f"{name}.md", d / f"{name}.json"
    try:
        meta = json.loads(m.read_text(encoding="utf-8")) if m.is_file() else None
    except (OSError, ValueError):
        meta = {}
    if meta is not None and not isinstance(meta, dict):
        meta = {}
    if not p.is_file():
        return None, meta
    return p.read_text(encoding="utf-8"), meta or {}


def get(name):
    """{name, title, text(지금 쓰는 글), default, custom(사용자 사본 여부), sha1, defaultSha1, base, defaultChanged, version, updated}."""
    _check(name)
    with _LOCK:
        default = default_text(name)
        text, meta = _saved(name)
    custom = text is not None
    cur = text if custom else default
    base = (meta or {}).get("base") if custom else None  # 되돌린 뒤 남은 메타의 base 는 사본이 없으면 안 보임
    return {"name": name, "title": TITLES[name], "text": cur, "default": default, "custom": custom, "sha1": _sha1(cur),
            "defaultSha1": _sha1(default), "base": base, "defaultChanged": bool(custom and base and base != _sha1(default)),
            "version": (meta or {}).get("version", 0), "updated": (meta or {}).get("updated")}


def listing():
    return [{k: v for k, v in get(n).items() if k not in ("text", "default")} for n in NAMES]


def save(name, text, *, expect=None, reason=""):
    """사용자 사본 저장 → get(name). expect = 기대 version(다르면 R.StaleVersion). 이전 사본은 이력으로 남긴다."""
    _check(name)
    if not isinstance(text, str) or len(text) > TEXT_MAX:
        raise ValueError(f"지침 글은 {TEXT_MAX:,}자 이하의 문자열")
    if name == "tolerance":
        parse_tolerance(text)  # 숫자 블록이 깨졌으면 ValueError
    with _LOCK:
        old, meta = _saved(name)
        meta = meta or {}
        expect = R.expect_version(expect)  # [1]·{}·'x' 는 ValueError(→ API 400)
        if expect is not None and expect != int(meta.get("version", 0)):
            raise R.StaleVersion(f"지침 {name} 이 바뀌었습니다(지금 {meta.get('version', 0)}, 요청 {expect})")
        version = int(meta.get("version", 0)) + 1
        new_meta = {"base": meta.get("base") if old is not None and meta.get("base") else _sha1(default_text(name)),
                    "version": version, "updated": round(time.time(), 3)}
        d = _dir()
        if d is None:
            _MEMORY[name] = (text, new_meta)
        else:
            d.mkdir(parents=True, exist_ok=True)
            if old is not None:
                h = d / "history" / name
                h.mkdir(parents=True, exist_ok=True)
                (h / f"{time.strftime('%Y%m%d-%H%M%S')}-v{meta.get('version', 0)}.md").write_text(old, encoding="utf-8")
            R._write_json(d / f"{name}.json", new_meta)
            tmp = d / f"{name}.md.tmp"
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(d / f"{name}.md")
        R.append_history({"kind": "guide", "name": name, "action": "save", "version": version, "sha1": _sha1(text), "reason": reason})
    return get(name)


def rebase(name):
    """사용자 사본의 기준을 지금 기본본으로(기본본 바뀜 알림을 확인했다는 뜻) → get(name)."""
    _check(name)
    with _LOCK:
        text, meta = _saved(name)
        if text is None:
            return get(name)
        meta = {**(meta or {}), "base": _sha1(default_text(name))}
        d = _dir()
        if d is None:
            _MEMORY[name] = (text, meta)
        else:
            R._write_json(d / f"{name}.json", meta)
        R.append_history({"kind": "guide", "name": name, "action": "rebase", "version": meta.get("version", 0)})
    return get(name)


def reset(name, reason=""):
    """기본본으로 되돌리기 — 사용자 사본을 이력으로 옮기고 지움. 메타는 {version+1, updated} 만 남긴다(0 으로 돌아가면 되돌리기 전
    판을 든 탭의 저장이 409 없이 통과 — ABA). 사본이 없으면 글이 안 바뀌니 version 도 그대로."""
    _check(name)
    with _LOCK:
        old, meta = _saved(name)
        version = int((meta or {}).get("version", 0))
        if old is not None:
            version += 1
            tomb = {"version": version, "updated": round(time.time(), 3), "base": (meta or {}).get("base")}  # base 도 남김 — 사본을 못 지우면 그대로 쓰임
            d = _dir()
            if d is None:
                _MEMORY[name] = (None, tomb)
            else:
                h = d / "history" / name
                h.mkdir(parents=True, exist_ok=True)
                (h / f"{time.strftime('%Y%m%d-%H%M%S')}-v{version - 1}-reset.md").write_text(old, encoding="utf-8")
                R._write_json(d / f"{name}.json", tomb)  # 메타 먼저 — 사본을 못 지워도 version 은 올라 있음
                (d / f"{name}.md").unlink(missing_ok=True)
        R.append_history({"kind": "guide", "name": name, "action": "reset", "version": version, "reason": reason})
    return get(name)


def snapshot():
    """실행 기록용 — {이름: {sha1, custom, text}}."""
    return {n: {k: g[k] for k in ("sha1", "custom", "text", "version")} for n in NAMES for g in [get(n)]}


_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.S)


def parse_tolerance(text):
    """tolerance 지침 글 → 문턱 dict(기본값 위에 덮음). json 블록이 없으면 기본값, 깨졌으면 ValueError."""
    m = _JSON_BLOCK.search(text or "")
    if not m:
        return dict(TOLERANCE_DEFAULT)
    try:
        data = json.loads(m.group(1))
    except ValueError as e:
        raise ValueError(f"오차 기준 json 블록을 읽을 수 없습니다: {e}")
    if not isinstance(data, dict):
        raise ValueError("오차 기준 json 블록은 객체여야 합니다")
    out = dict(TOLERANCE_DEFAULT)
    for k, v in data.items():
        if k in ("fontAliases", "colors"):
            if not isinstance(v, list) or not all(isinstance(g, list) for g in v):
                raise ValueError(f"{k} 는 목록의 목록")
            out[k] = v
        elif k in TOLERANCE_DEFAULT:  # NaN 이면 모든 차이가 「오차 안」, true 는 숫자가 아님
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ValueError(f"{k} 는 0 이상의 유한한 숫자")
            out[k] = v
        else:
            out.setdefault("extra", {})[k] = v
    return out


def tolerance():
    return parse_tolerance(get("tolerance")["text"])
