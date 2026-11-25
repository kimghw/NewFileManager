"""헤딩 추출 — 양식 정보(spec_헤딩_추출 ② §12): 양식마다 md 하나. 일반 지침(`heading_guides` — 모든 문서에 쓰는 판단 기준)과 **따로** 두고,
그 양식의 문서를 돌릴 때만 LLM 프롬프트에 「양식 정보」 절로 덧붙인다(사용자 2026-11-10 "일반적인 내용이랑 양식에 특화된 내용은 달리 관리").

- 파일: `<저장소>/forms/<양식 키>.md`(env `NFM_FORMS` 가 폴더, `off`·`0` = 양식 정보 없음). 파일 하나가 원본 — 기본본·사용자 사본을 가르지 않는다
  (화면·편집기·코드 에이전트가 같은 파일을 고친다). 양식 키 = 파일 이름(확장자 뺌).
- 글의 첫 ```json 블록 = 이 양식으로 볼 문서의 조건 `{"name": 표시 이름, "match": {"names": [파일 이름 꼴 — * ? 만 와일드카드], "sha256": [올린 원본 sha256]}}`
  (스크립트가 읽는다). 그 블록과 HTML 주석(`<!-- … -->` — 사람만 보는 메모)을 뺀 나머지 글 전체가 프롬프트에 들어간다(`body`).
- 문서 ↔ 양식(`match`): ① 문서마다 고른 것(작업 폴더 `headings/form.json` {"form": 키 | ""} — "" = 양식 없음으로 고정) ② 올린 원본 sha256 일치
  ③ 파일 이름 꼴(가장 긴 꼴이 이김). 폴더는 부를 때마다 읽는다(파일 몇 개 — 편집기에서 고친 글이 다음 실행에 바로).
- 저장(`save`): 기대 sha1(읽었을 때의 글)이 지금 글과 다르면 StaleVersion(→ 409). 이전 글은 헤딩 저장소 `forms_history/<키>/<시각>-<sha1 앞 8자>.md`,
  `history.jsonl` 에 한 줄 {kind: form, name, action, sha1, reason}."""
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from app import heading_rules as R
from app import works

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "forms"
TEXT_MAX = 20_000
KEY = re.compile(r"^[0-9A-Za-z가-힣_][0-9A-Za-z가-힣_ ().·-]{0,59}$")
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM\d|LPT\d|README)$", re.I)
_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```[ \t]*\n?", re.S)
_COMMENT = re.compile(r"<!--.*?-->[ \t]*\n?", re.S)
_SUFFIX = re.compile(r"[\s_\-.]*(양식|서식|form|template)$", re.I)
_LOCK = threading.RLock()
_CHOICE = {}  # 작업 폴더가 없을 때(저장 끔) {세션 id: 고른 양식 키 | ""}

SKELETON = """# 양식 정보 — {name}

```json
{head}
```

<!-- 이 양식에만 해당하는 사실·판단을 적는다. 모든 문서에 맞는 일반 기준은 「지침」에 둔다.
     위 json 블록 = 이 양식으로 볼 문서의 조건(파일 이름 꼴 · 올린 원본 sha256). 이런 주석은 LLM 에 안 보낸다. -->

## 문서 특성
-

## 개요 체계 — 주 사슬 · 가지
-

## 구분 라벨 · 구분 기준
-

## 구분 기준 자리 — 값마다 늘리고 줄이는 곳
-

## 헤딩이 아닌 것 · 제목
-

## 서식 · 조정
-

## 표
-
"""


def forms_dir():
    """양식 정보 폴더 Path | None(끔). env NFM_FORMS 가 폴더, off·0 이면 None, 없으면 저장소의 forms/."""
    env = os.environ.get("NFM_FORMS", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else DEFAULT_DIR


def _sha1(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def check_key(key):
    """양식 키(= 파일 이름)로 쓸 수 있는 글자인지 — 아니면 ValueError. 경로 구분자·점 둘·끝 점/빈칸·Windows 예약 이름은 안 됨."""
    if (not isinstance(key, str) or not KEY.fullmatch(key) or key.endswith((".", " ")) or ".." in key or _RESERVED.fullmatch(key)):
        raise ValueError("양식 키는 한글·영문·숫자·밑줄로 시작해 빈칸·괄호·점·가운뎃점·붙임표까지 60자입니다(파일 이름으로 씀 — 끝의 점·빈칸은 안 됨)")
    return key


def parse(text):
    """글 → {"name", "names", "sha256"}(json 블록의 조건). 블록이 없으면 빈 조건, 깨졌거나 안 닫혔으면 ValueError."""
    m = _JSON_BLOCK.search(text or "")
    if not m:
        if re.search(r"^[ \t]*```json", text or "", re.M):  # 여는 울타리만 있음 — 조건이 조용히 사라지고 그 글이 LLM 에 들어가는 것을 막는다
            raise ValueError("양식 정보의 json 블록이 닫히지 않았습니다(``` 로 닫아야 합니다)")
        return {"name": "", "names": [], "sha256": []}
    try:
        data = json.loads(m.group(1))
    except ValueError as e:
        raise ValueError(f"양식 정보의 json 블록을 읽을 수 없습니다: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("양식 정보의 json 블록은 객체여야 합니다")
    match_ = data.get("match")
    if match_ is None:
        match_ = {}
    if not isinstance(match_, dict):
        raise ValueError("match 는 객체여야 합니다")
    name = data.get("name")
    if name is not None and not isinstance(name, str):
        raise ValueError("name 은 문자열이어야 합니다")

    def strs(v, what):
        if v is None:
            return []
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError(f"{what} 는 문자열 목록이어야 합니다")
        return [x.strip() for x in v if x.strip()]
    return {"name": (name or "").strip()[:80], "names": strs(match_.get("names"), "match.names")[:20],
            "sha256": [x.lower() for x in strs(match_.get("sha256"), "match.sha256")][:50]}


def blank_fps(text):
    """글의 json 블록 `match.blank` = 이 양식 **빈 서식의 내용 지문** 목록(merge_table_map.blank_fp — 바이트가 달라도 내용이 같으면 같은 값: 다시 저장했거나 hwp 에서 바꿔 올린 빈 양식).
    병합의 표 대응이 「서식 예시를 덮어도 되는가」 를 가릴 때만 쓴다(spec_병합 ② §5-3 6). 블록이 없거나 깨졌으면 [](예시를 안 덮는 쪽)."""
    m = _JSON_BLOCK.search(text or "")
    try:
        got = ((json.loads(m.group(1)) if m else {}).get("match") or {}).get("blank")
    except (ValueError, AttributeError):
        return []
    return [x.strip().lower() for x in got if isinstance(x, str) and x.strip()][:20] if isinstance(got, list) else []


def copy_tables(text):
    """글의 json 블록 `copy` = 이 양식에서 **통째로 복사할 표**의 제목 목록(소속 제목 — 「[연구개발성과의 기술기여도]」). 다른 문서에서 내용을 받을 때 그 표는 칸을 맞추지 않고
    원본의 같은 제목 표를 그대로 넣는다(app/merge_copy.py — spec_병합 ② §5-8:2026-11-22 사용자 "이 테이블은 그냥 복사 타입으로 넣어줘"). 블록이 없거나 깨졌으면 [](칸을 맞추는 쪽 — 전과 같음)."""
    m = _JSON_BLOCK.search(text or "")
    try:
        got = (json.loads(m.group(1)) if m else {}).get("copy")
    except (ValueError, AttributeError):
        return []
    return [x.strip() for x in got if isinstance(x, str) and x.strip()][:50] if isinstance(got, list) else []


def body(text):
    """프롬프트에 넣는 글 — 조건 json 블록(첫 것)과 HTML 주석을 뺀 나머지(뺀 자리에 남은 빈 줄은 하나로).
    제목 줄과 빈 글머리(「-」)뿐이면 ""(손대지 않은 뼈대 — 보낼 내용이 없음)."""
    out = re.sub(r"\n{3,}", "\n\n", _COMMENT.sub("", _JSON_BLOCK.sub("", text or "", count=1))).strip()
    if not any(s and not s.startswith("#") and s not in ("-", "*") for s in (line.strip() for line in out.splitlines())):
        return ""
    return out


TABLE_SECTION = "표"                   # 이 낱말로 시작하는 절 = 표 도구의 LLM 에 가는 「양식 표 지침」
DIVISION_SECTION = "구분 기준 자리"     # 이 낱말로 시작하는 절 = 구분 기준 검토에만(헤딩 추출 프롬프트에서는 뺀다 — spec_구분_기준 ② §16)
LINK_SECTION = "자리 연결"              # 이 낱말로 시작하는 절 = 병합(이관)의 자리 연결 LLM 검토·표 대응 에이전트에만(spec_병합 ② §5-3 「연결 코멘트」 — 헤딩 추출·구분 기준 프롬프트에서는 뺀다)


def _split(text):
    """글 → [(절인가 — `## ` 제목이 있는 덩이, 제목 | "", [줄 …])] — `# `·`## ` 줄에서 끊는다(`###` 은 절 안). 첫 덩이는 제목 앞의 글."""
    parts = [(False, "", [])]
    for line in (text or "").splitlines():
        m = re.match(r"^(#{1,2})[ \t]+(.*?)[ \t]*$", line)
        if m:
            parts.append((len(m.group(1)) == 2, m.group(2), [line]))
        else:
            parts[-1][2].append(line)
    return parts


def _starts(title, word):
    """절 제목이 word 로 시작하는가 — word 바로 뒤가 글자·숫자면 다른 낱말(「표」 는 「표 — 작성 기준」 에 맞고 「표지」 에는 안 맞는다)."""
    return title.startswith(word) and not title[len(word):len(word) + 1].isalnum()


def _filled(lines):
    return any(s.strip() and s.strip() not in ("-", "*") for s in lines)


def section(text, word):
    """프롬프트에 넣는 글(body 를 거친 것)에서 `## ` 절 제목이 word 로 **시작하는** 절만(제목 줄 포함 — 여럿이면 빈 줄로 이어 붙임), 없으면 "".
    글머리만 있는 빈 절은 뺀다. 표 도구의 LLM 에는 「표」 절만 간다(spec ② §12 「쓰이는 곳」)."""
    return "\n\n".join("\n".join(lines).strip() for is_sec, title, lines in _split(text) if is_sec and _starts(title, word) and _filled(lines[1:]))


def without(text, word):
    """프롬프트에 넣는 글(body 를 거친 것)에서 `## ` 절 제목이 word 로 시작하는 절을 **뺀** 글 — 남은 것이 제목 줄·빈 글머리뿐이면 ""(body 와 같은 뜻).
    헤딩 추출 프롬프트는 「구분 기준 자리」 절을 뺀 글을 쓴다(그 절은 구분 기준 검토의 몫 — spec ② §12 「쓰이는 곳」)."""
    lines = [line for is_sec, title, ls in _split(text) if not (is_sec and _starts(title, word)) for line in ls]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out if _filled(s for s in out.splitlines() if not s.lstrip().startswith("#")) else ""


def prompt_body(form, *, headings=False):
    """단계에서 읽는 양식 본문. 자리 연결 지침은 별도 입력이고 헤딩 검토는 구분 기준 절도 제외한다."""
    if not form:
        return ""
    text = body(form.get("text"))
    if headings:
        text = without(text, DIVISION_SECTION)
    return without(text, LINK_SECTION)


# ---- 코멘트(spec_구분_기준 ② §18) — 「구분 기준 자리」 절 끝의 목록: 머리 줄 아래 `- (YYYY-MM-DD) 글` 한 줄씩(화면에서 남긴 것) ----------------------

COMMENT_HEAD = "코멘트 — 화면에서 남긴 것(새 것이 아래):"
COMMENT_MAX = 500
DIVISION_TITLE = DIVISION_SECTION + " — 값마다 늘리고 줄이는 곳"   # 그 절이 없을 때 만드는 제목(SKELETON 과 같은 글)
LINK_TITLE = LINK_SECTION + " — 다른 문서에서 내용을 받는 자리"       # 「자리 연결」 절이 없을 때 만드는 제목(연결 코멘트 — spec_병합 ② §5-3)
_COMMENT_LINE = re.compile(r"^[ \t]*-[ \t]+\((\d{4}-\d{2}-\d{2})\)[ \t]+(.*\S)[ \t]*$")


def _comment_head(line):
    return line.strip().startswith("코멘트 —")


def comment_line(text):
    """코멘트 글 → 한 줄(줄바꿈·탭·이어진 빈칸은 빈칸 하나, 앞뒤 빈칸 뗌). 비었거나 COMMENT_MAX 자를 넘으면 ValueError."""
    t = re.sub(r"\s+", " ", text).strip() if isinstance(text, str) else ""
    if not t:
        raise ValueError("코멘트 글이 비어 있습니다")
    if len(t) > COMMENT_MAX:
        raise ValueError(f"코멘트는 {COMMENT_MAX}자까지입니다(지금 {len(t)}자)")
    return t


def comments(text, section=DIVISION_SECTION):
    """글(파일 원문)의 「구분 기준 자리」 절에서 머리 줄(「코멘트 —」) 뒤의 `- (YYYY-MM-DD) 글` 줄 → [{date, text}](적힌 차례). HTML 주석 안은 안 본다(LLM 에도 안 감).
    section = 다른 절의 코멘트 목록(LINK_SECTION — 연결 코멘트)."""
    out = []
    for is_sec, title, lines in _split(_COMMENT.sub("", text or "")):
        if is_sec and _starts(title, section):
            h = next((i for i, s in enumerate(lines) if _comment_head(s)), len(lines))
            out += [{"date": m.group(1), "text": m.group(2)} for m in map(_COMMENT_LINE.match, lines[h + 1:]) if m]
    return out


def add_comment(text, comment, date, section=DIVISION_SECTION, title=DIVISION_TITLE):
    """글(파일 원문) → 「구분 기준 자리」 절의 코멘트 목록 끝(마지막 코멘트 줄 뒤)에 `- (date) comment` 를 더한 글. comment = comment_line 을 거친 한 줄.
    그 절이 없으면 글 끝에 절을 만들고, 머리 줄이 없으면 절 끝(끝 빈 줄 앞)에 머리 줄부터 더한다. 절이 여럿이면 머리 줄이 있는 것, 없으면 첫 절.
    section·title = 다른 절에(LINK_SECTION·LINK_TITLE — 연결 코멘트: spec_병합 ② §5-3)."""
    line = f"- ({date}) {comment}"
    parts = _split(text)
    secs = [ls for is_sec, sec_title, ls in parts if is_sec and _starts(sec_title, section)]
    ls = next((x for x in secs if any(map(_comment_head, x))), secs[0] if secs else None)
    if ls is None:
        return f"{(text or '').rstrip()}\n\n## {title}\n\n{COMMENT_HEAD}\n{line}\n".lstrip()
    h = next((i for i, s in enumerate(ls) if _comment_head(s)), None)
    if h is None:
        end = max(i for i, s in enumerate(ls) if s.strip()) + 1   # 제목 줄은 늘 있다
        ls[end:end] = ["", COMMENT_HEAD, line]
    else:
        ls.insert(max(i for i in range(h, len(ls)) if i == h or _COMMENT_LINE.match(ls[i])) + 1, line)
    return "\n".join(s for _, _, x in parts for s in x) + "\n"


def table_guide(sess):
    """이 문서의 양식 정보에서 「표」 절 글 | ""(맞는 양식 없음 · 그 절 없음 · 못 읽음) — 표 도구 LLM 의 「양식 표 지침」(spec ② §12)."""
    try:
        f = for_session(sess)
        return section(body(f["text"]), TABLE_SECTION) if f else ""
    except (OSError, ValueError):
        return ""


def _read_path(p):
    """양식 정보 파일 글(BOM·CRLF 는 걷어 냄). 저장이 막 바꿔 넣는 순간의 PermissionError(Windows)는 잠깐 쉬고 다시."""
    return R._retry(lambda: p.read_text(encoding="utf-8-sig")).replace("\r\n", "\n")


def _entry(p):
    text = _read_path(p)
    try:
        head, broken = parse(text), None
    except ValueError as e:
        head, broken = {"name": "", "names": [], "sha256": []}, str(e)
    return {"key": p.stem, "name": head["name"] or p.stem, "match": {"names": head["names"], "sha256": head["sha256"]}, "sha1": _sha1(text),
            "updated": round(p.stat().st_mtime, 3), "size": len(text), "broken": broken, "path": str(p), "text": text}


def _all():
    d = forms_dir()
    if d is None or not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.md")):  # 키 순 — 조건이 같은 양식이 둘이면 앞선 키가 맞는다(match)
        if not KEY.fullmatch(p.stem) or _RESERVED.fullmatch(p.stem):
            continue
        try:
            out.append(_entry(p))
        except (OSError, UnicodeError):  # 못 읽는 파일은 그것만 빠진다
            continue
    return out


def listing():
    """양식 정보 목록(글 빼고) [{key, name, match{names, sha256}, sha1, updated, size, broken, path}] — 키 순."""
    return [{k: v for k, v in f.items() if k != "text"} for f in _all()]


def get(key):
    """양식 정보 하나(글 포함) — 없으면 KeyError, 키가 잘못이면 ValueError."""
    check_key(key)
    d = forms_dir()
    p = d / f"{key}.md" if d is not None else None
    if p is None or not p.is_file():
        raise KeyError(key)
    return _entry(p)


def save(key, text, *, expect=None, reason=""):
    """양식 정보 저장(없으면 새로 만듦) → get(key). expect = 읽었을 때의 sha1("" = 새 양식 — 그 사이 생겼으면 거절), None 이면 안 견줌.
    지금 글과 다르면 R.StaleVersion. json 블록이 깨진 글·너무 긴 글은 ValueError."""
    check_key(key)
    if not isinstance(text, str) or len(text) > TEXT_MAX:
        raise ValueError(f"양식 정보 글은 {TEXT_MAX:,}자 이하의 문자열")
    if expect is not None and not isinstance(expect, str):
        raise ValueError("sha1 은 문자열이어야 합니다")
    text = text.replace("\r\n", "\n")
    parse(text)
    d = forms_dir()
    if d is None:
        raise ValueError("양식 정보 저장이 꺼져 있습니다(NFM_FORMS)")
    with _LOCK:
        p = d / f"{key}.md"
        old = _read_path(p) if p.is_file() else None
        if expect is not None and expect != (_sha1(old) if old is not None else ""):
            raise R.StaleVersion(f"양식 정보 {key} 이(가) 그 사이 바뀌었습니다")
        if old != text:
            d.mkdir(parents=True, exist_ok=True)
            if old is not None:
                _keep(key, old)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_bytes(text.encode("utf-8"))
            R._retry(lambda: os.replace(tmp, p))
            try:
                R.append_history({"kind": "form", "name": key, "action": "save" if old is not None else "create", "sha1": _sha1(text), "reason": reason})
            except OSError:  # 이력 폴더(C:)에 못 써도 글은 저장됨
                pass
    return get(key)


def _keep(key, old):
    """고치기 전 글을 헤딩 저장소에 남긴다(저장 끔·쓰기 실패면 건너뜀 — 원본 파일은 저장소에서 git 으로도 관리)."""
    hd = R.store_dir()
    if hd is None:
        return
    try:
        h = hd / "forms_history" / key
        h.mkdir(parents=True, exist_ok=True)
        (h / f"{time.strftime('%Y%m%d-%H%M%S')}-{_sha1(old)[:8]}.md").write_text(old, encoding="utf-8")
    except OSError:
        pass


def _glob(pattern, name):
    """파일 이름 꼴 — `*`(아무 글)·`?`(한 글자)만 와일드카드, 대소문자 안 가림(대괄호는 글자 그대로)."""
    rx = "".join(".*" if ch == "*" else "." if ch == "?" else re.escape(ch) for ch in pattern.casefold())
    return re.fullmatch(rx, (name or "").casefold(), re.S) is not None


def match(name, sha256=None, choice=None):
    """문서(파일 이름 · 올린 원본 sha256 · 고른 양식) → 양식 정보 + how(manual|sha256|name) | None.
    choice "" = 양식 없음으로 고정, 고른 양식 파일이 없어졌으면 자동으로 찾는다."""
    if choice == "":
        return None
    forms = _all()
    if choice:
        for f in forms:
            if f["key"] == choice:
                return {**f, "how": "manual"}
    sha = (sha256 or "").lower()
    if sha:
        for f in forms:
            if sha in f["match"]["sha256"]:
                return {**f, "how": "sha256"}
    best = None
    for f in forms:
        for pat in f["match"]["names"]:
            if _glob(pat, name) and (best is None or len(pat) > best[0]):
                best = (len(pat), f)
    return {**best[1], "how": "name"} if best else None


# ---- 문서(세션)마다 ---------------------------------------------------------------------------------------

def _choice_path(sid):
    f = works.folder(sid)
    return f / "headings" / "form.json" if f is not None and (f / "work.json").is_file() else None


def choice(sid):
    """문서마다 고른 양식 — 키 | ""(양식 없음으로 고정) | None(자동)."""
    p = _choice_path(sid)
    if p is None:
        return _CHOICE.get(sid)
    j = works._read_json(p)
    v = j.get("form") if isinstance(j, dict) else None
    return v if isinstance(v, str) else None


def set_choice(sid, key):
    """key = 양식 키(있는 것만 — 없으면 KeyError) | ""(양식 없음) | None(자동으로 되돌림)."""
    if key is not None and not isinstance(key, str):
        raise ValueError("form 은 양식 키 · \"\" · null")
    if key:
        get(key)
    p = _choice_path(sid)
    if p is None:
        if key is None:
            _CHOICE.pop(sid, None)
        else:
            _CHOICE[sid] = key
        return
    with works._lock(sid):
        if key is None:
            p.unlink(missing_ok=True)
        elif (p.parent.parent / "work.json").is_file():  # 그 사이 지운 작업을 되살리지 않는다
            works._write_json(p, {"form": key, "at": round(time.time(), 3)})


def doc_sha(sess):
    """올린 원본의 sha256 — 작업(work.json)에 적힌 것, 없으면 세션 원본 바이트에서(같은 바이트면 한 번만 셈)."""
    w = works.work(sess.id)
    if w and isinstance(w.get("sha256"), str):
        return w["sha256"]
    c = getattr(sess, "_form_sha", None)
    if c is None or c[0] is not sess.original:
        c = sess._form_sha = (sess.original, works.sha256(sess.original))
    return c[1]


def for_session(sess):
    """이 문서(세션)에 맞는 양식 정보 | None. 문서 세션이 아닌 것(문서 비교의 스냅샷 대역 `heading_compare` — name·id·original 없음)은 None."""
    if not all(hasattr(sess, a) for a in ("id", "name", "original")):
        return None
    return match(sess.name, doc_sha(sess), choice(sess.id))


def pin(sess):
    """실행 시작 때 고정할 이 문서의 양식 정보 — heading_guides.snapshot() 항목 꼴(+ key·name·how), 맞는 양식이 없으면 None."""
    f = for_session(sess)
    if f is None:
        return None
    return {"sha1": f["sha1"], "custom": True, "text": f["text"], "version": 0, "key": f["key"], "name": f["name"], "how": f["how"]}


def suggest(name, sha256=None):
    """이 문서로 새 양식 정보를 만들 때의 키·뼈대 글 → {key, text}. 키 = 파일 이름에서 확장자·끝의 「_양식」 을 뗀 것."""
    stem = (name or "").rsplit(".", 1)[0] if "." in (name or "") else (name or "")
    stem = _SUFFIX.sub("", stem.strip()) or stem.strip()
    key = re.sub(r"[^0-9A-Za-z가-힣_ ().·-]", "_", stem)[:60].strip(" .") or "양식"
    if not KEY.fullmatch(key) or _RESERVED.fullmatch(key):
        key = "양식"
    head = json.dumps({"name": key, "match": {"names": [f"*{key}*"], "sha256": [sha256] if sha256 else []}}, ensure_ascii=False)
    return {"key": key, "text": SKELETON.format(name=key, head=head)}


def bare(name, sha256=None):
    """코멘트로 처음 생기는 양식(spec_구분_기준 ② §18)의 {key, text} — 키·조건은 suggest 그대로, 글은 제목과 조건 블록뿐.
    빈 뼈대 절은 뺀다(절 하나만 채운 뼈대는 빈 절까지 프롬프트에 간다)."""
    s = suggest(name, sha256)
    return {"key": s["key"], "text": re.split(r"\n(?=<!--|## )", s["text"], maxsplit=1)[0].rstrip() + "\n"}
