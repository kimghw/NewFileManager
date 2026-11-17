"""헤딩 추출 — LLM 호출(spec_헤딩_추출 ② §3·§6): 코드 고정 출력 계약 + 사용자 지침 + 자료(JSON) 로 프롬프트를 짓고, 구조화 출력(평면 스키마 —
재귀 스키마 불가)을 받아 검증한다. 호출 원문(프롬프트·응답·시간·비용)은 `calls` 로 돌려 실행 폴더에 남긴다.

- 1단계 규칙 보강(`propose_rules`): 보강 대상 묶음 → 묶음마다 rule|keep|unsure → 스크립트 검증(heading_extract.test_rule) → 후보 규칙 저장·keeps 저장.
- 2단계 A(유형 판정)·B(구간 예외) 호출의 계약·스키마는 여기, 자료 짓기·조립은 `app/heading_graph.py`."""
import json
import time

from app import heading_extract as E
from app import heading_forms as F
from app import heading_guides as G
from app import heading_rules as R
from app import llm

RULE_KINDS = ["marker", "label", "note", "footnote", "data", "placeholder", "plain"]
BATCH_GROUPS = 10  # 규칙 보강 호출 하나에 담는 묶음 수 — 묶음이 많은 큰 문서는 여러 호출이 같이 돈다(llm.ask_all). 전에는 30: 실측(2026-11-17 · 묶음 29 · 한 호출) 73초 — 답 길이가 시간을 정한다(묶음마다 약 2.5초)


def _schema(props, required=None):
    return {"type": "object", "additionalProperties": False, "required": required or list(props), "properties": props}


def _arr(item):
    return {"type": "array", "items": item}


S, B, I = {"type": "string"}, {"type": "boolean"}, {"type": "integer"}

RULES_SCHEMA = _schema({"items": _arr(_schema({
    "group": S, "decision": {"type": "string", "enum": ["rule", "keep", "unsure"]}, "name": S,
    "kind": {"type": "string", "enum": RULE_KINDS + [""]}, "family": S, "pattern": S, "scope": {"type": "string", "enum": ["prefix", "whole", ""]},
    "first": B, "positives": _arr(S), "negatives": _arr(S), "globalHint": B, "reason": S}))})

RULES_CONTRACT = """당신은 한글(hwpx) 문서의 문단 첫머리 「레터」(개요 기호·번호·라벨·안내 표지)를 판정하는 정규식 규칙을 만드는 도우미입니다.
스크립트 규칙이 못 맞춘 문단 묶음(type unmatched — 꼴이 같은 문단들)과, 종류가 다른 두 규칙이 함께 맞아 먼저 온 규칙이 이긴 충돌 묶음(type conflict — rules = [이긴 규칙, 진 규칙])을 받습니다.
묶음마다 정확히 하나씩 답하세요(group = 묶음 group 값 그대로).
- decision "rule": 이 묶음을 판정할 규칙 하나 — name(짧은 이름), kind(marker·label·note·footnote·data·placeholder·plain), family(계열 이름 — 영문 소문자·하이픈),
  pattern(Python 정규식 — scope "prefix" 는 레터 앞 빈칸을 뗀 첫머리에 match 로 레터 토큰만, "whole" 은 앞뒤 빈칸을 뗀 첫 줄 전체에 fullmatch), scope,
  first(충돌 묶음에서 이긴 내장 규칙을 뒤집어야 할 때만 true — 그때 이 규칙은 내장 규칙보다 먼저 판정되며 묶음 밖 문단을 하나도 바꾸면 안 됨),
  positives(이 규칙이 맞아야 하는 예문 id — 묶음 예문 중), negatives(맞으면 안 되는 글 — 꾸며 써도 됨, 3개 이내).
  plain 으로 볼 꼴(괄호 안 낱말로 시작하는 표 머리말 등)도 kind plain 규칙으로 남겨 다시 묻지 않게 합니다.
- decision "keep": (충돌 묶음) 지금 이긴 규칙이 맞음 — 규칙 칸은 빈 값.
- decision "unsure": 판단 근거가 모자람.
globalHint = 다른 문서에도 나올 일반 꼴이면 true. reason = 한두 문장(한국어). 쓰지 않는 칸은 빈 문자열("")·빈 목록·false 로 채웁니다. 입력에 없는 group 은 쓰지 않습니다.
아래 「지침」 은 사용자가 관리하는 판정 기준입니다 — 계약과 어긋나면 계약을 따르세요."""

