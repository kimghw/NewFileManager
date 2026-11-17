"""글꼴 찾기·웹 글꼴 계획(spec_hwpx_웹편집 ② §3-3) — 문서의 언어별 글꼴(charPr fontRef)마다 웹이 그릴 글꼴을 한글과 같은 차례로 정하고
웹에는 @font-face 로 내준다. 글꼴 대조(pdf_style.check_fonts)도 같은 계획으로 PDF 글꼴과 견준다(웹이 실제로 그리는 것 = 판정 대상).

- 이 PC 글꼴: %WINDIR%\\Fonts·사용자 글꼴(브라우저가 local() 로 찾음) + 한글 설치 폴더 Shared\\TTF\\Hwp(한컴 동봉 — Windows 에 설치돼 있지
  않아 브라우저가 못 찾음 → 서버가 GET /api/fonts/{id} 로 파일을 내줌). 글꼴 이름표(name table)의 한글·영문 이름·전체 이름·PostScript 이름으로 묶는다.
- FontMap.dat 은 한컴 슬라이드용 대체 표다 — 한글 워드의 대체 규칙은 아니고(한컴돋움 → 표는 Dotum, 한글은 HCR Dotum), mapFont 줄의
  「같은 디자인 묶음」만 쓴다.
- 브라우저(Chrome·Edge)는 font-family 에 「HY중고딕」·「HYGothic-Medium」 같은 이름을 바로 써도 못 찾는 글꼴이 있다 — 그래서 모든 문서 글꼴을
  @font-face(src: local(전체 이름), local(PostScript 이름), url(...)) 별칭으로 건다(references/HWPX_렌더링_검증.md 「웹 글꼴」).
- 정하는 차례(한글이 찍는 것과 같게): 그 글꼴이 있으면 그것(same). HFT(한글 전용 글꼴 — 브라우저가 못 씀)는 한글 글자면 한컴 대응표
  (Shared\\Fonts\\FontMap.dat 의 mapFont — 「한양중고딕」 → 같은 디자인 TTF 「HY중고딕」, equiv), 영문·한자 등은 문서의 대체 글꼴(hh:substFont —
  한글도 HFT 에 없는 글자를 이것으로 찍음, subst — 문서에 대체 글꼴이 없으면 한글의 기본 대체 글꼴 `hft_subst`). 없는 TTF 는 문서의 대체 글꼴(subst) → 대응표(equiv) → 웹 기본(fallback).
- 언어별 글꼴은 unicode-range 로 나눈다(`LANG_RANGE` — 한글이 그 언어 글꼴로 찍는 글자: 영문·한자·일어·기호), 나머지(한글 등)는 한글 글꼴."""
import os
import re
import struct
import sys
import threading
import unicodedata
from pathlib import Path

WEB_FALLBACK = ["HCR Dotum", "함초롬돋움", "Malgun Gothic"]  # app.js FALLBACK 과 같은 차례 — 계획이 없을 때 브라우저가 쓰는 글꼴
LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")  # hh:fontface lang = charPr fontRef 속성(소문자)
# 웹이 언어 글꼴로 그리는 글자(unicode-range) = 한글 2020 이 그 언어 글꼴(charPr fontRef)로 찍는 글자 — 2026-11-17 언어마다 다른 KS X 1001 글꼴을 준
# 시험 문서를 한글 PDF 로 찍어 글자마다 PDF 글꼴을 봄(references/HWPX_렌더링_검증.md 「언어 글꼴 범위」). 블록마다 몇 글자씩 잰 것을 블록 전체로 넓혔고,
# 잰 글자가 블록 안에서 갈린 곳(따옴표 ‘’“” = 영문 · 〓 = 일어)만 따로 뗐다. 빈칸 글자(U+2000–200F · U+3000)·딩뱃(✓ — 두 글꼴 모두 글자가 없어 못 잼)·
# 한글 호환 자모(ㄱ·ㆍ — 한글 글꼴)는 넣지 않는다 — 그 밖은 한글 글꼴로 그린다.
LANG_RANGE = {
    "LATIN": [(0x0000, 0x024F), (0x2018, 0x2019), (0x201C, 0x201D)],
    "HANJA": [(0x2E80, 0x2FDF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)],
    "JAPANESE": [(0x3013, 0x3013), (0x3040, 0x30FF), (0x31F0, 0x31FF)],
    "SYMBOL": [(0x0370, 0x04FF),  # 그리스·키릴 문자
               (0x2010, 0x2017), (0x201A, 0x201B), (0x201E, 0x2027), (0x2030, 0x205E),  # 일반 문장부호(― † … ‰ ′ ※ •)
               (0x2070, 0x218F),  # 위·아래 첨자 숫자 · 통화(€) · 글자 같은 기호(℃ №) · 숫자 꼴(Ⅰ ⅓)
               (0x2190, 0x23FF),  # 화살표 · 수학 연산자(√ ∼ ≠ ∙) · 기술 기호(⌒)
               (0x2460, 0x26FF),  # 둘러싼 영숫자(① ⓐ) · 괘선 · 블록 · 도형(□ ○ △) · 기타 기호(☆ ♪)
               (0x3001, 0x3012), (0x3014, 0x303F),  # 한중일 문장부호(、 「」 〈〉)
               (0x3200, 0x33FF),  # 둘러싼 한중일 글자(㈜ ㉠) · 호환 단위(㎎ ㎥)
               (0xFF01, 0xFF5E), (0xFFE0, 0xFFE6)],  # 전각 꼴(！ Ａ ０ ～ ￦)
}
WEB_LANGS = ("HANGUL", *LANG_RANGE)
SCRIPT_SIZE, SUP_RISE = 0.64, 0.44  # 한글 윗·아래첨자: 글자 크기 × 0.64, 윗첨자 기준선 + 0.44 × 크기(한글 2020 PDF 실측 — app.js 와 같은 값)
REGULAR = {"", "regular", "normal", "book", "roman", "medium", "standard"}


