from playwright.sync_api import sync_playwright
import requests
import os
import re
import subprocess
import sys
import time

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'

FFWP_USER = os.environ['FFWP_USER']
FFWP_PW = os.environ['FFWP_PW']

LOGIN_URL = "https://www.ffwp.org/member/login.php"
MAIN_URL = "https://www.ffwp.org/main.php"
BOARD_URL = "https://korhq.ffwp.org/official/?sType=ffwp"

# =========================
# Git 설정
# =========================
subprocess.run(['git', 'config', '--global', 'user.name', 'noblefrog96'])
subprocess.run(['git', 'config', '--global', 'user.email', 'noblefrog96@gmail.com'])
subprocess.run([
    'git', 'remote', 'set-url', 'origin',
    f"https://x-access-token:{os.environ['GH_PAT']}@github.com/noblefrog96/alert-python.git"
])

def load_last_seen():
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ''

def save_last_seen(value):
    with open(LAST_SEEN_FILE, 'w', encoding='utf-8') as f:
        f.write(str(value))

def git_push_if_changed(newest_id):
    try:
        subprocess.run(['git', 'add', LAST_SEEN_FILE], check=True)
        subprocess.run(['git', 'commit', '-m', f'Update last_seen.txt to {newest_id}'], check=True)
        subprocess.run(['git', 'push'], check=True)
        print("✅ last_seen.txt 푸시 완료")
    except subprocess.CalledProcessError as e:
        print("⚠ git 작업 실패:", e)

def send_discord(msg):
    try:
        requests.post(WEBHOOK_URL, json={'content': msg}, timeout=10)
        print("✅ 디스코드 전송 완료")
    except Exception as e:
        print("⚠ 디스코드 전송 실패:", e)

def extract_posts(html):
    posts = []

    # 게시글 번호 + 제목 + 링크 추출
    # 케이스1: document=1234 링크
    pattern1 = re.findall(
        r'href="([^"]*document=(\d+)[^"]*)"[^>]*>\s*([^<]+?)\s*</a>',
        html,
        re.IGNORECASE
    )

    for href, post_id, title in pattern1:
        title = re.sub(r'\s+', ' ', title).strip()
        if title and post_id.isdigit():
            if href.startswith('/'):
                href = "https://korhq.ffwp.org" + href
            elif href.startswith('?'):
                href = "https://korhq.ffwp.org/official/" + href
            elif not href.startswith('http'):
                href = "https://korhq.ffwp.org/official/" + href

            posts.append({
                "id": post_id,
                "title": title,
                "href": href
            })

    # 케이스2: javascript:goView(1234)
    pattern2 = re.findall(
        r'href="javascript:goView\((\d+)\);"[^>]*>\s*([^<]+?)\s*</a>',
        html,
        re.IGNORECASE
    )

    for post_id, title in pattern2:
        title = re.sub(r'\s+', ' ', title).strip()
        href = (
            "https://korhq.ffwp.org/official/"
            "?mode=view&pageType=officialList&sPage=1&sType=ffwp"
            f"&sCategory=&listSearch=&document={post_id}#contents"
        )
        posts.append({
            "id": post_id,
            "title": title,
            "href": href
        })

    # 중복 제거
    dedup = {}
    for p in posts:
        dedup[p["id"]] = p

    posts = list(dedup.values())
    posts.sort(key=lambda x: int(x["id"]), reverse=True)
    return posts

# =========================
# 브라우저 실행
# =========================
with sync_playwright() as p:
browser = p.chromium.launch(
    headless=True,
    args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process"
    ]
)

context = browser.new_context(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    viewport={"width": 1366, "height": 768},
    locale="ko-KR",
    timezone_id="Asia/Seoul"
)

page = context.new_page()

# 자동화 흔적 숨기기
page.add_init_script("""
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['ko-KR', 'ko', 'en-US', 'en']
});
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32'
});
""")

    try:
        # 1) 로그인 페이지
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        print("로그인 페이지 접근 성공")
        print("현재 URL:", page.url)

        page.fill('input[name="userid"]', FFWP_USER)
        page.fill('input[name="password"]', FFWP_PW)
        page.click('#loginSubmit')

        page.wait_for_load_state("networkidle", timeout=60000)
        print("로그인 후 URL:", page.url)
        print("로그인 후 제목:", page.title())

        # 2) 메인 한번 거치기
        page.goto(MAIN_URL, wait_until="networkidle", timeout=60000)
        print("메인 페이지 URL:", page.url)
        print("메인 페이지 제목:", page.title())

# 3) 게시판 진입 (직접 goto 대신 브라우저 이동 방식 흉내)
page.evaluate(f"window.location.href = '{BOARD_URL}'")
page.wait_for_timeout(7000)

print("게시판 접근 후 URL:", page.url)
print("페이지 제목:", page.title())

# 한 번 더 강제로 이동 시도
if "official" not in page.url:
    print("⚠ 첫 진입 실패 → 새 탭 방식 재시도")
    new_page = context.new_page()
    new_page.goto(BOARD_URL, wait_until="domcontentloaded", timeout=60000)
    new_page.wait_for_timeout(7000)
    page = new_page

print("재확인 URL:", page.url)
print("재확인 제목:", page.title())

        # 혹시 JS 후처리 기다림
        page.wait_for_load_state("networkidle", timeout=30000)

        html = page.content()
        print("페이지 HTML 일부:", html[:3000])

        # 혹시 표가 뜨는지 확인
        if "공문" not in html and "번호" not in html and "제목" not in html:
            print("❌ 게시판 본문 키워드가 HTML에 없음")
            browser.close()
            sys.exit(0)

        posts = extract_posts(html)
        print(f"추출된 게시글 수: {len(posts)}")

        if not posts:
            print("❌ 게시글 추출 실패")
            browser.close()
            sys.exit(0)

        newest = posts[0]
        newest_id = newest["id"]

        print("최신 게시글:", newest)

        last_seen = load_last_seen()
        print("현재 last_seen:", last_seen)

        if last_seen and not last_seen.isdigit():
            print("⚠ last_seen 값 이상 → 재설정")
            save_last_seen(newest_id)
            browser.close()
            sys.exit(0)

        if last_seen == '':
            print("최초 실행 → 알림 없이 기준 저장")
        else:
            new_posts = []
            for p in posts:
                if p["id"] == last_seen:
                    break
                new_posts.append(p)

            print(f"새 게시글 수: {len(new_posts)}")

            for p in reversed(new_posts):
                msg = f"📢 **[공지 알림]**\n제목: {p['title']}\n링크: {p['href']}"
                send_discord(msg)

        if last_seen != newest_id:
            save_last_seen(newest_id)
            git_push_if_changed(newest_id)
        else:
            print("last_seen.txt unchanged")

    except Exception as e:
        print("❌ 실행 중 오류:", e)
        print("현재 URL:", page.url)
        try:
            print("현재 제목:", page.title())
            print("현재 HTML 일부:", page.content()[:3000])
        except:
            pass
    finally:
        browser.close()
