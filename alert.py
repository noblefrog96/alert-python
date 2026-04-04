import os
import re
import subprocess
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'

# =========================
# Git 설정
# =========================
subprocess.run(['git', 'config', '--global', 'user.name', 'noblefrog96'])
subprocess.run(['git', 'config', '--global', 'user.email', 'noblefrog96@gmail.com'])
subprocess.run([
    'git', 'remote', 'set-url', 'origin',
    f"https://x-access-token:{os.environ['GH_PAT']}@github.com/noblefrog96/alert-python.git"
])

LOGIN_URL = "https://www.ffwp.org/member/login.php"
BOARD_URL = "https://korhq.ffwp.org/official/?sType=ffwp"


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


def get_latest_post():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )

        page = browser.new_page()

        # 1) 로그인 페이지
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        print("로그인 페이지 접근 성공")
        print("현재 URL:", page.url)

        # 2) 로그인 입력창 대기
        page.wait_for_selector("input[name='userid']", timeout=15000)

        # 3) 로그인
        page.fill("input[name='userid']", os.environ['FFWP_USER'])
        page.fill("input[name='password']", os.environ['FFWP_PW'])
        page.click("#loginSubmit")
        page.wait_for_timeout(3000)

        print("로그인 후 URL:", page.url)
        try:
            print("로그인 후 제목:", page.title())
        except:
            pass

        # 4) 게시판 접근
        page.goto(BOARD_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        print("게시판 접근 후 URL:", page.url)
        try:
            print("페이지 제목:", page.title())
        except:
            pass

        html = page.content()
        print("페이지 HTML 일부:", html[:2000])

        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # 최신 번호
    total_elem = soup.select_one("#listTotNum")
    if not total_elem:
        print("❌ #listTotNum 못 찾음")
        return None

    latest_number = int(total_elem.get_text(strip=True))

    # 첫 번째 게시글
    first_row = soup.select_one("li.c_list_tr")
    if not first_row:
        print("❌ 첫 번째 게시글 행 못 찾음")
        return None

    # 제목
    title_elem = first_row.select_one(".list_tit")
    latest_title = title_elem.get_text(strip=True) if title_elem else "(제목 없음)"

    # 문서 ID
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
