import os
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageTk, ImageOps, ImageFilter, ImageChops, ImageDraw

# -------------------------------------------------------------------------
# TAB TOWNSCREEN CLASS
# -------------------------------------------------------------------------
class TownscreenTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        
        # Dictionary to store imported images paths, offsets, and custom masks
        # Key = filename, Value = {"path": str, "ox": int, "oy": int, "custom_mask": PIL.Image}
        self.imported_images = {}
        
        # History for Undo / Redo
        self.history = []
        self.history_index = -1
        
        # Vital references
        self.current_preview = None
        self.current_filepath = None
        self.current_filename = None
        
        # Zoom & Panning State
        self.zoom_level = 1.0
        
        # State variables for view modes and customizable colors
        self.view_mode = tk.StringVar(value="townscreen")
        self.fill_color = tk.StringVar(value="#C2BA79")
        self.bg_color = tk.StringVar(value="#00FFFF")
        self.preview_bg_color = tk.StringVar(value="#9C9C9C") # Default RGB(156,156,156)
        self.default_canvas_bg = "#1a1a1a"
        
        # Background removal and Mask variables
        self.remove_bg_var = tk.BooleanVar(value=True)
        self.transp_color = tk.StringVar(value="#00FFFF")
        self.eyedropper_mode = False
        
        # Overlay and Mask Editor variables
        self.draw_mode_var = tk.StringVar(value="none")
        self.brush_size_var = tk.IntVar(value=10)
        self.overlay_opacity_var = tk.IntVar(value=0)
        
        self.build_ui()
        self.setup_global_bindings()
        self.save_state()

    def build_ui(self):
        self.parent.columnconfigure(0, weight=0, minsize=260)
        self.parent.columnconfigure(1, weight=1)
        self.parent.rowconfigure(0, weight=1)

        # =========================================================================
        # LEFT ZONE : ASSETS MANAGER (TREEVIEW)
        # =========================================================================
        left_panel = ttk.Frame(self.parent, relief="groove")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        
        btn_frame = ttk.Frame(left_panel)
        btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="Import", command=self.import_assets).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_frame, text="Export", command=self.export_assets).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_frame, text="Clear Assets", command=self.clear_assets).pack(side="left", fill="x", expand=True, padx=2)
        
        self.tree = ttk.Treeview(left_panel, columns=("del", "name"), show="headings", selectmode="extended")
        self.tree.heading("del", text="✖")
        self.tree.column("del", width=35, stretch=False, anchor="center")
        self.tree.heading("name", text="Filename")
        self.tree.column("name", anchor="w")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        
        scroll_y = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        scroll_y.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll_y.set)
        
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)
        self.tree.bind("<Delete>", self.on_delete_key)
        self.tree.bind("<BackSpace>", self.on_delete_key)
        self.tree.bind("<Control-Shift-Button-1>", self.on_ctrl_shift_click)
        
        h_frame = ttk.Frame(left_panel)
        h_frame.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Button(h_frame, text="↶ Undo", command=self.undo).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(h_frame, text="↷ Redo", command=self.redo).pack(side="left", expand=True, fill="x", padx=1)

        # =========================================================================
        # RIGHT ZONE : PREVIEW (800x374 CANVAS) & TOOLS
        # =========================================================================
        right_panel = ttk.Frame(self.parent, relief="groove")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        
        lbl_title = ttk.Label(right_panel, text="Townscreen Preview (800x374 pixels)", font=("Arial", 11, "bold"))
        lbl_title.pack(pady=(10, 5))
        
        # --- TOP CONTROLS: View Modes & Zoom ---
        top_ctrl_frame = ttk.Frame(right_panel)
        top_ctrl_frame.pack(fill="x", pady=2, padx=10)
        
        mode_frame = ttk.Frame(top_ctrl_frame)
        mode_frame.pack(side="left")
        ttk.Radiobutton(mode_frame, text="Townscreen", variable=self.view_mode, value="townscreen", command=self.refresh_preview).pack(side="left", padx=5)
        ttk.Radiobutton(mode_frame, text="Building Area", variable=self.view_mode, value="area", command=self.refresh_preview).pack(side="left", padx=5)
        ttk.Radiobutton(mode_frame, text="Building Border", variable=self.view_mode, value="border", command=self.refresh_preview).pack(side="left", padx=5)
        
        zoom_frame = ttk.Frame(top_ctrl_frame)
        zoom_frame.pack(side="right")
        ttk.Button(zoom_frame, text="↺", width=2, command=self.reset_view).pack(side="left", padx=5)
        ttk.Button(zoom_frame, text="-", width=2, command=self.zoom_out).pack(side="left")
        self.lbl_zoom = ttk.Label(zoom_frame, text="100%", width=5, anchor="center")
        self.lbl_zoom.pack(side="left", padx=2)
        ttk.Button(zoom_frame, text="+", width=2, command=self.zoom_in).pack(side="left")
        
        # --- MIDDLE: Strict Canvas ---
        canvas_frame = tk.Frame(right_panel, bd=2, relief="groove")
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Create a massive fixed scrollregion (-5000 to +5000) so (0,0) is always exactly in the absolute mathematical center
        self.canvas = tk.Canvas(canvas_frame, bg=self.preview_bg_color.get(), highlightthickness=0, scrollregion=(-5000, -5000, 5000, 5000))
        self.canvas.pack(fill="both", expand=True)
        
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        
        # Panning bindings
        self.canvas.bind("<ButtonPress-2>", self.start_pan)
        self.canvas.bind("<B2-Motion>", self.do_pan)
        
        # Zoom bindings
        self.canvas.bind("<Control-MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Control-Button-4>", self.on_mousewheel) # Linux up
        self.canvas.bind("<Control-Button-5>", self.on_mousewheel) # Linux down
        
        # --- BOTTOM CONTROLS: Tools (Clean Grid Layout) ---
        tools_frame = ttk.Frame(right_panel)
        tools_frame.pack(fill="x", pady=10, padx=10)
        tools_frame.columnconfigure(0, weight=1)
        tools_frame.columnconfigure(1, weight=1)
        tools_frame.columnconfigure(2, weight=1)
        
        # Column 1: Colors
        col1 = ttk.Frame(tools_frame)
        col1.grid(row=0, column=0, sticky="nsew", padx=5)
        
        color_frame = ttk.LabelFrame(col1, text="Rendering Colors")
        color_frame.pack(fill="x", pady=2)
        color_frame.columnconfigure(1, weight=1)
        
        self.swatch_fill = tk.Label(color_frame, bg=self.fill_color.get(), width=2, relief="solid", bd=1)
        self.swatch_fill.grid(row=0, column=0, padx=5, pady=3)
        self.btn_fill = ttk.Button(color_frame, text="Set Area/Border Color", command=self.choose_fill_color)
        self.btn_fill.grid(row=0, column=1, sticky="ew", padx=(0,5), pady=3)
        
        self.swatch_bg = tk.Label(color_frame, bg=self.bg_color.get(), width=2, relief="solid", bd=1)
        self.swatch_bg.grid(row=1, column=0, padx=5, pady=3)
        self.btn_bg = ttk.Button(color_frame, text="Set Background Color", command=self.choose_bg_color)
        self.btn_bg.grid(row=1, column=1, sticky="ew", padx=(0,5), pady=3)
        
        self.swatch_preview_bg = tk.Label(color_frame, bg=self.preview_bg_color.get(), width=2, relief="solid", bd=1)
        self.swatch_preview_bg.grid(row=2, column=0, padx=5, pady=3)
        self.btn_preview_bg = ttk.Button(color_frame, text="Set Canvas Transp. Color", command=self.choose_preview_bg_color)
        self.btn_preview_bg.grid(row=2, column=1, sticky="ew", padx=(0,5), pady=3)

        ttk.Button(color_frame, text="↺ Reset Colors", command=self.reset_colors).grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
        
        # Column 2: Transparency & Offset
        col2 = ttk.Frame(tools_frame)
        col2.grid(row=0, column=1, sticky="nsew", padx=5)
        
        transp_frame = ttk.LabelFrame(col2, text="Background Removal")
        transp_frame.pack(fill="x", pady=2)
        transp_frame.columnconfigure(1, weight=1)
        
        ttk.Checkbutton(transp_frame, text="Remove Color:", variable=self.remove_bg_var, command=self.refresh_preview).grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(transp_frame, textvariable=self.transp_color, width=9).grid(row=0, column=1, sticky="ew", padx=(0,5), pady=3)
        self.transp_color.trace_add("write", lambda *args: self.refresh_preview_safe())
        
        ttk.Button(transp_frame, text="🖌️ Eyedropper", command=self.activate_eyedropper).grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
        
        offset_frame = ttk.LabelFrame(col2, text="Offset (X / Y)")
        offset_frame.pack(fill="x", pady=2)
        offset_frame.columnconfigure(1, weight=1)
        offset_frame.columnconfigure(3, weight=1)
        
        self.offset_x_var = tk.IntVar(value=0)
        self.offset_y_var = tk.IntVar(value=0)
        self.offset_x_var.trace_add("write", self.on_offset_changed)
        self.offset_y_var.trace_add("write", self.on_offset_changed)
        
        ttk.Label(offset_frame, text="X:").grid(row=0, column=0, sticky="e", padx=(5,2), pady=3)
        ttk.Spinbox(offset_frame, from_=-2000, to=2000, textvariable=self.offset_x_var, width=5, command=self.on_offset_changed).grid(row=0, column=1, sticky="ew", padx=(0,5), pady=3)
        
        ttk.Label(offset_frame, text="Y:").grid(row=0, column=2, sticky="e", padx=(5,2), pady=3)
        ttk.Spinbox(offset_frame, from_=-2000, to=2000, textvariable=self.offset_y_var, width=5, command=self.on_offset_changed).grid(row=0, column=3, sticky="ew", padx=(0,5), pady=3)
        
        ttk.Button(offset_frame, text="Reset Offset", command=self.reset_offset).grid(row=1, column=0, columnspan=4, sticky="ew", padx=5, pady=3)

        # Column 3: Mask Editor & Overlay
        col3 = ttk.Frame(tools_frame)
        col3.grid(row=0, column=2, sticky="nsew", padx=5)
        
        mask_frame = ttk.LabelFrame(col3, text="Mask Editor (Area/Border)")
        mask_frame.pack(fill="x", pady=2)
        
        m_r1 = ttk.Frame(mask_frame)
        m_r1.pack(fill="x", pady=3, padx=5)
        ttk.Radiobutton(m_r1, text="🚫 None", variable=self.draw_mode_var, value="none").pack(side="left", padx=2)
        ttk.Radiobutton(m_r1, text="🖊️ Pen", variable=self.draw_mode_var, value="pen").pack(side="left", padx=2)
        ttk.Radiobutton(m_r1, text="🧽 Eraser", variable=self.draw_mode_var, value="eraser").pack(side="left", padx=2)
        
        m_r2 = ttk.Frame(mask_frame)
        m_r2.pack(fill="x", pady=3, padx=5)
        ttk.Label(m_r2, text="Size:").pack(side="left")
        ttk.Spinbox(m_r2, from_=1, to=100, textvariable=self.brush_size_var, width=4).pack(side="left", padx=5)
        ttk.Button(m_r2, text="Reset Mask", command=self.reset_mask).pack(side="right")
        
        overlay_frame = ttk.LabelFrame(col3, text="Overlay (Base Image Preview)")
        overlay_frame.pack(fill="x", pady=2)
        
        o_r1 = ttk.Frame(overlay_frame)
        o_r1.pack(fill="x", pady=5, padx=5)
        ttk.Label(o_r1, text="Opacity %:").pack(side="left")
        tk.Scale(o_r1, from_=0, to=100, orient="horizontal", variable=self.overlay_opacity_var, showvalue=0, command=lambda v: self.refresh_preview_safe()).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Entry(o_r1, textvariable=self.overlay_opacity_var, width=4).pack(side="right")
        self.overlay_opacity_var.trace_add("write", lambda *args: self.refresh_preview_safe())
        
        self.draw_placeholder()

    def setup_global_bindings(self):
        """Bind global zoom shortcuts to the main window."""
        top = self.parent.winfo_toplevel()
        top.bind("<Control-plus>", self.global_zoom_in)
        top.bind("<Control-equal>", self.global_zoom_in)
        top.bind("<Control-KP_Add>", self.global_zoom_in)
        top.bind("<Control-minus>", self.global_zoom_out)
        top.bind("<Control-KP_Subtract>", self.global_zoom_out)

    def is_tab_active(self):
        """Checks if the Townscreen tab is currently active in the notebook."""
        return self.app.notebook.index(self.app.notebook.select()) == 2

    # -------------------------------------------------------------------------
    # ZOOM & PANNING LOGIC
    # -------------------------------------------------------------------------
    def global_zoom_in(self, event):
        if self.is_tab_active() and self.current_filepath:
            self.zoom_in()

    def global_zoom_out(self, event):
        if self.is_tab_active() and self.current_filepath:
            self.zoom_out()

    def zoom_in(self, event=None):
        if not self.current_filepath: return
        self.zoom_level = min(5.0, self.zoom_level + 0.25)
        self.refresh_preview()

    def zoom_out(self, event=None):
        if not self.current_filepath: return
        self.zoom_level = max(0.25, self.zoom_level - 0.25)
        self.refresh_preview()

    def on_mousewheel(self, event):
        if not self.current_filepath: return
        # Handle Ctrl+Scroll for zoom
        if event.state & 0x0004:
            if event.delta > 0 or event.num == 4:
                self.zoom_in()
            elif event.delta < 0 or event.num == 5:
                self.zoom_out()
        return "break"

    def start_pan(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def do_pan(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_canvas_configure(self, event):
        """Dynamically tracks canvas resize to keep the placeholder perfectly centered."""
        if not self.current_filepath:
            self.center_view()

    def center_view(self):
        """Centers the scrollregion exactly in the middle so the image/placeholder is centered."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        
        # Fallback if window is not yet fully drawn
        if cw <= 1 or ch <= 1:
            cw = self.canvas.winfo_reqwidth()
            ch = self.canvas.winfo_reqheight()

        # The scrollregion is from -5000 to 5000 (total 10000)
        # Point 0 is exactly in the middle of the scrollregion
        # We calculate the exact fractions to place point 0 in the middle of the screen
        x_frac = (5000 - cw / 2) / 10000.0
        y_frac = (5000 - ch / 2) / 10000.0
        
        self.canvas.xview_moveto(x_frac)
        self.canvas.yview_moveto(y_frac)

    def reset_view(self):
        """Resets zoom to 100% and centers the canvas."""
        self.zoom_level = 1.0
        if self.current_filepath:
            self.refresh_preview()
        self.center_view()

    def get_image_coords(self, event_x, event_y):
        """Maps absolute canvas click coordinates to the original 1:1 image pixels."""
        if not self.current_filepath: return None, None, None, None
        try:
            # Absolute canvas coordinates inside the -5000 to +5000 universe
            cx = self.canvas.canvasx(event_x)
            cy = self.canvas.canvasy(event_y)

            z = self.zoom_level
            img = Image.open(self.current_filepath)
            w, h = img.size
            
            # The image is anchored at 0,0 center.
            # Thus, the top-left corner of the scaled image starts at:
            tl_x = 0 - (w * z) / 2
            tl_y = 0 - (h * z) / 2
            
            # Click offset from the top-left of the image on the canvas
            dx = cx - tl_x
            dy = cy - tl_y
            
            # Map back to 1:1 scale
            shifted_x = dx / z
            shifted_y = dy / z
            
            # Remove user offset to get the exact original image/mask coordinate
            ox = self.offset_x_var.get()
            oy = self.offset_y_var.get()
            img_x = int(shifted_x - ox)
            img_y = int(shifted_y - oy)
            
            return img_x, img_y, w, h
        except: return None, None, None, None

    # -------------------------------------------------------------------------
    # STATE MANAGEMENT (UNDO / REDO)
    # -------------------------------------------------------------------------
    def save_state(self):
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index+1]
            
        state = []
        for fname, data in self.imported_images.items():
            new_data = data.copy()
            if new_data.get("custom_mask") is not None:
                new_data["custom_mask"] = new_data["custom_mask"].copy()
            state.append((fname, new_data))
            
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
        self.imported_images.clear()
        self.tree.delete(*self.tree.get_children())
        
        for fname, data in state:
            new_data = data.copy()
            if new_data.get("custom_mask") is not None:
                new_data["custom_mask"] = new_data["custom_mask"].copy()
            self.imported_images[fname] = new_data
            self.tree.insert("", "end", values=("❌", fname), tags=("file",))
            
        children = self.tree.get_children()
        current_active_files = [data["path"] for fname, data in state]
        
        if self.current_filepath and self.current_filepath not in current_active_files:
            self.clear_preview_state()
        elif self.current_filepath:
            for item in children:
                if self.tree.item(item, "values")[1] == self.current_filename:
                    self.tree.selection_set(item)
                    self.tree.focus(item)
                    break
            
            data = self.imported_images[self.current_filename]
            self.ignore_offset_trace = True
            self.offset_x_var.set(data.get("ox", 0))
            self.offset_y_var.set(data.get("oy", 0))
            self.ignore_offset_trace = False
            self.refresh_preview()

    # -------------------------------------------------------------------------
    # UI LOGIC & COLOR PICKERS
    # -------------------------------------------------------------------------
    def clear_preview_state(self):
        self.current_filepath = None
        self.current_filename = None
        self.current_preview = None
        
        self.ignore_offset_trace = True
        self.offset_x_var.set(0)
        self.offset_y_var.set(0)
        self.ignore_offset_trace = False
        
        self.draw_placeholder()

    def on_ctrl_shift_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            focus_item = self.tree.focus()
            if focus_item:
                items = self.tree.get_children("")
                try:
                    idx1 = items.index(focus_item)
                    idx2 = items.index(item)
                    start = min(idx1, idx2)
                    end = max(idx1, idx2)
                    to_select = items[start:end+1]
                    self.tree.selection_add(to_select)
                except ValueError:
                    self.tree.selection_add(item)
            else:
                self.tree.selection_add(item)
        return "break"

    def draw_placeholder(self):
        self.canvas.delete("all")
        self.canvas.config(bg=self.preview_bg_color.get(), scrollregion=(-5000, -5000, 5000, 5000))
        self.canvas.create_text(
            0, 0, 
            text="Select an image from the list on the left\nto preview it here.", 
            fill="#888888", font=("Arial", 12), justify="center", tags="hint"
        )
        self.lbl_zoom.config(text="100%")

    def choose_fill_color(self):
        color_code = colorchooser.askcolor(initialcolor=self.fill_color.get(), title="Choose Area/Border Color", parent=self.btn_fill)
        if color_code[1]:
            self.fill_color.set(color_code[1].upper())
            self.swatch_fill.config(bg=self.fill_color.get())
            self.refresh_preview()

    def choose_bg_color(self):
        color_code = colorchooser.askcolor(initialcolor=self.bg_color.get(), title="Choose Background Color", parent=self.btn_bg)
        if color_code[1]:
            self.bg_color.set(color_code[1].upper())
            self.swatch_bg.config(bg=self.bg_color.get())
            self.refresh_preview()

    def choose_preview_bg_color(self):
        color_code = colorchooser.askcolor(initialcolor=self.preview_bg_color.get(), title="Choose Canvas Transp Color", parent=self.btn_preview_bg)
        if color_code[1]:
            self.preview_bg_color.set(color_code[1].upper())
            self.swatch_preview_bg.config(bg=self.preview_bg_color.get())
            self.canvas.config(bg=self.preview_bg_color.get())

    def reset_colors(self):
        self.fill_color.set("#C2BA79")
        self.bg_color.set("#00FFFF")
        self.preview_bg_color.set("#9C9C9C")
        self.swatch_fill.config(bg=self.fill_color.get())
        self.swatch_bg.config(bg=self.bg_color.get())
        self.swatch_preview_bg.config(bg=self.preview_bg_color.get())
        self.canvas.config(bg=self.preview_bg_color.get())
        self.refresh_preview()

    def reset_offset(self):
        self.offset_x_var.set(0)
        self.offset_y_var.set(0)

    def reset_mask(self):
        if not self.current_filename: return
        data = self.imported_images.get(self.current_filename)
        if data and data.get("custom_mask") is not None:
            data["custom_mask"] = None
            self.refresh_preview()
            self.save_state()

    def refresh_preview_safe(self):
        if not getattr(self, 'ignore_offset_trace', False):
            self.refresh_preview()

    def on_offset_changed(self, *args):
        if getattr(self, 'ignore_offset_trace', False): return
        if not self.current_filename: return
        
        try:
            ox = self.offset_x_var.get()
            oy = self.offset_y_var.get()
            
            current_data = self.imported_images.get(self.current_filename)
            if current_data:
                if current_data["ox"] != ox or current_data["oy"] != oy:
                    current_data["ox"] = ox
                    current_data["oy"] = oy
                    self.refresh_preview()
        except tk.TclError:
            pass 

    # -------------------------------------------------------------------------
    # CANVAS DRAWING (MASK EDITOR & EYEDROPPER)
    # -------------------------------------------------------------------------
    def activate_eyedropper(self):
        self.eyedropper_mode = True
        self.draw_mode_var.set("none")
        self.canvas.config(cursor="crosshair")

    def on_canvas_press(self, event):
        # 1. Eyedropper logic
        if self.eyedropper_mode and self.current_filepath:
            img_x, img_y, w, h = self.get_image_coords(event.x, event.y)
            if img_x is not None and 0 <= img_x < w and 0 <= img_y < h:
                try:
                    img = Image.open(self.current_filepath).convert("RGB")
                    r, g, b = img.getpixel((img_x, img_y))
                    hex_color = f"#{r:02x}{g:02x}{b:02x}".upper()
                    self.transp_color.set(hex_color)
                    self.remove_bg_var.set(True)
                except Exception as e:
                    logging.warning(f"Eyedropper failed: {e}")
            self.eyedropper_mode = False
            self.canvas.config(cursor="")
            self.refresh_preview()
            return

        # 2. Mask Editor logic
        mode = self.draw_mode_var.get()
        if mode in ["pen", "eraser"] and self.current_filepath:
            if self.view_mode.get() not in ["area", "border"]:
                messagebox.showwarning("Mask Editor", "The mask editor can only be used in 'Building Area' or 'Building Border' view modes.")
                self.draw_mode_var.set("none")
                return
                
            img_x, img_y, w, h = self.get_image_coords(event.x, event.y)
            if img_x is None: return
            
            data = self.imported_images[self.current_filename]
            
            if data.get("custom_mask") is None:
                base_img = Image.open(self.current_filepath).convert("RGBA")
                if self.remove_bg_var.get() and self.transp_color.get():
                    base_img = self.apply_transparency(base_img, self.transp_color.get())
                data["custom_mask"] = base_img.getchannel('A').copy()
                
            self.last_draw_x, self.last_draw_y = img_x, img_y
            self.draw_on_mask(img_x, img_y, mode, w, h)

    def on_canvas_drag(self, event):
        if self.eyedropper_mode: return
        mode = self.draw_mode_var.get()
        if mode in ["pen", "eraser"] and self.current_filepath and hasattr(self, 'last_draw_x'):
            if self.view_mode.get() not in ["area", "border"]: return
            
            img_x, img_y, w, h = self.get_image_coords(event.x, event.y)
            if img_x is None: return
            self.draw_on_mask(img_x, img_y, mode, w, h, self.last_draw_x, self.last_draw_y)
            self.last_draw_x, self.last_draw_y = img_x, img_y

    def on_canvas_release(self, event):
        if self.eyedropper_mode: return
        mode = self.draw_mode_var.get()
        if mode in ["pen", "eraser"] and hasattr(self, 'last_draw_x'):
            if self.view_mode.get() not in ["area", "border"]: return
            
            self.canvas.delete("temp_draw")
            self.refresh_preview()
            self.save_state()
            del self.last_draw_x

    def draw_on_mask(self, x, y, mode, w, h, last_x=None, last_y=None):
        data = self.imported_images[self.current_filename]
        mask = data["custom_mask"]
        draw = ImageDraw.Draw(mask)
        
        color = 255 if mode == "pen" else 0
        brush_size = self.brush_size_var.get()
        r = brush_size // 2

        if last_x is not None and last_y is not None:
            draw.line([(last_x, last_y), (x, y)], fill=color, width=brush_size, joint="curve")
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
        else:
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

        # Scale drawing for visual UI feedback natively anchored on 0,0
        z = self.zoom_level
        ox = self.offset_x_var.get()
        oy = self.offset_y_var.get()
        
        cx = 0 - (w * z)/2 + (x + ox) * z
        cy = 0 - (h * z)/2 + (y + oy) * z
        scaled_r = (brush_size * z) / 2
        
        tk_color = "#00FF00" if mode == "pen" else "#FF0000" 
        
        if last_x is not None and last_y is not None:
            last_cx = 0 - (w * z)/2 + (last_x + ox) * z
            last_cy = 0 - (h * z)/2 + (last_y + oy) * z
            self.canvas.create_line(last_cx, last_cy, cx, cy, fill=tk_color, width=brush_size * z, capstyle=tk.ROUND, tags="temp_draw")
        else:
            self.canvas.create_oval(cx - scaled_r, cy - scaled_r, cx + scaled_r, cy + scaled_r, fill=tk_color, outline="", tags="temp_draw")

    # -------------------------------------------------------------------------
    # TREEVIEW EVENTS & ASSET MANAGEMENT
    # -------------------------------------------------------------------------
    def import_assets(self):
        files = filedialog.askopenfilenames(
            title="Import Images for Townscreen",
            filetypes=[("Images", "*.png;*.bmp;*.jpg")]
        )
        if not files: return
            
        was_empty = len(self.tree.get_children()) == 0
        changed = False
        
        for f_path in files:
            fname = os.path.basename(f_path)
            if fname not in self.imported_images:
                self.imported_images[fname] = {"path": f_path, "ox": 0, "oy": 0, "custom_mask": None}
                self.tree.insert("", "end", values=("❌", fname), tags=("file",))
                changed = True
                
        if changed:
            self.save_state()
            if was_empty:
                first_item = self.tree.get_children()[0]
                self.tree.selection_set(first_item)
                self.tree.focus(first_item)
                self.on_tree_select(None)
                self.center_view()
            
        logging.info(f"{len(files)} images imported in Townscreen tab.")

    def clear_assets(self):
        if not messagebox.askyesno("Confirm", "Clear all imported townscreen assets?"): return
        self.imported_images.clear()
        self.tree.delete(*self.tree.get_children())
        self.clear_preview_state()
        self.save_state()

    def on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        item = sel[0]
        values = self.tree.item(item, "values")
        if values and len(values) > 1:
            fname = values[1]
            if fname in self.imported_images:
                data = self.imported_images[fname]
                self.current_filename = fname
                self.current_filepath = data["path"]
                
                self.ignore_offset_trace = True
                self.offset_x_var.set(data.get("ox", 0))
                self.offset_y_var.set(data.get("oy", 0))
                self.ignore_offset_trace = False
                
                self.refresh_preview()

    def delete_item_internal(self, item):
        values = self.tree.item(item, "values")
        if not values or len(values) < 2: return
        fname = values[1]
        if fname in self.imported_images:
            del self.imported_images[fname]
        self.tree.delete(item)

    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell": return
        column = self.tree.identify_column(event.x)
        
        if column == "#1":
            item = self.tree.identify_row(event.y)
            if item:
                idx = self.tree.index(item)
                self.delete_item_internal(item)
                
                children = self.tree.get_children()
                if children:
                    next_idx = min(idx, len(children) - 1)
                    next_item = children[next_idx]
                    self.tree.selection_set(next_item)
                    self.tree.focus(next_item)
                    self.on_tree_select(None)
                else:
                    self.clear_preview_state()
                    
                self.save_state()

    def on_delete_key(self, event):
        sel = self.tree.selection()
        if not sel: return
        
        first_idx = self.tree.index(sel[0])
        for item in sel:
            self.delete_item_internal(item)
            
        children = self.tree.get_children()
        if children:
            next_idx = min(first_idx, len(children) - 1)
            next_item = children[next_idx]
            self.tree.selection_set(next_item)
            self.tree.focus(next_item)
            self.on_tree_select(None)
        else:
            self.clear_preview_state()
            
        self.save_state()

    # -------------------------------------------------------------------------
    # IMAGE PROCESSING & EXPORT ALGORITHMS
    # -------------------------------------------------------------------------
    def apply_transparency(self, img, hex_color):
        try:
            h = hex_color.lstrip('#')
            target_color = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            return img 
            
        img = img.convert("RGBA")
        r, g, b, a = img.split()
        
        r_mask = r.point(lambda i: 255 if i == target_color[0] else 0)
        g_mask = g.point(lambda i: 255 if i == target_color[1] else 0)
        b_mask = b.point(lambda i: 255 if i == target_color[2] else 0)
        
        match_mask = ImageChops.darker(ImageChops.darker(r_mask, g_mask), b_mask)
        keep_mask = ImageOps.invert(match_mask)
        
        new_a = ImageChops.darker(a, keep_mask)
        img.putalpha(new_a)
        return img

    def get_shifted_image(self, img, ox, oy, force_transp):
        if ox == 0 and oy == 0:
            return img
            
        if self.remove_bg_var.get() or force_transp:
            if img.mode == "L": pad_color = 0
            else: pad_color = (0, 0, 0, 0)
        else:
            if img.mode == "L": pad_color = 0
            else:
                try:
                    h = self.bg_color.get().lstrip('#')
                    pad_color = tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (255,)
                except ValueError:
                    pad_color = (0, 0, 0, 0)
                
        shifted = Image.new(img.mode, img.size, pad_color)
        
        if img.mode == "RGBA":
            temp = Image.new("RGBA", img.size, (0,0,0,0))
            temp.paste(img, (ox, oy))
            shifted = Image.alpha_composite(shifted, temp)
        else:
            shifted.paste(img, (ox, oy))
            
        return shifted

    def generate_area_image(self, mask, fill_hex, bg_hex, transparent_bg=False):
        fill_color = tuple(int(fill_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,)
        if transparent_bg:
            bg_color = (0, 0, 0, 0)
        else:
            bg_color = tuple(int(bg_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,)
            
        fg_img = Image.new("RGBA", mask.size, fill_color)
        bg_img = Image.new("RGBA", mask.size, bg_color)
        
        bin_mask = mask.point(lambda p: 255 if p > 0 else 0)
        return Image.composite(fg_img, bg_img, bin_mask)

    def generate_border_image(self, mask, fill_hex, bg_hex, transparent_bg=False):
        fill_color = tuple(int(fill_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,)
        if transparent_bg:
            bg_color = (0, 0, 0, 0)
        else:
            bg_color = tuple(int(bg_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (255,)
            
        fg_img = Image.new("RGBA", mask.size, fill_color)
        bg_img = Image.new("RGBA", mask.size, bg_color)
        
        bin_mask = mask.point(lambda p: 255 if p > 0 else 0)
        dilated_mask = bin_mask.filter(ImageFilter.MaxFilter(3))
        border_mask = ImageChops.subtract(dilated_mask, bin_mask)
        
        return Image.composite(fg_img, bg_img, border_mask)

    def refresh_preview(self):
        if not self.current_filepath:
            self.draw_placeholder()
            return
            
        try:
            self.canvas.delete("temp_draw")
            img = Image.open(self.current_filepath).convert("RGBA")
            mode = self.view_mode.get()
            force_transp = mode in ["area", "border"]
            
            try:
                ox = self.offset_x_var.get()
                oy = self.offset_y_var.get()
            except tk.TclError:
                ox, oy = 0, 0
                
            if (self.remove_bg_var.get() or force_transp) and self.transp_color.get():
                img = self.apply_transparency(img, self.transp_color.get())
                
            img_shifted = self.get_shifted_image(img, ox, oy, force_transp)
            
            data = self.imported_images[self.current_filename]
            custom_mask = data.get("custom_mask")
            if custom_mask:
                mask = custom_mask
            else:
                mask = img.getchannel('A')
                
            mask_shifted = self.get_shifted_image(mask, ox, oy, force_transp=True)
            
            if mode == "townscreen":
                display_img = img_shifted
            elif mode == "area":
                display_img = self.generate_area_image(mask_shifted, self.fill_color.get(), self.bg_color.get(), transparent_bg=self.remove_bg_var.get())
            elif mode == "border":
                display_img = self.generate_border_image(mask_shifted, self.fill_color.get(), self.bg_color.get(), transparent_bg=self.remove_bg_var.get())
            
            try:
                opacity = self.overlay_opacity_var.get()
            except tk.TclError:
                opacity = 0
                
            if mode in ["area", "border"] and opacity > 0:
                overlay_img = img_shifted.copy()
                alpha_chan = overlay_img.getchannel('A')
                alpha_chan = alpha_chan.point(lambda p: int(p * (opacity / 100.0)))
                overlay_img.putalpha(alpha_chan)
                display_img = Image.alpha_composite(display_img, overlay_img)

            # Zoom Calculation & Canvas rendering
            z = self.zoom_level
            self.lbl_zoom.config(text=f"{int(z * 100)}%")
            w, h = display_img.size
            sw, sh = int(w * z), int(h * z)
            
            scaled_img = display_img.resize((sw, sh), Image.Resampling.NEAREST)
            self.current_preview = ImageTk.PhotoImage(scaled_img)
            
            self.canvas.config(bg=self.preview_bg_color.get())
            self.canvas.delete("all")
            
            # Townscreen Boundaries (800x374 dashed line visual hint)
            ts_w = int(800 * z)
            ts_h = int(374 * z)
            self.canvas.create_rectangle(-ts_w/2, -ts_h/2, ts_w/2, ts_h/2, outline="#555555", dash=(4, 4), tags="bounds")
            
            self.canvas.create_image(0, 0, image=self.current_preview, anchor="center")
            
        except Exception as e:
            logging.error(f"Townscreen : Error processing preview {self.current_filepath}. Details : {e}", exc_info=True)

    def export_assets(self):
        if not self.imported_images:
            messagebox.showinfo("Export", "No assets to export. Please import images first.")
            return
            
        dest = filedialog.askdirectory(title="Select Destination Folder")
        if not dest:
            return
            
        count = 0
        try:
            for fname, data in self.imported_images.items():
                base_name = os.path.splitext(fname)[0]
                fpath = data["path"]
                ox = data.get("ox", 0)
                oy = data.get("oy", 0)
                custom_mask = data.get("custom_mask")
                
                base_img = Image.open(fpath).convert("RGBA")
                remove_bg = self.remove_bg_var.get()
                transp_hex = self.transp_color.get()
                
                # 1. Save Standard Version
                if remove_bg and transp_hex:
                    base_img_processed = self.apply_transparency(base_img, transp_hex)
                else:
                    base_img_processed = base_img
                    
                img_standard = self.get_shifted_image(base_img_processed, ox, oy, force_transp=False)
                img_standard.save(os.path.join(dest, f"{base_name}.png"))
                
                # Setup Mask for Area/Border
                if custom_mask:
                    mask = custom_mask
                else:
                    temp_img = base_img
                    if transp_hex:
                        temp_img = self.apply_transparency(temp_img, transp_hex)
                    mask = temp_img.getchannel('A')
                    
                mask_shifted = self.get_shifted_image(mask, ox, oy, force_transp=True)
                
                # 2. Save Building Area version
                area_img = self.generate_area_image(mask_shifted, self.fill_color.get(), self.bg_color.get(), transparent_bg=remove_bg)
                area_img.save(os.path.join(dest, f"{base_name}-area.png"))
                
                # 3. Save Building Border version
                border_img = self.generate_border_image(mask_shifted, self.fill_color.get(), self.bg_color.get(), transparent_bg=remove_bg)
                border_img.save(os.path.join(dest, f"{base_name}-border.png"))
                
                count += 1
                
            messagebox.showinfo("Export Successful", f"Successfully exported {count} files\n(Including Area and Border variants for each).")
            
        except Exception as e:
            logging.error(f"Townscreen Export failed: {e}", exc_info=True)
            messagebox.showerror("Export Failed", f"An error occurred during export:\n{e}")