#!/usr/bin/env python3
"""
Test script for building integration with terrain workflow

This script demonstrates and tests the complete workflow of:
1. Loading terrain and site boundary
2. Fetching building footprints from Swiss APIs
3. Converting buildings to IFC elements
4. Creating a combined IFC model

Run with network access to test with real data.
"""

import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

logger = logging.getLogger(__name__)


def test_building_to_ifc_conversion():
    """Test: Convert building features to IFC elements"""
    print("\n" + "="*80)
    print("TEST 1: Building to IFC Conversion")
    print("="*80)

    try:
        from src.building_loader import BuildingFeature
        from src.building_to_ifc import building_to_ifc
        from shapely.geometry import Polygon
        import ifcopenshell
        import ifcopenshell.api

        # Create a mock building
        building = BuildingFeature(
            id="TEST_001",
            geometry=Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
            height=20.0,
            building_class="Residential",
            roof_type="Flat"
        )

        # Create minimal IFC structure
        model = ifcopenshell.file(schema='IFC4')
        project = ifcopenshell.api.run("root.create_entity", model,
                                       ifc_class="IfcProject", name="Test")
        ifcopenshell.api.run("unit.assign_unit", model)
        context = ifcopenshell.api.run("context.add_context", model, context_type="Model")

        body_context = ifcopenshell.api.run(
            "context.add_context", model,
            context_type="Model", context_identifier="Body",
            target_view="MODEL_VIEW", parent=context
        )
        footprint_context = ifcopenshell.api.run(
            "context.add_context", model,
            context_type="Model", context_identifier="FootPrint",
            target_view="PLAN_VIEW", parent=context
        )

        site = ifcopenshell.api.run("root.create_entity", model,
                                    ifc_class="IfcSite", name="TestSite")
        ifcopenshell.api.run("aggregate.assign_object", model,
                            products=[site], relating_object=project)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=site)

        # Convert building to IFC
        ifc_building = building_to_ifc(
            model=model,
            building=building,
            site=site,
            body_context=body_context,
            footprint_context=footprint_context,
            base_elevation=0.0
        )

        # Verify
        assert ifc_building is not None
        assert ifc_building.is_a("IfcBuilding")
        assert ifc_building.Name == "TEST_001"
        assert ifc_building.Representation is not None

        print("✅ PASS: Building converted to IFC successfully")
        print(f"   Building name: {ifc_building.Name}")
        print(f"   Representations: {len(ifc_building.Representation.Representations)}")

        # Save for inspection
        test_output = "test_building.ifc"
        model.write(test_output)
        print(f"   Test IFC saved to: {test_output}")

        return True

    except Exception as e:
        print(f"❌ FAIL: {e}")
        logger.exception("Test failed")
        return False


def test_load_buildings_for_egrid():
    """Test: Load buildings around a Swiss parcel"""
    print("\n" + "="*80)
    print("TEST 2: Load Buildings for EGRID")
    print("="*80)

    egrid = "CH999979659148"  # Test EGRID
    print(f"EGRID: {egrid}")

    try:
        from src.building_loader import get_buildings_around_egrid

        buildings, stats = get_buildings_around_egrid(egrid, buffer_m=10)

        print(f"\n✅ PASS: Loaded {stats['count']} buildings")
        print(f"\nStatistics:")
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  {key:30s}: {value:10.1f}")
            else:
                print(f"  {key:30s}: {value:10}")

        if buildings:
            print(f"\nSample building:")
            b = buildings[0]
            print(f"  ID: {b.id}")
            print(f"  Height: {b.height:.1f}m" if b.height else "  Height: N/A")
            print(f"  Footprint: {b.geometry.area:.1f}m²")

        return stats['count'] > 0

    except Exception as e:
        print(f"❌ FAIL: {e}")
        print("(This is expected if running without network access)")
        return False


