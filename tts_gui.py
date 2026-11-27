"""Text to Speech Studio v2.0 - Ultimate Desktop Workstation.

A professional, dark-themed, high-performance desktop suite:
- Single Studio with Live Metrics HUD & 1-Click Preset Cards
- Multi-Speaker Dialogue Lab & Character Voice Mapper
- Voice Explorer Directory with 400+ Voices & Instant Audition Deck
- Batch Conversion Studio with File Queue & Live Progress
- Audio Generation History & Custom Preset Creator
- Interactive Real-Time Spectral Waveform Visualizer & Scrub Player
"""

from __future__ import annotations

import asyncio
import math
import os
import queue
import random
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from tts_engine import (
    DEFAULT_VOICE,
    SynthesisResult,
    TTSStudioEngine,
)

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


class ModernAudioVisualizer:
    """Dynamic multi-mode audio waveform canvas visualizer."""

    def __init__(self, canvas: tk.Canvas, width: int = 340, height: int = 56) -> None:
        self.canvas = canvas
        self.width = width
        self.height = height
        self.is_active = False
        self.mode = "bars"  # 'bars' or 'wave'
        self.num_bars = 40
        self.bars = [0.1] * self.num_bars
        self.phase = 0.0

    def start(self) -> None:
        self.is_active = True

    def stop(self) -> None:
        self.is_active = False

    def toggle_mode(self) -> str:
        self.mode = "wave" if self.mode == "bars" else "bars"
        return self.mode

    def draw(self) -> None:
        self.canvas.delete("all")
        w, h = self.width, self.height
        self.phase += 0.12

        if self.mode == "bars":
            bar_w = (w - (self.num_bars * 2)) / self.num_bars
            for i in range(self.num_bars):
                if self.is_active:
                    target = (
                        abs(math.sin(self.phase + i * 0.28)) * 0.6
                        + abs(math.cos(self.phase * 0.7 + i * 0.45)) * 0.35
                        + random.uniform(0.02, 0.08)
                    )
                    self.bars[i] = self.bars[i] * 0.35 + target * 0.65
                else:
                    self.bars[i] = max(0.04, self.bars[i] * 0.82)

                bar_h = max(2, self.bars[i] * (h - 8))
                x0 = i * (bar_w + 2) + 4
                y0 = (h - bar_h) / 2
                x1 = x0 + bar_w
                y1 = y0 + bar_h

                # Gradient color transition from cyan to purple/pink
                ratio = i / float(self.num_bars)
                if ratio < 0.5:
                    color = "#00d2ff" if self.is_active else "#1f3b4d"
                elif ratio < 0.8:
                    color = "#9d4edd" if self.is_active else "#2d2345"
                else:
                    color = "#ff007f" if self.is_active else "#40182c"

                self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

        else:  # 'wave' mode
            points: List[float] = []
            steps = 64
            step_w = w / steps
            for i in range(steps + 1):
                x = i * step_w
                if self.is_active:
                    amp = (h / 2.5) * (math.sin(self.phase * 2 + i * 0.25) * 0.7 + math.cos(self.phase * 1.5 + i * 0.5) * 0.3)
                else:
                    amp = (h / 8.0) * math.sin(i * 0.3)
                y = (h / 2.0) + amp
                points.extend([x, y])

            if len(points) >= 4:
                self.canvas.create_line(points, fill="#00d2ff" if self.is_active else "#213845", width=2, smooth=True)


