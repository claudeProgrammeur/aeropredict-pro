from django.test import TestCase

# Create your tests here.
"""

celery -A aeronoth worker --loglevel=info --pool=solo
daphne -b 127.0.0.1 -p 8000 aeronoth.asgi:application

"""