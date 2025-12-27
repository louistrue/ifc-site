"""
Site geometry utilities

Functions for creating site solids and calculating height offsets.
"""

import numpy as np
import math
from shapely.geometry import Polygon
from typing import List, Tuple

try:
    from scipy.spatial import cKDTree
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def _circular_mean(values: List[float], window_size: int) -> List[float]:
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


def _best_fit_plane(ext_coords: List[Tuple[float, float, float]]) -> List[float]:
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


def create_site_solid_coords(site_polygon, site_coords_3d: List[Tuple[float, float, float]], 
                             z_offset_adjustment: float = 0.0):
    # Note: site_polygon parameter is reserved for future use (e.g., validation or additional processing)
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
    # Apply smoothing
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


def calculate_height_offset(site_polygon, site_coords_3d: List[Tuple[float, float, float]], 
                           terrain_coords: List[Tuple[float, float]], 
                           terrain_elevations: List[float]) -> float:
    """
    Calculate Z offset needed to align site solid edges with terrain.
    
    Returns the average offset to apply to smoothed site elevations.
    """
    # Sample terrain elevations at site boundary points
    boundary_terrain_z = []
    
    if SCIPY_AVAILABLE and len(terrain_coords) > 100:
        # Use spatial index for large datasets (O(n log n) instead of O(n×m))
        terrain_points = np.array(terrain_coords)
        tree = cKDTree(terrain_points)
        for x, y, _ in site_coords_3d:
            _, idx = tree.query([x, y], k=1)
            boundary_terrain_z.append(terrain_elevations[idx])
    else:
        # Fallback to linear search for small datasets or when scipy unavailable
        for x, y, _ in site_coords_3d:
            # Find closest terrain point
            min_dist = float('inf')
            closest_z = None
            for idx, (tx, ty) in enumerate(terrain_coords):
                dist = math.sqrt((tx - x)**2 + (ty - y)**2)
                if dist < min_dist:
                    min_dist = dist
                    closest_z = terrain_elevations[idx]
            
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
    if len(boundary_terrain_z) != len(smoothed_boundary_z):
        return 0.0
    
    offsets = [tz - sz for tz, sz in zip(boundary_terrain_z, smoothed_boundary_z)]
    avg_offset = sum(offsets) / len(offsets)
    
    return avg_offset

