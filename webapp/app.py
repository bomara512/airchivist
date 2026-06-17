import re
import sqlite3
from flask import Flask, g
from webapp import filters as _filters
from webapp.db import init_webapp_tables, get_stats, get_watch_later_video_ids


def _regexp(pattern, string):
    return bool(re.search(pattern, string or "", re.IGNORECASE))


def create_app(db_path: str) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE"] = db_path
    init_webapp_tables(db_path)

    @app.before_request
    def open_db():
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.create_function("regexp", 2, _regexp)

    @app.context_processor
    def inject_stats():
        db = g.get("db")
        if db is None:
            return {}
        return {"stats": get_stats(db)}

    @app.context_processor
    def inject_watch_later_ids():
        db = g.get("db")
        if db is None:
            return {"watch_later_ids": set()}
        return {"watch_later_ids": get_watch_later_video_ids(db)}

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    from webapp import routes
    app.register_blueprint(routes.bp)

    app.jinja_env.filters["view_count"] = _filters.format_view_count
    app.jinja_env.filters["date"] = _filters.format_date
    app.jinja_env.filters["duration"] = _filters.format_duration

    return app
