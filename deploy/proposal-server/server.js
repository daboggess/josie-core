'use strict';

const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');

const port = 3030;
const proposalRoot = '/proposals';
const tokenPath = '/run/secrets/proposal_token';
const inbox = path.join(proposalRoot, 'inbox');
const dedupePath = path.join(proposalRoot, 'dedupe-state.json');
const allowedKinds = new Set(['health_check', 'memory_export', 'restore_drill']);
const maxBodyBytes = 8192;
const maxSummaryCharacters = 1000;
const maxInboxFiles = 1000;
const rateWindowMs = 60_000;
const rateLimit = 3;
const dedupeWindowMs = 5 * 60_000;
const maxDedupeEntries = 100;
const recentWrites = [];

function loadDedupeEntries() {
  try {
    const parsed = JSON.parse(fs.readFileSync(dedupePath, 'utf8'));
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(entry => entry && typeof entry === 'object'
      && typeof entry.fingerprint === 'string'
      && typeof entry.external_id === 'string'
      && typeof entry.kind === 'string'
      && Number.isFinite(entry.recorded_at));
  } catch (_error) {
    return [];
  }
}

let dedupeEntries = loadDedupeEntries();
let dedupePersistenceHealthy = true;

function saveDedupeEntries() {
  fs.mkdirSync(proposalRoot, {recursive: true});
  const temporary = path.join(proposalRoot, `dedupe-${crypto.randomUUID()}.tmp`);
  fs.writeFileSync(temporary, JSON.stringify(dedupeEntries, null, 2), {encoding: 'utf8', flag: 'wx'});
  fs.renameSync(temporary, dedupePath);
}

function proposalFingerprint(kind, summary) {
  return crypto.createHash('sha256').update(`${kind}\u0000${summary}`, 'utf8').digest('hex');
}

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
    version: '1.1.0',
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
        description: 'Records only. Never queues or executes a tool, command, message, or transaction. After success, report only assistant_message and add no claims.',
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
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  additionalProperties: false,
                  required: ['status', 'proposal_id', 'kind', 'actions_queued', 'actions_executed', 'duplicate', 'assistant_message'],
                  properties: {
                    status: {type: 'string', const: 'review_required'},
                    proposal_id: {type: 'string'},
                    kind: {type: 'string', enum: Array.from(allowedKinds)},
                    actions_queued: {type: 'integer', const: 0},
                    actions_executed: {type: 'integer', const: 0},
                    duplicate: {type: 'boolean'},
                    assistant_message: {type: 'string'},
                  },
                },
              },
            },
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
  const fingerprint = proposalFingerprint(input.kind, summary);
  dedupeEntries = dedupeEntries.filter(entry => entry.recorded_at > now - dedupeWindowMs);
  const existing = dedupeEntries.find(entry => entry.fingerprint === fingerprint);
  if (existing) {
    return {
      proposal: {
        external_id: existing.external_id,
        kind: existing.kind,
        status: 'review_required',
        actions_queued: 0,
        actions_executed: 0,
      },
      duplicate: true,
    };
  }
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
  dedupeEntries.push({fingerprint, external_id: externalId, kind: input.kind, recorded_at: now});
  dedupeEntries = dedupeEntries.slice(-maxDedupeEntries);
  try {
    saveDedupeEntries();
    dedupePersistenceHealthy = true;
  } catch (_error) {
    dedupePersistenceHealthy = false;
  }
  return {proposal, duplicate: false};
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
      duplicate_suppression: true,
      dedupe_window_seconds: dedupeWindowMs / 1000,
      dedupe_persistence_healthy: dedupePersistenceHealthy,
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
      const result = recordProposal(await readJsonBody(request));
      const proposal = result.proposal;
      const assistantMessage = result.duplicate
        ? `No action was performed. An identical ${proposal.kind} proposal was already recorded for human review. No duplicate record was created. Actions queued: 0. Actions executed: 0.`
        : `No action was performed. A ${proposal.kind} proposal was recorded for human review. Status: review_required. Actions queued: 0. Actions executed: 0.`;
      send(response, 201, {
        status: 'review_required',
        proposal_id: proposal.external_id,
        kind: proposal.kind,
        actions_queued: 0,
        actions_executed: 0,
        duplicate: result.duplicate,
        assistant_message: assistantMessage,
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
  const selfTestSummary = `Container self-test ${crypto.randomUUID()}`;
  const first = recordProposal({kind: 'health_check', summary: selfTestSummary});
  const second = recordProposal({kind: 'health_check', summary: selfTestSummary});
  process.stdout.write(JSON.stringify({
    status: 'ok',
    proposal_id: first.proposal.external_id,
    actions_executed: first.proposal.actions_executed,
    duplicate_suppression: second.duplicate,
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
