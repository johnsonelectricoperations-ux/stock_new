# 거래 이력 기록 및 전략 성과 평가 모듈
import csv
import json
import os
from datetime import datetime
from config.settings import TOTAL_BUDGET

TRADE_LOG = 'trades.csv'
SIGNAL_LOG = 'signal_log.csv'
BASIS_LOG = 'basis_log.csv'
TIMING_LOG = 'timing_log.csv'
FOLLOWUP_LOG = 'followup_log.csv'
FOLLOWUP_PENDING = 'config/followup_pending.json'

_BASIS_HEADERS = ['date', 'time', 'kospi200_spot', 'kospi200_futures', 'basis', 'basis_pct', 'basis_slope']
_TIMING_HEADERS = ['date', 'code', 'name', 'check_time', 'dip_met', 'action']

_HEADERS = [
    'exit_date', 'exit_time', 'code', 'name', 'sector',
    'entry_date', 'entry_time', 'entry_price', 'exit_price',
    'qty', 'profit', 'profit_rate', 'reason', 'hold_days',
    'peak_price', 'min_price', 'trigger_price',
    'momentum', 'foreign_net_buy_mil',
    'ma20_at_entry', 'ma60_at_entry', 'volume_ratio',
    'kospi_trend', 'dip_entry_used',
]
_SIGNAL_HEADERS = [
    'date', 'sector', 'sector_rank', 'sector_avg_momentum',
    'code', 'name', 'signal_price', 'momentum', 'is_uptrend',
    'ma20', 'ma60', 'volume_ratio',
    'foreign_5d_net_buy_mil', 'passed_all_filters', 'selected',
    # 향후 동적 임계값 결정용 데이터
    'bb_pct', 'atr', 'avg_tr_pbmn_mil',
]
_FOLLOWUP_HEADERS = [
    'code', 'name', 'exit_date', 'exit_price', 'reason',
    'd3_price', 'd3_rate', 'd5_price', 'd5_rate',
    'd10_price', 'd10_rate', 'd20_price', 'd20_rate',
]
_FOLLOWUP_DAYS = [3, 5, 10, 20]


