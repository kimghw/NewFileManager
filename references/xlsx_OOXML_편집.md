# xlsx(SpreadsheetML) 를 XML 로 직접 고칠 때 알아 둘 것

쓰는 곳: [spec_엑셀편집.md](../spec/spec_엑셀편집.md) · `app/xlsx_doc.py`. 2026-11-26 구현하며 확인한 것(openpyxl 로 다시 읽어 시험).

## 칸 값

- 글 칸은 공유 문자열 표(`sharedStrings.xml`)를 건드리지 않고 **인라인 글** `<c t="inlineStr"><is><t>…</t></is></c>` 로 쓸 수 있다 — 엑셀은 저장할 때 공유 표로 옮긴다. 앞뒤 빈칸 · 줄 나눔이 있으면 `<t xml:space="preserve">`.
- 공유 표의 `count` · `uniqueCount` 가 실제 쓰임과 달라도 엑셀이 연다(안 쓰는 문자열이 남아도 됨).
- 날짜는 일련번호(1900 체계 = 1899-12-30 부터의 날 수 · `workbookPr date1904` 면 1904-01-01) + 날짜 표시 형식. 표시 형식 번호 14~22 · 45~47 이 붙박이 날짜 · 시각이고, 한국어 로캘의 27~36 · 50~58 도 날짜다.
- 수식은 `=` 없이 `<f>SUM(A1:A3)</f>` · 함수 이름은 영어. 계산값 `<v>` 를 안 적어도 된다.

## 수식을 고치거나 지울 때

- `xl/calcChain.xml` 이 **수식이 없어진 칸을 가리키면 엑셀이 「복구」 창을 띄운다** — 수식을 바꾸는 편집을 하면 calcChain 을 빼고(워크북 관계 · `[Content_Types].xml` 의 Override 도), `workbook.xml` 의 `<calcPr fullCalcOnLoad="1"/>` 로 열 때 다시 계산하게 한다(엑셀이 calcChain 을 다시 만든다). `calcPr` 자리는 `definedNames` 뒤(없으면 `sheets` 뒤).
- **공유 수식**(`<f t="shared" ref="B1:B3" si="0">A1*2</f>` + 무리의 다른 칸은 `<f t="shared" si="0"/>`): 첫 칸(글이 있는 칸)을 지우거나 바꾸면 나머지가 기댈 글이 없어 깨진다 — 고치기 전에 칸마다 수식으로 풀어 둔다(상대 참조를 칸의 거리만큼 옮김 · `$` 붙은 쪽은 그대로).
- 배열 수식(`t="array" ref=…`) 칸은 범위째 다뤄야 한다.

## 행을 넣고 지울 때 함께 옮길 것

칸 `r` · 행 `r` · `mergeCells` · `dimension` · 모든 시트의 수식(다른 시트가 `'시트'!A1` 로 가리키는 것 포함) · `definedName`(인쇄 영역 등 — 늘 시트 이름이 붙음) · `conditionalFormatting@sqref` 와 그 `formula` ·
`dataValidation@sqref` 와 `formula1/2` · `hyperlink@ref` · `autoFilter@ref` · 표(`xl/tables/tableN.xml` 의 `ref` 와 그 안 `autoFilter`) · 메모(`comments` 의 `ref`) · 그림 자리(`xl/drawings/drawingN.xml` 의 `xdr:from/xdr:row` · `xdr:to/xdr:row` — **0 부터**) ·
`rowBreaks/brk@id` · `selection@sqref/activeCell`. 지운 행만 가리키는 수식 참조는 `#REF!`(엑셀과 같음) · 범위는 줄인다 · 넣은 자리가 범위 안이면 범위가 늘어난다. 옮기지 않는 것(엑셀이 고칠 수 있게 두는 것): 레거시 메모 상자(vml) 자리 · `extLst` 안의 x14 범위.

## 서식을 화면에 그릴 때

- 테마 색 번호는 **0 = lt1 · 1 = dk1 · 2 = lt2 · 3 = dk2** 로 clrScheme 의 차례(dk1, lt1, …)와 앞 둘씩이 뒤바뀐다 · 4~9 = accent1~6. `tint` 는 HLS 의 밝기를 바꾼다(음수 = l·(1+tint) · 양수 = l·(1−tint)+tint).
- 옛 색 번호(`indexed`)는 64 색 표 · 64 = 시스템 글자색 · 65 = 시스템 바탕색.
- 열 너비(글자 수) → px ≈ 너비 × 7 + 5(기본 8.43 → 64px) · 행 높이(pt) → px = pt × 4/3(기본 15pt = 20px).
- 틀 고정 = `sheetView/pane@state="frozen"` 의 `xSplit` · `ySplit`(고정한 열 · 행 수).
