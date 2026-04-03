import streamlit as st
import plotly.express as px
import pandas as pd


def render(trade_df: pd.DataFrame, filters: dict, fmt_price):
    st.subheader("수익률 시뮬레이터")
    st.caption("조회 기간 내 첫 거래가 → 최근 거래가 비교로 추정 수익률을 계산합니다.")

    first_month = trade_df["년월"].min()
    last_month = trade_df["년월"].max()

    first_trades = trade_df[trade_df["년월"] == first_month].groupby("아파트")["매매가"].mean().reset_index(name="시작평균가")
    last_trades = trade_df[trade_df["년월"] == last_month].groupby("아파트")["매매가"].mean().reset_index(name="최근평균가")
    profit_df = first_trades.merge(last_trades, on="아파트")
    profit_df["차이"] = profit_df["최근평균가"] - profit_df["시작평균가"]
    profit_df["수익률"] = ((profit_df["최근평균가"] / profit_df["시작평균가"] - 1) * 100).round(1)
    profit_df = profit_df.sort_values("수익률", ascending=False)

    if profit_df.empty:
        st.info("수익률 계산에 충분한 데이터가 없습니다.")
        return

    st.markdown(f"**기간: {first_month[:4]}.{first_month[4:]} → {last_month[:4]}.{last_month[4:]}**")

    scol1, scol2, scol3 = st.columns(3)
    scol1.metric("평균 수익률", f"{profit_df['수익률'].mean():+.1f}%")
    scol2.metric("최고 수익 아파트",
                 profit_df.iloc[0]["아파트"],
                 delta=f"{profit_df.iloc[0]['수익률']:+.1f}%")
    if len(profit_df) >= 2:
        worst = profit_df.iloc[-1]
        scol3.metric("최저 수익 아파트", worst["아파트"],
                     delta=f"{worst['수익률']:+.1f}%")

    st.divider()

    fig_profit = px.bar(
        profit_df, x="아파트", y="수익률",
        color="수익률",
        color_continuous_scale=["red", "white", "blue"],
        range_color=[-30, 30],
        title="아파트별 추정 수익률 (%)",
    )
    fig_profit.add_hline(y=0, line_color="gray")
    fig_profit.update_layout(height=420, xaxis_tickangle=-45, coloraxis_showscale=False)
    st.plotly_chart(fig_profit, use_container_width=True)

    st.dataframe(
        profit_df.assign(
            시작평균가=profit_df["시작평균가"].apply(fmt_price),
            최근평균가=profit_df["최근평균가"].apply(fmt_price),
            차이=profit_df["차이"].apply(lambda x: f"{'+' if x > 0 else ''}{fmt_price(x)}"),
            수익률=profit_df["수익률"].apply(lambda x: f"{x:+.1f}%"),
        )[["아파트", "시작평균가", "최근평균가", "차이", "수익률"]],
        use_container_width=True, hide_index=True,
    )

    # 투자 시뮬레이션
    st.divider()
    st.subheader("투자 시뮬레이션")
    투자금 = st.number_input("투자금액 (만원)", min_value=1000, value=50000, step=5000, format="%d")
    sim_apt = st.selectbox("아파트 선택", profit_df["아파트"].tolist())

    if sim_apt:
        row = profit_df[profit_df["아파트"] == sim_apt].iloc[0]
        예상수익 = 투자금 * row["수익률"] / 100
        st.markdown(f"""
| 항목 | 값 |
|------|-----|
| 투자금 | **{fmt_price(투자금)}** |
| 기간 | {first_month[:4]}.{first_month[4:]} → {last_month[:4]}.{last_month[4:]} |
| 수익률 | **{row['수익률']:+.1f}%** |
| 예상 수익 | **{fmt_price(abs(예상수익))}** {'이익' if 예상수익 >= 0 else '손실'} |
| 예상 총액 | **{fmt_price(투자금 + 예상수익)}** |
""")
