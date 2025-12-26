"""
Swiss Water Network Loader

Efficiently load Swiss water network data (creeks, rivers, lakes) from geo.admin.ch APIs.
Uses the proper REST API for fast vector data retrieval.
"""

import logging
from typing import Optional, Tuple, List, Dict, Union
from dataclasses import dataclass

import requests
from shapely.geometry import LineString, Polygon, shape

logger = logging.getLogger(__name__)

# REST API endpoint
REST_API_URL = "https://api3.geo.admin.ch/rest/services/all/MapServer/identify"

# Vector layer for water network
WATER_NETWORK_LAYER = "ch.swisstopo.vec25-gewaessernetz_referenz"

# Water type mappings
WATER_TYPE_MAP = {
    "Bach": "creek",
    "Bach_U": "underground_creek",
    "Bachachs": "creek_axis",
    "Fluss": "river",
    "Seeachse": "lake_axis",
    "See": "lake"
}

# Default widths by type (meters)
WATER_WIDTHS = {
    "creek": 1.5,
    "underground_creek": 1.0,
    "creek_axis": 1.5,
    "river": 8.0,
    "lake_axis": 5.0,
    "lake": None  # Lakes use polygon geometry, not buffered lines
}


@dataclass
class WaterFeature:
    """Represents a water feature (creek, river, lake)."""
    id: str
    geometry: Union[LineString, Polygon]  # LineString for streams/rivers, Polygon for lakes
    water_type: str  # "creek", "river", "lake", etc.
    name: Optional[str] = None
    gewiss_number: Optional[int] = None  # GEWISS identifier
    width: Optional[float] = None  # Width in meters (for buffering)
    is_underground: bool = False
    attributes: Optional[Dict] = None