def log_basis(data: dict):
    """매일 장 시작 전 KOSPI 200 베이시스 기록 (임계값 튜닝용)."""
    exists = os.path.exists(BASIS_LOG)
    with open(BASIS_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(_BASIS_HEADERS)
        now = datetime.now()
        writer.writerow([
            now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'),
            data['spot'],
            data.get('futures') or '',
            data.get('basis') or '',
            data.get('basis_pct') or '',
            data.get('basis_slope') or '',
        ])


def log_timing(code: str, name: str, dip_met: bool, action: str):
    """
    매수 윈도우(09:15~09:30) 매 분 체크 기록.
    action: waiting | bought_dip | buy_failed | forced_bought
    """
    exists = os.path.exists(TIMING_LOG)
    with open(TIMING_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(_TIMING_HEADERS)
        now = datetime.now()
        writer.writerow([
            now.strftime('%Y-%m-%d'), code, name,
            now.strftime('%H:%M:%S'), dip_met, action,
        ])


def log_signal_scan(scan_records: list):
    """매일 신호 스캔 결과 전체를 signal_log.csv에 기록."""
    exists = os.path.exists(SIGNAL_LOG)
    with open(SIGNAL_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(_SIGNAL_HEADERS)
        for r in scan_records:
            writer.writerow([
                r['date'], r['sector'], r['sector_rank'], r['sector_avg_momentum'],
                r['code'], r['name'],
                r.get('signal_price', ''), r['momentum'], r['is_uptrend'],
                r.get('ma20', ''), r.get('ma60', ''), r.get('volume_ratio', ''),
                r.get('foreign_5d_net_buy_mil', ''),
                r['passed_all_filters'], r['selected'],
                r.get('bb_pct', ''), r.get('atr', ''), r.get('avg_tr_pbmn_mil', ''),
            ])


def log_trade(code, name, sector, entry_date, entry_time, entry_price,
              exit_price, qty, reason,
              peak_price=None, min_price=None, trigger_price=None,
              momentum=None, foreign_net_buy_mil=None,
              ma20_at_entry=None, ma60_at_entry=None, volume_ratio=None,
              kospi_trend=None, dip_entry_used=None):
    exists = os.path.exists(TRADE_LOG)
    exit_date = datetime.now().strftime('%Y-%m-%d')
    exit_time = datetime.now().strftime('%H:%M:%S')
    hold_days = (
        datetime.strptime(exit_date, '%Y-%m-%d') -
        datetime.strptime(entry_date, '%Y-%m-%d')
    ).days
    profit = round((exit_price - entry_price) * qty)
    profit_rate = round((exit_price - entry_price) / entry_price * 100, 2)

    with open(TRADE_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(_HEADERS)
        writer.writerow([
            exit_date, exit_time, code, name, sector,
            entry_date, entry_time, entry_price, exit_price,
            qty, profit, profit_rate, reason, hold_days,
            peak_price, min_price, trigger_price,
            momentum, foreign_net_buy_mil,
            ma20_at_entry, ma60_at_entry, volume_ratio,
            kospi_trend, dip_entry_used,
        ])


# ─── 사후 추적 (followup) ───────────────────────────────────────────────────

def _load_followup_pending() -> list:
    if not os.path.exists(FOLLOWUP_PENDING):
        return []
    with open(FOLLOWUP_PENDING, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_followup_pending(pending: list):
    os.makedirs(os.path.dirname(FOLLOWUP_PENDING), exist_ok=True)
    with open(FOLLOWUP_PENDING, 'w', encoding='utf-8') as f:
        json.dump(pending, f, ensure_ascii=False)


def add_followup_pending(code: str, name: str, exit_date: str, exit_price: int, reason: str):
    """매도 시 사후 추적 대상에 추가."""
    pending = _load_followup_pending()
    for p in pending:
        if p['code'] == code and p['exit_date'] == exit_date:
            return
    pending.append({
        'code': code, 'name': name,
        'exit_date': exit_date, 'exit_price': exit_price, 'reason': reason,
        'd3': None, 'd5': None, 'd10': None, 'd20': None,
    })
    _save_followup_pending(pending)


def get_followup_due(today_str: str) -> list:
    """오늘 날짜 기준으로 가격 추적이 필요한 (item, day_key) 목록 반환."""
    pending = _load_followup_pending()
    today = datetime.strptime(today_str, '%Y-%m-%d')
    due = []
    for item in pending:
        exit_dt = datetime.strptime(item['exit_date'], '%Y-%m-%d')
        days_elapsed = (today - exit_dt).days
        for d in _FOLLOWUP_DAYS:
            key = f'd{d}'
            if days_elapsed >= d and item.get(key) is None:
                due.append((item, key))
    return due


def record_followup_price(code: str, exit_date: str, day_key: str, price: int):
    """사후 추적 가격 기록. 모든 시점 완료 시 followup_log.csv에 기록."""
    pending = _load_followup_pending()
    target = None
    for item in pending:
        if item['code'] == code and item['exit_date'] == exit_date:
            item[day_key] = price
            target = item
            break
    if target is None:
        return
    _save_followup_pending(pending)

    if all(target.get(f'd{d}') is not None for d in _FOLLOWUP_DAYS):
        _write_followup_log(target)
        pending = [p for p in pending
                   if not (p['code'] == code and p['exit_date'] == exit_date)]
        _save_followup_pending(pending)


def _write_followup_log(item: dict):
    ep = item['exit_price']
    exists = os.path.exists(FOLLOWUP_LOG)
    with open(FOLLOWUP_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(_FOLLOWUP_HEADERS)

        def rate(p):
            return round((p - ep) / ep * 100, 2) if p else ''

        writer.writerow([
            item['code'], item['name'], item['exit_date'], ep, item['reason'],
            item['d3'],  rate(item['d3']),
            item['d5'],  rate(item['d5']),
            item['d10'], rate(item['d10']),
            item['d20'], rate(item['d20']),
        ])


# ─── 성과 리포트 ────────────────────────────────────────────────────────────

def get_report() -> str:
    if not os.path.exists(TRADE_LOG):
        return '아직 완료된 거래가 없습니다.\n매도가 발생하면 기록이 시작됩니다.'

    trades = []
    with open(TRADE_LOG, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            trades.append(row)

    if not trades:
        return '완료된 거래 기록이 없습니다.'

    total = len(trades)
    profits = [float(t['profit_rate']) for t in trades]
    amounts = [int(t['profit']) for t in trades]

    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]
    win_rate = len(wins) / total * 100
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    pl_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

    cumulative_profit = sum(amounts)
    cumulative_rate = cumulative_profit / TOTAL_BUDGET * 100

    # MDD 계산
    running, peak, mdd = 0, 0, 0
    for a in amounts:
        running += a
        if running > peak:
            peak = running
        dd = (running - peak) / TOTAL_BUDGET * 100
        if dd < mdd:
            mdd = dd

    # 최대 연속 손실
    max_consec, cur_consec = 0, 0
    for p in profits:
        if p <= 0:
            cur_consec += 1
            max_consec = max(max_consec, cur_consec)
        else:
            cur_consec = 0

    avg_hold = sum(int(t['hold_days']) for t in trades) / total

    start_date = trades[0]['entry_date']
    end_date = trades[-1]['exit_date']

    # 섹터별 평균 수익률
    sector_map: dict = {}
    for t in trades:
        s = t['sector'] or '기타'
        sector_map.setdefault(s, []).append(float(t['profit_rate']))
    sector_lines = [
        f'  {s}: {sum(v)/len(v):+.1f}% ({len(v)}건)'
        for s, v in sorted(sector_map.items(), key=lambda x: -sum(x[1]))
    ]

    stat_note = '' if total >= 30 else f'\n⚠️ 거래 {total}건 — 30건 이상이어야 통계 신뢰도가 높습니다.'

    lines = [
        f'📊 누적 성과 ({start_date} ~ {end_date})',
        stat_note,
        f'총 거래: {total}건',
        f'승률: {win_rate:.0f}% ({len(wins)}승 {len(losses)}패)',
        f'평균 수익: +{avg_win:.1f}% / 평균 손실: -{avg_loss:.1f}%',
        f'손익비: {pl_ratio:.2f}',
        f'누적 수익: {cumulative_profit:+,}원 ({cumulative_rate:+.1f}%)',
        f'최대 낙폭(MDD): {mdd:.1f}%',
        f'최대 연속 손실: {max_consec}회',
        f'평균 보유 기간: {avg_hold:.1f}일',
        '',
        '섹터별 평균 수익률.',
    ] + sector_lines

    return '\n'.join(line for line in lines if line != '')
