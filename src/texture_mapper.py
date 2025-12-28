"""
IFC Texture Mapping Utilities

Functions for creating IFC texture entities and applying UV mapping to geometry.
"""

import logging
from typing import List, Tuple, Optional
import ifcopenshell

logger = logging.getLogger(__name__)


def generate_uv_coordinates(
    vertices: List[Tuple[float, float, float]], 
    bbox: Tuple[float, float, float, float]
) -> List[Tuple[float, float]]:
    """
    Generate UV coordinates (0-1 range) from world coordinates.
    
    Args:
        vertices: List of (x, y, z) world coordinates
        bbox: Bounding box (minx, miny, maxx, maxy) of the texture image
        
    Returns:
        List of (u, v) texture coordinates
    """
    minx, miny, maxx, maxy = bbox
    width = maxx - minx
    height = maxy - miny
    
    if width <= 0 or height <= 0:
        logger.warning(f"Invalid bbox dimensions: {bbox}")
        return [(0.0, 0.0)] * len(vertices)
    
    uvs = []
    for x, y, z in vertices:
        u = (x - minx) / width
        v = (y - miny) / height
        # Note: IFC uses (0,0) at bottom-left, but PIL images use top-left
        # We'll flip V coordinate to match IFC convention
        v = 1.0 - v
        uvs.append((u, v))
    
    return uvs


def create_texture_from_image(
    model: ifcopenshell.file,
    image_bytes: bytes,
    name: str,
    embed: bool = True,
    output_dir: str = None,
    ifc_filename: str = None
) -> ifcopenshell.entity_instance:
    """
    Create IFC texture entity from image data.
    
    For better BIM viewer compatibility, saves texture as external file
    and creates IfcImageTexture referencing it.
    
    Args:
        model: IFC model
        image_bytes: JPEG/PNG image data
        name: Name for the texture
        embed: If True, attempt embedded blob (may not work in all viewers)
        output_dir: Directory to save texture file (uses current dir if None)
        ifc_filename: IFC filename to derive texture filename from
        
    Returns:
        IfcImageTexture entity
    """
    import os
    
    # Determine texture filename
    if ifc_filename:
        base_name = os.path.splitext(os.path.basename(ifc_filename))[0]
        texture_filename = f"{base_name}_texture.jpg"
    else:
        texture_filename = f"{name}.jpg"
    
    # Determine output path
    if output_dir:
        texture_path = os.path.join(output_dir, texture_filename)
    else:
        texture_path = texture_filename
    
    # Save texture to file
    try:
        with open(texture_path, 'wb') as f:
            f.write(image_bytes)
        logger.info(f"Saved texture to {texture_path}")
    except Exception as e:
        logger.error(f"Failed to save texture file: {e}")
        return None
    
    # Create IfcImageTexture referencing the external file
    # IFC4X3 IfcImageTexture parameters:
    # - RepeatS, RepeatT: Boolean (texture tiling)
    # - Mode: String (optional)
    # - TextureTransform: optional
    # - Parameter: List of strings (optional)
    # - URLReference: String - path to image file
    
    # Use relative path in IFC (standard practice)
    # Parameter format: (source, function, color, factor)
    # - source: '' (empty) for default, or 'FACTOR' for factor-based blending
    # - function: '' (empty) for default
    # - color: '1 1 1' (white) for full intensity, or RGB values
    # - factor: '1' for full opacity/intensity
    texture = model.createIfcImageTexture(
        RepeatS=True,   # Allow tiling for better coverage
        RepeatT=True,   # Allow tiling for better coverage
        Mode="REPLACE",  # REPLACE is the standard mode for simple diffuse textures
        TextureTransform=None,
        Parameter=['', '', '1 1 1', '1'],  # Standard parameters: empty source/function, white color, full factor
        URLReference=texture_filename  # Relative path to texture file
    )
    
    return texture


