# Installing the "3D Retopo Optimizer" add-on (Blender 5.1)

## Installation (one-time)
1. Open Blender.
2. **Edit → Preferences → Add-ons**.
3. Top-right dropdown **⌄ → Install from Disk…**
4. Select `addon/retopo_optimizer.py`.
5. Enable the checkbox next to "3D Retopo Optimizer".

## How to use it
1. Import a model: **File → Import → glTF / FBX / OBJ** (your AI-generated model from Meshy/Tripo).
2. Select it (click).
3. In the 3D viewport press **N** → the **"Retopo"** tab on the right.
4. Configure:
   - **Method**: `Quad (retopology)` — main mode, clean quads.
   - **Target polygons**: how many you want in the result (e.g. 5000).
   - **Symmetry** (for Quad): clean symmetric mesh — for characters/props.
   - **Preserve hard edges** (for Quad): on for hard-surface/CAD (mechanical, architecture),
     off for organic shapes. Sharp edge angle is adjustable.
   - **Preserve form (Shrinkwrap)**: pulls the result back onto the original — silhouette
     doesn't "melt". Recommended to keep on.
   - **Bake Normal map**: bakes original detail into a texture (recommended on).
5. Click **Retopologize Selected**.
6. After a few seconds a new object `<name>_retopo` appears — it gets selected,
   the original is hidden. Rotate around, check the topology (Wireframe in the viewport header / Z).

## What you'll see
- A low-poly model with a clean quad mesh.
- A normal map with the original's detail wired into the material.
- Stats (triangles, % quads, time) shown at the bottom in the Info line.

## Getting the result (Export)
6. With `<name>_retopo` still selected, click **Export result** on the panel.
7. Choose a folder and name; the extension sets the format: `.fbx` / `.glb` / `.gltf` / `.obj`.
8. Textures (normal/AO) are saved alongside and embedded in FBX/GLB — the model is ready for an engine.

## If the result isn't quad
The Info line will show `collapse(fallback)` — meaning QuadriFlow couldn't handle this model.
Try lowering **Advanced → QuadriFlow input cap**, or cleaning up the model beforehand.

## Getting the original back
The original isn't deleted, just hidden. **Alt+H** in the viewport shows hidden objects.
Or enable "Keep original visible" before running.
