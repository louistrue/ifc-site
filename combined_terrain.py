#!/usr/bin/env python3
"""
Combined Terrain with Site Cutout

This script creates a single IFC file containing:
- Surrounding terrain mesh with a hole cut out for the site
- Site solid with smoothed surface, height-adjusted to align with terrain edges

Usage:
    python combined_terrain.py --egrid CH999979659148 --radius 500 --resolution 20 --output combined.ifc
"""

import numpy as np
import requests
import ifcopenshell
import ifcopenshell.api
from shapely.geometry import shape, Point, Polygon, MultiPolygon
from shapely.ops import triangulate
from shapely.geometry.polygon import orient
import argparse
import time
import sys
import math
import json
import struct
import subprocess
import tempfile
import os
import concurrent.futures
try:
    import trimesh
except ImportError:
    trimesh = None
try:
    import DracoPy
except ImportError:
    DracoPy = None
from pyproj import Transformer
try:
    import pygltflib
except ImportError:
    pygltflib = None


# Cache for geoid undulation values to avoid redundant API calls
_geoid_cache = {}


def fetch_geoid_undulation(x_lv95, y_lv95):
    """
    Fetch the geoid undulation (difference between ellipsoidal and orthometric height)
    at a given LV95 location using the Swisstopo REFRAME API.
    
    Returns: Geoid undulation in meters (ellipsoidal - orthometric)
    """
    # Round to 100m grid for caching (geoid varies slowly)
    cache_key = (round(x_lv95 / 100) * 100, round(y_lv95 / 100) * 100)
    
    if cache_key in _geoid_cache:
        return _geoid_cache[cache_key]
    
    try:
        # Use REFRAME API to convert from LV95+LN02 to WGS84
        # The difference in altitude gives us the geoid undulation
        url = "https://geodesy.geo.admin.ch/reframe/lv95towgs84"
        params = {
            "easting": x_lv95,
            "northing": y_lv95,
            "altitude": 0,  # Reference orthometric height
            "format": "json"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # The returned altitude is the ellipsoidal height for 0m orthometric
        # So the geoid undulation = returned_altitude - 0 = returned_altitude
        geoid_undulation = float(data.get("altitude", 47.5))  # Default ~47.5m for Switzerland
        
        _geoid_cache[cache_key] = geoid_undulation
        return geoid_undulation
        
    except Exception as e:
        print(f"  Warning: Could not fetch geoid undulation: {e}")
        # Fallback: use average Swiss geoid undulation (~47.5m)
        return 47.5


def fetch_boundary_by_egrid(egrid):
    """
    Fetch the cadastral boundary (Polygon) and metadata for a given EGRID via geo.admin.ch API.
    Returns tuple: (Shapely geometry in EPSG:2056, metadata dict)
    """
    url = "https://api3.geo.admin.ch/rest/services/ech/MapServer/find"
    params = {
        "layer": "ch.kantone.cadastralwebmap-farbe",
        "searchText": egrid,
        "searchField": "egris_egrid",
        "returnGeometry": "true",
        "geometryFormat": "geojson",
        "sr": "2056"
    }
    
    print(f"Fetching boundary for EGRID {egrid}...")
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    if not data.get("results"):
        print(f"No results found for EGRID {egrid}")
        return None, None
    
    feature = data["results"][0]
    geometry = shape(feature["geometry"])
    
    # Extract cadastre metadata (API uses 'properties' when geometry is included)
    attributes = feature.get("properties", {}) or feature.get("attributes", {})
    
    # Calculate area from geometry (in m² since EPSG:2056 is in meters)
    area_m2 = geometry.area
    
    metadata = {
        "egrid": egrid,
        "canton": attributes.get("ak", ""),
        "parcel_number": attributes.get("number", ""),
        "local_id": attributes.get("identnd", ""),
        "geoportal_url": attributes.get("geoportal_url", ""),
        "realestate_type": attributes.get("realestate_type", ""),
        "area_m2": round(area_m2, 2),
        "perimeter_m": round(geometry.length, 2),
    }
    
    # Print metadata
    if metadata["canton"]:
        print(f"  Canton: {metadata['canton']}")
    if metadata["parcel_number"]:
        print(f"  Parcel Number: {metadata['parcel_number']}")
    print(f"  Area: {metadata['area_m2']:.1f} m² ({metadata['area_m2']/10000:.3f} ha)")
    print(f"  Perimeter: {metadata['perimeter_m']:.1f} m")
    
    return geometry, metadata


def fetch_elevation_batch(coords, batch_size=50, max_workers=20):
    """
    Fetch elevations for a list of coordinates via geo.admin.ch REST height service.
    Uses parallel requests for improved performance.
    """
    url = "https://api3.geo.admin.ch/rest/services/height"
    total = len(coords)
    
    def fetch_one(coord):
        x, y = coord
        try:
            res = requests.get(url, params={"easting": x, "northing": y, "sr": "2056"}, timeout=10)
            res.raise_for_status()
            return float(res.json()["height"])
        except Exception:
            return None
    
    print(f"Fetching elevations for {total} points (parallel, {max_workers} workers)...")
    
    # Fetch all elevations in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        elevations = list(executor.map(fetch_one, coords))
    
    # Handle failures with fallback to neighbor values
    failed_count = sum(1 for e in elevations if e is None)
    if failed_count > 0:
        print(f"  Warning: {failed_count} points failed, using interpolation")
        # Fill None values with neighbors
        for i, e in enumerate(elevations):
            if e is None:
                # Try previous value
                if i > 0 and elevations[i-1] is not None:
                    elevations[i] = elevations[i-1]
                # Try next value
                elif i < len(elevations) - 1 and elevations[i+1] is not None:
                    elevations[i] = elevations[i+1]
                # Fallback to 0.0
                else:
                    elevations[i] = 0.0
    
    return elevations


def _geometry_has_z(coords):
    """Recursively check if a GeoJSON coordinate array contains Z values."""
    if not coords:
        return False
    first = coords[0]
    if isinstance(first, (float, int)):
        return len(coords) >= 3
    return any(_geometry_has_z(part) for part in coords)


def _collect_z_range_from_geojson(geometry):
    """Collect minimum and maximum Z values from a GeoJSON geometry."""
    z_values = []

    def _walk(values):
        if isinstance(values, (list, tuple)):
            if values and isinstance(values[0], (int, float)):
                if len(values) >= 3:
                    z_values.append(float(values[2]))
            else:
                for value in values:
                    _walk(value)

    _walk(geometry.get("coordinates", []))
    if not z_values:
        return None, None
    return min(z_values), max(z_values)


def _nearest_terrain_height(x, y, terrain_coords, terrain_elevations, default=0.0):
    """Find nearest terrain elevation for a point."""
    if not terrain_coords or not terrain_elevations:
        return default

    try:
        from scipy.spatial import KDTree
    except ImportError:
        KDTree = None

    if KDTree:
        tree = KDTree(terrain_coords)
        dist, idx = tree.query([[x, y]], k=1)
        if idx is None or len(idx) == 0:
            return default
        return float(terrain_elevations[int(idx[0])])

    best_idx = 0
    best_dist = float("inf")
    for idx, (tx, ty) in enumerate(terrain_coords):
        dist = (tx - x) ** 2 + (ty - y) ** 2
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return float(terrain_elevations[best_idx])


class TerrainIndex:
    """Spatial index wrapper for terrain points (KDTree when available)."""

    def __init__(self, coords, elevations):
        self.coords = coords
        self.elevations = elevations
        self.tree = None
        if coords and elevations:
            try:
                from scipy.spatial import KDTree
                self.tree = KDTree(coords)
            except ImportError:
                self.tree = None

    def nearest_height(self, x, y, default=0.0):
        if not self.coords or not self.elevations:
            return default
        if self.tree:
            dist, idx = self.tree.query([[x, y]], k=1)
            if idx is None or len(idx) == 0:
                return default
            return float(self.elevations[int(idx[0])])
        # Fallback linear scan
        best_idx = 0
        best_dist = float("inf")
        for i, (tx, ty) in enumerate(self.coords):
            dist = (tx - x) ** 2 + (ty - y) ** 2
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        return float(self.elevations[best_idx])


def _get_attr_float(attrs, keys):
    """Return the first available attribute from keys as float."""
    for key in keys:
        value = attrs.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _estimate_building_height(attrs, default_height=10.0):
    """Heuristic to estimate building height from swissBUILDINGS3D attributes."""
    height_keys = [
        "height",
        "HEIGHT",
        "H_GEB",
        "h_mean",
        "hmax",
        "z_max",
        "zmin",
        "zmax",
        "hroof",
        "roof_height",
        "buildingheight",
    ]
    height = _get_attr_float(attrs, height_keys)
    if height is None or height <= 0:
        return default_height
    return height


def _close_ring(ring):
    """Ensure a ring is closed by repeating the first coordinate if needed."""
    if not ring:
        return []
    if ring[0] != ring[-1]:
        return [*ring, ring[0]]
    return ring


# ============================================================================
# 3D Tiles (b3dm) Support Functions
# ============================================================================

def _region_to_bbox(region):
    """
    Convert Cesium region [west, south, east, north, min_height, max_height] to bbox.
    Region is in radians (WGS84).
    """
    west, south, east, north, min_h, max_h = region
    # Convert radians to degrees
    west_deg = math.degrees(west)
    south_deg = math.degrees(south)
    east_deg = math.degrees(east)
    north_deg = math.degrees(north)
    return (west_deg, south_deg, east_deg, north_deg)


def _bbox_intersects_region(bbox_lv95, region, buffer_meters=500):
    """
    Check if EPSG:2056 bbox intersects with Cesium region.
    bbox_lv95: (minx, miny, maxx, maxy) in EPSG:2056
    region: [west, south, east, north, min_height, max_height] in radians
    buffer_meters: Buffer distance in meters to include nearby tiles
    """
    if not region or len(region) < 4:
        return True  # If no region info, include it
    
    # Transform bbox to WGS84 for comparison
    transformer = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
    minx, miny, maxx, maxy = bbox_lv95
    
    # Transform bbox corners to WGS84
    corners_lv95 = [
        (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy),
        ((minx + maxx) / 2, (miny + maxy) / 2)  # Center point
    ]
    corners_wgs84 = [transformer.transform(x, y) for x, y in corners_lv95]
    
    west, south, east, north, _, _ = region
    west_deg = math.degrees(west)
    south_deg = math.degrees(south)
    east_deg = math.degrees(east)
    north_deg = math.degrees(north)
    
    # Check if any bbox corner is in region
    for lon, lat in corners_wgs84:
        if west_deg <= lon <= east_deg and south_deg <= lat <= north_deg:
            return True
    
    # Check if region center is in bbox
    center_lon = (west_deg + east_deg) / 2
    center_lat = (south_deg + north_deg) / 2
    center_x, center_y = transformer.transform(center_lon, center_lat, direction="INVERSE")
    if minx <= center_x <= maxx and miny <= center_y <= maxy:
        return True
    
    # Check if bbox overlaps region (more comprehensive check)
    bbox_min_lon = min(lon for lon, lat in corners_wgs84)
    bbox_max_lon = max(lon for lon, lat in corners_wgs84)
    bbox_min_lat = min(lat for lon, lat in corners_wgs84)
    bbox_max_lat = max(lat for lon, lat in corners_wgs84)
    
    # Check for overlap: regions overlap if they don't NOT overlap
    # Two boxes overlap if: max_lon >= min_lon AND max_lat >= min_lat (for both)
    if not (bbox_max_lon < west_deg or bbox_min_lon > east_deg or 
            bbox_max_lat < south_deg or bbox_min_lat > north_deg):
        return True
    
    # Also check in EPSG:2056 for more accurate overlap detection
    # Transform region corners to EPSG:2056
    transformer_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
    region_corners_wgs84 = [
        (west_deg, south_deg), (east_deg, south_deg),
        (east_deg, north_deg), (west_deg, north_deg)
    ]
    region_corners_lv95 = [transformer_lv95.transform(lon, lat) for lon, lat in region_corners_wgs84]
    region_min_x = min(x for x, y in region_corners_lv95)
    region_max_x = max(x for x, y in region_corners_lv95)
    region_min_y = min(y for x, y in region_corners_lv95)
    region_max_y = max(y for x, y in region_corners_lv95)
    
    # Expand bbox by buffer to include nearby tiles
    expanded_minx = minx - buffer_meters
    expanded_miny = miny - buffer_meters
    expanded_maxx = maxx + buffer_meters
    expanded_maxy = maxy + buffer_meters
    
    # Check overlap in EPSG:2056 (with buffer)
    if not (region_max_x < expanded_minx or region_min_x > expanded_maxx or 
            region_max_y < expanded_miny or region_min_y > expanded_maxy):
        return True
    
    return False


def calculate_tile_coordinates(bbox_lv95, zoom_level=11):
    """
    Calculate which 3D Tiles cover the given EPSG:2056 bounding box.
    Returns list of (z, x, y) tile coordinates.
    
    Note: This is approximate - 3D Tiles use a quadtree structure based on
    geographic regions, not a simple tile grid like web maps.
    """
    # Transform bbox to WGS84
    transformer = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
    minx, miny, maxx, maxy = bbox_lv95
    
    corners = [
        (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)
    ]
    lons, lats = zip(*[transformer.transform(x, y) for x, y in corners])
    
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    
    # Convert to tile coordinates (Web Mercator-like tiling)
    # This is approximate - actual 3D Tiles use region-based quadtree
    def deg_to_tile(lat_deg, lon_deg, zoom):
        n = 2.0 ** zoom
        x = int((lon_deg + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat_deg)
        y = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
        return x, y
    
    min_tile_x, max_tile_y = deg_to_tile(min_lat, min_lon, zoom_level)
    max_tile_x, min_tile_y = deg_to_tile(max_lat, max_lon, zoom_level)
    
    tiles = []
    for x in range(min_tile_x, max_tile_x + 1):
        for y in range(min_tile_y, max_tile_y + 1):
            tiles.append((zoom_level, x, y))
    
    return tiles


def fetch_and_parse_tileset(base_url, date=None):
    """
    Fetch and parse tileset.json from 3D Tiles service.
    Returns parsed JSON data.
    
    Args:
        base_url: Base URL or full URL. If it ends with 'tileset.json', treated as full URL.
        date: Optional date string (YYYYMMDD) for date-based tilesets.
    """
    # If base_url already ends with tileset.json, use it directly
    if base_url.endswith('tileset.json'):
        tileset_url = base_url
    elif date:
        tileset_url = f"{base_url}/{date}/tileset.json"
    else:
        # Ensure it ends with tileset.json
        if base_url.endswith('/'):
            tileset_url = f"{base_url}tileset.json"
        else:
            tileset_url = f"{base_url}/tileset.json"
    
    try:
        response = requests.get(tileset_url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        # Don't print errors for nested tilesets (they might not exist)
        return None


def parse_b3dm_header(b3dm_data):
    """
    Parse b3dm header (28 bytes).
    Returns dict with header fields.
    """
    if len(b3dm_data) < 28:
        return None
    
    magic = b3dm_data[0:4]
    if magic != b'b3dm':
        return None
    
    version, = struct.unpack('<I', b3dm_data[4:8])
    byte_length, = struct.unpack('<I', b3dm_data[8:12])
    feature_table_json_byte_length, = struct.unpack('<I', b3dm_data[12:16])
    feature_table_binary_byte_length, = struct.unpack('<I', b3dm_data[16:20])
    batch_table_json_byte_length, = struct.unpack('<I', b3dm_data[20:24])
    batch_table_binary_byte_length, = struct.unpack('<I', b3dm_data[24:28])
    
    header_end = 28
    feature_table_json_start = header_end
    feature_table_json_end = feature_table_json_start + feature_table_json_byte_length
    feature_table_binary_start = feature_table_json_end
    feature_table_binary_end = feature_table_binary_start + feature_table_binary_byte_length
    batch_table_json_start = feature_table_binary_end
    batch_table_json_end = batch_table_json_start + batch_table_json_byte_length
    batch_table_binary_start = batch_table_json_end
    glb_start = batch_table_json_start + batch_table_json_byte_length + batch_table_binary_byte_length
    
    return {
        'version': version,
        'byte_length': byte_length,
        'feature_table_json': b3dm_data[feature_table_json_start:feature_table_json_end],
        'feature_table_binary': b3dm_data[feature_table_binary_start:feature_table_binary_end],
        'batch_table_json': b3dm_data[batch_table_json_start:batch_table_json_end] if batch_table_json_byte_length > 0 else b'',
        'batch_table_binary': b3dm_data[batch_table_binary_start:glb_start] if batch_table_binary_byte_length > 0 else b'',
        'glb_data': b3dm_data[glb_start:]
    }


def parse_glb_geometries(glb_data):
    """
    Parse GLB data and extract building geometries.
    Handles both uncompressed and Draco-compressed meshes.
    Returns list of building meshes: [{'vertices': [...], 'faces': [...], 'batch_id': ...}, ...]
    """
    # First check if Draco compression is used - if so, use DracoPy directly
    # (trimesh doesn't handle Draco correctly)
    try:
        json_chunk_length = struct.unpack('<I', glb_data[12:16])[0]
        json_end = 20 + json_chunk_length
        json_data = glb_data[20:json_end]
        gltf_json = json.loads(json_data.decode('utf-8'))
        
        # Check for Draco compression
        has_draco = False
        for mesh_json in gltf_json.get('meshes', []):
            for prim in mesh_json.get('primitives', []):
                if 'extensions' in prim and 'KHR_draco_mesh_compression' in prim['extensions']:
                    has_draco = True
                    break
            if has_draco:
                break
        
        if has_draco and DracoPy is not None:
            # Skip trimesh - use DracoPy directly
            pass
        elif trimesh is not None:
            # Try using trimesh for uncompressed GLB files
            try:
                import io
                glb_file = io.BytesIO(glb_data)
                scene = trimesh.load(glb_file, file_type='glb')
                
                buildings = []
                if isinstance(scene, trimesh.Scene):
                    for name, mesh in scene.geometry.items():
                        if hasattr(mesh, 'vertices') and hasattr(mesh, 'faces'):
                            vertices = mesh.vertices.tolist()
                            faces = mesh.faces.tolist()
                            # Check if vertices are valid (not all zeros)
                            if len(vertices) > 0 and any(v[0] != 0 or v[1] != 0 or v[2] != 0 for v in vertices):
                                buildings.append({
                                    'vertices': vertices,
                                    'faces': faces,
                                    'batch_id': None
                                })
                elif isinstance(scene, trimesh.Trimesh):
                    vertices = scene.vertices.tolist()
                    faces = scene.faces.tolist()
                    if len(vertices) > 0 and any(v[0] != 0 or v[1] != 0 or v[2] != 0 for v in vertices):
                        buildings.append({
                            'vertices': vertices,
                            'faces': faces,
                            'batch_id': None
                        })
                
                if buildings:
                    return buildings
            except Exception as e:
                # trimesh failed, fall back to manual parsing
                pass
    except Exception:
        # If JSON parsing fails, continue to manual parsing
        pass
    
    if pygltflib is None:
        print("    Error: pygltflib not installed. Install with: pip install pygltflib")
        return []
    
    try:
        # Parse GLB file
        gltf = pygltflib.GLTF2().load_from_bytes(glb_data)
        buildings = []
        
        # Extract binary data from GLB chunks
        # GLB format: [12-byte header][JSON chunk][Binary chunk]
        # Header: magic(4) + version(4) + length(4)
        # JSON chunk: length(4) + type(4) + data
        # Binary chunk: length(4) + type(4) + data
        
        # Parse GLB header
        if len(glb_data) < 12:
            return []
        
        magic = glb_data[0:4]
        if magic != b'glTF':
            return []
        
        version = struct.unpack('<I', glb_data[4:8])[0]
        total_length = struct.unpack('<I', glb_data[8:12])[0]
        
        # Parse JSON chunk header
        if len(glb_data) < 20:
            return []
        
        json_chunk_length = struct.unpack('<I', glb_data[12:16])[0]
        json_chunk_type = glb_data[16:20]
        
        if json_chunk_type != b'JSON':
            return []
        
        # JSON data starts at offset 20
        json_end = 20 + json_chunk_length
        
        # Binary chunk starts after JSON chunk
        if len(glb_data) < json_end + 8:
            return []
        
        binary_chunk_length = struct.unpack('<I', glb_data[json_end:json_end+4])[0]
        binary_chunk_type = glb_data[json_end+4:json_end+8]
        
        if binary_chunk_type != b'BIN\0':
            return []
        
        binary_data_start = json_end + 8
        binary_data = glb_data[binary_data_start:binary_data_start + binary_chunk_length]
        
        # Parse JSON to check for Draco compression FIRST
        json_data = glb_data[20:json_end]
        gltf_json = json.loads(json_data.decode('utf-8'))
        
        # Check if any mesh uses Draco compression and decode it FIRST (before fallback)
        if DracoPy is not None:
            draco_found = False
            for mesh_idx, mesh_json in enumerate(gltf_json.get('meshes', [])):
                for prim_idx, prim in enumerate(mesh_json.get('primitives', [])):
                    if 'extensions' in prim and 'KHR_draco_mesh_compression' in prim['extensions']:
                        draco_found = True
                        draco_ext = prim['extensions']['KHR_draco_mesh_compression']
                        buffer_view_idx = draco_ext.get('bufferView')
                        
                        if buffer_view_idx is not None and buffer_view_idx < len(gltf.bufferViews):
                            buffer_view = gltf.bufferViews[buffer_view_idx]
                            byte_offset = buffer_view.byteOffset or 0
                            byte_length = buffer_view.byteLength
                            
                            # Extract compressed Draco data
                            compressed_data = binary_data[byte_offset:byte_offset + byte_length]
                            
                            try:
                                # Decode Draco-compressed mesh
                                decoded_mesh = DracoPy.decode(compressed_data)
                                
                                # Extract vertices and faces
                                vertices = []
                                if hasattr(decoded_mesh, 'points') and decoded_mesh.points is not None:
                                    import numpy as np
                                    if isinstance(decoded_mesh.points, np.ndarray):
                                        vertices = decoded_mesh.points.tolist()
                                    else:
                                        vertices = list(decoded_mesh.points)
                                
                                faces = []
                                if hasattr(decoded_mesh, 'faces') and decoded_mesh.faces is not None:
                                    import numpy as np
                                    if isinstance(decoded_mesh.faces, np.ndarray):
                                        faces = decoded_mesh.faces.tolist()
                                    else:
                                        faces = list(decoded_mesh.faces)
                                
                                if vertices and len(vertices) > 0:
                                    buildings.append({
                                        'vertices': vertices,
                                        'faces': faces,
                                        'batch_id': None
                                    })
                                    print(f"    ✓ Decoded Draco mesh {mesh_idx}/{prim_idx}: {len(vertices)} vertices, {len(faces)} faces")
                                    
                            except Exception as e:
                                print(f"    Error decoding Draco mesh {mesh_idx}/{prim_idx}: {e}")
                                import traceback
                                traceback.print_exc()
                                continue
            
            if draco_found and buildings:
                print(f"    Successfully decoded {len(buildings)} Draco-compressed meshes")
                return buildings
            elif draco_found:
                print(f"    ⚠️  Draco compression detected but decoding failed - trying fallback")
        
        # Extract meshes from all scenes
        scenes_to_process = []
        if gltf.scene is not None:
            scenes_to_process.append(gltf.scenes[gltf.scene])
        else:
            scenes_to_process.extend(gltf.scenes or [])
        
        if not scenes_to_process:
            # Try processing all nodes directly if no scenes
            for node in gltf.nodes or []:
                if node.mesh is not None:
                    mesh = gltf.meshes[node.mesh]
                    for primitive in mesh.primitives:
                        # Get accessor indices - attributes is an Attributes object, not a dict
                        position_accessor_idx = None
                        if hasattr(primitive.attributes, 'POSITION'):
                            position_accessor_idx = primitive.attributes.POSITION
                        indices_accessor_idx = primitive.indices
                        
                        if position_accessor_idx is None:
                            continue
                        
                        # Extract vertices
                        if position_accessor_idx >= len(gltf.accessors):
                            continue
                        position_accessor = gltf.accessors[position_accessor_idx]
                        buffer_view_idx = position_accessor.bufferView
                        if buffer_view_idx is None or buffer_view_idx >= len(gltf.bufferViews):
                            continue
                        buffer_view = gltf.bufferViews[buffer_view_idx]
                        
                        # Extract vertex positions from binary data
                        byte_offset = (buffer_view.byteOffset or 0) + (position_accessor.byteOffset or 0)
                        byte_stride = buffer_view.byteStride or (3 * 4)  # 3 floats * 4 bytes
                        count = position_accessor.count
                        
                        vertices = []
                        for i in range(count):
                            offset = byte_offset + i * byte_stride
                            if offset + 12 <= len(binary_data):
                                x, y, z = struct.unpack('<fff', binary_data[offset:offset+12])
                                vertices.append([x, y, z])
                        
                        # Extract face indices
                        faces = []
                        if indices_accessor_idx is not None:
                            if indices_accessor_idx >= len(gltf.accessors):
                                continue
                            indices_accessor = gltf.accessors[indices_accessor_idx]
                            indices_buffer_view_idx = indices_accessor.bufferView
                            if indices_buffer_view_idx is None or indices_buffer_view_idx >= len(gltf.bufferViews):
                                continue
                            indices_buffer_view = gltf.bufferViews[indices_buffer_view_idx]
                            
                            indices_byte_offset = (indices_buffer_view.byteOffset or 0) + (indices_accessor.byteOffset or 0)
                            
                            # Determine index type
                            if indices_accessor.componentType == 5123:  # UNSIGNED_SHORT
                                index_size = 2
                                unpack_fmt = '<H'
                            elif indices_accessor.componentType == 5125:  # UNSIGNED_INT
                                index_size = 4
                                unpack_fmt = '<I'
                            else:
                                continue
                            
                            for i in range(0, indices_accessor.count, 3):
                                if i + 2 < indices_accessor.count:
                                    offset0 = indices_byte_offset + i * index_size
                                    offset1 = indices_byte_offset + (i+1) * index_size
                                    offset2 = indices_byte_offset + (i+2) * index_size
                                    
                                    if offset2 + index_size <= len(binary_data):
                                        idx0, = struct.unpack(unpack_fmt, binary_data[offset0:offset0+index_size])
                                        idx1, = struct.unpack(unpack_fmt, binary_data[offset1:offset1+index_size])
                                        idx2, = struct.unpack(unpack_fmt, binary_data[offset2:offset2+index_size])
                                        faces.append([idx0, idx1, idx2])
                        
                        if vertices:
                            buildings.append({
                                'vertices': vertices,
                                'faces': faces,
                                'batch_id': None  # Will be set from batch table if available
                            })
        
        
        for scene in scenes_to_process:
            for node_idx in (scene.nodes if scene.nodes else []):
                node = gltf.nodes[node_idx]
                if node.mesh is not None:
                    mesh = gltf.meshes[node.mesh]
                    for primitive in mesh.primitives:
                        # Get accessor indices - attributes is an Attributes object, not a dict
                        position_accessor_idx = None
                        if hasattr(primitive.attributes, 'POSITION'):
                            position_accessor_idx = primitive.attributes.POSITION
                        indices_accessor_idx = primitive.indices
                        
                        if position_accessor_idx is None:
                            continue
                        
                        # Extract vertices
                        if position_accessor_idx >= len(gltf.accessors):
                            continue
                        position_accessor = gltf.accessors[position_accessor_idx]
                        buffer_view_idx = position_accessor.bufferView
                        if buffer_view_idx is None or buffer_view_idx >= len(gltf.bufferViews):
                            continue
                        buffer_view = gltf.bufferViews[buffer_view_idx]
                        
                        # Extract vertex positions from binary data
                        byte_offset = (buffer_view.byteOffset or 0) + (position_accessor.byteOffset or 0)
                        byte_stride = buffer_view.byteStride or (3 * 4)  # 3 floats * 4 bytes
                        count = position_accessor.count
                        
                        vertices = []
                        for i in range(count):
                            offset = byte_offset + i * byte_stride
                            if offset + 12 <= len(binary_data):
                                x, y, z = struct.unpack('<fff', binary_data[offset:offset+12])
                                vertices.append([x, y, z])
                        
                        # Extract face indices
                        faces = []
                        if indices_accessor_idx is not None:
                            if indices_accessor_idx >= len(gltf.accessors):
                                continue
                            indices_accessor = gltf.accessors[indices_accessor_idx]
                            indices_buffer_view_idx = indices_accessor.bufferView
                            if indices_buffer_view_idx is None or indices_buffer_view_idx >= len(gltf.bufferViews):
                                continue
                            indices_buffer_view = gltf.bufferViews[indices_buffer_view_idx]
                            
                            indices_byte_offset = (indices_buffer_view.byteOffset or 0) + (indices_accessor.byteOffset or 0)
                            
                            # Determine index type
                            if indices_accessor.componentType == 5123:  # UNSIGNED_SHORT
                                index_size = 2
                                unpack_fmt = '<H'
                            elif indices_accessor.componentType == 5125:  # UNSIGNED_INT
                                index_size = 4
                                unpack_fmt = '<I'
                            else:
                                continue
                            
                            for i in range(0, indices_accessor.count, 3):
                                if i + 2 < indices_accessor.count:
                                    offset0 = indices_byte_offset + i * index_size
                                    offset1 = indices_byte_offset + (i+1) * index_size
                                    offset2 = indices_byte_offset + (i+2) * index_size
                                    
                                    if offset2 + index_size <= len(binary_data):
                                        idx0, = struct.unpack(unpack_fmt, binary_data[offset0:offset0+index_size])
                                        idx1, = struct.unpack(unpack_fmt, binary_data[offset1:offset1+index_size])
                                        idx2, = struct.unpack(unpack_fmt, binary_data[offset2:offset2+index_size])
                                        faces.append([idx0, idx1, idx2])
                        
                        if vertices:
                            buildings.append({
                                'vertices': vertices,
                                'faces': faces,
                                'batch_id': None  # Will be set from batch table if available
                            })
        
        return buildings
    except Exception as e:
        print(f"    Error parsing GLB: {e}")
        import traceback
        traceback.print_exc()
        return []


def transform_tile_to_lv95(vertices, tile_transform, region, rtc_center=None):
    """
    Transform vertices from tile-local coordinates to EPSG:2056 (Swiss LV95).
    
    tile_transform: 4x4 transformation matrix (if available)
    region: [west, south, east, north, min_height, max_height] in radians
    rtc_center: RTC_CENTER from feature table in ECEF coordinates [x, y, z], if available
    """
    if not vertices:
        return []
    
    if rtc_center:
        # RTC_CENTER is in ECEF (Earth-Centered, Earth-Fixed) coordinates
        # Vertices are relative to RTC_CENTER, also in ECEF coordinates
        # We must add vertex to RTC_CENTER in ECEF, then transform to LV95
        ecef_x, ecef_y, ecef_z = rtc_center
        
        # Create transformers (reuse for efficiency)
        transformer_ecef = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
        transformer_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
        
        transformed_vertices = []
        for v in vertices:
            # Add vertex to RTC_CENTER in ECEF space
            vertex_ecef_x = ecef_x + v[0]
            vertex_ecef_y = ecef_y + v[1]
            vertex_ecef_z = ecef_z + v[2]
            
            # Transform from ECEF to WGS84 geographic
            lon, lat, alt = transformer_ecef.transform(vertex_ecef_x, vertex_ecef_y, vertex_ecef_z)
            
            # Transform from WGS84 to LV95
            world_x, world_y = transformer_lv95.transform(lon, lat)
            
            # Keep relative Z - it represents height relative to local terrain
            # Terrain elevation will be added per-building in prepare_building_geometries
            world_z = v[2]
            
            transformed_vertices.append([world_x, world_y, world_z])
        
        return transformed_vertices
    else:
        # Fallback to region center (existing behavior for tiles without RTC_CENTER)
        if not region or len(region) < 4:
            # If no region, cannot transform
            return vertices
        
        west, south, east, north = region[0], region[1], region[2], region[3]
        
        # Convert region to degrees
        west_deg = math.degrees(west)
        south_deg = math.degrees(south)
        east_deg = math.degrees(east)
        north_deg = math.degrees(north)
        
        # Calculate center of region
        center_lon = (west_deg + east_deg) / 2
        center_lat = (south_deg + north_deg) / 2
        
        # Transform center to EPSG:2056
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
        tile_center_x, tile_center_y = transformer.transform(center_lon, center_lat)
        
        # For fallback, vertices are assumed to be in meters relative to region center
        transformed_vertices = []
        for v in vertices:
            world_x = tile_center_x + v[0]
            world_y = tile_center_y + v[1]
            world_z = v[2]
            transformed_vertices.append([world_x, world_y, world_z])
        
        return transformed_vertices


def meshes_to_geojson(building_meshes, building_attributes=None):
    """
    Convert 3D building meshes to building dicts with full mesh data.
    Each mesh becomes one building (keeps full 3D geometry intact).
    Returns list of building dicts with geometry, mesh_vertices, mesh_faces, attributes.
    """
    buildings = []
    
    for idx, mesh in enumerate(building_meshes):
        vertices = mesh.get('vertices', [])
        faces = mesh.get('faces', [])
        
        if not vertices or not faces:
            continue
        
        x_coords = [v[0] for v in vertices]
        y_coords = [v[1] for v in vertices]
        z_coords = [v[2] for v in vertices]
        
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)
        min_z, max_z = min(z_coords), max(z_coords)
        
        # Create 2D footprint for spatial queries (convex hull of all points)
        try:
            from shapely.geometry import MultiPoint
            points_2d = [(v[0], v[1]) for v in vertices]
            mp = MultiPoint(points_2d)
            hull = mp.convex_hull
            if hull.geom_type == 'Polygon':
                geom_shape = hull
            else:
                geom_shape = Polygon([
                    (min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)
                ])
        except:
            geom_shape = Polygon([
                (min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)
            ])
        
        if not geom_shape.is_valid:
            geom_shape = geom_shape.buffer(0)
        
        attrs = building_attributes[idx] if building_attributes and idx < len(building_attributes) else {}
        attrs = attrs.copy() if attrs else {}
        if 'height' not in attrs:
            attrs['height'] = max_z - min_z if max_z > min_z else 10.0
        
        # Store full mesh data for proper 3D IFC creation
        buildings.append({
            "geometry": geom_shape,
            "mesh_vertices": vertices,   # Full 3D vertices
            "mesh_faces": faces,         # Triangle face indices
            "attributes": attrs,
            "layer": "ch.swisstopo.swissbuildings3d_3_0",
            "has_z": True,
            "has_mesh": True,
            "min_z": min_z,
            "max_z": max_z
        })
    
    return buildings


def download_and_parse_b3dm(tile_url):
    """
    Download b3dm tile and extract building geometries.
    Returns list of building meshes.
    """
    try:
        response = requests.get(tile_url, timeout=60)
        response.raise_for_status()
        b3dm_data = response.content
        
        # Parse b3dm header
        header = parse_b3dm_header(b3dm_data)
        if not header:
            return []
        
        # Parse feature table
        feature_table = {}
        if header['feature_table_json']:
            try:
                feature_table = json.loads(header['feature_table_json'].decode('utf-8'))
            except:
                pass
        
        # Parse batch table for building IDs
        batch_table = {}
        if header['batch_table_json']:
            try:
                batch_table = json.loads(header['batch_table_json'].decode('utf-8'))
            except:
                pass
        
        # Parse GLB geometries
        glb_data = header['glb_data']
        meshes = parse_glb_geometries(glb_data)
        
        # Attach batch IDs if available
        if batch_table and 'id' in batch_table:
            ids = batch_table['id']
            for i, mesh in enumerate(meshes):
                if i < len(ids):
                    mesh['batch_id'] = ids[i]
        
        return meshes, feature_table, batch_table
    except Exception as e:
        print(f"    Error downloading/parsing b3dm: {e}")
        return [], {}, {}


def _process_single_tile(tile_url, tile_uri, region, base_url, center_x, center_y, radius):
    """
    Process a single 3D tile: download, parse, transform, and filter buildings.
    Returns list of buildings that are within the radius.
    """
    try:
        print(f"    Downloading tile: {tile_uri}")
        result = download_and_parse_b3dm(tile_url)
        
        if isinstance(result, tuple) and len(result) == 3:
            meshes, feature_table, batch_table = result
        else:
            meshes, feature_table, batch_table = result, {}, {}
        
        if not meshes or len(meshes) == 0:
            return []
        
        print(f"      Parsed {len(meshes)} meshes from tile {tile_uri}")
        
        # Extract RTC_CENTER from feature table if available
        rtc_center = None
        if feature_table and isinstance(feature_table, dict):
            rtc_center = feature_table.get('RTC_CENTER')
            if rtc_center:
                print(f"      Using RTC_CENTER: {rtc_center[:3] if len(rtc_center) >= 3 else rtc_center}")
        
        # Transform coordinates
        transformed_meshes = []
        for mesh in meshes:
            vertices = mesh.get('vertices', [])
            if not vertices:
                continue
                
            if region:
                transformed_vertices = transform_tile_to_lv95(vertices, None, region, rtc_center=rtc_center)
            else:
                # Use vertices as-is if no region (they should already be in correct CRS)
                transformed_vertices = vertices
            
            if transformed_vertices and len(transformed_vertices) > 0:
                transformed_mesh = mesh.copy()
                transformed_mesh['vertices'] = transformed_vertices
                transformed_meshes.append(transformed_mesh)
        
        if not transformed_meshes:
            return []
        
        # Convert to GeoJSON
        building_attrs = []
        if batch_table and isinstance(batch_table, dict):
            if 'id' in batch_table:
                ids = batch_table['id']
                if isinstance(ids, list):
                    building_attrs = [{'egid': str(id)} for id in ids]
        
        buildings = meshes_to_geojson(transformed_meshes, building_attrs if building_attrs else None)
        
        # Filter by radius
        circle = Point(center_x, center_y).buffer(radius)
        filtered_buildings = []
        for building in buildings:
            geom = building.get('geometry')
            if not geom:
                continue
            
            try:
                # Check if geometry intersects circle
                if circle.intersects(geom):
                    filtered_buildings.append(building)
            except Exception:
                continue
        
        return filtered_buildings
    except Exception as e:
        print(f"      Error processing tile {tile_uri}: {e}")
        return []


def fetch_buildings_from_3d_tiles(center_x, center_y, radius, max_buildings=250):
    """
    Fetch swissBUILDINGS3D 3.0 Beta buildings from 3D Tiles service.
    Returns list of building dicts compatible with existing code.
    """
    if pygltflib is None:
        print("  Error: pygltflib not installed. Cannot parse 3D Tiles.")
        print("  Install with: pip install pygltflib")
        return []
    
    print(f"  Fetching buildings from 3D Tiles service...")
    
    base_url = "https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1"
    bbox_lv95 = (
        center_x - radius,
        center_y - radius,
        center_x + radius,
        center_y + radius,
    )
    
    # Fetch root tileset
    tileset = fetch_and_parse_tileset(base_url)
    if not tileset:
        print("  Failed to fetch root tileset")
        return []
    
    # Find date-based tileset that covers our area
    date_tileset = None
    date_str = None
    root_node = tileset.get('root', {})
    
    # Transform center to WGS84 for region comparison
    transformer = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
    center_lon, center_lat = transformer.transform(center_x, center_y)
    west_rad = math.radians(center_lon - 0.01)
    east_rad = math.radians(center_lon + 0.01)
    south_rad = math.radians(center_lat - 0.01)
    north_rad = math.radians(center_lat + 0.01)
    
    # Get date string from root children (but don't use that tileset - it's just the root)
    if 'children' in root_node:
        for child in root_node['children']:
            if 'content' in child and 'uri' in child.get('content', {}):
                uri = child['content']['uri']
                if uri.endswith('tileset.json'):
                    # Extract date from URI (format: YYYYMMDD/tileset.json)
                    date_str = uri.replace('/tileset.json', '')
                    if date_str.isdigit() and len(date_str) == 8:
                        break
    
    if not date_str:
        date_str = "20251121"  # Default to most recent
    
    # Fallback: try to find tileset by number (0-20) that covers our area
    if not date_tileset:
        # First, get the date string if available
        if not date_str:
            # Try to get date from root children
            if 'children' in root_node:
                for child in root_node['children']:
                    if 'content' in child and 'uri' in child.get('content', {}):
                        uri = child['content']['uri']
                        if uri.endswith('tileset.json'):
                            date_str = uri.replace('/tileset.json', '')
                            if date_str.isdigit() and len(date_str) == 8:
                                break
        
        if not date_str:
            date_str = "20251121"  # Default to most recent
        
        # Now check each tileset number - fetch directly
        for tileset_num in range(0, 20):
            try:
                tileset_url = f"{base_url}/{date_str}/tileset{tileset_num}.json"
                import requests
                response = requests.get(tileset_url, timeout=10)
                if response.status_code == 200:
                    test_tileset = response.json()
                    root = test_tileset.get('root', {})
                    if 'boundingVolume' in root and 'region' in root['boundingVolume']:
                        region = root['boundingVolume']['region']
                        tile_west, tile_south, tile_east, tile_north = region[0], region[1], region[2], region[3]
                        if not (tile_east < west_rad or tile_west > east_rad or tile_north < south_rad or tile_south > north_rad):
                            date_tileset = test_tileset
                            print(f"  Using tileset{tileset_num} (covers our area)")
                            break
            except Exception as e:
                continue
    
    # Final fallback to root tileset
    if not date_tileset:
        date_tileset = tileset
        date_str = None
    
    # Traverse tileset to find relevant tiles
    all_buildings = []
    tiles_to_download = []
    tileset_cache = {}  # Cache fetched tilesets
    
    def traverse_tileset(node, tileset_base_url=None, depth=0, max_depth=15, visited=None):
        if visited is None:
            visited = set()
        if depth > max_depth:
            return
        
        # Check bounding volume intersection
        # Only include nodes that actually intersect our search area
        should_include = True
        if 'boundingVolume' in node:
            bv = node['boundingVolume']
            if 'region' in bv:
                region = bv['region']
                # Use buffer to include nearby tiles (radius * 2 to be safe)
                intersects = _bbox_intersects_region(bbox_lv95, region, buffer_meters=radius * 2)
                if not intersects:
                    # Skip this node - it doesn't intersect
                    # But still traverse children in case they do
                    should_include = False
                    # Don't return - continue to check children
        
        # Process content - temporarily include all to debug
        if 'content' in node:
            content = node['content']
            uri = None
            if isinstance(content, dict) and 'uri' in content:
                uri = content['uri']
            elif isinstance(content, str):
                uri = content
            
            if uri:
                if '.b3dm' in uri or uri.endswith('.b3dm'):
                    # Found a b3dm tile
                    region = node.get('boundingVolume', {}).get('region') if 'boundingVolume' in node else None
                    tiles_to_download.append((uri, region, tileset_base_url))
                    if len(tiles_to_download) <= 5:  # Debug: show first few tiles
                        print(f"      Found tile: {uri}")
                elif 'tileset' in uri.lower() and uri not in visited:
                    # Found a nested tileset - fetch and traverse it
                    visited.add(uri)
                    
                    # Construct nested tileset URL
                    if tileset_base_url:
                        if uri.startswith('/'):
                            nested_full_url = f"{base_url}{uri}"
                        else:
                            nested_full_url = f"{tileset_base_url}/{uri}"
                    else:
                        if uri.startswith('/'):
                            nested_full_url = f"{base_url}{uri}"
                        else:
                            nested_full_url = f"{base_url}/{uri}"
                    
                    # Ensure URL ends with tileset.json for fetch_and_parse_tileset
                    if not nested_full_url.endswith('tileset.json'):
                        if nested_full_url.endswith('/'):
                            nested_full_url = nested_full_url + 'tileset.json'
                        else:
                            nested_full_url = nested_full_url + '/tileset.json'
                    
                    # Extract base URL for child tiles (directory containing tileset.json)
                    nested_base_for_tiles = nested_full_url.rsplit('/', 1)[0] if '/' in nested_full_url else tileset_base_url
                    
                    # Avoid infinite recursion
                    cache_key = nested_full_url
                    if cache_key not in tileset_cache:
                        nested_tileset = fetch_and_parse_tileset(nested_full_url)
                        if nested_tileset:
                            tileset_cache[cache_key] = nested_tileset
                            nested_root = nested_tileset.get('root', {})
                            traverse_tileset(nested_root, nested_base_for_tiles, depth + 1, max_depth, visited)
        
        # Always traverse children (they might intersect even if parent doesn't)
        if 'children' in node:
            for child in node['children']:
                traverse_tileset(child, tileset_base_url, depth + 1, max_depth, visited)
        
        # Debug: show traversal progress at top levels
        if depth <= 2 and 'boundingVolume' in node:
            bv = node['boundingVolume']
            if 'region' in bv:
                region = bv['region']
                intersects = _bbox_intersects_region(bbox_lv95, region, buffer_meters=radius * 2)
                if depth == 0:
                    print(f"    Root node: intersects={intersects}")
    
    root_node = date_tileset.get('root', {})
    # Determine base URL for relative URIs
    # date_str was already extracted above
    if date_str:
        date_base_url = f"{base_url}/{date_str}"
    else:
        date_base_url = base_url
    
    traverse_tileset(root_node, date_base_url)
    
    print(f"  Found {len(tiles_to_download)} tiles to download")
    
    if not tiles_to_download:
        print("  No tiles found in tileset hierarchy")
        return []
    
    # Sort tiles by distance to center (approximate) and download closest ones first
    # Calculate approximate distance for each tile based on its region
    tile_distances = []
    for tile_info in tiles_to_download:
        if len(tile_info) >= 2 and tile_info[1]:  # Has region
            region = tile_info[1]
            if len(region) >= 4:
                west, south, east, north = region[0], region[1], region[2], region[3]
                # Transform region center to EPSG:2056
                transformer = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
                center_lon = math.degrees((west + east) / 2)
                center_lat = math.degrees((south + north) / 2)
                tile_x, tile_y = transformer.transform(center_lon, center_lat)
                dist = ((tile_x - center_x)**2 + (tile_y - center_y)**2)**0.5
                tile_distances.append((dist, tile_info))
            else:
                tile_distances.append((float('inf'), tile_info))
        else:
            tile_distances.append((float('inf'), tile_info))
    
    # Sort by distance and take closest tiles
    tile_distances.sort(key=lambda x: x[0])
    
    # Download and parse tiles (limit for performance)
    max_tiles = 50  # Increased limit to get more buildings
    print(f"  Downloading up to {max_tiles} closest tiles (out of {len(tiles_to_download)} total) in parallel...")
    
    # Prepare tile URLs and metadata for parallel processing
    tile_tasks = []
    for dist, tile_info in tile_distances[:max_tiles]:
        # Handle tuple format: (uri, region, base_url) or (uri, region)
        if len(tile_info) == 3:
            tile_uri, region, tile_base_url = tile_info
        else:
            tile_uri, region = tile_info
            tile_base_url = base_url
        
        # Handle relative and absolute URIs
        if tile_uri.startswith('http'):
            tile_url = tile_uri
        else:
            # Construct full URL using the base URL from tileset
            if tile_base_url:
                tile_url = f"{tile_base_url}/{tile_uri}"
            else:
                tile_url = f"{base_url}/{tile_uri}"
        
        tile_tasks.append((tile_url, tile_uri, region, base_url))
    
    # Process tiles in parallel
    max_workers = 10  # Limit concurrent downloads to avoid overwhelming the server
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_tile = {
            executor.submit(_process_single_tile, tile_url, tile_uri, region, base_url, center_x, center_y, radius): tile_uri
            for tile_url, tile_uri, region, base_url in tile_tasks
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_tile):
            tile_uri = future_to_tile[future]
            try:
                buildings_from_tile = future.result()
                all_buildings.extend(buildings_from_tile)
                if buildings_from_tile:
                    print(f"      Tile {tile_uri}: added {len(buildings_from_tile)} buildings")
                
                # Stop early if we have enough buildings
                if len(all_buildings) >= max_buildings:
                    print(f"  Reached max_buildings limit ({max_buildings}), stopping tile processing")
                    # Cancel remaining tasks
                    for f in future_to_tile:
                        f.cancel()
                    break
            except Exception as e:
                print(f"      Tile {tile_uri} generated an exception: {e}")
    
    # Limit to max_buildings if we exceeded it
    if len(all_buildings) > max_buildings:
        all_buildings = all_buildings[:max_buildings]
    
    print(f"  Extracted {len(all_buildings)} buildings from 3D Tiles")
    return all_buildings


def fetch_buildings_in_radius(center_x, center_y, radius, layer="ch.swisstopo.swissbuildings3d_3_0", max_buildings=250):
    """
    Fetch swissBUILDINGS3D 3.0 Beta features in a circular search area.
    
    Note: swissBUILDINGS3D 3.0 Beta may not be available via REST API.
    The data is primarily available via download from swisstopo.
    This function attempts API access but may return empty results.
    """
    bbox = (
        center_x - radius,
        center_y - radius,
        center_x + radius,
        center_y + radius,
    )
    circle = Point(center_x, center_y).buffer(radius)
    
    # Try alternative layer names (including fallback to VEC200 buildings)
    alternative_layers = [
        layer,  # Original: ch.swisstopo.swissbuildings3d_3_0
        "ch.swisstopo.swissbuildings3d.3d",  # Alternative format
        "ch.swisstopo.swissbuildings3d",  # Without version
        "ch.swisstopo.vec200-building",  # Fallback: VEC200 buildings (2D footprints, available via API)
    ]
    
    def _query_bbox(bounds, try_layer):
        """Query identify endpoint"""
        params = {
            "geometry": f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}",
            "geometryType": "esriGeometryEnvelope",
            "layers": f"all:{try_layer}",
            "tolerance": 0,
            "returnGeometry": "true",
            "sr": "2056",
            "mapExtent": f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}",
            "imageDisplay": "1000,1000,96",
            "geometryFormat": "geojson",
        }
        url = "https://api3.geo.admin.ch/rest/services/all/MapServer/identify"
        try:
            response = requests.get(url, params=params, timeout=25)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                error_data = e.response.json()
                error_detail = error_data.get("detail", "")
                if "No GeoTable" in error_detail or "No Vector Table" in error_detail or "error in the parameter layers" in error_detail:
                    return None  # Signal that this layer doesn't work
            raise

    def _split_bbox(bounds):
        minx, miny, maxx, maxy = bounds
        midx = (minx + maxx) / 2.0
        midy = (miny + maxy) / 2.0
        return [
            (minx, miny, midx, midy),
            (midx, miny, maxx, midy),
            (minx, midy, midx, maxy),
            (midx, midy, maxx, maxy),
        ]

    print(f"\nFetching swissBUILDINGS3D 3.0 Beta buildings within {radius}m (with tiling to avoid API limit)...")
    seen_keys = set()
    collected = []

    def _feature_key(feature):
        attrs = feature.get("properties", {}) or feature.get("attributes", {}) or {}
        return (
            attrs.get("gml_id")
            or attrs.get("id")
            or attrs.get("egid")
            or attrs.get("EGID")
            or feature.get("layerId")
            or feature.get("value")
        )

    # Find working layer name
    working_layer = None
    for alt_layer in alternative_layers:
        try:
            test_results = _query_bbox(bbox, alt_layer)
            if test_results is not None:  # None means layer doesn't exist, [] means no results
                working_layer = alt_layer
                if alt_layer != layer:
                    print(f"  Using alternative layer name: {alt_layer}")
                break
        except Exception:
            continue
    
    if working_layer is None:
        print(f"  ⚠️  swissBUILDINGS3D 3.0 Beta is NOT available via GeoAdmin REST API")
        print(f"  Falling back to 3D Tiles service...")
        
        # Try 3D Tiles as fallback
        try:
            buildings_3d_tiles = fetch_buildings_from_3d_tiles(center_x, center_y, radius, max_buildings)
            if buildings_3d_tiles:
                print(f"  ✓ Successfully fetched {len(buildings_3d_tiles)} buildings from 3D Tiles")
                return buildings_3d_tiles
            else:
                print(f"  No buildings found via 3D Tiles service")
                return []
        except Exception as e:
            print(f"  Error fetching from 3D Tiles: {e}")
            import traceback
            traceback.print_exc()
            print(f"  NOTE: No buildings will be included in the IFC file")
            return []
    
    if working_layer == "ch.swisstopo.vec200-building":
        print(f"  NOTE: Using VEC200 building footprints (2D) as fallback")
        print(f"  These are 2D footprints without 3D geometry - will be extruded based on terrain")
    
    def _collect_from_bbox(bounds, depth=0, max_depth=4):
        nonlocal collected
        if max_buildings and len(collected) >= max_buildings:
            return
        
        try:
            results = _query_bbox(bounds, working_layer)
            if results is None:
                return  # Layer doesn't exist
        except Exception as exc:
            if depth == 0:
                print(f"  Warning: Failed bbox fetch {bounds}: {exc}")
            return

        if len(results) >= 50 and depth < max_depth:
            for sub_bbox in _split_bbox(bounds):
                _collect_from_bbox(sub_bbox, depth + 1, max_depth)
            return

        for feature in results:
            key = _feature_key(feature)
            if key is not None and key in seen_keys:
                continue

            geom_json = feature.get("geometry")
            if not geom_json:
                continue
            geom_shape = shape(geom_json)
            if not geom_shape.is_valid:
                geom_shape = geom_shape.buffer(0)
            if geom_shape.is_empty:
                continue
            if not circle.intersects(geom_shape):
                continue

            attrs = feature.get("properties", {}) or feature.get("attributes", {}) or {}
            collected.append({
                "geometry": geom_shape,
                "geometry_json": geom_json,
                "attributes": attrs,
                "layer": layer
            })
            if key is not None:
                seen_keys.add(key)
            if max_buildings and len(collected) >= max_buildings:
                return

    _collect_from_bbox(bbox)

    if not collected:
        print("  No buildings intersect the requested circle")
        return []

    # Limit building count by distance to center for performance (dedupe already applied)
    if max_buildings and len(collected) > max_buildings:
        collected.sort(key=lambda b: b["geometry"].centroid.distance(Point(center_x, center_y)))
        print(f"  Limiting buildings from {len(collected)} to closest {max_buildings}")
        collected = collected[:max_buildings]

    print(f"  Prepared {len(collected)} swissBUILDINGS3D features for processing")
    return collected


