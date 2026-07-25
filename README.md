# 3D Optimizer — mesh remesher / LOD generator

**The problem:** AI generation services (Meshy, Tripo, Rodin, Hunyuan3D) and 3D scans
produce high-poly meshes. Studios and game engines (Unreal/Unity) need **multiple levels
of detail** (LOD): high → mid → low. Doing this by hand is slow.

**Core (MVP):** one high-poly model in → several LOD levels out automatically,
**preserving UVs and materials**, exported to FBX (primary), GLB, GLTF, OBJ.

**Extra feature (optional):** baking high-poly detail into a **normal map** applied to
the simplified mesh — the visual detail is preserved despite the low poly count.

The gap this fills: there's no simple automated tool for turning "dirty" AI-generated
meshes into clean LOD chains (Simplygon/InstaLOD are expensive studio tools, Quad
Remesher is a manual plugin).

## Two simplification engines
| method | UV/textures | topology | use case |
|---|---|---|---|
| `collapse` (default) | preserved | triangles | **LOD chains**, fast |
| `planar` | preserved | removes flat faces | hard-surface |
| `quad` (QuadriFlow) | destroyed (needs `--bake`) | clean quads | final/hero model |

Core engine is **Blender** running headless via its Python API (`bpy`). Free, no licenses.

## Installation
1. Python 3.x (any recent version).
2. Blender 4.2 LTS: `winget install BlenderFoundation.Blender`
   or https://www.blender.org/download/lts/

## Usage
```powershell
# 3 levels (50%, 25%, 10%) exported to FBX:
python run.py input/model.glb

# custom levels, labels and formats:
python run.py input/model.glb --levels 0.5,0.2,0.05 --names high,mid,low --formats fbx,glb

# target triangle counts instead of ratios:
python run.py input/model.fbx --levels 20000,5000,1000

# clean quad retopology + normal+AO baking:
python run.py input/model.glb --method quad --bake --bake-ao
```
`--levels`: a value `<=1` means a polygon ratio, `>1` means a target polygon count.
Results land in `output/<name>/<name>_<label>.<format>` plus a before/after report.

## Knowledge base
[knowledge/](knowledge/00_overview.md) — expert reference (topology, retopology, UV,
baking, bpy automation). Drives the parameters and architecture. Read it before making changes.

## Roadmap
- [x] Stage 0: scaffolding, Blender engine (5.1.2), CLI
- [x] Stage 1: **remesher core** — multi-LOD, collapse/planar/quad, FBX/GLB/GLTF/OBJ
- [x] Stage 2: smoke test passed (20480→10240→4096→1024, UVs preserved, normal baked), dev env,
  knowledge base
- [ ] Stage 3: run on a REAL model, tune parameters to its topology
- [ ] Stage 4: presets (Unreal LOD `_LOD0..` / Unity / web / 3D printing), UV quality preservation
- [ ] Stage 5: baking as a standalone module (cage, DX/GL normal flip, curvature/diffuse/ID, supersampling)
- [ ] Stage 6: `--clean` preprocessing, voxel mode (watertight for printing), folder batch mode
- [ ] Stage 7: GUI / Blender add-on
- [ ] Stage 8: generation API integration (image → model → LOD)

## Environment
- Blender 5.1.2: `C:\Program Files\Blender Foundation\Blender 5.1\` (run.py finds it automatically)
- Python venv: `.venv/` (trimesh, numpy, pygltflib, Pillow) — for validation outside Blender
- Smoke test: `blender --background --python blender_scripts/make_test_model.py` → `python run.py input/test_highpoly.glb ...`

## Structure
```
3d_optimizer/
  run.py                    # CLI: locates Blender, runs it
  requirements.txt  .venv/  # dev validation tools
  blender_scripts/
    optimize.py             # core: LOD generation inside Blender
    make_test_model.py      # test high-poly model generator
  tools/
    inspect_mesh.py         # mesh inspection via trimesh (outside Blender)
  knowledge/                # expert knowledge base (00..06)
  input/  output/
  app/                       # standalone GUI (Tkinter) - see app/README.md
  addon/                     # Blender add-on - see addon/INSTALL.md
```
