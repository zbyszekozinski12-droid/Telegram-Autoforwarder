import os
import time
import threading
import asyncio

from fastapi import FastAPI, Query
import uvicorn

import TelegramForwarder  # bot en continu
from copy_last_messages import main as copy_last_main  # one-shot


def run_bot():
    asyncio.run(TelegramForwarder.main())


app = FastAPI()

@app.get("/")
def health():
    return {"ok": True, "t": int(time.time())}

@app.post("/copy")
async def copy_endpoint(limit: int = Query(100, ge=1, le=1000)):
    os.environ["LIMIT"] = str(limit)
    await copy_last_main()
    return {"status": "done", "copied": limit}

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
