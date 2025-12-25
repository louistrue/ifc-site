# Swiss Site Boundaries & Terrain to IFC Converter

Convert Swiss cadastral parcels into comprehensive 3D IFC (Industry Foundation Classes) models with terrain, site boundaries, and buildings. Fetches data from Swiss geo.admin.ch APIs and generates georeferenced IFC files for BIM applications.

## Features

- **Cadastral boundaries** - Fetch Swiss parcels via EGRID from geo.admin.ch
- **3D terrain generation** - Circular terrain mesh with precise site cutout
- **Building footprints & 3D models** - Load buildings from Swiss APIs (CityGML, Vector 25k)
- **Road network data** - Load Swiss road and transportation network from swissTLM3D
- **Vegetation & forest data** - Load trees, forests, and vegetation from swissTLM3D
- **Complete BIM models** - Site + terrain + buildings + roads + vegetation in georeferenced IFC
- **IFC4 compliance** - Proper georeferencing (EPSG:2056), property sets, and schema compliance
- **FastAPI service** - RESTful API for terrain and building generation
- **Multiple workflows** - Choose terrain-only, site-only, or complete models

## Quick Start

### Installation

```bash
# Clone and navigate to the project
cd site-boundaries-geom

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Generate a Complete Site Model

Create terrain, site boundary, and buildings in one command:

```bash
python -m src.terrain_with_buildings \
  --egrid CH999979659148 \
  --radius 500 \
  --include-buildings \
  --output complete_site.ifc
```

This generates a georeferenced IFC file with:
- Circular terrain mesh (500m radius)
- Site boundary solid with cadastral metadata
- 3D building models from Swiss CityGML data

## Available Workflows

### 1. Complete Site Model (Terrain + Site + Buildings)

**Script:** `src/terrain_with_buildings.py`

Generates the most comprehensive output: terrain mesh, site solid, and 3D buildings.

```bash
python -m src.terrain_with_buildings \
  --egrid CH999979659148 \
  --radius 500 \
  --resolution 10 \
  --include-buildings \
  --building-buffer 10 \
  --output complete.ifc
```

**Key Options:**
- `--egrid` - Swiss EGRID identifier (required)
- `--radius` - Terrain radius in meters (default: 500)
- `--resolution` - Grid resolution in meters (default: 10, lower = more detail)
- `--include-buildings` - Include 3D buildings from CityGML
- `--building-buffer` - Buffer around parcel for buildings (meters)
- `--buildings-full-radius` - Include all buildings in terrain radius (not just on site)
- `--attach-to-solid` - Attach terrain to smoothed site edges (smoother transitions)

### 2. Terrain with Site (No Buildings)

**Script:** `src/terrain_with_site.py`

Creates terrain mesh with site boundary solid, without buildings.

```bash
python -m src.terrain_with_site \
  --egrid CH999979659148 \
  --radius 500 \
  --resolution 10 \
  --output terrain_site.ifc
```

**Key Options:**
- `--egrid` - Swiss EGRID identifier (required)
- `--center-x`, `--center-y` - Override terrain center (EPSG:2056)
- `--radius` - Terrain radius in meters (default: 500)
- `--resolution` - Grid resolution (default: 10m)
- `--densify` - Site boundary densification interval (default: 0.5m)
- `--attach-to-solid` - Attach terrain to site edges

### 3. Site Boundary Only

**Script:** `src/site_solid.py`

Generates only the site boundary solid with elevation, no terrain or buildings.

```bash
python -m src.site_solid \
  --egrid CH999979659148 \
  --output site.ifc
```

**Key Options:**
- `--egrid` - Swiss EGRID identifier
- `--cadastral` - Path to local cadastral file (GeoPackage/Shapefile)
- `--dem` - Path to local DEM file (GeoTIFF)
- `--densify` - Boundary densification interval (default: 0.5m)

## Building Data Integration

### Supported Building Sources

The tool supports multiple Swiss building data sources:

1. **CityGML (3D)** - Complete 3D building geometry with walls, roofs, and ground surfaces
   - Best for: Complete 3D models with accurate heights
   - Source: Swiss Buildings 3D (STAC API)
   - Format: LOD2 solids with detailed geometry

2. **Vector 25k (2D)** - Building footprints from Swiss topographic maps
   - Best for: Fast footprint queries
   - Source: swisstopo Vector 25 (REST API)
   - Format: 2D polygons

### Building Loader API

Load buildings programmatically:

```python
from src.building_loader import SwissBuildingLoader, get_buildings_around_egrid

