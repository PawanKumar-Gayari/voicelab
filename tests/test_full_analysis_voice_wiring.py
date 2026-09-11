from app.voice.assemblyai_agent import AssemblyAIVoiceAgent


def _find_tool(name: str):
    tools = AssemblyAIVoiceAgent.get_tool_definitions()
    matches = [tool for tool in tools if tool["name"] == name]
    assert matches, f"Tool {name!r} not found in get_tool_definitions()."
    return matches[0]


def test_full_analysis_tool_is_advertised():
    tool = _find_tool("full_analysis")

    assert tool["type"] == "function"
    assert "molecule" in tool["parameters"]["properties"]
    assert tool["parameters"]["required"] == ["molecule"]


def test_existing_tools_still_advertised():
    for name in (
        "analyze_symmetry",
        "calculate_representation",
        "verify_representation",
    ):
        _find_tool(name)


def test_dispatch_tool_routes_full_analysis(monkeypatch):
    agent = AssemblyAIVoiceAgent.__new__(AssemblyAIVoiceAgent)

    result = agent.dispatch_tool("full_analysis", {"molecule": "H2O"})

    assert result["success"] is True
    assert result["data"]["point_group"] == "C2v"


def test_dispatch_tool_rejects_unknown_tool():
    agent = AssemblyAIVoiceAgent.__new__(AssemblyAIVoiceAgent)

    result = agent.dispatch_tool("not_a_real_tool", {})

    assert result["success"] is False
    assert result["error"]["code"] == "UNKNOWN_TOOL"
    assert "full_analysis" in result["error"]["message"]
