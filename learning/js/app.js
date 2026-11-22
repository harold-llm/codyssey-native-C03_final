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

const state = {
  token: localStorage.getItem(TOKEN_KEY) || null,
  account: null,
  child: null,
  view: 'loading',
  authMode: 'login',
  onboard: { age: null, experience: null, interests: [], studyTime: null, ek: false, materials: '', goal: '듣기' },
  diagnosisQuestions: [],
  diagnosis: {},
  today: null,
  nextCard: null,
  lastFeedback: null,
  report: null,
  achievement: null,
  aiRec: null,
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
  if (res.status === 401) {
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
  localStorage.removeItem(TOKEN_KEY);
  state.view = 'auth';
  render();
}

async function afterAuth(data) {
  state.token = data.token;
  state.account = data.account;
  localStorage.setItem(TOKEN_KEY, data.token);
  if (data.children && data.children.length) {
    state.child = data.children[0];
    await loadToday();
    state.view = 'today';
  } else {
    state.view = 'onboarding';
  }
  render();
}

/* ---------------- data loaders ---------------- */
async function loadToday() {
  if (!state.child) return;
  try {
    state.today = await api('GET', '/api/children/' + state.child.id + '/today');
    state.nextCard = null;
    if (!state.today.card) {
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
    case 'onboarding': app.innerHTML = onboardingHtml(); bindOnboarding(); break;
    case 'diagnosis': app.innerHTML = diagnosisHtml(); bindDiagnosis(); break;
    case 'plan': app.innerHTML = planHtml(); bindPlan(); break;
    case 'today': app.innerHTML = todayHtml(); bindToday(); break;
    case 'report': app.innerHTML = reportHtml(); bindReport(); break;
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
          <div class="form-message" id="authMsg"></div>
          <button class="btn btn-block" type="submit">${isLogin ? '로그인' : '회원가입'}</button>
        </form>
      </div>
    </div>
  </section>`;
}

function bindAuth() {
  document.querySelectorAll('[data-auth]').forEach((b) => {
    b.addEventListener('click', () => {
      state.authMode = b.getAttribute('data-auth');
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
      const data = await api('POST', path, { email, password });
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
      <h1 class="hero-title">${esc(name)}의 오늘</h1>
      <p class="hero-sub">${esc(t.date || '')}</p>
    </div>
    <div class="today-grid">
      <div>
        ${card ? cardHeroHtml(card) : emptyCardHtml(t)}
        <div class="section">
          <div class="section-head">
            <h2 class="section-title">오늘의 단어</h2>
            <button class="btn btn-ghost btn-sm" id="aiBtn">AI 추천 받기</button>
          </div>
          <div id="aiResult"></div>
          <div class="word-grid mt16">
            ${words.map(wordCardHtml).join('')}
          </div>
        </div>
        <div class="section">
          <h2 class="section-title">오늘의 표현</h2>
          <div class="phrase-list mt16">
            ${phrases.map((p) => `
              <div class="phrase-item">
                <div class="phrase-en">${esc(p.english)}</div>
                <div class="phrase-ko">${esc(p.korean)}</div>
                <div class="phrase-pron">[${esc(p.pronunciation)}]</div>
              </div>`).join('')}
          </div>
        </div>
      </div>
      <div>
        ${record ? coachMessageHtml(record, message) : feedbackFormHtml()}
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
      ${card.content_id ? `<span class="chip">${esc(card.content_id)}</span>` : ''}
    </div>
    ${card.check_point ? `<div class="check-point"><strong>확인 포인트</strong><br>${esc(card.check_point)}</div>` : ''}
  </div>`;
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
      <p class="small muted mt16">오늘은 학습일이 아니에요. 미리 살펴보세요. 🌱</p>
    </div>`;
  }
  return `<div class="card"><p class="muted">오늘은 계획된 학습일이 아니에요. 다음 학습일에 카드가 도착해요. 🌱</p></div>`;
}

function wordCardHtml(w) {
  return `
  <div class="word-card">
    <span class="word-emoji">${esc(w.emoji || '📘')}</span>
    <div class="word-text">${esc(w.word)}</div>
    <div class="word-meaning">${esc(w.meaning)}</div>
    <div class="word-pron">[${esc(w.pronunciation)}]</div>
  </div>`;
}

function feedbackFormHtml() {
  return `
  <div class="card">
    <div class="row">
      <h2 class="card-title">오늘 학습은 어땠나요?</h2>
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
        <textarea class="input" name="memo" maxlength="500" placeholder="예: 오늘은 소리 내어 읽기를 좋아했어요"></textarea>
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
    };
    const btn = form.querySelector('button[type="submit"]');
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = '기록 중…';
    try {
      const data = await api('POST', '/api/children/' + state.child.id + '/feedback', body);
      state.lastFeedback = data;
      await loadToday();
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
    ${(r.learned && r.learned.length) ? `
      <div class="report-block">
        <h3>새로 익힌 것</h3>
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
      if (target === 'home') {
        if (!state.token) { state.view = 'auth'; }
        else if (state.child) { await loadToday(); state.view = 'today'; }
        else { state.view = 'onboarding'; }
      } else if (target === 'today') {
        if (!state.token) { state.view = 'auth'; }
        else if (!state.child) { state.view = 'onboarding'; }
        else { await loadToday(); state.view = 'today'; }
      } else if (target === 'report') {
        if (!state.token) { state.view = 'auth'; }
        else if (!state.child) { state.view = 'onboarding'; }
        else { await loadReport(); state.view = 'report'; }
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
    if (state.token) {
      if (confirm('로그아웃할까요?')) logout();
    } else {
      state.view = 'auth';
      render();
    }
  });
  bindGlobalNav();

  if (state.token) {
    try {
      const me = await api('GET', '/api/me');
      state.account = me.account;
      if (me.children && me.children.length) {
        state.child = me.children[0];
        await loadToday();
        state.view = 'today';
      } else {
        state.view = 'onboarding';
      }
    } catch (e) {
      state.view = 'auth';
    }
  } else {
    state.view = 'auth';
  }
  render();
}

document.addEventListener('DOMContentLoaded', init);
