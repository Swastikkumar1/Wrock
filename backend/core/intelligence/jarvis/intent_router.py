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
        map_match = re.search(r"\b(?:in\s+map\s+search|search\s+in\s+map|search\s+on\s+map|search\s+map\s+for|find\s+on\s+map|find\s+in\s+map|show\s+on\s+map|show\s+in\s+map|locate\s+on\s+map|locate\s+in\s+map|map\s+search)\s+(.+)", u)
        if not map_match:
            map_match = re.search(r"\b(?:search|find|show|locate|where\s+is)\s+(?:for\s+)?(.+?)\s+(?:in|on)\s+map\b", u)

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
        elif (
            any(w in u for w in ["god's eye", "gods eye", "birds eye", "bird's eye", "satellite view", "edith view", "top down"]) or
            (any(w in u for w in ["open map", "show map"]) and not any(g in u for g in ["google", "chrome", "search", "find", "locate", "where is"]))
        ):
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

        # --- F. PC AUTOMATION: SYSTEM STATUS & BATTERY / LAPTOP STATUS ---
        elif any(w in u for w in [
            "laptop status", "laptop", "pc status", "system status", "battery", 
            "battery temp", "cpu", "gpu", "ram", "hardware", "diagnostics", 
            "temp", "temperature", "usage", "computer status", "specs", "how is my laptop",
            "laptop health", "pc health", "resource usage"
        ]):
            res = self.tool_registry.execute_tool("pc_system_status", {})
            tools_executed.append(res)
            action_type = "SYSTEM_STATUS"
            spoken = res.output_message
            self.memory.pending_action = "close_heavy_apps"

        # --- F2. CONVERSATIONAL FOLLOW-UP CONFIRMATION ("yes", "turn off", "do it", "sure", "so do it know") ---
        elif (
            (self.memory.pending_action == "close_heavy_apps" and (
                any(w in u.split() for w in ["yes", "yeah", "yep", "sure", "do", "turn", "close", "kill"]) or
                any(phrase in u for phrase in ["turn off", "close them", "do it", "yes do it", "clean memory", "turn it off", "turn off something", "so do it now", "so do it know", "do it now"])
            )) or
            any(phrase in u for phrase in ["so do it now", "so do it know", "clean up the apps", "turn off background apps"])
        ):
            self.memory.pending_action = None
            res = self.tool_registry.execute_tool("pc_close_heavy_apps", {})
            tools_executed.append(res)
            action_type = "CLOSE_PROCESSES"
            spoken = res.output_message

        elif self.memory.pending_action == "close_heavy_apps" and any(
            w in u.split() for w in ["no", "nah", "don't", "dont", "leave it", "keep them", "cancel"]
        ):
            self.memory.pending_action = None
            spoken = "Understood. Keeping all active applications and tabs running, Swastik."

        # --- F3. PC AUTOMATION: CLOSE / TURN OFF APPLICATION ("off my chrome browser", "close chrome", "turn off chrome", "kill spotify") ---
        elif (
            any(w in u for w in ["turn off", "close", "shut down", "kill", "terminate", "exit", "quit", "off"]) and
            any(app in u for app in ["chrome", "browser", "firefox", "edge", "spotify", "discord", "notepad", "calculator", "calc", "cursor", "steam", "slack", "tabs", "all apps"])
        ) or re.search(r"\b(?:turn\s+off|close|shut\s+down|kill|exit|quit|terminate|off)\s+(?:my\s+)?(?:the\s+)?([a-z0-9_\-\.]+)\b", u):
            close_match = re.search(
                r"\b(?:turn\s+off|close|shut\s+down|kill|exit|quit|terminate|off)\s+(?:my\s+)?(?:the\s+)?([a-z0-9_\-\.\s]+?)(?:\s+browser|\s+app|\s+application)?\b",
                u
            )
            raw_target = close_match.group(1).strip() if close_match else "chrome"
            clean_app = re.sub(r"^(?:my|the)\s+", "", raw_target).strip()
            clean_app = re.sub(r"\s+(?:browser|app|application)$", "", clean_app).strip()

            if clean_app in ["it", "them", "this", "something", "heavy apps", "background", "apps", "processes", "tabs", "all"]:
                res = self.tool_registry.execute_tool("pc_close_heavy_apps", {})
                action_type = "CLOSE_PROCESSES"
            else:
                res = self.tool_registry.execute_tool("pc_close_application", {"app_name": clean_app})
                action_type = "CLOSE_APPLICATION"
            tools_executed.append(res)
            spoken = res.output_message

        # --- G. PC AUTOMATION: LOCK PC ---
        elif any(w in u for w in ["lock pc", "lock screen", "lock workstation", "lock computer"]):
            res = self.tool_registry.execute_tool("pc_lock_workstation", {})
            tools_executed.append(res)
            action_type = "LOCK_PC"
            spoken = res.output_message

        # --- H. GOOGLE MAPS & MAP LOCATION SEARCH ("just search for the google maps", "search Paris on map", "open google maps") ---
        elif any(m in u for m in ["google maps", "google map", "maps.google.com"]) or map_match or (
            ("maps" in u or " map" in u) and any(w in u for w in ["search", "open", "go to", "launch", "find", "locate", "where is", "show"]) and not any(k in u for k in ["tactical", "god's eye", "gods eye", "orbit", "radar"])
        ):
            clean = u
            clean = re.sub(r"^(?:just\s+|can\s+you\s+|could\s+you\s+|please\s+|i\s+said\s+(?:to\s+)?|i\s+said\s+him\s+to\s+)?", "", clean, flags=re.IGNORECASE).strip()
            clean = re.sub(r"^(?:search(?:\s+for|\s+on|\s+in)?|open|go\s+to|launch|find|locate|where\s+is|show)\s+", "", clean, flags=re.IGNORECASE).strip()
            clean = re.sub(r"^(?:the\s+)?(?:google\s+maps?|maps?)(?:\s+for)?\s*", "", clean, flags=re.IGNORECASE).strip()
            clean = re.sub(r"\s+(?:on|in|at)\s+(?:the\s+)?(?:google\s+maps?|maps?)\b.*$", "", clean, flags=re.IGNORECASE).strip()
            clean = re.sub(r"\b(?:on|in|at)\s+(?:chrome|browser)\b", "", clean, flags=re.IGNORECASE).strip()
            clean = re.sub(r"^(?:for|the)\s+", "", clean, flags=re.IGNORECASE).strip()
            clean = clean.strip(" ?.,!\"'")

            if clean and clean not in ["google maps", "google map", "maps", "map", "it", "this", "that"]:
                target_loc = clean.title()
                res = self.tool_registry.execute_tool("search_map_location", {"location_name": target_loc})
                tools_executed.append(res)
                action_type = "MAP_SEARCH"
                new_cam_mode = "GODS_EYE"
                spoken = res.output_message
            else:
                res = self.tool_registry.execute_tool("open_chrome_or_search", {"query_or_url": "https://maps.google.com"})
                tools_executed.append(res)
                action_type = "CHROME_OPEN"
                new_cam_mode = "GODS_EYE"
                spoken = "Opening Google Maps on Chrome, Swastik."

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
            any(w in u for w in ["open", "go to", "launch", "search"]) and any(site in u for site in ["reddit", "github", "chatgpt", "openai", "twitter", "netflix", "amazon", "wikipedia", "wiki", "gmail", "facebook", "instagram", "linkedin", "discord", "twitch", "stackoverflow", "huggingface"])
        ) or any(ext in u for ext in [".com", ".org", ".net", ".io", ".ai", ".co", ".gov", ".edu", ".app", ".dev"]):
            target = u
            target = re.sub(r"^(?:just\s+|can\s+you\s+|could\s+you\s+|please\s+|i\s+said\s+(?:to\s+)?|i\s+want\s+to\s+)?", "", target, flags=re.IGNORECASE).strip()
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
            target = re.sub(r"^(?:the\s+)", "", target, flags=re.IGNORECASE).strip()
            target = target.strip(" ?.,!\"'")

            res = self.tool_registry.execute_tool("open_chrome_or_search", {"query_or_url": target})
            tools_executed.append(res)
            action_type = "CHROME_OPEN"
            spoken = res.output_message

        # --- L. GENERAL SEARCH & GOOGLE LOOKUP ("just search for ...", "search google for ...", "google ...", "search the web for ...") ---
        elif any(w in u for w in ["search google for", "search google", "search the web for", "search web for", "google ", "search for ", "look up "]) or re.search(r"^(?:just\s+|can\s+you\s+|please\s+)?(?:search|google|look\s+up)\b", u):
            query = u
            query = re.sub(r"^(?:just\s+|can\s+you\s+|could\s+you\s+|please\s+|i\s+said\s+(?:to\s+)?|i\s+said\s+him\s+to\s+)?", "", query, flags=re.IGNORECASE).strip()
            query = re.sub(r"^(?:search\s+google\s+for|search\s+google|search\s+the\s+web\s+for|search\s+web\s+for|search\s+for|search|google|look\s+up)\s+", "", query, flags=re.IGNORECASE).strip()
            query = re.sub(r"^(?:the\s+)", "", query, flags=re.IGNORECASE).strip()
            query = re.sub(r"\s+(?:on|in)\s+(?:google(?:\s+search)?|chrome|browser|web|the\s+web)$", "", query, flags=re.IGNORECASE).strip()
            query = query.strip(" ?.,!\"'")

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

        elif any(w in u for w in ["who are you", "what is your name", "what is wrock", "world reset", "wrold reset", "reset on command", "kaun ho", "tum kaun"]):
            spoken = "I am Wrock: World Reset On Command. Your autonomous spatial-AI assistant, Swastik."
            action_type = "CHAT"

        elif any(w in u for w in ["thank you", "thanks", "dhanyawad", "shukriya"]):
            spoken = "Always at your service, Swastik."
            action_type = "CHAT"

        elif any(w in u for w in ["good job", "well done", "nice work", "awesome", "great"]):
            spoken = "Thank you, Swastik. Systems running at peak efficiency."
            action_type = "CHAT"

        elif any(w in u for w in ["what can you do", "features", "kya kar sakte ho", "help"]):
            spoken = "I control applications, manage system resources, capture screenshots, adjust volume, and navigate the 3D map. What shall we do, Swastik?"
            action_type = "CHAT"

        elif any(w in u for w in ["hello", "hey", "wrock", "hi", "hi rock", "hi wrock", "namaste", "suno"]):
            spoken = "Online and standing by, Swastik."
            action_type = "CHAT"

        elif any(phrase in u for phrase in ["so do it now", "so do it know", "do it now", "clean up now", "proceed", "go ahead"]):
            res = self.tool_registry.execute_tool("pc_close_heavy_apps", {})
            tools_executed.append(res)
            action_type = "CLOSE_PROCESSES"
            spoken = res.output_message

        else:
            # Intelligent conversational response without echoing raw user text
            if any(q in u for q in ["what", "how", "why", "when", "where", "can you"]):
                spoken = "I can control applications, manage your system status, capture screenshots, and navigate the 3D map. What would you like me to do, Swastik?"
            elif any(w in u for w in ["yes", "yeah", "yep", "sure", "ok", "okay"]):
                spoken = "Confirmed, Swastik. What directive would you like executed?"
            else:
                spoken = "Standing by for your directive, Swastik."
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
