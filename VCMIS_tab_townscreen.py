import os
import logging
import io
import threading
import concurrent.futures
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageTk, ImageDraw

from VCMIS_ui_components import PlaceholderEntry, AdvancedTreeview, NotificationMixin, CanvasViewerMixin
from VCMIS_utils_project import HistoryManager, ProjectManager
from VCMIS_utils_image import apply_transparency, get_shifted_image, generate_area_image, generate_border_image

class TownscreenTab(NotificationMixin, CanvasViewerMixin):
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        
        self.imported_images = {}
        self.history_mgr = HistoryManager(15, self.restore_state)
        
        self.current_preview = None
        self.current_filepath = None
        self.current_filename = None
        self.notification_job = None
        self._refresh_job = None
        
        self.unsaved_mask_edits = 0
        
        self.sort_state = "manual" 
        self.manual_order_snapshot = []
        self.zoom_level = 1.0
        
        self.view_mode = tk.StringVar(value="townscreen")
        self.fill_color = tk.StringVar(value="#C2BA79")
        self.bg_color = tk.StringVar(value="#00FFFF")
        self.preview_bg_color = tk.StringVar(value="#9C9C9C") 
        self.default_canvas_bg = "#1a1a1a"
        
        self.remove_bg_var = tk.BooleanVar(value=False)
        self.transp_color = tk.StringVar(value="#00FFFF")
        self.eyedropper_mode = False
        
        self.draw_mode_var = tk.StringVar(value="none")
        
        self.brush_size_var = tk.StringVar(value="10")
        self.overlay_opacity_var = tk.StringVar(value="25")
        self.offset_x_var = tk.StringVar(value="0")
        self.offset_y_var = tk.StringVar(value="0")
        
        self.global_last_x = None
        self.global_last_y = None
        self.drag_start_x = None
        self.drag_start_y = None
        self.ortho_axis = None
        
        self.build_ui()
        self.setup_global_bindings()
        self.save_state()

        self.brush_size_var.trace_add("write", self.generate_cursor_image)
        self.draw_mode_var.trace_add("write", self.generate_cursor_image)
        self.view_mode.trace_add("write", self.generate_cursor_image)

    def has_unsaved_changes(self):
        return self.unsaved_mask_edits >= 1

    def undo(self, event=None): self.history_mgr.undo()
    def redo(self, event=None): self.history_mgr.redo()

    # ---- Implémentation requise par CanvasViewerMixin ----
    def is_tab_active(self): 
        return self.app.notebook.index(self.app.notebook.select()) == 3
    def can_zoom(self): 
        return bool(self.current_filepath)
    def on_zoom_changed(self): 
        self.refresh_preview()
        self.generate_cursor_image()
    # -----------------------------------------------------

    def validate_numeric_input(self, new_val):
        if new_val == "" or new_val == "-":
            return True
        return new_val.lstrip('-').isdigit()

    def build_ui(self):
        self.parent.columnconfigure(0, weight=0, minsize=260); self.parent.columnconfigure(1, weight=1); self.parent.rowconfigure(0, weight=1)

        vcmd = (self.parent.register(self.validate_numeric_input), '%P')

        left_panel = ttk.Frame(self.parent, relief="groove"); left_panel.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        proj_frame = ttk.Frame(left_panel); proj_frame.pack(fill="x", padx=5, pady=(5, 0))
        ttk.Button(proj_frame, text="Import Project", command=self.import_project).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(proj_frame, text="Export Project", command=self.export_project).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Separator(left_panel, orient="horizontal").pack(fill="x", padx=5, pady=5)
        
        btn_frame = ttk.Frame(left_panel); btn_frame.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Button(btn_frame, text="Import", command=self.import_assets).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_frame, text="Export", command=self.export_assets).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_frame, text="Clear Assets", command=self.clear_assets).pack(side="left", fill="x", expand=True, padx=2)
        
        self.tree = AdvancedTreeview(left_panel, allow_groups=False, columns=("del", "name"), show="headings", selectmode="extended")
        self.tree.heading("del", text="✖"); self.tree.column("del", width=35, stretch=False, anchor="center")
        self.tree.heading("name", text="Filename   ", anchor="w", command=self.cycle_sort); self.tree.column("name", anchor="w")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        
        scroll_y = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview); scroll_y.pack(side="right", fill="y"); self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select); self.tree.bind("<ButtonRelease-1>", self.on_delete_click, add="+")
        self.tree.bind("<<TreeOrderChanged>>", self.on_tree_order_changed); self.tree.bind("<Delete>", self.on_delete_key); self.tree.bind("<BackSpace>", self.on_delete_key)
        
        h_frame = ttk.Frame(left_panel); h_frame.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Button(h_frame, text="↶ Undo", command=self.undo).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(h_frame, text="↷ Redo", command=self.redo).pack(side="left", expand=True, fill="x", padx=1)

        right_panel = ttk.Frame(self.parent, relief="groove"); right_panel.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        ttk.Label(right_panel, text="Townscreen Preview (800x374 pixels)", font=("Arial", 11, "bold")).pack(pady=(10, 5))
        
        top_ctrl_frame = ttk.Frame(right_panel); top_ctrl_frame.pack(fill="x", pady=2, padx=10)
        mode_frame = ttk.Frame(top_ctrl_frame); mode_frame.pack(side="left")
        ttk.Radiobutton(mode_frame, text="Townscreen", variable=self.view_mode, value="townscreen", command=self.refresh_preview).pack(side="left", padx=5)
        ttk.Radiobutton(mode_frame, text="Building Area", variable=self.view_mode, value="area", command=self.refresh_preview).pack(side="left", padx=5)
        ttk.Radiobutton(mode_frame, text="Building Border", variable=self.view_mode, value="border", command=self.refresh_preview).pack(side="left", padx=5)
        
        self.lbl_notification = ttk.Label(top_ctrl_frame, text="", font=("Arial", 9, "italic"), foreground="#888888"); self.lbl_notification.pack(side="left", padx=15)
        
        zoom_frame = ttk.Frame(top_ctrl_frame); zoom_frame.pack(side="right")
        ttk.Button(zoom_frame, text="↺", width=2, command=self.reset_view).pack(side="left", padx=5)
        ttk.Button(zoom_frame, text="-", width=2, command=self.zoom_out).pack(side="left")
        self.lbl_zoom = ttk.Label(zoom_frame, text="100%", width=5, anchor="center"); self.lbl_zoom.pack(side="left", padx=2)
        ttk.Button(zoom_frame, text="+", width=2, command=self.zoom_in).pack(side="left")
        
        canvas_frame = tk.Frame(right_panel, bd=2, relief="groove"); canvas_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(canvas_frame, bg=self.preview_bg_color.get(), highlightthickness=0, scrollregion=(-5000, -5000, 5000, 5000))
        self.canvas.pack(fill="both", expand=True)
        
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Motion>", self.on_canvas_hover)
        self.canvas.bind("<Leave>", self.on_canvas_leave)
        
        # Initialisation globale des bindings depuis le mixin
        self.setup_canvas_bindings()
        
        tools_frame = ttk.Frame(right_panel); tools_frame.pack(fill="x", pady=10, padx=10)
        tools_frame.columnconfigure(0, weight=1); tools_frame.columnconfigure(1, weight=1); tools_frame.columnconfigure(2, weight=1)
        
        col1 = ttk.Frame(tools_frame); col1.grid(row=0, column=0, sticky="nsew", padx=5)
        color_frame = ttk.LabelFrame(col1, text="Rendering Colors"); color_frame.pack(fill="x", pady=2); color_frame.columnconfigure(1, weight=1)
        self.swatch_fill = tk.Label(color_frame, bg=self.fill_color.get(), width=2, relief="solid", bd=1); self.swatch_fill.grid(row=0, column=0, padx=5, pady=3)
        self.btn_fill = ttk.Button(color_frame, text="Set Area/Border Color", command=self.choose_fill_color); self.btn_fill.grid(row=0, column=1, sticky="ew", padx=(0,5), pady=3)
        self.swatch_bg = tk.Label(color_frame, bg=self.bg_color.get(), width=2, relief="solid", bd=1); self.swatch_bg.grid(row=1, column=0, padx=5, pady=3)
        self.btn_bg = ttk.Button(color_frame, text="Set Background Color", command=self.choose_bg_color); self.btn_bg.grid(row=1, column=1, sticky="ew", padx=(0,5), pady=3)
        self.swatch_preview_bg = tk.Label(color_frame, bg=self.preview_bg_color.get(), width=2, relief="solid", bd=1); self.swatch_preview_bg.grid(row=2, column=0, padx=5, pady=3)
        self.btn_preview_bg = ttk.Button(color_frame, text="Set Canvas Transp. Color", command=self.choose_preview_bg_color); self.btn_preview_bg.grid(row=2, column=1, sticky="ew", padx=(0,5), pady=3)
        ttk.Button(color_frame, text="↺ Reset Colors", command=self.reset_colors).grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
        
        col2 = ttk.Frame(tools_frame); col2.grid(row=0, column=1, sticky="nsew", padx=5)
        transp_frame = ttk.LabelFrame(col2, text="Background Removal"); transp_frame.pack(fill="x", pady=2); transp_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(transp_frame, text="Remove Color:", variable=self.remove_bg_var, command=self.refresh_preview).grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(transp_frame, textvariable=self.transp_color, width=9).grid(row=0, column=1, sticky="ew", padx=(0,5), pady=3); self.transp_color.trace_add("write", lambda *args: self.refresh_preview_safe())
        ttk.Button(transp_frame, text="🖌️ Eyedropper", command=self.activate_eyedropper).grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
        
        offset_frame = ttk.LabelFrame(col2, text="Offset (X / Y)"); offset_frame.pack(fill="x", pady=2); offset_frame.columnconfigure(1, weight=1); offset_frame.columnconfigure(3, weight=1)
        self.offset_x_var.trace_add("write", self.on_offset_changed); self.offset_y_var.trace_add("write", self.on_offset_changed)
        ttk.Label(offset_frame, text="X:").grid(row=0, column=0, sticky="e", padx=(5,2), pady=3)
        ttk.Spinbox(offset_frame, from_=-2000, to=2000, textvariable=self.offset_x_var, width=5, command=self.on_offset_changed, validate="key", validatecommand=vcmd).grid(row=0, column=1, sticky="ew", padx=(0,5), pady=3)
        ttk.Label(offset_frame, text="Y:").grid(row=0, column=2, sticky="e", padx=(5,2), pady=3)
        ttk.Spinbox(offset_frame, from_=-2000, to=2000, textvariable=self.offset_y_var, width=5, command=self.on_offset_changed, validate="key", validatecommand=vcmd).grid(row=0, column=3, sticky="ew", padx=(0,5), pady=3)
        ttk.Button(offset_frame, text="Reset Offset", command=self.reset_offset).grid(row=1, column=0, columnspan=4, sticky="ew", padx=5, pady=3)

        col3 = ttk.Frame(tools_frame); col3.grid(row=0, column=2, sticky="nsew", padx=5)
        mask_frame = ttk.LabelFrame(col3, text="Mask Editor (Area/Border)"); mask_frame.pack(fill="x", pady=2)
        m_r1 = ttk.Frame(mask_frame); m_r1.pack(fill="x", pady=3, padx=5)
        ttk.Radiobutton(m_r1, text="🚫 None", variable=self.draw_mode_var, value="none").pack(side="left", padx=2)
        ttk.Radiobutton(m_r1, text="🖊️ Pen", variable=self.draw_mode_var, value="pen").pack(side="left", padx=2)
        ttk.Radiobutton(m_r1, text="🧽 Eraser", variable=self.draw_mode_var, value="eraser").pack(side="left", padx=2)
        m_r2 = ttk.Frame(mask_frame); m_r2.pack(fill="x", pady=3, padx=5)
        ttk.Label(m_r2, text="Size:").pack(side="left")
        ttk.Spinbox(m_r2, from_=1, to=100, textvariable=self.brush_size_var, width=4, validate="key", validatecommand=vcmd).pack(side="left", padx=5)
        ttk.Button(m_r2, text="Reset Mask", command=self.reset_mask).pack(side="right")
        
        overlay_frame = ttk.LabelFrame(col3, text="Overlay (Base Image Preview)"); overlay_frame.pack(fill="x", pady=2)
        o_r1 = ttk.Frame(overlay_frame); o_r1.pack(fill="x", pady=5, padx=5)
        ttk.Label(o_r1, text="Opacity %:").pack(side="left")
        
        self.opacity_scale = tk.Scale(o_r1, from_=0, to=100, orient="horizontal", resolution=1, showvalue=0)
        self.opacity_scale.set(25)
        
        def on_scale_change(v):
            new_val = str(int(float(v)))
            if self.overlay_opacity_var.get() != new_val:
                self.overlay_opacity_var.set(new_val)
                
        self.opacity_scale.config(command=on_scale_change)
        self.opacity_scale.pack(side="left", fill="x", expand=True, padx=5)
        
        ttk.Spinbox(o_r1, from_=0, to=100, textvariable=self.overlay_opacity_var, width=4, validate="key", validatecommand=vcmd).pack(side="right")
        
        def on_opacity_change(*args):
            try:
                val = int(float(self.overlay_opacity_var.get() or 0))
                if self.opacity_scale.get() != val:
                    self.opacity_scale.set(val)
            except ValueError:
                pass
            self.refresh_preview_safe()
            
        self.overlay_opacity_var.trace_add("write", on_opacity_change)
        
        json_f = ttk.Frame(right_panel); json_f.pack(fill="x", padx=10, pady=5)
        ttk.Button(json_f, text="Preview JSON", command=self.preview_json).pack(side="left", padx=2)
        ttk.Label(json_f, text="Name:").pack(side="left", padx=(10, 2)); self.proj_name_entry = PlaceholderEntry(json_f, "projectName"); self.proj_name_entry.pack(side="left", fill="x", expand=True, padx=2)

        self.draw_placeholder()

    def setup_global_bindings(self):
        top = self.parent.winfo_toplevel()
        self.bind_global_zoom(top)
        top.bind("<KeyPress-x>", self.toggle_pen_eraser, add="+")
        top.bind("<KeyPress-X>", self.toggle_pen_eraser, add="+")
        top.bind_all("<Button-1>", self.remove_focus_if_outside, add="+")

    def remove_focus_if_outside(self, event):
        if not self.is_tab_active(): return
        widget = event.widget
        if not isinstance(widget, (tk.Entry, ttk.Entry, tk.Spinbox, ttk.Spinbox, tk.Text)):
            self.parent.focus_set()

    def toggle_pen_eraser(self, event=None):
        if not self.is_tab_active(): return
        if event and hasattr(event, "widget") and isinstance(event.widget, (tk.Entry, ttk.Entry, tk.Text, tk.Spinbox, ttk.Spinbox)): return
        
        if self.view_mode.get() in ["area", "border"]:
            if self.draw_mode_var.get() == "pen":
                self.draw_mode_var.set("eraser")
            else:
                self.draw_mode_var.set("pen")

    def generate_cursor_image(self, *args):
        if not hasattr(self, 'canvas') or not self.canvas.winfo_exists(): return
        if self.view_mode.get() not in ["area", "border"] or self.draw_mode_var.get() not in ["pen", "eraser"]:
            if hasattr(self, 'cursor_item'): self.canvas.coords(self.cursor_item, -5000, -5000)
            return
            
        try: brush_size = int(float(self.brush_size_var.get() or 10))
        except ValueError: brush_size = 10
        
        r = max(1, int((brush_size * self.zoom_level) / 2))
        target_size = r * 2 + 6
        
        if getattr(self, 'last_cursor_size', None) == target_size and hasattr(self, 'cursor_item') and self.canvas.find_withtag("brush_cursor_img"):
            return
            
        self.last_cursor_size = target_size
        img = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, target_size-3, target_size-3], outline="black", width=1)
        draw.ellipse([3, 3, target_size-4, target_size-4], outline="white", width=1)
        
        self.cursor_photo = ImageTk.PhotoImage(img)
        if not hasattr(self, 'cursor_item') or not self.canvas.find_withtag("brush_cursor_img"):
            self.cursor_item = self.canvas.create_image(-5000, -5000, image=self.cursor_photo, tags="brush_cursor_img", anchor="center")
        else: self.canvas.itemconfig(self.cursor_item, image=self.cursor_photo)
        self.canvas.tag_raise("brush_cursor_img")

    def update_brush_cursor(self, x, y):
        if not self.current_filepath or self.draw_mode_var.get() not in ["pen", "eraser"] or self.view_mode.get() not in ["area", "border"]:
            if hasattr(self, 'cursor_item'): self.canvas.coords(self.cursor_item, -5000, -5000)
            return
        cx, cy = self.canvas.canvasx(x), self.canvas.canvasy(y)
        if hasattr(self, 'cursor_item') and self.canvas.find_withtag("brush_cursor_img"):
            self.canvas.coords(self.cursor_item, cx, cy); self.canvas.tag_raise("brush_cursor_img")

    def on_canvas_hover(self, event):
        if not self.eyedropper_mode: self.update_brush_cursor(event.x, event.y)
            
    def on_canvas_leave(self, event):
        if hasattr(self, 'cursor_item'): self.canvas.coords(self.cursor_item, -5000, -5000)

    def activate_eyedropper(self):
        self.eyedropper_mode = True; self.draw_mode_var.set("none"); self.canvas.config(cursor="crosshair")

    def on_canvas_press(self, event):
        if self.eyedropper_mode and self.current_filepath:
            img_x, img_y, w, h = self.get_image_coords(event.x, event.y)
            if img_x is not None and 0 <= img_x < w and 0 <= img_y < h:
                try:
                    r, g, b = Image.open(self.current_filepath).convert("RGB").getpixel((img_x, img_y))
                    self.transp_color.set(f"#{r:02x}{g:02x}{b:02x}".upper()); self.remove_bg_var.set(True)
                except Exception as e: logging.warning(f"Eyedropper failed: {e}")
            self.eyedropper_mode = False; self.canvas.config(cursor=""); self.refresh_preview(); return

        mode = self.draw_mode_var.get()
        if mode in ["pen", "eraser"] and self.current_filepath:
            if self.view_mode.get() not in ["area", "border"]:
                messagebox.showwarning("Mask Editor", "The mask editor can only be used in 'Building Area' or 'Building Border' view modes.")
                self.draw_mode_var.set("none"); return
                
            self.update_brush_cursor(event.x, event.y)
            img_x, img_y, w, h = self.get_image_coords(event.x, event.y)
            if img_x is None: return
            
            data = self.imported_images[self.current_filename]
            if data.get("custom_mask") is None:
                base_img = Image.open(self.current_filepath).convert("RGBA")
                if self.transp_color.get(): base_img = apply_transparency(base_img, self.transp_color.get())
                data["custom_mask"] = base_img.getchannel('A').copy()

            if (event.state & 0x0001) != 0 and self.global_last_x is not None and self.global_last_y is not None:
                self.draw_on_mask(img_x, img_y, mode, w, h, self.global_last_x, self.global_last_y)
                self.global_last_x = self.drag_start_x = self.last_draw_x = img_x
                self.global_last_y = self.drag_start_y = self.last_draw_y = img_y
                self.ortho_axis = None
                self.canvas.delete("temp_draw"); self.refresh_preview(); self.unsaved_mask_edits += 1; self.save_state()
                return
                
            self.global_last_x = self.drag_start_x = self.last_draw_x = img_x
            self.global_last_y = self.drag_start_y = self.last_draw_y = img_y
            self.ortho_axis = None
            self.draw_on_mask(img_x, img_y, mode, w, h)

    def on_canvas_drag(self, event):
        if self.eyedropper_mode: return
        mode = self.draw_mode_var.get()
        if mode in ["pen", "eraser"] and self.current_filepath and hasattr(self, 'last_draw_x'):
            if self.view_mode.get() not in ["area", "border"]: return
            
            self.update_brush_cursor(event.x, event.y)
            img_x, img_y, w, h = self.get_image_coords(event.x, event.y)
            if img_x is None: return

            if (event.state & 0x0001) != 0:
                if self.ortho_axis is None:
                    self.ortho_axis = 'x' if abs(img_x - self.drag_start_x) > abs(img_y - self.drag_start_y) else 'y'
                if self.ortho_axis == 'x': img_y = self.drag_start_y
                elif self.ortho_axis == 'y': img_x = self.drag_start_x
            else: self.ortho_axis = None
                
            self.draw_on_mask(img_x, img_y, mode, w, h, self.last_draw_x, self.last_draw_y)
            self.last_draw_x, self.last_draw_y = img_x, img_y
            self.global_last_x, self.global_last_y = img_x, img_y

    def on_canvas_release(self, event):
        if self.eyedropper_mode: return
        if self.draw_mode_var.get() in ["pen", "eraser"] and hasattr(self, 'last_draw_x'):
            if self.view_mode.get() not in ["area", "border"]: return
            self.canvas.delete("temp_draw")
            self.refresh_preview()
            self.unsaved_mask_edits += 1
            self.save_state()
            del self.last_draw_x
            self.update_brush_cursor(event.x, event.y)

    def draw_on_mask(self, x, y, mode, w, h, last_x=None, last_y=None):
        draw = ImageDraw.Draw(self.imported_images[self.current_filename]["custom_mask"])
        color = 255 if mode == "pen" else 0
        try: brush_size = int(float(self.brush_size_var.get() or 10))
        except ValueError: brush_size = 10
        r = brush_size // 2

        if last_x is not None and last_y is not None:
            draw.line([(last_x, last_y), (x, y)], fill=color, width=brush_size, joint="curve")
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
        else: draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

        try: ox, oy = int(float(self.offset_x_var.get() or 0)), int(float(self.offset_y_var.get() or 0))
        except ValueError: ox, oy = 0, 0
        z = self.zoom_level
        cx, cy = 0 - (w * z)/2 + (x + ox) * z, 0 - (h * z)/2 + (y + oy) * z
        tk_color = "#00FF00" if mode == "pen" else "#FF0000" 
        
        if last_x is not None and last_y is not None:
            last_cx, last_cy = 0 - (w * z)/2 + (last_x + ox) * z, 0 - (h * z)/2 + (last_y + oy) * z
            self.canvas.create_line(last_cx, last_cy, cx, cy, fill=tk_color, width=brush_size * z, capstyle=tk.ROUND, tags="temp_draw")
        else:
            scaled_r = (brush_size * z) / 2
            self.canvas.create_oval(cx - scaled_r, cy - scaled_r, cx + scaled_r, cy + scaled_r, fill=tk_color, outline="", tags="temp_draw")
            
        if hasattr(self, 'cursor_item') and self.canvas.find_withtag("brush_cursor_img"):
            self.canvas.tag_raise("brush_cursor_img")

    def preview_json(self):
        json_str = ProjectManager.build_compact_json(self.tree, None, self.proj_name_entry.get_value(), is_flat=True)
        top = tk.Toplevel(self.parent); top.title("JSON Preview"); top.geometry(f"550x650+{self.parent.winfo_rootx() + 100}+{self.parent.winfo_rooty() + 100}")
        txt = tk.Text(top, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", wrap="none")
        vsb = ttk.Scrollbar(top, orient="vertical", command=txt.yview); hsb = ttk.Scrollbar(top, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set); vsb.pack(side="right", fill="y"); hsb.pack(side="bottom", fill="x"); txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", json_str); txt.config(state="disabled")

    def export_project(self):
        if not self.imported_images:
            messagebox.showinfo("Export Project", "No project data to export."); return
        if not (f := filedialog.asksaveasfilename(defaultextension=".vsp", filetypes=[("VCMI Townscreen Project", "*.vsp")])): return
        try:
            ProjectManager.export_townscreen_vsp(f, [self.tree.item(item, "values")[1] for item in self.tree.get_children() if self.tree.item(item, "values") and len(self.tree.item(item, "values")) > 1], self.imported_images)
            self.unsaved_mask_edits = 0
            self.show_notification("Project successfully exported (.vsp).")
        except Exception as e: logging.error(f"Export project error: {e}", exc_info=True); messagebox.showerror("Error", str(e))

    def import_project(self):
        if not (f := filedialog.askopenfilename(filetypes=[("VCMI Townscreen Project", "*.vsp")])): return
        try:
            tree_order, meta, imported_images = ProjectManager.import_townscreen_vsp(f, self.app.cache_dir)
            self.imported_images.clear(); self.imported_images.update(imported_images)
            self.tree.delete(*self.tree.get_children()); self.clear_preview_state()
            self.sort_state = "manual"; self.tree.heading("name", text="Filename   "); self.manual_order_snapshot.clear()
            for fname in tree_order:
                if fname in self.imported_images: self.tree.insert("", "end", values=("❌", fname), tags=("file",))
            for fname in meta.keys():
                if fname not in tree_order: self.tree.insert("", "end", values=("❌", fname), tags=("file",))
            self.save_state(); children = self.tree.get_children()
            if children:
                self.tree.selection_set(children[0]); self.tree.focus(children[0]); self.tree._last_clicked_item = children[0]
                self.on_tree_select(None); self.center_view()
            self.unsaved_mask_edits = 0
            self.show_notification("Project successfully imported.")
        except Exception as e: logging.error(f"Import project error: {e}", exc_info=True); messagebox.showerror("Error", f"Failed to load project.\n{e}")

    def cycle_sort(self):
        if not (children := self.tree.get_children()): return
        if self.sort_state == "manual":
            self.sort_state = "asc"; self.tree.heading("name", text="Filename ▲")
            self.manual_order_snapshot = [self.tree.item(i, "values")[1] for i in children]
            self.apply_sort(reverse=False)
        elif self.sort_state == "asc":
            self.sort_state = "desc"; self.tree.heading("name", text="Filename ▼")
            self.apply_sort(reverse=True)
        elif self.sort_state == "desc":
            self.sort_state = "manual"; self.tree.heading("name", text="Filename   ")
            self.restore_manual_order()
        self.sync_data_with_tree(); self.save_state()

    def apply_sort(self, reverse=False):
        for index, (_, k) in enumerate(sorted([(self.tree.item(k, "values")[1].lower(), k) for k in self.tree.get_children()], reverse=reverse)): self.tree.move(k, '', index)

    def restore_manual_order(self):
        if not hasattr(self, 'manual_order_snapshot'): return
        fname_to_item = {self.tree.item(item, "values")[1]: item for item in self.tree.get_children()}
        idx = 0
        for fname in self.manual_order_snapshot:
            if fname in fname_to_item:
                self.tree.move(fname_to_item[fname], '', idx); idx += 1; del fname_to_item[fname]
        for fname, item in fname_to_item.items():
            self.tree.move(item, '', idx); idx += 1

    def on_tree_order_changed(self, event):
        if self.sort_state != "manual":
            self.sort_state = "manual"; self.tree.heading("name", text="Filename   ")
        self.sync_data_with_tree(); self.save_state()

    def on_canvas_configure(self, event):
        if not self.current_filepath: self.center_view()
        
    def get_image_coords(self, event_x, event_y):
        if not self.current_filepath: return None, None, None, None
        try:
            cx, cy, z = self.canvas.canvasx(event_x), self.canvas.canvasy(event_y), self.zoom_level
            img = Image.open(self.current_filepath); w, h = img.size
            try: ox, oy = int(float(self.offset_x_var.get() or 0)), int(float(self.offset_y_var.get() or 0))
            except ValueError: ox, oy = 0, 0
            img_x = int((cx - (0 - (w * z) / 2)) / z - ox)
            img_y = int((cy - (0 - (h * z) / 2)) / z - oy)
            return img_x, img_y, w, h
        except: return None, None, None, None

    def save_state(self):
        state = []
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            if values and len(values) > 1:
                fname = values[1]
                if fname in self.imported_images:
                    orig_data = self.imported_images[fname]
                    new_data = {"ox": orig_data.get("ox", 0), "oy": orig_data.get("oy", 0), "path": orig_data["path"]}
                    if (mask := orig_data.get("custom_mask")) is not None:
                        b = io.BytesIO(); mask.save(b, format="PNG", compress_level=1); new_data["custom_mask_bytes"] = b.getvalue()
                    else: new_data["custom_mask_bytes"] = None
                    state.append((fname, new_data))
        self.history_mgr.save_state(state)

    def restore_state(self, state):
        self.sort_state = "manual"; self.tree.heading("name", text="Filename   ")
        self.imported_images.clear(); self.tree.delete(*self.tree.get_children())
        
        for fname, data in state:
            new_data = {"ox": data["ox"], "oy": data["oy"], "path": data["path"], "custom_mask": None}
            if data.get("custom_mask_bytes") is not None: new_data["custom_mask"] = Image.open(io.BytesIO(data["custom_mask_bytes"])).copy()
            self.imported_images[fname] = new_data
            self.tree.insert("", "end", values=("❌", fname), tags=("file",))
            
        children = self.tree.get_children()
        current_active_files = [data["path"] for fname, data in state]
        
        if self.current_filepath and self.current_filepath not in current_active_files: self.clear_preview_state()
        elif self.current_filepath:
            for item in children:
                if self.tree.item(item, "values")[1] == self.current_filename:
                    self.tree.selection_set(item); self.tree.focus(item); break
            data = self.imported_images[self.current_filename]
            self.ignore_offset_trace = True; self.offset_x_var.set(str(data.get("ox", 0))); self.offset_y_var.set(str(data.get("oy", 0))); self.ignore_offset_trace = False
            self.refresh_preview()

    def clear_preview_state(self):
        self.current_filepath = self.current_filename = self.current_preview = self.tree._last_clicked_item = None
        self.ignore_offset_trace = True; self.offset_x_var.set("0"); self.offset_y_var.set("0"); self.ignore_offset_trace = False
        self.draw_placeholder()

    def draw_placeholder(self):
        self.canvas.delete("all"); self.canvas.config(bg=self.preview_bg_color.get(), scrollregion=(-5000, -5000, 5000, 5000))
        self.canvas.create_text(0, 0, text="Select an image from the list on the left\nto preview it here.", fill="#888888", font=("Arial", 12), justify="center", tags="hint")
        self.lbl_zoom.config(text="100%")

    def choose_fill_color(self):
        if (color_code := colorchooser.askcolor(initialcolor=self.fill_color.get(), title="Choose Area/Border Color", parent=self.btn_fill))[1]:
            self.fill_color.set(color_code[1].upper()); self.swatch_fill.config(bg=self.fill_color.get()); self.refresh_preview()

    def choose_bg_color(self):
        if (color_code := colorchooser.askcolor(initialcolor=self.bg_color.get(), title="Choose Background Color", parent=self.btn_bg))[1]:
            self.bg_color.set(color_code[1].upper()); self.swatch_bg.config(bg=self.bg_color.get()); self.refresh_preview()

    def choose_preview_bg_color(self):
        if (color_code := colorchooser.askcolor(initialcolor=self.preview_bg_color.get(), title="Choose Canvas Transp Color", parent=self.btn_preview_bg))[1]:
            self.preview_bg_color.set(color_code[1].upper()); self.swatch_preview_bg.config(bg=self.preview_bg_color.get()); self.canvas.config(bg=self.preview_bg_color.get())

    def reset_colors(self):
        self.fill_color.set("#C2BA79"); self.bg_color.set("#00FFFF"); self.preview_bg_color.set("#9C9C9C")
        self.swatch_fill.config(bg=self.fill_color.get()); self.swatch_bg.config(bg=self.bg_color.get())
        self.swatch_preview_bg.config(bg=self.preview_bg_color.get()); self.canvas.config(bg=self.preview_bg_color.get()); self.refresh_preview()

    def reset_offset(self): self.offset_x_var.set("0"); self.offset_y_var.set("0")

    def reset_mask(self):
        if not self.current_filename: return
        if (data := self.imported_images.get(self.current_filename)) and data.get("custom_mask") is not None:
            data["custom_mask"] = None; self.refresh_preview(); self.save_state()

    def refresh_preview_safe(self, *args):
        if not getattr(self, 'ignore_offset_trace', False): self.refresh_preview()

    def on_offset_changed(self, *args):
        if getattr(self, 'ignore_offset_trace', False) or not self.current_filename: return
        try:
            ox = int(float(self.offset_x_var.get() or 0))
            oy = int(float(self.offset_y_var.get() or 0))
            if (current_data := self.imported_images.get(self.current_filename)) and (current_data["ox"] != ox or current_data["oy"] != oy):
                current_data["ox"], current_data["oy"] = ox, oy
                self.refresh_preview()
        except ValueError: pass 

    def sync_data_with_tree(self):
        self.imported_images = {fname: self.imported_images[fname] for item in self.tree.get_children() if (values := self.tree.item(item, "values")) and len(values) > 1 and (fname := values[1]) in self.imported_images}

    def on_delete_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell" or self.tree.identify_column(event.x) != "#1": return
        if item := self.tree.identify_row(event.y):
            idx = self.tree.index(item)
            self.delete_item_internal(item)
            if children := self.tree.get_children():
                next_item = children[min(idx, len(children) - 1)]
                self.tree.selection_set(next_item); self.tree.focus(next_item)
                self.tree._last_clicked_item = next_item
                self.on_tree_select(None)
            else: self.clear_preview_state()
            self.save_state()
            return "break"
                
    def import_assets(self):
        if not (files := filedialog.askopenfilenames(title="Import Images for Townscreen", filetypes=[("Images", "*.png;*.bmp;*.jpg")])): return
        was_empty = len(self.tree.get_children()) == 0
        changed = False
        for f_path in files:
            fname = os.path.basename(f_path)
            if fname not in self.imported_images:
                self.imported_images[fname] = {"path": f_path, "ox": 0, "oy": 0, "custom_mask": None}
                self.tree.insert("", "end", values=("❌", fname), tags=("file",)); changed = True
        if changed:
            if self.sort_state != "manual": self.apply_sort(reverse=(self.sort_state == "desc")); self.sync_data_with_tree()
            self.save_state()
            if was_empty:
                first_item = self.tree.get_children()[0]
                self.tree.selection_set(first_item); self.tree.focus(first_item)
                self.tree._last_clicked_item = first_item; self.on_tree_select(None); self.center_view()

    def clear_assets(self):
        if not messagebox.askyesno("Confirm", "Clear all imported townscreen assets?"): return
        self.imported_images.clear(); self.tree.delete(*self.tree.get_children()); self.clear_preview_state()
        self.sort_state = "manual"; self.tree.heading("name", text="Filename   ")
        self.manual_order_snapshot.clear(); self.history_mgr.clear(); self.save_state()

    def on_tree_select(self, event):
        if not (sel := self.tree.selection()): self.clear_preview_state(); return
        item = self.tree._last_clicked_item if getattr(self.tree, '_last_clicked_item', None) in sel else (self.tree.focus() if self.tree.focus() in sel else sel[-1])
        values = self.tree.item(item, "values")
        if values and len(values) > 1 and (fname := values[1]) in self.imported_images:
            data = self.imported_images[fname]
            self.current_filename, self.current_filepath = fname, data["path"]
            self.ignore_offset_trace = True
            self.offset_x_var.set(str(data.get("ox", 0))); self.offset_y_var.set(str(data.get("oy", 0)))
            self.ignore_offset_trace = False
            self.refresh_preview()

    def delete_item_internal(self, item):
        values = self.tree.item(item, "values")
        if not values or len(values) < 2: return
        if (fname := values[1]) in self.imported_images: del self.imported_images[fname]
        self.tree.delete(item)

    def on_delete_key(self, event):
        if not (sel := self.tree.selection()): return
        first_idx = self.tree.index(sel[0])
        for item in sel: self.delete_item_internal(item)
        if children := self.tree.get_children():
            next_item = children[min(first_idx, len(children) - 1)]
            self.tree.selection_set(next_item); self.tree.focus(next_item)
            self.tree._last_clicked_item = next_item; self.on_tree_select(None)
        else: self.clear_preview_state()
        self.save_state()

    def refresh_preview(self):
        if hasattr(self, '_refresh_job') and self._refresh_job:
            self.parent.after_cancel(self._refresh_job)
        self._refresh_job = self.parent.after(40, self._do_refresh_preview)

    def _do_refresh_preview(self):
        self._refresh_job = None
        if not self.current_filepath:
            self.draw_placeholder(); return
        try:
            self.canvas.delete("temp_draw")
            img = Image.open(self.current_filepath).convert("RGBA")
            mode = self.view_mode.get()
            force_transp = mode in ["area", "border"]
            try: ox = int(float(self.offset_x_var.get() or 0))
            except ValueError: ox = 0
            try: oy = int(float(self.offset_y_var.get() or 0))
            except ValueError: oy = 0
            
            if (self.remove_bg_var.get() or force_transp) and self.transp_color.get():
                img = apply_transparency(img, self.transp_color.get())
                
            img_shifted = get_shifted_image(img, ox, oy, force_transp, self.remove_bg_var.get(), self.bg_color.get())
            
            data = self.imported_images[self.current_filename]
            mask = data.get("custom_mask") if data.get("custom_mask") else img.getchannel('A')
            mask_shifted = get_shifted_image(mask, ox, oy, force_transp=True, remove_bg=True, bg_hex="#000000")
            
            if mode == "townscreen": display_img = img_shifted
            elif mode == "area": display_img = generate_area_image(mask_shifted, self.fill_color.get(), self.bg_color.get(), transparent_bg=self.remove_bg_var.get())
            elif mode == "border": display_img = generate_border_image(mask_shifted, self.fill_color.get(), self.bg_color.get(), transparent_bg=self.remove_bg_var.get())
            
            try: opacity = int(float(self.overlay_opacity_var.get() or 0))
            except ValueError: opacity = 0
            
            if mode in ["area", "border"] and opacity > 0:
                overlay_img = img_shifted.copy()
                alpha_chan = overlay_img.getchannel('A')
                alpha_chan = alpha_chan.point(lambda p: int(p * (opacity / 100.0)))
                overlay_img.putalpha(alpha_chan)
                display_img = Image.alpha_composite(display_img, overlay_img)

            z = self.zoom_level
            w, h = display_img.size
            sw, sh = int(w * z), int(h * z)
            scaled_img = display_img.resize((sw, sh), Image.Resampling.NEAREST)
            self.current_preview = ImageTk.PhotoImage(scaled_img)
            self.canvas.config(bg=self.preview_bg_color.get()); self.canvas.delete("all")
            ts_w, ts_h = int(800 * z), int(374 * z)
            self.canvas.create_rectangle(-ts_w/2, -ts_h/2, ts_w/2, ts_h/2, outline="#555555", dash=(4, 4), tags="bounds")
            self.canvas.create_image(0, 0, image=self.current_preview, anchor="center")
            
            if hasattr(self, 'cursor_item'): del self.cursor_item
            self.last_cursor_size = None
            self.generate_cursor_image()
            
        except Exception as e:
            logging.error(f"Townscreen : Error processing preview {self.current_filepath}. Details : {e}", exc_info=True)

    def export_assets(self):
        if not self.imported_images:
            messagebox.showinfo("Export", "No assets to export. Please import images first."); return
        if not (dest := filedialog.askdirectory(title="Select Destination Folder")): return

        popup = tk.Toplevel(self.parent); popup.title("Exporting Townscreen Assets...")
        popup_w, popup_h = 350, 120
        main_x = self.parent.winfo_rootx(); main_y = self.parent.winfo_rooty()
        main_w = self.parent.winfo_width(); main_h = self.parent.winfo_height()
        pos_x = main_x + (main_w - popup_w) // 2; pos_y = main_y + (main_h - popup_h) // 2
        popup.geometry(f"{popup_w}x{popup_h}+{pos_x}+{pos_y}")
        popup.transient(self.parent.winfo_toplevel()); popup.grab_set() 

        lbl_status = ttk.Label(popup, text="Starting export..."); lbl_status.pack(pady=(15, 5))
        progress = ttk.Progressbar(popup, orient="horizontal", length=300, mode="determinate"); progress.pack(pady=5)
        
        def process_item(item):
            fname, data = item
            base_name = os.path.splitext(fname)[0]
            fpath = data["path"]; ox, oy = data.get("ox", 0), data.get("oy", 0)
            
            base_img = Image.open(fpath).convert("RGBA")
            remove_bg, transp_hex = self.remove_bg_var.get(), self.transp_color.get()
            base_img_processed = apply_transparency(base_img, transp_hex) if remove_bg and transp_hex else base_img
            img_standard = get_shifted_image(base_img_processed, ox, oy, False, remove_bg, self.bg_color.get())
            
            export_base, c = base_name, 1
            while os.path.exists(os.path.join(dest, f"{export_base}.png")) or os.path.exists(os.path.join(dest, f"{export_base}-area.png")) or os.path.exists(os.path.join(dest, f"{export_base}-border.png")):
                export_base = f"{base_name}_{c}"; c += 1
            
            img_standard.save(os.path.join(dest, f"{export_base}.png"))
            
            mask = data["custom_mask"] if data.get("custom_mask") else (apply_transparency(base_img, transp_hex) if transp_hex else base_img).getchannel('A')
            mask_shifted = get_shifted_image(mask, ox, oy, True, True, "#000000")
            
            generate_area_image(mask_shifted, self.fill_color.get(), self.bg_color.get(), remove_bg).save(os.path.join(dest, f"{export_base}-area.png"))
            generate_border_image(mask_shifted, self.fill_color.get(), self.bg_color.get(), remove_bg).save(os.path.join(dest, f"{export_base}-border.png"))
            return export_base

        def worker():
            count, total = 0, len(self.imported_images)
            try:
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = {executor.submit(process_item, item): item for item in self.imported_images.items()}
                    for future in concurrent.futures.as_completed(futures):
                        name = future.result(); count += 1
                        self.parent.after(0, lambda current=count, tot=total, n=name: (
                            progress.config(value=(current/tot)*100),
                            lbl_status.config(text=f"Exported {current}/{tot}: {n}")
                        ))
                self.unsaved_mask_edits = 0
                self.parent.after(0, lambda: (popup.destroy(), messagebox.showinfo("Export Successful", f"Successfully exported {count} files\n(Including Area and Border variants for each).")))
            except Exception as e:
                logging.error(f"Townscreen Export failed: {e}", exc_info=True)
                self.parent.after(0, lambda: (popup.destroy(), messagebox.showerror("Export Failed", f"An error occurred during export:\n{e}")))

        threading.Thread(target=worker, daemon=True).start()