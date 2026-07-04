from .settings import *

SECURE_SSL_REDIRECT = False
RBAC_ALLOW_LEGACY_SCOPE_FALLBACK_FOR_TESTS = True

# Disable throttling globally for tests (prevents HTTP 429 errors in pytest bulk runs)
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_THROTTLE_CLASSES': [],
}

# Add missing GCP attributes for tests
GCP_PROJECT_ID = 'test-project-id'
APP_VERSION = 'test-version'