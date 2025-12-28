#!/usr/bin/env python3
"""
Verify the difference between buildings with and without textures
"""

import sys
import os

try:
    import trimesh
except ImportError:
    print("Error: trimesh not available")
    sys.exit(1)

def analyze_glb(filename):
    """Analyze a GLB file and report building texture status"""
    if not os.path.exists(filename):
        print(f"File not found: {filename}")
        return None
    
    try:
        scene = trimesh.load(filename)
        
        buildings_with_uv = 0
        buildings_without_uv = 0
        buildings_with_color = 0
        
        # Terrain is typically the first geometry (geometry_0) and has UV
        # Buildings are subsequent geometries
        terrain_vertex_count = None
        if 'geometry_0' in scene.geometry:
            terrain_vertex_count = len(scene.geometry['geometry_0'].vertices)
        
        for name, geom in scene.geometry.items():
            # Skip terrain (first geometry, usually has UV and many vertices)
            # Skip very small geometries (< 20 vertices) - likely not buildings
            if name == 'geometry_0' or len(geom.vertices) < 20:
                continue
            
            # Skip if this matches terrain vertex count (might be duplicate terrain)
            if terrain_vertex_count and len(geom.vertices) == terrain_vertex_count:
                continue
            
            # This should be a building
            has_uv = hasattr(geom.visual, 'uv') and geom.visual.uv is not None and len(geom.visual.uv) > 0
            has_color = hasattr(geom.visual, 'face_colors') and geom.visual.face_colors is not None
            
            if has_uv:
                buildings_with_uv += 1
            else:
                buildings_without_uv += 1
            
            if has_color:
                buildings_with_color += 1
        
        return {
            'with_uv': buildings_with_uv,
            'without_uv': buildings_without_uv,
            'with_color': buildings_with_color,
            'total': buildings_with_uv + buildings_without_uv
        }
    except Exception as e:
        print(f"Error analyzing {filename}: {e}")
        return None

def main():
    print("=" * 60)
    print("Verifying Building Texture Options")
    print("=" * 60)
    
    files = [
        ("test_buildings_with_textures.glb", "WITH textures"),
        ("test_buildings_no_textures.glb", "WITHOUT textures"),
        ("test_with_textures.glb", "WITH textures (CLI)"),
    ]
    
    for filename, description in files:
        print(f"\n{description}: {filename}")
        print("-" * 60)
        result = analyze_glb(filename)
        if result:
            print(f"  Total buildings: {result['total']}")
            print(f"  Buildings with UV/textures: {result['with_uv']}")
            print(f"  Buildings without UV (default color): {result['without_uv']}")
            print(f"  Buildings with face colors: {result['with_color']}")
            
            if "WITH textures" in description:
                if result['with_uv'] > 0:
                    print("  ✓ Correct: Buildings have UV coordinates")
                else:
                    print("  ✗ Issue: No buildings have UV coordinates")
            elif "WITHOUT textures" in description:
                if result['without_uv'] == result['total'] and result['total'] > 0:
                    print("  ✓ Correct: Buildings have no UV (using default color)")
                else:
                    print("  ✗ Issue: Some buildings have UV when they shouldn't")
        else:
            print("  File not found or error analyzing")

if __name__ == "__main__":
    main()

