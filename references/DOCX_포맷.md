# DOCX(OOXML) 포맷 — 블록 추출·무손실 편집에 필요한 사실 (2026-10-28, `app/docx_doc.py` 구현에서 확인)

포맷 자체의 사실만 적는다. (FileMergeManager references 에서 복사 — 그쪽 사양 링크는 FileMergeManager 의 spec. 이 프로젝트의 구현 사양은 [spec/spec_docx_웹편집.md](../spec/spec_docx_웹편집.md).)

## 패키지

- 본문 파트는 `_rels/.rels` 의 `…/officeDocument` 관계로 찾는다(보통 `word/document.xml`). styles·numbering 은
  `word/_rels/document.xml.rels` 의 Type 끝(`/styles`, `/numbering`)으로 찾고, Target 은 그 파트 폴더 기준 상대경로(`/` 로 시작하면 패키지 루트).
  `stylesWithEffects` 관계는 Type 이 `…/stylesWithEffects` 라 `/styles` 와 구분된다.
- XML 선언은 생성기마다 다르다: Word `<?xml version="1.0" … standalone="yes"?>\r\n`, python-docx `<?xml version='1.0' …?>\n`.
  lxml `tostring(root, encoding="UTF-8", xml_declaration=False)` 앞에 원본 선언(+뒤 공백)을 붙이면 3MB Word document.xml 도 **바이트 동일**하게 재직렬화된다.
- Python `zipfile.writestr(zinfo, …)` 는 넘긴 ZipInfo 를 변경한다(header_offset·크기·CRC) — 읽기용 ZipFile 의 ZipInfo 를 재사용할 땐 `copy.copy`.
  Word 는 png 를 STORED, XML 을 DEFLATED 로 저장한다.
- 새 파트 = 멤버 + 관계(새 rId) + `[Content_Types].xml`(XML 파트는 `Override PartName="/word/numbering.xml"`, 그림은 확장자 `Default`).
  numbering 파트 ContentType: `application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml`.

## 텍스트

- 런(`w:r`)은 `w:hyperlink`·`w:ins`·`w:smartTag`·`w:fldSimple`·`w:sdt/w:sdtContent`·`w:customXml`·`w:moveTo` 안에도 있다.
  `w:del`·`w:moveFrom` 안의 런은 삭제된 텍스트(`w:delText`).
- 문자 요소: `w:t`, `w:tab`(런 안 = 탭 문자; `pPr/w:tabs/w:tab` 은 탭 정의), `w:br`(type 없음/`textWrapping` = 줄바꿈, `page`/`column` = 나눔),
  `w:noBreakHyphen`(캡션 `3‑1` 의 하이픈이 이것인 경우가 많다). 앞뒤 공백 있는 `w:t` 는 `xml:space="preserve"` 필요.
- 문단 표식 서식 `pPr/rPr` 에는 `w:ins`/`w:del` 같은 수정 추적 표식이 들어갈 수 있어 런 `rPr` 로 그대로 옮기면 스키마 위반.
- `pPr` 자식은 스키마 순서가 있다: `numPr` 는 `pStyle, keepNext, keepLines, pageBreakBefore, framePr, widowControl` 뒤.
  `pPr/sectPr` 은 구역 나누기(머리글·바닥글 r:id 포함) — 문단 복제·복사 시 빼야 한다.

## 필드 (캡션 번호)

- 복합 필드: `fldChar begin` → `instrText`(여러 런에 나뉠 수 있음) → `fldChar separate` → 결과 런 → `fldChar end`. 중첩 가능.
  단순 필드: `<w:fldSimple w:instr=" SEQ Figure ">` 가 결과 런을 감싼다. 결과는 **캐시** — Word 는 열 때 SEQ 를 자동 갱신하지 않는다.
