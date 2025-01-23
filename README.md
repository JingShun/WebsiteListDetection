# WebsiteListDetection
1. 檢測網站存活，並更新到google試算表中。
2. 可在多個不同的地點執行，只要設定檔中的欄位不同就可以

比如說在 分公司、國內(公司外)、國外、弱掃平台主機 上定期執行腳本，
若發現弱掃主機無法連線，但國內(公司外)卻可以連線，合理判斷網站不小心誤將弱掃平台封鎖了。

![image](https://github.com/user-attachments/assets/0f0cc113-ebd5-4937-91ee-eedc138efe7f)


# 使用方法

1. 申請 Google API，取得 googleCertificate.json
2. 建立 Google Sheet，取得將API服務帳號加入編輯權限

必備工作表與欄位

|工作表|欄位|說明|
|---|---|---|
|資產清單|URL|可透過WORKSHEET_ASSET_NAME、ASSET_URL_FIELD_NAME 調整名稱|

 
3. 設定 config.ini

|參數|說明|範例|
|---|---|---|
|TIMEZONE|時區|預設UTC，台灣請改 Asia/Taipei|
|GOOGLE_CERTIFICATE_PATH|google證書相對位置|config/googleCertificate.json|
|GOOGLE_SHEET_URL|google試算表|https://docs.google.com/spreadsheets/d/1OZkYt.....Db1yQs/edit|
|ASSET_URL_FIELD_NAME|資產清單的網站連結欄位名稱|URL|
|WORKSHEET_ASSET_NAME|工作表名稱: 資產清單|資產清單|
|WORKSHEET_DETECT_NAME|工作表名稱: 檢測結果|檢測結果|
|FIELD_NAME_IP|欄位名稱:DN解析IP，空白則忽略|國外檢測IP|
|FIELD_NAME_CERT_STATUS|欄位名稱:檢測憑證狀態，空白則忽略|國外憑證狀態|
|FIELD_NAME_WEB_STATUS|欄位名稱:檢測網站狀態，空白則忽略|國外網站狀態|
|FIELD_NAME_WEB_HEADER|欄位名稱:檢測回應表頭，空白則忽略|國外回應表頭|
|FIELD_NAME_WEB_CONTENT|欄位名稱:檢測回應內文，空白則忽略|國外回應內文|
|FIELD_NAME_WEB_CONTENT_SIZE|欄位名稱:檢測回應內文大小，空白則忽略|國外回應內文大小|
|FIELD_NAME_UPDATE_AT|欄位名稱:更新日|國外更新日|
|AUTO_BACKUP|自動備份 |1:(default)yes 0:no|
|BACKUP_RETENTION_PERIOD|備份留存週期(天)|30|

4. 可設定排程自動執行

# 簡易判斷

1. 若公司內可以連線，外部都不能連線，那代表該網站有限縮不能對外
2. 若在本國都可以連線，國外卻不能連線，那代表該網站有限縮僅限自己國家瀏覽
3. 若公司內連不到，但外部卻都可以連線代表有問題
4. 若公司內外都可以連線，但唯獨弱掃平台無法連線，請管理者將弱掃平台加入白名單後再重新弱掃
5. 若公司內外的回應內文特別小或大小差異很大，可留意發生什麼狀況，確認回應表頭欄位看是不是導去第三方網站
6. 若回應內文大小與前幾天不同，可留意發生什麼狀況
7. 憑證逾期
