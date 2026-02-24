"""
First-run seeder
================
On startup, if the database has no users, automatically seeds the demo accounts
(admin, Acme SaaS, Globex Commerce) so the app is immediately usable without
running seed_demo.py manually.

This runs in a background daemon thread so it does not block the API startup.
"""
import io
import logging
import sys

logger = logging.getLogger(__name__)


def seed_if_first_run() -> None:
    """Seed demo data if the database is empty. Safe to call on every startup."""
    from app.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        count = db.query(User).count()
    finally:
        db.close()

    if count > 0:
        logger.debug("First-run check: %d user(s) found, skipping demo seed", count)
        return

    logger.info("First run detected — no users in DB. Seeding demo accounts...")
    try:
        # Suppress the print-heavy output of seed_demo.main()
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            from simulation.seed_demo import main as _seed_main
            _seed_main()
        finally:
            sys.stdout = old_stdout
        logger.info("First-run demo seed complete — demo accounts ready")
    except Exception:
        logger.exception("First-run seeding failed — demo accounts will not be available")
