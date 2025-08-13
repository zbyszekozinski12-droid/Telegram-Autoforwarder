import os
import time
import asyncio
from typing import List, Optional

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import Message


# ========= Config via variables d'environnement =========
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

MODE = os.getenv("MODE", "forward").strip().lower()  # "forward" ou "list"

SOURCE_CHAT_ID = os.getenv("SOURCE_CHAT_ID")
DESTINATION_CHAT_ID = os.getenv("DESTINATION_CHAT_ID")
KEYWORDS_RAW = os.getenv("KEYWORDS", "")            # ex: "mot1,mot2"
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))

# Fallback: si un média ne peut pas être renvoyé (p. ex. contenu protégé),
# envoyer un lien vers le message original ? "1" = oui, "0" = non
USE_LINK_ON_PROTECTED = os.getenv("USE_LINK_ON_PROTECTED", "1")

# Optionnel pour usage local (pas Render)
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "")


def build_client() -> TelegramClient:
    if not API_ID or not API_HASH:
        raise RuntimeError("API_ID/API_HASH manquants.")
    if SESSION_STRING:
        return TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    # Fallback local (évite pour Render)
    return TelegramClient("anon", API_ID, API_HASH)


def build_private_link(chat_id: int, msg_id: int) -> str:
    """Lien vers message privé (visible par les membres du canal/groupe)."""
    cid = str(chat_id)
    if cid.startswith("-100"):
        cid = cid[4:]
    return f"https://t.me/c/{cid}/{msg_id}"


class TelegramForwarder:
    def __init__(self, client: TelegramClient):
        self.client = client

    async def ensure_login(self):
        await self.client.connect()
        if not await self.client.is_user_authorized():
            if not PHONE_NUMBER:
                raise RuntimeError(
                    "Non autorisé et pas de SESSION_STRING. Fournis SESSION_STRING (recommandé pour Render)."
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
        return [k.strip().lower() for k in raw.split(",") if k.strip()] if raw else []

    async def _send_media_piece(self, dest_id: int, m: Message, caption: Optional[str]):
        """
        Envoie UNE pièce média avec le meilleur type pour avoir l'aperçu.
        Ne contourne pas la protection : si Telethon/Telegram refuse, on lève et l'appelant gère.
        """
        # Priorité à photo/vidéo pour gardez la preview/lecteur natif
        if getattr(m, "photo", None):
            await self.client.send_file(dest_id, m.photo, caption=caption, link_preview=False)
            return
        if getattr(m, "video", None):
            await self.client.send_file(dest_id, m.video, caption=caption, link_preview=False, supports_streaming=True)
            return
        if getattr(m, "document", None):
            # Peut être image envoyée en "document", pdf, zip, etc.
            await self.client.send_file(dest_id, m.document, caption=caption, link_preview=False)
            return
        # Pas de média reconnu -> on tente juste le texte si présent
        if caption:
            await self.client.send_message(dest_id, caption, link_preview=False)

    async def _repost_message(self, m: Message, dest_id: int):
        """
        Reposte texte + médias (photos/vidéos/docs) avec la légende si présente.
        Gère aussi les albums avec preview. Si l'envoi média échoue (ex: contenu protégé),
        envoie le texte, et éventuellement un lien vers l'original si USE_LINK_ON_PROTECTED = "1".
        """
        text = (m.message or "")
        caption = text.strip() or None

        # ---- Albums (messages groupés) ----
        if getattr(m, "grouped_id", None):
            # Récupérer les pièces de l'album proches
            pieces: List[Message] = []
            for delta in range(0, 20):
                a = await self.client.get_messages(m.chat_id, ids=m.id + delta)
                if not a or getattr(a, "grouped_id", None) != m.grouped_id:
                    continue
                pieces.append(a)

            if pieces:
                # Envoi groupé : on convertit chaque pièce en "media object"
                media_objs = []
                for a in pieces:
                    if getattr(a, "photo", None):
                        media_objs.append(a.photo)
                    elif getattr(a, "video", None):
                        media_objs.append(a.video)
                    elif getattr(a, "document", None):
                        media_objs.append(a.document)

                if media_objs:
                    try:
                        await self.client.send_file(dest_id, media_objs, caption=caption, link_preview=False, supports_streaming=True)
                        return
                    except Exception as e:
                        # Échec (ex: contenu protégé, taille, etc.) -> fallback
                        pass

            # Fallback album: texte + (lien)
            if caption:
                await self.client.send_message(dest_id, caption, link_preview=False)
            if USE_LINK_ON_PROTECTED == "1":
                link = build_private_link(m.chat_id, m.id)
                await self.client.send_message(dest_id, f"[Voir le message d’origine]({link})", link_preview=False)
            return

        # ---- Média unique ----
        if m.media:
            try:
                await self._send_media_piece(dest_id, m, caption)
            except Exception:
                # Échec média -> fallback texte + (lien)
                if caption:
                    await self.client.send_message(dest_id, caption, link_preview=False)
                if USE_LINK_ON_PROTECTED == "1":
                    link = build_private_link(m.chat_id, m.id)
                    await self.client.send_message(dest_id, f"[Voir le message d’origine]({link})", link_preview=False)
            return

        # ---- Texte seul ----
        if text:
            await self.client.send_message(dest_id, text, link_preview=False)

    async def forward_loop(self, source_chat_id: int, destination_chat_id: int, keywords: Optional[List[str]]):
        await self.ensure_login()

        # Point de départ pour éviter de re-poster l'historique
        last = await self.client.get_messages(source_chat_id, limit=1)
        last_id = last[0].id if last else 0

        print("Bot démarré. Surveillance en cours…")
        while True:
            msgs = await self.client.get_messages(source_chat_id, min_id=last_id, limit=None)
            for m in reversed(msgs):
                msg_text = (m.message or "")
                send_it = True if not keywords else any(k in msg_text.lower() for k in keywords)

                if send_it:
                    # Si le forward NATIF est autorisé par la source, tu peux utiliser ceci :
                    # await self.client.forward_messages(destination_chat_id, m)
                    # Sinon, on "repost" pour avoir la preview des médias
                    await self._repost_message(m, destination_chat_id)
                    print(f"Transféré: {m.id}")

                last_id = max(last_id, m.id)

            await asyncio.sleep(POLL_INTERVAL)


async def main():
    client = build_client()
    fwd = TelegramForwarder(client)

    if MODE == "list":
        await fwd.list_chats()
        return

    if SOURCE_CHAT_ID is None or DESTINATION_CHAT_ID is None:
        raise RuntimeError("SOURCE_CHAT_ID et DESTINATION_CHAT_ID sont requis en mode 'forward'.")

    source = int(SOURCE_CHAT_ID)
    dest = int(DESTINATION_CHAT_ID)
    keywords = TelegramForwarder.parse_keywords(KEYWORDS_RAW)

    await fwd.forward_loop(source, dest, keywords)


if __name__ == "__main__":
    asyncio.run(main())
