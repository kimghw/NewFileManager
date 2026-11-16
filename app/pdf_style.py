"""헤딩 레터·글꼴 대조(spec_hwpx_웹편집 ② §3-2) — 웹이 뽑은 레터 꼴·글자 모양을 한글 PDF 의 글자(PyMuPDF rawdict + 가짜 굵게 긋기)와 견준다.

- 레터(`check_heads`): headings.extract 의 헤딩 문단마다 PDF 첫 줄에서 레터 글자, 앞 공백(칸 수·폭 mm), 레터 뒤 공백(칸 수·폭 mm), 둘째 줄이
  첫 줄보다 들어간 폭(mm — 서식 내어쓰기와), 본문 문단의 왼쪽 여백(mm)을 잰다. 개요 문단(고정헤딩)은 한글이 개요 번호를 찍는데 웹은 안 보이면 「웹에 없는 레터」.
- 글꼴(`check_fonts`): 찾은 문단의 글자·숫자를 PDF 글자와 하나씩 맞춰 크기(쪽 배율 보정 — 윗·아래첨자 × 0.64, 장평은 √장평: PyMuPDF 크기는
  가로·세로 배율의 기하 평균)·굵게·색·글꼴을 견준다. 글꼴은 웹이 실제로 그리는 것(app/fonts.py 계획 — 글자의 언어 글꼴, 없으면 대체·대응표)과
  PDF 글꼴을 이 PC 글꼴 이름표로 같은 가족인지 본다.
읽기만 — 매핑 결과(pdf_map.map_detail 의 쪽·항목)를 받아 쓴다."""
import math
from collections import Counter
from statistics import median

from app.fonts import SCRIPT_SIZE, FontIndex, font_index, lang_of  # noqa: F401 — FontIndex·font_index 는 예전 자리(pdf_style)로도 쓴다
from app.headings import BR
from app.hwpx_format import LANG_FONT_KEYS
from app.pdf_map import key_text, strict_text

PT_MM = 72 / 25.4
TOL_MM = 0.5          # 둘째 줄·왼쪽 여백: 이만큼(mm) 안이면 같음
SIZE_TOL = (0.3, 0.03)  # 글자 크기: |PDF/배율 − 웹(첨자·장평 반영)| ≤ max(0.3pt, 3%)
SPACES = " \u00a0\u3000"
LIST_MAX = 120
LANG_KEY = {lang: key for key, lang in LANG_FONT_KEYS.items()}  # LATIN -> 서식 요약 fontLatin …


# ---- PDF 글자 자리 -----------------------------------------------------------------------------------

def key_index(pages):
    """pdf_map._stream 과 같은 글자·숫자 열의 자리마다 (쪽, 줄, 글자 번호) — 줄의 글자별 키를 이은 것이 줄 키와 다르면(NFKC 합성 등) 글자 번호 None."""
    at = []
    for pg, p in enumerate(pages):
        for li, ln in enumerate(p["lines"]):
            k = key_text(ln["text"])
            per = [(ci, kc) for ci, ch in enumerate(ln.get("chars") or ()) for kc in key_text(ch[0])]
            if "".join(kc for _, kc in per) == k:
                at += [(pg, li, ci) for ci, _ in per]
            else:
                at += [(pg, li, None)] * len(k)
    return at


def visual_line(page, li):
    """줄 li 와 같은 블록·같은 높이(세로로 반 넘게 겹침)인 줄들의 글자를 x 순으로 -> [(줄, 글자 번호, 글자)] — 탭·넓은 사이로 PyMuPDF 가 한 줄을 나눈 것을 잇는다."""
    base = page["lines"][li]
    y0, y1 = base["bbox"][1], base["bbox"][3]
    out = []
    for lj, ln in enumerate(page["lines"]):
        if ln["block"] != base["block"]:
            continue
        a, b = ln["bbox"][1], ln["bbox"][3]
        if min(y1, b) - max(y0, a) > 0.5 * min(y1 - y0, b - a):
            out += [(lj, ci, ch) for ci, ch in enumerate(ln.get("chars") or ())]
    return sorted(out, key=lambda t: t[2][1])


