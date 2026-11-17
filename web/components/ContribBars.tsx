import type { Signal } from "@/lib/data";

/** 신호별 기여 점수: 0을 기준으로 오른쪽(빨강) = 핫지수를 올림, 왼쪽(파랑) = 내림. 값은 막대 옆에 직접 표시. */
export default function ContribBars({ signals }: { signals: Record<string, Signal> }) {
  const rows = Object.values(signals).sort((a, b) => b.points - a.points);
  if (!rows.length) return <p className="muted">아직 신호 데이터가 없어요.</p>;
  const max = Math.max(5, ...rows.map((r) => Math.abs(r.points)));

  return (
    <div>
      <div className="contrib-legend">
        <span><i style={{ background: "var(--up)" }} />핫지수를 올림</span>
        <span><i style={{ background: "var(--down)" }} />내림</span>
      </div>
      <ul className="contrib">
        {rows.map((r) => {
          const pct = (Math.abs(r.points) / max) * 50;
          const up = r.points >= 0;
          return (
            <li key={r.label} title={`${r.label}: 기여 ${r.points > 0 ? "+" : ""}${r.points}점 (다른 종류 대비 ${r.z > 0 ? "+" : ""}${r.z}σ)`}>
              <span className="c-label">{r.label}</span>
              <span className="c-track">
                <span className="c-zero" />
                <span
                  className={`c-bar ${up ? "up" : "down"}`}
                  style={up ? { left: "50%", width: `${pct}%` } : { right: "50%", width: `${pct}%` }}
                />
              </span>
              <span className="c-val num">{r.points > 0 ? "+" : ""}{Math.round(r.points)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
