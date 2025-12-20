#!/usr/bin/env python3
"""
Standalone test: Extract buildings for EGRID and create IFC file.
"""

import sys
import os
sys.path.insert(0, '.')

from combined_terrain import (
    fetch_boundary_by_egrid,
    fetch_buildings_from_3d_tiles,
    prepare_building_geometries
)
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom

EGRID = "CH999979659148"
RADIUS = 500

def main():
    print("="*70)
    print("EGRID BUILDINGS TO IFC TEST")
    print("="*70)
    print(f"\nEGRID: {EGRID}")
    print(f"Radius: {RADIUS}m")
    
    # Step 1: Fetch boundary
    print("\n1. Fetching boundary...")
    try:
        boundary, metadata = fetch_boundary_by_egrid(EGRID)
        centroid = boundary.centroid
        print(f"   ✓ Boundary fetched")
        print(f"   Centroid: ({centroid.x:.2f}, {centroid.y:.2f})")
        print(f"   Area: {boundary.area:.1f} m²")
    except Exception as e:
        print(f"   ✗ Error fetching boundary: {e}")
        return False
    
    # Step 2: Fetch buildings
    print(f"\n2. Fetching buildings within {RADIUS}m...")
    try:
        buildings = fetch_buildings_from_3d_tiles(
            centroid.x, 
            centroid.y, 
            RADIUS,
            max_buildings=100
        )
        print(f"   ✓ Fetched {len(buildings)} buildings")
        
        if len(buildings) == 0:
            print("   ⚠️  No buildings found - trying larger radius...")
            buildings = fetch_buildings_from_3d_tiles(
                centroid.x,
                centroid.y,
                RADIUS * 3,  # Try 6km radius
                max_buildings=100
            )
            print(f"   Fetched {len(buildings)} buildings with larger radius")
        
        if len(buildings) == 0:
            print("   ✗ No buildings found")
            return False
        
        # Show building info
        for i, building in enumerate(buildings[:5]):
            geom = building.get('geometry')
            if geom:
                bcentroid = geom.centroid
                dist = centroid.distance(bcentroid)
                print(f"   Building {i}: centroid=({bcentroid.x:.2f}, {bcentroid.y:.2f}), distance={dist:.1f}m")
        
    except Exception as e:
        print(f"   ✗ Error fetching buildings: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 3: Create IFC file
    print(f"\n3. Creating IFC file...")
    try:
        # Create IFC model
        model = ifcopenshell.api.run("project.create_file")
        project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Building Extraction Test")
        
        # Create site
        site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
        ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
        
        # Prepare building geometries (not needed for simple IFC creation)
        # building_geoms = prepare_building_geometries(buildings, [], [])
        print(f"   Using {len(buildings)} buildings directly")
        
        # Calculate offset for local coordinates (use site centroid)
        offset_x = centroid.x
        offset_y = centroid.y
        offset_z = 0.0  # Will calculate from building vertices
        
        # Create body context for geometry
        owner_history = ifcopenshell.api.run("owner.create_owner_history", model)
        body_context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
        body_context.ContextIdentifier = "Body"
        body_context.ContextType = "Model"
        body_context.TargetView = "MODEL_VIEW"
        
        # Create building elements with geometry
        building_count = 0
        for i, building in enumerate(buildings):
            try:
                geom = building.get('geometry')
                if not geom:
                    continue
                
                # Get vertices and faces from building mesh if available
                vertices = building.get('vertices', [])
                faces_indices = building.get('faces', [])
                
                if not vertices or not faces_indices:
                    # Try to extract from geometry
                    if hasattr(geom, 'exterior'):
                        # 2D polygon - skip for now
                        continue
                    else:
                        continue
                
                # Calculate base Z from vertices
                if vertices:
                    min_z = min(v[2] for v in vertices)
                    offset_z = min(offset_z, min_z)
                
                # Create building
                building_elem = ifcopenshell.api.run(
                    "root.create_entity",
                    model,
                    ifc_class="IfcBuilding",
                    name=f"Building_{building_count}"
                )
                ifcopenshell.api.run("aggregate.assign_object", model, products=[building_elem], relating_object=site)
                
                # Create geometry from mesh
                try:
                    # Create IFC faces from triangles
                    ifc_faces = []
                    for face_idx in faces_indices:
                        if len(face_idx) >= 3:
                            # Get triangle vertices
                            v0_idx, v1_idx, v2_idx = face_idx[0], face_idx[1], face_idx[2]
                            if v0_idx < len(vertices) and v1_idx < len(vertices) and v2_idx < len(vertices):
                                v0 = vertices[v0_idx]
                                v1 = vertices[v1_idx]
                                v2 = vertices[v2_idx]
                                
                                # Convert to local coordinates
                                p0 = model.createIfcCartesianPoint([
                                    float(v0[0] - offset_x),
                                    float(v0[1] - offset_y),
                                    float(v0[2] - offset_z)
                                ])
                                p1 = model.createIfcCartesianPoint([
                                    float(v1[0] - offset_x),
                                    float(v1[1] - offset_y),
                                    float(v1[2] - offset_z)
                                ])
                                p2 = model.createIfcCartesianPoint([
                                    float(v2[0] - offset_x),
                                    float(v2[1] - offset_y),
                                    float(v2[2] - offset_z)
                                ])
                                
                                # Create triangle face
                                tri_loop = model.createIfcPolyLoop([p0, p1, p2])
                                face = model.createIfcFace([model.createIfcFaceOuterBound(tri_loop, True)])
                                ifc_faces.append(face)
                    
                    if ifc_faces:
                        # Create shell-based surface model
                        shell = model.createIfcOpenShell(ifc_faces)
                        shell_model = model.createIfcShellBasedSurfaceModel([shell])
                        
                        # Create shape representation
                        shape_rep = model.createIfcShapeRepresentation(
                            body_context, "Body", "SurfaceModel", [shell_model]
                        )
                        
                        # Create product definition shape
                        product_shape = model.createIfcProductDefinitionShape(None, None, [shape_rep])
                        building_elem.Representation = product_shape
                        
                        # Set placement
                        placement_origin = model.createIfcCartesianPoint([0.0, 0.0, 0.0])
                        axis = model.createIfcDirection([0.0, 0.0, 1.0])
                        ref_dir = model.createIfcDirection([1.0, 0.0, 0.0])
                        placement = model.createIfcAxis2Placement3D(placement_origin, axis, ref_dir)
                        building_elem.ObjectPlacement = model.createIfcLocalPlacement(
                            site.ObjectPlacement, placement
                        )
                        
                        print(f"   Building {building_count}: {len(ifc_faces)} faces")
                    
                except Exception as e:
                    print(f"   Warning: Could not create geometry for building {i}: {e}")
                    import traceback
                    traceback.print_exc()
                
                building_count += 1
                
                if building_count >= 50:  # Limit for test
                    break
                    
            except Exception as e:
                print(f"   Warning: Could not create building {i}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # Save IFC file
        output_file = f"test_{EGRID}_buildings.ifc"
        model.write(output_file)
        
        file_size = os.path.getsize(output_file)
        print(f"   ✓ Created IFC file: {output_file}")
        print(f"   Buildings in IFC: {building_count}")
        print(f"   File size: {file_size:,} bytes")
        
        if building_count > 0:
            print("\n" + "="*70)
            print("✓✓✓ SUCCESS: Buildings extracted and added to IFC!")
            print("="*70)
            print(f"\nOutput file: {output_file}")
            return True
        else:
            print("\n✗ No buildings added to IFC")
            return False
            
    except Exception as e:
        print(f"   ✗ Error creating IFC: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

