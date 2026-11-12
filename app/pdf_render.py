"""한글·Word COM PDF 출력(spec_hwpx_웹편집 ② §5) — FileMergeManager render_anchors.Exporter 를 옮긴 것(hwpx = 한글, docx = Word).

자식 프로세스마다 `HWPFrame.HwpObject` 를 계속 쓴다: 한글 「파일 접근 확인」 창(보안 모듈 미등록)은 프로세스마다 한 번이라 「모두 허용」을
한 번 누르면 그 뒤 문서는 묻지 않는다. 시간 초과·실패면 자식과 그것이 띄운 한글만 죽이고 다음에 새로 띄운다(한글 COM 은 가끔 멈춘다 —
references/HWPX_렌더링_검증.md). 자식은 풀(Pool, 기본 2개)로 두어 검증 단계·문서가 동시에 출력한다. PDF 는 출력용 사본(render_copy — hwpx 는
한 쪽씩 찍기 one_per_sheet, docx 는 바깥을 부르지 않게 한 docx_harden.strip_external)의 바이트 SHA-1 이름으로 캐시한다. Word 는 같은 자식이
처음 쓸 때 따로 띄운다(매크로·대화상자 끔, 읽기 전용)."""
import hashlib
import io
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

LIMIT_BASE, LIMIT_PER_MB, LIMIT_MOST = 120, 10, 900
_PRINT_METHOD = re.compile(rb'(<config:config-item\s+name="PrintMethod"\s+type="short"\s*>)\s*([1-9]\d*)\s*(</config:config-item>)')
_SETTINGS_MAX = 1 << 20


def render_dir() -> Path:
    """%LOCALAPPDATA%\\NewFileManager\\render, env NFM_RENDER 가 있으면 그것."""
    if env := os.environ.get("NFM_RENDER"):
        return Path(env)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "render"


def sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:20]


def export_limit(size: int) -> int:
    """한 문서의 PDF 출력 시간 한도(초) = 120 + MB 당 10, 상한 900."""
    return round(min(LIMIT_MOST, LIMIT_BASE + LIMIT_PER_MB * size / 2 ** 20))


PROGIDS = {"hwpx": "HWPFrame.HwpObject", "docx": "Word.Application"}  # 문서 형식 → 출력 프로그램 COM
APPS = {"hwpx": "hwp", "docx": "word"}                                   # 문서 형식 → 자식 작업의 "app"
APP_NAMES = {"hwp": "한글", "word": "Word"}


def app_name(fmt: str = "hwpx") -> str:
    """문서 형식을 찍는 프로그램 이름 — 화면 문구용("한글" | "Word")."""
    return APP_NAMES.get(APPS.get(fmt, ""), fmt)


def available(fmt: str = "hwpx") -> bool:
    """그 형식을 찍을 COM 이 등록돼 있는지 — hwpx = 한글(정식 한글 — 무료 뷰어엔 없음), docx = Word. env NFM_PDF=off 면 모두 끈다(시험)."""
    if os.environ.get("NFM_PDF", "").lower() == "off" or sys.platform != "win32" or fmt not in PROGIDS:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROGIDS[fmt] + r"\CLSID"):
            return True
    except OSError:
        return False


