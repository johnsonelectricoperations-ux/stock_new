# 텔레그램 봇 알림 및 명령어 처리 모듈
import requests as _requests
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TOTAL_BUDGET

logging.basicConfig(level=logging.WARNING)

_trading_paused = False

def send_message(text: str):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    _requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})

def _check_auth(update: Update) -> bool:
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    await update.message.reply_text('안녕하세요. 주식 자동매매 봇입니다.\n/help 으로 명령어 목록을 확인하세요.')

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    msg = (
        '명령어 목록\n'
        '/status — 보유 종목 + 수익률\n'
        '/balance — 운용 현황 조회\n'
        '/signal — 현재 매수 신호 종목 조회\n'
        '/report — 누적 성과 리포트\n'
        '/errors [n] — 최근 에러 n개 조회 (기본 10)\n'
        '/buy 종목코드 수량\n'
        '/sell 종목코드 수량\n'
        '/sellall 종목코드\n'
        '/register 종목코드 수량 진입가 — 기존 보유 종목 등록 (주문 없음)\n'
        '/pause — 자동매매 일시중지\n'
        '/resume — 자동매매 재개\n'
        '/stop — 시스템 종료'
    )
    await update.message.reply_text(msg)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    from main import positions
    if not positions:
        await update.message.reply_text('보유 중인 종목이 없습니다.')
        return
    from kis_data import get_current_price
    lines = ['보유 종목 현황']
    for code, pos in positions.items():
        try:
            info = get_current_price(code)
            rate = (info['price'] - pos['entry_price']) / pos['entry_price'] * 100
            profit = (info['price'] - pos['entry_price']) * pos['qty']
            lines.append(f"{pos['name']}({code})\n  {pos['qty']}주 | {rate:+.2f}% ({profit:+,}원)")
        except Exception:
            lines.append(f"{pos['name']}: 조회 실패")
    await update.message.reply_text('\n'.join(lines))

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    from main import positions
    from kis_data import get_current_price

    invested = 0
    eval_amt = 0
    profit_loss = 0
    lines = [f'운용 현황 (운용규모: {TOTAL_BUDGET:,}원)']

    for code, pos in positions.items():
        try:
            info = get_current_price(code)
            cost = pos['entry_price'] * pos['qty']
            value = info['price'] * pos['qty']
            profit = value - cost
            rate = profit / cost * 100
            invested += cost
            eval_amt += value
            profit_loss += profit
            lines.append(f"{pos['name']}: {rate:+.2f}% ({profit:+,}원)")
        except Exception:
            pass

    from main import realized_pnl
    remaining = TOTAL_BUDGET + realized_pnl - invested
    lines.append(f'\n투자금: {invested:,}원')
    lines.append(f'평가금: {eval_amt:,}원')
    lines.append(f'잔여예수금: {remaining:,}원')
    lines.append(f'미실현 수익: {profit_loss:+,}원')
    lines.append(f'누적 실현손익: {realized_pnl:+,}원')

    await update.message.reply_text('\n'.join(lines))

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    from performance import get_report
    await update.message.reply_text(get_report())

async def cmd_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    from error_monitor import get_recent_errors
    n = 10
    if context.args:
        try:
            n = int(context.args[0])
        except ValueError:
            pass
    await update.message.reply_text(get_recent_errors(n))

async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    await update.message.reply_text('신호 분석 중... (1~2분 소요)')
    try:
        from kis_sector import get_leading_sector_signals
        signals = get_leading_sector_signals(top_sectors=2)
        if not signals:
            await update.message.reply_text('현재 매수 신호 없음.')
            return
        lines = [f'매수 신호 {len(signals)}종목']
        for s in signals:
            lines.append(f"[{s['sector']}] {s['name']}({s['code']})\n  모멘텀 {s['momentum']:+.2f}% | {s['detail']}")
        await update.message.reply_text('\n'.join(lines))
    except Exception as e:
        await update.message.reply_text(f'신호 조회 실패: {e}')

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    if len(context.args) != 2:
        await update.message.reply_text('사용법: /buy 종목코드 수량\n예: /buy 005930 10')
        return
    from kis_order import buy_stock
    from main import positions
    from kis_data import get_current_price
    try:
        qty = int(context.args[1])
    except ValueError:
        await update.message.reply_text('수량은 숫자로 입력하세요.\n예: /buy 005930 10')
        return
    code = context.args[0]
    try:
        buy_stock(code, qty)
        info = get_current_price(code)
        positions[code] = {
            'name': code, 'qty': qty,
            'entry_price': info['price'], 'peak_price': info['price'],
            'entry_date': datetime.now().strftime('%Y-%m-%d'),
            'break_even_set': False, 'floor_price': 0, 'partial_sold': False,
        }
        await update.message.reply_text(f'{code} {qty}주 수동 매수 완료.\n{info["price"]:,}원 × {qty}주 = {info["price"]*qty:,}원')
    except Exception as e:
        await update.message.reply_text(f'매수 실패: {e}')

