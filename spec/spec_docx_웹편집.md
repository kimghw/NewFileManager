# DOCX 웹 편집 · 무손실 왕복 · PDF 매핑 검증

HWPX 쪽 원본(같은 흐름·화면·검증 단계): [spec_hwpx_웹편집.md](spec_hwpx_웹편집.md) · 구조·서식 편집: [spec_owpml_편집.md](spec_owpml_편집.md) ·
포맷 사실(Word PDF·다시 저장·표 스타일·번호 실측 포함): [references/DOCX_포맷.md](../references/DOCX_포맷.md)

## ① 질의·요청 히스토리

- 2026-11-08 요청: "현재 hwpx 로만 되어 있는데, docx 도 동일한 작업을 수행할 수 있도록 업데이트 해줘." → hwpx 와 같은 흐름(올리기 → 웹 편집 →
  저장 → 가져오기 검증·출력파일 검증)을 docx 로. 한글 대신 **Word** 로 PDF·다시 저장.
  - 세션 협의(newfilemanager-20·24·5a, 모두 겹침 없음): 글꼴 표 계약(`{언어: {글꼴: {type, subst}}}`·서식 요약 `font`·`fontLatin`…·`script`),
    `_edit` 의 OWPML 검사·`hwpx_struct.snapshot/top_host`·`restore.py` 는 hwpx 전용이니 형식 분기, Word 로 비신뢰 docx 를 열 땐 FileMergeManager 의
    렌더 하드닝(strip_external)을 같이 옮길 것, `pdf_map` 은 블록 스키마만 봄(고칠 일 생기면 5a 에 먼저 알림).
  - 실물 검증에서 나온 협의: `pdf_map` 두 곳(가로 쪽 머리말 띠 `BAND × max(w, h)`, 짧은 자동 번호 헤딩 = label + 글 키 전체 일치) — 6e 제안, **5a 가 고침**,
    이어 5a 가 HAZID 「문단 같은 쪽」(되풀이 셈·표 머리 행 되풀이)·AIP 서식(맨 위 줄이 블록에 없는 글상자 라벨)도 고침. 모듈 전역 lxml 파서를 여러 검증 스레드가
    나눠 쓰던 결함(docx 1.8 MB 가 거짓 구문 오류) — docx 쪽은 6e, `hwpx_doc`·`owpml_check` 는 **24 가 고침**. app.js `paraLook` 의 docx 내어쓰기 한 줄은
    장평 작업 중인 **20 이 넣음**.
- 2026-11-08 사용자 「문서 검토 한다」 → 서브에이전트 검토 19건(코드와 다른 ② 4건 — 선 종류·출력 실패 판정·「한글」 문구·다시 저장 사본, 시간 숫자 불일치,
  Word 사실의 자리 등) 반영: ② 고침, Word 사실은 references 로 옮기고 링크, verify 문구 4곳 형식별로.

## ② 확정 사양

### 1. 가져온 것·형식 분기

- FileMergeManager 에서 복사 후 보강: `app/docx_doc.py`(블록 트리·편집·저장 어댑터 — hwpx 와 같은 블록 스키마), `docx_format.py`(서식 요약·서식 적용),
  `docx_layout.py`(구역 용지·칸 크기), 시험 `tests/test_docx_doc.py`·`test_docx_format.py`, 예제 `samples/기술수요조사서.docx`. 원칙은 hwpx 와 같다 —
  무수정 저장 = 원본 바이트, 고친 XML 부분만 다시 쓰기, 다른 멤버는 원래 바이트·ZipInfo. 다시 쓸 때 원래 XML 선언·뿌리 뒤 공백·Word 식 16진 문자 참조(`&#xA;`)를 지킨다.
- 렌더 하드닝 `app/docx_harden.py` = FileMergeManager `render_anchors.strip_external`(바깥 관계·연결 필드·VML 주소·편지 병합·열 때 필드 갱신을 렌더 사본에서 뗌).
- 형식은 파일 확장자로 정한다(`.hwpx` → HwpxDoc, `.docx` → DocxDoc — `server.FORMATS`·`verify.KIT`). 서버·검증·화면은 형식마다 갈리는 곳만 분기하고
  API·블록 스키마는 같다. `GET /api/docs/{id}` 에 `format`(hwpx|docx), `GET /api/status` 에 `word`.
- lxml 파서는 스레드마다 하나(`docx_doc._parser()`) — 검증 단계가 같은 바이트를 동시에 연다.

### 2. 웹 보기 — 서식 요약 보강(읽기만)