- 한국어 Word 캡션: `[그림 {STYLEREF 1 \s}‑{SEQ 그림 \* ARABIC \s 1}]`. `\s N` 은 개요 수준 ≤ N 인 **스타일**(heading N 및 그 파생) 문단에서
  다시 1부터; 문단 직접 서식 `w:outlineLvl` 은 재시작시키지 않는다(HAZID 보고서 캐시값 20개와 대조해 확인). `\r n` 재설정, `\c` 직전값 반복, `\h` 숨김.

## 개요 수준·스타일

- `w:outlineLvl` 0–8 → 수준 1–9, 9 = 본문. 문단 `pPr` → 스타일 `basedOn` 체인 순으로 상속. 한국어 Word 의 제목 스타일은
  styleId `1`,`2`… / name `heading 1`(UI 표시 "제목 1"); `Title`(제목) 스타일도 outlineLvl 0 을 가진 경우가 있다.
- pStyle 이 없으면 `w:default="1"` 인 문단 스타일(Normal)이 적용. 스타일 이름은 문서마다 대소문자가 다르다(`heading 1`/`Heading 1`) — 이름 비교는 대소문자 무시.
  다른 문서로 복사한 스타일에서는 `w:default` 를 지워야 기본 스타일이 둘이 되지 않는다.
- `w:b` 등 on/off 속성: 요소만 있으면 켜짐, `w:val` 이 `0/false/off` 면 꺼짐.
- 표 스타일 조건부 서식(`tblStylePr`, `cnfStyle` — 머리행·줄무늬 음영)은 `tcPr/w:shd` 없이도 셀을 칠한다.

## 번호 매기기

- `numPr`(문단 직접 또는 스타일 체인) → `w:num`(numId) → `w:abstractNum`(lvl 별 `start`·`numFmt`·`lvlText` `%1.%2.`). `numId 0` = 번호 없음.
  `w:num` 의 `lvlOverride/startOverride`·`lvlOverride/lvl` 이 추상 정의를 덮는다. `numStyleLink` 추상번호는 수준 정의 없이 목록 스타일의 numPr 을 따른다.
- numbering.xml 은 모든 `abstractNum` 이 모든 `num` 보다 앞에 와야 한다. Word 는 목록을 `w:nsid` 로 식별 — 복사한 abstractNum 에는 새 nsid.
- override 없는 `w:num` 들이 같은 abstractNum 을 가리키면 번호가 이어진다(Word '번호 매기기 계속'), 재시작은 `startOverride` 를 가진 새 num.
- Symbol/Wingdings 글머리 문자는 PUA `U+F0xx`(예 `U+F0B7`=•, `U+F09F`, `U+F0A7`=▪)로 저장된다.

## 표

- `w:vMerge` 의 `w:val` 이 없으면 `continue`(시작은 `restart`). `w:gridSpan` 가로 병합, `trPr/w:gridBefore` 만큼 행이 오른쪽에서 시작.
- 행·셀도 `w:sdt`/`w:customXml` 로 감싸질 수 있다. 셀(`w:tc`)은 반드시 `w:p` 로 끝나야 한다(표로 끝나면 Word 오류).
- 행 끼우기(2026-10-29 `insert_rows` 에서 확인): 세로 병합 칸이 지나는 행의 `w:tr` 을 복사하면 이어짐(`w:vMerge` val 없음) `w:tc`
  도 같이 복사돼 그 칸이 저절로 늘어난다. 1행 칸을 늘리려면 원래 칸에 `vMerge val=restart`, 복사 행 칸을 빈 `w:p` 하나짜리 이어짐 칸으로.
- python-docx `_Cell.merge()` 는 합치는 칸들의 문단을 모두 이어 붙인다(빈 칸도 빈 문단으로 남아 글이 `"공동기관

"`).

## 그림·바이너리

- 그림: `w:drawing` → `wp:inline`/`wp:anchor` → `a:graphic/…/pic:pic/pic:blipFill/a:blip r:embed`(내부 관계, Type `…/image`) 또는 `r:link`(외부).
  크기 `wp:extent cx/cy` 는 EMU(1mm = 36000, 1in = 914400). `wp:docPr id` 는 문서 안에서 유일해야 한다.
