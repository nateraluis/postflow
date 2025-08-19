# Set base image (host OS)
FROM python:3.13.0-bullseye

# By default, listen on port
EXPOSE 8000/tcp
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBUG=False

# Install cron
RUN apt-get update && apt-get install -y cron

# Set working directory
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any dependencies
RUN pip install -r requirements.txt

# Copy the content of the local src directory to the working directory
COPY . .

# Copy the entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create cron jobs
# 1. Run scheduled posts every minute
# 2. Refresh Instagram tokens daily at 02:00
RUN echo "* * * * * root cd /app && $(which python3) manage.py run_post_scheduled >> /var/log/cron.log 2>&1" > /etc/cron.d/postflow-cron \
    && echo "* * * * * root cd /app && $(which python3) manage.py refresh_instagram_tokens >> /var/log/cron.log 2>&1" >> /etc/cron.d/postflow-cron \
    && chmod 0644 /etc/cron.d/postflow-cron \
    && crontab /etc/cron.d/postflow-cron

# Use the script as the entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command runs uwsgi
CMD [ "uwsgi", "--http", "0.0.0.0:8000", \
            "--protocol", "uwsgi", \
            "--wsgi", "core.wsgi:application" ]
