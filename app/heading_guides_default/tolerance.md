# 오차(같은 서식) 판단 기준

아래 json 블록은 스크립트가 읽는 숫자 문턱의 **단일 원본**이다(서식 라벨 S 묶기와 조정의 「오차 안」 기준).
- 같은 범주(정렬·굵게·기울임·밑줄·글꼴 별칭군·색 군·첫 줄 부호·줄 간격 종류)이고 수치 차이가 모두 문턱 이하면 같은 서식 라벨로 묶는다.
- 대표(가장 많이 쓰인 서식)와만 견준다. A≈B, B≈C라고 해서 A와 C를 잇지 않는다.

```json
{
  "leadSpaces": 1,
  "leadMm": 2.5,
  "indentMm": 1.0,
  "firstLineMm": 1.0,
  "sizePt": 0.5,
  "spacePt": 2.0,
  "gapPt": 4.0,
  "lineSpacingPct": 10,
  "lineSpacingPt": 1.0,
  "ratioPct": 5,
  "spacingPct": 5,
  "fontAliases": [["돋움", "돋움체", "Dotum", "DotumChe"], ["바탕", "바탕체", "Batang", "BatangChe"], ["굴림", "굴림체", "Gulim", "GulimChe"],
                  ["한양중고딕", "HY중고딕", "HYGothic-Medium"], ["한양견고딕", "HY견고딕", "HYGothic-Extra"], ["함초롬바탕", "HCR Batang"],
                  ["함초롬돋움", "HCR Dotum"], ["맑은 고딕", "Malgun Gothic"]],
  "colors": [["#000000", null]]
}
```

- `leadSpaces` · `leadMm`: 레터 앞 빈칸 칸 수 · 폭 차이.
- `indentMm`: 왼·오른 여백, `firstLineMm`: 첫 줄 들여/내어쓰기 폭.
- `sizePt`: 글자 크기, `spacePt`: 문단 위·아래 간격, `gapPt`: 유효 간격(빈 문단 포함).
- `lineSpacingPct`: 줄 간격(%), `lineSpacingPt`: 고정·최소·여백 줄 간격(pt).
- `ratioPct` · `spacingPct`: 장평 · 자간.
- `fontAliases`: 같은 글꼴로 보는 이름 묶음.
- `colors`: 같은 색으로 보는 묶음(`null` = 자동 색).

## 오차가 아닌 것(일부러 다른 서식)
- 아래 차이는 오차로 묶지 않는다: 굵게 켬/끔 · 정렬 · 첫 줄 **부호**(내어쓰기 ↔ 들여쓰기) · 검정 ↔ 파랑(안내 글) · 별칭 묶음 밖 글꼴 · 글자 크기 2pt 이상 차이.
- 문턱 밖이지만 같은 구실(같은 단계의 보통 항목)이면 LLM이 같은 슬롯으로 보고 편차로 기록한다(조정 지침).

## 비교에서 빼는 것
- 글 없는 줄(쓸 자리)의 레터 뒤 빈칸은 비교에서 뺀다.
- 빈 문단(간격 장치)의 글꼴 이름은 비교에서 뺀다.
