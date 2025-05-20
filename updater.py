import os
import sys
import requests
import zipfile
import shutil
import json
import hashlib
import urllib.parse # Ensure urllib.parse is imported at the top level
from packaging.version import parse as parse_version
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from logger import get_logger # Import the new logger
logger = get_logger(__name__) # Get a logger for this module

# ANSI颜色定义 (can still be used with the logger)
class LogColor:
    END = '\033[0m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    CYAN = '\033[36m'
    BOLD = '\033[1m'

def log_info(msg):
    logger.info(f"{LogColor.BLUE}{msg}{LogColor.END}")

def log_success(msg):
    logger.info(f"{LogColor.GREEN}{msg}{LogColor.END}") # Using logger.info for success as well, color indicates success

def log_warning(msg):
    logger.warning(f"{LogColor.YELLOW}{msg}{LogColor.END}")

def log_error(msg):
    logger.error(f"{LogColor.RED}{msg}{LogColor.END}")

# API 端点和镜像列表
API_URL = "https://webhook.sdjz.wiki/api/latest_release_info"
VERSION_FILE = "VERSION.txt"
CONFIG_DIR = "config"

# 备用下载镜像模板
DOWNLOAD_MIRRORS = [
    "https://github.com/{path}", # 官方链接放第一个
    "https://99z.top/https://github.com/{path}",
    "https://gh-proxy.com/https://github.com/{path}",
    "https://ghproxy.net/https://github.com/{path}",
    "https://github.tbedu.top/{path}",
]

def get_current_version():
    """读取本地版本文件"""
    if not os.path.exists(VERSION_FILE):
        return parse_version("0.0.0") # 默认为0.0.0
    with open(VERSION_FILE, 'r') as f:
        return parse_version(f.read().strip())

def get_latest_release_info():
    """
    从API获取最新版本信息.
    期望API响应的JSON中包含 'latest_version', 'release_notes', 
    'source_code_zip_url', 和 'sha256_hash' (zip文件的SHA256哈希值).
    """
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status() 
        return response.json()
    except requests.exceptions.HTTPError as e:
        log_error(f"获取最新版本信息失败 (HTTP错误): {e.response.status_code} - {e.response.reason}")
        return None
    except requests.exceptions.ConnectionError as e:
        log_error(f"获取最新版本信息失败 (网络连接错误): {e}")
        return None
    except requests.exceptions.Timeout as e:
        log_error(f"获取最新版本信息失败 (请求超时): {e}")
        return None
    except requests.exceptions.RequestException as e: # Catch other request-related errors
        log_error(f"获取最新版本信息失败 (请求异常): {e}")
        return None
    except json.JSONDecodeError as e:
        log_error(f"解析API响应JSON失败: {e}") # More specific message
        return None
    except Exception as e: # Generic fallback
        log_error(f"获取最新版本信息时发生未知错误: {e}")
        logger.exception("Uncaught exception in get_latest_release_info", exc_info=True)
        return None


def calculate_sha256(filepath):
    """计算文件的SHA256哈希值"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def download_file(url_path, download_path, expected_hash=None):
    """
    尝试从官方和镜像列表下载文件，带进度条。
    如果提供了 expected_hash，则进行SHA256校验。
    返回下载成功与否 (True/False)。
    """
    urls_to_try = [mirror.format(path=url_path) for mirror in DOWNLOAD_MIRRORS]
    for i, full_url in enumerate(urls_to_try):
        try:
            log_info(f"下载 [{i+1}/{len(urls_to_try)}] {full_url}")
            headers = {}
            if "api.github.com" in full_url:
                headers['Accept'] = 'application/octet-stream'
            with requests.get(full_url, headers=headers, stream=True, timeout=60) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                if HAS_TQDM and total > 0:
                    with open(download_path, 'wb') as f, tqdm(total=total, unit='B', unit_scale=True, desc='下载进度', ncols=70) as pbar:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            pbar.update(len(chunk))
                else:
                    downloaded = 0
                    with open(download_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            if total > 0:
                                downloaded += len(chunk)
                                percent = int(downloaded * 100 / total)
                                # For \r progress, print might still be okay, or use logger.debug with special handling
                                sys.stdout.write(f"\r下载进度: {percent}%")
                                sys.stdout.flush()
                    if total > 0:
                        sys.stdout.write("\n") # Newline after progress
                        sys.stdout.flush()
            log_success(f"下载成功: {download_path}")

            if expected_hash:
                log_info(f"正在校验文件哈希值: {download_path}")
                actual_hash = calculate_sha256(download_path)
                if actual_hash.lower() == expected_hash.lower():
                    log_success("文件哈希值校验成功。")
                    return True
                else:
                    log_error(f"哈希校验失败！文件可能已损坏或被篡改。")
                    log_error(f"  预期哈希: {expected_hash}")
                    log_error(f"  实际哈希: {actual_hash}")
                    try:
                        os.remove(download_path)
                        log_info(f"已删除不匹配的下载文件: {download_path}")
                    except OSError as e_del:
                        log_warning(f"删除不匹配文件 {download_path} 失败: {e_del}")
                    return False # 哈希不匹配，即使下载成功也返回False
            else:
                # 如果没有提供预期哈希，我们仅能假设下载成功即为成功
                # 但在 check_and_update 中，如果API没有提供哈希，会中止操作
                log_warning("未提供预期哈希值，跳过文件校验。")
                return True # 下载成功，但未校验

        except requests.exceptions.HTTPError as e_http:
            log_error(f"从 {full_url} 下载失败 (HTTP错误): {e_http.response.status_code} - {e_http.response.reason}")
        except requests.exceptions.ConnectionError as e_conn:
            log_error(f"从 {full_url} 下载失败 (网络连接错误): {e_conn}")
        except requests.exceptions.Timeout as e_timeout:
            log_error(f"从 {full_url} 下载失败 (请求超时): {e_timeout}")
        except requests.exceptions.RequestException as e_req: # Catch other request-related errors
            log_error(f"从 {full_url} 下载失败 (请求异常): {e_req}")
        except Exception as e: # Generic fallback for other errors during download/hash check
            log_error(f"下载或校验过程中发生未知错误 ({full_url}): {e}")
            logger.exception(f"Uncaught exception during download_file ({full_url})", exc_info=True)
            # 如果在下载后、校验前发生错误，确保清理已下载的文件
            if os.path.exists(download_path) and not (expected_hash and actual_hash.lower() == expected_hash.lower()): # Check if it was a good file
                try:
                    os.remove(download_path)
                    log_info(f"已清理部分下载的文件 (由于后续错误): {download_path}")
                except OSError:
                    pass #尽力而为
    log_error(f"所有源均下载失败或校验失败: {url_path}") # This is logged if loop completes without returning True
    return False

def update_files(zip_path, target_dir):
    """解压并替换文件，带进度条，减少无关细节输出"""
    temp_extract_dir = os.path.join(target_dir, "_update_temp")
    if os.path.exists(temp_extract_dir):
        shutil.rmtree(temp_extract_dir)
    os.makedirs(temp_extract_dir, exist_ok=True)
    try:
        log_info(f"开始解压 {zip_path} 到 {temp_extract_dir}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            members = zip_ref.namelist()
            first_member = members[0]
            root_folder_in_zip = os.path.normpath(first_member).split(os.sep)[0]
            log_info(f"Zip 包内的根目录: {root_folder_in_zip}")
            if HAS_TQDM:
                for member in tqdm(members, desc='解压进度', ncols=70):
                    zip_ref.extract(member, temp_extract_dir)
            else:
                total = len(members)
                for idx, member in enumerate(members):
                    zip_ref.extract(member, temp_extract_dir)
                    sys.stdout.write(f"\r解压进度: {int((idx+1)*100/total)}%")
                    sys.stdout.flush()
                sys.stdout.write("\n")
                sys.stdout.flush()
        log_success("解压完成。")
        source_dir_to_copy = os.path.join(temp_extract_dir, root_folder_in_zip)
        if not os.path.isdir(source_dir_to_copy):
            log_warning(f"未在 {temp_extract_dir} 中找到预期的根目录 {root_folder_in_zip}，尝试直接使用解压目录。")
            source_dir_to_copy = temp_extract_dir
        log_info(f"开始更新文件到 {target_dir}...")
        items = [item for item in os.listdir(source_dir_to_copy)]
        if HAS_TQDM:
            bar = tqdm(items, desc='替换进度', ncols=70)
        else:
            bar = items
        for idx, item in enumerate(bar if HAS_TQDM else items):
            s_item = os.path.join(source_dir_to_copy, item)
            d_item = os.path.join(target_dir, item)
            if item == CONFIG_DIR or item in [os.path.basename(zip_path), os.path.basename(VERSION_FILE), "updater.py", "_update_temp", ".git", ".github"]:
                continue
            if os.path.isdir(s_item):
                if os.path.exists(d_item):
                    shutil.rmtree(d_item)
                shutil.copytree(s_item, d_item, dirs_exist_ok=True)
            else:
                shutil.copy2(s_item, d_item)
            if not HAS_TQDM:
                sys.stdout.write(f"\r替换进度: {int((idx+1)*100/len(items))}%")
                sys.stdout.flush()
        if not HAS_TQDM:
            sys.stdout.write("\n")
            sys.stdout.flush()
        log_success("文件更新完成。")
        return True
    except zipfile.BadZipFile as e_zip:
        log_error(f"解压失败: {zip_path} 不是一个有效的zip文件或已损坏. Error: {e_zip}")
        return False
    except IOError as e_io: # More specific for file operations
        log_error(f"更新文件过程中发生IO错误: {e_io}")
        return False
    except Exception as e: # Generic fallback
        log_error(f"更新文件过程中发生未知错误: {e}")
        logger.exception(f"Uncaught exception during update_files ({zip_path})", exc_info=True)
        return False
    finally:
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError as e:
                log_warning(f"无法删除下载的zip文件 {zip_path}: {e}")

def write_current_version(version_str):
    """将当前版本写入文件"""
    with open(VERSION_FILE, 'w') as f:
        f.write(str(version_str))
    logger.info(f"本地版本已更新为: {version_str}") # Changed to logger.info

def restart_program():
    """重启当前程序"""
    logger.info("准备重启程序...") # Changed to logger.info
    try:
        os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as e:
        # Using log_error which internally uses logger.error
        log_error(f"❌ 重启失败: {e}。请手动重启程序。")
        logger.exception("Exception during restart_program", exc_info=True)


def check_and_update():
    """检查更新的主函数"""
    logger.info("正在检查更新...") # Changed to logger.info
    current_v = get_current_version()
    logger.info(f"当前本地版本: {current_v}") # Changed to logger.info

    latest_info = get_latest_release_info()
    if not latest_info:
        return

    latest_v_str = latest_info.get("latest_version")
    if not latest_v_str:
        log_error("API响应中未找到 'latest_version' 字段。无法确定最新版本。")
        return
        
    latest_v = parse_version(latest_v_str)
    log_info(f"最新可用版本: {latest_v}")

    if latest_v > current_v:
        log_success(f"✨ 发现新版本 {latest_v}！")
        log_info("📄 更新内容:")
        release_notes = latest_info.get("release_notes", "未提供更新日志。").strip()
        for line in release_notes.split('\n'):
            logger.info(f"  {line}") # Changed to logger.info for release notes
        
        # 获取预期的哈希值
        expected_sha256 = latest_info.get("sha256_hash")
        if not expected_sha256:
            log_warning("⚠️ API响应中未提供 'sha256_hash' 字段。")
            log_error("为了安全起见，缺少哈希值时将中止更新。请联系开发者更新API以包含哈希值。")
            # 严格模式：如果哈希缺失，则中止
            # 如果希望非严格模式，可以注释掉下一行并调整 download_file 的调用
            return 
        else:
            log_info(f"预期文件 SHA256 哈希: {expected_sha256}")

        user_input = input(f"❓ {LogColor.YELLOW}是否要下载并更新到最新版本? (y/N): {LogColor.END}").strip().lower()
        if user_input != 'y':
            log_info("用户取消更新。")
            return

        log_info("🚀 开始更新...")
        zip_url_from_api = latest_info.get("source_code_zip_url") 
        # source_code_zip_url 通常是类似 https://api.github.com/repos/owner/repo/zipball/v1.0.0
        # 我们需要的是下载路径 owner/repo/archive/refs/tags/v1.0.0.zip

        if not zip_url_from_api: # 简单检查
            log_error(f"API返回的 source_code_zip_url 无效: {zip_url_from_api}")
            return

        # 尝试从API URL中提取仓库所有者和名称及版本标签来构造更通用的下载路径
        # 假设API URL格式为 "https://api.github.com/repos/{owner}/{repo}/zipball/{tag}"
        # 或 "https://github.com/{owner}/{repo}/archive/refs/tags/{tag}.zip"
        # 我们需要 "{owner}/{repo}/archive/refs/tags/{tag}.zip" 格式给镜像
        
        repo_path_for_mirrors = None
        # 优先使用 tag 构建路径
        tag_name = latest_v_str # 通常版本号就是tag
        
        # 解析 zip_url_from_api 以获取 owner/repo
        try:
            parsed_api_url = urllib.parse.urlparse(zip_url_from_api)
            path_parts = parsed_api_url.path.strip('/').split('/')
            if "api.github.com" in parsed_api_url.netloc and len(path_parts) >= 4 and path_parts[0] == "repos":
                owner, repo = path_parts[1], path_parts[2]
                repo_path_for_mirrors = f"{owner}/{repo}/archive/refs/tags/{tag_name}.zip"
            # 如果API直接给的是GitHub的归档zip链接
            elif "github.com" in parsed_api_url.netloc and path_parts[-1].endswith(".zip") and "archive" in parsed_api_url.path:
                 # 尝试提取 owner/repo/archive/refs/tags/tag.zip 格式
                # e.g. /user/repo/archive/refs/tags/v1.0.0.zip
                if len(path_parts) >= 5 and path_parts[-3] == "tags" and path_parts[-4] == "refs" and path_parts[-5] == "archive":
                    repo_path_for_mirrors = "/".join(path_parts[-6:]) # owner/repo/archive/refs/tags/tag.zip
                else: # Fallback to a simpler extraction if structure is different
                    repo_path_for_mirrors = "/".join(path_parts[0:2]) + f"/archive/refs/tags/{tag_name}.zip"

            if not repo_path_for_mirrors:
                 raise ValueError("Could not determine repository path from API URL")

        except Exception as e:
            log_error(f"无法从API URL '{zip_url_from_api}' 解析仓库信息: {e}")
            log_warning("将尝试使用基于版本号的通用路径。")
            # 如果无法解析，可以尝试一个基于已知结构的猜测，但这不太可靠
            # 此处应有更健壮的 owner/repo 获取方式，或者API直接提供规范的下载路径
            # For now, we might have to rely on a pre-configured repo slug if parsing fails.
            # For this exercise, we'll assume a generic path might be formed if parsing fails,
            # or simply error out if a reliable path can't be formed.
            # Let's assume 'latest_info' might contain 'repo_slug' (e.g., "owner/repo")
            repo_slug_from_api = latest_info.get("repo_slug") # e.g. "username/repository"
            if repo_slug_from_api:
                repo_path_for_mirrors = f"{repo_slug_from_api}/archive/refs/tags/{tag_name}.zip"
            else:
                log_error("API 未提供 repo_slug 且无法从 source_code_zip_url 解析。无法构造下载路径。")
                return

        download_target_zip = "_latest_version.zip"
        
        log_info(f"将尝试从镜像源下载: {repo_path_for_mirrors}")

        # 调用 download_file 并传入预期的哈希值
        if download_file(repo_path_for_mirrors, download_target_zip, expected_sha256):
            if update_files(download_target_zip, "."): # update_files 会在 finally 中删除 zip
                write_current_version(latest_v_str)
                log_success("🎉 更新成功！程序即将重启。")
                restart_program()
            else:
                log_error("❌ 更新失败，文件替换过程中发生错误。请检查日志。")
                # download_file 成功后，zip文件可能已被 update_files 删除或保留
                # 如果 update_files 失败，它会尝试删除 zip。如果哈希校验失败，download_file 会删除。
        else:
            # download_file 返回 False 意味着下载失败或哈希校验失败
            # 错误信息已在 download_file 内部打印
            log_error("❌ 更新失败。下载或文件校验未通过。")
            # download_file 应该已经删除了文件如果哈希不匹配
            if os.path.exists(download_target_zip):
                 try:
                     os.remove(download_target_zip) # 再次尝试确保删除
                     log_info(f"已清理下载文件: {download_target_zip}")
                 except OSError as e:
                     log_warning(f"⚠️ 清理下载文件 {download_target_zip} 失败: {e}")
    else:
        log_success("✅ 当前已是最新版本。")

if __name__ == "__main__":
    from logger import setup_logging # Import setup_logging for the test execution
    # Setup basic logging for the __main__ execution
    # In a real app, this would be in the main entry point.
    setup_logging(level="DEBUG") 
    
    # For testing, ensure urllib.parse is available for the modified check_and_update
    # import urllib.parse # This is already imported at the top level
    
    logger.info("Updater script started directly.")
    check_and_update()
    logger.info("Updater script finished.")