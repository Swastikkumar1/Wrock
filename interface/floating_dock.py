"""
PROJECT WROCK: Floating Middle-Bottom Holographic Arc-Reactor Dock
===================================================================
A standalone, always-on-top, frameless desktop overlay widget that stays
floating at the middle-bottom of the Windows screen.

Features:
- Frameless (overrideredirect), Always-on-Top (topmost), 100% transparent cutout background
- Animated 60FPS Arc-Reactor AI Core with rotating coils & state-reactive glowing core
- Live Dynamic Audio Equalizer visualizer
- Conversational status pill (SLEEPING, LISTENING, THINKING, SPEAKING)
- Live dialogue ticker showing User Command and Wrock's Response
- Interactive command input field (Type & Enter or click SEND)
- Quick Action buttons: 🗺️ 3D Map, 📸 Screenshot, 🔊 Vol+, 🔉 Vol-, 🔒 Lock PC
- Draggable to any position on screen
- Double-click Arc Reactor to toggle between Minimalist Floating Orb & Full Dock
- Real-time Bidirectional WebSocket & REST link to FastAPI Backend (ws://127.0.0.1:8000/ws/spatial)
"""

import sys
import os
import math
import time
import queue
import random
import logging
import threading
import asyncio
import webbrowser
import tkinter as tk
from tkinter import font as tkfont
from typing import Dict, Any, Optional

try:
    import websockets
    import json
except ImportError:
    websockets = None
    import json

try:
    import httpx
except ImportError:
    httpx = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [FLOATING-DOCK] %(message)s")
log = logging.getLogger("FloatingDock")

# Visual Palette (Matches Stark-AI / Wrock Holographic Cyber Theme)
COLOR_TRANSPARENT = "#05070a"        # OS Transparent Key
COLOR_BG_CARD = "#081422"            # Dark glass container
COLOR_BORDER = "#00e5ff"             # Glowing Cyan
COLOR_BORDER_SUBTLE = "#005577"
COLOR_CYAN = "#00e5ff"
COLOR_CYAN_GLOW = "#33eeff"
COLOR_AMBER = "#ffb300"
COLOR_EMERALD = "#00e676"
COLOR_CRIMSON = "#ff1744"
COLOR_TEXT_PRIMARY = "#e0f7fa"
COLOR_TEXT_MUTED = "#80cbc4"
COLOR_INPUT_BG = "#040b13"


