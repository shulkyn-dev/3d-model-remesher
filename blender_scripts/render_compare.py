"""Рендерит сравнительные превью для оценки качества ретопологии.
Запуск:
    blender --background --python render_compare.py -- \
        --high input/test_suzanne.glb \
        --low  output/test_suzanne/test_suzanne_retopo.glb \
        --outdir output/test_suzanne/preview

Делает 4 кадра: high (shaded), low (shaded), low (wireframe), high (wireframe).
Так видно: держится ли силуэт и какая топология (квады / поток рёбер).
"""
import bpy
import sys
import os
import math


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--high", required=True)
    p.add_argument("--low", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--res", type=int, default=900)
    return p.parse_args(a)


def clean():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for b in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.objects):
        for it in list(b):
            try:
                b.remove(it)
            except Exception:
                pass


def imp(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def setup_scene():
    scn = bpy.context.scene
    # Cycles надёжно рендерит в --background (EEVEE требует GPU-контекст)
    scn.render.engine = "CYCLES"
    scn.cycles.samples = 16
    try:
        scn.cycles.device = "CPU"
    except Exception:
        pass
    scn.render.film_transparent = True
    scn.render.image_settings.file_format = "PNG"
    # свет
    light_data = bpy.data.lights.new("key", type="SUN")
    light_data.energy = 3
    light = bpy.data.objects.new("key", light_data)
    bpy.context.collection.objects.link(light)
    light.rotation_euler = (math.radians(50), 0, math.radians(45))
    # камера
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    scn.camera = cam
    cam.location = (0, -3.2, 0.6)
    cam.rotation_euler = (math.radians(82), 0, 0)


def frame_object(obj):
    # нормируем размер/позицию, чтобы влезал в кадр
    obj.location = (0, 0, 0)
    mx = max(obj.dimensions)
    if mx > 0:
        s = 1.6 / mx
        obj.scale = (s, s, s)
    bpy.context.view_layer.update()


def render(path, res):
    scn = bpy.context.scene
    scn.render.resolution_x = res
    scn.render.resolution_y = res
    scn.render.filepath = os.path.normpath(path)
    bpy.ops.render.render(write_still=True)
    ok = os.path.isfile(os.path.normpath(path))
    print(f"[render] {'OK' if ok else 'НЕ ЗАПИСАН'} {path}")


def show_wire(obj, on):
    obj.show_wire = on
    obj.show_all_edges = on
    # для рендера wireframe-наглядности добавим Wireframe-модификатор поверх
    name = "WIRE_PREVIEW"
    existing = obj.modifiers.get(name)
    if on and not existing:
        m = obj.modifiers.new(name, type="WIREFRAME")
        m.thickness = 0.004
    elif not on and existing:
        obj.modifiers.remove(existing)


def main():
    a = args()
    os.makedirs(a.outdir, exist_ok=True)

    # HIGH shaded
    clean(); setup_scene()
    h = imp(a.high); frame_object(h)
    render(os.path.join(a.outdir, "1_high_shaded.png"), a.res)

    # LOW shaded
    clean(); setup_scene()
    lo = imp(a.low); frame_object(lo)
    render(os.path.join(a.outdir, "2_low_shaded.png"), a.res)

    # LOW wireframe (топология!)
    clean(); setup_scene()
    lo = imp(a.low); frame_object(lo); show_wire(lo, True)
    render(os.path.join(a.outdir, "3_low_wireframe.png"), a.res)

    print("[render] готово. Папка:", a.outdir)


if __name__ == "__main__":
    main()
