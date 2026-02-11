import requests
from bs4 import BeautifulSoup
from get_course import load_config, load_cookies, is_session_valid, login_and_get_session
import re
import argparse
import time


def get_enrolled_courses(session):
    """Get all enrolled courses from ALL pages using robust pagination."""
    sso_url = "https://elearning.taipei/mpage/sso_moodle?redirectPage=courserecord"
    course_list_url = "https://ap1.elearning.taipei/elearn/courserecord/index.php"

    print(f"[資訊] 存取 SSO: {sso_url}")
    sso_response = session.get(sso_url, allow_redirects=True)
    
    print("   [除錯] SSO Redirect History:")
    for history_resp in sso_response.history:
        print(f"   -> {history_resp.status_code} {history_resp.url}")
    print(f"   -> {sso_response.status_code} {sso_response.url}")

    # Helper function
    def is_course_list_page(text):
        return "課程完成與否" in text or "table__tbody" in text

    # Check if SSO landed us on the correct page
    initial_response = None
    if is_course_list_page(sso_response.text):
        print("[成功] SSO 直接跳轉至課程列表頁面!")
        initial_response = sso_response
    else:
        print("[資訊] SSO 未直接跳轉至課程列表，嘗試手動存取...")
        resp = session.get(course_list_url)
        if is_course_list_page(resp.text):
             print("[成功] 手動存取課程列表成功!")
             initial_response = resp
        else:
             print("[資訊] 偵測到尚未進入學習紀錄頁面 (Validation Failed)，嘗試第二次 SSO 跳轉...")
             sso_response = session.get(sso_url)
             if is_course_list_page(sso_response.text):
                 initial_response = sso_response
             else:
                 # Last resort
                 initial_response = session.get(course_list_url)

    all_courses = []
    total_hours = 0.0
    enrolled_ids = set()
    page = 1

    while True:
        # Get course record page with pagination
        if page == 1 and initial_response:
            print(f"檢查已報名: 使用 SSO 獲取的第 1 頁...")
            resp = initial_response
            # Clear it so we don't reuse it if we somehow loop back to page 1 (unlikely but safe)
            initial_response = None 
        elif page == 1:
             record_url = "https://ap1.elearning.taipei/elearn/courserecord/index.php"
             print(f"檢查已報名: 讀取第 {page} 頁...")
             resp = session.get(record_url)
        else:
            record_url = f"https://ap1.elearning.taipei/elearn/courserecord/index.php?page={page}"
            print(f"檢查已報名: 讀取第 {page} 頁...")
            resp = session.get(record_url)

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="applySelection")

        if not table:
            print(f"  → 找不到表格，結束讀取")
            break

        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else []

        if not rows:
            print(f"  → 沒有課程資料，結束讀取")
            break

        courses_on_page = 0
        for row in rows:
            # Get course name and ID
            name_cell = row.find("td", {"data-column": "課程名稱"})
            if not name_cell:
                continue
            link = name_cell.find("a")
            if not link:
                continue

            course_name = link.get_text(strip=True)
            course_link = link.get("href", "")

            # Extract ID
            match = re.search(r"id=(\d+)", course_link)
            if match:
                enrolled_ids.add(match.group(1))

            # Get hours
            hours_cell = row.find("td", {"data-column": "認證時數"})
            hours = 0.0
            if hours_cell:
                try:
                    hours = float(hours_cell.get_text(strip=True))
                    total_hours += hours
                except ValueError:
                    pass

            # Get completion status
            completion_cell = row.find("td", {"data-column": "課程完成與否"})
            status = ""
            if completion_cell:
                status = completion_cell.get_text(strip=True)

            all_courses.append({
                'name': course_name,
                'hours': hours,
                'status': status,
                'link': course_link
            })
            courses_on_page += 1

        print(f"  → 找到 {courses_on_page} 門課程")

        # Determine if we should continue to next page

        # Check for duplicates to prevent infinite loops
        current_page_courses_signatures = {
            f"{c['name']}_{c['hours']}" for c in all_courses[-courses_on_page:]}
        previous_courses_signatures = {
            f"{c['name']}_{c['hours']}" for c in all_courses[:-courses_on_page]}

        if courses_on_page > 0 and current_page_courses_signatures.issubset(previous_courses_signatures):
            print("  [停止] 本頁課程皆已重複，視為已達最後一頁。")
            break

        # Force next page
        page += 1
        if page > 50:
            print("  [停止] 超過 50 頁安全限制")
            break

    return enrolled_ids, all_courses, total_hours


def enroll_course(session, course_id):
    """Enroll in a course."""
    enroll_url = f"https://ap1.elearning.taipei/elearn/course/view.php?id={course_id}&act=reg"
    resp = session.get(enroll_url, allow_redirects=True)
    return resp.status_code == 200


