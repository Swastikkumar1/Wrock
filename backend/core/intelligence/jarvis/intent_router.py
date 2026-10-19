from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import httpx
import json
import logging
import re
from .tools import SpatialToolRegistry, ToolCallResult
from .memory import WrockMemory
from ...perception.spatial.scene_graph import SpatialSceneGraph
from ...perception.spatial.tactical_observer import TacticalObserver

logger = logging.getLogger("WrockIntentRouter")


@dataclass
class IntentResponse:
    spoken_text: str
    tool_results: List[ToolCallResult] = field(default_factory=list)
    hud_alert: Optional[str] = None
    target_entity_id: Optional[str] = None
    camera_mode: Optional[str] = None
    pov_entity_id: Optional[str] = None
    action_type: Optional[str] = None


class WrockIntentRouter:
    """
    Multimodal Contextual Intent Engine for Wrock.
    Fuses voice commands with 3D spatial context, hand gestures, and Windows PC automation.
    """

    def __init__(
        self,
        tool_registry: SpatialToolRegistry,
        memory: WrockMemory,
        llm_provider: str = "mock",
        openai_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o",
        gemini_api_key: Optional[str] = None,
        ollama_host: str = "http://localhost:11434",
        ollama_model: str = "llama3"
    ):
        self.tool_registry = tool_registry
        self.memory = memory
        self.llm_provider = llm_provider
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.gemini_api_key = gemini_api_key
        self.ollama_host = ollama_host
        self.ollama_model = ollama_model

    def build_multimodal_system_prompt(self, perception_state: Dict[str, Any]) -> str:
        hovered = perception_state.get("hovered_object_id")
        selected = perception_state.get("selected_object_id")
        gestures = perception_state.get("active_gestures", [])
        camera_mode = perception_state.get("camera_mode", "ORBITAL")
        scene_summary = perception_state.get("scene_graph_summary", {})
        entity_ids = scene_summary.get("entity_ids", [])

        prompt = f"""You are WROCK, a high-speed, direct Multimodal Spatial-AI Assistant & OS Automation Core serving Swastik.
You have real-time perception over a 3D tactical map, drone feeds, hand tracking gestures, and Windows PC automation.

[CURRENT CONTEXT]
- Primary User: Swastik
- Camera Perspective: {camera_mode}
- User Hand Gesture: {gestures}
- Physically Hovered / Pointed Target: {hovered or 'NONE'}
- Currently Locked Target: {selected or 'NONE'}
- Available Tracked Entities: {entity_ids}
- Total Tracked Signatures: {scene_summary.get('total_entities', 0)}

[CORE DIRECTIVES]
1. USER: Swastik. Address the user as Swastik. Never refer to the user as King.
2. PERSONA: Minimal, direct, functional. Zero filler, no canned pleasantries or conversational padding.
3. PC AUTOMATION & WEB: Execute requested OS actions, app launches, Chrome web navigation, YouTube playback, Spotify searches, and map locations immediately.
4. ADAPTIVE CONCISENESS: Output short, clear confirmations (e.g. 'Screenshot saved.', 'Yes, I am online. What\'s your command, Swastik?', 'Searching Spotify for daft punk.').
5. DEICTIC BINDING: Resolve 'this', 'that', 'it', or 'here' to '{hovered or selected or 'DRONE-STARK-01'}'.
"""
        return prompt

    async def route_intent(
        self,
        user_utterance: str,
        perception_state: Dict[str, Any]
    ) -> IntentResponse:
        utterance = user_utterance.strip()
        hovered_id = perception_state.get("hovered_object_id")
        selected_id = perception_state.get("selected_object_id")

        self.memory.add_turn("user", utterance, {"perception": perception_state})
        target_candidate = hovered_id or selected_id or self.memory.last_focused_entity_id

        # 1. External LLM if configured
        if self.llm_provider == "openai" and self.openai_api_key:
            return await self._route_openai(utterance, perception_state, target_candidate)
        elif self.llm_provider == "ollama":
            return await self._route_ollama(utterance, perception_state, target_candidate)

        # 2. Fast Deterministic Spatial & PC Automation Engine (<10ms latency)
        return self._route_heuristic(utterance, target_candidate, perception_state)

    def _route_heuristic(
        self,
        utterance: str,
        target_id: Optional[str],
        perception_state: Dict[str, Any]
    ) -> IntentResponse:
        u = utterance.lower()
        tools_executed: List[ToolCallResult] = []
        new_cam_mode: Optional[str] = None
        pov_entity: Optional[str] = None
        action_type: Optional[str] = None
        spoken = ""

        # --- A. WATCH SOMEONE'S POV IN MAP / GOD'S EYE WITH RECON FEED ---
        if any(w in u for w in ["watch pov", "someone's pov", "someones pov", "drone pov", "watch drone", "drone camera", "pov in map", "recon feed", "cockpit view"]):
            # Determine target entity to watch
            pov_target = "UAV-BOGEY-99" if "bogey" in u or "hostile" in u else (target_id or "DRONE-STARK-01")
            res = self.tool_registry.execute_tool("watch_entity_pov", {"target_id": pov_target})
            tools_executed.append(res)
            new_cam_mode = "GODS_EYE"
            pov_entity = pov_target
            action_type = "POV_ENGAGED"
            spoken = f"Live POV active for {pov_target}."

        # --- B. GOD'S EYE / SATELLITE TOP-DOWN VIEW ---
        elif any(w in u for w in ["god's eye", "gods eye", "birds eye", "bird's eye", "open map", "show map", "satellite view", "edith view", "top down"]):
            res = self.tool_registry.execute_tool("set_camera_view", {"mode": "GODS_EYE"})
            tools_executed.append(res)
            new_cam_mode = "GODS_EYE"
            action_type = "CAMERA_SWITCH"
            spoken = "God's Eye perspective engaged."

        elif any(w in u for w in ["orbital view", "orbit view", "isometric", "tactical overview"]):
            res = self.tool_registry.execute_tool("set_camera_view", {"mode": "ORBITAL"})
            tools_executed.append(res)
            new_cam_mode = "ORBITAL"
            action_type = "CAMERA_SWITCH"
            spoken = "Orbital perspective active."

        elif any(w in u for w in ["hologram view", "workspace", "holo mode", "tabletop"]):
            res = self.tool_registry.execute_tool("set_camera_view", {"mode": "HOLOGRAM"})
            tools_executed.append(res)
            new_cam_mode = "HOLOGRAM"
            action_type = "CAMERA_SWITCH"
            spoken = "Hologram workspace active."

        # --- C. ZOOM / PINCH ON MAP ---
        elif any(w in u for w in ["zoom in", "closer", "zoom map in"]):
            res = self.tool_registry.execute_tool("zoom_gods_eye_map", {"zoom_factor": 1.3})
            tools_executed.append(res)
            action_type = "MAP_ZOOM"
            spoken = "Zooming in."

        elif any(w in u for w in ["zoom out", "wider", "zoom map out"]):
            res = self.tool_registry.execute_tool("zoom_gods_eye_map", {"zoom_factor": 0.75})
            tools_executed.append(res)
            action_type = "MAP_ZOOM"
            spoken = "Zooming out."

        # --- D. PC AUTOMATION: SCREENSHOT ---
        elif any(w in u for w in ["screenshot", "capture screen", "screen shot", "screen grab", "photo of screen"]):
            res = self.tool_registry.execute_tool("pc_take_screenshot", {})
            tools_executed.append(res)
            action_type = "SCREENSHOT"
            spoken = res.output_message

        # --- E. PC AUTOMATION: VOLUME ---
        elif any(w in u for w in ["volume up", "increase volume", "louder", "awaaz badhao", "sound up"]):
            res = self.tool_registry.execute_tool("pc_change_volume", {"action": "up"})
            tools_executed.append(res)
            action_type = "VOLUME"
            spoken = res.output_message

        elif any(w in u for w in ["volume down", "decrease volume", "lower volume", "softer", "awaaz kam", "sound down"]):
            res = self.tool_registry.execute_tool("pc_change_volume", {"action": "down"})
            tools_executed.append(res)
            action_type = "VOLUME"
            spoken = res.output_message

        elif any(w in u for w in ["mute", "unmute", "quiet", "shant", "silence"]):
            res = self.tool_registry.execute_tool("pc_change_volume", {"action": "mute"})
            tools_executed.append(res)
            action_type = "VOLUME"
            spoken = res.output_message

        # --- F. PC AUTOMATION: SYSTEM STATUS & BATTERY ---
        elif any(w in u for w in ["system status", "pc status", "battery", "cpu", "ram", "hardware", "diagnostics of pc", "computer status"]):
            res = self.tool_registry.execute_tool("pc_system_status", {})
            tools_executed.append(res)
            action_type = "SYSTEM_STATUS"
            spoken = res.output_message

        # --- G. PC AUTOMATION: LOCK PC ---
        elif any(w in u for w in ["lock pc", "lock screen", "lock workstation", "lock computer"]):
            res = self.tool_registry.execute_tool("pc_lock_workstation", {})
            tools_executed.append(res)
            action_type = "LOCK_PC"
            spoken = res.output_message

        # --- H. MAP LOCATION SEARCH ("in map search Tokyo", "search Paris on map") ---
        map_match = re.search(r"\b(?:in\s+map\s+search|search\s+in\s+map|search\s+on\s+map|search\s+map\s+for|find\s+on\s+map|find\s+in\s+map|show\s+on\s+map|show\s+in\s+map|locate\s+on\s+map|locate\s+in\s+map|map\s+search)\s+(.+)", u)
        if not map_match:
            map_match = re.search(r"\b(?:search|find|show|locate|where\s+is)\s+(?:for\s+)?(.+?)\s+(?:in|on)\s+map\b", u)

        if map_match:
            raw_place = map_match.group(1).strip()
            place = target_id or "Tactical Location" if raw_place in ["that place", "this place", "it", "here", "the place"] else raw_place.title()
            res = self.tool_registry.execute_tool("search_map_location", {"location_name": place})
            tools_executed.append(res)
            action_type = "MAP_SEARCH"
            new_cam_mode = "GODS_EYE"
            spoken = res.output_message

        # --- I. SPOTIFY SEARCH & PLAY ("search something in spotify", "play ... on spotify") ---
        elif "spotify" in u:
            q = re.sub(r"\b(open|launch|start)?\s*spotify\s*(and)?\s*(search|play|listen\s+to)?\s*(for)?\b", "", u, flags=re.IGNORECASE).strip()
            q = re.sub(r"\b(on|in|at)\s+spotify\b", "", q, flags=re.IGNORECASE).strip()
            q = re.sub(r"^(search|play|listen\s+to|find)\s+(for\s+)?", "", q, flags=re.IGNORECASE).strip()
            q = re.sub(r"\s+\b(on|in|at)\b$", "", q, flags=re.IGNORECASE).strip()
            res = self.tool_registry.execute_tool("search_spotify", {"query": q})
            tools_executed.append(res)
            action_type = "SPOTIFY_SEARCH"
            spoken = res.output_message

        # --- J. YOUTUBE SEARCH & PLAY ("search something in youtube", "play ... on youtube") ---
        elif "youtube" in u:
            q = re.sub(r"\b(open|launch|start)?\s*youtube\s*(and)?\s*(search|play|watch)?\s*(for)?\b", "", u, flags=re.IGNORECASE).strip()
            q = re.sub(r"\b(on|in|at)\s+youtube\b", "", q, flags=re.IGNORECASE).strip()
            q = re.sub(r"^(search|play|watch|find)\s+(for\s+)?", "", q, flags=re.IGNORECASE).strip()
            q = re.sub(r"\s+\b(on|in|at)\b$", "", q, flags=re.IGNORECASE).strip()
            res = self.tool_registry.execute_tool("search_youtube", {"query": q})
            tools_executed.append(res)
            action_type = "YOUTUBE_SEARCH"
            spoken = res.output_message

        # --- K. CHROME & WEB NAVIGATION ("open anything on chrome", "go to chrome", "search ... on chrome") ---
        elif any(k in u for k in ["on chrome", "in chrome", "go to chrome", "open chrome"]) or (
            any(w in u for w in ["open", "go to", "launch", "search"]) and any(site in u for site in ["reddit", "github", "chatgpt", "openai", "twitter", "netflix", "amazon", "wikipedia", "wiki", "gmail", "facebook", "instagram", "linkedin", "discord", "twitch", "stackoverflow"])
        ) or any(ext in u for ext in [".com", ".org", ".net", ".io", ".ai", ".co", ".gov", ".edu", ".app", ".dev"]):
            target = u
            for prefix in [
                r"^go\s+to\s+chrome\s+(and\s+)?(search\s+for|search)?\s*",
                r"^open\s+chrome\s+(and\s+)?(search\s+for|search)?\s*",
                r"^open\s+",
                r"^go\s+to\s+",
                r"^launch\s+",
                r"^search\s+for\s+",
                r"^search\s+",
            ]:
                target = re.sub(prefix, "", target, flags=re.IGNORECASE).strip()

            target = re.sub(r"\s+(on|in)\s+chrome\b", "", target, flags=re.IGNORECASE).strip()
            target = re.sub(r"\s+(on|in)\s+browser\b", "", target, flags=re.IGNORECASE).strip()

            res = self.tool_registry.execute_tool("open_chrome_or_search", {"query_or_url": target})
            tools_executed.append(res)
            action_type = "CHROME_OPEN"
            spoken = res.output_message

        # --- L. GENERAL GOOGLE SEARCH ---
        elif any(w in u for w in ["search google for", "search google", "search the web for", "search web for", "google "]):
            query = re.sub(r"^(search google for|search google|search the web for|search web for|google)\s*", "", u, flags=re.IGNORECASE).strip()
            res = self.tool_registry.execute_tool("open_chrome_or_search", {"query_or_url": query})
            tools_executed.append(res)
            action_type = "CHROME_OPEN"
            spoken = res.output_message

        # --- M. DESKTOP APPS (Cursor, Notepad, Calculator, Terminal, Explorer) ---
        elif any(w in u for w in ["cursor", "code editor", "vscode"]):
            res = self.tool_registry.execute_tool("pc_launch_app", {"app_name": "cursor"})
            tools_executed.append(res)
            action_type = "APP_LAUNCHED"
            spoken = res.output_message

        elif "notepad" in u:
            res = self.tool_registry.execute_tool("pc_launch_app", {"app_name": "notepad"})
            tools_executed.append(res)
            action_type = "APP_LAUNCHED"
            spoken = res.output_message

        elif any(w in u for w in ["calculator", "calc"]):
            res = self.tool_registry.execute_tool("pc_launch_app", {"app_name": "calc"})
            tools_executed.append(res)
            action_type = "APP_LAUNCHED"
            spoken = res.output_message

        elif any(w in u for w in ["terminal", "powershell", "command prompt", "cmd"]):
            res = self.tool_registry.execute_tool("pc_launch_app", {"app_name": "terminal"})
            tools_executed.append(res)
            action_type = "APP_LAUNCHED"
            spoken = res.output_message

        elif any(w in u for w in ["file explorer", "my computer", "files", "open explorer"]):
            res = self.tool_registry.execute_tool("pc_launch_app", {"app_name": "explorer"})
            tools_executed.append(res)
            action_type = "APP_LAUNCHED"
            spoken = res.output_message

        elif any(w in u for w in ["close window", "close this window", "exit app"]):
            res = self.tool_registry.execute_tool("pc_close_window", {})
            tools_executed.append(res)
            action_type = "CLOSE_WINDOW"
            spoken = res.output_message

        # --- I. SPATIAL: INSPECT / LOCK / RADAR / ANCHOR ---
        elif any(w in u for w in ["inspect", "analyze", "scan this", "what is this", "diagnostics", "who is that"]):
            effective_target = target_id or "DRONE-STARK-01"
            res = self.tool_registry.execute_tool("inspect_entity", {"target_id": effective_target})
            tools_executed.append(res)
            self.memory.set_focus(effective_target)
            spoken = f"Inspecting signature {effective_target}. Diagnostic telemetry streamed to HUD."
            action_type = "INSPECT"

        elif any(w in u for w in ["lock", "track target", "engage targeting", "lock on", "lock bogey"]):
            effective_target = "UAV-BOGEY-99" if "bogey" in u or "hostile" in u else (target_id or "UAV-BOGEY-99")
            res = self.tool_registry.execute_tool("lock_target", {"target_id": effective_target})
            tools_executed.append(res)
            self.memory.set_focus(effective_target)
            spoken = f"Target lock confirmed on {effective_target}. Continuous trajectory tracking engaged."
            action_type = "TARGET_LOCKED"

        elif any(w in u for w in ["scan", "sweep", "radar", "radar sweep", "threats"]):
            res = self.tool_registry.execute_tool("execute_tactical_scan", {"radius_km": 30.0})
            tools_executed.append(res)
            spoken = res.output_message
            action_type = "RADAR_SWEEP"

        elif any(w in u for w in ["anchor", "mark waypoint", "beacon", "drop anchor"]):
            res = self.tool_registry.execute_tool("deploy_spatial_anchor", {"label": "Tactical Waypoint"})
            tools_executed.append(res)
            spoken = res.output_message
            action_type = "SPATIAL_ANCHOR"

        # --- J. CONVERSATIONAL / MINIMAL & FUNCTIONAL ---
        elif any(w in u for w in ["wake up wrock", "wake up rock", "wake up", "wrock online"]):
            spoken = "Yes, I am online. What's your command, Swastik?"
            action_type = "WAKE_UP"

        elif any(w in u for w in ["how are you", "kese ho", "kaise ho", "kemon acho"]):
            spoken = "Systems operational. Standing by."
            action_type = "CHAT"

        elif any(w in u for w in ["say something", "kuch bolo", "speak", "talk to me"]):
            spoken = "Standing by for input."
            action_type = "CHAT"

        elif any(w in u for w in ["who are you", "what is your name", "kaun ho", "tum kaun"]):
            spoken = "Wrock Assistant."
            action_type = "CHAT"

        elif any(w in u for w in ["what can you do", "features", "kya kar sakte ho", "help"]):
            spoken = "Navigation, camera gestures, map control, volume, screenshots, and OS automation."
            action_type = "CHAT"

        elif any(w in u for w in ["hello", "hey", "wrock", "hi", "hi rock", "hi wrock", "namaste", "suno"]):
            spoken = "Ready."
            action_type = "CHAT"

        else:
            spoken = f"Acknowledged: {user_utterance.strip()}."
            action_type = "CHAT"

        self.memory.add_turn("assistant", spoken)

        return IntentResponse(
            spoken_text=spoken,
            tool_results=tools_executed,
            hud_alert=tools_executed[0].output_message if tools_executed else None,
            target_entity_id=target_id,
            camera_mode=new_cam_mode,
            pov_entity_id=pov_entity,
            action_type=action_type
        )

    async def _route_openai(
        self,
        utterance: str,
        perception_state: Dict[str, Any],
        target_candidate: Optional[str]
    ) -> IntentResponse:
        system_prompt = self.build_multimodal_system_prompt(perception_state)
        tools = [{"type": "function", "function": t} for t in self.tool_registry.get_tool_definitions()]
        messages = [
            {"role": "system", "content": system_prompt},
            *self.memory.get_context_turns()
        ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                    json={
                        "model": self.openai_model,
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": "auto",
                        "temperature": 0.3,
                    }
                )
                data = res.json()
                msg = data["choices"][0]["message"]
                tool_calls = msg.get("tool_calls", [])
                spoken = msg.get("content") or ""

                executed_tools = []
                new_cam = None
                pov_id = None
                action = None
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    fn_args = json.loads(tc["function"]["arguments"])
                    t_res = self.tool_registry.execute_tool(fn_name, fn_args)
                    executed_tools.append(t_res)
                    if t_res.new_camera_mode:
                        new_cam = t_res.new_camera_mode
                    if t_res.pov_entity_id:
                        pov_id = t_res.pov_entity_id
                    if t_res.action_type:
                        action = t_res.action_type
                    if not spoken:
                        spoken = t_res.output_message

                if not spoken and executed_tools:
                    spoken = executed_tools[0].output_message

                self.memory.add_turn("assistant", spoken)
                return IntentResponse(
                    spoken_text=spoken,
                    tool_results=executed_tools,
                    hud_alert=executed_tools[0].output_message if executed_tools else None,
                    target_entity_id=target_candidate,
                    camera_mode=new_cam,
                    pov_entity_id=pov_id,
                    action_type=action
                )
        except Exception as e:
            logger.error(f"OpenAI routing failed: {e}. Falling back to deterministic engine.")
            return self._route_heuristic(utterance, target_candidate, perception_state)

    async def _route_ollama(
        self,
        utterance: str,
        perception_state: Dict[str, Any],
        target_candidate: Optional[str]
    ) -> IntentResponse:
        try:
            system_prompt = self.build_multimodal_system_prompt(perception_state)
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.ollama_host}/api/chat",
                    json={
                        "model": self.ollama_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": utterance}
                        ],
                        "stream": False
                    }
                )
                data = res.json()
                text = data.get("message", {}).get("content", "")
                heuristic_resp = self._route_heuristic(utterance, target_candidate, perception_state)
                spoken = text if text else heuristic_resp.spoken_text
                self.memory.add_turn("assistant", spoken)
                heuristic_resp.spoken_text = spoken
                return heuristic_resp
        except Exception as e:
            logger.error(f"Ollama routing failed: {e}. Falling back to deterministic engine.")
            return self._route_heuristic(utterance, target_candidate, perception_state)


# Backward compatibility alias
JarvisIntentRouter = WrockIntentRouter
