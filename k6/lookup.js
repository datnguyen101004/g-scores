import http from 'k6/http';
import { sleep, check } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Rate } from 'k6/metrics';

const REQUEST_NAME = '/api/students/:sbd';
const SCORE_FIELD = 'toan';
const DEFAULT_SBD_FILE = '/opt/g-scores-load-test/sbds.json';
const REQUEST_TIMEOUT = '60s';
const MAX_DURATION = '30m';
const SETUP_TIMEOUT = '5m';
const GRACEFUL_STOP = '90s';



function requiredText(value, name) {
  const text = String(value || '').trim();
  if (!text) {
    throw new Error(`${name} is required`);
  }
  return text;
}

function positiveInteger(value, name) {
  const text = requiredText(value, name);
  if (!/^[1-9]\d*$/.test(text)) {
    throw new Error(`${name} must be a positive integer`);
  }
  return Number(text);
}

function normalizeBaseUrl(value) {
  const baseUrl = requiredText(value, 'BASE_URL').replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(baseUrl)) {
    throw new Error('BASE_URL must begin with http:// or https://');
  }
  return baseUrl;
}
function nonnegativeSeconds(value, name) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) {
    throw new Error(`${name} must be a non-negative number`);
  }
  return seconds;
}

const VUS = positiveInteger(__ENV.VUS || '10000', 'VUS');
const BASE_URL = normalizeBaseUrl(__ENV.BASE_URL);
const SBD_FILE = __ENV.SBD_FILE || DEFAULT_SBD_FILE;
const SUMMARY_FILE = requiredText(__ENV.SUMMARY_FILE, 'SUMMARY_FILE');
const BARRIER_SECONDS = nonnegativeSeconds(__ENV.BARRIER_SECONDS || '20', 'BARRIER_SECONDS');
const RUN_TOKEN = String(__ENV.RUN_ID || `local-${Date.now()}`);
const STARTED_AT_UTC = new Date().toISOString();

const sbds = new SharedArray('lookup-sbds', () => {
  let parsed;
  try {
    parsed = JSON.parse(open(SBD_FILE));
  } catch (error) {
    throw new Error(`Unable to parse SBD file ${SBD_FILE}: ${error}`);
  }

  if (!Array.isArray(parsed) || parsed.length < VUS) {
    throw new Error(`SBD file ${SBD_FILE} must contain at least ${VUS} entries for unique per-VU lookup`);
  }

  const validated = parsed.map((sbd, index) => {
    if (typeof sbd !== 'string' || !/^\d{8}$/.test(sbd)) {
      throw new Error(`SBD at index ${index} must be an 8-digit string`);
    }
    return sbd;
  });
  if (new Set(validated.slice(0, VUS)).size !== VUS) {
    throw new Error(`The first ${VUS} SBD entries must be unique`);
  }
  return validated;
});

const lookupErrors = new Rate('lookup_errors');
const cacheHit = new Rate('cache_hit');
const responses = {
  0: new Counter('response_network_error'),
  200: new Counter('response_200'),
  429: new Counter('response_429'),
  500: new Counter('response_500'),
  502: new Counter('response_502'),
  503: new Counter('response_503'),
  504: new Counter('response_504'),
};
const otherResponses = new Counter('response_other');
const semanticErrors = new Counter('response_semantic_error');

export const options = {
  scenarios: {
    lookup: {
      executor: 'per-vu-iterations',
      vus: VUS,
      iterations: 1,
      maxDuration: MAX_DURATION,
      gracefulStop: GRACEFUL_STOP,
    },
  },
  setupTimeout: SETUP_TIMEOUT,
  insecureSkipTLSVerify: false,
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  // Deliberately omit the raw URL system tag: nonce values are unique per request.
  systemTags: [
    'proto',
    'subproto',
    'status',
    'method',
    'name',
    'group',
    'check',
    'error',
    'error_code',
    'tls_version',
    'scenario',
    'service',
    'expected_response',
  ],
};

const requestParams = {
  headers: {
    'Cache-Control': 'no-cache',
  },
  tags: {
    name: REQUEST_NAME,
  },
  responseType: 'text',
  timeout: REQUEST_TIMEOUT,
  redirects: 0,
};

function selectedSbd(vu) {
  return sbds[vu - 1];
}

function responseHasExpectedData(response, expectedSbd) {
  if (!response || response.status !== 200 || typeof response.body !== 'string') {
    return false;
  }

  let payload;
  try {
    payload = JSON.parse(response.body);
  } catch (_) {
    return false;
  }

  if (!payload || typeof payload !== 'object' || payload.statusCode !== 200) {
    return false;
  }

  const data = payload.data;
  return data !== null
    && typeof data === 'object'
    && !Array.isArray(data)
    && data.sbd === expectedSbd
    && Object.prototype.hasOwnProperty.call(data, SCORE_FIELD);
}

