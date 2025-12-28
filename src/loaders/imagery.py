"""
Swiss Imagery Loader - SWISSIMAGE Orthophoto from geo.admin.ch WMS

Fetches orthophoto imagery from Swiss Federal Office of Topography
using WMS GetMap for texture mapping.
"""

import logging
import os
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Tuple, Optional
from pathlib import Path

import requests
from PIL import Image
import requests_cache

logger = logging.getLogger(__name__)

# WMS URL for SWISSIMAGE
WMS_URL = "https://wms.geo.admin.ch/"
SWISSIMAGE_LAYER = "ch.swisstopo.swissimage"

# Maximum image size (WMS has limits)
MAX_IMAGE_SIZE = 4096

# Rate limiting: 20 requests per minute
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW = 60  # seconds


@dataclass
class ImageryData:
    """Represents fetched imagery data."""
    image: bytes          # JPEG/PNG data
    bounds: Tuple[float, float, float, float]  # (minx, miny, maxx, maxy) in EPSG:2056
    width: int            # Image width in pixels
    height: int           # Image height in pixels
    resolution_m: float   # meters per pixel


class SwissImageryLoader:
    """Load SWISSIMAGE orthophoto from geo.admin.ch WMS service."""
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize the imagery loader.
        
        Args:
            cache_dir: Directory for cache (default: ~/.cache/swissimage)
        """
        # Setup caching with SQLite backend
        if cache_dir is None:
            cache_dir = str(Path.home() / ".cache" / "swissimage")
        os.makedirs(cache_dir, exist_ok=True)
        
        cache_path = os.path.join(cache_dir, "wms_cache.sqlite")
        self.session = requests_cache.CachedSession(
            cache_path,
            expire_after=30 * 24 * 60 * 60,  # 30 days
            backend='sqlite'
        )
        self.session.headers.update({
            "User-Agent": "SwissSiteModel/1.0"
        })
        
        # Rate limiting state
        self.request_times = []
    
    def _check_rate_limit(self):
        """Ensure we don't exceed rate limits."""
        now = time.time()
        # Remove requests older than the window
        self.request_times = [t for t in self.request_times if now - t < RATE_LIMIT_WINDOW]
        
        if len(self.request_times) >= RATE_LIMIT_REQUESTS:
            # Wait until we can make another request
            oldest = min(self.request_times)
            wait_time = RATE_LIMIT_WINDOW - (now - oldest) + 0.1
            if wait_time > 0:
                logger.debug(f"Rate limit reached, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                # Clean up again after waiting
                now = time.time()
                self.request_times = [t for t in self.request_times if now - t < RATE_LIMIT_WINDOW]
        
        self.request_times.append(time.time())
    
    def get_orthophoto_for_bbox(
        self,
        bbox_2056: Tuple[float, float, float, float],
        resolution_m: float = 0.5,
        year: str = "current"
    ) -> Optional[Tuple[bytes, Tuple[float, float, float, float]]]:
        """
        Fetch orthophoto image covering bounding box using WMS GetMap.
        
        Args:
            bbox_2056: Bounding box (minx, miny, maxx, maxy) in EPSG:2056
            resolution_m: Desired resolution in meters per pixel (default: 0.5)
            year: Year string (not used for WMS, kept for API compatibility)
            
        Returns:
            Tuple of (image_bytes, bbox) or None if failed
        """
        minx, miny, maxx, maxy = bbox_2056
        
        # Calculate image dimensions based on desired resolution
        width_m = maxx - minx
        height_m = maxy - miny
        
        width_px = int(width_m / resolution_m)
        height_px = int(height_m / resolution_m)
        
        # Limit image size
        if width_px > MAX_IMAGE_SIZE:
            width_px = MAX_IMAGE_SIZE
            resolution_m = width_m / width_px
        if height_px > MAX_IMAGE_SIZE:
            height_px = MAX_IMAGE_SIZE
            resolution_m = max(resolution_m, height_m / height_px)
        
        # Recalculate with consistent resolution
        width_px = int(width_m / resolution_m)
        height_px = int(height_m / resolution_m)
        
        print(f"  Fetching SWISSIMAGE via WMS ({width_px}x{height_px} pixels, {resolution_m:.2f}m/pixel)...")
        
        self._check_rate_limit()
        
        # Build WMS GetMap request
        params = {
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'REQUEST': 'GetMap',
            'LAYERS': SWISSIMAGE_LAYER,
            'CRS': 'EPSG:2056',
            'BBOX': f'{minx},{miny},{maxx},{maxy}',
            'WIDTH': width_px,
            'HEIGHT': height_px,
            'FORMAT': 'image/jpeg'
        }
        
        try:
            response = self.session.get(WMS_URL, params=params, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"WMS request failed: HTTP {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
                return None
            
            content_type = response.headers.get('content-type', '')
            if 'image' not in content_type:
                logger.error(f"Invalid content type: {content_type}")
                logger.error(f"Response: {response.text[:500]}")
                return None
            
            image_bytes = response.content
            
            # Verify it's a valid image
            try:
                img = Image.open(BytesIO(image_bytes))
                actual_width, actual_height = img.size
                print(f"  Successfully fetched {actual_width}x{actual_height} pixel image")
                print(f"  Image bounds: E {minx:.1f}-{maxx:.1f}, N {miny:.1f}-{maxy:.1f}")
            except Exception as e:
                logger.error(f"Invalid image data: {e}")
                return None
            
            return image_bytes, bbox_2056
            
        except requests.Timeout:
            logger.error("WMS request timed out")
            return None
        except Exception as e:
            logger.error(f"Error fetching WMS image: {e}")
            import traceback
            traceback.print_exc()
            return None

