import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-md border border-[var(--border)] bg-white px-6 py-12 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Org not screened yet</h1>
      <p className="mt-3 text-sm text-[var(--muted)] max-w-md mx-auto">
        This organization is in the entity-resolution goldens but hasn&apos;t been screened yet.
        Run the precache script or POST <span className="font-mono">/api/orgs/{"{id}"}/screen</span> to populate the dossier.
      </p>
      <Link
        href="/"
        className="inline-block mt-6 px-4 py-2 rounded-sm bg-[var(--accent)] text-white text-sm font-semibold hover:bg-[var(--accent-hover)]"
      >
        Back to dashboard
      </Link>
    </div>
  );
}
