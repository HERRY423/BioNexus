# SpatialWarrant revised design

This is a preserved, expanded revision of the Astra-generated
`spatial-transcriptomics-task-design`. No stage, dataset, analysis family,
claim-boundary demonstration, or screenshot concept was removed.

The revision corrects four scientific risks:

1. the primary boundary is fixed from pathology geometry before expression;
2. sections/spots are not called patients/replicates until metadata proves it;
3. Tangram, marker/NNLS, and scanpy ingest have distinct, honest roles;
4. all observed-result language starts as `PENDING` and is imported from
   evidence artifacts after execution.

Start with:

- `ANALYSIS_PLAN_LOCK.md` for the scientific contract;
- `WORKBENCH_EXECUTION_GUIDE.zh-CN.md` for the exact Workbench sequence;
- `CLAIMS_PREREGISTERED.csv` for the claim register;
- the dashboard for plan tracking and, after implementation, read-only receipt
  display.

The dashboard still requires PostgreSQL. Copy `.env.example` to `.env`,
start the database, install dependencies, push the schema, and run the app.
These steps make the planning UI runnable; they do not execute the scientific
  analysis.

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
npm install
npm run db:push
npm run db:seed
npm run dev
```

Dependency installation and the production build must be verified on the host
that will display the dashboard. They are separate from scientific execution.
