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


def create_building_footprint_representation(
    model: ifcopenshell.file,
    building: BuildingFeature,
    footprint_context,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0
) -> ifcopenshell.entity_instance:
    """
    Create 2D footprint representation for a building

    Args:
        model: IFC model
        building: BuildingFeature to convert
        footprint_context: IFC FootPrint context
        offset_x, offset_y, offset_z: Project origin offsets

    Returns:
        IfcShapeRepresentation for footprint
    """
    # Get exterior coordinates
    coords = list(building.geometry.exterior.coords)

    # Apply offsets and convert to 2D
    footprint_points = [
        model.createIfcCartesianPoint([
            float(x - offset_x),
            float(y - offset_y)
        ])
        for x, y in coords
    ]

    # Create polyline
    polyline = model.createIfcPolyLine(footprint_points)

    # Create shape representation
    rep = model.createIfcShapeRepresentation(
        footprint_context,
        "FootPrint",
        "Curve2D",
        [polyline]
    )

    return rep


def create_building_extrusion_representation(
    model: ifcopenshell.file,
    building: BuildingFeature,
    body_context,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    base_elevation: float = 0.0
) -> Optional[ifcopenshell.entity_instance]:
    """
    Create 3D extruded solid representation for a building

    Args:
        model: IFC model
        building: BuildingFeature to convert
        body_context: IFC Body context
        offset_x, offset_y, offset_z: Project origin offsets
        base_elevation: Base elevation for extrusion

    Returns:
        IfcShapeRepresentation for solid or None if no height available
    """
    if not building.height or building.height <= 0:
        return None

    # Get exterior coordinates
    coords = list(building.geometry.exterior.coords)
    if coords[0] == coords[-1]:
        coords = coords[:-1]  # Remove duplicate closing point

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
        float(building.height)
    )

    # Create shape representation
    rep = model.createIfcShapeRepresentation(
        body_context,
        "Body",
        "SweptSolid",
        [extrusion]
    )

    return rep


def create_building_brep_representation(
    model: ifcopenshell.file,
    building: BuildingFeature,
    body_context,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    base_elevation: float = 0.0
) -> Optional[ifcopenshell.entity_instance]:
    """
    Create 3D BRep solid representation for a building

    Similar to site_solid.py approach: triangulated top + skirt + bottom
    More accurate for non-rectangular buildings or when height varies

    Args:
        model: IFC model
        building: BuildingFeature to convert
        body_context: IFC Body context
        offset_x, offset_y, offset_z: Project origin offsets
        base_elevation: Base elevation for the solid

    Returns:
        IfcShapeRepresentation for solid or None if no height available
    """
    if not building.height or building.height <= 0:
        return None

    # Get exterior coordinates
    coords = list(building.geometry.exterior.coords)
    if coords[0] == coords[-1]:
        coords = coords[:-1]

    # Apply offsets and set height
    top_elevation = base_elevation + building.height
    coords_3d = [
        (float(x - offset_x), float(y - offset_y), float(top_elevation - offset_z))
        for x, y in coords
    ]

    # Create polygon for triangulation
    polygon_2d = Polygon([(x, y) for x, y, _ in coords_3d])
    if not polygon_2d.is_valid:
        polygon_2d = polygon_2d.buffer(0)
    if polygon_2d.is_empty:
        logger.warning(f"Invalid building footprint for {building.id}, skipping BRep")
        return None

    faces = []

    # Create triangulated top face
    for tri in triangulate(polygon_2d):
        if not polygon_2d.contains(tri.centroid):
            continue

        oriented_tri = orient(tri, sign=1.0)
        tri_coords = list(oriented_tri.exterior.coords)[:-1]

        tri_points = [
            model.createIfcCartesianPoint([
                float(x),
                float(y),
                float(top_elevation - offset_z)
            ])
            for x, y in tri_coords
        ]

        tri_loop = model.createIfcPolyLoop(tri_points)
        faces.append(model.createIfcFace([
            model.createIfcFaceOuterBound(tri_loop, True)
        ]))

    # Create side faces (skirt)
    base_z = float(base_elevation - offset_z)
    top_z = float(top_elevation - offset_z)

    for i in range(len(coords_3d)):
        p1 = coords_3d[i]
        p2 = coords_3d[(i + 1) % len(coords_3d)]

        side_pts = [
            model.createIfcCartesianPoint([p1[0], p1[1], top_z]),
            model.createIfcCartesianPoint([p1[0], p1[1], base_z]),
            model.createIfcCartesianPoint([p2[0], p2[1], base_z]),
            model.createIfcCartesianPoint([p2[0], p2[1], top_z])
        ]

        side_loop = model.createIfcPolyLoop(side_pts)
        faces.append(model.createIfcFace([
            model.createIfcFaceOuterBound(side_loop, True)
        ]))

    # Create bottom face
    bot_points = [
        model.createIfcCartesianPoint([x, y, base_z])
        for x, y, _ in reversed(coords_3d)
    ]
    bot_loop = model.createIfcPolyLoop(bot_points)
    faces.append(model.createIfcFace([
        model.createIfcFaceOuterBound(bot_loop, True)
    ]))

    # Create closed shell and solid
    shell = model.createIfcClosedShell(faces)
    solid = model.createIfcFacetedBrep(shell)

    # Create shape representation
    rep = model.createIfcShapeRepresentation(
        body_context,
        "Body",
        "Brep",
        [solid]
    )

    return rep