# ---- 2단계 계약·스키마(자료는 heading_graph) ------------------------------------------------------------------

TYPES_SCHEMA = _schema({
    "types": _arr(_schema({"type": S, "role": {"type": "string", "enum": ["heading", "label", "subtitle", "title", "note", "not_heading"]},
                           "parents": _arr(S), "variantOf": S, "basis": S, "reason": S})),
    "mainChain": _arr(S),
    "summary": S})

TYPES_CONTRACT = """당신은 국가R&D 계획서·보고서 같은 한글 양식의 개요 체계를 정하는 분석가입니다. 스크립트가 문서의 헤딩 후보 문단을 「헤딩 유형」(자리·레터 꼴·굵게·크기)으로
묶은 유형 표(key = 정규 레터 키 — 변형군을 합친 레터 모양, 구분 라벨은 "[구분 기준]"(예 "[기관]"), 괄호 소제목은 "[…]")와, 본문 헤딩 후보를 문서 순으로 적은 개요 스케치
(「유형 _레터앞빈칸수 레터 글」), 스크립트가 빈도로 제안한 본문 주 사슬(mainChainProposal), 이 문서의 구분 기준 목록(bases)을 받습니다. 템플릿은 레터 사슬 하나이고, 한 부모 아래
다른 레터가 오는 자리(가지 자리)마다 새 템플릿이 뿌리를 내립니다 — 템플릿·레벨은 스크립트가 부모 관계에서 셈하므로 당신은 **부모 관계를 정하는 지식**을 답합니다.
아래 지침(그래프·템플릿·오차 기준)에 따라 답하세요.
- types: 유형마다 하나 — role(heading·label·subtitle·title·note·not_heading), parents(이 레터가 **보통 매달리는 부모 레터 키** 목록 — 유형 표의 key 값, 구분 라벨 아래 내용이면
  라벨 키 "[구분 기준]"(예 "[기관]"), 괄호 소제목 아래 내용이면 "[…]", 문서 맨 위면 "root"; label·subtitle·note·not_heading·title 은 빈 목록), variantOf(같은 레터로 볼 다른 유형 id —
  없으면 ""; label·subtitle 은 ""), basis(구분 라벨·구분 값 제목의 구분 기준 이름 — **bases 목록의 이름만**, 겹치면 "단계-차년도" 처럼 이음, 없으면 ""), reason(예외·판단 근거 한 문장,
  없으면 "").
- **label(구분 라벨)은 그 글이 구분 기준(bases)의 값일 때만**입니다(「[1단계]」「[2차년도 목표]」「[주관연구개발기관(기관명 기입)]」 — 기관 이름만 적힌 「[한국선급]」 도 기관).
  구분 기준 값이 아닌 괄호 글(「[국내 기술 동향 및 수준]」「[최종목표]」「[과학·기술적 측면]」)은 **subtitle(괄호 소제목)** 이고 basis 는 "" 입니다 — bases 에 없는 이름(「측면」「구분」)을
  지어내지 않습니다. 유형 표의 key 가 이미 "[기관]"·"[…]" 로 적힌 괄호 유형은 스크립트가 글의 꼴이나 사용자 지정으로 정한 것입니다(그대로 두면 됩니다). 빈 「[  ]」·「[ √ ]」 는 not_heading.
- division(연구개발과제 문서에만 옴) = 헤딩보다 먼저 돈 **구분 기준 판독**(스크립트)의 유형별 수: confirmed = 그 유형의 줄 of 개 가운데 판독이 basis 의 값으로 확인한 줄 · conflict = 근거가 엇갈린 줄 ·
  names = 줄이 프로젝트 구성의 기관 이름뿐인 줄(「[한국선급]」 — 기관 자리인지는 당신이 앞뒤를 보고 정합니다: 기술 동향 절의 회사 이름 나열이면 subtitle). 줄 **모두**가 확인된 괄호 유형은 스크립트가 구분 라벨로 정합니다.
  일부만 확인된 유형은 유형 전체를 label 로 답하지 마세요 — 괄호 줄이 아닌 유형(「(N)」 에 「(1) 1차년도」 와 「(2) 기술목표」 가 섞임)을 label 로 답해도 스크립트가 받지 않습니다. 판단 근거는 reason 에.
  구분 라벨·괄호 소제목은 둘 다 그 줄부터 새 템플릿(그 줄 = L1, 아래 내용 = L2…)이므로 그 아래 「o」 의 parents 에는 그 키("[기관]"·"[…]")를 적습니다.
  같은 레터가 여러 자리에 쓰이면 parents 에 그 부모 레터를 모두 적습니다(예 □: ["N-N.", "(N)"]).
- mainChain: 본문 주 사슬의 레터 키 열(1레벨부터 — 예 ["N.", "N-N.", "(N)", "o", "-", "·"]). 제안이 맞으면 그대로, 틀리면 고친 사슬. 번호형 → 기호형 전환은 끊는 곳이 아닙니다.
- summary: 문서 개요 체계 요약 두세 문장(주 사슬·가지·라벨).
입력에 없는 유형 id·레터 키는 쓰지 않습니다. 쓰지 않는 칸은 빈 문자열·빈 목록."""

