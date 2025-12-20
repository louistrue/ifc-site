#!/usr/bin/env python3
"""
Standalone end-to-end test for building extraction and IFC generation.
Tests: download -> parse -> transform -> convert -> filter -> IFC creation
"""

import sys
import requests
import json
import struct
from shapely.geometry import Point
from pyproj import Transformer

# Import from combined_terrain.py
sys.path.insert(0, '.')
from combined_terrain import (
    parse_b3dm_header,
    download_and_parse_b3dm,
    transform_tile_to_lv95,
    meshes_to_geojson,
    fetch_buildings_from_3d_tiles
)

# Test parameters
CENTER_X = 2687201.7  # EPSG:2056
CENTER_Y = 1246498.2  # EPSG:2056
RADIUS = 500  # meters - larger to catch more buildings

def test_full_pipeline():
    print("="*70)
    print("FULL PIPELINE TEST: Buildings to IFC")
    print("="*70)
    print(f"\nTest area:")
    print(f"  Center: E={CENTER_X}, N={CENTER_Y} (EPSG:2056)")
    print(f"  Radius: {RADIUS}m")
    
    # Step 1: Fetch buildings using the full function
    print("\n" + "-"*70)
    print("Step 1: Fetching buildings from 3D Tiles...")
    print("-"*70)
    
    buildings = fetch_buildings_from_3d_tiles(CENTER_X, CENTER_Y, RADIUS, max_buildings=50)
    
    print(f"\n✓ Fetched {len(buildings)} buildings")
    
    if len(buildings) == 0:
        print("\n✗✗✗ FAILED: No buildings extracted!")
        print("\nDebugging...")
        
        # Try downloading a single tile manually
        print("\nTrying single tile download...")
        tile_url = "https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1/20251121/11/1891/425.b3dm"
        
        result = download_and_parse_b3dm(tile_url)
        if isinstance(result, tuple) and len(result) == 3:
            meshes, feature_table, batch_table = result
        else:
            meshes, feature_table, batch_table = result, {}, {}
        
        print(f"  Meshes from single tile: {len(meshes)}")
        for i, mesh in enumerate(meshes):
            v = mesh.get('vertices', [])
            if v:
                print(f"    Mesh {i}: {len(v)} vertices")
                x_coords = [vert[0] for vert in v]
                print(f"      X range: {min(x_coords):.2f} to {max(x_coords):.2f}")
        
        return False
    
    # Step 2: Check building coordinates
    print("\n" + "-"*70)
    print("Step 2: Checking building coordinates...")
    print("-"*70)
    
    for i, building in enumerate(buildings[:5]):  # Check first 5
        geom = building.get('geometry')
        if geom:
            centroid = geom.centroid
            dist = Point(CENTER_X, CENTER_Y).distance(centroid)
            print(f"  Building {i}:")
            print(f"    Centroid: ({centroid.x:.2f}, {centroid.y:.2f})")
            print(f"    Distance from center: {dist:.1f}m")
            print(f"    Within radius: {'✓' if dist <= RADIUS else '✗'}")
    
    # Step 3: Test IFC creation
    print("\n" + "-"*70)
    print("Step 3: Testing IFC creation...")
    print("-"*70)
    
    try:
        import ifcopenshell
        import ifcopenshell.api
        
        # Create a simple IFC file
        model = ifcopenshell.api.run("project.create_file")
        project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Test Project")
        
        # Create site
        site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Test Site")
        ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, product=site)
        
        # Create buildings
        building_count = 0
        for building in buildings:
            geom = building.get('geometry')
            if not geom:
                continue
            
            # Create building element
            building_elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name=f"Building_{building_count}")
            ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, product=building_elem)
            building_count += 1
            
            if building_count >= 10:  # Limit for test
                break
        
        # Save IFC
        output_file = "test_buildings_output.ifc"
        model.write(output_file)
        
        print(f"✓ Created IFC file: {output_file}")
        print(f"  Buildings in IFC: {building_count}")
        
        # Check file size
        import os
        file_size = os.path.getsize(output_file)
        print(f"  File size: {file_size} bytes")
        
        if building_count > 0:
            print("\n✓✓✓ SUCCESS: Buildings are in IFC file!")
            return True
        else:
            print("\n✗ FAILED: No buildings added to IFC")
            return False
            
    except Exception as e:
        print(f"✗ Error creating IFC: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_full_pipeline()
    sys.exit(0 if success else 1)

