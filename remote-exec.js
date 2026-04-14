const http = require('http');
const { exec } = require('child_process');

const TOKEN = process.env.EXEC_TOKEN || 'zencoder-exec-2026';

const server = http.createServer((req, res) => {
  if (req.method !== 'POST' || req.url !== '/exec') {
    res.writeHead(404); res.end('Not found'); return;
  }
  const auth = req.headers['x-token'];
  if (auth !== TOKEN) {
    res.writeHead(401); res.end('Unauthorized'); return;
  }
  let body = '';
  req.on('data', d => body += d);
  req.on('end', () => {
    const { cmd, cwd } = JSON.parse(body);
    exec(cmd, { cwd: cwd || '/workspaces/Toolkit', timeout: 120000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ code: err ? err.code || 1 : 0, stdout, stderr }));
    });
  });
});

server.listen(9999, '0.0.0.0', () => {
  console.log('Remote exec server running on port 9999');
  console.log('Token: ' + TOKEN);
});
