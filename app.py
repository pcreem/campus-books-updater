import streamlit as st
import pandas as pd
import sqlite3
import requests
import numpy as np  # 新增：用於處理 NaN
from io import BytesIO
from PIL import Image
from database import recommend_books
import time  # 新增：用於進度條

# 標題
st.title("圖書搜尋")

@st.cache_data
def load_books():
    conn = sqlite3.connect('books.db')
    df = pd.read_sql_query("SELECT * FROM books", conn)
    conn.close()
    # 處理必要欄位型態
    for col in ['discount_price', 'list_price', 'stock']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace('N/A', np.nan), errors='coerce').fillna(0)
    return df

df = load_books()

def run_recommendation():
    with st.spinner("正在計算推薦..."):
        time.sleep(0.5)
        st.session_state.recs = recommend_books(st.session_state.search_query)
        st.session_state.selected_display = None
    if st.session_state.recs.empty:
        st.warning("無推薦結果，請調整關鍵字。")
    else:
        st.success(f"找到 {len(st.session_state.recs)} 本推薦書籍！")

if "search_query" not in st.session_state:
    st.session_state.search_query = ""

search_query = st.text_input(
    "輸入關鍵字（如：靈修、耶穌）",
    value=st.session_state.search_query,
    key="search_query",
    on_change=run_recommendation
)
if "recs" not in st.session_state:
    st.session_state.recs = pd.DataFrame()
if st.session_state.recs is None or st.session_state.recs.empty:
    st.session_state.recs = pd.DataFrame()
if "selected_display" not in st.session_state:
    st.session_state.selected_display = None

if not st.session_state.recs.empty:
    st.subheader("推薦書籍列表（相似度排序）")
    recs_display = st.session_state.recs[['product_id', 'title', 'author', 'similarity']].copy()
    import re
    recs_display['顯示'] = recs_display['title'].apply(lambda x: re.sub(r'<[^>]+>', '', str(x)))
    recs_display['顯示'] = recs_display['顯示'].apply(lambda x: re.sub(r'~', '～', str(x)))
    for idx, row in recs_display.iterrows():
        if st.button(row['顯示'], key=f"book_{row['product_id']}"):
            st.session_state.selected_display = row['顯示']

if st.session_state.selected_display:
    selected_row = None
    if not st.session_state.recs.empty:
        recs_display = st.session_state.recs[['product_id', 'title', 'author', 'similarity']].copy()
        import re
        recs_display['顯示'] = recs_display['title'].apply(lambda x: re.sub(r'<[^>]+>', '', str(x)))
        recs_display['顯示'] = recs_display['顯示'].apply(lambda x: re.sub(r'~', '～', str(x)))
        selected_rows = recs_display[recs_display['顯示'] == st.session_state.selected_display]
        if not selected_rows.empty:
            selected_row = selected_rows.iloc[0]
    if selected_row is not None:
        book_data = df[df['product_id'] == selected_row['product_id']].iloc[0]
        def clean_text(val):
            import re
            return re.sub(r'~', '～', re.sub(r'<[^>]+>', '', str(val)))
        col1, col2 = st.columns([1, 2])
        with col1:
            if 'image_url' in book_data and book_data['image_url']:
                try:
                    response = requests.get(book_data['image_url'], verify=False, timeout=10)
                    response.raise_for_status()
                    img = Image.open(BytesIO(response.content))
                    img = img.resize((180, 250))
                    st.image(img, caption=f"{clean_text(book_data['title'])} - 作者：{clean_text(book_data['author'])}", width=180)
                except Exception as e:
                    st.error(f"圖片載入失敗：{e}（已跳過 SSL 驗證）")
        with col2:
            st.header("書籍詳情")
            product_id = book_data.get('product_id', '')
            st.markdown(f"""
            **書名**：{clean_text(book_data.get('title', 'N/A'))}
            **作者**：{clean_text(book_data.get('author', 'N/A'))}
            **出版社**：{clean_text(book_data.get('publisher', 'N/A'))}
            **優惠價**：{book_data.get('discount_price', 'N/A')}
            **定價**：{book_data.get('list_price', 'N/A')}
            **購買連結**：<a href="https://shop.campus.org.tw/ProductDetails.aspx?productID={product_id}" target="_blank" rel="noopener noreferrer">前往購買</a>
            """, unsafe_allow_html=True)
            content_intro = book_data.get('content_intro', 'N/A')
            content_intro = clean_text(content_intro)
            st.markdown("**內容簡介**：")
            st.write(content_intro[:500] + "..." if len(content_intro) > 500 else content_intro)
