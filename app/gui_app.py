"""
3D Retopo Optimizer — мини-приложение (standalone).
Окно с настройками; Blender работает СКРЫТО в фоне как движок.
Пользователь не открывает Blender — просто выбирает модель и жмёт кнопку.

Запуск:
    python app/gui_app.py
"""
import os
import sys
import shutil
import threading
import queue
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "engine_headless.py")


def find_blender():
    env = os.environ.get("BLENDER_PATH")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("blender")
    if found:
        return found
    cands = []
    for base in (
        r"C:\Program Files\Blender Foundation",
        r"C:\Program Files (x86)\Blender Foundation",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation"),
    ):
        if os.path.isdir(base):
            for d in os.listdir(base):
                exe = os.path.join(base, d, "blender.exe")
                if os.path.isfile(exe):
                    cands.append(exe)
    cands.sort(reverse=True)
    return cands[0] if cands else None


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.proc = None
        self.last_outdir = None
        self.blender = find_blender()

        root.title("3D Retopo Optimizer")
        root.geometry("680x680")
        root.minsize(620, 600)

        pad = dict(padx=8, pady=4)

        # --- статус Blender ---
        top = ttk.Frame(root)
        top.pack(fill="x", **pad)
        b_ok = self.blender is not None
        ttk.Label(top, text="Движок Blender:").pack(side="left")
        ttk.Label(top, text=(self.blender if b_ok else "НЕ НАЙДЕН — задай BLENDER_PATH"),
                  foreground=("green" if b_ok else "red")).pack(side="left", padx=6)

        # --- вход ---
        f_in = ttk.LabelFrame(root, text="1. Модель (high-poly)")
        f_in.pack(fill="x", **pad)
        self.in_var = tk.StringVar()
        ttk.Entry(f_in, textvariable=self.in_var).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(f_in, text="Обзор…", command=self.pick_input).pack(side="left", padx=6)

        # --- выход ---
        f_out = ttk.LabelFrame(root, text="2. Папка результата")
        f_out.pack(fill="x", **pad)
        self.out_var = tk.StringVar()
        ttk.Entry(f_out, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(f_out, text="Обзор…", command=self.pick_output).pack(side="left", padx=6)

        # --- настройки ---
        f_s = ttk.LabelFrame(root, text="3. Настройки")
        f_s.pack(fill="x", **pad)

        r1 = ttk.Frame(f_s); r1.pack(fill="x", pady=3)
        ttk.Label(r1, text="Метод:").pack(side="left", padx=6)
        self.method = tk.StringVar(value="QUAD")
        ttk.Combobox(r1, textvariable=self.method, width=12, state="readonly",
                     values=["QUAD", "COLLAPSE", "PLANAR"]).pack(side="left", padx=6)
        ttk.Label(r1, text="Target polygons:").pack(side="left", padx=12)
        self.target = tk.IntVar(value=5000)
        ttk.Spinbox(r1, from_=50, to=2000000, increment=1000, textvariable=self.target,
                    width=10).pack(side="left", padx=6)

        r2 = ttk.Frame(f_s); r2.pack(fill="x", pady=3)
        self.symmetry = tk.BooleanVar(value=True)
        self.preserve = tk.BooleanVar(value=True)
        self.mark_sharp = tk.BooleanVar(value=False)
        ttk.Checkbutton(r2, text="Symmetry", variable=self.symmetry).pack(side="left", padx=6)
        ttk.Checkbutton(r2, text="Preserve form (Shrinkwrap)", variable=self.preserve).pack(side="left", padx=6)
        ttk.Checkbutton(r2, text="Preserve hard edges", variable=self.mark_sharp).pack(side="left", padx=6)

        r3 = ttk.Frame(f_s); r3.pack(fill="x", pady=3)
        self.bake = tk.BooleanVar(value=True)
        self.bake_ao = tk.BooleanVar(value=False)
        ttk.Checkbutton(r3, text="Bake Normal", variable=self.bake).pack(side="left", padx=6)
        ttk.Checkbutton(r3, text="+ AO", variable=self.bake_ao).pack(side="left", padx=6)
        ttk.Label(r3, text="Texture:").pack(side="left", padx=12)
        self.bake_size = tk.StringVar(value="2048")
        ttk.Combobox(r3, textvariable=self.bake_size, width=6, state="readonly",
                     values=["1024", "2048", "4096"]).pack(side="left", padx=6)

        r5 = ttk.Frame(f_s); r5.pack(fill="x", pady=3)
        ttk.Label(r5, text="Weld distance, %:").pack(side="left", padx=6)
        self.weld = tk.DoubleVar(value=0.05)
        ttk.Spinbox(r5, from_=0.0, to=2.0, increment=0.01, textvariable=self.weld,
                    width=7, format="%.2f").pack(side="left", padx=6)
        ttk.Label(r5, text="(закрывает дыры; 0 = выкл)").pack(side="left", padx=4)

        r6 = ttk.Frame(f_s); r6.pack(fill="x", pady=3)
        ttk.Label(r6, text="Export scale:").pack(side="left", padx=6)
        self.escale = tk.DoubleVar(value=1.0)
        ttk.Spinbox(r6, from_=0.0001, to=1000.0, increment=0.01, textvariable=self.escale,
                    width=10, format="%.4f").pack(side="left", padx=6)
        ttk.Label(r6, text="(если результат в 100x — поставь 0.01)").pack(side="left", padx=4)

        r4 = ttk.Frame(f_s); r4.pack(fill="x", pady=3)
        ttk.Label(r4, text="Форматы:").pack(side="left", padx=6)
        self.fmt_fbx = tk.BooleanVar(value=True)
        self.fmt_glb = tk.BooleanVar(value=True)
        self.fmt_gltf = tk.BooleanVar(value=False)
        self.fmt_obj = tk.BooleanVar(value=False)
        ttk.Checkbutton(r4, text="FBX", variable=self.fmt_fbx).pack(side="left", padx=6)
        ttk.Checkbutton(r4, text="GLB", variable=self.fmt_glb).pack(side="left", padx=6)
        ttk.Checkbutton(r4, text="GLTF", variable=self.fmt_gltf).pack(side="left", padx=6)
        ttk.Checkbutton(r4, text="OBJ", variable=self.fmt_obj).pack(side="left", padx=6)

        # --- кнопка ---
        self.run_btn = ttk.Button(root, text="▶  Оптимизировать", command=self.run)
        self.run_btn.pack(fill="x", padx=8, pady=8)

        # --- лог ---
        f_log = ttk.LabelFrame(root, text="Процесс")
        f_log.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(f_log, height=12, wrap="word", state="disabled",
                           bg="#1e1e1e", fg="#dcdcdc")
        self.log.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb = ttk.Scrollbar(f_log, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log["yscrollcommand"] = sb.set

        # --- низ ---
        bot = ttk.Frame(root)
        bot.pack(fill="x", **pad)
        self.status = ttk.Label(bot, text="Готов")
        self.status.pack(side="left", padx=6)
        self.open_btn = ttk.Button(bot, text="Открыть папку результата",
                                   command=self.open_out, state="disabled")
        self.open_btn.pack(side="right", padx=6)

        self.root.after(100, self.poll_queue)

    # ---------- handlers ----------
    def pick_input(self):
        p = filedialog.askopenfilename(
            title="Выбери модель",
            filetypes=[("3D модели", "*.glb *.gltf *.fbx *.obj *.stl"), ("Все файлы", "*.*")])
        if p:
            self.in_var.set(p)
            base = os.path.splitext(os.path.basename(p))[0]
            self.out_var.set(os.path.join(os.path.dirname(p), base + "_retopo"))

    def pick_output(self):
        p = filedialog.askdirectory(title="Папка результата")
        if p:
            self.out_var.set(p)

    def write(self, line):
        self.log["state"] = "normal"
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log["state"] = "disabled"

    def run(self):
        if not self.blender:
            messagebox.showerror("Blender", "Blender не найден. Задай переменную BLENDER_PATH.")
            return
        inp = self.in_var.get().strip()
        outdir = self.out_var.get().strip()
        if not inp or not os.path.isfile(inp):
            messagebox.showerror("Вход", "Выбери корректный файл модели.")
            return
        if not outdir:
            messagebox.showerror("Выход", "Укажи папку результата.")
            return
        formats = []
        if self.fmt_fbx.get(): formats.append("fbx")
        if self.fmt_glb.get(): formats.append("glb")
        if self.fmt_gltf.get(): formats.append("gltf")
        if self.fmt_obj.get(): formats.append("obj")
        if not formats:
            messagebox.showerror("Форматы", "Выбери хотя бы один формат.")
            return

        os.makedirs(outdir, exist_ok=True)
        self.last_outdir = outdir
        base = os.path.splitext(os.path.basename(inp))[0]

        cmd = [
            self.blender, "--background", "--python", ENGINE, "--",
            "--input", inp, "--outdir", outdir, "--basename", base,
            "--method", self.method.get(), "--target", str(self.target.get()),
            "--formats", ",".join(formats),
            "--symmetry", "1" if self.symmetry.get() else "0",
            "--preserve-form", "1" if self.preserve.get() else "0",
            "--bake", "1" if self.bake.get() else "0",
            "--bake-ao", "1" if self.bake_ao.get() else "0",
            "--bake-size", self.bake_size.get(),
            "--mark-sharp", "1" if self.mark_sharp.get() else "0",
            "--merge", str(self.weld.get() / 100.0),
            "--scale", str(self.escale.get()),
        ]

        self.run_btn["state"] = "disabled"
        self.open_btn["state"] = "disabled"
        self.status["text"] = "Обработка… (Blender работает в фоне)"
        self.write(f"▶ запуск: {base}  [{self.method.get()}, target {self.target.get()}]")

        threading.Thread(target=self._worker, args=(cmd,), daemon=True).start()

    def _worker(self, cmd):
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in self.proc.stdout:
                line = line.rstrip()
                if any(t in line for t in ("[engine]", "[retopo]", "Error", "Traceback",
                                           "Exception", "Warning")):
                    self.q.put(("log", line.replace("[engine] ", "").replace("[retopo] ", "  · ")))
            self.proc.wait()
            self.q.put(("done", self.proc.returncode))
        except Exception as e:
            self.q.put(("log", f"ОШИБКА запуска: {e}"))
            self.q.put(("done", -1))

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.write(payload)
                elif kind == "done":
                    self.run_btn["state"] = "normal"
                    if payload == 0:
                        self.status["text"] = "Готово ✓"
                        self.open_btn["state"] = "normal"
                    else:
                        self.status["text"] = f"Ошибка (код {payload})"
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def open_out(self):
        if self.last_outdir and os.path.isdir(self.last_outdir):
            try:
                os.startfile(self.last_outdir)  # Windows
            except AttributeError:
                subprocess.call(["xdg-open", self.last_outdir])


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
