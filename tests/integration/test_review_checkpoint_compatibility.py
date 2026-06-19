from langgraph.types import Command

from scripts.check_review_checkpoint_compatibility import compile_graph


def test_sqlite_checkpoint_reopens_and_resumes_with_sync_durability(tmp_path):
    path = str(tmp_path / "checkpoints.db")
    config = {"configurable": {"thread_id": "review_rwf_test"}}

    graph, connection = compile_graph(path)
    first = graph.invoke({"decision_id": None}, config=config, durability="sync")
    assert first["__interrupt__"][0].value["workflow_id"] == "rwf_test"
    connection.close()

    reopened, reopened_connection = compile_graph(path)
    result = reopened.invoke(
        Command(resume="decision_001"),
        config=config,
        durability="sync",
    )
    assert result["decision_id"] == "decision_001"
    reopened_connection.close()
