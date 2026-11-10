"""가져오기·출력파일(옛 편집) 검증(spec_hwpx_웹편집 ② §3·§4).

단계 = {"key", "title", "status": wait|run|ok|warn|fail|skip, "detail", ...추가 자료}. 작업(Job)은 단계를 의존 관계대로 병렬로 채우고
(run_flow — 앞 단계가 끝난 단계는 바로 시작, 한글 출력은 pdf_render.Pool), 서버는 진행 중에도 그 목록을 그대로 내준다."""
import difflib
import hashlib
import io
import re
import threading
import time
import traceback
import unicodedata
import zipfile
from collections import Counter

import copy

from app import docx_check, headings, owpml_check, pdf_map, pdf_render, pdf_style, zip_guard
from app.docx_doc import DocxDoc
from app.hwpx_doc import HwpxDoc

# 문서 형식 → (어댑터, 표준·참조 검사 모듈, 저장본에서 바뀌어도 되는 멤버 앞머리) — spec_docx_웹편집 ② §4
KIT = {"hwpx": (HwpxDoc, owpml_check, ("Contents/",)),
       "docx": (DocxDoc, docx_check, ("word/", "[Content_Types].xml"))}


def fmt_of(sess):
    return getattr(sess, "fmt", "hwpx")

MAP_OK, MAP_WARN = 0.9, 0.6
STYLE_FAIL = 0.02  # 글꼴 대조: 크기(첨자 빼고)·굵게·색이 다른 글자가 이 비율을 넘으면 실패
LETTER_FAIL = 0.05  # 레터 대조: 레터 글자가 다른 헤딩이 이 비율을 넘으면 실패

IMPORT_STEPS = [
    ("package", "패키지 왕복", "연 그대로 저장한 파일이 원본과 바이트 동일한지"),
    ("xml", "XML 재직렬화", "XML 멤버를 모두 다시 써도 바이트가 같은지"),
    ("model", "웹 매핑", "다시 쓴 파일을 다시 열어도 블록 글이 같은지"),
    ("owpml", "OWPML 표준 검사", "원본을 OWPML 2024 XSD·참조 규칙으로 검사 — 편집 판정의 기준선(spec_owpml_편집 ② §1)"),
    ("pdf", "한글 PDF 출력", "원본을 한글로 PDF 출력"),
    ("map", "PDF 매핑", "웹 블록이 한글 PDF 의 어느 쪽에 있는지 대응"),
    ("pages", "쪽 나눔 대조", "웹 쪽 나눔이 한글 PDF 각 쪽 맨 위 줄과 맞는지"),
    ("letters", "헤딩 레터 대조", "웹이 뽑은 헤딩 레터·앞 공백·레터 뒤 공백·둘째 줄 들여쓰기·왼쪽 여백이 한글 PDF 첫 줄과 같은지"),
    ("fonts", "글꼴 대조", "웹이 뽑은 글꼴·크기·굵게·색이 한글 PDF 글자와 같은지"),
    ("render", "재구성 렌더 비교", "다시 쓴 파일의 한글 PDF 가 원본 PDF 와 쪽마다 같은지"),
]
# 단계 -> 앞 단계(모두 통과해야 시작 — 하나가 막히면 「건너뜀」). 적히지 않은 단계는 바로 시작
IMPORT_DEPS = {"model": ["xml"], "map": ["pdf"], "pages": ["map"], "letters": ["map"], "fonts": ["map"], "render": ["xml", "pdf"]}
EDIT_DEPS = {"eowpml": ["epackage"], "esave": ["epackage"], "epages": ["epdf"], "etext": ["epdf"]}
EDIT_STEPS = [
    ("epackage", "수정본 패키지", "바뀐 멤버·다시 열었을 때 바뀐 블록이 고친 블록뿐인지"),
    ("eowpml", "수정본 OWPML 검사", "저장본에 원본에 없던 종류의 OWPML 위반이 없는지"),
    ("epdf", "수정본 PDF 출력", "저장본을 한글로 PDF 출력"),
    ("esave", "한글 다시 저장", "내보낸 HWPX 를 한글이 열어 HWPX 로 다시 저장할 수 있는지·다시 저장한 글이 같은지"),
    ("epages", "쪽 차이 대조", "달라진 쪽이 고친 블록이 있는 쪽(과 그 뒤로 밀린 쪽)뿐인지"),
    ("etext", "수정 글 반영", "고친 블록의 새 글이 수정본 PDF 에 있는지"),
]


_DOCX_WORDS = [("OWPML 표준 검사", "OOXML 참조 검사"),
               ("원본을 OWPML 2024 XSD·참조 규칙으로 검사 — 편집 판정의 기준선(spec_owpml_편집 ② §1)",
                "원본을 OOXML 참조 규칙(관계·콘텐츠 형식·스타일·번호·표 구조·자식 순서)으로 검사 — 편집 판정의 기준선(spec_docx_웹편집 ② §3)"),
               ("한글이", "Word 가"), ("한글로", "Word 로"), ("한글", "Word"), ("HWPX", "DOCX"), ("OWPML", "OOXML")]


