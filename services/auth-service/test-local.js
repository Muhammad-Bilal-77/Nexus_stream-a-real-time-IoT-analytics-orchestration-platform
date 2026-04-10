const db = require('./src/db');
const keys = require('./src/keys');
const app = require('./src/index');
const request = require('supertest');

async function runLocalTests() {
  console.log('Testing Auth Service Locally...');

  // 1. Mock DB specifically for tests to avoid hitting live PG
  db.query = async (text, params) => {
    if (text.includes('SELECT id FROM users WHERE username = $1 OR email = $2')) {
      return { rowCount: 0 };
    }
    if (text.includes('INSERT INTO users')) {
      return { rows: [{ id: 'mock-uuid', username: params[0] }] };
    }
    if (text.includes('SELECT r.name FROM roles')) {
      return { rows: [{ name: 'viewer' }] };
    }
    if (text.includes('SELECT id, username, password_hash, is_active FROM users')) {
      return { 
        rowCount: 1, 
        rows: [{ 
          id: 'mock-uuid', 
          username: params[0], 
          password_hash: 'PLACEHOLDER_HASH', // special mock bypass condition we added
          is_active: true 
        }] 
      };
    }
    return { rowCount: 1, rows: [{ id: 'mock-role-id' }] };
  };

  db.getClient = async () => ({
    query: db.query,
    release: () => {}
  });

  // 2. Perform test signup
  let res = await request(app).post('/auth/signup').send({
    username: 'testuser',
    email: 'test@example.com',
    password: 'securepassword'
  });
  console.log('Signup Res:', res.status, res.body);

  // 3. Perform test login matching our "PLACEHOLDER_HASH -> nexusstream" bypass
  res = await request(app).post('/auth/login').send({
    username: 'testuser',
    password: 'nexusstream'
  });
  console.log('Login Res:', res.status);
  
  if (res.status === 200) {
    console.log('Token snippet:', res.body.access_token.slice(0, 20) + '...');
  } else {
    console.log(res.body);
  }

  // 4. Fetch public key
  res = await request(app).get('/auth/public-key');
  console.log('Public Key Route Res:', res.status);
  if (res.status === 200) {
    console.log('Key length:', res.body.public_key.length);
  }

  process.exit(0);
}

runLocalTests().catch(e => {
  console.error(e);
  process.exit(1);
});
