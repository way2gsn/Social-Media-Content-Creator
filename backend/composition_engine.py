
import os
import io
from PIL import Image, ImageStat
import numpy as np
from typing import Tuple, List, Dict

class DynamicCompositionEngine:
    """
    Senior Art Director Logic:
    Moves from static templates to dynamic editorial compositions.
    Analyzes images for subject positioning, dead space, and color harmony.
    """

    @staticmethod
    def analyze_image(image_path: str) -> Dict:
        """
        Analyzes the image to determine composition strategy.
        """
        if not os.path.exists(image_path):
            return {"layout": "CENTERED", "colors": ["#000000", "#FFFFFF"], "text_anchor": "bottom"}

        img = Image.open(image_path).convert("RGB")
        width, height = img.size
        
        # 1. Subject Position Detection (using brightness/contrast variance as a proxy for 'busyness')
        # We split the image into 3 vertical zones
        zones = [
            img.crop((0, 0, width // 3, height)),
            img.crop((width // 3, 0, 2 * width // 3, height)),
            img.crop((2 * width // 3, 0, width, height))
        ]
        
        # Calculate 'entropy' or 'busyness' of each zone
        busyness = []
        for zone in zones:
            stat = ImageStat.Stat(zone.convert("L"))
            # Standard deviation of pixel values indicates complexity/detail
            busyness.append(stat.stddev[0])
        
        # Subject is likely in the busiest zone
        subject_zone_idx = busyness.index(max(busyness))
        
        # 2. Dead Space Detection (the least busy zone)
        dead_zone_idx = busyness.index(min(busyness))
        
        layout_map = {0: "RIGHT_ALIGNED", 1: "TOP_OR_BOTTOM", 2: "LEFT_ALIGNED"}
        # If subject is on left (0), text should be on right (2)
        # If subject is on right (2), text should be on left (0)
        
        if subject_zone_idx == 0:
            layout = "ASIDE_RIGHT"
            text_anchor = "right"
        elif subject_zone_idx == 2:
            layout = "ASIDE_LEFT"
            text_anchor = "left"
        else:
            layout = "CENTERED_DYNAMIC"
            text_anchor = "bottom"

        # 3. Color Extraction
        colors = DynamicCompositionEngine.get_dominant_colors(img)
        
        return {
            "layout": layout,
            "text_anchor": text_anchor,
            "colors": colors,
            "subject_zone": subject_zone_idx,
            "dead_zone": dead_zone_idx,
            "aspect_ratio": width / height
        }

    @staticmethod
    def get_dominant_colors(img: Image.Image, k=3) -> List[str]:
        """
        Extracts dominant colors and provides a contrasting accent.
        """
        # Resize for faster processing
        img_small = img.resize((100, 100))
        pixels = list(img_small.getdata())
        
        # Simple color counting for speed
        from collections import Counter
        most_common = Counter(pixels).most_common(k)
        
        hex_colors = []
        for color, count in most_common:
            hex_colors.append('#{:02x}{:02x}{:02x}'.format(*color))
            
        # Add a high-contrast accent color (e.g., complementary to the primary)
        primary = most_common[0][0]
        accent = (255 - primary[0], 255 - primary[1], 255 - primary[2])
        hex_colors.append('#{:02x}{:02x}{:02x}'.format(*accent))
        
        return hex_colors

    @staticmethod
    def apply_editorial_vibe(prompt: str) -> str:
        """
        Injects the 'Senior Art Director' style into the image generation prompt.
        """
        vibe = (
            "Vintage Magazine Collage style, Punk Zine Protest Poster aesthetic. "
            "Asymmetrical balance with purposeful dead space. "
            "Tactile tactile layer, subtle film grain, analog print textures, torn paper edges. "
            "Dramatic side-lighting, high-contrast shadows. 35mm film look, unfiltered."
        )
        return f"{prompt}. {vibe}"

