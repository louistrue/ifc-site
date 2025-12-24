#!/usr/bin/env python3
"""
Test all building retrieval methods and compare results

Tests WFS, STAC, and other methods with the same EGRID to see which works best.
"""

import logging
import time
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

logger = logging.getLogger(__name__)


def test_rest_method(egrid: str, buffer_m: float = 10):
    """Test REST API method for getting buildings (RECOMMENDED)"""
    print("\n" + "="*80)
    print("TEST: REST API Method (Vector 25k Buildings)")
    print("="*80)
    
    try:
        from src.building_loader import SwissBuildingLoader
        from src.terrain_with_site import fetch_boundary_by_egrid
        
        loader = SwissBuildingLoader()
        
        # Get site boundary
        site_boundary, metadata = fetch_boundary_by_egrid(egrid)
        if site_boundary is None:
            raise ValueError(f"No boundary found for EGRID {egrid}")
        bounds = site_boundary.bounds
        bbox = (
            bounds[0] - buffer_m,
            bounds[1] - buffer_m,
            bounds[2] + buffer_m,
            bounds[3] + buffer_m
        )
        
        print(f"  BBOX: {bbox}")
        
        start_time = time.time()
        buildings = loader.get_buildings_rest(bbox, max_features=1000)
        elapsed = time.time() - start_time
        
        stats = loader.get_building_statistics(buildings)
        
        print(f"\n✅ REST API Results:")
        print(f"   Time: {elapsed:.2f}s")
        print(f"   Buildings found: {stats['count']}")
        print(f"   Total footprint: {stats['total_footprint_area_m2']:.0f}m²")
        print(f"   Avg footprint: {stats['avg_footprint_area_m2']:.1f}m²")
        
        if buildings:
            print(f"\n   Sample building:")
            b = buildings[0]
            print(f"     ID: {b.id}")
            print(f"     Class: {b.building_class}")
            print(f"     Area: {b.geometry.area:.1f}m²")
        
        return {
            "method": "REST API",
            "success": True,
            "time": elapsed,
            "buildings": buildings,
            "stats": stats
        }
        
    except Exception as e:
        print(f"\n❌ REST API Failed: {e}")
        logger.exception("REST API test failed")
        return {
            "method": "REST API",
            "success": False,
            "error": str(e),
            "time": 0,
            "buildings": [],
            "stats": {}
        }


def test_wfs_method(egrid: str, buffer_m: float = 10):
    """Test WFS method for getting buildings (DISABLED on Swiss servers)"""
    print("\n" + "="*80)
    print("TEST: WFS Method (Note: DISABLED on Swiss servers)")
    print("="*80)
    
    try:
        from src.building_loader import SwissBuildingLoader
        from src.terrain_with_site import fetch_boundary_by_egrid
        
        loader = SwissBuildingLoader()
        
        # Get site boundary
        site_boundary, metadata = fetch_boundary_by_egrid(egrid)
        if site_boundary is None:
            raise ValueError(f"No boundary found for EGRID {egrid}")
        bounds = site_boundary.bounds
        bbox = (
            bounds[0] - buffer_m,
            bounds[1] - buffer_m,
            bounds[2] + buffer_m,
            bounds[3] + buffer_m
        )
        
        print(f"  BBOX: {bbox}")
        
        start_time = time.time()
        buildings = loader.get_buildings_wfs(bbox, max_features=1000)
        elapsed = time.time() - start_time
        
        stats = loader.get_building_statistics(buildings)
        
        print(f"\n✅ WFS Results:")
        print(f"   Time: {elapsed:.2f}s")
        print(f"   Buildings found: {stats['count']}")
        print(f"   Total footprint: {stats['total_footprint_area_m2']:.0f}m²")
        
        return {
            "method": "WFS",
            "success": True,
            "time": elapsed,
            "buildings": buildings,
            "stats": stats
        }
        
    except Exception as e:
        print(f"\n❌ WFS Failed: {e}")
        print("   (WFS is disabled on Swiss geo.admin.ch servers)")
        return {
            "method": "WFS",
            "success": False,
            "error": str(e),
            "time": 0,
            "buildings": [],
            "stats": {}
        }