SECTION_SCHEMA = _schema({"changes": _arr(_schema({"id": S, "parent": S, "role": {"type": "string", "enum": ["heading", "label", "subtitle", "title", "note", "not_heading"]},
                                                   "basis": S, "template": S, "level": I, "reason": S})), "summary": S})

SECTION_CONTRACT = """당신은 한글 양식 문서의 헤딩 그래프를 검토하는 분석가입니다. 스크립트가 유형 판정(A)과 부모 규칙으로 쌓은 초안 그래프의 한 구간을 받습니다.
노드 행 = [id, 유형, 글 앞부분, 초안 부모 id, 초안 템플릿(앵커), 초안 레벨, 초안 구분 라벨 id]. 부모 "root" = 문서 맨 위, 조상 사슬 = 이 구간 앞에서 열린 노드들.
templates = 초안의 템플릿 목록(anchor = scope:레터 사슬). 지침에 따라 **초안과 다르게 해야 하는 노드만** changes 에 적으세요 — 바꾸지 않을 노드는 적지 않습니다.
- parent = 의미 부모(이 구간 노드·조상 사슬 id·"root" 중 하나, 문서 순으로 앞). 구분 라벨·괄호 소제목은 제 템플릿의 뿌리이므로 그 아래 내용은 **그 줄을 부모로** 적습니다.
- role = 역할(바꾸지 않으면 초안 값). label(구분 라벨)로 바꿀 때만 basis 에 구분 기준 이름을 적습니다 — **bases 목록의 이름만**(그 밖에는 ""). 구분 기준 값이 아닌 괄호 글은
  subtitle(괄호 소제목)입니다 — bases 에 없는 이름을 지어내지 않습니다. template·level 은 **슬롯 예외**에만 적습니다 — 부모만으로 구별되지 않는 경우(예: 「(N)」 을 건너뛴 주 사슬 4레벨 「o」 가 새 가지가 아니라
  주 사슬 L4 일 때 template = 주 사슬 앵커, level = 4). 그 밖에는 template "" · level 0(스크립트가 부모 관계에서 셈함).
- reason = 바꾸는 까닭 한 문장(한국어). 적는 노드에서 바꾸지 않는 칸(parent·role)은 초안 값을 그대로 옮겨 적습니다.
- 확신이 없으면 바꾸지 않습니다. summary = 이 구간 판단 요약 한 문장."""


FORMAT_SCHEMA = _schema({"pairs": _arr(_schema({"slot": S, "a": S, "b": S, "same": B, "reason": S})), "summary": S})

FORMAT_CONTRACT = """당신은 한글 양식 문서의 서식 통일(조정)을 판단하는 분석가입니다. 그래프로 정한 템플릿 슬롯(같은 템플릿·같은 레벨)마다, 슬롯 대표 서식 라벨 a 와
그 슬롯에 함께 쓰인 다른 서식 라벨 b 의 쌍을 받습니다(이름 = 사람이 읽는 서식 요약, examples = b 서식 문단 글 앞부분).
쌍마다 하나씩 답하세요(slot·a·b 는 입력 그대로): same = b 를 a 로 조정해도 되는 같은 구실(같은 단계의 보통 항목 — 오차·우연한 차이)이면 true,
일부러 다른 서식(소제목·안내·인용·상자 글·자리표시·강조·다른 역할)이면 false. reason = 한 문장(한국어). 확신이 없으면 false. summary = 한두 문장.
아래 지침(조정·오차 기준)을 따르세요."""


