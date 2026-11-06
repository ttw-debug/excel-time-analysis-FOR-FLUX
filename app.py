import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io

# 1. 頁面配置
st.set_page_config(page_title="通量系統資料分析", layout="wide")
st.title("📈 通量系統資料分析")
st.caption("支援一次上傳整月通量數據檔案，自動合併日期時間、識別物理單位、繪製長期趨勢圖與 ET 每日累積儀表板。")

# 內建常見通量與環境監測參數標準單位對照表
DEFAULT_UNITS = {
    "et": "mm",
    "co2_mole_fraction": "µmol/mol (ppm)",
    "h2o_mole_fraction": "mmol/mol",
    "ch4_mole_fraction": "µmol/mol",
    "co2_flux": "µmol m⁻² s⁻¹",
    "h2o_flux": "mmol m⁻² s⁻¹",
    "ch4_flux": "µmol m⁻² s⁻¹",
    "le": "W m⁻²",
    "h": "W m⁻²",
    "rn": "W m⁻²",
    "g": "W m⁻²",
    "air_temperature": "K / °C",
    "air_pressure": "Pa",
    "wind_speed": "m s⁻¹",
    "max_wind_speed": "m s⁻¹",
    "wind_dir": "° (deg)",
    "u*": "m s⁻¹",
    "rh": "%",
    "vpd": "Pa",
    "sonic_temperature": "K",
    "co2_mixing_ratio": "µmol/mol",
    "h2o_mixing_ratio": "mmol/mol",
}

def extract_units(df, default_dict):
    """從資料表前幾列自動偵測單位列（如 [W+1m-2]），若無則套用預設單位字典"""
    unit_map = {}
    unit_row_idx = None

    for idx in range(min(3, len(df))):
        row_vals = df.iloc[idx].astype(str).str.strip()
        bracket_count = sum(
            val.startswith('[') and val.endswith(']') 
            for val in row_vals if val not in ['nan', 'None', '']
        )
        if bracket_count >= 2:
            unit_row_idx = idx
            break

    for col in df.columns:
        if col == "_source_file":
            continue
        unit_str = ""
        if unit_row_idx is not None:
            raw_u = str(df.iloc[unit_row_idx][col]).strip()
            if raw_u not in ['nan', 'None', '', '[-]']:
                unit_str = raw_u.strip('[]')
        
        if not unit_str:
            col_lower = col.lower().strip()
            if col_lower in default_dict:
                unit_str = default_dict[col_lower]

        unit_map[col] = unit_str

    return unit_map

# 2. 多檔案上傳元件
uploaded_files = st.file_uploader(
    "請選取或框選拖曳整月份的所有檔案（可一次選取數十個檔案）：",
    type=["xlsx", "xls", "csv", "txt"],
    accept_multiple_files=True
)

