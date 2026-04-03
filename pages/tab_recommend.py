import streamlit as st
import pandas as pd


def render(trade_df: pd.DataFrame, rent_df: pd.DataFrame, filters: dict, fmt_price):
    st.subheader("종합 추천")
    st.caption("실거래 데이터 기반 객관적 지표 스코어링입니다. 투자 판단은 본인의 책임입니다.")

    rcol1, rcol2 = st.columns(2)
    with rcol1:
        예산_min = st.number_input("최소 예산 (만원)", min_value=0, value=50000, step=5000,
                                  format="%d", key="rec_min")
    with rcol2:
        예산_max = st.number_input("최대 예산 (만원)", min_value=0, value=70000, step=5000,
                                  format="%d", key="rec_max")

    st.markdown(f"**예산 범위: {fmt_price(예산_min)} ~ {fmt_price(예산_max)}**")

    budget_df = trade_df.copy()
    apt_avg = budget_df.groupby("아파트")["매매가"].mean().reset_index(name="평균매매가")
    budget_apts = apt_avg[(apt_avg["평균매매가"] >= 예산_min) & (apt_avg["평균매매가"] <= 예산_max)]

    if budget_apts.empty:
        st.warning(f"해당 예산 범위({fmt_price(예산_min)}~{fmt_price(예산_max)})에 맞는 아파트가 없습니다.")
        return

    target_names = budget_apts["아파트"].tolist()
    target_trades = budget_df[budget_df["아파트"].isin(target_names)]

    # ── 지표 계산 ─────────────────────────────────────────────────
    score_df = budget_apts[["아파트", "평균매매가"]].copy()

    # 1) 평당가
    pyeong = target_trades.groupby("아파트")["평당가"].mean().reset_index(name="평당가")
    score_df = score_df.merge(pyeong, on="아파트", how="left")

    # 2) 전고점 대비
    all_max = target_trades.groupby("아파트")["매매가"].max().reset_index(name="전고점")
    last_m = target_trades["년월"].max()
    last_avg = (target_trades[target_trades["년월"] == last_m]
                .groupby("아파트")["매매가"].mean().reset_index(name="최근가"))
    peak = all_max.merge(last_avg, on="아파트")
    peak["전고점대비"] = ((peak["최근가"] / peak["전고점"] - 1) * 100).round(1)
    score_df = score_df.merge(peak[["아파트", "전고점대비"]], on="아파트", how="left")

    # 3) 거래량
    vol_score = target_trades.groupby("아파트").size().reset_index(name="거래건수")
    score_df = score_df.merge(vol_score, on="아파트", how="left")

    # 4) 수익률
    fm = target_trades["년월"].min()
    lm = target_trades["년월"].max()
    first_avg = (target_trades[target_trades["년월"] == fm]
                 .groupby("아파트")["매매가"].mean().reset_index(name="시작가"))
    last_avg2 = (target_trades[target_trades["년월"] == lm]
                 .groupby("아파트")["매매가"].mean().reset_index(name="최근가2"))
    ret = first_avg.merge(last_avg2, on="아파트")
    ret["수익률"] = ((ret["최근가2"] / ret["시작가"] - 1) * 100).round(1)
    score_df = score_df.merge(ret[["아파트", "수익률"]], on="아파트", how="left")

    # 5) 전세가율
    if not rent_df.empty:
        r_avg = rent_df[rent_df["아파트"].isin(target_names)].groupby("아파트")["전세가"].mean().reset_index(name="평균전세가")
        jeonse = score_df[["아파트", "평균매매가"]].merge(r_avg, on="아파트", how="left")
        jeonse["전세가율"] = (jeonse["평균전세가"] / jeonse["평균매매가"] * 100).round(1)
        score_df = score_df.merge(jeonse[["아파트", "전세가율"]], on="아파트", how="left")
    else:
        score_df["전세가율"] = None

    score_df = score_df.fillna(0)

    # ── 스코어링 ──────────────────────────────────────────────────
    def normalize(series, reverse=False):
        s = series.astype(float)
        mn, mx = s.min(), s.max()
        if mx == mn:
            return pd.Series([0.5] * len(s), index=s.index)
        norm = (s - mn) / (mx - mn)
        return (1 - norm) if reverse else norm

    score_df["S_평당가"] = normalize(score_df["평당가"], reverse=True) * 25
    score_df["S_전고점"] = normalize(score_df["전고점대비"], reverse=True) * 20
    score_df["S_거래량"] = normalize(score_df["거래건수"], reverse=False) * 15
    score_df["S_수익률"] = normalize(score_df["수익률"], reverse=False) * 20

    if score_df["전세가율"].sum() > 0:
        score_df["S_전세가율"] = normalize(score_df["전세가율"], reverse=True) * 20
    else:
        score_df["S_전세가율"] = 10.0

    score_df["종합점수"] = (
        score_df["S_평당가"] + score_df["S_전고점"] + score_df["S_거래량"]
        + score_df["S_수익률"] + score_df["S_전세가율"]
    ).round(1)

    score_df = score_df.sort_values("종합점수", ascending=False)

    with st.expander("스코어링 기준 (100점 만점)", expanded=False):
        st.markdown("""
| 지표 | 배점 | 방향 | 설명 |
|------|------|------|------|
| **평당가** | 25점 | 낮을수록 높은 점수 | 같은 예산에 더 넓은 면적 = 가성비 |
| **전고점 대비** | 20점 | 낮을수록 높은 점수 | 전고점 대비 많이 빠진 = 저평가 가능성 |
| **수익률 추이** | 20점 | 높을수록 높은 점수 | 조회 기간 내 가격 상승세 |
| **전세가율** | 20점 | 낮을수록 높은 점수 | 전세가율 낮으면 안전 (갭투자 리스크 낮음) |
| **거래량** | 15점 | 많을수록 높은 점수 | 거래 활발 = 유동성 확보, 매도 용이 |
""")

    st.markdown(f"### 추천 결과 (총 {len(score_df)}개 단지)")

    top3 = score_df.head(3)
    medal = ["1위", "2위", "3위"]
    cols = st.columns(min(len(top3), 3))
    for i, (_, row) in enumerate(top3.iterrows()):
        with cols[i]:
            st.markdown(f"**{medal[i]}**")
            st.metric(row["아파트"], f"{row['종합점수']:.0f}점")
            st.caption(
                f"평균 {fmt_price(row['평균매매가'])}\n\n"
                f"평당가 {row['평당가']:,.0f}만\n\n"
                f"전고점대비 {row['전고점대비']:+.1f}%\n\n"
                f"수익률 {row['수익률']:+.1f}%"
            )

    st.divider()

    st.subheader("전체 랭킹")
    display_score = score_df.assign(
        평균매매가=score_df["평균매매가"].apply(fmt_price),
        평당가=score_df["평당가"].apply(lambda x: f"{x:,.0f}만원"),
        전고점대비=score_df["전고점대비"].apply(lambda x: f"{x:+.1f}%"),
        수익률=score_df["수익률"].apply(lambda x: f"{x:+.1f}%"),
        전세가율=score_df["전세가율"].apply(lambda x: f"{x:.1f}%" if x > 0 else "-"),
        종합점수=score_df["종합점수"].apply(lambda x: f"{x:.0f}점"),
    )[["아파트", "평균매매가", "평당가", "전고점대비", "수익률", "전세가율", "거래건수", "종합점수"]]
    st.dataframe(display_score, use_container_width=True, hide_index=True)
