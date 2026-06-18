import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SecretResolver:
    """
    Resolves secrets from environment variables or Google Secret Manager.
    
    Supported formats for environment variable values:
    1. Plain string: Returns as-is (backward compatible).
    2. sm://SECRET_NAME: Fetches 'latest' version of SECRET_NAME from GOOGLE_CLOUD_PROJECT.
    3. sm://SECRET_NAME/VERSION: Fetches specific version.
    4. sm://projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION: Full GCP resource path.
    """
    
    def __init__(self):
        self._client = None
        self._project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")

    @property
    def client(self):
        """Lazy-load the Secret Manager client."""
        if self._client is None:
            try:
                from google.cloud import secretmanager
                self._client = secretmanager.SecretManagerServiceClient()
            except ImportError:
                raise ImportError(
                    "google-cloud-secret-manager is required to resolve 'sm://' secrets. "
                    "Install it with 'pip install google-cloud-secret-manager'."
                )
        return self._client

    def resolve(self, value: Optional[str]) -> Optional[str]:
        """Resolves the value if it's an 'sm://' reference, otherwise returns as-is."""
        if not isinstance(value, str) or not value.startswith("sm://"):
            return value

        # Remove prefix
        path = value[5:]
        
        # Determine the full resource name
        if path.startswith("projects/"):
            # Full resource path provided: projects/*/secrets/*/versions/*
            resource_name = path
        else:
            # Short format provided: SECRET_NAME or SECRET_NAME/VERSION
            if not self._project_id:
                raise RuntimeError(
                    f"Cannot resolve secret '{path}': GOOGLE_CLOUD_PROJECT environment variable is not set."
                )
            
            parts = path.split("/")
            secret_id = parts[0]
            version_id = parts[1] if len(parts) > 1 else "latest"
            resource_name = f"projects/{self._project_id}/secrets/{secret_id}/versions/{version_id}"

        try:
            # We specifically do NOT log the resolved value or secret identifiers.
            # We only log that we are attempting to resolve a secret.
            logger.info("Resolving secret from Google Secret Manager")
            
            response = self.client.access_secret_version(request={"name": resource_name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            # Fail clearly if production requires a secret but it cannot be resolved.
            raise RuntimeError(f"Failed to resolve secret from Secret Manager ({resource_name}): {str(e)}")

# Singleton instance
_resolver = SecretResolver()

def get_secret(env_var_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Retrieves an environment variable and resolves it if it's a Secret Manager reference.
    """
    raw_value = os.environ.get(env_var_name, default)
    return _resolver.resolve(raw_value)
