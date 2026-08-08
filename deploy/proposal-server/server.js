'use strict';

const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');

const port = 3030;
const proposalRoot = '/proposals';
const tokenPath = '/run/secrets/proposal_token';
const inbox = path.join(proposalRoot, 'inbox');
const allowedKinds = new Set(['health_check', 'memory_export', 'restore_drill']);
const maxBodyBytes = 8192;
const maxSummaryCharacters = 1000;
const maxInboxFiles = 1000;
const rateWindowMs = 60_000;
const rateLimit = 3;
const recentWrites = [];

function loadBearerToken() {
  const token = fs.readFileSync(tokenPath, 'utf8').trim();
  if (token.length < 32 || token.length > 256) {
    throw new Error('Proposal bearer token must contain 32 to 256 characters');
  }
  return token;
}

const bearerToken = process.argv.includes('--self-test')
  ? 'self-test-token-that-is-never-used-in-service-mode'
  : loadBearerToken();

const openapi = {
  openapi: '3.1.0',
  info: {
    title: 'Josie Core Review Proposals',
    version: '1.0.0',
    description: 'Records bounded local proposals for human review. It never executes actions.',
  },
  servers: [{url: 'http://proposal-server:3030'}],
  components: {
    securitySchemes: {
      bearerAuth: {type: 'http', scheme: 'bearer'},
    },
  },
  paths: {
    '/v1/proposals': {
      post: {
        operationId: 'record_review_proposal',
        summary: 'Record a local proposal for human review',
        description: 'Records only. Never queues or executes a tool, command, message, or transaction.',
        security: [{bearerAuth: []}],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: {
                type: 'object',
                additionalProperties: false,
                required: ['kind', 'summary'],
                properties: {
                  kind: {type: 'string', enum: Array.from(allowedKinds)},
                  summary: {type: 'string', minLength: 1, maxLength: maxSummaryCharacters},
                },
              },
            },
          },
        },
        responses: {
          201: {
            description: 'Review-only proposal recorded',
            content: {'application/json': {schema: {type: 'object'}}},
          },
          400: {description: 'Invalid bounded proposal'},
          401: {description: 'Missing or invalid local bearer token'},
          429: {description: 'Local rate limit reached'},
          507: {description: 'Review inbox capacity reached'},
        },
      },
    },
  },
};

function isAuthorized(request) {
  const header = request.headers.authorization;
  if (typeof header !== 'string' || !header.startsWith('Bearer ')) return false;
  const supplied = Buffer.from(header.slice('Bearer '.length), 'utf8');
  const expected = Buffer.from(bearerToken, 'utf8');
  return supplied.length === expected.length && crypto.timingSafeEqual(supplied, expected);
}

function send(response, statusCode, body) {
  const rendered = JSON.stringify(body);
  response.writeHead(statusCode, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(rendered),
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  response.end(rendered);
}

function recordProposal(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new Error('Request body must be an object');
  }
  if (Object.keys(input).sort().join(',') !== 'kind,summary') {
    throw new Error('Only kind and summary are accepted');
  }
  if (!allowedKinds.has(input.kind)) {
    throw new Error('Proposal kind is not allowlisted');
  }
  if (typeof input.summary !== 'string') {
    throw new Error('Summary must be text');
  }
  const summary = input.summary.trim();
  if (!summary || summary.length > maxSummaryCharacters) {
    throw new Error('Summary must contain 1 to 1000 characters');
  }

  const now = Date.now();
  while (recentWrites.length && recentWrites[0] <= now - rateWindowMs) recentWrites.shift();
  if (recentWrites.length >= rateLimit) {
    const error = new Error('Local proposal rate limit reached');
    error.statusCode = 429;
    throw error;
  }
  fs.mkdirSync(inbox, {recursive: true});
  const inboxCount = fs.readdirSync(inbox).filter(name => name.endsWith('.json')).length;
  if (inboxCount >= maxInboxFiles) {
    const error = new Error('Review inbox capacity reached');
    error.statusCode = 507;
    throw error;
  }

  const externalId = crypto.randomUUID();
  const proposal = {
    schema_version: 1,
    external_id: externalId,
    created_at: new Date().toISOString(),
    source: 'openwebui',
    kind: input.kind,
    summary,
    status: 'review_required',
    actions_queued: 0,
    actions_executed: 0,
    model_parameters_accepted: false,
    cloud_activity: false,
  };
  const temporary = path.join(inbox, `${externalId}.tmp`);
  const destination = path.join(inbox, `${externalId}.json`);
  fs.writeFileSync(temporary, JSON.stringify(proposal, null, 2), {encoding: 'utf8', flag: 'wx'});
  fs.renameSync(temporary, destination);
  recentWrites.push(now);
  return proposal;
}

function readJsonBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    request.on('data', chunk => {
      size += chunk.length;
      if (size > maxBodyBytes) {
        reject(new Error('Request body exceeds 8192 bytes'));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on('end', () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      } catch (_error) {
        reject(new Error('Request body is not valid JSON'));
      }
    });
    request.on('error', reject);
  });
}

async function handle(request, response) {
  if (request.method === 'GET' && request.url === '/health') {
    fs.mkdirSync(inbox, {recursive: true});
    const inboxCount = fs.readdirSync(inbox).filter(name => name.endsWith('.json')).length;
    send(response, 200, {
      status: 'ok',
      execution: false,
      allowed_kinds: Array.from(allowedKinds),
      inbox_count: inboxCount,
      inbox_limit: maxInboxFiles,
    });
    return;
  }
  if (request.method === 'GET' && request.url === '/openapi.json') {
    send(response, 200, openapi);
    return;
  }
  if (request.method === 'POST' && request.url === '/v1/proposals') {
    if (!isAuthorized(request)) {
      send(response, 401, {
        status: 'rejected',
        message: 'Missing or invalid local bearer token',
        actions_queued: 0,
        actions_executed: 0,
      });
      return;
    }
    try {
      const proposal = recordProposal(await readJsonBody(request));
      send(response, 201, {
        status: 'review_required',
        proposal_id: proposal.external_id,
        kind: proposal.kind,
        actions_queued: 0,
        actions_executed: 0,
      });
    } catch (error) {
      send(response, error.statusCode || 400, {
        status: 'rejected',
        message: error.message,
        actions_queued: 0,
        actions_executed: 0,
      });
    }
    return;
  }
  send(response, 404, {status: 'not_found'});
}

if (process.argv.includes('--self-test')) {
  const authorized = isAuthorized({headers: {authorization: `Bearer ${bearerToken}`}});
  const wrongTokenRejected = !isAuthorized({headers: {authorization: 'Bearer wrong-token'}});
  if (!authorized || !wrongTokenRejected) throw new Error('Bearer authentication self-test failed');
  const proposal = recordProposal({kind: 'health_check', summary: 'Container self-test'});
  process.stdout.write(JSON.stringify({
    status: 'ok',
    proposal_id: proposal.external_id,
    actions_executed: proposal.actions_executed,
    bearer_authentication: 'verified',
    openapi_operation: openapi.paths['/v1/proposals'].post.operationId,
  }));
} else {
  http.createServer((request, response) => {
    handle(request, response).catch(() => {
      if (!response.headersSent) send(response, 500, {status: 'error'});
      else response.destroy();
    });
  }).listen(port, '0.0.0.0');
}
