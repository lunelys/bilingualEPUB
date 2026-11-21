# -*- coding: utf-8 -*-
"""
bilingualEPUB Studio — Local Web UI Server (v5)
===============================================
Updates in v5:
- Symmetric 'EN ➔ DE' and 'DE ➔ DE+' badges.
- E-Ink preview contains strictly authentic book text; explanatory caption moved outside below.
- Selecting B1 / B2 / C1 dynamically updates all UI descriptions & chapter preview labels,
  and is piped to BOTH English and German backend converters.
- Slider for 'Words per .txt List' (10..100, default 50).
- Slider for 'Thematic .txt Lists Generated' (1..8, default 4) with live 'Max X Lists × Y Words' badge.
"""

import json
import os
import subprocess
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from bilingual_epub import (
    ensure_folders,
    clean_book_slug,
    load_known_words,
    transform_en_to_progressive_de,
    transform_de_to_b1_assisted,
)

WORKSPACE = Path(__file__).parent.resolve()
FOLDERS = ensure_folders(WORKSPACE)
PORT = 8765


HTML_UI = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>bilingualEPUB — E-Reader Language Companion</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<style>
  :root {
    --bg-deep: #07070b;
    --bg-card: #101018;
    --bg-card-hover: #151521;
    --bg-input: #0b0b12;
    --purple-primary: #7c3aed;
    --purple-bright: #9333ea;
    --purple-glow: #a855f7;
    --purple-dim: rgba(124, 58, 237, 0.16);
    --border-subtle: rgba(139, 92, 246, 0.22);
    --border-bright: rgba(168, 85, 247, 0.55);
    --text-main: #f3f4f6;
    --text-muted: #9ca3af;
    --text-dim: #6b7280;
    --success: #10b981;
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  body {
    background-color: var(--bg-deep);
    background-image:
      radial-gradient(circle at 15% 10%, rgba(124, 58, 237, 0.12), transparent 35%),
      radial-gradient(circle at 85% 85%, rgba(147, 51, 234, 0.10), transparent 40%);
    color: var(--text-main);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    min-height: 100vh;
    padding: 28px 32px 48px;
    line-height: 1.5;
  }

  .container {
    max-width: 1260px;
    margin: 0 auto;
  }

  /* Header */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 22px;
    margin-bottom: 24px;
    border-bottom: 1px solid var(--border-subtle);
    flex-wrap: wrap;
    gap: 16px;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .logo-badge {
    width: 42px;
    height: 42px;
    border-radius: 11px;
    background: linear-gradient(135deg, var(--purple-primary), var(--purple-bright));
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 1.15rem;
    box-shadow: 0 0 22px rgba(124, 58, 237, 0.45);
    letter-spacing: -0.5px;
  }

  .brand h1 {
    font-size: 1.38rem;
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .brand h1 span {
    color: var(--purple-glow);
  }

  .brand p {
    font-size: 0.84rem;
    color: var(--text-muted);
  }

  /* Global Top Bar */
  .global-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 15px 20px;
    margin-bottom: 26px;
    flex-wrap: wrap;
    gap: 20px;
  }

  .level-group {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .level-label {
    font-size: 0.84rem;
    font-weight: 600;
    color: var(--text-muted);
    margin-right: 4px;
  }

  .level-pill {
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
    color: var(--text-muted);
    padding: 7px 14px;
    border-radius: 8px;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.18s ease;
  }

  .level-pill:hover {
    border-color: var(--purple-glow);
    color: var(--text-main);
  }

  .level-pill.active {
    background: linear-gradient(135deg, var(--purple-primary), var(--purple-bright));
    color: #fff;
    border-color: transparent;
    box-shadow: 0 0 14px rgba(124, 58, 237, 0.4);
  }

  .global-slider-group {
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--bg-input);
    border: 1px solid rgba(255, 255, 255, 0.06);
    padding: 7px 14px;
    border-radius: 10px;
  }

  .toggles-group {
    display: flex;
    align-items: center;
    gap: 18px;
    flex-wrap: wrap;
  }

  .toggle-item {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 0.82rem;
    color: var(--text-muted);
    cursor: pointer;
    user-select: none;
  }

  .toggle-item input {
    accent-color: var(--purple-primary);
    width: 15px;
    height: 15px;
    cursor: pointer;
  }

  .btn-secondary {
    background: var(--purple-dim);
    border: 1px solid var(--border-subtle);
    color: #d8b4fe;
    padding: 7px 14px;
    border-radius: 8px;
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.18s ease;
  }

  .btn-secondary:hover {
    background: rgba(124, 58, 237, 0.28);
    border-color: var(--purple-glow);
    color: #fff;
  }

  /* Two-Column Grid */
  .dual-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
  }

  @media (max-width: 940px) {
    .dual-grid {
      grid-template-columns: 1fr;
    }
  }

  .panel {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 16px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 18px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
    transition: border-color 0.2s ease;
  }

  .panel:hover {
    border-color: rgba(139, 92, 246, 0.36);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
  }

  .panel-title {
    font-size: 1.12rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .lang-pill {
    background: linear-gradient(135deg, rgba(124, 58, 237, 0.25), rgba(147, 51, 234, 0.25));
    border: 1px solid var(--border-bright);
    color: #e9d5ff;
    font-size: 0.78rem;
    font-weight: 800;
    padding: 3px 10px;
    border-radius: 7px;
    letter-spacing: 0.03em;
  }

  .panel-subtitle {
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-top: 4px;
  }

  .tag-badge {
    background: var(--purple-dim);
    color: #c4b5fd;
    border: 1px solid var(--border-subtle);
    font-size: 0.73rem;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 999px;
    white-space: nowrap;
  }

  /* Dropzone */
  .dropzone {
    border: 1.5px dashed rgba(139, 92, 246, 0.38);
    background: var(--bg-input);
    border-radius: 12px;
    padding: 20px 16px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
  }

  .dropzone:hover, .dropzone.dragover {
    border-color: var(--purple-glow);
    background: rgba(124, 58, 237, 0.08);
    box-shadow: inset 0 0 18px rgba(124, 58, 237, 0.12);
  }

  .dropzone input[type="file"] {
    display: none;
  }

  .dropzone-icon {
    font-size: 1.45rem;
    margin-bottom: 5px;
    color: var(--purple-glow);
  }

  .dropzone-title {
    font-size: 0.87rem;
    font-weight: 600;
    color: var(--text-main);
  }

  .dropzone-hint {
    font-size: 0.75rem;
    color: var(--text-dim);
    margin-top: 2px;
  }

  /* Book Queue List */
  .queue-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.78rem;
    color: var(--text-muted);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .book-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 155px;
    overflow-y: auto;
  }

  .book-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--bg-input);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 9px;
    padding: 8px 12px;
    font-size: 0.82rem;
  }

  .book-name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 82%;
    color: #e5e7eb;
  }

  .book-remove {
    background: none;
    border: none;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 0.9rem;
    padding: 2px 6px;
    border-radius: 4px;
  }

  .book-remove:hover {
    color: #f87171;
    background: rgba(248, 113, 113, 0.1);
  }

  /* Sliders & Settings */
  .settings-box {
    background: var(--bg-input);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 12px;
    padding: 15px 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .slider-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .slider-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.82rem;
  }

  .slider-top span:first-child {
    color: var(--text-muted);
    font-weight: 500;
  }

  .slider-val {
    color: #d8b4fe;
    font-weight: 700;
    background: var(--purple-dim);
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.77rem;
  }

  input[type="range"] {
    -webkit-appearance: none;
    width: 100%;
    height: 6px;
    background: #1f1f2e;
    border-radius: 4px;
    outline: none;
  }

  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--purple-glow);
    cursor: pointer;
    box-shadow: 0 0 10px rgba(168, 85, 247, 0.65);
  }

  /* Convert Primary Button */
  .btn-convert {
    background: linear-gradient(135deg, var(--purple-primary), var(--purple-bright));
    color: #fff;
    border: none;
    border-radius: 11px;
    padding: 13px 18px;
    font-size: 0.91rem;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 4px 18px rgba(124, 58, 237, 0.35);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .btn-convert:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 24px rgba(147, 51, 234, 0.55);
  }

  .btn-convert:disabled {
    opacity: 0.5;
    cursor: wait;
    transform: none;
  }

  /* Results Section */
  .results-area {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .result-card {
    background: rgba(16, 185, 129, 0.06);
    border: 1px solid rgba(16, 185, 129, 0.28);
    border-radius: 10px;
    padding: 12px 14px;
    font-size: 0.81rem;
  }

  .result-title {
    font-weight: 700;
    color: #6ee7b7;
    margin-bottom: 4px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .result-stats {
    color: var(--text-muted);
    margin-bottom: 8px;
  }

  .txt-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .txt-pill {
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
    color: #c4b5fd;
    padding: 3px 9px;
    border-radius: 6px;
    font-size: 0.74rem;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .txt-pill:hover {
    background: var(--purple-primary);
    color: #fff;
  }

  /* Live E-Ink Preview Footer */
  .preview-panel {
    margin-top: 26px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 16px;
    padding: 20px 24px;
  }

  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    flex-wrap: wrap;
    gap: 8px;
  }

  .preview-header h3 {
    font-size: 0.92rem;
    font-weight: 700;
    color: #d8b4fe;
  }

  .eink-page {
    background: #f4f2ed;
    color: #1a1a1a;
    border-radius: 10px;
    padding: 18px 22px;
    font-family: Georgia, "Times New Roman", serif;
    font-size: 0.96rem;
    line-height: 1.65;
    box-shadow: inset 0 0 12px rgba(0,0,0,0.12);
  }

  .eink-box {
    border: 1px solid #888;
    border-radius: 4px;
    padding: 8px 12px;
    margin-bottom: 12px;
    font-size: 0.8rem;
    background: #eae8e3;
    font-family: Georgia, serif;
  }

  .eink-hint {
    font-size: 0.72em;
    font-style: italic;
    font-weight: 300;
    color: #777777;
  }

  .preview-footer-note {
    margin-top: 10px;
    font-size: 0.78rem;
    color: var(--text-muted);
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
  }

  /* Modal for viewing .txt lists or Known Words */
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(4px);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 20px;
  }

  .modal-backdrop.open {
    display: flex;
  }

  .modal {
    background: var(--bg-card);
    border: 1px solid var(--border-bright);
    border-radius: 14px;
    max-width: 680px;
    width: 100%;
    padding: 22px;
    box-shadow: 0 20px 50px rgba(0,0,0,0.8);
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .modal-header h3 {
    font-size: 1.02rem;
    color: #e9d5ff;
  }

  .modal pre, .modal textarea {
    background: var(--bg-input);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 14px;
    color: #e5e7eb;
    font-family: "JetBrains Mono", Consolas, monospace;
    font-size: 0.8rem;
    max-height: 400px;
    overflow-y: auto;
    white-space: pre-wrap;
    width: 100%;
  }

  .modal textarea {
    min-height: 220px;
    outline: none;
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <div class="logo-badge" style="background:none; box-shadow: 0 0 22px rgba(124, 58, 237, 0.45); padding:0; overflow:hidden;">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="44" height="44" fill="none">
          <defs>
            <linearGradient id="bgG" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#18122B"/><stop offset="100%" stop-color="#0B0813"/>
            </linearGradient>
            <linearGradient id="bkG" x1="12" y1="10" x2="52" y2="54" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#9333EA"/><stop offset="100%" stop-color="#6D28D9"/>
            </linearGradient>
            <linearGradient id="rnG" x1="24" y1="18" x2="40" y2="42" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#F3E8FF"/><stop offset="100%" stop-color="#C084FC"/>
            </linearGradient>
          </defs>
          <rect width="64" height="64" rx="14" fill="url(#bgG)" stroke="#7C3AED" stroke-width="2" stroke-opacity="0.55"/>
          <path d="M16 14C16 11.79 17.79 10 20 10H46C48.21 10 50 11.79 50 14V46C50 48.21 48.21 50 46 50H20C17.79 50 16 48.21 16 46V14Z" fill="url(#bkG)" stroke="#C084FC" stroke-width="1.8"/>
          <path d="M21 10V46" stroke="#3B0764" stroke-width="2" stroke-opacity="0.55"/>
          <path d="M16 47C16 44.79 17.79 43 20 43H49V50C49 51.66 47.66 53 46 53H20C17.79 53 16 51.21 16 49V47Z" fill="#1E1B2E" stroke="#C084FC" stroke-width="1.8"/>
          <path d="M20 48H45" stroke="#A855F7" stroke-width="1.5" stroke-linecap="round" stroke-opacity="0.6"/>
          <path d="M35 17L29 24L35 31L41 24L35 17Z" stroke="url(#rnG)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M35 31L28 38M35 31L42 38" stroke="url(#rnG)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="35" cy="24" r="1.8" fill="#F3E8FF"/>
        </svg>
      </div>
      <div>
        <h1>bilingual<span>EPUB</span></h1>
        <p>Progressive German Weave &amp; Assisted German EPUB Generator for All E-Readers + Custom .txt Stack Builder</p>
      </div>
    </div>
    <div style="display:flex; gap:10px;">
      <button class="btn-secondary" onclick="openKnownWordsModal()">🧠 Words I Already Know</button>
      <button class="btn-secondary" onclick="openFolder('root')">📂 Open Workspace Folder</button>
    </div>
  </header>

  <!-- Global Settings Bar -->
  <div class="global-bar">
    <div class="level-group">
      <span class="level-label">Your German Level:</span>
      <button class="level-pill" data-level="B1" onclick="setLevel('B1')">B1 · Intermediate</button>
      <button class="level-pill active" data-level="B2" onclick="setLevel('B2')">B2 · Upper-Int</button>
      <button class="level-pill" data-level="C1" onclick="setLevel('C1')">C1 · Advanced</button>
    </div>

    <div class="global-slider-group">
      <label class="toggle-item">
        <input type="checkbox" id="chkTxtLists" checked onchange="onSliderChange()" />
        <span>Generate .txt Lists:</span>
      </label>
      <input type="range" id="rngWordsPerTxt" min="10" max="100" step="5" value="50" style="width:110px;" oninput="onSliderChange()" />
      <span class="slider-val"><span id="valWordsPerTxt">50</span> words / list</span>
    </div>

    <div class="toggles-group">
      <label class="toggle-item">
        <input type="checkbox" id="chkChapterBox" checked onchange="updatePreview()" />
        Top-of-Chapter Vocab Box
      </label>
      <label class="toggle-item">
        <input type="checkbox" id="chkAnki" />
        Also Export Anki TSV
      </label>
    </div>
  </div>

  <!-- Split 2-Column Panels -->
  <div class="dual-grid">

    <!-- LEFT PANEL: ENGLISH BOOKS (EN -> DE) -->
    <div class="panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">
            <span class="lang-pill">EN ➔ DE</span>
            <span>English Books · Progressive Weave</span>
          </div>
          <div class="panel-subtitle">
            Gradually weaves permanent <b class="dyn-level-text">B2/C1</b> German words into English EPUBs &amp; unlocks your e-reader's German dictionary.
          </div>
        </div>
        <span class="tag-badge">Mode 1</span>
      </div>

      <label class="dropzone" id="dropEn">
        <input type="file" id="fileEn" multiple accept=".epub" onchange="uploadFiles('en', this.files)" />
        <div class="dropzone-icon">📥</div>
        <div class="dropzone-title">Drop English .epub books here or click to add</div>
        <div class="dropzone-hint">Saved automatically to Input_English_Books/</div>
      </label>

      <div class="queue-header">
        <span>Input_English_Books (<span id="countEn">0</span>)</span>
        <button class="btn-secondary" style="padding:3px 9px; font-size:0.74rem;" onclick="openFolder('out_en')">📂 Output Folder</button>
      </div>
      <div class="book-list" id="listEn"></div>

      <div class="settings-box">
        <div class="slider-row">
          <div class="slider-top">
            <span>New <span class="dyn-level-text">B2/C1</span> German Words per Chapter (Fits 1 Page)</span>
            <span class="slider-val"><span id="valWordsPerCh">10</span> words / ch</span>
          </div>
          <input type="range" id="rngWordsPerCh" min="5" max="30" step="1" value="10" oninput="onSliderChange()" />
        </div>

        <div class="slider-row">
          <div class="slider-top">
            <span>Fade Out Inline [meaning] Hint After</span>
            <span class="slider-val"><span id="valEnFade">2</span>× encounters</span>
          </div>
          <input type="range" id="rngEnFade" min="1" max="5" step="1" value="2" oninput="onSliderChange()" />
        </div>
      </div>

      <button class="btn-convert" id="btnConvertEn" onclick="convertBooks('en')">
        ⚡ Convert English Books + Build <span id="btnEnTxtSize">50</span>-Word .txt Stacks
      </button>

      <div class="results-area" id="resultsEn"></div>
    </div>

    <!-- RIGHT PANEL: GERMAN BOOKS (DE -> DE+) -->
    <div class="panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">
            <span class="lang-pill">DE ➔ DE+</span>
            <span>German Books · Assisted Reader</span>
          </div>
          <div class="panel-subtitle">
            Keeps 100% original German text, adding whisper-thin inline English hints on tough <b class="dyn-level-text">B2/C1</b> words.
          </div>
        </div>
        <span class="tag-badge">Mode 2</span>
      </div>

      <label class="dropzone" id="dropDe">
        <input type="file" id="fileDe" multiple accept=".epub" onchange="uploadFiles('de', this.files)" />
        <div class="dropzone-icon">📥</div>
        <div class="dropzone-title">Drop German .epub books here or click to add</div>
        <div class="dropzone-hint">Saved automatically to Input_German_Books/</div>
      </label>

      <div class="queue-header">
        <span>Input_German_Books (<span id="countDe">0</span>)</span>
        <button class="btn-secondary" style="padding:3px 9px; font-size:0.74rem;" onclick="openFolder('out_de')">📂 Output Folder</button>
      </div>
      <div class="book-list" id="listDe"></div>

      <div class="settings-box">
        <div class="slider-row">
          <div class="slider-top">
            <span>Fade Out Inline [meaning] Hint After</span>
            <span class="slider-val"><span id="valDeFade">3</span>× encounters</span>
          </div>
          <input type="range" id="rngDeFade" min="1" max="5" step="1" value="3" oninput="onSliderChange()" />
        </div>

        <div class="slider-row">
          <div class="slider-top">
            <span>Thematic .txt Lists Generated</span>
            <span class="slider-val">Max <span id="valDeListsCount">4</span> Lists × <span id="valDeWordsPerList">50</span> Words</span>
          </div>
          <input type="range" id="rngDeListsCount" min="1" max="8" step="1" value="4" oninput="onSliderChange()" />
        </div>
      </div>

      <button class="btn-convert" id="btnConvertDe" onclick="convertBooks('de')">
        ⚡ Convert German Books + Build <span id="btnDeListsNum">4</span> Thematic .txt Lists
      </button>

      <div class="results-area" id="resultsDe"></div>
    </div>

  </div>

  <!-- Live E-Ink Preview Panel -->
  <div class="preview-panel">
    <div class="preview-header">
      <h3>👁️ Live E-Reader E-Ink Page Preview (<span class="dyn-level-text">B2/C1</span> Filter Active)</h3>
      <span style="font-size:0.78rem; color:var(--text-muted);">
        Normal font weight for German words · Faded 0.72em italic hints · Auto-fades after <span id="prevFadeNum">2</span>×
      </span>
    </div>
    <div class="eink-page">
      <div class="eink-box" id="prevChapterBox">
        <b>🇩🇪 Kapitel 1: +<span id="prevBoxCount">10</span> neue <span class="dyn-level-text">B2/C1</span>-Wörter</b><br/>
        <b>die Klinge</b> (<i>blade</i>) · <b>der Blick</b> (<i>gaze</i>) · <b>die Lichtung</b> (<i>clearing</i>) · <b>das Raubtier</b> (<i>predator</i>) · <b>die Dunkelheit</b> (<i>darkness</i>) ...
      </div>
      <div>
        We rode through pure, unceasing, suffocating Dunkelheit<span class="eink-hint" id="prevHint1"> [darkness]</span>.
        The ancient pines towered above the narrow trail, their twisted branches swallowing the last light of the moon in perpetual Dunkelheit<span class="eink-hint" id="prevHint2"> [darkness]</span>.
        When the hunter finally reached the edge of the Lichtung<span class="eink-hint"> [clearing]</span>, he drew his Klinge<span class="eink-hint"> [blade]</span> and watched the Raubtier<span class="eink-hint"> [predator]</span> vanish silently back into the Dunkelheit<span class="eink-hint" id="prevHint3" style="display:none;"> [darkness]</span>.
      </div>
    </div>
    <div class="preview-footer-note">
      <span>💡 Notice how on the 3rd occurrence of <b>Dunkelheit</b> in the excerpt above, the inline <i>[darkness]</i> hint automatically disappears once you reach your fade-out threshold.</span>
      <span>.txt export format: <code>die Klinge : blade</code></span>
    </div>
  </div>
</div>

<!-- Modal for viewing .txt file content -->
<div class="modal-backdrop" id="txtModal" onclick="if(event.target===this) closeTxtModal()">
  <div class="modal">
    <div class="modal-header">
      <h3 id="txtModalTitle">Vocabulary List</h3>
      <button class="btn-secondary" onclick="closeTxtModal()">✕ Close</button>
    </div>
    <pre id="txtModalContent"></pre>
  </div>
</div>

<!-- Modal for Known Words -->
<div class="modal-backdrop" id="knownModal" onclick="if(event.target===this) closeKnownModal()">
  <div class="modal">
    <div class="modal-header">
      <h3>🧠 Words I Already Know (Skipped in All Future Books)</h3>
      <button class="btn-secondary" onclick="closeKnownModal()">✕ Close</button>
    </div>
    <p style="font-size:0.82rem; color:var(--text-muted);">
      Enter one word per line (German or English). These words will never be translated or occupy learning slots:
    </p>
    <textarea id="knownTextarea"></textarea>
    <div style="display:flex; justify-content:flex-end; gap:10px;">
      <button class="btn-convert" style="padding:9px 18px;" onclick="saveKnownWords()">💾 Save Known Words</button>
    </div>
  </div>
</div>

<script>
  let currentLevel = 'B2';

  const LEVEL_LABELS = {
    'B1': 'B1/B2/C1',
    'B2': 'B2/C1',
    'C1': 'C1'
  };

  function setLevel(lvl) {
    currentLevel = lvl;
    document.querySelectorAll('.level-pill').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.level === lvl);
    });
    const label = LEVEL_LABELS[lvl] || 'B2/C1';
    document.querySelectorAll('.dyn-level-text').forEach(el => {
      el.textContent = label;
    });
  }

  function onSliderChange() {
    const w = parseInt(document.getElementById('rngWordsPerCh').value, 10);
    const ef = parseInt(document.getElementById('rngEnFade').value, 10);
    const df = parseInt(document.getElementById('rngDeFade').value, 10);
    const txtSize = parseInt(document.getElementById('rngWordsPerTxt').value, 10);
    const deLists = parseInt(document.getElementById('rngDeListsCount').value, 10);

    document.getElementById('valWordsPerCh').textContent = w;
    document.getElementById('valEnFade').textContent = ef;
    document.getElementById('valDeFade').textContent = df;
    document.getElementById('valWordsPerTxt').textContent = txtSize;
    document.getElementById('valDeListsCount').textContent = deLists;
    document.getElementById('valDeWordsPerList').textContent = txtSize;

    document.getElementById('btnEnTxtSize').textContent = txtSize;
    document.getElementById('btnDeListsNum').textContent = deLists;

    document.getElementById('prevBoxCount').textContent = w;
    document.getElementById('prevFadeNum').textContent = ef;

    // Dynamically toggle the 3 occurrences of Dunkelheit [darkness] in the E-Ink preview!
    document.getElementById('prevHint1').style.display = ef >= 1 ? 'inline' : 'none';
    document.getElementById('prevHint2').style.display = ef >= 2 ? 'inline' : 'none';
    document.getElementById('prevHint3').style.display = ef >= 3 ? 'inline' : 'none';
  }

  function updatePreview() {
    const showBox = document.getElementById('chkChapterBox').checked;
    document.getElementById('prevChapterBox').style.display = showBox ? 'block' : 'none';
  }

  async function refreshState() {
    const res = await fetch('/api/state');
    const data = await res.json();
    renderBookList('en', data.en_books);
    renderBookList('de', data.de_books);
  }

  function renderBookList(lang, books) {
    const container = document.getElementById(lang === 'en' ? 'listEn' : 'listDe');
    const counter = document.getElementById(lang === 'en' ? 'countEn' : 'countDe');
    counter.textContent = books.length;
    if (!books.length) {
      container.innerHTML = `<div style="font-size:0.8rem; color:var(--text-dim); padding:8px;">No books in folder yet. Drop .epub files above!</div>`;
      return;
    }
    container.innerHTML = books.map(name => `
      <div class="book-item">
        <span class="book-name" title="${name}">📘 ${name}</span>
        <button class="book-remove" title="Remove from input folder" onclick="removeBook('${lang}', '${encodeURIComponent(name)}')">✕</button>
      </div>
    `).join('');
  }

  async function uploadFiles(lang, fileList) {
    for (const file of fileList) {
      if (!file.name.toLowerCase().endsWith('.epub')) continue;
      const buf = await file.arrayBuffer();
      await fetch(`/api/upload?lang=${lang}&name=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        body: buf
      });
    }
    refreshState();
  }

  async function removeBook(lang, encodedName) {
    await fetch(`/api/remove?lang=${lang}&name=${encodedName}`, { method: 'POST' });
    refreshState();
  }

  async function convertBooks(lang) {
    const btn = document.getElementById(lang === 'en' ? 'btnConvertEn' : 'btnConvertDe');
    const resBox = document.getElementById(lang === 'en' ? 'resultsEn' : 'resultsDe');
    const origText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '⏳ Converting EPUBs &amp; Generating .txt Lists...';

    const payload = {
      lang,
      level: currentLevel,
      words_per_chapter: parseInt(document.getElementById('rngWordsPerCh').value, 10),
      en_fade: parseInt(document.getElementById('rngEnFade').value, 10),
      de_fade: parseInt(document.getElementById('rngDeFade').value, 10),
      words_per_txt_list: parseInt(document.getElementById('rngWordsPerTxt').value, 10),
      max_thematic_lists: parseInt(document.getElementById('rngDeListsCount').value, 10),
      show_chapter_box: document.getElementById('chkChapterBox').checked,
      export_txt_lists: document.getElementById('chkTxtLists').checked,
      export_anki: document.getElementById('chkAnki').checked,
    };

    try {
      const res = await fetch('/api/convert', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      resBox.innerHTML = data.results.map(r => `
        <div class="result-card">
          <div class="result-title">
            <span>✅ ${r.book_slug} (${r.chapters} chapters)</span>
            <span>${r.unlocked_words} ${r.level} words</span>
          </div>
          <div class="result-stats">
            EPUB saved + ${r.txt_files.length} vocabulary .txt files generated (click to preview):
          </div>
          <div class="txt-pills">
            ${r.txt_files.map(tf => `
              <span class="txt-pill" onclick="viewTxtFile('${lang}', '${r.book_slug}', '${tf}')">📄 ${tf}</span>
            `).join('')}
          </div>
        </div>
      `).join('');
    } finally {
      btn.disabled = false;
      btn.innerHTML = origText;
      onSliderChange();
    }
  }

  async function viewTxtFile(lang, slug, filename) {
    const res = await fetch(`/api/txt?lang=${lang}&slug=${encodeURIComponent(slug)}&file=${encodeURIComponent(filename)}`);
    const text = await res.text();
    document.getElementById('txtModalTitle').textContent = `📄 ${filename}`;
    document.getElementById('txtModalContent').textContent = text;
    document.getElementById('txtModal').classList.add('open');
  }

  function closeTxtModal() {
    document.getElementById('txtModal').classList.remove('open');
  }

  async function openKnownWordsModal() {
    const res = await fetch('/api/known_words');
    const text = await res.text();
    document.getElementById('knownTextarea').value = text;
    document.getElementById('knownModal').classList.add('open');
  }

  function closeKnownModal() {
    document.getElementById('knownModal').classList.remove('open');
  }

  async function saveKnownWords() {
    const text = document.getElementById('knownTextarea').value;
    await fetch('/api/known_words', { method: 'POST', body: text });
    closeKnownModal();
  }

  async function openFolder(which) {
    await fetch(`/api/open_folder?which=${which}`, { method: 'POST' });
  }

  // Drag and drop wiring
  [['dropEn', 'en'], ['dropDe', 'de']].forEach(([id, lang]) => {
    const el = document.getElementById(id);
    el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('dragover'); });
    el.addEventListener('dragleave', () => el.classList.remove('dragover'));
    el.addEventListener('drop', e => {
      e.preventDefault();
      el.classList.remove('dragover');
      if (e.dataTransfer.files.length) uploadFiles(lang, e.dataTransfer.files);
    });
  });

  refreshState();
</script>
</body>
</html>
"""


class StudioHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, text, content_type="text/plain; charset=utf-8", status=200):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_text(HTML_UI, "text/html; charset=utf-8")
        elif parsed.path in ("/favicon.svg", "/favicon.ico"):
            fav_path = WORKSPACE / "favicon.svg"
            if fav_path.exists():
                self._send_text(fav_path.read_text(encoding="utf-8"), "image/svg+xml; charset=utf-8")
            else:
                self._send_text("Not found", status=404)
        elif parsed.path == "/api/state":
            en_books = sorted([p.name for p in FOLDERS["in_en"].glob("*.epub")])
            de_books = sorted([p.name for p in FOLDERS["in_de"].glob("*.epub")])
            self._send_json({"en_books": en_books, "de_books": de_books})
        elif parsed.path == "/api/txt":
            qs = parse_qs(parsed.query)
            lang = qs.get("lang", ["en"])[0]
            slug = qs.get("slug", [""])[0]
            fname = Path(qs.get("file", [""])[0]).name
            base_out = FOLDERS["out_en"] if lang == "en" else FOLDERS["out_de"]
            target = base_out / f"{slug}_Vocab_Lists" / fname
            if target.exists():
                self._send_text(target.read_text(encoding="utf-8", errors="replace"))
            else:
                self._send_text("File not found.", status=404)
        elif parsed.path == "/api/known_words":
            load_known_words(WORKSPACE)
            kw_path = WORKSPACE / "known_words.txt"
            self._send_text(kw_path.read_text(encoding="utf-8", errors="replace"))
        else:
            self._send_text("Not found", status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b""

        if parsed.path == "/api/upload":
            lang = qs.get("lang", ["en"])[0]
            name = Path(qs.get("name", ["book.epub"])[0]).name
            folder = FOLDERS["in_en"] if lang == "en" else FOLDERS["in_de"]
            (folder / name).write_bytes(body)
            self._send_json({"ok": True})

        elif parsed.path == "/api/remove":
            lang = qs.get("lang", ["en"])[0]
            name = Path(qs.get("name", [""])[0]).name
            folder = FOLDERS["in_en"] if lang == "en" else FOLDERS["in_de"]
            target = folder / name
            if target.exists():
                target.unlink()
            self._send_json({"ok": True})

        elif parsed.path == "/api/known_words":
            (WORKSPACE / "known_words.txt").write_text(body.decode("utf-8", errors="replace"), encoding="utf-8")
            self._send_json({"ok": True})

        elif parsed.path == "/api/open_folder":
            which = qs.get("which", ["root"])[0]
            target = FOLDERS.get(which, WORKSPACE)
            if os.name == "nt":
                subprocess.Popen(["explorer", str(target)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            self._send_json({"ok": True})

        elif parsed.path == "/api/convert":
            cfg = json.loads(body.decode("utf-8"))
            lang = cfg.get("lang", "en")
            user_level = cfg.get("level", "B2")
            words_per_txt_list = int(cfg.get("words_per_txt_list", 50))
            max_thematic_lists = int(cfg.get("max_thematic_lists", 4))
            known = load_known_words(WORKSPACE)
            results = []

            if lang == "en":
                for epub in sorted(FOLDERS["in_en"].glob("*.epub")):
                    slug = clean_book_slug(epub.name)
                    out_epub = FOLDERS["out_en"] / f"{slug}_Progressive_DE.epub"
                    res = transform_en_to_progressive_de(
                        input_epub=epub,
                        output_epub=out_epub,
                        words_per_chapter=cfg.get("words_per_chapter", 10),
                        hint_max_encounters=cfg.get("en_fade", 2),
                        user_level=user_level,
                        show_chapter_box=cfg.get("show_chapter_box", True),
                        export_txt_lists=cfg.get("export_txt_lists", True),
                        words_per_txt_list=words_per_txt_list,
                        export_anki=cfg.get("export_anki", False),
                        known_words=known,
                    )
                    results.append(res)
            else:
                for epub in sorted(FOLDERS["in_de"].glob("*.epub")):
                    slug = clean_book_slug(epub.name)
                    out_epub = FOLDERS["out_de"] / f"{slug}_{user_level.upper()}_Assisted.epub"
                    res = transform_de_to_b1_assisted(
                        input_epub=epub,
                        output_epub=out_epub,
                        max_hints_per_word=cfg.get("de_fade", 3),
                        user_level=user_level,
                        show_chapter_box=cfg.get("show_chapter_box", True),
                        export_txt_lists=cfg.get("export_txt_lists", True),
                        words_per_txt_list=words_per_txt_list,
                        max_thematic_lists=max_thematic_lists,
                        export_anki=cfg.get("export_anki", False),
                        known_words=known,
                    )
                    results.append(res)

            self._send_json({"ok": True, "results": results})
        else:
            self._send_text("Not found", status=404)


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}"
    print("=" * 64)
    print(f" bilingualEPUB is running at: {url}")
    print("=" * 64)
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    server = HTTPServer(("127.0.0.1", PORT), StudioHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down bilingualEPUB.")
