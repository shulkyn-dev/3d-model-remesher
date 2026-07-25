"""Быстрая инспекция меша БЕЗ Blender (через trimesh).
Запуск:  .venv/Scripts/python tools/inspect_mesh.py output/test_highpoly/test_highpoly_low.glb
Печатает: вершины, грани, watertight, наличие UV, габариты.
"""
import sys
import trimesh


def inspect(path):
    scene = trimesh.load(path, force="scene")
    print(f"== {path} ==")
    total_v = total_f = 0
    for name, geom in scene.geometry.items():
        v, f = len(geom.vertices), len(geom.faces)
        total_v += v
        total_f += f
        uv = getattr(geom.visual, "uv", None)
        has_uv = uv is not None and len(uv) > 0
        print(f"  [{name}] verts={v} faces={f} watertight={geom.is_watertight} "
              f"uv={'yes' if has_uv else 'NO'}")
    print(f"  ИТОГО: verts={total_v} faces={total_f}")
    print(f"  габариты: {scene.bounds.tolist() if scene.bounds is not None else '?'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("укажи путь к .glb/.obj/.fbx/.stl")
    for p in sys.argv[1:]:
        inspect(p)