# ---- D 호출(조정 재검토 — 자료·적용은 heading_graph.review_pairs/apply_review) -------------------------------------------

REVIEW_SCHEMA = _schema({"pairs": _arr(_schema({"slot": S, "a": S, "b": S, "verdict": {"type": "string", "enum": ["agree", "disagree"]}, "same": B, "reason": S})),
                         "summary": S})

REVIEW_CONTRACT = """당신은 한글 양식 문서의 서식 통일(조정) 판정을 **재검토**하는 분석가입니다. 앞선 판정자(다른 호출)가 템플릿 슬롯(같은 템플릿·같은 레벨)마다
슬롯 대표 서식 라벨 a 와 그 슬롯에 함께 쓰인 다른 서식 라벨 b 의 쌍에 내린 1차 판정을 받습니다 — first.same true = b 를 a 로 조정(같은 구실), false = 다름 유지, first.reason = 그 까닭.
aName·bName 은 사람이 읽는 서식 요약(글꼴·크기·굵게·정렬·여백·간격·레터 앞 빈칸), examples = b 서식 문단 글 앞부분.
1차 까닭을 그대로 믿지 말고, 먼저 서식 이름과 예문으로 **스스로 판정**한 뒤 1차와 견주어 반박할 수 있는지 보세요.
쌍마다 하나씩 답하세요(slot·a·b 는 입력 그대로): same = 당신의 판정(b 를 a 로 조정해도 되는 같은 구실 — 같은 단계의 보통 항목, 오차·우연한 차이 — 이면 true,
일부러 다른 서식(소제목·안내·인용·상자 글·자리표시·강조·다른 역할)이면 false), verdict = 1차와 같으면 "agree", 다르면 "disagree",
reason = 한 문장(한국어 — disagree 면 1차 판정이 틀린 까닭). 확신이 없으면 same false 로 답합니다(1차가 조정이면 불일치가 되어 사람이 정하는 미판정으로 남고,
1차가 다름 유지면 동의). summary = 한두 문장.
입력에 없는 쌍은 쓰지 않습니다. 아래 지침(조정·재검토·오차 기준)을 따르세요."""


# ---- 3단계 T 호출(표 구조 — 자료·적용은 heading_tables) -------------------------------------------------------------

TABLES_SCHEMA = _schema({
    "tables": _arr(_schema({
        "table": S,
        "subtables": _arr(_schema({"sub": S, "rows": _arr(I), "cols": _arr(I),
                                   "kind": {"type": "string", "enum": ["matrix", "form", "list", "title", "note", "spacer", "plain"]},
                                   "headerRows": I, "headerCols": I, "note": S})),
        "cells": _arr(_schema({"cell": S, "role": {"type": "string", "enum": ["colhead", "rowhead", "corner", "field", "title", "note", "spacer"]}, "reason": S})),
        "summary": S})),
    "summary": S})

