#!/usr/bin/env python3
"""
Standalone test to debug GLB parsing from b3dm tiles.
Downloads a single tile and thoroughly tests parsing.
"""

import sys
import requests
import struct
import json

try:
    import pygltflib
except ImportError:
    print("ERROR: pygltflib not installed. Run: pip install pygltflib")
    sys.exit(1)

# Test tile URL (from the working test)
TILE_URL = "https://3d.geo.admin.ch/ch.swisstopo.swissbuildings3d.3d/v1/20251121/11/1891/425.b3dm"

def parse_b3dm_header(b3dm_data):
    """Parse b3dm header"""
    if len(b3dm_data) < 28:
        return None
    
    magic = b3dm_data[0:4]
    if magic != b'b3dm':
        return None
    
    version, = struct.unpack('<I', b3dm_data[4:8])
    byte_length, = struct.unpack('<I', b3dm_data[8:12])
    feature_table_json_byte_length, = struct.unpack('<I', b3dm_data[12:16])
    feature_table_binary_byte_length, = struct.unpack('<I', b3dm_data[16:20])
    batch_table_json_byte_length, = struct.unpack('<I', b3dm_data[20:24])
    batch_table_binary_byte_length, = struct.unpack('<I', b3dm_data[24:28])
    
    header_end = 28
    feature_table_json_start = header_end
    feature_table_json_end = feature_table_json_start + feature_table_json_byte_length
    feature_table_binary_start = feature_table_json_end
    feature_table_binary_end = feature_table_binary_start + feature_table_binary_byte_length
    batch_table_json_start = feature_table_binary_end
    batch_table_json_end = batch_table_json_start + batch_table_json_byte_length
    batch_table_binary_start = batch_table_json_end
    glb_start = batch_table_json_start + batch_table_json_byte_length + batch_table_binary_byte_length
    
    return {
        'version': version,
        'byte_length': byte_length,
        'feature_table_json': b3dm_data[feature_table_json_start:feature_table_json_end],
        'batch_table_json': b3dm_data[batch_table_json_start:batch_table_json_end] if batch_table_json_byte_length > 0 else b'',
        'glb_data': b3dm_data[glb_start:]
    }