# 자식 스크립트: 한 줄 = 작업 {"src", "pdf"(내보낼 경로), "format", "app": hwp|word}. 프로그램은 처음 쓸 때 띄우고(띄운 프로세스 번호를 알림 —
# 시간 초과면 부모가 죽임) 계속 쓴다. Word 는 매크로·대화상자를 끄고(AutomationSecurity 3 = ForceDisable, DisplayAlerts 0) 읽기 전용·변환 확인
# 없이 연다(FileMergeManager spec_병합 ② §2-4 「렌더 하드닝」 — 넘기는 파일도 docx_harden.strip_external 사본).
_CHILD = r'''
import json, subprocess, sys
import win32com.client
def pids(name):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return {int(l.split('","')[1]) for l in out.splitlines() if l.lower().startswith('"' + name.lower() + '"')}
apps = {}
def app(kind):
    if kind not in apps:
        name = "Hwp.exe" if kind == "hwp" else "WINWORD.EXE"
        before = pids(name)
        if kind == "hwp":
            a = win32com.client.Dispatch("HWPFrame.HwpObject")
            try:
                a.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
            except Exception:
                pass
            try:
                a.XHwpWindows.Item(0).Visible = False
            except Exception:
                pass
        else:
            a = win32com.client.DispatchEx("Word.Application")
            a.Visible, a.DisplayAlerts = False, 0
            a.AutomationSecurity = 3
        apps[kind] = a
        print(json.dumps({"pids": sorted(pids(name) - before)}), flush=True)
    return apps[kind]
WORD_FORMAT = {"PDF": 17, "DOCX": 16}  # wdFormatPDF, wdFormatDocumentDefault
for line in sys.stdin:
    job = json.loads(line)
    try:
        kind = job.get("app") or "hwp"
        a = app(kind)
        fmt = job.get("format", "PDF")  # "HWPX"·"DOCX" = 그 프로그램이 다시 저장(내보내기 검증, spec_owpml_편집 ② §1)
        if kind == "hwp":
            if not a.Open(job["src"], "HWP" if job["src"].lower().endswith(".hwp") else "HWPX", "forceopen:true"):  # hwp(바이너리)도 연다 — hwp_to_hwpx
                raise RuntimeError("한글이 파일을 열지 못함")
            ok = a.SaveAs(job["pdf"], fmt, "")
            a.Clear(1)
            if not ok:
                raise RuntimeError("한글 " + fmt + " 저장 실패")
        else:
            d = a.Documents.Open(job["src"], ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False,
                                 NoEncodingDialog=True)
            try:
                d.SaveAs2(job["pdf"], FileFormat=WORD_FORMAT[fmt])
            finally:
                d.Close(False)
        print(json.dumps({"ok": True}), flush=True)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), flush=True)
for a in apps.values():
    try:
        a.Quit()
    except Exception:
        pass
'''


class Exporter:
    def __init__(self):
        self.proc, self.pids, self.lines, self.lock = None, set(), None, threading.Lock()

    def _start(self):
        self.lines, self.pids = queue.Queue(), set()
        self.proc = subprocess.Popen([sys.executable, "-X", "utf8", "-c", _CHILD], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._read, args=(self.proc.stdout, self.lines), daemon=True).start()

    @staticmethod
    def _read(out, q):
        for line in out:
            q.put(line)
        q.put(None)

    def stop(self):
        if self.proc:
            try:
                self.proc.kill()
            except OSError:
                pass
        for pid in self.pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        self.proc, self.pids = None, set()

    def run(self, src, pdf, limit, fmt="PDF", app="hwp"):
        """app = hwp(한글)|word — 한 자식 프로세스가 둘 다 띄워 쓸 수 있다(처음 쓸 때). fmt = 내보낼 형식(PDF·HWPX·DOCX)."""
        name = APP_NAMES.get(app, app)
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                self._start()
            self.proc.stdin.write(json.dumps({"src": str(src), "pdf": str(pdf), "format": fmt, "app": app}) + "\n")
            self.proc.stdin.flush()
            end = time.time() + limit
            while True:
                try:
                    line = self.lines.get(timeout=max(0.1, end - time.time()))
                except queue.Empty:
                    self.stop()
                    raise TimeoutError(f"{name} {fmt} 출력 {limit}s 초과 — " + (
                        "한글 창(파일 접근 확인 등)이 떠 있는지 보세요" if app == "hwp" else "Word 대화상자가 떠 있는지 보세요"))
                if line is None:
                    self.stop()
                    raise RuntimeError(f"{name} {fmt} 출력 프로세스가 끝남")
                msg = json.loads(line)
                if "pids" in msg:
                    self.pids |= set(msg["pids"])
                    continue
                if not msg.get("ok"):
                    self.stop()
                    raise RuntimeError(msg.get("error") or f"{name} {fmt} 출력 실패")
                return pdf


def workers() -> int:
    """동시에 띄울 한글 출력 프로세스 수 — env NFM_PDF_WORKERS(기본 2, 1~4). 프로세스마다 Hwp.exe 하나·확인 창 한 번(보안 모듈 미등록 PC)."""
    try:
        return max(1, min(4, int(os.environ.get("NFM_PDF_WORKERS", "2"))))
    except ValueError:
        return 2


