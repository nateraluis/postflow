# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PostFlow is a Django 5.2.3 social media scheduling application that allows users to schedule posts to Mastodon/Pixelfed and Instagram Business accounts. The application features:

- Custom user model using email authentication (no username)
- Social media integration (Mastodon.py, Instagram Business API, Facebook Graph API)
- Image scheduling with S3 storage and signed URLs for private media
- Tag and hashtag group management
- Timezone-aware post scheduling
- Stripe integration for subscriptions
- Docker deployment on AWS EC2 with nginx reverse proxy and Let's Encrypt SSL

## Development Commands

### Local Development
```bash
# Start development server
python manage.py runserver

# Database operations
python manage.py makemigrations
python manage.py migrate

# Static files
python manage.py collectstatic

# Custom management commands
python manage.py run_post_scheduled    # Process scheduled posts
python manage.py refresh_instagram_tokens  # Refresh Instagram access tokens
```

### Tailwind CSS
```bash
# Development (watch mode)
python manage.py tailwind start

# Production build
python manage.py tailwind build
```

### Docker (Production)
```bash
# Build and start containers
docker-compose up --build -d

# View logs
docker-compose logs -f django
docker-compose logs -f nginx
```

## Architecture Overview

### Core Django Structure
- **postflow/** - Main Django app containing core functionality
- **subscriptions/** - Subscription management (basic structure, unused models)
- **theme/** - Tailwind CSS integration with django-tailwind
- **core/** - Django project settings and configuration

### Key Models
- **CustomUser** - Email-based authentication (no username field)
- **ScheduledPost** - Posts with timezone-aware scheduling, supports multiple social platforms
- **MastodonAccount** - OAuth-connected Mastodon/Pixelfed accounts
- **InstagramBusinessAccount** - Instagram Business API integration with token refresh
- **Tag/TagGroup** - Hashtag management system
- **Subscriber** - Email subscriber model

### Storage Configuration
The app uses a dual storage setup:
- **Development (DEBUG=True)**: Local filesystem storage
- **Production (DEBUG=False)**: AWS S3 with separate buckets for static files and private media
  - Static files: Public S3 bucket via `S3StaticStorage`
  - Media files: Private S3 bucket via `S3Boto3Storage` with signed URLs

### Social Media Integration
- **Mastodon/Pixelfed**: Uses Mastodon.py library with OAuth tokens
- **Instagram Business**: Uses Facebook Graph API with page access tokens that auto-refresh
- **Scheduling**: Timezone-aware with cron job processing via `run_post_scheduled` command

## Environment Configuration

### Required Environment Variables (core/.env)
```env
DJANGO_SECRET_KEY=your_secret_key
DEBUG=True  # False for production

# Database (PostgreSQL)
DB_NAME=postflow
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# AWS S3 Storage
S3_ACCESS_KEY=your_s3_key
S3_SECRET_KEY=your_s3_secret
S3_AWS_STORAGE_BUCKET_NAME=your_static_bucket
AWS_STORAGE_MEDIA_BUCKET_NAME=your_media_bucket
MEDIA_ACCESS_KEY=your_media_key
MEDIA_SECRET_ACCESS_KEY=your_media_secret

# Social Media APIs
FACEBOOK_APP_ID=your_app_id
FACEBOOK_APP_SECRET=your_app_secret
FACEBOOK_VERIFY_TOKEN=your_verify_token
INSTAGRAM_BUSINESS_REDIRECT_URI=your_redirect_uri
REDIRECT_URI=http://localhost:8000/mastodon/callback  # Mastodon OAuth
```

## Deployment

### Production Deployment
- Deployed on AWS EC2 via GitHub Actions on push to `main` branch
- Uses Docker Compose with Django + nginx + certbot setup
- SSL certificates managed via Let's Encrypt with automatic renewal
- Environment variables injected via GitHub Secrets during deployment

### GitHub Actions Workflow
- Builds Docker containers on EC2
- Deploys with zero-downtime using container health checks
- Manages SSL certificate renewal via certbot-renewer service
- Includes watchdog service for container monitoring

## Common Development Patterns

### Working with Social Media APIs
- Mastodon accounts use OAuth with stored access tokens
- Instagram accounts require page-level access tokens that expire and auto-refresh
- Use `get_image_file()` method on ScheduledPost to handle S3/local file access

### Database Queries
- Custom user model uses email as USERNAME_FIELD
- All user-related models include user foreign keys with proper related_names
- Timezone handling via pytz with user-specific timezone storage

### Static/Media Files
- Tailwind builds to `theme/static/css/dist/styles.css`
- Development uses STATICFILES_DIRS for multiple static directories
- Production serves static files directly from S3, media files via signed URLs
