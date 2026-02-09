import re
import os
from dataclasses import dataclass
from typing import List, Optional

from utils import Files, parse_time_to_minutes, calculate_remaining_time


@dataclass
class CourseResult:
    remaining_min: int
    link: str
    course_name: str
    output: str


def parse_course_block(block: str) -> Optional[CourseResult]:
    """解析單個課程區塊"""
    block = block.strip()
    match = re.search(r"^\s*\d+\.\s*(.+)", block)
    if not match:
        return None

    course_name = match.group(1).split("\n")[0].strip()

    cert_match = re.search(r"認證時數:\s*([^\n\r]+)", block)
    # 支援舊格式 "完成條件時數: 90分" 與新格式 "完成條件為：閱讀時間達90分鐘以上"
    target_req_match = re.search(r"(?:完成條件時數:|完成條件為[：:])\s*([^\n\r]+)", block)
    study_match = re.search(r"修課時間:\s*([^\n\r]+)", block)
    link_match = re.search(r"連結:\s*([^\n\r]+)", block)

    if cert_match and link_match:
        cert_str = cert_match.group(1).strip()
        target_req_str = target_req_match.group(
            1).strip() if target_req_match else None
        study_str = study_match.group(1).strip() if study_match else "0分"
        link = link_match.group(1).strip()

        remaining_min = calculate_remaining_time(
            cert_str, study_str, target_req_str)

        if target_req_str:
            target_desc = f"條件 {parse_time_to_minutes(target_req_str)} 分鐘"
        else:
            target_desc = f"目標 {int(parse_time_to_minutes(cert_str) / 2)} 分鐘 (認證/2)"

        print(
            f"解析：{course_name} - {target_desc} - 已上課 {parse_time_to_minutes(study_str)} 分鐘 -> 剩餘 {remaining_min} 分鐘"
        )

        return CourseResult(
            remaining_min=remaining_min,
            link=link,
            course_name=course_name,
            output=f"{remaining_min}|{link}|{course_name}"
        )

    return None


def read_course_file(file_path: str) -> str:
    """讀取課程檔案"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到檔案 '{file_path}'")

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def write_results(results: List[CourseResult], file_path: str) -> None:
    """寫入結果到檔案"""
    results.sort(key=lambda x: x.remaining_min)

    with open(file_path, "w", encoding="utf-8") as out_f:
        for item in results:
            out_f.write(item.output + "\n")


def main():
    """主函數"""
    try:
        content = read_course_file(Files.INCOMPLETE_COURSES)
    except FileNotFoundError as e:
        print(f"錯誤: {e}")
        return

    # 以數字開頭的行來切割不同的課程區塊
    blocks = re.split(r"\n(?=\d+\.)", content)

    results = []
    for block in blocks:
        result = parse_course_block(block)
        if result:
            results.append(result)

    write_results(results, Files.URLS_TXT)
    print(f"\n已完成排序，結果已儲存至 {Files.URLS_TXT}")


if __name__ == "__main__":
    main()