def prepare_building_geometries(building_features, terrain_coords, terrain_elevations, separate_elements=False):
    """Normalize swissBUILDINGS3D geometries for IFC creation."""
    prepared = []
    terrain_index = TerrainIndex(terrain_coords, terrain_elevations)
    
    # The raw Z values in 3D Tiles represent height RELATIVE TO LOCAL TERRAIN:
    # - Negative Z = basement (below terrain)
    # - Zero = ground level
    # - Positive Z = above terrain
    #
    # The correct formula is: final_z = raw_z + terrain_orthometric
    # We do NOT use min_h from the region - it's just a bounding box minimum!
    
    print(f"  Using terrain-based Z positioning (raw_z + terrain_elevation)")
    
    debug_count = 0
    for feature in building_features:
        attrs = feature.get("attributes", {})
        geom_shape = feature["geometry"]
        
        # Check if this building has full mesh data (from 3D Tiles)
        has_mesh = feature.get("has_mesh", False)
        mesh_vertices = feature.get("mesh_vertices", [])
        mesh_faces = feature.get("mesh_faces", [])
        
        # Get terrain elevation at building centroid (orthometric LN02)
        terrain_elevation = terrain_index.nearest_height(
            geom_shape.centroid.x, geom_shape.centroid.y, default=600.0
        )
        
        if has_mesh and mesh_vertices:
            # Get Z range from mesh vertices
            # Raw Z represents height relative to local terrain
            # final_z = raw_z + terrain_elevation
            z_coords = [v[2] for v in mesh_vertices]
            raw_min_z = min(z_coords)
            raw_max_z = max(z_coords)
            
            # Calculate actual heights by adding terrain
            min_z = raw_min_z + terrain_elevation
            max_z = raw_max_z + terrain_elevation
            has_z = True
            
            # The Z adjustment IS the terrain elevation
            # (raw_z is relative to terrain, so we add terrain to get absolute)
            z_offset_adjustment = terrain_elevation
            
            if debug_count < 3:
                print(f"    Building: raw_z=[{raw_min_z:.1f},{raw_max_z:.1f}], terrain={terrain_elevation:.1f}m, final_z=[{min_z:.1f},{max_z:.1f}]")
                debug_count += 1
        else:
            # Fall back to GeoJSON-based approach
            geom_json = feature.get("geometry_json", {})
            has_z = _geometry_has_z(geom_json.get("coordinates", []))
            raw_min_z, raw_max_z = _collect_z_range_from_geojson(geom_json) if has_z else (None, None)
            min_z = raw_min_z
            max_z = raw_max_z
            z_offset_adjustment = 0.0

        base_z = min_z if min_z is not None else terrain_elevation
        height = (max_z - min_z) if (min_z is not None and max_z is not None) else _estimate_building_height(attrs)

        building_id = (
            attrs.get("egid")
            or attrs.get("EGID")
            or attrs.get("id")
            or attrs.get("gml_id")
            or f"building_{len(prepared) + 1}"
        )

        building_data = {
            "shape": geom_shape,
            "attributes": attrs,
            "layer": feature.get("layer", ""),
            "has_z": has_z,
            "base_z": base_z,
            "height": height,
            "min_z": min_z if min_z is not None else base_z,
            "max_z": max_z if max_z is not None else base_z + height,
            "id": str(building_id),
            "separate_elements": separate_elements,
            "terrain_elevation": terrain_elevation,
            "z_offset_adjustment": z_offset_adjustment,
        }
        
        # Include mesh data if available (NOT modified - keep original geometry)
        if has_mesh and mesh_vertices:
            building_data["has_mesh"] = True
            building_data["mesh_vertices"] = mesh_vertices
            building_data["mesh_faces"] = mesh_faces
        else:
            building_data["geometry_json"] = feature.get("geometry_json", {})
        
        prepared.append(building_data)
    return prepared


