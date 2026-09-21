import os
import re
import math
import colorsys
import logging
import json
import zipfile
import io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageTk, ImageOps, ImageChops

# -------------------------------------------------------------------------
# HELPER CLASSES FOR SPRITES & UI
# -------------------------------------------------------------------------
class PlaceholderEntry(ttk.Entry):
    def __init__(self, container, placeholder, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.placeholder = placeholder
        self.is_placeholder = True
        self.insert("0", self.placeholder)
        self.bind("<FocusIn>", self._clear_placeholder)
        self.bind("<FocusOut>", self._add_placeholder)
        self.config(foreground="grey")

    def _clear_placeholder(self, e):
        if self.is_placeholder:
            self.delete("0", "end")
            self.config(foreground="black")
            self.is_placeholder = False

    def _add_placeholder(self, e):
        if not self.get():
            self.is_placeholder = True
            self.insert("0", self.placeholder)
            self.config(foreground="grey")

    def get_value(self):
        return "" if self.is_placeholder else self.get()

    def set_value(self, text):
        self.delete("0", "end")
        if text:
            self.is_placeholder = False
            self.insert("0", text)
            self.config(foreground="black")
        else:
            self.is_placeholder = True
            self.insert("0", self.placeholder)
            self.config(foreground="grey")


class YuyaTreeview(ttk.Treeview):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_drop)
        # Handle explicitly Ctrl+Shift+Click to act like Shift+Click
        self.bind("<Control-Shift-Button-1>", lambda e: self.event_generate("<Shift-Button-1>", x=e.x, y=e.y))
        
        self.drag_item = None
        self.start_x = 0
        self.start_y = 0

    def on_press(self, event):
        item = self.identify_row(event.y)
        self.start_x = event.x
        self.start_y = event.y
        if item:
            tags = self.item(item, "tags")
            if "file" in tags: 
                self.drag_item = item

    def on_drag(self, event):
        if self.drag_item: 
            # Seuil de mouvement de 5 pixels pour déclencher le drag.
            if abs(event.x - self.start_x) > 5 or abs(event.y - self.start_y) > 5:
                self.configure(cursor="hand2")

    def on_drop(self, event):
        self.configure(cursor="")
        if not self.drag_item: return
        
        if abs(event.x - self.start_x) <= 5 and abs(event.y - self.start_y) <= 5:
            self.drag_item = None
            return

        target = self.identify_row(event.y)
        if target and target != self.drag_item:
            sel = self.selection()
            if self.drag_item in sel:
                items_to_move = sel
            else:
                items_to_move = [self.drag_item]
                
            ttags = self.item(target, "tags")
            if "group" in ttags:
                for it in items_to_move:
                    if "file" in self.item(it, "tags"):
                        self.move(it, target, "end")
            elif "file" in ttags:
                parent = self.parent(target)
                idx = self.index(target)
                for it in items_to_move:
                    if "file" in self.item(it, "tags"):
                        self.move(it, parent, idx)
                        idx += 1
            self.event_generate("<<TreeOrderChanged>>")
        self.drag_item = None