def test_stac_method(egrid: str, buffer_m: float = 10):
    """Test STAC method for getting buildings"""
    print("\n" + "="*80)
    print("TEST: STAC Method")
    print("="*80)
    
    try:
        from src.building_loader import SwissBuildingLoader
        from src.terrain_with_site import fetch_boundary_by_egrid
        
        loader = SwissBuildingLoader()
        
        # Get site boundary
        site_boundary, metadata = fetch_boundary_by_egrid(egrid)
        if site_boundary is None:
            raise ValueError(f"No boundary found for EGRID {egrid}")
        bounds = site_boundary.bounds
        bbox = (
            bounds[0] - buffer_m,
            bounds[1] - buffer_m,
            bounds[2] + buffer_m,
            bounds[3] + buffer_m
        )
        
        print(f"  BBOX: {bbox}")
        
        start_time = time.time()
        tiles = loader.get_buildings_stac(bbox, limit=100)
        elapsed = time.time() - start_time
        
        print(f"\n✅ STAC Results:")
        print(f"   Time: {elapsed:.2f}s")
        print(f"   Tiles found: {len(tiles)}")
        
        # Note: STAC returns tiles, not individual buildings yet
        # This would require downloading and parsing tiles
        print(f"   ⚠️  Note: STAC returns tiles, not individual buildings")
        print(f"   ⚠️  Tile parsing not yet implemented")
        
        if tiles:
            print(f"\n   Sample tile info:")
            tile = tiles[0]
            print(f"     ID: {tile.get('id', 'N/A')}")
            print(f"     BBOX: {tile.get('bbox', 'N/A')}")
            if 'assets' in tile:
                print(f"     Assets: {list(tile['assets'].keys())}")
        
        return {
            "method": "STAC",
            "success": True,
            "time": elapsed,
            "tiles": tiles,
            "tile_count": len(tiles),
            "note": "Returns tiles, not individual buildings"
        }
        
    except Exception as e:
        print(f"\n❌ STAC Failed: {e}")
        logger.exception("STAC test failed")
        return {
            "method": "STAC",
            "success": False,
            "error": str(e),
            "time": 0,
            "tiles": []
        }


def test_geoadmin_identify(egrid: str, buffer_m: float = 10):
    """Test GeoAdmin Identify API"""
    print("\n" + "="*80)
    print("TEST: GeoAdmin Identify API")
    print("="*80)
    
    try:
        import requests
        from src.terrain_with_site import fetch_boundary_by_egrid
        
        # Get site boundary
        site_boundary, metadata = fetch_boundary_by_egrid(egrid)
        if site_boundary is None:
            raise ValueError(f"No boundary found for EGRID {egrid}")
        bounds = site_boundary.bounds
        center_x = (bounds[0] + bounds[2]) / 2
        center_y = (bounds[1] + bounds[3]) / 2
        
        print(f"  Center point: ({center_x}, {center_y})")
        
        url = "https://api3.geo.admin.ch/rest/services/api/MapServer/identify"
        params = {
            "geometryType": "esriGeometryPoint",
            "geometry": f"{center_x},{center_y}",
            "layers": "all:ch.swisstopo.swissbuildings3d_3_0-beta",
            "mapExtent": f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}",
            "imageDisplay": "1000,1000,96",
            "tolerance": 50,
            "returnGeometry": "true",
            "geometryFormat": "geojson",
            "sr": "2056"
        }
        
        start_time = time.time()
        response = requests.get(url, params=params, timeout=30)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            num_buildings = len(data.get("results", []))
            
            print(f"\n✅ GeoAdmin Identify Results:")
            print(f"   Time: {elapsed:.2f}s")
            print(f"   Buildings found: {num_buildings}")
            
            return {
                "method": "GeoAdmin Identify",
                "success": True,
                "time": elapsed,
                "buildings_count": num_buildings
            }
        else:
            print(f"\n❌ GeoAdmin Identify Failed: Status {response.status_code}")
            return {
                "method": "GeoAdmin Identify",
                "success": False,
                "error": f"Status {response.status_code}",
                "time": elapsed
            }
            
    except Exception as e:
        print(f"\n❌ GeoAdmin Identify Failed: {e}")
        logger.exception("GeoAdmin Identify test failed")
        return {
            "method": "GeoAdmin Identify",
            "success": False,
            "error": str(e),
            "time": 0
        }


