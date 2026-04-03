import streamlit as st
import plotly.graph_objects as go
import pandas as pd


def render(trade_df: pd.DataFrame, filters: dict, fmt_price):
    시도 = filters["시도"]
    구군 = filters["구군"]

    monthly = (
        trade_df.groupby("년월")["매매가"]
        .agg(평균="mean", 최저="min", 최고="max", 거래건수="count")
        .reset_index()
        .sort_values("년월")
    )
    monthly["년월표시"] = monthly["년월"].apply(lambda x: f"{x[:4]}.{x[4:]}")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=monthly["년월표시"], y=monthly["최고"],
        mode="lines", name="최고가",
        line=dict(dash="dot", color="lightcoral"), opacity=0.6,
    ))
    fig.add_trace(go.Scatter(
        x=monthly["년월표시"], y=monthly["평균"],
        mode="lines+markers", name="평균가",
        line=dict(color="steelblue", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=monthly["년월표시"], y=monthly["최저"],
        mode="lines", name="최저가",
        line=dict(dash="dot", color="lightblue"), opacity=0.6,
    ))
    fig.update_layout(
        title=f"{시도} {구군} 월별 매매가 추이 (만원)",
        yaxis_tickformat=",",
        hovermode="x unified",
        height=420,
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 요약 메트릭
    latest = monthly.iloc[-1]
    prev = monthly.iloc[-2] if len(monthly) >= 2 else latest
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "최근월 평균 매매가",
        f"{latest['평균']:,.0f}만원",
        delta=f"{latest['평균'] - prev['평균']:+,.0f}만원",
    )
    col2.metric("최근월 최고가", f"{latest['최고']:,.0f}만원")
    col3.metric("최근월 최저가", f"{latest['최저']:,.0f}만원")
    col4.metric("최근월 거래건수", f"{int(latest['거래건수'])}건")

    st.divider()

    # ── 전고점 대비 현재가 ──────────────────────────────────────────
    st.subheader("전고점 대비 현재가")
    latest_month = trade_df["년월"].max()
    latest_trades = trade_df[trade_df["년월"] == latest_month]
    apt_latest = latest_trades.groupby("아파트")["매매가"].mean().reset_index(name="최근평균가")
    apt_all_max = trade_df.groupby("아파트")["매매가"].max().reset_index(name="전고점")
    peak_df = apt_all_max.merge(apt_latest, on="아파트")
    peak_df["전고점대비"] = ((peak_df["최근평균가"] / peak_df["전고점"] - 1) * 100).round(1)
    peak_df = peak_df.sort_values("전고점대비")

    if not peak_df.empty:
        저평가 = peak_df[peak_df["전고점대비"] < -10]
        신고가 = peak_df[peak_df["전고점대비"] >= 0]

        pcol1, pcol2 = st.columns(2)
        with pcol1:
            st.markdown(f"**저평가 구간 (전고점 -10% 이하)** — {len(저평가)}개 단지")
            if not 저평가.empty:
                st.dataframe(
                    저평가.assign(
                        전고점=저평가["전고점"].apply(fmt_price),
                        최근평균가=저평가["최근평균가"].apply(fmt_price),
                        전고점대비=저평가["전고점대비"].apply(lambda x: f"{x:+.1f}%"),
                    )[["아파트", "전고점", "최근평균가", "전고점대비"]],
                    use_container_width=True, hide_index=True,
                )
            else:
                st.caption("해당 단지 없음")
        with pcol2:
            st.markdown(f"**신고가 경신 (전고점 이상)** — {len(신고가)}개 단지")
            if not 신고가.empty:
                st.dataframe(
                    신고가.sort_values("전고점대비", ascending=False).assign(
                        전고점=신고가["전고점"].apply(fmt_price),
                        최근평균가=신고가["최근평균가"].apply(fmt_price),
                        전고점대비=신고가["전고점대비"].apply(lambda x: f"{x:+.1f}%"),
                    )[["아파트", "전고점", "최근평균가", "전고점대비"]],
                    use_container_width=True, hide_index=True,
                )
            else:
                st.caption("해당 단지 없음")

    st.divider()

    # 거래 건수 Top 5
    st.subheader("거래 건수 Top 5 아파트")
    top5 = (
        trade_df.groupby("아파트")
        .agg(거래건수=("매매가", "count"), 평균매매가=("매매가", "mean"),
             최저가=("매매가", "min"), 최고가=("매매가", "max"))
        .reset_index()
        .sort_values("거래건수", ascending=False)
        .head(5)
    )
    top5_cols = st.columns(min(len(top5), 5))
    for i, (_, row) in enumerate(top5.iterrows()):
        with top5_cols[i]:
            st.metric(row["아파트"], f"{int(row['거래건수'])}건")
            st.caption(f"평균 {fmt_price(row['평균매매가'])}")

    st.divider()

    # 최근 거래 내역
    st.subheader("최근 거래 내역")
    display = (
        trade_df[["아파트", "법정동", "전용면적", "층", "매매가", "건축년도", "년월"]]
        .copy()
        .sort_values(["년월", "매매가"], ascending=[False, False])
    )
    display.insert(5, "매매가(억)", (display["매매가"] / 10000).round(2))
    st.dataframe(display, use_container_width=True, hide_index=True)
