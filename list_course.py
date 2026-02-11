import requests
from bs4 import BeautifulSoup
from get_course import load_config, load_cookies, is_session_valid, login_and_get_session
import re


def get_all_enrolled_courses(session):
    """Get all enrolled courses from ALL pages."""
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
    page = 1

    while True:
        # Get course record page with pagination
        if page == 1 and initial_response:
            print(f"正在讀取第 1 頁 (使用 SSO 結果)...")
            resp = initial_response
            initial_response = None
        elif page == 1:
            record_url = "https://ap1.elearning.taipei/elearn/courserecord/index.php"
            print(f"正在讀取第 {page} 頁...")
            resp = session.get(record_url)
        else:
            record_url = f"https://ap1.elearning.taipei/elearn/courserecord/index.php?page={page}"
            print(f"正在讀取第 {page} 頁...")
            resp = session.get(record_url)

        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="applySelection")

        if not table:
            print(f"第 {page} 頁找不到課程表格")
            break

        tbody = table.find("tbody")
        if not tbody:
            print(f"第 {page} 頁沒有課程內容")
            break

        rows = tbody.find_all("tr")

        if not rows:
            print(f"第 {page} 頁沒有課程")
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

            # Get study time
            study_time_cell = row.find("td", {"data-column": "修課時間"})
            study_time = ""
            if study_time_cell:
                study_time = study_time_cell.get_text(strip=True)

            all_courses.append({
                'name': course_name,
                'hours': hours,
                'status': status,
                'study_time': study_time,
                'link': course_link
            })
            courses_on_page += 1

        print(f"  → 找到 {courses_on_page} 門課程")

        # Ignore explicit pagination checks and Try to force next page
        # Many PHP sites support ?page=N even if the link is hard to find

        # Check for duplicates to prevent infinite loops (e.g. if page 10 redirects to page 1)
        current_page_courses_signatures = {
            f"{c['name']}_{c['hours']}" for c in all_courses[-courses_on_page:]}
        previous_courses_signatures = {
            f"{c['name']}_{c['hours']}" for c in all_courses[:-courses_on_page]}

        if courses_on_page > 0 and current_page_courses_signatures.issubset(previous_courses_signatures):
            print("  [停止] 本頁課程皆已重複，視為已達最後一頁。")
            break

        print(f"  → 準備嘗試讀取第 {page + 1} 頁...")
        page += 1

        # Safety limit
        if page > 50:
            print("警告：超過 50 頁，停止讀取")
            break

    return all_courses, total_hours


def save_courses_to_file(courses, total_hours, filename="courses.txt"):
    """Save course list to file."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("="*100 + "\n")
        f.write(f"已報名課程總時數: {total_hours:.1f} 小時\n")
        f.write(f"課程總數: {len(courses)}\n")
        f.write("="*100 + "\n\n")

        for i, course in enumerate(courses, 1):
            f.write(f"{i:4}. [{course['hours']:4.1f}h] {course['name']}\n")
            if course['status']:
                f.write(f"       狀態: {course['status']}\n")
            if course['study_time']:
                f.write(f"       修課時間: {course['study_time']}\n")
            f.write("\n")

        f.write("="*100 + "\n")
        f.write(f"總時數: {total_hours:.1f} 小時\n")
        f.write("="*100 + "\n")

    print(f"\n已儲存至: {filename}")


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
        print("✓ 使用已儲存的 Cookie\n")

    if not session:
        print("✗ 登入失敗！")
        return

    # Get all enrolled courses from all pages
    print("="*80)
    print("開始讀取所有已報名課程（檢查所有分頁）...")
    print("="*80 + "\n")

    courses, total_hours = get_all_enrolled_courses(session)

    print("\n" + "="*80)
    print(f"✓ 讀取完成！")
    print(f"  總課程數: {len(courses)}")
    print(f"  總時數: {total_hours:.1f} 小時")
    print("="*80)

    # Display summary
    print(f"\n前 10 門課程:")
    for i, course in enumerate(courses[:10], 1):
        print(f"  {i:2}. [{course['hours']:4.1f}h] {course['name']}")

    if len(courses) > 10:
        print(f"  ... 還有 {len(courses) - 10} 門課程")

    # Save to file
    print(f"\n儲存課程列表到 courses.txt...")
    save_courses_to_file(courses, total_hours, "courses.txt")

    print(f"\n✅ 完成！")
    print(f"   已報名課程總時數: {total_hours:.1f} 小時")
    print(f"   課程總數: {len(courses)}")


if __name__ == "__main__":
    main()
