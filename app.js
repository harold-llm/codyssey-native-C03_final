/* 꽃피다(Bloomy) 프론트엔드 — 바닐라 JS, 상태는 메모리에만 (토큰은 localStorage) */
"use strict";

const STAGES = {
  1: "듣기",
  2: "그림책 노출",
  3: "짧은 문장",
  4: "초기 독해",
  5: "문장 산출",
};
const STAGE_DESC = {
  1: "노래·동요로 영어의 리듬과 소리에 익숙해지기",
  2: "그림책과 영상에서 문장을 듣고 뜻에 맞추기",
  3: "짧은 문장을 따라 하고 직접 말해 보기",
  4: "글자와 소리를 연결해 쉬운 책을 읽기 시작하기",
  5: "자기 경험으로 짧은 영어 문장을 만들어 말하기",
};
const CASE_BADGE = {
  A: { text: "순항", cls: "" },
  B: { text: "편한 속도", cls: "badge-peach" },
  C: { text: "맞춤 조정", cls: "badge-pink" },
};

const state = {
  token: localStorage.getItem("bloomy_token") || null,
  account: null,
  children: [],
  childId: null,
  view: "today", // today | coach | report | library | mine
  authMode: "login",
  fb: { completion: null, satisfaction: null, interest: null, comprehension: null },
  lib: { stage: "", type: "", keyword: "" },
};

const $app = () => document.getElementById("app");
const $modal = () => document.getElementById("modal");

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function api(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* 비JSON */ }
  if (res.status === 401) {
    logout();
    throw new Error((data && data.error) || "로그인이 필요합니다");
  }
  if (!res.ok) throw new Error((data && data.error) || "요청에 실패했습니다");
  return data;
}

function logout() {
  localStorage.removeItem("bloomy_token");
  state.token = null;
  state.account = null;
  state.children = [];
  state.childId = null;
  render();
}

/* =========================================================================
 * 인증
 * ========================================================================= */

async function submitAuth(e) {
  e.preventDefault();
  const msgEl = document.getElementById("auth-msg");
  msgEl.textContent = "";
  const email = document.getElementById("f-email").value.trim();
  const password = document.getElementById("f-password").value;
  try {
    const data =
      state.authMode === "login"
        ? await api("POST", "/api/login", { email, password })
        : await api("POST", "/api/register", { email, password });
    state.token = data.token;
    localStorage.setItem("bloomy_token", data.token);
    state.account = data.account;
    state.children = data.children || [];
    state.childId = state.children.length ? state.children[0].id : null;
    render();
  } catch (err) {
    msgEl.textContent = err.message;
  }
}

function switchAuth(mode) {
  state.authMode = mode;
  render();
}

/* =========================================================================
 * 온보딩
 * ========================================================================= */

async function submitOnboard(e) {
  e.preventDefault();
  const msgEl = document.getElementById("auth-msg");
  msgEl.textContent = "";
  const body = {
    age: parseInt(document.getElementById("o-age").value, 10),
    nickname: document.getElementById("o-nickname").value.trim(),
    ek_kindergarten: document.getElementById("o-ek").checked,
    exposure: document.getElementById("o-exposure").value,
    daily_minutes: parseInt(document.getElementById("o-minutes").value, 10),
  };
  try {
    const data = await api("POST", "/api/children", body);
    state.children = [data.child];
    state.childId = data.child.id;
    state.fb = { completion: null, satisfaction: null, interest: null, comprehension: null };
    render();
  } catch (err) {
    msgEl.textContent = err.message;
  }
}

function addAnotherChild() {
  const form = document.getElementById("onboard-form");
  if (form) form.reset();
  document.getElementById("auth-msg").textContent = "";
  render();
}

/* =========================================================================
 * 메인
 * ========================================================================= */

function setView(v) {
  state.view = v;
  render();
}

function selectChild(id) {
  state.childId = id;
  state.fb = { completion: null, satisfaction: null, interest: null, comprehension: null };
  render();
}

async function refreshMe() {
  try {
    const data = await api("GET", "/api/me");
    state.account = data.account;
    state.children = data.children;
    if (!state.children.find((c) => c.id === state.childId)) {
      state.childId = state.children.length ? state.children[0].id : null;
    }
  } catch (e) { /* logout already handled */ }
}

