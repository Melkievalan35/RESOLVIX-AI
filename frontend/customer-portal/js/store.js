/* ==========================================================================
   RESOLVIX — mock data layer.
   Stands in for the real FastAPI backend so the portal is fully clickable
   without a server. Swap the body of each function for a fetch() call to
   ai/orchestrator + backend/api/* once the real API is wired up.
   ========================================================================== */

const DB_USERS = 'resolvix_users';
const DB_SESSION = 'resolvix_session';
const DB_COMPLAINTS = 'resolvix_complaints';
const DB_CHAT = 'resolvix_chat_';

const CATEGORIES = ['Billing', 'Product Defect', 'Delivery Delay', 'Refund Request', 'Service Quality', 'Fraud / Unauthorized Charge'];
const STATUSES = ['open', 'progress', 'resolved', 'escalated'];
const STATUS_LABEL = { open: 'Open', progress: 'In Progress', resolved: 'Resolved', escalated: 'Escalated' };

function readJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    return fallback;
  }
}
function writeJSON(key, value) { localStorage.setItem(key, JSON.stringify(value)); }

function genId(prefix) {
  return prefix + '-' + Math.random().toString(36).slice(2, 8).toUpperCase();
}
function genTicketId() {
  const year = new Date().getFullYear();
  const seq = String(Math.floor(1000 + Math.random() * 9000));
  return `RSLX-${year}-${seq}`;
}
function initials(name) {
  return (name || '?').split(' ').filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
}
function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}
function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

/* ---------- seed data on first load ---------- */
function seed() {
  if (!localStorage.getItem(DB_USERS)) {
    const demoUser = {
      id: genId('USR'),
      name: 'Aarav Sharma',
      email: 'demo@resolvix.ai',
      phone: '+91 98765 43210',
      password: 'demo1234',
      createdAt: new Date(Date.now() - 86400000 * 40).toISOString(),
      prefs: { emailNotify: true, smsNotify: false, whatsappNotify: true, marketing: false }
    };
    writeJSON(DB_USERS, [demoUser]);
  }
  if (!localStorage.getItem(DB_COMPLAINTS)) {
    const users = readJSON(DB_USERS, []);
    const uid = users[0].id;
    const now = Date.now();
    const demoComplaints = [
      { id: genId('CMP'), ticketId: genTicketId(), userId: uid, subject: 'Refund not processed for cancelled order', category: 'Refund Request', description: 'I cancelled order #48213 nine days ago and the refund has not reflected in my account yet.', priority: 'High', status: 'progress', createdAt: new Date(now - 86400000 * 3).toISOString(), evidence: ['invoice_48213.pdf'], confidence: 0.87 },
      { id: genId('CMP'), ticketId: genTicketId(), userId: uid, subject: 'Duplicate charge on last billing cycle', category: 'Billing', description: 'My statement shows two charges of ₹2,499 on the same day for one subscription renewal.', priority: 'Medium', status: 'resolved', createdAt: new Date(now - 86400000 * 12).toISOString(), evidence: ['statement_july.pdf'], confidence: 0.95 },
      { id: genId('CMP'), ticketId: genTicketId(), userId: uid, subject: 'Package arrived damaged', category: 'Product Defect', description: 'The unit arrived with a cracked casing, photos attached from the delivery agent handover.', priority: 'High', status: 'open', createdAt: new Date(now - 86400000 * 1).toISOString(), evidence: ['damage_photo_1.jpg', 'damage_photo_2.jpg'], confidence: 0.62 },
      { id: genId('CMP'), ticketId: genTicketId(), userId: uid, subject: 'Suspicious charge I did not authorize', category: 'Fraud / Unauthorized Charge', description: 'A charge of ₹8,999 appeared that I do not recognize and did not authorize.', priority: 'Critical', status: 'escalated', createdAt: new Date(now - 86400000 * 6).toISOString(), evidence: ['screenshot_txn.png'], confidence: 0.41 }
    ];
    writeJSON(DB_COMPLAINTS, demoComplaints);
  }
}
seed();

/* ---------- auth ---------- */
const Store = {
  CATEGORIES, STATUSES, STATUS_LABEL,
  initials, timeAgo, formatDate,

  currentUser() {
    const session = readJSON(DB_SESSION, null);
    if (!session) return null;
    const users = readJSON(DB_USERS, []);
    return users.find(u => u.id === session.userId) || null;
  },

  requireAuth() {
    if (!this.currentUser()) {
      window.location.href = 'login.html';
    }
  },

  redirectIfAuthed() {
    if (this.currentUser()) window.location.href = 'dashboard.html';
  },

  login(email, password) {
    const users = readJSON(DB_USERS, []);
    const user = users.find(u => u.email.toLowerCase() === email.toLowerCase());
    if (!user) return { ok: false, error: 'No account found with that email.' };
    if (user.password !== password) return { ok: false, error: 'Incorrect password. Please try again.' };
    writeJSON(DB_SESSION, { userId: user.id });
    return { ok: true };
  },

  register({ name, email, phone, password }) {
    const users = readJSON(DB_USERS, []);
    if (users.some(u => u.email.toLowerCase() === email.toLowerCase())) {
      return { ok: false, error: 'An account with this email already exists.' };
    }
    const user = { id: genId('USR'), name, email, phone, password, createdAt: new Date().toISOString(), prefs: { emailNotify: true, smsNotify: false, whatsappNotify: false, marketing: false } };
    users.push(user);
    writeJSON(DB_USERS, users);
    writeJSON(DB_SESSION, { userId: user.id });
    return { ok: true };
  },

  logout() {
    localStorage.removeItem(DB_SESSION);
    window.location.href = 'login.html';
  },

  updateProfile(userId, patch) {
    const users = readJSON(DB_USERS, []);
    const idx = users.findIndex(u => u.id === userId);
    if (idx === -1) return { ok: false };
    users[idx] = { ...users[idx], ...patch };
    writeJSON(DB_USERS, users);
    return { ok: true, user: users[idx] };
  },

  /* ---------- complaints ---------- */
  listComplaints(userId) {
    return readJSON(DB_COMPLAINTS, []).filter(c => c.userId === userId).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  },

  getComplaint(id) {
    return readJSON(DB_COMPLAINTS, []).find(c => c.id === id) || null;
  },

  createComplaint(userId, data) {
    const complaints = readJSON(DB_COMPLAINTS, []);
    const record = {
      id: genId('CMP'),
      ticketId: genTicketId(),
      userId,
      createdAt: new Date().toISOString(),
      status: 'open',
      confidence: Math.round((0.55 + Math.random() * 0.4) * 100) / 100,
      ...data
    };
    complaints.push(record);
    writeJSON(DB_COMPLAINTS, complaints);
    return record;
  },

  timelineFor(status) {
    const base = [
      { key: 'received', title: 'Complaint received', sub: 'Customer Agent logged the case' },
      { key: 'evidence', title: 'Evidence reviewed', sub: 'Evidence Agent parsed attachments' },
      { key: 'policy', title: 'Policy check', sub: 'Policy Agent matched applicable clauses' },
      { key: 'decision', title: 'Resolution decided', sub: 'Resolution Agent proposed an outcome' },
      { key: 'closed', title: 'Case closed', sub: 'Confirmation sent to customer' }
    ];
    const order = { open: 1, progress: 3, resolved: 5, escalated: 3 };
    const doneCount = order[status] || 1;
    return base.map((step, i) => ({
      ...step,
      state: status === 'escalated' && i === 3 ? 'current-escalated' : (i < doneCount ? 'done' : (i === doneCount ? 'current' : 'pending'))
    }));
  }
};
