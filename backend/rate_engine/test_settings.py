from .settings import *

SECURE_SSL_REDIRECT = False
RBAC_COMPAT_MODE = True

# Disable throttling for tests
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {}

