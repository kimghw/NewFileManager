"""헤딩 추출 — 앞머리 규칙식(spec_헤딩_추출 ② §2).

문단 글의 앞 공백을 뗀 첫머리에 거는 정규식 규칙으로 문단마다 **종류(kind)·계열(family)·레터·레터 뒤 공백·제목**을 정한다.
- 내장 규칙(`BUILTIN`, 코드) + **배운 규칙**(전역 `rules.json` — LLM 제안을 검증해 넣은 것·사용자가 넣은 것). 내장 규칙은 켜고 끄기만 저장한다
  (코드 개선이 계속 반영되게).
- 순서: 빈 문단 → 목차·캡션(스크립트 판정) → **글 전체 규칙**(값·자리표시 — 내장, 배운 것) → **첫머리 규칙**(내장, 배운 것) → 아무것도 안 맞으면 plain.
  처음 맞는 규칙이 이긴다. 배운 규칙은 같은 무리의 내장 규칙 뒤에 온다 — 내장 판정을 빼앗지 못하고, 틀린 내장 규칙은 끄는 것으로 고친다.
- 배운 규칙의 정규식은 `regex` 패키지로 호출당 50 ms·실행마다 시간 합 예산 안에서만 돌린다(FileMergeManager 변환 규칙과 같은 막이).
저장: `%LOCALAPPDATA%\\NewFileManager\\headings\\rules.json`(env `NFM_HEADINGS`; `off`·`0` 이면 메모리만), 바뀔 때마다 `history.jsonl` 에 한 줄.
깨진 rules.json 은 덮어쓰지 않는다 — 읽는 쪽은 빈 저장소(+ "broken"), 쓰기는 StoreBroken 으로 거절(곁에 사본 rules.json.broken-<시각>)."""
import json
import logging
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

KINDS = ("marker", "label", "note", "footnote", "caption", "toc", "data", "placeholder", "plain", "empty")
HEADISH = ("marker", "label")  # 그래프(2단계) 후보 — 개요 문단(outlineLevel)·자동 번호도 후보
SCOPES = ("prefix", "whole")  # 첫머리에 거는 규칙 · 글 전체(앞뒤 공백 뺀 첫 줄)에 거는 규칙
GA = "가나다라마바사아자차카타파하"
WS = " \t\u3000\u00a0\u2002"  # 앞 공백·레터 뒤 공백으로 보는 글자(블록 글은 hp:fwSpace 를 U+0020 으로, 묶음 빈칸 hp:nbSpace 를 U+2002 로 둔다 — hwpx_doc.SPECIAL)
BR = "\u2028"  # 강제 줄 바꿈
PATTERN_MAX, NAME_MAX, NOTE_MAX = 200, 60, 300
MATCH_TIMEOUT, MATCH_BUDGET = 0.05, 5.0  # 배운 규칙 정규식 — 호출당 초 · 한 실행 합(초)
REPEAT_MAX = 100_000
MATCH_TEXT_MAX = 400  # 첫머리 규칙이 보는 글 앞 글자 수


def _r(id, name, kind, family, pattern, scope="prefix"):
    return {"id": id, "name": name, "kind": kind, "family": family, "pattern": pattern, "scope": scope, "source": "builtin"}


