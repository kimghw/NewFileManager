"""웹 쪽 상자 ↔ 한글 PDF 쪽 나란히 그림(쪽 나눔 눈 검토용).

python -X utf8 tools/check_pages.py [예제 이름] [쪽 번호들(쉼표)] [출력 폴더]
서버(8114)가 떠 있어야 한다. 쪽마다 <출력>/page_NN.png = 왼쪽 웹 쪽 상자, 오른쪽 한글 PDF 그 쪽(2쪽 모아 찍기면 장의 반)."""
import io
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8114"
SAMPLE = sys.argv[1] if len(sys.argv) > 1 else "연구개발계획서_양식.hwpx"
PAGES = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "1,2,12,21,31,41,66").split(",")]
OUT = Path(sys.argv[3] if len(sys.argv) > 3 else Path(__file__).resolve().parents[1] / "artifacts" / "pages")
OUT.mkdir(parents=True, exist_ok=True)
H = 900


def pdf_half(doc, mapping, page):
    sheets = mapping.get("sheets") or []
    sheet = sheets[page - 1] if page <= len(sheets) else page
    png = urllib.request.urlopen(f"{URL}/api/docs/{doc}/pdf/original/{sheet}.png?dpi=110").read()
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if mapping.get("twoUp"):
        first = sheets.index(sheet) + 1  # 그 장의 첫 쪽
        w = im.width // 2
        im = im.crop((0, 0, w, im.height) if page == first else (w, 0, im.width, im.height))
    return im


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1100, "height": 1400})
        pg.goto(URL)
        pg.wait_for_selector(".sample")
        pg.click(f".sample >> text={SAMPLE}")
        pg.wait_for_selector(".para")
        for _ in range(600):
            if "run" not in (pg.get_attribute("#summary", "class") or "") and pg.inner_text("#summary").strip():
                break
            time.sleep(0.5)
        doc = pg.evaluate("state.id")
        mapping = pg.evaluate("state.mapping")
        pg.evaluate("setZoom(1)")
        boxes = pg.eval_on_selector_all(".sheet", "els => els.map(e => +e.dataset.page)")
        gaps = pg.eval_on_selector_all(".gap-page", "els => els.map(e => +e.dataset.page)")
        print("web page boxes", len(boxes), "gap pages", gaps, "pdf doc pages", mapping and mapping["pageCount"])
        for n in PAGES:
            box = pg.query_selector(f'.sheet[data-page="{n}"]')
            if not box:
                print(n, "no web page box")
                continue
            box.scroll_into_view_if_needed()
            pg.wait_for_timeout(300)
            web = Image.open(io.BytesIO(box.screenshot())).convert("RGB")
            pdf = pdf_half(doc, mapping, n)
            web = web.resize((round(web.width * H / web.height), H)) if web.height > H else web
            pdf = pdf.resize((round(pdf.width * H / pdf.height), H))
            out = Image.new("RGB", (web.width + pdf.width + 20, max(web.height, pdf.height)), "white")
            out.paste(web, (0, 0))
            out.paste(pdf, (web.width + 20, 0))
            out.save(OUT / f"page_{n:02d}.png")
            first = box.query_selector(".para")
            print(n, "web first para:", (first.inner_text()[:40] if first else "").replace("\n", " "))
        b.close()


if __name__ == "__main__":
    main()
