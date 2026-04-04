from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import requests
import os
import re
import subprocess
import sys

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'

# =========================
# 공통 함수
# =========================
def safe_exit(driver=None, code=0):
    try:
        if driver:
            driver.quit()
    except:
        pass
    sys.exit(code)

# =========================
# Git 설정
# =========================
subprocess.run(['git', 'config', '--global', 'user.name', 'noblefrog96'])
subprocess.run(['git', 'config', '--global', 'user.email', 'noblefrog96@gmail.com'])
subprocess.run([
    'git', 'remote', 'set-url', 'origin',
    f"https://x-access-token:{os.environ['GH_PAT']}@github.com/noblefrog96/alert-python.git"
])

# =========================
# Chrome 설정
# =========================
options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1920,1080')

# 봇 탐지 완화용
options.add_argument('--disable-blink-features=AutomationControlled')
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)

driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(60)

# webdriver 흔적 완화
driver.execute_script("""
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
})
""")

# =========================
# 1) 로그인
# =========================
try:
    driver.get('https://www.ffwp.org/member/login.php')
    print("로그인 페이지 접근 성공")
except Exception as e:
    print("❌ 로그인 페이지 로드 실패:", e)
    safe_exit(driver, 0)

try:
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.NAME, 'userid'))
    )
except TimeoutException:
    print("❌ 로그인 폼 로딩 실패")
    print("현재 URL:", driver.current_url)
    safe_exit(driver, 0)

driver.find_element(By.NAME, 'userid').send_keys(os.environ['FFWP_USER'])
driver.find_element(By.NAME, 'password').send_keys(os.environ['FFWP_PW'])
driver.find_element(By.ID, 'loginSubmit').click()

# 로그인 후 안정화 대기
time.sleep(5)

print("로그인 후 URL:", driver.current_url)
try:
    print("로그인 후 제목:", driver.title)
except:
    pass

# 로그인 실패 감지
if "login" in driver.current_url.lower():
    print("❌ 로그인 실패 감지")
    safe_exit(driver, 0)

# =========================
# 2) 메인 페이지 먼저 안정화
# =========================
try:
    driver.get('https://www.ffwp.org/main.php')
    print("메인 페이지 접근 완료")
    time.sleep(5)
except Exception as e:
    print("❌ 메인 페이지 접근 실패:", e)
    safe_exit(driver, 0)

print("메인 페이지 URL:", driver.current_url)
try:
    print("메인 페이지 제목:", driver.title)
except:
    pass

# 페이지 JS 안정화용 스크롤/대기
try:
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(2)
except:
    pass

# =========================
# 3) 게시판 접근 (직접 GET 대신 브라우저 흐름처럼 이동)
# =========================
try:
    driver.execute_script("""
        window.location.href = 'https://korhq.ffwp.org/official/?sType=ffwp';
    """)
    time.sleep(8)
except Exception as e:
    print("❌ 게시판 이동 스크립트 실패:", e)
    safe_exit(driver, 0)

print("게시판 접근 후 URL:", driver.current_url)
try:
    print("페이지 제목:", driver.title)
except:
    pass

# =========================
# 4) 게시판 로딩 대기
# =========================
try:
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr, table tbody tr'))
    )
    print("✅ 게시판 목록 로딩 성공")
except TimeoutException:
    print("❌ 게시판 로딩 실패")
    print("현재 URL:", driver.current_url)
    try:
        print("페이지 제목:", driver.title)
    except:
        pass
    safe_exit(driver, 0)

# =========================
# 5) 게시글 파싱
# 사이트 구조가 바뀌었을 가능성 고려해서 2가지 방식 지원
# =========================
posts = []

