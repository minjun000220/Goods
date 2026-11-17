import type { MetadataRoute } from "next";

// 폰에서 "홈 화면에 추가" 하면 앱처럼 열리게 하는 정보
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "굿즈 트렌드",
    short_name: "굿즈 트렌드",
    description: "요즘 뜨는 굿즈 종류를 매일 핫지수로 보여줍니다.",
    start_url: "/",
    display: "standalone",
    background_color: "#f6f6f4",
    theme_color: "#f6f6f4",
    lang: "ko",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/apple-icon", sizes: "180x180", type: "image/png" },
    ],
  };
}
