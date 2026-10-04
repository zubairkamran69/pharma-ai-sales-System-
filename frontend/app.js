const API_URL = (window.PHARMAAI_API_URL || '').replace(/\/+$/, '');
const API = `${API_URL}/api`;
let token = localStorage.getItem('pharmaai_token');
let me = JSON.parse(localStorage.getItem('pharmaai_user') || 'null');
let role = me?.role || 'doctor', page = 'dashboard', authMode = 'login', currentConversationId = null, humanConversationId = null, notificationItems = [], hiddenRepIds = [], navigationRequest = 0, humanRefreshTimer = null;
const navs = {
    pharma: [['dashboard', '⌂', 'Command Center'], ['medicines', '▦', 'Medicine Library'], ['knowledge', '◇', 'Knowledge Center'], ['doctors', '◉', 'Doctor Intelligence'], ['reps', '♙', 'Sales Representatives'], ['agent', '✦', 'AI Sales Agent'], ['human', '◌', 'Doctor Chats'], ['orders', '□', 'Orders'], ['tickets', '!', 'Escalations']],
    sales_rep: [['dashboard', '⌂', 'Sales Workspace'], ['medicines', '▦', 'My Products'], ['doctors', '◉', 'Doctor Intelligence'], ['agent', '✦', 'AI Sales Agent'], ['human', '◌', 'Doctor Chats'], ['tickets', '!', 'My Support Tickets'], ['orders', '□', 'Orders']],
    doctor: [['dashboard', '⌂', 'My Dashboard'], ['medicines', '▦', 'Medicine Hub'], ['agent', '✦', 'AI Medical Assistant'], ['human', '◌', 'Company Chats'], ['orders', '□', 'My Requests'], ['tickets', '!', 'Human Support'], ['profile', '○', 'My Profile']],
    admin: [['dashboard', '⌂', 'Owner Command Center'], ['users', '◉', 'Verification & Users'], ['agent', '✦', 'Owner AI Agent']]
};
function esc(s) { return String(s ?? '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c])) }
function initials(n) { return String(n || '').split(' ').filter(x => x !== 'Dr.').slice(0, 2).map(x => x[0]).join('').toUpperCase() || 'PA' }
function toast(x) { const t = document.getElementById('toast'); if (!t) return; t.textContent = x; t.className = 'toast show'; setTimeout(() => t.className = 'toast', 2600) }
function brand() { return `<div class="brand"><img class="brand-logo" src="/static/logo.png" alt="PharmaAI"><div><b>Pharma<span>AI</span></b><small>SALES AGENT</small></div></div>` }
function formatPrice(value) {
    const num = Number(value ?? 0);
    if (!Number.isFinite(num)) return 'PKR 0.00';
    return `PKR ${num.toLocaleString('en-PK', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function dashboardPrice(value) {
    return formatPrice(Number(value ?? 0));
}

function normalizeCurrencyDisplay() {
    document.querySelectorAll('*').forEach((el) => {
        [...el.childNodes].forEach((node) => {
            if (node.nodeType !== Node.TEXT_NODE) return;
            const source = node.textContent || '';
            const match = source.match(/\$\s*([0-9][0-9,]*(?:\.\d+)?)\s*(K)?/i);
            if (!match) return;
            const scaled = Number((match[1] || '0').replace(/,/g, '')) * (match[2] ? 1000 : 1);
            if (!Number.isFinite(scaled)) return;
            node.textContent = source.replace(/\$\s*([0-9][0-9,]*(?:\.\d+)?)\s*(K)?/i, formatPrice(scaled));
        });
    });
}
function roleLabel(roleKey) {
    if (roleKey === 'admin') return 'Platform Owner';
    if (roleKey === 'pharma') return 'Pharma Company';
    if (roleKey === 'sales_rep') return 'Sales Representative';
    if (roleKey === 'doctor') return 'Doctor';
    return 'User';
}
function roleBadgeText(roleKey) {
    if (roleKey === 'admin') return 'PLATFORM OWNER';
    if (roleKey === 'pharma') return 'PHARMA COMPANY';
    if (roleKey === 'sales_rep') return 'SALES REPRESENTATIVE';
    if (roleKey === 'doctor') return 'DOCTOR';
    return 'USER';
}
function sidebarOrgLabel(user) {
    if (!user) return '';
    if (user.role === 'admin') return 'Platform Administrator';
    if (user.company) return user.company;
    if (user.role === 'doctor') return 'Doctor';
    if (user.role === 'sales_rep') return 'Sales Team';
    return '';
}
function clearSessionState() {
    token = null;
    me = null;
    role = 'doctor';
    page = 'dashboard';
    authMode = 'login';
    currentConversationId = null;
    humanConversationId = null;
    notificationItems = [];
    hiddenRepIds = [];
    ['pharmaai_token', 'pharmaai_user', 'pharmaai_company', 'pharmaai_role'].forEach(key => localStorage.removeItem(key));
    sessionStorage.clear();
}
function handleUnauthorized(message = 'Your session has expired. Please sign in again.') {
    clearSessionState();
    closeLogoutModal();
    closeSessionExpiredModal();
    showSessionExpiredModal(message);
}
function closeSessionExpiredModal() { document.getElementById('sessionExpiredModal')?.remove(); }
function closeLogoutModal() { document.getElementById('logoutConfirmModal')?.remove(); }
function showSessionExpiredModal(message = 'Your session has expired. Please sign in again.') {
    closeLogoutModal();
    closeSessionExpiredModal();
    document.body.insertAdjacentHTML('beforeend', `<div class="modal-backdrop" id="sessionExpiredModal" role="presentation"><div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="sessionExpiredTitle"><div class="modal-head"><div><div class="ey">SESSION STATUS</div><h2 id="sessionExpiredTitle">Session Expired</h2><p>${esc(message || 'Your session has expired. Please sign in again.')}</p></div></div><div class="modal-actions"><button class="primary" type="button" onclick="closeSessionExpiredModal(); authMode='login'; window.history.pushState({}, '', '/login'); renderAuth();">Sign In</button></div></div></div>`);
    toast(message);
    authMode = 'login';
    window.history.pushState({}, '', '/login');
    renderAuth();
}
function showLogoutModal() {
    closeLogoutModal();
    closeSessionExpiredModal();
    document.body.insertAdjacentHTML('beforeend', `<div class="modal-backdrop" id="logoutConfirmModal" role="presentation" onclick="if(event.target===this)closeLogoutModal()"><div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="logoutConfirmTitle"><div class="modal-head"><div><div class="ey">ACCOUNT</div><h2 id="logoutConfirmTitle">Sign out of PharmaAI?</h2><p>Are you sure you want to sign out of your PharmaAI account?</p></div></div><div class="logout-copy"><p>You will need to sign in again to access your dashboard.</p></div><div class="modal-actions"><button class="secondary" type="button" onclick="closeLogoutModal()">Cancel</button><button class="primary" id="logoutConfirmButton" type="button" onclick="confirmLogout()">Sign Out</button></div></div></div>`);
    const button = document.getElementById('logoutConfirmButton'); if (button) button.focus();
}
function closeInputModal(id = 'inputModal') { document.getElementById(id)?.remove(); }
function showInputModal({ id = 'inputModal', title, message, label, value = '', confirmText = 'Confirm', confirmClass = 'primary', onConfirm }) {
    closeInputModal(id);
    document.body.insertAdjacentHTML('beforeend', `<div class="modal-backdrop" id="${id}" role="presentation" onclick="if(event.target===this)closeInputModal('${id}')"><div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="${id}Title"><div class="modal-head"><div><div class="ey">DETAIL</div><h2 id="${id}Title">${esc(title || 'Continue')}</h2><p>${esc(message || '')}</p></div></div><div class="field"><label for="${id}Input">${esc(label || 'Value')}</label><input id="${id}Input" type="text" value="${esc(value)}"></div><div class="modal-actions"><button class="secondary" type="button" onclick="closeInputModal('${id}')">Cancel</button><button class="${confirmClass}" id="${id}Confirm" type="button">${esc(confirmText)}</button></div></div></div>`);
    const input = document.getElementById(`${id}Input`);
    const confirmButton = document.getElementById(`${id}Confirm`);
    if (input) {
        input.focus();
        input.select();
    }
    confirmButton?.addEventListener('click', () => {
        const nextValue = input ? input.value.trim() : '';
        closeInputModal(id);
        if (typeof onConfirm === 'function') onConfirm(nextValue);
    });
}
async function confirmLogout() {
    const button = document.getElementById('logoutConfirmButton'); if (button) button.disabled = true;
    try {
        if (token) {
            try {
                await fetch(API + '/auth/logout', {
                    method: 'POST',
                    headers: { Authorization: 'Bearer ' + token }
                });
            } catch (_) { }
        }
    } finally {
        clearSessionState();
        closeLogoutModal();
        window.history.pushState({}, '', '/login');
        authMode = 'login';
        renderAuth();
    }
}
async function readApiError(response) {
    // Render may answer with HTML (proxy/timeout page) instead of JSON, so the
    // status has to survive even when the body cannot be parsed.
    let detail = '';
    try {
        const text = await response.text();
        if (text) {
            try { detail = (JSON.parse(text).detail) || ''; } catch (_) { detail = text.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 200); }
        }
    } catch (_) { }
    return detail;
}
async function api(path, opt = {}) {
    const h = { 'Content-Type': 'application/json', ...(opt.headers || {}) };
    if (token) h.Authorization = 'Bearer ' + token;
    const url = API + path;
    let r;
    try {
        r = await fetch(url, { ...opt, headers: h });
    } catch (networkError) {
        // Only a transport failure (offline, DNS, blocked by CORS, wrong host)
        // reaches this branch. HTTP error statuses are reported with their own
        // message below, so a backend bug is never mislabelled as "cannot reach".
        // Never fall back to window.location.origin: every production request has
        // to go to the single configured API base.
        const target = API_URL || 'the configured VITE_API_URL (not set)';
        throw Error(`Cannot reach the PharmaAI API at ${target}. Check your connection, the VITE_API_URL build variable and the Render CLIENT_URL / CORS settings. (${networkError.message})`);
    }
    if (!r.ok) {
        const detail = await readApiError(r);
        if (r.status === 401 && path !== '/auth/login') { handleUnauthorized(detail || 'Your session has expired. Please sign in again.'); }
        throw Error(detail || `API request ${path} failed (HTTP ${r.status} ${r.statusText})`);
    }
    let payload;
    try { payload = await r.json(); } catch (_) { throw Error(`API request ${path} returned a non-JSON response (HTTP ${r.status}).`); }
    return payload;
}
function render() {
    const path = window.location.pathname || '/';
    const protectedPaths = ['/dashboard', '/pharma', '/doctor', '/sales', '/owner'];
    if (protectedPaths.includes(path)) {
        if (!token || !me) {
            closeLogoutModal();
            closeSessionExpiredModal();
            authMode = 'login';
            window.history.pushState({}, '', '/login');
            toast('Your session has ended. Please sign in again.');
            renderAuth();
            return;
        }
        page = 'dashboard';
        renderShell();
        return;
    }
    if (!token || !me) {
        if (path !== '/login' && path !== '/') {
            window.history.pushState({}, '', '/login');
        }
        authMode = 'login';
        renderAuth();
        return;
    }
    if (path === '/' || path === '/login') {
        window.history.pushState({}, '', '/dashboard');
    }
    renderShell();
}
function renderAuth() { document.getElementById('root').innerHTML = `<div class="auth"><div class="auth-art">${brand()}<div class="art-copy"><div class="ey">AGENTIC PHARMACEUTICAL PLATFORM</div><h1>One intelligent system for doctors, pharma teams and human sales support.</h1><p>Conversational agents, approved medicine RAG, verified onboarding, specialty matching and real human handoff — in one workspace.</p><div class="agent-chain"><span>Supervisor</span><span>RAG</span><span>Doctor Intelligence</span><span>Sales</span><span>Risk</span><span>Human Handoff</span></div></div></div><div class="auth-card"><div class="login-box"><div class="tabs"><button class="${authMode === 'login' ? 'active' : ''}" onclick="authMode='login';renderAuth()">Sign in</button><button class="${authMode === 'register' ? 'active' : ''}" onclick="authMode='register';renderAuth()">Create account</button></div>${authMode === 'login' ? loginForm() : registerForm()}</div></div></div>` }
function loginForm() { return `<h2>Welcome back</h2><p>Choose your workspace and enter your credentials.</p><form onsubmit="event.preventDefault();login()"><div class="field"><label>Sign in as</label><select id="loginRole"><option value="doctor">Doctor</option><option value="pharma">Pharma Company</option><option value="sales_rep">Sales Representative</option><option value="admin">Platform Owner</option></select></div><div class="field"><label>Email</label><input id="email" type="email" required></div><div class="field"><label>Password</label><input id="password" type="password" required></div><button class="primary full">Enter workspace</button></form>` }
function registerForm() { return `<h2>Create an account</h2><p>Only doctors and pharmaceutical companies can self-register. Every account is verified before normal access.</p><form onsubmit="event.preventDefault();register()"><div class="field"><label>Account type</label><select id="rrole" onchange="toggleReg()"><option value="doctor">Doctor</option><option value="pharma">Pharma Company</option></select></div><div class="field"><label>Full name / authorized contact</label><input id="rname" required></div><div class="field"><label>Email</label><input id="remail" type="email" required></div><div class="field"><label>Password</label><input id="rpass" type="password" minlength="6" required></div><div class="field" id="specField"><label>Medical specialization</label><input id="rspec" placeholder="e.g. Cardiology" value="Cardiology"></div><div class="field" id="companyField" style="display:none"><label>Company name</label><input id="rcompany" placeholder="e.g. Verdant Therapeutics"></div><div class="grid two mini-form"><div class="field"><label id="regLabel">PM&DC license / registration number</label><input id="rreg" placeholder="DEMO-PMDC-001 for demo"></div><div class="field"><label>Phone</label><input id="rphone" placeholder="+92 ..."></div></div><div class="field"><label>Registration authority</label><input id="rauth" value="PM&DC"></div><div class="field"><label>Address</label><input id="raddress" placeholder="Clinic / company address"></div><button class="primary full">Submit for verification</button></form>` }
function toggleReg() { const p = document.getElementById('rrole').value === 'pharma'; document.getElementById('specField').style.display = p ? 'none' : 'flex'; document.getElementById('companyField').style.display = p ? 'flex' : 'none'; document.getElementById('regLabel').textContent = p ? 'Company registration / license number' : 'PM&DC license / registration number'; document.getElementById('rauth').value = p ? 'Regulator / company registry' : 'PM&DC' }
async function login() {
    try {
        const selectedRole = document.getElementById('loginRole')?.value || 'doctor';
        const x = await api('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email: email.value, password: password.value, role: selectedRole })
        });
        if (x.pending) { toast('Account is awaiting owner verification.'); return }
        token = x.token; me = x.user; role = me.role; localStorage.setItem('pharmaai_token', token); localStorage.setItem('pharmaai_user', JSON.stringify(me)); window.history.pushState({}, '', '/dashboard'); render()
    } catch (e) { toast(e.message) }
}
async function register() { try { const rr = rrole.value; const x = await api('/auth/register', { method: 'POST', body: JSON.stringify({ name: rname.value, email: remail.value, password: rpass.value, role: rr, specialization: rspec?.value || '', company: rcompany?.value || '', license_number: rr === 'doctor' ? rreg.value : '', registration_number: rr === 'pharma' ? rreg.value : '', registration_authority: rauth.value, phone: rphone.value, address: raddress.value }) }); if (x.pending) { toast('Account created — waiting for owner verification.'); authMode = 'login'; renderAuth(); return } token = x.token; me = x.user; role = me.role; localStorage.setItem('pharmaai_token', token); localStorage.setItem('pharmaai_user', JSON.stringify(me)); window.history.pushState({}, '', '/dashboard'); render() } catch (e) { toast(e.message) } }
function renderShell() { const nav = navs[role] || navs.doctor; const userName = me?.name || 'User'; const roleName = roleLabel(role); document.getElementById('root').innerHTML = `<div class="shell"><aside class="side"><div class="sidebar-header">${brand()}<div class="role-badge">${roleBadgeText(role)}</div></div><nav class="nav">${nav.map(n => `<button data-page="${n[0]}" class="${page === n[0] ? 'active' : ''}" onclick="go('${n[0]}')"><b>${n[1]}</b>${n[2]}</button>`).join('')}</nav><div class="side-bottom"><button class="logout-button" type="button" onclick="showLogoutModal()">↪ <span>Sign Out</span></button></div></aside><main class="main"><header class="top"><div class="top-brand"><img class="top-logo" src="/static/logo.png" alt="PharmaAI"><div><div class="ey">${role === 'admin' ? 'PLATFORM OWNER' : role === 'pharma' ? 'PHARMA COMPANY' : role === 'sales_rep' ? 'SALES REPRESENTATIVE' : 'DOCTOR PORTAL'}</div><h1 id="title">PharmaAI</h1></div></div><div class="top-right"><button class="icon" aria-label="Notifications" aria-expanded="false" onclick="toggleNotifications(event)">◔</button><div class="user-pill">${esc(userName)} · ${esc(roleName)}</div></div></header><section class="page" id="page"></section></main></div>`; loadPage() }
function updateNav() { document.querySelectorAll('.nav button[data-page]').forEach(button => button.classList.toggle('active', button.dataset.page === page)) }
function go(p) { if (!navs[role]?.some(n => n[0] === p)) return; page = p; const routeMap = { dashboard: '/dashboard', medicines: '/medicines', knowledge: '/knowledge', doctors: '/doctors', reps: '/reps', agent: '/agent', human: '/human', orders: '/orders', tickets: '/tickets', profile: '/profile', users: '/users' }; if (routeMap[p]) window.history.pushState({}, '', routeMap[p]); updateNav(); loadPage() }
function title() { return { dashboard: role === 'admin' ? 'Owner Command Center' : role === 'pharma' ? 'Command Center' : role === 'sales_rep' ? 'Sales Workspace' : 'My Practice Dashboard', medicines: role === 'doctor' ? 'Medicine Hub' : 'Medicine Library', knowledge: 'Knowledge Center', doctors: 'Doctor Intelligence', reps: 'Sales Representatives', agent: role === 'doctor' ? 'AI Medical Assistant' : role === 'admin' ? 'Owner AI Agent' : 'AI Sales Agent', human: role === 'doctor' ? 'Company Chats' : 'Doctor Chats', orders: role === 'doctor' ? 'My Requests' : 'Orders', tickets: role === 'doctor' ? 'Human Support' : 'Escalations', profile: 'My Profile', users: 'Verification & Users' }[page] || 'PharmaAI' }
async function loadPage() { clearInterval(humanRefreshTimer); humanRefreshTimer = null; const request = ++navigationRequest, targetPage = page; document.getElementById('title').textContent = title(); updateNav(); const el = document.getElementById('page'); el.innerHTML = '<div class="empty">Loading workspace…</div>'; try { if (targetPage === 'dashboard') await dashboard(el); else if (targetPage === 'medicines') await medicines(el); else if (targetPage === 'knowledge') await knowledge(el); else if (targetPage === 'doctors') await doctors(el); else if (targetPage === 'reps') await reps(el); else if (targetPage === 'agent') agent(el); else if (targetPage === 'human') await human(el); else if (targetPage === 'orders') await orders(el); else if (targetPage === 'tickets') await tickets(el); else if (targetPage === 'profile') await profile(el); else if (targetPage === 'users') await adminUsers(el); if (request !== navigationRequest) { loadPage(); return } normalizeCurrencyDisplay(); } catch (e) { if (request === navigationRequest) el.innerHTML = `<div class="card empty">${esc(e.message)}</div>` } }
function hero(ey, h, p, a = '') { return `<div class="hero"><div><div class="ey">${ey}</div><h2>${h}</h2><p>${p}</p></div>${a}</div>` }
async function dashboard(el) { const d = await api(role === 'admin' ? '/admin/overview' : '/dashboard'); if (role === 'admin') { el.innerHTML = hero('OWNER ONLY', 'PharmaAI Platform Command Center', 'The owner sees the entire network: doctors, pharmaceutical companies, representatives, verification, RAG documents and human conversations.', '<span class="tag">PRIVATE ADMIN</span>') + `<div class="grid kpis"><div class="card kpi"><span class="label">DOCTORS</span><h3>${d.doctors}</h3><span class="up">Registered accounts</span></div><div class="card kpi"><span class="label">PHARMA COMPANIES</span><h3>${d.pharma}</h3><span class="up">Verified + pending</span></div><div class="card kpi"><span class="label">SALES REPS</span><h3>${d.reps}</h3><span class="up">Company-managed users</span></div><div class="card kpi"><span class="label">PENDING VERIFICATION</span><h3>${d.pending}</h3><span class="up">Owner review queue</span></div></div><div class="grid two"><div class="card"><div class="head"><h3>Platform knowledge</h3></div><div class="match"><div><b>${d.medicines} medicines</b><span>Across all companies</span></div><span class="tag">CATALOG</span></div><div class="match"><div><b>${d.documents} documents</b><span>RAG knowledge sources</span></div><span class="tag">RAG</span></div></div><div class="card"><div class="head"><h3>Human support network</h3></div><div class="match"><div><b>${d.human_chats} human chats</b><span>Doctor ↔ representative</span></div><span class="tag">LIVE</span></div><div class="match"><div><b>${d.open_tickets} open escalations</b><span>Safety and expert review</span></div><span class="tag">SAFETY</span></div></div></div>`; return } el.innerHTML = hero(role === 'pharma' ? 'TODAY · LIVE' : role === 'sales_rep' ? 'SALES OPERATIONS' : 'YOUR PRACTICE', role === 'pharma' ? `Good afternoon, ${esc(me.company)}.` : role === 'sales_rep' ? `Good afternoon, ${esc(me.name)}.` : `Good afternoon, ${esc(me.name)}.`, `Your agent workforce is connected to approved knowledge, doctor intelligence and human support.`, '<span class="tag">● SYSTEM LIVE</span>') + `<div class="grid kpis"><div class="card kpi"><span class="label">${role === 'doctor' ? 'PRODUCT REQUESTS' : 'PRODUCT SALES'}</span><h3>${role === 'doctor' ? '$' + Number(d.sales).toLocaleString() : '$' + (Number(d.sales) / 1000).toFixed(1) + 'K'}</h3><span class="up">Live database</span></div><div class="card kpi"><span class="label">ACTIVE DOCTORS</span><h3>${d.doctors || 0}</h3><span class="up">Verified network</span></div><div class="card kpi"><span class="label">${role === 'doctor' ? 'MATCHED PRODUCTS' : 'MEDICINES'}</span><h3>${role === 'doctor' ? d.matched.length : d.medicines}</h3><span class="up">AI matching active</span></div><div class="card kpi"><span class="label">${role === 'doctor' ? 'EST. EARNINGS' : 'SALES REPS'}</span><h3>${role === 'doctor' ? '$' + Number(d.earnings).toFixed(0) : d.reps}</h3><span class="up">Human + AI workflows</span></div></div>` + (role === 'doctor' ? `<div class="card"><div class="head"><h3>Medicines matched to your specialty</h3><button class="link" onclick="go('medicines')">Open Medicine Hub →</button></div>${d.matched.length ? d.matched.map(m => medicineMini(m)).join('') : '<div class="empty">No exact specialty matches yet.</div>'}</div>` : `<div class="grid two"><div class="card"><div class="head"><h3>Product performance</h3><button class="link" onclick="go('medicines')">Manage →</button></div>${(d.top || []).map((m, i) => `<div class="bar-row"><span>${esc(m.name)}</span><div class="bar"><i style="width:${Math.max(18, 100 - i * 22)}%"></i></div><b>$${Number(m.sales).toLocaleString()}</b></div>`).join('')}</div><div class="card"><div class="head"><h3>Agent workforce</h3></div>${['Supervisor Agent', 'Product Knowledge + RAG', 'Doctor Intelligence', 'Sales Agent', 'Risk & Escalation Agent', 'Human Handoff'].map(x => `<div class="match"><div><b>${x}</b><span>Operational</span></div><span class="tag">ACTIVE</span></div>`).join('')}</div></div>`) }
function medicineMini(m) { return `<div class="match"><div><b>${esc(m.name)}</b><span>${esc(m.company)} · ${esc(m.category)}</span></div><div class="match-actions"><span class="pill">${esc(formatPrice(m.price))}</span><button class="secondary" onclick="contactRep(${m.id})">Talk to representative</button></div></div>` }
async function medicines(el) { const ms = await api('/medicines'); el.innerHTML = hero(role === 'doctor' ? 'APPROVED PRODUCT HUB' : 'PRODUCT CATALOG', role === 'doctor' ? 'Medicines for your practice' : role === 'sales_rep' ? 'My Company Products' : 'Medicine Library', role === 'doctor' ? 'Browse approved product information, see specialty matches and open a human sales conversation.' : 'Manage your product catalog. Approved documents are connected through the Knowledge Center.', role === 'pharma' ? '<button class="primary" onclick="addMedicineModal()">+ Add medicine</button>' : '') + `<div class="medicine-grid">${ms.map(m => `<div class="card med-card"><div class="med-top"><span class="pill">${esc(m.category)}</span><span class="stock">${m.stock} in stock</span></div><div class="med-title-row"><h3>${esc(m.name)}</h3>${role === 'pharma' ? `<div class="med-action-row"><button class="secondary small" onclick="editMedicine(${m.id})">Edit</button><button class="delete-icon" aria-label="Delete ${esc(m.name)}" onclick="confirmDelete('medicine',${m.id},'${esc(m.name)}')"></button></div>` : ''}</div><p>${esc(m.description || 'No product description added yet.')}</p><div class="specs">${(m.specializations || []).map(s => `<span>${esc(s)}</span>`).join('')}</div><div class="med-foot"><strong>${esc(formatPrice(m.price))}</strong>${role === 'doctor' ? `<div><button class="secondary" onclick="askMedicine('${esc(m.name)}')">Ask AI</button><button class="secondary" onclick="openOrderMedicineModal(${m.id})">Order Medicine</button><button class="primary" onclick="contactRep(${m.id})">Human rep</button></div>` : role === 'pharma' ? `<button class="secondary" onclick="startChat('Tell me about ${esc(m.name)} and its knowledge base')">Ask agent</button>` : ''}</div></div>`).join('')}</div>` }
function addMedicineModal(medicine = null) { const existing = document.getElementById('medicineModal'); if (existing) existing.remove(); const current = medicine || {}; const isEdit = Boolean(current.id); const fields = { name: current.name || '', category: current.category || 'General', price: current.price ?? 0, generic_name: current.generic_name || '', brand_name: current.brand_name || '', therapeutic_area: current.therapeutic_area || '', dosage_form: current.dosage_form || 'Tablet', strength: current.strength || '', manufacturer: current.manufacturer || me.company || '', pack_size: current.pack_size || '', stock: current.stock ?? 0, availability_status: current.availability_status || 'In Stock', description: current.description || '', composition: current.composition || '', indications: current.indications || '', contraindications: current.contraindications || '', warnings: current.warnings || '', storage_information: current.storage_information || '', prescription_status: current.prescription_status || 'Prescription Required' }; document.body.insertAdjacentHTML('beforeend', `<div class="modal-backdrop" id="medicineModal" role="presentation" onclick="if(event.target===this)closeMedicineModal()"><div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="medicineModalTitle"><div class="modal-head"><div><div class="ey">PRODUCT CATALOG</div><h2 id="medicineModalTitle">${isEdit ? 'Edit Medicine' : 'Add Medicine'}</h2><p>${isEdit ? 'Update your medicine record and keep the company ownership locked to your pharma account.' : 'Add approved product details to your company medicine library.'}</p></div><button class="modal-close" type="button" aria-label="Close" onclick="closeMedicineModal()">×</button></div><form data-medicine-id="${isEdit ? current.id : ''}" onsubmit="submitMedicine(event)"><div class="rep-form-grid"><div class="field"><label for="medicineName">Medicine Name <span aria-hidden="true">*</span></label><input id="medicineName" name="name" value="${esc(fields.name)}" required></div><div class="field"><label for="medicineGeneric">Generic Name / Active Ingredient</label><input id="medicineGeneric" name="generic_name" value="${esc(fields.generic_name)}"></div><div class="field"><label for="medicineBrand">Brand Name</label><input id="medicineBrand" name="brand_name" value="${esc(fields.brand_name)}"></div><div class="field"><label for="medicineCategory">Category <span aria-hidden="true">*</span></label><input id="medicineCategory" name="category" value="${esc(fields.category)}" required></div><div class="field"><label for="medicineTherapeutic">Therapeutic Area</label><input id="medicineTherapeutic" name="therapeutic_area" value="${esc(fields.therapeutic_area)}"></div><div class="field"><label for="medicineForm">Dosage Form</label><input id="medicineForm" name="dosage_form" value="${esc(fields.dosage_form)}"></div><div class="field"><label for="medicineStrength">Strength</label><input id="medicineStrength" name="strength" value="${esc(fields.strength)}"></div><div class="field"><label for="medicineManufacturer">Manufacturer / Pharma Company <span aria-hidden="true">*</span></label><input id="medicineManufacturer" name="manufacturer" value="${esc(fields.manufacturer)}" required></div><div class="field"><label for="medicinePrice">Price <span aria-hidden="true">*</span></label><input id="medicinePrice" name="price" type="number" min="0" step="0.01" value="${Number(fields.price || 0).toFixed(2)}" required></div><div class="field"><label for="medicineCurrency">Currency</label><input id="medicineCurrency" name="currency" value="PKR" readonly></div><div class="field"><label for="medicinePack">Pack Size</label><input id="medicinePack" name="pack_size" value="${esc(fields.pack_size)}"></div><div class="field"><label for="medicineStock">Stock Quantity</label><input id="medicineStock" name="stock" type="number" min="0" value="${Number(fields.stock || 0)}"></div><div class="field"><label for="medicineAvailability">Availability Status</label><select id="medicineAvailability" name="availability_status"><option value="In Stock" ${fields.availability_status === 'In Stock' ? 'selected' : ''}>In Stock</option><option value="Low Stock" ${fields.availability_status === 'Low Stock' ? 'selected' : ''}>Low Stock</option><option value="Out of Stock" ${fields.availability_status === 'Out of Stock' ? 'selected' : ''}>Out of Stock</option></select></div><div class="field" style="grid-column:1 / -1"><label for="medicineDescription">Description</label><textarea id="medicineDescription" name="description" rows="3">${esc(fields.description)}</textarea></div><div class="field" style="grid-column:1 / -1"><label for="medicineComposition">Composition / Ingredients</label><textarea id="medicineComposition" name="composition" rows="2">${esc(fields.composition)}</textarea></div><div class="field" style="grid-column:1 / -1"><label for="medicineIndications">Indications</label><textarea id="medicineIndications" name="indications" rows="2">${esc(fields.indications)}</textarea></div><div class="field" style="grid-column:1 / -1"><label for="medicineContra">Contraindications</label><textarea id="medicineContra" name="contraindications" rows="2">${esc(fields.contraindications)}</textarea></div><div class="field" style="grid-column:1 / -1"><label for="medicineWarnings">Warnings</label><textarea id="medicineWarnings" name="warnings" rows="2">${esc(fields.warnings)}</textarea></div><div class="field" style="grid-column:1 / -1"><label for="medicineStorage">Storage Information</label><textarea id="medicineStorage" name="storage_information" rows="2">${esc(fields.storage_information)}</textarea></div></div><div class="modal-actions"><button class="secondary" type="button" onclick="closeMedicineModal()">Cancel</button><button class="primary" type="submit">${isEdit ? 'Update Medicine' : 'Add Medicine'}</button></div></form></div></div>`); document.getElementById('medicineName').focus() }
function closeMedicineModal() { document.getElementById('medicineModal')?.remove() }
async function submitMedicine(event) { event.preventDefault(); const form = event.currentTarget; const submit = form.querySelector('button[type="submit"]'); submit.disabled = true; const payload = { name: form.elements.name.value.trim(), category: form.elements.category.value.trim(), price: Number(form.elements.price.value), currency: 'PKR', generic_name: form.elements.generic_name.value.trim(), brand_name: form.elements.brand_name.value.trim(), therapeutic_area: form.elements.therapeutic_area.value.trim(), dosage_form: form.elements.dosage_form.value.trim(), strength: form.elements.strength.value.trim(), manufacturer: form.elements.manufacturer.value.trim(), pack_size: form.elements.pack_size.value.trim(), stock: Number(form.elements.stock.value || 0), availability_status: form.elements.availability_status.value, description: form.elements.description.value.trim(), composition: form.elements.composition.value.trim(), indications: form.elements.indications.value.trim(), contraindications: form.elements.contraindications.value.trim(), warnings: form.elements.warnings.value.trim(), storage_information: form.elements.storage_information.value.trim(), prescription_status: 'Prescription Required', status: 'Active' }; if (!payload.name) throw Error('Medicine name is required'); if (!payload.category) throw Error('Category is required'); if (!payload.manufacturer) throw Error('Manufacturer / pharma company is required'); if (!Number.isFinite(payload.price) || payload.price < 0) throw Error('Price must be a valid number and cannot be negative'); if (payload.currency !== 'PKR') payload.currency = 'PKR'; try { const medicineId = form.dataset.medicineId; if (medicineId) { await api('/medicines/' + medicineId, { method: 'PATCH', body: JSON.stringify(payload) }); toast('Medicine updated'); } else { await api('/medicines', { method: 'POST', body: JSON.stringify(payload) }); toast('Medicine created'); } closeMedicineModal(); loadPage(); } catch (e) { toast(e.message); submit.disabled = false } }
async function editMedicine(mid) { const medicine = await api('/medicines/' + mid); addMedicineModal(medicine) }
async function knowledge(el) { const x = await api('/rag/status'), ms = await api('/medicines'); el.innerHTML = hero('COMPANY KNOWLEDGE BASE', 'Knowledge Center', 'This is where the pharma company teaches its agent. Upload approved product/company documents and they become searchable RAG sources.', '<span class="tag">' + x.total_chunks + ' CHUNKS</span>') + `<div class="grid two"><div class="card"><div class="head"><div><h3>Company-wide knowledge</h3><span>Policies, approved sales guidance, company information</span></div></div><div class="upload-zone"><input id="companyFile" type="file" accept=".pdf,.docx,.txt,.md"><button class="primary" onclick="uploadCompanyDoc()">Upload + index</button></div></div><div class="card"><div class="head"><div><h3>Medicine knowledge</h3><span>Product profiles, approved information, safety documents</span></div></div><div class="field"><label>Medicine</label><select id="knowledgeMedicine">${ms.map(m => `<option value="${m.id}">${esc(m.name)}</option>`).join('')}</select></div><div class="upload-zone"><input id="productFile" type="file" accept=".pdf,.docx,.txt,.md"><button class="primary" onclick="uploadProductDoc()">Upload + RAG index</button></div></div></div><div class="card table-card"><div class="head"><div><h3>Indexed knowledge</h3><span>Only your company scope is visible here</span></div><button class="secondary" onclick="loadPage()">Refresh</button></div>${x.documents.length ? x.documents.map(d => `<div class="match"><div><b>${esc(d.filename)}</b><span>${esc(d.medicine || 'Company-wide')} · ${d.document_type} · ${d.chunk_count} chunks</span></div><span class="pill">${esc(d.status)}</span></div>`).join('') : '<div class="empty">Upload your first approved document.</div>'}</div>` }
async function uploadCompanyDoc() { const f = document.getElementById('companyFile')?.files?.[0]; if (!f) return toast('Choose a document'); uploadFile('/company-documents', f) }
async function uploadProductDoc() { const id = document.getElementById('knowledgeMedicine')?.value, f = document.getElementById('productFile')?.files?.[0]; if (!id || !f) return toast('Choose medicine and document'); uploadFile('/documents/' + id, f) }
async function uploadFile(path, f) { const fd = new FormData(); fd.append('file', f); try { const r = await fetch(API + path, { method: 'POST', headers: { Authorization: 'Bearer ' + token }, body: fd }); const detail = r.ok ? '' : await readApiError(r); if (!r.ok) throw Error(detail || `Upload failed (HTTP ${r.status})`); const x = await r.json(); toast(`Indexed ${x.chunks} chunks`); loadPage() } catch (e) { toast(e.message) } }
async function doctors(el) { const ds = await api('/doctors'); el.innerHTML = hero('DOCTOR INTELLIGENCE', 'Registered Doctor Network', 'Every verified doctor is visible to the pharmaceutical workspace. Matching is a separate intelligence layer based on specialty/product alignment.', '<span class="tag">' + ds.length + ' VERIFIED DOCTORS</span>') + `<div class="card table-card"><div class="head"><h3>All doctors</h3><span class="tag">LIVE DIRECTORY</span></div><div class="table-wrap"><table><thead><tr><th>Doctor</th><th>Specialty</th><th>Matches</th><th>Verification</th><th>Action</th></tr></thead><tbody>${ds.map(d => `<tr><td><div class="person"><div class="avatar">${initials(d.name)}</div><div><b>${esc(d.name)}</b><span>${esc(d.email)}</span></div></div></td><td>${esc(d.specialization)}</td><td>${d.matches.length ? d.matches.map(x => `<span class="pill">${esc(x)}</span>`).join(' ') : '—'}</td><td><span class="tag">VERIFIED</span></td><td><button class="link" onclick="startChat('Tell me about ${esc(d.name)} and their matches')">Ask agent →</button></td></tr>`).join('')}</tbody></table></div></div>` }
async function reps(el) { const rs = (await api('/reps')).filter(r => !hiddenRepIds.includes(r.id)); el.innerHTML = hero('HUMAN SALES WORKFORCE', 'Sales Representatives', 'Create and manage the real people who receive doctor handoffs. Every human conversation remains visible to the pharmaceutical company.', '<button class="primary" onclick="addRepModal()">+ Add representative</button>') + `<div class="card table-card"><div class="head"><h3>Your sales representatives</h3><span class="tag">${rs.length} PEOPLE</span></div><div class="table-wrap"><table><thead><tr><th>Representative</th><th>Role</th><th>Contact</th><th>Unique Sales ID</th><th>Status</th><th>Action</th></tr></thead><tbody>${rs.map(r => `<tr><td><div class="person"><div class="avatar">${initials(r.name)}</div><div><b>${esc(r.name)}</b><span>${esc(r.email)}</span></div></div></td><td>${esc(r.job_title)}</td><td>${esc(r.phone || '—')}</td><td>${esc(r.sales_id || r.registration_number || '—')}</td><td><span class="tag">${esc(r.verification_status)}</span></td><td><button class="delete-icon" aria-label="Delete ${esc(r.name)}" onclick="confirmDelete('rep',${r.id},'${esc(r.name)}')"></button></td></tr>`).join('')}</tbody></table></div></div>` }
function confirmDelete(type, id, name) { const existing = document.getElementById('deleteConfirmModal'); if (existing) existing.remove(); const label = type === 'medicine' ? 'medicine' : 'sales representative'; document.body.insertAdjacentHTML('beforeend', `<div class="modal-backdrop" id="deleteConfirmModal" role="presentation" onclick="if(event.target===this)closeDeleteConfirm()"><div class="confirm-card" role="dialog" aria-modal="true" aria-labelledby="deleteConfirmTitle"><div class="confirm-icon">!</div><div class="confirm-copy"><h2 id="deleteConfirmTitle">Delete ${label}?</h2><p>Are you sure you want to delete this?</p><span>${esc(name)}</span></div><div class="modal-actions"><button class="secondary" type="button" onclick="closeDeleteConfirm()">Cancel</button><button class="primary danger-button" type="button" onclick="deleteItem('${type}',${id})">Delete</button></div></div></div>`); document.querySelector('#deleteConfirmModal .danger-button').focus() }
function closeDeleteConfirm() { document.getElementById('deleteConfirmModal')?.remove() }
async function deleteItem(type, id) { const button = document.querySelector('#deleteConfirmModal .danger-button'); if (button) button.disabled = true; try { if (type === 'medicine') { await api('/medicines/' + id, { method: 'DELETE' }) } else { hiddenRepIds.push(id) } closeDeleteConfirm(); toast(type === 'medicine' ? 'Medicine deleted' : 'Sales representative removed'); loadPage() } catch (e) { toast(e.message); if (button) button.disabled = false } }
function agent(el) { const label = role === 'doctor' ? 'Medical Assistant' : role === 'admin' ? 'Owner AI Agent' : 'Sales Agent'; el.innerHTML = hero('CONVERSATIONAL MULTI-AGENT', `AI ${label}`, 'Talk normally. The supervisor decides whether your request needs RAG, structured company data, doctor intelligence, sales tools, safety review or human handoff.', '<span class="tag">● AGENTS ONLINE</span>') + `<div class="grid agent-layout"><div class="card chat"><div class="agent-head"><div class="agent-id"><div class="orb">✦</div><div><b>PharmaAI Supervisor</b><span>Natural conversation · tool routing · RAG</span></div></div><span class="online">● ONLINE</span></div><div class="chatbody" id="chatbody"><div class="msg ai">${role === 'pharma' ? `Hello ${esc(me.name)}! I’m your PharmaAI company agent. Ask me anything about your company workflow, doctors, medicines, RAG or sales team.` : role === 'sales_rep' ? `Hello ${esc(me.name)}! I’m your sales workspace agent. I can help with products, doctors, approved information and human conversations.` : role === 'admin' ? `Hello Owner. I can summarize the platform, verification queue, doctors, companies, representatives and human-support network.` : `Hello ${esc(me.name)}! I’m your PharmaAI doctor assistant. I can answer general questions, search approved medicine knowledge and connect you with a real company representative.`}<small>Supervisor Agent · now</small></div></div><div class="quick-row">${(role === 'pharma' ? ['Hello', 'Show all new doctors', 'Help me upload a medicine', 'Show my sales representatives'] : role === 'doctor' ? ['Hello', 'What medicines match me?', 'Tell me about Cardiovex 10', 'Connect me to a sales representative'] : ['Hello', 'Show my doctors', 'Show company products', 'Show human chats']).map(q => `<button onclick="quickChat('${q.replace(/'/g, "\\'")}')">${q}</button>`).join('')}</div><div class="chatbar"><input id="chatinput" placeholder="Message PharmaAI…" onkeydown="if(event.key==='Enter')sendChat()"><button onclick="sendChat()">↑</button></div></div><div class="agentcards">${['Supervisor Agent', 'Product Knowledge + RAG', 'Doctor Intelligence', 'Sales / Commercial Tools', 'Risk & Escalation', 'Human Handoff'].map((x, i) => `<div class="card agentcard"><div class="agentmini">${['◈', '✚', '◉', '↗', '!', '◌'][i]}</div><div><b>${x}</b><span>${['Intent routing', 'Grounded medicine knowledge', 'Specialty matching', 'Structured facts', 'Safety gate', 'Real person chat'][i]}</span></div></div>`).join('')}</div></div>` }
function quickChat(q) { document.getElementById('chatinput').value = q; sendChat() }
function startChat(q) { go('agent'); setTimeout(() => quickChat(q), 250) }
async function sendChat() {
    const input = document.getElementById('chatinput'), body = document.getElementById('chatbody'), message = input.value.trim();
    if (!message) return;
    body.innerHTML += `<div class="msg user">${esc(message)}<small>You · now</small></div>`;
    input.value = '';
    body.innerHTML += '<div id="typing" class="msg ai typing">Connecting…<small>Supervisor · routing</small></div>';
    body.scrollTop = body.scrollHeight;
    try {
        if (role === 'doctor' && /\b(connect|talk|speak|contact|human|real person)\b.{0,70}\b(sales representative|sales rep|representative|company|human support|real person)\b/i.test(message)) {
            const handoff = await api('/ai/human-handoff', { method: 'POST', body: JSON.stringify({ message }) });
            document.getElementById('typing')?.remove();
            const choices = handoff.companies.length ? handoff.companies.map(company => `<button class="secondary small" ${company.available_contact ? '' : 'disabled'} onclick="startCompanyConversation(${company.company_id})">${esc(company.company_name || company.company || 'Pharmaceutical company')}${company.available_contact ? '' : ' · unavailable'}</button>`).join('') : '<span>No eligible company representatives are currently available.</span>';
            body.innerHTML += `<div class="msg ai">Choose a pharmaceutical company to start a real human support conversation.<div class="quick-row">${choices}</div><small>Human sales handoff · live company directory</small></div>`;
        } else {
            const x = await api('/chat', { method: 'POST', body: JSON.stringify({ message, conversation_id: currentConversationId }) });
            currentConversationId = x.conversation_id;
            document.getElementById('typing')?.remove();
            const used = (x.tools || []).filter(tool => tool && tool.tool);
            const dbTrace = used.length ? `<div class="sources"><b>Live database</b>${used.map(tool => `<span>${esc(String(tool.tool).replace(/_/g, ' '))}${tool.ok === false ? ' · unavailable' : ''}</span>`).join('')}</div>` : '';
            body.innerHTML += `<div class="msg ai">${formatText(x.message)}<small>${esc(x.agent)} · ${esc(x.provider || 'LLM')} · ${esc(x.risk)}</small>${(x.sources || []).length ? `<div class="sources"><b>RAG sources</b>${x.sources.map(source => `<span>[${source.source_no}] ${esc(source.filename)} · chunk ${source.chunk} · ${Math.round(source.score * 100)}%</span>`).join('')}</div>` : ''}${dbTrace}${x.ticket_no ? `<button class="secondary" onclick="go('tickets')">Open ${esc(x.ticket_no)}</button>` : ''}</div>`;
            if (x.risk === 'critical') toast('Human escalation opened');
        }
    } catch (e) {
        document.getElementById('typing')?.remove();
        toast('Unable to start handoff. Please try again.');
    }
    body.scrollTop = body.scrollHeight;
}
function formatText(s) { return esc(s).replace(/\*\*(.*?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>') }
async function contactRep(mid) { try { const x = await api('/contact-rep/' + mid, { method: 'POST' }); humanConversationId = x.conversation_id; toast(`Connected to ${x.representative.name}`); go('human') } catch (e) { toast(e.message) } }
async function startCompanyConversation(companyId) {
    try {
        const x = await api('/conversations', {
            method: 'POST',
            body: JSON.stringify({ company_id: companyId })
        });
        humanConversationId = x.id || x.conversation_id;
        toast(`Connected · ${x.ticket?.ticket_no || 'support ticket opened'}`);
        go('human');
    } catch (e) {
        toast(e.message.includes('unavailable') ? 'No sales representative is currently available for this company.' : 'Unable to start this conversation. Please try again.');
    }
}
function filterDoctorCompanies() {
    const query = document.getElementById('companySearch')?.value.trim().toLowerCase() || '';
    document.querySelectorAll('#humanCompanyResults [data-company-name]').forEach(card => {
        card.hidden = !card.dataset.companyName.includes(query);
    });
}
async function openTicketConversation(conversationId) {
    if (!conversationId) return;
    humanConversationId = conversationId;
    go('human');
}
async function updateHumanTicket(ticketId, status) {
    try {
        await api('/tickets/' + ticketId, { method: 'PATCH', body: JSON.stringify({ status }) });
        toast('Support ticket updated');
        if (page === 'human' && humanConversationId) await openHuman(humanConversationId);
        else loadPage();
    } catch (e) {
        toast(e.message);
    }
}
async function human(el) {
    if (role === 'doctor') {
        const [companyResult, chatResult] = await Promise.allSettled([
            api('/doctor/pharma-companies'),
            api('/human-conversations')
        ]);
        const companies = companyResult.status === 'fulfilled' ? companyResult.value : [];
        const chats = chatResult.status === 'fulfilled' ? chatResult.value : [];
        const chatList = chats.length ? chats.map(c => `<button class="chat-item ${humanConversationId === c.id ? 'active' : ''}" onclick="openHuman(${c.id})"><b>${esc(c.company || 'Pharmaceutical company')}</b><span>${esc(c.medicine || 'Company conversation')}</span><small>${esc(c.representative || 'Sales representative')} · ${esc(c.ticket_no || 'Ticket pending')} · ${esc(c.ticket_status || c.status || 'Open')}</small></button>`).join('') : '<div class="empty">No conversations yet. Choose a pharmaceutical company below to start human support.</div>';
        const companyCards = companies.length ? companies.map(company => {
            const companyName = company.company_name || company.company || 'Pharma company';
            const approved = ['approved', 'verified'].includes(String(company.verification_status || '').toLowerCase());
            return `<div class="company-option" data-company-name="${esc(companyName.toLowerCase())}" style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px;margin-bottom:9px;border:1px solid var(--line);border-radius:10px;background:#fff"><div><b>${esc(companyName)}</b><span style="display:block;margin-top:5px;color:var(--forest);font-size:10px;font-weight:700">${approved ? '✓ Verified' : 'Demo account'}</span><small style="display:block;margin-top:4px;color:var(--muted)">${company.available_contact ? 'Sales support available' : 'No sales representative currently available'}</small><small style="display:block;margin-top:3px;color:var(--muted)">${company.products_count ?? 0} products</small></div><button class="primary small" type="button" ${company.available_contact ? '' : 'disabled'} onclick="startCompanyConversation(${company.company_id})">Chat</button></div>`;
        }).join('') : companyResult.status === 'rejected' ? '<div class="empty">Unable to load pharmaceutical companies. Please try again.</div>' : '<div class="empty">No verified pharmaceutical companies are available right now.</div>';
        const companyError = companyResult.status === 'rejected' ? '<button class="secondary small" onclick="loadPage()">Retry</button>' : '';
        el.innerHTML = hero('HUMAN COMPANY SUPPORT', 'Talk to a real sales representative', 'Choose an approved pharmaceutical company to open a secure human conversation with its sales team.', '<span class="tag">' + companies.length + ' COMPANIES</span>') + `<div class="human-layout"><div class="card chat-list"><div class="head"><h3>My company conversations</h3><span class="tag">${chats.length} chats</span></div>${chatResult.status === 'rejected' ? '<div class="empty">Unable to load conversations. Please try again.</div>' : chatList}<div class="head company-list-head"><h3>Pharmaceutical companies</h3>${companyError}</div><div class="field company-search"><input id="companySearch" type="search" placeholder="Search companies..." oninput="filterDoctorCompanies()" aria-label="Search pharmaceutical companies"></div><div id="humanCompanyResults">${companyCards}</div></div><div class="card chat" id="humanPanel"><div class="empty">Select a company or conversation to open human support.</div></div></div>`;
        if (humanConversationId) openHuman(humanConversationId);
        return;
    }
    const cs = await api('/human-conversations');
    const list = cs.length ? cs.map(c => `<button class="chat-item ${humanConversationId === c.id ? 'active' : ''}" data-conversation-id="${c.id}" onclick="openHuman(${c.id})"><b>${esc(c.company || c.doctor || 'Company')}</b><span>${esc(c.medicine || 'Company conversation')}</span><small>${esc(c.representative || 'Sales representative')} · ${esc(c.ticket_no || 'Ticket pending')} · ${esc(c.ticket_status || 'Open')}</small></button>`).join('') : '<div class="empty">No human conversations yet.</div>';
    el.innerHTML = hero('DOCTOR CONVERSATIONS', 'Human sales support', 'Private human-to-human conversations with company sales representatives.', '<span class="tag">' + cs.length + ' CHATS</span>') + `<div class="human-layout"><div class="card chat-list"><div class="head"><h3>${role === 'pharma' ? 'Incoming support' : 'My support conversations'}</h3><span class="tag">${cs.length}</span></div>${list}</div><div class="card chat" id="humanPanel"><div class="empty">Select a conversation to open the secure human chat.</div></div></div>`;
    if (humanConversationId) openHuman(humanConversationId);
}
function humanMessageMarkup(messages) {
    return messages.map(m => {
        const ownMessage = Number(m.sender_id) === Number(me.id) || (!m.sender_id && m.agent === me.name);
        const sender = m.agent || m.sender || 'Participant';
        return `<div class="msg ${ownMessage ? 'user' : 'ai'}">${formatText(m.content || m.message || '')}<small>${esc(sender)} · ${esc(m.created_at || '')}</small></div>`;
    }).join('');
}
async function openHuman(cid) {
    humanConversationId = cid;
    try {
        const x = await api('/human-conversations/' + cid);
        const p = document.getElementById('humanPanel');
        if (!p) return;
        const c = x.conversation, ticket = x.ticket;
        const status = ticket?.status || 'Open';
        const statusOptions = ['Open', 'In Progress', 'Waiting for Doctor', 'Waiting for Company', 'Resolved', 'Reopened', 'Closed'];
        const statusControl = !ticket ? '' : role === 'doctor'
            ? status === 'Resolved' || status === 'Closed'
                ? `<button class="secondary small" onclick="updateHumanTicket(${ticket.id},'Reopened')">Reopen ticket</button>`
                : `<button class="secondary small" onclick="updateHumanTicket(${ticket.id},'Resolved')">Mark as resolved</button>`
            : `<select aria-label="Update support ticket status" onchange="updateHumanTicket(${ticket.id},this.value)">${statusOptions.map(option => `<option value="${option}" ${option.toLowerCase() === status.toLowerCase() ? 'selected' : ''}>${option}</option>`).join('')}</select>`;
        const timeline = (x.ticket_events || []).map(event => `<span>${esc(event.event_type.replace(/_/g, ' '))}${event.new_status ? ` · ${esc(event.new_status)}` : ''}${event.actor_name ? ` · ${esc(event.actor_name)}` : ''}</span>`).join('');
        p.innerHTML = `<div class="agent-head"><div class="agent-id"><div class="orb">◌</div><div><b>${esc(c.company_name || 'Pharmaceutical company')}</b><span>${esc(c.representative_name || 'Sales representative')} · Sales Representative</span></div></div><span class="online">● HUMAN</span></div><div class="human-ticket-summary" id="humanTicketSummary" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 14px;border-bottom:1px solid var(--line);background:#f8faf5;font-size:11px">${ticket ? `<b>Support Ticket: ${esc(ticket.ticket_no)}</b><span>Status: <strong id="humanTicketStatus">${esc(status)}</strong></span><div class="human-ticket-actions">${statusControl}</div>${timeline ? `<div class="human-ticket-events" style="flex-basis:100%;display:flex;gap:12px;flex-wrap:wrap;color:var(--muted);font-size:10px">${timeline}</div>` : ''}` : '<span>No linked support ticket.</span>'}</div><div class="chatbody" id="humanBody">${humanMessageMarkup(x.messages || [])}</div><div class="chatbar"><input id="humanInput" placeholder="Write a message…" onkeydown="if(event.key==='Enter')sendHuman()"><button aria-label="Send message" onclick="sendHuman()">↑</button></div>`;
        document.getElementById('humanBody').scrollTop = 999999;
        clearInterval(humanRefreshTimer);
        humanRefreshTimer = setInterval(refreshHumanConversation, 5000);
    } catch (e) {
        toast('Unable to load this conversation. Please try again.');
    }
}
async function refreshHumanConversation() {
    if (page !== 'human' || !humanConversationId) return;
    try {
        const [detail, conversations] = await Promise.all([
            api('/human-conversations/' + humanConversationId),
            api('/human-conversations')
        ]);
        const body = document.getElementById('humanBody');
        if (body) body.innerHTML = humanMessageMarkup(detail.messages || []);
        const status = document.getElementById('humanTicketStatus');
        if (status && detail.ticket) status.textContent = detail.ticket.status;
        conversations.forEach(conversation => {
            const entry = document.querySelector(`[data-conversation-id="${conversation.id}"] small`);
            if (entry) entry.textContent = `${conversation.representative || 'Sales representative'} · ${conversation.ticket_no || 'Ticket pending'} · ${conversation.ticket_status || 'Open'}`;
        });
    } catch (_) {
        // Polling is best-effort; the next interval retries without interrupting message entry.
    }
}
async function sendHuman() {
    const input = document.getElementById('humanInput');
    if (!input?.value.trim() || !humanConversationId) return;
    const content = input.value.trim();
    input.disabled = true;
    try {
        await api('/human-conversations/' + humanConversationId + '/messages', { method: 'POST', body: JSON.stringify({ content }) });
        input.value = '';
        await openHuman(humanConversationId);
    } catch (e) {
        toast('Message failed. Please retry.');
    } finally {
        if (document.getElementById('humanInput')) document.getElementById('humanInput').disabled = false;
    }
}
function orderStatusBadge(status) { return `<span class="tag">${esc(status || 'Pending')}</span>` }

