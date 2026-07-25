"""Высокополигональная Suzanne — реалистичный тест ретопологии (уши, глазницы,
разная кривизна). Кладёт в input/test_suzanne.glb.
Запуск:  blender --background --python make_test_suzanne.py
"""
import bpy
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "input", "test_suzanne.glb"))
os.makedirs(os.path.dirname(OUT), exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

bpy.ops.mesh.primitive_monkey_add()
obj = bpy.context.active_object
obj.name = "suzanne"

# делаем high-poly: subdivision surface + shade smooth
sub = obj.modifiers.new("Subsurf", type="SUBSURF")
sub.levels = 5
sub.render_levels = 5
bpy.ops.object.modifier_apply(modifier=sub.name)
bpy.ops.object.shade_smooth()

# простой материал + UV (чтобы было что-то на входе)
mat = bpy.data.materials.new("suzanne_mat")
mat.use_nodes = True
obj.data.materials.append(mat)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project()
bpy.ops.object.mode_set(mode="OBJECT")

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.export_scene.gltf(filepath=OUT, use_selection=True, export_format="GLB")

obj.data.calc_loop_triangles()
print(f"[test] Suzanne: {len(obj.data.polygons)} полигонов / {len(obj.data.loop_triangles)} треуг.")
print(f"[test] сохранено: {OUT}")