def geometry_scale(page, blocks):
    """PDF pt / 문서 pt — 보통 쪽 1, 2쪽 모아 찍기 반 쪽은 용지를 반 장에 맞춘 배율(가로·세로 중 작은 것)."""
    sec = next((b["page"] for b in blocks if b.get("page")), None)
    if "half" not in page or not sec:
        return 1.0
    return min(page["w"] / (sec["widthMm"] * PT_MM), page["h"] / (sec["heightMm"] * PT_MM))


# ---- 레터 대조 ----------------------------------------------------------------------------------------

AMBIG_LEN = 8  # 이보다 짧은 글이 PDF 에 여러 번 나오면 매핑이 다른 자리를 잡았을 수 있다(「작성 요령」·「합 계」) — 대조에서 뺀다


def reliable(its, pages):
    """대조에 쓸 항목 id — 찾았고, 「가까운 자리」가 아니고, 짧은 글이면 PDF 에 한 번뿐인 것."""
    stream = "".join(key_text(ln["text"]) for p in pages for ln in p["lines"])
    return {it["id"] for it in its if "pos" in it and not it.get("near")
            and (len(it["key"]) >= AMBIG_LEN or stream.count(it["key"]) == 1)}


def _first_key(text):
    """글에서 처음 글자·숫자(키에 드는 글자)가 나오는 자리 — 없으면 len."""
    return next((i for i, ch in enumerate(text) if key_text(ch)), len(text))


def _spaces(s):
    return sum(ch in SPACES for ch in s)


def _sections(blocks):
    """맨 위 블록 id -> 그 구역의 용지·여백(블록의 "page" 가 구역 시작)."""
    out, cur = {}, None
    for b in blocks:
        cur = b.get("page") or cur
        out[b["id"]] = cur
    return out