class PopupColorEditor(tk.Toplevel):
    def __init__(self, parent, index, initial_rgba, on_update_cb, on_apply_cb, on_cancel_cb):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.config(bg="#f0f0f0", bd=2, relief="raised")
        self.index = index; self.initial_rgba = initial_rgba; self.current_rgba = list(initial_rgba)
        self.on_update = on_update_cb; self.on_apply = on_apply_cb; self.on_cancel = on_cancel_cb
        self.ignore_event = False 
        self.setup_ui(); self.sync_ui_from_rgba()
        self.bind("<Button-1>", self.on_click_inside); self.bind_all("<Button-1>", self.on_click_outside, add="+"); self.focus_force()

    def setup_ui(self):
        top = tk.Frame(self, bg="#f0f0f0"); top.pack(fill="x", padx=5, pady=5)
        tk.Label(top, text="#", bg="#f0f0f0", font=("Consolas", 10, "bold")).pack(side="left")
        self.hex_var = tk.StringVar(); self.hex_var.trace("w", self.on_hex_change)
        tk.Entry(top, textvariable=self.hex_var, width=8, font=("Consolas", 10)).pack(side="left")
        self.swatch = tk.Label(top, width=6, relief="sunken", bg="black"); self.swatch.pack(side="right", padx=(10,0))
        sliders = tk.Frame(self, bg="#f0f0f0"); sliders.pack(fill="x", padx=5)
        self.rgb_vars = []
        for i, lab in enumerate("RGB"):
            f = tk.Frame(sliders, bg="#f0f0f0"); f.pack(fill="x", pady=1)
            tk.Label(f, text=lab, width=2, bg="#f0f0f0", font=("Arial", 8)).pack(side="left")
            var = tk.IntVar(); self.rgb_vars.append(var)
            s = tk.Scale(f, from_=0, to=255, orient="horizontal", variable=var, showvalue=0, bg="#f0f0f0", length=120, command=lambda v, c=i: self.on_rgb_slide())
            s.pack(side="left", padx=2); s.bind("<Double-Button-1>", lambda e, c=i: self.reset_channel(c))
            e = tk.Entry(f, textvariable=var, width=4, font=("Arial", 8)); e.pack(side="left"); e.bind("<Return>", lambda e: self.on_rgb_slide())
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=5)
        self.hsl_vars = []
        for i, (lab, maxi) in enumerate([("H", 360), ("S", 100), ("L", 100)]):
            f = tk.Frame(sliders, bg="#f0f0f0"); f.pack(fill="x", pady=1)
            tk.Label(f, text=lab, width=2, bg="#f0f0f0", font=("Arial", 8)).pack(side="left")
            var = tk.IntVar(); self.hsl_vars.append(var)
            s = tk.Scale(f, from_=0, to=maxi, orient="horizontal", variable=var, showvalue=0, bg="#f0f0f0", length=120, command=lambda v: self.on_hsl_slide())
            s.pack(side="left", padx=2); s.bind("<Double-Button-1>", lambda e, c=i: self.reset_hsl())
            e = tk.Entry(f, textvariable=var, width=4, font=("Arial", 8)); e.pack(side="left"); e.bind("<Return>", lambda e: self.on_hsl_slide())
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=5)
        f = tk.Frame(sliders, bg="#f0f0f0"); f.pack(fill="x", pady=1)
        tk.Label(f, text="A", width=2, bg="#f0f0f0", font=("Arial", 8)).pack(side="left")
        self.alpha_var = tk.IntVar(value=100)
        s = tk.Scale(f, from_=0, to=100, orient="horizontal", variable=self.alpha_var, showvalue=0, bg="#f0f0f0", length=120, command=lambda v: self.on_alpha_slide())
        s.pack(side="left", padx=2); s.bind("<Double-Button-1>", lambda e: self.reset_alpha())
        e = tk.Entry(f, textvariable=self.alpha_var, width=4, font=("Arial", 8)); e.pack(side="left"); e.bind("<Return>", lambda e: self.on_alpha_slide())
        btns = tk.Frame(self, bg="#f0f0f0"); btns.pack(fill="x", padx=5, pady=10)
        tk.Button(btns, text="Apply", bg="#ccffcc", command=self.do_apply, width=8).pack(side="left", padx=2)
        tk.Button(btns, text="Cancel", command=self.do_cancel, width=8).pack(side="right", padx=2)

    def sync_ui_from_rgba(self):
        self.ignore_event = True
        r, g, b, a = self.current_rgba
        for i in range(3): self.rgb_vars[i].set(self.current_rgba[i])
        h_str = f"{r:02x}{g:02x}{b:02x}".upper(); self.hex_var.set(h_str); self.swatch.config(bg=f"#{h_str}")
        h, l, s = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
        self.hsl_vars[0].set(int(h * 360)); self.hsl_vars[1].set(int(s * 100)); self.hsl_vars[2].set(int(l * 100))
        self.alpha_var.set(int((a / 255.0) * 100))
        self.ignore_event = False

    def on_rgb_slide(self):
        if self.ignore_event: return
        self.current_rgba = [v.get() for v in self.rgb_vars] + [self.current_rgba[3]]
        self.sync_ui_from_rgba(); self.on_update(self.index, tuple(self.current_rgba))

    def on_hsl_slide(self):
        if self.ignore_event: return
        h = self.hsl_vars[0].get() / 360.0; s = self.hsl_vars[1].get() / 100.0; l = self.hsl_vars[2].get() / 100.0
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        self.current_rgba = [int(r*255), int(g*255), int(b*255), self.current_rgba[3]]
        self.sync_ui_from_rgba(); self.on_update(self.index, tuple(self.current_rgba))

    def on_alpha_slide(self):
        if self.ignore_event: return
        a_val = int((self.alpha_var.get() / 100.0) * 255)
        self.current_rgba[3] = a_val
        self.on_update(self.index, tuple(self.current_rgba))

    def on_hex_change(self, *args):
        if self.ignore_event: return
        val = self.hex_var.get()
        if len(val) == 6:
            try:
                r, g, b = int(val[0:2], 16), int(val[2:4], 16), int(val[4:6], 16)
                self.current_rgba = [r, g, b, self.current_rgba[3]]
                self.sync_ui_from_rgba(); self.on_update(self.index, tuple(self.current_rgba))
            except: pass

    def reset_channel(self, idx):
        self.current_rgba[idx] = self.initial_rgba[idx]; self.sync_ui_from_rgba(); self.on_update(self.index, tuple(self.current_rgba))
    def reset_hsl(self):
        a = self.current_rgba[3]; self.current_rgba = list(self.initial_rgba); self.current_rgba[3] = a
        self.sync_ui_from_rgba(); self.on_update(self.index, tuple(self.current_rgba))
    def reset_alpha(self):
        self.current_rgba[3] = self.initial_rgba[3]; self.sync_ui_from_rgba(); self.on_update(self.index, tuple(self.current_rgba))
    def on_click_inside(self, event): return "break" 
    def on_click_outside(self, event):
        try:
            if event.widget.winfo_toplevel() != self: self.do_cancel()
        except: pass
    def do_apply(self):
        self.unbind_all("<Button-1>"); self.on_apply(self.index, tuple(self.current_rgba)); self.destroy()
    def do_cancel(self):
        self.unbind_all("<Button-1>"); self.on_cancel(self.index); self.destroy()