def steps(kind, fmt="hwpx"):
    """검증 단계 (키, 제목, 설명) — 키는 형식과 무관(화면이 키로 읽음), docx 는 제목·설명의 한글 → Word, OWPML → OOXML."""
    specs = IMPORT_STEPS if kind == "import" else EDIT_STEPS
    if fmt != "docx":
        return specs

    def tr(s):
        for a, b in _DOCX_WORDS:
            s = s.replace(a, b)
        return s
    return [(k, tr(t), tr(a)) for k, t, a in specs]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def flat_texts(blocks):
    """{블록 id: 글} — 문단(최상위·칸 안·캡션)만."""
    out = {}

    def walk(bs):
        for b in bs:
            if b.get("type") == "paragraph":
                out[b["id"]] = b.get("text") or ""
            for c in b.get("cells") or ():
                walk(c.get("blocks") or [])
    walk(blocks)
    return out


def rebuild_all(data, fmt="hwpx"):
    """파서가 읽는 XML 멤버를 모두 다시 쓴 zip — (바이트, 다르게 나온 멤버 목록, 다시 쓴 멤버 수)."""
    if fmt == "docx":
        return _rebuild_docx(data)
    doc = HwpxDoc(data)
    differ = [n for n in doc._roots if doc._dump(n) != zip_guard.read(doc._zip, n)]
    for n in doc._roots:
        doc._mark(n)
    return doc.save(), differ, len(doc._roots)


def docx_writable(doc):
    """어댑터가 고쳐 다시 쓸 수 있는 XML 부분 — 본문·그 관계·스타일·번호·콘텐츠 형식(머리말·docProps·customXml 은 읽지도 쓰지도 않음)."""
    return [n for n in dict.fromkeys(["[Content_Types].xml", doc._doc, doc._rels_name, doc._sub.get("styles"), doc._sub.get("numbering")])
            if n and n in doc._zip.NameToInfo]


def _rebuild_docx(data):
    """docx: 어댑터가 다시 쓸 수 있는 XML 부분(docx_writable)을 모두 lxml 로 다시 쓴 zip. DocxDoc.save() 는 SEQ 필드 캐시를 고쳐 쓰므로
    (_refresh_seq) 쓰지 않고 원래 ZipInfo 로 바로 쓴다 — 재직렬화 그 자체만 본다(spec_docx_웹편집 ② §4). 어댑터가 안 쓰는 부분(docProps·customXml)은
    lxml 이 빈 요소·속성 차례를 달리 써도 저장본엔 원래 바이트로 남으므로 보지 않는다."""
    doc = DocxDoc(data)
    parsed, differ = [], []
    writable = set(docx_writable(doc))
    for info in doc._zip.infolist():
        n = info.filename
        if n not in writable:
            continue
        try:
            doc._part(n)
        except Exception:  # 잘 짜이지 않은 XML — 다시 쓸 수 없음(원본 바이트는 저장 때 그대로)
            differ.append(n)
            continue
        parsed.append(n)
        if doc._dump(n) != zip_guard.read(doc._zip, n):
            differ.append(n)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for info in doc._zip.infolist():
            z.writestr(copy.copy(info), doc._dump(info.filename) if info.filename in parsed else zip_guard.read(doc._zip, info))
    return out.getvalue(), differ, len(parsed) + len([n for n in differ if n not in parsed])


def changed_members(a, b):
    """두 zip 에서 내용이 다른 멤버·한쪽에만 있는 멤버."""
    za, zb = zipfile.ZipFile(io.BytesIO(a)), zipfile.ZipFile(io.BytesIO(b))
    na, nb = {i.filename: i for i in za.infolist()}, {i.filename: i for i in zb.infolist()}
    out = []
    for n in dict.fromkeys([*na, *nb]):
        if n not in na or n not in nb:
            out.append(n)
        elif na[n].CRC != nb[n].CRC or na[n].file_size != nb[n].file_size:
            out.append(n)
    return out, list(na) == list(nb)


def _para_seq(doc):
    """문서 차례의 문단 글(공백 뺀 NFKC) — 한글이 다시 저장하면 id·런 구조는 달라도 문단 차례와 글은 같아야 한다."""
    out = []

    def walk(bs):
        for b in bs:
            if b.get("type") == "paragraph":
                out.append(re.sub(r"\s+", "", unicodedata.normalize("NFKC", (b.get("text") or "").replace(" ", " "))))
            for c in b.get("cells") or ():
                walk(c.get("blocks") or [])
    walk(doc.blocks())
    return out