async function orders(el) { const os = await api('/orders'); if (role === 'doctor') { el.innerHTML = hero('TRANSACTION WORKFLOW', 'My Orders', 'Track your medicine requests from submission to review, assignment and fulfillment.', '<span class="tag">' + os.length + ' RECORDS</span>') + `<div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Order ID</th><th>Medicine</th><th>Company</th><th>Representative</th><th>Requested Date</th><th>Status</th></tr></thead><tbody>${os.map(o => `<tr><td><button class="link" onclick="openOrderDetails(${o.id})">${esc(o.order_no)}</button></td><td>${esc(o.medicine)}</td><td>${esc(o.company || '—')}</td><td>${esc(o.representative || '—')}</td><td>${esc(o.requested_date || '—')}</td><td>${orderStatusBadge(o.status)}</td></tr>`).join('')}</tbody></table></div></div>`; return; }
    el.innerHTML = hero('TRANSACTION WORKFLOW', 'Orders', 'Product requests are stored against the company product and visible to the correct pharmaceutical workspace.', '<span class="tag">' + os.length + ' RECORDS</span>') + `<div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Order</th><th>Medicine</th><th>Doctor</th><th>Quantity</th><th>Requested</th><th>Representative</th><th>Status</th><th>Action</th></tr></thead><tbody>${os.map(o => `<tr><td><button class="link" onclick="openOrderDetails(${o.id})">${esc(o.order_no)}</button></td><td>${esc(o.medicine)}</td><td>${esc(o.doctor || me.name)}</td><td>${o.quantity}</td><td>${esc(o.requested_date || '—')}</td><td>${esc(o.representative || 'Unassigned')}</td><td>${orderStatusBadge(o.status)}</td><td><button class="secondary small" onclick="openUpdateOrderStatusModal(${o.id})">Update Status</button></td></tr>`).join('')}</tbody></table></div></div>` }