- 복사 시 중복되면 안 되는 고유 id 속성: `w14:paraId`·`w14:textId`(문단), `wp14:anchorId`·`wp14:editId`(그림), 책갈피 `w:id`/`w:name`.
- 차트 `c:chart r:id`(graphicData 안), OLE `w:object`(`o:OLEObject r:id`), 다이어그램 `dgm:relIds r:dm…`, 그림 글머리표 `numPicBullet` 은 별도 파트를 참조.
  도형은 `mc:AlternateContent`(Choice=`w:drawing`, Fallback=VML `w:pict`)로 감싸져 있어 한쪽만 지우면 빈 껍데기가 남는다.

## 서식 — 유효값 해석·쓰기 (2026-10-28, `app/docx_format.py` 구현에서 확인)

- 상속 순서(구체→일반): 직접 `rPr` → `rStyle` 체인 → `pStyle` 체인(`basedOn`) → `w:docDefaults`(`rPrDefault/rPr`, `pPrDefault/pPr`) → Word 기본값.
  (표 스타일 `tblStyle` 의 pPr/rPr·조건부 서식은 docDefaults 와 pStyle 사이에 끼지만 여기선 무시.) `pStyle` 이 없으면 기본 문단 스타일.
  → 2026-11-08 NewFileManager 실측으로 보탬: 번호 수준 pPr 이 직접 서식 다음에 끼고, 표 스타일은 **기본** 문단 스타일보다 이긴다 — 아래 「Word 16 PDF …」 절의
  「번호 수준의 문단 속성」·「표 스타일」.
- `w:sz`/`w:szCs` 는 반 포인트(22 = 11pt). 체인 어디에도 없으면 Word 는 10pt.
- `w:rFonts` 는 **속성 단위**로 상속(직접 ascii 만, 스타일이 eastAsia 를 줄 수 있음). 같은 요소에서 `*Theme` 속성(`eastAsiaTheme`, `asciiTheme`, `hAnsiTheme`, `cstheme`)이
  이름 속성보다 우선. 테마 참조 `minorEastAsia`/`majorHAnsi`… → `word/theme/theme1.xml`(문서 rels Type `…/theme`) `a:fontScheme/a:minorFont|majorFont`
  의 `a:ea`/`a:latin`/`a:cs typeface`. `a:ea typeface=""` 가 흔하다 — 한국어 문서는 `a:font script="Hang"`(보통 `맑은 고딕`).
- `w:color` 는 `w:themeColor`(+`themeShade/themeTint`)가 있으면 그게 이기고 `w:val` 은 캐시. 색을 바꿀 땐 theme 속성을 지운다. `auto` = 자동색.
  셀 `w:shd` 도 `themeFill` 이 `fill` 을 이긴다. `w:u w:val="none"` = 밑줄 없음.
- `w:ind`·`w:spacing` 도 속성(묶음) 단위 상속. `leftChars`/`firstLineChars`/`hangingChars`(1/100 글자), `beforeLines`/`afterLines`(1/100 줄)는
  0 이 아니면 트윕 값보다 우선 — 그래서 Word 는 스타일의 글자 단위를 덮을 때 `w:leftChars="0" w:left="567"` 처럼 0 을 함께 쓴다.
  `hanging` 이 있으면 `firstLine` 무시. Word 는 `beforeLines="100"` 과 함께 `before="240"`(1줄=12pt)을 같이 적는다.
