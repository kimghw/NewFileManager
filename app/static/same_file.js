// 같은 파일 고르기 · 작업 내용 초기화(spec_작업 ② §1 「같은 파일은 묻고 연다」 · ② §3-1 — 2026-11-18 사용자
// "파일이 같으면 그냥 새프로젝트로 할건지 기존 프로젝트 이어서 할건지 물어봐주고, 작업한 내용 초기화 하는 기능도 넣어줘" → 답 「새 작업 + 프로젝트 칸」 · 「문서 + 분석·결과 모두」).
// 올릴 때 POST /api/docs?ask=1 — 같은 파일로 하던 작업이 있으면 서버가 열지 않고 {ask, name, same[…]} 로 답하고, 이 파일이 떠 있는 창(design.md §16 — 모달 아님)으로 묻는다.
// 부르는 곳: app.js openFile · homeTaskStart · 「고친 문단」 탭 확정 상자(workResetAsk) · home_files.js hfOpenTarget · homeFilesPlain.
// app.js 의 el · hBtn · api · toast · fmtWhen · nf · workTaskInfo · taskChipEl · worksList · state · flushAll 에 기댄다(app.js 다음에 읽는다).

let sfOpen = null; // 열린 창 {box, done(값)} — 한 번에 하나

const SF_RESET_LOSE = "고친 문단 · 헤딩/표 분석 · LLM 결과 · 서식 정리 계획 · 에이전트 대화와 자료 · 작성 지침 저장본 · 양식 검토 · 검증 기록";
const SF_RESET_KEEP = "올린 원본 · 확정 기록 · 작업 기록 · 프로젝트 · 워크플로우 · 라운드 · 프로젝트 구성";

// file 을 올린다 — 같은 파일로 하던 작업이 있으면 묻는다. → 고른 것 | null(창을 닫음 — 아무것도 열지 않음)
//   {act: "fresh", r}  같은 파일 작업이 없어 새 작업을 만들었다(r = 올리기 응답 · reused false)
//   {act: "use", r}    고른 작업을 이어 열었다(r.reused true)
//   {act: "reset", r}  고른 작업을 초기화했다(r = {docId, reused: false, reset}) — 부른 쪽이 load · 첫 분석
//   {act: "new", r, project}  새 작업으로(r.reused false · project = 창의 프로젝트 칸 — TASK 로 시작할 때만, 비우면 "")
//   {act: "open", id}  「그대로 열기」 — 다른 TASK · 프로젝트 · 역할이던 작업: 부른 쪽이 그 작업을 그대로 열고 TASK 시작은 멈춘다
// opts: job(고른 TASK — 줄 차례 · 프로젝트 칸) · project(프로젝트 칸의 처음 값) · fit(row) → true(이어서 · 초기화) | 글(그대로 열기만 — 까닭) · onAsk(응답) — 창을 띄우기 직전
async function sameFileUpload(file, opts = {}) {
  const job = opts.job || "", q = job ? `&job=${encodeURIComponent(job)}` : "";
  const send = async (query) => { const fd = new FormData(); fd.append("file", file); return api(`/api/docs?${query}`, { method: "POST", body: fd }); };
  const r = await send(`ask=1${q}`);
  if (!r.ask) return { act: "fresh", r };
  setSaveState("", "");
  if (opts.onAsk) opts.onAsk(r); // 부른 쪽의 「올리는 중…」 글을 「고르세요」 로(시작 화면 문서 목록)
  const pick = await sameFilePick(r, opts);
  if (!pick) return null;
  if (pick.act === "open") return pick;
  setSaveState("busy", pick.act === "reset" ? "작업 내용 초기화 중…" : `${file.name} 여는 중…`);
  if (pick.act === "use") return { act: "use", r: { ...(await send(`use=${pick.id}${q}`)), picked: true } };
  if (pick.act === "reset") return { act: "reset", r: await workReset(pick.id) };
  return { act: "new", r: await send("new=1"), project: pick.project || "" };
}

