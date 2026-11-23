"""스크립트 판정을 LLM 이 얼마나 고치나 — 작업 폴더의 실행 기록(works/<id>/headings/<n>/run.json · tables.json.gz)에서 뽑는 통계(spec_작업 ② §22 「보정 통계」). 읽기만 한다.

    python -X utf8 tools/llm_stats.py                 # 문서(올린 파일 이름)마다 단계별 추이 + 표에서 LLM 이 가장 많이 고치는 꼴
    python -X utf8 tools/llm_stats.py --doc 자율운항   # 이름에 그 글이 든 문서만
    python -X utf8 tools/llm_stats.py --json          # 같은 수를 JSON 으로
    python -X utf8 tools/llm_stats.py --works <폴더>  # 다른 작업 폴더(기본 = NFM_WORKS · %LOCALAPPDATA%\\NewFileManager\\works)

보는 것 — 같은 문서를 날짜 차례로:
  레터(1단계)  스크립트가 못 맞춘 줄 수 · LLM 에 물은 묶음 수(받아들인 규칙은 규칙 저장소에 남아 다음 문서의 스크립트가 쓴다)
  헤딩(2단계)  LLM 이 고친 노드 / 노드
  표(3단계)    LLM 이 고친 칸 / 칸 · 고친 표 / 보낸 표 · 고친 꼴(스크립트 초안 역할 → LLM 역할)
「고친 수」 가 줄면 스크립트가 나아진 것이다. 같은 문서라도 구조 반영 뒤에는 크기(노드 · 칸)가 달라지니 비율로 견준다 — 문서가 다르면 견주지 않는다."""
import argparse
import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import works  # noqa: E402