_GA = f"[{GA}]"
_SYM_END = r"(?=[\s\u2028]|$)"  # 기호 뒤가 공백·줄 끝(「-10」·「o리」 같은 글이 아님)
BUILTIN = [
    # ---- 글 전체 규칙(앞뒤 공백을 뗀 첫 줄 전체가 맞아야) ----
    _r("b.placeholder", "자리표시(○○○·OOO·XXX·20××)", "placeholder", "placeholder",
       r"(?=(?:[^○●◦□■OＯXxＸ×ㅇ]*[○●◦□■OＯXxＸ×ㅇ]){2})[○●◦□■OoＯXxＸ×ㅇ0-9,.\s~%()\-]+(?:[가-힣]{1,4})?", "whole"),
    # 값 — 번호 쓸 자리(「1.」「(9)」「3)」「1.2.」)는 값이 아니다(첫머리 marker 규칙이 blank 로 받음)
    _r("b.data", "값(숫자·단위·범위)", "data", "data",
       r"(?![1-9]\d?(?:\.[1-9]\d?)*\.$|\([1-9]\d?\)$|[1-9]\d?\)$)"
       r"(?=.*\d)[\d\s.,:%~∼～\-+±×*/()]+(?:%|원|천원|만원|백만원|억원|개|건|명|년|월|일|개월|회|점|배|시간|분|초|g|kg|mm|cm|m|km|㎡|㎥|㎏|㎎|㎜|㎝|㎞)?",
       "whole"),
    # ---- 첫머리 규칙 ----
    _r("b.chapter", "제N장", "marker", "chapter", r"제\s*\d{1,3}\s*장"),
    _r("b.section", "제N절", "marker", "section", r"제\s*\d{1,3}\s*절"),
    _r("b.article", "제N조", "marker", "article", r"제\s*\d{1,3}\s*조(?:의\s*\d{1,2})?"),
    _r("b.decimal-multi", "N.N(.N…)", "marker", "decimal", r"\d{1,2}(?:\.\d{1,2})+(?:\.(?!\d)|(?=[\s\u2028]|$))"),
    _r("b.hyphen", "N-N(.)", "marker", "hyphen", r"\d{1,2}(?:-\d{1,2})+\.?(?=[\s\u2028]|$|[^\d\-~∼～.,%])"),
    _r("b.decimal", "N.", "marker", "decimal", r"\d{1,2}\.(?![\d.])"),
    _r("b.num-paren", "N)", "marker", "num-paren", r"\d{1,2}\)"),
    _r("b.paren-num", "(N)", "marker", "paren-num", r"\(\d{1,2}\)"),
    _r("b.hangul-dot", "가.", "marker", "hangul-dot", rf"{_GA}\.(?![\d.])"),
    _r("b.hangul-paren", "가)", "marker", "hangul-paren", rf"{_GA}\)"),
    _r("b.paren-hangul", "(가)", "marker", "paren-hangul", rf"\({_GA}\)"),
    _r("b.circled", "①", "marker", "circled", r"[①-⑳㉑-㉟㊱-㊿]"),
    _r("b.enclosed", "❶·⑴·⒈·⒜·ⓐ·㉠·㉮", "marker", "enclosed", r"[❶-❿➀-➉➊-➓⑴-⒇⒈-⒛⒜-⒵ⓐ-ⓩⒶ-Ⓩ㉠-㉭㉮-㉻]"),
    _r("b.roman-upper", "Ⅰ.·I.", "marker", "roman-upper", r"(?:[Ⅰ-Ⅻ]|(?:X{0,3})(?:IX|IV|V?I{0,3}))(?<=\S)[.)](?!\d)"),
    _r("b.roman-lower", "ⅰ.·i.", "marker", "roman-lower", r"(?:[ⅰ-ⅻ]|(?:x{0,3})(?:ix|iv|v?i{0,3}))(?<=\S)[.)](?!\d)"),
    _r("b.alpha-upper", "A.·A)", "marker", "alpha-upper", r"[A-Z][.)](?![\d.A-Za-z])"),
    _r("b.alpha-lower", "a.·a)", "marker", "alpha-lower", r"[a-z][.)](?![\d.A-Za-z])"),
    _r("b.paren-alpha", "(a)·(A)", "marker", "paren-alpha", r"\([A-Za-z]\)"),
    _r("b.bracket-num", "[N]", "marker", "bracket-num", r"\[\d{1,3}\]"),
    _r("b.bracket-hangul", "[가]", "marker", "bracket-hangul", rf"\[{_GA}\]"),
    _r("b.bracket-label", "[…] 라벨", "label", "bracket-label", r"\[[^\[\]\u2028]{1,40}\]"),
    _r("b.lenticular-label", "【…】 라벨", "label", "lenticular-label", r"【[^【】\u2028]{1,40}】"),
    _r("b.square", "□", "marker", "square", r"[□■]"),
    _r("b.circle", "○", "marker", "circle", r"[○◦●](?![○◦●])"),
    _r("b.latin-o", "o", "marker", "latin-o", rf"o{_SYM_END}"),
    _r("b.jamo-o", "ㅇ", "marker", "jamo-o", rf"ㅇ{_SYM_END}"),
    _r("b.triangle", "△", "marker", "triangle", r"[△▲]"),
    _r("b.dash", "-", "marker", "dash", rf"[-–—]{_SYM_END}"),
    _r("b.dot", "·", "marker", "dot", r"[·․•ㆍ⋅∙⦁‧]"),
    _r("b.small-square", "▫", "marker", "small-square", r"[▫▪]"),
    _r("b.diamond", "◇", "marker", "diamond", r"[◇◆]"),
    _r("b.arrow", "▶", "marker", "arrow", r"[▶►▷➢➤]"),
    _r("b.note", "※ 안내", "note", "note", r"※"),
    _r("b.footnote", "* 각주", "footnote", "footnote", r"\*{1,4}(?=[\s\d\u2028]|$)"),
]
BUILTIN_IDS = {r["id"] for r in BUILTIN}
_FAMILY_SHAPE = {"decimal": "N.", "hyphen": "N-N", "num-paren": "N)", "paren-num": "(N)", "hangul-dot": "가.", "hangul-paren": "가)",
                 "paren-hangul": "(가)", "circled": "①", "bracket-num": "[N]", "bracket-hangul": "[가]"}