TABLES_CONTRACT = """당신은 한글 양식 문서의 표 구조를 판정하는 분석가입니다. 표마다 격자(grid — 행마다 칸 토큰 목록)와 스크립트 초안(draft — 서브 테이블 띠·헤더 행/열 수)을 받습니다.
칸 토큰 = "칸id|행수x열수|표지|글 앞 30자|초안 역할". 표지: F 음영 · B 굵게 · 문단 종류 T 보통 글 L 괄호 라벨 D 값 P 자리표시 N 안내(※) M 글머리 E 빈 문단 O 개체(중첩 표).
"^" = 위 칸이 내려와 덮은 자리, "<" = 왼쪽 칸이 뻗어 덮은 자리, 칸id 만 있는 토큰 = 빈 1×1 칸(초안 field). before = 표 바로 앞 문단 글(표 제목 맥락).
역할: colhead(열헤더 — 아래 칸들의 이름) · rowhead(행헤더 — 오른쪽 칸들의 이름, 키-값 양식의 키 포함) · corner(헤더 행과 헤더 열이 겹치는 귀퉁이) ·
field(채우는 값 칸 — 빈 칸·자리표시·값·체크 칸) · title(서브 테이블 전체 너비의 제목) · note(※·작성 요령 안내) · spacer(빈 전체 너비 행).
**음영·굵게는 힌트일 뿐 — 칸의 값(글)을 보고 판단하세요**: 짧은 이름씨 = 헤더, 빈 칸·「YYYY.MM」「00%」「(  )」「[ ]」 = 필드, 「1차년도 … n차년도」 같은 차례 = 헤더 차례.
표마다 하나씩 답하세요(table = 입력 id 그대로):
- subtables: 표를 겹치지 않는 직사각형 영역으로 **빠짐없이** 나눕니다(rows·cols = [시작, 끝) 격자 번호, 병합 칸을 가르면 안 됨). 헤더 구조가 다시 시작하는 곳(헤더 행이 다시 오는 곳,
  키-값 묶음이 바뀌는 곳, 나란히 놓인 독립 블록, 전체 너비 제목·안내 행)에서 나누고, 헤더가 한 묶음이면 하나로 둡니다. 영역마다 sub(짧은 이름 A·B·…), kind(matrix 열헤더+필드 ·
  form 행헤더(키)+필드 · list 한 열 · title · note · spacer · plain), headerRows(위에서 열헤더인 행 수), headerCols(왼쪽에서 행헤더인 격자 열 수 — 병합 칸이면 그 너비만큼), note(까닭 한 문장 또는 "").
  헤더 수를 모르면 -1(스크립트 값 그대로). 초안이 맞으면 초안 영역을 그대로 적습니다.
- cells: 헤더 수로 정해지는 역할과 **다르게 볼 칸만** {cell, role, reason} — 예: 헤더 행 안의 값 칸, 키-값 양식의 키(rowhead), 표 안 안내 글(note), 체크 항목 라벨(rowhead).
  바꾸지 않을 칸은 적지 않습니다. 확신이 없으면 초안을 둡니다.
- summary: 그 표의 구조 한 문장(한국어). 맨 바깥 summary = 전체 한두 문장.
입력에 없는 표·칸 id 는 쓰지 않습니다. 쓰지 않는 칸은 빈 문자열·빈 목록·-1. 아래 지침(표 구조·오차 기준)을 따르세요."""


FORM_NOTE = ("위 지침은 모든 문서에 쓰는 일반 기준이고, 아래는 **이 문서의 양식**에 대해 사용자가 따로 관리하는 사실·판단입니다 — 지침의 일반 기준과 다르면 "
             "이 양식에 대해서는 아래 내용을 따르세요. 계약(맨 위)과 어긋나면 계약을 따릅니다.")


def prompt(contract, guide_names, data, pinned=None):
    """프롬프트 = 고정 계약 + 지침(이름 순) + 양식 정보(있으면) + 자료 JSON → (글, 쓴 지침 {이름: sha1}).
    pinned = 실행 시작 때 고정한 지침(heading_guides.snapshot() 꼴) — 있으면 지금 저장소 대신 그 글을 쓴다.
    pinned["form"] = 이 문서의 양식 정보(heading_forms.pin — spec ② §12): 일반 지침 뒤에 따로 한 절로 붙고 used 에 "form" 으로 남는다."""
    parts, used = [contract, ""], {}
    for name in guide_names:
        g = (pinned or {}).get(name) or G.get(name)
        used[name] = g["sha1"]
        parts += [f"## 지침 — {G.TITLES[name]} ({name})", g["text"].strip(), ""]
    form = (pinned or {}).get("form")
    form_text = F.without(F.without(F.body(form.get("text")), F.DIVISION_SECTION), F.LINK_SECTION) if form else ""   # 「자리 연결」 절(연결 코멘트 — spec_병합 ② §5-3)은 병합 검토의 몫 · 「구분 기준 자리」 절은 구분 기준 검토의 몫 — 헤딩 추출에는 안 보낸다(② §12 「쓰이는 곳」)
    if form_text:
        used["form"] = form["sha1"]
        parts += [f"## 양식 정보 — {form.get('name') or form.get('key')} (이 양식에만 해당)", FORM_NOTE, form_text, ""]
    parts += ["## 자료(JSON)", json.dumps(data, ensure_ascii=False, separators=(",", ":"))]
    return "\n".join(parts), used


def _call_record(job, res):
    return {"what": job["what"], "prompt": job["content"], "schema": job["schema"], "response": res.get("data"), "backend": res.get("backend"),
            "model": res.get("model"), "effort": res.get("effort"), "ms": res.get("ms"), "costUsd": res.get("costUsd"), "error": res.get("error"),
            "retried": res.get("retried", False)}


