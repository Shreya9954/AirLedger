// Shared constants. Keep in sync with backend/app/constants.py.

export const AGWP_CO2 = 1.48e12;   // J per tonne CO2, 100-year absolute global warming potential
export const CO2_PER_FUEL = 3.16;  // t CO2 per t jet fuel

// Every flight track is resampled to N waypoints; cruise is C0..C1 (climb and descent excluded).
export const N = 140, C0 = 7, C1 = 133;

// Reroute options, in flight-level units (20 = 2,000 ft) so the semicircular rule holds.
export const DELTAS = [-40, -20, 0, 20, 40];
export const MIN_FL = 290;
export const FLS = [310, 320, 330, 340, 350, 360, 370, 380, 390, 400];

export const CARRIERS = [
  { code: 'NWX', name: 'Northwind Atlantic' }, { code: 'MDX', name: 'Meridian Air' },
  { code: 'STX', name: 'Saltire Airways' }, { code: 'HLX', name: 'Halcyon' }, { code: 'CVX', name: 'Corvid Cargo' }
];

// burn: t fuel per hour; f: relative contrail strength (soot and wake size); ceil: max flight level
export const TYPES = {
  B77W: { name: 'Boeing 777-300ER', burn: 7.4, f: 1.25, ceil: 410 },
  A359: { name: 'Airbus A350-900', burn: 5.8, f: 1.0, ceil: 410 },
  B789: { name: 'Boeing 787-9', burn: 5.4, f: 1.0, ceil: 410 },
  A333: { name: 'Airbus A330-300', burn: 5.7, f: 1.15, ceil: 410 },
  B38M: { name: 'Boeing 737 MAX 8', burn: 2.6, f: 0.8, ceil: 410 },
  A21N: { name: 'Airbus A321neo LR', burn: 2.5, f: 0.65, ceil: 390 },
  B763F: { name: 'Boeing 767-300F', burn: 5.1, f: 1.15, ceil: 410 }
};
export const typeName = code => TYPES[code]?.name ?? code;
