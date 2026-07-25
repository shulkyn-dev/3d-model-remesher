"""Диагностика QuadriFlow: импорт Suzanne, чистка, перебор настроек."""
import bpy, os

HERE = os.path.dirname(os.path.abspath(__file__))
SUZ = os.path.normpath(os.path.join(HERE, "..", "input", "test_suzanne.glb"))

def fc(o): return len(o.data.polygons)

bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()
bpy.ops.import_scene.gltf(filepath=SUZ)
o = [x for x in bpy.context.scene.objects if x.type=="MESH"][0]
bpy.context.view_layer.objects.active = o; o.select_set(True)

# чистка
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=1e-5)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode="OBJECT")
print(f"[dbg] после чистки граней={fc(o)}")

# pre-decimate до ~30k (QuadriFlow не любит миллионы)
m = o.modifiers.new("d","DECIMATE"); m.ratio = 30000/fc(o)
bpy.ops.object.modifier_apply(modifier=m.name)
print(f"[dbg] после pre-decimate граней={fc(o)}")

for mode, kw in [
    ("default", {}),
    ("FACES_4000", {"mode":"FACES","target_faces":4000}),
    ("RATIO", {"mode":"RATIO","target_ratio":0.05}),
]:
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True)
    bpy.context.view_layer.objects.active = o
    before = fc(o)
    try:
        res = bpy.ops.object.quadriflow_remesh(**kw)
        print(f"[dbg] {mode}: статус={res} граней {before}->{fc(o)}")
    except Exception as e:
        print(f"[dbg] {mode}: ИСКЛЮЧЕНИЕ {e}")
    # переимпорт чистого для следующего теста
    if mode != "RATIO":
        bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()
        bpy.ops.import_scene.gltf(filepath=SUZ)
        o = [x for x in bpy.context.scene.objects if x.type=="MESH"][0]
        bpy.context.view_layer.objects.active = o; o.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=1e-5); bpy.ops.object.mode_set(mode="OBJECT")
        m = o.modifiers.new("d","DECIMATE"); m.ratio = 30000/fc(o)
        bpy.ops.object.modifier_apply(modifier=m.name)
