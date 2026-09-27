import tkinter as tk
from tkinter import ttk
import colorsys

class Tooltip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.hide)
        self.widget.bind("<ButtonPress>", self.hide)

    def schedule(self, event=None):
        self.hide()
        self.id = self.widget.after(self.delay, self.show)

    def hide(self, event=None):
        if self.id: 
            self.widget.after_cancel(self.id)
            self.id = None
        if self.tip_window: 
            self.tip_window.destroy()
            self.tip_window = None

    def show(self):
        if not self.text: return
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            label = tk.Label(tw, text=self.text, justify='left', bg="#ffffe0", relief='solid', borderwidth=1, font=("tahoma", "8"))
            label.pack(ipadx=1)
        except: pass

class ProxyEntry:
    def __init__(self, parent_dict): 
        self.parent = parent_dict
    def get(self): 
        return self.parent.get("key_name", "")

class DummyEntry:
    def __init__(self, val=""): 
        self.val = val
    def get_real_value(self): 
        return self.val
    def set_value(self, val): 
        self.val = val

class SmartEntry(ttk.Entry):
    def __init__(self, parent, placeholder, is_numeric=False, width=20, *args, **kwargs):
        super().__init__(parent, width=width, *args, **kwargs)
        self.placeholder = placeholder
        self.is_numeric = is_numeric
        self.placeholder_color = 'grey'
        self.text_color = 'black'
        self.showing_placeholder = False
        if self.is_numeric:
            self.configure(validate='key', validatecommand=(self.register(self.validate_number), '%P'))
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self._show_placeholder()
        
    def validate_number(self, new_val): 
        if new_val == "" or new_val == self.placeholder or new_val == "-": return True
        return new_val.lstrip('-').isdigit()
    
    def _on_focus_in(self, e):
        if str(self.cget("state")) == "disabled": return
        if self.showing_placeholder:
            st = str(self.cget("state"))
            if st == "disabled": self.configure(state="normal")
            self.delete(0, tk.END)
            self.configure(foreground=self.text_color)
            self.showing_placeholder = False
            if st == "disabled": self.configure(state="disabled")
            
    def _on_focus_out(self, e):
        if not self.get(): self._show_placeholder()
        
    def _show_placeholder(self):
        st = str(self.cget("state"))
        if st == "disabled": self.configure(state="normal")
        self.delete(0, tk.END)
        self.insert(0, self.placeholder)
        self.configure(foreground=self.placeholder_color)
        self.showing_placeholder = True
        if st == "disabled": self.configure(state="disabled")
        
    def set_value(self, text):
        st = str(self.cget("state"))
        if st == "disabled": self.configure(state="normal")
        self.delete(0, tk.END)
        if text: 
            self.insert(0, text)
            self.configure(foreground=self.text_color)
            self.showing_placeholder = False
        else: 
            self.insert(0, self.placeholder)
            self.configure(foreground=self.placeholder_color)
            self.showing_placeholder = True
        if st == "disabled": self.configure(state="disabled")
        
    def get_real_value(self):
        return "" if self.showing_placeholder else self.get()

class SmartTkEntry(tk.Entry):
    def __init__(self, parent, placeholder, is_numeric=False, width=20, *args, **kwargs):
        super().__init__(parent, width=width, bg="#ffffff", fg="#000000", disabledbackground="#e6e6e6", disabledforeground="#888888", *args, **kwargs)
        self.placeholder = placeholder
        self.is_numeric = is_numeric
        self.placeholder_color = '#777777'
        self.text_color = '#000000'
        self.showing_placeholder = False
        if self.is_numeric:
            self.configure(validate='key', validatecommand=(self.register(self.validate_number), '%P'))
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self._show_placeholder()
        
    def validate_number(self, new_val): 
        if new_val == "" or new_val == self.placeholder or new_val == "-": return True
        return new_val.lstrip('-').isdigit()
    
    def _on_focus_in(self, e):
        if str(self.cget("state")) == "disabled": return
        if self.showing_placeholder:
            st = str(self.cget("state"))
            if st == "disabled": self.configure(state="normal")
            self.delete(0, tk.END)
            self.configure(foreground=self.text_color)
            self.showing_placeholder = False
            if st == "disabled": self.configure(state="disabled")
            
    def _on_focus_out(self, e):
        if not self.get(): self._show_placeholder()
        
    def _show_placeholder(self):
        st = str(self.cget("state"))
        if st == "disabled": self.configure(state="normal")
        self.delete(0, tk.END)
        self.insert(0, self.placeholder)
        self.configure(foreground=self.placeholder_color)
        self.showing_placeholder = True
        if st == "disabled": self.configure(state="disabled")
        
    def set_value(self, text):
        st = str(self.cget("state"))
        if st == "disabled": self.configure(state="normal")
        self.delete(0, tk.END)
        if text: 
            self.insert(0, text)
            self.configure(foreground=self.text_color)
            self.showing_placeholder = False
        else: 
            self.insert(0, self.placeholder)
            self.configure(foreground=self.placeholder_color)
            self.showing_placeholder = True
        if st == "disabled": self.configure(state="disabled")
        
    def get_real_value(self):
        return "" if self.showing_placeholder else self.get()

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

