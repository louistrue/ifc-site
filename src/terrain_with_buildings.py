"""
Extended terrain workflow with building integration

This module extends terrain_with_site.py to include building footprints and 3D models.
"""

import logging
from typing import Optional, List, Tuple

import ifcopenshell

from src.terrain_with_site import (
    run_combined_terrain_workflow,
    fetch_boundary_by_egrid
)
from src.building_loader import (
    SwissBuildingLoader,
    BuildingFeature,
    get_buildings_around_egrid
)
from src.building_to_ifc import buildings_to_ifc


logger = logging.getLogger(__name__)


def run_terrain_with_buildings_workflow(
    egrid: Optional[str] = None,
    center_x: Optional[float] = None,
    center_y: Optional[float] = None,
    radius: float = 500.0,
    resolution: float = 10.0,
    densify: float = 0.5,
    attach_to_solid: bool = False,
    include_terrain: bool = True,
    include_site_solid: bool = True,
    include_buildings: bool = True,
    building_buffer_m: float = 0.0,
    output_path: str = "terrain_with_buildings.ifc",
) -> str:
    """
    Run the combined terrain generation workflow with building integration

    Args:
        egrid: Swiss EGRID identifier
        center_x, center_y: Center coordinates (EPSG:2056)
        radius: Radius of circular terrain area (meters)
        resolution: Grid resolution (meters)
        densify: Site boundary densification interval (meters)
        attach_to_solid: Attach terrain to smoothed site solid edges
        include_terrain: Include surrounding terrain mesh
        include_site_solid: Include site boundary solid
        include_buildings: Include building footprints and 3D models
        building_buffer_m: Buffer around parcel to include buildings (meters)
        output_path: Output IFC file path

    Returns:
        Path to generated IFC file
    """
    if not egrid:
        raise ValueError("EGRID is required for this workflow")

    # Step 1: Generate terrain and site (existing workflow)
    print("="*80)
    print("STEP 1: Generating terrain and site")
    print("="*80)

    base_output = output_path.replace(".ifc", "_base.ifc")

    terrain_ifc_path = run_combined_terrain_workflow(
        egrid=egrid,
        center_x=center_x,
        center_y=center_y,
        radius=radius,
        resolution=resolution,
        densify=densify,
        attach_to_solid=attach_to_solid,
        include_terrain=include_terrain,
        include_site_solid=include_site_solid,
        output_path=base_output,
    )

    # Step 2: Load buildings if requested
    buildings = []
    if include_buildings:
        print("\n" + "="*80)
        print("STEP 2: Loading buildings")
        print("="*80)

        try:
            buildings, stats = get_buildings_around_egrid(
                egrid=egrid,
                buffer_m=building_buffer_m
            )

            print(f"\n✅ Loaded {stats['count']} buildings:")
            print(f"   Average height: {stats['avg_height_m']:.1f}m")
            print(f"   Max height: {stats['max_height_m']:.1f}m")
            print(f"   Total footprint: {stats['total_footprint_area_m2']:.0f}m²")

        except Exception as e:
            logger.error(f"Failed to load buildings: {e}")
            print(f"\n⚠️  Building loading failed: {e}")
            print("   Continuing without buildings...")
            buildings = []

    # Step 3: Add buildings to IFC if any were loaded
    if buildings:
        print("\n" + "="*80)
        print("STEP 3: Adding buildings to IFC model")
        print("="*80)

        try:
            add_buildings_to_ifc(
                ifc_path=base_output,
                buildings=buildings,
                output_path=output_path
            )

            print(f"\n✅ Successfully added {len(buildings)} buildings to IFC")
            print(f"\n🎉 Final output: {output_path}")

            return output_path

        except Exception as e:
            logger.error(f"Failed to add buildings to IFC: {e}")
            print(f"\n⚠️  Building integration failed: {e}")
            print(f"   Base terrain saved to: {base_output}")
            return base_output

    else:
        # No buildings - just rename base output
        if base_output != output_path:
            import shutil
            shutil.move(base_output, output_path)

        print(f"\n✅ Output saved to: {output_path}")
        return output_path


