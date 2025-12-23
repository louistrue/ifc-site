#!/usr/bin/env python3
"""
Standalone test for RTC_CENTER coordinate transformation.
Tests the transformation from ECEF to LV95 and verifies building placement.
"""

import requests
import json
import struct
from pyproj import Transformer
import math

def parse_b3dm_header(b3dm_data):
    """Parse b3dm header to extract feature table and GLB data."""
    if len(b3dm_data) < 28:
        return None
    
    # Read header
    magic = b3dm_data[0:4]
    if magic != b'b3dm':
        return None
    
    version = struct.unpack('<I', b3dm_data[4:8])[0]
    byte_length = struct.unpack('<I', b3dm_data[8:12])[0]
    feature_table_json_length = struct.unpack('<I', b3dm_data[12:16])[0]
    feature_table_bin_length = struct.unpack('<I', b3dm_data[16:20])[0]
    batch_table_json_length = struct.unpack('<I', b3dm_data[20:24])[0]
    batch_table_bin_length = struct.unpack('<I', b3dm_data[24:28])[0]
    
    offset = 28
    
    # Extract feature table JSON
    feature_table_json = None
    if feature_table_json_length > 0:
        feature_table_json = b3dm_data[offset:offset + feature_table_json_length]
        offset += feature_table_json_length
    
    # Skip feature table binary
    offset += feature_table_bin_length
    
    # Extract batch table JSON
    batch_table_json = None
    if batch_table_json_length > 0:
        batch_table_json = b3dm_data[offset:offset + batch_table_json_length]
        offset += batch_table_json_length
    
    # Skip batch table binary
    offset += batch_table_bin_length
    
    # Remaining is GLB data
    glb_data = b3dm_data[offset:]
    
    return {
        'version': version,
        'byte_length': byte_length,
        'feature_table_json': feature_table_json,
        'batch_table_json': batch_table_json,
        'glb_data': glb_data
    }

def transform_rtc_to_lv95(rtc_center):
    """Transform RTC_CENTER from ECEF to LV95."""
    ecef_x, ecef_y, ecef_z = rtc_center
    
    # ECEF to WGS84 geographic (EPSG:4978 -> EPSG:4326)
    transformer_ecef = Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
    lon, lat, alt = transformer_ecef.transform(ecef_x, ecef_y, ecef_z)
    
    # WGS84 to LV95 (EPSG:4326 -> EPSG:2056)
    transformer_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
    x_lv95, y_lv95 = transformer_lv95.transform(lon, lat)
    
    return x_lv95, y_lv95, lon, lat

def transform_region_to_lv95(region):
    """Transform region bounds to LV95 center."""
    west, south, east, north = region[0], region[1], region[2], region[3]
    
    west_deg = math.degrees(west)
    south_deg = math.degrees(south)
    east_deg = math.degrees(east)
    north_deg = math.degrees(north)
    
    center_lon = (west_deg + east_deg) / 2
    center_lat = (south_deg + north_deg) / 2
    
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
    center_x, center_y = transformer.transform(center_lon, center_lat)
    
    return center_x, center_y, center_lon, center_lat

def test_tile_transformation(tile_url, tile_name, region=None):
    """Test transformation for a single tile."""
    print(f"\n{'='*80}")
    print(f"Testing tile: {tile_name}")
    print(f"URL: {tile_url}")
    print(f"{'='*80}")
    
    try:
        response = requests.get(tile_url, timeout=60)
        response.raise_for_status()
        b3dm_data = response.content
        
        header = parse_b3dm_header(b3dm_data)
        if not header:
            print("ERROR: Failed to parse b3dm header")
            return
        
        # Parse feature table
        feature_table = {}
        if header['feature_table_json']:
            try:
                feature_table = json.loads(header['feature_table_json'].decode('utf-8'))
            except Exception as e:
                print(f"ERROR parsing feature table: {e}")
                return
        
        print(f"\nFeature table keys: {list(feature_table.keys())}")
        
        # Extract RTC_CENTER
        rtc_center = feature_table.get('RTC_CENTER')
        if rtc_center:
            print(f"\nRTC_CENTER (ECEF): [{rtc_center[0]:.2f}, {rtc_center[1]:.2f}, {rtc_center[2]:.2f}]")
            
            # Transform RTC_CENTER to LV95
            x_lv95, y_lv95, lon, lat = transform_rtc_to_lv95(rtc_center)
            print(f"RTC_CENTER → WGS84: lon={lon:.6f}, lat={lat:.6f}")
            print(f"RTC_CENTER → LV95:  x={x_lv95:.2f}, y={y_lv95:.2f}")
        else:
            print("\nWARNING: No RTC_CENTER found in feature table")
        
        # Transform region if available
        if region:
            print(f"\nRegion (radians): west={region[0]:.6f}, south={region[1]:.6f}, east={region[2]:.6f}, north={region[3]:.6f}")
            reg_x, reg_y, reg_lon, reg_lat = transform_region_to_lv95(region)
            print(f"Region center → WGS84: lon={reg_lon:.6f}, lat={reg_lat:.6f}")
            print(f"Region center → LV95:  x={reg_x:.2f}, y={reg_y:.2f}")
            
            if rtc_center:
                # Compare the two methods
                diff_x = abs(x_lv95 - reg_x)
                diff_y = abs(y_lv95 - reg_y)
                print(f"\nDifference (RTC vs Region):")
                print(f"  X difference: {diff_x:.2f} m")
                print(f"  Y difference: {diff_y:.2f} m")
                print(f"  Total distance: {(diff_x**2 + diff_y**2)**0.5:.2f} m")
        
        # Check BATCH_LENGTH
        batch_length = feature_table.get('BATCH_LENGTH', 0)
        print(f"\nBATCH_LENGTH: {batch_length}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Test multiple tiles to compare transformations."""
    
    # Test tiles from the actual run
    base_url = "https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1/20251121"
    
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
    
    # Expected site center (from EGRID CH999979659148)
    site_center_x = 2687201.7
    site_center_y = 1246498.2
    
    print(f"\n{'#'*80}")
    print(f"RTC_CENTER Transformation Test")
    print(f"Site center (LV95): x={site_center_x:.2f}, y={site_center_y:.2f}")
    print(f"{'#'*80}")
    
    for tile_info in test_tiles:
        test_tile_transformation(
            tile_info['url'],
            tile_info['name'],
            tile_info['region']
        )
    
    print(f"\n{'#'*80}")
    print("Test Summary:")
    print("Compare the RTC_CENTER → LV95 coordinates with the site center.")
    print("All building clusters should be positioned relative to their RTC_CENTER.")
    print("If clusters are still misaligned, check:")
    print("  1. Are vertices being transformed correctly? (tile_center + vertex)")
    print("  2. Is the coordinate system consistent? (meters in both)")
    print("  3. Are there any additional transformations needed?")
    print(f"{'#'*80}\n")

if __name__ == '__main__':
    main()

