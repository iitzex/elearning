#!/bin/bash

FILE="urls.txt"

while IFS= read -r line || [ -n "$line" ]; do
    # 忽略空行或註解
    [[ -z "$line" || "$line" =~ ^# ]] && continue

    # 拆分分鐘與網址
    minute=$(echo "$line" | awk '{print $1}')
    url=$(echo "$line" | awk '{print $2}')
    seconds=$((minute * 60))

    echo "🔗 開啟網址：$url（$minute 分鐘）"

    # 使用 Brave 的獨立視窗（app 模式）開啟網址
    /Applications/Brave\ Browser.app/Contents/MacOS/Brave\ Browser --new --app="$url" &

    # 等待指定時間
    sleep "$seconds"

    echo "⏱️ 時間到，關閉 Brave 視窗"

    # 關閉最早開啟的 Brave 視窗（就是剛剛那個）
    pkill -o "Brave Browser"

    sleep 5  # 避免重疊
done < "$FILE"