"""양식 테마 — 테이블 타입 · 구분 기준 타입 · 개요 템플릿을 **테마마다 YAML 파일 하나**로 저장하고 관리한다(spec_양식작성 ② §5-7).
2026-11-26 사용자 "여기 지침에 테이블 타입 및 작성방법 을 저장하고 관리하도록 했으면 좋겟어. 1. 본문 테이블 … 2. 헤딩 테이블 … 3. 그림 테이블 … 해당하지 않으면 추가로 타입을 정의하고
해당한다면 타입으 ㄹ명확히 이야기 하는거지." · "테이블 말고 구분기준 타입 도 넣었으면 좋겠어 …" · "연구개발 과제 기본 템플릿, 자주사용하는 템플릿도 사전에 정의 … yaml 파일로 관리하면 어떨까? 테마마다."

- 기본본 = 저장소 `app/form_themes_default/<테마 id>.yaml`(읽기만 — `common` 공통 · `rnd` 연구개발과제). 이 PC 의 사본 = `%LOCALAPPDATA%\\NewFileManager\\form_themes\\<테마 id>.yaml`
  (env `NFM_FORM_THEMES` 가 폴더 · `off`·`0` 이면 메모리만). 이 PC 의 모든 문서 · 계정이 같이 쓴다(작업 폴더의 것이 아니다).
- 파일 하나 = 테마 하나: `id` · `name` · `docs`(해당 문서) · `signs`(그 테마의 문서를 알아보는 단서) · `division`(구분 기준 타입 — 중요하게 볼 항목 [{id, name, how}]) ·
  `templates`(개요 템플릿 [{id, name, levels[레벨마다 레터], how}]) · `tables`(테이블 타입 [{id, name, signs, how}]) · `added`(더한 항목 {division|templates|tables: […]} — LLM 이 새로 정의한 것: 항목에 `src: llm` · `work` · `at`).
- 합치기: 같은 테마 id 면 **사본 파일에 적힌 키가 먼저**(사본에 없는 키는 기본본) · `added` 의 항목은 그 뒤에 붙는다(같은 id 가 이미 있으면 덮지 않는다). 항목마다 출처 `src` = default | user | llm.
- `add` · `define` 은 LLM 이 정의한 항목 · 테마를 사본에 더한다 — **같은 이름이 있으면 덮지 않고 있는 것의 id 를 돌려주고, id 가 겹치면 새 id 를 짓는다**.
- YAML 은 `yaml.safe_load` · `safe_dump` 만. 사람이 고친 사본의 글(주석 포함)은 그대로 둔다 — `added` 가 맨 끝 키일 때는 그 덩이만 바꿔 쓴다.

**순수 모듈** — 다른 app 코드를 가져오지 않는다(끝점은 `app/form_themes_api.py` · 04 작성 지침 보완이 `brief` 로 자료에 싣는다)."""
import hashlib
import os
import re
import tempfile
import threading
from pathlib import Path

import yaml

DEFAULT_DIR = Path(__file__).with_name("form_themes_default")
ID = re.compile(r"[a-z][a-z0-9_]{0,39}")
KINDS = ("division", "templates", "tables")
KIND_NAMES = {"division": "구분 기준 타입", "templates": "템플릿", "tables": "테이블 타입"}
BASE_KEYS = ("name", "docs", "signs", *KINDS)   # 사본이 기본본을 덮는 키
ORDER = ("common", "rnd")   # 보이는 차례의 앞(그 밖은 id 순)
TEXT_MAX = 20_000
ITEMS_MAX, LEVELS_MAX, DOCS_MAX = 40, 10, 20
NAME_MAX, LETTER_MAX, SIGNS_MAX, HOW_MAX = 40, 20, 500, 700
SRCS = ("default", "user", "llm")

_LOCK = threading.RLock()
_MEMORY = {}   # 저장 끔일 때 {테마 id: 사본 글}
_CACHE = {}    # {파일 경로: (mtime_ns, size, 읽은 것)} — 자리 목록을 읽을 때마다 부르므로 파일을 다시 풀지 않는다


