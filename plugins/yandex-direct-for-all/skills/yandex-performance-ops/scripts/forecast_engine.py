#!/usr/bin/env python3
"""
Forecast Engine v1.0 — Медиа-план для Яндекс.Директ
Сбор данных + расчёт прогноза + сохранение JSON/MD

Использование:
  python3 forecast_engine.py --campaign_ids 89167235,89175298 --token TOKEN --login LOGIN
  python3 forecast_engine.py --campaign_ids 89167235 --horizons 3,7,30 --with_seasonality
  python3 forecast_engine.py --mode compare --forecast_file data/forecasts/89167235_20260226_30d.json
"""

import argparse, json, math, os, sys, csv
from datetime import datetime, timedelta
from io import StringIO

# ─── CONFIG ───────────────────────────────────────────────────
HORIZONS = [3, 7, 15, 30, 90]
CONFIDENCE_Z = 1.96  # 95%

# Оценочная сезонность (если нет Wordstat)
DEFAULT_SEASONALITY = {
    1: 0.85, 2: 0.90, 3: 1.05, 4: 1.10, 5: 1.15, 6: 1.00,
    7: 0.80, 8: 0.75, 9: 1.10, 10: 1.20, 11: 1.05, 12: 0.95
}


# ─── DATA LOADING ─────────────────────────────────────────────

def load_tsv(path):
    """Загрузить TSV с числовыми полями"""
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        # Пропускаем строки-комментарии Reports API
        lines = [l for l in f if not l.startswith('---') and l.strip()]
        if not lines:
            return rows
        reader = csv.DictReader(StringIO('\n'.join(lines)), delimiter='\t')
        for row in reader:
            parsed = {}
            for k, v in row.items():
                if k is None:
                    continue
                k = k.strip()
                if v in ('--', '', 'nan', 'None', None):
                    parsed[k] = 0
                else:
                    try:
                        parsed[k] = float(v) if '.' in str(v) else int(v)
                    except (ValueError, TypeError):
                        parsed[k] = v
            rows.append(parsed)
    return rows


