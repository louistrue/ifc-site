#!/usr/bin/env python3
"""
Small standalone test for building textures
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.site_model import run_combined_terrain_workflow

def main():
    """Generate a small test model with buildings and satellite imagery."""
    print("=" * 60)
    print("Building Texture Test (SMALL)")
    print("=" * 60)
    
    # Use 50m radius for quick testing with buildings
    result = run_combined_terrain_workflow(
        address="Paradeplatz, 8001 Zürich",
        radius=50.0,  # 50m radius - small area with a few buildings
        resolution=10.0,
        include_terrain=True,
        include_site_solid=False,  # Skip for faster test
        include_roads=False,  # Skip roads for faster test
        include_forest=False,
        include_water=False,
        include_buildings=True,  # Keep buildings - that's what we're testing!
        include_railways=False,
        include_bridges=False,
        include_satellite_overlay=True,
        embed_imagery=True,
        imagery_resolution=1.0,  # Lower resolution for faster download
        export_gltf=True,
        output_path="test_building_textures.ifc",
        return_model=False
    )
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
    print("Files created:")
    print("  - test_building_textures.ifc")
    print("  - test_building_textures.glb")
    print("  - test_building_textures_texture.jpg")
    print("\nRun: python3 tests/analyze_glb.py test_building_textures.glb")
    print("to check if buildings have UV coordinates")

if __name__ == "__main__":
    main()