def check_heads(rows, blocks, its, pages):
    """rows: headings.extract(...)["rows"]. -> {"checked", "letter": {ok, bad}, "lead"·"gap"·"line2"·"left": {ok, bad, measured}, "missingOnWeb",
    "unknown", "issues": [...], "patterns": [{key, count, leadMm, gapMm, line2Mm, hangMm}]}."""
    paras = {}

    def walk(bs, top):
        for b in bs:
            if b.get("type") == "paragraph":
                paras[b["id"]] = (b, top)
            for c in b.get("cells") or ():
                walk(c.get("blocks") or [], False)
    walk(blocks, True)
    secs = _sections(blocks)
    # 레터는 웹 앞머리를 PDF 줄에서 거꾸로 맞추므로 같은 글의 다른 자리여도 같은 레터 — 「가까운 자리」만 뺀다(글꼴은 reliable)
    pos = {it["id"]: it for it in its if "pos" in it and not it.get("near")}
    at = key_index(pages)
    cnt = {k: Counter() for k in ("letter", "lead", "gap", "line2", "left")}
    issues, unknown, missing_web, pat = [], 0, 0, {}

    def note(pid, kind, web, pdf, text, page):
        if len(issues) < LIST_MAX:
            issues.append({"id": pid, "kind": kind, "web": web, "pdf": pdf, "text": text[:60], "page": page})

    for pid, row in rows.items():
        it = pos.get(pid)
        p, top = paras.get(pid, (None, False))
        if it is None or p is None:  # 못 찾음·「가까운 자리」·여러 번 나오는 짧은 글(reliable)
            unknown += 1
            continue
        pg, li, ci = at[it["pos"]]
        page = pages[pg]
        if ci is None:
            unknown += 1
            continue
        head, text = row["head"], (p.get("text") or "").split(BR, 1)[0]
        label = head["letter"] if head.get("auto") else ""
        disp = label + text
        a = len(label) + _first_key(text)          # 키 첫 글자의 웹 자리 = PDF 의 (li, ci)
        line = visual_line(page, li)
        v0 = next((k for k, (lj, cj, _) in enumerate(line) if (lj, cj) == (li, ci)), None)
        if v0 is None:
            unknown += 1
            continue
        chars = [t[2] for t in line]
        pno = page["sheet"] + 1
        # 웹 앞머리(첫 글자·숫자 앞 — 레터 기호·자동 번호)를 PDF 줄의 v0 앞에서 거꾸로 맞춘다(공백 건너뜀). 그 앞의 공백 = 앞 공백,
        # 더 앞의 글자 = 같은 높이의 다른 칸 글(또는 개요 문단이면 웹이 안 보이는 개요 번호)
        web_pre = strict_text(disp[:a])
        back = [k for k in range(v0 - 1, -1, -1) if not chars[k][0].isspace()][:len(web_pre)]
        got = strict_text("".join(chars[k][0] for k in reversed(back)))
        if got != web_pre:
            cnt["letter"]["bad"] += 1
            note(pid, "letter", head["letter"] or web_pre, got or "(없음)", text, pno)
            continue
        s = back[-1] if back else v0
        while s > 0 and chars[s - 1][0].isspace():
            s -= 1
        before, chars = chars[:s], chars[s:]
        if before and not head["letter"] and row["source"] == "style":
            near_x = chars[0][1] - before[-1][3] < 3 * (chars[0][4] - chars[0][2])
            num = strict_text("".join(c[0] for c in before[-8:]))
            if near_x and num:
                missing_web += 1  # 개요 문단: 한글이 찍는 개요 번호를 웹은 안 보인다
                note(pid, "outline", "", num, text, pno)
        letter = strict_text(head["letter"])
        nonsp = [k for k, c in enumerate(chars) if not c[0].isspace()]
        if letter:
            got = "".join(chars[k][0] for k in nonsp[:len(letter)])
            if strict_text(got) != letter:
                cnt["letter"]["bad"] += 1
                note(pid, "letter", head["letter"], got, text, pno)
                continue
            cnt["letter"]["ok"] += 1
        if not nonsp:
            continue
        scale = geometry_scale(page, blocks) * PT_MM
        first = nonsp[0]
        x_line = chars[0][1]
        lead_n, lead_mm = sum(c[0] in SPACES for c in chars[:first]), (chars[first][1] - x_line) / scale
        rec = pat.setdefault((row["place"], head["full"]), {"lead": [], "gap": [], "line2": [], "hang": Counter(), "hang2": []})
        rec["lead"].append(lead_mm)
        web_lead = head["lead"]
        if "\t" not in web_lead:
            ok = lead_n == _spaces(web_lead)
            cnt["lead"]["ok" if ok else "bad"] += 1
            if not ok:
                note(pid, "lead", f"{_spaces(web_lead)}칸", f"{lead_n}칸 ({lead_mm:.1f}mm)", text, pno)
        if letter and len(nonsp) > len(letter):
            end, nxt = nonsp[len(letter) - 1], nonsp[len(letter)]
            gap_n, gap_mm = sum(c[0] in SPACES for c in chars[end + 1:nxt]), (chars[nxt][1] - chars[end][3]) / scale
            rec["gap"].append(gap_mm)
            # 자동 번호·글머리 뒤 간격은 한글이 문단 번호 설정(번호 뒤 간격)으로 띄운다 — 글에 공백이 없으니 칸 수는 견주지 않고 폭만 잰다
            if "\t" not in head["gap"] and not head.get("auto"):
                ok = gap_n == _spaces(head["gap"])
                cnt["gap"]["ok" if ok else "bad"] += 1
                if not ok:
                    note(pid, "gap", f"{_spaces(head['gap'])}칸", f"{gap_n}칸 ({gap_mm:.1f}mm)", text, pno)
        l2 = row["line2"]
        rec["hang"][l2["hangMm"] or 0.0] += 1
        if (p.get("format") or {}).get("align") in ("center", "right"):
            continue  # 가운데·오른쪽 정렬: 줄마다 시작 x 가 글 길이로 정해진다 — 둘째 줄·왼쪽 여백을 못 잼
        # 둘째 줄: 이 문단 키 안에서 첫 줄과 다른(더 아래) 줄이 처음 나오는 곳 — 같은 쪽일 때만
        here = {(lj, cj) for lj, cj, _ in line}
        y_mid = (page["lines"][li]["bbox"][1] + page["lines"][li]["bbox"][3]) / 2
        for j in range(it["pos"] + 1, min(len(at), it["pos"] + len(it["key"]))):
            pg2, li2, ci2 = at[j]
            if pg2 != pg or ci2 is None:
                break
            if (li2, ci2) in here:
                continue
            b2 = page["lines"][li2]["bbox"]
            if b2[1] <= y_mid:
                break  # 위로 되돌아감(다른 칸) — 둘째 줄 모름
            second = visual_line(page, li2)
            x2 = next((c[1] for _, _, c in second if not c[0].isspace()), None)
            if x2 is not None:
                mm = (x2 - x_line) / scale
                rec["line2"].append(mm)
                rec["hang2"].append(l2["hangMm"])  # 둘째 줄을 잰 문단의 서식 값 — 꼴의 실측과 나란히 보일 것
                ok = abs(mm - l2["hangMm"]) <= TOL_MM
                cnt["line2"]["ok" if ok else "bad"] += 1
                if not ok:
                    note(pid, "line2", f"{l2['hangMm']:g}mm ({l2['rule']})", f"{mm:.1f}mm", text, pno)
            break
        sec = secs.get(pid) if top else None
        if sec:
            f = p.get("format") or {}
            want = sec["marginsMm"]["l"] + float(f.get("indentLeftMm") or 0) + max(float(f.get("firstLineMm") or 0), 0)
            got_mm = x_line / scale
            ok = abs(got_mm - want) <= TOL_MM
            cnt["left"]["ok" if ok else "bad"] += 1
            if not ok:
                note(pid, "left", f"{want:.1f}mm", f"{got_mm:.1f}mm", text, pno)
    med = lambda xs: round(median(xs), 1) if xs else None  # noqa: E731
    patterns = [{"place": k[0], "full": k[1], "count": len(v["lead"]), "leadMm": med(v["lead"]), "gapMm": med(v["gap"]),
                 "line2Mm": med(v["line2"]), "line2Count": len(v["line2"]),
                 # 서식 내어쓰기: 둘째 줄을 잰 문단들의 가운데 값(실측과 같은 문단), 잰 것이 없으면 꼴 전체에서 가장 흔한 값
                 "hangMm": med(v["hang2"]) if v["hang2"] else v["hang"].most_common(1)[0][0] if v["hang"] else None}
                for k, v in sorted(pat.items(), key=lambda kv: -len(kv[1]["lead"]))]
    return {"checked": len(rows) - unknown, "total": len(rows), "unknown": unknown, "missingOnWeb": missing_web,
            **{k: dict(v) for k, v in cnt.items()}, "issues": issues, "patterns": patterns[:60]}


