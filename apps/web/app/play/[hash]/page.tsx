import PlayerShell from "@/components/player/PlayerShell";

export default async function PlayPage({
  params,
}: {
  params: Promise<{ hash: string }>;
}) {
  const { hash } = await params;
  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <PlayerShell hash={hash} />
    </main>
  );
}
