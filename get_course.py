import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import requests
from bs4 import BeautifulSoup

from utils import Files, parse_time_to_minutes

try:
    import ddddocr
except ImportError:
    ddddocr = None


@dataclass
class URLs:
    LOGIN_PAGE = "https://elearning.taipei/mpage/login"
    LOGIN_DO = "https://elearning.taipei/mpage/do-login"
    CAPTCHA = "https://elearning.taipei/mpage/captcha"
    HOME = "https://elearning.taipei/mpage/"
    SSO = "https://elearning.taipei/mpage/sso_moodle?redirectPage=courserecord"
    COURSE_LIST = "https://ap2.elearning.taipei/elearn/courserecord/index.php"
    AP2_BASE = "https://ap2.elearning.taipei"


@dataclass
class Headers:
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# 使用 utils 中的 Files 類別


@dataclass
class CourseInfo:
    name: str
    link: str
    hours: str = ""
    study_time: str = ""
    completion_status: str = "未知"
    progress: Optional[int] = None
    study_times: Optional[List[str]] = None
    scorm_link: Optional[str] = None
    required_time_str: Optional[str] = None

    def __post_init__(self):
        if self.study_times is None:
            self.study_times = []


class LoginError(Exception):
    """登录失败异常"""

    pass


class SessionExpiredError(Exception):
    """会话过期异常"""

    pass


def extract_course_info_from_html(html_content: str) -> List[CourseInfo]:
    """從 HTML 內容提取課程名稱、連結和完成狀態"""
    soup = BeautifulSoup(html_content, "html.parser")
    courses = []

    # 尋找包含課程列的表格主體
    tbody = soup.find("tbody", class_="table__tbody")
    if not tbody:
        # 嘗試尋找一般的 table
        tbody = soup.find("tbody")

    if tbody:
        rows = tbody.find_all("tr")
        for row in rows:
            course_cell = row.find("td", {"data-column": "課程名稱"})
            hours_cell = row.find("td", {"data-column": "認證時數"})
            study_time_cell = row.find("td", {"data-column": "修課時間"})
            completion_cell = row.find("td", {"data-column": "課程完成與否"})

            # 如果找不到 data-column，則按順序嘗試 (針對不同的頁面結構)
            if not course_cell:
                cells = row.find_all("td")
                if len(cells) >= 4:
                    course_cell = cells[1]
                    hours_cell = cells[2]
                    study_time_cell = cells[3]
                    completion_cell = cells[4] if len(cells) > 4 else None

            if course_cell:
                link_tag = course_cell.find("a")
                if link_tag:
                    course_name = link_tag.get_text(strip=True)
                    course_link = link_tag.get("href")
                    if course_link and course_link.startswith("/"):
                        course_link = URLs.AP2_BASE + course_link

                    # 提取認證時數
                    hours = ""
                    if hours_cell:
                        hours = hours_cell.get_text(strip=True)

                    # 提取修課時間
                    study_time = ""
                    if study_time_cell:
                        study_time = study_time_cell.get_text(strip=True)

                    # 提取完成狀態
                    completion_status = "未知"
                    if completion_cell:
                        completion_status = completion_cell.get_text(
                            strip=True)

                    courses.append(
                        CourseInfo(
                            name=course_name,
                            link=course_link,
                            hours=hours,
                            study_time=study_time,
                            completion_status=completion_status,
                        )
                    )
    return courses


def login_and_get_session(username: str, password: str) -> Optional[requests.Session]:
    """登入並返回 session 對象"""
    session = requests.Session()
    session.headers.update({"User-Agent": Headers.USER_AGENT})

    print(f"[登入] 正在準備登入帳號: {username}...")

    try:
        token = _get_csrf_token(session)
        captcha_code = _get_captcha_code(session)

        payload = {
            "_token": token,
            "username": username,
            "password": password,
            "captcha": captcha_code,
        }

        response = session.post(URLs.LOGIN_DO, data=payload)

        if _is_login_successful(response, session):
            print("[成功] 登入成功!")
            return session
        else:
            print("[失敗] 登入失敗，請檢查帳號密碼或驗證碼。")
            if "驗證碼" in response.text:
                print("[提示] 驗證碼錯誤。")
            _cleanup_captcha()
            return None

    except Exception as e:
        print(f"[錯誤] 登入過程中發生異常: {e}")
        _cleanup_captcha()
        return None


