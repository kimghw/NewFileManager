"""문서 비교용 헤딩 스냅샷. 문서를 다시 열거나 분석·검증·저장을 실행하지 않는다."""
import copy
from types import SimpleNamespace

from app import heading_runs as runs
from app import works


STAGES = {"stage1": "stage1.json", "stage2": "graph.json", "stage3": "tables.json"}


def _empty():
    return {"loaded": True, "job": None, "runs": [], **dict.fromkeys(STAGES)}


def _disk(wid, errors):
    """현재 결과 포인터만 읽는다. 원본·편집 문서 및 pickle 파일은 읽지 않는다."""
    st = _empty()
    folder = works.folder(wid)
    if folder is None:
        return None, st
    with works._lock(wid):
        work = works.work(wid)
        if work is None:
            return None, st
        directory = folder / "headings"
        pointer = directory / "current.json"
        current = works._read_json(pointer)
        if current is None and not pointer.exists():
            return work, st
        if not isinstance(current, dict):
            errors.append({"stage": "all", "message": "저장된 분석 결과의 목록을 읽지 못했습니다."})
            return work, st
        for stage, filename in STAGES.items():
            number = current.get(stage)
            if number is None:
                continue
            if type(number) is not int or number <= 0:
                errors.append({"stage": stage, "message": "저장된 분석의 실행 번호가 올바르지 않습니다."})
                continue
            result = runs._read(directory / str(number) / filename)
            if not isinstance(result, dict):
                errors.append({"stage": stage, "message": "저장된 분석 결과가 없거나 파일을 읽지 못했습니다."})
                continue
            if isinstance(result.get("meta"), dict):
                result["meta"].setdefault("run", number)
            st[stage] = result
        st["runs"] = [r for r in (works._read_json(directory / str(n) / "run.json")
                                   for n in runs._run_numbers(directory)[-20:]) if isinstance(r, dict)]
    return work, st


def _validate(stage, result):
    """구조가 깨진 한 단계 때문에 다른 문서·단계의 비교도 막히지 않게 한다."""
    if not isinstance(result, dict) or not isinstance(result.get("meta"), dict):
        raise ValueError("분석 메타데이터 없음")
    if not isinstance(result.get("counts"), dict):
        raise ValueError("분석 개수 없음")
    if stage == "stage1":
        if not isinstance(result.get("labels"), dict) or not isinstance(result.get("formats"), dict):
            raise ValueError("서식 라벨 없음")
        for label in result["labels"].values():
            if not isinstance(label, dict) or not isinstance(label.get("para"), dict) or not isinstance(label.get("char"), dict):
                raise ValueError("서식 라벨 구조 오류")
    elif stage == "stage2":
        for key in ("nodes", "types", "templates", "instances", "heterogeneous", "repeats", "adjustments"):
            if not isinstance(result.get(key), list) or any(not isinstance(item, dict) for item in result[key]):
                raise ValueError("그래프 구조 오류")
        for template in result["templates"]:
            if not isinstance(template.get("slots"), list) or any(not isinstance(slot, dict) for slot in template["slots"]):
                raise ValueError("템플릿 구조 오류")


def preview(wid, session, keys):
    """기존 세션은 잠금 아래 복사하고, 닫힌 작업은 저장된 분석 JSON만 읽는다. 없는 작업은 None."""
    errors = []
    if session is None:
        work, st = _disk(wid, errors)
        if work is None:
            return None
    else:
        with session.lock:
            work = works.work(wid) or {}
            work = {**work, "id": wid, "name": session.name, "format": session.fmt,
                    "rev": session.rev, "size": len(session.original), "created": session.created,
                    "edited": len(session.edited())}
            heads = getattr(session, "heads", None)
            if heads is not None and heads.get("loaded"):
                st = copy.deepcopy({k: v for k, v in heads.items() if k != "job"})
                job = heads.get("job")
                view = job.view() if job else None
                st["job"] = SimpleNamespace(view=lambda: view) if view else None
            else:
                _, st = _disk(wid, errors)

    supported = work.get("format") == "hwpx"
    rev = work.get("rev", 0)
    summary = runs.summary(SimpleNamespace(rev=rev, heads=_empty()))
    summary["runs"] = st.get("runs", [])[-20:]
    summary["persistError"] = st.get("persistError")
    if st.get("job"):
        summary["job"] = st["job"].view()
    labels = {"labels": [], "formats": 0}
    graph = None
    readiness = dict.fromkeys(STAGES, "missing" if supported else "unsupported")
    valid = {}
    if supported:
        for stage in STAGES:
            result = st.get(stage)
            if result is None:
                continue
            try:
                _validate(stage, result)
                proxy = SimpleNamespace(rev=rev, heads={**_empty(), stage: result})
                item = runs.summary(proxy)[stage]
                stage_labels = runs.labels(proxy) if stage == "stage1" else None
            except (KeyError, TypeError, ValueError, AttributeError, IndexError):
                errors.append({"stage": stage, "message": "저장된 분석 결과의 구조가 올바르지 않습니다."})
                continue
            valid[stage] = result
            summary[stage] = item
            readiness[stage] = "stale" if item["stale"] else "ready"
            if stage == "stage1":
                labels = stage_labels
            elif stage == "stage2":
                graph = result
        # 문서 rev가 같아도 라벨을 재추출했다면 이전 그래프의 S 번호와 섞어 비교할 수 없다.
        first = valid.get("stage1")
        for stage in ("stage2", "stage3"):
            result = valid.get(stage)
            if result is not None and (first is None or summary["stage1"]["stale"]
                                       or result["meta"].get("stage1Run") != first["meta"].get("run")):
                summary[stage]["stale"] = True
                readiness[stage] = "stale"
                errors.append({"stage": stage, "message": "현재 서식 라벨과 기준 실행이 달라 다시 분석해야 합니다."})
        for error in errors:
            targets = STAGES if error["stage"] == "all" else (error["stage"],)
            for stage in targets:
                if readiness[stage] == "missing":
                    readiness[stage] = "invalid"

    return {"work": {**{k: work.get(k) for k in keys}, "open": session is not None},
            "summary": summary, "labels": labels, "graph": graph, "supported": supported,
            "readiness": readiness, "errors": errors}
