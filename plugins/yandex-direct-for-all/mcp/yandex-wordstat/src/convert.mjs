import { mkdir, open, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';

// Conversion and persistent quota helpers for the Yandex Wordstat v2 API.
//
// The v2 REST gateway follows proto3 JSON encoding: int64 counts arrive as JSON
// *strings*, timestamps as RFC3339, and period/device/granularity as enum NAMES
// (PERIOD_*, DEVICE_*, REGION_*). These helpers translate between our friendly,
// ergonomic shapes and the wire format. They are side-effect free so they can be
// unit-tested without starting the server.

/** Convert a YYYY-MM-DD date to the RFC3339 timestamp the v2 API expects (UTC midnight). */
export function toRFC3339Date(date) {
  if (!date) return '';
  // Accept already-RFC3339 input unchanged.
  if (date.includes('T')) return date;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return date;
  return `${date}T00:00:00Z`;
}

/** Convert an RFC3339 timestamp from the v2 API back to YYYY-MM-DD. */
export function fromRFC3339Date(ts) {
  if (!ts) return '';
  const t = new Date(ts);
  if (Number.isNaN(t.getTime())) return ts;
  return t.toISOString().split('T')[0];
}

/** Canonicalize a period to daily/weekly/monthly. Accepts PERIOD_* enums and aliases. */
export function normalizePeriod(period) {
  switch (
    String(period ?? '')
      .trim()
      .toLowerCase()
  ) {
    case 'daily':
    case 'period_daily':
      return 'daily';
    case 'weekly':
    case 'period_weekly':
      return 'weekly';
    default: // monthly, period_monthly, empty, unknown
      return 'monthly';
  }
}

/** Map a period to the v2 Period enum. Accepts PERIOD_* enums and aliases. */
export function toYandexPeriod(period) {
  switch (
    String(period ?? '')
      .trim()
      .toLowerCase()
  ) {
    case 'daily':
    case 'period_daily':
      return 'PERIOD_DAILY';
    case 'weekly':
    case 'period_weekly':
      return 'PERIOD_WEEKLY';
    default:
      return 'PERIOD_MONTHLY';
  }
}

/**
 * Map device names (desktop/phone/tablet/all) to the v2 Device enum values.
 * Already-enum values (DEVICE_*) pass through. Unknown values are dropped so we
 * never send invalid enums.
 */
export function toYandexDevices(devices) {
  if (!devices?.length) return undefined;
  const out = [];
  for (const d of devices) {
    switch (String(d).trim().toLowerCase()) {
      case 'desktop':
      case 'device_desktop':
        out.push('DEVICE_DESKTOP');
        break;
      case 'phone':
      case 'mobile':
      case 'device_phone':
        out.push('DEVICE_PHONE');
        break;
      case 'tablet':
      case 'device_tablet':
        out.push('DEVICE_TABLET');
        break;
      case 'all':
      case 'device_all':
        out.push('DEVICE_ALL');
        break;
    }
  }
  return out.length ? out : undefined;
}

/**
 * Map the distribution granularity to the v2 Region enum, defaulting to the full
 * breakdown (REGION_ALL). Accepts the enum values and friendly aliases.
 */
export function toYandexRegionGranularity(region) {
  switch (
    String(region ?? '')
      .trim()
      .toLowerCase()
  ) {
    case 'cities':
    case 'region_cities':
      return 'REGION_CITIES';
    case 'regions':
    case 'region_regions':
      return 'REGION_REGIONS';
    default:
      return 'REGION_ALL';
  }
}

/** Convert int region IDs to the string IDs the v2 API expects. */
export function regionsToStrings(regions) {
  if (!regions?.length) return undefined;
  return regions.map((r) => String(r));
}

/**
 * Format a share percentage with precision adapted to its magnitude, trimming
 * trailing zeros. Regional shares are often tiny (e.g. 0.0123%), so a fixed two
 * decimals collapses them all to "0.01"; this keeps the significant digits.
 */
export function formatShare(share) {
  const n = Number(share);
  if (!n || Number.isNaN(n)) return '0';
  const abs = Math.abs(n);
  let decimals;
  if (abs >= 1) decimals = 2;
  else if (abs >= 0.01) decimals = 4;
  else decimals = 6;
  return Number(n.toFixed(decimals)).toString();
}

/** Parse a proto3-JSON count (quoted string or bare number) into a number; NaN -> 0. */
export function toInt(v) {
  if (v === null || v === undefined || v === '') return 0;
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

// Helpers for resolveDynamicsDates, operating on YYYY-MM-DD strings in UTC.
function fmt(d) {
  return d.toISOString().split('T')[0];
}

/**
 * Fill in any missing from/to dates with defaults that satisfy the v2 API's
 * period-specific alignment rules (verified against the live API):
 *   - monthly: from = first day of a month, to = last day of a month
 *   - weekly:  from = a Monday,             to = a Sunday
 *   - daily:   from within the last 60 days (exactly 60 is rejected), to = today
 * Dates supplied by the caller are passed through unchanged.
 * `now` is injectable for testing.
 */
export function resolveDynamicsDates(period, fromDate, toDate, now = new Date()) {
  const n = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  let from = fromDate || '';
  let to = toDate || '';

  if (!to) {
    if (period === 'weekly') {
      // Most recent Sunday (or today if Sunday). JS getUTCDay: Sunday == 0.
      const d = new Date(n);
      d.setUTCDate(d.getUTCDate() - d.getUTCDay());
      to = fmt(d);
    } else if (period === 'daily') {
      to = fmt(n);
    } else {
      // monthly: last day of the previous month.
      const d = new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), 1));
      d.setUTCDate(0); // day 0 -> last day of previous month
      to = fmt(d);
    }
  }

  if (!from) {
    if (period === 'daily') {
      // Must be within the last 60 days; exactly 60 is rejected, so use 59.
      const d = new Date(n);
      d.setUTCDate(d.getUTCDate() - 59);
      from = fmt(d);
    } else if (period === 'weekly') {
      // A Monday 52 weeks before the (Sunday) toDate: Sunday - 363 days == Monday.
      const t = new Date(`${to}T00:00:00Z`);
      t.setUTCDate(t.getUTCDate() - 363);
      from = fmt(t);
    } else {
      // monthly: first day of the month, 12 months before toDate.
      const t = new Date(`${to}T00:00:00Z`);
      from = fmt(new Date(Date.UTC(t.getUTCFullYear() - 1, t.getUTCMonth(), 1)));
    }
  }

  return { fromDate: from, toDate: to };
}

