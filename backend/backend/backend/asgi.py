import os
import django
from django.core.asgi import get_asgi_application
# from models_loader import load_models

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

# load_models()

application = get_asgi_application()