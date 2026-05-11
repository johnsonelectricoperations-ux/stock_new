# 거래 이력 기록 및 전략 성과 평가 모듈
import csv
import os
from datetime import datetime

TRADE_LOG = 'trades.csv'
_HEADERS = [
    'exit_date', 'code', 'name', 'sector',
    'entry_date', 'entry_price', 'exit_price',
    'qty', 'profit', 'profit_rate', 'reason', 'hold_days'
]
TOTAL_BUDGET = 10_000_000


def log_trade(code, name, sector, entry_date, entry_price, exit_price, qty, reason):
    exists = os.path.exists(TRADE_LOG)
    exit_date = datetime.now().strftime('%Y-%m-%d')
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
            exit_date, code, name, sector,
            entry_date, entry_price, exit_price,
            qty, profit, profit_rate, reason, hold_days
        ])


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
