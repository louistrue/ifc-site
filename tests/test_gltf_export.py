#!/usr/bin/env python3
"""
Test script to generate IFC file with satellite imagery and glTF export
"""

import logging
import sys
import os
from src.site_model import run_combined_terrain_workflow

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """Generate test IFC with satellite imagery overlay and glTF export"""
    
    address = "Paradeplatz, 8001 Zürich"
    
    print("=" * 80)
    print("Testing glTF Export with Satellite Imagery")
    print("=" * 80)
    print(f"Location: {address}")
    print("Radius: 500m")
    print("Imagery Resolution: 0.5m/pixel")
    print("glTF Export: Enabled")
    print()
    
    try:
        result = run_combined_terrain_workflow(
            address=address,
            radius=500.0,
            resolution=10.0,
            include_terrain=True,
            include_site_solid=True,
            include_roads=True,
            include_forest=False,
            include_water=True,
            include_buildings=True,   # Enable buildings
            include_railways=True,    # Enable railways
            include_bridges=False,
            include_satellite_overlay=True,  # Enable satellite imagery
            embed_imagery=True,              # Embed imagery in IFC
            imagery_resolution=0.5,          # 0.5m resolution
            export_gltf=True,                # Enable glTF export
            output_path="test_gltf_export.ifc",
            return_model=False
        )
        
        print("\n" + "=" * 80)
        print("SUCCESS: Test IFC file with glTF export created!")
        print("=" * 80)
        print("Output files:")
        print("  - test_gltf_export.ifc (IFC model)")
        print("  - test_gltf_export.glb (glTF binary with embedded texture)")
        print("  - test_gltf_export_texture.jpg (External texture file)")
        print(f"Offsets: x={result[0]:.2f}, y={result[1]:.2f}, z={result[2]:.2f}")
        print("\nNote: Open the GLB file in a Three.js viewer or Blender")
        print("      to see the satellite imagery texture applied to the terrain.")
        
    except Exception:
        print("\n" + "=" * 80)
        print("ERROR: Failed to create test IFC/glTF")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

