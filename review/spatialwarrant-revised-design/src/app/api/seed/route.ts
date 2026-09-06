import { resetAndSeed } from "@/db/seed";

export const dynamic = "force-dynamic";

/** POST /api/seed — reset the blueprint to its pristine state. */
export async function POST() {
  await resetAndSeed();
  return Response.json({ ok: true });
}
