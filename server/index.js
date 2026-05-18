const express = require('express');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config();

const PORT = process.env.PORT || 3000;
const SECRET = process.env.WELLCARE_SECRET || 'dev-secret-change-me';
const DB_PATH = process.env.WELLCARE_DB_PATH || path.join(__dirname, 'data', 'db.json');
const DEBUG_DB_ENABLED = process.env.WELLCARE_ENABLE_DEBUG_DB === 'true';

const DEFAULT_SHARE_SETTINGS = {
  risk: true,
  level: true,
  trend: true,
  last_checkin: true,
  top_contributors: false,
  recovery_status: false,
  important_updates: true,
  private_answers: false,
  notes: false,
};

function normalizeShareSettings(share) {
  return { ...DEFAULT_SHARE_SETTINGS, ...(share && typeof share === 'object' ? share : {}) };
}

function normalizeThreshold(value, fallback = 0.75) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(0, Math.min(1, n));
}

function ensureDb() {
  const dir = path.dirname(DB_PATH);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(DB_PATH)) fs.writeFileSync(DB_PATH, JSON.stringify({ invites: [], connections: [], notifications: [] }, null, 2));
}

function readDb() {
  ensureDb();
  const db = JSON.parse(fs.readFileSync(DB_PATH, 'utf8'));
  if (!Array.isArray(db.invites)) db.invites = [];
  if (!Array.isArray(db.connections)) db.connections = [];
  if (!Array.isArray(db.notifications)) db.notifications = [];
  if (!Array.isArray(db.checkins)) db.checkins = [];
  return db;
}
function writeDb(obj) { fs.writeFileSync(DB_PATH, JSON.stringify(obj, null, 2)); }

function makeToken(payload) {
  const json = JSON.stringify(payload);
  const b = Buffer.from(json).toString('base64url');
  const h = crypto.createHmac('sha256', SECRET).update(b).digest('hex');
  return `${b}.${h}`;
}

function verifyToken(token) {
  if (!token || typeof token !== 'string') return null;
  const parts = token.split('.');
  if (parts.length !== 2) return null;
  const [b, h] = parts;
  const expect = crypto.createHmac('sha256', SECRET).update(b).digest('hex');
  const given = Buffer.from(h);
  const wanted = Buffer.from(expect);
  if (given.length !== wanted.length) return null;
  if (!crypto.timingSafeEqual(given, wanted)) return null;
  try { return JSON.parse(Buffer.from(b, 'base64url').toString('utf8')); } catch (e) { return null; }
}

const ROOT_PATH = path.join(__dirname, '..');
const app = express();
app.use(express.json());
app.use(express.static(ROOT_PATH));

app.get('/', (req, res) => res.sendFile(path.join(ROOT_PATH, 'checkin-app.html')));

app.get('/health', (req, res) => res.json({ ok: true }));

app.post('/api/invite/create', (req, res) => {
  const from = req.body.from || { personId: 'me', name: 'Me' };
  const share = normalizeShareSettings(req.body.share);
  const alertThreshold = normalizeThreshold(req.body.alertThreshold);
  const payload = {
    from: from.personId || from.id || 'me',
    name: from.name || '',
    sharingMode: req.body.sharingMode || 'supportive',
    share,
    alertThreshold,
    notificationEnabled: req.body.notificationEnabled !== false,
    ts: Date.now(),
    exp: Date.now() + (7 * 24 * 3600 * 1000),
  };
  const token = makeToken(payload);

  const db = readDb();
  const token_hash = crypto.createHash('sha256').update(token).digest('hex');
  db.invites.push({
    id: crypto.randomUUID(),
    from: payload.from,
    name: payload.name,
    sharingMode: payload.sharingMode,
    share: payload.share,
    alertThreshold: payload.alertThreshold,
    notificationEnabled: payload.notificationEnabled,
    token_hash,
    status: 'pending',
    expires_at: new Date(payload.exp).toISOString(),
    created_at: new Date().toISOString(),
  });
  writeDb(db);

  res.json({ token });
});

