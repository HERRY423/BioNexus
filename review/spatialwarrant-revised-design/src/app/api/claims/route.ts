import { getClaims } from "@/lib/queries";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(await getClaims());
}

export async function POST() {
  return Response.json(
    {
      error:
        "Claim creation is disabled in the evidence view. Update the preregistration before execution or import a hash-bound receipt after execution.",
    },
    { status: 405, headers: { Allow: "GET" } },
  );
}

