"""
Convert Swiss building data to IFC elements

This module provides functions to convert BuildingFeature objects
(from building_loader.py) into IFC building representations.
"""

import logging
from typing import List, Tuple, Optional

import ifcopenshell
import ifcopenshell.api
from shapely.geometry import Polygon
from shapely.ops import orient, triangulate

from src.building_loader import BuildingFeature


logger = logging.getLogger(__name__)

# Default height for buildings without height data (meters)
DEFAULT_BUILDING_HEIGHT = 10.0
# Minimum extrusion height to ensure visibility
MIN_EXTRUSION_HEIGHT = 0.5


def create_building_footprint_surface(
    model: ifcopenshell.file,
    building: BuildingFeature,
    body_context,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    base_elevation: float = 0.0,
    offset_z: float = 0.0
) -> Optional[ifcopenshell.entity_instance]:
    """
    Create a visible 3D surface for the building footprint (flat polygon at ground level)
    
    This ensures buildings are visible even without height data.
    """
    if building.geometry is None or building.geometry.is_empty:
        return None
    
    try:
        coords = list(building.geometry.exterior.coords)
    except Exception as e:
        logger.warning(f"Building {building.id} has invalid geometry: {e}")
        return None
    
    if len(coords) < 3:
        return None
    
    # Remove duplicate closing point if present
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    
    if len(coords) < 3:
        return None
    
    # Create polygon at base elevation
    z = float(base_elevation - offset_z)
    
    # Triangulate the polygon for proper surface representation
    polygon_2d = Polygon([(x - offset_x, y - offset_y) for x, y in coords])
    if not polygon_2d.is_valid:
        polygon_2d = polygon_2d.buffer(0)
    if polygon_2d.is_empty:
        return None
    
    faces = []
    
    # Triangulate and create faces
    try:
        for tri in triangulate(polygon_2d):
            if not polygon_2d.contains(tri.centroid):
                continue
            
            oriented_tri = orient(tri, sign=1.0)
            tri_coords = list(oriented_tri.exterior.coords)[:-1]
            
            if len(tri_coords) < 3:
                continue
            
            tri_points = [
                model.createIfcCartesianPoint([float(x), float(y), z])
                for x, y in tri_coords
            ]
            
            tri_loop = model.createIfcPolyLoop(tri_points)
            faces.append(model.createIfcFace([
                model.createIfcFaceOuterBound(tri_loop, True)
            ]))
    except Exception as e:
        logger.warning(f"Failed to triangulate building {building.id}: {e}")
        return None
    
    if not faces:
        return None
    
    # Create shell surface
    shell = model.createIfcOpenShell(faces)
    surface = model.createIfcShellBasedSurfaceModel([shell])
    
    rep = model.createIfcShapeRepresentation(
        body_context,
        "Body",
        "SurfaceModel",
        [surface]
    )
    
    return rep


def create_building_extrusion(
    model: ifcopenshell.file,
    building: BuildingFeature,
    body_context,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    base_elevation: float = 0.0,
    height: float = DEFAULT_BUILDING_HEIGHT
) -> Optional[ifcopenshell.entity_instance]:
    """
    Create 3D extruded solid representation for a building
    
    Args:
        model: IFC model
        building: BuildingFeature to convert
        body_context: IFC Body context
        offset_x, offset_y, offset_z: Project origin offsets
        base_elevation: Base elevation for extrusion
        height: Building height in meters

    Returns:
        IfcShapeRepresentation for solid or None if geometry invalid
    """
    if building.geometry is None or building.geometry.is_empty:
        logger.warning(f"Building {building.id} has empty geometry")
        return None

    try:
        coords = list(building.geometry.exterior.coords)
    except Exception as e:
        logger.warning(f"Building {building.id} has invalid geometry: {e}")
        return None
    
    if len(coords) < 3:
        logger.warning(f"Building {building.id} has too few coordinates ({len(coords)})")
        return None
    
    # Remove duplicate closing point
    if coords[0] == coords[-1]:
        coords = coords[:-1]
    
    if len(coords) < 3:
        logger.warning(f"Building {building.id} has too few unique coordinates")
        return None

    # Apply offsets
    coords_2d = [
        (float(x - offset_x), float(y - offset_y))
        for x, y in coords
    ]

    # Create IfcPolyline for the footprint profile
    profile_points = [
        model.createIfcCartesianPoint([x, y])
        for x, y in coords_2d
    ]
    # Close the profile
    profile_points.append(profile_points[0])

    polyline = model.createIfcPolyLine(profile_points)

    # Create arbitrary profile
    profile = model.createIfcArbitraryClosedProfileDef(
        "AREA",
        None,
        polyline
    )

    # Create position for extrusion (at base elevation)
    position = model.createIfcAxis2Placement3D(
        model.createIfcCartesianPoint([0.0, 0.0, float(base_elevation - offset_z)]),
        model.createIfcDirection([0.0, 0.0, 1.0]),
        model.createIfcDirection([1.0, 0.0, 0.0])
    )

    # Create extruded solid
    extrusion = model.createIfcExtrudedAreaSolid(
        profile,
        position,
        model.createIfcDirection([0.0, 0.0, 1.0]),
        float(height)
    )

    # Create shape representation
    rep = model.createIfcShapeRepresentation(
        body_context,
        "Body",
        "SweptSolid",
        [extrusion]
    )

    return rep