def store_dir():
    """이 PC 의 사본 폴더 Path | None(메모리만)."""
    env = os.environ.get("NFM_FORM_THEMES", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "form_themes"


def _one(value, n):
    t = "" if value is None or isinstance(value, (bool, list, dict, tuple, set)) else " ".join(str(value).split())   # 수 · 날짜(따옴표 없이 적은 「2026-11-26」)도 글로
    return t if len(t) <= n else t[:n - 1] + "…"


def _item(kind, raw, strict):
    """항목 하나를 정리 → dict | None(쓸 수 없음). strict 면 꼴이 틀린 것을 ValueError 로."""
    def bad(why):
        if strict:
            raise ValueError(f"{KIND_NAMES[kind]} 항목 {why}")
        return None
    if not isinstance(raw, dict):
        return bad("은 「id · name · …」 을 가진 묶음이어야 합니다")
    iid, name = raw.get("id"), _one(raw.get("name"), NAME_MAX)
    if not isinstance(iid, str) or not ID.fullmatch(iid):
        return bad(f"의 id 는 영문 소문자로 시작하는 영문 소문자 · 숫자 · _ 40자까지입니다({raw.get('id')!r})")
    if not name:
        return bad(f"「{iid}」 에 name(이름)이 없습니다")
    out = {"id": iid, "name": name}
    if kind == "templates":
        levels = raw.get("levels")
        if not isinstance(levels, list) or not levels or len(levels) > LEVELS_MAX or not all(isinstance(x, str) and _one(x, LETTER_MAX) for x in levels):
            return bad(f"「{iid}」 의 levels 는 레벨마다 레터를 따옴표로 감싸 적은 목록입니다(1~{LEVELS_MAX}개 — 따옴표 없는 「1.」 은 수로 읽힙니다)")
        out["levels"] = [_one(x, LETTER_MAX) for x in levels]
    if kind == "tables":
        out["signs"] = _one(raw.get("signs"), SIGNS_MAX)
    out["how"] = _one(raw.get("how"), HOW_MAX)
    for k in ("src", "work", "at"):   # 더한 항목의 출처(누가 · 어느 작업 · 언제)
        if _one(raw.get(k), 40):
            out[k] = _one(raw.get(k), 40)
    return out


def _items(kind, raw, strict):
    if raw is None:
        return []
    if not isinstance(raw, list):
        if strict:
            raise ValueError(f"{kind} 는 항목의 목록이어야 합니다")
        return []
    out, seen = [], set()
    for x in raw:
        it = _item(kind, x, strict)
        if it is None:
            continue
        if it["id"] in seen:
            if strict:
                raise ValueError(f"{KIND_NAMES[kind]} 의 id 「{it['id']}」 가 두 번 나옵니다")
            continue
        seen.add(it["id"])
        out.append(it)
    if len(out) > ITEMS_MAX:
        if strict:
            raise ValueError(f"{KIND_NAMES[kind]} 는 {ITEMS_MAX}개까지입니다")
        out = out[:ITEMS_MAX]
    return out


def parse(text, tid=None, strict=True):
    """YAML 글 → 정리한 테마 {id, keys(글에 적힌 키), name, docs, signs, division, templates, tables, added{…}, src?, work?, at?}. strict 면 틀린 꼴은 ValueError(화면에서 고친 글의 검사),
    아니면 쓸 수 있는 것만 남긴다(저장된 파일 읽기 — 한 항목이 깨졌다고 테마가 사라지지 않게)."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("YAML 글이 비었습니다")
    if len(text) > TEXT_MAX:
        raise ValueError(f"YAML 글은 {TEXT_MAX:,}자까지입니다")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        raise ValueError("YAML 을 읽을 수 없습니다" + (f"({mark.line + 1}번째 줄 — {getattr(e, 'problem', '') or '꼴이 틀림'})" if mark else f"({e})")) from e
    if not isinstance(data, dict):
        raise ValueError("YAML 의 맨 위는 「키: 값」 묶음이어야 합니다")
    got = data.get("id", tid)
    if not isinstance(got, str) or not ID.fullmatch(got) or (tid is not None and got != tid):
        if strict or tid is None:
            raise ValueError(f"id 는 「{tid}」 여야 합니다" if tid else "id 는 영문 소문자로 시작하는 영문 소문자 · 숫자 · _ 40자까지입니다")
        got = tid
    docs = data.get("docs")
    if docs is not None and not isinstance(docs, list):
        if strict:
            raise ValueError("docs 는 문서 이름의 목록이어야 합니다")
        docs = []
    added = data.get("added")
    if added is not None and not isinstance(added, dict):
        if strict:
            raise ValueError("added 는 {division · templates · tables: 항목 목록} 이어야 합니다")
        added = {}
    out = {"id": got, "keys": [k for k in BASE_KEYS if k in data], "name": _one(data.get("name"), NAME_MAX), "docs": [_one(x, NAME_MAX) for x in (docs or [])[:DOCS_MAX] if _one(x, NAME_MAX)],
           "signs": _one(data.get("signs"), SIGNS_MAX), **{k: _items(k, data.get(k), strict) for k in KINDS},
           "added": {k: _items(k, (added or {}).get(k), strict) for k in KINDS}}
    for k in ("src", "work", "at"):
        if _one(data.get(k), 40):
            out[k] = _one(data.get(k), 40)
    if strict and "name" in data and not out["name"]:
        raise ValueError("name(테마 이름)이 비었습니다")
    return out


def _read(path):
    """파일의 글 | None — 고친 시각으로 다시 읽는다."""
    try:
        st = path.stat()
    except OSError:
        _CACHE.pop(str(path), None)
        return None
    hit = _CACHE.get(str(path))
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    _CACHE[str(path)] = (st.st_mtime_ns, st.st_size, text)
    return text


def default_text(tid):
    return _read(DEFAULT_DIR / f"{tid}.yaml") if ID.fullmatch(tid or "") else None


def copy_text(tid):
    if not ID.fullmatch(tid or ""):
        return None
    d = store_dir()
    with _LOCK:
        return _MEMORY.get(tid) if d is None else _read(d / f"{tid}.yaml")


_PARSED = {}   # {(테마 id, 기본|사본, 글의 sha1): 읽은 것}


def _parsed(tid, text, which):
    if text is None:
        return None
    key = (tid, which, hashlib.sha1(text.encode("utf-8")).hexdigest())
    if key not in _PARSED:
        try:
            got = parse(text, tid, strict=False)
        except ValueError:
            got = None
        for k in [k for k in _PARSED if k[:2] == key[:2]]:
            del _PARSED[k]
        _PARSED[key] = got
    return _PARSED[key]


def ids():
    """테마 id 들 — 공통 · 연구개발과제가 앞, 그 밖은 id 순(기본본 + 사본)."""
    found = {p.stem for p in DEFAULT_DIR.glob("*.yaml") if ID.fullmatch(p.stem)}
    d = store_dir()
    with _LOCK:
        if d is None:
            found |= set(_MEMORY)
        elif d.is_dir():
            found |= {p.stem for p in d.glob("*.yaml") if ID.fullmatch(p.stem)}
    return [t for t in ORDER if t in found] + sorted(found - set(ORDER))


def _bare(item):
    return {k: v for k, v in item.items() if k not in ("src", "work", "at")}


def get(tid):
    """합친 테마 {id, name, docs, signs, division, templates, tables, custom(사람이 고친 사본이 있음), default(기본본이 있음), src?} | None(없는 테마 · 읽을 수 없음). 항목마다 src(default | user | llm)."""
    if not isinstance(tid, str) or not ID.fullmatch(tid):
        return None
    d, c = _parsed(tid, default_text(tid), "default"), _parsed(tid, copy_text(tid), "copy")
    if d is None and c is None:
        return None
    base = d or {"name": "", "docs": [], "signs": "", **{k: [] for k in KINDS}}
    out = {"id": tid, "name": base["name"], "docs": list(base["docs"]), "signs": base["signs"], "custom": False, "default": d is not None}
    for k in KINDS:
        out[k] = [{**_bare(x), "src": "default"} for x in base[k]]
    if c is not None:
        mine = c.get("src") if d is None and c.get("src") in ("user", "llm") else "user"   # 기본본이 없는 테마(LLM 이 정의한 테마)의 항목은 그 테마의 출처
        for k in c["keys"]:
            out["custom"] = True
            if k in KINDS:
                was = [_bare(x) for x in (d[k] if d else [])]
                out[k] = [{**_bare(x), "src": "default" if _bare(x) in was else mine} for x in c[k]]
            else:
                out[k] = c[k]
        for k in KINDS:
            have = {x["id"] for x in out[k]}
            for x in c["added"][k]:
                if x["id"] not in have and len(out[k]) < ITEMS_MAX:
                    have.add(x["id"])
                    out[k].append({**x, "src": x.get("src") if x.get("src") in ("user", "llm") else "llm"})
        if d is None and c.get("src") in ("user", "llm"):
            out["src"] = c["src"]
    out["name"] = out["name"] or tid
    return out


def listing():
    return [t for t in (get(i) for i in ids()) if t is not None]


def _dump(data):
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000, default_flow_style=False)


def _has_added(c):
    return c is not None and any(c["added"][k] for k in KINDS)


def text(tid):
    """그 테마의 지금 YAML 글 | None — 사람이 고친 사본이 있으면 그 글, 없으면 기본본의 글(+ LLM 이 더한 `added`)."""
    dt, ct = default_text(tid), copy_text(tid)
    c = _parsed(tid, ct, "copy")
    if c is not None and (c["keys"] or dt is None):
        return ct
    if dt is None:
        return None
    return dt.rstrip("\n") + "\n" + ("\n" + _dump({"added": {k: c["added"][k] for k in KINDS if c["added"][k]}}) if _has_added(c) else "")


def _write(tid, body):
    d = store_dir()
    if d is None:
        _MEMORY[tid] = body
        return
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=f".{tid}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        os.replace(tmp, d / f"{tid}.yaml")
        _CACHE.pop(str(d / f"{tid}.yaml"), None)   # 같은 크기 · 같은 시각으로 고쳐 써도 옛 글을 읽지 않게
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save(tid, body):
    """화면에서 고친 YAML 글을 사본에 저장 → get(tid). 틀린 꼴은 ValueError."""
    if not isinstance(tid, str) or not ID.fullmatch(tid):
        raise ValueError("테마 id 는 영문 소문자로 시작하는 영문 소문자 · 숫자 · _ 40자까지입니다")
    body = (body or "").replace("\r\n", "\n") if isinstance(body, str) else ""
    parse(body, tid, strict=True)
    with _LOCK:
        _write(tid, body if body.endswith("\n") else body + "\n")
    return get(tid)


def reset(tid):
    """사본을 지운다(기본으로 — LLM 이 더한 항목도 함께 지워진다) → 지운 것이 있었나."""
    if not isinstance(tid, str) or not ID.fullmatch(tid):
        return False
    d = store_dir()
    with _LOCK:
        if d is None:
            return _MEMORY.pop(tid, None) is not None
        p = d / f"{tid}.yaml"
        had = p.is_file()
        p.unlink(missing_ok=True)
        _CACHE.pop(str(p), None)
        return had


def _norm(name):
    return re.sub(r"[\s·\-_/()「」]+", "", str(name or "")).lower()


def _new_id(want, name, have, lead):
    if isinstance(want, str) and ID.fullmatch(want) and want not in have:
        return want
    base = lead + hashlib.sha1(_norm(name).encode("utf-8")).hexdigest()[:8]
    out, n = base, 1
    while out in have:
        n += 1
        out = f"{base}_{n}"
    return out


_ADDED_AT = re.compile(r"(?m)^added\s*:")
_TOP_KEY = re.compile(r"(?m)^[A-Za-z_][\w]*\s*:")


def _with_added(body, added):
    """사본 글의 `added` 덩이만 바꾼 글 | None(그 덩이가 맨 끝 키가 아니다 — 통째로 다시 써야 한다). 사람이 적은 주석 · 줄 나눔을 지킨다."""
    block = _dump({"added": added})
    m = _ADDED_AT.search(body)
    if m is None:
        return body.rstrip("\n") + "\n\n" + block if body.strip() else block
    if _TOP_KEY.search(body, m.end()):
        return None
    return body[:m.start()].rstrip("\n") + ("\n\n" if body[:m.start()].strip() else "") + block


def add(tid, kind, item, src="llm", work="", at=""):
    """항목 하나를 그 테마 사본의 `added` 에 더한다 → (항목 id, 새로 더했나). 같은 이름(빈칸 · 기호를 뺀 글)이 이미 있으면 덮지 않고 그 id 를 돌려준다 · 준 id 가 겹치면 새 id 를 짓는다.
    item = {id?, name, signs?, how, levels?} · 못 쓰는 항목 · 없는 테마는 ValueError."""
    if kind not in KINDS:
        raise ValueError(f"종류는 {' · '.join(KINDS)} 가운데 하나")
    with _LOCK:
        theme = get(tid)
        if theme is None:
            raise ValueError(f"테마 「{tid}」 가 없습니다")
        name = _one((item or {}).get("name"), NAME_MAX)
        if not name:
            raise ValueError(f"{KIND_NAMES[kind]} 항목에 이름이 없습니다")
        for x in theme[kind]:
            if _norm(x["name"]) == _norm(name):
                return x["id"], False
        if len(theme[kind]) >= ITEMS_MAX:
            raise ValueError(f"{KIND_NAMES[kind]} 는 {ITEMS_MAX}개까지입니다")
        new = _item(kind, {**(item or {}), "id": _new_id((item or {}).get("id"), name, {x["id"] for x in theme[kind]}, "x"), "name": name,
                           "src": src if src in ("user", "llm") else "llm", "work": work, "at": at}, True)
        ct = copy_text(tid)
        c = _parsed(tid, ct, "copy")
        if ct is not None and c is None:
            raise ValueError(f"테마 「{tid}」 의 사본을 읽을 수 없어 더하지 못했습니다 — 화면에서 YAML 을 고치거나 기본으로 되돌리세요")
        added = {k: [dict(x) for x in (c["added"][k] if c else [])] for k in KINDS}
        added[kind].append(new)
        added = {k: v for k, v in added.items() if v}
        body = _with_added(ct, added) if c is not None else _dump({"added": added})
        if body is not None:
            try:
                ok = parse(body, tid, strict=False)["added"] == {k: added.get(k, []) for k in KINDS}
            except ValueError:
                ok = False
            body = body if ok else None
        if body is None:   # `added` 가 가운데 있는 글 — 읽은 것으로 통째로 다시 쓴다(주석은 남지 않는다)
            data = yaml.safe_load(ct) if ct else {}
            data = data if isinstance(data, dict) else {}
            data.pop("added", None)
            body = _dump({**data, "added": added})
        _write(tid, body)
        return new["id"], True


def define(theme, src="llm", work="", at=""):
    """새 테마를 사본에 만든다 → (테마 id, 새로 만들었나). theme = {id?, name, docs?, signs?, division?[{name, how}]} — 같은 이름의 테마가 있으면 만들지 않고 그 id 를 돌려준다."""
    name = _one((theme or {}).get("name"), NAME_MAX)
    if not name:
        raise ValueError("테마의 이름이 없습니다")
    with _LOCK:
        have = {}
        for t in listing():
            have[t["id"]] = t["name"]
            if _norm(t["name"]) == _norm(name):
                return t["id"], False
        tid = _new_id((theme or {}).get("id"), name, set(have), "t")
        division, seen = [], set()
        for x in ((theme or {}).get("division") or ())[:ITEMS_MAX]:
            if isinstance(x, dict) and _one(x.get("name"), NAME_MAX):
                iid = _new_id(x.get("id"), x.get("name"), seen, "d")
                seen.add(iid)
                division.append({"id": iid, "name": _one(x["name"], NAME_MAX), "how": _one(x.get("how"), HOW_MAX)})
        docs = (theme or {}).get("docs")
        data = {"id": tid, "name": name, "docs": [_one(x, NAME_MAX) for x in (docs if isinstance(docs, list) else [])[:DOCS_MAX] if _one(x, NAME_MAX)],
                "signs": _one((theme or {}).get("signs"), SIGNS_MAX), "division": division, "templates": [], "tables": [],
                "src": src if src in ("user", "llm") else "llm", **({"work": work} if work else {}), **({"at": at} if at else {})}
        body = _dump(data)
        parse(body, tid, strict=True)
        _write(tid, body)
        return tid, True


def ref(tid, iid):
    return f"{tid}.{iid}"


def find(kind, key, themes=None):
    """「<테마 id>.<항목 id>」 → (테마, 항목) | (None, None)."""
    tid, _, iid = key.partition(".") if isinstance(key, str) else ("", "", "")
    for t in (themes if themes is not None else listing()):
        if t["id"] == tid:
            return next(((t, x) for x in t.get(kind) or () if x["id"] == iid), (None, None))
    return None, None


def by_name(kind, name, themes=None):
    """같은 이름(빈칸 · 기호를 뺀 글)의 항목 → 「테마.항목」 | None — 어느 테마에 있든(새로 정의하기 전에 본다: 같은 타입을 테마마다 또 만들지 않게)."""
    n = _norm(name)
    for t in (themes if themes is not None else listing()):
        for x in t.get(kind) or ():
            if n and _norm(x["name"]) == n:
                return ref(t["id"], x["id"])
    return None


def unconfirmed(item):
    """LLM 이 정의했고 사람이 확인하지 않은 항목인가 — 저장 꼴에 「확인함」 표식이 따로 없어 출처로 가른다: `src: llm`(LLM 이 더한 것 · LLM 이 정의한 테마의 항목)이면 확인 전,
    사람이 YAML 에서 그 항목의 src 를 user 로 고치면 확인한 것(writing_guidance_api.attach 가 뒤 단계에 싣는 글을 가르는 것과 같은 기준 — spec_양식작성 ② §5-9)."""
    return (item or {}).get("src") == "llm"


def brief(themes=None, unconfirmed_how=True):
    """LLM 에 싣는 꼴 — 테마마다 {id, name, docs, signs, division[{name, how}], templates[{id(「테마.항목」), name, levels, how}], tables[{id(「테마.항목」), name, signs, how}]}.
    unconfirmed_how=False 면 확인 전 항목(`unconfirmed`)의 how(다루는 법 · 작성 방법)를 **빼고** 이름 · 판별 단서 · 레터만 싣는다(그 항목에 how 키가 없다) — 04 가 확인 전의 작성 방법을 자리 규칙으로 옮겨
    뒤 단계에 넘기지 않게(astra 2026-11-27 P1-4: 뒤 단계는 확인 전 how 를 빼는데 04 의 규칙으로 바뀌면 그 막이를 비켜 간다). 분류(이 표가 그 타입인가)에는 이름 · 단서로 족하다."""
    def how(x):
        return {} if not unconfirmed_how and unconfirmed(x) else {"how": x["how"]}
    out = []
    for t in (themes if themes is not None else listing()):
        out.append({"id": t["id"], "name": t["name"], "docs": t["docs"], "signs": t["signs"],
                    "division": [{"name": x["name"], **how(x)} for x in t["division"]],
                    "templates": [{"id": ref(t["id"], x["id"]), "name": x["name"], "levels": x["levels"], **how(x)} for x in t["templates"]],
                    "tables": [{"id": ref(t["id"], x["id"]), "name": x["name"], "signs": x["signs"], **how(x)} for x in t["tables"]]})
    return out


def same_def(kind, item, new):
    """새 정의(new)가 있는 항목(item)과 **같은 정의**인가 — 이름만 같고 내용이 다른 정의를 있는 항목에 잇지 않게(astra 2026-11-27 P2-3).
    템플릿 = 레벨마다의 레터가 같음 · 테이블 타입 = 판별 단서와 작성 방법이 같음 · 구분 기준 타입 = 다루는 법이 같음(빈칸 · 기호를 뺀 글로 견준다 — `_norm`)."""
    if not item or not isinstance(new, dict):
        return False
    if kind == "templates":
        return [_one(x, LETTER_MAX) for x in item.get("levels") or ()] == [_one(x, LETTER_MAX) for x in new.get("levels") or () if isinstance(x, str)]
    keys = (("signs", SIGNS_MAX), ("how", HOW_MAX)) if kind == "tables" else (("how", HOW_MAX),)   # 저장할 때와 같은 길이로 잘라 견준다
    return all(_norm(_one(item.get(k), n)) == _norm(_one(new.get(k), n)) for k, n in keys)


def division_text(theme, limit=600):
    """그 테마의 중요 항목 한 줄 — 「연구개발과제 — 참여기관: … / 연차: …」 | ""(항목 없음)."""
    items = [f"{x['name']}: {x['how']}" if x.get("how") else x["name"] for x in (theme or {}).get("division") or ()]
    if not items:
        return ""
    t = f"{theme['name']} — " + " / ".join(items)
    return t if len(t) <= limit else t[:limit - 1] + "…"