def _geojson_polygons(geometry_json):
    """Return list of polygon coordinate arrays from a GeoJSON geometry."""
    geom_type = geometry_json.get("type")
    coords = geometry_json.get("coordinates", [])
    if geom_type == "Polygon":
        return [coords]
    if geom_type in ("MultiPolygon", "MultiSurface", "CompositeSurface"):
        return coords
    return []


def _ring_to_points(model, ring, offset_x, offset_y, offset_z, fallback_z):
    """Convert a coordinate ring to IFC Cartesian points in local coordinates."""
    local_points = []
    local_coords = []
    for coord in _close_ring(ring):
        z_val = coord[2] if len(coord) >= 3 else fallback_z
        lx = float(coord[0] - offset_x)
        ly = float(coord[1] - offset_y)
        lz = float(float(z_val) - offset_z)
        local_points.append(model.createIfcCartesianPoint([lx, ly, lz]))
        local_coords.append((lx, ly, lz))
    return local_points, local_coords


def _create_faces_from_geojson(model, geometry_json, offset_x, offset_y, offset_z, fallback_z):
    """Create IFC faces from GeoJSON polygons (used when Z is present in geometry).

    Returns list of tuples: (IfcFace, classification)
    classification: ROOF, FACADE, FOOTPRINT, UNKNOWN
    """
    faces = []

    def _normal_from_ring(coords):
        # Need at least 3 distinct points
        if len(coords) < 3:
            return None
        p0 = np.array(coords[0])
        for i in range(1, len(coords) - 1):
            p1 = np.array(coords[i])
            p2 = np.array(coords[i + 1])
            v1 = p1 - p0
            v2 = p2 - p0
            cross = np.cross(v1, v2)
            norm = np.linalg.norm(cross)
            if norm > 0:
                return cross / norm
        return None

    def _classify_normal(normal):
        if normal is None:
            return "UNKNOWN"
        nz = normal[2]
        if nz > 0.7:
            return "ROOF"
        if nz < -0.7:
            return "FOOTPRINT"
        return "FACADE"

    for polygon in _geojson_polygons(geometry_json):
        if not polygon:
            continue
        try:
            outer_points, outer_coords = _ring_to_points(
                model, polygon[0], offset_x, offset_y, offset_z, fallback_z
            )
            outer_loop = model.createIfcPolyLoop(outer_points)
            bounds = [model.createIfcFaceOuterBound(outer_loop, True)]
            for hole in polygon[1:]:
                hole_points, _ = _ring_to_points(
                    model, hole, offset_x, offset_y, offset_z, fallback_z
                )
                hole_loop = model.createIfcPolyLoop(hole_points)
                bounds.append(model.createIfcFaceInnerBound(hole_loop, True))

            face = model.createIfcFace(bounds)
            normal = _normal_from_ring(outer_coords)
            faces.append((face, _classify_normal(normal)))
        except (AttributeError, ValueError, TypeError) as exc:
            print(f"    Warning: Failed to convert building polygon to IFC face: {exc}")
            continue
    return faces


