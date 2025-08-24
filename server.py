import os
import time
import threading
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

import TelegramForwarder  # ton bot (repost-only, stable)

def run_bot_resilient():
    # Redémarre le bot s'il plante ou si main() sort
    while True:
        try:
            asyncio.run(TelegramForwarder.main())
        except Exception as e:
            print(f"[bot] crashed: {e}. restarting in 5s...")
            time.sleep(5)
        else:
            print("[bot] main() returned. restarting in 5s...")
            time.sleep(5)

app = FastAPI()

# --- Health simple (GET) ---
@app.get("/")
def health_get():
    return {"ok": True, "t": int(time.time())}

# --- Health simple (HEAD) pour UptimeRobot gratuit ---
@app.head("/")
def health_head(request: Request):
    return JSONResponse(content={"ok": True, "t": int(time.time())})

# --- Health avancé (GET) : indique si le bot est connecté à Telegram ---
@app.get("/healthz")
def healthz_get():
    try:
        connected = bool(TelegramForwarder.is_connected)
    except Exception:
        connected = False
    return {"ok": True, "connected": connected, "t": int(time.time())}

# --- Health avancé (HEAD) pour UptimeRobot gratuit ---
@app.head("/healthz")
def healthz_head(request: Request):
    try:
        connected = bool(TelegramForwarder.is_connected)
    except Exception:
        connected = False
    return JSONResponse(content={"ok": True, "connected": connected, "t": int(time.time())})

if __name__ == "__main__":
    threading.Thread(target=run_bot_resilient, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
