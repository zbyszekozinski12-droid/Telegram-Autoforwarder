# server.py
import os, time, threading
from fastapi import FastAPI
import uvicorn

def run_bot():
    import TelegramForwarder
    if hasattr(TelegramForwarder, "main"):
        TelegramForwarder.main()
    else:
        # fallback si pas de main()
        from TelegramForwarder import build_client
        c = build_client()
        c.start()
        c.run_until_disconnected()

app = FastAPI()
@app.get("/")
def ok():
    return {"ok": True, "t": int(time.time())}

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