# 둘레 번호 글자(b.enclosed) 묶음 (첫 글자, 끝 글자) — ❶ ➀ ➊ ⑴ ⒈ ⒜ Ⓐ ⓐ ㉠ ㉮ (묶음마다 다른 레벨일 수 있어 가른다)
_ENCLOSED = ((0x2776, 0x277F), (0x2780, 0x2789), (0x278A, 0x2793), (0x2474, 0x2487), (0x2488, 0x249B), (0x249C, 0x24B5),
             (0x24B6, 0x24CF), (0x24D0, 0x24E9), (0x3260, 0x326D), (0x326E, 0x327B))


# ---- 정규식 막이(배운 규칙) ------------------------------------------------------------------------------

_REPEAT = re.compile(r"\{(\d*),?(\d*)\}")


def _regex():
    import regex  # requirements: regex — 호출당 timeout

    return regex


def compile_pattern(pattern):
    """배운 규칙 정규식 → 컴파일한 regex 패턴. 길이 PATTERN_MAX·되풀이 수 곱 REPEAT_MAX·빈 문자열에 맞지 않을 것 — 어기면 ValueError(까닭)."""
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("정규식이 비었습니다")
    if len(pattern) > PATTERN_MAX:
        raise ValueError(f"정규식이 너무 깁니다({PATTERN_MAX}자 이하)")
    n = 1
    for m in _REPEAT.finditer(pattern):
        n *= max(int(m.group(1) or 0), int(m.group(2) or 0), 1)
    if n > REPEAT_MAX:
        raise ValueError(f"정규식 되풀이 수가 너무 큽니다({REPEAT_MAX:,} 이하)")
    rx = _regex()
    try:
        c = rx.compile(pattern)
    except (rx.error, OverflowError, RecursionError) as x:
        raise ValueError(f"정규식 오류: {x}")
    try:
        if c.match("", timeout=MATCH_TIMEOUT) is not None:
            raise ValueError("빈 글에도 맞는 정규식은 받지 않습니다")
    except TimeoutError:
        raise ValueError("정규식이 빈 글에서 시간 제한을 넘었습니다")
    return c


