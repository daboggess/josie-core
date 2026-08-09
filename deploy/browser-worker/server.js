'use strict';

const crypto = require('crypto');
const dns = require('dns');
const fs = require('fs');
const http = require('http');
const https = require('https');
const net = require('net');

const policyPath = '/app/browser-policy.json';
const tokenPath = '/run/secrets/browser_token';
let activeRequests = 0;
const recentRequests = [];

function loadPolicy() {
  const raw = fs.readFileSync(policyPath, 'utf8');
  if (Buffer.byteLength(raw, 'utf8') > 32_768) throw new Error('Policy exceeds size limit');
  const policy = JSON.parse(raw);
  if (policy.schema_version !== 2 || policy.enabled !== true || policy.default !== 'deny'
      || policy.mode !== 'read_only_research') throw new Error('Policy is not an enabled read-only pilot');
  const expiresAt = Date.parse(policy.pilot && policy.pilot.expires_at);
  if (!Number.isFinite(expiresAt) || Date.now() >= expiresAt) throw new Error('Policy is expired');
  if (!Array.isArray(policy.allowed_hosts) || policy.allowed_hosts.length < 1
      || policy.allowed_hosts.some(host => typeof host !== 'string' || host.includes('*'))) {
    throw new Error('Exact hostname allowlist is invalid');
  }
  if (!Array.isArray(policy.allowed_urls) || policy.allowed_urls.length < 1
      || policy.allowed_urls.some(value => typeof value !== 'string' || !value.startsWith('https://'))) {
    throw new Error('Exact URL allowlist is invalid');
  }
  const capabilities = policy.capabilities || {};
  if (capabilities.navigation !== true || capabilities.extraction !== true
      || capabilities.form_entry !== false || capabilities.downloads !== false
      || capabilities.uploads !== false) throw new Error('Capability boundary is invalid');
  const content = policy.content_controls || {};
  if (content.model_direct_access !== false || content.persist_page_content !== false
      || content.javascript_execution !== false || content.cookies_enabled !== false
      || content.treat_page_content_as_untrusted !== true
      || content.strip_hidden_text_before_model_review !== true
      || content.strip_scripts_before_model_review !== true) throw new Error('Content boundary is invalid');
  const limits = policy.request_limits || {};
  if (!Array.isArray(limits.allowed_schemes) || limits.allowed_schemes.join(',') !== 'https'
      || !Array.isArray(limits.allowed_ports) || limits.allowed_ports.join(',') !== '443'
      || limits.parallel_requests !== 1) throw new Error('Request boundary is invalid');
  return policy;
}

function loadToken() {
  const token = fs.readFileSync(tokenPath, 'utf8').trim();
  if (token.length < 32) throw new Error('Browser credential is invalid');
  return token;
}

function isAuthorized(request) {
  const header = request.headers.authorization;
  if (typeof header !== 'string' || !header.startsWith('Bearer ')) return false;
  const supplied = Buffer.from(header.slice('Bearer '.length), 'utf8');
  const expected = Buffer.from(loadToken(), 'utf8');
  return supplied.length === expected.length && crypto.timingSafeEqual(supplied, expected);
}

const blocked = new net.BlockList();
for (const [network, prefix] of [
  ['0.0.0.0', 8], ['10.0.0.0', 8], ['100.64.0.0', 10], ['127.0.0.0', 8],
  ['169.254.0.0', 16], ['172.16.0.0', 12], ['192.0.0.0', 24], ['192.0.2.0', 24],
  ['192.168.0.0', 16], ['198.18.0.0', 15], ['198.51.100.0', 24],
  ['203.0.113.0', 24], ['224.0.0.0', 4], ['240.0.0.0', 4],
]) blocked.addSubnet(network, prefix, 'ipv4');
for (const [network, prefix] of [
  ['::', 128], ['::1', 128], ['fc00::', 7], ['fe80::', 10], ['ff00::', 8], ['2001:db8::', 32],
]) blocked.addSubnet(network, prefix, 'ipv6');

