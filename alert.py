import os
import re
import subprocess
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'

# Git 설정
subprocess.run(['git', 'config', '--global', 'user.name', 'noblefrog96'])
subprocess.run(['git', 'config', '--global', 'user.email', 'noblefrog96@gmail.com'])
subprocess.run([
    'git', 'remote', 'set-url', 'origin',
    f"https://x-access-token:{os.environ['GH_PAT']}@github.com/noblefrog96/alert-python.git"
])

LOGIN_URL = "https://www.ffwp.org/member/login.php"
MAIN_URL = "https://www.ffwp.org/main.php"
KORHQ_HOME = "https://korhq.ffwp.org/"
BOARD_URL = "https://korhq.ffwp.org/official/?sType=ffwp"
BOARD_URL_ALT1 = "https://korhq.ffwp.org/official/"
BOARD_URL_ALT2 = "https://korhq.ffwp.org/official/?#contents"


def load_last_seen():
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, 'r', encoding='utf-8') as f:
            val = f.read().strip()
            return int(val) if val.isdigit() else None
    return None


def save_last_seen(num):
    with open(LAST_SEEN_FILE, 'w', encoding='utf-8') as f:
        f.write(str(num))


def git_commit_and_push(newest_num):
    try:
        subprocess.run(['git', 'add', LAST_SEEN_FILE], check=True)
        subprocess.run(
            ['git', 'commit', '-m', f'Update last_seen.txt to {newest_num}'],
            check=True
        )
        subprocess.run(['git', 'push'], check=True)
        print("✅ last_seen.txt 커밋 & 푸시 완료")
    except subprocess.CalledProcessError as e:
        print("⚠ git 작업 실패 (알림은 정상 동작 가능):", e)


def send_discord_alert(number, title, doc_id):
    view_url = (
        "https://korhq.ffwp.org/official/"
        f"?mode=view&pageType=officialList&sPage=1&sType=ffwp"
        f"&sCategory=&listSearch=&document={doc_id}#contents"
    )

    msg = f"📢 **[공지 알림]**\n번호: {number}\n제목: {title}\n링크: {view_url}"

    try:
        r = requests.post(WEBHOOK_URL, json={'content': msg}, timeout=10)
        print("디스코드 전송 상태:", r.status_code)
    except Exception as e:
        print("⚠ 디스코드 전송 실패:", e)


def dump_cookies(context):
    print("===== 현재 쿠키 =====")
    try:
        cookies = context.cookies()
        for c in cookies:
            print(f"{c.get('name')}={c.get('value')} | domain={c.get('domain')}")
    except Exception as e:
        print("쿠키 출력 실패:", e)
    print("====================")


