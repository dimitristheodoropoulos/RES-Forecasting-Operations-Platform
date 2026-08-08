"""
scripts/download_era5_wind.py

Κατεβάζει δεδομένα ανέμου (10m u/v components) από το ERA5 reanalysis
για μια περιοχή γύρω από την Αττική, σε NetCDF format.
"""
import cdsapi

# Bounding box γύρω από την Αττική/Αθήνα: [North, West, South, East]
AREA_ATTICA = [38.5, 23.3, 37.7, 24.2]

def download_era5_wind(year="2025", month="07", days=None, output_file="data/raw/era5_wind_attica.nc"):
    if days is None:
        days = [f"{d:02d}" for d in range(1, 8)]  # πρώτη εβδομάδα του μήνα, δοκιμαστικά

    client = cdsapi.Client()
    dataset = "reanalysis-era5-single-levels"
    request = {
        "product_type": ["reanalysis"],
        "variable": [
            "10m_u_component_of_wind",
            "10m_v_component_of_wind",
        ],
        "year": [year],
        "month": [month],
        "day": days,
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": AREA_ATTICA,
        "data_format": "netcdf",
    }

    print(f"Ζητείται ERA5 data για {year}-{month}, ημέρες: {days}...")
    print("(Αυτό μπαίνει σε ουρά στο CDS — μπορεί να πάρει λίγα λεπτά έως ώρες.)")
    client.retrieve(dataset, request, output_file)
    print(f"✅ Τα δεδομένα αποθηκεύτηκαν στο '{output_file}'")


if __name__ == "__main__":
    import os
    os.makedirs("data/raw", exist_ok=True)
    download_era5_wind(
        year="2026",
        month="08",
        days=["01", "02"],
        output_file="data/raw/era5_wind_attica_recent.nc",
    )