import {
  decodeBloscLz4,
  inverseGridPoint,
  projectStation,
  readTemperatureKelvin,
  validateTemperatureMetadata,
} from "./hrrr_zarr_transport.ts";

const ORIGIN = "https://hrrrzarr.s3.amazonaws.com";
const RUN_DATE = "2026-08-29";
const RUN_HOUR = 12;
const RUN = "20260829_12z_fcst.zarr";
const BASE = `${ORIGIN}/sfc/20260829/${RUN}/2m_above_ground/TMP`;
const STEPS = Object.freeze([18, 21, 24, 27, 30, 33, 36, 39, 42]);
const MAX_REQUESTS = 19;
const STATIONS = Object.freeze([
  { station_id: "KATL", latitude: 33.640, longitude: -84.427 },
  { station_id: "KAUS", latitude: 30.194, longitude: -97.670 },
  { station_id: "KBOS", latitude: 42.365, longitude: -71.009 },
  { station_id: "KDCA", latitude: 38.852, longitude: -77.037 },
  { station_id: "KDEN", latitude: 39.856, longitude: -104.673 },
  { station_id: "KDFW", latitude: 32.899, longitude: -97.040 },
  { station_id: "KHOU", latitude: 29.646, longitude: -95.279 },
  { station_id: "KLAS", latitude: 36.084, longitude: -115.153 },
  { station_id: "KLAX", latitude: 33.942, longitude: -118.408 },
  { station_id: "KMDW", latitude: 41.786, longitude: -87.752 },
  { station_id: "KMIA", latitude: 25.795, longitude: -80.290 },
  { station_id: "KMSP", latitude: 44.884, longitude: -93.222 },
  { station_id: "KMSY", latitude: 29.993, longitude: -90.258 },
  { station_id: "KNYC", latitude: 40.783, longitude: -73.967 },
  { station_id: "KOKC", latitude: 35.393, longitude: -97.601 },
  { station_id: "KPHL", latitude: 39.874, longitude: -75.242 },
  { station_id: "KPHX", latitude: 33.435, longitude: -112.011 },
  { station_id: "KSAT", latitude: 29.533, longitude: -98.469 },
  { station_id: "KSEA", latitude: 47.450, longitude: -122.309 },
  { station_id: "KSFO", latitude: 37.619, longitude: -122.375 },
]);

type ReferenceValue = {
  station_id: string;
  grid_latitude: string;
  grid_longitude: string;
  temperature_kelvin: string;
};

class BoundedClient {
  requests = 0;

  async get(path: string): Promise<{ bytes: Uint8Array; etag: string }> {
    this.requests += 1;
    if (this.requests > MAX_REQUESTS) {
      throw new Error("Zarr cross-check exceeded its exact request budget.");
    }
    const response = await fetch(`${BASE}/${path}`, {
      headers: { "user-agent": "mimir-hrrr-zarr-crosscheck/1" },
      signal: AbortSignal.timeout(30_000),
    });
    if (response.status === 429) {
      throw new Error("Zarr transport cross-check stopped on HTTP 429.");
    }
    if (response.status !== 200) {
      throw new Error(`Zarr object ${path} returned ${response.status}.`);
    }
    return {
      bytes: new Uint8Array(await response.arrayBuffer()),
      etag: response.headers.get("etag") ?? "",
    };
  }
}

async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new Uint8Array(bytes).buffer,
  );
  return [...new Uint8Array(digest)].map((value) =>
    value.toString(16).padStart(2, "0")
  ).join("");
}