class Pool:
    """한글 출력 프로세스 풀(spec_hwpx_웹편집 ② §5) — 검증 단계·문서가 병렬로 출력을 요청하면 쉬는 프로세스에 하나씩 맡긴다(없으면 기다림).
    프로세스는 처음 쓸 때 띄우고(Exporter._start) 시간 초과·실패면 그 프로세스만 죽였다가 다음 요청에 새로 띄운다."""

    def __init__(self, size):
        self.idle = queue.Queue()
        for _ in range(size):
            self.idle.put(Exporter())

    def run(self, src, out, limit, fmt="PDF", app="hwp"):
        ex = self.idle.get()
        try:
            return ex.run(src, out, limit, fmt) if app == "hwp" else ex.run(src, out, limit, fmt, app=app)
        finally:
            self.idle.put(ex)


EXPORTER = Pool(workers())
_BUSY, _BUSY_LOCK = {}, threading.Lock()  # 같은 바이트를 두 단계가 동시에 찍지 않게(캐시 이름마다 잠금)


def _once(path: Path):
    with _BUSY_LOCK:
        return _BUSY.setdefault(path.name, threading.Lock())


def one_per_sheet(data: bytes) -> bytes:
    """PDF 출력용 사본 — settings.xml 인쇄 방식(`PrintMethod`, 4 = 2쪽 모아 찍기)을 0 으로(spec_hwpx_웹편집 ② §5).
    한글 COM PDF 출력은 문서 인쇄 방식을 따라 모아 찍기 문서를 가로 장에 두 쪽씩 줄여 찍는다 — 0 이면 문서 쪽마다 한 장
    (references/HWPX_렌더링_검증.md 「2쪽 모아 찍기 PDF」). zip 이 아니거나 settings.xml·PrintMethod 가 없거나 이미 0 이면 받은 바이트 그대로.
    다른 멤버는 원래 ZipInfo(순서·압축 방식 — mimetype 첫 멤버 STORED)로 다시 쓴다. 호출하는 곳은 모두 HwpxDoc(zip_guard)를 지난 바이트."""
    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
        info = zin.getinfo("settings.xml")
    except (zipfile.BadZipFile, KeyError):
        return data
    if info.file_size > _SETTINGS_MAX:
        return data
    settings = zin.read(info)
    fixed = _PRINT_METHOD.sub(rb"\g<1>0\g<3>", settings)
    if fixed == settings:
        return data
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        for m in zin.infolist():
            zout.writestr(m, fixed if m.filename == "settings.xml" else zin.read(m))
    return buf.getvalue()


def render_copy(data: bytes, fmt: str = "hwpx") -> bytes:
    """프로그램에 넘길 사본 — hwpx = 한 쪽씩 찍기(one_per_sheet), docx = 바깥을 부르지 않게 한 사본(docx_harden.strip_external — 읽을 수 없는
    멤버가 있으면 ValueError, 원본을 그대로 넘기지 않음). 사용자 문서·다운로드 바이트는 그대로."""
    if fmt == "docx":
        from app import docx_harden
        return docx_harden.strip_external(data)
    return one_per_sheet(data)


def export_pdf(data: bytes, limit: int | None = None, fmt: str = "hwpx") -> Path:
    """문서 바이트 → PDF 경로(hwpx = 한글, docx = Word). 출력용 사본(render_copy)을 찍고 그 바이트의 SHA-1 로 캐시 — 같은 바이트는 다시
    찍지 않는다(모아 찍기 문서는 원본 바이트 이름으로 남은 옛 모아 찍기 PDF 와 이름이 갈린다)."""
    out = render_dir()
    out.mkdir(parents=True, exist_ok=True)
    data = render_copy(data, fmt)
    pdf = out / f"{sha(data)}.pdf"
    with _once(pdf):
        return _export_pdf(data, limit, out, pdf, fmt)


