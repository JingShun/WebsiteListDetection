import configparser
from datetime import datetime, timedelta
import socket
import ssl
import time
import requests
import re
import gspread
from google.oauth2.service_account import Credentials
import urllib3
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import pytz

# request忽略SSL憑證問題
urllib3.disable_warnings(category=urllib3.exceptions.InsecureRequestWarning)
# 設定檔
config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")


# 連線 Google 試算表
def connect_google_sheet(sheet_url: str, certificate_path: str):
    """連線的 Google 試算表

    Args:
        sheet_url (str): sheet url
        certificate_path (str): google certificate json file path

    Returns:
        gspread.Spreadsheet:
    """

    # 設定Google Sheets API的範圍和認證
    __scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    __creds = Credentials.from_service_account_file(certificate_path, scopes=__scope)
    __client = gspread.authorize(__creds)

    # 讀取Google試算表
    __spreadsheet = __client.open_by_url(sheet_url)

    return __spreadsheet


# 取得檢測結果頁面
def load_result_worksheet(spreadsheet: gspread.Spreadsheet):
    """取得檢測結果頁面

    Args:
        spreadsheet (gspread.Spreadsheet): Google Sheet

    Returns:
        gspread.Worksheet: Google Sheet的一個單頁
    """

    # 檢查當天的檢測結果Sheet是否存在，不存在則創建
    __sheet_title = config.get("DEFAULT", "WORKSHEET_DETECT_NAME")
    try:
        __result_sheet = spreadsheet.worksheet(__sheet_title)

    except gspread.exceptions.WorksheetNotFound:
        print(f"指定頁面 {__sheet_title} 找不到，開始新增...", end="")

        # 讀取資產清單sheet
        __asset_sheet = spreadsheet.worksheet(
            config.get("DEFAULT", "WORKSHEET_ASSET_NAME")
        )  # 使用工作表名稱

        # 複製資產清單Sheet並創建新Sheet
        __result_sheet = spreadsheet.duplicate_sheet(
            source_sheet_id=__asset_sheet.id,
            insert_sheet_index=1,
            new_sheet_name=__sheet_title,
        )
        __result_sheet = spreadsheet.worksheet(__sheet_title)
        print("ok")

    # 檢查 檢測結果Sheet 有無指定欄位
    print(f"指定頁面 {__sheet_title} 載入，開始確認或建立欄位...", end="")
    # 取出標題
    __header_row = __result_sheet.row_values(1)

    # 確認必要URL欄位是否存在
    field_name = config.get("DEFAULT", "ASSET_URL_FIELD_NAME", fallback="URL")
    if not field_name in __header_row:
        print(
            f"必要欄位 {field_name} 於指定頁面 {__sheet_title} 中找不到，請在確認後重新執行"
        )
        exit()

    # 確認檢測欄位存在
    detect_columns = [
        "FIELD_NAME_IP",  # 檢測IP
        "FIELD_NAME_CERT_STATUS",  # 憑證狀態
        "FIELD_NAME_WEB_STATUS",  # 網站狀態
        "FIELD_NAME_WEB_HEADER",  # 回應表頭
        "FIELD_NAME_WEB_CONTENT",  # 回應內文
        "FIELD_NAME_WEB_CONTENT_SIZE",  # 回應內文大小
        "FIELD_NAME_UPDATE_AT",  # 更新日
    ]
    for column in detect_columns:
        field_name = config.get("DEFAULT", column, fallback=None)
        if not field_name and not field_name in __header_row:
            __header_row.append(field_name)

    __result_sheet.update([__header_row], "A1")
    print("ok")

    return __result_sheet


# 備份昨日結果頁面
def back_result_worksheet(spreadsheet: gspread.Spreadsheet):
    """備份昨日結果頁面

    Args:
        spreadsheet (gspread.Spreadsheet): Google Sheet

    Returns:
        bool: 成功/失敗
    """

    # 取得 前一天日期
    __yesterday = (
        datetime.now(pytz.timezone("Asia/Taipei")) - timedelta(days=1)
    ).strftime("%Y%m%d")

    # 檢查前一天的檢測結果Sheet是否存在，不存在則進行備份
    __sheet_title = config.get("DEFAULT", "WORKSHEET_DETECT_NAME") + __yesterday
    try:
        __result_sheet = spreadsheet.worksheet(__sheet_title)

    except gspread.exceptions.WorksheetNotFound:

        # 讀取資產清單sheet
        __asset_sheet = spreadsheet.worksheet(
            config.get("DEFAULT", "WORKSHEET_DETECT_NAME")
        )  # 使用工作表名稱

        # 複製資產清單Sheet並創建新Sheet
        __result_sheet = spreadsheet.duplicate_sheet(
            source_sheet_id=__asset_sheet.id,
            insert_sheet_index=1,
            new_sheet_name=__sheet_title,
        )

    return __result_sheet


