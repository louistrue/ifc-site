"""
glTF Exporter for Three.js Visualization

Exports site models as glTF/GLB files with proper texture mapping for web visualization.
"""

import logging
import os
import numpy as np
from typing import List, Optional, Tuple, Dict
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False
    logger.warning("trimesh not available. glTF export will be disabled.")


def create_terrain_mesh_with_uvs(
    triangles: List[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]],
    imagery_bbox: Tuple[float, float, float, float],
    offset_x: float,
    offset_y: float,
    offset_z: float
) -> Optional['trimesh.Trimesh']:
    """
    Create a trimesh terrain mesh with UV coordinates mapped to satellite imagery.
    
    Args:
        triangles: List of triangle tuples, each containing 3 (x, y, z) vertices
        imagery_bbox: (minx, miny, maxx, maxy) bounding box of satellite imagery in world coordinates
        offset_x, offset_y, offset_z: Offsets to convert world coordinates to local coordinates
        
    Returns:
        trimesh.Trimesh object with UV coordinates, or None if trimesh unavailable
    """
    if not TRIMESH_AVAILABLE:
        return None
    
    minx, miny, maxx, maxy = imagery_bbox
    width = maxx - minx
    height = maxy - miny
    
    if width <= 0 or height <= 0:
        logger.warning("Invalid imagery bounding box, cannot create UV coordinates")
        return None
    
    # Collect all vertices and faces
    vertices = []
    faces = []
    uv_coords = []
    
    vertex_map = {}  # Map (x, y, z) -> vertex index
    
    for tri in triangles:
        face_indices = []
        for pt in tri:
            # Convert to local coordinates
            local_pt = (pt[0] - offset_x, pt[1] - offset_y, pt[2] - offset_z)
            
            # Check if vertex already exists
            pt_key = (round(local_pt[0], 6), round(local_pt[1], 6), round(local_pt[2], 6))
            
            if pt_key not in vertex_map:
                vertex_map[pt_key] = len(vertices)
                vertices.append(local_pt)
                
                # Calculate UV coordinates based on world XY position
                world_x = pt[0]  # Original world coordinates
                world_y = pt[1]
                
                # Map world coordinates to UV (0-1 range)
                # Swiss coordinates: X increases east, Y increases north
                # glTF UV space: U increases right, V increases up (OpenGL convention)
                # Both coordinate systems align, so no flip needed
                u = (world_x - minx) / width
                v = (world_y - miny) / height
                
                uv_coords.append([u, v])
            
            face_indices.append(vertex_map[pt_key])
        
        faces.append(face_indices)
    
    if not vertices or not faces:
        logger.warning("No vertices or faces to create terrain mesh")
        return None
    
    # Create trimesh
    vertices_array = np.array(vertices, dtype=np.float32)
    faces_array = np.array(faces, dtype=np.uint32)
    uv_array = np.array(uv_coords, dtype=np.float32)
    
    mesh = trimesh.Trimesh(vertices=vertices_array, faces=faces_array)
    
    # Apply UV coordinates
    mesh.visual.uv = uv_array
    
    return mesh