function pick(key, val) {
  state.fb[key] = val;
  render();
}

async function submitFeedback(e) {
  e.preventDefault();
  if (!state.fb.completion || !state.fb.satisfaction || !state.fb.interest || !state.fb.comprehension) {
    alert("네 가지 항목을 모두 골라주세요.");
    return;
  }
  const btn = document.getElementById("fb-submit");
  btn.disabled = true;
  try {
    const body = { ...state.fb };
    const memo = document.getElementById("f-memo").value.trim();
    if (memo) body.memo = memo;
    await api("POST", "/api/children/" + state.childId + "/feedback", body);
    state.fb = { completion: null, satisfaction: null, interest: null, comprehension: null };
    render();
  } catch (err) {
    alert(err.message);
    btn.disabled = false;
  }
}

async function doReplan() {
  if (!confirm("지금까지의 4주 계획을 마무리하고, 오늘부터 새 4주 계획을 만들까요?")) return;
  try {
    await api("POST", "/api/children/" + state.childId + "/replan", {});
    render();
  } catch (err) {
    alert(err.message);
  }
}

async function saveSettings() {
  const body = {};
  const nick = document.getElementById("s-nickname");
  const mins = document.getElementById("s-minutes");
  if (nick) body.nickname = nick.value.trim();
  if (mins) {
    const v = parseInt(mins.value, 10);
    if (!v || v < 5 || v > 60) { alert("하루 학습 시간은 5~60분 사이로 설정해주세요."); return; }
    body.daily_minutes = v;
  }
  try {
    const data = await api("POST", "/api/children/" + state.childId + "/settings", body);
    const idx = state.children.findIndex((c) => c.id === data.id);
    if (idx >= 0) state.children[idx] = data;
    alert("저장했어요 🌱");
    render();
  } catch (err) {
    alert(err.message);
  }
}

async function searchLibrary() {
  render(); // filters already captured; re-render to refetch
}

/* =========================================================================
 * 렌더
 * ========================================================================= */

function render() {
  const app = $app();
  if (!state.token || !state.account) {
    app.innerHTML = renderAuth();
    document.getElementById("auth-form").addEventListener("submit", submitAuth);
    return;
  }
  if (!state.children.length) {
    app.innerHTML = renderOnboard();
    document.getElementById("onboard-form").addEventListener("submit", submitOnboard);
    return;
  }
  app.innerHTML = renderMain();
  bindMain();
}

/* ---------------- 인증 ---------------- */

function renderAuth() {
  const mode = state.authMode;
  return `
  <div class="auth-wrap">
    <div class="logo">🌷 꽃피다</div>
    <div class="logo-sub">영어 유치원 대신,<br>집안에서 피는 영어</div>
    <div class="auth-tabs">
      <button type="button" class="${mode === "login" ? "on" : ""}" onclick="switchAuth('login')">로그인</button>
      <button type="button" class="${mode === "register" ? "on" : ""}" onclick="switchAuth('register')">회원가입</button>
    </div>
    <form id="auth-form">
      <label class="field"><span>이메일 (ID)</span>
        <input id="f-email" type="email" required autocomplete="email" placeholder="you@example.com">
      </label>
      <label class="field"><span>비밀번호${mode === "register" ? " (6자 이상)" : ""}</span>
        <input id="f-password" type="password" required minlength="6" autocomplete="${mode === "register" ? "new-password" : "current-password"}" placeholder="••••••••">
      </label>
      <div class="auth-msg" id="auth-msg"></div>
      <button class="btn" type="submit">${mode === "login" ? "로그인" : "계정 만들기"}</button>
    </form>
    <p class="muted small center mt16">
      실명 인증 없이 이메일로 가입해요. 시터·가족과 계정 공유가 가능하도록 설계되었어요.<br>
      아이의 이름·생일은 수집하지 않습니다.
    </p>
  </div>`;
}

/* ---------------- 온보딩 ---------------- */

