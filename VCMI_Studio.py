import sys
import os
import ctypes
import logging
import traceback
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import importlib

# -------------------------------------------------------------------------
# 1. CONSOLE MASKING (WINDOWS)
# -------------------------------------------------------------------------
if os.name == 'nt':
    try:
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
logging.info("Starting initialization process for VCMI Studio (v0.79)...")

# -------------------------------------------------------------------------
# MAIN APPLICATION
# -------------------------------------------------------------------------
class VCMICreatureEditor:
    def __init__(self, root):
        logging.info("Initializing UI Main Interface...")
        self.root = root
        self.version = "0.79"
        self.root.title(f"VCMI Studio (v{self.version})")
        
        self.root.geometry("1300x850")
        self.root.minsize(1100, 750)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
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
        
        self.async_clear_cache()
        
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
        
        self.tab_menu_frame = ttk.Frame(self.notebook)
        self.tab_config_frame = ttk.Frame(self.notebook)
        self.tab_anims_frame = ttk.Frame(self.notebook)
        self.tab_townscreen_frame = ttk.Frame(self.notebook)
        self.tab_misc_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_menu_frame, text="Menu")
        self.notebook.add(self.tab_config_frame, text="Config (Creature)")
        self.notebook.add(self.tab_anims_frame, text="Sprite Editor")
        self.notebook.add(self.tab_townscreen_frame, text="Townscreen")
        self.notebook.add(self.tab_misc_frame, text="Misc.")
        
        logging.info("Building Menu Tab...")
        menu_container = tk.Frame(self.tab_menu_frame, bg="#e0e0e0")
        menu_container.pack(expand=True, fill="both")
        
        inner_menu = tk.Frame(menu_container, bg="#f2f2f2", bd=0, highlightthickness=1, highlightbackground="#cccccc")
        inner_menu.place(relx=0.5, rely=0.5, anchor="center", width=700, height=450)
        
        tk.Label(inner_menu, text="VCMI Studio", font=("Segoe UI", 48, "bold"), fg="#333333", bg="#f2f2f2").pack(pady=(60, 0))
        tk.Label(inner_menu, text=f"Version {self.version}", font=("Segoe UI", 16, "italic"), fg="#777777", bg="#f2f2f2").pack(pady=(0, 40))
        tk.Label(inner_menu, text="Community tool for Heroes 3 VCMI modding", font=("Segoe UI", 14), fg="#555555", bg="#f2f2f2").pack(pady=(0, 30))
        tk.Label(inner_menu, text="Author : Yūya Noboru", font=("Segoe UI", 14, "bold"), fg="#888888", bg="#f2f2f2").pack(side="bottom", pady=40)

        logging.info("Building Misc Tab...")
        misc_container = tk.Frame(self.tab_misc_frame, bg="#e0e0e0")
        misc_container.pack(expand=True, fill="both")
        
        misc_header = tk.Frame(misc_container, bg="#d0d0d0", height=80)
        misc_header.pack(fill="x")
        misc_header.pack_propagate(False) 
        tk.Label(misc_header, text="Miscellaneous & Settings", font=("Segoe UI", 20, "bold"), fg="#333333", bg="#d0d0d0").pack(pady=20)
        
        misc_content = tk.Frame(misc_container, bg="#e0e0e0")
        misc_content.pack(fill="both", expand=True, padx=60, pady=40)
        
        card_system = tk.LabelFrame(misc_content, text="  System Maintenance  ", font=("Segoe UI", 12, "bold"), bg="#f2f2f2", fg="#333333", bd=1)
        card_system.pack(fill="x", pady=10, ipadx=10, ipady=15)
        
        btn_logs = tk.Button(card_system, text="📄 Open Log File", font=("Segoe UI", 10, "bold"), bg="#dddddd", fg="#333333", width=30, relief="flat", cursor="hand2", command=self.open_logs)
        btn_logs.pack(anchor="w", pady=10, padx=20)
        
        btn_cache = tk.Button(card_system, text="🗑️ Clear Cache Folder", font=("Segoe UI", 10, "bold"), bg="#dddddd", fg="#333333", width=30, relief="flat", cursor="hand2", command=self.clear_cache_folder)
        btn_cache.pack(anchor="w", pady=10, padx=20)
        
        card_about = tk.LabelFrame(misc_content, text="  About  ", font=("Segoe UI", 12, "bold"), bg="#f2f2f2", fg="#333333", bd=1)
        card_about.pack(fill="x", pady=20, ipadx=10, ipady=15)
        
        about_text = ("VCMI Studio is an all-in-one modding suite for Heroes 3 VCMI.\n\n"
                      "It is designed to help modders in various ways : from JSON configuration file generation to sprite editing.\n"
                      "GitHub: https://github.com/Yuya-Noboru/VCMI-Studio, Forum : https://forum.vcmi.eu/t/vcmi-studio-project/6760")
        tk.Label(card_about, text=about_text, justify="left", bg="#f2f2f2", font=("Segoe UI", 11), fg="#555555").pack(anchor="w", pady=5, padx=20)

        self.config_tab = None
        self.sprite_tab = None
        self.townscreen_tab = None
        
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.root.bind("<Control-z>", self.global_undo)
        self.root.bind("<Control-y>", self.global_redo)
        
        logging.info("VCMI Studio initialized successfully.")

    def on_closing(self):
        warn = False
        if self.sprite_tab and self.sprite_tab.has_unsaved_changes(): warn = True
        if self.townscreen_tab and self.townscreen_tab.has_unsaved_changes(): warn = True
            
        if warn:
            if not messagebox.askyesno("Unsaved Changes", "You have unsaved changes in your projects that will be lost.\nAre you sure you want to exit without exporting/saving?"):
                return
        self.root.destroy()

    def on_tab_changed(self, event):
        idx = self.notebook.index(self.notebook.select())
        if idx == 1 and self.config_tab is None:
            self.config_tab = self.load_tab("VCMIS_tab_config_creature", "ConfigTab", self.tab_config_frame, 1, "Config (Creature)")
        elif idx == 2 and self.sprite_tab is None:
            self.sprite_tab = self.load_tab("VCMIS_tab_Sprite_editor", "SpriteEditorTab", self.tab_anims_frame, 2, "Sprite Editor")
        elif idx == 3 and self.townscreen_tab is None:
            self.townscreen_tab = self.load_tab("VCMIS_tab_townscreen", "TownscreenTab", self.tab_townscreen_frame, 3, "Townscreen")

    def load_tab(self, module_name, class_name, frame, tab_index, tab_title):
        try:
            logging.info(f"Lazy loading {class_name} module...")
            module = importlib.import_module(module_name)
            tab_class = getattr(module, class_name)
            return tab_class(frame, self)
        except Exception as e:
            logging.error(f"Fatal error while loading {class_name}: {e}", exc_info=True)
            for widget in frame.winfo_children(): widget.destroy()
            
            err_frame = tk.Frame(frame, bg="#ffe6e6", bd=2, relief="solid")
            err_frame.place(relx=0.5, rely=0.5, anchor="center", width=700, height=350)
            
            tk.Label(err_frame, text=f"⚠️ Tab Crash: {class_name}", font=("Segoe UI", 16, "bold"), fg="#cc0000", bg="#ffe6e6").pack(pady=(20, 10))
            tk.Label(err_frame, text="A critical error prevented this tab from loading.\nThe application remains usable for other functions.", font=("Segoe UI", 11), fg="#333333", bg="#ffe6e6").pack(pady=5)
            
            txt = tk.Text(err_frame, height=10, font=("Consolas", 9), bg="#f8f8f8", fg="#aa0000")
            txt.pack(fill="both", expand=True, padx=20, pady=15)
            txt.insert("1.0", traceback.format_exc())
            txt.config(state="disabled")
            
            self.notebook.tab(tab_index, text=f"⚠️ {tab_title} (Error)")
            return None

    def global_undo(self, event=None):
        try:
            idx = self.notebook.index(self.notebook.select())
            if idx == 2 and self.sprite_tab: self.sprite_tab.undo(event)
            elif idx == 3 and self.townscreen_tab: self.townscreen_tab.undo(event)
        except Exception as e: logging.error(f"Global undo error: {e}", exc_info=True)

    def global_redo(self, event=None):
        try:
            idx = self.notebook.index(self.notebook.select())
            if idx == 2 and self.sprite_tab: self.sprite_tab.redo(event)
            elif idx == 3 and self.townscreen_tab: self.townscreen_tab.redo(event)
        except Exception as e: logging.error(f"Global redo error: {e}", exc_info=True)

    def open_logs(self):
        logging.info("Attempting to open log file by user.")
        if os.path.exists(log_file):
            try: webbrowser.open(log_file)
            except Exception as e:
                logging.error(f"Failed to open log: {e}")
                messagebox.showerror("Error", f"Unable to open file: {e}")
        else:
            messagebox.showwarning("Not Found", "The log file does not exist yet.")

    def async_clear_cache(self):
        def worker():
            if not os.path.exists(self.cache_dir): return
            for f in os.listdir(self.cache_dir):
                try: os.remove(os.path.join(self.cache_dir, f))
                except (PermissionError, OSError): pass
        threading.Thread(target=worker, daemon=True).start()

    def clear_cache_folder(self):
        logging.info("Cache clearing request initiated by user.")
        if messagebox.askyesno("Clear Cache", "Are you sure you want to delete all files in the cache folder?"):
            self.async_clear_cache()
            messagebox.showinfo("Cache Cleanup", "Cache cleanup has been started in the background.")

    def load_ui_resources(self):
        logging.info("Loading UI resources and icons...")
        if not os.path.exists(self.res_dir): 
            logging.warning(f"Resource directory not found: {self.res_dir}")
            return
        from PIL import Image, ImageTk
        for res in ["Gold", "Wood", "Ore", "Mercury", "Sulfur", "Crystal", "Gems"]:
            self._load_icon(f"res{res}.png", res.lower(), size=(20, 20))
        map_files = {
            "attack": "statAttack.png", "defense": "statDefense.png",
            "damage": "statDamage.png", "health": "statHealth.png",
            "speed": "statSpeed.png", "growth": "statGrowth.png",
            "shots": "statShots.png", "mov_ground": "statMovementGround.png",
            "mov_fly": "statMovementFly.png", "mov_teleport": "statMovementTeleport.png",
            "aiValue": "statAival.png", "fightValue": "statFval.png",
            "advMap": "statAdvmap.png", "horde": "statHorde.png",
            "doubleWide": "statDwide.png", "special": "statSpecial.png",
            "spellPoints": "statSpellpoints.png"
        }
        for k, f in map_files.items(): self._load_icon(f, k, size=(26, 26))
        logging.info(f"Loaded {len(self.ui_icons)} UI icons successfully.")

    def _load_icon(self, filename, key, size=(20, 20)):
        from PIL import Image, ImageTk
        path = os.path.join(self.res_dir, filename)
        if os.path.exists(path):
            try:
                img = Image.open(path).resize(size, Image.Resampling.LANCZOS)
                self.ui_icons[key] = ImageTk.PhotoImage(img)
            except Exception as e: logging.warning(f"Failed to load icon {filename}: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VCMICreatureEditor(root)
    root.mainloop()