def search_and_enroll(session, enrolled_ids, current_hours, target_hours=120):
    """Search for courses with no quiz and enroll until target hours."""
    search_url = "https://elearning.taipei/mpage/view_type_list"

    resp = session.get(search_url)
    soup = BeautifulSoup(resp.text, "html.parser")
    token_tag = soup.find("input", {"name": "_token"})
    if not token_tag:
        print("錯誤: 找不到 CSRF token")
        return current_hours

    token = token_tag["value"]

    page = 1
    consecutive_empty_pages = 0

    while current_hours < target_hours:
        print(f"搜尋第 {page} 頁 (目前時數: {current_hours:.1f})")
        payload = {
            "_token": token,
            "search_quiz": "0",
            "search_pages": str(page)
        }

        try:
            resp = session.post(search_url, data=payload, timeout=30)
        except Exception as e:
            print(f"請求失敗: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        course_blocks = soup.find_all(
            "div", class_=re.compile(r"md:col-6.*xl:col-4"))

        if not course_blocks:
            consecutive_empty_pages += 1
            if consecutive_empty_pages > 3:
                break
            page += 1
            continue

        consecutive_empty_pages = 0

        for block in course_blocks:
            if current_hours >= target_hours:
                break

            title_tag = block.find("h2")
            if not title_tag:
                continue
            link = title_tag.find("a")
            if not link:
                continue
            course_name = link.get_text(strip=True)

            hours_tag = block.find("span", class_=re.compile(r"bg-blue"))
            hours = 0.0
            if hours_tag:
                hours_match = re.search(
                    r"(\d+)", hours_tag.get_text(strip=True))
                if hours_match:
                    hours = float(hours_match.group(1))

            # **重點：跳過認證時數 <= 2 的課程**
            if hours <= 2:
                continue

            enroll_btn = block.find("button", class_="btn-black")
            if not enroll_btn:
                continue

            if "已報名" in enroll_btn.get_text():
                continue

            onclick = enroll_btn.get("onclick", "")
            id_match = re.search(r"v=(\d+)", onclick)
            if id_match:
                course_id = id_match.group(1)
                if course_id in enrolled_ids:
                    continue

                print(f"  [報名] {course_name} ({hours}h, ID: {course_id})")
                if enroll_course(session, course_id):
                    current_hours += hours
                    enrolled_ids.add(course_id)
                    time.sleep(1.5)
                else:
                    print(f"    報名失敗")

        page += 1
        if page > 150:
            break

    return current_hours


def save_courses_to_file(courses, total_hours, filename="courses.txt"):
    """Save course list to file."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write(f"已報名課程總時數: {total_hours:.1f} 小時\n")
        f.write(f"課程總數: {len(courses)}\n")
        f.write("="*80 + "\n\n")

        for i, course in enumerate(courses, 1):
            f.write(f"{i:3}. [{course['hours']:4.1f}h] {course['name']}\n")
            if course['status']:
                f.write(f"      狀態: {course['status']}\n")
            f.write("\n")

        f.write("="*80 + "\n")
        f.write(f"總時數: {total_hours:.1f} 小時\n")
        f.write("="*80 + "\n")


def main():
    config = load_config()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    print("正在登入...")
    if not load_cookies(session) or not is_session_valid(session):
        print("Cookie 無效，重新登入...")
        session = login_and_get_session(
            config.get("USER_ID"), config.get("USER_PW"))
    else:
        print("使用已儲存的 Cookie")

    if not session:
        print("登入失敗！")
        return

    # Get current enrolled courses
    print("檢查目前已報名課程...")
    enrolled_ids, courses_list, current_hours = get_enrolled_courses(session)



    # 解析命令列參數
    parser = argparse.ArgumentParser(description='Auto enroll courses to reach target hours.')
    parser.add_argument('--target', type=float, default=120.0, help='Target hours to reach (default: 120)')
    args = parser.parse_args()
    target_enrolled_hours = args.target

    if current_hours >= target_enrolled_hours:
        print(f"✅ 已達到 {target_enrolled_hours} 小時目標！")
    else:
        need_hours = target_enrolled_hours - current_hours
        print(f"⚠️  還需要再報名 {need_hours:.1f} 小時的課程 (目標: {target_enrolled_hours} 小時)")
        print("開始自動報名課程（只報名認證時數 > 2 的課程）...\n")

        # Enroll in more courses
        final_hours = search_and_enroll(
            session, enrolled_ids, current_hours, target_hours=target_enrolled_hours)
        print(f"\n報名完成！最終時數: {final_hours:.1f} 小時")

        # Refresh course list
        print("\n重新取得課程列表...")
        time.sleep(2)  # Wait for system to update
        enrolled_ids, courses_list, current_hours = get_enrolled_courses(
            session)

    # Save to file
    print(f"\n儲存課程列表到 courses.txt...")
    save_courses_to_file(courses_list, current_hours)

    print(f"\n✅ 完成！")
    print(f"已報名課程總時數: {current_hours:.1f} 小時")
    print(f"課程總數: {len(courses_list)}")
    print(f"詳細清單已儲存至: courses.txt")


if __name__ == "__main__":
    main()
