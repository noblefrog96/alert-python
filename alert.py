import requests
import os
import subprocess
import re

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'
FFWP_COOKIE = os.environ['FFWP_COOKIE']

# Git 설정
subprocess.run(['git', 'config', '--global', 'user.name', 'noblefrog96'])
subprocess.run(['git', 'config', '--global', 'user.email', 'noblefrog96@gmail.com'])
subprocess.run([
    'git', 'remote', 'set-url', 'origin',
    f"https://x-access-token:{os.environ['GH_PAT']}@github.com/noblefrog96/alert-python.git"
])

# -------------------------------------------------
# 1) 세션 생성 + 브라우저 쿠키 주입
# -------------------------------------------------
session = requests.Session()

common_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Cookie": FFWP_COOKIE
}
session.headers.update(common_headers)

print("✅ 쿠키 주입 완료")

# -------------------------------------------------
# 2) 게시판 페이지 접근
# -------------------------------------------------
board_page_url = "https://korhq.ffwp.org/official/?sType=ffwp"

try:
    board_page_res = session.get(board_page_url, timeout=20)
    print("게시판 접근 URL:", board_page_res.url)
    print("게시판 접근 상태:", board_page_res.status_code)
    print("게시판 HTML 일부:", board_page_res.text[:500])
except Exception as e:
    print("❌ 게시판 접근 실패:", e)
    exit(0)

# 접근 차단 여부 체크
if "login.php" in board_page_res.url.lower() or "main.php" in board_page_res.url.lower():
    print("❌ 게시판 접근이 차단됨 (로그인 세션 무효 또는 권한 문제)")
    exit(0)

# -------------------------------------------------
# 3) function_ajax.php 호출
# -------------------------------------------------
ajax_url = "https://korhq.ffwp.org/include/function_ajax.php"

ajax_headers = {
    "Referer": "https://korhq.ffwp.org/official/?sType=ffwp",
    "Origin": "https://korhq.ffwp.org",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
}

payload = {
    "pageType": "pagingList",
    "sPage": "1",
    "sPageBlock": "10",
    "sTotalRows": "0",
    "sMaxRows": "30"
}

try:
    ajax_res = session.post(ajax_url, data=payload, headers=ajax_headers, timeout=20)
    print("AJAX 상태 코드:", ajax_res.status_code)
    print("AJAX 응답 일부:", ajax_res.text[:1000])
except Exception as e:
    print("❌ AJAX 호출 실패:", e)
    exit(0)

# -------------------------------------------------
# 4) 최신 게시글 번호 추출
# -------------------------------------------------
# 응답 안에서 4~6자리 숫자 후보 추출
matches = re.findall(r'\b\d{4,6}\b', ajax_res.text)

# 너무 작은 숫자(예: 10, 30 같은 설정값) 제외용
matches = [m for m in matches if int(m) >= 1000]

if not matches:
    print("❌ 최신 게시글 번호를 찾지 못함")
    exit(0)

latest_id = max(matches, key=int)
print(f"✅ 감지된 최신 게시글 번호: {latest_id}")

# -------------------------------------------------
# 5) last_seen 불러오기
# -------------------------------------------------
if os.path.exists(LAST_SEEN_FILE):
    with open(LAST_SEEN_FILE, 'r', encoding='utf-8') as f:
        last_seen = f.read().strip()
else:
    last_seen = ''

# sanity check
if last_seen and not last_seen.isdigit():
    print("⚠ last_seen 값이 숫자가 아님. 기준 재설정 후 종료")
    with open(LAST_SEEN_FILE, 'w', encoding='utf-8') as f:
        f.write(latest_id)
    exit(0)

# -------------------------------------------------
# 6) 새 글 감지
# -------------------------------------------------
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

# -------------------------------------------------
# 7) last_seen.txt 업데이트 + git push
# -------------------------------------------------
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
        print("⚠ git 작업 실패 (알림은 정상 동작 가능):", e)
else:
    print("last_seen.txt unchanged")
