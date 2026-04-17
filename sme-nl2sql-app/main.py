"""
Flask application factory.

Entry point for Gunicorn / Cloud Run:
    gunicorn main:app

Environment Variables:
    PORT: Server port (default: 8080)
    LOG_LEVEL: Python logging level (default: INFO)
"""

import logging
import os
from flask import Flask
from app.routes import bp, ui


def _configure_logging():
    """Set up structured logging for Cloud Run."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Reduce verbosity of third-party loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def create_app() -> Flask:
    _configure_logging()

    application = Flask(__name__)

    # Security: Set request size limits (1 MB default)
    # Prevents large payload attacks while allowing reasonable NL questions
    application.config["MAX_CONTENT_LENGTH"] = int(
        os.environ.get("MAX_CONTENT_LENGTH", 1024 * 1024)  # 1 MB
    )

    application.register_blueprint(ui)
    application.register_blueprint(bp)

    logger = logging.getLogger(__name__)
    logger.info(
        f"App initialized; MAX_CONTENT_LENGTH={application.config['MAX_CONTENT_LENGTH']} bytes"
    )

    return application


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    logging.info(f"Starting Flask dev server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
