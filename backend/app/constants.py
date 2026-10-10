"""Shared constants. Keep in sync with frontend/js/config.js."""

AGWP_CO2_J_PER_T = 1.48e12  # 100-year absolute global warming potential of 1 t CO2, in joules
CO2_PER_FUEL = 3.16         # t CO2 per t jet fuel

N_WAYPOINTS = 140           # every track is resampled to this many points
CRUISE_START, CRUISE_END = 7, 133

DELTAS_FL = (-40, -20, 0, 20, 40)  # reroute options in flight-level units (20 = 2,000 ft)
MIN_FL = 290
WINDOW_PAD_KM = 100.0

# ICAO type designator -> display name, service ceiling (FL)
AIRCRAFT = {
    "B77W": ("Boeing 777-300ER", 410),
    "A359": ("Airbus A350-900", 410),
    "B789": ("Boeing 787-9", 410),
    "A333": ("Airbus A330-300", 410),
    "B38M": ("Boeing 737 MAX 8", 410),
    "A21N": ("Airbus A321neo", 390),
    "B763": ("Boeing 767-300", 410),
}
DEFAULT_CEILING = 410