function renderOnboard() {
  return `
  <div class="auth-wrap">
    <div class="logo">🌱 첫걸음</div>
    <div class="logo-sub">아이의 정보를 알려주세요.<br>4주 학습 계획을 바로 만들어드려요.</div>
    <form id="onboard-form">
      <label class="field"><span>만 나이</span>
        <select id="o-age">
          <option value="3">3세</option>
          <option value="4" selected>4세</option>
          <option value="5">5세</option>
          <option value="6">6세</option>
        </select>
      </label>
      <label class="field"><span>닉네임 (이름 대신, 선택)</span>
        <input id="o-nickname" maxlength="20" placeholder="예: 우리별">
      </label>
      <label class="field" style="display:flex;align-items:center;gap:8px;">
        <input type="checkbox" id="o-ek" style="width:auto;">
        <span style="font-size:0.9rem;">현재 영어 유치원에 다니고 있어요</span>
      </label>
      <label class="field"><span>지금까지 영어 노출 정도</span>
        <select id="o-exposure">
          <option value="none">별로 없어요</option>
          <option value="some">조금 있어요 (노래·유튜브 등)</option>
          <option value="much">많이 있어요 (해외 체류·영어 가정 등)</option>
        </select>
      </label>
      <label class="field"><span>하루 학습 시간 (분)</span>
        <select id="o-minutes">
          <option value="5">5분</option>
          <option value="10" selected>10분</option>
          <option value="15">15분</option>
          <option value="20">20분</option>
          <option value="30">30분</option>
        </select>
      </label>
      <div class="auth-msg" id="auth-msg"></div>
      <button class="btn" type="submit">4주 계획 만들기</button>
    </form>
  </div>`;
}

/* ---------------- 메인 레이아웃 ---------------- */

function childById(id) {
  return state.children.find((c) => c.id === id) || state.children[0];
}

function renderMain() {
  const c = childById(state.childId);
  const tabs = [
    ["today", "📖", "오늘"],
    ["coach", "💬", "코치"],
    ["report", "📊", "리포트"],
    ["library", "📚", "서재"],
    ["mine", "⚙️", "내정보"],
  ];
  return `
  <header class="topbar">
    <span class="logo-sm">🌷 꽃피다</span>
    <div class="child-chips">
      ${state.children
        .map(
          (ch) =>
            `<button class="${ch.id === state.childId ? "on" : ""}" onclick="selectChild(${ch.id})">${escapeHtml(ch.nickname || "아이")} ${ch.age}세</button>`
        )
        .join("")}
    </div>
    <button class="bell" onclick="openNotifs()" title="알림">🔔<span class="dot" id="bell-dot" hidden></span></button>
  </header>
  <main class="page" id="page"><div class="empty">불러오는 중…</div></main>
  <nav class="tabs">
    ${tabs
      .map(
        ([v, ic, lbl]) =>
          `<button class="${state.view === v ? "on" : ""}" onclick="setView('${v}')"><span class="ic">${ic}</span>${lbl}</button>`
      )
      .join("")}
  </nav>`;
}

function bindMain() {
  loadBell();
  loadPage();
}

async function loadBell() {
  try {
    const data = await api("GET", "/api/notifications");
    const dot = document.getElementById("bell-dot");
    if (dot) {
      dot.hidden = !data.unread;
      dot.textContent = data.unread;
    }
  } catch (e) { /* ignore */ }
}

async function loadPage() {
  const el = document.getElementById("page");
  if (!el) return;
  const c = childById(state.childId);
  try {
    if (state.view === "today") {
      const data = await api("GET", "/api/children/" + c.id + "/today");
      el.innerHTML = renderToday(data);
      const form = document.getElementById("fb-form");
      if (form) form.addEventListener("submit", submitFeedback);
    } else if (state.view === "coach") {
      const msgs = await api("GET", "/api/children/" + c.id + "/messages");
      el.innerHTML = renderCoach(msgs);
    } else if (state.view === "report") {
      const [report, sub] = await Promise.all([
        api("GET", "/api/children/" + c.id + "/report"),
        api("GET", "/api/children/" + c.id + "/subscription"),
      ]);
      el.innerHTML = renderReport(report, sub);
    } else if (state.view === "library") {
      const qs = new URLSearchParams();
      if (state.lib.stage) qs.set("stage", state.lib.stage);
      if (state.lib.type) qs.set("type", state.lib.type);
      if (state.lib.keyword) qs.set("keyword", state.lib.keyword);
      qs.set("age", c.age);
      const items = await api("GET", "/api/catalog?" + qs.toString());
      el.innerHTML = renderLibrary(items);
    } else if (state.view === "mine") {
      const sub = await api("GET", "/api/children/" + c.id + "/subscription");
      el.innerHTML = renderMine(c, sub);
      const nick = document.getElementById("s-nickname");
      if (nick) nick.addEventListener("change", saveSettings);
      const mins = document.getElementById("s-minutes");
      if (mins) mins.addEventListener("change", saveSettings);
    }
  } catch (err) {
    el.innerHTML = `<div class="empty">🌫️ ${escapeHtml(err.message)}</div>`;
  }
}

