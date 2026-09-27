from PIL import Image, ImageOps, ImageFilter, ImageChops
import colorsys

def hex_to_rgb(hex_color):
    try:
        h = hex_color.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (255,)
    except ValueError:
        return (0, 0, 0, 255)

def apply_transparency(img, hex_color):
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

def get_shifted_image(img, ox, oy, force_transp=False, remove_bg=False, bg_hex="#000000"):
    if ox == 0 and oy == 0:
        return img
        
    if remove_bg or force_transp:
        pad_color = 0 if img.mode == "L" else (0, 0, 0, 0)
    else:
        pad_color = 0 if img.mode == "L" else hex_to_rgb(bg_hex)
            
    shifted = Image.new(img.mode, img.size, pad_color)
    
    if img.mode == "RGBA":
        temp = Image.new("RGBA", img.size, (0,0,0,0))
        temp.paste(img, (ox, oy))
        shifted = Image.alpha_composite(shifted, temp)
    else:
        shifted.paste(img, (ox, oy))
        
    return shifted

def generate_area_image(mask, fill_hex, bg_hex, transparent_bg=False):
    fill_color = hex_to_rgb(fill_hex)
    bg_color = (0, 0, 0, 0) if transparent_bg else hex_to_rgb(bg_hex)
        
    fg_img = Image.new("RGBA", mask.size, fill_color)
    bg_img = Image.new("RGBA", mask.size, bg_color)
    
    bin_mask = mask.point(lambda p: 255 if p > 0 else 0)
    return Image.composite(fg_img, bg_img, bin_mask)

def generate_border_image(mask, fill_hex, bg_hex, transparent_bg=False):
    fill_color = hex_to_rgb(fill_hex)
    bg_color = (0, 0, 0, 0) if transparent_bg else hex_to_rgb(bg_hex)
        
    fg_img = Image.new("RGBA", mask.size, fill_color)
    bg_img = Image.new("RGBA", mask.size, bg_color)
    
    bin_mask = mask.point(lambda p: 255 if p > 0 else 0)
    dilated_mask = bin_mask.filter(ImageFilter.MaxFilter(3))
    border_mask = ImageChops.subtract(dilated_mask, bin_mask)
    
    return Image.composite(fg_img, bg_img, border_mask)

def sort_palette_and_remap(palette_data, palette_alphas, anim_data):
    if not palette_data: return [], []
    
    limit = min(256, len(palette_data) // 3)
    colors = [(i, tuple(palette_data[i*3:i*3+3])) for i in range(limit)]
    
    def sort_key(item):
        r, g, b = item[1]
        return colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
        
    sorted_colors = sorted(colors, key=sort_key)
    mapping = {old_idx: new_idx for new_idx, (old_idx, rgb) in enumerate(sorted_colors)}
    
    new_pal = []
    for _, rgb in sorted_colors:
        new_pal.extend(rgb)
        
    palette_alphas = palette_alphas or [255]*256
    new_alphas = [palette_alphas[old_idx] for old_idx, _ in sorted_colors]
    
    for data in anim_data.values():
        img_p = data["idx"]
        new_pixels = [mapping.get(p, p) for p in img_p.getdata()]
        img_p.putdata(new_pixels)
        
    return new_pal, new_alphas