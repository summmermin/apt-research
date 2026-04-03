import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd


def render(trade_df: pd.DataFrame, filters: dict):
    시도 = filters["시도"]
    구군 = filters["구군"]

    st.subheader(f"{시도} {구군} 월별 거래량 추이")
    st.caption("거래량은 가격보다 먼저 움직이는 선행지표입니다. 급증 → 상승 신호 / 급감 → 관망세")

    vol = (
        trade_df.groupby("년월")["매매가"]
        .agg(거래건수="count", 평균가="mean")
        .reset_index()
        .sort_values("년월")
    )
    vol["년월표시"] = vol["년월"].apply(lambda x: f"{x[:4]}.{x[4:]}")
    vol["전월대비"] = vol["거래건수"].pct_change().fillna(0) * 100

    fig_vol = go.Figure()
    fig_vol.add_trace(go.Bar(
        x=vol["년월표시"], y=vol["거래건수"],
        name="거래건수",
        marker_color=vol["전월대비"].apply(
            lambda x: "salmon" if x < 0 else "steelblue"
        ).tolist(),
        yaxis="y",
    ))
    fig_vol.add_trace(go.Scatter(
        x=vol["년월표시"], y=vol["평균가"],
        name="평균 매매가",
        line=dict(color="orange", width=2),
        yaxis="y2",
    ))
    fig_vol.update_layout(
        title="거래량 vs 평균 매매가",
        yaxis=dict(title="거래건수", side="left"),
        yaxis2=dict(title="평균 매매가 (만원)", overlaying="y", side="right", tickformat=","),
        hovermode="x unified",
        height=420,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_vol, use_container_width=True)

    if len(vol) >= 2:
        최근 = vol.iloc[-1]
        이전 = vol.iloc[-2]
        변화 = 최근["거래건수"] - 이전["거래건수"]
        변화율 = (변화 / 이전["거래건수"] * 100) if 이전["거래건수"] > 0 else 0

        vcol1, vcol2, vcol3, vcol4 = st.columns(4)
        vcol1.metric("최근월 거래건수", f"{int(최근['거래건수'])}건",
                     delta=f"{변화:+.0f}건 ({변화율:+.1f}%)")
        vcol2.metric("전체 평균 거래건수", f"{vol['거래건수'].mean():.0f}건/월")
        vcol3.metric("최다 거래월", f"{vol.loc[vol['거래건수'].idxmax(), '년월표시']}")
        vcol4.metric("최소 거래월", f"{vol.loc[vol['거래건수'].idxmin(), '년월표시']}")

    st.divider()

    st.subheader("월별 거래량 전월 대비 변화율")
    fig_chg = px.bar(
        vol[1:], x="년월표시", y="전월대비",
        color="전월대비",
        color_continuous_scale=["red", "white", "blue"],
        range_color=[-100, 100],
        labels={"전월대비": "변화율 (%)"},
    )
    fig_chg.add_hline(y=0, line_color="gray")
    fig_chg.update_layout(height=300, coloraxis_showscale=False)
    st.plotly_chart(fig_chg, use_container_width=True)
