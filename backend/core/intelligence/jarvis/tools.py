from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import os
import sys
import time
import subprocess
import webbrowser
import urllib.parse
import re
import shutil
import logging
from ...perception.spatial.scene_graph import SpatialSceneGraph, ThreatLevel, EntityType
from ...perception.spatial.tactical_observer import TacticalObserver, CameraPerspectiveMode

logger = logging.getLogger("SpatialToolRegistry")

# Try importing PC automation dependencies
try:
    import pyautogui
    pyautogui.FAILSAFE = False
except ImportError:
    pyautogui = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None


@dataclass
class ToolCallResult:
    tool_name: str
    arguments: Dict[str, Any]
    success: bool
    output_message: str
    affected_entity_ids: List[str]
    new_camera_mode: Optional[str] = None
    telemetry_payload: Optional[Dict[str, Any]] = None
    action_type: Optional[str] = None
    pov_entity_id: Optional[str] = None


class SpatialToolRegistry:
    """
    Standardized function-calling schemas and execution runtime for
    both 3D Spatial/God's Eye manipulations and Windows PC automation in Project WROCK.
    """

    def __init__(self, scene_graph: SpatialSceneGraph, observer: TacticalObserver):
        self.scene_graph = scene_graph
        self.observer = observer
        self.active_pov_entity_id: Optional[str] = "DRONE-STARK-01"
        self.map_zoom_level: float = 1.0
        self.map_pan_offset: List[float] = [0.0, 0.0]

    @staticmethod
    def _open_url_in_chrome(url: str) -> bool:
        try:
            chrome_paths = [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            ]
            for p in chrome_paths:
                if os.path.isfile(p):
                    subprocess.Popen([p, url])
                    return True
        except Exception as e:
            logger.debug(f"Direct Chrome launch fallback: {e}")
        return webbrowser.open(url)

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns JSON Schema definitions formatted for LLM Function Calling."""
        return [
            {
                "name": "set_camera_view",
                "description": "Switches the 3D spatial camera perspective. Use GODS_EYE for satellite top-down map, ORBITAL for angled tactical view, TACTICAL_DRONE for drone follow, or HOLOGRAM for floating workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["GODS_EYE", "ORBITAL", "TACTICAL_DRONE", "HOLOGRAM"],
                            "description": "The camera perspective mode to engage."
                        }
                    },
                    "required": ["mode"]
                }
            },
            {
                "name": "watch_entity_pov",
                "description": "Switches to God's Eye tactical satellite map and opens a live reconnaissance POV camera feed watching a specific drone, satellite, or target.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_id": {
                            "type": "string",
                            "description": "ID of entity to watch POV from (e.g., 'DRONE-STARK-01', 'UAV-BOGEY-99', 'SAT-KH11-EDITH')."
                        }
                    },
                    "required": ["target_id"]
                }
            },
            {
                "name": "zoom_gods_eye_map",
                "description": "Zooms in or out of the God's Eye tactical satellite map using optical hand pinch or commands.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zoom_factor": {
                            "type": "number",
                            "description": "Zoom multiplier (e.g., 0.8 for zoom out, 1.25 for zoom in)."
                        }
                    },
                    "required": ["zoom_factor"]
                }
            },
            {
                "name": "inspect_entity",
                "description": "Brings up in-depth telemetry, diagnostics, and spatial overlay for a specific entity ID or deictically targeted object.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_id": {
                            "type": "string",
                            "description": "The exact ID of the entity (e.g., 'DRONE-STARK-01', 'UAV-BOGEY-99') or 'SELECTED'."
                        }
                    },
                    "required": ["target_id"]
                }
            },
            {
                "name": "lock_target",
                "description": "Engages targeting reticle and continuous tracking lock on an aerial, orbital, or ground entity.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_id": {
                            "type": "string",
                            "description": "The ID of the target to lock onto."
                        }
                    },
                    "required": ["target_id"]
                }
            },
            {
                "name": "execute_tactical_scan",
                "description": "Dispatches an active radar/LiDAR sweep pulse across the sector to refresh telemetry and reveal hostile signatures.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "radius_km": {
                            "type": "number",
                            "description": "The scan radius in kilometers (default 25.0)."
                        }
                    }
                }
            },
            {
                "name": "deploy_spatial_anchor",
                "description": "Drops a 3D persistent spatial beacon / anchor at specified coordinates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "Label for the spatial anchor."},
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number"}
                    },
                    "required": ["label"]
                }
            },
            {
                "name": "pc_take_screenshot",
                "description": "Takes a full-resolution screenshot of the Windows desktop, saves it to Pictures, and opens it.",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "pc_change_volume",
                "description": "Adjusts Windows master volume (up, down, or mute).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["up", "down", "mute"],
                            "description": "Volume action to perform."
                        }
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "pc_system_status",
                "description": "Reads real-time CPU usage, RAM utilization, and battery status from the Windows machine.",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "pc_close_heavy_apps",
                "description": "Closes background or heavy applications and tabs to free up system memory.",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "pc_close_application",
                "description": "Terminates or turns off a designated application or browser by name (e.g. Chrome, Firefox, Edge, Spotify, Discord, Notepad, Calculator).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "Name of the application or browser to close (e.g. 'chrome', 'browser', 'spotify', 'notepad')."
                        }
                    },
                    "required": ["app_name"]
                }
            },
            {
                "name": "pc_lock_workstation",
                "description": "Immediately locks the Windows PC screen for privacy/security.",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "pc_launch_app",
                "description": "Launches a designated application or website (e.g. Chrome, YouTube, Cursor, Notepad, Calculator).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "Name of the app (e.g. 'chrome', 'youtube', 'cursor', 'notepad', 'calculator', 'browser')."
                        },
                        "query_or_url": {
                            "type": "string",
                            "description": "Optional search query or direct URL to open."
                        }
                    },
                    "required": ["app_name"]
                }
            },
            {
                "name": "pc_close_window",
                "description": "Closes the current active foreground window via Alt+F4.",
                "parameters": {"type": "object", "properties": {}}
            },
            {
                "name": "search_map_location",
                "description": "Searches for a location, city, or landmark. Aligns God's Eye satellite perspective and opens Google Maps recon in Chrome.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location_name": {
                            "type": "string",
                            "description": "Name of the place, city, or landmark to search (e.g. 'Tokyo', 'Paris', 'New York')."
                        }
                    },
                    "required": ["location_name"]
                }
            },
            {
                "name": "search_youtube",
                "description": "Searches and plays videos, songs, or topics on YouTube in Chrome.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query or video title for YouTube."
                        }
                    }
                }
            },
            {
                "name": "search_spotify",
                "description": "Searches and plays music, artists, albums, or playlists on Spotify.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Song title, artist, or playlist to search on Spotify."
                        }
                    }
                }
            },
            {
                "name": "open_chrome_or_search",
                "description": "Opens Google Chrome to a designated website (e.g. reddit, github, chatgpt, netflix, wikipedia) or executes a web search query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_or_url": {
                            "type": "string",
                            "description": "Target website name or search phrase."
                        }
                    }
                }
            }
        ]

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> ToolCallResult:
        logger.info(f"⚡ Executing Wrock Tool: {tool_name} with args {args}")

        # --- SPATIAL & GOD'S EYE / POV TOOLS ---
        if tool_name == "set_camera_view":
            mode_str = args.get("mode", "GODS_EYE").upper()
            try:
                mode = CameraPerspectiveMode(mode_str)
            except ValueError:
                mode = CameraPerspectiveMode.GODS_EYE

            self.observer.set_mode(mode)
            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=f"Perspective shifted to {mode.value}. God's Eye satellite grid aligned.",
                affected_entity_ids=[],
                new_camera_mode=mode.value,
                action_type="CAMERA_SWITCH"
            )

        elif tool_name == "watch_entity_pov":
            target_id = args.get("target_id", "DRONE-STARK-01")
            entity = self.scene_graph.get_entity(target_id)
            if not entity:
                # Default to primary drone if target doesn't exist
                target_id = "DRONE-STARK-01"
                entity = self.scene_graph.get_entity(target_id)

            self.active_pov_entity_id = target_id
            self.observer.set_mode(CameraPerspectiveMode.GODS_EYE)
            entity_name = entity.name if entity else target_id

            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=f"Streaming live tactical POV reconnaissance from {entity_name} [{target_id}] on God's Eye map.",
                affected_entity_ids=[target_id],
                new_camera_mode="GODS_EYE",
                pov_entity_id=target_id,
                action_type="POV_ENGAGED"
            )

        elif tool_name == "zoom_gods_eye_map":
            factor = float(args.get("zoom_factor", 1.2))
            self.map_zoom_level = max(0.2, min(5.0, self.map_zoom_level * factor))
            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=f"God's Eye satellite zoom updated to {self.map_zoom_level:.2f}x.",
                affected_entity_ids=[],
                telemetry_payload={"zoom_level": self.map_zoom_level},
                action_type="MAP_ZOOM"
            )

        elif tool_name == "inspect_entity":
            target_id = args.get("target_id", "")
            entity = self.scene_graph.get_entity(target_id)
            if not entity:
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=False,
                    output_message=f"Target '{target_id}' not found in active scene.",
                    affected_entity_ids=[]
                )
            self.scene_graph.inspect_entity(target_id, True)
            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=f"Telemetry feed for {entity.name} [{entity.id}] expanded on primary HUD.",
                affected_entity_ids=[target_id],
                telemetry_payload=entity.telemetry,
                action_type="INSPECT"
            )

        elif tool_name == "lock_target":
            target_id = args.get("target_id", "UAV-BOGEY-99")
            entity = self.scene_graph.get_entity(target_id)
            if not entity:
                target_id = "UAV-BOGEY-99"
                entity = self.scene_graph.get_entity(target_id)

            self.scene_graph.lock_entity(target_id, True)
            name = entity.name if entity else target_id
            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=f"Target lock confirmed on {name} [{target_id}]. Tracking reticle active.",
                affected_entity_ids=[target_id],
                action_type="TARGET_LOCKED"
            )

        elif tool_name == "execute_tactical_scan":
            radius = args.get("radius_km", 25.0)
            summary = self.scene_graph.get_scene_summary()
            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=f"Sector radar sweep complete across {radius} km. Detected {summary['total_entities']} signatures with {summary['threats_count']} threat indicators.",
                affected_entity_ids=summary["entity_ids"],
                action_type="RADAR_SWEEP"
            )

        elif tool_name == "deploy_spatial_anchor":
            label = args.get("label", "Tactical Waypoint")
            x = args.get("x", 2.0)
            y = args.get("y", 0.0)
            z = args.get("z", -1.5)
            anchor_id = f"ANCHOR-{label.replace(' ', '_').upper()}"
            anchor = self.scene_graph.add_spatial_anchor(anchor_id, label, (x, y, z))
            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=f"Spatial beacon '{label}' deployed on tactical map.",
                affected_entity_ids=[],
                telemetry_payload=anchor,
                action_type="SPATIAL_ANCHOR"
            )

        # --- PC AUTOMATION TOOLS ---
        elif tool_name == "pc_take_screenshot":
            try:
                pics_dir = os.path.join(os.path.expanduser("~"), "Pictures", "WrockScreenshots")
                os.makedirs(pics_dir, exist_ok=True)
                filename = os.path.join(pics_dir, f"screenshot_{int(time.time())}.png")

                saved = False
                if pyautogui:
                    try:
                        pyautogui.screenshot(filename)
                        saved = True
                    except Exception:
                        pass
                if not saved and ImageGrab:
                    try:
                        img = ImageGrab.grab()
                        img.save(filename)
                        saved = True
                    except Exception:
                        pass
                if not saved and sys.platform == "win32":
                    try:
                        ps_script = f"Add-Type -AssemblyName System.Windows.Forms,System.Drawing; $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; $g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); $bmp.Save('{filename}'); $g.Dispose(); $bmp.Dispose()"
                        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=False, timeout=5)
                        saved = os.path.exists(filename) and os.path.getsize(filename) > 0
                    except Exception:
                        pass

                if not saved:
                    return ToolCallResult(
                        tool_name=tool_name,
                        arguments=args,
                        success=False,
                        output_message="Screen capture libraries unavailable or desktop locked.",
                        affected_entity_ids=[]
                    )

                if sys.platform == "win32":
                    try:
                        os.startfile(filename)
                    except Exception:
                        pass

                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=True,
                    output_message=f"Screenshot saved to {os.path.basename(filename)}.",
                    affected_entity_ids=[],
                    telemetry_payload={"screenshot_path": filename},
                    action_type="SCREENSHOT"
                )
            except Exception as e:
                logger.error(f"Screenshot error: {e}")
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=False,
                    output_message=f"Could not take screenshot: {e}",
                    affected_entity_ids=[]
                )

        elif tool_name == "pc_change_volume":
            action = args.get("action", "up").lower()
            try:
                if pyautogui:
                    if action == "up":
                        for _ in range(5):
                            pyautogui.press("volumeup")
                        msg = "Volume increased."
                    elif action == "down":
                        for _ in range(5):
                            pyautogui.press("volumedown")
                        msg = "Volume decreased."
                    elif action == "mute":
                        pyautogui.press("volumemute")
                        msg = "Audio muted."
                    else:
                        msg = "Volume adjusted."
                else:
                    # Windows virtual key fallback
                    if sys.platform == "win32":
                        import ctypes
                        VK_VOLUME_MUTE = 0xAD
                        VK_VOLUME_DOWN = 0xAE
                        VK_VOLUME_UP = 0xAF
                        vk = VK_VOLUME_UP if action == "up" else (VK_VOLUME_DOWN if action == "down" else VK_VOLUME_MUTE)
                        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                        msg = f"Volume {action} executed."
                    else:
                        msg = "Volume adjustment unsupported on this OS."

                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=True,
                    output_message=msg,
                    affected_entity_ids=[],
                    action_type="VOLUME"
                )
            except Exception as e:
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=False,
                    output_message=f"Failed to adjust volume: {e}",
                    affected_entity_ids=[]
                )

        elif tool_name == "pc_system_status":
            try:
                if psutil:
                    cpu = psutil.cpu_percent(interval=0.15)
                    vm = psutil.virtual_memory()
                    ram_pct = vm.percent
                    used_gb = round(vm.used / (1024**3), 1)
                    total_gb = round(vm.total / (1024**3), 1)

                    # Battery status
                    battery_str = ""
                    if hasattr(psutil, "sensors_battery"):
                        bat = psutil.sensors_battery()
                        if bat:
                            plug_state = "plugged in" if bat.power_plugged else "on battery"
                            battery_str = f", Battery is at {bat.percent}% ({plug_state})"

                    # GPU and GPU Temperature
                    gpu_str = ""
                    try:
                        res = subprocess.run(
                            ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=1.0
                        )
                        if res.returncode == 0 and res.stdout.strip():
                            parts = [p.strip() for p in res.stdout.strip().split(",")]
                            if len(parts) >= 2:
                                gpu_str = f", GPU load is {parts[0]}% at {parts[1]}°C"
                    except Exception:
                        pass

                    # Detect top active user applications (excluding core Windows daemons)
                    app_ram = {}
                    for p in psutil.process_iter(['name', 'memory_percent']):
                        try:
                            n = p.info['name']
                            if not n:
                                continue
                            n_lower = n.lower()
                            if any(k in n_lower for k in ["svchost", "system", "registry", "smss", "csrss", "services", "lsass", "conhost", "explorer"]):
                                continue
                            app_ram[n] = app_ram.get(n, 0) + (p.info['memory_percent'] or 0)
                        except Exception:
                            pass

                    top_apps = sorted(app_ram.items(), key=lambda x: x[1], reverse=True)[:3]
                    app_names = []
                    friendly_names = {
                        "chrome.exe": "Google Chrome",
                        "msedge.exe": "Microsoft Edge",
                        "code.exe": "VS Code",
                        "cursor.exe": "Cursor IDE",
                        "antigravity ide.exe": "Antigravity IDE",
                        "discord.exe": "Discord",
                        "spotify.exe": "Spotify",
                        "python.exe": "Python tasks",
                        "wispr flow.exe": "Wispr Flow",
                        "steam.exe": "Steam"
                    }
                    for app_proc, ram_usage in top_apps:
                        fname = friendly_names.get(app_proc.lower(), app_proc.replace(".exe", "").title())
                        if fname not in app_names:
                            app_names.append(fname)

                    apps_summary = f"You are currently running {', '.join(app_names)}." if app_names else ""
                    follow_up = " Would you like me to close heavy background processes to free up memory?"

                    msg = (
                        f"Laptop Status: CPU is at {cpu}%, RAM is at {ram_pct}% ({used_gb} of {total_gb} GB used)"
                        f"{battery_str}{gpu_str}. {apps_summary}{follow_up}"
                    )

                    return ToolCallResult(
                        tool_name=tool_name,
                        arguments=args,
                        success=True,
                        output_message=msg,
                        affected_entity_ids=[],
                        telemetry_payload={
                            "cpu": cpu,
                            "ram": ram_pct,
                            "used_gb": used_gb,
                            "total_gb": total_gb,
                            "top_apps": app_names
                        },
                        action_type="SYSTEM_STATUS"
                    )
                else:
                    return ToolCallResult(
                        tool_name=tool_name,
                        arguments=args,
                        success=True,
                        output_message="System operational. psutil diagnostics unavailable.",
                        affected_entity_ids=[]
                    )
            except Exception as e:
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=False,
                    output_message=f"System check error: {e}",
                    affected_entity_ids=[]
                )

        elif tool_name == "pc_close_heavy_apps":
            try:
                closed_count = 0
                closed_names = []
                target_names = ["msedge.exe", "discord.exe", "spotify.exe", "notepad.exe", "calc.exe"]
                for p in psutil.process_iter(['name', 'pid', 'cmdline']):
                    try:
                        n = p.info['name']
                        if not n:
                            continue
                        n_lower = n.lower()
                        if "antigravity" in n_lower or "uvicorn" in str(p.info.get('cmdline', [])):
                            continue
                        if n_lower in target_names:
                            p.terminate()
                            closed_count += 1
                            clean_n = n.replace(".exe", "").title()
                            if clean_n not in closed_names:
                                closed_names.append(clean_n)
                    except Exception:
                        pass

                msg = f"Closed background applications ({', '.join(closed_names) if closed_names else 'idle background tasks'}). Memory freed, Swastik."
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=True,
                    output_message=msg,
                    affected_entity_ids=[],
                    action_type="PROCESSES_CLOSED"
                )
            except Exception as e:
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=False,
                    output_message=f"Process cleanup notice: {e}",
                    affected_entity_ids=[]
                )

        elif tool_name == "pc_close_application":
            raw_target = str(args.get("app_name", "")).strip().lower()
            if not raw_target:
                raw_target = "chrome"

            # Clean prefixes/suffixes
            clean_target = re.sub(r"^(?:my|the)\s+", "", raw_target).strip()
            clean_target = re.sub(r"\s+(?:browser|app|application)$", "", clean_target).strip()

            exe_mapping = {
                "chrome": ["chrome.exe"],
                "google chrome": ["chrome.exe"],
                "browser": ["chrome.exe", "msedge.exe", "firefox.exe"],
                "edge": ["msedge.exe"],
                "microsoft edge": ["msedge.exe"],
                "firefox": ["firefox.exe"],
                "spotify": ["spotify.exe"],
                "discord": ["discord.exe"],
                "notepad": ["notepad.exe"],
                "calc": ["calc.exe", "calculatorapp.exe"],
                "calculator": ["calc.exe", "calculatorapp.exe"],
                "cursor": ["cursor.exe"],
                "steam": ["steam.exe"],
                "slack": ["slack.exe"],
            }

            target_exes = exe_mapping.get(clean_target, [f"{clean_target}.exe", clean_target])
            display_name = clean_target.title()
            if "chrome" in clean_target:
                display_name = "Google Chrome"

            closed_count = 0
            protected = ["python.exe", "uvicorn.exe", "node.exe", "explorer.exe", "antigravity"]

            for p in psutil.process_iter(['name', 'pid', 'cmdline']):
                try:
                    pname = p.info['name']
                    if not pname:
                        continue
                    pname_lower = pname.lower()

                    if any(prot in pname_lower for prot in protected) or "uvicorn" in str(p.info.get('cmdline', [])):
                        continue

                    matched = False
                    for t_exe in target_exes:
                        if t_exe.lower() in pname_lower or pname_lower == t_exe.lower():
                            matched = True
                            break

                    if matched:
                        p.terminate()
                        closed_count += 1
                except Exception:
                    pass

            # If Windows and closed_count > 0, ensure forceful taskkill for clean termination
            if sys.platform == "win32" and closed_count > 0:
                for t_exe in target_exes:
                    if t_exe.endswith(".exe"):
                        try:
                            import subprocess
                            subprocess.run(["taskkill", "/F", "/IM", t_exe], capture_output=True, timeout=2)
                        except Exception:
                            pass

            if closed_count > 0:
                msg = f"{display_name} has been closed, Swastik."
            else:
                msg = f"{display_name} is not currently running, Swastik."

            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=msg,
                affected_entity_ids=[],
                action_type="PROCESS_CLOSED"
            )

        elif tool_name == "pc_lock_workstation":
            try:
                if sys.platform == "win32":
                    import ctypes
                    ctypes.windll.user32.LockWorkStation()
                    return ToolCallResult(
                        tool_name=tool_name,
                        arguments=args,
                        success=True,
                        output_message="Workstation locked.",
                        affected_entity_ids=[],
                        action_type="LOCK_PC"
                    )
                else:
                    return ToolCallResult(
                        tool_name=tool_name,
                        arguments=args,
                        success=False,
                        output_message="Lock PC supported on Windows platform.",
                        affected_entity_ids=[]
                    )
            except Exception as e:
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=False,
                    output_message=f"Failed to lock PC: {e}",
                    affected_entity_ids=[]
                )

        elif tool_name == "search_map_location":
            location = args.get("location_name", "").strip()
            is_generic = (not location) or location.lower() in [
                "google maps", "google map", "maps", "map", "the map", "the maps",
                "the google maps", "tactical coordinates", "coordinates"
            ]

            if is_generic:
                maps_url = "https://maps.google.com"
                msg = "Opening Google Maps on Chrome, Swastik."
            else:
                maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(location)}"
                msg = f"Locating '{location}' on map. Coordinates locked on God's Eye satellite and Google Maps launched."

            self._open_url_in_chrome(maps_url)

            # Switch 3D tactical camera to God's Eye satellite perspective
            self.observer.set_mode(CameraPerspectiveMode.GODS_EYE)

            if not is_generic:
                # Deploy persistent spatial anchor on tactical grid
                try:
                    anchor_id = f"LOC-{int(time.time()) % 10000}"
                    self.scene_graph.add_entity(
                        id=anchor_id,
                        name=f"LOC: {location.upper()}",
                        entity_type=EntityType.WAYPOINT,
                        position=[0.0, 0.0, 0.0],
                        threat_level=ThreatLevel.FRIENDLY,
                        telemetry={"location_name": location, "maps_url": maps_url}
                    )
                except Exception as e:
                    logger.debug(f"Anchor addition error: {e}")

            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=msg,
                affected_entity_ids=[],
                new_camera_mode="GODS_EYE",
                telemetry_payload={"location": location or "Google Maps", "maps_url": maps_url},
                action_type="MAP_SEARCH"
            )

        elif tool_name == "search_youtube":
            query = args.get("query", "").strip()
            if query:
                url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
                msg = f"Searching YouTube for '{query}'."
            else:
                url = "https://www.youtube.com"
                msg = "Opening YouTube."
            self._open_url_in_chrome(url)
            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=msg,
                affected_entity_ids=[],
                action_type="YOUTUBE_SEARCH"
            )

        elif tool_name == "search_spotify":
            query = args.get("query", "").strip()
            if query:
                url = f"https://open.spotify.com/search/{urllib.parse.quote_plus(query)}"
                msg = f"Searching Spotify for '{query}'."
                try:
                    subprocess.Popen(["cmd", "/c", "start", f"spotify:search:{urllib.parse.quote(query)}"])
                except Exception:
                    pass
            else:
                url = "https://open.spotify.com"
                msg = "Opening Spotify."
                try:
                    subprocess.Popen(["cmd", "/c", "start", "spotify:"])
                except Exception:
                    pass

            self._open_url_in_chrome(url)
            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=msg,
                affected_entity_ids=[],
                action_type="SPOTIFY_SEARCH"
            )

        elif tool_name == "open_chrome_or_search":
            target = args.get("query_or_url", "").strip()
            known_sites = {
                "reddit": "https://www.reddit.com",
                "github": "https://github.com",
                "chatgpt": "https://chatgpt.com",
                "openai": "https://chatgpt.com",
                "twitter": "https://x.com",
                "x": "https://x.com",
                "netflix": "https://www.netflix.com",
                "amazon": "https://www.amazon.com",
                "wikipedia": "https://www.wikipedia.org",
                "wiki": "https://www.wikipedia.org",
                "gmail": "https://mail.google.com",
                "mail": "https://mail.google.com",
                "google": "https://www.google.com",
                "youtube": "https://www.youtube.com",
                "spotify": "https://open.spotify.com",
                "linkedin": "https://www.linkedin.com",
                "instagram": "https://www.instagram.com",
                "facebook": "https://www.facebook.com",
                "discord": "https://discord.com/app",
                "twitch": "https://www.twitch.tv",
                "stackoverflow": "https://stackoverflow.com",
                "huggingface": "https://huggingface.co",
                "maps": "https://maps.google.com",
                "googlemaps": "https://maps.google.com",
                "googlemap": "https://maps.google.com",
                "map": "https://maps.google.com",
            }
            clean_key = target.lower().replace(" ", "").replace(".com", "")
            if clean_key in known_sites:
                url = known_sites[clean_key]
                msg = f"Opening {target.capitalize()} on Chrome."
            elif any(target.lower().endswith(ext) or ext + "/" in target.lower() for ext in [".com", ".org", ".net", ".io", ".ai", ".co", ".gov", ".edu", ".app", ".dev"]) or target.startswith("http"):
                url = target if target.startswith("http") else f"https://{target}"
                msg = f"Opening {url} on Chrome."
            elif target:
                url = f"https://www.google.com/search?q={urllib.parse.quote_plus(target)}"
                msg = f"Searching Google for '{target}' on Chrome."
            else:
                url = "https://www.google.com"
                msg = "Opening Google Chrome."

            self._open_url_in_chrome(url)
            return ToolCallResult(
                tool_name=tool_name,
                arguments=args,
                success=True,
                output_message=msg,
                affected_entity_ids=[],
                action_type="CHROME_OPEN"
            )

        elif tool_name == "pc_launch_app":
            app = args.get("app_name", "").lower().strip()
            query = args.get("query_or_url", "")
            try:
                if "spotify" in app:
                    return self.execute_tool("search_spotify", {"query": query})
                elif "map" in app:
                    return self.execute_tool("search_map_location", {"location_name": query or "current"})
                elif "youtube" in app:
                    return self.execute_tool("search_youtube", {"query": query})
                elif "chrome" in app or "browser" in app or "google" in app:
                    return self.execute_tool("open_chrome_or_search", {"query_or_url": query})
                elif "cursor" in app:
                    exe = shutil.which("cursor") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "cursor", "Cursor.exe")
                    if os.path.isfile(exe):
                        subprocess.Popen([exe])
                        msg = "Cursor IDE launched."
                    else:
                        msg = "Cursor executable not found on path."
                elif "notepad" in app:
                    subprocess.Popen(["notepad.exe"])
                    msg = "Notepad launched."
                elif "calc" in app:
                    subprocess.Popen(["calc.exe"])
                    msg = "Calculator launched."
                elif "terminal" in app or "cmd" in app or "powershell" in app:
                    subprocess.Popen(["powershell.exe"])
                    msg = "Terminal launched."
                elif "explorer" in app or "files" in app or "my computer" in app:
                    subprocess.Popen(["explorer.exe"])
                    msg = "File Explorer opened."
                else:
                    return self.execute_tool("open_chrome_or_search", {"query_or_url": app if not query else f"{app} {query}"})

                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=True,
                    output_message=msg,
                    affected_entity_ids=[],
                    action_type="APP_LAUNCHED"
                )
            except Exception as e:
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=False,
                    output_message=f"Failed to launch {app}: {e}",
                    affected_entity_ids=[]
                )

        elif tool_name == "pc_close_window":
            try:
                if pyautogui:
                    pyautogui.hotkey("alt", "f4")
                    return ToolCallResult(
                        tool_name=tool_name,
                        arguments=args,
                        success=True,
                        output_message="Window closed.",
                        affected_entity_ids=[],
                        action_type="CLOSE_WINDOW"
                    )
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=False,
                    output_message="Window control unavailable.",
                    affected_entity_ids=[]
                )
            except Exception as e:
                return ToolCallResult(
                    tool_name=tool_name,
                    arguments=args,
                    success=False,
                    output_message=f"Close window error: {e}",
                    affected_entity_ids=[]
                )

        return ToolCallResult(
            tool_name=tool_name,
            arguments=args,
            success=False,
            output_message=f"Unknown command/tool '{tool_name}'.",
            affected_entity_ids=[]
        )
