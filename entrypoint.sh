#!/bin/bash
# entrypoint.sh - Version simplifiée

echo "🚀 Démarrage de AeroPredict Pro..."

# Attendre PostgreSQL avec python
echo "⏳ Attente de PostgreSQL..."
python -c "
import time
import psycopg2
import os
while True:
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get('DB_NAME', 'aeropredict'),
            user=os.environ.get('DB_USER', 'aeropredict'),
            password=os.environ.get('DB_PASSWORD', 'aeropredict123'),
            host=os.environ.get('DB_HOST', 'db'),
            port=os.environ.get('DB_PORT', '5432')
        )
        conn.close()
        break
    except:
        print('Attente de PostgreSQL...')
        time.sleep(1)
"
echo "✅ PostgreSQL prêt !"

echo "⏳ Attente de Redis..."
python -c "
import time
import redis
import os
while True:
    try:
        r = redis.Redis(
            host=os.environ.get('REDIS_URL', 'redis://redis:6379/0').split('//')[1].split(':')[0],
            port=6379
        )
        r.ping()
        break
    except:
        print('Attente de Redis...')
        time.sleep(1)
"
echo "✅ Redis prêt !"

echo "📦 Application des migrations..."
python manage.py makemigrations maintenance
python manage.py migrate

echo "👤 Création du superuser..."
python manage.py shell -c "
from django.contrib.auth.models import User;
import os
if not User.objects.filter(username=os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')).exists():
    User.objects.create_superuser(
        username=os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'),
        email=os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com'),
        password=os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123')
    )
    print('✅ Superuser créé')
"

echo "📁 Collecte des fichiers statiques..."
python manage.py collectstatic --noinput

exec "$@"