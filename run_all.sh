#!/bin/bash

# 設定腳本路徑（取得此腳本所在的絕對路徑）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

while true; do
    echo "============================================================"
    echo "開始執行自動上課檢查流程 (時間: $(date))"
    echo "============================================================"

    echo "步驟 1: 從臺北 e 大獲取未完成課程名單"
    python3 -u "$SCRIPT_DIR/get_course.py"

    if [ $? -ne 0 ]; then
        echo "警告: get_course.py 執行可能失敗，1 分鐘後重試..."
        sleep 60
        continue
    fi

    echo ""
    echo "步驟 2: 計算剩餘時間並產生 URL 清單"
    python3 -u "$SCRIPT_DIR/gen_url.py"

    if [ $? -ne 0 ]; then
        echo "錯誤: gen_url.py 執行失敗。"
        sleep 60
        continue
    fi

    echo ""
    echo "步驟 3: 自動依序上課 (開啟網頁 -> 等待倒數 -> 重新檢查)"
    if [ -f "$SCRIPT_DIR/urls.txt" ] && [ -s "$SCRIPT_DIR/urls.txt" ]; then
        total_courses=$(wc -l < "$SCRIPT_DIR/urls.txt")
        current_count=0
        recheck_needed=false
        RELOAD_INTERVAL=30  # 設定每 30 分鐘重新載入一次
        
        while read -r line; do
            current_count=$((current_count + 1))
            min=$(echo "$line" | awk '{print $1}')
            url=$(echo "$line" | awk '{print $2}')
            
            if [[ "$url" == http* ]]; then
                echo "------------------------------------------------------------"
                echo "正在處理第 $current_count/$total_courses 個課程"
                echo "剩餘所需時間: $min 分鐘"
                
                # 為了確保瀏覽器真的會重新載入，我們在網址後加上時間戳記
                timestamp=$(date +%s)
                if [[ "$url" == *\?* ]]; then
                    url_to_open="${url}&t=${timestamp}"
                else
                    url_to_open="${url}?t=${timestamp}"
                fi
                
                echo "網址: $url"
                echo "------------------------------------------------------------"
                
                open "$url_to_open"
                
                # 設定本次等待時間，最多為 RELOAD_INTERVAL 分鐘
                wait_min=$min
                limit_reached=false
                if [ "$wait_min" -gt "$RELOAD_INTERVAL" ]; then
                    wait_min=$RELOAD_INTERVAL
                    limit_reached=true
                fi

                if [ "$wait_min" -gt 0 ]; then
                    wait_seconds=$((wait_min * 60))
                    echo "開始計時 $wait_min 分鐘 ($wait_seconds 秒)..."
                    
                    if [ "$limit_reached" = true ]; then
                        echo "提示: 此課程時間較長，將於 $RELOAD_INTERVAL 分鐘後重新載入頁面以確保進度更新。"
                    fi
                    
                    while [ $wait_seconds -gt 0 ]; do
                        printf "\r剩餘時間: %02d:%02d " $((wait_seconds/60)) $((wait_seconds%60))
                        sleep 1
                        wait_seconds=$((wait_seconds - 1))
                    done
                    echo -e "\n時間到！"
                else
                    echo "此課程剩餘時間為 0。"
                fi
                
                if [ "$limit_reached" = true ]; then
                    echo "已達到 $RELOAD_INTERVAL 分鐘等待上限，將重新執行檢查並重新載入頁面..."
                    recheck_needed=true
                    break
                fi

                # 在課程間插入 1 分鐘等待 (如果還有下一個課程)
                if [ $current_count -lt $total_courses ]; then
                    echo "等待 1 分鐘再開啟下一個課程，以避免操作過於頻繁..."
                    sleep 60
                fi
            fi
        done < "$SCRIPT_DIR/urls.txt"
        
        if [ "$recheck_needed" = true ]; then
            continue
        fi
        
        echo "目前的課程清單已處理完畢，將再次檢查是否還有未完成課程..."
        sleep 10
    else
        echo "找不到未完成課程或 urls.txt 為空，任務圓滿結束！"
        break
    fi
done

echo ""
echo "============================================================"
echo "任務完全結束！"
echo "============================================================"