import Link from "next/link";
import { HotMeter, changeText, reasonText } from "@/components/bits";
import { getInsight, getItemRanking, getLatestDate, getRanking } from "@/lib/data";
import type { GoodsScore } from "@/lib/data";

function RankRows({ rows, base }: { rows: GoodsScore[]; base: string }) {
  return (
    <ol className="rank-list">
      {rows.map((r) => (
        <li key={r.goodsType}>
          <Link href={`${base}/${encodeURIComponent(r.goodsType)}`} className="rank-row">
            <span className="rank-no num">{r.rank}</span>
            <span className="rank-main">
              <span className="rank-title">
                <strong>{r.goodsType}</strong>
                {r.label && <span className="state">{r.label}</span>}
              </span>
              <div className="rank-why">{reasonText(r.signals)}</div>
              {r.examples[0] && <div className="rank-ex">예) {r.examples.slice(0, 2).join(", ")}</div>}
            </span>
            <span className="rank-side">
              <span className="idx num">{r.hotIndex}<small>점</small></span>
              <div className="change num">{changeText(r)}</div>
              <HotMeter value={r.hotIndex} />
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

export const dynamic = "force-dynamic";   // 매 요청마다 DB 에서 최신 순위를 읽는다

export default async function Home() {
  const asOf = await getLatestDate();
  if (!asOf) {
    return (
      <main className="wrap">
        <header className="top"><h1>🔥 요즘 핫한 굿즈</h1></header>
        <div className="card empty">아직 분석 결과가 없어요. 수집(GitHub Actions)이 한 번 이상 실행되면 여기에 나타나요.</div>
      </main>
    );
  }
  const [ranking, items, insight] = await Promise.all([getRanking(asOf), getItemRanking(asOf), getInsight(asOf)]);

  return (
    <main className="wrap">
      <header className="top">
        <h1>🔥 요즘 핫한 굿즈</h1>
        <span className="date num">{asOf} 기준</span>
      </header>
      <p className="legend-line">
        핫지수 0~100 · <b>50 = 평소 수준</b>, 70 이상 상승, 85 이상 급상승
      </p>

      <div className="layout">
        <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
          <section className="card" aria-label="굿즈 종류 순위">
            <RankRows rows={ranking} base="/goods" />
          </section>
          {items.length > 0 && (
            <section className="card" aria-label="주목 아이템 순위">
              <h2 style={{ padding: "14px 16px 0", margin: 0 }}>👀 주목 아이템</h2>
              <p className="note" style={{ padding: "0 16px", margin: "2px 0 0" }}>
                훈바루즈처럼 따로 추적하는 상품 라인 — 굿즈 종류와 같은 잣대의 핫지수예요.
              </p>
              <RankRows rows={items} base="/items" />
            </section>
          )}
        </div>

        <aside style={{ display: "grid", gap: 16 }}>
          <section className="card pad">
            <h2>📈 언급량 급상승</h2>
            {insight.bursts.length ? (
              <div className="chips">
                {insight.bursts.map((b) => (
                  <Link key={b.goods_type} className="chip" href={`/goods/${encodeURIComponent(b.goods_type)}`}>
                    {b.goods_type}<em className="num">하루 {Math.round(b.baseline_daily)}→{Math.round(b.recent_daily)}건</em>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="muted">평소보다 크게 늘어난 굿즈가 없어요.</p>
            )}
          </section>
          <section className="card pad">
            <h2>🆕 새로 뜨는 단어</h2>
            {insight.newTypes.length ? (
              <div className="chips">
                {insight.newTypes.slice(0, 12).map((t) => (
                  <span key={t.keyword} className="chip">{t.keyword}<em className="num">{t.recent_count}</em></span>
                ))}
              </div>
            ) : (
              <p className="muted">아직 없어요.</p>
            )}
            <p className="note">사전에 없는 단어 중 갑자기 많이 나온 것 — 새 굿즈 종류 후보예요.</p>
          </section>
        </aside>
      </div>
    </main>
  );
}
