"""한글 PDF 출력용 사본 — 2쪽 모아 찍기(PrintMethod)를 끄고 한 쪽씩 찍기(spec_hwpx_웹편집 ② §5)."""
import io
import zipfile
from pathlib import Path

from app import pdf_render

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
PLAN = SAMPLES / "연구개발계획서_양식.hwpx"     # settings.xml PrintMethod = 4(2쪽 모아 찍기)
SURVEY = SAMPLES / "기술수요조사서.hwpx"       # settings.xml 에 PrintInfo 없음
METHOD = b'<config:config-item name="PrintMethod" type="short">'


def _members(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    return [(i.filename, i.compress_type, z.read(i)) for i in z.infolist()]


def test_one_per_sheet_turns_off_two_up():
    data = PLAN.read_bytes()
    assert METHOD + b"4<" in zipfile.ZipFile(io.BytesIO(data)).read("settings.xml")
    out = pdf_render.one_per_sheet(data)
    before, after = _members(data), _members(out)
    assert [m[:2] for m in before] == [m[:2] for m in after]           # 멤버 순서·압축 방식 그대로
    assert after[0][0] == "mimetype" and after[0][1] == zipfile.ZIP_STORED
    for (name, _, a), (_, _, b) in zip(before, after):
        if name == "settings.xml":
            assert METHOD + b"0<" in b and b.replace(METHOD + b"0<", METHOD + b"4<") == a
        else:
            assert a == b
    assert pdf_render.one_per_sheet(out) == out                        # 이미 0 이면 그대로


def test_one_per_sheet_leaves_other_bytes():
    survey = SURVEY.read_bytes()
    assert pdf_render.one_per_sheet(survey) is survey
    assert pdf_render.one_per_sheet(b"not a zip") == b"not a zip"


def test_export_pdf_prints_and_caches_the_copy(monkeypatch):
    """한글에 넘기는 파일 = 한 쪽씩 사본, 캐시 이름 = 그 사본의 해시(원본 이름의 옛 모아 찍기 PDF 를 다시 쓰지 않음)."""
    seen = []

    class Fake:
        def run(self, src, out, limit, fmt="PDF"):
            seen.append(Path(src).read_bytes())
            Path(out).write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(pdf_render, "EXPORTER", Fake())
    data = PLAN.read_bytes()
    copy = pdf_render.one_per_sheet(data)
    old = pdf_render.render_dir() / f"{pdf_render.sha(data)}.pdf"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"%PDF-1.4 old two-up")
    pdf = pdf_render.export_pdf(data)
    assert seen == [copy] and pdf.name == f"{pdf_render.sha(copy)}.pdf" and pdf != old
    assert pdf_render.export_pdf(data) == pdf and len(seen) == 1       # 같은 바이트는 캐시


# ---- Word(docx) 출력 — 자식 스크립트를 가짜 win32com 으로(FileMergeManager tests/test_render_hardening.py 의 COM 흉내) ------------------

import json  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import types  # noqa: E402

from app import docx_harden  # noqa: E402

DOCX = SAMPLES / "기술수요조사서.docx"


class _Com:
    """COM 객체 흉내 — 속성 대입을 log 에 차례대로 적는다."""

    def __init__(self, log):
        object.__setattr__(self, "log", log)

    def __setattr__(self, k, v):
        self.log.append(("set", k, v))
        object.__setattr__(self, k, v)


class _Doc(_Com):
    def __init__(self, log, fail=False):
        super().__init__(log)
        object.__setattr__(self, "fail", fail)

    def SaveAs2(self, path, FileFormat=None):
        self.log.append(("SaveAs2", path, FileFormat))
        if self.fail:
            raise RuntimeError("save failed")

    def Close(self, save=None):
        self.log.append(("Close", save))


class _Documents(_Com):
    def __init__(self, log, fail=False):
        super().__init__(log)
        object.__setattr__(self, "fail", fail)

    def Open(self, *args, **kw):
        self.log.append(("Open", args, kw))
        return _Doc(self.log, self.fail)


