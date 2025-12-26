#!/usr/bin/env python3
"""
CLI for Site Boundaries Geometry Tool

Command-line interface for generating IFC site models with terrain, site solid, roads, trees, water, and buildings.
"""

import argparse
import sys
import os
import requests

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.site_model import run_combined_terrain_workflow


def main():
    parser = argparse.ArgumentParser(
        description="Generate IFC site model with terrain, site solid, roads, trees, water, and buildings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic site model (terrain + site solid)
  %(prog)s --egrid CH999979659148 --output site.ifc
  
  # Full model with all features
  %(prog)s --egrid CH999979659148 --include-roads --include-forest --include-water --include-buildings --output full.ifc
  
  # Custom terrain area
  %(prog)s --egrid CH999979659148 --radius 1000 --resolution 5 --output detailed.ifc
  
  # Site solid only (no terrain)
  %(prog)s --egrid CH999979659148 --no-terrain --output site_only.ifc
  
  # Terrain only (no site solid)
  %(prog)s --egrid CH999979659148 --no-site-solid --output terrain_only.ifc
        """
    )
    
    # Required arguments
    parser.add_argument("--egrid", required=True,
                        help="Swiss EGRID number (required)")
    
    # Optional location arguments
    parser.add_argument("--center-x", type=float,
                        help="Center easting (EPSG:2056). Default: site centroid")
    parser.add_argument("--center-y", type=float,
                        help="Center northing (EPSG:2056). Default: site centroid")
    
    # Terrain configuration
    terrain_group = parser.add_argument_group("Terrain Options")
    terrain_group.add_argument("--include-terrain", action="store_true", default=True,
                               help="Include surrounding terrain mesh (default: True)")
    terrain_group.add_argument("--no-terrain", dest="include_terrain", action="store_false",
                               help="Exclude surrounding terrain mesh")
    terrain_group.add_argument("--radius", type=float, default=500.0,
                               help="Radius of circular terrain area (meters), default: 500")
    terrain_group.add_argument("--resolution", type=float, default=10.0,
                               help="Grid resolution (meters), default: 10")
    terrain_group.add_argument("--attach-to-solid", action="store_true",
                               help="Attach terrain to smoothed site solid edges (less bumpy)")
    
    # Site solid configuration
    site_group = parser.add_argument_group("Site Solid Options")
    site_group.add_argument("--include-site-solid", action="store_true", default=True,
                            help="Include site solid (default: True)")
    site_group.add_argument("--no-site-solid", dest="include_site_solid", action="store_false",
                            help="Exclude site solid")
    site_group.add_argument("--densify", type=float, default=2.0,
                            help="Site boundary densification interval (meters), default: 2.0")
    
    # Road configuration
    road_group = parser.add_argument_group("Road Options")
    road_group.add_argument("--include-roads", action="store_true",
                            help="Include roads")
    road_group.add_argument("--road-buffer", type=float, default=100.0,
                            help="Buffer distance for road search (meters), default: 100")
    road_group.add_argument("--road-recess", type=float, default=0.15,
                            help="Depth to recess roads into terrain (meters), default: 0.15")
    road_group.add_argument("--roads-as-separate-elements", action="store_true",
                            help="Add roads as separate IFC elements (don't embed in terrain)")
    
    # Forest configuration
    forest_group = parser.add_argument_group("Forest Options")
    forest_group.add_argument("--include-forest", action="store_true",
                              help="Include forest trees and hedges")
    forest_group.add_argument("--forest-spacing", type=float, default=20.0,
                              help="Spacing between forest sample points (meters), default: 20")
    forest_group.add_argument("--forest-threshold", type=float, default=30.0,
                              help="Minimum forest coverage to place tree (0-100), default: 30")
    
    # Water configuration
    water_group = parser.add_argument_group("Water Options")
    water_group.add_argument("--include-water", action="store_true",
                             help="Include water features (creeks, rivers, lakes)")
    
    # Building configuration
    building_group = parser.add_argument_group("Building Options")
    building_group.add_argument("--include-buildings", action="store_true",
                                help="Include buildings from CityGML")
    
    # Output
    parser.add_argument("--output", default="combined_terrain.ifc",
                        help="Output IFC file path")
    
    args = parser.parse_args()
    
    try:
        run_combined_terrain_workflow(
            egrid=args.egrid,
            center_x=args.center_x,
            center_y=args.center_y,
            radius=args.radius,
            resolution=args.resolution,
            densify=args.densify,
            attach_to_solid=args.attach_to_solid,
            include_terrain=args.include_terrain,
            include_site_solid=args.include_site_solid,
            include_roads=args.include_roads,
            include_forest=args.include_forest,
            include_water=args.include_water,
            include_buildings=args.include_buildings,
            road_buffer_m=args.road_buffer,
            road_recess_depth=args.road_recess,
            forest_spacing=args.forest_spacing,
            forest_threshold=args.forest_threshold,
            embed_roads_in_terrain=not args.roads_as_separate_elements,
            output_path=args.output,
        )
    except requests.Timeout as exc:
        print(f"Upstream request timed out: {exc}")
        sys.exit(1)
    except requests.HTTPError as exc:
        print(f"Upstream request failed: {exc}")
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