# 更新試算表特定儲存格
def update_sheet_cell(
    result_sheet: gspread.Worksheet, row: int, col: int, value: int | float | str
):
    """更新試算表特定儲存格

    Args:
        result_sheet (gspread.Worksheet): _description_
        row (int): _description_
        col (int): _description_
        value (int | float | str): _description_
    """

    time.sleep(0.5)  # 避免超過頻率限制

    if type(value) is str and len(value) >= (50000 - 10):
        value = value[: (50000 - 10)] + "...(more)"

    try:
        result = result_sheet.update_cell(row, col, value)
    except Exception as e:
        result = update_sheet_cell(result_sheet, row, col, f"Error: {str(e)}")
    return result


# 檢查憑證鏈的有效性
def check_cert_chain(dns: str):
    """檢查憑證鏈的有效性

    Args:
        dns (str): FQDN/Domain

    Returns:
        str: ok|(錯誤訊息)
    """
    try:
        context = ssl.create_default_context()
        with socket.create_connection((dns, 443)) as sock:
            with context.wrap_socket(sock, server_hostname=dns) as ssock:
                der_cert_chain = ssock.getpeercert(binary_form=True)
                pem_cert_chain = ssl.DER_cert_to_PEM_cert(der_cert_chain)

                certs = []
                certs.append(
                    x509.load_pem_x509_certificate(
                        pem_cert_chain.encode(), default_backend()
                    )
                )

                # 驗證每個證書（从根证书到服务器证书）
                for i in range(len(certs) - 1, 0, -1):
                    cert = certs[i]
                    issuer_cert = certs[i - 1]

                    # 檢查有效期
                    if (
                        cert.not_valid_before > datetime.now()
                        or cert.not_valid_after < datetime.now()
                    ):
                        return f"Certificate {i+1} has expired or is not yet valid."

                    # 檢查簽名
                    try:
                        issuer_cert.public_key().verify(
                            cert.signature,
                            cert.tbs_certificate_bytes,
                            cert.signature_hash_algorithm,
                        )
                    except Exception as e:
                        return f"Signature verification failed for certificate {i+1}: {str(e)}"

                return "ok"  # 所有檢查都通過

    except ssl.SSLError as e:
        return f"SSL error: {str(e)}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"


# 解析IP
def resolver_dns_to_ip(dns: str):
    """將DNS解析成IP

    Args:
        dns (str): domain

    Returns:
        str: ip
    """
    # 取得IP
    try:
        __ip_address = socket.gethostbyname(dns)
    except:
        __ip_address = "Error"
    return __ip_address


def request_url(url: str) -> dict[str, str | int]:
    """瀏覽網頁

    Args:
        url (str): 網址

    Returns:
        dict[str, str | int]: response code, content, content_length
    """

    try:
        _response = requests.get(url, timeout=10, verify=False)
        _response_content_length = len(_response.text)
        _response_content = re.sub(r"(\r\n)+", "", _response.text, flags=re.S | re.M)
        _response_content = re.sub(r"\n+", "", _response.text, flags=re.S | re.M)
        _response_content = re.sub(r"\r+", "", _response.text, flags=re.S | re.M)
        _response_content = re.sub(r"\s+", " ", _response.text, flags=re.S | re.M)
        _response_content = _response_content.rstrip()
        _response_code = _response.status_code
    except Exception as e:
        _response_code = 0
        _response_content_length = 0
        _response_content = f"Error: {str(e)}"

    _result = {
        "code": _response_code,
        "content_length": _response_content_length,
        "content": _response_content,
    }

    return _result


# 將dict結構轉成純文字
def dict_to_text(data: requests.structures.CaseInsensitiveDict):
    """將dict結構轉成純文字

    Args:
        data (requests.structures.CaseInsensitiveDict): 表頭陣列dict

    Returns:
        str: 表頭文字
    """
    return "\n".join((f"{item[0]}:{item[1]}" for item in data.items()))


# 取得表頭
def request_redirect_header(_url: str, max_redirects=10):
    """取得表頭，包含每次跳轉，類似於`curl -ILk <url>`的結果

    Args:
        _url (str): _description_
        max_redirects (int, optional): _description_. Defaults to 10.

    Returns:
        _type_: _description_
    """

    # 获取完整的重定向链，包括每次跳转的响应头信息
    __session = requests.Session()
    __session.verify = False
    __headers_list = []
    __redirect_count = 0

    try:
        while __redirect_count < max_redirects:
            __response = __session.head(_url, allow_redirects=False)

            __headers_list.append(
                f"HTTP/{__response.raw.version / 10} {__response.status_code} {__response.reason}\n"
                + dict_to_text(__response.headers)
            )
            if __response.is_redirect or __response.is_permanent_redirect:
                location = __response.headers.get("Location")
                if not location:
                    break

                # 处理相对路径的重定向
                _url = requests.compat.urljoin(__response.url, location)
                __redirect_count += 1
            else:
                break
        else:
            __headers_list.append(
                f"Warning: Reached maximum number of redirects ({max_redirects})."
            )

    except requests.RequestException as _e:
        __headers_list.append(f"Request failed: {_e}")

    return "\n\n".join(__headers_list)