def test_full_workflow():
    """Test: Full terrain + buildings workflow"""
    print("\n" + "="*80)
    print("TEST 3: Full Terrain + Buildings Workflow")
    print("="*80)

    egrid = "CH999979659148"
    output_file = "test_terrain_with_buildings.ifc"

    print(f"EGRID: {egrid}")
    print(f"Output: {output_file}")

    try:
        from src.terrain_with_buildings import run_terrain_with_buildings_workflow

        result_path = run_terrain_with_buildings_workflow(
            egrid=egrid,
            radius=200.0,  # Smaller radius for faster testing
            resolution=20.0,  # Coarser resolution for speed
            include_terrain=True,
            include_site_solid=True,
            include_buildings=True,
            building_buffer_m=10.0,
            output_path=output_file
        )

        if Path(result_path).exists():
            file_size = Path(result_path).stat().st_size
            print(f"\n✅ PASS: IFC file created successfully")
            print(f"   Path: {result_path}")
            print(f"   Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")

            # Verify IFC content
            import ifcopenshell
            model = ifcopenshell.open(result_path)

            buildings = model.by_type("IfcBuilding")
            sites = model.by_type("IfcSite")
            terrain = model.by_type("IfcGeographicElement")

            print(f"\n   IFC Contents:")
            print(f"     Sites: {len(sites)}")
            print(f"     Terrain elements: {len(terrain)}")
            print(f"     Buildings: {len(buildings)}")

            return len(buildings) > 0

        else:
            print(f"❌ FAIL: Output file not created")
            return False

    except Exception as e:
        print(f"❌ FAIL: {e}")
        print("(This is expected if running without network access)")
        logger.exception("Test failed")
        return False


def test_add_buildings_to_existing_ifc():
    """Test: Add buildings to existing IFC file"""
    print("\n" + "="*80)
    print("TEST 4: Add Buildings to Existing IFC")
    print("="*80)

    # This test requires an existing IFC file from terrain workflow
    # Skip if not available

    try:
        from src.terrain_with_buildings import add_buildings_to_ifc
        from src.building_loader import get_buildings_around_egrid
        import ifcopenshell

        # Check if base terrain file exists
        base_ifc = "combined_terrain.ifc"
        if not Path(base_ifc).exists():
            print(f"⚠️  SKIP: Base terrain IFC not found: {base_ifc}")
            print(f"   Run terrain_with_site.py first to create base file")
            return None

        # Load buildings
        egrid = "CH999979659148"
        buildings, stats = get_buildings_around_egrid(egrid, buffer_m=10)

        if stats['count'] == 0:
            print(f"⚠️  SKIP: No buildings found for {egrid}")
            return None

        # Add buildings to IFC
        output_file = "test_add_buildings.ifc"
        add_buildings_to_ifc(
            ifc_path=base_ifc,
            buildings=buildings,
            output_path=output_file,
            use_extrusion=True
        )

        # Verify
        model = ifcopenshell.open(output_file)
        ifc_buildings = model.by_type("IfcBuilding")

        print(f"\n✅ PASS: Added {len(ifc_buildings)} buildings to IFC")
        print(f"   Output: {output_file}")

        return len(ifc_buildings) == stats['count']

    except Exception as e:
        print(f"❌ FAIL: {e}")
        logger.exception("Test failed")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("🧪 BUILDING INTEGRATION TEST SUITE")
    print("="*80)
    print("\nThis test suite validates the building integration functionality.")
    print("Some tests require network access to Swiss geo.admin.ch APIs.\n")

    tests = [
        ("Building to IFC conversion", test_building_to_ifc_conversion),
        ("Load buildings for EGRID", test_load_buildings_for_egrid),
        ("Full terrain + buildings workflow", test_full_workflow),
        ("Add buildings to existing IFC", test_add_buildings_to_existing_ifc),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except KeyboardInterrupt:
            print("\n\n⚠️  Tests interrupted by user")
            sys.exit(1)
        except Exception as e:
            logger.exception(f"Test '{name}' failed with exception")
            results.append((name, False))

    # Print summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)

    for name, result in results:
        if result is True:
            status = "✅ PASS"
        elif result is False:
            status = "❌ FAIL"
        else:
            status = "⚠️  SKIP"

        print(f"{status}: {name}")

    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")

    if failed > 0:
        print("\n⚠️  Some tests failed. See output above for details.")
        sys.exit(1)
    elif passed == 0:
        print("\n⚠️  No tests passed. Check network connectivity.")
        sys.exit(1)
    else:
        print("\n✅ All runnable tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
