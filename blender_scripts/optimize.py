"""
optimize.py — ядро "перестройщика" 3D-моделей (LOD-генератор).
Запускается ВНУТРИ Blender в фоновом режиме:

    blender --background --python optimize.py -- \
        --input  path/to/highpoly.glb \
        --outdir path/to/output \
        --basename chair \
        --levels  0.5,0.2,0.05 \
        --formats fbx,glb \
        --method  collapse

Главная задача: из одной high-poly модели сделать несколько уровней детализации
(high -> mid -> low ...), сохраняя UV и материалы, и экспортировать каждый.

--levels: список значений через запятую. Каждое значение:
    <= 1   -> трактуется как ДОЛЯ полигонов (0.5 = 50%)
    > 1    -> трактуется как ЦЕЛЕВОЕ число полигонов (5000)
  пример: "0.5,0.2,5000"  -> три LOD: 50%, 20%, ~5000 полигонов

--method:
    collapse  (по умолчанию) Decimate Collapse — сохраняет UV, быстро. Для LOD.
    planar    Decimate Planar — схлопывает плоские грани (хорошо для hard-surface)
    quad      QuadriFlow — чистые квады, НО уничтожает UV (нужен --bake)

Опц. фичи:
    --bake          запечь Normal map с исходного high-poly на каждый LOD
    --bake-ao       + Ambient Occlusion
    --bake-size N   разрешение текстур (по умолч. 2048)
"""

import bpy
import sys
import os
import argparse
import time

# QuadriFlow нестабилен на плотных мешах -> источник пре-децимируем до этого потолка
QUAD_INPUT_CAP = 30000


# ---------- аргументы (всё после "--") ----------
def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--basename", required=True)
    p.add_argument("--levels", default="0.5,0.25,0.1",
                   help="доли (<=1) или целевые полигоны (>1), через запятую")
    p.add_argument("--names", default="",
                   help="опц. метки уровней через запятую, напр. high,mid,low")
    p.add_argument("--formats", default="fbx",
                   help="форматы экспорта через запятую: fbx,glb,gltf,obj")
    p.add_argument("--method", default="collapse",
                   choices=["collapse", "planar", "quad"])
    p.add_argument("--bake", action="store_true")
    p.add_argument("--bake-ao", action="store_true")
    p.add_argument("--bake-size", type=int, default=2048)
    p.add_argument("--no-clean", action="store_true",
                   help="отключить препроцессинг (merge doubles / recalc normals)")
    p.add_argument("--no-voxel-fallback", action="store_true",
                   help="не делать voxel-ремеш, если QuadriFlow падает")
    p.add_argument("--quad-input-cap", type=int, default=QUAD_INPUT_CAP,
                   help="потолок граней источника перед QuadriFlow (по умолч. 30000)")
    return p.parse_args(argv)


def log(m):
    print(f"[optimizer] {m}", flush=True)


# ---------- сцена ----------
def clean_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for item in list(block):
            block.remove(item)


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


def tri_count(obj):
    """Кол-во треугольников после триангуляции (честная метрика для движков)."""
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def face_count(obj):
    return len(obj.data.polygons)


def quad_ratio(obj):
    """Доля четырёхугольных граней — показатель качества ретопологии (0..100%)."""
    polys = obj.data.polygons
    if not polys:
        return 0.0
    quads = sum(1 for p in polys if len(p.vertices) == 4)
    return 100.0 * quads / len(polys)


def duplicate(obj, new_name):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.duplicate()
    d = bpy.context.view_layer.objects.active
    d.name = new_name
    return d


