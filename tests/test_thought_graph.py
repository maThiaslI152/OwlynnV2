import time

import pytest
import pytest_asyncio

from src.memory.thought_graph import ThoughtGraphManager


@pytest_asyncio.fixture
async def graph_mgr():
    from src.memory.postgres_health import is_postgres_available, reset_postgres_breaker

    reset_postgres_breaker()
    if not is_postgres_available():
        pytest.skip("Postgres circuit open")
    mgr = ThoughtGraphManager()
    try:
        await mgr.ensure_tables()
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")
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
    assert node is not None
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
    assert n1 is not None and n2 is not None

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
    created = await graph_mgr.get_or_create_node(node_id, title="Temporary Node")
    assert created is not None

    updated = await graph_mgr.update_node(
        node_id, title="Updated Title", canvas_x=150.0, canvas_y=200.0
    )
    assert updated is not None
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

    tools_node = next(
        node for node in graph["nodes"] if node["id"] == "shared-tools-on"
    )
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


def test_embedding_text_falls_back_to_title_and_tags():
    from src.memory.thought_graph import embedding_text_for_node

    assert embedding_text_for_node("DNS notes", "", ["network", "infra"]) == (
        "DNS notes network infra"
    )
    assert embedding_text_for_node("X", "A full summary that is long enough", []) == (
        "A full summary that is long enough"
    )


def test_dormancy_pinned_never_decays():
    from src.memory.thought_graph import compute_dormancy_score, compute_fade_alpha

    now = 1_700_000_000.0
    old = now - (60 * 86400)
    assert compute_dormancy_score(old, pinned=True, now=now) == 0.0
    assert compute_fade_alpha(0.9, pinned=True) == 1.0
    dormant = compute_dormancy_score(old, pinned=False, now=now)
    assert dormant >= 0.55


def test_cluster_assignment_preserves_node_ids():
    from src.memory.thought_graph import assign_topic_clusters

    nodes = [
        {
            "id": "t-a",
            "mode": "normal",
            "title": "TLS",
            "tags": ["crypto"],
            "last_active_at": 2.0,
        },
        {
            "id": "t-b",
            "mode": "normal",
            "title": "TLS follow-up",
            "tags": ["crypto"],
            "last_active_at": 1.0,
        },
        {
            "id": "t-c",
            "mode": "study",
            "title": "TLS exam",
            "tags": ["crypto"],
            "last_active_at": 1.0,
        },
    ]
    edges = [
        {"source": "t-a", "target": "t-b", "relation": "merges_with", "weight": 0.91},
        {"source": "t-a", "target": "t-c", "relation": "merges_with", "weight": 0.91},
    ]
    assigned = assign_topic_clusters(nodes, edges)
    assert set(assigned) == {"t-a", "t-b", "t-c"}
    assert assigned["t-a"][0] == assigned["t-b"][0]
    assert assigned["t-a"][0] != assigned["t-c"][0]
    assert assigned["t-c"][0] == "t-c"


def test_prune_edges_top_k_by_weight():
    from src.memory.thought_graph import prune_edges_to_nodes

    edges = [
        {
            "id": i,
            "source": "hub",
            "target": f"n{i}",
            "weight": i / 10,
            "relation": "relates_to",
        }
        for i in range(1, 6)
    ]
    pruned = prune_edges_to_nodes(
        edges, {"hub", "n1", "n2", "n3", "n4", "n5"}, max_edges_per_node=2
    )
    weights = sorted(e["weight"] for e in pruned)
    assert len(pruned) == 2
    assert weights == [0.4, 0.5]


@pytest.mark.asyncio
async def test_dormancy_metadata_and_manual_layout(graph_mgr):
    node_id = "om-dormant-layout"
    await graph_mgr.get_or_create_node(node_id, title="Old topic", mode="normal")
    old = time.time() - (45 * 86400)
    await graph_mgr.update_node(node_id, last_active_at=old)

    drifted = await graph_mgr.get_node(node_id, touch_active=False)
    assert drifted is not None
    assert drifted["is_dormant"] is True
    assert drifted["fade_alpha"] < 1.0
    assert drifted["allow_radial_drift"] is True
    assert drifted["radial_tier"] >= 1

    placed = await graph_mgr.update_node(
        node_id, canvas_x=10.0, canvas_y=20.0, last_active_at=old
    )
    assert placed["allow_radial_drift"] is False
    assert placed["radial_tier"] == 0
    assert placed["is_dormant"] is True
    assert placed["last_active_at"] == old
    canvas_only = await graph_mgr.update_node(node_id, canvas_x=11.0, canvas_y=21.0)
    assert canvas_only["last_active_at"] == old

    pinned = await graph_mgr.update_node(
        node_id, pinned=True, last_active_at=old, touch_active=False
    )
    assert pinned["pinned"] is True
    assert pinned["is_dormant"] is False
    assert pinned["allow_radial_drift"] is False
    assert pinned["fade_alpha"] == 1.0


