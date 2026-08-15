import { HttpError } from './db';

/**
 * Address -> coordinate.
 *
 * The county's own geocoder is tried first because it is authoritative for
 * Gwinnett addresses and knows about local street naming. Census is the
 * fallback: national coverage, slower, and less precise on new subdivisions.
 *
 * Both results are labelled with which one answered, because it changes how much
 * the caller should trust a point that lands near a jurisdiction line — and near
 * a line is exactly where jurisdiction is decided.
 */
export interface Geocoded {
  lon: number;
  lat: number;
  matched: string;
  geocoder: 'gwinnett-county' | 'census';
}

const COUNTY =
  'https://gis3.gwinnettcounty.com/mapvis/rest/services/Locators/GC_AddressLocationService/GeocodeServer/findAddressCandidates';
const CENSUS = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress';

export async function geocode(address: string): Promise<Geocoded> {
  const q = address.trim();
  if (!q) throw new HttpError(400, 'address is empty');

  try {
    const url = `${COUNTY}?SingleLine=${encodeURIComponent(q)}&outFields=*&outSR=4326&maxLocations=1&f=json`;
    const r = await fetch(url, { cf: { cacheTtl: 86400, cacheEverything: true } });
    if (r.ok) {
      const j: any = await r.json();
      const c = j?.candidates?.[0];
      if (c?.location) {
        return {
          lon: c.location.x, lat: c.location.y,
          matched: c.address ?? q, geocoder: 'gwinnett-county',
        };
      }
    }
  } catch {
    // fall through to Census — a county GIS outage should degrade, not fail
  }

  const url = `${CENSUS}?address=${encodeURIComponent(q)}&benchmark=Public_AR_Current&format=json`;
  const r = await fetch(url, { cf: { cacheTtl: 86400, cacheEverything: true } });
  if (!r.ok) throw new HttpError(502, `census geocoder ${r.status}`);
  const j: any = await r.json();
  const m = j?.result?.addressMatches?.[0];
  if (!m) throw new HttpError(404, `no geocoder could match "${q}"`);
  return {
    lon: m.coordinates.x, lat: m.coordinates.y,
    matched: m.matchedAddress ?? q, geocoder: 'census',
  };
}

/**
 * PIN -> parcel centroid, proxied live from the county.
 *
 * Never cached beyond a few minutes and never stored: the Gwinnett GIS licence
 * forbids redistributing their parcel geometry. We pass through a coordinate
 * derived from it to answer the question, and keep nothing.
 */
export async function pinCentroid(pin: string): Promise<Geocoded> {
  const base =
    'https://gis3.gwinnettcounty.com/mapvis/rest/services/GISDataBrowser/GC_Parcels/MapServer/0/query';
  const where = encodeURIComponent(`PIN='${pin.replace(/'/g, "''")}'`);
  const url = `${base}?where=${where}&outFields=PIN&returnGeometry=true&outSR=4326&f=json`;
  const r = await fetch(url, { cf: { cacheTtl: 300, cacheEverything: true } });
  if (!r.ok) throw new HttpError(502, `county parcel service ${r.status}`);
  const j: any = await r.json();
  const rings = j?.features?.[0]?.geometry?.rings?.[0];
  if (!rings?.length) throw new HttpError(404, `no parcel found for PIN "${pin}"`);
  let x = 0, y = 0;
  for (const [px, py] of rings) { x += px; y += py; }
  return {
    lon: x / rings.length, lat: y / rings.length,
    matched: `PIN ${pin}`, geocoder: 'gwinnett-county',
  };
}
