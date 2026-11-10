# HWPX 렌더링(PDF) 검증 — 한컴 없이 (2026-10-28 확인) · 한글 COM PDF 특성 (2026-10-29)

## 렌더러 선택

- 한컴 COM(`HWPFrame.HwpObject`)이 한글과 같은 결과를 보장하는 유일한 공식 렌더러. 10-28 까지 이 PC 에는 없었고
  (LibreOffice 도 없음) 한글 2020 설치 뒤 ProgID 가 있다(10-29 확인). Word COM(`Word.Application`)도 있다.
- **@rhwp/core** (npm, MIT, Rust+WASM, `github.com/edwardkim/rhwp`) — HWP/HWPX 파싱 후 페이지별 SVG 렌더링.
  0.8.7 기준 API: `init({module_or_path})` → `new HwpDocument(Uint8Array)` → `pageCount()` / `renderPageSvg(i)`.
- 텍스트 폭 측정 콜백 `globalThis.measureTextWidth(font, text)` 가 **필수**(canvas `measureText`) — Node 단독은
  canvas 가 없어 불가, headless Chromium(playwright) 페이지에서 돌린다. SVG → `page.pdf()` 로 PDF, PyMuPDF 로 래스터 비교.
- 대안: LibreOffice + H2Orestart 확장(HWP/HWPX 가져오기) — 미검증.

## 한글 COM PDF 출력의 특성 (2026-10-29, 한글 2020 · PyMuPDF 1.28)

- **파일 접근 확인 창**: 보안 모듈(`RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")`)이 등록돼 있지 않으면
  (`HKCU\Software\HNC\HwpAutomation\Modules` 비어 있음) `Open` 때 「한글을 이용하여 위 파일에 접근하려는 시도…」 창(접근 허용 / 모두 허용 / 허용 안 함 /
  모두 안 함)이 뜨고, `XHwpWindows.Item(0).Visible = False` 여도 창은 화면에 보인다. 누르기 전까지 `Open` 은 기다린다(CPU 거의 0).
  이 창은 그 Hwp.exe 의 보이는 최상위 WPF 창(클래스 `HwndWrapper[hwp.exe;;…]`)으로 잡힌다 — 사람이 없어 시간 초과가 날 때 멈춤과 구별하는 법(2026-10-29).
  **「모두 허용」은 그 한글 프로세스 안에서 유지** — 한 프로세스로 문서 여러 개를 이어 찍으면 한 번만 묻는다(새 `Dispatch` = 새 Hwp.exe = 다시 물음).
  **끄는 법(2026-11-01)**: 한글 환경 설정 메뉴에는 없다. `HKCU\Software\HNC\HwpAutomation\Modules` 에 값 `FilePathCheckerModule`(REG_SZ) = 보안 모듈 DLL 경로를
  두면 `RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")` 이 True 를 돌려주고 창이 안 뜬다(둘째 인자 = 값 이름). DLL 은 한컴 자동화 예제
  FilePathCheckerModule(Example).dll — pyhwpx 휠(`pyhwpx/FilePathCheckerModule.dll`, 217KB)에 들어 있어 `pip download pyhwpx --no-deps` 로 받아 꺼낼 수 있다
  (설치 불필요). 이 PC 는 11-01 기준 키가 비어 있고 DLL 도 없었다 — `tools/hwp_register_module.py` 가 내려받기·등록·확인(`--check`)을 한다.
- 시간: 17.9MB·163쪽 46s, 31MB·178쪽 62s(`Open`+`SaveAs PDF`).
- **굵게는 가짜 굵게(돋움이 설치돼 있을 때)**: 10-29 에는 돋움이 있어(`C:\Windows\Fonts\gulim.ttc` — 「한국어 추가 글꼴」) PDF 글꼴이 `Dotum` 하나로
  나오고, 굵은 글자도 같은 글꼴에 span flags 굵게 비트(16)가 없다. 대신 글자를 채운 뒤 같은 자리를 한 번 더 긋는다 — PyMuPDF `page.get_texttrace()` 에
  같은 글자가 `type 0`(채움)·`type 1`(긋기, `linewidth` 2.2~2.8 ≈ 글자 크기의 0.17)로 두 번 나온다(굵게 판정 = span 폭의 절반 이상이 긋기 trace 로 덮임).
  10-28 처럼 돋움이 없으면 한글이 HCR Dotum 으로 바꾸고 굵게는 `HCR Dotum Bold` 파일로 나온다(아래 「한글의 글꼴 대체」). 맑은 고딕·함초롬바탕은
  `MalgunGothicBold`·`HCRBatang-Bold` 처럼 굵은 글꼴로. 같은 문서라도 PC 글꼴 설치 상태에 따라 굵게가 글꼴 이름으로도, 긋기로도 나온다.
