"""Text to Speech Web Studio - Modern Browser Interface & REST API.

A standalone, zero-dependency local web studio with glassmorphism UI,
real-time Web Audio API visualizer, multi-speaker dialogue builder,
instant MP3 / SRT / VTT downloads, and REST API endpoints.

Run with:
    python web_studio.py
"""

from __future__ import annotations

import asyncio
import datetime
import tempfile
import shutil
import uuid
from zipfile import ZipFile
import studio_project
import studio_audio
import json
import mimetypes
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from tts_engine import DEFAULT_VOICE, TTSStudioEngine

engine = TTSStudioEngine()
STATIC_OUTPUT_DIR = Path("web_output")
STATIC_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Hot-Reload Build State
_CURRENT_BUILD_VERSION: int = int(time.time() * 1000)
_build_lock = threading.Lock()


def touch_build_version() -> None:
    global _CURRENT_BUILD_VERSION
    with _build_lock:
        _CURRENT_BUILD_VERSION = int(time.time() * 1000)


def restart_server() -> None:
    """Restart current process to reload fresh Python bytecode and templates."""
    print("⚡ [Hot-Reload] File modification detected. Reloading server engine...")
    try:
        time.sleep(0.2)
        env = os.environ.copy()
        env["TTS_HOT_RELOAD"] = "1"
        python_exe = sys.executable
        os.execve(python_exe, [python_exe] + sys.argv, env)
    except Exception as e:
        print(f"[Hot-Reload] Process reload error: {e}")


def start_file_watcher(watch_dir: Path | None = None) -> None:
    """Watch python and asset files for modifications and trigger dynamic browser reloads."""
    if watch_dir is None:
        watch_dir = Path(__file__).parent.resolve()

    file_mtimes: Dict[str, float] = {}

    def _get_tracked_files() -> List[Path]:
        files: List[Path] = []
        for ext in ("*.py", "*.html", "*.css", "*.js", "*.json", "*.txt", "*.md"):
            for f in watch_dir.glob(ext):
                f_name = f.name
                if "web_output" not in str(f) and ".git" not in str(f) and "__pycache__" not in str(f) and not f_name.endswith(".tmp"):
                    files.append(f)
        return files

    # Initialize baseline timestamps
    for f in _get_tracked_files():
        try:
            file_mtimes[str(f)] = f.stat().st_mtime
        except Exception:
            pass

    def _watcher_loop() -> None:
        time.sleep(1.0)
        while True:
            time.sleep(0.5)
            changed = False
            current_files = _get_tracked_files()
            for f in current_files:
                f_str = str(f)
                try:
                    mtime = f.stat().st_mtime
                    if f_str not in file_mtimes:
                        file_mtimes[f_str] = mtime
                        changed = True
                    elif file_mtimes[f_str] != mtime:
                        file_mtimes[f_str] = mtime
                        changed = True
                except Exception:
                    pass

            if changed:
                touch_build_version()
                restart_server()

    threading.Thread(target=_watcher_loop, daemon=True, name="HotReloadWatcher").start()



FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#00d2ff"/><stop offset="100%" stop-color="#9d4edd"/></linearGradient><linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0e1524"/><stop offset="100%" stop-color="#070a10"/></linearGradient></defs><rect width="64" height="64" rx="16" fill="url(#bg)" stroke="url(#g)" stroke-width="2.5"/><path d="M32 14c-4.4 0-8 3.6-8 8v12c0 4.4 3.6 8 8 8s8-3.6 8-8V22c0-4.4-3.6-8-8-8z" fill="url(#g)"/><path d="M18 30c0 7.7 6.3 14 14 14s14-6.3 14-14" fill="none" stroke="#00f59b" stroke-width="3.5" stroke-linecap="round"/><path d="M32 44v8M24 52h16" fill="none" stroke="#00f59b" stroke-width="3.5" stroke-linecap="round"/></svg>"""

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Text to Speech Studio v2.0 • Neural AI Voice Suite</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0%25' y1='0%25' x2='100%25' y2='100%25'%3E%3Cstop offset='0%25' stop-color='%2300d2ff'/%3E%3Cstop offset='100%25' stop-color='%239d4edd'/%3E%3C/linearGradient%3E%3ClinearGradient id='bg' x1='0%25' y1='0%25' x2='100%25' y2='100%25'%3E%3Cstop offset='0%25' stop-color='%230e1524'/%3E%3Cstop offset='100%25' stop-color='%23070a10'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='64' height='64' rx='16' fill='url(%23bg)' stroke='url(%23g)' stroke-width='2.5'/%3E%3Cpath d='M32 14c-4.4 0-8 3.6-8 8v12c0 4.4 3.6 8 8 8s8-3.6 8-8V22c0-4.4-3.6-8-8-8z' fill='url(%23g)'/%3E%3Cpath d='M18 30c0 7.7 6.3 14 14 14s14-6.3 14-14' fill='none' stroke='%2300f59b' stroke-width='3.5' stroke-linecap='round'/%3E%3Cpath d='M32 44v8M24 52h16' fill='none' stroke='%2300f59b' stroke-width='3.5' stroke-linecap='round'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <style>
    :root {
      --bg: #0b0f17;
      --card-bg: #141a29;
      --card-border: rgba(255, 255, 255, 0.09);
      --accent: #00d2ff;
      --accent-purple: #9d4edd;
      --accent-green: #00f59b;
      --accent-glow: rgba(0, 210, 255, 0.25);
      --text: #f0f6fc;
      --subtext: #8b949e;
      --input-bg: #0d121c;
      --font-main: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
      -webkit-font-smoothing: antialiased;
      transform: translateZ(0);
    }

    /* Top Navbar */
    header {
      background: #0f1422;
      border-bottom: 1px solid var(--card-border);
      padding: 14px 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
      transform: translateZ(0);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .logo-badge {
      background: linear-gradient(135deg, var(--accent), var(--accent-purple));
      color: #000;
      font-weight: 800;
      font-size: 14px;
      padding: 6px 12px;
      border-radius: 8px;
      letter-spacing: 0.5px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .brand h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.3px;
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(0, 245, 155, 0.1);
      border: 1px solid rgba(0, 245, 155, 0.3);
      color: var(--accent-green);
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
    }
    .status-dot {
      width: 7px;
      height: 7px;
      background: var(--accent-green);
      border-radius: 50%;
    }

    /* Container */
    main {
      flex: 1;
      max-width: 1200px;
      width: 100%;
      margin: 0 auto;
      padding: 24px 20px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    /* Navigation Tabs */
    .tabs-nav {
      display: flex;
      gap: 10px;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 10px;
    }

    .tab-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--subtext);
      font-family: var(--font-main);
      font-size: 14px;
      font-weight: 600;
      padding: 8px 18px;
      border-radius: 10px;
      cursor: pointer;
      transition: background 0.15s ease, color 0.15s ease;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tab-btn:hover {
      color: var(--text);
      background: rgba(255, 255, 255, 0.05);
    }
    .tab-btn.active {
      color: var(--accent);
      background: rgba(0, 210, 255, 0.12);
      border-color: rgba(0, 210, 255, 0.3);
    }

    /* Studio Card */
    .glass-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.3);
      position: relative;
      overflow: visible;
    }

    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* Text Editor Area */
    .editor-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 10px;
    }

    .presets-row {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }

    .preset-pill {
      background: var(--input-bg);
      border: 1px solid var(--card-border);
      color: var(--subtext);
      font-size: 12px;
      padding: 4px 10px;
      border-radius: 14px;
      cursor: pointer;
      transition: color 0.15s ease, border-color 0.15s ease;
    }
    .preset-pill:hover, .preset-pill.active {
      color: var(--accent);
      border-color: var(--accent);
      background: rgba(0, 210, 255, 0.08);
    }

    textarea {
      width: 100%;
      height: 180px;
      background: var(--input-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      color: var(--text);
      font-family: var(--font-main);
      font-size: 15px;
      line-height: 1.6;
      padding: 16px;
      outline: none;
      resize: vertical;
      transition: border-color 0.15s;
    }
    textarea:focus {
      border-color: var(--accent);
    }

    .metrics-bar {
      display: flex;
      gap: 16px;
      margin-top: 8px;
      font-size: 12px;
      color: var(--subtext);
      flex-wrap: wrap;
    }
    .metrics-bar span b { color: var(--text); }

    /* Controls Grid */
    .controls-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-top: 20px;
    }

    .control-item {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    label {
      font-size: 13px;
      font-weight: 600;
      color: var(--subtext);
      display: flex;
      justify-content: space-between;
    }

    select, input[type="text"] {
      background: var(--input-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--text);
      font-family: var(--font-main);
      font-size: 14px;
      padding: 10px 12px;
      outline: none;
    }
    select:focus, input[type="text"]:focus {
      border-color: var(--accent);
    }

    input[type="range"] {
      accent-color: var(--accent);
      cursor: pointer;
    }

    /* Buttons & Actions */
    .action-row {
      display: flex;
      gap: 12px;
      margin-top: 24px;
      align-items: center;
      flex-wrap: wrap;
    }

    .btn-primary {
      background: linear-gradient(135deg, #00d2ff, #0077ff);
      color: #000;
      border: none;
      font-family: var(--font-main);
      font-weight: 700;
      font-size: 14px;
      padding: 12px 24px;
      border-radius: 10px;
      cursor: pointer;
      transition: all 0.2s;
      box-shadow: 0 4px 20px rgba(0, 210, 255, 0.3);
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    .btn-primary:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 24px rgba(0, 210, 255, 0.45);
    }
    .btn-primary:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none;
    }

    .btn-secondary {
      background: var(--input-bg);
      border: 1px solid var(--card-border);
      color: var(--text);
      font-family: var(--font-main);
      font-weight: 600;
      font-size: 13px;
      padding: 10px 16px;
      border-radius: 8px;
      cursor: pointer;
      transition: 0.2s;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .btn-secondary:hover {
      border-color: var(--accent);
      color: var(--accent);
    }

    /* Player & Visualizer Bar */
    .player-dock {
      margin-top: 24px;
      background: rgba(13, 17, 23, 0.95);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 16px 20px;
      display: flex;
      align-items: center;
      gap: 20px;
      flex-wrap: wrap;
    }

    canvas#visualizer {
      width: 240px;
      height: 48px;
      background: #080b10;
      border-radius: 8px;
    }

    audio {
      flex: 1;
      height: 40px;
      min-width: 240px;
    }

    /* Voice Explorer Table */
    .voice-table-wrap {
      max-height: 440px;
      overflow-y: auto;
      border: 1px solid var(--card-border);
      border-radius: 10px;
      margin-top: 14px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }
    th {
      background: var(--input-bg);
      padding: 10px 14px;
      color: var(--accent);
      font-weight: 600;
      position: sticky;
      top: 0;
    }
    td {
      padding: 10px 14px;
      border-top: 1px solid var(--card-border);
      color: var(--text);
    }
    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }

    .tag-gender {
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
    }
    .tag-female { background: rgba(255, 105, 180, 0.15); color: #ff69b4; }
    .tag-male { background: rgba(0, 210, 255, 0.15); color: #00d2ff; }

    /* Custom Scrollbar across the entire Studio */
    ::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }
    ::-webkit-scrollbar-track {
      background: rgba(13, 17, 23, 0.7);
      border-radius: 8px;
    }
    ::-webkit-scrollbar-thumb {
      background: linear-gradient(180deg, rgba(0, 210, 255, 0.6), rgba(157, 78, 221, 0.6));
      border-radius: 8px;
      border: 2px solid rgba(13, 17, 23, 0.8);
      transition: background 0.2s ease, box-shadow 0.2s ease;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: linear-gradient(180deg, #00d2ff, #9d4edd);
      box-shadow: 0 0 10px rgba(0, 210, 255, 0.5);
    }
    * {
      scrollbar-width: thin;
      scrollbar-color: rgba(0, 210, 255, 0.6) rgba(13, 17, 23, 0.7);
    }

    /* Custom JS Dropdown Styling */
    .custom-select-wrapper {
      position: relative;
      user-select: none;
      width: 100%;
      z-index: 50;
    }
    .custom-select-wrapper.open {
      z-index: 9999;
    }

    .custom-select-trigger {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--input-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      color: var(--text);
      font-size: 14px;
      padding: 10px 14px;
      cursor: pointer;
      transition: all 0.2s ease;
      min-height: 44px;
    }
    .custom-select-trigger:hover, .custom-select-wrapper.open .custom-select-trigger {
      border-color: var(--accent);
      box-shadow: 0 0 12px rgba(0, 210, 255, 0.2);
    }

    .custom-select-trigger .selected-info {
      display: flex;
      align-items: center;
      gap: 10px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .custom-select-trigger .arrow-icon {
      color: var(--subtext);
      font-size: 12px;
      transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .custom-select-wrapper.open .custom-select-trigger .arrow-icon {
      transform: rotate(180deg);
      color: var(--accent);
    }

    .custom-dropdown-menu {
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      width: 100%;
      min-width: 340px;
      max-width: 520px;
      background: #111726;
      border: 1px solid rgba(0, 210, 255, 0.3);
      border-radius: 12px;
      box-shadow: 0 20px 48px rgba(0, 0, 0, 0.85), 0 0 0 1px rgba(0, 210, 255, 0.2);
      z-index: 99999;
      opacity: 0;
      visibility: hidden;
      transform: translateY(-8px);
      transition: opacity 0.18s cubic-bezier(0.16, 1, 0.3, 1), transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), visibility 0.18s;
      padding: 10px;
    }
    .custom-select-wrapper.open .custom-dropdown-menu {
      opacity: 1;
      visibility: visible;
      transform: translateY(0);
    }
    .custom-dropdown-menu.drop-up {
      top: auto;
      bottom: calc(100% + 6px);
      transform: translateY(8px);
    }
    .custom-select-wrapper.open .custom-dropdown-menu.drop-up {
      transform: translateY(0);
    }

    .dropdown-search-box {
      position: relative;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
    }
    .dropdown-search-box i {
      position: absolute;
      left: 14px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--accent);
      font-size: 13px;
      pointer-events: none;
      z-index: 2;
    }
    .dropdown-search-input {
      width: 100%;
      background: #080c14;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--text);
      font-family: var(--font-main);
      font-size: 13px;
      padding: 10px 14px 10px 40px;
      outline: none;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .dropdown-search-input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 8px rgba(0, 210, 255, 0.25);
    }

    .dropdown-hub-link {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      background: rgba(0, 210, 255, 0.08);
      border: 1px dashed rgba(0, 210, 255, 0.3);
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 12px;
      font-weight: 600;
      color: var(--accent);
      cursor: pointer;
      margin-bottom: 8px;
      transition: all 0.2s;
    }
    .dropdown-hub-link:hover {
      background: rgba(0, 210, 255, 0.18);
      border-color: var(--accent);
    }

    .dropdown-options-list {
      max-height: 280px;
      min-height: 180px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 2px;
      scroll-behavior: smooth;
    }

    .dropdown-option {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
      font-size: 13px;
    }
    .dropdown-option:hover {
      background: rgba(0, 210, 255, 0.1);
      color: var(--accent);
    }
    .dropdown-option.selected {
      background: rgba(0, 210, 255, 0.15);
      color: var(--accent);
      font-weight: 600;
    }
    .dropdown-option .opt-left {
      display: flex;
      align-items: center;
      gap: 8px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dropdown-option .opt-badge {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.08);
      color: var(--subtext);
    }
    .dropdown-option.selected .opt-badge {
      background: rgba(0, 210, 255, 0.2);
      color: var(--accent);
    }

    .opt-audition-btn {
      background: transparent;
      border: none;
      color: var(--subtext);
      font-size: 12px;
      cursor: pointer;
      padding: 4px 6px;
      border-radius: 4px;
      transition: all 0.15s;
    }
    .opt-audition-btn:hover {
      color: var(--accent);
      background: rgba(0, 210, 255, 0.15);
    }

    /* Modal Dialog for Full Voice Hub */
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(5, 8, 14, 0.8);
      display: none;
      justify-content: center;
      align-items: center;
      z-index: 100000;
      padding: 20px;
    }
    .modal-overlay.active {
      display: flex;
    }
    .modal-card {
      background: #111726;
      border: 1px solid rgba(0, 210, 255, 0.3);
      border-radius: 16px;
      width: 100%;
      max-width: 900px;
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.9), 0 0 0 1px rgba(0, 210, 255, 0.2);
      overflow: hidden;
    }
    .modal-header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #0f1422;
    }
    .modal-header h3 {
      font-size: 16px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text);
    }
    .modal-close-btn {
      background: transparent;
      border: none;
      color: var(--subtext);
      font-size: 18px;
      cursor: pointer;
      padding: 4px 8px;
      border-radius: 6px;
      transition: color 0.15s;
    }
    .modal-close-btn:hover {
      color: #ff5555;
    }
    .modal-filters {
      padding: 14px 20px;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      flex-direction: column;
      gap: 10px;
      background: rgba(13, 18, 28, 0.9);
    }
    .modal-chips-row {
      display: flex;
      gap: 6px;
      overflow-x: auto;
      padding-bottom: 4px;
    }
    .modal-chip {
      background: var(--input-bg);
      border: 1px solid var(--card-border);
      color: var(--subtext);
      font-size: 12px;
      font-weight: 600;
      padding: 5px 12px;
      border-radius: 20px;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .modal-chip:hover, .modal-chip.active {
      color: var(--accent);
      border-color: var(--accent);
      background: rgba(0, 210, 255, 0.12);
    }
    .modal-body-grid {
      padding: 16px 20px;
      overflow-y: auto;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      gap: 12px;
      flex: 1;
    }
    .voice-hub-card {
      background: var(--input-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 10px;
      transition: all 0.2s;
    }
    .voice-hub-card:hover {
      border-color: var(--accent);
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(0, 210, 255, 0.15);
    }
    .voice-hub-card.selected {
      border-color: var(--accent);
      background: rgba(0, 210, 255, 0.08);
    }

    /* Subtitles Box */
    .subtitles-preview {
      background: #080b10;
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 12px;
      font-family: var(--font-mono);
      font-size: 12px;
      color: #7ee787;
      max-height: 160px;
      overflow-y: auto;
      margin-top: 14px;
      white-space: pre-wrap;
    }
    @media (max-width: 768px) {
      main { padding: 12px; }
      .glass-card { padding: 16px; }
      .tabs-nav { flex-wrap: wrap; gap: 6px; }
      .tab-btn { font-size: 12px; padding: 8px 14px; }
      .controls-grid { grid-template-columns: 1fr; }
      .player-dock { flex-direction: column; align-items: stretch; }
      .player-dock canvas { width: 100%; }
      .player-dock audio { width: 100%; min-width: unset; }
      header .brand h1 { font-size: 15px; }
    }
    @media (max-width: 480px) {
      .presets-row { gap: 6px; }
      .preset-pill { font-size: 11px; padding: 4px 8px; }
      textarea { font-size: 13px; min-height: 120px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="logo-badge"><i class="fa-solid fa-microphone-lines"></i> TTS 2.0</span>
      <h1>Text to Speech Studio</h1>
    </div>
    <div class="status-badge">
      <div class="status-dot"></div>
      <span id="headerStatus">Neural Voices Active (100% Free)</span>
    </div>
  </header>

  <main>
    <div class="tabs-nav">
      <a class="tab-btn" href="/projects">Project Studio</a>
      <button class="tab-btn active" onclick="switchTab('studio', this)"><i class="fa-solid fa-microphone-lines"></i> Single Studio</button>
      <button class="tab-btn" onclick="switchTab('dialogue', this)"><i class="fa-solid fa-comments"></i> Dialogue Lab</button>
      <button class="tab-btn" onclick="switchTab('voices', this)"><i class="fa-solid fa-list-ul"></i> Voice Directory</button>
      <button class="tab-btn" onclick="switchTab('api', this)"><i class="fa-solid fa-code"></i> REST API</button>
    </div>

    <!-- TAB 1: SINGLE STUDIO -->
    <section id="tab-studio" class="tab-content active">
      <div class="glass-card">
        <div class="editor-header">
          <div class="presets-row" id="presetPills">
            <span style="font-size: 12px; color: var(--subtext); font-weight: 600;"><i class="fa-solid fa-sliders"></i> Presets:</span>
            <!-- Populated via JS -->
          </div>
        </div>

        <textarea id="textInput" placeholder="Type or paste your text here to convert into ultra-realistic neural speech..."></textarea>
        
        <div class="metrics-bar">
          <span>Words: <b id="wordCount">0</b></span>
          <span>Characters: <b id="charCount">0</b></span>
          <span>Estimated Duration: <b id="estDuration">~0.0s</b></span>
          <span>Reading Level: <b id="readingGrade">Standard</b></span>
        </div>

        <div class="controls-grid">
          <div class="control-item" style="position: relative; z-index: 50;">
            <label>
              <span>Neural Voice</span>
              <a href="javascript:void(0)" onclick="openVoiceModal()" style="color:var(--accent); font-size:12px; text-decoration:none; font-weight:600; display:inline-flex; align-items:center; gap:4px;"><i class="fa-solid fa-table-cells"></i> Browse All (400+)</a>
            </label>
            <input type="hidden" id="voiceSelect" value="en-US-ChristopherNeural">
            <div class="custom-select-wrapper" id="customVoiceWrapper">
              <div class="custom-select-trigger" id="customVoiceTrigger" onclick="toggleVoiceDropdown()">
                <div class="selected-info" id="customVoiceLabel">
                  <i class="fa-solid fa-microphone" style="color:var(--accent);"></i>
                  <span id="selectedVoiceText">en-US-ChristopherNeural</span>
                </div>
                <i class="fa-solid fa-chevron-down arrow-icon"></i>
              </div>
              <div class="custom-dropdown-menu" id="customVoiceMenu">
                <div class="dropdown-hub-link" onclick="openVoiceModal(); closeVoiceDropdown();">
                  <i class="fa-solid fa-layer-group"></i> <span>Open Full Voice Hub Modal (400+ Voices)</span>
                </div>
                <div class="dropdown-search-box">
                  <i class="fa-solid fa-magnifying-glass"></i>
                  <input type="text" class="dropdown-search-input" id="dropdownSearch" placeholder="Filter voices by name or locale..." oninput="filterDropdownOptions()" onclick="event.stopPropagation()">
                </div>
                <div class="dropdown-options-list" id="customVoiceOptions">
                  <!-- Populated dynamically via JS -->
                </div>
              </div>
            </div>
          </div>
          <div class="control-item">
            <label>Speaking Speed: <span id="rateLabel" style="color:var(--accent);">+0%</span></label>
            <input type="range" id="rateSlider" min="-50" max="100" value="0">
          </div>
          <div class="control-item">
            <label>Pitch Shift: <span id="pitchLabel" style="color:var(--accent-purple);">+0Hz</span></label>
            <input type="range" id="pitchSlider" min="-50" max="50" value="0">
          </div>
        </div>

        <div class="action-row">
          <button id="generateBtn" class="btn-primary" onclick="generateSpeech()">
            <i class="fa-solid fa-bolt"></i> <span>Synthesize Speech & Subtitles</span>
          </button>
          <div id="downloadLinks" style="display: none; gap: 8px;">
            <a id="mp3Download" class="btn-secondary" href="#" download><i class="fa-solid fa-download"></i> Download MP3</a>
            <a id="srtDownload" class="btn-secondary" href="#" download><i class="fa-solid fa-closed-captioning"></i> Download SRT</a>
            <a id="vttDownload" class="btn-secondary" href="#" download><i class="fa-solid fa-file-lines"></i> Download VTT</a>
          </div>
        </div>

        <div id="playerDock" class="player-dock" style="display: none;">
          <canvas id="visualizer" width="240" height="48"></canvas>
          <audio id="audioPlayer" controls></audio>
        </div>

        <div id="subtitlesBox" class="subtitles-preview" style="display: none;"></div>
      </div>
    </section>

    <!-- TAB 2: DIALOGUE LAB -->
    <section id="tab-dialogue" class="tab-content">
      <div class="glass-card">
        <h3 style="font-size: 16px; margin-bottom: 8px; color: var(--accent-purple); display:flex; align-items:center; gap:8px;">
          <i class="fa-solid fa-comments"></i> Multi-Speaker Script Dialogue Studio
        </h3>
        <p style="font-size: 13px; color: var(--subtext); margin-bottom: 14px;">
          Compose full conversational scripts. Each character is rendered with their own voice and stitched into a seamless master track with synchronized subtitles!
        </p>

        <textarea id="dialogueInput" style="height: 220px; font-family: var(--font-mono); font-size: 13px;">[Narrator | en-US-ChristopherNeural]: In a world where AI speech was expensive and slow, a new studio emerged.
[Alice | en-US-JennyNeural]: Wait, Bob! You mean we can build entire podcasts and video dialogues for free?
[Bob | en-US-GuyNeural | rate=+5%]: Exactly Alice! With over 400 neural voices and automatic SRT subtitles.
[Narrator | en-US-ChristopherNeural]: Text to Speech Studio v2.0. Uncapped. Free forever.</textarea>

        <div class="action-row">
          <button id="dialogueBtn" class="btn-primary" style="background: linear-gradient(135deg, #9d4edd, #00d2ff);" onclick="generateDialogue()">
            <i class="fa-solid fa-wand-magic-sparkles"></i> <span>Compile Master Dialogue</span>
          </button>
          <div id="dialogueDownloads" style="display: none; gap: 8px;">
            <a id="dialogueMp3" class="btn-secondary" href="#" download><i class="fa-solid fa-download"></i> Master Audio</a>
            <a id="dialogueSrt" class="btn-secondary" href="#" download><i class="fa-solid fa-closed-captioning"></i> Dialogue SRT</a>
          </div>
        </div>

        <div id="dialoguePlayerDock" class="player-dock" style="display: none;">
          <audio id="dialogueAudio" controls style="width: 100%;"></audio>
        </div>
      </div>
    </section>

    <!-- TAB 3: VOICE DIRECTORY -->
    <section id="tab-voices" class="tab-content">
      <div class="glass-card">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <h3 style="font-size: 16px; display:flex; align-items:center; gap:8px;">
            <i class="fa-solid fa-list-ul"></i> Microsoft Edge Neural Voice Catalog
          </h3>
          <input type="text" id="voiceSearch" placeholder="Search voices by country, language, name..." style="width: 280px;" oninput="filterVoicesTable()">
        </div>

        <div class="voice-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Voice ID</th>
                <th>Locale</th>
                <th>Gender</th>
                <th>Friendly Name</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="voiceTableBody">
              <!-- Populated via JS -->
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- TAB 4: REST API DOCS -->
    <section id="tab-api" class="tab-content">
      <div class="glass-card">
        <h3 style="font-size: 16px; margin-bottom: 8px; color: var(--accent); display:flex; align-items:center; gap:8px;">
          <i class="fa-solid fa-code"></i> Developer REST API Endpoints
        </h3>
        <p style="font-size: 13px; color: var(--subtext); margin-bottom: 16px;">
          Integrate neural TTS directly into your apps, bots, Discord servers, and content automation pipelines.
        </p>

        <div style="display: flex; flex-direction: column; gap: 14px;">
          <div style="background: var(--input-bg); padding: 14px; border-radius: 8px; border: 1px solid var(--card-border);">
            <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 6px;">
              <span style="background: #00d2ff; color:#000; font-weight:700; font-size:11px; padding:2px 6px; border-radius:4px;">POST</span>
              <code style="color:var(--text); font-family:var(--font-mono);">/api/synthesize</code>
            </div>
            <p style="font-size: 12px; color: var(--subtext);">Body: <code>{"text": "Hello world", "voice": "en-US-ChristopherNeural", "rate": "+0%", "subtitles": true}</code></p>
          </div>

          <div style="background: var(--input-bg); padding: 14px; border-radius: 8px; border: 1px solid var(--card-border);">
            <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 6px;">
              <span style="background: #9d4edd; color:#fff; font-weight:700; font-size:11px; padding:2px 6px; border-radius:4px;">POST</span>
              <code style="color:var(--text); font-family:var(--font-mono);">/api/dialogue</code>
            </div>
            <p style="font-size: 12px; color: var(--subtext);">Body: <code>{"script": "[Alice]: Hi!\n[Bob]: Hello!"}</code></p>
          </div>

          <div style="background: var(--input-bg); padding: 14px; border-radius: 8px; border: 1px solid var(--card-border);">
            <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 6px;">
              <span style="background: #00f59b; color:#000; font-weight:700; font-size:11px; padding:2px 6px; border-radius:4px;">GET</span>
              <code style="color:var(--text); font-family:var(--font-mono);">/api/voices</code>
            </div>
            <p style="font-size: 12px; color: var(--subtext);">Returns full array of available neural voices with gender and locale tags.</p>
          </div>
        </div>
      </div>
    </section>

    <!-- VOICE HUB MODAL (Search & Audition 400+ Voices) -->
    <div id="voiceModal" class="modal-overlay" onclick="if(event.target === this) closeVoiceModal();">
      <div class="modal-card">
        <div class="modal-header">
          <h3><i class="fa-solid fa-microphone-lines" style="color:var(--accent);"></i> Microsoft Edge Neural Voice Hub (400+ Voices)</h3>
          <button class="modal-close-btn" onclick="closeVoiceModal()"><i class="fa-solid fa-xmark"></i></button>
        </div>
        <div class="modal-filters">
          <div style="display: flex; gap: 10px; align-items: center;">
            <div style="position: relative; flex: 1;">
              <i class="fa-solid fa-magnifying-glass" style="position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: var(--accent); font-size: 13px;"></i>
              <input type="text" id="modalVoiceSearch" class="dropdown-search-input" placeholder="Search by voice name, language, country code (e.g. US, India, Japan, Spanish)..." oninput="filterModalVoices()">
            </div>
            <select id="modalGenderFilter" onchange="filterModalVoices()" style="width: 140px; padding: 10px 12px;">
              <option value="All">All Genders</option>
              <option value="Female">Female</option>
              <option value="Male">Male</option>
            </select>
          </div>
          <div class="modal-chips-row">
            <button class="modal-chip active" onclick="setModalRegionFilter('All', this)">🌍 All Languages</button>
            <button class="modal-chip" onclick="setModalRegionFilter('en-US', this)">🇺🇸 US English</button>
            <button class="modal-chip" onclick="setModalRegionFilter('en-GB', this)">🇬🇧 UK English</button>
            <button class="modal-chip" onclick="setModalRegionFilter('en-IN', this)">🇮🇳 Indian English</button>
            <button class="modal-chip" onclick="setModalRegionFilter('hi-IN', this)">🇮🇳 Hindi</button>
            <button class="modal-chip" onclick="setModalRegionFilter('ja-JP', this)">🇯🇵 Japanese</button>
            <button class="modal-chip" onclick="setModalRegionFilter('es-', this)">🇪🇸 Spanish</button>
            <button class="modal-chip" onclick="setModalRegionFilter('fr-', this)">🇫🇷 French</button>
            <button class="modal-chip" onclick="setModalRegionFilter('de-', this)">🇩🇪 German</button>
            <button class="modal-chip" onclick="setModalRegionFilter('zh-', this)">🇨🇳 Chinese</button>
            <button class="modal-chip" onclick="setModalRegionFilter('pt-BR', this)">🇧🇷 Portuguese</button>
            <button class="modal-chip" onclick="setModalRegionFilter('ko-KR', this)">🇰🇷 Korean</button>
            <button class="modal-chip" onclick="setModalRegionFilter('it-IT', this)">🇮🇹 Italian</button>
            <button class="modal-chip" onclick="setModalRegionFilter('ar-', this)">🇸🇦 Arabic</button>
          </div>
        </div>
        <div id="modalVoiceGrid" class="modal-body-grid">
          <!-- Populated dynamically via JS -->
        </div>
      </div>
    </div>
  </main>


  <script>
    let allVoices = [];
    let presets = {};
    let audioCtx, analyser, dataArray, canvas, canvasCtx, sourceNode;

    function switchTab(tabId, btn) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
      document.getElementById('tab-' + tabId).classList.add('active');
      if (btn) btn.classList.add('active');
    }

    async function init() {
      setupVisualizer();
      setupTextInput();

      // Fetch presets & voices
      try {
        const [pRes, vRes] = await Promise.all([fetch('/api/presets'), fetch('/api/voices')]);
        presets = await pRes.json();
        allVoices = await vRes.json();

        renderPresets();
        renderVoiceSelect();
        renderVoiceTable(allVoices);
      } catch (err) {
        console.error('Init error:', err);
      }
    }

    function renderPresets() {
      const pillContainer = document.getElementById('presetPills');
      for (const [id, data] of Object.entries(presets)) {
        const btn = document.createElement('button');
        btn.className = 'preset-pill';
        btn.textContent = data.name;
        btn.onclick = () => applyPreset(id);
        pillContainer.appendChild(btn);
      }
    }

    function applyPreset(pid) {
      const p = presets[pid];
      if (!p) return;
      if (p.voice) {
        selectVoice(p.voice);
      }
      if (p.rate) {
        const rVal = parseInt(p.rate) || 0;
        document.getElementById('rateSlider').value = rVal;
        document.getElementById('rateLabel').textContent = (rVal >= 0 ? '+' : '') + rVal + '%';
      }
      if (p.pitch) {
        const pVal = parseInt(p.pitch) || 0;
        document.getElementById('pitchSlider').value = pVal;
        document.getElementById('pitchLabel').textContent = (pVal >= 0 ? '+' : '') + pVal + 'Hz';
      }
      updateMetrics();
    }

    let selectedVoiceId = 'en-US-ChristopherNeural';

    function renderVoiceSelect() {
      const optionsList = document.getElementById('customVoiceOptions');
      if (!optionsList) return;
      optionsList.innerHTML = '';

      allVoices.forEach(v => {
        const isSelected = v.ShortName === selectedVoiceId;
        const opt = document.createElement('div');
        opt.className = `dropdown-option ${isSelected ? 'selected' : ''}`;
        opt.dataset.voice = v.ShortName;
        opt.dataset.locale = v.Locale;
        opt.dataset.gender = v.Gender;
        opt.dataset.friendly = v.FriendlyName;
        opt.onclick = () => selectVoice(v.ShortName);

        const isFem = v.Gender === 'Female';
        opt.innerHTML = `
          <div class="opt-left">
            <i class="fa-solid fa-microphone" style="color:${isFem ? '#ff69b4' : '#00d2ff'}; font-size:12px;"></i>
            <span>${v.ShortName}</span>
          </div>
          <div style="display:flex; align-items:center; gap:6px;">
            <button class="opt-audition-btn" title="Audition voice sample" onclick="event.stopPropagation(); auditionVoice('${v.ShortName}')">
              <i class="fa-solid fa-volume-high"></i>
            </button>
            <span class="opt-badge">${v.Locale}</span>
            <span class="opt-badge" style="color:${isFem ? '#ff69b4' : '#00d2ff'};">${v.Gender}</span>
            ${isSelected ? '<i class="fa-solid fa-check" style="color:var(--accent); font-size:11px; margin-left:4px;"></i>' : ''}
          </div>
        `;
        optionsList.appendChild(opt);
      });

      updateDropdownTriggerLabel();
    }

    // --- Voice Hub Modal (Search & Audition 400+ Voices) ---
    let modalRegionFilter = 'All';

    function openVoiceModal() {
      const modal = document.getElementById('voiceModal');
      if (!modal) return;
      modal.classList.add('active');
      const search = document.getElementById('modalVoiceSearch');
      if (search) {
        search.value = '';
        setTimeout(() => search.focus(), 100);
      }
      renderModalVoiceGrid();
    }

    function closeVoiceModal() {
      const modal = document.getElementById('voiceModal');
      if (modal) modal.classList.remove('active');
    }

    function setModalRegionFilter(region, btn) {
      modalRegionFilter = region;
      document.querySelectorAll('.modal-chip').forEach(c => c.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterModalVoices();
    }

    function renderModalVoiceGrid(voicesToRender = null) {
      const grid = document.getElementById('modalVoiceGrid');
      if (!grid) return;
      grid.innerHTML = '';

      const list = voicesToRender || allVoices;
      list.forEach(v => {
        const isSelected = v.ShortName === selectedVoiceId;
        const isFem = v.Gender === 'Female';
        const card = document.createElement('div');
        card.className = `voice-hub-card ${isSelected ? 'selected' : ''}`;
        card.innerHTML = `
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
              <span style="font-weight:700; font-size:13px; color:var(--text);">${escapeHtml(v.ShortName)}</span>
              <span class="tag-gender ${isFem ? 'tag-female' : 'tag-male'}">${v.Gender}</span>
            </div>
            <div style="font-size:12px; color:var(--subtext); margin-bottom:4px;">${escapeHtml(v.FriendlyName)}</div>
            <span class="opt-badge" style="background:rgba(0,210,255,0.1); color:var(--accent); font-weight:600;">${v.Locale}</span>
          </div>
          <div style="display:flex; gap:6px; margin-top:8px;">
            <button class="btn-secondary" style="flex:1; padding:6px 8px; font-size:12px; justify-content:center;" onclick="auditionVoice('${escapeHtml(v.ShortName)}')">
              <i class="fa-solid fa-volume-high"></i> Audition
            </button>
            <button class="btn-primary" style="flex:1; padding:6px 8px; font-size:12px; justify-content:center;" onclick="useVoiceFromModal('${escapeHtml(v.ShortName)}')">
              <i class="fa-solid fa-check"></i> ${isSelected ? 'Selected' : 'Use Voice'}
            </button>
          </div>
        `;
        grid.appendChild(card);
      });
    }

    function filterModalVoices() {
      const q = (document.getElementById('modalVoiceSearch').value || '').toLowerCase().trim();
      const gender = document.getElementById('modalGenderFilter').value;

      const filtered = allVoices.filter(v => {
        const matchQuery = !q || v.ShortName.toLowerCase().includes(q) || v.Locale.toLowerCase().includes(q) || v.FriendlyName.toLowerCase().includes(q);
        const matchGender = gender === 'All' || v.Gender === gender;
        const matchRegion = modalRegionFilter === 'All' || v.Locale.startsWith(modalRegionFilter) || (modalRegionFilter === 'hi-IN' && v.Locale === 'hi-IN');
        return matchQuery && matchGender && matchRegion;
      });

      renderModalVoiceGrid(filtered);
    }

    function useVoiceFromModal(voiceId) {
      selectVoice(voiceId);
      closeVoiceModal();
    }

    function selectVoice(voiceId) {
      localStorage.setItem('tts_voice', voiceId);
      selectedVoiceId = voiceId;
      document.getElementById('voiceSelect').value = voiceId;
      updateDropdownTriggerLabel();

      // Update active highlight in dropdown
      document.querySelectorAll('#customVoiceOptions .dropdown-option').forEach(opt => {
        if (opt.dataset.voice === voiceId) {
          opt.classList.add('selected');
          if (!opt.querySelector('.fa-check')) {
            const rightDiv = opt.querySelector('div:last-child');
            if (rightDiv) rightDiv.insertAdjacentHTML('beforeend', '<i class="fa-solid fa-check" style="color:var(--accent); font-size:11px; margin-left:4px;"></i>');
          }
        } else {
          opt.classList.remove('selected');
          const checkIcon = opt.querySelector('.fa-check');
          if (checkIcon) checkIcon.remove();
        }
      });

      closeVoiceDropdown();
    }

    function updateDropdownTriggerLabel() {
      const v = allVoices.find(item => item.ShortName === selectedVoiceId);
      const label = document.getElementById('selectedVoiceText');
      if (label) {
        if (v) {
          label.innerHTML = `<b>${v.ShortName}</b> <span style="color:var(--subtext); font-size:12px; margin-left:6px;">(${v.Locale}, ${v.Gender})</span>`;
        } else {
          label.textContent = selectedVoiceId;
        }
      }
    }

    function toggleVoiceDropdown() {
      const wrapper = document.getElementById('customVoiceWrapper');
      const isOpen = wrapper.classList.contains('open');
      if (isOpen) {
        closeVoiceDropdown();
      } else {
        openVoiceDropdown();
      }
    }

    function openVoiceDropdown() {
      const wrapper = document.getElementById('customVoiceWrapper');
      const menu = document.getElementById('customVoiceMenu');
      if (!wrapper || !menu) return;

      // Smart collision detection: if near bottom of screen, drop upwards!
      const rect = wrapper.getBoundingClientRect();
      const menuHeight = 320;
      const spaceBelow = window.innerHeight - rect.bottom;
      const spaceAbove = rect.top;

      if (spaceBelow < menuHeight && spaceAbove > spaceBelow) {
        menu.classList.add('drop-up');
      } else {
        menu.classList.remove('drop-up');
      }

      wrapper.classList.add('open');

      // Scroll into view if needed so it's fully visible
      setTimeout(() => {
        wrapper.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 50);

      const searchInput = document.getElementById('dropdownSearch');
      if (searchInput) {
        searchInput.value = '';
        filterDropdownOptions();
        setTimeout(() => searchInput.focus(), 80);
      }
    }

    function closeVoiceDropdown() {
      const wrapper = document.getElementById('customVoiceWrapper');
      if (wrapper) wrapper.classList.remove('open');
    }

    function filterDropdownOptions() {
      const q = document.getElementById('dropdownSearch').value.toLowerCase().trim();
      const options = document.querySelectorAll('#customVoiceOptions .dropdown-option');
      options.forEach(opt => {
        const vName = (opt.dataset.voice || '').toLowerCase();
        const vLoc = (opt.dataset.locale || '').toLowerCase();
        const vFriendly = (opt.dataset.friendly || '').toLowerCase();
        if (!q || vName.includes(q) || vLoc.includes(q) || vFriendly.includes(q)) {
          opt.style.display = 'flex';
        } else {
          opt.style.display = 'none';
        }
      });
    }

    // Close custom dropdown when clicking outside or pressing Escape
    document.addEventListener('click', (e) => {
      const wrapper = document.getElementById('customVoiceWrapper');
      if (wrapper && !wrapper.contains(e.target)) {
        closeVoiceDropdown();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeVoiceDropdown();
      }
    });


    function escapeHtml(str) {
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }

    function renderVoiceTable(voices) {
      const tbody = document.getElementById('voiceTableBody');
      tbody.innerHTML = '';
      voices.slice(0, 150).forEach(v => {
        const tr = document.createElement('tr');
        const isFem = v.Gender === 'Female';
        tr.innerHTML = `
          <td style="font-family:var(--font-mono); font-weight:600; color:var(--accent);">${escapeHtml(v.ShortName)}</td>
          <td>${escapeHtml(v.Locale)}</td>
          <td><span class="tag-gender ${isFem ? 'tag-female' : 'tag-male'}">${escapeHtml(v.Gender)}</span></td>
          <td style="color:var(--subtext);">${escapeHtml(v.FriendlyName)}</td>
          <td>
            <div style="display:flex; gap:6px;">
              <button class="btn-secondary" style="padding:4px 10px; font-size:11px;" onclick="auditionVoice('${escapeHtml(v.ShortName)}')"><i class="fa-solid fa-volume-high"></i> Audition</button>
              <button class="btn-secondary" style="padding:4px 10px; font-size:11px; color:var(--accent); border-color:rgba(0,210,255,0.3);" onclick="useVoiceInStudio('${escapeHtml(v.ShortName)}')"><i class="fa-solid fa-check"></i> Use</button>
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function useVoiceInStudio(voiceId) {
      selectVoice(voiceId);
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
      document.getElementById('tab-studio').classList.add('active');
      const studioTabBtn = document.querySelector('.tab-btn');
      if (studioTabBtn) studioTabBtn.classList.add('active');
    }

    function filterVoicesTable() {
      const q = document.getElementById('voiceSearch').value.toLowerCase().trim();
      const filtered = allVoices.filter(v => 
        v.ShortName.toLowerCase().includes(q) ||
        v.Locale.toLowerCase().includes(q) ||
        v.FriendlyName.toLowerCase().includes(q)
      );
      renderVoiceTable(filtered);
    }

    function setupTextInput() {
      const textInput = document.getElementById('textInput');
      const rateSlider = document.getElementById('rateSlider');
      const pitchSlider = document.getElementById('pitchSlider');

      textInput.addEventListener('input', updateMetrics);
      rateSlider.addEventListener('input', (e) => {
        const val = e.target.value;
        document.getElementById('rateLabel').textContent = (val >= 0 ? '+' : '') + val + '%';
        updateMetrics();
      });
      pitchSlider.addEventListener('input', (e) => {
        const val = e.target.value;
        document.getElementById('pitchLabel').textContent = (val >= 0 ? '+' : '') + val + 'Hz';
      });
    }

    function updateMetrics() {
      const text = document.getElementById('textInput').value.trim();
      const chars = text.length;
      const words = text ? text.split(/\s+/).length : 0;
      const rateVal = parseInt(document.getElementById('rateSlider').value) || 0;
      const rateMod = 1.0 + (rateVal / 100.0);
      const duration = words > 0 ? ((words / (150 * rateMod)) * 60).toFixed(1) : '0.0';

      document.getElementById('charCount').textContent = chars;
      document.getElementById('wordCount').textContent = words;
      document.getElementById('estDuration').textContent = `~${duration}s`;
    }

    async function generateSpeech() {
      const text = document.getElementById('textInput').value.trim();
      if (!text) return alert('Please enter some text to synthesize.');

      const voice = document.getElementById('voiceSelect').value;
      const rate = (parseInt(document.getElementById('rateSlider').value) >= 0 ? '+' : '') + document.getElementById('rateSlider').value + '%';
      const pitch = (parseInt(document.getElementById('pitchSlider').value) >= 0 ? '+' : '') + document.getElementById('pitchSlider').value + 'Hz';

      const btn = document.getElementById('generateBtn');
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> <span>Synthesizing Neural Audio...</span>';

      try {
        const res = await fetch('/api/synthesize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, voice, rate, pitch, subtitles: true })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Synthesis error');

        // Play audio
        const audio = document.getElementById('audioPlayer');
        audio.src = data.audio_url;
        document.getElementById('playerDock').style.display = 'flex';
        audio.play();

        // Download links
        document.getElementById('downloadLinks').style.display = 'flex';
        document.getElementById('mp3Download').href = data.audio_url;
        if (data.srt_url) {
          document.getElementById('srtDownload').href = data.srt_url;
          document.getElementById('srtDownload').style.display = 'inline-flex';
        }
        if (data.vtt_url) {
          document.getElementById('vttDownload').href = data.vtt_url;
          document.getElementById('vttDownload').style.display = 'inline-flex';
        }

        // Show subtitles
        if (data.srt_text) {
          const sBox = document.getElementById('subtitlesBox');
          sBox.style.display = 'block';
          sBox.textContent = data.srt_text;
        }

      } catch (err) {
        alert('Synthesis failed: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-bolt"></i> <span>Synthesize Speech & Subtitles</span>';
      }
    }

    async function generateDialogue() {
      const script = document.getElementById('dialogueInput').value.trim();
      if (!script) return alert('Please enter a dialogue script.');

      const btn = document.getElementById('dialogueBtn');
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> <span>Compiling Dialogue Track...</span>';

      try {
        const res = await fetch('/api/dialogue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ script })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Dialogue error');

        const audio = document.getElementById('dialogueAudio');
        audio.src = data.audio_url;
        document.getElementById('dialoguePlayerDock').style.display = 'flex';
        audio.play();

        document.getElementById('dialogueDownloads').style.display = 'flex';
        document.getElementById('dialogueMp3').href = data.audio_url;
        if (data.srt_url) {
          document.getElementById('dialogueSrt').href = data.srt_url;
        }
      } catch (err) {
        alert('Dialogue generation failed: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Compile Master Dialogue</span>';
      }
    }

    async function auditionVoice(voiceId) {
      const input = document.getElementById('textInput');
      const sample = input.value.slice(input.selectionStart, input.selectionEnd) || input.value.trim().slice(0, 320);
      try {
        const res = await fetch('/api/synthesize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: sample || `This is a sample of ${voiceId}.`,
            voice: voiceId
          })
        });
        const data = await res.json();
        if (data.audio_url) {
          const audio = new Audio(data.audio_url);
          audio.play();
        }
      } catch (err) {
        alert('Audition error: ' + err.message);
      }
    }

    let isVisualizerRunning = false;

    function setupVisualizer() {
      canvas = document.getElementById('visualizer');
      if (!canvas) return;
      canvasCtx = canvas.getContext('2d');
      const audio = document.getElementById('audioPlayer');

      audio.onplay = () => {
        if (!audioCtx) {
          try {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            analyser = audioCtx.createAnalyser();
            analyser.fftSize = 64;
            sourceNode = audioCtx.createMediaElementSource(audio);
            sourceNode.connect(analyser);
            analyser.connect(audioCtx.destination);
            dataArray = new Uint8Array(analyser.frequencyBinCount);
            if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
          } catch(e) {
            console.warn('AudioContext init:', e);
          }
        }
        if (!isVisualizerRunning) {
          isVisualizerRunning = true;
          drawWaveform();
        }
      };

      audio.onpause = () => { isVisualizerRunning = false; };
      audio.onended = () => { isVisualizerRunning = false; };
    }

    function drawWaveform() {
      const audio = document.getElementById('audioPlayer');
      if (!isVisualizerRunning || !analyser || (audio && (audio.paused || audio.ended))) {
        isVisualizerRunning = false;
        if (canvasCtx && canvas) {
          canvasCtx.fillStyle = '#080b10';
          canvasCtx.fillRect(0, 0, canvas.width, canvas.height);
        }
        return;
      }

      requestAnimationFrame(drawWaveform);
      analyser.getByteFrequencyData(dataArray);

      canvasCtx.fillStyle = '#080b10';
      canvasCtx.fillRect(0, 0, canvas.width, canvas.height);

      const barWidth = (canvas.width / dataArray.length) * 2;
      let x = 0;

      for (let i = 0; i < dataArray.length; i++) {
        const barHeight = (dataArray[i] / 255) * (canvas.height - 4);
        canvasCtx.fillStyle = i < 16 ? '#00d2ff' : '#9d4edd';
        canvasCtx.fillRect(x, canvas.height - barHeight, barWidth - 1, barHeight);
        x += barWidth + 1;
      }
    }

    // --- Dynamic State Auto-Save & Auto-Restore (localStorage) ---
    function setupStatePersistence() {
      const textInput = document.getElementById('textInput');
      const dialogueInput = document.getElementById('dialogueInput');
      const rateSlider = document.getElementById('rateSlider');
      const pitchSlider = document.getElementById('pitchSlider');

      // Auto-save on change
      textInput.addEventListener('input', () => localStorage.setItem('tts_text', textInput.value));
      if (dialogueInput) dialogueInput.addEventListener('input', () => localStorage.setItem('tts_dialogue', dialogueInput.value));
      rateSlider.addEventListener('change', () => localStorage.setItem('tts_rate', rateSlider.value));
      pitchSlider.addEventListener('change', () => localStorage.setItem('tts_pitch', pitchSlider.value));

      // Restore saved values
      const savedText = localStorage.getItem('tts_text');
      if (savedText && textInput) {
        textInput.value = savedText;
      }
      const savedDialogue = localStorage.getItem('tts_dialogue');
      if (savedDialogue && dialogueInput) {
        dialogueInput.value = savedDialogue;
      }
      const savedRate = localStorage.getItem('tts_rate');
      if (savedRate && rateSlider) {
        rateSlider.value = savedRate;
        document.getElementById('rateLabel').textContent = (parseInt(savedRate) >= 0 ? '+' : '') + savedRate + '%';
      }
      const savedPitch = localStorage.getItem('tts_pitch');
      if (savedPitch && pitchSlider) {
        pitchSlider.value = savedPitch;
        document.getElementById('pitchLabel').textContent = (parseInt(savedPitch) >= 0 ? '+' : '') + savedPitch + 'Hz';
      }
      const savedVoice = localStorage.getItem('tts_voice');
      if (savedVoice) {
        selectedVoiceId = savedVoice;
        document.getElementById('voiceSelect').value = savedVoice;
      }
    }

    // --- Dynamic Live Hot-Reload Engine ---
    function setupLiveReload() {
      let currentVersion = null;
      let isChecking = false;

      async function checkVersion() {
        if (isChecking) return;
        isChecking = true;
        try {
          const res = await fetch('/api/version?t=' + Date.now(), { cache: 'no-store' });
          if (res.ok) {
            const data = await res.json();
            if (currentVersion === null) {
              currentVersion = data.version;
            } else if (data.version && data.version !== currentVersion) {
              console.log('[Hot-Reload] Changes detected! Reloading page...');
              window.location.reload();
              return;
            }
          }
        } catch (err) {
          // Server may be restarting, will retry on next tick
        } finally {
          isChecking = false;
          setTimeout(checkVersion, 800);
        }
      }

      setTimeout(checkVersion, 800);
    }

    window.onload = () => {
      init();
      setupStatePersistence();
      setupLiveReload();
    };
  </script>
</body>
</html>
"""


class WebStudioHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Web Studio & REST API."""

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        assets = {"/projects": ("projects.html", "text/html; charset=utf-8"),
                  "/projects.js": ("projects.js", "text/javascript; charset=utf-8")}
        if path in assets:
            name, mime = assets[path]
            content = Path(__file__).with_name(name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if path == "/api/project/offline":
            root, model = studio_audio.echon_paths()
            self._send_json({"runtime": (root / "src" / "inference.py").is_file(),
                             "checkpoint": model.is_file(), "path": str(root)})
            return

        if path in ("/", "/index.html"):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if path in ("/favicon.ico", "/favicon.svg"):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(FAVICON_SVG.encode("utf-8"))
            return

        if path == "/api/version":
            self._send_json({"version": _CURRENT_BUILD_VERSION})
            return

        if path == "/api/voices":
            try:
                voices = engine.list_voices_sync()
                self._send_json(voices)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/presets":
            presets = engine.get_all_presets()
            self._send_json(presets)
            return

        if path.startswith("/static/"):
            fname = path[len("/static/"):]
            fpath = STATIC_OUTPUT_DIR / fname
            resolved = fpath.resolve()
            if not resolved.is_relative_to(STATIC_OUTPUT_DIR.resolve()):
                self.send_error(HTTPStatus.FORBIDDEN, "Access denied")
                return
            if fpath.is_file():
                ctype, _ = mimetypes.guess_type(str(fpath))
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", ctype or "application/octet-stream")
                self.send_header("Content-Length", str(fpath.stat().st_size))
                self.send_header("Cache-Control", "no-cache, must-revalidate")
                self.end_headers()
                with open(fpath, "rb") as f:
                    shutil.copyfileobj(f, self.wfile, length=256 * 1024)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        if path == "/api/project/open":
            try:
                with tempfile.TemporaryFile() as source:
                    remaining = length
                    while remaining > 0:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("Incomplete project upload.")
                        source.write(chunk)
                        remaining -= len(chunk)
                    source.seek(0)
                    project = studio_project.restore(source, STATIC_OUTPUT_DIR)
                self._send_json(project)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}

        if path.startswith("/api/project/"):
            try:
                if path == "/api/project/take":
                    self._send_json(studio_project.render(engine, STATIC_OUTPUT_DIR, data))
                elif path == "/api/project/parse":
                    from dataclasses import asdict
                    lines = []
                    for line in engine.parse_dialogue_script(data["text"]):
                        for phrase in studio_audio.phrases(line.text):
                            lines.append({**asdict(line), "text": phrase})
                    self._send_json(lines)
                elif path == "/api/project/save":
                    name = uuid.uuid4().hex + ".ttsp"
                    studio_project.archive(data, STATIC_OUTPUT_DIR, STATIC_OUTPUT_DIR / name)
                    self._send_json({"url": "/static/" + name})
                elif path == "/api/project/mix":
                    name = uuid.uuid4().hex
                    dest = STATIC_OUTPUT_DIR / name
                    metadata = studio_project.mix(engine, data["project"], STATIC_OUTPUT_DIR, dest, data.get("stems", False))
                    if data.get("stems"):
                        with ZipFile(dest / "mix.zip", "w") as bundle:
                            for file in dest.iterdir():
                                if file.suffix != ".zip":
                                    bundle.write(file, file.name)
                    self._send_json({**metadata, "url": "/static/" + name + "/"})
                else:
                    self._send_json({"error": "Unknown project action."}, status=404)
            except (ConnectionError, TimeoutError) as exc:
                self._send_json({"error": str(exc)}, status=503)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=400)
            return

        if path == "/api/synthesize":
            text = data.get("text", "").strip()
            if not text:
                self._send_json({"success": False, "error": "Text is required."}, status=400)
                return

            voice = data.get("voice", DEFAULT_VOICE)
            rate = data.get("rate", "+0%")
            pitch = data.get("pitch", "+0Hz")
            subtitles = bool(data.get("subtitles", True))

            out_filename = engine.generate_auto_filename(text)
            out_path = STATIC_OUTPUT_DIR / out_filename

            try:
                res = engine.synthesize_sync(
                    text=text,
                    voice=voice,
                    output_path=str(out_path),
                    rate=rate,
                    pitch=pitch,
                    generate_subtitles=subtitles,
                )
                self._send_json(
                    {
                        "success": True,
                        "audio_url": f"/static/{Path(res.audio_path).name}",
                        "srt_url": f"/static/{Path(res.srt_path).name}" if res.srt_path else None,
                        "vtt_url": f"/static/{Path(res.vtt_path).name}" if res.vtt_path else None,
                        "srt_text": res.srt_subtitles,
                        "duration_sec": res.duration_estimate_sec,
                        "words": res.word_count,
                    }
                )
            except Exception as exc:
                self._send_json({"success": False, "error": str(exc)}, status=500)
            return

        if path == "/api/dialogue":
            script = data.get("script", "").strip()
            if not script:
                self._send_json({"success": False, "error": "Script is required."}, status=400)
                return

            out_filename = f"dialogue_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
            out_path = STATIC_OUTPUT_DIR / out_filename

            try:
                res = asyncio.run(
                    engine.synthesize_dialogue(
                        script_text=script,
                        output_path=str(out_path),
                        generate_subtitles=True,
                    )
                )
                self._send_json(
                    {
                        "success": True,
                        "audio_url": f"/static/{Path(res.audio_path).name}",
                        "srt_url": f"/static/{Path(res.srt_path).name}" if res.srt_path else None,
                        "vtt_url": f"/static/{Path(res.vtt_path).name}" if res.vtt_path else None,
                        "duration_sec": res.duration_estimate_sec,
                        "words": res.word_count,
                    }
                )
            except Exception as exc:
                self._send_json({"success": False, "error": str(exc)}, status=500)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "API route not found")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def log_message(self, format: str, *args: Any) -> None:
        # Keep console output neat
        pass


class SilentThreadingHTTPServer(ThreadingHTTPServer):
    """Threading HTTPServer that gracefully ignores client disconnect errors."""
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc_type, _, _ = sys.exc_info()
        if exc_type and issubclass(exc_type, (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError)):
            return  # Normal client disconnect (e.g. browser tab closed or refreshed)
        super().handle_error(request, client_address)


def run_web_studio(port: int = 7860, open_browser: bool = True) -> None:
    """Launch the Web Studio HTTP server with Hot-Reload watcher and auto port discovery."""
    # Start dynamic file watcher for automatic hot-reloads
    start_file_watcher()

    httpd = None
    active_port = port
    for p in range(port, port + 20):
        try:
            httpd = SilentThreadingHTTPServer(("", p), WebStudioHandler)
            active_port = p
            break
        except OSError:
            continue

    if not httpd:
        print(f"[Error] Could not bind to any port in range {port}-{port+20}")
        return

    url = f"http://localhost:{active_port}"

    is_hot_reload = os.environ.get("TTS_HOT_RELOAD") == "1"
    if not is_hot_reload:
        print("=" * 65)
        print(f"🎙️  Text to Speech Web Studio v2.0 is LIVE!")
        print(f"🔗  URL: {url}")
        print(f"⚡  Hot-Reload: Active (Dynamic file watch enabled)")
        print(f"📁  Outputs: {STATIC_OUTPUT_DIR.resolve()}")
        print("=" * 65)
    else:
        print(f"⚡  [Hot-Reload] Server refreshed and live on {url}")

    if open_browser and not is_hot_reload:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Web Studio...")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7860
    run_web_studio(port=port)


