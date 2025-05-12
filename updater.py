import os
import sys
import requests
import zipfile
import shutil
import json
from packaging.version import parse as parse_version
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ANSI颜色定义
class LogColor:
    END = '\033[0m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    CYAN = '\033[36m'
    BOLD = '\033[1m'

def log_info(msg):
    print(f"{LogColor.BLUE}{msg}{LogColor.END}")

def log_success(msg):
    print(f"{LogColor.GREEN}{msg}{LogColor.END}")

def log_warning(msg):
    print(f"{LogColor.YELLOW}{msg}{LogColor.END}")

def log_error(msg):
    print(f"{LogColor.RED}{msg}{LogColor.END}")

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
    """从API获取最新版本信息"""
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status() # 如果HTTP错误，则抛出异常
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 获取最新版本信息失败: {e}")
        return None

def download_file(url_path, download_path):
    """尝试从官方和镜像列表下载文件，带进度条"""
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
                                print(f"\r下载进度: {percent}%", end='')
                    if total > 0:
                        print()
            log_success(f"下载成功: {download_path}")
            return True
        except requests.exceptions.RequestException as e:
            log_error(f"从 {full_url} 下载失败: {e}")
        except Exception as e:
            log_error(f"下载过程中发生意外错误: {e}")
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
                    print(f"\r解压进度: {int((idx+1)*100/total)}%", end='')
                print()
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
                print(f"\r替换进度: {int((idx+1)*100/len(items))}%", end='')
        if not HAS_TQDM:
            print()
        log_success("文件更新完成。")
        return True
    except zipfile.BadZipFile:
        log_error(f"解压失败: {zip_path} 不是一个有效的zip文件或已损坏。")
        return False
    except Exception as e:
        log_error(f"更新文件过程中发生错误: {e}")
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
    print(f"本地版本已更新为: {version_str}")

def restart_program():
    """重启当前程序"""
    print("准备重启程序...")
    try:
        os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as e:
        print(f"❌ 重启失败: {e}。请手动重启程序。")

def check_and_update():
    """检查更新的主函数"""
    print("正在检查更新...")
    current_v = get_current_version()
    print(f"当前本地版本: {current_v}")

    latest_info = get_latest_release_info()
    if not latest_info:
        return

    latest_v_str = latest_info.get("latest_version")
    if not latest_v_str:
        print("❌ API响应中未找到 latest_version 字段。")
        return
        
    latest_v = parse_version(latest_v_str)
    print(f"最新可用版本: {latest_v}")

    if latest_v > current_v:
        print(f"✨ 发现新版本 {latest_v}！")
        print("📄 更新内容:")
        release_notes = latest_info.get("release_notes", "未提供更新日志。").strip()
        for line in release_notes.split('\n'): # 逐行打印，更好看
            print(f"  {line}")
        
        user_input = input("❓ 是否要下载并更新到最新版本? (y/N): ").strip().lower()
        if user_input != 'y':
            print(" отказался от обновления. (用户取消更新)")
            return

        print("🚀 开始更新...")
        zip_url_from_api = latest_info.get("source_code_zip_url")
        if not zip_url_from_api or "api.github.com" not in zip_url_from_api:
            print(f"❌ API返回的 source_code_zip_url 无效或格式不符合预期: {zip_url_from_api}")
            return

        # 从API URL中提取仓库所有者和名称
        try:
            parts = zip_url_from_api.split("api.github.com/repos/")[1].split("/")
            owner, repo = parts[0], parts[1]
            repo_slug = f"{owner}/{repo}"
            # tag_name 应该是 latest_v_str
            github_path_for_mirrors = f"{repo_slug}/archive/refs/tags/{latest_v_str}.zip"
        except IndexError:
            print(f"❌ 无法从API URL解析仓库信息: {zip_url_from_api}")
            return

        download_target_zip = "_latest_version.zip"
        
        # 优先尝试使用 API 直接给的 zipball_url
        urls_for_download_logic = [DOWNLOAD_MIRRORS[0].format(path=github_path_for_mirrors)] + \
                                   [mirror.format(path=github_path_for_mirrors) for mirror in DOWNLOAD_MIRRORS[1:]]
        
        print(f"将尝试从以下源下载 {github_path_for_mirrors}:")

        if download_file(github_path_for_mirrors, download_target_zip):
            if update_files(download_target_zip, "."):
                write_current_version(latest_v_str)
                print("更新成功！程序即将重启。")
                restart_program()
            else:
                print("❌ 更新失败，文件替换过程中发生错误。请检查日志。")
                # 尝试清理下载的文件
                if os.path.exists(download_target_zip):
                    try:
                        os.remove(download_target_zip)
                    except OSError as e:
                        print(f"⚠️ 无法删除未成功更新的zip文件 {download_target_zip}: {e}")
        else:
            print("❌ 更新失败，所有下载源均无法下载最新版本。")
    else:
        print("当前已是最新版本")

if __name__ == "__main__":
    check_and_update() 