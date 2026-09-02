from flask import current_app
from flask_login import UserMixin
from app.models import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    picture = db.Column(db.String(512))  # Google avatar URLs can be long
    
    items = db.relationship('Item', backref='seller', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)

    @property
    def is_admin(self):
        try:
            admin_email = (current_app.config.get('ADMIN_EMAIL') or "").lower()
            return bool(admin_email and self.email and self.email.lower() == admin_email)
        except Exception:
            return False
