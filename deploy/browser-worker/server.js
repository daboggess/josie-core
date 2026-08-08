'use strict';

const http = require('http');

const allowlist = new Set(
  (process.env.JOSIE_BROWSER_ALLOWLIST || '')
    .split(',')
    .map(value => value.trim().toLowerCase())
    .filter(Boolean)
);

const server = http.createServer((request, response) => {
  response.setHeader('Content-Type', 'application/json');
  if (request.method === 'GET' && request.url === '/health') {
    response.writeHead(200);
    response.end(JSON.stringify({status: 'ok', execution: false, allowedHosts: allowlist.size}));
    return;
  }
  response.writeHead(403);
  response.end(JSON.stringify({status: 'locked', message: 'Browser execution is not enabled yet.'}));
});

server.listen(3010, '0.0.0.0');