class _Run:
    """한 실행(문서 하나 판정)의 배운 규칙 정규식 시간 예산."""

    def __init__(self, budget=MATCH_BUDGET):
        self.left, self.skipped, self.warnings = budget, set(), []

    def skip(self, rid, why):
        if rid not in self.skipped:
            self.skipped.add(rid)
            self.warnings.append(f"규칙 {rid} 정규식이 시간 제한을 넘어 건너뜀({why})")
            log.warning("헤딩 규칙 %s 정규식 건너뜀: %s", rid, why)

    def match(self, rule, text, whole):
        rid = rule["id"]
        if rid in self.skipped:
            return None
        if self.left <= 0:
            self.skip(rid, f"실행 예산 {MATCH_BUDGET:g}초를 다 씀")
            return None
        limit, t0 = min(MATCH_TIMEOUT, self.left), time.perf_counter()
        try:
            fn = rule["rx"].fullmatch if whole else rule["rx"].match
            try:
                m = fn(text, concurrent=True, timeout=limit)
            except TimeoutError:
                # 한 번 더 — 시간 제한은 벽시계라 세대 2 GC 멈춤(큰 문서의 힙에서 85~110 ms 실측)이 호출 안에 떨어지면 「.」 같은 식도 넘는다
                # (references/Python_regex_시간제한.md). 정말 느린 식은 다시 넘으므로 판정은 같고, 건너뛰기까지 한 번의 제한 시간만 더 든다
                m = fn(text, concurrent=True, timeout=limit)
            return None if m is not None and not whole and m.start() != 0 else m  # \K·(?r) — 첫머리(0)부터 맞은 것만(레터 = 맞춘 앞머리)
        except TimeoutError:
            self.skip(rid, f"호출당 {MATCH_TIMEOUT * 1000:g}ms")
            return None
        finally:
            self.left -= time.perf_counter() - t0


# ---- 저장소 --------------------------------------------------------------------------------------------

_LOCK = threading.RLock()
_MEMORY = {}  # 저장 끔(off) 일 때의 저장소


def store_dir():
    """전역 헤딩 추출 폴더 Path | None(저장 끔). env NFM_HEADINGS 가 폴더, off·0 이면 None."""
    env = os.environ.get("NFM_HEADINGS", "").strip()
    if env.lower() in ("off", "0"):
        return None
    if env:
        return Path(env)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "headings"


RETRY = (0.02, 0.05, 0.1)  # PermissionError 때 쉬는 초 — Windows 는 다른 쪽(다른 프로세스)이 연 파일 위로 os.replace·바뀌는 중 읽기가 막힌다


