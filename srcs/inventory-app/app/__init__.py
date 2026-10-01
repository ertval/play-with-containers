import os
import time
import logging
from flask import Flask
from sqlalchemy import text
from sqlalchemy.engine import URL
from app.extensions import db
from app.movies import movies_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [inventory-app] %(message)s"
)
logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    """Return required secret env var or raise (no hardcoded fallback for secrets)."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required secret environment variable: {name}. "
            "Set it via .env / compose environment (see .env.example)."
        )
    return value


def create_app():
    app = Flask(__name__)

    # Secrets MUST come from env; host/port/db-name keep safe non-secret defaults.
    db_user = _require_env("INVENTORY_DB_USER")
    db_password = _require_env("INVENTORY_DB_PASSWORD")
    db_host = os.getenv("INVENTORY_DB_HOST", "").strip() or "inventory-database"
    db_port = os.getenv("INVENTORY_DB_PORT", "").strip() or "5432"
    db_name = os.getenv("INVENTORY_DB_NAME", "").strip() or "inventory_db"

    # URL.create() percent-encodes the password; f-string interpolation would
    # break on any password containing @ : / ? # or %.
    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        "postgresql+psycopg2",
        username=db_user,
        password=db_password,
        host=db_host,
        port=db_port,
        database=db_name,
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    app.register_blueprint(movies_bp)

    # Healthcheck endpoint for internal probes
    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "healthy"}, 200

    # Wait for database readiness and initialize schema
    with app.app_context():
        max_retries = 30
        for attempt in range(1, max_retries + 1):
            try:
                db.session.execute(text("SELECT 1"))
                db.create_all()
                logger.info("Successfully connected to inventory database and initialized schema.")
                break
            except Exception as e:
                logger.warning(f"Database connection attempt {attempt}/{max_retries} failed: {e}")
                if attempt == max_retries:
                    logger.error("Could not connect to inventory database after max retries.")
                    raise
                time.sleep(2)

    return app

