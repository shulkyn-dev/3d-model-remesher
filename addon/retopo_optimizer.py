"""
3D Retopo Optimizer — Blender-аддон.
Превращает высокополигональную модель в чистую низкополигональную (quad-ретопология)
+ запекает детали с оригинала в normal/AO. Работает прямо в окне Blender.

Установка:
  Edit > Preferences > Add-ons > (стрелка вверху справа) > Install from Disk...
  выбери этот файл retopo_optimizer.py > включи галочку.
Панель: в 3D-вьюпорте нажми N > вкладка "Retopo".

Использование:
  1. Импортируй/выбери высокополигональную модель (она станет источником деталей).
  2. На панели задай целевое число полигонов и метод.
  3. Жми "Retopologize Selected".
  4. Результат появится как новый объект <имя>_retopo и выделится. Оригинал прячется.
"""

bl_info = {
    "name": "3D Retopo Optimizer",
    "author": "Oleksandr",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Retopo",
    "description": "Авто-ретопология high->low + запекание normal/AO",
    "category": "Mesh",
}

import bpy
import os
import time


# ======================= ЯДРО (повторяет проверенный headless-конвейер) =======================

def _log(m):
    print(f"[retopo] {m}", flush=True)


def _face_count(obj):
    return len(obj.data.polygons)


def _tri_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def _quad_ratio(obj):
    polys = obj.data.polygons
    if not polys:
        return 0.0
    quads = sum(1 for p in polys if len(p.vertices) == 4)
    return 100.0 * quads / len(polys)


def _activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _duplicate(obj, name):
    _activate(obj)
    bpy.ops.object.duplicate()
    d = bpy.context.view_layer.objects.active
    d.name = name
    return d


def _preprocess(obj):
    """КРИТИЧНО: убрать расщеплённые вершины (импорт glb/fbx) -> манифолд для QuadriFlow."""
    _activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    before = len(obj.data.vertices)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=1e-5)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.mesh.delete_loose()
    bpy.ops.object.mode_set(mode="OBJECT")
    _log(f"очистка вершин {before} -> {len(obj.data.vertices)}")


def _decimate(obj, ratio, dtype="COLLAPSE"):
    _activate(obj)
    mod = obj.modifiers.new("Decimate", type="DECIMATE")
    if dtype == "PLANAR":
        mod.decimate_type = "DISSOLVE"
        mod.angle_limit = 0.087
    else:
        mod.decimate_type = "COLLAPSE"
        mod.ratio = max(0.0, min(1.0, ratio))
        mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)


def _voxel_manifold(obj):
    dims = obj.dimensions
    diag = max(1e-4, (dims.x**2 + dims.y**2 + dims.z**2) ** 0.5)
    obj.data.remesh_voxel_size = diag / 200.0
    _activate(obj)
    bpy.ops.object.voxel_remesh()


