"""
Tree and vegetation data loader using Swiss geo.admin.ch REST API.

Uses the proper vector-based ch.swisstopo.vec25-heckenbaeume layer which provides
actual tree and hedge geometries (not raster data).

This replaces the slow raster-based approach with a fast REST API query.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import requests
from shapely.geometry import LineString, Point, Polygon

logger = logging.getLogger(__name__)

# REST API endpoint
REST_API_URL = "https://api3.geo.admin.ch/rest/services/all/MapServer/identify"

# Vector layer for trees and hedges (proper REST API support)
TREES_HEDGES_LAYER = "ch.swisstopo.vec25-heckenbaeume"


@dataclass
class TreeFeature:
    """Represents a tree or hedge feature from vector data."""
    id: str
    geometry: LineString  # Original line geometry
    x: float  # Centroid X
    y: float  # Centroid Y
    z: float  # Elevation (filled later)
    length: float  # Length of hedge/tree row in meters
    feature_type: str  # "hedge" or "tree_row"
    
    @property
    def tree_type(self) -> str:
        """Returns tree type - alternates based on ID for variety."""
        # Use feature ID to create variety
        return "deciduous" if hash(self.id) % 2 == 0 else "coniferous"


class SwissTreeLoader:
    """Load tree and hedge data from Swiss geo.admin.ch REST API."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "SiteBoundariesGeom/1.0 (Tree Data Loader)"
        })
    
    def get_trees_in_bounds(
        self,
        bounds: Tuple[float, float, float, float],
        fetch_elevations_func=None,
        max_features: int = 500
    ) -> List[TreeFeature]:
        """
        Get tree/hedge features within bounds using REST API identify.
        
        This is the PROPER API method - fast and returns actual vector geometries.
        
        Args:
            bounds: (minx, miny, maxx, maxy) in EPSG:2056
            fetch_elevations_func: Optional function to fetch elevations
            max_features: Maximum features to return
        
        Returns:
            List of TreeFeature objects
        """
        minx, miny, maxx, maxy = bounds
        
        # Expand map extent slightly for better coverage
        extent_buffer = 1000  # 1km buffer
        map_extent = f"{minx-extent_buffer},{miny-extent_buffer},{maxx+extent_buffer},{maxy+extent_buffer}"
        
        params = {
            "geometry": f"{minx},{miny},{maxx},{maxy}",
            "geometryType": "esriGeometryEnvelope",
            "layers": f"all:{TREES_HEDGES_LAYER}",
            "mapExtent": map_extent,
            "imageDisplay": "1000,1000,96",
            "tolerance": 0,
            "returnGeometry": "true",
            "sr": "2056",
        }
        
        try:
            print(f"  Querying forest API for bounds {bounds}...")
            response = self.session.get(REST_API_URL, params=params, timeout=30)
            response.raise_for_status()
            print(f"  Forest API query completed")
            data = response.json()

            results = data.get("results", [])
            print(f"  Found {len(results)} tree/hedge features via REST API")
            
            features = []
            for result in results[:max_features]:
                feature = self._parse_result(result)
                if feature:
                    features.append(feature)
            
            # Fetch elevations if function provided
            if features and fetch_elevations_func:
                print(f"  Fetching elevations for {len(features)} features...")
                coords = [(f.x, f.y) for f in features]
                elevations = fetch_elevations_func(coords)
                for feature, elev in zip(features, elevations, strict=True):
                    feature.z = elev
            
            return features
            
        except Exception as e:
            logger.error(f"REST API query failed: {e}")
            return []
    
    def _parse_result(self, result: Dict) -> Optional[TreeFeature]:
        """Parse a REST API result into a TreeFeature."""
        try:
            geom_data = result.get("geometry", {})
            attrs = result.get("attributes", {})
            feature_id = str(result.get("id", "unknown"))
            
            # Parse line geometry (paths)
            paths = geom_data.get("paths", [])
            if not paths or not paths[0]:
                return None
            
            coords = [(p[0], p[1]) for p in paths[0]]
            if len(coords) < 2:
                return None
            
            line = LineString(coords)
            centroid = line.centroid
            
            # Get length from attributes or calculate
            length = attrs.get("length", line.length)
            
            # Determine feature type based on length
            # Short features (< 50m) are typically individual trees/small hedges
            # Longer features are hedge rows
            feature_type = "tree_row" if length > 50 else "hedge"
            
            return TreeFeature(
                id=feature_id,
                geometry=line,
                x=centroid.x,
                y=centroid.y,
                z=0.0,
                length=float(length),
                feature_type=feature_type
            )
            
        except Exception as e:
            logger.debug(f"Failed to parse result: {e}")
            return None


# Legacy compatibility - keep old class name as alias
SwissForestLoader = SwissTreeLoader


@dataclass  
class ForestPoint:
    """Legacy compatibility - maps to TreeFeature."""
    x: float
    y: float
    z: float
    has_forest: bool
    deciduous_ratio: float
    
    @property
    def is_deciduous(self) -> bool:
        return self.deciduous_ratio >= 0.5
    
    @property
    def tree_type(self) -> str:
        if not self.has_forest:
            return "none"
        return "deciduous" if self.is_deciduous else "coniferous"


def get_forest_around_bounds(
    bounds: Tuple[float, float, float, float],
    spacing: float = 20.0,  # Ignored - kept for compatibility
    threshold: float = 0.0,  # Ignored - kept for compatibility
    fetch_elevations_func=None
) -> List[ForestPoint]:
    """
    Get tree positions in an area using proper REST API.
    
    Note: This now uses the vector-based tree layer instead of raster sampling.
    The spacing and threshold parameters are kept for backward compatibility
    but are not used.
    
    Args:
        bounds: (minx, miny, maxx, maxy) in EPSG:2056
        spacing: Ignored (kept for compatibility)
        threshold: Ignored (kept for compatibility)
        fetch_elevations_func: Optional elevation function
    
    Returns:
        List of ForestPoint objects (one per tree/hedge)
    """
    loader = SwissTreeLoader()
    features = loader.get_trees_in_bounds(bounds, fetch_elevations_func)
    
    # Convert TreeFeature to ForestPoint for compatibility
    # Place trees along the hedge/tree row lines
    forest_points = []
    
    for feature in features:
        # For each hedge/tree row, place trees along the line
        line = feature.geometry
        length = feature.length
        
        # Determine tree spacing based on feature type
        if feature.feature_type == "hedge":
            tree_spacing = 8.0  # Dense hedge: tree every 8m
        else:
            tree_spacing = 15.0  # Tree row: tree every 15m
        
        # Calculate number of trees along the line
        num_trees = max(1, int(length / tree_spacing))
        
        for i in range(num_trees):
            # Position along the line (0.0 to 1.0)
            t = (i + 0.5) / num_trees
            point = line.interpolate(t, normalized=True)
            
            # Alternate tree types along the line
            is_deciduous = (hash(feature.id) + i) % 2 == 0
            
            forest_points.append(ForestPoint(
                x=point.x,
                y=point.y,
                z=feature.z,
                has_forest=True,
                deciduous_ratio=1.0 if is_deciduous else 0.0
            ))
    
    print(f"  Generated {len(forest_points)} tree positions from {len(features)} hedge/tree features")
    return forest_points

