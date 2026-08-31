"""Long-polling loop that pulls updates from Bale and dispatches them."""
import logging
import threading
import time

from app import config, store
from app.bot import handlers
from app.bot.client import BaleClient

log = logging.getLogger("bale.poller")


class BotPoller(threading.Thread):
    """Background thread: polls getUpdates and dispatches to handlers."""

    def __init__(self):
        super().__init__(daemon=True, name="bot-poller")
        self._stop = threading.Event()
        self.client: BaleClient | None = None
        self.bot_info: dict | None = None
        self.started_at = time.time()
        self.last_update_at: float | None = None
        self.status = "starting"  # starting | running | no-token | error | disabled

    def stop(self):
        self._stop.set()

    def run(self):
        offset = int(store.kv_get("update_offset", 0) or 0)
        while not self._stop.is_set():
            if not config.get("bot_enabled", True):
                self.status = "disabled"
                time.sleep(2)
                continue

            token = config.get("bot_token", "")
            if not token:
                self.status = "no-token"
                time.sleep(3)
                continue

            if self.client is None or self.client.token != token:
                self.client = BaleClient(token)
                self.bot_info = self.client.get_me()
                if self.bot_info:
                    log.info("Bot connected: @%s", self.bot_info.get("username"))

            updates = self.client.get_updates(offset=offset, poll_timeout=25)
            if updates is None:
                self.status = "error"
                time.sleep(5)
                continue

            self.status = "running"
            for upd in updates:
                offset = max(offset, upd.get("update_id", 0) + 1)
                self.last_update_at = time.time()
                try:
                    handlers.dispatch(self.client, upd)
                except Exception:
                    log.exception("Handler error for update %s", upd.get("update_id"))
            if updates:
                store.kv_set("update_offset", offset)


_poller: BotPoller | None = None


def start() -> BotPoller:
    global _poller
    _poller = BotPoller()
    _poller.start()
    return _poller


def get() -> BotPoller | None:
    return _poller