def create_road_meshes(
    roads: List,
    offset_x: float,
    offset_y: float,
    offset_z: float
) -> List['trimesh.Trimesh']:
    """
    Create trimesh meshes for road geometry as extruded paths.
    
    Args:
        roads: List of RoadFeature objects
        offset_x, offset_y, offset_z: Offsets to convert world coordinates to local coordinates
        
    Returns:
        List of trimesh.Trimesh objects
    """
    if not TRIMESH_AVAILABLE:
        return []
    
    meshes = []
    
    for road in roads:
        if not hasattr(road, 'geometry') or road.geometry is None:
            continue
        
        try:
            # Extract coordinates from road geometry (LineString)
            if hasattr(road.geometry, 'coords'):
                coords = list(road.geometry.coords)
            else:
                continue
            
            if len(coords) < 2:
                continue
            
            # Get road width (default 4m)
            width = getattr(road, 'width', 4.0) or 4.0
            half_width = width / 2.0
            
            # Create a path mesh by extruding the line
            # Build vertices for a ribbon along the road
            vertices = []
            faces = []
            
            for i, pt in enumerate(coords):
                x = pt[0] - offset_x
                y = pt[1] - offset_y
                z = (pt[2] - offset_z if len(pt) > 2 else 0.0) + 0.1  # Slight offset above terrain
                
                # Calculate perpendicular direction for road width
                if i < len(coords) - 1:
                    dx = coords[i + 1][0] - pt[0]
                    dy = coords[i + 1][1] - pt[1]
                elif i > 0:
                    dx = pt[0] - coords[i - 1][0]
                    dy = pt[1] - coords[i - 1][1]
                else:
                    dx, dy = 1, 0
                
                # Normalize and get perpendicular
                length = np.sqrt(dx * dx + dy * dy)
                if length > 0:
                    nx, ny = -dy / length, dx / length
                else:
                    nx, ny = 0, 1
                
                # Add left and right vertices
                vertices.append([x + nx * half_width, y + ny * half_width, z])
                vertices.append([x - nx * half_width, y - ny * half_width, z])
            
            # Create faces (quads as 2 triangles)
            for i in range(len(coords) - 1):
                v0 = i * 2
                v1 = i * 2 + 1
                v2 = (i + 1) * 2
                v3 = (i + 1) * 2 + 1
                faces.append([v0, v2, v1])
                faces.append([v1, v2, v3])
            
            if vertices and faces:
                mesh = trimesh.Trimesh(
                    vertices=np.array(vertices, dtype=np.float32),
                    faces=np.array(faces, dtype=np.uint32)
                )
                # Set road color (dark gray/asphalt)
                mesh.visual.face_colors = [80, 80, 80, 255]  # RGBA
                meshes.append(mesh)
                
        except Exception as e:
            logger.debug(f"Error processing road {getattr(road, 'id', 'unknown')}: {e}")
            continue
    
    return meshes


def create_railway_meshes(
    railways: List,
    offset_x: float,
    offset_y: float,
    offset_z: float
) -> List['trimesh.Trimesh']:
    """
    Create trimesh meshes for railway geometry.
    
    Args:
        railways: List of RailwayFeature objects
        offset_x, offset_y, offset_z: Offsets to convert world coordinates to local coordinates
        
    Returns:
        List of trimesh.Trimesh objects
    """
    if not TRIMESH_AVAILABLE:
        return []
    
    meshes = []
    
    for railway in railways:
        if not hasattr(railway, 'geometry') or railway.geometry is None:
            continue
        
        try:
            if hasattr(railway.geometry, 'coords'):
                coords = list(railway.geometry.coords)
            else:
                continue
            
            if len(coords) < 2:
                continue
            
            # Railway width (standard gauge ~1.5m, with ballast ~3m)
            width = 3.0
            half_width = width / 2.0
            
            vertices = []
            faces = []
            
            for i, pt in enumerate(coords):
                x = pt[0] - offset_x
                y = pt[1] - offset_y
                z = (pt[2] - offset_z if len(pt) > 2 else 0.0) + 0.15  # Slight offset
                
                if i < len(coords) - 1:
                    dx = coords[i + 1][0] - pt[0]
                    dy = coords[i + 1][1] - pt[1]
                elif i > 0:
                    dx = pt[0] - coords[i - 1][0]
                    dy = pt[1] - coords[i - 1][1]
                else:
                    dx, dy = 1, 0
                
                length = np.sqrt(dx * dx + dy * dy)
                if length > 0:
                    nx, ny = -dy / length, dx / length
                else:
                    nx, ny = 0, 1
                
                vertices.append([x + nx * half_width, y + ny * half_width, z])
                vertices.append([x - nx * half_width, y - ny * half_width, z])
            
            for i in range(len(coords) - 1):
                v0 = i * 2
                v1 = i * 2 + 1
                v2 = (i + 1) * 2
                v3 = (i + 1) * 2 + 1
                faces.append([v0, v2, v1])
                faces.append([v1, v2, v3])
            
            if vertices and faces:
                mesh = trimesh.Trimesh(
                    vertices=np.array(vertices, dtype=np.float32),
                    faces=np.array(faces, dtype=np.uint32)
                )
                # Set railway color (brown/gravel)
                mesh.visual.face_colors = [139, 119, 101, 255]  # RGBA
                meshes.append(mesh)
                
        except Exception as e:
            logger.debug(f"Error processing railway {getattr(railway, 'id', 'unknown')}: {e}")
            continue
    
    return meshes


