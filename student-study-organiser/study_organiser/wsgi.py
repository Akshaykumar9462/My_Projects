"""WSGI entry point used by Django-compatible web servers in deployment."""

import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "study_organiser.settings")
application = get_wsgi_application()