def try_click_navigation(page, context):
    """
    메인 페이지 안에서 사람이 링크 클릭한 것처럼 korhq 게시판 이동 시도
    """
    print("🔁 클릭 기반 이동 시도 시작")

    # 1차: 동일 탭 클릭
    page.goto(MAIN_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    print("메인 페이지 URL:", page.url)

    page.evaluate(f"""
        (() => {{
            const old = document.getElementById('korhq_link_injected');
            if (old) old.remove();

            const a = document.createElement('a');
            a.href = "{BOARD_URL}";
            a.id = "korhq_link_injected";
            a.target = "_self";
            a.textContent = "go korhq";
            document.body.appendChild(a);
        }})();
    """)

    page.click("#korhq_link_injected")
    page.wait_for_timeout(7000)
    print("게시판 접근 후 URL(클릭 1차):", page.url)

    if "official" in page.url:
        return page

    # 2차: 새 탭 클릭
    print("⚠ 클릭 1차 실패 → 새 탭 클릭 재시도")
    page.goto(MAIN_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    page.evaluate(f"""
        (() => {{
            const old = document.getElementById('korhq_link_injected_2');
            if (old) old.remove();

            const a = document.createElement('a');
            a.href = "{BOARD_URL}";
            a.id = "korhq_link_injected_2";
            a.target = "_blank";
            a.textContent = "go korhq blank";
            document.body.appendChild(a);
        }})();
    """)

    try:
        with context.expect_page(timeout=10000) as new_page_info:
            page.click("#korhq_link_injected_2")

        page2 = new_page_info.value
        page2.wait_for_load_state("domcontentloaded", timeout=60000)
        page2.wait_for_timeout(7000)
        print("게시판 접근 후 URL(클릭 2차):", page2.url)

        if "official" in page2.url:
            return page2
    except Exception as e:
        print("⚠ 새 탭 클릭 실패:", e)

    # 3차: official 루트
    print("⚠ 클릭 2차 실패 → official 루트 접근 재시도")
    page.goto(BOARD_URL_ALT1, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(7000)
    print("게시판 접근 후 URL(루트 3차):", page.url)

    if "official" in page.url:
        return page

    # 4차: #contents 버전
    print("⚠ 루트 3차 실패 → #contents 주소 재시도")
    page.goto(BOARD_URL_ALT2, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(7000)
    print("게시판 접근 후 URL(#contents 4차):", page.url)

    return page


def get_latest_post():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
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
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
        """)

        # 공통 헤더 흉내
        context.set_extra_http_headers({
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1"
        })

        # 1) 로그인 페이지
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        print("로그인 페이지 접근 성공")
        print("현재 URL:", page.url)

        page.wait_for_selector("input[name='userid']", timeout=15000)

        # 2) 로그인
        page.fill("input[name='userid']", os.environ['FFWP_USER'])
        page.fill("input[name='password']", os.environ['FFWP_PW'])
        page.click("#loginSubmit")
        page.wait_for_timeout(5000)

        print("로그인 후 URL:", page.url)
        try:
            print("로그인 후 제목:", page.title())
        except:
            pass

        dump_cookies(context)

        # 3) 메인 페이지 한 번 더 명시적으로
        page.goto(MAIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        print("메인 페이지 URL:", page.url)

        # 4) korhq 홈 먼저 접근
        page.goto(KORHQ_HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        print("KORHQ 홈 접근 후 URL:", page.url)
        try:
            print("KORHQ 홈 제목:", page.title())
        except:
            pass

        dump_cookies(context)

        # 5) 기존 직접 진입 1차
        page.goto(BOARD_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)
        print("게시판 접근 후 URL(직접 1차):", page.url)

        # 6) 기존 직접 진입 2차
        if "official" not in page.url:
            print("⚠ 직접 1차 실패 → 새 탭 직접 진입 재시도")
            page2 = context.new_page()
            page2.goto(KORHQ_HOME, wait_until="domcontentloaded", timeout=60000)
            page2.wait_for_timeout(3000)
            page2.goto(BOARD_URL, wait_until="domcontentloaded", timeout=60000)
            page2.wait_for_timeout(7000)
            print("게시판 접근 후 URL(직접 2차):", page2.url)
            page = page2

        # 7) 기존 직접 진입 3차
        if "official" not in page.url:
            print("⚠ 직접 2차 실패 → JS 이동 재시도")
            page.goto(KORHQ_HOME, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            page.evaluate(f"window.location.href = '{BOARD_URL}'")
            page.wait_for_timeout(7000)
            print("게시판 접근 후 URL(직접 3차):", page.url)

        # 8) 최종 fallback: 클릭 흐름 기반 이동
        if "official" not in page.url:
            print("⚠ 직접 진입 전부 실패 → 클릭 기반 우회 시도")
            page = try_click_navigation(page, context)

        try:
            print("최종 페이지 제목:", page.title())
        except:
            pass

        html = page.content()
        print("페이지 HTML 일부:", html[:3000])

        dump_cookies(context)

        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    total_elem = soup.select_one("#listTotNum")
    if not total_elem:
        print("❌ #listTotNum 못 찾음")
        return None

    latest_number = int(total_elem.get_text(strip=True))

    first_row = soup.select_one("li.c_list_tr")
    if not first_row:
        print("❌ 첫 번째 게시글 행 못 찾음")
        return None

    title_elem = first_row.select_one(".list_tit")
    latest_title = title_elem.get_text(strip=True) if title_elem else "(제목 없음)"

    doc_id = None
    a_tag = first_row.select_one("a[href*='goView']")
    if a_tag and a_tag.has_attr("href"):
        href = a_tag["href"]
        m = re.search(r"goView\((\d+)\)", href)
        if m:
            doc_id = m.group(1)

    print(f"최신 번호: {latest_number}")
    print(f"최신 제목: {latest_title}")
    print(f"문서 ID: {doc_id}")

    return {
        "number": latest_number,
        "title": latest_title,
        "doc_id": doc_id,
    }


def main():
    latest = get_latest_post()
    if not latest:
        print("❌ 최신 게시글 추출 실패")
        return

    current_num = latest["number"]
    current_title = latest["title"]
    current_doc_id = latest["doc_id"]

    last_seen = load_last_seen()
    print("이전 저장 번호:", last_seen)

    if last_seen is None:
        print("⚠ 최초 실행 → 현재 번호 저장만 하고 종료")
        save_last_seen(current_num)
        git_commit_and_push(current_num)
        return

    if current_num > last_seen:
        print("✅ 새 글 감지!")
        send_discord_alert(current_num, current_title, current_doc_id)
        save_last_seen(current_num)
        git_commit_and_push(current_num)
    else:
        print("변경 없음")


if __name__ == "__main__":
    main()
