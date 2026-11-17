"use client";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="wrap">
      <div className="card empty">
        데이터를 불러오지 못했어요. (DB 연결 설정을 확인해 주세요)
        <br />
        <button onClick={reset} style={{ marginTop: 12, padding: "6px 14px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)" }}>
          다시 시도
        </button>
      </div>
    </main>
  );
}
