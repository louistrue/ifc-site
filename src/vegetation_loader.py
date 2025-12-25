"""
Swiss Vegetation and Tree Data Loader

Efficiently load Swiss vegetation, forest, and tree data from geo.admin.ch APIs.
Integrates with existing terrain workflow for complete site context including natural features.
"""

import logging
import time
from typing import Optional, Tuple, List, Dict, Literal
from dataclasses import dataclass
from functools import wraps

import requests
from shapely.geometry import shape, box, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

try:
    from pyproj import Transformer
    PYPROJ_AVAILABLE = True
except ImportError:
    PYPROJ_AVAILABLE = False
    logging.warning("pyproj not available - coordinate conversion limited")


logger = logging.getLogger(__name__)


@dataclass
class VegetationFeature:
    """Represents a vegetation feature (forest area, tree, bush, etc.)"""
    id: str
    geometry: Polygon  # Forest polygon or tree canopy area
    vegetation_type: Optional[str] = None  # e.g., "Forest", "Sparse forest", "Bush forest", "Individual tree"
    tree_species: Optional[str] = None  # Tree species if available
    height: Optional[float] = None  # Vegetation height in meters
    canopy_area: Optional[float] = None  # Canopy area in m²
    density: Optional[str] = None  # e.g., "Dense", "Sparse"
    attributes: Optional[Dict] = None


def rate_limit(max_per_second: float):
    """
    Rate limiting decorator to prevent API abuse

    Args:
        max_per_second: Maximum requests per second
    """
    min_interval = 1.0 / max_per_second
    last_called = [0.0]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)

            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result

        return wrapper
    return decorator


