# HWPX 파일 포맷 — 구조·무손실 편집에 필요한 사실 (2026-09-02 최초, 2026-10-28 보강)

한컴 HWPX 는 OOXML 처럼 **zip + XML** 컨테이너다. 이 프로젝트의 소비자는
`app/hwpx_doc.py`(블록 트리·편집·병합 어댑터)이며, 이 문서는 포맷 자체의 사실만 기록한다.

## 컨테이너

- zip 멤버: `mimetype`(무압축 STORED 가 관례), `version.xml`, `META-INF/*`,
  `Contents/header.xml`(스타일·charPr 정의), `Contents/section0.xml`(본문 — 섹션이
  여러 개면 `section1.xml` …), `Contents/content.hpf`.
- 한컴 공식 설명(한컴테크 「HWPX 포맷 구조 살펴보기」, 2025-02-26, https://tech.hancom.com/hwpxformat/): HWPX = 국가표준
  **KS X 6101 OWPML**(2011-12-30 제정) 패키지. 멤버 역할 — `mimetype` 포맷 판별 시그니처, `version.xml` OWPML 버전·저장 환경,
  `settings.xml` 저장 시점 커서 위치(CaretPosition), `META-INF/` `container.xml`·`container.rdf`(주요 파일 목록)·`manifest.xml`
  (암호 문서면 파일별 암호화 정보), `BinData/` 그림·OLE, `Scripts/`(headerScripts·sourceScripts), `Preview/` 미리보기 이미지·텍스트
  (**암호 문서는 저장 안 함**), `Contents/content.hpf` = OPF(metadata 작성자·제목·날짜 / manifest 파일 목록, **순서 무의미** /
  spine **나열 순서대로 읽는다**), `header.xml` = HWP DocInfo 대응(글자·문단 모양, 금칙 문자, 호환 설정, 변경 추적),
  `section*.xml` 구역마다 1개. 변경 추적·이력·그림/스크립트 제거 여부에 따라 멤버 구성이 달라진다.
- 같은 블로그의 파싱 편(https://tech.hancom.com/python-hwpx-parsing-2/, 2025-09-29): `hp:p` 속성 id·paraPrIDRef·styleIDRef·
  pageBreak·columnBreak·merged(+paraTcId), `hp:run charPrIDRef`(+charTcId), `hp:t` 는 mixed — 자식 markpenBegin/End·titleMark·tab·
  lineBreak·hyphen·nbSpace·fwSpace·insertBegin/End·deleteBegin/End 와 tail 텍스트를 이어 붙여야 본문이 빠지지 않는다.
  블로그는 네임스페이스를 `http://www.owpml.org/owpml/2021/…` 로 적었으나 이 프로젝트 실파일(한글 11·12 저장)은
  `http://www.hancom.co.kr/hwpml/2011/…` — 파서는 URI 를 고정하지 말 것. 한컴 공개 C++ 모델: hwpx-owpml-model(오픈소스).
- 본문 조작은 `Contents/section*.xml` 만 바꾸고 나머지 멤버는 바이트 그대로 재압축하면
  된다(docx 의 `word/document.xml` 수술과 동형). ZipInfo(압축 방식 포함)를 보존할 것.
- 섹션 파일 번호 순서 = `content.hpf` spine 순서(실문서 3편 국문-25: section0~50, 51개).
  spine 에는 `header` itemref 도 있고 `linear` 속성은 있다 없다 한다. 섹션 수는 `header.xml` 루트 `hh:head secCnt` 에도 있다.
- 문서 중간의 용지 방향 전환은 섹션 경계가 된다(연구계획서: `pagePr landscape` WIDELY/NARROWLY 섹션이 번갈아 24개,
  width/height 값은 같고 속성만 다름). 섹션을 지우려면 멤버 + manifest item + spine itemref + secCnt 를 같이 고친다.
  **구역을 새로 만들려면**(예: 표 하나만 가로 쪽으로) 섹션 파일을 나눠 새 `sectionN.xml` 을 만들고 뒤 파일 번호를 밀어
  파일 번호 = spine 순서를 유지, manifest item·spine itemref 추가, secCnt 갱신. 새 구역 첫 문단 첫 런에 `hp:ctrl/hp:colPr` +
  `hp:secPr` 사본을 넣는다(방향만 바꾸려면 `pagePr landscape` WIDELY↔NARROWLY). 섹션 파일마다 secPr 는 하나.
  @rhwp/core 렌더로 확인(연구계획서_공동2: 163→165쪽, 그 자리에 가로 쪽) — 한글 실물은 미검증. 구현 `app/wide_pages.py`.
- 그림 바이너리는 `BinData/imageN.ext`. 목록은 **`Contents/content.hpf` manifest 에만** 있다
  (`<opf:item id="imageN" href="BinData/imageN.png" media-type="image/png" isEmbeded="1"/>`, 철자 `isEmbeded`).
  `META-INF/manifest.xml` 은 빈 요소, header.xml 에 binData 목록 없음.
  링크 그림은 `isEmbeded="0"` + zip 밖 href(멤버 없음).

## 본문 XML (표 기준)

- 표: `<hp:tbl>` → 행 `<hp:tr>` → 셀 `<hp:tc>` → `<hp:subList>` → 문단 `<hp:p>` →
  런 `<hp:run>` → 텍스트 `<hp:t>`.
- **네임스페이스 접두사는 `hp:` 고정이 아니다** — 생성 도구에 따라 다를 수 있으니
  파서는 접두사를 유연하게 잡아야 한다(`</?접두사:(tbl|tr|tc|p|subList)` 식).
- 셀 주소: `<hp:cellAddr colAddr=".." rowAddr=".."/>` 속성이 있으면 그것이 정본,
  없으면 등장 순서로 계산. 병합은 `<hp:cellSpan colSpan rowSpan>`.
- `hp:tr` 은 그 행에서 시작하는 칸만 담는다(세로 병합 칸은 시작 행의 `tr` 에). 행을 끼우면 뒤 칸 `rowAddr`, 걸친 칸 `rowSpan`,
  `hp:tbl rowCnt` 와 함께 `hp:tbl/hp:cellzoneList/hp:cellzone startRowAddr·endRowAddr`(칸 영역 테두리, 연구계획서 실문서에 있음)도
  밀어야 한다(2026-10-29 `insert_rows`). 병합 칸 `cellSz height` 는 실문서에서 0(한글이 행 높이 합으로 계산)인 경우가 많다.
  0 이 아니어도 행 높이 합과 안 맞을 수 있다(KEIT 연구개발계획서 일반형 251224 「자본총계(백만원)」 3행 병합 칸 5102 vs 행 2147×3 = 6441) — 한글은 병합 칸 높이를 무시하고 1칸짜리 칸의 높이로 행을 정한다. 문단 `hp:linesegarray/hp:lineseg` 의 `vertsize`·`textheight` 는 글자 크기(8pt → 800), `spacing` 은 줄간격 몫(110% → 80)(2026-10-31).
  **열 경계 = 칸 폭 누적**(2026-11-09): 한글은 칸을 제 `cellSz width` 대로 왼쪽부터 놓으므로 행마다 칸 폭을 더해 얻은 `colAddr` 경계가 인쇄 괘선 자리와 일치한다
  (연구개발계획서 양식 요약문 표 18열 — 3쪽 괘선 11곳 모두 0.1mm 안). 1칸짜리 칸이 없는 열이 많고(18열 중 14열) 첫 행이 전체 병합 제목인 표에서는 1칸 폭·균등 분할로
  열 폭을 추정하면 크게 어긋난다(레이블 열 36.4 → 25.0mm, 글이 줄 바뀜).
  **행·열을 지울 때**도 같은 값들을 줄인다(걸친 칸 span −, 시작 행이 지워진 칸은 남는 첫 행으로, 다 지워진 cellzone 은 뺌, 표 문단 lineseg 삭제) —
  이렇게 행 수십~129개·열 1개를 지운 연구계획서 표들을 한글 2020 이 열고 PDF 로 냈다(2026-10-29).
- **한글 「셀 합치기」(COM `TableMergeCell`, 2026-10-29 실측 — 기술수요조사서 1×2·2×1·2×3 범위)**: 글 = 칸들의 문단을 위→아래·왼→오른
  순으로 이어 붙임(빈 칸 제외), `cellSz` = 덮는 줄 합, 선 = 왼쪽 위 칸 borderFill 에 오른쪽 아래 칸의 오른쪽·아래 선을 얹은 새 borderFill.
  그 뒤 **칸이 하나도 시작하지 않는 행·열을 없앤다**(rowCnt/colCnt 감소, 걸친 칸 span −1, 크기는 앞 줄에 합침). 칸을 다시 나눠도 그 줄은 안 돌아온다.
- **칸 없는 `hp:tr`(빈 행) 이 있으면 한글이 열기는 하지만 HWPX 저장에서 죽는다**(COM `SaveAs` → `The server threw an exception`,
  2026-10-29 — 기술수요조사서 표 (3,1) 을 손으로 2행 걸침으로 늘려 4행을 비움). 칸이 시작하지 않는 **열**(colAddr 빈 번호)은 열고 저장한다
  (한글은 그대로 둠 — 고치지 않는다).
- **표를 새로 지어 넣기**(2026-11-10 한글 2020 COM 실측 — 기술수요조사서 2표·연구개발계획서 양식 6표를 본으로 4×6 표를 지어 넣고 「HWPX 로 다시 저장」·PDF 출력, 다시 연 표 수·글 일치):
  본이 되는 표의 `hp:tbl` 속성과 `hp:sz·hp:pos·hp:outMargin·hp:inMargin` 을 복사하고(`hp:caption`·`hp:cellzoneList` 는 빼도 됨) `hp:tr` 을 새로 지어, 칸마다 본의 `hp:tc`(속성·`cellMargin`)를 본떠
  `cellAddr·cellSpan·cellSz` 와 문단(본 칸 문단의 속성 + 런 하나 + `hp:t`)을 써넣은 표를 한글이 그대로 받아들인다. 새 문단(본의 표를 품은 문단 속성 + 런 + 표 + 빈 `hp:t`)에 담아 아무 문단 뒤에 넣으면 된다.
  `hp:tbl id` 는 다른 개체와 안 겹치는 수를 줬다(겹쳐도 되는지는 안 해 봄). **`cellSz height` 는 최솟값으로 읽힌다** — 한 줄 높이를 써도 글이 여러 줄이면 한글이 행을 늘려 찍고(다시 저장한 파일에는 늘어난 높이가 적힘),
  글보다 큰 높이는 그대로 남는다. 열 폭은 `cellSz width` 그대로(글이 길면 칸 안에서 줄을 바꿈). 칸 괘선은 칸마다 borderFill 네 변이라, 표 바깥 굵은 선·머리와 몸 사이 선을 지키려면 바깥 변·구역 경계의 칸에서 그 변을 따와야 한다
  (같은 바탕에 변만 바꾼 borderFill 을 header 에 더함). 귀퉁이 칸의 대각선은 borderFill `hh:backSlash type="CENTER"`(연구개발계획서 양식 정의 8개) — `NONE` 으로 바꾸면 사라진다.
- 그리기 개체 안에도 `subList`/`p` 가 중첩되므로 셀 텍스트 수집 시 깊이 추적 필요.
  중첩 표(`tbl` 안 `tbl`)도 존재한다.
- 섹션 첫 문단의 첫 런에 `hp:secPr`(용지·여백, `hp:pagePr width/height` + `hp:margin`, 단위 HWPUNIT=1/7200인치)와
  `hp:ctrl/hp:colPr` 가 있다. A4 세로는 `landscape="WIDELY" width="59528" height="84186"`.
  순서는 문서마다 다르다 — 연구개발계획서 양식(KEIT 일반형 251224) 「목  차」 문단은 `[ctrl colPr][secPr][t][t]`(colPr 가 앞, 같은 런에 글도 있음).
  그 문단 위에 새 문단을 넣으면 secPr·구역 ctrl 을 새 첫 문단으로 옮겨야 secPr 가 계속 구역 첫 문단에 있다(app `insert_line`, 2026-10-31).
- 표·그림은 런 안의 개체: 런 패턴은 대개 `(tbl, t/)`·`(pic, t/)` — 개체 뒤에 빈 `<hp:t/>`. 한 런·한 문단에 표 여러 개 가능
  (기술수요조사서는 첫 문단 하나에 secPr 런 + 표 2개).
- `hp:t` 자식: `hp:tab`(width/leader/type 속성), `hp:fwSpace`, `hp:lineBreak` (+tail 텍스트). `hp:t charStyleIDRef` 는 style 참조.
  탭 속성 값(한글은 숫자, OWPML 2024 는 열거·type 필수)과 한글이 새 탭을 읽는 방식은 [OWPML_스키마.md](OWPML_스키마.md) 「한글 2020 이 받아들이는 것」.
- 수식 `hp:equation` 은 런 안 인라인 개체(실문서에 5천여 개) — 텍스트 아님.
- `hp:p id` 는 `2147483648`·`0` 등 중복이 정상.
- 캡션: `hp:tbl`/`hp:pic` 의 자식 `hp:caption side gap width lastWidth` → `hp:subList` → `hp:p`.
  실문서 캡션은 리터럴 텍스트(`표 3.1.3 …`)였고 autoNum 은 쪽번호(`PAGE`)만 있었다.
- 자동 번호: `hp:run/hp:ctrl/hp:autoNum num=".." numType="PAGE|PICTURE|TABLE|EQUATION|…"` + `hp:autoNumFormat`.
- 그림 `hp:pic`: `hc:img binaryItemIDRef`(= manifest item id), 표시 크기 `hp:sz width/height`(HWPUNIT),
  원본 `hp:orgSz` ≈ 픽셀×75(96dpi), 자르기 없으면 `hp:imgClip right/bottom` = orgSz, `hp:imgRect` 꼭짓점도 orgSz.
  `hp:shapeComment` 에 원본 파일명·픽셀 크기. 0×0 크기(숨김) 그림도 실재한다.
  한글은 그림을 `hp:sz` 상자에 **늘려** 그린다 — 상자 비율이 원본(orgSz) 비율과 달라도(자르기 없음) 그렇다(연구계획서_주관 image18
  orgSz 90600×38880 = 2.33, sz 67071×27224 = 2.46, imgClip 전체). imgClip 이 orgSz 와 다른 값(예 right/bottom 15000)인 그림도 있다
  — WMF 등은 orgSz 와 단위가 달라 보임(미확인).
  연구계획서_공동2 PNG 그림 6개(150dpi)는 imgClip right/bottom = **픽셀×75**(775px → 58140)이고 orgSz 는 그와 무관한 값이었다 —
  「imgClip = orgSz」는 모든 그림에 맞는 규칙이 아니다(2026-10-29). WMF 그림(Office 붙여넣기 `CLP*.wmf`)은 imgClip 15000×15000.
- **Office 붙여넣기 WMF 에는 같은 그림의 EMF 가 들어 있다**(2026-10-29, 연구계획서 image160 596KB 중 388KB): `META_ESCAPE`(0x0626)
  `MFCOMMENT`(0x000F) + 식별자 `WMFC`(0x43464D57) 레코드 48개에 8192바이트씩 나눠 담고(CommentRecordCount·CurrentRecordSize·
  RemainingBytes·EnhancedMetafileDataSize), Checksum 은 첫 레코드에만 — **파일 전체 16비트 워드 합 = 0 (mod 65536)** 이 되게 한 값.
  그 EMF 는 EMF+ 겸용(EMF+ 주석 236개, GDI 글은 world transform 으로 위치·Reference 0,0). Windows GDI(Pillow WMF 읽기)는 체크섬이
  맞으면 이 EMF 를 그리고, 한 바이트라도 바뀌면 WMF 레코드로 그린다 — WMF 레코드판은 동그라미 숫자(①)·일부 굵은 제목이 빠지고 자간이 벌어짐.
  **한글 2020 도 EMF 를 뺀 판에서 동그라미 숫자·굵은 제목·대괄호 기관명이 빈칸**으로 나와(원본은 정상) 원본 렌더는 임베디드 EMF 를 쓴 것으로 본다.
  → WMF 레코드만 고치면 화면이 나빠지거나(체크섬 불일치) 옛 그림이 남을 수 있다(체크섬을 맞춘 경우). 고칠 때는 EMF 쪽까지 같이 고치거나
  원본 렌더(래스터)를 고쳐 PNG 로 바꾼다(manifest `href`·`media-type="image/png"`, imgClip = 픽셀×75).
- 런 안 기타 개체: `hp:rect`·`hp:ellipse`·`hp:line`·`hp:container`(묶음, 안에 pic 가능)·`hp:ole`.

## header.xml

- `hh:refList` 자식 순서: fontfaces, borderFills, charProperties, tabProperties, numberings, bullets,
  paraProperties, styles, (memoProperties, trackChanges …). 각 목록 `itemCnt` = 자식 수. 없는 목록은 생략된다.
- id 는 순번: charPr·paraPr·style·tabPr 은 0부터, borderFill·numbering·bullet 은 1부터.
- 글꼴: `hh:fontface lang="HANGUL|LATIN|HANJA|JAPANESE|OTHER|SYMBOL|USER" fontCnt` → `hh:font id face`.
  charPr 의 `hh:fontRef hangul=.. latin=..` 는 언어별 fontface 안의 font id — 문서 간 복사 시 재매핑 필요.
- 참조 관계: charPr `borderFillIDRef`; paraPr `tabPrIDRef`, `hh:border borderFillIDRef`,
  `hh:heading type="NONE|OUTLINE|BULLET|NUMBER" idRef level`; style `paraPrIDRef charPrIDRef nextStyleIDRef`;
  bullet/numbering `hh:paraHead charPrIDRef`(`4294967295` = 없음).
- heading: OUTLINE 은 `idRef="0"`(번호 모양은 secPr `outlineShapeIDRef` 의 numbering), level 0-based.
  BULLET → `hh:bullets/hh:bullet char`(paraHead level 0), NUMBER → `hh:numberings/hh:numbering`
  (paraHead level 1-based = heading level+1, 텍스트 템플릿 `^1.`·`(^5)`, `numFormat` DIGIT·HANGUL_SYLLABLE·CIRCLED_DIGIT…, `start`).
- 굵게: charPr 에 `hh:bold` 자식. 셀 배경: borderFill `hc:fillBrush/hc:winBrush faceColor`(`none` 또는 `#RRGGBB`).

## 기입(값 써넣기) 시 서식 보존

- 문단 속성은 `<hp:p paraPrIDRef=..>`, 글자 속성은 `<hp:run charPrIDRef=..>` 로
  header.xml 의 정의를 참조한다 — 셀 내용을 교체할 때 기존 첫 문단/첫 런의 이 속성을
  승계하면 서식이 유지된다.
- `<hp:linesegarray>`(줄 배치 캐시)는 복제하지 않아도 된다 — 한글이 열 때 재계산한다.
- 표준 ElementTree 재직렬화는 네임스페이스 접두사·속성 순서를 바꿔 위험. **lxml** 재직렬화는 실샘플 2종 전 XML 멤버에서
  바이트 동일했다 — 단 XML 파서는 원문 CR(`\r\n`, shapeComment·수식 script 에 실재)을 LF 로 정규화하므로
  파싱 전 `\r`→`&#13;`, 직렬화 후 되돌려야 한다. 선언은 `<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>`
  (`?>` 앞 공백) — 원문 문자열을 그대로 붙인다.

## 서식 정의 — 단위·의미 (2026-10-28, 실샘플 2종 관찰)

- **charPr**: `height` = 1/100 pt(1000 = 10pt), `textColor="#RRGGBB"`. 굵게·기울임은 빈 자식 `hh:bold`/`hh:italic`.
  자식 순서(스키마): fontRef, ratio, spacing, relSz, offset, italic, bold, underline, strikeout, outline, shadow,
  emboss, engrave, supscript, subscript (실문서에서 italic 이 bold 앞). 밑줄 `hh:underline type="NONE|BOTTOM|…" shape color` —
  xmlVersion 1.5 문서는 밑줄 없어도 `type="NONE"` 을 항상 쓰고, 1.2 문서(3편)는 밑줄 있을 때만 쓴다.
  - **장평·자간은 언어별**(2026-11-12): `hh:ratio`·`hh:spacing` 은 스키마상 charPr 의 필수 자식이고 속성은 언어 7개(`hangul`·`latin`·`hanja`·`japanese`·`other`·`symbol`·`user` — 선택, 기본 100·0)다. 실문서에 언어마다 자간이 다른 charPr 가 있다(연구계획서 439개 중 4개 —
    영문만 더 좁힘). 다른 문서의 장평·자간을 옮길 때는 한글 값 하나로 뭉개지 말고 7개를 그대로 옮긴다. `relSz`(언어별 상대 크기)는 본 세 문서 1,007개가 모두 100.
  - **`useFontSpace`(글꼴에 어울리는 빈칸)** = `"0"` 이면 공백 폭 = **0.5em × 장평 × (1 + 자간)**, 글꼴 무관 ✔(한글 PDF 실측,
    연구계획서 HCR Dotum 12pt 자간 −10%: 공백 5.40pt = 0.45em, 장평 99% 런 5.35pt; 글꼴 자체 공백은 0.30em). `"1"` 이면 글꼴의
    공백 폭(미실측). 연구계획서 charPr 439개 중 438개, 기술수요조사서 40/40 이 `"0"`.
- 한 문단 안에서 런마다 `charPrIDRef` 가 다른 것이 흔하다 — 연구계획서: `- `(보통)+`제목`(굵게), `∙ `(굵게)+`본문`(보통).
  문단 대표 글자 모양을 첫 런 하나로 잡으면 굵기가 뒤집혀 보인다.
- **글꼴**: `hh:font id face type="TTF" isEmbedded="0"` (+선택 `hh:typeInfo` 파노스 정보). 언어별 fontface 마다 목록·id 가 다르다.
- **paraPr 정렬** `hh:align horizontal` = JUSTIFY/LEFT/RIGHT/CENTER/DISTRIBUTE/DISTRIBUTE_SPACE.
- **paraPr 여백·간격** `hh:margin` → `hc:intent`(첫 줄, 음수=내어쓰기)·`hc:left`·`hc:right`·`hc:prev`(문단 위)·`hc:next`(문단 아래),
  각 `value` + `unit="HWPUNIT"`; `hh:lineSpacing type="PERCENT|FIXED|…" value`.
  - **내어쓰기(`intent` 음수)는 첫 줄을 `left` 에 두고 나머지 줄을 |intent| 만큼 더 들인다**(한글 문단 모양 "내어쓰기").
    CSS `text-indent` 음수·docx `w:ind hanging`(첫 줄을 왼쪽 밖으로 내밂)과 뜻이 반대 — 화면에 옮길 때
    padding/margin-left = left + |intent|, text-indent = intent. 근거: 연구계획서 마커 문단(`left=0`, intent −10~−12.6mm,
    앞머리 `    - `·`      ∙ ` 폭과 일치 — CSS 뜻이면 첫 줄이 용지 여백으로 나간다). `linesegarray` 의 `horzpos` 는
    intent 를 반영하지 않는다(모든 줄 0).
- **용지** `hp:pagePr landscape width height gutterType` + `hp:margin left right top bottom header footer gutter`.
  `landscape="WIDELY"` = 세로(값 그대로), `"NARROWLY"` = 가로(폭·높이 값은 세로 기준으로 저장 → 교환해서 읽는다).
  본문 시작은 위쪽 + 머리말, 끝은 아래쪽 + 꼬리말(한글 편집 용지의 머리말·꼬리말 영역이 여백 안쪽에 있다) — 연구계획서
  top 2834 + header 2834 = 20mm, 좌우 5669 = 20mm → 본문 폭 170mm 는 lineseg `horzsize` 48188 과 일치. 위·아래 해석은
  한글 대화상자 의미 기준이며 실물 렌더로는 미검증.
  - xmlVersion 1.5(한글 12.0) 문서: 두 요소가 `hp:switch` 안에 있다 — `hp:case hp:required-namespace=".../2016/HwpUnitChar"` 는
    **HWPUNIT**, `hp:default` 는 **같은 값 ×2**(구버전 판독기용).
  - switch 없는 문서(3편, xmlVersion 1.2, 한글 11.0)는 **×2 값**이 바로 들어 있다 — lineseg `horzpos` = left/2,
    `horzsize` = 본문폭 − left/2 로 확인. PERCENT 줄간격 값은 ×2 아님(case/default 동일). FIXED 등 비PERCENT 값은 ×2(아래 조판 규칙, rhwp 실측).
  - **×2 값은 짝수로 써야 한다 — 홀수면 한글이 그 여백을 5배로 그린다** ✔(2026-11-10 한글 2020 PDF 실측, 연구개발계획서 양식의 switch 없는
    paraPr 에 값만 바꿔 넣음): `hc:intent value="-7800"` → 둘째 줄 13.75mm, `-7801` → **68.75mm**, `-7802` → 13.75mm; `hc:left value="2834"` → 4.99mm,
    `2835` → **24.96mm**. 즉 짝수 v 는 v/2 HWPUNIT, 홀수 v 는 (v−1)/2 × 5 HWPUNIT. 추정: 맨 아래 비트가 단위 표지(0 = HWPUNIT, 1 = 글자(ch) 단위의 1/100 —
    1ch = 바탕글 10pt 의 영문 글자 폭 5pt = 500 HWPUNIT; 2016 이름 공간 「HwpUnitChar」 가 이 둘을 가르는 까닭으로 보임) — 단위 풀이는 미확인, **5배는 실측**.
    mm 를 값으로 옮길 때 `round(mm × 7200/25.4 × 2)` 는 홀수가 나온다(5mm → 2835) → `round(mm × 7200/25.4) × 2`. 한글이 저장한 switch 없는 파일의 값은 모두 짝수(연구개발계획서 양식 paraPr 여백 값 1,975개) —
    switch 꼴의 `hp:case`(HWPUNIT 그대로)에는 홀수도 있다(기술수요조사서 5개).
- **borderFill** 자식: slash, backSlash, left/right/top/bottomBorder, (diagonal), (`hc:fillBrush` — 마지막).
  채우기 `hc:fillBrush/hc:winBrush faceColor hatchColor alpha` — `faceColor="none"` 또는 fillBrush 없음 = 채우기 없음.
  `#FF000000`(8자리, Windows CLR_DEFAULT 형) 이 hatchColor·NONE 테두리 color·드물게 faceColor 로 나온다 — 색 없음으로 본다.
  `hc:gradation`·`hc:imgBrush` 채우기도 있다(3편 imgBrush 1개).
  **추진일정(간트) 막대가 채움이 아닐 수 있다**(2026-10-30, 연구계획서.hwpx 2-3 기관별 일정 표 t10877): 월 칸에 fillBrush·도형·그림이 전혀 없고 막대 구간 칸만
  borderFill `bottomBorder type="DASH"`(그 밖 칸은 NONE), 왼·오른 선은 열마다 SOLID/NONE 이 번갈아 — 막대를 찾으려면 채움색뿐 아니라 아래 선 종류도 봐야 한다.
  표 하나에 borderFill id 가 열·행 조합마다 다르게 수십 개 생긴다(161/162/72/122/65/119 …).
  **같아 보이는 칸도 borderFill id 가 다르다 — 「같은 표 서식」 은 id 가 아니라 내용으로 견줘야 한다**(2026-11-16, 사업계획서 한 편의 제목 띠 표 둘 「1 . | 운영 방침」·「2 . | 부서사업과제 추진내용」):
  제목 칸의 borderFill 이 9 와 17 인데 내용은 같다(아래 선 SOLID 0.7mm `#365F91` 하나 · 바탕 없음) — 한글에서 표를 복사·붙여 고치면 같은 내용의 정의가 새 번호로 또 생긴다. 바탕도 `faceColor="none"` 과 `#FFFFFF` 가 섞인다(번호 칸은 `#FFFFFF`).
  문단 정렬도 한쪽은 `JUSTIFY`(양쪽), 한쪽은 `LEFT` 였다 — 한 줄짜리 제목에서는 겉모습이 같다. paraPr·charPr id 도 여백 값이 조금 달라 번호가 갈린다(같은 문서의 「사업과제 1」 과 「사업과제 2~4」).
- **셀**: `hp:tc hasMargin="1"` 이면 `hp:cellMargin left/right/top/bottom`, `"0"` 이면 표의 `hp:inMargin` 이 적용된다
  (hasMargin=0 셀도 cellMargin 요소를 갖고 있음). 단위 HWPUNIT — 한글 기본 510/141 = 1.8mm/0.5mm.
  세로 정렬은 `hp:subList vertAlign="TOP|CENTER|BOTTOM"`. `hp:cellSz height` 는 저장된 행 높이 — 글자를 키워 넘치면
  rhwp 는 행을 다시 계산하며 주변 표 테두리가 가려질 수 있다(15pt→24pt 양식 제목 셀에서 관찰, 16pt 는 정상).

## 조판 규칙 — 한글이 저장한 줄 배치와 쪽·줄·셀 계산 (2026-10-28)

출처: Codex(gpt-6-astra)·fable 조사 + 이 PC 실파일 검증. 근거 문서 = 한글문서파일형식 5.0 rev1.3 PDF
(cdn.hancom.com/link/docs/한글문서파일형식_5.0_revision1.3.pdf, 표 6·33·44·46·62·76), rhwp 소스
(github.com/edwardkim/rhwp @1a76570e). OWPML 원문은 못 찾음 — `linesegarray` 는 한컴이 OWPML 밖 확장이라고 밝힘.
✔ = 실파일(연구계획서·연구계획서_공통·기술수요조사서)로 확인, 그 외는 스펙/rhwp 기준.

- **`hp:lineseg`** = HWP5 `PARA_LINE_SEG` 캐시(표 62). 길이 단위 HWPUNIT(100 = 1pt, 75 = 1 CSS px), 1.2 파일도 ×2 아님.
  `textpos` 줄 시작 오프셋, `vertpos` 줄 위, `vertsize` 줄 높이(= 그 줄 최대 charPr height, 개체 줄은 개체 높이 + outMargin 위아래 ✔),
  `textheight`(실파일은 vertsize 와 같음), `baseline` = round(0.85×vertsize) ✔, `spacing` 줄 아래 간격(음수 가능),
  `horzpos`/`horzsize` 단·셀 내용 기준 줄 시작 x·줄 상자 폭 ✔, `flags` 비트(0 쪽 첫 줄, 1 단 첫 줄, 17/18 줄 첫/끝 조각, 20 들여쓰기, 21 문단 머리).
  **flags 비트 0/1 은 한글 11 저장본에서 켜지지 않는다** → 쪽 경계는 flags 로 알 수 없다.
- **textpos 세는 법**(HWP 글자 축, 표 6) ✔: 글자 UTF-16 단위(BMP 1), `hp:lineBreak` 1, `hp:tab` 8, 개체·컨트롤 8 —
  `secPr`·`hp:ctrl` 자식(colPr·autoNum·필드 등)·`tbl`·`pic`·`container`·`equation`·도형. 기술수요조사서 첫 문단
  `[secPr][ctrl colPr][tbl][tbl]` 둘째 줄 textpos 24 = 8×3 → **secPr 도 8**(0 으로 세면 둘째 표 줄이 문단 끝에서 시작해 모순).
  런 경계·형광펜 표지 0. 글이 그대로면 `text[textpos_i : textpos_{i+1}]` 가 한글의 줄 — 같은 줄바꿈을 강제할 수 있다.
- **vertpos**: 본문은 쪽 본문 위 = 0 에서 누적, 셀 안은 셀 내용 위 = 0 에서 셀 문단끼리 누적. 같은 흐름 안 이웃 줄
  Δvertpos = vertsize + spacing ✔(2558/2558). 다음 문단 첫 줄 = 앞 줄 + vertsize + spacing + (앞 문단 `next` + 이 문단 `prev`)
  — **두 간격을 더한다(CSS 처럼 겹치지 않음)** ✔. **vertpos 가 줄면 새 쪽**(문단 중간에서도): section11 p[72]
  textpos 0,51 · vertpos 71296→0, pageBreak=0 ✔. `hp:p pageBreak="1"` 은 그 문단 앞 쪽 나눔(106/106 첫 vertpos 0 ✔), 구역 시작도 새 쪽.
- **줄간격**: PERCENT P → `spacing = sign(r)·4·floor(|r|/4 + 0.5)`, r = vertsize×(P−100)/100(4 HWPUNIT 단위 반올림),
  줄 피치 = vertsize + spacing ✔(900@130% → 272, 1300@110% → 132). 기준은 글꼴 ascent+descent 가 아니라 **글자 크기**.
  간격은 전부 줄 **아래**에 붙고 베이스라인은 줄 위에서 0.85em — CSS line-height(반씩 위아래)로 옮기면 글이
  (P−100)/2 % em 만큼 아래로 보인다. **쪽 끝에서는 마지막 줄의 간격이 본문 밖으로 나가도 된다** — 쪽에 드는 줄 수 N 은
  (N−1)·피치 + 글자 크기 ≤ 본문 높이(2026-10-31 연구계획서 한글 PDF 149쪽: 12pt·160% 피치 19.2pt, 본문 257mm = 728.5pt 에 38줄, 쪽 첫 줄 글자
  위 = 본문 위 56.8pt). CSS(N·피치 ≤ 본문)로는 37줄이라 쪽마다 한 줄이 넘친다 — 본문 상자를 위아래로 반 간격씩 늘리면 같다. FIXED = 줄 피치 그대로, BETWEEN_LINES = 줄 사이 간격, AT_LEAST = max(값, 글자 높이)
  (실파일에 없음, rhwp 기준). **비PERCENT 값도 1.2 파일·`hp:default` 는 ×2**(rhwp 262편 실측), PERCENT 는 ×1.
- **장평 `hh:ratio`·자간 `hh:spacing`**(언어별, 표 33: 장평 50~200%, 자간 −50~50%): 글자 전진폭
  ≈ 원래 폭 × ratio/100 × (1 + spacing/100) — 자간은 글자 크기가 아니라 (장평 적용 후) **그 글자 폭의 %**(rhwp #2279 한컴 PDF 실측;
  전각 글자는 두 해석이 같고 반각·영문만 차이, H2Orestart 는 글자 크기 %로 계산 — 이견). 공백은 LATIN 값.
  CSS: 자간 ≈ `letter-spacing: spacing/100 em`(전각), 장평은 `transform: scaleX` 가 모양만 바꾸고 줄바꿈 폭엔 반영 안 됨 →
  폭 보정(JS 측정 또는 음수 margin) 필요. `font-stretch` 는 가변 글꼴에서만. 연구계획서 분포: 장평 85~100, 자간 0~−14.
  실측(2026-11-02, 돋움 8pt 장평 96·자간 hangul −10/latin −8, 한글 PDF): 「Marine Object Segmentation and 」 118.3pt, 「2021-12-16」 42.8pt — 브라우저 돋움(자간 0)
  글자만 114.1/46.7pt. 전각 기준 `letter-spacing: −0.136em` 을 영문에 그대로 주면 98.6/35.9pt(겹쳐 보임), 그 절반이면 113.2/41.3pt — 반각은 절반이 가깝다.
- **표 쪽 나눔 `hp:tbl pageBreak`**: `CELL` 표에서만 셀 안 vertpos 리셋(행 중간에서 줄 단위로 잘림)이 나온다 — 높이 2120·9766 HU 의
  짧은 행도 잘림 ✔(연구계획서_공통 section21 row54). 한글 UI 이름("셀 단위로 나눔"/"나눔")과의 대응, `TABLE` 동작은 실파일 미확인(`NONE` 은 아래 11-10 실측)
  (Codex 는 hwpxlib 설명대로 TABLE = 줄 단위 분할·CELL = 걸친 셀을 다음 쪽으로 읽었으나 위 실측과 어긋남).
  **`NONE` 실측(2026-11-10)** ✔: `pageBreak="NONE"` · `hp:pos treatAsChar="1"` 인 63행 표(`hp:sz height` 700.8mm — 행을 늘려 용지보다 길어진 연구개발비 총괄표)를 한글이 PDF 로 찍으면
  **나누지 않고 그 쪽 아래로 넘쳐 잘린다** — 쪽 아래 여백·쪽 번호 위까지 그리고 나머지 행은 PDF 글에 없고(마지막 「총계」 행을 못 찾음), 다음 쪽은 표 다음 문단부터다.
  둘 중 어느 속성이 까닭인지는 따로 재지 않음. 행을 늘리는 편집(구분 기준 반영 등) 뒤에는 이런 표가 쪽을 넘는지 봐야 한다.
  쪽에 걸친 표의 **세로 병합 칸**은 한글이 병합 칸 안의 글도 줄에서 나눈다 ✔ PDF(연구개발계획서 양식 TRL 표: 병합 칸 「제품화↵단계」·「신뢰성 평가 및↵수요기업 평가」 의 첫 줄은 앞 쪽 맨 아래,
  둘째 줄은 다음 쪽 머리 — 그 표는 `pageBreak="CELL"` · `treatAsChar="0"` · `repeatHeader="1"`, 위 「`CELL` 표에서만 줄 단위로 잘림」 과 맞는다).
  **`CELL` 표의 긴 행 실측(2026-11-12)** ✔ PDF: 쪽에 남은 자리보다 긴 행은 다음 쪽으로 **행째 넘기지 않고 그 쪽에서 바로 이어 찍다가** 칸 안 줄(그림도 한 줄)에서 나눈다 — 연차보고서 요약문 표(31행,
  `pageBreak="CELL"` · `treatAsChar="0"`)의 「최종 목표」 행(글 30문단 + 그림 2)은 3쪽 아래 절반에서 시작해 4쪽으로, 다음 「전체 내용」 행은 4쪽 가운데에서 시작해 6쪽까지(한 행이 세 쪽). 나뉜 행의 **세로 가운데 맞춘
  제목 칸 글은 그 행이 처음 찍힌 쪽 조각 안에서 가운데**에 놓이고 뒤 쪽 조각의 그 칸은 비어 있다. 같은 표가 `pageBreak="NONE"` · `treatAsChar="1"`(원본 서식)이면 위 `NONE` 실측대로 안 나뉜다.
  `repeatHeader="1"` 이면 표 위에서부터 이어진 `hp:tc header="1"` 행들을 쪽마다 반복.
  여러 쪽에 걸친 `CELL` 표의 `hp:tbl/hp:sz height` 는 **첫 쪽 조각 높이**다 — 연구계획서 191행 표: sz 180mm, 행 cellSz 합 1044mm ✔.
  표 전체 높이·쪽 수는 행 높이 합(또는 셀 안 vertpos 리셋)으로 센다.
- **줄 나눔 기준 `hh:paraPr/hh:breakSetting`** (UI 뜻은 [한글_문단모양_줄나눔.md](한글_문단모양_줄나눔.md)):
  `breakNonLatinWord`(한글 단위) **KEEP_WORD = 글자, BREAK_WORD = 어절** ✔ — 이름과 반대로 읽힌다. 실측(3편 lineseg 줄 끝):
  JUSTIFY+KEEP_WORD 한글 낱말 중간 나눔 747 / 낱말 경계 609("대응이 가|능", "확|인"), JUSTIFY+BREAK_WORD 0 / 16,
  LEFT+BREAK_WORD 6 / 178. 바탕글(paraPr 0)이 KEEP_WORD = 한글 기본값 "글자"와 일치. HWP5 표 44 bit 7(0 어절, 1 글자)과
  enum 대응은 문서화된 것을 못 찾음. `breakLatinWord`(영어 단위) KEEP_WORD/BREAK_WORD(+하이픈 값) — 실파일은 거의 KEEP_WORD,
  영문 낱말 중간 나눔 18건(가운데 정렬 칸)뿐이라 대응 미확정. 같은 요소에 `widowOrphan`(외톨이줄 보호)·`keepWithNext`·
  `keepLines`(문단 보호)·`pageBreakBefore`·`lineWrap="BREAK"`(한 줄로 입력 아님), 형제 `hh:autoSpacing eAsianEng eAsianNum`
  (한글-영어·한글-숫자 간격 자동 조절, 표 45 bit 4·5), paraPr 속성 `snapToGrid`(줄 격자)·`fontLineHeight`(글꼴에 어울리는 줄 높이)·
  `condense`(최소 공백 %로 추정 — 표 44 bit 9–15 0~75%, 실파일 전부 0).
- **셀 높이**: `hp:cellSz height` 는 **최소 높이**(여백 포함) — 내용 + 위아래 여백이 더 크면 한글이 행을 키운다 ✔(연구계획서_공통 셀
  1685개가 선언 < 내용). **칸 선은 높이를 차지하지 않는다** — 10pt 한 줄 + 여백 0.4mm×2 = 4.33mm = cellSz, 한글 PDF 행 간격도
  4.3mm ✔(연구계획서 표지 표, 2026-10-28). 웹에서 선을 border 로 그리면 행마다 1px 커진다(outline 으로 그릴 것).
  내용 폭 = cellSz.width − 여백 좌우. 세로 정렬: 남는 높이 = 높이 − 여백 − 내용(마지막 줄 spacing 제외),
  CENTER 는 그 절반, BOTTOM 은 전부를 위에 둔다(rhwp, 실파일 미검증).
  - **음수가 된 높이는 부호 없는 32비트로 적힌다**(2026-11-11 실파일 — 한글 저장본 「자율운항 … 연구계획서_협약용」 section5, 3칸): `cellSz height="4294967256"`(= 2³² − 40, 즉 −40) ·
    `4294967216`(−80) · `4294965136`(−2160). 모두 rowSpan 1 칸이고 같은 행의 다른 칸은 정상 값(1081). 한글은 그 행을 다른 칸 높이·글 높이로 찍는다(PDF 행 11.1mm — 이웃 행과 같음) ✔.
    → 2³¹ 이상은 「높이 정보 없음(0)」으로 읽는다(`hwpx_layout.hu`). 그대로 읽으면 15,151,690mm 행이 되고, 행을 넣을 때 걸친 칸 높이에 더하면 2³² 를 넘는 값을 적게 된다.
    공개 XSD 의 `cellSz @width·@height` 는 `xs:nonNegativeInteger` 라 이 값은 **스키마 위반이 아니다**(OWPML 검사에 안 걸림). 폭(`width`)·표 `hp:sz` 에서는 아직 못 봄.
- 브라우저로 **정확히** 옮길 수 있는 것: 글이 바뀌지 않은 문단의 줄바꿈·줄 세로 위치·쪽 경계·표 행 분할 지점·셀 행 높이.
  **근사만**: 글꼴이 다를 때의 글자 폭·양쪽 정렬, 베이스라인(글꼴별 보정), 장평 모양, 고친 문단의 재조판.

## 한글 실물 렌더 관찰 (2026-10-28, 한글 2020 v11.0.0.2129 COM → PDF)

- **저장된 줄 배치(`hp:linesegarray`)를 그대로 쓴다**: 캐시가 있는 문단은 다시 계산하지 않는다. 캐시를 지운 문단만 이 PC 글꼴로
  다시 계산 — 문서 글꼴(예: 돋움)이 없으면 대체 글꼴 폭으로 줄 끝이 한두 글자 달라진다(연구계획서: 문단 1개 수정·복원 → 그 쪽만 차이).
- 「캐시 있는 문단의 첫 줄 vertpos 가 앞 문단 마지막 줄보다 위 = 새 쪽」 판정(웹 `pageStart`)이 한글 PDF 의 쪽 맨 위와 대조 가능한
  59개 모두 일치(나머지 113개는 빈 문단·표라 글로 대조 불가). 연구계획서 = 한글 251쪽.
- **글자처럼 취급(`hp:pos treatAsChar="1"`) 개체가 한 문단에 여럿**이면 글자처럼 한 줄에 나란히 놓인다(각 개체 캡션은 그 개체 밑).
  한글이 저장한 꼴(2026-11-12 실측 — 그림 둘을 나란히 붙여 넣은 문단): **런 하나에 개체가 잇달아** `<hp:run><hp:pic/><hp:pic/><hp:t/></hp:run>`(사이에 빈칸을 넣었으면 그 사이에 `<hp:t> </hp:t>`).
  개체마다 문단을 따로 만들면 문단마다 줄이 바뀌어 세로로 쌓인다 — 나란히 두려면 한 문단 안에 둬야 한다.
- `hh:breakSetting` 쪽 나눔: `keepWithNext`(다음 문단과 함께)·`keepLines`(문단 보호)·`widowOrphan`(외톨이줄 보호) — 연구계획서 문단 모양
  467개 중 1인 것 0·0·4. 끈 문단은 쪽 끝·처음에 한 줄만 남아도 그대로 둔다(브라우저 다단 기본 orphans/widows 2 와 다름).
- 머리말·꼬리말 여백(`hp:margin header/footer`)은 본문 위·아래 여백에 더해진다(top 10 + header 10 → 본문 20mm 부터, PDF 실측 일치).
- **양쪽 정렬은 줄 안 공백만 늘린다** — 줄 앞 공백(들여쓰기용)은 그대로(연구계획서 「   - (고장…」 첫 줄: 앞 공백 5.40pt, 글 사이 공백 6.95pt).
  반각 글자 폭 = 글자 폭 × (1 + 자간)(「-」 12pt 자간 −10% = 5.04pt).
- **칸보다 조금 긴 줄을 좁혀 한 줄에 넣는다**: `lineWrap="BREAK"`·`condense="0"` 인데도 lineseg 한 줄에 글 폭 0.85~0.9배로 압축
  (「SiC MOSFET」 칸 4180 HU = 41.8pt 에 41.9pt — 같은 글꼴 같은 크기 보통 폭 49.6pt, 「Wide-bandgap MOSFET」 92.7 → 83.1pt).
  어느 정도까지 좁히는지 규칙은 미확인.
- 글꼴 대체(이 PC 에 문서 글꼴이 없을 때)는 [HWPX_렌더링_검증.md](HWPX_렌더링_검증.md) 「브라우저 글꼴」.
- COM: `HWPFrame.HwpObject` → `Open(path, "HWPX", "forceopen:true")` → `SaveAs(pdf, "PDF", "")`. 47MB·251쪽 한 번에 약 80–100s.
  보안 모듈(`RegisterModule("FilePathCheckDLL", …)`) 미등록이면 파일 접근 확인 창이 뜬다. 무료 한컴 뷰어는 COM 없음.
- COM 한글은 **간헐적으로 죽거나 멈춘다**(2026-10-29, 같은 251쪽 파일 반복): PDF 를 반쯤 쓰다 끝남(열리지 않는 PDF), `Open` 이 8s→259s,
  응답 없음. 그 직후 실행은 1쪽짜리 빈 PDF 를 내기도 한다(열기 실패 뒤 빈 문서를 저장한 것으로 보임 — 원인 미확인). 남은 `hwp.exe -Automation -Embedding` 은 `Quit` 뒤에도
  살아 있을 수 있다 — 파일마다 새 프로세스·시간 제한을 두고, 실패는 한 번 다시 해 본 뒤 판정할 것(다시 하면 같은 파일이 정상 251쪽).

## 표 격자를 고친 파일을 한글이 받아들이는가 (2026-11-10, 한글 2020 COM `Open` → `SaveAs HWPX`, 연구개발계획서 양식)

아래를 한 파일에 모두 한 뒤 한글이 열어 다시 저장했다 — 다시 저장본의 문단 7,505개 글·차례, 표 121개의 행·열·칸 수가 고친 파일과 같다(저장 2.7 s).
칸마다 `hp:cellAddr`(colAddr·rowAddr)·`hp:cellSpan`·`hp:cellSz` 를 격자와 맞추고, 행마다 그 행에서 시작하는 칸만 `hp:tr` 에 열 차례로 두고, `rowCnt`·`colCnt` 를 맞춘 것이 전제(시작하는 칸이 없는
격자 줄은 접는다 — 빈 `hp:tr` 은 한글이 저장하다 멈춘다, 위 「본문 XML」).

- **칸(`hp:tc`)을 다른 표의 `hp:tr` 로 옮겨도 된다** — 칸 주소·폭을 새 표의 격자에 맞추면 한글은 칸이 어느 표에서 왔는지 가리지 않는다(표 둘을 열로 이어 붙이기).
- **표가 든 문단을 통째로 복사해 바로 뒤에 두고**(줄 배치 캐시 `linesegarray`·구역 설정은 빼고, `pageBreak`·`columnBreak` 는 0) 두 표에서 서로 다른 열을 지워도 된다(표 하나를 열로 둘로 나누기).
  표 폭(`hp:sz width`)은 그대로 두고 남은 열의 `cellSz width` 합을 그 폭에 맞췄다.
- **한 칸만 새 격자 행으로 나누고 그 행의 다른 칸은 rowSpan 을 늘려** 걸치게 해도 된다(`hp:sz height`·걸친 칸의 `cellSz height` 를 새 행 높이만큼 늘림 / 그대로 두고 행 높이를 나눠도 됨 — 둘 다).
- **칸의 괘선 한 변만 다른 `hh:borderFill`** 은 원래 정의를 복사해 그 변 요소(`hh:rightBorder` 등)의 속성만 바꾼 새 정의로 — 이웃 칸의 맞닿은 변과 선이 달라도 열린다(어느 선이 그려지는지는 눈으로 확인 안 함).
- 확인 안 한 것: PDF 로 찍은 모양(괘선 굵기·표 사이 간격), 캡션이 있는 표를 복사했을 때의 표 번호.

## 표의 쪽 나눔 · 그림 크기 — 다른 문서의 내용을 넣은 뒤 (2026-11-12, 한글 2020 COM → PDF · KEIT 연차보고서 서식 ↔ 연구개발계획서)

- **쪽을 넘어 나뉘는 표의 조건 둘** ✔: `hp:tbl pageBreak`(TABLE·CELL = 나눔 / NONE = 나누지 않음)가 NONE 이 아니고, **글자처럼 취급이 아님**(`hp:pos treatAsChar="0"`). KEIT 연차보고서 서식의 표지·요약문 표는 `treatAsChar="1"` + `pageBreak="NONE"`,
  연구개발계획서의 요약문 표는 `treatAsChar="0"` + `pageBreak="CELL"`(셀 단위로 나눔) + `textWrap="SQUARE"`.
- **못 나뉘는 표에 한 쪽보다 긴 내용이 들면** ✔: 표가 쪽 끝에서 **잘려** 그 뒤 내용이 안 보이고, 바로 뒤에 **빈 쪽**이 하나 생긴다(37쪽 문서의 4쪽이 빈 쪽 — 오류·경고 없음. 표준 검사·다시 열기로는 안 잡힌다 → PDF 를 눈으로).
- **`pageBreak="CELL"` + `treatAsChar="0"` 로만 바꾸면** ✔(다른 속성 `textWrap="TOP_AND_BOTTOM"`·정렬은 그대로): 같은 표가 3·4·5쪽으로 이어진다(37 → 40쪽). 「셀 단위로 나눔」 이어도 **한 쪽보다 긴 칸은 칸 안의 줄에서 갈린다**(칸 하나가 두 쪽 넘게 이어짐).
  첫 쪽의 자리·너비는 바뀌지 않았다(표 너비 = 글 폭인 표).
- **그림 크기를 줄일 때 함께 바꿀 값** ✔: `hp:sz`·`hp:curSz`(width·height) · `hp:rotationInfo`(centerX·centerY) · `hp:renderingInfo/hc:scaMatrix`(e1·e5 에 같은 배율을 곱함). `hp:orgSz`·`hp:imgRect`·`hp:imgClip`·그림 파일은 그대로 — 한글이 줄어든 크기로 그린다.
  문서 사이로 복사한 그림은 원본 크기 그대로라 목적 칸이 더 좁으면 **칸 오른쪽에서 잘린다**(칸 내폭 111.6mm 에 118.2mm 그림).

## 편집 보호 — 글·문장을 못 고치게 두는 수단 (2026-10-30 조사, 사용자 질문 「절대 수정 불가능한 글자·문장으로 둘 수 있나」)

「절대」는 없다 — 한글 안의 보호는 같은 대화상자에서 끄거나 암호로 풀 수 있고, hwpx 는 zip+XML 이라 외부 도구로 속성을 바꿀 수 있다.
- **일반 편집 모드에서 특정 영역만 편집 제한하는 기능은 없다** — 한컴디벨로퍼 포럼 공식 답(2025-04,
  [특정셀에서만 드래그를 허용하는게 가능한가요?](https://forum.developer.hancom.com/t/ex/2405)): "뷰어모드(EditMode=0) 에서는 특정 영역에 대한 제한을
  걸 수 없습니다." 가장 가까운 것은 **셀 보호**: "셀의 경우 ‘셀 보호’ 설정을 켜면 해당 영역 드래그를 막을 수 있습니다. … 편집모드에서도 동일하게
  제한됩니다." — 표 칸에만 걸 수 있는 부분 보호.
- **셀 보호의 hwpx 표현**: `hp:tc` 속성 `protect="1"`(샘플 3종의 칸 3,617개는 모두 `protect="0"`). 같은 요소의 `editable`(모두 0) = 「양식 모드에서 편집
  가능」 칸 — 양식 모드(웹한글 기안기 EditMode 2)에선 이 칸·누름틀만 고친다. 라벨 칸을 `protect="1"` 로 두면 작성자가 서식 글을 못 건드리고 값 칸만
  쓰게 할 수 있다(앱에서 켜 주는 것은 후보 — 한글에서 끄면 그만이므로 「절대」는 아님).
- **누름틀**(필드 입력 → 누름틀, [도움말](https://help.hancom.com/hoffice/webhelp/9.0/ko_kr/hwp/insert/madanginfo/madanginfo(press).htm)): 안내문·메모·필드
  이름뿐, 보호 옵션은 없다. 새 판·웹한글엔 「양식 모드에서 편집 가능」 체크가 있어 양식 모드에서 누름틀만 편집되게 한다(포럼 답 smkang). 샘플 서식 3종엔
  `hp:fieldBegin` 이 하나도 없다(누름틀을 안 씀).
- **배포용 문서**(보안 → 배포용 문서로 저장, [도움말](https://help.hancom.com/hoffice/multi/ko_kr/hwp/file/send_to_mail/publish(save).htm)): 문서 **전체**를
  쓰기 암호(5~44자) 없이는 "내용을 변경하지 못하도록" 하고, 선택으로 인쇄 제한(미리 보기·인쇄 불가)·복사 제한(복사·오려두기 불가). 문서 암호가 걸린
  문서는 배포용으로 저장 못 함, 블록을 잡아도 문서 전체가 저장됨, 문서 끼워 넣기 불가, 이전 판 한글은 못 읽음. 해제·암호 변경은 「보안 → 배포용 문서
  설정 변경 및 해제」에서 현재 암호 필요 — "암호를 잊으면 그 누구도 … 해독할 수 없습니다". 파일 형식(hwp/hwpx)은 도움말에 언급 없음 — 배포용 문서 구조는
  HWP 5.0 바이너리 기준으로 공개돼 있음([한글문서파일형식_배포용문서 revision 1.2](https://cdn.hancom.com/link/docs/%ED%95%9C%EA%B8%80%EB%AC%B8%EC%84%9C%ED%8C%8C%EC%9D%BC%ED%98%95%EC%8B%9D_%EB%B0%B0%ED%8F%AC%EC%9A%A9%EB%AC%B8%EC%84%9C_revision1.2.pdf)),
  hwpx 지원은 미확인(한글에서 hwpx 를 열고 저장해 볼 것). 서식을 채워야 하는 사람에겐 못 쓴다(전체가 잠김).
- **개체 보호**(개체 속성): 위치·크기만 고정, 안의 글 편집은 막지 않음. **그림으로 붙이기·PDF**: 글자로는 못 고치지만 개체째 지울 수 있음.
  **문서 암호**: 열기만 막음. **파일 읽기 전용 속성**: 다른 이름으로 저장하면 그만.

## 한글 「문서 비교」 (2026-10-30 조사, 사용자 질문 「두 문서를 비교하는 방법은 있나」)

- 메뉴 「검토 → 문서 비교」([도움말](https://help.hancom.com/hoffice/multi/ko_kr/hwp/review/compare_document/compare_document.htm)): 원본 문서·수정한
  문서를 각각 고르고 「비교」 → **새 읽기 전용 창**에 두 문서를 세로로 나란히 놓고 다른 내용을 표시한다("두 개의 문서를 비교하여 새 편집 창에 문서 간 다른
  내용을 표시합니다"). 변경 내용 추적을 켜지 않고 고친 문서도 원본과 비교해 바뀐 곳을 찾는 용도. 원본·수정본 자리 바꾸기 단추.
- 비교 창의 「문서 비교」 탭([도움말](https://help.hancom.com/hoffice/webhelp/9.0/ko_kr/hwp/toolbox/state_document_information.htm)): 분리 창으로 보기,
  가로/세로 배열 전환, 양쪽 창 크기 맞춤, 확대/축소 10~500%(단추 한 번 5%), 「닫기」로 끝.
- 한계(도움말 기준): 문서 전체 글 비교라 **표 칸 단위·구분 기준 자리 단위 차이**(이 앱의 병합 「앵커별 비교」·변경 수치)는 아니다. 도움말은 웹 9.0·멀티 판
  기준 — 2020·2022 메뉴 이름이 같은지는 실물 확인 전.

## 관련

- 구현: [app/hwpx_doc.py](../app/hwpx_doc.py)(서식 §8 은 [app/hwpx_format.py](../app/hwpx_format.py)), 테스트 [tests/test_hwpx_doc.py](../tests/test_hwpx_doc.py),
  사양 [FileMergeManager 의 spec_왕복_어댑터.md](../../FileMergeManager/spec/spec_왕복_어댑터.md) §1·§2, [FileMergeManager 의 spec_서식.md](../../FileMergeManager/spec/spec_서식.md)(옛 프로젝트 사양서 — 이 저장소 spec/ 에는 없다).
- 한/글 화면 쪽 규칙(문단 모양·정렬·줄 나눔 기준): [한글_문단모양_줄나눔.md](한글_문단모양_줄나눔.md).
- 한컴 미설치 PC 에서 작성 — 위 사실은 실파일 XML 관찰 기반이며 한글에서 여는 검증은 별도.
