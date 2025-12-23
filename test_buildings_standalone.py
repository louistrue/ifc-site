#!/usr/bin/env python3
"""
Standalone test to verify building extraction works end-to-end.
Downloads tiles, extracts buildings, and creates IFC file.
"""

import sys
import requests
import json
from shapely.geometry import Point
import ifcopenshell
import ifcopenshell.api

sys.path.insert(0, '.')
from combined_terrain import (
    parse_b3dm_header,
    download_and_parse_b3dm,
    transform_tile_to_lv95,
    meshes_to_geojson,
    prepare_building_geometries
)

# Test parameters
CENTER_X = 2687201.7
CENTER_Y = 1246498.2
RADIUS = 2000  # 2km radius to catch more buildings

# Find a tile near center dynamically
def find_tile_near_center(center_x, center_y, radius_m=5000):
    """Find a tile near the center coordinates"""
    import math
    from pyproj import Transformer
    
    transformer = Transformer.from_crs('EPSG:2056', 'EPSG:4326', always_xy=True)
    center_lon, center_lat = transformer.transform(center_x, center_y)
    
    # Search region in radians (expanded search)
    west_rad = math.radians(center_lon - 0.05)  # ~5km
    east_rad = math.radians(center_lon + 0.05)
    south_rad = math.radians(center_lat - 0.05)
    north_rad = math.radians(center_lat + 0.05)
    
    base_url = 'https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1/20251121'
    
    for tileset_num in range(0, 20):
        try:
            url = f'{base_url}/tileset{tileset_num}.json'
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                continue
            tileset = response.json()
            
            def search_node(node, depth=0):
                if depth > 12:
                    return None
                if 'boundingVolume' in node:
                    bv = node['boundingVolume']
                    if 'region' in bv:
                        region = bv['region']
                        tile_west, tile_south, tile_east, tile_north = region[0], region[1], region[2], region[3]
                        
                        # Check overlap
                        if not (tile_east < west_rad or tile_west > east_rad or tile_north < south_rad or tile_south > north_rad):
                            if 'content' in node:
                                uri = node['content'].get('uri', '') if isinstance(node['content'], dict) else node['content']
                                if '.b3dm' in uri:
                                    # Check distance
                                    tile_center_lon = math.degrees((tile_west + tile_east) / 2)
                                    tile_center_lat = math.degrees((tile_south + tile_north) / 2)
                                    tile_x, tile_y = transformer.transform(tile_center_lon, tile_center_lat)
                                    dist = ((tile_x - center_x)**2 + (tile_y - center_y)**2)**0.5
                                    if dist < radius_m * 2:  # Within 2x radius
                                        return (f'{base_url}/{uri}', region, dist)
                
                if 'children' in node:
                    for child in node['children']:
                        result = search_node(child, depth+1)
                        if result:
                            return result
                return None
            
            result = search_node(tileset.get('root', {}))
            if result:
                return result
        except:
            continue
    
    return None

# Known tile for testing (far from center but works for transformation test)
TEST_TILES = [
    {
        'url': 'https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1/20251121/11/1891/425.b3dm',
        'region': [0.1357262297115847, 0.8068598236545228, 0.13576485870342703, 0.8068767423921683, 2546.987999999998, 2552.92299976619]
    }
]