async function tickets(el) {
    const ts = await api('/tickets');
    const statusChoices = ['Open', 'In Progress', 'Waiting for Doctor', 'Waiting for Company', 'Resolved', 'Reopened', 'Closed'];
    el.innerHTML = hero(role === 'doctor' ? 'HUMAN SUPPORT' : 'HUMAN SUPPORT', role === 'sales_rep' ? 'My Support Tickets' : role === 'pharma' ? 'Incoming Human Support' : 'Human Support', 'One ticket record is shared by the doctor, selected company, and assigned representative.', '<span class="tag">' + ts.length + ' CASES</span>') + `<div class="card table-card"><div class="table-wrap"><table><thead><tr><th>Ticket</th><th>Doctor</th><th>Company</th><th>Medicine</th><th>Assigned representative</th><th>Status</th><th>Conversation</th></tr></thead><tbody>${ts.map(t => {
        const humanTicket = Boolean(t.conversation_id);
        const statusCell = humanTicket && role === 'doctor'
            ? `<span class="tag">${esc(t.status)}</span>${t.status === 'Resolved' || t.status === 'Closed' ? `<button class="link" onclick="updateHumanTicket(${t.id},'Reopened')">Reopen</button>` : `<button class="link" onclick="updateHumanTicket(${t.id},'Resolved')">Mark resolved</button>`}`
            : humanTicket
                ? `<select aria-label="Update ${esc(t.ticket_no)} status" onchange="updateHumanTicket(${t.id},this.value)">${statusChoices.map(status => `<option value="${status}" ${status.toLowerCase() === String(t.status).toLowerCase() ? 'selected' : ''}>${status}</option>`).join('')}</select>`
                : role === 'pharma' ? `<select onchange="updateTicket(${t.id},this.value)"><option>${esc(t.status)}</option><option>In Review</option><option>Resolved</option></select>` : `<span class="tag">${esc(t.status)}</span>`;
        const timeline = (t.events || []).map(event => `<div>${esc(event.event_type.replace(/_/g, ' '))}${event.new_status ? ` · ${esc(event.new_status)}` : ''}${event.actor_name ? ` · ${esc(event.actor_name)}` : ''}</div>`).join('');
        return `<tr><td><b>${esc(t.ticket_no)}</b><span style="display:block;color:var(--muted)">${esc(t.subject)}</span>${timeline ? `<details><summary>Timeline</summary>${timeline}</details>` : ''}</td><td>${esc(t.doctor || '—')}</td><td>${esc(t.company || '—')}</td><td>${esc(t.medicine || '—')}</td><td>${esc(t.representative || 'Unassigned')}</td><td>${statusCell}</td><td>${humanTicket ? `<button class="secondary small" onclick="openTicketConversation(${t.conversation_id})">Open chat</button>` : '—'}</td></tr>`;
    }).join('')}</tbody></table></div></div>`;
}
async function updateTicket(id, status) { try { await api('/tickets/' + id, { method: 'PATCH', body: JSON.stringify({ status }) }); toast('Updated') } catch (e) { toast(e.message) } }
async function profile(el) { const p = await api('/profile'); el.innerHTML = hero('IDENTITY + VERIFICATION', 'My Profile', 'Keep your professional identity and verification data current. For Pakistan demo verification, PM&DC is the reference registry; production automation requires an authorized integration.', '<span class="tag">' + esc(p.verification_status || 'pending') + '</span>') + `<div class="grid two"><div class="card"><div class="head"><h3>Identity</h3></div><div class="field"><label>Name</label><input id="pname" value="${esc(p.name)}" disabled></div><div class="field"><label>Email</label><input value="${esc(p.email)}" disabled></div><div class="field"><label>Phone</label><input id="pphone" value="${esc(p.phone || '')}"></div><div class="field"><label>Address</label><input id="paddress" value="${esc(p.address || '')}"></div></div><div class="card"><div class="head"><h3>Professional credentials</h3><span class="pill">${esc(p.verification_status)}</span></div>${p.role === 'doctor' ? `<div class="field"><label>Specialization</label><input id="pspec" value="${esc(p.specialization || '')}"></div><div class="field"><label>PM&DC license number</label><input id="plicense" value="${esc(p.license_number || '')}"></div><div class="field"><label>Authority</label><input id="pauth" value="${esc(p.registration_authority || 'PM&DC')}"></div><div class="note-box">Official registry reference: <a href="${p.verification_url}" target="_blank">PM&DC practitioner register ↗</a><br><small>Our demo uses an owner-verification adapter. Do not claim automatic government verification unless the regulator provides an authorized API/integration.</small></div>` : '<div class="note-box">Company verification credentials are managed by the owner admin. Your company can upload supporting documents through the Knowledge Center.</div>'}<button class="primary" onclick="saveProfile()">Save profile</button></div></div>` }
async function saveProfile() { try { const x = await api('/profile', { method: 'PATCH', body: JSON.stringify({ specialization: document.getElementById('pspec')?.value, phone: document.getElementById('pphone')?.value, address: document.getElementById('paddress')?.value, license_number: document.getElementById('plicense')?.value, registration_authority: document.getElementById('pauth')?.value }) }); me = x; localStorage.setItem('pharmaai_user', JSON.stringify(me)); toast('Profile updated') } catch (e) { toast(e.message) } }
async function adminUsers(el) { const [u, o] = await Promise.all([api('/admin/users'), api('/admin/overview')]); el.innerHTML = hero('OWNER VERIFICATION', 'Verification & Users', 'The platform owner controls access. Doctors and pharma companies self-register; sales representatives are created by their company.', '<span class="tag">' + o.pending + ' PENDING</span>') + `<div class="card table-card"><div class="head"><h3>All platform users</h3><a class="link" href="https://www.pmdc.pk/Home?keyWord=registration" target="_blank">Open PM&DC registry ↗</a></div><div class="table-wrap"><table><thead><tr><th>User</th><th>Role</th><th>Credential</th><th>Status</th><th>Owner action</th></tr></thead><tbody>${u.map(x => `<tr><td><div class="person"><div class="avatar">${initials(x.name)}</div><div><b>${esc(x.name)}</b><span>${esc(x.email)}</span></div></div></td><td>${esc(x.role)}</td><td>${esc(x.license_number || x.registration_number || '—')}<span style="display:block;color:var(--muted)">${esc(x.registration_authority || '')}</span></td><td><span class="tag">${esc(x.verification_status)}</span></td><td>${x.verification_status === 'pending' ? `<button class="primary small" onclick="verifyUser(${x.id},'approved')">Approve</button><button class="secondary small" onclick="verifyUser(${x.id},'rejected')">Reject</button>` : `<button class="link" onclick="verifyUser(${x.id},'pending')">Reopen</button>`}</td></tr>`).join('')}</tbody></table></div></div>` }
async function verifyUser(id, decision) {
    if (decision === 'pending') {
        const nextDecision = 'pending';
        try {
            await api('/admin/users/' + id + '/verification', { method: 'PATCH', body: JSON.stringify({ decision: nextDecision, note: 'Reopened by PharmaAI owner' }) });
            toast('Verification status reopened');
            loadPage();
        } catch (e) { toast(e.message) }
        return;
    }
    const note = decision === 'approved' ? 'Reviewed by PharmaAI owner' : 'Rejected by PharmaAI owner';
    showInputModal({
        id: 'verifyNoteModal',
        title: decision === 'approved' ? 'Approve user' : 'Reject user',
        message: 'Add an optional verification note before saving the status.',
        label: 'Verification note',
        value: note,
        confirmText: decision === 'approved' ? 'Approve user' : 'Reject user',
        onConfirm: async (nextNote) => {
            try {
                await api('/admin/users/' + id + '/verification', { method: 'PATCH', body: JSON.stringify({ decision, note: nextNote || note }) });
                toast('Verification updated');
                loadPage();
            } catch (e) { toast(e.message) }
        }
    });
}
function closeNotifications() { const panel = document.getElementById('notificationPanel'); if (panel) panel.remove(); const bell = document.querySelector('.top-right .icon'); if (bell) bell.setAttribute('aria-expanded', 'false'); document.removeEventListener('click', handleNotificationOutside); document.removeEventListener('keydown', handleNotificationEscape) }
function handleNotificationOutside(event) { const panel = document.getElementById('notificationPanel'); const bell = document.querySelector('.top-right .icon'); if (panel && !panel.contains(event.target) && event.target !== bell) closeNotifications() }
function handleNotificationEscape(event) { if (event.key === 'Escape') closeNotifications() }
function notificationPanel() { return `<div class="notification-panel" id="notificationPanel" role="dialog" aria-label="Notifications"><div class="notification-head"><div><div class="ey">INBOX</div><h2>Notifications</h2></div><button type="button" class="notification-close" aria-label="Close notifications" onclick="closeNotifications()">×</button></div><div class="notification-list">${notificationItems.length ? notificationItems.map((n, i) => `<div class="notification-item"><div class="notification-mark">●</div><div class="notification-copy"><b>${esc(n.title || 'Notification')}</b><p>${esc(n.body || '')}</p>${n.created_at ? `<time>${esc(n.created_at)}</time>` : ''}</div><button type="button" class="notification-delete" aria-label="Delete ${esc(n.title || 'notification')}" onclick="event.stopPropagation();deleteNotification(${i})"></button></div>`).join('') : '<div class="notification-empty"><div class="notification-empty-icon">✓</div><b>No new notifications</b><span>You are all caught up.</span></div>'}</div></div>` }
async function toggleNotifications(event) { event.stopPropagation(); const panel = document.getElementById('notificationPanel'); if (panel) { closeNotifications(); return } try { notificationItems = await api('/notifications'); const bell = event.currentTarget || event.target.closest('.icon'); if (!bell) throw Error('Notification control unavailable'); bell.setAttribute('aria-expanded', 'true'); bell.insertAdjacentHTML('afterend', notificationPanel()); setTimeout(() => { document.addEventListener('click', handleNotificationOutside); document.addEventListener('keydown', handleNotificationEscape) }, 0) } catch (e) { toast(e.message) } }
function deleteNotification(index) { notificationItems.splice(index, 1); const panel = document.getElementById('notificationPanel'); if (panel) panel.outerHTML = notificationPanel() }
function askMedicine(n) { startChat('Tell me about ' + n + ' using the approved medicine knowledge. What is it, what information is available, and what are the relevant sources?') }
async function openOrderMedicineModal(medicineId) {
    try {
        const medicine = await api('/medicines/' + medicineId);
        if (!medicine) return;
        const existing = document.getElementById('orderMedicineModal');
        if (existing) existing.remove();
        const today = new Date();
        const nextDate = new Date(today.getTime() + 86400000).toISOString().split('T')[0];

        document.body.insertAdjacentHTML('beforeend', `
            <div class="modal-backdrop" id="orderMedicineModal" role="presentation" onclick="if(event.target===this)closeOrderMedicineModal()">
              <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="orderMedicineTitle" style="max-width: 760px;">
                <div class="modal-head">
                  <div>
                    <div class="ey">ORDER REQUEST</div>
                    <h2 id="orderMedicineTitle">Order Medicine</h2>
                    <p>Review the medicine, quantity and delivery plan before submitting.</p>
                  </div>
                  <button class="modal-close" type="button" aria-label="Close" onclick="closeOrderMedicineModal()">×</button>
                </div>
                <form id="orderMedicineForm" onsubmit="submitMedicineOrder(event, ${medicine.id})">
                  <div class="rep-form-grid">
                    <div class="field"><label>Medicine</label><input value="${esc(medicine.name || '')}" readonly></div>
                    <div class="field"><label>Pharma Company</label><input value="${esc(medicine.company || me.company || '')}" readonly></div>
                    <div class="field"><label for="orderQty">Quantity <span aria-hidden="true">*</span></label><input id="orderQty" name="quantity" type="number" min="1" value="1" required></div>
                    <div class="field"><label for="orderDate">Requested Date</label><input id="orderDate" name="requested_date" type="date" value="${nextDate}" required></div>
                    <div class="field" style="grid-column: 1/-1;"><label for="orderNotes">Notes</label><textarea id="orderNotes" name="notes" rows="3" placeholder="Optional notes for the pharmacy team or sales rep."></textarea></div>
                    <div class="field" style="grid-column: 1/-1;"><label>Sales Representative</label><div class="info-readonly">Assigned by the backend based on the medicine company and current sales rep allocation.</div></div>
                  </div>
                  <div class="card" style="margin-top: 18px; padding: 18px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px;">
                    <div class="ey">ORDER SUMMARY</div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px;">
                      <div><b>Medicine</b><div>${esc(medicine.name || '')}</div></div>
                      <div><b>Company</b><div>${esc(medicine.company || me.company || '')}</div></div>
                      <div><b>Quantity</b><div id="summaryQty">1</div></div>
                      <div><b>Requested date</b><div id="summaryDate">${nextDate}</div></div>
                    </div>
                    <div style="margin-top: 12px;"><b>Notes</b><div id="summaryNotes">None</div></div>
                  </div>
                  <div class="modal-actions">
                    <button class="secondary" type="button" onclick="closeOrderMedicineModal()">Back</button>
                    <button class="primary" type="submit">Confirm Order</button>
                  </div>
                </form>
              </div>
            </div>
        `);

        const qty = document.getElementById('orderQty');
        const date = document.getElementById('orderDate');
        const notes = document.getElementById('orderNotes');
        const syncSummary = () => {
            document.getElementById('summaryQty').textContent = qty.value || '1';
            document.getElementById('summaryDate').textContent = date.value || nextDate;
            const noteText = notes.value.trim();
            document.getElementById('summaryNotes').textContent = noteText || 'None';
        };
        qty?.addEventListener('input', syncSummary);
        date?.addEventListener('input', syncSummary);
        notes?.addEventListener('input', syncSummary);
        qty?.focus();
    } catch (e) {
        toast(e.message);
    }
}

