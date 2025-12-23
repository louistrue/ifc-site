#!/usr/bin/env python3
"""
Detailed test for vertex transformation using RTC_CENTER.
Extracts actual vertices from tiles and shows their transformation.
"""

import requests
import json
import struct
from pyproj import Transformer
import math

def parse_b3dm_header(b3dm_data):
    """Parse b3dm header."""
    if len(b3dm_data) < 28:
        return None
    
    magic = b3dm_data[0:4]
    if magic != b'b3dm':
        return None
    
    feature_table_json_length = struct.unpack('<I', b3dm_data[12:16])[0]
    feature_table_bin_length = struct.unpack('<I', b3dm_data[16:20])[0]
    batch_table_json_length = struct.unpack('<I', b3dm_data[20:24])[0]
    batch_table_bin_length = struct.unpack('<I', b3dm_data[24:28])[0]
    
    offset = 28
    feature_table_json = b3dm_data[offset:offset + feature_table_json_length] if feature_table_json_length > 0 else None
    offset += feature_table_json_length + feature_table_bin_length
    batch_table_json = b3dm_data[offset:offset + batch_table_json_length] if batch_table_json_length > 0 else None
    offset += batch_table_json_length + batch_table_bin_length
    glb_data = b3dm_data[offset:]
    
    return {
        'feature_table_json': feature_table_json,
        'batch_table_json': batch_table_json,
        'glb_data': glb_data
    }

def extract_sample_vertices(glb_data, max_vertices=10):
    """Extract a few sample vertices from GLB."""
    try:
        import pygltflib
        gltf = pygltflib.GLTF2().load_from_bytes(glb_data)
        
        vertices = []
        for scene in gltf.scenes or []:
            for node_idx in (scene.nodes or []):
                node = gltf.nodes[node_idx]
                if node.mesh is not None:
                    mesh = gltf.meshes[node.mesh]
                    for primitive in mesh.primitives:
                        if hasattr(primitive.attributes, 'POSITION'):
                            pos_idx = primitive.attributes.POSITION
                            if pos_idx < len(gltf.accessors):
                                accessor = gltf.accessors[pos_idx]
                                if accessor.bufferView is not None:
                                    buffer_view = gltf.bufferViews[accessor.bufferView]
                                    buffer_data = gltf.buffers[buffer_view.buffer].uri
                                    
                                    # Read binary data
                                    byte_offset = (buffer_view.byteOffset or 0) + (accessor.byteOffset or 0)
                                    byte_stride = buffer_view.byteStride or 12
                                    count = min(accessor.count, max_vertices)
                                    
                                    for i in range(count):
                                        offset = byte_offset + i * byte_stride
                                        if offset + 12 <= len(glb_data):
                                            x, y, z = struct.unpack('<fff', glb_data[offset:offset+12])
                                            vertices.append([x, y, z])
                                    break
                        if vertices:
                            break
                    if vertices:
                        break
                if vertices:
                    break
        return vertices
    except Exception as e:
        print(f"  Error extracting vertices: {e}")
        return []

def transform_rtc_to_lv95(rtc_center):
    """Transform RTC_CENTER from ECEF to LV95."""
    ecef_x, ecef_y, ecef_z = rtc_center
    transformer_ecef = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
    lon, lat, alt = transformer_ecef.transform(ecef_x, ecef_y, ecef_z)
    transformer_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
    x_lv95, y_lv95 = transformer_lv95.transform(lon, lat)
    return x_lv95, y_lv95

def transform_vertices(vertices, rtc_center_lv95):
    """Transform vertices from local to LV95."""
    transformed = []
    for v in vertices:
        world_x = rtc_center_lv95[0] + v[0]
        world_y = rtc_center_lv95[1] + v[1]
        world_z = v[2]  # Keep Z as-is
        transformed.append([world_x, world_y, world_z])
    return transformed

