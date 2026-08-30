const HRRR_RADIUS_METERS = 6_371_229;
const DEGREES = Math.PI / 180;
const ORIGIN_LATITUDE = 38.5 * DEGREES;
const STANDARD_PARALLEL = 38.5 * DEGREES;
const ORIGIN_LONGITUDE = -97.5 * DEGREES;
const CONE = Math.sin(STANDARD_PARALLEL);
const SCALE = Math.cos(STANDARD_PARALLEL) *
  Math.tan(Math.PI / 4 + STANDARD_PARALLEL / 2) ** CONE / CONE;
const ORIGIN_RHO = HRRR_RADIUS_METERS * SCALE /
  Math.tan(Math.PI / 4 + ORIGIN_LATITUDE / 2) ** CONE;

export const HRRR_GRID = Object.freeze({
  xOriginMeters: -2697520.1425219304,
  yOriginMeters: -1587306.1525566636,
  spacingMeters: 3000,
  yPoints: 1059,
  xPoints: 1799,
  forecastPeriods: 48,
  chunkSide: 150,
});

export type ProjectedStation = {
  indexX: number;
  indexY: number;
  chunk: string;
};

export function projectStation(
  latitude: number,
  longitude: number,
): ProjectedStation {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    throw new Error("Station coordinates must be finite.");
  }
  const phi = latitude * DEGREES;
  const lambda = longitude * DEGREES;
  const rho = HRRR_RADIUS_METERS * SCALE /
    Math.tan(Math.PI / 4 + phi / 2) ** CONE;
  const theta = CONE * (lambda - ORIGIN_LONGITUDE);
  const x = rho * Math.sin(theta);
  const y = ORIGIN_RHO - rho * Math.cos(theta);
  const indexX = Math.round(
    (x - HRRR_GRID.xOriginMeters) / HRRR_GRID.spacingMeters,
  );
  const indexY = Math.round(
    (y - HRRR_GRID.yOriginMeters) / HRRR_GRID.spacingMeters,
  );
  if (
    indexX < 0 || indexX >= HRRR_GRID.xPoints || indexY < 0 ||
    indexY >= HRRR_GRID.yPoints
  ) {
    throw new Error("Projected station lies outside the exact HRRR grid.");
  }
  return {
    indexX,
    indexY,
    chunk: `0.${Math.floor(indexY / HRRR_GRID.chunkSide)}.${
      Math.floor(indexX / HRRR_GRID.chunkSide)
    }`,
  };
}

export function inverseGridPoint(
  indexY: number,
  indexX: number,
): { latitude: number; longitude: number } {
  if (
    !Number.isInteger(indexY) || !Number.isInteger(indexX) || indexY < 0 ||
    indexY >= HRRR_GRID.yPoints ||
    indexX < 0 || indexX >= HRRR_GRID.xPoints
  ) {
    throw new Error("HRRR grid indexes are outside the exact grid.");
  }
  const x = HRRR_GRID.xOriginMeters + indexX * HRRR_GRID.spacingMeters;
  const y = HRRR_GRID.yOriginMeters + indexY * HRRR_GRID.spacingMeters;
  const rho = Math.hypot(x, ORIGIN_RHO - y);
  const theta = Math.atan2(x, ORIGIN_RHO - y);
  return {
    latitude: (2 * Math.atan((HRRR_RADIUS_METERS * SCALE / rho) ** (1 / CONE)) -
      Math.PI / 2) / DEGREES,
    longitude: (ORIGIN_LONGITUDE + theta / CONE) / DEGREES,
  };
}

