import pytest
from backend.core.intelligence.jarvis.intent_router import WrockIntentRouter
from backend.core.intelligence.jarvis.tools import SpatialToolRegistry
from backend.core.intelligence.jarvis.memory import WrockMemory
from backend.core.perception.spatial.scene_graph import SpatialSceneGraph
from backend.core.perception.spatial.tactical_observer import TacticalObserver

def test_phrase_routing_checks():
    scene = SpatialSceneGraph()
    obs = TacticalObserver()
    tools = SpatialToolRegistry(scene, obs)
    mem = WrockMemory()
    router = WrockIntentRouter(tools, mem)

    map_queries = [
        "search odisha on google maps",
        "i said him to search odisha on google maps",
        "search for odisha in google maps",
        "search odisha on maps",
        "search odisha on map",
    ]

    for q in map_queries:
        resp = router._route_heuristic(q, None, {})
        assert resp.action_type == "MAP_SEARCH"
        assert "Odisha" in resp.spoken_text
        assert any(t.tool_name == "search_map_location" for t in resp.tool_results)

    stop_queries = [
        "stop",
        "stop it",
        "please stop it",
        "shut up",
        "bas karo",
        "ruk jao",
    ]

    for q in stop_queries:
        resp = router._route_heuristic(q, None, {})
        assert resp.action_type == "INTERRUPT"
        assert resp.spoken_text == "Stopped."