def create_building_meshes(
    buildings: List,
    offset_x: float,
    offset_y: float,
    offset_z: float,
    imagery_bbox: Tuple[float, float, float, float] = None
) -> List['trimesh.Trimesh']:
    """
    Create trimesh meshes for building geometry with UV mapping for satellite imagery.
    Optimized for performance with vectorized operations.
    
    Args:
        buildings: List of BuildingFeature objects with 3D faces
        offset_x, offset_y, offset_z: Offsets to convert world coordinates to local coordinates
        imagery_bbox: (minx, miny, maxx, maxy) bounding box for UV mapping (optional)
        
    Returns:
        List of trimesh.Trimesh objects
    """
    if not TRIMESH_AVAILABLE:
        return []
    
    # Calculate UV scale factors if imagery bbox provided
    has_uv = imagery_bbox is not None
    if has_uv:
        minx, miny, maxx, maxy = imagery_bbox
        width = maxx - minx
        height = maxy - miny
        if width <= 0 or height <= 0:
            has_uv = False
    
    meshes = []
    
    # Process buildings with progress indication for large batches
    total = len(buildings)
    if total > 100:
        import time
        start_time = time.time()
        last_log = 0
    
    for idx, building in enumerate(buildings):
        # Log progress for large batches
        if total > 100 and idx > 0 and idx % 100 == 0:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 0
            remaining = (total - idx) / rate if rate > 0 else 0
            logger.debug(f"Building meshes: {idx}/{total} ({elapsed:.1f}s, ~{remaining:.1f}s remaining)")
        if not hasattr(building, 'faces') or not building.faces:
            continue
        
        try:
            # Pre-allocate arrays for better performance
            all_vertices = []
            all_faces = []
            all_uvs = [] if has_uv else None
            vertex_offset = 0
            
            for face in building.faces:
                if len(face) < 3:
                    continue
                
                # Convert face to numpy array for vectorized operations
                face_array = np.array(face, dtype=np.float32)
                n_pts = len(face_array)
                
                # Extract world coordinates
                world_x = face_array[:, 0]
                world_y = face_array[:, 1]
                world_z = face_array[:, 2] if face_array.shape[1] > 2 else np.zeros(n_pts)
                
                # Convert to local coordinates (vectorized)
                local_x = world_x - offset_x
                local_y = world_y - offset_y
                local_z = world_z - offset_z
                
                # Stack into vertices
                face_vertices = np.column_stack([local_x, local_y, local_z])
                all_vertices.append(face_vertices)
                
                # Calculate UVs if needed (vectorized)
                if has_uv:
                    u = (world_x - minx) / width
                    v = (world_y - miny) / height
                    face_uv = np.column_stack([u, v])
                    if all_uvs is None:
                        all_uvs = []
                    all_uvs.append(face_uv)
                
                # Triangulate the face (fan triangulation)
                for i in range(1, n_pts - 1):
                    all_faces.append([
                        vertex_offset,
                        vertex_offset + i,
                        vertex_offset + i + 1
                    ])
                
                vertex_offset += n_pts
            
            if all_vertices and all_faces:
                # Concatenate all vertices at once
                vertices = np.vstack(all_vertices).astype(np.float32)
                faces = np.array(all_faces, dtype=np.uint32)
                
                mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                
                # Apply UV coordinates if available
                if has_uv and all_uvs:
                    mesh.visual.uv = np.vstack(all_uvs).astype(np.float32)
                else:
                    # Fallback to color if no UV
                    mesh.visual.face_colors = [200, 190, 170, 255]  # RGBA
                
                meshes.append(mesh)
                
        except Exception as e:
            logger.debug(f"Error processing building {getattr(building, 'id', 'unknown')}: {e}")
            continue
    
    return meshes


