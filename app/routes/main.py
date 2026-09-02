from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort
from flask_login import login_required, current_user
from app.models import db
from app.models.item import Item, ItemImage, ItemContact, Comment, CONDITIONS, STATUS_AVAILABLE, STATUS_SOLD
from app.storage import save_image, delete_image, StorageError

main_bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
CONTACT_TYPES = {'phone', 'whatsapp', 'email', 'hostel'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _parse_condition(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value in CONDITIONS else None


@main_bp.route('/')
def index():
    items = Item.query.order_by(Item.created_at.desc()).all()
    available = sum(1 for i in items if not i.is_sold)
    return render_template('index.html', items=items,
                           total_count=len(items), available_count=available)


@main_bp.route('/post', methods=['GET', 'POST'])
@login_required
def post_item():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        price = (request.form.get('price') or '').strip()
        is_negotiable = request.form.get('is_negotiable') == 'on'
        condition = _parse_condition(request.form.get('condition'))
        condition_details = (request.form.get('condition_details') or '').strip() or None
        online_link = (request.form.get('online_link') or '').strip() or None
        online_price = (request.form.get('online_price') or '').strip() or None

        images = request.files.getlist('images')
        candidate_files = [f for f in images if f and f.filename and allowed_file(f.filename)]

        if not title or not description or not candidate_files:
            flash("Title, description, and at least one image are required.", "warning")
            return redirect(url_for('main.post_item'))

        max_images = current_app.config['MAX_IMAGES_PER_ITEM']

        # Compress + upload every image first. Nothing touches the database until
        # all images are safely stored, so a storage failure can't leave a
        # half-created listing behind.
        uploaded_keys = []
        try:
            for file in candidate_files[:max_images]:
                uploaded_keys.append(save_image(file))
        except StorageError as exc:
            for key in uploaded_keys:
                delete_image(key)
            flash(f"Could not process your images: {exc}.", "danger")
            return redirect(url_for('main.post_item'))

        new_item = Item(
            title=title,
            description=description,
            price=price,
            is_negotiable=is_negotiable,
            condition=condition,
            condition_details=condition_details,
            online_link=online_link,
            online_price=online_price,
            seller_id=current_user.id,
        )
        db.session.add(new_item)
        db.session.flush()  # assign new_item.id without committing yet

        # Process Contacts
        contact_types = request.form.getlist('contact_type[]')
        contact_values = request.form.getlist('contact_value[]')
        for c_type, c_val in zip(contact_types, contact_values):
            c_val = c_val.strip()
            if c_val and c_type in CONTACT_TYPES:
                db.session.add(ItemContact(item_id=new_item.id, contact_type=c_type, contact_value=c_val))

        # Process Images
        for key in uploaded_keys:
            db.session.add(ItemImage(item_id=new_item.id, filename=key))

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            for key in uploaded_keys:
                delete_image(key)
            current_app.logger.exception("Failed to save item")
            flash("Something went wrong while saving your item. Please try again.", "danger")
            return redirect(url_for('main.post_item'))

        flash("Item posted successfully!", "success")
        return redirect(url_for('main.item_detail', item_id=new_item.id))

    return render_template('post_item.html')


@main_bp.route('/item/<int:item_id>')
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)
    return render_template('item_detail.html', item=item)


@main_bp.route('/item/<int:item_id>/comment', methods=['POST'])
@login_required
def post_comment(item_id):
    Item.query.get_or_404(item_id)
    content = (request.form.get('content') or '').strip()
    if content:
        db.session.add(Comment(content=content[:2000], item_id=item_id, user_id=current_user.id))
        db.session.commit()
        flash("Comment added.", "success")
    return redirect(url_for('main.item_detail', item_id=item_id))


@main_bp.route('/item/<int:item_id>/status', methods=['POST'])
@login_required
def toggle_status(item_id):
    item = Item.query.get_or_404(item_id)
    if item.seller_id != current_user.id:
        abort(403)
    item.status = STATUS_AVAILABLE if item.is_sold else STATUS_SOLD
    db.session.commit()
    flash(f"Marked as {item.status.lower()}.", "success")
    return redirect(url_for('main.item_detail', item_id=item_id))


@main_bp.route('/item/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    if item.seller_id != current_user.id:
        abort(403)

    image_keys = [img.filename for img in item.images]

    db.session.delete(item)
    db.session.commit()

    for key in image_keys:
        delete_image(key)

    flash("Item deleted successfully.", "success")
    return redirect(url_for('main.index'))