export function validateTemperatureMetadata(metadata: unknown): void {
  const document = metadata as Record<string, unknown>;
  const entries = document?.metadata as Record<string, unknown> | undefined;
  const array = entries?.["2m_above_ground/TMP/.zarray"] as
    | Record<string, unknown>
    | undefined;
  const attributes = entries?.["2m_above_ground/TMP/.zattrs"] as
    | Record<string, unknown>
    | undefined;
  const compressor = array?.compressor as Record<string, unknown> | undefined;
  if (
    document?.zarr_consolidated_format !== 1 || array?.zarr_format !== 2 ||
    array?.dtype !== "<f4" ||
    JSON.stringify(array?.shape) !== JSON.stringify([48, 1059, 1799]) ||
    JSON.stringify(array?.chunks) !== JSON.stringify([48, 150, 150]) ||
    array?.order !== "C" ||
    compressor?.id !== "blosc" || compressor?.cname !== "lz4" ||
    compressor?.shuffle !== 1 ||
    attributes?.long_name !== "2m_above_ground/TMP" || attributes?.units !== "K"
  ) {
    throw new Error(
      "Zarr metadata is outside the exact admitted transport identity.",
    );
  }
}

export function readTemperatureKelvin(
  decodedChunk: Uint8Array,
  forecastPeriod: number,
  indexY: number,
  indexX: number,
): number {
  const expectedBytes = HRRR_GRID.forecastPeriods * HRRR_GRID.chunkSide *
    HRRR_GRID.chunkSide * 4;
  if (decodedChunk.length !== expectedBytes) {
    throw new Error("Decoded HRRR temperature chunk has the wrong size.");
  }
  if (
    !Number.isInteger(forecastPeriod) || forecastPeriod < 1 ||
    forecastPeriod > HRRR_GRID.forecastPeriods
  ) {
    throw new Error(
      "Forecast period is outside the exact 1 through 48 identity.",
    );
  }
  if (
    !Number.isInteger(indexY) || !Number.isInteger(indexX) || indexY < 0 ||
    indexY >= HRRR_GRID.yPoints ||
    indexX < 0 || indexX >= HRRR_GRID.xPoints
  ) {
    throw new Error("HRRR grid indexes are outside the exact grid.");
  }
  const offset = (((forecastPeriod - 1) * HRRR_GRID.chunkSide +
        indexY % HRRR_GRID.chunkSide) *
      HRRR_GRID.chunkSide + indexX % HRRR_GRID.chunkSide) * 4;
  const value = new DataView(
    decodedChunk.buffer,
    decodedChunk.byteOffset,
    decodedChunk.byteLength,
  )
    .getFloat32(offset, true);
  if (!Number.isFinite(value)) {
    throw new Error("Decoded HRRR temperature is not finite.");
  }
  return value;
}

function uint32(view: DataView, offset: number): number {
  return view.getUint32(offset, true);
}

function decodeLz4Block(input: Uint8Array, expectedBytes: number): Uint8Array {
  const output = new Uint8Array(expectedBytes);
  let source = 0;
  let target = 0;
  const extendedLength = (initial: number): number => {
    let length = initial;
    if (initial !== 15) return length;
    while (true) {
      if (source >= input.length) {
        throw new Error("Truncated LZ4 extended length.");
      }
      const next = input[source++];
      length += next;
      if (next !== 255) return length;
    }
  };
  while (source < input.length) {
    const token = input[source++];
    const literalLength = extendedLength(token >>> 4);
    if (
      source + literalLength > input.length ||
      target + literalLength > output.length
    ) {
      throw new Error("LZ4 literal exceeds its bounded buffer.");
    }
    output.set(input.subarray(source, source + literalLength), target);
    source += literalLength;
    target += literalLength;
    if (source === input.length) break;
    if (source + 2 > input.length) {
      throw new Error("Truncated LZ4 match offset.");
    }
    const matchOffset = input[source] | (input[source + 1] << 8);
    source += 2;
    if (matchOffset === 0 || matchOffset > target) {
      throw new Error("Invalid LZ4 match offset.");
    }
    const matchLength = extendedLength(token & 0x0f) + 4;
    if (target + matchLength > output.length) {
      throw new Error("LZ4 match exceeds its bounded output.");
    }
    for (let index = 0; index < matchLength; index += 1) {
      output[target + index] = output[target - matchOffset + index];
    }
    target += matchLength;
  }
  if (target !== output.length) {
    throw new Error(`LZ4 decoded ${target}; expected ${output.length}.`);
  }
  return output;
}

