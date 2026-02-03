from pathlib import Path
import environ

# Load environment variables
env = environ.Env()
environ.Env.read_env()

BASE_DIR = Path(__file__).resolve().parent.parent

# ✅ Security & Debug
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DEBUG", default=True)
FACEBOOK_APP_ID = env("FACEBOOK_APP_ID")
FACEBOOK_APP_SECRET = env("FACEBOOK_APP_SECRET")
FACEBOOK_VERIFY_TOKEN = env("FACEBOOK_VERIFY_TOKEN")
INSTAGRAM_BUSINESS_REDIRECT_URI = env("INSTAGRAM_BUSINESS_REDIRECT_URI")

# Stripe Configuration
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_LOOKUP_KEY = "standard_monthly"

ALLOWED_HOSTS = [
    'localhost', '0.0.0.0', '127.0.0.1',
    'postflow.photo', 'www.postflow.photo', '3.70.194.91', '3.74.49.26', 'ec2-3-74-49-26.eu-central-1.compute.amazonaws.com',
    'https://postflow.photo', 'https://www.postflow.photo',
    'http://postflow.photo', 'http://www.postflow.photo',
]


CSRF_TRUSTED_ORIGINS = [
    'https://localhost', 'https://*.amazonlightsail.com', 'https://127.0.0.1',
    'https://postflow.pp347jb6gimu4.eu-central-1.cs.amazonlightsail.com',
    'https://postflow.photo', 'https://www.postflow.photo'
]

# ✅ Installed Apps (Including `contenttypes` to Fix RuntimeError)
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',  # 🔹 Required for many-to-many relationships and generic relations
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'tailwind',
    'theme',
    'postflow',
    'instagram',
    'pixelfed',
    'mastodon_native',
    'mastodon_integration',
    'subscriptions',
    'analytics',
    'analytics_pixelfed',  # Pixelfed analytics
    'analytics_mastodon',  # Mastodon analytics
    'analytics_instagram',  # Instagram analytics
    'django_tasks',  # Django 6.0 background tasks
    'django_tasks.backends.database',  # Database backend for django-tasks
    'django_browser_reload',
    'django_htmx',
]

# ✅ Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'subscriptions.middleware.SubscriptionRequiredMiddleware',
    "django_browser_reload.middleware.BrowserReloadMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = 'core.urls'

# ✅ Templates Configuration
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ✅ Authentication Redirects
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"
LOGIN_URL = "/login/"

# 🐘 Mastodon configuration
if DEBUG:
    REDIRECT_URI = "http://localhost:8000/mastodon/callback"
    PIXELFED_REDIRECT_URI = "http://localhost:8000/pixelfed/callback"
else:
    REDIRECT_URI = env("REDIRECT_URI")
    PIXELFED_REDIRECT_URI = env("PIXELFED_REDIRECT_URI", default=env("REDIRECT_URI"))  # Fallback to REDIRECT_URI if not set
MASTODON_API_BASE = "https://mastodon.example.com/api/v1"
MEDIA_UPLOAD_ENDPOINT = "/api/compose/v0/media/upload"
POST_STATUS_ENDPOINT = "/api/v1/statuses"

# ✅ WSGI Application
WSGI_APPLICATION = 'core.wsgi.application'

# ✅ Database (PostgreSQL)
DATABASES = {  
    'default': {  
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT'),
    }
}

# ✅ Password Validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ✅ Custom User Model
AUTH_USER_MODEL = "postflow.CustomUser"

# ✅ Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ✅ Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ✅ Static and Media Configuration
if DEBUG:
    STATIC_URL = "/static/"
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"
else:
    AWS_S3_REGION_NAME = "eu-central-1"
    AWS_STORAGE_BUCKET_NAME = env("S3_AWS_STORAGE_BUCKET_NAME")
    AWS_STORAGE_MEDIA_BUCKET_NAME = env("AWS_STORAGE_MEDIA_BUCKET_NAME")

    # Note: We don't set global AWS_S3_CUSTOM_DOMAIN here because it would override
    # per-storage custom_domain settings in STORAGES configuration below
    STATIC_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/static/"
    MEDIA_URL = f"https://{AWS_STORAGE_MEDIA_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"

# ✅ Django 5+ Storage Settings
if DEBUG:
    # Local storage for development
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
else:
    # Media-specific credentials
    MEDIA_ACCESS_KEY_ID = env("MEDIA_ACCESS_KEY")  # 🔹 Use separate credentials for media
    MEDIA_SECRET_ACCESS_KEY = env("MEDIA_SECRET_ACCESS_KEY")  # 🔹 Use separate credentials for media
    AWS_STORAGE_MEDIA_BUCKET_NAME = env("AWS_STORAGE_MEDIA_BUCKET_NAME")

    # S3 storage for production
    AWS_S3_REGION_NAME = "eu-central-1"
    AWS_STORAGE_BUCKET_NAME = env("S3_AWS_STORAGE_BUCKET_NAME")

    STORAGES = {
        # Static files (CSS, JS)
        "staticfiles": {
            "BACKEND": "storages.backends.s3boto3.S3StaticStorage",
            "OPTIONS": {
                "bucket_name": AWS_STORAGE_BUCKET_NAME,
                "access_key": env("S3_ACCESS_KEY"),
                "secret_key": env("S3_SECRET_KEY"),
                "region_name": AWS_S3_REGION_NAME,
                "custom_domain": f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com",
            },
        },
        # Media files (PRIVATE)
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "bucket_name": AWS_STORAGE_MEDIA_BUCKET_NAME,
                "access_key": MEDIA_ACCESS_KEY_ID,
                "secret_key": MEDIA_SECRET_ACCESS_KEY,
                "region_name": AWS_S3_REGION_NAME,
                # NOTE: Do NOT set custom_domain here - it disables signed URL generation
                # Let boto3 generate proper signed URLs with querystring_auth
                "querystring_auth": True,  # Require signed URLs
                "querystring_expire": 3600,  # Signed URLs expire after 1 hour
                "default_acl": None,  # No public ACL
                },
            },
        }
    MEDIA_URL = f"https://{AWS_STORAGE_MEDIA_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
# ✅ Static files settings
STATIC_ROOT = BASE_DIR / "staticfiles"
if DEBUG:
    STATICFILES_DIRS = [
        BASE_DIR / "static",
        BASE_DIR / "postflow" / "static",
        BASE_DIR / "theme" / "static",
    ]

# ✅ Tailwind Theme
TAILWIND_APP_NAME = 'theme'

# ✅ Internal IPs for development
INTERNAL_IPS = [
    "127.0.0.1",
]
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,  # allows Django default logs
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',  # or DEBUG if you want more detail
            'propagate': False,
        },
        'postflow': {  # your app-specific logger
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# ✅ Django 6.0 Background Tasks Configuration
TASKS = {
    "default": {
        "BACKEND": "django_tasks.backends.database.DatabaseBackend",
    }
}
