import "server-only";
import { sql } from "./db";

export type Signal = { label: string; value: number; z: number; points: number };

export type GoodsScore = {
  goodsType: string;
  rank: number;
  hotIndex: number;
  label: string;
  rankChange: number | null;   // 양수 = 순위 상승, null = 처음 등장
  indexChange: number | null;
  coverage: number;
  signals: Record<string, Signal>;
  examples: string[];
  mentions7d: number;
};

export type HistoryPoint = { date: string; hotIndex: number; rank: number };
export type Burst = { goods_type: string; recent_daily: number; baseline_daily: number; z: number };
export type NewType = { keyword: string; recent_count: number; ratio: number };

type Row = { goods_type: string; rank: number; score: number; breakdown: Record<string, unknown> };

function toScore(r: Row): GoodsScore {
  const b = r.breakdown ?? {};
  // 핫지수 도입 전 기록은 내부 점수로 환산 (분석 코드의 hot_index 와 같은 식)
  const hotIndex = typeof b.hot_index === "number" ? b.hot_index : Math.round(100 / (1 + Math.exp(-1.5 * r.score)));
  return {
    goodsType: r.goods_type,
    rank: r.rank,
    hotIndex,
    label: (b.label as string) ?? "",
    rankChange: (b.rank_change as number | null) ?? null,
    indexChange: (b.index_change as number | null) ?? null,
    coverage: (b.coverage as number) ?? 0,
    signals: (b.signals as Record<string, Signal>) ?? {},
    examples: (b.examples as string[]) ?? [],
    mentions7d: (b.mentions_7d as number) ?? 0,
  };
}

export async function getLatestDate(): Promise<string | null> {
  const [row] = await sql<{ d: string | null }[]>`select to_char(max(as_of), 'YYYY-MM-DD') as d from hot_score`;
  return row?.d ?? null;
}

export async function getRanking(asOf: string): Promise<GoodsScore[]> {
  const rows = await sql<Row[]>`
    select goods_type, rank, score, breakdown from hot_score
    where as_of = ${asOf}::date order by rank`;
  return rows.map(toScore);
}

export async function getScore(asOf: string, goodsType: string): Promise<GoodsScore | null> {
  const rows = await sql<Row[]>`
    select goods_type, rank, score, breakdown from hot_score
    where as_of = ${asOf}::date and goods_type = ${goodsType}`;
  return rows[0] ? toScore(rows[0]) : null;
}

export async function getHistory(goodsType: string, days = 60): Promise<HistoryPoint[]> {
  const rows = await sql<{ date: string; rank: number; score: number; breakdown: Record<string, unknown> }[]>`
    select to_char(as_of, 'YYYY-MM-DD') as date, rank, score, breakdown from hot_score
    where goods_type = ${goodsType} order by as_of desc limit ${days}`;
  return rows.reverse().map((r) => ({
    date: r.date,
    rank: r.rank,
    hotIndex: toScore({ goods_type: goodsType, rank: r.rank, score: r.score, breakdown: r.breakdown }).hotIndex,
  }));
}

export async function getInsight(asOf: string): Promise<{ bursts: Burst[]; newTypes: NewType[] }> {
  try {
    const rows = await sql<{ bursts: Burst[]; new_types: NewType[] }[]>`
      select bursts, new_types from daily_insight where as_of = ${asOf}::date`;
    return { bursts: rows[0]?.bursts ?? [], newTypes: rows[0]?.new_types ?? [] };
  } catch {
    return { bursts: [], newTypes: [] };      // 표가 아직 없으면 (첫 배포 직후) 비워 둔다
  }
}
