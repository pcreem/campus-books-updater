import asyncio
import httpx
from bs4 import BeautifulSoup
import json
from huggingface_hub import HfApi
import os

# 過濾非書本商品的條件
def is_valid_book(title, specs):
    if (
        "盒卡" in title or "金句" in title or
        "金句盒卡" in specs or "卡片" in specs or
        "福音卡片" in specs or "福音金句盒卡" in specs or
        "100張" in specs
    ):
        return False
    return True

async def get_newbook_ids(client, max_pages=15):
    ids = []
    url = "https://shop.campus.org.tw/IsNewBook.aspx"
    # 先抓第一頁
    resp = await client.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    def extract_ids(soup):
        found = []
        for a in soup.select("a[href*='ProductDetails.aspx?productID=']"):
            href = a.get("href", "")
            if "productID=" in href:
                pid = href.split("productID=")[1].split("&")[0]
                if pid not in ids and pid not in found:
                    found.append(pid)
        return found

    ids.extend(extract_ids(soup))

    # 取得 __VIEWSTATE, __EVENTVALIDATION 等
    def get_hidden(form, name):
        tag = form.find("input", {"name": name})
        return tag["value"] if tag else ""

    form = soup.find("form")
    viewstate = get_hidden(form, "__VIEWSTATE")
    eventvalidation = get_hidden(form, "__EVENTVALIDATION")
    viewstategen = get_hidden(form, "__VIEWSTATEGENERATOR")
    prevpage = get_hidden(form, "__PREVIOUSPAGE")

    # 分頁遍歷：前 10 頁用分頁按鈕，超過 10 頁用「下一頁」按鈕
    for page in range(2, max_pages+1):
        page_idx = page - 1
        if page_idx < 10:
            eventtarget = f"ctl00$ctl00$MainContent$MainContent$rptCounter$ctl{page_idx:02d}$LinkButton1"
        else:
            eventtarget = "ctl00$ctl00$MainContent$MainContent$ibtnNext"
        data = {
            "__EVENTTARGET": eventtarget,
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": viewstate,
            "__EVENTVALIDATION": eventvalidation,
            "__VIEWSTATEGENERATOR": viewstategen,
            "__PREVIOUSPAGE": prevpage,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": url,
            "User-Agent": "Mozilla/5.0"
        }
        resp = await client.post(url, data=data, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        ids.extend(extract_ids(soup))
        # 更新 __VIEWSTATE 等欄位
        form = soup.find("form")
        viewstate = get_hidden(form, "__VIEWSTATE")
        eventvalidation = get_hidden(form, "__EVENTVALIDATION")
        viewstategen = get_hidden(form, "__VIEWSTATEGENERATOR")
        prevpage = get_hidden(form, "__PREVIOUSPAGE")
    return ids

async def scrape_product_details(client, product_id):
    url = f'https://shop.campus.org.tw/ProductDetails.aspx?productID={product_id}'
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"請求失敗 (ID {product_id}): {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # 書名
    title_elem = soup.find(id="MainContent_MainContent_lbProductName")
    title = title_elem.get_text(strip=True) if title_elem else 'N/A'

    # 作者
    author_elem = soup.find(id="MainContent_MainContent_lbAuthor")
    author = author_elem.get_text(strip=True) if author_elem else 'N/A'

    # 出版社
    publisher_elem = soup.find(id="MainContent_MainContent_lbPublisher")
    publisher = publisher_elem.get_text(strip=True) if publisher_elem else 'N/A'

    # 售價
    price_elem = soup.find(id="MainContent_MainContent_lbListPrice0")
    list_price = price_elem.get_text(strip=True) if price_elem else 'N/A'
    discount_price = list_price

    # 庫存
    stock_elem = soup.find(id="MainContent_MainContent_lbQTY")
    stock = stock_elem.get_text(strip=True) if stock_elem else 'N/A'
    stock_note = soup.find(id="MainContent_MainContent_lbNormalQty")
    if stock_note:
        stock += " " + stock_note.get_text(strip=True)

    # 內容簡介
    content_intro = 'N/A'
    intro_block = soup.find(id="MainContent_MainContent_divDescriptionBlock")
    if intro_block:
        intro_text = intro_block.find(class_="heightlimit_des")
        if intro_text:
            content_intro = intro_text.get_text(separator="\n", strip=True)

    # 作者介紹
    author_intro = 'N/A'
    author_block = soup.find(id="MainContent_MainContent_divAuthorIntroBlock")
    if author_block:
        author_text = author_block.find(class_="heightlimit_aut")
        if author_text:
            author_intro = author_text.get_text(separator="\n", strip=True)

    # 目錄
    table_of_contents = 'N/A'
    toc_block = soup.find(id="MainContent_MainContent_divContentBlock")
    if toc_block:
        toc_text = toc_block.find(class_="heightlimit_con")
        if toc_text:
            table_of_contents = toc_text.get_text(separator="\n", strip=True)

    # 詳細資料
    detailed_specs = 'N/A'
    specs_block = soup.find(id="MainContent_MainContent_divDetailDesc")
    if specs_block:
        specs_text = specs_block.find(class_="infomore")
        if specs_text:
            detailed_specs = specs_text.get_text(separator="\n", strip=True)

    # 本書特色（目前頁面無此區塊，預設 N/A）
    book_features = 'N/A'

    image_url = f"https://shop.campus.org.tw/Images/thumbs/{product_id}_01_180_250.jpg"
    return {
        'product_id': product_id,
        'title': title,
        'author': author,
        'publisher': publisher,
        'list_price': list_price,
        'discount_price': discount_price,
        'stock': stock,
        'content_intro': content_intro,
        'book_features': book_features,
        'author_intro': author_intro,
        'table_of_contents': table_of_contents,
        'detailed_specs': detailed_specs,
        'image_url': image_url
    }

async def main():
    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        print("抓取新品分頁所有商品ID ...")
        ids = await get_newbook_ids(client, max_pages=15)
        print(f"共獲得 {len(ids)} 個商品ID")
        all_new_books = []
        for idx, pid in enumerate(ids):
            print(f"({idx+1}/{len(ids)}) 抓取商品 {pid} ...")
            book = await scrape_product_details(client, pid)
            if book and is_valid_book(book['title'], book['detailed_specs']):
                all_new_books.append(book)
        print(f"共獲得 {len(all_new_books)} 本書")

        # 合併新舊資料（避免重複）
        try:
            with open('data.json', 'r', encoding='utf-8') as f:
                old_data = json.load(f)
        except FileNotFoundError:
            old_data = []
        
        # 去重：使用 product_id 檢查
        existing_ids = {b['product_id'] for b in old_data}
        all_books = old_data + [book for book in all_new_books if book['product_id'] not in existing_ids]
        
        # 儲存更新後的 data.json
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(all_books, f, ensure_ascii=False, indent=2)
        
        # 推送到 HF Spaces repo
        api = HfApi()
        api.upload_file(
            path_or_fileobj='data.json',
            path_in_repo='data.json',
            repo_id='pcreem/campusBooks',  # 你的 HF Spaces repo ID
            token=os.getenv('HF_TOKEN'),
            commit_message='Weekly update: new books scraped'
        )
        print("資料更新並推送到 HF Spaces！")

if __name__ == "__main__":
    asyncio.run(main())