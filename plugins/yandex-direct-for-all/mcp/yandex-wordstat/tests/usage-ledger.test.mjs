import { afterEach, describe, expect, test } from 'bun:test';
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { WordstatUsageLedger } from '../src/usage-ledger.mjs';

const roots = [];
afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'ydfall-wordstat-'));
  roots.push(root);
  return join(root, 'limits.json');
}

describe('persistent Wordstat usage ledger', () => {
  test('records billed and free calls without charging the regions tree', async () => {
    const statePath = await fixture();
    const ledger = new WordstatUsageLedger({ statePath, now: () => 10_000 });
    await ledger.reserve({ endpoint: '/v2/wordstat/topRequests', billed: true });
    await ledger.reserve({ endpoint: '/v2/wordstat/getRegionsTree', billed: false });
    expect(await ledger.snapshot()).toEqual({ requestsLastSecond: 2, billedLastHour: 1, costUnitsLastHour: 1 });
    const saved = JSON.parse(await readFile(statePath, 'utf8'));
    expect(saved.requests[1].costUnits).toBe(0);
    expect((await stat(statePath)).mode & 0o777).toBe(0o600);
  });

  test('shares the per-second limit across ledger instances', async () => {
    const statePath = await fixture();
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
});