def load_json(path):
    """Загрузить JSON файл"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_roistat(roistat_path, campaign_id=None):
    """Загрузить Roistat данные (leads, sales, revenue), с фильтром по campaign_id"""
    if not os.path.exists(roistat_path):
        return None
    data = load_json(roistat_path)
    totals = {'visits': 0, 'leads': 0, 'sales': 0, 'revenue': 0, 'cost': 0}

    def parse_metrics(metrics_obj):
        """Парсить metrics — может быть dict ИЛИ list of {metric_name, value}"""
        if isinstance(metrics_obj, list):
            flat = {}
            for m in metrics_obj:
                if isinstance(m, dict) and 'metric_name' in m:
                    flat[m['metric_name']] = float(m.get('value', 0))
            return flat
        return metrics_obj if isinstance(metrics_obj, dict) else {}

    def get_marker(item):
        """Извлечь campaign marker из dimension_values"""
        dims = item.get('dimension_values', item.get('dimensions', {}))
        if isinstance(dims, dict):
            for v in dims.values():
                if isinstance(v, dict):
                    return str(v.get('value', ''))
        return ''

    def has_any_markers(items_list):
        """Проверить есть ли маркеры в данных (1-й проход)"""
        for item in items_list:
            if not isinstance(item, dict):
                continue
            if 'items' in item and isinstance(item['items'], list):
                if has_any_markers(item['items']):
                    return True
                continue
            if get_marker(item):
                return True
        return False

    def process_items(items_list, filter_id=None, markers_exist=False):
        for item in items_list:
            if not isinstance(item, dict):
                continue
            # Вложенные items
            if 'items' in item and isinstance(item['items'], list):
                process_items(item['items'], filter_id, markers_exist)
                continue
            # Фильтр по campaign_id через маркер
            if filter_id:
                marker = get_marker(item)
                if markers_exist:
                    # Данные размечены — фильтруем строго
                    if marker != str(filter_id):
                        continue
                else:
                    # Маркеров нет = агрегат проекта, не используем для одной кампании
                    return
            metrics = parse_metrics(item.get('metrics', item))
            totals['visits'] += float(metrics.get('visitCount', metrics.get('visits', 0)))
            totals['leads'] += float(metrics.get('leadCount', metrics.get('leads', 0)))
            totals['sales'] += float(metrics.get('salesCount', metrics.get('sales', 0)))
            totals['revenue'] += float(metrics.get('revenue', 0))
            totals['cost'] += float(metrics.get('marketing_cost', metrics.get('cost', 0)))

    # Определяем все items для 2-проходного анализа
    def get_all_items(source):
        if isinstance(source, list):
            return source
        elif isinstance(source, dict):
            if 'data' in source:
                items = source['data']
                return items if isinstance(items, list) else [items]
            elif 'items' in source:
                return source['items']
            return [source]
        return []

    all_items = get_all_items(data)
    markers_exist = has_any_markers(all_items) if campaign_id else False
    process_items(all_items, campaign_id, markers_exist)

    return totals


# ─── CALCULATIONS ─────────────────────────────────────────────

def calc_base_metrics(daily_data, days=30):
    """Рассчитать базовые метрики за последние N дней"""
    if not daily_data:
        return None

    # Сортировка по дате (новые первые)
    sorted_data = sorted(daily_data, key=lambda x: str(x.get('Date', '')), reverse=True)
    recent = sorted_data[:days]

    if not recent:
        return None

    n = len(recent)
    total_impressions = sum(r.get('Impressions', 0) for r in recent)
    total_clicks = sum(r.get('Clicks', 0) for r in recent)
    # Reports API TSV: Cost уже в рублях (НЕ микроединицы!)
    # Автодетект: если avg > 100000/день → вероятно микроединицы
    raw_costs = [r.get('Cost', 0) for r in recent]
    avg_raw = sum(raw_costs) / len(raw_costs) if raw_costs else 0
    cost_divisor = 1_000_000 if avg_raw > 100_000 else 1
    total_cost = sum(raw_costs) / cost_divisor
    total_conversions = sum(r.get('Conversions', r.get('Conversions_TODO_LC', 0)) for r in recent)

    daily_impressions = [r.get('Impressions', 0) for r in recent]
    daily_clicks = [r.get('Clicks', 0) for r in recent]
    daily_cost = [c / cost_divisor for c in raw_costs]

    return {
        'days': n,
        'total_impressions': total_impressions,
        'total_clicks': total_clicks,
        'total_cost': total_cost,
        'total_conversions': total_conversions,
        'daily_impressions_avg': total_impressions / n,
        'daily_clicks_avg': total_clicks / n,
        'daily_cost_avg': total_cost / n,
        'ctr': (total_clicks / total_impressions * 100) if total_impressions > 0 else 0,
        'cpc': (total_cost / total_clicks) if total_clicks > 0 else 0,
        'cr': (total_conversions / total_clicks * 100) if total_clicks > 0 else 0,
        'cpa': (total_cost / total_conversions) if total_conversions > 0 else 0,
        # Стандартные отклонения для CI
        'std_impressions': std_dev(daily_impressions),
        'std_clicks': std_dev(daily_clicks),
        'std_cost': std_dev(daily_cost),
    }


def std_dev(values):
    """Стандартное отклонение"""
    if len(values) < 2:
        return 0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def weighted_moving_avg_v2(daily_data, metric_key, weights=(0.5, 0.3, 0.2)):
    """WMA v2: непересекающиеся периоды (0-7, 7-14, 14-30 дней)"""
    sorted_data = sorted(daily_data, key=lambda x: str(x.get('Date', '')), reverse=True)
    periods = [sorted_data[0:7], sorted_data[7:14], sorted_data[14:30]]
    avgs = []
    for period in periods:
        if period:
            vals = [r.get(metric_key, 0) for r in period]
            avgs.append(sum(vals) / len(vals))
        else:
            avgs.append(0)
    return sum(a * w for a, w in zip(avgs, weights))


def estimate_trend(daily_data, days=90):
    """Линейный тренд (slope) через OLS regression"""
    sorted_data = sorted(daily_data, key=lambda x: str(x.get('Date', '')))[-days:]
    if len(sorted_data) < 7:
        return {}
    n = len(sorted_data)
    trends = {}
    for key in ['Impressions', 'Clicks', 'Cost']:
        vals = [r.get(key, 0) for r in sorted_data]
        x_mean = (n - 1) / 2
        y_mean = sum(vals) / n
        num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(vals))
        den = sum((i - x_mean) ** 2 for i in range(n))
        trends[key] = num / den if den > 0 else 0
    return trends


def bayesian_cr(conversions, clicks, prior_cr=0.02, prior_strength=20):
    """Beta-Binomial conjugate update (ИСПРАВЛЕНО по ревью Opus)"""
    if clicks == 0:
        return prior_cr
    alpha_prior = prior_cr * prior_strength
    beta_prior = (1 - prior_cr) * prior_strength
    alpha_post = alpha_prior + conversions
    beta_post = beta_prior + (clicks - conversions)
    return alpha_post / (alpha_post + beta_post)


def binomial_ci(expected_count, cr, n_clicks, z=1.96):
    """CI для КОЛИЧЕСТВА конверсий через нормальную аппроксимацию биномиала"""
    if n_clicks <= 0 or cr <= 0:
        return max(0, expected_count * 0.5), expected_count * 1.5
    std = math.sqrt(n_clicks * cr * (1 - cr))
    return max(0, expected_count - z * std), expected_count + z * std


# ─── FORECAST ─────────────────────────────────────────────────

def make_forecast(daily_data, roistat, horizon, seasonal_coef=1.0, budget_weekly=None, calibration=None):
    """Построить прогноз на N дней"""

    m7 = calc_base_metrics(daily_data, 7)
    m14 = calc_base_metrics(daily_data, 14)
    m30 = calc_base_metrics(daily_data, 30)
    m90 = calc_base_metrics(daily_data, 90)

    if not m30:
        return None

    # Базовые дневные значения
    # FIX #1 (Opus): WMA v2 с непересекающимися периодами
    if horizon <= 7 and len(daily_data) >= 14:
        daily_imp = weighted_moving_avg_v2(daily_data, 'Impressions')
        daily_clk = weighted_moving_avg_v2(daily_data, 'Clicks')
        daily_cost = weighted_moving_avg_v2(daily_data, 'Cost')
        # Автодетект cost divisor
        if daily_cost > 100_000:
            daily_cost /= 1_000_000
    elif horizon <= 30:
        daily_imp = m30['daily_impressions_avg']
        daily_clk = m30['daily_clicks_avg']
        daily_cost = m30['daily_cost_avg']
    else:
        # FIX #7 (Opus): тренд для 90д горизонта
        base = m90 or m30
        trends = estimate_trend(daily_data, days=min(90, len(daily_data)))
        # mid-point экстраполяция
        daily_imp = base['daily_impressions_avg'] + trends.get('Impressions', 0) * (horizon / 2)
        daily_clk = base['daily_clicks_avg'] + trends.get('Clicks', 0) * (horizon / 2)
        daily_cost = base['daily_cost_avg'] + trends.get('Cost', 0) * (horizon / 2)
        # Не допускать отрицательных значений
        daily_imp = max(0, daily_imp)
        daily_clk = max(0, daily_clk)
        daily_cost = max(0, daily_cost)

    # FIX #6 (Opus): Сезонность — к показам/кликам, НЕ к расходу напрямую
    f_impressions = daily_imp * horizon * seasonal_coef
    f_clicks = daily_clk * horizon * seasonal_coef
    # CPC растёт пропорционально половине сезонного коэф. (конкуренция)
    cpc_base = m30['cpc'] if m30['cpc'] > 0 else (daily_cost / daily_clk if daily_clk > 0 else 0)
    cpc_seasonal = cpc_base * (1 + (seasonal_coef - 1) * 0.5)
    f_spend = f_clicks * cpc_seasonal

    # Budget cap (FIX #5: применяем ratio и к конверсиям)
    budget_ratio = 1.0
    if budget_weekly:
        max_spend = budget_weekly / 7 * horizon
        if f_spend > max_spend:
            budget_ratio = max_spend / f_spend
            f_spend = max_spend
            f_clicks *= budget_ratio
            f_impressions *= budget_ratio

    # Конверсии (FIX #4: Beta-Binomial conjugate)
    roistat_visits = roistat.get('visits', m30['total_clicks']) if roistat else m30['total_clicks']
    if roistat and roistat['leads'] > 0:
        cr_lead = bayesian_cr(roistat['leads'], roistat_visits)
        cr_sale = roistat['sales'] / roistat['leads'] if roistat['leads'] > 0 else 0
        avg_order = roistat['revenue'] / roistat['sales'] if roistat['sales'] > 0 else 0
    else:
        cr_lead = m30['cr'] / 100 if m30['cr'] > 0 else 0.02
        cr_sale = 0
        avg_order = 0

    f_leads = f_clicks * cr_lead * budget_ratio
    f_sales = f_leads * cr_sale
    f_revenue = f_sales * avg_order

    # FIX #2 (Opus CRITICAL): CI для суммы — horizon/sqrt(n_sample), не sqrt(horizon)
    n_sample = m30['days']
    ci_imp = CONFIDENCE_Z * m30['std_impressions'] * horizon / math.sqrt(max(1, n_sample))
    ci_clk = CONFIDENCE_Z * m30['std_clicks'] * horizon / math.sqrt(max(1, n_sample))
    ci_cost = CONFIDENCE_Z * m30['std_cost'] * horizon / math.sqrt(max(1, n_sample))

    # FIX #3 (Opus): CI для leads через биномиальную аппроксимацию
    ci_leads_lo, ci_leads_hi = binomial_ci(f_leads, cr_lead, f_clicks)

    # Калибровка
    if calibration:
        corr = calibration.get('correction_factor', 1.0)
        f_impressions *= corr
        f_clicks *= corr
        f_spend *= corr
        f_leads *= corr
        f_sales *= corr
        f_revenue *= corr

    forecast = {
        'impressions': {'point': round(f_impressions), 'ci_lower': max(0, round(f_impressions - ci_imp)), 'ci_upper': round(f_impressions + ci_imp)},
        'clicks': {'point': round(f_clicks), 'ci_lower': max(0, round(f_clicks - ci_clk)), 'ci_upper': round(f_clicks + ci_clk)},
        'spend': {'point': round(f_spend), 'ci_lower': max(0, round(f_spend - ci_cost)), 'ci_upper': round(f_spend + ci_cost)},
        'leads': {'point': round(f_leads, 1), 'ci_lower': round(ci_leads_lo, 1), 'ci_upper': round(ci_leads_hi, 1)},
        'sales': {'point': round(f_sales, 1), 'ci_lower': round(f_sales * 0.5, 1), 'ci_upper': round(f_sales * 1.5, 1)},
        'revenue': {'point': round(f_revenue), 'ci_lower': round(f_revenue * 0.5), 'ci_upper': round(f_revenue * 1.5)},
        'ctr': round(m30['ctr'], 2),
        'cpc': round(m30['cpc'], 1),
        'cr_lead': round(cr_lead * 100, 2),
        'cr_sale': round(cr_sale * 100, 1),
        'cpl': round(f_spend / f_leads) if f_leads > 0 else 0,
        'cps': round(f_spend / f_sales) if f_sales > 0 else 0,
        'roi': round((f_revenue - f_spend) / f_spend * 100, 1) if f_spend > 0 and f_revenue > 0 else 0,
    }

    return forecast


# ─── PLAN-FACT COMPARE ────────────────────────────────────────

def compare_plan_fact(forecast_json, actual_data):
    """Сравнить прогноз с фактом"""
    results = {}
    for metric in ['impressions', 'clicks', 'spend', 'leads', 'sales', 'revenue']:
        plan = forecast_json['forecast'][metric]['point'] if isinstance(forecast_json['forecast'][metric], dict) else forecast_json['forecast'][metric]
        fact = actual_data.get(metric, 0)

        deviation_abs = fact - plan
        deviation_pct = ((fact - plan) / plan * 100) if plan != 0 else None

        results[metric] = {
            'plan': plan,
            'fact': fact,
            'deviation_abs': round(deviation_abs, 1),
            'deviation_pct': round(deviation_pct, 1) if deviation_pct is not None else None,
            'in_ci': forecast_json['forecast'][metric].get('ci_lower', 0) <= fact <= forecast_json['forecast'][metric].get('ci_upper', float('inf')) if isinstance(forecast_json['forecast'][metric], dict) else None,
        }

    # MAPE (без метрик с 0 фактом)
    mape_values = []
    for m in ['impressions', 'clicks', 'spend']:
        if results[m]['fact'] > 0 and results[m]['plan'] > 0:
            mape_values.append(abs(results[m]['deviation_pct']))
    mape = sum(mape_values) / len(mape_values) if mape_values else None

    # Bias
    bias_values = [results[m]['deviation_pct'] for m in ['impressions', 'clicks', 'spend'] if results[m]['deviation_pct'] is not None]
    bias = sum(bias_values) / len(bias_values) if bias_values else None

    return {
        'metrics': results,
        'mape': round(mape, 1) if mape else None,
        'bias': round(bias, 1) if bias else None,
        'quality': 'excellent' if mape and mape < 10 else 'good' if mape and mape < 20 else 'acceptable' if mape and mape < 30 else 'needs_calibration',
    }


# ─── OUTPUT ───────────────────────────────────────────────────

def save_forecast_json(forecast_data, output_dir, campaign_id, horizon):
    """Сохранить JSON прогноза"""
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f'{campaign_id}_{date_str}_{horizon}d.json'
    path = os.path.join(output_dir, 'forecasts', filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(forecast_data, f, ensure_ascii=False, indent=2)

    return path


def generate_md_report(all_forecasts, campaign_name, campaign_id, base_metrics, roistat, seasonal_coef, output_path):
    """Сгенерировать MD медиа-план"""
    now = datetime.now()
    lines = []
    lines.append(f'# Медиа-план: {campaign_name}')
    lines.append(f'**Кампания:** {campaign_id} | **Дата:** {now.strftime("%Y-%m-%d %H:%M")}')
    lines.append(f'**Базовый период:** 90 дней | **Сезонный коэф.:** {seasonal_coef}')
    lines.append('')

    # Текущее состояние
    lines.append('## Текущее состояние (30 дней)')
    lines.append('| Метрика | Значение |')
    lines.append('|---------|----------|')
    if base_metrics:
        lines.append(f'| Показы/день | {base_metrics["daily_impressions_avg"]:,.0f} |')
        lines.append(f'| Клики/день | {base_metrics["daily_clicks_avg"]:,.0f} |')
        lines.append(f'| Расход/день | {base_metrics["daily_cost_avg"]:,.0f}р |')
        lines.append(f'| CTR | {base_metrics["ctr"]:.2f}% |')
        lines.append(f'| CPC | {base_metrics["cpc"]:.1f}р |')
    if roistat:
        lines.append(f'| Лиды (Roistat 30д) | {roistat["leads"]:.0f} |')
        lines.append(f'| Продажи (Roistat 30д) | {roistat["sales"]:.0f} |')
        if roistat['leads'] > 0:
            lines.append(f'| CPL | {roistat["cost"] / roistat["leads"]:,.0f}р |' if roistat['cost'] > 0 else '| CPL | — |')
    lines.append('')

    # Прогноз
    lines.append('## Прогноз')
    lines.append('')
    horizons = sorted(all_forecasts.keys())
    header = '| Метрика |' + '|'.join(f' {h} дн. ' for h in horizons) + '|'
    sep = '|---------|' + '|'.join('-------:' for _ in horizons) + '|'
    lines.append(header)
    lines.append(sep)

    for metric, label, fmt in [
        ('impressions', 'Показы', '{:,.0f}'),
        ('clicks', 'Клики', '{:,.0f}'),
        ('ctr', 'CTR', '{:.2f}%'),
        ('cpc', 'CPC', '{:.1f}р'),
        ('spend', '**Расход**', '**{:,.0f}р**'),
        ('leads', 'Лиды', '{:.1f}'),
        ('sales', 'Продажи', '{:.1f}'),
        ('revenue', 'Выручка', '{:,.0f}р'),
        ('cpl', 'CPL', '{:,.0f}р'),
        ('cps', 'CPS', '{:,.0f}р'),
        ('roi', '**ROI**', '**{:.0f}%**'),
    ]:
        vals = []
        for h in horizons:
            f = all_forecasts[h]
            if isinstance(f.get(metric), dict):
                v = f[metric]['point']
            else:
                v = f.get(metric, 0)
            try:
                vals.append(fmt.format(v))
            except (ValueError, TypeError):
                vals.append(str(v))
        lines.append(f'| {label} |' + '|'.join(f' {v} ' for v in vals) + '|')

    lines.append('')

    # CI для 30д
    if 30 in all_forecasts:
        f30 = all_forecasts[30]
        lines.append('## Доверительные интервалы (95%) — 30 дней')
        lines.append('| Метрика | Пессимист | Базовый | Оптимист |')
        lines.append('|---------|----------:|--------:|---------:|')
        for metric, label in [('spend', 'Расход'), ('leads', 'Лиды'), ('sales', 'Продажи'), ('revenue', 'Выручка')]:
            if isinstance(f30.get(metric), dict):
                lines.append(f'| {label} | {f30[metric]["ci_lower"]:,.0f} | {f30[metric]["point"]:,.0f} | {f30[metric]["ci_upper"]:,.0f} |')
        lines.append('')

    # Дата верификации
    verify_dates = {h: (now + timedelta(days=h+1)).strftime('%Y-%m-%d') for h in horizons}
    lines.append('## Даты верификации')
    for h, d in verify_dates.items():
        lines.append(f'- **{h} дней:** {d}')
    lines.append('')

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return output_path


# ─── MAIN ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Forecast Engine v1.0')
    parser.add_argument('--campaign_ids', required=True, help='Campaign IDs через запятую')
    parser.add_argument('--data_dir', required=True, help='Путь к data/ проекта')
    parser.add_argument('--output_dir', default=None, help='Путь для сохранения (default: data_dir)')
    parser.add_argument('--horizons', default='3,7,15,30,90', help='Горизонты через запятую')
    parser.add_argument('--with_seasonality', action='store_true', help='Использовать сезонность')
    parser.add_argument('--roistat_file', default=None, help='Путь к roistat JSON')
    parser.add_argument('--mode', default='forecast', choices=['forecast', 'compare'], help='Режим')
    parser.add_argument('--forecast_file', default=None, help='JSON прогноза для compare')
    parser.add_argument('--docs_dir', default=None, help='Путь для markdown отчётов (default: ../claude/docs)')

    args = parser.parse_args()

    output_dir = args.output_dir or args.data_dir
    horizons = [int(h) for h in args.horizons.split(',')]
    campaign_ids = args.campaign_ids.split(',')

    for cid in campaign_ids:
        cid = cid.strip()
        print(f'\n=== Кампания {cid} ===')

        # Загрузка данных
        tsv_path = os.path.join(args.data_dir, cid, 'reports', 'daily_stats.tsv')
        if not os.path.exists(tsv_path):
            # Попробовать альтернативные пути
            alt_paths = [
                os.path.join(args.data_dir, cid, 'reports', 'campaign_daily_30d.tsv'),
                os.path.join(args.data_dir, f'{cid}_fresh', 'reports', 'daily_stats.tsv'),
                os.path.join(args.data_dir, f'{cid}_fresh', 'reports', 'campaign_daily_30d.tsv'),
                os.path.join(args.data_dir, cid, 'reports', 'campaign_performance_30d.tsv'),
            ]
            for alt in alt_paths:
                if os.path.exists(alt):
                    tsv_path = alt
                    break
            else:
                print(f'  [SKIP] Нет данных: {tsv_path}')
                continue

        daily_data = load_tsv(tsv_path)
        print(f'  Загружено {len(daily_data)} дней данных')

        # Roistat
        roistat = None
        if args.roistat_file:
            roistat = load_roistat(args.roistat_file, campaign_id=cid)
        else:
            roistat_paths = [
                os.path.join(args.data_dir, cid, 'roistat', 'campaigns_30d.json'),
                os.path.join(args.data_dir, cid, 'roistat', 'adgroups_30d.json'),
                os.path.join(args.data_dir, f'{cid}_fresh', 'roistat', 'campaigns_30d.json'),
                os.path.join(args.data_dir, f'{cid}_fresh', 'roistat', f'roistat_{cid}_groups.json'),
            ]
            for rp in roistat_paths:
                if os.path.exists(rp):
                    roistat = load_roistat(rp, campaign_id=cid)
                    if roistat and (roistat['visits'] > 0 or roistat['leads'] > 0):
                        break

        if roistat:
            print(f'  Roistat: {roistat["leads"]:.0f} leads, {roistat["sales"]:.0f} sales')
        else:
            print('  [WARN] Roistat данные не найдены')

        # Сезонность
        now = datetime.now()
        if args.with_seasonality:
            target_month = now.month
            seasonal_coef = DEFAULT_SEASONALITY.get(target_month, 1.0)
            print(f'  Сезонный коэф. (месяц {target_month}): {seasonal_coef}')
        else:
            seasonal_coef = 1.0

        # Калибровка
        cal_path = os.path.join(output_dir, 'calibration', f'{cid}_calibration.json')
        calibration = load_json(cal_path) if os.path.exists(cal_path) else None
        if calibration:
            print(f'  Калибровка: correction={calibration.get("correction_factor", 1.0):.3f}')

        # Бюджет
        campaign_path = os.path.join(args.data_dir, cid, 'management', 'campaign.json')
        budget_weekly = None
        campaign_name = f'Campaign {cid}'
        if os.path.exists(campaign_path):
            raw = load_json(campaign_path)
            # Структура: {"result": {"Campaigns": [...]}} или plain dict
            if isinstance(raw, dict) and 'result' in raw:
                camps = raw['result'].get('Campaigns', [raw['result']])
            elif isinstance(raw, list):
                camps = raw
            else:
                camps = [raw]
            camp = camps[0] if camps else {}
            campaign_name = camp.get('Name', campaign_name)
            # Извлечь бюджет из стратегии
            tc = camp.get('TextCampaign', {})
            strategy = tc.get('BiddingStrategy', {})
            for side in ['Network', 'Search']:
                s = strategy.get(side, {})
                for key in s:
                    if isinstance(s[key], dict):
                        wsl = s[key].get('WeeklySpendLimit')
                        if wsl:
                            budget_weekly = wsl / 1_000_000
                            break

        if budget_weekly:
            print(f'  Бюджет: {budget_weekly:,.0f}р/нед')

        # Расчёт прогнозов
        all_forecasts = {}
        base_30 = calc_base_metrics(daily_data, 30)

        for h in horizons:
            forecast = make_forecast(daily_data, roistat, h, seasonal_coef, budget_weekly, calibration)
            if forecast:
                all_forecasts[h] = forecast

                # Сохранить JSON
                forecast_data = {
                    'forecast_id': f'{cid}_{now.strftime("%Y%m%d")}_{h}d',
                    'campaign_id': int(cid),
                    'campaign_name': campaign_name,
                    'created_at': now.isoformat(),
                    'horizon_days': h,
                    'period': {
                        'from': (now + timedelta(days=1)).strftime('%Y-%m-%d'),
                        'to': (now + timedelta(days=h)).strftime('%Y-%m-%d'),
                    },
                    'base_period_days': 90,
                    'seasonal_coef': seasonal_coef,
                    'calibration_applied': calibration is not None,
                    'forecast': forecast,
                    'budget_weekly': budget_weekly,
                }

                path = save_forecast_json(forecast_data, output_dir, cid, h)
                print(f'  [{h}д] saved → {path}')

        # MD отчёт
        if all_forecasts:
            docs_dir = args.docs_dir or os.path.join(os.path.dirname(output_dir), 'claude', 'docs')
            md_path = os.path.join(docs_dir, f'media_plan_{cid}_{now.strftime("%Y%m%d")}.md')
            generate_md_report(all_forecasts, campaign_name, cid, base_30, roistat, seasonal_coef, md_path)
            print(f'  MD → {md_path}')

    print('\nDone.')


if __name__ == '__main__':
    main()