// 작업 내용 초기화(② §3-1) — 지금 연 문서면 반영 대기 중인 글을 먼저 보낸다(늦게 닿은 편집이 초기화한 문서를 고치지 않게) → {docId, reused: false, reset}
async function workReset(id, { keep = "" } = {}) { // keep "materials" = 이 문서의 자료는 남긴다(양식 작성의 「준비 초기화」 — form_write.js fwStageReset)
  if (state.id === id) {
    const run = typeof agwRunning === "function" ? agwRunning() : null;
    if (run) throw new Error(`「${run.label}」 이(가) 도는 중입니다 — 끝난 뒤에 초기화하세요`);
    await flushAll();
  }
  const d = await api(`/api/works/${id}/reset${keep ? `?keep=${keep}` : ""}`, { method: "POST" });
  document.dispatchEvent(new CustomEvent("nfm:work-reset", { detail: { id } })); // 문서 id 로 기억을 묶어 둔 화면 모듈(form_write.js 등)이 그 문서의 기억을 버린다 — 초기화해도 id 는 같다
  return { docId: id, name: d.name, reused: false, reset: d.reset };
}

function sfClose(value = null) {
  if (!sfOpen) return;
  const { box, done } = sfOpen;
  sfOpen = null;
  box.remove();
  document.removeEventListener("keydown", sfKey, true);
  done(value);
}

function sfKey(e) { if (e.key === "Escape" && sfOpen) { e.preventDefault(); e.stopPropagation(); sfClose(null); } }

function sfRowMeta(w) { // 만듦 · 바뀜 · 고친 문단 · 확정
  return [`만듦 ${fmtWhen(w.created)}`, w.updated ? `바뀜 ${fmtWhen(w.updated)}` : "", w.edited ? `고친 문단 ${nf(w.edited)}개` : "고친 문단 없음", w.commits ? `확정 ${w.commits}` : ""].filter(Boolean).join(" · ");
}

