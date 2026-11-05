import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 1. 頁面配置
st.set_page_config(page_title="批次時間序列分析工具", layout="wide")
st.title("📈 多檔案批次時間序列分析工具")
st.caption("支援一次上傳整月檔案，自動合併日期時間、識別並標示物理單位，繪製長期趨勢圖。")

# 內建常見通量與環境監測參數標準單位對照表（當檔案無單位列時自動補齊）
DEFAULT_UNITS = {
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

    # 檢查前 3 列是否有包含中括號格式 [xxx] 的單位列
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
        # 1. 優先從檔案內的單位列提取
        if unit_row_idx is not None:
            raw_u = str(df.iloc[unit_row_idx][col]).strip()
            if raw_u not in ['nan', 'None', '', '[-]']:
                unit_str = raw_u.strip('[]')
        
        # 2. 若檔案無單位列，查詢預設標準字典
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
        # 先從第一份檔案提取各欄位的單位
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

        # 定義顯示名稱格式：若有單位則顯示「欄位名稱 [單位]」
        def format_col_with_unit(col_name):
            u = unit_map.get(col_name, "")
            return f"{col_name} [{u}]" if u else col_name

        # 3. 欄位與過濾設定
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            time_col = st.selectbox("選擇【時間 / 日期】欄位：", columns, index=0)
        with col2:
            exclude_cols = [time_col, col_map.get('date'), col_map.get('time')]
            available_val_cols = [c for c in columns if c not in exclude_cols]
            value_cols = st.multiselect(
                "選擇要分析的【數值】欄位（自動標示單位，可多選）：",
                options=available_val_cols,
                format_func=format_col_with_unit
            )
        with col3:
            st.write("")
            st.write("")
            filter_invalid = st.checkbox("排除 -9999 無效值", value=True)

        # 4. 資料清理、去重與繪圖
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

                # 建立繪圖專用的欄位名稱（帶上單位）
                rename_dict = {col: format_col_with_unit(col) for col in value_cols}
                df_chart = df_plot[[time_col] + value_cols].rename(columns=rename_dict)
                labeled_value_cols = list(rename_dict.values())

                # 若只選單一欄位或所有選取欄位單位相同，將單位直接顯示在 Y 軸標題上
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

                # 5. 匯出合併清洗後的 CSV（欄位名稱包含單位）
                st.divider()
                csv_buffer = io.BytesIO()
                export_rename = {c: format_col_with_unit(c) for c in df_plot.columns if c not in [time_col, "_source_file"]}
                df_export = df_plot.rename(columns=export_rename)
                df_export.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 下載整月份合併清洗後的 CSV 檔案（含單位標題）",
                    data=csv_buffer.getvalue(),
                    file_name=f"merged_data_{df_plot[time_col].dt.strftime('%Y%m%d').min()}_to_{df_plot[time_col].dt.strftime('%Y%m%d').max()}.csv",
                    mime="text/csv"
                )

        elif not value_cols:
            st.info("請於上方選取至少一個欲觀察的數值欄位。")