# ---- 글꼴 대조 ----------------------------------------------------------------------------------------

def _web_chars(p):
    """문단 글자·숫자마다 (키 글자, 원 글자, 글자 모양) — 런 모양이 있으면 그것, 없으면 문단 모양."""
    f = p.get("format") or {}
    out = []
    for r in p.get("runs") or [{"text": p.get("text") or "", "format": None}]:
        rf = r.get("format") or f
        for ch in r.get("text") or "":
            out += [(kc, ch, rf) for kc in key_text(ch)]
    return out


def _hex(c):
    return f"#{c:06X}"


def _want(wf):
    """웹 글자 모양 -> (PDF 에 찍혀야 할 크기 ÷ 쪽 배율, 까닭) — 윗·아래첨자 × SCRIPT_SIZE, 장평 r% 는 × √(r/100)
    (PyMuPDF 의 글자 크기는 글자 행렬 가로·세로 배율의 기하 평균 — 장평 80% 면 0.894배로 읽힌다, references/HWPX_렌더링_검증.md)."""
    size = wf.get("sizePt")
    if not size:
        return None, ""
    k, why = 1.0, []
    if wf.get("script"):
        k *= SCRIPT_SIZE
        why.append("윗첨자" if wf["script"] == "sup" else "아래첨자")
    r = wf.get("ratioPct") or 100
    if r != 100:
        k *= math.sqrt(r / 100)
        why.append(f"장평 {r}%")
    return size * k, "·".join(why)


def _web_face(ch, wf):
    """글자를 웹이 그리는 문서 글꼴 (이름, 언어) — 영문·한자·일어 글자는 그 언어 글꼴(서식 요약 fontLatin…)이 있으면 그것, 아니면 한글 글꼴."""
    lang = lang_of(ch)
    face = wf.get(LANG_KEY[lang]) if lang in LANG_KEY else None
    return (face, lang) if face else (wf.get("font"), "HANGUL")


