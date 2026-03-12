"""Tests for Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest
from app.schemas.project import ProjectCreate


class TestChatRequest:
    def test_rejects_message_longer_than_32000(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            ChatRequest(message="x" * 32001)

    def test_rejects_empty_message(self):
        with pytest.raises(ValidationError, match="string_too_short"):
            ChatRequest(message="")

    def test_valid_request(self):
        req = ChatRequest(message="What is this?")
        assert req.message == "What is this?"


class TestProjectCreate:
    def test_rejects_url_longer_than_500(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            ProjectCreate(gdrive_folder_url="https://drive.google.com/" + "x" * 500)

    def test_rejects_name_longer_than_255(self):
        with pytest.raises(ValidationError, match="string_too_long"):
            ProjectCreate(
                gdrive_folder_url="https://drive.google.com/drive/folders/abc",
                name="x" * 256,
            )

    def test_valid_input(self):
        pc = ProjectCreate(
            gdrive_folder_url="https://drive.google.com/drive/folders/abc",
            name="My Folder",
        )
        assert pc.gdrive_folder_url == "https://drive.google.com/drive/folders/abc"
        assert pc.name == "My Folder"

    def test_name_is_optional(self):
        pc = ProjectCreate(gdrive_folder_url="https://drive.google.com/drive/folders/abc")
        assert pc.name is None
