import streamlit as st
import plotly.express as px
import pandas as pd


def render(trade_df: pd.DataFrame, filters: dict, fmt_price):
    시도 = filters["시도"]
    구군 = filters["구군"]

    st.subheader(f"{시도} {구군} 평당가 랭킹")
    st.caption("평당가 = 매매가 ÷ 전용면적(㎡) × 3.3058 (1평 환산)")

    pyeong_rank = (
        trade_df.groupby("아파트")
        .agg(평균평당가=("평당가", "mean"), 거래건수=("평당가", "count"),
             평균면적=("전용면적", "mean"))
        .reset_index()
        .sort_values("평균평당가", ascending=False)
    )
    pyeong_rank["평균평당가"] = pyeong_rank["평균평당가"].round(0)
    pyeong_rank["평균면적"] = pyeong_rank["평균면적"].round(1)

    # Top 10
    st.markdown("**가장 비싼 아파트 Top 10** (평당가 기준)")
    top10 = pyeong_rank.head(10)
    fig_p = px.bar(
        top10.sort_values("평균평당가"),
        x="평균평당가", y="아파트",
        orientation="h",
        text="평균평당가",
        color="평균평당가",
        color_continuous_scale="Reds",
    )
    fig_p.update_traces(texttemplate="%{text:,.0f}만원", textposition="outside")
    fig_p.update_layout(
        height=400, showlegend=False, coloraxis_showscale=False,
        xaxis_title="평당가 (만원)", yaxis_title="",
    )
    st.plotly_chart(fig_p, use_container_width=True)

    # Bottom 10
    if len(pyeong_rank) > 10:
        st.markdown("**가장 저렴한 아파트 Top 10** (평당가 기준)")
        bottom10 = pyeong_rank.tail(10)
        fig_b = px.bar(
            bottom10.sort_values("평균평당가"),
            x="평균평당가", y="아파트",
            orientation="h",
            text="평균평당가",
            color="평균평당가",
            color_continuous_scale="Blues",
        )
        fig_b.update_traces(texttemplate="%{text:,.0f}만원", textposition="outside")
        fig_b.update_layout(
            height=400, showlegend=False, coloraxis_showscale=False,
            xaxis_title="평당가 (만원)", yaxis_title="",
        )
        st.plotly_chart(fig_b, use_container_width=True)

    st.divider()

    st.subheader("전체 평당가 테이블")
    st.dataframe(
        pyeong_rank.assign(
            평균평당가=pyeong_rank["평균평당가"].apply(lambda x: f"{x:,.0f}만원"),
        )[["아파트", "평균면적", "평균평당가", "거래건수"]],
        use_container_width=True, hide_index=True,
    )