- 쪽에 걸친 표는 쪽마다 따로 그려진다(조각). 그림은 연구계획서 기관별 파일들에서 쪽에 걸쳐 잘린 것이 없었다(한글은 그림이 남은 높이보다 크면 다음 쪽으로).
- **같은 내용은 문서가 달라도 같은 픽셀로 찍힌다**(2026-10-29, 연구계획서 주관 ↔ 공동2 한국선급 PDF): 칸 글이 모두 같은 표 112개를 항목 자리만
  1.5배 회색조로 잘라 여백을 깎고 견주면 111개가 다른 픽셀 0, 1개(두 문서에서 다른 쪽·다른 높이)만 글자 가장자리 안티에일리어싱으로 3.0%(차 60/255
  초과) — 2×2 평균으로 줄이면 0.8%. 쪽 전체는 한 줄만 늘어도 아래가 다 밀려 견줄 수 없다(첫 30쪽 중 27쪽만 비트 동일).
- **그림은 원본 바이트가 같으면 PDF 그림도 같다**: PyMuPDF `page.get_image_info(hashes=True)` 의 `digest` 가 같은 원본 그림 24쌍 모두 같았다 —
  그 자리의 digest 가 다르면 그림 자리를 잘못 찾은 것. 좌우로 맞닿은 그림들은 `get_image_info` 상자가 서로 붙어 있어, 맞닿은 조각을 잇는 방식으로는
  여러 장이 하나로 묶인다(같은 쌍에서 13개 — 그래서 render_anchors 는 10-29 부터 문서의 그림 크기로 조각을 찾는다). 그림 위에 겹쳐 그린 글상자도
  같은 상자 안에 찍히므로 그림을 픽셀로 견주면 거짓 차이가 난다. WMF 같은 벡터 그림은 `get_image_info` 에 상자가 없다.
- **글 순서**(2026-10-31, 연구계획서 PDF·PyMuPDF `get_text("dict")`): 표 칸 글은 문서 칸 순서(행 우선)로 나온다 — 세로 병합 칸 글도 그 자리 순서로,
  화면에서는 덮는 행 가운데에 그려진다(추진일정 표: 「1 서브모듈 토폴로지… 2 고장 검출…」). 떠 있는 표(구역 첫 「연구개발계획서 [√] 일반형」 머리 표)는
  흐름 밖이라 쪽 맨 앞이 아니라 다른 글 뒤에 나온다. PyMuPDF 「줄」은 같은 높이 글이 칸 간격·탭으로 여러 줄로 나뉠 수 있어 줄 판정은 세로 가운데로.
- **줄 나눔이 작성자 PC 의 줄 캐시와 다를 수 있다**: 연구계획서 6,667문단 중 10(공백 자리만 다른 것 제외) — 글꼴 대체로 폭이 달라 어절 대신 글자에서
  넘어가거나(「실험장비 관|리 상태」) 한 줄로 들어감(「58.65%」). 강제 줄 바꿈 뒤 공백은 줄 캐시가 다음 줄(들여쓰기)로 친다.
- **PDF 글꼴 이름**(서브셋 접두 없음): 한글 — `HCRDotum`·`HCRDotum-Bold`·`HCRBatang-Bold`·`MalgunGothic`·`MalgunGothicBold`·`New Gulim`(공백 있음)·
  `H2hdrM`(HY헤드라인M)·`H2gtrM`(HY중고딕)·`T1`(Type3 = HFT 글꼴); Word(기술수요조사서.docx) — `MalgunGothic`·`MalgunGothicBold`. 브라우저 글꼴
  이름은 붙은 단어를 띄운 것(「HCR Dotum」)이 잡힌다. 휴먼명조처럼 **이름이 한글인 글꼴은 PyMuPDF 가 「????」로 준다**(2026-10-31, 공고문).
- **글머리(레터) 글자의 글꼴 대체**(2026-10-31, 공고문 한글 2020 PDF): 휴먼명조 문단의 「◦」(U+25E6)는 휴먼명조에 그 글자가 없어 `Batang`(batang.ttc)으로,
  「ㅇ」(U+3147, 한글 자모)은 휴먼명조로 찍힌다 — 8pt 글자에서 폭 3pt / 8pt 라 PDF 에서도 다른 글자로 보인다. 같은 문서의 「□」·「①」·「-」·숫자도 `Batang`.
- **2쪽 모아 찍기 PDF**(2026-10-31, 공고문 hwpx): 792×611pt 가로 한 장에 문서 두 쪽(본문 왼쪽 = 왼 반 38pt·오른 반 434.1pt), 글자 12pt → 8pt(배율 0.667).
  문서 설정 때문인지는 미확인. 한 장 안에서 가운데를 넘는 줄이 없다(쪽 판정에 씀 — calibration `_two_up`).
  2026-11-02 두 번째 사례(산업기술혁신사업 연구개발계획서 hwpx, 같은 792×611 장에 「- 23 -」·「- 24 -」, 8pt → 5.16pt 배율 0.645): 이 문서 `settings.xml` 의
  `<config:config-item-set name="PrintInfo">` 에 `PrintMethod`(short) = **4** — 한글 COM PDF 출력이 문서 인쇄 방식(모아 찍기)을 따르는 것으로 보인다(값 4 = 2쪽 모아 찍기로
  추정). **2026-11-08 확인**(NewFileManager, 연구개발계획서 양식): 출력용 사본의 `settings.xml` 에서 이 값만 4 → 0 으로 바꿔 COM `SaveAs(…, "PDF")` 하면
  모아 찍기 37장(792×611 가로) 대신 **74쪽 모두 A4 세로 595×841** 로 한 쪽씩 나온다(26.8 s) — 한글 PDF 출력이 문서의 인쇄 방식을 따르는 것이 맞다.
  모아 찍기 장 15 = 문서 PDF 29·30쪽(쪽 번호 줄 「- 22 -」·「- 23 -」, 앞 7쪽은 쪽 번호 없음) — 「장 번호」와 「쪽 번호」를 섞어 보면 다른 쪽으로 보인다. PyMuPDF 줄 순서는 **왼 쪽 다음 오른 쪽**(장 27개 모두 섞이지 않음) — 다만 반마다 쪽 번호 줄 「- n -」 이
  그 쪽 맨 앞 줄로 나오고, 줄여 찍혀 장 아래 8% 띠 밖(611pt 장의 538pt, 쪽 위 첫 줄은 38pt)에 온다. 같은 렌더 캐시의 모아 찍기 PDF 는 5개(792×611 — 연구개발계획서
  일반형 양식 d850c51b 포함, 장 27~38): KEIT·산업기술혁신사업 양식 문서에 흔하다. 반 쪽에서 띠를 글 높이로 재면 쪽 맨 위·아래 본문 줄(「구분」·「(1) 1차년도」·「작성요령」)이
  같은 높이로 3~8쪽에 되풀이된다 — 쪽 번호는 거의 모든 쪽(52/54).