class FloatingArcReactorDock:
    def __init__(self, backend_url: str = "http://127.0.0.1:8000", ws_url: str = "ws://127.0.0.1:8000/ws/spatial"):
        self.backend_url = backend_url
        self.ws_url = ws_url
        self.msg_queue: queue.Queue = queue.Queue()
        self.running = True

        # State Variables
        self.state = "SLEEPING"       # SLEEPING, LISTENING, THINKING, SPEAKING
        self.user_text = 'Say "Wake up Wrock" or type below (e.g., "take screenshot", "volume up")...'
        self.wrock_text = '"Standing by for your command, Swastik."'
        self.anim_step = 0
        self.is_compact = False       # True when collapsed into mini Arc Orb
        self.is_connected = False
        self.audio_level = 0.0

        # Drag tracking
        self._drag_data = {"x": 0, "y": 0}

        # Root Window Initialization
        self.root = tk.Tk()
        self.root.title("Wrock Arc-Reactor Dock")
        self.root.overrideredirect(True)      # Frameless
        self.root.attributes("-topmost", True)  # Always stay on top of all windows

        # Transparent Cutout Setup (Native Windows DWM Keying)
        self.root.config(bg=COLOR_TRANSPARENT)
        if sys.platform == "win32":
            self.root.attributes("-transparentcolor", COLOR_TRANSPARENT)
        elif sys.platform == "darwin":
            self.root.attributes("-transparent", True)

        # Standard & Compact Dimensions
        self.full_w, self.full_h = 980, 132
        self.mini_w, self.mini_h = 88, 88

        # Calculate Middle-Bottom Screen Position (above taskbar)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.curr_x = (sw - self.full_w) // 2
        self.curr_y = sh - self.full_h - 48    # ~48px above standard Windows taskbar
        self.root.geometry(f"{self.full_w}x{self.full_h}+{self.curr_x}+{self.curr_y}")

        # Fonts
        self.font_title = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.font_badge = tkfont.Font(family="Consolas", size=9, weight="bold")
        self.font_dialogue = tkfont.Font(family="Segoe UI", size=9)
        self.font_btn = tkfont.Font(family="Segoe UI", size=8, weight="bold")

        # Main Rendering Canvas (handles holographic background, animated reactor & equalizer)
        self.canvas = tk.Canvas(
            self.root,
            width=self.full_w,
            height=self.full_h,
            bg=COLOR_TRANSPARENT,
            highlightthickness=0,
            cursor="hand2"
        )
        self.canvas.pack(fill="both", expand=True)

        # Interactive Controls Container Overlay
        self._build_interactive_ui()

        # Mouse Draggable Bindings
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<Double-Button-1>", self._toggle_compact_mode)

        # Keyboard Bindings
        self.root.bind("<Escape>", lambda e: self._toggle_compact_mode())

        # Start Background WebSocket Thread
        self.ws_thread = threading.Thread(target=self._run_network_loop, daemon=True)
        self.ws_thread.start()

        # Start UI Loops
        self._poll_queue()
        self._animate_loop()

    def _build_interactive_ui(self):
        """Build entry box, send button, and quick-action buttons placed inside the canvas."""
        # 1. Command Entry Box (Left = 115, Width = 590, Top = 86)
        self.input_frame = tk.Frame(self.canvas, bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER_SUBTLE, highlightthickness=1)
        
        self.cmd_entry = tk.Entry(
            self.input_frame,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_CYAN,
            font=self.font_dialogue,
            relief="flat",
            bd=4
        )
        self.cmd_entry.pack(side="left", fill="both", expand=True, padx=4, pady=2)
        self.cmd_entry.bind("<Return>", lambda e: self._send_user_command())
        self.cmd_entry.insert(0, "")

        self.btn_send = tk.Button(
            self.input_frame,
            text="SEND ⚡",
            font=self.font_btn,
            bg="#006064",
            fg="#e0f7fa",
            activebackground=COLOR_CYAN,
            activeforeground="#000000",
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._send_user_command
        )
        self.btn_send.pack(side="right", padx=2, pady=2)

        self.canvas.create_window(115, 88, anchor="nw", window=self.input_frame, width=585, height=32, tags="ui_controls")

        # 2. Quick Action Buttons Container (Right Side: 715 to 965)
        self.actions_frame = tk.Frame(self.canvas, bg=COLOR_BG_CARD)

        def make_action_btn(parent, text, cmd_action, bg="#0d2538", fg=COLOR_CYAN):
            return tk.Button(
                parent,
                text=text,
                font=self.font_btn,
                bg=bg,
                fg=fg,
                activebackground=COLOR_CYAN,
                activeforeground="#000",
                relief="flat",
                bd=1,
                padx=6,
                pady=2,
                cursor="hand2",
                command=cmd_action
            )

        # Row 1 of Quick Actions
        r1 = tk.Frame(self.actions_frame, bg=COLOR_BG_CARD)
        r1.pack(fill="x", pady=2)
        make_action_btn(r1, "⚡ WAKE", self._wake_up_toggle, bg="#332200", fg=COLOR_AMBER).pack(side="left", padx=2)
        make_action_btn(r1, "🗺️ 3D MAP", self._open_3d_map, bg="#003847", fg=COLOR_CYAN).pack(side="left", padx=2)
        make_action_btn(r1, "📸 SNAP", lambda: self._execute_command_text("take screenshot")).pack(side="left", padx=2)
        make_action_btn(r1, "✕", self._minimize_to_mini, bg="#330011", fg=COLOR_CRIMSON).pack(side="left", padx=2)

        # Row 2 of Quick Actions
        r2 = tk.Frame(self.actions_frame, bg=COLOR_BG_CARD)
        r2.pack(fill="x", pady=2)
        make_action_btn(r2, "🔊 VOL+", lambda: self._execute_command_text("volume up")).pack(side="left", padx=2)
        make_action_btn(r2, "🔉 VOL-", lambda: self._execute_command_text("volume down")).pack(side="left", padx=2)
        make_action_btn(r2, "🔒 LOCK", lambda: self._execute_command_text("lock pc")).pack(side="left", padx=2)
        make_action_btn(r2, "💬 STATUS", lambda: self._execute_command_text("system status")).pack(side="left", padx=2)

        self.canvas.create_window(712, 60, anchor="nw", window=self.actions_frame, width=252, height=62, tags="ui_controls")

    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag_motion(self, event):
        deltax = event.x - self._drag_data["x"]
        deltay = event.y - self._drag_data["y"]
        self.curr_x = self.root.winfo_x() + deltax
        self.curr_y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{self.curr_x}+{self.curr_y}")

    def _toggle_compact_mode(self, event=None):
        """Switches between Full Holographic Command Dock and Compact Floating Arc-Reactor Orb."""
        self.is_compact = not self.is_compact
        if self.is_compact:
            self.root.geometry(f"{self.mini_w}x{self.mini_h}+{self.curr_x + 400}+{self.curr_y + 20}")
            self.canvas.config(width=self.mini_w, height=self.mini_h)
            self.canvas.itemconfigure("ui_controls", state="hidden")
        else:
            self.root.geometry(f"{self.full_w}x{self.full_h}+{self.curr_x}+{self.curr_y}")
            self.canvas.config(width=self.full_w, height=self.full_h)
            self.canvas.itemconfigure("ui_controls", state="normal")

    def _minimize_to_mini(self):
        self.is_compact = True
        self.root.geometry(f"{self.mini_w}x{self.mini_h}+{self.curr_x + 400}+{self.curr_y + 20}")
        self.canvas.config(width=self.mini_w, height=self.mini_h)
        self.canvas.itemconfigure("ui_controls", state="hidden")

    def _open_3d_map(self):
        """Opens the full Three.js God's Eye tactical satellite map in the browser on port 3000."""
        log.info("Opening God's Eye 3D Satellite Map...")
        try:
            webbrowser.open("http://localhost:3000")
        except Exception as e:
            log.warning("Could not launch browser: %s", e)

    def _wake_up_toggle(self):
        """Wakes up or dismisses Wrock."""
        if self.state == "SLEEPING":
            self._post_rest("/api/voice/wake")
            self._enqueue_state({"state": "LISTENING", "user_text": "[Awakened] Listening for command..."})
        else:
            self._post_rest("/api/voice/dismiss")
            self._enqueue_state({"state": "SLEEPING", "wrock_text": '"Standing by."'})

    def _send_user_command(self):
        """Fires the command typed in the input box."""
        text = self.cmd_entry.get().strip()
        if not text:
            return
        self.cmd_entry.delete(0, tk.END)
        self._execute_command_text(text)

    def _execute_command_text(self, command: str):
        self.user_text = f"You: \"{command}\""
        self.state = "THINKING"
        self.wrock_text = "Processing command..."

        # Submit via REST API / WebSocket
        def send_async():
            try:
                if httpx:
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.post(f"{self.backend_url}/api/voice/command", json={"command": command, "is_final": True})
                        if resp.status_code == 200:
                            data = resp.json()
                            spoken = data.get("spoken_text") or data.get("response") or "Executed."
                            self._enqueue_state({"state": "SPEAKING", "wrock_text": f'Wrock: "{spoken}"'})
                            return
            except Exception as e:
                log.warning("REST command failed: %s", e)

            # Fallback direct state
            self._enqueue_state({"state": "SPEAKING", "wrock_text": f'Wrock: "Command \'{command}\' dispatched to OS controller."'})

        threading.Thread(target=send_async, daemon=True).start()

    def _post_rest(self, endpoint: str):
        def task():
            try:
                if httpx:
                    with httpx.Client(timeout=5.0) as client:
                        client.post(f"{self.backend_url}{endpoint}")
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def _enqueue_state(self, data: Dict[str, Any]):
        self.msg_queue.put(data)

    def _poll_queue(self):
        """Process messages received from network background loop."""
        try:
            while not self.msg_queue.empty():
                msg = self.msg_queue.get_nowait()
                if "state" in msg:
                    self.state = msg["state"]
                if "user_text" in msg:
                    self.user_text = msg["user_text"]
                if "wrock_text" in msg:
                    self.wrock_text = msg["wrock_text"]
                if "audio_level" in msg:
                    self.audio_level = msg["audio_level"]
                if "connected" in msg:
                    self.is_connected = msg["connected"]
        except Exception:
            pass
        self.root.after(40, self._poll_queue)

    def _run_network_loop(self):
        """Persistent WebSocket loop connecting to FastAPI backend."""
        while self.running:
            if not websockets:
                time.sleep(2)
                continue
            try:
                asyncio.run(self._ws_client_session())
            except Exception as e:
                self._enqueue_state({"connected": False})
                time.sleep(3)

    async def _ws_client_session(self):
        async with websockets.connect(self.ws_url) as ws:
            log.info("Connected to Wrock Backend WebSocket at %s", self.ws_url)
            self._enqueue_state({"connected": True})

            async for msg_str in ws:
                try:
                    payload = json.loads(msg_str)
                    evt_type = payload.get("type")
                    data = payload.get("payload", {})

                    if evt_type == "LIFECYCLE_STATE":
                        st = data.get("state", "SLEEPING")
                        self._enqueue_state({"state": st})

                    elif evt_type == "VOICE_INTENT":
                        spoken = data.get("spoken_text") or data.get("hud_alert")
                        user_cmd = data.get("command")
                        update = {}
                        if spoken:
                            update["wrock_text"] = f'Wrock: "{spoken}"'
                            update["state"] = "SPEAKING"
                        if user_cmd:
                            update["user_text"] = f'You: "{user_cmd}"'
                        if update:
                            self._enqueue_state(update)

                    elif evt_type == "OS_GESTURE_EVENT":
                        g_name = data.get("gesture")
                        if g_name and g_name != "IDLE":
                            self._enqueue_state({"user_text": f"🖐️ Hand Gesture: {g_name}"})

                except Exception as e:
                    pass

    # =========================================================================
    # 60FPS GRAPHICAL RENDER & ANIMATION LOOP
    # =========================================================================
    def _animate_loop(self):
        if not self.running:
            return
        try:
            self.anim_step += 1
            self.canvas.delete("hud_gfx")

            if self.is_compact:
                self._render_compact_mode()
            else:
                self._render_full_dock()

        except Exception as e:
            pass

        self.root.after(25, self._animate_loop)

    def _render_compact_mode(self):
        """Renders mini 80x80 Arc Reactor Orb when collapsed."""
        cx, cy = 44, 44
        self._draw_arc_reactor(cx, cy, radius_scale=0.8)

    def _render_full_dock(self):
        """Renders the full holographic middle-bottom command dock."""
        w, h = self.full_w, self.full_h

        # 1. Glass Cyber Dock Outer Shell (Rounded Chamfered Appearance)
        pad = 6
        self.canvas.create_polygon(
            pad + 12, pad,
            w - pad - 12, pad,
            w - pad, pad + 12,
            w - pad, h - pad - 12,
            w - pad - 12, h - pad,
            pad + 12, h - pad,
            pad, h - pad - 12,
            pad, pad + 12,
            fill=COLOR_BG_CARD,
            outline=COLOR_BORDER,
            width=2,
            tags="hud_gfx"
        )

        # Subtle Glowing Edge Highlights
        self.canvas.create_line(pad + 12, pad, pad + 80, pad, fill=COLOR_CYAN_GLOW, width=3, tags="hud_gfx")
        self.canvas.create_line(w - pad - 80, pad, w - pad - 12, pad, fill=COLOR_CYAN_GLOW, width=3, tags="hud_gfx")
        self.canvas.create_line(pad, pad + 12, pad, pad + 60, fill=COLOR_CYAN_GLOW, width=3, tags="hud_gfx")
        self.canvas.create_line(w - pad, pad + 12, w - pad, pad + 60, fill=COLOR_CYAN_GLOW, width=3, tags="hud_gfx")

        # 2. Draw Pulsating Animated Arc-Reactor AI Core
        self._draw_arc_reactor(cx=58, cy=66, radius_scale=1.0)

        # 3. Status Badge & Equalizer Row (Top Info)
        status_colors = {
            "SLEEPING": ("#556677", "💤 ASLEEP (SAY 'WAKE UP WROCK' OR CLICK WAKE)"),
            "LISTENING": (COLOR_CYAN, "🎙️ LISTENING FOR VOICE COMMAND..."),
            "THINKING": (COLOR_AMBER, "⚡ THINKING & EXECUTING..."),
            "SPEAKING": (COLOR_EMERALD, "🗣️ WROCK SPEAKING VIA NEURAL VOICE"),
        }
        theme_col, status_title = status_colors.get(self.state, (COLOR_CYAN, f"⚡ STATE: {self.state}"))

        # Brand / Core Name
        self.canvas.create_text(118, 22, text="WROCK SPATIAL-AI CORE", anchor="w", fill="#ffffff", font=self.font_title, tags="hud_gfx")

        # Status Pill Badge
        badge_x = 320
        self.canvas.create_text(badge_x, 22, text=status_title, anchor="w", fill=theme_col, font=self.font_badge, tags="hud_gfx")

        # Animated Audio Equalizer Bars (12 bars reacting to voice state)
        eq_x = 730
        eq_y = 26
        num_bars = 14
        for i in range(num_bars):
            if self.state in ("SPEAKING", "LISTENING"):
                bar_h = 4 + int(math.sin(self.anim_step * 0.35 + i * 0.8) * 9 + random.randint(2, 8))
                bar_col = COLOR_EMERALD if self.state == "SPEAKING" else COLOR_CYAN
            elif self.state == "THINKING":
                bar_h = 3 + int(math.sin(self.anim_step * 0.5 + i * 0.5) * 6 + 4)
                bar_col = COLOR_AMBER
            else:
                bar_h = 3 + int(math.sin(self.anim_step * 0.08 + i * 0.4) * 2 + 2)
                bar_col = "#004d40"

            bx = eq_x + i * 6
            self.canvas.create_line(bx, eq_y, bx, eq_y - bar_h, fill=bar_col, width=3, tags="hud_gfx")

        # 4. Live Dialogue Tickers
        u_txt = self.user_text if len(self.user_text) < 85 else (self.user_text[:82] + "...")
        w_txt = self.wrock_text if len(self.wrock_text) < 85 else (self.wrock_text[:82] + "...")

        self.canvas.create_text(118, 44, text=u_txt, anchor="w", fill=COLOR_TEXT_MUTED, font=self.font_dialogue, tags="hud_gfx")
        self.canvas.create_text(118, 64, text=w_txt, anchor="w", fill=COLOR_CYAN_GLOW, font=self.font_dialogue, tags="hud_gfx")

    def _draw_arc_reactor(self, cx: int, cy: int, radius_scale: float = 1.0):
        """Draws multi-ring, animated high-tech Arc Reactor core in the canvas."""
        pulse = math.sin(self.anim_step * 0.12) * (3.0 * radius_scale)
        
        # Color profile based on state
        if self.state == "LISTENING":
            core_col = "#ffffff"
            ring_col = COLOR_CYAN
            coil_col = "#00ffff"
        elif self.state == "THINKING":
            core_col = "#fff8e1"
            ring_col = COLOR_AMBER
            coil_col = "#ffca28"
        elif self.state == "SPEAKING":
            core_col = "#e8f5e9"
            ring_col = COLOR_EMERALD
            coil_col = "#69f0ae"
        else: # SLEEPING / IDLE
            core_col = COLOR_CYAN
            ring_col = "#00838f"
            coil_col = "#00bcd4"

        # 1. Outer Chassis Ring
        r_outer = (40 + pulse) * radius_scale
        self.canvas.create_oval(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer, outline=ring_col, width=2, tags="hud_gfx")

        # 2. Segmented Electromagnetic Coils (10 Coils around the perimeter)
        num_coils = 10
        coil_rot = self.anim_step * 0.04
        r_coil_track = 31 * radius_scale
        for c in range(num_coils):
            angle = coil_rot + (c * (2 * math.pi / num_coils))
            px = cx + math.cos(angle) * r_coil_track
            py = cy + math.sin(angle) * r_coil_track
            
            # Coil bracket
            px2 = cx + math.cos(angle) * (r_coil_track + 6 * radius_scale)
            py2 = cy + math.sin(angle) * (r_coil_track + 6 * radius_scale)
            self.canvas.create_line(px, py, px2, py2, fill=coil_col, width=2, tags="hud_gfx")

        # 3. Inner Secondary Ring
        r_inner = 20 * radius_scale
        self.canvas.create_oval(cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner, outline=ring_col, width=1.5, tags="hud_gfx")

        # 4. Central Reactor Core (High Glow)
        r_core = (11 + pulse * 0.4) * radius_scale
        self.canvas.create_oval(cx - r_core, cy - r_core, cx + r_core, cy + r_core, fill=core_col, outline="#ffffff", width=1.5, tags="hud_gfx")

        # 5. Orbiting Energy Sparkles
        orb_angle = (self.anim_step * 0.15) % (2 * math.pi)
        spark_x = cx + math.cos(orb_angle) * (r_outer + 4 * radius_scale)
        spark_y = cy + math.sin(orb_angle) * (r_outer + 4 * radius_scale)
        self.canvas.create_oval(spark_x - 2, spark_y - 2, spark_x + 2, spark_y + 2, fill="#ffffff", outline=ring_col, tags="hud_gfx")

    def run(self):
        log.info("Starting Wrock Floating Arc-Reactor Desktop Dock...")
        self.root.mainloop()


if __name__ == "__main__":
    dock = FloatingArcReactorDock()
    dock.run()
