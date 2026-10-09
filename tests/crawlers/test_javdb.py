"""测试 JavDB 影片站: 检索词展开, 检索顺序与命中判据.

素人番号在 DMM 上带数字头, 站内不带; 别名展开后检索词与命中判据必须成对, 否则搜到了也判未命中.
"""

import re
from collections.abc import Mapping
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from amane.config import SiteConfig
from amane.crawlers.http import HttpClient
from amane.crawlers.models import SearchQuery
from amane.crawlers.sites.javdb import JavDBCrawler, expand_search_terms


@pytest.mark.parametrize(
    ("number", "aliases", "expected"),
    [
        # 无别名: 只有原番号, 与原行为一致
        ("SSIS-497", {}, ["SSIS-497"]),
        ("300MIUM-123", {}, ["300MIUM-123"]),
        # 命中别名前缀: 替换结果作为首个检索词, 原番号回退在后
        ("300MIUM-123", {"300MIUM": "MIUM"}, ["MIUM-123", "300MIUM-123"]),
        ("300MIUM-123", {"300MIUM-": "MIUM-"}, ["MIUM-123", "300MIUM-123"]),
        ("259LUXU-1000", {"259LUXU": "LUXU"}, ["LUXU-1000", "259LUXU-1000"]),
        # 大小写不敏感; 替换词按配置原样写入
        ("300mium-123", {"300MIUM": "MIUM"}, ["MIUM-123", "300mium-123"]),
        ("300MIUM-123", {"300mium": "mium"}, ["mium-123", "300MIUM-123"]),
        # 最长前缀优先: 短前缀不参与, 避免 300 截断 300MIUM 的替换范围
        ("300MIUM-123", {"300": "X", "300MIUM": "MIUM"}, ["MIUM-123", "300MIUM-123"]),
        # 前缀不命中: 番号原样; 前缀必须命中开头
        ("SSIS-497", {"300MIUM": "MIUM"}, ["SSIS-497"]),
        ("300MIUM-123", {"MIUM": "MIUM"}, ["300MIUM-123"]),
        # 边界: 前缀即整段番号, 替换结果与原番号相同 → 不重复追加
        ("MIUM-123", {"MIUM-123": "MIUM-123"}, ["MIUM-123"]),
        # 边界: 前缀长于番号 / 空前缀键
        ("300MIUM-123", {"300MIUM-1234": "X"}, ["300MIUM-123"]),
        ("300MIUM-123", {"": "X"}, ["300MIUM-123"]),
        # 边界: 替换结果为空串 → 不产出检索词
        ("300MIUM-123", {"300MIUM-123": ""}, ["300MIUM-123"]),
        # 欧美日期号: 两种年份写法保留, 别名对两者各自展开
        ("Blacked.26.03.29", {}, ["Blacked.26.03.29", "Blacked.2026.03.29"]),
        (
            "Blacked.26.03.29",
            {"Blacked": "BlackedRaw"},
            ["BlackedRaw.26.03.29", "Blacked.26.03.29", "BlackedRaw.2026.03.29", "Blacked.2026.03.29"],
        ),
        # 边界: 空番号保留为唯一检索词
        ("", {"300MIUM": "MIUM"}, [""]),
    ],
)
def test_expand_search_terms(number: str, aliases: Mapping[str, str], expected: list[str]) -> None:
    assert expand_search_terms(number, aliases) == expected


class _SearchStub:
    """按检索词返回搜索结果页, 并记录实际请求的检索词顺序."""

    def __init__(self, pages: Mapping[str, str]) -> None:
        self._pages = pages
        self.terms: list[str] = []

    async def get_text(self, url: str, **kwargs: object) -> str:
        term = parse_term(url)
        self.terms.append(term)
        return self._pages.get(term, "<html><body></body></html>")


def parse_term(url: str) -> str:
    """从检索 URL 取 ``q`` 参数."""
    query = urlsplit(url).query
    return unquote(parse_qs(query)["q"][0])


