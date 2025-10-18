import json
import sqlite3
import pandas as pd
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# 載入JSON數據
def load_data(json_file):
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return pd.DataFrame(data)

# 初始化資料庫
def init_db(db_name='books.db'):
    conn = sqlite3.connect(db_name)
    df = load_data('data.json')  # 假設JSON命名為data.json
    df.to_sql('books', conn, if_exists='replace', index=False)
    conn.close()
    print("資料庫初始化完成！")

# 簡單推薦函數（基於內容簡介的TF-IDF，優化中文處理）
def recommend_books(query, top_n=5):
    conn = sqlite3.connect('books.db')
    df = pd.read_sql_query("SELECT * FROM books", conn)
    conn.close()
    
    if df.empty or 'content_intro' not in df.columns:
        return pd.DataFrame()
    
    # 預處理：合併 title、author 與 content_intro，提升相關性
    df['text'] = (df['title'].fillna('') + ' ' + df['author'].fillna('') + ' ' + df['content_intro'].fillna('')).astype(str)
    query = re.sub(r'[^\w\s]', ' ', query.lower())  # 移除標點，簡化查詢
    
    # TF-IDF向量化（中文優化：使用 ngrams 捕捉詞組，無需分詞）
    vectorizer = TfidfVectorizer(
        max_features=2000,
        ngram_range=(1, 3),  # 單詞、雙詞、三詞組合，適合中文
        min_df=1,            # 最小文件頻率
        max_df=0.95,         # 最大文件頻率（過濾過常見詞）
        lowercase=True
    )
    tfidf_matrix = vectorizer.fit_transform(df['text'].values)
    
    query_vec = vectorizer.transform([query])
    similarities = cosine_similarity(query_vec, tfidf_matrix).flatten()
    
    df['similarity'] = similarities
    
    # 若所有相似度為0，使用關鍵字匹配 fallback
    if similarities.max() == 0:
        df['keyword_score'] = df['text'].str.contains(query, case=False, na=False).astype(int)
        df['similarity'] = df['keyword_score']  # 簡單計數匹配
    
    # 回傳推薦結果包含 product_id，並依相似度排序
    recommendations = df.nlargest(top_n, 'similarity')[['product_id', 'title', 'author', 'discount_price', 'similarity']]
    return recommendations

if __name__ == "__main__":
    init_db()