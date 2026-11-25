/* Bloomy · 꽃피다 — 통합 앱 (아이 학습 + 부모 코칭 루프)
 * Apple Newsroom 스타일 · 반응형 · 다크모드
 *
 * 흐름: 로그인 → 온보딩(프로필+진단) → 계획 승인 → 오늘(카드+단어/표현) →
 *       부모 피드백 → AI 코치 메시지 → 리포트
 */
'use strict';

const CONTENT = window.BLOOMY_CONTENT;
const TOKEN_KEY = 'bloomy_token';
const THEME_KEY = 'bloomy_theme';

function freshOnboard() {
  return { age: null, experience: null, interests: [], studyTime: null, ek: false, materials: '', goal: '듣기' };
}

const state = {
  token: localStorage.getItem(TOKEN_KEY) || null,
  account: null,
  child: null,
  view: 'loading',
  authMode: 'login',
  onboard: freshOnboard(),
  diagnosisQuestions: [],
  diagnosis: {},
  today: null,
  nextCard: null,
  lastFeedback: null,
  report: null,
  myPlan: null,
  showKo: (() => { try { return !!localStorage.getItem('bloomy_show_ko'); } catch (e) { return false; } })(),
  achievement: null,
  aiRec: null,
  privacy: null,
  error: '',
};

const $app = () => document.getElementById('app');

/* ---------------- helpers ---------------- */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

async function api(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.token) headers['Authorization'] = 'Bearer ' + state.token;
  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON */ }
  // 토큰을 보낸 요청의 401만 세션 만료로 처리한다.
  // (로그인 실패 401에서 logout()을 부르면 화면이 다시 그려져 오류 메시지가 사라진다)
  if (res.status === 401 && headers['Authorization']) {
    logout();
    throw new Error('로그인이 필요합니다');
  }
  if (!res.ok) throw new Error((data && data.error) || `요청에 실패했어요 (HTTP ${res.status})`);
  return data;
}

function childInterests() {
  const raw = (state.child && state.child.favorite_topics) || '';
  const list = raw.split(',').map((s) => s.trim()).filter(Boolean);
  const known = list.filter((t) => CONTENT.words[t]);
  return known.length ? known : ['우주'];
}

function wordsForInterests() {
  const seen = new Map();
  childInterests().forEach((topic) => {
    (CONTENT.words[topic] || []).forEach((w) => seen.set(w.word, w));
  });
  return [...seen.values()];
}

function phrasesForInterests() {
  const seen = new Map();
  childInterests().forEach((topic) => {
    (CONTENT.phrases[topic] || []).forEach((p) => seen.set(p.english, p));
  });
  return [...seen.values()];
}

/* ---------------- theme ---------------- */
function applyTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved || (prefersDark ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', theme);
  const icon = document.querySelector('#themeToggle .theme-icon');
  if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem(THEME_KEY, next);
  const icon = document.querySelector('#themeToggle .theme-icon');
  if (icon) icon.textContent = next === 'dark' ? '☀️' : '🌙';
}

/* ---------------- auth ---------------- */
function logout() {
  state.token = null;
  state.account = null;
  state.child = null;
  state.today = null;
  state.report = null;
  state.achievement = null;
  // 이전 사용자의 입력이 다음 가입·로그인 화면에 남지 않도록 사용자별 상태를 모두 초기화
  state.onboard = freshOnboard();
  state.diagnosis = {};
  state.nextCard = null;
  state.lastFeedback = null;
  state.aiRec = null;
  state.plan = null;
  state.cards = null;
  state.reportWeek = null;
  state.error = '';
  localStorage.removeItem(TOKEN_KEY);
  state.view = 'auth';
  render();
}

async function afterAuth(data) {
  state.token = data.token;
  state.account = data.account;
  localStorage.setItem(TOKEN_KEY, data.token);
  state.child = data.children && data.children.length ? data.children[0] : null;
  await routeAfterAccount();
  render();
}

function hasConsent() {
  return !!(state.account && state.account.consent && state.account.consent.version);
}

/* 동의 기록이 없는 기존 가입자는 동의 화면을 먼저 거친다 */
async function routeAfterAccount() {
  if (!hasConsent()) {
    await loadPrivacy();
    state.view = 'consent';
  } else if (state.child) {
    if (curriculumIdFromHash()) {
      await loadCurriculum(curriculumIdFromHash());
      return;
    }
    await loadToday();
    state.view = 'today';
  } else {
    state.view = 'onboarding';
  }
}

/* 자료별 전체 커리큘럼 (카드의 "전체 커리큘럼 보기" → 새 탭 #curriculum/<자료 id>) */
function curriculumIdFromHash() {
  const m = /^#curriculum\/([a-z0-9-]+)$/.exec(location.hash || '');
  return m ? m[1] : null;
}

async function loadCurriculum(id) {
  state.view = 'curriculum';
  try {
    state.curriculum = await api('GET', '/api/children/' + state.child.id + '/curriculum/' + id);
    state.curriculumError = null;
  } catch (e) {
    state.curriculum = null;
    state.curriculumError = e.message || '불러오지 못했어요';
  }
}

const UNIT_STATUS = {
  done: ['완료', 'st-done'], today: ['오늘', 'st-today'], planned: ['예정', 'st-planned'],
  missed: ['지난 날(기록 없음)', 'st-missed'], later: ['다음 계획 이후', 'st-later'],
};

function fmtDate(d) { return d ? d.slice(5).replace('-', '/') : ''; }

function curriculumHtml() {
  const c = state.curriculum;
  const back = '<button type="button" class="btn btn-ghost btn-sm" id="curBack">← 오늘의 학습</button>';
  if (!c) {
    return `<section class="screen"><div class="hero" style="padding:40px 0 20px;text-align:left">${back}
      <p class="muted mt16">${esc(state.curriculumError || '불러오는 중…')}</p></div></section>`;
  }
  const s = c.series || {}, it = c.item || {};
  const status = (k) => { const [t, cls] = UNIT_STATUS[k] || [k, '']; return `<span class="st ${cls}">${esc(t)}</span>`; };
  const doneN = (c.units || []).filter((u) => u.status === 'done').length;
  return `
  <section class="screen">
    <div class="hero" style="padding:32px 0 12px; text-align:left">
      ${back}
      <span class="eyebrow mt16" style="display:block">전체 커리큘럼</span>
      <h1 class="hero-title">${esc(s.name || it.title)}</h1>
      <p class="muted mt8">${s.kind ? esc(s.kind) + ' · ' : ''}${s.cost ? esc(s.cost) : ''}</p>
    </div>
    <div class="cur-grid">
      <div>
        <div class="card">
          <h2 class="card-title">이 자료는</h2>
          ${s.about ? `<p class="mt8">${esc(s.about)}</p>` : ''}
          <div class="guide mt16">
            <div class="guide-row"><span class="guide-k">지금 자료</span><span>${esc(it.title)} <span class="muted small">· ${esc(it.level_label)} · ${esc(it.age)} · ${esc(it.skill)}</span></span></div>
            ${c.find ? `<div class="guide-row"><span class="guide-k">찾는 법</span><span>${esc(c.find)}</span></div>` : ''}
          </div>
          ${s.official ? `<a class="btn btn-ghost btn-sm mt16" href="${esc(s.official)}" target="_blank" rel="noopener noreferrer">공식 사이트에서 전체 구성 보기 ↗</a>` : ''}
        </div>

        <div class="card mt16">
          <h2 class="card-title">꽃피다 추천 자료 (이 시리즈)</h2>
          <p class="small muted mt8">아이 단계가 오르면 다음 단계 자료로 넘어가요.</p>
          <ol class="cur-steps mt16">
            ${(c.steps || []).map((x) => `<li class="${x.current ? 'is-current' : ''}">
              <span class="cur-level">${esc(x.level_label)}</span>
              <span>${esc(x.title)}${x.units ? ` <span class="muted small">· ${x.units}개 단위</span>` : ''}${x.current ? ' <span class="chip chip-accent">지금</span>' : ''}</span>
            </li>`).join('')}
          </ol>
        </div>
      </div>

      <div>
        <div class="card">
          <h2 class="card-title">단계별 경로</h2>
          ${pathHtml(c)}
        </div>
        ${(c.units || []).length ? `
        <div class="card mt16">
          <h2 class="card-title">학습 단위 순서</h2>
          <p class="small muted mt8">한 단위(책 한 권·회차·소리 묶음)를 처음 → 다시 하기로 두 번 하고 다음으로 넘어가요. 지금까지 ${doneN}/${c.units.length}개 완료.</p>
          <ol class="cur-units mt16">
            ${c.units.map((u) => `<li class="${u.status === 'today' ? 'is-current' : ''}">
              <span class="cur-n">${u.n}</span>
              <span class="cur-title">${esc(u.title)} <span class="muted small">${esc(u.pack)}</span></span>
              <span class="cur-st">${status(u.status)}${u.dates.length ? `<span class="muted small"> ${u.dates.map(fmtDate).join('·')}</span>` : ''}</span>
            </li>`).join('')}
          </ol>
        </div>` : `
        <div class="card mt16">
          <h2 class="card-title">학습 단위 순서</h2>
          <p class="mt8 muted">이 자료는 아직 권·회차가 정해지지 않은 묶음이에요. '찾는 법'과 공식 사이트에서 아이가 좋아하는 것을 하나 골라 주세요. 출처를 확인하면 권 단위로 나눠 드릴게요.</p>
        </div>`}

        <div class="card mt16">
          <h2 class="card-title">우리 계획에서 이 자료를 하는 날</h2>
          ${(c.days || []).length ? `<ul class="cur-days mt16">
            ${c.days.map((d) => `<li><span class="cur-date">${fmtDate(d.date)}</span>${status(d.status)}<span class="small">${esc(d.task)}</span></li>`).join('')}
          </ul>` : '<p class="muted mt8">승인한 계획에는 아직 이 자료가 없어요.</p>'}
        </div>
      </div>
    </div>
  </section>`;
}

