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
    """브라우저 안전 종료"""
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

# Chrome headless 설정
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1920,1080')

driver = webdriver.Chrome(options=options)

# 1) 로그인
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
    print("❌ 로그인 폼 입력/제출 실패:", e)
    print("현재 URL:", driver.current_url)
    print("페이지 제목:", driver.title)
    with open("debug_login_page.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    driver.save_screenshot("debug_login_screenshot.png")
    safe_exit(driver)

# ✅ 로그인 성공 여부 확인 강화
print("로그인 후 URL:", driver.current_url)
print("로그인 후 제목:", driver.title)

if "login" in driver.current_url.lower() or "로그인" in driver.title:
    print("❌ 로그인 실패 감지")
    with open("debug_login_fail.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    driver.save_screenshot("debug_login_fail.png")
    safe_exit(driver)

# 2) 게시판 접속
try:
    driver.get('https://korhq.ffwp.org/official/?sType=ffwp')
except Exception as e:
    print("❌ 게시판 URL 접속 실패:", e)
    safe_exit(driver)

try:
    WebDriverWait(driver, 60).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr'))
    )
except Exception as e:
    print("❌ 게시판 로딩 실패:", e)
    print("현재 URL:", driver.current_url)
    print("페이지 제목:", driver.title)

    # 디버깅용 HTML / 스크린샷 저장
    with open("debug_board_page.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    driver.save_screenshot("debug_board_screenshot.png")

    safe_exit(driver)

# 3) 게시글 리스트 긁기 (ID 안정화)
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
                post_url = (
                    "https://korhq.ffwp.org/official/"
                    "?mode=view&pageType=officialList&sPage=1&sType=ffwp"
                    f"&sCategory=&listSearch=&document={post_id}#contents"
                )
        else:
            m = re.search(r'document=(\d+)', raw_href)
            if m:
                post_id = m.group(1)
                post_url = raw_href

        # post_id 없는 항목은 제외
        if post_id:
            posts.append({
                'id': post_id,
                'title': title,
                'href': post_url
            })

    except Exception as e:
        print("⚠ 게시글 파싱 중 일부 항목 스킵:", e)
        continue

driver.quit()

# 게시글 하나도 못 긁었으면 중단
if not posts:
    print("❌ 게시글을 하나도 가져오지 못했습니다. 종료합니다.")
    sys.exit(0)

# 게시글 ID 기준 최신순 정렬 (중요)
posts.sort(key=lambda x: int(x['id']), reverse=True)

# 4) last_seen 불러오기
if os.path.exists(LAST_SEEN_FILE):
    with open(LAST_SEEN_FILE, 'r') as f:
        last_seen = f.read().strip()
else:
    last_seen = ''

# ⚠ last_seen 값 sanity check (숫자 아니면 초기화)
if last_seen and not last_seen.isdigit():
    print("⚠ last_seen 값이 숫자가 아님. 기준 재설정 후 종료")
    with open(LAST_SEEN_FILE, 'w') as f:
        f.write(posts[0]['id'])
    sys.exit(0)

# ⚠ last_seen이 현재 페이지에 없으면 폭탄 방지
current_ids = [p['id'] for p in posts]

if last_seen and last_seen not in current_ids:
    print("⚠ last_seen이 현재 페이지에 없음. 기준 재설정 후 종료")
    with open(LAST_SEEN_FILE, 'w') as f:
        f.write(posts[0]['id'])
    sys.exit(0)

# 5) 새 게시글 필터링 (초기/비정상 상태 보호)
to_notify = []

if last_seen == '':
    # 최초 실행 또는 상태 꼬임 → 알림 보내지 않음
    print("Initial run or invalid last_seen. Skipping notifications.")
else:
    for p in posts:
        if p['id'] == last_seen:
            break
        to_notify.append(p)

print(f"🔔 감지된 새 게시글 수: {len(to_notify)}")

# 6) 디스코드 전송
for p in reversed(to_notify):
    msg = f"📢 **[공지 알림]**\n제목: {p['title']}\n링크: {p['href']}"
    try:
        requests.post(WEBHOOK_URL, json={'content': msg}, timeout=10)
    except Exception as e:
        print("⚠ 디스코드 전송 실패:", e)

# 7) last_seen.txt 업데이트 + git 커밋 & 푸시 (변경 있을 때만)
if posts:
    newest_id = posts[0]['id']

    current_last_seen = ""
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, 'r') as f:
            current_last_seen = f.read().strip()

    if current_last_seen != newest_id:
        with open(LAST_SEEN_FILE, 'w') as f:
            f.write(newest_id)

        try:
            subprocess.run(['git', 'add', LAST_SEEN_FILE], check=True)
            subprocess.run(
                ['git', 'commit', '-m', f'Update last_seen.txt to {newest_id}'],
                check=True
            )
            subprocess.run(['git', 'push'], check=True)
        except subprocess.CalledProcessError as e:
            print("⚠ git 작업 실패 (알림은 정상 전송됨):", e)
    else:
        print("last_seen.txt unchanged")
