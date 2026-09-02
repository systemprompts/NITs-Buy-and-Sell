from flask import Blueprint, redirect, url_for, current_app, flash
from flask_login import login_user, logout_user
from authlib.integrations.flask_client import OAuth
from app.models import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__)

oauth = OAuth()


@auth_bp.record_once
def on_load(state):
    oauth.init_app(state.app)
    if not state.app.config.get('MOCK_AUTH'):
        oauth.register(
            name='google',
            server_metadata_url=state.app.config['GOOGLE_DISCOVERY_URL'],
            client_kwargs={'scope': 'openid email profile'},
        )


def _domain_allowed(email):
    allowed = current_app.config['ALLOWED_DOMAIN'].lower()
    domain = email.rsplit('@', 1)[-1]
    return domain == allowed or domain.endswith('.' + allowed)


@auth_bp.route('/login')
def login():
    if current_app.config.get('MOCK_AUTH'):
        user = User.query.filter_by(email="student@nits.ac.in").first()
        if not user:
            user = User(
                google_id="mock_ggl_id",
                email="student@nits.ac.in",
                name="Mock Student",
                picture="https://ui-avatars.com/api/?name=Mock+Student",
            )
            db.session.add(user)
            db.session.commit()
        login_user(user)
        flash("Logged in with mock auth.", "success")
        return redirect(url_for('main.index'))

    redirect_uri = url_for('auth.authorize', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/authorize')
def authorize():
    try:
        token = oauth.google.authorize_access_token()
    except Exception:  # noqa: BLE001 - user denied, state mismatch, network, ...
        current_app.logger.warning("OAuth token exchange failed", exc_info=True)
        flash("Login failed. Please try again.", "danger")
        return redirect(url_for('main.index'))

    user_info = token.get('userinfo') or {}
    email = (user_info.get('email') or '').strip().lower()
    google_id = user_info.get('sub')

    if not email or not google_id:
        flash("Google did not return your account details. Please try again.", "danger")
        return redirect(url_for('main.index'))

    if user_info.get('email_verified') is False:
        flash("Your Google email is not verified.", "danger")
        return redirect(url_for('main.index'))

    allowed_domain = current_app.config['ALLOWED_DOMAIN']
    if not _domain_allowed(email):
        flash(f"Sign in with your @{allowed_domain} account to use nits.shop.", "danger")
        return redirect(url_for('main.index'))

    name = user_info.get('name') or email.split('@', 1)[0]
    picture = user_info.get('picture')

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User(google_id=google_id, email=email, name=name, picture=picture)
        db.session.add(user)
    else:
        # Keep profile details fresh on every login.
        user.email = email
        user.name = name
        user.picture = picture
    db.session.commit()

    login_user(user)
    flash("Signed in.", "success")
    return redirect(url_for('main.index'))


@auth_bp.route('/logout')
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('main.index'))
