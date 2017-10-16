# Replace this values with your local settings
import os
import dj_database_url

# Ya no es necesario cambiar esto
if os.environ.get('is_deployed', 'False') == 'True':
    DATABASE_DICT = dj_database_url.config(default=os.environ.get('DATABASE_URL', ''))
else:
    DATABASE_DICT = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'green_market',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': '127.0.0.1',
        'PORT': '5432',
        'TEST': {
            'NAME': 'test_green_market',
        }
    }