# Method 1: Load buildings by EGRID
buildings, stats = get_buildings_around_egrid(
    egrid="CH999979659148",
    buffer_m=10  # Include buildings within 10m of parcel
)

print(f"Found {stats['count']} buildings")
print(f"Total footprint area: {stats['total_footprint_area_m2']:.1f} m²")

# Method 2: Load buildings by bounding box
from src.building_loader import get_buildings_in_bbox

bbox = (2682500, 1247500, 2683000, 1248000)  # EPSG:2056
buildings, stats = get_buildings_in_bbox(bbox, method="rest")

# Method 3: Load 3D buildings from CityGML
loader = SwissBuildingLoader()
buildings_3d = loader.get_buildings_3d(bbox, max_tiles=1)

for building in buildings_3d:
    print(f"Building {building.id}:")
    print(f"  Height: {building.height:.1f}m")
    print(f"  Footprint area: {building.geometry.area:.1f}m²")
```

### Building Statistics

The loader provides comprehensive statistics:

```python
stats = loader.get_building_statistics(buildings)
# Returns:
# {
#   'count': 42,
#   'total_footprint_area_m2': 12543.2,
#   'avg_footprint_area_m2': 298.6,
#   'avg_height_m': 8.5,
#   'max_height_m': 24.3,
#   'min_height_m': 3.2,
#   'buildings_with_height': 38
# }
```

## Road Network Integration

### Supported Road Data Sources

The tool supports Swiss road and transportation network data:

1. **swissTLM3D Roads** - Complete road and path network
   - Source: Swiss Topographic Landscape Model
   - Format: Line geometry with classification and attributes
   - Coverage: Switzerland and Liechtenstein

2. **Vector 25k Roads** - Topographic road representation
   - Source: swisstopo Vector 25
   - Format: Simplified road network

3. **Main Roads Network** - Highway and main road network
   - Source: ASTRA (Federal Roads Office)
   - Format: Major road corridors

### Road Loader API

Load roads programmatically:

```python
from src.road_loader import SwissRoadLoader, get_roads_around_egrid

# Method 1: Load roads by EGRID
roads, stats = get_roads_around_egrid(
    egrid="CH999979659148",
    buffer_m=10  # Include roads within 10m of parcel
)

print(f"Found {stats['count']} roads")
print(f"Total length: {stats['total_length_m']:.1f} m")
print(f"Road classes: {stats['road_classes']}")

# Method 2: Load roads by bounding box
from src.road_loader import get_roads_in_bbox

bbox = (2682500, 1247500, 2683000, 1248000)  # EPSG:2056
roads, stats = get_roads_in_bbox(bbox)

# Method 3: Load roads around a point
loader = SwissRoadLoader()
roads = loader.get_roads_around_point(x=2683000, y=1248000, radius=500)

for road in roads:
    print(f"Road {road.id}:")
    print(f"  Class: {road.road_class}")
    print(f"  Name: {road.name or 'Unnamed'}")
    print(f"  Length: {road.geometry.length:.1f}m")
