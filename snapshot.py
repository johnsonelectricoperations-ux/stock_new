# 대시보드 현황을 이미지로 생성하는 모듈 (텔레그램 /snapshot 용)
import csv
import io
import os
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from matplotlib import font_manager

# 나눔고딕 한글 폰트 설정
_NANUM = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
if os.path.exists(_NANUM):
    font_manager.fontManager.addfont(_NANUM)
    matplotlib.rcParams['font.family'] = 'NanumGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

from config.settings import TOTAL_BUDGET

TRADE_LOG = 'trades.csv'


def _load_trades() -> list:
    if not os.path.exists(TRADE_LOG):
        return []
    with open(TRADE_LOG, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _get_positions():
    try:
        import main as m
        from kis_data import get_current_price
        rows = []
        for code, pos in m.positions.items():
            try:
                info = get_current_price(code)
                price = info['price']
            except Exception:
                price = pos['entry_price']
            rate = (price - pos['entry_price']) / pos['entry_price'] * 100
            profit = (price - pos['entry_price']) * pos['qty']
            rows.append({
                'name': pos.get('name', code),
                'qty': pos['qty'],
                'entry_price': pos['entry_price'],
                'current_price': price,
                'rate': rate,
                'profit': profit,
            })
        return rows
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
        return {'total': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
                'pl_ratio': 0.0, 'cumulative_profit': 0, 'mdd': 0.0}
    profits = [float(t['profit_rate']) for t in trades]
    amounts = [int(t['profit']) for t in trades]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 1
    running, peak, mdd = 0, 0, 0
    for a in amounts:
        running += a
        peak = max(peak, running)
        dd = (running - peak) / TOTAL_BUDGET * 100
        mdd = min(mdd, dd)
    return {
        'total': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(len(wins) / len(trades) * 100, 1),
        'pl_ratio': round(avg_win / avg_loss, 2) if avg_loss > 0 else 0,
        'cumulative_profit': sum(amounts),
        'mdd': round(mdd, 2),
    }


def generate_snapshot() -> bytes:
    """대시보드 스냅샷 PNG를 bytes로 반환."""
    trades = _load_trades()
    stats = _calc_stats(trades)
    positions = _get_positions()
    realized_pnl = _get_realized_pnl()
    unrealized = sum(p['profit'] for p in positions)
    total_eval = TOTAL_BUDGET + realized_pnl + unrealized

    # 다크 테마
    plt.style.use('dark_background')
    BG = '#0f1117'
    PANEL = '#1a1d27'
    BORDER = '#2a2d3a'
    GREEN = '#26d96c'
    RED = '#ff4d6a'
    GRAY = '#888888'
    WHITE = '#e0e0e0'

    fig = plt.figure(figsize=(12, 8), facecolor=BG)
    fig.patch.set_facecolor(BG)
    gs = GridSpec(3, 4, figure=fig, hspace=0.45, wspace=0.35,
                  top=0.90, bottom=0.06, left=0.05, right=0.98)

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    fig.suptitle(f'주식 자동매매 대시보드  |  {now_str}',
                 color=WHITE, fontsize=13, fontweight='bold', y=0.97)

    # ── 상단 메트릭 카드 4개 ────────────────────────────────
    def metric_card(ax, label, val_str, sub_str='', val_color=WHITE):
        ax.set_facecolor(PANEL)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(0.5, 0.72, label, ha='center', va='center',
                transform=ax.transAxes, color=GRAY, fontsize=9)
        ax.text(0.5, 0.42, val_str, ha='center', va='center',
                transform=ax.transAxes, color=val_color, fontsize=15, fontweight='bold')
        ax.text(0.5, 0.16, sub_str, ha='center', va='center',
                transform=ax.transAxes, color=GRAY, fontsize=8)

    pnl_color = GREEN if realized_pnl >= 0 else RED
    eval_ax = fig.add_subplot(gs[0, 0])
    metric_card(eval_ax, '총 평가금',
                f'{total_eval:,.0f}원',
                f'운용규모 {TOTAL_BUDGET:,}원')

    pnl_ax = fig.add_subplot(gs[0, 1])
    metric_card(pnl_ax, '누적 실현손익',
                f'{realized_pnl:+,.0f}원',
                f'{realized_pnl / TOTAL_BUDGET * 100:+.2f}%',
                val_color=pnl_color)

    wr_ax = fig.add_subplot(gs[0, 2])
    metric_card(wr_ax, '승률 / 거래수',
                f'{stats["win_rate"]}%',
                f'{stats["wins"]}승 {stats["losses"]}패 ({stats["total"]}건)')

    mdd_ax = fig.add_subplot(gs[0, 3])
    mdd_color = RED if stats['mdd'] < -10 else (WHITE if stats['mdd'] > -5 else '#ffaa55')
    metric_card(mdd_ax, '손익비 / MDD',
                f'{stats["pl_ratio"]}',
                f'MDD {stats["mdd"]}%',
                val_color=mdd_color)

    # ── 누적 손익 차트 ─────────────────────────────────────
    chart_ax = fig.add_subplot(gs[1, :3])
    chart_ax.set_facecolor(PANEL)
    for spine in chart_ax.spines.values():
        spine.set_edgecolor(BORDER)
    chart_ax.tick_params(colors=GRAY, labelsize=8)

    if trades:
        running = 0
        x_vals, y_vals = [], []
        for t in trades:
            running += int(t['profit'])
            x_vals.append(t['exit_date'])
            y_vals.append(running)

        line_color = GREEN if y_vals[-1] >= 0 else RED
        chart_ax.plot(range(len(y_vals)), y_vals, color=line_color, linewidth=2)
        chart_ax.fill_between(range(len(y_vals)), y_vals, alpha=0.15, color=line_color)
        chart_ax.axhline(0, color=BORDER, linewidth=1, linestyle='--')

        # x축 레이블 (최대 8개)
        step = max(1, len(x_vals) // 8)
        ticks = list(range(0, len(x_vals), step))
        chart_ax.set_xticks(ticks)
        chart_ax.set_xticklabels([x_vals[i] for i in ticks], rotation=30, ha='right', fontsize=7)
        chart_ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f'{v/10000:+.0f}만'))
        chart_ax.grid(axis='y', color=BORDER, linewidth=0.5, alpha=0.5)
    else:
        chart_ax.text(0.5, 0.5, '거래 데이터 없음', ha='center', va='center',
                      transform=chart_ax.transAxes, color=GRAY, fontsize=11)

    chart_ax.set_title('누적 손익 추이', color=WHITE, fontsize=10, pad=6)

    # ── 보유 종목 패널 ─────────────────────────────────────
    pos_ax = fig.add_subplot(gs[1, 3])
    pos_ax.set_facecolor(PANEL)
    for spine in pos_ax.spines.values():
        spine.set_edgecolor(BORDER)
    pos_ax.set_xticks([])
    pos_ax.set_yticks([])
    pos_ax.set_title('보유 종목', color=WHITE, fontsize=10, pad=6)

    if positions:
        y_start = 0.88
        for p in positions[:4]:
            clr = GREEN if p['rate'] >= 0 else RED
            pos_ax.text(0.05, y_start, p['name'][:6], color=WHITE, fontsize=9,
                        transform=pos_ax.transAxes, va='top')
            pos_ax.text(0.95, y_start, f'{p["rate"]:+.1f}%', color=clr, fontsize=9,
                        transform=pos_ax.transAxes, va='top', ha='right', fontweight='bold')
            pos_ax.text(0.05, y_start - 0.10, f'{p["profit"]:+,.0f}원', color=clr, fontsize=7.5,
                        transform=pos_ax.transAxes, va='top')
            y_start -= 0.22
    else:
        pos_ax.text(0.5, 0.5, '없음', ha='center', va='center',
                    transform=pos_ax.transAxes, color=GRAY, fontsize=10)

    # ── 최근 거래 내역 테이블 ──────────────────────────────
    table_ax = fig.add_subplot(gs[2, :])
    table_ax.set_facecolor(PANEL)
    for spine in table_ax.spines.values():
        spine.set_edgecolor(BORDER)
    table_ax.set_xticks([])
    table_ax.set_yticks([])
    table_ax.set_title('최근 거래 (최대 8건)', color=WHITE, fontsize=10, pad=6)

    recent = list(reversed(trades[-8:])) if trades else []
    if recent:
        col_labels = ['매도일', '종목', '진입가', '매도가', '수량', '수익률', '손익', '사유']
        col_data = []
        cell_colors = []
        for t in recent:
            rate = float(t['profit_rate'])
            profit = int(t['profit'])
            clr = '#1a3a1a' if rate >= 0 else '#3a1a1a'
            col_data.append([
                t['exit_date'],
                t['name'][:6],
                f'{int(t["entry_price"]):,}',
                f'{int(t["exit_price"]):,}',
                t['qty'],
                f'{rate:+.2f}%',
                f'{profit:+,}',
                t['reason'][:6],
            ])
            cell_colors.append([PANEL] * 8)
            cell_colors[-1][5] = clr
            cell_colors[-1][6] = clr

        tbl = table_ax.table(
            cellText=col_data,
            colLabels=col_labels,
            cellLoc='center',
            loc='center',
            bbox=[0, 0, 1, 1],
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        for (row, col), cell in tbl.get_celld().items():
            cell.set_edgecolor(BORDER)
            if row == 0:
                cell.set_facecolor('#161923')
                cell.set_text_props(color=GRAY, fontweight='bold')
            else:
                cell.set_facecolor(cell_colors[row - 1][col])
                rate_val = float(recent[row - 1]['profit_rate'])
                profit_val = int(recent[row - 1]['profit'])
                if col == 5:
                    cell.set_text_props(color=GREEN if rate_val >= 0 else RED, fontweight='bold')
                elif col == 6:
                    cell.set_text_props(color=GREEN if profit_val >= 0 else RED, fontweight='bold')
                else:
                    cell.set_text_props(color=WHITE)
    else:
        table_ax.text(0.5, 0.5, '완료된 거래 없음', ha='center', va='center',
                      transform=table_ax.transAxes, color=GRAY, fontsize=11)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', facecolor=BG, dpi=130, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


if __name__ == '__main__':
    data = generate_snapshot()
    with open('/tmp/snapshot_test.png', 'wb') as f:
        f.write(data)
    print(f'저장 완료: /tmp/snapshot_test.png ({len(data):,} bytes)')
