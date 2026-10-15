# One image for the web app and every scheduled job.
#   web:  uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
#   job:  python -m app.jobs publish
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

ARG GIT_SHA=dev
ENV KA_BUILD_VERSION=$GIT_SHA

RUN useradd --uid 10001 --no-create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
