#!/usr/bin/env python3
"""
End-to-end test for building extraction from 3D Tiles.
Tests the complete flow: download -> parse -> transform -> convert -> filter
"""

import sys
import requests
import json
from shapely.geometry import Point
from pyproj import Transformer

# Import functions from combined_terrain.py
sys.path.insert(0, '.')
from combined_terrain import (
    parse_b3dm_header,
    download_and_parse_b3dm,
    transform_tile_to_lv95,
    meshes_to_geojson
)

# Test parameters
CENTER_X = 2687201.7  # EPSG:2056
CENTER_Y = 1246498.2  # EPSG:2056
RADIUS = 200  # meters
TILE_URL = "https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1/20251121/11/1891/425.b3dm"

def test_e2e():
    print("="*70)
    print("END-TO-END BUILDING EXTRACTION TEST")
    print("="*70)
    print(f"\nTest area:")
    print(f"  Center: E={CENTER_X}, N={CENTER_Y} (EPSG:2056)")
    print(f"  Radius: {RADIUS}m")
    print(f"\nTile URL: {TILE_URL}")
    
    # Step 1: Download tile
    print("\n" + "-"*70)
    print("Step 1: Downloading b3dm tile...")
    print("-"*70)
    try:
        response = requests.get(TILE_URL, timeout=30)
        response.raise_for_status()
        b3dm_data = response.content
        print(f"✓ Downloaded {len(b3dm_data)} bytes")
    except Exception as e:
        print(f"✗ Download failed: {e}")
        return False
    
    # Step 2: Parse b3dm
    print("\n" + "-"*70)
    print("Step 2: Parsing b3dm header...")
    print("-"*70)
    header = parse_b3dm_header(b3dm_data)
    if not header:
        print("✗ Failed to parse b3dm header")
        return False
    print(f"✓ b3dm header parsed")
    print(f"  Version: {header['version']}")
    print(f"  GLB data: {len(header['glb_data'])} bytes")
    
    # Parse batch table for building IDs
    batch_table = {}
    if header['batch_table_json']:
        try:
            batch_table = json.loads(header['batch_table_json'].decode('utf-8'))
            print(f"  Batch table: {len(batch_table)} fields")
            if 'id' in batch_table:
                ids = batch_table['id']
                print(f"  Building IDs: {len(ids) if isinstance(ids, list) else 'N/A'}")
        except:
            pass
    
    # Step 3: Parse GLB and extract meshes
    print("\n" + "-"*70)
    print("Step 3: Parsing GLB and extracting meshes...")
    print("-"*70)
    result = download_and_parse_b3dm(TILE_URL)
    if isinstance(result, tuple) and len(result) == 3:
        meshes, feature_table, batch_table = result
    else:
        meshes, feature_table, batch_table = result, {}, {}
    
    if not meshes or len(meshes) == 0:
        print("✗ No meshes extracted")
        return False
    
    print(f"✓ Extracted {len(meshes)} meshes")
    for i, mesh in enumerate(meshes):
        vertices = mesh.get('vertices', [])
        faces = mesh.get('faces', [])
        print(f"  Mesh {i}: {len(vertices)} vertices, {len(faces)} faces")
        if vertices:
            # Show coordinate statistics
            x_coords = [v[0] for v in vertices]
            y_coords = [v[1] for v in vertices]
            z_coords = [v[2] for v in vertices]
            print(f"    X range: {min(x_coords):.2f} to {max(x_coords):.2f}")
            print(f"    Y range: {min(y_coords):.2f} to {max(y_coords):.2f}")
            print(f"    Z range: {min(z_coords):.2f} to {max(z_coords):.2f}")
            
            # Check if all zeros (indicates extraction issue)
            if all(v[0] == 0 and v[1] == 0 and v[2] == 0 for v in vertices[:10]):
                print(f"    ⚠️  WARNING: All vertices appear to be (0,0,0) - geometry extraction may have failed")
                print(f"    This suggests trimesh may not be handling Draco compression correctly")
                print(f"    or the geometry needs additional processing")
    
    # Step 4: Transform coordinates
    print("\n" + "-"*70)
    print("Step 4: Transforming coordinates to EPSG:2056...")
    print("-"*70)
    
    # Check vertex coordinate ranges to understand coordinate system
    print("  Analyzing vertex coordinates...")
    all_x = []
    all_y = []
    all_z = []
    for mesh in meshes:
        vertices = mesh.get('vertices', [])
        for v in vertices:
            all_x.append(v[0])
            all_y.append(v[1])
            all_z.append(v[2])
    
    if all_x:
        print(f"  X range: {min(all_x):.2f} to {max(all_x):.2f}")
        print(f"  Y range: {min(all_y):.2f} to {max(all_y):.2f}")
        print(f"  Z range: {min(all_z):.2f} to {max(all_z):.2f}")
        
        # If coordinates are small (likely local/tile coordinates), we need proper region
        # If coordinates are large (likely already in EPSG:2056), skip transformation
        max_coord = max(abs(max(all_x)), abs(min(all_x)), abs(max(all_y)), abs(min(all_y)))
        
        if max_coord < 1000:
            print("  Coordinates appear to be local/tile coordinates - transformation needed")
            # Get region from tileset (approximate for Bern area)
            # These are rough estimates - in real code, get from tileset node
            region = [
                0.12502599897126387,  # west (radians) - approximate
                0.8004814595621665,   # south
                0.1256440628407409,   # east
                0.8007521593644946,   # north
                0.0,                  # min_height
                1000.0                # max_height
            ]
            print(f"  Using region: {region[:4]}")
        else:
            print("  Coordinates appear to be in EPSG:2056 already - skipping transformation")
            region = None
    
    transformed_meshes = []
    for i, mesh in enumerate(meshes):
        vertices = mesh.get('vertices', [])
        if not vertices:
            continue
        
        print(f"  Processing mesh {i} ({len(vertices)} vertices)...")
        
        if region:
            transformed_vertices = transform_tile_to_lv95(vertices, None, region)
        else:
            # Already in correct CRS
            transformed_vertices = vertices
        
        if transformed_vertices and len(transformed_vertices) > 0:
            transformed_mesh = mesh.copy()
            transformed_mesh['vertices'] = transformed_vertices
            transformed_meshes.append(transformed_mesh)
            
            # Show coordinate stats
            tx_coords = [v[0] for v in transformed_vertices]
            ty_coords = [v[1] for v in transformed_vertices]
            print(f"    Transformed X range: {min(tx_coords):.2f} to {max(tx_coords):.2f}")
            print(f"    Transformed Y range: {min(ty_coords):.2f} to {max(ty_coords):.2f}")
            print(f"    Centroid: ({sum(tx_coords)/len(tx_coords):.2f}, {sum(ty_coords)/len(ty_coords):.2f})")
    
    if not transformed_meshes:
        print("✗ No meshes after transformation")
        return False
    
    print(f"✓ Processed {len(transformed_meshes)} meshes")
    
    # Step 5: Convert to GeoJSON buildings
    print("\n" + "-"*70)
    print("Step 5: Converting meshes to GeoJSON buildings...")
    print("-"*70)
    
    building_attrs = []
    if batch_table and isinstance(batch_table, dict):
        if 'id' in batch_table:
            ids = batch_table['id']
            if isinstance(ids, list):
                building_attrs = [{'egid': str(id)} for id in ids]
    
    buildings = meshes_to_geojson(transformed_meshes, building_attrs if building_attrs else None)
    
    if not buildings:
        print("✗ No buildings created from meshes")
        return False
    
    print(f"✓ Created {len(buildings)} buildings")
    for i, building in enumerate(buildings):
        geom = building.get('geometry')
        if geom:
            centroid = geom.centroid
            print(f"  Building {i}:")
            print(f"    Centroid: ({centroid.x:.2f}, {centroid.y:.2f})")
            print(f"    Geometry type: {geom.geom_type}")
            if hasattr(geom, 'area'):
                print(f"    Area: {geom.area:.2f} m²")
            attrs = building.get('attributes', {})
            if attrs:
                print(f"    Attributes: {attrs}")
    
    # Step 6: Filter by radius
    print("\n" + "-"*70)
    print("Step 6: Filtering buildings by radius...")
    print("-"*70)
    
    circle = Point(CENTER_X, CENTER_Y).buffer(RADIUS)
    print(f"Search circle: center=({CENTER_X}, {CENTER_Y}), radius={RADIUS}m")
    
    filtered_buildings = []
    for i, building in enumerate(buildings):
        geom = building.get('geometry')
        if geom:
            centroid = geom.centroid
            dist = Point(CENTER_X, CENTER_Y).distance(centroid)
            intersects = circle.intersects(geom)
            
            status = "✓ INCLUDED" if intersects else "✗ OUTSIDE"
            print(f"  Building {i}: distance={dist:.1f}m, {status}")
            
            if intersects:
                filtered_buildings.append(building)
    
    print(f"\n✓ Filtered to {len(filtered_buildings)} buildings within radius")
    
    # Final result
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    # Check if we have valid geometry
    has_valid_coords = False
    for building in buildings:
        geom = building.get('geometry')
        if geom:
            centroid = geom.centroid
            # Check if coordinates are reasonable (not all zeros)
            if abs(centroid.x) > 1 or abs(centroid.y) > 1:
                has_valid_coords = True
                break
    
    if not has_valid_coords:
        print("✗✗✗ TEST FAILED: Geometry extraction issue detected ✗✗✗")
        print("\nROOT CAUSE:")
        print("  trimesh is not correctly extracting vertex coordinates from Draco-compressed GLB files.")
        print("  All vertices are (0,0,0), indicating Draco decompression is not working.")
        print("\nSOLUTION NEEDED:")
        print("  1. Install a Draco decoder library (e.g., draco3d via npm/node.js)")
        print("  2. Or use a library that handles Draco automatically")
        print("  3. Or implement manual Draco decompression")
        print("\nWORKAROUND:")
        print("  The pipeline works end-to-end, but needs proper Draco support.")
        print("  Current status: Meshes parsed ✓, but coordinates are invalid ✗")
        return False
    elif len(filtered_buildings) > 0:
        print("✓✓✓ TEST PASSED: Buildings successfully extracted! ✓✓✓")
        print(f"   Found {len(filtered_buildings)} buildings within {RADIUS}m radius")
        return True
    else:
        print("⚠️  TEST PARTIAL: Buildings extracted but none within radius")
        print(f"   Extracted {len(buildings)} buildings total")
        print(f"   Building centroids are outside the search radius")
        print(f"   This may indicate coordinate transformation issues")
        return False

if __name__ == "__main__":
    success = test_e2e()
    sys.exit(0 if success else 1)