- **앞 공백·글자 자리**(PyMuPDF `TEXT_PRESERVE_WHITESPACE`): 한글 PDF 는 문단 앞 공백도 글자로 내보내 줄 상자 x0 = 문단 왼쪽, 첫 비공백 글자 x 와의 차 =
  앞 공백 폭(휴먼명조 12pt 공백 ≈ 6pt). `get_text("rawdict")` 글자(chars)를 이으면 `"dict"` span 글과 같다(178쪽 모두), 시간 0.53 → 0.60 s.
- **표 칸 글이 뒤 본문보다 나중에 나온다**(2026-11-08, NewFileManager — 연구개발계획서 양식 한글 2020 PDF, PyMuPDF `get_text("dict")` 순서):
  「가. 참여연구자 현황」 문단 → 표(「번호·소속·기관…」) → 「나. 연구지원인력 현황」 문단 순서의 문서가 PDF 글자열에서는 가 → 나 → 표 칸 순으로 나왔다.
  문서 순서 하나로 맞추면 표 칸을 놓친다(73%) — 본문 문단을 먼저 맞추고 표 칸은 앞뒤 본문 문단의 쪽 범위에서 따로 찾으면 95%.
- **줄 캐시를 지운 문단이 있으면 다른 쪽 글자 자리도 미세하게 흔들린다**(2026-11-08, NewFileManager — 연구개발계획서 양식): 문단 2개 끝에 「★」(줄 캐시 삭제,
  section2.xml 만 바뀜) → 고친 문단이 든 PDF 11·26쪽 외에 6~9·13~19쪽도 픽셀이 달랐다. 그 쪽들은 PyMuPDF 줄마다 글이 같고 줄 상자가 1pt 안,
  다른 픽셀 0.002~0.033% — 숫자·영문(「1단계(20xx~20xx)」의 1·2·x) 글자 가장자리만 다름. 고친 쪽보다 **앞쪽**에도 생긴다(6~9쪽 < 11쪽).
  그래서 쪽 비교는 픽셀이 다르면 곧 실패로 보지 말고 글·줄 자리를 함께 봐야 한다. 원인(구역 전체 재조판인지)은 미확인.
- **반복 머리 행·이어진 칸이 쪽 맨 위에 온다**(2026-11-08, NewFileManager — 연구개발계획서 양식 문서 74쪽): 쪽 맨 위 줄은 늘 「그 쪽에서 시작한 문단」이 아니다 —
  ① 앞 쪽에서 이어진 표 칸의 뒤 문단(「작성 요령」 한 칸 표가 쪽을 넘김, 세로 병합 행 묶음의 아래 행) ② 표 머리 행 반복(「20××년」). 쪽 나눔을 맨 위 줄로 맞출 때는
  줄이 단위의 **첫 문단 첫머리**인지(시작) 그 밖인지(이어짐)를 가려야 한다. 같은 글의 표(일정표 3개, 「구분|구체적인 내용」 표 2개)가 붙은 쪽에 되풀이되면 글만으로는
  어느 표인지 모른다 — 앞 쪽 PDF 글에 그 글이 몇 번 나왔는지 세어 고른다.
