import SelfTest from "@/components/player/SelfTest";

export default async function SelfTestPage({
  params,
}: {
  params: Promise<{ hash: string }>;
}) {
  const { hash } = await params;
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="mb-4 text-lg font-semibold">엔진 자체 검증</h1>
      <p className="mb-6 text-sm text-neutral-500">
        실제 스템으로 오디오 그래프를 오프라인 렌더링해 검증합니다. 헤드리스 브라우저에는
        오디오 장치가 없어 실시간 재생을 확인할 수 없으므로, 결정적으로 확인 가능한
        부분을 여기서 잡습니다.
      </p>
      <SelfTest hash={hash} />
    </main>
  );
}
