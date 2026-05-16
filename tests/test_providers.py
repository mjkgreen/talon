from talon.providers.litellm_p import _to_litellm_tools
from talon.tools import TOOL_DEFINITIONS


class TestToolSchemaConversion:
    def test_count_preserved(self):
        assert len(_to_litellm_tools(TOOL_DEFINITIONS)) == len(TOOL_DEFINITIONS)

    def test_function_type(self):
        for tool in _to_litellm_tools(TOOL_DEFINITIONS):
            assert tool["type"] == "function"

    def test_all_fields_present(self):
        for tool in _to_litellm_tools(TOOL_DEFINITIONS):
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn

    def test_input_schema_becomes_parameters(self):
        converted = _to_litellm_tools(TOOL_DEFINITIONS)
        for orig, conv in zip(TOOL_DEFINITIONS, converted):
            assert conv["function"]["parameters"] == orig["input_schema"]

    def test_all_tool_names_present(self):
        names = {t["function"]["name"] for t in _to_litellm_tools(TOOL_DEFINITIONS)}
        assert names == {"read_file", "write_file", "list_files", "run_command", "search_files"}

    def test_empty_list(self):
        assert _to_litellm_tools([]) == []
