#!/usr/bin/env python3
"""
Virtual Fence Simulator - Polygonal Fences (Tkinter)
--------------------------------------------------
Features:
 - Draw a polygonal virtual fence by clicking points on the canvas.
 - Start/stop simulation of animals moving with configurable speed and count.
 - Parameters: simulation tick (ms), animal speed multiplier, initial animal count,
   canvas width/height, fence color, animal size.
 - Save/load fence + config to JSON.
 - Export alerts to CSV.
 - Live dashboard showing counts inside/outside and alerts log.
 - Point-in-polygon detection (ray casting).

Usage:
    python3 virtual_fence_simulator_polygonal.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
import random, math, time, csv, json, os

# Default configuration
DEFAULT_CANVAS_W = 900
DEFAULT_CANVAS_H = 600
DEFAULT_TICK_MS = 100
DEFAULT_ANIMAL_COUNT = 8
DEFAULT_SPEED = 1.0
DEFAULT_ANIMAL_SIZE = 6
DEFAULT_FENCE_COLOR = "#2563eb"

class Animal:
    def __init__(self, aid, x, y, speed_multiplier=1.0):
        self.id = aid
        self.x = x
        self.y = y
        # velocity direction random
        angle = random.uniform(0, 2*math.pi)
        self.vx = math.cos(angle)
        self.vy = math.sin(angle)
        self.base_speed = random.uniform(0.6, 1.8)
        self.speed_multiplier = speed_multiplier
        self.inside = True
        self.canvas_obj = None

    def step(self):
        speed = self.base_speed * self.speed_multiplier
        # add small random wandering
        self.vx += random.uniform(-0.25, 0.25)
        self.vy += random.uniform(-0.25, 0.25)
        # normalize
        n = max(1e-6, math.hypot(self.vx, self.vy))
        self.vx = (self.vx / n) * speed
        self.vy = (self.vy / n) * speed
        self.x += self.vx
        self.y += self.vy

class VirtualFenceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Virtual Fence Simulator - Polygonal (Livestock)")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # configuration state (editable)
        self.canvas_w = tk.IntVar(value=DEFAULT_CANVAS_W)
        self.canvas_h = tk.IntVar(value=DEFAULT_CANVAS_H)
        self.tick_ms = tk.IntVar(value=DEFAULT_TICK_MS)
        self.init_animal_count = tk.IntVar(value=DEFAULT_ANIMAL_COUNT)
        self.speed_mul = tk.DoubleVar(value=DEFAULT_SPEED)
        self.animal_size = tk.IntVar(value=DEFAULT_ANIMAL_SIZE)
        self.fence_color = tk.StringVar(value=DEFAULT_FENCE_COLOR)
        self.show_coords = tk.BooleanVar(value=False)

        self._build_ui()
        self.animals = {}
        self.next_animal_id = 1
        self.sim_running = False
        self._job = None
        self.alerts = []  # (timestamp, id, x, y, msg)
        self.polygon_points = []  # list of (x,y) while drawing
        self.fence_polygon_id = None  # canvas polygon id for drawn/active fence

        # draw grid and subscribe
        self._draw_grid()
        # initial animals
        for _ in range(self.init_animal_count.get()):
            self.add_random_animal()

    def _build_ui(self):
        # main layout: canvas left, controls right
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.grid(row=0, column=1, sticky="n", padx=8, pady=8)
        # canvas
        self.canvas = tk.Canvas(self, width=self.canvas_w.get(), height=self.canvas_h.get(), bg="#fbfbfb", bd=2, relief="sunken")
        self.canvas.grid(row=0, column=0, padx=8, pady=8)
        self.canvas.bind("<Button-1>", self.canvas_click)
        self.canvas.bind("<Motion>", self.canvas_motion)

        # Controls: Fence drawing
        ttk.Label(ctrl_frame, text="Fence (polygon) drawing", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        btns = ttk.Frame(ctrl_frame); btns.grid(row=1, column=0, sticky="ew", pady=(4,8))
        self.draw_mode = tk.BooleanVar(value=False)
        self.draw_btn = ttk.Button(btns, text="Start Drawing Fence", command=self.toggle_draw_mode)
        self.draw_btn.grid(row=0, column=0, sticky="ew")
        ttk.Button(btns, text="Finish & Activate", command=self.finish_polygon).grid(row=0, column=1, padx=(6,0))
        ttk.Button(btns, text="Clear Fence", command=self.clear_fence).grid(row=0, column=2, padx=(6,0))

        # polygon helper info
        ttk.Label(ctrl_frame, text="(Click to add points; Finish to activate)").grid(row=2, column=0, sticky="w", pady=(2,8))

        # Parameters section
        ttk.Label(ctrl_frame, text="Parameters", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w")
        pframe = ttk.Frame(ctrl_frame); pframe.grid(row=4, column=0, sticky="ew", pady=(4,8))

        ttk.Label(pframe, text="Canvas W:").grid(row=0, column=0, sticky="w")
        ttk.Entry(pframe, textvariable=self.canvas_w, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(pframe, text="H:").grid(row=0, column=2, sticky="w", padx=(8,0))
        ttk.Entry(pframe, textvariable=self.canvas_h, width=8).grid(row=0, column=3, sticky="w")

        ttk.Label(pframe, text="Tick (ms):").grid(row=1, column=0, sticky="w", pady=(6,0))
        ttk.Entry(pframe, textvariable=self.tick_ms, width=8).grid(row=1, column=1, sticky="w", pady=(6,0))

        ttk.Label(pframe, text="Initial animals:").grid(row=2, column=0, sticky="w", pady=(6,0))
        ttk.Entry(pframe, textvariable=self.init_animal_count, width=8).grid(row=2, column=1, sticky="w", pady=(6,0))

        ttk.Label(pframe, text="Speed multiplier:").grid(row=3, column=0, sticky="w", pady=(6,0))
        ttk.Entry(pframe, textvariable=self.speed_mul, width=8).grid(row=3, column=1, sticky="w", pady=(6,0))

        ttk.Label(pframe, text="Animal size(px):").grid(row=4, column=0, sticky="w", pady=(6,0))
        ttk.Entry(pframe, textvariable=self.animal_size, width=8).grid(row=4, column=1, sticky="w", pady=(6,0))

        ttk.Label(pframe, text="Fence color:").grid(row=5, column=0, sticky="w", pady=(6,0))
        color_frame = ttk.Frame(pframe); color_frame.grid(row=5, column=1, sticky="w")
        self.color_preview = tk.Canvas(color_frame, width=24, height=16, bg=self.fence_color.get(), bd=1, relief="ridge")
        self.color_preview.grid(row=0, column=0)
        ttk.Button(color_frame, text="Choose...", command=self.choose_color).grid(row=0, column=1, padx=(6,0))

        ttk.Checkbutton(pframe, text="Show coords", variable=self.show_coords).grid(row=6, column=0, columnspan=2, pady=(6,0))

        # Simulation control buttons
        sim_frame = ttk.Frame(ctrl_frame); sim_frame.grid(row=5, column=0, sticky="ew", pady=(8,0))
        ttk.Button(sim_frame, text="Apply canvas size", command=self.apply_canvas_size).grid(row=0, column=0, sticky="ew")
        ttk.Button(sim_frame, text="Reset animals to initial count", command=self.reset_animals).grid(row=0, column=1, padx=(6,0))
        start_stop_frame = ttk.Frame(ctrl_frame); start_stop_frame.grid(row=6, column=0, sticky="ew", pady=(8,0))
        self.start_btn = ttk.Button(start_stop_frame, text="Start Simulation", command=self.start_simulation)
        self.start_btn.grid(row=0, column=0, sticky="ew")
        self.stop_btn = ttk.Button(start_stop_frame, text="Stop", command=self.stop_simulation, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=(6,0), sticky="ew")

        # Animal add/remove
        ar_frame = ttk.Frame(ctrl_frame); ar_frame.grid(row=7, column=0, sticky="ew", pady=(8,0))
        ttk.Button(ar_frame, text="Add random animal", command=self.add_random_animal).grid(row=0, column=0, sticky="ew")
        ttk.Button(ar_frame, text="Add at center", command=self.add_animal_at_center).grid(row=0, column=1, padx=(6,0), sticky="ew")
        ttk.Button(ar_frame, text="Remove last", command=self.remove_last_animal).grid(row=0, column=2, padx=(6,0), sticky="ew")

        # Dashboard & logs
        dash_label = ttk.Label(ctrl_frame, text="Dashboard / Logs", font=("Segoe UI", 10, "bold"))
        dash_label.grid(row=8, column=0, sticky="w", pady=(8,0))
        self.status_inside = tk.IntVar(value=0)
        self.status_outside = tk.IntVar(value=0)
        status_frame = ttk.Frame(ctrl_frame); status_frame.grid(row=9, column=0, sticky="ew", pady=(4,0))
        ttk.Label(status_frame, text="Inside:").grid(row=0, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self.status_inside).grid(row=0, column=1, sticky="w", padx=(6,12))
        ttk.Label(status_frame, text="Outside:").grid(row=0, column=2, sticky="w")
        ttk.Label(status_frame, textvariable=self.status_outside).grid(row=0, column=3, sticky="w", padx=(6,0))

        self.log_text = tk.Text(ctrl_frame, width=48, height=12, state="disabled", wrap="word")
        self.log_text.grid(row=10, column=0, pady=(6,0))

        export_frame = ttk.Frame(ctrl_frame); export_frame.grid(row=11, column=0, sticky="ew", pady=(6,0))
        ttk.Button(export_frame, text="Export alerts CSV", command=self.export_csv).grid(row=0, column=0, sticky="ew")
        ttk.Button(export_frame, text="Save config (JSON)", command=self.save_config).grid(row=0, column=1, padx=(6,0))
        ttk.Button(export_frame, text="Load config (JSON)", command=self.load_config).grid(row=0, column=2, padx=(6,0))

        # bottom help
        ttk.Label(ctrl_frame, text="Tip: Draw polygon then Finish & Activate. Animals turn red when outside.").grid(row=12, column=0, sticky="w", pady=(8,0))

    def _draw_grid(self):
        # clear any grid lines (canvas may be resized)
        self.canvas.delete("grid_line")
        step = 50
        w = self.canvas.winfo_reqwidth()
        h = self.canvas.winfo_reqheight()
        for x in range(0, w, step):
            self.canvas.create_line(x, 0, x, h, fill="#f1f5f9", tags=("grid_line",))
        for y in range(0, h, step):
            self.canvas.create_line(0, y, w, y, fill="#f1f5f9", tags=("grid_line",))

    def apply_canvas_size(self):
        w = max(200, int(self.canvas_w.get()))
        h = max(150, int(self.canvas_h.get()))
        self.canvas.config(width=w, height=h)
        self._draw_grid()
        self.log(f"Applied canvas size {w}x{h}")

    def choose_color(self):
        c = colorchooser.askcolor(color=self.fence_color.get(), title="Choose fence color")
        if c and c[1]:
            self.fence_color.set(c[1])
            self.color_preview.config(bg=c[1])
            # update active polygon color if exists
            if self.fence_polygon_id:
                self.canvas.itemconfig(self.fence_polygon_id, outline=self.fence_color.get())

    def toggle_draw_mode(self):
        val = not self.draw_mode.get()
        self.draw_mode.set(val)
        if val:
            self.draw_btn.config(text="Drawing... (Click to add)")
            self.polygon_points = []
            # remove temporary items
            self._clear_temp_shapes()
            self.log("Drawing mode enabled: click on canvas to add polygon vertices.")
        else:
            self.draw_btn.config(text="Start Drawing Fence")
            self.log("Drawing mode disabled. Use Finish & Activate to set fence.")

    def _clear_temp_shapes(self):
        # remove small markers for points
        self.canvas.delete("poly_point")
        self.canvas.delete("poly_line")
        self.canvas.delete("poly_preview_text")

    def canvas_click(self, event):
        if self.draw_mode.get():
            # add point
            self.polygon_points.append((event.x, event.y))
            # draw small marker
            r = 3
            self.canvas.create_oval(event.x-r, event.y-r, event.x+r, event.y+r, fill="#111827", tags=("poly_point",))
            # draw lines between points
            if len(self.polygon_points) > 1:
                pts = self.polygon_points
                x1,y1 = pts[-2]; x2,y2 = pts[-1]
                self.canvas.create_line(x1,y1,x2,y2, width=2, dash=(2,2), tags=("poly_line",))
            self.log(f"Added polygon point ({event.x},{event.y})")
        else:
            # not in draw mode: maybe show clicked animal info / select
            clicked = self.canvas.find_closest(event.x, event.y)
            if clicked:
                # check if clicked item corresponds to an animal (by tag)
                tags = self.canvas.gettags(clicked)
            # no action for now
            pass

    def canvas_motion(self, event):
        # show coords on canvas if enabled
        self.canvas.delete("mouse_coords")
        if self.show_coords.get():
            self.canvas.create_text(event.x+10, event.y+10, text=f"{event.x},{event.y}", anchor="nw", tags=("mouse_coords",), font=("Segoe UI",8), fill="#0f172a")

    def finish_polygon(self):
        if len(self.polygon_points) < 3:
            messagebox.showwarning("Invalid polygon", "A polygon needs at least 3 points.")
            return
        # remove existing fence polygon if any
        if self.fence_polygon_id:
            self.canvas.delete(self.fence_polygon_id)
            self.fence_polygon_id = None
        # draw filled polygon with outline
        flat = [coord for pt in self.polygon_points for coord in pt]
        self.fence_polygon_id = self.canvas.create_polygon(*flat, outline=self.fence_color.get(), width=3, fill="", dash=(6,4), tags=("fence",))
        self._clear_temp_shapes()
        self.draw_mode.set(False)
        self.draw_btn.config(text="Start Drawing Fence")
        self.log(f"Fence activated with {len(self.polygon_points)} vertices.")

    def clear_fence(self):
        if self.fence_polygon_id:
            self.canvas.delete(self.fence_polygon_id)
            self.fence_polygon_id = None
        self.polygon_points = []
        self._clear_temp_shapes()
        self.log("Fence cleared.")

    def add_random_animal(self):
        w = int(self.canvas.cget("width"))
        h = int(self.canvas.cget("height"))
        # spawn away from edges
        x = random.uniform(40, max(40, w-40))
        y = random.uniform(40, max(40, h-40))
        self._create_animal(x, y)

    def add_animal_at_center(self):
        w = int(self.canvas.cget("width"))
        h = int(self.canvas.cget("height"))
        self._create_animal(w/2 + random.uniform(-10,10), h/2 + random.uniform(-10,10))

    def _create_animal(self, x, y):
        aid = self.next_animal_id
        self.next_animal_id += 1
        a = Animal(aid, x, y, speed_multiplier=self.speed_mul.get())
        r = self.animal_size.get()
        a.canvas_obj = self.canvas.create_oval(a.x-r, a.y-r, a.x+r, a.y+r, fill="#10b981", outline="#065f46", width=1, tags=(f"animal_{aid}",))
        self.animals[aid] = a
        self.log(f"Added animal #{aid} at ({int(a.x)},{int(a.y)})")
        self._update_counts()

    def remove_last_animal(self):
        if not self.animals:
            return
        last = max(self.animals.keys())
        a = self.animals.pop(last)
        if a.canvas_obj:
            self.canvas.delete(a.canvas_obj)
        self.log(f"Removed animal #{last}")
        self._update_counts()

    def reset_animals(self):
        # remove all and add initial number
        for a in list(self.animals.values()):
            if a.canvas_obj:
                self.canvas.delete(a.canvas_obj)
        self.animals = {}
        self.next_animal_id = 1
        for _ in range(max(0, int(self.init_animal_count.get()))):
            self.add_random_animal()
        self.log("Reset animals to initial count.")
        self._update_counts()

    def start_simulation(self):
        if self.sim_running:
            return
        self.sim_running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        # apply speed multiplier to animals
        for a in self.animals.values():
            a.speed_multiplier = self.speed_mul.get()
        self._tick_loop()

    def stop_simulation(self):
        if not self.sim_running:
            return
        self.sim_running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        if self._job:
            self.after_cancel(self._job)
            self._job = None

    def _tick_loop(self):
        # update all animals and check polygon inclusion
        for a in list(self.animals.values()):
            a.step()
            # keep inside canvas with soft bounce
            w = int(self.canvas.cget("width"))
            h = int(self.canvas.cget("height"))
            if a.x < 5: a.x = 5; a.vx *= -0.6
            if a.x > w-5: a.x = w-5; a.vx *= -0.6
            if a.y < 5: a.y = 5; a.vy *= -0.6
            if a.y > h-5: a.y = h-5; a.vy *= -0.6
            # determine if inside fence polygon (if exists)
            inside = True
            if self.fence_polygon_id or len(self.polygon_points) >= 3:
                poly = self.polygon_points if self.polygon_points and self.fence_polygon_id is None else self._get_active_polygon_points()
                inside = self.point_in_polygon(a.x, a.y, poly) if poly else True
            # update drawing and state
            r = self.animal_size.get()
            color = "#10b981" if inside else "#ef4444"
            outline = "#065f46" if inside else "#7f1d1d"
            self.canvas.coords(a.canvas_obj, a.x-r, a.y-r, a.x+r, a.y+r)
            self.canvas.itemconfig(a.canvas_obj, fill=color, outline=outline)
            if not inside and a.inside:
                # left
                a.inside = False
                msg = f"Animal #{a.id} LEFT fence at ({int(a.x)},{int(a.y)})"
                self.alerts.append((time.strftime("%Y-%m-%d %H:%M:%S"), a.id, int(a.x), int(a.y), msg))
                self.log(msg)
                # non-blocking popup
                self.after(10, lambda m=msg: messagebox.showwarning("ALERT", m))
            if inside and not a.inside:
                a.inside = True
                msg = f"Animal #{a.id} re-entered fence at ({int(a.x)},{int(a.y)})"
                self.alerts.append((time.strftime("%Y-%m-%d %H:%M:%S"), a.id, int(a.x), int(a.y), msg))
                self.log(msg)
        self._update_counts()
        if self.sim_running:
            self._job = self.after(max(10, int(self.tick_ms.get())), self._tick_loop)

    def _get_active_polygon_points(self):
        if self.fence_polygon_id and self.polygon_points:
            return self.polygon_points
        return None

    def point_in_polygon(self, x, y, poly):
        # Ray casting algorithm for point-in-polygon
        # poly = list of (x,y) tuples
        if not poly: return True
        inside = False
        n = len(poly)
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]; xj, yj = poly[j]
            intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
            if intersect:
                inside = not inside
            j = i
        return inside

    def _update_counts(self):
        inside = sum(1 for a in self.animals.values() if getattr(a, "inside", True))
        outside = max(0, len(self.animals) - inside)
        self.status_inside.set(inside)
        self.status_outside.set(outside)

    def log(self, text):
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {text}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def export_csv(self):
        if not self.alerts:
            messagebox.showinfo("Export", "No alerts to export.")
            return
        fpath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files","*.csv")], initialfile="virtual_fence_alerts.csv")
        if not fpath: return
        try:
            with open(fpath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp","animal_id","x","y","message"])
                for row in self.alerts:
                    writer.writerow(row)
            messagebox.showinfo("Export", f"Exported alerts to {fpath}")
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def save_config(self):
        cfg = {
            "canvas_w": int(self.canvas.cget("width")),
            "canvas_h": int(self.canvas.cget("height")),
            "tick_ms": int(self.tick_ms.get()),
            "init_animal_count": int(self.init_animal_count.get()),
            "speed_mul": float(self.speed_mul.get()),
            "animal_size": int(self.animal_size.get()),
            "fence_color": self.fence_color.get(),
            "polygon_points": self.polygon_points,
            "animals": [(a.id, a.x, a.y, a.base_speed, a.speed_multiplier) for a in self.animals.values()]
        }
        fpath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files","*.json")], initialfile="virtual_fence_config.json")
        if not fpath: return
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            messagebox.showinfo("Save", f"Config saved to {fpath}")
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    def load_config(self):
        fpath = filedialog.askopenfilename(filetypes=[("JSON files","*.json")])
        if not fpath: return
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # apply canvas size
            self.canvas.config(width=cfg.get("canvas_w", self.canvas_w.get()), height=cfg.get("canvas_h", self.canvas_h.get()))
            self.canvas_w.set(cfg.get("canvas_w", self.canvas_w.get()))
            self.canvas_h.set(cfg.get("canvas_h", self.canvas_h.get()))
            self.tick_ms.set(cfg.get("tick_ms", self.tick_ms.get()))
            self.init_animal_count.set(cfg.get("init_animal_count", self.init_animal_count.get()))
            self.speed_mul.set(cfg.get("speed_mul", self.speed_mul.get()))
            self.animal_size.set(cfg.get("animal_size", self.animal_size.get()))
            self.fence_color.set(cfg.get("fence_color", self.fence_color.get()))
            self.color_preview.config(bg=self.fence_color.get())
            pts = cfg.get("polygon_points", [])
            self.polygon_points = [(float(x), float(y)) for x,y in pts] if pts else []
            # redraw fence
            if self.fence_polygon_id:
                self.canvas.delete(self.fence_polygon_id)
                self.fence_polygon_id = None
            if len(self.polygon_points) >= 3:
                flat = [coord for pt in self.polygon_points for coord in pt]
                self.fence_polygon_id = self.canvas.create_polygon(*flat, outline=self.fence_color.get(), width=3, fill="", dash=(6,4), tags=("fence",))
            # load animals (replace existing)
            for a in list(self.animals.values()):
                if a.canvas_obj: self.canvas.delete(a.canvas_obj)
            self.animals = {}
            self.next_animal_id = 1
            for entry in cfg.get("animals", []):
                try:
                    aid, x, y, base, mult = entry
                    self._create_animal(float(x), float(y))
                    # update base speed if desired
                    new = self.animals[self.next_animal_id-1]
                    new.base_speed = float(base)
                    new.speed_multiplier = float(mult)
                except Exception:
                    continue
            self.log(f"Config loaded from {fpath}")
            self._update_counts()
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def on_close(self):
        if self.sim_running and not messagebox.askokcancel("Quit", "Simulation running. Quit anyway?"): return
        self.stop_simulation()
        self.destroy()

def main():
    app = VirtualFenceApp()
    app.mainloop()

if __name__ == "__main__":
    main()
