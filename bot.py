# -*- coding: utf-8 -*-
"""Btc_5m_100% — MEXC BTC_USDT 5m pattern alert bot. Signal-only; no trading."""
import os, json, time, logging, asyncio
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
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "8"))
DOJI_EPSILON = float(os.getenv("DOJI_EPSILON", "0"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("btc5m")

with PATTERNS_FILE.open("r", encoding="utf-8") as f:
    PATTERNS = json.load(f)
if not PATTERNS:
    raise RuntimeError("Файл patterns.json не містить шаблонів")


def candle_color(o, c):
    diff = float(c) - float(o)
    if abs(diff) <= DOJI_EPSILON:
        return "D"
    return "G" if diff > 0 else "R"


def load_state():
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            s = json.load(f)
            if s.get("version") == 1:
                return s
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"version": 1, "last_closed_ts": None, "patterns": {}, "stats": {"signals": 0, "wins": 0, "losses": 0}}


def save_state():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)

STATE = load_state()


def get_candles():
    url = f"{API_BASE}/api/v1/contract/kline/{SYMBOL}"
    r = requests.get(url, params={"interval": INTERVAL}, timeout=12)
    r.raise_for_status()
    payload = r.json()
    if not payload.get("success"):
        raise RuntimeError(f"MEXC API: {payload}")
    d = payload["data"]
    rows = []
    for i, ts in enumerate(d.get("time", [])):
        rows.append({"ts": int(ts), "open": float(d["open"][i]), "close": float(d["close"][i])})
    return sorted(rows, key=lambda x: x["ts"])


def ensure_pattern_state():
    changed = False
    for p in PATTERNS:
        k = p["id"]
        if k not in STATE["patterns"]:
            STATE["patterns"][k] = {"next_start_ts": None, "active": None, "pre_sent_for": None, "stats": {"signals": 0, "wins": 0, "losses": 0}}
            changed = True
    if changed:
        save_state()


