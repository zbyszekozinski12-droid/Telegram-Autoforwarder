import os
import time
import asyncio
from typing import List, Optional

from telethon import errors
from telethon import TelegramClient
from telethon.sessions import StringSession


# ---------- Config via variables d'environnement ----------
# OBLIGATOIRES
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
# SESSION_STRING = login sans interaction (génère-le une fois en local, puis colle-le dans Render)
SESSION_STRING = os.getenv("SESSION_STRING", "")

# MODE : "forward" (par défaut) ou "list"
MODE = os.getenv("MODE", "forward").strip().lower()

# Paramètres du mode "forward"
SOURCE_CHAT_ID = os.getenv("SOURCE_CHAT_ID")   # ex: -100123456789
DESTINATION_CHAT_ID = os.getenv("DESTINATION_CHAT_ID")  # ex: -100987654321
KEYWORDS_RAW = os.getenv("KEYWORDS", "")  # ex: mot1,mot2
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))  # secondes

# Optionnel (utile seulement en local)
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")


def build_client() -> TelegramClient:
    """
    Crée le client Telethon sans interaction si SESSION_STRING est défini.
    """
    if not API_ID or not API_HASH:
        raise RuntimeError("API_ID/API_HASH manquants (variables d'environnement).")

    if SESSION_STRING:
        return TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    # Fallback (local uniquement : demandera un code SMS). À éviter sur Render.
    return TelegramClient("anon", API_ID, API_HASH)


class TelegramForwarder:
    def __init__(self, client: TelegramClient):
        self.client = client

    async def ensure_login(self):
        """
        Si SESSION_STRING est fourni, client.start() ne demandera rien.
        Sans SESSION_STRING, on tente un login interactif (local).
        """
        await self.client.connect()
        if not await self.client.is_user_authorized():
            if not PHONE_NUMBER:
                raise RuntimeError(
                    "Non autorisé et pas de SESSION_STRING. "
                    "Fournis SESSION_STRING (recommandé pour Render)."
                )
            await self.client.send_code_request(PHONE_NUMBER)
            try:
                code = input("Enter the code: ")
                await self.client.sign_in(PHONE_NUMBER, code)
            except errors.rpcerrorlist.SessionPasswordNeededError:
                password = input("Two-step verification is enabled. Enter your password: ")
                await self.client.sign_in(password=password)

    async def list_chats(self):
        await self.ensure_login()
        dialogs = await self.client.get_dialogs()
        filename = "chats_list.txt"
        with open(filename, "w", encoding="utf-8") as f:
            for d in dialogs:
                line = f"Chat ID: {d.id}, Title: {d.title}\n"
                print(line, end="")
                f.write(line)
        print(f"Liste des chats sauvegardée dans {filename}")

    @staticmethod
    def parse_keywords(raw: str) -> List[str]:
        if not raw:
            return []
        return [k.strip().lower() for k in raw.split(",") if k.strip()]

    async def forward_messages(self, source_chat_id: int, destination_chat_id: int, keywords: Optional[List[str]]):
        await self.ensure_login()

        # Dernier message existant pour éviter de re-forward l'historique
        last = await self.client.get_messages(source_chat_id, limit=1)
        last_id = last[0].id if last else 0

        print("Bot démarré. Surveillance en cours…")
        while True:
            msgs = await self.client.get_messages(source_chat_id, min_id=last_id, limit=None)
            for m in reversed(msgs):
                text = (m.text or "")  # peut être None
                if not keywords:
                    await self.client.send_message(destination_chat_id, text)
                    print(f"[FORWARD] {m.id}")
                else:
                    low = text.lower()
                    if any(k in low for k in keywords):
                        await self.client.send_message(destination_chat_id, text)
                        print(f"[FORWARD MATCH] {m.id} -> '{text[:60]}'")
                last_id = max(last_id, m.id)
            await asyncio.sleep(POLL_INTERVAL)


async def main():
    client = build_client()
    forwarder = TelegramForwarder(client)

    if MODE == "list":
        await forwarder.list_chats()
        return

    # MODE forward par défaut
    if SOURCE_CHAT_ID is None or DESTINATION_CHAT_ID is None:
        raise RuntimeError("SOURCE_CHAT_ID et DESTINATION_CHAT_ID sont requis en mode 'forward'.")

    source = int(SOURCE_CHAT_ID)
    dest = int(DESTINATION_CHAT_ID)
    keywords = TelegramForwarder.parse_keywords(KEYWORDS_RAW)

    await forwarder.forward_messages(source, dest, keywords)


if __name__ == "__main__":
    asyncio.run(main())