def _create_faces_from_mesh(model, mesh_vertices, mesh_faces, offset_x, offset_y, offset_z, z_adjustment=0.0):
    """Create IFC faces from mesh triangles (from 3D Tiles).
    
    Args:
        z_adjustment: Additional Z offset to apply (to align building with terrain)
    
    Returns list of IfcFace objects.
    """
    ifc_faces = []
    
    if not mesh_vertices or not mesh_faces:
        return ifc_faces
    
    for face_indices in mesh_faces:
        if len(face_indices) < 3:
            continue
        
        try:
            # Get vertices for this face
            face_vertices = []
            for vi in face_indices:
                if vi < len(mesh_vertices):
                    v = mesh_vertices[vi]
                    # Convert to local coordinates, applying Z adjustment
                    lx = float(v[0] - offset_x)
                    ly = float(v[1] - offset_y)
                    lz = float(v[2] + z_adjustment - offset_z)
                    face_vertices.append(model.createIfcCartesianPoint([lx, ly, lz]))
            
            if len(face_vertices) >= 3:
                poly_loop = model.createIfcPolyLoop(face_vertices)
                face_bound = model.createIfcFaceOuterBound(poly_loop, True)
                ifc_face = model.createIfcFace([face_bound])
                ifc_faces.append(ifc_face)
        except Exception as e:
            # Skip problematic faces
            continue
    
    return ifc_faces