if uploaded_files:
    df_list = []
    error_files = []

    with st.status(f"正在批次解析 {len(uploaded_files)} 份檔案...", expanded=False) as status:
        for file in uploaded_files:
            try:
                if file.name.endswith(('.xlsx', '.xls')):
                    temp_df = pd.read_excel(file)
                else:
                    temp_df = pd.read_csv(file, sep=None, engine='python')
                
                temp_df["_source_file"] = file.name
                df_list.append(temp_df)
            except Exception as e:
                error_files.append((file.name, str(e)))

        if error_files:
            st.warning(f"⚠️ 共有 {len(error_files)} 份檔案讀取失敗並已跳過。")
        status.update(label=f"✅ 成功載入 {len(df_list)} 份檔案！", state="complete")

    if df_list:
        unit_map = extract_units(df_list[0], DEFAULT_UNITS)
        raw_df = pd.concat(df_list, ignore_index=True)

        # 自動偵測並合併 date 與 time 欄位
        col_map = {c.lower().strip(): c for c in raw_df.columns}
        if 'date' in col_map and 'time' in col_map:
            d_col = col_map['date']
            t_col = col_map['time']
            combined_series = raw_df[d_col].astype(str).str.strip() + " " + raw_df[t_col].astype(str).str.strip()
            time_merged_name = "datetime (自動合併日期與時間)"
            raw_df.insert(0, time_merged_name, combined_series)
            unit_map[time_merged_name] = "yyyy-mm-dd HH:MM"

        st.success(f"整月資料彙整完成：共合併 {len(df_list)} 個檔案，累計 {len(raw_df):,} 筆原始列、{len(raw_df.columns)-1} 個欄位。")

        with st.expander("🔍 檢視合併後的資料前 5 筆與後 5 筆"):
            st.dataframe(pd.concat([raw_df.head(5), raw_df.tail(5)]))

        columns = [c for c in raw_df.columns if c != "_source_file"]

        def format_col_with_unit(col_name):
            u = unit_map.get(col_name, "")
            return f"{col_name} [{u}]" if u else col_name

        # 使用分頁切換「時序趨勢分析」與「ET 累積儀表板」
        tab_timeseries, tab_et_dashboard = st.tabs(["📈 通量時間序列趨勢", "💧 ET 每日累積儀表板"])

        # ------------------- TAB 1: 時間序列分析 -------------------
        with tab_timeseries:
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                time_col = st.selectbox("選擇【時間 / 日期】欄位：", columns, index=0, key="ts_time")
            with col2:
                exclude_cols = [time_col, col_map.get('date'), col_map.get('time')]
                available_val_cols = [c for c in columns if c not in exclude_cols]
                value_cols = st.multiselect(
                    "選擇要分析的【數值】欄位（可多選）：",
                    options=available_val_cols,
                    format_func=format_col_with_unit,
                    key="ts_values"
                )
            with col3:
                st.write("")
                st.write("")
                filter_invalid = st.checkbox("排除 -9999 無效值", value=True, key="ts_filter")

            if time_col and value_cols:
                df_plot = raw_df.copy()
                df_plot[time_col] = pd.to_datetime(df_plot[time_col], errors='coerce')
                
                for col in value_cols:
                    df_plot[col] = pd.to_numeric(df_plot[col], errors='coerce')
                    if filter_invalid:
                        df_plot.loc[df_plot[col] <= -9990, col] = pd.NA

                df_plot = df_plot.dropna(subset=[time_col])
                df_plot = df_plot.dropna(subset=value_cols, how='all')
                df_plot = df_plot.sort_values(by=time_col).drop_duplicates(subset=[time_col], keep='last')

                if df_plot.empty:
                    st.warning("⚠️ 篩選後無有效數據，請確認時間與數值內容格式。")
                else:
                    total_points = len(df_plot)
                    start_time = df_plot[time_col].min().strftime('%Y-%m-%d %H:%M')
                    end_time = df_plot[time_col].max().strftime('%Y-%m-%d %H:%M')
                    st.info(f"📊 分析區間：`{start_time}` 至 `{end_time}`（總計有效時間點：{total_points:,} 點）")

                    rename_dict = {col: format_col_with_unit(col) for col in value_cols}
                    df_chart = df_plot[[time_col] + value_cols].rename(columns=rename_dict)
                    labeled_value_cols = list(rename_dict.values())

                    selected_units = list({unit_map.get(c, "") for c in value_cols if unit_map.get(c, "")})
                    if len(value_cols) == 1:
                        y_axis_label = labeled_value_cols[0]
                    elif len(selected_units) == 1:
                        y_axis_label = f"數值 [{selected_units[0]}]"
                    else:
                        y_axis_label = "數值 (請見圖例各指標單位)"

                    show_markers = True if total_points <= 500 else False

                    fig = px.line(
                        df_chart,
                        x=time_col,
                        y=labeled_value_cols,
                        markers=show_markers,
                        title=f"時間趨勢分析（{start_time} ~ {end_time}）",
                        labels={time_col: "日期時間", "value": y_axis_label, "variable": "指標名稱 [單位]"}
                    )
                    fig.update_layout(
                        hovermode="x unified",
                        xaxis_title="日期時間",
                        yaxis_title=y_axis_label,
                        legend_title_text="指標名稱 [單位]"
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    st.divider()
                    csv_buffer = io.BytesIO()
                    export_rename = {c: format_col_with_unit(c) for c in df_plot.columns if c not in [time_col, "_source_file"]}
                    df_export = df_plot.rename(columns=export_rename)
                    df_export.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 下載整月份合併清洗後的 CSV 檔案",
                        data=csv_buffer.getvalue(),
                        file_name=f"merged_flux_data_{df_plot[time_col].dt.strftime('%Y%m%d').min()}_{df_plot[time_col].dt.strftime('%Y%m%d').max()}.csv",
                        mime="text/csv"
                    )

        # ------------------- TAB 2: ET 每日累積儀表板 -------------------
        with tab_et_dashboard:
            st.markdown("### 💧 蒸散量 (Evapotranspiration, ET) 累積統計儀表板")
            
            # 尋找候選 ET 欄位
            et_candidates = [c for c in columns if 'et' in c.lower() or 'evapo' in c.lower()]
            default_et_index = columns.index(et_candidates[0]) if et_candidates else 0

            col_et_time, col_et_target = st.columns(2)
            with col_et_time:
                et_time_col = st.selectbox("選擇【時間 / 日期】基準欄位：", columns, index=0, key="et_time")
            with col_et_target:
                et_col = st.selectbox(
                    "選擇【ET 蒸散量】欄位：",
                    columns,
                    index=default_et_index,
                    format_func=format_col_with_unit,
                    key="et_col_select"
                )

            if et_time_col and et_col:
                df_et = raw_df.copy()
                df_et[et_time_col] = pd.to_datetime(df_et[et_time_col], errors='coerce')
                df_et[et_col] = pd.to_numeric(df_et[et_col], errors='coerce')
                
                # 清除無效值
                df_et.loc[df_et[et_col] <= -9990, et_col] = pd.NA
                # 排除小於 0 的物理不合理微小負值（露水或雜訊，可根據需求保留或歸零）
                df_et.loc[df_et[et_col] < 0, et_col] = 0.0

                df_et = df_et.dropna(subset=[et_time_col, et_col])
                df_et = df_et.sort_values(by=et_time_col).drop_duplicates(subset=[et_time_col], keep='last')

                if df_et.empty:
                    st.warning("⚠️ 所選 ET 欄位無有效數值。")
                else:
                    # 依日期提取日期字串 (yyyy-mm-dd)
                    df_et['date_only'] = df_et[et_time_col].dt.date

                    # 按「天」計算累積 ET 與資料完整度
                    daily_et_df = df_et.groupby('date_only').agg(
                        daily_accum_et=(et_col, 'sum'),
                        valid_records=(et_col, 'count'),
                        max_rate=(et_col, 'max')
                    ).reset_index()

                    daily_et_df['date_str'] = daily_et_df['date_only'].astype(str)
                    daily_et_df['cum_monthly_et'] = daily_et_df['daily_accum_et'].cumsum()

                    # 1. 頂部關鍵指標卡片 (Metrics)
                    total_monthly_et = daily_et_df['daily_accum_et'].sum()
                    days_count = len(daily_et_df)
                    avg_daily_et = total_monthly_et / days_count if days_count > 0 else 0
                    max_day_row = daily_et_df.loc[daily_et_df['daily_accum_et'].idxmax()]

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("🗓️ 觀測天數", f"{days_count} 天")
                    m2.metric("💧 整月總累積 ET", f"{total_monthly_et:.2f} mm")
                    m3.metric("📊 日平均累積 ET", f"{avg_daily_et:.2f} mm/天")
                    m4.metric("🔥 單日最大 ET", f"{max_day_row['daily_accum_et']:.2f} mm", f"日期: {max_day_row['date_str']}")

                    st.write("")

                    # 2. 每日累積 ET 柱狀圖 + 累積上升曲線 (雙軸綜合圖)
                    fig_et = go.Figure()

                    # 柱狀圖：每日累積 ET
                    fig_et.add_trace(go.Bar(
                        x=daily_et_df['date_str'],
                        y=daily_et_df['daily_accum_et'],
                        name="每日累積 ET (mm/day)",
                        marker_color='#2ca02c',
                        text=daily_et_df['daily_accum_et'].apply(lambda v: f"{v:.1f}"),
                        textposition='outside'
                    ))

                    # 折線圖：月累加趨勢線 (次 Y 軸)
                    fig_et.add_trace(go.Scatter(
                        x=daily_et_df['date_str'],
                        y=daily_et_df['cum_monthly_et'],
                        name="整月累積總量 (Cumulative mm)",
                        mode='lines+markers',
                        marker=dict(color='#ff7f0e', size=6),
                        line=dict(color='#ff7f0e', width=2.5),
                        yaxis='y2'
                    ))

                    fig_et.update_layout(
                        title=f"💧 每日累積蒸散量與整月累計趨勢圖 ({daily_et_df['date_str'].iloc[0]} ~ {daily_et_df['date_str'].iloc[-1]})",
                        xaxis_title="日期",
                        yaxis=dict(title="每日累積 ET (mm/day)"),
                        yaxis2=dict(
                            title="整月累計總量 (mm)",
                            overlaying='y',
                            side='right',
                            showgrid=False
                        ),
                        legend=dict(x=0.01, y=0.98),
                        hovermode="x unified",
                        height=520
                    )

                    st.plotly_chart(fig_et, use_container_width=True)

                    # 3. 每日統計數據列表與下載
                    with st.expander("📋 檢視每日累積數值清單"):
                        display_df = daily_et_df.rename(columns={
                            'date_str': '日期',
                            'daily_accum_et': '當日累積蒸散量 (mm)',
                            'cum_monthly_et': '累計總量 (mm)',
                            'valid_records': '當日有效記錄點數 (滿額為 48 點)',
                            'max_rate': '單日瞬時最大值'
                        })[['日期', '當日累積蒸散量 (mm)', '累計總量 (mm)', '當日有效記錄點數 (滿額為 48 點)', '單日瞬時最大值']]
                        st.dataframe(display_df, use_container_width=True)

                    # 提供每日累積摘要報表下載
                    et_csv_buffer = io.BytesIO()
                    display_df.to_csv(et_csv_buffer, index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 下載「每日累積 ET 摘要報表 (CSV)」",
                        data=et_csv_buffer.getvalue(),
                        file_name=f"daily_ET_summary_{daily_et_df['date_str'].iloc[0]}_{daily_et_df['date_str'].iloc[-1]}.csv",
                        mime="text/csv"
                    )
