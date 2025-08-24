import os
import time
import threading
import asyncio

from fastapi import FastAPI
import uvicorn
import TelegramForwarder  # ton bot

def run_bot_resilient():
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

@app.get("/")
def health():
    return {"ok": True, "t": int(time.time())}

@app.get("/healthz")
def healthz():
    try:
        connected = bool(TelegramForwarder.is_connected)
    except Exception:
        connected = False
    return {"ok": True, "connected": connected, "t": int(time.time())}

if __name__ == "__main__":
    threading.Thread(target=run_bot_resilient, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
