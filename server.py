# server.py
import os
import time
import threading
import asyncio

from fastapi import FastAPI
import uvicorn

import TelegramForwarder  # notre script ci-dessus


def run_bot():
    asyncio.run(TelegramForwarder.main())


app = FastAPI()

@app.get("/")
def health():
    return {"ok": True, "t": int(time.time())}

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