- **글자처럼 취급한 표 여럿이 한 문단에 있어도 넓으면 쪽까지 갈라진다**(같은 문서 2-3절: 일정표 2개가 한 문단 → 20쪽·21쪽).
- **글자 모양이 PDF 에 나오는 방식**(2026-11-08, NewFileManager — 한글 2020 · PyMuPDF 1.28 `rawdict`·`get_texttrace`, 기술수요조사서·연구개발계획서 양식):
  - 크기: span 크기 = 문서 크기 × 0.995(10pt → 9.95, 15 → 14.99, 9.5 → 9.47). 2쪽 모아 찍기는 × 0.665~0.675(8 → 5.4, 10 → 6.71, 13 → 8.75) — 같은 장에서도 크기마다 1% 안팎 흔들린다.
    **윗첨자**(`hh:supscript`)는 본문 크기의 약 64%로 찍힌다(「보안등급1)」의 「1)」).
  - **언어별 글꼴**: 한글은 글자마다 charPr `fontRef` 의 그 언어 글꼴로 찍는다 — 한글 글꼴이 「한컴돋움」인 런의 숫자·「[」「]」「,」는 영문 글꼴 `Dotum`, 한글은
    `HCRDotum`(한컴돋움이 없어 함초롬돋움으로 대체). 자동 글머리 「◦」는 글이 굵지 않아도 `HCRBatang-Bold`(굵게 비트 켜짐)로 찍혔다.
  - 굵게: 맑은 고딕은 굵은 글꼴 파일(`MalgunGothicBold`, flags 20 = 굵게 16 + 4), 돋움·돋움체는 가짜 굵게(긋기 trace — 위 「굵게는 가짜 굵게」, 이 PC 11-08 에도 그대로).
    **Type3 글꼴**(HFT 한양중고딕 `T8`·`T9`, 한양견고딕 `T1`·`T11` — `page.get_fonts()` 의 종류 「Type3」, flags 0)은 굵은 런도 굵게 비트·「Bold」 이름·긋기가 없어 PDF 로는 굵게를 모른다.
  - 휴먼명조(한컴 동봉 글꼴)는 PDF 글꼴 이름이 `????`, 그 런의 영문·숫자는 `Batang` 으로 찍혔다.
  - **PDF 글꼴 이름 ↔ 글꼴 파일**: 이름표(name table)의 PostScript·전체 이름이나 파일 이름과 공백·기호 뺀 소문자로 맞는다 — `HCRDotum`·`HCRBatang-Bold`(HANDotum·HANBatangB),
    `MalgunGothic`·`MalgunGothicBold`, `Dotum`·`DotumChe`·`Gulim`(gulim.ttc 안 face), `H2hdrM`(H2HDRM.TTF = HY헤드라인M = HYHeadLine-Medium), `H2gtrM`(HY중고딕). 이 PC
    `C:\Windows\Fonts` 이름표 읽기 1.5s(이름 2,810개).
  - 앞 공백·레터 뒤 공백은 공백 글자로 나온다(칸 수 = 문서 글의 공백 수 — 연구개발계획서 양식 헤딩 790줄 모두 같음). 자동 글머리 「◦」 다음 글은 공백 글자 없이 바로 붙는다
    (글머리 상자 오른쪽과 글이 0.1mm 겹침). 둘째 줄 x − 첫 줄 x = 서식 내어쓰기(−첫 줄 들여쓰기) ±0.5mm(144줄 모두), 본문 첫 줄 x = 왼쪽 여백 + 들여쓰기(302줄) —
    2쪽 모아 찍기 반 쪽은 용지를 반 장에 맞춘 배율(가로·세로 중 작은 것, A4 → 792×611 반 장 0.666)로 나누면 맞다.
  - PyMuPDF 블록 하나에 같은 높이의 **이웃 표 칸 글**이 함께 들 수 있다(「대3」 칸 글 뒤에 「0.01 초과 ～ 0.1 이하」 칸 글이 같은 줄 높이·같은 블록) — 줄 앞머리를 볼 땐
    문서 글을 PDF 줄에서 거꾸로 맞춰 문단 시작을 찾아야 한다. 가운데 정렬 칸은 줄마다 시작 x 가 달라 둘째 줄 들여쓰기로 못 잰다.
- **한글 COM 을 두 프로세스에서 동시에**(2026-11-08): 자식 프로세스 둘이 각자 `Dispatch("HWPFrame.HwpObject")`(Hwp.exe 둘)로 다른 문서를 동시에 PDF 로 찍어도 둘 다 정상
  (2·12s 문서: 하나씩 14.3s → 동시에 12.7s). 보안 모듈이 등록된 PC 라 확인 창은 안 떴다 — 미등록 PC 면 프로세스마다 창이 한 번씩 뜬다.
- **PDF → 한글 변환 부품**(2026-11-08, 이 PC 한글 2020 설치본 `E:\Office 2020\HOffice110\Bin`): `HpdfHwpConverter.exe`(2020-02 빌드 — 들어 있는 글자열
  `CHpdfHwpConverterDlg`·`CDHwpCtrl` 로 보아 한글 컨트롤을 쓰는 MFC 대화상자 앱, 명령줄 옵션 글자열은 안 보임), `HncPdfSdk\PdfFlt.flt` 와 형식 필터
  (`DOCXFlt`·`XlsxFlt`·`PptxFlt`·`RtfFlt`·`htmFlt`·`txtFlt`·`CsvFlt`…), OCR `Hocr.exe` 가 있다. 따로 설치하는 한PDF 앱(실행 파일)은 없고 `.pdf` 연결에도 한컴이 없다.
  **확인 안 함**: COM `Open(경로, "PDF", …)` 이 받는지, 숨긴 한글에서 변환 대화상자가 떠서 멈추는지.
