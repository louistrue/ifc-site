#!/usr/bin/env python3
"""
Test script to compare building textures: enabled vs disabled
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.site_model import run_combined_terrain_workflow

def main():
    print("=" * 60)
    print("Testing Building Texture Options")
    print("=" * 60)
    
    address = "Paradeplatz, 8001 Zürich"
    radius = 50.0  # Small area for quick testing
    
    # Test 1: With building textures (satellite imagery)
    print("\n" + "=" * 60)
    print("Test 1: Buildings WITH satellite textures")
    print("=" * 60)
    result1 = run_combined_terrain_workflow(
        address=address,
        radius=radius,
        resolution=10.0,
        include_terrain=True,
        include_site_solid=False,
        include_roads=False,
        include_forest=False,
        include_water=False,
        include_buildings=True,
        include_railways=False,
        include_bridges=False,
        include_satellite_overlay=True,
        embed_imagery=True,
        imagery_resolution=1.0,
        apply_texture_to_buildings=True,  # Explicitly enable
        export_gltf=True,
        output_path="test_buildings_with_textures.ifc",
        return_model=False
    )
    
    # Test 2: Without building textures (default color)
    print("\n" + "=" * 60)
    print("Test 2: Buildings WITHOUT satellite textures (default color)")
    print("=" * 60)
    result2 = run_combined_terrain_workflow(
        address=address,
        radius=radius,
        resolution=10.0,
        include_terrain=True,
        include_site_solid=False,
        include_roads=False,
        include_forest=False,
        include_water=False,
        include_buildings=True,
        include_railways=False,
        include_bridges=False,
        include_satellite_overlay=True,
        embed_imagery=True,
        imagery_resolution=1.0,
        apply_texture_to_buildings=False,  # Explicitly disable
        export_gltf=True,
        output_path="test_buildings_no_textures.ifc",
        return_model=False
    )
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)
    print("\nFiles created:")
    print("  - test_buildings_with_textures.ifc")
    print("  - test_buildings_with_textures.glb  (buildings have satellite textures)")
    print("  - test_buildings_no_textures.ifc")
    print("  - test_buildings_no_textures.glb  (buildings have default beige color)")
    print("\nCompare the GLB files to see the difference!")
    print("  Buildings are included in both, but colored differently.")

if __name__ == "__main__":
    main()