def _run(src, part, limit, fmt, doc_fmt):
    """풀에 맡긴다 — 한글은 예전 호출 그대로(인자 넷), Word 는 app 을 붙여."""
    if doc_fmt == "hwpx":
        return EXPORTER.run(src, part, limit) if fmt == "PDF" else EXPORTER.run(src, part, limit, fmt=fmt)
    return EXPORTER.run(src, part, limit, fmt, app=APPS[doc_fmt])


def _export_pdf(data, limit, out, pdf, fmt="hwpx"):
    if pdf.exists() and pdf.stat().st_size:
        return pdf
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        src, part = Path(tmp) / f"doc.{fmt}", Path(tmp) / "doc.pdf"
        src.write_bytes(data)
        _run(src.resolve(), part.resolve(), limit or export_limit(len(data)), "PDF", fmt)
        if not part.exists() or not part.stat().st_size:
            raise RuntimeError("PDF 가 만들어지지 않음")
        part.replace(pdf)
    return pdf


def resave(data: bytes, fmt: str = "hwpx", limit: int | None = None) -> bytes:
    """그 형식의 프로그램이 문서를 열어 같은 형식으로 다시 저장한 바이트 — hwpx = 한글(resave_hwpx), docx = Word(바깥을 뗀 사본을 열어 DOCX 로,
    캐시 {사본 sha}.resave.docx). 내보낸 파일을 그 프로그램이 받아들이는지 본다."""
    if fmt != "docx":
        return resave_hwpx(data, limit)
    out = render_dir()
    out.mkdir(parents=True, exist_ok=True)
    data = render_copy(data, "docx")
    done = out / f"{sha(data)}.resave.docx"
    with _once(done):
        return _resave(data, limit, out, done, "docx")


def resave_hwpx(data: bytes, limit: int | None = None) -> bytes:
    """한글이 hwpx 바이트를 열어 HWPX 로 다시 저장한 바이트(캐시 {sha}.resave.hwpx) — 내보낸 파일을 한글이 받아들이는지
    (칸 없는 hp:tr 처럼 열기·PDF 는 되는데 저장에서 죽는 구조가 있다 — references/HWPX_포맷.md)."""
    out = render_dir()
    out.mkdir(parents=True, exist_ok=True)
    done = out / f"{sha(data)}.resave.hwpx"
    with _once(done):
        return _resave(data, limit, out, done, "hwpx")


def hwp_to_hwpx(data: bytes, limit: int | None = None) -> bytes:
    """한글이 hwp(바이너리) 바이트를 열어 HWPX 로 저장한 바이트(캐시 {sha}.from-hwp.hwpx) — 올린 hwp 를 hwpx 작업으로 받는 길(spec_작업 ② §1).
    한글이 없으면(available) 부르는 쪽이 막는다. 시간 한도·실패는 PDF 출력과 같다(TimeoutError·RuntimeError)."""
    out = render_dir()
    out.mkdir(parents=True, exist_ok=True)
    done = out / f"{sha(data)}.from-hwp.hwpx"
    with _once(done):
        if done.exists() and done.stat().st_size:
            return done.read_bytes()
        with tempfile.TemporaryDirectory(dir=out) as tmp:
            src, part = Path(tmp) / "doc.hwp", Path(tmp) / "doc.hwpx"
            src.write_bytes(data)
            EXPORTER.run(src.resolve(), part.resolve(), limit or export_limit(len(data)), fmt="HWPX")
            if not part.exists() or not part.stat().st_size:
                raise RuntimeError("한글이 HWPX 를 만들지 않음")
            part.replace(done)
        return done.read_bytes()


def _resave(data, limit, out, done, fmt):
    if done.exists() and done.stat().st_size:
        return done.read_bytes()
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        src, part = Path(tmp) / f"doc.{fmt}", Path(tmp) / f"again.{fmt}"
        src.write_bytes(data)
        _run(src.resolve(), part.resolve(), limit or export_limit(len(data)), fmt.upper(), fmt)
        if not part.exists() or not part.stat().st_size:
            raise RuntimeError(f"{app_name(fmt)}{'이' if fmt == 'hwpx' else '가'} {fmt.upper()} 를 만들지 않음")
        part.replace(done)
    return done.read_bytes()