function closeOrderMedicineModal() { document.getElementById('orderMedicineModal')?.remove(); }

async function submitMedicineOrder(event, medicineId) {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    if (!submit) return;
    submit.disabled = true;

    const quantity = Number(form.querySelector('#orderQty')?.value || 0);
    const requestedDate = form.querySelector('#orderDate')?.value || '';
    const notes = form.querySelector('#orderNotes')?.value || '';

    if (!Number.isFinite(quantity) || quantity < 1) {
        toast('Quantity must be at least 1.');
        submit.disabled = false;
        return;
    }

    try {
        await api('/orders', {
            method: 'POST',
            body: JSON.stringify({ medicine_id: medicineId, quantity, requested_date: requestedDate, notes: notes.trim() })
        });
        closeOrderMedicineModal();
        toast('Order submitted successfully');
        go('orders');
    } catch (e) {
        toast(e.message);
        submit.disabled = false;
    }
}

async function openOrderDetails(orderId) {
    try {
        const detail = await api('/orders/' + orderId);
        const timeline = (detail.timeline || []).map(step => `
            <div class="timeline-item">
                <div class="timeline-dot"></div>
                <div>
                    <b>${esc(step.new_status || step.old_status || 'Status')}</b>
                    <div>${esc(step.note || 'Order update')}</div>
                    <small>${esc(step.timestamp || '')}</small>
                </div>
            </div>
        `).join('');
        const canManageStatus = ['pharma', 'sales_rep'].includes(role);

        document.body.insertAdjacentHTML('beforeend', `
            <div class="modal-backdrop" id="orderDetailModal" role="presentation" onclick="if(event.target===this)closeOrderDetailModal()">
              <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="orderDetailTitle" style="max-width: 820px;">
                <div class="modal-head">
                  <div>
                    <div class="ey">ORDER DETAILS</div>
                    <h2 id="orderDetailTitle">${esc(detail.order?.order_no || 'Order')}</h2>
                    <p>${esc(detail.medicine?.name || '')}</p>
                  </div>
                  <button class="modal-close" type="button" aria-label="Close" onclick="closeOrderDetailModal()">×</button>
                </div>
                <div class="grid two" style="margin-top: 12px;">
                  <div class="card" style="padding: 16px;">
                    <div><b>Medicine</b><div>${esc(detail.medicine?.name || '')}</div></div>
                    <div style="margin-top: 12px;"><b>Quantity</b><div>${detail.order?.quantity ?? 0}</div></div>
                    <div style="margin-top: 12px;"><b>Requested date</b><div>${esc(detail.order?.requested_date || '—')}</div></div>
                    <div style="margin-top: 12px;"><b>Company</b><div>${esc(detail.medicine?.company || detail.order?.company_id || '—')}</div></div>
                  </div>
                  <div class="card" style="padding: 16px;">
                    <div><b>Sales Representative</b><div>${esc(detail.sales_rep?.name || 'Unassigned')}</div></div>
                    <div style="margin-top: 12px;"><b>Current Status</b><div>${orderStatusBadge(detail.order?.status || 'Pending')}</div></div>
                    <div style="margin-top: 12px;"><b>Notes</b><div>${esc(detail.order?.notes || 'No notes')}</div></div>
                  </div>
                </div>
                <div class="card" style="margin-top: 18px; padding: 16px;">
                  <div class="ey">ORDER TIMELINE</div>
                  <div class="timeline" style="margin-top: 12px;">${timeline || '<div class="empty">No timeline entries yet.</div>'}</div>
                </div>
                ${canManageStatus ? `<div class="modal-actions"><button class="secondary" type="button" onclick="closeOrderDetailModal(); openUpdateOrderStatusModal(${detail.order?.id})">Update Status</button></div>` : ''}
              </div>
            </div>
        `);
    } catch (e) {
        toast(e.message);
    }
}

