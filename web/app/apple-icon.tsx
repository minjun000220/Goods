import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

// iOS 홈 화면 아이콘 (PNG 필요): 빨간 바탕 + 흰 불꽃 모양
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#e34948" }}>
        <svg width="120" height="120" viewBox="0 0 64 64">
          <path d="M33 10c2 8-6 12-6 20 0 3 2 5 4 6-1-5 3-8 5-12 5 5 9 10 9 17 0 7-6 13-13 13s-13-6-13-13c0-12 13-17 14-31z" fill="#fff" />
        </svg>
      </div>
    ),
    size,
  );
}
