# -*- coding: utf-8 -*-
"""BTC_USDT MEXC Futures 5m pattern alert bot. Signal-only; no trading."""
import os
import json
import time
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BASE_DIR = Path(__file__).resolve().parent
PATTERNS_FILE = BASE_DIR / "patterns.json"
STATE_FILE = Path(os.getenv("STATE_FILE", "/data/state.json" if Path("/data").exists() else str(BASE_DIR / "state.json")))
API_BASE = os.getenv("MEXC_API_BASE", "https://api.mexc.com")
SYMBOL = "BTC_USDT"
INTERVAL = "Min5"
TF_SECONDS = 300
PATTERN_LENGTH = 11
RESULT_CANDLES = 5
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "8"))
DOJI_EPSILON = float(os.getenv("DOJI_EPSILON", "0"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("btc5m")

with PATTERNS_FILE.open("r", encoding="utf-8") as f:
    PATTERNS = json.load(f)
if len(PATTERNS) != 9:
    raise RuntimeError(f"Очікується рівно 9 шаблонів, знайдено: {len(PATTERNS)}")
for pattern in PATTERNS:
    if len(pattern["pattern"]) != PATTERN_LENGTH or pattern["direction"] not in ("LONG", "SHORT"):
        raise RuntimeError(f"Некоректний шаблон: {pattern}")


def candle_color(open_price, close_price):
    diff = float(close_price) - float(open_price)
    if abs(diff) <= DOJI_EPSILON:
        return "D"
    return "G" if diff > 0 else "R"


def empty_stats():
    return {"signals": 0, "wins": 0, "losses": 0, "voids": 0}


def load_state():
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            state = json.load(f)
            # Version 1 used the old separated-position + confirmation logic.
            if state.get("version") == 2:
                return state
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"version": 2, "last_closed_ts": None, "patterns": {}, "stats": empty_stats()}


STATE = load_state()


def save_state():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def fresh_pattern_state():
    return {"history": [], "active": None, "stats": empty_stats()}


def ensure_pattern_state():
    changed = False
    if STATE.get("version") != 2:
        STATE.clear()
        STATE.update({"version": 2, "last_closed_ts": None, "patterns": {}, "stats": empty_stats()})
        changed = True
    STATE.setdefault("stats", empty_stats())
    for key in ("signals", "wins", "losses", "voids"):
        STATE["stats"].setdefault(key, 0)
    for p in PATTERNS:
        if p["id"] not in STATE["patterns"]:
            STATE["patterns"][p["id"]] = fresh_pattern_state()
            changed = True
        else:
            ps = STATE["patterns"][p["id"]]
            ps.setdefault("history", [])
            ps.setdefault("active", None)
            ps.setdefault("stats", empty_stats())
            for key in ("signals", "wins", "losses", "voids"):
                ps["stats"].setdefault(key, 0)
    if changed:
        save_state()


def get_candles():
    url = f"{API_BASE}/api/v1/contract/kline/{SYMBOL}"
    response = requests.get(url, params={"interval": INTERVAL}, timeout=12)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"MEXC API: {payload}")
    data = payload["data"]
    rows = []
    for i, ts in enumerate(data.get("time", [])):
        rows.append({"ts": int(ts), "open": float(data["open"][i]), "close": float(data["close"][i])})
    return sorted(rows, key=lambda row: row["ts"])


