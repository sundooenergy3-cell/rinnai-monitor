import pandas as pd
import requests
import sqlite3
import time
import schedule
import json
from datetime import datetime

# =========================
# 네이버 API
# =========================
CLIENT_ID = "Dhu6vM_iFaeBegi5vki2"
CLIENT_SECRET = "pQmwlZDtHs"

# =========================
# 카카오 설정
# access token은 만료되므로 refresh token으로 자동 재발급해서 사용
# =========================
KAKAO_REST_API_KEY = "cf0444343c140d234a24cea95f1a99d7"
KAKAO_CLIENT_SECRET = "3hpct9Kd9ZPqom3uZGfKs2qfYtcIbBHR"
KAKAO_REFRESH_TOKEN = "EkhICQxItAAmtKtkQwB9ol5omx3HyqZLAAAAAgoXFmIAAAGdit6pcujqOP6o1CZo"

# =========================
# 파일명
# =========================
file_name = '대리점_리스트.xlsx'

# =========================
# 특정 상품만 고정
# =========================
FIXED_MALL_NAME = "세명트레이딩"
FIXED_KEYWORD = "RSB-922N 세명트레이딩"
FIXED_PRODUCT_ID = "12171751999"

# 후보 상품ID: 83275916200 / mall: 세명트레이딩 / price: 438,570원
# 후보 상품ID: 12171751999 / mall: 세명트레이딩 / price: 408,870원


def normalize_text(value):
    return " ".join(str(value).replace("\u00A0", " ").split()).strip()


