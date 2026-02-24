import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="text-center space-y-4">
        <p className="text-6xl font-bold text-indigo-500">404</p>
        <h1 className="text-xl font-semibold text-white">Page not found</h1>
        <p className="text-sm text-gray-400">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Link
          href="/dashboard"
          className="inline-block mt-2 rounded-lg bg-indigo-600 hover:bg-indigo-500
                     px-5 py-2.5 text-sm font-semibold text-white transition-colors"
        >
          Go to dashboard
        </Link>
      </div>
    </div>
  );
}
