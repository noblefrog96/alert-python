import requests
import os
import re
import subprocess
import sys

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'

FFWP_USER = os.environ['FFWP_USER']
FFWP_PW = os.environ['FFWP_PW']

LOGIN_URL = "https://www.ffwp.org/member/login.php"
MAIN_URL = "https://www.ffwp.org/main.php"
BOARD_URL = "https://korhq.ffwp.org/official/?sType=ffwp"
AJAX_URL = "https://korhq.ffwp.org/include/function_ajax.php"

# =========================
# Git 설정
# =========================
subprocess.run(['git', 'config', '--global', 'user.name', 'noblefrog96'])
subprocess.run(['git', 'config', '--global', 'user.email', 'noblefrog96@gmail.com'])
subprocess.run([
    'git', 'remote', 'set-url', 'origin',
    f"https://x-access-token:{os.environ['GH_PAT']}@github.com/noblefrog96/alert-python.git"
])

session = requests.Session()

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    "Accept-Language": "ko,en;q=0.9,en-US;q=0.8",
}

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

def login():
    try:
        # 로그인 페이지 한번 열기
        r1 = session.get(LOGIN_URL, headers=COMMON_HEADERS, timeout=20)
        print("로그인 페이지 접근:", r1.status_code, r1.url)

        payload = {
            "userid": FFWP_USER,
            "password": FFWP_PW
        }

        headers = COMMON_HEADERS.copy()
        headers.update({
            "Referer": LOGIN_URL,
            "Origin": "https://www.ffwp.org",
            "Content-Type": "application/x-www-form-urlencoded"
        })

        r2 = session.post(LOGIN_URL, data=payload, headers=headers, timeout=20, allow_redirects=True)
        print("로그인 응답 URL:", r2.url)
        print("로그인 상태 코드:", r2.status_code)

        # 메인 페이지 한번 접근
        r3 = session.get(MAIN_URL, headers=COMMON_HEADERS, timeout=20)
        print("메인 페이지 접근:", r3.status_code, r3.url)

        print("현재 세션 쿠키:")
        for c in session.cookies:
            print(f"  {c.name}={c.value} (domain={c.domain})")

    except Exception as e:
        print("❌ 로그인 실패:", e)
        sys.exit(0)

def try_board_page():
    """
    게시판 document 직접 접근 시도
    """
    try:
        headers = COMMON_HEADERS.copy()
        headers.update({
            "Referer": MAIN_URL,
            "Origin": "https://korhq.ffwp.org"
        })

        r = session.get(BOARD_URL, headers=headers, timeout=20, allow_redirects=True)
        print("게시판 접근 URL:", r.url)
        print("게시판 접근 상태:", r.status_code)
        print("게시판 HTML 일부:\n", r.text[:2000])

        return r.text, r.url
    except Exception as e:
        print("❌ 게시판 접근 실패:", e)
        return "", ""

def extract_latest_from_html(html):
    """
    HTML에서 최신 게시글 번호 / 제목 / 링크 추출
    """
    posts = []

    # 1) goView(숫자)
    matches = re.findall(r'goView\((\d+)\)', html)
    for post_id in matches:
        if post_id.isdigit():
            href = (
                "https://korhq.ffwp.org/official/"
                "?mode=view&pageType=officialList&sPage=1&sType=ffwp"
                f"&sCategory=&listSearch=&document={post_id}#contents"
            )
            posts.append({
                "id": post_id,
                "title": f"게시글 {post_id}",
                "href": href
            })

    # 2) document=숫자
    matches = re.findall(r'document=(\d+)', html)
    for post_id in matches:
        if post_id.isdigit():
            href = (
                "https://korhq.ffwp.org/official/"
                "?mode=view&pageType=officialList&sPage=1&sType=ffwp"
                f"&sCategory=&listSearch=&document={post_id}#contents"
            )
            posts.append({
                "id": post_id,
                "title": f"게시글 {post_id}",
                "href": href
            })

    # 3) 표 첫 번호 추정
    matches = re.findall(r'<td[^>]*>\s*(\d{3,6})\s*</td>', html)
    for post_id in matches:
        if post_id.isdigit():
            href = (
                "https://korhq.ffwp.org/official/"
                "?mode=view&pageType=officialList&sPage=1&sType=ffwp"
                f"&sCategory=&listSearch=&document={post_id}#contents"
            )
            posts.append({
                "id": post_id,
                "title": f"게시글 {post_id}",
                "href": href
            })

    # 중복 제거
    dedup = {}
    for p in posts:
        dedup[p["id"]] = p

    posts = list(dedup.values())
    posts.sort(key=lambda x: int(x["id"]), reverse=True)

    if posts:
        print("HTML 기반 후보 게시글들:", posts[:10])
        return posts[0]

    return None