def _json(p):
    try:
        if p.suffix == ".gz":
            with gzip.open(p, "rt", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cells(run_dir):
    """그 3단계 실행의 표에서 — 보낸 표 · 고친 표 · 고친 꼴 Counter((초안, LLM 역할, 음영))."""
    t = _json(run_dir / "tables.json.gz")
    if not isinstance(t, dict):
        return None
    sent = touched = 0
    kinds = Counter()
    for tb in t.get("tables") or []:
        n = 0
        for c in tb.get("cells") or []:
            if c.get("draft") and c.get("role") and c["draft"] != c["role"]:
                kinds[(c["draft"], c["role"], bool(c.get("shaded")))] += 1
                n += 1
        sent += bool((tb.get("llm") or {}).get("sent"))
        touched += bool(n)
    return {"sent": sent, "touched": touched, "kinds": kinds}


def collect(root, doc=""):
    """{문서 이름: {"rules": [...], "heads": [...], "tables": [...]}} — 줄마다 날짜 차례."""
    out = defaultdict(lambda: {"rules": [], "heads": [], "tables": []})
    for w in sorted(p for p in Path(root).iterdir() if (p / "headings").is_dir()):
        name = ((_json(w / "work.json") or {}).get("name") or w.name).strip()
        if doc and doc not in name:
            continue
        for d in (w / "headings").iterdir():
            r = _json(d / "run.json") if d.is_dir() else None
            if not r or r.get("derivedFrom"):  # 이름만 다시 붙인 실행은 새 판정이 아니다
                continue
            s, base = r.get("summary") or {}, {"at": r.get("at") or 0, "work": w.name, "run": r.get("n"), "llm": bool(r.get("llm")), "cost": r.get("costUsd") or 0}
            if r.get("stage") == 1:
                q = r.get("rules") or {}
                out[name]["rules"].append({**base, "paragraphs": s.get("paragraphs"), "unmatched": s.get("unmatched"), "asked": q.get("groups") if q.get("asked") else 0, "saved": q.get("saved") or 0})
            elif r.get("stage") == 2 and r.get("llm"):
                out[name]["heads"].append({**base, "size": s.get("nodes") or 0, "changed": s.get("changed") or 0})
            elif r.get("stage") == 3 and r.get("llm"):
                c = _cells(d) or {"sent": None, "touched": None, "kinds": Counter()}
                out[name]["tables"].append({**base, "size": s.get("cells") or 0, "changed": s.get("changed") or 0, "tablesN": s.get("tables"), **c})
    for v in out.values():
        for k in v:
            v[k].sort(key=lambda x: x["at"])
    return dict(out)


def _day(t):
    return time.strftime("%m-%d %H:%M", time.localtime(t))


def _rate(x):
    return 100 * x["changed"] / x["size"] if x.get("size") else 0.0


def trends(rows, unit=""):
    """크기가 같은 실행끼리(구조 반영 전후를 섞지 않는다 — 2% 안) 첫 실행 → 마지막 실행의 고친 비율. 둘 이상인 묶음만."""
    groups = []
    for x in rows:
        g = next((g for g in groups if x["size"] and abs(x["size"] - g[0]["size"]) <= g[0]["size"] * 0.02), None)
        (g.append(x) if g else groups.append([x]))
    out = []
    for g in groups:
        if len(g) < 2:
            continue
        a, b = _rate(g[0]), _rate(g[-1])
        word = "줄었음" if b < a * 0.9 else "늘었음" if b > a * 1.1 else "그대로"
        out.append(f"  ⇒ {unit} {g[0]['size']} 짜리: 처음 {a:.1f}% ({_day(g[0]['at'])[:5]}) → 마지막 {b:.1f}% ({_day(g[-1]['at'])[:5]}) — {word}")
    return out


def report(data):
    lines = []
    for name, v in sorted(data.items(), key=lambda kv: -len(kv[1]["heads"]) - len(kv[1]["tables"])):
        if not (v["heads"] or v["tables"] or any(r["llm"] for r in v["rules"])):
            continue
        lines.append(f"\n■ {name}")
        sc = [r for r in v["rules"] if not r["llm"] and r["unmatched"] is not None]
        if sc:
            lines.append(f"  레터(스크립트가 못 맞춘 줄): 처음 {sc[0]['unmatched']} ({_day(sc[0]['at'])[:5]}) → 마지막 {sc[-1]['unmatched']} ({_day(sc[-1]['at'])[:5]}) · 실행 {len(sc)}")
        asked = [r for r in v["rules"] if r["llm"]]
        if asked:
            lines.append("  레터(LLM 에 물은 묶음 › 받아들인 규칙): " + " · ".join(f"{_day(r['at'])[:5]} {r['asked']}›{r['saved']}" for r in asked))
        for key, title, unit in (("heads", "헤딩", "노드"), ("tables", "표", "칸")):
            rows = v[key]
            if not rows:
                continue
            lines.append(f"  {title}(LLM 이 고친 {unit} / {unit}):")
            for x in rows:
                more = f" · 고친 표 {x['touched']}/{x['sent']}" if key == "tables" and x.get("sent") else ""
                lines.append(f"    {_day(x['at'])}  {x['changed']:>5} / {x['size']:<6} {_rate(x):4.1f}%{more}  ${x['cost']:.2f}  ({x['work']} #{x['run']})")
            lines += trends(rows, unit)
    kinds = Counter()
    for v in data.values():
        if v["tables"]:
            kinds += v["tables"][-1]["kinds"]
    total = sum(kinds.values())
    if total:
        lines.append(f"\n■ 표에서 LLM 이 고친 꼴 — 문서마다 마지막 실행을 모음(고친 칸 {total})")
        for (a, b, shaded), n in kinds.most_common(8):
            lines.append(f"    {a} → {b} ({'음영' if shaded else '음영 없음'}): {n} ({100 * n / total:.0f}%)")
    return "\n".join(lines) or "LLM 으로 건 실행 기록이 없습니다."


def main():
    ap = argparse.ArgumentParser(description="스크립트 판정을 LLM 이 얼마나 고치나 — 실행 기록에서 뽑는 통계(읽기만)")
    ap.add_argument("--works")
    ap.add_argument("--doc", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = Path(a.works) if a.works else works.root()
    if root is None or not root.is_dir():
        sys.exit("작업 폴더가 없습니다")
    data = collect(root, a.doc)
    if a.json:
        for v in data.values():
            for x in v["tables"]:
                x["kinds"] = [{"draft": k[0], "llm": k[1], "shaded": k[2], "n": n} for k, n in x["kinds"].most_common()]
        print(json.dumps(data, ensure_ascii=False, indent=1))
    else:
        print(report(data))


if __name__ == "__main__":
    main()