def add_building_properties(
    model: ifcopenshell.file,
    ifc_building: ifcopenshell.entity_instance,
    building: BuildingFeature
):
    """
    Add property sets to IFC building

    Args:
        model: IFC model
        ifc_building: IfcBuilding element
        building: BuildingFeature with attribute data
    """
    # Create property set for building data
    pset = ifcopenshell.api.run(
        "pset.add_pset",
        model,
        product=ifc_building,
        name="Pset_BuildingCommon"
    )

    # Add properties
    properties = {}

    if building.height:
        properties["GrossPlannedArea"] = building.geometry.area
        properties["TotalHeight"] = building.height

    if building.building_class:
        properties["BuildingClass"] = building.building_class

    if building.year_built:
        properties["YearOfConstruction"] = building.year_built

    if properties:
        ifcopenshell.api.run(
            "pset.edit_pset",
            model,
            pset=pset,
            properties=properties
        )

    # Add custom property set for Swiss building attributes
    if building.attributes:
        pset_swiss = ifcopenshell.api.run(
            "pset.add_pset",
            model,
            product=ifc_building,
            name="CPset_SwissBuilding"
        )

        swiss_props = {}
        if building.roof_type:
            swiss_props["RoofType"] = building.roof_type
        if "gebaeudeklasse" in building.attributes:
            swiss_props["Gebaeudeklasse"] = building.attributes["gebaeudeklasse"]

        if swiss_props:
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
    use_extrusion: bool = True
) -> ifcopenshell.entity_instance:
    """
    Convert a BuildingFeature to an IfcBuilding element

    Args:
        model: IFC model
        building: BuildingFeature to convert
        site: Parent IfcSite element
        body_context: IFC Body context
        footprint_context: IFC FootPrint context
        offset_x, offset_y, offset_z: Project origin offsets
        base_elevation: Base elevation for building (ground level)
        use_extrusion: If True, use simple extrusion; if False, use BRep

    Returns:
        IfcBuilding element
    """
    # Create IfcBuilding
    ifc_building = ifcopenshell.api.run(
        "root.create_entity",
        model,
        ifc_class="IfcBuilding",
        name=building.id
    )

    # Set building description
    if building.building_class:
        ifc_building.Description = f"{building.building_class}"

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

    # 1. Footprint representation (always)
    footprint_rep = create_building_footprint_representation(
        model, building, footprint_context, offset_x, offset_y, offset_z
    )
    representations.append(footprint_rep)

    # 2. 3D representation (if height available)
    if building.height and building.height > 0:
        if use_extrusion:
            body_rep = create_building_extrusion_representation(
                model, building, body_context,
                offset_x, offset_y, offset_z, base_elevation
            )
        else:
            body_rep = create_building_brep_representation(
                model, building, body_context,
                offset_x, offset_y, offset_z, base_elevation
            )

        if body_rep:
            representations.append(body_rep)

    # Assign representation
    if representations:
        ifc_building.Representation = model.createIfcProductDefinitionShape(
            None, None, representations
        )

    # Add properties
    add_building_properties(model, ifc_building, building)

    logger.info(f"Created IfcBuilding: {building.id} (height: {building.height}m)")

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
    use_extrusion: bool = True
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
        use_extrusion: Use extrusion vs BRep for 3D

    Returns:
        List of IfcBuilding elements
    """
    ifc_buildings = []

    logger.info(f"Converting {len(buildings)} buildings to IFC...")

    for building in buildings:
        try:
            ifc_building = building_to_ifc(
                model, building, site, body_context, footprint_context,
                offset_x, offset_y, offset_z, base_elevation, use_extrusion
            )
            ifc_buildings.append(ifc_building)
        except Exception as e:
            logger.error(f"Failed to convert building {building.id}: {e}")

    logger.info(f"Successfully converted {len(ifc_buildings)}/{len(buildings)} buildings")

    return ifc_buildings