# ---- 방식 A: 기존 ul.pub_list 구조
elements_a = driver.find_elements(By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr')

if elements_a:
    print(f"기존 리스트 구조 감지: {len(elements_a)}개")
    for el in elements_a:
        try:
            title = el.find_element(By.CSS_SELECTOR, 'span.list_tit').text.strip()
            raw_href = el.find_element(By.TAG_NAME, 'a').get_attribute('href')

            post_id = None
            post_url = None

            if raw_href and raw_href.startswith("javascript:goView"):
                m = re.search(r"goView\((\d+)\)", raw_href)
                if m:
                    post_id = m.group(1)
                    post_url = (
                        "https://korhq.ffwp.org/official/"
                        "?mode=view&pageType=officialList&sPage=1&sType=ffwp"
                        f"&sCategory=&listSearch=&document={post_id}#contents"
                    )
            elif raw_href:
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

# ---- 방식 B: 현재 표(table) 구조
if not posts:
    rows = driver.find_elements(By.CSS_SELECTOR, 'table tbody tr')
    print(f"테이블 구조 감지: {len(rows)}개")

    for row in rows:
        try:
            links = row.find_elements(By.TAG_NAME, 'a')
            if not links:
                continue

            a = links[0]
            title = a.text.strip()
            raw_href = a.get_attribute('href')

            if not title:
                continue

            post_id = None
            post_url = None

            if raw_href and "document=" in raw_href:
                m = re.search(r'document=(\d+)', raw_href)
                if m:
                    post_id = m.group(1)
                    post_url = raw_href

            elif raw_href and raw_href.startswith("javascript:goView"):
                m = re.search(r"goView\((\d+)\)", raw_href)
                if m:
                    post_id = m.group(1)
                    post_url = (
                        "https://korhq.ffwp.org/official/"
                        "?mode=view&pageType=officialList&sPage=1&sType=ffwp"
                        f"&sCategory=&listSearch=&document={post_id}#contents"
                    )

            # href에 ID가 없을 경우 onclick도 확인
            if not post_id:
                onclick = a.get_attribute("onclick")
                if onclick:
                    m = re.search(r"goView\((\d+)\)", onclick)
                    if m:
                        post_id = m.group(1)
                        post_url = (
                            "https://korhq.ffwp.org/official/"
                            "?mode=view&pageType=officialList&sPage=1&sType=ffwp"
                            f"&sCategory=&listSearch=&document={post_id}#contents"
                        )

            if post_id:
                posts.append({
                    'id': post_id,
                    'title': title,
                    'href': post_url
                })
        except:
            continue

driver.quit()

print(f"파싱된 게시글 수: {len(posts)}")

if not posts:
    print("❌ 게시글 파싱 실패: posts가 비어 있음")
    sys.exit(0)

# 게시글 ID 기준 최신순 정렬
posts.sort(key=lambda x: int(x['id']), reverse=True)

# =========================
# 6) last_seen 불러오기
# =========================
if os.path.exists(LAST_SEEN_FILE):
    with open(LAST_SEEN_FILE, 'r', encoding='utf-8') as f:
        last_seen = f.read().strip()
else:
    last_seen = ''

print("현재 last_seen:", last_seen)

# sanity check
if last_seen and not last_seen.isdigit():
    print("⚠ last_seen 값이 숫자가 아님. 기준 재설정 후 종료")
    with open(LAST_SEEN_FILE, 'w', encoding='utf-8') as f:
        f.write(posts[0]['id'])
    sys.exit(0)

# 현재 페이지에 last_seen이 없으면 폭탄 방지
current_ids = [p['id'] for p in posts]

if last_seen and last_seen not in current_ids:
    print("⚠ last_seen이 현재 페이지에 없음. 기준 재설정 후 종료")
    with open(LAST_SEEN_FILE, 'w', encoding='utf-8') as f:
        f.write(posts[0]['id'])
    sys.exit(0)

# =========================
# 7) 새 게시글 필터링
# =========================
to_notify = []

if last_seen == '':
    print("Initial run or invalid last_seen. Skipping notifications.")
else:
    for p in posts:
        if p['id'] == last_seen:
            break
        to_notify.append(p)

print(f"🔔 감지된 새 게시글 수: {len(to_notify)}")

# =========================
# 8) 디스코드 전송
# =========================
for p in reversed(to_notify):
    msg = f"📢 **[공지 알림]**\n제목: {p['title']}\n링크: {p['href']}"
    try:
        r = requests.post(WEBHOOK_URL, json={'content': msg}, timeout=10)
        print(f"디스코드 전송: {p['id']} / status={r.status_code}")
    except Exception as e:
        print(f"⚠ 디스코드 전송 실패: {p['id']} / {e}")

# =========================
# 9) last_seen 저장 + git push
# =========================
newest_id = posts[0]['id']

if not os.path.exists(LAST_SEEN_FILE) or open(LAST_SEEN_FILE, encoding='utf-8').read().strip() != newest_id:
    with open(LAST_SEEN_FILE, 'w', encoding='utf-8') as f:
        f.write(newest_id)

    try:
        subprocess.run(['git', 'add', LAST_SEEN_FILE], check=True)
        subprocess.run(
            ['git', 'commit', '-m', f'Update last_seen.txt to {newest_id}'],
            check=True
        )
        subprocess.run(['git', 'push'], check=True)
        print(f"✅ last_seen 업데이트 완료: {newest_id}")
    except subprocess.CalledProcessError as e:
        print("⚠ git 작업 실패 (알림은 정상 전송됨):", e)
else:
    print("last_seen.txt unchanged")
