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

session = requests.Session()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Referer": "https://www.ffwp.org/member/login.php",
    "Origin": "https://www.ffwp.org",
}

# =========================
# 1) 로그인
# =========================
login_payload = {
    "userid": FFWP_USER,
    "password": FFWP_PW
}

try:
    login_res = session.post(LOGIN_URL, data=login_payload, headers=headers, timeout=20)
    print("로그인 응답 URL:", login_res.url)
    print("로그인 상태 코드:", login_res.status_code)
except Exception as e:
    print("❌ 로그인 요청 실패:", e)
    sys.exit(0)

# =========================
# 2) 게시판 페이지 접근
# =========================
board_headers = {
    "User-Agent": headers["User-Agent"],
    "Referer": "https://www.ffwp.org/main.php",
    "Origin": "https://korhq.ffwp.org",
}

try:
    board_res = session.get(BOARD_URL, headers=board_headers, timeout=20)
    print("게시판 접근 URL:", board_res.url)
    print("게시판 접근 상태:", board_res.status_code)
    print("게시판 HTML 일부:\n", board_res.text[:1200])
except Exception as e:
    print("❌ 게시판 접근 실패:", e)
    sys.exit(0)

html = board_res.text

# =========================
# 3) 최신 게시글 번호 추출
# =========================

latest_id = None

# (1) 가장 유력: JS/HTML 내 sTotalRows
m = re.search(r'sTotalRows["\']?\s*[:=]\s*["\']?(\d+)', html)
if m:
    latest_id = m.group(1)
    print("✅ sTotalRows 기반 최신 번호 발견:", latest_id)

# (2) 백업: 게시판 표 첫 번호 추출
if not latest_id:
    m = re.search(r'<td[^>]*>\s*(\d{3,6})\s*</td>', html)
    if m:
        latest_id = m.group(1)
        print("✅ 표 첫 번호 기반 최신 번호 발견:", latest_id)

# (3) 백업: goView/document 기반 번호 추출
if not latest_id:
    ids = re.findall(r'(?:goView\(|document=)(\d+)', html)
    ids = [x for x in ids if x.isdigit()]
    if ids:
        latest_id = max(ids, key=int)
        print("✅ 링크 기반 최신 번호 발견:", latest_id)

if not latest_id:
    print("❌ 최신 게시글 번호를 찾지 못함")
    sys.exit(0)

# =========================
# 4) last_seen 불러오기
# =========================
if os.path.exists(LAST_SEEN_FILE):
    with open(LAST_SEEN_FILE, 'r', encoding='utf-8') as f:
        last_seen = f.read().strip()
else:
    last_seen = ''

print("현재 last_seen:", last_seen)
print("현재 latest_id:", latest_id)

# sanity check
if last_seen and not last_seen.isdigit():
    print("⚠ last_seen 값이 숫자가 아님. 기준 재설정 후 종료")
    with open(LAST_SEEN_FILE, 'w', encoding='utf-8') as f:
        f.write(latest_id)
    sys.exit(0)

# =========================
# 5) 새 글 감지
# =========================
if last_seen == '':
    print("최초 실행 → 알림 없이 기준값만 저장")
elif int(latest_id) > int(last_seen):
    msg = (
        f"📢 **[공지 알림]**\n"
        f"새 공지가 올라왔습니다!\n"
        f"최신 번호: {latest_id}\n"
        f"게시판: {BOARD_URL}"
    )
    try:
        requests.post(WEBHOOK_URL, json={'content': msg}, timeout=10)
        print("✅ 디스코드 알림 전송 완료")
    except Exception as e:
        print("⚠ 디스코드 전송 실패:", e)
else:
    print("새 글 없음")

# =========================
# 6) last_seen 저장 + git push
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
