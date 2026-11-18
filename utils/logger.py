"""
utils/logger.py
===============
Logging terpusat ke logs/app.log (berputar, maksimal 2 MB x 5 berkas) dan ke terminal. Berguna untuk menelusuri
masalah di lapangan tanpa harus selalu menyalakan terminal.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask


def setup_logger(app: Flask) -> None:
    log_folder = app.config["LOG_FOLDER"]
    os.makedirs(log_folder, exist_ok=True)
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")

    handler = RotatingFileHandler(os.path.join(log_folder, "app.log"), maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in app.logger.handlers):
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
