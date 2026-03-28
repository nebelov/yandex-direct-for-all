#!/usr/bin/env node
const fs = require('fs');
const os = require('os');
const path = require('path');
const { fileURLToPath, pathToFileURL } = require('url');

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const key = a.slice(2);
    const val = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : 'true';
    args[key] = val;
  }
  return args;
}

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function safeName(s) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9а-яё\s_-]/gi, '')
    .replace(/\s+/g, '_')
    .slice(0, 70);
}

function toIsoDate(d) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function monthRange(monthsBack = 6) {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth() - monthsBack, 1);
  // Last day of previous full month (Wordstat monthly requirement)
  const to = new Date(now.getFullYear(), now.getMonth(), 0);
  return { fromDate: toIsoDate(from), toDate: toIsoDate(to) };
}

function wordCount(mask) {
  const parts = String(mask || '').trim().split(/\s+/).filter(Boolean);
  return parts.length;
}

function candidateClientPaths() {
  const envPath = process.env.YANDEX_WORDSTAT_CLIENT_PATH;
  const home = os.homedir();
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const dynamicHomePaths = [];
  try {
    for (const entry of fs.readdirSync(home, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      dynamicHomePaths.push(path.join(home, entry.name, 'mcp/yandex-wordstat/dist/client.js'));
    }
  } catch (_) {
    // Best-effort only.
  }

  return [
    envPath,
    path.resolve(scriptDir, '../../mcp/yandex-wordstat/dist/client.js'),
    path.join(home, '.codex/mcp/yandex-wordstat/dist/client.js'),
    path.join(process.cwd(), 'mcp/yandex-wordstat/dist/client.js'),
    path.join(home, 'mcp/yandex-wordstat/dist/client.js'),
    ...dynamicHomePaths
  ].filter(Boolean);
}

async function loadWordstatClientClass() {
  for (const candidate of candidateClientPaths()) {
    if (!fs.existsSync(candidate)) continue;
    const mod = await import(pathToFileURL(candidate).href);
    if (mod.WordstatClient) {
      return mod.WordstatClient;
    }
  }
  throw new Error(
    'Wordstat client not found. Set YANDEX_WORDSTAT_CLIENT_PATH or install bundled MCP client into ~/.codex/mcp/yandex-wordstat.'
  );
}

async function main() {
  const args = parseArgs(process.argv);
  const masksFile = args['masks-file'];
  const outDir = args['output-dir'];
  const regions = (args['regions'] || '225').split(',').map((x) => Number(x.trim())).filter(Boolean);
  const numPhrases = Number(args['num-phrases'] || 200);
  const sleepMs = Number(args['sleep-ms'] || 250);
  const devices = (args['devices'] || 'all').split(',').map((s) => s.trim()).filter(Boolean);
  const doDynamics = (args['dynamics'] || 'false') === 'true';
  const doRegions = (args['regions-report'] || 'false') === 'true';
  const doRegionsTree = (args['regions-tree'] || 'false') === 'true';
  const requireSingleToken = (args['require-single-token'] || 'false') === 'true';
  const enforceMaskWordRange = (args['enforce-mask-word-range'] || 'true') === 'true';
  const dynamicsMonthsBack = Number(args['dynamics-months-back'] || 6);
  const dynamicsFromDate = args['dynamics-from-date'] || '';
  const dynamicsToDate = args['dynamics-to-date'] || '';
  let minMaskWords = Number(args['min-mask-words'] || 1);
  let maxMaskWords = Number(args['max-mask-words'] || 2);
  if (requireSingleToken) {
    minMaskWords = 1;
    maxMaskWords = 1;
  }
  const fullDepth = (args['full-depth'] || 'true') === 'true';

  if (!masksFile || !outDir) {
    console.error('Usage: node wordstat_collect_wave.js --masks-file FILE.tsv --output-dir DIR [--regions 225] [--num-phrases 2000] [--devices all] [--dynamics true] [--regions-report true] [--regions-tree true] [--min-mask-words 1] [--max-mask-words 2] [--require-single-token false] [--enforce-mask-word-range true] [--full-depth true]');
    process.exit(2);
  }

  if (fullDepth && numPhrases < 2000) {
    console.error('ERROR: full-depth mode requires --num-phrases >= 2000');
    process.exit(2);
  }

  const token = process.env.YANDEX_WORDSTAT_TOKEN;
  if (!token) {
    console.error('ERROR: YANDEX_WORDSTAT_TOKEN env is required');
    process.exit(2);
  }

  ensureDir(outDir);
  const WordstatClient = await loadWordstatClientClass();
  const client = new WordstatClient({ token });

  const input = fs.readFileSync(masksFile, 'utf-8').split(/\r?\n/).filter(Boolean);
  const header = input[0].split('\t');
  const idxMask = header.indexOf('mask');
  const idxIntent = header.indexOf('intent');
  if (idxMask === -1) throw new Error('masks file must contain column: mask');

  const rawRows = input.slice(1).map((line) => line.split('\t'));
  const seenMasks = new Set();
  const rows = [];
  const duplicates = [];
  const invalidMasks = [];

  for (const cols of rawRows) {
    const intent = (cols[idxIntent] || '').trim().toLowerCase();
    if (intent === 'exclude') continue;
    const mask = (cols[idxMask] || '').trim();
    if (!mask) continue;

    const wc = wordCount(mask);
    if (enforceMaskWordRange && (wc < minMaskWords || wc > maxMaskWords)) {
      invalidMasks.push(mask);
      continue;
    }

    const key = mask.toLowerCase();
    if (seenMasks.has(key)) {
      duplicates.push(mask);
      continue;
    }
    seenMasks.add(key);
    rows.push(cols);
  }

  const masksAudit = {
    inputRows: rawRows.length,
    rowsAfterExclude: rawRows.filter((cols) => ((cols[idxIntent] || '').trim().toLowerCase() !== 'exclude')).length,
    uniqueRows: rows.length,
    enforceMaskWordRange,
    minMaskWords,
    maxMaskWords,
    requireSingleToken,
    invalidMasks,
    duplicates
  };
  fs.writeFileSync(path.join(outDir, '_masks_audit.json'), JSON.stringify(masksAudit, null, 2));

  if (enforceMaskWordRange && invalidMasks.length > 0) {
    console.error(`ERROR: found ${invalidMasks.length} masks outside word range ${minMaskWords}-${maxMaskWords}. See _masks_audit.json`);
    process.exit(2);
  }

  const manifest = [];
  let topOk = 0;
  let topFail = 0;
  let dynOk = 0;
  let dynFail = 0;
  let regionsOk = 0;
  let regionsFail = 0;
  let truncatedMasks = 0;

  const userInfo = await client.getUserInfo();
  fs.writeFileSync(path.join(outDir, '_wordstat_user_info_start.json'), JSON.stringify(userInfo, null, 2));

  if (doRegionsTree) {
    try {
      const regionsTree = await client.getRegionsTree();
      fs.writeFileSync(path.join(outDir, '_regions_tree.json'), JSON.stringify(regionsTree, null, 2));
      manifest.push({ type: 'regions_tree', file: path.join(outDir, '_regions_tree.json') });
    } catch (e) {
      const errFile = path.join(outDir, '_error_regions_tree.txt');
      fs.writeFileSync(errFile, String(e?.message || e));
      manifest.push({ type: 'regions_tree_error', file: errFile, error: String(e?.message || e) });
    }
  }

  for (const cols of rows) {
    const mask = (cols[idxMask] || '').trim();
    if (!mask) continue;

    const stub = safeName(mask);
    const topFile = path.join(outDir, `top_requests_${stub}.json`);

    try {
      const top = await client.getTopRequests({ phrase: mask, numPhrases, regions, devices });
      fs.writeFileSync(topFile, JSON.stringify(top, null, 2));
      const totalCount = top.totalCount || 0;
      const truncated = Array.isArray(top.topRequests) && top.topRequests.length >= numPhrases;
      if (truncated) truncatedMasks += 1;
      manifest.push({ mask, type: 'top_requests', file: topFile, totalCount, truncated });
      topOk += 1;
    } catch (e) {
      const errFile = path.join(outDir, `error_top_${stub}.txt`);
      fs.writeFileSync(errFile, String(e?.message || e));
      manifest.push({ mask, type: 'top_requests_error', file: errFile, error: String(e?.message || e) });
      topFail += 1;
    }

    if (doDynamics) {
      try {
        const { fromDate, toDate } = dynamicsFromDate && dynamicsToDate
          ? { fromDate: dynamicsFromDate, toDate: dynamicsToDate }
          : monthRange(dynamicsMonthsBack);
        const dyn = await client.getDynamics({
          phrase: mask,
          period: 'monthly',
          fromDate,
          toDate,
          regions,
          devices
        });
        const dynFile = path.join(outDir, `dynamics_${stub}.json`);
        fs.writeFileSync(dynFile, JSON.stringify(dyn, null, 2));
        manifest.push({
          mask,
          type: 'dynamics',
          file: dynFile,
          points: dyn.dynamics?.length || 0,
          fromDate,
          toDate
        });
        dynOk += 1;
      } catch (e) {
        const errFile = path.join(outDir, `error_dyn_${stub}.txt`);
        fs.writeFileSync(errFile, String(e?.message || e));
        manifest.push({ mask, type: 'dynamics_error', file: errFile, error: String(e?.message || e) });
        dynFail += 1;
      }
    }

    if (doRegions) {
      try {
        const regionsResponse = await client.getRegions({
          phrase: mask,
          regions,
          devices
        });
        const regionsFile = path.join(outDir, `regions_${stub}.json`);
        fs.writeFileSync(regionsFile, JSON.stringify(regionsResponse, null, 2));
        manifest.push({
          mask,
          type: 'regions',
          file: regionsFile,
          regionsTotal: Array.isArray(regionsResponse.regions) ? regionsResponse.regions.length : 0
        });
        regionsOk += 1;
      } catch (e) {
        const errFile = path.join(outDir, `error_regions_${stub}.txt`);
        fs.writeFileSync(errFile, String(e?.message || e));
        manifest.push({ mask, type: 'regions_error', file: errFile, error: String(e?.message || e) });
        regionsFail += 1;
      }
    }

    await new Promise((r) => setTimeout(r, sleepMs));
  }

  const userInfoEnd = await client.getUserInfo().catch(() => null);
  if (userInfoEnd) {
    fs.writeFileSync(path.join(outDir, '_wordstat_user_info_end.json'), JSON.stringify(userInfoEnd, null, 2));
  }

  fs.writeFileSync(path.join(outDir, '_manifest.json'), JSON.stringify(manifest, null, 2));
  fs.writeFileSync(path.join(outDir, '_summary.json'), JSON.stringify({
    masks: rows.length,
    config: {
      numPhrases,
      regions,
      devices,
      doDynamics,
      doRegions,
      doRegionsTree,
      enforceMaskWordRange,
      minMaskWords,
      maxMaskWords,
      requireSingleToken,
      fullDepth
    },
    top: { ok: topOk, fail: topFail },
    dynamics: doDynamics ? { ok: dynOk, fail: dynFail } : null,
    regions: doRegions ? { ok: regionsOk, fail: regionsFail } : null,
    truncatedMasks
  }, null, 2));

  console.log(JSON.stringify({
    masks: rows.length,
    config: {
      numPhrases,
      regions,
      doDynamics,
      doRegions,
      doRegionsTree,
      enforceMaskWordRange,
      minMaskWords,
      maxMaskWords,
      requireSingleToken,
      fullDepth
    },
    top: { ok: topOk, fail: topFail },
    dynamics: doDynamics ? { ok: dynOk, fail: dynFail } : null,
    regions: doRegions ? { ok: regionsOk, fail: regionsFail } : null,
    truncatedMasks,
    outDir
  }, null, 2));
}

main().catch((e) => {
  console.error(e?.stack || String(e));
  process.exit(1);
});