def _get_csrf_token(session: requests.Session) -> str:
    """獲取 CSRF token"""
    response = session.get(URLs.LOGIN_PAGE)
    soup = BeautifulSoup(response.text, "html.parser")
    token_input = soup.find("input", {"name": "_token"})

    if not token_input:
        print("[警告] 找不到 CSRF token。")
        return ""
    return token_input["value"]


def _get_captcha_code(session: requests.Session) -> str:
    """獲取驗證碼"""
    print("[資訊] 正在下載驗證碼...")
    captcha_resp = session.get(URLs.CAPTCHA)

    with open(Files.CAPTCHA, "wb") as f:
        f.write(captcha_resp.content)

    # 嘗試自動辨識驗證碼
    if ddddocr:
        try:
            print("[資訊] 正在自動辨識驗證碼...")
            ocr = ddddocr.DdddOcr(show_ad=False)
            captcha_code = ocr.classification(captcha_resp.content)
            print(f"[成功] 自動辨識結果: {captcha_code}")
            return captcha_code
        except Exception as ocr_err:
            print(f"[警告] OCR 辨識失敗: {ocr_err}")

    # 手動輸入驗證碼
    import subprocess

    subprocess.run(["open", Files.CAPTCHA])
    return input("\n[等待輸入] 請查看開啟的 captcha.png 並在此輸入驗證碼: ")


def _is_login_successful(
    response: requests.Response, session: requests.Session
) -> bool:
    """檢查登入是否成功"""
    # 檢查登入回應
    if (
        "logout" in response.text.lower()
        or "登出" in response.text
        or "個人選單" in response.text
    ):
        return True

    # 檢查首頁
    try:
        test_resp = session.get(URLs.HOME)
        if "logout" in test_resp.text.lower() or "登出" in test_resp.text:
            return True
    except:
        pass

    return False


def _cleanup_captcha():
    """清理驗證碼檔案"""
    if os.path.exists(Files.CAPTCHA):
        os.remove(Files.CAPTCHA)


def check_course_completion(
    session: requests.Session, course_url: str
) -> Tuple[Optional[bool], Optional[int], List[str], Optional[str]]:
    """檢查課程詳細資訊"""
    try:
        content = _get_course_content(session, course_url)
        soup = BeautifulSoup(content, "html.parser")

        study_times = _extract_study_times(content)
        progress, is_completed = _extract_progress_info(soup, content)
        scorm_link = _extract_scorm_link(soup, content)

        # 提取完成條件中的閱讀時間
        required_time_str = None
        req_match = re.search(r"完成條件為[：:]\s*閱讀時間達\d+分鐘以上", content)
        if req_match:
            required_time_str = req_match.group(0)

        return is_completed, progress, study_times, scorm_link, required_time_str

    except Exception as e:
        print(f"   [錯誤] 檢查課程時發生問題: {e}")
        return None, None, [], None


def _get_course_content(session: requests.Session, course_url: str) -> str:
    """獲取課程內容，處理 JavaScript 跳轉"""
    response = session.get(course_url)
    content = response.text

    # 處理 JavaScript 跳轉
    js_redirect = re.search(
        r'location\.href\s*=\s*["\']([^"\']+)["\']', content)
    if js_redirect:
        redirect_url = js_redirect.group(1)
        if redirect_url.startswith("/"):
            redirect_url = URLs.AP2_BASE + redirect_url
        response = session.get(redirect_url)
        content = response.text

    return content


