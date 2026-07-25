"""Проверяет аддон end-to-end в фоне: регистрирует, создаёт модель, жмёт оператор."""
import bpy, os, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.normpath(os.path.join(HERE, "..", "addon", "retopo_optimizer.py"))

# загрузить аддон как модуль и зарегистрировать
spec = importlib.util.spec_from_file_location("retopo_optimizer", ADDON)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.register()
print("[test] аддон зарегистрирован")

# сцена: high-poly monkey
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()
bpy.ops.mesh.primitive_monkey_add()
o = bpy.context.active_object
m = o.modifiers.new("s", "SUBSURF"); m.levels = 5
bpy.ops.object.modifier_apply(modifier=m.name)
o.data.calc_loop_triangles()
print(f"[test] монки: {len(o.data.loop_triangles)} треуг.")

# настройки и запуск оператора (как нажатие кнопки)
s = bpy.context.scene.retopo_settings
s.method = "QUAD"; s.target_faces = 4000; s.do_bake = True; s.bake_ao = False
bpy.ops.object.select_all(action="DESELECT")
o.select_set(True); bpy.context.view_layer.objects.active = o

res = bpy.ops.object.retopo_optimize()
print(f"[test] оператор вернул: {res}")

# проверить результат
result = bpy.data.objects.get("Suzanne_retopo")
if result:
    result.data.calc_loop_triangles()
    quads = sum(1 for p in result.data.polygons if len(p.vertices) == 4)
    qr = 100.0 * quads / max(1, len(result.data.polygons))
    has_uv = bool(result.data.uv_layers)
    has_mat = bool(result.data.materials)
    print(f"[test] РЕЗУЛЬТАТ: {len(result.data.loop_triangles)} треуг., "
          f"квады {qr:.0f}%, UV={has_uv}, материал/бейк={has_mat}")
    print("[test] OK" if qr > 80 and has_uv else "[test] ВНИМАНИЕ: проверить")
else:
    print("[test] ОШИБКА: объект Suzanne_retopo не создан")
