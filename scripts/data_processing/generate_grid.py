import numpy as np
import pandas as pd
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_ncp_grid(lat_min=32.0, lat_max=42.0, lon_min=110.0, lon_max=123.0, resolution=0.25):
    """
    Generate a grid of latitude and longitude coordinates for the North China Plain.
    
    Args:
        lat_min (float): Minimum latitude.
        lat_max (float): Maximum latitude.
        lon_min (float): Minimum longitude.
        lon_max (float): Maximum longitude.
        resolution (float): Grid resolution in degrees.
        
    Returns:
        pd.DataFrame: DataFrame containing 'latitude' and 'longitude' columns.
    """
    lats = np.arange(lat_min, lat_max + resolution, resolution)
    lons = np.arange(lon_min, lon_max + resolution, resolution)
    
    # Create a meshgrid
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    
    # Flatten the grid
    grid_points = pd.DataFrame({
        'latitude': lat_grid.flatten(),
        'longitude': lon_grid.flatten()
    })
    
    # Round coordinates to avoid floating point issues
    grid_points['latitude'] = grid_points['latitude'].round(2)
    grid_points['longitude'] = grid_points['longitude'].round(2)
    
    logging.info(f"Generated {len(grid_points)} grid points for NCP region.")
    return grid_points

if __name__ == "__main__":
    grid = generate_ncp_grid()
    print(grid.head())
    print(f"Total points: {len(grid)}")
    # Optional: Save to CSV for inspection
    # grid.to_csv("ncp_grid_points.csv", index=False)
