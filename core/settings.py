from pathlib import Path
import environ

# Load environment variables
env = environ.Env()
environ.Env.read_env()

BASE_DIR = Path(__file__).resolve().parent.parent

# ✅ Security & Debug
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = [
    '.amazonlightsail.com', 'localhost', '0.0.0.0', '127.0.0.1',
    'https://postflow.pp347jb6gimu4.eu-central-1.cs.amazonlightsail.com',
    'postflow.photo', 'www.postflow.photo'
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
    AWS_STORAGE_MEDIA_BUCKET_NAME = env("S3_AWS_STORAGE_MEDIA_BUCKET_NAME")
    AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com"
    AWS_S3_MEDIA_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com"

    STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/static/"
    MEDIA_URL = f"https://{AWS_S3_MEDIA_DOMAIN}/media/"

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
    AWS_STORAGE_MEDIA_BUCKET_NAME = env("S3_AWS_STORAGE_MEDIA_BUCKET_NAME")

    # S3 storage for production
    AWS_ACCESS_KEY_ID = env("S3_ACCESS_KEY")
    AWS_SECRET_ACCESS_KEY = env("S3_SECRET_KEY")
    AWS_S3_REGION_NAME = "eu-central-1"
    AWS_STORAGE_BUCKET_NAME = env("S3_AWS_STORAGE_BUCKET_NAME")

    AWS_QUERYSTRING_AUTH = True  # Requires signed URLs
    AWS_DEFAULT_ACL = None  # No public ACL

    STORAGES = {
        # Static files (CSS, JS)
        "staticfiles": {
            "BACKEND": "storages.backends.s3boto3.S3StaticStorage",
            "OPTIONS": {"bucket_name": AWS_STORAGE_BUCKET_NAME},
        },
        # Media files (PRIVATE)
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "bucket_name": AWS_STORAGE_MEDIA_BUCKET_NAME,
                "access_key": AWS_ACCESS_KEY_ID,  # 🔹 Use MEDIA_ACCESS_KEY
                "secret_key": AWS_SECRET_ACCESS_KEY,  # 🔹 Use MEDIA_SECRET_ACCESS_KEY
                "region_name": AWS_S3_REGION_NAME,
                },
            },
        }
    MEDIA_URL = f"https://{AWS_STORAGE_MEDIA_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"

AWS_ACCESS_KEY_ID = env("S3_ACCESS_KEY")
AWS_SECRET_ACCESS_KEY = env("S3_SECRET_KEY")
AWS_S3_REGION_NAME = "eu-central-1"
AWS_STORAGE_MEDIA_BUCKET_NAME = "media-postflow"
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
