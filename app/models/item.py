from datetime import datetime, timedelta
from app.models import db


def get_ist_time():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)


# Condition grading scale (1..6), shared by the model, the post form and the
# item page. `bars` drives the little 6-segment meter shown on the chip.
CONDITIONS = {
    6: {"label": "Brand New", "detail": "Unused, in original packaging; perfect physical and functional state."},
    5: {"label": "Like New", "detail": "Opened or used once; no visible wear and 100% functional."},
    4: {"label": "Good", "detail": "Minor cosmetic scuffs or scratches; 100% functional."},
    3: {"label": "Fair", "detail": "Heavy visible wear and tear; 100% functional."},
    2: {"label": "Damaged", "detail": "Significant cosmetic issues; minor functional defects or missing non-essential parts."},
    1: {"label": "For Parts", "detail": "Major functional failure or broken; for salvage or repair only."},
}

STATUS_AVAILABLE = "Available"
STATUS_SOLD = "Sold"


class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.String(50))
    is_negotiable = db.Column(db.Boolean, default=False)
    condition = db.Column(db.Integer)  # 1 to 6
    condition_details = db.Column(db.String(500))  # optional free-text notes
    online_link = db.Column(db.String(500))
    online_price = db.Column(db.String(50))

    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_ist_time)
    status = db.Column(db.String(20), default=STATUS_AVAILABLE)

    images = db.relationship('ItemImage', backref='item', lazy=True, cascade='all, delete-orphan')
    contacts = db.relationship('ItemContact', backref='item', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='item', lazy=True, cascade='all, delete-orphan', order_by='Comment.created_at.asc()')

    @property
    def is_sold(self):
        return self.status == STATUS_SOLD

    @property
    def condition_label(self):
        c = CONDITIONS.get(self.condition)
        return c["label"] if c else None

    @property
    def condition_detail(self):
        c = CONDITIONS.get(self.condition)
        return c["detail"] if c else None


class ItemImage(db.Model):
    __tablename__ = 'item_images'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    # Storage key (e.g. "items/<uuid>.jpg") for the configured storage backend.
    filename = db.Column(db.String(255), nullable=False)

    @property
    def url(self):
        from app.storage import image_url
        return image_url(self.filename)


class ItemContact(db.Model):
    __tablename__ = 'item_contacts'
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    contact_type = db.Column(db.String(20), nullable=False)  # phone | whatsapp | email | hostel
    contact_value = db.Column(db.String(255), nullable=False)


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_anonymous = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_ist_time)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

