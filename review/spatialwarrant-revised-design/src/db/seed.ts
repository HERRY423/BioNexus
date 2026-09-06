import { db } from "@/db";
import { claims, datasets, pluginUsages, stages, tasks } from "@/db/schema";
import { CLAIMS, DATASETS, PLUGINS, STAGES } from "@/db/seed-data";
import { sql } from "drizzle-orm";

type Executor = Parameters<Parameters<typeof db.transaction>[0]>[0] | typeof db;

export async function resetAndSeed() {
  await db.transaction(async (tx) => {
    await tx.execute(sql`select pg_advisory_xact_lock(7420251)`);
    await tx.execute(
      sql`truncate table tasks, stages, datasets, claims, plugin_usages restart identity cascade`,
    );
    await seedAll(tx);
  });
}

async function seedAll(exec: Executor) {
  const db = exec;
  for (const [i, s] of STAGES.entries()) {
    const [row] = await db
      .insert(stages)
      .values({
        code: s.code,
        order: i,
        title: s.title,
        goal: s.goal,
        plugin: s.plugin,
        tools: s.tools,
        memoryNote: s.memoryNote,
        deliverable: s.deliverable,
        screenshotHint: s.screenshotHint,
        estHours: s.estHours,
      })
      .returning({ id: stages.id });
    await db.insert(tasks).values(
      s.tasks.map((t, j) => ({
        stageId: row.id,
        order: j,
        title: t.title,
        detail: t.detail,
      })),
    );
  }

  await db.insert(datasets).values(DATASETS);
  await db.insert(claims).values(CLAIMS);
  await db.insert(pluginUsages).values(PLUGINS);
}

// Module-level lock so concurrent server-component queries never seed twice.
const globalForSeed = globalThis as typeof globalThis & {
  __spatialWarrantSeedLock?: Promise<void> | null;
};

/** Seed once if the database is empty. Safe to call concurrently from server components. */
export async function ensureSeeded() {
  if (!globalForSeed.__spatialWarrantSeedLock) {
    globalForSeed.__spatialWarrantSeedLock = (async () => {
      // Transaction-scoped advisory lock guards against multiple processes racing as well.
      await db.transaction(async (tx) => {
        await tx.execute(sql`select pg_advisory_xact_lock(7420251)`);
        const [{ count }] = await tx
          .select({ count: sql<number>`count(*)::int` })
          .from(stages);
        if (Number(count) === 0) {
          await seedAll(tx);
        }
      });
    })().catch((err) => {
      // allow a retry on the next request if seeding failed
      globalForSeed.__spatialWarrantSeedLock = null;
      throw err;
    });
  }
  await globalForSeed.__spatialWarrantSeedLock;
}
