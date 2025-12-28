#!/usr/bin/env python3
"""
Analyze GLB files to check geometry and textures
"""

import sys
import os

try:
    import trimesh
except ImportError:
    print("Error: trimesh not installed. Install with: pip install trimesh")
    sys.exit(1)

def analyze_glb(filepath):
    """Analyze a GLB file and report findings."""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False
    
    print(f"\n{'='*60}")
    print(f"Analyzing: {os.path.basename(filepath)}")
    print(f"{'='*60}")
    
    try:
        scene = trimesh.load(filepath)
        
        print(f"\nScene Statistics:")
        print(f"  Number of geometries: {len(scene.geometry)}")
        
        total_vertices = 0
        total_faces = 0
        meshes_with_uv = 0
        meshes_with_texture = 0
        meshes_without_texture = 0
        
        building_meshes = []
        terrain_meshes = []
        road_meshes = []
        other_meshes = []
        
        for name, geom in scene.geometry.items():
            total_vertices += len(geom.vertices)
            total_faces += len(geom.faces)
            
            has_uv = hasattr(geom.visual, 'uv') and geom.visual.uv is not None and len(geom.visual.uv) > 0
            has_texture = hasattr(geom.visual, 'material') and geom.visual.material is not None
            
            if has_uv:
                meshes_with_uv += 1
            if has_texture:
                meshes_with_texture += 1
                if hasattr(geom.visual.material, 'baseColorTexture'):
                    print(f"  Mesh '{name}': Has texture material with baseColorTexture")
            else:
                meshes_without_texture += 1
            
            # Categorize meshes by vertex count (rough heuristic)
            vcount = len(geom.vertices)
            if vcount > 1000:
                building_meshes.append((name, vcount, has_uv, has_texture))
            elif vcount > 100:
                road_meshes.append((name, vcount, has_uv, has_texture))
            elif vcount > 10:
                terrain_meshes.append((name, vcount, has_uv, has_texture))
            else:
                other_meshes.append((name, vcount, has_uv, has_texture))
        
        print(f"\nTotal Statistics:")
        print(f"  Total vertices: {total_vertices:,}")
        print(f"  Total faces: {total_faces:,}")
        print(f"  Meshes with UV coordinates: {meshes_with_uv}")
        print(f"  Meshes with texture material: {meshes_with_texture}")
        print(f"  Meshes without texture: {meshes_without_texture}")
        
        print(f"\nMesh Categories:")
        print(f"  Building-like meshes (>1000 vertices): {len(building_meshes)}")
        print(f"  Road-like meshes (100-1000 vertices): {len(road_meshes)}")
        print(f"  Terrain-like meshes (10-100 vertices): {len(terrain_meshes)}")
        print(f"  Other meshes (<10 vertices): {len(other_meshes)}")
        
        # Check building meshes
        if building_meshes:
            print(f"\nBuilding Mesh Analysis:")
            buildings_with_uv = sum(1 for _, _, uv, _ in building_meshes if uv)
            buildings_with_texture = sum(1 for _, _, _, tex in building_meshes if tex)
            print(f"  Buildings with UV: {buildings_with_uv}/{len(building_meshes)}")
            print(f"  Buildings with texture: {buildings_with_texture}/{len(building_meshes)}")
            
            # Sample a few building meshes
            print(f"\n  Sample buildings (first 5):")
            for name, vcount, has_uv, has_texture in building_meshes[:5]:
                print(f"    {name}: {vcount} vertices, UV={has_uv}, Texture={has_texture}")
        
        # Check terrain mesh
        if terrain_meshes:
            print(f"\nTerrain Mesh Analysis:")
            for name, vcount, has_uv, has_texture in terrain_meshes:
                print(f"  {name}: {vcount} vertices, UV={has_uv}, Texture={has_texture}")
        
        return True
        
    except Exception as e:
        print(f"Error analyzing file: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Analyze showcase GLB files."""
    files = [
        "showcase_zurich.glb",
        "showcase_geneva.glb"
    ]
    
    print("GLB File Analysis")
    print("="*60)
    
    for filepath in files:
        analyze_glb(filepath)
    
    print(f"\n{'='*60}")
    print("Analysis complete")


if __name__ == "__main__":
    main()