def add_buildings_to_ifc(
    ifc_path: str,
    buildings: List[BuildingFeature],
    output_path: str
):
    """
    Add buildings to an existing IFC file

    Args:
        ifc_path: Path to existing IFC file
        buildings: List of BuildingFeature objects
        output_path: Path for output IFC file
    """
    # Load existing IFC file
    print(f"   Loading IFC file: {ifc_path}")
    model = ifcopenshell.open(ifc_path)

    # Find contexts
    body_context = None
    footprint_context = None

    for context in model.by_type("IfcGeometricRepresentationContext"):
        if context.ContextIdentifier == "Body":
            body_context = context
        elif context.ContextIdentifier == "FootPrint":
            footprint_context = context

    if not body_context or not footprint_context:
        raise ValueError("Required IFC contexts not found in file")

    # Find site element
    sites = model.by_type("IfcSite")
    if not sites:
        raise ValueError("No IfcSite found in file")

    site = sites[0]  # Use first site

    # Get project origin from MapConversion
    map_conv = model.by_type("IfcMapConversion")
    if map_conv:
        offset_x = float(map_conv[0].Eastings)
        offset_y = float(map_conv[0].Northings)
        offset_z = float(map_conv[0].OrthogonalHeight)
    else:
        offset_x = offset_y = offset_z = 0.0

    print(f"   Project origin: E={offset_x}, N={offset_y}, H={offset_z}")

    # Estimate base elevation from site geometry
    # For simplicity, use offset_z as base elevation
    base_elevation = offset_z

    # Add buildings to IFC
    print(f"   Converting {len(buildings)} buildings to IFC...")

    ifc_buildings = buildings_to_ifc(
        model=model,
        buildings=buildings,
        site=site,
        body_context=body_context,
        footprint_context=footprint_context,
        offset_x=offset_x,
        offset_y=offset_y,
        offset_z=offset_z,
        base_elevation=base_elevation
    )

    # Save modified IFC
    print(f"   Saving IFC to: {output_path}")
    model.write(output_path)

    print(f"   ✅ Added {len(ifc_buildings)} buildings to IFC model")


def main():
    """CLI for terrain with buildings workflow"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Create terrain with site and buildings"
    )
    parser.add_argument("--egrid", required=True, help="EGRID number")
    parser.add_argument("--center-x", type=float, help="Center easting (EPSG:2056)")
    parser.add_argument("--center-y", type=float, help="Center northing (EPSG:2056)")
    parser.add_argument("--radius", type=float, default=500.0,
                        help="Radius of circular terrain area (meters), default: 500")
    parser.add_argument("--resolution", type=float, default=10.0,
                        help="Grid resolution (meters), default: 10")
    parser.add_argument("--densify", type=float, default=0.5,
                        help="Site boundary densification interval (meters), default: 0.5")
    parser.add_argument("--attach-to-solid", action="store_true",
                        help="Attach terrain to smoothed site solid edges")
    parser.add_argument("--no-terrain", action="store_true",
                        help="Don't include terrain mesh")
    parser.add_argument("--no-site", action="store_true",
                        help="Don't include site solid")
    parser.add_argument("--include-buildings", action="store_true",
                        help="Include building footprints and 3D models")
    parser.add_argument("--building-buffer", type=float, default=0.0,
                        help="Buffer around parcel to include buildings (meters), default: 0")
    parser.add_argument("--output", default="terrain_with_buildings.ifc",
                        help="Output IFC file path")

    args = parser.parse_args()

    try:
        run_terrain_with_buildings_workflow(
            egrid=args.egrid,
            center_x=args.center_x,
            center_y=args.center_y,
            radius=args.radius,
            resolution=args.resolution,
            densify=args.densify,
            attach_to_solid=args.attach_to_solid,
            include_terrain=not args.no_terrain,
            include_site_solid=not args.no_site,
            include_buildings=args.include_buildings,
            building_buffer_m=args.building_buffer,
            output_path=args.output,
        )

        print("\n✅ Workflow completed successfully!")
        sys.exit(0)

    except Exception as exc:
        logger.error(f"Workflow failed: {exc}", exc_info=True)
        print(f"\n❌ Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    main()
