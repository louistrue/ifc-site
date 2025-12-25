#!/usr/bin/env python3
"""
Address-to-EGRID Lookup Service

Converts Swiss addresses to EGRID using geo.admin.ch geocoding and cadastral APIs.
Optimized for nice UX - automatically resolves addresses to cadastral parcels.
"""

import requests
from typing import Optional, Tuple, Dict, Any
from shapely.geometry import Point, shape
import logging

logger = logging.getLogger(__name__)


class AddressResolver:
    """
    Resolves Swiss addresses to EGRID numbers via geo.admin.ch APIs.

    Usage:
        resolver = AddressResolver()
        egrid, metadata = resolver.resolve("Bundesplatz 3, 3003 Bern")
    """

    GEOCODING_API = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
    CADASTRE_API = "https://api3.geo.admin.ch/rest/services/ech/MapServer/identify"

    def __init__(self, timeout: int = 10):
        """
        Initialize address resolver.

        Args:
            timeout: Request timeout in seconds (default: 10)
        """
        self.timeout = timeout

    def geocode(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert address to EPSG:2056 coordinates using geo.admin.ch geocoding.

        Args:
            address: Swiss address string (e.g., "Bundesplatz 3, 3003 Bern")

        Returns:
            Tuple of (easting, northing) in EPSG:2056, or None if not found
        """
        params = {
            "searchText": address,
            "type": "locations",
            "sr": "2056",  # Swiss LV95 coordinate system
            "limit": 1  # Only return best match
        }

        try:
            response = requests.get(self.GEOCODING_API, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if not data.get("results") or len(data["results"]) == 0:
                logger.warning(f"No geocoding results found for address: {address}")
                return None

            result = data["results"][0]

            # Extract coordinates from result
            # geo.admin.ch returns coordinates in 'attrs' dict
            attrs = result.get("attrs", {})
            x = attrs.get("x") or attrs.get("lon")
            y = attrs.get("y") or attrs.get("lat")

            if x is None or y is None:
                logger.warning(f"Geocoding result missing coordinates for: {address}")
                return None

            easting = float(x)
            northing = float(y)

            logger.info(f"Geocoded '{address}' to E={easting:.1f}, N={northing:.1f}")
            return (easting, northing)

        except requests.RequestException as e:
            logger.error(f"Geocoding request failed: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse geocoding response: {e}")
            return None

    def lookup_egrid_at_coordinates(self, easting: float, northing: float) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Look up EGRID at given coordinates using cadastral API.

        Args:
            easting: Easting coordinate in EPSG:2056
            northing: Northing coordinate in EPSG:2056

        Returns:
            Tuple of (egrid, metadata_dict) or None if no parcel found
        """
        params = {
            "geometry": f"{easting},{northing}",
            "geometryType": "esriGeometryPoint",
            "layers": "all:ch.kantone.cadastralwebmap-farbe",
            "returnGeometry": "true",
            "geometryFormat": "geojson",
            "sr": "2056",
            "tolerance": 1  # 1 meter tolerance
        }

        try:
            response = requests.get(self.CADASTRE_API, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if not data.get("results") or len(data["results"]) == 0:
                logger.warning(f"No cadastral parcel found at E={easting:.1f}, N={northing:.1f}")
                return None

            # Get first result (parcel at this location)
            result = data["results"][0]

            # Extract EGRID from attributes
            attributes = result.get("attributes", {}) or result.get("properties", {})
            egrid = attributes.get("egris_egrid")

            if not egrid:
                logger.warning(f"Cadastral result missing EGRID at coordinates")
                return None

            # Extract geometry
            geometry = None
            if result.get("geometry"):
                geometry = shape(result["geometry"])
                area_m2 = geometry.area if geometry else None
            else:
                area_m2 = None

            # Build metadata
            metadata = {
                "egrid": egrid,
                "canton": attributes.get("ak", ""),
                "parcel_number": attributes.get("number", ""),
                "local_id": attributes.get("identnd", ""),
                "geoportal_url": attributes.get("geoportal_url", ""),
                "realestate_type": attributes.get("realestate_type", ""),
                "area_m2": round(area_m2, 2) if area_m2 else None,
                "coordinates": {
                    "easting": easting,
                    "northing": northing,
                    "sr": "EPSG:2056"
                }
            }

            logger.info(f"Found parcel EGRID={egrid} at coordinates (Canton: {metadata['canton']})")
            return (egrid, metadata)

        except requests.RequestException as e:
            logger.error(f"Cadastral lookup request failed: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse cadastral response: {e}")
            return None

    def resolve(self, address: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Resolve a Swiss address to EGRID and metadata.

        This is the main entry point - combines geocoding and cadastral lookup.

        Args:
            address: Swiss address string (e.g., "Bundesplatz 3, 3003 Bern")

        Returns:
            Tuple of (egrid, metadata_dict) or None if resolution failed

        Example:
            >>> resolver = AddressResolver()
            >>> egrid, metadata = resolver.resolve("Bundesplatz 3, 3003 Bern")
            >>> print(f"EGRID: {egrid}")
            >>> print(f"Canton: {metadata['canton']}")
        """
        # Step 1: Geocode address to coordinates
        coords = self.geocode(address)
        if coords is None:
            logger.error(f"Failed to geocode address: {address}")
            return None

        easting, northing = coords

        # Step 2: Look up EGRID at coordinates
        result = self.lookup_egrid_at_coordinates(easting, northing)
        if result is None:
            logger.error(f"Failed to find cadastral parcel at geocoded location")
            return None

        egrid, metadata = result

        # Add the original address to metadata
        metadata["input_address"] = address

        logger.info(f"Successfully resolved '{address}' to EGRID {egrid}")
        return (egrid, metadata)


def resolve_address_to_egrid(address: str) -> Optional[str]:
    """
    Convenience function to quickly resolve address to EGRID.

    Args:
        address: Swiss address string

    Returns:
        EGRID string or None if resolution failed
    """
    resolver = AddressResolver()
    result = resolver.resolve(address)
    return result[0] if result else None


# For testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.address_lookup 'Address String'")
        print("Example: python -m src.address_lookup 'Bundesplatz 3, 3003 Bern'")
        sys.exit(1)

    address = " ".join(sys.argv[1:])

    resolver = AddressResolver()
    result = resolver.resolve(address)

    if result:
        egrid, metadata = result
        print(f"\n✓ Address resolved successfully!")
        print(f"  Address: {address}")
        print(f"  EGRID: {egrid}")
        print(f"  Canton: {metadata.get('canton', 'N/A')}")
        print(f"  Parcel Number: {metadata.get('parcel_number', 'N/A')}")
        if metadata.get('area_m2'):
            print(f"  Area: {metadata['area_m2']:.1f} m²")
        print(f"  Coordinates: E={metadata['coordinates']['easting']:.1f}, N={metadata['coordinates']['northing']:.1f}")
    else:
        print(f"\n✗ Failed to resolve address: {address}")
        sys.exit(1)
