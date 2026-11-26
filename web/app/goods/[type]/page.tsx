import { notFound } from "next/navigation";
import DetailView from "@/components/DetailView";
import { getHistory, getLatestDate, getScore } from "@/lib/data";

export const dynamic = "force-dynamic";

function decode(s: string) {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ type: string }> }) {
  const { type } = await params;
  return { title: `${decode(type)} · 굿즈 트렌드` };
}

export default async function GoodsDetail({ params }: { params: Promise<{ type: string }> }) {
  const goodsType = decode((await params).type);
  const asOf = await getLatestDate();
  if (!asOf) notFound();
  const [score, history] = await Promise.all([getScore(asOf, goodsType), getHistory(goodsType)]);
  if (!score) notFound();

  return <DetailView name={goodsType} asOf={asOf} score={score} history={history} />;
}
