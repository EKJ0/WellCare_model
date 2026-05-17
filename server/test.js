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
    const create = await request(port, { method: 'POST', path: '/api/invite/create', headers: { 'Content-Type': 'application/json' } }, { from: { personId: 'me', name: 'Me' } });
    assert.strictEqual(create.statusCode, 200, 'invite create should return 200');
    assert.ok(create.body.token, 'invite create response contains token');
    assert.ok(create.body.token.includes('.'), 'token should be signed');

    const accept = await request(port, { method: 'POST', path: '/api/invite/accept', headers: { 'Content-Type': 'application/json' } }, { token: create.body.token });
    assert.strictEqual(accept.statusCode, 200, 'invite accept should return 200');
    assert.ok(accept.body.connection, 'invite accept response contains connection');
    assert.strictEqual(accept.body.connection.personId, 'me');
    assert.strictEqual(accept.body.connection.status, 'accepted');
    assert.strictEqual(accept.body.connection.notificationEnabled, true);
    assert.strictEqual(accept.body.connection.share.risk, true);
    assert.strictEqual(accept.body.connection.share.trend, true);
    assert.strictEqual(accept.body.connection.share.last_checkin, true);
    assert.strictEqual(accept.body.connection.share.private_answers, false);
    assert.strictEqual(accept.body.connection.share.notes, false);

    const db = await request(port, { method: 'GET', path: '/api/db' });
    assert.strictEqual(db.statusCode, 200, 'database endpoint should return 200');
    assert.ok(Array.isArray(db.body.invites), 'db includes invites array');
    assert.ok(Array.isArray(db.body.connections), 'db includes connections array');
    assert.strictEqual(db.body.invites[0].status, 'accepted');
    assert.ok(db.body.invites[0].accepted_at, 'accepted invite records accepted_at');
    assert.strictEqual(db.body.connections[0].personId, 'me');

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
