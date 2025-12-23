#!/usr/bin/env python3
"""
Simple standalone test for 3D Tiles building extraction.
Tests the 3D Tiles parsing functionality independently.
"""

import sys
import requests
import json
import struct
from pyproj import Transformer
import math

try:
    import pygltflib
except ImportError:
    print("ERROR: pygltflib not installed. Run: pip install pygltflib")
    sys.exit(1)

sys.path.insert(0, '.')
from combined_terrain import parse_b3dm_header

# Test coordinates (same as main script)
CENTER_X = 2687201.7  # EPSG:2056
CENTER_Y = 1246498.2  # EPSG:2056
RADIUS = 200  # meters

BASE_URL = "https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1"

def fetch_tileset(url):
    """Fetch tileset.json"""
    # Ensure URL ends with tileset.json
    if not url.endswith('tileset.json'):
        if url.endswith('/'):
            url = url + 'tileset.json'
        else:
            url = url + '/tileset.json'
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        # Don't print errors for nested tilesets (they might not exist)
        return None

def parse_glb_simple(glb_data):
    """Simple GLB parser to extract vertex count"""
    try:
        gltf = pygltflib.GLTF2().load_from_bytes(glb_data)
        
        # Count meshes and vertices
        total_vertices = 0
        total_faces = 0
        
        scenes = gltf.scenes or []
        if gltf.scene is not None:
            scenes = [gltf.scenes[gltf.scene]]
        
        for scene in scenes:
            for node_idx in (scene.nodes if scene.nodes else []):
                node = gltf.nodes[node_idx]
                if node.mesh is not None:
                    mesh = gltf.meshes[node.mesh]
                    for primitive in mesh.primitives:
                        # Access attributes correctly - it's an Attributes object
                        if hasattr(primitive.attributes, 'POSITION'):
                            pos_idx = primitive.attributes.POSITION
                            if pos_idx is not None and pos_idx < len(gltf.accessors):
                                accessor = gltf.accessors[pos_idx]
                                total_vertices += accessor.count
                        if primitive.indices is not None:
                            idx_accessor = gltf.accessors[primitive.indices]
                            total_faces += idx_accessor.count // 3
        
        return total_vertices, total_faces
    except Exception as e:
        print(f"    GLB parse error: {e}")
        import traceback
        traceback.print_exc()
        return 0, 0

