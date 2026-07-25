# База знаний — 3D Optimizer

Экспертный референс по топологии/ретопологии/UV/бейку. Двойное назначение:
(1) направляет архитектуру и параметры приложения, (2) документация для пользователя.

## Навигация
1. [01_topology_fundamentals](01_topology_fundamentals.md) — quad/tri/ngon, edge flow, поляки,
   loops, нормали, затенение. **Что такое «хорошая топология».**
2. [02_poly_levels](02_poly_levels.md) — high/mid/low poly vs LOD-цепочка, бюджеты полигонов
   по платформам, правила редукции (≈50%/шаг), texel density.
3. [03_retopology](03_retopology.md) — принципы + алгоритмы (collapse / planar / quad / voxel /
   instant-meshes), шпаргалка выбора, препроцессинг.
4. [04_uv_unwrapping](04_uv_unwrapping.md) — швы, острова, искажения, packing, Smart UV vs Unwrap,
   когда UV нужен в нашем пайплайне.
5. [05_baking](05_baking.md) — normal (tangent/object), AO, curvature; selected-to-active, cage,
   ray distance, артефакты, DirectX vs OpenGL.
6. [06_blender_automation](06_blender_automation.md) — `bpy`-операторы, параметры, грабли,
   карта «фича → код». Проверено на Blender 5.1.2.

## Главные выводы для продукта
- **Ядро = LOD-генерация** из одного входа. Для неё правильный движок — **Decimate Collapse**
  (сохраняет UV/текстуры, быстро). QuadriFlow — для «чистовой» сетки, требует бейка.
- **Бейк normal map** — отдельный модуль/фича, не обязателен для базового LOD.
- Считать **треугольники**, не «полигоны» — движки меряют так.
- Будущие фичи просятся как «кубики»: препроцессинг-clean, voxel-для-печати, cage-бейк,
  флип нормали DX/GL, пресеты платформ, batch-папки, GUI/аддон.

## Источник истины по версиям
Blender **5.1.2** (build 2026-05-19). При обновлении Blender — гонять смоук-тест
(`make_test_model.py` → `run.py`) и сверять имена операторов (см. грабля №8 в файле 06).