def _create_extruded_building_shell(model, polygon, base_z, height, offset_x, offset_y, offset_z):
    """Create a closed shell for an extruded building volume."""
    if height is None or height <= 0:
        return None, 0
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None, 0

    ext_coords = list(polygon.exterior.coords)
    if len(ext_coords) < 4:
        return None, 0

    local_ext = [(float(x - offset_x), float(y - offset_y), float(base_z - offset_z)) for x, y in ext_coords]
    local_roof = [(float(x - offset_x), float(y - offset_y), float(base_z + height - offset_z)) for x, y in ext_coords]

    faces = []

    # Roof faces (triangulated)
    tri_list = list(triangulate(polygon))
    for tri in tri_list:
        if not polygon.contains(tri.centroid):
            continue
        tri_coords = list(tri.exterior.coords)[:-1]
        tri_points = [
            model.createIfcCartesianPoint([float(x - offset_x), float(y - offset_y), float(base_z + height - offset_z)])
            for x, y in tri_coords
        ]
        tri_loop = model.createIfcPolyLoop(tri_points)
        faces.append(model.createIfcFace([model.createIfcFaceOuterBound(tri_loop, True)]))

    # Side faces
    for i in range(len(local_ext) - 1):
        p1 = local_ext[i]
        p2 = local_ext[i + 1]
        r1 = local_roof[i]
        r2 = local_roof[i + 1]
        side_pts = [
            model.createIfcCartesianPoint([float(p1[0]), float(p1[1]), float(p1[2])]),
            model.createIfcCartesianPoint([float(r1[0]), float(r1[1]), float(r1[2])]),
            model.createIfcCartesianPoint([float(r2[0]), float(r2[1]), float(r2[2])]),
            model.createIfcCartesianPoint([float(p2[0]), float(p2[1]), float(p2[2])])
        ]
        side_loop = model.createIfcPolyLoop(side_pts)
        faces.append(model.createIfcFace([model.createIfcFaceOuterBound(side_loop, True)]))

    # Bottom face
    bot_points = [model.createIfcCartesianPoint([float(p[0]), float(p[1]), float(p[2])]) for p in reversed(local_ext)]
    bot_loop = model.createIfcPolyLoop(bot_points)
    faces.append(model.createIfcFace([model.createIfcFaceOuterBound(bot_loop, True)]))

    if not faces:
        return None, 0

    shell = model.createIfcClosedShell(faces)
    return shell, len(faces)