class SwissWaterLoader:
    """Load water network data from Swiss geo.admin.ch REST API."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "SiteBoundariesGeom/1.0 (Water Data Loader)"
        })
    
    def get_water_in_bounds(
        self,
        bounds: Tuple[float, float, float, float],
        fetch_elevations_func=None,
        max_features: int = 500
    ) -> List[WaterFeature]:
        """
        Get water features within bounds using REST API identify.
        
        Args:
            bounds: (minx, miny, maxx, maxy) in EPSG:2056
            fetch_elevations_func: Optional function to fetch elevations
            max_features: Maximum features to return
        
        Returns:
            List of WaterFeature objects
        """
        minx, miny, maxx, maxy = bounds
        
        # Expand map extent slightly for better coverage
        extent_buffer = 1000  # 1km buffer
        map_extent = f"{minx-extent_buffer},{miny-extent_buffer},{maxx+extent_buffer},{maxy+extent_buffer}"
        
        params = {
            "geometry": f"{minx},{miny},{maxx},{maxy}",
            "geometryType": "esriGeometryEnvelope",
            "layers": f"all:{WATER_NETWORK_LAYER}",
            "mapExtent": map_extent,
            "imageDisplay": "1000,1000,96",
            "tolerance": 0,
            "returnGeometry": "true",
            "sr": "2056",
        }
        
        try:
            response = self.session.get(REST_API_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            print(f"  Found {len(results)} water features via REST API")
            
            features = []
            for result in results[:max_features]:
                feature = self._parse_result(result)
                if feature:
                    features.append(feature)
            
            # Fetch elevations if function provided
            if features and fetch_elevations_func:
                print(f"  Fetching elevations for {len(features)} water features...")
                # Get representative points for elevation sampling
                coords = []
                for f in features:
                    if isinstance(f.geometry, LineString):
                        # Use midpoint of line
                        midpoint = f.geometry.interpolate(0.5, normalized=True)
                        coords.append((midpoint.x, midpoint.y))
                    elif isinstance(f.geometry, Polygon):
                        # Use centroid
                        coords.append((f.geometry.centroid.x, f.geometry.centroid.y))
                
                elevations = fetch_elevations_func(coords)
                # Store elevations in attributes for later use
                for feature, elev in zip(features, elevations):
                    if feature.attributes is None:
                        feature.attributes = {}
                    feature.attributes['elevation'] = elev
            
            return features
            
        except Exception as e:
            logger.error(f"REST API query failed: {e}")
            return []
    
    def _parse_result(self, result: Dict) -> Optional[WaterFeature]:
        """Parse a REST API result into a WaterFeature."""
        try:
            geom_data = result.get("geometry", {})
            attrs = result.get("attributes", {})
            feature_id = str(result.get("id", "unknown"))
            
            # Parse geometry - handle ESRI format (paths for lines, rings for polygons)
            geom = None
            if "paths" in geom_data:
                # LineString geometry (streams/rivers)
                paths = geom_data["paths"]
                if paths and len(paths) > 0:
                    # Use first path (most common case)
                    coords = [(p[0], p[1]) for p in paths[0]]
                    if len(coords) >= 2:
                        geom = LineString(coords)
            elif "rings" in geom_data:
                # Polygon geometry (lakes)
                rings = geom_data["rings"]
                if rings and len(rings) > 0:
                    # Use first ring (exterior)
                    coords = [(p[0], p[1]) for p in rings[0]]
                    if len(coords) >= 3:
                        geom = Polygon(coords)
            else:
                # Try shapely shape() as fallback
                try:
                    geom = shape(geom_data)
                except Exception:
                    pass
            
            if geom is None:
                logger.debug(f"Could not parse geometry for water feature {feature_id}")
                return None
            
            # Get water type
            obj_val = attrs.get("objectval", "")
            water_type = WATER_TYPE_MAP.get(obj_val, "creek")  # Default to creek
            
            # Determine if underground
            is_underground = water_type == "underground_creek"
            
            # Get name
            name = attrs.get("name", "").strip() or None
            
            # Get GEWISS number
            gewiss_nr = attrs.get("gewissnr")
            if gewiss_nr is not None:
                try:
                    gewiss_nr = int(gewiss_nr)
                except (ValueError, TypeError):
                    gewiss_nr = None
            
            # Get width based on type
            width = WATER_WIDTHS.get(water_type)
            
            # Validate geometry type
            if not isinstance(geom, (LineString, Polygon)):
                logger.debug(f"Unsupported geometry type: {type(geom)}")
                return None
            
            # Convert lakes to polygons if needed
            if water_type == "lake" and isinstance(geom, LineString):
                # If we got a line for a lake, buffer it slightly
                geom = geom.buffer(5.0)  # 5m buffer for lake representation
            
            return WaterFeature(
                id=feature_id,
                geometry=geom,
                water_type=water_type,
                name=name,
                gewiss_number=gewiss_nr,
                width=width,
                is_underground=is_underground,
                attributes=attrs
            )
            
        except Exception as e:
            logger.debug(f"Failed to parse result: {e}")
            return None
    
    def get_water_statistics(self, features: List[WaterFeature]) -> Dict:
        """Calculate statistics for water features."""
        if not features:
            return {
                "count": 0,
                "total_length_m": 0,
                "by_type": {}
            }
        
        total_length = 0
        by_type = {}
        
        for feature in features:
            # Count by type
            wtype = feature.water_type
            by_type[wtype] = by_type.get(wtype, 0) + 1
            
            # Calculate length
            if isinstance(feature.geometry, LineString):
                total_length += feature.geometry.length
            elif isinstance(feature.geometry, Polygon):
                total_length += feature.geometry.exterior.length
        
        return {
            "count": len(features),
            "total_length_m": total_length,
            "by_type": by_type
        }


def get_water_around_bounds(
    bounds: Tuple[float, float, float, float],
    fetch_elevations_func=None
) -> List[WaterFeature]:
    """
    Convenience function to get water features in an area.
    
    Args:
        bounds: (minx, miny, maxx, maxy) in EPSG:2056
        fetch_elevations_func: Optional elevation function
    
    Returns:
        List of WaterFeature objects
    """
    loader = SwissWaterLoader()
    return loader.get_water_in_bounds(bounds, fetch_elevations_func)

