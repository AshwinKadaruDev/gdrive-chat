"""Tests for Drive agent tool definitions."""

from app.services.agent_tools import (
    DRIVE_AGENT_TOOLS,
    DRIVE_ONLY_TOOLS,
    SHARED_TOOLS,
)


def _tool_names(tools: list[dict]) -> list[str]:
    return [t["function"]["name"] for t in tools]


class TestToolGroupComposition:
    def test_drive_only_tools_names(self):
        names = _tool_names(DRIVE_ONLY_TOOLS)
        assert names == [
            "search_drive",
            "get_file_content",
            "search_within_file_text",
        ]

    def test_shared_tools_names(self):
        names = _tool_names(SHARED_TOOLS)
        assert "get_folder_structure" in names
        assert "get_file_metadata" in names
        assert "read_document_pages" in names
        assert "report_inability" in names
        assert "request_clarification" in names
        assert len(names) == 9

    def test_drive_agent_tools_is_drive_plus_shared(self):
        assert DRIVE_AGENT_TOOLS == DRIVE_ONLY_TOOLS + SHARED_TOOLS

    def test_drive_agent_tool_count(self):
        assert len(DRIVE_AGENT_TOOLS) == 12

    def test_no_overlap_between_drive_only_and_shared(self):
        drive_names = set(_tool_names(DRIVE_ONLY_TOOLS))
        shared_names = set(_tool_names(SHARED_TOOLS))
        assert drive_names.isdisjoint(shared_names)


class TestToolSchemaValidity:
    def test_all_tools_have_type_and_function(self):
        for tool_list in [DRIVE_ONLY_TOOLS, SHARED_TOOLS]:
            for tool in tool_list:
                assert tool["type"] == "function"
                assert "function" in tool
                assert "name" in tool["function"]
                assert "description" in tool["function"]
                assert "parameters" in tool["function"]

    def test_search_drive_schema(self):
        tool = next(
            t for t in DRIVE_ONLY_TOOLS
            if t["function"]["name"] == "search_drive"
        )
        params = tool["function"]["parameters"]
        assert params["required"] == ["query"]
        assert "query" in params["properties"]
        assert "file_types" in params["properties"]

    def test_get_file_content_schema(self):
        tool = next(
            t for t in DRIVE_ONLY_TOOLS
            if t["function"]["name"] == "get_file_content"
        )
        params = tool["function"]["parameters"]
        assert params["required"] == ["file_id"]
        assert "file_id" in params["properties"]
        assert "max_chars" in params["properties"]

    def test_search_within_file_text_schema(self):
        tool = next(
            t for t in DRIVE_ONLY_TOOLS
            if t["function"]["name"] == "search_within_file_text"
        )
        params = tool["function"]["parameters"]
        assert params["required"] == ["file_id", "query"]
        assert "file_id" in params["properties"]
        assert "query" in params["properties"]
        assert "context_chars" in params["properties"]