# ---------- препроцессинг (КРИТИЧНО для AI-мешей) ----------
def preprocess(obj):
    """Готовит меш к ретопологии: убирает расщеплённые/дублирующиеся вершины
    (после импорта glb/fbx их почти всегда много -> не-манифолд -> QuadriFlow падает),
    пересчитывает нормали наружу, удаляет висящую геометрию, применяет трансформы."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # применяем масштаб/поворот (иначе бейк/лучи врут)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    before = len(obj.data.vertices)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=1e-5)        # merge by distance
    bpy.ops.mesh.normals_make_consistent(inside=False)  # recalc outside
    bpy.ops.mesh.delete_loose()
    bpy.ops.object.mode_set(mode="OBJECT")
    after = len(obj.data.vertices)
    log(f"Очистка: вершин {before} -> {after} (слито {before-after})")


def make_manifold_voxel(obj, src_faces):
    """Voxel-ремеш -> гарантированно водонепроницаемый манифолд (теряет тонкие детали,
    но они потом вернутся бейком). Размер вокселя оцениваем от габаритов и плотности."""
    dims = obj.dimensions
    diag = max(1e-4, (dims.x**2 + dims.y**2 + dims.z**2) ** 0.5)
    # цель ~ плотность близкая к исходной; эвристика
    voxel = diag / 200.0
    obj.data.remesh_voxel_size = voxel
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.voxel_remesh()
    log(f"Voxel remesh: размер вокселя {voxel:.4f} -> {len(obj.data.polygons)} граней")


# ---------- упрощение одного уровня ----------
def reduce_level(src, level_value, method, name, voxel_fallback=True):
    """Создаёт уровень из копии src. level_value: <=1 доля, >1 целевые полигоны.
    Возвращает (объект, фактически_применённый_метод)."""
    low = duplicate(src, name)
    src_faces = face_count(src)

    if level_value <= 1:
        ratio = float(level_value)
    else:
        ratio = min(1.0, float(level_value) / max(1, src_faces))

    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.context.view_layer.objects.active = low

    if method == "quad":
        target = int(level_value) if level_value > 1 else max(50, int(src_faces * ratio))
        # QuadriFlow нестабилен на плотных мешах (>~30k граней он отдаёт CANCELLED).
        # Пре-децимируем источник до безопасного потолка; детали вернёт бейк с оригинала.
        if face_count(low) > QUAD_INPUT_CAP:
            _decimate(low, QUAD_INPUT_CAP / face_count(low), "COLLAPSE")
            log(f"  пре-децимация до {face_count(low)} граней для QuadriFlow")
        if _quadriflow(low, target):
            return low, "quad"
        # 1-я страховка: сделать манифолд voxel-ремешем и повторить QuadriFlow
        if voxel_fallback:
            log("QuadriFlow упал -> делаю voxel-манифолд и повторяю")
            make_manifold_voxel(low, src_faces)
            if face_count(low) > QUAD_INPUT_CAP:
                _decimate(low, QUAD_INPUT_CAP / face_count(low), "COLLAPSE")
            if _quadriflow(low, target):
                return low, "quad(voxel)"
        # 2-я страховка: децимация, но ЧЕСТНО сообщаем, что это не quad
        log("QuadriFlow не удался -> fallback на collapse (НЕ настоящая ретопология)")
        _decimate(low, ratio, "COLLAPSE")
        return low, "collapse(fallback)"
    elif method == "planar":
        _decimate(low, ratio, "PLANAR")
        return low, "planar"
    else:  # collapse
        _decimate(low, ratio, "COLLAPSE")
        return low, "collapse"


def _quadriflow(obj, target):
    """Пробует QuadriFlow. True/False — реально ли произошла ретопология.
    Оператор при мягком провале возвращает {'CANCELLED'} (без исключения),
    поэтому проверяем И статус, И что число граней действительно упало."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    before = face_count(obj)
    try:
        res = bpy.ops.object.quadriflow_remesh(
            mode="FACES",
            target_faces=target,
            use_preserve_sharp=True,
            use_preserve_boundary=True,
            smooth_normals=True,
        )
    except Exception as e:
        log(f"  QuadriFlow исключение: {e}")
        return False
    after = face_count(obj)
    if "FINISHED" not in res or after >= before:
        log(f"  QuadriFlow не изменил меш (статус={res}, граней {before}->{after})")
        return False
    bpy.ops.object.shade_smooth()   # чистое затенение после ретопо
    return True


def _decimate(obj, ratio, dtype):
    mod = obj.modifiers.new(name="Decimate", type="DECIMATE")
    if dtype == "PLANAR":
        mod.decimate_type = "DISSOLVE"
        mod.angle_limit = 0.087  # ~5 градусов
    else:
        mod.decimate_type = "COLLAPSE"
        mod.ratio = max(0.0, min(1.0, ratio))
        mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)


