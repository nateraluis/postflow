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

# Copy the content of the local src directory to the working directory
COPY . .

# Install dependencies using uv into system Python
# Use --system flag to install directly into system Python (no venv)
# This installs all dependencies defined in pyproject.toml
RUN uv pip install --system --no-cache .

# Make entrypoint executable
RUN chmod +x /entrypoint.sh

# Use the script as the entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command runs uwsgi
CMD [ "uwsgi", "--http", "0.0.0.0:8000", \
            "--protocol", "uwsgi", \
            "--wsgi", "core.wsgi:application" ]