/** Compute a human-readable trend from dynamics points (first vs last count). */
export function calculateTrend(points) {
  if (!points || points.length < 2) return 'stable';
  const first = points[0].count;
  const last = points[points.length - 1].count;
  if (first === 0) return last > 0 ? 'up (new)' : 'stable';
  const change = ((last - first) / first) * 100;
  if (change > 1) return `up ${change.toFixed(1)}%`;
  if (change < -1) return `down ${(-change).toFixed(1)}%`;
  return 'stable';
}

/**
 * Recursively flatten a v2 region tree (nodes shaped {id, label, children}) into a
 * Map<regionId:number, {label, parentId}> for O(1) name lookups.
 */
export function flattenRegionsTree(nodes, parentId, map) {
  if (!nodes) return map;
  for (const node of nodes) {
    const id = Number(node.id);
    map.set(id, { label: node.label, parentId });
    if (node.children) {
      flattenRegionsTree(node.children, id, map);
    }
  }
  return map;
}

const SECOND_MS = 1000;
const HOUR_MS = 60 * 60 * 1000;

function defaultStatePath() {
  const root = process.env.YDFALL_STATE_ROOT || join(homedir(), '.local', 'state', 'yandex-direct-for-all');
  return join(root, 'wordstat', 'limits.json');
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function processIsAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === 'ESRCH') return false;
    if (error.code === 'EPERM') return true;
    throw error;
  }
}

