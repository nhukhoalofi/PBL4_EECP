import Link from "next/link";
import { SessionList } from "@/features/exam-sessions";

export const dynamic = "force-dynamic";

export default function SessionsPage() {
  return (
    <main className="page-shell">
      <header className="hero sessions-hero">
        <div>
          <p className="eyebrow">Control Server</p>
          <h1>Exam Sessions</h1>
          <p>Create, prepare, run, and finish managed exam sessions.</p>
        </div>
        <Link className="sessions-primary-link" href="/sessions/create">
          Create session
        </Link>
      </header>
      <SessionList />
    </main>
  );
}