app.post('/api/invite/accept', (req, res) => {
  const token = req.body.token;
  const acceptor = req.body.acceptor || {};
  const payload = verifyToken(token);
  if (!payload) return res.status(400).json({ error: 'invalid_token' });
  if (payload.exp && Date.now() > payload.exp) return res.status(400).json({ error: 'expired' });

  const db = readDb();
  const token_hash = crypto.createHash('sha256').update(token).digest('hex');
  const invite = db.invites.find(i => i.token_hash === token_hash && (i.status === 'pending' || i.status === 'created'));
  if (!invite) return res.status(404).json({ error: 'not_found' });

  // mark invite accepted and create connection
  invite.status = 'accepted';
  invite.accepted_at = new Date().toISOString();
  invite.accepted_by = acceptor.personId || acceptor.id || null;
  const sharingMode = payload.sharingMode || invite.sharingMode || 'supportive';
  const conn = {
    id: crypto.randomUUID(),
    personId: payload.from,
    connectedPersonId: acceptor.personId || acceptor.id || null,
    connectedName: acceptor.name || '',
    name: payload.name || payload.from,
    relationship: 'Friend',
    status: 'accepted',
    sharingMode,
    alertThreshold: normalizeThreshold(payload.alertThreshold, invite.alertThreshold),
    notificationEnabled: payload.notificationEnabled !== false,
    share: normalizeShareSettings(payload.share || invite.share),
    created_at: new Date().toISOString(),
  };
  db.connections.push(conn);
  writeDb(db);

  res.json({ connection: conn });
});

app.post('/api/checkins', (req, res) => {
  const personId = String(req.body.personId || req.body.person_id || '').trim();
  const entry = req.body.entry || {};
  const when = entry.when || new Date().toISOString();
  const risk = Number(entry.risk);
  if (!personId) return res.status(400).json({ error: 'missing_person_id' });
  if (!Number.isFinite(risk)) return res.status(400).json({ error: 'missing_risk' });

  const shared = {
    id: String(entry.id || `${personId}-${when}`),
    person_id: personId,
    name: req.body.name || entry.name || '',
    when,
    risk: Math.max(0, Math.min(1, risk)),
    verdict: entry.verdict || '',
    recovery_status: entry.recovery_status || '',
    recovery_key: entry.recovery_key || '',
    updated_at: new Date().toISOString(),
  };

  const db = readDb();
  const idx = db.checkins.findIndex(x => x.id === shared.id || (x.person_id === personId && x.when === when));
  if (idx >= 0) db.checkins[idx] = { ...db.checkins[idx], ...shared };
  else db.checkins.push(shared);
  db.checkins = db.checkins
    .sort((a, b) => new Date(b.when) - new Date(a.when))
    .slice(0, 1000);
  writeDb(db);

  res.json({ ok: true, checkin: shared });
});

app.get('/api/shared-tracker/:personId', (req, res) => {
  const personId = String(req.params.personId || '').trim();
  const viewerPersonId = String(req.query.viewerPersonId || req.query.viewer || '').trim();
  if (!viewerPersonId) return res.status(400).json({ error: 'missing_viewer_person_id' });

  const db = readDb();
  const canViewSelf = viewerPersonId === personId;
  const hasAcceptedConnection = db.connections.some(c =>
    c.status === 'accepted' &&
    c.personId === personId &&
    c.connectedPersonId === viewerPersonId
  );
  if (!canViewSelf && !hasAcceptedConnection) {
    return res.status(403).json({ error: 'not_connected' });
  }

  const rows = db.checkins
    .filter(x => x.person_id === personId)
    .sort((a, b) => new Date(b.when) - new Date(a.when))
    .slice(0, 30);
  res.json({ personId, checkins: rows });
});

app.get('/api/db', (req, res) => {
  if (!DEBUG_DB_ENABLED) return res.status(404).json({ error: 'not_found' });
  res.json(readDb());
});

if (require.main === module) {
  app.listen(PORT, () => console.log(`WellCare invite server running on http://localhost:${PORT}`));
}

module.exports = app;