/* ---------------- 오늘 ---------------- */

const FB_GROUPS = [
  { key: "completion", label: "오늘 학습, 얼마나 같이 했어요?", opts: [["full", "다 함께 했어요"], ["partial", "절반쯤 했어요"], ["none", "못 했어요"]] },
  { key: "satisfaction", label: "아이는 어땠어요?", opts: [["happy", "좋아했어요 😊"], ["neutral", "보통이었어요 😐"], ["sad", "힘들어했어요 😢"]] },
  { key: "interest", label: "흥미는?", opts: [["high", "흥미진진했어요"], ["low", "별로 흥미 없었어"]] },
  { key: "comprehension", label: "어려웠나요?", opts: [["good", "이해한 것 같아요"], ["unsure", "잘 모르겠어요"], ["poor", "아직 어려웠어요"]] },
];

function renderToday(data) {
  const c = childById(state.childId);
  const day = data.today;
  const recorded = !!data.record;
  const msg = data.message;
  let html = `<h1 class="page-title">${fmtDate(data.date)} · ${
    day && day.date === data.date ? "오늘" : "다음 학습일"
  }</h1>`;

  if (!day) {
    html += `<div class="card center">
      <div class="muted">4주 계획이 모두 끝났어요. '내정보'에서 새 계획을 만들 수 있어요. 🌷</div>
      <button class="btn mt16 btn-ghost" onclick="setView('mine')">내정보로</button>
    </div>`;
  } else {
    const item = day.content || {};
    html += `
    <div class="card today-hero">
      <div class="stage-row">
        <span class="badge">${STAGES[day.stage] || ""}</span>
        <span class="badge badge-gray">${escapeHtml(item.type || "")}</span>
        ${item.paid ? '<span class="badge badge-peach">구매 교재</span>' : '<span class="badge badge-pink">무료</span>'}
      </div>
      <h2>${escapeHtml(item.title || "오늘의 학습")}</h2>
      <div class="meta"><span class="muted">⏱ ${day.minutes}분</span></div>
      ${item.why ? `<div class="why-box">💡 ${escapeHtml(item.why)}</div>` : ""}
      ${item.link ? `<a class="content-link" href="${escapeHtml(item.link)}" target="_blank" rel="noopener">링크 열기 ↗</a>` : ""}
      ${item.tip ? `<div class="tip-box">TIP · ${escapeHtml(item.tip)}</div>` : ""}
    </div>`;
  }

  if (recorded) {
    const r = data.record;
    html += `
    <div class="card">
      <div class="center"><span class="badge">오늘 기록 완료</span></div>
      <p class="muted small center mt8">
        완료: ${fbLabel("completion", r.completion)} · 만족: ${fbLabel("satisfaction", r.satisfaction)}<br>
        흥미: ${fbLabel("interest", r.interest)} · 이해: ${fbLabel("comprehension", r.comprehension)}
      </p>
    </div>`;
  } else {
    html += `
    <form id="fb-form" class="card">
      <h3 style="font-size:0.98rem;margin-bottom:12px;">오늘 기록 남기기 <span class="muted small">(1분)</span></h3>
      ${FB_GROUPS.map(
        (g) => `
        <div class="fb-group">
          <span>${g.label}</span>
          <div class="chips">
            ${g.opts
              .map(
                ([v, l]) =>
                  `<button type="button" class="${state.fb[g.key] === v ? "on" : ""}" onclick="pick('${g.key}','${v}')">${l}</button>`
              )
              .join("")}
          </div>
        </div>`
      ).join("")}
      <label class="field" style="margin-top:4px;"><span>코치에게 남길 말 (선택) — 어렵거나 지루하거나, 질문이 있다면</span>
        <textarea id="f-memo" maxlength="500" placeholder="예: 너무 어려워서요. 쉬워지는 방향으로 수정해주세요"></textarea>
      </label>
      <button class="btn" id="fb-submit" type="submit">코치에게 전달하기</button>
    </form>`;
  }

  if (msg) {
    html += `<div class="card coach-msg">
      <div class="head"><span class="avatar">🌷</span>
        <strong>코치의 말</strong>
        <span class="badge ${CASE_BADGE[msg.case_type] ? CASE_BADGE[msg.case_type].cls : "badge-gray"}">${
          CASE_BADGE[msg.case_type] ? CASE_BADGE[msg.case_type].text : "메시지"
        }</span>
        <span class="muted small" style="margin-left:auto;">${fmtDate(msg.record_date)}</span>
      </div>
      <div class="body">${escapeHtml(msg.message)}</div>
      <div class="ai-label"><span class="badge badge-gray">AI 코칭 메시지</span></div>
    </div>`;
  }

  if (data.plan) {
    html += `<div class="philosophy">🌱 영어는 '증서'가 아니라<br>읽고 듣고 말하고 쓰듯 <u>영어로 사고하는</u> 사람이 되는 길이에요.<br>남은 학습일 ${data.days_left}일</div>`;
  }
  return html;
}