def _attach_building_metadata(model, owner_history, set_owner_history_on_pset, product, building):
    attrs = building.get("attributes", {})
    pset_props = {}
    egid_value = attrs.get("egid") or attrs.get("EGID")
    if egid_value:
        pset_props["EGID"] = str(egid_value)
    if building.get("layer"):
        pset_props["SourceLayer"] = building["layer"]
    if building.get("height"):
        pset_props["HeightEstimate"] = float(building["height"])
    if pset_props:
        pset_buildings = ifcopenshell.api.run(
            "pset.add_pset", model, product=product, name="CPset_SwissBUILDINGS3D"
        )
        set_owner_history_on_pset(pset_buildings)
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset_buildings, properties=pset_props)
    product.OwnerHistory = owner_history


def _create_surface_element(model, body_context, owner_history, site, base_local, name, faces):
    shell = model.createIfcOpenShell(faces)
    shell_model = model.createIfcShellBasedSurfaceModel([shell])
    shape_rep = model.createIfcShapeRepresentation(
        body_context, "Body", "SurfaceModel", [shell_model]
    )
    element = ifcopenshell.api.run(
        "root.create_entity",
        model,
        ifc_class="IfcGeographicElement",
        name=name,
    )
    element.OwnerHistory = owner_history
    element.PredefinedType = "USERDEFINED"
    element.ObjectPlacement = base_local
    ifcopenshell.api.run("spatial.assign_container", model, products=[element], relating_structure=site)
    element.Representation = model.createIfcProductDefinitionShape(None, None, [shape_rep])
    return element


def _create_solid_building(model, body_context, building, offset_x, offset_y, offset_z):
    polygons = []
    if isinstance(building.get("shape"), Polygon):
        polygons = [building["shape"]]
    elif isinstance(building.get("shape"), MultiPolygon):
        polygons = list(building["shape"].geoms)

    rep_items = []
    total_faces = 0
    for poly in polygons:
        shell, face_count = _create_extruded_building_shell(
            model, poly, building.get("base_z", 0.0), building.get("height", 0.0),
            offset_x, offset_y, offset_z
        )
        total_faces += face_count
        if shell:
            rep_items.append(model.createIfcFacetedBrep(shell))

    if not rep_items:
        return None, 0

    shape_rep = model.createIfcShapeRepresentation(
        body_context, "Body", "Brep", rep_items
    )
    rep = model.createIfcProductDefinitionShape(None, None, [shape_rep])
    return rep, total_faces


def create_circular_terrain_grid(center_x, center_y, radius=500.0, resolution=10.0):
    """
    Create a grid of points covering a circular terrain area.
    
    Returns:
        coords: List of (x, y) coordinates within the circle
        circle_bounds: (minx, miny, maxx, maxy) bounding box of the circle
    """
    # Create bounding box for the circle
    minx = center_x - radius
    maxx = center_x + radius
    miny = center_y - radius
    maxy = center_y + radius
    
    # Create grid covering the bounding box
    x_range = np.arange(minx, maxx + resolution, resolution)
    y_range = np.arange(miny, maxy + resolution, resolution)
    
    # Filter points to only include those within the circle
    coords = []
    center_point = Point(center_x, center_y)
    circle = center_point.buffer(radius)
    
    for y in y_range:
        for x in x_range:
            point = Point(x, y)
            if circle.contains(point) or circle.boundary.distance(point) < resolution * 0.1:
                coords.append((x, y))
    
    print(f"Created circular grid: {len(coords)} points within {radius}m radius")
    print(f"Circle center: E {center_x:.1f}, N {center_y:.1f}")
    print(f"Coverage: E {minx:.1f} - {maxx:.1f}, N {miny:.1f} - {maxy:.1f}")
    print(f"Resolution: {resolution}m")
    
    return coords, (minx, miny, maxx, maxy)


def _circular_mean(values, window_size):
    """Smooth values with a circular mean filter."""
    n = len(values)
    if n == 0:
        return []

    window_size = min(window_size, n)
    if window_size % 2 == 0:
        window_size -= 1
    if window_size < 1:
        window_size = 1

    half_window = window_size // 2
    smoothed = []
    for i in range(n):
        window = [values[(i + j) % n] for j in range(-half_window, half_window + 1)]
        smoothed.append(float(np.mean(window)))
    return smoothed


def _best_fit_plane(ext_coords):
    """Project coordinates onto a best-fit plane to flatten bumps while keeping tilt."""
    if len(ext_coords) < 3:
        return [c[2] for c in ext_coords]

    arr = np.array(ext_coords, dtype=float)
    A = np.column_stack((arr[:, 0], arr[:, 1], np.ones(len(arr))))
    try:
        coeffs, _, _, _ = np.linalg.lstsq(A, arr[:, 2], rcond=None)
    except np.linalg.LinAlgError:
        return [c[2] for c in ext_coords]

    plane_z = A @ coeffs
    return plane_z.tolist()


def triangulate_terrain_with_cutout(coords, elevations, site_polygon, site_boundary_coords=None, site_boundary_elevations=None):
    """
    Create triangulated mesh from points, excluding triangles inside site boundary.
    Includes site boundary vertices in triangulation to ensure precise cutout shape.
    
    Args:
        coords: List of (x, y) coordinates for terrain grid
        elevations: List of elevations corresponding to coords
        site_polygon: Shapely Polygon representing site boundary
        site_boundary_coords: Optional list of (x, y) coordinates for site boundary
        site_boundary_elevations: Optional list of elevations for site boundary
    
    Returns list of triangles, each as [(x1,y1,z1), (x2,y2,z2), (x3,y3,z3)]
    """
    # Merge site boundary points with terrain grid if provided
    if site_boundary_coords and site_boundary_elevations:
        # Combine terrain and boundary coordinates
        all_coords = coords + site_boundary_coords
        all_elevations = elevations + site_boundary_elevations
        print(f"  Merged {len(site_boundary_coords)} site boundary points into terrain grid")
    else:
        all_coords = coords
        all_elevations = elevations
    
    try:
        from scipy.spatial import Delaunay
        use_scipy = True
    except ImportError:
        use_scipy = False
    
    if use_scipy:
        # Use scipy's Delaunay triangulation on combined point set
        points_2d = np.array(all_coords)
        tri = Delaunay(points_2d)
        
        triangles_3d = []
        excluded_count = 0
        
        for simplex in tri.simplices:
            i0, i1, i2 = simplex
            v0_2d = all_coords[i0]
            v1_2d = all_coords[i1]
            v2_2d = all_coords[i2]
            
            p0 = (*v0_2d, all_elevations[i0])
            p1 = (*v1_2d, all_elevations[i1])
            p2 = (*v2_2d, all_elevations[i2])
            
            # Calculate triangle centroid
            centroid_x = (v0_2d[0] + v1_2d[0] + v2_2d[0]) / 3.0
            centroid_y = (v0_2d[1] + v1_2d[1] + v2_2d[1]) / 3.0
            centroid = Point(centroid_x, centroid_y)
            
            # Exclude triangles whose centroid is inside site polygon
            # This ensures clean cutout even with boundary points in triangulation
            if not site_polygon.contains(centroid):
                triangles_3d.append([p0, p1, p2])
            else:
                excluded_count += 1
        
        print(f"  Excluded {excluded_count} triangles with centroid inside site boundary")
        return triangles_3d
    else:
        # Fallback: Use Shapely's triangulate
        from shapely.geometry import MultiPoint
        
        multipoint = MultiPoint([Point(x, y) for x, y in all_coords])
        triangles_2d = triangulate(multipoint)
        
        triangles_3d = []
        excluded_count = 0
        
        for tri_2d in triangles_2d:
            tri_coords_2d = list(tri_2d.exterior.coords)[:-1]
            
            if len(tri_coords_2d) == 3:
                # Check if triangle centroid is inside site
                centroid = tri_2d.centroid
                if site_polygon.contains(centroid):
                    excluded_count += 1
                    continue
                
                # Map to 3D coordinates
                tri_3d = []
                for tx, ty in tri_coords_2d:
                    min_dist = float('inf')
                    closest_idx = 0
                    for idx, (cx, cy) in enumerate(all_coords):
                        dist = math.sqrt((tx - cx)**2 + (ty - cy)**2)
                        if dist < min_dist:
                            min_dist = dist
                            closest_idx = idx
                    
                    tri_3d.append((all_coords[closest_idx][0], all_coords[closest_idx][1], all_elevations[closest_idx]))
                
                if len(tri_3d) == 3:
                    triangles_3d.append(tri_3d)
        
        print(f"  Excluded {excluded_count} triangles with centroid inside site boundary")
        return triangles_3d


def create_site_solid_coords(site_polygon, site_coords_3d, z_offset_adjustment=0.0):
    """
    Create smoothed site solid coordinates with height adjustment.
    
    Args:
        site_polygon: Shapely Polygon of site boundary
        site_coords_3d: List of (x, y, z) coordinates for site boundary
        z_offset_adjustment: Additional Z offset to align with terrain
    
    Returns:
        ext_coords: List of (x, y, z) coordinates for smoothed boundary
        base_elevation: Base elevation for solid bottom
        polygon_2d: 2D polygon for triangulation
        smoothed_boundary_2d: List of (x, y) for smoothed boundary
        smoothed_boundary_z: List of Z values for smoothed boundary
    """
    # Apply smoothing (same as workflow.py)
    ext_coords = [(float(x), float(y), float(z)) for x, y, z in site_coords_3d]
    if ext_coords[0] == ext_coords[-1]:
        ext_coords = ext_coords[:-1]
    
    # Apply smoothing
    z_values = [c[2] for c in ext_coords]
    plane_z = _best_fit_plane(ext_coords)
    smoothed_z = _circular_mean(z_values, window_size=9)
    residuals = [sz - pz for sz, pz in zip(smoothed_z, plane_z)]
    smoothed_residuals = _circular_mean(residuals, window_size=9)
    
    # Heavily attenuate residuals (20% scale)
    residual_scale = 0.2
    flattened_z = [pz + residual_scale * rz for pz, rz in zip(plane_z, smoothed_residuals)]
    
    # Apply height adjustment to align with terrain
    adjusted_z = [z + z_offset_adjustment for z in flattened_z]
    
    ext_coords = [(ext_coords[i][0], ext_coords[i][1], adjusted_z[i]) for i in range(len(ext_coords))]
    
    base_elevation = min(z for _, _, z in ext_coords) - 2.0  # 2 meters below lowest point
    
    # Create 2D polygon for triangulation
    polygon_2d = Polygon([(x, y) for x, y, _ in ext_coords])
    if not polygon_2d.is_valid:
        polygon_2d = polygon_2d.buffer(0)
    
    # Extract smoothed boundary for terrain attachment
    smoothed_boundary_2d = [(x, y) for x, y, _ in ext_coords]
    smoothed_boundary_z = [z for _, _, z in ext_coords]
    
    return ext_coords, base_elevation, polygon_2d, smoothed_boundary_2d, smoothed_boundary_z


def calculate_height_offset(site_polygon, site_coords_3d, terrain_coords, terrain_elevations):
    """
    Calculate Z offset needed to align site solid edges with terrain.
    
    Returns the average offset to apply to smoothed site elevations.
    """
    # Sample terrain elevations at site boundary points
    boundary_terrain_z = []
    
    terrain_index = TerrainIndex(terrain_coords, terrain_elevations)

    for x, y, _ in site_coords_3d:
        closest_z = terrain_index.nearest_height(x, y, default=None)
        if closest_z is not None:
            boundary_terrain_z.append(closest_z)
    
    if not boundary_terrain_z:
        return 0.0
    
    # Get smoothed site elevations at boundary
    ext_coords = [(float(x), float(y), float(z)) for x, y, z in site_coords_3d]
    if ext_coords[0] == ext_coords[-1]:
        ext_coords = ext_coords[:-1]
    
    z_values = [c[2] for c in ext_coords]
    plane_z = _best_fit_plane(ext_coords)
    smoothed_z = _circular_mean(z_values, window_size=9)
    residuals = [sz - pz for sz, pz in zip(smoothed_z, plane_z)]
    smoothed_residuals = _circular_mean(residuals, window_size=9)
    residual_scale = 0.2
    smoothed_boundary_z = [pz + residual_scale * rz for pz, rz in zip(plane_z, smoothed_residuals)]
    
    # Calculate average offset
    avg_terrain_z = np.mean(boundary_terrain_z)
    avg_smoothed_z = np.mean(smoothed_boundary_z)
    z_offset = avg_terrain_z - avg_smoothed_z
    
    print(f"  Terrain avg Z at boundary: {avg_terrain_z:.2f}m")
    print(f"  Smoothed site avg Z: {avg_smoothed_z:.2f}m")
    print(f"  Height offset adjustment: {z_offset:.2f}m")
    
    return z_offset