def _mark_sharp(obj, angle_deg):
    """Помечает острые рёбра по углу -> QuadriFlow их сохраняет (важно для hard-surface)."""
    import math
    _activate(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.mark_sharp(clear=True)
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.mesh.edges_select_sharp(sharpness=math.radians(angle_deg))
    bpy.ops.mesh.mark_sharp()
    bpy.ops.object.mode_set(mode="OBJECT")


def _quadriflow(obj, target, symmetry=True):
    """True, если ретопология реально произошла (оператор может вернуть CANCELLED)."""
    _activate(obj)
    before = _face_count(obj)
    try:
        res = bpy.ops.object.quadriflow_remesh(
            mode="FACES", target_faces=target, use_mesh_symmetry=symmetry,
            use_preserve_sharp=True, use_preserve_boundary=True, smooth_normals=True,
        )
    except Exception as e:
        _log(f"QuadriFlow исключение: {e}")
        return False
    if "FINISHED" not in res or _face_count(obj) >= before:
        return False
    bpy.ops.object.shade_smooth()
    return True


def _retopologize(src, target, method, quad_cap, voxel_fallback=True,
                  symmetry=True, mark_sharp_deg=0):
    """Возвращает (объект, применённый_метод). mark_sharp_deg=0 -> не помечать."""
    low = _duplicate(src, src.name + "_retopo")
    src_faces = _face_count(src)
    ratio = target / max(1, src_faces) if target > 1 else target

    if method == "QUAD":
        if _face_count(low) > quad_cap:
            _decimate(low, quad_cap / _face_count(low))
            _log(f"пре-децимация до {_face_count(low)} для QuadriFlow")
        if mark_sharp_deg > 0:
            _mark_sharp(low, mark_sharp_deg)
        if _quadriflow(low, target, symmetry):
            return low, "quad"
        if voxel_fallback:
            _log("QuadriFlow упал -> voxel-манифолд и повтор")
            _voxel_manifold(low)
            if _face_count(low) > quad_cap:
                _decimate(low, quad_cap / _face_count(low))
            if _quadriflow(low, target, symmetry):
                return low, "quad(voxel)"
        _decimate(low, ratio)
        return low, "collapse(fallback)"
    elif method == "PLANAR":
        _decimate(low, ratio, "PLANAR")
        return low, "planar"
    else:
        _decimate(low, ratio)
        return low, "collapse"


def _shrinkwrap(low, target):
    """Притягивает вершины результата на поверхность оригинала -> сохраняет форму/силуэт.
    Ключевой приём против 'оплывания' после ретопологии."""
    _activate(low)
    mod = low.modifiers.new("Shrinkwrap", type="SHRINKWRAP")
    mod.target = target
    mod.wrap_method = "NEAREST_SURFACEPOINT"
    bpy.ops.object.modifier_apply(modifier=mod.name)
    # пересчитать нормали и сгладить после подгонки
    _activate(low)
    bpy.ops.object.shade_smooth()


def _smart_uv(obj):
    _activate(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")


def _bake(high, low, size, do_ao, name):
    if not low.data.uv_layers:
        _smart_uv(low)
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    low.data.materials.clear()
    low.data.materials.append(mat)
    nt = mat.node_tree

    scn = bpy.context.scene
    prev_engine = scn.render.engine
    scn.render.engine = "CYCLES"
    scn.cycles.samples = 8
    scn.render.bake.use_selected_to_active = True
    scn.render.bake.cage_extrusion = 0.05
    scn.render.bake.margin = max(4, size // 256)

    def bake_one(btype, key):
        img = bpy.data.images.new(f"{name}_{key}", width=size, height=size)
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        nt.nodes.active = node
        scn.cycles.bake_type = btype
        bpy.ops.object.select_all(action="DESELECT")
        high.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        bpy.ops.object.bake(type=btype)
        _log(f"запечено {key}")
        return img, node

    nimg, nnode = bake_one("NORMAL", "normal")
    if do_ao:
        aimg, _ = bake_one("AO", "ao")
        aimg.pack()  # встроить в .blend, чтобы не потерять

    nimg.pack()
    bsdf = nt.nodes.get("Principled BSDF")
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nnode.outputs["Color"], nmap.inputs["Color"])
    if bsdf:
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    scn.render.engine = prev_engine


# ======================= НАСТРОЙКИ (Scene properties) =======================

class RetopoSettings(bpy.types.PropertyGroup):
    target_faces: bpy.props.IntProperty(
        name="Target polygons", default=5000, min=50, max=2000000,
        description="Желаемое число полигонов у результата")
    method: bpy.props.EnumProperty(
        name="Method", default="QUAD",
        items=[
            ("QUAD", "Quad (ретопология)", "QuadriFlow — чистые квады. Главный режим"),
            ("COLLAPSE", "Collapse (LOD)", "Децимация, сохраняет UV/текстуры, быстро"),
            ("PLANAR", "Planar (hard-surface)", "Убирает рёбра с плоскостей"),
        ])
    preserve_form: bpy.props.BoolProperty(
        name="Preserve form (Shrinkwrap)", default=True,
        description="Притянуть результат на оригинал — сохраняет силуэт/форму, "
                    "не даёт модели 'оплыть' после ретопологии")
    use_symmetry: bpy.props.BoolProperty(
        name="Symmetry", default=True,
        description="Симметричная топология (персонажи, предметы по оси X)")
    mark_sharp: bpy.props.BoolProperty(
        name="Preserve hard edges", default=False,
        description="Помечать и сохранять острые края — для hard-surface/CAD. "
                    "Для органики лучше выключить")
    sharp_angle: bpy.props.FloatProperty(
        name="Sharp angle", default=40.0, min=10.0, max=80.0,
        description="Угол, выше которого ребро считается острым")
    do_bake: bpy.props.BoolProperty(
        name="Bake Normal map", default=True,
        description="Запечь детали с оригинала в normal map")
    bake_ao: bpy.props.BoolProperty(
        name="+ Ambient Occlusion", default=False)
    bake_size: bpy.props.EnumProperty(
        name="Texture size", default="2048",
        items=[("1024", "1024", ""), ("2048", "2048", ""), ("4096", "4096", "")])
    keep_original: bpy.props.BoolProperty(
        name="Keep original visible", default=False,
        description="Не прятать исходную модель после ретопологии")
    quad_cap: bpy.props.IntProperty(
        name="QuadriFlow input cap", default=30000, min=2000, max=200000,
        description="Потолок плотности источника перед QuadriFlow (стабильность)")


# ======================= ОПЕРАТОР =======================

class OBJECT_OT_retopo_optimize(bpy.types.Operator):
    bl_idname = "object.retopo_optimize"
    bl_label = "Retopologize Selected"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        s = context.scene.retopo_settings
        original = context.active_object
        t0 = time.time()

        src_tris = _tri_count(original)
        self.report({"INFO"}, f"Старт: {src_tris} треуг.")

        base_name = original.name
        # рабочая копия-источник (бейк + чистка), оригинал не трогаем
        work_high = _duplicate(original, base_name + "_highsrc")
        _preprocess(work_high)

        # ретопология
        low, used = _retopologize(
            work_high, s.target_faces, s.method, s.quad_cap,
            symmetry=s.use_symmetry,
            mark_sharp_deg=(s.sharp_angle if s.mark_sharp else 0))
        low.name = base_name + "_retopo"
        if low.data:
            low.data.name = base_name + "_retopo"

        # сохранение формы: притянуть результат на оригинал
        if s.preserve_form:
            try:
                _shrinkwrap(low, work_high)
            except Exception as e:
                self.report({"WARNING"}, f"Shrinkwrap не удался: {e}")

        # запекание
        if s.do_bake:
            try:
                _bake(work_high, low, int(s.bake_size), s.bake_ao, low.name)
            except Exception as e:
                self.report({"WARNING"}, f"Бейк не удался: {e}")

        # убрать служебный источник
        _activate(work_high)
        bpy.ops.object.delete()

        # спрятать оригинал (или оставить)
        if not s.keep_original:
            original.hide_set(True)

        # показать результат
        _activate(low)

        dt = time.time() - t0
        q = _quad_ratio(low)
        red = 100 * (1 - _tri_count(low) / max(1, src_tris))
        msg = (f"{used}: {src_tris}->{_tri_count(low)} треуг. "
               f"(-{red:.1f}%), квады {q:.0f}%, {dt:.1f}s")
        self.report({"INFO"}, msg)
        _log(msg)
        return {"FINISHED"}


# ======================= ЭКСПОРТ =======================

class OBJECT_OT_retopo_export(bpy.types.Operator):
    bl_idname = "object.retopo_export"
    bl_label = "Export result"
    bl_description = "Сохранить результат в FBX/GLB/OBJ с текстурами"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(
        default="*.fbx;*.glb;*.gltf;*.obj", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def invoke(self, context, event):
        obj = context.active_object
        if not self.filepath:
            self.filepath = obj.name + ".fbx"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        obj = context.active_object
        path = self.filepath
        ext = os.path.splitext(path)[1].lower()
        out_dir = os.path.dirname(path)

        # сохранить текстуры объекта на диск рядом с моделью (для FBX/OBJ)
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image:
                    img = node.image
                    tex_path = os.path.join(out_dir, img.name + ".png")
                    try:
                        img.filepath_raw = tex_path
                        img.file_format = "PNG"
                        img.save()
                    except Exception as e:
                        self.report({"WARNING"}, f"Текстура {img.name}: {e}")

        _activate(obj)
        try:
            if ext == ".fbx":
                bpy.ops.export_scene.fbx(filepath=path, use_selection=True,
                                         path_mode="COPY", embed_textures=True)
            elif ext == ".glb":
                bpy.ops.export_scene.gltf(filepath=path, use_selection=True,
                                          export_format="GLB")
            elif ext == ".gltf":
                bpy.ops.export_scene.gltf(filepath=path, use_selection=True,
                                          export_format="GLTF_SEPARATE")
            elif ext == ".obj":
                bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
            else:
                self.report({"ERROR"}, f"Неизвестный формат: {ext}")
                return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, f"Экспорт не удался: {e}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Экспортировано: {path}")
        return {"FINISHED"}


# ======================= ПАНЕЛЬ =======================

class VIEW3D_PT_retopo(bpy.types.Panel):
    bl_label = "3D Retopo Optimizer"
    bl_idname = "VIEW3D_PT_retopo"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Retopo"

    def draw(self, context):
        layout = self.layout
        s = context.scene.retopo_settings

        col = layout.column(align=True)
        col.prop(s, "method")
        col.prop(s, "target_faces")

        if s.method == "QUAD":
            qbox = layout.box()
            qbox.prop(s, "use_symmetry")
            qbox.prop(s, "mark_sharp")
            if s.mark_sharp:
                qbox.prop(s, "sharp_angle")

        layout.prop(s, "preserve_form")

        box = layout.box()
        box.prop(s, "do_bake")
        if s.do_bake:
            box.prop(s, "bake_ao")
            box.prop(s, "bake_size")

        layout.prop(s, "keep_original")

        adv = layout.box()
        adv.label(text="Advanced")
        adv.prop(s, "quad_cap")

        obj = context.active_object
        row = layout.row()
        row.scale_y = 1.6
        if obj and obj.type == "MESH":
            row.operator("object.retopo_optimize", icon="MOD_REMESH")
            obj.data.calc_loop_triangles()
            info = layout.column(align=True)
            info.label(text=f"Выбрано: {len(obj.data.loop_triangles)} треуг.", icon="MESH_DATA")
            # экспорт результата (виден, если выбран *_retopo)
            exp = layout.row()
            exp.scale_y = 1.3
            exp.operator("object.retopo_export", icon="EXPORT")
        else:
            row.enabled = False
            row.operator("object.retopo_optimize", icon="MOD_REMESH")
            layout.label(text="Выбери MESH-объект", icon="ERROR")


# ======================= РЕГИСТРАЦИЯ =======================

_classes = (
    RetopoSettings,
    OBJECT_OT_retopo_optimize,
    OBJECT_OT_retopo_export,
    VIEW3D_PT_retopo,
)


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.retopo_settings = bpy.props.PointerProperty(type=RetopoSettings)


def unregister():
    del bpy.types.Scene.retopo_settings
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