def _retry(fn):
    """fn() — PermissionError 면 잠깐 쉬고 다시(RETRY 만큼), 그래도 안 되면 그 오류."""
    for wait in RETRY:
        try:
            return fn()
        except PermissionError:
            time.sleep(wait)
    return fn()


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        _retry(lambda: os.replace(tmp, path))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_history(event):
    """history.jsonl 에 한 줄(규칙·지침 바뀜 기록) — 저장 끔이면 버림."""
    d = store_dir()
    if d is None:
        return
    d.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(d / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": round(time.time(), 3), **event}, ensure_ascii=False) + "\n")


def history(kind=None, limit=200):
    d = store_dir()
    p = d / "history.jsonl" if d else None
    if not p or not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if kind is None or e.get("kind") == kind:
            out.append(e)
    return out[-limit:]


class StoreBroken(ValueError):
    """rules.json 이 있는데 깨짐(JSON 오류·꼴 틀림) — 쓰기(update)는 덮어쓰지 않고 이 오류로 거절한다."""


def _parse(data):
    """rules.json 내용 → 저장소. 꼴이 틀리면 ValueError."""
    if not isinstance(data, dict):
        raise ValueError("최상위가 dict 가 아닙니다")
    rules, builtin, keeps = data.get("rules") or [], data.get("builtin") or {}, data.get("keeps") or []
    if not (isinstance(rules, list) and isinstance(builtin, dict) and isinstance(keeps, list)):
        raise ValueError("rules·keeps 는 목록, builtin 은 dict 여야 합니다")
    try:
        version, last = int(data.get("version") or 0), int(data.get("lastId") or 0)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("version·lastId 는 정수여야 합니다") from None
    return {"version": version, "rules": [r for r in rules if isinstance(r, dict)],
            "builtin": {k: v for k, v in builtin.items() if k in BUILTIN_IDS and isinstance(v, dict)},
            "keeps": [k for k in keeps if isinstance(k, str)], "lastId": last}


def _keep_broken(p):
    """깨진 rules.json 을 곁에 「rules.json.broken-<시각>」 으로 복사(같은 내용 사본이 이미 있으면 그것) → 사본 Path | None."""
    try:
        raw = p.read_bytes()
        for q in sorted(p.parent.glob(p.name + ".broken-*")):
            if q.read_bytes() == raw:
                return q
        q = p.with_name(f"{p.name}.broken-{time.strftime('%Y%m%d-%H%M%S')}")
        q.write_bytes(raw)
        return q
    except OSError as e:
        log.warning("깨진 헤딩 규칙 파일 사본을 못 만들었습니다: %s", e)
        return None


def load(strict=False):
    """저장소 {"version", "rules": [배운 규칙…], "builtin": {id: {"enabled": bool}}, "keeps", "lastId"} — 없으면 빈 저장소.
    있는데 못 읽거나 깨졌으면(JSON 오류·꼴 틀림) 읽는 쪽은 빈 저장소 + "broken"(까닭), strict(쓰기 — update)면 OSError·StoreBroken.
    깨진 파일은 덮어쓰지 않고 그대로 둔다(쓰기를 거절할 때 곁에 사본). BOM(utf-8-sig)은 깨짐이 아니다.
    읽기는 _LOCK 안 — update 의 os.replace 와 겹치면 Windows 는 쓰는 쪽 PermissionError·읽는 쪽 빈 저장소로 오판."""
    empty = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}
    d = store_dir()
    with _LOCK:
        if d is None:
            return json.loads(json.dumps(_MEMORY.get("rules") or empty))
        p = d / "rules.json"
        if not p.is_file():
            return empty
        try:
            return _parse(json.loads(_retry(lambda: p.read_text(encoding="utf-8-sig"))))
        except OSError as e:
            if strict:
                raise
            log.warning("헤딩 규칙 파일을 읽을 수 없어 빈 저장소로 봅니다: %s", e)
            return {**empty, "broken": f"읽을 수 없음: {e}"}
        except ValueError as e:  # JSON 오류·UnicodeDecodeError·꼴 틀림
            if strict:
                q = _keep_broken(p)
                raise StoreBroken(f"헤딩 규칙 파일이 깨져 저장하지 않습니다 — {p} 를 고치거나 지우세요"
                                  f"{f'(사본 {q.name})' if q else ''}: {e}") from e
            log.warning("헤딩 규칙 파일이 깨져 빈 저장소로 봅니다(파일은 그대로): %s", e)
            return {**empty, "broken": str(e)}


def add_keeps(keys, *, reason="", source="llm"):
    """충돌 묶음에서 「지금 이긴 규칙이 맞음」 이라고 한 묶음 key 들 — 보강 대상에서 다시 안 묻는다."""
    keys = [k for k in keys if isinstance(k, str) and k]
    if not keys:
        return load()

    def fn(st):
        st.setdefault("keeps", [])
        for k in keys:  # 한 번 부를 때 같은 key 가 둘이어도 하나만
            if k not in st["keeps"]:
                st["keeps"].append(k)
    return update(fn, None, {"action": "keep", "keys": keys, "source": source, "reason": reason})


class StaleVersion(Exception):
    pass


