const express = require('express');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config();

const PORT = process.env.PORT || 3000;
const SECRET = process.env.WELLCARE_SECRET || 'dev-secret-change-me';
const DB_PATH = path.join(__dirname, 'data', 'db.json');

function ensureDb() {
  const dir = path.dirname(DB_PATH);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  if (!fs.existsSync(DB_PATH)) fs.writeFileSync(DB_PATH, JSON.stringify({ invites: [], connections: [], notifications: [] }, null, 2));
}

function readDb() { ensureDb(); return JSON.parse(fs.readFileSync(DB_PATH, 'utf8')); }
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
  if (!crypto.timingSafeEqual(Buffer.from(h), Buffer.from(expect))) return null;
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
  const payload = { from: from.personId || from.id || 'me', name: from.name || '', ts: Date.now(), exp: Date.now() + (7 * 24 * 3600 * 1000) };
  const token = makeToken(payload);

  const db = readDb();
  const token_hash = crypto.createHash('sha256').update(token).digest('hex');
  db.invites.push({ id: crypto.randomUUID(), from: payload.from, name: payload.name, token_hash, status: 'pending', expires_at: new Date(payload.exp).toISOString(), created_at: new Date().toISOString() });
  writeDb(db);

  res.json({ token });
});

app.post('/api/invite/accept', (req, res) => {
  const token = req.body.token;
  const payload = verifyToken(token);
  if (!payload) return res.status(400).json({ error: 'invalid_token' });
  if (payload.exp && Date.now() > payload.exp) return res.status(400).json({ error: 'expired' });

  const db = readDb();
  const token_hash = crypto.createHash('sha256').update(token).digest('hex');
  const invite = db.invites.find(i => i.token_hash === token_hash && (i.status === 'pending' || i.status === 'created'));
  if (!invite) return res.status(404).json({ error: 'not_found' });

  // mark invite accepted and create connection
  invite.status = 'accepted';
  const conn = { id: crypto.randomUUID(), personId: payload.from, name: payload.name || payload.from, relationship: 'Friend', alertThreshold: 0.75, share: { risk: true, trend: true, last_checkin: true }, created_at: new Date().toISOString() };
  db.connections.push(conn);
  writeDb(db);

  res.json({ connection: conn });
});

app.get('/api/db', (req, res) => {
  res.json(readDb());
});

if (require.main === module) {
  app.listen(PORT, () => console.log(`WellCare invite server running on http://localhost:${PORT}`));
}

module.exports = app;
