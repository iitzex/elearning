#!/bin/bash

# 設定腳本路徑（取得此腳本所在的絕對路徑）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "============================================================"
echo "步驟 1: 從臺北 e 大獲取未完成課程名單"
echo "============================================================"
python3 -u "$SCRIPT_DIR/get_course.py"

# 檢查上一步是否成功執行
if [ $? -ne 0 ]; then
    echo "錯誤: get_course.py 執行失敗，請檢查登入資訊或驗證碼。"
    exit 1
fi

echo ""
echo "============================================================"
echo "步驟 2: 計算剩餘時間並產生 URL 清單"
echo "============================================================"
python3 -u "$SCRIPT_DIR/gen_url.py"

if [ $? -ne 0 ]; then
    echo "錯誤: gen_url.py 執行失敗。"
    exit 1
fi

echo ""
echo "============================================================"
echo "步驟 3: 自動依序上課 (開啟網頁 -> 等待倒數 -> 開啟下一個)"
echo "============================================================"
if [ -f "$SCRIPT_DIR/urls.txt" ]; then
    total_courses=$(wc -l < "$SCRIPT_DIR/urls.txt")
    current_count=0
    
    while read -r line; do
        current_count=$((current_count + 1))
        # 分離分鐘數與 URL (格式: 分鐘 URL)
        min=$(echo "$line" | awk '{print $1}')
        url=$(echo "$line" | awk '{print $2}')
        
        if [[ "$url" == http* ]]; then
            echo "------------------------------------------------------------"
            echo "正在處理第 $current_count/$total_courses 個課程"
            echo "剩餘所需時間: $min 分鐘"
            echo "網址: $url"
            echo "------------------------------------------------------------"
            
            # 開啟網頁
            echo "正在開啟網頁，請在瀏覽器中手動完成登入..."
            open "$url"
            
            # 如果分鐘數大於 0，進行倒數
            if [ "$min" -gt 0 ]; then
                wait_seconds=$((min * 60))
                echo "開始計時 $min 分鐘 ($wait_seconds 秒)..."
                
                # 簡單的倒數顯示
                while [ $wait_seconds -gt 0 ]; do
                    printf "\r剩餘時間: %02d:%02d " $((wait_seconds/60)) $((wait_seconds%60))
                    sleep 1
                    wait_seconds=$((wait_seconds - 1))
                done
                echo -e "\n時間到！"
            else
                echo "此課程剩餘時間為 0。"
            fi
            
            # 在課程間插入 1 分鐘等待 (如果還有下一個課程)
            if [ $current_count -lt $total_courses ]; then
                echo "等待 1 分鐘再開啟下一個課程，以避免操作過於頻繁..."
                sleep 60
            fi
        fi
    done < "$SCRIPT_DIR/urls.txt"
    echo "所有課程已依序開啟完畢！"
else
    echo "找不到 urls.txt，跳過步驟。"
fi

echo ""
echo "============================================================"
echo "任務完全結束！"
echo "============================================================"