import configparser
import os
import re
import shutil
import subprocess
import sys
import time

import undetected_chromedriver as uc
from notice import Notice
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class AkileCheckin:
    def __init__(self):
        self.browser = None

        # 优先读取环境变量（便于在 GitHub Actions 中直接运行）
        self.email = os.getenv("AKILE_EMAIL", "").strip()
        self.password = os.getenv("AKILE_PASSWORD", "").strip()
        self.push_key = os.getenv("AKILE_PUSH_KEY", "").strip()

        # 若环境变量未配置则回退到配置文件
        if not self.email or not self.password:
            config = configparser.ConfigParser()
            config.read("config.ini", encoding="utf-8")
            self.email = self.email or config.get("akile", "email")
            self.password = self.password or config.get("akile", "password")
            self.push_key = self.push_key or config.get(
                "akile", "push_key", fallback=""
            )

        options = uc.ChromeOptions()
        options.add_argument("--lang=zh-CN")
        options.add_experimental_option("prefs", {"intl.accept_languages": "zh-CN,zh"})
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
        )

        # 在 CI 中显式指定 Chrome 二进制与主版本，避免多版本并存导致的版本错配
        chrome_path, chrome_major = self._get_chrome_info()
        if chrome_path:
            options.binary_location = chrome_path
            print(f"Using Chrome binary: {chrome_path} (major={chrome_major})")

        if chrome_major:
            self.browser = uc.Chrome(options=options, version_main=chrome_major)
        else:
            self.browser = uc.Chrome(options=options)

    @staticmethod
    def _get_chrome_info():
        candidates = [
            "google-chrome",
            "google-chrome-stable",
            "chromium-browser",
            "chromium",
        ]

        for binary in candidates:
            binary_path = shutil.which(binary)
            if not binary_path:
                continue

            try:
                output = subprocess.check_output(
                    [binary_path, "--version"], stderr=subprocess.STDOUT, text=True
                ).strip()
                match = re.search(r"(\d+)\.", output)
                if match:
                    return binary_path, int(match.group(1))
            except Exception:
                continue

        return None, None

    def _fail(self, msg, screenshot=None):
        """统一失败处理：截图、打印、推送并退出。"""
        if screenshot:
            try:
                self.browser.save_screenshot(screenshot)
            except Exception:
                pass
        print(msg)
        Notice.serverJ(self.push_key, "Akile签到", msg)
        sys.exit(1)

    def _page_text(self):
        try:
            return (
                self.browser.execute_script(
                    "return document.body ? document.body.innerText : '';"
                )
                or ""
            )
        except Exception:
            return ""

    def _detect_login_blockers(self):
        """检测登录后无法自动处理的安全拦截。"""
        text = self._page_text()
        url = (self.browser.current_url or "").lower()

        # 强制改密（需要邮箱验证码，自动化无法完成）
        if (
            "验证邮箱并修改密码" in text
            or "本次登录需要修改密码" in text
            or ("验证码已发送至" in text and "新密码" in text)
            or "修改密码并登录" in text
        ):
            return (
                "forced_password_change",
                "登录被拦截：平台要求强制修改密码。"
                "请先在官网手动完成邮箱验证码改密，"
                "并同步更新 config.ini 或 GitHub Secrets 中的 AKILE_PASSWORD。",
            )

        # 验证器 TOTP
        if (
            "使用验证器应用验证身份" in text
            or "验证器应用生成的6位验证码" in text
        ):
            return (
                "totp_required",
                "登录被拦截：需要验证器应用二次验证。"
                "自动签到无法输入动态验证码，请先关闭强制 2FA 或改用可自动登录的方式。",
            )

        # 必须完成 Passkey 验证才能继续
        if "需要 Passkey 验证" in text and "立即验证" in text:
            return (
                "passkey_required",
                "登录被拦截：需要 Passkey 验证。"
                "自动签到无法完成 Passkey，请在官网取消强制 Passkey 后再试。",
            )

        # 常见密码错误提示
        if any(
            tip in text
            for tip in (
                "密码错误",
                "账号或密码错误",
                "邮箱或密码错误",
                "用户名或密码错误",
            )
        ):
            return (
                "bad_credentials",
                "登录失败：账号或密码错误，请检查 AKILE_EMAIL / AKILE_PASSWORD。",
            )

        # 仍在登录页且没有明显可跳过提示
        if "/login" in url and "控制台" not in text:
            # 若页面只有登录表单，可能是失败但无明确文案
            if "登录您的帐户" in text or "请输入邮箱" in text:
                return (
                    "still_on_login",
                    "登录失败：提交后仍停留在登录页。"
                    "可能是密码错误、触发安全校验或网络异常。",
                )

        return None, None

    def _dismiss_skippable_dialogs(self):
        """关闭可跳过的弹窗（Passkey 提示、公告等），避免遮挡签到按钮。"""
        # 优先点「下次一定」，对应可选的 Passkey 绑定提示
        try:
            later_buttons = self.browser.find_elements(
                By.XPATH, '//button[contains(., "下次一定")]'
            )
            for btn in later_buttons:
                try:
                    if btn.is_displayed():
                        self.browser.execute_script("arguments[0].click();", btn)
                        time.sleep(0.4)
                except Exception:
                    continue
        except Exception:
            pass

        # 点关闭按钮
        try:
            close_buttons = self.browser.find_elements(
                By.CSS_SELECTOR, ".arco-modal-close-btn, .arco-modal-close"
            )
            for btn in close_buttons:
                try:
                    if btn.is_displayed():
                        self.browser.execute_script("arguments[0].click();", btn)
                        time.sleep(0.3)
                except Exception:
                    continue
        except Exception:
            pass

        # 兜底移除残留遮罩，避免挡住点击
        try:
            self.browser.execute_script(
                """
                document.querySelectorAll(
                    '.arco-modal-wrapper, .arco-modal-mask, .arco-modal, .arco-modal-container'
                ).forEach(function (m) {
                    try {
                        if (m && m.parentNode) {
                            m.parentNode.removeChild(m);
                        }
                    } catch (e) {}
                });
                document.body.style.overflow = '';
                """
            )
        except Exception:
            pass

    def login(self):
        # 直接访问登录页面
        self.browser.get("https://akile.ai/login")
        self.browser.maximize_window()
        time.sleep(2)

        # 登录前清理无关遮挡
        self._dismiss_skippable_dialogs()

        # 键入邮箱和密码
        try:
            email_input = WebDriverWait(self.browser, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'input[placeholder*="邮箱"]')
                )
            )
            email_input.clear()
            email_input.send_keys(self.email)
            password_input = WebDriverWait(self.browser, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'input[placeholder*="密码"]')
                )
            )
            password_input.clear()
            password_input.send_keys(self.password)
        except TimeoutException as e:
            self._fail(
                f"邮箱或密码输入框没有加载出来: {e}\n签到失败",
                screenshot="login_form.png",
            )

        try:
            submit_button = WebDriverWait(self.browser, 10).until(
                EC.element_to_be_clickable(
                    (
                        By.CSS_SELECTOR,
                        'form button[type="submit"], form .arco-btn-primary',
                    )
                )
            )
            submit_button.click()
        except TimeoutException as e:
            self._fail(
                f"登录按钮没有加载出来: {e}\n签到失败",
                screenshot="login_button.png",
            )

        # 等待登录结果：离开登录页，或出现安全拦截弹窗
        deadline = time.time() + 20
        while time.time() < deadline:
            blocker, blocker_msg = self._detect_login_blockers()
            if blocker and blocker != "still_on_login":
                self._fail(blocker_msg + "\n签到失败", screenshot="login_blocked.png")

            url = (self.browser.current_url or "").lower()
            text = self._page_text()
            if "/login" not in url or "控制台" in text or "AVIP" in text:
                break
            time.sleep(0.5)
        else:
            blocker, blocker_msg = self._detect_login_blockers()
            if blocker:
                self._fail(
                    (blocker_msg or "登录失败") + "\n签到失败",
                    screenshot="login_timeout.png",
                )
            self._fail(
                "登录超时：未能确认登录成功\n签到失败",
                screenshot="login_timeout.png",
            )

        # 登录成功后可能弹出可选 Passkey 绑定提示
        self._dismiss_skippable_dialogs()
        print("登录成功")

    def _get_ak_coins(self):
        """获取当前AK币数量"""
        try:
            element = self.browser.find_element(By.CSS_SELECTOR, ".coin-balance-value")
            text = element.text.strip()
            match = re.search(r"(\d+)", text)
            return int(match.group(1)) if match else -1
        except Exception:
            return -1

    def _find_visible_checkin_state(self):
        for label, state in (("已签到", "already"), ("今日已签到", "already")):
            try:
                buttons = self.browser.find_elements(
                    By.XPATH, f'//button[contains(normalize-space(.), "{label}")]'
                )
                if any(button.is_displayed() for button in buttons):
                    return state
            except Exception:
                continue

        text = self._page_text()
        if any(message in text for message in ("签到成功", "签到成功！", "领取成功")):
            return "success"
        if any(message in text for message in ("今日已签到", "已经签到", "重复签到")):
            return "already"
        return None

    def _wait_for_checkin_result(self, previous_points_num, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self._find_visible_checkin_state()
            if state:
                return state, self._get_ak_coins()

            current_points_num = self._get_ak_coins()
            if (
                previous_points_num >= 0
                and current_points_num >= 0
                and current_points_num != previous_points_num
            ):
                return "success", current_points_num

            time.sleep(0.5)

        return None, self._get_ak_coins()

    def _is_logged_out(self):
        url = (self.browser.current_url or "").lower()
        text = self._page_text()
        return "/login" in url or "您还没有登录" in text

    # 签到主逻辑
    def check_in(self):
        checkin_page = "https://akile.ai/console/ak-coin-shop"
        self.browser.get(checkin_page)
        time.sleep(5)

        # 若被踢回登录页，说明会话无效
        if self._is_logged_out():
            # 再检查是否其实是强制改密等拦截
            blocker, blocker_msg = self._detect_login_blockers()
            if blocker and blocker != "still_on_login":
                self._fail(blocker_msg + "\n签到失败", screenshot="checkin_blocked.png")
            self._fail(
                "访问签到页失败：未登录或登录态失效。"
                "若近期平台要求强制改密，请先手动改密并更新密码配置。\n签到失败",
                screenshot="checkin_login_required.png",
            )

        # 关闭公告 / Passkey 等可跳过弹窗
        self._dismiss_skippable_dialogs()

        prev_points_num = self._get_ak_coins()
        print(f"当前AK币: {prev_points_num}")

        if self._find_visible_checkin_state() == "already":
            msg = f"今日已签到，未重复执行签到，现在有{prev_points_num}AK币"
            print(msg)
            Notice.serverJ(self.push_key, "Akile签到", msg)
            sys.exit(0)

        # 尝试签到
        try:
            checkin_button = WebDriverWait(self.browser, 15).until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//button[contains(., "每日签到")]')
                )
            )
            print("找到签到按钮，正在点击...")
            self.browser.execute_script("arguments[0].click();", checkin_button)

            result, cur_points_num = self._wait_for_checkin_result(prev_points_num)
            if result == "already":
                msg = f"今日已签到，未重复执行签到，现在有{cur_points_num}AK币"
            elif result == "success":
                if (
                    prev_points_num < 0
                    or cur_points_num < 0
                    or cur_points_num <= prev_points_num
                ):
                    msg = f"签到成功，积分正在刷新，当前有{cur_points_num}个AK币"
                else:
                    gain = cur_points_num - prev_points_num
                    msg = f"签到成功, 获得{gain}个AK币, 当前有{cur_points_num}个AK币"
            else:
                self._fail(
                    "点击签到后未检测到成功结果。"
                    "页面可能改版、请求被拦截或网络异常，请查看失败截图后重试。\n签到失败",
                    screenshot="checkin_result_timeout.png",
                )

            print(msg)
            Notice.serverJ(self.push_key, "Akile签到", msg)
            sys.exit(0)

        except TimeoutException:
            print("未找到签到按钮，再次检查是否已签到...")
            if self._find_visible_checkin_state() == "already":
                msg = f"今日已签到，未重复执行签到，现在有{prev_points_num}AK币"
                print(msg)
                Notice.serverJ(self.push_key, "Akile签到", msg)
                sys.exit(0)
            self._fail(
                "签到按钮和已签到按钮都无法加载出来。"
                "可能是网络波动、页面改版，或登录后被安全弹窗拦截。"
                "请稍后重试；若出现强制改密提示，请先手动改密。\n签到失败",
                screenshot="debug.png",
            )

    def __del__(self):
        if self.browser:
            try:
                self.browser.quit()
            except Exception:
                pass


if __name__ == "__main__":
    akile = AkileCheckin()
    try:
        akile.login()
        time.sleep(2)
        akile.check_in()
    finally:
        if akile.browser:
            try:
                akile.browser.quit()
            except Exception:
                pass