- 줄간격: `w:line` + `w:lineRule`(없으면 `auto`). `auto` 는 240 분의 1 줄(276 = 115%, 360 = 150%), `exact`/`atLeast` 는 트윕(고정 높이).
- `w:jc`: `both` = 양쪽, `distribute` = 배분, strict 문서는 `start`/`end`(= left/right).
- 스키마 자식 순서(어기면 Word 오류): `pPr` … `spacing, ind, contextualSpacing, mirrorIndents, suppressOverlap, jc, …, outlineLvl, divId, cnfStyle, rPr, sectPr, pPrChange`;
  `rPr` `rStyle, rFonts, b, bCs, i, iCs, …, vanish, webHidden, color, spacing, w, kern, position, sz, szCs, highlight, u, …, lang, eastAsianLayout, specVanish, oMath, rPrChange`
  (문단 표식 `pPr/rPr` 은 맨 앞에 `ins, del, moveFrom, moveTo`); `tcPr` `cnfStyle, tcW, gridSpan, hMerge, vMerge, tcBorders, shd, noWrap, tcMar, textDirection, tcFitText, vAlign, …, tcPrChange`;
  `tcMar` `top, start|left, bottom, end|right`.
- 구역 나누기는 대부분 문단 `pPr/sectPr` 에 있다(HAZID 보고서: 10개 구역 중 9개, 마지막만 `body/sectPr`). 문단 서식을 통째로 바꿀 때 그 문단의 sectPr 은 남겨야 한다.
- 번호: 스타일이 번호를 주는 문단(python-docx 기본 템플릿 `List Number` 등)은 `pStyle` 을 바꾸면 번호가 사라진다 — 유지하려면 직접 `numPr`(ilvl+numId)을 박고,
  새 스타일이 번호를 줄 때 끄려면 `numId 0`.
- 목차(`toc N`) 항목은 `w:hyperlink` 안 런이고 `rStyle`=하이퍼링크(파랑·밑줄) — 첫 런 글자모양이 하이퍼링크 모양으로 나온다.
- 셀: 채우기 `tcPr/w:shd w:val="clear" w:color="auto" w:fill="RRGGBB"`(`fill="auto"` = 없음, 직접 지정이면 표 스타일 음영도 덮음), 세로 정렬 `w:vAlign`(없으면 top).
  여백 `tcPr/w:tcMar` → `tblPr/w:tblCellMar` → 표 스타일(`tblStyle`, 없으면 `w:default="1"` 인 table 스타일)의 `tblPr/tblCellMar` → Word 기본 좌우 108 트윕(0.19cm)·상하 0.
  `w:w` 는 `w:type="dxa"`(트윕), `nil` = 0.
- 들여쓰기: `w:ind hanging` 은 첫 줄을 `left` 보다 hanging 만큼 왼쪽에 둔다(CSS `text-indent` 음수와 같은 뜻) —
  hwpx 내어쓰기와 반대([HWPX_포맷.md](HWPX_포맷.md) paraPr 여백).
- 용지: `w:sectPr/w:pgSz w h`(트윕, `w:orient` 와 무관하게 실제 방향 값), `w:pgMar top bottom left right header footer gutter` —
  top/bottom 은 본문까지의 거리(머리말은 그 안, `header` 는 용지 끝~머리말 거리), 음수 = 고정(머리말이 밀어도 본문 시작 불변),
  gutter 는 왼쪽에 더해진다. 구역 정보는 구역 마지막 문단의 `w:pPr/w:sectPr`, 마지막 구역은 `w:body/w:sectPr`.
  python-docx `Document.add_section()` 은 앞 구역의 sectPr 를 마지막 글 문단이 아니라 **새 빈 문단**(`w:p/w:pPr/w:sectPr`)에 달아 붙인다 —
  시험 문서에서 「구역 끝 문단」은 그 빈 문단이다(2026-10-31 확인).
  요소 하나만 가로 쪽으로: 앞에 원래 sectPr 사본을 단 빈 문단, 뒤에 `pgSz` w/h 교환 + `w:orient="landscape"`·`w:type` 없음
  (= 새 쪽) 사본을 단 빈 문단 — 그 뒤 내용은 원래 구역 sectPr 이 계속 맡는다. `w:` 접두로 만든 문단은 lxml 이 문서의
  기존 xmlns 선언을 재사용한다(`ns0:` 생기지 않음).
