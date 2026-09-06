import { db } from "@/db";
import { tasks } from "@/db/schema";
import { eq } from "drizzle-orm";
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const taskId = Number(id);
  if (!Number.isFinite(taskId)) {
    return Response.json({ error: "invalid id" }, { status: 400 });
  }
  const body = (await req.json().catch(() => ({}))) as { done?: boolean };
  if (typeof body.done !== "boolean") {
    return Response.json({ error: "done must be boolean" }, { status: 400 });
  }
  const [row] = await db
    .update(tasks)
    .set({ done: body.done })
    .where(eq(tasks.id, taskId))
    .returning();
  if (!row) return Response.json({ error: "not found" }, { status: 404 });
  return Response.json(row);
}