# ---------- запекание (опц. фича) ----------
def unwrap(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")


def bake_for(high, low, name, outdir, size, do_ao):
    # quad-метод убил UV — делаем новую развёртку
    if not low.data.uv_layers:
        unwrap(low)

    mat = bpy.data.materials.new(f"{name}_mat")
    mat.use_nodes = True
    low.data.materials.clear()
    low.data.materials.append(mat)
    nt = mat.node_tree

    def make_img(key):
        img = bpy.data.images.new(f"{name}_{key}", width=size, height=size)
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        return img, node

    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 8
    bpy.context.scene.render.bake.use_selected_to_active = True
    bpy.context.scene.render.bake.cage_extrusion = 0.05
    bpy.context.scene.render.bake.margin = 8

    def bake(bake_type, key):
        img, node = make_img(key)
        nt.nodes.active = node
        bpy.context.scene.cycles.bake_type = bake_type
        bpy.ops.object.select_all(action="DESELECT")
        high.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        bpy.ops.object.bake(type=bake_type)
        path = os.path.join(outdir, f"{name}_{key}.png")
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        log(f"  запечено {key} -> {os.path.basename(path)}")
        return img, node

    nimg, nnode = bake("NORMAL", "normal")
    if do_ao:
        bake("AO", "ao")

    # подключим normal в материал
    bsdf = nt.nodes.get("Principled BSDF")
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nnode.outputs["Color"], nmap.inputs["Color"])
    if bsdf:
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])


# ---------- экспорт ----------
def export(obj, outdir, name, formats):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for fmt in formats:
        fmt = fmt.strip().lower()
        if not fmt:
            continue
        path = os.path.join(outdir, f"{name}.{fmt}")
        if fmt == "fbx":
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True,
                                     path_mode="COPY", embed_textures=True)
        elif fmt == "glb":
            bpy.ops.export_scene.gltf(filepath=path, use_selection=True,
                                      export_format="GLB")
        elif fmt == "gltf":
            bpy.ops.export_scene.gltf(filepath=path[:-5] + ".gltf",
                                      use_selection=True,
                                      export_format="GLTF_SEPARATE")
        elif fmt == "obj":
            bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
        else:
            log(f"  пропускаю неизвестный формат: {fmt}")
            continue
        log(f"  экспорт -> {os.path.basename(path)}")


def main():
    global QUAD_INPUT_CAP
    args = parse_args()
    QUAD_INPUT_CAP = args.quad_input_cap
    t0 = time.time()
    os.makedirs(args.outdir, exist_ok=True)
    formats = [f for f in args.formats.split(",") if f.strip()]

    levels = []
    for v in args.levels.split(","):
        v = v.strip()
        if v:
            levels.append(float(v))
    names_override = [n.strip() for n in args.names.split(",") if n.strip()]

    log(f"Старт. input={args.input}")
    clean_scene()
    import_model(args.input)
    high = join_meshes(f"{args.basename}_HIGH")

    # КРИТИЧНО: чистка перед ретопологией (импортированные меши почти всегда
    # с расщеплёнными вершинами -> не-манифолд -> QuadriFlow падает)
    if not args.no_clean:
        preprocess(high)

    src_faces = face_count(high)
    src_tris = tri_count(high)
    log(f"High-poly: {src_faces} полигонов / {src_tris} треуг.")

    report = [("HIGH/исходник", src_faces, src_tris, quad_ratio(high), "—")]

    for i, lvl in enumerate(levels):
        if i < len(names_override):
            label = names_override[i]
        else:
            label = f"LOD{i+1}"
        name = f"{args.basename}_{label}"
        log(f"Уровень {label}: значение={lvl} method={args.method}")
        low, used = reduce_level(high, lvl, args.method, name,
                                 voxel_fallback=not args.no_voxel_fallback)
        if args.bake:
            bake_for(high, low, name, args.outdir, args.bake_size, args.bake_ao)
        f, t, q = face_count(low), tri_count(low), quad_ratio(low)
        report.append((label, f, t, q, used))
        export(low, args.outdir, name, formats)
        # удалим уровень из сцены, чтобы не мешал следующему bake
        bpy.ops.object.select_all(action="DESELECT")
        low.select_set(True)
        bpy.ops.object.delete()

    log("=" * 72)
    log(f"ГОТОВО за {time.time()-t0:.1f}s. Форматы: {','.join(formats)}")
    log(f"{'Уровень':<14}{'полигоны':>10}{'треуг.':>10}{'-% от исх.':>11}{'квады%':>8}  {'метод':<18}")
    for label, f, t, q, used in report:
        red = 100 * (1 - t / max(1, src_tris))
        log(f"{label:<14}{f:>10}{t:>10}{red:>10.1f}%{q:>7.0f}%  {used:<18}")
    log(f"Результаты в: {args.outdir}")
    log("=" * 72)


if __name__ == "__main__":
    main()
