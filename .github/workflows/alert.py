from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
import os
import re

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'

options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')

driver = webdriver.Chrome(options=options)

# 1) 로그인
driver.get('https://www.ffwp.org/member/login.php')
driver.find_element(By.NAME, 'userid').send_keys(os.environ['FFWP_USER'])
driver.find_element(By.NAME, 'password').send_keys(os.environ['FFWP_PW'])
driver.find_element(By.ID, 'loginSubmit').click()
time.sleep(2)

# 2) 게시판 접속
driver.get('https://korhq.ffwp.org/official/?sType=ffwp')
WebDriverWait(driver, 30).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr'))
)

# 3) 게시글 리스트 전부 긁어오기
elements = driver.find_elements(By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr')
print(f"🔍 총 게시글 수: {len(elements)}")

posts = []
for el in elements:
    title = el.find_element(By.CSS_SELECTOR, 'span.list_tit').text.strip()
    raw_href = el.find_element(By.TAG_NAME, 'a').get_attribute('href')
    m = re.search(r"goView\((\d+)\)", raw_href)
    post_id = m.group(1) if m else raw_href
    posts.append({'id': post_id, 'title': title, 'href': raw_href})
driver.quit()

# 4) last_seen 불러오기
if os.path.exists(LAST_SEEN_FILE):
    with open(LAST_SEEN_FILE, 'r') as f:
        last_seen = f.read().strip()
else:
    last_seen = ''
print(f"📄 last_seen: '{last_seen}'")

# 5) 알림 대상 분류
to_notify = []
if last_seen == '':
    to_notify = posts[:]   # 처음엔 전체
else:
    for p in posts:
        if p['id'] == last_seen:
            break
        to_notify.append(p)

print(f"🔔 알림 대상 수: {len(to_notify)}")

# 6) 디스코드 웹훅
for p in reversed(to_notify):
    msg = f"📢 **[공지 알림]**\n제목: {p['title']}\n링크: {p['href']}"
    print(f"📤 전송: {msg}")
    res = requests.post(WEBHOOK_URL, json={'content': msg})
    print("   →", "성공✅" if res.status_code == 204 else f"실패❌ {res.status_code}")

# 7) 최신 ID 기록
if posts:
    newest_id = posts[0]['id']
    with open(LAST_SEEN_FILE, 'w') as f:
        f.write(newest_id)
    print(f"✅ last_seen 업데이트: {newest_id}")
