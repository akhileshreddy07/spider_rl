# SPIDER-SENSE ARENA: Autonomous Combat Simulation

A cinematic, Spider-Man-inspired competitive battle simulator and replay engine for the **CSES Arcade RL Hackathon (NIT Warangal)** Buckshot Roulette competition.

---

## Visual Direction & Architecture

- **Futuristic Spider-Man Aesthetic & Atmosphere**:
  - **New York City at Night Background**: Deep midnight-navy palette (`#070B18`, `#101729`) with atmospheric ambient spotlights (Electric-Blue `#168BFF` top-right, Spider-Red `#F3263E` bottom-left), multi-layered vector Manhattan skyline with illuminated spires (Chrysler / One WTC style) and blinking red beacons, large glowing corner spider-webs, and subtle floating particles.
  - **Header HUD**: Angular geometric spider emblem, glowing live simulation telemetry badge, turn pill, and AAA-game menu buttons (`REPLAYS`, `NEW BATTLE`, `LOAD LOG`, `SFX`).
  - **Central Duel Arena**: Cinematic arena panel with holographic perspective floor grid, central glowing "VS" emblem badge with electric arcs, tactical combat shotgun stand with live/blank muzzle flashes, chamber magazine rack, and **Spider-Sense Bayesian Probability Radar** (`P(Live)` vs `P(Blank)`).
  - **Player & Opponent HUD Cards**: High-impact digital health readouts, smooth gradient-fill health integrity meters, health segment pips, status condition badges (`ALIVE`, `ELIMINATED`, `SKIPPED`), active-turn glowing neon aura, and tactical inventory slots for modules (`Juice`, `Coffee`, `Mag Glass`, `Floatie`, `Hand Saw`).
  - **Original Vector SVG Avatars**: Red & blue suited Spider-Sense superhero with angular expressive white eyes, chest insignia, and spider-sense tingle arcs; contrasting cybernetic rogue combat android opponent with cyan optic visor and thrusters.
  - **Futuristic Combat Feed**: Chronological event cards with contextual icons (🎯, ⚡, 📦, ⚠️), turn tags, readable descriptions, and round dividers.
  - **Command Replay Console**: Docked media deck with circular Spider-Red play/pause button, step controls, timeline scrubber with hotkey badges (`SPACE`, `◀ / ▶`, `HOME / END`), and speed multipliers (`0.5x` - `8.0x`).

- **Strict Separation of Deliverables**:
  - All visualizer files reside inside `visualizer/`.
  - The bot submission files (`submissions/spider_sense/bot.py`, `params.json`, `spider_sense.zip`) remain 100% clean, intact, and unmodified.
  - Zero external npm or pip dependencies required.

---

## How to Launch

### Method 1: Local HTTP Server (Recommended)

Start the Python HTTP server from the repository root:
```bash
python3 visualizer/server.py --port 8080
```
Open your browser to:
[http://localhost:8080](http://localhost:8080)
*(If port 8080 is in use, the server automatically selects the next available port, e.g. 8081)*.

Features available via server:
1. **Replay Library**: Browse and replay over 1,690+ historical tournament matches from `out*/logs/` and `visualizer/logs/`.
2. **New Battle**: Trigger on-demand matches between `spider_sense` and baseline bots using the official local simulator engine.
3. **Log Inspector**: Live parsing and animated replay of real `.jsonl` simulator logs.

### Method 2: Standalone Static HTML

You can also directly open the file in any browser without a running server:
```bash
open visualizer/index.html
```
Includes bundled sample match data and drag-and-drop support for any `.jsonl` log file.

---

## Acceptance & Testing Verification

1. **Validation**: `python3 -m engine.validate submissions/spider_sense/ --backend local --games 5` passes with exit code 0 (`OK`).
2. **Integrity**: `submissions/spider_sense/bot.py` and `params.json` match original hashes and remain untouched.
3. **Log Fidelity**: Replays actual decision records from `engine.run_match` step-by-step with real health and turn updates.