hwpx 웹 보기가 쓰는 키를 docx 도 낸다(`docx_format._summary`, 런 `runs[].format` 도):
- `script` = `sup`|`sub`(`w:vertAlign`, 상속). `font` = 동아시아 글꼴(`w:rFonts eastAsia`, 테마 참조면 테마 글꼴 — 없으면 `ascii`), `fontLatin` = `ascii`(없으면 `hAnsi`)
  — font 와 다를 때만. `wordBreak` = `w:wordWrap` 이 꺼져 있으면(val 0, 상속 포함) `char`, 그 밖은 `word`.
- **상속 차례**(Word 사실은 [references](../references/DOCX_포맷.md) 「번호 수준의 문단 속성」·「표 스타일」):
  - 문단 속성: 직접 → 번호 수준 pPr(`w:num lvlOverride/lvl`, 없으면 abstractNum 의 같은 ilvl) → [가] → docDefaults.
  - 글자 속성: 직접 → 글자 스타일 체인 → [가] → docDefaults.
  - [가] = 문단이 기본 아닌 문단 스타일을 골랐으면 그 스타일 체인(basedOn 으로 기본 스타일에서 물려받은 값 포함 — 미실측) → 표 스타일, 아니면 표 스타일 → 문단 스타일 체인.
  - 표 스타일(칸 안 문단만, `cell_ctx`) = 조건부 서식(겹침 차례, 이기는 것 먼저) → 표 전체. 걸리는 조건부 서식은 칸·문단 `w:cnfStyle`(속성, 없으면 val 비트)을
    먼저 믿고, 없으면 칸 자리 + `tblLook`·`tblStyleRow/ColBandSize` 로 센다. 모서리 칸은 그 행·열 서식도 건다.
- 칸 음영(`fill`) = 칸 직접 `w:shd` → 표 스타일 조건부·전체 `tcPr/shd`. 색 없는(auto) 글은 칸 음영이 어두우면 흰색(`docx_doc._dark` — 문턱은 references 「자동 글자색」).
- **목차 하이퍼링크**: `toc N` 문단 안 Hyperlink 글자 스타일은 빼고 본다(references 「목차 하이퍼링크」).
- **번호 라벨**: references 「번호 이어 세기」대로(`DocxDoc._list` — 같은 abstractNum 이면 이어 세고 startOverride 는 그 w:num 첫 문단의 수준만).
- **내어쓰기 뜻**: 서식 요약은 Word 그대로(`indentLeftMm` = w:left = 둘째 줄부터, `firstLineMm` = −hanging). 화면은 첫 줄을 left − hanging 에 그리고(app.js
  `paraLook`, docx 분기), 레터 대조는 hwpx 뜻(첫 줄 = 왼쪽 여백)으로 바꿔 견준다(`verify.hang_as_hwpx`).
- **표 선**: 칸 `bf` = 칸 선 묶음 키, 표 블록 `borderFills` = {키: {t,r,b,l: {type, widthMm, color} | None}}(hwpx 와 같은 모양). 칸 `w:tcBorders` →
  표 `w:tblBorders`(바깥 칸 = top/left/bottom/right, 안쪽 = insideH/insideV) → 표 스타일 체인의 `tblPr/tblBorders`. 종류 single·thick→SOLID,
  double·triple·thinThickSmallGap·thickThinSmallGap→DOUBLE_SLIM, dashed·dashSmallGap→DASH, dotted→DOT, dotDash→DASH_DOT, dotDotDash→DASH_DOT_DOT,
  nil·none→없음, 그 밖은 SOLID. 굵기 `w:sz` = 1/8 pt, `auto` 색 = 검정. 조건부 서식의 선(`tblStylePr/tcPr/tcBorders`)은 안 본다.
- **글꼴 표** `DocxDoc.font_table(blocks)` = {HANGUL·HANJA·JAPANESE: font, LATIN: fontLatin(없으면 font)} — 블록 서식에 쓰인 글꼴만, `type` 은 늘 TTF,
  `subst` = `fontTable.xml` `w:altName`, 없으면 문서 기본 글꼴(기본 문단 스타일 — 이 PC 에 없는 글꼴을 Word 가 대신 찍는 자리). 웹 글꼴 계획(`app/fonts.py`)은 hwpx 와 같은 길.
- **매핑 전 추정 쪽**: 최상위 블록 `pageStart` = 그 블록 첫 문단의 `pageBreakBefore`(스타일 체인 포함), 또는 글보다 앞선 Word 쪽 나눔 캐시 `w:lastRenderedPageBreak`·
  쪽 나눔 `w:br w:type="page"`, 또는 앞 문단이 글 뒤 쪽 나눔으로 끝남. 문단·표 행 가운데의 나눔은 무시. 매핑이 오면 PDF 맨 위 줄로 다시 나눈다(`pdf_map.paginate`).

