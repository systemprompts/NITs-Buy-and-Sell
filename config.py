import os
from urllib.parse import quote_plus, unquote, urlparse
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


def _bool(val, default=False):
    if val is None:
        return default
    return str(val).lower() in ("true", "1", "t", "yes")


def _clean_database_url(url):
    if not url or "@" not in url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    prefix_and_creds, sep, host_and_path = url.rpartition("@")
    if "://" in prefix_and_creds:
        scheme, creds = prefix_and_creds.split("://", 1)
        if ":" in creds:
            user, pwd = creds.split(":", 1)
            raw_pwd = unquote(pwd)
            encoded_pwd = quote_plus(raw_pwd)
            return f"{scheme}://{user}:{encoded_pwd}@{host_and_path}"
    return url



def _resolve_database_uri():
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not url:
        user = os.environ.get("POSTGRES_USER") or os.environ.get("user")
        password = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("password")
        host = os.environ.get("POSTGRES_HOST") or os.environ.get("host")
        port = os.environ.get("POSTGRES_PORT") or os.environ.get("port") or "5432"
        dbname = os.environ.get("POSTGRES_DB") or os.environ.get("dbname") or "postgres"
        if user and password and host:
            url = f"postgresql://{user}:{quote_plus(password)}@{host}:{port}/{dbname}"

    if not url:
        return "sqlite:///" + os.path.join(basedir, "app.db")

    url = _clean_database_url(url)

    if url.startswith("postgresql://") and "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"

    return url



def _resolve_storage():
    supabase_url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    endpoint = (os.environ.get("SUPABASE_S3_ENDPOINT") or "").rstrip("/")
    ref = ""
    if supabase_url:
        ref = (urlparse(supabase_url).hostname or "").split(".")[0]
    elif endpoint:
        ref = (urlparse(endpoint).hostname or "").split(".")[0]

    if not supabase_url and ref:
        supabase_url = f"https://{ref}.supabase.co"
    if not endpoint and ref:
        endpoint = f"https://{ref}.storage.supabase.co/storage/v1/s3"

    access_key = os.environ.get("SUPABASE_S3_ACCESS_KEY_ID")
    secret_key = os.environ.get("SUPABASE_S3_SECRET_ACCESS_KEY")
    bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "item-images")
    region = os.environ.get("SUPABASE_S3_REGION", "ap-south-1")

    public_url_base = f"{supabase_url}/storage/v1/object/public" if supabase_url else ""
    backend = "supabase" if (endpoint and access_key and secret_key) else "local"

    return {
        "SUPABASE_URL": supabase_url,
        "SUPABASE_STORAGE_BUCKET": bucket,
        "SUPABASE_S3_ENDPOINT": endpoint,
        "SUPABASE_S3_REGION": region,
        "SUPABASE_S3_ACCESS_KEY_ID": access_key,
        "SUPABASE_S3_SECRET_ACCESS_KEY": secret_key,
        "SUPABASE_PUBLIC_URL_BASE": public_url_base,
        "STORAGE_BACKEND": backend,
    }



class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "super-secret-key-change-in-production"
    SQLALCHEMY_DATABASE_URI = _resolve_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    if SQLALCHEMY_DATABASE_URI.startswith("postgresql"):
        SQLALCHEMY_ENGINE_OPTIONS = {"poolclass": NullPool, "pool_pre_ping": True}

    PREFERRED_URL_SCHEME = "https"
    SITE_URL = (os.environ.get("SITE_URL") or "https://nits.shop").rstrip("/")
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_SSL_STRICT = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = bool(os.environ.get("VERCEL") or (os.environ.get("SITE_URL") and os.environ.get("SITE_URL").startswith("https")))

    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 4500000))

    MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", 2097152))
    MAX_IMAGES_PER_ITEM = int(os.environ.get("MAX_IMAGES_PER_ITEM", 5))

    _storage = _resolve_storage()
    SUPABASE_URL = _storage["SUPABASE_URL"]
    SUPABASE_STORAGE_BUCKET = _storage["SUPABASE_STORAGE_BUCKET"]
    SUPABASE_S3_ENDPOINT = _storage["SUPABASE_S3_ENDPOINT"]
    SUPABASE_S3_REGION = _storage["SUPABASE_S3_REGION"]
    SUPABASE_S3_ACCESS_KEY_ID = _storage["SUPABASE_S3_ACCESS_KEY_ID"]
    SUPABASE_S3_SECRET_ACCESS_KEY = _storage["SUPABASE_S3_SECRET_ACCESS_KEY"]
    SUPABASE_PUBLIC_URL_BASE = _storage["SUPABASE_PUBLIC_URL_BASE"]
    STORAGE_BACKEND = _storage["STORAGE_BACKEND"]

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", None)
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", None)
    GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

    # If real Google OAuth credentials are provided, ALWAYS use real Google OAuth!
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        MOCK_AUTH = False
    else:
        _mock = os.environ.get("MOCK_AUTH")
        MOCK_AUTH = _bool(_mock, False if os.environ.get("VERCEL") else True)

    ALLOWED_DOMAIN = "nits.ac.in"
    ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()


