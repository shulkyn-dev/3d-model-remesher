r"""
run.py — обёртка "перестройщика". Находит Blender и генерит LOD-уровни.

Примеры:
    # 3 уровня (50%, 25%, 10%) в FBX:
    python run.py input/model.glb

    # свои уровни и метки, экспорт в FBX + GLB:
    python run.py input/model.glb --levels 0.5,0.2,0.05 --names high,mid,low --formats fbx,glb

    # целевые полигоны вместо долей:
    python run.py input/model.fbx --levels 20000,5000,1000

    # чистая quad-ретопология + запекание normal map:
    python run.py input/model.glb --method quad --bake --bake-ao

Если Blender не в PATH:
    set BLENDER_PATH=C:\Program Files\Blender Foundation\Blender 4.2\blender.exe
"""

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_SCRIPT = os.path.join(HERE, "blender_scripts", "optimize.py")


def find_blender():
    env = os.environ.get("BLENDER_PATH")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("blender")
    if found:
        return found
    candidates = []
    for base in (
        r"C:\Program Files\Blender Foundation",
        r"C:\Program Files (x86)\Blender Foundation",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation"),
    ):
        if os.path.isdir(base):
            for d in os.listdir(base):
                exe = os.path.join(base, d, "blender.exe")
                if os.path.isfile(exe):
                    candidates.append(exe)
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0]
    return None


def main():
    p = argparse.ArgumentParser(description="Перестройщик 3D-моделей: high -> LOD (Blender headless)")
    p.add_argument("input", help="путь к исходной high-poly модели")
    p.add_argument("--outdir", help="папка результатов (по умолчанию output/<имя>/)")
    p.add_argument("--basename", help="базовое имя файлов (по умолчанию имя входного)")
    p.add_argument("--levels", default="0.5,0.25,0.1",
                   help="доли (<=1) или целевые полигоны (>1), через запятую")
    p.add_argument("--names", default="", help="метки уровней, напр. high,mid,low")
    p.add_argument("--formats", default="fbx", help="fbx,glb,gltf,obj")
    p.add_argument("--method", default="collapse", choices=["collapse", "planar", "quad"])
    p.add_argument("--bake", action="store_true")
    p.add_argument("--bake-ao", action="store_true")
    p.add_argument("--bake-size", type=int, default=2048)
    args = p.parse_args()

    blender = find_blender()
    if not blender:
        sys.exit(
            "Blender не найден. Установи (winget install BlenderFoundation.Blender) "
            "или задай путь:\n"
            "  set BLENDER_PATH=C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe"
        )
    print(f"Blender: {blender}")

    inp = os.path.abspath(args.input)
    if not os.path.isfile(inp):
        sys.exit(f"Файл не найден: {inp}")

    basename = args.basename or os.path.splitext(os.path.basename(inp))[0]
    outdir = os.path.abspath(args.outdir) if args.outdir else os.path.join(HERE, "output", basename)

    cmd = [
        blender, "--background", "--python", BLENDER_SCRIPT, "--",
        "--input", inp,
        "--outdir", outdir,
        "--basename", basename,
        "--levels", args.levels,
        "--names", args.names,
        "--formats", args.formats,
        "--method", args.method,
        "--bake-size", str(args.bake_size),
    ]
    if args.bake:
        cmd.append("--bake")
    if args.bake_ao:
        cmd.append("--bake-ao")

    print("Запуск:", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
