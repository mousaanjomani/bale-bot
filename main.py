"""Entry point: starts the Bale bot poller and the web dashboard.

Run:  python main.py
The supervisor script (installer/run_bot.ps1) keeps this process alive on
the customer server and restarts it after upgrades (exit code 42).
"""
import logging
import logging.handlers

from app import config, store


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fh = logging.handlers.RotatingFileHandler(
        config.LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)


def main() -> None:
    setup_logging()
    log = logging.getLogger("main")

    store.init_db()

    from app import org
    org.seed_if_empty()

    from app.bot import poller
    poller.start()
    log.info("Bot poller started.")

    from app import updater
    updater.start_auto_check()
    log.info("Auto update-check started (every 2 hours).")

    from app.web.server import app as flask_app
    from waitress import serve

    host = config.get("web_host", "0.0.0.0")
    port = int(config.get("web_port", 8585))
    log.info("Dashboard listening on http://%s:%s", host, port)
    serve(flask_app, host=host, port=port, threads=8)


if __name__ == "__main__":
    main()