- 쓰는 곳(FileMergeManager): app/render_anchors.py(렌더링 모양 앵커), app/calibration.py(PDF 대조 보정).
  NewFileManager: [app/pdf_render.py](../app/pdf_render.py)(한글 COM PDF 출력), [app/pdf_map.py](../app/pdf_map.py)(매핑·쪽 비교),
  [app/pdf_style.py](../app/pdf_style.py)(레터·글꼴 대조),
  [spec/spec_hwpx_웹편집.md](../spec/spec_hwpx_웹편집.md) ② §3·§4.

## 렌더러 특성 (비교 결과 해석 시 주의)

- 문단에 `hp:linesegarray`(한글이 저장한 줄 배치 캐시)가 있으면 그 값을 쓴다. 텍스트가 같으면 lineseg 를 지워도
  렌더 결과가 같다(SVG 동일).
- lineseg 가 없고 텍스트가 바뀐 문단은 rhwp 자체 글꼴 메트릭으로 줄을 계산 → 아래 내용이 몇 px 이동할 수 있다.
- 표 셀 안 문단의 줄 수가 바뀌면 rhwp 는 표 행 높이를 내용 기준으로 다시 계산해 **다른 행이 줄어들 수 있다** —
  한글은 셀 저장 높이(`hp:cellSz`)를 최소로 유지하므로 이 차이는 렌더러 특성으로 본다(한컴 실물 확인 전 가정).
- 기본 글꼴(함초롬 등)이 없으면 브라우저 대체 글꼴로 측정 — 원본/저장본을 **같은 렌더러로 상대 비교**하는 용도로만 신뢰.

## 브라우저 글꼴 (2026-10-28, 이 PC Chromium)

- Windows Chromium 은 `font-family` 의 **한글 이름도 찾는다**: "새굴림" = "New Gulim", "맑은 고딕" = "Malgun Gothic"(같은 폭).
  한글 문서의 글꼴 이름을 그대로 써도 설치만 돼 있으면 잡힌다.
- 설치 여부 확인은 `document.fonts.check()` 로 하면 안 된다(없는 글꼴도 true) — canvas `measureText` 폭을 fallback 과 비교한다.
- 이 PC 미설치(10-28): 돋움·돋움체·굴림·바탕(Windows 선택적 기능 "한국어 추가 글꼴" = Korean Supplemental Fonts 에 들어 있음 — 10-29 에는
  `gulim.ttc`·`batang.ttc` 가 있다, 위 「한글 COM PDF 출력의 특성」),
  휴먼명조·한양 글꼴(한양은 한글 HFT 내장 글꼴 — PDF 에 Type3 로 나옴). 레지스트리에 HY 글꼴(HYHeadLine-Medium 등)이 있으나 한글·영문 이름 모두 브라우저에서 안 잡힘.
- 함초롬체는 한글 2020 설치 뒤 **있다**(`C:\Windows\Fonts\HANDotum.ttf`·`HANDotumB.ttf`·`HANBatang.ttf`·`HANBatangB.ttf`, 2026-10-28 밤):
  "HCR Dotum"·"함초롬돋움"·"HCR Batang"·"함초롬바탕" 모두 잡히고 `font-weight:700` 이면 Bold 파일을 쓴다(local() 고정 글꼴과 픽셀 동일).
  "HCR Dotum Bold" 같은 굵기 붙은 이름은 family 로 안 잡힘. 공백 폭: HCR Dotum·HCR Batang 0.30em, New Gulim 0.333, 맑은 고딕 0.35, Segoe UI 0.274.
- **한글의 글꼴 대체**(이 PC, 연구계획서 한글 2020 PDF — 문서 런 글을 PDF 글자열에 맞춰 PDF 글꼴을 셈): 돋움 → HCR Dotum
  (굵게 → HCR Dotum Bold), 굴림 → New Gulim, **돋움체 → HCR Batang Bold**(보통·굵게 모두 Bold 파일, PDF 굵게 플래그), 바탕 → HCR Batang Bold
  (6글자뿐), 한양중고딕 → 영문·숫자는 HCR Dotum(이 문서엔 숫자만), 한양견고딕 → Type3(HFT), HY중고딕 → H2gtrM·HY헤드라인M → H2hdrM(한글은 HY 를
  찾음). 문서 `hh:font` 에 `hh:substFont` 가 없는 글꼴이라 한글 자체 대체 규칙(돋움체는 typeInfo proportion 9 = 고정폭)으로 보인다 — 규칙은 미확인.
  맑은 고딕(굵게 = Malgun Gothic Bold)은 설치돼 있어 그대로.
- Chromium 은 **글상자 맨 앞 글자가 공백이면 word-spacing 을 안 준다**(white-space pre·pre-wrap, text-indent 무관). 줄바꿈 뒤 줄 첫 공백·NBSP·
  앞에 U+FEFF 나 빈 `inline-block` 이 있으면 준다. U+200B·U+2060 을 ::before 에 넣으면 그 글자가 폭을 차지했다(HCR Dotum, 24–26px@16px).
- HY 글꼴은 **파일이 실제로 있다**(`C:\Windows\Fonts\H2*.TTF`, 11개 — 레지스트리 HKLM `…\CurrentVersion\Fonts` 의 값). 예:
  `H2HDRM.TTF` = HY헤드라인M / HYHeadLine-Medium, `H2GTRM.TTF` = HY중고딕 / HYGothic-Medium, `H2MJSM.TTF` = HY신명조 /
  HYSinMyeongJo-Medium. 유니코드 cmap(3,1)이고 name 표에 한글(0x412)·영문(0x409) 이름이 다 있다 — 이름이 안 잡히는 원인은 파일 쪽이 아님(미확인).
  `HMKM*.TTF` 는 HY 가 아니라 휴먼둥근헤드라인·휴먼아미체·휴먼매직체.
