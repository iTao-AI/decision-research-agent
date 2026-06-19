from typing import Any, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class InvalidThenValidStructuredModel(BaseChatModel):
    call_count: int = 0
    requests: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "invalid-then-valid-structured-model"

    def bind_tools(
        self,
        tools: Sequence,
        *,
        tool_choice: dict | str | bool | None = None,
        **kwargs: Any,
    ):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        self.call_count += 1
        self.requests.append(list(messages))
        if self.call_count == 1:
            message = AIMessage(
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": "call-invalid",
                            "type": "function",
                            "function": {
                                "name": "ResearchPacket",
                                "arguments": "{",
                            },
                        }
                    ]
                },
                invalid_tool_calls=[
                    {
                        "name": "ResearchPacket",
                        "args": "{",
                        "id": "call-invalid",
                        "error": "Function arguments are not valid JSON.",
                        "type": "invalid_tool_call",
                    }
                ],
            )
        else:
            if not any(
                isinstance(item, ToolMessage)
                and item.tool_call_id == "call-invalid"
                and item.status == "error"
                for item in messages
            ):
                raise RuntimeError("provider rejected unpaired invalid tool call")
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ResearchPacket",
                        "args": {
                            "packet_id": "packet-recovered",
                            "scope_id": "scope-1",
                            "findings": [],
                            "candidate_claims": [],
                            "contradictions": [],
                            "limitations": ["bounded fixture"],
                        },
                        "id": "call-valid",
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_talent_agent_recovers_invalid_structured_tool_call_with_paired_error():
    from agent.profile_agents import compile_profile_agent
    from agent.profile_registry import profile_registry

    model = InvalidThenValidStructuredModel()
    profile = profile_registry.get("talent-hiring-signal")
    policy = profile_registry.policy_for("talent-hiring-signal")
    agent = compile_profile_agent(
        profile,
        policy,
        model=model,
        generic_agent=object(),
    )

    result = agent.invoke({"messages": [{"role": "user", "content": "bounded input"}]})

    assert result["structured_response"].packet_id == "packet-recovered"
    assert model.call_count == 2
    assert any(
        isinstance(item, ToolMessage)
        and item.tool_call_id == "call-invalid"
        and item.name == "ResearchPacket"
        and item.status == "error"
        for item in model.requests[1]
    )
