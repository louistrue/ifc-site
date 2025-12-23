#!/usr/bin/env python3
"""
Test building placement by using actual transformation functions.
This will help identify if the issue is in the transformation logic.
"""

import sys
import os

# Import from the main script
sys.path.insert(0, os.path.dirname(__file__))
from combined_terrain import download_and_parse_b3dm, transform_tile_to_lv95

def test_building_transformation():
    """Test building transformation using actual code."""
    
    base_url = "https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1/20251121"
    
    # Site center from EGRID CH999979659148
    site_center_x = 2687201.7
    site_center_y = 1246498.2
    
    test_tiles = [
        {
            'name': '11/1189/1594.b3dm',
            'url': f'{base_url}/11/1189/1594.b3dm',
            'region': [0.14994169870955615, 0.8266378279621209, 0.14998032770139846, 0.8266547466997665]
        },
        {
            'name': '11/1190/1594.b3dm',
            'url': f'{base_url}/11/1190/1594.b3dm',
            'region': [0.14998032770139846, 0.8266378279621209, 0.15001895669324078, 0.8266547466997665]
        },
        {
            'name': '11/1189/1595.b3dm',
            'url': f'{base_url}/11/1189/1595.b3dm',
            'region': [0.14994169870955615, 0.8266547466997665, 0.14998032770139846, 0.8266716654374119]
        },
        {
            'name': '11/1190/1595.b3dm',
            'url': f'{base_url}/11/1190/1595.b3dm',
            'region': [0.14998032770139846, 0.8266547466997665, 0.15001895669324078, 0.8266716654374119]
        },
    ]
    
    print(f"\n{'#'*80}")
    print(f"Building Placement Test")
    print(f"Site center (LV95): x={site_center_x:.2f}, y={site_center_y:.2f}")
    print(f"{'#'*80}\n")
    
    all_building_centroids = []
    
    for tile_info in test_tiles:
        print(f"{'='*80}")
        print(f"Tile: {tile_info['name']}")
        print(f"{'='*80}")
        
        try:
            # Download and parse tile
            result = download_and_parse_b3dm(tile_info['url'])
            
            if isinstance(result, tuple) and len(result) == 3:
                meshes, feature_table, batch_table = result
            else:
                meshes, feature_table, batch_table = result, {}, {}
            
            if not meshes:
                print("  No meshes found")
                continue
            
            print(f"  Found {len(meshes)} meshes")
            
            # Extract RTC_CENTER
            rtc_center = None
            if feature_table and isinstance(feature_table, dict):
                rtc_center = feature_table.get('RTC_CENTER')
                if rtc_center:
                    print(f"  RTC_CENTER: [{rtc_center[0]:.2f}, {rtc_center[1]:.2f}, {rtc_center[2]:.2f}]")
            
            # Transform each mesh
            for mesh_idx, mesh in enumerate(meshes):
                vertices = mesh.get('vertices', [])
                if not vertices:
                    continue
                
                # Transform vertices
                transformed_vertices = transform_tile_to_lv95(
                    vertices, None, tile_info['region'], rtc_center=rtc_center
                )
                
                if not transformed_vertices:
                    continue
                
                # Calculate centroid of transformed vertices
                x_coords = [v[0] for v in transformed_vertices]
                y_coords = [v[1] for v in transformed_vertices]
                z_coords = [v[2] for v in transformed_vertices]
                
                centroid_x = sum(x_coords) / len(x_coords)
                centroid_y = sum(y_coords) / len(y_coords)
                centroid_z = sum(z_coords) / len(z_coords)
                
                # Calculate distance from site center
                dist = ((centroid_x - site_center_x)**2 + (centroid_y - site_center_y)**2)**0.5
                
                print(f"  Mesh {mesh_idx}:")
                print(f"    Vertices: {len(transformed_vertices)}")
                print(f"    Centroid (LV95): x={centroid_x:.2f}, y={centroid_y:.2f}, z={centroid_z:.2f}")
                print(f"    Distance from site center: {dist:.2f} m")
                print(f"    Bounds: X=[{min(x_coords):.2f}, {max(x_coords):.2f}], Y=[{min(y_coords):.2f}, {max(y_coords):.2f}]")
                
                all_building_centroids.append({
                    'tile': tile_info['name'],
                    'mesh': mesh_idx,
                    'centroid': (centroid_x, centroid_y, centroid_z),
                    'distance': dist
                })
        
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n{'#'*80}")
    print("Summary:")
    print(f"{'#'*80}")
    
    if all_building_centroids:
        print(f"\nTotal buildings processed: {len(all_building_centroids)}")
        print(f"\nBuilding centroids:")
        for b in all_building_centroids:
            print(f"  {b['tile']} mesh {b['mesh']}: ({b['centroid'][0]:.2f}, {b['centroid'][1]:.2f}) - {b['distance']:.2f}m from site")
        
        # Check if buildings are clustered correctly
        x_coords = [b['centroid'][0] for b in all_building_centroids]
        y_coords = [b['centroid'][1] for b in all_building_centroids]
        
        print(f"\nOverall bounds:")
        print(f"  X: [{min(x_coords):.2f}, {max(x_coords):.2f}] (span: {max(x_coords) - min(x_coords):.2f} m)")
        print(f"  Y: [{min(y_coords):.2f}, {max(y_coords):.2f}] (span: {max(y_coords) - min(y_coords):.2f} m)")
        
        # Check for misalignment
        print(f"\nAnalysis:")
        print(f"  Site center: ({site_center_x:.2f}, {site_center_y:.2f})")
        print(f"  Building cluster center: ({(min(x_coords) + max(x_coords))/2:.2f}, {(min(y_coords) + max(y_coords))/2:.2f})")
        
        cluster_center_x = (min(x_coords) + max(x_coords)) / 2
        cluster_center_y = (min(y_coords) + max(y_coords)) / 2
        cluster_offset_x = cluster_center_x - site_center_x
        cluster_offset_y = cluster_center_y - site_center_y
        cluster_offset_dist = (cluster_offset_x**2 + cluster_offset_y**2)**0.5
        
        print(f"  Cluster offset: ({cluster_offset_x:.2f}, {cluster_offset_y:.2f}) = {cluster_offset_dist:.2f} m")
        
        if cluster_offset_dist > 50:
            print(f"\n  ⚠️  WARNING: Large cluster offset detected!")
            print(f"     Buildings may be misaligned. Check RTC_CENTER transformation.")
        else:
            print(f"\n  ✓ Cluster appears to be correctly positioned.")
    
    print(f"{'#'*80}\n")

if __name__ == '__main__':
    test_building_transformation()