def fmt_time(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def direction_color(direction):
    return "G" if direction == "LONG" else "R"


def signal_text(pattern, signal_ts):
    return (
        f"🚨 SIGNAL — {pattern['direction']}\n"
        f"📊 MEXC Futures: {SYMBOL}\n"
        f"⏱ Таймфрейм: 5 хв\n"
        f"🧩 Патерн (11 свічок): {pattern['emoji']}\n"
        f"🕒 Закриття патерну: {fmt_time(signal_ts)}\n"
        f"🎯 Перевірка: наступні 5 закритих свічок — 1/5, 2/5, 3/5, 4/5, 5/5\n"
        f"ℹ️ WIN фіксується на першій свічці у напрямку сигналу. Бот не відкриває угоди."
    )


async def send_message(app, message):
    target = CHAT_ID or STATE.get("chat_id")
    if target:
        await app.bot.send_message(chat_id=target, text=message)


def add_result(pattern_state, result, global_result):
    pattern_state["stats"][result] += 1
    STATE["stats"][result] += 1


async def finish_active(app, pattern, pattern_state, result, checked, colors):
    active = pattern_state["active"]
    if result == "wins":
        add_result(pattern_state, "wins", STATE["stats"])
        await send_message(
            app,
            f"✅ WIN {checked}/5\n{pattern['direction']} • {SYMBOL} • 5m\n"
            f"Патерн: {pattern['emoji']}\n"
            f"Перша свічка у напрямку сигналу: {checked}/5\n"
            f"Свічки перевірки: {' '.join(colors)}",
        )
    elif result == "losses":
        add_result(pattern_state, "losses", STATE["stats"])
        await send_message(
            app,
            f"❌ LOSS 5/5\n{pattern['direction']} • {SYMBOL} • 5m\n"
            f"Патерн: {pattern['emoji']}\n"
            f"Усі 5 наступних свічок були протилежного кольору.\n"
            f"Свічки перевірки: {' '.join(colors)}",
        )
    else:
        add_result(pattern_state, "voids", STATE["stats"])
        await send_message(
            app,
            f"⚪ VOID / НЕВИЗНАЧЕНО\n{pattern['direction']} • {SYMBOL} • 5m\n"
            f"Патерн: {pattern['emoji']}\n"
            f"За 5 свічок не було сигналового кольору, але була doji-свічка.\n"
            f"Свічки перевірки: {' '.join(colors)}",
        )
    pattern_state["active"] = None


async def process_candle(app, candle):
    ts = candle["ts"]
    color = candle_color(candle["open"], candle["close"])
    previous_ts = STATE.get("last_closed_ts")
    gap_before_candle = previous_ts is not None and ts != int(previous_ts) + TF_SECONDS

    for pattern in PATTERNS:
        ps = STATE["patterns"][pattern["id"]]
        history = ps["history"]
        active = ps.get("active")

        # A gap breaks both the contiguous pattern and the five-candle result window.
        if gap_before_candle:
            if active:
                await finish_active(app, pattern, ps, "voids", active["checked"], active["colors"])
            history.clear()
            history.append(color)
            continue

        was_active = active is not None
        if active:
            active["checked"] += 1
            active["last_ts"] = ts
            active["colors"].append(color)
            if color == direction_color(pattern["direction"]):
                await finish_active(app, pattern, ps, "wins", active["checked"], active["colors"])
            elif active["checked"] == RESULT_CANDLES:
                opposite = "R" if pattern["direction"] == "LONG" else "G"
                if all(x == opposite for x in active["colors"]):
                    await finish_active(app, pattern, ps, "losses", 5, active["colors"])
                else:
                    await finish_active(app, pattern, ps, "voids", 5, active["colors"])

        # Keep a rolling contiguous candle history for exact 11-candle matching.
        history.append(color)
        if len(history) > PATTERN_LENGTH:
            del history[:-PATTERN_LENGTH]

        # Candles inside an active result window cannot also start a new signal.
        if was_active:
            continue

        if len(history) == PATTERN_LENGTH and "D" not in history:
            if "".join(history) == pattern["pattern"]:
                ps["active"] = {"signal_ts": ts, "last_ts": ts, "checked": 0, "colors": []}
                ps["stats"]["signals"] += 1
                STATE["stats"]["signals"] += 1
                await send_message(app, signal_text(pattern, ts))

    STATE["last_closed_ts"] = ts
    save_state()


async def process_new_closed(app, fresh_candles):
    for candle in fresh_candles:
        await process_candle(app, candle)


async def tick(app):
    try:
        candles = await asyncio.to_thread(get_candles)
        now_ts = int(time.time())
        closed = [c for c in candles if c["ts"] + TF_SECONDS <= now_ts]
        if not closed:
            return
        ensure_pattern_state()
        last_seen = STATE.get("last_closed_ts")
        if last_seen is None:
            # Start clean: seed only the previous 10 colors, so no old signal is emitted on startup.
            seed = closed[-PATTERN_LENGTH + 1:]
            for pattern in PATTERNS:
                STATE["patterns"][pattern["id"]]["history"] = [
                    candle_color(c["open"], c["close"]) for c in seed
                ]
            STATE["last_closed_ts"] = closed[-1]["ts"]
            save_state()
            return

        fresh = [c for c in closed if c["ts"] > int(last_seen)]
        if fresh:
            # If the API no longer contains the last processed candle, don't invent missing bars.
            if closed[0]["ts"] > int(last_seen) + TF_SECONDS:
                log.warning("Пропущено частину історії свічок MEXC; перевірки з розривом буде позначено VOID")
            await process_new_closed(app, fresh)
    except Exception:
        log.exception("Помилка циклу перевірки ринку")


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    STATE["chat_id"] = update.effective_chat.id
    save_state()
    await update.message.reply_text(
        "🤖 Бот запущений. Аналізую BTC_USDT Futures, 5m.\n"
        "Команди: /status /stats /help\n"
        "Сигнал надсилається після закриття 11-ї свічки патерну. Результат перевіряється на наступних 5 свічках: WIN 1/5–5/5 або LOSS 5/5. Автоторгівлі немає."
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = sum(1 for value in STATE["patterns"].values() if value.get("active"))
    await update.message.reply_text(
        f"🟢 Бот працює\nШаблонів: {len(PATTERNS)}\n"
        f"Активних перевірок результату: {active}\n"
        f"Остання закрита свічка: {STATE.get('last_closed_ts')}"
    )


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = STATE["stats"]
    lines = [
        "📊 Загальна статистика",
        f"Сигналів: {stats['signals']}",
        f"WIN: {stats['wins']}",
        f"LOSS: {stats['losses']}",
        f"VOID: {stats['voids']}",
        "\nПо патернах:",
    ]
    for pattern in PATTERNS:
        st = STATE["patterns"][pattern["id"]]["stats"]
        lines.append(f"{pattern['emoji']} {pattern['direction']}: {st['signals']} сигналів, {st['wins']}W/{st['losses']}L/{st['voids']}V")
    await update.message.reply_text("\n".join(lines))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Правила бота:\n"
        "1) Шукає рівно 9 заданих патернів, кожен — 11 послідовних закритих свічок без пропусків.\n"
        "2) Напрямок LONG/SHORT заданий у patterns.json. Сигнал надсилається відразу після закриття 11-ї свічки патерну; додаткового підтвердження немає.\n"
        "3) Після сигналу перевіряються наступні 5 закритих свічок. Якщо з'являється свічка у напрямку сигналу, результат WIN 1/5, 2/5, 3/5, 4/5 або 5/5 — за номером першої такої свічки.\n"
        "4) Якщо всі 5 свічок протилежного кольору — LOSS 5/5. Якщо напрямного кольору не було, але була doji — VOID.\n"
        "Бот лише надсилає сигнали, угоди автоматично не відкриває."
    )


async def post_init(app):
    ensure_pattern_state()
    if CHAT_ID:
        await send_message(app, f"🟢 Бот онлайн. Завантажено {len(PATTERNS)} патернів. Режим: тільки сигнали.")
    app.job_queue.run_repeating(lambda ctx: tick(app), interval=POLL_SECONDS, first=2, name="market_scan")


def main():
    if not BOT_TOKEN:
        raise SystemExit("Не задано BOT_TOKEN у змінних середовища")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    log.info("Starting BTC 5m signal bot with %s patterns", len(PATTERNS))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