def resave_check(ours, again_bytes, fmt="hwpx"):
    """(status, detail, extra) — 내보낸 문서(ours)와 한글(docx 는 Word)이 다시 저장한 바이트의 문단 글 차례 대조.
    docx 는 빈 문단을 셈에서 뺀다 — Word 는 본문·칸이 표로 끝나면 다시 저장할 때 빈 문단을 하나 더한다(references/DOCX_포맷.md)."""
    a, b = _para_seq(ours), _para_seq(KIT[fmt][0](again_bytes))
    note = ""
    if fmt == "docx":
        empty = sum(1 for x in b if not x) - sum(1 for x in a if not x)
        a, b = [x for x in a if x], [x for x in b if x]
        note = f" · 빈 문단 {empty:+d}개는 셈에서 뺌(Word 가 표 뒤에 더함)" if empty else ""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    same = sum(m.size for m in sm.get_matching_blocks())
    diff = [{"ours": " / ".join(a[i1:i2])[:120], "hangul": " / ".join(b[j1:j2])[:120]}
            for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"][:20]
    who = pdf_render.app_name(fmt)
    head = f"{who}{'이' if fmt == 'hwpx' else ' 가'} 다시 저장함({len(again_bytes):,} B) · 문단 {len(a):,}개 중 글·차례가 같은 것 {same:,}개" + note
    if same == len(a) == len(b):
        return "ok", head, {"diff": []}
    return "warn", head + f" · 다른 곳 {len(diff)}군데({who}{'이' if fmt == 'hwpx' else ' 가'} 문단을 고쳐 씀 — 목록 확인)", {"diff": diff}


class Job:
    def __init__(self, kind, specs):
        self.kind, self.started, self.finished, self.error = kind, time.time(), None, None
        self.steps = [{"key": k, "title": t, "about": a, "status": "wait", "detail": ""} for k, t, a in specs]
        self.lock = threading.Lock()

    def step(self, key):
        return next(s for s in self.steps if s["key"] == key)

    def set(self, key, status, detail="", **extra):
        with self.lock:
            s = self.step(key)
            s.update(status=status, detail=detail, **extra)
            if status == "run":
                s["t0"] = time.time()
            elif "t0" in s:
                s["seconds"] = round(time.time() - s.pop("t0"), 1)

    def view(self):
        with self.lock:
            steps = [{k: v for k, v in s.items() if k != "t0"} for s in self.steps]
        worst = "ok"
        for s in steps:
            if s["status"] in ("run", "wait"):
                worst = "run"
                break
        else:
            order = ["ok", "skip", "warn", "fail"]
            worst = max((s["status"] for s in steps), key=order.index, default="ok")
            if worst == "skip":
                worst = "ok"
        return {"kind": self.kind, "started": self.started, "status": worst if not self.error else "fail", "steps": steps,
                "running": self.finished is None, "error": self.error,
                "seconds": round((self.finished or time.time()) - self.started, 1)}


class Stop(Exception):
    """단계가 뒤 단계를 막는다 — 그 단계 상태는 함수가 이미 적었고(또는 status 로 적고), 뒤 단계는 reason 으로 「건너뜀」."""

    def __init__(self, reason, status=None):
        super().__init__(reason)
        self.reason, self.status = reason, status


def run_flow(job, fns, deps):
    """단계 함수 {키: fn()} 를 의존 관계 deps {키: [앞 단계]} 대로 병렬 실행 — 앞 단계가 모두 통과한 단계는 바로 스레드에서 시작,
    앞 단계가 막히면(Stop·오류) 그 뒤 단계는 「건너뜀」. 예기치 않은 오류는 그 단계 실패 + job.error. 끝나면 job.finished."""
    state, running, cv = {}, set(), threading.Condition()

    def worker(k):
        reason = None
        try:
            fns[k]()
        except Stop as e:
            reason = e.reason
            if e.status:
                job.set(k, e.status, e.reason)
        except Exception as e:  # 한 단계가 예기치 않게 죽어도 화면에는 그 단계 실패로 보인다
            job.error = job.error or f"{type(e).__name__}: {e}"
            traceback.print_exc()
            job.set(k, "fail", f"{type(e).__name__}: {e}")
            reason = "앞 단계 오류로 건너뜀"
        with cv:
            state[k] = reason
            running.discard(k)
            cv.notify_all()

    try:
        pending = [s["key"] for s in job.steps if s["key"] in fns]
        with cv:
            while pending or running:
                moved = False
                for k in list(pending):
                    before = deps.get(k, ())
                    blocked = next((state[d] for d in before if state.get(d)), None)
                    if blocked:
                        job.set(k, "skip", blocked)
                        state[k] = blocked
                    elif all(d in state for d in before):
                        running.add(k)
                        threading.Thread(target=worker, args=(k,), daemon=True, name=f"verify-{k}").start()
                    else:
                        continue
                    pending.remove(k)
                    moved = True
                if moved:
                    continue
                if not running:  # 앞 단계가 목록에 없는 단계 — 막힌 채 남지 않게
                    for k in pending:
                        job.set(k, "skip", "앞 단계가 없어 건너뜀")
                    break
                cv.wait()
    finally:
        job.finished = time.time()


# ---- 가져오기 검증 ---------------------------------------------------------------------------------

def run_import(sess, job):
    """sess: 서버 문서(original 바이트·blocks·pdf·mapping 을 채운다). 단계는 IMPORT_DEPS 대로 병렬 — 패키지·XML·OWPML 검사와 원본 PDF 출력이
    함께 시작하고, 매핑 뒤 쪽 나눔·레터·글꼴 대조가 함께, 재구성 PDF 는 XML 단계 직후 다른 한글 프로세스에서 미리 찍는다."""
    data, ctx = sess.original, {}
    fmt = fmt_of(sess)
    Doc, check, _ = KIT[fmt]
    app = pdf_render.app_name(fmt)

    def package():
        job.set("package", "run")
        same = Doc(data).save() == data
        job.set("package", "ok" if same else "fail",
                f"{len(data):,} B · SHA-256 {sha256(data)[:16]}… {'일치' if same else '불일치'}")

    def xml():
        job.set("xml", "run")
        rebuilt, differ, n = rebuild_all(data, fmt)
        sess.rebuilt = ctx["rebuilt"] = rebuilt
        if rebuilt != data and pdf_render.available(fmt):  # 재구성 렌더 단계가 쓸 PDF 를 원본 PDF 와 동시에(같은 바이트는 캐시·잠금으로 한 번만)
            threading.Thread(target=_prefetch, args=(rebuilt, fmt), daemon=True, name="verify-prefetch").start()
        job.set("xml", "fail" if differ else "ok",
                f"XML 멤버 {n}개 중 {n - len(differ)}개 바이트 동일" + (f" — 다름: {', '.join(differ[:5])}" if differ else ""),
                members=differ)

    def model():
        job.set("model", "run")
        a, b = flat_texts(sess.blocks), flat_texts(Doc(ctx["rebuilt"]).blocks())
        bad = [i for i in a if a.get(i) != b.get(i)] + [i for i in b if i not in a]
        job.set("model", "fail" if bad else "ok",
                f"문단 {len(a):,}개 글 " + ("모두 동일" if not bad else f"{len(bad)}개 다름"), blocks=bad[:50])

    def owpml():
        job.set("owpml", "run")
        od = Doc(data)
        od.blocks()
        res = check.check_doc(od)
        base = check.counts(res)
        sess.owpml_base = base
        n_rules = len(res["rules"])
        top = base["schema"].most_common(3)
        xsd = (f"OWPML 2024 XSD 위반 {len(res['schema']):,}건 {len(base['schema'])}가지"
               + (" — 한글 저장본도 공개 XSD 와 어긋남(" + ", ".join(f"{check.kind_text(k)} {c:,}" for k, c in top) + ")" if top else "")
               if fmt == "hwpx" else "OOXML XSD 검사는 없음(참조 규칙만)")
        job.set("owpml", "warn" if n_rules else "ok",
                f"참조 규칙 위반 {n_rules}건 · {xsd} · 편집은 이 기준선에 없던 종류가 생기면 막는다",
                kinds=[{"kind": check.kind_text(k), "count": c} for k, c in base["schema"].most_common(20)],
                rules=[{"kind": check.kind_text(v["kind"]), "message": v["message"]} for v in res["rules"][:20]])

    def pdf():
        if not pdf_render.available(fmt):
            raise Stop(f"이 PC 에 {app}({pdf_render.PROGIDS[fmt]} COM)이 없어 PDF 단계를 건너뜀", "skip")
        job.set("pdf", "run", "한글로 PDF 출력 중 — 한글 「파일 접근」 창이 뜨면 「모두 허용」" if fmt == "hwpx"
                else f"{app} 로 PDF 출력 중(바깥 연결을 뗀 사본 — 매크로·대화상자 끔)")
        try:
            sess.pdf["original"] = pdf_render.export_pdf(data, fmt=fmt)
        except Exception as e:
            job.set("pdf", "fail", str(e))
            raise Stop("원본 PDF 가 없어 건너뜀") from e
        n_pages = pdf_map.page_count(sess.pdf["original"])
        two = pdf_map.two_up(sess.pdf["original"], sess.blocks)
        unit = "장" if two else "쪽"
        ctx.update(n_pages=n_pages, two=two, unit=unit)
        job.set("pdf", "ok", f"{n_pages}{unit}" + (" — 문서 설정대로 한 장에 두 쪽씩 모아 찍힘" if two else ""), pages=n_pages, unit=unit)

    def map_():
        job.set("map", "run")
        m, pages, its = pdf_map.map_detail(sess.blocks, sess.pdf["original"], halves=ctx["two"], chars=True)
        m["unit"] = ctx["unit"]
        if fmt == "docx":
            word_pdf_lines(pages)
        sess.mapping = m
        ctx.update(mapping=m, pages=pages, its=its)
        status = "ok" if m["ratio"] >= MAP_OK else "warn" if m["ratio"] >= MAP_WARN else "fail"
        job.set("map", status, f"글 있는 문단 {m['total']:,}개 중 {m['located']:,}개의 PDF 위치를 찾음({m['ratio'] * 100:.1f}%)"
                + (" — 못 찾은 문단도 파일에는 그대로 있다(① 바이트 동일); 위치만 모름" if m["missing"] else ""),
                missing=m["missing"][:200], missingCount=len(m["missing"]))

    def pages_():
        m, two, n_pages = ctx["mapping"], ctx["two"], ctx["n_pages"]
        job.set("pages", "run")
        c = {}
        for x in m["checks"]:
            c[x["status"]] = c.get(x["status"], 0) + 1
        bad = c.get("miss", 0) + c.get("none", 0)
        n_doc = m["pageCount"]
        parts = [f"문서 {n_doc}쪽" + (f"(PDF {n_pages}장)" if two else "")]
        if n_doc > 1:
            parts.append(f"둘째 쪽부터 PDF 맨 위 줄로 확인 {c.get('ok', 0) + c.get('moved', 0)}쪽" + (f"(그중 매핑 나눔을 고친 {c['moved']}쪽)" if c.get("moved") else ""))
        if c.get("split"):
            parts.append(f"앞 쪽에서 이어진 문단·표 행 {c['split']}쪽(웹은 그 뒤에서 나눔)")
        if c.get("short") or c.get("blank"):
            parts.append(f"맨 위 줄이 짧거나 빈 쪽 {c.get('short', 0) + c.get('blank', 0)}쪽(확인 못 함)")
        if bad:
            parts.append(f"못 맞춤 {bad}쪽")
        parts.append(f"문단이 PDF 와 같은 쪽 {m['agree'] * 100:.1f}%")
        job.set("pages", "fail" if bad > max(1, n_doc // 10) else "warn" if bad or m["agree"] < 0.9 else "ok", " · ".join(parts),
                checks=[x for x in m["checks"] if x["status"] != "ok"][:100])

    def letters():
        job.set("letters", "run")
        doc = Doc(data)  # 줄 배치 캐시(둘째 줄 종류 — hwpx 만)를 읽는다 — 편집 중인 세션 문서와 따로(같은 바이트라 블록 id 같음)
        blocks = doc.blocks()
        if fmt == "docx":
            hang_as_hwpx(blocks)
        rows = headings.extract(blocks, doc)["rows"]
        r = pdf_style.check_heads(rows, blocks, ctx["its"], ctx["pages"])
        job.set("letters", *letters_verdict(r), heads=r, missing=_issue_list(r["issues"]))

    def fonts():
        job.set("fonts", "run")
        table = sess.doc.font_table(sess.blocks) if fmt == "docx" else sess.doc.font_table()  # 웹 글꼴 계획(app/fonts.py)과 같은 표
        r = pdf_style.check_fonts(sess.blocks, ctx["its"], ctx["pages"], table=table)
        job.set("fonts", *fonts_verdict(r), fonts={k: r[k] for k in ("faces", "latin", "scale", "chars", "paragraphs")},
                missing=_style_list(r, flat_texts(sess.blocks)))

    def render():
        rebuilt = ctx["rebuilt"]
        job.set("render", "run", f"다시 쓴 파일을 {app}{'로' if fmt == 'hwpx' else ' 로'} PDF 출력 중")
        if rebuilt == data:
            sess.pdf["rebuilt"] = sess.pdf["original"]
            job.set("render", "ok", "다시 쓴 파일이 원본과 바이트 동일 — 같은 PDF")
            return
        sess.pdf["rebuilt"] = pdf_render.export_pdf(rebuilt, fmt=fmt)
        cmp = pdf_map.compare_pdfs(sess.pdf["original"], sess.pdf["rebuilt"])
        real = [d["page"] for d in cmp["diff"] if not d["minor"]]
        minor = [d["page"] for d in cmp["diff"] if d["minor"]]
        same_count = cmp["pagesA"] == cmp["pagesB"]
        status = "fail" if real or not same_count else "warn" if minor else "ok"
        u = (sess.mapping or {}).get("unit", "쪽")
        detail = f"{cmp['pagesA']}{u} vs {cmp['pagesB']}{u} · " + (
            "모든 쪽 픽셀 동일" if status == "ok" else f"다른 쪽 {len(real)}개" + (f" · 미세 차이(글자·기호·줄 위치·그림 같음, 눈으로 확인 권장) {len(minor)}개" if minor else ""))
        job.set("render", status, detail, diffPages=cmp["diff"], minor=minor, unexpected=real, compare="rebuilt")

    run_flow(job, {"package": package, "xml": xml, "model": model, "owpml": owpml, "pdf": pdf, "map": map_, "pages": pages_,
                   "letters": letters, "fonts": fonts, "render": render}, IMPORT_DEPS)


# Word PDF 가 Wingdings 글머리에 붙인 유니코드 ↔ 웹 라벨(docx_doc._PUA_BULLET): Wingdings 「l」(0x6C) = ⚫ U+26AB(AIP 서식, Word 16)
_WORD_BULLETS = {"⚫": "●", "⬤": "●"}


def word_pdf_lines(pages):
    """Word PDF 줄 다듬기(spec_docx_웹편집 ② §4 — 레터·글꼴 대조 전, 제자리): Word 는 줄 끝마다 빈칸을 찍어 같은 높이 오른쪽 칸 글의 「앞 공백」으로
    잘못 세이므로 떼고, Symbol·Wingdings 글머리(PUA U+F0xx — PDF 에도 그대로)는 웹 라벨과 같은 글자로(docx_doc._PUA_BULLET)."""
    from app.docx_doc import _PUA_BULLET
    pua = {chr(0xF000 + k): v for k, v in _PUA_BULLET.items()}
    pua.update(_WORD_BULLETS)
    for p in pages:
        for ln in p["lines"]:
            ch = ln.get("chars")
            if ch is not None:
                while ch and ch[-1][0].isspace():
                    ch.pop()
                ln["chars"] = [(pua.get(c[0], c[0]), *c[1:]) for c in ch]
            ln["text"] = "".join(pua.get(c, c) for c in ln["text"].rstrip())
    return pages


def hang_as_hwpx(blocks):
    """docx 내어쓰기(w:ind hanging): Word 는 둘째 줄부터가 left, 첫 줄이 left − hanging — 레터 대조(pdf_style 왼쪽 여백·headings 규칙 글)는 hwpx 뜻
    (첫 줄 = 왼쪽 여백, 둘째 줄이 더 들어감)으로 견주므로 첫 줄 들여쓰기가 음수인 문단의 indentLeftMm 을 첫 줄 자리로 옮긴다(제자리 — 새로 연 문서의
    블록에만 쓸 것). 둘째 줄 폭(hangMm = −첫 줄)은 두 뜻이 같다(spec_docx_웹편집 ② §2)."""
    def walk(bs):
        for b in bs:
            f = b.get("format") if b.get("type") == "paragraph" else None
            if f and (f.get("firstLineMm") or 0) < 0:
                f["indentLeftMm"] = round((f.get("indentLeftMm") or 0) + f["firstLineMm"], 2)
            for c in b.get("cells") or ():
                walk(c.get("blocks") or [])
    walk(blocks)
    return blocks


def _prefetch(data, fmt="hwpx"):
    try:
        pdf_render.export_pdf(data, fmt=fmt)
    except Exception:  # 단계가 다시 찍으며 오류를 알린다
        pass


def _issue_list(issues):
    """레터 대조의 다른 곳 -> 화면 「확인할 문단」 목록 [{id, text}]."""
    what = {"letter": "레터", "lead": "앞 공백", "gap": "레터 뒤 공백", "line2": "둘째 줄 들여쓰기", "left": "왼쪽 여백", "outline": "웹에 없는 개요 번호"}
    return [{"id": i["id"], "text": f"{what[i['kind']]} 웹 「{i['web']}」 · PDF 「{i['pdf']}」({i['page']}쪽) — {i['text']}"} for i in issues]


def _style_list(r, texts):
    """글꼴 대조의 다른 글자(문단마다 하나) -> 화면 「확인할 문단」 목록 [{id, text}] — 어느 문단인지 글 앞부분을 붙인다."""
    what = {"size": "크기", "bold": "굵게", "color": "색"}
    return [{"id": e["id"], "text": f"{what[k]} 웹 {e['web']} · PDF {e['pdf']}({e['page']}쪽, 「{e['char']}」) — {texts.get(e['id'], '')[:40]}"}
            for k in ("size", "bold", "color") for e in r[k]["examples"]][:200]


def _ratio(ok, bad):
    return f"{ok}/{ok + bad}"


def letters_verdict(r):
    """(상태, 설명) — 레터 글자가 다른 헤딩이 LETTER_FAIL 을 넘으면 실패, 다른 곳이 하나라도 있으면 주의."""
    if not r["total"]:
        return "ok", "헤딩 문단(레터·개요·자동 번호) 없음"
    c = {k: (r[k].get("ok", 0), r[k].get("bad", 0)) for k in ("letter", "lead", "gap", "line2", "left")}
    parts = [f"헤딩 문단 {r['total']:,}개 중 PDF 첫 줄을 잰 것 {r['checked']:,}개",
             f"레터 같음 {_ratio(*c['letter'])}", f"앞 공백 칸 수 {_ratio(*c['lead'])}", f"레터 뒤 공백 칸 수 {_ratio(*c['gap'])}"]
    if sum(c["line2"]):
        parts.append(f"둘째 줄 들여쓰기 {_ratio(*c['line2'])}(±{pdf_style.TOL_MM}mm)")
    if sum(c["left"]):
        parts.append(f"본문 왼쪽 여백 {_ratio(*c['left'])}")
    if r["missingOnWeb"]:
        parts.append(f"PDF 엔 찍히는데 웹엔 없는 개요 번호 {r['missingOnWeb']}개")
    if r["unknown"]:
        parts.append(f"PDF 자리를 모름 {r['unknown']}개(글 없는 줄·못 찾은 문단·같은 글이 여러 칸)")
    bad = sum(b for _, b in c.values())
    status = ("fail" if c["letter"][1] > max(2, LETTER_FAIL * r["checked"]) else
              "warn" if bad or r["missingOnWeb"] else "ok")
    return status, " · ".join(parts)


VERDICT_KO = {"same": "같음", "subst": "둘 다 대체", "equiv": "한글 전용 글꼴 → 같은 디자인", "differ": "웹이 다른 글꼴",
              "hangul": "한글 전용 글꼴(웹은 대체)", "unknown": "모름"}


def fonts_verdict(r):
    """(상태, 설명) — 크기(웹 서식에 없는 첨자로 보이는 것 빼고)·굵게·색이 다른 글자가 STYLE_FAIL 을 넘으면 실패, 다른 글자·다른 글꼴이 있으면 주의."""
    n = r["chars"]
    if not n:
        return "skip", "PDF 글자와 맞춘 문단이 없음"
    size, bold, color = r["size"], r["bold"], r["color"]
    real = size["bad"] - size["script"]
    known = [f"윗·아래첨자 {size['scripted']:,}자" if size.get("scripted") else "", f"장평 {size['ratio']:,}자" if size.get("ratio") else ""]
    parts = [f"글자 {n:,}자(문단 {r['paragraphs']:,}개)를 PDF 글자와 하나씩 맞춤",
             f"크기 다름 {size['bad']:,}자" + (f"(그중 첨자로 보임 {size['script']:,}자 — 웹 서식에 첨자 없음)" if size["script"] else "")
             + (f" — {'·'.join(x for x in known if x)}는 그 크기(첨자 × {pdf_style.SCRIPT_SIZE:g}, 장평 √)로 견줌" if any(known) else ""),
             f"굵게 다름 {bold['bad']:,}자" + (f"(Type3 글꼴 {n - bold['checked']:,}자는 모름)" if n > bold["checked"] else ""),
             f"색 다름 {color['bad']:,}자"]
    for name, rows in (("한글 글자 글꼴", r["faces"]), ("영문·숫자 글꼴", r["latin"])):
        c = Counter(f["verdict"] for f in rows)
        if c:
            parts.append(f"{name} " + ", ".join(f"{VERDICT_KO[v]} {c[v]}종" for v in VERDICT_KO if c[v]))
    bad_face = [f for f in r["faces"] + r["latin"] if f["verdict"] in ("differ", "hangul")]
    worst = max(real, bold["bad"], color["bad"]) / n
    status = "fail" if worst > STYLE_FAIL else "warn" if size["bad"] or bold["bad"] or color["bad"] or bad_face else "ok"
    return status, " · ".join(parts)


# ---- 출력파일 검증 (옛 이름 편집 검증) ---------------------------------------------------------------

def run_edit(sess, job, saved, edited, blocks_now, unrestored=frozenset(), touched=frozenset(), origin=None, ids=None):
    """saved: 지금 저장 바이트, edited: 글이 달라야 하는 블록 id(글 고침·새 문단·지운 문단), blocks_now: 지금 블록 트리,
    unrestored: 글은 원래대로인데 원본 XML 로 못 되돌린 문단(줄 배치 캐시 없음), touched: 글은 같아도 되는 모양·구조 편집 문단,
    origin: 새 문단 → 생겨난 문단(쪽 찾기), ids: 블록 id 자리표 — 저장본을 다시 열 때 되붙여 문단 수가 바뀌어도 같은 id 로 비교."""
    origin, orig, ctx = origin or {}, sess.original, {}
    fmt = fmt_of(sess)
    Doc, check, inside = KIT[fmt]
    app = pdf_render.app_name(fmt)

    def epackage():
        job.set("epackage", "run")
        members, order_same = changed_members(orig, saved)
        reopened = ctx["reopened"] = Doc(saved)
        adopted = bool(ids) and reopened.adopt_ids(ids)
        before, after = sess.orig_texts, flat_texts(reopened.blocks())
        moved = sorted(i for i in set(before) | set(after) if before.get(i) != after.get(i))
        extra = sorted(set(moved) - edited - set(touched))
        missing = sorted(edited - set(moved))
        if ids and not adopted:
            extra = extra or ["(블록 id 자리표를 되붙이지 못함)"]
        ok = not extra and not missing and order_same and all(m.startswith(inside) for m in members)
        same = saved == orig
        job.set("epackage", "fail" if not ok else "warn" if unrestored else "ok",
                ("저장본 = 원본과 바이트 동일" if same else
                 f"고친 문단 {len(edited | set(touched))}개 · 바뀐 멤버 {len(members)}개({', '.join(members[:4]) or '없음'})")
                + (f" · 예상 밖 블록 {len(extra)}개" if extra else "") + (f" · 반영 안 된 블록 {len(missing)}개" if missing else "")
                + ((f" · 글은 원래대로이나 줄 배치 캐시를 못 되돌린 문단 {len(unrestored)}개(한글이 다시 조판)" if fmt == "hwpx"
                    else f" · 글은 원래대로이나 원본 XML 로 못 되돌린 문단 {len(unrestored)}개") if unrestored else "")
                + ("" if order_same else " · 멤버 순서 바뀜"),
                members=members, extra=extra[:50], missing=missing[:50], same=same)

    def eowpml():
        reopened = ctx["reopened"]
        job.set("eowpml", "run")
        base = sess.owpml_base or check.counts(check.check_doc(Doc(orig)))
        v = check.verdict(reopened, base, check.check_doc(reopened))
        job.set("eowpml", v["status"], check.summary_text(v), owpml={k: v[k] for k in ("new", "rules", "grown")},
                blocks=[e["block"] for x in v["new"] + v["rules"] for e in x["examples"] if e["block"]][:50])

    def epdf():
        if "original" not in sess.pdf:
            raise Stop(f"원본 PDF 가 없어 건너뜀(가져오기 검증의 {app} PDF 단계)", "skip")
        job.set("epdf", "run", f"저장본을 {app}{'로' if fmt == 'hwpx' else ' 로'} PDF 출력 중")
        try:
            sess.pdf["edited"] = pdf_render.export_pdf(saved, fmt=fmt)
        except Exception as e:
            job.set("epdf", "fail", str(e))
            raise Stop("수정본 PDF 가 없어 건너뜀") from e
        n_pages = pdf_map.page_count(sess.pdf["edited"])
        unit = (sess.mapping or {}).get("unit", "쪽")
        job.set("epdf", "ok", f"{n_pages}{unit}", pages=n_pages)

    def esave():  # PDF 와 무관 — 한글만 있으면 수정본 PDF 출력과 다른 한글 프로세스에서 함께
        if not pdf_render.available(fmt):
            raise Stop(f"이 PC 에 {app}({pdf_render.PROGIDS[fmt]} COM)이 없어 건너뜀", "skip")
        up = fmt.upper()
        job.set("esave", "run", f"내보낸 {up} 를 {app}{'로' if fmt == 'hwpx' else ' 로'} 열어 {up} 로 다시 저장 중")
        try:
            again = pdf_render.resave(saved, fmt=fmt)
        except Exception as e:
            job.set("esave", "fail", f"{app}{'이' if fmt == 'hwpx' else ' 가'} 내보낸 {up} 를 다시 저장하지 못함 — {e}")
        else:
            status, detail, extra = resave_check(ctx["reopened"], again, fmt)
            job.set("esave", status, detail, **extra)

    def epages():
        job.set("epages", "run")
        cmp = pdf_map.compare_pdfs(sess.pdf["original"], sess.pdf["edited"])
        diff = [d["page"] for d in cmp["diff"]]
        mpages = (sess.mapping or {}).get("pages", {})
        sheets = (sess.mapping or {}).get("sheets") or []
        sheet = lambda p: sheets[p - 1] if 0 < p <= len(sheets) else p  # noqa: E731 — 문서 쪽 → PDF 장(2쪽 모아 찍기)
        hit = set(edited) | set(unrestored) | set(touched)
        where = lambda i: mpages.get(i) or mpages.get(origin.get(i), ())  # noqa: E731 — 새 문단은 생겨난 문단의 쪽
        expect = sorted({sheet(p) for i in hit for p in where(i)})
        unknown = sorted(i for i in hit if not where(i))
        first = min(expect) if expect else None
        # 미세 차이: 글·줄 자리가 같고 글자 가장자리만 다른 쪽 — 고친 문단의 줄 캐시를 지우면 한글이 그 구역을 다시 조판하며 생긴다
        minor = [d["page"] for d in cmp["diff"] if d["minor"] and d["page"] not in expect]
        rest = [p for p in diff if p not in expect and p not in minor]
        shifted = [p for p in rest if first is not None and p > first]
        unexpected = [p for p in rest if p not in shifted]
        if unknown and not expect:
            unexpected, shifted = [], rest
        status = "fail" if unexpected else "warn" if shifted or cmp["pagesA"] != cmp["pagesB"] or unknown else "ok"
        u = (sess.mapping or {}).get("unit", "쪽")
        parts = [f"{cmp['pagesA']}{u} → {cmp['pagesB']}{u}", f"다른 {u} {len(diff)}개"]
        if expect:
            parts.append(f"고친 문단이 있는 {u} {', '.join(map(str, expect[:12]))}")
        if shifted:
            parts.append(f"고친 곳 이후 차이 {len(shifted)}개(밀림 추정 — 원인 미확인, 비교 창으로 확인)")
        if minor:
            parts.append(f"미세 차이 {len(minor)}개(글자·기호·줄 위치·그림 같음)")
        if unexpected:
            parts.append(f"예상 밖 차이 {', '.join(map(str, unexpected[:12]))}")
        if unknown:
            parts.append(f"PDF 위치를 모르는 고친 문단 {len(unknown)}개")
        job.set("epages", status, " · ".join(parts), diffPages=cmp["diff"], expected=expect, shifted=shifted,
                minor=minor, unexpected=unexpected, compare="edited")

    def etext():
        job.set("etext", "run")
        two = bool((sess.mapping or {}).get("twoUp"))
        pages = pdf_map.read_pdf(sess.pdf["edited"], two)
        allits = pdf_map.locate(pdf_map.items(blocks_now), pages)
        sess.mapping_edited = {"pages": {it["id"]: it["pages"] for it in allits if "pages" in it}, "pageCount": len(pages),
                               "ratio": round(sum("pages" in it for it in allits) / len(allits), 4) if allits else 1.0,
                               "unit": (sess.mapping or {}).get("unit", "쪽"), "twoUp": two, "sheets": [p["sheet"] + 1 for p in pages]}
        texts = flat_texts(blocks_now)
        now = {i: texts[i] for i in edited if i in texts}  # 지운 문단(합치기)은 글이 다른 문단으로 옮겨 감 — 그 문단에서 본다
        res = pdf_map.check_texts(now, pages, sess.mapping_edited["pages"])
        strict, loose, lost, empty = res["strict"], res["loose"], res["lost"], res["empty"]
        n = len(now) - len(empty)
        gone = [i for i in empty if i in sess.orig_texts]           # 원래 글이 있던 문단을 모두 지움
        new_empty = [i for i in empty if i not in sess.orig_texts]  # 빈 새 문단(표 행·열 넣기 등) — 지운 것이 아님
        tail = ((f"글을 모두 지운 문단 {len(gone)}개" if gone else "") + (" · " if gone and new_empty else "")
                + (f"빈 새 문단(표 행·열 넣기 등) {len(new_empty)}개" if new_empty else ""))
        status = "fail" if lost else "warn" if loose else "ok"
        detail = (f"고친 문단 {n}개 중 글자·기호까지 같은 것 {len(strict)}개" + (f", 글자·숫자만 같은 것 {len(loose)}개(기호는 눈으로 확인)" if loose else "")
                  + (f", 못 찾음 {len(lost)}개" if lost else "") + (f" · {tail}" if tail else ""))
        job.set("etext", status, detail if n else f"글이 남은 고친 문단 없음 — {tail}",
                missing=[{"id": i, "text": texts.get(i, "")[:80]} for i in lost + loose])

    run_flow(job, {"epackage": epackage, "eowpml": eowpml, "epdf": epdf, "esave": esave, "epages": epages, "etext": etext}, EDIT_DEPS)
