# -*- coding: utf-8 -*-
"""
Created on 2023/06/01 4:11 PM
---------
@summary:
---------
@author: wanghaisheng
@email: admin@tiktokastudio.com
"""

import json
import os
import re
from collections import defaultdict
from typing import Union, List

try:
    from typing import Literal  # python >= 3.8
except ImportError:  # python <3.8
    from typing_extensions import Literal
import asyncio

from playwright.async_api import Page, BrowserContext, ViewportSize, ProxySettings
from playwright.async_api import Playwright, Browser
from playwright.async_api import Response
from playwright.async_api import async_playwright

from tsup.utils import tools
from tsup.utils.log import log
from tsup.utils.webdriver.webdirver import *
import filecmp
import requests


class PlaywrightAsyncDriver(WebDriver):
    def __init__(
        self,
        *,
        page_on_event_callback: dict = None,
        storage_state_path: str = None,
        isRecodingVideo: bool = True,
        driver_type: Literal["chromium", "firefox", "webkit"] = "chromium",
        url_regexes: list = None,
        save_all: bool = False,
        **kwargs
    ):
        """

        Args:
            page_on_event_callback: page.on() 事件的回调 如 page_on_event_callback={"dialog": lambda dialog: dialog.accept()}
            storage_state_path: 保存浏览器状态的路径
            driver_type: 浏览器类型 chromium, firefox, webkit
            url_regexes: 拦截接口，支持正则，数组类型
            save_all: 是否保存所有拦截的接口, 默认只保存最后一个
            **kwargs:
        """
        super(PlaywrightAsyncDriver, self).__init__(**kwargs)
        self.driver: Playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.url = None
        self.storage_state_path = storage_state_path
        self.isRecodingVideo = isRecodingVideo
        self._driver_type = driver_type
        self._page_on_event_callback = page_on_event_callback
        self._url_regexes = url_regexes
        self._save_all = save_all

        if self._save_all and self._url_regexes:
            log.warning(
                "获取完拦截的数据后, 请主动调用PlaywrightDriver的clear_cache()方法清空拦截的数据，否则数据会一直累加，导致内存溢出"
            )
            self._cache_data = defaultdict(list)
        else:
            self._cache_data = {}

        # await self._setup()

    async def _setup(self):
        # 处理参数
        if self._proxy:
            proxy = self._proxy() if callable(self._proxy) else self._proxy
            proxy = self.format_context_proxy(proxy)
        else:
            proxy = None

        user_agent = (
            self._user_agent() if callable(self._user_agent) else self._user_agent
        )

        view_size = ViewportSize(
            width=self._window_size[0], height=self._window_size[1]
        )

        # 初始化浏览器对象
        self.driver = await async_playwright().start()
        self.browser = await getattr(self.driver, self._driver_type).launch(
            headless=self._headless,
            args=["--no-sandbox"],
            proxy=proxy,
            executable_path=self._executable_path,
            downloads_path=self._download_path,
        )

        if self.storage_state_path and os.path.exists(self.storage_state_path):
            if self._isRecodingVideo:
                self.context = await self.browser.new_context(
                    user_agent=user_agent,
                    no_viewport=True,
                    # Sets a consistent viewport for each page. Defaults to an 1280x720 viewport. no_viewport disables the fixed viewport.
                    viewport=view_size,
                    screen=view_size,
                    proxy=proxy,
                    storage_state=self.storage_state_path,
                    record_video_dir=os.getcwd() + os.sep + "screen-recording",
                )
            else:
                self.context = await self.browser.new_context(
                    user_agent=user_agent,
                    no_viewport=True,
                    # Sets a consistent viewport for each page. Defaults to an 1280x720 viewport. no_viewport disables the fixed viewport.
                    viewport=view_size,
                    screen=view_size,
                    proxy=proxy,
                    storage_state=self.storage_state_path,
                )
        else:
            if self._isRecodingVideo:
                self.context = await self.browser.new_context(
                    user_agent=user_agent,
                    screen=view_size,
                    viewport=view_size,
                    proxy=proxy,
                    record_video_dir=os.getcwd() + os.sep + "screen-recording",
                )
            else:
                self.context = await self.browser.new_context(
                    user_agent=user_agent,
                    screen=view_size,
                    viewport=view_size,
                    proxy=proxy,
                    record_video_dir=os.getcwd() + os.sep + "screen-recording",
                )

        if self._use_stealth_js:
            # https://gitcdn.xyz/repo/berstend/puppeteer-extra/stealth-js/stealth.min.js
            # https://raw.githubusercontent.com/requireCool/stealth.min.js/main/stealth.min.js
            # https://gitee.com/edwin_uestc/stealth.min.js/raw/main/stealth.min.js
            # https://github.com/requireCool/stealth.min.js
            url = "https://gitee.com/edwin_uestc/stealth.min.js/raw/main/stealth.min.js"
            url_ = "https://raw.githubusercontent.com/requireCool/stealth.min.js/main/stealth.min.js"
            local_filename = "stealth.min-latest.js"
            # NOTE the stream=True parameter below
            latest_path = os.path.join(
                os.path.dirname(__file__), "../js/" + local_filename
            )

            print("using stealth")
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(latest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        # If you have chunk encoded response uncomment if
                        # and set chunk_size parameter to None.
                        # if chunk:
                        f.write(chunk)
            path = os.path.join(os.path.dirname(__file__), "../js/stealth.min.js")
            if not os.path.exists(path):
                os.rename(latest_path, path)
            else:
                # Compare the
                # contents of both files
                comp = filecmp.cmp(latest_path, path, shallow=False)
                if comp:
                    os.remove(latest_path)
                    print("stealth is latest ")
                else:
                    os.remove(path)
                    os.rename(latest_path, path)
                    print("stealth is  upgraded just now ")

            await self.context.add_init_script(path=path)

        self.page = await self.context.new_page()
        self.page.set_default_timeout(self._timeout * 1000)

        if self._page_on_event_callback:
            for event, callback in self._page_on_event_callback.items():
                self.page.on(event, callback)

        if self._url_regexes:
            self.page.on("response", self.on_response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            log.error(exc_val)

        await self.quit()
        return True

    def format_context_proxy(self, proxy) -> ProxySettings:
        """
        Args:
            proxy: username:password@ip:port / ip:port
        Returns:
            {
                "server": "ip:port"
                "username": username,
                "password": password,
            }
            server: http://ip:port or socks5://ip:port. Short form ip:port is considered an HTTP proxy.
        """

        if "@" in proxy:
            certification, _proxy = proxy.split("@")
            username, password = certification.split(":")

            context_proxy = ProxySettings(
                server=_proxy,
                username=username,
                password=password,
            )
        else:
            context_proxy = ProxySettings(server=proxy)

        return context_proxy

    async def save_storage_stage(self):
        if self.storage_state_path:
            os.makedirs(os.path.dirname(self.storage_state_path), exist_ok=True)
            await self.context.storage_state(path=self.storage_state_path)

    async def quit(self):
        await self.page.close()
        await self.context.close()
        await self.browser.close()
        await self.driver.stop()

    @property
    def domain(self):
        return tools.get_domain(self.url or self.page.url)

    @property
    def cookies(self):
        cookies_json = {}
        for cookie in self.page.context.cookies():
            cookies_json[cookie["name"]] = cookie["value"]

        return cookies_json

    @cookies.setter
    async def cookies(self, val: Union[dict, List[dict]]):
        """
        设置cookie
        Args:
            val: List[{name: str, value: str, url: Union[str, NoneType], domain: Union[str, NoneType], path: Union[str, NoneType], expires: Union[float, NoneType], httpOnly: Union[bool, NoneType], secure: Union[bool, NoneType], sameSite: Union["Lax", "None", "Strict", NoneType]}]

        Returns:

        """
        if isinstance(val, list):
            await self.page.context.add_cookies(val)
        else:
            cookies = []
            for key, value in val.items():
                cookies.append(
                    {"name": key, "value": value, "url": self.url or self.page.url}
                )
            await self.page.context.add_cookies(cookies)

    @property
    async def user_agent(self):
        return await self.page.evaluate("() => navigator.userAgent")

    def on_response(self, response: Response):
        for regex in self._url_regexes:
            if re.search(regex, response.request.url):
                intercept_request = InterceptRequest(
                    url=response.request.url,
                    headers=response.request.headers,
                    data=response.request.post_data,
                )

                intercept_response = InterceptResponse(
                    request=intercept_request,
                    url=response.url,
                    headers=response.headers,
                    content=response.body(),
                    status_code=response.status,
                )
                if self._save_all:
                    self._cache_data[regex].append(intercept_response)
                else:
                    self._cache_data[regex] = intercept_response

    def get_response(self, url_regex) -> InterceptResponse:
        if self._save_all:
            response_list = self._cache_data.get(url_regex)
            if response_list:
                return response_list[-1]
        return self._cache_data.get(url_regex)

    def get_all_response(self, url_regex) -> List[InterceptResponse]:
        """
        获取所有匹配的响应, 仅在save_all=True时有效
        Args:
            url_regex:

        Returns:

        """
        response_list = self._cache_data.get(url_regex, [])
        if not isinstance(response_list, list):
            return [response_list]
        return response_list

    def get_text(self, url_regex):
        return (
            self.get_response(url_regex).content.decode()
            if self.get_response(url_regex)
            else None
        )

    def get_all_text(self, url_regex):
        """
        获取所有匹配的响应文本, 仅在save_all=True时有效
        Args:
            url_regex:

        Returns:

        """
        return [
            response.content.decode() for response in self.get_all_response(url_regex)
        ]

    def get_json(self, url_regex):
        return (
            json.loads(self.get_text(url_regex))
            if self.get_response(url_regex)
            else None
        )

    def get_all_json(self, url_regex):
        """
        获取所有匹配的响应json, 仅在save_all=True时有效
        Args:
            url_regex:

        Returns:

        """
        return [json.loads(text) for text in self.get_all_text(url_regex)]

    def clear_cache(self):
        self._cache_data = defaultdict(list)