/* 공식 단계 전체: 출판사·서비스가 정한 순서. 꽃피다 추천 자료가 있는 단계에 표시 */
function pathHtml(c) {
  const p = c.path;
  if (!p) return '<p class="small muted mt8">이 자료는 출판사가 정한 단계 순서가 없어요(단권 그림책·영상 채널 등). 꽃피다가 이 시리즈에서 추천하는 자료는 왼쪽(휴대폰은 위)에 있어요.</p>';
  const steps = p.steps || [];
  return `
    ${p.note ? `<p class="small muted mt8">${esc(p.note)}</p>` : ''}
    ${steps.length ? `<ol class="cur-path mt16">
      ${steps.map((st, i) => `<li class="${st.current ? 'is-current' : ''}">
        <span class="cur-n">${i + 1}</span>
        <div>
          <div><strong>${esc(st.name)}</strong>${st.age ? ` <span class="muted small">· ${esc(st.age)}</span>` : ''}${st.current ? ' <span class="chip chip-accent">지금</span>' : ''}</div>
          ${st.desc ? `<div class="small muted">${esc(st.desc)}</div>` : ''}
          ${st.items.length ? `<div class="small mt4">꽃피다 추천: ${st.items.map((x) => esc(x.title)).join(', ')}</div>` : ''}
        </div>
      </li>`).join('')}
    </ol>` : ''}
    ${p.source ? `<p class="small muted mt8">출처: <a href="${esc(p.source)}" target="_blank" rel="noopener noreferrer">${esc(p.source.replace(/^https?:\/\//, '').split('/')[0])}</a></p>` : ''}`;
}

function bindCurriculum() {
  const b = document.getElementById('curBack');
  if (b) b.addEventListener('click', async () => {
    history.replaceState(null, '', location.pathname);
    await loadToday();
    state.view = 'today';
    render();
  });
}

async function loadPrivacy() {
  if (state.privacy) return state.privacy;
  try { state.privacy = await api('GET', '/api/privacy'); } catch (e) { state.privacy = null; }
  return state.privacy;
}

/* ---------------- privacy consent ---------------- */
function privacyDetailsHtml(open) {
  const p = state.privacy;
  if (!p) return '<p class="muted">개인정보 안내를 불러오지 못했어요. 새로고침 해 주세요.</p>';
  const rows = p.items.map((it) => `<li><strong>${esc(it.label)}</strong> — ${esc(it.value)}</li>`).join('');
  return `<details class="privacy-details"${open ? ' open' : ''}>
      <summary>${esc(p.title)} 안내 보기</summary>
      <ul class="privacy-list">${rows}</ul>
    </details>`;
}

function consentChecksHtml() {
  const p = state.privacy;
  if (!p) return '';
  return Object.entries(p.required).map(([key, label]) => `
    <label class="consent-item">
      <input type="checkbox" name="${esc(key)}" required />
      <span>${esc(label)}</span>
    </label>`).join('');
}

function consentValues(form) {
  const out = {};
  if (state.privacy) Object.keys(state.privacy.required).forEach((k) => { out[k] = !!(form[k] && form[k].checked); });
  return out;
}

function consentHtml() {
  return `
  <section class="screen">
    <div class="auth-wrap">
      <div class="hero" style="padding:48px 0 20px">
        <span class="eyebrow">개인정보 동의</span>
        <h1 class="hero-title">계속하기 전에<br>동의가 필요해요</h1>
        <p class="hero-sub">아이 정보를 안전하게 다루기 위해 보호자 동의를 받고 있어요.</p>
      </div>
      <div class="card">
        <form id="consentForm">
          ${privacyDetailsHtml(true)}
          ${consentChecksHtml()}
          <div class="form-message" id="consentMsg"></div>
          <button class="btn btn-block" type="submit">동의하고 계속하기</button>
          <button class="btn btn-ghost btn-block consent-alt" type="button" id="consentDecline">동의하지 않음 (로그아웃)</button>
        </form>
      </div>
    </div>
  </section>`;
}

function bindConsent() {
  const form = document.getElementById('consentForm');
  document.getElementById('consentDecline').addEventListener('click', logout);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = document.getElementById('consentMsg');
    try {
      const data = await api('POST', '/api/me/consent', consentValues(form));
      state.account = data.account;
      await routeAfterAccount();
      render();
    } catch (err) {
      msg.className = 'form-message is-error';
      msg.textContent = err.message;
    }
  });
}

/* ---------------- account (내 계정 · 탈퇴 = 동의 철회) ---------------- */
/* 서버 시각은 UTC (SQLite는 타임존 표기 없음) → 사용자 지역 날짜로 표시 */
function consentDate(raw) {
  let iso = String(raw).trim().replace(' ', 'T');
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(iso)) iso += 'Z';
  const d = new Date(iso);
  return isNaN(d) ? String(raw).slice(0, 10) : d.toLocaleDateString('ko-KR');
}

function accountHtml() {
  const a = state.account || {};
  const c = a.consent || {};
  const when = c.consented_at ? consentDate(c.consented_at) : '-';
  return `
  <section class="screen">
    <div class="auth-wrap">
      <div class="hero" style="padding:48px 0 20px">
        <span class="eyebrow">내 계정</span>
        <h1 class="hero-title">계정 관리</h1>
        <p class="hero-sub account-email">${esc(a.email || '')}<br>개인정보 동의 ${esc(when)} · 버전 ${esc(c.version || '-')}</p>
      </div>
      <div class="card">
        ${privacyDetailsHtml(false)}
        <button class="btn btn-ghost btn-block" type="button" id="logoutBtn">로그아웃</button>
      </div>
      <div class="card danger-zone">
        <h2 class="card-title">탈퇴 (동의 철회)</h2>
        <p class="muted">탈퇴하면 계정과 아이의 프로필·학습 계획·기록·코칭 메시지가 <strong>즉시 모두 삭제</strong>되며 되돌릴 수 없어요.</p>
        <form id="deleteForm">
          <label class="field">
            <span class="field-label">비밀번호 확인</span>
            <input class="input" type="password" name="password" autocomplete="current-password" required minlength="6" maxlength="128" />
          </label>
          <div class="form-message" id="deleteMsg"></div>
          <button class="btn btn-block btn-danger" type="submit">탈퇴하고 모든 데이터 삭제</button>
        </form>
      </div>
    </div>
  </section>`;
}

function bindAccount() {
  document.getElementById('logoutBtn').addEventListener('click', logout);
  const form = document.getElementById('deleteForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!confirm('정말 탈퇴할까요? 모든 데이터가 즉시 삭제되며 되돌릴 수 없어요.')) return;
    const msg = document.getElementById('deleteMsg');
    try {
      await api('POST', '/api/me/delete', { password: form.password.value });
      alert('탈퇴가 완료되었고 모든 데이터를 삭제했어요.');
      logout();
    } catch (err) {
      msg.className = 'form-message is-error';
      msg.textContent = err.message;
    }
  });
}

