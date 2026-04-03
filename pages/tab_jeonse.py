import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def render(trade_df: pd.DataFrame, rent_df: pd.DataFrame, filters: dict, fmt_price):
    if rent_df.empty:
        st.info(
            "전세 거래 데이터가 없거나 API 미신청 상태입니다.\n\n"
            "data.go.kr 에서 **'국토교통부 아파트 전월세 자료'** API를 추가 신청해주세요."
        )
        return

    avg_trade = trade_df.groupby("아파트")["매매가"].mean().reset_index(name="평균매매가")
    avg_rent = rent_df.groupby("아파트")["전세가"].mean().reset_index(name="평균전세가")
    ratio_df = avg_trade.merge(avg_rent, on="아파트").dropna()
    ratio_df["전세가율"] = (ratio_df["평균전세가"] / ratio_df["평균매매가"] * 100).round(1)
    ratio_df = ratio_df.sort_values("전세가율", ascending=False)

    def risk_label(r):
        if r >= 70:
            return "🔴 위험"
        if r >= 60:
            return "🟡 주의"
        return "🟢 안전"
    ratio_df["위험도"] = ratio_df["전세가율"].apply(risk_label)

    with st.expander("전세가율이란? (기준 설명)", expanded=False):
        st.markdown("""
**전세가율** = 전세 보증금 / 매매가 × 100

아파트의 매매가 대비 전세가 비율로, **갭투자 리스크**를 판단하는 핵심 지표입니다.

| 구간 | 의미 | 해석 |
|------|------|------|
| **60% 미만** | 안전 | 매매가 대비 전세가가 낮아 가격 하락 시에도 보증금 회수 가능성 높음 |
| **60~70%** | 주의 | 갭이 좁아지는 구간. 시장 하락 시 역전세 가능성 있음 |
| **70% 이상** | 위험 | 매매가와 전세가 차이가 작아 소액 갭투자 많은 구간. 하락장에서 깡통전세 위험 |

**활용 팁**
- 전세가율이 **높을수록** 갭투자 비중이 높아 가격 하락 시 급매 가능성 증가
- 전세가율이 **낮을수록** 실수요 비중이 높아 가격 방어력이 상대적으로 강함
- 같은 지역 내에서 단지별 전세가율을 비교하면 투자 과열 단지를 식별할 수 있음
""")

    col1, col2, col3 = st.columns(3)
    col1.metric("평균 전세가율", f"{ratio_df['전세가율'].mean():.1f}%")
    col2.metric("위험 단지 (70%↑)", f"{(ratio_df['전세가율'] >= 70).sum()}개")
    col3.metric("안전 단지 (60%↓)", f"{(ratio_df['전세가율'] < 60).sum()}개")

    fig2 = px.bar(
        ratio_df, x="아파트", y="전세가율",
        color="전세가율",
        color_continuous_scale=["green", "yellow", "red"],
        range_color=[40, 90],
        title="아파트별 전세가율 (%)",
        labels={"전세가율": "전세가율 (%)"},
    )
    fig2.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="위험선 70%")
    fig2.add_hline(y=60, line_dash="dash", line_color="orange", annotation_text="주의선 60%")
    fig2.update_layout(height=420, xaxis_tickangle=-45, coloraxis_showscale=False)
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(
        ratio_df.assign(
            평균매매가=ratio_df["평균매매가"].apply(lambda x: f"{x:,.0f}만원"),
            평균전세가=ratio_df["평균전세가"].apply(lambda x: f"{x:,.0f}만원"),
            전세가율=ratio_df["전세가율"].apply(lambda x: f"{x:.1f}%"),
        )[["아파트", "평균매매가", "평균전세가", "전세가율", "위험도"]],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # 월별 전세가율 추이
    m_trade = trade_df.groupby("년월")["매매가"].mean().reset_index(name="평균매매가")
    m_rent = rent_df.groupby("년월")["전세가"].mean().reset_index(name="평균전세가")
    m_ratio = m_trade.merge(m_rent, on="년월")
    m_ratio["전세가율"] = (m_ratio["평균전세가"] / m_ratio["평균매매가"] * 100).round(1)
    m_ratio["년월표시"] = m_ratio["년월"].apply(lambda x: f"{x[:4]}.{x[4:]}")
    m_ratio = m_ratio.sort_values("년월")

    fig3 = go.Figure()
    fig3.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="위험선 70%")
    fig3.add_hline(y=60, line_dash="dash", line_color="orange", annotation_text="주의선 60%")
    fig3.add_trace(go.Scatter(
        x=m_ratio["년월표시"], y=m_ratio["전세가율"],
        mode="lines+markers", name="전세가율",
        line=dict(color="steelblue", width=2),
    ))
    fig3.update_layout(
        title="월별 전세가율 추이 (%)",
        yaxis_title="전세가율 (%)",
        height=380,
    )
    st.plotly_chart(fig3, use_container_width=True)