# 執行前先確認必要參數是否存在
def init_ckeck(spreadsheet: gspread.Spreadsheet):
    """執行前先確認必要參數是否存在

    Returns:
        bool:
    """
    __sheet_title = config.get("DEFAULT", "WORKSHEET_ASSET_NAME", fallback=None)
    if not __sheet_title:
        print("資產清單未指定，請確認config.ini")
        exit()
    try:
        spreadsheet.worksheet(__sheet_title)
    except gspread.exceptions.WorksheetNotFound:
        print("找不到資產清單 {__sheet_title}，請確認後再重新執行")
        exit()

    return True


# # # # # # # # # # # # # # # # # # # #

print("開始執行於 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

print("連線並存取資料表")

# 讀取Google試算表
spreadsheet = connect_google_sheet(
    config.get("DEFAULT", "GOOGLE_SHEET_URL"),
    config.get("DEFAULT", "GOOGLE_CERTIFICATE_PATH"),
)

# 參數檢查
init_ckeck(spreadsheet)

# 備份昨日結果頁面
if config.get("DEFAULT", "AUTO_BACKUP", fallback="1"):
    back_result_worksheet(spreadsheet)

# 取得檢測結果頁面
result_worksheet = load_result_worksheet(spreadsheet)


# 讀取檢測結果Sheet中的URL欄位
field_name = config.get("DEFAULT", "ASSET_URL_FIELD_NAME", fallback="URL")
url_col = result_worksheet.find(field_name).col if field_name != "NA" else None

if url_col is None:
    print(f"未找到資產網址欄位: {field_name} ，直接結束")
    exit()

urls = result_worksheet.col_values(url_col)[1:]  # 假設URL欄位是標題列的其中之一

# 動態確定要更新的檢測結果的起始列

# 檢測IP
field_name = config.get("DEFAULT", "FIELD_NAME_IP", fallback="NA")
ip_col = result_worksheet.find(field_name).col if field_name != "NA" else None

# 憑證狀態
field_name = config.get("DEFAULT", "FIELD_NAME_CERT_STATUS", fallback="NA")
cert_col = result_worksheet.find(field_name).col if field_name != "NA" else None

# 網站狀態
field_name = config.get("DEFAULT", "FIELD_NAME_WEB_STATUS", fallback="NA")
response_code_col = (
    result_worksheet.find(field_name).col if field_name != "NA" else None
)

# 回應表頭
field_name = config.get("DEFAULT", "FIELD_NAME_WEB_HEADER", fallback="NA")
headers_col = result_worksheet.find(field_name).col if field_name != "NA" else None

# 回應內文
field_name = config.get("DEFAULT", "FIELD_NAME_WEB_CONTENT", fallback="NA")
content_col = result_worksheet.find(field_name).col if field_name != "NA" else None

# 回應內文大小
field_name = config.get("DEFAULT", "FIELD_NAME_WEB_CONTENT_SIZE", fallback="NA")
content_length_col = (
    result_worksheet.find(field_name).col if field_name != "NA" else None
)

# 更新日
field_name = config.get("DEFAULT", "FIELD_NAME_UPDATE_AT", fallback="NA")
updated_at_col = result_worksheet.find(field_name).col if field_name != "NA" else None


# 依序對每個URL進行檢測
print("依序對每個URL進行檢測")
for idx, url in enumerate(urls, start=2):  # 從第2列開始，因為第1列是標題
    # 沒網址就跳過
    if len(url.rstrip()) == 0:
        continue
    else:
        time.sleep(1)  # 避免超過Google API頻率限制

    print(f"[{idx}/{str(len(urls))}]{url}...", end="")

    host = url.split("//")[-1].split("/")[0]

    # 取得IP
    if ip_col:
        ip_address = resolver_dns_to_ip(host)
        update_sheet_cell(result_worksheet, idx, ip_col, ip_address)

    # 取得憑證狀態
    if cert_col:
        cert_chain_status = check_cert_chain(host)
        update_sheet_cell(result_worksheet, idx, cert_col, cert_chain_status)

    # 取得表頭
    if headers_col:
        header_text = request_redirect_header(url)
        update_sheet_cell(result_worksheet, idx, headers_col, header_text)

    # 取得回應
    response = request_url(url)
    if response_code_col:
        update_sheet_cell(result_worksheet, idx, response_code_col, response["code"])
    if content_col:
        update_sheet_cell(result_worksheet, idx, content_col, response["content"])
    if content_length_col:
        update_sheet_cell(
            result_worksheet, idx, content_length_col, response["content_length"]
        )

    # 更新日期
    if updated_at_col:
        update_sheet_cell(
            result_worksheet, idx, updated_at_col, datetime.now().strftime("%Y/%m/%d")
        )

    print("ok")


print("檢測完成，結果已更新至Google Sheets。")
print("完成執行於 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
