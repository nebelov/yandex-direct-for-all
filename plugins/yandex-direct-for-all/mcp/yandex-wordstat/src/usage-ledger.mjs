import { mkdir, open, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';

const SECOND_MS = 1000;
const HOUR_MS = 60 * 60 * 1000;

function defaultStatePath() {
  const root = process.env.YDFALL_STATE_ROOT || join(homedir(), '.local', 'state', 'yandex-direct-for-all');
  return join(root, 'wordstat', 'limits.json');
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class WordstatUsageLedger {
  constructor({ statePath = defaultStatePath(), now = () => Date.now(), sleep = delay } = {}) {
    this.statePath = statePath;
    this.lockPath = `${statePath}.lock`;
    this.now = now;
    this.sleep = sleep;
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
        const billedHour = state.requests.filter((item) => item.billed);
        if (billed && billedHour.length >= 100) {
          waitMs = Math.max(waitMs, billedHour[0].at + HOUR_MS - now + 1);
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
        billedLastHour: requests.filter((item) => item.billed).length,
        costUnitsLastHour: requests.reduce((sum, item) => sum + (item.costUnits || 0), 0),
      };
    } finally {
      await rm(this.lockPath, { recursive: true, force: true });
    }
  }

  async #lock() {
    await mkdir(dirname(this.statePath), { recursive: true, mode: 0o700 });
    for (;;) {
      try {
        await mkdir(this.lockPath, { mode: 0o700 });
        return;
      } catch (error) {
        if (error.code !== 'EEXIST') throw error;
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
