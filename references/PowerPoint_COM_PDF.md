# PowerPoint COM 으로 PDF 찍기 (ppt · pptx)

2026-11-26 문서 라이브러리가 ppt · pptx 를 자료 문서로 받으면서 이 PC(Windows 11 · Microsoft 365 PowerPoint)에서 확인한 것. 쓰는 곳 = `app/pdf_render.py` 의 자식 스크립트(`app == "ppt"`).

## 확인한 동작

- ProgID = `PowerPoint.Application`(등록 여부는 `HKCR\PowerPoint.Application\CLSID`). 프로세스 이름 `POWERPNT.EXE`.
- **인스턴스는 하나뿐이다** — `DispatchEx` 도 새 PowerPoint 를 띄우지 않고 이미 떠 있는 것(사람이 연 PowerPoint · 다른 프로세스가 자동화로 띄운 것 포함)에 붙는다(실측 — 띄운 뒤 새 `POWERPNT.EXE` 번호가 없다). 그래서:
  - 자동화 쪽에서 `Quit()` 하면 사람이 쓰던 PowerPoint 까지 닫을 수 있다 — 제가 띄웠을 때(띄우기 전후의 `POWERPNT.EXE` 번호가 늘었을 때)이고 `Presentations.Count == 0` 일 때만 닫는다.
  - 시간 초과로 죽일 프로세스 번호도 「띄우기 전후에 새로 생긴 것」 만이다(붙었으면 빈 목록 — 사람의 PowerPoint 를 죽이지 않는다).
  - **계속 띄워 두지 않는다** — 띄워 둔 동안 사람이 PowerPoint 를 열면 그 인스턴스에 들어간다. 작업마다 띄우고 놓는다(작업 하나 ≈ 7초 · 띄우는 시간 포함).
- **`Quit()` 해도 다른 COM 클라이언트가 참조를 쥐고 있으면 프로세스가 남는다**(실측): 같은 프로세스의 남은 변수(`Application` · `Presentation` 객체)도 그렇고, 참조를 쥔 채 죽은 프로세스의 몫도 Windows 가 정리할 때까지(몇 분) 남는다 —
  죽인 서버가 띄운 PowerPoint 는 `/AUTOMATION -Embedding` 으로 홀로 남았다(열린 프레젠테이션 0 을 확인하고 끔). 그래서 Quit 전에 쥔 참조를 모두 놓는다(`a = d = None`).
- **창을 감출 수 없다**(알려진 동작 — 이 PC 에서 따로 재지 않음) — `Application.Visible = False` 는 오류(「Hiding the application window is not allowed」). 대신 `Presentations.Open(FileName, ReadOnly, Untitled, WithWindow)` 의 `WithWindow = msoFalse(0)` 로 창 없이 연다.
  자동화로 띄운 PowerPoint 는 창 없이 연 프레젠테이션만 있으면 화면에 나오지 않는다.
- 여는 인자: `Presentations.Open(path, -1, 0, 0)` = 읽기 전용(msoTrue -1) · 제목 있음 · 창 없음. 매크로는 `Application.AutomationSecurity = 3`(msoAutomationSecurityForceDisable) · 경고는 `DisplayAlerts = 1`(ppAlertsNone).
- PDF: `Presentation.SaveAs(pdf, 32)`(ppSaveAsPDF) — 슬라이드 하나가 한 쪽 · 글은 텍스트로 남아 PyMuPDF 로 읽힌다. 숨긴 슬라이드는 이 방식의 기본으로 빠진다고 알려져 있다(재지 않음 — 넣으려면 `ExportAsFixedFormat` 의 `PrintHiddenSlides`).
- 옛 바이너리 `.ppt` 도 같은 `Open` 으로 열린다 — 확장자는 실제 형식대로 두고 넘긴다(.ppt 를 .pptx 이름으로 넘기지 않는다).
- 잰 값: 3장짜리 pptx · ppt 가 각각 약 4초(PowerPoint 를 처음 띄우는 시간 포함). 자식이 stdin 을 닫고 끝나면 몇 초 뒤 `POWERPNT.EXE` 가 사라진다.

## 하드닝

- pptx 는 OOXML 이라 Word 와 같은 바깥 관계(TargetMode="External" · UNC · URL 대상의 연결 그림 · 연결 OLE · 동영상)가 있을 수 있다 — `docx_harden.strip_external` 의 관계 떼기는 OOXML 공통이라 렌더 사본에 그대로 쓴다(Word 전용 처리 — settings · 필드 — 는 Word 이름공간일 때만 돈다).
- 옛 `.ppt` 는 바이너리라 고칠 수 없다 — 그대로 넘긴다.