- 표 크기: 열 너비 `w:tblGrid/w:gridCol w:w`(트윕) — 칸 너비 = 걸친 gridCol 합, 행 높이 `w:trPr/w:trHeight w:val`(+ `hRule` exact/atLeast),
  표 정렬 `w:tblPr/w:jc`. `w:trHeight` 가 없는 행은 Word 가 내용 높이로 정한다(자동) — 한글 `cellSz` 처럼 모든 행에 값이 있지 않으므로 행 높이를
  같게·맞출 때는 값이 있는 행만 기준이 된다(2026-11-01 매직 브러쉬 DOCX). 기술수요조사서.docx 는 20행 중 6행만 trHeight(라벨 행). python-docx
  `table.columns[k].width = Twips(n)` 은 `gridCol` 만 바꾸고 칸의 `tcW`(기본 = 표 너비 ÷ 열 수)는 그대로라 둘이 어긋난 파일이 된다.
- lxml: 따로 파싱한 `<w:fmt xmlns:w=…>` 조각의 요소를 deepcopy 해 문서에 넣어도 중복 xmlns 선언이 생기지 않는다(같은 prefix·URI 재사용).
- 빈 문단·빈 런(2026-10-31, 표 서식 정리): 글 런(`w:t` 등)이 없는 문단에서 Word 가 새로 치는 글의 모양은 **문단 끝 표식** `w:pPr/w:rPr` 이다. python-docx
  `add_run("")` 은 `w:t` 없이 `w:rPr` 만 든 빈 런을 남긴다(Word 는 저장할 때 보통 지움) — 서식을 읽을 때 글 런이 없으면 빈 런 → 끝 표식 순으로 본다.
  장평 `w:rPr/w:w w:val`(%), 자간 `w:rPr/w:spacing w:val`(트윕, 절대값 — 장평과 곱하지 않음). `w:trHeight w:hRule="atLeast"` 는 Word 가 내용보다 행을 줄이지 않는
  최소 높이(`exact` 는 잘라냄) — 행 높이를 쓸 때 안전한 쪽. `w:trPr` 자식 순서: cnfStyle, divId, gridBefore, gridAfter, wBefore, wAfter, cantSplit, trHeight,
  tblHeader, tblCellSpacing, jc, hidden, ins, del, trPrChange.

## 열 때 Word 가 바깥에서 가져오는 것 (2026-11-01, 렌더 하드닝 `app/render_anchors.py` `strip_external` 에서 정리)

비신뢰 docx 를 Word COM 으로 열 때 원격 요청·모달 대화상자가 생기는 자리. 앱의 적용은 [spec/spec_병합.md](../spec/spec_병합.md) §2-4 「렌더 하드닝」.
- 서식 파일: `word/_rels/settings.xml.rels` 의 attachedTemplate 관계 + settings 의 `<w:attachedTemplate r:id>`.
- 프레임: `word/_rels/webSettings.xml.rels` + `w:frameset/w:frame/w:sourceFileName r:id`. 하위 문서: document 관계 + `<w:subDoc r:id>`.
- 연결 그림: image 관계 `TargetMode="External"` 을 `a:blip r:link` 또는 `v:imagedata r:id`·`r:href`·`o:relid`(VML `v:fill` 도)로 참조 — `r:embed`·`r:link` 는
  둘 다 선택이라 한 그림에 임베드와 연결이 같이 있을 수 있다. 연결 OLE: `<o:OLEObject Type="Link" r:id UpdateMode="Always">`. 차트 외부 데이터: `c:externalData r:id`.
- 편지 병합: settings 의 `<w:mailMerge><w:dataSource r:id>` — 열 때 SQL 확인 대화상자. `<w:updateFields w:val="true"/>` — 열 때 필드 업데이트 확인 대화상자
  (INCLUDETEXT 같은 필드가 바깥 글을 끌어옴).