async function main(): Promise<void> {
  const referencePath = Deno.args[0];
  const outputPath = Deno.args[1];
  if (!referencePath || !outputPath || Deno.args.length !== 2) {
    throw new Error(
      "Exact reference and create-new output paths are required.",
    );
  }
  const referenceBytes = await Deno.readFile(referencePath);
  const reference = JSON.parse(new TextDecoder().decode(referenceBytes));
  if (
    reference.schema !== "hrrr_v4_current_grib_station_reference_v1" ||
    reference.research_only !== true ||
    reference.active_trading_capability_changed !== false ||
    reference.automatic_production_activation !== false ||
    reference.run_date !== RUN_DATE || reference.run_hour_utc !== RUN_HOUR ||
    reference.request_count !== 18 ||
    JSON.stringify(reference.steps_hours) !== JSON.stringify(STEPS) ||
    !Array.isArray(reference.messages) ||
    reference.messages.length !== STEPS.length ||
    reference.station_count !== STATIONS.length
  ) throw new Error("Frozen GRIB reference identity is malformed.");

  const client = new BoundedClient();
  const metadataObject = await client.get(".zmetadata");
  const metadata = JSON.parse(new TextDecoder().decode(metadataObject.bytes));
  validateTemperatureMetadata(metadata);

  const projections = new Map(STATIONS.map((station) => [
    station.station_id,
    projectStation(station.latitude, station.longitude),
  ]));
  const chunks = [
    ...new Set([...projections.values()].map((value) => value.chunk)),
  ].sort();
  if (chunks.length !== 18) {
    throw new Error(
      `Expected 18 exact station chunks; found ${chunks.length}.`,
    );
  }
  const decodedChunks = new Map<string, Uint8Array>();
  const chunkIdentities = [];
  for (const chunk of chunks) {
    const object = await client.get(`2m_above_ground/TMP/${chunk}`);
    const decoded = decodeBloscLz4(object.bytes);
    decodedChunks.set(chunk, decoded);
    chunkIdentities.push({
      chunk,
      bytes: object.bytes.length,
      etag: object.etag,
      sha256: await sha256(object.bytes),
    });
  }
  if (client.requests !== MAX_REQUESTS) {
    throw new Error("Zarr cross-check did not use its exact request budget.");
  }

  let compared = 0;
  let maximumAbsoluteDifference = 0;
  const rows = [];
  for (const message of reference.messages) {
    const step = Number(message.step_hours);
    if (
      !STEPS.includes(step) || !Array.isArray(message.values) ||
      message.values.length !== STATIONS.length
    ) {
      throw new Error("GRIB message step or station identity is malformed.");
    }
    const unique = new Set<string>();
    for (const value of message.values as ReferenceValue[]) {
      const projected = projections.get(value.station_id);
      if (!projected || unique.has(value.station_id)) {
        throw new Error(`Unknown or duplicate station ${value.station_id}.`);
      }
      unique.add(value.station_id);
      const grid = inverseGridPoint(projected.indexY, projected.indexX);
      const referenceLongitude = Number(value.grid_longitude) > 180
        ? Number(value.grid_longitude) - 360
        : Number(value.grid_longitude);
      if (
        Math.abs(grid.latitude - Number(value.grid_latitude)) > 1e-9 ||
        Math.abs(grid.longitude - referenceLongitude) > 1e-9
      ) {
        throw new Error(
          `Projected grid identity differs from ecCodes for ${value.station_id}.`,
        );
      }
      const zarr = readTemperatureKelvin(
        decodedChunks.get(projected.chunk)!,
        step,
        projected.indexY,
        projected.indexX,
      );
      const grib = Number(value.temperature_kelvin);
      const difference = Math.abs(zarr - grib);
      maximumAbsoluteDifference = Math.max(
        maximumAbsoluteDifference,
        difference,
      );
      if (!Object.is(zarr, Math.fround(grib))) {
        throw new Error(
          `Zarr differs from exact float32 GRIB for ${value.station_id} step ${step}.`,
        );
      }
      rows.push({
        station_id: value.station_id,
        step_hours: step,
        temperature_kelvin: zarr.toString(),
      });
      compared += 1;
    }
  }
  if (compared !== 180) {
    throw new Error(`Expected 180 exact comparisons; found ${compared}.`);
  }
  const report = {
    schema: "hrrr_v4_grib_zarr_exact_transport_crosscheck_v1",
    research_only: true,
    active_trading_capability_changed: false,
    automatic_production_activation: false,
    paid_provider_required: false,
    run_date: RUN_DATE,
    run_hour_utc: RUN_HOUR,
    reference_sha256: await sha256(referenceBytes),
    metadata_sha256: await sha256(metadataObject.bytes),
    metadata_etag: metadataObject.etag,
    chunks: chunkIdentities,
    requests: client.requests,
    compared_station_steps: compared,
    exact_float32_matches: compared,
    maximum_absolute_difference_kelvin: maximumAbsoluteDifference.toString(),
    passes: true,
    rows,
  };
  await Deno.writeTextFile(outputPath, `${JSON.stringify(report)}\n`, {
    createNew: true,
    mode: 0o600,
  });
  console.log(JSON.stringify({
    schema: report.schema,
    chunks: chunks.length,
    compared_station_steps: compared,
    maximum_absolute_difference_kelvin:
      report.maximum_absolute_difference_kelvin,
    passes: report.passes,
  }));
}

if (import.meta.main) await main();
