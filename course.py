import os
import re
import requests
from bs4 import BeautifulSoup


def extract_course_info(file_path):
    """從主頁面 HTML 提取課程名稱、連結和完成狀態"""
    print(f"[讀取檔案] {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    courses = []

    # 尋找包含課程列的表格主體
    tbody = soup.find('tbody', class_='table__tbody')
    if tbody:
        rows = tbody.find_all('tr', class_='table-row')
        for row in rows:
            course_cell = row.find('td', {'data-column': '課程名稱'})
            hours_cell = row.find('td', {'data-column': '認證時數'})
            study_time_cell = row.find('td', {'data-column': '修課時間'})
            completion_cell = row.find('td', {'data-column': '課程完成與否'})

            if course_cell:
                link_tag = course_cell.find('a', class_='href')
                if link_tag:
                    course_name = link_tag.get_text(strip=True)
                    course_link = link_tag.get('href')

                    # 提取認證時數
                    hours = ""
                    if hours_cell:
                        hours_p = hours_cell.find('p')
                        if hours_p:
                            hours = hours_p.get_text(strip=True)

                    # 提取修課時間（已上課累計時間）
                    study_time = ""
                    if study_time_cell:
                        study_time_link = study_time_cell.find('a')
                        if study_time_link:
                            study_time = study_time_link.get_text(strip=True)

                    # 提取完成狀態
                    completion_status = "未知"
                    if completion_cell:
                        completion_p = completion_cell.find('p')
                        if completion_p:
                            completion_status = completion_p.get_text(strip=True)

                    courses.append({
                        'name': course_name,
                        'link': course_link,
                        'hours': hours,
                        'study_time': study_time,
                        'completion_status': completion_status
                    })
    print(f"[資訊] 找到 {len(courses)} 個課程")
    return courses


def login_and_get_session(username, password):
    """登入並返回 session 對象"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })

    login_page_url = "https://elearning.taipei/mpage/login"
    login_do_url = "https://elearning.taipei/mpage/do-login"
    captcha_img_url = "https://elearning.taipei/mpage/captcha"

    print(f"[登入] 正在準備登入帳號: {username}...")

    try:
        # 1. 獲取 CSRF token
        response = session.get(login_page_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        token_input = soup.find('input', {'name': '_token'})

        if not token_input:
            print("[警告] 找不到 CSRF token。")
            token = ""
        else:
            token = token_input['value']

        # 2. 獲取驗證碼圖片
        print("[資訊] 正在下載驗證碼...")
        captcha_resp = session.get(captcha_img_url)
        with open("captcha.png", "wb") as f:
            f.write(captcha_resp.content)
        
        # 3. 開啟驗證碼圖片 (適用於 Mac)
        import subprocess
        subprocess.run(["open", "captcha.png"])
        
        # 4. 停下等待用戶輸入
        captcha_code = input("\n[等待輸入] 請查看開啟的 captcha.png 並在此輸入驗證碼: ")

        # 準備登入資料
        payload = {
            '_token': token,
            'username': username,
            'password': password,
            'captcha': captcha_code
        }

        # 5. 執行登入
        response = session.post(login_do_url, data=payload)

        # 檢查是否登入成功
        if "logout" in response.text.lower() or "個人選單" in response.text or "訪客" not in response.text:
            print("[成功] 登入成功!")
        else:
            print("[失敗] 登入失敗，請檢查帳號密碼或驗證碼是否正確。")
            # 刪除已使用的驗證碼圖片
            if os.path.exists("captcha.png"):
                os.remove("captcha.png")
            return login_and_get_session(username, password) # 嘗試重新登入

        # 登入成功後刪除驗證碼圖片
        if os.path.exists("captcha.png"):
            os.remove("captcha.png")
            
        return session

    except Exception as e:
        print(f"[錯誤] 登入過程中發生異常: {e}")
        return session


def get_scorm_links_with_session(session, url):
    """使用 session 獲取頁面內容，處理跳轉並解析 SCORM 連結"""
    try:
        print(f"   [讀取中] {url}...")
        response = session.get(url)
        content = response.text

        # 處理 <script>location.href = "/elearn/courseinfo/so.php?v=5508";</script> 形式的跳轉
        js_redirect = re.search(
            r'location\.href\s*=\s*["\']([^"\']+)["\']', content)
        if js_redirect:
            redirect_url = js_redirect.group(1)
            if redirect_url.startswith('/'):
                redirect_url = "https://ap2.elearning.taipei" + redirect_url
            print(f"   [跳轉中] {redirect_url}...")
            response = session.get(redirect_url)
            content = response.text

        soup = BeautifulSoup(content, 'html.parser')
        scorm_links = []

        # 目標網址模式
        pattern = 'https://ap2.elearning.taipei/elearn/mod/scorm/view.php?id='

        # 1. 尋找所有 <a> 標籤
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            if href.startswith(pattern):
                scorm_links.append(href)

        # 2. 正則表達式備案 (搜尋整個內容)
        matches = re.findall(
            rf'https://ap2\.elearning\.taipei/elearn/mod/scorm/view\.php\?id=\d+', content)
        scorm_links.extend(matches)

        return sorted(list(set(scorm_links)))  # 去重並排序
    except Exception as e:
        print(f"   [錯誤] 解析過程發生問題: {e}")
        return []


def check_course_completion(session, course_url):
    """檢查課程是否已完成，並提取已上課時間"""
    try:
        response = session.get(course_url)
        content = response.text
        
        # 處理 JavaScript 跳轉
        js_redirect = re.search(r'location\.href\s*=\s*["\']([^"\']+)["\']', content)
        if js_redirect:
            redirect_url = js_redirect.group(1)
            if redirect_url.startswith('/'):
                redirect_url = "https://ap2.elearning.taipei" + redirect_url
            response = session.get(redirect_url)
            content = response.text
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # 提取已上課時間
        study_times = []
        
        # 方法1: 查找時間記錄（常見格式：YYYY-MM-DD HH:MM 或 YYYY/MM/DD）
        time_patterns = [
            r'\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}',  # 2024-01-15 14:30
            r'\d{4}[-/]\d{2}[-/]\d{2}',  # 2024-01-15
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, content)
            study_times.extend(matches)
        
        # 方法2: 查找包含"上課時間"、"學習時間"、"完成時間"等關鍵字的區域
        time_keywords = ['上課時間', '學習時間', '完成時間', '觀看時間', '學習日期']
        for keyword in time_keywords:
            # 查找關鍵字後面的時間
            keyword_pattern = keyword + r'[：:]\s*([^\n<]+)'
            matches = re.findall(keyword_pattern, content)
            study_times.extend(matches)
        
        # 方法3: 從表格中提取時間資訊
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    # 檢查是否包含日期格式
                    for pattern in time_patterns:
                        matches = re.findall(pattern, cell_text)
                        study_times.extend(matches)
        
        # 去重並排序
        study_times = sorted(list(set(study_times)))
        
        # 檢查是否有完成標記
        progress = None
        is_completed = None
        
        # 方法1: 查找進度百分比
        progress_indicators = soup.find_all(string=re.compile(r'(\d+)%'))
        for indicator in progress_indicators:
            match = re.search(r'(\d+)%', indicator)
            if match:
                progress = int(match.group(1))
                if progress == 100:
                    is_completed = True
                else:
                    is_completed = False
                break
        
        # 方法2: 查找完成狀態文字
        if is_completed is None:
            completion_texts = ['已完成', '完成', 'Completed', '100%']
            for text in completion_texts:
                if text in content:
                    is_completed = True
                    progress = 100
                    break
        
        # 方法3: 查找未完成狀態
        if is_completed is None:
            incomplete_texts = ['未完成', '進行中', 'In Progress']
            for text in incomplete_texts:
                if text in content:
                    is_completed = False
                    if progress is None:
                        progress = 0
                    break
        
        # 尋找 SCORM 連結
        scorm_link = None
        # 依照使用者提示，搜尋包含 "/elearn/mod/scorm/view.ph" 的網址
        scorm_pattern = "/elearn/mod/scorm/view.ph"
        
        # 1. 從所有 <a> 標籤尋找
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            if scorm_pattern in href:
                if href.startswith('/'):
                    scorm_link = "https://ap2.elearning.taipei" + href
                else:
                    scorm_link = href
                break
        
        # 2. 如果沒找到，用正則表達式搜整個內容（包含 JavaScript 中的網址）
        if not scorm_link:
            # 搜尋包含 scorm/view.php?id= 數字的模式
            matches = re.findall(r'https?://[^\s"\'<>]+/elearn/mod/scorm/view\.php\?id=\d+', content)
            if not matches:
                matches = re.findall(r'["\'](/elearn/mod/scorm/view\.php\?id=\d+)["\']', content)
                if matches:
                    scorm_link = "https://ap2.elearning.taipei" + matches[0]
            else:
                scorm_link = matches[0]
        
        if not scorm_link:
             # 再試一次更廣泛的搜尋
             matches = re.findall(r'[/a-zA-Z0-9\._\-]*scorm/view\.php\?id=\d+', content)
             if matches:
                 if matches[0].startswith('/'):
                     scorm_link = "https://ap2.elearning.taipei" + matches[0]
                 elif matches[0].startswith('http'):
                     scorm_link = matches[0]
                 else:
                     scorm_link = "https://ap2.elearning.taipei/elearn/mod/" + matches[0]

        if scorm_link:
            print(f"   [找到 SCORM 連結] {scorm_link}")
        else:
            print(f"   [警告] 找不到 SCORM 連結")

        return is_completed, progress, study_times, scorm_link
        
    except Exception as e:
        print(f"   [錯誤] 檢查課程時發生問題: {e}")
        return None, None, [], None


def load_config(config_file="id.confg"):
    """從設定檔讀取帳號密碼"""
    config = {}
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    config[key] = value
    return config


if __name__ == '__main__':
    # 從 id.confg 讀取帳號密碼
    config = load_config()
    USER_ID = config.get("USER_ID", "")
    USER_PW = config.get("USER_PW", "")

    if not USER_ID or not USER_PW:
        print("錯誤: 請確保 id.confg 中包含 USER_ID 和 USER_PW")
        exit(1)

    main_file = 'course.html'
    if not os.path.exists(main_file):
        print(f"錯誤: 在此路徑找不到檔案 '{main_file}'")
        exit(1)
    
    # 提取課程資訊
    print("=" * 60)
    print("正在提取課程資訊...")
    print("=" * 60)
    courses = extract_course_info(main_file)
    
    # 先根據 HTML 中的完成狀態進行初步分類
    print("\n" + "=" * 60)
    print("正在分析課程狀態...")
    print("=" * 60)
    
    incomplete_courses = []
    completed_courses = []
    unknown_courses = []
    
    # 統計課程狀態
    for course in courses:
        status = course.get('completion_status', '未知')
        print(f"\n課程: {course['name']}")
        print(f"   狀態: {status}")
        
        if status == '已完成':
            completed_courses.append({
                'name': course['name'],
                'link': course['link'],
                'hours': course['hours'],
                'study_time': course.get('study_time', ''),
                'progress': 100,
                'study_times': []
            })
        elif status == '未完成':
            incomplete_courses.append({
                'name': course['name'],
                'link': course['link'],
                'hours': course['hours'],
                'study_time': course.get('study_time', ''),
                'progress': None,
                'study_times': []
            })
        else:
            unknown_courses.append({
                'name': course['name'],
                'link': course['link'],
                'hours': course['hours'],
                'study_time': course.get('study_time', ''),
                'progress': None,
                'study_times': []
            })
    
    # 如果有未完成的課程，登入並獲取詳細資訊
    if incomplete_courses:
        print("\n" + "=" * 60)
        print("正在登入學習平台獲取詳細資訊...")
        print("=" * 60)
        session = login_and_get_session(USER_ID, USER_PW)
        
        print("\n" + "=" * 60)
        print("正在檢查未完成課程的詳細資訊...")
        print("=" * 60)
        
        for i, course in enumerate(incomplete_courses, 1):
            print(f"\n[{i}/{len(incomplete_courses)}] 檢查: {course['name']}")
            is_completed, progress, study_times, scorm_link = check_course_completion(session, course['link'])
            
            # 更新課程資訊
            course['progress'] = progress if progress is not None else 0
            course['study_times'] = study_times
            if scorm_link:
                course['scorm_link'] = scorm_link
            
            if study_times:
                print(f"   📅 上課時間: {', '.join(study_times[:3])}{'...' if len(study_times) > 3 else ''}")
    
    # 顯示結果
    print("\n" + "=" * 60)
    print("檢查結果摘要")
    print("=" * 60)
    print(f"總課程數: {len(courses)}")
    print(f"已完成: {len(completed_courses)}")
    print(f"未完成: {len(incomplete_courses)}")
    print(f"狀態未知: {len(unknown_courses)}")
    
    if incomplete_courses:
        print("\n" + "=" * 60)
        print("未完成的課程列表")
        print("=" * 60)
        for i, course in enumerate(incomplete_courses, 1):
            print(f"\n{i}. {course['name']}")
            print(f"   認證時數: {course['hours']} 小時")
            if course.get('study_time'):
                print(f"   修課時間: {course['study_time']}")
            if course['progress'] is not None:
                print(f"   進度: {course['progress']}%")
            if course.get('study_times'):
                print(f"   📅 上課時間: {', '.join(course['study_times'])}")
            print(f"   連結: {course['link']}")
    
    if unknown_courses:
        print("\n" + "=" * 60)
        print("狀態未知的課程列表")
        print("=" * 60)
        for i, course in enumerate(unknown_courses, 1):
            print(f"\n{i}. {course['name']}")
            print(f"   時數: {course['hours']}")
            print(f"   連結: {course['link']}")
    
    # 儲存結果到檔案
    with open('incomplete_courses.txt', 'w', encoding='utf-8') as f:
        f.write("未完成的課程列表\n")
        f.write("=" * 60 + "\n\n")
        for i, course in enumerate(incomplete_courses, 1):
            f.write(f"{i}. {course['name']}\n")
            f.write(f"   認證時數: {course['hours']} 小時\n")
            if course.get('study_time'):
                f.write(f"   修課時間: {course['study_time']}\n")
            if course['progress'] is not None:
                f.write(f"   進度: {course['progress']}%\n")
            if course.get('study_times'):
                f.write(f"   上課時間: {', '.join(course['study_times'])}\n")
            # 優先寫入 SCORM 連結，若無則寫入原始連結
            link_to_save = course.get('scorm_link', course['link'])
            f.write(f"   連結: {link_to_save}\n\n")
    
    print("\n" + "=" * 60)
    print("結果已儲存至 incomplete_courses.txt")
    print("=" * 60)
