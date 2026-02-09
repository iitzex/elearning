"""
共享工具模組，包含兩個檔案都會用到的通用功能
"""

from dataclasses import dataclass
import re
from typing import Optional


@dataclass
class Files:
    """檔案名稱常量"""

    CONFIG = "id.confg"
    COOKIES = "cookies.json"
    CAPTCHA = "captcha.png"
    DEBUG_COURSES = "debug_courserecord.html"
    INCOMPLETE_COURSES = "incomplete_courses.txt"
    URLS_TXT = "urls.txt"


def parse_time_to_minutes(time_str: Optional[str]) -> int:
    """將時間字串轉換為總分鐘數

    支援格式：
    - "1小時30分" -> 90
    - "1.5" -> 90 (視為小時)
    - "40分" -> 40
    - "2時" -> 120
    """
    if not time_str:
        return 0

    time_str = time_str.strip()
    total_min = 0

    # 匹配小時 (支援 "1小時"、"1時"、"1 小時"、"1 時")
    hr_match = re.search(r"(\d+)\s*(?:小時|時)", time_str)
    if hr_match:
        total_min += int(hr_match.group(1)) * 60

    # 匹配分鐘 (支援 "40分" 或 "40 分")
    min_match = re.search(r"(\d+)\s*分", time_str)
    if min_match:
        total_min += int(min_match.group(1))

    # 如果完全沒對應到小時或分鐘，但有純數字，則視為小時 (針對認證時數純數字情況)
    if total_min == 0 and re.match(r"^\d+(\.\d+)?$", time_str):
        try:
            return int(float(time_str) * 60)
        except ValueError:
            pass

    return total_min


def calculate_remaining_time(cert_str: str, study_str: str, target_str: Optional[str] = None) -> int:
    """計算剩餘時間：目標時間 - 已上課時間
    如果提供了 target_str (例如 "完成條件時數")，則優先使用它作為目標。
    否則預設使用 認證時數的一半 作為目標。
    """
    if target_str:
        target_min = parse_time_to_minutes(target_str)
    else:
        target_min = int(parse_time_to_minutes(cert_str) / 2)

    study_min = parse_time_to_minutes(study_str)
    remaining_min = target_min - study_min
    return max(remaining_min, 0)