- 하이퍼링크(`…/hyperlink` 관계, External)는 누를 때만 가져온다. 쓰이지 않는 관계는 무해하지만, **없는 관계를 가리키는 r:id 는 Word 가 손상 파일로 본다**
  — 관계를 지우면 참조도 같이 지우거나, 관계를 남기고 Target 만 없는 상대 경로로 바꾼다.
- `Application.AutomationSecurity`(3 = msoAutomationSecurityForceDisable, 매크로 끔)는 인스턴스마다이고 저장되지 않는다. `Options.UpdateLinksAtOpen` 은 사용자별로
  저장되므로 렌더 인스턴스에서 바꾸면 그 계정의 Word 전체에 남는다(그래서 건드리지 않음). `Documents.Open(ConfirmConversions=False, ReadOnly=True,
  AddToRecentFiles=False, NoEncodingDialog=True)` 는 변환·인코딩 대화상자와 최근 파일 기록을 막는다.

구현 검토(2026-11-01, astra·fable)에서 더한 자리 — 파일 이름·한 자리만 보면 빠져나간다.
- **settings 파트는 이름이 아니라 관계로 찾는다**: OPC 에서 Word 는 document 관계(Type `…/settings`)의 Target 을 읽는다 — `word/settings.xml` 은 관례일 뿐이라
  Target 을 `options.xml`·`/word/options.xml`·`../cfg/opts.xml` 로 바꿔도 된다(astra 재현: 고정 이름만 보던 코드가 `w:updateFields` 를 남김). Target 은 원본 부분 폴더
  기준 상대 경로, `/` 로 시작하면 패키지 뿌리 기준이고 부분 이름은 대소문자·% 인코딩을 가리지 않는다. 용어집(`glossaryDocument`)도 자기 settings 를 가질 수 있다.
- **`mc:AlternateContent`**(settings·본문 어디서나): `mc:Choice Requires="…"` 가지들과 `mc:Fallback` — Word 는 아는 가지 하나를 고르므로, 미리 막으려면 모든 가지 안을
  본다(자식만 보면 `mc:Choice` 안의 `w:updateFields` 가 남는다). 빈 가지도 성립한다.
- **VML 은 관계 없이 주소를 직접 적을 수 있다**: `v:imagedata`·`v:fill`·`v:image` 의 `src`, `o:href`·`o:althref`(그림 원래 자리), `v:shape href`(누를 때 — 하이퍼링크).
  값이 직접 URL(`http`·`https`·`ftp`·`file`)이나 UNC(`\\server\…`, `//server/…`)면 열 때 가져올 수 있다 — 속성만 떼면 요소·그림 자리는 그대로 성립. 연결된 네트워크
  드라이브 문자(`Z:\…`)도 결국 네트워크라 같이 본다. 그림 글머리(`w:numPicBullet`)는 numbering 파트 안 VML 이라 본문 밖 파트도 봐야 한다.
- **바깥을 부르는 필드 코드**: `INCLUDEPICTURE`(`\d` = 문서에 그림을 저장하지 않음 → 그릴 때 가져옴), `INCLUDETEXT`, `LINK`(`\a` 자동 갱신), `DDE`·`DDEAUTO`(열 때
  다른 프로그램을 부름), 옛 이름 `INCLUDE`·`IMPORT`. 복합 필드는 `w:fldChar` begin … separate … end 이고 명령은 그 사이 런의 `w:instrText` 를 이은 것 — 런마다 나눠
  적을 수 있어(`INCLUDEP` + `ICTURE "http://ev` + `il…"`) 한 요소씩 문자열을 찾으면 놓친다. 필드는 안길 수 있고(안긴 필드 결과가 바깥 명령의 일부), 필드 종류·대상을
  안긴 필드 결과로 만들 수도 있다. 단순 필드는 `w:fldSimple/@w:instr`. 명령만 무해한 것(`QUOTE ""`)으로 바꾸면 갱신 전까지 캐시된 결과(begin~separate~end 사이 결과
  런)가 그대로 보인다. `w:fldChar/@w:dirty`·`w:fldSimple/@w:dirty` 는 그 필드만의 「열 때 갱신」(settings `w:updateFields` 와 같은 확인 창).