/* ---------------- data loaders ---------------- */
async function loadToday(date) {
  if (!state.child) return;
  try {
    const q = date ? '?date=' + encodeURIComponent(date) : '';
    state.today = await api('GET', '/api/children/' + state.child.id + '/today' + q);
    state.nextCard = state.today.next_card || null;
    if (!state.today.card && !state.nextCard) {
      try {
        const plan = await api('GET', '/api/children/' + state.child.id + '/plan');
        const today = state.today.date;
        state.nextCard = (plan.cards || []).find((c) => c.date >= today) || null;
      } catch (e) { /* 계획 없음 */ }
    }
  } catch (e) {
    state.today = null;
  }
}

function ymd(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${dd}`;
}

function thisWeekMonday() {
  const d = new Date();
  const day = d.getDay(); // 0=Sun
  const diff = day === 0 ? 6 : day - 1;
  d.setDate(d.getDate() - diff);
  return ymd(d);
}

function lastWeekMonday() {
  const d = new Date();
  const day = d.getDay();
  const diff = (day === 0 ? 6 : day - 1) + 7;
  d.setDate(d.getDate() - diff);
  return ymd(d);
}

function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

async function loadReport() {
  if (!state.child) return;
  try {
    const ws = state.reportWeek || thisWeekMonday();
    const [report, achievement] = await Promise.all([
      api('GET', '/api/children/' + state.child.id + '/report?week_start=' + ws),
      api('GET', '/api/children/' + state.child.id + '/achievement?month=' + thisMonth()),
    ]);
    state.report = report;
    state.achievement = achievement;
  } catch (e) {
    state.report = null;
    state.achievement = null;
  }
}

/* ---------------- render ---------------- */
function render() {
  const app = $app();
  if (!app) return;
  switch (state.view) {
    case 'loading': app.innerHTML = loadingHtml(); break;
    case 'auth': app.innerHTML = authHtml(); bindAuth(); break;
    case 'consent': app.innerHTML = consentHtml(); bindConsent(); break;
    case 'account': app.innerHTML = accountHtml(); bindAccount(); break;
    case 'onboarding': app.innerHTML = onboardingHtml(); bindOnboarding(); break;
    case 'diagnosis': app.innerHTML = diagnosisHtml(); bindDiagnosis(); break;
    case 'plan': app.innerHTML = planHtml(); bindPlan(); break;
    case 'today': app.innerHTML = todayHtml(); bindToday(); break;
    case 'myplan': app.innerHTML = myPlanHtml(); bindMyPlan(); break;
    case 'report': app.innerHTML = reportHtml(); bindReport(); break;
    case 'curriculum': app.innerHTML = curriculumHtml(); bindCurriculum(); window.scrollTo(0, 0); break;
    default: app.innerHTML = loadingHtml();
  }
  updateNav();
}

function updateNav() {
  document.querySelectorAll('.nav-link').forEach((b) => {
    const target = b.getAttribute('data-nav');
    b.classList.toggle('is-active', target === state.view);
  });
}

function loadingHtml() {
  return `<div class="loading"><div class="spinner"></div>불러오는 중…</div>`;
}

/* ---------------- auth view ---------------- */
function authHtml() {
  const isLogin = state.authMode === 'login';
  return `
  <section class="screen">
    <div class="auth-wrap">
      <div class="hero" style="padding:48px 0 28px">
        <span class="eyebrow">Bloomy · 꽃피다</span>
        <h1 class="hero-title">아이가 배우고,<br>부모가 함께해요</h1>
        <p class="hero-sub">매일 1분의 기록으로 AI 코치가 아이의 영어 여정을 함께합니다.</p>
      </div>
      <div class="card">
        <div class="auth-tabs">
          <button class="auth-tab ${isLogin ? 'is-active' : ''}" data-auth="login">로그인</button>
          <button class="auth-tab ${!isLogin ? 'is-active' : ''}" data-auth="register">회원가입</button>
        </div>
        <form id="authForm">
          <label class="field">
            <span class="field-label">이메일</span>
            <input class="input" type="email" name="email" autocomplete="email" required maxlength="254" />
          </label>
          <label class="field">
            <span class="field-label">비밀번호</span>
            <input class="input" type="password" name="password" autocomplete="current-password" required minlength="6" maxlength="128" />
          </label>
          ${isLogin ? '' : `<div class="consent-block">${privacyDetailsHtml(false)}${consentChecksHtml()}</div>`}
          <div class="form-message" id="authMsg"></div>
          <button class="btn btn-block" type="submit">${isLogin ? '로그인' : '동의하고 회원가입'}</button>
        </form>
      </div>
    </div>
  </section>`;
}

function bindAuth() {
  document.querySelectorAll('[data-auth]').forEach((b) => {
    b.addEventListener('click', async () => {
      state.authMode = b.getAttribute('data-auth');
      if (state.authMode === 'register') await loadPrivacy();
      render();
    });
  });
  const form = document.getElementById('authForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = document.getElementById('authMsg');
    const email = form.email.value.trim();
    const password = form.password.value;
    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      const path = state.authMode === 'login' ? '/api/login' : '/api/register';
      const body = state.authMode === 'login' ? { email, password } : { email, password, ...consentValues(form) };
      const data = await api('POST', path, body);
      await afterAuth(data);
    } catch (err) {
      msg.className = 'form-message is-error';
      msg.textContent = err.message;
      btn.disabled = false;
    }
  });
}

/* ---------------- onboarding (profile) ---------------- */
function customChipsHtml() {
  return state.onboard.interests
    .filter((t) => !CONTENT.interests.includes(t))
    .map((t) => `<span class="chip chip-accent">${esc(t)} <button type="button" class="chip-x" data-remove="${esc(t)}" aria-label="삭제">×</button></span>`)
    .join('');
}

function refreshInterestUI() {
  const list = document.getElementById('customInterestList');
  if (list) list.innerHTML = customChipsHtml();
  document.querySelectorAll('.interest-item input').forEach((cb) => {
    cb.checked = state.onboard.interests.includes(cb.value);
    const label = cb.closest('.interest-item');
    if (label) label.classList.toggle('is-selected', cb.checked);
  });
  if (list) {
    list.querySelectorAll('[data-remove]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const t = btn.getAttribute('data-remove');
        state.onboard.interests = state.onboard.interests.filter((x) => x !== t);
        refreshInterestUI();
      });
    });
  }
}

function onboardingHtml() {
  const o = state.onboard;
  return `
  <section class="screen">
    <div class="onboard-wrap">
      <div class="hero" style="padding:40px 0 24px">
        <span class="step-badge">1 / 2 · 아이 프로필</span>
        <h1 class="hero-title">우리 아이를 알려주세요</h1>
        <p class="hero-sub">나이와 관심사에 맞춰 4주 계획을 준비할게요.</p>
      </div>
      <div class="card">
        <div class="form-section">
          <h2 class="form-section-title">아이 나이<span class="required-dot">필수</span></h2>
          <div class="choice-grid" data-group="age">
            ${[4, 5, 6, 7].map((a) => `<button type="button" class="choice-btn ${o.age === a ? 'is-selected' : ''}" data-value="${a}">${a}세</button>`).join('')}
          </div>
        </div>
        <div class="form-section">
          <h2 class="form-section-title">영어 학습 경험<span class="required-dot">필수</span></h2>
          <div class="choice-grid" data-group="experience">
            ${CONTENT.experience.map((x) => `<button type="button" class="choice-btn ${o.experience === x ? 'is-selected' : ''}" data-value="${esc(x)}">${esc(x)}</button>`).join('')}
          </div>
        </div>
        <div class="form-section">
          <h2 class="form-section-title">아이 관심사<span class="required-dot">필수</span></h2>
          <div class="interest-grid">
            ${CONTENT.interests.map((t) => `
              <label class="interest-item ${o.interests.includes(t) ? 'is-selected' : ''}">
                <input type="checkbox" value="${esc(t)}" ${o.interests.includes(t) ? 'checked' : ''} />
                <span>${esc(t)}</span>
              </label>`).join('')}
          </div>
          <div class="row mt16">
            <input class="input" id="customInterestInput" maxlength="20" placeholder="직접 입력 (예: 로봇, 공주, 우주선)" style="flex:1" />
            <button type="button" class="btn btn-ghost btn-sm" id="addInterestBtn">추가</button>
          </div>
          <div id="customInterestList" class="card-meta mt8">${customChipsHtml()}</div>
        </div>
        <div class="form-section">
          <h2 class="form-section-title">하루 학습 시간<span class="required-dot">필수</span></h2>
          <div class="choice-grid" data-group="studyTime">
            ${[10, 15, 20, 30, 40, 50, 60, 90, 120].map((m) => `<button type="button" class="choice-btn ${o.studyTime === m ? 'is-selected' : ''}" data-value="${m}">${m}분</button>`).join('')}
          </div>
        </div>
        <div class="form-section">
          <h2 class="form-section-title">학습 목표 (선택)</h2>
          <div class="choice-grid" data-group="goal">
            ${['듣기', '읽기', '파닉스', '말하기'].map((g) => `<button type="button" class="choice-btn ${o.goal === g ? 'is-selected' : ''}" data-value="${esc(g)}">${esc(g)}</button>`).join('')}
          </div>
        </div>
        <div class="form-section">
          <h2 class="form-section-title">영어유치원 재원 여부</h2>
          <label class="checkbox-row">
            <input type="checkbox" id="ekCheck" ${o.ek ? 'checked' : ''} />
            <span>영어유치원에 다니고 있어요</span>
          </label>
        </div>
        <div class="form-section">
          <h2 class="form-section-title">집에 있는 교재 (선택)</h2>
          <input class="input" id="materialsInput" maxlength="200" placeholder="예: 핑크퐁, 슈퍼심플, ORT" value="${esc(o.materials)}" />
        </div>
        <div class="form-message" id="onboardMsg"></div>
        <button class="btn btn-block" id="onboardNext">다음: 단계 진단</button>
      </div>
    </div>
  </section>`;
}

function bindOnboarding() {
  document.querySelectorAll('[data-group]').forEach((group) => {
    const key = group.getAttribute('data-group');
    group.querySelectorAll('.choice-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const raw = btn.getAttribute('data-value');
        state.onboard[key] = key === 'age' || key === 'studyTime' ? Number(raw) : raw;
        group.querySelectorAll('.choice-btn').forEach((b) => b.classList.remove('is-selected'));
        btn.classList.add('is-selected');
      });
    });
  });
  document.querySelectorAll('.interest-item input').forEach((cb) => {
    cb.addEventListener('change', () => {
      const label = cb.closest('.interest-item');
      label.classList.toggle('is-selected', cb.checked);
      const val = cb.value;
      const set = new Set(state.onboard.interests);
      if (cb.checked) set.add(val); else set.delete(val);
      state.onboard.interests = [...set];
    });
  });
  const addInterestBtn = document.getElementById('addInterestBtn');
  if (addInterestBtn) {
    addInterestBtn.addEventListener('click', () => {
      const input = document.getElementById('customInterestInput');
      if (!input) return;
      const val = (input.value || '').trim().slice(0, 20);
      if (!val) return;
      if (!state.onboard.interests.includes(val)) {
        state.onboard.interests = [...state.onboard.interests, val];
      }
      input.value = '';
      refreshInterestUI();
    });
  }
  const customInput = document.getElementById('customInterestInput');
  if (customInput) {
    customInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const b = document.getElementById('addInterestBtn');
        if (b) b.click();
      }
    });
  }
  refreshInterestUI();
  const ekCheck = document.getElementById('ekCheck');
  if (ekCheck) ekCheck.addEventListener('change', () => { state.onboard.ek = ekCheck.checked; });
  const materialsInput = document.getElementById('materialsInput');
  if (materialsInput) materialsInput.addEventListener('input', () => { state.onboard.materials = materialsInput.value; });
  document.getElementById('onboardNext').addEventListener('click', async () => {
    const o = state.onboard;
    const msg = document.getElementById('onboardMsg');
    if (!o.age || !o.experience || !o.interests.length || !o.studyTime) {
      msg.className = 'form-message is-error';
      msg.textContent = '나이·경험·관심사·학습 시간을 모두 선택해 주세요.';
      return;
    }
    try {
      if (!state.diagnosisQuestions.length) {
        const data = await api('GET', '/api/diagnosis/questions');
        state.diagnosisQuestions = (data && data.questions) || [];
      }
      state.view = 'diagnosis';
      render();
    } catch (err) {
      msg.className = 'form-message is-error';
      msg.textContent = err.message;
    }
  });
}

/* ---------------- diagnosis ---------------- */
function diagnosisHtml() {
  const qs = state.diagnosisQuestions;
  return `
  <section class="screen">
    <div class="onboard-wrap">
      <div class="hero" style="padding:40px 0 24px">
        <span class="step-badge">2 / 2 · 단계 진단</span>
        <h1 class="hero-title">지금 어디쯤인지 확인해요</h1>
        <p class="hero-sub">결과는 확정이 아니라 가설이에요. 2주간의 반응으로 보정됩니다.</p>
      </div>
      <div class="card">
        ${qs.map((q) => `
          <div class="form-section">
            <h2 class="form-section-title">${esc(q.label)}</h2>
            <div class="choice-grid" data-q="${esc(q.key)}">
              ${Object.entries(q.options).map(([val, label]) => `
                <button type="button" class="choice-btn ${state.diagnosis[q.key] === val ? 'is-selected' : ''}" data-value="${esc(val)}">${esc(label)}</button>`).join('')}
            </div>
          </div>`).join('')}
        <div class="form-message" id="diagMsg"></div>
        <button class="btn btn-block" id="diagSubmit">계획 만들기</button>
        <button type="button" class="btn btn-ghost btn-block mt16" id="diagBack">← 이전: 프로필</button>
      </div>
    </div>
  </section>`;
}

function bindDiagnosis() {
  document.querySelectorAll('[data-q]').forEach((group) => {
    const key = group.getAttribute('data-q');
    group.querySelectorAll('.choice-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.diagnosis[key] = btn.getAttribute('data-value');
        group.querySelectorAll('.choice-btn').forEach((b) => b.classList.remove('is-selected'));
        btn.classList.add('is-selected');
      });
    });
  });
  document.getElementById('diagSubmit').addEventListener('click', async () => {
    const msg = document.getElementById('diagMsg');
    const missing = state.diagnosisQuestions.filter((q) => !state.diagnosis[q.key]);
    if (missing.length) {
      msg.className = 'form-message is-error';
      msg.textContent = '모든 문항에 답해 주세요.';
      return;
    }
    const o = state.onboard;
    const exposureMap = {
      '처음 시작해요': 'none', '가끔 해봤어요': 'some',
      '기초를 알고 있어요': 'some', '영어를 자주 접해요': 'much',
    };
    const body = {
      name: '우리 아이',
      age: o.age,
      exposure: exposureMap[o.experience] || 'none',
      session_length: o.studyTime,
      favorite_topics: o.interests.join(', '),
      ek_kindergarten: o.ek,
      materials: o.materials,
      goal: o.goal,
      diagnosis: state.diagnosis,
    };
    const btn = document.getElementById('diagSubmit');
    btn.disabled = true;
    try {
      const data = await api('POST', '/api/children', body);
      state.child = data.child;
      state.plan = data.plan;
      state.cards = data.cards;
      state.view = 'plan';
      render();
    } catch (err) {
      msg.className = 'form-message is-error';
      msg.textContent = err.message;
      btn.disabled = false;
    }
  });
  const back = document.getElementById('diagBack');
  if (back) back.addEventListener('click', () => { state.view = 'onboarding'; render(); });
}

/* ---------------- plan approval ---------------- */
function planHtml() {
  const plan = state.plan || {};
  const cards = state.cards || [];
  const weeks = [];
  for (let i = 0; i < cards.length; i += 5) weeks.push(cards.slice(i, i + 5));
  return `
  <section class="screen">
    <div class="hero" style="padding:40px 0 24px">
      <span class="eyebrow">4주 계획 초안</span>
      <h1 class="hero-title">이렇게 시작해볼게요</h1>
      <p class="hero-sub">${esc(plan.explanation || '아이의 진단을 바탕으로 4주 계획을 준비했어요.')}</p>
    </div>
    <div class="plan-hero">
      ${weeks.map((week, wi) => `
        <div class="plan-week">
          <div class="plan-week-head">
            <h3 class="plan-week-title">${wi + 1}주차</h3>
            <span class="plan-week-range">${esc(String(week[0].date).slice(5))} ~ ${esc(String(week[week.length - 1].date).slice(5))}</span>
          </div>
          <div class="plan-list">
            ${week.map((c) => `
              <div class="plan-row">
                <span class="plan-date">${esc(String(c.date).slice(5))}</span>
                <span class="plan-task">${esc(c.task)}</span>
                <span class="plan-min">${c.minutes}분</span>
              </div>`).join('')}
          </div>
        </div>`).join('')}
      <p class="small muted mt16">총 ${cards.length}개 학습일 · 승인하면 첫 학습일부터 카드가 도착해요.</p>
    </div>
    <div class="form-message" id="planMsg"></div>
    <button class="btn btn-block" id="approveBtn">계획 승인하고 시작하기</button>
  </section>`;
}

function bindPlan() {
  document.getElementById('approveBtn').addEventListener('click', async () => {
    const msg = document.getElementById('planMsg');
    const btn = document.getElementById('approveBtn');
    btn.disabled = true;
    try {
      await api('POST', '/api/children/' + state.child.id + '/plans/' + state.plan.id + '/approve', {});
      await loadToday();
      state.view = 'today';
      render();
    } catch (err) {
      msg.className = 'form-message is-error';
      msg.textContent = err.message;
      btn.disabled = false;
    }
  });
}

/* ---------------- today ---------------- */
function todayHtml() {
  const t = state.today || {};
  const card = t.card;
  const record = t.record;
  const message = t.message;
  const words = wordsForInterests();
  const phrases = phrasesForInterests();
  const name = (state.child && state.child.name) || '우리 아이';

  return `
  <section class="screen">
    <div class="hero" style="padding:40px 0 20px; text-align:left">
      <span class="eyebrow">오늘의 학습</span>
      <h1 class="hero-title">${esc(name)}의 ${t.today && t.date !== t.today ? esc(t.date) : '오늘'}</h1>
      ${dayPickerHtml(t)}
    </div>
    <div class="today-grid">
      <div>
        ${card ? cardHeroHtml(card) : emptyCardHtml(t)}
        ${card && card.letters && card.letters.length ? `
        <div class="section">
          <h2 class="section-title">오늘의 글자</h2>
          <p class="small muted mt8">오늘 자료에 나오는 글자예요. 자료를 본 뒤 그림을 눌러 소리를 같이 들어 보세요.</p>
          <div class="word-grid mt16">${card.letters.map(letterCardHtml).join('')}</div>
        </div>` : ''}
        ${t.song ? `<div class="only-narrow">${songHtml(t.song)}</div>` : ''}
        <div class="section">
          <div class="section-head">
            <h2 class="section-title">함께 써 볼 단어</h2>
            <button class="btn btn-ghost btn-sm" id="aiBtn">AI 추천 받기</button>
          </div>
          <p class="small muted mt8">아이 관심사로 고른 단어예요. 오늘 자료를 보면서 나오면 같이 말해 보세요. 그림을 누르면 소리가 나요.
            <button type="button" class="link-btn" id="koToggle">${state.showKo ? '한국어 뜻 숨기기' : '한국어 뜻 보기(부모용)'}</button></p>
          <p class="small form-message is-error" id="speakNote" hidden></p>
          <div class="check-question mt8"><strong>부모 확인 질문</strong><br>자료를 보며 단어 2개를 골라 "Where is the ___?" / "Show me ___!"로 물어보세요. 못 찾은 단어는 아래 메모에 적어 주시면 리포트에 남아요.</div>
          <div id="aiResult"></div>
          <div class="word-grid mt16">
            ${words.map(wordCardHtml).join('')}
          </div>
        </div>
        <div class="section">
          <h2 class="section-title">오늘의 표현</h2>
          <div class="phrase-list mt16">
            ${phrases.map((p) => `
              <button type="button" class="phrase-item" data-say="${esc(p.english)}" aria-label="${esc(p.english)} 소리 듣기">
                <span class="phrase-en">${esc(p.english)} <span class="word-tap" aria-hidden="true">🔊</span></span>
                ${state.showKo ? `<span class="phrase-ko">${esc(p.korean)}</span>` : ''}
              </button>`).join('')}
          </div>
        </div>
      </div>
      <div>
        ${t.song ? `<div class="only-wide">${songHtml(t.song, true)}</div>` : ''}
        ${record ? coachMessageHtml(record, message) : feedbackFormHtml()}
        ${t.praise ? praiseHtml(t.praise) : ''}
      </div>
    </div>
  </section>`;
}

function cardHeroHtml(card) {
  return `
  <div class="card-hero">
    <span class="chip chip-accent">오늘의 카드</span>
    <h2 class="card-title mt8">${esc(card.task || '오늘의 학습')}</h2>
    <div class="card-meta">
      <span class="chip">⏱ ${card.minutes}분</span>
      ${card.guide && card.guide.cost ? `<span class="chip">${esc(card.guide.cost)}</span>` : ''}
    </div>
    ${card.check_point ? `<div class="check-point"><strong>확인 포인트</strong><br>${esc(card.check_point)}</div>` : ''}
    ${guideHtml(card)}
  </div>`;
}

/* 칭찬 가이드: 앱 안 점수·보상 대신, 부모가 어떤 말로 어떻게 칭찬할지 안내 (표현은 눌러서 발음 듣기) */
function praiseHtml(p) {
  return `
  <div class="card praise mt16">
    <h2 class="card-title">${esc(p.headline)}</h2>
    <div class="praise-phrases mt8">
      ${p.phrases.map((x) => `<button type="button" class="praise-chip" data-say="${esc(x)}" aria-label="${esc(x)} 소리 듣기">${esc(x)} <span class="word-tap" aria-hidden="true">🔊</span></button>`).join('')}
    </div>
    <ul class="praise-tips">
      ${p.tips.map((t) => `<li><strong>${esc(t.title)}</strong><br><span class="muted">${esc(t.text)}</span></li>`).join('')}
    </ul>
    ${p.streak_note ? `<p class="praise-streak">🌱 ${esc(p.streak_note)}</p>` : ''}
  </div>`;
}

/* 오늘의 동요: 단계에 맞춘 공식 채널 영상 1곡 — 앱 안에서 재생하지 않고 YouTube로 안내 */
function songHtml(song, side) {
  // 넓은 화면(side): 제목을 박스 안 칩으로 넣어 박스 윗변을 '오늘의 카드' 박스와 맞춘다
  return `
  <div class="${side ? 'side-block' : 'section'}">
    ${side ? '' : '<h2 class="section-title">오늘의 동요</h2>'}
    <div class="song-card${side ? '' : ' mt16'}">
      ${side ? '<span class="chip chip-accent song-chip">오늘의 동요</span>' : ''}
      <div class="song-head">
        <span class="song-icon" aria-hidden="true">🎵</span>
        <div>
          <div class="song-title">${esc(song.title)}</div>
          <div class="small muted">${esc(song.channel)} 공식 채널 · 약 ${song.minutes}분 · ${esc(song.focus)}</div>
        </div>
      </div>
      <div class="guide">
        <div class="guide-row"><span class="guide-k">왜 이 노래</span><span>${esc(song.why)}</span></div>
        <div class="guide-row"><span class="guide-k">함께 할 것</span><span>${esc(song.do)}</span></div>
      </div>
      <a class="btn btn-ghost btn-sm mt8" href="${esc(song.url)}" target="_blank" rel="noopener noreferrer">YouTube에서 보기 ↗</a>
      <p class="small muted mt8">아이 혼자 연속 재생하지 않게, 한 곡 듣고 끝내 주세요. 광고가 나올 수 있어요.</p>
    </div>
  </div>`;
}

/* 카드 자료 안내: 무엇인지·어디서·왜·부모 역할·기록 근거 (콘텐츠는 외부 공식 경로로만 안내) */
function guideHtml(card) {
  const g = card && card.guide;
  if (!g) return '';
  const link = g.link ? `<a class="btn btn-ghost btn-sm" href="${esc(g.link)}" target="_blank" rel="noopener noreferrer">공식 사이트 열기 ↗</a>` : '';
  return `
    <div class="guide mt16">
      <div class="guide-row"><span class="guide-k">자료</span><span>${esc(g.title)}${g.kind ? ` <span class="muted small">· ${esc(g.kind)}</span>` : ''}</span></div>
      ${g.about ? `<details class="guide-about"><summary>이 자료가 뭔가요?</summary><p class="small muted">${esc(g.about)}</p></details>` : ''}
      ${g.find ? `<div class="guide-row"><span class="guide-k">찾는 법</span><span>${esc(g.find)}</span></div>` : ''}
      <div class="guide-row"><span class="guide-k">왜 이 자료</span><span>${esc(g.why || '')}</span></div>
      <div class="guide-row"><span class="guide-k">부모 역할</span><span>${esc(g.help || '')}</span></div>
      ${card.basis ? `<div class="guide-row"><span class="guide-k">기록 근거</span><span>${esc(card.basis)}</span></div>` : ''}
      ${g.specific ? '' : `<p class="small muted mt8">이 자료는 아직 권·회차가 정해지지 않은 묶음이에요. 위 찾는 법에서 아이가 좋아하는 것 하나를 골라 주세요.</p>`}
      <div class="mt8 guide-links">${link}${card.content_id ? `<a class="btn btn-ghost btn-sm" href="#curriculum/${esc(card.content_id)}" target="_blank" rel="noopener">전체 커리큘럼 보기 ↗</a>` : ''}</div>
    </div>`;
}

function dayPickerHtml(t) {
  const dates = (t.plan_dates || []).slice().reverse();
  if (dates.length < 2) return `<p class="hero-sub">${esc(t.date || '')}</p>`;
  return `
    <label class="day-picker mt8">
      <span class="small muted">날짜 선택 (지난 학습일 보기·밀린 기록 남기기)</span>
      <select class="input" id="dayPick">
        ${dates.map((d) => `<option value="${esc(d)}" ${d === t.date ? 'selected' : ''}>${esc(d)}${d === t.today ? ' (오늘)' : ''}</option>`).join('')}
      </select>
    </label>`;
}

/* 부모 발음 확인용: 브라우저 내장 음성 (앱이 콘텐츠를 재생하는 게 아니라 부모가 읽어 줄 발음을 확인) */
function speakUnavailable() {
  const ua = navigator.userAgent || '';
  if (/KAKAOTALK|NAVER|Instagram|FBAN|FBAV|Line\//i.test(ua)) return '앱 안 브라우저에서는 소리가 나지 않을 수 있어요. 오른쪽 위 메뉴에서 Safari·Chrome으로 열어 주세요.';
  if (!('speechSynthesis' in window)) return '이 브라우저는 소리 재생을 지원하지 않아요. Safari·Chrome으로 열어 주세요.';
  return '';
}

function speak(text) {
  const note = document.getElementById('speakNote');
  const problem = speakUnavailable();
  if (note) {
    note.textContent = problem || '소리가 안 들리면 휴대폰 무음 모드와 음량을 확인해 주세요.';
    note.hidden = !problem;
  }
  try {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-US';
    u.rate = 0.85;
    window.speechSynthesis.speak(u);
  } catch (e) { /* 음성 미지원 기기 */ }
}

function emptyCardHtml(t) {
  if (t.draft_plan) {
    return `<div class="card"><p class="muted">계획 초안이 아직 승인되지 않았어요.</p>
      <button class="btn mt16" id="goApprove">계획 승인하러 가기</button></div>`;
  }
  if (state.nextCard) {
    const c = state.nextCard;
    return `<div class="card-hero">
      <span class="chip chip-accent">다음 학습일 · ${esc(c.date)}</span>
      <h2 class="card-title mt8">${esc(c.task || '다음 학습')}</h2>
      <div class="card-meta"><span class="chip">⏱ ${c.minutes}분</span></div>
      ${c.check_point ? `<div class="check-point"><strong>확인 포인트</strong><br>${esc(c.check_point)}</div>` : ''}
      ${guideHtml(c)}
      <p class="small muted mt16">오늘은 학습일이 아니에요. 미리 살펴보세요. 🌱</p>
    </div>`;
  }
  return `<div class="card"><p class="muted">오늘은 계획된 학습일이 아니에요. 다음 학습일에 카드가 도착해요. 🌱</p></div>`;
}

/* 아이와 같이 보는 화면: 그림 + 영어만 크게. 누르면 소리. 한국어 뜻은 부모가 켤 때만 (보호자 피드백) */
function wordCardHtml(w) {
  return `
  <button type="button" class="word-card" data-say="${esc(w.word)}" aria-label="${esc(w.word)} 소리 듣기">
    <span class="word-emoji">${esc(w.emoji || '📘')}</span>
    <span class="word-text">${esc(w.word)}</span>
    ${state.showKo ? `<span class="word-meaning">${esc(w.meaning)}</span>` : ''}
    <span class="word-tap" aria-hidden="true">🔊</span>
  </button>`;
}

/* 알파벳을 아직 모르는 아이: 그날 자료의 글자 (예: A a — apple). 누르면 소리 */
function letterCardHtml(l) {
  return `
  <button type="button" class="word-card letter-card" data-say="${esc(l.say)}" aria-label="${esc(l.letter)} 소리 듣기">
    <span class="letter-big">${esc(l.letter)}</span>
    <span class="word-emoji">${esc(l.emoji || '')}</span>
    <span class="word-text">${esc(l.word)}</span>
    <span class="word-tap" aria-hidden="true">🔊</span>
  </button>`;
}

function feedbackFormHtml() {
  return `
  <div class="card">
    <div class="row">
      <h2 class="card-title">${state.today && state.today.today && state.today.date !== state.today.today ? esc(state.today.date) + ' 학습은' : '오늘 학습은'} 어땠나요?</h2>
      <span class="spacer"></span>
      <span class="ai-badge">부모 1분 기록</span>
    </div>
    <p class="small muted mt8">아이와 함께한 뒤 1분이면 충분해요. <strong>완료도·만족도·흥미·이해도는 필수</strong>예요.</p>
    <form class="feedback-form mt16" id="feedbackForm">
      <div>
        <span class="field-label">완료도<span class="required-dot">필수</span></span>
        <div class="choice-grid" data-fb="completion">
          <button type="button" class="choice-btn" data-value="full">잘 따라옴</button>
          <button type="button" class="choice-btn" data-value="partial">일부</button>
          <button type="button" class="choice-btn" data-value="none">못 함</button>
        </div>
      </div>
      ${scaleHtml('satisfaction', '만족도')}
      ${scaleHtml('interest', '흥미')}
      ${scaleHtml('comprehension', '이해도')}
      <label class="field">
        <span class="field-label">한 줄 메모 (선택)</span>
        <textarea class="input" name="memo" maxlength="500" placeholder="예: 소리 내어 읽기를 좋아했어요. bus는 못 찾았어요"></textarea>
      </label>
      <label class="checkbox-row">
        <input type="checkbox" name="rest_day" />
        <span>오늘은 휴식일이에요 (분기·성취에서 제외)</span>
      </label>
      <div class="form-message" id="fbMsg"></div>
      <button class="btn btn-block" type="submit">기록하고 코치 메시지 받기</button>
    </form>
  </div>`;
}

function scaleHtml(name, label) {
  return `
  <div>
    <span class="field-label">${esc(label)} (1~5)<span class="required-dot">필수</span></span>
    <div class="scale" data-fb="${name}">
      ${[1, 2, 3, 4, 5].map((n) => `<button type="button" class="scale-btn" data-value="${n}">${n}</button>`).join('')}
    </div>
  </div>`;
}

function coachMessageHtml(record, message) {
  if (record && record.rest_day) {
    return `<div class="card"><h2 class="card-title">오늘은 휴식일 🌿</h2>
      <p class="muted mt8">잘 쉬었어요. 내일 다시 만나요.</p></div>`;
  }
  if (!message) {
    return `<div class="card"><h2 class="card-title">오늘 기록 완료</h2>
      <p class="muted mt8">코치 메시지를 준비 중이에요.</p></div>`;
  }
  return `
  <div class="coach-message">
    <div class="coach-head">
      <span class="badge-case case-${esc(message.branch || 'A')}">${caseLabel(message.branch)}</span>
      <span class="ai-badge">AI가 작성한 코칭 메시지입니다</span>
    </div>
    ${esc(message.body)}
  </div>`;
}

function caseLabel(branch) {
  return { A: '순항', B: '편한 속도', C: '맞춤 조정' }[branch] || '코칭';
}

function bindToday() {
  const goApprove = document.getElementById('goApprove');
  if (goApprove) {
    goApprove.addEventListener('click', async () => {
      try {
        const plan = await api('GET', '/api/children/' + state.child.id + '/plan');
        state.plan = plan.plan;
        state.cards = plan.cards || [];
      } catch (e) {
        state.plan = state.today.draft_plan;
        state.cards = [];
      }
      state.view = 'plan';
      render();
    });
  }
  const aiBtn = document.getElementById('aiBtn');
  if (aiBtn) aiBtn.addEventListener('click', runAiRecommendation);
  const dayPick = document.getElementById('dayPick');
  if (dayPick) dayPick.addEventListener('change', async () => {
    await loadToday(dayPick.value === state.today.today ? undefined : dayPick.value);
    render();
  });
  document.querySelectorAll('[data-say]').forEach((b) => {
    b.addEventListener('click', () => speak(b.getAttribute('data-say')));
  });
  const koToggle = document.getElementById('koToggle');
  if (koToggle) koToggle.addEventListener('click', () => {
    state.showKo = !state.showKo;
    try { localStorage.setItem('bloomy_show_ko', state.showKo ? '1' : ''); } catch (e) { /* 저장 불가 */ }
    render();
  });

  const form = document.getElementById('feedbackForm');
  if (form) bindFeedback(form);
}

function bindFeedback(form) {
  const fb = { completion: null, satisfaction: null, interest: null, comprehension: null };
  form.querySelectorAll('[data-fb]').forEach((group) => {
    const key = group.getAttribute('data-fb');
    group.querySelectorAll('button').forEach((btn) => {
      btn.addEventListener('click', () => {
        fb[key] = btn.getAttribute('data-value');
        group.querySelectorAll('button').forEach((b) => b.classList.remove('is-selected'));
        btn.classList.add('is-selected');
      });
    });
  });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = document.getElementById('fbMsg');
    const restDay = form.rest_day.checked;
    if (!restDay) {
      const missing = ['completion', 'satisfaction', 'interest', 'comprehension'].filter((k) => !fb[k]);
      if (missing.length) {
        msg.className = 'form-message is-error';
        msg.textContent = '완료도·만족도·흥미·이해도를 모두 선택해 주세요.';
        msg.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
    }
    const body = {
      completion: fb.completion || 'full',
      satisfaction: Number(fb.satisfaction) || 3,
      interest: Number(fb.interest) || 3,
      comprehension: Number(fb.comprehension) || 3,
      memo: form.memo.value.trim(),
      rest_day: restDay,
      date: state.today && state.today.date,
    };
    const btn = form.querySelector('button[type="submit"]');
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = '기록 중…';
    try {
      const data = await api('POST', '/api/children/' + state.child.id + '/feedback', body);
      state.lastFeedback = data;
      await loadToday(state.today && state.today.date !== state.today.today ? state.today.date : undefined);
      render();
    } catch (err) {
      msg.className = 'form-message is-error';
      msg.textContent = err.message || '저장에 실패했어요';
      msg.scrollIntoView({ behavior: 'smooth', block: 'center' });
      btn.disabled = false;
      btn.textContent = original;
    }
  });
}

async function runAiRecommendation() {
  const box = document.getElementById('aiResult');
  const btn = document.getElementById('aiBtn');
  if (!box) return;
  btn.disabled = true;
  box.innerHTML = `<p class="small muted">AI가 기록을 살펴보고 있어요…</p>`;
  const o = state.onboard;
  const words = wordsForInterests();
  const phrases = phrasesForInterests();
  const payload = {
    profile: {
      age: (state.child && state.child.age) || o.age || 5,
      experience: o.experience || '가끔 해봤어요',
      interests: childInterests(),
      studyTime: (state.child && state.child.session_length) || o.studyTime || 10,
    },
    diagnosis: {},
    stats: { recentAttemptCount: 0, recentAccuracy: null, weakWords: [], words: [], completionRate: 0 },
    words,
    phrases,
  };
  try {
    const rec = await api('POST', '/api/learning/recommendation', payload);
    state.aiRec = rec;
    const recWords = (rec.words || []).map((w) => w.word);
    box.innerHTML = `
      <div class="card" style="border-color:var(--accent)">
        <div class="row">
          <span class="ai-badge">AI 추천 · ${esc(rec.difficulty)}</span>
          <span class="chip">⏱ ${rec.estimatedMinutes}분</span>
        </div>
        <p class="mt8">${esc(rec.summary)}</p>
        <p class="small muted mt8">${esc(rec.reason)}</p>
        ${recWords.length ? `<div class="card-meta">${recWords.map((w) => `<span class="chip chip-accent">${esc(w)}</span>`).join('')}</div>` : ''}
        <p class="small muted mt8">${esc(rec.nextLearning)}</p>
      </div>`;
  } catch (err) {
    box.innerHTML = `<p class="small muted">AI 추천을 불러오지 못했어요. (${esc(err.message)})</p>`;
  } finally {
    btn.disabled = false;
  }
}

/* ---------------- report ---------------- */
/* ---------------- 학습 계획 (메뉴: 언제든 4주 계획 보기) ---------------- */
const DAY_STATUS = {
  done: ['완료', 'st-done'], today: ['오늘', 'st-today'], planned: ['예정', 'st-planned'],
  missed: ['기록 없음', 'st-missed'], none: ['못 함', 'st-missed'], rest: ['쉬는 날', 'st-later'],
};
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

async function loadMyPlan() {
  if (!state.child) return;
  try {
    state.myPlan = await api('GET', '/api/children/' + state.child.id + '/plan');
  } catch (e) {
    state.myPlan = null;
  }
}

function weekdayOf(d) {
  const [y, m, dd] = String(d).split('-').map(Number);
  return WEEKDAYS[new Date(y, m - 1, dd).getDay()];
}

function myPlanHtml() {
  const data = state.myPlan;
  if (!data || !data.plan) {
    return `<section class="screen"><div class="empty">아직 학습 계획이 없어요.<br>프로필과 진단을 마치면 4주 계획이 만들어져요.</div></section>`;
  }
  const plan = data.plan, cards = data.cards || [], today = data.today || '';
  if (plan.status !== 'approved') {
    return `<section class="screen">
      <div class="hero" style="padding:40px 0 24px"><span class="eyebrow">학습 계획</span>
        <h1 class="hero-title">계획 초안이 준비돼 있어요</h1>
        <p class="hero-sub">승인하면 첫 학습일부터 카드가 도착해요.</p></div>
      <button class="btn btn-block" id="myPlanApprove">계획 확인하고 승인하기</button>
    </section>`;
  }
  const weeks = [];
  for (let i = 0; i < cards.length; i += 5) weeks.push(cards.slice(i, i + 5));
  const passed = cards.filter((c) => c.date <= today);
  const done = cards.filter((c) => c.day_status === 'done').length;
  const chip = (k) => { const [t, cls] = DAY_STATUS[k] || [k, '']; return `<span class="st ${cls}">${esc(t)}</span>`; };
  return `
  <section class="screen">
    <div class="hero" style="padding:40px 0 24px">
      <span class="eyebrow">학습 계획</span>
      <h1 class="hero-title">우리 아이 4주 계획</h1>
      <p class="hero-sub">${esc(plan.explanation || '아이의 진단을 바탕으로 만든 4주 계획이에요.')}</p>
      <p class="small muted mt8">${cards.length ? `${esc(fmtDate(cards[0].date))} ~ ${esc(fmtDate(cards[cards.length - 1].date))} · ` : ''}지난 학습일 ${passed.length}일 중 ${done}일 완료</p>
    </div>
    <div class="plan-hero">
      ${weeks.map((week, wi) => `
        <div class="plan-week">
          <div class="plan-week-head">
            <h3 class="plan-week-title">${wi + 1}주차</h3>
            <span class="plan-week-range">${esc(fmtDate(week[0].date))} ~ ${esc(fmtDate(week[week.length - 1].date))}</span>
          </div>
          <div class="plan-list">
            ${week.map((c) => {
              const open = c.date <= today;
              return `
              <div class="plan-row${c.date === today ? ' is-today' : ''}${open ? ' is-open' : ''}"${open ? ` data-date="${esc(c.date)}" role="button" tabindex="0" title="이날 카드 보기"` : ''}>
                <span class="plan-date">${esc(fmtDate(c.date))} (${weekdayOf(c.date)})</span>
                <span class="plan-task">${esc(c.task)}${c.content_title ? `<span class="plan-src">${esc(c.content_title)}</span>` : ''}</span>
                <span class="plan-min">${c.minutes}분</span>
                ${chip(c.day_status)}
                ${c.content_id ? `<a class="plan-cur" href="#curriculum/${esc(c.content_id)}" target="_blank" rel="noopener" title="전체 커리큘럼 보기">↗</a>` : ''}
              </div>`;
            }).join('')}
          </div>
        </div>`).join('')}
      <p class="small muted mt16">오늘까지의 날짜를 누르면 그날 카드와 기록을 볼 수 있어요. ↗는 자료별 전체 커리큘럼(새 탭)이에요.</p>
    </div>
  </section>`;
}

function bindMyPlan() {
  const approve = document.getElementById('myPlanApprove');
  if (approve) {
    approve.addEventListener('click', () => {
      state.plan = state.myPlan.plan;
      state.cards = state.myPlan.cards || [];
      state.view = 'plan';
      render();
    });
  }
  const go = async (date) => { await loadToday(date); state.view = 'today'; render(); window.scrollTo(0, 0); };
  document.querySelectorAll('.plan-row.is-open').forEach((row) => {
    row.addEventListener('click', (e) => {
      if (e.target.closest('a')) return;
      go(row.getAttribute('data-date'));
    });
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(row.getAttribute('data-date')); }
    });
  });
}

function reportHtml() {
  const r = state.report;
  const a = state.achievement;
  if (!r) {
    return `<section class="screen"><div class="empty">아직 리포트가 없어요.<br>학습 기록이 쌓이면 이곳에 나타나요.</div></section>`;
  }
  return `
  <section class="screen">
    <div class="hero" style="padding:40px 0 20px; text-align:left">
      <span class="eyebrow">리포트</span>
      <h1 class="hero-title">주간 리포트</h1>
      <p class="hero-sub">${esc(r.week_start)} ~ ${esc(r.week_end)}</p>
      <div class="row mt16">
        <button class="btn btn-ghost btn-sm" data-week="last">← 지난 주</button>
        <button class="btn btn-ghost btn-sm" data-week="this">이번 주 →</button>
      </div>
    </div>
    <div class="stat-grid">
      <div class="stat"><div class="stat-num">${r.record_days}</div><div class="stat-lbl">학습한 날</div></div>
      <div class="stat"><div class="stat-num">${fmtAvg(r.avg_interest)}</div><div class="stat-lbl">평균 흥미</div></div>
      <div class="stat"><div class="stat-num">${fmtAvg(r.avg_comprehension)}</div><div class="stat-lbl">평균 이해도</div></div>
      <div class="stat"><div class="stat-num">${r.branch_counts ? (r.branch_counts.A || 0) : 0}</div><div class="stat-lbl">순항한 날</div></div>
    </div>
    <div class="report-block mt24">
      <h3>이번 주 요약</h3>
      <p class="muted">${esc(r.summary || '')}</p>
      ${r.confidence_sentence ? `<div class="confidence-note mt16">${esc(r.confidence_sentence)}</div>` : ''}
      ${r.honest_note ? `<div class="honest-note mt16">${esc(r.honest_note)}</div>` : ''}
    </div>
    ${(r.days && r.days.length) ? `
      <div class="report-block">
        <h3>이번 주 기록 한눈에</h3>
        <div class="trend-list">
          ${r.days.map((d) => `<div class="trend-item"><strong>${esc(d.date)}</strong> ${esc(d.what || '')} · ${esc(COMPLETION_KO[d.completion] || '')} · 흥미 ${esc(d.interest)} · 이해도 ${esc(d.comprehension)}${d.memo ? `<br><span class="small muted">메모: ${esc(d.memo)}</span>` : ''}</div>`).join('')}
        </div>
      </div>` : ''}
    ${(r.learned && r.learned.length) ? `
      <div class="report-block">
        <h3>잘 해낸 것 (부모 관찰 기록)</h3>
        <div class="learned-list">
          ${r.learned.map((x) => `<div class="learned-item">✓ ${esc(x)}</div>`).join('')}
        </div>
      </div>` : ''}
    ${(r.trend && r.trend.length) ? `
      <div class="report-block">
        <h3>추이</h3>
        <div class="trend-list">
          ${r.trend.map((x) => `<div class="trend-item">${esc(x)}</div>`).join('')}
        </div>
      </div>` : ''}
    ${(r.choices && r.choices.length) ? `
      <div class="report-block">
        <h3>다음 주 선택지</h3>
        <div class="trend-list">
          ${r.choices.map((x) => `<div class="trend-item">${esc(x)}</div>`).join('')}
        </div>
      </div>` : ''}
    ${a ? `
      <div class="report-block">
        <h3>이번 달 성취 (${esc(a.month)})</h3>
        <div class="stat-grid">
          <div class="stat"><div class="stat-num">${a.record_days}</div><div class="stat-lbl">학습일</div></div>
          <div class="stat"><div class="stat-num">${a.max_streak}</div><div class="stat-lbl">최장 연속</div></div>
          <div class="stat"><div class="stat-num">${fmtAvg(a.avg_interest)}</div><div class="stat-lbl">평균 흥미</div></div>
          <div class="stat"><div class="stat-num">${fmtAvg(a.avg_comprehension)}</div><div class="stat-lbl">평균 이해도</div></div>
        </div>
        <p class="small muted mt16">${esc(a.note || '')}</p>
      </div>` : ''}
  </section>`;
}

const COMPLETION_KO = { full: '끝까지', partial: '일부', none: '못 함' };

function fmtAvg(v) {
  return v == null ? '–' : Number(v).toFixed(1);
}

function bindReport() {
  document.querySelectorAll('[data-week]').forEach((b) => {
    b.addEventListener('click', async () => {
      state.reportWeek = b.getAttribute('data-week') === 'last' ? lastWeekMonday() : thisWeekMonday();
      await loadReport();
      render();
    });
  });
}

/* ---------------- navigation ---------------- */
function bindGlobalNav() {
  document.querySelectorAll('[data-nav]').forEach((b) => {
    b.addEventListener('click', async (e) => {
      e.preventDefault();
      const target = b.getAttribute('data-nav');
      if (location.hash) history.replaceState(null, '', location.pathname);  // 커리큘럼 페이지에서 나갈 때
      if (state.token && state.account && !hasConsent()) {
        state.view = 'consent';  // 동의 전에는 다른 화면으로 이동하지 않는다
      } else if (target === 'home') {
        if (!state.token) { state.view = 'auth'; }
        else if (state.child) { await loadToday(); state.view = 'today'; }
        else { state.view = 'onboarding'; }
      } else if (target === 'today') {
        if (!state.token) { state.view = 'auth'; }
        else if (!state.child) { state.view = 'onboarding'; }
        else { await loadToday(); state.view = 'today'; }
      } else if (target === 'myplan') {
        if (!state.token) { state.view = 'auth'; }
        else if (!state.child) { state.view = 'onboarding'; }
        else { await loadMyPlan(); state.view = 'myplan'; }
      } else if (target === 'report') {
        if (!state.token) { state.view = 'auth'; }
        else if (!state.child) { state.view = 'onboarding'; }
        else {
          // 메뉴로 들어오면 항상 이번 주부터 (지난 주 선택이 다른 화면을 다녀와도 남던 문제)
          state.reportWeek = null;
          await loadReport();
          state.view = 'report';
        }
      }
      render();
    });
  });
}

/* ---------------- init ---------------- */
async function init() {
  applyTheme();
  document.getElementById('themeToggle').addEventListener('click', toggleTheme);
  document.getElementById('accountBtn').addEventListener('click', () => {
    if (state.token && state.account) {
      state.view = hasConsent() ? 'account' : 'consent';
      render();
    } else if (state.token) {
      if (confirm('로그아웃할까요?')) logout();
    } else {
      state.view = 'auth';
      render();
    }
  });
  bindGlobalNav();
  window.addEventListener('hashchange', async () => {
    const id = curriculumIdFromHash();
    if (id && state.token && state.child && hasConsent()) { await loadCurriculum(id); render(); }
  });

  if (state.token) {
    try {
      const me = await api('GET', '/api/me');
      state.account = me.account;
      state.child = me.children && me.children.length ? me.children[0] : null;
      await routeAfterAccount();
    } catch (e) {
      state.view = 'auth';
    }
  } else {
    state.view = 'auth';
  }
  render();
}

document.addEventListener('DOMContentLoaded', init);
