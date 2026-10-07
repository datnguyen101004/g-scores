import http from 'k6/http';
import exec from 'k6/execution';
import { SharedArray } from 'k6/data';
import { Counter, Gauge, Rate } from 'k6/metrics';

const REQUEST_NAME = '/api/students/:sbd';
const SCORE_FIELD = 'toan';
const BASE_URL = requiredText(__ENV.BASE_URL, 'BASE_URL').replace(/\/+$/, '');
const SBD_FILE = __ENV.SBD_FILE || './sbds.json';
const SUMMARY_FILE = requiredText(__ENV.SUMMARY_FILE, 'SUMMARY_FILE');
const TARGET_RPS = positiveInteger(__ENV.TARGET_RPS, 'TARGET_RPS');
const DURATION_SECONDS = positiveInteger(__ENV.DURATION_SECONDS, 'DURATION_SECONDS');
const WARMUP_SECONDS = nonnegativeInteger(__ENV.WARMUP_SECONDS || '0', 'WARMUP_SECONDS');
const RAMP_UP_SECONDS = nonnegativeInteger(__ENV.RAMP_UP_SECONDS || '0', 'RAMP_UP_SECONDS');
const START_RPS = positiveInteger(__ENV.START_RPS || String(TARGET_RPS), 'START_RPS');
const RAMP_DOWN_SECONDS = nonnegativeInteger(__ENV.RAMP_DOWN_SECONDS || '0', 'RAMP_DOWN_SECONDS');
const PREALLOCATED_VUS = positiveInteger(__ENV.PREALLOCATED_VUS, 'PREALLOCATED_VUS');
const MAX_VUS = positiveInteger(__ENV.MAX_VUS, 'MAX_VUS');
const TIMEOUT_SECONDS = positiveInteger(__ENV.TIMEOUT_SECONDS, 'TIMEOUT_SECONDS');
const REQUEST_TIMEOUT = `${TIMEOUT_SECONDS}s`;
const GRACEFUL_STOP = `${TIMEOUT_SECONDS + 5}s`;
const HAS_RAMP_PROFILE = RAMP_UP_SECONDS > 0 || RAMP_DOWN_SECONDS > 0;


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

function nonnegativeInteger(value, name) {
  const text = String(value);
  if (!/^\d+$/.test(text)) {
    throw new Error(`${name} must be a non-negative integer`);
  }
  return Number(text);
}

if (!/^https?:\/\//i.test(BASE_URL)) {
  throw new Error('BASE_URL must begin with http:// or https://');
}
if (PREALLOCATED_VUS > MAX_VUS) {
  throw new Error('PREALLOCATED_VUS must not exceed MAX_VUS');
}

const sbds = new SharedArray('lookup-sbds', () => {
  let parsed;
  try {
    parsed = JSON.parse(open(SBD_FILE));
  } catch (error) {
    throw new Error(`Unable to parse SBD file ${SBD_FILE}: ${error}`);
  }
  if (!Array.isArray(parsed) || parsed.length === 0) {
    throw new Error(`SBD file ${SBD_FILE} must contain at least one SBD`);
  }
  parsed.forEach((sbd, index) => {
    if (typeof sbd !== 'string' || !/^\d{8}$/.test(sbd)) {
      throw new Error(`SBD at index ${index} must be an 8-digit string`);
    }
  });
  return parsed;
});

const lookupErrors = new Rate('lookup_errors');
const lookupSuccess = new Counter('lookup_success');
const lookupStarted = new Counter('lookup_started');
const measurementWindowStart = new Gauge('measurement_window_start');