class _Word(_Com):
    def __init__(self, log, fail=False):
        super().__init__(log)
        object.__setattr__(self, "Documents", _Documents(log, fail))

    def Quit(self):
        self.log.append(("Quit",))


class _Hwp(_Com):
    def __init__(self, log):
        super().__init__(log)
        win = _Com(log)
        object.__setattr__(self, "XHwpWindows", types.SimpleNamespace(Item=lambda i: win))

    def RegisterModule(self, *a):
        self.log.append(("RegisterModule",) + a)

    def Open(self, *a):
        self.log.append(("Open",) + a)
        return True

    def SaveAs(self, *a):
        self.log.append(("SaveAs",) + a)
        return True

    def Clear(self, *a):
        self.log.append(("Clear",) + a)

    def Quit(self):
        self.log.append(("Quit",))


class _Pres(_Com):
    def __init__(self, log, fail=False):
        super().__init__(log)
        object.__setattr__(self, "fail", fail)

    def SaveAs(self, path, kind=None):
        self.log.append(("SaveAs", path, kind))
        if self.fail:
            raise RuntimeError("save failed")

    def Close(self):
        self.log.append(("Close",))


class _Presentations(_Com):
    def __init__(self, log, fail=False, count=0):
        super().__init__(log)
        object.__setattr__(self, "fail", fail)
        object.__setattr__(self, "Count", count)

    def Open(self, *args, **kw):
        self.log.append(("Open", args, kw))
        return _Pres(self.log, self.fail)


class _PowerPoint(_Com):
    def __init__(self, log, fail=False, count=0):
        super().__init__(log)
        object.__setattr__(self, "Presentations", _Presentations(log, fail, count))

    def Quit(self):
        self.log.append(("Quit",))


def _run_child(monkeypatch, capsys, jobs, fail=False, tasks="", open_count=0):
    """_CHILD 를 가짜 win32com 으로 이 프로세스 안에서 돌린다 -> (COM 기록, 자식이 낸 JSON 줄).
    tasks = tasklist 가 띄운 뒤에 보일 줄(새 프로세스 번호 — 이 자식이 띄운 것) · open_count = PowerPoint 에 이미 열린 프레젠테이션 수."""
    log = []
    client = types.ModuleType("win32com.client")
    client.Dispatch = lambda prog: (log.append(("Dispatch", prog)), _Hwp(log))[1]
    client.DispatchEx = lambda prog: (log.append(("DispatchEx", prog)), _PowerPoint(log, fail, open_count) if prog == "PowerPoint.Application" else _Word(log, fail))[1]
    pkg = types.ModuleType("win32com")
    pkg.client = client
    monkeypatch.setitem(sys.modules, "win32com", pkg)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    calls = []

    def fake_run(*a, **k):  # tasklist 없이 — 띄우기 전(홀수 번째)은 빈 목록, 띄운 뒤(짝수 번째)는 tasks
        calls.append(a)
        return types.SimpleNamespace(stdout="" if len(calls) % 2 else tasks)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(json.dumps(j) + "\n" for j in jobs)))
    exec(pdf_render._CHILD, {"__name__": "_child"})  # noqa: S102 — 모듈 안의 고정 스크립트
    out = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.strip()]
    return log, out