### 3. 편집 (hwpx 와 같은 API — `app/docx_struct.py` 믹스인, `app/docx_restore.py`)

- 글 고치기·되돌리기: `set_text`(런마다 `redistribute`), 글이 원래대로면 **원본 문단 XML 복원**(`docx_restore` — 문단 속성·자식을 원본 사본으로, 그림 `w:drawing`
  자리에는 지금 요소를 그대로 둬 그림 블록 id 유지; 그림 수가 다르면 포기), 고친 문단이 더 없고 다시 쓴 바이트가 원본 부분과 같으면 「고침」 표시를 뗀다
  → 모두 되돌리면 다운로드 = 원본 바이트.
- 글 위치(offset) = 블록 글 단위(탭·강제 줄 바꿈 `w:br` = 한 글자, SEQ 필드 = 그 표시 번호).
- **문단 나누기** `split_para`: offset 자리에서 런(`w:t` 도 둘로)과 그것을 감싼 하이퍼링크를 같은 속성으로 나눠 뒤쪽을 바로 뒤 새 `w:p` 에(문단 속성 사본 —
  `w14:paraId`·`textId` 는 빼고, 번호 `numPr` 은 따라감 = Word 의 Enter). 구역 나누기 `pPr/sectPr` 는 **뒤 문단으로 옮긴다**(docx 는 구역 마지막 문단에 있음 —
  hwpx 와 반대). 새 문단에 글 런이 없으면 끊은 런 글자 모양의 빈 `w:t` 런. 거절: 끊는 자리가 복합 필드(begin~end)·`w:fldSimple`·`w:sdt`·변경 추적(`w:ins`·`w:del`…)·
  `w:customXml`·`w:smartTag` 안.
- **문단 합치기** `merge_paras`: 바로 다음 형제 `w:p`(사이의 책갈피·주석 범위 표지는 건너뜀)의 `pPr` 밖 자식을 앞 문단 끝으로, 뒤 문단 삭제, 같은 `rPr` 의 이웃 글 런 합치기.
  뒤 문단의 구역 나누기는 앞 문단으로 옮긴다. 거절: 다음 형제가 문단이 아님·없음, 앞 문단에 구역 나누기(구역을 없앰), 어느 쪽이든 그림·개체.
- **글자 모양** `format_chars`: 범위 경계에서 런을 나누고 범위 안 글 런의 `rPr` 에 직접 서식(`docx_format._set_chars` — 스키마 자식 순서). 켜고 끄기(toggle)는
  범위 런의 유효 값(스타일·표 스타일 상속 포함)이 모두 켜져 있으면 끔. 빈 문단은 그 문단의 런(rPr 만 든 빈 런 포함), 런이 하나도 없으면 문단 끝 표식 `pPr/rPr`.
  끝나면 이웃 같은 런 합치기.
- **문단 모양** `format_para`: `derive_format` + `apply_format(keep_numbering=True, runs={})` — `jc`·`ind`(글자 단위 `*Chars` 는 0 으로 덮음)·`spacing`. 번호·구역 나누기·런 서식은 그대로.
- **표 행·열** `table_edit`: hwpx 와 같은 op 를 어댑터의 `clone_rows`·`delete_rows`·`clone_cols`·`delete_cols` 로(새 칸은 비움, 열 넣기·지우기는 표 폭 그대로).
- **실행 취소**: 직전 상태 묶음(저장 바이트·고친 부분·새 바이너리·블록 id 자리표)을 원본 기준으로 다시 연다(`docx_struct.snapshot/restore`).
- **편집마다 검사**: OWPML 대신 `app/docx_check.py`(OOXML 참조 규칙 — 관계 r:id·대상·콘텐츠 형식·스타일·번호 정의·표 칸 끝 문단·빈 행·세로 병합·gridSpan·
  pPr/rPr 자리·자식 순서·docPr·paraId 중복)를 닿은 최상위 블록 + 패키지 규칙으로 돌려 원본 기준선에 없던 종류가 생기면 그 편집을 되돌리고 422.
  응답 키는 hwpx 와 같은 `owpml`(화면 이름만 「OOXML」).

### 4. 검증 (hwpx 와 같은 단계 키 — 제목만 형식별, `verify.steps(kind, fmt)`)

