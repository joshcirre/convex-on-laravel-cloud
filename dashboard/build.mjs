import { createHash } from "node:crypto";
import { createWriteStream } from "node:fs";
import { mkdir, mkdtemp, rename, rm, stat } from "node:fs/promises";
import { join } from "node:path";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import { spawnSync } from "node:child_process";

// Match ../build.sh's precompiled-2026-09-26-27ef234 release.
// These are the three application layers from the official dashboard image
// ghcr.io/get-convex/convex-dashboard:27ef2346e0fea1f7e9fbfe7bfae895164c89dbec.
const repository = "get-convex/convex-dashboard";
const layers = {
  arm64: [
    "sha256:f9757899c8846f9eb7c64560006ba5e68ace1cca80c1636e62496cb220f1f105",
    "sha256:25ec5bc1e82642d6c2e52ae5f72a5c993e64eac67e6d2533abaeb19e39f98575",
    "sha256:bf7562f7a2b9386993be3705504265ccb4780e59dc9efa46a7d40e91a38a9410",
  ],
  x64: [
    "sha256:f8662ce1615d46b89da8ca678d863778a5889dc367a893eeed8b656a44366427",
    "sha256:a311db238e47490418f5cad7ca51ee12a009667570515d2562633d61c394c1a6",
    "sha256:a59e080cefe13d18bcbbbc37c674f7ad792625b68e9383d7c05b74eae773b15a",
  ],
};

async function main() {
  const selected = layers[process.arch];
  if (!selected) throw new Error(`Unsupported architecture: ${process.arch}`);

  const tokenResponse = await fetch(
    `https://ghcr.io/token?scope=repository:${repository}:pull&service=ghcr.io`,
  );
  if (!tokenResponse.ok) throw new Error(`GHCR token request failed: ${tokenResponse.status}`);
  const { token } = await tokenResponse.json();

  // Stage beside dist so the final rename also works when /tmp is a
  // separate filesystem in the build container.
  const temp = await mkdtemp(join(import.meta.dirname, ".build-"));
  const output = join(import.meta.dirname, "dist");
  try {
    for (const [index, digest] of selected.entries()) {
      const response = await fetch(`https://ghcr.io/v2/${repository}/blobs/${digest}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok || !response.body) {
        throw new Error(`Dashboard layer ${index + 1} download failed: ${response.status}`);
      }

      const archive = join(temp, `layer-${index}.tar.gz`);
      const hash = createHash("sha256");
      const chunks = Readable.fromWeb(response.body);
      chunks.on("data", (chunk) => hash.update(chunk));
      await pipeline(chunks, createWriteStream(archive));
      if (`sha256:${hash.digest("hex")}` !== digest) {
        throw new Error(`Dashboard layer ${index + 1} failed SHA-256 verification`);
      }

      const result = spawnSync("tar", ["-xzf", archive, "-C", temp, "app"], {
        stdio: "inherit",
      });
      if (result.status !== 0) throw new Error(`Dashboard layer ${index + 1} extraction failed`);
      console.log(`Verified and extracted dashboard layer ${index + 1}/${selected.length}`);
    }

    await stat(join(temp, "app", "dashboard-self-hosted", "server.js"));
    await rm(output, { recursive: true, force: true });
    await mkdir(output, { recursive: true });
    await rename(join(temp, "app"), join(output, "app"));
  } finally {
    await rm(temp, { recursive: true, force: true });
  }
}

await main();