function fbLabel(group, val) {
  const g = FB_GROUPS.find((x) => x.key === group);
  if (!g) return val;
  const hit = g.opts.find((o) => o[0] === val);
  return hit ? hit[1].replace(/\s*[😊😐😢].*$/, "") : val;
}

/* ---------------- 코치 ---------------- */

function renderCoach(msgs) {
  if (!msgs.length) {
    return `<h1 class="page-title">💬 코치</h1>
      <div class="empty">아직 코치의 메시지가 없어요.<br>'오늘' 페이지에서 첫 기록을 남겨보세요.</div>`;
  }
  return `<h1 class="page-title">💬 코치의 메시지</h1>
  <div class="msg-list">
  ${msgs
    .map(
      (m) => `
    <div class="card coach-msg">
      <div class="head"><span class="avatar">🌷</span><strong>코치</strong>
        <span class="badge ${CASE_BADGE[m.case_type] ? CASE_BADGE[m.case_type].cls : "badge-gray"}">${
          CASE_BADGE[m.case_type] ? CASE_BADGE[m.case_type].text : "메시지"
        }</span>
        <span class="muted small" style="margin-left:auto;">${fmtDate(m.record_date)}</span>
      </div>
      <div class="body">${escapeHtml(m.message)}</div>
    </div>`
    )
    .join("")}
  </div>`;
}

/* ---------------- 리포트 ---------------- */

function renderReport(report, sub) {
  const maxC = Math.max(1, report.by_completion.full, report.by_completion.partial, report.by_completion.none);
  const maxU = Math.max(1, report.by_comprehension.good, report.by_comprehension.unsure, report.by_comprehension.poor);
  const trendText = { up: "상승 추세 📈", steady: "꾸준한 리듬 🌿", support: "서포트가 필요한 주 🤍", no_data: "기록 대기 중 🌱" }[report.trend] || "";
  return `
  <h1 class="page-title">📊 주간 리포트 <span class="muted small">${escapeHtml(report.week)}</span></h1>
  <div class="stat-grid">
    <div class="stat"><div class="num">${report.record_days}</div><div class="lbl">학습한 날</div></div>
    <div class="stat"><div class="num">${report.planned_days}</div><div class="lbl">계획된 날</div></div>
  </div>
  <div class="card">
    <span class="muted small" style="font-weight:700;">완료도</span>
    ${barRow("다함께", report.by_completion.full, maxC, "")}
    ${barRow("약간", report.by_completion.partial, maxC, "peach")}
    ${barRow("못함", report.by_completion.none, maxC, "pink")}
    <span class="muted small" style="font-weight:700;display:block;margin-top:10px;">이해도</span>
    ${barRow("이해", report.by_comprehension.good, maxU, "")}
    ${barRow("모름", report.by_comprehension.unsure, maxU, "peach")}
    ${barRow("어려움", report.by_comprehension.poor, maxU, "pink")}
  </div>
  <div class="card">
    <span class="badge ${report.trend === "up" ? "" : report.trend === "support" ? "badge-peach" : "badge-gray"}">${trendText}</span>
    <p class="mt8" style="font-size:0.93rem;">${escapeHtml(report.comment)}</p>
  </div>
  <div class="card fee-card">
    <div class="muted small" style="font-weight:700;">이번 달 성취도 → 다음 달 요금</div>
    <div class="fee">${(sub.next_fee / 10000).toFixed(0)}만 원 <span class="muted small">/ 현재 ${sub.tier === "consistent" ? "꾸준한 학습 상" : "기본"}</span></div>
    <div class="progress"><i style="width:${Math.min(100, sub.achievement_pct)}%"></i></div>
    <div class="small muted">기록 ${sub.recorded_days}일 / 계획 ${sub.planned_days}일 = <b style="color:var(--teal-deep);">${sub.achievement_pct}%</b> (목표 ${sub.target_pct}%)</div>
    <p class="small mt8" style="color:#7c3e08;">꾸준히 학습하면 다음 달 요금은 10만 원이에요. 할인이 아니라, 꾸준히 배운 아이에게 주는 상입니다.</p>
  </div>`;
}

