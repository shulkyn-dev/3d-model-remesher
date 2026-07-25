# "3D Retopo Optimizer" mini-app (standalone)

A separate window. Blender runs **hidden in the background** as the engine — no need to open Blender itself.

## Architecture (like Quad Remesher)
```
gui_app.py (Tkinter window)
     │  launches in the background:
     ▼
blender --background --python engine_headless.py   ← hidden engine
     │  (same logic as the Blender add-on)
     ▼
finished models + textures in the output folder
```
`engine_headless.py` reuses the core logic from `../addon/retopo_optimizer.py` — one
engine, two frontends (window and add-on), same results either way.

## Running it
- **Double-click** `run_app.bat`
- or from a terminal: `python app/gui_app.py`

Requires Blender to be installed (auto-detected; otherwise set `BLENDER_PATH`).

## How to use it
1. **Browse…** — pick a model (.glb/.gltf/.fbx/.obj/.stl).
2. The output folder is filled in automatically (can be changed).
3. Configure: method (QUAD/COLLAPSE/PLANAR), target polygons, symmetry, shape preservation,
   sharp edges, normal/AO baking, export formats.
   - **Weld distance, %** — light merge of nearby vertices, closes gaps (0 = off, start at 0.05).
   - **Export scale** — if the model comes out 100x too big in your importer, set 0.01.
4. Click **▶ Optimize**. The "Process" panel shows a live log.
5. Once done ("✓ Done") — **Open result folder**.

## Requirements
- Python 3.x (Tkinter included)
- Blender 4.2+/5.x