def create_water_meshes(
    waters: List,
    offset_x: float,
    offset_y: float,
    offset_z: float
) -> List['trimesh.Trimesh']:
    """
    Create trimesh meshes for water features.
    
    Args:
        waters: List of WaterFeature objects
        offset_x, offset_y, offset_z: Offsets to convert world coordinates to local coordinates
        
    Returns:
        List of trimesh.Trimesh objects
    """
    if not TRIMESH_AVAILABLE:
        return []
    
    meshes = []
    
    for water in waters:
        if not hasattr(water, 'geometry') or water.geometry is None:
            continue
        
        # Skip underground water
        if hasattr(water, 'is_underground') and water.is_underground:
            continue
        
        try:
            # Extract polygon coordinates
            if hasattr(water.geometry, 'exterior'):
                coords = list(water.geometry.exterior.coords)
            elif hasattr(water.geometry, 'coords'):
                coords = list(water.geometry.coords)
            else:
                continue
            
            if len(coords) < 3:
                continue
            
            # Convert to local coordinates
            local_coords = [(p[0] - offset_x, p[1] - offset_y, p[2] - offset_z if len(p) > 2 else 0.0) 
                           for p in coords]
            
            vertices = np.array(local_coords, dtype=np.float32)
            
            # Create triangulation
            try:
                from scipy.spatial import ConvexHull
                hull = ConvexHull(vertices[:, :2])  # Use XY only for hull
                faces = hull.simplices
                mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                
                # Set water color (blue)
                mesh.visual.vertex_colors = [50, 100, 200, 200]  # RGBA (semi-transparent blue)
                meshes.append(mesh)
            except Exception as e:
                logger.debug(f"Could not create water mesh: {e}")
                continue
        except Exception as e:
            logger.debug(f"Error processing water {getattr(water, 'id', 'unknown')}: {e}")
            continue
    
    return meshes


def export_gltf(
    terrain_mesh: Optional['trimesh.Trimesh'],
    other_meshes: List['trimesh.Trimesh'],
    texture_bytes: Optional[bytes],
    texture_filename: str,
    output_path: str
) -> bool:
    """
    Export meshes as GLB file with embedded texture.
    
    Args:
        terrain_mesh: Terrain mesh with UV coordinates
        other_meshes: List of other meshes (roads, water, etc.)
        texture_bytes: Raw JPEG/PNG image data
        texture_filename: Filename for texture reference
        output_path: Output GLB file path
        
    Returns:
        True if successful, False otherwise
    """
    if not TRIMESH_AVAILABLE:
        logger.error("trimesh not available, cannot export glTF")
        return False
    
    try:
        # Load texture image if provided
        texture_material = None
        if texture_bytes:
            try:
                img = Image.open(BytesIO(texture_bytes))
                texture_material = trimesh.visual.material.PBRMaterial(
                    baseColorTexture=img,
                    metallicFactor=0.0,
                    roughnessFactor=0.8
                )
            except Exception as e:
                logger.warning(f"Could not load texture image: {e}")
        
        # Combine all meshes
        all_meshes = []
        
        if terrain_mesh is not None:
            # Apply texture to terrain mesh
            if texture_material:
                terrain_mesh.visual.material = texture_material
            else:
                terrain_mesh.visual.vertex_colors = [150, 150, 150, 255]
            all_meshes.append(terrain_mesh)
        
        # Add other meshes, applying texture to those with UV coordinates
        for mesh in other_meshes:
            # Check if mesh has UV coordinates
            if texture_material and hasattr(mesh.visual, 'uv') and mesh.visual.uv is not None and len(mesh.visual.uv) > 0:
                # Apply satellite texture to meshes with UVs
                mesh.visual.material = texture_material
            # Meshes without UVs keep their vertex/face colors
            all_meshes.append(mesh)
        
        if not all_meshes:
            logger.warning("No meshes to export")
            return False
        
        # Combine into a single scene
        logger.debug(f"Combining {len(all_meshes)} meshes into scene...")
        scene = trimesh.Scene(all_meshes)
        
        # Export as GLB
        logger.debug(f"Exporting GLB to {output_path}...")
        scene.export(output_path, file_type='glb')
        
        logger.info(f"Exported glTF to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error exporting glTF: {e}")
        import traceback
        traceback.print_exc()
        return False