def test_single_tile():
    print("="*70)
    print("STANDALONE BUILDING EXTRACTION TEST")
    print("="*70)
    
    # Try to find a tile near center first
    print("\nSearching for tile near center...")
    tile_result = find_tile_near_center(CENTER_X, CENTER_Y, RADIUS)
    
    if tile_result:
        tile_url, region, dist = tile_result
        print(f"Found tile at distance {dist:.1f}m from center")
    else:
        print("No tile found near center, using test tile (far from center)")
        tile_info = TEST_TILES[0]
        tile_url = tile_info['url']
        region = tile_info['region']
        dist = None
    
    print(f"\nTesting tile: {tile_url}")
    print(f"Region: {region[:4]}")
    
    # Download and parse
    print("\n1. Downloading and parsing tile...")
    result = download_and_parse_b3dm(tile_url)
    if isinstance(result, tuple) and len(result) == 3:
        meshes, feature_table, batch_table = result
    else:
        meshes, feature_table, batch_table = result, {}, {}
    
    print(f"   Extracted {len(meshes)} meshes")
    
    if not meshes:
        print("   ✗ No meshes extracted")
        return False
    
    # Transform coordinates
    print("\n2. Transforming coordinates...")
    transformed_meshes = []
    for i, mesh in enumerate(meshes):
        vertices = mesh.get('vertices', [])
        if not vertices:
            continue
        
        print(f"   Mesh {i}: {len(vertices)} vertices")
        x_coords = [v[0] for v in vertices]
        y_coords = [v[1] for v in vertices]
        print(f"     Local range: X=[{min(x_coords):.2f}, {max(x_coords):.2f}], Y=[{min(y_coords):.2f}, {max(y_coords):.2f}]")
        
        transformed_vertices = transform_tile_to_lv95(vertices, None, region)
        
        if transformed_vertices:
            tx_coords = [v[0] for v in transformed_vertices]
            ty_coords = [v[1] for v in transformed_vertices]
            print(f"     Transformed range: X=[{min(tx_coords):.2f}, {max(tx_coords):.2f}], Y=[{min(ty_coords):.2f}, {max(ty_coords):.2f}]")
            
            transformed_mesh = mesh.copy()
            transformed_mesh['vertices'] = transformed_vertices
            transformed_meshes.append(transformed_mesh)
    
    if not transformed_meshes:
        print("   ✗ No meshes after transformation")
        return False
    
    # Convert to buildings
    print("\n3. Converting to buildings...")
    buildings = meshes_to_geojson(transformed_meshes)
    print(f"   Created {len(buildings)} buildings")
    
    if not buildings:
        print("   ✗ No buildings created")
        return False
    
    # Check distances
    print("\n4. Checking building positions...")
    circle = Point(CENTER_X, CENTER_Y).buffer(RADIUS)
    print(f"   Search area: center=({CENTER_X}, {CENTER_Y}), radius={RADIUS}m")
    
    included = []
    for i, building in enumerate(buildings):
        geom = building.get('geometry')
        if geom:
            centroid = geom.centroid
            dist = Point(CENTER_X, CENTER_Y).distance(centroid)
            print(f"   Building {i}: centroid=({centroid.x:.2f}, {centroid.y:.2f}), distance={dist:.1f}m")
            
            if circle.intersects(geom):
                included.append(building)
                print(f"     ✓ INCLUDED")
            else:
                print(f"     ✗ OUTSIDE")
    
    print(f"\n   {len(included)} buildings within {RADIUS}m radius")
    
    # Create IFC
    if included:
        print("\n5. Creating IFC file...")
        try:
            model = ifcopenshell.api.run("project.create_file")
            project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Test Project")
            
            site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Test Site")
            ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
            
            # Prepare building geometries (simplified - just create building elements)
            building_count = 0
            for building in included:
                try:
                    building_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name=f"Building_{building_count}")
                    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building_elem])
                    building_count += 1
                except:
                    pass
            
            output_file = "test_buildings_standalone.ifc"
            model.write(output_file)
            
            import os
            file_size = os.path.getsize(output_file)
            print(f"   ✓ Created IFC: {output_file}")
            print(f"   Buildings in IFC: {building_count}")
            print(f"   File size: {file_size} bytes")
            
            if building_count > 0:
                print("\n" + "="*70)
                print("✓✓✓ SUCCESS: Buildings extracted and added to IFC!")
                print("="*70)
                return True
            else:
                print("\n✗ No buildings added to IFC")
                return False
                
        except Exception as e:
            print(f"   ✗ Error creating IFC: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print("\n⚠️  Buildings extracted but none within radius")
        print("   This indicates coordinate transformation may need adjustment")
        return False

if __name__ == "__main__":
    success = test_single_tile()
    sys.exit(0 if success else 1)

