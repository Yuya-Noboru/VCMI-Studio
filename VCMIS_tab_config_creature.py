import os
import json
import copy
import logging
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageEnhance, ImageOps

# -------------------------------------------------------------------------
# IMPORTS AUDIO
# -------------------------------------------------------------------------
AUDIO_AVAILABLE = False
try:
    import pygame
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
    pygame.mixer.init()
    AUDIO_AVAILABLE = True
except ImportError: pass

# -------------------------------------------------------------------------
# HELPER CLASSES & FORMATTERS
# -------------------------------------------------------------------------
def to_camel_case(text):
    """Formate un texte en camelCase tout en préservant le namespace VCMI (les ':')
       Empêche strictement les majuscules consécutives."""
    if not text: return text
    parts = text.split(':')
    formatted_parts = []
    for part in parts:
        if not any(c in part for c in [' ', '_', '-']):
            if part:
                part = part[0].lower() + part[1:]
                res = ""
                prev_upper = False
                for char in part:
                    if char.isupper():
                        if prev_upper: res += char.lower()
                        else: res += char; prev_upper = True
                    else: res += char; prev_upper = False
                formatted_parts.append(res)
            else: formatted_parts.append("")
            continue
        
        s = part.replace('_', ' ').replace('-', ' ')
        words = s.split()
        if not words: formatted_parts.append("")
        else:
            first_word = words[0].lower()
            camel = first_word + ''.join(w[0].upper() + w[1:].lower() for w in words[1:] if w)
            formatted_parts.append(camel)
            
    return ':'.join(formatted_parts)

def is_placeholder_hint(val_str):
    """Détecte si la valeur est un hint de la library (ex: 'string (Spell ID)', 'enum (...)', 'integer [0..10]', 'integer')"""
    v = str(val_str).lower().strip()
    keywords = ["string", "integer", "number", "enum", "array", "object", "any", "boolean"]
    has_keyword = any(k in v for k in keywords)
    has_brackets = ("(" in v and ")" in v) or ("[" in v and "]" in v)
    is_exact_keyword = v in keywords
    return (has_keyword and has_brackets) or is_exact_keyword

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
        if self.id: self.widget.after_cancel(self.id); self.id = None
        if self.tip_window: self.tip_window.destroy(); self.tip_window = None
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
    def __init__(self, parent_dict): self.parent = parent_dict
    def get(self): return self.parent.get("key_name", "")

# --- CHAMP MODERNE (ttk) ---
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

# --- CHAMP SPECIFIQUE COULEURS VERROUILLEES (tk) ---
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

class DummyEntry:
    def __init__(self, val=""): self.val = val
    def get_real_value(self): return self.val
    def set_value(self, val): self.val = val