def _extract_study_times(content: str) -> List[str]:
    """提取上課時間"""
    time_patterns = [
        r"\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}",
        r"\d{4}[-/]\d{2}[-/]\d{2}",
    ]

    study_times = []
    for pattern in time_patterns:
        matches = re.findall(pattern, content)
        study_times.extend(matches)

    return sorted(list(set(study_times)))


def _extract_progress_info(
    soup: BeautifulSoup, content: str
) -> Tuple[Optional[int], Optional[bool]]:
    """提取進度資訊"""
    progress = None
    is_completed = None

    # 進度檢查
    progress_indicators = soup.find_all(string=re.compile(r"(\d+)%"))
    for indicator in progress_indicators:
        match = re.search(r"(\d+)%", indicator)
        if match:
            progress = int(match.group(1))
            is_completed = progress == 100
            break

    if is_completed is None:
        if any(text in content for text in ["已完成", "完成", "Completed"]):
            is_completed = True
            progress = 100
        elif any(text in content for text in ["未完成", "進行中", "In Progress"]):
            is_completed = False
            progress = progress if progress is not None else 0

    return progress, is_completed


def _extract_scorm_link(soup: BeautifulSoup, content: str) -> Optional[str]:
    """提取 SCORM 連結"""
    # 從連結中查找
    scorm_pattern = "/elearn/mod/scorm/view.ph"
    links = soup.find_all("a", href=True)
    for link in links:
        href = link["href"]
        if scorm_pattern in href:
            return URLs.AP2_BASE + href if href.startswith("/") else href

    # 從內容中查找
    match = re.search(
        r'https?://[^\s"\'<>]+/elearn/mod/scorm/view\.php\?id=\d+', content
    )
    if match:
        return match.group(0)

    return None


def save_cookies(session: requests.Session, filename: str = Files.COOKIES) -> None:
    """儲存 session cookies 到檔案"""
    with open(filename, "w") as f:
        json.dump(requests.utils.dict_from_cookiejar(session.cookies), f)
    print(f"[資訊] Cookies 已儲存至 {filename}")


def load_cookies(session: requests.Session, filename: str = Files.COOKIES) -> bool:
    """從檔案載入 cookies 到 session"""
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                cookies = json.load(f)
                session.cookies.update(
                    requests.utils.cookiejar_from_dict(cookies))
            print(f"[資訊] 已從 {filename} 載入 Cookies")
            return True
        except Exception as e:
            print(f"[警告] 載入 Cookies 失敗: {e}")
    return False


def is_session_valid(session: requests.Session) -> bool:
    """檢查 session 是否仍然有效 (檢查主網域)"""
    try:
        response = session.get(URLs.HOME, timeout=10)
        # 如果頁面包含 "登出" 或 "個人選單"，表示主網域 Session 有效
        return (
            "logout" in response.text.lower()
            or "登出" in response.text
            or "個人選單" in response.text
        )
    except Exception as e:
        print(f"[警告] 檢查 Session 有效性時發生錯誤: {e}")
        return False


def load_config(config_file: str = Files.CONFIG) -> Dict[str, str]:
    """從設定檔讀取帳號密碼"""
    config = {}
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    config[key] = value
    return config


