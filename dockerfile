# Set base image (host OS)
FROM python:3.13.0-bullseye

# By default, listen on port
EXPOSE 8000/tcp
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBUG=False

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy pyproject.toml and uv.lock for dependency installation
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# uv automatically detects Docker and installs system-wide
RUN uv sync --frozen --no-dev

# Copy the content of the local src directory to the working directory
COPY . .

# Copy the entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Use the script as the entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command runs uwsgi
CMD [ "uwsgi", "--http", "0.0.0.0:8000", \
            "--protocol", "uwsgi", \
            "--wsgi", "core.wsgi:application" ]