def test_tile_vertices(tile_url, tile_name):
    """Test vertex transformation for a tile."""
    print(f"\n{'='*80}")
    print(f"Testing tile: {tile_name}")
    print(f"{'='*80}")
    
    try:
        response = requests.get(tile_url, timeout=60)
        response.raise_for_status()
        b3dm_data = response.content
        
        header = parse_b3dm_header(b3dm_data)
        if not header:
            print("ERROR: Failed to parse header")
            return
        
        # Parse feature table
        feature_table = {}
        if header['feature_table_json']:
            feature_table = json.loads(header['feature_table_json'].decode('utf-8'))
        
        rtc_center_ecef = feature_table.get('RTC_CENTER')
        if not rtc_center_ecef:
            print("ERROR: No RTC_CENTER found")
            return
        
        print(f"\nRTC_CENTER (ECEF): [{rtc_center_ecef[0]:.2f}, {rtc_center_ecef[1]:.2f}, {rtc_center_ecef[2]:.2f}]")
        
        # Transform RTC_CENTER to LV95
        rtc_x_lv95, rtc_y_lv95 = transform_rtc_to_lv95(rtc_center_ecef)
        print(f"RTC_CENTER → LV95: x={rtc_x_lv95:.2f}, y={rtc_y_lv95:.2f}")
        
        # Extract sample vertices
        print(f"\nExtracting sample vertices from GLB...")
        vertices = extract_sample_vertices(header['glb_data'], max_vertices=5)
        
        if not vertices:
            print("  No vertices extracted (may need DracoPy for compressed meshes)")
            return
        
        print(f"\nSample local vertices (relative to RTC_CENTER):")
        for i, v in enumerate(vertices):
            print(f"  Vertex {i}: [{v[0]:.2f}, {v[1]:.2f}, {v[2]:.2f}]")
        
        # Transform vertices
        rtc_lv95 = (rtc_x_lv95, rtc_y_lv95)
        transformed_vertices = transform_vertices(vertices, rtc_lv95)
        
        print(f"\nTransformed vertices (LV95):")
        for i, v in enumerate(transformed_vertices):
            print(f"  Vertex {i}: [{v[0]:.2f}, {v[1]:.2f}, {v[2]:.2f}]")
        
        # Calculate bounds
        if transformed_vertices:
            x_coords = [v[0] for v in transformed_vertices]
            y_coords = [v[1] for v in transformed_vertices]
            print(f"\nTransformed bounds:")
            print(f"  X: [{min(x_coords):.2f}, {max(x_coords):.2f}]")
            print(f"  Y: [{min(y_coords):.2f}, {max(y_coords):.2f}]")
            
            # Compare with site center
            site_center_x = 2687201.7
            site_center_y = 1246498.2
            print(f"\nSite center: x={site_center_x:.2f}, y={site_center_y:.2f}")
            print(f"Distance from site center:")
            for i, v in enumerate(transformed_vertices):
                dist = ((v[0] - site_center_x)**2 + (v[1] - site_center_y)**2)**0.5
                print(f"  Vertex {i}: {dist:.2f} m")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Test vertex transformation."""
    base_url = "https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1/20251121"
    
    # Test a couple of tiles
    test_tiles = [
        ('11/1189/1594.b3dm', f'{base_url}/11/1189/1594.b3dm'),
        ('11/1190/1594.b3dm', f'{base_url}/11/1190/1594.b3dm'),
    ]
    
    print(f"\n{'#'*80}")
    print(f"Vertex Transformation Test")
    print(f"Testing how vertices are transformed using RTC_CENTER")
    print(f"{'#'*80}")
    
    for tile_name, tile_url in test_tiles:
        test_tile_vertices(tile_url, tile_name)
    
    print(f"\n{'#'*80}")
    print("Analysis:")
    print("Check if transformed vertices are in the correct location.")
    print("If vertices from different tiles are misaligned, the issue is")
    print("likely in how we're applying the RTC_CENTER transformation.")
    print(f"{'#'*80}\n")

if __name__ == '__main__':
    main()

