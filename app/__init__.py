import os

from flask import Flask, Response, render_template, redirect, request, flash, url_for
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config

csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Vercel (and any reverse proxy) terminates TLS and forwards the original
    # host/scheme in X-Forwarded-* headers. Trust them so url_for(_external=True)
    # and the OAuth callback URL are generated as https with the real host.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    from app.models import db, login_manager
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.models.item import CONDITIONS

    @app.context_processor
    def inject_globals():
        return {"SITE_URL": app.config["SITE_URL"], "CONDITIONS": CONDITIONS}

    @app.template_filter("rupee")
    def _rupee(value):
        """Format a price string as ₹ with Indian digit grouping."""
        if value is None or str(value).strip() in ("", "None"):
            return "—"
        raw = str(value).replace(",", "").strip()
        try:
            number = float(raw)
        except ValueError:
            return "₹" + str(value)
        if number == int(number):
            number = int(number)
        digits = str(abs(number))
        frac = ""
        if "." in digits:
            digits, frac = digits.split(".", 1)
            frac = "." + frac
        if len(digits) > 3:
            head, tail = digits[:-3], digits[-3:]
            groups = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            if head:
                groups.insert(0, head)
            digits = ",".join(groups) + "," + tail
        sign = "-" if number < 0 else ""
        return f"₹{sign}{digits}{frac}"

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "storage": app.config["STORAGE_BACKEND"]}, 200

    @app.get("/robots.txt")
    def robots():
        body = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /auth/\n"
            "Disallow: /post\n"
            f"Sitemap: {app.config['SITE_URL']}/sitemap.xml\n"
        )
        return Response(body, mimetype="text/plain")

    @app.get("/sitemap.xml")
    def sitemap():
        from app.models.item import Item

        base = app.config["SITE_URL"]
        urls = [(base + "/", None)]
        try:
            for item in Item.query.order_by(Item.created_at.desc()).limit(2000):
                urls.append((f"{base}/item/{item.id}", item.created_at))
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("sitemap query failed: %s", exc)

        parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for loc, lastmod in urls:
            parts.append("<url><loc>%s</loc>%s</url>" % (
                loc,
                f"<lastmod>{lastmod.date().isoformat()}</lastmod>" if lastmod else "",
            ))
        parts.append("</urlset>")
        return Response("\n".join(parts), mimetype="application/xml")

    @app.errorhandler(413)
    def _payload_too_large(_e):
        flash("Those images exceed the ~4.5 MB upload limit. Choose fewer or smaller photos.", "warning")
        return render_template("error.html", code=413,
                               title="Upload too large",
                               message="Your images add up to more than the server accepts in one request."), 413

    @app.errorhandler(404)
    def _not_found(_e):
        return render_template("error.html", code=404,
                               title="Page not found",
                               message="That listing may have been de-listed, or the link is wrong."), 404

    @app.errorhandler(CSRFError)
    def _csrf_error(_e):
        flash("Your session expired. Please try that again.", "warning")
        return redirect(request.referrer or url_for("main.index"))

    @app.errorhandler(Exception)
    def _handle_exception(e):
        app.logger.exception("Unhandled Exception: %s", e)
        if os.environ.get("SHOW_DEBUG_ERRORS") == "true":
            import traceback
            return Response(f"<h1>500 Internal Server Error</h1><pre>{traceback.format_exc()}</pre>", status=500, mimetype="text/html")
        return render_template("error.html", code=500,
                               title="Server Error",
                               message="An unexpected error occurred. Please try again later."), 500


    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        db.create_all()
        print("Database tables created.")

    # Create tables on boot. Idempotent; guarded so a transient DB hiccup on a
    # cold start doesn't take the whole app down (the next invocation retries).
    if os.environ.get("AUTO_CREATE_DB", "true").lower() in ("true", "1", "t"):
        with app.app_context():
            try:
                db.create_all()
            except Exception as exc:  # noqa: BLE001
                app.logger.error("db.create_all() failed: %s", exc)

    return app
