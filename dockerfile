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
# Specify the command to run on container start
# Copy the entrypoint script
COPY entrypoint.sh /entrypoint.sh

# Make the script executable
RUN chmod +x /entrypoint.sh

# Copy and set up crontab
COPY cronjob /etc/cron.d/postflow-cron
RUN chmod 0644 /etc/cron.d/postflow-cron && \
    crontab /etc/cron.d/postflow-cron

# Use the script as the entrypoint
ENTRYPOINT ["/entrypoint.sh"]
#CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000"]
CMD [ "uwsgi", "--http", "0.0.0.0:8000", \
            "--protocol", "uwsgi", \
            "--wsgi", "core.wsgi:application" ]