```

### Road Classification

Swiss roads are classified into categories:
- **Autobahn** - Highway/Motorway
- **Autostrasse** - Expressway
- **Hauptstrasse** - Main road
- **Nebenstrasse** - Secondary road
- **Verbindungsstrasse** - Connecting road
- **Gemeindestrasse** - Local road
- **Privatstrasse** - Private road
- **Weg** - Path/Track
- **Fussweg** - Footpath

## Vegetation and Forest Data

### Supported Vegetation Data Sources

The tool supports Swiss vegetation and forest data:

1. **swissTLM3D Forest** - Forest polygons with classification
   - Best for: Forest areas, tree cover analysis
   - Source: Swiss Topographic Landscape Model
   - Format: Polygon geometry with type classification
   - Types: Forest, Sparse forest, Bush forest

2. **Vegetation 3D** - 3D vegetation objects
   - Best for: Individual trees and vegetation features
   - Source: swisstopo 3D data
   - Format: Point/polygon with height data

3. **Vegetation Health Index** - Satellite-based vegetation monitoring
   - Best for: Current vegetation health status
   - Source: swissEO satellite observations
   - Format: Raster with vegetation indices

### Vegetation Loader API

Load vegetation programmatically:

```python
from src.vegetation_loader import SwissVegetationLoader, get_vegetation_around_egrid

# Method 1: Load vegetation by EGRID
vegetation, stats = get_vegetation_around_egrid(
    egrid="CH999979659148",
    buffer_m=10  # Include vegetation within 10m of parcel
)

print(f"Found {stats['count']} vegetation features")
print(f"Total canopy area: {stats['total_canopy_area_m2']:.1f} m²")
print(f"Average height: {stats['avg_height_m']:.1f} m")

# Method 2: Load vegetation by bounding box
from src.vegetation_loader import get_vegetation_in_bbox

bbox = (2682500, 1247500, 2683000, 1248000)  # EPSG:2056
vegetation, stats = get_vegetation_in_bbox(bbox)

# Method 3: Load vegetation around a point
loader = SwissVegetationLoader()
vegetation = loader.get_vegetation_around_point(x=2683000, y=1248000, radius=500)

for veg in vegetation:
    print(f"Vegetation {veg.id}:")
    print(f"  Type: {veg.vegetation_type}")
    print(f"  Height: {veg.height:.1f}m" if veg.height else "  Height: Unknown")
    print(f"  Canopy area: {veg.canopy_area:.1f}m²" if veg.canopy_area else "")
```

### Vegetation Types

Swiss vegetation is classified into types:
- **Forest** (Wald) - Dense forest areas
- **Sparse forest** (Wald_offen) - Open forest with lower density
- **Bush forest** (Buschwald) - Shrubland and bushes
- **Individual tree** (Einzelbaum) - Single trees
- **Row of trees** (Baumreihe) - Linear tree arrangements
- **Hedge** (Hecke) - Hedgerows
- **Scrubland** (Gebueschwald) - Mixed scrub vegetation

## FastAPI Service

Run the terrain and building generation service as a REST API:

### Starting the Service

```bash
uvicorn src.rest_api:app --host 0.0.0.0 --port 8000
```

### API Endpoints

- `GET /health` - Service health check
- `POST /generate` - Generate and stream IFC file immediately
- `POST /jobs` - Start background generation job
- `GET /jobs/{job_id}` - Check job status
- `GET /jobs/{job_id}/download` - Download completed IFC file

### Example Requests

**Immediate generation:**
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -o site.ifc \
  -d '{
    "egrid": "CH999979659148",
    "radius": 500,
    "resolution": 10,
    "include_buildings": true
  }'
```

**Background job:**
```bash
# Start job
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "egrid": "CH999979659148",
    "radius": 500,
    "include_buildings": true
  }' | jq -r .job_id)

# Check status
curl http://localhost:8000/jobs/$JOB_ID

# Download when ready
curl -o site.ifc http://localhost:8000/jobs/$JOB_ID/download
```

## How It Works

### Workflow Overview

1. **Boundary Fetching**
   - Fetches cadastral polygon via geo.admin.ch API using EGRID
   - Extracts metadata (parcel number, canton, area, perimeter)
   - Calculates site centroid

2. **Terrain Generation**
   - Creates circular grid around site centroid
   - Fetches elevation data from Swiss height API
   - Generates Delaunay triangulation
   - Creates precise cutout for site boundary

3. **Site Solid Creation**
   - Samples elevations along site boundary
   - Applies smoothing algorithm (best-fit plane + circular mean filter)
   - Creates closed solid with triangulated surfaces

