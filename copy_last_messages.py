import os
import asyncio
from typing import List, Optional

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message
from telethon.errors import rpcerrorlist


API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

SOURCE_CHAT_ID = int(os.getenv("SOURCE_CHAT_ID", "0"))       # ex: -100123456789
DESTINATION_CHAT_ID = int(os.getenv("DESTINATION_CHAT_ID", "0"))
LIMIT = int(os.getenv("LIMIT", "100"))                       # combien de messages copier
SLEEP_BETWEEN = float(os.getenv("SLEEP_BETWEEN", "0.4"))     # petite pause anti-flood
USE_LINK_ON_PROTECTED = os.getenv("USE_LINK_ON_PROTECTED", "1")  # "1" => texte + lien si media impossible


def build_private_link(chat_id: int, msg_id: int) -> str:
    cid = str(chat_id)
    if cid.startswith("-100"):
        cid = cid[4:]
    return f"https://t.me/c/{cid}/{msg_id}"


async def _send_media_piece(client: TelegramClient, dest_id: int, m: Message, caption: Optional[str]):
    # Priorité à photo/vidéo pour garder l’aperçu/lecteur
    if getattr(m, "photo", None):
        await client.send_file(dest_id, m.photo, caption=caption, link_preview=False)
        return
    if getattr(m, "video", None):
        await client.send_file(dest_id, m.video, caption=caption, link_preview=False, supports_streaming=True)
        return
    if getattr(m, "document", None):
        await client.send_file(dest_id, m.document, caption=caption, link_preview=False)
        return
    # Pas de media connu -> texte seul
    if caption:
        await client.send_message(dest_id, caption, link_preview=False)


async def _repost_message(client: TelegramClient, m: Message, dest_id: int):
    """
    Repost texte + media (photos/vidéos/docs/vocaux). Gère albums.
    Ne contourne pas la protection : si envoi impossible, fallback texte + lien.
    """
    text = (m.message or "")
    caption = text.strip() or None

    # Albums (messages groupés)
    if getattr(m, "grouped_id", None):
        pieces: List[Message] = []
        for delta in range(0, 20):
            a = await client.get_messages(m.chat_id, ids=m.id + delta)
            if not a or getattr(a, "grouped_id", None) != m.grouped_id:
                continue
            pieces.append(a)

        if pieces:
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
                    await client.send_file(dest_id, media_objs, caption=caption, link_preview=False, supports_streaming=True)
                    return
                except Exception:
                    pass  # on tombera sur le fallback
        # Fallback album
        if caption:
            await client.send_message(dest_id, caption, link_preview=False)
        if USE_LINK_ON_PROTECTED == "1":
            link = build_private_link(m.chat_id, m.id)
            await client.send_message(dest_id, f"[Voir le message d’origine]({link})", link_preview=False)
        return

    # Média unique
    if m.media:
        try:
            await _send_media_piece(client, dest_id, m, caption)
        except Exception:
            # Fallback si échec (ex : contenu protégé)
            if caption:
                await client.send_message(dest_id, caption, link_preview=False)
            if USE_LINK_ON_PROTECTED == "1":
                link = build_private_link(m.chat_id, m.id)
                await client.send_message(dest_id, f"[Voir le message d’origine]({link})", link_preview=False)
        return

    # Texte seul
    if text:
        await client.send_message(dest_id, text, link_preview=False)


async def main():
    if not (API_ID and API_HASH and SESSION_STRING and SOURCE_CHAT_ID and DESTINATION_CHAT_ID):
        raise SystemExit("Manque une variable (API_ID, API_HASH, SESSION_STRING, SOURCE_CHAT_ID, DESTINATION_CHAT_ID).")

    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        msgs = await client.get_messages(SOURCE_CHAT_ID, limit=LIMIT)

        # On renvoie du plus ancien au plus récent
        for m in reversed(msgs):
            # 1) ESSAI FORWARD NATIF (serveur-à-serveur, sans téléchargement)
            try:
                await client.forward_messages(DESTINATION_CHAT_ID, m)
                await asyncio.sleep(SLEEP_BETWEEN)
                continue
            except (rpcerrorlist.ChatForwardsRestrictedError,
                    rpcerrorlist.ForbiddenError,
                    rpcerrorlist.MessageNotModifiedError,
                    Exception):
                # 2) SINON REPOST (re-upload par le client)
                await _repost_message(client, m, DESTINATION_CHAT_ID)
                await asyncio.sleep(SLEEP_BETWEEN)


if __name__ == "__main__":
    asyncio.run(main())
