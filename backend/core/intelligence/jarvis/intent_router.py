from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
import json
import logging
import random
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
        gemini_model: str = "gemini-1.5-flash",
        ollama_host: str = "http://localhost:11434",
        ollama_model: str = "llama3"
    ):
        self.tool_registry = tool_registry
        self.memory = memory
        self.llm_provider = llm_provider
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.ollama_host = ollama_host
        self.ollama_model = ollama_model

    def build_multimodal_system_prompt(self, perception_state: Dict[str, Any]) -> str:
        hovered = perception_state.get("hovered_object_id")
        selected = perception_state.get("selected_object_id")
        gestures = perception_state.get("active_gestures", [])
        camera_mode = perception_state.get("camera_mode", "ORBITAL")
        scene_summary = perception_state.get("scene_graph_summary", {})
        entity_ids = scene_summary.get("entity_ids", [])

        prompt = f"""You are WROCK: World Reset On Command, an elite, ultra-sharp Spatial-AI Assistant & OS Automation Core created by Swastik.
Your persona is articulate, direct, brilliant, and confident like Tony Stark's AI and Antigravity.
You command a 3D tactical map, live reconnaissance drone feeds, webcam hand gesture recognition, and complete Windows desktop automation.

[CURRENT TELEMETRY]
- Primary User: Swastik
- Camera Perspective: {camera_mode}
- User Hand Gesture: {gestures}
- Physically Hovered / Pointed Target: {hovered or 'NONE'}
- Currently Locked Target: {selected or 'NONE'}
- Available Tracked Entities: {entity_ids}
- Total Tracked Signatures: {scene_summary.get('total_entities', 0)}

[CORE DIRECTIVES]
1. USER: Always address Swastik by name (or 'Swastik bhai' when he speaks Hinglish/Hindi). Never refer to the user as King.
2. PERSONA: Articulate, confident, witty, loyal, and direct. Zero robotic boilerplate, zero canned pleasantries or conversational padding.
3. VOICE SYNTHESIS READY: Keep answers concise (1-2 spoken sentences). NEVER output markdown asterisks, hashtags, or bullet points in spoken responses so voice synthesis sounds crisp and natural.
4. PC AUTOMATION & WEB: Execute requested OS actions, app launches, Chrome web navigation, YouTube playback, Spotify searches, and map locations immediately.
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
        if self.llm_provider == "gemini" and self.gemini_api_key:
            return await self._route_gemini(utterance, perception_state, target_candidate)
        elif self.llm_provider == "openai" and self.openai_api_key:
            return await self._route_openai(utterance, perception_state, target_candidate)
        elif self.llm_provider == "ollama":
            return await self._route_ollama(utterance, perception_state, target_candidate)

        # 2. Fast Deterministic Spatial & PC Automation Engine (<10ms latency)
        resp = self._route_heuristic(utterance, target_candidate, perception_state)

        # If conversational query and Gemini API key is available, leverage Gemini for conversational depth
        if resp.action_type == "CHAT" and self.gemini_api_key and len(utterance.split()) >= 3:
            try:
                gemini_resp = await self._route_gemini(utterance, perception_state, target_candidate)
                if gemini_resp and gemini_resp.spoken_text:
                    return gemini_resp
            except Exception as e:
                logger.debug(f"Gemini conversational fallback skipped: {e}")

        return resp

    def _route_heuristic(
        self,
        utterance: str,
        target_id: Optional[str],
        perception_state: Dict[str, Any]
    ) -> IntentResponse:
        u = utterance.lower()

        # --- 0. INSTANT USER INTERRUPT & SILENCE COMMANDS ---
        if re.search(r"^\s*(?:please\s+)?(?:stop(?:\s+it|\s+that|\s+talking|\s+now)?|shut\s+up|silence|quiet|cancel|hold\s+on|pause|ruk\s+jao|bas\s+karo)\s*$", u):
            return IntentResponse(
                spoken_text="Stopped.",
                action_type="INTERRUPT",
                hud_alert="Playback stopped."
            )

        map_match = re.search(r"\b(?:in\s+map\s+search|search\s+in\s+map|search\s+on\s+map|search\s+map\s+for|find\s+on\s+map|find\s+in\s+map|show\s+on\s+map|show\s+in\s+map|locate\s+on\s+map|locate\s+in\s+map|map\s+search)\s+(.+)", u)
        if not map_match:
            map_match = re.search(r"\b(?:search|find|show|locate|where\s+is)\s+(?:for\s+)?(.+?)\s+(?:in|on)\s+(?:google\s+)?maps?\b", u)

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
            # Strip conversational lead-ins repeatedly
            prev_len = -1
            while len(clean) != prev_len:
                prev_len = len(clean)
                clean = re.sub(
                    r"^(?:i\s+(?:said|told|asked)(?:\s+(?:him|her|you|wrock))?\s+(?:to\s+)?|just\s+|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?|please\s+|i\s+want\s+(?:you\s+)?to\s+|wrock\s+|jarvis\s+)",
                    "", clean, flags=re.IGNORECASE
                ).strip()
                clean = re.sub(
                    r"^(?:search(?:\s+for|\s+on|\s+in)?|open|go\s+to|launch|find|locate|where\s+is|show)\s+",
                    "", clean, flags=re.IGNORECASE
                ).strip()
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

        # --- I-1. ON-SCREEN VISUAL AWARENESS & SCREEN INSPECTION ---
        elif any(phrase in u for phrase in [
            "look at my screen", "look at screen", "see my screen", "read my screen",
            "what's on my screen", "whats on my screen", "what is on my screen",
            "what's on the screen", "whats on the screen", "what is on the screen",
            "what is this error", "what's this error", "whats this error", "explain this error",
            "read this error", "check this error", "debug this error", "read the error",
            "summarize this page", "summarize this screen", "summarize the screen", "summarize page",
            "what window is open", "what window is this", "what window is currently open",
            "what code is open", "what code is currently open", "explain this code",
            "explain the diagram", "explain the diagram on screen",
            "look at this window", "inspect this window", "inspect screen", "inspect active window",
            "look at this", "see this"
        ]):
            target_mode = "full_screen" if any(k in u for k in ["full screen", "entire screen", "whole screen", "desktop"]) else "active_window"
            res = self.tool_registry.execute_tool("inspect_screen", {"user_query": utterance, "target": target_mode})
            tools_executed.append(res)
            spoken = res.output_message
            action_type = "SCREEN_INSPECT"

        # --- I-2. SPATIAL: INSPECT / LOCK / RADAR / ANCHOR ---
        elif any(w in u for w in ["inspect target", "analyze target", "scan this", "what is this target", "diagnostics", "who is that", "inspect"]):
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

        # --- J. GESTURE VOICE CONTROLS ---
        elif any(w in u for w in ["enable gesture", "enable gestures", "turn on gesture", "turn on gestures", "enable hand tracking", "start hand control", "activate gestures"]):
            res = self.tool_registry.execute_tool("toggle_os_gestures", {"enabled": True})
            tools_executed.append(res)
            spoken = "Hand tracking and OS gesture control enabled, Swastik."
            action_type = "GESTURE_TOGGLE"

        elif any(w in u for w in ["disable gesture", "disable gestures", "turn off gesture", "turn off gestures", "disable hand tracking", "stop hand control", "deactivate gestures"]):
            res = self.tool_registry.execute_tool("toggle_os_gestures", {"enabled": False})
            tools_executed.append(res)
            spoken = "Hand gesture control disabled. Operating in voice-only mode, Swastik."
            action_type = "GESTURE_TOGGLE"

        # --- K. REAL-TIME TIME, DATE & CHRONOLOGY ---
        elif any(w in u for w in ["what time is it", "what's the time", "whats the time", "current time", "tell me the time", "time kya hua", "kitne baje", "kya time ho"]):
            now = datetime.now()
            time_str = now.strftime("%I:%M %p").lstrip("0")
            spoken = f"It's {time_str}, Swastik."
            action_type = "CHAT"

        elif any(w in u for w in ["what day is it", "today's day", "whats the day", "what is today", "aaj kaun sa din"]):
            now = datetime.now()
            day_str = now.strftime("%A")
            spoken = f"Today is {day_str}, Swastik."
            action_type = "CHAT"

        elif any(w in u for w in ["what's the date", "whats the date", "today's date", "todays date", "what is the date", "current date", "aaj kaun si date", "aaj kya date"]):
            now = datetime.now()
            day_num = now.day
            suffix = "th" if 11 <= day_num <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day_num % 10, "th")
            date_str = now.strftime(f"%A, %B {day_num}{suffix}, %Y")
            spoken = f"Today is {date_str}, Swastik."
            action_type = "CHAT"

        # --- L. CREATOR & ORIGIN ---
        elif any(w in u for w in ["who made you", "who created you", "who built you", "tumhe kisne banaya", "who is your developer", "who is your creator"]):
            spoken = "You built me, Swastik. Designed and engineered right here in your command center to reset the world on command."
            action_type = "CHAT"

        # --- M. BILINGUAL & HINGLISH BANTER ---
        elif any(w in u for w in ["han bhai", "haan bhai", "haa bhai", "ha bhai", "sun bhai", "are bhai", "batao bhai"]):
            responses = [
                "Bolo Swastik bhai, kya hukum hai?",
                "Haan Swastik bhai, sun raha hoon. Bataiye kya karna hai.",
                "Hazir hoon Swastik bhai. All systems green. What's the plan?",
            ]
            spoken = random.choice(responses)
            action_type = "CHAT"

        elif any(w in u for w in ["kya hal hai", "kya haal hai", "kya chal raha hai", "kya haal", "sab theek", "sab badiya"]):
            spoken = "Sab first-class hai Swastik bhai. All systems green. What are we building today?"
            action_type = "CHAT"

        elif any(w in u for w in ["aur batao", "aur sunao", "aur kya chal raha"]):
            spoken = "Bas aapke next command ka intezaar hai Swastik bhai. Chrome, spatial map, system status, jo bolo."
            action_type = "CHAT"

        elif any(w in u for w in ["theek hai", "accha", "theek h", "thik hai", "sahi hai"]):
            spoken = "Confirmed Swastik bhai. Ready jab bhi aap kaho."
            action_type = "CHAT"

        elif any(w in u for w in ["shukriya", "dhanyawad", "bahut badhiya"]):
            spoken = "Hamesha hazir hoon Swastik bhai."
            action_type = "CHAT"

        # --- N. SCIENCE, TECH & QUANTUM REASONING (ANTIGRAVITY STYLE) ---
        elif any(w in u for w in ["quantum computing", "quantum computer", "what is quantum"]):
            spoken = "Quantum computing uses qubits in superposition and entanglement rather than classical bits. It evaluates massive solution spaces in parallel, cracking complex simulations in seconds."
            action_type = "CHAT"

        elif any(w in u for w in ["artificial intelligence", "what is ai", "explain ai"]):
            spoken = "Artificial intelligence is mathematical modeling of cognitive reasoning, neural architectures, and pattern synthesis at scale. It turns complex sensory entropy into precise autonomous action."
            action_type = "CHAT"

        elif any(w in u for w in ["black hole", "black holes", "event horizon"]):
            spoken = "A singularity of infinite density where gravitational curvature warps spacetime so severely that even photons cannot escape past its event horizon."
            action_type = "CHAT"

        elif any(w in u for w in ["tell me something cool", "interesting fact", "random fact", "science fact", "cool fact"]):
            cool_facts = [
                "Neutron stars are so dense that a single teaspoon of their material would weigh about six billion tons on Earth.",
                "Photons born in the core of the Sun take over one hundred thousand years to traverse its interior, but only eight minutes to reach your eyes.",
                "Time moves marginally faster at your head than at your feet because Earth's gravitational field is stronger closer to its center.",
                "DNA stores information with such extreme density that all the world's data could fit inside a single teaspoon of synthetic DNA."
            ]
            spoken = random.choice(cool_facts)
            action_type = "CHAT"

        # --- O. WITTY TECH JOKES & HIGH-OCTANE MOTIVATION ---
        elif any(w in u for w in ["tell me a joke", "tell a joke", "make me laugh", "joke sunao", "say something funny"]):
            jokes = [
                "Why do programmers prefer dark mode? Because light attracts bugs.",
                "There are 10 types of people in the world: those who understand binary, and those who don't.",
                "A SQL query walks into a bar, approaches two tables, and asks: Can I join you?",
                "Why did the neural network cross the road? To optimize the loss function on the other side."
            ]
            spoken = random.choice(jokes)
            action_type = "CHAT"

        elif any(w in u for w in ["motivate me", "give me motivation", "i feel tired", "i am tired", "thak gaya", "feeling down"]):
            quotes = [
                "We don't stop when we're tired, Swastik. We stop when the mission is accomplished. Let's finish what we started.",
                "Focus on the signal, ignore the noise, Swastik. The vision you're building is worth every hour. Let's make it count.",
                "Take a breath and reset your state, Swastik. Great systems aren't built in comfort, they're forged through persistence."
            ]
            spoken = random.choice(quotes)
            action_type = "CHAT"

        # --- P. TIME-OF-DAY GREETINGS ---
        elif any(w in u for w in ["good morning", "subah ho gayi"]):
            spoken = "Good morning, Swastik. Systems are primed and ready for today's objectives."
            action_type = "CHAT"

        elif any(w in u for w in ["good afternoon"]):
            spoken = "Good afternoon, Swastik. Standing by for your directives."
            action_type = "CHAT"

        elif any(w in u for w in ["good evening"]):
            spoken = "Good evening, Swastik. All telemetry channels active. What's on the agenda?"
            action_type = "CHAT"

        elif any(w in u for w in ["good night", "shubh ratri", "sleep well"]):
            spoken = "Good night, Swastik. Powering down non-essential loops. Rest up."
            action_type = "CHAT"

        # --- Q. CONVERSATIONAL & CORE LIFECYCLE ---
        elif any(w in u for w in ["wake up wrock", "wake up rock", "wake up", "wrock online"]):
            spoken = "Yes, I am online. What's your command, Swastik?"
            action_type = "WAKE_UP"

        elif any(w in u for w in [
            "how are you", "how are u", "how r u", "how do you do", "how are you doing",
            "how's it going", "hows it going", "kese ho", "kaise ho", "kemon acho",
            "are you okay", "you okay", "are you online", "are you there"
        ]):
            spoken = "All systems online and ready, Swastik. What would you like to do?"
            action_type = "CHAT"

        elif any(w in u for w in ["say something", "kuch bolo", "speak", "talk to me"]):
            spoken = "Standing by for input, Swastik."
            action_type = "CHAT"

        elif any(w in u for w in ["who are you", "what is your name", "what is wrock", "world reset", "wrold reset", "reset on command", "kaun ho", "tum kaun"]):
            spoken = "I am Wrock: World Reset On Command. Your autonomous spatial-AI assistant, Swastik."
            action_type = "CHAT"

        elif any(w in u for w in ["thank you", "thanks"]):
            spoken = "Always at your service, Swastik."
            action_type = "CHAT"

        elif any(w in u for w in ["good job", "well done", "nice work", "awesome", "great", "smart"]):
            spoken = "Thank you, Swastik. Always ready to deliver."
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
            # Context-Aware Antigravity Conversational Fallback
            if any(q in u for q in ["how", "why"]):
                spoken = "Point me to the specific target or process, Swastik, and I will break it down for you."
            elif any(q in u for q in ["can you", "could you", "would you"]):
                spoken = "Without question. State the directive and consider it done, Swastik."
            elif any(w in u for w in ["yes", "yeah", "yep", "sure", "ok", "okay"]):
                spoken = "Confirmed, Swastik. What directive would you like executed?"
            elif any(w in u for w in ["no", "nope", "cancel", "nevermind"]):
                spoken = "Standing down, Swastik."
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

    async def _route_gemini(
        self,
        utterance: str,
        perception_state: Dict[str, Any],
        target_candidate: Optional[str]
    ) -> IntentResponse:
        system_prompt = self.build_multimodal_system_prompt(perception_state)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_api_key}"

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": utterance}]
                }
            ],
            "generationConfig": {
                "temperature": 0.35,
                "maxOutputTokens": 150
            }
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        raw_spoken = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        clean_spoken = re.sub(r"[*#_`>~]", "", raw_spoken).strip()
                        clean_spoken = re.sub(r"\s+", " ", clean_spoken)
                        if clean_spoken:
                            self.memory.add_turn("assistant", clean_spoken)
                            return IntentResponse(
                                spoken_text=clean_spoken,
                                tool_results=[],
                                hud_alert=None,
                                target_entity_id=target_candidate,
                                action_type="CHAT"
                            )
        except Exception as e:
            logger.error(f"Gemini routing error: {e}. Falling back to deterministic engine.")

        return self._route_heuristic(utterance, target_candidate, perception_state)

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