def expect_version(v):
    """기대 버전 → int | None(안 줌). 정수로 못 바꾸는 값([1]·{}·'x')은 ValueError(→ API 400)."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"version 은 정수여야 합니다: {v!r}") from None


def update(fn, expect=None, event=None):
    """저장소 읽고-고치고-쓰기(잠금 안, 원자적) → 새 저장소. expect(버전)가 지금 버전과 다르면 StaleVersion. fn(저장소) 는 제자리 고침.
    rules.json 이 깨졌으면 StoreBroken(덮어쓰지 않음), expect 가 정수가 아니면 ValueError — 둘 다 아무것도 안 씀."""
    expect = expect_version(expect)
    with _LOCK:
        st = load(strict=True)
        if expect is not None and expect != st["version"]:
            raise StaleVersion(f"규칙 저장소가 바뀌었습니다(지금 {st['version']}, 요청 {expect})")
        fn(st)
        st["version"] += 1
        d = store_dir()
        if d is None:
            _MEMORY["rules"] = json.loads(json.dumps(st))
        else:
            _write_json(d / "rules.json", st)
        if event:
            append_history({"kind": "rules", "version": st["version"], **event})
        return st


def _clean_rule(r, *, source):
    """사용자·LLM 이 준 규칙 dict → 저장할 꼴(검증 포함) | ValueError."""
    kind, family, scope = str(r.get("kind") or ""), str(r.get("family") or "").strip()[:40], str(r.get("scope") or "prefix")
    if kind not in KINDS or kind in ("toc", "caption", "empty"):
        raise ValueError(f"종류(kind) 가 잘못됐습니다: {kind!r}")
    if scope not in SCOPES:
        raise ValueError(f"scope 는 prefix·whole: {scope!r}")
    if re.search(r"\\[1-9]|\\g<|\(\?P=", r.get("pattern") or ""):  # \1 · \g<1>·\g<이름> · (?P=이름)
        raise ValueError("역참조는 쓰지 않습니다")
    compile_pattern(r.get("pattern"))
    status = str(r.get("status") or "candidate")
    if status not in ("candidate", "global"):
        raise ValueError(f"status 는 candidate·global: {status!r}")
    return {"id": str(r.get("id") or ""), "name": str(r.get("name") or family or kind)[:NAME_MAX], "kind": kind,
            "family": family or kind, "pattern": r["pattern"], "scope": scope, "first": bool(r.get("first")), "source": source,
            "status": status, "docs": [str(d)[:64] for d in (r.get("docs") or [])][:50], "globalHint": bool(r.get("globalHint")),
            "enabled": bool(r.get("enabled", True)), "note": str(r.get("note") or "")[:NOTE_MAX],
            "examples": [str(x)[:80] for x in (r.get("examples") or [])][:5],
            "created": r.get("created") or round(time.time(), 3), "provenance": r.get("provenance") or {}}


def add_rules(rules, *, source, expect=None, event=None):
    """규칙 여럿을 배운 규칙 끝에 더함 → (저장소, 새 규칙 id 목록). id 는 l1, l2, … (지운 번호는 다시 안 씀)."""
    clean = [_clean_rule(r, source=source) for r in rules]
    ids = []

    def fn(st):
        n = max([int(r["id"][1:]) for r in st["rules"] if re.fullmatch(r"l\d+", str(r.get("id")))] + [st.get("lastId", 0)])
        for c in clean:
            n += 1
            c["id"] = f"l{n}"
            ids.append(c["id"])
            st["rules"].append(c)
        st["lastId"] = n
    st = update(fn, expect, {"action": "add", "source": source, "ids": ids, **(event or {})})
    return st, ids


def set_enabled(rid, enabled, *, expect=None, reason=""):
    def fn(st):
        if rid in BUILTIN_IDS:
            st["builtin"][rid] = {"enabled": bool(enabled)}
            return
        for r in st["rules"]:
            if r["id"] == rid:
                r["enabled"] = bool(enabled)
                return
        raise KeyError(rid)
    return update(fn, expect, {"action": "enable" if enabled else "disable", "id": rid, "reason": reason})


PROMOTE_DOCS = 2  # 후보 규칙이 서로 다른 문서 몇 개에서 통과하면 전역으로 올리나


def set_status(rid, status, *, expect=None, reason=""):
    """배운 규칙 상태 바꾸기(candidate ↔ global — 사용자가 전역으로 올리기·내리기)."""
    if status not in ("candidate", "global"):
        raise ValueError(f"status 는 candidate·global: {status!r}")

    def fn(st):
        for r in st["rules"]:
            if r["id"] == rid:
                r["status"] = status
                return
        raise KeyError(rid)
    return update(fn, expect, {"action": "status", "id": rid, "status": status, "reason": reason})


def add_docs(passed, *, reason=""):
    """다른 문서에서 시험해 통과한 후보 규칙 {rid: doc_key} → docs 에 더하고 PROMOTE_DOCS 개가 되면 전역으로. 바뀐 게 없으면 저장 안 함 → 올린 id 목록."""
    promoted = []

    def fn(st):
        for r in st["rules"]:
            key = passed.get(r["id"])
            if key and r.get("status") == "candidate" and key not in (r.get("docs") or []):
                r.setdefault("docs", []).append(key)
                if len(r["docs"]) >= PROMOTE_DOCS:
                    r["status"] = "global"
                    promoted.append(r["id"])
    if passed and any(r["id"] in passed and r.get("status") == "candidate" and passed[r["id"]] not in (r.get("docs") or [])
                      for r in load()["rules"]):
        update(fn, None, {"action": "docs", "ids": sorted(passed), "promoted": promoted, "reason": reason})
    return promoted


def delete_rule(rid, *, expect=None, reason=""):
    if rid in BUILTIN_IDS:
        raise ValueError("내장 규칙은 지울 수 없습니다 — 끄세요")

    def fn(st):
        before = len(st["rules"])
        st["rules"] = [r for r in st["rules"] if r["id"] != rid]
        if len(st["rules"]) == before:
            raise KeyError(rid)
    return update(fn, expect, {"action": "delete", "id": rid, "reason": reason})


# ---- 판정 ------------------------------------------------------------------------------------------------

_BUILTIN_RX = {r["id"]: re.compile(r["pattern"]) for r in BUILTIN}


def applies(rule, doc_key):
    """배운 규칙이 이 문서에 걸리는가 — 전역(status global)이면 늘, 후보(candidate)면 그 규칙을 검증한 문서(docs)일 때만."""
    if not rule.get("enabled", True):
        return False
    if rule.get("status", "global") == "global":
        return True
    return bool(doc_key) and doc_key in (rule.get("docs") or ())


def active(store=None, extra=(), doc_key=None):
    """판정 순서의 켜진 규칙 목록 — [{…규칙, "rx"}]: 글 전체(내장 → 배운 것) 다음 첫머리(내장 → 배운 것). extra = 시험할 임시 규칙(배운 것 뒤).
    doc_key = 문서 sha256 — 후보 규칙은 그 문서에서 검증된 것만."""
    st = store if store is not None else load()
    off = {k for k, v in st.get("builtin", {}).items() if v.get("enabled") is False}
    learned = []
    for r in [x for x in st.get("rules") or [] if applies(x, doc_key)] + list(extra):
        if not r.get("enabled", True):
            continue
        try:
            learned.append({**r, "rx": compile_pattern(r["pattern"])})
        except ValueError as e:
            log.warning("배운 규칙 %s 건너뜀: %s", r.get("id"), e)
    out = [r for r in learned if r.get("first")]  # 앞선 배운 규칙(충돌 바로잡기) — 내장보다 먼저
    for scope in SCOPES[::-1]:  # whole 먼저
        out += [{**r, "rx": _BUILTIN_RX[r["id"]], "builtin": True} for r in BUILTIN if r["scope"] == scope and r["id"] not in off]
        out += [r for r in learned if r.get("scope", "prefix") == scope and not r.get("first")]
    return out


def split_lead(text):
    """(앞 공백, 나머지)."""
    i = 0
    while i < len(text) and text[i] in WS:
        i += 1
    return text[:i], text[i:]


def _enclosed_lo(s):
    """둘레 번호 글자가 든 묶음의 첫 글자 코드 | None."""
    c = ord(s[0]) if s else -1
    return next((lo for lo, hi in _ENCLOSED if lo <= c <= hi), None)


def _ordinal(family, letter):
    """번호형 레터의 번호 목록 — 「1.2.」 → [1, 2], 「다)」 → [3], 「③」 → [3], 「⑵」 → [2], 모르면 None."""
    s = letter.strip()
    if family == "enclosed":
        lo = _enclosed_lo(s)
        return [ord(s[0]) - lo + 1] if lo is not None else None
    if family in ("decimal", "hyphen", "num-paren", "paren-num", "chapter", "section", "article", "bracket-num"):
        nums = [int(x) for x in re.findall(r"\d+", s)]
        return nums or None
    if family in ("hangul-dot", "hangul-paren", "paren-hangul", "bracket-hangul"):
        m = re.search(f"[{GA}]", s)
        return [GA.index(m.group()) + 1] if m else None
    if family == "circled" and s:
        c = ord(s[0])
        for lo, hi, base in ((0x2460, 0x2473, 1), (0x3251, 0x325F, 21), (0x32B1, 0x32BF, 36)):
            if lo <= c <= hi:
                return [c - lo + base]
    if family in ("alpha-upper", "alpha-lower", "paren-alpha"):
        m = re.search("[A-Za-z]", s)
        return [ord(m.group().lower()) - 96] if m else None
    if family in ("roman-upper", "roman-lower") and s:
        if "Ⅰ" <= s[0] <= "Ⅻ":
            return [ord(s[0]) - 0x2160 + 1]
        if "ⅰ" <= s[0] <= "ⅻ":
            return [ord(s[0]) - 0x2170 + 1]
        val, prev = 0, 0
        for ch in reversed(re.sub(r"[^IVXivx]", "", s).upper()):
            v = {"I": 1, "V": 5, "X": 10}[ch]
            val, prev = (val - v, prev) if v < prev else (val + v, v)
        return [val] if val else None
    return None


def shape_of(family, letter):
    """레터 모양 키 — 번호형은 번호를 N·가·첫 값으로 바꾼 꼴(「1.2.」 → N.N., 「다)」 → 가), 「C.」 → A., 「Ⅲ.」 → Ⅰ., 「⑵」 → ⑴),
    기호형은 글자 그대로. 알파벳 대·소문자, 유니코드·ASCII 로마자, 둘레 번호 묶음은 다른 레벨일 수 있어 가른다."""
    s = letter.strip()
    if family == "circled":
        return "①"
    if family == "enclosed":
        lo = _enclosed_lo(s)
        return chr(lo) if lo is not None else s
    if family in ("alpha-upper", "alpha-lower", "paren-alpha"):
        return re.sub("[a-z]", "a", re.sub("[A-Z]", "A", s))
    if family in ("roman-upper", "roman-lower"):
        s = re.sub("[ⅰ-ⅻ]", "ⅰ", re.sub("[Ⅰ-Ⅻ]", "Ⅰ", s))
        return re.sub("[ivx]+", "i", re.sub("[IVX]+", "I", s))
    if family in _FAMILY_SHAPE or family in ("chapter", "section", "article"):
        s = re.sub(r"\d+", "N", s)
        s = re.sub(f"[{GA}]", "가", s)
        return re.sub(r"\s+", "", s)
    return s


def classify(text, rules, run=None, *, caption=False, toc=False):
    """문단 글 하나 → {"kind", "rule", "family", "lead", "letter", "gap", "rest", "ord", "shape", "blank"}.
    lead = 앞 공백, letter = 규칙이 맞춘 레터(글 전체 규칙이면 ""), gap = 레터 뒤 공백, rest = 제목(첫 줄 뒤 글 포함), blank = 레터만 있고 제목 없음."""
    text = text or ""
    lead, body = split_lead(text)
    out = {"kind": "plain", "rule": None, "family": None, "lead": lead, "letter": "", "gap": "", "rest": body, "ord": None, "shape": "",
           "blank": False}
    first = body.split(BR, 1)[0]
    if not first.strip() and not body.strip():
        out["kind"] = "empty"
        return out
    if toc or caption:
        out["kind"] = "toc" if toc else "caption"
        return out
    run = run or _Run()
    whole_text = first.strip()
    for r in rules:
        whole = r.get("scope") == "whole"
        if whole:
            m = (r["rx"].fullmatch(whole_text) if r.get("builtin") else run.match(r, whole_text, True))
        else:
            probe = first[:MATCH_TEXT_MAX]
            m = r["rx"].match(probe) if r.get("builtin") else run.match(r, probe, False)
            if m is not None and m.end() == 0:
                m = None
        if m is None:
            continue
        out.update(kind=r["kind"], rule=r["id"], family=r.get("family"))
        if whole:
            return out
        letter = m.group(0)
        tail = body[len(letter):]
        gap, rest = split_lead(tail)
        out.update(letter=letter, gap=gap, rest=rest, blank=not rest.split(BR, 1)[0].strip(),
                   ord=_ordinal(r.get("family"), letter), shape=shape_of(r.get("family"), letter))
        return out
    return out
