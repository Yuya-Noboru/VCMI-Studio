import os
import re
import json
import zipfile
import io
import logging
from PIL import Image

class HistoryManager:
    """Gestionnaire universel d'Undo/Redo en RAM."""
    def __init__(self, max_steps, restore_callback):
        self.history = []
        self.index = -1
        self.max_steps = max_steps
        self.restore_callback = restore_callback

    def save_state(self, state):
        if self.index < len(self.history) - 1:
            self.history = self.history[:self.index+1]
        
        self.history.append(state)
        self.index += 1
        
        if len(self.history) > self.max_steps:
            self.history.pop(0)
            self.index -= 1

    def undo(self):
        if self.index > 0:
            self.index -= 1
            self.restore_callback(self.history[self.index])

    def redo(self):
        if self.index < len(self.history) - 1:
            self.index += 1
            self.restore_callback(self.history[self.index])

    def clear(self):
        self.history = []
        self.index = -1

class ProjectManager:
    """Gestionnaire centralisé pour l'exportation ZIP (.vsp) et la génération JSON."""

    @staticmethod
    def get_tree_state(tree_widget):
        """Extrait l'état hiérarchique de l'arbre (Groupes et Fichiers) pour la sauvegarde."""
        state = []
        for group in tree_widget.get_children(""):
            g_dict = {
                "text": tree_widget.item(group, "text"),
                "tags": tree_widget.item(group, "tags"),
                "open": tree_widget.item(group, "open"),
                "children": []
            }
            for f_node in tree_widget.get_children(group):
                g_dict["children"].append({
                    "text": tree_widget.item(f_node, "text"),
                    "tags": tree_widget.item(f_node, "tags")
                })
            state.append(g_dict)
        return state

    @staticmethod
    def build_compact_json(tree_widget, root_node, proj_name, is_flat=False):
        """Construit le JSON compressé pour les Sprites ou Townscreen."""
        if not proj_name or proj_name == "projectName":
            proj_name = "MyProject"

        json_structure = {"basepath": f"sprites/{proj_name}/", "images": []}
        
        if is_flat:
            for frame_idx, item_id in enumerate(tree_widget.get_children("")):
                values = tree_widget.item(item_id, 'values')
                fname = values[1] if values and len(values) > 1 else tree_widget.item(item_id, 'text')
                base_name, _ = os.path.splitext(fname)
                json_structure["images"].append({"group": 0, "frame": frame_idx, "file": f"{base_name}.png"})
        else:
            for group_id in tree_widget.get_children(""):
                if group_id == root_node:
                    continue 
                    
                txt = tree_widget.item(group_id, 'text')
                gid = 0
                if txt.startswith("[") and "]" in txt:
                    try:
                        gid = int(txt[1:txt.find("]")])
                    except ValueError:
                        pass
                        
                children = tree_widget.get_children(group_id)
                for frame_idx, item_id in enumerate(children):
                    fname = tree_widget.item(item_id, 'text')
                    base_name, _ = os.path.splitext(fname)
                    json_structure["images"].append({"group": gid, "frame": frame_idx, "file": f"{base_name}.png"})
                
        raw_json = json.dumps(json_structure, indent=4)
        
        compact_json = re.sub(
            r'\{\s+"group":\s+(\d+),\s+"frame":\s+(\d+),\s+"file":\s+"([^"]+)"\s+\}', 
            r'{ "group": \1, "frame": \2, "file": "\3" }', 
            raw_json
        )
        
        return compact_json

    @staticmethod
    def export_sprite_vsp(filepath, palette_data, palette_alphas, tree_state, proj_name, anim_data):
        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            state = {
                "rgb": list(palette_data),
                "alpha": list(palette_alphas) if palette_alphas else [255]*256,
                "tree": tree_state,
                "project_name": proj_name
            }
            zf.writestr("project.json", json.dumps(state))

            for fname, d in anim_data.items():
                idx_bytes = io.BytesIO()
                d["idx"].putpalette(palette_data) 
                d["idx"].save(idx_bytes, format="PNG")
                zf.writestr(f"images/{fname}_idx.png", idx_bytes.getvalue())

                alpha_bytes = io.BytesIO()
                d["alpha"].save(alpha_bytes, format="PNG")
                zf.writestr(f"images/{fname}_alpha.png", alpha_bytes.getvalue())

    @staticmethod
    def import_sprite_vsp(filepath):
        anim_data = {}
        with zipfile.ZipFile(filepath, 'r') as zf:
            state = json.loads(zf.read("project.json"))
            for item in zf.namelist():
                if item.startswith("images/") and item.endswith("_idx.png"):
                    fname = item[len("images/"): -len("_idx.png")]
                    idx_data = zf.read(item)
                    alpha_data = zf.read(f"images/{fname}_alpha.png")
                    idx_img = Image.open(io.BytesIO(idx_data)).copy()
                    alpha_img = Image.open(io.BytesIO(alpha_data)).copy()
                    anim_data[fname] = {"idx": idx_img, "alpha": alpha_img}
        return state, anim_data

    @staticmethod
    def export_townscreen_vsp(filepath, tree_order, imported_images):
        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            meta = {}
            for fname, data in imported_images.items():
                meta[fname] = {
                    "ox": data.get("ox", 0),
                    "oy": data.get("oy", 0),
                    "has_mask": data.get("custom_mask") is not None
                }
                try:
                    with open(data["path"], "rb") as img_file:
                        zf.writestr(f"images/{fname}", img_file.read())
                except Exception as e:
                    logging.error(f"Could not read {data['path']} for export: {e}")

                if data.get("custom_mask") is not None:
                    mask_bytes = io.BytesIO()
                    data["custom_mask"].save(mask_bytes, format="PNG")
                    zf.writestr(f"masks/{fname}_mask.png", mask_bytes.getvalue())

            state = {"tree": tree_order, "meta": meta}
            zf.writestr("project.json", json.dumps(state))

    @staticmethod
    def import_townscreen_vsp(filepath, cache_dir):
        imported_images = {}
        with zipfile.ZipFile(filepath, 'r') as zf:
            state = json.loads(zf.read("project.json"))
            meta = state.get("meta", {})
            tree_order = state.get("tree", [])

            for fname, m_data in meta.items():
                img_data = zf.read(f"images/{fname}")
                cache_img_path = os.path.join(cache_dir, f"ts_{fname}")
                with open(cache_img_path, "wb") as f_out:
                    f_out.write(img_data)

                custom_mask = None
                if m_data.get("has_mask"):
                    mask_data = zf.read(f"masks/{fname}_mask.png")
                    custom_mask = Image.open(io.BytesIO(mask_data)).copy()

                imported_images[fname] = {
                    "path": cache_img_path,
                    "ox": m_data.get("ox", 0),
                    "oy": m_data.get("oy", 0),
                    "custom_mask": custom_mask
                }
        return tree_order, meta, imported_images