class SwissVegetationLoader:
    """
    Load Swiss vegetation and forest data from geo.admin.ch APIs

    Supports multiple data sources:
    - swissTLM3D Forest - forest polygons with classification
    - Vegetation 3D - 3D vegetation objects (trees, bushes)
    - Vegetation Height Model - raster-based vegetation heights
    """

    # API Configuration
    REST_BASE = "https://api3.geo.admin.ch/rest/services"

    # Vegetation layer names
    FOREST_TLM3D = "ch.swisstopo.swisstlm3d-wald"  # Forest polygons
    VEGETATION_3D = "ch.swisstopo.vegetation.3d"  # 3D vegetation objects (limited support)
    VEG_HEIGHT_MODEL = "ch.swisstopo.swisseo_vhi_v100"  # Vegetation Health Index

    # Vegetation classification types
    VEGETATION_TYPES = {
        "Wald": "Forest",
        "Wald_offen": "Sparse forest",
        "Buschwald": "Bush forest",
        "Einzelbaum": "Individual tree",
        "Baumreihe": "Row of trees",
        "Hecke": "Hedge",
        "Gebueschwald": "Scrubland"
    }

    def __init__(
        self,
        timeout: int = 60,
        retry_count: int = 3
    ):
        """
        Initialize vegetation loader

        Args:
            timeout: Request timeout in seconds
            retry_count: Number of retries for failed requests
        """
        self.timeout = timeout
        self.retry_count = retry_count

        # Initialize coordinate transformer if available
        if PYPROJ_AVAILABLE:
            self.transformer_to_wgs84 = Transformer.from_crs(
                "EPSG:2056", "EPSG:4326", always_xy=True
            )
            self.transformer_to_2056 = Transformer.from_crs(
                "EPSG:4326", "EPSG:2056", always_xy=True
            )
        else:
            self.transformer_to_wgs84 = None
            self.transformer_to_2056 = None

        logger.info("SwissVegetationLoader initialized")

    def epsg2056_to_wgs84(self, x: float, y: float) -> Tuple[float, float]:
        """Convert EPSG:2056 to WGS84"""
        if self.transformer_to_wgs84:
            return self.transformer_to_wgs84.transform(x, y)
        else:
            # Rough approximation if pyproj not available
            lon = (x - 2600000) / 111320 + 7.44
            lat = (y - 1200000) / 111320 + 46.0
            return lon, lat

    def bbox_2056_to_wgs84(self, bbox: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
        """Convert bbox from EPSG:2056 to WGS84"""
        min_lon, min_lat = self.epsg2056_to_wgs84(bbox[0], bbox[1])
        max_lon, max_lat = self.epsg2056_to_wgs84(bbox[2], bbox[3])
        return (min_lon, min_lat, max_lon, max_lat)

    @rate_limit(max_per_second=5)
    def _request_with_retry(self, url: str, params: Dict, method: str = "GET") -> requests.Response:
        """
        Make HTTP request with retry logic

        Args:
            url: Request URL
            params: Query parameters
            method: HTTP method

        Returns:
            Response object

        Raises:
            requests.RequestException: If all retries fail
        """
        if self.retry_count < 1:
            raise ValueError("retry_count must be at least 1")

        last_exception = None

        for attempt in range(self.retry_count):
            try:
                if method.upper() == "GET":
                    response = requests.get(url, params=params, timeout=self.timeout)
                else:
                    response = requests.post(url, params=params, timeout=self.timeout)

                response.raise_for_status()
                return response

            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.retry_count}): {e}")

                if attempt < self.retry_count - 1:
                    # Exponential backoff
                    time.sleep(2 ** attempt)

        if last_exception is None:
            raise RuntimeError("Request failed but no exception was captured")
        raise last_exception

    def get_vegetation_rest(
        self,
        bbox_2056: Tuple[float, float, float, float],
        layer: str = None,
        max_features: int = 1000
    ) -> List[VegetationFeature]:
        """
        Get vegetation using REST API MapServer Identify endpoint

        Args:
            bbox_2056: Bounding box (min_x, min_y, max_x, max_y) in EPSG:2056
            layer: Layer to query (default: FOREST_TLM3D)
            max_features: Maximum number of vegetation features to return

        Returns:
            List of VegetationFeature objects with geometry
        """
        if layer is None:
            layer = self.FOREST_TLM3D

        logger.info(f"Fetching vegetation via REST API in bbox: {bbox_2056}, layer: {layer}")

        url = f"{self.REST_BASE}/api/MapServer/identify"
        params = {
            "geometryType": "esriGeometryEnvelope",
            "geometry": f"{bbox_2056[0]},{bbox_2056[1]},{bbox_2056[2]},{bbox_2056[3]}",
            "layers": f"all:{layer}",
            "mapExtent": f"{bbox_2056[0]},{bbox_2056[1]},{bbox_2056[2]},{bbox_2056[3]}",
            "imageDisplay": "1000,1000,96",
            "tolerance": 0,
            "returnGeometry": "true",
            "geometryFormat": "geojson",
            "sr": "2056"
        }

        try:
            response = self._request_with_retry(url, params)
            data = response.json()

            vegetation = []
            for result in data.get("results", []):
                if max_features > 0 and len(vegetation) >= max_features:
                    break
                veg = self._parse_rest_result(result)
                if veg:
                    vegetation.append(veg)

            logger.info(f"Retrieved {len(vegetation)} vegetation features via REST API")
            return vegetation

        except Exception as e:
            logger.error(f"REST API request failed: {e}")
            raise

    def _parse_rest_result(self, result: Dict) -> Optional[VegetationFeature]:
        """
        Parse a REST API identify result into VegetationFeature

        Args:
            result: REST API result dict

        Returns:
            VegetationFeature or None if invalid
        """
        try:
            # Parse geometry
            geom_data = result.get("geometry", {})
            if not geom_data:
                return None

            geom = shape(geom_data)

            # Handle MultiPolygon by taking the largest polygon
            if geom.geom_type == "MultiPolygon":
                if geom.geoms:
                    largest = max(geom.geoms, key=lambda p: p.area)
                    geom = largest
                else:
                    return None

            # Convert point to small polygon (tree canopy approximation)
            if geom.geom_type == "Point":
                # Approximate tree canopy as 5m radius circle
                geom = geom.buffer(5.0)

            # Extract to 2D if 3D
            if hasattr(geom, 'has_z') and geom.has_z:
                coords = [(x, y) for x, y, *_ in geom.exterior.coords]
                geom = Polygon(coords)

            # Validate
            if not isinstance(geom, Polygon):
                logger.debug(f"Skipping non-polygon geometry: {geom.geom_type}")
                return None

            # Extract properties
            attrs = result.get("attributes", {})
            feature_id = str(result.get("id", attrs.get("id", "unknown")))

            # Parse vegetation type and attributes
            veg_type = attrs.get("objektart") or attrs.get("vegetation_type")
            # Translate German to English if in VEGETATION_TYPES
            if veg_type and veg_type in self.VEGETATION_TYPES:
                veg_type = self.VEGETATION_TYPES[veg_type]

            tree_species = attrs.get("baumart") or attrs.get("species")
            height = attrs.get("hoehe") or attrs.get("height")
            density = attrs.get("dichte") or attrs.get("density")

            # Calculate canopy area
            canopy_area = geom.area if geom and hasattr(geom, 'area') else None

            return VegetationFeature(
                id=feature_id,
                geometry=geom,
                vegetation_type=veg_type,
                tree_species=tree_species,
                height=float(height) if height else None,
                canopy_area=canopy_area,
                density=density,
                attributes=attrs
            )

        except Exception as e:
            logger.warning(f"Failed to parse REST result: {e}")
            return None

    def get_vegetation_around_point(
        self,
        x: float,
        y: float,
        radius: float = 500,
        layer: str = None
    ) -> List[VegetationFeature]:
        """
        Get vegetation within radius of a point

        Args:
            x: X coordinate in EPSG:2056
            y: Y coordinate in EPSG:2056
            radius: Radius in meters
            layer: Layer to query (default: FOREST_TLM3D)

        Returns:
            List of VegetationFeature objects
        """
        # Create bbox
        bbox = (x - radius, y - radius, x + radius, y + radius)

        vegetation = self.get_vegetation_rest(bbox, layer=layer)

        # Filter to circular area
        center = Point(x, y)
        filtered = [
            v for v in vegetation
            if v.geometry.distance(center) <= radius
        ]

        logger.info(f"Filtered {len(filtered)}/{len(vegetation)} vegetation features within {radius}m radius")
        return filtered

    def get_vegetation_on_parcel(
        self,
        egrid: str,
        buffer_m: float = 0
    ) -> List[VegetationFeature]:
        """
        Get vegetation on or near a cadastral parcel

        Args:
            egrid: Swiss EGRID identifier
            buffer_m: Buffer around parcel boundary in meters

        Returns:
            List of VegetationFeature objects
        """
        logger.info(f"Fetching vegetation for EGRID: {egrid}")

        # Import here to avoid circular dependency
        from src.terrain_with_site import fetch_boundary_by_egrid

        # Get parcel boundary
        site_boundary, metadata = fetch_boundary_by_egrid(egrid)
        if site_boundary is None:
            logger.warning(f"No boundary found for EGRID {egrid}")
            return []

        # Create bbox with buffer
        bounds = site_boundary.bounds
        bbox = (
            bounds[0] - buffer_m,
            bounds[1] - buffer_m,
            bounds[2] + buffer_m,
            bounds[3] + buffer_m
        )

        # Get vegetation in bbox
        vegetation = self.get_vegetation_rest(bbox)

        # Filter to vegetation that intersects the parcel (with buffer)
        if buffer_m > 0:
            search_area = site_boundary.buffer(buffer_m)
        else:
            search_area = site_boundary

        filtered_vegetation = [
            v for v in vegetation
            if search_area.intersects(v.geometry)
        ]

        logger.info(
            f"Found {len(filtered_vegetation)} vegetation features on parcel "
            f"(buffer: {buffer_m}m)"
        )

        return filtered_vegetation

    def get_vegetation_statistics(
        self,
        vegetation: List[VegetationFeature]
    ) -> Dict:
        """
        Calculate statistics for a list of vegetation features

        Args:
            vegetation: List of VegetationFeature objects

        Returns:
            Dictionary with statistics
        """
        if not vegetation:
            return {
                "count": 0,
                "total_canopy_area_m2": 0,
                "avg_canopy_area_m2": 0,
                "avg_height_m": 0,
                "max_height_m": 0,
                "vegetation_types": {}
            }

        heights = [v.height for v in vegetation if v.height is not None]
        canopy_areas = [v.canopy_area for v in vegetation if v.canopy_area is not None]

        # Count by vegetation type
        type_counts = {}
        for veg in vegetation:
            veg_type = veg.vegetation_type or "Unknown"
            type_counts[veg_type] = type_counts.get(veg_type, 0) + 1

        return {
            "count": len(vegetation),
            "total_canopy_area_m2": sum(canopy_areas) if canopy_areas else 0,
            "avg_canopy_area_m2": sum(canopy_areas) / len(canopy_areas) if canopy_areas else 0,
            "avg_height_m": sum(heights) / len(heights) if heights else 0,
            "max_height_m": max(heights) if heights else 0,
            "vegetation_types": type_counts
        }


