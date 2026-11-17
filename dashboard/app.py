"""MVP 대시보드 (Streamlit). API 서버를 먼저 띄운 뒤 실행.

  pip install -e ".[dashboard]"
  uvicorn api.main:app &
  streamlit run dashboard/app.py
"""
import os

import httpx
import pandas as pd
import streamlit as st

API = os.getenv("GOODS_API", "http://localhost:8000")

st.set_page_config(page_title="굿즈 트렌드", layout="wide")
st.title("🔥 요즘 핫한 굿즈")

data = httpx.get(f"{API}/trending").json()
if not data["items"]:
    st.info("데이터가 없습니다. 먼저 파이프라인을 실행하세요.")
    st.stop()
st.caption(f"기준일: {data['as_of']} · 핫지수 0~100 (50 = 평소 수준, 70 이상 상승, 85 이상 급상승)")


def change_text(it):
    if it.get("rank_change") is None:
        return "NEW"
    rc, ic = it["rank_change"], it.get("index_change") or 0
    arrow = "▲" if rc > 0 else ("▼" if rc < 0 else "-")
    return f"{arrow}{abs(rc) if rc else ''}  ({ic:+d}점)"


df = pd.DataFrame([{
    "순위": it["rank"], "굿즈": it["goods_type"], "핫지수": it.get("hot_index"),
    "상태": it.get("label", ""), "어제 대비": change_text(it),
    "대표 상품": ", ".join(it["examples"]), "근거 수": it["coverage"],
} for it in data["items"]])
st.dataframe(df, hide_index=True, use_container_width=True,
             column_config={"핫지수": st.column_config.ProgressColumn("핫지수", min_value=0, max_value=100, format="%d")})

bursts = httpx.get(f"{API}/bursts").json()
if bursts["new_goods_type_candidates"]:
    st.warning("🆕 사전에 없는 새 굿즈 후보: "
               + ", ".join(c["keyword"] for c in bursts["new_goods_type_candidates"][:5]))

choice = st.selectbox("굿즈 상세", df["굿즈"])
item = next(it for it in data["items"] if it["goods_type"] == choice)
m1, m2, m3 = st.columns(3)
m1.metric("핫지수", f"{item.get('hot_index', '-')}점", item.get("index_change"))
m2.metric("순위", f"{item['rank']}위", item.get("rank_change"))
m3.metric("최근 7일 언급", f"{item.get('mentions_7d', 0)}건")

left, right = st.columns(2)
with left:
    st.write("**핫지수 추이**")
    hist = httpx.get(f"{API}/goods/{choice}/scores").json().get("history", [])
    if hist:
        st.line_chart(pd.DataFrame(hist).set_index("date")[["hot_index"]])
with right:
    st.write("**왜 이 점수인가** (신호별 기여 점수)")
    st.bar_chart(pd.Series({v.get("label", k): v.get("points", 0) for k, v in item["signals"].items()}))

tl = pd.DataFrame(httpx.get(f"{API}/goods/{choice}/timeline").json()["timeline"]).set_index("date")
c1, c2 = st.columns(2)
c1.write("**베스트 순위 점유율**")
c1.line_chart(tl[["best_share"]])
c2.write("**언급량 · 리셀 매물**")
c2.line_chart(tl[["mentions", "resale_listings"]])
