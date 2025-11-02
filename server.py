import os
import time
import threading
import asyncio
import requests

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

import TelegramForwarder  # ton bot (repost-only, stable)

# --- Fonction pour relancer le bot s'il plante ---
def run_bot_resilient():
    while True:
        try:
            asyncio.run(TelegramForwarder.main())
        except Exception as e:
            print(f"[bot] crashed: {e}. Restarting in 5s...")
            time.sleep(5)
        else:
            print("[bot] main() returned. Restarting in 5s...")
            time.sleep(5)

# --- Fonction keep-alive pour éviter que Render mette le container en veille ---
def keep_alive():
    url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', '')}/"
    while True:
        if url and url != "https://":
            try:
                requests.get(url, timeout=10)
                print("[keep-alive] Ping envoyé ✅")
            except Exception as e:
                print(f"[keep-alive] Erreur : {e}")
        time.sleep(600)  # toutes les 10 minutes

# --- FastAPI ---
app = FastAPI(title="Telegram Autoforwarder API")

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
    connected = getattr(TelegramForwarder, "is_connected", False)
    return {"ok": True, "connected": connected, "t": int(time.time())}

# --- Health avancé (HEAD) pour UptimeRobot gratuit ---
@app.head("/healthz")
def healthz_head(request: Request):
    connected = getattr(TelegramForwarder, "is_connected", False)
    return JSONResponse(content={"ok": True, "connected": connected, "t": int(time.time())})

# --- Lancement du bot et du serveur ---
if __name__ == "__main__":
    threading.Thread(target=run_bot_resilient, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
