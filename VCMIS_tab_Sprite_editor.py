import os
import json
import logging
import threading
import concurrent.futures
import math
import colorsys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageTk, ImageChops

from VCMIS_ui_components import PlaceholderEntry, AdvancedTreeview, PopupColorEditor, NotificationMixin, CanvasViewerMixin
from VCMIS_utils_project import HistoryManager, ProjectManager
from VCMIS_utils_image import hex_to_rgb


class SpriteEditorTab(NotificationMixin, CanvasViewerMixin):
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        
        self.anim_data = {} 
        self.palette_data = [] 
        self.palette_alphas = [] 
        
        self.original_palette_data = []
        self.original_palette_alphas = []
        
        self.unsaved_color_edits = 0
        self.unsaved_reorders = 0
        
        self.is_playing = False
        self.current_frame_list = []
        self.current_frame_index = 0
        self.anim_job = None
        
        self.zoom_level = 1.0
        self.zoom_auto_var = tk.BooleanVar(value=False)
        self.framerate_ms_var = tk.StringVar(value="100") 
        
        self.selected_indices = set()
        self.reference_color_index = -1 
        self.palette_snapshot = None 
        self.active_popup = None 
        
        self.remove_bg_var = tk.BooleanVar(value=False)
        self.transp_color = tk.StringVar(value="#00FFFF")
        self.eyedropper_mode = False
        self.palette_picker_mode = False
        
        self.preview_original_var = tk.BooleanVar(value=False)
        self.duo_view_var = tk.BooleanVar(value=False)
        
        self.history_mgr = HistoryManager(30, self.restore_state)
        self.last_open_dir = os.path.expanduser("~")
        self.preset_files = {}
        self.clipboard_frames = []
        self.notification_job = None
        
        self.build_ui()

    def has_unsaved_changes(self):
        return self.unsaved_color_edits >= 1 or self.unsaved_reorders >= 10

    def undo(self, event=None): self.history_mgr.undo()
    def redo(self, event=None): self.history_mgr.redo()

    # ---- Implémentation requise par CanvasViewerMixin ----
    def is_tab_active(self): 
        return self.app.notebook.index(self.app.notebook.select()) == 2
    def can_zoom(self): 
        return bool(self.current_frame_list)
    def on_zoom_changed(self): 
        self.render_current()
    # -----------------------------------------------------

    def export_project(self):
        if not self.anim_data:
            messagebox.showinfo("Export", "No project data to export.")
            return
        f = filedialog.asksaveasfilename(defaultextension=".vsp", filetypes=[("VCMI Sprite Project", "*.vsp")])
        if not f: return
        try:
            full_pal = list(self.palette_data)
            pad_col = self.palette_data[:3] if self.palette_data else [0,0,0]
            while len(full_pal) < 768: full_pal.extend(pad_col)
            
            full_alphas = list(self.palette_alphas) if self.palette_alphas else [255] * (len(self.palette_data) // 3)
            while len(full_alphas) < 256: full_alphas.append(255)
            
            ProjectManager.export_sprite_vsp(f, full_pal, full_alphas, ProjectManager.get_tree_state(self.tree), self.proj_name_entry.get_value(), self.anim_data)
            self.unsaved_color_edits = 0; self.unsaved_reorders = 0
            self.show_notification("Projet exporté avec succès (.vsp).")
        except Exception as e:
            logging.error(f"Export project error: {e}", exc_info=True)
            messagebox.showerror("Error", f"Export project error:\n{e}")

    def import_project(self):
        f = filedialog.askopenfilename(filetypes=[("VCMI Sprite Project", "*.vsp")])
        if not f: return
        try:
            state, anim_data = ProjectManager.import_sprite_vsp(f)
            self.anim_data.clear(); self.anim_data.update(anim_data)
            self.proj_name_entry.set_value(state.get("project_name", ""))
            
            raw_pal = list(state.get("rgb", []))
            raw_alpha = list(state.get("alpha", []))
            
            valid_len = len(raw_pal)
            while valid_len >= 3 and raw_pal[valid_len-3:valid_len] == raw_pal[:3]:
                valid_len -= 3
                
            if valid_len == 0 and len(raw_pal) > 0: valid_len = 3 
            
            state["rgb"] = raw_pal[:valid_len]
            state["alpha"] = raw_alpha[:valid_len // 3]

            self.restore_state(state); self.save_state()
            
            self.original_palette_data = list(state.get("rgb", []))
            self.original_palette_alphas = list(state.get("alpha", []))
            self.unsaved_color_edits = 0; self.unsaved_reorders = 0
            
            self.show_notification("Projet importé avec succès.")
        except Exception as e:
            logging.error(f"Import project error: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to load project.\n{e}")

    def save_state(self, event=None):
        self.history_mgr.save_state({"rgb": list(self.palette_data), "alpha": list(self.palette_alphas) if self.palette_alphas else [255]*(len(self.palette_data)//3), "tree": ProjectManager.get_tree_state(self.tree)})

    def restore_state(self, state):
        self.palette_data = list(state["rgb"]); self.palette_alphas = list(state["alpha"]); self.palette_snapshot = None
        self.tree.delete(*self.tree.get_children(""))
        for g in state.get("tree", []):
            node = self.tree.insert("", "end", text=g["text"], tags=tuple(g["tags"]) if g["tags"] else ("group",), open=g.get("open", True))
            if "imported" in self.tree.item(node, "tags"): self.imported_node = node
            for child in g["children"]: self.tree.insert(node, "end", text=child["text"], tags=tuple(child["tags"]) if child["tags"] else ("file",))
        self.draw_palette_grid(); self.render_current()

    def load_presets_list(self):
        preset_dir = os.path.join(self.app.current_dir, 'presets')
        if not os.path.exists(preset_dir):
            try: os.makedirs(preset_dir)
            except: pass
        self.preset_files.clear()
        if os.path.exists(preset_dir):
            for f in os.listdir(preset_dir):
                if f.lower().endswith('.json'): self.preset_files[os.path.splitext(f)[0]] = os.path.join(preset_dir, f)
        preset_names = sorted(list(self.preset_files.keys()))
        if "default" in preset_names: preset_names.remove("default"); preset_names.insert(0, "default")
        self.preset_cb['values'] = preset_names
        if preset_names: self.preset_var.set(preset_names[0])

    def apply_preset(self, event=None):
        selected = self.preset_var.get()
        if selected not in self.preset_files: return
        try:
            with open(self.preset_files[selected], 'r', encoding='utf-8') as f: data = json.load(f)
            for child in self.tree.get_children(""):
                if child != self.imported_node:
                    for file_item in self.tree.get_children(child): self.tree.move(file_item, self.imported_node, "end")
                    self.tree.delete(child)
            if isinstance(data, dict) and "groups" in data:
                for item in data["groups"]: self.tree.insert("", "end", text=f"[{int(item.get('id', 0)):02d}] {item.get('name', 'Unnamed Group')}", tags=("group", "preset_group"), open=True)
            self.tree.move(self.imported_node, "", 0); self.save_state(); self.show_notification(f"Preset '{selected}' chargé.")
        except Exception as e:
            logging.error(f"Failed to load preset {selected}: {e}", exc_info=True)
            messagebox.showerror("Error", f"Could not load preset.\n{e}")

    def on_preview_orig_toggle(self):
        if self.preview_original_var.get():
            self.duo_view_var.set(False)
        self.render_current()

    def on_duo_view_toggle(self):
        if self.duo_view_var.get():
            self.preview_original_var.set(False)
        self.render_current()

    def on_canvas_configure(self, event):
        self.center_view()

    def build_ui(self):
        self.parent.columnconfigure(0, weight=0, minsize=260); self.parent.columnconfigure(1, weight=1); self.parent.columnconfigure(2, weight=0, minsize=300); self.parent.rowconfigure(0, weight=1)

        left = ttk.Frame(self.parent, relief="groove"); left.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        proj_f = ttk.Frame(left); proj_f.pack(fill="x", padx=5, pady=5)
        ttk.Button(proj_f, text="Import Project", command=self.import_project).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(proj_f, text="Export Project", command=self.export_project).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=5, pady=5)
        
        btn_f = ttk.Frame(left); btn_f.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_f, text="Import", command=self.import_sprites).pack(side="left", fill="x", expand=True, padx=2)
        self.btn_export = ttk.Button(btn_f, text="Export", command=self.export_sprites, state="disabled")
        self.btn_export.pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="Clear Assets", command=self.clear_assets).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Separator(left, orient="horizontal").pack(fill="x", padx=5, pady=5)
        
        preset_f = ttk.Frame(left); preset_f.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Label(preset_f, text="Presets:").pack(side="left")
        self.preset_var = tk.StringVar()
        self.preset_cb = ttk.Combobox(preset_f, textvariable=self.preset_var, state="readonly"); self.preset_cb.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(preset_f, text="Load", width=6, command=self.apply_preset).pack(side="left")
        self.load_presets_list()
        
        self.tree = AdvancedTreeview(left, allow_groups=True, selectmode="extended"); self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select); self.tree.bind("<Control-c>", self.copy_frames); self.tree.bind("<Control-v>", self.paste_frames)
        self.tree.bind("<Delete>", self.delete_selected); self.tree.bind("<BackSpace>", self.delete_selected); self.tree.bind("<<TreeOrderChanged>>", self.on_tree_order_changed)
        self.tree_menu = tk.Menu(self.tree, tearoff=0); self.tree_menu.add_command(label="Clone / Paste", command=self.clone_selected); self.tree_menu.add_command(label="Delete", command=self.delete_selected)
        self.tree.bind("<Button-3>", self.on_tree_rclick); self.imported_node = self.tree.insert("", "end", text="Imported", tags=("group", "imported"), open=True)

        refresh_f = ttk.Frame(left); refresh_f.pack(fill="x", padx=5, pady=(0,5))
        ttk.Button(refresh_f, text="🔄 Refresh sources", command=self.refresh_sources).pack(side="left", fill="x", expand=True)
        
        json_f = ttk.Frame(left); json_f.pack(fill="x", padx=5, pady=(5, 0))
        ttk.Button(json_f, text="Generate JSON", command=self.generate_json).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(json_f, text="Preview JSON", command=self.preview_json).pack(side="left", fill="x", expand=True, padx=2)
        
        json_name_f = ttk.Frame(left); json_name_f.pack(fill="x", padx=5, pady=5)
        ttk.Label(json_name_f, text="Name:").pack(side="left")
        self.proj_name_entry = PlaceholderEntry(json_name_f, "projectName")
        self.proj_name_entry.pack(side="left", fill="x", expand=True, padx=2)

        center = ttk.Frame(self.parent, relief="groove"); center.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        
        # Nouveau Canvas avec Scrollregion pour Panning & Zooming
        self.canvas = tk.Canvas(center, bg="#303030", highlightthickness=0, scrollregion=(-5000, -5000, 5000, 5000))
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        
        # Initialisation globale des bindings depuis le mixin
        self.setup_canvas_bindings()
        self.bind_global_zoom(self.parent.winfo_toplevel())
        
        ctrl = ttk.Frame(center); ctrl.pack(fill="x", padx=5, pady=5)
        self.btn_play = ttk.Button(ctrl, text="▶ Play", command=self.toggle_play); self.btn_play.pack(side="left")
        ttk.Label(ctrl, text="Framerate (ms):").pack(side="left", padx=(10,0)); tk.Entry(ctrl, textvariable=self.framerate_ms_var, width=5).pack(side="left")
        
        zoom_f = ttk.Frame(ctrl); zoom_f.pack(side="left", padx=(20,0))
        ttk.Button(zoom_f, text="↺", width=2, command=self.reset_view).pack(side="left", padx=5)
        
        def on_zoom_auto_toggle():
            if self.zoom_auto_var.get():
                self.center_view()
            self.render_current()
            
        ttk.Checkbutton(zoom_f, text="Auto", variable=self.zoom_auto_var, command=on_zoom_auto_toggle).pack(side="left")
        ttk.Button(zoom_f, text="-", width=2, command=self.zoom_out).pack(side="left")
        self.lbl_zoom = ttk.Label(zoom_f, text="100%"); self.lbl_zoom.pack(side="left", padx=5)
        ttk.Button(zoom_f, text="+", width=2, command=self.zoom_in).pack(side="left")
        
        ttk.Checkbutton(ctrl, text="Preview Original", variable=self.preview_original_var, command=self.on_preview_orig_toggle).pack(side="left", padx=(20,5))
        ttk.Checkbutton(ctrl, text="Duo view", variable=self.duo_view_var, command=self.on_duo_view_toggle).pack(side="left", padx=(0,5))
        self.lbl_notification = ttk.Label(ctrl, text="", font=("Arial", 9, "italic"), foreground="#888888"); self.lbl_notification.pack(side="left", padx=(10, 0))

        right = ttk.Frame(self.parent, relief="groove"); right.grid(row=0, column=2, sticky="nsew", padx=2, pady=2)
        h_frame = ttk.Frame(right); h_frame.pack(fill="x", pady=2)
        ttk.Button(h_frame, text="↶ Undo", command=self.undo).pack(side="left", expand=True, fill="x"); ttk.Button(h_frame, text="↷ Redo", command=self.redo).pack(side="left", expand=True, fill="x")
        io_frame = ttk.Frame(right); io_frame.pack(fill="x", pady=2)
        ttk.Button(io_frame, text="Import Palette", command=self.import_palette).pack(side="left", expand=True, fill="x"); ttk.Button(io_frame, text="Export Palette", command=self.export_palette).pack(side="left", expand=True, fill="x")

        ttk.Label(right, text="Palette (256 Colors)").pack(pady=5)
        
        self.pal_canvas = tk.Canvas(right, width=256, height=256, bg="#e0e0e0", highlightthickness=1, highlightbackground="gray")
        self.pal_canvas.pack(); self.pal_canvas.bind("<Button-1>", self.on_palette_click); self.pal_canvas.bind("<Button-3>", self.on_palette_rclick)
        
        tools = ttk.LabelFrame(right, text="Group Selection"); tools.pack(fill="x", padx=5, pady=5)
        self.group_mode_var = tk.BooleanVar(value=True); ttk.Checkbutton(tools, text="Enable Group Mode", variable=self.group_mode_var).pack(anchor="w")
        f_tol = ttk.Frame(tools); f_tol.pack(fill="x", pady=2)
        ttk.Label(f_tol, text="Tolerance:").pack(side="left")
        self.tol_var = tk.IntVar(value=10); s_tol = tk.Scale(f_tol, from_=0, to=100, orient="horizontal", variable=self.tol_var, showvalue=0, command=lambda v: self.update_selection_dynamic())
        s_tol.pack(side="left", fill="x", expand=True); s_tol.bind("<Double-Button-1>", lambda e: self.tol_var.set(10) or self.update_selection_dynamic())
        tk.Entry(f_tol, textvariable=self.tol_var, width=4).pack(side="left"); ttk.Button(tools, text="Clear Selection", command=self.clear_selection).pack(fill="x", pady=2)

        grp = ttk.LabelFrame(right, text="Group Modification (Effect)"); grp.pack(fill="x", padx=5, pady=5)
        self.grp_h = tk.DoubleVar(value=0.0); self.grp_s = tk.DoubleVar(value=0.0); self.grp_l = tk.DoubleVar(value=0.0)
        self.create_hsl_slider(grp, "Hue", self.grp_h, -0.5, 0.5); self.create_hsl_slider(grp, "Sat", self.grp_s, -1.0, 1.0); self.create_hsl_slider(grp, "Lum", self.grp_l, -1.0, 1.0)
        bgp = ttk.Frame(grp); bgp.pack(fill="x", pady=5)
        ttk.Button(bgp, text="Apply", command=self.apply_group_edit).pack(side="left", expand=True, padx=2); ttk.Button(bgp, text="Cancel", command=self.cancel_group_edit).pack(side="left", expand=True, padx=2)

        self.btn_pick_palette = ttk.Button(right, text="🖌️ Pick Sprite Color", command=self.activate_palette_picker)
        self.btn_pick_palette.pack(fill="x", padx=5, pady=(10, 5))

        transp_frame = ttk.LabelFrame(right, text="Background Removal"); transp_frame.pack(fill="x", padx=5, pady=5)
        transp_inner = ttk.Frame(transp_frame); transp_inner.pack(fill="x", pady=2)
        transp_inner.columnconfigure(1, weight=1)
        ttk.Checkbutton(transp_inner, text="Remove Color:", variable=self.remove_bg_var, command=self.render_current).grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(transp_inner, textvariable=self.transp_color, width=9).grid(row=0, column=1, sticky="ew", padx=(0,5), pady=3)
        self.transp_color.trace_add("write", lambda *args: self.render_current())
        ttk.Button(transp_inner, text="🖌️ Eyedropper", command=self.activate_eyedropper).grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=3)

        if self.preset_var.get() == "default": self.apply_preset()
        else: self.save_state()

    def _sort_palette_and_remap(self, palette_data, palette_alphas, anim_data):
        if not palette_data: return [], []
        
        limit = len(palette_data) // 3
        colors = [(i, tuple(palette_data[i*3:i*3+3])) for i in range(limit)]

        def sort_key(item):
            r, g, b = item[1]
            h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
            luma = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            
            if s < 0.18 or v < 0.15 or luma > 0.95:
                return (0, 0, luma, s)
                
            h_deg = h * 360
            if h_deg < 20 or h_deg >= 340: fam = 1 
            elif h_deg < 45: fam = 2 
            elif h_deg < 75: fam = 3 
            elif h_deg < 160: fam = 4 
            elif h_deg < 200: fam = 5 
            elif h_deg < 260: fam = 6 
            elif h_deg < 310: fam = 7 
            else: fam = 8 
            
            s_bucket = 0 if s < 0.45 else 1
            return (1, fam, s_bucket, luma)

        sorted_colors = sorted(colors, key=sort_key)
        mapping = {old_idx: new_idx for new_idx, (old_idx, rgb) in enumerate(sorted_colors)}

        new_pal = []
        for _, rgb in sorted_colors:
            new_pal.extend(rgb)

        palette_alphas = palette_alphas or [255] * limit
        new_alphas = [palette_alphas[old_idx] for old_idx, _ in sorted_colors]

        for data in anim_data.values():
            if "idx" in data:
                img_p = data["idx"]
                new_pixels = [mapping.get(p, p) for p in img_p.getdata()]
                img_p.putdata(new_pixels)

        return new_pal, new_alphas

    def on_tree_order_changed(self, event):
        self.unsaved_reorders += 1
        self.save_state()

    def activate_eyedropper(self):
        self.eyedropper_mode = True
        self.palette_picker_mode = False
        self.canvas.config(cursor="crosshair")

    def activate_palette_picker(self):
        self.palette_picker_mode = True
        self.eyedropper_mode = False
        self.canvas.config(cursor="crosshair")

    def on_canvas_press(self, event):
        if (self.eyedropper_mode or self.palette_picker_mode) and self.current_frame_list:
            fname = self.current_frame_list[self.current_frame_index]
            if fname in self.anim_data:
                img_data = self.anim_data[fname]
                w, h = img_data["idx"].size
                
                is_duo = self.duo_view_var.get()
                gap = 10
                disp_w = (w * 2 + gap) if is_duo else w
                
                z = min(self.canvas.winfo_width()/disp_w, self.canvas.winfo_height()/h) * 0.9 if self.zoom_auto_var.get() and self.canvas.winfo_width() > 10 and disp_w > 0 and h > 0 else self.zoom_level
                
                # Conversion des coordonnées avec le canvas de défilement centralisé
                sw, sh = int(disp_w * z), int(h * z)
                cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
                tl_x, tl_y = 0 - sw / 2, 0 - sh / 2
                
                img_x, img_y = int((cx - tl_x) / z), int((cy - tl_y) / z)
                
                if is_duo:
                    if img_x >= w + gap:
                        img_x -= (w + gap)
                    elif w <= img_x < w + gap:
                        img_x = -1 
                        
                if 0 <= img_x < w and 0 <= img_y < h:
                    px_idx = img_data["idx"].getpixel((img_x, img_y))
                    
                    if self.eyedropper_mode:
                        if px_idx * 3 + 2 < len(self.palette_data):
                            r, g, b = self.palette_data[px_idx*3 : px_idx*3+3]
                            self.transp_color.set(f"#{r:02x}{g:02x}{b:02x}".upper())
                            self.remove_bg_var.set(True)
                            
                    elif self.palette_picker_mode:
                        if px_idx < len(self.palette_data) // 3:
                            self.reference_color_index = px_idx
                            self.last_selected_index = px_idx
                            self.selected_indices = {px_idx}
                            if self.palette_snapshot is None: self.palette_snapshot = list(self.palette_data)
                            if self.group_mode_var.get():
                                self.update_selection_dynamic()
                            else:
                                self.draw_palette_grid()
                                
            self.eyedropper_mode = False
            self.palette_picker_mode = False
            self.canvas.config(cursor="")
            self.render_current()

    def generate_json(self): 
        self.show_notification("Structure JSON générée en mémoire (prête à exporter).")

    def preview_json(self):
        json_str = ProjectManager.build_compact_json(self.tree, self.imported_node, self.proj_name_entry.get_value())
        top = tk.Toplevel(self.parent); top.title("JSON Preview"); top.geometry(f"550x650+{self.parent.winfo_rootx() + 100}+{self.parent.winfo_rooty() + 100}")
        txt = tk.Text(top, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", wrap="none")
        vsb = ttk.Scrollbar(top, orient="vertical", command=txt.yview); hsb = ttk.Scrollbar(top, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set); vsb.pack(side="right", fill="y"); hsb.pack(side="bottom", fill="x"); txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", json_str); txt.config(state="disabled")

    def copy_frames(self, event=None):
        self.clipboard_frames = [self.tree.item(item, "text") for item in self.tree.selection() if "file" in self.tree.item(item, "tags")]

    def paste_frames(self, event=None):
        if not self.clipboard_frames: return
        sel = self.tree.selection()
        target_node, idx = self.imported_node, "end"
        if sel:
            if "group" in self.tree.item(sel[0], "tags"): target_node = sel[0]
            elif "file" in self.tree.item(sel[0], "tags"): target_node = self.tree.parent(sel[0]); idx = self.tree.index(sel[0]) + 1
        for fname in self.clipboard_frames:
            if fname in self.anim_data:
                self.tree.insert(target_node, idx if idx != "end" else "end", text=fname, tags=("file",))
                if isinstance(idx, int): idx += 1
        self.save_state()

    def delete_selected(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        
        def get_all_files(parent=""):
            res = []
            for child in self.tree.get_children(parent):
                if "file" in self.tree.item(child, "tags"):
                    res.append(child)
                if self.tree.item(child, "open"):
                    res.extend(get_all_files(child))
            return res
        
        flat_files = get_all_files()
        first_sel_idx = -1
        for item in sel:
            if item in flat_files:
                idx = flat_files.index(item)
                if first_sel_idx == -1 or idx < first_sel_idx:
                    first_sel_idx = idx

        deleted = False
        for item in list(sel):
            if "file" in self.tree.item(item, "tags"):
                self.tree.delete(item)
                deleted = True
                
        if deleted:
            self.save_state()
            remaining_files = get_all_files()
            if remaining_files:
                new_idx = first_sel_idx - 1
                if new_idx < 0:
                    new_idx = 0
                if new_idx >= len(remaining_files):
                    new_idx = len(remaining_files) - 1
                    
                next_item = remaining_files[new_idx]
                self.tree.selection_set(next_item)
                self.tree.focus(next_item)
                self.tree._last_clicked_item = next_item
                self.on_tree_select(None)
            else:
                self.current_frame_list = []
                self.canvas.delete("all")

    def on_tree_rclick(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            if item not in self.tree.selection():
                self.tree.selection_set(item)
            self.tree_menu.post(event.x_root, event.y_root)

    def clone_selected(self): self.copy_frames(); self.paste_frames()

    def refresh_sources(self):
        count = 0
        if not self.palette_data:
            messagebox.showinfo("Info", "Aucune palette active.")
            return
            
        full_pal = list(self.palette_data)
        pad_col = self.palette_data[:3] if self.palette_data else [0,0,0]
        while len(full_pal) < 768: full_pal.extend(pad_col)
        pal_img = Image.new("P", (1,1))
        pal_img.putpalette(full_pal)
        
        for fname, data in self.anim_data.items():
            fpath = data.get("path")
            if fpath and os.path.exists(fpath):
                try:
                    img = Image.open(fpath).convert("RGBA")
                    alpha = img.split()[3]; rgb = img.convert("RGB")
                    data["idx"] = rgb.quantize(palette=pal_img, dither=Image.Dither.NONE)
                    data["alpha"] = alpha
                    count += 1
                except Exception as e:
                    logging.error(f"Failed to refresh {fname}: {e}", exc_info=True)
        if count > 0:
            self.render_current()
            self.save_state()
            self.show_notification(f"{count} image(s) rafraîchie(s) depuis la source.")
        else:
            self.show_notification("Aucune image source n'a pu être actualisée.")

    def create_hsl_slider(self, parent, label, var, mini, maxi):
        r = ttk.Frame(parent); r.pack(fill="x", pady=2)
        ttk.Label(r, text=label, width=4).pack(side="left")
        s = tk.Scale(r, from_=mini, to=maxi, resolution=0.01, orient="horizontal", variable=var, showvalue=0)
        s.pack(side="left", fill="x", expand=True)
        s.bind("<Button-1>", self.start_group_edit); s.bind("<B1-Motion>", self.update_group_edit); s.bind("<ButtonRelease-1>", self.end_group_edit); s.bind("<Double-Button-1>", lambda e: self.reset_slider(var))
        tk.Entry(r, textvariable=var, width=5).pack(side="left")

    def reset_slider(self, var): var.set(0.0); self.update_group_edit(None) 

    def import_sprites(self):
        files = filedialog.askopenfilenames(filetypes=[("Images", "*.png;*.bmp")])
        if not files: return
        self.last_open_dir = os.path.dirname(files[0])

        if not self.palette_data:
            try:
                max_w = max((Image.open(f).width for f in files[:15]), default=100)
                total_h = sum((Image.open(f).height for f in files[:15]))
                if total_h == 0: total_h = 100
                
                combo = Image.new("RGB", (max_w, total_h))
                y_off = 0
                for f in files[:15]: 
                    i = Image.open(f).convert("RGB")
                    combo.paste(i, (0, y_off))
                    y_off += i.height
                    
                q = combo.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                raw_pal = q.getpalette()
                
                used_indices = set(q.getdata())
                active_palette = []
                for old_idx in sorted(used_indices):
                    active_palette.extend(raw_pal[old_idx*3 : old_idx*3+3])
                    
                self.palette_data = active_palette
                self.palette_alphas = [255] * len(used_indices)
                
                self.palette_data, self.palette_alphas = self._sort_palette_and_remap(self.palette_data, self.palette_alphas, self.anim_data)
                
                self.original_palette_data = list(self.palette_data)
                self.original_palette_alphas = list(self.palette_alphas)
            except Exception as e: logging.error(f"Quantize error: {e}", exc_info=True)
                
        self.palette_snapshot = None 
        sel = self.tree.selection()
        parent = sel[0] if sel and "group" in self.tree.item(sel[0], "tags") else self.imported_node
        
        full_pal = list(self.palette_data)
        pad_color = self.palette_data[:3] if self.palette_data else [0,0,0]
        while len(full_pal) < 768: full_pal.extend(pad_color)
        pal_img = Image.new("P", (1,1))
        pal_img.putpalette(full_pal)
            
        for f in files:
            fname = os.path.basename(f)
            try:
                img = Image.open(f).convert("RGBA"); alpha = img.split()[3]; rgb = img.convert("RGB")
                self.anim_data[fname] = {"idx": rgb.quantize(palette=pal_img, dither=Image.Dither.NONE), "alpha": alpha, "path": f}
                self.tree.insert(parent, "end", text=fname, tags=("file",))
            except Exception as e: logging.error(f"Import error {fname}: {e}", exc_info=True)
                
        self.draw_palette_grid(); self.btn_export.config(state="normal"); self.save_state(); self.show_notification(f"{len(files)} image(s) importée(s).")

    def export_sprites(self):
        if not self.anim_data: return
        dest = filedialog.askdirectory(initialdir=self.last_open_dir)
        if not dest: return

        popup = tk.Toplevel(self.parent); popup.title("Exporting Sprites...")
        popup.geometry(f"350x120+{self.parent.winfo_rootx() + (self.parent.winfo_width() - 350) // 2}+{self.parent.winfo_rooty() + (self.parent.winfo_height() - 120) // 2}")
        popup.transient(self.parent.winfo_toplevel()); popup.grab_set() 

        lbl_status = ttk.Label(popup, text="Starting export..."); lbl_status.pack(pady=(15, 5))
        progress = ttk.Progressbar(popup, orient="horizontal", length=300, mode="determinate"); progress.pack(pady=5)
        
        def process_item(item):
            fname, d = item
            base_name, _ = os.path.splitext(fname)
            export_fname = f"{base_name}.png"
            
            render_pal = list(self.palette_data)
            pad_color = self.palette_data[:3] if self.palette_data else [0,0,0]
            while len(render_pal) < 768: render_pal.extend(pad_color)
            d["idx"].putpalette(render_pal)
            
            img = d["idx"].convert("RGBA")
            base_alpha = d["alpha"]
            
            base_alphas_export = list(self.palette_alphas) if self.palette_alphas else [255]*(len(self.palette_data)//3)
            if self.remove_bg_var.get() and self.transp_color.get():
                try:
                    target = hex_to_rgb(self.transp_color.get())
                    best_idx, min_dist = 0, 999999
                    for i in range(min(256, len(self.palette_data)//3)):
                        dist = sum((self.palette_data[i*3+j] - target[j])**2 for j in range(3))
                        if dist < min_dist: min_dist, best_idx = dist, i
                    base_alphas_export[best_idx] = 0
                except: pass
            
            gray_pal = []
            for a_val in base_alphas_export: gray_pal.extend((a_val, a_val, a_val))
            gray_pal.extend([255]*(768-len(gray_pal)))
            
            alpha_mask = d["idx"].copy()
            alpha_mask.putpalette(gray_pal)
            
            final_alpha = ImageChops.multiply(base_alpha, alpha_mask.convert("L"))
            img.putalpha(final_alpha)
            
            dest_path = os.path.join(dest, export_fname)
            c = 1
            while os.path.exists(dest_path):
                export_fname = f"{base_name}_{c}.png"; dest_path = os.path.join(dest, export_fname); c += 1
            img.save(dest_path, format="PNG")
            return export_fname

        def worker():
            count, total = 0, len(self.anim_data)
            try:
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = {executor.submit(process_item, item): item for item in self.anim_data.items()}
                    for future in concurrent.futures.as_completed(futures):
                        name = future.result(); count += 1
                        self.parent.after(0, lambda current=count, tot=total, n=name: (
                            progress.config(value=(current/tot)*100),
                            lbl_status.config(text=f"Exported {current}/{tot}: {n}")
                        ))
                self.unsaved_color_edits = 0; self.unsaved_reorders = 0
                self.parent.after(0, lambda: (popup.destroy(), self.show_notification(f"{count} image(s) exportée(s) avec succès.")))
            except Exception as e:
                logging.error(f"Export failed: {e}", exc_info=True)
                self.parent.after(0, lambda: (popup.destroy(), messagebox.showerror("Export Failed", str(e))))

        threading.Thread(target=worker, daemon=True).start()

    def clear_assets(self):
        if not messagebox.askyesno("Confirm", "Clear all imported sprites and palette?"): return
        self.anim_data.clear(); self.palette_data = []; self.palette_alphas = []; self.palette_snapshot = None; self.current_frame_list = []; self.clipboard_frames = []
        self.original_palette_data = []; self.original_palette_alphas = []
        self.history_mgr.clear(); self.canvas.delete("all"); self.pal_canvas.delete("all")
        for group in self.tree.get_children(""):
            for file_node in self.tree.get_children(group): self.tree.delete(file_node)
        self.app.async_clear_cache(); self.btn_export.config(state="disabled"); self.save_state()
        
        self.current_frame_index = 0
        self.is_playing = False
        self.btn_play.config(text="▶ Play")
        if self.anim_job:
            self.app.root.after_cancel(self.anim_job)
            self.anim_job = None
            
        self.show_notification("Projet nettoyé.")

    def draw_palette_grid(self):
        self.pal_canvas.delete("all")
        for i in range(len(self.palette_data)//3):
            r,g,b = self.palette_data[i*3 : i*3+3]; x, y = (i%16)*16, (i//16)*16
            rect = self.pal_canvas.create_rectangle(x, y, x+16, y+16, fill=f"#{r:02x}{g:02x}{b:02x}", outline="gray", tags=f"c_{i}")
            if i in self.selected_indices:
                self.pal_canvas.itemconfig(rect, outline="white", width=2); self.pal_canvas.create_rectangle(x+2, y+2, x+14, y+14, outline="black", tags="sel_inner")
    
    def toggle_play(self): 
        self.is_playing = not self.is_playing
        self.btn_play.config(text="⏸ Stop" if self.is_playing else "▶ Play")
        if self.is_playing:
            self.run_anim_loop()
        elif self.anim_job:
            self.app.root.after_cancel(self.anim_job)
            self.anim_job = None

    def run_anim_loop(self):
        if self.anim_job:
            self.app.root.after_cancel(self.anim_job)
            self.anim_job = None
        if self.is_playing and self.current_frame_list:
            self.current_frame_index = (self.current_frame_index + 1) % len(self.current_frame_list)
            self.render_current()
            try: ms = int(self.framerate_ms_var.get())
            except: ms = 100
            self.anim_job = self.app.root.after(max(10, ms), self.run_anim_loop)

    def _build_render_image(self, d, pal, base_alphas):
        render_pal = list(pal)
        pad_col = pal[:3] if pal else [0,0,0]
        while len(render_pal) < 768: render_pal.extend(pad_col)
        
        idx_copy = d["idx"].copy()
        idx_copy.putpalette(render_pal)
        img = idx_copy.convert("RGBA")
        base_alpha = d["alpha"]
        
        base_alphas_render = list(base_alphas) if base_alphas else [255]*(len(pal)//3)

        if self.remove_bg_var.get() and self.transp_color.get():
            try:
                target = hex_to_rgb(self.transp_color.get())
                best_idx, min_dist = 0, 999999
                for i in range(min(256, len(pal)//3)):
                    dist = sum((pal[i*3+j] - target[j])**2 for j in range(3))
                    if dist < min_dist: min_dist, best_idx = dist, i
                base_alphas_render[best_idx] = 0
            except: pass

        gray_pal = []
        for a_val in base_alphas_render: gray_pal.extend((a_val, a_val, a_val))
        gray_pal.extend([255]*(768-len(gray_pal)))
        
        alpha_mask = d["idx"].copy()
        alpha_mask.putpalette(gray_pal)
        
        img.putalpha(ImageChops.multiply(base_alpha, alpha_mask.convert("L")))
        return img

    def render_current(self):
        if not self.current_frame_list:
            self.canvas.delete("all")
            return
            
        fname = self.current_frame_list[self.current_frame_index]
        if fname not in self.anim_data: return
        d = self.anim_data[fname]
        
        is_duo = self.duo_view_var.get()
        is_orig = self.preview_original_var.get()
        
        pal_mod = self.palette_data
        alphas_mod = self.palette_alphas
        
        pal_orig_data = self.original_palette_data if self.original_palette_data else self.palette_data
        alphas_orig_data = self.original_palette_alphas if self.original_palette_alphas else self.palette_alphas
        
        if is_duo:
            img1 = self._build_render_image(d, pal_orig_data, alphas_orig_data)
            img2 = self._build_render_image(d, pal_mod, alphas_mod)
            w, h = img1.size
            gap = 10
            disp_w = w * 2 + gap
            final_img = Image.new("RGBA", (disp_w, h), (0,0,0,0))
            final_img.paste(img1, (0, 0))
            final_img.paste(img2, (w + gap, 0))
            img_to_scale = final_img
            target_w = disp_w
        else:
            if is_orig:
                img_to_scale = self._build_render_image(d, pal_orig_data, alphas_orig_data)
            else:
                img_to_scale = self._build_render_image(d, pal_mod, alphas_mod)
            target_w, h = img_to_scale.size
        
        z = min(self.canvas.winfo_width()/target_w, self.canvas.winfo_height()/h) * 0.9 if self.zoom_auto_var.get() and self.canvas.winfo_width() > 10 and target_w > 0 and h > 0 else self.zoom_level
        self.lbl_zoom.config(text=f"{int(z*100)}%")
        w_new, h_new = int(target_w * z), int(h * z)
        
        if w_new > 0 and h_new > 0:
            img_to_scale = img_to_scale.resize((w_new, h_new), Image.Resampling.NEAREST)
        
        self.tk_img = ImageTk.PhotoImage(img_to_scale)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.tk_img, anchor="center")

    def on_tree_select(self, event):
        if not (sel := self.tree.selection()): return
        item = self.tree._last_clicked_item if getattr(self.tree, '_last_clicked_item', None) in sel else (self.tree.focus() if self.tree.focus() in sel else sel[-1])
        tags = self.tree.item(item, "tags")
        if "file" in tags:
            f = self.tree.item(item, "text"); self.current_frame_list = [f]; self.current_frame_index = 0
            self.is_playing = False; self.btn_play.config(text="▶ Play")
            if self.anim_job:
                self.app.root.after_cancel(self.anim_job)
                self.anim_job = None
            self.render_current()
            self.last_open_dir = os.path.dirname(os.path.join(self.last_open_dir, f)) 
        elif "group" in tags:
            files = [self.tree.item(c, "text") for c in self.tree.get_children(item)]
            self.current_frame_list = files; self.current_frame_index = 0
            if files: 
                was_playing = self.is_playing
                self.is_playing = True; self.btn_play.config(text="⏸ Stop")
                if not was_playing: self.run_anim_loop()

    def on_palette_click(self, event):
        if event.x < 0 or event.y < 0 or event.x >= 256 or event.y >= 256: return
        idx = (event.y // 16) * 16 + (event.x // 16)
        if idx >= len(self.palette_data) // 3: return
        
        if not self.group_mode_var.get():
            self.last_selected_index = idx; self.selected_indices = {idx}
            self.draw_palette_grid(); self.open_popup_editor(idx, event); return
        self.reference_color_index = idx; self.last_selected_index = idx
        if self.palette_snapshot is None: self.palette_snapshot = list(self.palette_data)
        self.update_selection_dynamic()

    def on_palette_rclick(self, event):
        if event.x < 0 or event.y < 0 or event.x >= 256 or event.y >= 256: return
        idx = (event.y // 16) * 16 + (event.x // 16)
        if idx >= len(self.palette_data) // 3: return
        
        if idx in self.selected_indices: self.selected_indices.remove(idx)
        else: self.selected_indices.add(idx)
        self.apply_hsl_to_selection(); self.draw_palette_grid(); self.render_current()

    def update_selection_dynamic(self):
        if self.reference_color_index == -1: return
        if self.palette_snapshot is None: self.palette_snapshot = list(self.palette_data)
        target = self.palette_snapshot[self.reference_color_index*3 : self.reference_color_index*3+3]
        max_dist = 442.0 * (self.tol_var.get() / 100.0)
        self.selected_indices = {i for i in range(len(self.palette_snapshot)//3) if math.sqrt(sum((t - c) ** 2 for t, c in zip(target, self.palette_snapshot[i*3 : i*3+3]))) <= max_dist}
        self.apply_hsl_to_selection(); self.draw_palette_grid(); self.render_current()

    def start_group_edit(self, event):
        if self.palette_snapshot is None: self.palette_snapshot = list(self.palette_data)
        
    def update_group_edit(self, event): self.apply_hsl_to_selection(); self.draw_palette_grid(); self.render_current()
    
    def end_group_edit(self, event): pass

    def apply_hsl_to_selection(self):
        if self.palette_snapshot is None: return
        dh, ds, dl = self.grp_h.get(), self.grp_s.get(), self.grp_l.get()
        self.palette_data = list(self.palette_snapshot)
        for idx in self.selected_indices:
            r, g, b = self.palette_snapshot[idx*3:idx*3+3]
            h, l, s = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
            nr, ng, nb = colorsys.hls_to_rgb((h + dh) % 1.0, max(0.0, min(1.0, l + dl)), max(0.0, min(1.0, s + ds)))
            
            self.palette_data[idx*3:idx*3+3] = [
                int(max(0, min(255, nr * 255))), 
                int(max(0, min(255, ng * 255))), 
                int(max(0, min(255, nb * 255)))
            ]

    def apply_group_edit(self):
        self.palette_snapshot = None; self.grp_h.set(0); self.grp_s.set(0); self.grp_l.set(0)
        self.selected_indices.clear(); self.reference_color_index = -1
        self.unsaved_color_edits += 1
        self.draw_palette_grid(); self.save_state()

    def cancel_group_edit(self):
        if self.palette_snapshot: self.palette_data = list(self.palette_snapshot); self.palette_snapshot = None
        self.grp_h.set(0); self.grp_s.set(0); self.grp_l.set(0)
        self.selected_indices.clear(); self.reference_color_index = -1
        self.draw_palette_grid(); self.render_current()

    def clear_selection(self): self.cancel_group_edit()

    def open_popup_editor(self, idx, event):
        if self.active_popup: self.active_popup.destroy()
        if not self.palette_alphas: self.palette_alphas = [255]*(len(self.palette_data)//3)
        rgba = tuple(self.palette_data[idx*3 : idx*3+3]) + (self.palette_alphas[idx],)
        orig_rgba = list(rgba)
        
        def on_up(i, c):
            self.palette_data[i*3:i*3+3], self.palette_alphas[i] = c[0:3], c[3]
            self.draw_palette_grid(); self.render_current()
        def on_ap(i, c): 
            self.active_popup = None
            self.unsaved_color_edits += 1
            self.save_state()
        def on_ca(i): on_up(i, orig_rgba); self.active_popup = None

        self.active_popup = PopupColorEditor(self.app.root, idx, rgba, on_up, on_ap, on_ca)
        self.active_popup.geometry(f"+{self.pal_canvas.winfo_rootx() + event.x + 20}+{self.pal_canvas.winfo_rooty() + event.y}")

    def import_palette(self):
        if not (f := filedialog.askopenfilename(filetypes=[("Palette", "*.pal;*.act")])): return
        try:
            with open(f, 'r') as pal_file:
                lines = pal_file.readlines()
                if "JASC-PAL" not in lines[0]: messagebox.showerror("Error", "Only JASC-PAL supported for now"); return
                
                raw_data = [int(p) for i in range(int(lines[2].strip())) for p in lines[3+i].strip().split()[:3]]
                valid_len = len(raw_data)
                while valid_len >= 3 and raw_data[valid_len-3:valid_len] == raw_data[:3]:
                    valid_len -= 3
                if valid_len == 0 and len(raw_data) > 0: valid_len = 3 
                
                self.palette_data = raw_data[:valid_len]
                self.palette_alphas = [255] * (len(self.palette_data)//3)
                
                self.draw_palette_grid(); self.render_current(); self.save_state(); self.show_notification("Palette importée avec succès.")
        except Exception as e: logging.error(f"Palette import error: {e}", exc_info=True); messagebox.showerror("Error", str(e))

    def export_palette(self):
        if not (f := filedialog.asksaveasfilename(defaultextension=".pal", filetypes=[("JASC Palette", "*.pal")])): return
        try:
            with open(f, 'w') as pal_file:
                pal_file.write("JASC-PAL\n0100\n256\n")
                for i in range(256): 
                    if i*3+2 < len(self.palette_data):
                        pal_file.write(f"{self.palette_data[i*3]} {self.palette_data[i*3+1]} {self.palette_data[i*3+2]}\n")
                    else:
                        pad_r, pad_g, pad_b = self.palette_data[:3] if self.palette_data else [0,0,0]
                        pal_file.write(f"{pad_r} {pad_g} {pad_b}\n")
            self.show_notification("Palette exportée avec succès.")
        except Exception as e: logging.error(f"Palette export error: {e}", exc_info=True); messagebox.showerror("Error", str(e))