4. **Building Integration** (if enabled)
   - Queries building APIs within site bounds or terrain radius
   - Downloads CityGML tiles with complete 3D geometry
   - Filters buildings to search area
   - Converts to IFC building elements

5. **IFC Generation**
   - Creates georeferenced IFC4 file (EPSG:2056)
   - Adds terrain mesh as IfcGeographicElement
   - Adds site solid with property sets
   - Adds buildings as IfcBuilding with 3D geometry
   - Maps all metadata to IFC schema

### Terrain Smoothing

Multi-step smoothing process to reduce noise while preserving slope:

1. Calculate best-fit plane using least squares
2. Apply circular mean filter to elevations (window: 9)
3. Compute residuals (smoothed - plane)
4. Smooth residuals with circular mean filter
5. Attenuate residuals to 20%
6. Final elevation: `plane + 0.2 * smoothed_residuals`

### Coordinate Systems

- **Input/Output:** EPSG:2056 (Swiss LV95 / CH1903+)
- **Vertical Datum:** LN02 (Swiss height system)
- **Units:** Meters (SI)
- **Project Origin:** Site centroid rounded to nearest 100m

## IFC Schema Compliance

### Standard Property Sets

**Pset_LandRegistration:**
- `LandID` - Parcel number
- `LandTitleID` - EGRID identifier
- `IsPermanentID` - EGRID permanence flag

**Pset_SiteCommon:**
- `Reference` - Local identifier
- `TotalArea` - Site area in m²
- `BuildableArea` - Maximum buildable area in m²

**Pset_BuildingCommon** (for buildings):
- `Reference` - Building identifier
- `YearOfConstruction` - Construction year
- `GrossPlannedArea` - Building footprint area

**Qto_SiteBaseQuantities:**
- `GrossArea` - Total site area
- `GrossPerimeter` - Site perimeter

**CPset_SwissCadastre** (custom):
- `GeoportalURL` - Canton geoportal link
- `Canton` - Canton abbreviation
- `ParcelNumber` - Parcel number

### IFC Structure

```
IfcProject
└── IfcSite
    ├── Representation: FootPrint (2D polyline)
    ├── Property Sets: Pset_LandRegistration, Pset_SiteCommon, etc.
    ├── IfcGeographicElement (Surrounding_Terrain)
    │   ├── PredefinedType: TERRAIN
    │   └── Representation: Body (ShellBasedSurfaceModel)
    ├── IfcGeographicElement (Site_Solid)
    │   ├── PredefinedType: TERRAIN
    │   └── Representation: Body (FacetedBrep)
    └── IfcBuilding (for each building)
        ├── Representation: Body (FacetedBrep or Tessellation)
        ├── Representation: FootPrint (2D polygon)
        └── Property Sets: Pset_BuildingCommon
```

## Performance & Optimization

### Terrain Generation

- **500m radius @ 10m resolution:** ~2000 points, ~3-4 minutes
- **500m radius @ 20m resolution:** ~500 points, ~1 minute
- **Recommendation:** Use 15-25m resolution for faster processing
- **Detail:** Use 2-5m resolution for high-detail terrain

### Building Loading

**CityGML 3D (Recommended):**
- Download: ~14MB per tile, 10-30 seconds
- Processing: Fast (Fiona/GDAL)
- Output: Complete LOD2 geometry with walls and roofs

**Vector 25k (Fast):**
- Download: Instant (REST API)
- Processing: Very fast
- Output: 2D footprints only

**Tip:** Use `--buildings-on-site-only` to load only buildings on the parcel for faster processing.

### Rate Limiting

The building loader includes automatic rate limiting (5 requests/second) to prevent API abuse.

## Troubleshooting

### API Rate Limits

If you encounter elevation API rate limiting:
- Use larger `--resolution` values (20-30m)
- Increase `--densify` interval (2.0m or higher)
- Reduce terrain `--radius`
- Use local DEM file with `--dem` flag (site_solid.py only)

### Building Loading Fails

