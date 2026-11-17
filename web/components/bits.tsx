import type { GoodsScore, Signal } from "@/lib/data";

/** 핫지수 0~100 막대. 가운데 눈금 = 50(평소 수준). */
export function HotMeter({ value }: { value: number }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className="meter" role="img" aria-label={`핫지수 ${v}점 (50점이 평소 수준)`}>
      <span style={{ width: `${v}%` }} />
      <i />
    </div>
  );
}

/** 어제 대비: 순위 ▲▼ + 핫지수 증감. 처음 등장하면 NEW. */
export function changeText(s: Pick<GoodsScore, "rankChange" | "indexChange">): string {
  if (s.rankChange === null) return "NEW";
  const rc = s.rankChange;
  const ic = s.indexChange ?? 0;
  const idx = ic === 0 ? "점수 그대로" : `${ic > 0 ? "+" : ""}${ic}점`;
  if (rc === 0) return idx;                        // 순위 변동 없음 → 점수 변화만
  return `${rc > 0 ? `▲${rc}` : `▼${-rc}`}위 · ${idx}`;
}

/** 핫지수에 가장 크게 영향을 준 신호 n개 */
export function topReasons(signals: Record<string, Signal>, n = 2): Signal[] {
  return Object.values(signals)
    .filter((s) => Math.round(s.points ?? 0) !== 0)
    .sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
    .slice(0, n);
}

export function reasonText(signals: Record<string, Signal>): string {
  const r = topReasons(signals);
  if (!r.length) return "아직 비교할 데이터가 부족해요";
  return r.map((s) => `${s.label} ${s.points > 0 ? "+" : ""}${Math.round(s.points)}`).join(" · ");
}