def create_combined_ifc(terrain_triangles, site_solid_data, output_path, bounds, 
                        center_x, center_y, egrid=None, cadastre_metadata=None, buildings=None):
    """
    Create a single IFC file with both terrain (with hole) and site solid.
    cadastre_metadata: dict with parcel info from cadastre API
    """
    model = ifcopenshell.file(schema='IFC4')
    
    # Create OwnerHistory (required by many IFC viewers for psets)
    person = model.createIfcPerson(FamilyName="User")
    organization = model.createIfcOrganization(Name="Site Boundaries Tool")
    person_org = model.createIfcPersonAndOrganization(person, organization)
    application = model.createIfcApplication(
        organization, 
        "1.0", 
        "Site Boundaries Geometry Tool", 
        "SiteBoundariesGeom"
    )
    owner_history = model.createIfcOwnerHistory(
        OwningUser=person_org, 
        OwningApplication=application, 
        ChangeAction="ADDED",
        CreationDate=int(time.time())
    )
    
    def set_owner_history_on_pset(pset):
        """Set OwnerHistory on pset and its relationship."""
        pset.OwnerHistory = owner_history
        # Find and update the relationship
        for rel in model.by_type('IfcRelDefinesByProperties'):
            if rel.RelatingPropertyDefinition == pset:
                rel.OwnerHistory = owner_history
    
    # Project setup
    project = ifcopenshell.api.run("root.create_entity", model,
                                    ifc_class="IfcProject",
                                    name="Combined Terrain Model")
    project.OwnerHistory = owner_history
    
    length_unit = ifcopenshell.api.run("unit.add_si_unit", model)
    ifcopenshell.api.run("unit.assign_unit", model, units=[length_unit])
    
    context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_context = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=context,
    )
    footprint_context = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Plan",
        context_identifier="FootPrint",
        target_view="PLAN_VIEW",
        parent=context,
    )
    
    # CRS setup
    crs = model.createIfcProjectedCRS(
        Name="EPSG:2056",
        Description="Swiss LV95 / CH1903+",
        GeodeticDatum="CH1903+",
        VerticalDatum="LN02"
    )
    
    # Calculate offsets - center on site
    minx, miny, maxx, maxy = bounds
    offset_x = round(center_x, -2)  # Round to nearest 100m
    offset_y = round(center_y, -2)
    terrain_min_z = min(p[2] for tri in terrain_triangles for p in tri)
    building_min_z = terrain_min_z
    if buildings:
        building_min_z = min(b.get("min_z", terrain_min_z) for b in buildings)
    offset_z = round(min(terrain_min_z, building_min_z))
    
    print(f"\nProject Origin: E={offset_x}, N={offset_y}, H={offset_z}")
    print(f"Site Center (relative to origin): E={center_x - offset_x:.1f}, N={center_y - offset_y:.1f}")
    
    model.createIfcMapConversion(
        SourceCRS=context,
        TargetCRS=crs,
        Eastings=float(offset_x),
        Northings=float(offset_y),
        OrthogonalHeight=float(offset_z)
    )
    
    # Create Site
    site_name = f"Site_{egrid}" if egrid else "Combined_Site"
    site = ifcopenshell.api.run("root.create_entity", model,
                                 ifc_class="IfcSite",
                                 name=site_name)
    site.OwnerHistory = owner_history
    ifcopenshell.api.run("aggregate.assign_object", model,
                          products=[site], relating_object=project)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=site)
    
    # Create terrain mesh (with hole)
    print(f"\nCreating terrain mesh with {len(terrain_triangles)} triangles...")
    terrain = ifcopenshell.api.run("root.create_entity", model,
                                    ifc_class="IfcGeographicElement",
                                    name="Surrounding_Terrain")
    terrain.OwnerHistory = owner_history
    terrain.PredefinedType = "TERRAIN"
    
    terrain_origin = model.createIfcCartesianPoint([0., 0., 0.])
    terrain_axis = model.createIfcDirection([0., 0., 1.])
    terrain_ref_direction = model.createIfcDirection([1., 0., 0.])
    terrain_axis2_placement = model.createIfcAxis2Placement3D(terrain_origin, terrain_axis, terrain_ref_direction)
    terrain_placement = model.createIfcLocalPlacement(site.ObjectPlacement, terrain_axis2_placement)
    terrain.ObjectPlacement = terrain_placement
    
    ifcopenshell.api.run("spatial.assign_container", model,
                          products=[terrain], relating_structure=site)
    
    terrain_faces = []
    for tri in terrain_triangles:
        local_pts = [(p[0] - offset_x, p[1] - offset_y, p[2] - offset_z) for p in tri]
        tri_points = [
            model.createIfcCartesianPoint([float(p[0]), float(p[1]), float(p[2])])
            for p in local_pts
        ]
        tri_loop = model.createIfcPolyLoop(tri_points)
        face = model.createIfcFace([model.createIfcFaceOuterBound(tri_loop, True)])
        terrain_faces.append(face)
    
    terrain_shell = model.createIfcOpenShell(terrain_faces)
    terrain_shell_model = model.createIfcShellBasedSurfaceModel([terrain_shell])
    
    terrain_rep = model.createIfcShapeRepresentation(
        body_context, "Body", "SurfaceModel", [terrain_shell_model])
    terrain.Representation = model.createIfcProductDefinitionShape(
        None, None, [terrain_rep])
    
    # Create site solid
    if site_solid_data:
        try:
            print(f"Creating site solid...")
            ext_coords = site_solid_data['ext_coords']
            base_elevation = site_solid_data['base_elevation']
            polygon_2d = site_solid_data['polygon_2d']
            
            print(f"  Site boundary points: {len(ext_coords)}")
            
            site_terrain = ifcopenshell.api.run("root.create_entity", model,
                                                 ifc_class="IfcGeographicElement",
                                                 name=f"Site_Solid_{egrid}" if egrid else "Site_Solid")
            site_terrain.OwnerHistory = owner_history
            site_terrain.PredefinedType = "TERRAIN"
            
            site_origin = model.createIfcCartesianPoint([0., 0., 0.])
            site_axis = model.createIfcDirection([0., 0., 1.])
            site_ref_direction = model.createIfcDirection([1., 0., 0.])
            site_axis2_placement = model.createIfcAxis2Placement3D(site_origin, site_axis, site_ref_direction)
            site_terrain_placement = model.createIfcLocalPlacement(site.ObjectPlacement, site_axis2_placement)
            site_terrain.ObjectPlacement = site_terrain_placement
            
            ifcopenshell.api.run("spatial.assign_container", model,
                                  products=[site_terrain], relating_structure=site)
            
            # Create local coordinates
            print(f"  Converting to local coordinates...")
            local_ext_coords = [(float(x - offset_x), float(y - offset_y), float(z - offset_z)) 
                                for x, y, z in ext_coords]
            local_base_elevation = base_elevation - offset_z
            
            z_lookup = {(round(x, 6), round(y, 6)): z for x, y, z in local_ext_coords}
            
            def get_vertex_z(x, y):
                key = (round(x, 6), round(y, 6))
                if key in z_lookup:
                    return z_lookup[key]
                return min(local_ext_coords, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)[2]
            
            site_ifc_faces = []
            
            # Create local 2D polygon for triangulation
            print(f"  Creating local polygon...")
            local_polygon_2d = Polygon([(x, y) for x, y, _ in local_ext_coords])
            if not local_polygon_2d.is_valid:
                print(f"  Polygon invalid, buffering...")
                local_polygon_2d = local_polygon_2d.buffer(0)
            
            if local_polygon_2d.is_empty:
                print(f"  Warning: Local polygon is empty, skipping site solid")
            else:
                # Create triangulated top faces
                print(f"  Triangulating top surface...")
                tri_list = list(triangulate(local_polygon_2d))
                print(f"  Generated {len(tri_list)} triangles")
                
                for tri in tri_list:
                    if not local_polygon_2d.contains(tri.centroid):
                        continue
                    
                    oriented_tri = orient(tri, sign=1.0)
                    tri_coords = list(oriented_tri.exterior.coords)[:-1]
                    tri_points = [
                        model.createIfcCartesianPoint([float(x), float(y), float(get_vertex_z(x, y))])
                        for x, y in tri_coords
                    ]
                    tri_loop = model.createIfcPolyLoop(tri_points)
                    face = model.createIfcFace([model.createIfcFaceOuterBound(tri_loop, True)])
                    site_ifc_faces.append(face)
                
                print(f"  Created {len(site_ifc_faces)} top faces")
                
                # Create side faces (skirt)
                print(f"  Creating side faces...")
                for i in range(len(local_ext_coords)):
                    p1 = local_ext_coords[i]
                    p2 = local_ext_coords[(i + 1) % len(local_ext_coords)]
                    
                    side_pts = [
                        model.createIfcCartesianPoint([float(p1[0]), float(p1[1]), float(p1[2])]),
                        model.createIfcCartesianPoint([float(p1[0]), float(p1[1]), float(local_base_elevation)]),
                        model.createIfcCartesianPoint([float(p2[0]), float(p2[1]), float(local_base_elevation)]),
                        model.createIfcCartesianPoint([float(p2[0]), float(p2[1]), float(p2[2])])
                    ]
                    side_loop = model.createIfcPolyLoop(side_pts)
                    side_face = model.createIfcFace([model.createIfcFaceOuterBound(side_loop, True)])
                    site_ifc_faces.append(side_face)
                
                # Create bottom face
                print(f"  Creating bottom face...")
                bot_points = [model.createIfcCartesianPoint([float(p[0]), float(p[1]), float(local_base_elevation)]) 
                              for p in reversed(local_ext_coords)]
                bot_loop = model.createIfcPolyLoop(bot_points)
                bot_face = model.createIfcFace([model.createIfcFaceOuterBound(bot_loop, True)])
                site_ifc_faces.append(bot_face)
                
                print(f"  Creating closed shell with {len(site_ifc_faces)} faces...")
                site_shell = model.createIfcClosedShell(site_ifc_faces)
                print(f"  Creating faceted brep...")
                site_solid = model.createIfcFacetedBrep(site_shell)
                
                site_rep = model.createIfcShapeRepresentation(
                    body_context, "Body", "Brep", [site_solid])
                site_terrain.Representation = model.createIfcProductDefinitionShape(
                    None, None, [site_rep])
                
                print(f"  Created site solid with {len(site_ifc_faces)} faces")
                
                # Add cadastre metadata using IFC schema best practices
                if cadastre_metadata:
                    # --- IfcSite schema attributes ---
                    # LandTitleNumber: Official land registration identifier (EGRID)
                    if cadastre_metadata.get('egrid'):
                        site.LandTitleNumber = cadastre_metadata['egrid']
                    
                    # LongName: Human-readable parcel identifier
                    if cadastre_metadata.get('parcel_number'):
                        site.LongName = f"{cadastre_metadata.get('canton', '')} {cadastre_metadata['parcel_number']}"
                    
                    # Description: Brief summary
                    site.Description = f"Swiss cadastral parcel in Canton {cadastre_metadata.get('canton', 'CH')}"
                    
                    # --- Pset_LandRegistration (IFC standard pset for land parcels) ---
                    pset_land = ifcopenshell.api.run("pset.add_pset", model, 
                                                      product=site, 
                                                      name="Pset_LandRegistration")
                    set_owner_history_on_pset(pset_land)
                    land_props = {
                        'LandID': cadastre_metadata.get('parcel_number', ''),
                        'LandTitleID': cadastre_metadata.get('egrid', ''),
                        'IsPermanentID': True  # EGRID is a permanent identifier
                    }
                    ifcopenshell.api.run("pset.edit_pset", model, 
                                          pset=pset_land, 
                                          properties=land_props)
                    print(f"  Added Pset_LandRegistration: {list(land_props.keys())}")
                    
                    # --- Qto_SiteBaseQuantities (IFC standard quantity set) ---
                    if cadastre_metadata.get('area_m2') or cadastre_metadata.get('perimeter_m'):
                        qto = ifcopenshell.api.run("pset.add_qto", model, 
                                                    product=site, 
                                                    name="Qto_SiteBaseQuantities")
                        set_owner_history_on_pset(qto)
                        quantities = {}
                        if cadastre_metadata.get('area_m2'):
                            quantities['GrossArea'] = cadastre_metadata['area_m2']
                        if cadastre_metadata.get('perimeter_m'):
                            quantities['GrossPerimeter'] = cadastre_metadata['perimeter_m']
                        
                        ifcopenshell.api.run("pset.edit_qto", model, 
                                              qto=qto, 
                                              properties=quantities)
                        print(f"  Added Qto_SiteBaseQuantities: {list(quantities.keys())}")
                    
                    # --- Site solid element description ---
                    site_terrain.Description = f"Site terrain solid - Parcel {cadastre_metadata.get('parcel_number', '')}"
                    
                    # --- Pset_SiteCommon (IFC standard - comprehensive site properties) ---
                    pset_common = ifcopenshell.api.run("pset.add_pset", model, 
                                                        product=site, 
                                                        name="Pset_SiteCommon")
                    set_owner_history_on_pset(pset_common)
                    
                    common_props = {}
                    if cadastre_metadata.get('local_id'):
                        common_props['Reference'] = cadastre_metadata['local_id']
                    if cadastre_metadata.get('area_m2'):
                        # TotalArea: Total planned area for the site
                        common_props['TotalArea'] = cadastre_metadata['area_m2']
                        # BuildableArea: Maximum buildable area (use total area as default if not specified)
                        # In Swiss cadastre, this might be different, but we use total area as fallback
                        common_props['BuildableArea'] = cadastre_metadata['area_m2']
                    
                    ifcopenshell.api.run("pset.edit_pset", model, 
                                          pset=pset_common, 
                                          properties=common_props)
                    print(f"  Added Pset_SiteCommon: {list(common_props.keys())}")
                    
                    # --- CPset_SwissCadastre (Custom property set - NOT in IFC schema) ---
                    if cadastre_metadata.get('geoportal_url') or cadastre_metadata.get('canton'):
                        pset_swiss = ifcopenshell.api.run("pset.add_pset", model, 
                                                           product=site, 
                                                           name="CPset_SwissCadastre")
                        set_owner_history_on_pset(pset_swiss)
                        swiss_props = {}
                        if cadastre_metadata.get('geoportal_url'):
                            swiss_props['GeoportalURL'] = cadastre_metadata['geoportal_url']
                        if cadastre_metadata.get('canton'):
                            swiss_props['Canton'] = cadastre_metadata['canton']
                        if cadastre_metadata.get('parcel_number'):
                            swiss_props['ParcelNumber'] = cadastre_metadata['parcel_number']
                        
                        ifcopenshell.api.run("pset.edit_pset", model, 
                                              pset=pset_swiss, 
                                              properties=swiss_props)
                        print(f"  Added CPset_SwissCadastre: {list(swiss_props.keys())}")
                    
        except Exception as e:
            import traceback
            print(f"  ERROR creating site solid: {e}")
            traceback.print_exc()
            print(f"  Continuing without site solid...")
    
    # Add swissBUILDINGS3D buildings if provided
    if buildings:
        print(f"\nAdding {len(buildings)} swissBUILDINGS3D buildings to IFC...")
        for idx, building in enumerate(buildings, 1):
            building_name = f"Building_{building.get('id', idx)}"
            base_placement_origin = model.createIfcCartesianPoint([0.0, 0.0, 0.0])
            axis = model.createIfcDirection([0.0, 0.0, 1.0])
            ref_dir = model.createIfcDirection([1.0, 0.0, 0.0])
            base_placement = model.createIfcAxis2Placement3D(base_placement_origin, axis, ref_dir)
            base_local = model.createIfcLocalPlacement(site.ObjectPlacement, base_placement)

            if building.get("has_z") and building.get("separate_elements"):
                faces = _create_faces_from_geojson(
                    model, building["geometry_json"], offset_x, offset_y, offset_z, building.get("base_z", 0.0)
                )
                grouped_faces = {"ROOF": [], "FACADE": [], "FOOTPRINT": [], "UNKNOWN": []}
                for face, cls in faces:
                    grouped_faces.setdefault(cls, []).append(face)
                for cls_name, cls_faces in grouped_faces.items():
                    if not cls_faces:
                        continue
                    element = _create_surface_element(
                        model, body_context, owner_history, site, base_local,
                        f"{building_name}_{cls_name.lower()}", cls_faces
                    )
                    element.ObjectType = f"Building_{cls_name}"
                    _attach_building_metadata(model, owner_history, set_owner_history_on_pset, element, building)
                    print(f"  Building {idx}: added {len(cls_faces)} {cls_name.lower()} face(s)")
                continue

            building_elem = ifcopenshell.api.run(
                "root.create_entity", model, ifc_class="IfcGeographicElement", name=building_name
            )
            building_elem.ObjectType = "Building"
            building_elem.PredefinedType = "USERDEFINED"
            building_elem.ObjectPlacement = base_local
            ifcopenshell.api.run("spatial.assign_container", model, products=[building_elem], relating_structure=site)

            rep = None
            # Check if we have full mesh data (from 3D Tiles)
            if building.get("has_mesh"):
                mesh_vertices = building.get("mesh_vertices", [])
                mesh_faces = building.get("mesh_faces", [])
                z_adjustment = building.get("z_offset_adjustment", 0.0)
                if mesh_vertices and mesh_faces:
                    ifc_faces = _create_faces_from_mesh(
                        model, mesh_vertices, mesh_faces, offset_x, offset_y, offset_z, z_adjustment
                    )
                    if ifc_faces:
                        shell = model.createIfcOpenShell(ifc_faces)
                        shell_model = model.createIfcShellBasedSurfaceModel([shell])
                        shape_rep = model.createIfcShapeRepresentation(
                            body_context, "Body", "SurfaceModel", [shell_model]
                        )
                        rep = model.createIfcProductDefinitionShape(None, None, [shape_rep])
                        print(f"  Building {idx}: created {len(ifc_faces)} faces from 3D mesh")
            elif building.get("has_z"):
                faces = _create_faces_from_geojson(
                    model, building["geometry_json"], offset_x, offset_y, offset_z, building.get("base_z", 0.0)
                )
                only_faces = [fc for fc, _cls in faces]
                if only_faces:
                    shell = model.createIfcOpenShell(only_faces)
                    shell_model = model.createIfcShellBasedSurfaceModel([shell])
                    shape_rep = model.createIfcShapeRepresentation(
                        body_context, "Body", "SurfaceModel", [shell_model]
                    )
                    rep = model.createIfcProductDefinitionShape(None, None, [shape_rep])
            else:
                rep, total_faces = _create_solid_building(
                    model, body_context, building, offset_x, offset_y, offset_z
                )
                if rep:
                    print(f"  Building {idx}: created {total_faces} faces from extruded footprint(s)")

            if rep:
                building_elem.Representation = rep
                _attach_building_metadata(model, owner_history, set_owner_history_on_pset, building_elem, building)
            else:
                print(f"  Building {idx}: No geometry created, skipping representation")

        print(f"Completed adding {len(buildings)} buildings")
    
    # Set OwnerHistory on all relationships that are missing it
    for entity in model:
        if hasattr(entity, 'OwnerHistory') and entity.OwnerHistory is None:
            try:
                entity.OwnerHistory = owner_history
            except:
                pass  # Some entities may not accept OwnerHistory
    
    model.write(output_path)
    print(f"\nCombined IFC file created: {output_path}")
    print(f"  Terrain triangles: {len(terrain_triangles)}")
    if site_solid_data:
        print(f"  Site solid: created")
    
    return offset_x, offset_y, offset_z