# -------------------------------------------------------------------------
# TAB SPRITES CLASS
# -------------------------------------------------------------------------
class SpriteEditorTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        
        self.anim_data = {} 
        self.palette_data = [] 
        self.palette_alphas = [] 
        
        self.is_playing = False
        self.current_frame_list = []
        self.current_frame_index = 0
        
        self.zoom_level = 1.0
        self.zoom_auto_var = tk.BooleanVar(value=False)
        self.framerate_ms_var = tk.StringVar(value="100") 
        
        self.selected_indices = set()
        self.reference_color_index = -1 
        self.palette_snapshot = None 
        self.active_popup = None 
        
        self.history = []
        self.history_index = -1
        
        self.last_open_dir = os.path.expanduser("~")
        
        self.preset_files = {}
        self.clipboard_frames = []
        
        self.notification_job = None
        
        self.build_ui()

    def show_notification(self, message, duration=15000):
        """Affiche un message temporaire non intrusif en bas de l'écran."""
        self.lbl_notification.config(text=message)
        if self.notification_job:
            self.parent.after_cancel(self.notification_job)
        self.notification_job = self.parent.after(duration, lambda: self.lbl_notification.config(text=""))

    # --- PROJECT IMPORT / EXPORT METHODS ---
    def export_project(self):
        if not self.anim_data:
            messagebox.showinfo("Export", "No project data to export.")
            return
            
        f = filedialog.asksaveasfilename(defaultextension=".vsp", filetypes=[("VCMI Sprite Project", "*.vsp")])
        if not f: return
        
        try:
            with zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED) as zf:
                state = {
                    "rgb": list(self.palette_data),
                    "alpha": list(self.palette_alphas) if self.palette_alphas else [255]*256,
                    "tree": self.get_tree_state(),
                    "project_name": self.proj_name_entry.get_value()
                }
                zf.writestr("project.json", json.dumps(state))

                pal_img = Image.new("P", (1,1))
                pal_img.putpalette(self.palette_data)

                for fname, d in self.anim_data.items():
                    idx_bytes = io.BytesIO()
                    d["idx"].putpalette(self.palette_data) 
                    d["idx"].save(idx_bytes, format="PNG")
                    zf.writestr(f"images/{fname}_idx.png", idx_bytes.getvalue())

                    alpha_bytes = io.BytesIO()
                    d["alpha"].save(alpha_bytes, format="PNG")
                    zf.writestr(f"images/{fname}_alpha.png", alpha_bytes.getvalue())
                    
            self.show_notification("Projet exporté avec succès (.vsp).")
        except Exception as e:
            logging.error(f"Export project error: {e}", exc_info=True)
            messagebox.showerror("Error", str(e))

    def import_project(self):
        f = filedialog.askopenfilename(filetypes=[("VCMI Sprite Project", "*.vsp")])
        if not f: return
        
        try:
            with zipfile.ZipFile(f, 'r') as zf:
                state = json.loads(zf.read("project.json"))

                self.palette_data = state.get("rgb", [])
                self.palette_alphas = state.get("alpha", [])

                pname = state.get("project_name", "")
                self.proj_name_entry.set_value(pname)

                self.anim_data.clear()
                
                for item in zf.namelist():
                    if item.startswith("images/") and item.endswith("_idx.png"):
                        fname = item[len("images/"): -len("_idx.png")]
                        
                        idx_data = zf.read(item)
                        alpha_data = zf.read(f"images/{fname}_alpha.png")

                        idx_img = Image.open(io.BytesIO(idx_data)).copy()
                        alpha_img = Image.open(io.BytesIO(alpha_data)).copy()

                        self.anim_data[fname] = {"idx": idx_img, "alpha": alpha_img}

                self.restore_state(state)
                self.save_state()
                
            self.show_notification("Projet importé avec succès.")
        except Exception as e:
            logging.error(f"Import project error: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to load project.\n{e}")

    # --- STATE MANAGEMENT (UNDO/REDO) ---
    def get_tree_state(self):
        state = []
        for group in self.tree.get_children(""):
            g_dict = {
                "text": self.tree.item(group, "text"),
                "tags": self.tree.item(group, "tags"),
                "open": self.tree.item(group, "open"),
                "children": []
            }
            for f_node in self.tree.get_children(group):
                g_dict["children"].append({
                    "text": self.tree.item(f_node, "text"),
                    "tags": self.tree.item(f_node, "tags")
                })
            state.append(g_dict)
        return state

    def save_state(self, event=None):
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index+1]
            
        state = {
            "rgb": list(self.palette_data) if hasattr(self, 'palette_data') else [],
            "alpha": list(self.palette_alphas) if hasattr(self, 'palette_alphas') and self.palette_alphas else [255]*256,
            "tree": self.get_tree_state()
        }
        
        self.history.append(state)
        self.history_index += 1
        if len(self.history) > 50:
            self.history.pop(0)
            self.history_index -= 1

    def undo(self, event=None):
        if self.history_index > 0:
            self.history_index -= 1
            self.restore_state(self.history[self.history_index])
    
    def redo(self, event=None):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.restore_state(self.history[self.history_index])

    def restore_state(self, state):
        self.palette_data = list(state["rgb"])
        self.palette_alphas = list(state["alpha"])
        self.palette_snapshot = None
        
        self.tree.delete(*self.tree.get_children(""))
        for g in state.get("tree", []):
            tags = tuple(g["tags"]) if g["tags"] else ("group",)
            node = self.tree.insert("", "end", text=g["text"], tags=tags, open=g.get("open", True))
            if "imported" in tags:
                self.imported_node = node
            for child in g["children"]:
                c_tags = tuple(child["tags"]) if child["tags"] else ("file",)
                self.tree.insert(node, "end", text=child["text"], tags=c_tags)

        self.draw_palette_grid()
        self.render_current()

    def load_presets_list(self):
        preset_dir = os.path.join(self.app.current_dir, 'presets')
        
        if not os.path.exists(preset_dir):
            try: os.makedirs(preset_dir)
            except: pass
                
        self.preset_files.clear()
        if os.path.exists(preset_dir):
            for f in os.listdir(preset_dir):
                if f.lower().endswith('.json'):
                    name = os.path.splitext(f)[0]
                    self.preset_files[name] = os.path.join(preset_dir, f)
                    
        preset_names = list(self.preset_files.keys())
        preset_names.sort()
        
        if "default" in preset_names:
            preset_names.remove("default")
            preset_names.insert(0, "default")
            
        self.preset_cb['values'] = preset_names
        if preset_names:
            self.preset_var.set(preset_names[0])

    def apply_preset(self, event=None):
        selected = self.preset_var.get()
        if selected not in self.preset_files: return
            
        filepath = self.preset_files[selected]
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for child in self.tree.get_children(""):
                if child != self.imported_node:
                    for file_item in self.tree.get_children(child):
                        self.tree.move(file_item, self.imported_node, "end")
                    self.tree.delete(child)
                
            if isinstance(data, dict) and "groups" in data:
                for item in data["groups"]:
                    g_id = item.get("id", 0)
                    g_name = item.get("name", "Unnamed Group")
                    formatted_name = f"[{int(g_id):02d}] {g_name}"
                    self.tree.insert("", "end", text=formatted_name, tags=("group", "preset_group"), open=True)
            else:
                logging.warning(f"Le fichier preset '{selected}.json' a un format invalide.")
                
            self.tree.move(self.imported_node, "", 0)
            self.save_state() 
            self.show_notification(f"Preset '{selected}' chargé.")
                
        except Exception as e:
            logging.error(f"Failed to load preset {selected}: {e}", exc_info=True)
            messagebox.showerror("Error", f"Could not load preset.\n{e}")

    # --- UI BUILDING ---
    def build_ui(self):
        self.parent.columnconfigure(0, weight=0, minsize=260)
        self.parent.columnconfigure(1, weight=1)
        self.parent.columnconfigure(2, weight=0, minsize=300)
        self.parent.rowconfigure(0, weight=1)

        # LEFT PANEL
        left = ttk.Frame(self.parent, relief="groove")
        left.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        
        # 1. Project Import/Export Section
        proj_f = ttk.Frame(left)
        proj_f.pack(fill="x", padx=5, pady=5)
        ttk.Button(proj_f, text="Import Project", command=self.import_project).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(proj_f, text="Export Project", command=self.export_project).pack(side="left", fill="x", expand=True, padx=2)
        
        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=5, pady=5)
        
        # 2. Assets Section
        btn_f = ttk.Frame(left)
        btn_f.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_f, text="Import", command=self.import_sprites).pack(side="left", fill="x", expand=True, padx=2)
        self.btn_export = ttk.Button(btn_f, text="Export", command=self.export_sprites, state="disabled")
        self.btn_export.pack(side="left", fill="x", expand=True, padx=2)
        self.btn_clear = ttk.Button(btn_f, text="Clear Assets", command=self.clear_assets)
        self.btn_clear.pack(side="left", fill="x", expand=True, padx=2)
        
        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=5, pady=5)
        
        # 3. Presets Section
        preset_f = ttk.Frame(left)
        preset_f.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Label(preset_f, text="Presets:").pack(side="left")
        
        self.preset_var = tk.StringVar()
        self.preset_cb = ttk.Combobox(preset_f, textvariable=self.preset_var, state="readonly")
        self.preset_cb.pack(side="left", fill="x", expand=True, padx=5)
        
        ttk.Button(preset_f, text="Load", width=6, command=self.apply_preset).pack(side="left")
        
        self.load_presets_list()
        
        # 4. Treeview
        self.tree = YuyaTreeview(left, selectmode="extended")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        self.tree.bind("<Control-c>", self.copy_frames)
        self.tree.bind("<Control-v>", self.paste_frames)
        self.tree.bind("<Delete>", self.delete_selected)
        self.tree.bind("<BackSpace>", self.delete_selected)
        self.tree.bind("<<TreeOrderChanged>>", lambda e: self.save_state())
        
        self.tree_menu = tk.Menu(self.tree, tearoff=0)
        self.tree_menu.add_command(label="Clone / Paste", command=self.clone_selected)
        self.tree_menu.add_command(label="Delete", command=self.delete_selected)
        self.tree.bind("<Button-3>", self.on_tree_rclick)
        
        self.imported_node = self.tree.insert("", "end", text="Imported", tags=("group", "imported"), open=True)

        # CENTER PANEL
        center = ttk.Frame(self.parent, relief="groove"); center.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        self.canvas = tk.Canvas(center, bg="#303030", highlightthickness=0); self.canvas.pack(fill="both", expand=True)
        ctrl = ttk.Frame(center); ctrl.pack(fill="x", padx=5, pady=5)
        self.btn_play = ttk.Button(ctrl, text="▶ Play", command=self.toggle_play); self.btn_play.pack(side="left")
        
        ttk.Label(ctrl, text="Framerate (ms):").pack(side="left", padx=(10,0))
        tk.Entry(ctrl, textvariable=self.framerate_ms_var, width=5).pack(side="left")
        
        zoom_f = ttk.Frame(ctrl); zoom_f.pack(side="left", padx=(20,0))
        ttk.Checkbutton(zoom_f, text="Auto", variable=self.zoom_auto_var, command=self.render_current).pack(side="left")
        ttk.Button(zoom_f, text="-", width=2, command=self.zoom_out).pack(side="left")
        self.lbl_zoom = ttk.Label(zoom_f, text="100%"); self.lbl_zoom.pack(side="left", padx=5)
        ttk.Button(zoom_f, text="+", width=2, command=self.zoom_in).pack(side="left")
        
        ttk.Button(ctrl, text="Remove BG", command=self.remove_bg_prompt).pack(side="left", padx=(20,5))
        
        # NOTIFICATION LABEL
        self.lbl_notification = ttk.Label(ctrl, text="", font=("Arial", 9, "italic"), foreground="#888888")
        self.lbl_notification.pack(side="left", padx=(10, 0))

        # RIGHT PANEL
        right = ttk.Frame(self.parent, relief="groove"); right.grid(row=0, column=2, sticky="nsew", padx=2, pady=2)
        
        h_frame = ttk.Frame(right); h_frame.pack(fill="x", pady=2)
        ttk.Button(h_frame, text="↶ Undo", command=self.undo).pack(side="left", expand=True, fill="x")
        ttk.Button(h_frame, text="↷ Redo", command=self.redo).pack(side="left", expand=True, fill="x")
        
        io_frame = ttk.Frame(right); io_frame.pack(fill="x", pady=2)
        ttk.Button(io_frame, text="Import Palette", command=self.import_palette).pack(side="left", expand=True, fill="x")
        ttk.Button(io_frame, text="Export Palette", command=self.export_palette).pack(side="left", expand=True, fill="x")

        ttk.Label(right, text="Palette (256 Colors)").pack(pady=5)
        self.pal_canvas = tk.Canvas(right, width=256, height=256, bg="black", highlightthickness=1, highlightbackground="gray")
        self.pal_canvas.pack()
        self.pal_canvas.bind("<Button-1>", self.on_palette_click)
        self.pal_canvas.bind("<Button-3>", self.on_palette_rclick)
        
        tools = ttk.LabelFrame(right, text="Group Selection")
        tools.pack(fill="x", padx=5, pady=5)
        
        self.group_mode_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tools, text="Enable Group Mode", variable=self.group_mode_var).pack(anchor="w")
        
        f_tol = ttk.Frame(tools); f_tol.pack(fill="x", pady=2)
        ttk.Label(f_tol, text="Tolerance:").pack(side="left")
        self.tol_var = tk.IntVar(value=10)
        s_tol = tk.Scale(f_tol, from_=0, to=100, orient="horizontal", variable=self.tol_var, showvalue=0, command=lambda v: self.update_selection_dynamic())
        s_tol.pack(side="left", fill="x", expand=True)
        s_tol.bind("<Double-Button-1>", lambda e: self.tol_var.set(10) or self.update_selection_dynamic())
        tk.Entry(f_tol, textvariable=self.tol_var, width=4).pack(side="left")

        ttk.Button(tools, text="Clear Selection", command=self.clear_selection).pack(fill="x", pady=2)

        grp = ttk.LabelFrame(right, text="Group Modification (Effect)"); grp.pack(fill="x", padx=5, pady=5)
        self.grp_h = tk.DoubleVar(value=0.0)
        self.grp_s = tk.DoubleVar(value=0.0)
        self.grp_l = tk.DoubleVar(value=0.0)
        self.create_hsl_slider(grp, "Hue", self.grp_h, -0.5, 0.5)
        self.create_hsl_slider(grp, "Sat", self.grp_s, -1.0, 1.0)
        self.create_hsl_slider(grp, "Lum", self.grp_l, -1.0, 1.0)
        bgp = ttk.Frame(grp); bgp.pack(fill="x", pady=5)
        ttk.Button(bgp, text="Apply", command=self.apply_group_edit).pack(side="left", expand=True, padx=2)
        ttk.Button(bgp, text="Cancel", command=self.cancel_group_edit).pack(side="left", expand=True, padx=2)

        # JSON Export / Preview Section (Clean layout without text area)
        json_f = ttk.Frame(right)
        json_f.pack(fill="x", padx=5, pady=5)
        ttk.Button(json_f, text="Generate JSON", command=self.generate_json).pack(side="left", padx=2)
        ttk.Button(json_f, text="Preview JSON", command=self.preview_json).pack(side="left", padx=2)
        ttk.Label(json_f, text="Name:").pack(side="left", padx=(10, 2))
        self.proj_name_entry = PlaceholderEntry(json_f, "projectName")
        self.proj_name_entry.pack(side="left", fill="x", expand=True, padx=2)

        if self.preset_var.get() == "default":
            self.apply_preset()
        else:
            self.save_state()

    # --- ACTION METHODS ---
    def _build_json_data(self):
        """Construit le dictionnaire de données JSON et le retourne sous forme de chaîne formatée et compactée."""
        proj_name = self.proj_name_entry.get_value()
        if not proj_name or proj_name == "projectName":
            proj_name = "MyProject"

        json_structure = {"basepath": f"sprites/{proj_name}/", "images": []}
        
        for group_id in self.tree.get_children(""):
            if group_id == self.imported_node:
                continue 
                
            txt = self.tree.item(group_id, 'text')
            gid = 0
            if txt.startswith("[") and "]" in txt:
                try:
                    gid = int(txt[1:txt.find("]")])
                except ValueError:
                    pass
                    
            children = self.tree.get_children(group_id)
            for frame_idx, item_id in enumerate(children):
                fname = self.tree.item(item_id, 'text')
                base_name, _ = os.path.splitext(fname)
                json_structure["images"].append({"group": gid, "frame": frame_idx, "file": f"{base_name}.png"})
                
        raw_json = json.dumps(json_structure, indent=4)
        
        # Regex très propre pour compacter l'objet JSON intérieur sur une seule ligne
        compact_json = re.sub(
            r'\{\s+"group":\s+(\d+),\s+"frame":\s+(\d+),\s+"file":\s+"([^"]+)"\s+\}', 
            r'{ "group": \1, "frame": \2, "file": "\3" }', 
            raw_json
        )
        
        return compact_json

    def generate_json(self):
        """Ne fait que signaler que la structure a été générée en mémoire (logique d'enregistrement à venir)."""
        self._build_json_data()
        self.show_notification("Structure JSON générée en mémoire (prête à exporter).")

    def preview_json(self):
        """Ouvre une fenêtre pop-up affichant le JSON formaté."""
        json_str = self._build_json_data()
        
        top = tk.Toplevel(self.parent)
        top.title("JSON Preview")
        top.geometry("550x650")
        
        main_x = self.parent.winfo_rootx()
        main_y = self.parent.winfo_rooty()
        top.geometry(f"+{main_x + 100}+{main_y + 100}")
        
        txt = tk.Text(top, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", wrap="none")
        vsb = ttk.Scrollbar(top, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(top, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        txt.pack(side="left", fill="both", expand=True)
        
        txt.insert("1.0", json_str)
        txt.config(state="disabled")

    def copy_frames(self, event=None):
        self.clipboard_frames = []
        for item in self.tree.selection():
            if "file" in self.tree.item(item, "tags"):
                self.clipboard_frames.append(self.tree.item(item, "text"))

    def paste_frames(self, event=None):
        if not self.clipboard_frames: return
        
        sel = self.tree.selection()
        target_node = self.imported_node
        idx = "end"
        
        if sel:
            tags = self.tree.item(sel[0], "tags")
            if "group" in tags:
                target_node = sel[0]
            elif "file" in tags:
                target_node = self.tree.parent(sel[0])
                idx = self.tree.index(sel[0]) + 1
        
        for fname in self.clipboard_frames:
            if fname in self.anim_data:
                if idx == "end":
                    self.tree.insert(target_node, "end", text=fname, tags=("file",))
                else:
                    self.tree.insert(target_node, idx, text=fname, tags=("file",))
                    if isinstance(idx, int): idx += 1
                    
        self.save_state()

    def delete_selected(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        changed = False
        for item in sel:
            if "file" in self.tree.item(item, "tags"):
                self.tree.delete(item)
                changed = True
        if changed:
            self.save_state()

    def on_tree_rclick(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            if item not in self.tree.selection():
                self.tree.selection_set(item)
            self.tree_menu.post(event.x_root, event.y_root)

    def clone_selected(self):
        self.copy_frames()
        self.paste_frames()

    def remove_bg_prompt(self):
        if not self.anim_data or not self.current_frame_list:
            messagebox.showinfo("Info", "Veuillez d'abord sélectionner une image dans l'arbre.")
            return
            
        fname = self.current_frame_list[self.current_frame_index]
        img_idx = self.anim_data[fname]["idx"]
        
        px_idx = img_idx.getpixel((0, 0))
        
        if px_idx * 3 + 2 < len(self.palette_data):
            r = self.palette_data[px_idx*3]
            g = self.palette_data[px_idx*3+1]
            b = self.palette_data[px_idx*3+2]
            default_color = f"#{r:02x}{g:02x}{b:02x}"
        else:
            default_color = "#000000"
            
        color = colorchooser.askcolor(initialcolor=default_color, title="Couleur à rendre transparente")
        
        if color[1]:
            target = color[0]
            best_idx = 0
            min_dist = 999999
            for i in range(256):
                if i*3+2 >= len(self.palette_data): break
                cr, cg, cb = self.palette_data[i*3:i*3+3]
                dist = (cr - target[0])**2 + (cg - target[1])**2 + (cb - target[2])**2
                if dist < min_dist:
                    min_dist = dist
                    best_idx = i
            
            if not self.palette_alphas:
                self.palette_alphas = [255]*256
            
            self.palette_alphas[best_idx] = 0
            self.draw_palette_grid()
            self.render_current()
            self.save_state()
            self.show_notification(f"Couleur #{best_idx} supprimée du fond.")

    # -------------------------------------------------------------------------
    # HSL SLIDERS & PALETTE
    # -------------------------------------------------------------------------
    def create_hsl_slider(self, parent, label, var, mini, maxi):
        r = ttk.Frame(parent); r.pack(fill="x", pady=2)
        ttk.Label(r, text=label, width=4).pack(side="left")
        s = tk.Scale(r, from_=mini, to=maxi, resolution=0.01, orient="horizontal", variable=var, showvalue=0)
        s.pack(side="left", fill="x", expand=True)
        s.bind("<Button-1>", self.start_group_edit)
        s.bind("<B1-Motion>", self.update_group_edit)
        s.bind("<ButtonRelease-1>", self.end_group_edit)
        s.bind("<Double-Button-1>", lambda e: self.reset_slider(var))
        tk.Entry(r, textvariable=var, width=5).pack(side="left")

    def reset_slider(self, var):
        var.set(0.0)
        self.update_group_edit(None) 

    def sort_palette_and_remap(self):
        if not self.palette_data: return
        colors = []
        for i in range(256):
            if i*3+2 >= len(self.palette_data): break
            rgb = tuple(self.palette_data[i*3 : i*3+3])
            colors.append((i, rgb))
        
        def sort_key(item):
            r, g, b = item[1]
            h, l, s = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
            return (h, l, s)
            
        sorted_colors = sorted(colors, key=sort_key)
        mapping = {}
        new_pal = []
        new_alphas = [] 
        if not self.palette_alphas: self.palette_alphas = [255]*256
        
        for new_idx, (old_idx, rgb) in enumerate(sorted_colors):
            new_pal.extend(rgb)
            mapping[old_idx] = new_idx
            new_alphas.append(self.palette_alphas[old_idx])
            
        self.palette_data = new_pal
        self.palette_alphas = new_alphas
        
        for fname, data in self.anim_data.items():
            img_p = data["idx"]
            pixels = list(img_p.getdata())
            new_pixels = [mapping.get(p, p) for p in pixels]
            img_p.putdata(new_pixels)
            
    def import_sprites(self):
        files = filedialog.askopenfilenames(filetypes=[("Images", "*.png;*.bmp")])
        if not files: return
        
        self.last_open_dir = os.path.dirname(files[0])

        if not self.palette_data:
            try:
                combo = Image.new("RGB", (1000, 1000))
                y_off = 0
                for f in files[:15]: 
                    i = Image.open(f).convert("RGB")
                    combo.paste(i, (0, y_off))
                    y_off += i.height
                q = combo.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                self.palette_data = q.getpalette()[:768]
                self.palette_alphas = [255]*256
                self.sort_palette_and_remap()
            except Exception as e: 
                logging.error(f"Quantize error: {e}", exc_info=True)
                
        self.palette_snapshot = None 
        sel = self.tree.selection()
        
        if sel and "group" in self.tree.item(sel[0], "tags"): 
            parent = sel[0]
        else: 
            parent = self.imported_node
            
        pal_img = Image.new("P", (1,1)); pal_img.putpalette(self.palette_data)
        for f in files:
            fname = os.path.basename(f)
            try:
                img = Image.open(f).convert("RGBA")
                alpha = img.split()[3]
                rgb = img.convert("RGB")
                idx = rgb.quantize(palette=pal_img, dither=Image.Dither.NONE)
                self.anim_data[fname] = {"idx": idx, "alpha": alpha}
                self.tree.insert(parent, "end", text=fname, tags=("file",))
            except Exception as e: 
                logging.error(f"Import error {fname}: {e}", exc_info=True)
                
        self.draw_palette_grid()
        self.btn_export.config(state="normal")
        self.save_state()
        self.show_notification(f"{len(files)} image(s) importée(s).")

    def export_sprites(self):
        if not self.anim_data: return
        dest = filedialog.askdirectory(initialdir=self.last_open_dir)
        if not dest: return
        
        count = 0
        try:
            for fname, d in self.anim_data.items():
                base_name, _ = os.path.splitext(fname)
                export_fname = f"{base_name}.png"
                
                d["idx"].putpalette(self.palette_data)
                img = d["idx"].convert("RGBA")
                base_alpha = d["alpha"]
                
                gray_pal = []
                for a_val in self.palette_alphas: gray_pal.extend((a_val, a_val, a_val))
                gray_pal.extend([255]*(768-len(gray_pal)))
                alpha_mask = d["idx"].copy()
                alpha_mask.putpalette(gray_pal)
                alpha_mask = alpha_mask.convert("L")
                
                final_alpha = ImageChops.multiply(base_alpha, alpha_mask)
                img.putalpha(final_alpha)
                
                dest_path = os.path.join(dest, export_fname)
                c = 1
                while os.path.exists(dest_path):
                    export_fname = f"{base_name}_{c}.png"
                    dest_path = os.path.join(dest, export_fname)
                    c += 1
                
                # Sauvegarde strictement au format PNG pour forcer le canal Alpha !
                img.save(dest_path, format="PNG")
                count += 1
                
            self.show_notification(f"{count} image(s) exportée(s) avec succès.")
            
        except Exception as e:
            logging.error(f"Export failed: {e}", exc_info=True)
            messagebox.showerror("Export Failed", str(e))

    def clear_assets(self):
        if not messagebox.askyesno("Confirm", "Clear all imported sprites and palette?"): return
        
        self.anim_data.clear()
        self.palette_data = []
        self.palette_alphas = []
        self.palette_snapshot = None
        self.current_frame_list = []
        self.clipboard_frames = []
        self.history = []
        self.history_index = -1
        
        self.canvas.delete("all")
        self.pal_canvas.delete("all")
        
        for group in self.tree.get_children(""):
            for file_node in self.tree.get_children(group):
                self.tree.delete(file_node)
        
        try:
            for f in os.listdir(self.app.cache_dir):
                fp = os.path.join(self.app.cache_dir, f)
                if os.path.isfile(fp): os.unlink(fp)
        except: pass
        
        self.btn_export.config(state="disabled")
        self.save_state()
        self.show_notification("Projet nettoyé.")

    def draw_palette_grid(self):
        self.pal_canvas.delete("all")
        for i in range(256):
            if i*3+2 >= len(self.palette_data): break
            r,g,b = self.palette_data[i*3 : i*3+3]
            color = f"#{r:02x}{g:02x}{b:02x}"
            x, y = (i%16)*16, (i//16)*16
            tag = f"c_{i}"
            rect = self.pal_canvas.create_rectangle(x, y, x+16, y+16, fill=color, outline="gray", tags=tag)
            if i in self.selected_indices:
                self.pal_canvas.itemconfig(rect, outline="white", width=2)
                self.pal_canvas.create_rectangle(x+2, y+2, x+14, y+14, outline="black", tags="sel_inner")

    def zoom_in(self):
        self.zoom_auto_var.set(False)
        self.zoom_level += 0.5
        self.render_current()

    def zoom_out(self):
        self.zoom_auto_var.set(False)
        self.zoom_level = max(0.5, self.zoom_level - 0.5)
        self.render_current()

    def toggle_play(self):
        self.is_playing = not self.is_playing
        self.btn_play.config(text="⏸ Stop" if self.is_playing else "▶ Play")
        if self.is_playing: self.run_anim_loop()

    def run_anim_loop(self):
        if self.is_playing and self.current_frame_list:
            self.current_frame_index = (self.current_frame_index + 1) % len(self.current_frame_list)
            self.render_current()
            try:
                ms = int(self.framerate_ms_var.get())
            except: ms = 100
            self.app.root.after(max(10, ms), self.run_anim_loop)

    def render_current(self):
        if not self.current_frame_list: return
        fname = self.current_frame_list[self.current_frame_index]
        if fname not in self.anim_data: return
        d = self.anim_data[fname]
        
        d["idx"].putpalette(self.palette_data)
        img = d["idx"].convert("RGBA")
        base_alpha = d["alpha"]
        w, h = img.size
        
        gray_pal = []
        for a_val in self.palette_alphas: gray_pal.extend((a_val, a_val, a_val))
        gray_pal.extend([255]*(768-len(gray_pal)))
        alpha_mask = d["idx"].copy(); alpha_mask.putpalette(gray_pal); alpha_mask = alpha_mask.convert("L")
        
        final_alpha = ImageChops.multiply(base_alpha, alpha_mask)
        img.putalpha(final_alpha)
        
        z = 1.0
        if self.zoom_auto_var.get():
            cw = self.canvas.winfo_width(); ch = self.canvas.winfo_height()
            if cw > 10 and ch > 10 and w > 0 and h > 0:
                z = min(cw/w, ch/h) * 0.9 
        else:
            z = self.zoom_level
        
        self.lbl_zoom.config(text=f"{int(z*100)}%")
        
        w_new, h_new = int(w * z), int(h * z)
        if w_new > 0 and h_new > 0:
            img = img.resize((w_new, h_new), Image.Resampling.NEAREST)
        
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        cx, cy = self.canvas.winfo_width()//2, self.canvas.winfo_height()//2
        self.canvas.create_image(cx, cy, image=self.tk_img)

    def on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        item = sel[0]; tags = self.tree.item(item, "tags")
        if "file" in tags:
            f = self.tree.item(item, "text"); self.current_frame_list = [f]; self.current_frame_index = 0
            self.render_current(); self.is_playing = False; self.btn_play.config(text="▶ Play")
            self.last_open_dir = os.path.dirname(os.path.join(self.last_open_dir, f)) 
        elif "group" in tags:
            files = [self.tree.item(c, "text") for c in self.tree.get_children(item)]
            self.current_frame_list = files; self.current_frame_index = 0
            if files: self.is_playing = True; self.btn_play.config(text="⏸ Stop"); self.run_anim_loop()

    def on_palette_click(self, event):
        col, row = event.x // 16, event.y // 16
        idx = row * 16 + col
        if idx >= 256: return
        
        if not self.group_mode_var.get():
            self.last_selected_index = idx
            self.selected_indices = {idx}
            self.draw_palette_grid()
            self.open_popup_editor(idx, event)
            return

        self.reference_color_index = idx
        self.last_selected_index = idx
        if self.palette_snapshot is None: self.palette_snapshot = list(self.palette_data)
        self.update_selection_dynamic()

    def on_palette_rclick(self, event):
        col, row = event.x // 16, event.y // 16
        idx = row * 16 + col
        if idx >= 256: return
        if idx in self.selected_indices: self.selected_indices.remove(idx)
        else: self.selected_indices.add(idx)
        self.apply_hsl_to_selection()
        self.draw_palette_grid()
        self.render_current()

    def update_selection_dynamic(self):
        if self.reference_color_index == -1: return
        if self.palette_snapshot is None: self.palette_snapshot = list(self.palette_data)
        target = self.palette_snapshot[self.reference_color_index*3 : self.reference_color_index*3+3]
        tol = self.tol_var.get()
        max_dist = 442.0 * (tol / 100.0)
        new_sel = set()
        for i in range(256):
            if i*3+2 >= len(self.palette_snapshot): break
            current = self.palette_snapshot[i*3 : i*3+3]
            dist = math.sqrt(sum((t - c) ** 2 for t, c in zip(target, current)))
            if dist <= max_dist: new_sel.add(i)
        self.selected_indices = new_sel
        self.apply_hsl_to_selection()
        self.draw_palette_grid()
        self.render_current()

    def start_group_edit(self, event):
        if self.palette_snapshot is None: self.palette_snapshot = list(self.palette_data)

    def update_group_edit(self, event):
        self.apply_hsl_to_selection()
        self.draw_palette_grid()
        self.render_current()

    def end_group_edit(self, event): pass

    def apply_hsl_to_selection(self):
        if self.palette_snapshot is None: return
        dh = self.grp_h.get(); ds = self.grp_s.get(); dl = self.grp_l.get()
        self.palette_data = list(self.palette_snapshot)
        for idx in self.selected_indices:
            r = self.palette_snapshot[idx*3]; g = self.palette_snapshot[idx*3+1]; b = self.palette_snapshot[idx*3+2]
            h, l, s = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
            h = (h + dh) % 1.0
            s = max(0.0, min(1.0, s + ds))
            l = max(0.0, min(1.0, l + dl))
            nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
            self.palette_data[idx*3] = int(nr*255)
            self.palette_data[idx*3+1] = int(ng*255)
            self.palette_data[idx*3+2] = int(nb*255)

    def apply_group_edit(self):
        self.palette_snapshot = None
        self.grp_h.set(0); self.grp_s.set(0); self.grp_l.set(0)
        self.selected_indices.clear()
        self.reference_color_index = -1
        self.draw_palette_grid()
        self.save_state()

    def cancel_group_edit(self):
        if self.palette_snapshot:
            self.palette_data = list(self.palette_snapshot)
            self.palette_snapshot = None
        self.grp_h.set(0); self.grp_s.set(0); self.grp_l.set(0)
        self.selected_indices.clear()
        self.reference_color_index = -1
        self.draw_palette_grid()
        self.render_current()

    def clear_selection(self): self.cancel_group_edit()

    def open_popup_editor(self, idx, event):
        if self.active_popup:
            self.active_popup.destroy(); self.active_popup = None
        rgb = tuple(self.palette_data[idx*3 : idx*3+3])
        if not self.palette_alphas: self.palette_alphas = [255]*256
        alpha = self.palette_alphas[idx]
        rgba = rgb + (alpha,)
        rx = self.pal_canvas.winfo_rootx() + event.x + 20
        ry = self.pal_canvas.winfo_rooty() + event.y
        orig_rgba = list(rgba)
        
        def on_up(i, c):
            self.palette_data[i*3] = c[0]
            self.palette_data[i*3+1] = c[1]
            self.palette_data[i*3+2] = c[2]
            self.palette_alphas[i] = c[3]
            self.draw_palette_grid()
            self.render_current()
            
        def on_ap(i, c): 
            self.active_popup = None
            self.save_state()
            
        def on_ca(i):
            on_up(i, orig_rgba)
            self.active_popup = None

        self.active_popup = PopupColorEditor(self.app.root, idx, rgba, on_up, on_ap, on_ca)
        self.active_popup.geometry(f"+{rx}+{ry}")

    def import_palette(self):
        f = filedialog.askopenfilename(filetypes=[("Palette", "*.pal;*.act")])
        if not f: return
        try:
            with open(f, 'r') as pal_file:
                lines = pal_file.readlines()
                if "JASC-PAL" not in lines[0]:
                    messagebox.showerror("Error", "Only JASC-PAL supported for now")
                    return
                count = int(lines[2].strip())
                self.palette_data = []
                for i in range(count):
                    parts = lines[3+i].strip().split()
                    if len(parts) >= 3:
                        self.palette_data.extend([int(p) for p in parts[:3]])
                while len(self.palette_data) < 768: self.palette_data.extend([0,0,0])
                self.draw_palette_grid()
                self.render_current()
                self.save_state()
                self.show_notification("Palette importée avec succès.")
        except Exception as e: 
            logging.error(f"Palette import error: {e}", exc_info=True)
            messagebox.showerror("Error", str(e))

    def export_palette(self):
        f = filedialog.asksaveasfilename(defaultextension=".pal", filetypes=[("JASC Palette", "*.pal")])
        if not f: return
        try:
            with open(f, 'w') as pal_file:
                pal_file.write("JASC-PAL\n0100\n256\n")
                for i in range(256):
                    if i*3+2 < len(self.palette_data):
                        r,g,b = self.palette_data[i*3:i*3+3]
                        pal_file.write(f"{r} {g} {b}\n")
                    else:
                        pal_file.write("0 0 0\n")
            self.show_notification("Palette exportée avec succès.")
        except Exception as e: 
            logging.error(f"Palette export error: {e}", exc_info=True)
            messagebox.showerror("Error", str(e))