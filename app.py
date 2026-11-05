import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 1. 頁面配置
st.set_page_config(page_title="批次時間序列分析工具", layout="wide")
st.title("📈 多檔案批次時間序列分析工具")
st.caption("支援一次上傳整月（多個同格式）檔案，自動合併日期與時間、過濾單位列並繪製長期趨勢圖。")

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
                    # 支援 Tab、逗號與空白分隔
                    temp_df = pd.read_csv(file, sep=None, engine='python')
                
                temp_df["_source_file"] = file.name
                df_list.append(temp_df)
            except Exception as e:
                error_files.append((file.name, str(e)))

        if error_files:
            st.warning(f"⚠️ 共有 {len(error_files)} 份檔案讀取失敗並已跳過。")
        status.update(label=f"✅ 成功載入 {len(df_list)} 份檔案！", state="complete")

    if df_list:
        raw_df = pd.concat(df_list, ignore_index=True)

        # 自動偵測：若表格內同時有 date 與 time 欄位（如 EddyPro Summary 格式），自動合併成完整時間欄位
        col_map = {c.lower().strip(): c for c in raw_df.columns}
        if 'date' in col_map and 'time' in col_map:
            d_col = col_map['date']
            t_col = col_map['time']
            # 將日期與時間字串相加合併，放到最前面第一欄
            combined_series = raw_df[d_col].astype(str).str.strip() + " " + raw_df[t_col].astype(str).str.strip()
            raw_df.insert(0, "datetime (自動合併日期與時間)", combined_series)

        st.success(f"整月資料彙整完成：共合併 {len(df_list)} 個檔案，累計 {len(raw_df):,} 筆原始列、{len(raw_df.columns)-1} 個欄位。")

        with st.expander("🔍 檢視合併後的資料前 5 筆與後 5 筆"):
            st.dataframe(pd.concat([raw_df.head(5), raw_df.tail(5)]))

        columns = [c for c in raw_df.columns if c != "_source_file"]

        # 3. 欄位與過濾設定
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            # 預設自動選中合併後的完整時間欄
            time_col = st.selectbox("選擇【時間 / 日期】欄位：", columns, index=0)
        with col2:
            exclude_cols = [time_col, col_map.get('date'), col_map.get('time')]
            value_cols = st.multiselect(
                "選擇要分析的【數值】欄位（可多選）：",
                [c for c in columns if c not in exclude_cols]
            )
        with col3:
            st.write("")
            st.write("")
            filter_invalid = st.checkbox("排除 -9999 無效值", value=True)

        # 4. 資料清理、去重與繪圖
        if time_col and value_cols:
            df_plot = raw_df.copy()
            
            # 轉換為標準時間格式（檔案中的單位列如 [yyyy-mm-dd] 會自動轉為 NaT 被剔除）
            df_plot[time_col] = pd.to_datetime(df_plot[time_col], errors='coerce')
            
            # 數值型別轉換與 -9999 無效值過濾
            for col in value_cols:
                df_plot[col] = pd.to_numeric(df_plot[col], errors='coerce')
                if filter_invalid:
                    df_plot.loc[df_plot[col] <= -9990, col] = pd.NA

            # 排除時間為空的列（包含單位列），以及所有選取數值皆為空的列
            df_plot = df_plot.dropna(subset=[time_col])
            df_plot = df_plot.dropna(subset=value_cols, how='all')

            # 依完整日期時間排序並去除重複時間點
            df_plot = df_plot.sort_values(by=time_col).drop_duplicates(subset=[time_col], keep='last')

            if df_plot.empty:
                st.warning("⚠️ 篩選後無有效數據，請確認時間與數值內容格式。")
            else:
                total_points = len(df_plot)
                start_time = df_plot[time_col].min().strftime('%Y-%m-%d %H:%M')
                end_time = df_plot[time_col].max().strftime('%Y-%m-%d %H:%M')
                
                st.info(f"📊 分析區間：`{start_time}` 至 `{end_time}`（總計有效時間點：{total_points:,} 點）")

                show_markers = True if total_points <= 500 else False

                fig = px.line(
                    df_plot,
                    x=time_col,
                    y=value_cols,
                    markers=show_markers,
                    title=f"時間趨勢分析（{start_time} ~ {end_time}）",
                    labels={time_col: "日期時間", "value": "數值", "variable": "指標"}
                )

                fig.update_layout(
                    hovermode="x unified",
                    xaxis_title="日期時間",
                    yaxis_title="數值",
                    legend_title_text="指標名稱"
                )

                st.plotly_chart(fig, use_container_width=True)

                # 5. 匯出合併清洗後的 CSV
                st.divider()
                csv_buffer = io.BytesIO()
                df_plot.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 下載整月份合併清洗後的 CSV 檔案",
                    data=csv_buffer.getvalue(),
                    file_name=f"merged_data_{df_plot[time_col].dt.strftime('%Y%m%d').min()}_to_{df_plot[time_col].dt.strftime('%Y%m%d').max()}.csv",
                    mime="text/csv"
                )

        elif not value_cols:
            st.info("請於上方選取至少一個欲觀察的數值欄位。")
