"""엑셀 수식 글의 문법·계산(`app/table_formula.py` — 화면 격자 엔진의 파이썬 짝, spec_헤딩_추출 ② §14 「LLM 수식 판정」): 문법 · 가리키는 주소 · 계산 · 채우기 · 견줄 꼴."""
import pytest

from app import table_formula as F


def val(grid):
    return lambda r, c: grid.get((r, c))


def test_addresses():
    assert F.pos("E26") == (25, 4) and F.pos("$aa$1") == (0, 26) and F.pos("E0") is None and F.pos("1E") is None and F.pos("") is None
    assert F.a1(25, 4) == "E26" and F.col_letter(26) == "AA" and F.col_index("AB") == 27


def test_parse_shapes_and_rects():
    t = F.parse("=E10+SUM(E12:E13)+$K$3*2")
    assert F.rects(t) == [(9, 4, 9, 4), (11, 4, 12, 4), (2, 10, 2, 10)]
    assert F.parse("=sum(e3:e4)")[1] == "SUM" and F.rects(F.parse("=SUM(J3:E3)")) == [(2, 4, 2, 9)]  # 대소문자 · 거꾸로 적은 범위
    assert F.parse("=(E24/(E3+E5))*100")[0] == "bin" and F.parse('=IF(A1>0,"있음","")')[1] == "IF" and F.parse("=-A1%")[0] == "un"
    assert F.rects(F.parse('="E3"&A1')) == [(0, 0, 0, 0)]  # 글 상수 안의 「E3」 은 주소가 아님
    for bad, why in (("E3+E4", "「=」"), ("=", "빈 수식"), ("=E3+", "끊겼"), ("=VLOOKUP(A1,B1:C2,2)", "모르는 함수"), ("=E3 E4", "남은"), ("=SUM(E3:)", "끝 주소"),
                     ("=합계+1", "이름"), ("=(E3", "「)」"), ("=E3#", "모르는 글자"), ("=" + "1+" * 300 + "1", "너무 깁니다")):
        with pytest.raises(F.FormulaError) as err:
            F.parse(bad)
        assert why in str(err.value), (bad, str(err.value))


def test_evaluate_like_the_grid_engine():
    g = {(0, 0): 10.0, (1, 0): 5.0, (2, 0): None, (3, 0): "글", (0, 1): 3.0}
    ev = lambda s: F.evaluate(F.parse(s), val(g))  # noqa: E731
    assert ev("=A1+A2*2") == 20 and ev("=(A1+A2)*2") == 30 and ev("=A1/A2") == 2 and ev("=2^3^2") == 512 and ev("=-A1+50%") == -9.5
    assert ev("=SUM(A1:A4)") == 15 and ev("=SUM(A3:A3)") is None and ev("=AVERAGE(A1:A2)") == 7.5 and ev("=MAX(A1:B1)") == 10 and ev("=COUNT(A1:A4)") == 2 and ev("=COUNTA(A1:A4)") == 3
    assert ev("=A3+A3") is None and ev("=A1+A3") == 10 and ev("=A1*A3") is None and ev("=A1/A3") is None  # 빈 값: 더하기는 0, 곱·나누기는 빈 값
    assert ev("=ROUND(A1/B1,1)") == 3.3 and ev("=ROUND(2.5,0)") == 3 and ev("=ROUNDDOWN(-2.57,1)") == -2.5 and ev("=ROUNDUP(2.01,0)") == 3 and ev("=INT(-0.5)") == -1
    assert ev("=MOD(A1,B1)") == 1 and ev("=POWER(B1,2)") == 9 and ev("=ABS(A2-A1)") == 5 and ev("=SQRT(B1*B1)") == 3
    assert ev('=IF(A1>A2,"큼","작음")') == "큼" and ev("=IF(AND(A1>0,NOT(A2>9)),1,0)") == 1 and ev("=OR(A3,A1=10)") is True and ev('=A1&"원"') == "10.0원"
    for bad in ("=A1/0", "=A1/(A2-5)", "=MOD(A1,0)", "=SQRT(-1)", "=A4+1"):
        with pytest.raises(F.FormulaError):
            ev(bad)
    # 병합 칸은 한 번만 — cells 가 범위의 칸 자리를 준다
    spots = lambda r0, c0, r1, c1: [(0, 0)]  # noqa: E731 — A1:A2 가 한 칸으로 합쳐짐
    assert F.evaluate(F.parse("=SUM(A1:A2)"), val(g), spots) == 10


def test_shift_like_fill():
    assert F.shift("=E23+E24", 0, 6) == "=K23+K24" and F.shift("=SUM(E3:E4)+E5", 2, 1) == "=SUM(F5:F6)+F7"
    assert F.shift("=$E$3+E$3+$E3+E3", 1, 1) == "=$E$3+F$3+$E4+F4"                 # 「$」 붙은 쪽은 그대로
    assert F.shift('=IF(E3>0,"E3 초과",E4)', 1, 0) == '=IF(E4>0,"E3 초과",E5)'    # 글 상수 안은 안 건드림
    assert F.shift("=LOG10(E3)", 1, 0) == "=LOG10(E4)"                            # 함수 이름의 숫자는 주소가 아님(문법 검사는 따로)
    assert F.shift("=A1+B2", -1, 0) is None and F.shift("=A1", 0, 3, rows=10, cols=3) is None and F.shift("=A1", 0, 2, rows=10, cols=3) == "=C1"


def test_canon():
    assert F.canon("= sum( e3 : e4 ) + $E$5") == "=SUM(E3:E4)+E5" and F.canon('=if(a1>0, "가 나", b1)') == '=IF(A1>0,"가 나",B1)'
    assert F.canon("=E23+E24") == F.canon("=e23 + e24")