function headerValue(headers, expectedName) {
  if (!headers) {
    return '';
  }

  const expectedLower = expectedName.toLowerCase();
  for (const name in headers) {
    if (name.toLowerCase() === expectedLower) {
      return String(headers[name]);
    }
  }
  return '';
}

function isCloudFrontCacheHit(response) {
  return /hit from cloudfront/i.test(headerValue(response && response.headers, 'x-cache'));
}

export function setup() {
  return { barrierAtMs: Date.now() + BARRIER_SECONDS * 1000 };
}

function csvField(value) {
  const text = value === undefined || value === null ? '' : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export default function (setupData) {
  const waitSeconds = Math.max(0, (setupData.barrierAtMs - Date.now()) / 1000);
  if (waitSeconds > 0) {
    sleep(waitSeconds);
  }

  const sbd = selectedSbd(__VU);
  const requestId = `vu-${__VU}`;
  const nonce = `${RUN_TOKEN}-${__VU}-${Date.now()}`;
  const url = `${BASE_URL}/api/students/${encodeURIComponent(sbd)}?nonce=${encodeURIComponent(nonce)}`;
  const startedMs = Date.now();
  let response = null;
  let correct = false;
  let errorCode = '';
  try {
    response = http.get(url, requestParams);
    correct = responseHasExpectedData(response, sbd);
    errorCode = response && response.error_code ? response.error_code : '';
  } catch (_) {
    errorCode = 'request_exception';
  }
  const finishedMs = Date.now();
  const status = response && Number.isFinite(response.status) ? response.status : 0;
  const hit = isCloudFrontCacheHit(response);
  console.log(`BURST_REQUEST,${[
    requestId,
    sbd,
    startedMs,
    finishedMs,
    status,
    correct,
    hit,
    errorCode,
  ].map(csvField).join(',')}`);

  (responses[status] || otherResponses).add(1);
  if (status === 200 && !correct) {
    semanticErrors.add(1);
  }
  lookupErrors.add(!correct, { name: REQUEST_NAME });
  cacheHit.add(hit, { name: REQUEST_NAME });
  check(response, {
    'lookup response is correct': () => correct,
  }, { name: REQUEST_NAME });
}

function normalizeMetrics(data) {
  if (data && data.metrics && typeof data.metrics === 'object' && !Array.isArray(data.metrics)) {
    return { format: 'legacy', metrics: data.metrics };
  }

  const machineMetrics = data && data.results && data.results.metrics;
  if (Array.isArray(machineMetrics)) {
    const metrics = {};
    machineMetrics.forEach((metric) => {
      if (metric && metric.name) {
        metrics[metric.name] = metric;
      }
    });
    return { format: 'machine-readable', metrics };
  }

  return { format: 'unknown', metrics: {} };
}

function metricValues(metrics, name) {
  const metric = metrics[name];
  return metric && metric.values ? metric.values : {};
}

function formatNumber(value, digits) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'n/a';
}

function formatRate(value) {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : 'n/a';
}

export function handleSummary(data) {
  const finishedAtUtc = new Date().toISOString();
  const normalized = normalizeMetrics(data);
  const duration = metricValues(normalized.metrics, 'http_req_duration');
  const errors = metricValues(normalized.metrics, 'lookup_errors');
  const cache = metricValues(normalized.metrics, 'cache_hit');
  const summary = {
    schemaVersion: 'g-scores-lookup-summary/v2',
    startedAtUtc: STARTED_AT_UTC,
    finishedAtUtc,
    config: {
      runToken: RUN_TOKEN,
      baseUrl: BASE_URL,
      vus: VUS,
      iterationsPerVu: 1,
      barrierSeconds: BARRIER_SECONDS,
      maxDuration: MAX_DURATION,
      requestTimeout: REQUEST_TIMEOUT,
      gracefulStop: GRACEFUL_STOP,
      sbdFile: SBD_FILE,
      sbdCount: sbds.length,
      requestName: REQUEST_NAME,
      nonceQueryParameter: 'nonce',
      cacheControl: 'no-cache',
      tlsValidation: true,
    },
    k6SummaryFormat: normalized.format,
    metrics: normalized.metrics,
    k6Summary: data,
  };
  const stdout = [
    'lookup complete:',
    `p95=${formatNumber(duration['p(95)'], 2)}ms`,
    `errors=${formatRate(errors.rate)}`,
    `cache_hit=${formatRate(cache.rate)}`,
    `summary=${SUMMARY_FILE}`,
  ].join(' ');

  return {
    [SUMMARY_FILE]: JSON.stringify(summary, null, 2),
    stdout: `${stdout}\n`,
  };
}
