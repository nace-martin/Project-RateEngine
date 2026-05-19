import os
import pytest
from unittest.mock import MagicMock, patch
from core.secrets import SecretResolver, get_secret

class TestSecretResolver:
    def test_resolve_plain_value(self):
        resolver = SecretResolver()
        assert resolver.resolve("plain_value") == "plain_value"
        assert resolver.resolve(None) is None
        assert resolver.resolve(123) == 123

    def test_resolve_sm_short_path_no_project(self):
        with patch.dict(os.environ, {}, clear=True):
            resolver = SecretResolver()
            with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT environment variable is not set"):
                resolver.resolve("sm://MY_SECRET")

    @patch("google.cloud.secretmanager.SecretManagerServiceClient")
    def test_resolve_sm_short_path_with_project(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = "secret_value"
        mock_client.access_secret_version.return_value = mock_response

        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            resolver = SecretResolver()
            result = resolver.resolve("sm://MY_SECRET")
            
            assert result == "secret_value"
            mock_client.access_secret_version.assert_called_once_with(
                request={"name": "projects/test-project/secrets/MY_SECRET/versions/latest"}
            )

    @patch("google.cloud.secretmanager.SecretManagerServiceClient")
    def test_resolve_sm_versioned_path(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = "v2_value"
        mock_client.access_secret_version.return_value = mock_response

        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            resolver = SecretResolver()
            result = resolver.resolve("sm://MY_SECRET/2")
            
            assert result == "v2_value"
            mock_client.access_secret_version.assert_called_once_with(
                request={"name": "projects/test-project/secrets/MY_SECRET/versions/2"}
            )

    @patch("google.cloud.secretmanager.SecretManagerServiceClient")
    def test_resolve_sm_full_path(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = "full_path_value"
        mock_client.access_secret_version.return_value = mock_response

        resolver = SecretResolver()
        full_path = "projects/other-project/secrets/OTHER_SECRET/versions/5"
        result = resolver.resolve(f"sm://{full_path}")
        
        assert result == "full_path_value"
        mock_client.access_secret_version.assert_called_once_with(
            request={"name": full_path}
        )

    @patch("google.cloud.secretmanager.SecretManagerServiceClient")
    def test_resolve_failure(self, mock_client_class):
        mock_client = mock_client_class.return_value
        mock_client.access_secret_version.side_effect = Exception("API Error")

        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            resolver = SecretResolver()
            with pytest.raises(RuntimeError, match="Failed to resolve secret from Secret Manager"):
                resolver.resolve("sm://MY_SECRET")

    @patch("core.secrets._resolver.resolve")
    def test_get_secret_wrapper(self, mock_resolve):
        mock_resolve.return_value = "resolved"
        with patch.dict(os.environ, {"MY_VAR": "raw"}):
            assert get_secret("MY_VAR") == "resolved"
            mock_resolve.assert_called_once_with("raw")

    @patch("core.secrets._resolver.resolve")
    def test_get_secret_default(self, mock_resolve):
        mock_resolve.side_effect = lambda x: x
        assert get_secret("NON_EXISTENT", default="fallback") == "fallback"
        mock_resolve.assert_called_once_with("fallback")