def check_fonts(blocks, its, pages, index=None, table=None):
    """table: HwpxDoc.font_table() — 웹 글꼴 계획(app/fonts.py)을 문서 글꼴 종류(HFT)·대체 글꼴까지 넣어 세운다(없으면 TTF·대체 없음).
    -> {"chars", "size": {bad, checked, script, scripted, ratio, examples}, "bold", "color", "faces": [...], "latin": [...], "scale"}."""
    index = index or font_index()
    table = table or {}
    plans = {}

    def plan(face, lang):
        if (face, lang) not in plans:
            info = (table.get(lang) or {}).get(face) or {}
            ftype = info.get("type") or "TTF"
            plans[face, lang] = {**index.resolve(face or "", lang, ftype, info.get("subst") or ()), "type": ftype}
        return plans[face, lang]
    paras = {}

    def walk(bs):
        for b in bs:
            if b.get("type") == "paragraph":
                paras[b["id"]] = b
            for c in b.get("cells") or ():
                walk(c.get("blocks") or [])
    walk(blocks)
    at = key_index(pages)
    ok_ids = reliable(its, pages)
    pairs = []  # (web 원 글자, 웹 모양, PDF 글자, span, 쪽 번호, 문단 id, Type3)
    for it in its:
        p = paras.get(it["id"])
        if it["id"] not in ok_ids or p is None:
            continue
        web = _web_chars(p)
        if "".join(w[0] for w in web) != it["key"]:
            continue
        for k, (kc, ch, wf) in enumerate(web):
            j = it["pos"] + k
            if j >= len(at):
                break
            pg, li, ci = at[j]
            if ci is None:
                break
            ln = pages[pg]["lines"][li]
            pc = ln["chars"][ci]
            if key_text(pc[0]) != kc and kc not in key_text(pc[0]):
                break  # 어긋남 — 이 문단은 여기까지만
            sp = ln["spans"][pc[5]]
            pairs.append((ch, wf, pc, sp, pg, it["id"], sp[0] in pages[pg].get("type3", ())))
    # 쪽마다 크기 배율 = PDF 크기 / 웹이 바라는 크기(첨자·장평 반영) 의 가운데 값(보통 ≈ 1.0, 2쪽 모아 찍기 ≈ 0.67)
    by_page = {}
    for ch, wf, pc, sp, pg, *_ in pairs:
        want, _ = _want(wf)
        if want:
            by_page.setdefault(pg, []).append(sp[1] / want)
    scale = {pg: median(v) for pg, v in by_page.items()}
    res = {k: {"bad": 0, "checked": 0, "examples": []} for k in ("size", "bold", "color")}
    # script = 크기가 웹의 55~75% — 첨자로 보이는데 웹 서식엔 첨자가 없음 · scripted/ratio = 웹 첨자·장평 글자(그 크기로 견줌)
    res["size"].update(script=0, scripted=0, ratio=0)
    faces, latin, type3s, bolds = {}, {}, set(), {}

    seen = set()

    def bad(kind, pid, ch, web, pdf, pg):
        """셈은 글자 단위, 보기(examples)는 문단·항목마다 한 번."""
        r = res[kind]
        r["bad"] += 1
        if (pid, kind) not in seen and len(r["examples"]) < LIST_MAX:
            seen.add((pid, kind))
            r["examples"].append({"id": pid, "char": ch, "web": web, "pdf": pdf, "page": pages[pg]["sheet"] + 1})
    for ch, wf, pc, sp, pg, pid, type3 in pairs:
        (want, why), s = _want(wf), scale.get(pg)
        if want and s:
            res["size"]["checked"] += 1
            res["size"]["scripted"] += bool(wf.get("script"))
            res["size"]["ratio"] += not wf.get("script") and (wf.get("ratioPct") or 100) != 100
            got = sp[1] / s
            if abs(got - want) > max(SIZE_TOL[0], SIZE_TOL[1] * want):
                res["size"]["script"] += not wf.get("script") and 0.55 <= got / want <= 0.75
                bad("size", pid, ch, f"{wf['sizePt']:g}pt" + (f"({why} → {want:.1f}pt)" if why else ""), f"{got:.1f}pt", pg)
        if not type3:  # Type3(한글 HFT) 글자는 굵게를 글꼴 이름·긋기로 알 수 없다
            res["bold"]["checked"] += 1
            if bool(wf.get("bold")) != bool(pc[6]):
                bad("bold", pid, ch, "굵게" if wf.get("bold") else "보통", "굵게" if pc[6] else "보통", pg)
        else:
            type3s.add(sp[0])
        res["color"]["checked"] += 1
        color = (wf.get("color") or "#000000").upper()
        if _hex(sp[3]) != color:
            bad("color", pid, ch, color, _hex(sp[3]), pg)
        face, lang = _web_face(ch, wf)
        (faces if lang == "HANGUL" else latin).setdefault((face, lang), Counter())[sp[0]] += 1  # 한글 글꼴로 그린 글자 / 언어 글꼴로 그린 글자
        # 굵게 짝(웹 → PDF) — 다름이 PDF 글꼴 하나에 몰렸는지(기준 쪽 사정) 문단 서식을 따르는지 가리는 근거(검증 LLM 검토, spec_hwpx_웹편집 ② §4-1)
        bolds.setdefault((face, lang), Counter())[f"{'굵게' if wf.get('bold') else '보통'}→{'모름' if type3 else '굵게' if pc[6] else '보통'}"] += 1
    return {"chars": len(pairs), "paragraphs": len({x[5] for x in pairs}), **res, "faces": _verdicts(faces, plan, index, type3s, bolds),
            "latin": _verdicts(latin, plan, index, type3s, bolds)[:20], "scale": round(median(scale.values()), 3) if scale else None}