| 키 | docx 단계 제목 | hwpx 와 다른 점 |
|---|---|---|
| package·model | 패키지 왕복·웹 매핑 | |
| xml | XML 재직렬화 | 어댑터가 다시 쓸 수 있는 부분만(`[Content_Types].xml`·본문·본문 관계·스타일·번호 — `verify.docx_writable`), SEQ 캐시 갱신 없이. docProps·customXml 은 다시 쓰지 않으므로 안 봄 |
| owpml | **OOXML 참조 검사** | 스키마(XSD)는 없음 — 참조 규칙만, 원본 위반은 기준선 |
| pdf·render | **Word PDF 출력**·재구성 렌더 비교 | Word COM(`SaveAs2` PDF), 렌더 사본은 `strip_external`, 캐시 이름 = 사본 바이트. 모아 찍기 사본 없음 |
| map·pages | 그대로 | |
| letters·fonts | 그대로 + Word PDF 줄 다듬기 | 매핑 뒤 줄 끝 빈칸을 떼고 Symbol·Wingdings 글머리(PUA·⚫)를 웹 라벨 글자로(`verify.word_pdf_lines`). 레터 대조는 내어쓰기를 hwpx 뜻으로(§2), 번호 라벨(`list.label`)이 있는 개요 문단은 그 라벨을 레터로(`headings.levels`), 둘째 줄 종류는 강제 줄 바꿈만 `forced` |
| epackage | 수정본 패키지 | 바뀌어도 되는 멤버 = `word/`·`[Content_Types].xml` |
| eowpml | **수정본 OOXML 검사** | |
| epdf·esave | 수정본 PDF 출력·**Word 다시 저장** | 수정본도 `strip_external` 사본을 찍는다. 다시 저장도 그 사본을 열어 `SaveAs2` DOCX(FileFormat 16) → 문단 글 차례 대조(내려받는 바이트 그대로가 아님), **빈 문단은 셈에서 뺌**(Word 가 표로 끝나는 본문 뒤에 더함) |
| epages·etext | 쪽 차이 대조·수정 글 반영 | 그대로 |

- Word 가 없으면 PDF 와 그 뒤 단계는 「건너뜀」, 출력이 실패하면 PDF 단계 「실패」·뒤 단계 「건너뜀」(hwpx 와 같음). 단계 제목·설명·상태 문구의 「한글」·「HWPX」·「OWPML」은
  docx 면 「Word」·「DOCX」·「OOXML」(`verify.steps`·`pdf_render.app_name`).

### 5. 화면

- 열기는 `.hwpx`·`.docx`. 저장 단추·안내 문구는 형식별(「HWPX 저장」/「DOCX 저장」, 「한글 PDF」/「Word PDF」, 「OWPML」/「OOXML」 — app.js `APP()`·`EXT()`·`STD()`).

## ③ 구현 상태

- 2026-11-08 구현: FileMergeManager docx 어댑터·시험 복사(22 passed) → 보강(위 ②), 새 `app/docx_struct.py`·`docx_restore.py`·`docx_check.py`(포크 에이전트)·
  `docx_harden.py`(포크 에이전트), `pdf_render.py` Word 자식(`available(fmt)`·`export_pdf(…, fmt)`·`resave(…, fmt)`), server·verify·화면 형식 분기,
  `headings.py` 한 줄(번호 라벨 있는 개요 문단). 시험 `tests/test_docx_web.py` 15개·`test_docx_check.py` 12개·`test_docx_harden.py` 23개·`test_pdf_render.py` +7 —
  전체 152 passed(다른 세션 시험 포함).