function processIdentity(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return null;
  if (process.platform === 'linux') {
    try {
      const stat = readFileSync(`/proc/${pid}/stat`, 'utf8');
      const commandEnd = stat.lastIndexOf(')');
      const fields = stat.slice(commandEnd + 2).trim().split(/\s+/);
      const startTicks = fields[19];
      if (commandEnd >= 0 && /^\d+$/.test(startTicks || '')) return `linux:${startTicks}`;
    } catch (error) {
      if (error.code === 'ENOENT' || error.code === 'ESRCH') return null;
    }
  }
  try {
    const started = execFileSync('/bin/ps', ['-o', 'lstart=', '-p', String(pid)], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    return started ? `${process.platform}:${started}` : null;
  } catch {
    return null;
  }
}

export class WordstatUsageLedger {
  constructor({
    statePath = defaultStatePath(),
    now = () => Date.now(),
    sleep = delay,
    isProcessAlive = processIsAlive,
    getProcessIdentity = processIdentity,
  } = {}) {
    this.statePath = statePath;
    this.lockPath = `${statePath}.lock`;
    this.now = now;
    this.sleep = sleep;
    this.isProcessAlive = isProcessAlive;
    this.getProcessIdentity = getProcessIdentity;
  }

  async reserve({ endpoint, billed }) {
    for (;;) {
      await this.#lock();
      let waitMs = 0;
      try {
        const now = this.now();
        const state = await this.#read();
        state.requests = state.requests.filter((item) => item.at > now - HOUR_MS);
        const recent = state.requests.filter((item) => item.at > now - SECOND_MS);
        if (recent.length >= 10) {
          waitMs = Math.max(waitMs, recent[0].at + SECOND_MS - now + 1);
        }
        if (state.requests.length >= 100) {
          waitMs = Math.max(waitMs, state.requests[0].at + HOUR_MS - now + 1);
        }
        if (waitMs === 0) {
          state.requests.push({ at: now, endpoint, billed: Boolean(billed), costUnits: billed ? 1 : 0 });
          await this.#write(state);
          return;
        }
      } finally {
        await rm(this.lockPath, { recursive: true, force: true });
      }
      await this.sleep(waitMs);
    }
  }

  async snapshot() {
    await this.#lock();
    try {
      const now = this.now();
      const state = await this.#read();
      const requests = state.requests.filter((item) => item.at > now - HOUR_MS);
      return {
        requestsLastSecond: requests.filter((item) => item.at > now - SECOND_MS).length,
        requestsLastHour: requests.length,
        billedLastHour: requests.filter((item) => item.billed).length,
        costUnitsLastHour: requests.reduce((sum, item) => sum + (item.costUnits || 0), 0),
      };
    } finally {
      await rm(this.lockPath, { recursive: true, force: true });
    }
  }

  async #lock() {
    await mkdir(dirname(this.statePath), { recursive: true, mode: 0o700 });
    const selfIdentity = this.getProcessIdentity(process.pid);
    if (!selfIdentity) throw new Error('Не удалось определить идентичность процесса для блокировки квоты Wordstat');
    for (;;) {
      let handle;
      try {
        handle = await open(this.lockPath, 'wx', 0o600);
        await handle.writeFile(`${JSON.stringify({ version: 2, pid: process.pid, processIdentity: selfIdentity, acquiredAt: new Date().toISOString() })}\n`);
        await handle.sync();
        await handle.close();
        return;
      } catch (error) {
        await handle?.close().catch(() => {});
        if (error.code !== 'EEXIST') throw error;
        let owner;
        try {
          owner = JSON.parse(await readFile(this.lockPath, 'utf8'));
        } catch (ownerError) {
          if (ownerError.code === 'ENOENT') continue;
          throw new Error(`Блокировка квоты Wordstat повреждена: ${ownerError.message}`);
        }
        if (!Number.isInteger(owner.pid) || owner.pid <= 0) {
          throw new Error('Блокировка квоты Wordstat повреждена: отсутствует владелец процесса');
        }
        if (typeof owner.processIdentity !== 'string' || !owner.processIdentity) {
          throw new Error('Блокировка квоты Wordstat повреждена: отсутствует идентичность запуска процесса');
        }
        let ownerAlive = this.isProcessAlive(owner.pid);
        const liveIdentity = ownerAlive ? this.getProcessIdentity(owner.pid) : null;
        if (ownerAlive && !liveIdentity) {
          ownerAlive = this.isProcessAlive(owner.pid);
          if (ownerAlive) throw new Error('Не удалось проверить идентичность владельца блокировки квоты Wordstat');
        }
        if (!ownerAlive || liveIdentity !== owner.processIdentity) {
          const stalePath = `${this.lockPath}.stale-${process.pid}-${Math.random().toString(16).slice(2)}`;
          try {
            await rename(this.lockPath, stalePath);
          } catch (renameError) {
            if (renameError.code === 'ENOENT') continue;
            throw renameError;
          }
          await rm(stalePath, { force: true });
          continue;
        }
        await this.sleep(25);
      }
    }
  }

  async #read() {
    try {
      const parsed = JSON.parse(await readFile(this.statePath, 'utf8'));
      return Array.isArray(parsed.requests) ? parsed : { version: 1, requests: [] };
    } catch (error) {
      if (error.code === 'ENOENT') return { version: 1, requests: [] };
      throw error;
    }
  }

  async #write(state) {
    const temporary = `${this.statePath}.tmp-${process.pid}-${Math.random().toString(16).slice(2)}`;
    await writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
    await rename(temporary, this.statePath);
    const handle = await open(this.statePath, 'r');
    await handle.chmod(0o600);
    await handle.close();
  }
}
