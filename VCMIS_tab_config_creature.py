import os
import json
import copy
import logging
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageEnhance, ImageOps

from VCMIS_ui_components import Tooltip, SmartEntry, SmartTkEntry, DummyEntry, ProxyEntry

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

def to_camel_case(text):
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
    v = str(val_str).lower().strip()
    keywords = ["string", "integer", "number", "enum", "array", "object", "any", "boolean"]
    has_keyword = any(k in v for k in keywords)
    has_brackets = ("(" in v and ")" in v) or ("[" in v and "]" in v)
    is_exact_keyword = v in keywords
    return (has_keyword and has_brackets) or is_exact_keyword

# -------------------------------------------------------------------------
# JSON FORMATTER CLASS
# -------------------------------------------------------------------------
class VCMIJSONFormatter:
    @staticmethod
    def format_value(val, indent_level=0):
        indent = "\t" * indent_level
        if isinstance(val, dict):
            if not val: return "{}"
            items = ["{"]
            for k, v in val.items():
                formatted_v = VCMIJSONFormatter.format_value(v, indent_level + 1)
                items.append(f'{indent}\t"{k}": {formatted_v},')
            if len(items) > 1: items[-1] = items[-1].rstrip(',') 
            items.append(f'{indent}}}')
            if len(items) < 4 and len(str(items)) < 100: 
                return "{" + ", ".join([f'"{k}": {VCMIJSONFormatter.format_value(v, 0)}' for k,v in val.items()]) + "}"
            return "\n".join(items)
        elif isinstance(val, list):
            if not val: return "[]"
            if all(isinstance(x, (str, int, float, bool)) for x in val):
                formatted_list = ", ".join([VCMIJSONFormatter.format_value(x, 0) for x in val])
                return f'[ {formatted_list} ]'
            else:
                items = ["["]
                for x in val: items.append(f'{indent}\t{VCMIJSONFormatter.format_value(x, indent_level + 1)},')
                if len(items) > 1: items[-1] = items[-1].rstrip(',')
                items.append(f'{indent}]')
                return "\n".join(items)
        elif isinstance(val, str): return json.dumps(val) 
        elif isinstance(val, bool): return "true" if val else "false"
        else: return str(val)

    @staticmethod
    def format(data_dict):
        output = ["{"]
        for creature_id, c_data in data_dict.items():
            output.append(f'\t"{creature_id}": {{')
            fields = []
            
            s_name = json.dumps(c_data.get("name", {}).get("singular", ""))
            p_name = json.dumps(c_data.get("name", {}).get("plural", ""))
            fields.append(f'\t\t"name": {{ "singular": {s_name}, "plural": {p_name} }}')
            
            for f in ["advMapAmount", "faction", "special", "level", "attack", "defense", "hitPoints", "speed", "shots", "spellPoints", "growth", "horde", "fightValue", "aiValue", "doubleWide", "cost"]:
                if f in c_data: fields.append(f'\t\t"{f}": {VCMIJSONFormatter.format_value(c_data[f])}')
                    
            if "damage" in c_data:
                d = c_data["damage"]
                fields.append(f'\t\t"damage": {{ "min": {d["min"]}, "max": {d["max"]} }}')
            if "upgrades" in c_data and c_data["upgrades"]:
                 fields.append(f'\t\t"upgrades": {VCMIJSONFormatter.format_value(c_data["upgrades"])}')
            if "graphics" in c_data:
                fields.append(f'\t\t"graphics": {VCMIJSONFormatter.format_value(c_data["graphics"], 2)}')
            if "sound" in c_data and c_data["sound"]:
                fields.append(f'\t\t"sound": {VCMIJSONFormatter.format_value(c_data["sound"], 2)}')
            if "abilities" in c_data and c_data["abilities"]:
                ab_lines = ['{']
                ab_keys = list(c_data["abilities"].keys())
                for i, k in enumerate(ab_keys):
                    v = c_data["abilities"][k]
                    comma = "," if i < len(ab_keys) - 1 else ""
                    ab_lines.append(f'\t\t\t"{k}": {VCMIJSONFormatter.format_value(v, 3)}{comma}')
                ab_lines.append('\t\t}')
                fields.append(f'\t\t"abilities": ' + "\n".join(ab_lines))

            output.append(",\n\n".join(fields))
            output.append('\t}')
        output.append("}")
        return "\n".join(output)

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
        
        if not hasattr(self.app, 'dynamic_abilities'): self.app.dynamic_abilities = []
            
        self.bonus_list = []
        self.bonus_hints = {}
        self.identifiers_lib = {}
        
        self.load_bonus_library()
        self.load_identifiers_library()
        self.build_ui()

    def prompt_reset(self):
        x = self.parent.winfo_pointerx() + 15
        y = self.parent.winfo_pointery() + 15
        top = tk.Toplevel(self.parent)
        top.title("Reset")
        top.geometry(f"+{x}+{y}")
        top.transient(self.parent.winfo_toplevel())
        top.grab_set()
        
        ttk.Label(top, text="⚠️ Are you sure you want to clear all fields?", font=("Arial", 10, "bold")).pack(padx=20, pady=15)
        btn_f = ttk.Frame(top)
        btn_f.pack(pady=(0, 15))
        
        def do_reset():
            self.execute_reset(); top.destroy()
            
        ttk.Button(btn_f, text="Confirm", command=do_reset).pack(side="left", padx=10)
        ttk.Button(btn_f, text="Cancel", command=top.destroy).pack(side="left", padx=10)

    def execute_reset(self):
        for entry in self.app.entries.values():
            if hasattr(entry, 'set_value'): entry.set_value("")
                
        if "doubleWide" in self.app.vars: self.app.vars["doubleWide"].set(False)
        if "special" in self.app.vars: self.app.vars["special"].set(False)
        if "movement" in self.app.vars: self.app.vars["movement"].set("Ground")
        if "is_upgraded" in self.app.vars: 
            self.app.vars["is_upgraded"].set(False)
            self.btn_upgrade.config(text="unupgraded")
            
        self.update_movement_icon()
        self.adv_map_manual_override = False
        self.app.entries["adv_min"].config(state="disabled")
        self.app.entries["adv_max"].config(state="disabled")
        self.btn_edit_adv.config(state="normal")
        self.app.entries["adv_min"].set_value("")
        self.app.entries["adv_max"].set_value("")
        
        for k in ["attack", "defend", "killed", "shoot", "move", "wince", "startMoving", "endMoving"]:
            p_key = f"snd_{k}_path"
            if p_key in self.app.vars: self.app.vars[p_key].set("")
        
        self.app.dynamic_abilities.clear()
        self.refresh_active_abilities()
        
        self._set_portrait_image("iconLarge", os.path.join(self.app.res_dir, "prtLarge.png"), "prtLarge.png")
        self._set_portrait_image("iconSmall", os.path.join(self.app.res_dir, "prtSmall.png"), "prtSmall.png")

    def load_bonus_library(self):
        try:
            lib_path = os.path.join(self.app.current_dir, "library-bonusSystem.json")
            if not os.path.exists(lib_path): return
            with open(lib_path, "r", encoding="utf-8") as f: lib_data = json.load(f)
            
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
                if cat.lower().replace(" ", "_") in target_categories: add_bonuses_from_dict(bonuses)
            
            if not self.bonus_list:
                for cat, bonuses in categories_container.items():
                    if "creature" in cat.lower().replace(" ", "_") and cat not in ["Base_Format", "Enums", "BonusFormat_Complex_Examples"]:
                        add_bonuses_from_dict(bonuses)

            self.bonus_list = sorted(list(set(self.bonus_list)))
                
        except Exception as e: logging.error(f"Error loading bonus library: {e}", exc_info=True)

    def load_identifiers_library(self):
        try:
            lib_path = os.path.join(self.app.current_dir, "library-identifiers.json")
            if not os.path.exists(lib_path): return
            with open(lib_path, "r", encoding="utf-8") as f: self.identifiers_lib = json.load(f)
        except Exception as e: logging.error(f"Error loading identifiers library: {e}", exc_info=True)

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
                widget.delete(0, tk.END); widget.insert(0, new_val)

    def toggle_upgrade(self):
        current = self.app.vars["is_upgraded"].get()
        self.app.vars["is_upgraded"].set(not current)
        self.btn_upgrade.config(text="upgraded" if self.app.vars["is_upgraded"].get() else "unupgraded")
        self.update_adv_map_from_level()

    def update_adv_map_from_level(self, event=None):
        if getattr(self, 'adv_map_manual_override', False): return
        level_str = self.app.entries["level"].get_real_value().strip()
        if not level_str or not level_str.isdigit(): return
        
        lvl_num = int(level_str)
        is_upg = self.app.vars["is_upgraded"].get()
        key = f"{lvl_num}+" if is_upg else str(lvl_num)
        
        mapping = {
            "1": ("20", "50"), "1+": ("20", "30"), "2": ("16", "30"), "2+": ("16", "25"),
            "3": ("12", "25"), "3+": ("12", "20"), "4": ("10", "20"), "4+": ("10", "16"),
            "5": ("8", "16"),  "5+": ("8", "12"),  "6": ("5", "12"),  "6+": ("5", "10"),
            "7": ("4", "10"),  "7+": ("3", "8"),
        }
        
        if key in mapping: min_v, max_v = mapping[key]
        elif lvl_num >= 8: min_v, max_v = ("1", "3")
        else: return
            
        self.app.entries["adv_min"].set_value(min_v); self.app.entries["adv_max"].set_value(max_v)

    def unlock_adv_map(self):
        self.adv_map_manual_override = True
        self.app.entries["adv_min"].config(state="normal"); self.app.entries["adv_max"].config(state="normal")
        self.btn_edit_adv.config(state="disabled")

    def build_ui(self):
        header_frame = tk.Frame(self.parent, bg="#dddddd", height=45)
        header_frame.pack(fill="x"); header_frame.pack_propagate(False)
        
        btn_reset = tk.Button(header_frame, text="🔄 Reset All", bg="#ffcccc", cursor="hand2", command=self.prompt_reset)
        btn_reset.place(relx=0.02, rely=0.5, anchor="w")
        Tooltip(btn_reset, "Clear all fields and reset to default.")
        tk.Label(header_frame, text="VCMI CREATURE CONFIGURATION", font=("Arial", 14, "bold"), bg="#dddddd").place(relx=0.5, rely=0.5, anchor="center")

        content_frame = ttk.Frame(self.parent)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        content_frame.columnconfigure(0, weight=55); content_frame.columnconfigure(1, weight=45); content_frame.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(content_frame)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left_panel.columnconfigure(0, weight=1); left_panel.columnconfigure(1, weight=1)
        left_panel.rowconfigure(0, weight=0); left_panel.rowconfigure(1, weight=0); left_panel.rowconfigure(2, weight=1) 
        
        right_panel = ttk.Frame(content_frame)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_panel.columnconfigure(0, weight=1); right_panel.rowconfigure(3, weight=1) 

        # =========================================================================
        # 1. GENERAL INFO
        # =========================================================================
        info = ttk.LabelFrame(left_panel, text="General information & costs")
        info.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        info.columnconfigure(0, minsize=140, weight=0); info.columnconfigure(1, minsize=220, weight=0); info.columnconfigure(2, minsize=140, weight=0); info.columnconfigure(3, weight=1)

        id_entry = self.create_smart_field(info, "Unique ID:", "id", "core:pikeman", row=0, col=0, padding=4, tooltip="Unique technical identifier for the game engine.")
        id_entry.bind("<FocusOut>", self.enforce_camel_case_on_widget, add="+")
        self.create_smart_field(info, "Name (Singular):", "name_singular", "Peasant", row=1, col=0, padding=4)
        self.create_smart_field(info, "Name (Plural):", "name_plural", "Peasants", row=2, col=0, padding=4)
        
        faction_entry = self.create_smart_field(info, "Faction ID:", "faction", "castle", row=3, col=0, padding=4)
        faction_entry.bind("<FocusOut>", self.enforce_camel_case_on_widget, add="+")
        
        lbl_lvl = ttk.Label(info, text=" Level:")
        if "level" in self.app.ui_icons: lbl_lvl.config(image=self.app.ui_icons["level"], compound="left")
        lbl_lvl.grid(row=4, column=0, sticky='w', padx=5, pady=4)
        
        lvl_frame = ttk.Frame(info); lvl_frame.grid(row=4, column=1, sticky='w', padx=5, pady=4)
        lvl_entry = SmartEntry(lvl_frame, "1", is_numeric=True, width=5); lvl_entry.pack(side="left")
        self.app.entries["level"] = lvl_entry
        self.app.vars["is_upgraded"] = tk.BooleanVar(value=False)
        self.btn_upgrade = tk.Button(lvl_frame, text="unupgraded", width=10, command=self.toggle_upgrade, pady=0, bd=1, bg="#f0f0f0")
        self.btn_upgrade.pack(side="left", padx=(5,0))
        lvl_entry.bind("<FocusOut>", self.update_adv_map_from_level, add="+"); lvl_entry.bind("<Return>", self.update_adv_map_from_level, add="+")
        
        upgrades_entry = self.create_smart_field(info, "Upgrades To (ID):", "upgrades", "core:marksman", row=5, col=0, padding=4)
        upgrades_entry.bind("<FocusOut>", self.enforce_camel_case_on_widget, add="+")

        # Dynamic loop for costs
        costs = [
            ("Gold", "cost_gold", "gold"), ("Wood", "cost_wood", "wood"), ("Ore", "cost_ore", "ore"), 
            ("Mercury", "cost_mercury", "mercury"), ("Sulfur", "cost_sulfur", "sulfur"), 
            ("Crystal", "cost_crystal", "crystal"), ("Gems", "cost_gems", "gems")
        ]
        for i, (label, key, icon) in enumerate(costs):
            self.create_smart_field(info, f"{label}:", key, "0", row=i, col=2, width=8, is_numeric=True, icon_key=icon, padding=4)

        # =========================================================================
        # 2. STATISTICS & DATA
        # =========================================================================
        stats = ttk.LabelFrame(left_panel, text="Statistics & data")
        stats.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        stats.columnconfigure(0, minsize=140, weight=0); stats.columnconfigure(1, minsize=220, weight=0); stats.columnconfigure(2, minsize=140, weight=0); stats.columnconfigure(3, weight=1)

        self.create_smart_field(stats, "Attack:", "attack", "5", row=0, col=0, is_numeric=True, icon_key="attack")
        self.create_smart_field(stats, "Defense:", "defense", "5", row=1, col=0, is_numeric=True, icon_key="defense")
        
        lbl_d = ttk.Label(stats, text=" Damage:")
        if "damage" in self.app.ui_icons: lbl_d.config(image=self.app.ui_icons["damage"], compound="left")
        lbl_d.grid(row=2, column=0, sticky='w', padx=5, pady=2)
        df = ttk.Frame(stats); df.grid(row=2, column=1, sticky='w', padx=5, pady=2)
        self.app.entries["dmg_min"] = SmartEntry(df, "min", True, 8); self.app.entries["dmg_min"].pack(side="left", padx=(0,5))
        self.app.entries["dmg_max"] = SmartEntry(df, "max", True, 8); self.app.entries["dmg_max"].pack(side="left")

        self.create_smart_field(stats, "Health:", "hitPoints", "10", row=3, col=0, is_numeric=True, icon_key="health")
        self.create_smart_field(stats, "Speed:", "speed", "5", row=4, col=0, is_numeric=True, icon_key="speed")
        self.create_smart_field(stats, "Growth:", "growth", "10", row=5, col=0, is_numeric=True, icon_key="growth")

        self.lbl_mov_type = ttk.Label(stats, text=" Movement Type:")
        if "mov_ground" in self.app.ui_icons: self.lbl_mov_type.config(image=self.app.ui_icons["mov_ground"], compound="left")
        self.lbl_mov_type.grid(row=6, column=0, sticky='w', padx=5, pady=2)
        mf = ttk.Frame(stats); mf.grid(row=6, column=1, sticky='w')
        self.app.vars["movement"] = tk.StringVar(value="Ground")
        ttk.Radiobutton(mf, text="Ground", variable=self.app.vars["movement"], value="Ground", command=self.update_movement_icon).pack(side="left")
        ttk.Radiobutton(mf, text="Fly", variable=self.app.vars["movement"], value="Fly", command=self.update_movement_icon).pack(side="left")
        ttk.Radiobutton(mf, text="Teleport", variable=self.app.vars["movement"], value="Teleport", command=self.update_movement_icon).pack(side="left")

        self.create_smart_field(stats, "Shots:", "shots", "0", row=0, col=2, is_numeric=True, icon_key="shots")
        self.create_smart_field(stats, "Spell pts:", "spellPoints", "0", row=1, col=2, is_numeric=True, icon_key="spellPoints")
        self.create_smart_field(stats, "AI Value:", "aiValue", "100", row=2, col=2, is_numeric=True, icon_key="aiValue")
        self.create_smart_field(stats, "Horde Bonus:", "horde", "0", row=3, col=2, is_numeric=True, icon_key="horde")

        lbl_adv = ttk.Label(stats, text=" Adv. Map amt:")
        if "advMap" in self.app.ui_icons: lbl_adv.config(image=self.app.ui_icons["advMap"], compound="left")
        lbl_adv.grid(row=4, column=2, sticky='w', padx=5, pady=2)
        amf = ttk.Frame(stats); amf.grid(row=4, column=3, sticky='w', padx=5, pady=2)
        self.app.entries["adv_min"] = SmartTkEntry(amf, "min", True, 6); self.app.entries["adv_min"].pack(side="left", padx=(0,2))
        self.app.entries["adv_max"] = SmartTkEntry(amf, "max", True, 6); self.app.entries["adv_max"].pack(side="left", padx=(0,5))
        self.app.entries["adv_min"].config(state="disabled"); self.app.entries["adv_max"].config(state="disabled")
        self.btn_edit_adv = tk.Button(amf, text="Edit", width=4, command=self.unlock_adv_map, pady=0, bd=1, bg="#f0f0f0")
        self.btn_edit_adv.pack(side="left")

        lbl_dw = ttk.Label(stats, text=" Double Wide:")
        if "doubleWide" in self.app.ui_icons: lbl_dw.config(image=self.app.ui_icons["doubleWide"], compound="left")
        lbl_dw.grid(row=5, column=2, sticky='w', padx=5, pady=2)
        dw_frame = ttk.Frame(stats); dw_frame.grid(row=5, column=3, sticky='w')
        self.app.vars["doubleWide"] = tk.BooleanVar(value=False)
        ttk.Radiobutton(dw_frame, text="Yes", variable=self.app.vars["doubleWide"], value=True).pack(side="left")
        ttk.Radiobutton(dw_frame, text="No", variable=self.app.vars["doubleWide"], value=False).pack(side="left")

        lbl_sp = ttk.Label(stats, text=" Is Special:")
        if "special" in self.app.ui_icons: lbl_sp.config(image=self.app.ui_icons["special"], compound="left")
        lbl_sp.grid(row=6, column=2, sticky='w', padx=5, pady=2)
        sp_frame = ttk.Frame(stats); sp_frame.grid(row=6, column=3, sticky='w')
        self.app.vars["special"] = tk.BooleanVar(value=False)
        ttk.Radiobutton(sp_frame, text="Yes", variable=self.app.vars["special"], value=True).pack(side="left")
        ttk.Radiobutton(sp_frame, text="No", variable=self.app.vars["special"], value=False).pack(side="left")

        # =========================================================================
        # 3. SPECIAL ABILITIES
        # =========================================================================
        self.special_frame = ttk.LabelFrame(left_panel, text="Special abilities")
        self.special_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        self.special_frame.rowconfigure(0, weight=1); self.special_frame.columnconfigure(0, weight=55); self.special_frame.columnconfigure(1, weight=45)
        
        lib_frame = ttk.Frame(self.special_frame); lib_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.lib_filter_var = tk.StringVar(); self.lib_filter_var.trace_add("write", self.populate_library_list)
        search_f = ttk.Frame(lib_frame); search_f.pack(fill="x", pady=(0, 5))
        ttk.Label(search_f, text="🔍").pack(side="left")
        ttk.Entry(search_f, textvariable=self.lib_filter_var).pack(side="left", fill="x", expand=True, padx=(2,0))
        
        style = ttk.Style()
        style.configure("Compact.Treeview", rowheight=18)
        self.lib_tree = ttk.Treeview(lib_frame, columns=("add", "name"), show="headings", style="Compact.Treeview")
        self.lib_tree.heading("add", text="➕"); self.lib_tree.column("add", width=35, stretch=False, anchor="center")
        self.lib_tree.heading("name", text="Bonus Library"); self.lib_tree.column("name", anchor="w")
        lib_scroll = tk.Scrollbar(lib_frame, orient="vertical", command=self.lib_tree.yview, width=24)
        self.lib_tree.configure(yscrollcommand=lib_scroll.set)
        self.lib_tree.pack(side="left", fill="both", expand=True); lib_scroll.pack(side="right", fill="y")
        self.lib_tree.bind("<ButtonRelease-1>", self.on_library_click); self.lib_tree.bind("<Double-Button-1>", self.on_lib_double_click); self.lib_tree.bind("<Return>", self.on_lib_return)
        
        act_frame = ttk.LabelFrame(self.special_frame, text="Active Abilities"); act_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        act_top_f = ttk.Frame(act_frame); act_top_f.pack(fill="x", padx=5, pady=(2, 0))
        self.btn_edit_lib = tk.Button(act_top_f, text="Edit", width=4, command=self.edit_selected_library, pady=0, bd=1, bg="#f0f0f0")
        self.btn_edit_lib.pack(side="right")
        self.act_canvas = tk.Canvas(act_frame, highlightthickness=0)
        act_scroll = tk.Scrollbar(act_frame, orient="vertical", command=self.act_canvas.yview, width=24)
        self.act_scrollable_frame = ttk.Frame(self.act_canvas)
        self.act_scrollable_frame.bind("<Configure>", lambda e: self.act_canvas.configure(scrollregion=self.act_canvas.bbox("all")))
        self.act_canvas.create_window((0, 0), window=self.act_scrollable_frame, anchor="nw", width=self.act_canvas.winfo_width())
        self.act_canvas.bind('<Configure>', lambda e: self.act_canvas.itemconfig(self.act_canvas.find_withtag("all")[0], width=e.width))
        self.act_canvas.configure(yscrollcommand=act_scroll.set)
        self.act_canvas.pack(side="left", fill="both", expand=True, pady=(5,0)); act_scroll.pack(side="right", fill="y", pady=(5,0))
        
        self.load_default_ability_icon()
        self.populate_library_list()
        self.refresh_active_abilities()

        # =========================================================================
        # 4. RIGHT PANEL (ASSETS & EXPORT)
        # =========================================================================
        top_assets = ttk.Frame(right_panel)
        top_assets.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        top_assets.columnconfigure(0, weight=1); top_assets.columnconfigure(1, weight=1)

        port = ttk.LabelFrame(top_assets, text="Portraits (.png, .bmp)")
        port.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        port_inner = ttk.Frame(port); port_inner.pack(expand=True)
        self.create_clickable_portrait(port_inner, "iconLarge", "IconLarge", "58x64", "prtLarge.png", 0)
        self.create_clickable_portrait(port_inner, "iconSmall", "IconSmall", "32x32", "prtSmall.png", 1)

        gfx = ttk.LabelFrame(top_assets, text="Animations")
        gfx.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
        gfx_inner = ttk.Frame(gfx); gfx_inner.pack(expand=True, anchor="w", padx=15)
        self.create_smart_field(gfx_inner, "Battle Anim:", "anim_battle", "creature.def", 0, 0, width=15, padding=8)
        self.create_smart_field(gfx_inner, "Map Anim:", "anim_map", "creature_map.def", 1, 0, width=15, padding=8)
        self.create_smart_field(gfx_inner, "Projectile:", "anim_missile", "projectile.def", 2, 0, width=15, padding=8)

        audio = ttk.LabelFrame(right_panel, text="Audio (.wav, .ogg)")
        audio.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        audio_inner = ttk.Frame(audio); audio_inner.pack(expand=True, pady=10)
        
        # Dynamic loop for audio
        snds_layout = [
            ("attack", 0, 0), ("defend", 1, 0), ("killed", 2, 0),
            ("shoot", 0, 1), ("move", 1, 1), ("wince", 2, 1),
            ("startMoving", 0, 2), ("endMoving", 1, 2)
        ]
        for s, r, col_idx in snds_layout:
            self.create_compact_audio(audio_inner, f"{s.title()}:", f"snd_{s}", f"{s}.wav", r, col_idx * 4)
            
        audio_inner.columnconfigure(3, minsize=40); audio_inner.columnconfigure(7, minsize=40)

        # JSON Export Builder
        self.export_container = ttk.Frame(right_panel)
        self.export_container.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)
        self.build_export_section(self.export_container)

    def load_default_ability_icon(self):
        try:
            icon_path = os.path.join(self.app.res_dir, "ability", "_ability.png")
            if os.path.exists(icon_path):
                img = Image.open(icon_path).convert("RGBA").resize((24, 24), Image.LANCZOS)
            else:
                img = Image.new('RGBA', (24, 24), color=(200, 200, 200, 255))
            self.default_ability_img = ImageTk.PhotoImage(img)
        except Exception:
            self.default_ability_img = ImageTk.PhotoImage(Image.new('RGBA', (24, 24), color=(200, 200, 200, 255)))

    def populate_library_list(self, *args):
        for item in self.lib_tree.get_children(): self.lib_tree.delete(item)
        q = self.lib_filter_var.get().lower()
        for b in self.bonus_list:
            if q in b.lower(): self.lib_tree.insert("", tk.END, values=("➕", b))

    def on_library_click(self, event):
        region = self.lib_tree.identify_region(event.x, event.y)
        if region != "cell": return
        column = self.lib_tree.identify_column(event.x)
        if column == "#1":
            item = self.lib_tree.identify_row(event.y)
            if item:
                self.add_ability(key_name=self.lib_tree.item(item, "values")[1])

    def on_lib_double_click(self, event):
        region = self.lib_tree.identify_region(event.x, event.y)
        if region != "cell" or self.lib_tree.identify_column(event.x) == "#1": return 
        sel = self.lib_tree.selection()
        if sel: self.add_ability(key_name=self.lib_tree.item(sel[0], "values")[1])

    def on_lib_return(self, event):
        sel = self.lib_tree.selection()
        if sel: self.add_ability(key_name=self.lib_tree.item(sel[0], "values")[1])

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
        self.add_ability(key_name=ab["key_name"] + "Copy", full_payload=copy.deepcopy(ab["full_payload"]))

    def refresh_active_abilities(self):
        for widget in self.act_scrollable_frame.winfo_children(): widget.destroy()
        for i, ab in enumerate(self.app.dynamic_abilities):
            f = tk.Frame(self.act_scrollable_frame, cursor="hand2", bg="#ffffff", bd=1, relief="solid")
            f.pack(fill="x", pady=1, padx=2)
            
            lbl_del = tk.Label(f, text="❌", font=("Arial", 9), bg="#ffffff", fg="#cc0000", cursor="hand2")
            lbl_del.pack(side="right", padx=8)
            tk.Label(f, image=self.default_ability_img, bg="#ffffff").pack(side="left", padx=2, pady=1)
            lbl_name = tk.Label(f, text=ab["key_name"], font=("Arial", 9, "bold"), bg="#ffffff")
            lbl_name.pack(side="left", padx=(5, 0))
            
            payload = ab.get("full_payload", {})
            params = [f"{key}: {v}" for key in ["type", "subtype", "val", "addInfo"] if (v := str(payload.get(key, ""))) and not is_placeholder_hint(v)]
            if any(k not in ["type", "subtype", "val", "addInfo", "description"] and payload[k] for k in payload): params.append("...")
            
            lbl_params = None
            if params:
                lbl_params = tk.Label(f, text=f"  ({', '.join(params)})", font=("Arial", 8, "italic"), bg="#ffffff", fg="#555555", anchor="w")
                lbl_params.pack(side="left", padx=(0, 5), fill="x", expand=True)
                
            def on_enter(e, frm=f, txt1=lbl_name, txt2=lbl_params, ldel=lbl_del):
                for w in (frm, txt1, txt2, ldel):
                    if w: w.config(bg="#d9e8f5")
            def on_leave(e, frm=f, txt1=lbl_name, txt2=lbl_params, ldel=lbl_del):
                for w in (frm, txt1, txt2, ldel):
                    if w: w.config(bg="#ffffff")

            for w in (f, lbl_name) + ((lbl_params,) if lbl_params else ()):
                w.bind("<Double-Button-1>", lambda e, idx=i: self.open_edit_popup(idx))
                w.bind("<Button-3>", lambda e, idx=i: self.show_context_menu(e, idx)) 
                w.bind("<Enter>", on_enter); w.bind("<Leave>", on_leave)
                
            lbl_del.bind("<Button-1>", lambda e, idx=i: self.delete_ability(idx))
            lbl_del.bind("<Enter>", on_enter); lbl_del.bind("<Leave>", on_leave)
                
        self.act_scrollable_frame.update_idletasks()
        self.act_canvas.configure(scrollregion=self.act_canvas.bbox("all"))

    def add_ability(self, key_name=None, full_payload=None):
        if not key_name: return
        key_name = to_camel_case(key_name)
        if full_payload is None:
            hint_key = key_name if key_name in self.bonus_hints else next((k for k in self.bonus_hints if to_camel_case(k) == key_name), key_name)
            full_payload = copy.deepcopy(self.bonus_hints.get(hint_key, {"type": "", "subtype": "", "val": ""}))
        
        ability_obj = {"key_name": key_name, "full_payload": full_payload}
        ability_obj["key_entry"] = ProxyEntry(ability_obj)
        self.app.dynamic_abilities.append(ability_obj)
        self.refresh_active_abilities()

    def open_id_search(self, target_entry, hint_text):
        if not self.identifiers_lib:
            messagebox.showwarning("Missing Library", "The 'library-identifiers.json' library could not be loaded.")
            return
        top = tk.Toplevel(self.parent.winfo_toplevel()); top.title("Search VCMI Identifiers")
        top.geometry(f"550x400+{top.winfo_pointerx() + 15}+{top.winfo_pointery() + 15}")
        top.transient(self.parent.winfo_toplevel()); top.grab_set()
        
        hint_lower = str(hint_text).lower()
        preferred_cat = "combatSpells" if "spell" in hint_lower else "creatures" if "creature" in hint_lower else "factions" if "faction" in hint_lower else "skills" if "skill" in hint_lower else "resources" if "resource" in hint_lower else "artifacts" if "artifact" in hint_lower else "heroes" if "hero" in hint_lower else "All"
        
        filter_var = tk.StringVar()
        search_f = ttk.Frame(top, padding=5); search_f.pack(fill="x")
        ttk.Label(search_f, text="🔍").pack(side="left")
        cat_var = tk.StringVar()
        cats = ["All"] + list(self.identifiers_lib.keys())
        cat_cb = ttk.Combobox(search_f, textvariable=cat_var, values=cats, state="readonly", width=15)
        cat_cb.set(preferred_cat if preferred_cat in cats else "All")
        cat_cb.pack(side="left", padx=5)
        ttk.Entry(search_f, textvariable=filter_var).pack(side="left", fill="x", expand=True)
        
        tree_f = ttk.Frame(top, padding=5); tree_f.pack(fill="both", expand=True)
        cols = ("id", "name", "desc")
        tree = ttk.Treeview(tree_f, columns=cols, show="headings", selectmode="browse")
        tree.heading("id", text="Identifier"); tree.heading("name", text="Name"); tree.heading("desc", text="Description")
        tree.column("id", width=180); tree.column("name", width=120); tree.column("desc", width=200)
        
        scroll = tk.Scrollbar(tree_f, orient="vertical", command=tree.yview, width=24)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        
        def populate(*args):
            tree.delete(*tree.get_children())
            q, selected_cat = filter_var.get().lower(), cat_var.get()
            cats_to_show = self.identifiers_lib.keys() if selected_cat == "All" else [selected_cat]
            for cat in cats_to_show:
                if cat not in self.identifiers_lib: continue
                for item_id, item_data in self.identifiers_lib[cat].items():
                    name = item_data.get("name", ""); desc = item_data.get("description", "")
                    if q in item_id.lower() or q in name.lower() or q in desc.lower():
                        tree.insert("", tk.END, values=(item_id, name, desc))
                        
        filter_var.trace_add("write", populate); cat_cb.bind("<<ComboboxSelected>>", lambda e: populate()); populate()
        
        def confirm(evt=None):
            if sel := tree.selection():
                target_entry.set_value(tree.item(sel[0], "values")[0]) 
                top.destroy()
                
        tree.bind("<Double-Button-1>", confirm); tree.bind("<Return>", confirm)
        btn_f = ttk.Frame(top, padding=5); btn_f.pack(fill="x")
        ttk.Button(btn_f, text="Cancel", command=top.destroy).pack(side="right", padx=5)
        ttk.Button(btn_f, text="Select", command=confirm).pack(side="right", padx=5)

    def open_edit_popup(self, index):
        ab = self.app.dynamic_abilities[index]
        new_k = ab["key_name"]
        
        top = tk.Toplevel(self.parent.winfo_toplevel()); top.title(f"Edit Ability: {new_k}")
        x = self.special_frame.winfo_rootx() + 20; y = max(20, self.special_frame.winfo_rooty() - 320 - 10)
        top.transient(self.parent.winfo_toplevel()); top.grab_set()
        
        content = ttk.Frame(top, padding=15); content.pack(fill="both", expand=True)
        ttk.Label(content, text="Key Name:", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        key_var = tk.StringVar(value=new_k); key_entry = ttk.Entry(content, textvariable=key_var)
        key_entry.grid(row=0, column=1, sticky="ew", pady=5); key_entry.bind("<FocusOut>", self.enforce_camel_case_on_tk_entry)
        
        orig_hint = self.bonus_hints.get(new_k, {})
        
        def build_dynamic_field(field_name, row_idx, compact=False):
            ttk.Label(content, text=f"{field_name.capitalize()}:").grid(row=row_idx, column=0, sticky="w", pady=5)
            f = ttk.Frame(content); f.grid(row=row_idx, column=1, sticky="ew", pady=5)
            
            raw_val = str(ab["full_payload"].get(field_name, ""))
            ph_hint = orig_hint.get(field_name, f"{field_name.capitalize()}...")
            act_val = raw_val if not is_placeholder_hint(raw_val) else ""
            if act_val == "" and not is_placeholder_hint(ph_hint): ph_hint = raw_val if raw_val else f"{field_name.capitalize()}..."
                
            enum_match = re.search(r"enum\s*\((.*?)\)", str(ph_hint), re.IGNORECASE)
            int_match = re.search(r"integer\s*\[(-?\d+)\.\.(-?\d+)\]", str(ph_hint), re.IGNORECASE)
            is_percentage = "percent" in str(ph_hint).lower() or "%" in str(ph_hint)
            
            if enum_match:
                cb = ttk.Combobox(f, values=[v.strip(" '\"") for v in enum_match.group(1).split(",")])
                cb.pack(side="left", fill="x" if not compact else "none", expand=not compact)
                if compact: cb.config(width=15)
                if act_val: cb.set(act_val)
                cb.get_real_value = cb.get; Tooltip(cb, str(ph_hint))
                return cb
            elif int_match:
                min_v, max_v = int(int_match.group(1)), int(int_match.group(2))
                if min_v == 0 and max_v == 100: is_percentage = True
                if is_percentage:
                    se = SmartEntry(f, placeholder=str(ph_hint), is_numeric=True, width=15 if compact else 20)
                    se.pack(side="left", fill="x" if not compact else "none", expand=not compact); se.set_value(act_val)
                    ttk.Label(f, text="%").pack(side="left", padx=2)
                    def clamp_val(e, entry=se, mn=min_v, mx=max_v):
                        val = entry.get_real_value()
                        if val and (val.isdigit() or (val.startswith('-') and val[1:].isdigit())):
                            v = int(val)
                            if v < mn: entry.set_value(str(mn))
                            elif v > mx: entry.set_value(str(mx))
                    se.bind("<FocusOut>", clamp_val, add="+"); Tooltip(se, str(ph_hint))
                    return se
                else:
                    sb = ttk.Spinbox(f, from_=min_v, to=max_v, width=10 if compact else 20)
                    sb.pack(side="left", fill="x" if not compact else "none", expand=not compact)
                    if act_val: sb.set(act_val)
                    sb.get_real_value = sb.get; Tooltip(sb, str(ph_hint))
                    return sb
            else:
                se = SmartEntry(f, placeholder=str(ph_hint), is_numeric=is_percentage, width=15 if compact else 20)
                se.pack(side="left", fill="x" if not compact else "none", expand=not compact); se.set_value(act_val)
                if is_percentage: ttk.Label(f, text="%").pack(side="left", padx=2)
                elif "ID" in str(ph_hint):
                    btn = ttk.Button(f, text="🔍", width=3, command=lambda e=se, ht=ph_hint: self.open_id_search(e, ht))
                    btn.pack(side="right", padx=(2,0)); Tooltip(btn, "Search in VCMI Identifiers")
                Tooltip(se, str(ph_hint))
                return se

        type_entry = build_dynamic_field("type", 1)
        subtype_entry = build_dynamic_field("subtype", 2)
        val_entry = build_dynamic_field("val", 3, compact=False)
        addinfo_entry = build_dynamic_field("addInfo", 4) if "addInfo" in orig_hint else None
        
        top.geometry(f"420x{360 if addinfo_entry else 320}+{x}+{y}"); content.columnconfigure(1, weight=1)
        
        def apply_fields_to_ab():
            ab["key_name"] = key_entry.get()
            t_val, s_val, v_val = type_entry.get_real_value(), subtype_entry.get_real_value(), val_entry.get_real_value()
            
            ab["full_payload"]["type"] = t_val if t_val else ""
            if s_val: ab["full_payload"]["subtype"] = s_val
            else: ab["full_payload"].pop("subtype", None)
            if v_val: ab["full_payload"]["val"] = v_val
            else: ab["full_payload"].pop("val", None)
            
            if addinfo_entry:
                if a_val := addinfo_entry.get_real_value(): ab["full_payload"]["addInfo"] = a_val
                else: ab["full_payload"].pop("addInfo", None)
            
        def save_changes(): apply_fields_to_ab(); self.refresh_active_abilities(); top.destroy()
        def clone(): apply_fields_to_ab(); self.clone_ability(index); top.destroy()
        def delete(): self.delete_ability(index); top.destroy()
        def open_adv(): apply_fields_to_ab(); self.open_current_advanced_editor(index, top)
            
        btn_f = ttk.Frame(content)
        btn_f.grid(row=5 if addinfo_entry else 4, column=0, columnspan=2, pady=15, sticky="ew")
        ttk.Button(btn_f, text="⚙️ Adv. Modifiers", command=open_adv).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="📑 Clone", command=clone).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(btn_f, text="❌ Delete", command=delete).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(content, text="Save & Close", command=save_changes).grid(row=6 if addinfo_entry else 5, column=0, columnspan=2, pady=5, sticky="ew")

    def open_current_advanced_editor(self, index, parent_popup):
        ab = self.app.dynamic_abilities[index]
        top = tk.Toplevel(parent_popup); top.title(f"Advanced Bonus Editor - {ab['key_name']}")
        top.geometry(f"600x500+{self.special_frame.winfo_rootx() + 20}+{max(20, self.special_frame.winfo_rooty() - 510)}")
        top.transient(parent_popup); top.grab_set()
        
        ttk.Label(top, text="VCMI Bonus Payload Editor (JSON format)", font=("Arial", 9, "bold")).pack(fill="x", padx=10, pady=5)
        text_area = tk.Text(top, wrap="none", font=("Consolas", 10))
        scroll_y = ttk.Scrollbar(top, orient="vertical", command=text_area.yview)
        scroll_x = ttk.Scrollbar(top, orient="horizontal", command=text_area.xview)
        text_area.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.pack(side="right", fill="y"); scroll_x.pack(side="bottom", fill="x")
        text_area.pack(side="top", fill="both", expand=True, padx=10, pady=5)
        
        payload_copy = copy.deepcopy(ab["full_payload"])
        payload_copy.pop("description", None)
        text_area.insert("1.0", json.dumps(payload_copy, indent=4))
        
        def save_advanced_bonus():
            try:
                new_payload = json.loads(text_area.get("1.0", tk.END).strip())
                if "type" not in new_payload: messagebox.showwarning("Attention", "Le champ 'type' est requis !", parent=top)
                if "description" in ab["full_payload"]: new_payload["description"] = ab["full_payload"]["description"]
                ab["full_payload"] = new_payload
                self.refresh_active_abilities()
                top.destroy(); parent_popup.destroy()
            except json.JSONDecodeError as je: messagebox.showerror("Invalid JSON", f"Malformed JSON:\n{je}", parent=top)
            except Exception as e: messagebox.showerror("Error", str(e), parent=top)

        btn_frame = ttk.Frame(top); btn_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(btn_frame, text="Cancel", command=top.destroy).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Save & Apply", command=save_advanced_bonus).pack(side="right", padx=5)

    def create_clickable_portrait(self, parent, key, label, size_str, default_img, col, tooltip=None):
        f = ttk.Frame(parent); f.grid(row=0, column=col, padx=15, pady=10)
        lbl_w = ttk.Label(f, text=label, font=("Arial", 9, "bold")); lbl_w.pack(pady=(5, 5))
        img_lbl = tk.Label(f, cursor="hand2"); img_lbl.pack(pady=5)
        ttk.Label(f, text=size_str, font=("Arial", 8)).pack(pady=(0, 5))
        
        if tooltip: Tooltip(lbl_w, tooltip); Tooltip(img_lbl, tooltip)
        self.image_refs[key] = {"label": img_lbl, "img_tk_normal": None, "img_tk_dark": None}
        if key not in self.app.entries: self.app.entries[key] = DummyEntry(default_img)
        self._set_portrait_image(key, os.path.join(self.app.res_dir, default_img), default_img)
        
        img_lbl.bind("<Enter>", lambda e, k=key: self._on_portrait_hover(k, True))
        img_lbl.bind("<Leave>", lambda e, k=key: self._on_portrait_hover(k, False))
        img_lbl.bind("<Button-1>", lambda e, k=key: self.load_image_smart(k))

    def _set_portrait_image(self, key, path, filename=""):
        state = self.image_refs.get(key)
        if not state: return
        actual_path = path if os.path.exists(path) else os.path.join(self.app.res_dir, "prtSmall.png" if key == "iconSmall" else "prtLarge.png")
        if os.path.exists(actual_path):
            try:
                img = Image.open(actual_path).convert("RGBA")
                state["img_tk_normal"] = ImageTk.PhotoImage(img)
                state["img_tk_dark"] = ImageTk.PhotoImage(ImageEnhance.Brightness(img).enhance(0.4))
                state["label"].config(image=state["img_tk_normal"], text="")
            except: pass
        else: state["label"].config(image="", text="No Img", width=8, height=4)
        if filename: self.app.entries[key].set_value(filename)

    def _on_portrait_hover(self, key, entering):
        state = self.image_refs.get(key)
        if state and state.get("img_tk_dark"): state["label"].config(image=state["img_tk_dark"] if entering else state["img_tk_normal"])

    def load_image_smart(self, key):
        f = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.bmp;*.jpg")])
        if not f: return
        try:
            with Image.open(f) as img:
                img = img.convert("RGBA"); w, h = img.size
                target_key = "iconLarge" if (key == "iconSmall" and 56 <= w <= 60 and 62 <= h <= 66) else "iconSmall" if (key == "iconLarge" and 30 <= w <= 34 and 30 <= h <= 34) else key
                target_size = (58, 64) if target_key == "iconLarge" else (32, 32)
                
                if (w, h) != target_size:
                    img = ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS)
                    filename = f"cropped_{target_key}_{os.path.basename(f)}"
                    path_to_load = os.path.join(self.app.cache_dir, filename)
                    img.save(path_to_load, format="PNG")
                else: path_to_load, filename = f, os.path.basename(f)
            self._set_portrait_image(target_key, path_to_load, filename)
        except Exception as e: logging.error(f"Error loading image: {e}", exc_info=True)

    def create_compact_audio(self, p, lbl, key, ph, r, c, tooltip=None):
        l = ttk.Label(p, text=lbl, font=("Arial", 8)); l.grid(row=r, column=c, padx=(5,2), pady=8, sticky='e')
        e = SmartEntry(p, ph, width=13); e.grid(row=r, column=c+1, padx=2, pady=8)
        if tooltip: Tooltip(l, tooltip); Tooltip(e, tooltip)
        self.app.entries[key] = e; self.app.vars[key+"_path"] = tk.StringVar()
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
        key = "mov_fly" if val == "Fly" else "mov_teleport" if val == "Teleport" else "mov_ground"
        if key in self.app.ui_icons: self.lbl_mov_type.config(image=self.app.ui_icons[key])

    def build_export_section(self, parent):
        f = ttk.LabelFrame(parent, text="JSON Manager"); f.pack(side="top", fill="both", expand=True)
        b = ttk.Frame(f); b.pack(fill="x", pady=2)
        ttk.Button(b, text="Generate JSON", command=self.generate_json).pack(side="left", padx=5)
        ttk.Button(b, text="Save As...", command=self.save_json).pack(side="left", padx=5)
        ttk.Button(b, text="Load", command=self.load_json).pack(side="left", padx=5)
        ttk.Button(b, text="⤢", width=3, command=self.open_json_popup).pack(side="right", padx=5)
        self.json_text = tk.Text(f, height=8, font=("Consolas", 9)); self.json_text.pack(fill="both", expand=True, padx=5, pady=5)

    def open_json_popup(self):
        top = tk.Toplevel(self.parent.winfo_toplevel()); top.title("VCMI JSON Viewer")
        top.geometry(f"900x700+{self.parent.winfo_rootx() + 50}+{self.parent.winfo_rooty() + 50}")
        self.popup_text = tk.Text(top, wrap="none", font=("Consolas", 11))
        vsb = ttk.Scrollbar(top, orient="vertical", command=self.popup_text.yview); hsb = ttk.Scrollbar(top, orient="horizontal", command=self.popup_text.xview)
        self.popup_text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y"); hsb.pack(side="bottom", fill="x"); self.popup_text.pack(side="left", fill="both", expand=True)
        self.popup_text.insert("1.0", self.json_text.get("1.0", tk.END))
        self.popup_text.bind("<ButtonPress-2>", lambda e: self.popup_text.scan_mark(e.x, e.y)); self.popup_text.bind("<B2-Motion>", lambda e: self.popup_text.scan_dragto(e.x, e.y, gain=1))

    def load_json(self):
        f_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if not f_path: return
        try:
            with open(f_path, 'r', encoding='utf-8') as f: clean_data = re.sub(r'//.*', '', re.sub(r'/\*.*?\*/', '', f.read(), flags=re.DOTALL))
            data = json.loads(clean_data)
            if not isinstance(data, dict) or not data: raise ValueError("The file does not contain a root Creature object.")
            creature_id = list(data.keys())[0]; c_data = data[creature_id]
            if not isinstance(c_data, dict): raise ValueError("Creature data is corrupted.")
                
            def set_e(k, v):
                if k in self.app.entries: self.app.entries[k].set_value(str(v) if v is not None else "")
            def set_v(k, v):
                if k in self.app.vars: self.app.vars[k].set(v)
            
            set_e("id", creature_id); set_e("name_singular", c_data.get("name", {}).get("singular", ""))
            set_e("name_plural", c_data.get("name", {}).get("plural", "")); set_e("faction", c_data.get("faction", ""))
            set_e("level", c_data.get("level", "1"))
            
            cost = c_data.get("cost", {})
            for res in ["gold", "wood", "ore", "mercury", "sulfur", "crystal", "gems"]: set_e(f"cost_{res}", cost.get(res, "0"))
                
            for stat in ["attack", "defense", "hitPoints", "speed", "shots", "spellPoints", "growth", "horde", "aiValue"]: set_e(stat, c_data.get(stat, "0" if stat in ["shots","spellPoints","horde"] else ("10" if stat in ["hitPoints","growth"] else ("100" if stat=="aiValue" else "5"))))
            
            dmg = c_data.get("damage", {}); set_e("dmg_min", dmg.get("min", "")); set_e("dmg_max", dmg.get("max", ""))
            adv = c_data.get("advMapAmount", {}); set_e("adv_min", adv.get("min", "")); set_e("adv_max", adv.get("max", ""))
            
            set_v("doubleWide", bool(c_data.get("doubleWide", False))); set_v("special", bool(c_data.get("special", False)))
            
            sounds = c_data.get("sound", {})
            for s in ["attack", "defend", "killed", "move", "shoot", "wince", "startMoving", "endMoving"]: set_e(f"snd_{s}", sounds.get(s, ""))
                
            gfx = c_data.get("graphics", {})
            set_e("anim_battle", gfx.get("animation", "")); set_e("anim_map", gfx.get("map", ""))
            if (p_small := gfx.get("iconSmall", "")): self._set_portrait_image("iconSmall", os.path.join(self.app.res_dir, p_small), p_small)
            if (p_large := gfx.get("iconLarge", "")): self._set_portrait_image("iconLarge", os.path.join(self.app.res_dir, p_large), p_large)
            set_e("anim_missile", gfx.get("missile", {}).get("animation", "") if isinstance(gfx.get("missile"), dict) else "")
            
            upgrades = c_data.get("upgrades", [])
            set_e("upgrades", upgrades[0] if isinstance(upgrades, list) and upgrades else "")
                
            self.app.dynamic_abilities.clear()
            movement_set = False
            for ak, av in c_data.get("abilities", {}).items():
                if isinstance(av, dict):
                    t, s = av.get("type", ""), av.get("subtype", "")
                    if t == "FLYING" and s in ["movementFlying", "movementTeleporting"]:
                        set_v("movement", "Fly" if s == "movementFlying" else "Teleport")
                        movement_set = True
                        continue
                    elif t == "SHOOTER": continue 
                    self.add_ability(key_name=ak, full_payload=av)
            
            if not movement_set: set_v("movement", "Ground")
            self.update_movement_icon()
            self.generate_json()
            messagebox.showinfo("Success", f"Creature '{creature_id}' successfully loaded.")
            
        except Exception as e: messagebox.showerror("Error", f"Failed to load file.\n\n{e}")

    def generate_json(self):
        try:
            def g(k): return self.app.entries[k].get_real_value().strip() if k in self.app.entries else ""
            def gi(k): return int(v) if (v := g(k)).lstrip('-').isdigit() else 0
            
            ai_val = gi("aiValue")
            data = {
                "name": {"singular": g("name_singular"), "plural": g("name_plural")},
                "faction": g("faction"), "level": int(g("level") or 1),
                "attack": gi("attack"), "defense": gi("defense"),
                "damage": {"min": gi("dmg_min"), "max": gi("dmg_max")},
                "hitPoints": gi("hitPoints"), "speed": gi("speed"), "growth": gi("growth"), 
                "fightValue": ai_val, "aiValue": ai_val, "cost": {}, "sound": {}, "graphics": {}, "abilities": {} 
            }
            
            if (adv_min := gi("adv_min")) > 0 or (adv_max := gi("adv_max")) > 0: data["advMapAmount"] = {"min": adv_min, "max": adv_max}
            if (horde := gi("horde")) > 0: data["horde"] = horde
            if (shots := gi("shots")) > 0: data["shots"] = shots
            if (spell_points := gi("spellPoints")) > 0: data["spellPoints"] = spell_points
            if self.app.vars.get("special", tk.BooleanVar()).get(): data["special"] = True
            data["doubleWide"] = self.app.vars.get("doubleWide", tk.BooleanVar()).get()
            
            for res in ["gold","wood","ore","mercury","sulfur","crystal","gems"]:
                if (v := gi(f"cost_{res}")) > 0: data["cost"][res] = v
            for s in ["attack","defend","killed","move","shoot","wince", "startMoving", "endMoving"]:
                if (v := g(f"snd_{s}")): data["sound"][s] = v

            if (upg := g("upgrades")): data["upgrades"] = [upg]

            data["graphics"].update({
                "animation": g("anim_battle"), "map": g("anim_map"),
                "iconSmall": g("iconSmall"), "iconLarge": g("iconLarge"),
                "timeBetweenFidgets": 1.00, "animationTime": {"walk": 1.0, "idle": 10.0, "attack": 1.0}
            })

            if (missile_anim := g("anim_missile")):
                data["graphics"]["missile"] = {"animation": missile_anim, "attackClimaxFrame": 0, "frameAngles": [-90, -45, 0, 45, 90]}

            if "movement" in self.app.vars:
                m = self.app.vars["movement"].get()
                if m in ["Fly", "Teleport"]:
                    data["abilities"]["flyingAbility" if m == "Fly" else "teleportAbility"] = { "type": "FLYING", "subtype": "movementFlying" if m == "Fly" else "movementTeleporting" }

            if gi("shots") > 0: data["abilities"]["shooterAbility"] = { "type": "SHOOTER" }
                 
            for ab_obj in self.app.dynamic_abilities:
                if (k := ab_obj["key_entry"].get().strip()) and "full_payload" in ab_obj:
                    payload = dict(ab_obj["full_payload"])
                    payload.pop("description", None)
                    if isinstance(payload.get("val"), str) and payload["val"].lstrip('-').isdigit(): payload["val"] = int(payload["val"])
                    if isinstance(payload.get("addInfo"), str) and (payload["addInfo"].strip().startswith(('{','['))):
                        try: payload["addInfo"] = json.loads(payload["addInfo"].strip().replace("'", '"'))
                        except: pass
                    data["abilities"][k] = payload

            txt = VCMIJSONFormatter.format({g("id") or "newCreature": data})
            self.json_text.delete("1.0", tk.END); self.json_text.insert(tk.END, txt)
            if hasattr(self, 'popup_text') and self.popup_text.winfo_exists():
                self.popup_text.delete("1.0", tk.END); self.popup_text.insert(tk.END, txt)
            
        except Exception as e: messagebox.showerror("Error", str(e))

    def save_json(self):
        if f := filedialog.asksaveasfile(mode='w', defaultextension=".json", filetypes=[("JSON Files", "*.json")]): 
            f.write(self.json_text.get("1.0", tk.END)); f.close()