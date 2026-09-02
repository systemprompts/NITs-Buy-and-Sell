"""Image compression + object storage.

Storage backend is chosen at config time:
  * ``supabase`` — uploads to a Supabase Storage bucket over the S3 API.
  * ``local``    — writes to ``app/static/uploads`` (local development only;
                   Vercel's filesystem is read-only and ephemeral).

Every image is compressed so it never exceeds ``MAX_IMAGE_BYTES`` (2 MB by
default) before it is stored.
"""

import io
import os
import threading
import uuid

from flask import current_app, url_for
from PIL import Image, ImageOps

_S3_LOCK = threading.Lock()
_s3_client = None


class StorageError(Exception):
    """Raised when an image cannot be processed or stored."""


# --------------------------------------------------------------------------- #
# Compression
# --------------------------------------------------------------------------- #
def compress_image(raw, max_bytes, max_dim=1920):
    """Compress ``raw`` image bytes to ``<= max_bytes`` where possible.

    Returns ``(data, ext, content_type)``.
    """
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise StorageError(f"could not read image ({exc})")

    # Honour EXIF orientation, then drop the metadata.
    img = ImageOps.exif_transpose(img)

    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )

    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    # Keep transparency as an optimised PNG when it still fits; otherwise
    # flatten onto white and continue as JPEG.
    if has_alpha:
        rgba = img.convert("RGBA")
        buf = io.BytesIO()
        rgba.save(buf, format="PNG", optimize=True)
        if buf.tell() <= max_bytes:
            return buf.getvalue(), "png", "image/png"
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    for quality in (85, 75, 65, 55, 45, 35):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= max_bytes:
            return buf.getvalue(), "jpg", "image/jpeg"

    # Still too big: keep shrinking the dimensions.
    work = img
    buf = io.BytesIO()
    work.save(buf, format="JPEG", quality=45, optimize=True, progressive=True)
    while max(work.size) > 640 and buf.tell() > max_bytes:
        w, h = work.size
        work = work.resize((int(w * 0.8), int(h * 0.8)), Image.LANCZOS)
        buf = io.BytesIO()
        work.save(buf, format="JPEG", quality=55, optimize=True, progressive=True)

    return buf.getvalue(), "jpg", "image/jpeg"


# --------------------------------------------------------------------------- #
# S3 client (lazy)
# --------------------------------------------------------------------------- #
def _get_s3():
    global _s3_client
    if _s3_client is not None:
        return _s3_client
    with _S3_LOCK:
        if _s3_client is None:
            import boto3
            from botocore.config import Config as BotoConfig

            cfg = current_app.config
            _s3_client = boto3.client(
                "s3",
                endpoint_url=cfg["SUPABASE_S3_ENDPOINT"],
                region_name=cfg["SUPABASE_S3_REGION"],
                aws_access_key_id=cfg["SUPABASE_S3_ACCESS_KEY_ID"],
                aws_secret_access_key=cfg["SUPABASE_S3_SECRET_ACCESS_KEY"],
                config=BotoConfig(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},  # forcePathStyle
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
    return _s3_client


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def save_image(file_storage):
    """Compress ``file_storage`` and store it. Returns the storage key."""
    cfg = current_app.config
    raw = file_storage.read()
    if not raw:
        raise StorageError("the file is empty")

    data, ext, content_type = compress_image(raw, cfg["MAX_IMAGE_BYTES"])
    key = f"items/{uuid.uuid4().hex}.{ext}"

    if cfg["STORAGE_BACKEND"] == "supabase":
        try:
            _get_s3().put_object(
                Bucket=cfg["SUPABASE_STORAGE_BUCKET"],
                Key=key,
                Body=data,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"upload failed ({exc})")
    else:
        path = os.path.join(current_app.root_path, "static", "uploads", key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)

    return key


def delete_image(key):
    """Best-effort removal of a stored image."""
    if not key:
        return
    cfg = current_app.config
    if cfg["STORAGE_BACKEND"] == "supabase":
        try:
            _get_s3().delete_object(Bucket=cfg["SUPABASE_STORAGE_BUCKET"], Key=key)
        except Exception as exc:  # noqa: BLE001
            current_app.logger.warning("could not delete %s from storage: %s", key, exc)
    else:
        path = os.path.join(current_app.root_path, "static", "uploads", key)
        if os.path.exists(path):
            os.remove(path)


def image_url(key):
    """Public URL for a stored image key (falls back to a placeholder)."""
    if not key:
        return url_for("static", filename="images/no-image.svg")
    cfg = current_app.config
    if cfg["STORAGE_BACKEND"] == "supabase":
        return f"{cfg['SUPABASE_PUBLIC_URL_BASE']}/{cfg['SUPABASE_STORAGE_BUCKET']}/{key}"
    return url_for("static", filename=f"uploads/{key}")
