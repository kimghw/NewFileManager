# OWPML(KS X 6101) 스키마 — 구할 곳·한글 저장본과의 차이·검사 도구 사실 (2026-11-08)

쓰는 곳: [app/owpml_check.py](../app/owpml_check.py) · 사양 [spec/spec_owpml_편집.md](../spec/spec_owpml_편집.md) ② §1 · 포맷 일반 [HWPX_포맷.md](HWPX_포맷.md)

## 스키마를 구할 곳

- HWPX = 국가표준 **KS X 6101 OWPML**(HWPX_포맷.md 「컨테이너」). 2024 개정판이 있다(LibreOffice 포럼·hwpjs 자료가 「KS X 6101:2024」로 적음) — 표준 원문은 국가표준 포털(standard.go.kr) 유료 열람으로 보이며 이 PC 에선 확인 안 함.
- 한컴 공개 저장소 **hancom-io/hwpx-owpml-model**(Apache-2.0, 「OWPML파일 필터 모델」, 마지막 push 2023-10-24): C++ 모델(OWPML/·OWPMLApi/·OWPMLUtil/·OWPMLTest/)뿐이고 **XSD 는 없다**(트리 720항목에 xsd·schema 없음, gh API 2026-11-08).
- **python-hwpx 6.11.0**(airmang, PyPI, Apache-2.0) wheel 의 `hwpx/tools/_schemas/` 에 **OWPML 2024 XSD 5개**: `owpml-core.xsd`(44 KB)·`owpml-header.xsd`(99 KB)·`owpml-paralist.xsd`(153 KB)·`owpml-body.xsd`·`owpml-xml.xsd`. 네임스페이스
  `http://www.owpml.org/owpml/2024/{head,paragraph,core,section}`. 같은 폴더의 `header.xsd`·`section.xsd` 는 2011 네임스페이스 루트만 보는 느슨한 껍데기(`xs:any lax`).
  NOTICE 는 「public OWPML schema」를 참고했다고만 적고 원 출처 URL 은 없다. 이 프로젝트 사본: `app/owpml_schema/`(NOTICE.md 에 SHA-256).
- 한글 2020 이 저장한 파일은 **2011 네임스페이스**(`http://www.hancom.co.kr/hwpml/2011/…`) — 2024 XSD 로 검사하려면 네 네임스페이스 URI 를 바꿔 넣는다(요소 이름·구조는 대부분 같다).

## 한글 저장본 ↔ OWPML 2024 XSD (실샘플 2종, 2011→2024 네임스페이스만 바꿈)

기술수요조사서(50 KB) · 연구개발계획서 양식(488 KB, 문단 7,496). 한글이 저장한 원본도 XSD 를 통과하지 못한다 — 「위반 없음」은 기준이 될 수 없고 **원본 대비**로 봐야 한다.

| 어긋남 | 개수(작은·큰) | 뜻 |
|---|---|---|
| `hp:p/hp:linesegarray` 「run 이 와야 할 자리」 | 54 · 7,638 | 줄 배치 캐시 — 한컴이 OWPML 밖 확장이라고 밝힌 것(HWPX_포맷.md 조판 규칙) |
| `hh:paraPr` 안 `hp:switch`(HwpUnitChar case/default) → 「margin 이 와야 할 자리」(autoSpacing 다음) | 38 · 395 | XSD 에 switch 가 없음 — 한글 12.0(xmlVersion 1.5) 형식 |
| `hh:charPr @shadeColor="none"` — 패턴 `#[0-9A-F]{6}` 밖 | 40 · 358 | 한글은 「없음」을 none 으로 쓴다 |
| `hh:borderFill` 자식 순서(fillBrush 자리) | 12 · 104 | |
| `hh:font/hh:typeInfo @letterform·armStyle·midline` 등 = 숫자 — xs:boolean 밖 | 수십 | 파노스 값 |
| `hp:t/hp:tab @type="2" @leader="3"` — 열거(LEFT…·LineType2) 밖 | 0 · 34+34 | 한글은 숫자 코드로 쓴다(아래 「탭」) |
| `hp:secPr @tabStop` 허용 안 됨, `startNum` 자리, `newNum` 에 autoNumFormat 없음, `trackchangeConfig`·`presentation` 자리 | 1~3 | 판 차이 |

- linesegarray 를 검사 사본에서 빼면 작은 문서 141건 11가지, 큰 문서 978건(2026-11-08).
- 참조 규칙(IDRef 가 있는 정의를 가리킴·itemCnt·secCnt·secPr 자리·표 격자)은 두 원본 모두 **위반 0**.