const scenarios = {};
if (WARMUP_SECONDS > 0) {
  scenarios.warmup = {
    executor: 'constant-arrival-rate',
    tags: { phase: 'warmup', target_rps: String(TARGET_RPS) },
    rate: TARGET_RPS,
    timeUnit: '1s',
    duration: `${WARMUP_SECONDS}s`,
    preAllocatedVUs: PREALLOCATED_VUS,
    maxVUs: MAX_VUS,
    gracefulStop: '0s',
  };
}
if (HAS_RAMP_PROFILE) {
  const stages = [];
  if (RAMP_UP_SECONDS > 0) {
    stages.push({ duration: `${RAMP_UP_SECONDS}s`, target: TARGET_RPS });
  }
  stages.push({ duration: `${DURATION_SECONDS}s`, target: TARGET_RPS });
  if (RAMP_DOWN_SECONDS > 0) {
    stages.push({ duration: `${RAMP_DOWN_SECONDS}s`, target: 0 });
  }
  scenarios.profile = {
    executor: 'ramping-arrival-rate',
    startTime: `${WARMUP_SECONDS}s`,
    startRate: RAMP_UP_SECONDS > 0 ? START_RPS : TARGET_RPS,
    timeUnit: '1s',
    stages,
    tags: { target_rps: String(TARGET_RPS) },
    preAllocatedVUs: PREALLOCATED_VUS,
    maxVUs: MAX_VUS,
    gracefulStop: GRACEFUL_STOP,
  };
} else {
  scenarios.measurement = {
    executor: 'constant-arrival-rate',
    startTime: `${WARMUP_SECONDS}s`,
    tags: { phase: 'measurement', target_rps: String(TARGET_RPS) },
    rate: TARGET_RPS,
    timeUnit: '1s',
    duration: `${DURATION_SECONDS}s`,
    preAllocatedVUs: PREALLOCATED_VUS,
    maxVUs: MAX_VUS,
    gracefulStop: GRACEFUL_STOP,
  };
}

export const options = {
  scenarios,
  thresholds: {
    'http_req_duration{phase:measurement}': ['p(95)<500', 'p(99)<1000'],
    'lookup_errors{phase:measurement}': ['rate<0.01'],
  },
  insecureSkipTLSVerify: false,
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  // Omit the raw URL system tag: SBD values must not create high-cardinality series.
  systemTags: [
    'proto', 'subproto', 'status', 'method', 'name', 'group', 'check', 'error',
    'error_code', 'tls_version', 'scenario', 'service', 'expected_response',
  ],
};

const requestParams = {
  responseType: 'text',
  timeout: REQUEST_TIMEOUT,
  redirects: 0,
};

function responseIsCorrect(response, expectedSbd) {
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

function phaseForIteration() {
  if (!HAS_RAMP_PROFILE) {
    return exec.scenario.name;
  }
  const elapsedMilliseconds = Math.max(0, Date.now() - exec.scenario.startTime);
  const rampUpMilliseconds = RAMP_UP_SECONDS * 1000;
  const measurementMilliseconds = DURATION_SECONDS * 1000;
  if (elapsedMilliseconds < rampUpMilliseconds) {
    return 'ramp_up';
  }
  if (elapsedMilliseconds < rampUpMilliseconds + measurementMilliseconds) {
    return 'measurement';
  }
  return 'ramp_down';
}

export default function () {
  const profile = HAS_RAMP_PROFILE && exec.scenario.name === 'profile';
  const phase = phaseForIteration();
  const measurement = phase === 'measurement';
  const tags = { name: REQUEST_NAME, phase, target_rps: String(TARGET_RPS) };
  const sbd = sbds[exec.scenario.iterationInTest % sbds.length];
  const url = `${BASE_URL}/api/students/${encodeURIComponent(sbd)}`;

  if ((profile || exec.scenario.name === 'measurement') && exec.scenario.iterationInInstance === 0) {
    const measurementStart = profile
      ? exec.scenario.startTime + RAMP_UP_SECONDS * 1000
      : exec.scenario.startTime;
    measurementWindowStart.add(measurementStart, {
      phase: 'measurement',
      target_rps: String(TARGET_RPS),
    });
  }

  if (measurement) {
    lookupStarted.add(1, tags);
  }

  let response = null;
  try {
    response = http.get(url, { ...requestParams, tags });
  } catch (_) {
    // A thrown request is a network failure and is counted below for measurement.
  }
  const correct = responseIsCorrect(response, sbd);

  if (measurement) {
    lookupErrors.add(correct ? 0 : 1, tags);
    lookupSuccess.add(correct ? 1 : 0, tags);
  }
}

export function handleSummary(data) {
  return { [SUMMARY_FILE]: `${JSON.stringify(data, null, 2)}\n` };
}