HFT_SANS = {"산세리프", "HCI Hollyhock"}  # 이름에 「고딕」 이 없는데 한글이 돋움으로 대체하는 HFT(산세리프 = 문서들의 substFont 돋움 · HCI Hollyhock = 기술수요조사서 PDF)


def hft_subst(face, lang):
    """hh:substFont 가 없는 HFT 의 그 언어 글자를 한글이 찍는 글꼴 — 고딕 계열의 영문·한자·일어는 돋움, 그 밖(명조 계열 · 기호·기타·사용자)은 바탕.
    근거: 2026-11-17 대체 글꼴을 뺀 시험 문서(한양견고딕 영문·한양중고딕 한자·일어 → Dotum, 한양중고딕 기호 → Batang)와 연구계획서_공통.hwpx 의 PDF,
    그리고 한글이 대체 글꼴을 적어 둔 문서 18개의 값(한양중고딕·한양견고딕·산세리프 영문 → Dotum, 한양신명조·명조·HCI Poppy·기호 → Batang)이 같다."""
    if lang in ("LATIN", "HANJA", "JAPANESE") and ("고딕" in (face or "") or face in HFT_SANS):
        return ("Dotum",)
    return ("Batang",)


def lang_of(ch):
    """글자 -> 웹이 그 글자를 그리는 언어 글꼴(LANG_RANGE 에 없으면 HANGUL)."""
    o = ord(ch)
    for lang, rng in LANG_RANGE.items():
        if any(a <= o <= b for a, b in rng):
            return lang
    return "HANGUL"


def _norm(name):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", name or "")).lower()


BITMAP_TABLES = {b"EBDT", b"EBLC", b"EBSC"}  # 내장 비트맵(굴림·돋움·바탕·궁서 계열) — 웹으로 내줄 때 뺀다(크기 반, 폭 계산엔 무관)


def _faces(path):
    """글꼴 파일(ttf·otf·ttc)의 face 마다 (이름 [(nameID, 언어, 글)], 표 이름 집합) — 이름표와 표 목록만 읽는다."""
    out = []
    with open(path, "rb") as f:
        tag = f.read(4)
        offs = [0]
        if tag == b"ttcf":
            f.seek(8)
            n = struct.unpack(">I", f.read(4))[0]
            offs = list(struct.unpack(f">{n}I", f.read(4 * n)))
        for off in offs:
            f.seek(off + 4)
            n_tab = struct.unpack(">H", f.read(2))[0]
            f.seek(off + 12)
            dirs = f.read(16 * n_tab)
            tags = {dirs[i:i + 4] for i in range(0, len(dirs), 16)}
            rec = next((struct.unpack(">4sIII", dirs[i:i + 16]) for i in range(0, len(dirs), 16) if dirs[i:i + 4] == b"name"), None)
            if rec is None:
                out.append(([], tags))
                continue
            f.seek(rec[2])
            data = f.read(rec[3])
            _, count, base = struct.unpack(">HHH", data[:6])
            names = []
            for i in range(count):
                pid, eid, lang, nid, ln, so = struct.unpack(">HHHHHH", data[6 + 12 * i:18 + 12 * i])
                if nid not in (1, 2, 4, 6, 16, 17):
                    continue
                raw = data[base + so:base + so + ln]
                if pid == 3:
                    s = raw.decode("utf-16-be", "ignore")
                elif pid == 1 and eid == 0:
                    s = raw.decode("latin-1")
                else:
                    continue
                names.append((nid, lang if pid == 3 else 0x409, s))
            out.append((names, tags))
    return out