def fmt_time(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def signal_text(p, final_ts):
    positions = ", ".join(map(str, p["positions"]))
    return (f"🚨 SIGNAL — {p['direction']}\n"
            f"📊 MEXC Futures: BTC_USDT\n⏱ Таймфрейм: 5 хв\n"
            f"🧩 Шаблон: {p['emoji']} ({p['pattern']})\n"
            f"📍 Позиції: {positions}\n"
            f"🕒 Закриття шаблону: {fmt_time(final_ts)}\n"
            f"🎯 Перевірка: наступні 6 свічок по 5 хв\n"
            f"ℹ️ Це сигнал для тестування, не гарантія результату. Бот не відкриває угоди.")


async def send_message(app, text):
    target = CHAT_ID or STATE.get("chat_id")
    if target:
        await app.bot.send_message(chat_id=target, text=text)


async def process_new_closed(app, closed):
    """Check each signal candle-by-candle; report the first favorable candle (1/6..6/6)."""
    if not closed:
        return
    by_ts = {c["ts"]: c for c in closed}
    latest_ts = closed[-1]["ts"]
    for p in PATTERNS:
        ps = STATE["patterns"][p["id"]]
        active = ps.get("active")
        if active:
            for c in closed:
                if c["ts"] <= active["signal_ts"] or c["ts"] <= active.get("last_checked_ts", active["signal_ts"]):
                    continue
                color = candle_color(c["open"], c["close"])
                active["checked"] += 1
                active["last_checked_ts"] = c["ts"]
                active["colors"].append(color)
                wanted = "G" if p["direction"] == "LONG" else "R"
                opposite = "R" if wanted == "G" else "G"
                if color == wanted:
                    n = active["checked"]
                    ps["stats"]["signals"] += 1
                    ps["stats"]["wins"] += 1
                    STATE["stats"]["signals"] += 1
                    STATE["stats"]["wins"] += 1
                    await send_message(app, f"✅ WIN {n}/6\n{p['direction']} • BTC_USDT • 5m\nШаблон: {p['emoji']} {p['pattern']}\nПерша свічка у напрямку сигналу: {n}/6")
                    ps["next_start_ts"] = c["ts"] + TF_SECONDS
                    ps["active"] = None
                    break
                if active["checked"] >= 6:
                    if all(x == opposite for x in active["colors"]):
                        ps["stats"]["signals"] += 1
                        ps["stats"]["losses"] += 1
                        STATE["stats"]["signals"] += 1
                        STATE["stats"]["losses"] += 1
                        await send_message(app, f"❌ LOSS 6/6\n{p['direction']} • BTC_USDT • 5m\nШаблон: {p['emoji']} {p['pattern']}\nУсі 6 свічок були протилежного кольору.")
                    else:
                        await send_message(app, f"⚪ VOID / НЕВИЗНАЧЕНО\nШаблон: {p['emoji']} {p['pattern']}\nУ 6 свічках був doji, результат не визначений.")
                    ps["next_start_ts"] = c["ts"] + TF_SECONDS
                    ps["active"] = None
                    break
            continue

        if ps.get("next_start_ts") is None:
            ps["next_start_ts"] = latest_ts + TF_SECONDS
            continue

        start_ts = int(ps["next_start_ts"])
        while start_ts + (p["positions"][-1] - 1) * TF_SECONDS <= latest_ts:
            req = []
            complete = True
            for pos in p["positions"]:
                candle = by_ts.get(start_ts + (pos - 1) * TF_SECONDS)
                if candle is None:
                    complete = False
                    break
                req.append(candle_color(candle["open"], candle["close"]))
            if not complete:
                start_ts += TF_SECONDS
                continue
            if "D" not in req and "".join(req) == p["pattern"]:
                final_ts = start_ts + (p["positions"][-1] - 1) * TF_SECONDS
                ps["active"] = {"signal_ts": final_ts, "checked": 0, "colors": [], "last_checked_ts": final_ts}
                await send_message(app, signal_text(p, final_ts))
                break
            start_ts += TF_SECONDS
        ps["next_start_ts"] = start_ts
    STATE["last_closed_ts"] = latest_ts
    save_state()

async def tick(app):
    try:
        candles = await asyncio.to_thread(get_candles)
        now_ts = int(time.time())
        closed = [c for c in candles if c["ts"] + TF_SECONDS <= now_ts]
        if not closed:
            return
        last_seen = STATE.get("last_closed_ts")
        if last_seen is None:
            ensure_pattern_state()
            # Establish a clean starting point on first launch.
            for p in PATTERNS:
                ps = STATE["patterns"][p["id"]]
                if ps.get("next_start_ts") is None:
                    ps["next_start_ts"] = closed[-1]["ts"] + TF_SECONDS
            STATE["last_closed_ts"] = closed[-1]["ts"]
            save_state()
        else:
            fresh = [c for c in closed if c["ts"] > int(last_seen)]
            if fresh:
                # Pass the full recent candle history: pattern positions may be separated by gaps.
                await process_new_closed(app, closed)
    except Exception:
        log.exception("Помилка циклу перевірки ринку")


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    STATE["chat_id"] = update.effective_chat.id
    save_state()
    await update.message.reply_text("🤖 Btc_5m_100% запущений. Аналізую BTC_USDT Futures, 5m.\nКоманди: /status /stats /help\nТепер цей чат отримуватиме SIGNAL та результат WIN 1/6–6/6 або LOSS 6/6. Бот не торгує автоматично.")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = sum(1 for x in STATE["patterns"].values() if x.get("active"))
    await update.message.reply_text(f"🟢 Бот працює\nШаблонів: {len(PATTERNS)}\nАктивних перевірок результату: {active}\nОстання закрита свічка: {STATE.get('last_closed_ts')}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = STATE["stats"]
    lines = [f"📊 Загальна статистика\nСигналів: {s['signals']}\nWIN: {s['wins']}\nLOSS: {s['losses']}"]
    ranked = sorted(((v['stats']['signals'], k, v['stats']) for k,v in STATE['patterns'].items()), reverse=True)
    lines.append("\nПо шаблонах (тільки завершені WIN/LOSS):")
    for n,k,st in ranked:
        if n:
            p = next(x for x in PATTERNS if x['id'] == k)
            lines.append(f"{p['emoji']} {p['pattern']} {p['direction']}: {st['wins']}W/{st['losses']}L")
    await update.message.reply_text("\n".join(lines))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("SIGNAL — усі 6 заданих позицій підтверджені після закриття.\nWIN 1/6, 2/6, 3/6, 4/6, 5/6 або 6/6 — номер першої свічки у напрямку сигналу.\nLOSS 6/6 — усі шість наступних свічок протилежного кольору.\nDoji не вважається ні зеленою, ні червоною свічкою; неоднозначний результат позначається VOID.\nПроміжні свічки між позиціями шаблону можуть бути будь-якого кольору.")

async def post_init(app):
    ensure_pattern_state()
    if CHAT_ID:
        await send_message(app, f"🟢 Btc_5m_100% онлайн. Завантажено {len(PATTERNS)} шаблонів. Режим: тільки сигнали.")
    app.job_queue.run_repeating(lambda ctx: tick(app), interval=POLL_SECONDS, first=2, name="market_scan")


def main():
    if not BOT_TOKEN:
        raise SystemExit("Не задано BOT_TOKEN у змінних середовища")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    log.info("Starting Btc_5m_100%% with %s patterns", len(PATTERNS))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