@pytest.mark.asyncio
async def test_immediate_revive_on_reopen(graph_mgr):
    node_id = "om-revive"
    await graph_mgr.get_or_create_node(node_id, title="Sleepy", mode="normal")
    old = time.time() - (40 * 86400)
    await graph_mgr.update_node(node_id, last_active_at=old)
    dormant = await graph_mgr.get_node(node_id, touch_active=False)
    assert dormant["is_dormant"] is True

    revived = await graph_mgr.get_or_create_node(node_id, title="Sleepy", mode="normal")
    assert revived["is_dormant"] is False
    assert revived["dormancy_score"] == 0.0
    assert revived["last_active_at"] > old


@pytest.mark.asyncio
async def test_graph_clusters_ranking_and_edge_prune(graph_mgr):
    now = time.time()
    await graph_mgr.get_or_create_node(
        "om-c1", title="Auth cookies", mode="normal", tags=["auth"]
    )
    await graph_mgr.get_or_create_node(
        "om-c2", title="Auth sessions", mode="normal", tags=["auth"]
    )
    await graph_mgr.get_or_create_node(
        "om-study", title="Auth quiz", mode="study", tags=["auth"]
    )
    await graph_mgr.get_or_create_node(
        "om-old", title="Unrelated archive", mode="normal"
    )
    await graph_mgr.update_node("om-c1", last_active_at=now)
    await graph_mgr.update_node("om-c2", last_active_at=now - 60)
    await graph_mgr.update_node("om-old", last_active_at=now - (50 * 86400))
    await graph_mgr.create_edge("om-c1", "om-c2", relation="relates_to", weight=0.88)
    await graph_mgr.create_edge("om-c1", "om-study", relation="relates_to", weight=0.9)
    for i in range(6):
        nid = f"om-spoke-{i}"
        await graph_mgr.get_or_create_node(nid, title=f"Spoke {i}", mode="normal")
        await graph_mgr.create_edge("om-c1", nid, relation="relates_to", weight=0.1 * i)

    graph = await graph_mgr.get_graph_data(
        mode="normal", clustered=True, max_nodes=50, max_edges_per_node=3
    )
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["om-c1"]["id"] != by_id["om-c2"]["id"]
    assert by_id["om-c1"]["topic_cluster_id"] == by_id["om-c2"]["topic_cluster_id"]
    assert "om-study" not in by_id
    assert by_id["om-old"]["is_dormant"] is True
    hub_edges = [
        e for e in graph["edges"] if e["source"] == "om-c1" or e["target"] == "om-c1"
    ]
    assert len(hub_edges) <= 3 + 3
    ids = [n["id"] for n in graph["nodes"]]
    assert ids.index("om-c1") < ids.index("om-old")

    hidden = await graph_mgr.get_graph_data(
        mode="normal", show_dormant=False, clustered=False, max_nodes=50
    )
    hidden_ids = {n["id"] for n in hidden["nodes"]}
    assert "om-old" not in hidden_ids


@pytest.mark.asyncio
async def test_get_node_immediately_revives_dormancy(graph_mgr):
    node_id = "om-get-revive"
    await graph_mgr.get_or_create_node(node_id, title="Archived notes", mode="normal")
    old = time.time() - (35 * 86400)
    await graph_mgr.update_node(node_id, last_active_at=old)
    dormant = await graph_mgr.get_node(node_id, touch_active=False)
    assert dormant["is_dormant"] is True
    assert dormant["fade_alpha"] < 1.0

    revived = await graph_mgr.get_node(node_id, touch_active=True)
    assert revived["is_dormant"] is False
    assert revived["dormancy_score"] == 0.0
    assert revived["fade_alpha"] == 1.0
    assert revived["last_active_at"] > old


@pytest.mark.asyncio
async def test_search_overrides_dormant_hide(graph_mgr):
    now = time.time()
    await graph_mgr.get_or_create_node(
        "om-hidden-dormant", title="Needle haystack chat", mode="normal"
    )
    await graph_mgr.update_node("om-hidden-dormant", last_active_at=now - (55 * 86400))
    for i in range(4):
        nid = f"om-hot-{i}"
        await graph_mgr.get_or_create_node(nid, title=f"Hot {i}", mode="normal")
        await graph_mgr.update_node(nid, last_active_at=now - i)

    graph = await graph_mgr.get_graph_data(
        mode="normal",
        max_nodes=2,
        show_dormant=False,
        search="Needle",
        clustered=False,
    )
    ids = {n["id"] for n in graph["nodes"]}
    assert "om-hidden-dormant" in ids
    hit = next(n for n in graph["nodes"] if n["id"] == "om-hidden-dormant")
    assert hit["is_dormant"] is True
    assert hit["fade_alpha"] < 1.0


@pytest.mark.asyncio
async def test_focus_search_overrides_node_cap(graph_mgr):
    now = time.time()
    await graph_mgr.get_or_create_node(
        "om-focus-target", title="Rare zebra topic", mode="normal"
    )
    await graph_mgr.update_node("om-focus-target", last_active_at=now - (30 * 86400))
    for i in range(5):
        nid = f"om-recent-{i}"
        await graph_mgr.get_or_create_node(nid, title=f"Recent {i}", mode="normal")
        await graph_mgr.update_node(nid, last_active_at=now - i)

    graph = await graph_mgr.get_graph_data(
        mode="normal",
        max_nodes=3,
        show_dormant=False,
        search="zebra",
        clustered=False,
    )
    ids = {n["id"] for n in graph["nodes"]}
    assert "om-focus-target" in ids