def create_building_footprint_curve(
    model: ifcopenshell.file,
    building: BuildingFeature,
    footprint_context,
    offset_x: float = 0.0,
    offset_y: float = 0.0
) -> Optional[ifcopenshell.entity_instance]:
    """
    Create 2D footprint curve representation
    """
    if building.geometry is None or building.geometry.is_empty:
        return None
    
    try:
        coords = list(building.geometry.exterior.coords)
    except:
        return None
    
    if len(coords) < 3:
        return None

    footprint_points = [
        model.createIfcCartesianPoint([
            float(x - offset_x),
            float(y - offset_y)
        ])
        for x, y in coords
    ]

    polyline = model.createIfcPolyLine(footprint_points)

    rep = model.createIfcShapeRepresentation(
        footprint_context,
        "FootPrint",
        "Curve2D",
        [polyline]
    )

    return rep


def add_building_properties(
    model: ifcopenshell.file,
    ifc_building: ifcopenshell.entity_instance,
    building: BuildingFeature,
    height_used: float,
    height_source: str
):
    """
    Add property sets to IFC building
    """
    pset = ifcopenshell.api.run(
        "pset.add_pset",
        model,
        product=ifc_building,
        name="Pset_BuildingCommon"
    )

    properties = {
        "GrossPlannedArea": building.geometry.area if building.geometry else 0,
        "TotalHeight": height_used,
        "HeightSource": height_source  # "actual", "estimated", or "default"
    }

    if building.building_class:
        properties["BuildingClass"] = building.building_class

    if building.year_built:
        properties["YearOfConstruction"] = building.year_built

    ifcopenshell.api.run(
        "pset.edit_pset",
        model,
        pset=pset,
        properties=properties
    )

    # Add Swiss building attributes if available
    if building.attributes:
        pset_swiss = ifcopenshell.api.run(
            "pset.add_pset",
            model,
            product=ifc_building,
            name="CPset_SwissBuilding"
        )

        swiss_props = {"SourceID": building.id}
        if building.roof_type:
            swiss_props["RoofType"] = building.roof_type
        
        for key in ["egid", "gbauj", "gastw", "garea", "gvol"]:
            if key in building.attributes:
                swiss_props[key] = str(building.attributes[key])

        ifcopenshell.api.run(
            "pset.edit_pset",
            model,
            pset=pset_swiss,
            properties=swiss_props
        )


