import {
  decodeBloscLz4,
  HRRR_GRID,
  inverseGridPoint,
  projectStation,
  readTemperatureKelvin,
  validateTemperatureMetadata,
} from "./hrrr_zarr_transport.ts";

function assert(
  condition: unknown,
  message = "assertion failed",
): asserts condition {
  if (!condition) throw new Error(message);
}

function assertThrows(action: () => unknown, pattern: RegExp): void {
  try {
    action();
  } catch (error) {
    assert(
      error instanceof Error && pattern.test(error.message),
      `unexpected error: ${String(error)}`,
    );
    return;
  }
  throw new Error("expected action to throw");
}

function shuffled(input: Uint8Array, typesize: number): Uint8Array {
  const output = new Uint8Array(input.length);
  const elements = input.length / typesize;
  for (let byte = 0; byte < typesize; byte += 1) {
    for (let element = 0; element < elements; element += 1) {
      output[byte * elements + element] = input[element * typesize + byte];
    }
  }
  return output;
}

function literalBlosc(input: Uint8Array): Uint8Array {
  assert(input.length === 16);
  const payload = shuffled(input, 4);
  const lz4 = new Uint8Array([0xf0, 1, ...payload]);
  const output = new Uint8Array(16 + 4 + 4 + lz4.length);
  const view = new DataView(output.buffer);
  output.set([2, 1, 0x31, 4]);
  view.setUint32(4, input.length, true);
  view.setUint32(8, input.length, true);
  view.setUint32(12, output.length, true);
  view.setUint32(16, 20, true);
  view.setUint32(20, lz4.length, true);
  output.set(lz4, 24);
  return output;
}

Deno.test("Blosc LZ4 decoder reproduces byte-shuffled float storage and rejects adjacent identities", () => {
  const values = new Float32Array([270.25, 280.5, 290.75, 300]);
  const source = new Uint8Array(values.buffer.slice(0));
  const encoded = literalBlosc(source);
  const decoded = decodeBloscLz4(encoded);
  assert(decoded.length === source.length);
  assert(decoded.every((value, index) => value === source[index]));

  const wrongVersion = encoded.slice();
  wrongVersion[0] = 1;
  assertThrows(() => decodeBloscLz4(wrongVersion), /Unsupported/);
  const wrongFilter = encoded.slice();
  wrongFilter[2] |= 0x04;
  assertThrows(() => decodeBloscLz4(wrongFilter), /byte-shuffled/);
  assertThrows(
    () => decodeBloscLz4(encoded.subarray(0, encoded.length - 1)),
    /size identity/,
  );
});

Deno.test("Lambert projection reproduces the exact ecCodes KATL grid point", () => {
  const projected = projectStation(33.640, -84.427);
  const inverse = inverseGridPoint(projected.indexY, projected.indexX);
  assert(Math.abs(inverse.latitude - 33.62671858217282) < 1e-9);
  assert(Math.abs(inverse.longitude - -84.4181067096825) < 1e-9);
  assert(
    projected.chunk ===
      `0.${Math.floor(projected.indexY / 150)}.${
        Math.floor(projected.indexX / 150)
      }`,
  );
  assertThrows(() => projectStation(0, 0), /outside/);
});

Deno.test("temperature metadata admits only the exact HRRR Zarr representation", () => {
  const metadata = {
    zarr_consolidated_format: 1,
    metadata: {
      "2m_above_ground/TMP/.zarray": {
        zarr_format: 2,
        dtype: "<f4",
        shape: [48, 1059, 1799],
        chunks: [48, 150, 150],
        order: "C",
        compressor: { id: "blosc", cname: "lz4", shuffle: 1 },
      },
      "2m_above_ground/TMP/.zattrs": {
        long_name: "2m_above_ground/TMP",
        units: "K",
      },
    },
  };
  validateTemperatureMetadata(metadata);
  const drift = structuredClone(metadata);
  drift.metadata["2m_above_ground/TMP/.zarray"].compressor.shuffle = 2;
  assertThrows(() => validateTemperatureMetadata(drift), /outside the exact/);
});

Deno.test("temperature extraction binds forecast period, chunk coordinates, and finite float32", () => {
  const bytes = new Uint8Array(
    HRRR_GRID.forecastPeriods * HRRR_GRID.chunkSide * HRRR_GRID.chunkSide * 4,
  );
  const period = 42;
  const indexY = 503;
  const indexX = 987;
  const offset =
    (((period - 1) * HRRR_GRID.chunkSide + indexY % HRRR_GRID.chunkSide) *
        HRRR_GRID.chunkSide + indexX % HRRR_GRID.chunkSide) * 4;
  new DataView(bytes.buffer).setFloat32(offset, 301.125, true);
  assert(readTemperatureKelvin(bytes, period, indexY, indexX) === 301.125);
  assertThrows(
    () => readTemperatureKelvin(bytes, 0, indexY, indexX),
    /Forecast period/,
  );
  assertThrows(
    () => readTemperatureKelvin(bytes.subarray(1), period, indexY, indexX),
    /wrong size/,
  );
});