async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    if len(context.args) != 2:
        await update.message.reply_text('사용법: /sell 종목코드 수량\n예: /sell 005930 10')
        return
    from kis_order import sell_stock
    try:
        qty = int(context.args[1])
    except ValueError:
        await update.message.reply_text('수량은 숫자로 입력하세요.\n예: /sell 005930 10')
        return
    code = context.args[0]
    try:
        from main import positions, add_realized_pnl
        from kis_data import get_current_price
        from performance import log_trade
        from datetime import datetime
        info = get_current_price(code)
        sell_stock(code, qty)
        if code in positions:
            pos = positions[code]
            profit = (info['price'] - pos['entry_price']) * qty
            add_realized_pnl(profit)
            log_trade(
                code=code, name=pos['name'], sector=pos.get('sector', ''),
                entry_date=pos.get('entry_date', datetime.now().strftime('%Y-%m-%d')),
                entry_time=pos.get('entry_time', ''),
                entry_price=pos['entry_price'], exit_price=info['price'],
                qty=qty, reason='수동매도',
            )
            positions[code]['qty'] -= qty
            if positions[code]['qty'] <= 0:
                del positions[code]
        await update.message.reply_text(f'{code} {qty}주 수동 매도 완료. 수익: {profit:+,}원')
    except Exception as e:
        await update.message.reply_text(f'매도 실패: {e}')

async def cmd_sellall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    if len(context.args) != 1:
        await update.message.reply_text('사용법: /sellall 종목코드\n예: /sellall 005930')
        return
    from kis_order import sell_stock
    from main import positions
    code = context.args[0]
    if code not in positions:
        await update.message.reply_text(f'{code} 보유중이 아닙니다.')
        return
    try:
        from main import add_realized_pnl
        from kis_data import get_current_price
        from performance import log_trade
        from datetime import datetime
        pos = positions[code]
        info = get_current_price(code)
        sell_stock(code, pos['qty'])
        profit = (info['price'] - pos['entry_price']) * pos['qty']
        add_realized_pnl(profit)
        log_trade(
            code=code, name=pos['name'], sector=pos.get('sector', ''),
            entry_date=pos.get('entry_date', datetime.now().strftime('%Y-%m-%d')),
            entry_time=pos.get('entry_time', ''),
            entry_price=pos['entry_price'], exit_price=info['price'],
            qty=pos['qty'], reason='수동전량매도',
        )
        del positions[code]
        await update.message.reply_text(f'{code} 전량매도 완료. 수익: {profit:+,}원')
    except Exception as e:
        await update.message.reply_text(f'매도 실패: {e}')

async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """KIS 계좌에 이미 보유 중인 종목을 positions에 수동 등록 (실제 주문 없음)."""
    if not _check_auth(update): return
    if len(context.args) != 3:
        await update.message.reply_text('사용법: /register 종목코드 수량 진입가\n예: /register 036930 20 162100')
        return
    from main import positions
    from kis_data import get_current_price
    code = context.args[0]
    try:
        qty = int(context.args[1])
        entry_price = int(context.args[2])
    except ValueError:
        await update.message.reply_text('수량과 진입가는 숫자로 입력하세요.')
        return
    if code in positions:
        await update.message.reply_text(f'{code} 이미 positions에 등록되어 있습니다.')
        return
    try:
        info = get_current_price(code)
        name = info.get('name', code)
    except Exception:
        name = code
    positions[code] = {
        'name': name, 'sector': '', 'qty': qty,
        'entry_price': entry_price,
        'entry_date': datetime.now().strftime('%Y-%m-%d'),
        'entry_time': '',
        'peak_price': entry_price,
        'min_price': entry_price,
        'break_even_set': False, 'floor_price': 0, 'partial_sold': False,
    }
    rate = (info['price'] - entry_price) / entry_price * 100
    await update.message.reply_text(
        f'{name}({code}) {qty}주 등록 완료.\n'
        f'진입가: {entry_price:,}원 | 현재가: {info["price"]:,}원 | {rate:+.2f}%\n'
        f'이제 자동 매도 감시 대상에 포함됩니다.'
    )

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _trading_paused
    if not _check_auth(update): return
    _trading_paused = True
    await update.message.reply_text('자동매매가 일시중지되었습니다.')

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _trading_paused
    if not _check_auth(update): return
    _trading_paused = False
    await update.message.reply_text('자동매매를 재개합니다.')

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    await update.message.reply_text('시스템을 종료합니다.')
    import os, signal
    os.kill(os.getpid(), signal.SIGTERM)

def is_paused():
    return _trading_paused

def build_app():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('help', cmd_help))
    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('balance', cmd_balance))
    app.add_handler(CommandHandler('signal', cmd_signal))
    app.add_handler(CommandHandler('report', cmd_report))
    app.add_handler(CommandHandler('errors', cmd_errors))
    app.add_handler(CommandHandler('buy', cmd_buy))
    app.add_handler(CommandHandler('sell', cmd_sell))
    app.add_handler(CommandHandler('sellall', cmd_sellall))
    app.add_handler(CommandHandler('register', cmd_register))
    app.add_handler(CommandHandler('pause', cmd_pause))
    app.add_handler(CommandHandler('resume', cmd_resume))
    app.add_handler(CommandHandler('stop', cmd_stop))
    return app
