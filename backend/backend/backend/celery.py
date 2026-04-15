import os
from celery import Celery, signals
from kombu import Queue

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

CELERY_QUEUES = (
    Queue(
        'default',
        routing_key='tasks.#',
        queue_arguments={'x-max-priority': 10}  # до 10 уровней приоритета
    ),
)

CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_DEFAULT_ROUTING_KEY = 'tasks.default'
CELERY_TASK_DEFAULT_EXCHANGE = 'tasks'
CELERY_TASK_DEFAULT_EXCHANGE_TYPE = 'direct'

@signals.worker_process_init.connect
def load_models_on_worker(**kwargs):
    from backend.models_loader import load_models
    load_models()