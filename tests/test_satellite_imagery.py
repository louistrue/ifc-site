#!/usr/bin/env python3
"""
Test script to generate IFC file with satellite imagery overlay

Tests the new satellite imagery loader and texture mapping functionality.
"""

import logging
import sys
from src.site_model import run_combined_terrain_workflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """Generate test IFC with satellite imagery overlay"""
    
    # Use a well-known location (Paradeplatz, Zurich)
    address = "Paradeplatz, 8001 Zürich"
    
    print("=" * 80)
    print("Testing Satellite Imagery Overlay")
    print("=" * 80)
    print(f"Location: {address}")
    print("Radius: 500m")
    print("Imagery Resolution: 0.5m/pixel")
    print("Embedded: True")
    print()
    
    try:
        result = run_combined_terrain_workflow(
            address=address,
            radius=500.0,
            resolution=10.0,
            include_terrain=True,
            include_site_solid=True,
            include_roads=True,
            include_forest=False,  # Skip forest for faster generation
            include_water=True,
            include_buildings=False,  # Skip buildings for faster generation
            include_railways=False,
            include_bridges=False,
            include_satellite_overlay=True,  # Enable satellite imagery
            embed_imagery=True,  # Embed imagery in IFC
            imagery_resolution=0.5,  # 0.5m per pixel
            imagery_year=None,  # Use current imagery
            output_path="test_satellite_imagery.ifc",
            return_model=False
        )
        
        print("\n" + "=" * 80)
        print("SUCCESS: Test IFC file with satellite imagery created!")
        print("=" * 80)
        print("Output file: test_satellite_imagery.ifc")
        print(f"Offsets: x={result[0]:.2f}, y={result[1]:.2f}, z={result[2]:.2f}")
        print("\nNote: Open the IFC file in an IFC viewer")
        print("      to see the satellite imagery texture applied to the terrain.")
        
    except Exception:
        print("\n" + "=" * 80)
        print("ERROR: Failed to create test IFC with satellite imagery")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