# ---- 1단계 규칙 보강 -------------------------------------------------------------------------------------

def rule_groups(result, limit=None):
    """보강 대상 묶음 → LLM 입력 꼴 [{group, type, shape, count, rules?, examples}]."""
    out = []
    for g in result["review"]["unmatched"]:
        out.append({"group": g["key"], "type": "unmatched", "shape": g["shape"], "count": g["count"], "examples": g["examples"]})
    for g in result["review"]["conflicts"]:
        out.append({"group": g["key"], "type": "conflict", "shape": g["shape"], "count": g["count"], "rules": g["rules"], "examples": g["examples"]})
    return out[:limit] if limit else out


def rule_jobs(result, store=None, groups=None, pinned=None):
    st = store if store is not None else R.load()
    groups = rule_groups(result) if groups is None else groups
    builtin = [{"id": r["id"], "name": r["name"], "kind": r["kind"], "scope": r["scope"]} for r in R.BUILTIN]
    learned = [{"id": r["id"], "name": r["name"], "kind": r["kind"], "pattern": r["pattern"], "scope": r.get("scope"), "status": r.get("status")}
               for r in st.get("rules") or [] if r.get("enabled", True)]
    jobs, guides = [], {}
    for i in range(0, len(groups), BATCH_GROUPS):
        content, used = prompt(RULES_CONTRACT, ["rules"], {"builtinRules": builtin, "learnedRules": learned, "groups": groups[i:i + BATCH_GROUPS]}, pinned)
        guides.update(used)
        jobs.append({"schema": RULES_SCHEMA, "content": content, "what": f"heading_rules#{i // BATCH_GROUPS + 1}", "timeout": 600.0, "effort": "low"})
    return jobs, guides


