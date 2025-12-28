#!/usr/bin/env python3
"""
Showcase script: Generate site models for Zurich and Geneva with satellite imagery
"""

import sys
import os
import time

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.site_model import run_combined_terrain_workflow

def showcase_city(name, address, output_prefix):
    """Generate showcase model for a city."""
    print("\n" + "=" * 80)
    print(f"  {name} Showcase")
    print("=" * 80)
    print(f"Location: {address}")
    print(f"Radius: 500m")
    print(f"Resolution: 10m")
    print(f"Imagery Resolution: 0.5m/pixel")
    print(f"Features: ALL (terrain, roads, water, buildings, railways, satellite imagery)")
    print()
    
    start_time = time.time()
    
    try:
        result = run_combined_terrain_workflow(
            address=address,
            radius=500.0,
            resolution=10.0,
            include_terrain=True,
            include_site_solid=True,
            include_roads=True,
            include_forest=False,  # Skip for faster generation
            include_water=True,
            include_buildings=True,
            include_railways=True,
            include_bridges=False,
            include_satellite_overlay=True,  # Enable satellite imagery
            embed_imagery=True,
            imagery_resolution=0.5,
            export_gltf=True,  # Enable glTF export
            output_path=f"{output_prefix}.ifc",
            return_model=False
        )
        
        elapsed = time.time() - start_time
        
        print("\n" + "=" * 80)
        print(f"SUCCESS: {name} showcase created!")
        print("=" * 80)
        print(f"Time: {elapsed:.1f} seconds")
        print(f"Output files:")
        print(f"  - {output_prefix}.ifc")
        print(f"  - {output_prefix}.glb")
        print(f"  - {output_prefix}_texture.jpg")
        print(f"Offsets: x={result[0]:.2f}, y={result[1]:.2f}, z={result[2]:.2f}")
        print()
        
        return True
        
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"ERROR: Failed to create {name} showcase")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run showcase for Zurich and Geneva."""
    print("\n" + "=" * 80)
    print("  Swiss Site Model Showcase")
    print("  Generating models for Zurich and Geneva with satellite imagery")
    print("=" * 80)
    
    showcase_results = []
    
    # Zurich showcase
    showcase_results.append(
        showcase_city(
            "Zurich",
            "Paradeplatz, 8001 Zürich",
            "showcase_zurich"
        )
    )
    
    # Geneva showcase
    showcase_results.append(
        showcase_city(
            "Geneva",
            "Place du Molard, 1204 Genève",
            "showcase_geneva"
        )
    )
    
    # Summary
    print("\n" + "=" * 80)
    print("  Showcase Summary")
    print("=" * 80)
    print(f"Zurich: {'✓ Success' if showcase_results[0] else '✗ Failed'}")
    print(f"Geneva: {'✓ Success' if showcase_results[1] else '✗ Failed'}")
    print()
    
    if all(showcase_results):
        print("All showcases completed successfully!")
        print("\nOpen the GLB files in a Three.js viewer or Blender to see")
        print("the satellite imagery textures applied to terrain and buildings.")
    else:
        print("Some showcases failed. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