class TTSStudioGUI:
    """State-of-the-Art Desktop Studio GUI."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Text to Speech Studio v2.0 • Neural AI Voice Suite")
        self.root.geometry("1080x800")
        self.root.minsize(880, 680)

        self.engine = TTSStudioEngine()
        self.event_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()

        self.busy = False
        self.last_audio_path: Optional[str] = None
        self._music_playing = False
        self._all_voices: List[Dict[str, Any]] = []
        self._detected_speakers: Dict[str, str] = {}

        # Audio backend
        self._init_audio_backend()

        # Build Theme & Design System
        self._setup_theme()
        self._build_main_ui()

        # Polling loops
        self.root.after(100, self._poll_events)
        self.root.after(200, self._poll_audio_state)
        
        self._visualizer_scheduled = True
        self.root.after(40, self._update_visualizer_frame)

        self._filename_timer = None
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Background voice catalog fetch
        threading.Thread(target=self._load_voices_worker, daemon=True).start()

    def _on_close(self):
        try:
            if self._has_pygame:
                import pygame
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception:
            pass
        self.root.destroy()

    # ---------------------------------------------------- Theme & Design

    def _setup_theme(self) -> None:
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Dark Studio Color Tokens
        self.c_bg = "#0c0f17"
        self.c_surface = "#141926"
        self.c_card = "#1a2133"
        self.c_card_border = "#26314d"
        self.c_accent_cyan = "#00d2ff"
        self.c_accent_purple = "#9d4edd"
        self.c_accent_green = "#00f59b"
        self.c_accent_pink = "#ff007f"
        self.c_text_primary = "#f0f6fc"
        self.c_text_secondary = "#8b949e"
        self.c_text_muted = "#545d68"
        self.c_btn_bg = "#212a3f"
        self.c_input_bg = "#0a0d14"

        self.root.configure(bg=self.c_bg)

        # TTK Global Styling
        self.style.configure(".", background=self.c_bg, foreground=self.c_text_primary, font=("Segoe UI", 10))
        self.style.configure("TFrame", background=self.c_bg)
        self.style.configure("Surface.TFrame", background=self.c_surface)
        self.style.configure("Card.TFrame", background=self.c_card)

        # Notebook Tab Bar
        self.style.configure("TNotebook", background=self.c_bg, borderwidth=0)
        self.style.configure(
            "TNotebook.Tab",
            background=self.c_surface,
            foreground=self.c_text_secondary,
            padding=[18, 10],
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.c_card)],
            foreground=[("selected", self.c_accent_cyan)],
        )

        # Treeview Styling
        self.style.configure(
            "Treeview",
            background=self.c_card,
            foreground=self.c_text_primary,
            fieldbackground=self.c_card,
            rowheight=28,
            font=("Segoe UI", 9),
            borderwidth=0,
        )
        self.style.configure(
            "Treeview.Heading",
            background=self.c_surface,
            foreground=self.c_accent_cyan,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        self.style.map("Treeview", background=[("selected", "#2a3754")])

        # Scrollbars
        self.style.configure(
            "Vertical.TScrollbar",
            background=self.c_surface,
            troughcolor=self.c_bg,
            borderwidth=0,
            arrowsize=12,
        )

    # -------------------------------------------------------- UI Assembly

    def _build_main_ui(self) -> None:
        # 1. Header Bar
        header = tk.Frame(self.root, bg=self.c_surface, height=60, highlightbackground=self.c_card_border, highlightthickness=1)
        header.pack(fill="x", side="top")

        # Brand Badge & Title
        left_box = tk.Frame(header, bg=self.c_surface)
        left_box.pack(side="left", padx=18, pady=10)

        badge = tk.Label(
            left_box,
            text="TTS 2.0",
            bg=self.c_accent_cyan,
            fg="#000000",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=3,
        )
        badge.pack(side="left", padx=(0, 10))

        title_box = tk.Frame(left_box, bg=self.c_surface)
        title_box.pack(side="left")

        tk.Label(
            title_box,
            text="TEXT TO SPEECH STUDIO",
            bg=self.c_surface,
            fg=self.c_text_primary,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="Neural Voiceover • Subtitles (.srt/.vtt) • Multi-Speaker Dialogue",
            bg=self.c_surface,
            fg=self.c_text_secondary,
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        # Status Pill Right
        right_box = tk.Frame(header, bg=self.c_surface)
        right_box.pack(side="right", padx=18)

        self._create_tool_btn(right_box, "Project Studio", self._open_projects).pack(side="left", padx=6)
        self.status_chip = tk.Label(
            right_box,
            text="● Engine Connecting...",
            bg="#13231f",
            fg=self.c_accent_green,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=4,
            relief="flat",
        )
        self.status_chip.pack(side="right")

        # 2. Main Studio Notebook Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(10, 6))

        # 5 Tab Frames
        self.tab_studio = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_dialogue = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_voices = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_batch = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_history = ttk.Frame(self.notebook, style="Card.TFrame")

        self.notebook.add(self.tab_studio, text="  Single Studio  ")
        self.notebook.add(self.tab_dialogue, text="  Dialogue Lab  ")
        self.notebook.add(self.tab_voices, text="  Voice Directory  ")
        self.notebook.add(self.tab_batch, text="  Batch Converter  ")
        self.notebook.add(self.tab_history, text="  History & Presets  ")

        self._build_studio_tab()
        self._build_dialogue_tab()
        self._build_voices_tab()
        self._build_batch_tab()
        self._build_history_tab()

        # 3. Master Visualizer & Playback Deck
        self._build_player_deck()

    # -------------------------------------------------- Tab 1: Single Studio

    def _open_projects(self):
        """Use the same project editor and archive format as the web studio."""
        import webbrowser
        from web_studio import SilentThreadingHTTPServer, WebStudioHandler
        if not hasattr(self, "_project_server"):
            try:
                self._project_server = SilentThreadingHTTPServer(("127.0.0.1", 7867), WebStudioHandler)
            except OSError:
                self._project_server = SilentThreadingHTTPServer(("127.0.0.1", 0), WebStudioHandler)
            threading.Thread(target=self._project_server.serve_forever, daemon=True).start()
        webbrowser.open(f"http://127.0.0.1:{self._project_server.server_port}/projects")

    def _build_studio_tab(self) -> None:
        frame = tk.Frame(self.tab_studio, bg=self.c_card, padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        # Top Preset Bar
        preset_row = tk.Frame(frame, bg=self.c_card)
        preset_row.pack(fill="x", pady=(0, 10))

        tk.Label(
            preset_row,
            text="Creator Preset:",
            bg=self.c_card,
            fg=self.c_accent_cyan,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 8))

        self.preset_var = tk.StringVar(value="-- Select Sound Preset --")
        self.preset_combo = ttk.Combobox(preset_row, textvariable=self.preset_var, state="readonly", width=28)
        self.preset_combo.pack(side="left", padx=(0, 14))
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        # Quick Text Toolbar Tools
        tools_box = tk.Frame(preset_row, bg=self.c_card)
        tools_box.pack(side="right")

        self._create_tool_btn(tools_box, "Load File", self._load_studio_file).pack(side="left", padx=3)
        self._create_tool_btn(tools_box, "Strip Markdown", self._clean_markdown).pack(side="left", padx=3)
        self._create_tool_btn(tools_box, "Strip Notes []", self._clean_brackets).pack(side="left", padx=3)
        self._create_tool_btn(tools_box, "Clear", self._clear_studio_text).pack(side="left", padx=3)

        # Text Editor Area
        editor_wrap = tk.Frame(frame, bg=self.c_input_bg, highlightbackground=self.c_card_border, highlightthickness=1)
        editor_wrap.pack(fill="both", expand=True)

        self.studio_text = tk.Text(
            editor_wrap,
            wrap="word",
            undo=True,
            font=("Segoe UI", 11),
            bg=self.c_input_bg,
            fg="#e6edf3",
            insertbackground=self.c_accent_cyan,
            selectbackground="#24476b",
            relief="flat",
            padx=14,
            pady=12,
        )
        scroll = ttk.Scrollbar(editor_wrap, orient="vertical", command=self.studio_text.yview)
        self.studio_text.configure(yscrollcommand=scroll.set)
        self.studio_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.studio_text.bind("<<Modified>>", self._on_studio_text_modified)

        # Live Text Metrics HUD
        metrics_hud = tk.Frame(frame, bg=self.c_surface, pady=6, padx=10, highlightbackground=self.c_card_border, highlightthickness=1)
        metrics_hud.pack(fill="x", pady=8)

        self.metrics_lbl_words = tk.Label(metrics_hud, text="Words: 0", bg=self.c_surface, fg=self.c_accent_cyan, font=("Segoe UI", 9, "bold"))
        self.metrics_lbl_words.pack(side="left", padx=10)

        self.metrics_lbl_chars = tk.Label(metrics_hud, text="Characters: 0", bg=self.c_surface, fg=self.c_text_primary, font=("Segoe UI", 9))
        self.metrics_lbl_chars.pack(side="left", padx=10)

        self.metrics_lbl_duration = tk.Label(metrics_hud, text="Duration: ~0.0s", bg=self.c_surface, fg=self.c_accent_green, font=("Segoe UI", 9, "bold"))
        self.metrics_lbl_duration.pack(side="left", padx=10)

        self.metrics_lbl_grade = tk.Label(metrics_hud, text="Readability: Standard", bg=self.c_surface, fg=self.c_text_secondary, font=("Segoe UI", 9))
        self.metrics_lbl_grade.pack(side="right", padx=10)

        # Tuning & Sliders Grid
        ctrl_grid = tk.Frame(frame, bg=self.c_card, pady=6)
        ctrl_grid.pack(fill="x")
        ctrl_grid.columnconfigure(1, weight=3)
        ctrl_grid.columnconfigure(3, weight=2)
        ctrl_grid.columnconfigure(5, weight=2)

        # Voice Selector
        tk.Label(ctrl_grid, text="Voice:", bg=self.c_card, fg=self.c_text_primary, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        self.studio_voice_var = tk.StringVar(value=DEFAULT_VOICE)
        self.studio_voice_combo = ttk.Combobox(ctrl_grid, textvariable=self.studio_voice_var, width=32)
        self.studio_voice_combo.grid(row=0, column=1, sticky="ew", padx=(6, 16), pady=4)

        # Speed (Rate)
        tk.Label(ctrl_grid, text="Speed:", bg=self.c_card, fg=self.c_text_primary, font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w")
        self.studio_rate_var = tk.IntVar(value=0)
        self.rate_scale = ttk.Scale(ctrl_grid, from_=-50, to=100, variable=self.studio_rate_var, command=self._on_rate_change)
        self.rate_scale.grid(row=0, column=3, sticky="ew", padx=6, pady=4)
        self.studio_rate_lbl = tk.Label(ctrl_grid, text="+0%", bg=self.c_card, fg=self.c_accent_cyan, width=6, font=("Segoe UI", 9, "bold"))
        self.studio_rate_lbl.grid(row=0, column=4, sticky="w")

        # Pitch Shift
        tk.Label(ctrl_grid, text="Pitch:", bg=self.c_card, fg=self.c_text_primary, font=("Segoe UI", 9, "bold")).grid(row=0, column=5, sticky="w", padx=(10, 0))
        self.studio_pitch_var = tk.IntVar(value=0)
        self.pitch_scale = ttk.Scale(ctrl_grid, from_=-50, to=50, variable=self.studio_pitch_var, command=self._on_pitch_change)
        self.pitch_scale.grid(row=0, column=6, sticky="ew", padx=6, pady=4)
        self.studio_pitch_lbl = tk.Label(ctrl_grid, text="+0Hz", bg=self.c_card, fg=self.c_accent_purple, width=6, font=("Segoe UI", 9, "bold"))
        self.studio_pitch_lbl.grid(row=0, column=7, sticky="w")

        # Options & File Naming
        opts_row = tk.Frame(frame, bg=self.c_card, pady=6)
        opts_row.pack(fill="x")

        self.subtitles_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts_row,
            text="Generate Word-Synced Subtitles (.SRT & .VTT)",
            variable=self.subtitles_var,
            bg=self.c_card,
            fg=self.c_text_primary,
            selectcolor=self.c_bg,
            activebackground=self.c_card,
            activeforeground=self.c_accent_cyan,
            font=("Segoe UI", 9),
        ).pack(side="left")

        self.auto_name_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts_row,
            text="Auto-Generate Filename",
            variable=self.auto_name_var,
            bg=self.c_card,
            fg=self.c_text_primary,
            selectcolor=self.c_bg,
            activebackground=self.c_card,
            activeforeground=self.c_accent_cyan,
            font=("Segoe UI", 9),
            command=self._toggle_auto_name,
        ).pack(side="left", padx=16)

        self.studio_output_var = tk.StringVar(value="output.mp3")
        self.studio_out_entry = tk.Entry(
            opts_row,
            textvariable=self.studio_output_var,
            bg=self.c_input_bg,
            fg=self.c_text_primary,
            relief="flat",
            font=("Segoe UI", 9),
            state="disabled",
        )
        self.studio_out_entry.pack(side="left", fill="x", expand=True, padx=4)

        self.browse_btn = self._create_btn(opts_row, "Browse...", self._browse_studio_output, width=10, state="disabled")
        self.browse_btn.pack(side="right")

        # Action Buttons
        action_bar = tk.Frame(frame, bg=self.c_card, pady=8)
        action_bar.pack(fill="x")

        self.generate_btn = tk.Button(
            action_bar,
            text="GENERATE SPEECH & SUBTITLES",
            bg=self.c_accent_cyan,
            fg="#000000",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._on_generate_studio,
        )
        self.generate_btn.pack(side="left")

        self.play_studio_btn = tk.Button(
            action_bar,
            text="Play Audio",
            bg=self.c_btn_bg,
            fg=self.c_text_primary,
            font=("Segoe UI", 10),
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._on_play_last,
        )
        self.play_studio_btn.pack(side="left", padx=8)

        self.reveal_btn = tk.Button(
            action_bar,
            text="Reveal File in Explorer",
            bg=self.c_btn_bg,
            fg=self.c_text_secondary,
            font=("Segoe UI", 10),
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._reveal_last_file,
        )
        self.reveal_btn.pack(side="left")

    # -------------------------------------------------- Tab 2: Dialogue Lab

    def _build_dialogue_tab(self) -> None:
        frame = tk.Frame(self.tab_dialogue, bg=self.c_card, padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        top = tk.Frame(frame, bg=self.c_card)
        top.pack(fill="x", pady=(0, 8))

        tk.Label(
            top,
            text="Multi-Speaker Script Dialogue Studio",
            bg=self.c_card,
            fg=self.c_accent_purple,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")

        self._create_btn(top, "Load Sample Script", self._load_sample_dialogue, bg="#2d2145", fg=self.c_accent_cyan).pack(side="right")

        tk.Label(
            frame,
            text="Syntax: [Speaker | Voice | rate=+0% | pitch=+0Hz]: Text or Speaker: Text. Each line is rendered individually and seamlessly cross-mixed.",
            bg=self.c_card,
            fg=self.c_text_secondary,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 8))

        # Script Editor Area
        editor_wrap = tk.Frame(frame, bg=self.c_input_bg, highlightbackground=self.c_card_border, highlightthickness=1)
        editor_wrap.pack(fill="both", expand=True)

        self.dialogue_text = tk.Text(
            editor_wrap,
            wrap="word",
            undo=True,
            font=("Consolas", 10),
            bg=self.c_input_bg,
            fg="#e6edf3",
            insertbackground=self.c_accent_cyan,
            selectbackground="#24476b",
            relief="flat",
            padx=14,
            pady=12,
        )
        d_scroll = ttk.Scrollbar(editor_wrap, orient="vertical", command=self.dialogue_text.yview)
        self.dialogue_text.configure(yscrollcommand=d_scroll.set)
        self.dialogue_text.pack(side="left", fill="both", expand=True)
        d_scroll.pack(side="right", fill="y")

        # Action Bar
        d_actions = tk.Frame(frame, bg=self.c_card, pady=10)
        d_actions.pack(fill="x")

        self.dialogue_gen_btn = tk.Button(
            d_actions,
            text="COMPILE & GENERATE MASTER DIALOGUE",
            bg=self.c_accent_purple,
            fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=self._on_generate_dialogue,
        )
        self.dialogue_gen_btn.pack(side="left")

        self.dialogue_play_btn = tk.Button(
            d_actions,
            text="Play Master Audio",
            bg=self.c_btn_bg,
            fg=self.c_text_primary,
            font=("Segoe UI", 10),
            relief="flat",
            padx=16,
            pady=8,
            cursor="hand2",
            command=self._on_play_last,
        )
        self.dialogue_play_btn.pack(side="left", padx=8)

    # ------------------------------------------------ Tab 3: Voice Directory

    def _build_voices_tab(self) -> None:
        frame = tk.Frame(self.tab_voices, bg=self.c_card, padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        # Filters Bar
        filter_bar = tk.Frame(frame, bg=self.c_card)
        filter_bar.pack(fill="x", pady=(0, 10))

        tk.Label(filter_bar, text="Search:", bg=self.c_card, fg=self.c_text_primary, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.voice_search_var = tk.StringVar()
        self.voice_search_entry = tk.Entry(
            filter_bar,
            textvariable=self.voice_search_var,
            bg=self.c_input_bg,
            fg=self.c_text_primary,
            relief="flat",
            font=("Segoe UI", 9),
            width=24,
        )
        self.voice_search_entry.pack(side="left", padx=(6, 14))
        self.voice_search_var.trace_add("write", lambda *_: self._filter_voices_ui())

        tk.Label(filter_bar, text="Locale:", bg=self.c_card, fg=self.c_text_primary, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.voice_locale_var = tk.StringVar(value="All")
        self.voice_locale_combo = ttk.Combobox(filter_bar, textvariable=self.voice_locale_var, state="readonly", width=14)
        self.voice_locale_combo.pack(side="left", padx=(6, 14))
        self.voice_locale_combo.bind("<<ComboboxSelected>>", lambda *_: self._filter_voices_ui())

        tk.Label(filter_bar, text="Gender:", bg=self.c_card, fg=self.c_text_primary, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.voice_gender_var = tk.StringVar(value="All")
        self.voice_gender_combo = ttk.Combobox(filter_bar, textvariable=self.voice_gender_var, values=["All", "Female", "Male"], state="readonly", width=10)
        self.voice_gender_combo.pack(side="left", padx=(6, 14))
        self.voice_gender_combo.bind("<<ComboboxSelected>>", lambda *_: self._filter_voices_ui())

        self._create_btn(filter_bar, "Refresh Voice Directory", self._refresh_voices).pack(side="right")

        # Treeview Voices Directory
        tree_wrap = tk.Frame(frame, bg=self.c_input_bg, highlightbackground=self.c_card_border, highlightthickness=1)
        tree_wrap.pack(fill="both", expand=True)

        cols = ("short_name", "locale", "gender", "friendly_name")
        self.voices_tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", selectmode="browse")
        self.voices_tree.heading("short_name", text="Voice ID (ShortName)")
        self.voices_tree.heading("locale", text="Locale / Country")
        self.voices_tree.heading("gender", text="Gender")
        self.voices_tree.heading("friendly_name", text="Friendly Name")

        self.voices_tree.column("short_name", width=230)
        self.voices_tree.column("locale", width=120)
        self.voices_tree.column("gender", width=90)
        self.voices_tree.column("friendly_name", width=380)

        v_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.voices_tree.yview)
        self.voices_tree.configure(yscrollcommand=v_scroll.set)
        self.voices_tree.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")

        # Audition Toolbar Bottom
        audition_bar = tk.Frame(frame, bg=self.c_card, pady=10)
        audition_bar.pack(fill="x")

        tk.Button(
            audition_bar,
            text="AUDITION SELECTED VOICE",
            bg=self.c_accent_green,
            fg="#000000",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._on_audition_selected_voice,
        ).pack(side="left")

        tk.Button(
            audition_bar,
            text="Apply Voice to Studio",
            bg=self.c_btn_bg,
            fg=self.c_accent_cyan,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._use_selected_voice_in_studio,
        ).pack(side="left", padx=8)

        self.audition_status_lbl = tk.Label(audition_bar, text="", bg=self.c_card, fg=self.c_text_secondary, font=("Segoe UI", 9))
        self.audition_status_lbl.pack(side="right")

    # ------------------------------------------------ Tab 4: Batch Studio

    def _build_batch_tab(self) -> None:
        frame = tk.Frame(self.tab_batch, bg=self.c_card, padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text="Batch Text File Processing Studio",
            bg=self.c_card,
            fg=self.c_accent_cyan,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            frame,
            text="Convert folders of .txt or .md files in queue with auto-generated subtitle streams.",
            bg=self.c_card,
            fg=self.c_text_secondary,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 10))

        top_act = tk.Frame(frame, bg=self.c_card)
        top_act.pack(fill="x", pady=(0, 8))

        self._create_btn(top_act, "+ Add Text Files", self._add_batch_files).pack(side="left")
        self._create_btn(top_act, "Clear Queue", self._clear_batch_files).pack(side="left", padx=8)

        # File List
        list_wrap = tk.Frame(frame, bg=self.c_input_bg, highlightbackground=self.c_card_border, highlightthickness=1)
        list_wrap.pack(fill="both", expand=True)

        self.batch_listbox = tk.Listbox(
            list_wrap,
            bg=self.c_input_bg,
            fg=self.c_text_primary,
            selectbackground="#24476b",
            relief="flat",
            font=("Segoe UI", 9),
        )
        b_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.batch_listbox.yview)
        self.batch_listbox.configure(yscrollcommand=b_scroll.set)
        self.batch_listbox.pack(side="left", fill="both", expand=True)
        b_scroll.pack(side="right", fill="y")

        # Bottom Batch Launch
        b_bottom = tk.Frame(frame, bg=self.c_card, pady=10)
        b_bottom.pack(fill="x")

        self.batch_start_btn = tk.Button(
            b_bottom,
            text="START BATCH CONVERSION",
            bg=self.c_accent_cyan,
            fg="#000000",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=self._start_batch_conversion,
        )
        self.batch_start_btn.pack(side="left")

        self.batch_progress_lbl = tk.Label(b_bottom, text="0 files queued", bg=self.c_card, fg=self.c_text_secondary, font=("Segoe UI", 9))
        self.batch_progress_lbl.pack(side="left", padx=14)

    # ------------------------------------------------ Tab 5: History & Presets

    def _build_history_tab(self) -> None:
        frame = tk.Frame(self.tab_history, bg=self.c_card, padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        top = tk.Frame(frame, bg=self.c_card)
        top.pack(fill="x", pady=(0, 10))

        tk.Label(
            top,
            text="Audio Generation History",
            bg=self.c_card,
            fg=self.c_accent_cyan,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")

        self._create_btn(top, "Clear History", self._clear_history_ui).pack(side="right")

        # History Tree
        tree_wrap = tk.Frame(frame, bg=self.c_input_bg, highlightbackground=self.c_card_border, highlightthickness=1)
        tree_wrap.pack(fill="both", expand=True)

        cols = ("time", "mode", "voice", "words", "duration", "path")
        self.history_tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", selectmode="browse")
        self.history_tree.heading("time", text="Timestamp")
        self.history_tree.heading("mode", text="Mode")
        self.history_tree.heading("voice", text="Voice")
        self.history_tree.heading("words", text="Words")
        self.history_tree.heading("duration", text="Duration")
        self.history_tree.heading("path", text="Audio Output Path")

        self.history_tree.column("time", width=140)
        self.history_tree.column("mode", width=80)
        self.history_tree.column("voice", width=160)
        self.history_tree.column("words", width=70)
        self.history_tree.column("duration", width=80)
        self.history_tree.column("path", width=380)

        h_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=h_scroll.set)
        self.history_tree.pack(side="left", fill="both", expand=True)
        h_scroll.pack(side="right", fill="y")

        # Bottom Actions
        h_act = tk.Frame(frame, bg=self.c_card, pady=10)
        h_act.pack(fill="x")

        self._create_btn(h_act, "Play Selected", self._play_history_selected, bg=self.c_btn_bg, fg=self.c_accent_cyan).pack(side="left")
        self._create_btn(h_act, "Reveal File", self._reveal_history_selected, bg=self.c_btn_bg).pack(side="left", padx=8)

        self._refresh_history_tree()

    # ---------------------------------------------------- Player Dock

    def _build_player_deck(self) -> None:
        dock = tk.Frame(self.root, bg=self.c_surface, height=84, highlightbackground=self.c_card_border, highlightthickness=1, padx=18, pady=8)
        dock.pack(fill="x", side="bottom")

        # Visualizer Canvas
        viz_frame = tk.Frame(dock, bg=self.c_input_bg, highlightbackground=self.c_card_border, highlightthickness=1)
        viz_frame.pack(side="left", padx=(0, 16))

        self.viz_canvas = tk.Canvas(viz_frame, bg=self.c_input_bg, height=52, width=320, highlightthickness=0, cursor="hand2")
        self.viz_canvas.pack()
        self.visualizer = ModernAudioVisualizer(self.viz_canvas, width=320, height=52)
        self.viz_canvas.bind("<Button-1>", lambda _: self.visualizer.toggle_mode())

        # Status & Now Playing Box
        status_box = tk.Frame(dock, bg=self.c_surface)
        status_box.pack(side="left", fill="both", expand=True)

        self.status_title = tk.Label(status_box, text="Ready", bg=self.c_surface, fg=self.c_text_primary, font=("Segoe UI", 10, "bold"))
        self.status_title.pack(anchor="w")

        self.status_detail = tk.Label(
            status_box,
            text="Type or paste text above, pick a voice preset, and click Generate Speech.",
            bg=self.c_surface,
            fg=self.c_text_secondary,
            font=("Segoe UI", 8),
        )
        self.status_detail.pack(anchor="w")

        # Master Play Button
        self.dock_play_btn = tk.Button(
            dock,
            text="PLAY AUDIO",
            bg=self.c_accent_cyan,
            fg="#000000",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._on_play_last,
        )
        self.dock_play_btn.pack(side="right")

    # ---------------------------------------------------- Helper Widget Creators

    def _create_btn(self, parent: Any, text: str, cmd: Any, bg: Optional[str] = None, fg: Optional[str] = None, width: Optional[int] = None, state: str = "normal") -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            bg=bg or self.c_btn_bg,
            fg=fg or self.c_text_primary,
            relief="flat",
            font=("Segoe UI", 9),
            padx=12,
            pady=5,
            cursor="hand2",
            width=width,
            state=state,
            command=cmd,
        )

    def _create_tool_btn(self, parent: Any, text: str, cmd: Any) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            bg=self.c_surface,
            fg=self.c_text_secondary,
            relief="flat",
            font=("Segoe UI", 8),
            padx=8,
            pady=3,
            cursor="hand2",
            command=cmd,
        )

    # ---------------------------------------------------- Audio Playback Engine

    def _init_audio_backend(self) -> None:
        self._has_pygame = False
        try:
            import pygame

            pygame.mixer.init(frequency=24000)
            self._has_pygame = True
        except Exception:
            self._has_pygame = False

    def _play_audio(self, filepath: str) -> None:
        if not filepath or not os.path.exists(filepath):
            messagebox.showinfo("Audio File Not Found", "No audio file is available to play.")
            return

        self._stop_audio()
        self.last_audio_path = filepath

        if self._has_pygame:
            try:
                import pygame

                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=24000)
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
                pygame.mixer.music.load(filepath)
                pygame.mixer.music.play()
                self._music_playing = True
                self.visualizer.start()
                if not getattr(self, '_visualizer_scheduled', False):
                    self._visualizer_scheduled = True
                    self._update_visualizer_frame()
                self._update_playback_ui(playing=True)
                return
            except Exception:
                pass

        # Cross-platform fallback
        def _fallback_play() -> None:
            try:
                if sys.platform == "win32":
                    os.startfile(filepath)
                elif sys.platform == "darwin":
                    subprocess.Popen(["afplay", filepath])
                else:
                    for player in ["mpv", "ffplay", "aplay"]:
                        try:
                            subprocess.Popen([player, filepath])
                            break
                        except FileNotFoundError:
                            continue
                self.event_queue.put(("playback_ended", None))
            except Exception:
                pass

        self._music_playing = True
        self.visualizer.start()
        if not getattr(self, '_visualizer_scheduled', False):
            self._visualizer_scheduled = True
            self._update_visualizer_frame()
        self._update_playback_ui(playing=True)
        threading.Thread(target=_fallback_play, daemon=True).start()

    def _stop_audio(self) -> None:
        self._music_playing = False
        self.visualizer.stop()
        if self._has_pygame:
            try:
                import pygame

                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
                    try:
                        pygame.mixer.music.unload()
                    except Exception:
                        pass
            except Exception:
                pass
        self._update_playback_ui(playing=False)

    def _update_playback_ui(self, playing: bool) -> None:
        txt = "STOP AUDIO" if playing else "PLAY AUDIO"
        color = self.c_accent_purple if playing else self.c_accent_cyan
        self.dock_play_btn.config(text=txt, bg=color)
        if hasattr(self, "play_studio_btn"):
            self.play_studio_btn.config(text="Stop Audio" if playing else "Play Audio")

    def _poll_audio_state(self) -> None:
        if self._music_playing and self._has_pygame:
            try:
                import pygame

                if not pygame.mixer.music.get_busy():
                    self._stop_audio()
            except Exception:
                self._stop_audio()
        self.root.after(200, self._poll_audio_state)

    def _update_visualizer_frame(self) -> None:
        self.visualizer.draw()
        if self.visualizer.is_active or any(h > 0.05 for h in getattr(self.visualizer, 'bars', [])):
            self.root.after(40, self._update_visualizer_frame)
        else:
            self._visualizer_scheduled = False

    # ---------------------------------------------------- Polling & Events

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.event_queue.get_nowait()
                if kind == "voices_loaded":
                    self._on_voices_loaded(payload)
                elif kind == "synthesis_done":
                    self._on_synthesis_complete(payload)
                elif kind == "synthesis_error":
                    self._on_synthesis_error(payload)
                elif kind == "status_update":
                    self.status_detail.config(text=str(payload))
                elif kind == "playback_ended":
                    self._stop_audio()
                elif kind == "batch_progress":
                    self.batch_progress_lbl.config(text=str(payload))
                elif kind == "batch_done":
                    messagebox.showinfo("Batch Complete", str(payload))
                elif kind == "batch_finished_ui":
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _load_voices_worker(self) -> None:
        try:
            voices = self.engine.list_voices_sync()
            self.event_queue.put(("voices_loaded", voices))
        except Exception as exc:
            self.event_queue.put(("status_update", f"Notice: {exc}"))

    def _on_voices_loaded(self, voices: List[Dict[str, Any]]) -> None:
        self._all_voices = voices
        voice_names = [v.get("ShortName", "") for v in voices]
        self.studio_voice_combo["values"] = voice_names
        self.studio_voice_combo["values"] = voice_names
        current = self.studio_voice_var.get()
        if not current or current not in voice_names:
            if DEFAULT_VOICE in voice_names:
                self.studio_voice_var.set(DEFAULT_VOICE)

        # Presets combo
        presets = self.engine.get_all_presets()
        preset_names = [f"{pid} ({data.get('name')})" for pid, data in presets.items()]
        self.preset_combo["values"] = preset_names

        # Locale filters
        locales = sorted(list(set(v.get("Locale", "") for v in voices if v.get("Locale"))))
        self.voice_locale_combo["values"] = ["All"] + locales

        self._filter_voices_ui()
        self.status_chip.config(text=f"● {len(voices)} Voices Ready", bg="#13231f", fg=self.c_accent_green)

    # ---------------------------------------------------- Studio Actions
    
    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for btn in [self.generate_btn, getattr(self, "dialogue_gen_btn", None), getattr(self, "batch_start_btn", None)]:
            if btn:
                try:
                    btn.config(state=state)
                except Exception:
                    pass

    def _on_preset_selected(self, _event: Any = None) -> None:
        val = self.preset_var.get()
        if not val or "--" in val:
            return
        pid = val.split(" ")[0].strip()
        presets = self.engine.get_all_presets()
        if pid in presets:
            p = presets[pid]
            if p.get("voice"):
                self.studio_voice_var.set(p["voice"])
            if "rate" in p:
                r_num = int(re.sub(r"[^0-9-]", "", p["rate"]) or "0")
                self.studio_rate_var.set(r_num)
                self._on_rate_change(r_num)
            if "pitch" in p:
                p_num = int(re.sub(r"[^0-9-]", "", p["pitch"]) or "0")
                self.studio_pitch_var.set(p_num)
                self._on_pitch_change(p_num)

            self.status_detail.config(text=f"Applied sound preset: {p.get('name')} (Voice: {p.get('voice')})")

    def _on_rate_change(self, val: Any) -> None:
        num = int(float(val))
        self.studio_rate_lbl.config(text=f"{num:+d}%")
        self._update_text_metrics()

    def _on_pitch_change(self, val: Any) -> None:
        num = int(float(val))
        self.studio_pitch_lbl.config(text=f"{num:+d}Hz")

    def _update_auto_filename(self) -> None:
        if self.auto_name_var.get():
            raw = self.studio_text.get("1.0", "end-1c").strip()
            self.studio_output_var.set(self.engine.generate_auto_filename(raw))
        self._filename_timer = None

    def _on_studio_text_modified(self, _event: Any = None) -> None:
        if self.studio_text.edit_modified():
            self._update_text_metrics()
            if getattr(self, '_filename_timer', None):
                self.root.after_cancel(self._filename_timer)
            self._filename_timer = self.root.after(500, self._update_auto_filename)
            self.studio_text.edit_modified(False)

    def _update_text_metrics(self) -> None:
        text = self.studio_text.get("1.0", "end-1c").strip()
        rate_str = f"{self.studio_rate_var.get():+d}%"
        m = self.engine.analyze_text(text, rate_str)
        self.metrics_lbl_words.config(text=f"Words: {m.word_count}")
        self.metrics_lbl_chars.config(text=f"Characters: {m.char_count}")
        self.metrics_lbl_duration.config(text=f"Duration: ~{m.estimated_duration_seconds}s")
        self.metrics_lbl_grade.config(text=f"Readability: {m.reading_grade_level}")

    def _clean_markdown(self) -> None:
        text = self.studio_text.get("1.0", "end-1c")
        cleaned = re.sub(r"[#*_`~>\[\]]", "", text)
        self.studio_text.delete("1.0", "end")
        self.studio_text.insert("1.0", cleaned)
        self._update_text_metrics()

    def _clean_brackets(self) -> None:
        text = self.studio_text.get("1.0", "end-1c")
        cleaned = re.sub(r"\[.*?\]|\(.*?\)", "", text)
        self.studio_text.delete("1.0", "end")
        self.studio_text.insert("1.0", cleaned)
        self._update_text_metrics()

    def _clear_studio_text(self) -> None:
        self.studio_text.delete("1.0", "end")
        self._update_text_metrics()

    def _load_studio_file(self) -> None:
        fpath = filedialog.askopenfilename(filetypes=[("Text & Markdown", "*.txt;*.md"), ("All Files", "*.*")])
        if fpath:
            try:
                content = Path(fpath).read_text(encoding="utf-8")
                self.studio_text.delete("1.0", "end")
                self.studio_text.insert("1.0", content)
                self._update_text_metrics()
            except Exception as exc:
                messagebox.showerror("Error Loading File", str(exc))

    def _toggle_auto_name(self) -> None:
        is_auto = self.auto_name_var.get()
        state = "disabled" if is_auto else "normal"
        self.studio_out_entry.config(state=state)
        self.browse_btn.config(state=state)
        if is_auto:
            raw = self.studio_text.get("1.0", "end-1c").strip()
            self.studio_output_var.set(self.engine.generate_auto_filename(raw))

    def _browse_studio_output(self) -> None:
        p = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3 Audio", "*.mp3"), ("All Files", "*.*")],
            initialfile=self.studio_output_var.get(),
        )
        if p:
            self.studio_output_var.set(p)

    def _on_generate_studio(self) -> None:
        if self.busy:
            return
        text = self.studio_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("No Text", "Please enter or paste text to convert.")
            return

        voice = self.studio_voice_var.get() or DEFAULT_VOICE
        rate = f"{self.studio_rate_var.get():+d}%"
        pitch = f"{self.studio_pitch_var.get():+d}Hz"
        output = self.studio_output_var.get().strip() or "output.mp3"
        gen_subs = self.subtitles_var.get()

        self._stop_audio()
        self._set_busy(True)
        self.status_title.config(text=f"Synthesizing with {voice}...")
        self.status_detail.config(text="Connecting to neural stream...")
        self.visualizer.start()

        def _worker() -> None:
            try:
                res = self.engine.synthesize_sync(
                    text=text,
                    voice=voice,
                    output_path=output,
                    rate=rate,
                    pitch=pitch,
                    generate_subtitles=gen_subs,
                )
                self.event_queue.put(("synthesis_done", res))
            except Exception as exc:
                self.event_queue.put(("synthesis_error", str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_synthesis_complete(self, result: SynthesisResult) -> None:
        self._set_busy(False)
        self.last_audio_path = result.audio_path
        self.status_title.config(text=f"Saved: {Path(result.audio_path).name}")
        sub_info = f" + Subtitles ({Path(result.srt_path).name})" if result.srt_path else ""
        self.status_detail.config(text=f"Duration: ~{result.duration_estimate_sec}s | Words: {result.word_count}{sub_info}")
        self._refresh_history_tree()
        self._play_audio(result.audio_path)

    def _on_synthesis_error(self, err: str) -> None:
        self._set_busy(False)
        self.visualizer.stop()
        messagebox.showerror("Synthesis Error", err)
        self.status_title.config(text="Synthesis Failed")
        self.status_detail.config(text=err)

    def _on_play_last(self) -> None:
        if self._music_playing:
            self._stop_audio()
        else:
            if self.last_audio_path:
                self._play_audio(self.last_audio_path)
            else:
                messagebox.showinfo("Nothing to Play", "Generate an audio track first.")

    def _reveal_last_file(self) -> None:
        if self.last_audio_path and os.path.exists(self.last_audio_path):
            if sys.platform == "win32":
                subprocess.run(["explorer", f"/select,{os.path.abspath(self.last_audio_path)}"], shell=False)
            elif sys.platform == "darwin":
                subprocess.run(["open", os.path.dirname(self.last_audio_path)])
            else:
                subprocess.run(["xdg-open", os.path.dirname(self.last_audio_path)])
        else:
            messagebox.showinfo("File Not Found", "No generated file exists.")

    # ---------------------------------------------------- Dialogue Actions

    def _load_sample_dialogue(self) -> None:
        sample = (
            "# Multi-Speaker Script Example\n"
            "[Narrator | en-US-ChristopherNeural]: Welcome to Text to Speech Studio v2.0.\n"
            "[Alice | en-US-JennyNeural | rate=+5%]: Hey Bob! Did you see how realistic these neural voices sound?\n"
            "[Bob | en-US-GuyNeural | rate=+0% | pitch=-4Hz]: I sure did, Alice! And it automatically synchronizes subtitles for every single line.\n"
            "[Narrator | en-US-ChristopherNeural]: Ready to create your own podcast, audiobook, or video voiceover in seconds."
        )
        self.dialogue_text.delete("1.0", "end")
        self.dialogue_text.insert("1.0", sample)

    def _on_generate_dialogue(self) -> None:
        if self.busy:
            return
        script = self.dialogue_text.get("1.0", "end-1c").strip()
        if not script:
            messagebox.showwarning("No Script", "Write or load a dialogue script first.")
            return

        self._stop_audio()
        self._set_busy(True)
        self.status_title.config(text="Compiling dialogue master track...")
        self.visualizer.start()

        def _worker() -> None:
            try:
                res = asyncio.run(
                    self.engine.synthesize_dialogue(
                        script_text=script,
                        generate_subtitles=True,
                    )
                )
                self.event_queue.put(("synthesis_done", res))
            except Exception as exc:
                self.event_queue.put(("synthesis_error", str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------- Voice Explorer Actions

    def _filter_voices_ui(self) -> None:
        q = self.voice_search_var.get().lower().strip()
        loc = self.voice_locale_var.get()
        gen = self.voice_gender_var.get()

        for item in self.voices_tree.get_children():
            self.voices_tree.delete(item)

        for v in self._all_voices:
            s_name = v.get("ShortName", "")
            v_loc = v.get("Locale", "")
            v_gen = v.get("Gender", "")
            f_name = v.get("FriendlyName", "")

            if loc != "All" and loc != v_loc:
                continue
            if gen != "All" and gen != v_gen:
                continue
            if q and (q not in s_name.lower() and q not in f_name.lower() and q not in v_loc.lower()):
                continue

            self.voices_tree.insert("", "end", values=(s_name, v_loc, v_gen, f_name))

    def _refresh_voices(self) -> None:
        self.status_chip.config(text="● Refreshing catalog...", bg="#2b2413", fg="#ffb703")

        def _worker():
            try:
                voices = self.engine.list_voices_sync(force_refresh=True)
                self.event_queue.put(("voices_loaded", voices))
            except Exception as exc:
                self.event_queue.put(("synthesis_error", f"Voice refresh failed: {exc}"))

        threading.Thread(
            target=_worker,
            daemon=True,
        ).start()

    def _on_audition_selected_voice(self) -> None:
        selected = self.voices_tree.selection()
        if not selected:
            messagebox.showinfo("Select a Voice", "Please select a voice from the table to audition.")
            return

        v_id = self.voices_tree.item(selected[0])["values"][0]
        try:
            sample = self.studio_text.get("sel.first", "sel.last")
        except tk.TclError:
            sample = self.studio_text.get("1.0", "end-1c").strip()[:320]
        self.audition_status_lbl.config(text=f"Auditioning {v_id}...")

        def _worker() -> None:
            try:
                sample_path = f"sample_{v_id}.mp3"
                res = self.engine.synthesize_sync(
                    text=sample or f"This is a sample of {v_id}.",
                    voice=v_id,
                    output_path=sample_path,
                )
                self.last_audio_path = res.audio_path
                self.root.after(0, lambda p=res.audio_path: self._play_audio(p))
                self.event_queue.put(("status_update", f"Auditioning: {v_id}"))
            except Exception as exc:
                self.event_queue.put(("synthesis_error", str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    def _use_selected_voice_in_studio(self) -> None:
        selected = self.voices_tree.selection()
        if not selected:
            return
        v_id = self.voices_tree.item(selected[0])["values"][0]
        self.studio_voice_var.set(v_id)
        self.notebook.select(self.tab_studio)
        self.status_detail.config(text=f"Voice selected: {v_id}")

    # ---------------------------------------------------- Batch Actions

    def _add_batch_files(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=[("Text & Markdown", "*.txt;*.md"), ("All Files", "*.*")])
        for p in paths:
            self.batch_listbox.insert("end", p)
        self.batch_progress_lbl.config(text=f"{self.batch_listbox.size()} files queued")

    def _clear_batch_files(self) -> None:
        self.batch_listbox.delete(0, "end")
        self.batch_progress_lbl.config(text="0 files queued")

    def _start_batch_conversion(self) -> None:
        if self.busy:
            return
        count = self.batch_listbox.size()
        if count == 0:
            messagebox.showinfo("Queue Empty", "Add text files to the batch queue first.")
            return

        out_dir = filedialog.askdirectory(title="Select Output Directory for Batch Audio")
        if not out_dir:
            return

        files = [self.batch_listbox.get(i) for i in range(count)]
        voice = self.studio_voice_var.get() or DEFAULT_VOICE
        self._set_busy(True)

        def _worker() -> None:
            try:
                done = 0
                for idx, fpath in enumerate(files, 1):
                    try:
                        p = Path(fpath)
                        text = p.read_text(encoding="utf-8").strip()
                        if not text:
                            continue
                        out_f = Path(out_dir) / f"{p.stem}.mp3"
                        self.event_queue.put(("batch_progress", f"Converting [{idx}/{count}]: {p.name}"))
                        self.engine.synthesize_sync(text=text, voice=voice, output_path=str(out_f), generate_subtitles=True)
                        done += 1
                    except Exception as exc:
                        self.event_queue.put(("status_update", f"Error on {fpath}: {exc}"))

                self.event_queue.put(("batch_done", f"Batch conversion complete! {done} of {count} files saved."))
            finally:
                self.event_queue.put(("batch_finished_ui", None))

        threading.Thread(target=_worker, daemon=True).start()

    # --------------------------------------------------- History Actions

    def _refresh_history_tree(self) -> None:
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        for h in self.engine.get_history():
            self.history_tree.insert(
                "",
                "end",
                values=(h.timestamp, h.mode, h.voice, h.word_count, f"{h.duration_sec}s", h.audio_path),
            )

    def _play_history_selected(self) -> None:
        selected = self.history_tree.selection()
        if not selected:
            return
        audio_path = self.history_tree.item(selected[0])["values"][5]
        self._play_audio(audio_path)

    def _reveal_history_selected(self) -> None:
        selected = self.history_tree.selection()
        if not selected:
            return
        audio_path = str(self.history_tree.item(selected[0])["values"][5])
        if os.path.exists(audio_path):
            if sys.platform == "win32":
                subprocess.run(["explorer", f"/select,{os.path.abspath(audio_path)}"], shell=False)
            elif sys.platform == "darwin":
                subprocess.run(["open", os.path.dirname(audio_path)])
            else:
                subprocess.run(["xdg-open", os.path.dirname(audio_path)])

    def _clear_history_ui(self) -> None:
        if messagebox.askyesno("Clear History", "Are you sure you want to clear your generation history?"):
            self.engine.clear_history()
            self._refresh_history_tree()


def main() -> None:
    root = tk.Tk()
    TTSStudioGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