function unshuffle(input: Uint8Array, typesize: number): Uint8Array {
  if (input.length % typesize !== 0) {
    throw new Error("Shuffled block is not aligned to its type size.");
  }
  const elements = input.length / typesize;
  const output = new Uint8Array(input.length);
  for (let byte = 0; byte < typesize; byte += 1) {
    for (let element = 0; element < elements; element += 1) {
      output[element * typesize + byte] = input[byte * elements + element];
    }
  }
  return output;
}

export function decodeBloscLz4(input: Uint8Array): Uint8Array {
  if (input.length < 16) {
    throw new Error("Blosc chunk is shorter than its header.");
  }
  const view = new DataView(input.buffer, input.byteOffset, input.byteLength);
  const version = input[0];
  const codecVersion = input[1];
  const flags = input[2];
  const typesize = input[3];
  const decodedBytes = uint32(view, 4);
  const blocksize = uint32(view, 8);
  const compressedBytes = uint32(view, 12);
  if (
    version !== 2 || codecVersion !== 1 || typesize < 1 || blocksize < 1 ||
    decodedBytes < 1
  ) {
    throw new Error("Unsupported Blosc/LZ4 header identity.");
  }
  if (compressedBytes !== input.length || decodedBytes % typesize !== 0) {
    throw new Error("Blosc size identity is inconsistent.");
  }
  const compressorFormat = (flags & 0xe0) >>> 5;
  if (
    compressorFormat !== 1 || (flags & 0x02) !== 0 || (flags & 0x04) !== 0 ||
    (flags & 0x01) === 0
  ) {
    throw new Error("Only compressed byte-shuffled Blosc chunks are admitted.");
  }
  const blocks = Math.ceil(decodedBytes / blocksize);
  const startsOffset = 16;
  if (startsOffset + blocks * 4 > input.length) {
    throw new Error("Blosc block table is truncated.");
  }
  const output = new Uint8Array(decodedBytes);
  let outputOffset = 0;
  for (let block = 0; block < blocks; block += 1) {
    const start = uint32(view, startsOffset + block * 4);
    const end = block + 1 < blocks
      ? uint32(view, startsOffset + (block + 1) * 4)
      : compressedBytes;
    if (start + 4 > end || end > input.length) {
      throw new Error("Blosc block boundary is malformed.");
    }
    const expectedBlockBytes = Math.min(blocksize, decodedBytes - outputOffset);
    const isLeftover = expectedBlockBytes !== blocksize;
    const splits = (flags & 0x10) === 0 && !isLeftover && typesize <= 16 &&
        blocksize / typesize >= 128
      ? typesize
      : 1;
    const bytesPerSplit = expectedBlockBytes / splits;
    if (!Number.isInteger(bytesPerSplit)) {
      throw new Error("Blosc split is not element-aligned.");
    }
    const shuffled = new Uint8Array(expectedBlockBytes);
    let compressedOffset = start;
    for (let split = 0; split < splits; split += 1) {
      if (compressedOffset + 4 > end) {
        throw new Error("Blosc split length is truncated.");
      }
      const compressedSplitBytes = uint32(view, compressedOffset);
      compressedOffset += 4;
      if (
        compressedSplitBytes < 1 ||
        compressedOffset + compressedSplitBytes > end
      ) {
        throw new Error("Blosc split boundary is malformed.");
      }
      const compressed = input.subarray(
        compressedOffset,
        compressedOffset + compressedSplitBytes,
      );
      const decoded = compressedSplitBytes === bytesPerSplit
        ? compressed
        : decodeLz4Block(compressed, bytesPerSplit);
      shuffled.set(decoded, split * bytesPerSplit);
      compressedOffset += compressedSplitBytes;
    }
    if (compressedOffset !== end) {
      throw new Error("Blosc block has unconsumed bytes.");
    }
    output.set(unshuffle(shuffled, typesize), outputOffset);
    outputOffset += expectedBlockBytes;
  }
  if (outputOffset !== decodedBytes) {
    throw new Error("Blosc output is incomplete.");
  }
  return output;
}