async function openUpdateOrderStatusModal(orderId) {
    try {
        const detail = await api('/orders/' + orderId);
        const statusValue = detail.order?.status || 'Pending';
        const options = ['Pending', 'Under Review', 'Assigned', 'Confirmed', 'Processing', 'Dispatched', 'Delivered', 'Rejected', 'Cancelled'];
        const current = detail.order || {};
        const form = `
            <div class="modal-backdrop" id="orderStatusModal" role="presentation" onclick="if(event.target===this)closeOrderStatusModal()">
              <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="orderStatusTitle" style="max-width: 620px;">
                <div class="modal-head">
                  <div>
                    <div class="ey">UPDATE ORDER STATUS</div>
                    <h2 id="orderStatusTitle">Update Order Status</h2>
                    <p>Order: ${esc(current.order_no || orderId)}</p>
                  </div>
                  <button class="modal-close" type="button" aria-label="Close" onclick="closeOrderStatusModal()">×</button>
                </div>
                <form id="orderStatusForm" onsubmit="submitOrderStatusUpdate(event, ${orderId})">
                  <div class="rep-form-grid">
                    <div class="field" style="grid-column: 1/-1;">
                      <label>Current Status</label>
                      <div class="info-readonly">${esc(statusValue)}</div>
                    </div>
                    <div class="field" style="grid-column: 1/-1;">
                      <label for="orderStatusSelect">New Status</label>
                      <select id="orderStatusSelect" name="status">${options.map(s => `<option value="${s}" ${s === statusValue ? 'selected' : ''}>${s}</option>`).join('')}</select>
                    </div>
                    <div class="field" style="grid-column: 1/-1;">
                      <label for="orderStatusNote">Optional Note</label>
                      <textarea id="orderStatusNote" name="note" rows="3" placeholder="Optional note for the doctor or internal workflow."></textarea>
                    </div>
                  </div>
                  <div class="modal-actions">
                    <button class="secondary" type="button" onclick="closeOrderStatusModal()">Cancel</button>
                    <button class="primary" type="submit">Update Status</button>
                  </div>
                </form>
              </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', form);
    } catch (e) {
        toast(e.message);
    }
}

async function submitOrderStatusUpdate(event, orderId) {
    event.preventDefault();
    const form = event.currentTarget;
    const status = form.elements.status.value;
    const note = form.elements.note.value.trim();
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    try {
        await api('/orders/' + orderId + '/status', { method: 'PATCH', body: JSON.stringify({ status, note }) });
        closeOrderStatusModal();
        toast('Order status updated');
        loadPage();
    } catch (e) {
        toast(e.message);
        if (submitButton) submitButton.disabled = false;
    }
}

function closeOrderStatusModal() { document.getElementById('orderStatusModal')?.remove(); }
function closeOrderDetailModal() { document.getElementById('orderDetailModal')?.remove(); }
function addRepModal() { const existing = document.getElementById('repModal'); if (existing) existing.remove(); document.body.insertAdjacentHTML('beforeend', `<div class="modal-backdrop" id="repModal" role="presentation" onclick="if(event.target===this)closeRepModal()"><div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="repModalTitle"><div class="modal-head"><div><div class="ey">TEAM MANAGEMENT</div><h2 id="repModalTitle">Add Sales Representative</h2><p>Create a representative account for your company.</p></div><button class="modal-close" type="button" aria-label="Close" onclick="closeRepModal()">×</button></div><form onsubmit="submitRep(event)"><div class="rep-form-grid"><div class="field"><label for="repName">Full Name <span aria-hidden="true">*</span></label><input id="repName" name="name" autocomplete="name" required></div><div class="field"><label for="repPhone">Phone Number <span aria-hidden="true">*</span></label><input id="repPhone" name="phone" type="tel" autocomplete="tel" required></div><div class="field"><label for="repEmail">Email Address <span aria-hidden="true">*</span></label><input id="repEmail" name="email" type="email" autocomplete="email" required></div><div class="field"><label for="repCompany">Pharma Company</label><input id="repCompany" name="company" value="${esc(me.company || '')}" readonly></div><div class="field"><label for="repPassword">Password <span aria-hidden="true">*</span></label><input id="repPassword" name="password" type="password" required></div><div class="field"><label for="repConfirmPassword">Confirm Password <span aria-hidden="true">*</span></label><input id="repConfirmPassword" name="confirm_password" type="password" required></div><div class="field"><label>Sales ID</label><div class="info-readonly">Automatically generated by PharmaAI</div></div></div><div class="modal-actions"><button class="secondary" type="button" onclick="closeRepModal()">Cancel</button><button class="primary" type="submit">Add representative</button></div></form></div></div>`); document.getElementById('repName').focus() }
function closeRepModal() { document.getElementById('repModal')?.remove() }
async function submitRep(event) { event.preventDefault(); const form = event.currentTarget; const submit = form.querySelector('button[type="submit"]'); submit.disabled = true; try { const password = form.elements.password.value.trim(); const confirm = form.elements.confirm_password.value.trim(); if (password.length < 6) throw Error('Password must be at least 6 characters'); if (password !== confirm) throw Error('Passwords do not match'); await api('/reps', { method: 'POST', body: JSON.stringify({ name: form.elements.name.value.trim(), email: form.elements.email.value.trim(), password, phone: form.elements.phone.value.trim(), job_title: 'Sales Representative' }) }); closeRepModal(); toast('Sales representative added'); loadPage() } catch (e) { toast(e.message); submit.disabled = false } }
window.addEventListener('popstate', () => render());
render();
