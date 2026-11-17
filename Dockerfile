FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV DATABASE_PATH=/data/lifeguard.db
VOLUME ["/data"]
EXPOSE 8080
# Secrets come from the environment (docker run --env-file .env.production)
CMD ["python", "-m", "lifeguard"]
