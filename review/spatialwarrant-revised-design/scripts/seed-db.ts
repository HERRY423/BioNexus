import "dotenv/config";

import { resetAndSeed } from "../src/db/seed";

await resetAndSeed();
console.log("SpatialWarrant planning database seeded.");