def extract_face(path, index=0, drop=BITMAP_TABLES):
    """글꼴 파일의 face 하나를 낱 TTF 바이트로(ttc 는 그 face 의 표만 복사, drop 표는 뺀다). Chrome 은 local() 시스템 글꼴 중 내장 비트맵 글꼴
    (굴림·돋움·바탕·궁서 계열)의 글자 폭을 정수 px 로 반올림한다(13pt 돋움체 17.33 → 18px = 3.8% 넓어져 한글보다 줄이 더 바뀜, 10pt 돋움 13.33 → 13px)
    — 같은 face 를 url() 웹 글꼴로 주면 소수 폭 그대로다(2026-11-10 실측, spec_hwpx_웹편집 ② §3-5). 검사합(checksum)은 그대로 두어도 브라우저가 받는다."""
    data = Path(path).read_bytes()
    off = 0
    if data[:4] == b"ttcf":
        n = struct.unpack(">I", data[8:12])[0]
        off = struct.unpack(f">{n}I", data[12:12 + 4 * n])[index]
    sfnt, n_tab = struct.unpack(">IH", data[off:off + 6])
    keep = []
    for i in range(n_tab):
        tag, cs, o, ln = struct.unpack(">4sIII", data[off + 12 + 16 * i:off + 28 + 16 * i])
        if tag not in drop:
            keep.append((tag, cs, data[o:o + ln]))
    keep.sort()
    n = len(keep)
    es = n.bit_length() - 1
    sr = (1 << es) * 16
    head = bytearray(struct.pack(">IHHHH", sfnt, n, sr, es, n * 16 - sr))
    body, recs, base = bytearray(), [], 12 + 16 * n
    for tag, cs, blob in keep:
        recs.append(struct.pack(">4sIII", tag, cs, base + len(body), len(blob)))
        body += blob + b"\0" * ((4 - len(blob) % 4) % 4)
    return bytes(head + b"".join(recs) + body)


# ---- 한글 설치 폴더 -------------------------------------------------------------------------------------

def _hwp_shared():
    """한글 COM 등록(HWPFrame.HwpObject → LocalServer32 = …\\HOffice110\\Bin\\hwp.exe)에서 …\\HOffice110\\Shared."""
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"HWPFrame.HwpObject\CLSID") as k:
            clsid = winreg.QueryValue(k, None)
    except OSError:
        return None
    for sub in (rf"CLSID\{clsid}\LocalServer32", rf"WOW6432Node\CLSID\{clsid}\LocalServer32"):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, sub) as k:
                cmd = winreg.QueryValue(k, None)
        except OSError:
            continue
        m = re.match(r'\s*"?([^"]+?\.exe)', cmd or "", re.I)
        if m:
            return Path(m[1]).parent.parent / "Shared"
    return None


def hancom():
    """{"dirs": 한글이 쓰는 동봉 글꼴 폴더(Shared\\TTF\\Hwp), "fontmap": Shared\\Fonts\\FontMap.dat | None}. env NFM_HNC_SHARED = Shared 폴더.
    TTF\\All(한컴돋움 HDOTUM.TTF 등)은 한글이 쓰지 않는다 — 한컴돋움 문단을 HCR Dotum 으로 찍음(2026-11-08 실측, 휴먼명조 TTF\\Hwp 는 그대로 씀)."""
    env = os.environ.get("NFM_HNC_SHARED")
    shared = Path(env) if env else _hwp_shared()
    if shared is None or not shared.is_dir():
        return {"dirs": [], "fontmap": None}
    hwp = shared / "TTF" / "Hwp"
    fm = shared / "Fonts" / "FontMap.dat"
    return {"dirs": [hwp] if hwp.is_dir() else [], "fontmap": fm if fm.is_file() else None}