# Convenience functions

def get_vegetation_around_egrid(
    egrid: str,
    buffer_m: float = 0
) -> Tuple[List[VegetationFeature], Dict]:
    """
    Get vegetation around a cadastral parcel identified by EGRID

    Args:
        egrid: Swiss EGRID identifier
        buffer_m: Buffer around parcel boundary

    Returns:
        Tuple of (vegetation list, statistics dict)
    """
    loader = SwissVegetationLoader()
    vegetation = loader.get_vegetation_on_parcel(egrid, buffer_m)
    stats = loader.get_vegetation_statistics(vegetation)

    return vegetation, stats


def get_vegetation_in_bbox(
    bbox_2056: Tuple[float, float, float, float],
    layer: str = None
) -> Tuple[List[VegetationFeature], Dict]:
    """
    Get vegetation in bounding box

    Args:
        bbox_2056: Bounding box (min_x, min_y, max_x, max_y) in EPSG:2056
        layer: Layer to query (default: swissTLM3D forest)

    Returns:
        Tuple of (vegetation list, statistics dict)
    """
    loader = SwissVegetationLoader()
    vegetation = loader.get_vegetation_rest(bbox_2056, layer=layer)
    stats = loader.get_vegetation_statistics(vegetation)

    return vegetation, stats


if __name__ == "__main__":
    """Example usage"""
    import sys

    logging.basicConfig(level=logging.INFO)

    # Example 1: Get vegetation in bbox
    print("\n" + "="*80)
    print("Example 1: Get vegetation in bounding box (Zurich area)")
    print("="*80)

    bbox = (2682500, 1247500, 2683000, 1248000)  # 500m x 500m
    try:
        vegetation, stats = get_vegetation_in_bbox(bbox)
        print(f"\nStatistics:")
        for key, value in stats.items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value:.1f}" if isinstance(value, float) else f"  {key}: {value}")
    except Exception as e:
        print(f"Error: {e}")

    # Example 2: Get vegetation on parcel
    if len(sys.argv) > 1:
        print("\n" + "="*80)
        print(f"Example 2: Get vegetation for EGRID: {sys.argv[1]}")
        print("="*80)

        try:
            vegetation, stats = get_vegetation_around_egrid(sys.argv[1], buffer_m=10)
            print(f"\nStatistics:")
            for key, value in stats.items():
                if isinstance(value, dict):
                    print(f"  {key}:")
                    for k, v in value.items():
                        print(f"    {k}: {v}")
                else:
                    print(f"  {key}: {value:.1f}" if isinstance(value, float) else f"  {key}: {value}")
        except Exception as e:
            print(f"Error: {e}")
