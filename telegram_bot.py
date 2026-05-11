# 텔레그램 봇 알림 및 명령어 처리 모듈
import requests as _requests
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

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
        '/balance — 잔고 조회\n'
        '/signal — 오늘 매수 신호 종목\n'
        '/buy 종목코드 수량\n'
        '/sell 종목코드 수량\n'
        '/sellall 종목코드\n'
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
    lines = []
    for code, pos in positions.items():
        try:
            info = get_current_price(code)
            rate = (info['price'] - pos['entry_price']) / pos['entry_price'] * 100
            lines.append(f"{pos['name']}: {rate:+.2f}% ({info['price']:,}원)")
        except Exception:
            lines.append(f"{pos['name']}: 조회 실패")
    await update.message.reply_text('\n'.join(lines))

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    await update.message.reply_text('잔고 조회 기능은 추후 구현 예정입니다.')

async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    await update.message.reply_text('매일 장 시작 08:30에 신호를 분석합니다.')

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    if len(context.args) != 2:
        await update.message.reply_text('사용법: /buy 종목코드 수량\n예: /buy 005930 10')
        return
    from kis_order import buy_stock
    from main import positions
    from kis_data import get_current_price
    code, qty = context.args[0], int(context.args[1])
    try:
        buy_stock(code, qty)
        info = get_current_price(code)
        positions[code] = {'name': code, 'qty': qty, 'entry_price': info['price'], 'peak_price': info['price']}
        await update.message.reply_text(f'{code} {qty}주 수동 매수 완료.')
    except Exception as e:
        await update.message.reply_text(f'매수 실패: {e}')

async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_auth(update): return
    if len(context.args) != 2:
        await update.message.reply_text('사용법: /sell 종목코드 수량\n예: /sell 005930 10')
        return
    from kis_order import sell_stock
    code, qty = context.args[0], int(context.args[1])
    try:
        sell_stock(code, qty)
        await update.message.reply_text(f'{code} {qty}주 수동 매도 완료.')
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
        sell_stock(code, positions[code]['qty'])
        del positions[code]
        await update.message.reply_text(f'{code} 전량매도 완료.')
    except Exception as e:
        await update.message.reply_text(f'매도 실패: {e}')

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
    app.add_handler(CommandHandler('buy', cmd_buy))
    app.add_handler(CommandHandler('sell', cmd_sell))
    app.add_handler(CommandHandler('sellall', cmd_sellall))
    app.add_handler(CommandHandler('pause', cmd_pause))
    app.add_handler(CommandHandler('resume', cmd_resume))
    app.add_handler(CommandHandler('stop', cmd_stop))
    return app
