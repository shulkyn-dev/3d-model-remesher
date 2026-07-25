"""
engine_headless.py — СКРЫТЫЙ ДВИЖОК. Запускается внутри Blender в фоне приложением (gui_app.py).
Переиспользует проверенную логику аддона (тот же движок, что и в Blender-аддоне).

Вызов:
    blender --background --python engine_headless.py -- \
        --input model.glb --outdir out --basename model \
        --method QUAD --target 5000 --formats fbx,glb \
        --symmetry 1 --preserve-form 1 --bake 1 --bake-ao 0 --bake-size 2048 \
        --mark-sharp 0 --sharp-angle 40
"""
import bpy
import sys
import os
import argparse
import importlib.util

# --- подключаем ядро из файла аддона (единый источник логики) ---
HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.normpath(os.path.join(HERE, "..", "addon", "retopo_optimizer.py"))
_spec = importlib.util.spec_from_file_location("retopo_core", ADDON)
RO = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RO)


def log(m):
    print(f"[engine] {m}", flush=True)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--basename", required=True)
    p.add_argument("--method", default="QUAD", choices=["QUAD", "COLLAPSE", "PLANAR"])
    p.add_argument("--target", type=int, default=5000)
    p.add_argument("--formats", default="fbx")
    p.add_argument("--symmetry", type=int, default=1)
    p.add_argument("--preserve-form", type=int, default=1)
    p.add_argument("--bake", type=int, default=1)
    p.add_argument("--bake-ao", type=int, default=0)
    p.add_argument("--bake-size", type=int, default=2048)
    p.add_argument("--mark-sharp", type=int, default=0)
    p.add_argument("--sharp-angle", type=float, default=40.0)
    p.add_argument("--quad-cap", type=int, default=30000)
    p.add_argument("--merge", type=float, default=0.0005,
                   help="лёгкий weld соседних точек: доля габарита (0=выкл). Закрывает мелкие дыры")
    p.add_argument("--scale", type=float, default=1.0,
                   help="множитель размера результата перед экспортом (0.01 чинит 100x в FBX)")
    return p.parse_args(argv)


def clean_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for it in list(block):
            try:
                block.remove(it)
            except Exception:
                pass


def import_model(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=path)
    else:
        raise ValueError(f"Неподдерживаемый формат: {ext}")


def weld(obj, factor):
    """Лёгкий merge соседних вершин (scale-relative). Закрывает микрозазоры/дыры
    в исходной геометрии ДО ретопологии. factor — доля диагонали габарита."""
    if factor <= 0:
        return
    d = obj.dimensions
    diag = max(1e-6, (d.x**2 + d.y**2 + d.z**2) ** 0.5)
    thr = diag * factor
    RO._activate(obj)
    before = len(obj.data.vertices)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=thr)
    bpy.ops.mesh.fill_holes(sides=8)   # закрыть мелкие дыры (≤8 сторон), не трогая крупные проёмы
    bpy.ops.object.mode_set(mode="OBJECT")
    log(f"weld: порог {thr:.5f}, вершин {before} -> {len(obj.data.vertices)}")


def join_meshes(name):
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("В файле нет мешей")
    bpy.ops.object.select_all(action="DESELECT")
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    return obj


def export(obj, outdir, name, formats):
    RO._activate(obj)
    # сохранить текстуры объекта рядом (для FBX/OBJ) и встроить
    for mat in obj.data.materials:
        if not mat or not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                img = node.image
                tex = os.path.join(outdir, img.name + ".png")
                try:
                    img.filepath_raw = tex
                    img.file_format = "PNG"
                    img.save()
                except Exception as e:
                    log(f"текстура {img.name}: {e}")
    for fmt in formats:
        fmt = fmt.strip().lower()
        if not fmt:
            continue
        path = os.path.join(outdir, f"{name}.{fmt}")
        if fmt == "fbx":
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True,
                                     path_mode="COPY", embed_textures=True)
        elif fmt == "glb":
            bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_format="GLB")
        elif fmt == "gltf":
            bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_format="GLTF_SEPARATE")
        elif fmt == "obj":
            bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
        else:
            log(f"пропуск формата: {fmt}")
            continue
        log(f"экспорт -> {os.path.basename(path)}")


def main():
    a = parse_args()
    a.input = os.path.abspath(a.input)
    a.outdir = os.path.abspath(a.outdir)   # абсолютный путь -> img.save()/экспорт надёжны
    os.makedirs(a.outdir, exist_ok=True)
    formats = [f for f in a.formats.split(",") if f.strip()]

    log(f"вход: {a.input}")
    clean_scene()
    import_model(a.input)
    original = join_meshes(a.basename + "_in")
    src_tris = RO._tri_count(original)
    log(f"исходник: {src_tris} треуг.")

    # рабочая копия-источник + чистка (КРИТИЧНО для AI-мешей)
    work_high = RO._duplicate(original, a.basename + "_highsrc")
    weld(work_high, a.merge)        # лёгкий merge соседних точек (закрывает дыры)
    RO._preprocess(work_high)

    # ретопология (та же логика, что в аддоне)
    low, used = RO._retopologize(
        work_high, a.target, a.method, a.quad_cap,
        symmetry=bool(a.symmetry),
        mark_sharp_deg=(a.sharp_angle if a.mark_sharp else 0))
    low.name = a.basename + "_retopo"

    # сохранение формы
    if a.preserve_form:
        try:
            RO._shrinkwrap(low, work_high)
        except Exception as e:
            log(f"shrinkwrap пропущен: {e}")

    # запекание деталей
    if a.bake:
        try:
            RO._bake(work_high, low, a.bake_size, bool(a.bake_ao), low.name)
        except Exception as e:
            log(f"бейк пропущен: {e}")

    # убрать служебный источник
    RO._activate(work_high)
    bpy.ops.object.delete()

    # масштаб результата перед экспортом (фикс 100x в некоторых импортёрах FBX)
    if a.scale != 1.0:
        RO._activate(low)
        low.scale = (a.scale, a.scale, a.scale)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        log(f"масштаб результата x{a.scale}")

    # экспорт
    export(low, a.outdir, low.name, formats)

    dst_tris = RO._tri_count(low)
    q = RO._quad_ratio(low)
    red = 100 * (1 - dst_tris / max(1, src_tris))
    log("=" * 50)
    log(f"РЕЗУЛЬТАТ: {src_tris} -> {dst_tris} треуг. (-{red:.1f}%), "
        f"квады {q:.0f}%, метод {used}")
    log(f"папка: {a.outdir}")
    log("DONE")


if __name__ == "__main__":
    main()