def test_tileset_traversal():
    """Test tileset traversal to find b3dm tiles"""
    print("=" * 60)
    print("Testing 3D Tiles Building Extraction")
    print("=" * 60)
    print(f"\nTest area:")
    print(f"  Center: E={CENTER_X}, N={CENTER_Y} (EPSG:2056)")
    print(f"  Radius: {RADIUS}m")
    
    # Step 1: Fetch root tileset
    print("\n1. Fetching root tileset...")
    root_tileset = fetch_tileset(f"{BASE_URL}/tileset.json")
    if not root_tileset:
        print("   FAILED")
        return False
    print("   ✓ Root tileset fetched")
    
    # Step 2: Find date-based tileset
    print("\n2. Finding date-based tileset...")
    date_tileset = None
    root_node = root_tileset.get('root', {})
    if 'children' in root_node:
        for child in root_node['children']:
            if 'content' in child and 'uri' in child.get('content', {}):
                uri = child['content']['uri']
                if uri.endswith('tileset.json'):
                    date_str = uri.replace('/tileset.json', '')
                    if date_str.isdigit() and len(date_str) == 8:
                        date_tileset = fetch_tileset(f"{BASE_URL}/{date_str}/tileset.json")
                        if date_tileset:
                            print(f"   ✓ Found date tileset: {date_str}")
                            break
    
    if not date_tileset:
        date_tileset = root_tileset
        print("   Using root tileset")
    
    # Step 3: Traverse to find b3dm tiles
    print("\n3. Traversing tileset hierarchy...")
    tiles_found = []
    
    def traverse(node, base_url, depth=0, max_depth=15, visited=None):
        if visited is None:
            visited = set()
        if depth > max_depth:
            return
        
        if 'content' in node:
            content = node['content']
            uri = content.get('uri') if isinstance(content, dict) else content
            
            if uri:
                if '.b3dm' in uri or uri.endswith('.b3dm'):
                    tiles_found.append((uri, base_url))
                    print(f"   ✓ Found b3dm (depth {depth}): {uri}")
                elif 'tileset' in uri.lower() and uri not in visited:
                    # Nested tileset
                    visited.add(uri)
                    if base_url.endswith('/tileset.json'):
                        nested_base = base_url.replace('/tileset.json', '')
                    elif base_url.endswith('/'):
                        nested_base = base_url[:-1]
                    else:
                        nested_base = base_url
                    
                    # Construct nested tileset URL
                    if uri.startswith('/'):
                        nested_full_url = f"{BASE_URL}{uri}"
                    else:
                        nested_full_url = f"{nested_base}/{uri}"
                    
                    if depth <= 5:  # Only print first few levels
                        print(f"   Traversing nested tileset (depth {depth}): {uri}")
                    nested_tileset = fetch_tileset(nested_full_url)
                    if nested_tileset:
                        nested_root = nested_tileset.get('root', {})
                        # Base URL for child tiles
                        nested_base_for_tiles = nested_full_url.rsplit('/', 1)[0]
                        traverse(nested_root, nested_base_for_tiles, depth + 1, max_depth, visited)
        
        if 'children' in node:
            for child in node['children']:
                traverse(child, base_url, depth + 1, max_depth, visited)
    
    date_base = f"{BASE_URL}/20251121" if date_tileset != root_tileset else BASE_URL
    traverse(date_tileset.get('root', {}), date_base)
    
    print(f"\n   Total tiles found: {len(tiles_found)}")
    
    if not tiles_found:
        print("\n   ⚠️  No b3dm tiles found in tileset hierarchy")
        print("   This might be normal - tiles may be very deep in hierarchy")
        return False
    
    # Step 4: Download and parse first tile
    print(f"\n4. Testing download and parse of first tile...")
    tile_uri, tile_base = tiles_found[0]
    tile_url = f"{tile_base}/{tile_uri}" if not tile_uri.startswith('http') else tile_uri
    
    print(f"   Downloading: {tile_url}")
    try:
        response = requests.get(tile_url, timeout=60)
        response.raise_for_status()
        b3dm_data = response.content
        print(f"   ✓ Downloaded {len(b3dm_data)} bytes")
        
        # Parse header
        header = parse_b3dm_header(b3dm_data)
        if not header:
            print("   ✗ Failed to parse b3dm header")
            return False
        
        print(f"   ✓ b3dm header parsed:")
        print(f"     Version: {header['version']}")
        print(f"     Total length: {header['byte_length']} bytes")
        print(f"     GLB data: {len(header['glb_data'])} bytes")
        
        # Parse feature table
        if header['feature_table_json']:
            try:
                feature_table = json.loads(header['feature_table_json'].decode('utf-8'))
                print(f"   ✓ Feature table: {len(feature_table)} fields")
            except:
                print(f"   ⚠️  Feature table parse failed")
        
        # Parse batch table
        if header['batch_table_json']:
            try:
                batch_table = json.loads(header['batch_table_json'].decode('utf-8'))
                print(f"   ✓ Batch table: {len(batch_table)} fields")
                if 'id' in batch_table:
                    ids = batch_table['id']
                    print(f"     Building IDs: {len(ids) if isinstance(ids, list) else 'N/A'}")
            except:
                print(f"   ⚠️  Batch table parse failed")
        
        # Parse GLB
        vertices, faces = parse_glb_simple(header['glb_data'])
        print(f"   ✓ GLB parsed:")
        print(f"     Vertices: {vertices}")
        print(f"     Faces: {faces}")
        
        if vertices > 0:
            print(f"\n   ✓ SUCCESS: Building geometry extracted!")
            return True
        else:
            print(f"\n   ⚠️  No vertices found in GLB")
            return False
            
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_tileset_traversal()
    print("\n" + "=" * 60)
    if success:
        print("TEST PASSED: 3D Tiles extraction is working!")
    else:
        print("TEST FAILED: Check output above for issues")
    print("=" * 60)
    sys.exit(0 if success else 1)

