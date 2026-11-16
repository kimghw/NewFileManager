"""독립 작업 내비게이션·문서 비교의 격리된 브라우저 연기 시험.

python -X utf8 tools/smoke_workspace_ui.py [출력 폴더] [--port 8115]
샘플의 별도 작업 사본만 사용한다. PDF/LLM 끔, 별도 숨김 서버를 띄우고 종료한다.
비교 B의 문서 안 S/# 번호만 바꾼 분석 fixture로 번호가 다른 같은 사슬을 검사한다.
"""
import argparse
import gzip
import json
import os
import re
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui_workspace"


def seed(folder):
    os.environ.update(NFM_WORKS=str(folder / "works"), NFM_HEADINGS=str(folder / "headings"),
                      NFM_PDF="off", NFM_RENDER=str(folder / "render"), NFM_LLM_BACKEND="off")
    sys.path.insert(0, str(ROOT))
    from app import heading_runs, server, works
    data = (ROOT / "samples" / "연구개발계획서_양식.hwpx").read_bytes()
    sessions = []
    for name in ("비교 A 연구개발계획서.hwpx", "비교 B 다른 번호.hwpx"):
        session = server.Session(name, data)
        works.create(session.id, name, "hwpx", data)
        server.DOCS[session.id] = session
        job = heading_runs.run_sync(session, 2, False)
        assert job.status == "done", job.error
        sessions.append(session)
    second = sessions[1]
    heads = heading_runs.state(second)
    first, graph = heads["stage1"], heads["stage2"]
    remap = {key: f"S{1000 + int(key[1:])}" for key in first["labels"]}
    first["labels"] = {remap[key]: {**value, "id": remap[key]} for key, value in first["labels"].items()}
    for para in first["paras"]:
        para["fmt"] = remap[para["fmt"]]
    for fmt in first["formats"].values():
        fmt["label"] = remap[fmt["label"]]
    for template in graph["templates"]:
        template["id"] += 100
        template["no"] += 100
        for slot in template["slots"]:
            slot["format"] = remap[slot["format"]]
            slot["formats"] = {remap[key]: value for key, value in slot["formats"].items()}
    for node in graph["nodes"]:
        if node.get("fmt") in remap:
            node["fmt"] = remap[node["fmt"]]
        if node.get("tplNo"):
            node["tplNo"] += 100
    for instance in graph["instances"]:
        instance["template"] += 100
    for repeat in graph["repeats"]:
        repeat["template"] += 100
    for item in graph["types"]:
        item["labels"] = {remap.get(key, key): value for key, value in item.get("labels", {}).items()}
    for adjustment in graph["adjustments"]:
        for key in ("from", "to"):
            adjustment[key] = remap.get(adjustment.get(key), adjustment.get(key))
    directory = works.folder(second.id) / "headings"
    for result, filename in ((first, "stage1.json.gz"), (graph, "graph.json.gz")):
        (directory / str(result["meta"]["run"]) / filename).write_bytes(gzip.compress(json.dumps(result, ensure_ascii=False).encode()))
    docx_data = (ROOT / "samples" / "기술수요조사서.docx").read_bytes()
    docx = server.Session("비교 제외 DOCX.docx", docx_data)
    works.create(docx.id, docx.name, "docx", docx_data)
    third = server.Session("비교 C 분석 전.hwpx", (ROOT / "samples" / "기술수요조사서.hwpx").read_bytes())
    works.create(third.id, third.name, "hwpx", third.original)
    ids = {"a": sessions[0].id, "b": sessions[1].id, "docx": docx.id,
           "c": third.id, "c_name": third.name, "a_name": sessions[0].name, "b_name": sessions[1].name}
    (folder / "fixtures.json").write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")
    server.DOCS.clear()
    return ids


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default=str(OUT))
    parser.add_argument("--port", type=int, default=8115)
    args = parser.parse_args()
    OUT = Path(args.out).resolve()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", args.port))  # 사용 중인 서버는 건드리지 않는다.
    OUT.mkdir(parents=True, exist_ok=True)
    folder = OUT / time.strftime("run_%Y%m%d_%H%M%S")
    folder.mkdir()
    ids = seed(folder)
    url = f"http://127.0.0.1:{args.port}"
    checks, logs = [], []

    def check(name, condition, detail=""):
        checks.append({"name": name, "ok": bool(condition), "detail": detail})
        print(("PASS " if condition else "FAIL ") + name + (": " + detail if detail else ""), flush=True)

    log_file = (folder / "server.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(args.port)],
                            cwd=ROOT, env=os.environ.copy(), stdout=log_file, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if requests.get(url + "/api/status", timeout=1).ok:
                    break
            except requests.RequestException:
                time.sleep(.2)
        else:
            raise RuntimeError("isolated server did not start")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
            page.add_init_script("try { localStorage.setItem('nfm.toolMore', '1'); } catch (e) {}")  # 패널 머리 오른쪽 묶음(검증·PDF·기록)을 펴 둔다 — 접힘은 smoke_panel_head_ui.py(2026-11-16)
            page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
            page.on("console", lambda msg: logs.append(f"console {msg.type}: {msg.text}") if msg.type == "error" else None)
            page.goto(f"{url}/#w={ids['a']}")
            page.wait_for_selector("#workspaceNav:not([hidden])")
            page.wait_for_selector(".para")
            page.click("#tabHeads")
            page.wait_for_selector("#heads2More .htree")
            # 2026-11-15: 검증·PDF·기록은 패널 머리 탭(#toolTabs) · 2026-11-16: 에이전트도 패널 머리 첫 탭 — 탭 띠는 고친 문단·헤딩 추출·표·문서 비교 넷
            check("HWPX four strip destinations + agent/verify/PDF/log in the panel head", page.locator("#workspaceNav [role=tab]:visible").count() == 4
                  and page.locator("#toolTabs #tabAgent:visible, #toolTabs #tabVerify:visible, #toolTabs #tabPdf:visible, #toolTabs #tabLog:visible").count() == 4)
            check("Six heading result views", page.locator(".heads-view-nav [role=tab]:visible").count() == 6)
            check("Heading tree visible without execution controls", page.locator("#heads2More .htree").is_visible() and not page.locator("#headsViewRun").is_visible())
            page.locator("#heads2More button.htext").first.click()
            check("Tree row jumps to source paragraph", page.locator("#doc .para.flash").count() > 0)
            page.screenshot(path=OUT / "01_heads_tree.png")

            page.click("#headsTabTemplates")
            check("Templates accessible directly", page.locator("#headsTemplatesResult .tpl-tree li.trel-node").count() > 0)  # 2026-11-15: 탭도 「템플릿 관계」 와 같은 트리(옛 카드 목록 없음)
            source = page.locator("#headsTemplatesResult .template-source")
            check("Template source jump buttons exist", source.count() > 0, f"{source.count()} buttons")
            if source.count():
                source.first.click()
                check("Template source jump works", page.locator("#doc .para.flash").count() > 0)
            page.screenshot(path=OUT / "02_templates.png")

            page.click("#headsTabLabels")
            page.locator("#headsLabelsResult .label-result").first.click()
            page.wait_for_selector("#headsDlg:not([hidden])")
            page.wait_for_selector("#headsDlgBody tr.go")
            check("Label opens matching paragraph list", "문단" in page.locator("#headsDlgTitle").inner_text())
            page.locator("#headsDlgBody tr.go").first.click()
            check("Label paragraph jumps to source", page.locator("#doc .para.flash").count() > 0)
            page.click("#headsDlgClose")
            for key in ("Edits", "Pdf", "Log", "Verify"):
                page.click(f"#tab{key}")
                check(f"{key} independent view", page.locator(f"#pane{key}").is_visible() and not page.locator("#paneHeads").is_visible())

            page.click("#tabCompare")
            page.get_by_role("checkbox", name=ids["b_name"] + " 비교 선택", exact=True).check()
            page.get_by_role("button", name="선택 문서 비교", exact=True).click()
            page.wait_for_selector(".mc-column")
            check("Two document comparison columns", page.locator(".mc-column").count() == 2)
            check("Matching chains despite different template numbers", page.locator(".mc-chip.candidate").count() > 0
                  and any(ref in page.locator(".mc-column").nth(1).inner_text() for ref in ("#101", "T101")))
            check("Labels remain scoped to their documents", re.search(r"\bS\d{4}\b", page.locator(".mc-column").nth(1).inner_text())
                  and not re.search(r"\bS\d{4}\b", page.locator(".mc-column").first.inner_text()))
            page.screenshot(path=OUT / "03_comparison_templates.png")
            page.locator(".mc-column .mc-format summary").first.click()
            check("Format values inspectable", page.locator(".mc-format[open] .mc-format-grid").first.is_visible())
            page.locator('[data-mc-mode="labels"]').click()
            check("Side by side labels", page.locator(".mc-column .mc-item").count() > 0)
            page.screenshot(path=OUT / "04_comparison_labels.png")
            page.locator(".mc-column").first.get_by_role("button", name="대표 문단", exact=False).first.click()
            check("Comparison current-source jump", page.locator("#tabHeads").get_attribute("aria-selected") == "true"
                  and page.locator("#doc .para.flash").count() > 0)

            page.click("#tabCompare")
            review = page.get_by_role("checkbox", name=ids["b_name"] + " 분석 결과 사용자 확인", exact=True)
            check("Fresh analysis permits user confirmation", review.is_enabled())
            doc = requests.get(f"{url}/api/docs/{ids['b']}", timeout=30).json()
            def paras(blocks):
                for block in blocks:
                    if block["type"] == "paragraph":
                        yield block
                    for cell in block.get("cells", []):
                        yield from paras(cell["blocks"])
            paragraph = next(p for p in paras(doc["blocks"]) if len(p.get("text", "")) > 10)
            response = requests.patch(f"{url}/api/docs/{ids['b']}/blocks/{paragraph['id']}",
                                      json={"text": paragraph["text"] + " 시험 수정"}, timeout=30)
            check("Isolated stale fixture edited", response.ok)
            review.check()  # 표시 직전 최신 분석을 다시 조회해야 한다.
            page.wait_for_function("[...document.querySelectorAll('.mc-notice')].some(e => e.textContent.includes('문서 또는 분석이 바뀌어'))")
            review = page.get_by_role("checkbox", name=ids["b_name"] + " 분석 결과 사용자 확인", exact=True)
            check("Stale result blocks user confirmation", review.is_disabled() and not review.is_checked())
            check("Stale column explains reanalysis", "다시 추출 필요" in page.locator(".mc-column").nth(1).inner_text())
            page.screenshot(path=OUT / "05_comparison_stale.png")

            page.locator(".mc-picker > summary").click()
            page.get_by_role("checkbox", name=ids["c_name"] + " 비교 선택", exact=True).check()
            page.get_by_role("button", name="선택 문서 비교", exact=True).click()
            page.wait_for_function("document.querySelectorAll('.mc-column').length === 3")
            check("Three document comparison with missing analysis", "분석 전" in page.locator(".mc-column").nth(2).inner_text())
            check("Missing analysis cannot be confirmed", page.get_by_role("checkbox", name=ids["c_name"] + " 분석 결과 사용자 확인", exact=True).is_disabled())
            page.screenshot(path=OUT / "05b_comparison_three.png")

            for width in (800, 390):
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_timeout(300)
                buttons = page.locator("#workspaceNav [role=tab]:visible")
                boxes = [buttons.nth(i).bounding_box() for i in range(buttons.count())]
                check(f"{width}px navigation remains on one scrollable row", len(boxes) == 4 and len({round(b["y"] + b["height"] / 2) for b in boxes if b}) == 1
                      and page.evaluate("() => { const t = document.getElementById('workspaceTools'); return t.clientWidth <= innerWidth && getComputedStyle(t).overflowX === 'auto'; }"), str(boxes))
                page.screenshot(path=OUT / f"06_narrow_{width}.png")
                page.click("#tabPdf")
                check(f"{width}px navigation usable", page.locator("#panePdf").is_visible())
                page.click("#tabCompare")

            page.set_viewport_size({"width": 1600, "height": 1000})
            page.goto(f"{url}/?docx=1#w={ids['docx']}")
            page.wait_for_selector("#workspaceNav:not([hidden])")
            check("DOCX excludes unsupported heading tool", not page.locator("#tabHeads").is_visible())
            page.click("#tabCompare")
            check("DOCX keeps comparison destination", page.locator("#paneCompare").is_visible())
            page.screenshot(path=OUT / "07_docx.png")
            check("No JavaScript runtime errors", not any(line.startswith("pageerror:") for line in logs), " | ".join(logs))
            browser.close()
    except Exception:
        checks.append({"name": "smoke completion", "ok": False, "detail": traceback.format_exc()})
        print(traceback.format_exc(), flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        log_file.close()
        (OUT / "console.txt").write_text("\n".join(logs), encoding="utf-8")
        (OUT / "results.json").write_text(json.dumps({"checks": checks, "fixtures": ids, "run": str(folder)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if checks and all(item["ok"] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