if __name__ == "__main__":
    # 從 id.confg 讀取帳號密碼
    config = load_config()
    USER_ID = config.get("USER_ID", "")
    USER_PW = config.get("USER_PW", "")

    if not USER_ID or not USER_PW:
        print("錯誤: 請確保 id.confg 中包含 USER_ID 和 USER_PW")
        exit(1)

    # 初始化 Session
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )

    # 嘗試載入舊的 Session
    logged_in = False
    if load_cookies(session):
        print("[資訊] 正在檢查舊 Session 是否有效...")
        if is_session_valid(session):
            print("[成功] Session 仍然有效，跳過登入步驟。")
            logged_in = True
        else:
            print("[資訊] Session 已失效，準備重新登入。")

    if not logged_in:
        # 1. 登入
        print("=" * 60)
        print("正在登入學習平台...")
        print("=" * 60)

        # 重新獲取 session (避免舊 cookies 干擾)
        session = login_and_get_session(USER_ID, USER_PW)

        if not session:
            print("\n[錯誤] 無法繼續執行，因為登入失敗。")
            exit(1)

        # 儲存新的 cookies
        save_cookies(session)

    # 2. 獲取課程名單頁面 (強制透過 SSO)
    print("\n" + "=" * 60)
    print("正在獲取課程名單 (透過 SSO)...")
    print("=" * 60)

    sso_url = "https://elearning.taipei/mpage/sso_moodle?redirectPage=courserecord"
    course_list_url = "https://ap2.elearning.taipei/elearn/courserecord/index.php"

    # 強制執行 SSO 以確保 ap2 網域的 session 被初始化
    session.get(sso_url)
    response = session.get(course_list_url)

    # 檢查是否真的拿到了課程頁面 (檢查欄位名稱)
    if "課程名稱" not in response.text and "認證時數" not in response.text:
        print("[資訊] 偵測到尚未進入學習紀錄頁面，嘗試第二次 SSO 跳轉...")
        session.get(sso_url)
        response = session.get(course_list_url)

    # Debug: 儲存 HTML 以便檢查結構
    with open(Files.DEBUG_COURSES, "w", encoding="utf-8") as f:
        f.write(response.text)

    courses = extract_course_info_from_html(response.text)

    if not courses:
        print(
            f"[警告] 找不到任何課程。請檢查 {Files.DEBUG_COURSES} 以確認頁面內容是否正確。"
        )
        # 如果是讀取舊 cookie 導致的失敗，刪除它
        if logged_in and os.path.exists(Files.COOKIES):
            print("[提示] 可能是 Session 已過期但檢查通過，下次執行將重新登入。")
            os.remove(Files.COOKIES)
    else:
        print(f"[資訊] 總共找到 {len(courses)} 個課程")

    # 3. 過濾未完成課程
    incomplete_courses = []
    for course in courses:
        if "未完成" in course.completion_status or "進行中" in course.completion_status:
            incomplete_courses.append(course)
            print(f"發現未完成課程: {course.name}")

    # 4. 檢查詳細資訊
    if incomplete_courses:
        print("\n" + "=" * 60)
        print("正在檢查未完成課程的詳細資訊 (SCORM 連結與進度)...")
        print("=" * 60)

        for i, course in enumerate(incomplete_courses, 1):
            print(f"\n[{i}/{len(incomplete_courses)}] 檢查: {course.name}")
            is_completed, progress, study_times, scorm_link, required_time_str = check_course_completion(
                session, course.link
            )

            course.required_time_str = required_time_str
            if required_time_str:
                print(f"   [找到完成條件] {required_time_str}")

            course.progress = progress if progress is not None else 0
            course.study_times = study_times
            if scorm_link:
                course.scorm_link = scorm_link
                print(f"   [找到 SCORM 連結] {scorm_link}")

    # 5. 輸出結果
    print("\n" + "=" * 60)
    print("檢查結果摘要")
    print("=" * 60)
    print(f"未完成課程數: {len(incomplete_courses)}")

    with open(Files.INCOMPLETE_COURSES, "w", encoding="utf-8") as f:
        f.write("未完成的課程列表 (從網路即時下載)\n")
        f.write("=" * 60 + "\n\n")
        for i, course in enumerate(incomplete_courses, 1):
            f.write(f"{i}. {course.name}\n")
            f.write(f"   認證時數: {course.hours}\n")
            if course.required_time_str:
                f.write(f"   {course.required_time_str}\n")
            if course.study_time:
                f.write(f"   修課時間: {course.study_time}\n")
            if course.progress is not None:
                f.write(f"   進度: {course.progress}%\n")
            if course.study_times:
                f.write(f"   上課時間: {', '.join(course.study_times)}\n")

            link_to_save = course.scorm_link or course.link
            f.write(f"   連結: {link_to_save}\n\n")

    print(f"\n結果已儲存至 {Files.INCOMPLETE_COURSES}")
