from pathlib import Path
import sqlite3
import tempfile
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class GateState(TypedDict):
    decision_id: str | None


def _gate(state: GateState):
    decision_id = interrupt(
        {
            "workflow_id": "rwf_test",
            "allowed": ["approve", "reject"],
        }
    )
    return {"decision_id": decision_id}


def compile_graph(path: str):
    connection = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    builder = StateGraph(GateState)
    builder.add_node("gate", _gate)
    builder.add_edge(START, "gate")
    builder.add_edge("gate", END)
    return builder.compile(checkpointer=saver), connection


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="review-checkpoint-") as tmp:
        path = str(Path(tmp) / "checkpoints.db")
        config = {"configurable": {"thread_id": "review_compatibility"}}
        graph, connection = compile_graph(path)
        first = graph.invoke(
            {"decision_id": None},
            config=config,
            durability="sync",
        )
        assert first["__interrupt__"]
        connection.close()

        graph, connection = compile_graph(path)
        result = graph.invoke(
            Command(resume="decision_compatibility"),
            config=config,
            durability="sync",
        )
        assert result["decision_id"] == "decision_compatibility"
        connection.close()
    print("persistent_review_checkpoint_compatibility=passed")


if __name__ == "__main__":
    main()