function barRow(label, val, max, cls) {
  return `<div class="bar-row"><span class="lbl">${label}</span><div class="bar"><i class="${cls}" style="width:${(val / max) * 100}%"></i></div><span class="val">${val}</span></div>`;
}

/* ---------------- 서재 ---------------- */

const LIB_TYPES = ["노래", "유튜브", "교재", "앱", "웹", "활동"];

function renderLibrary(items) {
  const f = state.lib;
  return `
  <h1 class="page-title">📚 콘텐츠 서재</h1>
  <div class="filter-row">
    <select onchange="state.lib.stage=this.value;searchLibrary()">
      <option value="">전체 단계</option>
      ${Object.keys(STAGES).map((s) => `<option value="${s}" ${f.stage == s ? "selected" : ""}>${s}. ${STAGES[s]}</option>`).join("")}
    </select>
    <select onchange="state.lib.type=this.value;searchLibrary()">
      <option value="">전체 유형</option>
      ${LIB_TYPES.map((t) => `<option value="${t}" ${f.type === t ? "selected" : ""}>${t}</option>`).join("")}
    </select>
    <input placeholder="검색" value="${escapeHtml(f.keyword)}" oninput="state.lib.keyword=this.value" onchange="searchLibrary()">
  </div>
  ${
    items.length
      ? items
          .map(
            (it) => `
      <div class="card item-card">
        <h3>${escapeHtml(it.title)}</h3>
        <div class="meta">
          <span class="badge">${it.stage}. ${STAGES[it.stage] || ""}</span>
          <span class="badge badge-gray">${escapeHtml(it.type)}</span>
          <span class="badge badge-gray">⏱ ${it.minutes}분</span>
          ${it.paid ? '<span class="badge badge-peach">구매</span>' : '<span class="badge badge-pink">무료</span>'}
        </div>
        ${it.why ? `<div class="why">💡 ${escapeHtml(it.why)}</div>` : ""}
        ${it.tip ? `<div class="why">TIP · ${escapeHtml(it.tip)}</div>` : ""}
        ${it.link ? `<a class="content-link" href="${escapeHtml(it.link)}" target="_blank" rel="noopener">링크 열기 ↗</a>` : ""}
      </div>`
          )
          .join("")
      : `<div class="empty">조건에 맞는 콘텐츠가 없어요.</div>`
  }
  <p class="muted small center">교재는 안내만 드리고 직접 구매해요. 영상·앱은 링크로 바로 접속할 수 있어요.</p>`;
}

/* ---------------- 내정보 ---------------- */

