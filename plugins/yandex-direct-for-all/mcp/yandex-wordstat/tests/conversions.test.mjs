import { afterEach, describe, expect, test } from 'bun:test';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  calculateTrend,
  flattenRegionsTree,
  formatShare,
  fromRFC3339Date,
  normalizePeriod,
  regionsToStrings,
  resolveDynamicsDates,
  toInt,
  toRFC3339Date,
  toYandexDevices,
  toYandexPeriod,
  toYandexRegionGranularity,
  WordstatUsageLedger,
} from '../src/convert.mjs';

const quotaRoots = [];
afterEach(async () => {
  await Promise.all(quotaRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function quotaFixture() {
  const root = await mkdtemp(join(tmpdir(), 'ydfall-wordstat-'));
  quotaRoots.push(root);
  return join(root, 'limits.json');
}

describe('date conversion', () => {
  test('toRFC3339Date converts YYYY-MM-DD to UTC midnight', () => {
    expect(toRFC3339Date('2025-04-30')).toBe('2025-04-30T00:00:00Z');
  });

  test('toRFC3339Date passes through empty and already-RFC3339', () => {
    expect(toRFC3339Date('')).toBe('');
    expect(toRFC3339Date('2025-04-30T00:00:00Z')).toBe('2025-04-30T00:00:00Z');
    expect(toRFC3339Date('not-a-date')).toBe('not-a-date');
  });

  test('fromRFC3339Date converts RFC3339 to YYYY-MM-DD', () => {
    expect(fromRFC3339Date('2025-01-01T00:00:00Z')).toBe('2025-01-01');
  });

  test('fromRFC3339Date passes through empty and invalid', () => {
    expect(fromRFC3339Date('')).toBe('');
    expect(fromRFC3339Date('garbage')).toBe('garbage');
  });

  test('round-trips', () => {
    expect(fromRFC3339Date(toRFC3339Date('2024-12-25'))).toBe('2024-12-25');
  });
});

describe('enum mapping', () => {
  test('normalizePeriod', () => {
    expect(normalizePeriod('daily')).toBe('daily');
    expect(normalizePeriod('PERIOD_WEEKLY')).toBe('weekly');
    expect(normalizePeriod('')).toBe('monthly');
    expect(normalizePeriod(undefined)).toBe('monthly');
    expect(normalizePeriod('nonsense')).toBe('monthly');
  });

  test('toYandexPeriod', () => {
    expect(toYandexPeriod('daily')).toBe('PERIOD_DAILY');
    expect(toYandexPeriod('weekly')).toBe('PERIOD_WEEKLY');
    expect(toYandexPeriod('monthly')).toBe('PERIOD_MONTHLY');
    expect(toYandexPeriod('PERIOD_DAILY')).toBe('PERIOD_DAILY');
    expect(toYandexPeriod(undefined)).toBe('PERIOD_MONTHLY');
  });

  test('toYandexDevices maps aliases and drops unknowns', () => {
    expect(toYandexDevices(['desktop', 'phone', 'tablet'])).toEqual([
      'DEVICE_DESKTOP',
      'DEVICE_PHONE',
      'DEVICE_TABLET',
    ]);
    expect(toYandexDevices(['mobile', 'all'])).toEqual(['DEVICE_PHONE', 'DEVICE_ALL']);
    expect(toYandexDevices(['DEVICE_DESKTOP'])).toEqual(['DEVICE_DESKTOP']);
    expect(toYandexDevices(['unknown'])).toBeUndefined();
    expect(toYandexDevices([])).toBeUndefined();
    expect(toYandexDevices(undefined)).toBeUndefined();
  });

  test('toYandexRegionGranularity defaults to REGION_ALL', () => {
    expect(toYandexRegionGranularity('cities')).toBe('REGION_CITIES');
    expect(toYandexRegionGranularity('regions')).toBe('REGION_REGIONS');
    expect(toYandexRegionGranularity('all')).toBe('REGION_ALL');
    expect(toYandexRegionGranularity('REGION_CITIES')).toBe('REGION_CITIES');
    expect(toYandexRegionGranularity(undefined)).toBe('REGION_ALL');
  });
});

describe('regionsToStrings', () => {
  test('converts numbers to strings', () => {
    expect(regionsToStrings([213, 2])).toEqual(['213', '2']);
  });

  test('returns undefined for empty', () => {
    expect(regionsToStrings([])).toBeUndefined();
    expect(regionsToStrings(undefined)).toBeUndefined();
  });
});

describe('toInt (proto3 JSON int64)', () => {
  test('parses quoted strings', () => {
    expect(toInt('45230')).toBe(45230);
  });
  test('parses bare numbers', () => {
    expect(toInt(45230)).toBe(45230);
  });
  test('empty/null/garbage -> 0', () => {
    expect(toInt('')).toBe(0);
    expect(toInt(null)).toBe(0);
    expect(toInt(undefined)).toBe(0);
    expect(toInt('abc')).toBe(0);
  });
});

describe('formatShare (adaptive precision, trimmed zeros)', () => {
  test('keeps significant digits for tiny shares', () => {
    expect(formatShare(0.0123)).toBe('0.0123'); // would collapse to "0.01" with toFixed(2)
    expect(formatShare(0.000123)).toBe('0.000123');
  });
  test('two decimals for shares >= 1', () => {
    expect(formatShare(12.345)).toBe('12.35');
    expect(formatShare(5)).toBe('5');
  });
  test('trims trailing zeros', () => {
    expect(formatShare(0.01)).toBe('0.01');
    expect(formatShare(2.5)).toBe('2.5');
  });
  test('zero / invalid -> "0"', () => {
    expect(formatShare(0)).toBe('0');
    expect(formatShare(null)).toBe('0');
    expect(formatShare(undefined)).toBe('0');
  });
});

describe('resolveDynamicsDates', () => {
  // Fixed "now": Sunday 2026-06-07 (June 7 2026 is a Sunday).
  const now = new Date('2026-06-07T12:00:00Z');

  test('monthly: from=1st of month a year back, to=last day of prev month', () => {
    const { fromDate, toDate } = resolveDynamicsDates('monthly', '', '', now);
    expect(toDate).toBe('2026-05-31'); // last day of May
    expect(fromDate).toBe('2025-05-01'); // first day of month, 12 months before toDate
  });

  test('weekly: to=most recent Sunday, from=Monday 363 days earlier', () => {
    const { fromDate, toDate } = resolveDynamicsDates('weekly', '', '', now);
    expect(toDate).toBe('2026-06-07'); // now is Sunday
    expect(new Date(`${toDate}T00:00:00Z`).getUTCDay()).toBe(0); // Sunday
    expect(new Date(`${fromDate}T00:00:00Z`).getUTCDay()).toBe(1); // Monday
    expect(fromDate).toBe('2025-06-09');
  });

  test('daily: to=today, from=59 days back', () => {
    const { fromDate, toDate } = resolveDynamicsDates('daily', '', '', now);
    expect(toDate).toBe('2026-06-07');
    expect(fromDate).toBe('2026-04-09'); // 59 days before
    const span = (new Date(`${toDate}T00:00:00Z`) - new Date(`${fromDate}T00:00:00Z`)) / 86400000;
    expect(span).toBe(59);
  });

  test('caller-supplied dates pass through unchanged', () => {
    const { fromDate, toDate } = resolveDynamicsDates('monthly', '2024-01-01', '2024-12-31', now);
    expect(fromDate).toBe('2024-01-01');
    expect(toDate).toBe('2024-12-31');
  });
});

describe('calculateTrend', () => {
  test('up / down / stable', () => {
    expect(calculateTrend([{ count: 100 }, { count: 200 }])).toBe('up 100.0%');
    expect(calculateTrend([{ count: 200 }, { count: 100 }])).toBe('down 50.0%');
    expect(calculateTrend([{ count: 100 }, { count: 100 }])).toBe('stable');
    expect(calculateTrend([{ count: 0 }, { count: 50 }])).toBe('up (new)');
    expect(calculateTrend([{ count: 100 }])).toBe('stable');
    expect(calculateTrend([])).toBe('stable');
  });
});

describe('flattenRegionsTree (v2 {id,label,children} shape)', () => {
  test('flattens into a Map keyed by numeric region IDs', () => {
    const tree = [
      {
        id: '225',
        label: 'Россия',
        children: [
          { id: '1', label: 'Москва и область', children: [{ id: '213', label: 'Москва', children: null }] },
          { id: '2', label: 'Санкт-Петербург', children: null },
        ],
      },
    ];
    const map = flattenRegionsTree(tree, null, new Map());
    expect(map.size).toBe(4);
    expect(map.get(225)).toEqual({ label: 'Россия', parentId: null });
    expect(map.get(213)).toEqual({ label: 'Москва', parentId: 1 });
    expect(map.get(2)).toEqual({ label: 'Санкт-Петербург', parentId: 225 });
    // keys are numbers, not strings
    expect([...map.keys()].every((k) => typeof k === 'number')).toBe(true);
  });
});

describe('persistent Wordstat usage ledger', () => {
  test('records cost separately while counting every request per hour', async () => {
    const statePath = await quotaFixture();
    const ledger = new WordstatUsageLedger({ statePath, now: () => 10_000 });
    await ledger.reserve({ endpoint: '/v2/wordstat/topRequests', billed: true });
    await ledger.reserve({ endpoint: '/v2/wordstat/getRegionsTree', billed: false });
    expect(await ledger.snapshot()).toEqual({
      requestsLastSecond: 2,
      requestsLastHour: 2,
      billedLastHour: 1,
      costUnitsLastHour: 1,
    });
    const saved = JSON.parse(await readFile(statePath, 'utf8'));
    expect(saved.requests[1].costUnits).toBe(0);
    expect((await stat(statePath)).mode & 0o777).toBe(0o600);
  });

  test('shares the per-second limit across ledger instances', async () => {
    const statePath = await quotaFixture();
    let now = 20_000;
    const waits = [];
    const sleep = async (ms) => { waits.push(ms); now += ms; };
    for (let index = 0; index < 11; index += 1) {
      const ledger = new WordstatUsageLedger({ statePath, now: () => now, sleep });
      await ledger.reserve({ endpoint: '/v2/wordstat/regions', billed: true });
    }
    expect(waits.length).toBe(1);
    expect(waits[0]).toBeGreaterThanOrEqual(1000);
  });

  test('counts free regions-tree calls toward the total hourly limit', async () => {
    const statePath = await quotaFixture();
    let now = 100_000;
    const waits = [];
    const sleep = async (ms) => { waits.push(ms); now += ms; };
    const ledger = new WordstatUsageLedger({ statePath, now: () => now, sleep });
    for (let index = 0; index < 100; index += 1) {
      await ledger.reserve({ endpoint: '/v2/wordstat/getRegionsTree', billed: false });
      now += 1001;
    }
    await ledger.reserve({ endpoint: '/v2/wordstat/getRegionsTree', billed: false });
    expect(waits.length).toBe(1);
    expect(waits[0]).toBeGreaterThan(0);
    const snapshot = await ledger.snapshot();
    expect(snapshot.requestsLastHour).toBe(100);
    expect(snapshot.billedLastHour).toBe(0);
  });

  test('accepts the shared version-2 state written by the Python collector', async () => {
    const statePath = await quotaFixture();
    await writeFile(statePath, `${JSON.stringify({
      version: 2,
      requests: [{ at: 50_000, endpoint: 'wordstat-cloud-collector', billed: false, costUnits: 0 }],
      nextAllowedAt: 0,
    })}\n`, { mode: 0o600 });
    const ledger = new WordstatUsageLedger({ statePath, now: () => 50_100 });
    await ledger.reserve({ endpoint: '/v2/wordstat/topRequests', billed: true });
    expect((await ledger.snapshot()).requestsLastHour).toBe(2);
  });

  test('rejects valid JSON with a foreign state shape without rewriting it', async () => {
    const statePath = await quotaFixture();
    const original = '{"requestTimes":[],"billedTimes":[],"nextAllowedAt":0}\n';
    await writeFile(statePath, original, { mode: 0o600 });
    const ledger = new WordstatUsageLedger({ statePath });
    await expect(ledger.reserve({ endpoint: '/v2/wordstat/topRequests', billed: true })).rejects.toThrow(
      'Состояние квоты Wordstat повреждено',
    );
    expect(await readFile(statePath, 'utf8')).toBe(original);
  });

  test('honours a Retry-After deadline written by the Python collector', async () => {
    const statePath = await quotaFixture();
    await writeFile(statePath, `${JSON.stringify({ version: 2, requests: [], nextAllowedAt: 12_000 })}\n`, { mode: 0o600 });
    let now = 10_000;
    const waits = [];
    const ledger = new WordstatUsageLedger({
      statePath,
      now: () => now,
      sleep: async (ms) => { waits.push(ms); now += ms; },
    });
    await ledger.reserve({ endpoint: '/v2/wordstat/topRequests', billed: true });
    expect(waits).toEqual([2000]);
  });

  test('recovers an owner-recorded lock left by a dead process', async () => {
    const statePath = await quotaFixture();
    await writeFile(`${statePath}.lock`, `${JSON.stringify({ version: 2, pid: 999999, processIdentity: 'dead:1', acquiredAt: '2026-07-14T00:00:00Z' })}\n`, { mode: 0o600 });
    const checkedOwners = [];
    const ledger = new WordstatUsageLedger({
      statePath,
      now: () => 200_000,
      isProcessAlive: (pid) => { checkedOwners.push(pid); return false; },
    });
    await ledger.reserve({ endpoint: '/v2/wordstat/topRequests', billed: true });
    expect(checkedOwners).toEqual([999999]);
    expect((await ledger.snapshot()).requestsLastHour).toBe(1);
    await expect(stat(`${statePath}.lock`)).rejects.toMatchObject({ code: 'ENOENT' });
  });

  test('recovers a stale lock when the operating system reused the owner pid', async () => {
    const statePath = await quotaFixture();
    await writeFile(`${statePath}.lock`, `${JSON.stringify({ version: 2, pid: 4242, processIdentity: 'linux:old-start', acquiredAt: '2026-07-14T00:00:00Z' })}\n`, { mode: 0o600 });
    const waits = [];
    const ledger = new WordstatUsageLedger({
      statePath,
      isProcessAlive: () => true,
      getProcessIdentity: (pid) => pid === 4242 ? 'linux:new-start' : 'linux:self-start',
      sleep: async (ms) => waits.push(ms),
    });
    await ledger.reserve({ endpoint: '/v2/wordstat/topRequests', billed: true });
    expect(waits).toEqual([]);
    expect((await ledger.snapshot()).requestsLastHour).toBe(1);
  });

  test('rejects a corrupt lock instead of waiting forever', async () => {
    const statePath = await quotaFixture();
    await writeFile(`${statePath}.lock`, '{not-json\n', { mode: 0o600 });
    const waits = [];
    const ledger = new WordstatUsageLedger({ statePath, sleep: async (ms) => waits.push(ms) });
    await expect(ledger.reserve({ endpoint: '/v2/wordstat/topRequests', billed: true })).rejects.toThrow(
      'Блокировка квоты Wordstat повреждена',
    );
    expect(waits).toEqual([]);
  });
});
