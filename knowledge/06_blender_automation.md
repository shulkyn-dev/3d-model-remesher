# 06 — Автоматизация Blender (bpy): операторы, параметры, грабли

Как теория из 01–05 ложится на код. Blender headless = «движок» приложения.
Проверено на **Blender 5.1.2**.

## Запуск headless
```
blender --background --python script.py -- <свои аргументы после "--">
```
- `--background` (`-b`) — без UI.
- Аргументы после `--` берём через `sys.argv[sys.argv.index("--")+1:]`.
- Внутри доступен полноценный `bpy`, у Blender свой встроенный Python (не системный 3.14).

## Импорт / экспорт (5.x)
| Формат | Импорт | Экспорт |
|---|---|---|
| glTF/GLB | `bpy.ops.import_scene.gltf` | `bpy.ops.export_scene.gltf(export_format="GLB"/"GLTF_SEPARATE")` |
| OBJ | `bpy.ops.wm.obj_import` | `bpy.ops.wm.obj_export` |
| FBX | `bpy.ops.import_scene.fbx` | `bpy.ops.export_scene.fbx(path_mode="COPY", embed_textures=True)` |
| STL | `bpy.ops.wm.stl_import` | `bpy.ops.wm.stl_export` |
- Экспортируем только выделенное: `use_selection=True`.

## Упрощение
```python
# Decimate Collapse (LOD, сохраняет UV):
mod = obj.modifiers.new("Decimate", type="DECIMATE")
mod.decimate_type = "COLLAPSE"
mod.ratio = target_ratio          # 0..1
mod.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier=mod.name)

# Planar (hard-surface):
mod.decimate_type = "DISSOLVE"
mod.angle_limit = radians(5)

# QuadriFlow (quad-ретопо, убивает UV):
bpy.ops.object.quadriflow_remesh(target_faces=N,
    use_preserve_sharp=True, use_preserve_boundary=True, smooth_normals=True)

# Voxel remesh (watertight, для печати) — кандидат:
obj.data.remesh_voxel_size = 0.01
bpy.ops.object.voxel_remesh()
```

## UV
```python
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02)
bpy.ops.object.mode_set(mode="OBJECT")
# качество выше: mark seams from sharp -> bpy.ops.uv.unwrap(method="ANGLE_BASED")
```

## Бейк (Cycles)
```python
scene.render.engine = "CYCLES"
scene.cycles.bake_type = "NORMAL"          # / "AO" / "DIFFUSE" / "ROUGHNESS"...
scene.render.bake.use_selected_to_active = True
scene.render.bake.cage_extrusion = 0.05    # или scene.render.bake.cage_object = cage
scene.render.bake.margin = 8
# целевая image-нода ДОЛЖНА быть active в node_tree материала low-poly
mat.node_tree.nodes.active = image_node
# выделить high (source) + low, low = active, затем:
bpy.ops.object.bake(type="NORMAL")
```

## Препроцессинг (кандидат-модуль `--clean`)
```python
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=1e-4)      # merge by distance
bpy.ops.mesh.normals_make_consistent(inside=False)  # recalc outside
bpy.ops.mesh.delete_loose()
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.transform_apply(scale=True, rotation=True)  # apply transforms
```

## Грабли (важно!)
1. **Контекст оператора.** Операторы зависят от выделения/активного объекта/режима. В headless
   нет «активной области» — большинство меш-операторов требуют правильного `view_layer.objects.active`
   и `select_set(True)`. Всегда явно выставлять перед вызовом.
2. **Метрика «полигоны» vs «треугольники».** `len(obj.data.polygons)` ≠ треугольники. Для движка
   считать `calc_loop_triangles()` → `len(loop_triangles)`. Мы так и делаем.
3. **Порядок selected-to-active при бейке:** источник(и) просто selected, цель — **active**. Перепутать =
   запечётся не туда.
4. **QuadriFlow убивает UV** — после него обязателен Smart UV перед бейком.
5. **Применять модификаторы** (`modifier_apply`) до экспорта/бейка — иначе геометрия «виртуальная».
6. **Apply scale/rotation** до бейка — иначе нормали/расстояния лучей врут.
7. **FBX и текстуры:** `path_mode="COPY", embed_textures=True` чтобы текстуры уехали в файл; иначе
   ссылки побьются. Для glTF GLB всё встраивается само.
8. **Версии API.** Имена операторов между мажорами Blender меняются (напр. STL/OBJ переезжали в `wm.*`).
   Закрепили на 5.1.2; при апгрейде проверять смоук-тестом.
9. **Чистка datablocks** между прогонами в одной сессии (meshes/materials/images), иначе утечки и
   путаница имён.

## Карта «фича → где в коде»
- LOD-генерация, методы → `blender_scripts/optimize.py: reduce_level()`, `_decimate()`
- UV для quad → `unwrap()`
- Бейк → `bake_for()`
- Экспорт форматов → `export()`
- Поиск Blender, CLI → `run.py: find_blender()`
- Валидация вне Blender → `tools/inspect_mesh.py` (trimesh)

См. индекс: [00_overview](00_overview.md).