function renderMine(c, sub) {
  return `
  <h1 class="page-title">⚙️ 내정보</h1>
  <div class="card">
    <span class="muted small" style="font-weight:700;">계정</span>
    <p style="font-size:0.95rem;">${escapeHtml(state.account ? state.account.email : "")}</p>
    <p class="small muted">이메일 계정은 시터·가족과 공유할 수 있어요. 아이 이름·생일은 수집하지 않아요.</p>
  </div>
  <div class="card">
    <span class="muted small" style="font-weight:700;">${escapeHtml(c.nickname || "우리 아이")} · 학습 설정</span>
    <label class="field mt8"><span>닉네임</span>
      <input id="s-nickname" maxlength="20" value="${escapeHtml(c.nickname || "")}" placeholder="예: 우리별">
    </label>
    <label class="field"><span>하루 학습 시간 (분)</span>
      <select id="s-minutes">
        ${[5, 10, 15, 20, 30, 45, 60]
          .map((m) => `<option value="${m}" ${c.daily_minutes === m ? "selected" : ""}>${m}분</option>`)
          .join("")}
      </select>
    </label>
    <p class="small muted">변경하면 자동으로 저장돼요.</p>
  </div>
  <div class="card fee-card">
    <span class="muted small" style="font-weight:700;">구독 · 이번 달 성취도</span>
    <div class="progress mt8"><i style="width:${Math.min(100, sub.achievement_pct)}%"></i></div>
    <div class="small">기록 <b>${sub.recorded_days}</b>일 / 계획 <b>${sub.planned_days}</b>일 → <b style="color:var(--teal-deep);">${sub.achievement_pct}%</b></div>
    <p class="small mt8">
      다음 달 요금: <b class="fee" style="font-size:1.1rem;">${(sub.next_fee / 10000).toFixed(0)}만 원</b><br>
      <span class="muted">80% 달성 시 10만 원, 그 외 30만 원. 꾸준함의 상입니다. 🌷</span>
    </p>
  </div>
  <div class="card">
    <span class="muted small" style="font-weight:700;">학습 계획</span>
    <p class="small mt8">4주가 지나거나 방향을 바꾸고 싶을 때 새 계획을 만들어요.</p>
    <button class="btn btn-ghost mt8" onclick="doReplan()">새 4주 계획 만들기</button>
  </div>
  <button class="btn btn-warn" onclick="logout()">로그아웃</button>
  <div class="philosophy">🌷 꽃피다 — 영어는 '증서'가 아니라<br>영어로 <u>사고하는 사람</u>을 키우는 여정이에요.<br><span class="small" style="font-weight:400;color:var(--ink-soft);">코칭 메시지는 AI가 작성하며, 발달 진단과 효과 보장은 하지 않습니다.</span></div>`;
}

/* ---------------- 알림 ---------------- */

async function openNotifs() {
  const m = $modal();
  m.hidden = false;
  document.body.classList.add("has-modal");
  m.innerHTML = `<div class="modal-sheet"><div class="modal-head"><h3>🔔 알림</h3><button onclick="closeNotifs()">✕</button></div><div class="empty">불러오는 중…</div></div>`;
  try {
    const data = await api("GET", "/api/notifications");
    await api("POST", "/api/notifications/read", {});
    const list = data.items.length
      ? data.items
          .map(
            (n) => `
      <div class="notif ${n.read_at ? "" : "unread"}">
        <h4>${escapeHtml(n.title)}</h4>
        <div class="body">${escapeHtml(n.body)}</div>
        <div class="date">${escapeHtml(n.created_at || "")}</div>
      </div>`
          )
          .join("")
      : `<div class="empty">알림이 없어요 🌿</div>`;
    m.innerHTML = `<div class="modal-sheet"><div class="modal-head"><h3>🔔 알림</h3><button onclick="closeNotifs()">✕</button></div>${list}</div>`;
    const dot = document.getElementById("bell-dot");
    if (dot) dot.hidden = true;
  } catch (err) {
    m.innerHTML = `<div class="modal-sheet"><div class="modal-head"><h3>🔔 알림</h3><button onclick="closeNotifs()">✕</button></div><div class="empty">${escapeHtml(err.message)}</div></div>`;
  }
}

function closeNotifs() {
  $modal().hidden = true;
  $modal().innerHTML = "";
  document.body.classList.remove("has-modal");
}

/* ---------------- 유틸 ---------------- */

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  const wd = ["일", "월", "화", "수", "목", "금", "토"][d.getDay()];
  return `${d.getMonth() + 1}월 ${d.getDate()}일 (${wd})`;
}

/* ---------------- 시작 ---------------- */

(async function init() {
  if (state.token) {
    try {
      await refreshMe();
    } catch (e) {
      /* 토큰 무효 → logout in api() */
    }
  }
  render();
})();