- **하이퍼링크 관계**(`file:///\\server\…`·UNC 포함)는 열 때 가져오지 않는다(누를 때만) — 다만 Word 가 관계를 참조한 요소로 쓰는지 Type 으로 가리는지는 확인하지 않았으므로,
  hyperlink Type 관계를 `a:blip r:link` 같은 그림·데이터 자리에서 참조하면 하이퍼링크로 믿지 않는다(앱은 `w:hyperlink`·`a:hlinkClick`·`a:hlinkHover`·`a:hlinkMouseOver`
  밖의 참조면 뺀다). TargetMode 가 없거나 Internal 인데 Target 이 직접 URL·UNC 인 관계도 같은 이유로 바깥으로 본다.
- 확인하지 않은 것(Word 를 띄우지 않음): `w:altChunk r:id`(HTML·MHT·RTF·docx 부분을 열 때 가져와 붙임 — HTML 안 `<img src="http…">` 를 가져올 수 있음),
  `DATABASE`(`\c` 연결)·`RD` 필드(갱신할 때만 부름), 사용자 옵션 「인쇄 전 필드 업데이트」가 `SaveAs2(FileFormat=17)`(PDF)에도 걸리는지.

## Word 16 PDF 출력·다시 저장에서 확인한 것 (2026-11-08, NewFileManager — 예제 기술수요조사서.docx·HAZID 보고서 72쪽·AIP 서식)

COM 사용법·렌더 하드닝은 위 「열 때 Word 가 바깥에서 가져오는 것」, 구현은 `app/pdf_render.py`·`app/docx_harden.py`.
- **PDF**: `Documents.Open(…, ReadOnly=True)` → `SaveAs2(path, FileFormat=17)`. 용지는 `w:pgSz` 그대로(기술수요조사서.docx 는 Letter 612×792pt).
  글꼴은 TrueType 부분 글꼴로 이름이 남는다(`BCDEEE+MalgunGothic`, `MalgunGothicBold`, `ArialMT`) — 한글 PDF 의 이름 없는 Type3·「????」 와 달리 가족 이름으로 맞출 수 있다.
  PyMuPDF 로 읽으면 **줄마다 끝에 빈칸 글자**가 하나 붙는다(`'31.50 m '`) — 같은 높이 오른쪽 칸 글의 앞 공백으로 잘못 세지 않게 떼야 한다.
  Symbol·Wingdings 글머리는 PDF 에도 대개 PUA 글자 그대로다(U+F09F, 글꼴 `Wingdings-Regular` — HAZID) — 단 Wingdings 「l」(F06C)은 U+26AB ⚫ 로 나왔다(AIP 서식).
  머리말(가로 A4, 쪽 높이 595pt)은 아래끝이 ≈50pt(쪽 높이의 8.4%) — 쪽 높이 비율로 머리말 띠를 잡으면 가로 쪽에서 모자란다(머리말 자리는 물리 거리).
  번호(`w:suff` tab) 뒤 탭은 빈칸 글자 하나로 읽힌다(「1.」+「 」+「서론」).
- **다시 저장**: `SaveAs2(path, FileFormat=16)`(docx). 본문이 표로 끝나면(`w:tbl` 바로 뒤 `body/w:sectPr`) **빈 문단을 하나 더해** 저장한다 — 문단 글 차례를 견줄 때 빈 문단은 뺀다.
- **번호 이어 세기**: 같은 abstractNum 을 가리키는 `w:num` 들은 `lvlOverride/startOverride` 가 있어도 번호를 잇고, startOverride 는 **그 w:num 을 처음 쓴 문단의 수준만**
  다시 센다(HAZID: numId 9 로 「1.」~「5.」, numId 12 = 같은 abstractNum + 모든 수준 startOverride 1, 처음 쓴 문단이 수준 1 → Word 는 「5.1.」, 뒤의 수준 0 은 「6.」).
  위 「번호 매기기」의 「재시작은 startOverride 를 가진 새 num」은 그 num 을 처음 쓴 수준에서만 맞다(HAZID 1건 실측).