def _verdicts(tally, plan, index, type3s, bolds=None):
    """{(웹 문서 글꼴, 언어): Counter(PDF 글꼴)} -> 그 글꼴마다 판정(글자 많은 순). 웹이 그리는 가족 = plan(app/fonts.py 계획).
    bolds {(글꼴, 언어): Counter(「보통→굵게」 …)} 가 있으면 줄마다 "bold"(굵게 짝 — 웹 → PDF 글자 수).
    same = 같은 글꼴 · subst = 문서 글꼴이 이 PC 에 없어 한글·웹이 같은 글꼴로 대체(문서 대체 글꼴·한컴 대응표) · differ = 웹이 다른 글꼴로 그림 ·
    equiv = 한글 전용 글꼴(HFT — PDF 엔 이름 없는 Type3)인데 웹은 한컴 대응표의 같은 디자인 TTF(한양중고딕 → HY중고딕) ·
    hangul = 이름 모를 글꼴(Type3·「????」)로 찍혔고 웹은 대체 글꼴 · unknown = PDF 글꼴 이름을 모름(웹은 문서 글꼴 그대로)."""
    out = []
    for (face, lang), pdf in sorted(tally.items(), key=lambda kv: -sum(kv[1].values())):
        r = plan(face, lang)
        uses = r["key"]
        fams = Counter()
        for name, n in pdf.items():
            fam = index.family(name) or (uses if index.broken_match(name, uses) else None)
            fams[fam or "?" + name] += n
        top, n_top = fams.most_common(1)[0]
        if top.startswith("?"):
            t3 = top[1:] in type3s
            verdict = ("equiv" if t3 and r["how"] == "equiv" and r["type"].upper() == "HFT" else
                       "hangul" if t3 or r["how"] != "same" else "unknown")
        else:
            verdict = ("same" if r["how"] == "same" else "subst") if top == uses else "differ"
        out.append({"web": face or "(없음)", "lang": lang, "how": r["how"], "via": r["via"], "type": r["type"],
                    "uses": index.label.get(uses, uses) if uses else None, "fallback": r["how"] != "same",
                    "pdf": dict(pdf.most_common(4)), "verdict": verdict, "chars": sum(pdf.values()),
                    "share": round(n_top / sum(fams.values()), 3)})
        if bolds is not None:
            out[-1]["bold"] = dict(bolds.get((face, lang)) or {})
    return out