# -------------------------------------------------------------------------
# TAB CONFIG CLASS
# -------------------------------------------------------------------------
class ConfigTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.image_refs = {}
        self.lbl_mov_type = None
        self.current_sound = None
        self.default_ability_img = None
        
        self.adv_map_manual_override = False
        self.special_frame = None 
        
        if not hasattr(self.app, 'dynamic_abilities'):
            self.app.dynamic_abilities = []
            
        self.bonus_list = []
        self.bonus_hints = {}
        self.identifiers_lib = {}
        
        self.load_bonus_library()
        self.load_identifiers_library()
        
        self.build_ui()

    def prompt_reset(self):
        """Ouvre une popup près de la souris pour confirmer la réinitialisation totale."""
        x = self.parent.winfo_pointerx() + 15
        y = self.parent.winfo_pointery() + 15
        
        top = tk.Toplevel(self.parent)
        top.title("Reset")
        top.geometry(f"+{x}+{y}")
        top.transient(self.parent.winfo_toplevel())
        top.grab_set()
        
        lbl = ttk.Label(top, text="⚠️ Are you sure you want to clear all fields?", font=("Arial", 10, "bold"))
        lbl.pack(padx=20, pady=15)
        
        btn_f = ttk.Frame(top)
        btn_f.pack(pady=(0, 15))
        
        def do_reset():
            self.execute_reset()
            top.destroy()
            
        ttk.Button(btn_f, text="Confirm", command=do_reset).pack(side="left", padx=10)
        ttk.Button(btn_f, text="Cancel", command=top.destroy).pack(side="left", padx=10)

    def execute_reset(self):
        """Efface tout et réinitialise les placeholders par défaut."""
        # 1. Reset Text Entries
        for key, entry in self.app.entries.items():
            if hasattr(entry, 'set_value'):
                entry.set_value("")
                
        # 2. Reset Booleans / Variables
        if "doubleWide" in self.app.vars: self.app.vars["doubleWide"].set(False)
        if "special" in self.app.vars: self.app.vars["special"].set(False)
        if "movement" in self.app.vars: self.app.vars["movement"].set("Ground")
        if "is_upgraded" in self.app.vars: 
            self.app.vars["is_upgraded"].set(False)
            self.btn_upgrade.config(text="unupgraded")
            
        self.update_movement_icon()
        
        # 3. Reset Adv Map manual override
        self.adv_map_manual_override = False
        self.app.entries["adv_min"].config(state="disabled")
        self.app.entries["adv_max"].config(state="disabled")
        self.btn_edit_adv.config(state="normal")
        self.app.entries["adv_min"].set_value("")
        self.app.entries["adv_max"].set_value("")
        
        # 4. Audio paths
        for k in ["snd_attack", "snd_defend", "snd_killed", "snd_shoot", "snd_move", "snd_wince", "snd_startMoving", "snd_endMoving"]:
            p_key = k + "_path"
            if p_key in self.app.vars:
                self.app.vars[p_key].set("")
        
        # 5. Clear dynamic abilities
        self.app.dynamic_abilities.clear()
        self.refresh_active_abilities()
        
        # 6. Images reset
        self._set_portrait_image("iconLarge", os.path.join(self.app.res_dir, "prtLarge.png"), "prtLarge.png")
        self._set_portrait_image("iconSmall", os.path.join(self.app.res_dir, "prtSmall.png"), "prtSmall.png")

    def load_bonus_library(self):
        try:
            lib_path = os.path.join(self.app.current_dir, "library-bonusSystem.json")
            if not os.path.exists(lib_path): return
            with open(lib_path, "r", encoding="utf-8") as f:
                lib_data = json.load(f)
            
            categories_container = lib_data.get("BonusTypes_Dictionary", lib_data)
            target_categories = ["creature_combat_abilities", "creature_special_abilities", "creature_spellcasting_abilities", "creature_spell_immunities"]
            
            def add_bonuses_from_dict(bonuses):
                if isinstance(bonuses, dict):
                    for b_type, b_data in bonuses.items():
                        self.bonus_list.append(b_type)
                        if isinstance(b_data, dict):
                            payload = b_data.copy()
                            if "type" not in payload: payload["type"] = b_type
                            self.bonus_hints[b_type] = payload
                        elif isinstance(b_data, str):
                            self.bonus_hints[b_type] = {"type": b_type, "val": "", "subtype": "", "description": str(b_data)}

            for cat, bonuses in categories_container.items():
                if cat.lower().replace(" ", "_") in target_categories:
                    add_bonuses_from_dict(bonuses)
            
            if not self.bonus_list:
                for cat, bonuses in categories_container.items():
                    if "creature" in cat.lower().replace(" ", "_") and cat not in ["Base_Format", "Enums", "BonusFormat_Complex_Examples"]:
                        add_bonuses_from_dict(bonuses)

            self.bonus_list = sorted(list(set(self.bonus_list)))
                
        except Exception as e:
            logging.error(f"Error loading bonus library: {e}", exc_info=True)

    def load_identifiers_library(self):
        """Charge le nouveau dictionnaire d'identifiants (Spells, Creatures, etc.)"""
        try:
            lib_path = os.path.join(self.app.current_dir, "library-identifiers.json")
            if not os.path.exists(lib_path): return
            with open(lib_path, "r", encoding="utf-8") as f:
                self.identifiers_lib = json.load(f)
        except Exception as e:
            logging.error(f"Error loading identifiers library: {e}", exc_info=True)

    def create_smart_field(self, parent, label, key, placeholder, row, col=0, width=20, is_numeric=False, icon_key=None, padding=2, tooltip=None):
        if icon_key and icon_key in self.app.ui_icons:
            lbl = ttk.Label(parent, text=f" {label}", image=self.app.ui_icons[icon_key], compound="left")
        else:
            lbl = ttk.Label(parent, text=label)
        
        lbl.grid(row=row, column=col, sticky='w', padx=5, pady=padding)
        entry = SmartEntry(parent, placeholder, is_numeric=is_numeric, width=width)
        entry.grid(row=row, column=col+1, sticky='w', padx=5, pady=padding)
        
        self.app.entries[key] = entry
        
        if tooltip: Tooltip(lbl, tooltip); Tooltip(entry, tooltip)
        return entry

    def enforce_camel_case_on_widget(self, event):
        widget = event.widget
        val = widget.get_real_value()
        if val:
            new_val = to_camel_case(val)
            if new_val != val: widget.set_value(new_val)

    def enforce_camel_case_on_tk_entry(self, event):
        widget = event.widget
        val = widget.get()
        if val:
            new_val = to_camel_case(val)
            if new_val != val:
                widget.delete(0, tk.END)
                widget.insert(0, new_val)

    def toggle_upgrade(self):
        current = self.app.vars["is_upgraded"].get()
        self.app.vars["is_upgraded"].set(not current)
        if self.app.vars["is_upgraded"].get():
            self.btn_upgrade.config(text="upgraded")
        else:
            self.btn_upgrade.config(text="unupgraded")
        self.update_adv_map_from_level()

    def update_adv_map_from_level(self, event=None):
        if getattr(self, 'adv_map_manual_override', False): return
        
        level_str = self.app.entries["level"].get_real_value().strip()
        if not level_str or not level_str.isdigit(): return
        
        lvl_num = int(level_str)
        is_upg = self.app.vars["is_upgraded"].get()
        
        key = f"{lvl_num}+" if is_upg else str(lvl_num)
        
        mapping = {
            "1": ("20", "50"), "1+": ("20", "30"),
            "2": ("16", "30"), "2+": ("16", "25"),
            "3": ("12", "25"), "3+": ("12", "20"),
            "4": ("10", "20"), "4+": ("10", "16"),
            "5": ("8", "16"),  "5+": ("8", "12"),
            "6": ("5", "12"),  "6+": ("5", "10"),
            "7": ("4", "10"),  "7+": ("3", "8"),
        }
        
        if key in mapping:
            min_v, max_v = mapping[key]
        elif lvl_num >= 8:
            min_v, max_v = ("1", "3")
        else:
            return
            
        self.app.entries["adv_min"].set_value(min_v)
        self.app.entries["adv_max"].set_value(max_v)

    def unlock_adv_map(self):
        self.adv_map_manual_override = True
        self.app.entries["adv_min"].config(state="normal")
        self.app.entries["adv_max"].config(state="normal")
        self.btn_edit_adv.config(state="disabled")

    def build_ui(self):
        header_frame = tk.Frame(self.parent, bg="#dddddd", height=45)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        btn_reset = tk.Button(header_frame, text="🔄 Reset All", bg="#ffcccc", cursor="hand2", command=self.prompt_reset)
        btn_reset.place(relx=0.02, rely=0.5, anchor="w")
        Tooltip(btn_reset, "Clear all fields and reset to default.")
        
        tk.Label(header_frame, text="VCMI CREATURE CONFIGURATION", font=("Arial", 14, "bold"), bg="#dddddd").place(relx=0.5, rely=0.5, anchor="center")

        content_frame = ttk.Frame(self.parent)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        content_frame.columnconfigure(0, weight=55)
        content_frame.columnconfigure(1, weight=45)
        content_frame.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(content_frame)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left_panel.columnconfigure(0, weight=1)
        left_panel.columnconfigure(1, weight=1)
        left_panel.rowconfigure(0, weight=0)
        left_panel.rowconfigure(1, weight=0)
        left_panel.rowconfigure(2, weight=1) 
        
        right_panel = ttk.Frame(content_frame)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(3, weight=1) 

        # =========================================================================
        # LEFT PANEL (STATS & DATA)
        # =========================================================================

        # 1. GENERAL INFO
        info = ttk.LabelFrame(left_panel, text="General information & costs")
        info.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        
        info.columnconfigure(0, minsize=140, weight=0)
        info.columnconfigure(1, minsize=220, weight=0)
        info.columnconfigure(2, minsize=140, weight=0)
        info.columnconfigure(3, weight=1)

        id_entry = self.create_smart_field(info, "Unique ID:", "id", "core:pikeman", row=0, col=0, padding=4, tooltip="Unique technical identifier for the game engine (Example: core:pikeman).")
        id_entry.bind("<FocusOut>", self.enforce_camel_case_on_widget, add="+")
        
        self.create_smart_field(info, "Name (Singular):", "name_singular", "Peasant", row=1, col=0, padding=4, tooltip="Name displayed for a single unit (Example: Peasant).")
        self.create_smart_field(info, "Name (Plural):", "name_plural", "Peasants", row=2, col=0, padding=4, tooltip="Name displayed for multiple units (Example: Peasants).")
        
        faction_entry = self.create_smart_field(info, "Faction ID:", "faction", "castle", row=3, col=0, padding=4, tooltip="The faction this unit belongs to (Example: castle).")
        faction_entry.bind("<FocusOut>", self.enforce_camel_case_on_widget, add="+")
        
        # Champ Level dynamique avec le bouton Upgraded/Unupgraded
        lbl_lvl = ttk.Label(info, text=" Level:")
        if "level" in self.app.ui_icons: lbl_lvl.config(image=self.app.ui_icons["level"], compound="left")
        lbl_lvl.grid(row=4, column=0, sticky='w', padx=5, pady=4)
        
        lvl_frame = ttk.Frame(info)
        lvl_frame.grid(row=4, column=1, sticky='w', padx=5, pady=4)
        
        lvl_entry = SmartEntry(lvl_frame, "1", is_numeric=True, width=5)
        lvl_entry.pack(side="left")
        self.app.entries["level"] = lvl_entry
        
        self.app.vars["is_upgraded"] = tk.BooleanVar(value=False)
        self.btn_upgrade = tk.Button(lvl_frame, text="unupgraded", width=10, command=self.toggle_upgrade, pady=0, bd=1, bg="#f0f0f0")
        self.btn_upgrade.pack(side="left", padx=(5,0))
        
        lvl_entry.bind("<FocusOut>", self.update_adv_map_from_level, add="+")
        lvl_entry.bind("<Return>", self.update_adv_map_from_level, add="+")
        Tooltip(lbl_lvl, "Creature tier or level, 1 to 7 usually (Example: 1).")
        Tooltip(lvl_entry, "Creature tier or level, 1 to 7 usually (Example: 1).")
        
        upgrades_entry = self.create_smart_field(info, "Upgrades To (ID):", "upgrades", "core:marksman", row=5, col=0, padding=4, tooltip="ID of the upgraded version of this creature (Example: core:marksman).")
        upgrades_entry.bind("<FocusOut>", self.enforce_camel_case_on_widget, add="+")

        self.create_smart_field(info, "Gold:", "cost_gold", "0", row=0, col=2, width=8, is_numeric=True, icon_key="gold", padding=4, tooltip="Gold cost to recruit one unit (Example: 100).")
        self.create_smart_field(info, "Wood:", "cost_wood", "0", row=1, col=2, width=8, is_numeric=True, icon_key="wood", padding=4, tooltip="Wood cost to recruit one unit (Example: 0).")
        self.create_smart_field(info, "Ore:", "cost_ore", "0", row=2, col=2, width=8, is_numeric=True, icon_key="ore", padding=4, tooltip="Ore cost to recruit one unit (Example: 0).")
        self.create_smart_field(info, "Mercury:", "cost_mercury", "0", row=3, col=2, width=8, is_numeric=True, icon_key="mercury", padding=4, tooltip="Mercury cost to recruit one unit (Example: 0).")
        self.create_smart_field(info, "Sulfur:", "cost_sulfur", "0", row=4, col=2, width=8, is_numeric=True, icon_key="sulfur", padding=4, tooltip="Sulfur cost to recruit one unit (Example: 0).")
        self.create_smart_field(info, "Crystal:", "cost_crystal", "0", row=5, col=2, width=8, is_numeric=True, icon_key="crystal", padding=4, tooltip="Crystal cost to recruit one unit (Example: 0).")
        self.create_smart_field(info, "Gems:", "cost_gems", "0", row=6, col=2, width=8, is_numeric=True, icon_key="gems", padding=4, tooltip="Gems cost to recruit one unit (Example: 0).")

        # 2. STATISTICS & DATA
        stats = ttk.LabelFrame(left_panel, text="Statistics & data")
        stats.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        
        stats.columnconfigure(0, minsize=140, weight=0)
        stats.columnconfigure(1, minsize=220, weight=0)
        stats.columnconfigure(2, minsize=140, weight=0)
        stats.columnconfigure(3, weight=1)

        self.create_smart_field(stats, "Attack:", "attack", "5", row=0, col=0, is_numeric=True, icon_key="attack", tooltip="Base attack skill (Example: 5).")
        self.create_smart_field(stats, "Defense:", "defense", "5", row=1, col=0, is_numeric=True, icon_key="defense", tooltip="Base defense skill (Example: 5).")
        
        lbl_d = ttk.Label(stats, text=" Damage:")
        if "damage" in self.app.ui_icons: lbl_d.config(image=self.app.ui_icons["damage"], compound="left")
        lbl_d.grid(row=2, column=0, sticky='w', padx=5, pady=2)
        Tooltip(lbl_d, "Damage range dealt by the unit (Example: 1-3).")

        df = ttk.Frame(stats); df.grid(row=2, column=1, sticky='w', padx=5, pady=2)
        self.app.entries["dmg_min"] = SmartEntry(df, "min", True, 8); self.app.entries["dmg_min"].pack(side="left", padx=(0,5))
        self.app.entries["dmg_max"] = SmartEntry(df, "max", True, 8); self.app.entries["dmg_max"].pack(side="left")
        Tooltip(self.app.entries["dmg_min"], "Minimum damage (Example: 1).")
        Tooltip(self.app.entries["dmg_max"], "Maximum damage (Example: 3).")

        self.create_smart_field(stats, "Health:", "hitPoints", "10", row=3, col=0, is_numeric=True, icon_key="health", tooltip="Hit points per unit before it dies (Example: 10).")
        self.create_smart_field(stats, "Speed:", "speed", "5", row=4, col=0, is_numeric=True, icon_key="speed", tooltip="Movement range in hexes during combat (Example: 4).")

        self.create_smart_field(stats, "Growth:", "growth", "10", row=5, col=0, is_numeric=True, icon_key="growth", tooltip="Base weekly growth in towns (Example: 14).")

        self.lbl_mov_type = ttk.Label(stats, text=" Movement Type:")
        if "mov_ground" in self.app.ui_icons: self.lbl_mov_type.config(image=self.app.ui_icons["mov_ground"], compound="left")
        self.lbl_mov_type.grid(row=6, column=0, sticky='w', padx=5, pady=2)
        Tooltip(self.lbl_mov_type, "Type of movement across the battlefield (Example: Ground).")

        mf = ttk.Frame(stats); mf.grid(row=6, column=1, sticky='w')
        self.app.vars["movement"] = tk.StringVar(value="Ground")
        ttk.Radiobutton(mf, text="Ground", variable=self.app.vars["movement"], value="Ground", command=self.update_movement_icon).pack(side="left")
        ttk.Radiobutton(mf, text="Fly", variable=self.app.vars["movement"], value="Fly", command=self.update_movement_icon).pack(side="left")
        ttk.Radiobutton(mf, text="Teleport", variable=self.app.vars["movement"], value="Teleport", command=self.update_movement_icon).pack(side="left")

        self.create_smart_field(stats, "Shots:", "shots", "0", row=0, col=2, is_numeric=True, icon_key="shots", tooltip="Number of ranged attacks. 0 means melee unit (Example: 12).")
        self.create_smart_field(stats, "Spell pts:", "spellPoints", "0", row=1, col=2, is_numeric=True, icon_key="spellPoints", tooltip="Mana pool for casting spells (Example: 0).")

        self.create_smart_field(stats, "AI Value:", "aiValue", "100", row=2, col=2, is_numeric=True, icon_key="aiValue", tooltip="Strength rating used by AI for recruitment and combat decisions (Example: 80).")
        
        self.create_smart_field(stats, "Horde Bonus:", "horde", "0", row=3, col=2, is_numeric=True, icon_key="horde", tooltip="Extra weekly growth provided by a Horde building (Example: 5).")

        lbl_adv = ttk.Label(stats, text=" Adv. Map amt:")
        if "advMap" in self.app.ui_icons: lbl_adv.config(image=self.app.ui_icons["advMap"], compound="left")
        lbl_adv.grid(row=4, column=2, sticky='w', padx=5, pady=2)
        Tooltip(lbl_adv, "Random stack size range when generated on the adventure map (Example: 20-50).")

        amf = ttk.Frame(stats); amf.grid(row=4, column=3, sticky='w', padx=5, pady=2)
        
        self.app.entries["adv_min"] = SmartTkEntry(amf, "min", True, 6); self.app.entries["adv_min"].pack(side="left", padx=(0,2))
        self.app.entries["adv_max"] = SmartTkEntry(amf, "max", True, 6); self.app.entries["adv_max"].pack(side="left", padx=(0,5))
        
        self.app.entries["adv_min"].config(state="disabled")
        self.app.entries["adv_max"].config(state="disabled")
        
        Tooltip(self.app.entries["adv_min"], "Minimum stack size (Example: 20).")
        Tooltip(self.app.entries["adv_max"], "Maximum stack size (Example: 50).")
        
        self.btn_edit_adv = tk.Button(amf, text="Edit", width=4, command=self.unlock_adv_map, pady=0, bd=1, bg="#f0f0f0")
        self.btn_edit_adv.pack(side="left")
        Tooltip(self.btn_edit_adv, "Unlock fields for manual edit (disables auto-scaling by level).")
        
        lbl_dw = ttk.Label(stats, text=" Double Wide:")
        if "doubleWide" in self.app.ui_icons: lbl_dw.config(image=self.app.ui_icons["doubleWide"], compound="left")
        lbl_dw.grid(row=5, column=2, sticky='w', padx=5, pady=2)
        Tooltip(lbl_dw, "Indicates if the creature takes up two hexes in combat (Example: Yes).")
        
        dw_frame = ttk.Frame(stats); dw_frame.grid(row=5, column=3, sticky='w')
        self.app.vars["doubleWide"] = tk.BooleanVar(value=False)
        ttk.Radiobutton(dw_frame, text="Yes", variable=self.app.vars["doubleWide"], value=True).pack(side="left")
        ttk.Radiobutton(dw_frame, text="No", variable=self.app.vars["doubleWide"], value=False).pack(side="left")

        lbl_sp = ttk.Label(stats, text=" Is Special:")
        if "special" in self.app.ui_icons: lbl_sp.config(image=self.app.ui_icons["special"], compound="left")
        lbl_sp.grid(row=6, column=2, sticky='w', padx=5, pady=2)
        Tooltip(lbl_sp, "Marks the unit as special, like commanders or war machines (Example: No).")
        
        sp_frame = ttk.Frame(stats); sp_frame.grid(row=6, column=3, sticky='w')
        self.app.vars["special"] = tk.BooleanVar(value=False)
        ttk.Radiobutton(sp_frame, text="Yes", variable=self.app.vars["special"], value=True).pack(side="left")
        ttk.Radiobutton(sp_frame, text="No", variable=self.app.vars["special"], value=False).pack(side="left")

        # =========================================================================
        # 3. SPECIAL ABILITIES (Two Columns Architecture)
        # =========================================================================
        self.special_frame = ttk.LabelFrame(left_panel, text="Special abilities")
        self.special_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        self.special_frame.rowconfigure(0, weight=1)
        self.special_frame.columnconfigure(0, weight=55)
        self.special_frame.columnconfigure(1, weight=45)
        
        # --- LEFT COLUMN: Bonus Library ---
        lib_frame = ttk.Frame(self.special_frame)
        lib_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        self.lib_filter_var = tk.StringVar()
        self.lib_filter_var.trace_add("write", self.populate_library_list)
        
        search_f = ttk.Frame(lib_frame)
        search_f.pack(fill="x", pady=(0, 5))
        
        ttk.Label(search_f, text="🔍").pack(side="left")
        filter_entry = ttk.Entry(search_f, textvariable=self.lib_filter_var)
        filter_entry.pack(side="left", fill="x", expand=True, padx=(2,0))
        Tooltip(filter_entry, "Filter the abilities library")
        
        style = ttk.Style()
        style.configure("Compact.Treeview", rowheight=18)
        
        self.lib_tree = ttk.Treeview(lib_frame, columns=("add", "name"), show="headings", style="Compact.Treeview")
        self.lib_tree.heading("add", text="➕")
        self.lib_tree.column("add", width=35, stretch=False, anchor="center")
        self.lib_tree.heading("name", text="Bonus Library")
        self.lib_tree.column("name", anchor="w")
        
        lib_scroll = tk.Scrollbar(lib_frame, orient="vertical", command=self.lib_tree.yview, width=24)
        self.lib_tree.configure(yscrollcommand=lib_scroll.set)
        
        self.lib_tree.pack(side="left", fill="both", expand=True)
        lib_scroll.pack(side="right", fill="y")
        
        self.lib_tree.bind("<ButtonRelease-1>", self.on_library_click)
        self.lib_tree.bind("<Double-Button-1>", self.on_lib_double_click)
        self.lib_tree.bind("<Return>", self.on_lib_return)
        
        # --- RIGHT COLUMN: Active Abilities ---
        act_frame = ttk.LabelFrame(self.special_frame, text="Active Abilities")
        act_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        act_top_f = ttk.Frame(act_frame)
        act_top_f.pack(fill="x", padx=5, pady=(2, 0))
        
        self.btn_edit_lib = tk.Button(act_top_f, text="Edit", width=4, command=self.edit_selected_library, pady=0, bd=1, bg="#f0f0f0")
        self.btn_edit_lib.pack(side="right")
        Tooltip(self.btn_edit_lib, "Edit the selected library ability (prevents duplicates).")
        
        self.act_canvas = tk.Canvas(act_frame, highlightthickness=0)
        act_scroll = tk.Scrollbar(act_frame, orient="vertical", command=self.act_canvas.yview, width=24)
        self.act_scrollable_frame = ttk.Frame(self.act_canvas)
        
        self.act_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.act_canvas.configure(scrollregion=self.act_canvas.bbox("all"))
        )
        
        self.act_canvas.create_window((0, 0), window=self.act_scrollable_frame, anchor="nw", width=self.act_canvas.winfo_width())
        self.act_canvas.bind('<Configure>', lambda e: self.act_canvas.itemconfig(self.act_canvas.find_withtag("all")[0], width=e.width))
        self.act_canvas.configure(yscrollcommand=act_scroll.set)
        
        self.act_canvas.pack(side="left", fill="both", expand=True, pady=(5,0))
        act_scroll.pack(side="right", fill="y", pady=(5,0))
        
        # Pre-load abilities resources
        self.load_default_ability_icon()
        self.populate_library_list()
        self.refresh_active_abilities()

        # =========================================================================
        # RIGHT PANEL (ASSETS & EXPORT)
        # =========================================================================

        top_assets = ttk.Frame(right_panel)
        top_assets.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        top_assets.columnconfigure(0, weight=1)
        top_assets.columnconfigure(1, weight=1)

        # 4. PORTRAITS
        port = ttk.LabelFrame(top_assets, text="Portraits (.png, .bmp)")
        port.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        
        port_inner = ttk.Frame(port)
        port_inner.pack(expand=True)
        
        self.create_clickable_portrait(port_inner, "iconLarge", "IconLarge", "58x64", "prtLarge.png", 0, "Icon shown in hero screen/town screen (Example: prtLarge.png).")
        self.create_clickable_portrait(port_inner, "iconSmall", "IconSmall", "32x32", "prtSmall.png", 1, "Icon shown on the adventure map/combat order (Example: prtSmall.png).")

        # 5. ANIMATIONS
        gfx = ttk.LabelFrame(top_assets, text="Animations")
        gfx.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
        
        gfx_inner = ttk.Frame(gfx)
        gfx_inner.pack(expand=True, anchor="w", padx=15)
        
        self.create_smart_field(gfx_inner, "Battle Anim:", "anim_battle", "creature.def", 0, 0, width=15, padding=8, tooltip="Filename of the battle animation (Example: creature.def).")
        self.create_smart_field(gfx_inner, "Map Anim:", "anim_map", "creature_map.def", 1, 0, width=15, padding=8, tooltip="Filename of the adventure map animation (Example: creature_map.def).")
        self.create_smart_field(gfx_inner, "Projectile:", "anim_missile", "projectile.def", 2, 0, width=15, padding=8, tooltip="Filename of the ranged attack projectile animation (Example: projectile.def).")

        # 6. AUDIO
        audio = ttk.LabelFrame(right_panel, text="Audio (.wav, .ogg)")
        audio.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        audio_inner = ttk.Frame(audio)
        audio_inner.pack(expand=True, pady=10)
        
        snds_layout = [
            ("attack", 0, 0, "Sound played when attacking (Example: attack.wav)."), 
            ("defend", 1, 0, "Sound played when defending (Example: defend.wav)."), 
            ("killed", 2, 0, "Sound played when killed (Example: killed.wav)."),
            ("shoot", 0, 1, "Sound played when shooting (Example: shoot.wav)."), 
            ("move", 1, 1, "Sound played when moving (Example: move.wav)."), 
            ("wince", 2, 1, "Sound played when taking damage (Example: wince.wav)."),
            ("startMoving", 0, 2, "Sound played at the start of movement (Example: startMove.wav)."), 
            ("endMoving", 1, 2, "Sound played at the end of movement (Example: endMove.wav).")
        ]
        
        for s, r, col_idx, tt in snds_layout:
            c = col_idx * 4
            self.create_compact_audio(audio_inner, f"{s.title()}:", f"snd_{s}", f"{s}.wav", r, c, tooltip=tt)
            
        audio_inner.columnconfigure(3, minsize=40)
        audio_inner.columnconfigure(7, minsize=40)

        # 7. EXPORT CONTAINER
        self.export_container = ttk.Frame(right_panel)
        self.export_container.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)

    # -------------------------------------------------------------------------
    # NEW SPECIAL ABILITIES LOGIC (Two-Column)
    # -------------------------------------------------------------------------
    def load_default_ability_icon(self):
        try:
            icon_path = os.path.join(self.app.res_dir, "ability", "_ability.png")
            if os.path.exists(icon_path):
                img = Image.open(icon_path).convert("RGBA").resize((24, 24), Image.LANCZOS)
            else:
                img = Image.new('RGBA', (24, 24), color=(200, 200, 200, 255))
            self.default_ability_img = ImageTk.PhotoImage(img)
        except Exception as e:
            logging.error(f"Error loading ability icon: {e}")
            self.default_ability_img = ImageTk.PhotoImage(Image.new('RGBA', (24, 24), color=(200, 200, 200, 255)))

    def populate_library_list(self, *args):
        for item in self.lib_tree.get_children():
            self.lib_tree.delete(item)
            
        q = self.lib_filter_var.get().lower()
        for b in self.bonus_list:
            if q in b.lower():
                self.lib_tree.insert("", tk.END, values=("➕", b))

    def on_library_click(self, event):
        region = self.lib_tree.identify_region(event.x, event.y)
        if region != "cell": return
        column = self.lib_tree.identify_column(event.x)
        if column == "#1":
            item = self.lib_tree.identify_row(event.y)
            if item:
                val = self.lib_tree.item(item, "values")[1]
                self.add_ability(key_name=val)

    def on_lib_double_click(self, event):
        region = self.lib_tree.identify_region(event.x, event.y)
        if region != "cell": return
        column = self.lib_tree.identify_column(event.x)
        if column == "#1": return 
        sel = self.lib_tree.selection()
        if sel:
            val = self.lib_tree.item(sel[0], "values")[1]
            self.add_ability(key_name=val)

    def on_lib_return(self, event):
        sel = self.lib_tree.selection()
        if sel:
            val = self.lib_tree.item(sel[0], "values")[1]
            self.add_ability(key_name=val)

    def edit_selected_library(self):
        sel = self.lib_tree.selection()
        if not sel: return
        val = self.lib_tree.item(sel[0], "values")[1]
        val_camel = to_camel_case(val)
        
        for i in range(len(self.app.dynamic_abilities)-1, -1, -1):
            if self.app.dynamic_abilities[i]["key_name"] == val_camel:
                self.open_edit_popup(i)
                return
                
        self.add_ability(key_name=val)
        self.open_edit_popup(len(self.app.dynamic_abilities) - 1)
        
    def show_context_menu(self, event, index):
        menu = tk.Menu(self.parent.winfo_toplevel(), tearoff=0)
        menu.add_command(label="✏️ Edit", command=lambda: self.open_edit_popup(index))
        menu.add_command(label="📑 Clone", command=lambda: self.clone_ability(index))
        menu.add_separator()
        menu.add_command(label="❌ Delete", command=lambda: self.delete_ability(index))
        menu.post(event.x_root, event.y_root)
        
    def delete_ability(self, index):
        del self.app.dynamic_abilities[index]
        self.refresh_active_abilities()

    def clone_ability(self, index):
        ab = self.app.dynamic_abilities[index]
        new_key = ab["key_name"] + "Copy"
        new_payload = copy.deepcopy(ab["full_payload"])
        self.add_ability(key_name=new_key, full_payload=new_payload)

    def refresh_active_abilities(self):
        for widget in self.act_scrollable_frame.winfo_children():
            widget.destroy()
            
        for i, ab in enumerate(self.app.dynamic_abilities):
            f = tk.Frame(self.act_scrollable_frame, cursor="hand2", bg="#ffffff", bd=1, relief="solid")
            f.pack(fill="x", pady=1, padx=2)
            
            # --- PACKING DU BOUTON DELETE EN PREMIER (Sécurise son ancrage à droite) ---
            lbl_del = tk.Label(f, text="❌", font=("Arial", 9), bg="#ffffff", fg="#cc0000", cursor="hand2")
            lbl_del.pack(side="right", padx=8)
            Tooltip(lbl_del, "Delete this ability")
            
            # --- PACKING DES AUTRES ELEMENTS (À gauche) ---
            lbl_img = tk.Label(f, image=self.default_ability_img, bg="#ffffff")
            lbl_img.pack(side="left", padx=2, pady=1)
            
            lbl_name = tk.Label(f, text=ab["key_name"], font=("Arial", 9, "bold"), bg="#ffffff")
            lbl_name.pack(side="left", padx=(5, 0))
            
            params = []
            payload = ab.get("full_payload", {})
            for key in ["type", "subtype", "val", "addInfo"]:
                v = str(payload.get(key, ""))
                if v != "" and not is_placeholder_hint(v):
                    params.append(f"{key}: {v}")
            
            adv_keys = [k for k in payload if k not in ["type", "subtype", "val", "addInfo", "description"] and payload[k]]
            if adv_keys: params.append("...")
                
            param_str = f"  ({', '.join(params)})" if params else ""
            
            lbl_params = None
            if param_str:
                lbl_params = tk.Label(f, text=param_str, font=("Arial", 8, "italic"), bg="#ffffff", fg="#555555")
                # Utilisation de fill="x" et expand=True ici pousse les éléments contre le bouton delete,
                # mais le bouton n'est jamais écrasé car il a été pack en 1er.
                lbl_params.pack(side="left", padx=(0, 5), fill="x", expand=True)
                lbl_params.config(anchor="w")
                
            def on_enter(e, frm=f, img=lbl_img, txt1=lbl_name, txt2=lbl_params, ldel=lbl_del):
                frm.config(bg="#d9e8f5"); img.config(bg="#d9e8f5"); txt1.config(bg="#d9e8f5")
                if txt2: txt2.config(bg="#d9e8f5")
                ldel.config(bg="#d9e8f5")

            def on_leave(e, frm=f, img=lbl_img, txt1=lbl_name, txt2=lbl_params, ldel=lbl_del):
                frm.config(bg="#ffffff"); img.config(bg="#ffffff"); txt1.config(bg="#ffffff")
                if txt2: txt2.config(bg="#ffffff")
                ldel.config(bg="#ffffff")

            for w in (f, lbl_img, lbl_name) + ((lbl_params,) if lbl_params else ()):
                w.bind("<Double-Button-1>", lambda e, idx=i: self.open_edit_popup(idx))
                w.bind("<Button-3>", lambda e, idx=i: self.show_context_menu(e, idx)) 
                w.bind("<Button-2>", lambda e, idx=i: self.show_context_menu(e, idx)) 
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
                
            lbl_del.bind("<Button-1>", lambda e, idx=i: self.delete_ability(idx))
            lbl_del.bind("<Enter>", on_enter)
            lbl_del.bind("<Leave>", on_leave)
                
        self.act_scrollable_frame.update_idletasks()
        self.act_canvas.configure(scrollregion=self.act_canvas.bbox("all"))

    def add_ability(self, key_name=None, full_payload=None):
        if not key_name: return
        key_name = to_camel_case(key_name)
        
        if full_payload is None:
            hint_key = key_name if key_name in self.bonus_hints else next((k for k in self.bonus_hints if to_camel_case(k) == key_name), key_name)
            if hint_key in self.bonus_hints:
                full_payload = copy.deepcopy(self.bonus_hints[hint_key])
            else:
                full_payload = {"type": "", "subtype": "", "val": ""}
        
        ability_obj = {
            "key_name": key_name,
            "full_payload": full_payload
        }
        ability_obj["key_entry"] = ProxyEntry(ability_obj)
        
        self.app.dynamic_abilities.append(ability_obj)
        self.refresh_active_abilities()

    # -------------------------------------------------------------------------
    # IDENTIFIERS SEARCH POPUP (Contextual)
    # -------------------------------------------------------------------------
    def open_id_search(self, target_entry, hint_text):
        if not self.identifiers_lib:
            messagebox.showwarning("Missing Library", "The 'library-identifiers.json' library could not be loaded.\nEnsure the file exists in the directory.")
            return
            
        top = tk.Toplevel(self.parent.winfo_toplevel())
        top.title("Search VCMI Identifiers")
        
        x = top.winfo_pointerx() + 15
        y = top.winfo_pointery() + 15
        top.geometry(f"550x400+{x}+{y}")
        top.transient(self.parent.winfo_toplevel())
        top.grab_set()
        
        hint_lower = str(hint_text).lower()
        preferred_cat = "All"
        if "spell" in hint_lower: preferred_cat = "combatSpells"
        elif "creature" in hint_lower: preferred_cat = "creatures"
        elif "faction" in hint_lower: preferred_cat = "factions"
        elif "skill" in hint_lower: preferred_cat = "skills"
        elif "resource" in hint_lower: preferred_cat = "resources"
        elif "artifact" in hint_lower: preferred_cat = "artifacts"
        elif "hero" in hint_lower: preferred_cat = "heroes"
        
        filter_var = tk.StringVar()
        
        search_f = ttk.Frame(top, padding=5)
        search_f.pack(fill="x")
        
        ttk.Label(search_f, text="🔍").pack(side="left")
        
        cat_var = tk.StringVar()
        cats = ["All"] + list(self.identifiers_lib.keys())
        cat_cb = ttk.Combobox(search_f, textvariable=cat_var, values=cats, state="readonly", width=15)
        cat_cb.set(preferred_cat if preferred_cat in cats else "All")
        cat_cb.pack(side="left", padx=5)
        
        ttk.Entry(search_f, textvariable=filter_var).pack(side="left", fill="x", expand=True)
        
        tree_f = ttk.Frame(top, padding=5)
        tree_f.pack(fill="both", expand=True)
        
        cols = ("id", "name", "desc")
        tree = ttk.Treeview(tree_f, columns=cols, show="headings", selectmode="browse")
        tree.heading("id", text="Identifier")
        tree.heading("name", text="Name")
        tree.heading("desc", text="Description")
        tree.column("id", width=180)
        tree.column("name", width=120)
        tree.column("desc", width=200)
        
        scroll = tk.Scrollbar(tree_f, orient="vertical", command=tree.yview, width=24)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        
        def populate(*args):
            tree.delete(*tree.get_children())
            q = filter_var.get().lower()
            selected_cat = cat_var.get()
            
            if selected_cat == "All":
                cats_to_show = self.identifiers_lib.keys()
            else:
                cats_to_show = [selected_cat]
            
            for cat in cats_to_show:
                if cat not in self.identifiers_lib: continue
                for item_id, item_data in self.identifiers_lib[cat].items():
                    name = item_data.get("name", "")
                    desc = item_data.get("description", "")
                    if q in item_id.lower() or q in name.lower() or q in desc.lower():
                        tree.insert("", tk.END, values=(item_id, name, desc))
                        
        filter_var.trace_add("write", populate)
        cat_cb.bind("<<ComboboxSelected>>", lambda e: populate())
        populate()
        
        def confirm(evt=None):
            sel = tree.selection()
            if sel:
                val = tree.item(sel[0], "values")[0]
                target_entry.set_value(val) 
                top.destroy()
                
        tree.bind("<Double-Button-1>", confirm)
        tree.bind("<Return>", confirm)
        
        btn_f = ttk.Frame(top, padding=5)
        btn_f.pack(fill="x")
        ttk.Button(btn_f, text="Cancel", command=top.destroy).pack(side="right", padx=5)
        ttk.Button(btn_f, text="Select", command=confirm).pack(side="right", padx=5)

    def open_edit_popup(self, index):
        ab = self.app.dynamic_abilities[index]
        new_k = ab["key_name"]
        
        top = tk.Toplevel(self.parent.winfo_toplevel())
        top.title(f"Edit Ability: {new_k}")
        
        # Positionnement
        w, h = 420, 320 # Valeur de base (ajustée plus bas)
        x = self.special_frame.winfo_rootx() + 20
        y = self.special_frame.winfo_rooty() - h - 10
        if y < 10: y = 20
        
        top.transient(self.parent.winfo_toplevel())
        top.grab_set()
        
        content = ttk.Frame(top, padding=15)
        content.pack(fill="both", expand=True)
        
        ttk.Label(content, text="Key Name:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        key_var = tk.StringVar(value=new_k)
        key_entry = ttk.Entry(content, textvariable=key_var)
        key_entry.grid(row=0, column=1, sticky="ew", pady=5)
        key_entry.bind("<FocusOut>", self.enforce_camel_case_on_tk_entry)
        
        orig_hint = self.bonus_hints.get(new_k, {})
        
        # --- GENERATEUR DYNAMIQUE DE CHAMP ---
        def build_dynamic_field(field_name, row_idx, compact=False):
            ttk.Label(content, text=f"{field_name.capitalize()}:").grid(row=row_idx, column=0, sticky="w", pady=5)
            f = ttk.Frame(content)
            f.grid(row=row_idx, column=1, sticky="ew", pady=5)
            
            raw_val = str(ab["full_payload"].get(field_name, ""))
            ph_hint = orig_hint.get(field_name, f"{field_name.capitalize()}...")
            act_val = raw_val if not is_placeholder_hint(raw_val) else ""
            if act_val == "" and not is_placeholder_hint(ph_hint): 
                ph_hint = raw_val if raw_val else f"{field_name.capitalize()}..."
                
            enum_match = re.search(r"enum\s*\((.*?)\)", str(ph_hint), re.IGNORECASE)
            int_match = re.search(r"integer\s*\[(-?\d+)\.\.(-?\d+)\]", str(ph_hint), re.IGNORECASE)
            is_percentage = "percent" in str(ph_hint).lower() or "%" in str(ph_hint)
            
            if enum_match:
                enum_vals = [v.strip(" '\"") for v in enum_match.group(1).split(",")]
                cb = ttk.Combobox(f, values=enum_vals)
                # Si compact (ex: champ Val), on limite la taille, sinon on l'étire
                cb.pack(side="left", fill="x" if not compact else "none", expand=not compact)
                if compact: cb.config(width=15)
                
                if act_val: cb.set(act_val)
                cb.get_real_value = cb.get 
                Tooltip(cb, str(ph_hint))
                return cb
                
            elif int_match:
                min_v = int(int_match.group(1))
                max_v = int(int_match.group(2))
                if min_v == 0 and max_v == 100: is_percentage = True
                    
                if is_percentage:
                    # CHAMP TEXTE POURCENTAGE
                    se = SmartEntry(f, placeholder=str(ph_hint), is_numeric=True, width=15 if compact else 20)
                    se.pack(side="left", fill="x" if not compact else "none", expand=not compact)
                    se.set_value(act_val)
                    ttk.Label(f, text="%").pack(side="left", padx=2)
                    
                    def clamp_val(event, entry=se, mn=min_v, mx=max_v):
                        val = entry.get_real_value()
                        if val and (val.isdigit() or (val.startswith('-') and val[1:].isdigit())):
                            v = int(val)
                            if v < mn: entry.set_value(str(mn))
                            elif v > mx: entry.set_value(str(mx))
                    se.bind("<FocusOut>", clamp_val, add="+")
                    Tooltip(se, str(ph_hint))
                    return se
                else:
                    # SPINBOX POUR LIMITES (Ex: -9 à 9)
                    sb = ttk.Spinbox(f, from_=min_v, to=max_v, width=10 if compact else 20)
                    sb.pack(side="left", fill="x" if not compact else "none", expand=not compact)
                    if act_val: sb.set(act_val)
                    sb.get_real_value = sb.get
                    Tooltip(sb, str(ph_hint))
                    return sb
            else:
                if is_percentage:
                    se = SmartEntry(f, placeholder=str(ph_hint), is_numeric=True, width=15 if compact else 20)
                    se.pack(side="left", fill="x" if not compact else "none", expand=not compact)
                    se.set_value(act_val)
                    ttk.Label(f, text="%").pack(side="left", padx=2)
                    Tooltip(se, str(ph_hint))
                    return se
                else:
                    se = SmartEntry(f, placeholder=str(ph_hint), width=15 if compact else 20)
                    se.pack(side="left", fill="x" if not compact else "none", expand=not compact)
                    se.set_value(act_val)
                    
                    if "ID" in str(ph_hint):
                        btn = ttk.Button(f, text="🔍", width=3, command=lambda e=se, ht=ph_hint: self.open_id_search(e, ht))
                        btn.pack(side="right", padx=(2,0))
                        Tooltip(btn, "Search in VCMI Identifiers")
                    
                    Tooltip(se, str(ph_hint))
                    return se

        type_entry = build_dynamic_field("type", 1)
        subtype_entry = build_dynamic_field("subtype", 2)
        val_entry = build_dynamic_field("val", 3, compact=False) # Val est désomais de taille standard
        
        # --- Masquage conditionnel de addInfo ---
        addinfo_entry = None
        if "addInfo" in orig_hint:
            addinfo_entry = build_dynamic_field("addInfo", 4)
            h = 360 # Fenêtre plus grande si addInfo est présent
            
        top.geometry(f"{w}x{h}+{x}+{y}")
        content.columnconfigure(1, weight=1)
        
        def apply_fields_to_ab():
            k = key_entry.get()
            ab["key_name"] = k
            
            t_val = type_entry.get_real_value()
            s_val = subtype_entry.get_real_value()
            v_val = val_entry.get_real_value()
            
            # Le type reste requis. S'il est vide, on assigne "" (au lieu du hint destructeur)
            if t_val: ab["full_payload"]["type"] = t_val
            else: ab["full_payload"]["type"] = ""
            
            if s_val: ab["full_payload"]["subtype"] = s_val
            elif "subtype" in ab["full_payload"]: del ab["full_payload"]["subtype"]
            
            if v_val: ab["full_payload"]["val"] = v_val
            elif "val" in ab["full_payload"]: del ab["full_payload"]["val"]
            
            if addinfo_entry:
                a_val = addinfo_entry.get_real_value()
                if a_val: ab["full_payload"]["addInfo"] = a_val
                elif "addInfo" in ab["full_payload"]: del ab["full_payload"]["addInfo"]
            
        def save_changes():
            apply_fields_to_ab()
            self.refresh_active_abilities()
            top.destroy()
            
        def clone():
            apply_fields_to_ab()
            self.clone_ability(index)
            top.destroy()
            
        def delete():
            self.delete_ability(index)
            top.destroy()
            
        def open_adv():
            apply_fields_to_ab()
            self.open_current_advanced_editor(index, top)
            
        btn_f = ttk.Frame(content)
        # Positionnement adaptatif des boutons selon si addInfo est présent ou non
        btn_f.grid(row=5 if addinfo_entry else 4, column=0, columnspan=2, pady=15, sticky="ew")
        ttk.Button(btn_f, text="⚙️ Adv. Modifiers (JSON)", command=open_adv).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="📑 Clone", command=clone).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="❌ Delete", command=delete).pack(side="left", fill="x", expand=True, padx=2)
        
        ttk.Button(content, text="Save & Close", command=save_changes).grid(row=6 if addinfo_entry else 5, column=0, columnspan=2, pady=5, sticky="ew")

    def open_current_advanced_editor(self, index, parent_popup):
        ab = self.app.dynamic_abilities[index]
        key_name = ab["key_name"]
        
        top = tk.Toplevel(parent_popup)
        top.title(f"Advanced Bonus Editor - {key_name}")
        
        w, h = 600, 500
        x = self.special_frame.winfo_rootx() + 20
        y = self.special_frame.winfo_rooty() - h - 10
        if y < 10: y = 20
        top.geometry(f"{w}x{h}+{x}+{y}")
        
        top.transient(parent_popup)
        top.grab_set()
        
        lbl_info = ttk.Label(top, text="VCMI Bonus Payload Editor (JSON format)\nUse this to configure Limiters, Propagators, and Updaters.", justify="left", font=("Arial", 9, "bold"))
        lbl_info.pack(fill="x", padx=10, pady=5)
        
        text_area = tk.Text(top, wrap="none", font=("Consolas", 10))
        scroll_y = ttk.Scrollbar(top, orient="vertical", command=text_area.yview)
        scroll_x = ttk.Scrollbar(top, orient="horizontal", command=text_area.xview)
        text_area.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        text_area.pack(side="top", fill="both", expand=True, padx=10, pady=5)
        
        payload_copy = copy.deepcopy(ab["full_payload"])
        if "description" in payload_copy:
            del payload_copy["description"]
            
        json_str = json.dumps(payload_copy, indent=4)
        text_area.insert("1.0", json_str)
        
        def save_advanced_bonus():
            try:
                raw_json = text_area.get("1.0", tk.END).strip()
                new_payload = json.loads(raw_json)
                
                if "type" not in new_payload:
                    messagebox.showwarning("Attention", "Le champ 'type' est strictement requis par VCMI pour que le bonus fonctionne. Pensez à l'ajouter !", parent=top)
                
                if "description" in ab["full_payload"]:
                    new_payload["description"] = ab["full_payload"]["description"]
                    
                ab["full_payload"] = new_payload
                self.refresh_active_abilities()
                
                top.destroy()
                parent_popup.destroy()
            except json.JSONDecodeError as je:
                messagebox.showerror("Invalid JSON", f"Your JSON is malformed.\n\nDetails: {je}", parent=top)
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred:\n{e}", parent=top)

        btn_frame = ttk.Frame(top)
        btn_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(btn_frame, text="Cancel", command=top.destroy).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Save & Apply", command=save_advanced_bonus).pack(side="right", padx=5)

    # -------------------------------------------------------------------------
    # CLICKABLE PORTRAITS LOGIC
    # -------------------------------------------------------------------------
    def create_clickable_portrait(self, parent, key, label, size_str, default_img, col, tooltip=None):
        f = ttk.Frame(parent)
        f.grid(row=0, column=col, padx=15, pady=10)
        
        lbl_w = ttk.Label(f, text=label, font=("Arial", 9, "bold"))
        lbl_w.pack(pady=(5, 5))
        if tooltip: Tooltip(lbl_w, tooltip)
        
        img_lbl = tk.Label(f, cursor="hand2")
        img_lbl.pack(pady=5)
        if tooltip: Tooltip(img_lbl, tooltip)
        
        ttk.Label(f, text=size_str, font=("Arial", 8)).pack(pady=(0, 5))
        
        self.image_refs[key] = {"label": img_lbl, "img_tk_normal": None, "img_tk_dark": None}
        
        if key not in self.app.entries: self.app.entries[key] = DummyEntry(default_img)
        path = os.path.join(self.app.res_dir, default_img)
        self._set_portrait_image(key, path, default_img)
        
        img_lbl.bind("<Enter>", lambda e, k=key: self._on_portrait_hover(k, True))
        img_lbl.bind("<Leave>", lambda e, k=key: self._on_portrait_hover(k, False))
        img_lbl.bind("<Button-1>", lambda e, k=key: self.load_image_smart(k))

    def _set_portrait_image(self, key, path, filename=""):
        state = self.image_refs.get(key)
        if not state: return
        actual_path = path
        if not os.path.exists(actual_path):
            default_img = "prtSmall.png" if key == "iconSmall" else "prtLarge.png"
            actual_path = os.path.join(self.app.res_dir, default_img)
            
        if os.path.exists(actual_path):
            try:
                img = Image.open(actual_path).convert("RGBA")
                state["img_tk_normal"] = ImageTk.PhotoImage(img)
                enhancer = ImageEnhance.Brightness(img)
                dark_img = enhancer.enhance(0.4)
                state["img_tk_dark"] = ImageTk.PhotoImage(dark_img)
                state["label"].config(image=state["img_tk_normal"], text="")
            except: pass
        else: state["label"].config(image="", text="No Img", width=8, height=4)
        if filename: self.app.entries[key].set_value(filename)

    def _on_portrait_hover(self, key, entering):
        state = self.image_refs.get(key)
        if not state or not state.get("img_tk_dark"): return
        lbl = state["label"]
        if entering: lbl.config(image=state["img_tk_dark"])
        else: lbl.config(image=state["img_tk_normal"])

    def load_image_smart(self, key):
        f = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.bmp;*.jpg")])
        if not f: return
        try:
            with Image.open(f) as img:
                img = img.convert("RGBA")
                w, h = img.size
                
                target_key = key
                
                # Check target matches with a +/- 2 pixel tolerance
                is_large_match = (56 <= w <= 60 and 62 <= h <= 66)
                is_small_match = (30 <= w <= 34 and 30 <= h <= 34)

                # Swap logic if mistakenly clicked the wrong icon box
                if key == "iconSmall" and is_large_match:
                    target_key = "iconLarge"
                elif key == "iconLarge" and is_small_match:
                    target_key = "iconSmall"
                
                target_size = (58, 64) if target_key == "iconLarge" else (32, 32)
                
                # If dimensions are not strictly exact, resize and crop precisely
                if (w, h) != target_size:
                    # ImageOps.fit maintains aspect ratio, covers the target size, and crops the remainder evenly from center
                    img = ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS)
                    filename = f"cropped_{target_key}_{os.path.basename(f)}"
                    cache_path = os.path.join(self.app.cache_dir, filename)
                    img.save(cache_path, format="PNG")
                    path_to_load = cache_path
                    filename_to_set = filename
                else:
                    path_to_load = f
                    filename_to_set = os.path.basename(f)

            self._set_portrait_image(target_key, path_to_load, filename_to_set)
        except Exception as e: 
            logging.error(f"Error loading image: {e}", exc_info=True)

    # -------------------------------------------------------------------------
    # AUDIO HELPERS
    # -------------------------------------------------------------------------
    def create_compact_audio(self, p, lbl, key, ph, r, c, tooltip=None):
        l = ttk.Label(p, text=lbl, font=("Arial", 8))
        l.grid(row=r, column=c, padx=(5,2), pady=8, sticky='e')
        e = SmartEntry(p, ph, width=13)
        e.grid(row=r, column=c+1, padx=2, pady=8)
        if tooltip: Tooltip(l, tooltip); Tooltip(e, tooltip)
        self.app.entries[key] = e
        self.app.vars[key+"_path"] = tk.StringVar()
        tk.Button(p, text="...", width=2, command=lambda: self.pick_audio(key), pady=0, bd=1, bg="#f0f0f0").grid(row=r, column=c+2, padx=2, pady=8)
        tk.Button(p, text="▶", width=2, bg="#90EE90", font=("Arial", 7), command=lambda: self.play_snd(self.app.vars[key+"_path"].get()), pady=0, bd=1).grid(row=r, column=c+3, padx=(1,5), pady=8)

    def pick_audio(self, key):
        f = filedialog.askopenfilename(filetypes=[("Audio", "*.wav;*.ogg")])
        if f: self.app.entries[key].set_value(os.path.basename(f)); self.app.vars[key+"_path"].set(f)

    def play_snd(self, p):
        if AUDIO_AVAILABLE and p and os.path.exists(p):
            if self.current_sound: self.current_sound.stop()
            self.current_sound = pygame.mixer.Sound(p); self.current_sound.play()
    
    def update_movement_icon(self):
        if not self.lbl_mov_type: return
        val = self.app.vars["movement"].get()
        key = "mov_ground"
        if val == "Fly": key = "mov_fly"
        elif val == "Teleport": key = "mov_teleport"
        if key in self.app.ui_icons: self.lbl_mov_type.config(image=self.app.ui_icons[key])