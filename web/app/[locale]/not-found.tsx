import { Link } from "@/i18n/navigation";

export default function NotFound() {
  return (
    <main className="grid min-h-dvh place-items-center p-6">
      <div className="panel max-w-sm p-8 text-center">
        <div className="eyebrow mb-2">404</div>
        <p className="text-ink">This page does not exist.</p>
        <Link href="/" className="mt-4 inline-block text-sm text-signal underline-offset-4 hover:underline">
          Back to the dashboard
        </Link>
      </div>
    </main>
  );
}
