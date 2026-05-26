import sqlite3
from flask import Flask, g
from webapp import filters as _filters
from webapp.db import init_webapp_tables


def create_app(db_path: str) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE"] = db_path
    init_webapp_tables(db_path)

    @app.before_request
    def open_db():
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

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