def apply_texture_to_element(
    model: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    texture: ifcopenshell.entity_instance,
    vertices: List[Tuple[float, float, float]],
    uv_coords: List[Tuple[float, float]],
    bbox: Tuple[float, float, float, float],
    body_context: ifcopenshell.entity_instance,
    embed: bool = True
) -> bool:
    """
    Apply texture with UV mapping to an IFC element.
    
    Args:
        model: IFC model
        element: IFC element (e.g., IfcGeographicElement)
        texture: IfcBlobTexture or IfcImageTexture
        vertices: List of (x, y, z) vertex coordinates
        uv_coords: List of (u, v) texture coordinates
        bbox: Bounding box of texture image
        body_context: IFC representation context
        embed: Whether texture is embedded (affects texture type)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the element's representation
        if not hasattr(element, 'Representation') or element.Representation is None:
            logger.warning(f"Element {element} has no representation")
            return False
        
        representation = element.Representation
        if not hasattr(representation, 'Representations') or not representation.Representations:
            logger.warning(f"Element {element} has no representations")
            return False
        
        # Find the body representation
        body_rep = None
        for rep in representation.Representations:
            if rep.ContextOfItems == body_context and rep.RepresentationIdentifier == "Body":
                body_rep = rep
                break
        
        if body_rep is None:
            logger.warning(f"Could not find Body representation for {element}")
            return False
        
        # Create texture coordinate generator for automatic UV mapping
        # Mode "COORD" generates UVs from XY world coordinates (vertex positions)
        # This maps world XY coordinates to UV texture coordinates automatically
        minx, miny, maxx, maxy = bbox
        width = maxx - minx
        height = maxy - miny
        
        # Calculate scale factors to map world coordinates to 0-1 UV range
        # Parameter format: [scale_x, scale_y, offset_x, offset_y]
        # These transform world XY -> UV: u = (x - minx) / width, v = (y - miny) / height
        scale_x = 1.0 / width if width > 0 else 1.0
        scale_y = 1.0 / height if height > 0 else 1.0
        offset_x = -minx * scale_x
        offset_y = -miny * scale_y
        
        # Create texture coordinate generator
        # The generator wraps the texture and provides automatic UV mapping
        tex_coord_gen = model.createIfcTextureCoordinateGenerator(
            [texture],  # Maps: list of textures to apply coordinates to
            "COORD",    # Mode: generate UVs from vertex XY world coordinates
            [scale_x, scale_y, offset_x, offset_y]  # Parameter: transformation floats
        )
        
        # Create surface style with BOTH texture and texture coordinate generator
        # The texture coordinate generator provides UV mapping
        # IFC4X3 uses IfcSurfaceStyleWithTextures for textures
        # Include both for maximum compatibility
        surface_style_with_textures = model.createIfcSurfaceStyleWithTextures(
            [texture, tex_coord_gen]  # Include texture directly AND coordinate generator
        )
        
        # Create the main surface style
        surface_style = model.createIfcSurfaceStyle(
            "SatelliteImagery",
            "BOTH",  # Both shading and rendering
            [surface_style_with_textures]
        )
        
        # Apply style to all items in representation
        for item in body_rep.Items:
            # Create styled item linking geometry to style
            model.createIfcStyledItem(item, [surface_style], None)
        
        logger.debug(f"Applied texture to {element}")
        return True
        
    except Exception as e:
        logger.error(f"Error applying texture to element: {e}")
        import traceback
        traceback.print_exc()
        return False


def apply_texture_to_faces(
    model: ifcopenshell.file,
    faces: List[ifcopenshell.entity_instance],
    texture: ifcopenshell.entity_instance,
    vertex_to_uv: dict
) -> bool:
    """
    Apply texture with UV mapping to specific faces.
    
    This is a more advanced function that maps texture coordinates to individual faces.
    
    Args:
        model: IFC model
        faces: List of IfcFace entities
        texture: IfcBlobTexture or IfcImageTexture
        vertex_to_uv: Dictionary mapping vertex coordinates (x, y, z) to (u, v)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        surface_style_with_textures = model.createIfcSurfaceStyleWithTextures(
            [texture]
        )
        
        surface_style = model.createIfcSurfaceStyle(
            "SatelliteImagery",
            "BOTH",
            [surface_style_with_textures]
        )
        
        # Apply to each face
        for face in faces:
            # Get vertices from face
            # This requires traversing the face's bounds
            if hasattr(face, 'Bounds'):
                for bound in face.Bounds:
                    if hasattr(bound, 'Bound') and hasattr(bound.Bound, 'Points'):
                        # Create texture map for this face
                        texture_map = model.createIfcTextureMap(
                            MappedTo=bound.Bound,
                            Maps=[texture]
                        )
                        
                        # Apply style
                        model.createIfcStyledItem(face, [surface_style], None)
        
        return True
        
    except Exception as e:
        logger.error(f"Error applying texture to faces: {e}")
        import traceback
        traceback.print_exc()
        return False