def test_geoadmin_find(egrid: str, buffer_m: float = 10):
    """Test GeoAdmin Find API"""
    print("\n" + "="*80)
    print("TEST: GeoAdmin Find API")
    print("="*80)
    
    try:
        import requests
        from src.terrain_with_site import fetch_boundary_by_egrid
        
        # Get site boundary
        site_boundary, metadata = fetch_boundary_by_egrid(egrid)
        if site_boundary is None:
            raise ValueError(f"No boundary found for EGRID {egrid}")
        bounds = site_boundary.bounds
        bbox = (
            bounds[0] - buffer_m,
            bounds[1] - buffer_m,
            bounds[2] + buffer_m,
            bounds[3] + buffer_m
        )
        
        url = "https://api3.geo.admin.ch/rest/services/ech/MapServer/find"
        params = {
            "layer": "ch.swisstopo.swissbuildings3d_3_0",
            "searchText": "*",
            "searchField": "id",
            "returnGeometry": "true",
            "geometryFormat": "geojson",
            "sr": "2056",
            "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "limit": 100
        }
        
        start_time = time.time()
        response = requests.get(url, params=params, timeout=30)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            num_buildings = len(data.get("results", []))
            
            print(f"\n✅ GeoAdmin Find Results:")
            print(f"   Time: {elapsed:.2f}s")
            print(f"   Buildings found: {num_buildings}")
            
            return {
                "method": "GeoAdmin Find",
                "success": True,
                "time": elapsed,
                "buildings_count": num_buildings
            }
        else:
            print(f"\n❌ GeoAdmin Find Failed: Status {response.status_code}")
            return {
                "method": "GeoAdmin Find",
                "success": False,
                "error": f"Status {response.status_code}",
                "time": elapsed
            }
            
    except Exception as e:
        print(f"\n❌ GeoAdmin Find Failed: {e}")
        logger.exception("GeoAdmin Find test failed")
        return {
            "method": "GeoAdmin Find",
            "success": False,
            "error": str(e),
            "time": 0
        }


def main():
    """Run all building method tests"""
    print("\n" + "="*80)
    print("🏗️  COMPREHENSIVE BUILDING RETRIEVAL METHOD TEST")
    print("="*80)
    
    egrid = "CH999979659148"  # Test EGRID
    buffer_m = 10.0
    
    print(f"\n📍 EGRID: {egrid}")
    print(f"📍 Buffer: {buffer_m}m")
    
    results = []
    
    # Test all methods - REST API first as it's the recommended one
    results.append(test_rest_method(egrid, buffer_m))
    results.append(test_stac_method(egrid, buffer_m))
    results.append(test_wfs_method(egrid, buffer_m))  # Known to be disabled
    results.append(test_geoadmin_identify(egrid, buffer_m))
    results.append(test_geoadmin_find(egrid, buffer_m))
    
    # Print summary
    print("\n" + "="*80)
    print("📊 COMPARISON SUMMARY")
    print("="*80)
    
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    
    if successful:
        print("\n✅ Successful Methods:\n")
        for result in successful:
            method = result["method"]
            time_taken = result.get("time", 0)
            
            if "buildings" in result:
                count = result["stats"].get("count", 0)
                print(f"  {method:25s} | Time: {time_taken:6.2f}s | Buildings: {count:4d}")
            elif "tile_count" in result:
                count = result["tile_count"]
                print(f"  {method:25s} | Time: {time_taken:6.2f}s | Tiles: {count:4d} (⚠️  tiles, not buildings)")
            elif "buildings_count" in result:
                count = result["buildings_count"]
                print(f"  {method:25s} | Time: {time_taken:6.2f}s | Buildings: {count:4d}")
    
    if failed:
        print("\n❌ Failed Methods:\n")
        for result in failed:
            method = result["method"]
            error = result.get("error", "Unknown error")
            print(f"  {method:25s} | Error: {error}")
    
    # Recommendations
    print("\n" + "="*80)
    print("💡 RECOMMENDATIONS")
    print("="*80)
    
    if successful:
        # Find best method for actual buildings
        building_methods = [r for r in successful if "buildings" in r or "buildings_count" in r]
        if building_methods:
            best = min(building_methods, key=lambda x: x.get("time", float('inf')))
            print(f"\n🚀 Best method for buildings: {best['method']}")
            print(f"   Time: {best.get('time', 0):.2f}s")
            
            if "buildings" in best:
                print(f"   Buildings found: {best['stats'].get('count', 0)}")
            elif "buildings_count" in best:
                print(f"   Buildings found: {best['buildings_count']}")
    
    print("\n" + "="*80)
    
    # Return success if at least one method worked
    return len(successful) > 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

