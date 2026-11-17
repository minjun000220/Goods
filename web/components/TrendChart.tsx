"use client";

import { useEffect, useRef, useState } from "react";

type Point = { date: string; hotIndex: number };

const H = 220;
const M = { t: 14, r: 40, b: 26, l: 30 };
const md = (d: string) => d.slice(5).replace("-", "/");

/** 핫지수 추이: 단일 계열 선 차트 (2px 선, 50점 기준선, 마우스/터치 십자선 + 툴팁). */
export default function TrendChart({ data }: { data: Point[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(640);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const n = data.length;
  const iw = w - M.l - M.r;
  const ih = H - M.t - M.b;
  const x = (i: number) => M.l + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v: number) => M.t + (1 - v / 100) * ih;
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.hotIndex).toFixed(1)}`).join("");

  const pick = (clientX: number) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box || n === 0) return;
    const rel = (clientX - box.left - M.l) / iw;
    setHover(Math.max(0, Math.min(n - 1, Math.round(rel * (n - 1)))));
  };

  const last = n - 1;
  const ticks = n > 2 ? [0, Math.floor(last / 2), last] : [...Array(n).keys()];
  const h = hover !== null ? data[hover] : null;

  return (
    <div
      ref={ref}
      className="chart"
      onPointerMove={(e) => pick(e.clientX)}
      onPointerDown={(e) => pick(e.clientX)}
      onPointerLeave={() => setHover(null)}
    >
      <svg viewBox={`0 0 ${w} ${H}`} height={H} role="img" aria-label="날짜별 핫지수 추이">
        {/* 눈금: 0 / 100 은 옅게, 50(평소 수준)은 점선 기준선 */}
        {[0, 100].map((v) => (
          <g key={v}>
            <line x1={M.l} x2={w - M.r} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
            <text x={M.l - 6} y={y(v) + 4} textAnchor="end">{v}</text>
          </g>
        ))}
        <line x1={M.l} x2={w - M.r} y1={y(50)} y2={y(50)} stroke="var(--neutral)" strokeDasharray="4 4" />
        <text x={M.l - 6} y={y(50) + 4} textAnchor="end">50</text>
        <text x={w - M.r + 6} y={y(50) + 4}>평소</text>

        {ticks.map((i) => (
          <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === last ? "end" : "middle"}>
            {md(data[i].date)}
          </text>
        ))}

        {n > 1 && <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}

        {/* 마지막 값은 직접 표시 */}
        {n > 0 && (
          <g>
            <circle cx={x(last)} cy={y(data[last].hotIndex)} r={4} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />
            <text x={x(last) + 8} y={y(data[last].hotIndex) + 4} style={{ fill: "var(--text)", fontWeight: 600 }}>
              {data[last].hotIndex}
            </text>
          </g>
        )}

        {h && hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={M.t} y2={H - M.b} stroke="var(--text-3)" strokeWidth={1} />
            <circle cx={x(hover)} cy={y(h.hotIndex)} r={5} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />
          </g>
        )}
      </svg>
      {h && hover !== null && (
        <div className="tip num" style={{ left: Math.max(56, Math.min(w - 56, x(hover))), top: y(h.hotIndex) - 6 }}>
          {md(h.date)} · 핫지수 <b>{h.hotIndex}</b>
        </div>
      )}
    </div>
  );
}