- **한컴 동봉 글꼴 자리**(2026-10-31, 한글 2020): 휴먼·HY·양재 등 TTF 86개를 `<설치>\HOffice110\Shared\TTF\Hwp`(이 PC `E:\Office 2020\…` — 레지스트리
  `HKLM\SOFTWARE\WOW6432Node\HNC\…` 의 `SharedData Path`)에 두고 **Windows 글꼴로 등록하지 않는다** — 브라우저·Word 는 「휴먼명조」를 못 찾는다(위 미설치와 같음).
  `HMKMM.TTF` = 휴먼명조, `HMKMG.TTF` = 휴먼고딕, `HMKMOLD.TTF` = 휴먼옛체(C:\Windows\Fonts 의 같은 접두 파일과 다른 글꼴; name 표 이름이 한글뿐 —
  fontTools 없이 `name` 표를 직접 읽어 확인). 이 휴먼 글꼴들엔 「◦」(U+25E6)가 없다(「ㅇ」·「□」는 있음). 한양 글꼴은 `Shared\Fonts\*.HFT`.
  `Shared\Fonts\UnlicenseFontList.ini`(UTF-16)에는 함초롬·문체부 글꼴 이름 76줄이 있고 휴먼 계열은 없다(목록의 뜻은 미확인).
- 이름 조회와 무관하게 쓰는 길: 로컬 서버가 글꼴 파일을 내주고 `@font-face { font-family: "HY헤드라인M"; src: url(/fonts/H2HDRM.TTF) }`
  — 브라우저가 파일을 직접 읽는다(2026-11-08 확인 — 아래 「웹 글꼴 local()·url()」). 상용 글꼴(MS·한컴 동봉)은 **그 PC 안에서만** 쓸 것(외부 배포·공개 서버 금지).
  함초롬체는 한컴이 무료 배포.

## 웹 글꼴 local()·url() · 한글 HFT·대체 글꼴 · 첨자·장평 PDF 크기 (2026-11-08, 한글 2020 · Chrome 156·Edge 157 · PyMuPDF 1.28)

- **font-family 이름 vs `@font-face local()`**: Chrome 156·Edge 157·Playwright Chromium 140 모두 font-family 의 「Dotum」·「돋움」·「Malgun Gothic」·「맑은 고딕」·
  「HCR Dotum」·「함초롬돋움」은 찾지만 「HYGothic-Medium」·「HY중고딕」·「HYHeadLine-Medium」·「HY헤드라인M」은 **못 찾고** 대체 글꼴로 그린다(폭이 serif 와 같음).
  같은 글꼴을 `@font-face { src: local("HYGothic-Medium") }`(또는 PostScript `local("H2gtrM")`·한글 전체 이름 `local("HY중고딕")`)로 걸면 **찾는다**.
  → 문서 글꼴은 이름표의 전체 이름(name 4)·PostScript 이름(name 6)으로 local() 을 거는 것이 확실하다. 한컴 동봉 TTF(`Shared\TTF\Hwp\HMKMM.TTF` = 휴먼명조)는
  설치가 안 돼 local() 은 못 찾고 `url()` 로 읽힌다. `unicode-range` 로 언어 글꼴을 나누면 한 줄의 영문은 영문 글꼴, 한글은 한글 글꼴(폭이 두 글꼴 합과 같음).
- **한글 2020 이 쓰는 동봉 글꼴 폴더**: `Shared\TTF\Hwp`(휴먼명조 → PDF 에 「????」 글꼴로 찍힘)는 쓰고, `Shared\TTF\All`(한컴돋움 `HDOTUM.TTF`·한컴바탕 등)은
  **안 쓴다** — 한컴돋움 문단이 HCR Dotum 으로 찍힘(기술수요조사서). 설치 폴더 = 한글 COM 등록 `HKCR\HWPFrame.HwpObject\CLSID` → `CLSID\{…}\LocalServer32`
  (`E:\Office 2020\HOffice110\Bin\hwp.exe -Automation`) 의 `..\..\Shared`.
- **HFT(한글 전용 글꼴 — 한양중고딕·한양견고딕·한양신명조 …, `Shared\Fonts\*.HFT` 「Han Unified Font File 1.0」)**: 한글 글자는 PDF 에 이름 없는 Type3(「T1」·「T8」·「T9」·「T11」)로
  찍히고, 영문·숫자·기호는 문서 `hh:font`(그 언어 fontface)의 `hh:substFont` 로 찍힌다(연구개발계획서 양식: 한양중고딕 LATIN → Dotum, SYMBOL → Batang, HCI Poppy → Batang).
  대체 글꼴이 없는 영문 HFT(「HCI Hollyhock」)는 Dotum 으로 찍혔다 — 규칙은 모름(HNC 레지스트리·FontMap 에 없음). 10-28 줄의 「한양중고딕 영문 → HCR Dotum」은
  그때 이 PC 에 Dotum 이 없어서였던 것으로 보인다(대체 글꼴 Dotum → 없으면 HCR Dotum).