class AdvancedTreeview(ttk.Treeview):
    """
    Arbre unifié gérant le Drag & Drop fluide avec gestion stricte des sélections multiples via Shift et Ctrl.
    """
    def __init__(self, master, allow_groups=False, **kwargs):
        super().__init__(master, **kwargs)
        self.allow_groups = allow_groups
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_motion)
        self.bind("<ButtonRelease-1>", self.on_release)
        
        self._drag_start_y = 0
        self._drag_active = False
        self._drag_items = []
        self._pending_selection = None
        self._last_clicked_item = None

    def on_press(self, event):
        item = self.identify_row(event.y)
        if not item:
            self._drag_items = []
            return
            
        region = self.identify_region(event.x, event.y)
        if region == "cell":
            column = self.identify_column(event.x)
            if column == "#1":
                self._drag_items = []
                return
                
        self._last_clicked_item = item

        is_shift = (event.state & 0x0001) != 0
        is_ctrl = (event.state & 0x0004) != 0

        if is_shift:
            anchor_item = self.focus() or (self.selection()[0] if self.selection() else None)
            if anchor_item:
                def get_all_items(parent=""):
                    res = []
                    for child in self.get_children(parent):
                        res.append(child)
                        res.extend(get_all_items(child))
                    return res
                all_items = get_all_items()
                try:
                    idx1 = all_items.index(anchor_item)
                    idx2 = all_items.index(item)
                    start = min(idx1, idx2)
                    end = max(idx1, idx2)
                    to_select = all_items[start:end+1]
                    
                    if is_ctrl:
                        current_sel = list(self.selection())
                        for i in to_select:
                            if i not in current_sel:
                                current_sel.append(i)
                        self.selection_set(current_sel)
                    else:
                        self.selection_set(to_select)
                except ValueError:
                    if is_ctrl: self.selection_add(item)
                    else: self.selection_set(item)
            else:
                if is_ctrl: self.selection_add(item)
                else: self.selection_set(item)
                
            self.focus(item)
            self._drag_items = []
            self.event_generate("<<TreeviewSelect>>")
            return "break"
            
        if is_ctrl:
            self._drag_items = []
            return

        self._drag_start_y = event.y
        self._drag_active = False
        
        sel = self.selection()
        if item in sel:
            self._drag_items = [i for i in sel if "file" in self.item(i, "tags")]
            def get_all_items(parent=""):
                res = []
                for child in self.get_children(parent):
                    res.append(child)
                    res.extend(get_all_items(child))
                return res
            all_items = get_all_items()
            self._drag_items.sort(key=lambda x: all_items.index(x) if x in all_items else 0)
            
            self._pending_selection = item
            return "break"
        else:
            if "file" in self.item(item, "tags"):
                self._drag_items = [item]
            else:
                self._drag_items = []
            self._pending_selection = None

    def on_motion(self, event):
        if not getattr(self, '_drag_items', None): 
            return "break"
        
        if not self._drag_active:
            if abs(event.y - self._drag_start_y) > 5:
                self._drag_active = True
                self.configure(cursor="hand2")
            else:
                return "break"
                
        self.detach(*self._drag_items)
        
        hovered = self.identify_row(event.y)
        target_parent = ""
        target_idx = "end"
        
        if hovered:
            tags = self.item(hovered, "tags")
            if "group" in tags and self.allow_groups:
                target_parent = hovered
                target_idx = "end"
            else:
                target_parent = self.parent(hovered)
                bbox = self.bbox(hovered)
                if bbox:
                    if event.y < bbox[1] + (bbox[3] // 2):
                        target_idx = self.index(hovered)
                    else:
                        target_idx = self.index(hovered) + 1
                        
        for i, item in enumerate(self._drag_items):
            idx = target_idx + i if isinstance(target_idx, int) else "end"
            self.move(item, target_parent, idx)
            
        self.selection_set(self._drag_items)
        return "break"

    def on_release(self, event):
        if getattr(self, '_drag_active', False):
            self.configure(cursor="")
            self._drag_active = False
            self.event_generate("<<TreeOrderChanged>>")
            self._drag_items = []
            self._pending_selection = None
            return "break"
            
        self._drag_items = []
        
        if getattr(self, '_pending_selection', None):
            self.selection_set(self._pending_selection)
            self._pending_selection = None
            self.event_generate("<<TreeviewSelect>>")
            return "break"

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


# =========================================================================
# MIXINS RÉUTILISABLES (Pour Sprite Editor & Townscreen)
# =========================================================================

class NotificationMixin:
    def show_notification(self, message, duration=5000):
        """Affiche un message temporaire dans self.lbl_notification s'il existe."""
        if not hasattr(self, 'lbl_notification') or not hasattr(self, 'parent'): 
            return
        self.lbl_notification.config(text=message)
        if getattr(self, 'notification_job', None):
            self.parent.after_cancel(self.notification_job)
        self.notification_job = self.parent.after(duration, lambda: self.lbl_notification.config(text=""))


class CanvasViewerMixin:
    """Centralise la gestion du zoom, pan, raccourcis et centrage du Canvas."""
    def setup_canvas_bindings(self):
        if not hasattr(self, 'canvas'): return
        self.canvas.bind("<ButtonPress-2>", self.start_pan)
        self.canvas.bind("<B2-Motion>", self.do_pan)
        self.canvas.bind("<Control-MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Control-Button-4>", self.on_mousewheel)
        self.canvas.bind("<Control-Button-5>", self.on_mousewheel)
        
    def bind_global_zoom(self, top_window):
        """À appeler dans l'initialisation pour lier les raccourcis clavier au top-niveau."""
        top_window.bind("<Control-plus>", self.global_zoom_in, add="+")
        top_window.bind("<Control-equal>", self.global_zoom_in, add="+")
        top_window.bind("<Control-KP_Add>", self.global_zoom_in, add="+")
        top_window.bind("<Control-minus>", self.global_zoom_out, add="+")
        top_window.bind("<Control-KP_Subtract>", self.global_zoom_out, add="+")

    def global_zoom_in(self, event=None):
        if self.is_tab_active() and self.can_zoom(): self.zoom_in()
        
    def global_zoom_out(self, event=None):
        if self.is_tab_active() and self.can_zoom(): self.zoom_out()
        
    def zoom_in(self, event=None):
        if not self.can_zoom(): return
        if hasattr(self, 'zoom_auto_var'): self.zoom_auto_var.set(False)
        self.zoom_level = min(5.0, getattr(self, 'zoom_level', 1.0) + 0.25)
        if hasattr(self, 'lbl_zoom'): self.lbl_zoom.config(text=f"{int(self.zoom_level * 100)}%")
        self.on_zoom_changed()
        
    def zoom_out(self, event=None):
        if not self.can_zoom(): return
        if hasattr(self, 'zoom_auto_var'): self.zoom_auto_var.set(False)
        self.zoom_level = max(0.25, getattr(self, 'zoom_level', 1.0) - 0.25)
        if hasattr(self, 'lbl_zoom'): self.lbl_zoom.config(text=f"{int(self.zoom_level * 100)}%")
        self.on_zoom_changed()
        
    def reset_view(self, event=None):
        self.zoom_level = 1.0
        if hasattr(self, 'lbl_zoom'): self.lbl_zoom.config(text=f"{int(self.zoom_level * 100)}%")
        if hasattr(self, 'zoom_auto_var'): self.zoom_auto_var.set(False)
        self.center_view()
        self.on_zoom_changed()
        
    def on_mousewheel(self, event):
        if not self.can_zoom(): return
        if event.state & 0x0004: # Vérifie si Control est enfoncé
            if getattr(event, 'delta', 0) > 0 or getattr(event, 'num', 0) == 4: self.zoom_in()
            elif getattr(event, 'delta', 0) < 0 or getattr(event, 'num', 0) == 5: self.zoom_out()
        return "break"
        
    def start_pan(self, event): 
        if hasattr(self, 'canvas'): self.canvas.scan_mark(event.x, event.y)
        
    def do_pan(self, event): 
        if hasattr(self, 'canvas'): self.canvas.scan_dragto(event.x, event.y, gain=1)
        
    def center_view(self):
        if not hasattr(self, 'canvas'): return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1 or ch <= 1: cw, ch = self.canvas.winfo_reqwidth(), self.canvas.winfo_reqheight()
        self.canvas.xview_moveto((5000 - cw / 2) / 10000.0)
        self.canvas.yview_moveto((5000 - ch / 2) / 10000.0)

    # =========================================================================
    # Méthodes à implémenter par les enfants pour lier la logique
    # =========================================================================
    def is_tab_active(self): return True
    def can_zoom(self): return True
    def on_zoom_changed(self): pass