def _slug(number: str) -> str:
    return re.sub(r"[^a-z0-9]", "", number.casefold())


def _entry(number: str) -> str:
    """搜索结果条目: 站内声明的番号在 ``div.video-title/strong``."""
    return f'<a class="box" href="/v/{_slug(number)}"><div class="video-title"><strong>{number}</strong></div></a>'


def _page(*numbers: str) -> str:
    return f"<html><body>{''.join(_entry(number) for number in numbers)}</body></html>"


def _url(number: str) -> str:
    return f"https://javdb.com/v/{_slug(number)}"


@pytest.mark.parametrize(
    ("number", "config", "pages", "expected_url", "expected_terms"),
    [
        # 素人番号: 别名检索词命中即返回, 不再请求原番号; 命中判据是别名检索词而不是原番号
        (
            "300MIUM-123",
            SiteConfig(number_aliases={"300MIUM": "MIUM"}),
            {"MIUM-123": _page("MIUM-123")},
            _url("MIUM-123"),
            ["MIUM-123"],
        ),
        # 别名检索词下的条目必须与别名检索词同一番号: 站内声明原番号时判未命中, 回退原番号后同样无结果
        (
            "300MIUM-123",
            SiteConfig(number_aliases={"300MIUM": "MIUM"}),
            {"MIUM-123": _page("300MIUM-123")},
            None,
            ["MIUM-123", "300MIUM-123"],
        ),
        # 别名检索词无结果时回退原番号: 原番号命中
        (
            "300MIUM-123",
            SiteConfig(number_aliases={"300MIUM": "MIUM"}),
            {"300MIUM-123": _page("300MIUM-123")},
            _url("300MIUM-123"),
            ["MIUM-123", "300MIUM-123"],
        ),
        # 用例内的番号大小写与配置前缀不一致时同样展开
        (
            "300mium-123",
            SiteConfig(number_aliases={"300MIUM": "MIUM"}),
            {"MIUM-123": _page("MIUM-123")},
            _url("MIUM-123"),
            ["MIUM-123"],
        ),
        # 无配置与空配置: 只请求原番号
        ("MIUM-123", None, {"MIUM-123": _page("MIUM-123")}, _url("MIUM-123"), ["MIUM-123"]),
        ("MIUM-123", SiteConfig(), {"MIUM-123": _page("MIUM-123")}, _url("MIUM-123"), ["MIUM-123"]),
        # 欧美日期号: 第一种年份写法无结果时改用另一种; 站内两种写法视为同一番号
        (
            "Blacked.26.03.29",
            None,
            {"Blacked.2026.03.29": _page("Blacked.26.03.29")},
            _url("Blacked.26.03.29"),
            ["Blacked.26.03.29", "Blacked.2026.03.29"],
        ),
        # 别名只命中前缀时同样展开; 番号其余部分原样保留
        (
            "259LUXU-1000",
            SiteConfig(number_aliases={"259LUXU": "LUXU"}),
            {"LUXU-1000": _page("LUXU-1000")},
            _url("LUXU-1000"),
            ["LUXU-1000"],
        ),
        # 全部检索词无结果
        ("SSIS-497", SiteConfig(number_aliases={"300MIUM": "MIUM"}), {}, None, ["SSIS-497"]),
    ],
)
@pytest.mark.asyncio
async def test_search_terms_and_hit_basis(
    number: str,
    config: SiteConfig | None,
    pages: Mapping[str, str],
    expected_url: str | None,
    expected_terms: list[str],
    http_client: HttpClient,
    mock_web_client: AsyncMock,
) -> None:
    stub = _SearchStub(pages)
    mock_web_client.get_text.side_effect = stub.get_text
    crawler = JavDBCrawler(client=http_client, config=config)

    assert await crawler._search(SearchQuery(number)) == expected_url
    assert stub.terms == expected_terms
