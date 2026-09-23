import sys
import os
import ctypes
import shutil
import logging
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import re
import webbrowser

# -------------------------------------------------------------------------
# 1. CONSOLE MASKING (WINDOWS)
# -------------------------------------------------------------------------
if os.name == 'nt':
    try:
        # Attempts to hide the active console window if the script is not run as .pyw
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

# -------------------------------------------------------------------------
# 2. LOGGING & CRASH HANDLING
# -------------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(current_dir, 'vcmi_studio.log')

logging.basicConfig(
    filename=log_file,
    filemode='w',
    format='%(asctime)s - %(levelname)s - [%(module)s] %(message)s',
    level=logging.DEBUG, 
    encoding='utf-8'
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    messagebox.showerror("Critical Error", f"An error occurred:\n\n{exc_value}\n\nPlease check the logs.")

sys.excepthook = handle_exception
logging.info("Starting initialization process for VCMI Studio (v0.69)...")

# -------------------------------------------------------------------------
# 3. SUBMODULE IMPORTS
# -------------------------------------------------------------------------
try:
    from VCMIS_tab_config_creature import ConfigTab
    from VCMIS_tab_Sprite_editor import SpriteEditorTab
    from VCMIS_tab_townscreen import TownscreenTab
    logging.info("Application submodules imported successfully.")
except Exception as e:
    logging.critical("Fatal error while loading tabs.", exc_info=True)
    raise

# -------------------------------------------------------------------------
# IMPROVED JSON FORMATTER
# -------------------------------------------------------------------------
class VCMIJSONFormatter:
    @staticmethod
    def format_value(val, indent_level=0):
        indent = "\t" * indent_level
        
        if isinstance(val, dict):
            if not val: return "{}"
            items = []
            items.append("{")
            for k, v in val.items():
                formatted_v = VCMIJSONFormatter.format_value(v, indent_level + 1)
                items.append(f'{indent}\t"{k}": {formatted_v},')
            if len(items) > 1:
                items[-1] = items[-1].rstrip(',') 
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
                for x in val:
                     items.append(f'{indent}\t{VCMIJSONFormatter.format_value(x, indent_level + 1)},')
                if len(items) > 1: items[-1] = items[-1].rstrip(',')
                items.append(f'{indent}]')
                return "\n".join(items)
        
        elif isinstance(val, str):
            return json.dumps(val) 
        elif isinstance(val, bool):
            return "true" if val else "false"
        else:
            return str(val)

    @staticmethod
    def format(data_dict):
        output = []
        output.append("{")
        
        for creature_id, c_data in data_dict.items():
            output.append(f'\t"{creature_id}": {{')
            
            fields = []
            
            # 1. Names
            s_name = json.dumps(c_data.get("name", {}).get("singular", ""))
            p_name = json.dumps(c_data.get("name", {}).get("plural", ""))
            fields.append(f'\t\t"name": {{ "singular": {s_name}, "plural": {p_name} }}')
            
            # 2. General Stats
            simple_fields = ["advMapAmount", "faction", "special", "level", "attack", "defense", "hitPoints", "speed", "shots", "spellPoints", "growth", "horde", "fightValue", "aiValue", "doubleWide", "cost"]
            
            for f in simple_fields:
                if f in c_data:
                    fields.append(f'\t\t"{f}": {VCMIJSONFormatter.format_value(c_data[f])}')
                    
            if "damage" in c_data:
                d = c_data["damage"]
                fields.append(f'\t\t"damage": {{ "min": {d["min"]}, "max": {d["max"]} }}')
            
            if "upgrades" in c_data and c_data["upgrades"]:
                 fields.append(f'\t\t"upgrades": {VCMIJSONFormatter.format_value(c_data["upgrades"])}')

            # 4. Graphics
            if "graphics" in c_data:
                fields.append(f'\t\t"graphics": {VCMIJSONFormatter.format_value(c_data["graphics"], 2)}')
            
            # 5. Sounds
            if "sound" in c_data and c_data["sound"]:
                fields.append(f'\t\t"sound": {VCMIJSONFormatter.format_value(c_data["sound"], 2)}')

            # 6. Abilities
            if "abilities" in c_data and c_data["abilities"]:
                ab_lines = ['{']
                ab_keys = list(c_data["abilities"].keys())
                for i, k in enumerate(ab_keys):
                    v = c_data["abilities"][k]
                    comma = "," if i < len(ab_keys) - 1 else ""
                    formatted_val = VCMIJSONFormatter.format_value(v, 3)
                    ab_lines.append(f'\t\t\t"{k}": {formatted_val}{comma}')
                ab_lines.append('\t\t}')
                fields.append(f'\t\t"abilities": ' + "\n".join(ab_lines))

            output.append(",\n\n".join(fields))
            output.append('\t}')
            
        output.append("}")
        return "\n".join(output)

# -------------------------------------------------------------------------
# MAIN APPLICATION
# -------------------------------------------------------------------------
class VCMICreatureEditor:
    def __init__(self, root):
        logging.info("Initializing UI Main Interface...")
        self.root = root
        self.version = "0.69"
        self.root.title(f"VCMI Studio (v{self.version})")
        
        self.root.geometry("1300x850")
        self.root.minsize(1100, 750)
        
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.res_dir = os.path.join(self.current_dir, 'res')
        self.cache_dir = os.path.join(self.current_dir, 'cache')
        for d in [self.cache_dir]:
            if not os.path.exists(d):
                try: 
                    os.makedirs(d)
                    logging.debug(f"Created directory: {d}")
                except Exception as e: 
                    logging.error(f"Failed to create directory {d}: {e}")
        
        self.vars = {}
        self.entries = {}
        self.ui_icons = {}
        
        self.load_ui_resources()
        
        style = ttk.Style()
        try: 
            style.theme_use('clam')
            logging.debug("Applied 'clam' ttk theme.")
        except: 
            pass

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=True, fill='both', padx=5, pady=5)
        
        # 1. Tab frames creation
        self.tab_menu_frame = ttk.Frame(self.notebook)
        self.tab_config_frame = ttk.Frame(self.notebook)
        self.tab_anims_frame = ttk.Frame(self.notebook)
        self.tab_townscreen_frame = ttk.Frame(self.notebook)
        self.tab_misc_frame = ttk.Frame(self.notebook)
        
        # 2. Add tabs in strict order
        self.notebook.add(self.tab_menu_frame, text="Menu")
        self.notebook.add(self.tab_config_frame, text="Config (Creature)")
        self.notebook.add(self.tab_anims_frame, text="Sprite Editor")
        self.notebook.add(self.tab_townscreen_frame, text="Townscreen")
        self.notebook.add(self.tab_misc_frame, text="Misc.")
        
        # 3. Build Menu Tab (Sober Gray Aesthetics)
        logging.info("Building Menu Tab...")
        menu_container = tk.Frame(self.tab_menu_frame, bg="#e0e0e0")
        menu_container.pack(expand=True, fill="both")
        
        inner_menu = tk.Frame(menu_container, bg="#f2f2f2", bd=0, highlightthickness=1, highlightbackground="#cccccc")
        inner_menu.place(relx=0.5, rely=0.5, anchor="center", width=700, height=450)
        
        tk.Label(inner_menu, text="VCMI Studio", font=("Segoe UI", 48, "bold"), fg="#333333", bg="#f2f2f2").pack(pady=(60, 0))
        tk.Label(inner_menu, text=f"Version {self.version}", font=("Segoe UI", 16, "italic"), fg="#777777", bg="#f2f2f2").pack(pady=(0, 40))
        
        tk.Label(inner_menu, text="Community tool for Heroes 3 VCMI modding", font=("Segoe UI", 14), fg="#555555", bg="#f2f2f2").pack(pady=(0, 30))
        
        tk.Label(inner_menu, text="Author : Yūya Noboru", font=("Segoe UI", 14, "bold"), fg="#888888", bg="#f2f2f2").pack(side="bottom", pady=40)

        # 4. Build Misc Tab (Sober Gray Aesthetics)
        logging.info("Building Misc Tab...")
        misc_container = tk.Frame(self.tab_misc_frame, bg="#e0e0e0")
        misc_container.pack(expand=True, fill="both")
        
        misc_header = tk.Frame(misc_container, bg="#d0d0d0", height=80)
        misc_header.pack(fill="x")
        misc_header.pack_propagate(False) 
        tk.Label(misc_header, text="Miscellaneous & Settings", font=("Segoe UI", 20, "bold"), fg="#333333", bg="#d0d0d0").pack(pady=20)
        
        misc_content = tk.Frame(misc_container, bg="#e0e0e0")
        misc_content.pack(fill="both", expand=True, padx=60, pady=40)
        
        # System Maintenance Card
        card_system = tk.LabelFrame(misc_content, text="  System Maintenance  ", font=("Segoe UI", 12, "bold"), bg="#f2f2f2", fg="#333333", bd=1)
        card_system.pack(fill="x", pady=10, ipadx=10, ipady=15)
        
        btn_logs = tk.Button(card_system, text="📄 Open Log File", font=("Segoe UI", 10, "bold"), bg="#dddddd", fg="#333333", width=30, relief="flat", cursor="hand2", command=self.open_logs)
        btn_logs.pack(anchor="w", pady=10, padx=20)
        
        btn_cache = tk.Button(card_system, text="🗑️ Clear Cache Folder", font=("Segoe UI", 10, "bold"), bg="#dddddd", fg="#333333", width=30, relief="flat", cursor="hand2", command=self.clear_cache_folder)
        btn_cache.pack(anchor="w", pady=10, padx=20)
        
        # About Card
        card_about = tk.LabelFrame(misc_content, text="  About  ", font=("Segoe UI", 12, "bold"), bg="#f2f2f2", fg="#333333", bd=1)
        card_about.pack(fill="x", pady=20, ipadx=10, ipady=15)
        
        about_text = ("VCMI Studio is an all-in-one modding suite for Heroes 3 VCMI.\n\n"
                      "It is designed to help modders in various ways : from JSON configuration file generation to sprite editing.\n"
                      "GitHub: https://github.com/Yuya-Noboru/VCMI-Studio, Forum : https://forum.vcmi.eu/t/vcmi-studio-project/6760")
        tk.Label(card_about, text=about_text, justify="left", bg="#f2f2f2", font=("Segoe UI", 11), fg="#555555").pack(anchor="w", pady=5, padx=20)

        # 5. Submodules Instantiation
        logging.info("Instantiating ConfigTab module...")
        self.config_tab = ConfigTab(self.tab_config_frame, self)
        
        logging.info("Instantiating SpriteEditorTab module...")
        self.sprite_tab = SpriteEditorTab(self.tab_anims_frame, self)
        
        logging.info("Instantiating TownscreenTab module...")
        self.townscreen_tab = TownscreenTab(self.tab_townscreen_frame, self)
        
        self.build_export_section(self.config_tab.export_container)
        
        self.root.bind("<Control-z>", self.sprite_tab.undo)
        self.root.bind("<Control-y>", self.sprite_tab.redo)
        
        logging.info("VCMI Studio initialized successfully.")

    # -------------------------------------------------------------------------
    # MISC TAB FUNCTIONS
    # -------------------------------------------------------------------------
    def open_logs(self):
        logging.info("Attempting to open log file by user.")
        if os.path.exists(log_file):
            try:
                webbrowser.open(log_file)
            except Exception as e:
                logging.error(f"Failed to open log: {e}")
                messagebox.showerror("Error", f"Unable to open file: {e}")
        else:
            messagebox.showwarning("Not Found", "The log file does not exist yet.")

    def clear_cache_folder(self):
        logging.info("Cache clearing request initiated.")
        if messagebox.askyesno("Clear Cache", "Are you sure you want to delete all files in the cache folder?"):
            try:
                count = 0
                for f in os.listdir(self.cache_dir):
                    fp = os.path.join(self.cache_dir, f)
                    if os.path.isfile(fp):
                        os.unlink(fp)
                        count += 1
                logging.info(f"Cache cleared: {count} files deleted.")
                messagebox.showinfo("Cache Cleared", f"{count} file(s) successfully deleted from the cache.")
            except Exception as e:
                logging.error(f"Error clearing cache: {e}")
                messagebox.showerror("Error", f"An error occurred during deletion:\n{e}")

    # -------------------------------------------------------------------------
    # ASSETS & JSON CORE FUNCTIONS
    # -------------------------------------------------------------------------
    def load_ui_resources(self):
        logging.info("Loading UI resources and icons...")
        if not os.path.exists(self.res_dir): 
            logging.warning(f"Resource directory not found: {self.res_dir}")
            return
            
        from PIL import Image, ImageTk
        for res in ["Gold", "Wood", "Ore", "Mercury", "Sulfur", "Crystal", "Gems"]:
            self._load_icon(f"res{res}.png", res.lower(), size=(20, 20))
            
        stat_size = (26, 26)
        map_files = {
            "attack": "statAttack.png", "defense": "statDefense.png",
            "damage": "statDamage.png", "health": "statHealth.png",
            "speed": "statSpeed.png", "growth": "statGrowth.png",
            "shots": "statShots.png",
            "mov_ground": "statMovementGround.png",
            "mov_fly": "statMovementFly.png",
            "mov_teleport": "statMovementTeleport.png",
            "aiValue": "statAival.png", "fightValue": "statFval.png",
            "advMap": "statAdvmap.png", "horde": "statHorde.png",
            "doubleWide": "statDwide.png", "special": "statSpecial.png",
            "spellPoints": "statSpellpoints.png"
        }
        for k, f in map_files.items(): 
            self._load_icon(f, k, size=stat_size)
            
        logging.info(f"Loaded {len(self.ui_icons)} UI icons successfully.")

    def _load_icon(self, filename, key, size=(20, 20)):
        from PIL import Image, ImageTk
        path = os.path.join(self.res_dir, filename)
        if os.path.exists(path):
            try:
                img = Image.open(path)
                img = img.resize(size, Image.Resampling.LANCZOS)
                self.ui_icons[key] = ImageTk.PhotoImage(img)
            except Exception as e:
                logging.warning(f"Failed to load icon {filename}: {e}")
        else:
            logging.debug(f"Icon file missing: {filename}")

    def build_export_section(self, parent):
        logging.info("Building JSON Export section...")
        f = ttk.LabelFrame(parent, text="JSON Manager")
        f.pack(side="top", fill="both", expand=True)
        
        b = ttk.Frame(f)
        b.pack(fill="x", pady=2)
        ttk.Button(b, text="Generate JSON", command=self.generate_json).pack(side="left", padx=5)
        ttk.Button(b, text="Save As...", command=self.save_json).pack(side="left", padx=5)
        ttk.Button(b, text="Load", command=self.load_json).pack(side="left", padx=5)
        
        ttk.Button(b, text="⤢", width=3, command=self.open_json_popup).pack(side="right", padx=5)
        
        self.json_text = tk.Text(f, height=8, font=("Consolas", 9))
        self.json_text.pack(fill="both", expand=True, padx=5, pady=5)

    def open_json_popup(self):
        logging.debug("Opening JSON Viewer popup.")
        top = tk.Toplevel(self.root)
        top.title("VCMI JSON Viewer")
        
        popup_w = 900
        popup_h = 700
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_w = self.root.winfo_width()
        main_h = self.root.winfo_height()
        
        pos_x = main_x + (main_w - popup_w) // 2
        pos_y = main_y + (main_h - popup_h) // 2
        
        top.geometry(f"{popup_w}x{popup_h}+{pos_x}+{pos_y}")
        
        self.popup_text = tk.Text(top, wrap="none", font=("Consolas", 11))
        vsb = ttk.Scrollbar(top, orient="vertical", command=self.popup_text.yview)
        hsb = ttk.Scrollbar(top, orient="horizontal", command=self.popup_text.xview)
        self.popup_text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.popup_text.pack(side="left", fill="both", expand=True)
        
        self.popup_text.insert("1.0", self.json_text.get("1.0", tk.END))
        
        def start_scroll(event):
            self.popup_text.scan_mark(event.x, event.y)
        def do_scroll(event):
            self.popup_text.scan_dragto(event.x, event.y, gain=1)
            
        self.popup_text.bind("<ButtonPress-2>", start_scroll)
        self.popup_text.bind("<B2-Motion>", do_scroll)

    def load_json(self):
        f_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if not f_path: return
        
        logging.info(f"Loading JSON file: {f_path}")
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                raw_data = f.read()
            
            clean_data = re.sub(r'/\*.*?\*/', '', raw_data, flags=re.DOTALL)
            clean_data = re.sub(r'//.*', '', clean_data)
            
            data = json.loads(clean_data)
            
            if not isinstance(data, dict) or len(data) == 0:
                raise ValueError("The file does not contain a root Creature object.")
                
            creature_id = list(data.keys())[0]
            c_data = data[creature_id]
            
            if not isinstance(c_data, dict):
                raise ValueError("Creature data is corrupted.")
                
            def set_e(k, v):
                if k in self.entries:
                    self.entries[k].set_value(str(v) if v is not None else "")
                    
            def set_v(k, v):
                if k in self.vars:
                    self.vars[k].set(v)
            
            set_e("id", creature_id)
            set_e("name_singular", c_data.get("name", {}).get("singular", ""))
            set_e("name_plural", c_data.get("name", {}).get("plural", ""))
            set_e("faction", c_data.get("faction", ""))
            set_e("level", c_data.get("level", "1"))
            
            cost = c_data.get("cost", {})
            for res in ["gold", "wood", "ore", "mercury", "sulfur", "crystal", "gems"]:
                set_e(f"cost_{res}", cost.get(res, "0"))
                
            set_e("attack", c_data.get("attack", "5"))
            set_e("defense", c_data.get("defense", "5"))
            set_e("hitPoints", c_data.get("hitPoints", "10"))
            set_e("speed", c_data.get("speed", "5"))
            set_e("shots", c_data.get("shots", "0"))
            set_e("spellPoints", c_data.get("spellPoints", "0"))
            
            dmg = c_data.get("damage", {})
            set_e("dmg_min", dmg.get("min", ""))
            set_e("dmg_max", dmg.get("max", ""))
            
            set_e("growth", c_data.get("growth", "10"))
            set_e("horde", c_data.get("horde", "0"))
            set_e("aiValue", c_data.get("aiValue", "100"))
            
            adv = c_data.get("advMapAmount", {})
            set_e("adv_min", adv.get("min", ""))
            set_e("adv_max", adv.get("max", ""))
            
            set_v("doubleWide", bool(c_data.get("doubleWide", False)))
            set_v("special", bool(c_data.get("special", False)))
            
            sounds = c_data.get("sound", {})
            for s in ["attack", "defend", "killed", "move", "shoot", "wince", "startMoving", "endMoving"]:
                set_e(f"snd_{s}", sounds.get(s, ""))
                
            gfx = c_data.get("graphics", {})
            set_e("anim_battle", gfx.get("animation", ""))
            set_e("anim_map", gfx.get("map", ""))
            
            p_small = gfx.get("iconSmall", "")
            p_large = gfx.get("iconLarge", "")
            if p_small: self.config_tab._set_portrait_image("iconSmall", os.path.join(self.res_dir, p_small), p_small)
            if p_large: self.config_tab._set_portrait_image("iconLarge", os.path.join(self.res_dir, p_large), p_large)
            
            missile = gfx.get("missile", {})
            if isinstance(missile, dict):
                set_e("anim_missile", missile.get("animation", ""))
            else:
                set_e("anim_missile", "")
                
            upgrades = c_data.get("upgrades", [])
            if isinstance(upgrades, list) and len(upgrades) > 0:
                set_e("upgrades", upgrades[0])
            else:
                set_e("upgrades", "")
                
            self.config_tab.clear_abilities()
            abilities = c_data.get("abilities", {})
            movement_set = False
            
            for ak, av in abilities.items():
                if isinstance(av, dict):
                    t = av.get("type", "")
                    s = av.get("subtype", "")
                    
                    if t == "FLYING" and s == "movementFlying":
                        set_v("movement", "Fly")
                        movement_set = True
                        continue
                    elif t == "FLYING" and s == "movementTeleporting":
                        set_v("movement", "Teleport")
                        movement_set = True
                        continue
                    elif t == "SHOOTER":
                        continue 
                        
                    # INJECTION DU PAYLOAD COMPLET
                    self.config_tab.add_ability(key_name=ak, full_payload=av)
            
            if not movement_set:
                set_v("movement", "Ground")
            self.config_tab.update_movement_icon()
                
            self.generate_json()
            logging.info(f"Loaded creature JSON successfully: {creature_id}")
            messagebox.showinfo("Success", f"Creature '{creature_id}' successfully loaded.")
            
        except json.JSONDecodeError as je:
            logging.error(f"JSON Decode Error: {je}", exc_info=True)
            messagebox.showerror("JSON Error", f"Invalid JSON format. Please check the file.\n\nDetails: {je}")
        except Exception as e:
            logging.error(f"Error loading JSON file: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to load file.\n\n{e}")

    def generate_json(self):
        logging.info("Generating JSON payload from configuration...")
        try:
            def g(k): return self.entries[k].get_real_value().strip() if k in self.entries else ""
            def gi(k): 
                v = g(k)
                return int(v) if v.lstrip('-').isdigit() else 0
            
            ai_val = gi("aiValue")
            
            data = {
                "name": {"singular": g("name_singular"), "plural": g("name_plural")},
                "faction": g("faction"), 
                "level": int(g("level") or 1),
                "attack": gi("attack"), 
                "defense": gi("defense"),
                "damage": {"min": gi("dmg_min"), "max": gi("dmg_max")},
                "hitPoints": gi("hitPoints"), 
                "speed": gi("speed"), 
                "growth": gi("growth"), 
                "fightValue": ai_val, 
                "aiValue": ai_val, 
                "cost": {}, 
                "sound": {}, 
                "graphics": {},
                "abilities": {} 
            }
            
            adv_min, adv_max = gi("adv_min"), gi("adv_max")
            if adv_min > 0 or adv_max > 0:
                data["advMapAmount"] = {"min": adv_min, "max": adv_max}

            horde = gi("horde")
            if horde > 0: data["horde"] = horde

            shots = gi("shots")
            if shots > 0: data["shots"] = shots

            spell_points = gi("spellPoints")
            if spell_points > 0: data["spellPoints"] = spell_points

            if "special" in self.vars and self.vars["special"].get():
                data["special"] = True
                
            if "doubleWide" in self.vars:
                data["doubleWide"] = self.vars["doubleWide"].get()
            
            for res in ["gold","wood","ore","mercury","sulfur","crystal","gems"]:
                v = gi(f"cost_{res}")
                if v > 0: data["cost"][res] = v
            
            for s in ["attack","defend","killed","move","shoot","wince", "startMoving", "endMoving"]:
                if f"snd_{s}" in self.entries:
                    v = g(f"snd_{s}")
                    if v: data["sound"][s] = v

            upg = g("upgrades")
            if upg: data["upgrades"] = [upg]

            data["graphics"]["animation"] = g("anim_battle")
            data["graphics"]["map"] = g("anim_map")
            data["graphics"]["iconSmall"] = g("iconSmall")
            data["graphics"]["iconLarge"] = g("iconLarge")
            data["graphics"]["timeBetweenFidgets"] = 1.00
            data["graphics"]["animationTime"] = {"walk": 1.0, "idle": 10.0, "attack": 1.0}

            missile_anim = g("anim_missile")
            if missile_anim:
                data["graphics"]["missile"] = {
                    "animation": missile_anim,
                    "attackClimaxFrame": 0,
                    "frameAngles": [-90, -45, 0, 45, 90]
                }

            if "movement" in self.vars:
                m = self.vars["movement"].get()
                if m == "Fly":
                    data["abilities"]["flyingAbility"] = { "type": "FLYING", "subtype": "movementFlying" }
                elif m == "Teleport":
                    data["abilities"]["teleportAbility"] = { "type": "FLYING", "subtype": "movementTeleporting" }

            if gi("shots") > 0:
                 data["abilities"]["shooterAbility"] = { "type": "SHOOTER" }
                 
            # GÉNÉRATION DES CAPACITÉS DYNAMIQUES AVEC FULL PAYLOAD
            if hasattr(self, 'dynamic_abilities'):
                for ab_obj in self.dynamic_abilities:
                    k = ab_obj["key_entry"].get().strip()
                    if k and "full_payload" in ab_obj:
                        payload = dict(ab_obj["full_payload"])
                        # Nettoyer la description (Non reconnue par le moteur VCMI)
                        if "description" in payload:
                            del payload["description"]
                        
                        if "val" in payload and isinstance(payload["val"], str):
                            try:
                                if payload["val"].lstrip('-').isdigit():
                                    payload["val"] = int(payload["val"])
                            except ValueError:
                                pass # On laisse en string
                        
                        # Convertir dynamiquement addInfo si c'est un tableau ou un objet
                        if "addInfo" in payload and isinstance(payload["addInfo"], str):
                            add_val = payload["addInfo"].strip()
                            if (add_val.startswith('[') and add_val.endswith(']')) or (add_val.startswith('{') and add_val.endswith('}')):
                                try:
                                    add_val_clean = add_val.replace("'", '"')
                                    payload["addInfo"] = json.loads(add_val_clean)
                                except Exception as e:
                                    logging.debug(f"Parsing addInfo string as JSON failed for {k}: {e}")
                                    pass # En cas d'erreur de parsing, on laisse en string
                                
                        data["abilities"][k] = payload

            creature_id = g("id") or "newCreature"
            txt = VCMIJSONFormatter.format({creature_id: data})
            
            self.json_text.delete("1.0", tk.END)
            self.json_text.insert(tk.END, txt)
            
            if hasattr(self, 'popup_text') and self.popup_text.winfo_exists():
                self.popup_text.delete("1.0", tk.END)
                self.popup_text.insert(tk.END, txt)
                
            logging.info("JSON payload generated successfully.")
            
        except Exception as e:
            logging.error(f"Error generating JSON: {e}", exc_info=True)
            messagebox.showerror("Error", str(e))

    def save_json(self):
        logging.info("Prompting user to save JSON...")
        f = filedialog.asksaveasfile(mode='w', defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if f: 
            f.write(self.json_text.get("1.0", tk.END))
            f.close()
            logging.info(f"JSON file saved successfully to: {f.name}")
        else:
            logging.debug("JSON save operation cancelled by user.")

if __name__ == "__main__":
    root = tk.Tk()
    app = VCMICreatureEditor(root)
    root.mainloop()