def test_word_disables_macros_and_dialogs_before_open(monkeypatch, capsys):
    log, out = _run_child(monkeypatch, capsys, [{"src": "C:\\t\\doc.docx", "pdf": "C:\\t\\doc.pdf", "format": "PDF", "app": "word"},
                                                {"src": "C:\\t\\doc.docx", "pdf": "C:\\t\\again.docx", "format": "DOCX", "app": "word"}])
    assert out == [{"pids": []}, {"ok": True}, {"ok": True}]       # Word 는 한 번만 띄운다
    assert sum(x[0] == "DispatchEx" for x in log) == 1 and ("DispatchEx", "Word.Application") in log
    opened = next(i for i, x in enumerate(log) if x[0] == "Open")
    before = {x[1]: x[2] for x in log[:opened] if x[0] == "set"}
    assert before.get("AutomationSecurity") == 3 and before.get("DisplayAlerts") == 0 and before.get("Visible") is False
    args, kw = log[opened][1], log[opened][2]
    assert args == ("C:\\t\\doc.docx",)
    assert kw["ConfirmConversions"] is False and kw["ReadOnly"] is True and kw["AddToRecentFiles"] is False
    assert ("SaveAs2", "C:\\t\\doc.pdf", 17) in log and ("SaveAs2", "C:\\t\\again.docx", 16) in log
    assert log.index(("Close", False)) > log.index(("SaveAs2", "C:\\t\\doc.pdf", 17))
    assert log[-1] == ("Quit",)


def test_word_closes_document_when_save_fails(monkeypatch, capsys):
    log, out = _run_child(monkeypatch, capsys, [{"src": "a.docx", "pdf": "a.pdf", "format": "PDF", "app": "word"}], fail=True)
    assert out[-1]["ok"] is False and "save failed" in out[-1]["error"]
    assert ("Close", False) in log and log[-1] == ("Quit",)


def test_hangul_job_without_app_keeps_forceopen(monkeypatch, capsys):
    """옛 작업 줄(app 없음)은 한글 — hwpx 경로는 그대로."""
    log, out = _run_child(monkeypatch, capsys, [{"src": "a.hwpx", "pdf": "a.pdf", "format": "PDF"},
                                                {"src": "a.hwpx", "pdf": "b.hwpx", "format": "HWPX", "app": "hwp"}])
    assert out == [{"pids": []}, {"ok": True}, {"ok": True}]
    assert ("Dispatch", "HWPFrame.HwpObject") in log and not any(x[0] == "DispatchEx" for x in log)
    assert ("Open", "a.hwpx", "HWPX", "forceopen:true") in log and ("SaveAs", "a.pdf", "PDF", "") in log
    assert ("SaveAs", "b.hwpx", "HWPX", "") in log


def test_powerpoint_prints_pdf_without_window_and_lets_go_after_each_job(monkeypatch, capsys):
    """ppt · pptx = PowerPoint(2026-11-26 — 문서 라이브러리의 자료 문서). 창 없이 읽기 전용으로 열어 PDF(32)로 · 매크로 끔 ·
    작업마다 놓는다 — 이 자식이 띄웠으면 닫고 그 번호를 부모가 잊게 알린다(계속 띄워 두면 사람이 연 프레젠테이션이 그 인스턴스에 들어온다)."""
    mine = '"POWERPNT.EXE","4321","Console","1","100 K"\n'
    log, out = _run_child(monkeypatch, capsys, [{"src": "C:\\t\\doc.pptx", "pdf": "C:\\t\\doc.pdf", "format": "PDF", "app": "ppt"},
                                                {"src": "C:\\t\\doc.ppt", "pdf": "C:\\t\\old.pdf", "format": "PDF", "app": "ppt"}], tasks=mine)
    assert out == [{"pids": [4321]}, {"gone": [4321]}, {"ok": True}] * 2         # 띄운 번호를 알리고(시간 초과면 부모가 죽임) · 닫으면 잊게 알린다
    assert log.count(("DispatchEx", "PowerPoint.Application")) == 2 and not any(x[0] == "Dispatch" for x in log) and log.count(("Quit",)) == 2
    opened = next(i for i, x in enumerate(log) if x[0] == "Open")
    before = {x[1]: x[2] for x in log[:opened] if x[0] == "set"}
    assert before.get("AutomationSecurity") == 3 and before.get("DisplayAlerts") == 1 and "Visible" not in before   # PowerPoint 는 창을 감출 수 없다 — 열 때 WithWindow 없이
    assert log[opened][1] == ("C:\\t\\doc.pptx", -1, 0, 0)
    assert ("SaveAs", "C:\\t\\doc.pdf", 32) in log and ("SaveAs", "C:\\t\\old.pdf", 32) in log and log.count(("Close",)) == 2
    assert log.index(("Quit",)) > log.index(("Close",))


