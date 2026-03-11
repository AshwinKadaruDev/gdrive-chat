"""Tests for the token refresh and 401 handling in worker activities."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
from temporalio.exceptions import ApplicationError


# Temporal's activity.logger / activity.logger.info need to be mocked
# when calling activity functions outside a Temporal worker context.
@pytest.fixture(autouse=True)
def _mock_activity_context():
    """Mock the Temporal activity context so activities can run in tests."""
    with patch("temporalio.activity.logger", MagicMock()):
        yield


def _mock_httpx_client(mock_response):
    """Create a mock httpx.AsyncClient context manager."""
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestRefreshGoogleToken:
    """Tests for worker/activities/refresh_token.py"""

    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    async def test_returns_new_access_token(self):
        from worker.activities.refresh_token import refresh_google_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new-token-123"}

        with patch("worker.activities.refresh_token.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_httpx_client(mock_response)

            token = await refresh_google_token("valid-refresh-token")

        assert token == "new-token-123"

    async def test_sends_correct_payload(self):
        from worker.activities.refresh_token import refresh_google_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "token"}
        mock_client = _mock_httpx_client(mock_response)

        with patch("worker.activities.refresh_token.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_client

            await refresh_google_token("my-refresh-token")

        call_kwargs = mock_client.post.call_args
        data = call_kwargs[1]["data"]
        assert data["refresh_token"] == "my-refresh-token"
        assert data["grant_type"] == "refresh_token"
        assert data["client_id"] == "test-client-id"
        assert data["client_secret"] == "test-client-secret"

    async def test_raises_non_retryable_on_401(self):
        from worker.activities.refresh_token import refresh_google_token

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = '{"error": "invalid_grant"}'

        with patch("worker.activities.refresh_token.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_httpx_client(mock_response)

            with pytest.raises(ApplicationError) as exc_info:
                await refresh_google_token("bad-refresh-token")

        assert exc_info.value.type == "TOKEN_EXPIRED"
        assert exc_info.value.non_retryable

    async def test_raises_non_retryable_on_empty_refresh_token(self):
        from worker.activities.refresh_token import refresh_google_token

        with pytest.raises(ApplicationError) as exc_info:
            await refresh_google_token("")

        assert exc_info.value.non_retryable

    async def test_raises_non_retryable_on_empty_access_token_response(self):
        from worker.activities.refresh_token import refresh_google_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": ""}

        with patch("worker.activities.refresh_token.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_httpx_client(mock_response)

            with pytest.raises(ApplicationError) as exc_info:
                await refresh_google_token("some-token")

        assert exc_info.value.non_retryable

    async def test_raises_on_missing_env_vars(self, monkeypatch):
        from worker.activities.refresh_token import refresh_google_token

        monkeypatch.delenv("GOOGLE_CLIENT_ID")
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET")

        with pytest.raises(ApplicationError) as exc_info:
            await refresh_google_token("some-token")

        assert exc_info.value.type == "CONFIG_ERROR"
        assert exc_info.value.non_retryable


class TestCrawlFolder401:
    """Tests for 401 handling in worker/activities/crawl_folder.py"""

    async def test_raises_non_retryable_on_401(self):
        from worker.activities.crawl_folder import crawl_folder

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = '{"error": {"message": "Invalid Credentials"}}'

        with patch("worker.activities.crawl_folder.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_httpx_client(mock_response)

            with pytest.raises(ApplicationError) as exc_info:
                await crawl_folder("folder123", "expired-token")

        assert exc_info.value.type == "TOKEN_EXPIRED"
        assert exc_info.value.non_retryable

    async def test_succeeds_with_valid_token(self):
        from worker.activities.crawl_folder import crawl_folder

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "files": [
                {
                    "id": "f1",
                    "name": "doc.pdf",
                    "mimeType": "application/pdf",
                    "size": "1024",
                    "webViewLink": "https://drive.google.com/file/d/f1",
                }
            ],
        }

        with patch("worker.activities.crawl_folder.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_httpx_client(mock_response)

            files = await crawl_folder("folder123", "good-token")

        assert len(files) == 1
        assert files[0]["name"] == "doc.pdf"

    async def test_raises_on_non_401_error(self):
        from worker.activities.crawl_folder import crawl_folder

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=mock_response,
        )

        with patch("worker.activities.crawl_folder.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_httpx_client(mock_response)

            with pytest.raises(httpx.HTTPStatusError):
                await crawl_folder("folder123", "good-token")


class TestExtractContent401:
    """Tests for 401 handling in worker/activities/extract_content.py"""

    async def test_raises_non_retryable_on_401(self):
        from worker.activities.extract_content import extract_content

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}
        mock_request = MagicMock(spec=httpx.Request)
        mock_request.url = "https://www.googleapis.com/drive/v3/files/f1/export"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=mock_request,
            response=mock_response,
        )

        file_info = {
            "id": "f1",
            "name": "doc.txt",
            "mimeType": "application/vnd.google-apps.document",
        }

        with patch("worker.activities.extract_content.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_httpx_client(mock_response)

            with pytest.raises(ApplicationError) as exc_info:
                await extract_content(file_info, "expired-token")

        assert exc_info.value.type == "TOKEN_EXPIRED"
        assert exc_info.value.non_retryable

    async def test_reraises_non_401_errors(self):
        from worker.activities.extract_content import extract_content

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}
        mock_request = MagicMock(spec=httpx.Request)
        mock_request.url = "https://www.googleapis.com/drive/v3/files/f1/export"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=mock_request,
            response=mock_response,
        )

        file_info = {
            "id": "f1",
            "name": "doc.txt",
            "mimeType": "application/vnd.google-apps.document",
        }

        with patch("worker.activities.extract_content.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _mock_httpx_client(mock_response)

            with pytest.raises(httpx.HTTPStatusError):
                await extract_content(file_info, "valid-token")

    async def test_image_files_skip_drive_api(self):
        from worker.activities.extract_content import extract_content

        file_info = {
            "id": "img1",
            "name": "photo.png",
            "mimeType": "image/png",
        }

        result = await extract_content(file_info, "any-token")
        assert result["extraction_type"] == "image_placeholder"
        assert "photo.png" in result["text"]
