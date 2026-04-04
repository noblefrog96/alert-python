from playwright.sync_api import sync_playwright
import requests
import os
import re
import subprocess
import sys
import json

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'
STORAGE_STATE_JSON = os.environ['FFWP_STORAGE_STATE']


def safe_exit(code=0):
    sys.exit(code)


# Git 설정
subprocess.run(['git', 'config', '--global', 'user.name', 'noblefrog96'])
subprocess.run(['git', 'config', '--global', 'user.email', 'noblefrog96@gmail.com'])
subprocess.run([
    'git', 'remote', 'set-url', 'origin',
    f"https://x-access-token:{os.environ['GH_PAT']}@github.com/noblefrog96/alert-python.git"
])

# storage_state 로드
try:
    storage_state = json.loads(STORAGE_STATE_JSON)
    print("✅ storage_state 로드 완료")
except Exception as e:
    print("❌ storage_state JSON 파싱 실패:", e)
    safe_exit(0)

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage'
        ]
    )

    context = browser.new_context(
        storage_state=storage_state,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="ko-KR",
        viewport={"width": 1920, "height": 1080}
    )

    page = context.new_page()

    # -------------------------
    # 게시판 접근
    # -------------------------
    try:
        page.goto("https://korhq.ffwp.org/official/?sType=ffwp", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
    except Exception as e:
        print("❌ 게시판 URL 접속 실패:", e)
        page.screenshot(path="debug_board_goto_fail.png")
        browser.close()
        safe_exit(0)

    print("게시판 접근 후 URL:", page.url)
    print("페이지 제목:", page.title())

    try:
        page.wait_for_selector("ul.pub_list li.c_list_tr", timeout=60000)
    except Exception as e:
        print("❌ 게시판 로딩 실패:", e)
        print("현재 URL:", page.url)
        print("페이지 제목:", page.title())
        page.screenshot(path="debug_board_fail.png")
        with open("debug_board_fail.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        browser.close()
        safe_exit(0)

    # -------------------------
    # 게시글 수집
    # -------------------------
    elements = page.query_selector_all("ul.pub_list li.c_list_tr")
    posts = []

    for el in elements:
        try:
            title = el.query_selector("span.list_tit").inner_text().strip()
            raw_href = el.query_selector("a").get_attribute("href")

            post_id = None
            post_url = None

            if raw_href and raw_href.startswith("javascript:goView"):
                m = re.search(r"goView\((\d+)\)", raw_href)
                if m:
                    post_id = m.group(1)
                    post_url = f"https://korhq.ffwp.org/official/?mode=view&pageType=officialList&sPage=1&sType=ffwp&document={post_id}#contents"
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

        except Exception as e:
            print("⚠ 게시글 파싱 스킵:", e)
            continue

    browser.close()

# 게시글 없으면 종료
if not posts:
    print("❌ 게시글 0개 → 종료")
    safe_exit(0)

posts.sort(key=lambda x: int(x['id']), reverse=True)

print("📄 게시글 수:", len(posts))
print("🆕 최신 ID:", posts[0]['id'])
print("📝 최신 제목:", posts[0]['title'])

# -------------------------
# last_seen 읽기
# -------------------------
if os.path.exists(LAST_SEEN_FILE):
    with open(LAST_SEEN_FILE, 'r') as f:
        last_seen = f.read().strip()
else:
    last_seen = ''

print("💾 last_seen:", last_seen)

# 이상값 방지
if last_seen and not last_seen.isdigit():
    print("⚠ last_seen 비정상 → 초기화")
    with open(LAST_SEEN_FILE, 'w') as f:
        f.write(posts[0]['id'])
    safe_exit(0)

current_ids = [p['id'] for p in posts]

if last_seen and last_seen not in current_ids:
    print("⚠ 기준 글이 현재 페이지에 없음 → 초기화")
    with open(LAST_SEEN_FILE, 'w') as f:
        f.write(posts[0]['id'])
    safe_exit(0)

# -------------------------
# 새 글 필터
# -------------------------
to_notify = []

if last_seen:
    for p in posts:
        if p['id'] == last_seen:
            break
        to_notify.append(p)

print("🔔 새 글 수:", len(to_notify))
for p in to_notify[:5]:
    print(f"➡ {p['id']} | {p['title']}")

# -------------------------
# 디스코드 전송
# -------------------------
if not to_notify:
    print("ℹ️ 새 글 없음 → 디스코드 전송 안 함")

for p in reversed(to_notify):
    try:
        requests.post(
            WEBHOOK_URL,
            json={'content': f"📢 **[공지 알림]**\n제목: {p['title']}\n링크: {p['href']}"},
            timeout=10
        )
    except Exception as e:
        print("⚠ 디스코드 전송 실패:", e)

# -------------------------
# last_seen 업데이트
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