def test_powerpoint_leaves_a_powerpoint_it_did_not_start(monkeypatch, capsys):
    """사람이 연 PowerPoint 에 붙었으면(새 프로세스 없음) 닫지 않는다 · 열린 프레젠테이션이 있어도 닫지 않는다 · PDF 말고는 거절 · 실패해도 문서는 닫고 놓는다."""
    log, out = _run_child(monkeypatch, capsys, [{"src": "a.pptx", "pdf": "a.pdf", "format": "PDF", "app": "ppt"},
                                                {"src": "a.pptx", "pdf": "a.docx", "format": "DOCX", "app": "ppt"}])
    assert out[:3] == [{"pids": []}, {"ok": True}, {"pids": []}] and out[3]["ok"] is False and "PDF" in out[3]["error"]
    assert ("Quit",) not in log
    mine = '"POWERPNT.EXE","4321","Console","1","100 K"\n'
    log, out = _run_child(monkeypatch, capsys, [{"src": "a.pptx", "pdf": "a.pdf", "format": "PDF", "app": "ppt"}], tasks=mine, open_count=1)
    assert out == [{"pids": [4321]}, {"ok": True}] and ("Quit",) not in log
    log, out = _run_child(monkeypatch, capsys, [{"src": "a.pptx", "pdf": "a.pdf", "format": "PDF", "app": "ppt"}], fail=True, tasks=mine)
    assert out[:2] == [{"pids": [4321]}, {"gone": [4321]}] and out[-1]["ok"] is False and "save failed" in out[-1]["error"]
    assert ("Close",) in log and log[-1] == ("Quit",)


def test_exporter_forgets_pids_the_child_closed(monkeypatch):
    """자식이 「gone」 으로 알린 번호는 부모가 잊는다 — 시간 초과 때 그 번호(다른 프로세스가 다시 받았을 수 있다)를 죽이지 않게."""
    ex = pdf_render.Exporter()
    ex.proc = types.SimpleNamespace(poll=lambda: None, stdin=io.StringIO())
    ex.lines = __import__("queue").Queue()
    for m in ({"pids": [4321]}, {"gone": [4321]}, {"ok": True}):
        ex.lines.put(json.dumps(m))
    assert ex.run("a.pptx", "a.pdf", 5, app="ppt") == "a.pdf" and ex.pids == set()


def test_pptx_copy_is_hardened_and_ppt_goes_as_is(monkeypatch):
    """pptx 렌더 사본도 바깥 관계(연결 그림 등)를 뗀다(OOXML 공통 하드닝) · ppt(옛 바이너리)는 그대로 · 출력은 PowerPoint(app ppt)."""
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="\\\\evil\\share\\a.png" TargetMode="External"/>'
            '</Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("ppt/slides/slide1.xml", '<?xml version="1.0"?><p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>')
        z.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
    data = buf.getvalue()
    copy = pdf_render.render_copy(data, "pptx")
    assert copy != data and b"evil" not in zipfile.ZipFile(io.BytesIO(copy)).read("ppt/slides/_rels/slide1.xml.rels")
    assert pdf_render.render_copy(b"\xd0\xcf\x11\xe0old", "ppt") == b"\xd0\xcf\x11\xe0old"
    fake = _FakeWord()
    monkeypatch.setattr(pdf_render, "EXPORTER", fake)
    pdf_render.export_pdf(b"\xd0\xcf\x11\xe0old", fmt="ppt")
    assert [(c["name"], c["fmt"], c["app"]) for c in fake.calls] == [("doc.ppt", "PDF", "ppt")]
    assert pdf_render.app_name("pptx") == pdf_render.app_name("ppt") == "PowerPoint"