- **번호 수준의 문단 속성**: abstractNum `w:lvl/w:pPr`(들여쓰기 `w:ind`)가 문단에 걸린다 — 직접 서식 다음·문단 스타일 앞 차례로 견주니 HAZID 헤딩 첫 줄 x 가
  83/83 맞음(번호 수준을 빼면 7/83).
- **표 스타일**(AIP 서식 5개·HAZID, 2026-11-08): 표 칸 안 문단에 표 스타일의 pPr·rPr·tcPr(음영)이 걸리고, **기본 문단 스타일보다 이긴다**(따로 고른 문단 스타일에는
  지는 것으로 두었다 — 미실측). 조건부 서식(`tblStylePr`)은 겹칠 때 모서리(nw·ne·sw·se) → 머리·끝 행 → 첫·끝 열 → 가로 줄무늬 → 세로 줄무늬 차례로 이긴다고 두고
  견주어 맞았다. Word 는 칸·문단에 `w:cnfStyle`(어느 조건부 서식이 걸렸는지 캐시)을 저장하는데, **모서리 칸 표시(firstRowFirstColumn=1)는 firstRow=0 이어도 머리 행
  모양으로 찍는다**(AIP: 흰 굵은 글). cnfStyle 의 val 비트 차례가 속성 차례와 다른 저장본이 있었다(속성을 믿을 것).
- **자동 글자색**: 색이 없는(auto) 글은 칸 음영이 어두우면 흰색으로 찍힌다. 문턱 = 밝기 `(76R + 151G + 29B) >> 8 ≤ 62`(LibreOffice `Color::IsDark` 가 MS Office 와 맞춘
  값) — 빨강 FF0000(75)은 검은 글 그대로(HAZID 위험도 칸), 남색 002060 은 흰 글.
- **목차 하이퍼링크**: `toc N` 문단의 `w:hyperlink` 안 런은 `rStyle`=Hyperlink(파랑 0000FF·밑줄)인데 Word 는 그 글자 스타일을 그리지 않고 목차 문단 모양(HAZID: 262626)으로 찍는다.
- **XML 바이트**: Word 는 속성 값 안 줄 바꿈을 16진 참조 `&#xA;`(VML `o:gfxdata` 등 — document.xml·header 안), lxml 은 `&#10;` 으로 쓴다. 손으로 고친 패키지는
  뿌리 요소 뒤에 줄 바꿈이 있을 수 있다(lxml `tostring` 은 버림). docProps·customXml 은 lxml 로 다시 쓰면 빈 요소(`<x></x>` → `<x/>`)·속성 차례·`" />` 빈칸이
  바뀐다 — 바이트를 지키려면 고치지 않는 부분은 다시 쓰지 않는다.
- **COM 프로세스**: `DispatchEx("Word.Application")` 은 부를 때마다 WINWORD.EXE 를 새로 띄운다 — 출력 자식 프로세스마다 하나. 매크로·대화상자를 끈 인스턴스
  (`AutomationSecurity=3`·`DisplayAlerts=0`)로 열면 이 PC(Word 16)에서 확인 창 없이 돌았다. 시간: 1쪽 3.8~6.7s(Word 를 처음 띄우는 몫 포함 여부),
  72쪽 17.6~17.8s(두 번 잼). 출력 자식을 강제로 끝내면(서버 프로세스째 종료) `Quit()` 을 못 불러 `/Automation` WINWORD.EXE 가 남는다.