def fontmap_groups(path):
    """FontMap.dat(UTF-16) 의 mapFont=원래,대체1,대체2… 줄마다 [이름…] — 한컴이 같은 디자인으로 보는 글꼴 묶음(「HY중고딕,HY중고딕,한양중고딕,중고딕」)."""
    if not path:
        return []
    try:
        s = Path(path).read_bytes().decode("utf-16")
    except (OSError, UnicodeError):
        return []
    out = []
    for line in s.splitlines():
        m = re.match(r"\s*mapFont\s*=\s*(.+)", line)
        if m:
            g = [x.strip() for x in m[1].rstrip(";").split(",") if x.strip()]
            if len(g) > 1:
                out.append(g)
    return out


# ---- 글꼴 목록 ----------------------------------------------------------------------------------------

def system_dirs():
    return [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
            Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Microsoft" / "Windows" / "Fonts"]


class FontIndex:
    """이 PC 글꼴의 이름 -> 가족 키(영문 가족 이름 정규화). 웹 글꼴 이름(한글 이름 포함)과 PDF 글꼴 이름(PostScript)을 같은 가족으로 묶고,
    가족마다 face(파일·전체 이름·PostScript 이름·굵게·설치 여부)를 둔다 — @font-face src 를 만든다."""

    def __init__(self, dirs=None, bundled=None, fontmap=None):
        hc = hancom() if bundled is None or fontmap is None else {}
        self.names, self.label, self.fams, self.faces, self._served = {}, {}, {}, [], {}
        for d in system_dirs() if dirs is None else dirs:
            self._scan(Path(d), True)
        for d in hc.get("dirs", []) if bundled is None else bundled:
            self._scan(Path(d), False)
        self.groups = fontmap_groups(hc.get("fontmap") if fontmap is None else fontmap)

    def _scan(self, d, system):
        if not d.is_dir():
            return
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                continue
            try:
                faces = _faces(p)
            except (OSError, struct.error, ValueError):
                continue
            for i, (names, tags) in enumerate(faces):
                en = lambda nid: next((s for n, lang, s in names if n == nid and lang == 0x409), None)  # noqa: E731
                fam = en(16) or en(1) or next((s for n, _, s in names if n == 1), None)
                if not fam:
                    continue
                key = _norm(fam)
                self.label.setdefault(key, fam)
                sub = (en(17) or en(2) or "").strip().lower()
                face = {"id": len(self.faces), "path": p, "index": i, "ttc": len(faces) > 1 or p.suffix.lower() == ".ttc",
                        "bitmap": bool(tags & BITMAP_TABLES),  # 내장 비트맵 글꼴 — local() 대신 파일을 먼저(extract_face)
                        "system": system, "bold": sub == "bold", "italic": "italic" in sub or "oblique" in sub, "sub": sub,
                        "local": list(dict.fromkeys(s for n, _, s in names if n in (4, 6) and s.strip())),
                        "ps": {s for n, _, s in names if n == 6}}
                self.faces.append(face)
                self.fams.setdefault(key, []).append(face)
                alias = {_norm(s) for n, _, s in names if n in (1, 4, 6, 16)}
                if len(faces) == 1:
                    alias.add(_norm(p.stem))
                for a in alias - {""}:
                    self.names.setdefault(a, set()).add(key)

    def family(self, name):
        """글꼴 이름(웹 글꼴·PDF 글꼴) -> 가족 키 | None(이 PC 에 없음 · Type3 「T1」 · 한글 이름이 깨진 「????」)."""
        n = _norm(re.sub(r"^[A-Z]{6}\+", "", name or ""))
        for cand in (n, re.sub(r"(bold|italic|regular|oblique)+$", "", n)):
            if cand and cand in self.names:
                return sorted(self.names[cand])[0]
        return None

    def broken_match(self, pdf_name, key):
        """PDF 글꼴 이름이 「????」(한글 PostScript 이름을 한글 PDF 가 ? 로 씀)일 때 가족 key 의 한글 PostScript 이름과 글자 수가 같은지."""
        q = re.sub(r"^[A-Z]{6}\+", "", pdf_name or "")
        if not q or set(q) != {"?"} or not key:
            return False
        return any(len(ps) == len(q) and not ps.isascii() for f in self.fams.get(key, ()) for ps in f["ps"])

    def face(self, key, bold=False):
        """가족의 보통(또는 굵은) face — 설치된 것 먼저, 굵은 face 가 없으면 None(브라우저가 굵게를 흉내 냄)."""
        cand = [f for f in self.fams.get(key, ()) if not f["italic"] and f["bold"] == bold]
        if not bold:
            cand = [f for f in cand if f["sub"] in REGULAR] or cand
        return sorted(cand, key=lambda f: (not f["system"], f["sub"] != ("bold" if bold else "regular")))[0] if cand else None

    def file_of(self, fid):
        """GET /api/fonts/{id} 로 내줄 것 — 낱 글꼴 파일은 경로, ttc 의 face·내장 비트맵 글꼴은 뽑은 TTF 바이트(extract_face, 메모리에 한 번만) | None."""
        f = self.faces[fid] if isinstance(fid, int) and 0 <= fid < len(self.faces) else None
        if f is None:
            return None
        if not f["ttc"] and not f["bitmap"]:
            return f["path"]
        if fid not in self._served:
            try:
                self._served[fid] = extract_face(f["path"], f["index"])
            except (OSError, struct.error, ValueError, IndexError):
                self._served[fid] = None
        return self._served[fid]

    def css_src(self, key, bold=False):
        f = self.face(key, bold)
        if f is None:
            return None
        q = lambda s: '"' + s.replace("\\", "").replace('"', "") + '"'  # noqa: E731
        url = f'url("/api/fonts/{f["id"]}")'
        parts = [f"local({q(n)})" for n in f["local"]]
        if f["bitmap"]:
            parts.insert(0, url)  # 내장 비트맵 글꼴은 파일 먼저 — local() 이면 Chrome 이 글자 폭을 정수 px 로 반올림(extract_face 주석)
        else:
            parts.append(url)  # 설치 안 된 한컴 동봉 글꼴(또는 local() 이 못 찾은 글꼴) — ttc 는 face 를 뽑아 준다
        return ", ".join(parts) or None

    # ---- 계획 ----
    def resolve(self, face, lang="HANGUL", ftype="TTF", subst=()):
        """문서 글꼴 하나 -> 웹이 그릴 글꼴 {"key": 가족 키|None, "how": same|equiv|subst|fallback, "via": 실제로 찾은 이름}."""
        hft = (ftype or "").upper() == "HFT"
        if not hft and (k := self.family(face)):
            return {"key": k, "how": "same", "via": face}
        if hft and lang != "HANGUL" and not subst:
            subst = hft_subst(face, lang)  # 문서에 대체 글꼴이 없어도 한글은 기본 대체 글꼴로 찍는다(HFT 의 영문·기호 글자는 HFT 에서 안 나옴)

        def by_subst():
            for s in subst:
                if k := self.family(s):
                    return {"key": k, "how": "subst", "via": s}

        def by_map():
            n = _norm(face)
            for g in self.groups:
                if n in {_norm(x) for x in g}:
                    for x in g:
                        if _norm(x) != n and (k := self.family(x)):
                            return {"key": k, "how": "equiv", "via": x}
        for step in ((by_map, by_subst) if hft and lang == "HANGUL" else (by_subst, by_map)):
            if r := step():
                return r
        for s in WEB_FALLBACK:
            if k := self.family(s):
                return {"key": k, "how": "fallback", "via": s}
        return {"key": None, "how": "fallback", "via": None}


_INDEX, _INDEX_LOCK = None, threading.Lock()


def font_index():
    global _INDEX
    with _INDEX_LOCK:
        if _INDEX is None:
            _INDEX = FontIndex()
        return _INDEX


def _range_css(lang):
    return ", ".join(f"U+{a:04X}-{b:04X}" for a, b in LANG_RANGE[lang])


def web_fonts(table, index=None):
    """table: HwpxDoc.font_table() {lang: {face: {"type", "subst"}}} -> {"css": @font-face 규칙, "alias": {lang: {face: 별칭}},
    "plan": {lang: {face: {how, via, uses}}}} — app.js fontStack 이 「영문 별칭, 한자 별칭, 일어 별칭, 한글 별칭, 웹 기본」 차례로 쓴다."""
    index = index or font_index()
    rules, alias, plan = [], {}, {}
    for lang in WEB_LANGS:
        for n, (face, info) in enumerate((table.get(lang) or {}).items()):
            r = index.resolve(face, lang, info.get("type"), info.get("subst") or ())
            plan.setdefault(lang, {})[face] = {"how": r["how"], "via": r["via"], "uses": index.label.get(r["key"], r["key"])}
            if not r["key"]:
                continue
            name = f"nfm-{lang.lower()}-{n}"
            alias.setdefault(lang, {})[face] = name
            rng = f"unicode-range:{_range_css(lang)};" if lang in LANG_RANGE else ""
            for bold in (False, True):
                src = index.css_src(r["key"], bold)
                if src:
                    rules.append(f'@font-face{{font-family:"{name}";src:{src};font-weight:{700 if bold else 400};{rng}font-display:block}}')
    return {"css": "\n".join(rules), "alias": alias, "plan": plan}