function isPublicAddress(address, family) {
  if (family === 4 || net.isIP(address) === 4) return !blocked.check(address, 'ipv4');
  if (family === 6 || net.isIP(address) === 6) {
    const mapped = address.toLowerCase().match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
    if (mapped) return !blocked.check(mapped[1], 'ipv4');
    return !blocked.check(address, 'ipv6');
  }
  return false;
}

function safeLookup(hostname, options, callback) {
  dns.lookup(hostname, {all: true, verbatim: true}, (error, records) => {
    if (error) return callback(error);
    if (!records.length || records.some(record => !isPublicAddress(record.address, record.family))) {
      return callback(new Error('DNS resolution included a blocked address'));
    }
    if (options && options.all) return callback(null, records);
    return callback(null, records[0].address, records[0].family);
  });
}

function pathAllowed(policy, hostname, pathname) {
  const values = policy.allowed_paths && policy.allowed_paths[hostname];
  return Array.isArray(values) && values.some(value => pathname === value);
}

function validateUrl(policy, value) {
  let url;
  try { url = new URL(value); } catch { throw new Error('URL is invalid'); }
  if (url.protocol !== 'https:' || (url.port && url.port !== '443')) throw new Error('HTTPS port 443 is required');
  if (url.username || url.password) throw new Error('URL credentials are forbidden');
  if (net.isIP(url.hostname)) throw new Error('IP-literal destinations are forbidden');
  const hostname = url.hostname.toLowerCase();
  if (!policy.allowed_hosts.includes(hostname)) throw new Error('Hostname is not allowlisted');
  if (!pathAllowed(policy, hostname, url.pathname)) throw new Error('Path is not allowlisted');
  if (!policy.allowed_urls.includes(url.toString())) throw new Error('URL is not exactly allowlisted');
  return url;
}

function decodeEntities(value) {
  const named = {amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' '};
  return value.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (match, entity) => {
    if (entity[0] !== '#') return named[entity.toLowerCase()] || ' ';
    const code = entity[1].toLowerCase() === 'x' ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10);
    return Number.isFinite(code) && code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : ' ';
  });
}

function extractVisibleText(html, maximum) {
  let safe = html.replace(/<!--[^]*?-->/g, ' ');
  safe = safe.replace(/<(script|style|noscript|template|svg|canvas|iframe|object|embed)[^>]*>[^]*?<\/\1\s*>/gi, ' ');
  safe = safe.replace(/<([a-z0-9:-]+)[^>]*(?:\shidden(?:\s|=|>)|aria-hidden\s*=\s*["']?true|style\s*=\s*["'][^"']*(?:display\s*:\s*none|visibility\s*:\s*hidden))[^>]*>[^]*?<\/\1\s*>/gi, ' ');
  safe = safe.replace(/<form\b[^>]*>[^]*?<\/form\s*>/gi, ' ');
  safe = safe.replace(/<[^>]+>/g, ' ');
  safe = decodeEntities(safe).replace(/[\t\r ]+/g, ' ').replace(/ *\n+ */g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  return safe.slice(0, maximum);
}

function fetchPage(policy, inputUrl, redirectCount = 0) {
  const url = validateUrl(policy, inputUrl);
  const limits = policy.request_limits;
  return new Promise((resolve, reject) => {
    const request = https.request(url, {
      method: 'GET', lookup: safeLookup, timeout: limits.request_timeout_seconds * 1000,
      headers: {
        'Accept': limits.allowed_content_types.join(', '),
        'User-Agent': 'Josie-ReadOnly-Research/1.0',
        'Cache-Control': 'no-store',
      },
    }, response => {
      const status = response.statusCode || 0;
      if ([301, 302, 303, 307, 308].includes(status)) {
        response.resume();
        if (redirectCount >= limits.max_redirects) return reject(new Error('Redirect limit exceeded'));
        if (!response.headers.location) return reject(new Error('Redirect location is missing'));
        let next;
        try { next = new URL(response.headers.location, url).toString(); } catch { return reject(new Error('Redirect URL is invalid')); }
        try { validateUrl(policy, next); } catch { return reject(new Error('Redirect left the exact allowlist')); }
        return fetchPage(policy, next, redirectCount + 1).then(resolve, reject);
      }
      if (status !== 200) { response.resume(); return reject(new Error(`Upstream returned HTTP ${status}`)); }
      const contentType = String(response.headers['content-type'] || '').split(';', 1)[0].trim().toLowerCase();
      if (!limits.allowed_content_types.includes(contentType)) {
        response.resume();
        return reject(new Error(`Content type is not approved: ${contentType || 'missing'}`));
      }
      const advertised = Number(response.headers['content-length'] || 0);
      if (advertised > limits.max_response_bytes) { response.resume(); return reject(new Error('Response exceeds byte limit')); }
      const chunks = [];
      let total = 0;
      response.on('data', chunk => {
        total += chunk.length;
        if (total > limits.max_response_bytes) {
          response.destroy(new Error('Response exceeds byte limit'));
          return;
        }
        chunks.push(chunk);
      });
      response.on('error', reject);
      response.on('end', () => {
        const html = Buffer.concat(chunks).toString('utf8');
        const titleMatch = html.match(/<title[^>]*>([^]*?)<\/title\s*>/i);
        resolve({
          finalUrl: url.toString(), contentType, bytesReceived: total,
          title: titleMatch ? extractVisibleText(titleMatch[1], 300) : '',
          text: extractVisibleText(html, limits.max_output_characters),
        });
      });
    });
    request.on('timeout', () => request.destroy(new Error('Request timed out')));
    request.on('error', reject);
    request.end();
  });
}

function readJsonBody(request, maximum = 16_384) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    request.on('data', chunk => {
      total += chunk.length;
      if (total > maximum) return reject(new Error('Request body exceeds limit'));
      chunks.push(chunk);
    });
    request.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
      catch { reject(new Error('Request body must be valid JSON')); }
    });
    request.on('error', reject);
  });
}