def check_proposal(item, group, result, store, doc_key):
    """LLM 제안 하나 검증 → (규칙 dict | None, 판정 {verdict, why, test})."""
    rule = {"name": item.get("name") or item.get("family"), "kind": item.get("kind"), "family": item.get("family"), "pattern": item.get("pattern"),
            "scope": item.get("scope") or "prefix", "first": bool(item.get("first")) and group["type"] == "conflict",
            "globalHint": bool(item.get("globalHint")), "note": item.get("reason") or ""}
    targets = set(group["ids"])
    t = E.test_rule(rule, result, store, doc_key=doc_key, targets=targets)
    verdict = {"verdict": "rejected", "why": "", "test": {k: t[k] for k in ("fixed", "taken", "broken", "takenExamples", "brokenExamples", "error")}}
    if t["error"]:
        verdict["why"] = f"규칙 오류: {t['error']}"
        return None, verdict
    if not t["ok"]:
        verdict["why"] = "정규식이 시간 제한을 넘음"
        return None, verdict
    changed = {c["id"]: c for c in t["changed"]}
    pos = [p for p in item.get("positives") or [] if p in targets]
    miss = [p for p in pos if p not in changed or changed[p]["after"][0] != rule["kind"]]
    if t["fixed"] == 0:
        verdict["why"] = "대상 문단을 하나도 못 고침"
        return None, verdict
    if miss:
        verdict["why"] = f"positives 중 맞지 않는 예문 {len(miss)}개({', '.join(miss[:3])})"
        return None, verdict
    trial = {**R._clean_rule({**rule, "status": "candidate"}, source="llm"), "id": "neg"}
    probe = R.active({"rules": [], "builtin": {}}, [trial])
    run = R._Run()
    neg = next(r for r in probe if r["id"] == "neg")
    for text in (item.get("negatives") or [])[:5]:
        lead, body = R.split_lead(str(text))
        first = body.split(R.BR, 1)[0]
        whole = rule["scope"] == "whole"
        m = run.match(neg, first.strip() if whole else first[:R.MATCH_TEXT_MAX], whole)
        if m is not None and (whole or m.end() > 0):
            verdict["why"] = f"negatives 「{str(text)[:30]}」 에도 맞음"
            return None, verdict
    plain = sum(1 for r in result["paras"] if r["kind"] == "plain" and not r["rule"])
    if t["broken"]:
        verdict["why"] = f"묶음 밖 판정 {t['broken']}개를 바꿈"
        return None, verdict
    if rule["first"] and t["taken"]:
        verdict["why"] = f"앞선 규칙이 묶음 밖 문단 {t['taken']}개를 바꿈"
        return None, verdict
    if t["taken"] > max(3, plain // 100):  # plain 규칙도 같다 — 레터·서식 라벨·검토 묶음을 바꾼다(spec ② §3 빼앗음 검사)
        verdict["why"] = f"너무 넓음 — 묶음 밖 보통 글 {t['taken']}개를 가져감"
        return None, verdict
    verdict.update(verdict="saved", why=f"고침 {t['fixed']} · 묶음 밖 보통 글 {t['taken']}")
    return rule, verdict


def propose_rules(result, *, doc_key, doc_name="", store=None, ask=None, save=True, run_id=None, pinned=None):
    """1단계 규칙 보강 — LLM 제안을 검증해 저장 → {"items": [...], "saved": [규칙 id], "kept": [key], "calls": [...], "guides", "seconds", "costUsd", "error"}.
    ask = llm.ask_all 대신 쓸 함수(시험). save=False 면 저장하지 않고 판정만. pinned = 실행 시작 때 고정한 지침(heading_guides.snapshot() 꼴)."""
    t0 = time.monotonic()
    st = store if store is not None else R.load()
    groups = rule_groups(result)
    by_key = {g["key"]: g for g in result["review"]["unmatched"] + result["review"]["conflicts"]}
    report = {"items": [], "saved": [], "kept": [], "calls": [], "guides": {}, "groups": len(groups), "seconds": 0, "costUsd": 0.0, "error": None}
    if not groups:
        return report
    jobs, report["guides"] = rule_jobs(result, st, groups, pinned)
    results = (ask or llm.ask_all)(jobs)
    to_save, keeps = [], []
    known = {(r.get("kind"), r.get("scope", "prefix"), r.get("pattern"), bool(r.get("first"))): r.get("id") for r in st.get("rules") or []}
    for job, res in zip(jobs, results):
        report["calls"].append(_call_record(job, res))
        report["costUsd"] += res.get("costUsd") or 0
        if res.get("data") is None:
            report["error"] = res.get("error") or "LLM 응답 없음"
            continue
        for item in res["data"].get("items") or []:
            g = by_key.get(item.get("group"))
            if g is None:
                continue
            entry = {"group": g["key"], "decision": item.get("decision"), "reason": item.get("reason"), "rule": None}
            if item.get("decision") == "rule":
                rule, verdict = check_proposal(item, {**g, "type": "conflict" if g["key"].startswith("c:") else "unmatched"}, result, st, doc_key)
                entry.update(rule={k: item.get(k) for k in ("name", "kind", "family", "pattern", "scope", "first", "globalHint")}, **verdict)
                if rule:
                    sig = (rule["kind"], rule["scope"], rule["pattern"], rule["first"])
                    if sig in known:  # 같은 규칙이 이미 있거나 이번에 이미 저장할 것 — 두 번 넣지 않는다
                        entry.update(verdict="duplicate", why=f"같은 규칙이 이미 있음({known[sig] or '이번 실행'})", id=known[sig])
                    else:
                        known[sig] = None
                        rule.update(docs=[doc_key] if doc_key else [], examples=[e["text"] for e in g["examples"][:3]],
                                    provenance={"model": res.get("model"), "guide": report["guides"].get("rules"), "run": run_id,
                                                "doc": doc_name, "group": g["key"]})
                        to_save.append((entry, rule))
            elif item.get("decision") == "keep" and g["key"].startswith("c:"):
                entry["verdict"] = "kept"
                keeps.append(g["key"])
            else:
                entry["verdict"] = "unsure"
            report["items"].append(entry)
    if save and to_save:
        _, ids = R.add_rules([r for _, r in to_save], source="llm", event={"reason": "LLM 규칙 보강", "doc": doc_name, "run": run_id})
        for (entry, _), rid in zip(to_save, ids):
            entry["id"] = rid
        report["saved"] = ids
    if save and keeps:
        R.add_keeps(keeps, reason="LLM: 이긴 규칙이 맞음")
        report["kept"] = keeps
    report["seconds"] = round(time.monotonic() - t0, 2)
    report["costUsd"] = round(report["costUsd"], 4)
    return report
