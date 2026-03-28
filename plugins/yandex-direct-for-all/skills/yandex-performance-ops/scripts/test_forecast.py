#!/usr/bin/env python3
"""
Системный тест forecast_engine.py — запускать после КАЖДОЙ правки!
python3 test_forecast.py --data_dir /path/to/data
"""
import sys, os, argparse

sys.path.insert(0, os.path.dirname(__file__))
from forecast_engine import *

def run_tests(data_dir):
    passed = 0
    failed = 0

    def check(name, condition, msg=""):
        nonlocal passed, failed
        if condition:
            print(f'  PASS: {name}')
            passed += 1
        else:
            print(f'  FAIL: {name} — {msg}')
            failed += 1

    # === Roistat фильтрация ===
    print('=== TEST 1: Roistat фильтрация по campaign_id ===')
    roistat_files = []
    for cid_dir in os.listdir(data_dir):
        rp = os.path.join(data_dir, cid_dir, 'roistat', 'campaigns_30d.json')
        if os.path.exists(rp):
            roistat_files.append((cid_dir, rp))

    if roistat_files:
        cid_dir, rp = roistat_files[0]
        r_all = load_roistat(rp)
        r_filtered = load_roistat(rp, campaign_id=cid_dir)
        check('filter reduces total', r_filtered['leads'] <= r_all['leads'],
              f'filtered={r_filtered["leads"]} all={r_all["leads"]}')
        check('all > 0', r_all['visits'] > 0, f'visits={r_all["visits"]}')
    else:
        print('  SKIP: no roistat files found')

    # === TSV загрузка ===
    print('\n=== TEST 2: TSV загрузка ===')
    tsv_found = False
    for cid_dir in os.listdir(data_dir):
        tsv_path = os.path.join(data_dir, cid_dir, 'reports', 'campaign_daily_30d.tsv')
        if os.path.exists(tsv_path):
            rows = load_tsv(tsv_path)
            if len(rows) > 1:
                check(f'TSV {cid_dir}', len(rows) > 0, f'rows={len(rows)}')
                check('has Impressions', 'Impressions' in rows[0])
                check('has Cost', 'Cost' in rows[0])
                check('numeric values', isinstance(rows[0].get('Impressions', ''), (int, float)))
                tsv_found = True
                break
    if not tsv_found:
        print('  SKIP: no TSV files with >1 row')

    # === Base metrics ===
    print('\n=== TEST 3: calc_base_metrics ===')
    if tsv_found:
        m = calc_base_metrics(rows, min(30, len(rows)))
        check('not None', m is not None)
        if m:
            check('CTR > 0', m['ctr'] > 0, f'CTR={m["ctr"]}')
            check('CPC > 0', m['cpc'] > 0, f'CPC={m["cpc"]}')
            check('std > 0', m['std_impressions'] > 0, f'std={m["std_impressions"]}')

    # === WMA ===
    print('\n=== TEST 4: WMA v2 ===')
    if tsv_found and len(rows) >= 7:
        wma = weighted_moving_avg_v2(rows, 'Impressions')
        check('WMA > 0', wma > 0, f'wma={wma}')
    else:
        print('  SKIP: not enough rows for WMA')

    # === Bayesian CR ===
    print('\n=== TEST 5: bayesian_cr ===')
    check('prior dominates at 0', bayesian_cr(0, 100) > 0)
    check('data moves CR', bayesian_cr(10, 100) > bayesian_cr(0, 100))
    check('more data = stronger', abs(bayesian_cr(100, 10000) - 0.01) < abs(bayesian_cr(1, 100) - 0.01))

    # === Binomial CI ===
    print('\n=== TEST 6: binomial_ci ===')
    lo, hi = binomial_ci(50, 0.05, 1000)
    check('contains point', lo < 50 < hi)
    check('lower >= 0', lo >= 0)
    lo0, hi0 = binomial_ci(0, 0, 0)
    check('handles zero', lo0 == 0)

    # === Trend ===
    print('\n=== TEST 7: estimate_trend ===')
    if tsv_found and len(rows) >= 7:
        trends = estimate_trend(rows, min(30, len(rows)))
        check('has Impressions', 'Impressions' in trends)
        check('has Cost', 'Cost' in trends)
    else:
        print('  SKIP')

    # === Full forecast ===
    print('\n=== TEST 8: make_forecast ===')
    if tsv_found:
        for horizon in [3, 7, 15, 30, 90]:
            f = make_forecast(rows, None, horizon, seasonal_coef=0.9)
            if f:
                check(f'{horizon}d impressions > 0', f['impressions']['point'] > 0)
                check(f'{horizon}d CI lower < upper', f['impressions']['ci_lower'] <= f['impressions']['ci_upper'])

    # === Summary ===
    print(f'\n{"="*50}')
    print(f'RESULTS: {passed} passed, {failed} failed')
    return failed == 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='./data')
    args = parser.parse_args()

    success = run_tests(args.data_dir)
    sys.exit(0 if success else 1)
