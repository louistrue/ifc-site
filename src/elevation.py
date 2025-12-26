"""
Elevation fetching utilities

Fetches elevation data from Swiss geo.admin.ch height service.
"""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple


def _fetch_single_elevation(coord: Tuple[float, float]) -> float:
    """
    Fetch elevation for a single coordinate.
    
    Args:
        coord: Tuple of (x, y) coordinates
        
    Returns:
        Elevation value or None on failure
    """
    x, y = coord
    url = "https://api3.geo.admin.ch/rest/services/height"
    try:
        res = requests.get(url, params={"easting": x, "northing": y, "sr": "2056"}, timeout=10)
        res.raise_for_status()
        h = float(res.json()["height"])
        return h
    except Exception:
        return None


def fetch_elevation_batch(coords: List[Tuple[float, float]], batch_size: int = 50, 
                          delay: float = 0.1, max_workers: int = 15) -> List[float]:
    """
    Fetch elevations for a list of coordinates via geo.admin.ch REST height service.
    Uses concurrent requests for faster processing.
    
    Args:
        coords: List of (x, y) coordinate tuples
        batch_size: Progress reporting interval (deprecated, kept for compatibility)
        delay: Delay between batches (deprecated, kept for compatibility)
        max_workers: Number of concurrent workers (default: 15)
        
    Returns:
        List of elevations in same order as coords
    """
    total = len(coords)
    elevations = [None] * total
    failed_count = 0
    
    print(f"Fetching elevations for {total} points (concurrent, {max_workers} workers)...")
    
    # Use ThreadPoolExecutor for concurrent requests
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_index = {
            executor.submit(_fetch_single_elevation, coord): i 
            for i, coord in enumerate(coords)
        }
        
        completed = 0
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                elevation = future.result()
                if elevation is not None:
                    elevations[index] = elevation
                else:
                    failed_count += 1
                    elevations[index] = None
            except Exception:
                failed_count += 1
                elevations[index] = None
            
            completed += 1
            if completed % batch_size == 0:
                pct = completed / total * 100
                print(f"  Progress: {completed}/{total} ({pct:.1f}%)")
    
    # Post-processing: replace None values with nearest previous non-None value (or 0.0)
    for i in range(total):
        if elevations[i] is None:
            fallback_value = 0.0
            for j in range(i - 1, -1, -1):
                if elevations[j] is not None:
                    fallback_value = elevations[j]
                    break
            elevations[i] = fallback_value
    
    if failed_count > 0:
        print(f"  Warning: {failed_count} points failed to fetch elevation")
    
    return elevations

