from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient


def test_spot_reply_analysis_rejects_invalid_pdf_upload(db):
    user = get_user_model().objects.create_user(username="spot-upload-user", password="pass123")
    client = APIClient()
    client.force_authenticate(user=user)
    upload = SimpleUploadedFile("reply.pdf", b"not-a-real-pdf", content_type="application/pdf")

    response = client.post("/api/v3/spot/analyze-reply/", {"file": upload}, format="multipart")

    assert response.status_code == 400
    assert "valid PDF" in response.data["error"]
