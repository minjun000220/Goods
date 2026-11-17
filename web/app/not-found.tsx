import Link from "next/link";

export default function NotFound() {
  return (
    <main className="wrap">
      <div className="card empty">
        해당 굿즈의 오늘 기록이 없어요.<br />
        <Link href="/" style={{ color: "var(--accent)" }}>전체 순위로 돌아가기</Link>
      </div>
    </main>
  );
}