def setup_db():
    conn = sqlite3.connect('rinnai_monitoring.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_comparison (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            keyword TEXT,
            mall_name TEXT,
            sell_price INTEGER,
            ship_fee TEXT,
            total_price INTEGER
        )
    ''')
    conn.commit()
    return conn


def search_naver(keyword, target_mall, target_product_id=None):
    url = "https://openapi.naver.com/v1/search/shop.json"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET
    }
    params = {"query": keyword, "display": 100, "sort": "sim"}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code != 200:
            print(f"⚠️ API 오류: {res.status_code} / {res.text}")
            return None

        target_clean = normalize_text(target_mall).replace(" ", "").lower()
        candidates = []

        for item in res.json().get("items", []):
            mall_name = item.get("mallName", "")
            mall_clean = normalize_text(mall_name).replace(" ", "").lower()

            if target_clean in mall_clean:
                sell_price = int(item.get("lprice", 0))
                if sell_price < 10000:
                    continue

                product_id = str(item.get("productId", "")).strip()

                candidates.append({
                    "mall": mall_name,
                    "sell_price": sell_price,
                    "product_id": product_id
                })

        if not candidates:
            return None

        # 특정 상품ID가 지정된 경우: 해당 상품만 선택
        if target_product_id:
            target_product_id = str(target_product_id).strip()

            for item in candidates:
                if item["product_id"] == target_product_id:
                    return {
                        "mall": item["mall"],
                        "sell_price": item["sell_price"]
                    }

            print(f"⚠️ 지정한 상품ID({target_product_id})를 찾지 못함")
            for item in candidates[:10]:
                print(f"   후보 상품ID: {item['product_id']} / mall: {item['mall']} / price: {item['sell_price']:,}원")
            return None

        # 일반 상품은 기존처럼 첫 번째 후보 사용
        return {
            "mall": candidates[0]["mall"],
            "sell_price": candidates[0]["sell_price"]
        }

    except Exception as e:
        print(f"⚠️ 요청 오류: {e}")

    return None


def get_last_price(cursor, keyword, mall_name):
    cursor.execute("""
        SELECT sell_price, total_price, date
        FROM price_comparison
        WHERE keyword = ? AND mall_name = ?
        ORDER BY id DESC
        LIMIT 1
    """, (keyword, mall_name))
    return cursor.fetchone()


def refresh_kakao_access_token():
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": KAKAO_REST_API_KEY,
        "client_secret": KAKAO_CLIENT_SECRET,
        "refresh_token": KAKAO_REFRESH_TOKEN,
    }

    res = requests.post(url, data=data, timeout=10)
    if res.status_code != 200:
        raise Exception(f"카카오 토큰 재발급 실패: {res.status_code} / {res.text}")

    token_data = res.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise Exception(f"access_token 없음: {token_data}")

    return access_token


def build_change_message(changes):
    def short_text(text, limit=28):
        text = str(text).strip()
        return text if len(text) <= limit else text[:limit] + "..."

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [
        "📢 린나이 가격 변동 알림",
        "",
        f" 확인 시각: {now_str}",
        ""
    ]

    for idx, ch in enumerate(changes[:10], 1):
        diff = ch["new_total"] - ch["old_total"]

        if diff > 0:
            diff_text = f"▲ +{diff:,}원 상승"
        elif diff < 0:
            diff_text = f"▼ {abs(diff):,}원 하락"
        else:
            diff_text = "➖ 변동 없음"

        keyword = short_text(ch["keyword"], 30)
        mall_name = short_text(ch["mall_name"], 20)

        lines.extend([
            f" {idx}. {keyword}",
            "",
            f"① 대리점: {mall_name}",
            f"② 이전: {ch['old_total']:,}원",
            f"③ 현재: {ch['new_total']:,}원",
            f"④ 변동: {diff_text}",
            ""
        ])

    if len(changes) > 10:
        lines.append(f"외 {len(changes) - 10}건 추가 변동")

    return "\n".join(lines).strip()


def send_kakao_message(message_text):
    try:
        access_token = refresh_kakao_access_token()
    except Exception as e:
        print(f"⚠️ 카카오 access token 발급 실패: {e}")
        return

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    template_object = {
        "object_type": "text",
        "text": message_text,
        "link": {
            "web_url": "https://example.com",
            "mobile_web_url": "https://example.com"
        }
    }

    data = {
        "template_object": json.dumps(template_object, ensure_ascii=False)
    }

    try:
        res = requests.post(url, headers=headers, data=data, timeout=10)
        print(f"📨 카톡 전송 결과: {res.status_code} / {res.text}")
    except Exception as e:
        print(f"⚠️ 카톡 전송 오류: {e}")


def run_collection():
    print("\n" + "=" * 50)
    print(f"🕐 자동 수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    try:
        df = pd.read_excel(file_name).dropna(subset=['대리점명', '키워드'])
        print(f"✅ {file_name} 로드 완료 ({len(df)}건)")
    except FileNotFoundError:
        print(f"❌ 오류: {file_name} 파일이 없습니다.")
        return
    except Exception as e:
        print(f"❌ 엑셀 로드 오류: {e}")
        return

    conn = setup_db()
    cursor = conn.cursor()

    results = []
    changes = []
    now_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    search_list = df[['대리점명', '키워드', '배송비']].values.tolist()

    fixed_mall_norm = normalize_text(FIXED_MALL_NAME)
    fixed_keyword_norm = normalize_text(FIXED_KEYWORD)

    for count, (target_mall, kw, ship_fee) in enumerate(search_list, 1):
        print(f"📡 [{count}/{len(search_list)}] '{kw}' 검색 중...", end=" ", flush=True)

        ship_fee_raw = str(ship_fee).strip()
        try:
            ship_fee_num = int(float(ship_fee_raw))
            ship_fee_text = str(ship_fee_num)
        except Exception:
            ship_fee_text = ship_fee_raw if ship_fee_raw not in ['nan', ''] else '0'
            ship_fee_num = 0

        mall_norm = normalize_text(target_mall)
        kw_norm = normalize_text(kw)

        target_product_id = None
        if mall_norm == fixed_mall_norm and kw_norm == fixed_keyword_norm:
            target_product_id = FIXED_PRODUCT_ID
            print(f"[고정ID적용:{target_product_id}]", end=" ", flush=True)

        found = search_naver(kw, target_mall, target_product_id)

        if found:
            sell_price = found['sell_price']
            total_price = sell_price + ship_fee_num
            ship_display = '무료' if ship_fee_text == '0' else ship_fee_text

            print(f"🎯 {sell_price:,}원 (배송비: {ship_display})")

            results.append((now_time, kw, found['mall'], sell_price, ship_fee_text, total_price))

            last_row = get_last_price(cursor, kw, found['mall'])
            if last_row:
                old_sell_price, old_total_price, old_date = last_row

                if old_total_price != total_price:
                    changes.append({
                        "keyword": kw,
                        "mall_name": found['mall'],
                        "old_sell": old_sell_price,
                        "new_sell": sell_price,
                        "old_total": old_total_price,
                        "new_total": total_price,
                        "old_date": old_date,
                        "new_date": now_time
                    })
                    print(f"   🔔 가격 변동 감지: {old_total_price:,}원 → {total_price:,}원")
        else:
            print("❌ 미검출")

        time.sleep(0.2)

    if results:
        cursor.executemany(
            "INSERT INTO price_comparison (date, keyword, mall_name, sell_price, ship_fee, total_price) VALUES (?,?,?,?,?,?)",
            results
        )
        conn.commit()
        print(f"\n✅ 총 {len(results)}건 저장 완료!")
    else:
        print("\n⚠️ 저장된 데이터가 없습니다.")

    if changes:
        print(f"📢 가격 변동 {len(changes)}건 발견")
        message = build_change_message(changes)
        send_kakao_message(message)
    else:
        print("📭 가격 변동 없음")

    conn.close()
    print("🏁 수집 완료!")


print("🚀 린나이 가격 수집기 시작!")
print("⏰ 매일 오전 08:00 / 12:00 자동 수집")
run_collection()

schedule.every().day.at("08:00").do(run_collection)
schedule.every().day.at("12:00").do(run_collection)

while True:
    schedule.run_pending()
    time.sleep(60)