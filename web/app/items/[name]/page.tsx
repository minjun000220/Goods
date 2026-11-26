import { notFound } from "next/navigation";
import DetailView from "@/components/DetailView";
import { getItemHistory, getItemScore, getLatestDate } from "@/lib/data";

export const dynamic = "force-dynamic";

function decode(s: string) {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return { title: `${decode(name)} · 주목 아이템 · 굿즈 트렌드` };
}

export default async function ItemDetail({ params }: { params: Promise<{ name: string }> }) {
  const item = decode((await params).name);
  const asOf = await getLatestDate();
  if (!asOf) notFound();
  const [score, history] = await Promise.all([getItemScore(asOf, item), getItemHistory(item)]);
  if (!score) notFound();
  return (
    <DetailView
      name={item}
      asOf={asOf}
      score={score}
      history={history}
      note="👀 주목 아이템 — 굿즈 종류와 같은 잣대로 계산한 점수예요. 이 아이템은 해당 굿즈 종류(예: 인형) 점수에도 함께 포함돼요."
    />
  );
}
