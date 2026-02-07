import re
import os

def parse_time_to_minutes(time_str):
    """將時間字串轉換為總分鐘數"""
    if not time_str:
        return 0
    
    # 如果字串純粹是數字，預設為小時 (針對認證時數欄位)
    if time_str.isdigit():
        return int(time_str) * 60
        
    total_min = 0
    # 匹配小時
    hr_match = re.search(r'(\d+)\s*小時', time_str)
    if hr_match:
        total_min += int(hr_match.group(1)) * 60
    
    # 匹配分鐘
    min_match = re.search(r'(\d+)\s*分', time_str)
    if min_match:
        total_min += int(min_match.group(1))
    
    # 匹配秒數（若有秒數，進位 1 分鐘）
    sec_match = re.search(r'(\d+)\s*秒', time_str)
    if sec_match:
        if int(sec_match.group(1)) > 0:
            total_min += 1
            
    return total_min

def main():
    input_file = "incomplete_courses.txt"
    output_file = "urls.txt"
    
    if not os.path.exists(input_file):
        print(f"錯誤: 找不到檔案 '{input_file}'")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 以數字開頭的行來切割不同的課程區塊
    blocks = re.split(r'\n(?=\d+\.)', content)
    
    results = []
    for block in blocks:
        if not re.search(r'^\s*\d+\.', block.strip()):
            continue
            
        cert_match = re.search(r'認證時數:\s*([^\n\r]+)', block)
        study_match = re.search(r'修課時間:\s*([^\n\r]+)', block)
        link_match = re.search(r'連結:\s*([^\n\r]+)', block)
        
        if cert_match and link_match:
            cert_str = cert_match.group(1).strip()
            study_str = study_match.group(1).strip() if study_match else "0分"
            link = link_match.group(1).strip()
            
            # 解析為分鐘
            cert_min = parse_time_to_minutes(cert_str)
            study_min = parse_time_to_minutes(study_str)
            
            # 計算剩餘分鐘數 (認證時數 / 2 - 修課時間)
            remaining_min = int(cert_min / 2) - study_min
            if remaining_min < 0:
                remaining_min = 0
            
            # 儲存資訊以便排序
            results.append({
                'remaining_min': remaining_min,
                'link': link,
                'output': f"{remaining_min} {link}"
            })
            print(f"解析：{cert_str}/2 ({int(cert_min/2)}分) - {study_str}({study_min}分) -> 剩餘 {remaining_min}分")

    # 依照剩餘分鐘數排序（由短到長）
    results.sort(key=lambda x: x['remaining_min'])
    
    # 儲存到 urls.txt
    with open(output_file, "w", encoding="utf-8") as out_f:
        for item in results:
            out_f.write(item['output'] + "\n")
            
    print(f"\n已完成排序，結果已儲存至 {output_file}")

if __name__ == "__main__":
    main()