def _with_update_fields(data):
    """settings 에 열 때 필드 갱신(w:updateFields — Word 확인 창)을 넣은 docx — 렌더 사본에서 빠져야 한다."""
    zin, buf = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for m in zin.infolist():
            raw = zin.read(m)
            if m.filename == "word/settings.xml":
                raw = raw.replace(b"</w:settings>", b'<w:updateFields w:val="true"/></w:settings>')
            z.writestr(m, raw)
    return buf.getvalue()


class _FakeWord:
    def __init__(self):
        self.calls = []

    def run(self, src, out, limit, fmt="PDF", app="hwp"):
        self.calls.append({"name": Path(src).name, "bytes": Path(src).read_bytes(), "fmt": fmt, "app": app, "limit": limit})
        Path(out).write_bytes(b"%PDF-1.4 fake" if fmt == "PDF" else b"PK-again")
        return out


def test_docx_export_pdf_prints_hardened_copy_with_word(monkeypatch):
    fake = _FakeWord()
    monkeypatch.setattr(pdf_render, "EXPORTER", fake)
    data = _with_update_fields(DOCX.read_bytes())
    copy = docx_harden.strip_external(data)
    assert copy != data and b"updateFields" not in zipfile.ZipFile(io.BytesIO(copy)).read("word/settings.xml")
    pdf = pdf_render.export_pdf(data, fmt="docx")
    assert [(c["name"], c["fmt"], c["app"]) for c in fake.calls] == [("doc.docx", "PDF", "word")]
    assert fake.calls[0]["bytes"] == copy and fake.calls[0]["limit"] == pdf_render.export_limit(len(copy))
    assert pdf.name == f"{pdf_render.sha(copy)}.pdf"
    assert pdf_render.export_pdf(data, fmt="docx") == pdf and len(fake.calls) == 1   # 같은 바이트는 캐시
    clean = DOCX.read_bytes()
    assert pdf_render.render_copy(clean, "docx") == clean                             # 고칠 것이 없으면 그대로(캐시 이름 = 원본 해시)


def test_docx_resave_uses_word_and_caches(monkeypatch):
    fake = _FakeWord()
    monkeypatch.setattr(pdf_render, "EXPORTER", fake)
    data = _with_update_fields(DOCX.read_bytes())
    copy = docx_harden.strip_external(data)
    assert pdf_render.resave(data, "docx") == b"PK-again"
    assert [(c["name"], c["fmt"], c["app"], c["bytes"] == copy) for c in fake.calls] == [("doc.docx", "DOCX", "word", True)]
    assert (pdf_render.render_dir() / f"{pdf_render.sha(copy)}.resave.docx").exists()
    assert pdf_render.resave(data, "docx") == b"PK-again" and len(fake.calls) == 1


def test_resave_hwpx_still_calls_hangul(monkeypatch):
    seen = []

    class Fake:  # 예전 시그니처(app 없음) — hwpx 길은 app 을 넘기지 않는다
        def run(self, src, out, limit, fmt="PDF"):
            seen.append((Path(src).name, fmt))
            Path(out).write_bytes(b"PK-hwpx")
    monkeypatch.setattr(pdf_render, "EXPORTER", Fake())
    assert pdf_render.resave(b"hwpx bytes") == b"PK-hwpx" == pdf_render.resave_hwpx(b"hwpx bytes")
    assert seen == [("doc.hwpx", "HWPX")]


def test_available_per_format(monkeypatch):
    assert not pdf_render.available("docx") and not pdf_render.available()   # conftest: NFM_PDF=off 면 모두 끔
    monkeypatch.delenv("NFM_PDF")
    keys = []

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    import winreg
    monkeypatch.setattr(winreg, "OpenKey", lambda root, sub: keys.append(sub) or Key())
    assert pdf_render.available("docx") and pdf_render.available("hwpx") and not pdf_render.available("odt")
    assert keys == [r"Word.Application\CLSID", r"HWPFrame.HwpObject\CLSID"]
    assert pdf_render.app_name("docx") == "Word" and pdf_render.app_name() == "한글"
