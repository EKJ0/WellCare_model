const assert = require('assert');
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wellcare-test-'));
process.env.WELLCARE_DB_PATH = path.join(tempDir, 'db.json');

const app = require('./index');

function request(port, options, body) {
  return new Promise((resolve, reject) => {
    const req = http.request({ ...options, port }, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data || '{}');
          resolve({ statusCode: res.statusCode, body: parsed });
        } catch (err) {
          reject(err);
        }
      });
    });
    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

async function run() {
  const server = app.listen(0);
  const port = server.address().port;
  try {
    const create = await request(port, { method: 'POST', path: '/api/invite/create', headers: { 'Content-Type': 'application/json' } }, {
      from: { personId: 'me', name: 'Me' },
      sharingMode: 'minimal',
      alertThreshold: 0.8,
      notificationEnabled: true,
      share: {
        risk: false,
        level: true,
        trend: false,
        last_checkin: true,
        notes: false,
      },
    });
    assert.strictEqual(create.statusCode, 200, 'invite create should return 200');
    assert.ok(create.body.token, 'invite create response contains token');
    assert.ok(create.body.token.includes('.'), 'token should be signed');

    const invalid = await request(port, { method: 'POST', path: '/api/invite/accept', headers: { 'Content-Type': 'application/json' } }, { token: 'short.bad' });
    assert.strictEqual(invalid.statusCode, 400, 'malformed token should return 400');
    assert.strictEqual(invalid.body.error, 'invalid_token');

    const accept = await request(port, { method: 'POST', path: '/api/invite/accept', headers: { 'Content-Type': 'application/json' } }, {
      token: create.body.token,
      acceptor: { personId: 'friend', name: 'Friend' },
    });
    assert.strictEqual(accept.statusCode, 200, 'invite accept should return 200');
    assert.ok(accept.body.connection, 'invite accept response contains connection');
    assert.strictEqual(accept.body.connection.personId, 'me');
    assert.strictEqual(accept.body.connection.connectedPersonId, 'friend');
    assert.strictEqual(accept.body.connection.status, 'accepted');
    assert.strictEqual(accept.body.connection.sharingMode, 'minimal');
    assert.strictEqual(accept.body.connection.alertThreshold, 0.8);
    assert.strictEqual(accept.body.connection.notificationEnabled, true);
    assert.strictEqual(accept.body.connection.share.risk, false);
    assert.strictEqual(accept.body.connection.share.trend, false);
    assert.strictEqual(accept.body.connection.share.last_checkin, true);
    assert.strictEqual(accept.body.connection.share.private_answers, false);
    assert.strictEqual(accept.body.connection.share.notes, false);

    const dbEndpoint = await request(port, { method: 'GET', path: '/api/db' });
    assert.strictEqual(dbEndpoint.statusCode, 404, 'database endpoint is hidden by default');

    const db = JSON.parse(fs.readFileSync(process.env.WELLCARE_DB_PATH, 'utf8'));
    assert.ok(Array.isArray(db.invites), 'db includes invites array');
    assert.ok(Array.isArray(db.connections), 'db includes connections array');
    assert.strictEqual(db.invites[0].status, 'accepted');
    assert.ok(db.invites[0].accepted_at, 'accepted invite records accepted_at');
    assert.strictEqual(db.invites[0].accepted_by, 'friend');
    assert.strictEqual(db.connections[0].personId, 'me');

    const checkin = await request(port, { method: 'POST', path: '/api/checkins', headers: { 'Content-Type': 'application/json' } }, {
      personId: 'me',
      name: 'Me',
      entry: { id: 'c1', when: '2026-05-18T10:00:00.000Z', risk: 0.72, verdict: 'High', notes: 'private note' },
    });
    assert.strictEqual(checkin.statusCode, 200, 'checkin sync should return 200');
    assert.strictEqual(checkin.body.checkin.risk, 0.72);
    assert.strictEqual(checkin.body.checkin.notes, undefined, 'shared checkin must not expose notes');

    const missingViewer = await request(port, { method: 'GET', path: '/api/shared-tracker/me' });
    assert.strictEqual(missingViewer.statusCode, 400, 'shared tracker requires viewer identity');

    const wrongViewer = await request(port, { method: 'GET', path: '/api/shared-tracker/me?viewerPersonId=stranger' });
    assert.strictEqual(wrongViewer.statusCode, 403, 'shared tracker rejects unconnected viewers');

    const shared = await request(port, { method: 'GET', path: '/api/shared-tracker/me?viewerPersonId=friend' });
    assert.strictEqual(shared.statusCode, 200, 'shared tracker should return 200');
    assert.strictEqual(shared.body.checkins.length, 1);
    assert.strictEqual(shared.body.checkins[0].person_id, 'me');
    assert.strictEqual(shared.body.checkins[0].notes, undefined, 'shared tracker hides private notes');

    console.log('All server tests passed.');
  } finally {
    server.close();
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

run().catch(err => {
  console.error('Server test failed:', err);
  process.exit(1);
});