- **`Shared\Fonts\FontMap.dat`**(UTF-16, 머리 「Haansoft Slide Font Information Data」 — 한컴 슬라이드용): `mapFont=HY중고딕,HY중고딕,한양중고딕,중고딕`·
  `mapFont=HY견고딕,한양견고딕,견고딕,HY강B`·`mapFont=HY신명조,HY신명조,한양신명조,신명조` 처럼 같은 디자인 묶음이 있다(한양 HFT ↔ HY TTF). `mapFontClass=한컴돋움,DOTUM`
  같은 대체 규칙도 있으나 한글 워드는 따르지 않는다(한컴돋움 → HCR Dotum).
- **「????」 PDF 글꼴 이름**: 한글 PostScript 이름(휴먼명조의 name 6 = 「휴먼명조」)을 한글 PDF 가 글자 수만큼 「?」로 쓴다(`INPILL+????`). 넣은 부분 글꼴엔 name 표가 없다.
- **언어 글꼴로 찍는 글자**: 숫자·영문 → LATIN fontRef, ㎎·㎥(U+3380–33FF) → SYMBOL fontRef(한양중고딕 문단에서 Batang). 「ㆍ」(U+318D)·「ㅇ」·①은 한글 글꼴과 같은
  글꼴로 찍혀 구분 못 함.
- **윗첨자**(`hh:supscript`): 글자 크기 × 0.639~0.642(91자), 기준선이 크기 × 0.433~0.448 올라감(같은 줄 앞 글자 origin 과 비교).
- **PyMuPDF span 크기 = 글자 행렬의 기하 평균**(√|det|): 장평 r% 글자는 크기 × √(r/100) 로 읽힌다(80% → 0.895, 96% → 0.979~0.981, 98% → 0.981 — 한 쪽씩 찍은 PDF).
  rawdict 글자 상자 높이도 같은 배율. 「11pt 가 10.5pt 로 찍힘」처럼 보이던 것이 장평이었다.
  쓰는 곳: [app/fonts.py](../app/fonts.py), [app/pdf_style.py](../app/pdf_style.py) `check_fonts`, [spec/spec_hwpx_웹편집.md](../spec/spec_hwpx_웹편집.md) ② §3-2·§3-3.

## 한글 줄·글자 배치 — 장평·자간·빈칸·줄 간격·문단 간격 (2026-11-08, 한글 2020 A4 PDF · Chrome 156 대조)

- **글자 간격 = 글자 폭 × 장평 × (1 + 자간)**: 자간(%)은 장평을 적용한 폭 기준이다. 한글 글자(전각) 평균 간격 실측 — 장평 96%·자간 −8/−11/−12/−18% =
  0.8831/0.8528/0.8430/0.7860em(식 0.8832/0.8544/0.8448/0.7872), 장평 80%·자간 −18% = 0.652em(식 0.656, 「크기 기준」 식 0.62 와 다름). PDF 글자 x 가 0.12pt 단위로
  반올림돼 글자 하나씩 보면 5.16·5.28pt 가 번갈아 나온다 — 평균으로 봐야 한다(가운데 값은 치우침).
- **빈칸**(「글꼴에 어울리는 빈칸」 끔, charPr `useFontSpace="0"`): 0.5em × 장평 × (1 + 자간) — 8pt 장평 80% 자간 −18% 빈칸 2.64pt(식 2.62). 브라우저는 글꼴 빈칸 폭
  (Dotum ≈ 0.3em)이라 빈칸 많은 줄이 몇 mm 좁아진다. PDF 에는 빈칸 글자가 안 나오는 곳이 있다(앞뒤 글자 간격에 들어감).
- **줄 배치**(lineseg·PDF 바닥선): 줄 = 글자 높이 `textheight`(= 그 줄 가장 큰 글자 크기) + `spacing`(= textheight × (줄 간격 − 100%)), 기준선 `baseline` = 줄 위 + 0.85 × textheight
  (8,285줄 모두 0.85), 줄 사이 거리 = textheight × 줄 간격 — 여분은 글자 **아래**. CSS `line-height` 는 같은 거리지만 여분을 위아래 반씩 둔다(크기·줄 간격이 바뀌는 문단
  경계에서 ±0.8mm 어긋남).