## 한글 2020 이 받아들이는 것 (COM, 2026-11-08 실측)

- **탭 `hp:tab`**(글 안 탭): 한글이 저장한 것은 `width="19879" leader="3" type="2"` 처럼 숫자. 우리가 넣은 세 가지를 한글이 열어 다시 저장(SaveAs HWPX)하면 —
  속성 없는 `<hp:tab/>` → `width="0" leader="0" type="0"`, `type="LEFT" leader="NONE" width="4000"` → `width="4000" leader="0" type="0"`(OWPML 이름을 제 숫자 0 = 왼쪽·채움 없음으로 읽음),
  `type="1" leader="0"` → 그대로. 저장된 width 는 조판에 안 쓰인다(4000 을 줬는데 PDF 탭 간격 7.5pt — 탭 자리로 다시 잼).
  OWPML 2024 는 `type` 필수 — 속성 없는 `<hp:tab/>` 은 XSD 위반(「필수 속성 없음」). → 새 탭은 `width="4000" leader="NONE" type="LEFT"`.
- **다시 저장**: COM `hwp.SaveAs(path, "HWPX", "")` 로 한글이 연 문서를 HWPX 로 다시 쓴다(PDF 와 같은 자식 프로세스). 열기·PDF 는 되는데 저장에서 죽는 구조(칸 없는 `hp:tr`, HWPX_포맷.md)를 찾는 데 쓴다.
- 구조·서식 편집 결과(문단 나누기·합치기, 새 charPr/paraPr — refList 끝에 붙이고 itemCnt 갱신, 표 행·열 복사·삭제, 칸 안 문단 나누기)를 넣은 연구개발계획서 양식:
  한글이 열고 PDF 37장(원본과 같은 장 수), 다시 저장한 파일의 문단 7,504개 글·차례가 내보낸 파일과 모두 같음.

## 검사 도구(lxml/libxml2) 사실

- **오류 하나가 뒤를 가린다**: 요소만 내용(sequence)에서 「이 요소는 올 자리가 아님」이 나면 libxml2 는 그 부모의 나머지 자식을 더 보지 않는다 — `hp:p` 끝의 linesegarray 가 그 뒤에 잘못 들어간 요소를 가렸다.
  검사 사본에서 linesegarray 를 빼야 편집 결과가 끝까지 검사된다.
- **오류 → 요소**: 오류에는 줄 번호만 있다. HWPX XML 은 한 줄이라, 검사 사본에서 자식 요소마다 앞에 줄 바꿈을 넣어(요소만 내용·섞인 내용 모두 공백 글이 허용됨) 줄 번호 = 요소로 맞춘다.
  6만 7천 요소(5 MB 구역)도 줄 번호가 맞았다(lxml 6.1 — 65,535 줄 넘음 문제 없음).
- **`XMLParser` 객체도 스레드 사이에 나눠 쓰면 안 된다**(lxml FAQ): 병렬 가져오기 검증에서 여러 단계가 같은 바이트를 한 전역 파서로 동시에 열자 1.8 MB 문서가
  「Namespace prefix w for eastAsia on lang is not defined, line 2, column 864000」 같은 **거짓 구문 오류**로 한 단계만 실패했다(newfilemanager-6e, docx, 2026-11-08). 스레드마다 파서를 만든다.
- **`XMLSchema` 객체는 스레드 사이에 나눠 쓰면 안 된다**: `validate()` 가 같은 객체의 `error_log` 를 덮어써서, 두 스레드가 동시에 검사하면 오류 목록이 섞인다(가져오기 검증 스레드 + 편집 요청에서 실제로 엉뚱한 위반으로 거절됨). 스레드마다 따로 만든다.
- **떼어 낸 요소의 뿌리**: lxml 은 `parent.remove(el)` 한 요소도 같은 문서에 묶어 둬서 `el.getroottree().getroot()` 가 **원래 뿌리**를 돌려준다 — 「트리 안에 있나」 판정에 쓰면 지운 문단이 살아 있는 것으로 보인다. 부모를 따라 올라가 확인한다.
- 속도(연구개발계획서 양식): header 750 KB 검사 0.03 s, 구역 5 MB 0.24 s, 줄 바꿈 사본 포함 문서 전체 1.2 s, 편집 한 번이 닿은 문단만 0.02~0.16 s.
