"""문서 라이브러리 서버(spec_양식작성 ② §2) — 자료 문서(hwp · hwpx · docx · pdf · ppt · pptx)를 보관 · 관리하고, 고른 문서에서 특정 기관 · 특정 연구의 내용만 뽑아 MD 로 만든다(「자료 추출」).

8114(app/)와 **따로 선 서버**다(포트 8121 — env NFM_DOCLIB_PORT · 띄우개 tools/start_doclib.ps1). 2026-11-24 사용자 "이 문서 관리 라이브러리는 별도 서버에서 관리해도 될거 같은데? … 자료추출도 같이 좀분리하고".
- 이 묶음은 `app.server` · `app.*_api` · `app.works` 를 가져오지 않는다 — 8114 가 꺼져 있어도 돈다. `app/` 에서 빌려 쓰는 것은 한글 · Word · PowerPoint 의 PDF 출력(`app.pdf_render` — 순수 모듈) 하나다.
- 8114 쪽은 `app/doclib_client.py`(HTTP 로만 묻는다)로 이 서버를 읽는다 — 이 서버의 파일 · 함수를 가져오지 않는다.
- 저장소 = `%LOCALAPPDATA%\\NewFileManager\\doclib`(env NFM_DOCLIB) — `store.py`."""
