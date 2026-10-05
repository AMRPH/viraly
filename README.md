# viraly

## Backend configuration

Copy `.env.example` to `.env` and fill in the credentials. Generate a new Django
secret key, for example with `openssl rand -hex 32`. Set `CELERY_BROKER_URL` to
your RabbitMQ connection URL.

The backend reads environment variables; it does not load `.env` automatically.
Export them before starting Django or Celery:

```bash
set -a
source .env
set +a
cd backend/backend
python manage.py runserver
```

Keep `.env` local. Do not commit passwords, tokens, or private keys.