def try_ajax_with_guess(last_seen):
    """
    function_ajax.php 우회 시도
    핵심: sTotalRows를 대충 현재 추정값으로 넣고 응답 확인
    """
    guess_total = 8600  # 기본 추정치

    if last_seen.isdigit():
        guess_total = max(int(last_seen), 8600)

    payload = {
        "pageType": "pagingList",
        "sPage": "1",
        "sPageBlock": "10",
        "sTotalRows": str(guess_total),
        "sMaxRows": "30"
    }

    headers = COMMON_HEADERS.copy()
    headers.update({
        "Accept": "text/plain, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://korhq.ffwp.org",
        "Referer": BOARD_URL
    })

    try:
        r = session.post(AJAX_URL, data=payload, headers=headers, timeout=20)
        print("AJAX 상태 코드:", r.status_code)
        print("AJAX 응답 일부:\n", r.text[:1500])

        # 응답 내 마지막 페이지 계산 힌트
        page_moves = re.findall(r'pageMove\((\d+)\)', r.text)
        if page_moves:
            print("AJAX 응답 pageMove 후보:", page_moves[:20])

        # 여기선 직접 최신 게시글 번호는 못 얻더라도
        # 현재 totalRows 추정치가 맞는지 보조 힌트로 사용
        return True
    except Exception as e:
        print("❌ AJAX 요청 실패:", e)
        return False

# =========================
# 실행
# =========================
login()

last_seen = load_last_seen()
print("현재 last_seen:", last_seen)

html, final_url = try_board_page()

latest_post = None

# 1차: HTML 직접 파싱
if html:
    latest_post = extract_latest_from_html(html)

# 2차: HTML 실패 시 AJAX 힌트 확인
if not latest_post:
    print("⚠ HTML에서 최신 게시글 추출 실패 → AJAX 보조 시도")
    try_ajax_with_guess(last_seen)

# 3차: 최후 fallback
if not latest_post:
    # 만약 게시판 문서 접근이 막혀도, 최신 번호를 last_seen+1 정도로 추정하는 건 위험해서 금지
    print("❌ 최신 게시글 번호를 찾지 못함")
    sys.exit(0)

latest_id = latest_post["id"]
print("최종 최신 게시글:", latest_post)

# sanity check
if last_seen and not last_seen.isdigit():
    print("⚠ last_seen 값 이상 → 재설정")
    save_last_seen(latest_id)
    sys.exit(0)

# =========================
# 알림 처리
# =========================
if last_seen == '':
    print("최초 실행 → 알림 없이 기준 저장")
elif int(latest_id) > int(last_seen):
    msg = (
        f"📢 **[공지 알림]**\n"
        f"제목: {latest_post['title']}\n"
        f"링크: {latest_post['href']}"
    )
    send_discord(msg)
else:
    print("새 글 없음")

# =========================
# 저장 + 푸시
# =========================
if last_seen != latest_id:
    save_last_seen(latest_id)
    git_push_if_changed(latest_id)
else:
    print("last_seen.txt unchanged")
