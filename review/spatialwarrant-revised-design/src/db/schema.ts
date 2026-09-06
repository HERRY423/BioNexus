import {
  boolean,
  integer,
  jsonb,
  pgTable,
  serial,
  text,
  timestamp,
} from "drizzle-orm/pg-core";

// Pipeline stages (S0..S7) of the SpatialWarrant project plan
export const stages = pgTable("stages", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(), // S0, S1 ...
  order: integer("order").notNull(),
  title: text("title").notNull(),
  goal: text("goal").notNull(),
  plugin: text("plugin").notNull(), // primary Rosalind plugin/tool used
  tools: jsonb("tools").$type<string[]>().notNull().default([]),
  memoryNote: text("memory_note").notNull(),
  deliverable: text("deliverable").notNull(),
  screenshotHint: text("screenshot_hint").notNull(),
  estHours: integer("est_hours").notNull().default(2),
});

export const tasks = pgTable("tasks", {
  id: serial("id").primaryKey(),
  stageId: integer("stage_id")
    .notNull()
    .references(() => stages.id, { onDelete: "cascade" }),
  order: integer("order").notNull(),
  title: text("title").notNull(),
  detail: text("detail").notNull().default(""),
  done: boolean("done").notNull().default(false),
});

export const datasets = pgTable("datasets", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  accession: text("accession").notNull(),
  sourceUrl: text("source_url").notNull(),
  modality: text("modality").notNull(), // scRNA-seq / Visium / annotation / knowledge base
  role: text("role").notNull(), // how it is used
  sizeNote: text("size_note").notNull(),
  ramNote: text("ram_note").notNull(),
  priority: text("priority").notNull().default("primary"), // primary | validation | fallback | knowledge
});

// Claim–Evidence ledger (mirrors BioNexus BNS-012)
export const claims = pgTable("claims", {
  id: serial("id").primaryKey(),
  code: text("code").notNull(),
  statement: text("statement").notNull(),
  claimClass: text("claim_class").notNull(), // descriptive | association | population_effect | mechanistic | causal | clinical
  capability: text("capability").notNull(), // BioNexus capability that audits it
  // Preregistered ceiling or TO_BE_COMPUTED. This field is never an observed verdict.
  expectedCeiling: text("expected_ceiling").notNull(),
  verdict: text("verdict").notNull().default("PENDING"), // PENDING | WARRANTED | WARRANTED_WITH_LIMITS | NOT_SUFFICIENT | REFUSED
  evidenceFacts: text("evidence_facts").notNull().default(""),
  stageCode: text("stage_code").notNull(),
  isTrap: boolean("is_trap").notNull().default(false),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

export const pluginUsages = pgTable("plugin_usages", {
  id: serial("id").primaryKey(),
  plugin: text("plugin").notNull(),
  vendor: text("vendor").notNull(),
  role: text("role").notNull(),
  howUsed: jsonb("how_used").$type<string[]>().notNull().default([]),
  proofArtifact: text("proof_artifact").notNull(),
  accent: text("accent").notNull().default("emerald"),
});

export type Stage = typeof stages.$inferSelect;
export type Task = typeof tasks.$inferSelect;
export type Dataset = typeof datasets.$inferSelect;
export type Claim = typeof claims.$inferSelect;
export type PluginUsage = typeof pluginUsages.$inferSelect;