- 2026-11-08 실물 Word 16(이 PC) — 서버 코드를 TestClient 로. 시간은 마지막 차례(빈 렌더 폴더 — Word 를 처음 띄우는 몫은 포함 안 될 수 있음) 기준:
  - 기술수요조사서.docx(38 KB, Letter 1쪽): 가져오기 **모든 단계 통과**(4.2s, Word PDF 3.8s) — 바이트 동일, XML 5/5, 매핑 34/34, 레터 6/6, 글꼴 513자 다름 0,
    재구성 = 원본 바이트. 편집(글·나누기·글자 모양·표 행 아래) → 출력파일 검증 3.1s: 패키지·OOXML 통과, Word PDF 2쪽, **Word 다시 저장 41/41 문단**(빈 문단 +1 뺌), 글 반영 3/3.
  - HAZID 보고서(2.6 MB, 72쪽, 그림·번호 헤딩·가로 부록 표): 가져오기 25.6s(Word PDF 17.6s) — 바이트 동일, XML 5/5, 문단 3,599개 글 동일, OOXML 0건,
    매핑 2,022/2,024(99.9%), 재구성 PDF **72쪽 모두 픽셀 동일**. 처음 대조는 쪽 나눔·레터 **실패**였다 → 고친 뒤 주의:
    쪽 나눔 못 맞춤 16 → 1쪽·문단 같은 쪽 54.2% → 99.6%(5a), 레터 237/262 → 287/287·앞 공백 170/280 → 305/305·왼쪽 여백 7/83 → 83/83·웹에 없는 번호 28 → 2,
    글꼴 색 다름 252 → 39자(0.1%). 고친 것: 번호 수준 들여쓰기, 내어쓰기 뜻, 번호 이어 세기(startOverride), 목차 하이퍼링크, Word PDF 줄 끝 빈칸·PUA 글머리, 번호 헤딩 레터.
    편집 뒤 출력파일 검증 19.6s: Word 다시 저장 2,309/2,309 문단, 쪽 차이 = 고친 쪽 + 밀림(주의).
  - AIP 신청서식(1.8 MB, 4쪽, 표 스타일 머리 행·첫 열): 처음 OOXML 단계가 거짓 구문 오류(파서 스레드 결함 — 고침), 글꼴 굵게·색 27자 다름 → 표 스타일 조건부 서식·
    자동 글자색·모서리 칸 규칙으로 **글꼴 다름 0**, 레터 2/24 → **24/24**(⚫ 글머리), 쪽 나눔 못 맞춤 2 → 0·문단 같은 쪽 100%(5a — 글상자 라벨). AIP 서식 5개·
    New Statement(7쪽) 모두 글꼴 대조 통과, XML 5/5.
- 화면(Chrome, 임시 서버 8115 + `tools/screenshot_ui.py 기술수요조사서.docx` → `artifacts/ui_docx/`): 「DOCX 저장」·「OOXML 검사」·「Word 출력」 문구, 가져오기 검증 10단계 통과,
  편집 → 출력파일 검증 통과, 원본 ↔ 수정본 Word PDF 쪽 비교 창, 되돌리기 뒤 원본 바이트. 콘솔 오류 0. app.js `paraLook` docx 내어쓰기 분기는 20 이 넣음(장평 작업과 함께).
- 2026-11-08 문서 검토 반영: verify 문구 4곳(다시 저장 차이·웹에 없는 개요 번호·못 되돌린 문단·원본 PDF 없음)을 형식별로, docx_check 사양 링크.

## ④ 미결/후속

- 글상자(`w:txbxContent`) 글은 웹 블록이 아니다(HAZID 뒤표지 주소 1쪽 쪽 나눔 못 맞춤).
- 레터 대조: HAZID 강제 줄 바꿈 문단 15개가 둘째 줄 1.2mm(둘째 줄 맨 앞 빈칸 폭으로 보임 — 미확인), 웹에 없는 개요 번호 2개.
- 글꼴 대조: HAZID 색 39자·크기 24자 — 머리 행이 쪽마다 되풀이되는 표(`w:tblHeader`)의 같은 글을 다른 자리 PDF 글자와 맞춘 것으로 보임(웹 쪽 모양은 맞음).
- 화면의 문단 위·아래 간격·줄 간격 모형(padding·leadShift — spec_hwpx_웹편집 ② §3-4)은 hwpx 만 — docx 는 CSS margin(겹쳐짐) 그대로. Word PDF 로 재고 맞으면 조건을 푼다(20 의 안내).
- 화면 문구 중 「줄 배치」(app.js 고친 문단 탭·되돌리기 알림)는 docx 에 없는 개념인데 그대로 — app.js 를 다른 세션이 고치는 중이라 미룸.
- 조건부 서식의 선(`tblStylePr` tcBorders)·문단 음영(`pPr/shd`) 위 자동 글자색·번호 `lvlRestart`/`isLgl` 은 안 본다. 기본 아닌 문단 스타일 대 표 스타일 차례는 미실측.
- Word 첨자: 첨자 크기 × 0.64·윗첨자 올림 0.44 는 한글 실측값을 그대로 씀(Word 미실측). Word 한글 줄 나눔 단위(`wordBreak`)도 미실측.
- 떠 있는 그림(`wp:anchor`)은 웹에 글 흐름 안 그림으로. 표준 검사는 참조 규칙뿐 — OOXML(ECMA-376) XSD 는 넣지 않았다.
- 출력 자식을 강제로 끝내면 `/Automation` WINWORD.EXE 가 남는다(references 「COM 프로세스」) — 시험 서버를 끌 때 정리 필요.
