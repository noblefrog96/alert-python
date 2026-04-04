from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
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

# =========================
# 공통 함수
# =========================
def safe_exit(browser=None, code=0):
    try:
        if browser:
            browser.close()
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

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage"
        ]
    )

    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )

    page = context.new_page()

    # 브라우저 흔적 완화
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    try:
        # =========================
        # 1) 로그인 페이지 접속
        # =========================
        page.goto("https://www.ffwp.org/member/login.php", wait_until="domcontentloaded", timeout=60000)
        print("로그인 페이지 접근 성공")
        print("현재 URL:", page.url)

        page.wait_for_selector('input[name="userid"]', timeout=20000)
        page.fill('input[name="userid"]', FFWP_USER)
        page.fill('input[name="password"]', FFWP_PW)

        # 로그인 버튼 클릭
        page.click('#loginSubmit')
        page.wait_for_timeout(5000)

        print("로그인 후 URL:", page.url)
        try:
            print("로그인 후 제목:", page.title())
        except:
            pass

        if "login" in page.url.lower():
            print("❌ 로그인 실패 감지")
            safe_exit(browser, 0)

        # =========================
        # 2) 메인 페이지 안정화
        # =========================
        page.goto("https://www.ffwp.org/main.php", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        print("메인 페이지 URL:", page.url)
        try:
            print("메인 페이지 제목:", page.title())
        except:
            pass

        # 스크롤로 JS 안정화
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1500)
        page.mouse.wheel(0, -3000)
        page.wait_for_timeout(1500)

        # =========================
        # 3) 게시판 이동 시도
        # =========================
        page.goto("https://korhq.ffwp.org/official/?sType=ffwp", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        print("게시판 접근 후 URL:", page.url)
        try:
            print("페이지 제목:", page.title())
        except:
            pass

        # =========================
        # 4) 게시판 목록 로딩 대기
        # =========================
        try:
            page.wait_for_selector("ul.pub_list li.c_list_tr, table tbody tr, a[href*='document='], a[href*='goView']", timeout=60000)
            print("✅ 게시판 목록 로딩 성공")
        except PlaywrightTimeoutError:
            print("❌ 게시판 로딩 실패")
            print("현재 URL:", page.url)
            try:
                print("페이지 제목:", page.title())
            except:
                pass

            # 디버깅용 HTML 일부 출력
            html = page.content()
            print("페이지 HTML 일부:", html[:1500])

            safe_exit(browser, 0)

        # =========================
        # 5) 게시글 파싱
        # =========================
        html = page.content()
        browser.close()

    except Exception as e:
        print("❌ 브라우저 실행 중 예외:", e)
        safe_exit(browser, 0)

# =========================
# 6) HTML에서 게시글 번호 추출
# =========================
# document=숫자 우선 추출
doc_ids = re.findall(r'document=(\d+)', html)

# javascript:goView(숫자)도 같이 추출
goview_ids = re.findall(r'goView\((\d+)\)', html)

all_ids = list(set(doc_ids + goview_ids))
all_ids = [x for x in all_ids if x.isdigit()]

print(f"파싱된 게시글 ID 수: {len(all_ids)}")

if not all_ids:
    print("❌ 게시글 ID 파싱 실패")
    sys.exit(0)

latest_id = max(all_ids, key=int)
print(f"✅ 감지된 최신 게시글 번호: {latest_id}")

# =========================
# 7) last_seen 불러오기
# =========================
if os.path.exists(LAST_SEEN_FILE):
    with open(LAST_SEEN_FILE, 'r', encoding='utf-8') as f:
        last_seen = f.read().strip()
else:
    last_seen = ''

print("현재 last_seen:", last_seen)

if last_seen and not last_seen.isdigit():
    print("⚠ last_seen 값이 숫자가 아님. 기준 재설정 후 종료")
    with open(LAST_SEEN_FILE, 'w', encoding='utf-8') as f:
        f.write(latest_id)
    sys.exit(0)

# =========================
# 8) 새 글 감지
# =========================
if last_seen == '':
    print("최초 실행 또는 last_seen 비어있음 → 알림 없이 기준값만 저장")
elif int(latest_id) > int(last_seen):
    msg = (
        f"📢 **[공지 알림]**\n"
        f"새 공지가 올라왔습니다!\n"
        f"최신 번호: {latest_id}\n"
        f"게시판: https://korhq.ffwp.org/official/?sType=ffwp"
    )
    try:
        requests.post(WEBHOOK_URL, json={'content': msg}, timeout=10)
        print("✅ 디스코드 알림 전송 완료")
    except Exception as e:
        print("⚠ 디스코드 전송 실패:", e)
else:
    print("새 글 없음")

# =========================
# 9) last_seen 저장 + git push
# =========================
if last_seen != latest_id:
    with open(LAST_SEEN_FILE, 'w', encoding='utf-8') as f:
        f.write(latest_id)

    try:
        subprocess.run(['git', 'add', LAST_SEEN_FILE], check=True)
        subprocess.run(
            ['git', 'commit', '-m', f'Update last_seen.txt to {latest_id}'],
            check=True
        )
        subprocess.run(['git', 'push'], check=True)
        print("✅ last_seen.txt 업데이트 및 푸시 완료")
    except subprocess.CalledProcessError as e:
        print("⚠ git 작업 실패 (알림은 정상 전송 가능):", e)
else:
    print("last_seen.txt unchanged")
