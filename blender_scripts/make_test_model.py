"""Создаёт высокополигональную тестовую модель и кладёт в input/test_highpoly.glb.
Запуск:  blender --background --python make_test_model.py
"""
import bpy
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "input", "test_highpoly.glb"))
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# чистим сцену
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# плотная сфера с шумом + материал -> имитация "грязного" AI-меша
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=6, radius=1.0)  # ~много полигонов
obj = bpy.context.active_object
obj.name = "test"

# добавим деталей модификатором Subdivision + Displace по текстуре
tex = bpy.data.textures.new("noise", type="MUSGRAVE") if hasattr(bpy.data.textures, "new") else None
disp = obj.modifiers.new("Displace", type="DISPLACE")
if tex is None:
    tex = bpy.data.textures.new("noise", type="CLOUDS")
disp.texture = tex
disp.strength = 0.15
bpy.ops.object.modifier_apply(modifier=disp.name)

# простой материал
mat = bpy.data.materials.new("test_mat")
mat.use_nodes = True
obj.data.materials.append(mat)

# UV, чтобы было что сохранять/печь
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project()
bpy.ops.object.mode_set(mode="OBJECT")

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.export_scene.gltf(filepath=OUT, use_selection=True, export_format="GLB")

obj.data.calc_loop_triangles()
print(f"[test] создано {len(obj.data.polygons)} полигонов / {len(obj.data.loop_triangles)} треуг.")
print(f"[test] сохранено: {OUT}")