function send(response, status, payload) {
  response.setHeader('Content-Type', 'application/json');
  response.setHeader('Cache-Control', 'no-store');
  response.setHeader('X-Content-Type-Options', 'nosniff');
  response.writeHead(status);
  response.end(JSON.stringify(payload));
}

const server = http.createServer(async (request, response) => {
  let policy;
  try { policy = loadPolicy(); }
  catch (error) { return send(response, 503, {status: 'locked', message: error.message}); }

  if (request.method === 'GET' && request.url === '/health') {
    return send(response, 200, {
      status: 'ok', execution: true, mode: 'read_only_research',
      allowedHosts: policy.allowed_hosts.length, writeActions: false,
      authRequired: true, modelDirectAccess: false,
    });
  }
  if (request.method !== 'POST' || request.url !== '/extract') {
    return send(response, 403, {status: 'locked', message: 'Only authenticated read-only extraction is available.'});
  }
  try { if (!isAuthorized(request)) return send(response, 401, {status: 'unauthorized'}); }
  catch { return send(response, 503, {status: 'locked', message: 'Credential is unavailable.'}); }

  const now = Date.now();
  while (recentRequests.length && recentRequests[0] <= now - 60_000) recentRequests.shift();
  if (activeRequests >= policy.request_limits.parallel_requests
      || recentRequests.length >= policy.request_limits.requests_per_minute) {
    return send(response, 429, {status: 'rate_limited'});
  }
  activeRequests += 1;
  recentRequests.push(now);
  try {
    const body = await readJsonBody(request);
    if (!body || Object.keys(body).length !== 1 || typeof body.url !== 'string') {
      throw new Error('Only one URL field is accepted');
    }
    const result = await fetchPage(policy, body.url);
    return send(response, 200, {
      status: 'ok', source_url: body.url, final_url: result.finalUrl,
      title: result.title, text: result.text, content_type: result.contentType,
      bytes_received: result.bytesReceived, content_untrusted: true,
      scripts_stripped: true, hidden_text_stripped: true, forms_submitted: false,
      downloads_saved: false, cookies_used: false, model_direct_access: false,
      external_activity: true,
    });
  } catch (error) {
    return send(response, 400, {status: 'rejected', message: String(error.message || error)});
  } finally {
    activeRequests -= 1;
  }
});

server.listen(3010, '0.0.0.0');
