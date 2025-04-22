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

WEBHOOK_URL = os.environ['DISCORD_WEBHOOK']
LAST_SEEN_FILE = 'last_seen.txt'

# Git 설정 (푸시를 위해 필요)
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

driver = webdriver.Chrome(options=options)

# 1) 로그인
driver.get('https://www.ffwp.org/member/login.php')
driver.find_element(By.NAME, 'userid').send_keys(os.environ['FFWP_USER'])
driver.find_element(By.NAME, 'password').send_keys(os.environ['FFWP_PW'])
driver.find_element(By.ID, 'loginSubmit').click()
time.sleep(2)

# 2) 게시판 접속
driver.get('https://korhq.ffwp.org/official/?sType=ffwp')
WebDriverWait(driver, 30).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr'))
)

# 3) 게시글 리스트 긁기
elements = driver.find_elements(By.CSS_SELECTOR, 'ul.pub_list li.c_list_tr')
posts = []
for el in elements:
    title = el.find_element(By.CSS_SELECTOR, 'span.list_tit').text.strip()
    raw_href = el.find_element(By.TAG_NAME, 'a')._
