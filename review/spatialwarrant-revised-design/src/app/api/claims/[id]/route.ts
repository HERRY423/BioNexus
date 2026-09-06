export const dynamic = "force-dynamic";

function readOnlyResponse() {
  return Response.json(
    {
      error:
        "Claim verdicts are read-only. Import a hash-bound BioNexus receipt and preserve Human Scientific Adjudication separately.",
    },
    { status: 405 },
  );
}

export async function PATCH() {
  return readOnlyResponse();
}

export async function DELETE() {
  return readOnlyResponse();
}