// 창 — 하던 작업마다 한 줄 + 「새 작업으로 시작」. 고른 것 {act, id?, project?} | null 로 끝난다
function sameFilePick(r, opts = {}) {
  sfClose(null); // 앞의 창은 아무것도 열지 않고 닫는다
  return new Promise((done) => {
    const box = el("div", "sf-pop"), head = el("div", "sf-head"), x = el("button", "sf-x", "✕");
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-label", "같은 파일 고르기");
    x.type = "button";
    x.title = "닫기(Esc) — 아무것도 열지 않습니다";
    x.setAttribute("aria-label", "닫기");
    x.onclick = () => sfClose(null);
    const title = el("div", "sf-title");
    title.append(el("strong", null, "같은 파일로 하던 작업이 있습니다"), el("span", "sf-file", r.name));
    head.append(title, x);
    const list = el("ul", "sf-list");
    let confirmAt = ""; // 초기화 확인 줄을 편 작업 id
    const draw = () => {
      list.textContent = "";
      for (const w of r.same) {
        const ok = opts.fit ? opts.fit(w) : true, T = workTaskInfo(w), li = el("li", "sf-row");
        li.dataset.work = w.id;
        const info = el("div", "sf-info"), top = el("div", "sf-top");
        top.append(taskChipEl(T)); // TASK 없이 연 작업은 칩(「TASK 없음」)만 — 프로젝트 · 라운드는 TASK 의 것
        if (T.job) top.append(el("span", "sf-what", `${T.project ? `프로젝트 「${T.project}」` : "프로젝트 미지정"} · Round ${taskRound(w.task)}${T.role ? ` · ${T.role}` : ""}`));
        info.append(top, el("div", "sf-meta", sfRowMeta(w)));
        if (ok !== true) info.append(el("div", "sf-why", `${ok} — 그 작업을 그대로 엽니다`));
        const acts = el("div", "sf-acts");
        if (ok === true) {
          const go = hBtn("이어서", () => sfClose({ act: "use", id: w.id }), { cls: "btn sm primary", title: "이 작업을 이어서 엽니다" });
          go.dataset.sf = "use";
          const rs = hBtn("초기화하고 열기", () => { confirmAt = confirmAt === w.id ? "" : w.id; draw(); const c = list.querySelector('[data-sf="reset-ok"]'); if (c) c.focus(); },
            { cls: "btn sm" + (confirmAt === w.id ? " on" : ""), title: `이 작업을 올린 직후로 되돌리고 엽니다 — 누르면 아래에서 확인합니다` });
          rs.dataset.sf = "reset";
          rs.setAttribute("aria-expanded", String(confirmAt === w.id));
          acts.append(go, rs);
        } else {
          const open = hBtn("그대로 열기", () => sfClose({ act: "open", id: w.id }), { cls: "btn sm", title: "그 작업을 그 워크플로우 그대로 엽니다 — 이 워크플로우 시작은 멈춥니다" });
          open.dataset.sf = "open";
          acts.append(open);
        }
        li.append(info, acts);
        if (confirmAt === w.id) {
          const c = el("div", "sf-confirm");
          c.setAttribute("role", "group");
          c.setAttribute("aria-label", "초기화 확인");
          c.append(el("p", null, `${w.edited ? `고친 문단 ${nf(w.edited)}개와 ` : ""}${SF_RESET_LOSE}을 비우고 올린 원본으로 엽니다. 남는 것: ${SF_RESET_KEEP}. 비운 것은 작업 폴더 reset/ 에 옮겨 둡니다.`));
          const row = el("div", "sf-confirm-acts");
          const yes = hBtn("초기화", () => sfClose({ act: "reset", id: w.id }), { cls: "btn sm project-danger" });
          yes.dataset.sf = "reset-ok";
          row.append(yes, hBtn("취소", () => { confirmAt = ""; draw(); }));
          c.append(row);
          li.append(c);
        }
        list.append(li);
      }
    };
    draw();
    const foot = el("div", "sf-new");
    let input = null;
    if (opts.job) {
      const lab = el("label", "sf-k", "프로젝트"), id = "sfProject";
      input = el("input");
      input.id = id;
      lab.htmlFor = id;
      input.maxLength = 60;
      input.placeholder = "비우면 임시 이름"; // 비우면 서버가 「임시 프로젝트 N」 을 붙인다(spec_작업 ② §17 「임시 프로젝트」 — home_files.js hfOpenTarget)
      input.value = opts.project || "";
      input.setAttribute("list", "sfProjects");
      const dl = el("datalist");
      dl.id = "sfProjects";
      for (const name of [...new Set((typeof worksList !== "undefined" ? worksList : []).map((w) => (w.task || {}).project).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ko"))) dl.append(new Option(name));
      const row = el("div", "sf-grid");
      row.append(lab, input, dl);
      foot.append(row);
    }
    const fresh = hBtn("새 작업으로 시작", () => sfClose({ act: "new", project: input ? input.value.trim() : "" }),
      { cls: "btn sm", title: "올린 원본부터 새 작업을 만듭니다" + (opts.job ? " — 프로젝트 칸에 적으면 그 프로젝트의 이 워크플로우 다음 라운드로 · 비우면 임시 이름(임시 프로젝트 N)으로" : "") });
    fresh.dataset.sf = "new";
    const acts = el("div", "sf-new-acts");
    acts.append(fresh, el("span", "sf-note", "하던 작업은 목록에 그대로 남습니다"));
    foot.append(acts);
    box.append(head, list, foot);
    document.body.append(box);
    sfOpen = { box, done };
    document.addEventListener("keydown", sfKey, true);
    const first = box.querySelector('[data-sf="use"]') || box.querySelector('[data-sf="open"]') || fresh;
    first.focus();
  });
}

// 「고친 문단」 탭 확정 상자의 「작업 내용 초기화…」(② §3-1) — 지금 연 작업을 올린 직후로
async function workResetAsk() {
  if (!state.id || !state.stored || state.commitBusy) return;
  const id = state.id, run = typeof agwRunning === "function" ? agwRunning() : null;
  if (run) { toast(`「${run.label}」 이(가) 도는 중입니다 — 끝난 뒤에 초기화하세요`, true); return; }
  const n = state.edited.size;
  if (!confirm(`이 작업을 올린 직후로 되돌릴까요?\n\n비우는 것: ${n ? `고친 문단 ${nf(n)}개 · ` : ""}${SF_RESET_LOSE}\n남는 것: ${SF_RESET_KEEP}\n\n비운 것은 작업 폴더의 reset/ 에 옮겨 두고 화면에서는 되살리지 않습니다.`)) return;
  state.commitBusy = "reset";
  if (typeof commitBar === "function") commitBar();
  setSaveState("busy", "작업 내용 초기화 중…");
  try {
    await workReset(id);
    state.commitBusy = false;
    await load(id);
    firstRun(); // 새 작업과 같다 — 첫 분석(② §9)
    toast("작업 내용을 초기화했습니다 — 올린 원본부터 다시 시작합니다");
  } catch (e) {
    state.commitBusy = false;
    setSaveState("err", "초기화하지 못함");
    toast(`작업 내용을 초기화하지 못했습니다: ${e.message}`, true);
    if (state.id === id && typeof commitBar === "function") commitBar();
  }
  loadWorks();
}
