import streamlit as st
from common import render_sidebar, load_data, fmt_price

st.set_page_config(page_title="아파트 시세 탐색기", layout="wide")
st.title("아파트 시세 탐색기")
st.caption("국토교통부 실거래가 기반 · 매매가 추이 & 전세가율 분석")

# ── Sidebar & Data ───────────────────────────────────────────────────
filters = render_sidebar()
trade_df, rent_df = load_data(filters)

if trade_df.empty:
    st.warning("해당 조건의 매매 거래 데이터가 없습니다.")
    st.stop()

# ── 아파트 선택 ─────────────────────────────────────────────────────
apt_list = sorted(trade_df["아파트"].unique().tolist())
selected_apts = st.multiselect(
    f"아파트 선택 — {filters['시도']} {filters['구군']} ({len(apt_list)}개 단지 검색됨, 비워두면 지역 전체)",
    apt_list,
    placeholder="아파트를 선택하면 해당 단지만 분석합니다...",
)

if selected_apts:
    trade_df = trade_df[trade_df["아파트"].isin(selected_apts)]
    if not rent_df.empty:
        rent_df = rent_df[rent_df["아파트"].isin(selected_apts)]

# session_state에 공유 데이터 저장 (페이지 간 공유)
st.session_state["trade_df"] = trade_df
st.session_state["rent_df"] = rent_df
st.session_state["filters"] = filters

# ── Tabs ─────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "매매가 분석", "평당가 비교", "거래량 분석", "전세가율 분석", "수익률 시뮬레이터", "종합 추천",
])

# 각 탭 렌더링
from pages.tab_trade import render as render_trade
from pages.tab_pyeong import render as render_pyeong
from pages.tab_volume import render as render_volume
from pages.tab_jeonse import render as render_jeonse
from pages.tab_profit import render as render_profit
from pages.tab_recommend import render as render_recommend

with tab1:
    render_trade(trade_df, filters, fmt_price)
with tab2:
    render_pyeong(trade_df, filters, fmt_price)
with tab3:
    render_volume(trade_df, filters)
with tab4:
    render_jeonse(trade_df, rent_df, filters, fmt_price)
with tab5:
    render_profit(trade_df, filters, fmt_price)
with tab6:
    render_recommend(trade_df, rent_df, filters, fmt_price)
