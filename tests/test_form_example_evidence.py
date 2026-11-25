import io

from PIL import Image

from app import form_example_evidence as E, guide_write
from tests.test_form_slots import box, para
from tests.test_guide_write import T


class Pictures:
    def media(self, name):
        if name == "bad.bmp":
            return b"damaged bitmap"
        buf = io.BytesIO()
        Image.new("RGB", (17, 13), "orange").save(buf, "BMP")
        return buf.getvalue()


def pic(id_, media="shot.bmp"):
    return {"type": "image", "id": id_, "media": media}


def test_embedded_and_standalone_examples_reach_model_with_pixels_and_context():
    h = para("chapter", "목표 관리")
    normal = T("entry", ["구분", "예시"], [para("note", "예시를 참고하여 기재"), pic("diagram")])
    normal["cells"][0]["blocks"][0]["format"] = {"font": "돋움", "sizePt": 11, "align": "center"}
    sample = T("sample", ["", "≪ 작성을 위한 샘플자료 ≫", ""], [T("row", ["보고서 표지"], [pic("screenshot")])])
    nested = box("next", [para("label", "다음 연도 목표"), para("slot", ""), sample])
    blocks = [h, normal, para("title", "<작성 예시>"), para("blank", ""), T("named", ["목표", "내용"], [pic("example")]), nested]
    graph = {"nodes": [{"role": "heading", "area": "body", "para": h["id"], "depth": 1}]}
    refs = {r["id"]: r for r in E.evidence(Pictures(), blocks, graph)}
    assert set(refs) == {"title", "sample", "diagram"}
    assert refs["title"]["head"] == "chapter" and "앞쪽 표 [entry]" in refs["title"]["text"] and "돋움 · 11pt" in refs["title"]["text"]
    assert refs["sample"]["head"] == "next" and "바깥 표 [next]" in refs["sample"]["text"] and "표 [row]" in refs["sample"]["text"]
    assert "1행 2열" in refs["sample"]["text"] and "첨부 그림 1" in refs["sample"]["text"] and "보고서 표지" in refs["sample"]["text"]
    assert refs["diagram"]["name"] == "양식 내 그림"
    for ref in refs.values():
        assert not ref["cut"] and len(ref["images"]) == 1 and ref["images"][0]["media"] == "image/png"
        with Image.open(io.BytesIO(ref["images"][0]["data"])) as im:
            assert im.size == (17, 13) and im.convert("RGB").getpixel((0, 0)) == (255, 165, 0)
    guides = {key: [{"src": "doc", "text": "작성 지침"}] for key in ("named", "sample", "row", "entry")}
    places = {p["id"]: p for p in guide_write.places(blocks, graph, {"heads": {}, "tables": guides})}
    # 그림이 든 일반 표는 별도 자리로 확인할 수 있고, 헤딩만 고르면 채우기 범위에서 빠진다.
    assert set(places) == {"chapter", "entry", "next"} and places["chapter"]["tables"] == []


def test_sample_box_and_text_only_or_unreadable_examples():
    caption = para("caption", "작성 예시")
    sample_box = box("box", [para("btitle", "작성 예시"), para("blank", "")])
    blocks = [caption, para("one", "○ 추진 목표"), para("two", "  - 협력 기관별 추진 실적"), para("gap", ""), sample_box, pic("damaged", "bad.bmp")]
    by = {r["id"]: r for r in E.evidence(Pictures(), blocks, None)}
    assert "추진 목표" in by["caption"]["text"] and "협력 기관별" in by["caption"]["text"]
    assert by["damaged"]["cut"] and not by["damaged"]["images"] and "미첨부" in by["damaged"]["text"]
    assert guide_write.boxes(blocks, None) == {} and not guide_write.places(blocks, None, {"heads": {}, "tables": {"box": [{"text": "견본"}]}})
