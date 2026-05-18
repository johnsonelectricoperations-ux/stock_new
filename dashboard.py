# 자동매매 운용 현황을 보여주는 Flask 웹 대시보드
import csv
import os
from datetime import datetime
from flask import Flask, render_template, jsonify
from config.settings import TOTAL_BUDGET

app = Flask(__name__)

TRADE_LOG = 'trades.csv'
SIGNAL_LOG = 'signal_log.csv'
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '5000'))


def _load_trades() -> list:
    if not os.path.exists(TRADE_LOG):
        return []
    with open(TRADE_LOG, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _get_positions_data() -> list:
    """main 모듈에서 positions 가져오기 (서비스 실행 중일 때)."""
    try:
        import main as m
        from kis_data import get_current_price
        result = []
        for code, pos in m.positions.items():
            try:
                info = get_current_price(code)
                price = info['price']
            except Exception:
                price = pos['entry_price']
            cost = pos['entry_price'] * pos['qty']
            value = price * pos['qty']
            rate = (price - pos['entry_price']) / pos['entry_price'] * 100
            result.append({
                'code': code,
                'name': pos.get('name', code),
                'sector': pos.get('sector', ''),
                'qty': pos['qty'],
                'entry_price': pos['entry_price'],
                'current_price': price,
                'profit': value - cost,
                'rate': round(rate, 2),
                'entry_date': pos.get('entry_date', ''),
            })
        return result
    except Exception:
        return []


def _get_realized_pnl() -> int:
    try:
        import main as m
        return m.realized_pnl
    except Exception:
        trades = _load_trades()
        return sum(int(t['profit']) for t in trades)


def _calc_stats(trades: list) -> dict:
    if not trades:
        return {
            'total': 0, 'win_rate': 0, 'pl_ratio': 0,
            'cumulative_profit': 0, 'cumulative_rate': 0, 'mdd': 0,
        }
    profits = [float(t['profit_rate']) for t in trades]
    amounts = [int(t['profit']) for t in trades]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 1
    pl_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    cumulative_profit = sum(amounts)

    running, peak, mdd = 0, 0, 0
    for a in amounts:
        running += a
        if running > peak:
            peak = running
        dd = (running - peak) / TOTAL_BUDGET * 100
        if dd < mdd:
            mdd = dd

    return {
        'total': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(len(wins) / len(trades) * 100, 1),
        'pl_ratio': pl_ratio,
        'cumulative_profit': cumulative_profit,
        'cumulative_rate': round(cumulative_profit / TOTAL_BUDGET * 100, 2),
        'mdd': round(mdd, 2),
    }


def _build_chart_data(trades: list) -> dict:
    """누적 손익 차트용 데이터 (날짜, 누적손익)."""
    labels, values = [], []
    running = 0
    for t in trades:
        running += int(t['profit'])
        labels.append(t['exit_date'])
        values.append(running)
    return {'labels': labels, 'values': values}


@app.route('/')
def index():
    trades = _load_trades()
    stats = _calc_stats(trades)
    positions = _get_positions_data()
    realized_pnl = _get_realized_pnl()
    chart = _build_chart_data(trades)

    unrealized = sum(p['profit'] for p in positions)
    total_eval = TOTAL_BUDGET + realized_pnl + unrealized

    recent_trades = list(reversed(trades[-30:]))

    return render_template(
        'dashboard.html',
        stats=stats,
        positions=positions,
        recent_trades=recent_trades,
        chart_labels=chart['labels'],
        chart_values=chart['values'],
        total_budget=TOTAL_BUDGET,
        realized_pnl=realized_pnl,
        unrealized=unrealized,
        total_eval=total_eval,
        updated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )


@app.route('/api/status')
def api_status():
    trades = _load_trades()
    stats = _calc_stats(trades)
    positions = _get_positions_data()
    realized_pnl = _get_realized_pnl()
    unrealized = sum(p['profit'] for p in positions)
    return jsonify({
        'stats': stats,
        'positions': positions,
        'realized_pnl': realized_pnl,
        'unrealized': unrealized,
        'total_eval': TOTAL_BUDGET + realized_pnl + unrealized,
        'updated_at': datetime.now().isoformat(),
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=False)
