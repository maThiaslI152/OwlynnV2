import pytest
import pytest_asyncio

from src.memory.thought_graph import ThoughtGraphManager


@pytest_asyncio.fixture
async def graph_mgr():
    mgr = ThoughtGraphManager()
    await mgr.ensure_tables()
    return mgr


@pytest.mark.asyncio
async def test_create_and_get_node(graph_mgr):
    node_id = "test-node-123"
    node = await graph_mgr.get_or_create_node(
        node_id=node_id,
        title="Test Architectural Discussion",
        mode="normal",
        tags=["arch", "mindmap"],
    )
    assert node["id"] == node_id
    assert node["title"] == "Test Architectural Discussion"
    assert node["mode"] == "normal"
    assert "arch" in node["tags"]

    fetched = await graph_mgr.get_node(node_id)
    assert fetched is not None
    assert fetched["title"] == "Test Architectural Discussion"


@pytest.mark.asyncio
async def test_create_edges_and_get_graph_data(graph_mgr):
    n1 = await graph_mgr.get_or_create_node("node-a", title="Node A", mode="normal")
    n2 = await graph_mgr.get_or_create_node("node-b", title="Node B", mode="normal")

    edge = await graph_mgr.create_edge(
        source_id="node-a",
        target_id="node-b",
        relation="branches_to",
        weight=1.0,
    )
    assert edge is not None
    assert edge["source"] == "node-a"
    assert edge["target"] == "node-b"
    assert edge["relation"] == "branches_to"

    graph = await graph_mgr.get_graph_data()
    assert any(n["id"] == "node-a" for n in graph["nodes"])
    assert any(n["id"] == "node-b" for n in graph["nodes"])
    assert any(
        e["source"] == "node-a" and e["target"] == "node-b" for e in graph["edges"]
    )


@pytest.mark.asyncio
async def test_update_and_delete_node(graph_mgr):
    node_id = "node-delete-test"
    await graph_mgr.get_or_create_node(node_id, title="Temporary Node")

    updated = await graph_mgr.update_node(
        node_id, title="Updated Title", canvas_x=150.0, canvas_y=200.0
    )
    assert updated["title"] == "Updated Title"
    assert updated["canvas_x"] == 150.0

    deleted = await graph_mgr.delete_node(node_id)
    assert deleted is True

    fetched = await graph_mgr.get_node(node_id)
    assert fetched is None


@pytest.mark.asyncio
async def test_shared_graph_excludes_pentest_nodes(graph_mgr):
    await graph_mgr.get_or_create_node("shared-normal", title="Shared", mode="normal")
    await graph_mgr.get_or_create_node(
        "legacy-pentest",
        title="Legacy Pentest",
        mode="pentest",
        scenario_id="pentest",
    )

    graph = await graph_mgr.get_graph_data()

    assert any(node["id"] == "shared-normal" for node in graph["nodes"])
    assert all(node["mode"] != "pentest" for node in graph["nodes"])


@pytest.mark.asyncio
async def test_shared_graph_includes_internal_non_pentest_modes(graph_mgr):
    await graph_mgr.get_or_create_node(
        "shared-tools-on",
        title="Python 3.14 News",
        mode="tools_on",
    )
    await graph_mgr.get_or_create_node(
        "shared-normal-2",
        title="Python 3.14 Features",
        mode="normal",
    )
    await graph_mgr.create_edge(
        source_id="shared-tools-on",
        target_id="shared-normal-2",
        relation="relates_to",
        weight=0.71,
        auto_generated=True,
    )

    graph = await graph_mgr.get_graph_data()

    tools_node = next(node for node in graph["nodes"] if node["id"] == "shared-tools-on")
    assert tools_node["mode"] == "normal"
    assert any(
        e["source"] == "shared-tools-on" and e["target"] == "shared-normal-2"
        for e in graph["edges"]
    )


@pytest.mark.asyncio
async def test_delete_legacy_pentest_graph_data_removes_shared_pentest_rows(graph_mgr):
    await graph_mgr.get_or_create_node(
        "cleanup-pentest",
        title="Cleanup Node",
        mode="pentest",
        scenario_id="pentest",
    )
    removed = await graph_mgr.delete_legacy_pentest_graph_data()

    assert removed >= 1
    assert await graph_mgr.get_node("cleanup-pentest") is None
