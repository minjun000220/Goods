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
st.caption(f"기준일: {data['as_of']}")
if not data["items"]:
    st.info("데이터가 없습니다. 먼저 파이프라인을 실행하세요.")
    st.stop()

df = pd.DataFrame([{"순위": it["rank"], "굿즈": it["goods_type"], "점수": it["score"],
                    "대표 상품": ", ".join(it["examples"]), "근거 수": it["coverage"]} for it in data["items"]])
st.dataframe(df, hide_index=True, use_container_width=True)

bursts = httpx.get(f"{API}/bursts").json()
if bursts["new_goods_type_candidates"]:
    st.warning("🆕 사전에 없는 새 굿즈 후보: "
               + ", ".join(c["keyword"] for c in bursts["new_goods_type_candidates"][:5]))

choice = st.selectbox("굿즈 상세", df["굿즈"])
item = next(it for it in data["items"] if it["goods_type"] == choice)
st.write("**왜 핫한가** (신호별 z-score)")
st.bar_chart(pd.Series({k: v["z"] for k, v in item["signals"].items()}))
tl = pd.DataFrame(httpx.get(f"{API}/goods/{choice}/timeline").json()["timeline"]).set_index("date")
c1, c2 = st.columns(2)
c1.line_chart(tl[["best_share"]])
c2.line_chart(tl[["mentions", "resale_listings"]])
