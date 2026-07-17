# Xiao An Screen Tracker (v0.1)

A local-only Windows tool that records **what you work on** and **how actively**,
not just how long. Everything stays in a local SQLite file — nothing is uploaded.

## What it captures

| Layer | Data | Privacy tier |
|-------|------|--------------|
| L1 | foreground app + window title, idle seconds | L1 (default) |
| L1 | keystroke / click / scroll counts, mouse travel (counts only, never key values) | all tiers |
| L2 | browser domain (Chrome/Edge/Brave/Vivaldi) via UI Automation | L1 = domain, L2 = full url |
| — | rule-based category (coding / writing / meeting / browsing / …) | all tiers |

Privacy tiers (`config.json` → `privacy_level`):
- **L0** app + category only (no titles, no domains)
- **L1** + window title + browser domain  ← default
- **L2** + full browser url/

Apps matching `blocklist_apps` (password managers, banking) never have their
title/url stored, at any tier.

## Usage

```bash
python run.py init                 # (optional) write config.json to tweak settings
python run.py track                # start recording; Ctrl+C to stop
python run.py report               # today's summary in the console
python run.py report --hours 3     # last 3 hours
python run.py report --html out.html   # rich HTML report (bars + timeline)
```

## Requirements

Python 3.10+, Windows. Packages: `pywin32 psutil pynput uiautomation` (Pillow/Flask
optional, reserved for later). Install: `pip install pywin32 psutil pynput uiautomation`.

## Notes / limits

- Browser domain reading depends on UI Automation exposing the address bar; if a
  browser is not focused it simply records app+title (no domain), never errors.
- Keystroke capture stores **counts only** — it is not a keylogger and records no
  key identities or text.
- Roadmap: Chrome extension for exact URL/tab/dwell-time; optional push of a
  summary schema to the Xiao An base station (OpenClaw) over LAN.
