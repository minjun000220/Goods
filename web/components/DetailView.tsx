import Link from "next/link";
import ContribBars from "@/components/ContribBars";
import TrendChart from "@/components/TrendChart";
import { HotMeter, changeText } from "@/components/bits";
import type { GoodsScore, HistoryPoint } from "@/lib/data";

/** 상세 화면 (굿즈 종류·주목 아이템 공용) */
export default function DetailView({ name, asOf, score, history, note }: {
  name: string; asOf: string; score: GoodsScore; history: HistoryPoint[]; note?: string;
}) {
  const goodsType = name;
  return (
    <main className="wrap">
      <Link href="/" className="back">← 전체 순위</Link>
      <header className="top">
        <h1>{goodsType} {score.label && <span className="state" style={{ verticalAlign: "middle" }}>{score.label}</span>}</h1>
        <span className="date num">{asOf} 기준</span>
      </header>
      {note && <p className="legend-line">{note}</p>}

      <div className="hero">
        <div className="card">
          <div className="k">핫지수</div>
          <div className="v num">{score.hotIndex}<small style={{ fontSize: 14, color: "var(--text-3)" }}> / 100</small></div>
          <HotMeter value={score.hotIndex} />
        </div>
        <div className="card">
          <div className="k">순위</div>
          <div className="v num">{score.rank}위</div>
          <div className="s num">{changeText(score)}</div>
        </div>
        <div className="card">
          <div className="k">7일 언급</div>
          <div className="v num">{score.mentions7d}건</div>
          <div className="s">근거 {score.coverage}개</div>
        </div>
      </div>

      <div className="detail-grid">
        <section className="card pad">
          <h2>핫지수 추이</h2>
          {history.length > 1 ? (
            <TrendChart data={history} />
          ) : (
            <p className="muted">하루치 기록만 있어요. 매일 쌓이면 추이 그래프가 그려져요.</p>
          )}
          <details className="table-view">
            <summary>표로 보기</summary>
            <table className="num">
              <thead><tr><th>날짜</th><th>핫지수</th><th>순위</th></tr></thead>
              <tbody>
                {[...history].reverse().map((h) => (
                  <tr key={h.date}><td>{h.date}</td><td>{h.hotIndex}</td><td>{h.rank}</td></tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>

        <section className="card pad">
          <h2>왜 이 점수인가</h2>
          <ContribBars signals={score.signals} />
          <p className="note">기여 점수를 모두 더하면 ‘핫지수 − 50’이에요. 각 신호는 최근 7일을 이전 28일과 비교해요.</p>
        </section>
      </div>

      {score.examples.length > 0 && (
        <section className="card pad" style={{ marginTop: 16 }}>
          <h2>요즘 순위가 높은 상품</h2>
          <ul className="examples">
            {score.examples.map((e) => <li key={e}>{e}</li>)}
          </ul>
        </section>
      )}
    </main>
  );
}