- **표 칸 높이**(2026-11-09 실측, 11-10 바로잡음 — 연구개발계획서 양식, 한글 2020 한 쪽씩 PDF 괘선): 저장된 `hp:cellSz height` 는 **최소 높이**이자 보통 인쇄 행 높이(요약문 표
  24행 0.05mm 안) — 내용이 더 크면 행이 커진다(2쪽 작성 요령 표 저장 5.52 → 인쇄 16.9). 칸 내용 높이 = **글자 크기(1em) + (줄 수 − 1) × 크기 × 줄 간격 + 위·아래 칸 여백**(`cellMargin`)
  — 마지막 줄엔 줄 간격 여분이 없다(문단이 여럿이어도 줄 사이 거리는 같음). 예: 10pt 130% 1줄 여백 0.5 → 3.53 + 1.0 = 4.53(저장 4.52), 여백 0.4 → 4.33(저장 4.33), 3줄 3.53 + 2×4.586 +
  1.0 = 13.70(13.69), 10pt 120% 8줄 3.53 + 7×4.233 + 1.0 = 34.16(34.13). (11-09 의 「글꼴 높이 = 크기 + 0.18mm」는 여백을 0.4 로 잘못 보고 맞춘 값.) 괘선은 저장 높이 안에 긋는다(두께가
  행을 늘리지 않음). 한글 줄 높이는 **줄마다** 그 줄의 가장 큰 글자 × 줄 간격(13pt 라벨 + 11pt 설명 문단 둘째 줄 = 11pt × 160%). 표 바깥 여백 `hp:tbl/hp:outMargin` 은 이 양식이
  140~141 HWPUNIT(0.5mm)·일부 0 — 한글 기본값 283(1mm)과 다르다. 쪽 번호는 꼬리말 영역(283~287mm)에 찍히고 본문은 위쪽 + 머리말(20mm) ~ 아래쪽 + 꼬리말 앞(277mm).
  CSS 표는 td `height` 가 content-box(여백·괘선 1px 이 더해짐) → `box-sizing: border-box` + 여백 `calc(여백 − 0.5px)`, 마지막 문단 음수 margin 으로 맞춘다.
  쓰는 곳: [spec/spec_hwpx_웹편집.md](../spec/spec_hwpx_웹편집.md) ② §3-5.
- **Chrome 글자 폭 반올림(Windows, 2026-11-10 실측)**: `local()` 로 쓰는 시스템 글꼴 중 내장 비트맵(EBDT)이 있는 굴림·돋움·바탕·궁서·돋움체·바탕체는 글자 폭이 **정수 px 로 반올림**된다
  (13pt 돋움체 17.33 → 18px, 10pt 돋움 13.33 → 13px, 11pt 14.67 → 16px; 배율(CSS zoom)에 따라 달라짐). 맑은 고딕·HCR 돋움/바탕·휴먼명조는 소수 폭 그대로. `text-rendering`·
  `font-synthesis` 는 영향 없음. 같은 face 를 `@font-face url()` 웹 글꼴로 주면(ttc 에서 표만 복사한 TTF, 비트맵 표 EBDT·EBLC·EBSC 를 빼도 됨 — 13 → 6.4MB) 소수 폭 그대로 —
  돋움체는 전각 1.000em·반각 0.500em(PDF 와 0.1mm 안), 돋움 숫자 0.58em. Chrome 은 @font-face 의 ttc 에서 face 를 고르지 못하므로 서버가 face 를 뽑아 준다(fonts.py `extract_face`).
- **Chrome 다단 쪽 흘림(2026-11-10 실험, Chrome 156)**: `column-width/count` + `column-height`(열 높이) + `column-fill: auto` + `column-wrap: wrap`(Chrome 145+) 이면 열이 가로로 다 차면 아래 줄로
  이어져 「열 행 = 쪽」이 된다(`row-gap` 이 쪽 사이). 블록 문단은 줄에서, 표는 행에서, 쪽보다 큰 행은 칸 안 블록에서 나뉘며 `break-before: column` 이 강제 쪽 머리. `getClientRects()` 가 조각마다 하나
  (contenteditable 문단도). Playwright 내장 Chromium 140 은 column-wrap 미지원(열이 가로로 넘침) — 시스템 Chrome(`channel="chrome"`)으로 검증. CSS Regions 는 Chromium 에서 제거됨.
  쓰는 곳: [spec/spec_hwpx_웹편집.md](../spec/spec_hwpx_웹편집.md) ④ 「용지 고정·쪽 흘림 설계」.
- **문단 끝 빈 런**: 마지막 `hp:run` 이 글 없는 런(`<hp:run charPrIDRef="353"/>`)이면 그 글자 크기도 마지막 줄 높이에 든다 — 보이는 글 8pt + 끝 빈 런 10pt 문단의 lineseg
  vertsize 1000(연구개발계획서 양식 20문단 모두, 끝 런이 더 작으면 영향 없음).
- **문단 위·아래 간격은 더한다**: 앞 문단 아래 10pt + 뒤 문단 위 6pt → 사이가 16pt 늘어남(CSS margin 처럼 큰 쪽만 남지 않음). 시험 문서를 만들어 한글로 다시 찍어 확인.
- **한양 HFT 글자 폭**: 한양중고딕·한양견고딕(Type3) 한글 글자 간격 1.04~1.13em — 같은 디자인 HY 중고딕·HY 견고딕 TTF(1em)보다 넓다.
- 브라우저 쪽: `transform: scaleX(r)` 로 줄인 문단 상자(폭 100%/r, 오른쪽 여백 100% − 100%/r)는 줄 나눔이 한글 장평과 같아진다(45/45). 굵은 face 없는 Dotum 을
  Chrome 이 흉내 굵게로 그리면 작은 크기에서 받침 「ㅇ」 글자가 속이 빈 듯 보인다.
  쓰는 곳: [app/static/app.js](../app/static/app.js) `paraLook`·`leadShift`, [spec/spec_hwpx_웹편집.md](../spec/spec_hwpx_웹편집.md) ② §3-4.
