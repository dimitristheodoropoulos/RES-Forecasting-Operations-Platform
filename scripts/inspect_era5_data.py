"""
scripts/inspect_era5_data.py

Γρήγορη επισκόπηση του κατεβασμένου ERA5 NetCDF αρχείου.
"""
import xarray as xr
import numpy as np

def inspect(filepath="data/raw/era5_wind_attica.nc"):
    ds = xr.open_dataset(filepath)

    print("=== Dataset Overview ===")
    print(ds)

    print("\n=== Διαστάσεις (dimensions) ===")
    for dim, size in ds.sizes.items():
        print(f"  {dim}: {size}")

    print("\n=== Μεταβλητές ===")
    for var in ds.data_vars:
        print(f"  {var}: {ds[var].attrs.get('long_name', 'N/A')} [{ds[var].attrs.get('units', 'N/A')}]")

    # Υπολογισμός ταχύτητας/κατεύθυνσης ανέμου από u/v components
    u = ds["u10"]
    v = ds["v10"]
    wind_speed = np.sqrt(u**2 + v**2)
    wind_direction = (180 + np.degrees(np.arctan2(u, v))) % 360

    print(f"\n=== Στατιστικά Ταχύτητας Ανέμου (m/s) ===")
    print(f"  Ελάχιστη: {float(wind_speed.min()):.2f}")
    print(f"  Μέγιστη:  {float(wind_speed.max()):.2f}")
    print(f"  Μέση:     {float(wind_speed.mean()):.2f}")

    return ds, wind_speed, wind_direction


if __name__ == "__main__":
    inspect()