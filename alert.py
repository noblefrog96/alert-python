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

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'

# Git 설정 (푸시를 위해 필요)
subprocess.run(['git', 'config', '--global', 'user.name', 'noblefrog96'])
subprocess.run(['git', 'config', '--global', 'user.email', 'noblefrog96@gmail.com'])
subprocess.run([
    'git', 'remote', 'set-url', 'origin',
    f"https://x-access-token:{os.environ['GH_PAT']}@github.com/noblefrog96/alert-python.git"
])

# Chrome headless 설정
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

# 3) 게시글 리스트 긁기
elements = driver.find_elements(By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr')
posts = []
for el in elements:
    title = el.find_element(By.CSS_SELECTOR, 'span.list_tit').text.strip()
    raw_href = el.find_element(By.TAG_NAME, 'a').get_attribute('href')

    if raw_href.startswith("javascript:goView"):
    m = re.search(r"goView\((\d+)\)", raw_href)
    post_id = m.group(1) if m else raw_href
    post_url = f"https://korhq.ffwp.org/official/?mode=view&pageType=officialList&sPage=1&sType=ffwp&sCategory=&listSearch=&document={post_id}#contents"  # 실제 URL 형식으로 수정
    else:
        post_url = raw_href
    posts.append({'id': post_id, 'title': title, 'href': raw_href})
driver.quit()

# 4) last_seen 불러오기
if os.path.exists(LAST_SEEN_FILE):
    with open(LAST_SEEN_FILE, 'r') as f:
        last_seen = f.read().strip()
else:
    last_seen = ''

# 5) 새 게시글 필터링
to_notify = []
if last_seen == '':
    to_notify = posts[:]
else:
    for p in posts:
        if p['id'] == last_seen:
            break
        to_notify.append(p)

# 6) 디스코드 전송
for p in reversed(to_notify):
    msg = f"📢 **[공지 알림]**\n제목: {p['title']}\n링크: {p['href']}"
    requests.post(WEBHOOK_URL, json={'content': msg})

# 7) last_seen.txt 업데이트 + git 커밋 & 푸시
if posts:
    newest_id = posts[0]['id']
    with open(LAST_SEEN_FILE, 'w') as f:
        f.write(newest_id)

    subprocess.run(['git', 'add', LAST_SEEN_FILE])
    subprocess.run(['git', 'commit', '-m', f'Update last_seen.txt to {newest_id}'])
    subprocess.run(['git', 'push'])
