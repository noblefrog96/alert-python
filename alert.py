from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
import os
import re
import subprocess
import sys

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'


def safe_exit(driver=None, code=0):
    try:
        if driver:
            driver.quit()
    except:
        pass
    sys.exit(code)


# Git 설정
subprocess.run(['git', 'config', '--global', 'user.name', 'noblefrog96'])
subprocess.run(['git', 'config', '--global', 'user.email', 'noblefrog96@gmail.com'])
subprocess.run([
    'git', 'remote', 'set-url', 'origin',
    f"https://x-access-token:{os.environ['GH_PAT']}@github.com/noblefrog96/alert-python.git"
])

# Chrome 설정
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1920,1080')
options.add_argument('--disable-blink-features=AutomationControlled')

driver = webdriver.Chrome(options=options)

# -------------------------
# 1) 로그인 (www)
# -------------------------
try:
    driver.get('https://www.ffwp.org/member/login.php')
except Exception as e:
    print("❌ 로그인 페이지 로드 실패:", e)
    safe_exit(driver)

try:
    driver.find_element(By.NAME, 'userid').send_keys(os.environ['FFWP_USER'])
    driver.find_element(By.NAME, 'password').send_keys(os.environ['FFWP_PW'])
    driver.find_element(By.ID, 'loginSubmit').click()
    time.sleep(3)
except Exception as e:
    print("❌ 로그인 실패:", e)
    safe_exit(driver)

print("로그인 후 URL:", driver.current_url)

if "login" in driver.current_url.lower():
    print("❌ 로그인 실패 감지")
    safe_exit(driver)

# -------------------------
# 2) 게시판 접근 (핵심 수정)
# -------------------------
driver.get('https://korhq.ffwp.org/official/?sType=ffwp')
time.sleep(3)

# 👉 korhq에서 로그인 요구 시 재로그인
if "login" in driver.current_url.lower():
    print("🔐 korhq 도메인 재로그인 필요")

    try:
        driver.find_element(By.NAME, 'userid').clear()
        driver.find_element(By.NAME, 'userid').send_keys(os.environ['FFWP_USER'])
        driver.find_element(By.NAME, 'password').clear()
        driver.find_element(By.NAME, 'password').send_keys(os.environ['FFWP_PW'])
        driver.find_element(By.ID, 'loginSubmit').click()
        time.sleep(3)
    except Exception as e:
        print("❌ korhq 로그인 실패:", e)
        safe_exit(driver)

# 다시 게시판 접근
driver.get('https://korhq.ffwp.org/official/?sType=ffwp')

try:
    WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr'))
    )
except Exception as e:
    print("❌ 게시판 로딩 실패:", e)
    print("현재 URL:", driver.current_url)
    safe_exit(driver)

# -------------------------
# 3) 게시글 수집
# -------------------------
elements = driver.find_elements(By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr')
posts = []

for el in elements:
    try:
        title = el.find_element(By.CSS_SELECTOR, 'span.list_tit').text.strip()
        raw_href = el.find_element(By.TAG_NAME, 'a').get_attribute('href')

        post_id = None
        post_url = None

        if raw_href.startswith("javascript:goView"):
            m = re.search(r"goView\((\d+)\)", raw_href)
            if m:
                post_id = m.group(1)
                post_url = f"https://korhq.ffwp.org/official/?mode=view&pageType=officialList&sPage=1&sType=ffwp&document={post_id}#contents"
        else:
            m = re.search(r'document=(\d+)', raw_href)
            if m:
                post_id = m.group(1)
                post_url = raw_href

        if post_id:
            posts.append({
                'id': post_id,
                'title': title,
                'href': post_url
            })

    except:
        continue

driver.quit()

if not posts:
    print("❌ 게시글 0개 → 종료")
    sys.exit(0)

posts.sort(key=lambda x: int(x['id']), reverse=True)

print("📄 게시글 수:", len(posts))
print("🆕 최신 ID:", posts[0]['id'])

# -------------------------
# 4) last_seen
# -------------------------
if os.path.exists(LAST_SEEN_FILE):
    with open(LAST_SEEN_FILE, 'r') as f:
        last_seen = f.read().strip()
else:
    last_seen = ''

print("💾 last_seen:", last_seen)

# 이상값 방지
if last_seen and not last_seen.isdigit():
    with open(LAST_SEEN_FILE, 'w') as f:
        f.write(posts[0]['id'])
    sys.exit(0)

current_ids = [p['id'] for p in posts]

if last_seen and last_seen not in current_ids:
    print("⚠ 기준 초기화")
    with open(LAST_SEEN_FILE, 'w') as f:
        f.write(posts[0]['id'])
    sys.exit(0)

# -------------------------
# 5) 새 글 필터
# -------------------------
to_notify = []

if last_seen:
    for p in posts:
        if p['id'] == last_seen:
            break
        to_notify.append(p)

print("🔔 새 글 수:", len(to_notify))

# -------------------------
# 6) 디스코드 전송
# -------------------------
for p in reversed(to_notify):
    try:
        requests.post(WEBHOOK_URL, json={
            'content': f"📢 **[공지 알림]**\n제목: {p['title']}\n링크: {p['href']}"
        }, timeout=10)
    except Exception as e:
        print("⚠ 디스코드 실패:", e)

# -------------------------
# 7) last_seen 업데이트
# -------------------------
newest_id = posts[0]['id']

if last_seen != newest_id:
    with open(LAST_SEEN_FILE, 'w') as f:
        f.write(newest_id)

    try:
        subprocess.run(['git', 'add', LAST_SEEN_FILE], check=True)
        subprocess.run(['git', 'commit', '-m', f'Update {newest_id}'], check=True)
        subprocess.run(['git', 'push'], check=True)
    except Exception as e:
        print("⚠ git 실패:", e)
else:
    print("변경 없음")
