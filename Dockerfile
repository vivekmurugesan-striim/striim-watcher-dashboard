FROM python:3.12-slim

WORKDIR /srv

# System deps: none needed beyond what the slim base + pip wheels already provide for
# google-cloud-bigquery (it ships prebuilt wheels for its C-extension dependencies).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8080

# Shell form (not exec-form JSON array) so APP_PORT actually gets substituted at container
# start — docker-compose.yml passes it through from .env, default 8080 if unset.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8080}