def main():
    parser = argparse.ArgumentParser(
        description="Create combined terrain with site cutout"
    )
    parser.add_argument("--egrid", help="EGRID number")
    parser.add_argument("--center-x", type=float, help="Center easting (EPSG:2056)")
    parser.add_argument("--center-y", type=float, help="Center northing (EPSG:2056)")
    parser.add_argument("--radius", type=float, default=500.0,
                        help="Radius of circular terrain area (meters), default: 500")
    parser.add_argument("--resolution", type=float, default=10.0,
                        help="Grid resolution (meters), default: 10")
    parser.add_argument("--densify", type=float, default=0.5,
                        help="Site boundary densification interval (meters), default: 0.5")
    parser.add_argument("--attach-to-solid", action="store_true",
                        help="Attach terrain to smoothed site solid edges (less bumpy)")
    parser.add_argument("--include-buildings", action="store_true",
                        help="Include swissBUILDINGS3D 3.0 Beta buildings within the terrain radius")
    parser.add_argument("--buildings-separate", action="store_true",
                        help="Export swissBUILDINGS3D faces as separate roof/facade/footprint objects when Z data is available")
    parser.add_argument("--building-radius", type=float,
                        help="Radius for fetching swissBUILDINGS3D buildings (defaults to terrain radius)")
    parser.add_argument("--building-layer", default="ch.swisstopo.swissbuildings3d_3_0",
                        help="GeoAdmin layer name for swissBUILDINGS3D 3.0 Beta")
    parser.add_argument("--max-buildings", type=int, default=250,
                        help="Limit the number of buildings to include (closest to center)")
    parser.add_argument("--output", default="combined_terrain.ifc",
                        help="Output IFC file path")
    
    args = parser.parse_args()
    
    if not args.egrid and not (args.center_x and args.center_y):
        print("Error: Either --egrid or both --center-x and --center-y must be provided")
        sys.exit(1)
    
    # Fetch site boundary
    cadastre_metadata = None
    if args.egrid:
        site_geometry, cadastre_metadata = fetch_boundary_by_egrid(args.egrid)
        if site_geometry is None:
            print("Failed to fetch site boundary")
            sys.exit(1)
        centroid = site_geometry.centroid
        center_x = centroid.x
        center_y = centroid.y
        bounds = site_geometry.bounds
        print(f"Site bounds: E {bounds[0]:.1f}-{bounds[2]:.1f}, N {bounds[1]:.1f}-{bounds[3]:.1f}")
        print(f"Site centroid: E {center_x:.1f}, N {center_y:.1f}")
    else:
        center_x = args.center_x
        center_y = args.center_y
        site_geometry = None
    
    # Create terrain grid
    terrain_coords, circle_bounds = create_circular_terrain_grid(
        center_x, center_y, radius=args.radius, resolution=args.resolution
    )
    
    if len(terrain_coords) == 0:
        print("Error: No points generated in circular area")
        sys.exit(1)
    
    # Fetch terrain elevations
    print("\nFetching terrain elevations...")
    terrain_elevations = fetch_elevation_batch(terrain_coords)

    # Optionally fetch nearby buildings
    buildings_prepared = []
    building_radius = args.building_radius if args.building_radius else args.radius
    if args.include_buildings:
        building_features = fetch_buildings_in_radius(
            center_x, center_y, building_radius, layer=args.building_layer, max_buildings=args.max_buildings
        )
        if building_features:
            buildings_prepared = prepare_building_geometries(
                building_features, terrain_coords, terrain_elevations, separate_elements=args.buildings_separate
            )
            print(f"Prepared {len(buildings_prepared)} buildings for IFC export")
    
    # Get site boundary 3D coordinates
    site_solid_data = None
    smoothed_boundary_2d = None
    smoothed_boundary_z = None
    
    if site_geometry:
        ring = site_geometry.exterior
        distances = np.arange(0, ring.length, args.densify)
        if distances[-1] < ring.length:
            distances = np.append(distances, ring.length)
        
        site_points = [ring.interpolate(d) for d in distances]
        site_coords_2d = [(p.x, p.y) for p in site_points]
        
        print(f"\nFetching site boundary elevations ({len(site_coords_2d)} points)...")
        site_elevations = fetch_elevation_batch(site_coords_2d)
        site_coords_3d = [(x, y, z) for (x, y), z in zip(site_coords_2d, site_elevations)]
        
        # Calculate height offset
        print("\nCalculating height offset for site solid...")
        z_offset = calculate_height_offset(
            site_geometry, site_coords_3d, terrain_coords, terrain_elevations
        )
        
        # Prepare site solid data BEFORE triangulation (so we can use smoothed boundary)
        print("\nPreparing smoothed site solid...")
        ext_coords, base_elevation, polygon_2d, smoothed_boundary_2d, smoothed_boundary_z = create_site_solid_coords(
            site_geometry, site_coords_3d, z_offset_adjustment=z_offset
        )
        site_solid_data = {
            'ext_coords': ext_coords,
            'base_elevation': base_elevation,
            'polygon_2d': polygon_2d
        }
        print(f"Site solid prepared with {len(ext_coords)} boundary points")
    else:
        print("Warning: No site geometry provided, skipping site solid")
        site_coords_3d = []
        z_offset = 0.0
    
    # Triangulate terrain with site cutout
    print("\nTriangulating terrain mesh (excluding site area)...")
    if site_geometry:
        # Choose boundary elevations based on --attach-to-solid option
        if args.attach_to_solid and smoothed_boundary_2d and smoothed_boundary_z:
            print("  Using smoothed site solid boundary for terrain attachment")
            boundary_coords = smoothed_boundary_2d
            boundary_elevations = smoothed_boundary_z
        else:
            print("  Using raw API elevations for terrain boundary")
            boundary_coords = site_coords_2d
            boundary_elevations = site_elevations
        
        # Pass site boundary coordinates to ensure precise cutout shape
        terrain_triangles = triangulate_terrain_with_cutout(
            terrain_coords, terrain_elevations, site_geometry,
            site_boundary_coords=boundary_coords,
            site_boundary_elevations=boundary_elevations
        )
    else:
        # No cutout if no site geometry
        terrain_triangles = []
        for i in range(len(terrain_coords) - 1):
            for j in range(len(terrain_coords) - 1):
                # Simple grid triangulation fallback
                pass
        print("Warning: Cannot create terrain without site geometry")
        sys.exit(1)
    
    print(f"Created {len(terrain_triangles)} terrain triangles")
    
    # Generate combined IFC
    print("\nGenerating combined IFC file...")
    create_combined_ifc(
        terrain_triangles, site_solid_data, args.output, circle_bounds,
        center_x, center_y, egrid=args.egrid, cadastre_metadata=cadastre_metadata, buildings=buildings_prepared
    )
    
    print(f"\nSuccess! Combined terrain IFC saved to: {args.output}")


if __name__ == "__main__":
    main()