def parse_glb_debug(glb_data):
    """Debug GLB parsing with detailed output"""
    print("\n" + "="*60)
    print("GLB PARSING DEBUG")
    print("="*60)
    
    print(f"\nGLB data size: {len(glb_data)} bytes")
    
    # Check GLB header
    if len(glb_data) < 12:
        print("ERROR: GLB too small for header")
        return []
    
    magic = glb_data[0:4]
    print(f"Magic: {magic}")
    if magic != b'glTF':
        print(f"ERROR: Invalid magic, expected 'glTF', got {magic}")
        return []
    
    version = struct.unpack('<I', glb_data[4:8])[0]
    total_length = struct.unpack('<I', glb_data[8:12])[0]
    print(f"Version: {version}, Total length: {total_length}")
    
    # Parse JSON chunk
    if len(glb_data) < 20:
        print("ERROR: GLB too small for JSON chunk header")
        return []
    
    json_chunk_length = struct.unpack('<I', glb_data[12:16])[0]
    json_chunk_type = glb_data[16:20]
    print(f"JSON chunk: length={json_chunk_length}, type={json_chunk_type}")
    
    if json_chunk_type != b'JSON':
        print(f"ERROR: Invalid JSON chunk type: {json_chunk_type}")
        return []
    
    json_end = 20 + json_chunk_length
    
    # Parse binary chunk
    if len(glb_data) < json_end + 8:
        print(f"ERROR: GLB too small for binary chunk header (need {json_end + 8}, have {len(glb_data)})")
        return []
    
    binary_chunk_length = struct.unpack('<I', glb_data[json_end:json_end+4])[0]
    binary_chunk_type = glb_data[json_end+4:json_end+8]
    print(f"Binary chunk: length={binary_chunk_length}, type={binary_chunk_type}")
    
    if binary_chunk_type != b'BIN\0':
        print(f"ERROR: Invalid binary chunk type: {binary_chunk_type}")
        return []
    
    binary_data_start = json_end + 8
    binary_data = glb_data[binary_data_start:binary_data_start + binary_chunk_length]
    print(f"Binary data: {len(binary_data)} bytes")
    
    # Parse GLTF JSON
    json_data = glb_data[20:json_end]
    try:
        gltf_json = json.loads(json_data.decode('utf-8'))
        print(f"\nGLTF JSON parsed successfully")
        print(f"  Scenes: {len(gltf_json.get('scenes', []))}")
        print(f"  Nodes: {len(gltf_json.get('nodes', []))}")
        print(f"  Meshes: {len(gltf_json.get('meshes', []))}")
        print(f"  Accessors: {len(gltf_json.get('accessors', []))}")
        print(f"  BufferViews: {len(gltf_json.get('bufferViews', []))}")
        print(f"  Buffers: {len(gltf_json.get('buffers', []))}")
        
        # Debug: Print structures
        if gltf_json.get('accessors'):
            print(f"\n  First accessor JSON: {gltf_json['accessors'][0]}")
            if len(gltf_json['accessors']) > 2:
                print(f"  Accessor 2 JSON (POSITION): {gltf_json['accessors'][2]}")
            if len(gltf_json['accessors']) > 6:
                print(f"  Accessor 6 JSON (POSITION): {gltf_json['accessors'][6]}")
        if gltf_json.get('bufferViews'):
            print(f"\n  BufferViews JSON:")
            for i, bv in enumerate(gltf_json['bufferViews']):
                print(f"    [{i}] {bv}")
        if gltf_json.get('meshes'):
            print(f"\n  Meshes JSON:")
            for i, mesh in enumerate(gltf_json['meshes']):
                print(f"    [{i}] {mesh}")
                # Check for Draco compression
                for prim in mesh.get('primitives', []):
                    if 'extensions' in prim and 'KHR_draco_mesh_compression' in prim['extensions']:
                        draco_ext = prim['extensions']['KHR_draco_mesh_compression']
                        print(f"      ⚠️  DRACO COMPRESSION DETECTED!")
                        print(f"        bufferView: {draco_ext.get('bufferView')}")
                        print(f"        attributes: {draco_ext.get('attributes')}")
    except Exception as e:
        print(f"ERROR parsing GLTF JSON: {e}")
        return []
    
    # Parse with pygltflib
    try:
        gltf = pygltflib.GLTF2().load_from_bytes(glb_data)
        print(f"\npygltflib parsed successfully")
        print(f"  Scenes: {len(gltf.scenes or [])}")
        print(f"  Nodes: {len(gltf.nodes or [])}")
        print(f"  Meshes: {len(gltf.meshes or [])}")
        print(f"  Accessors: {len(gltf.accessors or [])}")
        print(f"  BufferViews: {len(gltf.bufferViews or [])}")
        print(f"  Buffers: {len(gltf.buffers or [])}")
        
        if gltf.scene is not None:
            print(f"  Active scene index: {gltf.scene}")
    except Exception as e:
        print(f"ERROR parsing with pygltflib: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    # Extract meshes
    buildings = []
    
    # Try processing scenes
    scenes_to_process = []
    if gltf.scene is not None:
        scenes_to_process.append(gltf.scenes[gltf.scene])
        print(f"\nProcessing scene {gltf.scene}")
    else:
        scenes_to_process.extend(gltf.scenes or [])
        print(f"\nProcessing {len(scenes_to_process)} scenes")
    
    if not scenes_to_process:
        print("  No scenes found, trying to process nodes directly...")
        # Process all nodes directly
        for node_idx, node in enumerate(gltf.nodes or []):
            print(f"  Node {node_idx}: mesh={node.mesh}, children={node.children}")
            if node.mesh is not None:
                print(f"    Processing mesh {node.mesh}")
                mesh = gltf.meshes[node.mesh]
                print(f"    Mesh has {len(mesh.primitives)} primitives")
                for prim_idx, primitive in enumerate(mesh.primitives):
                    print(f"      Primitive {prim_idx}:")
                    print(f"        Attributes: {primitive.attributes}")
                    print(f"        Indices: {primitive.indices}")
                    
                    # Get position accessor
                    position_accessor_idx = None
                    if hasattr(primitive.attributes, 'POSITION'):
                        position_accessor_idx = primitive.attributes.POSITION
                        print(f"        POSITION accessor: {position_accessor_idx}")
                    else:
                        print(f"        No POSITION attribute found")
                        print(f"        Available attributes: {dir(primitive.attributes)}")
                        continue
                    
                    if position_accessor_idx is None or position_accessor_idx >= len(gltf.accessors):
                        print(f"        Invalid position accessor index")
                        continue
                    
                    position_accessor = gltf.accessors[position_accessor_idx]
                    print(f"        Position accessor: count={position_accessor.count}, type={position_accessor.type}")
                    
                    buffer_view_idx = position_accessor.bufferView
                    if buffer_view_idx is None or buffer_view_idx >= len(gltf.bufferViews):
                        print(f"        Invalid buffer view index: {buffer_view_idx}")
                        continue
                    
                    buffer_view = gltf.bufferViews[buffer_view_idx]
                    print(f"        Buffer view: byteOffset={buffer_view.byteOffset}, byteLength={buffer_view.byteLength}, byteStride={buffer_view.byteStride}")
                    
                    # Extract vertices
                    byte_offset = (buffer_view.byteOffset or 0) + (position_accessor.byteOffset or 0)
                    byte_stride = buffer_view.byteStride or (3 * 4)  # 3 floats * 4 bytes
                    count = position_accessor.count
                    
                    print(f"        Extracting {count} vertices from offset {byte_offset}, stride {byte_stride}")
                    
                    vertices = []
                    for i in range(count):
                        offset = byte_offset + i * byte_stride
                        if offset + 12 <= len(binary_data):
                            x, y, z = struct.unpack('<fff', binary_data[offset:offset+12])
                            vertices.append([x, y, z])
                    
                    print(f"        Extracted {len(vertices)} vertices")
                    
                    # Extract faces
                    faces = []
                    if primitive.indices is not None:
                        indices_accessor_idx = primitive.indices
                        print(f"        Indices accessor: {indices_accessor_idx}")
                        
                        if indices_accessor_idx < len(gltf.accessors):
                            indices_accessor = gltf.accessors[indices_accessor_idx]
                            indices_buffer_view_idx = indices_accessor.bufferView
                            
                            if indices_buffer_view_idx is not None and indices_buffer_view_idx < len(gltf.bufferViews):
                                indices_buffer_view = gltf.bufferViews[indices_buffer_view_idx]
                                indices_byte_offset = (indices_buffer_view.byteOffset or 0) + (indices_accessor.byteOffset or 0)
                                
                                if indices_accessor.componentType == 5123:  # UNSIGNED_SHORT
                                    index_size = 2
                                    unpack_fmt = '<H'
                                elif indices_accessor.componentType == 5125:  # UNSIGNED_INT
                                    index_size = 4
                                    unpack_fmt = '<I'
                                else:
                                    index_size = 0
                                
                                if index_size > 0:
                                    print(f"        Extracting {indices_accessor.count} indices from offset {indices_byte_offset}, size {index_size}")
                                    for i in range(0, indices_accessor.count, 3):
                                        if i + 2 < indices_accessor.count:
                                            offset0 = indices_byte_offset + i * index_size
                                            offset1 = indices_byte_offset + (i+1) * index_size
                                            offset2 = indices_byte_offset + (i+2) * index_size
                                            
                                            if offset2 + index_size <= len(binary_data):
                                                idx0, = struct.unpack(unpack_fmt, binary_data[offset0:offset0+index_size])
                                                idx1, = struct.unpack(unpack_fmt, binary_data[offset1:offset1+index_size])
                                                idx2, = struct.unpack(unpack_fmt, binary_data[offset2:offset2+index_size])
                                                faces.append([idx0, idx1, idx2])
                                    print(f"        Extracted {len(faces)} faces")
                    
                    if vertices:
                        buildings.append({
                            'vertices': vertices,
                            'faces': faces,
                            'batch_id': None
                        })
                        print(f"        ✓ Added building mesh with {len(vertices)} vertices, {len(faces)} faces")
    
    # Process scenes
    for scene_idx, scene in enumerate(scenes_to_process):
        print(f"\nProcessing scene {scene_idx}")
        print(f"  Scene nodes: {scene.nodes}")
        
        for node_idx in (scene.nodes if scene.nodes else []):
            if node_idx >= len(gltf.nodes):
                print(f"  Invalid node index: {node_idx}")
                continue
            
            node = gltf.nodes[node_idx]
            print(f"  Node {node_idx}: mesh={node.mesh}, children={node.children}")
            
            if node.mesh is not None:
                if node.mesh >= len(gltf.meshes):
                    print(f"    Invalid mesh index: {node.mesh}")
                    continue
                
                mesh = gltf.meshes[node.mesh]
                print(f"    Mesh has {len(mesh.primitives)} primitives")
                
                for prim_idx, primitive in enumerate(mesh.primitives):
                    print(f"      Primitive {prim_idx}:")
                    print(f"        Attributes: {primitive.attributes}")
                    print(f"        Indices: {primitive.indices}")
                    
                    # Get position accessor
                    position_accessor_idx = None
                    if hasattr(primitive.attributes, 'POSITION'):
                        position_accessor_idx = primitive.attributes.POSITION
                        print(f"        POSITION accessor: {position_accessor_idx}")
                    else:
                        print(f"        No POSITION attribute found")
                        print(f"        Available attributes: {dir(primitive.attributes)}")
                        continue
                    
                    if position_accessor_idx is None or position_accessor_idx >= len(gltf.accessors):
                        print(f"        Invalid position accessor index")
                        continue
                    
                    position_accessor = gltf.accessors[position_accessor_idx]
                    print(f"        Position accessor: count={position_accessor.count}, type={position_accessor.type}")
                    
                    buffer_view_idx = position_accessor.bufferView
                    if buffer_view_idx is None or buffer_view_idx >= len(gltf.bufferViews):
                        print(f"        Invalid buffer view index: {buffer_view_idx}")
                        continue
                    
                    buffer_view = gltf.bufferViews[buffer_view_idx]
                    print(f"        Buffer view: byteOffset={buffer_view.byteOffset}, byteLength={buffer_view.byteLength}, byteStride={buffer_view.byteStride}")
                    
                    # Extract vertices
                    byte_offset = (buffer_view.byteOffset or 0) + (position_accessor.byteOffset or 0)
                    byte_stride = buffer_view.byteStride or (3 * 4)  # 3 floats * 4 bytes
                    count = position_accessor.count
                    
                    print(f"        Extracting {count} vertices from offset {byte_offset}, stride {byte_stride}")
                    
                    vertices = []
                    for i in range(count):
                        offset = byte_offset + i * byte_stride
                        if offset + 12 <= len(binary_data):
                            x, y, z = struct.unpack('<fff', binary_data[offset:offset+12])
                            vertices.append([x, y, z])
                    
                    print(f"        Extracted {len(vertices)} vertices")
                    
                    # Extract faces
                    faces = []
                    if primitive.indices is not None:
                        indices_accessor_idx = primitive.indices
                        print(f"        Indices accessor: {indices_accessor_idx}")
                        
                        if indices_accessor_idx < len(gltf.accessors):
                            indices_accessor = gltf.accessors[indices_accessor_idx]
                            indices_buffer_view_idx = indices_accessor.bufferView
                            
                            if indices_buffer_view_idx is not None and indices_buffer_view_idx < len(gltf.bufferViews):
                                indices_buffer_view = gltf.bufferViews[indices_buffer_view_idx]
                                indices_byte_offset = (indices_buffer_view.byteOffset or 0) + (indices_accessor.byteOffset or 0)
                                
                                if indices_accessor.componentType == 5123:  # UNSIGNED_SHORT
                                    index_size = 2
                                    unpack_fmt = '<H'
                                elif indices_accessor.componentType == 5125:  # UNSIGNED_INT
                                    index_size = 4
                                    unpack_fmt = '<I'
                                else:
                                    index_size = 0
                                
                                if index_size > 0:
                                    print(f"        Extracting {indices_accessor.count} indices from offset {indices_byte_offset}, size {index_size}")
                                    for i in range(0, indices_accessor.count, 3):
                                        if i + 2 < indices_accessor.count:
                                            offset0 = indices_byte_offset + i * index_size
                                            offset1 = indices_byte_offset + (i+1) * index_size
                                            offset2 = indices_byte_offset + (i+2) * index_size
                                            
                                            if offset2 + index_size <= len(binary_data):
                                                idx0, = struct.unpack(unpack_fmt, binary_data[offset0:offset0+index_size])
                                                idx1, = struct.unpack(unpack_fmt, binary_data[offset1:offset1+index_size])
                                                idx2, = struct.unpack(unpack_fmt, binary_data[offset2:offset2+index_size])
                                                faces.append([idx0, idx1, idx2])
                                    print(f"        Extracted {len(faces)} faces")
                    
                    if vertices:
                        buildings.append({
                            'vertices': vertices,
                            'faces': faces,
                            'batch_id': None
                        })
                        print(f"        ✓ Added building mesh with {len(vertices)} vertices, {len(faces)} faces")
    
    print(f"\n{'='*60}")
    print(f"RESULT: Extracted {len(buildings)} building meshes")
    print(f"{'='*60}")
    
    if len(buildings) == 0:
        print("\n⚠️  ROOT CAUSE IDENTIFIED:")
        print("   The GLB meshes use KHR_draco_mesh_compression (Draco compression).")
        print("   To extract geometry, you need to:")
        print("   1. Install a Draco decoder library (e.g., 'draco' or 'pydraco')")
        print("   2. Extract compressed data from bufferView referenced in extension")
        print("   3. Decompress using Draco decoder")
        print("   4. Map decompressed attributes back to accessors")
        print("\n   Alternative: Use a library that handles Draco automatically,")
        print("   or fetch buildings from a different source (if available).")
    
    return buildings

def main():
    print("="*60)
    print("GLB Parsing Debug Test")
    print("="*60)
    print(f"\nDownloading tile: {TILE_URL}")
    
    try:
        response = requests.get(TILE_URL, timeout=60)
        response.raise_for_status()
        b3dm_data = response.content
        print(f"✓ Downloaded {len(b3dm_data)} bytes")
    except Exception as e:
        print(f"✗ Error downloading: {e}")
        return 1
    
    # Parse b3dm header
    header = parse_b3dm_header(b3dm_data)
    if not header:
        print("✗ Failed to parse b3dm header")
        return 1
    
    print(f"\n✓ b3dm header parsed:")
    print(f"  Version: {header['version']}")
    print(f"  Total length: {header['byte_length']} bytes")
    print(f"  GLB data: {len(header['glb_data'])} bytes")
    
    # Parse feature table
    if header['feature_table_json']:
        try:
            feature_table = json.loads(header['feature_table_json'].decode('utf-8'))
            print(f"  Feature table: {len(feature_table)} fields")
        except:
            print(f"  ⚠️  Feature table parse failed")
    
    # Parse batch table
    if header['batch_table_json']:
        try:
            batch_table = json.loads(header['batch_table_json'].decode('utf-8'))
            print(f"  Batch table: {len(batch_table)} fields")
            if 'id' in batch_table:
                ids = batch_table['id']
                print(f"    Building IDs: {len(ids) if isinstance(ids, list) else 'N/A'}")
        except:
            print(f"  ⚠️  Batch table parse failed")
    
    # Parse GLB
    buildings = parse_glb_debug(header['glb_data'])
    
    if buildings:
        print(f"\n✓ SUCCESS: Extracted {len(buildings)} building meshes!")
        total_vertices = sum(len(b['vertices']) for b in buildings)
        total_faces = sum(len(b['faces']) for b in buildings)
        print(f"  Total vertices: {total_vertices}")
        print(f"  Total faces: {total_faces}")
        return 0
    else:
        print(f"\n✗ FAILED: No building meshes extracted")
        return 1

if __name__ == "__main__":
    sys.exit(main())

