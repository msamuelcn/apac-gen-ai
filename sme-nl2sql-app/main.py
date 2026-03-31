"""
Flask application factory.

Entry point for Gunicorn / Cloud Run:
    gunicorn main:app
"""

import os
from flask import Flask
from app.routes import bp


def create_app() -> Flask:
    application = Flask(__name__)
    application.register_blueprint(bp)
    return application


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