If building download fails:
- Check network connectivity
- Verify EGRID exists in cadastral database
- Try without buildings: remove `--include-buildings` flag
- Check logs for specific error messages

### Invalid Geometry

If you see geometry warnings:
- The tool attempts automatic fixes with `buffer(0)`
- Check source cadastral data for self-intersections
- Increase `--densify` value for smoother boundaries

### Python Version

Ensure Python 3.9 or higher:
```bash
python --version
```

## Data Sources

### Swiss Federal Geoportal (geo.admin.ch)

- **Cadastral boundaries:** geo.admin.ch REST API
- **Elevation data:** Swiss height API (LN02)
- **Buildings (Vector 25k):** swisstopo topographic maps
- **Buildings (3D):** Swiss Buildings 3D STAC API
- **CityGML:** LOD2 building models with complete geometry
- **Roads (swissTLM3D):** Swiss Topographic Landscape Model road network
- **Roads (Vector 25k):** Topographic road representation
- **Roads (Main network):** ASTRA main roads network
- **Vegetation (swissTLM3D):** Forest polygons and vegetation areas
- **Vegetation (3D):** 3D vegetation objects and individual trees
- **Vegetation Health:** SwissEO satellite-based vegetation monitoring

### API Endpoints

- Cadastral: `https://api3.geo.admin.ch/rest/services/api/MapServer/identify`
- Height: `https://api3.geo.admin.ch/rest/services/height`
- Buildings REST: `https://api3.geo.admin.ch/rest/services/api/MapServer/identify`
- Buildings STAC: `https://data.geo.admin.ch/api/stac/v1`
- Roads: `https://api3.geo.admin.ch/rest/services/api/MapServer/identify`
- Vegetation: `https://api3.geo.admin.ch/rest/services/api/MapServer/identify`

### Available Layers

- `ch.swisstopo.swissbuildings3d_3_0` - 3D building models (STAC)
- `ch.swisstopo.vec25-gebaeude` - Building footprints (REST)
- `ch.swisstopo.swisstlm3d-strassen` - Complete road network (REST)
- `ch.swisstopo.vec25-strassennetz` - Vector 25k roads (REST)
- `ch.astra.hauptstrassennetz` - Main roads network (REST)
- `ch.swisstopo.swisstlm3d-wald` - Forest areas (REST)
- `ch.swisstopo.vegetation.3d` - 3D vegetation objects (3D Tiles)
- `ch.swisstopo.swisseo_vhi_v100` - Vegetation Health Index (Raster)

## Docker Deployment

See `docs/DEPLOYMENT.md` for containerized deployment instructions.

## Testing

Run the test suite:

```bash
# Install test dependencies (included in requirements.txt)
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Run specific test module
pytest tests/test_api.py
```

## Output

Generated IFC files contain:
- Georeferenced site boundaries (EPSG:2056)
- 3D terrain geometry (surface mesh with cutout)
- 3D building models (complete LOD2 solids)
- Comprehensive metadata (cadastral, building attributes)
- IFC4 compliance for major viewers (BlenderBIM, Solibri, etc.)

## References

- [geo.admin.ch API](https://api3.geo.admin.ch/)
- [IFC4 Schema](https://www.buildingsmart.org/standards/bsi-standards/industry-foundation-classes-ifc/)
- [Swiss LV95 Coordinate System](https://www.swisstopo.admin.ch/en/knowledge-facts/surveying-geodesy/reference-systems/switzerland.html)
- [Swiss Buildings 3D](https://www.swisstopo.admin.ch/en/geodata/landscape/buildings3d2.html)
- [swissTLM3D Topographic Landscape Model](https://www.swisstopo.admin.ch/en/landscape-model-swisstlm3d)
- [swissTLM3D Roads and Tracks](https://opendata.swiss/en/dataset/swisstlm3d-strassen-und-wege)
- [swissTLM3D Forest](https://opendata.swiss/en/dataset/swisstlm3d-wald)
- [buildingSMART Property Sets](https://www.buildingsmart.org/standards/bsi-standards/ifc-library/)

## License

See LICENSE file for details.