def building_to_ifc(
    model: ifcopenshell.file,
    building: BuildingFeature,
    site: ifcopenshell.entity_instance,
    body_context,
    footprint_context,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    base_elevation: float = 0.0,
    default_height: float = DEFAULT_BUILDING_HEIGHT
) -> Optional[ifcopenshell.entity_instance]:
    """
    Convert a BuildingFeature to an IfcBuilding element with visible geometry

    Args:
        model: IFC model
        building: BuildingFeature to convert
        site: Parent IfcSite element
        body_context: IFC Body context
        footprint_context: IFC FootPrint context
        offset_x, offset_y, offset_z: Project origin offsets
        base_elevation: Base elevation for building (ground level)
        default_height: Default building height if not provided (meters)

    Returns:
        IfcBuilding element or None if failed
    """
    # Validate geometry first
    if building.geometry is None or building.geometry.is_empty:
        logger.warning(f"Skipping building {building.id}: no geometry")
        return None
    
    try:
        coords = list(building.geometry.exterior.coords)
        if len(coords) < 3:
            logger.warning(f"Skipping building {building.id}: too few coordinates")
            return None
    except Exception as e:
        logger.warning(f"Skipping building {building.id}: invalid geometry - {e}")
        return None

    # Determine height to use
    if building.height and building.height > 0:
        height_used = building.height
        height_source = "actual"
    else:
        height_used = default_height
        height_source = "default"

    # Create IfcBuilding
    ifc_building = ifcopenshell.api.run(
        "root.create_entity",
        model,
        ifc_class="IfcBuilding",
        name=str(building.id)
    )

    if building.building_class:
        ifc_building.Description = str(building.building_class)

    # Create placement relative to site
    origin = model.createIfcCartesianPoint([0.0, 0.0, 0.0])
    axis = model.createIfcDirection([0.0, 0.0, 1.0])
    ref_direction = model.createIfcDirection([1.0, 0.0, 0.0])
    axis2_placement = model.createIfcAxis2Placement3D(origin, axis, ref_direction)
    building_placement = model.createIfcLocalPlacement(
        site.ObjectPlacement,
        axis2_placement
    )
    ifc_building.ObjectPlacement = building_placement

    # Assign building to site
    ifcopenshell.api.run(
        "aggregate.assign_object",
        model,
        products=[ifc_building],
        relating_object=site
    )

    # Create representations
    representations = []

    # 1. Create 3D extruded body (always - ensures visibility)
    body_rep = create_building_extrusion(
        model, building, body_context,
        offset_x, offset_y, offset_z, base_elevation, height_used
    )
    if body_rep:
        representations.append(body_rep)
    else:
        # Fallback: create surface footprint if extrusion fails
        surface_rep = create_building_footprint_surface(
            model, building, body_context,
            offset_x, offset_y, base_elevation, offset_z
        )
        if surface_rep:
            representations.append(surface_rep)

    # 2. Create 2D footprint curve
    footprint_rep = create_building_footprint_curve(
        model, building, footprint_context, offset_x, offset_y
    )
    if footprint_rep:
        representations.append(footprint_rep)

    # Assign representation
    if representations:
        ifc_building.Representation = model.createIfcProductDefinitionShape(
            None, None, representations
        )
    else:
        logger.warning(f"Building {building.id}: no representations created")
        return None

    # Add properties
    add_building_properties(model, ifc_building, building, height_used, height_source)

    logger.info(f"Created IfcBuilding: {building.id} (height: {height_used}m [{height_source}])")

    return ifc_building


def buildings_to_ifc(
    model: ifcopenshell.file,
    buildings: List[BuildingFeature],
    site: ifcopenshell.entity_instance,
    body_context,
    footprint_context,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    base_elevation: float = 0.0,
    default_height: float = DEFAULT_BUILDING_HEIGHT
) -> List[ifcopenshell.entity_instance]:
    """
    Convert multiple buildings to IFC

    Args:
        model: IFC model
        buildings: List of BuildingFeature objects
        site: Parent IfcSite element
        body_context: IFC Body context
        footprint_context: IFC FootPrint context
        offset_x, offset_y, offset_z: Project origin offsets
        base_elevation: Base elevation for buildings
        default_height: Default building height if not provided (meters)

    Returns:
        List of IfcBuilding elements
    """
    ifc_buildings = []

    logger.info(f"Converting {len(buildings)} buildings to IFC...")

    for building in buildings:
        try:
            ifc_building = building_to_ifc(
                model, building, site, body_context, footprint_context,
                offset_x, offset_y, offset_z, base_elevation, default_height
            )
            if ifc_building:
                ifc_buildings.append(ifc_building)
        except Exception as e:
            logger.error(f"Failed to convert building {building.id}: {e}")

    logger.info(f"Successfully converted {len(ifc_buildings)}/{len(buildings)} buildings")

    return ifc_buildings
